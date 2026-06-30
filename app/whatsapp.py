
import os
import httpx

BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://localhost:3000")


async def _send(to: str, text: str):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BRIDGE_URL}/send", json={"to": to, "text": text})
        if r.status_code >= 300:
            print("WA BRIDGE SEND ERROR:", r.status_code, r.text)
        return r.json()


async def send_text(to: str, body: str):
    return await _send(to, body)


async def send_buttons(to: str, body: str, buttons: list[tuple[str, str]]):
    """
    Baileys real buttons are unreliable / deprecated on recent WhatsApp versions.
    Flatten to a numbered text list instead — user replies with the number,
    main.py's button_id resolution below maps it back.
    """
    lines = [body, ""]
    for i, (bid, title) in enumerate(buttons, start=1):
        lines.append(f"{i}. {title}")
    lines.append("\nReply with the number of your choice.")
    return await _send(to, "\n".join(lines))


async def send_list(to: str, body: str, button_text: str, rows: list[tuple[str, str]]):
    lines = [body, ""]
    for i, (rid, title) in enumerate(rows, start=1):
        lines.append(f"{i}. {title}")
    lines.append("\nReply with the number of your choice.")
    return await _send(to, "\n".join(lines))


# Media is forwarded already-downloaded (as base64) by the Node bridge,
# so these two are no-ops kept only for main.py's interface compatibility.
async def get_media_url(media_id: str) -> str:
    return media_id  # unused in the bridge flow


async def download_media(url: str) -> bytes:
    raise NotImplementedError("Not used with the Baileys bridge — image bytes arrive inline.")
