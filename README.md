# DamaDam Bot V2.0 - Complete Documentation

## Overview

Clean, modular, multi-mode automation bot for DamaDam.pk with three complete modes:

- **MSG Mode** (Phase 1): Send personal messages to targets
- **POST Mode** (Phase 2): Create new text/image posts
- **INBOX Mode** (Phase 3): Monitor inbox and send replies

## File Structure

```text
damadam-bot/
├── main.py               # Single-file implementation (all logic)
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create this)
├── credentials.json      # Google service account (create this)
├── chromedriver.exe      # ChromeDriver binary (place in repo root)
└── logs/                 # Auto-created log directory
```

Notes:

- **Security**: `.env` and `credentials.json` are intentionally ignored by Git.
- **Local binary**: `chromedriver.exe` is intentionally ignored by Git.

## Installation

### Requirements

- **Python**: 3.11+ recommended
- **Google Chrome** installed (for Selenium)
- **ChromeDriver** (Windows local runs only if you want to pin a driver). If you don't provide a working ChromeDriver path, Selenium will try to manage it automatically.

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt:**

```text
gspread>=5.8.0
google-auth>=2.20.0
google-auth-oauthlib>=1.0.0
selenium==4.27.1
python-dotenv>=1.0.0
rich>=13.0.0
```

### 2. Setup Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable **Google Sheets API**
4. Create **Service Account**
5. Download JSON key as `credentials.json`
6. Share your Google Sheet with the service account email

### 3. Create .env File

```text
# DamaDam Credentials
DD_LOGIN_EMAIL=your_username
DD_LOGIN_PASS=your_password

# Secondary login (optional fallback)
DD_LOGIN_EMAIL2=backup_username
DD_LOGIN_PASS2=backup_password

# Google Sheets
DD_SHEET_ID=your_main_sheet_id
DD_PROFILES_SHEET_ID=your_profiles_sheet_id
CREDENTIALS_FILE=credentials.json

# Browser
CHROMEDRIVER_PATH=chromedriver.exe

# Optional: run Chrome headless (recommended for CI)
DD_HEADLESS=1

# Bot Settings
DD_DEBUG=0
DD_MAX_PROFILES=0
DD_MAX_POST_PAGES=4
DD_AUTO_PUSH=0

# Optional: Auto-populate IMG_LINK in PostQueue from POST_LINK
DD_POPULATE_IMG_LINKS=0
```

## Usage

### Interactive Menu (Recommended)

Run without arguments:

```bash
python main.py
```

You can choose:

- **1** Message Mode
- **2** Post Mode
- **3** Inbox Mode
- **4** Populate IMG_LINK (PostQueue)

Then enter `0` to process all rows, or a number to limit.

### CLI (non-interactive)

If you are running via GitHub Actions / automation, always use `--no-menu`.

You can choose:

- **1** Message Mode
- **2** Post Mode
- **3** Inbox Mode
- **4** Populate IMG_LINK (PostQueue)

Then enter `0` to process all rows, or a number to limit.

### POPULATE Mode (Rekhta populate / queue helpers)

```bash
# Preview populate (no write)
python main.py --mode populate --no-menu --populate-limit 10

# Write results to PostQueue
python main.py --mode populate --no-menu --populate-limit 10 --populate-write
```

## Configuration Options

**Environment Variables:**

