import re
import secrets

ID_BYTES = 16
DRAFT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")


def new_draft_id() -> str:
    return secrets.token_urlsafe(ID_BYTES)


def is_draft_id(value: str) -> bool:
    return bool(DRAFT_ID_PATTERN.match(value))
