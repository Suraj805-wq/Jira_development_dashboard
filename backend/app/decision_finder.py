"""Decision-maker NAME finder — finds executives from open public sources.

Used when an organisation's own website doesn't publish its leadership.

Primary:   Wikipedia (fully open, legitimate) — infobox `founder`/`founders`
           and `key_people`/`key people` fields list founders, CEOs, CFOs,
           chairmen.
Secondary: open-web search (Bing → DuckDuckGo) — role-specific queries whose
           result TITLES/SNIPPETS contain "Name — Title — Company" text.

IMPORTANT: linkedin.com member pages are NEVER accessed. Reading a search
engine's own results (which may mention LinkedIn profile titles) is legitimate
and is exactly what the search engine is designed to surface.
"""
from __future__ import annotations

import re
import time

import httpx

from .enrichment.scraper import PRESS_RE, REVERSED_PRESS_RE, ROLE_CHECK, USER_AGENT

WIKI_API = "https://en.wikipedia.org/w/api.php"
BING_URL = "https://www.bing.com/search"
DDG_URL = "https://html.duckduckgo.com/html/"

ROLE_QUERIES = [
    '"{name}" CEO',
    '"{name}" founder',
    '"{name}" chief executive officer',
    '"{name}" managing director',
]

# Company-name suffixes to strip when matching Wikipedia page titles.
SUFFIX_RE = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|group|company|technologies|"
    r"technology|holdings|plc|gmbh|ag|sa|srl|bv|pvt|private|solutions|"
    r"systems|software|telematics|tracking|international|holdings)\b\.?",
    re.IGNORECASE,
)

REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.S)
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]|\[\[([^\]]+)\]\]")
BR_RE = re.compile(r"<br\s*/?>", re.I)


def _resolve_wikilinks(text: str) -> str:
    def repl(m):
        if m.group(2):
            return m.group(2)      # [[Target|display]] -> display
        return m.group(3) or m.group(1)  # [[Target]] -> Target
    return WIKILINK_RE.sub(repl, text)


def _clean_text(text: str) -> str:
    text = REF_RE.sub("", text)
    text = _resolve_wikilinks(text)
    text = BR_RE.sub(", ", text)
    text = re.sub(r"\{\{[^}]+\}\}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_name(name: str) -> str | None:
    name = _clean_text(name)
    name = re.sub(r"\bet al\.?\b", "", name, flags=re.I)
    name = re.sub(r"\(born[^)]*\)|\([0-9]{4}[\u2013-][^)]*\)|\([0-9]{4}\)", "", name)
    name = re.sub(r"\b\d{4}\b", "", name)
    name = name.strip(" ,;–—-.")
    if not name or len(name) < 4 or len(name) > 60:
        return None
    # must look like a person's name (2-3 capitalized words)
    if not re.fullmatch(r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ.\-']+(?:\s+[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ.\-']+){1,2}", name):
        # allow middle initials etc.
        if not re.search(r"[A-ZÀ-ÖØ-Þ]", name):
            return None
    return name


def _clean_role(role: str) -> str | None:
    role = _clean_text(role)
    role = role.strip(" (),")
    if not role or len(role) > 70:
        return None
    return role


# --------------------------------------------------------------------------- #
def _wikipedia_pages(company_name: str) -> list[str]:
    """Candidate Wikipedia page titles for a company, in relevance order.

    Falls back to the brand token (first word) if the full name isn't found.
    Prefers organisation pages ("… (company)", "… Inc.") over films/places.
    """
    def search(q: str) -> list[str]:
        try:
            r = httpx.get(WIKI_API, params={
                "action": "opensearch", "search": q, "limit": 8, "format": "json",
            }, headers={"User-Agent": USER_AGENT}, timeout=15)
            data = r.json()
            titles, urls = data[1], data[3]
            return [t for t, u in zip(titles, urls) if u.startswith("https://en.wikipedia.org")]
        except Exception:
            return []

    titles = search(company_name)
    if not titles:
        brand_tokens = [t for t in re.findall(r"[a-z0-9]+", company_name.lower()) if len(t) >= 2]
        if brand_tokens:
            titles = search(brand_tokens[0])

    brand_tokens = [t for t in re.findall(r"[a-z0-9]+", company_name.lower()) if len(t) >= 2]
    brand = brand_tokens[0] if brand_tokens else company_name.lower()

    scored: list[tuple[int, str]] = []
    for title in titles:
        t_tokens = [x for x in re.findall(r"[a-z0-9]+", title.lower()) if len(x) >= 2]
        if not t_tokens:
            continue
        score = 0
        if t_tokens[0] == brand:
            score += 5
        if company_name.lower().strip() == title.lower().strip():
            score += 3
        if re.search(r"\(company\)|\binc\b|\bcorporation\b|\bltd\b", title, re.I):
            score += 4
        score += len(set(brand_tokens) & set(t_tokens))
        scored.append((score, title))
    scored.sort(key=lambda x: -x[0])
    return [t for s, t in scored if s >= 5]


