"""Test-name normalisation, so "Hemoglobin (Photometry)" and "hemoglobin" match."""
from __future__ import annotations

import re


def normalize_name(name: str) -> str:
    n = re.sub(r"\([^)]*\)", " ", name)  # drop method text in brackets
    n = n.lower().replace("&", " and ")
    n = re.sub(r"[^a-z0-9% ]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()
