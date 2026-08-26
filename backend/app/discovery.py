"""Open-source country → organisation discovery engine.

Given a country, discovers fleet/telematics organisations operating there by
querying free web search (DuckDuckGo HTML + Bing), extracting real company
domains from the results, and filtering out directory/aggregator/blog sites.

No API keys. Polite by design (delays + retries + domain blocklist).
"""
from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36 FleetLeads/1.0"
)

# Directory / aggregator / blog / review sites that appear in search results
# but are NOT the organisations themselves. Their domains are never added.
BLOCKED_DOMAINS = {
    # directories & review sites
    "f6s.com", "sourceforge.net", "slashdot.org", "ensun.io", "g2.com",
    "capterra.com", "getapp.com", "softwareadvice.com", "trustradius.com",
    "crozdesk.com", "saasworthy.com", "financesonline.com", "aeroleads.com",
    "owler.com", "zoominfo.com", "lusha.com", "rocketreach.co", "apollo.io",
    "hunter.io", "leadiq.com", "cognism.com", "6sense.com", "clutch.co",
    "goodfirms.co", "themanifest.com", "designrush.com", "sortlist.com",
    "bark.com", "crunchbase.com", "pitchbook.com", "tracxn.com",
    "startupranking.com", "thedunsnumber.com", "dun & bradstreet",
    "dnb.com", "kompass.com", "europages.com", "wlw.de", "firmenauskunft",
    # blogs & media
    "forbes.com", "techrepublic.com", "businessnewsdaily.com", "geekflare.com",
    "techradar.com", "pcmag.com", "zdnet.com", "medium.com", "blog.",
    "fleetowner.com", "automotive-fleet.com", "ccjdigital.com", "supplychaindigital.com",
    "logisticsmgmt.com", "telematicswire.net", "gpsworld.com", "iotforall.com",
    "techtarget.com", "thestreet.com", "investopedia.com", "startupill.com",
    "thetopfirms.com", "topdevelopers.co", "mobileappdaily.com",
    # social / jobs / generic
    "linkedin.com", "wikipedia.org", "glassdoor.com", "indeed.com", "yelp.com",
    "yellowpages.com", "facebook.com", "twitter.com", "x.com", "youtube.com",
    "instagram.com", "reddit.com", "quora.com", "pinterest.com", "tiktok.com",
    "duckduckgo.com", "bing.com", "google.com", "github.com", "ycombinator.com",
    "news.ycombinator.com",
    # marketplaces / apps
    "amazon.com", "alibaba.com", "made-in-china.com", "globalsources.com",
    "indiamart.com", "ebay.com", "aliexpress.com",
    # government / consumer / non-fleet noise that recurs in searches
    "gps.gov", "gps-coordinates.net", "maps.apple.com", "waze.com",
    "groupsolutions.three.com", "fleetlabs.com", "fleetfarm.com", "fleetfeet.com",
    "yourdictionary.com", "dictionary.cambridge.org",
    # finance / stock sites that match "fleet" (a fleet of companies)
    "stockanalysis.com", "yahoo.com", "barrons.com", "morningstar.com",
    "markets.ft.com", "wsj.com", "marketwatch.com", "investing.com",
    "tradingview.com", "seekingalpha.com", "pchome.megatime.com.tw",
    "finance.yahoo.com", "nasdaq.com", "reuters.com", "bloomberg.com",
}

# Directory sites that, while blocked as sources, are the *only* thing some
# queries return. Their result *titles* often contain real company names — so
# we still harvest titles as name candidates (but never their domains).
NAME_HARVEST_DOMAINS = {"ensun.io", "f6s.com", "aeroleads.com"}

QUERY_TEMPLATES = [
    "fleet management company {country}",
    "fleet telematics company {country}",
    "GPS tracking company {country}",
    "fleet management software {country}",
    "telematics company {country}",
]

# Signals that a domain is a genuine fleet/telematics organisation.
FLEET_KEYWORDS = [
    "fleet management", "fleet tracking", "fleet software", "fleet solutions",
    "fleet telematics", "fleet optimization", "fleet monitoring",
    "telematics", "vehicle tracking", "gps tracking", "gps fleet",
    "gps tracking software", "tracking system", "tracking solutions",
    "asset tracking", "cargo tracking", "driver safety", "driver behaviour",
    "dashcam", "dash cam", "video telematics", "eld", "electronic logging",
    "tachograph", "fuel monitoring", "fuel management", "route optimization",
    "field service management", "transport management", "logistics software",
    "connected car", "connected fleet", "iot fleet", "mobility solutions",
    "track and trace", "real-time tracking", "flottenmanagement", "flotte",
    "flotten", "telematik", "ortung", "fahrzeugortung", "gestion de flotte",
    "rastreo", "rastreador", "monitoramento", "frota",
    "geolocalizaci", "geolocalisation", "geolocation", "位置追踪", "车队",
    "车联网", "追踪", "运输管理", "تتبع المركبات", "テレマティクス",
    "車両管理",
]

