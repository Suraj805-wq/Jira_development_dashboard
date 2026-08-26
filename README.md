# ⚡ FleetLeads

A **fleet-management & telematics contact finder** (the category **Uffizio**
sits in). Browse 115+ fleet organisations across 36 countries — or **search
ANY company worldwide** and scrape it live. For each organisation you get:

- **Decision makers** — CEO, CFO, COO, CRO, CTO, VPs, regional Managing
  Directors and other executives, from **two sources**:
  1. the company's own leadership/team and news pages (real names + real
     titles, with a link to the exact source page);
  2. when the site publishes nothing, **open-source lookup** — Wikipedia
     infoboxes (founders / key people) + open-web search results. This finds
     executives for the majority of organisations that don't list leadership
     on their site.
  **Note:** linkedin.com member pages are never scraped (against LinkedIn's
  ToS and blocked); names come from Wikipedia and search-engine results only.
- **Decision-maker contact info** — for each executive:
  - **published email/phone** when the company prints it next to the person;
  - **derived email** built from the company's naming convention
    (e.g. `first.last@company.com`), labelled **"derived · unverified"**;
  - **LinkedIn link** — the person's real profile when the site links to it,
    otherwise a ready-made LinkedIn people-search for that name.
- **Email verification at save-time** — every email is checked **before it is
  saved** (MX + SMTP handshake + catch-all + disposable-domain detection,
  dnspython + smtplib). Only correct, working addresses are kept:
  - **✓ verified** — the mail server confirmed the mailbox exists
  - **◌ catch-all** — the domain accepts any address (can't confirm individually)
  - rejected / invalid addresses are **dropped, not saved**
- **Automatic combination retry** — if a guessed executive email is rejected,
  FleetLeads tries other name conventions (`first.last`, `f.last`, `flast`,
  `first_last`, …) until one verifies; the mail domain used is the one the
  majority of the organisation's published emails share.
- **Proxy / VPN-style egress** — scraping routes through any HTTP/SOCKS proxy
  (single or rotating pool) via the settings or `FLEETLEADS_PROXY` env var, with
  user-agent rotation and retries.
- **Company contacts** — published emails (sales/support/info), phone numbers
  and social profiles.

**100% open-source. No paid services. Nothing invented** — FleetLeads only
reports what a company publicly publishes; if it finds nothing, it says so.

---

## Continuous background worker (the app never stops)

FleetLeads runs a **polite, never-ending worker** (auto-starts with the app)
that cycles through four jobs forever:

| Job | What it does |
|---|---|
| 🔭 **Discover** | finds new fleet/telematics organisations in the countries with the *fewest* companies, verifies each candidate's homepage, and adds real ones |
| 🕷 **Scrape** | scrapes organisations that haven't been scraped yet |
| 👤 **People** | re-scrapes organisations that have **0 decision makers** (now with sitemap discovery to find team/leadership pages) |
| ✓ **Verify** | re-verifies emails that are unverified/rejected so every stored address ends up correct |

The worker status pill in the top bar shows what it's doing live (click it to
pause/resume). Progress counters survive restarts.

### Data is never lost on re-scrape

Re-scraping **merges** results (upsert by natural key) instead of deleting and
replacing. A transient rate-limit or site outage during a re-scrape can no
longer wipe previously-good data.

---

## Honest note on volume (1000–2000 per country)

There is no free way to produce 1,000–2,000 *verified decision makers per
country*: most countries simply do not have that many fleet/telematics
vendors, and most vendors do not publish their executives' emails. The global
fleet-telematics vendor market is a few thousand companies concentrated in the
US, EU, India, China and the GCC. FleetLeads maximises what is legally and
freely obtainable — real companies, real leadership names, verified/catch-all
emails — and reports honest totals rather than padding numbers with guesses.
Reaching 1,000+ verified contacts per country requires licensed data
(Apollo/ZoomInfo-style), which is exactly what those paid tools sell.

---

## Country targeting ("gather all organisations of a country")

Type a country (e.g. *Spain*, *Poland*, *UAE*) in the **🌍 Gather country** box.
FleetLeads then:

1. **Searches** for fleet/telematics organisations in that country using free
   web search (Bing → DuckDuckGo) + **Wikidata** (structured, key-free).
2. **Verifies** every candidate — fetches its homepage and confirms it is a
   genuine fleet/telematics organisation (and filters out dictionaries, shops,
   finance sites, "what is telematics" SEO pages, etc.).
