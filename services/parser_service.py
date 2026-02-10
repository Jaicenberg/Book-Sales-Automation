import json
import logging

import anthropic

from config.settings import ANTHROPIC_API_KEY, BOOK_CATALOG

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Classification prompt ───────────────────────────────────────────────────

CLASSIFY_PROMPT = """You are an email classifier. You will be given an email and must determine whether it is related to a book sale/purchase.

A book sale email is one where:
- Someone is buying, ordering, or requesting a book
- Someone is responding to a book order (providing address, payment info, etc.)
- Nick is CC'ing his assistant about a book sale
- A client is confirming or following up on a book purchase

NOT a book sale:
- Newsletter subscriptions, marketing emails
- General questions unrelated to purchasing
- Spam, notifications, calendar invites
- Social media notifications

Return ONLY a JSON object (no markdown, no explanation):
{{"is_book_sale": true}} or {{"is_book_sale": false}}"""

# ── Extraction prompt ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an order extraction assistant. You will be given an email thread about a book order.
Extract the following information from the entire conversation thread:

1. name — the customer/recipient's full name (single field)
2. email — the customer's email address (already provided separately, just confirm it)
3. phone — the customer's phone number
4. shipping_address — their full shipping address as a single string (street, city, state, ZIP, country)
5. quantity — how many copies (default 1 if not specified)
6. payment_method — how they paid (e.g. "Venmo", "PayPal", "credit card", "check", etc.)
7. source — how this sale originated (e.g. "direct email", "website", "referral", "event", etc.)

IMPORTANT:
- Look through ALL messages in the thread to find information. A customer might provide their address in a follow-up reply.
- If a field is not found anywhere in the thread, set it to null.
- Return a "missing_fields" array listing any of these fields that are null or incomplete: name, phone, shipping_address.
  Only these three fields should appear in missing_fields. Do NOT include email, quantity, payment_method, or source in missing_fields.
- For shipping_address, if the address is incomplete or missing, include "shipping_address" in missing_fields.
- The book is always "The 2-Hour Cocktail Party" — do not ask about book title.
- Always return valid JSON matching the exact schema below.

Available books: {book_list}

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{
  "name": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "shipping_address": "string or null",
  "quantity": 1,
  "payment_method": "string or null",
  "source": "string or null",
  "missing_fields": ["field1", "field2"]
}}"""


def _error_result(sender_email: str, error_type: str) -> dict:
    """Return a standardized error result dict."""
    return {
        "name": None,
        "email": sender_email,
        "phone": None,
        "shipping_address": None,
        "quantity": 1,
        "payment_method": None,
        "source": None,
        "missing_fields": [error_type],
    }


def classify_as_book_sale(email_text: str) -> bool:
    """Use Claude to classify whether an email is about a book sale.

    Returns True if the email is a book sale, False otherwise.
    """
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=64,
            system=CLASSIFY_PROMPT,
            messages=[{"role": "user", "content": email_text}],
        )

        content = response.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[: content.rfind("```")]
            content = content.strip()

        result = json.loads(content)
        is_sale = result.get("is_book_sale", False)
        logger.info("Email classified as book sale: %s", is_sale)
        return is_sale

    except (json.JSONDecodeError, Exception):
        logger.exception("Failed to classify email, defaulting to False")
        return False


def parse_email_thread(thread_text: str, sender_email: str) -> dict:
    """Parse an email thread using Claude to extract order details.

    Args:
        thread_text: concatenated text of all messages in the thread
        sender_email: email address of the customer

    Returns:
        Parsed order data dict with missing_fields list
    """
    book_list = ", ".join(f'"{b["title"]}"' for b in BOOK_CATALOG)
    system = SYSTEM_PROMPT.format(book_list=book_list)

    user_message = (
        f"Customer email: {sender_email}\n\n"
        f"--- EMAIL THREAD ---\n{thread_text}\n--- END ---"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

        content = response.content[0].text.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[: content.rfind("```")]
            content = content.strip()

        parsed = json.loads(content)

        # Ensure required structure
        parsed.setdefault("email", sender_email)
        parsed.setdefault("missing_fields", [])
        parsed.setdefault("quantity", 1)
        parsed.setdefault("payment_method", None)
        parsed.setdefault("source", None)

        # Validate required fields are present
        if not parsed.get("name") and "name" not in parsed["missing_fields"]:
            parsed["missing_fields"].append("name")
        if not parsed.get("phone") and "phone" not in parsed["missing_fields"]:
            parsed["missing_fields"].append("phone")
        if not parsed.get("shipping_address") and "shipping_address" not in parsed["missing_fields"]:
            parsed["missing_fields"].append("shipping_address")

        logger.info(
            "Parsed order — name: %s, missing: %s",
            parsed.get("name"),
            parsed.get("missing_fields"),
        )
        return parsed

    except json.JSONDecodeError:
        logger.exception("Failed to parse Claude response as JSON")
        return _error_result(sender_email, "parse_error")
    except Exception:
        logger.exception("Claude API call failed")
        return _error_result(sender_email, "api_error")
