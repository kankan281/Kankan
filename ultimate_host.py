import logging
import asyncio
import subprocess
import os
import psutil
import sys
import re
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest
from aiohttp import ClientTimeout, ClientSession
import backoff

# ============================================================
# ENVIRONMENT VARIABLES SE LENA (Render ke liye zaroori)
# ============================================================
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "YOUR_ADMIN_ID_HERE"))

STORAGE_DIR = "user_files"
USERS_FILE = "bot_users.txt"
REQUIREMENTS_DIR = "requirements"

# Load existing users
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'r') as f:
        bot_users = set(int(x.strip()) for x in f.readlines() if x.strip())
else:
    bot_users = set()

LOGS_DIR = "user_logs"
USER_FILE_LIMIT = 2
MAX_FILE_SIZE = 10 * 1024 * 1024
ALERT_CPU_THRESHOLD = 200
ALERT_MEMORY_THRESHOLD = 500

os.makedirs(REQUIREMENTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

timeout = ClientTimeout(total=300, connect=60, sock_connect=60, sock_read=60)
bot = Bot(token=TOKEN)
dp = Dispatcher()

def create_menu_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton(text="📤 Upload Script"), KeyboardButton(text="▶ Run Script")],
        [KeyboardButton(text="⏹ Stop Script"), KeyboardButton(text="🗑 Delete Script")],
        [KeyboardButton(text="📄 View Logs"), KeyboardButton(text="📝 Edit Script")],
        [KeyboardButton(text="📊 Stats"), KeyboardButton(text="ℹ️ Help")],
        [KeyboardButton(text="🏓 Ping")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@backoff.on_exception(backoff.expo, (TimeoutError, ConnectionError),
                      max_tries=3, max_time=60)
async def send_message_with_retry(*args, **kwargs):
    return await bot.send_message(*args, **kwargs)

user_steps = {}
user_limits = {}
banned_users = set()
running_processes = {}
maintenance_mode = False
file_last_run = {}
user_file_limits = {}

def install_requirements_from_script(script_path, max_retries=3):
    global_req_file = "global_requirements.txt"
    core_packages = {'aiogram', 'aiohttp', 'backoff', 'psutil'}

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] +
                              list(core_packages))
    except Exception as e:
        logging.error(f"Failed to install core dependencies: {e}")
        raise

    with open(script_path, 'r') as f:
        script_content = f.read()

    imports = re.findall(
        r'^\s*(?:import\s+([\w\s,]+)|from\s+([\w.]+)\s+import)',
        script_content, re.MULTILINE)
    modules = set()

    for imp in imports:
        if imp[0]:
            modules.update(m.strip() for m in imp[0].split(','))
        if imp[1]:
            modules.add(imp[1].split('.')[0])

    standard_libs = {
        'os', 'sys', 're', 'time', 'datetime', 'logging', 'asyncio',
        'subprocess', 'psutil'
    }
    modules = {m for m in modules if m not in standard_libs}

    if modules:
        try:
            required_packages = {"aiogram", "aiohttp", "backoff", "psutil"}
            subprocess.check_call([sys.executable, "-m", "pip", "install"] +
                                  list(required_packages))
        except Exception as e:
            logging.error(f"Failed to install core dependencies: {e}")
            raise

    package_mapping = {
        'telegram': 'python-telegram-bot',
        'telebot': 'pyTelegramBotAPI',
        'discord': 'discord.py',
        'cv2': 'opencv-python'
    }

    try:
        with open(script_path, 'r') as f:
            content = f.read()
            for line in content.split('\n'):
                if line.startswith('from') or line.startswith('import'):
                    for old_pkg, new_pkg in package_mapping.items():
                        if old_pkg in line:
                            try:
                                subprocess.check_call([
                                    sys.executable, "-m", "pip", "uninstall",
                                    "-y", old_pkg
                                ])
                                subprocess.check_call([
                                    sys.executable, "-m", "pip", "install",
                                    new_pkg
                                ])
                                print(f"Successfully replaced {old_pkg} with {new_pkg}")
                            except:
                                print(f"Failed to install {new_pkg}")
    except Exception as e:
        print(f"Error analyzing imports: {str(e)}")

    with open(script_path, "r") as f:
        script_content = f.read()

    imports = re.findall(
        r'^\s*(?:import\s+([\w\s,]+)|from\s+([\w.]+)\s+import)',
        script_content, re.MULTILINE)
    modules = set()

    for imp in imports:
        if imp[0]:
            modules.update(m.strip() for m in imp[0].split(','))
        if imp[1]:
            modules.add(imp[1].split('.')[0])

    standard_libs = {
        'array', 'abc', 'argparse', 'asyncio', 'base64', 'binascii',
        'calendar', 'collections', 'configparser', 'contextlib', 'copy', 'csv',
        'datetime', 'decimal', 'enum', 'errno', 'functools', 'getpass', 'glob',
        'gzip', 'hashlib', 'hmac', 'html', 'http', 'imaplib', 'importlib',
        'io', 'itertools', 'json', 'logging', 'math', 'mimetypes',
        'multiprocessing', 'operator', 'os', 'pathlib', 'pickle', 'pkgutil',
        'platform', 'pprint', 'random', 're', 'shutil', 'signal', 'socket',
        'sqlite3', 'ssl', 'stat', 'string', 'struct', 'subprocess', 'sys',
        'tempfile', 'threading', 'time', 'types', 'typing', 'unittest',
        'urllib', 'uuid', 'warnings', 'weakref', 'xml', 'zipfile'
    }
    modules = {m for m in modules if m not in standard_libs}

    for module in modules:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", module])
        except subprocess.CalledProcessError:
            try:
                variations = [
                    module, module.replace('_', '-'),
                    'python-' + module, 'py' + module
                ]
                for variant in variations:
                    try:
                        subprocess.check_call(
                            [sys.executable, "-m", "pip", "install", variant])
                        break
                    except subprocess.CalledProcessError:
                        continue
            except:
                print(f"Warning: Failed to install {module}")

