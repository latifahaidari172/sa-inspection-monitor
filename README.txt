SA Inspection Booking Monitor — Cloud Setup Guide
==================================================
Runs automatically in the cloud every 10 minutes, 7am–5pm,
even when your laptop is off. Emails you when a slot appears.


WHAT YOU NEED
──────────────
  • A Gmail account (you already have one)
  • A free GitHub account (takes 2 minutes to create)
  • These files


STEP 1 — Create a free GitHub account
───────────────────────────────────────
  1. Go to https://github.com
  2. Click "Sign up"
  3. Enter your email, create a password, choose a username
  4. Verify your email address
  5. When asked about preferences, just click "Skip" or "Continue"


STEP 2 — Create a new repository (a folder on GitHub)
───────────────────────────────────────────────────────
  1. Once logged in, click the "+" button (top right of GitHub)
  2. Click "New repository"
  3. Name it:   sa-inspection-monitor
  4. Set it to PRIVATE (important — keeps your details safe)
  5. Leave everything else as-is
  6. Click "Create repository"


STEP 3 — Upload the files
───────────────────────────
  You need to upload these files in the right places.

  First, upload the two files in the main folder:
    • monitor.py
    • results.csv  ← you need to create this (see below)

  How to upload:
    1. On your new repository page, click "uploading an existing file"
    2. Drag "monitor.py" into the upload area
    3. Click "Commit changes"

  Create a blank results.csv:
    1. Click "Add file" → "Create new file"
    2. Name it:  results.csv
    3. In the content area paste exactly this one line:
       Date,Time,Result,Slots Found
    4. Click "Commit new file"

  Now upload the workflow file (this is what schedules the monitor):
    1. Click "Add file" → "Create new file"
    2. In the filename box type:  .github/workflows/monitor.yml
       (GitHub will automatically create the folders)
    3. Open the file "monitor.yml" from your downloads in TextEdit
    4. Select all the text (Cmd+A), copy it (Cmd+C)
    5. Paste it into the GitHub text area (Cmd+V)
    6. Click "Commit new file"


STEP 4 — Add your personal details as Secrets
───────────────────────────────────────────────
  Your details are stored as encrypted "Secrets" — GitHub staff
  cannot see them, and they never appear in any logs.

  1. In your repository, click "Settings" (top menu)
  2. In the left sidebar, click "Secrets and variables" → "Actions"
  3. Click "New repository secret" for each of these:

     Name: LICENCE_NUMBER
     Value: your SA driver's licence number

     Name: DATE_OF_BIRTH
     Value: your date of birth  (format: DD/MM/YYYY e.g. 25/03/1985)

     Name: LAST_NAME
     Value: your last name / surname

     Name: GMAIL_ADDRESS
     Value: your full Gmail address  (e.g. yourname@gmail.com)

     Name: GMAIL_APP_PASSWORD
     Value: your Gmail App Password  (see Step 5 below)

     Name: NOTIFY_EMAIL
     Value: the email address to send alerts to
            (can be the same Gmail, or any other email)

  Add each one by clicking "New repository secret", entering the
  Name and Value, then clicking "Add secret".


STEP 5 — Create a Gmail App Password
──────────────────────────────────────
  Gmail requires a special "App Password" for scripts to send email.
  This is separate from your normal Gmail password.

  1. Go to your Google Account: https://myaccount.google.com
  2. Click "Security" in the left sidebar
  3. Under "How you sign in to Google", make sure
     "2-Step Verification" is turned ON
     (if not, turn it on first — Google requires this)
  4. Go back to Security, scroll down and click "App passwords"
     (or search "App passwords" in the Google Account search bar)
  5. Under "App name" type:  SA Monitor
  6. Click "Create"
  7. Google shows you a 16-character password like: abcd efgh ijkl mnop
  8. Copy it (without spaces) and use it as your GMAIL_APP_PASSWORD secret


STEP 6 — Turn on GitHub Actions
─────────────────────────────────
  1. In your repository, click the "Actions" tab
  2. You may see a message asking you to enable workflows
     If so, click "I understand my workflows, go ahead and enable them"
  3. In the left sidebar you should see "SA Inspection Booking Monitor"
  4. Click on it, then click "Run workflow" → "Run workflow"
     to do a test run right now and make sure everything works


CHECKING IT WORKED
───────────────────
  After running (either manually or at 7am the next day):

  1. Click the "Actions" tab in your repository
  2. You should see a run listed — click on it
  3. Click "check-booking" to see the full log
  4. Look for lines like:
       [INFO] No slots — check complete.    ← working correctly, no slots yet
       [ALERT] *** SLOTS AVAILABLE ***      ← a slot was found!

  The results.csv file in your repository updates with every check.
  To download it: click the file → click the download button.


WHAT HAPPENS WHEN A SLOT IS FOUND
───────────────────────────────────
  You'll receive an email at the address you set for NOTIFY_EMAIL.
  Subject: "SA Inspection Slot Available — X slot(s) found!"
  The email includes the available times and a direct link to book.

  Act fast — slots get taken quickly!


STOPPING THE MONITOR
─────────────────────
  To pause it temporarily:
    Actions tab → "SA Inspection Booking Monitor" → "..." → Disable workflow

  To stop it permanently:
    Delete the repository, or disable the workflow as above.


SOMETHING WRONG?
─────────────────
  In the Actions tab, click on a failed run (shown with a red X).
  Click "check-booking" to see the error message.
  Screenshot that and send it for help.

  Common issues:
  • Red X with "Missing required environment variable"
    → A Secret wasn't added correctly. Check Step 4.
  • Email not arriving
    → Check your App Password (Step 5). Make sure 2-Step
      Verification is enabled on your Google account.
  • "No slots" every check
    → This is normal! It means it's working but nothing is
      available yet. You'll get an email the moment one appears.