3. **Adds** new organisations to the directory (deduping against what's there)
   and **scrapes** each one for decision makers, emails and phones.

### Honest note on search-based discovery

Free web-search engines (Bing, DuckDuckGo) aggressively rate-limit requests
coming from cloud/server IPs — they work for a few fresh queries, then start
serving cached or generic results. FleetLeads handles this gracefully: it
detects degraded responses and stops early rather than adding junk, and it
always falls back to the curated directory + Wikidata. For maximum coverage,
the bundled directory (140+ real, verified organisations across 40 countries)
is the reliable base, and the **🔍 Search & scrape** box can add any specific
company on demand.

---

## How it works

1. **Company directory** — 87 real fleet / telematics / GPS-tracking
   organisations across 24 countries (deep coverage for India, the US, the UK,
   the EU, the GCC, South Africa and Brazil).
2. **Open-source web scraper** (`httpx` + `beautifulsoup4` + `lxml`) visits each
   company's own website and extracts **real published data**:
   - **Decision makers** from:
     - leadership / team / management pages ("Name Title" cards, e.g.
       *"Sanjit Biswas CEO & Co-Founder"*)
     - structured data (JSON-LD / microdata `Person`) — e.g. ORBCOMM's
       executive team
     - news / press pages ("…said John Smith, Chief Executive Officer of X")
   - **Email addresses** (`mailto:` links + page text, TLD-validated)
   - **Phone numbers** (`tel:` links + explicit international/US formats)
   - **Social profiles** (LinkedIn company page, X/Twitter, Facebook,
     Instagram, YouTube)
3. **Verifiable by design** — every item records its `source_url`, so you can
   click through and see exactly where it came from.
4. **Search, filter, export** — filter by country/category, search by
   name/domain/city, bulk-scrape, and export everything to CSV.

---

## Architecture

```
fleet-leads/
├── backend/                     # Python / FastAPI
│   ├── app/
│   │   ├── main.py              # app entrypoint (serves API + built frontend)
│   │   ├── database.py          # SQLite (stdlib, no ORM) + migrations
│   │   ├── seed_data.py         # curated directory of real fleet companies
│   │   ├── enrichment/
│   │   │   ├── scraper.py       # open-source website scraper (the data source)
│   │   │   └── manager.py       # orchestration + caching
│   │   └── routers/             # companies, enrich, settings, export
│   ├── data/fleetleads.db       # SQLite database (auto-created)
│   └── requirements.txt
└── frontend/                    # React + Vite
    ├── src/App.jsx              # dashboard (filters, cards, stats)
    ├── src/components/          # company drawer + scraper options
    └── src/styles.css           # dark dashboard theme
```

### Dependencies (all open-source)

| Package | License | Used for |
|---|---|---|
| fastapi, uvicorn | MIT / BSD | API server |
| httpx (+ socksio) | BSD / MIT | HTTP client + SOCKS proxy support |
| pydantic | MIT | validation |
| beautifulsoup4 | MIT | HTML parsing |
| lxml | BSD | fast HTML parsing |
| dnspython | ISC | MX lookups for email verification |
| smtplib | stdlib (PSF) | SMTP handshake verification |
| react, vite | MIT | frontend |
| sqlite3 | public domain | storage |

---

## Run it

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# frontend (dev, proxies /api → :8000)
cd frontend
npm install
npm run dev

# production (single server: build frontend, serve on :8000)
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Interactive API docs: **http://localhost:8000/docs**

---

## Scraper behaviour & settings

The scraper is **polite by default** and configurable via **⚙ Scraper options**:

| Setting | Default | Meaning |
|---|---|---|
| Verify emails before saving | on | MX + SMTP + catch-all check; keep only working addresses |
| Derive & verify executive emails | on | try name combinations until one verifies |
| Max email combinations/person | 11 | how many name patterns to try |
| SMTP timeout | 8 s | per-mailbox handshake timeout |
| Proxy URL | — | `http://…` / `socks5://…` / `pool:…` for rotating proxies |
| Respect robots.txt | on | skips paths a site disallows for bots |
| Delay between requests | 1.0 s | pause between page fetches |
| Max pages per company | 10 | homepage + leadership/contact/news pages |

If a site is bot-protected or publishes nothing public, FleetLeads records an
honest failure rather than guessing.

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | `/api/health` | health check |
| GET  | `/api/stats` | dashboard counters (companies, decision makers, emails, phones, verified) |
| GET  | `/api/companies?country=&category=&q=&page=&page_size=` | directory + facets |
| POST | `/api/companies/lookup` | **search ANY company** (name/domain) — resolves + scrapes live |
| POST | `/api/discover` | **target a country** — gather its fleet orgs (search + Wikidata) & scrape |
| GET  | `/api/companies/{id}` | one organisation |
| GET  | `/api/companies/{id}/contacts?refresh=` | scraped data (scrapes live if not cached) |
| POST | `/api/companies/{id}/enrich` | force re-scrape one organisation |
| POST | `/api/enrich?country=&category=&limit=&only_unscraped=` | bulk scrape |
| GET  | `/api/verify?email=` | verify a single address (MX + SMTP) |
| POST | `/api/companies/{id}/verify` | verify all emails of a company |
| POST | `/api/verify/all?limit=` | bulk verify across the directory |
| GET  | `/api/countries` · `/api/categories` | filter options |
| GET/PUT | `/api/settings` | scraper options |
| GET  | `/api/export/contacts?country=&category=&q=` | CSV download |

---

## What this tool will *not* give you (important)

- **Executives' personal mobile/direct phone numbers.** Those are licensed by
  data vendors (Apollo, ZoomInfo, RocketReach…) and companies do not publish
  them, so no free tool — and no legal scraping — can produce them. FleetLeads
  gives you the closest obtainable for free: each executive's **name + title**,
  a **derived email** (clearly unverified), any phone the company prints next
  to them, and the company's **published** phone numbers to call and ask for
  the right person.
- **LinkedIn member data.** Scraping LinkedIn is against its Terms of Service
  (and aggressively blocked), so FleetLeads does not do it. It does capture
  each company's public LinkedIn *company page* URL when the site links to it.

What you *do* get is everything a company officially publishes: its leadership
(real names + titles) with derived emails, general/sales/support inboxes,
switchboard & regional phone numbers, and social profiles — every item with its
source page linked.

---

## Compliance

When you use the scraped data for outreach, follow the applicable rules —
GDPR (EU/UK), CAN-SPAM (US), India's DPDP Act, etc. — and honour each site's
robots.txt (on by default).

## Extending

- **Add more companies**: edit `backend/app/seed_data.py` → `COMPANIES`.
- **Smarter extraction**: extend `enrichment/scraper.py` (e.g. sitemap
  discovery, more structured-data formats, public registry lookups such as
  SEC EDGAR / Companies House for officer names).
- **Scale up**: swap `database.py` for PostgreSQL via SQLAlchemy when you pass
  a few thousand rows.
