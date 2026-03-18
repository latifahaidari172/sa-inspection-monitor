#!/usr/bin/env python3
"""
SA Vehicle Inspection Booking Monitor
1. Opens SA Transport homepage
2. Clicks "Reschedule a Vehicle Inspection Booking"
3. Fills clientNumber, clientSurnameOrgName, clientDOB
4. Clicks the Next button
5. Checks the times dropdown
6. Emails screenshots every run
"""

import os
import csv
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ─────────────────────────────────────────────────────────────────────────────

HOME_URL = "https://www.ecom.transport.sa.gov.au/et/welcome.jsp"
CSV_FILE = Path(__file__).parent / "results.csv"
SHOT_DIR = Path(__file__).parent / "screenshots"

PLACEHOLDER_OPTIONS = {
    "", "select", "-- select --", "select a time", "please select",
    "select time", "--", "select...", "choose...", "- select -",
    "no times available", "none available"
}

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def get_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        log(f"Missing required secret: {key}", "ERROR")
        sys.exit(1)
    return val


def format_dob(dob: str) -> str:
    """Strip non-digits — site expects DDMMYYYY with no separators."""
    return "".join(c for c in dob if c.isdigit())


# ── CSV ───────────────────────────────────────────────────────────────────────

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


# ── Screenshots ───────────────────────────────────────────────────────────────