def _fetch_wikitext(page: str) -> str:
    """Fetch raw wikitext, following #REDIRECTs."""
    seen: set[str] = set()
    for _ in range(3):
        if page in seen:
            return ""
        seen.add(page)
        try:
            r = httpx.get(WIKI_API, params={
                "action": "parse", "page": page, "prop": "wikitext",
                "format": "json", "formatversion": "2",
            }, headers={"User-Agent": USER_AGENT}, timeout=15)
            wt = r.json()["parse"]["wikitext"]
        except Exception:
            return ""
        m = re.search(r"#REDIRECT\s*\[\[([^\]|#]+)", wt, re.I)
        if m:
            page = m.group(1).strip()
            continue
        return wt
    return ""


def _preprocess_infobox(wt: str) -> str:
    """Normalise wikitext so role/name fields parse cleanly."""
    # {{ubl|...}} / {{plainlist|...}} / {{Unbulleted list|...}} -> inner content
    wt = re.sub(r"\{\{(?:ubl|plainlist|Unbulleted list)\|(.*?)\}\}", r"\1", wt, flags=re.S)
    # ([[CEO]])     -> (CEO)
    wt = re.sub(r"\(\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]\s*\)",
                lambda m: f"({m.group(2) or m.group(1)})", wt)
    # {{small|...}} -> ...
    wt = re.sub(r"\{\{small\|(.*?)\}\}", r"\1", wt, flags=re.S)
    return wt


def _parse_people_items(value: str) -> list[tuple[str, str]]:
    """Parse a key_people / founders value into (name, role) pairs.

    Handles:
      - "Name (Role)"                       e.g. "Robert Painter (CEO)"
      - "[[Name]] ([[Role]])"               (wikilinks resolved beforehand)
      - "{{ubl|Name|(Role)|Name|(Role)}}"   alternating name / (role) items
    """
    out: list[tuple[str, str]] = []
    pending_name: str | None = None
    for item in value.split("|"):
        cleaned = _clean_text(item).strip()
        if not cleaned:
            continue
        # "Name (Role)"
        m = re.match(r"(.+?)\s*\(\s*(.+?)\s*\)\s*$", cleaned)
        if m:
            name = _clean_name(m.group(1))
            role = _clean_role(m.group(2))
            if name and role:
                out.append((name, role))
            pending_name = None
            continue
        # "(Role)" alone -> attach to pending name
        m = re.match(r"\(\s*(.+?)\s*\)\s*$", cleaned)
        if m:
            role = _clean_role(m.group(1))
            if pending_name and role:
                out.append((pending_name, role))
            pending_name = None
            continue
        # bare name
        name = _clean_name(cleaned)
        if name:
            pending_name = name
    return out


def _wikipedia_people(company_name: str) -> list[dict]:
    pages = _wikipedia_pages(company_name)
    if not pages:
        return []

    people: dict[str, dict] = {}

    for page in pages:
        wt = _preprocess_infobox(_fetch_wikitext(page))
        if not wt:
            continue
        url = f"https://en.wikipedia.org/wiki/{page.replace(' ', '_')}"

        def add(name: str | None, role: str | None):
            if not name or not role:
                return
            key = name.lower()
            if key not in people:
                people[key] = {"name": name, "title": role, "source_url": url}

        # ---- founder / founders ----
        for field in ("founder", "founders"):
            m = re.search(r"\|\s*" + field + r"\s*=\s*(.+)", wt, re.I)
            if not m:
                continue
            value = _clean_text(m.group(1))
            value = re.sub(r"\bet al\.?\b", "", value, flags=re.I)
            for part in re.split(r"<br\s*/?>|,|\band\b|&|;|\n|\|", value):
                name = _clean_name(part.strip())
                if name:
                    add(name, "Founder")

        # ---- key people / key_people ----
        for field in ("key_people", "key people", "key_peoples"):
            m = re.search(r"\|\s*" + field + r"\s*=\s*(.+)", wt, re.I)
            if not m:
                continue
            for name, role in _parse_people_items(m.group(1)):
                add(name, role)

        # stop once we found people on the best-matching page
        if people:
            break
    return list(people.values())


