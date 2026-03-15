#!/usr/bin/env python3
"""Discover Facebook groups the user has joined related to flats/flatmates in Hyderabad."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from playwright.async_api import async_playwright

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Keywords to identify flat/room-related groups
GROUP_KEYWORDS = [
    "flat", "flatmate", "room", "rent", "roommate",
    "house", "apartment", "sharing", "pg", "accommodation",
    "tenant", "1bhk", "2bhk", "3bhk", "bachelor",
]

CITY_KEYWORDS = [
    "hyderabad", "hyd", "hitech", "gachibowli", "kondapur",
    "madhapur", "secunderabad", "financial district",
]


async def discover_groups():
    """Navigate to user's Facebook groups page and find relevant groups."""
    env = config.load_env()
    data_dir = config.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    cookies_path = data_dir / "cookies.json"

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=config.USER_AGENT,
        locale="en-US",
    )

    # Load cookies
    if cookies_path.exists():
        with open(cookies_path) as f:
            await context.add_cookies(json.load(f))

    page = await context.new_page()

    # Check login
    cookies = await context.cookies()
    if not any(c["name"] == "c_user" for c in cookies):
        logger.error("Not logged in. Run main.py --no-headless first to login.")
        await browser.close()
        await pw.stop()
        return

    logger.info("Navigating to your Facebook groups page...")
    await page.goto("https://www.facebook.com/groups/joins/", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(5)

    # Scroll extensively to load ALL groups
    logger.info("Scrolling to load all groups...")
    for _ in range(25):
        await page.keyboard.press("End")
        await asyncio.sleep(1.5)

    # Extract group names and URLs
    js_code = """
        () => {
            const links = document.querySelectorAll('a[href*="/groups/"]');
            const groups = [];
            const seen = new Set();

            for (const link of links) {
                const href = link.href || '';
                const text = (link.innerText || '').trim();

                // Filter: must be a group link, not a post or settings link
                if (!href.includes('/groups/')) continue;
                if (href.includes('/posts/') || href.includes('/settings') ||
                    href.includes('/members') || href.includes('/about')) continue;

                // Extract group slug
                const match = href.match(/facebook\\.com\\/groups\\/([^/?]+)/);
                if (!match) continue;

                const slug = match[1];
                if (slug === 'joins' || slug === 'feed' || slug === 'discover') continue;
                if (seen.has(slug)) continue;
                seen.add(slug);

                // Get the visible text (group name)
                let name = text.split('\\n')[0].trim();
                if (name.length < 3 || name.length > 100) continue;

                groups.push({
                    name: name,
                    url: 'https://www.facebook.com/groups/' + slug + '/',
                    slug: slug
                });
            }
            return groups;
        }
    """

    all_groups = await page.evaluate(js_code)
    logger.info(f"Found {len(all_groups)} total groups")

    # Filter for flat/room related groups in Hyderabad
    # Include if group has EITHER a flat keyword OR a city keyword (relaxed matching)
    relevant = []
    partial = []
    for g in all_groups:
        name_lower = g["name"].lower()
        has_flat_kw = any(kw in name_lower for kw in GROUP_KEYWORDS)
        has_city_kw = any(kw in name_lower for kw in CITY_KEYWORDS)

        if has_flat_kw and has_city_kw:
            relevant.append(g)
            logger.info(f"  MATCH: {g['name']} -> {g['url']}")
        elif has_flat_kw or has_city_kw:
            partial.append(g)
            logger.info(f"  PARTIAL: {g['name']} -> {g['url']}")

    # Include partial matches too — more groups = more listings
    relevant.extend(partial)

    # Save cookies
    cookies = await context.cookies()
    with open(cookies_path, "w") as f:
        json.dump(cookies, f, indent=2)

    await browser.close()
    await pw.stop()

    # Save discovered groups
    output_path = data_dir / "discovered_groups.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(relevant, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Found {len(relevant)} flat/room related Hyderabad groups:")
    print(f"{'='*60}")
    for i, g in enumerate(relevant):
        print(f"  {i}. {g['name']}")
        print(f"     {g['url']}")

    print(f"\nSaved to: {output_path}")
    print(f"\nTo use these groups, add them to TARGET_GROUPS in config.py")
    print(f"Or run: python main.py --auto-groups")

    # Generate config snippet
    print(f"\n{'='*60}")
    print("Copy this to config.py TARGET_GROUPS:")
    print(f"{'='*60}")
    for g in relevant:
        print(f'    {{"name": "{g["name"]}", "url": "{g["url"]}"}},')

    return relevant


if __name__ == "__main__":
    asyncio.run(discover_groups())
