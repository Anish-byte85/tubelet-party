# 🚀 Deploy Tubelet Party to Render.com

Follow these steps to get a permanent HTTPS URL like
`https://tubelet-party.onrender.com` that anyone can join from any WiFi.

**Total time: ~10 minutes** • **Cost: Free**

---

## Step 1 — Put your code on GitHub

If you don't have git installed: https://git-scm.com/downloads

### 1a. Create a repo on GitHub
1. Go to https://github.com/new
2. Name it `tubelet-party`
3. Keep it **Public** (Render's free tier requires public repos, or connect your GitHub account for private ones)
4. **Don't** initialize with README/gitignore (we already have them)
5. Click **Create repository**

### 1b. Push your code
Open a terminal in your `tubelet_party` folder:

```bash
cd tubelet_party
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/tubelet-party.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

---

## Step 2 — Deploy on Render (Blueprint method — easiest)

Because we included `render.yaml`, Render will auto-configure everything.

1. Go to https://render.com and **Sign up** (use "Sign in with GitHub" — free)
2. Click **New +** (top right) → **Blueprint**
3. Click **Connect a repository** → select `tubelet-party`
4. Render reads `render.yaml` and shows the service it will create → click **Apply**
5. Wait ~3–5 minutes for the first build

That's it! When it's live, you'll see a URL like:
```
https://tubelet-party-xxxx.onrender.com
```

---

## Step 2 (alternate) — Manual setup

If Blueprint doesn't work for some reason:

1. Render dashboard → **New +** → **Web Service**
2. **Connect repository** → pick `tubelet-party`
3. Fill in the form:
   | Field | Value |
   |---|---|
   | **Name** | `tubelet-party` |
   | **Region** | pick closest to your friends |
   | **Branch** | `main` |
   | **Runtime** | `Python 3` |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT --timeout 120 app:app` |
   | **Instance Type** | `Free` |
4. Scroll down → **Advanced** → **Add Environment Variable**:
   - Key: `SECRET_KEY`
   - Value: run this in a terminal and paste the output:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
5. Set **Health Check Path**: `/healthz`
6. Click **Create Web Service**

---

## Step 3 — Test it!

1. Open the Render URL in your browser
2. Sign up for an account (any email works — no verification)
3. Create a room → copy the invite link (🔗 Copy invite)
4. Text the link to a friend
5. They open it on their phone, sign up, and they're in your room instantly

---

## ⚠️ Free tier notes

- **Sleeps after 15 min idle** — first hit takes 30-60 sec to wake up. After that it's snappy.
- **Keep alive trick**: create a free account at https://cron-job.org and set a cron job to hit `https://YOUR-APP.onrender.com/healthz` every 10 minutes.
- **Database resets on redeploy** — SQLite lives on ephemeral disk. For persistent data:
  - Free option: use Render's PostgreSQL free tier (requires small code change)
  - Cheap option: attach a Render Disk ($1/month) and set env var `DATA_DIR=/var/data`

---

## 🔄 Updating your app later

Any push to `main` on GitHub triggers an auto-deploy:
```bash
# Make your changes locally, then:
git add .
git commit -m "Added new feature"
git push
```
Render rebuilds and deploys in ~2 minutes.

---

## 🐛 Troubleshooting

**"Application error" after deploy:**
- Open Render dashboard → your service → **Logs** tab
- Look for red error lines. Most common:
  - Missing `SECRET_KEY` → add it in Environment
  - Package install failed → check `requirements.txt`

**Login/session doesn't persist:**
- Make sure you're using the **HTTPS** URL, not HTTP
- Cookies won't survive HTTP on modern browsers

**Chat/video sync doesn't work:**
- Open browser dev tools (F12) → Console → look for red errors
- Should see `socket.io` messages. If it says WebSocket failed, your network blocks WS — the app auto-falls back to polling.

**Room join button does nothing / says "not found":**
- Codes are case-insensitive but must be exactly 6 characters (A–Z, 0–9)
- Rooms are stored in the DB — they persist unless the free-tier disk gets wiped on redeploy

**Free tier is too slow / sleepy:**
- Upgrade to **Starter** ($7/mo) for always-on + more CPU
- Or try Railway.app (similar flow, generous free tier)

---

## 🎉 You're done!

Your app is live. Share `https://YOUR-APP.onrender.com` with anyone. Enjoy the show! 🍿
