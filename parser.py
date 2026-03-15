"""Extract structured data from raw Facebook post text."""

from __future__ import annotations

import re
from typing import Optional, Tuple, List

import config


class PostParser:
    """Parse unstructured post text to extract price, location, contacts, etc."""

    # ── Price patterns ─────────────────────────────────────────────────────
    PRICE_PATTERNS = [
        # ₹15,000 / ₹15000 / Rs.15,000 / Rs 15000 / INR 15000
        r"(?:₹|rs\.?|inr)\s*([\d,]+)",
        # 15k / 15K / 15.5k
        r"(\d+(?:\.\d+)?)\s*[kK]",
        # rent 15000 / rent: 15,000
        r"rent\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*([\d,]+)",
        # 15,000/- or 15000/-
        r"([\d,]+)\s*/\-",
        # standalone 5-digit number likely a rent (10000-99999)
        r"\b(\d{5})\b",
    ]

    # ── Phone patterns ─────────────────────────────────────────────────────
    PHONE_PATTERN = re.compile(
        r"(?:\+?91[\s\-]?)?([6-9]\d{4}[\s\-]?\d{5})"
    )

    # ── BHK pattern ────────────────────────────────────────────────────────
    BHK_PATTERN = re.compile(r"([1-4])\s*bhk", re.IGNORECASE)

    def __init__(self):
        self.locations = config.TARGET_LOCATIONS
        self.canonical = config.LOCATION_CANONICAL
        self.budget_min = config.BUDGET_MIN
        self.budget_max = config.BUDGET_MAX
        self.budget_tolerance = config.BUDGET_TOLERANCE
        self.include_kw = config.INCLUDE_KEYWORDS
        self.exclude_kw = config.EXCLUDE_KEYWORDS

    def parse(self, raw_post: dict) -> dict:
        """Parse a raw post dict into a structured result."""
        text = raw_post.get("raw_text", "")
        text_lower = text.lower()

        price, price_raw = self.extract_price(text_lower)
        location, all_locations = self.extract_locations(text_lower)
        phones = self.extract_phones(text)
        bhk = self.extract_bhk(text_lower)

        parsed = {
            "date": raw_post.get("timestamp_text", ""),
            "group_name": raw_post.get("group_name", ""),
            "group_url": raw_post.get("group_url", ""),
            "location": location,
            "all_locations": all_locations,
            "price": price,
            "price_raw": price_raw,
            "description": text,
            "contact": ", ".join(phones) if phones else "",
            "phone_numbers": phones,
            "post_url": raw_post.get("post_url", ""),
            "author": raw_post.get("author", ""),
            "bhk_type": bhk,
            "scraped_at": raw_post.get("scraped_at", ""),
        }

        parsed["relevance_score"] = self._compute_relevance(parsed, text_lower)
        return parsed

    def extract_price(self, text: str) -> tuple[Optional[int], Optional[str]]:
        """Extract rent price from text. Returns (numeric_value, raw_string)."""
        for pattern in self.PRICE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw = match.group(0)
                num_str = match.group(1).replace(",", "").replace(" ", "").replace("-", "")
                try:
                    value = float(num_str)
                    # Handle 'k' suffix
                    if re.search(r"[kK]", raw):
                        value *= 1000
                    value = int(value)
                    # Sanity check: rent should be between 3000 and 100000
                    if 3000 <= value <= 100_000:
                        return value, raw.strip()
                except ValueError:
                    continue
        return None, None

    def extract_locations(self, text: str) -> tuple[Optional[str], list[str]]:
        """Extract matched locations from text."""
        found = []
        for loc in self.locations:
            # Word boundary search to avoid partial matches
            pattern = r"\b" + re.escape(loc) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                canonical = self.canonical.get(loc, loc.title())
                if canonical not in found:
                    found.append(canonical)

        # Also check for "FD" as Financial District (needs special handling)
        if re.search(r"\bfd\b", text, re.IGNORECASE):
            if "Financial District" not in found:
                found.append("Financial District")

        primary = found[0] if found else None
        return primary, found

    def extract_phones(self, text: str) -> list[str]:
        """Extract Indian mobile numbers from text."""
        matches = self.PHONE_PATTERN.findall(text)
        # Clean up: remove spaces and hyphens
        cleaned = []
        seen = set()
        for m in matches:
            num = re.sub(r"[\s\-]", "", m)
            if len(num) == 10 and num not in seen:
                cleaned.append(num)
                seen.add(num)
        return cleaned

    def extract_bhk(self, text: str) -> Optional[str]:
        """Extract BHK type from text."""
        match = self.BHK_PATTERN.search(text)
        if match:
            return f"{match.group(1)}BHK"

        # Check for common phrases
        if "single room" in text or "single sharing" in text:
            return "Single Room"
        if "double sharing" in text or "double room" in text:
            return "Double Sharing"
        if "triple sharing" in text:
            return "Triple Sharing"
        return None

    def is_relevant(self, parsed: dict) -> bool:
        """Check if a parsed post matches our criteria."""
        text_lower = parsed["description"].lower()

        # Must have at least one include keyword
        has_keyword = any(kw in text_lower for kw in self.include_kw)
        if not has_keyword and parsed["relevance_score"] < 0.4:
            return False

        # Exclude unwanted posts
        has_exclude = any(kw in text_lower for kw in self.exclude_kw)
        if has_exclude:
            return False

        # Location check (relaxed: if no location found, still include if score is decent)
        has_location = bool(parsed["location"])

        # Price check (if price is found, it must be in range)
        price = parsed["price"]
        max_with_tolerance = self.budget_max * (1 + self.budget_tolerance)
        if price is not None and (price < self.budget_min or price > max_with_tolerance):
            return False

        # Must have location OR high relevance
        if not has_location and parsed["relevance_score"] < 0.5:
            return False

        return True

    def _compute_relevance(self, parsed: dict, text_lower: str) -> float:
        """Compute a 0.0-1.0 relevance score."""
        score = 0.0

        # Location match
        if parsed["location"]:
            score += 0.3

        # Price in budget
        price = parsed["price"]
        if price is not None and self.budget_min <= price <= self.budget_max:
            score += 0.3
        elif price is None:
            score += 0.1  # Unknown price, slight boost

        # Keyword matches
        kw_matches = sum(1 for kw in self.include_kw if kw in text_lower)
        score += min(kw_matches * 0.08, 0.3)

        # Contact info present
        if parsed["phone_numbers"]:
            score += 0.1

        # Penalty for exclude keywords
        if any(kw in text_lower for kw in self.exclude_kw):
            score -= 0.5

        return max(0.0, min(1.0, score))
