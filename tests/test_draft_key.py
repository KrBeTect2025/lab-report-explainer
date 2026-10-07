import json

from tools.draft_key import draft_key
from tools.evaluate import evaluate
from tools.make_synthetic import generate


def test_unverified_draft_key_is_never_scored(tmp_path):
    """A draft copies the extractor's output; scoring it unchecked would always look perfect."""
    generate(str(tmp_path), per_template=1, seed=3)
    pdf_dir, keys = tmp_path / "pdf", tmp_path / "answer_keys"
    for key_file in keys.glob("*.json"):
        key_file.unlink()
    pdf = sorted(pdf_dir.glob("*.pdf"))[0]
    key = draft_key(str(pdf))
    assert key["verified"] is False and key["rows"]
    (keys / f"{pdf.stem}.json").write_text(json.dumps(key), encoding="utf-8")

    total, _ = evaluate(str(pdf_dir), str(keys), verbose=False)
    assert sum(total.total.values()) == 0  # nothing was scored

    key["verified"] = True  # the owner has checked it
    (keys / f"{pdf.stem}.json").write_text(json.dumps(key), encoding="utf-8")
    total, _ = evaluate(str(pdf_dir), str(keys), verbose=False)
    assert total.total["value"] == len(key["rows"])
