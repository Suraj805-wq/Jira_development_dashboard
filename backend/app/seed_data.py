"""Curated directory of real fleet-management / telematics organisations.

Each entry: (name, domain, country, country_code, city, category, employees, founded)
Contacts are NOT stored here — they are produced by the enrichment layer
(real APIs when keys are configured, or the clearly-labelled demo generator).
"""

CATEGORIES = [
    "Fleet Management Software",
    "GPS Tracking / Telematics",
    "Video Telematics / Dashcam",
    "ELD & Compliance",
    "Asset & Cargo Tracking",
    "Fleet Maintenance",
    "Field Service Management",
    "Transportation Management (TMS)",
]

# name, domain, country, code, city, category, employees, founded
COMPANIES = [
    # ---------- United States ----------
    ("Samsara", "samsara.com", "United States", "US", "San Francisco, CA", "Fleet Management Software", 3000, 2015),
    ("Motive", "gomotive.com", "United States", "US", "San Francisco, CA", "Fleet Management Software", 3200, 2013),
    ("Verizon Connect", "verizonconnect.com", "United States", "US", "Atlanta, GA", "Fleet Management Software", 4000, 2018),
    ("Teletrac Navman", "teletracnavman.com", "United States", "US", "Garden Grove, CA", "GPS Tracking / Telematics", 900, 1988),
    ("Omnitracs (Solera Fleet)", "omnitracs.com", "United States", "US", "Dallas, TX", "Fleet Management Software", 1800, 1988),
    ("GPS Insight", "gpsinsight.com", "United States", "US", "Scottsdale, AZ", "GPS Tracking / Telematics", 500, 2004),
    ("Azuga", "azuga.com", "United States", "US", "San Jose, CA", "GPS Tracking / Telematics", 300, 2013),
    ("Zonar Systems", "zonarsystems.com", "United States", "US", "Seattle, WA", "Fleet Management Software", 500, 2001),
    ("Lytx", "lytx.com", "United States", "US", "San Diego, CA", "Video Telematics / Dashcam", 1200, 1998),
    ("Netradyne", "netradyne.com", "United States", "US", "San Diego, CA", "Video Telematics / Dashcam", 800, 2015),
    ("ORBCOMM", "orbcomm.com", "United States", "US", "Rochelle Park, NJ", "Asset & Cargo Tracking", 1000, 1993),
    ("CalAmp", "calamp.com", "United States", "US", "Irvine, CA", "GPS Tracking / Telematics", 800, 1981),
    ("Spireon", "spireon.com", "United States", "US", "Irvine, CA", "Asset & Cargo Tracking", 700, 2002),
    ("Fleetio", "fleetio.com", "United States", "US", "Birmingham, AL", "Fleet Maintenance", 400, 2012),
    ("Whip Around", "whiparound.com", "United States", "US", "Charlotte, NC", "Fleet Maintenance", 150, 2016),
    ("Transflo", "transflo.com", "United States", "US", "Tampa, FL", "ELD & Compliance", 400, 1991),
    ("PowerFleet", "powerfleet.com", "United States", "US", "Woodcliff Lake, NJ", "Asset & Cargo Tracking", 600, 1993),
    ("ClearPathGPS", "clearpathgps.com", "United States", "US", "Santa Barbara, CA", "GPS Tracking / Telematics", 60, 2013),
    ("GPS Trackit", "gpstrackit.com", "United States", "US", "Marietta, GA", "GPS Tracking / Telematics", 200, 2001),
    ("Trimble Transportation", "trimble.com", "United States", "US", "Westminster, CO", "Transportation Management (TMS)", 3000, 1978),
    ("Fleet Complete", "fleetcomplete.com", "United States", "US", "Atlanta, GA", "Fleet Management Software", 800, 2000),

    # ---------- Canada ----------
    ("Geotab", "geotab.com", "Canada", "CA", "Oakville, ON", "Fleet Management Software", 1000, 2000),
    ("GoFleet", "gofleet.ca", "Canada", "CA", "Mississauga, ON", "GPS Tracking / Telematics", 120, 2009),
    ("Titan GPS", "titangps.com", "Canada", "CA", "Edmonton, AB", "GPS Tracking / Telematics", 100, 2006),
    ("ISAAC Instruments", "isaacinstruments.com", "Canada", "CA", "Saint-Bruno, QC", "ELD & Compliance", 400, 1999),
    ("AttriX Technologies", "attrix.ca", "Canada", "CA", "Sherbrooke, QC", "Fleet Management Software", 90, 2010),

    # ---------- United Kingdom ----------
    ("Quartix", "quartix.com", "United Kingdom", "GB", "Newtown, Wales", "GPS Tracking / Telematics", 350, 2001),
    ("Trakm8", "trakm8.com", "United Kingdom", "GB", "Coleshill", "GPS Tracking / Telematics", 200, 2002),
    ("Microlise", "microlise.com", "United Kingdom", "GB", "Nottingham", "Fleet Management Software", 600, 1982),
    ("Lightfoot", "lightfoot.co.uk", "United Kingdom", "GB", "Exeter", "Video Telematics / Dashcam", 150, 2013),
    ("Crystal Ball", "crystalball.tv", "United Kingdom", "GB", "Manchester", "GPS Tracking / Telematics", 120, 2004),
    ("BigChange", "bigchange.com", "United Kingdom", "GB", "Leeds", "Field Service Management", 300, 2013),
    ("Radius Telematics", "radius.com", "United Kingdom", "GB", "Crewe", "Fleet Management Software", 3000, 1990),
    ("RAM Tracking", "ramtracking.com", "United Kingdom", "GB", "Leeds", "GPS Tracking / Telematics", 200, 2004),
    ("VisionTrack", "visiontrack.com", "United Kingdom", "GB", "Dartford", "Video Telematics / Dashcam", 100, 2013),

    # ---------- Netherlands / Belgium ----------
    ("Webfleet (Bridgestone)", "webfleet.com", "Netherlands", "NL", "Amsterdam", "Fleet Management Software", 800, 1991),
    ("Simacan", "simacan.com", "Netherlands", "NL", "Amersfoort", "Transportation Management (TMS)", 60, 2013),
    ("Be-Mobile", "be-mobile.be", "Belgium", "BE", "Ghent", "Transportation Management (TMS)", 300, 2006),
    ("Transics", "transics.com", "Belgium", "BE", "Ypres", "Fleet Management Software", 200, 1991),
    ("Astrata", "astrata.eu", "Belgium", "BE", "Leuven", "Transportation Management (TMS)", 200, 2000),

    # ---------- Germany ----------
    ("Fleetboard (Daimler Truck)", "fleetboard.com", "Germany", "DE", "Stuttgart", "Fleet Management Software", 200, 2000),
    ("Carano", "carano.de", "Germany", "DE", "Berlin", "Fleet Management Software", 100, 2000),
    ("Schmitz Cargobull Telematics", "cargobull.com", "Germany", "DE", "Münster", "Asset & Cargo Tracking", 300, 2004),
    ("Idem Telematics", "idemtelematics.com", "Germany", "DE", "Munich", "Fleet Management Software", 80, 2015),

    # ---------- Nordics ----------
    ("ABAX", "abax.com", "Norway", "NO", "Larvik", "GPS Tracking / Telematics", 600, 2003),
    ("Trackunit", "trackunit.com", "Denmark", "DK", "Aalborg", "Asset & Cargo Tracking", 400, 2005),
    ("AddSecure", "addsecure.com", "Sweden", "SE", "Stockholm", "GPS Tracking / Telematics", 800, 1995),

    # ---------- Baltics / Poland ----------
    ("Ruptela", "ruptela.com", "Lithuania", "LT", "Vilnius", "GPS Tracking / Telematics", 250, 2007),
    ("Teltonika Telematics", "teltonika-gps.com", "Lithuania", "LT", "Vilnius", "GPS Tracking / Telematics", 2000, 2007),
    ("Gurtam (Wialon)", "gurtam.com", "Lithuania", "LT", "Vilnius", "Fleet Management Software", 400, 2002),
    ("Mapon", "mapon.com", "Latvia", "LV", "Riga", "GPS Tracking / Telematics", 100, 2006),

    # ---------- Turkey ----------
    ("Arvento Mobile Systems", "arvento.com", "Turkey", "TR", "Ankara", "GPS Tracking / Telematics", 150, 2004),

    # ---------- Israel ----------
    ("Ituran", "ituran.com", "Israel", "IL", "Azor", "GPS Tracking / Telematics", 2500, 1994),
    ("Traffilog", "traffilog.com", "Israel", "IL", "Hod HaSharon", "Fleet Management Software", 150, 2004),

    # ---------- South Africa ----------
    ("MiX Telematics", "mixtelematics.com", "South Africa", "ZA", "Johannesburg", "Fleet Management Software", 1000, 1996),
    ("Cartrack", "cartrack.com", "South Africa", "ZA", "Johannesburg", "Fleet Management Software", 3000, 2004),
    ("Netstar", "netstar.co.za", "South Africa", "ZA", "Midrand", "GPS Tracking / Telematics", 1500, 1994),
    ("Tracker Connect", "tracker.co.za", "South Africa", "ZA", "Johannesburg", "GPS Tracking / Telematics", 1200, 1996),
    ("Ctrack (Inseego)", "ctrack.com", "South Africa", "ZA", "Centurion", "GPS Tracking / Telematics", 800, 1985),

    # ---------- India ----------
    ("Uffizio", "uffizio.com", "India", "IN", "Surat, Gujarat", "Fleet Management Software", 300, 2010),
    ("LocoNav", "loconav.com", "India", "IN", "Gurugram, Haryana", "Fleet Management Software", 200, 2016),
    ("Fleetx", "fleetx.io", "India", "IN", "Gurugram, Haryana", "Fleet Management Software", 300, 2018),
    ("Sensel Telematics", "senseltelematics.com", "India", "IN", "Mumbai, Maharashtra", "GPS Tracking / Telematics", 200, 2006),
    ("Arya Omnitalk", "aryaomnitalk.com", "India", "IN", "Pune, Maharashtra", "GPS Tracking / Telematics", 500, 2005),
    ("GPS Renew", "gpsrenew.com", "India", "IN", "Mumbai, Maharashtra", "GPS Tracking / Telematics", 100, 2016),
    ("Onelap Telematics", "onelap.in", "India", "IN", "Surat, Gujarat", "GPS Tracking / Telematics", 80, 2017),
    ("MapmyIndia (Mappls)", "mappls.com", "India", "IN", "New Delhi", "Fleet Management Software", 800, 1995),
    ("Intangles", "intangles.com", "India", "IN", "Pune, Maharashtra", "Fleet Management Software", 200, 2016),
    ("iTriangle", "itriangle.in", "India", "IN", "Bengaluru, Karnataka", "GPS Tracking / Telematics", 150, 2014),
    ("Letstrack", "letstrack.in", "India", "IN", "New Delhi", "GPS Tracking / Telematics", 100, 2016),
    ("Fleetable", "fleetable.in", "India", "IN", "Ahmedabad, Gujarat", "Fleet Management Software", 60, 2018),
    ("Trak N Tell", "trakntell.com", "India", "IN", "Gurugram, Haryana", "GPS Tracking / Telematics", 100, 2015),

    # ---------- UAE / GCC ----------
    ("Fleetroot", "fleetroot.com", "United Arab Emirates", "AE", "Dubai", "Fleet Management Software", 150, 2017),
    ("SecureTech", "securetech.ae", "United Arab Emirates", "AE", "Abu Dhabi", "GPS Tracking / Telematics", 300, 2000),
    ("Naizak Global Engineering", "naizak.com", "Saudi Arabia", "SA", "Al Khobar", "GPS Tracking / Telematics", 200, 2002),

    # ---------- Asia Pacific ----------
    ("Overdrive IoT", "overdrive.sg", "Singapore", "SG", "Singapore", "GPS Tracking / Telematics", 80, 2000),
    ("EROAD", "eroad.com", "New Zealand", "NZ", "Auckland", "ELD & Compliance", 400, 2000),
    ("Smartrak", "smartrak.com", "New Zealand", "NZ", "Hamilton", "GPS Tracking / Telematics", 120, 2007),
    ("MTData", "mtdata.com.au", "Australia", "AU", "Melbourne, VIC", "Fleet Management Software", 200, 2003),

    # ---------- Latin America ----------
    ("Satrack", "satrack.com", "Colombia", "CO", "Bogotá", "GPS Tracking / Telematics", 400, 1999),
    ("Sascar (Michelin)", "sascar.com.br", "Brazil", "BR", "São Paulo", "GPS Tracking / Telematics", 1000, 2000),
    ("Maxtrack", "maxtrack.com.br", "Brazil", "BR", "Contagem, MG", "GPS Tracking / Telematics", 300, 2003),
    ("Omnilink", "omnilink.com.br", "Brazil", "BR", "São Paulo", "Fleet Management Software", 200, 2005),
    ("Autotrac", "autotrac.com.br", "Brazil", "BR", "Brasília, DF", "Fleet Management Software", 500, 1994),
    ("Onixsat", "onixsat.com.br", "Brazil", "BR", "Londrina, PR", "GPS Tracking / Telematics", 90, 2004),

    # ---------- France / Iberia ----------
    ("Masternaut (Michelin)", "masternaut.com", "France", "FR", "Paris", "Fleet Management Software", 300, 1996),
    ("Frotcom", "frotcom.com", "Portugal", "PT", "Lisbon", "Fleet Management Software", 300, 1998),

    # ---------- Italy ----------
    ("Targa Telematics", "targatelematics.com", "Italy", "IT", "Treviso", "Fleet Management Software", 300, 2011),
    ("Octo Telematics", "octotelematics.com", "Italy", "IT", "Rome", "GPS Tracking / Telematics", 500, 2002),
    ("Viasat Group", "viasatgroup.it", "Italy", "IT", "Rome", "GPS Tracking / Telematics", 700, 2004),

    # ---------- Japan ----------
    ("Soracom", "soracom.io", "Japan", "JP", "Tokyo", "GPS Tracking / Telematics", 300, 2015),

    # ---------- South Korea ----------
    ("Samsung SDS", "samsungsds.com", "South Korea", "KR", "Seoul", "Transportation Management (TMS)", 13000, 1985),
    ("AUTOCRYPT", "autocrypt.io", "South Korea", "KR", "Seoul", "GPS Tracking / Telematics", 200, 2019),

    # ---------- China ----------
    ("Concox", "concox.com", "China", "CN", "Shenzhen, Guangdong", "GPS Tracking / Telematics", 800, 2008),
    ("Meitrack", "meitrack.com", "China", "CN", "Shenzhen, Guangdong", "GPS Tracking / Telematics", 500, 2002),
    ("Queclink", "queclink.com", "China", "CN", "Shanghai", "GPS Tracking / Telematics", 400, 2009),
    ("Jimi IoT", "jimiiot.com", "China", "CN", "Shenzhen, Guangdong", "GPS Tracking / Telematics", 300, 2010),

    # ---------- Southeast Asia ----------
    ("KATSANA", "katsana.com", "Malaysia", "MY", "Kuala Lumpur", "Fleet Management Software", 120, 2015),
    ("Bosnet", "bosnet.id", "Indonesia", "ID", "Jakarta", "Fleet Management Software", 200, 2009),

    # ---------- Finland / Czech / Switzerland / Ireland ----------
    ("Aplicom", "aplicom.com", "Finland", "FI", "Jyvaskyla", "GPS Tracking / Telematics", 100, 1990),
    ("Sherlog Technology", "sherlog.cz", "Czech Republic", "CZ", "Prague", "Fleet Management Software", 150, 2005),
    ("ContGuard", "contguard.com", "Switzerland", "CH", "Baar", "Asset & Cargo Tracking", 80, 2016),
    ("Cubic Telecom", "cubictelecom.com", "Ireland", "IE", "Dublin", "GPS Tracking / Telematics", 300, 2009),

    # ---------- Latin America ----------
    ("Sitrack", "sitrack.com", "Mexico", "MX", "Guadalajara", "GPS Tracking / Telematics", 300, 2002),
    ("Wisetrack", "wisetrack.com", "Chile", "CL", "Santiago", "GPS Tracking / Telematics", 150, 2003),

    # ---------- Australia ----------
    ("Digital Matter", "digitalmatter.com", "Australia", "AU", "Brisbane, QLD", "GPS Tracking / Telematics", 100, 2001),

    # ---------- More United States ----------
    ("Geoforce", "geoforce.com", "United States", "US", "Addison, TX", "Asset & Cargo Tracking", 250, 2007),
    ("SmartWitness", "smartwitness.com", "United States", "US", "Itasca, IL", "Video Telematics / Dashcam", 200, 2007),
    ("Xirgo Technologies", "xirgo.com", "United States", "US", "Camarillo, CA", "GPS Tracking / Telematics", 150, 2006),
    ("Danlaw", "danlawinc.com", "United States", "US", "Novi, MI", "GPS Tracking / Telematics", 500, 1984),
    ("Linxup", "linxup.com", "United States", "US", "St. Louis, MO", "GPS Tracking / Telematics", 120, 2004),
    ("Rhino Fleet Tracking", "rhinofleettracking.com", "United States", "US", "Alpharetta, GA", "GPS Tracking / Telematics", 60, 2010),
    ("Track Your Truck", "trackyourtruck.com", "United States", "US", "Carrollton, TX", "GPS Tracking / Telematics", 60, 2006),
    ("One Step GPS", "onestepgps.com", "United States", "US", "Santa Clarita, CA", "GPS Tracking / Telematics", 80, 2017),
    ("Bouncie", "bouncie.com", "United States", "US", "Dallas, TX", "GPS Tracking / Telematics", 100, 2014),

    # ---------- More United Kingdom ----------
    ("Movolytics", "movolytics.com", "United Kingdom", "GB", "Cambridge", "Fleet Management Software", 60, 2016),
    ("FleetCheck", "fleetcheck.co.uk", "United Kingdom", "GB", "Kemble", "Fleet Maintenance", 50, 2005),

    # ---------- Spain ----------
    ("LiveLink Motor", "livelinkmotor.com", "Spain", "ES", "Madrid", "GPS Tracking / Telematics", 60, 2018),
    ("LoJack Iberia", "lojackiberia.com", "Spain", "ES", "Valladolid", "GPS Tracking / Telematics", 200, 2021),
    ("GlobalAVL", "globalavl.com", "Spain", "ES", "Girona", "GPS Tracking / Telematics", 60, 2003),
    ("Grup Eina", "grupeina.com", "Spain", "ES", "Figueres", "GPS Tracking / Telematics", 60, 2003),
    ("IMS Telematics", "imstelematics.com", "Spain", "ES", "Valladolid", "GPS Tracking / Telematics", 30, 2019),
    ("Movildata", "movildata.com", "Spain", "ES", "Barcelona", "GPS Tracking / Telematics", 50, 1999),
    ("Iberotrack", "iberotrack.com", "Spain", "ES", "Vilafranca del Penedès", "GPS Tracking / Telematics", 40, 2017),
    ("GMV", "gmv.com", "Spain", "ES", "Tres Cantos, Madrid", "Fleet Management Software", 3000, 1984),
    ("Track24", "track24.com", "Spain", "ES", "Madrid", "GPS Tracking / Telematics", 200, 2003),
    ("Gestracking", "gestracking.com", "Spain", "ES", "Coslada, Madrid", "GPS Tracking / Telematics", 50, 2007),
    ("Grupo Oesia", "grupooesia.com", "Spain", "ES", "Madrid", "GPS Tracking / Telematics", 3000, 1976),

    # ---------- UAE (more) ----------
    ("Location Solutions", "locationsolutions.com", "United Arab Emirates", "AE", "Dubai", "GPS Tracking / Telematics", 200, 2004),
    ("Trakker Middle East", "trakker.ae", "United Arab Emirates", "AE", "Dubai", "Fleet Management Software", 150, 2005),
    ("FMSi (Fleet Management Systems Intl)", "fms-intl.com", "United Arab Emirates", "AE", "Abu Dhabi", "Fleet Management Software", 100, 2003),
    ("Norconsult Telematics", "ntww.com", "United Arab Emirates", "AE", "Dubai", "GPS Tracking / Telematics", 150, 2000),

    # ---------- France (more) ----------
    ("Optimum Automotive", "optimumautomotive.com", "France", "FR", "Marseille", "Fleet Management Software", 200, 2015),
    ("CLS Mobilité (Novacom)", "novacom-services.com", "France", "FR", "Paris", "GPS Tracking / Telematics", 300, 2000),
    ("Synox", "synox.io", "France", "FR", "Montpellier", "GPS Tracking / Telematics", 150, 2005),

    # ---------- Saudi Arabia ----------
    ("Machinestalk", "machinestalk.com", "Saudi Arabia", "SA", "Riyadh", "GPS Tracking / Telematics", 150, 2015),

    # ---------- Italy (more) ----------
    ("Kiwitron", "kiwitron.com", "Italy", "IT", "Bologna", "Fleet Management Software", 100, 2015),

    # ---------- Australia (more) ----------
    ("Linxio", "linxio.com", "Australia", "AU", "Sydney, NSW", "Fleet Management Software", 60, 2014),
    ("Fleetcare", "fleetcare.com.au", "Australia", "AU", "Perth, WA", "Fleet Management Software", 300, 1998),
    ("IntelliTrac", "intellitrac.com.au", "Australia", "AU", "Melbourne, VIC", "GPS Tracking / Telematics", 100, 2005),

    # ---------- Poland ----------
    ("Inelo", "inelo.pl", "Poland", "PL", "Bielsko-Biala", "Fleet Management Software", 300, 2000),

    # ---------- Turkey (more) ----------
    ("Mobiliz", "mobiliz.com.tr", "Turkey", "TR", "Istanbul", "GPS Tracking / Telematics", 150, 2012),

    # ---------- Mexico (more) ----------
    ("Vigia Solutions", "vigiasolutions.com", "Mexico", "MX", "Monterrey", "GPS Tracking / Telematics", 100, 2015),
]

