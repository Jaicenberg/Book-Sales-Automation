#!/usr/bin/env python3
"""Dry-run script — simulates the full order pipeline with fake data.

No API keys, no external services. Run this to verify the logic flow before
hooking up real credentials.

Usage:
    python dry_run.py
    python dry_run.py --scenario complete      # order with all info
    python dry_run.py --scenario missing        # order missing phone/address
    python dry_run.py --scenario duplicate      # already-processed thread
"""
import argparse
import logging
from datetime import datetime, timezone
from string import Template

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dry_run")

# ── Constants (matching config/settings.py defaults) ─────────────────────────
ASH_SENDER_NAME = "Ash Smith"
NICK_EMAIL = "nick@nickgray.net"
BOOK_TITLE = "The 2-Hour Cocktail Party"
KDP_GIFT_MESSAGE = (
    "Congrats! Here is your copy of The 2-Hour Cocktail Party by Nick Gray. "
    "Enjoy the book! Nick's cell is 512-trick-46 — feel free to text with questions."
)

# ── Inline copies of templates (avoids importing config which needs env vars) ─
MISSING_INFO_TEMPLATE = Template(
    "Hey $name,\n\n"
    "Thanks so much for your book purchase! I'm $sender_name, Nick's assistant, "
    "and I'll be handling the shipping for your copy of The 2-Hour Cocktail Party.\n\n"
    "Before I can get it sent out, I just need a couple things from you:\n\n"
    "$missing_list\n\n"
    "Once I have that, I'll get your book ordered and on its way!\n\n"
    "Best,\n$sender_name"
)

ORDER_CONFIRMATION_TEMPLATE = Template(
    "Hey $name,\n\n"
    "Your copy of The 2-Hour Cocktail Party is on its way! "
    "You should receive it by $estimated_delivery.\n\n"
    "You'll get a shipping confirmation from Amazon with tracking info shortly.\n\n"
    "Enjoy the read!\n\n"
    "Best,\n$sender_name\n\n"
    "P.S. If you find the book helpful, a review on Amazon goes a long way: "
    "https://www.amazon.com/dp/B09VKY415G"
)

FIELD_LABELS = {
    "name": "Your full name",
    "phone": "Your phone number",
    "shipping_address": "Your full shipping address (street, city, state, ZIP, country)",
}


def format_missing_fields(missing_fields: list[str]) -> str:
    lines = []
    for field in missing_fields:
        label = FIELD_LABELS.get(field, field.replace("_", " ").title())
        lines.append(f"  - {label}")
    return "\n".join(lines)


# ── Fake data ────────────────────────────────────────────────────────────────
FAKE_EMAILS = {
    "complete": {
        "thread_id": "thread_abc123",
        "message_id": "msg_001",
        "from": "Nick Gray <nick@nickgray.net>",
        "to": "ash@nickgray.net",
        "cc": "Sarah Johnson <sarah.johnson@example.com>",
        "subject": "Book for Sarah",
        "body": (
            "Hey Ash,\n\n"
            "Can you send a copy of the book to Sarah?\n\n"
            "Sarah Johnson\n"
            "sarah.johnson@example.com\n"
            "Phone: 917-555-0123\n"
            "456 Oak Avenue, Apt 2B\n"
            "Brooklyn, NY 11201\n\n"
            "She paid via Venmo.\n\n"
            "Thanks!\n"
            "Nick"
        ),
    },
    "missing": {
        "thread_id": "thread_def456",
        "message_id": "msg_002",
        "from": "Nick Gray <nick@nickgray.net>",
        "to": "ash@nickgray.net",
        "cc": "Mike Chen <mike.chen@example.com>",
        "subject": "Book for Mike",
        "body": (
            "Hey Ash,\n\n"
            "Please send Mike a copy of the book. "
            "He paid via PayPal.\n\n"
            "Thanks,\n"
            "Nick"
        ),
    },
    "duplicate": {
        "thread_id": "thread_already_done",
        "message_id": "msg_003",
        "from": "Sarah Johnson <sarah.johnson@example.com>",
        "to": "ash@nickgray.net",
        "subject": "Re: Book for Sarah",
        "body": "Got it, thanks so much!",
    },
}

# Simulated "classified" results
FAKE_CLASSIFICATIONS = {
    "complete": True,
    "missing": True,
    "duplicate": True,  # already labeled, skip classification
}

