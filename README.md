# Hyderabad Flat Finder

Automated Facebook group scraper to find single room / replacement listings in Hyderabad.

Monitors Facebook groups for flat/room postings in Financial District, Gachibowli, Narsingi, Kokapet, Nanakramguda, Raidurg, and Wipro Circle areas, within ₹15K-25K budget range.

## Setup

### 1. Install Python dependencies

```bash
cd ~/Projects/hyderabad-flat-finder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your credentials
```

**Facebook**: Use a secondary account. Your primary account may get flagged.

**Telegram Bot** (recommended for notifications):
1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → get your bot token
2. Message [@userinfobot](https://t.me/userinfobot) → get your chat ID
3. Start a chat with your bot (message it anything once)
4. Add both values to `.env`

### 3. First run (with visible browser)

```bash
python main.py --no-headless --scrolls 3 --groups 0
```

This opens a visible browser so you can:
- Complete Facebook login
- Handle 2FA if needed
- Verify the scraper finds posts correctly

Cookies are saved automatically for future headless runs.

### 4. Test notifications

```bash
python main.py --notify-test
```

### 5. Production run

```bash
python main.py --headless
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--headless` | Run browser without UI (default for cron) |
| `--no-headless` | Show browser UI (for login/debugging) |
| `--dry-run` | Scrape and save but skip notifications |
| `--groups 0,1,2` | Only scrape specific group indices |
| `--scrolls 5` | Override scroll count per group |
| `--notify-test` | Send a test notification and exit |

## Automation (Cron)

Run every 4 hours:

```bash
crontab -e
```

Add:

```
0 */4 * * * cd /Users/adarshpandey/Projects/hyderabad-flat-finder && /Users/adarshpandey/Projects/hyderabad-flat-finder/venv/bin/python main.py --headless >> data/cron.log 2>&1
```

## Adding More Groups

Edit `TARGET_GROUPS` in `config.py`:

```python
TARGET_GROUPS = [
    # ... existing groups ...
    {
        "name": "Your New Group Name",
        "url": "https://www.facebook.com/groups/group-slug/",
    },
]
```

Find the group URL by visiting the group on Facebook and copying the address bar URL.

## Output Files

All output is saved in the `data/` directory:

| File | Description |
|------|-------------|
| `posts.json` | All scraped posts (structured JSON) |
| `posts.csv` | Same data as CSV for spreadsheet use |
| `last_run.json` | Metadata about the last run |
| `cookies.json` | Facebook session cookies (auto-managed) |
| `cron.log` | Cron job output log |

## How It Works

1. **Scraper** (`scraper.py`): Playwright browser logs into Facebook, visits each group, scrolls to load posts, extracts raw text and metadata
2. **Parser** (`parser.py`): Regex-based extraction of price (₹/Rs/k formats), location, phone numbers, BHK type from unstructured text; computes relevance score
3. **Storage** (`storage.py`): Deduplicates by URL + content similarity + phone+price match; saves to JSON/CSV
4. **Notifier** (`notifier.py`): Sends Telegram/email alerts for new matching posts

## Troubleshooting

- **Login fails**: Run with `--no-headless` to login manually. Cookies persist for weeks.
- **No posts found**: Facebook may have changed DOM selectors. Check `data/debug_*.png` screenshots.
- **Cookie expiry**: Re-run with `--no-headless` once to refresh the session.
- **2FA every time**: Use an app password or disable 2FA on your scraper account.

## Disclaimer

This tool is for personal use. Facebook's Terms of Service may prohibit automated scraping. Use at your own risk with a secondary account.
