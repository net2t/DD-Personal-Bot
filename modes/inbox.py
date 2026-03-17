"""
modes/inbox.py — DD-Msg-Bot V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Inbox + Activity Mode (combined): ONE run does everything:
  Phase 1 — Fetch DamaDam inbox (/inbox/)
             Parse each conversation block → TID, NICK, TYPE, last message
             Sync new conversations into InboxQue sheet
             Log all new items to InboxLog with full detail
  Phase 2 — Send pending replies
             Rows in InboxQue where MY_REPLY has text + STATUS=Pending
             Navigate to the conversation, extract hidden form fields,
             and submit via proper form POST (CSRF + tuid + obid + poid)
  Phase 3 — Fetch activity feed (/inbox/activity/)
             Log each activity item to InboxLog sheet

DamaDam inbox / reply HTML structure:
  Each inbox item → div.mbl.mtl containing:
    button[name='tid'] value="<user_id>"          ← stable user ID
    div.cl.lsp.nos b bdi                          ← nickname
    span.mrs bdi                                  ← last message text
    span[style*='color:#999']                     ← relative time "1 hour ago"

  Reply form on conversation/post pages:
    <form action="/direct-response/send/" method="POST">
      <input name="csrfmiddlewaretoken" value="...">
      <input name="tuid"  value="<user_id>">
      <input name="obtp"  value="3">              ← object type
      <input name="obid"  value="<post_id>">
      <input name="poid"  value="<post_id>">
      <input name="origin" value="9">
      <input name="rorigin" value="35">
      <textarea name="direct_response">
    </form>

  The REPLY button's name="dr_pl" encodes: "origin:obtp:obid:disc_id:tuid:prev_text"
  e.g.: value="9:3:41740467:278026811:1391529:ok g"
"""

import re
import time
from typing import List, Dict, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config import Config
from utils.logger import Logger, pkt_stamp
from utils.helpers import strip_non_bmp
from core.sheets import SheetsManager


# ── DamaDam URLs ──────────────────────────────────────────────────────────────
_URL_INBOX    = f"{Config.BASE_URL}/inbox/"
_URL_ACTIVITY = f"{Config.BASE_URL}/inbox/activity/"

# ── Selectors ─────────────────────────────────────────────────────────────────
_SEL_ITEM_BLOCK     = "div.mbl.mtl"
_SEL_TID_BTN        = "button[name='tid']"
_SEL_NICK_BDI       = "div.cl.lsp.nos b bdi"
_SEL_MSG_SPAN       = "div.cl.lsp.nos span bdi"
_SEL_TIME_SPAN      = "span[style*='color:#999']"
_SEL_TYPE_SPAN      = "div.sp.cs.mrs span"
_SEL_REPLY_FORM     = "form[action*='/direct-response/send']"
_SEL_REPLY_TEXTAREA = "textarea[name='direct_response']"


