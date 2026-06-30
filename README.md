cat > /home/claude/novabuddy/README.md << 'EOF'
# NovaBuddy Expense Management -- WhatsApp POC

A working proof of concept for an AI-powered expense management flow over
WhatsApp: an employee submits a receipt photo, AI (Tesseract OCR + Cohere)
extracts the data, the employee reviews/edits it, and a manager approves or
rejects it -- all inside a WhatsApp conversation.

## How it connects to WhatsApp

This uses **Baileys**, an unofficial WhatsApp Web automation library, instead
of Meta's official Cloud API. No business verification needed -- you scan a
QR code with a spare WhatsApp number and you're live in minutes.

**Read this first:** this connects via WhatsApp's unofficial web protocol,
which violates WhatsApp's Terms of Service. There's a real risk of the
connected number getting banned (commonly cited as roughly 2-8 weeks of
safe-ish use before detection, though it varies). Use a spare/secondary
number you don't mind losing -- not your primary personal WhatsApp. This is
meant as a fast way to get working demo footage; for a production product,
migrate to Meta's official Cloud API (this requires Meta Business
verification, which is a separate, slower process).

## Architecture

```
WhatsApp (real, via Baileys)
        |
        v
whatsapp-bridge/index.js (Node)  <-- QR-code login, holds the WA connection
        |  forwards incoming msgs as JSON
        v
FastAPI /wa-bridge/incoming (Python)  --> state machine --> OCR --> Cohere
        |  calls back out
        v
whatsapp-bridge POST /send (or /send-buttons)  -->  WhatsApp
```

Menus with 3 or fewer options (payment method, currency, manager
approve/reject) attempt real native WhatsApp buttons first. Menus with more
than 3 options (main menu, expense category) use a numbered text list
instead, since native lists/buttons are frequently flattened to plain text by
WhatsApp's servers for non-Business-verified senders -- this is a WhatsApp
policy limitation, not something fixable in code. If native buttons don't
render on your account, the numbered-text fallback is fully functional and
proven to work end to end.

## 1. Install the bridge

```bash
cd whatsapp-bridge
npm install
node index.js
```

A QR code prints in your terminal. Open WhatsApp on your **spare** phone/number
-> Settings -> Linked Devices -> Link a Device -> scan it. Once linked, you'll
see "WhatsApp bridge connected." in the terminal -- leave this running.

Your `auth_info/` folder (created automatically) stores the session so you
don't need to re-scan every restart, unless you get logged out.

## 2. Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Make sure Tesseract OCR is installed separately (not a pip package):
`brew install tesseract` (Mac) or `sudo apt install tesseract-ocr` (Ubuntu).

## 3. Set up `.env`

```bash
cp .env.example .env
```

Fill in:
```
COHERE_API_KEY=your_cohere_key
COHERE_MODEL=command-r-plus-08-2024
WA_BRIDGE_URL=http://localhost:3000
MANAGER_WHATSAPP_NUMBER=971XXXXXXXXX
```

`MANAGER_WHATSAPP_NUMBER` is raw digits only -- no `+`, no `whatsapp:` prefix.
Get a free Cohere trial key at https://dashboard.cohere.com/api-keys.

## 4. Run the FastAPI app

```bash
source venv/bin/activate
python3 -m uvicorn app.main:app --reload --port 8000
```

## 5. Test it

You'll want three phone numbers total: the one linked in step 1 (the "bot"),
an "employee" number, and the manager number set in `.env`. From the employee
number, message the linked number: "hi". You should get the main menu as a
numbered list. Pick Expense Submission, send a photo of any receipt, and walk
through review/edit -> payment method -> currency -> category -> description
-> submit. The manager number receives an approval card automatically;
approving or rejecting notifies the employee.

No ngrok, no webhook config, no Meta dashboard needed -- the bridge and
FastAPI both run locally and talk to each other directly over HTTP.

## What's stubbed vs production-real

In-memory state (resets on restart, no database), no real ERP integration,
single hardcoded manager (no org chart / multi-level approval). OCR
(Tesseract) and the Cohere field-extraction step are fully real, not mocked.

## Project structure

```
app/
  main.py        -- FastAPI app, conversation state machine
  whatsapp.py     -- send helper, talks to the Node bridge
  ocr.py          -- Tesseract OCR + Cohere field extraction
  state.py        -- in-memory session/approval store, manager number config
whatsapp-bridge/
  index.js        -- Baileys connection, forwards messages to/from FastAPI
requirements.txt
.env.example
```
