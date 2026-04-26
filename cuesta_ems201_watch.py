import asyncio
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from playwright.async_api import async_playwright

STATE_FILE = Path("ems201_seen.txt")
CLASS_FINDER_URL = "https://ssb2.cuesta.edu/StudentRegistrationSsb/ssb/term/termSelection?mode=search"


def already_seen() -> bool:
    return STATE_FILE.exists() and STATE_FILE.read_text().strip() == "seen"


def mark_seen():
    STATE_FILE.write_text("seen")


def send_email_alert(subject: str, body: str):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    alert_to = os.getenv("ALERT_TO")
    alert_from = os.getenv("ALERT_FROM", smtp_user)

    if not all([smtp_user, smtp_pass, alert_to, alert_from]):
        print("Email settings are missing. Skipping email.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = alert_from
    msg["To"] = alert_to
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    print("Email alert sent.")


async def debug_dump(page, label: str):
    print(f"\n--- DEBUG: {label} ---")
    print("Title:", await page.title())
    print("URL:", page.url)
    body_text = await page.locator("body").inner_text()
    print(body_text[:2000])
    print("--- END DEBUG ---\n")


async def select_term(page, target_term="Fall 2026") -> bool:
    await page.wait_for_timeout(2000)

    openers = [
        page.get_by_text("Select a term...", exact=False),
        page.get_by_role("combobox"),
        page.locator('[role="combobox"]'),
    ]

    opened = False
    for opener in openers:
        try:
            if await opener.count() > 0:
                await opener.first.click(timeout=3000)
                await page.wait_for_timeout(1000)
                opened = True
                break
        except Exception:
            pass

    if not opened:
        print("Could not open term dropdown.")
        return False

    options = [
        page.get_by_role("option", name=target_term),
        page.get_by_text(target_term, exact=False),
        page.locator(f'text="{target_term}"'),
    ]

    for option in options:
        try:
            if await option.count() > 0:
                await option.first.click(timeout=5000)
                await page.wait_for_timeout(1000)
                print(f'Selected term: "{target_term}"')
                return True
        except Exception:
            pass

    print(f'Could not find term "{target_term}"')
    return False


async def click_continue(page) -> bool:
    try:
        await page.get_by_role("button", name="Continue").click(timeout=5000)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2500)
        print("Clicked Continue.")
        return True
    except Exception as e:
        print("Failed to click Continue:", e)
        return False


