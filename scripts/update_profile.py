"""Render a GitHub profile terminal from public account data. Python stdlib only."""
import base64
import datetime as dt
import html
import json
import os
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USER = os.environ.get('PROFILE_USER', 'KaiAlexander-commits')
NOW = dt.datetime.now(dt.timezone.utc)
GREEN, RED, WHITE, MUTED = '#57e389', '#ff6577', '#eaf2ed', '#82958c'
COLORS = {'Python': '#3776ab', 'Java': '#b77913', 'JavaScript': '#f1e45b', 'CSS': '#ad91c7', 'HTML': '#e44d26', 'TypeScript': '#3178c6', 'Shell': '#8be9a0', 'Dockerfile': '#45616a', 'Vue': '#41b883', 'Markdown': '#829aca'}


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


def language_icon(language, x, y, size):
    """Embed vendored Devicon vectors so logos survive GitHub image rendering."""
    path = ROOT/'assets/icons'/f'{language.lower()}.svg'
    if not path.is_file():
        return rect(x, y, size, size, '#253640', 3) + text(x+size/2, y+size*.72, language[:2], size*.5, WHITE, 700, 'text-anchor="middle"')
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    icon = ET.fromstring(path.read_text())
    for key, value in {'x': x, 'y': y, 'width': size, 'height': size}.items():
        icon.set(key, str(value))
    if language == 'Markdown':
        icon.set('fill', WHITE)
        for element in icon.iter():
            if element.get('fill') in {'#000', '#000000', 'black'}:
                element.set('fill', WHITE)
    return ET.tostring(icon, encoding='unicode')


def line(x1, y1, x2, y2, color='#203029'):
    return f'<path d="M{x1} {y1}H{x2}" stroke="{color}"/>' if y1 == y2 else f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}"/>'


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


def activity_candles(days):
    """Weekly OHLC of the rolling 30-day contribution count / 10; no random prices."""
    today = NOW.date()
    def price(day):
        return sum(days.get((day-dt.timedelta(days=i)).isoformat(), 0) for i in range(30)) / 10
    start = today - dt.timedelta(days=25*7 + (today.weekday()+1)%7)
    candles = []
    for week in range(26):
        first = start + dt.timedelta(days=week*7)
        last = min(first+dt.timedelta(days=6), today)
        dates = [first+dt.timedelta(days=i) for i in range((last-first).days+1)]
        opening = price(first-dt.timedelta(days=1))
        values = [opening] + [price(day) for day in dates]
        candles.append({'open': opening, 'close': values[-1], 'high': max(values), 'low': min(values),
                        'volume': sum(days.get(day.isoformat(), 0) for day in dates)})
    return candles


