#!/usr/bin/env python3
"""
STUDIO SHIFT: build step
  python3 build.py            bake content.js into index-staging.html (+ SEO block, llms.txt)
  python3 build.py --publish  also regenerate index.html from index-staging.html

Why: the site fills its text from content.js with JavaScript, and most AI crawlers
do not run JavaScript. Baking the same text into the HTML makes it readable to them.
The browser still re-fills everything from content.js, so editing content.js and
the ?edit mode keep working. Run this after every content.js change, before committing.
"""
import html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).parent
SITE = "https://studioshift.eu"
HOLD_BIOS = True   # keep the specialist bio popups off the live page until real bios exist


# ── 1. read content.js ──────────────────────────────────
def load_content():
    src = (ROOT / "content.js").read_text()
    src = src[src.index("const CONTENT = ") + len("const CONTENT = "):]
    src = src[: src.rindex("};") + 1]
    out, i, n = [], 0, len(src)
    while i < n:                                   # strip comments, keep strings intact
        c = src[i]
        if c == '"':
            j = i + 1
            while src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); i = j + 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n": i += 1
        elif src.startswith("/*", i):
            i = src.index("*/", i) + 2
        else:
            out.append(c); i += 1
    s = "".join(out)
    parts, i = [], 0                               # quote bare keys outside strings
    for m in re.finditer(r'"(?:[^"\\]|\\.)*"', s):
        parts.append(re.sub(r'([{,]\s*)([A-Za-z_]\w*)(\s*:)', r'\1"\2"\3', s[i:m.start()]))
        parts.append(m.group(0)); i = m.end()
    parts.append(re.sub(r'([{,]\s*)([A-Za-z_]\w*)(\s*:)', r'\1"\2"\3', s[i:]))
    s = re.sub(r',(\s*[}\]])', r'\1', "".join(parts))
    return json.loads(s)


C = load_content()


def plain(t):
    t = re.sub(r"<br\s*/?>", " ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\s+", " ", t).strip()


# ── 2. bake content into the page (mirrors injectContent in content.js) ──
def chips_html(items):
    return "".join(
        f'<span class="step-chip-sub">{i["sub"]}</span>' if isinstance(i, dict) and "sub" in i
        else f'<div class="step-chip">{i["chip"] if isinstance(i, dict) else i}</div>'
        for i in items)


def faq_html():
    cats = "".join(
        f'<button type="button" class="faq-cat{" active" if n == 0 else ""}" data-cat="{c["key"]}">{c["label"]}</button>'
        for n, c in enumerate(C["faq_categories"]))
    items = "".join(
        f'<details class="faq-item" data-cat="{i["cat"]}"><summary><span class="faq-q">{i["q"]}</span></summary>'
        f'<div class="faq-answer">{i["a"]}</div></details>' for i in C["faq_items"])
    return cats, items


def element_sub(page, attr, render):
    """Replace the inner HTML of every element carrying data-<attr>="key" (nested tags handled)."""
    open_re = re.compile(r'<(\w+)\b[^>]*\sdata-%s="(\w+)"[^>]*>' % attr)
    out, pos, count = [], 0, 0
    while True:
        m = open_re.search(page, pos)
        if not m:
            break
        tag, val = m.group(1), C.get(m.group(2))
        tok = re.compile(r'<(/?)%s\b[^>]*>' % tag)
        depth, end = 1, None
        for t in tok.finditer(page, m.end()):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                end = t; break
        if val is None or end is None:
            out.append(page[pos:m.end()]); pos = m.end(); continue
        out.append(page[pos:m.end()] + render(val)); pos = end.start(); count += 1
    out.append(page[pos:])
    return "".join(out), count


def bake(page):
    page, n1 = element_sub(page, "content", lambda v: v)
    page, n2 = element_sub(page, "chips", chips_html)
    page, n3 = element_sub(page, "tags", lambda v: "".join(f'<span class="team-tag">{t}</span>' for t in v))
    page, n4 = element_sub(page, "how-pills", lambda v: "".join(f'<span class="how-pill">{t}</span>' for t in v))
    page, n5 = element_sub(page, "ticker", lambda v: "".join(f'<span class="ticker-item">{t}</span>' for t in v))
    cats, items = faq_html()
    page = re.sub(r'(<div class="faq-cats" id="faqCats">).*?(</div>)', lambda m: m.group(1) + cats + m.group(2), page, count=1, flags=re.S)
    page = re.sub(r'(<div class="faq-list" id="faqList">).*?(</div>\s*</div>\s*</section>)',
                  lambda m: m.group(1) + items + m.group(2), page, count=1, flags=re.S)
    print(f"baked: {n1} text, {n2} chip lists, {n3} tag lists, {n4} pills, {n5} ticker, {len(C['faq_items'])} FAQ items")
    return page