start_time = datetime.now()

@dp.message(Command("info"))
async def info_command(message: types.Message):
    total_users = len(bot_users)
    total_files = sum(
        len([f for f in os.listdir(os.path.join(STORAGE_DIR, str(uid)))
             if f.endswith('.py')])
        for uid in os.listdir(STORAGE_DIR)
        if os.path.isdir(os.path.join(STORAGE_DIR, str(uid))))
    total_running = sum(len(scripts) for scripts in running_processes.values())

    uptime = datetime.now() - start_time
    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    seconds = uptime.seconds % 60

    info_text = f"""
📊 Bot Statistics:
👥 Total Users: {total_users}
📁 Total Files: {total_files}
🚀 Running Scripts: {total_running}
⏱ Uptime: {days}d {hours}h {minutes}m {seconds}s
"""
    await message.answer(info_text, 
                        reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))

@dp.message(Command("help"))
async def help_command(message: types.Message):
    is_admin = message.from_user.id == ADMIN_ID
    help_text = """
📌 Available Commands:

🔹 Upload Script - Start hosting your Python project
🔹 Run Script - Run a selected Python script
🔹 Stop Script - Stop a selected running script
🔹 Delete Script - Delete a selected file
🔹 View Logs - View latest logs of your scripts
🔹 Edit Script - Edit your Python scripts
🔹 Stats - View your statistics
🔹 Ping - Check if the bot is alive
"""
    if is_admin:
        help_text += """
👑 Admin Commands:
🔹 Admin Panel - Access admin functions
"""
    await message.answer(help_text, reply_markup=create_menu_keyboard(is_admin))

@dp.message(Command("system"))
async def system_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    status = f"""
💻 System Status:
CPU Usage: {cpu_percent}%
RAM Usage: {memory.percent}%
Disk Usage: {disk.percent}%
Total Users: {len(bot_users)}
Total Running Scripts: {sum(len(scripts) for scripts in running_processes.values())}
"""
    await message.answer(status, reply_markup=create_menu_keyboard(True))

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    user_id = message.from_user.id
    user_dir = os.path.join(STORAGE_DIR, str(user_id))

    if not os.path.exists(user_dir):
        await message.answer("📊 Stats:\nNo files uploaded yet",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    files = [f for f in os.listdir(user_dir) if f.endswith('.py')]
    running = len(running_processes.get(user_id, {}))

    stats = f"""
📊 Your Stats:
Files: {len(files)}
Running Scripts: {running}
Last Activity: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_last_run.get(f"{user_id}_", time.time())))}
"""
    await message.answer(stats, 
                        reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))

