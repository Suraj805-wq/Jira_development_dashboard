"""Open-source website scraper — the only data source.

Extracts what companies publish on their own websites:

  - email addresses (``mailto:`` links + text, TLD-filtered)
  - phone numbers (``tel:`` links + explicit international / US formats)
  - social profiles (LinkedIn company page, X/Twitter, Facebook, Instagram, YouTube)
  - organisation details from JSON-LD structured data (name, address, sameAs)
  - **decision makers**: names + job titles from structured data (JSON-LD /
    microdata), leadership/team page "Name Title" blocks, and press-release
    phrasing ("said X, CEO of Y")
  - **derived executive emails**: when a company's published emails reveal a
    naming convention (e.g. first.last@domain), the same convention is applied
    to the executives' names. These are ALWAYS flagged ``pattern-derived``
    (unverified) — FleetLeads never presents them as confirmed.

Every item records the exact page it was found on, so results are verifiable.
**Nothing is invented** — if a page doesn't publish it, it isn't returned.

Dependencies: httpx, beautifulsoup4, lxml — all open-source (BSD/MIT).
"""
from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36 FleetLeads/1.0 "
    "(open-source fleet-market research)"
)

KNOWN_TLDS = {
    "com", "org", "net", "io", "co", "ai", "dev", "app", "me", "info", "biz",
    "edu", "gov", "mil", "int", "eu", "xyz", "site", "online", "tech", "cloud",
    "in", "co.in", "org.in", "ac.in", "gov.in",
    "uk", "co.uk", "org.uk", "ac.uk", "gov.uk",
    "au", "com.au", "org.au", "net.au", "nz", "co.nz", "ca", "us",
    "de", "fr", "nl", "be", "dk", "no", "se", "fi", "is", "ie", "at", "ch",
    "it", "es", "pt", "gr", "pl", "cz", "sk", "hu", "ro", "bg", "hr", "rs", "ua",
    "lt", "lv", "ee", "tr", "il", "ru",
    "za", "co.za", "org.za", "ng", "ke", "eg", "ma", "tn", "gh",
    "ae", "sa", "qa", "om", "kw", "bh", "jo", "lb", "pk", "bd", "lk", "np",
    "sg", "my", "id", "th", "vn", "ph", "jp", "cn", "kr", "hk", "tw",
    "br", "com.br", "org.br", "mx", "com.mx", "ar", "cl", "co", "com.co", "pe",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
INTL_PHONE_RE = re.compile(r"\+[0-9][0-9\s\-().]{6,18}[0-9]")
US_PHONE_RE = re.compile(r"\(\d{3}\)[\s.\-]?\d{3}[\s.\-]?\d{4}")

# --------------------------------------------------------------------------- #
# Decision-maker extraction machinery
# --------------------------------------------------------------------------- #
# Accented-Latin ranges included so names like "Böckers" / "López" survive,
# plus Latin Extended-A/B for Polish/Turkish/Czech/Romanian letters
# (ł, ą, ę, ś, ż, ş, ğ, ı, č, ș, …). Both straight (') and curly (’)
# apostrophes accepted so "O’Meara" works.
NAME_TOKEN = r"[A-ZÀ-ÖØ-Þ\u0100-\u017f\u0180-\u024f][A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u017f\u0180-\u024f.'’\-]*"
NAME_RE = re.compile(r"^(?P<name>" + NAME_TOKEN + r"(?:\s+" + NAME_TOKEN + r"){1,3})$")
WORD_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u017f\u0180-\u024f][A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u017f\u0180-\u024f.'’\-]*")

# Role/department/region tokens that must never be treated as person-name
# evidence when inferring an email convention from a bare address.
ROLE_TOKENS = {
    "sales", "support", "info", "contact", "contacts", "hello", "office",
    "media", "press", "marketing", "partners", "partner", "partnership",
    "billing", "accounts", "accounting", "finance", "careers", "career",
    "jobs", "hr", "people", "talent", "recruiting", "recruit", "webmaster",
    "noreply", "no", "reply", "enquiries", "enquiry", "inquiries", "inquiry",
    "orders", "returns", "grievance", "ethics", "complaints", "security",
    "privacy", "legal", "admin", "administrator", "help", "helpdesk",
    "servicedesk", "service", "services", "customer", "customers", "customerservice",
    "business", "bd", "bizdev", "ventas", "dach", "benelux", "uki", "uk",
    "apac", "emea", "latam", "na", "us", "usa", "ca", "mx", "eu", "global",
    "team", "main", "general", "inbox", "postmaster", "abuse", "hostmaster",
    "it", "web", "news", "newsletter", "events", "training", "academy",
    "development", "dev", "api", "data", "accountsreceivable", "ar",
}

NAME_EMAIL_PAIR_RE = re.compile(
    r"\b(?P<name>" + NAME_TOKEN + r"(?:\s+" + NAME_TOKEN + r"){1,3})"
    r"\s*(?:,|\(|—|–|-|·|:)\s*"
    r"(?P<email>[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
)

# Words that mark the START of a job title when they appear after a person's name.
# Deliberately restricted to STRONG executive words — loose modifiers (e.g.
# "fleet", "software") caused blog headings to be mistaken for people.
TITLE_WORDS = {
    # English
    "chief", "co-founder", "cofounder", "founder", "managing", "general", "vice",
    "president", "chairman", "chairperson", "board", "evp", "svp", "avp", "vp",
    "ceo", "coo", "cto", "cfo", "cio", "cmo", "cro", "cso", "cpo", "chro", "ciso",
    "cao", "cco", "director", "head", "partner", "proprietor", "owner",
    "executive", "senior", "manager",
    # Spanish
    "director", "directora", "gerente", "presidente", "presidenta",
    "consejero", "consejera", "delegado", "delegada", "fundador", "fundadora",
    "cofundador", "vicepresidente", "jefe", "jefa", "responsable", "socio",
    "socia", "director", "directora",
    # French
    "directeur", "directrice", "président", "president", "fondateur",
    "fondatrice", "gérant", "gérante", "responsable", "cofondateur",
    # German
    "geschäftsführer", "geschäftsführerin", "vorstand", "vorstandsvorsitzender",
    "leiter", "leiterin", "gründer", "gründerin", "inhaber", "inhaberin",
    # Italian
    "direttore", "direttrice", "presidente", "fondatore", "fondatrice",
    "amministratore", "delegato", "responsabile", "socio", "socia",
    # Portuguese
    "diretor", "diretora", "gerente", "presidente", "fundador", "fundadora",
    "sócio", "sócia", "cofundador",
    # Turkish
    "müdür", "müdürü", "kurucu", "başkan", "yönetici", "genel",
    # Polish
    "dyrektor", "prezes", "założyciel", "kierownik",
}

# Strong job-title words (used when the TITLE precedes the NAME, e.g.
# "Vice President, Global Fleet Solutions Brad Taylor"). A text block only
# counts as a reversed person-entry if the head contains one of these AND the
# tail is a valid Title-case name.
STRONG_TITLE_WORDS = {
    # Leadership / decision-maker roles ONLY. Individual-contributor roles
    # (analyst, engineer, developer, specialist, …) are deliberately excluded —
    # they are not decision makers and they caused prose/list text to be
    # misread as "Title Name" people (e.g. "Business Analyst … Mobile Web").
    "chief", "officer", "president", "director", "manager", "vp", "evp", "svp",
    "avp", "head", "executive", "founder", "co-founder", "cofounder", "ceo",
    "coo", "cto", "cfo", "cio", "cmo", "cro", "cso", "cpo", "chro", "ciso",
    "cao", "cco", "chairman", "chairperson", "managing", "general", "partner",
    "owner", "proprietor", "senior", "board",
    # multilingual leadership words
    "director", "directora", "gerente", "presidente", "presidenta",
    "consejero", "delegado", "fundador", "fundadora", "cofundador",
    "vicepresidente", "jefe", "directeur", "directrice", "fondateur",
    "fondatrice", "gérant", "geschäftsführer", "vorstand", "leiter",
    "gründer", "inhaber", "direttore", "direttrice", "fondatore",
    "amministratore", "diretor", "diretora", "sócio", "sócia", "müdür",
    "kurucu", "başkan", "dyrektor", "prezes", "założyciel",
}

# Honorifics that may appear between a title and a name ("Chairman Mr. X").
HONORIFICS = {"mr", "ms", "mrs", "miss", "dr", "prof"}

ROLE_CORE = (
    r"Chief\s+[A-Za-z]+\s+Officer"
    r"|Chief\s+[A-Za-z]+"
    r"|Co-?[Ff]ounder"
    r"|Founder"
    r"|Managing\s+Director"
    r"|General\s+Manager"
    r"|Vice\s+President"
    r"|President"
    r"|Chairman"
    r"|Chairperson"
    r"|Board\s+Member"
    r"|EVP|SVP|AVP|VP"
    r"|CEO|COO|CTO|CFO|CIO|CMO|CRO|CSO|CPO|CHRO|CISO|CAO|CCO"
    r"|Director"
    r"|Head"
    r"|Partner|Proprietor|Owner"
)
ROLE_CHECK = re.compile(r"^\s*(?:" + ROLE_CORE + r")\b", re.IGNORECASE)

PRESS_RE = re.compile(
    r"\b(?P<name>" + NAME_TOKEN + r"(?:\s+" + NAME_TOKEN + r"){1,3})"
    r"(?:\s*,|\s+is\s+the|\s+is\s+|\s+was\s+the|\s+was\s+)"
    r"\s*(?:the\s+|our\s+|as\s+|new\s+|its\s+|company'?s\s+)?"
    r"(?P<role>" + ROLE_CORE + r"\b(?:\s+of\s+[A-Za-z&]+(?:\s+[A-Za-z&]+)?)?)"
)

# Reversed form found in press releases: "Group Chairman Mr. Tushar Bhagat".
# Captures a leadership title (optionally prefixed by group/deputy/senior/...),
# an optional honorific, then a person's name.
REVERSED_PRESS_RE = re.compile(
    r"\b(?P<role>(?:(?:group|deputy|senior|associate|global|regional|national|"
    r"executive|managing)\s+)?"
    r"(?:chairman|chairperson|"
    r"chief\s+(?:executive|operating|technology|financial|revenue|marketing|"
    r"people|information|security|commercial|customer|administrative|"
    r"accounting|legal|business\s+development|strategy|growth|product)\s+officer|"
    r"ceo|coo|cto|cfo|cio|cmo|cro|cpo|chro|ciso|cao|cco|"
    r"founder|co-?founder|managing\s+director|general\s+manager|"
    r"vice\s+president|president|director|head\s+of\s+[a-z]+|board\s+member|partner))\b"
    r"(?:\s+(?:mr|ms|mrs|miss|dr|prof)\.?)?\s+"
    r"(?P<name>" + NAME_TOKEN + r"(?:\s+" + NAME_TOKEN + r"){1,2})",
    re.IGNORECASE,
)


NAME_STOP = {
    "contact", "contacts", "about", "team", "meet", "the", "our", "us", "your",
    "with", "and", "for", "sales", "support", "careers", "career", "blog",
    "news", "press", "media", "privacy", "terms", "policy", "policies", "login",
    "sign", "register", "search", "menu", "home", "back", "top", "next",
    "previous", "learn", "more", "read", "view", "get", "start", "all", "by",
    "a", "an", "inc", "ltd", "llc", "corp", "group", "company", "corporation",
    "solutions", "services", "products", "platform", "dashboard", "reports",
    "login", "subscribe", "download", "connect", "follow", "share", "close",
    "open", "submit", "send", "email", "phone", "address", "office",
    "headquarters", "regional", "global", "worldwide", "locations", "partners",
    "customers", "drivers", "fleets", "fleet", "this", "that", "here", "there",
    "request", "demo", "book", "call", "talk", "speak", "chat", "message",
    "customer", "referral", "refer", "program", "programs", "founding", "partner",
    "partnership", "advisors", "advisory", "investors", "investor", "entrepreneur",
    "former", "formerly", "prior", "previous", "acting", "interim", "ex", "hr",
    # business/title words that are never part of a person's name
    "accounts", "account", "national", "north", "south", "east", "west",
    "american", "regional", "operations", "operation", "international",
    "division", "department", "manager", "director", "officer", "executive",
    "vice", "chief", "senior", "head", "lead", "president", "vp", "svp", "evp",
    "avp", "gms", "gm", "mds", "md", "corporation", "corp",
    # tech / team / function words that are never a person's name
    "mobile", "web", "desktop", "server", "comserver", "frontend", "front",
    "backend", "back", "end", "ios", "android", "qa", "quality", "ui", "ux",
    "devops", "data", "cloud", "design", "testing", "tester", "test", "java",
    "php", "python", "dotnet", "net", "api", "infra", "infrastructure",
    "analyst", "analysts", "developer", "developers", "engineer", "engineers",
    "designer", "specialist", "coordinator", "supervisor", "consultant",
    "scientist", "architect", "accountant", "attorney", "treasurer",
    "secretary", "administrator", "assistant", "associate", "mr", "ms", "mrs",
    "miss", "dr", "prof",
    # common prose words (never part of a person's name)
    "what", "is", "are", "was", "were", "of", "to", "in", "on", "for", "a", "an",
    "it", "its", "and", "or", "with", "by", "at", "from", "as", "this", "that",
    "these", "those", "how", "why", "when", "where", "who", "which", "your",
    "their", "we", "you", "they", "has", "have", "had", "do", "does", "did",
    "will", "would", "can", "could", "should", "may", "might", "must", "tips",
    "ways", "benefits", "guide", "features", "solutions", "management",
    "tracking", "telematics", "logistics", "transportation", "fleet", "fleets",
    "case", "study", "story", "stories", "help", "faq", "resource", "resources",
    "white", "paper", "ebook", "webinar", "download", "video", "watch", "best",
    "top", "latest", "free", "today", "now", "here", "there", "out", "up", "off",
    "over", "under", "into", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "no", "not", "yes", "any", "some", "more",
    "most", "other", "only", "just", "also", "even", "than", "then", "be",
    "been", "being", "new", "our", "us",
}

# Word-boundary matching so "teams-evolve" does NOT match the keyword "team".
PEOPLE_PAGE_RE = re.compile(
    r"\b(?:leadership|management|executive|board|people|founder|senior|"
    r"our-team|management-team|who-we-are|the-team|our-story|our-leadership|team)\b",
    re.IGNORECASE,
)
PRESS_PAGE_RE = re.compile(
    r"\b(?:press|news|newsroom|media|blog|insights|release|investor|"
    r"webinar|exhibitions|stories|updates|corporate-news)\b",
    re.IGNORECASE,
)

# Job-title fragments that indicate the person is NOT a company decision maker
# (e.g. a customer in a case study, or an external organisation).
TITLE_BLOCKLIST = (
    "police", "sheriff", "fire chief", "fire department", "mayor", "city of",
    "county of", "school district", "university", "hospital", "church",
    "ministry", "inc.", "llc", "ltd.", "corp.", "agency", "association",
    "coach", "captain", "lieutenant", "sergeant", "superintendent", "principal",
    "teacher", "professor",
    " at ", " with ",  # "CIO at Acme Co." / "Engineer with Acme" => external person
    " company", " motors", " group plc", " plc", " holdings", " systems",
    " construction", " industrial", " steel", " builders", " contractors",
)

GUESS_PATHS = [
    "/about/leadership", "/company/leadership", "/leadership", "/about-us/leadership",
    "/about/our-team", "/our-team", "/about/team", "/team", "/about-us/team",
    "/about/management", "/company/management", "/management",
    "/who-we-are", "/about/who-we-are", "/our-story", "/the-team", "/our-leadership",
    "/about-us", "/about", "/company", "/about/company",
    "/contact", "/contact-us", "/contact-us/", "/contact/", "/contact-us-2",
    "/sales", "/sales-contact", "/request-a-demo", "/support", "/get-in-touch",
    "/press", "/news", "/newsroom", "/media", "/investors", "/investor-relations",
]

LINK_KEYWORDS = [
    "leadership", "executive", "board", "team", "about", "company",
    "press", "news", "media", "newsroom", "investor", "contact", "support",
    "help", "careers", "people", "our-team", "meet-the-team", "management-team",
    "who-we-are", "our-story", "the-team", "about-us", "our-leadership",
    "executive-team", "leadership-team",
]

# Priority when choosing which pages to crawl (lower = crawl first).
LINK_PRIORITY = {
    "leadership": 0, "executive": 0, "board": 0, "team": 0,
    "our-team": 0, "meet-the-team": 0, "management-team": 0,
    "who-we-are": 0, "our-story": 0, "the-team": 0, "our-leadership": 0,
    "executive-team": 0, "leadership-team": 0,
    "about": 1, "company": 1, "about-us": 1,
    "press": 2, "news": 2, "media": 2, "newsroom": 2, "investor": 2,
    "contact": 3,
    "support": 4, "help": 4,
    "careers": 5, "people": 5,
}

SOCIAL_PATTERNS = [
    ("linkedin", re.compile(r"linkedin\.com/company/")),
    ("linkedin", re.compile(r"linkedin\.com/school/")),
    ("x", re.compile(r"(?:^|\.)x\.com/")),
    ("twitter", re.compile(r"twitter\.com/")),
    ("facebook", re.compile(r"facebook\.com/")),
    ("instagram", re.compile(r"instagram\.com/")),
    ("youtube", re.compile(r"youtube\.com/")),
]

EXCLUDE_SOCIAL = re.compile(r"share|sharer|intent|hashtag|login|oauth|dialog|embed|feed|status", re.I)

EMAIL_PATTERNS = {
    "first.last": lambda f, l: f"{f}.{l}",
    "first_last": lambda f, l: f"{f}_{l}",
    "first-last": lambda f, l: f"{f}-{l}",
    "firstinitial.last": lambda f, l: f"{f[0]}.{l}",
    "firstinitiallast": lambda f, l: f"{f[0]}{l}",
    "firstlastinitial": lambda f, l: f"{f}{l[0]}",
    "first": lambda f, l: f"{f}",
    "last": lambda f, l: f"{l}",
    "last.first": lambda f, l: f"{l}.{f}",
}
PATTERN_ORDER = list(EMAIL_PATTERNS.keys())


@dataclass
class ScrapeResult:
    domain: str = ""
    status: str = "pending"          # ok | partial | failed
    message: str = ""
    base_url: str = ""
    pages_checked: int = 0
    emails: list[dict] = field(default_factory=list)
    phones: list[dict] = field(default_factory=list)
    socials: list[dict] = field(default_factory=list)
    people: list[dict] = field(default_factory=list)
    address: str | None = None


class WebScraper:
    def __init__(
        self,
        respect_robots: bool = True,
        delay: float = 1.0,
        max_pages: int = 10,
        derive_emails: bool = True,
        timeout: float = 20.0,
        proxies: list[str] | None = None,
    ):
        self.respect_robots = respect_robots
        self.delay = max(0.0, delay)
        self.max_pages = max(1, max_pages)
        self.derive_emails = derive_emails
        self.timeout = timeout
        self.proxies = proxies or []
        self._proxy_idx = 0
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._company_name = ""
        self._name_email_pairs: list[tuple[str, str]] = []
        self._pattern_evidence: dict[str, int] = {}

    def _next_proxy(self) -> str | None:
        if not self.proxies:
            return None
        p = self.proxies[self._proxy_idx % len(self.proxies)]
        self._proxy_idx += 1
        return p

    # ------------------------------------------------------------------ #
    def scrape(self, domain: str, company_name: str = "") -> ScrapeResult:
        domain = (domain or "").strip().lower().removeprefix("www.")
        self._company_name = (company_name or "").strip().lower()
        self._name_email_pairs = []
        self._pattern_evidence = {}
        result = ScrapeResult(domain=domain)
        if not domain:
            result.status = "failed"
            result.message = "No domain provided."
            return result

        client = httpx.Client(
            follow_redirects=True, timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
            proxy=self._next_proxy(),
        )
        try:
            base = self._resolve_base(client, domain)
            if not base:
                result.status = "failed"
                result.message = "Could not reach the website (DNS/connection failure)."
                return result
            result.base_url = base

            robots = self._robots(client, base)
            if robots is not None and not self._allowed(robots, base):
                result.status = "failed"
                result.message = "robots.txt disallows automated access to this site."
                return result

            pages = self._discover(client, base, robots)
            scraped_pages = 0
            for url in pages:
                if not self._allowed(robots, url):
                    continue
                html = self._fetch(client, url)
                if html is None:
                    continue
                scraped_pages += 1
                self._parse_page(html, url, result)
                if self.delay:
                    time.sleep(self.delay)

            self._finalize(result)

            result.pages_checked = scraped_pages
            if scraped_pages == 0:
                result.status = "failed"
                result.message = "Site reached but no pages could be fetched (may be bot-protected)."
            else:
                result.status = "ok" if (result.emails or result.phones or result.socials or result.people) else "partial"
                if result.status == "partial":
                    result.message = "Pages fetched but no contact details were published on them."
            return result
        except Exception as exc:  # pragma: no cover - defensive
            result.status = "failed"
            result.message = f"Scrape error: {type(exc).__name__}: {exc}"
            return result
        finally:
            client.close()

    # ------------------------------------------------------------------ #
    def _resolve_base(self, client: httpx.Client, domain: str) -> str | None:
        for candidate in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
            try:
                r = client.get(candidate)
                if r.status_code < 400:
                    return str(r.url).rstrip("/") or candidate
            except httpx.HTTPError:
                continue
        return None

    def _robots(self, client: httpx.Client, base: str) -> RobotFileParser | None:
        if not self.respect_robots:
            return None
        key = urlparse(base).netloc
        if key in self._robots_cache:
            return self._robots_cache[key]
        rp = RobotFileParser()
        rp.set_url(urljoin(base + "/", "/robots.txt"))
        try:
            r = client.get(urljoin(base + "/", "/robots.txt"))
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            elif r.status_code in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True
        except httpx.HTTPError:
            rp.allow_all = True
        self._robots_cache[key] = rp
        return rp

    @staticmethod
    def _allowed(robots: RobotFileParser | None, url: str) -> bool:
        if robots is None:
            return True
        try:
            return robots.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def _fetch(self, client: httpx.Client, url: str) -> str | None:
        try:
            r = client.get(url)
            if r.status_code >= 400:
                return None
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return None
            return r.text
        except httpx.HTTPError:
            return None

    def _discover(self, client: httpx.Client, base: str, robots) -> list[str]:
        urls: list[str] = [base + "/"]
        seen: set[str] = {base + "/"}

        # 0) sitemap discovery — finds leadership/team pages not linked on home
        for url in self._discover_sitemap(client, base):
            if url not in seen:
                seen.add(url)
                urls.append(url)
            if len(urls) >= self.max_pages:
                return urls[: self.max_pages]

        # 1) guess common leadership/about paths (most valuable for executives)
        for url in self._guess_pages(client, base):
            if url not in seen:
                seen.add(url)
                urls.append(url)
            if len(urls) >= self.max_pages:
                return urls[: self.max_pages]

        # 2) follow keyword links from the homepage
        homepage = self._fetch(client, base + "/")
        if homepage:
            soup = BeautifulSoup(homepage, "lxml")
            candidates: list[tuple[int, str]] = []
            for a in soup.find_all("a", href=True):
                href = urljoin(base + "/", a["href"].strip())
                if urlparse(href).netloc != urlparse(base).netloc:
                    continue
                href = href.split("#")[0].rstrip("/") + "/"
                path = urlparse(href).path.lower()
                # word-boundary match so "teams-evolve" ≠ "team" and
                # "fleet-management" ≠ "management".
                matched = [
                    k for k in LINK_KEYWORDS
                    if re.search(r"\b" + re.escape(k) + r"\b", path, re.IGNORECASE)
                ]
                if not matched:
                    continue
                score = min(LINK_PRIORITY.get(k, 9) for k in matched)
                if href not in seen:
                    seen.add(href)
                    candidates.append((score, href))
            candidates.sort(key=lambda x: (x[0], x[1]))
            for _, url in candidates:
                if len(urls) >= self.max_pages:
                    break
                urls.append(url)
        return urls[: self.max_pages]

    def _discover_sitemap(self, client: httpx.Client, base: str) -> list[str]:
        """Fetch sitemap.xml and return high-value people pages (leadership/
        team/board/about) not necessarily linked from the homepage."""
        try:
            sm = self._fetch(client, urljoin(base + "/", "/sitemap.xml"))
            if sm is None:
                return []
            soup = BeautifulSoup(sm, "lxml")
            locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")][:500]
            if not locs:
                return []
            scored: list[tuple[int, str]] = []
            for loc in locs:
                path = urlparse(loc).path.lower()
                if not path or path == "/":
                    continue
                if any(k in path for k in ("wp-content", "wp-json", "cart",
                                            "checkout", "tag/", "category/",
                                            "author/", ".xml", "?s=")):
                    continue
                matched = [
                    k for k in ("leadership", "executive", "board", "our-team",
                                "team", "who-we-are", "about", "people", "founder")
                    if re.search(r"\b" + re.escape(k) + r"\b", path, re.IGNORECASE)
                ]
                if not matched:
                    continue
                score = min(LINK_PRIORITY.get(k, 9) for k in matched)
                scored.append((score, urljoin(base + "/", loc).split("#")[0]))
            scored.sort(key=lambda x: (x[0], x[1]))
            return [u for _, u in scored][:6]
        except Exception:
            return []

    def _guess_pages(self, client: httpx.Client, base: str) -> list[str]:
        """Probe common leadership/about paths (soft-404 aware)."""
        found: list[str] = []
        for suffix in GUESS_PATHS:
            if len(found) >= 3:
                break
            url = (base + suffix).rstrip("/") + "/"
            html = self._fetch(client, url)
            if html is None:
                continue
            soup = BeautifulSoup(html, "lxml")
            title = (soup.title.get_text(" ", strip=True).lower() if soup.title else "")
            if "not found" in title or "404" in title or "page not found" in title:
                continue
            found.append(url)
        return found

    # ------------------------------------------------------------------ #
    def _parse_page(self, html: str, url: str, result: ScrapeResult) -> None:
        soup = BeautifulSoup(html, "lxml")

        # --- emails ---------------------------------------------------- #
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                email = href[7:].split("?")[0].strip().lower()
                if self._valid_email(email):
                    result.emails.append(
                        {"email": email, "category": self._categorise(email), "source_url": url}
                    )
                    anchor = a.get_text(" ", strip=True)
                    if anchor and NAME_RE.fullmatch(anchor) and not self._name_is_stop(anchor):
                        self._name_email_pairs.append((anchor, email))
                    else:
                        # Anchor equals the address itself -> the local part
                        # reveals the naming convention (first.last etc.).
                        self._note_pattern_from_local(email, a)
        text = soup.get_text(" ", strip=True)
        for m in EMAIL_RE.findall(text):
            email = m.lower()
            if self._valid_email(email):
                result.emails.append(
                    {"email": email, "category": self._categorise(email), "source_url": url}
                )

        # "Name, email@domain" pairings -> reveals the company's email convention
        for m in NAME_EMAIL_PAIR_RE.finditer(text):
            name = m.group("name")
            email = m.group("email").lower()
            if not self._name_is_stop(name) and self._valid_email(email):
                self._name_email_pairs.append((name, email))

        # --- phones ---------------------------------------------------- #
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("tel:"):
                phone = href[4:].strip()
                if 7 <= sum(c.isdigit() for c in phone) <= 15:
                    result.phones.append({"phone": phone, "label": "Published", "source_url": url})
        for m in INTL_PHONE_RE.findall(text):
            if 7 <= sum(c.isdigit() for c in m) <= 15:
                result.phones.append({"phone": m.strip(), "label": "Published", "source_url": url})
        for m in US_PHONE_RE.findall(text):
            result.phones.append({"phone": m, "label": "Published", "source_url": url})

        # --- socials --------------------------------------------------- #
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if EXCLUDE_SOCIAL.search(href):
                continue
            for network, pattern in SOCIAL_PATTERNS:
                if pattern.search(href):
                    result.socials.append({"network": network, "url": href.split("#")[0]})
                    break

        # --- structured data ------------------------------------------ #
        self._parse_structured_data(soup, url, result)

        # --- decision makers: class-based leadership cards (any page) - #
        self._extract_people_structured(soup, url, result)

        # --- decision makers (only on leadership/team or news pages) -- #
        path = urlparse(url).path.lower()
        if PEOPLE_PAGE_RE.search(path):
            self._extract_people_cards(soup, url, result)
        if PRESS_PAGE_RE.search(path):
            self._extract_people_press(text, url, result)

    # ------------------------------------------------------------------ #
    def _parse_structured_data(self, soup: BeautifulSoup, url: str, result: ScrapeResult) -> None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text() or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for item in self._flatten(data):
                if not isinstance(item, dict):
                    continue
                itype = item.get("@type")
                if isinstance(itype, list):
                    itype = next((t for t in itype if isinstance(t, str)), None)
                if itype == "Person":
                    name = self._first_str(item.get("name"))
                    title = self._first_str(item.get("jobTitle"))
                    email = self._first_str(item.get("email"))
                    phone = self._first_str(item.get("telephone"))
                    if name:
                        person = {
                            "name": str(name), "title": title or "",
                            "email": None, "email_status": None,
                            "phone": None, "phone_label": None,
                            "linkedin_url": None, "linkedin_type": None, "source_url": url,
                        }
                        if email and self._valid_email(str(email)):
                            person["email"] = str(email).lower()
                            person["email_status"] = "published"
                            self._name_email_pairs.append((str(name), str(email).lower()))
                        if phone and 7 <= sum(c.isdigit() for c in str(phone)) <= 15:
                            person["phone"] = str(phone)
                            person["phone_label"] = "Published"
                        for s in self._flatten(item.get("sameAs")):
                            if isinstance(s, str) and "linkedin.com/in/" in s:
                                person["linkedin_url"] = s.split("?")[0]
                                person["linkedin_type"] = "profile"
                                break
                        result.people.append(person)
                elif itype == "Organization":
                    email = self._first_str(item.get("email"))
                    phone = self._first_str(item.get("telephone"))
                    if email and self._valid_email(str(email)):
                        result.emails.append(
                            {"email": str(email).lower(), "category": self._categorise(str(email)), "source_url": url}
                        )
                    if phone:
                        result.phones.append({"phone": str(phone), "label": "Published", "source_url": url})
                    if not result.address:
                        result.address = self._extract_address(item)
                    for s in self._flatten(item.get("sameAs")):
                        if isinstance(s, str) and EXCLUDE_SOCIAL.search(s) is None:
                            for network, pattern in SOCIAL_PATTERNS:
                                if pattern.search(s):
                                    result.socials.append({"network": network, "url": s.split("#")[0]})
                                    break

        # microdata (schema.org/Person) --------------------------------- #
        for node in soup.find_all(itemtype=re.compile(r"schema\.org/Person")):
            name_el = node.find(itemprop="name")
            title_el = node.find(itemprop="jobTitle")
            if name_el and name_el.get_text(strip=True):
                phone_el = node.find(itemprop="telephone")
                email_el = node.find(itemprop="email")
                person = {
                    "name": name_el.get_text(strip=True),
                    "title": title_el.get_text(strip=True) if title_el else "",
                    "email": None, "email_status": None,
                    "phone": None, "phone_label": None,
                    "linkedin_url": None, "linkedin_type": None, "source_url": url,
                }
                if email_el and email_el.get_text(strip=True):
                    em = email_el.get_text(strip=True).lower()
                    if self._valid_email(em):
                        person["email"] = em
                        person["email_status"] = "published"
                if phone_el and phone_el.get_text(strip=True):
                    person["phone"] = phone_el.get_text(strip=True)
                    person["phone_label"] = "Published"
                result.people.append(person)

    # ------------------------------------------------------------------ #
    def _extract_people_cards(self, soup: BeautifulSoup, url: str, result: ScrapeResult) -> None:
        seen_texts: set[str] = set()
        tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "div", "strong", "b", "li", "figcaption", "dt", "dd"}
        for el in soup.find_all(list(tags)):
            txt = el.get_text(" ", strip=True)
            if not txt or len(txt) > 90 or txt in seen_texts:
                continue
            seen_texts.add(txt)

            # Pattern A: "Name Title" in one text block ----------------- #
            name, role = self._split_name_role(txt)
            if name and role and not self._name_is_stop(name):
                person = {"name": name, "title": role, "email": None, "email_status": None,
                          "phone": None, "phone_label": None,
                          "linkedin_url": None, "linkedin_type": None, "source_url": url}
                # a mailto inside the same card -> published executive email
                card_email = self._card_email(el)
                if card_email:
                    person["email"] = card_email
                    person["email_status"] = "published"
                    self._name_email_pairs.append((name, card_email))
                card_phone = self._card_phone(el)
                if card_phone:
                    person["phone"], person["phone_label"] = card_phone
                card_li = self._card_linkedin(el)
                if card_li:
                    person["linkedin_url"] = card_li
                    person["linkedin_type"] = "profile"
                result.people.append(person)
                continue

            # Pattern B: bare name, role in a close sibling ------------- #
            if len(txt) <= 40 and NAME_RE.fullmatch(txt) and not self._name_is_stop(txt):
                role = self._sibling_role(el)
                if role:
                    person = {"name": txt, "title": role, "email": None, "email_status": None,
                              "phone": None, "phone_label": None,
                              "linkedin_url": None, "linkedin_type": None, "source_url": url}
                    card_email = self._card_email(el)
                    if card_email:
                        person["email"] = card_email
                        person["email_status"] = "published"
                        self._name_email_pairs.append((txt, card_email))
                    card_phone = self._card_phone(el)
                    if card_phone:
                        person["phone"], person["phone_label"] = card_phone
                    card_li = self._card_linkedin(el)
                    if card_li:
                        person["linkedin_url"] = card_li
                        person["linkedin_type"] = "profile"
                    result.people.append(person)
                continue

            # Pattern C: "Title Name" reversed ("VP Global Fleet Solutions Brad Taylor") #
            name, role = self._split_reversed(txt)
            if name and role:
                person = {"name": name, "title": role, "email": None, "email_status": None,
                          "phone": None, "phone_label": None,
                          "linkedin_url": None, "linkedin_type": None, "source_url": url}
                card_email = self._card_email(el)
                if card_email:
                    person["email"] = card_email
                    person["email_status"] = "published"
                    self._name_email_pairs.append((name, card_email))
                card_phone = self._card_phone(el)
                if card_phone:
                    person["phone"], person["phone_label"] = card_phone
                card_li = self._card_linkedin(el)
                if card_li:
                    person["linkedin_url"] = card_li
                    person["linkedin_type"] = "profile"
                result.people.append(person)

    @staticmethod
    def _split_name_role(txt: str) -> tuple[str | None, str | None]:
        """Split "Neil Cawse Founder and CEO" -> ("Neil Cawse", "Founder and CEO").

        Finds the FIRST title-word at index >= 1 and splits there, so multi-word
        titles like "Executive Vice President" are not mistaken for name parts.
        """
        words = WORD_TOKEN_RE.findall(txt)
        if len(words) < 3:
            return None, None
        for i in range(1, len(words)):
            if words[i].lower() in TITLE_WORDS:
                name_words = words[:i]
                if 2 <= len(name_words) <= 4:
                    name = " ".join(name_words)
                    # role = original text after the name, preserving "&" etc.
                    role = txt[len(name):].strip().lstrip("–—,;: ")
                    role = re.sub(r"\b[A-Za-z]\b\s*", "", role)  # drop stray 1-letter tokens
                    role = re.sub(r"\s+", " ", role).strip(" ,–—-")
                    if len(role) >= 3:
                        return name, role
                return None, None
        return None, None

    def _looks_like_name(self, name: str) -> bool:
        """A plausible person name: 2-4 Title-case words, no stopwords/digits.

        Internal capitals are allowed so names like "O'Meara", "McKay" and
        "DeVries" survive.
        """
        if not name or len(name) < 4 or len(name) > 40:
            return False
        tokens = name.split()
        if not (2 <= len(tokens) <= 4):
            return False
        for t in tokens:
            if t.lower() in NAME_STOP:
                return False
            if not re.fullmatch(r"[A-ZÀ-ÖØ-Þ\u0100-\u017f\u0180-\u024f][A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u017f\u0180-\u024f.'’\-]*", t):
                return False
        return True

    def _is_company_word(self, word: str) -> bool:
        """True if `word` is a token of the company's own name (e.g. "Uffizio")."""
        if not self._company_name:
            return False
        cwords = {
            w for w in self._company_name.replace("-", " ").replace("&", " ").split()
            if len(w) >= 3
        }
        return word.lower() in cwords

    def _split_reversed(self, txt: str) -> tuple[str | None, str | None]:
        """Split "Vice President, Global Fleet Solutions Brad Taylor"
        -> ("Brad Taylor", "Vice President, Global Fleet Solutions").

        The head must contain a leadership title word and the tail must look
        like a person's name. Honorifics ("Mr.") and the company's own name
        are stripped from the role. Two-word names are tried before three-word
        ones so "Sales Manager, National Accounts Christian Wales" yields
        ("Christian Wales", "Sales Manager, National Accounts").
        """
        words = WORD_TOKEN_RE.findall(txt)
        if len(words) < 4:
            return None, None
        for tail_len in (2, 3):
            for split in range(1, len(words) - tail_len + 1):
                head = words[:split]
                tail = words[split:split + tail_len]
                name = " ".join(tail)
                if not self._looks_like_name(name) or self._name_is_stop(name):
                    continue
                role_words = [
                    w for w in head
                    if w.lower() not in HONORIFICS and not self._is_company_word(w)
                ]
                if not role_words:
                    continue
                if not any(w.lower() in STRONG_TITLE_WORDS for w in role_words):
                    continue
                role = " ".join(role_words).strip(" ,–—-")
                if len(role) >= 3:
                    return name, role
        return None, None

    def _extract_people_structured(self, soup: BeautifulSoup, url: str, result: ScrapeResult) -> None:
        """Handle leadership-plugin card layouts via CSS class names.

        Covers patterns like WordPress "Leadership Module" (lm__member),
        Elementor team widgets, etc.:

          <div class="...member...">
            <div class="...name...">Brad Taylor</div>
            <div class="...role/title/position...">Vice President</div>
            <a href="linkedin.com/in/...">...</a>
          </div>

        Also merges LinkedIn profiles found in separate bio blocks (keyed by
        the person's name). Class-based, so it is precise and low-noise.
        """
        NAME_CLASS_RE = re.compile(r"(?:member|team|staff|person|leadership|bio)[\w-]*name", re.I)
        ROLE_CLASS_RE = re.compile(r"(?:member|team|staff|person|leadership|bio)[\w-]*(?:role|title|position|job)", re.I)

        # --- 1) member cards: name + role within the same card --------- #
        for name_el in soup.find_all(class_=NAME_CLASS_RE):
            name = name_el.get_text(" ", strip=True)
            if not self._looks_like_name(name) or self._name_is_stop(name):
                continue
            card = name_el
            found = False
            for _ in range(3):
                card = card.parent
                if card is None:
                    break
                role_el = card.find(class_=ROLE_CLASS_RE)
                if role_el is None:
                    continue
                role = role_el.get_text(" ", strip=True)
                if not role or len(role) > 90:
                    continue
                person = {"name": name, "title": role, "email": None, "email_status": None,
                          "phone": None, "phone_label": None,
                          "linkedin_url": None, "linkedin_type": None, "source_url": url}
                li = card.find("a", href=re.compile(r"linkedin\.com/in/", re.I))
                if li:
                    person["linkedin_url"] = li["href"].split("?")[0]
                    person["linkedin_type"] = "profile"
                em = card.find("a", href=re.compile(r"^mailto:", re.I))
                if em:
                    email = em["href"][7:].split("?")[0].strip().lower()
                    if self._valid_email(email):
                        person["email"] = email
                        person["email_status"] = "published"
                        self._name_email_pairs.append((name, email))
                ph = card.find("a", href=re.compile(r"^tel:", re.I))
                if ph:
                    phone = ph["href"][4:].strip()
                    if 7 <= sum(c.isdigit() for c in phone) <= 15:
                        person["phone"] = phone
                        person["phone_label"] = "Direct line"
                result.people.append(person)
                found = True
                break
            _ = found

        # --- 2) LinkedIn bio blocks keyed by name ---------------------- #
        bio_links: dict[str, str] = {}
        for a in soup.find_all("a", href=re.compile(r"linkedin\.com/in/", re.I)):
            node = a
            for _ in range(2):
                node = node.parent
                if node is None:
                    break
                name_el = node.find(class_=NAME_CLASS_RE)
                if name_el is None:
                    continue
                n = name_el.get_text(" ", strip=True)
                if self._looks_like_name(n) and not self._name_is_stop(n):
                    bio_links[n.lower()] = a["href"].split("?")[0]
                # stop regardless — going higher would grab another person's name
                break
        if bio_links:
            for person in result.people:
                if not person.get("linkedin_url") and person["name"].lower() in bio_links:
                    person["linkedin_url"] = bio_links[person["name"].lower()]
                    person["linkedin_type"] = "profile"

    def _note_pattern_from_local(self, email: str, a=None) -> None:
        """Infer the naming convention from a bare email's local part.

        Only counts person-like locals: two alphabetic tokens joined by '.',
        '_', '-'. Role/department/region tokens (sales, support, dach, emea,
        etc.) are excluded so they don't pollute the pattern inference.
        """
        local = email.split("@")[0].lower()
        tokens = re.findall(r"[a-z]{2,}", local)
        if len(tokens) != 2:
            return
        if any(t in ROLE_TOKENS for t in tokens):
            return
        if "." in local:
            self._pattern_evidence["first.last"] = self._pattern_evidence.get("first.last", 0) + 1
        elif "_" in local:
            self._pattern_evidence["first_last"] = self._pattern_evidence.get("first_last", 0) + 1
        elif "-" in local:
            self._pattern_evidence["first-last"] = self._pattern_evidence.get("first-last", 0) + 1

    def _card_phone(self, el) -> tuple[str, str] | None:
        """Find a tel: link inside the same card as a person."""
        for _ in range(4):
            el = el.parent
            if el is None:
                return None
            for a in el.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().startswith("tel:"):
                    phone = href[4:].strip()
                    if 7 <= sum(c.isdigit() for c in phone) <= 15:
                        label = a.get_text(" ", strip=True) or "Direct line"
                        return phone, label
        return None

    def _card_linkedin(self, el) -> str | None:
        """Find a personal LinkedIn profile link inside the same card."""
        for _ in range(4):
            el = el.parent
            if el is None:
                return None
            for a in el.find_all("a", href=True):
                href = a["href"].strip()
                if "linkedin.com/in/" in href:
                    return href.split("?")[0]
        return None

    def _card_email(self, el) -> str | None:
        for _ in range(4):
            el = el.parent
            if el is None:
                return None
            for a in el.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().startswith("mailto:"):
                    email = href[7:].split("?")[0].strip().lower()
                    if self._valid_email(email):
                        return email
        return None

    @staticmethod
    def _sibling_role(name_el):
        n = name_el.next_sibling
        for _ in range(2):
            while n is not None and getattr(n, "name", None) is None:
                n = n.next_sibling
            if n is None:
                return None
            txt = n.get_text(" ", strip=True)
            if txt and len(txt) <= 60 and ROLE_CHECK.match(txt):
                return txt
            n = n.next_sibling
        return None

    def _extract_people_press(self, text: str, url: str, result: ScrapeResult) -> None:
        for m in PRESS_RE.finditer(text):
            name = m.group("name")
            role = m.group("role")
            if self._name_is_stop(name):
                continue
            result.people.append(
                {"name": name, "title": role.strip(" ,"), "email": None, "email_status": None,
                 "phone": None, "phone_label": None,
                 "linkedin_url": None, "linkedin_type": None, "source_url": url}
            )
        for m in REVERSED_PRESS_RE.finditer(text):
            name = m.group("name")
            role = m.group("role")
            if self._name_is_stop(name) or not self._looks_like_name(name):
                continue
            result.people.append(
                {"name": name, "title": role.strip(" ,"), "email": None, "email_status": None,
                 "phone": None, "phone_label": None,
                 "linkedin_url": None, "linkedin_type": None, "source_url": url}
            )

    # ------------------------------------------------------------------ #
    def _finalize(self, result: ScrapeResult) -> None:
        """Dedupe, drop noise, and derive executive emails."""

        def _digits(s: str) -> str:
            return "".join(c for c in s if c.isdigit())

        emails, seen = [], set()
        for e in result.emails:
            if e["email"] in seen:
                continue
            seen.add(e["email"])
            emails.append(e)
        result.emails = emails

        phones, seen_phones = [], set()
        for p in result.phones:
            d = _digits(p["phone"])
            if not d or d in seen_phones:
                continue
            seen_phones.add(d)
            phones.append(p)
        result.phones = phones

        socials, seen_soc = [], set()
        for s in result.socials:
            key = (s["network"], s["url"].split("?")[0])
            if key in seen_soc:
                continue
            seen_soc.add(key)
            socials.append(s)
        result.socials = socials

        people, seen_ppl = [], set()
        for p in result.people:
            name = p.get("name", "").strip()
            if self._name_is_stop(name):
                continue
            if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u017f\u0180-\u024f][A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u017f\u0180-\u024f.'’\- ]+", name):
                continue
            if re.search(r"\d", name):
                continue
            tokens = name.split()
            if len(tokens) < 2 or len(tokens) > 4:
                continue
            # a title word can never be a person-name word ("Chief Financial Officer")
            if any(t.lower() in TITLE_WORDS for t in tokens):
                continue
            # duplicated names from stacked mobile/desktop cards
            if any(tokens[i].lower() == tokens[i + 1].lower() for i in range(len(tokens) - 1)):
                continue
            # "First Last First Last" repetition
            if len(tokens) == 4 and tokens[0].lower() == tokens[2].lower() and tokens[1].lower() == tokens[3].lower():
                continue
            if self._company_name and (
                name.lower() == self._company_name or name.lower() in self._company_name.split()
            ):
                continue
            title = (p.get("title") or "").strip().strip(", ")
            title = re.sub(
                r"\s*(more|view|read more|learn more|biography|bio|details|profile|website|follow)\s*$",
                "", title, flags=re.IGNORECASE,
            ).strip(" ,–—-")
            title = re.sub(r"^(?:the|he|she|a|an|and|&|of)\s+", "", title, flags=re.IGNORECASE)
            if not title and not p.get("email"):
                continue
            if any(b in title.lower() for b in TITLE_BLOCKLIST):
                continue
            if self._name_is_company(name):
                continue
            low = name.lower()
            if low in seen_ppl:
                continue
            seen_ppl.add(low)
            p["name"] = html.unescape(name)
            p["title"] = html.unescape(title)
            people.append(p)
        result.people = people[:60]

        # --- derive executive emails from the company's own format ----- #
        if self.derive_emails:
            # merge name↔email pair evidence into the pattern tally
            for name, email in self._name_email_pairs:
                tokens = name.split()
                if len(tokens) < 2:
                    continue
                first, last = tokens[0].lower(), tokens[-1].lower()
                if len(first) < 2 or len(last) < 2:
                    continue
                local = email.split("@")[0].lower().split("+")[0]
                for pat in PATTERN_ORDER:
                    if EMAIL_PATTERNS[pat](first, last) == local:
                        self._pattern_evidence[pat] = self._pattern_evidence.get(pat, 0) + 1
                        break

            pattern = self._pick_pattern(self._pattern_evidence)
            if pattern is None:
                pattern = "first.last"  # most common corporate convention
            mail_domain = self._mail_domain(result) or result.domain
            published = {e["email"] for e in result.emails}
            for person in result.people:
                if person.get("email"):
                    continue
                tokens = person["name"].split()
                if len(tokens) < 2:
                    continue
                first = self._ascii(tokens[0]).lower()
                last = self._ascii(tokens[-1]).lower()
                if len(first) < 2 or len(last) < 2:
                    continue
                local = EMAIL_PATTERNS[pattern](first, last)
                email = f"{local}@{mail_domain}"
                if email in published or not self._valid_email(email):
                    continue
                person["email"] = email
                person["email_status"] = "pattern-derived"

    @staticmethod
    def _ascii(s: str) -> str:
        """Fold accents so 'José' -> 'jose' for email local-parts."""
        import unicodedata

        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return s

    @staticmethod
    def _pick_pattern(evidence: dict[str, int]) -> str | None:
        if not evidence:
            return None
        return max(evidence, key=lambda p: (evidence[p], -PATTERN_ORDER.index(p)))

    @staticmethod
    def _mail_domain(result: ScrapeResult) -> str | None:
        counts: dict[str, int] = {}
        for e in result.emails:
            d = e["email"].split("@")[-1]
            counts[d] = counts.get(d, 0) + 1
        if not counts:
            return None
        return max(counts, key=counts.get)

    @staticmethod
    def _name_is_stop(name: str) -> bool:
        if not name or len(name) < 3:
            return True
        return any(tok.lower() in NAME_STOP for tok in name.split())

    def _name_is_company(self, name: str) -> bool:
        """Reject names that are actually the company/brand name."""
        if not self._company_name:
            return False
        cwords = {w for w in self._company_name.replace("-", " ").split() if len(w) >= 3}
        return any(tok.lower() in cwords for tok in name.split())

    # ------------------------------------------------------------------ #
    @staticmethod
    def _flatten(data):
        if isinstance(data, list):
            for item in data:
                yield from WebScraper._flatten(item)
        elif isinstance(data, dict):
            yield data
            for v in data.values():
                yield from WebScraper._flatten(v)

    @staticmethod
    def _first_str(value):
        if isinstance(value, list):
            return next((v for v in value if isinstance(v, str)), None)
        if isinstance(value, dict):
            return value.get("name") or value.get("email") or value.get("telephone")
        return value if isinstance(value, str) else None

    @staticmethod
    def _extract_address(item: dict) -> str | None:
        addr = item.get("address") or item.get("location")
        if isinstance(addr, str):
            return addr
        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress"), addr.get("addressLocality"),
                addr.get("addressRegion"), addr.get("postalCode"),
                addr.get("addressCountry"),
            ]
            return ", ".join(p for p in parts if p) or None
        return None

    @staticmethod
    def _valid_email(email: str) -> bool:
        if not email or ".." in email or email.startswith("."):
            return False
        if email.count("@") != 1:
            return False
        local, _, domain = email.partition("@")
        if not local or not domain or domain.startswith(".") or domain.endswith("."):
            return False
        if not re.fullmatch(r"[A-Za-z0-9._%+\-]+", local):
            return False
        if not re.fullmatch(r"[A-Za-z0-9.\-]+", domain):
            return False
        tld = domain.rsplit(".", 1)[-1]
        if tld in {"uk", "au", "in", "nz", "jp", "br", "mx", "za", "tr"}:
            tld = domain.rsplit(".", 2)[-2] + "." + tld if domain.count(".") >= 2 else tld
        return tld in KNOWN_TLDS

    @staticmethod
    def _categorise(email: str) -> str:
        local = email.split("@")[0].lower()
        if any(k in local for k in ("sales", "business", "bd", "partners", "partnership", "marketing", "bizdev")):
            return "Sales"
        if any(k in local for k in ("support", "help", "service", "care", "customerservice", "servicedesk")):
            return "Support"
        if any(k in local for k in ("career", "hr", "jobs", "hiring", "recruit", "people", "talent")):
            return "Careers"
        if any(k in local for k in ("billing", "account", "finance", "invoice", "accounts")):
            return "Billing"
        if any(k in local for k in ("info", "contact", "hello", "office", "general", "enquir", "inquiry")):
            return "General"
        return "General"