# ── 3. SEO block: title, description, social tags, structured data ──
TITLE = "Studio SHIFT | Sustainability studio in Amsterdam: CSRD, PPWR, supply chain, circular design"
DESC = ("Studio SHIFT is an Amsterdam sustainability studio. Senior-led teams and a curated network of 25+ specialists "
        "turn strategy, EU regulation (CSRD, CSDDD, PPWR) and supply chain ambitions into working processes.")


def jsonld():
    services = []
    for n in range(1, 7):
        services.append({"@type": "Offer", "itemOffered": {
            "@type": "Service", "name": C[f"step{n}_title"], "description": plain(C[f"step{n}_desc"]),
            "provider": {"@id": SITE + "/#org"}}})
    people = []
    for n in (1, 2):
        people.append({"@type": "Person", "name": C[f"team{n}_name"],
                       "jobTitle": C[f"team{n}_role"].split("·")[0].strip(),
                       "description": plain(C[f"team{n}_bio"]),
                       "worksFor": {"@id": SITE + "/#org"}, "sameAs": [C[f"team{n}_linkedin"]]})
    org = {
        "@context": "https://schema.org", "@type": "ProfessionalService", "@id": SITE + "/#org",
        "name": "Studio SHIFT", "url": SITE + "/", "slogan": "Less talk, more SHIFT",
        "description": DESC, "email": "hello@studioshift.eu",
        "address": {"@type": "PostalAddress", "addressLocality": "Amsterdam", "addressCountry": "NL"},
        "areaServed": ["NL", "EU"],
        "identifier": {"@type": "PropertyValue", "propertyID": "KVK", "value": "42225087"},
        "founder": people,
        "knowsAbout": ["CSRD", "ESRS", "CSDDD", "PPWR", "ESPR", "Digital Product Passport", "EUDR", "EPR",
                       "Double materiality assessment", "GHG carbon accounting", "Science Based Targets",
                       "Human rights due diligence", "Circular design", "Life cycle assessment"],
        "hasOfferCatalog": {"@type": "OfferCatalog", "name": "What we do", "itemListElement": services},
    }
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": plain(i["q"]),
         "acceptedAnswer": {"@type": "Answer", "text": plain(re.sub(r"</li>", ". ", i["a"]))}}
        for i in C["faq_items"]]}
    return [org, faq]


def seo_block(staging):
    ld = "\n".join('<script type="application/ld+json">' + json.dumps(o, ensure_ascii=False) + "</script>" for o in jsonld())
    e = lambda t: html.escape(t, quote=True)
    lines = [
        "<!-- SEO:START (generated by build.py) -->",
        f"<title>{e(TITLE)}</title>",
        f'<meta name="description" content="{e(DESC)}">',
        f'<link rel="canonical" href="{SITE}/">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Studio SHIFT">',
        f'<meta property="og:title" content="{e(TITLE)}">',
        f'<meta property="og:description" content="{e(DESC)}">',
        f'<meta property="og:url" content="{SITE}/">',
        '<meta property="og:locale" content="en_GB">',
        f'<meta property="og:image" content="{SITE}/og-image.png">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="Studio SHIFT: Ambition into action. Sustainability studio in Amsterdam">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:image" content="{SITE}/og-image.png">',
        f'<meta name="twitter:title" content="{e(TITLE)}">',
        f'<meta name="twitter:description" content="{e(DESC)}">',
    ]
    if staging:
        lines.append('<meta name="robots" content="noindex, nofollow">')
    lines += [ld, "<!-- SEO:END -->"]
    return "\n".join(lines)


