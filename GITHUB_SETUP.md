# Put the Boat Tracker on the web (GitHub Pages)

One-time setup, about 15 minutes. Afterward the dashboard lives at a public URL
like `https://YOURNAME.github.io/boat-tracker/` and updates automatically.

## How the pieces fit

1. Claude's daily 8 AM task scans Craigslist and refreshes `dashboard.html` in this folder (Claude app must be open).
2. `publish.bat` copies it to `index.html` and pushes the folder to GitHub.
3. GitHub Pages serves the site. Windows Task Scheduler runs publish.bat daily so no clicks are needed.

## Step 1 — GitHub account and repo

1. Create a free account at https://github.com (skip if you have one).
2. Click **+** (top right) → **New repository**. Name: `boat-tracker`. Visibility: **Public** (required for free Pages). Do NOT add a README. Click **Create repository**.

Note: public means anyone with the link can see the site and data — it's all public Craigslist info, so nothing sensitive.

## Step 2 — Install Git for Windows

Download from https://git-scm.com/download/win and install with all default options.

## Step 3 — Connect this folder to the repo

Open this folder in File Explorer, click the address bar, type `cmd`, press Enter. Then run these commands one at a time (replace YOURNAME with your GitHub username):

    git init -b main
    git add .
    git commit -m "initial boat tracker"
    git remote add origin https://github.com/YOURNAME/boat-tracker.git
    git push -u origin main

The push opens a browser window to sign in to GitHub — approve it once and Git remembers you.

## Step 4 — Turn on GitHub Pages

On your repo page: **Settings → Pages** → under "Build and deployment", Source: **Deploy from a branch**, Branch: **main**, folder **/ (root)** → Save.

After a minute your site is live at:

    https://YOURNAME.github.io/boat-tracker/

Bookmark it, share it — it works on phones too.

## Step 5 — Automate the daily publish

1. Press Start, search **Task Scheduler**, open it.
2. **Create Basic Task** → Name: `Publish boat tracker` → Daily → 8:30 AM → **Start a program** → Browse to `publish.bat` in this folder → Finish.

Done. Each morning: Claude refreshes the data at 8:00 (if the Claude app is open), Windows publishes at 8:30. If a day is missed, the next run catches up — publish.bat can also be double-clicked to publish immediately.
