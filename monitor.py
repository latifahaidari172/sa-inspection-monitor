#!/usr/bin/env python3
"""
SA Vehicle Inspection Booking Monitor
Fast version — uses requests only, no browser needed.
Runs every 5 minutes via GitHub Actions (free, public repo).
Auto-books earliest slot before 22/04/2026.
Emails confirmation when booked.
Logs every check to results.csv.
"""

import csv
import os
import re
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from pathlib import Path

import requests

# ── Timezone: Adelaide (ACST/ACDT) ───────────────────────────────────────────

def adelaide_now() -> datetime:
    """Return current time in Adelaide timezone (ACST=UTC+9:30, ACDT=UTC+10:30)."""
    import time as _time
    # Use fixed ACST offset — Python handles DST via this offset automatically
    # Adelaide observes ACDT (UTC+10:30) in summer, ACST (UTC+9:30) in winter
    # We use the system approach: set TZ or calculate manually
    utc_now = datetime.now(timezone.utc)
    # Adelaide standard offset is UTC+9:30
    # DST applies Oct-Apr (summer): UTC+10:30
    import zoneinfo
    try:
        adelaide_tz = zoneinfo.ZoneInfo("Australia/Adelaide")
        return datetime.now(adelaide_tz).replace(tzinfo=None)
    except Exception:
        # Fallback: ACST UTC+9:30
        return utc_now.replace(tzinfo=None) + timedelta(hours=9, minutes=30)
from dateutil.relativedelta import relativedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────────────────────────────────────

HOME_URL       = "https://www.ecom.transport.sa.gov.au/et/welcome.jsp"
RESCHEDULE_URL = "https://www.ecom.transport.sa.gov.au/et/rescheduleAVehicleInspectionBooking.do"
BASE_URL       = "https://www.ecom.transport.sa.gov.au"
CSV_FILE       = Path(__file__).parent / "results.csv"
CUTOFF_DATE    = datetime(2026, 4, 22)

PLACEHOLDER_OPTIONS = {
    "", "select", "-- select --", "select a time", "please select",
    "select time", "--", "select...", "choose...", "- select -",
    "no times available", "none available"
}

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = adelaide_now().strftime("%d/%m/%Y %I:%M:%S %p")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def get_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        log(f"Missing required secret: {key}", "ERROR")
        sys.exit(1)
    return val


def format_dob(dob: str) -> str:
    return "".join(c for c in dob if c.isdigit())

# ── CSV ───────────────────────────────────────────────────────────────────────

def write_csv_row(check_time: datetime, result: str, detail: str = ""):
    file_exists = CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Date", "Time", "Result", "Detail"])
        writer.writerow([
            check_time.strftime("%d/%m/%Y"),
            check_time.strftime("%I:%M:%S %p"),
            result,
            detail
        ])

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(subject: str, body: str, gmail_address: str,
               app_password: str, notify_email: str):
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"]    = gmail_address
    msg["To"]      = notify_email
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
    fields = {}
    for m in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.I):
        tag     = m.group(0)
        name_m  = re.search(r'name=["\']([^"\']+)["\']', tag, re.I)
        value_m = re.search(r'value=["\']([^"\']*)["\']', tag, re.I)
        if name_m:
            fields[name_m.group(1)] = value_m.group(1) if value_m else ""
    return fields


def extract_form_action(html: str) -> str:
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.I)
    if not m:
        return RESCHEDULE_URL
    action = m.group(1)
    if action.startswith("http"):
        return action
    return BASE_URL + ("" if action.startswith("/") else "/") + action


def extract_select_options(html: str) -> list:
    options = []
    for sel_m in re.finditer(
        r'<select[^>]*name=["\']([^"\']+)["\'][^>]*>(.*?)</select>',
        html, re.I | re.S
    ):
        sel_name = sel_m.group(1)
        for opt_m in re.finditer(
            r'<option[^>]+value=["\']([^"\']*)["\'][^>]*>(.*?)</option>',
            sel_m.group(2), re.I | re.S
        ):
            val  = opt_m.group(1).strip()
            text = re.sub(r'<[^>]+>', '', opt_m.group(2)).strip()
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').strip()
            options.append((sel_name, val, text))
    return options


