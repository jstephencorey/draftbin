import re
import secrets

from draftbin.wordlist import WORDS

# Two words is ~1.7M combinations, against 128 bits for the ids minted before this. That
# is a deliberate trade: an id that survives being read aloud down a phone is worth more
# here than guess-resistance a draft's short life already bounds. It does mean the
# keyspace is enumerable by a determined scanner, so it is not what keeps a draft private
# — expiry is. See "Why links expire" in the README.
WORDS_PER_ID = 2

DRAFT_ID_PATTERN = re.compile(rf"^[a-z]{{3,5}}(?:-[a-z]{{3,5}}){{{WORDS_PER_ID - 1}}}$")

# Ids minted before the switch to words. Still resolvable, so links already written into
# notes keep working; never generated again.
LEGACY_DRAFT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")


def new_draft_id() -> str:
    return "-".join(secrets.choice(WORDS) for _ in range(WORDS_PER_ID))


def is_draft_id(value: str) -> bool:
    return bool(DRAFT_ID_PATTERN.match(value) or LEGACY_DRAFT_ID_PATTERN.match(value))
