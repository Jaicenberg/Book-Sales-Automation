# Book Sales Automation -- User Guide

**For: Ash (ash@nickgray.net) and Nick Gray**
**Book: "The 2-Hour Cocktail Party"**

---

## Table of Contents

1. [Overview -- How It Works](#1-overview----how-it-works)
2. [Prerequisites -- What Needs To Be Set Up](#2-prerequisites----what-needs-to-be-set-up)
3. [Configuration -- The .env File](#3-configuration----the-env-file)
4. [Running the System](#4-running-the-system)
5. [Day-to-Day Usage](#5-day-to-day-usage)
6. [Troubleshooting](#6-troubleshooting)
7. [The Dashboard](#7-the-dashboard)

---

## 1. Overview -- How It Works

This system automates the entire process of fulfilling book orders for "The 2-Hour Cocktail Party." Here is what happens, step by step:

```
Nick emails a client and CCs Ash
        |
        v
Gmail filter catches the phrase "send you a free book copy"
and auto-applies the "Book Sales" label
        |
        v
The automation detects the new labeled email
        |
        v
Claude AI reads the email and extracts:
  - Client name
  - Phone number
  - Shipping address
        |
        v
  Is anything missing?
   /            \
  YES            NO
  |               |
  v               v
Ash's account    Ash's account places a
sends a reply    KDP author copy order on
asking for the   Amazon, then sends a
missing info     confirmation email to
(Nick is CC'd)   the client (Nick is CC'd)
  |               |
  |               v
  |          Order is logged to
  |          Google Sheets
  |          (monthly tab, e.g. "February 2026")
  |
  v
When the client replies with the missing info,
the email lands in the same thread (same label),
the system picks it up again and completes the order.
```

**Key points:**
- All emails are sent from Ash's account (ash@nickgray.net).
- Nick (nick@nickgray.net) is CC'd on every reply the system sends.
- Each order is tracked by its Gmail thread ID, so the same order is never processed twice.
- The Google Sheet has a new tab created automatically for each month (e.g., "February 2026", "March 2026").

---

## 2. Prerequisites -- What Needs To Be Set Up

Before the system can run, the following things need to be in place. (Most of this is a one-time setup.)

### A. Google Cloud Project

A Google Cloud Platform (GCP) project is required. It provides:
- **Gmail API** -- so the system can read and send emails as Ash.
- **Google Sheets API** -- so orders can be logged to the spreadsheet.
- **Pub/Sub** -- so the system gets notified instantly when a new "Book Sales" email arrives.

What needs to exist in GCP:
1. A project (e.g., `book-sales-automation`).
2. Three APIs enabled: Gmail, Sheets, and Pub/Sub.
3. A **Pub/Sub topic** named `gmail-book-orders`.
4. A **Pub/Sub pull subscription** named `gmail-book-orders-sub`.
5. A **service account** with a downloaded JSON key file (this file goes in the project folder).
6. **Domain-wide delegation** configured in Google Workspace Admin so the service account can act as Ash.

The authorized scopes for domain-wide delegation are:
- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/spreadsheets`
- `https://www.googleapis.com/auth/pubsub`

### B. Gmail Label and Filter

In Ash's Gmail (ash@nickgray.net):

1. **Create a label** called `Book Sales` (case does not matter, but "Book Sales" is the default).
2. **Create a filter** with this setup:
   - Has the words: `send you a free book copy`
   - Action: Apply label "Book Sales"

This filter is what triggers the entire automation. When Nick sends a client an email containing that phrase and CCs Ash, the filter labels it, and the system picks it up.

### C. Google Sheet

A Google Sheet is used to log all orders. The current sheet ID is `1jJ2jqHOwPUGuO1nQGL32SPj_jROdyeLSc77nqFIL9XU`.

**Important:** The Google Sheet must be shared (Editor access) with the service account email address. The service account email looks like:
```
book-automation@book-sales-automation.iam.gserviceaccount.com
```
(The exact address is in your service account JSON key file, under `client_email`.)

The system automatically creates a new tab each month (e.g., "February 2026") with these columns:

| Column | Description |
|--------|-------------|
| NAME | Client's full name |
| EMAIL ADDRESS | Client's email |
| PHONE # | Client's phone number |
| NO. OF COPIES | Number of books ordered (usually 1) |
| CONFIRMATION SENT? | "Yes" after the confirmation email is sent |
| AMAZON STATUS | "Ordered" when the KDP order is placed |
| RECEIVED BY RECIPIENT | Filled in manually later if needed |
| PAYMENT METHOD | How the client paid (Venmo, PayPal, etc.) |
| ADDRESS | Shipping address |
| ESTIMATED DELIVERY DATE | From the KDP order confirmation |
| SOURCE | How the sale originated (e.g., "direct email") |
| THREAD_ID | Internal Gmail thread ID (used for deduplication) |

### D. Amazon KDP Account

The system logs into Amazon KDP (Kindle Direct Publishing) to place author copy orders. It needs:
- The KDP login email
- The KDP password
- The TOTP secret for two-factor authentication (the base32 secret from your authenticator app setup)

### E. Anthropic (Claude) API Key

An API key from Anthropic is needed so Claude AI can read and understand the emails. You can get one at https://console.anthropic.com/.

### F. Software Requirements

- Python 3.11 or newer
- Chromium browser (installed automatically via Playwright -- see "Running the System" below)

---

## 3. Configuration -- The .env File

All settings live in a file called `.env` in the project folder. A template is provided in `.env.example`.

To set up: copy `.env.example` to `.env`, then fill in the values.

Here is what each variable does:

### Required Variables

| Variable | What It Does | Example |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | Your Google Cloud project ID | `book-sales-automation` |
| `GCP_SERVICE_ACCOUNT_KEY_PATH` | Path to the service account JSON key file | `./service-account.json` |
| `GMAIL_USER_EMAIL` | The Gmail address the system operates as | `ash@nickgray.net` |
| `ANTHROPIC_API_KEY` | Your Claude API key | `sk-ant-...` |
| `KDP_EMAIL` | Amazon KDP login email | `ash@nickgray.net` |
| `KDP_PASSWORD` | Amazon KDP login password | (your password) |
| `KDP_TOTP_SECRET` | The TOTP base32 secret for KDP 2FA | (your TOTP secret) |
| `DASHBOARD_PASSWORD` | Password for the web dashboard | (choose something strong) |

### Optional Variables (defaults are fine for most setups)

| Variable | Default | What It Does |
|----------|---------|-------------|
| `PUBSUB_TOPIC` | `gmail-book-orders` | Name of the Pub/Sub topic |
| `PUBSUB_SUBSCRIPTION` | `gmail-book-orders-sub` | Name of the Pub/Sub subscription |
| `GMAIL_LABEL_NAME` | `Book Sales` | The Gmail label to watch |
| `GOOGLE_SHEET_ID` | (Nick's sheet) | The ID of the Google Sheet for logging |
| `NICK_EMAIL` | `nick@nickgray.net` | Nick's email (CC'd on all replies) |
| `ASH_SENDER_NAME` | `Ash Smith` | The name used in email signatures |
| `KDP_GIFT_MESSAGE` | (a default message from Nick) | The gift message included with KDP orders |
| `DASHBOARD_USERNAME` | `admin` | Username for the web dashboard |
| `DASHBOARD_PORT` | `5000` | Port the dashboard runs on |
| `DRY_RUN` | `true` | When `true`, orders are simulated (not actually placed on Amazon) |
| `LOG_LEVEL` | `INFO` | How much detail to show in logs (`DEBUG` for maximum detail) |
| `SCREENSHOTS_DIR` | `./screenshots` | Where KDP browser screenshots are saved |
| `STATE_FILE` | `./state.json` | File that tracks the last processed Gmail history ID |

---

## 4. Running the System

### Step 1: Install dependencies (one-time)

Open a terminal in the project folder and run:

```bash
python -m venv venv
venv\Scripts\activate          # On Windows
# source venv/bin/activate     # On Mac/Linux

pip install -r requirements.txt
playwright install chromium
```

### Step 2: Run the dry run first

**Always do this first before going live.** The dry run simulates the entire pipeline with fake data -- no API keys needed, no real emails sent, no real orders placed.

```bash
python dry_run.py
```

This will show you three scenarios:
1. **Complete** -- A client with all info (name, phone, address). The system places the order and sends a confirmation.
2. **Missing** -- A client missing phone and address. The system sends a reply asking for the missing info.
3. **Duplicate** -- A thread that was already processed. The system skips it.

You can also run a specific scenario:
```bash
python dry_run.py --scenario complete
python dry_run.py --scenario missing
python dry_run.py --scenario duplicate
```

If everything looks right in the dry run output, you are ready to go live.

### Step 3: Go live

1. Open `.env` and set:
   ```
   DRY_RUN=false
   ```

2. Make sure all required variables are filled in (see Section 3 above).

3. Start the system:
   ```bash
   python main.py
   ```

When the system starts, it will:
- Validate all settings (and tell you if anything is missing).
- Register a Gmail "watch" on the "Book Sales" label (renewed automatically every 24 hours).
- Start the web dashboard in the background.
- Begin listening for new emails via Pub/Sub (this runs continuously).

**Leave the terminal open.** The system runs as long as the terminal is open. For a more permanent setup (e.g., on a server), see the deployment section in README.md.

### Step 4: Verify it is working

- Check the terminal for log messages. You should see:
  ```
  Starting Book Sending Automation
  Watch renewed -- historyId: ...
  Dashboard started in background thread
  Starting Pub/Sub listener (watching 'Book Sales' label only)
  ```
- Open the dashboard at `http://localhost:5000` (login with the credentials from `.env`).
- Have Nick send a test email to a test address, CC'ing Ash, with the trigger phrase.

---

## 5. Day-to-Day Usage

### For Nick

Just keep doing what you already do:

1. Email the client about the book.
2. Include the phrase **"send you a free book copy"** somewhere in the email (this is what triggers the Gmail filter).
3. CC **ash@nickgray.net** on the email.

That is it. The system handles everything from there.

Nick can also use **hello@nickgray.net** -- as long as Ash is CC'd, the filter will catch it.

### For Ash

**Most of the time, you do not need to do anything.** The system runs automatically.

Here is what happens behind the scenes after Nick sends a book sale email:

1. The Gmail filter applies the "Book Sales" label.
2. The system picks it up within seconds.
3. Claude AI reads the email and pulls out the client's name, phone, and shipping address.
4. **If info is missing:** The system sends a reply from your account asking the client for the missing details. Nick is CC'd. When the client replies, the system picks up the reply (same thread, same label) and tries again.
5. **If all info is present:** The system places an author copy order on Amazon KDP, sends a confirmation email to the client (from your account, Nick CC'd), and logs everything to the Google Sheet.

### What you might need to do manually

- **Check the Google Sheet** periodically to see orders and update the "RECEIVED BY RECIPIENT" column when clients confirm receipt.
- **Check the dashboard** at `http://localhost:5000` for a quick overview of current orders.
- **Handle edge cases** -- if Claude cannot parse an email (rare), it will be flagged in the logs. You may need to manually process those.
- **If the system stops** (computer restart, crash, etc.), just run `python main.py` again. It will pick up where it left off.

### What if I need to manually label an email?

If an email does not get auto-labeled by the filter (maybe it did not contain the exact trigger phrase), you can manually apply the "Book Sales" label in Gmail. The system will pick it up on the next check.

---

## 6. Troubleshooting

### "Missing required environment variables" error on startup

The system checks that all required settings are present. Open your `.env` file and make sure these are filled in:
- `GCP_PROJECT_ID`
- `GCP_SERVICE_ACCOUNT_KEY_PATH`
- `GMAIL_USER_EMAIL`
- `ANTHROPIC_API_KEY`
- `KDP_EMAIL`
- `KDP_PASSWORD`
- `KDP_TOTP_SECRET`

### "Service account key file not found" error

The JSON key file path in `GCP_SERVICE_ACCOUNT_KEY_PATH` does not point to a real file. Make sure the file exists in the project folder and the path in `.env` is correct.

### "Gmail label 'Book Sales' not found"

The label does not exist in Ash's Gmail. Go to Gmail, create a label called "Book Sales" (Settings > Labels > Create new label).

### Emails are not being picked up

1. **Check the Gmail filter.** Go to Ash's Gmail > Settings > Filters and Blocked Addresses. Make sure there is a filter that applies the "Book Sales" label to emails containing "send you a free book copy."
2. **Check the Pub/Sub subscription.** In the Google Cloud Console, go to Pub/Sub > Subscriptions and verify `gmail-book-orders-sub` exists and is not stuck.
3. **Check the logs.** Look at the terminal where `main.py` is running for error messages.
4. **Restart the system.** Stop the process (Ctrl+C) and run `python main.py` again.

### KDP order failed

If the Amazon KDP order fails (login issues, page changes, etc.):
- Check the `screenshots/` folder -- the system saves screenshots on failure so you can see what went wrong.
- Make sure `KDP_TOTP_SECRET` is correct (the TOTP code must work).
- Try logging into KDP manually to confirm the credentials work.
- If Amazon changed their website layout, the automation may need updating (contact your developer).

### "Failed to parse Claude response"

Claude could not extract order info from the email. This can happen with unusual email formatting. Check the logs for details, and if needed, manually process the order and add it to the Google Sheet.

### The dashboard is not loading

- Make sure the system is running (`python main.py`).
- Check that nothing else is using port 5000 (or change `DASHBOARD_PORT` in `.env`).
- Try opening `http://localhost:5000` in your browser.
- The login credentials are the `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` from `.env`.

### An order was processed twice

This should not happen -- the system checks the Google Sheet for duplicate thread IDs before processing. If it does happen, delete the duplicate row from the Google Sheet. The `THREAD_ID` column helps identify duplicates.

### The system stopped or crashed

Just run `python main.py` again. The system saves its last known state in `state.json`, so it will resume from where it left off. No orders will be lost or duplicated.

---

## 7. The Dashboard

The system includes a simple web dashboard that shows all orders for the current month.

### How to access it

1. Open your browser and go to: `http://localhost:5000`
   (If the system is running on a server, replace `localhost` with the server's address.)

2. Enter the login credentials:
   - **Username:** The value of `DASHBOARD_USERNAME` in `.env` (default: `admin`)
   - **Password:** The value of `DASHBOARD_PASSWORD` in `.env`

### What you see

The dashboard shows a table with all orders from the current month's Google Sheet tab. Each row includes:

| Column | What It Shows |
|--------|--------------|
| Name | Client's full name |
| Email | Client's email address |
| Phone | Client's phone number |
| Copies | Number of books ordered |
| Confirmed | Whether a confirmation email was sent (green = Yes) |
| Amazon Status | "Ordered" (blue), "Delivered" (green), or "Pending" (yellow) |
| Received | Whether the client confirmed receipt |
| Payment | How they paid |
| Address | Shipping address |
| Est. Delivery | Estimated delivery date from Amazon |
| Source | How the sale originated |

### Color-coded status badges

The dashboard uses color-coded badges to make it easy to scan:
- **Green** -- Confirmed, Delivered, Received
- **Blue** -- Ordered
- **Yellow/Orange** -- Pending, Awaiting info
- **Red** -- Error (needs attention)

### Refreshing data

The dashboard reads directly from the Google Sheet each time you load the page. Just refresh your browser to see the latest data.

---

## Quick Reference

| What | Where |
|------|-------|
| Nick's email | nick@nickgray.net (also hello@nickgray.net) |
| Ash's email (system sends from here) | ash@nickgray.net |
| Gmail trigger phrase | "send you a free book copy" |
| Gmail label | Book Sales |
| Google Sheet | [Open Sheet](https://docs.google.com/spreadsheets/d/1jJ2jqHOwPUGuO1nQGL32SPj_jROdyeLSc77nqFIL9XU) |
| Dashboard URL | http://localhost:5000 |
| Dashboard login | admin / (see DASHBOARD_PASSWORD in .env) |
| Start the system | `python main.py` |
| Dry run (test mode) | `python dry_run.py` |
| Stop the system | Press Ctrl+C in the terminal |
| Logs | Terminal output (or check LOG_LEVEL in .env) |
| KDP failure screenshots | `./screenshots/` folder |
