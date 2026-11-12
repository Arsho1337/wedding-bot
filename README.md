# Wedding Studio Bot · ربات استودیو عروسی

A small Persian (RTL) Telegram bot for a **wedding photography studio**. The leader
creates a project per customer and hands out a short access code; the customer
sends that code once to the bot and afterwards always sees **only their own**
project: current stage, progress bar, latest note, delivery date, and links to
galleries/finals.

No AI in the runtime loop, no external services — one Python process plus
SQLite, so it is cheap to host and survives reboots under systemd.

---

## How it works

```
leader                     bot                      customer
  /new Sara Ahmadi  ──▶  WED-7K4Q  ──(code)──▶  sends /start + WED-7K4Q
  /stage WED-7K4Q رتاش عکس‌ها ─▶ update ──(push)──▶  "مرحله فعلی: رتاش عکس‌ها"
```

1. `/new` generates a code. Send it to the customer (or send the deep link
   `https://t.me/<bot>?start=WED-7K4Q`).
2. The customer's code binds to their Telegram account on first use. A
   forwarded code is rejected; `/reset` frees it if they change accounts.
3. Every stage/note/delivery change pushes a notification to the customer.
   That is the point of the bot — customers stop asking "when are our photos?".

## The pipeline

Edit `texts.py` → `STAGES` to change wording or reorder. Seven defaults:

`رزرو تأیید شد → عکاسی انجام شد → گزینش و ویرایش → رتاش عکس‌ها → آلبوم دیجیتال → آلبوم چاپی → تحویل نهایی`

Stages are 1-based for humans: `/stage WED-7K4Q 4` means "رتاش عکس‌ها".

## Commands

### مدیر تیم (admin)

| Command | Meaning |
|---|---|
| `/new نام مشتری` | create project, return access code |
| `/list` | all projects, stage, linked/pending |
| `/card کد` | full project card |
| `/stage کد مرحله` | set stage by number or name |
| `/next کد` | advance one stage |
| `/note کد متن` | save note + notify customer |
| `/media کد لینک [برچسب]` | attach a Drive/WeTransfer link |
| `/delivery کد 1404/02/15` | set delivery date |
| `/reset کد` | unbind the customer's account |
| `/crew add کد آیدی` | assign a crew member to a project |
| `/crew del آیدی` / `/crew list` | manage crew |
| `/id` | show your Telegram id and role |

### همکار (crew)

`/card`, `/stage`, `/next`, `/note`, `/id` — limited to their assigned project.
Add them with `/crew add WED-7K4Q 123456789`; the bot messages them the guide.

### مشتری (customer)

`/start` → send code → project card with a 🔄 refresh button. Any other text
re-renders the card.

---

## Run it locally first

```bash
cd wedding-bot
python3 -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # then edit BOT_TOKEN and ADMIN_IDS
python selfcheck.py           # offline test: storage, stages, codes
python bot.py
```

Get `BOT_TOKEN` from [@BotFather](https://t.me/BotFather) (`/newbot`).
Get your own id by messaging [@userinfobot](https://t.me/userinfobot), or run
the bot once with a placeholder and use `/id`.

## Deploy on the VPS

```bash
# 1) system user + code
sudo useradd --system --home /opt/wedding-bot --shell /usr/sbin/nologin weddingbot
sudo mkdir -p /opt/wedding-bot
sudo rsync -a ./ /opt/wedding-bot/         # or git clone
cd /opt/wedding-bot

# 2) venv + deps
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

# 3) config + permissions
sudo cp .env.example .env
sudo nano .env                              # BOT_TOKEN, ADMIN_IDS
sudo mkdir -p data
sudo chown -R weddingbot:weddingbot /opt/wedding-bot
sudo chmod 600 .env

# 4) service
sudo cp deploy/wedding-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wedding-bot
systemctl status wedding-bot
journalctl -u wedding-bot -f
```

The unit restarts on crash (`Restart=always`), starts at boot, and is
sandboxed: `ProtectSystem=strict`, `ProtectHome=yes`, `NoNewPrivileges=yes`,
and the only writable path is `/opt/wedding-bot/data`.

### Updating

```bash
cd /opt/wedding-bot
sudo -u weddingbot git pull            # or rsync new files
sudo -u weddingbot .venv/bin/pip install -r requirements.txt
sudo systemctl restart wedding-bot
journalctl -u wedding-bot -n 50        # confirm clean start
```

### Backups (SQLite, WAL mode)

```bash
sudo -u weddingbot sqlite3 data/bot.db ".backup '/opt/wedding-bot/data/backup-$(date +%F).db'"
```

Copy that file off-box with a nightly cron or `rclone`. WAL means **do not**
`cp` the live `.db` and hope — use `.backup` or stop the service first.

---

## Security notes (read these)

- **Codes are bearer secrets.** Binding to the first Telegram account that
  claims them limits damage, but a customer can still forward their code
  before claiming it. Treat `/new` output as private, and use `/reset` if a
  code leaks. Wrong guesses are limited to 8 per 15 minutes per account.
- **`.env` holds the bot token** — `chmod 600`, never commit it (see
  `.gitignore`). A leaked token means someone else controls your bot.
- **The DB holds customer names and Telegram ids.** Personal data — back it up
  privately, don't publish it.
- **Crew can write.** Anyone you add with `/crew` can change stages and notes
  for their project, and customers are notified. Remove people who leave with
  `/crew del <id>`.
- **One bot, one poller.** Running two copies against the same token causes
  Telegram `Conflict` errors and duplicated replies.

## Known limits

- Telegram allows bots to upload ~**50 MB** — so large files must be **links**
  (Drive, WeTransfer), not files. Preview JPEGs can be added later as a
  file-upload handler; the schema already stores links.
- SQLite + a single process comfortably covers hundreds of projects. Beyond
  that you'd move to Postgres and a worker queue; nothing here needs it yet.
- One project per customer code. A couple with two weddings (engagement +
  wedding) needs two codes, or a schema change to `projects.customer_id`.
- Timestamps use `TZ_NAME` (default `Asia/Tehran`). Change it in `.env`.

## Files

```
bot.py                     handlers, rendering, access control
db.py                      SQLite schema + queries
texts.py                   all Persian copy, stages, code normalisation
config.py                  env/.env loading
selfcheck.py               offline test, no token needed
deploy/wedding-bot.service systemd unit (hardened)
.env.example               config template
```

## Quick test checklist

1. `python selfcheck.py` → ✅
2. `python bot.py` → no traceback, "starting; db=..." logged.
3. `/id` from your account → matches `ADMIN_IDS`.
4. `/new Test Customer` → code appears.
5. Send the code from a **second** Telegram account → card appears, project
   list shows 🔗.
6. `/stage <code> رتاش عکس‌ها` from the admin → second account receives the push.
7. `/reset <code>` → the code works for another account, old one loses access.
