# ============================================================
# COMPLETE FIXED BOT - RENDER READY
# ============================================================

import logging
import asyncio
import subprocess
import os
import psutil
import sys
import re
import time
from datetime import datetime

# ============================================================
# SABSE PEHLE PACKAGES CHECK KARO
# ============================================================
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])

required = ["aiogram", "aiohttp", "backoff", "psutil"]
for pkg in required:
    try:
        __import__(pkg)
    except ImportError:
        print(f"Installing {pkg}...")
        install_package(pkg)

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.exceptions import TelegramBadRequest
from aiohttp import web, ClientTimeout
import backoff

# ============================================================
# ENVIRONMENT VARIABLES - RENDER KE LIYE
# ============================================================
TOKEN    = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT     = int(os.environ.get("PORT", "8080"))

if not TOKEN:
    print("❌ ERROR: BOT_TOKEN environment variable set nahi hai!")
    sys.exit(1)

if ADMIN_ID == 0:
    print("❌ ERROR: ADMIN_ID environment variable set nahi hai!")
    sys.exit(1)

# ============================================================
# DIRECTORIES & CONSTANTS
# ============================================================
STORAGE_DIR      = "user_files"
USERS_FILE       = "bot_users.txt"
REQUIREMENTS_DIR = "requirements"
LOGS_DIR         = "user_logs"
USER_FILE_LIMIT  = 2
MAX_FILE_SIZE    = 10 * 1024 * 1024  # 10MB

for d in [STORAGE_DIR, LOGS_DIR, REQUIREMENTS_DIR]:
    os.makedirs(d, exist_ok=True)

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# USERS LOAD KARO
# ============================================================
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return set(int(x.strip()) for x in f if x.strip().isdigit())
        except Exception as e:
            logger.error(f"Users load error: {e}")
    return set()

def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            for uid in users:
                f.write(f"{uid}\n")
    except Exception as e:
        logger.error(f"Users save error: {e}")

bot_users = load_users()

# ============================================================
# BOT & DISPATCHER
# ============================================================
bot = Bot(token=TOKEN)
dp  = Dispatcher()

# ============================================================
# GLOBAL STATE
# ============================================================
user_steps       = {}
banned_users     = set()
running_processes = {}
maintenance_mode  = False
file_last_run     = {}
user_file_limits  = {}
start_time        = datetime.now()

# ============================================================
# KEYBOARD HELPERS
# ============================================================
def create_menu_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton(text="📤 Upload Script"),
         KeyboardButton(text="▶ Run Script")],
        [KeyboardButton(text="⏹ Stop Script"),
         KeyboardButton(text="🗑 Delete Script")],
        [KeyboardButton(text="📄 View Logs"),
         KeyboardButton(text="📝 Edit Script")],
        [KeyboardButton(text="📊 Stats"),
         KeyboardButton(text="ℹ️ Help")],
        [KeyboardButton(text="🏓 Ping")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def create_admin_keyboard():
    buttons = [
        [KeyboardButton(text="🔄 Restart Bot"),
         KeyboardButton(text="🧹 Clear Logs")],
        [KeyboardButton(text="📊 System Info"),
         KeyboardButton(text="👥 User Stats")],
        [KeyboardButton(text="🔧 Maintenance"),
         KeyboardButton(text="📝 Broadcast")],
        [KeyboardButton(text="⬅️ Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def create_paginated_keyboard(items, callback_prefix, user_id,
                               chunk_size=8, button_symbol=""):
    keyboards = []
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i + chunk_size]
        keyboard = []
        for item in chunk:
            cb_data = f"{callback_prefix}_{user_id}_{item}"
            if len(cb_data) > 64:
                cb_data = cb_data[:64]
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{button_symbol} {item}",
                    callback_data=cb_data
                )
            ])
        keyboards.append(keyboard)
    return keyboards

# ============================================================
# SAFE MESSAGE SENDER
# ============================================================
async def safe_send(message, text, reply_markup=None, parse_mode=None):
    try:
        return await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except TelegramBadRequest as e:
        logger.error(f"Send error: {e}")
    except Exception as e:
        logger.error(f"Unexpected send error: {e}")

async def safe_edit(message, text, reply_markup=None):
    try:
        return await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Edit error: {e}")
    except Exception as e:
        logger.error(f"Unexpected edit error: {e}")

