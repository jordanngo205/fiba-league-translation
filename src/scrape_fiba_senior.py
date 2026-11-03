#!/usr/bin/env python3
"""Every senior women's FIBA game in 2025 and 2026, per player, tagged by competition.

Competition is carried through rather than filtered away: AmeriCup, EuroBasket and
the World Championships differ in difficulty, and that difference would otherwise
be absorbed into the club-league coefficient it is meant to be separated from.

Youth events (U16-U20) are excluded. Those players are largely not in the NCAA or
WNBA data yet, and youth FIBA is not the same competition level as senior, so
pooling them would corrupt the translation.
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict
import requests

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from paths import DATA as OUT  # noqa: E402
BASE = 'https://basketball.synergysportstech.com/api'
FIBA = '54457dce300969b132fcfb41'

SEASONS = [('2025', '684205c6d01c0c93c586dbf2'),
           ('2026', '6a279f505a56541612057320')]

YOUTH = ('U16', 'U17', 'U18', 'U19', 'U20', 'U23', '3x3', 'Grassroots')
# University-level and exhibition play are not senior international competition.
SKIP = ('World University Games', 'Exhibition', 'Albert Schweitzer')

STATS = ('secondsPlayed', 'possessions', 'points',
         'fieldGoalsMade', 'fieldGoalsAttempted',
         'threePtsMade', 'threePtsAttempted',
         'freeThrowsMade', 'freeThrowsAttempted',
         'offReb', 'defReb', 'assists', 'steals', 'blocks',
         'turnovers', 'fouls', 'blockedFGAs')


# Auth lives in synergy_auth: it reuses the token on disk while valid, then
# refreshes it with the refresh token, and only falls back to a full login if
# that fails. Full logins are what lock the account, so they are capped there.
import synergy_auth


def refresh_token():
    """Called on a 401. Renews without a login where possible."""
    return synergy_auth.on_401()


def headers():
    return synergy_auth.headers()


def is_senior(name):
    return (name and not any(y in name for y in YOUTH)
            and not any(s in name for s in SKIP))


def get_games(s, H, season_id):
    # Refresh in place before each call. headers() reuses the token on disk when
    # it is still fresh, so this is a file read, not a network call -- but it
    # means an expiring token is renewed ahead of time instead of after a 401.
    H.update(headers())
    out, skip = [], 0
    while True:
        r = s.post(f'{BASE}/games', headers=H, timeout=90,
                   json={'seasonIds': [season_id], 'excludeGamesWithoutCompetition': False,
                         'take': 500, 'skip': skip})
        if r.status_code == 401:
            H.update(refresh_token())
            continue
        b = r.json()['result']
        out += b
        if len(b) < 500:
            return out
        skip += 500


def fetch_team(s, H, season_id, team_id):
    # Refresh in place before each call. headers() reuses the token on disk when
    # it is still fresh, so this is a file read, not a network call -- but it
    # means an expiring token is renewed ahead of time instead of after a 401.
    H.update(headers())
    for _ in range(4):
        try:
            r = s.post(f'{BASE}/leagues/{FIBA}/seasons/{season_id}/playerswithboxscore',
                       headers=H, json={'competitionDefinitionKey': f'{FIBA}:ALL',
                                        'teamId': team_id}, timeout=60)
        except Exception:
            time.sleep(3)
            continue
        if r.status_code == 200:
            return r.json().get('result', [])
        if r.status_code == 401:
            H.update(refresh_token())
            continue
        time.sleep(2)
    return []


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s, H = requests.Session(), headers()
    rows, calls = {}, 0

    for sname, sid in SEASONS:
        games = get_games(s, H, sid); calls += 2
        senior = [g for g in games if is_senior((g.get('competition') or {}).get('name'))]
        comps = sorted({(g.get('competition') or {}).get('name') for g in senior})
        print(f'\n=== FIBA {sname}: {len(senior)} senior games, {len(comps)} competitions ===')

        # One call per team covers every competition that team played, so the
        # team is the unit to fetch and the competition is applied afterwards.
        teams = {}
        for g in senior:
            for side in ('homeTeam', 'awayTeam'):
                tm = g.get(side) or {}
                if tm.get('id'):
                    teams[tm['id']] = tm.get('name')
        print(f'    {len(teams)} distinct teams')

        for i, (tid, tname) in enumerate(teams.items(), 1):
            recs = fetch_team(s, H, sid, tid); calls += 1
            per_comp = defaultdict(lambda: defaultdict(float))
            for r in recs:
                pid = r.get('id')
                if not pid:
                    continue
                for bx in r.get('boxscore', []) or []:
                    gm = bx.get('game') or {}
                    comp = (gm.get('competition') or {}).get('name')
                    if not is_senior(comp):
                        continue
                    k = (pid, comp)
                    d = per_comp[k]
                    d['gp'] += 1
                    for f in STATS:
                        d[f] += (bx.get(f) or 0)
                    d['_name'] = r.get('name')
            for (pid, comp), d in per_comp.items():
                rec = {'player_id': pid, 'name': d.pop('_name'), 'nation': tname,
                       'competition': comp, 'season': sname}
                rec.update({k: v for k, v in d.items()})
                rec['twoPtsMade'] = rec['fieldGoalsMade'] - rec['threePtsMade']
                rec['twoPtsAttempted'] = rec['fieldGoalsAttempted'] - rec['threePtsAttempted']
                rows[f'{pid}|{sname}|{comp}'] = rec
            if i % 10 == 0 or i == len(teams):
                print(f'    {i}/{len(teams)} teams, {len(rows)} rows, {calls} calls', flush=True)

    json.dump(rows, open(OUT / 'fiba_senior.json', 'w'), indent=1)
    from collections import Counter
    c = Counter(v['competition'] for v in rows.values())
    print(f'\n{len(rows)} player-competition rows, {len({v["player_id"] for v in rows.values()})} players')
    print(f'{calls} API calls')
    for k, v in c.most_common():
        print(f'   {k[:50]:52} {v:4} players')


if __name__ == '__main__':
    main()
