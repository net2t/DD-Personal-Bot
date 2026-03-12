"""
modes/rekhta.py — DD-Msg-Bot V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rekhta Mode: Scrape poetry image cards from rekhta.org/shayari-image
and populate the PostQueue sheet.

What it does:
  1. Opens rekhta.org/shayari-image (infinite scroll page)
  2. Scrolls the page REKHTA_MAX_SCROLLS times to load cards
  3. Parses each card for: image URL, Roman Urdu text, poet name
  4. Converts Roman Urdu to Urdu script via Claude API (roman_to_urdu())
  5. BATCH duplicate check: loads all existing IMG_LINK values from PostQueue
     at start — no per-row comparison during scraping
  6. Appends only NEW entries to PostQueue with STATUS=Pending

Card HTML structure (from provided HTML):
  div.shyriImgBox
    div.shyriImg
      a.shyriImgInner[style*='url(...)']   ← background-image contains _small or _medium URL
        img[data-src=...]                   ← direct image URL (webp, fallback jpg)
    div.shyriImgFooter
      p.shyriImgLine > a                   ← Roman Urdu first line text
      h4.shyriImgPoetName > a              ← Poet name
"""

import re
import time
from typing import List, Dict, Set, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import Config
from utils.logger import Logger, pkt_stamp
from utils.helpers import roman_to_urdu
from core.sheets import SheetsManager


def run(driver, sheets: SheetsManager, logger: Logger,
        max_items: int = 0) -> Dict:
    """
    Run Rekhta Mode end-to-end.

    Args:
        driver:    Selenium WebDriver (login not required for Rekhta)
        sheets:    Connected SheetsManager
        logger:    Logger
        max_items: 0 = add all new found; N = stop after N new rows added

    Returns:
        Stats dict: {added, skipped_dup, total_scraped}
    """
    logger.section("REKHTA MODE")

    # ── Get PostQueue sheet ───────────────────────────────────────────────────
    ws = sheets.get_worksheet(Config.SHEET_POST_QUEUE, headers=Config.POST_QUEUE_COLS)
    if not ws:
        logger.error("PostQueue sheet not found")
        return {}

    headers    = [c for c in Config.POST_QUEUE_COLS]  # use canonical headers
    col_img    = sheets.get_col(headers, "IMG_LINK")

    # ── BATCH duplicate check — load all existing IMG_LINK values at once ────
    # This is O(1) per scraped item instead of O(n) per item.
    existing_img_links: Set[str] = set()
    if col_img:
        raw_col = sheets.read_col_values(ws, col_img)
        for v in raw_col:
            if v:
                existing_img_links.add(_normalize_img_url(v))
        logger.info(f"Existing PostQueue entries: {len(existing_img_links)} image URLs loaded")

    # ── Scrape Rekhta listing page ────────────────────────────────────────────
    logger.info(f"Opening: {Config.REKHTA_URL}")
    driver.get(Config.REKHTA_URL)
    time.sleep(4)

    # Scroll down to load more cards
    # The page uses infinite scroll — each scroll loads approximately 9–12 more cards
    scroll_count = Config.REKHTA_MAX_SCROLLS
    for scroll_num in range(1, scroll_count + 1):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.5)
        logger.debug(f"Scroll {scroll_num}/{scroll_count} done")

    # ── Parse all cards ───────────────────────────────────────────────────────
    logger.info("Parsing poetry cards...")
    cards = driver.find_elements(By.CSS_SELECTOR, "div.shyriImgBox")
    logger.info(f"Found {len(cards)} cards on page")

    scraped: List[Dict] = []
    for card in cards:
        item = _parse_card(card, logger)
        if item:
            scraped.append(item)

    logger.info(f"Successfully parsed {len(scraped)} cards")

    # ── Filter duplicates and apply limit ────────────────────────────────────
    new_items: List[Dict] = []
    dup_count = 0

    for item in scraped:
        norm_url = _normalize_img_url(item["img_link"])
        if norm_url in existing_img_links:
            dup_count += 1
            continue
        new_items.append(item)
        existing_img_links.add(norm_url)  # Mark as seen within this run
        if max_items and len(new_items) >= max_items:
            break

    logger.info(f"New: {len(new_items)} | Duplicates skipped: {dup_count}")

    if not new_items:
        logger.info("No new items to add — PostQueue is up to date")
        return {"added": 0, "skipped_dup": dup_count, "total_scraped": len(scraped)}

    # ── Convert Roman Urdu → Urdu script and append to sheet ─────────────────
    added = 0
    for idx, item in enumerate(new_items, start=1):
        logger.info(f"[{idx}/{len(new_items)}] Converting: {item['roman_text'][:50]}...")

        # Convert to Urdu script using Claude API
        urdu_caption = roman_to_urdu(
            roman_text=item["roman_text"],
            poet_name=item["poet"],
            logger=logger,
        )

        # Build the row matching Config.POST_QUEUE_COLS order:
        # STATUS, TYPE, TITLE, URDU, IMG_LINK, POET, POST_URL, ADDED, NOTES
        row_values = [
            "Pending",              # STATUS
            "image",               # TYPE
            item["roman_text"],    # TITLE (Roman Urdu — kept for reference)
            urdu_caption,          # URDU  (converted Urdu script — used as caption)
            item["img_link"],      # IMG_LINK
            item["poet"],          # POET
            "",                    # POST_URL (empty until posted)
            pkt_stamp(),           # ADDED timestamp
            "",                    # NOTES
        ]

        if sheets.append_row(ws, row_values):
            added += 1
            logger.ok(f"Added: {item['poet']} — {item['roman_text'][:40]}")
        else:
            logger.error(f"Failed to append row for: {item['roman_text'][:40]}")

        # Small delay to avoid Sheets API quota exhaustion
        time.sleep(0.5)

    logger.section(
        f"REKHTA MODE DONE — Added:{added}  "
        f"Duplicates skipped:{dup_count}  Total scraped:{len(scraped)}"
    )
    return {"added": added, "skipped_dup": dup_count, "total_scraped": len(scraped)}


