import logging

from config.email_templates import (
    MISSING_INFO_TEMPLATE,
    ORDER_CONFIRMATION_TEMPLATE,
    format_missing_fields,
)
from config.settings import (
    ASH_SENDER_NAME,
    DEFAULT_BOOK,
    DRY_RUN,
    GMAIL_USER_EMAIL,
    GOOGLE_SHEET_ID,
    KDP_GIFT_MESSAGE,
    NICK_EMAIL,
)
from services.gmail_service import (
    apply_label_to_thread,
    get_gmail_service,
    get_message_body,
    get_message_headers,
    get_thread_messages,
    parse_sender,
    reply_to_thread,
)
from services.kdp_service import order_author_copies
from services.parser_service import classify_as_book_sale, parse_email_thread
from services.sheets_service import is_thread_logged, log_order

logger = logging.getLogger(__name__)


def process_inbox_message(thread_id: str, message_id: str, message: dict):
    """Process a new INBOX message that hasn't been labeled yet.

    Classifies the email as a book sale or not. If it's a book sale,
    applies the "book sales" label and hands off to process_book_sale().
    """
    gmail_service = get_gmail_service(GMAIL_USER_EMAIL)
    body = get_message_body(message)
    headers = get_message_headers(message)

    email_text = (
        f"From: {headers.get('from', '')}\n"
        f"To: {headers.get('to', '')}\n"
        f"Cc: {headers.get('cc', '')}\n"
        f"Subject: {headers.get('subject', '')}\n\n"
        f"{body}"
    )

    if not classify_as_book_sale(email_text):
        logger.debug("Thread %s is NOT a book sale — ignoring", thread_id)
        return

    logger.info("Thread %s classified as BOOK SALE — applying label", thread_id)
    try:
        apply_label_to_thread(gmail_service, thread_id)
    except Exception:
        logger.exception("Failed to apply label to thread %s", thread_id)

    # Now process as a book sale
    process_book_sale(thread_id, message_id, message)


def process_book_sale(thread_id: str, message_id: str, message: dict):
    """Process a confirmed book sale thread.

    Flow: parse -> (ask for info OR ship) -> confirm -> log to Sheets
    """
    # Dedup: check if this thread was already fully processed
    if is_thread_logged(GOOGLE_SHEET_ID, thread_id):
        logger.info("Thread %s already logged in Sheets, skipping", thread_id)
        return

    gmail_service = get_gmail_service(GMAIL_USER_EMAIL)
    headers = get_message_headers(message)
    sender = parse_sender(headers.get("from", ""))

    # --- Step 1: Build thread text for Claude ---
    messages = get_thread_messages(gmail_service, thread_id)

    thread_parts = []
    last_message = None
    for msg in reversed(messages):
        msg_headers = get_message_headers(msg)
        body = get_message_body(msg)
        thread_parts.append(
            f"From: {msg_headers.get('from', 'Unknown')}\n"
            f"Date: {msg_headers.get('date', 'Unknown')}\n\n"
            f"{body}\n\n---\n"
        )
        if last_message is None:
            last_message = msg

    thread_text = "\n".join(thread_parts)

    # --- Step 2: Parse with Claude ---
    parsed = parse_email_thread(thread_text, sender["email"])

    if "parse_error" in parsed.get("missing_fields", []) or "api_error" in parsed.get(
        "missing_fields", []
    ):
        logger.error("Failed to parse thread %s — flagging for manual review", thread_id)
        return

    # --- Step 3: Missing info? Ask for it and stop ---
    missing = parsed.get("missing_fields", [])
    if missing:
        name = parsed.get("name") or "there"

        body = MISSING_INFO_TEMPLATE.substitute(
            name=name,
            sender_name=ASH_SENDER_NAME,
            missing_list=format_missing_fields(missing),
        )
        try:
            reply_to_thread(gmail_service, last_message, body, cc=NICK_EMAIL)
            logger.info("Requested missing info for thread %s: %s", thread_id, missing)
        except Exception:
            logger.exception("Failed to send missing info request for thread %s", thread_id)
        return

    # --- Step 4: All info present — place KDP order ---
    book_title = DEFAULT_BOOK["title"] if DEFAULT_BOOK else "The 2-Hour Cocktail Party"
    quantity = parsed.get("quantity", 1)
    address = parsed.get("shipping_address", "")

    # Build address dict for KDP if we have a string
    if isinstance(address, str):
        address_for_kdp = {"street": address}
    else:
        address_for_kdp = address or {}

    try:
        result = order_author_copies(book_title, quantity, address_for_kdp, gift_message=KDP_GIFT_MESSAGE)
    except Exception:
        logger.exception("KDP order failed for thread %s", thread_id)
        return

    kdp_order_id = result.get("order_id", "DRY_RUN" if DRY_RUN else "UNKNOWN")
    estimated_delivery = result.get("estimated_delivery", "5-7 business days")

    # --- Step 5: Send confirmation email ---
    name = parsed.get("name") or "there"
    first_name = name.split()[0] if name != "there" else "there"

    confirmation_body = ORDER_CONFIRMATION_TEMPLATE.substitute(
        name=first_name,
        estimated_delivery=estimated_delivery,
        sender_name=ASH_SENDER_NAME,
    )

    try:
        reply_to_thread(gmail_service, last_message, confirmation_body, cc=NICK_EMAIL)
        logger.info("Sent confirmation for thread %s", thread_id)
    except Exception:
        logger.exception("Failed to send confirmation for thread %s", thread_id)

    # --- Step 6: Log to Google Sheets ---
    try:
        log_order(GOOGLE_SHEET_ID, {
            "thread_id": thread_id,
            "name": parsed.get("name", ""),
            "email": parsed.get("email", sender["email"]),
            "phone": parsed.get("phone", ""),
            "quantity": quantity,
            "shipping_address": address if isinstance(address, str) else str(address),
            "estimated_delivery": estimated_delivery,
            "payment_method": parsed.get("payment_method", ""),
            "source": parsed.get("source", ""),
            "confirmation_sent": "Yes",
            "amazon_status": "Ordered",
        })
        logger.info("Order fully processed and logged for thread %s", thread_id)
    except Exception:
        logger.exception("Failed to log order to Sheets for thread %s (order was placed)", thread_id)
