"""HTTP API: upload a report, review its rows, read the result by token, delete it.

    uvicorn app.api.main:app --reload

The uploaded PDF is read from a temporary file and deleted straight after extraction.
Only the structured values are stored, and only for 24 hours.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.api.store import Store
from app.extract.pdf_rows import TooManyPages, extract_pdf
from app.schema import Correction, Report, accept, correct, pending, reject

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30  # lab reports run to about 15 pages; more is likely not a report
PURGE_EVERY_SECONDS = 60 * 60
# Draft wording; the owner may change it. Sent with every result (hard rule 4).
DISCLAIMER = (
    "This is general information to help you read your report. It is not a diagnosis "
    "or medical advice. Please discuss your results with your doctor."
)
log = logging.getLogger("api")  # never log file names or values: they can identify a person


class RowAction(BaseModel):
    action: Literal["accept", "reject", "correct"]
    correction: Optional[Correction] = None  # required when action is "correct"


def create_app(store: Store) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async def purge_loop():
            while True:
                gone = store.purge_expired()
                if gone:
                    log.info("deleted %d expired results", gone)
                await asyncio.sleep(PURGE_EVERY_SECONDS)

        task = asyncio.create_task(purge_loop())
        yield
        task.cancel()

    app = FastAPI(title="Lab Report Explainer", lifespan=lifespan)

    def _result(token: str, report: Report) -> dict:
        return {
            "token": token,
            "disclaimer": DISCLAIMER,
            "pending_review": pending(report),
            "report": report.model_dump(),
        }

    def _load(token: str) -> Report:
        report = store.load(token)
        if report is None:
            raise HTTPException(404, "not found or expired")
        return report

    @app.post("/reports", status_code=201)
    def upload(file: UploadFile = File(...), consent: bool = Form(...)) -> dict:
        if not consent:
            raise HTTPException(400, "consent is required before upload")
        data = file.file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "file is larger than 10 MB")
        if not data.startswith(b"%PDF-"):
            raise HTTPException(415, "only PDF files are supported for now")
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            try:
                result = extract_pdf(tmp, max_pages=MAX_PAGES)
            except TooManyPages:
                raise HTTPException(413, f"more than {MAX_PAGES} pages") from None
            except Exception as exc:  # damaged or unusual PDF
                log.warning("extraction failed: %s", type(exc).__name__)
                raise HTTPException(422, "could not read this PDF") from None
        finally:
            Path(tmp).unlink(missing_ok=True)
        result["file"] = "upload.pdf"  # the real file name may contain the patient's name
        report = Report.model_validate(result)
        return _result(store.save(report), report)

    @app.get("/reports/{token}")
    def get_report(token: str) -> dict:
        return _result(token, _load(token))

    @app.post("/reports/{token}/rows/{index}")
    def review_row(token: str, index: int, body: RowAction) -> dict:
        """The confirmation step: accept, reject or correct one extracted row."""
        report = _load(token)
        if not 0 <= index < len(report.rows):
            raise HTTPException(404, "no such row")
        if body.action == "accept":
            accept(report, index)
        elif body.action == "reject":
            reject(report, index)
        elif body.correction is None:
            raise HTTPException(422, "a correction is required for action 'correct'")
        else:
            correct(report, index, body.correction)
        if not store.update(token, report):
            raise HTTPException(404, "not found or expired")
        return _result(token, report)

    @app.delete("/reports/{token}", status_code=204)
    def delete_report(token: str) -> Response:
        if not store.delete(token):
            raise HTTPException(404, "not found or expired")
        return Response(status_code=204)

    return app


app = create_app(Store(Path(os.environ.get("STORE_DIR", "data/store"))))