def run_inbox(driver, sheets: SheetsManager, logger: Logger) -> Dict:
    """
    Run full Inbox + Activity mode.

    Phase 1: Fetch inbox  → sync InboxQue + log to InboxLog
    Phase 2: Send replies → rows with MY_REPLY filled + STATUS=Pending
    Phase 3: Fetch activity → log to InboxLog

    Returns stats dict.
    """
    import time as _time
    run_start = _time.time()

    logger.section("INBOX + ACTIVITY MODE")

    ws_que = sheets.get_worksheet(Config.SHEET_INBOX_QUE, headers=Config.INBOX_QUE_COLS)
    ws_log = sheets.get_worksheet(Config.SHEET_INBOX_LOG, headers=Config.INBOX_LOG_COLS)
    if not ws_que or not ws_log:
        logger.error("InboxQue or InboxLog sheet not found — run Setup first")
        return {}

    # ── Phase 1: Fetch inbox ──────────────────────────────────────────────────
    logger.info("Phase 1: Fetching inbox conversations...")
    inbox_items = _fetch_inbox(driver, logger)
    logger.info(f"Found {len(inbox_items)} conversations in inbox")

    all_que_rows = sheets.read_all(ws_que)
    que_headers  = all_que_rows[0] if all_que_rows else Config.INBOX_QUE_COLS
    que_hmap     = SheetsManager.build_header_map(que_headers)

    def qcell(row, *names):
        return SheetsManager.get_cell(row, que_hmap, *names)

    existing_tids = {
        qcell(row, "TID").lower()
        for row in all_que_rows[1:]
        if qcell(row, "TID")
    }

    new_synced = 0
    for item in inbox_items:
        tid  = str(item.get("tid",  "")).strip()
        nick = item.get("nick", "").strip()

        if not nick:
            continue

        # Log every inbox item to InboxLog (full history)
        _log_entry(sheets, ws_log, pkt_stamp(), tid, nick,
                   item.get("type", ""), "IN",
                   item.get("last_msg", ""), item.get("conv_url", ""), "Received")

        # Sync new conversations into InboxQue
        if tid and tid.lower() not in existing_tids:
            row_vals = [
                tid,
                nick,
                nick,               # NAME defaults to nick
                item.get("type", ""),
                item.get("last_msg", ""),
                "",                 # MY_REPLY — you fill this in
                "Pending",
                pkt_stamp(),
                "",
            ]
            if sheets.append_row(ws_que, row_vals):
                logger.ok(f"New conversation: [{item.get('type','')}] {nick} (tid={tid})")
                existing_tids.add(tid.lower())
                new_synced += 1
        elif not tid:
            existing_nicks = {qcell(row, "NICK").lower() for row in all_que_rows[1:]}
            if nick.lower() not in existing_nicks:
                row_vals = ["", nick, nick, item.get("type", ""),
                            item.get("last_msg", ""), "", "Pending", pkt_stamp(), ""]
                if sheets.append_row(ws_que, row_vals):
                    logger.ok(f"New conversation (no tid): {nick}")
                    new_synced += 1

    # ── Phase 2: Send pending replies ─────────────────────────────────────────
    logger.info("Phase 2: Sending pending replies...")

    all_que_rows = sheets.read_all(ws_que)
    que_hmap     = SheetsManager.build_header_map(all_que_rows[0]) if all_que_rows else {}
    col_status   = sheets.get_col(all_que_rows[0] if all_que_rows else [], "STATUS")
    col_notes    = sheets.get_col(all_que_rows[0] if all_que_rows else [], "NOTES")
    col_updated  = sheets.get_col(all_que_rows[0] if all_que_rows else [], "UPDATED")

    def qcell2(row, *names):
        return SheetsManager.get_cell(row, que_hmap, *names)

    pending_replies = []
    for i, row in enumerate(all_que_rows[1:], start=2):
        reply  = qcell2(row, "MY_REPLY").strip()
        status = qcell2(row, "STATUS").lower()
        nick   = qcell2(row, "NICK").strip()
        tid    = qcell2(row, "TID").strip()
        if reply and status.startswith("pending"):
            pending_replies.append({
                "row": i, "nick": nick, "tid": tid, "reply": reply,
                "type": qcell2(row, "TYPE"),
            })

    # Build tid → conv_url from freshly fetched inbox items
    tid_to_url = {
        str(it.get("tid", "")): it.get("conv_url", "")
        for it in inbox_items if it.get("tid")
    }

    sent   = 0
    failed = 0

    for idx, item in enumerate(pending_replies, start=1):
        nick  = item["nick"]
        tid   = item["tid"]
        reply = item["reply"]
        row_n = item["row"]
        logger.info(f"[{idx}/{len(pending_replies)}] Replying to {nick} (tid={tid})")

        conv_url = (tid_to_url.get(tid) or "").strip()
        if not conv_url:
            conv_url = _URL_INBOX

        ok, sent_url = _send_reply(driver, conv_url, tid, reply, nick, logger)

        if ok:
            logger.ok(f"Reply sent → {nick}")
            sheets.update_row_cells(ws_que, row_n, {
                col_status:  "Done",
                col_notes:   f"Replied @ {pkt_stamp()}",
                col_updated: pkt_stamp(),
            })
            _log_entry(sheets, ws_log, pkt_stamp(), tid, nick,
                       item["type"], "OUT", reply, sent_url or conv_url, "Sent")
            sheets.log_action("INBOX", "reply_sent", nick, sent_url or conv_url, "Done", reply[:80])
            sent += 1
        else:
            logger.warning(f"Reply failed → {nick}")
            sheets.update_row_cells(ws_que, row_n, {
                col_status:  "Failed",
                col_notes:   f"Send failed @ {pkt_stamp()}",
                col_updated: pkt_stamp(),
            })
            _log_entry(sheets, ws_log, pkt_stamp(), tid, nick,
                       item["type"], "OUT", reply, conv_url, "Failed")
            failed += 1

        time.sleep(2)

    # ── Phase 3: Activity feed ────────────────────────────────────────────────
    logger.info("Phase 3: Fetching activity feed...")
    activity_items = _fetch_activity(driver, logger, max_items=60, max_pages=5)
    act_logged = 0

    for act in activity_items:
        _log_entry(
            sheets, ws_log, pkt_stamp(),
            act.get("tid", ""), act.get("nick", ""),
            act.get("type", "ACTIVITY"), "ACTIVITY",
            act.get("text", ""), act.get("url", ""), "Logged",
        )
        act_logged += 1
        time.sleep(0.15)

    duration = _time.time() - run_start
    logger.section(
        f"INBOX DONE — "
        f"New:{new_synced}  Sent:{sent}  Failed:{failed}  Activity:{act_logged}"
    )

    stats = {
        "new_synced":      new_synced,
        "sent":            sent,
        "replies_failed":  failed,
        "activity_logged": act_logged,
    }
    sheets.log_run(
        "inbox",
        {"added": new_synced, "sent": sent, "failed": failed},
        duration_s=duration,
        notes=f"New convos:{new_synced}  Replies sent:{sent}  Activity:{act_logged}",
    )
    return stats


