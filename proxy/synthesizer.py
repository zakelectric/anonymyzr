"""
synthesizer.py
--------------
Generates realistic synthetic replacements for detected PII.

Design goals:
  - Preserve structure and context (a name stays a name, an address stays an address)
  - Preserve numeric magnitude for amounts ($245k → $312k, not $3)
  - Preserve format masks for phones/SSNs (dashes, parens, spacing)
  - Consistency: same real value always produces same synthetic within a session
    (enforced by mapper cache, not by this module)
"""

import random
import re
from typing import Optional

from faker import Faker

from .mapper import mapper

fake = Faker()


def synthesize(session_id: str, real_value: str, entity_label: str) -> str:
    """
    Return a consistent synthetic value for real_value.
    Checks the session mapper first; generates and stores if not seen before.
    """
    cached = mapper.get_synthetic(session_id, real_value)
    if cached:
        return cached

    synthetic = _generate(real_value, entity_label)

    # Collision guard: don't map two different real values to the same synthetic
    attempts = 0
    while mapper.get_real(session_id, synthetic) is not None and attempts < 10:
        synthetic = _generate(real_value, entity_label)
        attempts += 1

    mapper.store(session_id, real_value, synthetic)
    return synthetic


def _generate(real_value: str, entity_label: str) -> str:
    label = entity_label.lower()

    if _matches(label, ["person", "name", "individual"]):
        return fake.name()

    if _matches(label, ["company", "organization", "org", "business", "employer", "firm"]):
        return fake.company()

    if _matches(label, ["address"]):
        return fake.address().replace("\n", ", ")

    if _matches(label, ["email"]):
        return fake.email()

    if _matches(label, ["phone"]):
        return _fake_phone(real_value)

    if _matches(label, ["social security", "ssn"]):
        return fake.ssn()

    if _matches(label, ["credit card"]):
        return fake.credit_card_number()

    if _matches(label, ["bank account", "account number", "routing"]):
        digit_count = max(len(re.sub(r"\D", "", real_value)), 8)
        return "".join(str(fake.random_digit()) for _ in range(digit_count))

    if _matches(label, ["dollar", "amount", "money", "salary", "wage", "revenue", "price"]):
        return _fake_amount(real_value)

    if _matches(label, ["ip address", "ip"]):
        return fake.ipv4()

    if _matches(label, ["url", "website", "domain"]):
        return fake.url()

    if _matches(label, ["date of birth", "dob", "birthday"]):
        return fake.date_of_birth(minimum_age=18, maximum_age=80).strftime("%m/%d/%Y")

    if _matches(label, ["date"]):
        return fake.date()

    if _matches(label, ["passport"]):
        return fake.bothify("?#######").upper()

    if _matches(label, ["driver", "license", "licence"]):
        return fake.bothify("??######").upper()

    if _matches(label, ["medical record", "mrn"]):
        return fake.numerify("MRN-#######")

    if _matches(label, ["employee", "emp id", "staff id"]):
        return fake.numerify("EMP-######")

    # Fallback: preserve length with random alphanumeric
    return fake.lexify("?" * min(len(real_value), 12))


def _matches(label: str, keywords: list[str]) -> bool:
    return any(kw in label for kw in keywords)


def _fake_phone(real_value: str) -> str:
    """
    Randomize digits while preserving separators and formatting.
    Example: (312) 867-5309 → (312) 234-7821
    Area code (first 3 digits) is also randomized.
    """
    digit_count = [0]

    def replace_digit(m):
        digit_count[0] += 1
        # First digit of a group must not be 0 or 1
        if digit_count[0] == 1:
            return str(random.randint(2, 9))
        return str(random.randint(0, 9))

    return re.sub(r"\d", replace_digit, real_value)


def _fake_amount(real_value: str) -> str:
    """
    Replace dollar amount while preserving:
      - currency symbol ($, £, €, ¥)
      - comma formatting
      - decimal places
      - order of magnitude (±50%)
    """
    currency_symbol = ""
    if real_value and real_value[0] in "$£€¥":
        currency_symbol = real_value[0]

    digits_only = re.sub(r"[^\d.]", "", real_value)

    try:
        original = float(digits_only)
        new_amount = original * random.uniform(0.5, 1.5)

        has_cents = "." in real_value and len(real_value.split(".")[-1]) == 2
        has_commas = "," in real_value

        if has_cents:
            formatted = f"{new_amount:,.2f}" if has_commas else f"{new_amount:.2f}"
        else:
            formatted = f"{int(new_amount):,}" if has_commas else str(int(new_amount))

        return f"{currency_symbol}{formatted}"

    except (ValueError, IndexError):
        return real_value
