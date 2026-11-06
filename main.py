#!/usr/bin/env python3
# Telegram configuration + read-only Firebase device viewer.
# No SMS sending and no remote device commands.

import json, os, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

CONFIG_FILE = Path.home() / ".sms_bot_config.json"
BOT_TOKEN = ""
OWNER_ID = None
OFFSET = 0

def load_config():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict): data = {}
    except Exception:
        data = {}
    data.setdefault("firebases", [])
    data.setdefault("channels", [])
    data.setdefault("active_firebase", 0)
    data.setdefault("active_channel", 0)
    data.setdefault("bot_token", "9111530542:AAFjCQK7I88o0dKpVKTxpqxk7d9Zl6IE7UM")
    data.setdefault("owner_id", "")
    return data

def save_config(data):
    CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try: os.chmod(CONFIG_FILE, 0o600)
    except OSError: pass

def setup_credentials():
    global BOT_TOKEN, OWNER_ID
    cfg = load_config()
    BOT_TOKEN = os.environ.get("9111530542:AAFjCQK7I88o0dKpVKTxpqxk7d9Zl6IE7UM", "").strip() or str(cfg.get("bot_token", "")).strip()
    if not BOT_TOKEN:
        BOT_TOKEN = input("Telegram bot token (saved locally): ").strip()
        if not BOT_TOKEN: raise SystemExit("Bot token required.")
        cfg["bot_token"] = BOT_TOKEN
    owner = os.environ.get("BOT_OWNER_ID", "").strip() or str(cfg.get("owner_id", "")).strip()
    if not owner:
        owner = input("Your Telegram numeric user ID (owner): ").strip()
        if not owner.isdigit(): raise SystemExit("Numeric owner ID required.")
        cfg["owner_id"] = owner
    if not owner.isdigit(): raise SystemExit("Invalid owner ID.")
    OWNER_ID = int(owner)
    save_config(cfg)

def telegram(method, params=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params or {}).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"): raise RuntimeError(result.get("description", "Telegram API error"))
    return result

def send(chat_id, message):
    telegram("sendMessage", {"chat_id": chat_id, "text": str(message)[:4000]})

def firebase_get(url, path):
    req = urllib.request.Request(url.rstrip("/") + "/" + path.lstrip("/") + ".json", method="GET")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))

def active_firebase(cfg):
    items = cfg["firebases"]
    if not items: return None
    idx = cfg.get("active_firebase", 0)
    if not isinstance(idx, int) or not 0 <= idx < len(items): idx = 0
    return items[idx]

def pair(text):
    parts = [x.strip() for x in text.split("|", 1)]
    return (parts[0], parts[1]) if len(parts) == 2 and parts[0] else (None, None)

def model_of(info):
    info = info if isinstance(info, dict) else {}
    return str(info.get("modelName") or info.get("model") or info.get("deviceName") or "Unknown Model")

def device_text(device_id, info):
    info = info if isinstance(info, dict) else {}
    status = "🟢 Online" if info.get("status") else "⚪ Status unknown/offline"
    return (f"📱 {model_of(info)}\n🆔 Device ID: {device_id}\n"
            f"🔋 Battery: {info.get('battery', '—')}\n"
            f"🤖 Android: {info.get('androidV') or info.get('androidVersion') or '—'}\n"
            f"Status: {status}")

def get_devices(cfg):
    fb = active_firebase(cfg)
    if not fb: raise ValueError("No Firebase saved. First use /addfirebase URL | NAME")
    data = firebase_get(fb["url"], "clients")
    return data if isinstance(data, dict) else {}

HELP = (
    "🤖 BOT CONTROL\n\n"
    "/start or /help - commands\n"
    "/status - saved configuration\n"
    "/firebase - list saved Firebase URLs\n"
    "/addfirebase URL | NAME - add Firebase\n"
    "/setfirebase NUMBER - select Firebase\n"
    "/channel - list saved chat/channel IDs\n"
    "/addchannel ID | NAME - save chat/channel ID\n"
    "/setchannel NUMBER - select chat/channel\n"
    "/devices - read-only device list\n"
    "/device MODEL - search by model name\n\n"
    "Device information is view-only. SMS sending and remote device commands are not included."
)

