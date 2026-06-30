# Expense Management -- WhatsApp POC (Baileys bridge / unofficial WhatsApp)

This version uses **Baileys** (an unofficial WhatsApp Web automation library)
instead of Meta's official Cloud API. No business verification needed -- you
scan a QR code with a spare WhatsApp number and you're live in minutes.

**Read this first:** this connects via WhatsApp's unofficial web protocol, which
violates WhatsApp's Terms of Service. Risk of the connected number getting
banned is real (commonly cited as 2-8 weeks of safe-ish use before detection,
though it varies). Use a spare/secondary number you don't mind losing -- not
your primary personal WhatsApp. This is meant strictly as a fast way to record
working demo footage for your ad; for the real product you'll want to migrate
to Meta's official Cloud API (instructions for that are in the git history /
ask me to bring that version back).

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
whatsapp-bridge POST /send  -->  WhatsApp
```

Buttons/lists are sent as plain numbered text (e.g. "1. Food\n2. Travel...")
since Baileys' native interactive-button support is unreliable across WhatsApp
client versions -- the user just replies with the number.

## 1. Install the bridge

Open your **first terminal** and run:

```bash
cd whatsapp-bridge
npm install
node index.js
```

A QR code will print in your terminal. Open WhatsApp on your **spare** phone/number
-> Settings -> Linked Devices -> Link a Device -> scan it. Once linked, you'll see
"WhatsApp bridge connected." in the terminal -- leave this terminal running.

Your `auth_info/` folder (created automatically) stores the session so you don't
need to re-scan every restart, unless you get logged out.

## 2. Set the manager's number

In `app/state.py`:

```python
MANAGER_WHATSAPP_NUMBER = "971xxxxxxx"  # raw digits, no + or whatsapp: prefix
```

Use a second spare number here, separate from the one linked in step 1.

## 3. Get a Cohere key

https://dashboard.cohere.com/api-keys -- free trial key works.

## 4. Fill in `.env`

```
COHERE_API_KEY=your_key_here
WA_BRIDGE_URL=http://localhost:3000
```

(You can delete the old WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID /
WHATSAPP_VERIFY_TOKEN lines -- not used in this version.)

## 5. Run the Python app

Open a **second terminal** and navigate to the project root.

Create a virtual environment (if you haven't already):

```bash
python -m venv venv
```

Activate it:

**macOS / Linux**

```bash
source venv/bin/activate
```

**Windows (Command Prompt)**

```cmd
venv\Scripts\activate
```

**Windows (PowerShell)**

```powershell
venv\Scripts\Activate.ps1
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Run the FastAPI application:

```bash
python3 -m uvicorn app.main:app --reload --port 8000
```

Make sure tesseract is installed on your machine (`brew install tesseract` /
`sudo apt install tesseract-ocr`).

## 6. Test it

To test the application, keep **both terminals running**:

* **Terminal 1:** `cd whatsapp-bridge` → `node index.js`
* **Terminal 2:** FastAPI backend running with `python3 -m uvicorn app.main:app --reload --port 8000`

From a **third** WhatsApp number (the "employee"), message the number you linked
in step 1: send "hi". You should get the menu back as a numbered list. Reply
with a number, send a receipt photo when prompted, and walk through the flow.
The manager number gets the approval card automatically; replying with the
approve/reject number notifies the employee.

No ngrok, no webhook config, no Meta dashboard needed for this version -- the
bridge and FastAPI both run locally and talk to each other directly.
