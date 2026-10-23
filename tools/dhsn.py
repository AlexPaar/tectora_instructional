import re
import unicodedata
from pathlib import Path
from typing import Annotated

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from rapidfuzz import process as fuzz_process

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DHSN_CONTACT_URL = "https://www.dhsn.de/kontakt"

_CONTACT_CACHE: list[dict] | None = None

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
}


class ContactSearchParams(BaseModel):
    name: Annotated[
        str,
        Field(
            description="The full or partial name of the contact to look up (e.g., 'Krabbes', 'Prof. Krabbes', 'Markus Krabbes')."
        ),
    ]
    score_cutoff: Annotated[
        float,
        Field(
            default=60.0,
            ge=0.0,
            le=100.0,
            description="Minimum fuzzy-match score (0-100). Lower values return more lenient matches.",
        ),
    ] = 60


class ContactSearchOutput(BaseModel):
    name: str = Field(description="The name of the contact.")
    title: str | None = Field(default=None, description="The academic title of the contact.")
    affiliation: str = Field(default="Duale Hochschule Sachsen", description="The affiliation of the contact.")
    campus: str | None = Field(default=None, description="The campus or department of the contact.")
    email: str | None = Field(default=None, description="The email address of the contact.")
    phone_number: str | None = Field(default=None, description="The phone number of the contact.")
    role: str | None = Field(default=None, description="The role of the contact.")
    match_score: float = Field(description="Fuzzy-match confidence score (0-100).")


def _normalize(text: str) -> str:
    """Lowercase and strip accents for comparison."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _fetch_contacts() -> list[dict]:
    """Scrape all employee contacts from the DHSN contact page.

    The page uses TYPO3's cc_professorenliste plugin.  Each campus is
    a ``<section class="cc_professorenliste">`` element preceded by an
    ``<h3>`` heading.  Inside each section, contacts are ``<li>`` items
    in ``<ul class="cc_professorenliste_list">``.

    Returns a list of dicts with keys:
        name, title, role, campus, email, phone
    """
    global _CONTACT_CACHE
    if _CONTACT_CACHE is not None:
        return _CONTACT_CACHE

    response = requests.get(DHSN_CONTACT_URL, headers=_REQUEST_HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    contacts: list[dict] = []

    for section in soup.find_all("section", class_="cc_professorenliste"):
        # The h3 immediately before this section is the campus/department heading.
        prev_heading = section.find_previous(["h3", "h2"])
        campus = prev_heading.get_text(strip=True) if prev_heading else "Unbekannt"

        for li in section.find_all("li"):
            namewrap = li.find(class_="cc_namewrap")
            if not namewrap:
                continue

            title_el = namewrap.find(class_="cc_title")
            surname_el = namewrap.find(class_="cc_surname")
            firstname_el = namewrap.find(class_="cc_firstname")

            title = title_el.get_text(strip=True) if title_el else None
            surname = surname_el.get_text(strip=True) if surname_el else ""
            firstname = firstname_el.get_text(strip=True) if firstname_el else ""
            proper_name = f"{firstname} {surname}".strip()

            if not proper_name:
                continue

            role_el = li.find(class_="cc_position")
            role = role_el.get_text(" ", strip=True).strip() if role_el else None

            collapsed = li.find(class_="cc_mobile_collapsed")

            email: str | None = None
            phone: str | None = None
            if collapsed:
                email_tag = collapsed.find("a", href=re.compile(r"^mailto:", re.IGNORECASE))
                if email_tag:
                    email = email_tag["href"].replace("mailto:", "").strip()

                phone_tag = collapsed.find("a", href=re.compile(r"^tel:", re.IGNORECASE))
                if phone_tag:
                    phone = phone_tag["href"].replace("tel:", "").strip()

            contacts.append(
                {
                    "name": proper_name,
                    "title": title or None,
                    "role": role or None,
                    "campus": campus,
                    "email": email,
                    "phone": phone,
                }
            )

    _CONTACT_CACHE = contacts
    return contacts


@tool(
    args_schema=ContactSearchParams,
    description=(
        "Look up an employee's contact information from the DHSN (Duale Hochschule Sachsen) website. "
        "Accepts a full or partial name and returns the best-matching contact as a dictionary."
    ),
)
def search_contact(name: str, score_cutoff: float = 60.0) -> dict:
    """Search the DHSN contact directory for an employee by (fuzzy) name.

    Returns a dict with keys: name, title, affiliation, campus, email,
    phone_number, role, match_score.  Returns an error dict if no match
    is found above the score_cutoff threshold.
    """
    contact_schema = ContactSearchOutput.model_json_schema()["properties"]

    contacts = _fetch_contacts()
    if not contacts:
        return {
            "data": {},
            "error": "Could not retrieve contacts from the DHSN website.",
            "field_semantics_reference": contact_schema,
        }

    # Build a mapping from a searchable key to the original contact dict.
    # We index by "Firstname Lastname" (title stripped) for better matching.
    keys = [_normalize(c["name"]) for c in contacts]
    query = _normalize(name)

    result = fuzz_process.extractOne(query, keys, score_cutoff=score_cutoff)
    if result is None:
        return {
            "data": {},
            "error": (
                f"No contact found for '{name}' with a match score ≥ {score_cutoff}. "
                "Try lowering score_cutoff or check the spelling."
            ),
            "field_semantics_reference": contact_schema,
        }

    _matched_key, score, idx = result

    contact = contacts[idx]

    contact_object = ContactSearchOutput(
        name=contact["name"],
        title=contact.get("title"),
        campus=contact.get("campus"),
        email=contact.get("email"),
        phone_number=contact.get("phone"),
        role=contact.get("role"),
        match_score=score,
    )

    self_documenting_payload = {
        "data": contact_object.model_dump(),
        "field_semantics_reference": contact_schema,
    }

    return self_documenting_payload
