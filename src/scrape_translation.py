#!/usr/bin/env python3
"""Pull FIBA tournament, WNBA and NCAA player stats for league-translation work.

All three competitions live in one Synergy account with shared player ids, so a
player's national-team line joins to her club line directly. No name matching.

Output: data/translation/{fiba,wnba,ncaa}_players.json
"""
import json, os, sys, time
from pathlib import Path
import requests

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from paths import DATA as OUT  # noqa: E402
BASE = 'https://basketball.synergysportstech.com/api'

LEAGUES = {'fiba': '54457dce300969b132fcfb41',
           'wnba': '54457dce300969b132fcfb35',
           'ncaa': '54457dce300969b132fcfb38'}

# The two tournaments, each a group of teams inside a larger competition.
TOURNAMENTS = [
    {'key': 'guadalajara', 'season': '6a279f505a56541612057320',
     'competition': 'Olympic Pre-Qualifying Tournament'},
    # All four World Cup qualifying venues, not just Canada's group. The
    # coefficient being estimated belongs to the club league, so every NCAA or
    # WNBA player at any venue is another observation of the same quantity, and
    # fitting each venue separately gives a check on whether the effect is stable.
    {'key': 'wcq_turkey', 'season': '684205c6d01c0c93c586dbf2',
     'competition': 'World Cup Qualifying',
     'teams': {'Argentina', 'Australia', 'Canada', 'Hungary', 'Japan', 'Turkey'}},
    {'key': 'wcq_b', 'season': '684205c6d01c0c93c586dbf2',
     'competition': 'World Cup Qualifying',
     'teams': {'Belgium', 'Brazil', 'China', 'CzechRepublic', 'Mali', 'South Sudan'}},
    {'key': 'wcq_c', 'season': '684205c6d01c0c93c586dbf2',
     'competition': 'World Cup Qualifying',
     'teams': {'Italy', 'New Zealand', 'PuertoRico', 'Senegal', 'Spain', 'USA'}},
    {'key': 'wcq_d', 'season': '684205c6d01c0c93c586dbf2',
     'competition': 'World Cup Qualifying',
     'teams': {'Colombia', 'France', 'Germany', 'Korea', 'Nigeria', 'Philippines'}},
]

# Club seasons that overlap the tournaments. NCAA runs across the new year, so
# its label differs from the WNBA's.
CLUB_SEASONS = {'wnba': [('2025', '6813f4495f4f589b08802dbe'),
                         ('2026', '69dd3a83ee0695a6a40e384d')],
                'ncaa': [('2024-2025', '66c6294bac528f0cafb5ea59'),
                         ('2025-2026', '68a4bdab3c211b288250118f')]}


# Auth lives in synergy_auth: it reuses the token on disk while valid, then
# refreshes it with the refresh token, and only falls back to a full login if
# that fails. Full logins are what lock the account, so they are capped there.
import synergy_auth


def refresh_token():
    """Called on a 401. Renews without a login where possible."""
    return synergy_auth.on_401()


def headers():
    return synergy_auth.headers()


def get_games(s, H, season_id):
    # Refresh in place before each call. headers() reuses the token on disk when
    # it is still fresh, so this is a file read, not a network call -- but it
    # means an expiring token is renewed ahead of time instead of after a 401.
    H.update(headers())
    out, skip = [], 0
    while True:
        b = s.post(f'{BASE}/games', headers=H, timeout=60,
                   json={'seasonIds': [season_id], 'excludeGamesWithoutCompetition': False,
                         'take': 500, 'skip': skip}).json().get('result', [])
        out += b
        if len(b) < 500:
            return out
        skip += 500


def teams_in_tournament(games, spec):
    """Team ids taking part, restricted to one venue group when given."""
    ids = {}
    for g in games:
        if spec['competition'] not in ((g.get('competition') or {}).get('name') or ''):
            continue
        for side in ('homeTeam', 'awayTeam'):
            tm = g.get(side) or {}
            if not tm.get('id'):
                continue
            if 'teams' in spec and tm.get('name') not in spec['teams']:
                continue
            ids[tm['id']] = tm.get('name')
    return ids


def fetch_club_season(s, H, league_id, season_id):
    """Whole-league season totals for every player, in one call.

    The /playerswithboxscore endpoint returns only a player's last five games no
    matter what parameters are passed, so club "season totals" built from it were
    five-game windows. The leaderboards endpoint returns real season aggregates
    (gp, shot2/shot3/ft splits, possessions) and needs competitionType and
    rankingType set to 4; leaving them unset returns a 400.

    Paged, because the endpoint silently caps a response at `take`. An earlier
    single call with take=4096 returned exactly 4096 NCAA records for each
    season -- the limit, not the league. Division I women's basketball has
    appreciably more players than that, and because the ranking is descending
    the missing ones were the low-usage tail. A short page size that is paged to
    exhaustion is safer than a large one that might silently clip again.
    """
    PAGE = 2000
    out, skip = [], 0
    while True:
        # Renew in place: a full club scrape can outlive a ~10min token.
        H.update(headers())
        r = s.get(f'{BASE}/leaderboards/recordswithsparseranks', headers=H, timeout=120,
                  params={'leagueId': league_id, 'seasonId': season_id,
                          # playType 0 is total offence; 110 and the others are
                          # subsets, which is why Caitlin Clark came back with
                          # 115 possessions for a whole WNBA season.
                          'playType': 0, 'reportType': 0,
                          'competitionDefinitionKey': f'{league_id}:ALL',
                          'competitionType': 4, 'rankingType': 4,
                          'perGame': 'false', 'minPossessions': 0,
                          'minPossessionsPerGame': 'false', 'ascending': 'false',
                          'skip': skip, 'take': PAGE})
        if r.status_code == 401:
            H.update(refresh_token())
            continue
        if r.status_code != 200:
            print(f'   leaderboard failed: {r.status_code} {r.text[:120]}')
            return out
        batch = r.json().get('result', [])
        out += batch
        print(f'   page skip={skip}: {len(batch)} records (total {len(out)})', flush=True)
        if len(batch) < PAGE:
            return out
        skip += PAGE


