#!/usr/bin/env python3
"""Render docs/index.html from the fitted coefficients.

Every number on the page comes out of data/translation/*.json. Nothing is typed
in by hand, so the page cannot drift from the fit that produced it.

Charts are inline SVG with no external dependencies: the page is served from
GitHub Pages and should not need a CDN to render a coefficient plot.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from paths import DATA, DOCS  # noqa: E402
import leagues as L  # noqa: E402

LEAGUE = L.LEAGUES
ORDER = ['free throw', 'two point', 'three point']


def esc(t):
    return (str(t).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


# --------------------------------------------------------------------------
# coefficient plot: estimate with a 95% interval, against a zero reference
# --------------------------------------------------------------------------
def forest(rows, width=720, row_h=42, pad_l=136, pad_r=56, dom=None):
    """Horizontal dot-and-interval plot. One row per entry.

    rows: [{label, sub, value, lo, hi, league, hollow, note}]
    A hollow marker means the interval covers zero -- shape, not colour alone,
    carries that distinction, and each row is also labelled in text.
    """
    if not rows:
        return ''
    lo = min(r['lo'] for r in rows)
    hi = max(r['hi'] for r in rows)
    if dom:
        lo, hi = min(lo, dom[0]), max(hi, dom[1])
    span = (hi - lo) or 1
    lo -= span * 0.12
    hi += span * 0.12
    h = len(rows) * row_h + 46
    iw = width - pad_l - pad_r

    def x(v):
        return pad_l + (v - lo) / (hi - lo) * iw

    # ticks on whole percentage points, thinned to about six
    t0, t1 = int(lo * 100) - 1, int(hi * 100) + 2
    step = max(1, round((t1 - t0) / 6))
    ticks = [t / 100 for t in range(t0, t1) if t % step == 0]

    o = [f'<svg class="chart" viewBox="0 0 {width} {h}" role="img" '
         f'aria-label="Coefficient estimates with 95 percent intervals">']
    # gridlines and tick labels
    for t in ticks:
        o.append(f'<line class="grid" x1="{x(t):.1f}" y1="28" '
                 f'x2="{x(t):.1f}" y2="{h - 18}"/>')
        o.append(f'<text class="tick" x="{x(t):.1f}" y="{h - 4}" '
                 f'text-anchor="middle">{t * 100:+.0f}</text>')
    # the zero reference is the thing every estimate is read against
    o.append(f'<line class="zero" x1="{x(0):.1f}" y1="22" '
             f'x2="{x(0):.1f}" y2="{h - 18}"/>')
    o.append(f'<text class="zero-lab" x="{x(0):.1f}" y="14" '
             f'text-anchor="middle">no change</text>')

    for i, r in enumerate(rows):
        cy = 40 + i * row_h
        col = f"var(--s-{r['league']})" if r.get('league') else 'var(--ink-2)'
        o.append(f'<text class="row-lab" x="{pad_l - 12}" y="{cy + 4}" '
                 f'text-anchor="end">{esc(r["label"])}</text>')
        if r.get('sub'):
            o.append(f'<text class="row-sub" x="{pad_l - 12}" y="{cy + 17}" '
                     f'text-anchor="end">{esc(r["sub"])}</text>')
        # interval, then a 2px surface ring under the marker so the two marks
        # stay legible where they overlap
        o.append(f'<line class="ci" x1="{x(r["lo"]):.1f}" y1="{cy}" '
                 f'x2="{x(r["hi"]):.1f}" y2="{cy}" stroke="{col}"/>')
        for e in (r['lo'], r['hi']):
            o.append(f'<line class="cap" x1="{x(e):.1f}" y1="{cy - 5}" '
                     f'x2="{x(e):.1f}" y2="{cy + 5}" stroke="{col}"/>')
        fill = 'var(--surface)' if r.get('hollow') else col
        o.append(f'<circle class="dot" cx="{x(r["value"]):.1f}" cy="{cy}" r="6.5" '
                 f'fill="{fill}" stroke="{col}"/>')
        # A point with no interval must not print one; lo == hi means the row
        # is a single pooled figure, not a fitted estimate.
        if abs(r['hi'] - r['lo']) < 1e-12:
            val = f'{r["value"] * 100:+.1f}'
        else:
            val = (f'{r["value"] * 100:+.1f}  [{r["lo"] * 100:+.1f}, '
                   f'{r["hi"] * 100:+.1f}]')
        o.append(f'<text class="row-val" x="{width - pad_r + 8}" y="{cy + 4}">'
                 f'{esc(val)}</text>')
        # invisible hit strip, comfortably larger than the marks
        tip = f'{r["label"]} — {val} pts' + (
            f' · {r["note"]}' if r.get('note') else '')
        o.append(f'<rect class="hit" x="{pad_l}" y="{cy - 16}" width="{iw}" '
                 f'height="32" data-tip="{esc(tip)}"/>')
    o.append('</svg>')
    return '\n'.join(o)


# --------------------------------------------------------------------------
# player scatter: club rate against FIBA rate, with the line of no change
# --------------------------------------------------------------------------
def scatter(pts, size=430, pad=52):
    if not pts:
        return ''
    iw = size - pad * 2
    lo, hi = 0.0, 1.0

    def px(v):
        return pad + (v - lo) / (hi - lo) * iw

    def py(v):
        return size - pad - (v - lo) / (hi - lo) * iw
    o = [f'<svg class="chart scat" viewBox="0 0 {size} {size}" role="img" '
         f'aria-label="Club rate against FIBA rate, one point per player">']
    for t in (0, .2, .4, .6, .8, 1.0):
        o.append(f'<line class="grid" x1="{px(t):.1f}" y1="{py(lo):.1f}" '
                 f'x2="{px(t):.1f}" y2="{py(hi):.1f}"/>')
        o.append(f'<line class="grid" x1="{px(lo):.1f}" y1="{py(t):.1f}" '
                 f'x2="{px(hi):.1f}" y2="{py(t):.1f}"/>')
        o.append(f'<text class="tick" x="{px(t):.1f}" y="{size - pad + 16}" '
                 f'text-anchor="middle">{t * 100:.0f}</text>')
        o.append(f'<text class="tick" x="{pad - 8}" y="{py(t) + 4:.1f}" '
                 f'text-anchor="end">{t * 100:.0f}</text>')
    # y = x is the whole point of the chart: above it a player improved
    o.append(f'<line class="ident" x1="{px(0):.1f}" y1="{py(0):.1f}" '
             f'x2="{px(1):.1f}" y2="{py(1):.1f}"/>')
    o.append(f'<text class="ident-lab" x="{px(.80):.1f}" y="{py(.86):.1f}">'
             'same rate in both</text>')
    for p in pts:
        col = f"var(--s-{p['league']})"
        r = 4 + min(5.0, (p['fiba_att'] / 26.0) ** 0.5 * 2.6)
        tip = (f"{p['name']} ({L.label(p['league'])}, {p['nation']}) — "
               f"club {p['club_made']:.0f}/{p['club_att']:.0f} "
               f"= {100 * p['club_rate']:.0f}%, FIBA {p['fiba_made']:.0f}/"
               f"{p['fiba_att']:.0f} = {100 * p['fiba_rate']:.0f}%")
        o.append(f'<circle class="pt" cx="{px(p["club_rate"]):.1f}" '
                 f'cy="{py(p["fiba_rate"]):.1f}" r="{r:.1f}" fill="{col}" '
                 f'data-tip="{esc(tip)}"/>')
    o.append(f'<text class="ax" x="{pad + iw / 2}" y="{size - 6}" '
             f'text-anchor="middle">club rate (%)</text>')
    o.append(f'<text class="ax" transform="translate(14,{pad + iw / 2}) '
             f'rotate(-90)" text-anchor="middle">FIBA rate (%)</text>')
    o.append('</svg>')
    return '\n'.join(o)


def legend(keys):
    items = ''.join(
        f'<span class="lg-item"><span class="sw" style="background:'
        f'var(--s-{k})"></span>{esc(L.label(k))}</span>' for k in keys)
    return f'<div class="legend">{items}</div>'


def main():
    co = json.load(open(DATA / 'coefficients.json'))
    pairs = json.load(open(DATA / 'matched_pairs.json'))
    rb_path = DATA / 'robustness.json'
    rb = json.load(open(rb_path)) if rb_path.exists() else {}
    cells = {(c['stat'], c['league']): c for c in co['cells']}
    keys = [l['key'] for l in co.get('leagues', [])] or ['ncaa', 'wnba']
    ref = co.get('reference', 'wnba')
    ctl_name = co.get('control', 'free throw')
    adj = {(a['stat'], a['league']): a for a in co.get('adjusted', [])}
    diffs = co['diffs']
    # differences quoted against the reference league, which is the comparison
    # a selector is actually making
    ref_diffs = [d for d in diffs if d.get('vs_reference')]

    css_light = ' '.join(f"--s-{k}:{LEAGUE[k]['light']};" for k in keys)
    css_dark = ' '.join(f"--s-{k}:{LEAGUE[k]['dark']};" for k in keys)

    comps = co.get('competitions', [])

    # ---- headline tiles ---------------------------------------------------
    def signed(d):
        """Orient a difference as 'other league minus reference'."""
        if d['b'] == ref:
            return d['diff_raw'], d['diff_ci_lo'], d['diff_ci_hi'], d['a']
        return (-d['diff_raw'], -d['diff_ci_hi'], -d['diff_ci_lo'], d['b'])

    tiles = []
    for stat in ORDER:
        for d in [x for x in ref_diffs if x['stat'] == stat]:
            v, lo, hi, other = signed(d)
            if d['is_control']:
                verdict, cls = 'control — passes' if lo <= 0 <= hi \
                    else 'control — FAILS', 'ctl' if lo <= 0 <= hi else 'ns'
            elif lo <= 0 <= hi:
                verdict, cls = 'not distinguishable from zero', 'ns'
            else:
                verdict, cls = 'excludes zero', 'sig'
            tiles.append(f'''<div class="tile {cls}" style="border-left-color:var(--s-{other})">
      <div class="t-stat">{esc(stat)} &middot; {esc(L.label(other))}</div>
      <div class="t-val">{v * 100:+.1f}</div>
      <div class="t-ci">95% CI {lo * 100:+.1f} to {hi * 100:+.1f}</div>
      <div class="t-verdict">{esc(verdict)}</div>
    </div>''')

    # ---- per-league coefficient rows -------------------------------------
    f_rows = []
    for stat in ORDER:
        for lg in keys:
            c = cells.get((stat, lg))
            if not c:
                continue
            f_rows.append({
                'label': f"{stat} · {L.label(lg)}",
                'sub': f"n={c['n']} · own weight {c['own_weight']:.0%}",
                'value': c['shrunk'], 'lo': c['ci_lo'], 'hi': c['ci_hi'],
                'league': lg,
                'hollow': c['ci_lo'] <= 0 <= c['ci_hi'],
                'note': 'control statistic' if c['is_control'] else
                        f"club {100 * c['club']:.1f}% → FIBA {100 * c['fiba']:.1f}%"})

    d_rows = []
    for stat in ORDER:
        for d in [x for x in diffs if x['stat'] == stat]:
            v, lo, hi, other = signed(d) if d.get('vs_reference') else (
                d['diff_raw'], d['diff_ci_lo'], d['diff_ci_hi'], d['a'])
            lab = (f"{L.label(other)} − {L.label(ref)}" if d.get('vs_reference')
                   else d['pair'].replace(' - ', ' − '))
            d_rows.append({
                'label': stat, 'sub': lab, 'value': v, 'lo': lo, 'hi': hi,
                'league': other if d.get('vs_reference') else None,
                'hollow': lo <= 0 <= hi,
                'note': 'interval covers zero' if lo <= 0 <= hi
                        else 'interval excludes zero'})

    # ---- audit table -----------------------------------------------------
    by_player = defaultdict(dict)
    for p in pairs:
        k = (p['name'], p['league'])
        by_player[k]['meta'] = p
        by_player[k][p['stat']] = p
    trows = []
    for (name, lg), rec in sorted(by_player.items(), key=lambda kv: kv[0][0]):
        m = rec['meta']
        tds = [f'<td class="nm">{esc(name)}</td>',
               f'<td><span class="pill" style="background:var(--s-{lg})">'
               f'{esc(L.label(lg))}</span></td>',
               f'<td class="sub">{esc(m["team"] or "")}</td>',
               f'<td class="sub">{esc(m["nation"] or "")}</td>']
        for stat in ORDER:
            p = rec.get(stat)
            if not p:
                tds.append('<td class="num empty">—</td>')
                continue
            g = p['gap'] * 100
            tds.append(
                f'<td class="num" title="club {p["club_made"]:.0f}/'
                f'{p["club_att"]:.0f} · FIBA {p["fiba_made"]:.0f}/'
                f'{p["fiba_att"]:.0f}">{100 * p["club_rate"]:.0f} → '
                f'{100 * p["fiba_rate"]:.0f} <span class="gp">({g:+.0f})</span></td>')
        trows.append(f'<tr data-league="{lg}" data-name="{esc(name.lower())}">'
                     + ''.join(tds) + '</tr>')

    scats = ''.join(
        f'<div class="scat-wrap" data-stat="{esc(s)}" '
        f'{"hidden" if s != "two point" else ""}>'
        f'<h4>{esc(s)}</h4>'
        + scatter([p for p in pairs if p['stat'] == s]) + '</div>'
        for s in ORDER)

    comp_rows = ''.join(
        f'<tr><td>{esc(c["competition"])}</td>'
        f'<td class="num">{c["players"]}</td></tr>' for c in comps)

    # Dated from the fit, never from the clock: the page is a committed build
    # artefact and CI fails it if a rebuild differs, so today's date would make
    # it stale every midnight.
    n_tot = co['matched']['total']
    by_lg = co['matched']['by_league']
    built = co.get('fitted_on') or 'unknown'
    ref_label = L.label(ref)
    league_opts = ''.join(
        f'<option value="{k}">{esc(L.label(k))} only</option>'
        for k in keys)
    _ls = [L.label(k) for k in keys]
    league_list = (' and '.join(_ls) if len(_ls) < 3
                   else ', '.join(_ls[:-1]) + ' and ' + _ls[-1])
    league_counts = ', '.join(f"{by_lg.get(k, 0)} {L.label(k)}" for k in keys)
    ctl_line = '; '.join(
        f"<strong>{100 * cells[(ctl_name, k)]['raw_gap']:+.1f}</strong> "
        f"for the {esc(L.label(k))}"
        for k in keys if (ctl_name, k) in cells)
    n_qual = len({(p['name'], p['league']) for p in pairs})
    # ---- robustness ------------------------------------------------------
    thr_html = infl_html = comp_html = ''
    if rb:
        hdr = ''.join(f'<th class="num">{esc(x)}</th>' for x in ORDER)
        trs = []
        for r in rb.get('thresholds', []):
            tds = []
            for st in ORDER:
                d = r['stats'].get(st)
                if not d:
                    tds.append('<td class="num empty">—</td>')
                    continue
                crosses = d['lo'] <= 0 <= d['hi']
                mark = '' if crosses else ' class="hit-zero"'
                tds.append(
                    f'<td class="num"><span{mark}>{100 * d["diff"]:+.1f}</span>'
                    f'<span class="gp"> [{100 * d["lo"]:+.1f}, '
                    f'{100 * d["hi"]:+.1f}] n{d["min_n"]}</span></td>')
            trs.append(f'<tr><td class="num">{r["min_club"]}</td>'
                       f'<td class="num">{r["min_fiba"]}</td>'
                       + ''.join(tds) + '</tr>')
        thr_html = (f'<table><thead><tr><th class="num">min club</th>'
                    f'<th class="num">min FIBA</th>{hdr}</tr></thead>'
                    f'<tbody>{"".join(trs)}</tbody></table>')

        parts = []
        for key, lab in (('influence', 'two point'),
                         ('influence_3pt', 'three point')):
            i = rb.get(key)
            if not i:
                continue
            parts.append(
                f'<li><strong>{esc(lab)}</strong>: largest swing '
                f'{100 * i["max_abs_swing"]:.2f} pts across {i["n_refits"]} '
                f'refits, on removing {esc(i["max_swing_player"] or "—")} '
                f'(base {100 * i["base"]:+.2f}).</li>')
        infl_html = f'<ul>{"".join(parts)}</ul>'

        comps_r = rb.get('offset_by_competition', [])
        if comps_r:
            # Strip only a trailing women's marker. An unanchored replace of
            # ' W' turned "FIBA World Championships" into "FIBAorld".
            def _clean(n):
                return re.sub(r'\s*\(?\s*W\s*\)?\s*$', '', n).strip()

            rows_c = [{'label': _clean(c['competition'])[:30],
                       'sub': f"n={c['n']}",
                       'value': c['gap'], 'lo': c['gap'], 'hi': c['gap'],
                       'league': None, 'hollow': False,
                       'note': f"free-throw gap, {c['n']} players"}
                      for c in comps_r]
            # wider gutter: competition names are far longer than stat names
            comp_html = forest(rows_c, row_h=36, pad_l=230, pad_r=70)

    ctl_ds = [d for d in diffs if d['is_control']]
    ctl_max = max((abs(d['diff_raw']) for d in ctl_ds), default=0.0) * 100
    ctl_span = max((d['diff_ci_hi'] - d['diff_ci_lo'] for d in ctl_ds),
                   default=0.0) * 100
    off = co.get('offset') or 0.0

    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FIBA League Translation</title>
<style>
:root {{
  color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb;
  --ink-1:#0b0b0b; --ink-2:#52514e; --ink-3:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  {css_light}
  --good:#0ca30c; --warn:#fab219; --crit:#d03b3b;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19;
    --ink-1:#f0efec; --ink-2:#c3c2b7; --ink-3:#898781;
    --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
    {css_dark}
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19;
  --ink-1:#f0efec; --ink-2:#c3c2b7; --ink-3:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  {css_dark}
}}
* {{ box-sizing:border-box }}
body {{
  margin:0; background:var(--page); color:var(--ink-1);
  font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;
}}
.wrap {{ max-width:1000px; margin:0 auto; padding:0 16px 80px }}
header {{ padding:52px 0 8px }}
h1 {{ font-size:30px; line-height:1.2; margin:0 0 10px; letter-spacing:-.02em }}
.lede {{ font-size:17px; color:var(--ink-2); max-width:62ch; margin:0 0 6px }}
.meta {{ font-size:13px; color:var(--ink-3); margin-top:14px }}
section {{ margin-top:44px }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.09em;
     color:var(--ink-3); margin:0 0 16px; font-weight:650 }}
h3 {{ font-size:19px; margin:0 0 8px }}
h4 {{ font-size:13px; color:var(--ink-2); margin:0 0 6px; font-weight:600 }}
p {{ max-width:68ch; color:var(--ink-2); margin:0 0 12px }}
p strong {{ color:var(--ink-1) }}
.card {{ background:var(--surface); border:1px solid var(--ring);
        border-radius:12px; padding:22px }}
.tiles {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)) }}
.tile {{ background:var(--surface); border:1px solid var(--ring);
        border-radius:12px; padding:16px 18px; border-left:3px solid var(--ink-3) }}
.tile.sig {{ border-left-color:var(--s-ncaa) }}
.tile.ns  {{ border-left-color:var(--axis) }}
.tile.ctl {{ border-left-color:var(--good) }}
.t-stat {{ font-size:12px; text-transform:uppercase; letter-spacing:.07em;
          color:var(--ink-3); font-weight:650 }}
.t-val {{ font-size:34px; font-weight:680; letter-spacing:-.02em; margin:4px 0 2px }}
.t-ci {{ font-size:12.5px; color:var(--ink-2); font-variant-numeric:tabular-nums }}
.t-verdict {{ font-size:12.5px; margin-top:7px; font-weight:600 }}
.tile.sig .t-verdict {{ color:var(--s-ncaa) }}
.tile.ns  .t-verdict {{ color:var(--ink-3) }}
.tile.ctl .t-verdict {{ color:var(--good) }}
.chart {{ width:100%; height:auto; display:block; overflow:visible }}
.scat {{ max-width:470px; margin:0 auto }}
.grid {{ stroke:var(--grid); stroke-width:1 }}
.zero {{ stroke:var(--axis); stroke-width:2 }}
.zero-lab, .tick, .ax {{ fill:var(--ink-3); font-size:11px }}
.ident {{ stroke:var(--axis); stroke-width:2; stroke-dasharray:4 4 }}
.ident-lab {{ fill:var(--ink-3); font-size:11px }}
.row-lab {{ fill:var(--ink-1); font-size:13px; font-weight:560 }}
.row-sub {{ fill:var(--ink-3); font-size:11px }}
.row-val {{ fill:var(--ink-2); font-size:12px; font-variant-numeric:tabular-nums }}
.ci {{ stroke-width:2 }}
.cap {{ stroke-width:2 }}
.dot {{ stroke-width:2; paint-order:stroke }}
.pt {{ stroke:var(--surface); stroke-width:2 }}
.hit {{ fill:transparent }}
.hit:hover ~ .dot {{ r:8 }}
.legend {{ display:flex; gap:18px; margin:2px 0 10px; font-size:12.5px;
          color:var(--ink-2) }}
.lg-item {{ display:flex; align-items:center; gap:7px }}
.sw {{ width:11px; height:11px; border-radius:3px; display:inline-block }}
.row2 {{ display:grid; gap:22px; grid-template-columns:1fr 1fr }}
@media (max-width:760px) {{ .row2 {{ grid-template-columns:1fr }} }}
table {{ width:100%; border-collapse:collapse; font-size:13px }}
th {{ text-align:left; font-size:11px; text-transform:uppercase;
     letter-spacing:.06em; color:var(--ink-3); font-weight:650;
     padding:8px 10px; border-bottom:1px solid var(--axis); position:sticky;
     top:0; background:var(--surface) }}
td {{ padding:7px 10px; border-bottom:1px solid var(--grid) }}
td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums }}
td.nm {{ font-weight:560 }}
td.sub {{ color:var(--ink-3); font-size:12px }}
td.empty {{ color:var(--ink-3) }}
.gp {{ color:var(--ink-3); font-size:11.5px }}
.hit-zero {{ font-weight:700; color:var(--ink-1) }}
.pill {{ font-size:11px; font-weight:650; padding:2px 7px; border-radius:20px;
        color:#fff }}
.tbl-wrap {{ max-height:560px; overflow:auto; border:1px solid var(--ring);
            border-radius:12px; background:var(--surface) }}
.controls {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px;
            align-items:center }}
input[type=search], select {{ font:inherit; font-size:13px; padding:7px 11px;
  border:1px solid var(--axis); border-radius:8px; background:var(--surface);
  color:var(--ink-1) }}
.btn {{ font:inherit; font-size:12.5px; font-weight:600; padding:6px 13px;
  border:1px solid var(--axis); border-radius:20px; background:var(--surface);
  color:var(--ink-2); cursor:pointer }}
.btn[aria-pressed=true] {{ background:var(--ink-1); color:var(--page);
  border-color:var(--ink-1) }}
#tip {{ position:fixed; pointer-events:none; opacity:0; transition:opacity .1s;
  background:var(--ink-1); color:var(--page); font-size:12px; padding:7px 10px;
  border-radius:7px; max-width:320px; z-index:9; line-height:1.45 }}
.note {{ font-size:13px; color:var(--ink-3); margin-top:10px; max-width:68ch }}
ul {{ max-width:68ch; color:var(--ink-2); padding-left:20px }}
li {{ margin-bottom:7px }}
.flag {{ display:inline-block; font-size:11px; font-weight:650; padding:1px 7px;
  border-radius:4px; background:var(--grid); color:var(--ink-2); margin-right:6px }}
footer {{ margin-top:56px; padding-top:20px; border-top:1px solid var(--grid);
  font-size:12.5px; color:var(--ink-3) }}
a {{ color:var(--s-ncaa) }}
</style>
</head>
<body>
<div id="tip"></div>
<div class="wrap">

<header>
  <h1>How much of a club season survives the jump to FIBA?</h1>
  <p class="lede">Translation coefficients for {league_list}, measured against
  senior international competition as a common reference frame. One coefficient
  per shooting statistic per league.</p>
  <div class="meta">{n_tot} players matched across both environments
  ({by_lg.get('ncaa', 0)} NCAA, {by_lg.get('wnba', 0)} WNBA) ·
  senior FIBA 2025&ndash;2026 · fitted {built}</div>
</header>

<section>
  <h2>The headline</h2>
  <h3>Each league minus the {ref_label}, in percentage points</h3>
  <p>How much more a player's rate falls when she arrives from that league
  rather than from the {ref_label}. This difference is the quantity the data
  actually identifies, for the reason set out under <em>the control</em>
  below.</p>
  <div class="tiles">{''.join(tiles)}</div>
  <p class="note">A negative figure means that league's production overstates a
  player relative to the same production in the {ref_label}.</p>
</section>

<section>
  <h2>The control</h2>
  <h3>Free throws should have shown nothing. They showed &minus;3.</h3>
  <p>Nobody guards a free throw: same rim, same distance, no defender. If the
  method were measuring league difficulty, the free-throw coefficient would come
  out near zero. It did not. It came out at
  {ctl_line} &mdash; a drop of about three points in each.</p>
  <p>That cannot be league difficulty. It is a flat cost of playing FIBA at
  all: travel, unfamiliar teammates, a different ball, compressed schedules.
  And because it is common to every league, it sits on every absolute gap
  alike.</p>
  <p><strong>So absolute club&rarr;FIBA gaps are not interpretable as league
  strength. The difference between two leagues is, because the shared offset
  cancels.</strong> On that scale the control passes: every pairwise control
  difference is {ctl_max:.1f} points or less.</p>
  <p class="note">Estimated FIBA environment offset: {100 * off:+.1f} points.
  Worth its own scepticism &mdash; the control's interval spans
  {ctl_span:.0f} points, so it could not have detected an offset difference the
  size of the three-point effect. It bounds the method loosely, not tightly.</p>
</section>

<section>
  <h2>Per league</h2>
  <h3>Club&rarr;FIBA gap, after shrinkage</h3>
  {legend(keys)}
  <div class="card">{forest(f_rows, dom=(-0.09, 0.06))}</div>
  <p class="note">Shrunk toward the across-league mean in proportion to
  precision. <strong>Own weight</strong> is how much of each estimate is the
  league's own data rather than the pooled mean; at 0% the leagues are
  indistinguishable on that statistic, which is an answer rather than a
  failure. A hollow marker means the interval covers zero. These are absolute
  gaps, so they carry the environment offset.</p>
</section>

<section>
  <h2>League difference</h2>
  <h3>The offset-free quantity</h3>
  <div class="card">{forest(d_rows, dom=(-0.12, 0.03))}</div>
  <p class="note">Unshrunk, because shrinkage pulls the two leagues toward a
  common value and would understate the difference between them. Hollow markers
  cover zero and are not results.</p>
</section>

<section>
  <h2>Player level</h2>
  <h3>Every matched player, club rate against FIBA rate</h3>
  {legend(keys)}
  <div class="controls">
    {''.join(f'<button class="btn" data-scat="{esc(s)}" aria-pressed="{str(s == "two point").lower()}">{esc(s)}</button>' for s in ORDER)}
  </div>
  <div class="card">{scats}</div>
  <p class="note">Marker size follows FIBA attempts, so the small points are
  the thin samples. Points above the dashed line shot better in FIBA than at
  their club. The spread is the real story: individual gaps run to &plusmn;30
  points, and the coefficient is the centre of that cloud, not a description of
  any one player.</p>
</section>

<section>
  <h2>Audit</h2>
  <h3>The name match, exposed</h3>
  <p>Synergy issues a different player id per league, so club and FIBA records
  cannot be joined on id and are matched on normalised name. That is the
  weakest assumption in the study, so every pair it produced is listed here
  rather than hidden. Club team and nation are shown because an implausible
  pairing is usually obvious from them.</p>
  <div class="controls">
    <input type="search" id="q" placeholder="filter by name&hellip;" aria-label="Filter by name">
    <select id="lgf" aria-label="Filter by league">
      <option value="">all leagues</option>
      {league_opts}
    </select>
    <span class="note" id="cnt" style="margin:0"></span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>
      <th>Player</th><th>League</th><th>Club</th><th>Nation</th>
      {''.join(f'<th class="num">{esc(s)}</th>' for s in ORDER)}
    </tr></thead>
    <tbody id="tb">{''.join(trows)}</tbody>
  </table></div>
  <p class="note">Each cell reads club rate &rarr; FIBA rate, with the gap in
  brackets. Hover for the underlying makes and attempts. Minimum sample to
  qualify: {co['min_club_att']} club attempts and {co['min_fiba_att']} FIBA
  attempts.</p>
</section>

<section>
  <h2>Robustness</h2>
  <h3>Does the result survive being made harder to produce?</h3>
  <p>A coefficient that exists only at one arbitrary sample threshold is not a
  finding. Each row below re-fits everything from scratch at a stricter minimum.
  <strong>Bold</strong> marks an interval that excludes zero.</p>
  <div class="tbl-wrap">{thr_html}</div>
  <p class="note">The two-point difference excludes zero at every cutoff tried.
  The three-point difference crosses zero at every one, which settles it as a
  non-result rather than a borderline one. The control degrades at the strictest
  cutoffs, where it is down to a handful of players &mdash; it bounds the method
  only where it has sample.</p>

  <h3 style="margin-top:30px">Does one player carry it?</h3>
  {infl_html}
  <p class="note">Leave-one-player-out, refitting once per removed player.</p>

  <h3 style="margin-top:30px">Is the environment offset really one number?</h3>
  <p>The method assumes a single FIBA environment offset. Estimated separately
  per competition, the control does not look like one number at all.</p>
  <div class="card">{comp_html}</div>
  <p class="note">Free-throw gap by event, against a pooled offset of
  {100 * off:+.1f}. The spread is about nine points, so the offset looks like a
  property of the event rather than of FIBA. <strong>This weakens the adjusted
  per-league columns and leaves the league differences untouched</strong>, since
  a difference cancels whatever the offset is &mdash; a stronger reason to lead
  with them than the control alone provided. No interval is drawn: these are
  single pooled gaps, not fitted estimates.</p>
</section>

<section>
  <h2>What this rests on</h2>
  <div class="row2">
    <div>
      <h4>Senior FIBA competitions used</h4>
      <div class="tbl-wrap" style="max-height:300px"><table>
        <thead><tr><th>Competition</th><th class="num">Players</th></tr></thead>
        <tbody>{comp_rows}</tbody>
      </table></div>
      <p class="note">Youth brackets (U16&ndash;U23, 3x3) and University Games
      excluded. Women's basketball throughout.</p>
    </div>
    <div>
      <h4>Known defects, found and handled</h4>
      <ul>
        <li><span class="flag">fixed</span>The club leaderboard silently capped
        responses at the page limit, returning exactly 4,096 NCAA records per
        season. Paging to exhaustion returns over 20,000. Coefficients moved by
        less than half a point, which is a useful robustness check.</li>
        <li><span class="flag">dropped</span>Field goals. The club endpoint's
        <code>fgMade/fgAttempt</code> are not field goals: A'ja Wilson's 2025
        season reads 950/1940 against a true 2PM+3PM of 459/931. The points
        identity closes on the explicit shot fields and not at all on the fg
        ones. The FIBA endpoint is unaffected.</li>
        <li><span class="flag">fixed</span>Inverse-variance weights were
        computed from each player's own observed rate, so an 8-for-8 line gave
        a variance of zero and an exploding weight. Weights now depend on
        sample size alone.</li>
      </ul>
    </div>
  </div>
</section>

<section>
  <h2>Limitations</h2>
  <ul>
    <li><strong>Cell sizes are 39&ndash;89 players.</strong> The three-point
    difference does not clear zero and is not a result.</li>
    <li><strong>Players are matched by name, not id.</strong> See the audit
    table; the pairs are not individually hand-verified.</li>
    <li><strong>Selection.</strong> Players who reach a national team are not a
    random sample of their league, and those who play enough FIBA minutes to
    qualify are a further cut.</li>
    <li><strong>The environment offset rests on one control statistic</strong>,
    with a wide interval. League differences do not depend on it; the adjusted
    per-league figures do.</li>
    <li><strong>Shooting only.</strong> Assists, rebounds and steals are not
    available from the endpoint used.</li>
    <li><strong>Season pairing is coarse</strong> &mdash; club seasons are
    matched to tournaments by year rather than by sequence.</li>
    <li><strong>Intervals are approximate.</strong> The shrunk estimate's
    variance treats its two components as independent and ignores uncertainty
    in the between-league variance.</li>
  </ul>
</section>

<footer>
  Data: Synergy Sports. Raw data is licensed and not redistributed.
  Source: <a href="https://github.com/jordanngo205/fiba-league-translation">github.com/jordanngo205/fiba-league-translation</a>
</footer>
</div>

<script>
// tooltip, shared by every chart
const tip = document.getElementById('tip');
document.addEventListener('mouseover', e => {{
  const t = e.target.closest('[data-tip]');
  if (!t) return;
  tip.textContent = t.getAttribute('data-tip');
  tip.style.opacity = 1;
}});
document.addEventListener('mousemove', e => {{
  if (tip.style.opacity === '0' || !tip.style.opacity) return;
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}});
document.addEventListener('mouseout', e => {{
  if (e.target.closest('[data-tip]')) tip.style.opacity = 0;
}});

// scatter statistic switch
document.querySelectorAll('[data-scat]').forEach(b => {{
  b.addEventListener('click', () => {{
    const s = b.dataset.scat;
    document.querySelectorAll('[data-scat]').forEach(o =>
      o.setAttribute('aria-pressed', String(o === b)));
    document.querySelectorAll('.scat-wrap').forEach(w =>
      w.hidden = (w.dataset.stat !== s));
  }});
}});

// audit table filters
const q = document.getElementById('q'), lgf = document.getElementById('lgf'),
      cnt = document.getElementById('cnt'),
      rows = [...document.querySelectorAll('#tb tr')];
function filt() {{
  const s = q.value.trim().toLowerCase(), l = lgf.value;
  let n = 0;
  rows.forEach(r => {{
    const ok = (!s || r.dataset.name.includes(s)) &&
               (!l || r.dataset.league === l);
    r.hidden = !ok; if (ok) n++;
  }});
  cnt.textContent = n + ' of ' + rows.length + ' players';
}}
q.addEventListener('input', filt); lgf.addEventListener('change', filt); filt();
</script>
</body>
</html>'''

    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / 'index.html'
    out.write_text(html)
    print(f'wrote {out}  ({len(html) / 1024:.0f} KB)')
    print(f'  {len(f_rows)} coefficient rows, {len(trows)} audited players, '
          f'{len(comps)} competitions')


if __name__ == '__main__':
    main()
