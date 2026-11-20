"""Render a GitHub profile terminal from public account data. Python stdlib only."""
import base64
import datetime as dt
import html
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USER = os.environ.get('PROFILE_USER', 'KaiAlexander-commits')
NOW = dt.datetime.now(dt.timezone.utc)
GREEN, RED, WHITE, MUTED = '#57e389', '#ff6577', '#eaf2ed', '#82958c'
COLORS = {'Python': '#68b8f8', 'Java': '#e6a454', 'JavaScript': '#f1d95b', 'CSS': '#b69bf8', 'HTML': '#f67c63', 'TypeScript': '#5ba9e8', 'Shell': '#8be9a0'}


def fetch(url, raw=False):
    headers = {'User-Agent': 'Kai-Profile-Terminal', 'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GITHUB_TOKEN')
    if token and url.startswith('https://api.github.com/'):
        headers['Authorization'] = f'Bearer {token}'
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        body = response.read()
    return body if raw else json.loads(body)


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days, self.levels, self.ids = {}, {}, {}
        self.tooltip = None
        self.buffer = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-date' in attrs and 'data-level' in attrs:
            day = attrs['data-date']
            self.levels[day] = int(attrs['data-level'])
            self.ids[attrs.get('id', '')] = day
        if tag == 'tool-tip' and attrs.get('for') in self.ids:
            self.tooltip = self.ids[attrs['for']]
            self.buffer = ''

    def handle_data(self, data):
        if self.tooltip:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == 'tool-tip' and self.tooltip:
            first = self.buffer.strip().split()[0].replace(',', '')
            self.days[self.tooltip] = int(first) if first.isdigit() else 0
            self.tooltip = None


def collect():
    profile = fetch(f'https://api.github.com/users/{USER}')
    repos, page = [], 1
    while True:
        batch = fetch(f'https://api.github.com/users/{USER}/repos?per_page=100&type=owner&page={page}')
        repos.extend(r for r in batch if not r['private'])
        if len(batch) < 100:
            break
        page += 1
    def language(repo):
        # Profile art and copied server history should not dominate code composition.
        if repo['name'] in {USER, 'Employee-Manager-Server'} or repo['fork']:
            return {}
        return fetch(repo['languages_url'])
    languages = Counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(language, repos):
            languages.update(result)
    parser = CalendarParser()
    parser.feed(fetch(f'https://github.com/users/{USER}/contributions', raw=True).decode())
    if len(parser.days) < 350 or any(day not in parser.days for day in parser.levels):
        raise RuntimeError('Incomplete contribution calendar; keeping previous profile assets.')
    today = NOW.date()
    cutoff = (today - dt.timedelta(days=364)).isoformat()
    days = {date: count for date, count in parser.days.items() if cutoff <= date <= today.isoformat()}
    avatar_bytes = fetch(profile['avatar_url'], raw=True)
    avatar = base64.b64encode(avatar_bytes).decode()
    avatar_mime = 'image/png' if avatar_bytes.startswith(b'\x89PNG') else 'image/jpeg'
    return {'profile': profile, 'repos': repos, 'languages': dict(languages), 'days': days,
            'avatar': avatar, 'avatar_mime': avatar_mime, 'updated': NOW.strftime('%Y-%m-%d %H:%M UTC')}


def text(x, y, value, size=14, color=WHITE, weight=400, extra=''):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" {extra}>{html.escape(str(value))}</text>'


def rect(x, y, w, h, fill, radius=0, stroke='none'):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'


def line(x1, y1, x2, y2, color='#203029'):
    return f'<path d="M{x1} {y1}H{x2}" stroke="{color}"/>' if y1 == y2 else f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}"/>'


