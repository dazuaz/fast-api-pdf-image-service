import hashlib


def content_document_id(data: bytes) -> str:
    """SHA-256 hex digest of file bytes — stable for the same document contents."""
    return hashlib.sha256(data).hexdigest()
