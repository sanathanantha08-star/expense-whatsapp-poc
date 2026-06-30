
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  downloadMediaMessage,
} = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const express = require("express");
const axios = require("axios");
const pino = require("pino");

const FASTAPI_URL = process.env.FASTAPI_URL || "http://localhost:8000";
const BRIDGE_PORT = process.env.BRIDGE_PORT || 3000;

let sock; // current Baileys socket, set after connection

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");

  sock = makeWASocket({
    auth: state,
    logger: pino({ level: "silent" }), // set to "info" to debug connection issues
    printQRInTerminal: false, // we handle QR display ourselves below
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\nScan this QR code with WhatsApp > Linked Devices:\n");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      const shouldReconnect =
        lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log("Connection closed.", shouldReconnect ? "Reconnecting..." : "Logged out — delete auth_info/ and re-scan.");
      if (shouldReconnect) startSock();
    } else if (connection === "open") {
      console.log("✅ WhatsApp bridge connected.");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    console.log(`\n--- messages.upsert fired, type=${type}, count=${messages.length} ---`);

    for (const msg of messages) {
      console.log("raw msg.key:", JSON.stringify(msg.key));
      console.log("raw msg.message keys:", msg.message ? Object.keys(msg.message) : "NO MESSAGE OBJECT");

      if (!msg.message) {
        console.log("Skipping: no message content (likely a protocol/status message)");
        continue;
      }
      if (msg.key.fromMe) {
        console.log("Skipping: message is from ourselves (fromMe=true)");
        continue;
      }

      // WhatsApp's privacy "LID" addressing can put a non-phone-number ID in
      // remoteJid (e.g. "277004016439542@lid"); the real phone number, when
      // available, is in remoteJidAlt instead. Prefer that.
      const from = msg.key.remoteJidAlt || msg.key.remoteJid;
      const phone = from.split("@")[0];

      let payload = { from: phone, type: "text", text: "" };

      if (msg.message.conversation) {
        payload.text = msg.message.conversation;
      } else if (msg.message.extendedTextMessage?.text) {
        payload.text = msg.message.extendedTextMessage.text;
      } else if (msg.message.imageMessage) {
        const buffer = await downloadMediaMessage(msg, "buffer", {});
        payload.type = "image";
        payload.image_base64 = buffer.toString("base64");
        payload.caption = msg.message.imageMessage.caption || "";
      } else {
        console.log("Skipping: unrecognized message type, keys were:", Object.keys(msg.message));
        continue;
      }

      console.log("Forwarding payload to FastAPI:", JSON.stringify({ ...payload, image_base64: payload.image_base64 ? "[omitted]" : undefined }));

      try {
        const resp = await axios.post(`${FASTAPI_URL}/wa-bridge/incoming`, payload);
        console.log("FastAPI responded:", resp.status, resp.data);
      } catch (err) {
        console.error("Failed to forward message to FastAPI:", err.message);
        if (err.response) {
          console.error("FastAPI error response:", err.response.status, err.response.data);
        }
      }
    }
  });
}

startSock();


const app = express();
app.use(express.json({ limit: "10mb" }));

app.post("/send", async (req, res) => {
  try {
    const { to, text } = req.body;
    if (!sock) return res.status(503).json({ error: "WhatsApp not connected yet" });

    const jid = to.includes("@") ? to : `${to}@s.whatsapp.net`;
    await sock.sendMessage(jid, { text });
    res.json({ status: "sent" });
  } catch (err) {
    console.error("Send error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

app.listen(BRIDGE_PORT, () => {
  console.log(`WhatsApp bridge HTTP server listening on port ${BRIDGE_PORT}`);
});