def parse_slot_date(text: str):
    for pattern, builder in [
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
        (r'(\d{4})-(\d{2})-(\d{2})',      lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    ]:
        match = re.search(pattern, text)
        if match:
            try:
                return builder(match)
            except ValueError:
                pass
    return None

# ── Core checker ──────────────────────────────────────────────────────────────

def check_and_book(licence, dob, last_name, gmail_addr, gmail_pass, notify_addr):
    session = make_session()

    try:
        # Step 1: Homepage for session cookie
        log("Loading homepage...")
        session.get(HOME_URL, timeout=20).raise_for_status()

        # Step 2: Reschedule page
        log("Loading reschedule page...")
        r1 = session.get(RESCHEDULE_URL, timeout=20,
                         headers={"Referer": HOME_URL})
        r1.raise_for_status()

        # Step 3: Submit personal details
        log("Submitting personal details...")
        r2 = session.post(
            extract_form_action(r1.text),
            data={
                **extract_hidden_fields(r1.text),
                "clientNumber":         licence,
                "clientSurnameOrgName": last_name,
                "clientDOB":            dob,
            },
            headers={"Referer": RESCHEDULE_URL}, timeout=20
        )
        r2.raise_for_status()

        # Step 4: Submit preferred date
        preferred = (adelaide_now() + relativedelta(months=3)).strftime("%d%m%Y")
        log(f"Submitting preferred date: {preferred}...")

        date_field = "preferredDate"
        for m in re.finditer(r'<input[^>]+>', r2.text, re.I):
            tag = m.group(0)
            if 'hidden' in tag.lower():
                continue
            nm = re.search(r'name=["\']([^"\']+)["\']', tag, re.I)
            if nm and any(x in nm.group(1).lower()
                          for x in ["preferred", "inspectiondate", "bookingdate"]):
                date_field = nm.group(1)
                break

        r3 = session.post(
            extract_form_action(r2.text),
            data={**extract_hidden_fields(r2.text), date_field: preferred},
            headers={"Referer": r2.url}, timeout=20
        )
        r3.raise_for_status()

        # Step 5: Parse dropdown options
        options = extract_select_options(r3.text)
        real = [
            (n, v, t) for n, v, t in options
            if t.lower() not in PLACEHOLDER_OPTIONS
            and v not in ("", "0", "-1", "null", "none", "NULL")
        ]

        log(f"Slots found: {[t for _, _, t in real] or 'none'}")

        if not real:
            return "no_slots", ""

        # Step 6: Filter by cutoff
        eligible = []
        for n, v, t in real:
            dt = parse_slot_date(t)
            if dt and dt < CUTOFF_DATE:
                eligible.append((dt, n, v, t))

        if not eligible:
            return "outside_cutoff", " | ".join(t for _, _, t in real)

        # Step 7: Book the earliest
        eligible.sort(key=lambda x: x[0])
        dt, sel_name, val, text = eligible[0]
        log(f"Booking: '{text}'")

        r4 = session.post(
            extract_form_action(r3.text),
            data={**extract_hidden_fields(r3.text), sel_name: val},
            headers={"Referer": r3.url}, timeout=20
        )
        r4.raise_for_status()

        confirmed = any(w in r4.text.lower() for w in
                        ["confirm", "booked", "booking reference",
                         "success", "thank you", "scheduled"])

        return ("booked" if confirmed else "booked_unconfirmed"), text

    except requests.exceptions.RequestException as e:
        return "error", f"Network error: {e}"
    except Exception as e:
        import traceback
        log(traceback.format_exc(), "DEBUG")
        return "error", str(e)

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    log("=" * 55)
    log("SA Inspection Monitor — checking now")
    log("=" * 55)

    licence     = get_env("LICENCE_NUMBER")
    dob         = format_dob(get_env("DATE_OF_BIRTH"))
    last_name   = get_env("LAST_NAME")
    gmail_addr  = get_env("GMAIL_ADDRESS")
    gmail_pass  = get_env("GMAIL_APP_PASSWORD")
    notify_addr = get_env("NOTIFY_EMAIL")

    now    = adelaide_now()
    result, detail = check_and_book(
        licence, dob, last_name, gmail_addr, gmail_pass, notify_addr
    )

    if result == "no_slots":
        write_csv_row(now, "No slots", "")
        log("No slots available.")

    elif result == "outside_cutoff":
        write_csv_row(now, "Slots exist — outside target date", detail)
        log("Slots found but none before cutoff date.")

    elif result == "booked":
        write_csv_row(now, "BOOKED", detail)
        send_email(
            f"✅ SA Inspection BOOKED — {detail}",
            f"Your vehicle inspection has been automatically booked!\n\n"
            f"Booked slot: {detail}\n\n"
            f"Please log in and verify:\n{HOME_URL}\n\n"
            f"If anything looks wrong, contact SA Transport immediately.",
            gmail_addr, gmail_pass, notify_addr
        )

    elif result == "booked_unconfirmed":
        write_csv_row(now, "BOOKED (verify manually)", detail)
        send_email(
            f"⚠️ SA Inspection booking submitted — please verify",
            f"The monitor submitted a booking for:\n\n"
            f"Slot: {detail}\n\n"
            f"Could not confirm 100% — please check manually:\n{HOME_URL}",
            gmail_addr, gmail_pass, notify_addr
        )

    elif result == "error":
        write_csv_row(now, "Error", detail)
        log(f"Error: {detail}", "ERROR")

    log("Done.")


if __name__ == "__main__":
    run()

# ── Patch run() to include daily summary ──────────────────────────────────────
_original_run = run

def run():
    import os as _os

    licence        = get_env("LICENCE_NUMBER")
    dob            = format_dob(get_env("DATE_OF_BIRTH"))
    last_name      = get_env("LAST_NAME")
    gmail_addr     = get_env("GMAIL_ADDRESS")
    gmail_pass     = get_env("GMAIL_APP_PASSWORD")
    notify_addr    = get_env("NOTIFY_EMAIL")
    daily_summary  = _os.environ.get("DAILY_SUMMARY", "false").lower() == "true"

    _original_run()

    if daily_summary:
        log("Sending daily 5pm summary email...")
        now       = adelaide_now()
        today_str = now.strftime("%d/%m/%Y")
        today_slots  = []
        today_checks = 0

        if CSV_FILE.exists():
            with open(CSV_FILE, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Date") == today_str:
                        today_checks += 1
                        if row.get("Result") not in ("No slots", "Error", ""):
                            today_slots.append(
                                f"  {row['Time']} — {row['Result']}: {row['Detail']}"
                            )

        slots_section = (
            "Slots seen today:\n\n" + "\n".join(today_slots)
            if today_slots
            else "No slots were seen today — the dropdown was empty all day."
        )

        body = (
            f"Daily summary for {today_str}\n"
            f"{'=' * 40}\n\n"
            f"Total checks run today: {today_checks}\n\n"
            f"{slots_section}\n\n"
            f"The monitor checks every 5 minutes and will automatically\n"
            f"book the first slot before 22/04/2026.\n\n"
            f"View full history: open results.csv in your GitHub repository."
        )

        send_email(
            f"📋 SA Inspection Daily Summary — {today_str}",
            body,
            gmail_addr, gmail_pass, notify_addr
        )
        log("Daily summary sent.")
