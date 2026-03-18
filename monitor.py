#!/usr/bin/env python3
"""
SA Vehicle Inspection Booking Monitor — Render.com version
- Uses requests (no browser needed, works on free tier)
- Runs every 30 seconds, 24/7
- Checks for slots before 22/04/2026
- Auto-books the earliest available slot
- Emails confirmation with details
- Logs every check to results.csv
"""

import csv
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────────────────────────────────────

HOME_URL    = "https://www.ecom.transport.sa.gov.au/et/welcome.jsp"
RESCHEDULE_URL = "https://www.ecom.transport.sa.gov.au/et/rescheduleAVehicleInspectionBooking.do"
BASE_URL    = "https://www.ecom.transport.sa.gov.au"
CSV_FILE    = Path(__file__).parent / "results.csv"

CUTOFF_DATE = datetime(2026, 4, 22)
CHECK_INTERVAL_SECONDS = 30

PLACEHOLDER_OPTIONS = {
    "", "select", "-- select --", "select a time", "please select",
    "select time", "--", "select...", "choose...", "- select -",
    "no times available", "none available"
}

# ── Environment variables (set in Render dashboard) ──────────────────────────

def get_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return val

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

# ── DOB formatter ─────────────────────────────────────────────────────────────

def format_dob(dob: str) -> str:
    """Strip non-digits to get DDMMYYYY."""
    return "".join(c for c in dob if c.isdigit())

# ── CSV logging ───────────────────────────────────────────────────────────────

def write_csv_row(check_time: datetime, result: str, detail: str = ""):
    file_exists = CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Date", "Time", "Result", "Detail"])
        writer.writerow([
            check_time.strftime("%d/%m/%Y"),
            check_time.strftime("%H:%M:%S"),
            result,
            detail
        ])

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(subject: str, body: str, gmail_address: str,
               app_password: str, notify_email: str):
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = gmail_address
    msg["To"]      = notify_email
    msg.attach(MIMEText(body, "plain"))
    try:
        log(f"Sending email: {subject}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, notify_email, msg.as_string())
        log("Email sent.")
    except Exception as e:
        log(f"Email failed: {e}", "ERROR")

# ── HTTP session ──────────────────────────────────────────────────────────────

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
        "Connection": "keep-alive",
    })
    return session

# ── HTML helpers ──────────────────────────────────────────────────────────────

def extract_hidden_fields(html: str) -> dict:
    """Extract all hidden input fields from a page."""
    fields = {}
    for m in re.finditer(
        r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.I
    ):
        tag = m.group(0)
        name_m  = re.search(r'name=["\']([^"\']+)["\']', tag, re.I)
        value_m = re.search(r'value=["\']([^"\']*)["\']', tag, re.I)
        if name_m:
            fields[name_m.group(1)] = value_m.group(1) if value_m else ""
    return fields


def extract_form_action(html: str, base: str = BASE_URL) -> str:
    """Extract the form action URL."""
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.I)
    if not m:
        return RESCHEDULE_URL
    action = m.group(1)
    if action.startswith("http"):
        return action
    return base + ("" if action.startswith("/") else "/") + action


def extract_select_options(html: str) -> list:
    """
    Extract all <select> options from a page.
    Returns list of (name, value, text) tuples.
    """
    options = []
    for sel_m in re.finditer(r'<select[^>]*name=["\']([^"\']+)["\'][^>]*>(.*?)</select>',
                              html, re.I | re.S):
        sel_name = sel_m.group(1)
        for opt_m in re.finditer(
            r'<option[^>]+value=["\']([^"\']*)["\'][^>]*>(.*?)</option>',
            sel_m.group(2), re.I | re.S
        ):
            val  = opt_m.group(1).strip()
            text = re.sub(r'<[^>]+>', '', opt_m.group(2)).strip()
            options.append((sel_name, val, text))
    return options


def parse_slot_date(text: str) -> datetime | None:
    """Parse a date from a slot option string."""
    # DD/MM/YYYY
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    # DD-MM-YYYY
    m = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    # YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None

# ── Core checker ──────────────────────────────────────────────────────────────

