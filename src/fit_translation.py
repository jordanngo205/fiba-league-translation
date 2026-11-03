#!/usr/bin/env python3
"""Per-statistic league translation coefficients, with shrinkage at two levels.

Level 1  a player's own gap between club and FIBA, weighted by her sample
Level 2  a league's coefficient, shrunk toward the global mean across leagues

Level 2 is the part that matters when a league sends three players. A raw mean
of three noisy gaps is not a coefficient; shrinking it toward the global mean in
proportion to its precision is the same idea used on the players, one level up.
This is a random-effects meta-analysis, and the estimator is the one Efron and
Morris demonstrated on group means.

Only efficiency is compared, never volume. A player's role changes between club
and national team, and counting production would absorb that as though it were
league quality.

Free throws are the placebo. Same rim, same distance, nobody guarding: the gap
should be near zero. If it is not, the model is measuring something other than
league difficulty and no other coefficient should be believed.
"""
import json, math, re, unicodedata
from datetime import date
from collections import defaultdict
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from paths import DATA as T  # noqa: E402

# (label, made, attempted). Free throws first: it is the check, not a result.
SHOOTING = [('free throw', 'freeThrowsMade', 'freeThrowsAttempted'),
            ('two point',  'twoPtsMade',     'twoPtsAttempted'),
            ('three point','threePtsMade',   'threePtsAttempted')]

# Field goals are deliberately absent. On the club leaderboard endpoint the
# fgMade/fgAttempt fields are not field goals in the standard sense: for
# A'ja Wilson's 2025 season they read 950/1940 against a true 2PM+3PM of
# 459/931, roughly double. The giveaway is the points identity, which closes
# exactly on the explicit shot fields and not at all on the fg ones:
#     2*427 + 3*32 + 334 = 1284 = reported points
# while 950 made field goals plus 334 free throws could not produce 1284 points
# under any arithmetic. The FIBA boxscore endpoint's fg fields ARE standard --
# all 1,680 rows satisfy the identity -- so this is an endpoint difference, not
# a league one, and it only ever corrupted the club side.
#
# Two- and three-pointers are unaffected: both sides use the explicit, verified
# shot2/shot3 fields, and field goals added nothing those two did not already
# decompose.

MIN_CLUB_ATT = 40      # club sample needed before a player's gap means anything
MIN_FIBA_ATT = 8


def ca_club(c, att):
    return c[att]


def norm(n):
    """Normalised join key for a player name.

    Accents are folded to their base letter rather than deleted. Stripping
    non-ASCII outright maps "Dugalic" to dugalic but "Dugalic" with its acute
    accent to dugali, so the two spellings of one player never meet. FIBA
    records carry no diacritics while club records do, so every accented club
    name was failing to match in silence -- folding recovers seven of them.
    """
    s = unicodedata.normalize('NFKD', n or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z]', '', s.lower())


def pooled(rows, made, att):
    m = sum(r[made] for r in rows)
    a = sum(r[att] for r in rows)
    return (m / a if a else None), a


def shrink_groups(groups):
    """Random-effects pooling of per-league gaps.

    groups: {league: [(gap, variance), ...]}
    Returns {league: (shrunk gap, n, raw gap)}.

    tau2 is the spread of true league effects, estimated by DerSimonian-Laird.
    Where it is near zero the leagues are indistinguishable and everything
    collapses to the global mean, which is the correct answer rather than a
    failure: it says the data cannot tell the leagues apart.
    """
    flat = [(g, v) for lst in groups.values() for g, v in lst]
    if not flat:
        return {}
    # global mean, inverse-variance weighted
    W = sum(1 / v for _, v in flat if v > 0)
    mu = sum(g / v for g, v in flat if v > 0) / W

    # between-league variance
    means = {}
    for lg, lst in groups.items():
        w = sum(1 / v for _, v in lst if v > 0)
        if w <= 0:
            continue
        means[lg] = (sum(g / v for g, v in lst if v > 0) / w, 1 / w)
    if len(means) < 2:
        return {lg: (m, len(groups[lg]), m, 1.0, math.sqrt(v), math.sqrt(v))
                for lg, (m, v) in means.items()}

    Q = sum((m - mu) ** 2 / v for m, v in means.values())
    df = len(means) - 1
    c = sum(1 / v for _, v in means.values()) - \
        sum(1 / v ** 2 for _, v in means.values()) / sum(1 / v for _, v in means.values())
    tau2 = max(0.0, (Q - df) / c) if c > 0 else 0.0

    var_mu = 1 / W if W > 0 else 0.0
    out = {}
    for lg, (m, v) in means.items():
        w = tau2 / (tau2 + v) if (tau2 + v) > 0 else 0.0   # weight on own data
        # Standard error of the shrunk estimate. The shrunk value is a blend of
        # the league's own mean and the global mean, so its variance blends the
        # two as well. Treating them as independent slightly understates the
        # result and it ignores uncertainty in tau2 itself, so these intervals
        # are approximate -- but a shrunk point estimate with no interval at all
        # invites being read as precise, which is worse.
        se = math.sqrt(w * w * v + (1 - w) * (1 - w) * var_mu)
        out[lg] = (w * m + (1 - w) * mu, len(groups[lg]), m, w,
                   se, math.sqrt(v))
    return out