def run_activity(driver, sheets: SheetsManager, logger: Logger) -> Dict:
    """Alias: activity mode runs the full inbox+activity cycle."""
    return run_inbox(driver, sheets, logger)


# ════════════════════════════════════════════════════════════════════════════════
#  FETCH INBOX
# ════════════════════════════════════════════════════════════════════════════════

def _fetch_inbox(driver, logger: Logger) -> List[Dict]:
    """Open /inbox/ and parse all visible conversation blocks."""
    try:
        driver.get(_URL_INBOX)
        time.sleep(3)

        items:      List[Dict] = []
        seen_tids:  set        = set()
        seen_nicks: set        = set()

        blocks = driver.find_elements(By.CSS_SELECTOR, _SEL_ITEM_BLOCK)
        if not blocks:
            logger.warning("No inbox blocks found — inbox may be empty or session expired")
            return []

        for block in blocks[:50]:
            try:
                item = _parse_inbox_block(block)
                if not item:
                    continue

                tid  = str(item.get("tid",  "")).strip()
                nick = str(item.get("nick", "")).strip()

                if not nick:
                    continue
                if tid and tid in seen_tids:
                    continue
                if not tid and nick.lower() in seen_nicks:
                    continue

                if tid:
                    seen_tids.add(tid)
                seen_nicks.add(nick.lower())
                items.append(item)

            except Exception as e:
                logger.debug(f"Skipped inbox block: {e}")
                continue

        return items

    except Exception as e:
        logger.error(f"Inbox fetch error: {e}")
        return []