def screenshot(driver, name: str) -> Path:
    SHOT_DIR.mkdir(exist_ok=True)
    path = SHOT_DIR / f"{name}.png"
    try:
        driver.save_screenshot(str(path))
        log(f"Screenshot: {name}.png")
    except Exception as e:
        log(f"Screenshot failed ({name}): {e}", "WARN")
    return path


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(subject: str, body: str, gmail_address: str,
               app_password: str, notify_email: str, images: list = None):
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = gmail_address
    msg["To"]      = notify_email

    img_tags = ""
    if images:
        for i, path in enumerate(images):
            if Path(path).exists():
                label = Path(path).stem.replace("_", " ").title()
                img_tags += (
                    f'<h3 style="font-family:sans-serif;color:#333">{label}</h3>'
                    f'<img src="cid:shot{i}" style="max-width:100%;border:1px solid #ddd;'
                    f'border-radius:4px;margin-bottom:24px"><br>'
                )

    html = f"""
    <html><body style="font-family:sans-serif;padding:20px;color:#333">
    <p style="font-size:16px">{body.replace(chr(10), '<br>')}</p>
    <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
    <h2 style="color:#555">Screenshots from this check:</h2>
    {img_tags if img_tags else '<p><em>No screenshots captured.</em></p>'}
    </body></html>
    """
    msg.attach(MIMEText(html, "html"))

    if images:
        for i, path in enumerate(images):
            p = Path(path)
            if p.exists():
                with open(p, "rb") as f:
                    img = MIMEImage(f.read())
                    img.add_header("Content-ID", f"<shot{i}>")
                    img.add_header("Content-Disposition", "inline", filename=p.name)
                    msg.attach(img)

    try:
        log(f"Sending email: '{subject}' to {notify_email}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, notify_email, msg.as_string())
        log("Email sent successfully.")
    except smtplib.SMTPAuthenticationError:
        log("Email auth failed — check GMAIL_APP_PASSWORD secret.", "ERROR")
    except Exception as e:
        log(f"Email failed: {e}", "ERROR")


# ── WebDriver ─────────────────────────────────────────────────────────────────

def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--log-level=3")
    opts.binary_location = "/usr/bin/google-chrome"
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver


def fill_field_by_name(driver, field_name: str, value: str):
    """Clear a field by exact name and type the value."""
    try:
        field = driver.find_element(By.NAME, field_name)
        field.click()
        field.clear()
        # Use JS to set value cleanly — avoids any leftover content
        driver.execute_script("arguments[0].value = '';", field)
        field.send_keys(value)
        log(f"Filled '{field_name}' = '{value}'")
        return True
    except NoSuchElementException:
        log(f"Field not found: '{field_name}'", "WARN")
        return False


def click_next_button(driver, wait) -> bool:
    """Click the Next button — tries multiple strategies."""
    strategies = [
        # Exact text "Next"
        "//input[@type='submit' and translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='next']",
        "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='next']",
        # Contains "next"
        "//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
        "//input[@type='button' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
        "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
        # Any submit
        "//input[@type='submit']",
        # Any button
        "//button",
        # Image button (old-school)
        "//input[@type='image']",
    ]

    for xpath in strategies:
        try:
            el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            label = el.get_attribute("value") or el.text.strip() or el.get_attribute("name") or xpath
            log(f"Clicking: '{label}'")
            el.click()
            time.sleep(3)
            return True
        except TimeoutException:
            continue
        except Exception:
            continue

    # Last resort: submit the form via JavaScript
    try:
        forms = driver.find_elements(By.TAG_NAME, "form")
        if forms:
            log("Submitting form via JavaScript as last resort.")
            driver.execute_script("arguments[0].submit();", forms[0])
            time.sleep(3)
            return True
    except Exception as e:
        log(f"JS submit failed: {e}", "WARN")

    # Log everything on the page to help diagnose
    log("Could not find Next button. All elements on page:", "WARN")
    for el in driver.find_elements(By.XPATH, "//input | //button | //a"):
        log(f"  <{el.tag_name}> type='{el.get_attribute('type')}' "
            f"value='{el.get_attribute('value')}' text='{el.text.strip()}' "
            f"name='{el.get_attribute('name')}'", "WARN")
    return False


# ── Core scraper ──────────────────────────────────────────────────────────────

def check_for_slots(licence: str, dob_raw: str, last_name: str,
                    gmail_addr: str, gmail_pass: str, notify_addr: str) -> list:

    dob    = format_dob(dob_raw)
    driver = make_driver()
    wait   = WebDriverWait(driver, 20)
    slots  = []
    shots  = []

    try:
        # ── Step 1: Homepage ──────────────────────────────────────────────────
        log("Loading homepage...")
        driver.get(HOME_URL)
        time.sleep(3)
        shots.append(screenshot(driver, "01_homepage"))

        # ── Step 2: Click reschedule link ─────────────────────────────────────
        try:
            link = driver.find_element(By.XPATH,
                "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reschedule')]"
            )
            log(f"Clicking link: '{link.text.strip()}'")
            link.click()
            time.sleep(3)
        except NoSuchElementException:
            log("Reschedule link not found!", "ERROR")
            shots.append(screenshot(driver, "02_error"))
            raise Exception("Reschedule link not found on homepage")

        log(f"Now on: {driver.current_url}")
        shots.append(screenshot(driver, "02_booking_form"))

        # ── Step 3: Fill fields using confirmed exact field names ─────────────
        # Order matters — fill one at a time with a small pause between each
        fill_field_by_name(driver, "clientNumber",        licence)
        time.sleep(0.5)
        fill_field_by_name(driver, "clientSurnameOrgName", last_name)
        time.sleep(0.5)
        fill_field_by_name(driver, "clientDOB",           dob)
        time.sleep(0.5)

        shots.append(screenshot(driver, "03_form_filled"))

        # ── Step 4: Click Next ────────────────────────────────────────────────
        if not click_next_button(driver, wait):
            shots.append(screenshot(driver, "04_next_not_found"))
        else:
            log(f"Page 1 submitted. Now on: {driver.current_url}")
            shots.append(screenshot(driver, "04_page2"))
            time.sleep(2)

            # ── Step 5: Page 2 — preferred date, click Next again ────────────
            log(f"Page 2 title: {driver.title}")
            click_next_button(driver, wait)
            time.sleep(3)

            shots.append(screenshot(driver, "05_times_page"))
            log(f"Times page — title: {driver.title} | URL: {driver.current_url}")

            # ── Step 6: Read times dropdown ───────────────────────────────────
            selects = driver.find_elements(By.TAG_NAME, "select")
            log(f"Dropdowns found: {len(selects)}")

            for sel_el in selects:
                log(f"Dropdown: name='{sel_el.get_attribute('name')}'")
                try:
                    select = Select(sel_el)
                    for opt in select.options:
                        t = opt.text.strip()
                        v = opt.get_attribute("value") or ""
                        log(f"  Option: '{t}' value='{v}'")
                        if (t.lower() not in PLACEHOLDER_OPTIONS
                                and v not in ("", "0", "-1", "null", "none", "NULL")):
                            slots.append(t)
                except Exception as e:
                    log(f"Error reading dropdown: {e}", "WARN")

            if slots:
                log(f"SLOTS FOUND: {slots}")
            else:
                log("No slots available.")

    except Exception as e:
        log(f"Error: {e}", "ERROR")
        import traceback
        log(traceback.format_exc(), "DEBUG")
        try:
            shots.append(screenshot(driver, "error"))
        except Exception:
            pass
    finally:
        driver.quit()

    # ── Always email screenshots ──────────────────────────────────────────────
    if slots:
        subject = f"SA Inspection Slot Available — {len(slots)} slot(s) found!"
        body    = (
            "Great news! Available inspection slot(s):\n\n"
            + "\n".join(f"• {s}" for s in slots)
            + "\n\nAct fast — book now:\n"
            + HOME_URL + "\n\n"
            + "Screenshots from this check are below."
        )
    else:
        subject = "SA Inspection Monitor — check complete (no slots yet)"
        body    = (
            "The monitor ran successfully. No slots available yet.\n\n"
            "Screenshots from each step are below.\n"
            "You will get an email the moment a slot appears."
        )

    send_email(subject, body, gmail_addr, gmail_pass, notify_addr, shots)
    return slots


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    log("=" * 55)
    log("SA Inspection Monitor — starting check")
    log("=" * 55)

    licence     = get_env("LICENCE_NUMBER")
    dob         = get_env("DATE_OF_BIRTH")
    last_name   = get_env("LAST_NAME")
    gmail_addr  = get_env("GMAIL_ADDRESS")
    gmail_pass  = get_env("GMAIL_APP_PASSWORD")
    notify_addr = get_env("NOTIFY_EMAIL")

    now   = datetime.now()
    slots = check_for_slots(licence, dob, last_name, gmail_addr, gmail_pass, notify_addr)

    write_csv_row(now, slots)
    log("Done.")


if __name__ == "__main__":
    run()