def fetch_players(s, H, league_id, season_id, team_id, opponents=None):
    payload = {'competitionDefinitionKey': f'{league_id}:ALL', 'teamId': team_id}
    if opponents:
        payload['opponentTeamIds'] = opponents
    for attempt in range(3):
        try:
            r = s.post(f'{BASE}/leagues/{league_id}/seasons/{season_id}/playerswithboxscore',
                       headers=H, json=payload, timeout=45)
            if r.status_code == 200:
                return r.json().get('result', [])
            if r.status_code == 401:
                H.update(refresh_token())
                continue
        except Exception:
            pass
        time.sleep(2)
    return []


def totals(rec, competition=None, team_names=None):
    """Totals from a player's boxscore rows, restricted to one tournament.

    The endpoint returns every game the team played that season, so a Czech
    player's rows include EuroBasket alongside the World Cup qualifier. Filtering
    by competition name, and by the venue's team list where the four qualifying
    groups share one competition, keeps only the games in question.
    """
    g = []
    for x in rec.get('boxscore', []) or []:
        gm = x.get('game') or {}
        if competition and competition not in ((gm.get('competition') or {}).get('name') or ''):
            continue
        if team_names:
            sides = {(gm.get('homeTeam') or {}).get('name'), (gm.get('awayTeam') or {}).get('name')}
            if not sides <= team_names:
                continue
        g.append(x)
    t = {'gp': len(g)}
    # Synergy omits a field entirely when its value is zero, so .get(k) or 0 is
    # doing real work here rather than guarding against a malformed response.
    for k in ('secondsPlayed', 'possessions', 'points',
              'fieldGoalsMade', 'fieldGoalsAttempted',
              'threePtsMade', 'threePtsAttempted',
              'freeThrowsMade', 'freeThrowsAttempted',
              'offReb', 'defReb', 'assists', 'steals', 'blocks',
              'turnovers', 'fouls', 'blockedFGAs'):
        t[k] = sum((x.get(k) or 0) for x in g)
    # two-point shots are not a field; they are what is left after the threes
    t['twoPtsMade'] = t['fieldGoalsMade'] - t['threePtsMade']
    t['twoPtsAttempted'] = t['fieldGoalsAttempted'] - t['threePtsAttempted']
    return t


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s, H = requests.Session(), headers()

    # ---- FIBA tournaments -------------------------------------------------
    fiba = {}
    for spec in TOURNAMENTS:
        games = get_games(s, H, spec['season'])
        teams = teams_in_tournament(games, spec)
        print(f"\n{spec['key']}: {len(teams)} teams")
        opp = list(teams)
        for tid, tname in teams.items():
            recs = fetch_players(s, H, LEAGUES['fiba'], spec['season'], tid, opp)
            kept = 0
            for r in recs:
                pid = r.get('id')
                if not pid:
                    continue
                tot = totals(r, spec['competition'], spec.get('teams'))
                if tot['gp'] == 0:
                    continue
                fiba[f"{pid}|{spec['key']}"] = {
                    'player_id': pid, 'name': r.get('name'),
                    'nation': tname, 'tournament': spec['key'], **tot}
                kept += 1
            print(f"   {tname:16} {kept} players", flush=True)
    json.dump(fiba, open(OUT / 'fiba_players.json', 'w'), indent=1)
    print(f"\nFIBA: {len(fiba)} player-tournament rows -> fiba_players.json")

    # ---- club leagues -----------------------------------------------------
    for lg in ('wnba', 'ncaa'):
        club = {}
        for sname, sid in CLUB_SEASONS[lg]:
            recs = fetch_club_season(s, H, LEAGUES[lg], sid)
            print(f'\n{lg} {sname}: {len(recs)} player records', flush=True)
            for rec in recs:
                pr = rec.get('possessionReport') or {}
                pl = pr.get('player') or {}
                pid = pl.get('id')
                if not pid or not (pr.get('gp') or 0):
                    continue
                club[f'{pid}|{sname}'] = {
                    'player_id': pid, 'name': pl.get('name'),
                    'team': (pr.get('team') or {}).get('name'),
                    'season': sname,
                    'gp': pr.get('gp') or 0,
                    'possessions': pr.get('possessions') or 0,
                    'points': pr.get('pointMade') or 0,
                    'twoPtsMade': pr.get('shot2Made') or 0,
                    'twoPtsAttempted': pr.get('shot2Attempt') or 0,
                    'threePtsMade': pr.get('shot3Made') or 0,
                    'threePtsAttempted': pr.get('shot3Attempt') or 0,
                    'freeThrowsMade': pr.get('ftMade') or 0,
                    'freeThrowsAttempted': pr.get('ftAttempt') or 0,
                    'fieldGoalsMade': pr.get('fgMade') or 0,
                    'fieldGoalsAttempted': pr.get('fgAttempt') or 0,
                }
        json.dump(club, open(OUT / f'{lg}_players.json', 'w'), indent=1)
        gps = sorted(v['gp'] for v in club.values())
        med = gps[len(gps)//2] if gps else 0
        print(f'{lg}: {len(club)} player-seasons, median gp {med}, max gp {max(gps) if gps else 0}')


if __name__ == '__main__':
    main()