def load_pairs():
    """Join FIBA records to club records on normalised name.

    Returns [(league, fiba_totals, club_totals), ...]. Club seasons are summed
    per player, so a two-season NCAA career is one club line.
    """
    fiba = json.load(open(T / 'fiba_senior.json'))
    clubs = {}
    for lg in ('wnba', 'ncaa'):
        idx = defaultdict(lambda: defaultdict(float))
        for v in json.load(open(T / f'{lg}_players.json')).values():
            k = norm(v['name'])
            for f, val in v.items():
                if isinstance(val, (int, float)):
                    idx[k][f] += val
            idx[k]['_name'] = v['name']
            idx[k]['_team'] = v['team']
        clubs[lg] = idx

    # pool a player's FIBA lines across competitions
    f_idx = defaultdict(lambda: defaultdict(float))
    for v in fiba.values():
        k = norm(v['name'])
        for f, val in v.items():
            if isinstance(val, (int, float)):
                f_idx[k][f] += val
        f_idx[k]['_name'] = v['name']
        f_idx[k]['_nation'] = v['nation']

    pairs = [(lg, f_idx[k], clubs[lg][k]) for k in f_idx
             for lg in clubs if k in clubs[lg]]
    return pairs, sorted(clubs)


def fit(pairs, leagues, min_club=MIN_CLUB_ATT, min_fiba=MIN_FIBA_ATT,
        verbose=True):
    """Fit every statistic at the given sample thresholds.

    Separated from main so the thresholds can be swept without re-reading or
    re-joining the data -- robustness.py relies on this.
    """
    clubs = {lg: None for lg in leagues}
    if verbose:
        print(f'matched players: {len(pairs)}')
        for lg in clubs:
            print(f'   {lg}: {sum(1 for p in pairs if p[0] == lg)}')

    if verbose:
        print(f"\n{'statistic':13} {'league':6} {'n':>4} {'club':>7} {'FIBA':>7} "
              f"{'raw gap':>8} {'shrunk':>8} {'own wt':>7}")
    keep, raws, cells, players, ses = {}, {}, [], [], {}
    for label, made, att in SHOOTING:
        groups = defaultdict(list)
        cell = {}
        subs = {}
        for lg in clubs:
            sub = [(f, c) for l, f, c in pairs if l == lg
                   and c[att] >= min_club and f[att] >= min_fiba]
            if len(sub) >= 3:
                subs[lg] = sub

        # One pooled rate for the whole statistic, used only to build the
        # weights. Using each player's OWN observed rate here is a trap: a
        # player who went 8/8 in FIBA has an observed rate of 1.0, so her
        # p(1-p) term is exactly zero, her variance collapses and her
        # inverse-variance weight explodes. Players at 0% do the same. The
        # extremes then dominate the mean in both directions, which is what
        # made free throws read +4.9 against a raw gap of -3.1.
        # Weights must depend on sample size, not on how the sample landed.
        all_rows = [r for sub in subs.values() for pair in sub for r in pair]
        pbar = pooled(all_rows, made, att)[0] or 0.5
        pq = pbar * (1 - pbar)

        for lg, sub in subs.items():
            for f, c in sub:
                cr, ca = f[made] / f[att], f[att]
                kr, ka = c[made] / c[att], c[att]
                gap = cr - kr
                players.append({'stat': label, 'league': lg,
                                'name': c['_name'], 'fiba_name': f['_name'],
                                'team': c['_team'], 'nation': f['_nation'],
                                'club_made': c[made], 'club_att': ca_club(c, att),
                                'club_rate': kr, 'fiba_made': f[made],
                                'fiba_att': ca, 'fiba_rate': cr, 'gap': gap})
                # variance of a difference of two proportions, evaluated at the
                # common rate so the weight is a function of attempts alone
                var = pq * (1 / ca + 1 / ka)
                groups[lg].append((gap, max(var, 1e-9)))
            cell[lg] = (len(sub),
                        pooled([c for _, c in sub], made, att)[0],
                        pooled([f for f, _ in sub], made, att)[0])
        res = shrink_groups(groups)
        for lg in sorted(cell):
            n, cl, fb = cell[lg]
            r = res.get(lg)
            if not r:
                continue
            shrunk, _, raw = r[0], r[1], r[2]
            w = r[3] if len(r) > 3 else 1.0
            se_shrunk = r[4] if len(r) > 4 else 0.0
            se_raw = r[5] if len(r) > 5 else 0.0
            ses[(label, lg)] = (se_shrunk, se_raw)
            if verbose:
                print(f'{label:13} {lg:6} {n:4} {100*cl:6.1f}% {100*fb:6.1f}% '
                      f'{100*(fb-cl):+7.1f} {100*shrunk:+7.1f} {w:6.0%}')
            keep[(label, lg)] = shrunk
            raws[(label, lg)] = fb - cl
            cells.append({'stat': label, 'league': lg, 'n': n,
                          'club': cl, 'fiba': fb, 'raw_gap': fb - cl,
                          'shrunk': shrunk, 'own_weight': w,
                          'se_shrunk': se_shrunk, 'se_raw': se_raw,
                          'ci_lo': shrunk - 1.96 * se_shrunk,
                          'ci_hi': shrunk + 1.96 * se_shrunk,
                          'is_control': label == 'free throw'})

    # ---- what the placebo forces us to do -------------------------------
    #
    # The free-throw gap came out near -3 points in BOTH leagues. Nobody
    # guards a free throw, so that cannot be league difficulty. It is a
    # common cost of playing FIBA at all -- travel, unfamiliar teammates, a
    # different ball, less rest -- and it sits on every absolute gap alike.
    #
    # So the absolute gaps are not interpretable as league strength, but the
    # DIFFERENCE between two leagues is: the shared offset cancels. That is
    # the number the roster decision needs anyway, since it asks how an NCAA
    # season compares with a WNBA season, not how either compares with FIBA.
    offset, diffs = 0.0, []
    base = keep.get(('free throw', 'ncaa')), keep.get(('free throw', 'wnba'))
    if all(b is not None for b in base):
        offset = sum(base) / 2
        if verbose:
            print(f"\nFIBA environment offset, from the free-throw placebo: "
                  f"{100*offset:+.1f} pts")
            print('Absolute gaps carry this offset; league differences do not.\n')
            print(f"{'statistic':13} {'NCAA adj':>9} {'WNBA adj':>9} "
                  f"{'diff(shr)':>10} {'diff(raw)':>10}")
        for label, _, _ in SHOOTING:
            a, b = keep.get((label, 'ncaa')), keep.get((label, 'wnba'))
            if a is None or b is None:
                continue
            # Report the RAW league difference as well. Where shrinkage put 0%
            # weight on a league's own data both leagues collapse to the same
            # pooled value, so the shrunk difference is forced to zero and is
            # no longer an independent check. The raw difference still is.
            ra, rb = raws[(label, 'ncaa')], raws[(label, 'wnba')]
            tag = '   <- placebo, should be ~0' if label == 'free throw' else ''
            if verbose:
                print(f'{label:13} {100*(a-offset):+8.1f}  {100*(b-offset):+8.1f}  '
                      f'{100*(a-b):+9.1f} {100*(ra-rb):+9.1f}{tag}')
            # The difference cancels the shared FIBA offset, so it needs no
            # adjustment and no assumption about the control. Its interval comes
            # from the two leagues' own standard errors.
            sa, sb = ses[(label, 'ncaa')][1], ses[(label, 'wnba')][1]
            se_d = math.sqrt(sa * sa + sb * sb)
            diffs.append({'stat': label,
                          'ncaa_adj': a - offset, 'wnba_adj': b - offset,
                          'diff_shrunk': a - b, 'diff_raw': ra - rb,
                          'se_diff': se_d,
                          'diff_ci_lo': (ra - rb) - 1.96 * se_d,
                          'diff_ci_hi': (ra - rb) + 1.96 * se_d,
                          'is_control': label == 'free throw'})

    return {'fitted_on': date.today().isoformat(),
            'offset': offset, 'cells': cells, 'diffs': diffs,
            'players': players,
            'matched': {'total': len(pairs),
                        'by_league': {lg: sum(1 for p in pairs if p[0] == lg)
                                      for lg in leagues}},
            'min_club_att': min_club, 'min_fiba_att': min_fiba}


def main():
    pairs, leagues = load_pairs()
    res = fit(pairs, leagues)

    # Write results out so the dashboard is rendered from data rather than from
    # numbers retyped by hand. matched_pairs carries every player-level row that
    # backs a coefficient, because the club-to-FIBA join is on name rather than
    # id and needs to be auditable rather than trusted.
    T.mkdir(parents=True, exist_ok=True)
    players = res.pop('players')
    json.dump(res, open(T / 'coefficients.json', 'w'), indent=1)
    json.dump(players, open(T / 'matched_pairs.json', 'w'), indent=1)
    print(f"\nwrote coefficients.json ({len(res['cells'])} cells) and "
          f'matched_pairs.json ({len(players)} player-stat rows)')


if __name__ == '__main__':
    main()
