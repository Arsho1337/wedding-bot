#!/usr/bin/env python3
"""Wedding photography studio Telegram bot — Persian (RTL).

Roles
-----
admin  : team leader. Creates projects, sets stages, sees everything.
crew   : assigned to one project (or all). Can set stage / add notes.
customer: bound to exactly one project via an access code, sees only that.

Run:  python bot.py
"""

from __future__ import annotations

import html
import logging
import secrets
import sys
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import db
import texts as T

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
log = logging.getLogger("weddingbot")

HTML = ParseMode.HTML


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def stamp() -> str:
    from datetime import datetime

    return datetime.now(config.TZ).strftime("%Y-%m-%d %H:%M")


def new_code() -> str:
    while True:
        code = "WED-" + "".join(secrets.choice(T.ALPHABET) for _ in range(5))
        if db.project_by_code(code) is None:
            return code


def normalize_code(raw: str) -> str:
    """Thin alias so call sites read cleanly; logic lives in texts.py."""
    return T.normalize_code(raw)


# --------------------------------------------------------------------------
# Access-code brute-force guard (in-memory; resets when the bot restarts)
# --------------------------------------------------------------------------
_attempts: dict[int, list[float]] = {}


def _locked_out(tg_id: int) -> bool:
    cutoff = time.monotonic() - config.CODE_WINDOW_SECONDS
    hits = [t for t in _attempts.get(tg_id, []) if t > cutoff]
    _attempts[tg_id] = hits
    return len(hits) >= config.CODE_MAX_ATTEMPTS


def _record_attempt(tg_id: int) -> None:
    _attempts.setdefault(tg_id, []).append(time.monotonic())


# --------------------------------------------------------------------------
# Role checks
# --------------------------------------------------------------------------
def is_admin(tg_id: int) -> bool:
    return tg_id in config.ADMIN_IDS


def staff_of(tg_id: int):
    return db.get_staff(tg_id)


def can_manage(tg_id: int, project) -> bool:
    """Admins manage everything; crew only their project."""
    if is_admin(tg_id):
        return True
    st = staff_of(tg_id)
    if st is None:
        return False
    return st["project_id"] is None or st["project_id"] == project["id"]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render_card(p) -> str:
    total = len(T.STAGES)
    stage = max(0, min(int(p["stage"]), total - 1))
    lines = [
        f"💍 <b>{esc(p['customer_name'])}</b>",
        T.CODE_LINE.format(code=esc(p["code"])),
        "",
        T.CURRENT_STAGE.format(stage=esc(T.STAGES[stage])),
        T.bar(stage, total),
        T.STAGE_OF.format(index=stage + 1, total=total),
        "",
    ]

    for i, label in enumerate(T.STAGES):
        mark = "✅" if i < stage else ("🔵" if i == stage else "⚪")
        lines.append(f"{mark} {esc(label)}")

    if p["delivery_date"]:
        lines.append("")
        lines.append(T.DELIVERY_LINE.format(date=esc(p["delivery_date"])))

    if p["note"]:
        lines.append("")
        lines.append(T.NOTE_LINE.format(note=esc(p["note"])))

    links = db.list_media(p["id"])
    if links:
        lines.append("")
        lines.append(T.MEDIA_HEADER)
        for m in links[:10]:
            label = esc(m["label"] or T.MEDIA_DEFAULT_LABEL)
            lines.append(f'• <a href="{esc(m["url"])}">{label}</a>')
        if len(links) > 10:
            lines.append(T.MEDIA_MORE.format(count=len(links) - 10))

    lines.append("")
    lines.append(T.UPDATED_LINE.format(ts=esc(str(p["updated_at"])[:16].replace("T", " "))))
    return "\n".join(lines)


def card_keyboard(p) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(T.BTN_REFRESH, callback_data=f"refresh:{p['id']}")]]
    )


async def reply_card(message, p) -> None:
    await message.reply_text(
        render_card(p),
        parse_mode=HTML,
        reply_markup=card_keyboard(p),
        disable_web_page_preview=True,
    )


