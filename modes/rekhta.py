"""
modes/rekhta.py — DD-Msg-Bot V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rekhta Mode: Scrape poetry image cards from rekhta.org/shayari-image
and populate the PostQueue sheet.

What it does:
  1. Opens rekhta.org/shayari-image (infinite scroll page)
  2. Scrolls the page REKHTA_MAX_SCROLLS times to load cards
  3. Parses each card for: image URL, Roman Urdu text, poet name
  4. Writes Urdu caption as a Google Sheets GOOGLETRANSLATE() formula
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
from urllib.parse import urljoin, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import Config
from utils.logger import Logger, pkt_stamp
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
    ws = sheets.get_worksheet(Config.SHEET_POST_QUE, headers=Config.POST_QUE_COLS)
    if not ws:
        logger.error("PostQueue sheet not found")
        return {}

    headers    = [c for c in Config.POST_QUE_COLS]  # use canonical headers
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

    # ── Scrape Rekhta pages via CollectionLoading (no scroll automation) ─────
    # The listing uses an HTML fragment loader:
    #   /CollectionLoading?lang=1&pageType=shayariImage&contentType=&keyword=&pageIndex=N
    # This is easier to replay, and allows resuming safely because we dedupe
    # against what's already in the sheet.
    total_pages = max(1, int(getattr(Config, "REKHTA_MAX_SCROLLS", 6) or 6))
    if max_items and max_items > 0:
        # Ensure we have enough paging budget to fulfill the user's requested count.
        # A page typically contains ~9–12 cards; we use 8 as a conservative lower bound.
        total_pages = max(total_pages, int(max_items / 8) + 5)
    base_url = "https://www.rekhta.org"
    added = 0
    dup_count = 0
    total_scraped = 0
    # Track roman_text seen in THIS run to catch same poem with different image variants
    seen_texts: Set[str] = set()
    no_new_pages = 0
    max_no_new_pages = 2

    for page_index in range(1, total_pages + 1):
        page_url = _rekhta_page_url(page_index)
        logger.info(f"Loading page {page_index}/{total_pages}: {page_url}")
        try:
            driver.get(page_url)
        except TimeoutException as e:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
            logger.warning(f"Page load timeout loading Rekhta pageIndex={page_index}; skipping: {e}")
            continue

        time.sleep(2.0)

        cards = driver.find_elements(By.CSS_SELECTOR, "div.shyriImgBox")
        logger.debug(f"Cards found on pageIndex={page_index}: {len(cards)}")

        if not cards:
            logger.debug(f"No cards found on pageIndex={page_index}; stopping")
            break

        page_new_added = 0
        for card in cards:
            item = _parse_card_elem(card, logger, base_url=base_url)
            if not item:
                continue

            total_scraped += 1
            norm_url  = _normalize_img_url(item["img_link"])
            norm_text = item["roman_text"].strip().lower()[:60]

            if norm_url in existing_img_links:
                dup_count += 1
                continue
            if norm_text and norm_text in seen_texts:
                dup_count += 1
                continue

            # ── Append to sheet (Urdu column uses GOOGLETRANSLATE formula) ──
            logger.info(f"Adding: {item['roman_text'][:50]}...")

            # Column D (URDU) formula: translate Column C (TITLE) for the same row.
            # Using INDIRECT+ROW avoids hardcoding the row number.
            urdu_formula = (
                '=GOOGLETRANSLATE('
                'INDIRECT("C"&ROW())&" - by "&INDIRECT("F"&ROW()),'
                '"en","ur")'
            )

            title = item["roman_text"].strip()

            # Build the row matching Config.POST_QUE_COLS order:
            # STATUS, TYPE, TITLE, URDU, IMG_LINK, POET, POST_URL, ADDED, NOTES
            row_values = [
                "Pending",              # STATUS
                "image",               # TYPE
                title,                  # TITLE (Column C)
                urdu_formula,           # URDU
                item["img_link"],      # IMG_LINK (Column E)
                item["poet"],          # POET (Column F)
                "",                    # POST_URL
                pkt_stamp(),            # ADDED
                "",                    # NOTES
            ]

            if sheets.append_row(ws, row_values):
                added += 1
                page_new_added += 1
                existing_img_links.add(norm_url)
                seen_texts.add(norm_text)
                logger.ok(f"Added: {item['poet']} — {item['roman_text'][:40]}")
            else:
                logger.error(f"Failed to append row for: {item['roman_text'][:40]}")

            # Small delay to avoid Sheets API quota exhaustion
            time.sleep(0.5)

            if max_items and added >= max_items:
                logger.debug(f"Reached max_items={max_items}; stopping")
                break

        if max_items and added >= max_items:
            break

        # Resume behavior (only when max_items is unlimited):
        # stop after a couple consecutive pages with 0 new additions.
        if page_new_added == 0 and page_index > 1:
            no_new_pages += 1
            if not max_items and no_new_pages >= max_no_new_pages:
                logger.info(
                    f"No new items on {no_new_pages} consecutive page(s) "
                    f"(last pageIndex={page_index}); stopping (resume/dedupe)"
                )
                break
        else:
            no_new_pages = 0

    logger.section(
        f"REKHTA MODE DONE — Added:{added}  "
        f"Duplicates skipped:{dup_count}  Total scraped:{total_scraped}"
    )
    return {"added": added, "skipped_dup": dup_count, "total_scraped": total_scraped}


# ════════════════════════════════════════════════════════════════════════════════
#  CARD PARSER
#  Extracts image URL, Roman Urdu text, and poet name from one card element.
# ════════════════════════════════════════════════════════════════════════════════

def _parse_card_elem(card, logger: Logger, base_url: str) -> Optional[Dict]:
    """Parse one div.shyriImgBox card element."""
    try:
        detail_url = _extract_detail_url(card, base_url=base_url)
        roman_text = _extract_roman_text(card)
        poet       = _extract_poet_name(card)

        if not roman_text:
            return None

        # Prefer deterministic large image URL derived from the shayari-image slug.
        img_link = _extract_image_url(card, detail_url=detail_url)
        if not img_link:
            return None

        return {
            "img_link":    img_link,
            "roman_text":  roman_text.strip(),
            "poet":        poet.strip() if poet else "",
            "detail_url":  detail_url or "",
        }
    except Exception as e:
        logger.debug(f"Card parse error: {e}")
        return None


def _extract_image_url(card, detail_url: str = "") -> str:
    """
    Extract the best available image URL from a card.

    Priority order:
      1. img[data-src] attribute (direct webp URL from lazy-load)
      2. img[src] attribute
      3. background-image style of the anchor tag (contains _small/_medium size)
         → We upgrade _small to _medium for better quality

    Always prefer the largest available size.
    """
    # Strategy 0: build large URL from the shayari-image detail URL if available
    large_from_detail = _build_large_image_url(detail_url)
    if large_from_detail:
        return large_from_detail

    # Strategy 1: img[data-src] — the actual lazy-loaded URL
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


def _extract_detail_url(card, base_url: str) -> str:
    """Extract the /shayari-image/... detail page link from a card."""
    try:
        a = card.find_element(By.CSS_SELECTOR, "a.shyriImgInner")
        href = (a.get_attribute("href") or "").strip()
        if not href:
            return ""
        # Selenium sometimes returns relative hrefs
        return urljoin(base_url, href)
    except Exception:
        return ""


def _rekhta_page_url(page_index: int) -> str:
    """Return the URL to load for a given pageIndex of Rekhta shayari-image."""
    if page_index <= 1:
        return Config.REKHTA_URL
    return (
        "https://www.rekhta.org/CollectionLoading"
        f"?lang=1&pageType=shayariImage&contentType=&keyword=&pageIndex={page_index}"
    )


def _build_large_image_url(detail_url: str) -> str:
    """Derive the _large.png image URL from a /shayari-image/... detail URL."""
    if not detail_url:
        return ""
    try:
        p = urlparse(detail_url)
        slug = p.path.strip("/").split("/")[-1]
        if not slug:
            return ""
        # Rekhta uses /images/shayariimages/<slug>_large.(png|jpg)
        return f"https://www.rekhta.org/images/shayariimages/{slug}_large.png"
    except Exception:
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
