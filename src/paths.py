"""Where things live.

Scripts sit in src/ but credentials, the session token and the data directory
all belong to the project root, so every path is resolved from here rather than
from the directory a script happens to be in.
"""
import os
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
ENV_FILE = ROOT / '.env'

# The Synergy session is per-ACCOUNT, not per-project, so the token belongs in
# one place that every project shares.
#
# A per-project copy is actively dangerous. Refresh tokens rotate: whichever
# project refreshes first silently invalidates every other copy, and presenting
# a spent token makes the server treat it as theft and revoke the whole session.
# That looks exactly like an account lockout and is not one. It is what happened
# here -- a token copied between two projects, rotated by one, then presented by
# the other.
#
# SYNERGY_TOKEN_PATH overrides, otherwise a single file under the home
# directory is shared by every project on this machine.
TOKEN_FILE = Path(
    os.environ.get('SYNERGY_TOKEN_PATH')
    or Path.home() / '.synergy' / 'token.json')
TWOFA_FILE = ROOT / '.2fa_code'
DATA = ROOT / 'data' / 'translation'
DOCS = ROOT / 'docs'
