# cyberbot.py
import asyncio
import json
import os
import random
import signal
import string
from typing import Dict, Any, Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

# -----------------------------
# CONFIGURATION
# -----------------------------
API_ID = 23625611
API_HASH = "40f58ed9f6f677c588851e2251830d62"
BOT_TOKEN = "8162720813:AAEvCxY8rbtKCBWdoGcGlrN3PBvDoP_28oY"
OWNER_ID = 7090863962

# start with NO demo keys
license_keys = set()          # persisted
ADMIN_LICENSE_KEY = "abc123"  # admin special key to self-activate (optional)

licensed_users = set()        # persisted
blocked_users = set()         # persisted
joined_users = set()          # persisted

# bad words
BAD_WORDS = {"badword1", "খারাপশব্দ"}

# pending requests (in-memory). persisted minimal fields separately.
# pending_requests structure:
# user_id -> {"tool": str, "input": str|tuple|None, "status": "waiting"|"done",
#             "loading_msg": (chat_id, message_id) | None}
pending_requests: Dict[int, Dict[str, Any]] = {}

# state file
STATE_FILE = "bot_state.json"

# -----------------------------
# APP INIT
# -----------------------------
app = Client("cyberbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -----------------------------
# PERSISTENCE HELPERS
# -----------------------------
def save_state():
    """Save persistent state to disk (non-blocking safe call)."""
    try:
        data = {
            "license_keys": list(license_keys),
            "licensed_users": list(licensed_users),
            "blocked_users": list(blocked_users),
            "joined_users": list(joined_users),
            # Persist pending requests minimal info (no message ids)
            "pending_requests": {
                str(uid): {
                    "tool": v["tool"],
                    "input": v.get("input"),
                    "status": v.get("status", "waiting")
                }
                for uid, v in pending_requests.items()
            }
        }
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[STATE] Saved.")
    except Exception as e:
        print("[STATE] Save error:", e)

def load_state():
    """Load persistent state from disk if exists."""
    global license_keys, licensed_users, blocked_users, joined_users, pending_requests
    if not os.path.exists(STATE_FILE):
        print("[STATE] No state file found, starting fresh.")
        return
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        license_keys = set(data.get("license_keys", []))
        licensed_users = set(data.get("licensed_users", []))
        blocked_users = set(data.get("blocked_users", []))
        joined_users = set(data.get("joined_users", []))
        # pending requests: restore minimal fields, mark loading_msg = None
        pending_requests = {}
        for k, v in data.get("pending_requests", {}).items():
            try:
                uid = int(k)
            except:
                continue
            pending_requests[uid] = {
                "tool": v.get("tool"),
                "input": v.get("input"),
                "status": v.get("status", "waiting"),
                "loading_msg": None
            }
        print("[STATE] Loaded.")
    except Exception as e:
        print("[STATE] Load error:", e)

# auto-save background task
async def autosave_loop():
    while True:
        await asyncio.sleep(30)
        save_state()

# graceful shutdown handler
def _graceful_exit(signum=None, frame=None):
    print("[STATE] Exiting — saving state...")
    save_state()
    try:
        loop = asyncio.get_event_loop()
        loop.stop()
    except Exception:
        pass

# register signals
signal.signal(signal.SIGINT, _graceful_exit)
signal.signal(signal.SIGTERM, _graceful_exit)

# -----------------------------
# HELPERS / UTILITIES
# -----------------------------
def is_paid(user_id: int) -> bool:
    return int(user_id) in licensed_users

def check_bad_words(text: str) -> bool:
    txt = text.lower()
    return any(b in txt for b in BAD_WORDS)

def gen_license_key(length: int = 10) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# start a loading animation message and track it (non-blocking)
async def start_loading_for(user_id: int, chat_id: int, reply_to_msg_id: Optional[int], label: str):
    """Sends a loading message and periodically edits it until admin responds."""
    try:
        msg = await app.send_message(chat_id, f"⏳ {label} — processing... (awaiting admin response)", reply_to_message_id=reply_to_msg_id)
    except Exception:
        # fallback: send in user's chat without reply_to
        try:
            msg = await app.send_message(chat_id, f"⏳ {label} — processing... (awaiting admin response)")
        except Exception:
            return
    # store loading message (not persisted)
    if user_id in pending_requests:
        pending_requests[user_id]["loading_msg"] = (msg.chat.id, msg.message_id)
    # loop until admin responds (status changes)
    dots = ""
    try:
        while pending_requests.get(user_id) and pending_requests[user_id].get("status") == "waiting":
            dots = (dots + ".") if len(dots) < 6 else ""
            try:
                await app.edit_message_text(msg.chat.id, msg.message_id, f"⏳ {label} — processing{dots}\n(Waiting for admin reply...)")
            except Exception:
                pass
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        pass
    return

# -----------------------------
# UI: single-column inline keyboard (one per row)
# -----------------------------
def tools_keyboard_single_column():
    kb = [
        # Hack Tools
        [InlineKeyboardButton("📘 Facebook ID Hack", callback_data="tool_facebook")],
        [InlineKeyboardButton("🎵 TikTok ID Hack", callback_data="tool_tiktok")],
        [InlineKeyboardButton("📧 Gmail ID Hack", callback_data="tool_gmail")],
        [InlineKeyboardButton("📸 Instagram ID Hack", callback_data="tool_instagram")],
        [InlineKeyboardButton("📞 WhatsApp Hack", callback_data="tool_whatsapp")],
        [InlineKeyboardButton("📱 IMO Hack", callback_data="tool_imo")],
        [InlineKeyboardButton("📲 Android Hack", callback_data="tool_android")],
        [InlineKeyboardButton("💬 Telegram ID Hack", callback_data="tool_telegram")],
        [InlineKeyboardButton("📷 Camera Hack", callback_data="tool_camera")],

        # separator
        [InlineKeyboardButton("— IMEI / Device Tools —", callback_data="noop")],

        # IMEI / Device Tools
        [InlineKeyboardButton("📱 /devices — List connected devices", callback_data="tool_devices")],
        [InlineKeyboardButton("📍 /location <IMEI> — Get GPS Location", callback_data="tool_location")],
        [InlineKeyboardButton("📩 /sms <IMEI> — SMS Inbox", callback_data="tool_sms")],
        [InlineKeyboardButton("📞 /calls <IMEI> — Call History", callback_data="tool_calls")],
        [InlineKeyboardButton("📶 /sim <IMEI> — SIM & Operator Info", callback_data="tool_sim")],
        [InlineKeyboardButton("📱 /model <IMEI> — Device Info", callback_data="tool_model")],
        [InlineKeyboardButton("📸 /photo <IMEI> — Camera Photo", callback_data="tool_photo")],
        [InlineKeyboardButton("🎥 /camera_live <IMEI> — Live Camera", callback_data="tool_camera_live")],
        [InlineKeyboardButton("🎙️ /mic <IMEI> — Microphone Record", callback_data="tool_mic")],
        [InlineKeyboardButton("📦 /apps <IMEI> — Installed Apps", callback_data="tool_apps")],
        [InlineKeyboardButton("🖼️ /gallery <IMEI> — Gallery", callback_data="tool_gallery")],
        [InlineKeyboardButton("📁 /files <IMEI> — File Manager", callback_data="tool_files")],
        [InlineKeyboardButton("🔐 /otp <IMEI> — OTP Capture", callback_data="tool_otp")],
        [InlineKeyboardButton("🟢 /whatsapp <IMEI> — WhatsApp Messages", callback_data="tool_whatsapp_msgs")],
        [InlineKeyboardButton("🔵 /imo <IMEI> — IMO Messages", callback_data="tool_imo_msgs")],
        [InlineKeyboardButton("🔔 /notify <IMEI> — Live Notifications", callback_data="tool_notify")],
        [InlineKeyboardButton("🎬 /screen_record <IMEI> — Screen Record", callback_data="tool_screen_record")],
        [InlineKeyboardButton("📋 /clipboard <IMEI> — Clipboard Capture", callback_data="tool_clipboard")],
        [InlineKeyboardButton("✅ /device_status <IMEI> — Active/Inactive Check", callback_data="tool_device_status")],
        [InlineKeyboardButton("⌨️ /keylogger <IMEI> — Key Logger", callback_data="tool_keylogger")],

        # consent-based features
        [InlineKeyboardButton("📲 My Phone Number (share contact)", callback_data="tool_my_phone")],
        [InlineKeyboardButton("📍 My Location (share location)", callback_data="tool_my_location")],

        # license & user/admin
        [InlineKeyboardButton("💳 Buy License", url="https://t.me/android_spy1")],
        [InlineKeyboardButton("🔑 Activate License", callback_data="activate_prompt")],
        [InlineKeyboardButton("👤 User Info", callback_data="userinfo")],
        [InlineKeyboardButton("🆘 Admin Help", callback_data="admin_network")],
    ]
    return InlineKeyboardMarkup(kb)

# -----------------------------
# START / BASIC HANDLERS
# -----------------------------
@app.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    user = message.from_user
    joined_users.add(user.id)
    save_state()
    if user.id in blocked_users:
        await message.reply_text("❌ আপনি ব্লক হয়েছেন।")
        return

    text = f"""👋 হ্যালো {user.first_name}!

🧰 Available Tools:
(বাটন থেকে সরাসরি যেকোনো টুল সিলেক্ট করুন — সব টুলস অ্যাডমিন-সাপোর্টেড; বাস্তব ডিভাইস-অ্যাকশন নেই)

💳 Buy License: /buy
🔑 Activate License: /activate <key>
🆘 Help: /admin
"""
    await message.reply_text(text, reply_markup=tools_keyboard_single_column())

# -----------------------------
# CALLBACK HANDLER (buttons)
# -----------------------------
@app.on_callback_query()
async def callback_handler(client: Client, callback_query):
    user = callback_query.from_user
    data = callback_query.data

    # blocked check
    if user.id in blocked_users:
        await callback_query.answer("❌ আপনি ব্লক হয়েছেন।", show_alert=True)
        return

    # noop separator
    if data == "noop":
        await callback_query.answer()
        return

    # Activate prompt
    if data == "activate_prompt":
        await callback_query.message.reply_text("লাইসেন্স একটিভ করতে: /activate <LICENSE_KEY>\nউদাহরণ: /activate ABC123XYZ")
        await callback_query.answer()
        return

    # userinfo
    if data == "userinfo":
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        username = f"@{user.username}" if user.username else "N/A"
        await callback_query.message.reply_text(f"👤 User Info:\n\nFull Name: {full_name}\nUsername: {username}\nUser ID: {user.id}")
        await callback_query.answer()
        return

    # admin network (owner only)
    if data == "admin_network":
        if user.id != OWNER_ID:
            await callback_query.answer("❌ আপনাকে অনুমতি নেই। (Admin only)", show_alert=True)
            return
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Generate Key (/gen_key)", callback_data="admin_gen_key")],
            [InlineKeyboardButton("➕ Add Key (/addkey <KEY>)", callback_data="admin_addkey")],
            [InlineKeyboardButton("🚫 Block User (/block <USER_ID>)", callback_data="admin_block")],
            [InlineKeyboardButton("✅ Unblock User (/unblock <USER_ID>)", callback_data="admin_unblock")],
            [InlineKeyboardButton("👥 Join List (/joinlist)", callback_data="admin_joinlist")],
            [InlineKeyboardButton("📣 Broadcast (/broadcast <MSG>)", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔐 List Keys (/list_keys)", callback_data="admin_list_keys")],
            [InlineKeyboardButton("↩️ Back to Tools", callback_data="back_to_tools")]
        ])
        await callback_query.message.edit("👮‍♂️ Admin Network — Select an action (or use chat commands):", reply_markup=admin_kb)
        await callback_query.answer()
        return

    # admin helper callbacks (owner only)
    if data.startswith("admin_"):
        if user.id != OWNER_ID:
            await callback_query.answer("❌ অনুমতি নেই।", show_alert=True)
            return
        if data == "admin_list_keys":
            keys_text = "\n".join(sorted(license_keys)) if license_keys else "No keys"
            await callback_query.message.reply_text(f"Active license keys:\n{keys_text}")
        elif data == "back_to_tools":
            await callback_query.message.edit("Back to Tools:", reply_markup=tools_keyboard_single_column())
        else:
            await callback_query.message.reply_text("Use the corresponding chat command (e.g. /gen_key, /addkey, /block ...).")
        await callback_query.answer()
        return

    # tools mapping: (label, kind)
    # kind: "text_input" (ask typed input), "imei_input" (same), "share_contact", "share_location"
    tools_map = {
        "tool_facebook": ("Facebook ID Hack", "text_input"),
        "tool_tiktok": ("TikTok ID Hack", "text_input"),
        "tool_gmail": ("Gmail ID Hack", "text_input"),
        "tool_instagram": ("Instagram ID Hack", "text_input"),
        "tool_whatsapp": ("WhatsApp Hack", "text_input"),
        "tool_imo": ("IMO Hack", "text_input"),
        "tool_android": ("Android Hack", "text_input"),
        "tool_telegram": ("Telegram ID Hack", "text_input"),
        "tool_camera": ("Camera Hack", "text_input"),
        "tool_devices": ("List Connected Devices", "imei_input"),
        "tool_location": ("Get GPS Location", "imei_input"),
        "tool_sms": ("SMS Inbox", "imei_input"),
        "tool_calls": ("Call History", "imei_input"),
        "tool_sim": ("SIM & Operator Info", "imei_input"),
        "tool_model": ("Device Info", "imei_input"),
        "tool_photo": ("Camera Photo", "imei_input"),
        "tool_camera_live": ("Live Camera Stream", "imei_input"),
        "tool_mic": ("Microphone Record", "imei_input"),
        "tool_apps": ("Installed Apps", "imei_input"),
        "tool_gallery": ("Gallery", "imei_input"),
        "tool_files": ("File Manager", "imei_input"),
        "tool_otp": ("OTP Capture", "imei_input"),
        "tool_whatsapp_msgs": ("WhatsApp Messages", "imei_input"),
        "tool_imo_msgs": ("IMO Messages", "imei_input"),
        "tool_notify": ("Live Notifications", "imei_input"),
        "tool_screen_record": ("Screen Record", "imei_input"),
        "tool_clipboard": ("Clipboard Capture", "imei_input"),
        "tool_device_status": ("Device Status Check", "imei_input"),
        "tool_keylogger": ("Key Logger", "imei_input"),
        "tool_my_phone": ("My Phone Number", "share_contact"),
        "tool_my_location": ("My Location", "share_location"),
    }

    if data not in tools_map:
        await callback_query.answer()
        return

    label, kind = tools_map[data]

    # paid check
    if not is_paid(user.id):
        quick_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Buy License", url="https://t.me/android_spy1")],
            [InlineKeyboardButton("🔑 Activate (use /activate)", callback_data="activate_prompt")]
        ])
        await callback_query.answer("⚠️ এটি একটি পেইড টুল — লাইসেন্স লাগবে।", show_alert=True)
        await callback_query.message.reply_text("এই টুল ব্যবহার করতে লাইসেন্স প্রয়োজন।", reply_markup=quick_kb)
        return

    # now request input or contact/location
    if kind == "share_contact":
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("📲 Share my phone number", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        pending_requests[user.id] = {"tool": label, "input": None, "status": "waiting", "loading_msg": None}
        save_state()
        await callback_query.message.reply_text(
            "অনুগ্রহ করে নিচের বোতনে ট্যাপ করে আপনার কন্ট্যাক্ট শেয়ার করুন।\n(এডমিন রিভিউ লাগবে)", reply_markup=kb
        )
        await callback_query.answer()
        return

    if kind == "share_location":
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("📍 Share my location", request_location=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        pending_requests[user.id] = {"tool": label, "input": None, "status": "waiting", "loading_msg": None}
        save_state()
        await callback_query.message.reply_text(
            "অনুগ্রহ করে নিচের বোতনে ট্যাপ করে আপনার লোকেশন শেয়ার করুন (ম্যাপ)।\n(এডমিন রিভিউ লাগবে)", reply_markup=kb
        )
        await callback_query.answer()
        return

    # text or imei input
    if kind in ("text_input", "imei_input"):
        pending_requests[user.id] = {"tool": label, "input": None, "status": "waiting", "loading_msg": None}
        save_state()
        prompt = "অনুগ্রহ করে ইনপুট টাইপ করুন (যেমন: ইউজারনেম/IMEI/ফোন ইত্যাদি) এবং পাঠান।\n(এডমিন রিভিউ হবে — পরে রেজাল্ট পাবেন)"
        await callback_query.message.reply_text(prompt)
        await callback_query.answer()
        return

# -----------------------------
# HANDLE CONTACT & LOCATION & TEXT INPUT
# -----------------------------
@app.on_message(filters.private & filters.contact)
async def handle_contact(client: Client, message: Message):
    user = message.from_user
    if user.id not in pending_requests or pending_requests[user.id].get("status") != "waiting":
        await message.reply_text("কোনো অনুরোধ সক্রিয় নেই। টুল ব্যবহার করতে /start বাটন ব্যবহার করুন।")
        return
    contact = message.contact
    phone = contact.phone_number
    pending_requests[user.id]["input"] = phone
    save_state()
    # start loading animation and notify admin
    asyncio.create_task(start_loading_for(user.id, message.chat.id, message.message_id, pending_requests[user.id]["tool"]))
    await app.send_message(OWNER_ID,
                           f"📲 New Contact shared by @{user.username or user.first_name} ({user.id})\nTool: {pending_requests[user.id]['tool']}\nPhone: {phone}\n\nTo respond: /respond {user.id} <RESULT_TEXT>")
    await message.reply_text("✅ আপনার কন্ট্যাক্ট গ্রহণ করা হয়েছে। এডমিন রিভিউ করবেন — পরে রেজাল্ট পাবেন.")

@app.on_message(filters.private & filters.location)
async def handle_location(client: Client, message: Message):
    user = message.from_user
    if user.id not in pending_requests or pending_requests[user.id].get("status") != "waiting":
        await message.reply_text("কোনো অনুরোধ সক্রিয় নেই। টুল ব্যবহার করতে /start বাটন ব্যবহার করুন।")
        return
    loc = message.location
    pending_requests[user.id]["input"] = {"latitude": loc.latitude, "longitude": loc.longitude}
    save_state()
    asyncio.create_task(start_loading_for(user.id, message.chat.id, message.message_id, pending_requests[user.id]["tool"]))
    await app.send_message(OWNER_ID,
                           f"📍 New Location shared by @{user.username or user.first_name} ({user.id})\nTool: {pending_requests[user.id]['tool']}\nLocation: {loc.latitude}, {loc.longitude}\n\nTo respond: /respond {user.id} <RESULT_TEXT>")
    # also send a map preview to admin
    try:
        await app.send_location(OWNER_ID, loc.latitude, loc.longitude)
    except Exception:
        pass
    await message.reply_text("✅ আপনার লোকেশন গ্রহণ করা হয়েছে। এডমিন রিভিউ করবেন — পরে রেজাল্ট পাবেন.")

@app.on_message(filters.private & filters.text & ~filters.command(["activate","buy","gen_key","addkey","block","unblock","joinlist","broadcast","respond","save_state","load_state","admin"]))
async def handle_text_input(client: Client, message: Message):
    user = message.from_user
    text = message.text.strip()
    # if there's a pending request, treat this text as input
    if user.id in pending_requests and pending_requests[user.id].get("status") == "waiting":
        pending_requests[user.id]["input"] = text
        save_state()
        asyncio.create_task(start_loading_for(user.id, message.chat.id, message.message_id, pending_requests[user.id]["tool"]))
        await app.send_message(OWNER_ID,
                               f"📝 New request from @{user.username or user.first_name} ({user.id})\nTool: {pending_requests[user.id]['tool']}\nInput: {text}\n\nTo respond: /respond {user.id} <RESULT_TEXT>")
        await message.reply_text("✅ আপনার ইনপুট নেওয়া হয়েছে। এডমিন রিভিউ করবেন — পরে রেজাল্ট পাবেন.")
        return

    # if no pending request, treat as normal message (bad-word check)
    if user.id in blocked_users:
        return
    if check_bad_words(text):
        blocked_users.add(user.id)
        save_state()
        await message.reply_text("⚠️ খারাপ শব্দ ব্যবহারের জন্য আপনাকে ব্লক করা হয়েছে।")
        return

# -----------------------------
# ADMIN: respond to pending request
# -----------------------------
@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("respond"))
async def admin_respond(client: Client, message: Message):
    # /respond <user_id> <result text>
    if len(message.command) < 3:
        await message.reply_text("⚠️ Usage: /respond <USER_ID> <RESULT_TEXT>")
        return
    try:
        target_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid USER_ID.")
        return
    if target_id not in pending_requests:
        await message.reply_text("❌ No pending request for that USER_ID.")
        return
    result_text = message.text.split(None, 2)[2]
    pending = pending_requests[target_id]
    pending["status"] = "done"
    save_state()
    # send result to user
    try:
        await app.send_message(target_id, f"✅ Result for your request ({pending['tool']}):\n\n{result_text}")
    except Exception:
        pass
    # edit loading message if present
    loading = pending.get("loading_msg")
    if loading:
        chat_id, msg_id = loading
        try:
            await app.edit_message_text(chat_id, msg_id, f"✅ {pending['tool']} — result posted by admin.\n\nResult:\n{result_text}")
        except Exception:
            pass
    # notify admin done
    await message.reply_text(f"✅ Response sent to {target_id}.")
    # remove pending
    pending_requests.pop(target_id, None)
    save_state()

# -----------------------------
# ADMIN / LICENSE / MISC COMMANDS
# -----------------------------
@app.on_message(filters.private & filters.command("activate"))
async def activate_handler(client: Client, message: Message):
    user = message.from_user
    if len(message.command) < 2:
        await message.reply_text("❌ উদাহরণ: /activate <license_key>")
        return
    key = message.command[1].strip()
    if key == ADMIN_LICENSE_KEY and user.id == OWNER_ID:
        licensed_users.add(user.id)
        save_state()
        await message.reply_text("✅ আপনি এডমিন হিসেবে সফলভাবে একটিভ হয়েছেন।")
        return
    if key in license_keys:
        licensed_users.add(user.id)
        save_state()
        await message.reply_text("✅ লাইসেন্স একটিভ হয়েছে! সব টুলস ব্যবহার করতে পারবেন।")
    else:
        await message.reply_text("❌ ভুল লাইসেন্স কী।")

@app.on_message(filters.private & filters.command("buy"))
async def buy_handler(client: Client, message: Message):
    await message.reply_text("💳 লাইসেন্স কিনতে যোগাযোগ করুন: [এডমিন](https://t.me/android_spy1)", disable_web_page_preview=True)

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("admin"))
async def admin_panel(client: Client, message: Message):
    await message.reply_text(
        f"""👮‍♂️ Admin Panel:
✅ Licensed Users: {len(licensed_users)}
🚫 Blocked Users: {len(blocked_users)}
👥 Joined Users: {len(joined_users)}
🧾 Pending Requests: {len([1 for v in pending_requests.values() if v.get('status')=='waiting'])}

🛠️ Commands:
/gen_key - Generate License
/addkey <KEY> - Add License Key
/block <USER_ID> - Block User
/unblock <USER_ID> - Unblock User
/joinlist - Joined Users List
/broadcast <MSG> - Broadcast Message
/respond <USER_ID> <TEXT> - Respond to pending request
/save_state - Save state to disk
/load_state - Load state from disk
"""
    )

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("addkey"))
async def add_key_handler(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ উদাহরণ: /addkey NEWKEY123")
        return
    new_key = message.command[1].strip()
    license_keys.add(new_key)
    save_state()
    await message.reply_text(f"✅ নতুন কী যুক্ত হয়েছে: {new_key}")

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("gen_key"))
async def gen_key_handler(client: Client, message: Message):
    new_key = gen_license_key()
    license_keys.add(new_key)
    save_state()
    await message.reply_text(f"🔑 নতুন লাইসেন্স কী: {new_key}")

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("block"))
async def block_user(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ উদাহরণ: /block USER_ID")
        return
    try:
        user_id = int(message.command[1])
        blocked_users.add(user_id)
        # also clear any pending requests from this user
        pending_requests.pop(user_id, None)
        save_state()
        await message.reply_text(f"🚫 {user_id} ব্লক করা হয়েছে।")
    except:
        await message.reply_text("❌ ভুল USER_ID।")

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("unblock"))
async def unblock_user(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ উদাহরণ: /unblock USER_ID")
        return
    try:
        user_id = int(message.command[1])
        blocked_users.discard(user_id)
        save_state()
        await message.reply_text(f"✅ {user_id} আনব্লক করা হয়েছে।")
    except:
        await message.reply_text("❌ ভুল USER_ID।")

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("joinlist"))
async def join_list(client: Client, message: Message):
    if not joined_users:
        await message.reply_text("কোনো ইউজার নেই।")
        return
    users_str = "\n".join(str(uid) for uid in joined_users)
    await message.reply_text(f"👥 Join Users:\n{users_str}")

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("broadcast"))
async def broadcast_msg(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ উদাহরণ: /broadcast Hello everyone")
        return
    text = message.text.split(None, 1)[1]
    for uid in list(joined_users):
        try:
            await app.send_message(uid, text)
            await asyncio.sleep(0.1)
        except Exception:
            continue
    await message.reply_text("✅ Broadcast Complete!")

# save/load state commands for admin
@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("save_state"))
async def save_state_cmd(client: Client, message: Message):
    save_state()
    await message.reply_text("✅ State saved.")

