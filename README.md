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

The free-throw gap was **not** near zero. It came out at −3.1 points for the
NCAA and −3.2 for the WNBA: a drop of about three points in both leagues.

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

On the difference scale the control passes: the NCAA and WNBA free-throw gaps
differ by **+0.1 points**.

## Results

185 players matched across both environments (103 WNBA, 82 NCAA).

| Statistic | NCAA (adj.) | WNBA (adj.) | NCAA − WNBA |
|---|---|---|---|
| Free throw | +0.0 | +0.0 | **+0.1** ← control |
| Two point | −2.3 | +4.1 | **−7.4** |
| Three point | +1.4 | +4.2 | **−3.5** |
| Field goal | −0.7 | +7.3 | **−6.9** |

Adjusted figures have the −2.5 point FIBA environment offset removed.

**Reading:** an NCAA season overstates a player's finishing by roughly seven
points of two-point percentage relative to a WNBA season, but only about three
and a half points of three-point percentage. Perimeter shooting travels. Interior
scoring does not — unsurprising once the defenders are grown professionals.

## Limitations

Stated plainly, because they bound what the numbers can be used for.

- **Cell sizes are 39–78 players.** The three-point figure is the softest.
- **Players are matched by name, not ID.** Synergy issues a different player id
  per league, so the join is on normalised name. Pairs are written to
  `data/translation/matched_pairs.json` for inspection; the dashboard exposes
  them as an auditable view rather than a hidden assumption.
- **Selection.** Players who reach a national team are not a random sample of
  their league, and the ones who play enough FIBA minutes to qualify are a
  further cut.
- **The environment offset is estimated from one control statistic.** A −2.5
  point correction resting on free throws alone is the weakest link in the
  adjusted columns. The league *differences* do not depend on it.
- **Counting stats are absent.** Assists, rebounds and steals are not available
  from the endpoint used, so this covers shooting only.
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
