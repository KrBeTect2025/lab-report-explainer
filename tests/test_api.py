from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.store import TTL_SECONDS, Store
from tools.make_synthetic import generate


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def _setup(tmp_path):
    clock = Clock()
    store = Store(tmp_path / "store", now=clock)
    generate(str(tmp_path / "syn"), per_template=1, seed=3)
    pdf = sorted((tmp_path / "syn" / "pdf").glob("*.pdf"))[0].read_bytes()
    return TestClient(create_app(store)), store, clock, pdf


def _upload(client, pdf, consent="true"):
    return client.post("/reports", files={"file": ("Ravi Kumar report.pdf", pdf, "application/pdf")},
                       data={"consent": consent})


def test_upload_then_read_by_token(tmp_path):
    client, _, _, pdf = _setup(tmp_path)
    r = _upload(client, pdf)
    assert r.status_code == 201
    body = r.json()
    assert len(body["token"]) == 43 and body["report"]["rows"]
    assert body["report"]["file"] == "upload.pdf"  # uploaded file name is not kept
    assert client.get(f"/reports/{body['token']}").json() == body


def test_expired_result_is_gone_from_api_and_disk(tmp_path):
    client, store, clock, pdf = _setup(tmp_path)
    token = _upload(client, pdf).json()["token"]
    clock.t += TTL_SECONDS - 1
    assert client.get(f"/reports/{token}").status_code == 200
    clock.t += 1  # exactly 24 hours old
    assert client.get(f"/reports/{token}").status_code == 404
    assert not list((tmp_path / "store").iterdir())  # removed from disk, not only hidden


def test_cleanup_job_deletes_expired_results_nobody_asked_for(tmp_path):
    client, store, clock, pdf = _setup(tmp_path)
    old = _upload(client, pdf).json()["token"]
    clock.t += TTL_SECONDS
    new = _upload(client, pdf).json()["token"]
    assert store.purge_expired() == 1
    assert [p.stem for p in (tmp_path / "store").iterdir()] == [new]
    assert store.load(old) is None


def test_user_can_delete_their_result(tmp_path):
    client, _, _, pdf = _setup(tmp_path)
    token = _upload(client, pdf).json()["token"]
    assert client.delete(f"/reports/{token}").status_code == 204
    assert client.get(f"/reports/{token}").status_code == 404
    assert client.delete(f"/reports/{token}").status_code == 404


def test_upload_is_refused_without_consent_or_when_not_a_pdf(tmp_path):
    client, _, _, pdf = _setup(tmp_path)
    assert _upload(client, pdf, consent="false").status_code == 400
    assert _upload(client, b"hello, not a pdf").status_code == 415
    assert _upload(client, b"%PDF-1.4 broken").status_code == 422
    assert not list((tmp_path / "store").iterdir())  # nothing stored for refused uploads


def test_bad_tokens_never_touch_the_file_system(tmp_path):
    client, store, _, _ = _setup(tmp_path)
    assert client.get("/reports/..%2F..%2Fsecret").status_code == 404
    assert store.load("../../etc/passwd") is None and not store.delete("../x")


def test_every_result_carries_the_disclaimer(tmp_path):
    client, _, _, pdf = _setup(tmp_path)
    body = _upload(client, pdf).json()
    assert "discuss your results with your doctor" in body["disclaimer"]
    assert client.get(f"/reports/{body['token']}").json()["disclaimer"] == body["disclaimer"]


def test_review_row_over_the_api(tmp_path):
    client, store, clock, pdf = _setup(tmp_path)
    token = _upload(client, pdf).json()["token"]
    r = client.post(f"/reports/{token}/rows/0", json={"action": "reject"})
    assert r.status_code == 200 and r.json()["report"]["rows"][0]["status"] == "rejected"
    fix = {"name": "Hemoglobin", "value": 9.1, "unit": "g/dL", "range_text": "13.0 - 17.0"}
    row = client.post(f"/reports/{token}/rows/1", json={"action": "correct", "correction": fix}).json()["report"]["rows"][1]
    assert (row["value"], row["computed_flag"], row["status"]) == (9.1, "low", "corrected")
    assert client.get(f"/reports/{token}").json()["report"]["rows"][1]["status"] == "corrected"  # saved
    assert client.post(f"/reports/{token}/rows/1", json={"action": "correct"}).status_code == 422
    assert client.post(f"/reports/{token}/rows/999", json={"action": "accept"}).status_code == 404
    # Editing a row must not extend the 24 hours.
    clock.t += TTL_SECONDS
    assert client.post(f"/reports/{token}/rows/0", json={"action": "accept"}).status_code == 404


def test_scanned_pdf_says_so_instead_of_returning_nothing(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(path))
    c.rect(50, 50, 400, 600, fill=1)  # an image-like page with no text at all
    c.save()
    client, _, _, _ = _setup(tmp_path)
    body = _upload(client, path.read_bytes()).json()
    assert body["report"]["rows"] == []
    assert body["report"]["unparsed"] == [{"page": 1, "text": "", "reason": "no_text_layer"}]


def test_too_many_pages_is_refused(tmp_path):
    from reportlab.pdfgen import canvas

    from app.api.main import MAX_PAGES

    path = tmp_path / "long.pdf"
    c = canvas.Canvas(str(path))
    for _ in range(MAX_PAGES + 1):
        c.drawString(50, 700, "page")
        c.showPage()
    c.save()
    client, _, _, _ = _setup(tmp_path)
    assert _upload(client, path.read_bytes()).status_code == 413
    assert not list((tmp_path / "store").iterdir())