async def notify_customer(ctx: ContextTypes.DEFAULT_TYPE, p, text: str) -> bool:
    """Push a message to the customer, tolerating blocked/deleted accounts."""
    if not p["cust_tg_id"]:
        return False
    try:
        await ctx.bot.send_message(
            chat_id=int(p["cust_tg_id"]),
            text=text,
            parse_mode=HTML,
            disable_web_page_preview=True,
        )
        return True
    except Exception as exc:  # blocked bot, deleted account, network blip
        log.warning("notify failed for project %s: %s", p["code"], exc)
        return False


# --------------------------------------------------------------------------
# Project lookup
# --------------------------------------------------------------------------
def resolve_project(ref: str):
    ref = (ref or "").strip()
    if not ref:
        return None
    return db.project_by_code(normalize_code(ref)) or db.project_by_name(ref)


# --------------------------------------------------------------------------
# Customer flow
# --------------------------------------------------------------------------
async def _deliver_code(update: Update, raw: str) -> None:
    msg = update.effective_message
    tg_id = update.effective_user.id

    if _locked_out(tg_id):
        await msg.reply_text(T.TOO_MANY_ATTEMPTS)
        return

    code = normalize_code(raw)
    p = db.project_by_code(code)
    if p is None:
        _record_attempt(tg_id)
        await msg.reply_text(T.CODE_NOT_FOUND)
        return

    if p["cust_tg_id"] is None:
        # A team member previewing a fresh code must never claim the customer's
        # slot — they test with /card, not by typing the code.
        if is_admin(tg_id) or staff_of(tg_id):
            await reply_card(msg, p)
            return
        if db.project_by_customer(tg_id) is not None:
            await msg.reply_text(T.CODE_ALREADY_BOUND)
            return
        if db.bind_customer(p["id"], tg_id):
            db.log_event(p["id"], str(tg_id), "bind", "customer linked to code")
            p = db.project_by_code(code)
            await msg.reply_text(
                T.CODE_WELCOME.format(name=esc(p["customer_name"])), parse_mode=HTML
            )
            await reply_card(msg, p)
        else:  # lost a race with another device
            await msg.reply_text(T.CODE_TAKEN)
        return

    if int(p["cust_tg_id"]) == int(tg_id):
        await reply_card(msg, p)
        return

    await msg.reply_text(T.CODE_TAKEN)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tg_id = user.id

    # Deep link: https://t.me/<bot>?start=WED-XXXXX
    if ctx.args:
        await _deliver_code(update, " ".join(ctx.args))
        return

    if is_admin(tg_id):
        await update.message.reply_text(
            T.ADMIN_HELP.format(stages=T.stage_list()), parse_mode=HTML
        )
        return

    if staff_of(tg_id):
        await update.message.reply_text(T.CREW_HELP, parse_mode=HTML)
        return

    p = db.project_by_customer(tg_id)
    if p:
        await reply_card(update.message, p)
        return

    await update.message.reply_text(T.WELCOME_CUSTOMER, parse_mode=HTML)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Everything that isn't a command: an access code, or a nudge."""
    msg = update.message
    if msg is None or not msg.text:
        return
    tg_id = update.effective_user.id

    if is_admin(tg_id) or staff_of(tg_id):
        if normalize_code(msg.text).startswith("WED-"):
            await _deliver_code(update, msg.text)
            return
        await msg.reply_text(T.ADMIN_HINT)
        return

    p = db.project_by_customer(tg_id)
    if p:
        await reply_card(msg, p)
        return

    await _deliver_code(update, msg.text)


async def on_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tg_id = query.from_user.id
    try:
        project_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer()
        return

    p = db.project_by_id(project_id)
    if p is None:
        await query.answer(T.PROJECT_GONE, show_alert=True)
        return
    if int(p["cust_tg_id"] or 0) != int(tg_id) and not can_manage(tg_id, p):
        await query.answer(T.NO_ACCESS, show_alert=True)
        return

    await query.answer()
    try:
        await query.edit_message_text(
            render_card(p),
            parse_mode=HTML,
            reply_markup=card_keyboard(p),
            disable_web_page_preview=True,
        )
    except Exception as exc:  # "message is not modified"
        log.debug("refresh edit skipped: %s", exc)