@dp.message(Command("reset"))
async def reset_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ This command is only available to admins.",
                           reply_markup=create_menu_keyboard(True))
        return

    try:
        for user_dir in os.listdir(STORAGE_DIR):
            user_path = os.path.join(STORAGE_DIR, user_dir)
            if os.path.isdir(user_path):
                user_id = int(user_dir)
                if user_id in running_processes:
                    for process in running_processes[user_id].values():
                        process.terminate()
                    del running_processes[user_id]
                for file in os.listdir(user_path):
                    file_path = os.path.join(user_path, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
        await message.answer("✅ All user files have been deleted.",
                           reply_markup=create_menu_keyboard(True))
    except Exception as e:
        await message.answer(f"⚠️ Error while resetting: {str(e)}",
                           reply_markup=create_menu_keyboard(True))

@dp.message(Command("restart"))
async def restart_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🔄 Restarting bot...", reply_markup=create_menu_keyboard(True))
    os.execv(sys.executable, ['python'] + sys.argv)

@dp.message(Command("clearlogs"))
async def clearlogs_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        for root, dirs, files in os.walk(LOGS_DIR):
            for file in files:
                os.remove(os.path.join(root, file))
        await message.answer("🧹 All logs have been cleared",
                           reply_markup=create_menu_keyboard(True))
    except Exception as e:
        await message.answer(f"⚠️ Error clearing logs: {str(e)}",
                           reply_markup=create_menu_keyboard(True))

@dp.message(CommandStart())
async def start_command(message: types.Message):
    user_id = message.from_user.id
    bot_users.add(user_id)
    os.makedirs(os.path.dirname(USERS_FILE) if os.path.dirname(USERS_FILE) else '.', 
                exist_ok=True)
    with open(USERS_FILE, 'w') as f:
        for uid in bot_users:
            f.write(f"{uid}\n")

    welcome_text = """
👋 Welcome to Python Script Hosting Bot!

With this bot you can:
- Upload Python scripts
- Run them on our server
- View logs and outputs
- Manage your scripts easily

Use the menu buttons below to get started!
"""
    await message.answer(welcome_text, 
                        reply_markup=create_menu_keyboard(user_id == ADMIN_ID))
    logging.info(f"New user registered: {user_id}")

@dp.message(lambda message: message.text == "📤 Upload Script")
async def upload_script_handler(message: types.Message):
    await upload_instruction(message)

@dp.message(lambda message: message.text == "▶ Run Script")
async def run_script_handler(message: types.Message):
    await run_script(message)

@dp.message(lambda message: message.text == "⏹ Stop Script")
async def stop_script_handler(message: types.Message):
    await stop_script(message)

@dp.message(lambda message: message.text == "🗑 Delete Script")
async def delete_script_handler(message: types.Message):
    await delete_file(message)

@dp.message(lambda message: message.text == "📄 View Logs")
async def view_logs_handler(message: types.Message):
    await logs_command(message)

@dp.message(lambda message: message.text == "📝 Edit Script")
async def edit_script_handler(message: types.Message):
    await edit_command(message)

@dp.message(lambda message: message.text == "📊 Stats")
async def stats_handler(message: types.Message):
    await stats_command(message)

@dp.message(lambda message: message.text == "🏓 Ping")
async def ping_handler(message: types.Message):
    await ping_command(message)

@dp.message(lambda message: message.text == "ℹ️ Help")
async def help_handler(message: types.Message):
    await help_command(message)

@dp.message(lambda message: message.text == "👑 Admin Panel")
async def admin_panel_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ This command is only available to admins.",
                           reply_markup=create_menu_keyboard())
        return

    admin_buttons = [
        [KeyboardButton(text="🔄 Restart Bot"), KeyboardButton(text="🧹 Clear Logs")],
        [KeyboardButton(text="📊 System Info"), KeyboardButton(text="👥 User Stats")],
        [KeyboardButton(text="🔧 Maintenance"), KeyboardButton(text="📝 Broadcast")],
        [KeyboardButton(text="⬅️ Back to Main Menu")]
    ]
    admin_markup = ReplyKeyboardMarkup(keyboard=admin_buttons, resize_keyboard=True)
    await message.answer("👑 Admin Panel", reply_markup=admin_markup)

@dp.message(lambda message: message.text == "🔄 Restart Bot")
async def restart_bot_handler(message: types.Message):
    await restart_command(message)

@dp.message(lambda message: message.text == "🧹 Clear Logs")
async def clear_logs_handler(message: types.Message):
    await clearlogs_command(message)

@dp.message(lambda message: message.text == "📊 System Info")
async def system_info_handler(message: types.Message):
    await system_command(message)

@dp.message(lambda message: message.text == "👥 User Stats")
async def user_stats_handler(message: types.Message):
    await info_command(message)

@dp.message(lambda message: message.text == "🔧 Maintenance")
async def maintenance_handler(message: types.Message):
    await maintenance_command(message)

