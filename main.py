#!/usr/bin/env python3
"""Book Sending Automation — Main entry point.

Starts:
1. Pub/Sub listener (pulls Gmail notifications for "book sales" label, processes orders)
2. Gmail watch renewal (every 24h)
3. Flask dashboard (on a separate thread)
"""
import logging
import threading
import time

import schedule

from config.settings import GMAIL_LABEL_NAME, GMAIL_USER_EMAIL, validate_settings
from dashboard.app import start_dashboard
from services.gmail_service import get_gmail_service, start_watch
from services.order_service import process_book_sale
from services.pubsub_service import start_listener

logger = logging.getLogger(__name__)


def renew_watch():
    """Re-register Gmail Pub/Sub watch on the 'book sales' label (must be called every <7 days; we do it daily)."""
    try:
        service = get_gmail_service(GMAIL_USER_EMAIL)
        result = start_watch(service, GMAIL_LABEL_NAME)
        logger.info("Watch renewed — historyId: %s", result.get("historyId"))
    except Exception:
        logger.exception("Failed to renew Gmail watch")


def run_scheduler():
    """Run the schedule loop for periodic tasks (watch renewal)."""
    schedule.every(24).hours.do(renew_watch)
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    # Validate all required settings before doing anything
    validate_settings()

    logger.info("Starting Book Sending Automation")

    # Register initial Gmail watch on "book sales" label
    renew_watch()

    # Start dashboard in a background thread
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    logger.info("Dashboard started in background thread")

    # Start scheduler in a background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Scheduler started (watch renewal every 24h)")

    # Start Pub/Sub listener (blocking — runs in main thread)
    # Only fires for emails with the "book sales" label — no wasted Claude calls
    logger.info("Starting Pub/Sub listener (watching '%s' label only)", GMAIL_LABEL_NAME)
    start_listener(message_callback=process_book_sale, poll_interval=5)


if __name__ == "__main__":
    main()