@app.on_message(filters.private & filters.user(OWNER_ID) & filters.command("load_state"))
async def load_state_cmd(client: Client, message: Message):
    load_state()
    await message.reply_text("✅ State loaded.")

# -----------------------------
# IMEI-style command wrapper (user can also call via /devices etc)
# -----------------------------
@app.on_message(filters.private & filters.command([
    "devices","location","sms","calls","sim","model","photo","camera_live","mic","apps",
    "gallery","files","otp","whatsapp","imo","notify","screen_record","clipboard","device_status","keylogger"
]))
async def imei_tools_command(client: Client, message: Message):
    user = message.from_user
    if not is_paid(user.id):
        await message.reply_text("⚠️ এটি পেইড টুল, লাইসেন্স কিনুন।")
        return
    cmd = message.command[0]
    imei = message.command[1] if len(message.command) > 1 else None
    pending_requests[user.id] = {"tool": cmd, "input": imei, "status": "waiting", "loading_msg": None}
    save_state()
    asyncio.create_task(start_loading_for(user.id, message.chat.id, message.message_id, cmd))
    await app.send_message(OWNER_ID, f"🛠️ New request from @{user.username or user.first_name} ({user.id})\nTool: {cmd}\nIMEI/Input: {imei}\n\nTo respond: /respond {user.id} <RESULT_TEXT>")
    await message.reply_text(f"🔧 {cmd} চালু হয়েছে — এডমিন রিভিউ চলছে। আপনি পরে রেজাল্ট পাবেন.")

# -----------------------------
# GENERIC TEXT (commands are filtered out above)
# -----------------------------
# handled earlier in handle_text_input and generic filters

# -----------------------------
# BOOT / SHUTDOWN
# -----------------------------
if __name__ == "__main__":
    load_state()
    # start autosave task
    loop = asyncio.get_event_loop()
    loop.create_task(autosave_loop())
    print("🤖 বট চালু হয়েছে...")
    try:
        app.run()
    finally:
        save_state()
