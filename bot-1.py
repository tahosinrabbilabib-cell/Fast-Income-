import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
REFERRAL_BONUS = float(os.environ.get("REFERRAL_BONUS", "5.0"))
MIN_WITHDRAW = float(os.environ.get("MIN_WITHDRAW", "100.0"))
WITHDRAW_FEE = float(os.environ.get("WITHDRAW_FEE", "5.0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance REAL DEFAULT 0,
        total_income REAL DEFAULT 0,
        referred_by INTEGER,
        join_date TEXT,
        is_banned INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        reward REAL,
        is_active INTEGER DEFAULT 1
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
    c.execute("SELECT COUNT(*) FROM tasks")
    if c.fetchone()[0] == 0:
        tasks = [
            ("📧 Gmail কাজ", "নতুন Gmail একাউন্ট খুলুন এবং স্ক্রিনশট পাঠান।\n\nনিয়ম:\n1. gmail.com এ যান\n2. নতুন একাউন্ট তৈরি করুন\n3. স্ক্রিনশট তুলুন\n4. জমা দিন বাটনে চাপুন", 10.0),
            ("📸 Instagram কাজ", "নতুন Instagram একাউন্ট খুলুন এবং স্ক্রিনশট পাঠান।\n\nনিয়ম:\n1. instagram.com এ যান\n2. নতুন একাউন্ট তৈরি করুন\n3. স্ক্রিনশট তুলুন\n4. জমা দিন বাটনে চাপুন", 8.0),
            ("🎬 YouTube কাজ", "YouTube চ্যানেল Subscribe করুন এবং স্ক্রিনশট পাঠান।", 7.0),
            ("📱 App Install কাজ", "App ডাউনলোড করুন এবং স্ক্রিনশট পাঠান।", 12.0),
        ]
        for t in tasks:
            c.execute("INSERT INTO tasks (title, description, reward) VALUES (?,?,?)", t)
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect("bot.db")

def get_user(uid):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    u = cur.fetchone()
    c.close()
    return u

def add_user(uid, uname, name, ref=None):
    c = db()
    cur = c.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id,username,full_name,referred_by,join_date) VALUES (?,?,?,?,?)",
                (uid, uname, name, ref, datetime.now().isoformat()))
    c.commit()
    c.close()

def add_balance(uid, amount):
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE users SET balance=balance+?, total_income=total_income+? WHERE user_id=? AND ?> 0",
                (amount, amount, uid, amount))
    cur.execute("UPDATE users SET balance=balance+? WHERE user_id=? AND ?<=0",
                (amount, uid, amount))
    c.commit()
    c.close()

