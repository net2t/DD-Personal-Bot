#!/bin/bash
# ── DD-Msg-Bot — Commit & Push ──────────────────────────────────────────────
# Run this from your project root folder (where main.py lives)
# Usage: bash commit_and_push.sh

set -e  # stop on any error

echo ""
echo "═══════════════════════════════════════════"
echo "  DD-Msg-Bot — Committing fixes"
echo "═══════════════════════════════════════════"

# 1. Copy the new files into place (run from project root)
echo ""
echo "Step 1: Copying updated files..."
#   Make sure you've already placed:
#     modes/post.py          ← the fixed post.py
#     .github/workflows/bot.yml  ← the new workflow

# 2. Stage changed files
echo "Step 2: Staging files..."
git add modes/post.py
git add .github/workflows/bot.yml

# 3. Show what will be committed
echo ""
echo "Files staged for commit:"
git diff --cached --name-only

# 4. Commit
echo ""
echo "Step 3: Committing..."
git commit -m "fix(post): fix posting mode - 3 root causes resolved

- Fix false rate-limit detection caused by New Relic JS bundle
  embedded in DamaDam pages (stripped <script> blocks before check)
- Fix wrong submit button selector (was reply form btn[name=dec],
  now correctly targets #share_img_btn[name=btn][value=1])
- Fix success detection: recognize /users/<nick>/ and /profile/public/
  as valid redirect targets after successful post
- Increase post cooldown to 180s (3min) based on upload-denied page
- Treat /share/photo/upload-denied/ as real rate limit, leave Pending
- Disable HTML/PNG debug dumps by default (enable with DD_DEBUG=1)
- Caption uses col D (URDU) only, rejects unevaluated formulas

fix(workflow): add bot.yml - 1 post per hour schedule
- Post: every hour at minute 0
- Inbox: every 20 min (minutes 5, 25, 45)
- Rekhta: every 6 hours
- Msg: once daily at 06:00 PKT"

# 5. Push
echo ""
echo "Step 4: Pushing to GitHub..."
git push

echo ""
echo "✅ Done! Check GitHub Actions tab to see the scheduled runs."
echo "   Manual trigger: Actions → DD-Msg-Bot → Run workflow → select mode"
