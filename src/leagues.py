"""The leagues under comparison, in one place.

Adding a league should mean editing this file and nothing else. Previously the
pair ('wnba', 'ncaa') was written into six separate places across the scraper,
the fit and the dashboard, which is why a third league is a refactor rather than
a configuration change.

Colour slots are the categorical order of a palette validated for colour-vision
deficiency; the first three slots clear every all-pairs check in both light and
dark modes. Slot 3 (aqua) sits below 3:1 contrast on the light surface, so any
chart using it must carry direct labels -- which the forest rows and the audit
table both do.
"""

FIBA_ID = '54457dce300969b132fcfb41'      # FIBA - National Teams - Women

LEAGUES = {
    'ncaa': {
        'label': 'NCAA',
        'synergy_id': '54457dce300969b132fcfb38',   # College Women
        'seasons': [('2024-2025', '66c6294bac528f0cafb5ea59'),
                    ('2025-2026', '68a4bdab3c211b288250118f')],
        'light': '#2a78d6', 'dark': '#3987e5',      # slot 1, blue
    },
    'wnba': {
        'label': 'WNBA',
        'synergy_id': '54457dce300969b132fcfb35',
        'seasons': [('2025', '6813f4495f4f589b08802dbe'),
                    ('2026', '69dd3a83ee0695a6a40e384d')],
        'light': '#eb6834', 'dark': '#d95926',      # slot 2, orange
    },
    'euro': {
        'label': 'EuroLeague Women',
        # Not yet discovered. src/discover_leagues.py finds the ids; until then
        # this league is skipped everywhere rather than half-scraped.
        'synergy_id': None,
        'seasons': [],
        'light': '#1baf7a', 'dark': '#199e70',      # slot 3, aqua
    },
}

# The league every difference is quoted against. The WNBA is the professional
# benchmark a national-team selector is implicitly comparing to, so NCAA-WNBA
# and EuroLeague-WNBA are the two numbers the roster question actually asks.
REFERENCE = 'wnba'

# The control. Nobody guards a free throw, so its coefficient should be near
# zero; where it is not, it is measuring the environment rather than the league.
CONTROL = 'free throw'


def configured():
    """Leagues with enough configuration to scrape."""
    return [k for k, v in LEAGUES.items() if v['synergy_id'] and v['seasons']]


def label(key):
    return LEAGUES.get(key, {}).get('label', key)


def ordered(keys):
    """Keys in registry order, so colour assignment never depends on which
    leagues happen to be present in a given run."""
    return [k for k in LEAGUES if k in set(keys)]
