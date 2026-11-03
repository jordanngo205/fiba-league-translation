# Pipeline stages, in dependency order. Each stage is re-runnable on its own;
# only `scrape` touches the network, and it is the expensive one.
PY := python3
SRC := src

.PHONY: help auth scrape fit dash check all clean-derived

help:
	@echo "auth    one interactive Synergy login (saves a refresh token)"
	@echo "scrape  pull senior FIBA + NCAA/WNBA club seasons  [network]"
	@echo "fit     fit the translation coefficients"
	@echo "dash    render docs/index.html from the fit"
	@echo "check   run the test suite"
	@echo "all     fit + dash  (assumes data is already scraped)"

auth:
	$(PY) $(SRC)/do_auth.py

scrape:
	$(PY) $(SRC)/scrape_fiba_senior.py
	$(PY) $(SRC)/scrape_translation.py

fit:
	$(PY) $(SRC)/fit_translation.py

dash:
	$(PY) $(SRC)/build_dashboard.py

check:
	$(PY) -m unittest discover -s tests -v

all: fit dash

# Derived outputs only. The raw scrapes are expensive and are left alone.
clean-derived:
	rm -f data/translation/coefficients.json data/translation/matched_pairs.json
	rm -f docs/index.html
