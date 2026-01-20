import pymupdf


class PDFProcessor:
    def __init__(self, file_path):
        self.file_path = file_path
        self.doc = pymupdf.open(file_path)

    def extract_text(self):
        """Extracts text from the entire PDF."""
        text = ""
        for page in self.doc:
            text += page.get_text()
        return text

    def get_pages(self):
        """Yields text page by page."""
        for i, page in enumerate(self.doc):  # type: ignore
            yield i + 1, page.get_text()

    def chunk_text(self, text, chunk_size=2000, overlap=200):
        """Splits text into chunks with overlap."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    def close(self):
        """Closes the PDF document."""
        self.doc.close()
