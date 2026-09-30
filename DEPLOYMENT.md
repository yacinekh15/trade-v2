# Vercel deployment

1. Upload/push this folder as the new version; keep the previous project/archive untouched.
2. Vercel detects `api/index.py` as the Python function and the root `index.html` as the dashboard.
3. Add environment variables in Vercel if Telegram or Upstash is required.
4. Verify `/api/health` after deployment.
5. Open the dashboard and run a single manual scan first.
6. If desired, enable **Auto-scan every 60s**. This is browser-driven; there is no cron or GitHub Action.

The browser scans coins in batches of 40. This keeps each serverless request bounded instead of asking one Vercel invocation to process the entire 242-coin universe.