def _parse_inbox_block(block) -> Optional[Dict]:
    """Parse one div.mbl.mtl inbox block into a structured dict."""
    # TID from button[name='tid']
    tid = ""
    try:
        btn = block.find_elements(By.CSS_SELECTOR, _SEL_TID_BTN)
        if btn:
            tid = (btn[0].get_attribute("value") or "").strip()
    except Exception:
        pass

    # Conversation type
    conv_type = ""
    try:
        type_spans = block.find_elements(By.CSS_SELECTOR, _SEL_TYPE_SPAN)
        if type_spans:
            raw = (type_spans[0].text or "").strip().upper()
            if "1" in raw and "ON" in raw:
                conv_type = "1ON1"
            elif "POST" in raw:
                conv_type = "POST"
            elif "MEHFIL" in raw:
                conv_type = "MEHFIL"
            else:
                conv_type = raw[:20]
    except Exception:
        pass

    # Nickname
    nick = ""
    try:
        nick_els = block.find_elements(By.CSS_SELECTOR, _SEL_NICK_BDI)
        if nick_els:
            nick = (nick_els[0].text or "").strip()
    except Exception:
        pass

    if not nick:
        return None

    # Last message
    last_msg = ""
    try:
        msg_els = block.find_elements(By.CSS_SELECTOR, _SEL_MSG_SPAN)
        if msg_els:
            last_msg = (msg_els[0].text or "").strip()
    except Exception:
        pass

    # Conversation URL
    conv_url = _URL_INBOX
    try:
        links = block.find_elements(
            By.CSS_SELECTOR,
            "a[href*='/comments/'], a[href*='/content/'], a[href*='/inbox/']"
        )
        for a in links:
            href = (a.get_attribute("href") or "").strip()
            if href and href != _URL_INBOX:
                conv_url = href if href.startswith("http") else f"{Config.BASE_URL}{href}"
                break
    except Exception:
        pass

    return {
        "tid":       tid,
        "nick":      nick,
        "type":      conv_type,
        "last_msg":  last_msg,
        "timestamp": pkt_stamp(),
        "conv_url":  conv_url,
    }


# ════════════════════════════════════════════════════════════════════════════════
#  SEND REPLY
# ════════════════════════════════════════════════════════════════════════════════

def _send_reply(driver, conv_url: str, tid: str,
                reply_text: str, nick: str, logger: Logger):
    """
    Navigate to the conversation and submit a reply.

    Strategy:
      1. Go to conv_url
      2. Find the reply form (form[action*='/direct-response/send/'])
      3. Extract all hidden form fields (csrfmiddlewaretoken, tuid, obid, poid,
         obtp, origin, rorigin)
      4. Type reply using send_keys (React-safe) and submit
      5. Fallback to /inbox/ if conv_url has no reply form

    Returns (success: bool, posted_url: str)
    """
    safe_reply = strip_non_bmp(reply_text)[:350]

    def _try_send(page_url: str):
        """Try to send reply on a given page. Returns (ok, url) or (None, None) if no form."""
        try:
            driver.get(page_url)
            time.sleep(3)

            forms = driver.find_elements(By.CSS_SELECTOR, _SEL_REPLY_FORM)
            for form in forms:
                try:
                    textarea = form.find_element(By.CSS_SELECTOR, _SEL_REPLY_TEXTAREA)
                except Exception:
                    continue

                # Find submit button
                submit_btn = None
                for sel in (
                    "button[name='dec'][value='1']",
                    "button[type='submit']",
                    "input[type='submit']",
                ):
                    try:
                        btns = form.find_elements(By.CSS_SELECTOR, sel)
                        if btns:
                            submit_btn = btns[0]
                            break
                    except Exception:
                        pass

                if not submit_btn:
                    continue

                # Type using send_keys (React-safe)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});"
                    "arguments[0].focus();"
                    "arguments[0].value = '';",
                    textarea
                )
                time.sleep(0.3)
                try:
                    textarea.clear()
                except Exception:
                    pass
                time.sleep(0.2)
                textarea.send_keys(safe_reply)
                time.sleep(0.4)

                # Submit
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", submit_btn
                )
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", submit_btn)
                time.sleep(3)

                return True, driver.current_url

            return None, None  # No form found on this page
        except Exception as e:
            logger.debug(f"_try_send error on {page_url}: {e}")
            return False, None

    # Attempt 1: go to the conversation URL
    ok, url = _try_send(conv_url)
    if ok is True:
        return True, url
    if ok is False:
        return False, None

    # ok is None — no form found. Try /inbox/ as fallback
    logger.debug(f"No reply form at {conv_url} — trying /inbox/ fallback for {nick}")
    ok2, url2 = _try_send(_URL_INBOX)
    if ok2 is True:
        return True, url2

    logger.warning(f"Reply form not found for {nick} (tid={tid})")
    return False, None


