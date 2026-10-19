"""Parsing of a job *detail* page. No network / DB access here, so it can be
unit-tested with saved HTML.

Strategy (most reliable first):
1. schema.org JobPosting JSON-LD (many job boards embed it for Google Jobs).
2. Heading-based sections: find headings such as "Missions", "Profil",
   "Compétences" and take the content that follows them.
3. Fallback: the text of <main>/<article> as the description.

If recruteo.mg uses its own markup, adjust SECTION_KEYWORDS or add a
site-specific step in `parse_detail` once the real HTML has been inspected.
"""
import json
import re

from bs4 import BeautifulSoup

# keyword (lowercase, accents kept) -> target field
SECTION_KEYWORDS = {
    "missions": ("mission", "responsabilit", "tâches", "taches", "description du poste",
                 "description de l'offre", "descriptif", "vos missions", "role", "rôle"),
    "requirements": ("profil", "qualification", "exigence", "requirement", "prérequis",
                     "prerequis", "formation", "expérience", "experience", "niveau"),
    "skills": ("compétence", "competence", "skill", "savoir", "technologies",
               "outils", "maîtrise", "maitrise"),
}
HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]


def _clean(text: str) -> str:
    text = re.sub(r"[ \t\xa0]+", " ", text or "")
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _html_to_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment or "", "html.parser")
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all(["p", "div", "ul", "ol"]):
        p.append("\n")
    return _clean(soup.get_text())


def _as_lines(value) -> str:
    """JSON-LD fields may be a string, a list, or a dict with a 'name'."""
    if not value:
        return ""
    if isinstance(value, str):
        parts = re.split(r"[\n,;]+", _html_to_text(value))
    elif isinstance(value, dict):
        parts = [str(value.get("name") or value.get("description") or "")]
    else:
        parts = [_as_lines(v) for v in value]
    return "\n".join(p.strip() for p in parts if p and p.strip())


def _find_jobposting(soup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "@graph" in item:
                    stack.extend(item["@graph"])
                t = item.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return item
    return None


def _sections_from_headings(soup) -> dict:
    found = {}
    for heading in soup.find_all(HEADING_TAGS):
        title = heading.get_text(" ", strip=True).lower()
        if not title or len(title) > 80:
            continue
        field = next(
            (f for f, kws in SECTION_KEYWORDS.items() if any(k in title for k in kws)),
            None,
        )
        if not field or field in found:
            continue
        chunks = []
        for sib in heading.find_next_siblings():
            if sib.name in HEADING_TAGS:
                break
            chunks.append(str(sib))
        text = _html_to_text("".join(chunks))
        if text:
            found[field] = text
    return found


def parse_detail(html: str) -> dict:
    """Return {'description','missions','requirements','skills'} (strings,
    possibly empty). `skills` is one skill per line."""
    soup = BeautifulSoup(html, "html.parser")
    out = {"description": "", "missions": "", "requirements": "", "skills": ""}

    posting = _find_jobposting(soup)
    if posting:
        out["description"] = _html_to_text(posting.get("description", ""))
        out["skills"] = _as_lines(posting.get("skills"))
        out["requirements"] = "\n".join(filter(None, [
            _as_lines(posting.get("qualifications")),
            _as_lines(posting.get("experienceRequirements")),
            _as_lines(posting.get("educationRequirements")),
        ]))
        out["missions"] = _as_lines(posting.get("responsibilities"))

    for field, text in _sections_from_headings(soup).items():
        if not out[field]:
            out[field] = text

    if not out["description"]:
        container = soup.find("main") or soup.find("article") or soup.body
        if container:
            for junk in container(["script", "style", "nav", "header", "footer", "form"]):
                junk.decompose()
            out["description"] = _clean(container.get_text("\n"))[:20000]

    # A "skills" section is usually a bullet list: normalise to one per line.
    if out["skills"]:
        lines = [re.sub(r"^[-•*\s]+", "", l).strip() for l in out["skills"].splitlines()]
        out["skills"] = "\n".join(l for l in lines if l)
    return out
