import logging
from datetime import datetime, timezone

import gspread
from google.oauth2 import service_account

from config.settings import GCP_SERVICE_ACCOUNT_KEY_PATH

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column headers for monthly tabs
HEADERS = [
    "NAME",
    "EMAIL ADDRESS",
    "PHONE #",
    "NO. OF COPIES",
    "CONFIRMATION SENT?",
    "AMAZON STATUS",
    "RECEIVED BY RECIPIENT",
    "PAYMENT METHOD",
    "ADDRESS",
    "ESTIMATED DELIVERY DATE",
    "SOURCE",
    "THREAD_ID",
]

THREAD_ID_COL = 12  # 1-indexed column number for THREAD_ID


def _get_client() -> gspread.Client:
    """Create an authenticated gspread client."""
    credentials = service_account.Credentials.from_service_account_file(
        GCP_SERVICE_ACCOUNT_KEY_PATH, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def _get_or_create_monthly_tab(spreadsheet) -> gspread.Worksheet:
    """Get or create a worksheet tab for the current month (e.g. 'February 2026').

    Creates the tab with headers if it doesn't exist.
    """
    now = datetime.now(timezone.utc)
    tab_name = now.strftime("%B %Y")  # e.g. "February 2026"

    try:
        worksheet = spreadsheet.worksheet(tab_name)
        logger.debug("Found existing tab: %s", tab_name)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        pass

    # Create new tab with headers
    worksheet = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=len(HEADERS))
    worksheet.append_row(HEADERS, value_input_option="USER_ENTERED")
    # Bold the header row
    worksheet.format("1:1", {"textFormat": {"bold": True}})
    logger.info("Created new monthly tab: %s", tab_name)
    return worksheet


def is_thread_logged(sheet_id: str, thread_id: str) -> bool:
    """Check if a thread ID already has a row in the current month's tab (deduplication)."""
    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)

    try:
        worksheet = _get_or_create_monthly_tab(spreadsheet)
        thread_ids = worksheet.col_values(THREAD_ID_COL)
        return thread_id in thread_ids
    except Exception:
        logger.exception("Failed to check sheet for thread %s", thread_id)
        return False


def log_order(sheet_id: str, order: dict):
    """Append an order row to the current month's tab in the Google Sheet.

    Columns:
    NAME | EMAIL ADDRESS | PHONE # | NO. OF COPIES | CONFIRMATION SENT? |
    AMAZON STATUS | RECEIVED BY RECIPIENT | PAYMENT METHOD | ADDRESS |
    ESTIMATED DELIVERY DATE | SOURCE | THREAD_ID
    """
    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = _get_or_create_monthly_tab(spreadsheet)

    row = [
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

    worksheet.append_row(row, value_input_option="USER_ENTERED")
    logger.info("Logged order to Google Sheet (thread: %s)", order.get("thread_id"))


def get_all_rows(sheet_id: str) -> list[dict]:
    """Fetch all order rows from the current month's tab for the dashboard."""
    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)

    try:
        worksheet = _get_or_create_monthly_tab(spreadsheet)
    except Exception:
        logger.exception("Failed to access monthly tab")
        return []

    records = worksheet.get_all_values()

    field_keys = [
        "name", "email", "phone", "quantity", "confirmation_sent",
        "amazon_status", "received_by_recipient", "payment_method",
        "shipping_address", "estimated_delivery", "source", "thread_id",
    ]

    orders = []
    for i, row in enumerate(records[1:], start=2):  # skip header row
        order = {"row_number": i}
        for j, key in enumerate(field_keys):
            order[key] = row[j] if j < len(row) else ""
        orders.append(order)

    return list(reversed(orders))  # newest first