# Simulated "parsed" results (what Claude would return)
FAKE_PARSED = {
    "complete": {
        "name": "Sarah Johnson",
        "email": "sarah.johnson@example.com",
        "phone": "917-555-0123",
        "shipping_address": "456 Oak Avenue, Apt 2B, Brooklyn, NY 11201",
        "quantity": 1,
        "payment_method": "Venmo",
        "source": "direct email from Nick",
        "missing_fields": [],
    },
    "missing": {
        "name": "Mike Chen",
        "email": "mike.chen@example.com",
        "phone": None,
        "shipping_address": None,
        "quantity": 1,
        "payment_method": "PayPal",
        "source": "direct email from Nick",
        "missing_fields": ["phone", "shipping_address"],
    },
}

# Simulated Google Sheet (threads already processed)
FAKE_SHEET_LOG = {"thread_already_done"}


# ── Simulated services ───────────────────────────────────────────────────────
def fake_classify(email_text: str, scenario: str) -> bool:
    is_sale = FAKE_CLASSIFICATIONS.get(scenario, False)
    logger.info("[Claude] Classifying email as book sale: %s", is_sale)
    return is_sale


def fake_is_thread_logged(thread_id: str) -> bool:
    logged = thread_id in FAKE_SHEET_LOG
    logger.info("[Sheets] Checking if thread '%s' is logged: %s", thread_id, logged)
    return logged


def fake_parse_email(thread_text: str, sender_email: str, scenario: str) -> dict:
    logger.info("[Claude] Parsing email thread from %s ...", sender_email)
    parsed = FAKE_PARSED.get(scenario)
    if parsed:
        logger.info(
            "[Claude] Extracted — name: %s, missing: %s",
            parsed.get("name"),
            parsed.get("missing_fields"),
        )
    return parsed


def fake_reply(to: str, subject: str, body: str, cc: str = None):
    logger.info("[Gmail] Sending reply to %s (CC: %s)", to, cc or "none")
    print(f"\n{'='*60}")
    print(f"  TO: {to}")
    if cc:
        print(f"  CC: {cc}")
    print(f"  SUBJECT: Re: {subject}")
    print(f"{'='*60}")
    print(body)
    print(f"{'='*60}\n")


def fake_apply_label(thread_id: str):
    logger.info("[Gmail] Applied 'book sales' label to thread %s", thread_id)


def fake_order_author_copies(book_title: str, quantity: int, address: str, gift_message: str) -> dict:
    logger.info(
        "[KDP] DRY RUN — would order %d copy(ies) of '%s' to %s",
        quantity, book_title, address,
    )
    logger.info("[KDP] Gift message: %s", gift_message[:60])
    return {
        "order_id": "DRY_RUN_12345",
        "estimated_delivery": "February 18, 2026",
    }


def fake_log_order(order: dict):
    logger.info("[Sheets] Logging order to monthly tab (February 2026):")
    headers = [
        "NAME", "EMAIL ADDRESS", "PHONE #", "NO. OF COPIES",
        "CONFIRMATION SENT?", "AMAZON STATUS", "RECEIVED BY RECIPIENT",
        "PAYMENT METHOD", "ADDRESS", "ESTIMATED DELIVERY DATE", "SOURCE", "THREAD_ID",
    ]
    values = [
        order.get("name", ""),
        order.get("email", ""),
        order.get("phone", ""),
        order.get("quantity", 1),
        order.get("confirmation_sent", "Yes"),
        order.get("amazon_status", "Ordered"),
        order.get("received_by_recipient", ""),
        order.get("payment_method", ""),
        order.get("shipping_address", ""),
        order.get("estimated_delivery", ""),
        order.get("source", ""),
        order.get("thread_id", ""),
    ]
    for h, v in zip(headers, values):
        print(f"  {h:>28}: {v}")
    FAKE_SHEET_LOG.add(order.get("thread_id"))