# Strong negative signals that immediately disqualify a domain.
NEGATIVE_KEYWORDS = [
    "dictionary", "thesaurus", "merriam-webster", "cambridge dictionary",
    "running shoes", "shoe store", "apparel", "clothing", "farm supply",
    "farm & fleet", "code editor", "jetbrains", "legal advice", "bank", "banking",
    "recruitment", "staffing", "job board",
    "what is telematics", "how do telematics", "telematics definition",
    "telematics & how", "what is fleet", "fleet definition", "definition & meaning",
    "gps coordinates", "global positioning system - wikipedia", "wikipedia",
]

# Single strong words that, if present in the <title> alone, mark a site as
# fleet/telematics even when the body is JS-rendered or thin.
# ("gps" alone is too generic — it matches government/consumer coordinate sites.)
TITLE_STRONG_WORDS = [
    "fleet", "telematics", "telematik", "flotte", "flotten", "flota", "frota",
    "frotas", "telemetria", "telemetría", "tracking", "trucking", "haulage",
    "transport", "logistics", "gps tracking", "vehicle tracking", "iot fleet",
    "vehicle", "mobility",
]


def _looks_like_junk_search(results: list[tuple[str, str]]) -> bool:
    """Detect a canned/bot-degraded search response.

    When engines are throttling a cloud IP they often return the same generic
    "definition of FLEET" / dictionary / Wikipedia page for every query.
    """
    if len(results) < 3:
        return False
    titles = " | ".join(t.lower() for t, _ in results)
    junk_markers = [
        "definition & meaning", "english meaning", "cambridge dictionary",
        "merriam-webster", "disambiguation", "definitions",
    ]
    hits = sum(1 for m in junk_markers if m in titles)
    return hits >= 2