# ============================================================
# REQUIREMENTS INSTALLER
# ============================================================
STANDARD_LIBS = {
    'array', 'abc', 'argparse', 'asyncio', 'base64', 'binascii',
    'calendar', 'collections', 'configparser', 'contextlib', 'copy',
    'csv', 'datetime', 'decimal', 'enum', 'errno', 'functools',
    'getpass', 'glob', 'gzip', 'hashlib', 'hmac', 'html', 'http',
    'imaplib', 'importlib', 'io', 'itertools', 'json', 'logging',
    'math', 'mimetypes', 'multiprocessing', 'operator', 'os',
    'pathlib', 'pickle', 'pkgutil', 'platform', 'pprint', 'random',
    're', 'shutil', 'signal', 'socket', 'sqlite3', 'ssl', 'stat',
    'string', 'struct', 'subprocess', 'sys', 'tempfile', 'threading',
    'time', 'types', 'typing', 'unittest', 'urllib', 'uuid',
    'warnings', 'weakref', 'xml', 'zipfile', 'fcntl', 'psutil',
    'builtins', 'gc', 'inspect', 'traceback', 'dataclasses'
}

PACKAGE_MAPPING = {
    'telegram'  : 'python-telegram-bot',
    'telebot'   : 'pyTelegramBotAPI',
    'discord'   : 'discord.py',
    'cv2'       : 'opencv-python',
    'PIL'       : 'Pillow',
    'sklearn'   : 'scikit-learn',
    'dotenv'    : 'python-dotenv',
    'bs4'       : 'beautifulsoup4',
    'yaml'      : 'PyYAML',
    'Crypto'    : 'pycryptodome',
    'jwt'       : 'PyJWT',
    'pymongo'   : 'pymongo',
    'motor'     : 'motor',
    'redis'     : 'redis',
    'sqlalchemy': 'SQLAlchemy',
    'flask'     : 'Flask',
    'fastapi'   : 'fastapi',
    'requests'  : 'requests',
    'httpx'     : 'httpx',
    'numpy'     : 'numpy',
    'pandas'    : 'pandas',
}

def install_script_requirements(script_path):
    """Script ke imports parse karke packages install karo"""
    try:
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Script read error: {e}")
        return

    # Import statements extract karo
    patterns = [
        r'^\s*import\s+([\w\s,]+)',
        r'^\s*from\s+([\w.]+)\s+import',
    ]
    modules = set()
    for pattern in patterns:
        matches = re.findall(pattern, content, re.MULTILINE)
        for match in matches:
            for mod in match.split(','):
                base = mod.strip().split('.')[0]
                if base:
                    modules.add(base)

    # Standard libs filter karo
    to_install = {m for m in modules if m not in STANDARD_LIBS and m}

    logger.info(f"Modules to install: {to_install}")

    for module in to_install:
        # Package mapping check karo
        pkg_name = PACKAGE_MAPPING.get(module, module)
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg_name, "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info(f"Installed: {pkg_name}")
        except subprocess.CalledProcessError:
            # Variations try karo
            variations = [
                module,
                module.replace('_', '-'),
                f'python-{module}',
                f'py{module}'
            ]
            installed = False
            for variant in variations:
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", variant, "-q"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    installed = True
                    break
                except subprocess.CalledProcessError:
                    continue
            if not installed:
                logger.warning(f"Could not install: {module}")

