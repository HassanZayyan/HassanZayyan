"""Render the public GitHub calendar as a static grid and a Pac-Man SVG.

Both images use the exact same anonymous profile snapshot. No repository
contents, access tokens, private contributions or synthetic activity are used.
"""
from collections import Counter
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

USER = 'HassanZayyan'
OUT = Path('dist')
COLORS = ['#1e293b', '#164e45', '#237b65', '#34b88b', '#9af5bb']


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = {}
        self.tooltips = {}
        self.target = None
        self.text = []
        self.heading = False
        self.summary = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'td' and 'data-date' in attrs:
            self.cells[attrs['id']] = {
                'date': attrs['data-date'], 'level': int(attrs['data-level'])
            }
        if tag == 'tool-tip' and attrs.get('for', '').startswith('contribution-day-'):
            self.target = attrs['for']
            self.text = []
        if tag == 'h2' and attrs.get('id') == 'js-contribution-activity-description':
            self.heading = True

    def handle_data(self, data):
        if self.target:
            self.text.append(data)
        if self.heading:
            self.summary += data

    def handle_endtag(self, tag):
        if tag == 'tool-tip' and self.target:
            self.tooltips[self.target] = ''.join(self.text).strip()
            self.target = None
        if tag == 'h2':
            self.heading = False


def fetch_calendar():
    url = f'https://github.com/users/{USER}/contributions'
    request = Request(url, headers={'User-Agent': 'HassanZayyan-profile-calendar'})
    with urlopen(request, timeout=45) as response:
        source = response.read().decode('utf-8')
    parser = CalendarParser()
    parser.feed(source)
    days = []
    for cell_id, cell in parser.cells.items():
        tooltip = parser.tooltips.get(cell_id, '')
        match = re.match(r'([\d,]+) contributions?\b', tooltip)
        if tooltip.startswith('No contributions'):
            count = 0
        elif match:
            count = int(match[1].replace(',', ''))
        else:
            raise ValueError(f'Missing or unrecognized tooltip: {cell["date"]}')
        if cell['level'] not in range(5) or (count == 0) != (cell['level'] == 0):
            raise ValueError('Calendar count and intensity disagree')
        days.append({**cell, 'count': count})
    days.sort(key=lambda day: day['date'])
    summary = re.search(r'([\d,]+)\s+contributions?\s+in the last year', parser.summary)
    if not summary or not 350 <= len(days) <= 378:
        raise ValueError('GitHub calendar markup changed; refusing to publish incomplete data')
    total = int(summary[1].replace(',', ''))
    if total != sum(day['count'] for day in days):
        raise ValueError('Daily counts do not match the GitHub public total')
    dates = [datetime.strptime(day['date'], '%Y-%m-%d') for day in days]
    if any((b - a).days != 1 for a, b in zip(dates, dates[1:])):
        raise ValueError('Calendar dates are not contiguous')
    return days, total, url


def render(days, total, updated, animated=False):
    # The source's Sunday-first calendar is sorted by date, then laid out by week.
    width, height, step, size = 1166, 280, 21, 16
    x0, y0 = 28, 79
    duration, hold, travel = 50, 0.12, 0.80
    active = [i for i, day in enumerate(days) if day['count']]
    rank = {index: n for n, index in enumerate(active)}
    def point(index):
        return x0 + (index // 7) * step + size / 2, y0 + (index % 7) * step + size / 2
    label = 'PAC-MAN / PUBLIC CONTRIBUTIONS' if animated else 'PUBLIC CONTRIBUTION CALENDAR'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           f'<title id="title">{label}: {total} contributions</title>',
           '<desc id="desc">Public GitHub calendar. Each cell is one day. Animation consumes cells; the static calendar preserves all original intensities.</desc>',
           '<rect width="1166" height="280" rx="8" fill="#101827"/>',
           '<path d="M0 3H1166" stroke="#f7d774" stroke-width="6"/>',
           f'<text x="28" y="34" font-family="monospace" font-size="17" font-weight="bold" fill="#f7d774">{label}</text>',
           f'<text x="1138" y="34" text-anchor="end" font-family="monospace" font-size="16" fill="#9af5bb">{total:,} CONTRIBUTIONS</text>']
    month = None
    for index, day in enumerate(days):
        date = datetime.strptime(day['date'], '%Y-%m-%d')
        if date.month != month:
            x, _ = point(index)
            out.append(f'<text x="{x-8}" y="65" font-family="monospace" font-size="11" fill="#acb9cb">{date:%b}</text>')
            month = date.month
        x, y = point(index)
        color = COLORS[day['level']]
        out.append(f'<rect x="{x-8}" y="{y-8}" width="16" height="16" rx="2" fill="{color}"><title>{day["date"]}: {day["count"]} contributions</title>')
        if animated and index in rank:
            eaten = hold + travel * (rank[index] + 1) / max(len(active), 1)
            out.append(f'<animate attributeName="fill" dur="{duration}s" repeatCount="indefinite" calcMode="discrete" keyTimes="0;{eaten:.6f};0.98;1" values="{color};{COLORS[0]};{color};{color}"/>')
        out.append('</rect>')
    if animated and active:
        # Hold the untouched calendar for six seconds before eating cells.
        points = [point(active[0]), point(active[0])] + [point(index) for index in active] + [point(active[-1])]
        coords = ';'.join(f'{x} {y}' for x, y in points)
        times = [0, hold] + [hold + travel * (i+1)/len(active) for i in range(len(active))] + [1]
        keys = ';'.join(f'{t:.6f}' for t in times)
        out += ['<g>', f'<animateTransform attributeName="transform" type="translate" dur="{duration}s" repeatCount="indefinite" calcMode="linear" keyTimes="{keys}" values="{coords}"/>',
                '<path d="M0 0 L7 -6 A9 9 0 1 0 7 6 Z" fill="#f7d774" stroke="#101827" stroke-width="1.5"/>',
                '<circle cx="-1" cy="-4" r="1.2" fill="#101827"/>', '</g>']
        # Ghosts live in the header, keeping the calendar cells unobscured.
        for n, color in enumerate(['#ff8274', '#6fe7ed', '#ec9ac6']):
            x = 720 + n * 30
            out += [f'<g transform="translate({x} 22)"><path d="M-8 8V0a8 8 0 0 1 16 0v8l-4-3-4 3-4-3Z" fill="{color}"/>',
                    '<circle cx="-3" cy="0" r="2" fill="#fff"/><circle cx="3" cy="0" r="2" fill="#fff"/></g>']
    out += [f'<text x="28" y="250" font-family="monospace" font-size="12" fill="#acb9cb">PUBLIC DATA ONLY / UPDATED {escape(updated)} UTC</text>',
            '<text x="1138" y="250" text-anchor="end" font-family="monospace" font-size="12" fill="#6fe7ed">github.com/HassanZayyan</text>', '</svg>']
    return '\n'.join(out)


if __name__ == '__main__':
    days, total, source = fetch_calendar()
    updated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    OUT.mkdir(exist_ok=True)
    snapshot = {'username': USER, 'visibility': 'public', 'source': source,
                'updated_at': updated + ' UTC', 'total': total, 'days': days}
    (OUT / 'contributions.json').write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')
    for name, animated in [('contribution-calendar.svg', False), ('pacman-contribution-graph.svg', True)]:
        svg = render(days, total, updated, animated)
        (OUT / name).write_text(svg, encoding='utf-8')
    print(f'Validated {len(days)} days, {total} public contributions. Levels: {dict(Counter(d["level"] for d in days))}')