def handle(message):
    chat = message.get("chat", {})
    user = message.get("from", {})
    chat_id, user_id = chat.get("id"), user.get("id")
    text = (message.get("text") or "").strip()
    if chat.get("type") != "private" or user_id != OWNER_ID:
        if chat_id: send(chat_id, "⛔ Access denied. Owner-only private control.")
        return
    if not text: return
    command, _, args = text.partition(" ")
    command = command.split("@", 1)[0].lower()
    args = args.strip()
    cfg = load_config()

    try:
        if command in ("/start", "/help"):
            send(chat_id, HELP)

        elif command == "/status":
            fb = active_firebase(cfg)
            chans = cfg["channels"]
            ci = cfg.get("active_channel", 0)
            ch = chans[ci] if isinstance(ci, int) and 0 <= ci < len(chans) else None
            send(chat_id, f"⚙️ STATUS\nFirebase saved: {len(cfg['firebases'])}\n"
                 f"Active Firebase: {fb['name'] if fb else 'Not set'}\n"
                 f"Channels saved: {len(chans)}\nActive channel: {ch['name'] if ch else 'Not set'}\n"
                 "Device access: read-only")

        elif command == "/firebase":
            if not cfg["firebases"]:
                send(chat_id, "No Firebase saved. Add:\n/addfirebase https://your-db.firebaseio.com | My Firebase")
            else:
                lines = ["🔥 SAVED FIREBASES"]
                for i, item in enumerate(cfg["firebases"], 1):
                    mark = " ⭐" if i - 1 == cfg.get("active_firebase", 0) else ""
                    lines.append(f"{i}. {item['name']}{mark}\n{item['url']}")
                send(chat_id, "\n".join(lines))

        elif command == "/addfirebase":
            url, name = pair(args)
            if not url or not url.startswith(("https://", "http://")):
                send(chat_id, "Format:\n/addfirebase https://your-db.firebaseio.com | My Firebase")
                return
            name = name or url
            found = next((x for x in cfg["firebases"] if x.get("url", "").rstrip("/") == url.rstrip("/")), None)
            if found: found["name"] = name
            else:
                cfg["firebases"].append({"name": name, "url": url.rstrip("/")})
                cfg["active_firebase"] = len(cfg["firebases"]) - 1
            save_config(cfg)
            send(chat_id, f"✅ Firebase saved: {name}")

        elif command == "/setfirebase":
            if not args.isdigit() or not 1 <= int(args) <= len(cfg["firebases"]):
                send(chat_id, "Use /firebase, then /setfirebase NUMBER")
                return
            cfg["active_firebase"] = int(args) - 1
            save_config(cfg)
            send(chat_id, f"✅ Selected: {cfg['firebases'][int(args)-1]['name']}")

        elif command == "/channel":
            if not cfg["channels"]:
                send(chat_id, "No channel saved. Add:\n/addchannel -1001234567890 | My Channel")
            else:
                lines = ["💬 SAVED CHANNELS"]
                for i, item in enumerate(cfg["channels"], 1):
                    mark = " ⭐" if i - 1 == cfg.get("active_channel", 0) else ""
                    lines.append(f"{i}. {item['name']} — {item['id']}{mark}")
                send(chat_id, "\n".join(lines))

        elif command == "/addchannel":
            cid, name = pair(args)
            try: cid = str(int(cid))
            except (TypeError, ValueError):
                send(chat_id, "Format:\n/addchannel -1001234567890 | My Channel")
                return
            name = name or cid
            found = next((x for x in cfg["channels"] if str(x.get("id")) == cid), None)
            if found: found["name"] = name
            else:
                cfg["channels"].append({"name": name, "id": cid})
                cfg["active_channel"] = len(cfg["channels"]) - 1
            save_config(cfg)
            send(chat_id, f"✅ Channel saved: {name}")

        elif command == "/setchannel":
            if not args.isdigit() or not 1 <= int(args) <= len(cfg["channels"]):
                send(chat_id, "Use /channel, then /setchannel NUMBER")
                return
            cfg["active_channel"] = int(args) - 1
            save_config(cfg)
            send(chat_id, f"✅ Selected: {cfg['channels'][int(args)-1]['name']}")

        elif command == "/devices":
            devices = get_devices(cfg)
            if not devices:
                send(chat_id, "No records found under /clients.")
            else:
                lines = [f"📱 DEVICES ({len(devices)})"]
                for did, info in list(devices.items())[:30]:
                    lines.append("\n" + device_text(did, info))
                if len(devices) > 30: lines.append(f"\nShowing 30 of {len(devices)}. Search with /device MODEL")
                send(chat_id, "\n".join(lines))

        elif command == "/device":
            if not args:
                send(chat_id, "Use: /device MODEL_NAME")
                return
            devices = get_devices(cfg)
            matches = [(did, info) for did, info in devices.items() if args.casefold() in model_of(info).casefold()]
            if not matches: send(chat_id, f"No model matching '{args}' found.")
            else: send(chat_id, f"🔎 Matches: {len(matches)}\n\n" + "\n\n".join(device_text(d, i) for d, i in matches[:15]))

        else:
            send(chat_id, "Unknown command. Use /help.")

    except urllib.error.HTTPError as exc:
        send(chat_id, f"Request failed: HTTP {exc.code}. Check Firebase URL/read permissions.")
    except Exception as exc:
        send(chat_id, f"Error: {str(exc)[:400]}")

def main():
    global OFFSET
    print("=== TELEGRAM CONTROL BOT ===", flush=True)
    setup_credentials()
    print("Starting bot. Open Telegram and send /start.", flush=True)
    me = telegram("getMe")
    print("Connected as @" + me["result"].get("username", "bot"), flush=True)
    try:
        old = telegram("getUpdates", {"timeout": 0, "allowed_updates": json.dumps(["message"])})
        if old.get("result"): OFFSET = old["result"][-1]["update_id"] + 1
    except Exception: pass
    while True:
        try:
            result = telegram("getUpdates", {"offset": OFFSET, "timeout": 30,
                                             "allowed_updates": json.dumps(["message"])})
            for update in result.get("result", []):
                OFFSET = update["update_id"] + 1
                handle(update.get("message", {}))
        except KeyboardInterrupt:
            print("\nBot stopped.", flush=True)
            break
        except urllib.error.URLError as exc:
            print(f"Network error: {exc}; retrying...", flush=True)
            time.sleep(4)
        except Exception as exc:
            print(f"Error: {exc}; retrying...", flush=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
