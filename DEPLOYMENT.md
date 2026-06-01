# Deployment Guide — Secure AI Coding Assistant v1.0

## Quick Start Checklist

### Step 1: GitHub Repository
```bash
# Create new GitHub repo at https://github.com/new
# Name: secure-ai-coding-assistant
# Make it PUBLIC
# Skip "Initialize with README" (we already have one)

# Then push your code:
cd C:\s
git remote add origin https://github.com/YOUR_USERNAME/secure-ai-coding-assistant.git
git branch -M main
git push -u origin main
```

After pushing, verify at: https://github.com/YOUR_USERNAME/secure-ai-coding-assistant

---

### Step 2: Dashboard (Instant Free Hosting)
1. Go to **https://netlify.com/drop**
2. Drag `C:\s\output\dashboard.html` onto the page
3. Wait 5 seconds for deployment
4. You'll get a live URL like: `https://xyz123.netlify.app`
5. Share this URL — it's your public dashboard!

**Note:** The dashboard is purely frontend. When users click "RUN PIPELINE", it will need to hit your API server (Step 3).

---

### Step 3: Flask API Deployment (Free Tier)

#### Option A: Render (Recommended)
1. Go to **https://render.com**
2. Sign up with GitHub
3. Click "New" → "Web Service"
4. Connect your GitHub repo
5. Configure:
   - **Name:** secure-ai-coder
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
6. Add Environment Variables:
   ```
   ANTHROPIC_API_KEY = sk-ant-...
   GROQ_API_KEY = gsk_...
   PORT = 5000
   ```
7. Deploy (takes 2-3 minutes)
8. You'll get a URL like: `https://secure-ai-coder.onrender.com`

#### Option B: Railway.app
1. Go to **https://railway.app**
2. Create new project → Deploy from GitHub
3. Select your repo
4. Add same env vars as above
5. Railway auto-deploys on every git push

#### Option C: Local Testing Before Deployment
```bash
# Install Flask
pip install flask

# Run locally
cd C:\s
python app.py

# Visit http://localhost:5000
# Dashboard loads at http://localhost:5000/
# API at http://localhost:5000/api/health
```

---

### Step 4: Connect Dashboard to API

Edit the dashboard HTML to use your live API:

**Current (local testing):**
```javascript
// Dashboard makes requests to same domain
fetch('http://localhost:5000/api/run', { ... })
```

**After deployment, update to live API:**
```javascript
// Edit output/dashboard.html after deploying API
const API_BASE = 'https://secure-ai-coder.onrender.com';
fetch(API_BASE + '/api/run', { ... })
```

---

## Verification Checklist

After deployment, verify each step:

### 1. GitHub Repo
```bash
git remote -v
# Should show your GitHub repo URL

git log
# Should show your first commit
```

### 2. Dashboard Accessible
```bash
curl -I https://xyz123.netlify.app
# Should return 200 OK
```

### 3. API Health Check
```bash
curl https://secure-ai-coder.onrender.com/api/health
# Should return JSON with "status": "online"
```

### 4. Full Pipeline Test
```bash
curl -X POST https://secure-ai-coder.onrender.com/api/run \
  -H "Content-Type: application/json" \
  -d '{"request":"Build JWT validator","language":"python"}'
# Should return results with "status": "success"
```

---

## Environment Variables for Deployment

| Variable | Value | Required |
|----------|-------|----------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Yes |
| `GROQ_API_KEY` | Your Groq API key | No (fallback) |
| `PORT` | 5000 | No (auto-set by render) |
| `DEBUG` | false | No |
| `TEMPERATURE` | 0.1 | No |
| `MAX_TOKENS` | 4096 | No |

**To get API keys:**
- Anthropic: https://console.anthropic.com/ (click "Get API key")
- Groq: https://groq.com (sign up, then get key)

---

## Troubleshooting

### "API key invalid" error
- Check your key is pasted correctly (no extra spaces)
- Verify it's not expired (Anthropic/Groq dashboard)
- Test with: `curl https://api.anthropic.com/v1/messages` with your key

### "Port 5000 already in use" locally
```bash
# Kill existing process
lsof -i :5000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use different port
PORT=8000 python app.py
```

### Dashboard shows "waiting for execution" after clicking Run
- Check browser console (F12) for errors
- Verify API endpoint is correct
- Check API is online: `curl https://your-api.onrender.com/api/health`

### Build fails on Render/Railway
- Check Python version (must be 3.11+)
- Verify all dependencies in requirements.txt
- Check logs: `render logs` or Railway dashboard

---

## Scaling for Production

After v1.0 validation, consider:

1. **Database** — Store sessions (PostgreSQL)
   ```
   Render: Add PostgreSQL addon → get DATABASE_URL
   ```

2. **Caching** — Redis for repeated requests
   ```
   Render: Add Redis addon → get REDIS_URL
   ```

3. **Monitoring** — Sentry for error tracking
   ```python
   import sentry_sdk
   sentry_sdk.init("your-sentry-dsn")
   ```

4. **CDN** — Cloudflare for dashboard (fast edge delivery)

5. **Load Balancing** — Scale API horizontally
   ```
   Render: Select Pro/Business plan
   ```

---

## Next Steps

1. ✓ Create GitHub repo
2. ✓ Push code
3. ✓ Deploy dashboard to Netlify
4. ✓ Deploy API to Render
5. ✓ Test pipeline end-to-end
6. Share URL with beta users!

---

**Questions?** Check:
- Render docs: https://render.com/docs
- Netlify docs: https://docs.netlify.com
- Flask docs: https://flask.palletsprojects.com
- CrewAI docs: https://docs.crewai.com

**API Reference:**
- `GET /` — Serve dashboard
- `GET /api/health` — Health check
- `GET /api/models` — Available models
- `POST /api/run` — Execute pipeline

---

*Last updated: June 2026*
