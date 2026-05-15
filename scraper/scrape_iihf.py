"""
IIHF World Championship scraper using Puppeteer (Node.js) as a subprocess.
The IIHF website is Cloudflare-protected; a real browser is required.
Outputs:
  data/iihf_groups.json   — group standings
  data/iihf_schedule.json — full schedule with scores
"""

import json
import subprocess
import datetime
import sys

GROUPS_PATH = "data/iihf_groups.json"
SCHEDULE_PATH = "data/iihf_schedule.json"

# Inline Node/Puppeteer script — uses npx puppeteer if available
NODE_SCRIPT = r"""
const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();
  await page.setUserAgent(
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
  );

  const result = { standings: {}, games: [] };

  // ── Standings ──────────────────────────────────────────────────────────
  await page.goto('https://www.iihf.com/en/events/2026/wm/standings/group', {
    waitUntil: 'networkidle2',
    timeout: 30000,
  });
  await new Promise(r => setTimeout(r, 3000));

  const standingsData = await page.evaluate(() => {
    const groups = {};
    document.querySelectorAll('table').forEach(table => {
      const header = table.closest('section')?.querySelector('h2,h3')?.textContent?.trim() || '';
      const groupLetter = header.match(/Group ([A-Z])/)?.[1];
      if (!groupLetter) return;
      const rows = [];
      table.querySelectorAll('tbody tr').forEach(tr => {
        const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
        if (cells.length < 5) return;
        rows.push(cells);
      });
      groups[groupLetter] = rows;
    });
    return groups;
  });
  result.standings = standingsData;

  // ── Schedule ───────────────────────────────────────────────────────────
  await page.goto('https://www.iihf.com/en/events/2026/wm/schedule', {
    waitUntil: 'networkidle2',
    timeout: 30000,
  });
  await new Promise(r => setTimeout(r, 3000));

  const scheduleText = await page.evaluate(() => document.body.innerText);
  result.scheduleText = scheduleText;

  await browser.close();
  process.stdout.write(JSON.stringify(result));
})().catch(e => { process.stderr.write(e.message); process.exit(1); });
"""


def parse_schedule_text(text):
    """Parse the IIHF schedule page text into a list of game dicts."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    games = []
    i = 0
    gid = 1
    while i < len(lines):
        # Look for date pattern like "15 MAY" or "15 May"
        import re
        date_m = re.match(r'^(\d{1,2})\s+(MAY|JUN|may|jun)$', lines[i], re.IGNORECASE)
        if date_m:
            day = int(date_m.group(1))
            month = 5 if 'MAY' in date_m.group(2).upper() else 6
            date_str = f"2026-{month:02d}-{day:02d}"
            # Next few lines: score/state, away, home, venue+group, times
            # Pattern: score line, team, state/score, team, venue line, time lines
            j = i + 1
            # Find score/state marker
            state = "scheduled"
            away_score = None
            home_score = None
            away = None
            home = None
            group = None
            time_et = None

            # Look ahead up to 12 lines for this game block
            block = lines[j:j+12]

            # Check for FINAL or UPCOMING
            for bi, bl in enumerate(block):
                if bl in ('FINAL', 'UPCOMING', 'LIVE'):
                    if bl == 'FINAL':
                        state = 'final'
                        # scores might be before/after
                        if bi > 0 and re.match(r'^\d+$', block[bi-1]):
                            away_score = int(block[bi-1])
                        if bi + 1 < len(block) and re.match(r'^\d+$', block[bi+1]):
                            home_score = int(block[bi+1])
                    break

            # Find team codes (3-letter all caps)
            teams_found = []
            for bl in block:
                if re.match(r'^[A-Z]{3}$', bl) and bl not in ('MAY', 'JUN', 'UTC', 'BUY', 'QF', 'TBD'):
                    teams_found.append(bl)
            if len(teams_found) >= 2:
                away = teams_found[0]
                home = teams_found[1]

            # Find group
            for bl in block:
                gm = re.search(r'Group ([AB])', bl)
                if gm:
                    group = gm.group(1)
                    break
            if not group:
                for bl in block:
                    if 'QF' in bl:
                        group = 'QF'
                        break
                    if 'SF' in bl or 'Semifinal' in bl.lower():
                        group = 'SF'
                        break
                    if 'Final' in bl and 'Bronze' not in bl:
                        group = 'GOLD'
                        break
                    if 'Bronze' in bl:
                        group = 'BRZ'
                        break

            # Find ET time (Your time)
            for bl in block:
                tm = re.match(r'^(\d{1,2}:\d{2})\s*\(Your time\)', bl)
                if tm:
                    # convert to ET: Your time is PDT (UTC-7), ET is EDT (UTC-4)
                    h, m = map(int, tm.group(1).split(':'))
                    h = (h + 3) % 24
                    ampm = 'AM' if h < 12 else 'PM'
                    h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
                    time_et = f"{h12}:{m:02d} {ampm} ET"
                    break

            if away and home:
                games.append({
                    'id': f'iihf-g{gid:03d}',
                    'date': date_str,
                    'time': time_et or 'TBD',
                    'group': group or '?',
                    'away': away,
                    'home': home,
                    'awayScore': away_score,
                    'homeScore': home_score,
                    'state': state,
                })
                gid += 1
            i = j + len(block)
            continue
        i += 1
    return games


def run_puppeteer():
    result = subprocess.run(
        ['node', '-e', NODE_SCRIPT],
        capture_output=True, text=True, timeout=90
    )
    if result.returncode != 0:
        print(f"Puppeteer error: {result.stderr}", file=sys.stderr)
        return None
    return json.loads(result.stdout)


def main():
    print("Running IIHF scraper via Puppeteer...")
    data = run_puppeteer()
    if not data:
        print("Failed to fetch IIHF data", file=sys.stderr)
        sys.exit(1)

    today = str(datetime.date.today())

    # ── Write schedule ─────────────────────────────────────────────────────
    games = parse_schedule_text(data.get('scheduleText', ''))
    schedule = {
        'tournament': '2026 IIHF World Championship',
        'updatedAt': today,
        'games': games,
    }
    with open(SCHEDULE_PATH, 'w') as f:
        json.dump(schedule, f, indent=2)
    print(f"iihf_schedule.json — {len(games)} games")

    # ── Write standings ────────────────────────────────────────────────────
    # standings parsing is complex; for now, keep manual JSON or extend later
    print("Note: standings require manual update or extended parsing.")
    print("Done.")


if __name__ == '__main__':
    main()