- `DD_LOGIN_EMAIL`: DamaDam username (required)
- `DD_LOGIN_PASS`: DamaDam password (required)
- `DD_LOGIN_EMAIL2`: Secondary username (optional)
- `DD_LOGIN_PASS2`: Secondary password (optional)
- `DD_SHEET_ID`: Main Google Sheet ID (required)
- `DD_PROFILES_SHEET_ID`: Profiles sheet ID (optional)
- `CREDENTIALS_FILE`: Google credentials file path (default: `credentials.json`)
- `CHROMEDRIVER_PATH`: ChromeDriver path (default: `chromedriver.exe`, or use `auto`)
- `DD_HEADLESS`: Run Chrome headless (`1`/`0`, default `1`)
- `DD_DEBUG`: Enable debug logging (`1`/`0`, default `0`)
- `DD_DRY_RUN`: Global dry-run (`1`/`0`, default `0`)
- `DD_MAX_PROFILES`: Max targets to process (`0` = unlimited)
- `DD_MAX_POST_PAGES`: Max pages to search for open posts (default: `4`)
- `DD_POST_COOLDOWN_SECONDS`: Delay between posts (default: `120`)
- `DD_POST_RETRY_FAILED`: Retry rows with `STATUS=Failed` (`1`/`0`)
- `DD_POST_MAX_ATTEMPTS`: Max attempts per row when retry enabled
- `DD_POST_DENIED_RETRIES`: Backoff retries for denied redirects
- `DD_POST_DENIED_BACKOFF_SECONDS`: Backoff seconds for denied redirects
- `DD_POST_MAX_REPEAT_CHARS`: Repeated char clamp (default: `6`)
- `DD_POST_CAPTION_MAX_LEN`: Caption max length (default: `300`)
- `DD_POST_TAGS_MAX_LEN`: Tags max length (default: `120`)
- `DD_IMAGE_DOWNLOAD_TIMEOUT_SECONDS`: Image download timeout (default: `90`)
- `DD_IMAGE_DOWNLOAD_RETRIES`: Image download retries (default: `3`)
- `DD_IMAGE_DOWNLOAD_RETRY_DELAY_SECONDS`: Retry delay seconds (default: `5`)
- `DD_AUTO_PUSH`: Auto push after run (default: `0`)

For a full template, see `.env.sample`.

**CLI Flags:**

- `--mode {msg,populate,post,inbox,logs,setup}`
- `--max-profiles N`
- `--dry-run`
- `--no-menu`
- `--populate-img-links`
- `--populate-limit N`
- `--populate-write`

## GitHub Actions (Manual Dashboard)

This repo includes a single workflow:

- `.github/workflows/dashboard.yml` (Run workflow button)

**Required GitHub Secrets:**

- `DD_LOGIN_EMAIL`
- `DD_LOGIN_PASS`
- `DD_SHEET_ID`
- `GOOGLE_CREDENTIALS_JSON` (paste your `credentials.json` content)

**How to run:**

1. Go to **Actions** tab
2. Open **DamaDam Dashboard**
3. Click **Run workflow**
4. Select `mode` and options like `max_profiles`, `dry_run`, etc.

Logs are uploaded automatically as an artifact (`logs/*.log`).

## Example Usage Workflows

### Workflow 1: Mass Personal Messaging

1. Add targets to `MsgList`:

```text
MODE: nick
NAME: User1
NICK/URL: user1
MESSAGE: Hi {{name}}! Love your posts!
STATUS: pending
```

1. Run bot:

```bash
python main.py --mode msg --max-profiles 20
```

1. Check results in `MsgList` (STATUS, NOTES, RESULT URL)
1. Review history in `MsgHistory` sheet

### Workflow 2: Daily Content Posting

1. Prepare posts in `PostQueue`:

```text
TYPE: text
TITLE: Daily Tip
CONTENT: Today's tip: Stay positive!
TAGS: motivation,tips
STATUS: pending
```

1. Run bot:

```bash
python main.py --mode post
```

1. Post URLs saved in `PostQueue`

### Workflow 3: Inbox Management

1. Run to fetch new messages:

```bash
python main.py --mode inbox
```

1. New conversations appear in `InboxQueue`

1. Add your replies in MY_REPLY column

1. Run again to send:

```bash
python main.py --mode inbox
```

1. Full conversation saved in CONVERSATION_LOG

## Security

- Never commit `.env` or `credentials.json`
- Use `.gitignore` to exclude sensitive files
- Rotate credentials regularly
- Use strong passwords

## Performance Tips

1. **Rate Limiting**: Bot includes 2-3 second delays between actions
2. **Batch Processing**: Use `--max-profiles` to limit targets
3. **Error Recovery**: Failed items stay as `pending` for retry
4. **API Efficiency**: Batched sheet updates minimize API calls

## Support

For issues:

1. Check logs in `logs/` folder
2. Enable debug mode: `DD_DEBUG=1`
3. Review error in NOTES column
4. Check this documentation

## License

MIT License - Use responsibly and ethically.

---

**Version:** 2.0.0  
**Last Updated:** January 2025