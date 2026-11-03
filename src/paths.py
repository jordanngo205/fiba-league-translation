"""Where things live.

Scripts sit in src/ but credentials, the session token and the data directory
all belong to the project root, so every path is resolved from here rather than
from the directory a script happens to be in.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
ENV_FILE = ROOT / '.env'
TOKEN_FILE = ROOT / '.synergy_token'
TWOFA_FILE = ROOT / '.2fa_code'
DATA = ROOT / 'data' / 'translation'
DOCS = ROOT / 'docs'
