#!/usr/bin/env python3
"""
SA Vehicle Inspection Booking Monitor
Cloud version with Selenium + screenshots.
Takes a screenshot at every step and emails them to you.
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

# ── Selenium ──────────────────────────────────────────────────────────────────
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

BOOKING_URL = "https://www.ecom.transport.sa.gov.au/et/makeAVehicleInspectionBooking.do"
CSV_FILE    = Path(__file__).parent / "results.csv"
SHOT_DIR    = Path(__file__).parent / "screenshots"

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

def take_screenshot(driver, name: str) -> Path:
    SHOT_DIR.mkdir(exist_ok=True)
    path = SHOT_DIR / f"{name}.png"
    try:
        driver.save_screenshot(str(path))
        log(f"Screenshot saved: {name}.png")
    except Exception as e:
        log(f"Screenshot failed ({name}): {e}", "WARN")
    return path


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(subject: str, body: str, gmail_address: str,
               app_password: str, notify_email: str,
               images: list = None):
    """Send an email with optional inline screenshot attachments."""
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = gmail_address
    msg["To"]      = notify_email

    # Build HTML body with embedded images
    img_tags = ""
    if images:
        for i, path in enumerate(images):
            if Path(path).exists():
                img_tags += f'<h3>{Path(path).stem.replace("_", " ").title()}</h3>'
                img_tags += f'<img src="cid:screenshot{i}" style="max-width:100%;border:1px solid #ccc;margin-bottom:20px;"><br>'

    html = f"""
    <html><body>
    <p>{body.replace(chr(10), '<br>')}</p>
    {img_tags}
    </body></html>
    """
    msg.attach(MIMEText(html, "html"))

    # Attach images
    if images:
        for i, path in enumerate(images):
            p = Path(path)
            if p.exists():
                with open(p, "rb") as f:
                    img = MIMEImage(f.read())
                    img.add_header("Content-ID", f"<screenshot{i}>")
                    img.add_header("Content-Disposition", "inline",
                                   filename=p.name)
                    msg.attach(img)

    try:
        log(f"Sending email: {subject}")
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
    opts.add_argument("--disable-extensions")
    opts.add_argument("--log-level=3")
    # Use the system Chrome installed by the workflow
    opts.binary_location = "/usr/bin/google-chrome"
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver


def find_input(driver, *names):
    for name in names:
        for attr in ["name", "id"]:
            try:
                return driver.find_element(By.XPATH, f"//input[@{attr}='{name}']")
            except NoSuchElementException:
                pass
    raise NoSuchElementException(f"Input not found: {names}")


def click_next(driver, wait):
    try:
        btn = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='submit'] | "
            "//input[@type='button' and ("
            "  contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next') or "
            "  contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue') or "
            "  contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')"
            ")] | "
            "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next') or "
            "         contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]"
        )))
        btn.click()
        time.sleep(2)
        return True
    except TimeoutException:
        return False


# ── Core scraper ──────────────────────────────────────────────────────────────

def check_for_slots(licence: str, dob: str, last_name: str,
                    gmail_addr: str, gmail_pass: str, notify_addr: str) -> list:

    driver     = make_driver()
    wait       = WebDriverWait(driver, 20)
    slots      = []
    screenshots = []

    try:
        # ── Page 1: Load ─────────────────────────────────────────────────────
        log("Loading booking page...")
        driver.get(BOOKING_URL)
        time.sleep(3)
        p = take_screenshot(driver, "01_page1_loaded")
        screenshots.append(p)

        # Log all input field names so we can see exactly what the form has
        inputs = driver.find_elements(By.TAG_NAME, "input")
        log(f"Input fields on page 1: {[(i.get_attribute('name'), i.get_attribute('type')) for i in inputs]}")

        # Fill personal details
        filled_any = False
        for field_names, value, label in [
            (["licenceNumber","licence_number","licNo","driverLicence",
              "driverLicenceNumber","licenceNo","licence","dlNumber",
              "licenceNo","driverlicence"], licence, "licence"),
            (["dateOfBirth","dob","birthDate","date_of_birth",
              "birthdate","DOB","dateofbirth"], dob, "DOB"),
            (["lastName","last_name","surname","familyName",
              "family_name","Surname","LastName","LASTNAME"], last_name, "last name"),
        ]:
            try:
                f = find_input(driver, *field_names)
                f.clear()
                f.send_keys(value)
                log(f"Filled: {label} (field: {f.get_attribute('name')})")
                filled_any = True
            except NoSuchElementException:
                log(f"Field not found for: {label}", "WARN")

        p = take_screenshot(driver, "02_page1_filled")
        screenshots.append(p)

        if not click_next(driver, wait):
            log("Next button not found on page 1", "WARN")
            p = take_screenshot(driver, "03_page1_no_next_button")
            screenshots.append(p)
            # Log page source snippet to find correct field names
            src = driver.page_source
            log(f"Page 1 source snippet: {src[:3000]}", "DEBUG")
            return []

        log("Page 1 submitted.")
        time.sleep(2)
        p = take_screenshot(driver, "03_page2_loaded")
        screenshots.append(p)

        # ── Page 2: Preferred date — just submit ─────────────────────────────
        inputs2 = driver.find_elements(By.TAG_NAME, "input")
        log(f"Fields on page 2: {[(i.get_attribute('name'), i.get_attribute('type')) for i in inputs2]}")

        click_next(driver, wait)
        log("Page 2 submitted.")
        time.sleep(3)

        p = take_screenshot(driver, "04_page3_times")
        screenshots.append(p)

        # ── Page 3: Read times dropdown ───────────────────────────────────────
        selects = driver.find_elements(By.TAG_NAME, "select")
        log(f"Dropdowns found on page 3: {len(selects)}")

        for sel_el in selects:
            sel_name = sel_el.get_attribute("name")
            log(f"Dropdown name: '{sel_name}'")
            try:
                select = Select(sel_el)
                for opt in select.options:
                    t = opt.text.strip()
                    v = opt.get_attribute("value") or ""
                    log(f"  Option: text='{t}' value='{v}'")
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
            p = take_screenshot(driver, "error")
            screenshots.append(p)
        except Exception:
            pass
    finally:
        driver.quit()

    # Always email the screenshots so you can see what happened
    if slots:
        subject = f"SA Inspection Slot Available — {len(slots)} slot(s) found!"
        body    = f"Great news! Available slots:\n\n" + "\n".join(f"• {s}" for s in slots)
        body   += f"\n\nBook now: {BOOKING_URL}\n\nScreenshots from this check are attached below."
    else:
        subject = "SA Inspection Monitor — check complete (no slots yet)"
        body    = "The monitor ran successfully. No slots available yet.\n\nScreenshots from each step are attached so you can see what it's doing."

    send_email(subject, body, gmail_addr, gmail_pass, notify_addr, screenshots)

    return slots


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    log("=" * 55)
    log("SA Inspection Monitor — starting check")
    log("=" * 55)

    if not SELENIUM_OK:
        log("Selenium not installed.", "ERROR")
        sys.exit(1)

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
