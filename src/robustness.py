#!/usr/bin/env python3
"""Robustness checks on the translation coefficients.

A coefficient that only exists at one arbitrary sample threshold is not a
finding. These sweeps ask whether the headline survives being made harder to
produce, and write the answer out for the dashboard.

Three checks:

  thresholds  re-fit across minimum-sample cutoffs. The default FIBA minimum of
              eight attempts is low enough that a single tournament can qualify
              a player; if the result only holds there, it is an artefact.

  influence   leave-one-player-out. A difference that moves materially when one
              player is removed rests on that player, not on the league.

  per-event   the environment offset estimated separately per competition. The
              offset is assumed common to all FIBA play; this asks whether a
              World Cup qualifier and an AfroBasket really cost the same.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from paths import DATA  # noqa: E402
import fit_translation as F  # noqa: E402

STATS = ('free throw', 'two point', 'three point')


def diff_of(res, stat):
    for d in res['diffs']:
        if d['stat'] == stat:
            return d
    return None


def sweep_thresholds(pairs, leagues):
    """Re-fit at progressively stricter minimum samples."""
    grid = [(40, 8), (40, 15), (40, 25), (40, 40),
            (100, 15), (200, 15), (200, 25)]
    rows = []
    print(f"\n{'min club':>9} {'min FIBA':>9} " +
          ' '.join(f'{s:>22}' for s in STATS))
    for mc, mf in grid:
        res = F.fit(pairs, leagues, min_club=mc, min_fiba=mf, verbose=False)
        row = {'min_club': mc, 'min_fiba': mf, 'stats': {}}
        cells = {(c['stat'], c['league']): c for c in res['cells']}
        out = []
        for s in STATS:
            d = diff_of(res, s)
            if not d:
                out.append(f'{"--":>22}')
                continue
            n = min(cells[(s, 'ncaa')]['n'], cells[(s, 'wnba')]['n'])
            row['stats'][s] = {'diff': d['diff_raw'], 'lo': d['diff_ci_lo'],
                               'hi': d['diff_ci_hi'], 'min_n': n}
            out.append(f'{100 * d["diff_raw"]:+6.1f} '
                       f'[{100 * d["diff_ci_lo"]:+5.1f},'
                       f'{100 * d["diff_ci_hi"]:+5.1f}] n{n:>3}')
        rows.append(row)
        print(f'{mc:>9} {mf:>9} ' + ' '.join(out))
    return rows


def leave_one_out(pairs, leagues, stat='two point'):
    """Refit once per removed player and report the largest swings."""
    base = diff_of(F.fit(pairs, leagues, verbose=False), stat)
    if not base:
        return {}
    swings = []
    names = sorted({(p[2].get('_name'), p[0]) for p in pairs})
    for name, lg in names:
        kept = [p for p in pairs
                if not (p[2].get('_name') == name and p[0] == lg)]
        d = diff_of(F.fit(kept, leagues, verbose=False), stat)
        if d:
            swings.append((d['diff_raw'] - base['diff_raw'], name, lg))
    swings.sort(key=lambda t: -abs(t[0]))
    print(f'\nleave-one-out on "{stat}" '
          f'(base {100 * base["diff_raw"]:+.2f})')
    for delta, name, lg in swings[:6]:
        print(f'   without {name[:24]:26} {lg:5} '
              f'{100 * (base["diff_raw"] + delta):+6.2f}  '
              f'({100 * delta:+.2f})')
    worst = swings[0] if swings else (0, None, None)
    return {'stat': stat, 'base': base['diff_raw'],
            'max_abs_swing': abs(worst[0]),
            'max_swing_player': worst[1], 'max_swing_league': worst[2],
            'n_refits': len(swings),
            'top': [{'delta': d, 'name': n, 'league': l}
                    for d, n, l in swings[:10]]}


def offset_by_competition():
    """Free-throw gap per FIBA competition.

    The method assumes one environment offset for all FIBA play. If the offset
    is really a property of the event rather than of FIBA, that assumption is
    doing unearned work.
    """
    fiba = json.load(open(DATA / 'fiba_senior.json'))
    club = {}
    for lg in ('wnba', 'ncaa'):
        for v in json.load(open(DATA / f'{lg}_players.json')).values():
            k = F.norm(v['name'])
            c = club.setdefault(k, defaultdict(float))
            c['freeThrowsMade'] += v['freeThrowsMade']
            c['freeThrowsAttempted'] += v['freeThrowsAttempted']

    per = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0])
    for v in fiba.values():
        k = F.norm(v['name'])
        c = club.get(k)
        fa = v.get('freeThrowsAttempted') or 0
        if not c or fa < 8 or c['freeThrowsAttempted'] < 40:
            continue
        e = per[v['competition']]
        e[0] += v['freeThrowsMade']; e[1] += fa
        e[2] += c['freeThrowsMade']; e[3] += c['freeThrowsAttempted']
        e[4] += 1

    rows = []
    print('\nfree-throw gap by competition (the control, per event)')
    for comp, (fm, fa, cm, ca, n) in sorted(
            per.items(), key=lambda kv: -kv[1][4]):
        if n < 5:
            continue
        gap = fm / fa - cm / ca
        rows.append({'competition': comp, 'n': n, 'gap': gap,
                     'fiba_att': fa})
        print(f'   {comp[:46]:48} n={n:>3}  {100 * gap:+5.1f}')
    return rows


def main():
    pairs, leagues = F.load_pairs()
    out = {'thresholds': sweep_thresholds(pairs, leagues),
           'influence': leave_one_out(pairs, leagues, 'two point'),
           'influence_3pt': leave_one_out(pairs, leagues, 'three point'),
           'offset_by_competition': offset_by_competition()}
    json.dump(out, open(DATA / 'robustness.json', 'w'), indent=1)
    print(f'\nwrote robustness.json')


if __name__ == '__main__':
    main()
