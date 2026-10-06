import io

from pypdf import PdfReader

PDF = "application/pdf"


class ExtractionError(Exception):
    pass


def extract_text(data: bytes, content_type: str) -> str:
    if content_type == PDF:
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ExtractionError(f"cannot read PDF: {exc}") from exc
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ExtractionError("file is not valid UTF-8 text") from exc

    text = text.strip()
    if not text:
        raise ExtractionError("no extractable text in document")
    return text
