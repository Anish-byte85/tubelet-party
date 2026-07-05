"""
Tubelet Party — Watch YouTube together, chat live.
Production-ready for Render.com deployment.

Key fixes in this version:
- Room joining works via code entry OR direct URL (fixed redirect flow)
- Any authenticated user can join any room (not just admin)
- init_db() runs at import time so gunicorn/eventlet workers on Render work
- WSGI-compatible: exposes `app` for `gunicorn` (Procfile uses eventlet worker)
- Optional `/join/<code>` short-link route for shareable invites
- Better mobile: viewport, safe-area padding, big touch targets, responsive layout
- Perf: DB indexes, connection reuse, single lookup per socket op, lighter payloads
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
import string
import time
from contextlib import closing
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from flask import (Flask, flash, g, redirect, render_template, request, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# App / config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Render's persistent disk (if attached) mounts to /var/data; fall back to local
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "party.db")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    # Behind Render's proxy — trust HTTPS so secure cookies work
    PREFERRED_URL_SCHEME="https",
    TEMPLATES_AUTO_RELOAD=False,
)

# Trust proxy headers so url_for(..., _external=True) uses https on Render
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"

# Choose async mode: eventlet on server, threading for local dev fallback
try:
    import eventlet  # noqa: F401
    ASYNC_MODE = "eventlet"
except ImportError:
    ASYNC_MODE = "threading"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=ASYNC_MODE,
    ping_interval=25,
    ping_timeout=60,
)

# In-memory state (per-worker; that's why Procfile uses 1 worker)
PRESENCE: dict[str, dict[str, dict]] = {}  # {code: {sid: {"username","user_id"}}}
PLAYER_STATE: dict[str, dict] = {}          # {code: {"video_id","playing","position","updated_at"}}

# Cache room -> admin_id to avoid a DB hit on every socket event
_ADMIN_CACHE: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rooms (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                admin_id INTEGER NOT NULL,
                video_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(admin_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_code) REFERENCES rooms(code) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_code, id);
            CREATE INDEX IF NOT EXISTS idx_rooms_admin ON rooms(admin_id);
            """
        )
        db.commit()


# Initialize DB at import time so gunicorn workers on Render have it ready
init_db()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class User(UserMixin):
    def __init__(self, row: sqlite3.Row):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"]


@login_manager.user_loader
def load_user(user_id: str):
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(row) if row else None


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------
YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CODE_RE = re.compile(r"^[A-Z0-9]{6}$")
CODE_ALPHABET = string.ascii_uppercase + string.digits


def extract_video_id(url_or_id: str) -> str | None:
    if not url_or_id:
        return None
    s = url_or_id.strip()
    if YT_ID_RE.match(s):
        return s
    try:
        p = urlparse(s if "://" in s else "https://" + s)
    except Exception:
        return None
    if p.hostname == "youtu.be":
        vid = p.path.lstrip("/").split("/")[0]
        return vid if YT_ID_RE.match(vid) else None
    if p.hostname and "youtube" in p.hostname:
        if p.path == "/watch":
            vid = parse_qs(p.query).get("v", [None])[0]
            return vid if vid and YT_ID_RE.match(vid) else None
        parts = p.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("embed", "shorts", "v", "live"):
            return parts[1] if YT_ID_RE.match(parts[1]) else None
    return None


def new_room_code() -> str:
    db = get_db()
    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not db.execute("SELECT 1 FROM rooms WHERE code = ?", (code,)).fetchone():
            return code
    raise RuntimeError("Could not generate unique room code")


def get_room(code: str) -> sqlite3.Row | None:
    if not code or not CODE_RE.match(code):
        return None
    return get_db().execute("SELECT * FROM rooms WHERE code = ?", (code,)).fetchone()