def apply_seo(page, staging):
    block = seo_block(staging)
    if "<!-- SEO:START" in page:
        return re.sub(r"<!-- SEO:START.*?<!-- SEO:END -->", lambda m: block, page, flags=re.S)
    page = re.sub(r"<title>.*?</title>\s*", "", page, count=1, flags=re.S)
    page = re.sub(r'<meta name="description"[^>]*>\s*', "", page, count=1)
    return page.replace('<meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
                        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' + block + "\n", 1)


# ── 4. llms.txt ─────────────────────────────────────────
def llms():
    L = ["# Studio SHIFT", "", f"> {DESC}", "",
         "Studio SHIFT designs and implements sustainability strategies for products, processes and supply chains, "
         "without the extensive slide decks. A senior sustainability professional leads every project and brings in "
         "specialists from a curated network of 25+ freelancers. Based in Amsterdam, working physically or remotely. "
         "Chamber of Commerce (KVK) 42225087.", "", "## What we do", ""]
    for n in range(1, 7):
        chips = ", ".join(i["sub"] if isinstance(i, dict) and "sub" in i else (i["chip"] if isinstance(i, dict) else i)
                          for i in C[f"step{n}_chips"])
        L.append(f"- **{C[f'step{n}_title']}**: {plain(C[f'step{n}_desc'])} ({chips})")
    L += ["", "## Questions and answers", ""]
    for i in C["faq_items"]:
        L += [f"### {plain(i['q'])}", plain(re.sub(r'</li>', '. ', i['a'])), ""]
    L += ["## Pages", "", f"- [Home]({SITE}/): services, team, specialists, FAQ, contact",
          f"- [For freelancers]({SITE}/freelancers.html): how specialists join the network", "",
          "## Contact", "", "- hello@studioshift.eu", "- Amsterdam, Netherlands"]
    return "\n".join(L) + "\n"


# ── 5. publish: index.html from index-staging.html ──────
def make_live(page):
    a, b = page.index("<!-- STAGING PASSWORD GATE -->"), page.index('<div id="scrollProgress"></div>')
    page = page[:a] + page[b:]
    page = page.replace('<script src="edit-mode.js"></script>\n', "")
    page = page.replace('<meta name="robots" content="noindex, nofollow">\n', "")
    if HOLD_BIOS:
        page = re.sub(r'\n\s*<div class="specialist-more">Read bio <i>\+</i></div>', "", page)
        a, b = page.index('<div class="bio-overlay"'), page.index('<script src="content.js"></script>')
        page = page[:a] + page[b:]
        a, b = page.index("// Specialist bios (click"), page.index("// FAQ (rendered")
        page = page[:a] + page[b:]
        a, b = page.index("/* Specialist bio: hover hint"), page.index("/* ── FAQ ── */")
        page = page[:a] + page[b:]
    return page


FL_TITLE = "Freelance with Studio SHIFT | Join our network of sustainability specialists"
FL_DESC = ("Join the Studio SHIFT freelance pool. Sustainability specialists working on real projects "
           "that create measurable impact, with senior oversight and fair rates.")


def fl_seo(page):
    e = lambda t: html.escape(t, quote=True)
    url = SITE + "/freelancers.html"
    block = "\n".join([
        "<!-- SEO:START (generated by build.py) -->",
        f"<title>{e(FL_TITLE)}</title>",
        f'<meta name="description" content="{e(FL_DESC)}">',
        f'<link rel="canonical" href="{url}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Studio SHIFT">',
        f'<meta property="og:title" content="{e(FL_TITLE)}">',
        f'<meta property="og:description" content="{e(FL_DESC)}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:image" content="{SITE}/og-image.png">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:image" content="{SITE}/og-image.png">',
        "<!-- SEO:END -->"])
    if "<!-- SEO:START" in page:
        return re.sub(r"<!-- SEO:START.*?<!-- SEO:END -->", lambda m: block, page, flags=re.S)
    page = re.sub(r"<title>.*?</title>\s*", "", page, count=1, flags=re.S)
    page = re.sub(r'<meta name="description"[^>]*>\s*', "", page, count=1)
    return page.replace('<meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
                        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' + block + "\n", 1)


if __name__ == "__main__":
    staging = (ROOT / "index-staging.html").read_text()
    staging = apply_seo(bake(staging), staging=True)
    (ROOT / "index-staging.html").write_text(staging)
    (ROOT / "llms.txt").write_text(llms())
    fl = fl_seo(bake((ROOT / "freelancers.html").read_text()))
    (ROOT / "freelancers.html").write_text(fl)
    if "--publish" in sys.argv:
        live = make_live(staging)
        live = apply_seo(live, staging=False)
        (ROOT / "index.html").write_text(live)
        print("index.html regenerated from index-staging.html")
    print("done")
