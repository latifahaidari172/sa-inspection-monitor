#!/usr/bin/env python3
"""
SA Vehicle Inspection Booking Monitor
Cloud version — uses requests (no browser needed).
Runs via GitHub Actions. Sends Gmail alert when slots found.
Appends every check to results.csv.
"""

import os
import csv
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────────────────────────────────────

BOOKING_URL = "https://www.ecom.transport.sa.gov.au/et/makeAVehicleInspectionBooking.do"
CSV_FILE    = Path(__file__).parent / "results.csv"

PLACEHOLDER_OPTIONS = {
    "", "select", "-- select --", "select a time", "please select",
    "select time", "--", "select...", "choose...", "- select -",
    "no times available", "none available"
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def get_env(key: str, required: bool = True) -> str:
    val = os.environ.get(key, "").strip()
    if required and not val:
        log(f"Missing required environment variable: {key}", "ERROR")
        log("Make sure all Secrets are set in your GitHub repository.", "ERROR")
        sys.exit(1)
    return val


# ── CSV logging ───────────────────────────────────────────────────────────────

def write_csv_row(check_time: datetime, slots: list):
    file_exists = CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Date", "Time", "Result", "Slots Found"])
        writer.writerow([
            check_time.strftime("%d/%m/%Y"),
            check_time.strftime("%H:%M"),
            "SLOTS AVAILABLE" if slots else "No slots",
            " | ".join(slots) if slots else ""
        ])
    log(f"CSV updated: {'SLOTS AVAILABLE — ' + str(slots) if slots else 'No slots'}")


# ── Email alert ───────────────────────────────────────────────────────────────

def send_email_alert(slots: list, gmail_address: str, app_password: str, notify_email: str):
    slot_list = "\n".join(f"  • {s}" for s in slots)
    body = f"""An earlier SA vehicle inspection booking slot has been found!

Available times:
{slot_list}

Act quickly — these slots go fast.

Book now: {BOOKING_URL}

---
This alert was sent by your SA Inspection Booking Monitor.
"""
    msg              = MIMEText(body)
    msg["Subject"]   = f"🚗 SA Inspection Slot Available — {len(slots)} slot(s) found!"
    msg["From"]      = gmail_address
    msg["To"]        = notify_email

    try:
        log(f"Sending email alert to {notify_email}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, notify_email, msg.as_string())
        log("Email sent successfully.")
    except smtplib.SMTPAuthenticationError:
        log("Email failed: Gmail authentication error.", "ERROR")
        log("Make sure you're using an App Password, not your regular Gmail password.", "ERROR")
        log("See README.txt for how to create an App Password.", "ERROR")
    except Exception as e:
        log(f"Email failed: {e}", "ERROR")


# ── HTTP session with retries ─────────────────────────────────────────────────

def make_session() -> requests.Session:
    session = requests.Session()
    retry   = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    })
    return session


# ── Scraper ───────────────────────────────────────────────────────────────────

