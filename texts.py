"""All Persian (RTL) copy and stage helpers live here.

Edit this file alone to reword the bot or change the pipeline.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Pipeline: order matters. Index 0 is "just booked", the last one is "done".
# --------------------------------------------------------------------------
STAGES: list[str] = [
    "رزرو تأیید شد",
    "عکاسی انجام شد",
    "گزینش و ویرایش",
    "رتاش عکس‌ها",
    "آلبوم دیجیتال",
    "آلبوم چاپی",
    "تحویل نهایی",
]


def norm(text: str) -> str:
    """Normalise Persian input for tolerant matching."""
    s = (text or "").strip()
    # Arabic variants -> Persian, ZWNJ -> space, collapse whitespace
    s = s.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return " ".join(s.split()).lower()


def bar(stage: int, total: int | None = None) -> str:
    """Progress line, e.g. 🟢🟢🟢🔵⚪⚪⚪"""
    total = total or len(STAGES)
    stage = max(0, min(stage, total - 1))
    return "".join(
        "🟢" if i < stage else ("🔵" if i == stage else "⚪") for i in range(total)
    )


def parse_stage(raw: str) -> int | None:
    """Accept `4`, `رتاش عکس‌ها`, or a fuzzy fragment like `آلبوم`."""
    s = norm(raw)
    if not s:
        return None
    if s.isdigit():
        n = int(s)
        return n - 1 if 1 <= n <= len(STAGES) else None
    for i, label in enumerate(STAGES):
        if norm(label) == s:
            return i
    for i, label in enumerate(STAGES):
        if s in norm(label):
            return i
    return None


def stage_list() -> str:
    return "\n".join(f"{i + 1}. {label}" for i, label in enumerate(STAGES))


# --------------------------------------------------------------------------
# Customer-facing copy
# --------------------------------------------------------------------------
WELCOME_CUSTOMER = (
    "سلام 👋\n"
    "به ربات تیم عکاسی عروسی خوش آمدید.\n\n"
    "برای مشاهده وضعیت پروژه‌تان، کد پروژه‌ای که مدیر تیم به شما داده است را "
    "بفرستید.\n"
    "مثال: <code>WED-7K4Q</code>"
)

CODE_NOT_FOUND = (
    "❌ کدی با این مشخصات پیدا نشد.\n"
    "لطفاً کد را دقیقاً همان‌طور که دریافت کرده‌اید وارد کنید، یا با تیم تماس بگیرید."
)

CODE_TAKEN = (
    "⛔ این کد قبلاً روی حساب تلگرام دیگری فعال شده است.\n"
    "اگر حساب شما عوض شده، با تیم تماس بگیرید تا کد را آزاد کنند."
)

CODE_ALREADY_BOUND = (
    "⛔ حساب شما از قبل به یک پروژه متصل است و هر حساب تنها یک پروژه دارد.\n"
    "برای دیدن پروژه /start را بزنید، یا با تیم تماس بگیرید."
)

CODE_WELCOME = (
    "✅ خوش آمدید <b>{name}</b>!\n"
    "کد شما به این حساب متصل شد؛ از این پس با همین حساب پروژه را می‌بینید."
)

TOO_MANY_ATTEMPTS = (
    "⏳ تعداد تلاش‌های ناموفق زیاد شده است.\n"
    "لطفاً چند دقیقه بعد دوباره تلاش کنید."
)

NO_ACCESS = "⛔ شما به این پروژه دسترسی ندارید."
PROJECT_GONE = "این پروژه دیگر موجود نیست. با تیم تماس بگیرید."

DELIVERY_LINE = "📅 تاریخ تحویل: <b>{date}</b>"
NOTE_LINE = "📝 آخرین یادداشت: {note}"
MEDIA_HEADER = "🔗 گالری پروژه:"
MEDIA_MORE = "<i>و {count} مورد دیگر</i>"
MEDIA_DEFAULT_LABEL = "عکس پروژه"
UPDATED_LINE = "<i>آخرین به‌روزرسانی: {ts}</i>"
STAGE_OF = "<i>مرحله {index} از {total}</i>"
CURRENT_STAGE = "مرحله فعلی: <b>{stage}</b>"
CODE_LINE = "کد پروژه: <code>{code}</code>"

BTN_REFRESH = "🔄 به‌روزرسانی"

# Notifications pushed to the customer
STAGE_NOTIFY = (
    "🎉 وضعیت پروژه شما به‌روزرسانی شد\n\n"
    "مرحله فعلی: <b>{stage}</b>\n"
    "پیشرفت: {bar}\n\n"
    "برای جزئیات /start را بزنید."
)
NOTE_NOTIFY = "📝 یادداشت جدید از تیم:\n{note}"
MEDIA_NOTIFY = "🔗 عکس/گالری جدیدی برای پروژه شما اضافه شد.\nبرای دیدن آن /start را بزنید."
DELIVERY_NOTIFY = "📅 تاریخ تحویل پروژه شما: <b>{date}</b>"

# --------------------------------------------------------------------------
# Team-facing copy
# --------------------------------------------------------------------------
ADMIN_HELP = (
    "👑 <b>راهنمای مدیر تیم</b>\n\n"
    "<b>پروژه</b>\n"
    "/new نام مشتری — ساخت پروژه جدید و گرفتن کد\n"
    "/list — لیست همه پروژه‌ها\n"
    "/card کد — نمایش کارت پروژه\n\n"
    "<b>به‌روزرسانی</b>\n"
    "/stage کد مرحله — تغییر مرحله (شماره یا نام)\n"
    "/next کد — رفتن به مرحله بعد\n"
    "/note کد متن — ثبت یادداشت و اطلاع به مشتری\n"
    "/media کد لینک [برچسب] — افزودن لینک فایل (گالری/آلبوم)\n"
    "/delivery کد تاریخ — تعیین تاریخ تحویل\n\n"
    "<b>دسترسی</b>\n"
    "/reset کد — آزاد کردن کد مشتری (برای تغییر حساب)\n"
    "/crew add کد آیدی — افزودن همکار به یک پروژه\n"
    "/crew del آیدی — حذف همکار\n"
    "/crew list — لیست همکاران\n"
    "/id — نمایش شناسه تلگرام شما\n\n"
    "<b>مراحل:</b>\n{stages}\n\n"
    "⚠️ فایل‌های حجیم را در گوگل درایو بگذارید و لینکش را با /media ثبت کنید؛ "
    "تلگرام اجازه ارسال فایل بزرگ‌تر از ۵۰ مگابایت را به ربات نمی‌دهد."
)

CREW_HELP = (
    "👷 <b>راهنمای همکار</b>\n\n"
    "/card کد — نمایش پروژه\n"
    "/stage کد مرحله — تغییر مرحله\n"
    "/next کد — مرحله بعد\n"
    "/note کد متن — ثبت یادداشت\n"
    "/id — نمایش شناسه تلگرام شما\n\n"
    "همه تغییرات برای مشتری نوتیفیکیشن می‌شود."
)

NOT_ADMIN = "⛔ این دستور فقط برای مدیر تیم است."
NOT_STAFF = "⛔ شما به این پروژه دسترسی ندارید."
ADMIN_HINT = "برای دستورها /start را بزنید."
UNKNOWN_COMMAND = "دستور ناشناخته. /start را بزنید."

PROJECT_CREATED = (
    "✅ پروژه برای «{name}» ساخته شد.\n\n"
    "کد مشتری: <code>{code}</code>\n\n"
    "این کد را به مشتری بدهید. کافی است در ربات /start بزند و کد را بفرستد.\n"
    "لینک مستقیم:\nhttps://t.me/{bot_username}?start={code}"
)

LIST_HEADER = "📋 <b>پروژه‌ها</b> (🔗 متصل، ⏳ در انتظار مشتری)"
LIST_EMPTY = "هنوز پروژه‌ای ساخته نشده. با /new شروع کنید."

CREATED_LOG = "پروژه ساخته شد"
STAGE_SET = "✅ مرحله «{stage}» ثبت شد و به مشتری اطلاع داده شد."
STAGE_SET_NO_CUSTOMER = "✅ مرحله «{stage}» ثبت شد. (مشتری هنوز به ربات وصل نشده)"
NOTE_SET = "✅ یادداشت ثبت شد."
MEDIA_SET = "✅ لینک ثبت شد.\n{url}"
DELIVERY_SET = "✅ تاریخ تحویل ثبت شد: {date}"
RESET_DONE = "✅ کد {code} آزاد شد. مشتری بعدی که آن را وارد کند به پروژه وصل می‌شود."
RESET_NOT_LINKED = "این پروژه به هیچ حسابی وصل نیست."
CREW_ADDED = "✅ همکار <code>{tg}</code> به پروژه <code>{code}</code> اضافه شد."
CREW_REMOVED = "✅ همکار حذف شد."
CREW_NOT_FOUND = "همکاری با این شناسه پیدا نشد."
CREW_LIST_HEADER = "👷 <b>همکاران</b>"
CREW_LIST_EMPTY = "هیچ همکاری ثبت نشده."
CREW_LIST_LINE = "• <code>{tg}</code> — {project}"
CREW_ALL_PROJECTS = "همه پروژه‌ها"
ID_HELP = "شناسه تلگرام شما: <code>{tg}</code>\nنقش: {role}"

USAGE_NEW = "استفاده: <code>/new نام مشتری</code>"
USAGE_STAGE = (
    "استفاده: <code>/stage کد مرحله</code>\n"
    "مثال: <code>/stage WED-7K4Q 4</code> یا <code>/stage WED-7K4Q رتاش عکس‌ها</code>\n\n"
    "مراحل:\n{stages}"
)
USAGE_REF = "استفاده: <code>/{command} کد</code>"
USAGE_NOTE = "استفاده: <code>/note کد متن یادداشت</code>"
USAGE_MEDIA = "استفاده: <code>/media کد لینک [برچسب]</code>"
USAGE_DELIVERY = "استفاده: <code>/delivery کد 1404/02/15</code>"
USAGE_CREW = (
    "استفاده:\n"
    "<code>/crew add کد آیدی</code>\n"
    "<code>/crew del آیدی</code>\n"
    "<code>/crew list</code>"
)
PROJECT_NOT_FOUND = "❌ پروژه‌ای با این کد/نام پیدا نشد."
STAGE_NOT_FOUND = "❌ مرحله نامعتبر. یکی از این‌ها را بفرستید:\n{stages}"
BAD_URL = "❌ لینک باید با http:// یا https:// شروع شود."

# --------------------------------------------------------------------------
# Access-code helpers
# --------------------------------------------------------------------------
# Unambiguous alphabet: no O/0 or I/1, so codes survive being read by phone.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_code(raw: str) -> str:
    """`wed 7k4q`, `7K4Q`, `WED-7K4Q`, `WED7K4Q` -> `WED-7K4Q`."""
    s = (raw or "").strip().upper().replace("_", "-").replace("–", "-")
    s = "".join(ch for ch in s if not ch.isspace())
    core = s
    if core.startswith("WED-"):
        core = core[4:]
    elif core.startswith("WED"):
        core = core[3:]
    core = core.replace("-", "")
    if 4 <= len(core) <= 6 and all(ch in ALPHABET for ch in core):
        return "WED-" + core
    return s
