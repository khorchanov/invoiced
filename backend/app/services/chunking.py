SEPARATORS = ("\n\n", "\n", ". ", " ")


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    """Split text into chunks of at most `size` characters, preferring natural boundaries.

    Consecutive chunks share up to `overlap` characters so context is not lost at a cut.
    """
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("need size > 0 and 0 <= overlap < size")

    text = text.strip()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Cut at the last separator in the back half of the window, if any.
            floor = start + size // 2
            for separator in SEPARATORS:
                cut = text.rfind(separator, floor, end)
                if cut != -1:
                    end = cut + len(separator)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