def main_menu():
    kb = [
        [KeyboardButton("📋 কাজ"), KeyboardButton("💰 ব্যালেন্স")],
        [KeyboardButton("🏦 টাকা উতোলন"), KeyboardButton("🎁 Invite & Earn")],
        [KeyboardButton("🆘 সাপোর্ট"), KeyboardButton("🆕 আমি নতুন")],
        [KeyboardButton("🎯 মিশন")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args
    ref = None
    if args and args[0].startswith("ref_"):
        try:
            ref = int(args[0][4:])
            if ref == user.id:
                ref = None
        except:
            ref = None

    existing = get_user(user.id)
    if not existing:
        add_user(user.id, user.username or "", user.full_name, ref)
        if ref:
            refuser = get_user(ref)
            if refuser and not refuser[7]:
                c = db()
                cur = c.cursor()
                cur.execute("UPDATE users SET balance=balance+?, total_income=total_income+? WHERE user_id=?",
                            (REFERRAL_BONUS, REFERRAL_BONUS, ref))
                c.commit()
                c.close()
                try:
                    await ctx.bot.send_message(ref, f"🎉 নতুন রেফারেল! {REFERRAL_BONUS} BDT যোগ হয়েছে!")
                except:
                    pass
        text = f"🌟 স্বাগতম {user.first_name}!\n\n✅ কাজ করে টাকা আয় করুন\n✅ বন্ধুদের রেফার করুন\n✅ Bkash/Nagad-এ টাকা তুলুন\n\nনিচের মেনু থেকে শুরু করুন 👇"
    else:
        if existing[7]:
            await update.message.reply_text("❌ আপনার একাউন্ট বন্ধ।")
            return
        text = f"👋 আবার স্বাগতম {user.first_name}! 👇"
    await update.message.reply_text(text, reply_markup=main_menu())

async def balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("প্রথমে /start দিন।")
        return
    c = db()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM user_tasks WHERE user_id=? AND status='approved'", (u[0],))
    done = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM user_tasks WHERE user_id=? AND status='pending'", (u[0],))
    pend = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (u[0],))
    refs = cur.fetchone()[0]
    c.close()
    await update.message.reply_text(
        f"💰 *আপনার ব্যালেন্স*\n"
        f"{'─'*20}\n"
        f"🔥 ব্যালেন্স: {u[3]:.2f} BDT\n"
        f"📊 মোট আয়: {u[4]:.2f} BDT\n"
        f"{'─'*20}\n"
        f"✅ সম্পন্ন কাজ: {done} টি\n"
        f"⏳ রিভিউতে: {pend} টি\n"
        f"👥 রেফারেল: {refs} জন",
        parse_mode="Markdown"
    )

async def tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    c = db()
    cur = c.cursor()
    cur.execute("SELECT task_id, title, reward FROM tasks WHERE is_active=1")
    tlist = cur.fetchall()
    c.close()
    if not tlist:
        await update.message.reply_text("⚠️ এখন কোনো কাজ নেই।")
        return
    kb = [[InlineKeyboardButton(f"{t[1]} — {t[2]} BDT", callback_data=f"task_{t[0]}")] for t in tlist]
    await update.message.reply_text("📋 *কাজ সিলেক্ট করুন:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u:
        return
    if u[3] < MIN_WITHDRAW:
        await update.message.reply_text(f"❌ সর্বনিম্ন {MIN_WITHDRAW} BDT লাগবে।\nআপনার ব্যালেন্স: {u[3]:.2f} BDT")
        return
    kb = [
        [InlineKeyboardButton(f"💙 বিকাশ (সর্বনিম্ন {MIN_WITHDRAW}৳)", callback_data="w_bkash")],
        [InlineKeyboardButton(f"🟠 নগদ (সর্বনিম্ন {MIN_WITHDRAW}৳)", callback_data="w_nagad")],
        [InlineKeyboardButton("💚 USDT BEP-20", callback_data="w_usdt")],
    ]
    await update.message.reply_text("🏦 *পদ্ধতি সিলেক্ট করুন:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def invite(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    me = await ctx.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    c = db()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    refs = cur.fetchone()[0]
    c.close()
    await update.message.reply_text(
        f"🎁 *Invite & Earn*\n\n"
        f"আপনার লিংক:\n`{link}`\n\n"
        f"👥 রেফারেল: {refs} জন\n"
        f"💰 প্রতি রেফারেলে: {REFERRAL_BONUS} BDT\n"
        f"🏆 মোট রেফারেল আয়: {refs * REFERRAL_BONUS:.2f} BDT\n\n"
        f"লিংকটি বন্ধুদের পাঠান!",
        parse_mode="Markdown"
    )

async def support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["support"] = True
    await update.message.reply_text("🆘 সমস্যার কথা লিখুন, Admin-এর কাছে পাঠানো হবে:")

async def new_guide(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆕 *নতুনদের গাইড*\n\n"
        "1️⃣ 📋 কাজ বাটনে চাপুন\n"
        "2️⃣ কাজ সিলেক্ট করুন\n"
        "3️⃣ নির্দেশনা পড়ুন ও কাজ করুন\n"
        "4️⃣ স্ক্রিনশট তুলুন\n"
        "5️⃣ ✅ জমা দিন বাটনে চাপুন\n"
        "6️⃣ Admin অনুমোদন করলে টাকা পাবেন\n\n"
        f"💡 রেফারেল করলে প্রতিজনে {REFERRAL_BONUS} BDT!",
        parse_mode="Markdown"
    )

async def mission(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 বর্তমানে কোনো মিশন নেই। পরে আবার দেখুন।")

async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data.startswith("task_"):
        tid = int(data[5:])
        c = db()
        cur = c.cursor()
        cur.execute("SELECT * FROM tasks WHERE task_id=?", (tid,))
        t = cur.fetchone()
        cur.execute("SELECT status FROM user_tasks WHERE user_id=? AND task_id=? AND status IN ('pending','approved')", (uid, tid))
        already = cur.fetchone()
        c.close()
        if already:
            s = "✅ অনুমোদিত" if already[0] == "approved" else "⏳ রিভিউতে"
            await q.edit_message_text(f"আপনি এই কাজ ইতোমধ্যে করেছেন।\nস্ট্যাটাস: {s}")
            return
        kb = [
            [InlineKeyboardButton("✅ জমা দিন", callback_data=f"submit_{tid}")],
            [InlineKeyboardButton("❌ কাজ বাতিল করুন", callback_data="cancel_task")],
        ]
        await q.edit_message_text(
            f"📌 *{t[1]}*\n\n{t[2]}\n\n💵 পুরস্কার: {t[3]} BDT",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

    elif data.startswith("submit_"):
        tid = int(data[7:])
        ctx.user_data["submitting"] = tid
        await q.edit_message_text("📸 এখন কাজের স্ক্রিনশট পাঠান:")

    elif data == "cancel_task":
        await q.edit_message_text("❌ কাজ বাতিল করা হয়েছে।")

    elif data.startswith("w_"):
        method = data[2:]
        ctx.user_data["w_method"] = method
        ctx.user_data["w_account"] = True
        names = {"bkash": "বিকাশ", "nagad": "নগদ", "usdt": "USDT"}
        await q.edit_message_text(f"📱 আপনার {names.get(method,method)} নম্বর লিখুন:")

async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message.text else ""

    if text == "📋 কাজ":
        await tasks(update, ctx)
    elif text == "💰 ব্যালেন্স":
        await balance(update, ctx)
    elif text == "🏦 টাকা উতোলন":
        await withdraw(update, ctx)
    elif text == "🎁 Invite & Earn":
        await invite(update, ctx)
    elif text == "🆘 সাপোর্ট":
        await support(update, ctx)
    elif text == "🆕 আমি নতুন":
        await new_guide(update, ctx)
    elif text == "🎯 মিশন":
        await mission(update, ctx)
    elif ctx.user_data.get("support"):
        ctx.user_data["support"] = False
        try:
            await ctx.bot.send_message(ADMIN_ID, f"📩 সাপোর্ট!\nFrom: {update.effective_user.full_name} (ID: {update.effective_user.id})\n\n{text}")
        except:
            pass
        await update.message.reply_text("✅ আপনার মেসেজ পাঠানো হয়েছে!", reply_markup=main_menu())
    elif ctx.user_data.get("w_account"):
        ctx.user_data["w_account"] = False
        ctx.user_data["w_acc_num"] = text
        ctx.user_data["w_amount"] = True
        u = get_user(update.effective_user.id)
        await update.message.reply_text(f"💰 কত টাকা তুলতে চান?\n(সর্বনিম্ন: {MIN_WITHDRAW} BDT, আপনার ব্যালেন্স: {u[3]:.2f} BDT)")
    elif ctx.user_data.get("w_amount"):
        ctx.user_data["w_amount"] = False
        try:
            amount = float(text)
            u = get_user(update.effective_user.id)
            if amount < MIN_WITHDRAW:
                await update.message.reply_text(f"❌ সর্বনিম্ন {MIN_WITHDRAW} BDT লাগবে।")
                return
            if amount > u[3]:
                await update.message.reply_text("❌ পর্যাপ্ত ব্যালেন্স নেই।")
                return
            method = ctx.user_data.get("w_method", "")
            account = ctx.user_data.get("w_acc_num", "")
            c = db()
            cur = c.cursor()
            cur.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, u[0]))
            cur.execute("INSERT INTO withdrawals (user_id,amount,method,account,requested_at) VALUES (?,?,?,?,?)",
                        (u[0], amount, method, account, datetime.now().isoformat()))
            c.commit()
            c.close()
            await update.message.reply_text(
                f"✅ উইথড্র রিকোয়েস্ট জমা!\n💰 {amount} BDT\n📱 {method}\n📋 {account}\n\n⏳ ২৪ ঘন্টার মধ্যে পাঠানো হবে।",
                reply_markup=main_menu()
            )
            try:
                await ctx.bot.send_message(ADMIN_ID, f"💸 উইথড্র!\nUser: {update.effective_user.full_name} ({u[0]})\nAmount: {amount}\nMethod: {method}\nAccount: {account}")
            except:
                pass
        except:
            await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন।")

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    tid = ctx.user_data.get("submitting")
    if not tid:
        return
    proof = update.message.photo[-1].file_id
    c = db()
    cur = c.cursor()
    cur.execute("INSERT INTO user_tasks (user_id,task_id,status,submitted_at,proof) VALUES (?,?,?,?,?)",
                (uid, tid, "pending", datetime.now().isoformat(), proof))
    cur.execute("SELECT title FROM tasks WHERE task_id=?", (tid,))
    t = cur.fetchone()
    c.commit()
    c.close()
    ctx.user_data.pop("submitting", None)
    await update.message.reply_text(f"✅ জমা হয়েছে!\nকাজ: {t[0]}\n⏳ Admin রিভিউ করবেন।", reply_markup=main_menu())
    try:
        await ctx.bot.send_message(ADMIN_ID, f"🆕 নতুন কাজ জমা!\nUser: {update.effective_user.full_name} ({uid})\nকাজ: {t[0]}\n\n/approve_{uid}_{tid} — অনুমোদন\n/reject_{uid}_{tid} — বাতিল")
        await ctx.bot.send_photo(ADMIN_ID, proof)
    except:
        pass

async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = update.message.text
    if text.startswith("/approve_"):
        parts = text.split("_")
        uid, tid = int(parts[1]), int(parts[2])
        c = db()
        cur = c.cursor()
        cur.execute("SELECT reward FROM tasks WHERE task_id=?", (tid,))
        t = cur.fetchone()
        cur.execute("UPDATE user_tasks SET status='approved' WHERE user_id=? AND task_id=?", (uid, tid))
        c.commit()
        c.close()
        if t:
            c2 = db()
            cur2 = c2.cursor()
            cur2.execute("UPDATE users SET balance=balance+?, total_income=total_income+? WHERE user_id=?", (t[0], t[0], uid))
            c2.commit()
            c2.close()
            try:
                await ctx.bot.send_message(uid, f"🎉 কাজ অনুমোদিত! {t[0]} BDT যোগ হয়েছে!")
            except:
                pass
        await update.message.reply_text(f"✅ অনুমোদন করা হয়েছে।")
    elif text.startswith("/reject_"):
        parts = text.split("_")
        uid, tid = int(parts[1]), int(parts[2])
        c = db()
        cur = c.cursor()
        cur.execute("UPDATE user_tasks SET status='rejected' WHERE user_id=? AND task_id=?", (uid, tid))
        c.commit()
        c.close()
        try:
            await ctx.bot.send_message(uid, "❌ আপনার কাজ বাতিল হয়েছে। আবার চেষ্টা করুন।")
        except:
            pass
        await update.message.reply_text("❌ বাতিল করা হয়েছে।")
    elif text.startswith("/addbalance"):
        parts = text.split()
        if len(parts) == 3:
            uid, amt = int(parts[1]), float(parts[2])
            c = db()
            cur = c.cursor()
            cur.execute("UPDATE users SET balance=balance+?, total_income=total_income+? WHERE user_id=?", (amt, amt, uid))
            c.commit()
            c.close()
            await update.message.reply_text(f"✅ {uid} কে {amt} BDT দেওয়া হয়েছে।")
            try:
                await ctx.bot.send_message(uid, f"🎁 Admin আপনাকে {amt} BDT দিয়েছেন!")
            except:
                pass

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r"^/(approve|reject|addbalance)"), admin_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.add_handler(CallbackQueryHandler(callback))
    print("Bot চালু!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