# --------------------------------------------------------------------------- #
def _bing_search(query: str) -> list[tuple[str, str]]:
    try:
        r = httpx.get(BING_URL, params={"q": query, "count": 8},
                      headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
                      timeout=20, follow_redirects=True)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        out = []
        for it in soup.select("li.b_algo"):
            a = it.select_one("h2 a")
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            snip_el = it.select_one(".b_caption p") or it.select_one("p")
            snip = snip_el.get_text(" ", strip=True) if snip_el else ""
            out.append((title, snip))
        return out
    except httpx.HTTPError:
        return []


def _ddg_search(query: str) -> list[tuple[str, str]]:
    try:
        r = httpx.post(DDG_URL, data={"q": query},
                       headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
        from bs4 import BeautifulSoup
        from urllib.parse import unquote
        soup = BeautifulSoup(r.text, "lxml")
        out = []
        for res in soup.select(".result"):
            a = res.select_one(".result__a")
            if not a:
                continue
            href = a.get("href", "")
            m = re.search(r"uddg=([^&]+)", href)
            title = a.get_text(" ", strip=True)
            snip_el = res.select_one(".result__snippet")
            snip = snip_el.get_text(" ", strip=True) if snip_el else ""
            if title:
                out.append((title, snip))
        return out
    except httpx.HTTPError:
        return []


def _extract_from_search(title: str, snippet: str) -> list[dict]:
    """Extract (name, title) pairs from a search result's title + snippet."""
    found: list[dict] = []
    blob = f"{title}. {snippet}"
    for m in PRESS_RE.finditer(blob):
        name = m.group("name")
        role = m.group("role")
        if name and role and not any(w in name.lower() for w in ("company", "companies", "wikipedia", "login", "sign")):
            found.append({"name": name, "title": role.strip(" ,")})
    for m in REVERSED_PRESS_RE.finditer(blob):
        name = m.group("name")
        role = m.group("role")
        if name and role and not any(w in name.lower() for w in ("company", "companies", "login", "sign")):
            found.append({"name": name, "title": role.strip(" ,")})
    # "Name – Title – Company" pattern: role must actually look like a role
    m = re.match(r"(.+?)\s+[\u2013—-]\s+(.+?)\s*[\u2013—-]", title)
    if m:
        candidate_name = m.group(1).strip()
        candidate_role = m.group(2).strip()
        if ROLE_CHECK.match(candidate_role) and not any(
            w in candidate_name.lower() for w in ("login", "sign in", "signup")
        ):
            found.append({"name": candidate_name, "title": candidate_role})
    return found


def _search_people(company_name: str, delay: float = 1.2) -> list[dict]:
    people: dict[str, dict] = {}
    # brand token — a search result must MENTION the company to be kept
    brand_tokens = [t for t in re.findall(r"[a-z0-9]+", company_name.lower()) if len(t) >= 3]
    brand = brand_tokens[0] if brand_tokens else company_name.lower()

    for q in ROLE_QUERIES:
        query = q.format(name=company_name)
        results = _bing_search(query) or _ddg_search(query)
        from urllib.parse import quote
        search_url = "https://www.bing.com/search?q=" + quote(query)
        for title, snippet in results:
            blob_lower = f"{title} {snippet}".lower()
            # relevance guard: the result must actually be about this company
            if brand not in blob_lower and not any(t in blob_lower for t in brand_tokens):
                continue
            for p in _extract_from_search(title, snippet):
                key = p["name"].lower()
                if key not in people:
                    people[key] = {
                        "name": p["name"],
                        "title": p["title"],
                        "source_url": search_url,
                    }
        time.sleep(delay)
    return list(people.values())


# --------------------------------------------------------------------------- #
def find_decision_makers(company_name: str, domain: str = "") -> list[dict]:
    """Return decision makers (name+title) from open sources for a company.

    Wikipedia first (reliable, free), then open-web search as a supplement.
    Never touches linkedin.com member pages.
    """
    people: dict[str, dict] = {}

    for p in _wikipedia_people(company_name):
        people.setdefault(p["name"].lower(), p)

    for p in _search_people(company_name):
        people.setdefault(p["name"].lower(), p)

    out = []
    for p in people.values():
        out.append({
            "name": p["name"],
            "title": p["title"],
            "email": None,
            "email_status": None,
            "phone": None,
            "phone_label": None,
            "linkedin_url": None,
            "linkedin_type": None,
            "source_url": p["source_url"],
        })
    return out
