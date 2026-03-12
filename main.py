"""
main.py — DD-Msg-Bot V2
━━━━━━━━━━━━━━━━━━━━━━━
Entry point for all bot modes.

Usage:
    python main.py msg            → Message Mode
    python main.py post           → Post Mode
    python main.py rekhta         → Rekhta (Populate) Mode
    python main.py logs           → Show recent MasterLog entries
    python main.py setup          → Create/repair all sheets

Options (can be combined with any mode):
    --max N       Process only N items (default: 0 = unlimited)
    --dry-run     Simulate actions without writing to sheet or posting
    --debug       Verbose debug logging
    --headless    Force headless browser (default from .env)

Examples:
    python main.py msg --max 10
    python main.py post --dry-run
    python main.py rekhta --max 30
    python main.py logs
"""

import sys
import argparse

from config import Config
from utils.logger import Logger
from core.browser import BrowserManager
from core.login import LoginManager
from core.sheets import SheetsManager

# ── Mode modules (real implementations — no circular imports) ──────────────────
import modes.message as message_mode
import modes.post    as post_mode
import modes.rekhta  as rekhta_mode
import modes.logs    as logs_mode
import modes.setup   as setup_mode


# ═══════════════════════════════════════════════════════════════════════════════
#  Argument Parser
# ═══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    """Define all CLI arguments."""
    p = argparse.ArgumentParser(
        prog="main.py",
        description=f"DD-Msg-Bot V{Config.VERSION} — DamaDam automation bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "mode",
        choices=["msg", "post", "rekhta", "logs", "setup"],
        help="Which mode to run",
    )
    p.add_argument(
        "--max", dest="max_items", type=int, default=0,
        metavar="N",
        help="Maximum number of items to process (0 = unlimited)",
    )
    p.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="Simulate actions — no posts sent, no sheet writes",
    )
    p.add_argument(
        "--debug", dest="debug", action="store_true",
        help="Enable verbose debug logging",
    )
    p.add_argument(
        "--headless", dest="headless", action="store_true", default=None,
        help="Force headless browser mode",
    )
    return p


# ═══════════════════════════════════════════════════════════════════════════════
#  Mode runners
# ═══════════════════════════════════════════════════════════════════════════════

def _run_needs_browser(mode: str, args) -> None:
    """
    Shared runner for modes that need a browser (msg, post, rekhta).

    Steps:
      1. Validate config
      2. Start browser
      3. Login (skipped for rekhta — Rekhta.org doesn't need login)
      4. Connect to Sheets
      5. Dispatch to mode
      6. Close browser
    """
    logger = Logger(mode)
    logger.section(f"DD-Msg-Bot V{Config.VERSION} — {mode.upper()} MODE")

    # -- Validate config -------------------------------------------------------
    Config.validate()

    # -- Start browser ---------------------------------------------------------
    bm     = BrowserManager(logger)
    driver = bm.start()
    if not driver:
        logger.error("Browser failed to start — aborting")
        sys.exit(1)

    try:
        # -- Login (not needed for Rekhta) ------------------------------------
        if mode != "rekhta":
            lm = LoginManager(driver, logger)
            if not lm.login():
                logger.error("Login failed — aborting")
                sys.exit(1)

        # -- Connect to Google Sheets -----------------------------------------
        sheets = SheetsManager(logger)
        if not sheets.connect():
            logger.error("Google Sheets connection failed — aborting")
            sys.exit(1)

        # -- Dispatch ----------------------------------------------------------
        max_n = args.max_items  # 0 = unlimited

        if mode == "msg":
            message_mode.run(driver, sheets, logger, max_targets=max_n)

        elif mode == "post":
            post_mode.run(driver, sheets, logger, max_posts=max_n)

        elif mode == "rekhta":
            rekhta_mode.run(driver, sheets, logger, max_items=max_n)

    finally:
        bm.close()


def _run_sheets_only(mode: str, args) -> None:
    """
    Shared runner for modes that only need Google Sheets (logs, setup).
    No browser started.
    """
    logger = Logger(mode)
    Config.validate()

    sheets = SheetsManager(logger)
    if not sheets.connect():
        logger.error("Google Sheets connection failed")
        sys.exit(1)

    if mode == "logs":
        logs_mode.run(sheets, logger, last_n=30)

    elif mode == "setup":
        setup_mode.run(sheets, logger)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = _build_parser()
    args   = parser.parse_args()

    # -- Apply CLI overrides to Config ----------------------------------------
    # These override whatever is in .env
    if args.dry_run:
        Config.DRY_RUN = True
    if args.debug:
        Config.DEBUG = True
    if args.headless:
        Config.HEADLESS = True

    mode = args.mode

    if mode in ("msg", "post", "rekhta"):
        _run_needs_browser(mode, args)
    else:
        _run_sheets_only(mode, args)


if __name__ == "__main__":
    main()
