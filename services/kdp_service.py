import logging
from datetime import datetime, timezone
from pathlib import Path

import pyotp
from playwright.sync_api import sync_playwright, Page, BrowserContext

from config.settings import (
    DRY_RUN,
    KDP_BROWSER_PROFILE_DIR,
    KDP_EMAIL,
    KDP_PASSWORD,
    KDP_TOTP_SECRET,
    SCREENSHOTS_DIR,
)

logger = logging.getLogger(__name__)

KDP_BASE_URL = "https://kdp.amazon.com"
KDP_BOOKSHELF_URL = f"{KDP_BASE_URL}/bookshelf"

# Module-level state for persistent browser
_playwright = None
_browser_context: BrowserContext | None = None
_page: Page | None = None


def initialize_browser() -> Page:
    """Launch Chromium with a persistent context to preserve session cookies."""
    global _playwright, _browser_context, _page

    if _page and not _page.is_closed():
        return _page

    _playwright = sync_playwright().start()
    _browser_context = _playwright.chromium.launch_persistent_context(
        user_data_dir=KDP_BROWSER_PROFILE_DIR,
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
    )
    _page = _browser_context.new_page()
    logger.info("Browser initialized with persistent context at %s", KDP_BROWSER_PROFILE_DIR)
    return _page


def _take_screenshot(name: str):
    """Save a screenshot for debugging."""
    if _page and not _page.is_closed():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = Path(SCREENSHOTS_DIR) / f"{name}_{timestamp}.png"
        _page.screenshot(path=str(path))
        logger.info("Screenshot saved: %s", path)
        return str(path)
    return None