def render(data):
    p, repos, days = data['profile'], data['repos'], data['days']
    candles = activity_candles(days)
    price, opening = candles[-1]['close'], candles[-1]['open']
    change = (price-opening)/opening*100 if opening else None
    up = price >= opening
    color = GREEN if up else RED
    candidates = [r for r in repos if r['name'] != USER]
    priority = ['Apartment-Database', 'Employee-Manager-Server', 'Trading-Algo', 'Employee-Manager-Dashboard', 'Final-Project']
    candidates.sort(key=lambda r: (priority.index(r['name']) if r['name'] in priority else len(priority), r['name']))
    candidates = candidates[:6]
    stars = sum(r['stargazers_count'] for r in repos)
    avatar = f'data:{data["avatar_mime"]};base64,{data["avatar"]}'
    languages = sorted(data['languages'].items(), key=lambda item: item[1], reverse=True)
    sector = languages[0][0] if languages else 'CODE'
    body = [rect(1, 1, 998, 44, '#111917'), line(1, 45, 999, 45, '#2c3730')]
    for i, dot in enumerate([RED, '#efc153', GREEN]):
        body.append(f'<circle cx="{26+i*17}" cy="23" r="4" fill="{dot}"/>')
    body += [text(92, 28, f'{USER} / README.md', 11, MUTED), text(965, 28, 'AUTO · 6H', 10, GREEN, extra='text-anchor="end"'),
             f'<image x="45" y="84" width="54" height="54" clip-path="url(#small-avatar)" xlink:href="{avatar}"/>',
             text(111, 111, '$KAIAL', 31, WHITE, 800, 'font-family="Arial,sans-serif"'),
             rect(257, 88, 164, 25, '#152d35', 13, '#255267'), text(339, 105, f'SECTOR · {sector.upper()}', 10, '#5da5cd', 600, 'text-anchor="middle"'),
             text(111, 137, 'Kai Smith · GitHub · price = 30-day contributions / 10', 11, MUTED, extra='font-family="Arial,sans-serif"'),
             text(955, 114, f'${price:.2f}', 36, WHITE, 800, 'text-anchor="end" font-family="Arial,sans-serif"'),
             text(955, 139, f'{"▲" if up else "▼"} {abs(change):.1f}% · 1 week' if change is not None else f'{"▲" if up else "▼"} ${abs(price-opening):.2f} · 1 week', 11, color, extra='text-anchor="end"')]
    chart_x, chart_y, chart_w, chart_h = 45, 171, 910, 250
    low = min(c['low'] for c in candles)
    high = max(c['high'] for c in candles)
    span = max(high-low, .1)
    def y(value):
        return round(chart_y+chart_h-(value-low)/span*chart_h, 2)
    for fraction in [0, .25, .5, .75, 1]:
        yy = chart_y + chart_h*fraction
        body.append(line(chart_x, yy, chart_x+chart_w, yy, '#23302b'))
    max_volume = max(max(c['volume'] for c in candles), 1)
    for i, c in enumerate(candles):
        x = chart_x + i*35
        green = c['close'] >= c['open']
        cc = GREEN if green else RED
        body += [line(x+10, y(c['high']), x+10, y(c['low']), cc),
                 rect(x, min(y(c['open']), y(c['close'])), 22, max(abs(y(c['open'])-y(c['close'])), 1.5), cc),
                 rect(x, 491-c['volume']/max_volume*60, 22, c['volume']/max_volume*60, '#3b444d')]
    body += [text(45, 510, 'volume = contributions per week · last 26 weeks', 10, MUTED), text(955, 510, 'github.com', 10, MUTED, extra='text-anchor="end"')]
    ticker_items = []
    for r in candidates:
        symbol = r['name'].replace('-','').upper()[:16]
        ticker_items.append(f'{symbol} ★{r["stargazers_count"]} ▲')
    ticker = '     '.join(ticker_items)
    ticker_width = max(960, len(ticker)*6.65+80)
    body += [rect(45, 535, 910, 34, '#161f26'), '<g clip-path="url(#ticker-clip)"><g>',
             f'<animateTransform attributeName="transform" type="translate" from="0 0" to="-{ticker_width} 0" dur="36s" repeatCount="indefinite"/>',
             text(61, 557, ticker, 11, '#d5e2df', 600), text(61+ticker_width, 557, ticker, 11, '#d5e2df', 600), '</g></g>',
             text(45, 611, 'Activity index: $1.00 = 10 GitHub contributions in the trailing 30 days.', 11, '#b3bdbb', extra='font-family="Arial,sans-serif"')]

    def card(top, height, label):
        return [rect(45, top, 910, height, '#0d1218', 12, '#253039'), text(81, top+41, f'▲ {label}', 11, GREEN, 600, 'letter-spacing="1.6"'), line(45, top+64, 955, top+64, '#253039')]
    body += card(634, 230, 'COMPANY PROFILE')
    body += [text(81, 739, p.get('name') or 'Kai Smith', 31, WHITE, 800, 'font-family="Arial,sans-serif"'),
             text(81, 777, 'Python developer. Building software, exploring data and finance.', 16, '#d4dcdf', 500, 'font-family="Arial,sans-serif"'),
             text(81, 824, f'{p.get("location") or "USA"} · {p["followers"]} followers · {len(repos)} repositories · ★ {stars} stars', 11, MUTED),
             f'<image x="790" y="695" width="126" height="126" clip-path="url(#large-avatar)" xlink:href="{avatar}"/>',
             '<circle cx="853" cy="758" r="65" fill="none" stroke="#3fca53" stroke-width="4"/>']
    holdings_top = 886
    holdings_h = 91+len(candidates)*47
    body += card(holdings_top, holdings_h, 'HOLDINGS')
    for i, repo in enumerate(candidates):
        yy = holdings_top+108+i*47
        symbol = repo['name'].upper().replace('-','')[:5]
        language = repo.get('language') or ('Python' if repo['name']=='Final-Project' else 'Code')
        age = (NOW-dt.datetime.fromisoformat(repo['pushed_at'].replace('Z','+00:00'))).total_seconds()/86400
        state = 'archived' if repo['archived'] else 'recent' if age <=30 else 'idle'
        state_color = GREEN if state=='recent' else MUTED
        if i:
            body.append(line(81, yy-24, 919, yy-24, '#303840'))
        body += [text(81, yy, symbol, 12, WHITE, 700), language_icon(language, 175, yy-15, 20),
                 text(204, yy, repo['name'][:36], 13, MUTED, extra='font-family="Arial,sans-serif"'),
                 text(688, yy, repo['pushed_at'][:10], 10, MUTED), text(826, yy, f'★ {repo["stargazers_count"]}', 13, WHITE, 600),
                 text(920, yy, f'▲ {state}', 10, state_color, extra='text-anchor="end"')]
    allocation_top = holdings_top+holdings_h+22
    body += card(allocation_top, 292, 'SECTOR ALLOCATION')
    denominator = sum(data['languages'].values()) or 1
    for i, (language, count) in enumerate(languages[:5]):
        yy = allocation_top+106+i*36
        share = count/denominator*100
        body += [language_icon(language, 80, yy-18, 25), text(113, yy, language, 14, WHITE, 700, 'font-family="Arial,sans-serif"'),
                 rect(283, yy-11, 557, 16, '#3b434b', 8), rect(283, yy-11, 557*share/100, 16, COLORS.get(language, GREEN), 8),
                 text(920, yy+1, f'{share:.0f}%', 12, MUTED, extra='text-anchor="end"')]
    volume_top = allocation_top+314
    body += card(volume_top, 269, 'VOLUME · 26 WEEKS')
    today = NOW.date()
    sunday = today-dt.timedelta(days=(today.weekday()+1)%7)
    start = sunday-dt.timedelta(weeks=25)
    shades = ['#19232b', '#123d29', '#17633a', '#238e41', GREEN]
    for i in range((today-start).days+1):
        day = start+dt.timedelta(days=i)
        count = days.get(day.isoformat(), 0)
        level = 0 if count==0 else 1 if count<3 else 2 if count<6 else 3 if count<10 else 4
        body += [f'<g><title>{day}: {count} contributions</title>{rect(81+i//7*16,volume_top+89+i%7*16,12,12,shades[level],2)}</g>']
    current, longest = streaks(days)
    for i, (label, value) in enumerate([('UP DAYS IN A ROW', f'{current} day'+('s' if current!=1 else '')), ('BEST RUN · YEAR', f'{longest} day'+('s' if longest!=1 else '')), ('VOLUME THIS YEAR', str(sum(days.values())))]):
        yy = volume_top+96+i*58
        body += [text(584, yy, label, 10, MUTED, extra='letter-spacing="1.5"'), text(584, yy+25, value, 23, WHITE, 800, 'font-family="Arial,sans-serif"')]
    height = volume_top+330
    body += [text(45, height-31, 'GITHUB ACTIVITY / AUTO REFRESH EVERY 6 HOURS', 10, GREEN), text(955, height-31, data['updated'], 10, MUTED, extra='text-anchor="end"')]
    defs = f'<defs><linearGradient id="bg" x2="0" y2="1"><stop stop-color="#17211b"/><stop offset=".45" stop-color="#0d1317"/><stop offset="1" stop-color="#080f0b"/></linearGradient><clipPath id="small-avatar"><circle cx="72" cy="111" r="27"/></clipPath><clipPath id="large-avatar"><circle cx="853" cy="758" r="63"/></clipPath><clipPath id="ticker-clip">{rect(45,535,910,34,"white")}</clipPath></defs>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1000" height="{height}" viewBox="0 0 1000 {height}" role="img" aria-labelledby="title"><title id="title">Kai Smith stock ticker — updating GitHub activity index</title>{defs}{rect(1,1,998,height-2,"url(#bg)",13,"#425c43")}<g font-family="Consolas,monospace">{"".join(body)}</g></svg>'
    (ROOT/'assets/terminal.svg').write_text(svg)
    links = ' · '.join(f'[{r["name"]}]({r["html_url"]})' for r in candidates)
    readme = f'''<!-- Generated by scripts/update_profile.py -->
<img src="assets/terminal.svg" width="100%" alt="Kai Smith stock ticker: activity-based price, 26-week candlestick chart and volume, scrolling project ticker, company profile, holdings, language allocation, and contribution streaks." />

{links}

<div align="center">

[GitHub](https://github.com/{USER}) · [Refresh status](https://github.com/{USER}/{USER}/actions/workflows/profile.yml)

<sub>Price = trailing 30-day GitHub contributions ÷ 10. Weekly candles show opening, highest, lowest and closing values of that activity index; volume is actual weekly contributions. Refreshes every six hours, subject to GitHub scheduling delays. Language shares exclude forks, this profile and the standalone Employee API copy. Holdings marked recent were pushed within 30 days.</sub>

</div>
'''
    (ROOT/'README.md').write_text(readme)


if __name__ == '__main__':
    (ROOT/'assets').mkdir(exist_ok=True)
    data = collect()
    render(data)
    print(f'Rendered profile: {len(data["days"])} calendar days, {len(data["repos"])} public repositories.')
