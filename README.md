# FIBA League Translation

How much of a player's club shooting survives the jump to senior international
basketball — measured separately for the NCAA and the WNBA, one coefficient per
statistic per league.

## The question

A national-team selector picks from players who have played a handful of games
in a national-team jersey and several full seasons somewhere else. The club
seasons hold almost all of the information, but they are not measured on a
common scale: a 52% two-point season in the NCAA and a 52% two-point season in
the WNBA are not the same accomplishment.

FIBA competition is the bridge. Players arrive at the same tournaments from
different club leagues, so the tournament is a common reference frame. If a
player's rate drops going from her club league to FIBA, and the same drop shows
up across many players from that league, that drop is a property of the league
rather than of the player.

## Method

**Level 1 — the player.** For each player who appears in both a club league and
a senior FIBA competition, take the gap between her club rate and her FIBA rate.
Weight each player by her sample size.

**Level 2 — the league.** Pool those gaps into a per-league coefficient, shrunk
toward the across-league mean in proportion to its precision (a random-effects
meta-analysis, DerSimonian–Laird). A raw mean of a handful of noisy gaps is not
a coefficient; shrinkage is the same idea applied to the players, one level up.

Only efficiency is compared, never volume. A player's role changes between club
and national team, and counting production would absorb that change as though it
were league quality.

### Free throws are the control

Nobody guards a free throw. Same rim, same distance, same mechanics. If the
method is measuring league difficulty, the free-throw coefficient should come
out near zero. It is run first and reported first, as a check rather than as a
result.

## What the control revealed

The free-throw gap was **not** near zero. It came out at -3.3 points for the
NCAA and -3.2 for the WNBA: a drop of about three points in both leagues.

That cannot be league difficulty, because nobody defends a free throw. It is a
flat cost of playing FIBA at all — travel, unfamiliar teammates, a different
ball, compressed schedules, higher stakes. And because it is common to both
leagues, it sits on every absolute gap alike.

The consequence is the main methodological finding here:

> **Absolute club→FIBA gaps are not interpretable as league strength. The
> difference between two leagues is, because the shared offset cancels.**

That difference is also the quantity a selector actually needs, since the
question is how an NCAA season compares with a WNBA season — not how either
compares with a tournament nobody is choosing between.

On the difference scale the control passes, at **-0.1 points**.

## Results

260 players matched across both environments
(151 NCAA, 109 WNBA);
172 clear the minimum-sample thresholds and enter a coefficient.

| Statistic | NCAA (adj.) | WNBA (adj.) | NCAA − WNBA | 95% CI | |
|---|---|---|---|---|---|
| Free Throw | +0.0 | +0.0 | **-0.1** | -4.4 to +4.3 | control |
| Two Point | -2.4 | +4.8 | **-8.4** | -11.5 to -5.3 | **excludes zero** |
| Three Point | +1.3 | +4.6 | **-3.6** | -7.5 to +0.2 | crosses zero |

Adjusted figures have the -2.4 point FIBA environment offset removed.
The difference column does not depend on that adjustment.

**What can be claimed.** An NCAA season overstates a player's two-point shooting
by roughly eight points relative to a WNBA season, and that interval is clear of
zero. The three-point difference is smaller and its interval **crosses zero**, so
on this sample it cannot be distinguished from no difference at all and is not a
result. The contrast between the two — interior scoring translating much worse
than perimeter shooting — is the suggestive part, but only one half of it is
established.

**The control deserves the same scepticism.** Passing at -0.1 sounds clean, but its
interval spans about nine points: it could not have detected an offset difference
the size of the three-point effect. It bounds the method loosely, not tightly.

## Robustness

A coefficient that exists only at one arbitrary sample threshold is not a
finding. `src/robustness.py` re-fits everything under three kinds of pressure.

**Minimum sample.** The default FIBA minimum of eight attempts is low enough
that one tournament can qualify a player. Re-fitting at stricter cutoffs:

| min club | min FIBA | Two point | Three point |
|---|---|---|---|
| 40 | 8 | -8.4 [-11.5, -5.3] | -3.6 [-7.5, +0.2] |
| 40 | 15 | -7.6 [-10.8, -4.4] | -3.3 [-7.6, +0.9] |
| 40 | 25 | -7.1 [-10.5, -3.6] | -2.8 [-8.2, +2.6] |
| 100 | 15 | -7.0 [-10.4, -3.6] | -3.9 [-8.6, +0.7] |
| 200 | 15 | -9.9 [-13.9, -6.0] | -1.9 [-7.7, +4.0] |
| 200 | 25 | -9.2 [-13.5, -4.9] | -1.6 [-8.4, +5.3] |

The two-point difference excludes zero at every cutoff. The three-point
difference crosses zero at every one, which settles it as a non-result rather
than a borderline one. The control degrades at the strictest cutoffs, where it
is down to a handful of players — it bounds the method only where it has sample.

**Influence.** Leave-one-player-out, refitting once per removed player: the
two-point difference moves by at most 0.51 points across
260 refits, and the three-point difference by at most
0.67. No single player carries either result.

**Is the offset really one number?** This is the uncomfortable one. The method
assumes a single FIBA environment offset, but estimated per competition the
free-throw gap runs from +3.1 at FIBA Eurobasket Qualifications
to -5.9 at Olympic Pre-Qualifying Tournament — a spread of about
9 points around a pooled -2.4.

The offset looks like a property of the event rather than of FIBA. That
**weakens the adjusted per-league columns** and leaves the **league differences
untouched**, since a difference cancels whatever the offset is. It is a stronger
reason to lead with the differences than the control alone provided.

## Limitations

Stated plainly, because they bound what the numbers can be used for.

- **Cell sizes are 43–89 players.** The three-point difference does not
  clear zero and is not a result.
- **Players are matched by name, not ID.** Synergy issues a different player id
  per league, so the join is on normalised name. Pairs are written to
  `data/translation/matched_pairs.json` for inspection; the dashboard exposes
  them as an auditable view rather than a hidden assumption.
- **Selection.** Players who reach a national team are not a random sample of
  their league, and the ones who play enough FIBA minutes to qualify are a
  further cut.
- **The environment offset is not one number.** Estimated per competition it
  spans about nine points, so a single pooled correction is papering over real
  heterogeneity. This is the weakest link in the adjusted per-league columns.
  The league *differences* do not depend on it at all.
- **Counting stats are absent.** Assists, rebounds and steals are not available
  from the endpoint used, so this covers shooting only.
- **Field goals are excluded.** The club endpoint's `fgMade`/`fgAttempt` are not
  field goals — A'ja Wilson's 2025 season reads 950/1940 against a true 2PM+3PM
  of 459/931, and the points identity closes only on the explicit shot fields.
  Two- and three-pointers use those verified fields and are unaffected.
- **Intervals are approximate.** The shrunk estimate's variance treats its two
  components as independent and ignores uncertainty in the between-league
  variance.
- **Season pairing is coarse.** Club seasons are matched to tournaments by year
  rather than by what preceded what.

## Layout

```
src/
  synergy_auth.py        session handling: reuse -> refresh -> login
  do_auth.py             one interactive login, saves the refresh token
  synergy_functions.py   Synergy OAuth/PKCE flow
  scrape_fiba_senior.py  all senior FIBA competitions, youth excluded
  scrape_translation.py  NCAA and WNBA club seasons
  fit_translation.py     two-level shrinkage, control first
  build_dashboard.py     renders docs/index.html
data/translation/        derived results (raw scrapes are gitignored)
docs/index.html          the dashboard
```

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env          # add Synergy credentials
python src/do_auth.py         # one login; saves a refresh token
python src/scrape_fiba_senior.py
python src/scrape_translation.py
python src/fit_translation.py
python src/build_dashboard.py
```

A note on auth: Synergy locks an account after a handful of rapid logins, and
returns "Invalid username or password" when it does — indistinguishable from a
wrong password. `synergy_auth.py` exists because of that: it reuses the token on
disk, refreshes it with the rotating refresh token when it expires, and only
falls back to a full login as a capped last resort. A full scrape costs one
login.

## Data

Synergy Sports, via the Basketball TeamSite API. Senior FIBA competitions
2025–2026, NCAA 2024–25 and 2025–26, WNBA 2025 and 2026. Women's basketball
throughout. Raw data is licensed and not redistributed here.
