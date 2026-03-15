"""Playwright-based Facebook group scraper."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext

import config

logger = logging.getLogger(__name__)


class FacebookScraper:
    """Scrape posts from Facebook groups using Playwright."""

    def __init__(self, credentials: dict, headless: bool = None):
        self.email = credentials["fb_email"]
        self.password = credentials["fb_password"]
        self.headless = headless if headless is not None else config.HEADLESS
        self.data_dir = config.DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_path = self.data_dir / "cookies.json"

        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start_browser(self) -> None:
        """Launch browser with persistent cookies."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=config.USER_AGENT,
            locale="en-US",
        )

        # Load saved cookies
        if self.cookies_path.exists():
            try:
                with open(self.cookies_path, "r") as f:
                    cookies = json.load(f)
                await self._context.add_cookies(cookies)
                logger.info("Loaded saved cookies")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")

        self._page = await self._context.new_page()

    async def login(self) -> bool:
        """Login to Facebook, or verify existing session."""
        page = self._page

        # Check if cookies already have a session
        cookies = await self._context.cookies()
        c_user = any(c["name"] == "c_user" for c in cookies)
        if c_user:
            logger.info("Already logged in (session cookie found, skipping login page)")
            return True

        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        # Recheck after page load
        cookies = await self._context.cookies()
        c_user = any(c["name"] == "c_user" for c in cookies)
        if c_user:
            logger.info("Already logged in (session cookie found)")
            return True

        logger.info("Logging in to Facebook...")
        logger.info(f"Current URL: {page.url}")

        try:
            # Accept cookies dialog if present
            try:
                accept_btn = page.locator(
                    'button[data-cookiebanner="accept_button"], '
                    'button[data-testid="cookie-policy-manage-dialog-accept-button"], '
                    'button:has-text("Allow"), button:has-text("Accept")'
                )
                if await accept_btn.count() > 0:
                    await accept_btn.first.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Take debug screenshot to see current state
            await page.screenshot(path=str(self.data_dir / "debug_before_login.png"))
            logger.info("Screenshot saved: debug_before_login.png")

            # Check for "Continue" button (remembered account flow)
            continue_btn = page.locator(
                'div[role="button"]:has-text("Continue"), '
                'span:has-text("Continue")'
            )
            email_input = page.locator('input#email, input[name="email"]')

            if await continue_btn.count() > 0 and not await email_input.is_visible():
                # Remembered account — click "Continue" then enter password
                logger.info("Remembered account detected, clicking Continue...")
                await continue_btn.first.click()
                await asyncio.sleep(3)

                # Now password field should appear
                pass_input = page.locator('input#pass, input[name="pass"], input[type="password"]')
                await pass_input.wait_for(state="visible", timeout=10000)
                await pass_input.click()
                await pass_input.fill(self.password)
                await asyncio.sleep(random.uniform(0.5, 1.5))

                logger.info("Submitting password...")
                await pass_input.press("Enter")
            else:
                # Standard email + password login form
                await email_input.wait_for(state="visible", timeout=10000)
                await email_input.click()
                await email_input.fill(self.email)
                await asyncio.sleep(random.uniform(0.5, 1.5))

                pass_input = page.locator('input#pass, input[name="pass"]')
                await pass_input.click()
                await pass_input.fill(self.password)
                await asyncio.sleep(random.uniform(0.5, 1.5))

                logger.info("Submitting login form...")
                await pass_input.press("Enter")

            # Wait for navigation after login
            try:
                await page.wait_for_url(
                    lambda url: "facebook.com" in url and url != "https://www.facebook.com/",
                    timeout=15000,
                )
            except Exception:
                pass  # URL may not change if login fails
            await asyncio.sleep(3)
            logger.info(f"Post-login URL: {page.url}")

            # Check for 2FA or checkpoint
            if "checkpoint" in page.url or "two_step_verification" in page.url:
                await page.screenshot(path=str(self.data_dir / "debug_2fa.png"))
                if self.headless:
                    logger.error(
                        "2FA required! Run with --no-headless first to complete 2FA manually."
                    )
                    return False
                else:
                    logger.info("2FA/checkpoint detected. Please complete it in the browser...")
                    # Wait up to 180 seconds for manual 2FA
                    for _ in range(90):
                        await asyncio.sleep(2)
                        current_cookies = await self._context.cookies()
                        if any(c["name"] == "c_user" for c in current_cookies):
                            break
                    else:
                        logger.error("2FA timeout after 180 seconds")
                        return False

            # Verify login
            current_cookies = await self._context.cookies()
            if any(c["name"] == "c_user" for c in current_cookies):
                await self._save_cookies()
                logger.info("Login successful")
                return True

            logger.error("Login failed - no session cookie after login attempt")
            await page.screenshot(path=str(self.data_dir / "debug_login_failed.png"))
            logger.info("Screenshot saved: debug_login_failed.png")
            return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            try:
                await page.screenshot(path=str(self.data_dir / "debug_login_error.png"))
            except Exception:
                pass
            return False

    async def scrape_group(self, group: dict) -> list[dict]:
        """Scrape posts from a single Facebook group."""
        group_name = group["name"]
        group_url = group["url"]
        page = self._page

        logger.info(f"Scraping group: {group_name}")

        try:
            await page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))

            # Check if we can access the group
            page_text = await page.text_content("body") or ""
            if "join group" in page_text.lower() and "write something" not in page_text.lower():
                logger.warning(f"Not a member of group: {group_name}. Skipping.")
                return []

        except Exception as e:
            logger.error(f"Failed to load group {group_name}: {e}")
            return []

        # Scroll and extract posts incrementally.
        # Facebook uses virtualized rendering — only ~3-5 posts exist in DOM at once.
        # We must extract DURING scrolling, not after.
        all_posts = []
        seen_keys = set()
        logger.info(f"Scrolling {config.SCROLL_COUNT} times (extracting after each scroll)...")

        for scroll_num in range(config.SCROLL_COUNT):
            # Click "See more" on currently visible posts
            await self._expand_all_posts(page)

            # Extract whatever is currently in the DOM
            batch = await self._extract_posts_from_page(page, group_name, group_url, seen_keys)
            all_posts.extend(batch)

            # Scroll down to load new posts (old ones will be removed from DOM)
            await page.keyboard.press("End")
            pause = random.uniform(config.SCROLL_PAUSE_MIN, config.SCROLL_PAUSE_MAX)
            await asyncio.sleep(pause)

            if batch:
                logger.debug(f"Scroll {scroll_num + 1}: +{len(batch)} posts (total: {len(all_posts)})")

        # Final extraction after last scroll
        await self._expand_all_posts(page)
        final_batch = await self._extract_posts_from_page(page, group_name, group_url, seen_keys)
        all_posts.extend(final_batch)

        logger.info(f"Extracted {len(all_posts)} posts from {group_name}")
        return all_posts

    async def _expand_all_posts(self, page: Page) -> None:
        """Click all 'See more' buttons to expand truncated post text."""
        try:
            see_more = await page.query_selector_all('div[role="button"]')
            clicked = 0
            for btn in see_more:
                try:
                    text = await btn.inner_text()
                    if text.strip().lower() == "see more":
                        await btn.click()
                        clicked += 1
                        await asyncio.sleep(0.2)
                except Exception:
                    pass
            if clicked:
                logger.info(f"Expanded {clicked} 'See more' buttons")
                await asyncio.sleep(1)
        except Exception as e:
            logger.debug(f"Error expanding posts: {e}")

    async def _extract_posts_from_page(
        self, page: Page, group_name: str, group_url: str, seen_keys: set = None
    ) -> list[dict]:
        """Extract post data from the loaded feed using dir=auto text blocks."""
        if seen_keys is None:
            seen_keys = set()
        js_code = """
            () => {
                const feed = document.querySelector('div[role="feed"]');
                if (!feed) return [];

                const blocks = feed.querySelectorAll('div[dir="auto"]');
                let results = [];
                let seen = new Set();

                for (const el of blocks) {
                    const text = (el.innerText || '').trim();
                    if (text.length < 40) continue;

                    const key = text.substring(0, 120);
                    if (seen.has(key)) continue;
                    seen.add(key);

                    // Walk up to find post permalink
                    let postUrl = '';
                    let container = el;
                    let postContainer = null;

                    // Extract group slug from the current page URL for matching
                    const groupSlug = location.pathname.replace(/\\/+$/, '');

                    // Phase 1: Walk UP the DOM (increased radius to 30)
                    for (let i = 0; i < 30; i++) {
                        container = container.parentElement;
                        if (!container) break;

                        // Classic permalink selectors
                        const classicLinks = container.querySelectorAll(
                            'a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]'
                        );
                        if (classicLinks.length > 0) {
                            postUrl = classicLinks[0].href.split('?')[0];
                            postContainer = container;
                            break;
                        }

                        // New Facebook "pfbid" permalink format
                        const pfbidLinks = container.querySelectorAll('a[href*="pfbid"]');
                        if (pfbidLinks.length > 0) {
                            postUrl = pfbidLinks[0].href.split('?')[0];
                            postContainer = container;
                            break;
                        }

                        // Links with aria-label containing time text (timestamps are links to the post)
                        const ariaTimeLinks = container.querySelectorAll('a[aria-label]');
                        for (const atl of ariaTimeLinks) {
                            const label = atl.getAttribute('aria-label') || '';
                            if (/\\d+\\s*(hour|minute|day|week|month|year|h|m|d|w)|yesterday|just now|today/i.test(label)) {
                                const href = atl.href || '';
                                if (href && href.includes('facebook.com')) {
                                    postUrl = href.split('?')[0];
                                    postContainer = container;
                                    break;
                                }
                            }
                        }
                        if (postUrl) break;

                        // Group URL slug + numeric ID pattern (e.g. /groups/mygroup/123456789/)
                        if (groupSlug) {
                            const groupLinks = container.querySelectorAll('a[href]');
                            for (const gl of groupLinks) {
                                const href = gl.href || '';
                                if (href.includes(groupSlug) && /\\/\\d{10,}/.test(href)) {
                                    postUrl = href.split('?')[0];
                                    postContainer = container;
                                    break;
                                }
                            }
                            if (postUrl) break;
                        }
                    }

                    // Phase 2: If still no URL, search DOWN from the found container
                    //          (or from the last parent we reached)
                    if (!postUrl && (postContainer || container)) {
                        const searchRoot = postContainer || container;
                        // Try all strategies inside the container, searching downward
                        const downLinks = searchRoot.querySelectorAll('a[href]');
                        for (const dl of downLinks) {
                            const href = dl.href || '';
                            if (!href || !href.includes('facebook.com')) continue;

                            // Classic patterns
                            if (/\\/posts\\/|\\bpermalink\\/|story_fbid|pfbid/.test(href)) {
                                postUrl = href.split('?')[0];
                                break;
                            }
                            // Aria-label timestamp link
                            const label = dl.getAttribute('aria-label') || '';
                            if (/\\d+\\s*(hour|minute|day|week|month|year|h|m|d|w)|yesterday|just now|today/i.test(label)) {
                                postUrl = href.split('?')[0];
                                break;
                            }
                            // Group slug + numeric ID
                            if (groupSlug && href.includes(groupSlug) && /\\/\\d{10,}/.test(href)) {
                                postUrl = href.split('?')[0];
                                break;
                            }
                        }
                    }

                    // Phase 3: Last-resort fallback — any link starting with the group URL
                    if (!postUrl && groupSlug) {
                        let fallbackContainer = el;
                        for (let i = 0; i < 30; i++) {
                            fallbackContainer = fallbackContainer.parentElement;
                            if (!fallbackContainer) break;
                            const allLinks = fallbackContainer.querySelectorAll('a[href]');
                            for (const fl of allLinks) {
                                const href = fl.href || '';
                                if (href.includes(groupSlug) && href !== location.href) {
                                    postUrl = href.split('?')[0];
                                    break;
                                }
                            }
                            if (postUrl) break;
                        }
                    }

                    // Try to find author name (usually in a strong or h3 near the top)
                    let author = '';
                    let authorContainer = el;
                    for (let i = 0; i < 20; i++) {
                        authorContainer = authorContainer.parentElement;
                        if (!authorContainer) break;
                        const heading = authorContainer.querySelector('h3, h4, strong > span, a[role="link"] > strong');
                        if (heading) {
                            author = (heading.innerText || '').trim();
                            if (author.length > 2 && author.length < 60) break;
                            author = '';
                        }
                    }

                    // Try to find timestamp text
                    let timestamp = '';
                    let tsContainer = el;
                    for (let i = 0; i < 20; i++) {
                        tsContainer = tsContainer.parentElement;
                        if (!tsContainer) break;
                        const abbrs = tsContainer.querySelectorAll('abbr, a[href*="/posts/"] span, a[href*="/permalink/"] span');
                        for (const abbr of abbrs) {
                            const t = (abbr.innerText || '').trim();
                            if (/\\d+\\s*(h|hr|min|m|d|w)\\b|hour|minute|day|week|yesterday|just now/i.test(t)) {
                                timestamp = t;
                                break;
                            }
                        }
                        if (timestamp) break;
                    }

                    results.push({
                        text: text.substring(0, 2000),
                        url: postUrl,
                        author: author,
                        timestamp: timestamp
                    });

                    if (results.length >= 100) break;
                }
                return results;
            }
        """

        raw_posts = await page.evaluate(js_code)
        posts = []

        for raw in raw_posts:
            # Deduplicate across scrolls using first 120 chars of text
            key = raw["text"][:120]
            if key in seen_keys:
                continue
            seen_keys.add(key)

            posts.append({
                "raw_text": raw["text"],
                "post_url": raw["url"],
                "timestamp_text": raw["timestamp"],
                "author": raw["author"],
                "group_name": group_name,
                "group_url": group_url,
                "scraped_at": datetime.now().isoformat(),
            })

        return posts

    async def scrape_all_groups(self, groups: list[dict] = None) -> list[dict]:
        """Scrape posts from all configured groups."""
        groups = groups or config.TARGET_GROUPS
        all_posts = []

        for i, group in enumerate(groups):
            try:
                posts = await self.scrape_group(group)
                all_posts.extend(posts)
            except Exception as e:
                logger.error(f"Error scraping {group['name']}: {e}")

            # Random delay between groups (except after last)
            if i < len(groups) - 1:
                delay = random.uniform(
                    config.DELAY_BETWEEN_GROUPS_MIN,
                    config.DELAY_BETWEEN_GROUPS_MAX,
                )
                logger.info(f"Waiting {delay:.0f}s before next group...")
                await asyncio.sleep(delay)

        logger.info(f"Total raw posts scraped: {len(all_posts)}")
        return all_posts

    async def _save_cookies(self) -> None:
        """Save browser cookies for session persistence."""
        try:
            cookies = await self._context.cookies()
            with open(self.cookies_path, "w") as f:
                json.dump(cookies, f, indent=2)
            logger.info("Cookies saved")
        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")

    async def close(self) -> None:
        """Save cookies and close browser."""
        if self._context:
            await self._save_cookies()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")
