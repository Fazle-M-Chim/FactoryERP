# Deployment Guide — Railway.app

This guide deploys the HIC Industries Factory Production System to Railway.app.
**Cost:** $5/month (~₹420). **Time:** 30–45 minutes.

Railway handles HTTPS, automatic restarts, monitoring, and logging automatically.
Updating the live site is a single `git push`.

---

## What You Need Before Starting

1. A GitHub account — [github.com](https://github.com) (free)
2. A Railway account — [railway.app](https://railway.app) (sign up with GitHub)
3. Git installed on your Mac — check with `git --version` in Terminal
4. The `FactoryProduction` folder on your Mac

---

## Step 1 — Install Git (if needed)

Open Terminal (Cmd+Space → type "Terminal") and run:
```bash
git --version
```
If it says "command not found", install it:
```bash
xcode-select --install
```

---

## Step 2 — Install the Railway CLI

```bash
# Install Homebrew first if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Then install Railway CLI
brew install railway
```

Verify it installed:
```bash
railway --version
```

---

## Step 3 — Push Your Code to GitHub

### 3a. Create a new GitHub repository
1. Go to [github.com/new](https://github.com/new)
2. Name it `FactoryProduction`
3. Set it to **Private** (important — don't make factory data public)
4. Leave everything else default, click **Create repository**

### 3b. Push your code
Open Terminal, navigate to your project folder:
```bash
cd /Users/fazlemalak/PycharmProjects/FactoryProduction
```

Run these commands one by one:
```bash
git init
git add .
git commit -m "Initial deploy"
git branch -M main
git remote add origin https://github.com/Fazle-M-Ch/FactoryProduction.git
git push -u origin main
```

> Replace `Fazle-M-Ch` with your actual GitHub username.

---

## Step 4 — Create a Railway Project

```bash
# Log in to Railway
railway login

# This opens a browser — click "Authorize"
```

Then in your project folder:
```bash
cd /Users/fazlemalak/PycharmProjects/FactoryProduction
railway init
```

When prompted:
- **Project name:** `FactoryProduction` (or any name you like)
- **Environment:** `production`

---

## Step 5 — Add a Persistent Volume (for SQLite)

This is critical. Railway's filesystem resets on every deploy — without a persistent volume, the database is wiped every time you update the code.

1. Go to [railway.app/dashboard](https://railway.app/dashboard)
2. Click your `FactoryProduction` project
3. Click **New** → **Volume**
4. Set mount path to: `/data`
5. Size: **1 GB** (more than enough)
6. Click **Create**

Railway will set `RAILWAY_VOLUME_MOUNT_PATH=/data` automatically.
The app is already configured to detect this and store `hic.db` there.

---

## Step 6 — Set Environment Variables

In Railway dashboard → your project → **Variables** tab, add:

| Variable | Value |
|----------|-------|
| `HIC_SECRET_KEY` | A long random string (see below to generate one) |

Generate a secret key — run this in Terminal:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output and paste it as the value for `HIC_SECRET_KEY`.

**Do not use the default `hic2024` password once live.**
Change it immediately after first login via Settings → Users.

---

## Step 7 — Deploy

```bash
cd /Users/fazlemalak/PycharmProjects/FactoryProduction
railway up
```

Railway will:
1. Detect it's a Python app
2. Install everything from `requirements.txt`
3. Start the app with Gunicorn
4. Give you a live URL like `https://factoryproduction-production.up.railway.app`

Watch the logs — it should end with something like:
```
[INFO] Listening at: http://0.0.0.0:XXXX
```

---

## Step 8 — Open Your Live Site

```bash
railway open
```

This opens your live site in the browser. Log in with `admin` / `hic2024`, immediately go to **Settings → Users** and change the admin password.

---

## Step 9 — Get a Domain Name (Optional but recommended)

### Buy a domain
Good options for an Indian business:
- [GoDaddy.in](https://godaddy.in) — search for `hicindustries.in` (~₹800/year)
- [Namecheap.com](https://namecheap.com) — often cheaper
- [BigRock.in](https://bigrock.in) — Indian registrar

Suggested names: `hicindustries.in`, `hicproduction.in`, `factory.hicindustries.in`

### Connect it to Railway
1. In Railway dashboard → your project → **Settings** tab
2. Click **Custom Domain**
3. Enter your domain (e.g. `app.hicindustries.in`)
4. Railway gives you a CNAME record to add in your domain registrar's DNS settings
5. Add the CNAME, wait 5–15 minutes, and your domain is live with HTTPS automatically

---

## Updating the Site (After Making Changes)

Every future update is just three commands:
```bash
cd /Users/fazlemalak/PycharmProjects/FactoryProduction
git add .
git commit -m "Description of what changed"
git push
```

Railway detects the push and automatically redeploys. Downtime is about 10–20 seconds.

---

## Monitoring & Logs

**View live logs:**
```bash
railway logs
```

Or in Railway dashboard → your project → **Deployments** → click any deployment → **Logs**

**Check if the site is up:**
Railway dashboard shows a green dot when healthy, red when down.

**Usage metrics:** CPU, memory, and bandwidth shown in the Railway dashboard under **Metrics**.

---

## Backing Up Your Database

The database lives at `/data/hic.db` on the Railway server. 

**Download a backup:**
```bash
railway run -- cat /data/hic.db > backup_$(date +%Y%m%d).db
```

Do this before every update that changes the database schema. Store the backup somewhere safe (Google Drive, local drive).

**Recommended:** back up once a week manually, or before any significant changes.

---

## If Something Goes Wrong

**Site is down:**
```bash
railway logs --tail 50
```
Look for error messages at the bottom.

**Need to restart:**
Railway dashboard → your project → **Deployments** → **Redeploy**

**Database got wiped:**
This should not happen with the persistent volume. If it did, check that the volume is still mounted at `/data` in Railway dashboard.

**App crashes on startup:**
Almost always a missing environment variable or a Python import error. Check logs.

---

## Cost Summary

| Item | Cost |
|------|------|
| Railway Hobby plan | $5/month (~₹420) |
| 1 GB persistent volume | Included |
| HTTPS certificate | Free (automatic) |
| Domain name (optional) | ₹800–1500/year |
| **Total** | **~₹420/month + optional domain** |

Railway's free tier exists but the app sleeps after 15 minutes of inactivity — not suitable for a factory floor system where someone might open it at any time. The $5 Hobby plan keeps it always on.

---

## Local Development (Continuing to Work Locally)

Keep running locally on your Mac for development:
```bash
cd /Users/fazlemalak/PycharmProjects/FactoryProduction
python app.py
# http://192.168.31.89:8080 (local network)
```

The local copy uses `instance/hic.db`. The Railway copy uses `/data/hic.db`. They are separate databases — changes to one don't affect the other. This is intentional: test locally, push when happy.

---

*HIC Industries Production Management System — Deployment Guide*  
*Last updated: June 2026*
