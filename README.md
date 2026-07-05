# 🎉 Tubelet Party

Watch YouTube together in perfect sync with friends, anywhere. **Custom video player** with your own controls, live chat, video queue, and full mobile responsiveness — including immersive fullscreen with sidebar chat.

## ✨ Features

### 🎬 Custom YouTube Player (like YouTube's own UI)
- **Play/Pause, Seek bar** with hover preview and buffered indicator
- **Volume slider + mute**
- **Playback speed** (0.25× → 2×)
- **Quality selector** (auto / 144p → 4K, based on available levels)
- **Captions (CC)** toggle
- **Picture-in-picture** (where supported)
- **Fullscreen** with immersive layout + landscape lock on mobile
- **Big center play button** animation, loading spinner
- **Keyboard shortcuts**: `space` play/pause, `←/→` seek 5s, `f` fullscreen, `m` mute, `c` captions
- **YouTube's native controls are HIDDEN** — viewers cannot bypass the host

### 👑 Host-only control
- Only the room creator can play/pause/seek/change video
- Viewers see the same custom UI but seek + play buttons are read-only
- Viewers get a status pill ("● Live sync" / "⏸ Paused by host")
- Auto-play next video when current one ends

### 💬 Live chat + queue
- Real-time chat with typing indicators, presence, host badges
- **Video queue** — anyone can add, host controls "Play next"
- **Floating chat button** on mobile (with unread badge)
- **Bottom-sheet drawer** with swipe-to-close
- **In-fullscreen chat toggle** — chat sidebar appears on the right, close button top-right

### 📱 Mobile responsive
- Landscape fullscreen → video left, chat right (like YouTube Live)
- Portrait → chat opens as bottom sheet drawer
- PWA-ready meta tags, safe-area insets for notched devices

### 🔐 Auth + rooms
- Local login (SQLite + hashed passwords)
- Multi-room with 6-char join codes + shareable `/j/CODE` links
- **Works across any network** (deploy to Render, tunnel with cloudflared, etc.)

## 🚀 Deploy

See **[`HOSTING.md`](HOSTING.md)** — one-click Blueprint deploy to Render in ~10 min.

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

1. **Register/Login** → land in Lobby
2. **Create a party** — get a 6-char code; you're the host
3. **Share** the code or copy-invite link (`/j/CODE`)
4. Friends **Join** with the code → same player, same time
5. As host: paste YouTube URL → **Load**; play/pause/seek — all viewers sync instantly
6. Add videos to the **queue** — click ⏭ Next to play the next one
7. Go **fullscreen** for immersive mode; open chat sidebar with 💬 button

## 📂 Structure

```
tubelet_party/
├── app.py              # Flask + Socket.IO — routes, DB, sync, queue
├── requirements.txt    # gevent-based (no eventlet warnings)
├── Procfile            # gunicorn + gevent-websocket for Render
├── runtime.txt         # Python 3.11.9
├── render.yaml         # Render Blueprint (one-click deploy)
├── HOSTING.md          # Full deploy guide
├── README.md
├── .gitignore
└── templates/
    ├── base.html       # Layout + mobile-first dark theme
    ├── login.html
    ├── register.html
    ├── lobby.html      # Create/join/list rooms
    └── room.html       # Custom YT player + chat + queue + viewers
```

## 🔒 Production notes

- Set `SECRET_KEY` env var (render.yaml auto-generates)
- Uses `ProxyFix` for Render's load balancer
- SQLite WAL mode for concurrent writes
- Single gunicorn worker + gevent-websocket (Socket.IO needs sticky state)
- YouTube IFrame Player API — fully TOS-compliant

Enjoy the show 🍿