# ════════════════════════════════════════════════════════════════════════════════
#  CARD PARSER
#  Extracts image URL, Roman Urdu text, and poet name from one card element.
# ════════════════════════════════════════════════════════════════════════════════

def _parse_card(card, logger: Logger) -> Optional[Dict]:
    """
    Parse one div.shyriImgBox card element.

    Returns dict with keys: img_link, roman_text, poet
    Returns None if any required field is missing.
    """
    try:
        img_link  = _extract_image_url(card)
        roman_text = _extract_roman_text(card)
        poet       = _extract_poet_name(card)

        if not img_link:
            return None
        if not roman_text:
            return None

        return {
            "img_link":   img_link,
            "roman_text": roman_text.strip(),
            "poet":       poet.strip() if poet else "",
        }

    except Exception as e:
        logger.debug(f"Card parse error: {e}")
        return None


def _extract_image_url(card) -> str:
    """
    Extract the best available image URL from a card.

    Priority order:
      1. img[data-src] attribute (direct webp URL from lazy-load)
      2. img[src] attribute
      3. background-image style of the anchor tag (contains _small/_medium size)
         → We upgrade _small to _medium for better quality

    Always prefer the largest available size.
    """
    # Strategy 1: img[data-src] — the actual lazy-loaded URL (best quality)
    try:
        img = card.find_element(By.CSS_SELECTOR, "div.shyriImg img")
        data_src = (img.get_attribute("data-src") or "").strip()
        if data_src and data_src.startswith("http"):
            # Use the _medium.png version if available (better than _small)
            return _upgrade_image_size(data_src)
    except Exception:
        pass

    # Strategy 2: img[src]
    try:
        img = card.find_element(By.CSS_SELECTOR, "div.shyriImg img")
        src = (img.get_attribute("src") or "").strip()
        if src and src.startswith("http"):
            return _upgrade_image_size(src)
    except Exception:
        pass

    # Strategy 3: background-image style on the anchor
    try:
        a = card.find_element(By.CSS_SELECTOR, "a.shyriImgInner")
        style = (a.get_attribute("style") or "").strip()
        # Extract first URL from: url('https://...'), url('https://...')
        m = re.search(r"url\(['\"]?(https?://[^'\")]+)['\"]?\)", style)
        if m:
            return _upgrade_image_size(m.group(1))
    except Exception:
        pass

    return ""