PHONE_CODES = {
    "US": "+1", "CA": "+1", "GB": "+44", "DE": "+49", "FR": "+33", "NL": "+31",
    "BE": "+32", "DK": "+45", "NO": "+47", "SE": "+46", "LT": "+370", "LV": "+371",
    "PL": "+48", "TR": "+90", "IL": "+972", "ZA": "+27", "IN": "+91", "AE": "+971",
    "SA": "+966", "SG": "+65", "AU": "+61", "NZ": "+64", "BR": "+55", "CO": "+57",
    "PT": "+351", "JP": "+81", "KR": "+82", "CN": "+86", "MY": "+60", "ID": "+62",
    "IT": "+39", "FI": "+358", "CZ": "+420", "CH": "+41", "IE": "+353", "MX": "+52",
    "CL": "+56", "ES": "+34",
}


def seed_companies() -> int:
    """Insert any missing companies (incremental, safe to call on every startup)."""
    from .database import get_conn

    conn = get_conn()
    inserted = 0
    try:
        for (name, domain, country, code, city, category, employees, founded) in COMPANIES:
            website = f"https://www.{domain}"
            linkedin = f"https://www.linkedin.com/company/{domain.split('.')[0]}"
            description = (
                f"{name} is a {category.lower()} provider headquartered in "
                f"{city}, {country}. Focused on fleet visibility, safety and "
                f"operational efficiency for logistics and field-service fleets."
            )
            cur = conn.execute(
                """INSERT OR IGNORE INTO companies
                   (name, domain, website, country, country_code, city, category,
                    description, employees, founded, linkedin_url, tags)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, domain, website, country, code, city, category,
                 description, employees, founded, linkedin, "fleet,telematics"),
            )
            inserted += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return inserted