# ============================================================
# USER HELPER
# ============================================================
def get_user_dir(user_id):
    path = os.path.join(STORAGE_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path

def get_user_files(user_id):
    user_dir = get_user_dir(user_id)
    return [f for f in os.listdir(user_dir) if f.endswith('.py')]

def is_admin(user_id):
    return user_id == ADMIN_ID

def is_banned(user_id):
    return user_id in banned_users

def is_maintenance(user_id):
    return maintenance_mode and not is_admin(user_id)

# ============================================================
# COMMANDS - START
# ============================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    bot_users.add(uid)
    save_users(bot_users)

    text = (
        "👋 *Welcome to Python Script Hosting Bot!*\n\n"
        "Aap yahan:\n"
        "• Python scripts upload kar sakte ho\n"
        "• Unhe server par run kar sakte ho\n"
        "• Logs aur output dekh sakte ho\n"
        "• Scripts manage kar sakte ho\n\n"
        "Neeche ke buttons se shuru karo! 👇"
    )
    await safe_send(message, text,
                    reply_markup=create_menu_keyboard(is_admin(uid)),
                    parse_mode="Markdown")
    logger.info(f"User started: {uid}")

# ============================================================
# COMMANDS - HELP
# ============================================================
@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Help")
async def cmd_help(message: types.Message):
    admin = is_admin(message.from_user.id)
    text = (
        "📌 *Available Commands:*\n\n"
        "🔹 *Upload Script* - Python script upload karo\n"
        "🔹 *Run Script* - Script run karo\n"
        "🔹 *Stop Script* - Running script stop karo\n"
        "🔹 *Delete Script* - Script delete karo\n"
        "🔹 *View Logs* - Script logs dekho\n"
        "🔹 *Edit Script* - Script edit karo\n"
        "🔹 *Stats* - Apni stats dekho\n"
        "🔹 *Ping* - Bot check karo\n"
    )
    if admin:
        text += (
            "\n👑 *Admin Commands:*\n"
            "🔹 /processes - Running processes dekho\n"
            "🔹 /broadcast - Message bhejo\n"
            "🔹 /system - System info\n"
            "🔹 /maintenance - Maintenance mode\n"
            "🔹 /allow <id> <limit> - File limit set karo\n"
            "🔹 /reset - Sab files delete karo\n"
            "🔹 /clearlogs - Sab logs clear karo\n"
        )
    await safe_send(message, text,
                    reply_markup=create_menu_keyboard(admin),
                    parse_mode="Markdown")

# ============================================================
# COMMANDS - PING
# ============================================================
@dp.message(Command("ping"))
@dp.message(F.text == "🏓 Ping")
async def cmd_ping(message: types.Message):
    start = time.time()
    msg = await message.answer("🏓 Pinging...")
    elapsed = round((time.time() - start) * 1000)
    await safe_edit(msg, f"🏓 Pong! `{elapsed}ms`")

# ============================================================
# COMMANDS - STATS
# ============================================================
@dp.message(Command("stats"))
@dp.message(F.text == "📊 Stats")
async def cmd_stats(message: types.Message):
    uid = message.from_user.id
    user_dir = get_user_dir(uid)
    files = get_user_files(uid)
    running = len(running_processes.get(uid, {}))
    uptime = datetime.now() - start_time
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)

    text = (
        f"📊 *Your Stats:*\n\n"
        f"📁 Files: `{len(files)}`\n"
        f"🚀 Running: `{running}`\n"
        f"⏱ Bot Uptime: `{h}h {m}m {s}s`\n"
    )
    await safe_send(message, text,
                    reply_markup=create_menu_keyboard(is_admin(uid)),
                    parse_mode="Markdown")