# ---------------------------------------------------------------------------
# Health check (for Render)
# ---------------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return {"ok": True, "async_mode": ASYNC_MODE}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(request.args.get("next") or url_for("lobby"))
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        e = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if not (u and e and pw):
            flash("All fields are required.", "danger")
        elif len(u) < 2 or len(u) > 20:
            flash("Username must be 2–20 characters.", "danger")
        elif not re.match(r"^[A-Za-z0-9_]+$", u):
            flash("Username can only contain letters, numbers and underscores.", "danger")
        elif len(pw) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (username, email, password_hash, created_at) VALUES (?,?,?,?)",
                    (u, e, generate_password_hash(pw), datetime.utcnow().isoformat()),
                )
                db.commit()
                # Auto-login for smooth UX
                row = db.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
                login_user(User(row), remember=True)
                flash("Welcome to Tubelet Party! 🎉", "success")
                return redirect(request.args.get("next") or url_for("lobby"))
            except sqlite3.IntegrityError:
                flash("Username or email already taken.", "danger")
    return render_template("register.html", next=request.args.get("next", ""))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(request.args.get("next") or url_for("lobby"))
    if request.method == "POST":
        ident = request.form.get("identifier", "").strip()
        pw = request.form.get("password", "")
        row = get_db().execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (ident, ident.lower()),
        ).fetchone()
        if row and check_password_hash(row["password_hash"], pw):
            login_user(User(row), remember=True)
            return redirect(request.args.get("next") or url_for("lobby"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Lobby / rooms
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def lobby():
    my_rooms = get_db().execute(
        "SELECT * FROM rooms WHERE admin_id = ? ORDER BY created_at DESC",
        (current_user.id,),
    ).fetchall()
    return render_template("lobby.html", my_rooms=my_rooms)


@app.route("/room/create", methods=["POST"])
@login_required
def create_room():
    name = (request.form.get("name") or "").strip() or f"{current_user.username}'s party"
    vid = extract_video_id(request.form.get("url", "")) or None
    code = new_room_code()
    db = get_db()
    db.execute(
        "INSERT INTO rooms (code, name, admin_id, video_id, created_at) VALUES (?,?,?,?,?)",
        (code, name[:60], current_user.id, vid, datetime.utcnow().isoformat()),
    )
    db.commit()
    _ADMIN_CACHE[code] = current_user.id
    if vid:
        PLAYER_STATE[code] = {"video_id": vid, "playing": False, "position": 0, "updated_at": time.time()}
    return redirect(url_for("room", code=code))


@app.route("/room/join", methods=["POST", "GET"])
@login_required
def join_room_form():
    code = (request.values.get("code") or "").strip().upper()
    if not CODE_RE.match(code):
        flash("Room code must be 6 letters/numbers.", "danger")
        return redirect(url_for("lobby"))
    if not get_room(code):
        flash(f"Room “{code}” not found. Check the code and try again.", "danger")
        return redirect(url_for("lobby"))
    return redirect(url_for("room", code=code))


# Short share link: /j/ABC123  — friendly for texting
@app.route("/j/<code>")
def join_short(code):
    code = (code or "").upper()
    if not current_user.is_authenticated:
        return redirect(url_for("login", next=url_for("room", code=code)))
    if not CODE_RE.match(code) or not get_room(code):
        flash(f"Room “{code}” not found.", "danger")
        return redirect(url_for("lobby"))
    return redirect(url_for("room", code=code))


@app.route("/room/<code>")
@login_required
def room(code):
    code = (code or "").upper()
    row = get_room(code)
    if not row:
        flash("Room not found.", "danger")
        return redirect(url_for("lobby"))

    _ADMIN_CACHE[code] = row["admin_id"]
    admin_name = get_db().execute(
        "SELECT username FROM users WHERE id = ?", (row["admin_id"],)
    ).fetchone()["username"]
    is_admin = current_user.id == row["admin_id"]

    messages = get_db().execute(
        """SELECT username, body, created_at
             FROM messages WHERE room_code = ?
            ORDER BY id DESC LIMIT 50""",
        (code,),
    ).fetchall()
    messages = list(reversed(messages))

    return render_template(
        "room.html",
        room=row,
        is_admin=is_admin,
        admin_name=admin_name,
        messages=messages,
    )


@app.route("/room/<code>/delete", methods=["POST"])
@login_required
def delete_room(code):
    code = (code or "").upper()
    db = get_db()
    row = db.execute("SELECT admin_id FROM rooms WHERE code = ?", (code,)).fetchone()
    if row and row["admin_id"] == current_user.id:
        db.execute("DELETE FROM rooms WHERE code = ?", (code,))
        db.commit()
        PRESENCE.pop(code, None)
        PLAYER_STATE.pop(code, None)
        _ADMIN_CACHE.pop(code, None)
        flash("Room deleted.", "info")
    return redirect(url_for("lobby"))


# ---------------------------------------------------------------------------
# SocketIO helpers
# ---------------------------------------------------------------------------
def _admin_of(code: str) -> int | None:
    if code in _ADMIN_CACHE:
        return _ADMIN_CACHE[code]
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT admin_id FROM rooms WHERE code = ?", (code,)).fetchone()
    if row:
        _ADMIN_CACHE[code] = row["admin_id"]
        return row["admin_id"]
    return None


def _room_video_id(code: str) -> str | None:
    st = PLAYER_STATE.get(code)
    if st:
        return st.get("video_id")
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT video_id FROM rooms WHERE code = ?", (code,)).fetchone()
        return row["video_id"] if row else None


def _viewer_list(code: str) -> list[dict]:
    admin_id = _admin_of(code)
    seen = set()
    out = []
    for info in PRESENCE.get(code, {}).values():
        if info["username"] in seen:
            continue
        seen.add(info["username"])
        out.append({"username": info["username"], "is_admin": info["user_id"] == admin_id})
    return out


def _require_admin(code: str) -> bool:
    return current_user.is_authenticated and current_user.id == _admin_of(code)


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------
@socketio.on("join")
def on_join(data):
    if not current_user.is_authenticated:
        emit("error", {"text": "You must be signed in."})
        return
    code = ((data or {}).get("code") or "").upper()
    if not code or not _admin_of(code):
        emit("error", {"text": "Room not found."})
        return
    join_room(code)
    PRESENCE.setdefault(code, {})[request.sid] = {
        "username": current_user.username,
        "user_id": current_user.id,
    }
    emit("system", {"text": f"👋 {current_user.username} joined"}, to=code)
    emit("viewers", _viewer_list(code), to=code)

    state = PLAYER_STATE.get(code)
    if state and state.get("video_id"):
        emit("sync", state)
    else:
        vid = _room_video_id(code)
        if vid:
            emit("load", {"video_id": vid, "playing": False, "position": 0})


@socketio.on("disconnect")
def on_disconnect():
    for code, sids in list(PRESENCE.items()):
        if request.sid in sids:
            uname = sids[request.sid]["username"]
            del sids[request.sid]
            emit("system", {"text": f"👋 {uname} left"}, to=code)
            emit("viewers", _viewer_list(code), to=code)
            if not sids:
                PRESENCE.pop(code, None)


@socketio.on("chat")
def on_chat(data):
    if not current_user.is_authenticated:
        return
    code = ((data or {}).get("code") or "").upper()
    body = ((data or {}).get("body") or "").strip()[:500]
    if not code or not body or not _admin_of(code):
        return
    ts = datetime.utcnow().isoformat()
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute(
            "INSERT INTO messages (room_code, user_id, username, body, created_at) VALUES (?,?,?,?,?)",
            (code, current_user.id, current_user.username, body, ts),
        )
        db.commit()
    emit("chat", {
        "username": current_user.username,
        "body": body,
        "created_at": ts,
        "is_admin": current_user.id == _admin_of(code),
    }, to=code)


@socketio.on("typing")
def on_typing(data):
    if not current_user.is_authenticated:
        return
    code = ((data or {}).get("code") or "").upper()
    if code and _admin_of(code):
        emit("typing", {"username": current_user.username}, to=code, include_self=False)


@socketio.on("player")
def on_player(data):
    code = ((data or {}).get("code") or "").upper()
    action = (data or {}).get("action")
    position = float((data or {}).get("position", 0) or 0)
    if not code or action not in ("play", "pause", "seek"):
        return
    if not _require_admin(code):
        emit("error", {"text": "Only the host can control the player."})
        return
    playing = action != "pause"
    PLAYER_STATE[code] = {
        "video_id": _room_video_id(code),
        "playing": playing,
        "position": position,
        "updated_at": time.time(),
    }
    # Broadcast server timestamp so viewers can compensate for network latency
    emit("player", {"action": action, "position": position, "ts": time.time()},
         to=code, include_self=False)


@socketio.on("sync_request")
def on_sync_request(data):
    """Viewer asks for latest player state (reconnect / drift recovery)."""
    code = ((data or {}).get("code") or "").upper()
    if not code:
        return
    st = PLAYER_STATE.get(code)
    if st and st.get("video_id"):
        emit("sync", st)


@socketio.on("load")
def on_load(data):
    code = ((data or {}).get("code") or "").upper()
    vid = extract_video_id((data or {}).get("url", ""))
    if not code:
        return
    if not vid:
        emit("error", {"text": "Invalid YouTube URL."})
        return
    if not _require_admin(code):
        emit("error", {"text": "Only the host can change the video."})
        return
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute("UPDATE rooms SET video_id = ? WHERE code = ?", (vid, code))
        db.commit()
    PLAYER_STATE[code] = {"video_id": vid, "playing": False, "position": 0, "updated_at": time.time()}
    emit("load", {"video_id": vid, "playing": False, "position": 0}, to=code)
    emit("system", {"text": f"🎬 {current_user.username} changed the video"}, to=code)


# ---------------------------------------------------------------------------
# Entry point (local dev)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)
