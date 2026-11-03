#!/usr/bin/env python3
"""Find Synergy league and season ids by name.

EuroLeague Women is not in the cached discovery dump, so its ids have to be
looked up before it can be scraped. Two calls, both read-only.

    python3 src/discover_leagues.py            # list every league
    python3 src/discover_leagues.py euro       # filter by name
"""
import json
import sys
from pathlib import Path

import requests

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import synergy_auth as A  # noqa: E402

BASE = 'https://basketball.synergysportstech.com/api'


def main():
    needle = (sys.argv[1] if len(sys.argv) > 1 else '').lower()
    s = requests.Session()
    H = A.headers()

    r = s.get(f'{BASE}/leagues', headers=H, timeout=60)
    if r.status_code != 200:
        sys.exit(f'leagues call failed: {r.status_code} {r.text[:160]}')
    leagues = r.json().get('result', r.json())

    hits = [lg for lg in leagues
            if not needle or needle in (lg.get('name') or '').lower()]
    print(f'{len(hits)} of {len(leagues)} leagues match\n')
    for lg in hits:
        print(f"  {lg.get('name'):44} {lg.get('id')}")

    # Seasons for a single unambiguous match, which is the usual case.
    if len(hits) == 1:
        lid = hits[0]['id']
        r = s.get(f'{BASE}/leagues/{lid}/seasons', headers=H, timeout=60)
        if r.status_code == 200:
            seasons = r.json().get('result', [])
            print(f"\nseasons for {hits[0]['name']}:")
            for sn in sorted(seasons, key=lambda x: str(x.get('name')),
                             reverse=True)[:8]:
                print(f"  {str(sn.get('name')):14} {sn.get('id')}")
            print('\nPaste the id and the two most recent seasons into '
                  'src/leagues.py under the matching league.')
        else:
            print(f'\nseasons call failed: {r.status_code}')


if __name__ == '__main__':
    main()