def check_for_slots(licence: str, dob: str, last_name: str) -> list:
    """
    POST personal details to the SA booking form and check the
    resulting page for available time slots in any <select> dropdown.
    """
    session = make_session()
    slots   = []

    try:
        # Step 1 — load the booking page to get any hidden fields / session cookies
        log("Loading booking page...")
        resp = session.get(BOOKING_URL, timeout=20)
        resp.raise_for_status()

        # Extract any hidden form fields (session tokens, etc.)
        from html.parser import HTMLParser

        class HiddenFieldParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.hidden = {}
                self.in_form = False
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "form":
                    self.in_form = True
                if tag == "input" and attrs.get("type", "").lower() == "hidden":
                    name = attrs.get("name", "")
                    val  = attrs.get("value", "")
                    if name:
                        self.hidden[name] = val

        parser = HiddenFieldParser()
        parser.feed(resp.text)
        hidden = parser.hidden
        log(f"Found {len(hidden)} hidden field(s) on page 1.")

        # Step 2 — POST personal details
        # Common field names used by SA Transport booking systems.
        # The script tries the most likely names; if the form uses different
        # names the debug output will show what was returned.
        form_data = {
            **hidden,
            # Try multiple common field name variants:
            "licenceNumber":       licence,
            "licence_number":      licence,
            "licNo":               licence,
            "driverLicenceNumber": licence,
            "dateOfBirth":         dob,
            "dob":                 dob,
            "birthDate":           dob,
            "lastName":            last_name,
            "surname":             last_name,
            "familyName":          last_name,
        }

        log("Submitting personal details...")
        resp2 = session.post(BOOKING_URL, data=form_data, timeout=20)
        resp2.raise_for_status()

        # Step 3 — Check for a times dropdown in the resulting page
        # We may need to go through page 2 (preferred date) first
        page_text = resp2.text

        # If page 2 is a "preferred date" page, submit it immediately
        if "preferred" in page_text.lower() or "date" in page_text.lower():
            parser2 = HiddenFieldParser()
            parser2.feed(page_text)
            hidden2 = parser2.hidden

            # Extract the action URL if there's a form with a different action
            import re
            action_match = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', page_text, re.I)
            action_url   = action_match.group(1) if action_match else BOOKING_URL
            if not action_url.startswith("http"):
                action_url = "https://www.ecom.transport.sa.gov.au" + action_url

            log("Submitting preferred date page...")
            resp3 = session.post(action_url, data=hidden2, timeout=20)
            resp3.raise_for_status()
            page_text = resp3.text

        # Step 4 — Parse time slots from the dropdown(s)
        import re

        # Find all <select> blocks
        select_blocks = re.findall(r'<select[^>]*>(.*?)</select>', page_text, re.I | re.S)
        log(f"Found {len(select_blocks)} dropdown(s) on times page.")

        for block in select_blocks:
            # Extract <option value="...">text</option>
            options = re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>', block, re.I | re.S)
            for value, text in options:
                clean_text  = re.sub(r'<[^>]+>', '', text).strip()   # strip any inner HTML
                clean_value = value.strip()
                if (clean_text.lower() not in PLACEHOLDER_OPTIONS
                        and clean_value not in ("", "0", "-1", "null", "none", "NULL")):
                    slots.append(clean_text)

        if slots:
            log(f"Slots found: {slots}")
        else:
            log("No slots in any dropdown — nothing available yet.")

        # Debug: if we got zero select blocks, log a snippet to help diagnose
        if not select_blocks:
            snippet = page_text[:2000].replace("\n", " ")
            log(f"Page snippet (first 2000 chars): {snippet}", "DEBUG")

    except requests.exceptions.RequestException as e:
        log(f"Network error: {e}", "ERROR")
    except Exception as e:
        log(f"Unexpected error: {e}", "ERROR")
        import traceback
        log(traceback.format_exc(), "DEBUG")

    return slots


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    log("=" * 55)
    log("SA Inspection Monitor — cloud check starting")
    log("=" * 55)

    # Load credentials from environment (set as GitHub Secrets)
    licence     = get_env("LICENCE_NUMBER")
    dob         = get_env("DATE_OF_BIRTH")
    last_name   = get_env("LAST_NAME")
    gmail_addr  = get_env("GMAIL_ADDRESS")
    gmail_pass  = get_env("GMAIL_APP_PASSWORD")
    notify_addr = get_env("NOTIFY_EMAIL")

    now   = datetime.now()
    slots = check_for_slots(licence, dob, last_name)

    write_csv_row(now, slots)

    if slots:
        log(f"*** SLOTS AVAILABLE — sending alert! ***", "ALERT")
        send_email_alert(slots, gmail_addr, gmail_pass, notify_addr)
    else:
        log("No slots — check complete.")

    log("Done.")


if __name__ == "__main__":
    run()