def _upgrade_image_size(url: str) -> str:
    """
    Replace _small with _medium in Rekhta image URLs for higher resolution.
    If already _medium or _large, keep as-is.
    Uses .png extension (better quality than .webp for posting compatibility).
    """
    if not url:
        return ""
    # Prefer PNG over WebP for maximum compatibility
    url = re.sub(r"_medium\.webp$", "_medium.png", url)
    url = re.sub(r"_small\.webp$",  "_medium.png", url)
    url = re.sub(r"_small\.png$",   "_medium.png", url)
    url = re.sub(r"_small\.jpg$",   "_medium.jpg", url)
    return url


def _extract_roman_text(card) -> str:
    """
    Extract the Roman Urdu poetry line(s) from a card.

    Sources (tried in order):
      1. p.shyriImgLine a text — the main shayari line shown below the image
      2. img alt attribute — fallback, often contains the text
      3. data-text attribute on the share div
    """
    # Strategy 1: footer line text (primary)
    try:
        line_elem = card.find_element(By.CSS_SELECTOR, "p.shyriImgLine a")
        text = (line_elem.text or "").strip()
        if text:
            # Remove the fadeImgSherLine span content (it's invisible but in DOM)
            return re.sub(r"\s+", " ", text).strip()
    except Exception:
        pass

    # Strategy 2: data-text attribute on the share social div
    try:
        share_div = card.find_element(By.CSS_SELECTOR, "div.shareSocial")
        text = (share_div.get_attribute("data-text") or "").strip()
        if text:
            return text
    except Exception:
        pass

    # Strategy 3: img alt text
    try:
        img = card.find_element(By.CSS_SELECTOR, "img")
        alt = (img.get_attribute("alt") or "").strip()
        # Alt often has format "text-Poet Name" — extract just the text part
        if "-" in alt:
            return alt.rsplit("-", 1)[0].strip()
        return alt
    except Exception:
        pass

    return ""


def _extract_poet_name(card) -> str:
    """
    Extract the poet name from a card.

    Sources (tried in order):
      1. h4.shyriImgPoetName a text
      2. .ShyriImgInfoPoetName a text (individual card page variant)
      3. img alt attribute — usually ends with "-Poet Name"
    """
    for selector in ("h4.shyriImgPoetName a", ".ShyriImgInfoPoetName a",
                     "h4.shyriImgPoetName", ".ShyriImgInfoPoetName"):
        try:
            elem = card.find_element(By.CSS_SELECTOR, selector)
            name = (elem.text or "").strip()
            if name:
                return name
        except Exception:
            continue

    # Fallback: extract from img alt
    try:
        img = card.find_element(By.CSS_SELECTOR, "img")
        alt = (img.get_attribute("alt") or "").strip()
        if "-" in alt:
            return alt.rsplit("-", 1)[-1].strip()
    except Exception:
        pass

    return ""


def _normalize_img_url(url: str) -> str:
    """
    Normalize an image URL for duplicate comparison.
    Removes size suffixes so _small, _medium, _large all compare as the same image.

    Example:
        /Images/ShayariImages/foo_small.png  →  /images/shayariimages/foo
        /Images/ShayariImages/foo_medium.jpg →  /images/shayariimages/foo
    """
    if not url:
        return ""
    # Lowercase
    u = url.lower().strip()
    # Remove size suffix before extension
    u = re.sub(r"_(small|medium|large)\.(png|jpg|jpeg|webp)$", "", u)
    # Remove extension if still present
    u = re.sub(r"\.(png|jpg|jpeg|webp)$", "", u)
    return u