# --------------------------------------------------------------------------
# Team commands
# --------------------------------------------------------------------------
async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not is_admin(tg_id):
        await update.message.reply_text(T.NOT_ADMIN)
        return
    name = " ".join(ctx.args).strip()
    if not name:
        await update.message.reply_text(T.USAGE_NEW, parse_mode=HTML)
        return

    code = new_code()
    p = db.create_project(code, name)
    db.log_event(p["id"], str(tg_id), "create", name)

    bot_username = ctx.bot.username or "YourBot"
    await update.message.reply_text(
        T.PROJECT_CREATED.format(
            name=esc(name), code=esc(code), bot_username=esc(bot_username)
        ),
        parse_mode=HTML,
        disable_web_page_preview=True,
    )
    log.info("project %s created for %r by %s", code, name, tg_id)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(T.NOT_ADMIN)
        return

    rows = db.list_projects()
    if not rows:
        await update.message.reply_text(T.LIST_EMPTY)
        return

    total = len(T.STAGES)
    lines = [T.LIST_HEADER, ""]
    for p in rows:
        linked = "🔗" if p["cust_tg_id"] else "⏳"
        lines.append(
            f"{linked} <code>{esc(p['code'])}</code> · {esc(p['customer_name'])} · "
            f"{esc(T.STAGES[min(int(p['stage']), total - 1)])} "
            f"({int(p['stage']) + 1}/{total})"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=HTML)


async def cmd_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text(
            T.USAGE_REF.format(command="card"), parse_mode=HTML
        )
        return
    p = resolve_project(ctx.args[0])
    if p is None:
        await update.message.reply_text(T.PROJECT_NOT_FOUND)
        return
    if not can_manage(tg_id, p):
        await update.message.reply_text(T.NOT_STAFF)
        return
    await reply_card(update.message, p)


