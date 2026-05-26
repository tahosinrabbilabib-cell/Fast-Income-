import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ===== CONFIGURATION =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))  # আপনার Telegram User ID
REFERRAL_BONUS = float(os.environ.get("REFERRAL_BONUS", "5.0"))  # প্রতি রেফারেলে কত BDT
MIN_WITHDRAW = float(os.environ.get("MIN_WITHDRAW", "100.0"))  # সর্বনিম্ন উইথড্র
WITHDRAW_FEE = float(os.environ.get("WITHDRAW_FEE", "5.0"))  # উইথড্র ফি

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== DATABASE SETUP =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance REAL DEFAULT 0.0,
        total_income REAL DEFAULT 0.0,
        referred_by INTEGER,
        join_date TEXT,
        is_banned INTEGER DEFAULT 0
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        reward REAL,
        task_type TEXT DEFAULT 'fixed',
        is_active INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS user_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        task_id INTEGER,
        status TEXT DEFAULT 'pending',
        submitted_at TEXT,
        proof TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        method TEXT,
        account TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TEXT
    )""")
    
    # Default tasks
    c.execute("SELECT COUNT(*) FROM tasks")
    if c.fetchone()[0] == 0:
        default_tasks = [
            ("Gmail কাজ 📧", "নতুন Gmail একাউন্ট তৈরি করুন এবং স্ক্রিনশট পাঠান", 10.0, "fixed"),
            ("YouTube কাজ 🎬", "চ্যানেল Subscribe করুন এবং স্ক্রিনশট পাঠান", 8.0, "fixed"),
            ("Facebook কাজ 📘", "পেজ Like করুন এবং স্ক্রিনশট পাঠান", 7.0, "fixed"),
            ("App Install কাজ 📱", "App ডাউনলোড করুন এবং স্ক্রিনশট পাঠান", 12.0, "fixed"),
        ]
        c.executemany("INSERT INTO tasks (title, description, reward, task_type, created_at) VALUES (?,?,?,?,?)",
                      [(t[0], t[1], t[2], t[3], datetime.now().isoformat()) for t in default_tasks])
    
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("bot_data.db")

# ===== USER HELPERS =====
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id, username, full_name, referred_by=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, referred_by, join_date) VALUES (?,?,?,?,?)",
              (user_id, username, full_name, referred_by, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance=balance+?, total_income=total_income+? WHERE user_id=?",
              (amount, amount if amount > 0 else 0, user_id))
    conn.commit()
    conn.close()

def get_referral_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

# ===== MAIN KEYBOARD =====
def main_keyboard():
    keyboard = [
        [KeyboardButton("📋 কাজ"), KeyboardButton("💰 ব্যালেন্স")],
        [KeyboardButton("🏦 টাকা উতোলন"), KeyboardButton("🎁 Invite & Earn")],
        [KeyboardButton("🆘 সাপোর্ট"), KeyboardButton("🆕 আমি নতুন")],
        [KeyboardButton("🎯 মিশন")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ===== /START COMMAND =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referred_by = None
    
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0].replace("ref_", ""))
            if referred_by == user.id:
                referred_by = None
        except:
            referred_by = None
    
    existing = get_user(user.id)
    
    if not existing:
        create_user(user.id, user.username or "", user.full_name, referred_by)
        
        # Referral bonus দিন
        if referred_by:
            referrer = get_user(referred_by)
            if referrer and not referrer[7]:  # not banned
                update_balance(referred_by, REFERRAL_BONUS)
                try:
                    await context.bot.send_message(
                        chat_id=referred_by,
                        text=f"🎉 অভিনন্দন! আপনার রেফারেল লিংক দিয়ে একজন নতুন সদস্য যোগ দিয়েছে!\n"
                             f"✅ আপনার একাউন্টে {REFERRAL_BONUS} BDT যোগ হয়েছে!"
                    )
                except:
                    pass
        
        welcome_text = (
            f"🌟 স্বাগতম, {user.first_name}!\n\n"
            f"আমাদের Income Bot-এ আপনাকে স্বাগত জানাই! 🎊\n\n"
            f"✅ ছোট ছোট কাজ করে টাকা আয় করুন\n"
            f"✅ বন্ধুদের রেফার করে বোনাস নিন\n"
            f"✅ Bkash/Nagad/USDT-এ টাকা তুলুন\n\n"
            f"নিচের মেনু থেকে শুরু করুন 👇"
        )
    else:
        if existing[7]:  # banned
            await update.message.reply_text("❌ আপনার একাউন্ট বন্ধ করা হয়েছে। সাপোর্টে যোগাযোগ করুন।")
            return
        welcome_text = f"👋 আবার স্বাগতম, {user.first_name}!\n\nনিচের মেনু থেকে কাজ শুরু করুন 👇"
    
    await update.message.reply_text(welcome_text, reply_markup=main_keyboard())

# ===== BALANCE =====
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = get_user(update.effective_user.id)
    if not user_data:
        await update.message.reply_text("প্রথমে /start দিন।")
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_tasks WHERE user_id=? AND status='approved'", (user_data[0],))
    completed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM user_tasks WHERE user_id=? AND status='pending'", (user_data[0],))
    pending = c.fetchone()[0]
    c.execute("SELECT SUM(amount) FROM withdrawals WHERE user_id=? AND status='pending'", (user_data[0],))
    pending_withdraw = c.fetchone()[0] or 0
    conn.close()
    
    ref_count = get_referral_count(user_data[0])
    
    text = (
        f"💰 *আপনার ব্যালেন্স*\n"
        f"{'─'*25}\n"
        f"🔥 ব্যালেন্স: {user_data[3]:.2f} BDT\n"
        f"⏳ পেন্ডিং (উইথড্র): {pending_withdraw:.2f} BDT\n"
        f"📊 Total Income: {user_data[4]:.2f} BDT\n"
        f"{'─'*25}\n"
        f"✅ সম্পন্ন কাজ: {completed} টি\n"
        f"⏸ রিভিউতে আছে: {pending} টি\n"
        f"👥 রেফারেল: {ref_count} জন"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ===== TASKS =====
async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("প্রথমে /start দিন।")
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT task_id, title, reward FROM tasks WHERE is_active=1")
    tasks = c.fetchall()
    conn.close()
    
    if not tasks:
        await update.message.reply_text("⚠️ এখন কোনো কাজ নেই। পরে আবার চেক করুন।")
        return
    
    keyboard = []
    for task in tasks:
        keyboard.append([InlineKeyboardButton(
            f"{task[1]} — {task[2]} BDT",
            callback_data=f"task_{task[0]}"
        )])
    
    await update.message.reply_text(
        "📋 *নিচের কাজগুলো থেকে একটি সিলেক্ট করুন:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def task_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.replace("task_", ""))
    user_id = query.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    task = c.fetchone()
    
    # ইতোমধ্যে করেছে কিনা চেক
    c.execute("SELECT status FROM user_tasks WHERE user_id=? AND task_id=? AND status IN ('pending','approved')",
              (user_id, task_id))
    already = c.fetchone()
    conn.close()
    
    if already:
        status = "✅ অনুমোদিত" if already[0] == "approved" else "⏳ রিভিউতে আছে"
        await query.edit_message_text(f"আপনি এই কাজটি ইতোমধ্যে করেছেন।\nস্ট্যাটাস: {status}")
        return
    
    text = (
        f"📌 *{task[1]}*\n\n"
        f"📝 বিবরণ: {task[2]}\n"
        f"💵 পুরস্কার: {task[3]} BDT\n\n"
        f"✅ কাজটি সম্পন্ন করুন এবং স্ক্রিনশট পাঠান।"
    )
    
    keyboard = [[InlineKeyboardButton("📸 প্রমাণ পাঠান (স্ক্রিনশট)", callback_data=f"submit_{task_id}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def submit_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.replace("submit_", ""))
    context.user_data["submitting_task"] = task_id
    await query.edit_message_text("📸 এখন কাজের স্ক্রিনশট/ছবি পাঠান:")

async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    task_id = context.user_data.get("submitting_task")
    
    if not task_id:
        return
    
    proof = ""
    if update.message.photo:
        proof = update.message.photo[-1].file_id
    elif update.message.text:
        proof = update.message.text
    
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO user_tasks (user_id, task_id, status, submitted_at, proof) VALUES (?,?,?,?,?)",
              (user_id, task_id, "pending", datetime.now().isoformat(), proof))
    conn.commit()
    
    c.execute("SELECT title FROM tasks WHERE task_id=?", (task_id,))
    task = c.fetchone()
    conn.close()
    
    del context.user_data["submitting_task"]
    
    await update.message.reply_text(
        f"✅ আপনার কাজ জমা দেওয়া হয়েছে!\n"
        f"কাজ: {task[0]}\n"
        f"স্ট্যাটাস: ⏳ রিভিউতে আছে\n\n"
        f"Admin অনুমোদন করলে টাকা যোগ হবে।",
        reply_markup=main_keyboard()
    )
    
    # Admin-কে নোটিফাই করুন
    try:
        msg = f"🆕 নতুন কাজ জমা!\nUser: {update.effective_user.full_name} (ID: {user_id})\nকাজ: {task[0]}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
        if update.message.photo:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=proof,
                caption=f"/approve_{user_id}_{task_id} অনুমোদন\n/reject_{user_id}_{task_id} বাতিল")
    except:
        pass

# ===== WITHDRAW =====
async def show_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = get_user(update.effective_user.id)
    if not user_data:
        return
    
    if user_data[3] < MIN_WITHDRAW:
        await update.message.reply_text(
            f"❌ উইথড্র করতে সর্বনিম্ন {MIN_WITHDRAW} BDT লাগবে।\n"
            f"আপনার ব্যালেন্স: {user_data[3]:.2f} BDT"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton(f"💙 বিকাশ → সর্বনিম্ন: {MIN_WITHDRAW}টা(-{WITHDRAW_FEE})", callback_data="withdraw_bkash")],
        [InlineKeyboardButton(f"🟠 নগদ → সর্বনিম্ন: {MIN_WITHDRAW}টা(-{WITHDRAW_FEE})", callback_data="withdraw_nagad")],
        [InlineKeyboardButton(f"💚 USDT (BEP-20) → সর্বনিম্ন: 0.25(-0.05)", callback_data="withdraw_usdt")],
        [InlineKeyboardButton("🔙 ফিরে যান", callback_data="back_main")],
    ]
    await update.message.reply_text(
        "🏦 *টাকা তোলার মাধ্যম সিলেক্ট করুন:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("withdraw_", "")
    context.user_data["withdraw_method"] = method
    
    method_names = {"bkash": "বিকাশ", "nagad": "নগদ", "usdt": "USDT"}
    await query.edit_message_text(
        f"📱 আপনার {method_names.get(method, method)} নম্বর/ঠিকানা লিখুন:"
    )
    context.user_data["awaiting_withdraw_account"] = True

async def process_withdraw_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_withdraw_account"):
        return
    
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    method = context.user_data.get("withdraw_method", "")
    account = update.message.text
    
    context.user_data["awaiting_withdraw_account"] = False
    context.user_data["withdraw_account"] = account
    context.user_data["awaiting_withdraw_amount"] = True
    
    await update.message.reply_text(
        f"💰 কত টাকা তুলতে চান?\n"
        f"(সর্বনিম্ন: {MIN_WITHDRAW} BDT, আপনার ব্যালেন্স: {user_data[3]:.2f} BDT)\n\n"
        f"শুধু সংখ্যা লিখুন:"
    )

async def process_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_withdraw_amount"):
        return
    
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    try:
        amount = float(update.message.text)
    except:
        await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন।")
        return
    
    if amount < MIN_WITHDRAW:
        await update.message.reply_text(f"❌ সর্বনিম্ন {MIN_WITHDRAW} BDT উইথড্র করতে হবে।")
        return
    
    if amount > user_data[3]:
        await update.message.reply_text(f"❌ অপর্যাপ্ত ব্যালেন্স। আপনার ব্যালেন্স: {user_data[3]:.2f} BDT")
        return
    
    method = context.user_data.get("withdraw_method", "")
    account = context.user_data.get("withdraw_account", "")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user_id))
    c.execute("INSERT INTO withdrawals (user_id, amount, method, account, requested_at) VALUES (?,?,?,?,?)",
              (user_id, amount, method, account, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    context.user_data["awaiting_withdraw_amount"] = False
    
    await update.message.reply_text(
        f"✅ উইথড্র রিকোয়েস্ট জমা হয়েছে!\n\n"
        f"💰 পরিমাণ: {amount:.2f} BDT\n"
        f"📱 মাধ্যম: {method}\n"
        f"📋 একাউন্ট: {account}\n\n"
        f"⏳ ২৪ ঘন্টার মধ্যে প্রক্রিয়া করা হবে।",
        reply_markup=main_keyboard()
    )
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💸 নতুন উইথড্র রিকোয়েস্ট!\n"
                 f"User: {update.effective_user.full_name} (ID: {user_id})\n"
                 f"Amount: {amount} BDT\nMethod: {method}\nAccount: {account}"
        )
    except:
        pass

# ===== INVITE & EARN =====
async def invite_earn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    ref_count = get_referral_count(user_id)
    
    text = (
        f"🎁 *Invite & Earn*\n\n"
        f"আপনার রেফারেল লিংক:\n"
        f"`{ref_link}`\n\n"
        f"👥 মোট রেফারেল: {ref_count} জন\n"
        f"💰 প্রতি রেফারেলে: {REFERRAL_BONUS} BDT\n"
        f"🏆 মোট রেফারেল আয়: {ref_count * REFERRAL_BONUS:.2f} BDT\n\n"
        f"👆 লিংকটি কপি করে বন্ধুদের পাঠান!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ===== SUPPORT =====
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆘 *সাপোর্ট*\n\n"
        f"কোনো সমস্যা হলে Admin-এর সাথে যোগাযোগ করুন:\n"
        f"👤 @YourAdminUsername\n\n"  # আপনার username দিন
        f"অথবা নিচে আপনার সমস্যা লিখুন:",
        parse_mode="Markdown"
    )
    context.user_data["awaiting_support"] = True

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_support"):
        return
    
    user = update.effective_user
    msg = update.message.text
    context.user_data["awaiting_support"] = False
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 সাপোর্ট মেসেজ!\nFrom: {user.full_name} (ID: {user.id})\n\n{msg}"
        )
    except:
        pass
    
    await update.message.reply_text("✅ আপনার মেসেজ Admin-এর কাছে পাঠানো হয়েছে। ধন্যবাদ!", reply_markup=main_keyboard())

# ===== NEW USER GUIDE =====
async def new_user_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆕 *নতুনদের জন্য গাইড*\n\n"
        "1️⃣ *কাজ* বাটনে চাপুন → কাজ সিলেক্ট করুন\n"
        "2️⃣ কাজের নির্দেশ পড়ুন এবং সম্পন্ন করুন\n"
        "3️⃣ স্ক্রিনশট পাঠান প্রমাণ হিসেবে\n"
        "4️⃣ Admin অনুমোদন করলে টাকা যোগ হবে\n"
        "5️⃣ সর্বনিম্ন ১০০ BDT হলে উইথড্র করুন\n\n"
        f"💡 বন্ধুদের রেফার করলে প্রতিজনের জন্য {REFERRAL_BONUS} BDT পাবেন!",
        parse_mode="Markdown"
    )

# ===== MISSION =====
async def mission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 *মিশন*\n\n"
        "ℹ️ বর্তমানে কোনো মিশন চালু নেই।\n"
        "দয়া করে পরবর্তীতে আবার চেক করুন।",
        parse_mode="Markdown"
    )

# ===== ADMIN COMMANDS =====
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    parts = update.message.text.split("_")
    if len(parts) < 3:
        return
    
    user_id = int(parts[1])
    task_id = int(parts[2])
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT reward FROM tasks WHERE task_id=?", (task_id,))
    task = c.fetchone()
    c.execute("UPDATE user_tasks SET status='approved' WHERE user_id=? AND task_id=?", (user_id, task_id))
    conn.commit()
    conn.close()
    
    if task:
        update_balance(user_id, task[0])
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 অভিনন্দন! আপনার কাজ অনুমোদিত হয়েছে!\n✅ {task[0]} BDT আপনার একাউন্টে যোগ হয়েছে!"
            )
        except:
            pass
    
    await update.message.reply_text(f"✅ User {user_id} এর কাজ অনুমোদন করা হয়েছে।")

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    parts = update.message.text.split("_")
    if len(parts) < 3:
        return
    
    user_id = int(parts[1])
    task_id = int(parts[2])
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE user_tasks SET status='rejected' WHERE user_id=? AND task_id=?", (user_id, task_id))
    conn.commit()
    conn.close()
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ দুঃখিত! আপনার কাজটি গ্রহণ করা হয়নি। সঠিকভাবে কাজ করে আবার চেষ্টা করুন।"
        )
    except:
        pass
    
    await update.message.reply_text(f"❌ User {user_id} এর কাজ বাতিল করা হয়েছে।")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM user_tasks WHERE status='pending'")
    pending_tasks = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
    pending_withdrawals = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    conn.close()
    
    await update.message.reply_text(
        f"👑 *Admin Panel*\n\n"
        f"👥 মোট ইউজার: {total_users}\n"
        f"⏳ পেন্ডিং কাজ: {pending_tasks}\n"
        f"💸 পেন্ডিং উইথড্র: {pending_withdrawals}\n"
        f"💰 মোট ব্যালেন্স (সব ইউজার): {total_balance:.2f} BDT\n\n"
        f"*কমান্ড:*\n"
        f"/addtask - নতুন কাজ যোগ\n"
        f"/users - সব ইউজার দেখুন\n"
        f"/pending - পেন্ডিং কাজ\n"
        f"/addbalance [user_id] [amount] - ব্যালেন্স যোগ",
        parse_mode="Markdown"
    )

async def add_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("ব্যবহার: /addbalance [user_id] [amount]")
        return
    
    try:
        user_id = int(args[0])
        amount = float(args[1])
        update_balance(user_id, amount)
        await update.message.reply_text(f"✅ User {user_id} কে {amount} BDT দেওয়া হয়েছে।")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎁 Admin আপনার একাউন্টে {amount} BDT যোগ করেছেন!"
            )
        except:
            pass
    except:
        await update.message.reply_text("❌ ভুল ইনপুট।")

# ===== MESSAGE HANDLER =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📋 কাজ":
        await show_tasks(update, context)
    elif text == "💰 ব্যালেন্স":
        await show_balance(update, context)
    elif text == "🏦 টাকা উতোলন":
        await show_withdraw(update, context)
    elif text == "🎁 Invite & Earn":
        await invite_earn(update, context)
    elif text == "🆘 সাপোর্ট":
        await support(update, context)
    elif text == "🆕 আমি নতুন":
        await new_user_guide(update, context)
    elif text == "🎯 মিশন":
        await mission(update, context)
    elif context.user_data.get("awaiting_support"):
        await handle_support_message(update, context)
    elif context.user_data.get("awaiting_withdraw_account"):
        await process_withdraw_account(update, context)
    elif context.user_data.get("awaiting_withdraw_amount"):
        await process_withdraw_amount(update, context)
    elif context.user_data.get("submitting_task") and not update.message.photo:
        await receive_proof(update, context)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("submitting_task"):
        await receive_proof(update, context)

# ===== CALLBACK HANDLER =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("task_"):
        await task_detail(update, context)
    elif data.startswith("submit_"):
        await submit_task(update, context)
    elif data.startswith("withdraw_"):
        await withdraw_method(update, context)
    elif data == "back_main":
        await query.edit_message_text("প্রধান মেনু:")

# ===== ADMIN COMMAND HANDLERS =====
async def handle_admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    text = update.message.text
    if text.startswith("/approve_"):
        await admin_approve(update, context)
    elif text.startswith("/reject_"):
        await admin_reject(update, context)

# ===== MAIN =====
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("addbalance", add_balance_cmd))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/approve_|^/reject_"), handle_admin_commands))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("✅ Bot চালু হয়েছে!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
