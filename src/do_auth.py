#!/usr/bin/env python3
"""
Full interactive login. Run this only when there is no usable token and no
working refresh token -- every run of this is a real username/password login,
and a handful of them in quick succession locks the Synergy account.

To extend an existing session instead, use:  python3 synergy_auth.py renew

Usage:  python3 do_auth.py
"""
import pkce, requests, os, sys
from pathlib import Path
from dotenv import load_dotenv

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from paths import ENV_FILE  # noqa: E402
import synergy_functions as sf
import synergy_auth

load_dotenv(ENV_FILE)

session = requests.Session()
cv = pkce.generate_code_verifier(length=128)
cc = pkce.get_code_challenge(cv)

token_type, refresh_token, access_token = sf.get_access_token(
    session, cv, cc,
    os.getenv('SYNERGY_USERNAME'), os.getenv('SYNERGY_PASSWORD'))

if not access_token:
    sys.exit('Auth failed')

# The refresh token is the whole point of saving more than the access token:
# with it, later renewals cost a token-endpoint call instead of a login.
tok = synergy_auth.save({'token_type': token_type,
                         'access_token': access_token,
                         'refresh_token': refresh_token})

print(f'Token saved to {synergy_auth.TOKEN_FILE}')
print(f'  refresh token: {"saved" if tok["refresh_token"] else "NOT RETURNED by server"}')
print(f'  valid for: {tok["expires_in"] // 60} min '
      '(renewable without another login)')
