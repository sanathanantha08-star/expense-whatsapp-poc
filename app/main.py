"""
NovaBuddy Expense Management POC -- Baileys bridge version.

Flow: employee texts WhatsApp -> menu -> expense submission -> photo of receipt
-> OCR + Cohere extraction -> review/edit -> payment method -> currency ->
category -> description -> submit -> manager gets approval card -> approve/reject
-> employee notified.

Since the Baileys bridge sends plain text (no native interactive buttons), all
menus are numbered text lists; the user replies with a number, and we resolve
it against session["last_options"] (the options shown in the most recent message).

Run: uvicorn app.main:app --reload --port 8000
Also run the bridge separately: cd whatsapp-bridge && node index.js
"""
import os
import base64
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import whatsapp, ocr
from app.state import (
    get_session,
    reset_session,
    create_pending_approval,
    pending_approvals,
    MANAGER_WHATSAPP_NUMBER,
)

app = FastAPI(title="NovaBuddy Expense POC (Baileys bridge)")

CATEGORIES = [("food", "Food"), ("travel", "Travel"), ("parking", "Parking"),
              ("accommodation", "Accommodation"), ("misc", "Misc")]
PAYMENT_METHODS = [("card", "Company Card"), ("cash", "Cash"), ("personal", "Personal (reimburse)")]
CURRENCIES = [("AED", "AED"), ("USD", "USD"), ("EUR", "EUR")]


def manager_number() -> str:
    return MANAGER_WHATSAPP_NUMBER.replace("whatsapp:", "").lstrip("+")


async def send_options(phone: str, body: str, options: list):
    session = get_session(phone)
    session["last_options"] = options
    await whatsapp.send_list(phone, body, "Select", options)


def resolve_choice(phone: str, payload_or_text):
    """Resolve a user's selection back to an option id. Accepts either the
    raw payload dict (preferred -- uses row_id from native list taps when
    present) or a plain text string (numeric/title fallback)."""
    session = get_session(phone)
    options = session.get("last_options") or []

    if isinstance(payload_or_text, dict):
        if payload_or_text.get("type") == "list_reply" and payload_or_text.get("row_id"):
            row_id = payload_or_text["row_id"]
            if any(opt_id == row_id for opt_id, _ in options):
                return row_id
        text_body = payload_or_text.get("text", "")
    else:
        text_body = payload_or_text

    text_body = text_body.strip()
    if text_body.isdigit():
        idx = int(text_body) - 1
        if 0 <= idx < len(options):
            return options[idx][0]
    for opt_id, title in options:
        if text_body.lower() == title.lower() or text_body.lower() == opt_id.lower():
            return opt_id
    return None


@app.post("/wa-bridge/incoming")
async def bridge_incoming(request: Request):
    payload = await request.json()
    phone = payload["from"]

    if phone == manager_number():
        await handle_manager_reply(payload, phone)
    else:
        await handle_employee_message(payload, phone)

    return JSONResponse({"status": "ok"})


