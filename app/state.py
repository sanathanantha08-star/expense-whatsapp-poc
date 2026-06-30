
from typing import Dict, Any
from datetime import datetime
import uuid

sessions: Dict[str, Dict[str, Any]] = {}

# Pending approvals, keyed by expense_id, so the manager's reply can be matched back
pending_approvals: Dict[str, Dict[str, Any]] = {}
import os

MANAGER_WHATSAPP_NUMBER = os.getenv("MANAGER_WHATSAPP_NUMBER", "971500000000")


def get_session(phone: str) -> Dict[str, Any]:
    if phone not in sessions:
        sessions[phone] = {"stage": "MENU", "expense": {}}
    return sessions[phone]


def reset_session(phone: str):
    sessions[phone] = {"stage": "MENU", "expense": {}}


def new_expense_id() -> str:
    return uuid.uuid4().hex[:8]


def create_pending_approval(employee_phone: str, expense: Dict[str, Any]) -> str:
    expense_id = new_expense_id()
    pending_approvals[expense_id] = {
        "employee_phone": employee_phone,
        "expense": expense,
        "status": "PENDING",
        "created_at": datetime.utcnow().isoformat(),
    }
    return expense_id
