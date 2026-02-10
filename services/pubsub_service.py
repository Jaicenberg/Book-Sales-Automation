import json
import logging
from pathlib import Path

from google.api_core import retry
from google.cloud import pubsub_v1
from google.oauth2 import service_account

from config.settings import (
    GCP_PROJECT_ID,
    GCP_SERVICE_ACCOUNT_KEY_PATH,
    GMAIL_LABEL_NAME,
    GMAIL_USER_EMAIL,
    PUBSUB_SUBSCRIPTION,
    STATE_FILE,
)
from services.gmail_service import get_gmail_service, get_history, get_label_id

logger = logging.getLogger(__name__)


def _load_state() -> dict:
    path = Path(STATE_FILE)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_state(state: dict):
    Path(STATE_FILE).write_text(json.dumps(state))


def get_subscriber_client() -> pubsub_v1.SubscriberClient:
    credentials = service_account.Credentials.from_service_account_file(
        GCP_SERVICE_ACCOUNT_KEY_PATH,
        scopes=["https://www.googleapis.com/auth/pubsub"],
    )
    return pubsub_v1.SubscriberClient(credentials=credentials)


def pull_and_process(message_callback):
    """Pull messages from Pub/Sub and process new Gmail messages.

    Only processes messages with the "book sales" label — no classification needed.

    Args:
        message_callback: function(thread_id, message_id, message) called for each new message
    """
    subscriber = get_subscriber_client()
    subscription_path = subscriber.subscription_path(GCP_PROJECT_ID, PUBSUB_SUBSCRIPTION)

    gmail_service = get_gmail_service(GMAIL_USER_EMAIL)
    label_id = get_label_id(gmail_service, GMAIL_LABEL_NAME)

    if not label_id:
        logger.error("Gmail label '%s' not found", GMAIL_LABEL_NAME)
        return

    response = subscriber.pull(
        request={"subscription": subscription_path, "max_messages": 10},
        retry=retry.Retry(deadline=30),
    )

    if not response.received_messages:
        return

    state = _load_state()
    ack_ids = []

    for received in response.received_messages:
        ack_ids.append(received.ack_id)

        try:
            data = json.loads(received.message.data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Failed to decode Pub/Sub message, skipping")
            continue

        new_history_id = data.get("historyId")
        if not new_history_id:
            continue

        last_history_id = state.get("last_history_id")
        if not last_history_id:
            logger.info("First run — storing historyId %s", new_history_id)
            state["last_history_id"] = str(new_history_id)
            _save_state(state)
            continue

        try:
            new_messages = get_history(gmail_service, last_history_id, label_id)
        except Exception:
            logger.exception("Failed to fetch Gmail history from %s", last_history_id)
            continue

        logger.info("Found %d new 'book sales' messages since historyId %s", len(new_messages), last_history_id)

        seen_threads = set()
        for msg_stub in new_messages:
            msg_id = msg_stub.get("id")
            thread_id = msg_stub.get("threadId")

            if thread_id in seen_threads:
                continue
            seen_threads.add(thread_id)

            try:
                full_message = (
                    gmail_service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )
                message_callback(thread_id, msg_id, full_message)
            except Exception:
                logger.exception("Failed to process message %s in thread %s", msg_id, thread_id)

        state["last_history_id"] = str(new_history_id)
        _save_state(state)

    if ack_ids:
        subscriber.acknowledge(
            request={"subscription": subscription_path, "ack_ids": ack_ids}
        )
        logger.info("Acknowledged %d Pub/Sub messages", len(ack_ids))


def start_listener(message_callback, poll_interval: int = 5):
    """Continuously poll Pub/Sub for new messages with the 'book sales' label."""
    import time

    logger.info("Starting Pub/Sub listener (poll interval: %ds)", poll_interval)
    while True:
        try:
            pull_and_process(message_callback)
        except Exception:
            logger.exception("Error in Pub/Sub pull loop")
        time.sleep(poll_interval)
