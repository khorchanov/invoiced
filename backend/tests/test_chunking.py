import pytest

from app.services.chunking import chunk_text
from app.services.extraction import ExtractionError, extract_text


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("hello world") == ["hello world"]


def test_chunks_respect_size_and_cover_text() -> None:
    text = " ".join(f"word{i}" for i in range(500))
    chunks = chunk_text(text, size=200, overlap=30)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    assert chunks[0].startswith("word0")
    assert chunks[-1].endswith("word499")


def test_chunks_overlap() -> None:
    text = " ".join(f"w{i}" for i in range(300))
    chunks = chunk_text(text, size=100, overlap=20)
    assert chunks[0].split()[-1] in chunks[1].split()


def test_prefers_paragraph_boundaries() -> None:
    text = ("a" * 60) + "\n\n" + ("b" * 60)
    assert chunk_text(text, size=100, overlap=0) == ["a" * 60, "b" * 60]


def test_text_without_separators_still_terminates() -> None:
    chunks = chunk_text("x" * 1000, size=100, overlap=10)
    assert all(len(c) <= 100 for c in chunks)
    assert len(chunks) >= 10


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", size=10, overlap=10)


def test_extract_plain_text_strips_bom() -> None:
    assert extract_text("\ufeffhello\n".encode("utf-8"), "text/plain") == "hello"


def test_extract_rejects_empty_and_binary() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"   \n", "text/plain")
    with pytest.raises(ExtractionError):
        extract_text(b"\xff\xfe\x00", "text/plain")


def test_extract_rejects_broken_pdf() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"%PDF-1.4 garbage", "application/pdf")