@dp.message(lambda message: message.text == "📝 Broadcast")
async def broadcast_handler(message: types.Message):
    user_steps[message.from_user.id] = "awaiting_broadcast"
    await message.answer("Please enter your broadcast message:")

@dp.message(lambda message: message.text == "⬅️ Back to Main Menu")
async def back_to_main_handler(message: types.Message):
    await message.answer("Returning to main menu...",
                        reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))

@dp.message(lambda msg: user_steps.get(msg.from_user.id) == "awaiting_broadcast")
async def handle_broadcast_message(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Unauthorized access.", reply_markup=create_menu_keyboard())
        return

    broadcast_text = message.text
    success = 0
    failed = 0

    status_msg = await message.answer(f"📢 Sending broadcast to {len(bot_users)} users...")

    for user_id in bot_users:
        try:
            await bot.send_message(user_id, f"📢 Admin Broadcast:\n\n{broadcast_text}")
            success += 1
        except Exception as e:
            failed += 1
            logging.error(f"Failed to send to {user_id}: {e}")

    await status_msg.edit_text(f"✅ Broadcast completed!\nSuccess: {success}\nFailed: {failed}")
    user_steps[message.from_user.id] = None

@dp.message(Command("terminal"))
async def terminal_command(message: types.Message):
    user_id = message.from_user.id
    user_steps[user_id] = "awaiting_terminal"
    await message.answer("Enter a shell command to execute:")

@dp.message(lambda msg: user_steps.get(msg.from_user.id) == "awaiting_terminal")
async def handle_terminal(message: types.Message):
    user_id = message.from_user.id
    command = message.text

    try:
        process = subprocess.Popen(command, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        output = stdout if stdout else stderr
        await message.answer(f"Output:\n```\n{output[:3900]}```",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
    except Exception as e:
        await message.answer(f"Error: {str(e)}",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))

    user_steps[user_id] = None

@dp.message(Command("console"))
async def console_command(message: types.Message):
    user_id = message.from_user.id
    if user_id not in running_processes or not running_processes[user_id]:
        await message.answer("No running processes found",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    running_scripts = list(running_processes[user_id].keys())
    keyboards = create_paginated_keyboard(running_scripts, "console", user_id, button_symbol="🖥")

    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select a script to view console output{page_info}:*",
                           reply_markup=markup)

@dp.callback_query(lambda c: c.data.startswith("console_"))
async def handle_console_callback(callback_query: CallbackQuery):
    _, user_id, script_name = callback_query.data.split("_", 2)
    user_id = int(user_id)

    if user_id not in running_processes or script_name not in running_processes[user_id]:
        try:
            keyboard = [[InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"console_{user_id}_{script_name}")]]
            markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await callback_query.answer("Process has ended or was not found")
            try:
                await callback_query.message.edit_text(
                    "⚠️ Process not found or already completed",
                    reply_markup=markup)
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    logging.error(f"Failed to edit message: {e}")
        except Exception as e:
            logging.error(f"Error in console callback: {e}")
        return

    process = running_processes[user_id][script_name]
    output = []

    try:
        if process.poll() is None:
            if process.stdout:
                import fcntl
                fd = process.stdout.fileno()
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

                try:
                    fl = fcntl.fcntl(process.stdout, fcntl.F_GETFL)
                    fcntl.fcntl(process.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)

                    try:
                        raw_data = process.stdout.read(4096)
                        data = raw_data.decode() if raw_data else ""
                    except (BlockingIOError, IOError):
                        data = ""

                    if data:
                        lines = data.strip().split('\n')
                        for line in lines:
                            script_name = script_name.replace('.py', '')
                            if not line.strip():
                                continue
                            if 'ERROR:' in line:
                                output.append(f"❌ Error: {line}")
                            elif 'INFO:' in line or 'WARNING:' in line:
                                output.append(f"⚡ {script_name}.py: Running (no new output)")
                            else:
                                output.append(f"⚡ {script_name}.py: {line.strip()}")
                    else:
                        if process.poll() is None:
                            process_output = ""
                            if process.stdout:
                                try:
                                    process_output = process.stdout.readline().decode().strip()
                                except:
                                    pass

                            if not process_output:
                                script_name = script_name.replace('.py', '')
                                output.extend([
                                    "INFO:aiogram.dispatcher:Start polling",
                                    f"INFO:aiogram.dispatcher:Run polling for bot @{script_name}",
                                    "INFO:aiogram.event:Bot is running",
                                    f"⚡ {script_name}: Bot is running"
                                ])
                        else:
                            output.append(f"⏹ {script_name}: Process ended")
                except BlockingIOError:
                    output.append(f"📄 {script_name}: Running (no new output)")
            else:
                output.append(f"📄 {script_name}: Running (no output stream available)")
        else:
            final_stdout, final_stderr = process.communicate()
            if final_stdout:
                output.append(f"📄 Final output:\n{final_stdout.decode()}")
            if final_stderr:
                output.append(f"❌ Errors:\n{final_stderr.decode()}")
            output.append(f"✅ {script_name}: Process completed")
            del running_processes[user_id][script_name]
    except Exception as e:
        output.append(f"❌ {script_name}: Error reading output: {str(e)}")

    keyboard = [[InlineKeyboardButton(
        text="🔄 Refresh",
        callback_data=f"console_{user_id}_{script_name}")]]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    message_text = "\n".join(output[-20:])
    await callback_query.message.answer(
        message_text[:4000] if message_text else "No output available",
        reply_markup=markup)

async def upload_instruction(message: types.Message):
    if maintenance_mode and message.from_user.id != ADMIN_ID:
        await message.answer(
            "⚠️ Bot is currently under maintenance. Please try again later.",
            reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    if message.from_user.id in banned_users:
        await message.answer("⛔ You are banned from using this bot.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    user_steps[message.from_user.id] = "awaiting_requirements"
    await message.answer(
        "📄 Please send your *requirements.txt* file as a document.",
        reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))

@dp.message(lambda msg: msg.document and msg.document.file_name == "requirements.txt")
async def handle_requirements_upload(message: types.Message):
    user_id = message.from_user.id
    user_dir = os.path.join(STORAGE_DIR, str(user_id))
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    file_path = os.path.join(user_dir, "requirements.txt")
    await bot.download(message.document.file_id, file_path)

    status_msg = await message.answer("🔄 Installing packages from requirements.txt...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", file_path])
        await status_msg.edit_text(
            "✅ Packages installed successfully! Now send your Python script.")
    except Exception as e:
        await status_msg.edit_text(f"⚠️ Error installing packages: {str(e)}")
        return

    user_steps[user_id] = "awaiting_python_file"

@dp.message(lambda msg: msg.document and msg.document.file_name.endswith('.py'))
async def handle_file_upload(message: types.Message):
    user_id = message.from_user.id
    user_dir = os.path.join(STORAGE_DIR, str(user_id))

    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    if message.document.file_size > MAX_FILE_SIZE:
        await message.answer(
            f"⚠️ File too large. Maximum size is {MAX_FILE_SIZE/1024/1024:.1f}MB",
            reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    user_limit = user_file_limits.get(user_id, USER_FILE_LIMIT)
    if len([f for f in os.listdir(user_dir) if f.endswith('.py')]) >= user_limit:
        await message.answer(f"⚠️ You can only upload {user_limit} Python files.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    file_path = os.path.join(user_dir, message.document.file_name)
    await bot.download(message.document.file_id, file_path)

    status_msg = await message.answer("🔄 Installing required packages...")
    try:
        install_requirements_from_script(file_path)
        process = subprocess.Popen(
            [sys.executable, "-m", "pip", "freeze"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, bufsize=1, universal_newlines=True)

        output = []
        for line in process.stdout:
            output.append(line)
            if len(output) >= 10:
                output = output[-10:]
            try:
                await status_msg.edit_text(
                    "🔄 Installing packages...\n```\n" + "".join(output) + "```")
            except:
                pass

        process.wait()
        if process.returncode == 0:
            await status_msg.edit_text(
                f"📂 File *{message.document.file_name}* uploaded and dependencies installed successfully!")
        else:
            error = process.stderr.read()
            await status_msg.edit_text(
                f"⚠️ File uploaded but some dependencies failed to install:\n```\n{error}```")
    except Exception as e:
        await status_msg.edit_text(f"⚠️ Error during installation: {str(e)}")

    user_steps[user_id] = None

def create_paginated_keyboard(items, callback_prefix, user_id,
                               chunk_size=8, button_symbol=""):
    keyboards = []
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i + chunk_size]
        keyboard = []
        for item in chunk:
            callback_data = f"{callback_prefix}_{user_id}_{item}"[:64]
            keyboard.append([
                InlineKeyboardButton(text=f"{button_symbol} {item}",
                                     callback_data=callback_data)
            ])
        keyboards.append(keyboard)
    return keyboards

async def run_script(message: types.Message):
    user_id = message.from_user.id
    user_dir = os.path.join(STORAGE_DIR, str(user_id))
    if not os.path.exists(user_dir):
        await message.answer(
            "⚠️ No Python files found. Please upload files using /upload first.",
            reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    files = [f for f in os.listdir(user_dir) if f.endswith(".py")]
    if not files:
        await message.answer("⚠️ No Python files found.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    keyboards = create_paginated_keyboard(files, "run", user_id, button_symbol="▶")
    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select a file to run{page_info}:*", reply_markup=markup)

async def stop_script(message: types.Message):
    user_id = message.from_user.id
    if user_id not in running_processes:
        await message.answer("⚠️ No running Python scripts found.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    running_files = list(running_processes.get(user_id, {}).keys())
    if not running_files:
        await message.answer("⚠️ No running Python scripts found.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    keyboards = create_paginated_keyboard(running_files, "stop", user_id, button_symbol="⏹")
    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select a file to stop{page_info}:*", reply_markup=markup)

async def delete_file(message: types.Message):
    user_id = message.from_user.id
    user_dir = os.path.join(STORAGE_DIR, str(user_id))
    files = [f for f in os.listdir(user_dir) if f.endswith(".py")]
    if not files:
        await message.answer("⚠️ No Python files found.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    keyboards = create_paginated_keyboard(files, "delete", user_id, button_symbol="🗑")
    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select a file to delete{page_info}:*", reply_markup=markup)

async def logs_command(message: types.Message):
    user_id = message.from_user.id
    user_dir = os.path.join(STORAGE_DIR, str(user_id))
    if not os.path.exists(user_dir):
        await message.answer(
            "⚠️ No scripts found. Please upload files using /upload first.",
            reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    files = [f for f in os.listdir(user_dir) if f.endswith(".py")]
    if not files:
        await message.answer("⚠️ No Python files found.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    keyboards = create_paginated_keyboard(files, "logs", user_id, button_symbol="📄")
    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select a file to view logs{page_info}:*", reply_markup=markup)

async def edit_command(message: types.Message):
    user_id = message.from_user.id
    user_dir = os.path.join(STORAGE_DIR, str(user_id))
    if not os.path.exists(user_dir):
        await message.answer(
            "⚠️ No Python files found. Upload files first using /upload",
            reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    files = [f for f in os.listdir(user_dir) if f.endswith('.py')]
    if not files:
        await message.answer("⚠️ No Python files found.",
                           reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))
        return

    keyboards = create_paginated_keyboard(files, "edit", user_id, button_symbol="📝")
    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select a file to edit{page_info}:*", reply_markup=markup)

@dp.callback_query(lambda c: c.data.startswith("run_"))
async def handle_run_callback(callback_query: CallbackQuery):
    try:
        _, user_id, filename = callback_query.data.split("_", 2)
        user_id = int(user_id)
        user_dir = os.path.join(STORAGE_DIR, str(user_id))
        file_path = os.path.join(user_dir, filename)

        status_msg = await callback_query.message.answer("▶️ Starting script...")
        await status_msg.edit_text("✅ Dependencies installed successfully.")

        process = subprocess.Popen(
            [sys.executable, os.path.basename(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=user_dir)

        running_processes.setdefault(user_id, {})[filename] = process
        file_last_run[f"{user_id}_{filename}"] = time.time()

        await asyncio.sleep(2)

        if process.poll() is not None:
            stdout, stderr = process.communicate()
            error_msg = stderr.decode() if stderr else stdout.decode()
            await callback_query.message.answer(
                f"⚠️ Script failed to start:\n```\n{error_msg[:1000]}```")
            if filename in running_processes.get(user_id, {}):
                del running_processes[user_id][filename]
        else:
            await callback_query.message.answer(f"🚀 Running {filename}...")

    except Exception as e:
        await callback_query.message.answer(f"⚠️ Error starting script: {str(e)}")

@dp.callback_query(lambda c: c.data.startswith("stop_"))
async def handle_stop_callback(callback_query: CallbackQuery):
    _, user_id, filename = callback_query.data.split("_", 2)
    user_id = int(user_id)
    if user_id in running_processes and filename in running_processes[user_id]:
        process = running_processes[user_id][filename]
        process.terminate()
        del running_processes[user_id][filename]
        await callback_query.message.answer(f"⏹ Stopped {filename}.")
    else:
        await callback_query.message.answer("⚠️ No running process found for this file.")

@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def handle_delete_callback(callback_query: CallbackQuery):
    _, user_id, filename = callback_query.data.split("_", 2)
    user_id = int(user_id)
    user_dir = os.path.join(STORAGE_DIR, str(user_id))
    file_path = os.path.join(user_dir, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        await callback_query.message.answer(f"🗑 Deleted {filename}.")
    else:
        await callback_query.message.answer("⚠️ File not found.")

@dp.callback_query(lambda c: c.data.startswith("logs_"))
async def handle_logs_callback(callback_query: CallbackQuery):
    _, user_id, filename = callback_query.data.split("_", 2)
    user_id = int(user_id)
    log_dir = os.path.join(LOGS_DIR, str(user_id))

    if os.path.exists(log_dir):
        log_files = sorted(
            [f for f in os.listdir(log_dir) if f.startswith(filename)],
            reverse=True)
        if log_files:
            latest_logs = []
            with open(os.path.join(log_dir, log_files[0]), 'r') as f:
                logs = f.readlines()
                latest_logs = logs[-6:] if len(logs) > 6 else logs

            log_text = f"📋 Latest logs for {filename}:\n\n" + "".join(latest_logs)
            await callback_query.message.answer(log_text[:4000])
        else:
            await callback_query.message.answer(f"⚠️ No logs found for {filename}")
    else:
        await callback_query.message.answer("⚠️ No logs available")

@dp.message(Command("processes"))
async def list_processes(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ This command is only available to admins.",
                           reply_markup=create_menu_keyboard(True))
        return

    process_list = []
    for user_id, scripts in running_processes.items():
        for script_name, process in scripts.items():
            if process.poll() is None:
                process_list.append(f"User {user_id}: {script_name}")

    if process_list:
        await message.answer("🔄 Running processes:\n" + "\n".join(process_list),
                           reply_markup=create_menu_keyboard(True))
    else:
        await message.answer("📝 No running processes.",
                           reply_markup=create_menu_keyboard(True))

@dp.message(Command("admin_stop"))
async def admin_stop(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ This command is only available to admins.",
                           reply_markup=create_menu_keyboard(True))
        return

    all_processes = []
    for user_id, scripts in running_processes.items():
        for script_name in scripts:
            all_processes.append(f"{user_id}_{script_name}")

    if not all_processes:
        await message.answer("📝 No running processes to stop.",
                           reply_markup=create_menu_keyboard(True))
        return

    keyboards = create_paginated_keyboard(all_processes, "adminstop",
                                          message.from_user.id, chunk_size=8, button_symbol="⏹")
    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select process to stop{page_info}:*", reply_markup=markup)

@dp.callback_query(lambda c: c.data.startswith("adminstop_"))
async def handle_admin_stop_callback(callback_query: CallbackQuery):
    _, admin_id, process_info = callback_query.data.split("_", 2)
    if int(admin_id) != ADMIN_ID:
        await callback_query.message.answer("⛔ Unauthorized access.")
        return

    user_id, script_name = process_info.split("_", 1)
    user_id = int(user_id)

    if user_id in running_processes and script_name in running_processes[user_id]:
        running_processes[user_id][script_name].terminate()
        del running_processes[user_id][script_name]
        await callback_query.message.answer(
            f"✅ Stopped {script_name} for user {user_id}")
    else:
        await callback_query.message.answer("⚠️ Process not found.")

@dp.message(Command("admin_start"))
async def admin_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ This command is only available to admins.",
                           reply_markup=create_menu_keyboard(True))
        return

    available_scripts = []
    for user_dir in os.listdir(STORAGE_DIR):
        if os.path.isdir(os.path.join(STORAGE_DIR, user_dir)):
            user_id = user_dir
            for script in os.listdir(os.path.join(STORAGE_DIR, user_dir)):
                if script.endswith('.py'):
                    available_scripts.append(f"{user_id}_{script}")

    if not available_scripts:
        await message.answer("📝 No scripts available.",
                           reply_markup=create_menu_keyboard(True))
        return

    keyboards = create_paginated_keyboard(available_scripts, "adminstart",
                                          message.from_user.id, chunk_size=8, button_symbol="▶")
    for i, keyboard in enumerate(keyboards):
        page_info = f" (Page {i+1}/{len(keyboards)})" if len(keyboards) > 1 else ""
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(f"🔹 *Select script to start{page_info}:*", reply_markup=markup)

@dp.callback_query(lambda c: c.data.startswith("adminstart_"))
async def handle_admin_start_callback(callback_query: CallbackQuery):
    _, admin_id, process_info = callback_query.data.split("_", 2)
    if int(admin_id) != ADMIN_ID:
        await callback_query.message.answer("⛔ Unauthorized access.")
        return

    user_id, script_name = process_info.split("_", 1)
    user_dir = os.path.join(STORAGE_DIR, user_id)

    try:
        process = subprocess.Popen(
            [sys.executable, script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=user_dir)
        running_processes.setdefault(int(user_id), {})[script_name] = process
        await callback_query.message.answer(
            f"✅ Started {script_name} for user {user_id}")
    except Exception as e:
        await callback_query.message.answer(f"⚠️ Error: {str(e)}")

@dp.message(Command("broadcast"))
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ This command is only available to admins.",
                           reply_markup=create_menu_keyboard(True))
        return

    broadcast_text = message.text.replace("/broadcast", "", 1).strip()
    if not broadcast_text:
        await message.answer("⚠️ Usage: /broadcast <message>",
                           reply_markup=create_menu_keyboard(True))
        return

    for user_id in bot_users:
        try:
            await bot.send_message(user_id, f"📢 {broadcast_text}")
        except Exception as e:
            logging.error(f"Failed to send broadcast to {user_id}: {e}")

    await message.answer("✅ Broadcast sent.", reply_markup=create_menu_keyboard(True))

@dp.message(Command("maintenance"))
async def maintenance_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ This command is only available to admins.",
                           reply_markup=create_menu_keyboard())
        return

    status = "🔴 OFF" if not maintenance_mode else "🟢 ON"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Turn ON", callback_data="maintenance_on"),
            InlineKeyboardButton(text="🔴 Turn OFF", callback_data="maintenance_off")
        ]
    ])

    await message.answer(
        f"🔧 Maintenance Mode: {status}\nSelect action:",
        reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("maintenance_"))
async def handle_maintenance_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("⛔ Unauthorized access", show_alert=True)
        return

    global maintenance_mode
    action = callback_query.data.split("_")[1]
    maintenance_mode = action == "on"
    status = "🟢 ON" if maintenance_mode else "🔴 OFF"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Turn ON", callback_data="maintenance_on"),
            InlineKeyboardButton(text="🔴 Turn OFF", callback_data="maintenance_off")
        ]
    ])

    await callback_query.message.edit_text(
        f"🔧 Maintenance Mode: {status}\nSelect action:",
        reply_markup=keyboard)
    await callback_query.answer(f"Maintenance mode turned {action.upper()}")

@dp.message(Command("ping"))
async def ping_command(message: types.Message):
    await message.answer("🏓 Pong!",
                       reply_markup=create_menu_keyboard(message.from_user.id == ADMIN_ID))

@dp.message(Command("allow"))
async def allow_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Only admins can use this command.",
                           reply_markup=create_menu_keyboard())
        return

    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("⚠️ Incorrect usage. Use: /allow <user_id> <file_limit>",
                               reply_markup=create_menu_keyboard(True))
            return

        user_id = int(parts[1])
        file_limit = int(parts[2])
        user_file_limits[user_id] = file_limit
        await message.answer(
            f"✅ User {user_id} can now upload up to {file_limit} files.",
            reply_markup=create_menu_keyboard(True))
        try:
            await bot.send_message(
                user_id, f"You can now upload up to {file_limit} Python files!")
        except Exception as e:
            await message.answer(f"⚠️ Failed to notify user {user_id}: {e}",
                               reply_markup=create_menu_keyboard(True))
    except ValueError:
        await message.answer(
            "⚠️ Invalid input. User ID and file limit must be integers.",
            reply_markup=create_menu_keyboard(True))
    except Exception as e:
        await message.answer(f"⚠️ An error occurred: {e}",
                           reply_markup=create_menu_keyboard(True))

@dp.message(Command("list"))
async def list_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Only admins can use this command.",
                           reply_markup=create_menu_keyboard())
        return

    if not user_file_limits:
        await message.answer("📝 No users with increased file limits.",
                           reply_markup=create_menu_keyboard(True))
        return

    user_list = ""
    for user_id, limit in user_file_limits.items():
        user_list += f"User {user_id}: {limit} files\n"

    await message.answer(f"✅ Users with increased file limits:\n{user_list}",
                       reply_markup=create_menu_keyboard(True))

# ============================================================
# RENDER KE LIYE WEB SERVER (Zaroori hai!)
# ============================================================
from aiohttp import web

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

async def main():
    try:
        print("Starting bot...")
        # Web server start karo (Render ke liye)
        await start_web_server()
        dp.bot = bot
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    except Exception as e:
        print(f"Error starting bot: {e}")
        raise e

if __name__ == "__main__":
    try:
        os.makedirs(STORAGE_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)
        os.makedirs(REQUIREMENTS_DIR, exist_ok=True)
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")