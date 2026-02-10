import base64
import logging
import re
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

from config.settings import (
    GCP_PROJECT_ID,
    GCP_SERVICE_ACCOUNT_KEY_PATH,
    GMAIL_LABEL_NAME,
    GMAIL_SCOPES,
    PUBSUB_TOPIC,
)

logger = logging.getLogger(__name__)


def get_gmail_service(user_email: str):
    """Build an authenticated Gmail API service impersonating the given user."""
    credentials = service_account.Credentials.from_service_account_file(
        GCP_SERVICE_ACCOUNT_KEY_PATH, scopes=GMAIL_SCOPES
    )
    delegated = credentials.with_subject(user_email)
    delegated.refresh(Request())
    return build("gmail", "v1", credentials=delegated, cache_discovery=False)


def get_label_id(service, label_name: str) -> str | None:
    """Resolve a Gmail label name to its ID."""
    results = service.users().labels().list(userId="me").execute()
    for label in results.get("labels", []):
        if label["name"].lower() == label_name.lower():
            return label["id"]
    return None


def apply_label_to_thread(service, thread_id: str, label_name: str = GMAIL_LABEL_NAME):
    """Apply a Gmail label to an entire thread."""
    label_id = get_label_id(service, label_name)
    if not label_id:
        logger.error("Cannot apply label '%s' — not found", label_name)
        return
    service.users().threads().modify(
        userId="me",
        id=thread_id,
        body={"addLabelIds": [label_id]},
    ).execute()
    logger.info("Applied label '%s' to thread %s", label_name, thread_id)


def thread_has_label(service, thread_id: str, label_name: str = GMAIL_LABEL_NAME) -> bool:
    """Check if a thread already has a specific label."""
    label_id = get_label_id(service, label_name)
    if not label_id:
        return False
    thread = service.users().threads().get(
        userId="me", id=thread_id, format="minimal"
    ).execute()
    for msg in thread.get("messages", []):
        if label_id in msg.get("labelIds", []):
            return True
    return False


def start_watch(service, label_name: str = GMAIL_LABEL_NAME) -> dict:
    """Register a Pub/Sub watch on the given label. Returns watch response with historyId."""
    label_id = get_label_id(service, label_name)
    if not label_id:
        raise ValueError(f"Gmail label '{label_name}' not found")

    topic = f"projects/{GCP_PROJECT_ID}/topics/{PUBSUB_TOPIC}"
    request_body = {
        "topicName": topic,
        "labelIds": [label_id],
        "labelFilterBehavior": "INCLUDE",
    }
    response = service.users().watch(userId="me", body=request_body).execute()
    logger.info(
        "Watch registered — historyId: %s, expiration: %s",
        response.get("historyId"),
        response.get("expiration"),
    )
    return response


def start_watch_inbox(service) -> dict:
    """Register a Pub/Sub watch on the entire INBOX. Returns watch response with historyId."""
    topic = f"projects/{GCP_PROJECT_ID}/topics/{PUBSUB_TOPIC}"
    request_body = {
        "topicName": topic,
        "labelIds": ["INBOX"],
        "labelFilterBehavior": "INCLUDE",
    }
    response = service.users().watch(userId="me", body=request_body).execute()
    logger.info(
        "INBOX watch registered — historyId: %s, expiration: %s",
        response.get("historyId"),
        response.get("expiration"),
    )
    return response


def get_thread_messages(service, thread_id: str) -> list[dict]:
    """Fetch all messages in a thread, ordered oldest first."""
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    return thread.get("messages", [])


def get_message_body(message: dict) -> str:
    """Extract plain text body from a Gmail message's MIME payload."""
    payload = message.get("payload", {})
    return _extract_text(payload)


def _extract_text(payload: dict) -> str:
    """Recursively extract text/plain parts from MIME payload."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    # Multipart — recurse into parts
    parts = payload.get("parts", [])
    for part in parts:
        text = _extract_text(part)
        if text:
            return text

    return ""


def get_message_headers(message: dict) -> dict:
    """Extract common headers (From, To, Cc, Subject, Date) from a message."""
    headers = {}
    for header in message.get("payload", {}).get("headers", []):
        name = header["name"].lower()
        if name in ("from", "to", "cc", "subject", "date", "message-id"):
            headers[name] = header["value"]
    return headers


def parse_sender(from_header: str) -> dict:
    """Extract name and email from a From header like 'John Smith <john@example.com>'."""
    match = re.match(r"^(.*?)\s*<(.+?)>$", from_header)
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip()
    else:
        name = ""
        email = from_header.strip()

    first_name = name.split()[0] if name else email.split("@")[0]
    return {"full_name": name, "first_name": first_name, "email": email}


def reply_to_thread(service, original_message: dict, body: str, cc: str = None):
    """Reply within an existing thread, optionally CC'ing someone."""
    headers = get_message_headers(original_message)
    thread_id = original_message.get("threadId")
    sender = headers.get("from", "")
    subject = headers.get("subject", "")
    message_id = headers.get("message-id", "")

    # Ensure subject has Re: prefix
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    sender_info = parse_sender(sender)

    mime = MIMEText(body)
    mime["to"] = sender_info["email"]
    mime["subject"] = subject
    if cc:
        mime["cc"] = cc
    if message_id:
        mime["In-Reply-To"] = message_id
        mime["References"] = message_id

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": thread_id})
        .execute()
    )
    logger.info("Replied to thread %s — message ID: %s", thread_id, sent.get("id"))
    return sent


def send_email(service, to: str, subject: str, body: str, thread_id: str = None, cc: str = None):
    """Send a new email or within a thread, optionally CC'ing someone."""
    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject
    if cc:
        mime["cc"] = cc

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
    message_body = {"raw": raw}
    if thread_id:
        message_body["threadId"] = thread_id

    sent = service.users().messages().send(userId="me", body=message_body).execute()
    logger.info("Sent email to %s — message ID: %s", to, sent.get("id"))
    return sent


def get_history(service, start_history_id: str, label_id: str) -> list[dict]:
    """Fetch Gmail history since a given historyId, filtered by label."""
    messages = []
    page_token = None

    while True:
        kwargs = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "historyTypes": ["messageAdded"],
            "labelId": label_id,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().history().list(**kwargs).execute()

        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                msg = added.get("message", {})
                label_ids = msg.get("labelIds", [])
                if label_id in label_ids:
                    messages.append(msg)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return messages


def get_inbox_history(service, start_history_id: str) -> list[dict]:
    """Fetch Gmail history since a given historyId for all INBOX messages."""
    messages = []
    page_token = None

    while True:
        kwargs = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "historyTypes": ["messageAdded"],
            "labelId": "INBOX",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().history().list(**kwargs).execute()

        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                msg = added.get("message", {})
                label_ids = msg.get("labelIds", [])
                if "INBOX" in label_ids:
                    messages.append(msg)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return messages