def verify_relevance(domain: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Fetch a domain's homepage and decide whether it's a fleet/telematics org.

    Returns (is_relevant, reason).
    """
    for cand in (f"https://{domain}", f"https://www.{domain}"):
        try:
            r = httpx.get(cand, headers={"User-Agent": USER_AGENT},
                           timeout=timeout, follow_redirects=True)
            if r.status_code >= 400:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            title = (soup.title.get_text(" ", strip=True).lower() if soup.title else "")
            meta = " ".join(
                m.get("content", "") for m in soup.find_all("meta")
                if m.get("name") in ("description", "keywords")
            ).lower()
            # first ~4000 chars of visible text is plenty for classification
            body = soup.get_text(" ", strip=True).lower()[:4000]
            blob = f"{title} {meta} {body}"

            # negative check first
            for neg in NEGATIVE_KEYWORDS:
                if neg in blob:
                    return False, f"negative signal: {neg}"
            hits = [k for k in FLEET_KEYWORDS if k in blob]
            if hits:
                return True, f"fleet signals: {hits[:3]}"
            # JS-rendered / thin pages: trust the <title> for strong words
            title_hits = [w for w in TITLE_STRONG_WORDS if w in title]
            if title_hits:
                return True, f"title signal: {title_hits[:3]}"
            return False, "no fleet/telematics signal on homepage"
        except httpx.HTTPError:
            continue
    return False, "unreachable"


DDG_URL = "https://html.duckduckgo.com/html/"
BING_URL = "https://www.bing.com/search"

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Country name -> Wikidata QID for the most commonly targeted countries.
COUNTRY_QIDS = {
    "united states": "Q30", "usa": "Q30", "united kingdom": "Q145", "uk": "Q145",
    "germany": "Q183", "france": "Q142", "netherlands": "Q55", "belgium": "Q31",
    "spain": "Q29", "italy": "Q38", "portugal": "Q45", "poland": "Q36",
    "sweden": "Q34", "norway": "Q20", "denmark": "Q35", "finland": "Q33",
    "switzerland": "Q39", "austria": "Q40", "ireland": "Q27", "czech republic": "Q213",
    "czechia": "Q213", "romania": "Q218", "hungary": "Q28", "greece": "Q41",
    "turkey": "Q43", "israel": "Q801", "ukraine": "Q212", "russia": "Q159",
    "india": "Q668", "pakistan": "Q843", "bangladesh": "Q902", "sri lanka": "Q854",
    "nepal": "Q837", "china": "Q148", "japan": "Q17", "south korea": "Q884",
    "taiwan": "Q865", "hong kong": "Q8646", "singapore": "Q334", "malaysia": "Q833",
    "indonesia": "Q252", "thailand": "Q869", "vietnam": "Q881", "philippines": "Q928",
    "australia": "Q408", "new zealand": "Q664", "canada": "Q16", "mexico": "Q96",
    "brazil": "Q155", "argentina": "Q414", "chile": "Q298", "colombia": "Q739",
    "peru": "Q419", "uruguay": "Q77", "south africa": "Q258", "nigeria": "Q1033",
    "kenya": "Q114", "egypt": "Q79", "morocco": "Q1028", "tunisia": "Q948",
    "ghana": "Q117", "united arab emirates": "Q878", "uae": "Q878",
    "saudi arabia": "Q851", "qatar": "Q846", "oman": "Q842", "kuwait": "Q817",
    "bahrain": "Q398", "jordan": "Q810", "lebanon": "Q822", "lithuania": "Q37",
    "latvia": "Q211", "estonia": "Q191", "bulgaria": "Q219", "croatia": "Q224",
    "serbia": "Q403", "slovakia": "Q214", "slovenia": "Q215", "luxembourg": "Q32",
    "iceland": "Q189", "malta": "Q233", "cyprus": "Q229",
}


def wikidata_country_companies(country: str, limit: int = 40) -> list[tuple[str, str]]:
    """Fetch (name, website) for fleet/telematics companies in a country from
    Wikidata. Reliable and key-free; sparse for this niche but always honest."""
    qid = COUNTRY_QIDS.get(country.lower())
    if not qid:
        return []
    q = f"""
    SELECT DISTINCT ?companyLabel ?website WHERE {{
      ?company wdt:P31/wdt:P279* wd:Q783794 .
      ?company wdt:P17 wd:{qid} .
      ?company wdt:P452 ?industry .
      ?industry rdfs:label ?industryLabel .
      FILTER(LANG(?industryLabel) = "en")
      FILTER(REGEX(STR(?industryLabel), "fleet|telematics|tracking|GPS|vehicle tracking", "i"))
      ?company wdt:P856 ?website .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT {limit}
    """
    try:
        r = httpx.get(WIKIDATA_SPARQL, params={"query": q, "format": "json"},
                      headers={"User-Agent": USER_AGENT}, timeout=45)
        if r.status_code != 200:
            return []
        rows = r.json()["results"]["bindings"]
        out = []
        for row in rows:
            name = row.get("companyLabel", {}).get("value")
            site = row.get("website", {}).get("value")
            if not name or not site or name.startswith("Q"):
                continue
            dom = _domain(site)
            if dom:
                out.append((name, dom))
        return out
    except Exception:
        return []


class SearchProvider:
    name = "base"

    def search(self, query: str) -> list[tuple[str, str]]:
        """Return list of (title, url) results."""
        raise NotImplementedError


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def search(self, query: str) -> list[tuple[str, str]]:
        try:
            r = httpx.post(
                DDG_URL,
                data={"q": query},
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
                follow_redirects=True,
            )
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "lxml")
            out: list[tuple[str, str]] = []
            for res in soup.select(".result"):
                a = res.select_one(".result__a")
                if not a:
                    continue
                href = a.get("href", "")
                url = self._decode(href)
                title = a.get_text(" ", strip=True)
                if url and title:
                    out.append((title, url))
            return out
        except httpx.HTTPError:
            return []

    @staticmethod
    def _decode(href: str) -> str | None:
        m = re.search(r"uddg=([^&]+)", href)
        if not m:
            return None
        return unquote(m.group(1))


class BingProvider(SearchProvider):
    name = "bing"

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def search(self, query: str) -> list[tuple[str, str]]:
        try:
            r = httpx.get(
                BING_URL,
                params={"q": query, "count": 20},
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
                follow_redirects=True,
            )
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "lxml")
            out: list[tuple[str, str]] = []
            for item in soup.select("li.b_algo"):
                a = item.select_one("h2 a")
                if not a:
                    continue
                title = a.get_text(" ", strip=True)
                url = self._decode(a.get("href"))
                if url and title:
                    out.append((title, url))
            return out
        except httpx.HTTPError:
            return []

    @staticmethod
    def _decode(href: str) -> str | None:
        """Bing wraps result URLs as /ck/a?…&u=<base64url of target>&…"""
        if not href:
            return None
        if "/ck/a" in href:
            m = re.search(r"[&?]u=([^&]+)", href)
            if m:
                enc = m.group(1)
                # Bing prefixes the base64 payload with "a1" (a version marker).
                if enc.startswith("a1"):
                    enc = enc[2:]
                # URL-safe base64 without padding
                enc += "=" * (-len(enc) % 4)
                try:
                    import base64
                    decoded = base64.urlsafe_b64decode(enc).decode("utf-8", "ignore")
                    if decoded.startswith("http"):
                        return decoded
                except Exception:
                    return None
            return None
        if href.startswith("http"):
            return href
        return None


def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.lower()
        d = d.removeprefix("www.")
        d = d.removeprefix("m.")
        return d
    except Exception:
        return ""


def _blocked(url: str) -> bool:
    dom = _domain(url)
    if not dom or "." not in dom:
        return True
    if dom in BLOCKED_DOMAINS:
        return True
    # subdomain or partial matches against blocklist
    parts = dom.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in BLOCKED_DOMAINS:
            return True
    return False


def _title_name_candidate(title: str) -> str | None:
    """Pull a plausible company name out of a result title like
    'Top GPS Tracking Companies in Germany - ensun' -> ignored; or
    'Fairfleet GmbH & Co. KG - Telematics- and Fleet management' -> 'Fairfleet GmbH'."""
    t = title.strip()
    if not t or len(t) < 4:
        return None
    # strip trailing " - Source" style suffixes
    t = re.sub(r"\s*[-–|]\s*(source|review|top|best|compare|list|directory).*$", "", t, flags=re.I)
    t = re.sub(r"^Top\s+\d+\s+", "", t, flags=re.I)
    t = re.sub(r"^\d+\s+(?:Top|Best)\s+", "", t, flags=re.I)
    t = t.strip(" -–|")
    return t if 3 <= len(t) <= 60 else None


class DiscoveryEngine:
    def __init__(self, delay: float = 4.0, max_results_per_query: int = 8):
        self.delay = delay
        self.max_results_per_query = max_results_per_query
        # Bing first (more tolerant of repeated queries); DDG as fallback.
        self.providers: list[SearchProvider] = [BingProvider(), DuckDuckGoProvider()]

    def discover(self, country: str, extra_terms: list[str] | None = None,
                 max_domains: int = 25, verify: bool = True,
                 verify_limit: int = 40) -> dict:
        """Discover fleet/telematics organisations in a country.

        Sources (merged + deduped):
          1. Wikidata (reliable, key-free, sparse)
          2. Web search — Bing then DuckDuckGo (best-effort; engines rate-limit
             aggressively from cloud IPs, so yields vary)

        When `verify` is True, each web-search candidate's homepage is fetched
        and checked for fleet/telematics signals before being returned.
        """
        sources_used: list[str] = []
        domains: dict[str, str] = {}     # domain -> best title/name
        wikidata_domains: set[str] = set()

        # --- 1) Wikidata ------------------------------------------------- #
        for name, dom in wikidata_country_companies(country):
            if dom not in domains:
                domains[dom] = name
                wikidata_domains.add(dom)
        if wikidata_domains:
            sources_used.append("wikidata")

        # --- 2) Web search ----------------------------------------------- #
        queries = [t.format(country=country) for t in QUERY_TEMPLATES]
        if extra_terms:
            queries += [f"{term} {country}" for term in extra_terms]

        name_candidates: set[str] = set()
        consecutive_junk = 0
        for q in queries:
            got = False
            for provider in self.providers:
                if got:
                    break
                try:
                    results = provider.search(q)
                except Exception:
                    results = []
                if results and _looks_like_junk_search(results):
                    results = []  # canned/bot-degraded response -> discard
                if results:
                    got = True
                    if provider.name not in sources_used:
                        sources_used.append(provider.name)
            if not got:
                consecutive_junk += 1
                time.sleep(self.delay)
                if consecutive_junk >= 3:
                    # engine is throttling us; stop burning time on search
                    break
                continue
            consecutive_junk = 0
            for title, url in results:
                if _blocked(url):
                    dom = _domain(url)
                    if dom in NAME_HARVEST_DOMAINS:
                        name = _title_name_candidate(title)
                        if name:
                            name_candidates.add(name)
                    continue
                dom = _domain(url)
                if dom and dom not in domains:
                    domains[dom] = title
            time.sleep(self.delay)
            if len(domains) >= max_domains * 2:  # over-fetch; verification filters down
                break

        # --- 3) Relevance verification ----------------------------------- #
        verified: dict[str, str] = {}
        rejected: dict[str, str] = {}
        if verify:
            for dom, title in list(domains.items())[:verify_limit]:
                if dom in wikidata_domains:
                    # Wikidata entries are industry-filtered already.
                    verified[dom] = title
                    continue
                ok, reason = verify_relevance(dom)
                if ok:
                    verified[dom] = title
                else:
                    rejected[dom] = reason
                time.sleep(0.3)
        else:
            verified = dict(list(domains.items())[:max_domains])

        return {
            "country": country,
            "domains": verified,
            "rejected": rejected,
            "name_candidates": sorted(name_candidates),
            "queries_run": queries,
            "sources_used": sources_used,
        }
