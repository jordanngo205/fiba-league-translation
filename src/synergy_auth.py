#!/usr/bin/env python3
"""
One place that owns the Synergy session, so no scraper has to think about it.

Why this exists: Synergy locks the account after a handful of rapid logins. An
earlier scrape shelled out to do_auth.py -- a full username/password login --
every time a token expired, and did it five times in an hour. The auth system
read that as credential stuffing and locked the account.

The login response has always included a refresh token; do_auth.py just threw it
away. A refresh is a token-endpoint call with no credentials attached, so it is
not rate-limited the way a login is. Order of preference here:

  1. reuse the token on disk while it is still valid (no network call at all)
  2. refresh it with the refresh token      (cheap, no credentials sent)
  3. full login                             (last resort, capped and spaced)
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from paths import ROOT, SRC, ENV_FILE, TOKEN_FILE  # noqa: E402

DIR = SRC
AUTH_BASE = 'https://auth.synergysportstech.com'
CLIENT_ID = 'client.basketball.teamsite'

# Renew this long before the token actually expires, so a request started just
# under the wire does not die mid-flight. Measured behaviour: a login gives a
# 60min token but a refresh gives only ~10min, so a fixed 5min margin would
# renew almost continuously. Scale it to the token instead, with a floor above
# the longest request timeout in the scrapers (90s).
_MIN_MARGIN = 120
_MAX_MARGIN = 300


def _margin(tok):
    return max(_MIN_MARGIN, min(_MAX_MARGIN, tok.get('expires_in', 3600) * 0.25))

# Backstop on full logins only. Refreshes are not counted or delayed.
_MIN_SECONDS_BETWEEN_LOGINS = 90
_MAX_LOGINS_PER_RUN = 2
_login_count = 0
_last_login = 0.0


def load():
    if not TOKEN_FILE.exists():
        return {}
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (ValueError, OSError):
        return {}


def save(data, keep_refresh_from=None):
    """Persist a token response, carrying the old refresh token if a new one
    was not issued (some servers rotate it, some do not)."""
    out = {
        'token_type': data.get('token_type', 'Bearer'),
        'access_token': data['access_token'],
        'refresh_token': data.get('refresh_token')
                         or (keep_refresh_from or {}).get('refresh_token'),
        'expires_in': data.get('expires_in', 3600),
        'obtained_at': time.time(),
    }
    # Write-then-rename so a crash or two scrapers overlapping can never leave a
    # half-written token file -- that would cost a login to recover from.
    tmp = TOKEN_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(out))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, TOKEN_FILE)
    return out


def seconds_left(tok=None):
    tok = tok if tok is not None else load()
    if not tok.get('access_token'):
        return 0
    # Tokens saved by the old do_auth.py have no timestamp. Treat them as
    # unknown-age rather than fresh, so they get renewed instead of 401ing.
    if 'obtained_at' not in tok:
        return 0
    return tok['obtained_at'] + tok.get('expires_in', 3600) - time.time()


class _RotationLock:
    """Exclusive lock around a refresh.

    Rotation is read-modify-write on a shared file: two processes refreshing at
    once both read the same token, both send it, and the loser is left holding
    one the server has already retired. Serialising the refresh is what makes a
    shared token file safe to share.
    """

    def __init__(self, path):
        self.path = Path(str(path) + '.lock')
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, 'w')
        try:
            import fcntl
            fcntl.flock(self.fh, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass        # best effort: a missing lock must not block the scrape
        return self

    def __exit__(self, *exc):
        try:
            import fcntl
            fcntl.flock(self.fh, fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        self.fh.close()


def renew(verbose=True):
    """Swap the refresh token for a new access token. No credentials sent.

    Synergy rotates the refresh token on every use: the response carries a new
    one and the old one stops working. So the save below is not optional -- miss
    it once and the chain is broken and the next renewal costs a full login.
    It also means two scrapers must not run against this token file at the same
    time; each refresh would invalidate the other's token.
    """
    with _RotationLock(TOKEN_FILE):
        return _renew_locked(verbose)


def _renew_locked(verbose):
    # Re-read inside the lock: another process may have refreshed while this
    # one waited, in which case its token is already good and no call is needed.
    tok = load()
    if not tok.get('refresh_token'):
        return None
    if seconds_left(tok) > _MIN_MARGIN:
        if verbose:
            print('   [another process already refreshed; reusing]', flush=True)
        return tok
    r = requests.post(
        f'{AUTH_BASE}/connect/token',
        headers={'Content-Type': 'application/x-www-form-urlencoded',
                 'Accept': 'application/json'},
        data={'grant_type': 'refresh_token',
              'refresh_token': tok['refresh_token'],
              'client_id': CLIENT_ID},
        timeout=30)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code != 200 or 'access_token' not in data:
        # A dead refresh token must be discarded, not kept and presented again.
        # Servers treat a reused refresh token as a stolen one and revoke the
        # whole token family; retrying it cannot succeed and can only make
        # things worse. Clearing it here means the next renewal goes straight
        # to a login instead of burning a second rejection first.
        #
        # The usual cause is two processes sharing one token file: rotation
        # means whichever refreshes first invalidates the other's copy. One
        # file used by one process at a time is the only safe arrangement.
        if data.get('error') == 'invalid_grant' or r.status_code == 400:
            tok.pop('refresh_token', None)
            try:
                save(tok)
            except (OSError, KeyError):
                pass
            if verbose:
                print('   [refresh token is spent or revoked; discarded so it '
                      'is not presented twice]', flush=True)
        elif verbose:
            print(f'   [refresh rejected ({r.status_code})]', flush=True)
        if verbose:
            print('   [falling back to a full login]', flush=True)
        return None
    out = save(data, keep_refresh_from=tok)
    if verbose:
        print(f'   [token refreshed, no login needed, good for '
              f'{out["expires_in"] // 60}min]', flush=True)
    return out


def login(verbose=True):
    """Full username/password login. Capped and spaced -- this is the call that
    gets the account locked if it is made too often."""
    global _login_count, _last_login
    if _login_count >= _MAX_LOGINS_PER_RUN:
        sys.exit(f'stopping: {_MAX_LOGINS_PER_RUN} full logins already used this '
                 'run and the refresh token is not working. Rerun '
                 '`python3 do_auth.py` by hand rather than risking a lockout.')
    wait = _MIN_SECONDS_BETWEEN_LOGINS - (time.time() - _last_login)
    if wait > 0:
        if verbose:
            print(f'   [waiting {wait:.0f}s before login]', flush=True)
        time.sleep(wait)
    r = subprocess.run([sys.executable, str(DIR / 'do_auth.py')],
                       cwd=str(DIR), capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    _login_count += 1
    _last_login = time.time()
    if 'Token saved' not in r.stdout:
        sys.exit('login failed -- stopping rather than retrying, so the account '
                 'is not locked out:\n' + (r.stdout + r.stderr)[-400:])
    if verbose:
        print(f'   [logged in, {_login_count}/{_MAX_LOGINS_PER_RUN}]', flush=True)
    return load()


def ensure(force=False, verbose=True):
    """Return a valid token, doing the least expensive thing that works."""
    tok = load()
    if not force and seconds_left(tok) > _margin(tok):
        return tok
    return renew(verbose=verbose) or login(verbose=verbose)


def headers(tok=None, force=False):
    """Request headers with a guaranteed-live token."""
    tok = tok or ensure(force=force)
    return {'Authorization': f"{tok['token_type']} {tok['access_token']}",
            'Accept': 'application/json, text/plain, */*',
            'X-SYNERGY-CLIENT': 'ProductVersion=2026.02.25.10717; '
                                'ProductName=Basketball.TeamSite',
            'Origin': 'https://apps.synergysports.com',
            'Referer': 'https://apps.synergysports.com/',
            'Content-Type': 'application/json; charset=utf-8'}


def on_401():
    """Call after a 401: renew first, only log in if that fails."""
    return headers(force=True)


if __name__ == '__main__':
    load_dotenv(ENV_FILE)
    tok = load()
    left = seconds_left(tok)
    print(f'token on disk: {"yes" if tok.get("access_token") else "no"}'
          f'   refresh token: {"yes" if tok.get("refresh_token") else "no"}'
          f'   valid for: {left / 60:.0f}min')
    if len(sys.argv) > 1 and sys.argv[1] == 'renew':
        ensure(force=True)