async def cmd_stage(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if len(ctx.args) < 2:
        await update.message.reply_text(
            T.USAGE_STAGE.format(stages=T.stage_list()), parse_mode=HTML
        )
        return

    p = resolve_project(ctx.args[0])
    if p is None:
        await update.message.reply_text(T.PROJECT_NOT_FOUND)
        return
    if not can_manage(tg_id, p):
        await update.message.reply_text(T.NOT_STAFF)
        return

    index = T.parse_stage(" ".join(ctx.args[1:]))
    if index is None:
        await update.message.reply_text(
            T.STAGE_NOT_FOUND.format(stages=T.stage_list()), parse_mode=HTML
        )
        return

    db.set_stage(p["id"], index)
    db.log_event(p["id"], str(tg_id), "stage", T.STAGES[index])
    p = db.project_by_id(p["id"])

    sent = await notify_customer(
        ctx,
        p,
        T.STAGE_NOTIFY.format(stage=esc(T.STAGES[index]), bar=T.bar(index)),
    )
    template = T.STAGE_SET if sent else T.STAGE_SET_NO_CUSTOMER
    await update.message.reply_text(
        template.format(stage=esc(T.STAGES[index])), parse_mode=HTML
    )
    log.info("%s set stage %s -> %s", tg_id, p["code"], T.STAGES[index])


async def cmd_next(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text(
            T.USAGE_REF.format(command="next"), parse_mode=HTML
        )
        return
    p = resolve_project(ctx.args[0])
    if p is None:
        await update.message.reply_text(T.PROJECT_NOT_FOUND)
        return
    if not can_manage(tg_id, p):
        await update.message.reply_text(T.NOT_STAFF)
        return

    current = int(p["stage"])
    last = len(T.STAGES) - 1
    if current >= last:
        await update.message.reply_text(
            T.STAGE_SET.format(stage=esc(T.STAGES[last])), parse_mode=HTML
        )
        return

    index = current + 1
    db.set_stage(p["id"], index)
    db.log_event(p["id"], str(tg_id), "stage", T.STAGES[index])
    p = db.project_by_id(p["id"])
    sent = await notify_customer(
        ctx,
        p,
        T.STAGE_NOTIFY.format(stage=esc(T.STAGES[index]), bar=T.bar(index)),
    )
    template = T.STAGE_SET if sent else T.STAGE_SET_NO_CUSTOMER
    await update.message.reply_text(
        template.format(stage=esc(T.STAGES[index])), parse_mode=HTML
    )


async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if len(ctx.args) < 2:
        await update.message.reply_text(T.USAGE_NOTE, parse_mode=HTML)
        return
    p = resolve_project(ctx.args[0])
    if p is None:
        await update.message.reply_text(T.PROJECT_NOT_FOUND)
        return
    if not can_manage(tg_id, p):
        await update.message.reply_text(T.NOT_STAFF)
        return

    note = " ".join(ctx.args[1:]).strip()
    db.set_note(p["id"], note)
    db.log_event(p["id"], str(tg_id), "note", note)
    p = db.project_by_id(p["id"])

    sent = await notify_customer(ctx, p, T.NOTE_NOTIFY.format(note=esc(note)))
    suffix = "" if sent else "\n(مشتری هنوز وصل نیست)"
    await update.message.reply_text(T.NOTE_SET + suffix)


async def cmd_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if len(ctx.args) < 2:
        await update.message.reply_text(T.USAGE_MEDIA, parse_mode=HTML)
        return
    p = resolve_project(ctx.args[0])
    if p is None:
        await update.message.reply_text(T.PROJECT_NOT_FOUND)
        return
    if not can_manage(tg_id, p):
        await update.message.reply_text(T.NOT_STAFF)
        return

    url = ctx.args[1].strip()
    if not url.lower().startswith(("http://", "https://")):
        await update.message.reply_text(T.BAD_URL)
        return
    label = " ".join(ctx.args[2:]).strip() or None

    db.add_media(p["id"], url, label)
    db.log_event(p["id"], str(tg_id), "media", url)
    p = db.project_by_id(p["id"])
    await notify_customer(ctx, p, T.MEDIA_NOTIFY)
    await update.message.reply_text(
        T.MEDIA_SET.format(url=esc(url)), parse_mode=HTML, disable_web_page_preview=True
    )


async def cmd_delivery(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if len(ctx.args) < 2:
        await update.message.reply_text(T.USAGE_DELIVERY, parse_mode=HTML)
        return
    p = resolve_project(ctx.args[0])
    if p is None:
        await update.message.reply_text(T.PROJECT_NOT_FOUND)
        return
    if not can_manage(tg_id, p):
        await update.message.reply_text(T.NOT_STAFF)
        return

    date = " ".join(ctx.args[1:]).strip()
    db.set_delivery(p["id"], date)
    db.log_event(p["id"], str(tg_id), "delivery", date)
    p = db.project_by_id(p["id"])
    await notify_customer(ctx, p, T.DELIVERY_NOTIFY.format(date=esc(date)))
    await update.message.reply_text(
        T.DELIVERY_SET.format(date=esc(date)), parse_mode=HTML
    )


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not is_admin(tg_id):
        await update.message.reply_text(T.NOT_ADMIN)
        return
    if not ctx.args:
        await update.message.reply_text(
            T.USAGE_REF.format(command="reset"), parse_mode=HTML
        )
        return
    p = resolve_project(ctx.args[0])
    if p is None:
        await update.message.reply_text(T.PROJECT_NOT_FOUND)
        return
    if db.reset_customer(p["id"]):
        db.log_event(p["id"], str(tg_id), "reset", "customer unbound")
        await update.message.reply_text(T.RESET_DONE.format(code=esc(p["code"])))
    else:
        await update.message.reply_text(T.RESET_NOT_LINKED)


async def cmd_crew(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if not is_admin(tg_id):
        await update.message.reply_text(T.NOT_ADMIN)
        return
    if not ctx.args:
        await update.message.reply_text(T.USAGE_CREW, parse_mode=HTML)
        return

    action = ctx.args[0].lower()
    rest = ctx.args[1:]

    if action == "list":
        rows = db.list_staff()
        if not rows:
            await update.message.reply_text(T.CREW_LIST_EMPTY)
            return
        lines = [T.CREW_LIST_HEADER, ""]
        for r in rows:
            project = (
                f"{r['project_code']} · {r['customer_name']}"
                if r["project_code"]
                else T.CREW_ALL_PROJECTS
            )
            lines.append(T.CREW_LIST_LINE.format(tg=r["tg_id"], project=esc(project)))
        await update.message.reply_text("\n".join(lines), parse_mode=HTML)
        return

    if action == "add":
        if len(rest) < 2:
            await update.message.reply_text(T.USAGE_CREW, parse_mode=HTML)
            return
        p = resolve_project(rest[0])
        if p is None:
            await update.message.reply_text(T.PROJECT_NOT_FOUND)
            return
        try:
            crew_id = int(rest[1])
        except ValueError:
            await update.message.reply_text(T.USAGE_CREW, parse_mode=HTML)
            return
        db.add_staff(crew_id, p["id"])
        db.log_event(p["id"], str(tg_id), "crew", f"added {crew_id}")
        await update.message.reply_text(
            T.CREW_ADDED.format(tg=crew_id, code=esc(p["code"])), parse_mode=HTML
        )
        try:
            await ctx.bot.send_message(
                chat_id=crew_id,
                text=T.CREW_HELP,
                parse_mode=HTML,
            )
        except Exception as exc:
            log.info("could not greet crew %s: %s", crew_id, exc)
        return

    if action in {"del", "remove", "rm"}:
        if not rest:
            await update.message.reply_text(T.USAGE_CREW, parse_mode=HTML)
            return
        try:
            crew_id = int(rest[0])
        except ValueError:
            await update.message.reply_text(T.USAGE_CREW, parse_mode=HTML)
            return
        if db.remove_staff(crew_id):
            await update.message.reply_text(T.CREW_REMOVED)
        else:
            await update.message.reply_text(T.CREW_NOT_FOUND)
        return

    await update.message.reply_text(T.USAGE_CREW, parse_mode=HTML)


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if is_admin(tg_id):
        role = "مدیر تیم"
    elif staff_of(tg_id):
        role = "همکار"
    elif db.project_by_customer(tg_id):
        role = "مشتری"
    else:
        role = "مهمان"
    await update.message.reply_text(
        T.ID_HELP.format(tg=tg_id, role=role), parse_mode=HTML
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------
async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("unhandled error", exc_info=ctx.error)


def build_application() -> Application:
    builder = Application.builder().token(config.BOT_TOKEN)
    if config.PROXY_URL:
        builder = builder.proxy_url(config.PROXY_URL)
        # get_updates_proxy_url can be different if needed
        builder = builder.get_updates_proxy_url(config.PROXY_URL)
    app = builder.build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))

    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("card", cmd_card))
    app.add_handler(CommandHandler("stage", cmd_stage))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("media", cmd_media))
    app.add_handler(CommandHandler("delivery", cmd_delivery))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("crew", cmd_crew))

    app.add_handler(CallbackQueryHandler(on_refresh, pattern=r"^refresh:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    if not config.BOT_TOKEN:
        sys.exit("BOT_TOKEN is missing — set it in .env or the environment.")
    if not config.ADMIN_IDS:
        sys.exit("ADMIN_IDS is missing — put your Telegram id there (use /id).")

    # Windows fix: create and set event loop for python-telegram-bot (Python 3.14+)
    if sys.platform == "win32":
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    db.init_db()
    log.info("starting; db=%s tz=%s admins=%s", config.DB_PATH, config.TZ_NAME, sorted(config.ADMIN_IDS))
    app = build_application()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