def login_to_kdp(email: str = KDP_EMAIL, password: str = KDP_PASSWORD, totp_secret: str = KDP_TOTP_SECRET):
    """Log in to KDP, handling 2FA with TOTP."""
    page = initialize_browser()

    page.goto(KDP_BOOKSHELF_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # Check if already logged in
    if "bookshelf" in page.url.lower() and page.query_selector('[id="title-list"]'):
        logger.info("Already logged in to KDP")
        return

    logger.info("Logging in to KDP as %s", email)

    # Email field
    email_field = page.wait_for_selector('input[type="email"], #ap_email', timeout=15000)
    email_field.fill(email)

    # Some flows have a "Continue" button before password
    continue_btn = page.query_selector('#continue')
    if continue_btn:
        continue_btn.click()
        page.wait_for_timeout(1000)

    # Password field
    password_field = page.wait_for_selector('input[type="password"], #ap_password', timeout=10000)
    password_field.fill(password)

    # Sign in
    sign_in_btn = page.query_selector('#signInSubmit')
    if sign_in_btn:
        sign_in_btn.click()
    else:
        password_field.press("Enter")

    page.wait_for_timeout(3000)

    # Handle 2FA if prompted
    totp_field = page.query_selector('input#auth-mfa-otpcode, input[name="otpCode"]')
    if totp_field:
        totp = pyotp.TOTP(totp_secret)
        code = totp.now()
        logger.info("Entering 2FA code")
        totp_field.fill(code)

        submit_btn = page.query_selector('#auth-signin-button')
        if submit_btn:
            submit_btn.click()
        else:
            totp_field.press("Enter")

        page.wait_for_timeout(3000)

    # Verify login succeeded
    if "bookshelf" in page.url.lower():
        logger.info("Successfully logged in to KDP")
    else:
        screenshot_path = _take_screenshot("login_failed")
        raise RuntimeError(f"KDP login failed — unexpected URL: {page.url}. Screenshot: {screenshot_path}")


def ensure_logged_in():
    """Check if the current session is valid; re-login if needed."""
    page = initialize_browser()
    page.goto(KDP_BOOKSHELF_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    if "signin" in page.url.lower() or "ap/signin" in page.url.lower():
        logger.info("Session expired, re-logging in")
        login_to_kdp()
    else:
        logger.debug("KDP session is still valid")


def select_book(book_title: str) -> bool:
    """Find and navigate to a book on the KDP bookshelf by title.

    Returns True if the book was found.
    """
    page = initialize_browser()
    ensure_logged_in()

    page.goto(KDP_BOOKSHELF_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # Search for the book by title
    search_input = page.query_selector('input[placeholder*="Search"]')
    if search_input:
        search_input.fill(book_title)
        search_input.press("Enter")
        page.wait_for_timeout(2000)

    # Look for the book in the list
    # KDP uses an ellipsis menu (...) next to each title
    book_rows = page.query_selector_all('[class*="title"]')
    for row in book_rows:
        text = row.inner_text()
        if book_title.lower() in text.lower():
            logger.info("Found book: %s", book_title)
            return True

    logger.warning("Book '%s' not found on KDP bookshelf", book_title)
    _take_screenshot("book_not_found")
    return False


def order_author_copies(book_title: str, quantity: int, address: dict, gift_message: str = "") -> dict:
    """Order author copies of a book through KDP.

    Args:
        book_title: title of the book to order
        quantity: number of copies
        address: dict with street, city, state, zip, country
        gift_message: optional gift message to include with the order

    Returns:
        dict with order_id and estimated_delivery
    """
    if DRY_RUN:
        logger.info(
            "DRY RUN — would order %d copies of '%s' to %s (gift: %s)",
            quantity, book_title, address, gift_message[:50] if gift_message else "none",
        )
        return {
            "order_id": "DRY_RUN",
            "estimated_delivery": "5-7 business days (dry run)",
        }

    page = initialize_browser()
    ensure_logged_in()

    try:
        # Navigate to bookshelf
        page.goto(KDP_BOOKSHELF_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Find the book's action menu
        # KDP bookshelf has "..." menus or direct action buttons per book
        book_found = False
        action_menus = page.query_selector_all('[class*="action-menu"], [class*="ellipsis"]')

        # Try to find the book row and click its action menu
        rows = page.query_selector_all('tr, [class*="book-row"], [class*="title-row"]')
        for row in rows:
            row_text = row.inner_text()
            if book_title.lower() in row_text.lower():
                # Click the action menu for this row
                menu = row.query_selector('[class*="action"], button[class*="menu"], [class*="ellipsis"]')
                if menu:
                    menu.click()
                    page.wait_for_timeout(1000)
                    book_found = True
                break

        if not book_found:
            raise RuntimeError(f"Could not find book '{book_title}' on KDP bookshelf")

        # Click "Order Author Copies" from the dropdown
        author_copies_link = page.query_selector(
            'text="Order Author Copies", a:has-text("Author Copies"), '
            '[class*="author-copies"]'
        )
        if not author_copies_link:
            # Try alternate selectors
            links = page.query_selector_all("a, button")
            for link in links:
                if "author cop" in link.inner_text().lower():
                    author_copies_link = link
                    break

        if not author_copies_link:
            _take_screenshot("no_author_copies_option")
            raise RuntimeError("Could not find 'Order Author Copies' option")

        author_copies_link.click()
        page.wait_for_timeout(3000)

        # Fill in quantity
        qty_input = page.wait_for_selector(
            'input[name*="quantity"], input[type="number"], input#quantity',
            timeout=10000,
        )
        qty_input.fill("")
        qty_input.fill(str(quantity))

        # Fill in shipping address
        _fill_address(page, address)

        # Fill gift message if provided
        if gift_message:
            gift_input = page.query_selector(
                'textarea[name*="gift"], textarea[name*="message"], '
                'input[name*="gift"], textarea#gift-message'
            )
            if gift_input:
                gift_input.fill("")
                gift_input.fill(gift_message)
                logger.info("Gift message filled")

        # Review order
        review_btn = page.query_selector(
            'button:has-text("Review"), input[value*="Review"], '
            'button:has-text("Continue"), a:has-text("Review")'
        )
        if review_btn:
            review_btn.click()
            page.wait_for_timeout(3000)

        # Submit order
        submit_btn = page.query_selector(
            'button:has-text("Place"), button:has-text("Submit"), '
            'input[value*="Place"], button:has-text("Order")'
        )
        if submit_btn:
            _take_screenshot("before_submit")
            submit_btn.click()
            page.wait_for_timeout(5000)
        else:
            _take_screenshot("no_submit_button")
            raise RuntimeError("Could not find submit/place order button")

        # Capture confirmation details
        result = {
            "order_id": _extract_order_id(page),
            "estimated_delivery": _extract_delivery_estimate(page),
        }

        _take_screenshot("order_confirmation")
        logger.info("KDP order placed: %s", result)
        return result

    except Exception:
        _take_screenshot("order_error")
        raise


def _fill_address(page: Page, address: dict):
    """Fill in the shipping address form on KDP."""
    field_mappings = [
        (address.get("street", ""), 'input[name*="street"], input[name*="address1"], #street'),
        (address.get("city", ""), 'input[name*="city"], #city'),
        (address.get("state", ""), 'input[name*="state"], select[name*="state"], #state'),
        (address.get("zip", ""), 'input[name*="zip"], input[name*="postal"], #zip'),
        (address.get("country", "US"), 'select[name*="country"], #country'),
    ]

    for value, selector in field_mappings:
        if not value:
            continue
        elements = selector.split(", ")
        for sel in elements:
            element = page.query_selector(sel.strip())
            if element:
                tag = element.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    element.select_option(label=value)
                else:
                    element.fill("")
                    element.fill(value)
                break


def _extract_order_id(page: Page) -> str:
    """Try to extract the order ID from the confirmation page."""
    # Look for common patterns
    selectors = [
        '[class*="order-id"]',
        '[class*="confirmation"]',
        'text=/[Oo]rder.*#?\\s*\\d+/',
    ]
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text()
            # Extract number from text
            import re
            match = re.search(r"#?\s*(\d[\d-]+)", text)
            if match:
                return match.group(1)
    return "UNKNOWN"


def _extract_delivery_estimate(page: Page) -> str:
    """Try to extract the estimated delivery date from the confirmation page."""
    selectors = [
        '[class*="delivery"]',
        '[class*="estimate"]',
        'text=/[Dd]eliver/',
    ]
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            return el.inner_text().strip()
    return "5-7 business days"


def close_browser():
    """Clean up browser resources."""
    global _playwright, _browser_context, _page
    if _page and not _page.is_closed():
        _page.close()
    if _browser_context:
        _browser_context.close()
    if _playwright:
        _playwright.stop()
    _page = None
    _browser_context = None
    _playwright = None
    logger.info("Browser closed")
