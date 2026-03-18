#!/usr/bin/env python3
"""
SA Vehicle Inspection Booking Monitor
1. Opens the SA Transport homepage
2. Clicks "Reschedule a Vehicle Inspection Booking"
3. Fills in Licence/Client Number, Surname, Date of Birth
4. Checks the times dropdown for available slots
5. Emails screenshots every run
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

HOME_URL    = "https://www.ecom.transport.sa.gov.au/et/welcome.jsp"
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


# ── Format DOB ────────────────────────────────────────────────────────────────

def format_dob(dob: str) -> str:
    """Strip non-digits to get DDMMYYYY format."""
    digits = "".join(c for c in dob if c.isdigit())
    return digits


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


def fill_field(driver, value: str, *identifiers) -> str | None:
    """
    Try to fill a field by label text first, then by name/id.
    Returns the field name if successful, None if not found.
    """
    # Method 1: find by label text
    for text in identifiers:
        try:
            el = driver.find_element(
                By.XPATH,
                f"//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{text.lower()}')]"
                f"/following::input[1]"
            )
            el.clear()
            el.send_keys(value)
            return el.get_attribute("name") or el.get_attribute("id") or text
        except NoSuchElementException:
            pass

    # Method 2: find by name/id attribute
    for ident in identifiers:
        for attr in ["name", "id"]:
            try:
                el = driver.find_element(By.XPATH, f"//input[@{attr}='{ident}']")
                el.clear()
                el.send_keys(value)
                return ident
            except NoSuchElementException:
                pass

    return None


def click_next(driver, wait) -> bool:
    try:
        btn = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='submit'] | "
            "//input[@type='button' and ("
            "  contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next') or "
            "  contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue') or "
            "  contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit') or "
            "  contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search')"
            ")] | "
            "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next') or "
            "         contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue') or "
            "         contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search')]"
        )))
        log(f"Clicking: '{btn.get_attribute('value') or btn.text}'")
        btn.click()
        time.sleep(3)
        return True
    except TimeoutException:
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
        # ── Step 1: Load homepage ─────────────────────────────────────────────
        log(f"Loading homepage: {HOME_URL}")
        driver.get(HOME_URL)
        time.sleep(3)
        log(f"Title: {driver.title} | URL: {driver.current_url}")
        shots.append(screenshot(driver, "01_homepage"))

        # Log all links on the page so we can see what's available
        all_links = driver.find_elements(By.TAG_NAME, "a")
        log("Links on homepage:")
        for link in all_links:
            log(f"  '{link.text.strip()}' -> {link.get_attribute('href')}")

        # ── Step 2: Click "Reschedule a Vehicle Inspection Booking" ──────────
        clicked = False
        link_texts = [
            "reschedule a vehicle inspection booking",
            "reschedule a vehicle inspection",
            "reschedule",
            "vehicle inspection booking",
            "inspection booking",
        ]
        for text in link_texts:
            try:
                link = driver.find_element(
                    By.XPATH,
                    f"//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{text}')]"
                )
                log(f"Found link: '{link.text.strip()}' — clicking it")
                link.click()
                time.sleep(3)
                clicked = True
                break
            except NoSuchElementException:
                continue

        if not clicked:
            log("Could not find the reschedule link on homepage!", "ERROR")
            shots.append(screenshot(driver, "02_link_not_found"))
        else:
            log(f"Clicked reschedule link. New URL: {driver.current_url}")
            shots.append(screenshot(driver, "02_booking_form"))

            # Log all input fields on the booking form
            all_inputs = driver.find_elements(By.TAG_NAME, "input")
            log("Input fields on booking form:")
            for inp in all_inputs:
                log(f"  name='{inp.get_attribute('name')}' "
                    f"id='{inp.get_attribute('id')}' "
                    f"type='{inp.get_attribute('type')}' "
                    f"placeholder='{inp.get_attribute('placeholder')}'")

            # ── Step 3: Fill Licence/Client Number ───────────────────────────
            result = fill_field(driver, licence,
                "licence", "client number", "licen",
                "licenceNumber", "licence_number", "licNo",
                "clientNumber", "client_number", "licenceClientNumber",
                "licenceNo", "driverLicenceNumber", "clientNo")
            if result:
                log(f"Filled licence into field: '{result}'")
            else:
                log("Could not fill licence field!", "WARN")

            # ── Step 4: Fill Surname ──────────────────────────────────────────
            result = fill_field(driver, last_name,
                "surname", "organisation name", "last name",
                "lastName", "last_name", "familyName",
                "organisationName", "surnameName", "Surname")
            if result:
                log(f"Filled surname into field: '{result}'")
            else:
                log("Could not fill surname field!", "WARN")

            # ── Step 5: Fill Date of Birth ────────────────────────────────────
            result = fill_field(driver, dob,
                "date of birth", "dob", "birth",
                "dateOfBirth", "birthDate", "date_of_birth", "DOB")
            if result:
                log(f"Filled DOB ({dob}) into field: '{result}'")
            else:
                log("Could not fill DOB field!", "WARN")

            shots.append(screenshot(driver, "03_form_filled"))

            # ── Step 6: Submit the form ───────────────────────────────────────
            if not click_next(driver, wait):
                log("Submit button not found!", "WARN")
                shots.append(screenshot(driver, "04_no_submit_button"))
            else:
                log(f"Form submitted. URL: {driver.current_url}")
                shots.append(screenshot(driver, "04_after_submit"))
                time.sleep(2)

                # ── Step 7: Page 2 - preferred date, just submit ──────────────
                log(f"Page 2 title: {driver.title}")
                shots.append(screenshot(driver, "05_page2"))

                if click_next(driver, wait):
                    log(f"Page 2 submitted. URL: {driver.current_url}")
                    time.sleep(3)
                else:
                    log("No button on page 2 — may already be on times page.")

                shots.append(screenshot(driver, "06_times_page"))

                # ── Step 8: Read times dropdown ───────────────────────────────
                log(f"Times page title: {driver.title}")
                selects = driver.find_elements(By.TAG_NAME, "select")
                log(f"Dropdowns found: {len(selects)}")

                for sel_el in selects:
                    sel_name = sel_el.get_attribute("name")
                    log(f"Dropdown: name='{sel_name}'")
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

    # ── Always send email with screenshots ────────────────────────────────────
    if slots:
        subject = f"SA Inspection Slot Available — {len(slots)} slot(s) found!"
        body    = (
            "Great news! Available inspection slot(s):\n\n"
            + "\n".join(f"• {s}" for s in slots)
            + f"\n\nAct fast — book now:\n"
            + "https://www.ecom.transport.sa.gov.au/et/welcome.jsp\n\n"
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