async def handle_employee_message(payload: dict, phone: str):
    session = get_session(phone)
    stage = session["stage"]

    msg_type = payload.get("type")
    text_body = payload.get("text", "").strip() if msg_type == "text" else ""

    if text_body.lower() in ("hi", "hello", "menu", "start"):
        reset_session(phone)
        await send_main_menu(phone)
        return

    if stage == "MENU":
        choice = resolve_choice(phone, payload)
        if choice == "expense_submission":
            session["stage"] = "AWAITING_RECEIPT"
            await whatsapp.send_text(
                phone,
                "Please send a photo of only one receipt that you'd like to submit as an expense."
            )
        else:
            await send_main_menu(phone)
        return

    if stage == "AWAITING_RECEIPT":
        if msg_type == "image":
            await whatsapp.send_text(phone, "Receipt is being reviewed, please wait a moment...")
            image_bytes = base64.b64decode(payload["image_base64"])

            ocr_text = ocr.extract_text_from_image(image_bytes)
            extracted = ocr.parse_receipt_fields(ocr_text)
            session["expense"].update(extracted)
            # Auto-fill from AI extraction -- no manual selection needed
            session["expense"]["payment_method"] = extracted["payment_method_guess"]
            session["expense"]["category"] = extracted["category_guess"]
            # currency already set by extracted["currency"]
            session["stage"] = "REVIEW_EXTRACTED"

            summary = (
                "Values extracted from your receipt:\n\n"
                f"Vendor: {extracted['vendor']}\n"
                f"Amount: {extracted['amount']} {extracted['currency']}\n"
                f"Date: {extracted['date'] or 'not detected'}\n"
                f"Category: {extracted['category_guess']}\n"
                f"Payment method: {extracted['payment_method_guess']}\n\n"
                "Reply 1 to start expense submission."
            )
            await send_options(phone, summary, [("start_expense_submission", "Start Expense Submission")])
        else:
            await whatsapp.send_text(phone, "Please send a photo of the receipt (image only).")
        return

    if stage == "REVIEW_EXTRACTED":
        choice = resolve_choice(phone, payload)
        if choice == "start_expense_submission":
            session["stage"] = "EDIT_PROMPT"
            exp = session["expense"]
            await whatsapp.send_text(
                phone,
                "Edit extracted values (or reply 'ok' to keep as-is):\n\n"
                f"Vendor: {exp['vendor']}\n"
                f"Amount: {exp['amount']}\n"
                f"Currency: {exp['currency']}\n"
                f"Date: {exp['date'] or 'N/A'}\n"
                f"Category: {exp['category']}\n"
                f"Payment method: {exp['payment_method']}\n\n"
                "To edit, reply in this format:\n"
                "vendor=Starbucks; amount=45.5; date=2026-06-30; category=food; payment_method=cash\n"
                "(category options: food, travel, parking, accommodation, misc)\n"
                "(payment_method options: card, cash, personal)\n"
                "Or just reply ok to continue."
            )
        return

    if stage == "EDIT_PROMPT":
        if text_body.lower() != "ok":
            for pair in text_body.split(";"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    k, v = k.strip().lower(), v.strip()
                    if k in ("vendor", "amount", "currency", "date", "category", "payment_method"):
                        session["expense"][k] = v
        session["stage"] = "AWAITING_DESCRIPTION"
        await whatsapp.send_text(phone, "Finally, add a short description for this expense:")
        return

    if stage == "AWAITING_DESCRIPTION":
        session["expense"]["description"] = text_body
        session["stage"] = "SUBMITTED"
        exp = session["expense"]

        expense_id = create_pending_approval(phone, exp)

        await whatsapp.send_text(
            phone,
            f"Expense submitted! (ID: {expense_id})\n"
            f"You'll be notified once your manager reviews it.\n\n"
            "Reply hi to go back to the main menu."
        )

        manager_card = (
            "New Expense Approval Request\n\n"
            f"ID: {expense_id}\n"
            f"Employee: {phone}\n"
            f"Vendor: {exp['vendor']}\n"
            f"Amount: {exp['amount']} {exp['currency']}\n"
            f"Date: {exp.get('date') or 'N/A'}\n"
            f"Payment method: {exp.get('payment_method')}\n"
            f"Category: {exp.get('category')}\n"
            f"Description: {exp.get('description')}\n"
        )
        await send_options(
            manager_number(),
            manager_card,
            [(f"approve_{expense_id}", "Approve"), (f"reject_{expense_id}", "Reject")],
        )
        return


async def send_main_menu(phone: str):
    rows = [
        ("expense_submission", "Expense Submission"),
        ("download_expenses", "Download Expenses"),
        ("leave_submission", "Leave Submission"),
        ("download_leaves", "Download Leaves"),
        ("advance_request", "Advance Request"),
        ("reports", "Reports"),
    ]
    await send_options(phone, "Hi! What would you like to do?", rows)


async def handle_manager_reply(payload: dict, manager_phone: str):
    if payload.get("type") not in ("text", "list_reply"):
        return
    choice = resolve_choice(manager_phone, payload)
    if not choice:
        return

    action, expense_id = choice.split("_", 1)
    approval = pending_approvals.get(expense_id)
    if not approval:
        await whatsapp.send_text(manager_phone, "This expense request was not found (may be stale).")
        return

    employee_phone = approval["employee_phone"]
    exp = approval["expense"]

    if action == "approve":
        approval["status"] = "APPROVED"
        await whatsapp.send_text(manager_phone, f"You approved expense {expense_id}.")
        await whatsapp.send_text(
            employee_phone,
            f"Your expense ({exp['vendor']}, {exp['amount']} {exp['currency']}) was approved by your manager."
        )
    elif action == "reject":
        approval["status"] = "REJECTED"
        await whatsapp.send_text(manager_phone, f"You rejected expense {expense_id}.")
        await whatsapp.send_text(
            employee_phone,
            f"Your expense ({exp['vendor']}, {exp['amount']} {exp['currency']}) was rejected by your manager."
        )