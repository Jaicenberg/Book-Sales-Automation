# Book Sending Automation

Automates the book order fulfillment pipeline: monitors Gmail for orders, parses customer details with Claude, places author copy orders on Amazon KDP via Playwright, sends confirmations, and logs everything to Google Sheets.

## Architecture

```
Gmail (label: "book sales")
        │
        ▼
Gmail API watch() ──► Google Cloud Pub/Sub
                              │
                              ▼ (pull subscription)
                     ┌────────────────────┐
                     │  Main Worker       │
                     │  (Python daemon)   │
                     └────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      Email Parser     KDP Automator    Notification
      (Claude API)     (Playwright)     (Gmail API)
              │               │               │
              ▼               ▼               ▼
           SQLite DB    KDP Website     Google Sheets
           (state)      (order placed)  (logging)
```

## Prerequisites

- Python 3.11+
- Google Cloud project with enabled APIs
- Google Workspace account (for domain-wide delegation)
- Amazon KDP account with TOTP 2FA
- Anthropic API key

## Google Cloud Setup

### 1. Create GCP project
```bash
gcloud projects create book-automation --name="Book Automation"
gcloud config set project book-automation
```

### 2. Enable APIs
```bash
gcloud services enable gmail.googleapis.com
gcloud services enable pubsub.googleapis.com
gcloud services enable sheets.googleapis.com
```

### 3. Create Pub/Sub topic and subscription
```bash
# Create topic
gcloud pubsub topics create gmail-book-orders

# Grant Gmail permission to publish
gcloud pubsub topics add-iam-policy-binding gmail-book-orders \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

# Create pull subscription
gcloud pubsub subscriptions create gmail-book-orders-sub \
  --topic=gmail-book-orders \
  --ack-deadline=60
```

### 4. Create service account
```bash
gcloud iam service-accounts create book-automation \
  --display-name="Book Automation Service Account"

gcloud iam service-accounts keys create service-account-key.json \
  --iam-account=book-automation@book-automation.iam.gserviceaccount.com

# Grant Pub/Sub subscriber role
gcloud projects add-iam-policy-binding book-automation \
  --member="serviceAccount:book-automation@book-automation.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"
```

### 5. Configure domain-wide delegation (Google Workspace)
1. Go to Google Workspace Admin Console → Security → API Controls → Domain-wide Delegation
2. Add the service account client ID
3. Authorize scopes:
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/spreadsheets`
   - `https://www.googleapis.com/auth/pubsub`

### 6. Create Gmail label
In Gmail, create a label called "book sales" and set up a filter to auto-label incoming book order emails.

## Installation

```bash
cd book-automation
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Configuration

```bash
cp .env.example .env
# Edit .env with your credentials
```

Key environment variables:
- `GCP_PROJECT_ID` — Your Google Cloud project ID
- `GCP_SERVICE_ACCOUNT_KEY_PATH` — Path to service account JSON key
- `GMAIL_USER_EMAIL` — Gmail address to monitor
- `ANTHROPIC_API_KEY` — Claude API key for email parsing
- `KDP_EMAIL` / `KDP_PASSWORD` / `KDP_TOTP_SECRET` — Amazon KDP credentials
- `GOOGLE_SHEET_ID` — Google Sheet for order logging
- `DRY_RUN=true` — Set to `false` to actually submit KDP orders

## Usage

```bash
# Start the automation (Pub/Sub listener + dashboard)
python main.py
```

The dashboard will be available at `http://localhost:5000` (default credentials in `.env`).

## Order Flow

1. **received** — New email detected in "book sales" label
2. **parsing** — Claude API extracts customer details from email thread
3. **awaiting_info** — Missing fields → auto-reply requesting details
4. **validated** — All required fields present
5. **shipping** — Playwright placing KDP author copy order
6. **shipped** — Order placed, delivery estimate captured
7. **notified** — Confirmation email sent to customer
8. **logged** — Order data written to Google Sheet

## Deployment (GCE VM)

### Systemd service files

**`/etc/systemd/system/book-worker.service`**
```ini
[Unit]
Description=Book Order Automation Worker
After=network.target

[Service]
Type=simple
User=book-automation
WorkingDirectory=/opt/book-automation
ExecStart=/opt/book-automation/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/book-automation/.env

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/book-dashboard.service`**
```ini
[Unit]
Description=Book Order Dashboard
After=network.target

[Service]
Type=simple
User=book-automation
WorkingDirectory=/opt/book-automation
ExecStart=/opt/book-automation/venv/bin/gunicorn --bind 0.0.0.0:5000 dashboard.app:app
Restart=always
RestartSec=10
EnvironmentFile=/opt/book-automation/.env

[Install]
WantedBy=multi-user.target
```

### Enable and start
```bash
sudo systemctl enable book-worker book-dashboard
sudo systemctl start book-worker book-dashboard
```

## Safety

- **DRY_RUN mode**: Set `DRY_RUN=true` to test the full pipeline without submitting KDP orders
- **Idempotency**: Orders are keyed by Gmail thread ID — re-processing the same thread resumes from the current state
- **Error handling**: Failed orders are marked as `error` and visible on the dashboard with retry capability
- **Screenshots**: On KDP automation failure, screenshots are saved to `./screenshots/` for debugging