async def select_subject_and_search(page, subject_name="Emergency Medical Services") -> bool:
    print('Trying "Browse by Course Subject"...')
    await page.wait_for_timeout(1500)

    opened = False

    opener_candidates = [
        page.locator('[aria-label*="Browse by Course Subject"]'),
        page.locator('[placeholder*="Browse by Course Subject"]'),
        page.locator('[role="combobox"]'),
        page.locator('input'),
        page.locator('button'),
    ]

    for candidate in opener_candidates:
        try:
            count = await candidate.count()
            for i in range(count):
                el = candidate.nth(i)
                try:
                    text = (await el.inner_text(timeout=500)).strip()
                except Exception:
                    text = ""
                try:
                    aria = await el.get_attribute("aria-label")
                except Exception:
                    aria = None
                try:
                    placeholder = await el.get_attribute("placeholder")
                except Exception:
                    placeholder = None

                looks_right = any([
                    aria and "course subject" in aria.lower(),
                    placeholder and "course subject" in placeholder.lower(),
                    "browse by course subject" in text.lower(),
                ])

                if looks_right:
                    await el.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                    opened = True
                    print("Opened subject control via labeled element.")
                    break
            if opened:
                break
        except Exception:
            pass

    if not opened:
        try:
            lbl = page.get_by_text("Browse by Course Subject", exact=False)
            if await lbl.count() > 0:
                await lbl.first.click(timeout=3000)
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(800)
                opened = True
                print("Focused subject control via label + Tab.")
        except Exception:
            pass

    if not opened:
        try:
            combos = page.locator('[role="combobox"]')
            count = await combos.count()
            for i in range(count):
                try:
                    await combos.nth(i).click(timeout=2000)
                    await page.wait_for_timeout(800)
                    opened = True
                    print(f"Opened combobox #{i}.")
                    break
                except Exception:
                    pass
        except Exception:
            pass

    if not opened:
        print("Could not open subject dropdown.")
        await debug_dump(page, "subject dropdown failure")
        return False

    typed = False
    try:
        await page.keyboard.press("Meta+A")
    except Exception:
        pass

    for text_value in [subject_name, "Emergency Medical", "Emergency Medical Services"]:
        try:
            await page.keyboard.type(text_value, delay=40)
            await page.wait_for_timeout(1200)
            typed = True
            print(f'Typed "{text_value}" into subject field.')
            break
        except Exception:
            pass

    if not typed:
        try:
            inputs = page.locator('input[type="text"], input[type="search"], input:not([type])')
            count = await inputs.count()
            for i in range(count):
                try:
                    inp = inputs.nth(i)
                    if await inp.is_visible():
                        await inp.click(timeout=1500)
                        await inp.fill(subject_name)
                        await page.wait_for_timeout(1200)
                        typed = True
                        print(f'Filled visible input #{i} with "{subject_name}".')
                        break
                except Exception:
                    pass
        except Exception:
            pass

    option_selected = False
    option_candidates = [
        page.get_by_role("option", name=subject_name),
        page.locator(f'text="{subject_name}"'),
        page.get_by_text(subject_name, exact=False),
        page.locator('[role="listbox"]'),
    ]

    for option in option_candidates:
        try:
            count = await option.count()
            if count > 0:
                try:
                    await page.get_by_text(subject_name, exact=False).first.click(timeout=5000)
                except Exception:
                    await option.first.click(timeout=5000)
                await page.wait_for_timeout(1200)
                option_selected = True
                print(f'Selected subject: "{subject_name}"')
                break
        except Exception:
            pass

    if not option_selected and typed:
        try:
            await page.keyboard.press("ArrowDown")
            await page.wait_for_timeout(300)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1200)
            option_selected = True
            print(f'Selected subject via keyboard: "{subject_name}"')
        except Exception:
            pass

    if not option_selected:
        print(f'Could not select subject "{subject_name}"')
        await debug_dump(page, "subject option failure")
        return False

    try:
        await page.locator("#search-go").click(timeout=5000)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)
        print("Clicked Search.")
        return True
    except Exception as e:
        print("Could not click Search:", e)
        await debug_dump(page, "search button failure")
        return False


async def check_results_for_ems201(page) -> bool:
    text = await page.locator("body").inner_text()

    print("\n--- RESULTS PREVIEW ---")
    print(text[:3000])
    print("--- END RESULTS PREVIEW ---\n")

    return ("EMS 201" in text) or ("EMS\n201" in text)


async def check_for_ems201():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Opening Cuesta term selection page...")
        await page.goto(CLASS_FINDER_URL, wait_until="domcontentloaded", timeout=60000)

        term_ok = await select_term(page, "Fall 2026")
        if not term_ok:
            await browser.close()
            return False, "Fall 2026 term is not selectable yet."

        continued = await click_continue(page)
        if not continued:
            await browser.close()
            return False, "Could not continue to class search."

        await debug_dump(page, "search page before subject search")

        searched = await select_subject_and_search(page, "Emergency Medical Services")
        if not searched:
            await browser.close()
            return False, "Could not search by subject."

        found = await check_results_for_ems201(page)

        await browser.close()

        if found:
            return True, "EMS 201 appears to be listed."
        return False, "EMS 201 not listed yet."


async def main():
    print("FORCE_TEST_EMAIL =", os.getenv("FORCE_TEST_EMAIL"))
    found, message = await check_for_ems201()
    print(message)

    force_test_email = os.getenv("FORCE_TEST_EMAIL", "false").lower() == "true"

    if found:
        send_email_alert(
            subject="Cuesta alert: EMS 201 is posted",
            body=(
                "EMS 201 appears to be listed in Cuesta's Fall 2026 schedule.\n\n"
                "Go check the Class Finder and try to register as soon as possible."
            ),
        )
    elif force_test_email:
        send_email_alert(
            subject="TEST: Cuesta EMS watcher email is working",
            body=(
                "This is a test email from your GitHub Actions workflow.\n\n"
                "Current script result: EMS 201 is not listed yet.\n\n"
                "If you received this, your Gmail notification setup is working."
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
