import os
import io
import json
import pytesseract
from PIL import Image
import cohere

co = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))

EXTRACTION_PROMPT = """You are an expense receipt parser. Below is raw OCR text extracted from a photo of a receipt.
Extract these fields as strict JSON, no markdown, no commentary:
{{
  "vendor": "<merchant/business name>",
  "amount": <number, total amount paid, no currency symbol>,
  "currency": "<3-letter currency code if visible, else best guess e.g. AED>",
  "date": "<date on receipt in YYYY-MM-DD, else null>",
  "category_guess": "<one of: food, travel, parking, accommodation, misc>",
  "payment_method_guess": "<one of: card, cash, personal -- infer from receipt text: look for words like VISA/MASTERCARD/credit/debit card -> 'card', explicit cash payment -> 'cash', otherwise default to 'personal'>"
}}

If a field is unreadable, make your best reasonable estimate rather than leaving it null, except date which can be null.

OCR TEXT:
---
{ocr_text}
---

Respond with ONLY the JSON object."""


def extract_text_from_image(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(img)
    return text.strip()


def parse_receipt_fields(ocr_text: str) -> dict:
    if not ocr_text:
        ocr_text = "(no text could be read from the image)"

    resp = co.chat(
        model="command-r-plus-08-2024",
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(ocr_text=ocr_text)}],
    )
    raw = resp.message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "vendor": "Unknown",
            "amount": 0,
            "currency": "AED",
            "date": None,
            "category_guess": "misc",
            "payment_method_guess": "personal",
        }
    # safety defaults
    data.setdefault("vendor", "Unknown")
    data.setdefault("amount", 0)
    data.setdefault("currency", "AED")
    data.setdefault("date", None)
    data.setdefault("category_guess", "misc")
    data.setdefault("payment_method_guess", "personal")
    return data