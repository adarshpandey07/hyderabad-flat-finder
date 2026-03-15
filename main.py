#!/usr/bin/env python3
"""
Hyderabad Flat Finder - Facebook Group Scraper
Automatically finds single room / replacement listings in Hyderabad.
"""

import argparse
import asyncio
import logging
import sys

import config
from notifier import get_notifiers
from parser import PostParser
from scraper import FacebookScraper
from storage import PostStore

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("flat-finder")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hyderabad Flat Finder Scraper")
    parser.add_argument(
        "--headless", action="store_true", default=None, help="Run browser in headless mode"
    )
    parser.add_argument(
        "--no-headless", action="store_true", help="Run browser with visible UI (for login/debug)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Scrape and parse but do not send notifications"
    )
    parser.add_argument(
        "--groups",
        type=str,
        default=None,
        help="Comma-separated group indices to scrape (e.g., 0,1,2)",
    )
    parser.add_argument(
        "--notify-test", action="store_true", help="Send a test notification and exit"
    )
    parser.add_argument(
        "--auto-groups",
        action="store_true",
        help="Use auto-discovered groups from data/discovered_groups.json",
    )
    parser.add_argument(
        "--scrolls",
        type=int,
        default=None,
        help=f"Override scroll count per group (default: {config.SCROLL_COUNT})",
    )
    return parser.parse_args()


async def send_test_notification(env_config: dict) -> None:
    """Send a test notification to verify setup."""
    notifiers = get_notifiers(env_config)
    if not notifiers:
        logger.error("No notifiers configured. Check your .env file.")
        return

    test_post = {
        "location": "Gachibowli",
        "price": 18000,
        "contact": "9876543210",
        "bhk_type": "1BHK",
        "description": "This is a test notification from Hyderabad Flat Finder.",
        "post_url": "https://facebook.com/test",
        "group_name": "Test Group",
        "relevance_score": 0.95,
    }

    for notifier in notifiers:
        success = await notifier.send(test_post)
        name = type(notifier).__name__
        if success:
            logger.info(f"Test notification sent via {name}")
        else:
            logger.error(f"Test notification FAILED via {name}")


async def main() -> None:
    args = parse_args()
    env_config = config.load_env()

    # ── Test notification mode ─────────────────────────────────────────────
    if args.notify_test:
        await send_test_notification(env_config)
        return

    # ── Validate credentials ──────────────────────────────────────────────
    if not env_config["fb_email"] or not env_config["fb_password"]:
        logger.error("FB_EMAIL and FB_PASSWORD must be set in .env file")
        sys.exit(1)

    # ── Resolve headless mode ─────────────────────────────────────────────
    headless = config.HEADLESS
    if args.headless:
        headless = True
    elif args.no_headless:
        headless = False

    # ── Override scroll count ─────────────────────────────────────────────
    if args.scrolls:
        config.SCROLL_COUNT = args.scrolls

    # ── Select groups ─────────────────────────────────────────────────────
    groups = config.TARGET_GROUPS
    if args.auto_groups:
        discovered_path = config.DATA_DIR / "discovered_groups.json"
        if discovered_path.exists():
            import json as _json
            with open(discovered_path) as f:
                discovered = _json.load(f)
            # Merge: discovered + configured (dedup by URL)
            seen_urls = {g["url"] for g in groups}
            for g in discovered:
                if g["url"] not in seen_urls:
                    groups.append(g)
                    seen_urls.add(g["url"])
            logger.info(f"Using {len(groups)} groups (config + discovered)")
        else:
            logger.warning("No discovered_groups.json found. Run discover_groups.py first.")
    if args.groups:
        indices = [int(i.strip()) for i in args.groups.split(",")]
        groups = [config.TARGET_GROUPS[i] for i in indices if i < len(config.TARGET_GROUPS)]
        logger.info(f"Scraping {len(groups)} selected groups")

    # ── Initialize components ─────────────────────────────────────────────
    store = PostStore()
    parser = PostParser()
    notifiers = get_notifiers(env_config) if not args.dry_run else []

    last_run = store.get_last_run_time()
    if last_run:
        logger.info(f"Last run: {last_run.strftime('%Y-%m-%d %H:%M')}")
    else:
        logger.info("First run")

    # ── Scrape ────────────────────────────────────────────────────────────
    scraper = FacebookScraper(env_config, headless=headless)
    raw_posts = []

    try:
        await scraper.start_browser()

        if not await scraper.login():
            logger.error("Login failed. Exiting.")
            for n in notifiers:
                await n.send_error("Facebook login failed. Please re-login manually.")
            await scraper.close()
            sys.exit(1)

        raw_posts = await scraper.scrape_all_groups(groups)

    except Exception as e:
        logger.error(f"Scraper error: {e}")
        for n in notifiers:
            await n.send_error(f"Scraper crashed: {e}")
    finally:
        await scraper.close()

    if not raw_posts:
        logger.info("No posts scraped")
        for n in notifiers:
            await n.send_summary(0, len(store.posts))
        return

    # ── Parse all posts ──────────────────────────────────────────────────
    all_parsed = []
    relevant = []
    for raw in raw_posts:
        parsed = parser.parse(raw)
        all_parsed.append(parsed)
        if parser.is_relevant(parsed):
            relevant.append(parsed)

    logger.info(f"Relevant posts: {len(relevant)} / {len(raw_posts)} total")

    # Log non-relevant posts for debugging
    for p in all_parsed:
        if p not in relevant:
            loc = p.get("location", "no-loc")
            price = p.get("price", "no-price")
            score = p.get("relevance_score", 0)
            desc = p.get("description", "")[:80].replace("\n", " ")
            logger.debug(f"Filtered out: loc={loc} price={price} score={score:.2f} | {desc}")

    # ── Deduplicate and store ALL parsed posts (for CSV review) ──────────
    new_posts = store.add_posts(all_parsed)
    store.save()
    logger.info(f"New posts saved: {len(new_posts)} (all), {len(relevant)} relevant")

    # Only notify for relevant posts
    new_relevant = [p for p in new_posts if p in relevant]

    # ── Notify (only relevant posts) ────────────────────────────────────
    if new_relevant and notifiers:
        new_relevant.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)

        for post in new_relevant:
            for n in notifiers:
                await n.send(post)
            await asyncio.sleep(0.5)  # Respect Telegram rate limits

    # Send summary
    for n in notifiers:
        await n.send_summary(len(new_posts), len(store.posts))

    # ── Cleanup old posts ─────────────────────────────────────────────────
    store.cleanup_old_posts()
    store.save()

    # ── Print summary ─────────────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info(f"Run complete:")
    logger.info(f"  Raw posts scraped:  {len(raw_posts)}")
    logger.info(f"  Relevant posts:     {len(relevant)}")
    logger.info(f"  New (non-duplicate): {len(new_posts)} (relevant: {len(new_relevant)})")
    logger.info(f"  Total in database:  {len(store.posts)}")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