# ── Main pipeline ────────────────────────────────────────────────────────────
def process_fake_message(scenario: str):
    email = FAKE_EMAILS[scenario]
    thread_id = email["thread_id"]
    sender_email = email["from"].split("<")[1].rstrip(">") if "<" in email["from"] else email["from"]
    client_cc = email.get("cc", "")
    client_email = ""
    if client_cc and "<" in client_cc:
        client_email = client_cc.split("<")[1].rstrip(">")
    elif client_cc:
        client_email = client_cc

    print(f"\n{'#'*60}")
    print(f"  SCENARIO: {scenario.upper()}")
    print(f"  Thread:   {thread_id}")
    print(f"  From:     {email['from']}")
    print(f"  To:       {email.get('to', '')}")
    if email.get("cc"):
        print(f"  CC:       {email['cc']}")
    print(f"  Subject:  {email['subject']}")
    print(f"{'#'*60}\n")

    # Step 0a: Classification (simulate inbox_callback path for non-duplicate)
    if scenario != "duplicate":
        email_text = (
            f"From: {email['from']}\n"
            f"To: {email.get('to', '')}\n"
            f"Cc: {email.get('cc', '')}\n"
            f"Subject: {email['subject']}\n\n"
            f"{email['body']}"
        )
        if not fake_classify(email_text, scenario):
            logger.info("Not a book sale — IGNORING")
            return
        fake_apply_label(thread_id)

    # Step 0b: Dedup check
    if fake_is_thread_logged(thread_id):
        logger.info("Thread %s already logged — SKIPPING (duplicate)", thread_id)
        return

    # Step 1: Build thread text
    thread_text = (
        f"From: {email['from']}\n"
        f"Date: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"{email['body']}\n\n---\n"
    )

    # Step 2: Parse with Claude (simulated)
    parsed = fake_parse_email(thread_text, client_email or sender_email, scenario)
    if not parsed:
        logger.error("No parsed data for scenario '%s' — skipping", scenario)
        return

    if "parse_error" in parsed.get("missing_fields", []) or "api_error" in parsed.get("missing_fields", []):
        logger.error("Parse/API error — flagging for manual review")
        return

    # Step 3: Missing info? Ask for it
    missing = parsed.get("missing_fields", [])
    if missing:
        name = parsed.get("name") or "there"

        body = MISSING_INFO_TEMPLATE.substitute(
            name=name,
            sender_name=ASH_SENDER_NAME,
            missing_list=format_missing_fields(missing),
        )
        fake_reply(client_email or sender_email, email["subject"], body, cc=NICK_EMAIL)
        logger.info("Requested missing info: %s — PIPELINE PAUSED for this thread", missing)
        return

    # Step 4: Place KDP order
    quantity = parsed.get("quantity", 1)
    address = parsed.get("shipping_address", "")

    result = fake_order_author_copies(BOOK_TITLE, quantity, address, KDP_GIFT_MESSAGE)

    # Step 5: Send confirmation email
    name = parsed.get("name") or "there"
    first_name = name.split()[0] if name != "there" else "there"
    confirmation_body = ORDER_CONFIRMATION_TEMPLATE.substitute(
        name=first_name,
        estimated_delivery=result["estimated_delivery"],
        sender_name=ASH_SENDER_NAME,
    )
    fake_reply(client_email or sender_email, email["subject"], confirmation_body, cc=NICK_EMAIL)

    # Step 6: Log to Sheets
    fake_log_order({
        "thread_id": thread_id,
        "name": parsed.get("name", ""),
        "email": parsed.get("email", client_email or sender_email),
        "phone": parsed.get("phone", ""),
        "quantity": quantity,
        "shipping_address": address,
        "estimated_delivery": result["estimated_delivery"],
        "payment_method": parsed.get("payment_method", ""),
        "source": parsed.get("source", ""),
        "confirmation_sent": "Yes",
        "amazon_status": "Ordered",
    })

    logger.info("Order FULLY PROCESSED for thread %s", thread_id)


# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Dry-run the book order pipeline")
    parser.add_argument(
        "--scenario",
        choices=["complete", "missing", "duplicate", "all"],
        default="all",
        help="Which scenario to run (default: all)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  BOOK SALES AUTOMATION — DRY RUN")
    print(f"  Nick Gray / {ASH_SENDER_NAME} workflow")
    print("  No API keys needed. All services are simulated.")
    print("=" * 60)

    if args.scenario == "all":
        for scenario in ["complete", "missing", "duplicate"]:
            process_fake_message(scenario)
    else:
        process_fake_message(args.scenario)

    print("\n" + "=" * 60)
    print("  DRY RUN COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
