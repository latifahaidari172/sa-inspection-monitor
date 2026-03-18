SA Inspection Monitor — Render.com Setup Guide
===============================================
Runs every 30 seconds, 24/7, completely free.
No laptop needed. Books automatically when a slot appears.


WHAT YOU NEED
──────────────
  • Your existing GitHub account (already set up)
  • A free Render.com account (takes 2 minutes)
  • These 2 files: monitor.py and requirements.txt


STEP 1 — Add the new files to your GitHub repository
──────────────────────────────────────────────────────
  Your existing GitHub repository already has the old files.
  We need to add the new ones.

  1. Go to github.com and open your sa-inspection-monitor repository
  2. Click "Add file" → "Upload files"
  3. Drag in both files:
       • monitor.py          (replace the existing one)
       • requirements.txt    (new file)
  4. Click "Commit changes"


STEP 2 — Create a free Render account
───────────────────────────────────────
  1. Go to https://render.com
  2. Click "Get Started for Free"
  3. Click "Continue with GitHub" — this links your GitHub account
     so Render can access your repository
  4. Authorise Render to access your GitHub when it asks


STEP 3 — Create a new Background Worker
─────────────────────────────────────────
  1. Once logged in to Render, click "New +" (top right)
  2. Click "Background Worker"
  3. Click "Connect a repository"
  4. Find and click "sa-inspection-monitor"
  5. Fill in the settings:
       Name:          sa-inspection-monitor
       Region:        Singapore (closest to Adelaide)
       Branch:        main
       Runtime:       Python 3
       Build Command: pip install -r requirements.txt
       Start Command: python monitor.py
  6. Scroll down to "Instance Type" — make sure FREE is selected
  7. DO NOT click Deploy yet — go to Step 4 first


STEP 4 — Add your personal details as Environment Variables
─────────────────────────────────────────────────────────────
  Still on the same page, scroll down to find
  "Environment Variables". Add each one by clicking
  "Add Environment Variable":

     Key: LICENCE_NUMBER        Value: your licence number
     Key: DATE_OF_BIRTH         Value: your DOB (e.g. 25031985)
     Key: LAST_NAME             Value: your surname
     Key: GMAIL_ADDRESS         Value: your gmail address
     Key: GMAIL_APP_PASSWORD    Value: your 16-char app password
     Key: NOTIFY_EMAIL          Value: email to send alerts to

  These are encrypted — Render staff cannot see them.


STEP 5 — Deploy
────────────────
  1. Click "Create Background Worker" at the bottom
  2. Render will build and start your monitor automatically
  3. You'll see a log window — after about 1 minute you should
     see lines like:
       [INFO] SA Inspection Monitor — Render.com version
       [INFO] Checking every 30 seconds, 24/7
       [INFO] Check #1 at 09:15:00
       [INFO] No slots available.
       [INFO] Sleeping 30s...

  That means it's working!


CHECKING THE LOGS
──────────────────
  Any time you want to check what it's doing:
  1. Go to render.com → your sa-inspection-monitor service
  2. Click "Logs" in the left sidebar
  You'll see every check in real time.


WHAT HAPPENS NEXT
──────────────────
  The monitor runs every 30 seconds forever.
  When it finds a slot before 22/04/2026 it will:
    1. Automatically book it
    2. Email you immediately with the booking details
    3. Keep running in case the booking didn't go through

  You don't need to do anything — just wait for the email.


THE SPREADSHEET
────────────────
  results.csv is saved inside the Render service.
  To download it at any time:
  1. Go to render.com → your service → "Shell"
  2. Type: cat results.csv
  It will print all the results. You can copy and paste
  into Excel or Numbers.

  (A better download option can be added later if needed)


SOMETHING WRONG?
─────────────────
  Go to render.com → your service → Logs
  Look for lines marked [ERROR] and send them for help.
