# 🎉 Tubelet Party

Watch YouTube together in perfect sync with friends, anywhere. Live chat, host controls, mobile-friendly.

## ✨ Features

- 🔐 Local login (SQLite + bcrypt-hashed passwords)
- 🎬 Multi-room with 6-char join codes
- 👑 Room creator is the host — only they control play/pause/seek/video
- 🔄 Real-time sync via WebSockets (Flask-SocketIO)
- 💬 Live chat + typing indicators + presence
- 📱 Mobile-first responsive UI with tabbed layout on small screens
- 🌐 Works across any network (deploy to Render for a permanent URL)
- ⚡ Fast: DB indexes, in-memory caching, connection reuse

## 🚀 Deploy (recommended)

**See [`HOSTING.md`](HOSTING.md)** for a step-by-step guide to deploy on **Render.com** in ~10 minutes. Includes one-click Blueprint via `render.yaml`.

## 💻 Local dev

```bash
cd tubelet_party
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## 🕹 How to use

1. **Register/Login** → land in the Lobby
2. **Create a party** — get a 6-char code (e.g. `A7K2P9`); you're the host
3. **Share** the code or the copy-invite link (`/j/CODE`)
4. Friends **Join a party** with the code → same player, same time
5. As host: paste a YouTube URL → hit **Load**
6. Play / pause / seek — everyone stays in sync
7. Chat on the right (or the 💬 tab on mobile) at any time

## 📂 Structure

```
tubelet_party/
├── app.py              # Flask + Socket.IO — routes, DB, sync logic
├── requirements.txt    # Pinned versions
├── Procfile            # Gunicorn + eventlet for prod
├── runtime.txt         # Python version pin
├── render.yaml         # Render Blueprint (one-click deploy)
├── HOSTING.md          # Full deploy guide
├── README.md
├── .gitignore
└── templates/
    ├── base.html       # Layout + mobile-first dark theme
    ├── login.html
    ├── register.html
    ├── lobby.html      # Create/join/list rooms
    └── room.html       # Player + chat + viewers (with mobile tabs)
```

## 🔒 Production notes

- Set `SECRET_KEY` env var to a long random string (render.yaml does this automatically)
- Uses `ProxyFix` middleware so it works behind Render's load balancer
- WAL mode enabled on SQLite for better concurrent writes
- Single gunicorn worker + eventlet is required (Socket.IO needs sticky state)

Enjoy the show 🍿