def shell(height, label, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1000" height="{height}" viewBox="0 0 1000 {height}" role="img" aria-labelledby="title desc">
<title id="title">{html.escape(label)}</title><desc id="desc">Kai Smith's GitHub profile. Data refreshed every six hours from public GitHub activity.</desc>
<defs><linearGradient id="bg" x2="0.8" y2="1"><stop stop-color="#102019"/><stop offset="1" stop-color="#0a100e"/></linearGradient><clipPath id="avatar"><circle cx="76" cy="110" r="27"/></clipPath></defs>
<g font-family="'SFMono-Regular',Consolas,'Liberation Mono',monospace">
{rect(1, 1, 998, height-2, 'url(#bg)', 16, '#2a3e31')}{''.join(body)}</g></svg>'''


def section(y, number, title):
    return text(34, y, f'{number} / {title}', 12, GREEN, 600, 'letter-spacing="2"')


def streaks(days):
    longest = run = 0
    for date in sorted(days):
        run = run + 1 if days[date] else 0
        longest = max(longest, run)
    day = NOW.date()
    if not days.get(day.isoformat(), 0):
        day -= dt.timedelta(days=1)
    current = 0
    while days.get(day.isoformat(), 0):
        current += 1
        day -= dt.timedelta(days=1)
    return current, longest


def render(data):
    p, repos, days = data['profile'], data['repos'], data['days']
    last30 = [(NOW.date()-dt.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    counts = [days.get(d, 0) for d in last30]
    total = sum(days.values())
    stars = sum(r['stargazers_count'] for r in repos)
    body = [rect(2, 2, 996, 44, '#111b16', 15), line(1, 46, 999, 46)]
    for i, color in enumerate([RED, '#e6bd57', GREEN]):
        body.append(f'<circle cx="{29+i*18}" cy="24" r="4" fill="{color}"/>')
    body += [text(101, 29, f'{USER} / README', 12, MUTED), text(961, 29, 'PROFILE TERMINAL', 11, GREEN, extra='text-anchor="end"')]
    body += [f'<image x="49" y="83" width="54" height="54" clip-path="url(#avatar)" xlink:href="data:{data["avatar_mime"]};base64,{data["avatar"]}"/>',
             text(118, 108, '$KAI', 32, WHITE, 700), text(118, 130, 'SOFTWARE / DATA / FINANCE', 11, MUTED),
             text(959, 102, f'{sum(counts):,}', 34, WHITE, 700, 'text-anchor="end"'),
             text(959, 126, 'CONTRIBUTIONS · 30D', 11, GREEN, extra='text-anchor="end"'),
             section(176, '01', 'ACTIVITY EXCHANGE'), text(34, 201, 'Daily contributions', 13, MUTED),
             text(959, 201, '30D', 12, GREEN, extra='text-anchor="end"')]
    chart_top, chart_bottom = 229, 383
    maximum = max(max(counts), 1)
    for i in range(4):
        y = chart_top + i*(chart_bottom-chart_top)/3
        body += [line(34, round(y, 1), 921, round(y, 1), '#1a2b22'), text(959, y+4, round(maximum*(1-i/3)), 10, MUTED, extra='text-anchor="end"')]
    for i, count in enumerate(counts):
        color = GREEN if i == 0 or count >= counts[i-1] else RED
        x = 38 + i*29.2
        h = count/maximum*(chart_bottom-chart_top)
        body.append(rect(round(x, 1), round(chart_bottom-max(h, 2), 1), 18, round(max(h, 2), 1), color if count else '#21352a', 2))
    body += [text(34, 408, last30[0][5:], 10, MUTED), text(921, 408, last30[-1][5:], 10, MUTED, extra='text-anchor="end"'),
             text(34, 435, 'Green ≥ previous day  /  Red &lt; previous day'.replace('&lt;', '<'), 10, MUTED), line(34, 454, 966, 454)]
    metrics = [('REPOSITORIES', len(repos)), ('STARS', stars), ('FOLLOWERS', p['followers']), ('CONTRIBUTIONS · YEAR', total)]
    for i, (label, value) in enumerate(metrics):
        x = 34 + i*239
        body += [text(x, 482, label, 10, MUTED), text(x, 514, f'{value:,}', 23, WHITE, 600)]
    (ROOT/'assets/market.svg').write_text(shell(542, 'Kai activity exchange', body))

    body = [section(37, '02', 'THE BUILDER'), text(34, 89, p.get('name') or 'Kai Smith', 34, WHITE, 700),
            text(34, 121, 'Python automation. Full-stack systems. Data with a purpose.', 15, WHITE),
            text(34, 150, 'Student developer exploring the intersection of software and finance.', 12, MUTED),
            rect(34, 176, 932, 45, '#11251a', 7, '#244a32'),
            text(52, 204, 'FOCUS', 11, GREEN, 600), text(118, 204, 'Data science / economics / building useful things', 12),
            section(266, '03', 'PROJECT WATCHLIST')]
    body += [text(34, 299, 'PROJECT / THESIS', 10, MUTED), text(679, 299, 'LANGUAGE', 10, MUTED), text(831, 299, 'PUSHED', 10, MUTED), text(963, 299, 'STARS', 10, MUTED, extra='text-anchor="end"')]
    overrides = {
        'Employee-Manager-Dashboard': ('Employee Manager', 'React interface + Spring Boot API / one directory'),
        'Trading-Algo': ('Trading Algo', 'Momentum signals / Alpaca / Python automation'),
        'Apartment-Database': ('Apartment Database', 'Java maintenance-request backend / in progress'),
        'Final-Project': ('Penguin Run', 'Python + Pygame / an endless-runner experiment'),
        'Employee-Manager-Server': ('Employee API', 'Original Spring Boot service / preserved history'),
    }
    candidates = [r for r in repos if r['name'] != USER]
    priority = ['Employee-Manager-Dashboard', 'Trading-Algo', 'Apartment-Database', 'Final-Project', 'Employee-Manager-Server']
    candidates.sort(key=lambda r: (priority.index(r['name']) if r['name'] in priority else len(priority), r['name']))
    for i, repo in enumerate(candidates[:6]):
        y = 322 + i*67
        title, desc = overrides.get(repo['name'], (repo['name'], repo.get('description') or 'Public repository'))
        body += [line(34, y-9, 966, y-9), text(34, y+12, f'{i+1:02}', 11, GREEN), text(70, y+12, title[:48], 15, WHITE, 600),
                 text(70, y+32, desc[:73], 10, MUTED), text(679, y+12, repo.get('language') or '—', 11, MUTED),
                 text(831, y+12, repo['pushed_at'][:10], 10, MUTED), text(963, y+12, repo['stargazers_count'], 12, GREEN, extra='text-anchor="end"')]
    height = 349 + len(candidates[:6])*67
    (ROOT/'assets/watchlist.svg').write_text(shell(height, 'Kai Smith and project watchlist', body))

    languages = sorted(data['languages'].items(), key=lambda item: item[1], reverse=True)
    denominator = sum(data['languages'].values()) or 1
    body = [section(37, '04', 'LANGUAGE ALLOCATION'), text(34, 65, 'Share of code bytes · original public projects', 11, MUTED)]
    for i, (language, count) in enumerate(languages[:5]):
        y = 102 + i*36
        percentage = count/denominator*100
        body += [text(34, y+4, language, 13), rect(199, y-8, 640, 10, '#223028', 5),
                 rect(199, y-8, round(640*percentage/100, 1), 10, COLORS.get(language, GREEN), 5), text(961, y+4, f'{percentage:.1f}%', 12, MUTED, extra='text-anchor="end"')]
    body += [line(34, 284, 966, 284), section(319, '05', 'CONSISTENCY LEDGER')]
    current, longest = streaks(days)
    start = dt.date.fromisoformat(min(days))
    start -= dt.timedelta(days=(start.weekday()+1)%7)
    shades = ['#17271e', '#163d25', '#226938', '#37a653', GREEN]
    for date, count in sorted(days.items()):
        day = dt.date.fromisoformat(date)
        offset = (day-start).days
        x, y = 34 + (offset//7)*12, 366 + (offset%7)*12
        level = 0 if count == 0 else 1 if count < 3 else 2 if count < 6 else 3 if count < 10 else 4
        body.append(f'<g><title>{date}: {count} contributions</title>{rect(x,y,9,9,shades[level],2)}</g>')
    body += [text(34, 352, min(days)[:7], 10, MUTED), text(671, 352, max(days)[:7], 10, MUTED, extra='text-anchor="end"')]
    for i, (label, value) in enumerate([('CURRENT STREAK', f'{current} day' + ('s' if current != 1 else '')), ('LONGEST · THIS YEAR', f'{longest} day' + ('s' if longest != 1 else '')), ('CONTRIBUTIONS · YEAR', f'{total:,}')]):
        y = 354 + i*48
        body += [text(745, y, label, 9, MUTED), text(745, y+22, value, 19, WHITE, 600)]
    body += [text(34, 477, 'Less', 9, MUTED)]
    for i, color in enumerate(shades):
        body.append(rect(70+i*14, 468, 10, 10, color, 2))
    body += [text(148, 477, 'More', 9, MUTED), line(34, 506, 966, 506),
             text(34, 537, 'PUBLIC GITHUB DATA / REFRESH EVERY 6 HOURS', 10, GREEN),
             text(965, 537, data['updated'], 10, MUTED, extra='text-anchor="end"')]
    (ROOT/'assets/telemetry.svg').write_text(shell(561, 'Code languages and contribution calendar', body))
    links = ' · '.join(f'[{overrides.get(r["name"], (r["name"],))[0]}]({r["html_url"]})' for r in candidates[:6])
    readme = f'''<!-- Generated by scripts/update_profile.py. Personal copy is in the renderer; public stats update automatically. -->
<a href="https://github.com/{USER}?tab=overview"><img src="assets/market.svg" width="100%" alt="Kai Smith — activity exchange, 30-day contribution chart, repositories, stars and followers" /></a>

<img src="assets/watchlist.svg" width="100%" alt="Kai Smith — student developer focused on software, data and finance; public project watchlist" />

{links}

<img src="assets/telemetry.svg" width="100%" alt="Live language composition, contribution calendar, current and longest streaks, and last refresh time" />

<div align="center">

[GitHub](https://github.com/{USER}) · [All projects](https://github.com/{USER}?tab=repositories) · [Refresh status](https://github.com/{USER}/{USER}/actions/workflows/profile.yml)

<sub>Built from my public GitHub activity. Scheduled refresh every six hours; GitHub may delay scheduled runs. Language shares exclude forks, this profile, and the standalone Employee API copy. Streaks use the displayed calendar; an active yesterday streak carries through today.</sub>

</div>
'''
    (ROOT/'README.md').write_text(readme)


if __name__ == '__main__':
    (ROOT/'assets').mkdir(exist_ok=True)
    data = collect()
    render(data)
    print(f'Rendered profile: {len(data["days"])} calendar days, {len(data["repos"])} public repositories.')