def check_and_book(licence: str, dob: str, last_name: str,
                   gmail_addr: str, gmail_pass: str, notify_addr: str) -> str:
    """
    Run one full check cycle.
    Returns: "booked:<slot>", "no_slots", "outside_cutoff", or "error:<msg>"
    """
    session = make_session()

    try:
        from dateutil.relativedelta import relativedelta

        # ── Step 1: Load homepage to get session cookie ───────────────────────
        resp = session.get(HOME_URL, timeout=20)
        resp.raise_for_status()

        # ── Step 2: Load reschedule page ──────────────────────────────────────
        resp = session.get(RESCHEDULE_URL, timeout=20,
                           headers={"Referer": HOME_URL})
        resp.raise_for_status()
        hidden1 = extract_hidden_fields(resp.text)
        action1 = extract_form_action(resp.text)

        # ── Step 3: Submit personal details ──────────────────────────────────
        form1 = {
            **hidden1,
            "clientNumber":        licence,
            "clientSurnameOrgName": last_name,
            "clientDOB":           dob,
        }
        resp2 = session.post(action1, data=form1,
                             headers={"Referer": RESCHEDULE_URL}, timeout=20)
        resp2.raise_for_status()

        # ── Step 4: Submit preferred date (3 months from today) ───────────────
        preferred = (datetime.now() + relativedelta(months=3)).strftime("%d%m%Y")
        hidden2   = extract_hidden_fields(resp2.text)
        action2   = extract_form_action(resp2.text)

        # Find the preferred date field name
        date_field_name = "preferredDate"  # fallback
        for m in re.finditer(
            r'<input[^>]+name=["\']([^"\']+)["\'][^>]*>', resp2.text, re.I
        ):
            tag = m.group(0)
            n   = re.search(r'name=["\']([^"\']+)["\']', tag, re.I).group(1)
            if any(x in n.lower() for x in ["preferred", "date", "inspection"]):
                if "hidden" not in tag.lower():
                    date_field_name = n
                    break

        form2 = {
            **hidden2,
            date_field_name: preferred,
        }
        resp3 = session.post(action2, data=form2,
                             headers={"Referer": resp2.url}, timeout=20)
        resp3.raise_for_status()

        # ── Step 5: Parse times dropdown ─────────────────────────────────────
        options = extract_select_options(resp3.text)
        real_options = [
            (sel_name, val, text)
            for (sel_name, val, text) in options
            if text.lower() not in PLACEHOLDER_OPTIONS
            and val not in ("", "0", "-1", "null", "none", "NULL")
        ]

        if not real_options:
            log("No slots available.")
            return "no_slots"

        log(f"Slots found: {[t for _, _, t in real_options]}")

        # ── Step 6: Filter by cutoff date ────────────────────────────────────
        eligible = []
        for sel_name, val, text in real_options:
            dt = parse_slot_date(text)
            if dt and dt < CUTOFF_DATE:
                eligible.append((dt, sel_name, val, text))

        if not eligible:
            log(f"Slots exist but none before {CUTOFF_DATE.strftime('%d/%m/%Y')}.")
            return "outside_cutoff"

        # ── Step 7: Pick earliest and book it ─────────────────────────────────
        eligible.sort(key=lambda x: x[0])
        earliest_dt, sel_name, earliest_val, earliest_text = eligible[0]
        log(f"Booking earliest eligible slot: '{earliest_text}'")

        hidden3 = extract_hidden_fields(resp3.text)
        action3 = extract_form_action(resp3.text)

        form3 = {
            **hidden3,
            sel_name: earliest_val,
        }
        resp4 = session.post(action3, data=form3,
                             headers={"Referer": resp3.url}, timeout=20)
        resp4.raise_for_status()

        log(f"Booking submitted. Response length: {len(resp4.text)} chars")

        # Check confirmation page for success indicators
        confirmed = any(word in resp4.text.lower() for word in
                        ["confirm", "booked", "booking reference",
                         "success", "thank you", "scheduled"])

        if confirmed:
            log(f"Booking CONFIRMED: {earliest_text}")
            return f"booked:{earliest_text}"
        else:
            log("Booking submitted but confirmation unclear — check manually.", "WARN")
            return f"booked_unconfirmed:{earliest_text}"

    except requests.exceptions.RequestException as e:
        return f"error:Network error — {e}"
    except Exception as e:
        import traceback
        log(traceback.format_exc(), "DEBUG")
        return f"error:{e}"

# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    log("=" * 55)
    log("SA Inspection Monitor — Render.com version")
    log(f"Checking every {CHECK_INTERVAL_SECONDS} seconds, 24/7")
    log(f"Auto-booking slots before {CUTOFF_DATE.strftime('%d/%m/%Y')}")
    log("=" * 55)

    licence     = get_env("LICENCE_NUMBER")
    dob_raw     = get_env("DATE_OF_BIRTH")
    last_name   = get_env("LAST_NAME")
    gmail_addr  = get_env("GMAIL_ADDRESS")
    gmail_pass  = get_env("GMAIL_APP_PASSWORD")
    notify_addr = get_env("NOTIFY_EMAIL")

    dob = format_dob(dob_raw)

    check_count  = 0
    last_alerted = None  # avoid repeat emails for same slot

    while True:
        check_count += 1
        now = datetime.now()
        log(f"── Check #{check_count} at {now.strftime('%H:%M:%S')} ──")

        result = check_and_book(licence, dob, last_name,
                                gmail_addr, gmail_pass, notify_addr)

        # ── Log to CSV ────────────────────────────────────────────────────────
        if result == "no_slots":
            write_csv_row(now, "No slots", "")

        elif result == "outside_cutoff":
            write_csv_row(now, "Slots exist — outside target date", "")

        elif result.startswith("booked:"):
            slot = result.replace("booked:", "")
            write_csv_row(now, "BOOKED", slot)
            if slot != last_alerted:
                send_email(
                    subject=f"✅ SA Inspection BOOKED — {slot}",
                    body=(
                        f"Your vehicle inspection has been automatically booked!\n\n"
                        f"Booked slot: {slot}\n\n"
                        f"Please log in and verify the booking is confirmed:\n"
                        f"{HOME_URL}\n\n"
                        f"If anything looks wrong, contact SA Transport immediately."
                    ),
                    gmail_address=gmail_addr,
                    app_password=gmail_pass,
                    notify_email=notify_addr
                )
                last_alerted = slot
                log("Booking email sent. Monitor will keep running.")

        elif result.startswith("booked_unconfirmed:"):
            slot = result.replace("booked_unconfirmed:", "")
            write_csv_row(now, "BOOKED (unconfirmed)", slot)
            if slot != last_alerted:
                send_email(
                    subject=f"⚠️ SA Inspection booking submitted — please verify",
                    body=(
                        f"The monitor submitted a booking for:\n\n"
                        f"Slot: {slot}\n\n"
                        f"However it could not confirm 100% that it went through.\n"
                        f"Please log in and check manually:\n"
                        f"{HOME_URL}"
                    ),
                    gmail_address=gmail_addr,
                    app_password=gmail_pass,
                    notify_email=notify_addr
                )
                last_alerted = slot

        elif result.startswith("error:"):
            msg = result.replace("error:", "")
            write_csv_row(now, "Error", msg)
            log(f"Error: {msg}", "ERROR")

        log(f"Sleeping {CHECK_INTERVAL_SECONDS}s...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