# ============================================================
# COMMANDS - SYSTEM (ADMIN)
# ============================================================
@dp.message(Command("system"))
@dp.message(F.text == "📊 System Info")
async def cmd_system(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    uptime = datetime.now() - start_time
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    total_running = sum(len(v) for v in running_processes.values())

    text = (
        f"💻 *System Status:*\n\n"
        f"🖥 CPU: `{cpu}%`\n"
        f"🧠 RAM: `{mem.percent}%` "
        f"({mem.used // 1024 // 1024}MB / {mem.total // 1024 // 1024}MB)\n"
        f"💾 Disk: `{disk.percent}%`\n"
        f"👥 Total Users: `{len(bot_users)}`\n"
        f"🚀 Running Scripts: `{total_running}`\n"
        f"⏱ Uptime: `{h}h {m}m {s}s`\n"
    )
    await safe_send(message, text,
                    reply_markup=create_admin_keyboard(),
                    parse_mode="Markdown")

# ============================================================
# COMMANDS - INFO (ADMIN)
# ============================================================
@dp.message(Command("info"))
@dp.message(F.text == "👥 User Stats")
async def cmd_info(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    total_files = 0
    for uid_dir in os.listdir(STORAGE_DIR):
        full = os.path.join(STORAGE_DIR, uid_dir)
        if os.path.isdir(full):
            total_files += len([f for f in os.listdir(full) if f.endswith('.py')])

    total_running = sum(len(v) for v in running_processes.values())
    uptime = datetime.now() - start_time
    h, rem = divmod(int(uptime.total_seconds()), 3600)
    m, s = divmod(rem, 60)

    text = (
        f"📊 *Bot Statistics:*\n\n"
        f"👥 Total Users: `{len(bot_users)}`\n"
        f"📁 Total Files: `{total_files}`\n"
        f"🚀 Running Scripts: `{total_running}`\n"
        f"⏱ Uptime: `{h}h {m}m {s}s`\n"
    )
    await safe_send(message, text,
                    reply_markup=create_admin_keyboard(),
                    parse_mode="Markdown")

# ============================================================
# COMMANDS - UPLOAD
# ============================================================
@dp.message(F.text == "📤 Upload Script")
async def cmd_upload(message: types.Message):
    uid = message.from_user.id

    if is_maintenance(uid):
        await safe_send(message,
                       "⚠️ Bot maintenance mein hai. Baad mein try karo.")
        return
    if is_banned(uid):
        await safe_send(message, "⛔ Aap banned hain!")
        return

    user_steps[uid] = "awaiting_file"
    await safe_send(
        message,
        "📤 *Script Upload Karo*\n\n"
        "Seedha `.py` file send karo.\n"
        "Agar requirements hain to pehle `requirements.txt` bhejo.",
        reply_markup=create_menu_keyboard(is_admin(uid)),
        parse_mode="Markdown"
    )

# ============================================================
# FILE UPLOAD HANDLER - requirements.txt
# ============================================================
@dp.message(F.document)
async def handle_document(message: types.Message):
    uid = message.from_user.id

    if not message.document:
        return

    fname = message.document.file_name or ""

    # Requirements.txt handle karo
    if fname == "requirements.txt":
        await handle_requirements(message, uid, fname)
        return

    # Python file handle karo
    if fname.endswith('.py'):
        await handle_python_file(message, uid, fname)
        return

    await safe_send(message,
                   "⚠️ Sirf `.py` ya `requirements.txt` files allowed hain!")

async def handle_requirements(message, uid, fname):
    user_dir = get_user_dir(uid)
    file_path = os.path.join(user_dir, fname)

    try:
        await bot.download(message.document, file_path)
    except Exception as e:
        await safe_send(message, f"⚠️ Download error: {e}")
        return

    status = await message.answer("🔄 Requirements install ho rahi hain...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", file_path, "-q"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            await safe_edit(status,
                           "✅ Packages install ho gaye!\nAb `.py` file bhejo.")
            user_steps[uid] = "awaiting_python_file"
        else:
            err = result.stderr[:500] if result.stderr else "Unknown error"
            await safe_edit(status, f"⚠️ Install error:\n```{err}```")
    except subprocess.TimeoutExpired:
        await safe_edit(status, "⚠️ Installation timeout! Baad mein try karo.")
    except Exception as e:
        await safe_edit(status, f"⚠️ Error: {e}")

async def handle_python_file(message, uid, fname):
    if is_banned(uid):
        await safe_send(message, "⛔ Aap banned hain!")
        return
    if is_maintenance(uid):
        await safe_send(message, "⚠️ Bot maintenance mein hai!")
        return

    # File size check
    if message.document.file_size > MAX_FILE_SIZE:
        await safe_send(message,
                       f"⚠️ File bahut badi hai! Max {MAX_FILE_SIZE//1024//1024}MB allowed hai.")
        return

    # File limit check
    user_dir = get_user_dir(uid)
    current_files = get_user_files(uid)
    limit = user_file_limits.get(uid, USER_FILE_LIMIT)
    if len(current_files) >= limit:
        await safe_send(message,
                       f"⚠️ Max {limit} files allowed hain!\nPehle koi file delete karo.")
        return

    file_path = os.path.join(user_dir, fname)

    status = await message.answer(f"🔄 `{fname}` upload ho raha hai...")

    try:
        await bot.download(message.document, file_path)
    except Exception as e:
        await safe_edit(status, f"⚠️ Download error: {e}")
        return

    # Requirements install karo
    await safe_edit(status, "🔄 Dependencies install ho rahi hain...")
    try:
        install_script_requirements(file_path)
        await safe_edit(status,
                       f"✅ `{fname}` successfully upload ho gaya!\n"
                       f"Ab *Run Script* se run karo.",)
    except Exception as e:
        await safe_edit(status,
                       f"✅ File upload ho gaya (kuch packages fail ho sakti hain):\n`{e}`")

    user_steps[uid] = None

# ============================================================
# RUN SCRIPT
# ============================================================
@dp.message(F.text == "▶ Run Script")
async def cmd_run(message: types.Message):
    uid = message.from_user.id
    if is_maintenance(uid):
        await safe_send(message, "⚠️ Maintenance mode on hai!")
        return

    files = get_user_files(uid)
    if not files:
        await safe_send(message,
                       "⚠️ Koi Python file nahi mili!\nPehle *Upload Script* se file upload karo.")
        return

    keyboards = create_paginated_keyboard(files, "run", uid, button_symbol="▶")
    for i, kb in enumerate(keyboards):
        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        await safe_send(message, f"▶ *Konsi file run karni hai?*",
                       reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("run_"))
async def cb_run(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.message.answer("⚠️ Invalid request!")
        return

    _, uid_str, filename = parts
    uid = int(uid_str)

    # Auth check
    if callback.from_user.id != uid and not is_admin(callback.from_user.id):
        await callback.message.answer("⛔ Ye aapki file nahi hai!")
        return

    user_dir = get_user_dir(uid)
    file_path = os.path.join(user_dir, filename)

    if not os.path.exists(file_path):
        await callback.message.answer("⚠️ File nahi mili!")
        return

    # Already running check
    if uid in running_processes and filename in running_processes[uid]:
        proc = running_processes[uid][filename]
        if proc.poll() is None:
            await callback.message.answer(f"⚠️ `{filename}` pehle se chal raha hai!")
            return
        else:
            del running_processes[uid][filename]

    status = await callback.message.answer(f"🔄 `{filename}` start ho raha hai...")

    try:
        process = subprocess.Popen(
            [sys.executable, "-u", filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=user_dir,
            bufsize=0
        )

        running_processes.setdefault(uid, {})[filename] = process
        file_last_run[f"{uid}_{filename}"] = time.time()

        # 2 second wait karke check karo
        await asyncio.sleep(2)

        if process.poll() is not None:
            # Process crash ho gaya
            stdout_data = b""
            stderr_data = b""
            try:
                stdout_data, stderr_data = process.communicate(timeout=5)
            except:
                pass
            error = (stderr_data or stdout_data).decode('utf-8', errors='replace')
            await safe_edit(status,
                           f"❌ `{filename}` crash ho gaya:\n```\n{error[:800]}\n```")
            if filename in running_processes.get(uid, {}):
                del running_processes[uid][filename]
        else:
            await safe_edit(status,
                           f"✅ `{filename}` successfully chal raha hai! 🚀\n"
                           f"Logs dekhne ke liye *View Logs* use karo.")

    except FileNotFoundError:
        await safe_edit(status, "❌ Python executable nahi mila!")
    except Exception as e:
        await safe_edit(status, f"❌ Error: `{e}`")
        logger.error(f"Run error for {filename}: {e}")

# ============================================================
# STOP SCRIPT
# ============================================================
@dp.message(F.text == "⏹ Stop Script")
async def cmd_stop(message: types.Message):
    uid = message.from_user.id
    user_procs = running_processes.get(uid, {})

    if not user_procs:
        await safe_send(message, "⚠️ Koi script nahi chal rahi!")
        return

    running = [f for f, p in user_procs.items() if p.poll() is None]
    if not running:
        running_processes.pop(uid, None)
        await safe_send(message, "⚠️ Koi active script nahi!")
        return

    keyboards = create_paginated_keyboard(running, "stop", uid, button_symbol="⏹")
    for kb in keyboards:
        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        await safe_send(message, "⏹ *Konsi script stop karni hai?*",
                       reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("stop_"))
async def cb_stop(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        return

    _, uid_str, filename = parts
    uid = int(uid_str)

    if callback.from_user.id != uid and not is_admin(callback.from_user.id):
        await callback.message.answer("⛔ Permission nahi hai!")
        return

    if uid in running_processes and filename in running_processes[uid]:
        proc = running_processes[uid][filename]
        try:
            proc.terminate()
            await asyncio.sleep(1)
            if proc.poll() is None:
                proc.kill()
        except Exception as e:
            logger.error(f"Stop error: {e}")
        del running_processes[uid][filename]
        await callback.message.answer(f"✅ `{filename}` stop ho gaya!")
    else:
        await callback.message.answer("⚠️ Ye process nahi chal raha tha!")

# ============================================================
# DELETE SCRIPT
# ============================================================
@dp.message(F.text == "🗑 Delete Script")
async def cmd_delete(message: types.Message):
    uid = message.from_user.id
    files = get_user_files(uid)

    if not files:
        await safe_send(message, "⚠️ Delete karne ke liye koi file nahi!")
        return

    keyboards = create_paginated_keyboard(files, "delete", uid, button_symbol="🗑")
    for kb in keyboards:
        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        await safe_send(message, "🗑 *Konsi file delete karni hai?*",
                       reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("delete_"))
async def cb_delete(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        return

    _, uid_str, filename = parts
    uid = int(uid_str)

    if callback.from_user.id != uid and not is_admin(callback.from_user.id):
        await callback.message.answer("⛔ Permission nahi hai!")
        return

    # Pehle stop karo agar chal raha hai
    if uid in running_processes and filename in running_processes[uid]:
        try:
            running_processes[uid][filename].terminate()
        except:
            pass
        del running_processes[uid][filename]

    user_dir = get_user_dir(uid)
    file_path = os.path.join(user_dir, filename)

    if os.path.exists(file_path):
        os.remove(file_path)
        await callback.message.answer(f"✅ `{filename}` delete ho gaya!")
    else:
        await callback.message.answer("⚠️ File pehle se delete ho chuki hai!")

# ============================================================
# VIEW LOGS
# ============================================================
@dp.message(F.text == "📄 View Logs")
async def cmd_logs(message: types.Message):
    uid = message.from_user.id
    files = get_user_files(uid)

    if not files:
        await safe_send(message, "⚠️ Koi file nahi mili!")
        return

    keyboards = create_paginated_keyboard(files, "logs", uid, button_symbol="📄")
    for kb in keyboards:
        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        await safe_send(message, "📄 *Konsi file ke logs dekhne hain?*",
                       reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("logs_"))
async def cb_logs(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        return

    _, uid_str, filename = parts
    uid = int(uid_str)

    if uid not in running_processes or filename not in running_processes[uid]:
        await callback.message.answer(
            f"ℹ️ `{filename}` abhi nahi chal raha.\n"
            f"Pehle script run karo, phir logs dekho.")
        return

    proc = running_processes[uid][filename]

    if proc.poll() is not None:
        await callback.message.answer(f"ℹ️ `{filename}` band ho chuka hai.")
        return

    # Non-blocking read try karo
    output_lines = []
    try:
        if proc.stderr:
            import select
            ready, _, _ = select.select([proc.stderr], [], [], 0.5)
            if ready:
                data = os.read(proc.stderr.fileno(), 4096)
                if data:
                    output_lines = data.decode('utf-8', errors='replace').splitlines()

        if proc.stdout:
            import select
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            if ready:
                data = os.read(proc.stdout.fileno(), 4096)
                if data:
                    output_lines += data.decode('utf-8', errors='replace').splitlines()
    except Exception as e:
        logger.error(f"Log read error: {e}")

    kb = [[InlineKeyboardButton(
        text="🔄 Refresh", callback_data=f"logs_{uid}_{filename}")]]
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    if output_lines:
        text = f"📄 *Logs - {filename}:*\n\n```\n"
        text += "\n".join(output_lines[-30:])
        text += "\n```"
    else:
        text = (f"✅ `{filename}` chal raha hai!\n"
                f"Abhi koi output nahi (ya sab log file mein hai)")

    await callback.message.answer(
        text[:4000], reply_markup=markup, parse_mode="Markdown")

# ============================================================
# EDIT SCRIPT
# ============================================================
@dp.message(F.text == "📝 Edit Script")
async def cmd_edit(message: types.Message):
    uid = message.from_user.id
    files = get_user_files(uid)

    if not files:
        await safe_send(message, "⚠️ Edit karne ke liye koi file nahi!")
        return

    keyboards = create_paginated_keyboard(files, "edit", uid, button_symbol="📝")
    for kb in keyboards:
        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        await safe_send(message, "📝 *Konsi file edit karni hai?*",
                       reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("edit_"))
async def cb_edit(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        return

    _, uid_str, filename = parts
    uid = int(uid_str)

    if callback.from_user.id != uid and not is_admin(callback.from_user.id):
        await callback.message.answer("⛔ Permission nahi hai!")
        return

    user_dir = get_user_dir(uid)
    file_path = os.path.join(user_dir, filename)

    if not os.path.exists(file_path):
        await callback.message.answer("⚠️ File nahi mili!")
        return

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        user_steps[uid] = f"editing_{filename}"

        preview = content[:2000]
        text = (
            f"📝 *{filename}*\n\n"
            f"```python\n{preview}\n```\n\n"
            f"Naya code bhejo (poora file replace ho jaega):"
        )
        await callback.message.answer(text[:4000], parse_mode="Markdown")
    except Exception as e:
        await callback.message.answer(f"⚠️ File read error: {e}")

@dp.message(lambda msg: (
    msg.from_user and
    isinstance(user_steps.get(msg.from_user.id), str) and
    user_steps.get(msg.from_user.id, "").startswith("editing_") and
    msg.text
))
async def handle_edit_content(message: types.Message):
    uid = message.from_user.id
    step = user_steps.get(uid, "")
    if not step.startswith("editing_"):
        return

    filename = step.replace("editing_", "", 1)
    user_dir = get_user_dir(uid)
    file_path = os.path.join(user_dir, filename)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(message.text)
        user_steps[uid] = None
        await safe_send(message,
                       f"✅ `{filename}` update ho gaya!",
                       reply_markup=create_menu_keyboard(is_admin(uid)),
                       parse_mode="Markdown")
    except Exception as e:
        await safe_send(message, f"⚠️ Save error: {e}")

# ============================================================
# ADMIN PANEL
# ============================================================
@dp.message(F.text == "👑 Admin Panel")
async def cmd_admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return
    await safe_send(message, "👑 *Admin Panel*",
                   reply_markup=create_admin_keyboard(),
                   parse_mode="Markdown")

@dp.message(F.text == "⬅️ Back to Main Menu")
async def cmd_back(message: types.Message):
    uid = message.from_user.id
    await safe_send(message, "🏠 Main menu",
                   reply_markup=create_menu_keyboard(is_admin(uid)))

# ============================================================
# BROADCAST
# ============================================================
@dp.message(Command("broadcast"))
@dp.message(F.text == "📝 Broadcast")
async def cmd_broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    # /broadcast text ke saath
    if message.text and message.text.startswith("/broadcast"):
        text = message.text.replace("/broadcast", "", 1).strip()
        if text:
            await do_broadcast(message, text)
            return

    user_steps[message.from_user.id] = "awaiting_broadcast"
    await safe_send(message, "📝 Broadcast message bhejo:")

@dp.message(lambda msg: user_steps.get(msg.from_user.id) == "awaiting_broadcast")
async def handle_broadcast_text(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    user_steps[message.from_user.id] = None
    await do_broadcast(message, message.text)

async def do_broadcast(message, text):
    status = await message.answer(f"📢 {len(bot_users)} users ko bhej raha hun...")
    success = 0
    failed = 0
    for uid in list(bot_users):
        try:
            await bot.send_message(uid, f"📢 *Admin Message:*\n\n{text}",
                                   parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)  # Rate limit avoid karo
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast fail {uid}: {e}")

    await safe_edit(status,
                   f"✅ Broadcast complete!\n"
                   f"✅ Success: `{success}`\n"
                   f"❌ Failed: `{failed}`")

# ============================================================
# MAINTENANCE
# ============================================================
@dp.message(Command("maintenance"))
@dp.message(F.text == "🔧 Maintenance")
async def cmd_maintenance(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    status_text = "🟢 ON" if maintenance_mode else "🔴 OFF"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🟢 Turn ON",
                            callback_data="maint_on"),
        InlineKeyboardButton(text="🔴 Turn OFF",
                            callback_data="maint_off"),
    ]])
    await safe_send(message,
                   f"🔧 *Maintenance Mode:* {status_text}",
                   reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("maint_"))
async def cb_maintenance(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Permission nahi!", show_alert=True)
        return

    global maintenance_mode
    maintenance_mode = callback.data == "maint_on"
    status_text = "🟢 ON" if maintenance_mode else "🔴 OFF"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🟢 Turn ON", callback_data="maint_on"),
        InlineKeyboardButton(text="🔴 Turn OFF", callback_data="maint_off"),
    ]])
    await safe_edit(callback.message,
                   f"🔧 *Maintenance Mode:* {status_text}",
                   reply_markup=kb)
    await callback.answer(f"Maintenance {status_text}")

# ============================================================
# RESET (ADMIN)
# ============================================================
@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Haan, delete karo",
                            callback_data="confirm_reset"),
        InlineKeyboardButton(text="❌ Cancel",
                            callback_data="cancel_reset"),
    ]])
    await safe_send(message,
                   "⚠️ *Sab users ki files delete ho jaengi!*\nConfirm karo:",
                   reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "confirm_reset")
async def cb_confirm_reset(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()

    count = 0
    for uid_dir in os.listdir(STORAGE_DIR):
        full = os.path.join(STORAGE_DIR, uid_dir)
        if os.path.isdir(full):
            uid = int(uid_dir)
            if uid in running_processes:
                for p in running_processes[uid].values():
                    try:
                        p.terminate()
                    except:
                        pass
                running_processes.pop(uid, None)
            for f in os.listdir(full):
                fp = os.path.join(full, f)
                if os.path.isfile(fp):
                    os.remove(fp)
                    count += 1

    await callback.message.edit_text(f"✅ `{count}` files delete ho gayi!")

@dp.callback_query(F.data == "cancel_reset")
async def cb_cancel_reset(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("❌ Reset cancel ho gaya.")

# ============================================================
# CLEAR LOGS (ADMIN)
# ============================================================
@dp.message(Command("clearlogs"))
@dp.message(F.text == "🧹 Clear Logs")
async def cmd_clearlogs(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return
    count = 0
    for root, dirs, files in os.walk(LOGS_DIR):
        for f in files:
            os.remove(os.path.join(root, f))
            count += 1
    await safe_send(message, f"🧹 `{count}` log files clear ho gayi!",
                   reply_markup=create_admin_keyboard(),
                   parse_mode="Markdown")

# ============================================================
# RESTART (ADMIN)
# ============================================================
@dp.message(Command("restart"))
@dp.message(F.text == "🔄 Restart Bot")
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return
    await safe_send(message, "🔄 Restarting...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ============================================================
# PROCESSES (ADMIN)
# ============================================================
@dp.message(Command("processes"))
async def cmd_processes(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    lines = []
    for uid, scripts in running_processes.items():
        for sname, proc in scripts.items():
            status = "🟢 Running" if proc.poll() is None else "🔴 Stopped"
            lines.append(f"👤 User `{uid}`: `{sname}` - {status}")

    if lines:
        await safe_send(message,
                       "🔄 *All Processes:*\n\n" + "\n".join(lines),
                       parse_mode="Markdown")
    else:
        await safe_send(message, "📝 Koi process nahi chal raha!")

# ============================================================
# ALLOW (ADMIN)
# ============================================================
@dp.message(Command("allow"))
async def cmd_allow(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await safe_send(message,
                       "⚠️ Usage: `/allow <user_id> <file_limit>`",
                       parse_mode="Markdown")
        return

    try:
        uid = int(parts[1])
        limit = int(parts[2])
        user_file_limits[uid] = limit
        await safe_send(message,
                       f"✅ User `{uid}` ka limit `{limit}` files ho gaya!",
                       parse_mode="Markdown")
        try:
            await bot.send_message(uid,
                                   f"✅ Aapka file limit `{limit}` ho gaya!",
                                   parse_mode="Markdown")
        except:
            pass
    except ValueError:
        await safe_send(message, "⚠️ User ID aur limit numbers hone chahiye!")

# ============================================================
# LIST (ADMIN)
# ============================================================
@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return

    if not user_file_limits:
        await safe_send(message, "📝 Kisi ka custom limit nahi set hai!")
        return

    lines = [f"👤 `{uid}`: `{lim}` files"
             for uid, lim in user_file_limits.items()]
    await safe_send(message,
                   "📋 *Custom File Limits:*\n\n" + "\n".join(lines),
                   parse_mode="Markdown")

# ============================================================
# TERMINAL (ADMIN ONLY)
# ============================================================
@dp.message(Command("terminal"))
async def cmd_terminal(message: types.Message):
    if not is_admin(message.from_user.id):
        await safe_send(message, "⛔ Sirf admins ke liye!")
        return
    user_steps[message.from_user.id] = "awaiting_terminal"
    await safe_send(message, "💻 Shell command bhejo:")

@dp.message(lambda msg: user_steps.get(msg.from_user.id) == "awaiting_terminal")
async def handle_terminal(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    user_steps[message.from_user.id] = None
    cmd = message.text

    try:
        result = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout or result.stderr or "No output"
        await safe_send(message,
                       f"```\n{output[:3500]}\n```",
                       parse_mode="Markdown")
    except subprocess.TimeoutExpired:
        await safe_send(message, "⚠️ Command timeout!")
    except Exception as e:
        await safe_send(message, f"⚠️ Error: {e}")

# ============================================================
# UNKNOWN MESSAGES
# ============================================================
@dp.message()
async def handle_unknown(message: types.Message):
    uid = message.from_user.id
    step = user_steps.get(uid)

    # Agar koi step active hai to ignore karo
    if step and step not in ["awaiting_file"]:
        return

    # Simple response
    await safe_send(
        message,
        "❓ Samajh nahi aaya! Neeche se option select karo:",
        reply_markup=create_menu_keyboard(is_admin(uid))
    )

# ============================================================
# WEB SERVER - RENDER KE LIYE ZAROORI
# ============================================================
async def health_handler(request):
    uptime = datetime.now() - start_time
    return web.json_response({
        "status"    : "running",
        "uptime_sec": int(uptime.total_seconds()),
        "users"     : len(bot_users),
        "running"   : sum(len(v) for v in running_processes.values()),
    })

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_handler)
    app.router.add_get('/health', health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Web server started on port {PORT}")

# ============================================================
# PROCESS CLEANUP - Dead processes hataao
# ============================================================
async def cleanup_dead_processes():
    while True:
        try:
            for uid in list(running_processes.keys()):
                for fname in list(running_processes[uid].keys()):
                    proc = running_processes[uid][fname]
                    if proc.poll() is not None:
                        del running_processes[uid][fname]
                        logger.info(f"Cleaned dead process: {fname} (user {uid})")
                if not running_processes[uid]:
                    del running_processes[uid]
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(60)  # Har 60 sec mein check

# ============================================================
# MAIN
# ============================================================
async def main():
    logger.info("🤖 Bot start ho raha hai...")

    # Web server start karo
    await start_web_server()

    # Background cleanup start karo
    asyncio.create_task(cleanup_dead_processes())

    logger.info("✅ Polling shuru ho rahi hai...")
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot band ho gaya (user ne roka)")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