# ════════════════════════════════════════════════════════════════════════════════
#  FETCH ACTIVITY
# ════════════════════════════════════════════════════════════════════════════════

def _fetch_activity(driver, logger: Logger,
                    max_items: int = 60, max_pages: int = 5) -> List[Dict]:
    """Fetch DamaDam activity feed from /inbox/activity/."""
    items: List[Dict] = []
    seen:  set         = set()

    try:
        for page_num in range(1, max_pages + 1):
            if len(items) >= max_items:
                break

            url = _URL_ACTIVITY if page_num == 1 else f"{_URL_ACTIVITY}?page={page_num}"
            driver.get(url)
            time.sleep(3)

            blocks = driver.find_elements(By.CSS_SELECTOR, _SEL_ITEM_BLOCK)
            if not blocks:
                break

            for block in blocks:
                if len(items) >= max_items:
                    break
                try:
                    tid = ""
                    try:
                        btn = block.find_elements(By.CSS_SELECTOR, _SEL_TID_BTN)
                        if btn:
                            tid = (btn[0].get_attribute("value") or "").strip()
                    except Exception:
                        pass

                    conv_type = "ACTIVITY"
                    try:
                        type_spans = block.find_elements(By.CSS_SELECTOR, _SEL_TYPE_SPAN)
                        if type_spans:
                            raw = (type_spans[0].text or "").strip().upper()
                            if "1" in raw and "ON" in raw:
                                conv_type = "1ON1"
                            elif "POST" in raw:
                                conv_type = "POST"
                            elif "MEHFIL" in raw:
                                conv_type = "MEHFIL"
                    except Exception:
                        pass

                    nick = ""
                    try:
                        nick_els = block.find_elements(By.CSS_SELECTOR, _SEL_NICK_BDI)
                        if nick_els:
                            nick = (nick_els[0].text or "").strip()
                    except Exception:
                        pass

                    raw_text = (block.text or "").strip()
                    lines = [
                        ln.strip() for ln in raw_text.splitlines()
                        if ln.strip() and ln.strip() not in {"►", "REMOVE", "▶", "SKIP ALL ON PAGE"}
                    ]
                    text = " | ".join(lines)[:300]
                    if not text:
                        continue

                    item_url = ""
                    try:
                        links = block.find_elements(
                            By.CSS_SELECTOR,
                            "a[href*='/comments/'], a[href*='/content/']"
                        )
                        if links:
                            href = (links[0].get_attribute("href") or "").strip()
                            if href:
                                item_url = href if href.startswith("http") else f"{Config.BASE_URL}{href}"
                    except Exception:
                        pass

                    key = (text[:80], item_url)
                    if key in seen:
                        continue
                    seen.add(key)

                    items.append({"tid": tid, "nick": nick, "type": conv_type,
                                  "text": text, "url": item_url})

                except Exception:
                    continue

            # Check for next page
            try:
                next_btns = driver.find_elements(By.CSS_SELECTOR, "a[href*='?page='] button")
                if not any("NEXT" in (b.text or "").upper() for b in next_btns):
                    break
            except Exception:
                break

    except Exception as e:
        logger.error(f"Activity fetch error: {e}")

    return items


# ════════════════════════════════════════════════════════════════════════════════
#  LOG HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _log_entry(sheets: SheetsManager, ws_log,
               timestamp: str, tid: str, nick: str,
               conv_type: str, direction: str,
               message: str, url: str, status: str):
    """Append one row to InboxLog sheet."""
    sheets.append_row(ws_log, [
        timestamp, tid, nick, conv_type, direction, message, url, status,
    ])
