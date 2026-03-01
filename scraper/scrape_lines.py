import json
import time
import re
from playwright.sync_api import sync_playwright

OUTPUT_PATH = "data/lines.json"

TEAMS = [
    "anaheim-ducks", "boston-bruins", "buffalo-sabres", "calgary-flames",
    "carolina-hurricanes", "chicago-blackhawks", "colorado-avalanche",
    "columbus-blue-jackets", "dallas-stars", "detroit-red-wings",
    "edmonton-oilers", "florida-panthers", "los-angeles-kings",
    "minnesota-wild", "montreal-canadiens", "nashville-predators",
    "new-jersey-devils", "new-york-islanders", "new-york-rangers",
    "ottawa-senators", "philadelphia-flyers", "pittsburgh-penguins",
    "san-jose-sharks", "seattle-kraken", "st-louis-blues",
    "tampa-bay-lightning", "toronto-maple-leafs", "utah-mammoth",
    "vancouver-canucks", "vegas-golden-knights", "washington-capitals",
    "winnipeg-jets",
]


def scrape_team(page, team_slug):
    url = f"https://www.dailyfaceoff.com/teams/{team_slug}/line-combinations"
    page.goto(url, wait_until="networkidle", timeout=30000)

    # Use JS to walk the rendered DOM and extract line sections by heading + row structure
    result = page.evaluate("""() => {
        const out = { forwards: [], defense: [], goalies: [] };

        // Daily Faceoff renders sections with a heading then a table/grid of lines.
        // Each ROW in that grid = one line (3 forwards) or one pair (2 D) or goalie.
        // We find all headings, determine type, then grab rows of player links below them.

        function getPlayersInRow(rowEl) {
            const links = rowEl.querySelectorAll('a');
            const players = [];
            for (const a of links) {
                const href = a.getAttribute('href') || '';
                const text = (a.innerText || a.textContent || '').trim();
                // Only count actual player links (not nav/team links)
                if (text && text.length > 2 && text.length < 40 &&
                    (href.includes('/players/') || href.includes('/player/'))) {
                    players.push(text.toUpperCase());
                }
            }
            return players;
        }

        function extractSectionLines(startEl) {
            // Walk siblings after the heading to find the first table/grid
            let el = startEl.nextElementSibling;
            let depth = 0;
            while (el && depth < 8) {
                // Check this element and its children for rows of player links
                const rows = el.querySelectorAll('tr');
                if (rows.length > 0) {
                    const lines = [];
                    for (const row of rows) {
                        const players = getPlayersInRow(row);
                        if (players.length >= 1) lines.push(players);
                    }
                    if (lines.length > 0) return lines;
                }

                // No table rows — check for div/flex rows (player cards in a row)
                // Look for children that each contain a player link
                const children = Array.from(el.children);
                if (children.length >= 2) {
                    // Check if children are "cells" (each containing one player)
                    const playerCells = children.filter(c => c.querySelector('a'));
                    if (playerCells.length >= 2) {
                        // This might be one line laid out as flex children
                        const players = [];
                        for (const cell of playerCells) {
                            const links = cell.querySelectorAll('a');
                            for (const a of links) {
                                const href = a.getAttribute('href') || '';
                                const text = (a.innerText || a.textContent || '').trim();
                                if (text && text.length > 2 && text.length < 40 &&
                                    (href.includes('/players/') || href.includes('/player/'))) {
                                    players.push(text.toUpperCase());
                                    break; // one player per cell
                                }
                            }
                        }
                        if (players.length >= 2) return [players];
                    }
                }

                // If we hit another heading, stop
                if (['H1','H2','H3','H4'].includes(el.tagName)) break;
                el = el.nextElementSibling;
                depth++;
            }
            return [];
        }

        // Find all headings and section containers
        const allEls = document.querySelectorAll('h1,h2,h3,h4,[class*="title"],[class*="Title"],[class*="header"],[class*="Header"],[class*="section"],[class*="Section"]');

        for (const el of allEls) {
            const text = (el.innerText || el.textContent || '').toLowerCase().trim();
            if (!text || text.length > 80) continue;

            let type = null;
            if (/\\bline\\b/.test(text) && !text.includes('blue line') && !text.includes('goal line')) type = 'forwards';
            else if (/\\bpair\\b/.test(text) || text.includes('defense') || text.includes('defence')) type = 'defense';
            else if (text.includes('goalie') || text.includes('starter') || text.includes('backup')) type = 'goalies';

            if (!type) continue;

            const lines = extractSectionLines(el);
            if (lines.length > 0) {
                out[type].push(...lines);
            }
        }

        // Dedupe: remove exact duplicate lines
        for (const key of ['forwards', 'defense', 'goalies']) {
            const seen = new Set();
            out[key] = out[key].filter(line => {
                const sig = line.join('|');
                if (seen.has(sig)) return false;
                seen.add(sig);
                return true;
            });
        }

        return out;
    }""")

    # If JS extraction got nothing, fall back to regex on page text
    if not any([result["forwards"], result["defense"], result["goalies"]]):
        print(f"  JS extraction empty for {team_slug}, trying text regex fallback...")
        result = text_fallback(page)

    return result


def text_fallback(page):
    """Parse line structure from visible page text using LINE/PAIR/GOALIE markers."""
    out = {"forwards": [], "defense": [], "goalies": []}
    try:
        text = page.inner_text("body")
        # Split on section markers
        pattern = re.compile(
            r'(LINE\s*\d+|PAIR\s*\d+|DEFENSIVE\s*PAIR\s*\d+|GOALIE\s*STARTER|GOALIE\s*BACKUP|STARTING\s*GOALIE|BACKUP\s*GOALIE)',
            re.IGNORECASE
        )
        parts = pattern.split(text)
        current_type = None
        for i, part in enumerate(parts):
            lower = part.strip().lower()
            if re.search(r'line\s*\d', lower):
                current_type = "forwards"
            elif re.search(r'pair\s*\d|defensive', lower):
                current_type = "defense"
            elif "goalie" in lower or "starter" in lower or "backup" in lower:
                current_type = "goalies"
            elif current_type and i > 0:
                # Extract proper names: Title Case or ALL CAPS multi-word
                names = re.findall(
                    r'\b[A-Z][a-zA-Z\'\-\.]+(?:[\s\-][A-Z][a-zA-Z\'\-\.]+)+\b',
                    part
                )
                names = [n.upper() for n in names if 2 < len(n) < 40][:4]
                if names:
                    out[current_type].append(names)
                current_type = None
    except Exception as e:
        print(f"  Text fallback error: {e}")
    return out


def main():
    all_data = {
        "source": "dailyfaceoff.com",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "teams": {}
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        for team in TEAMS:
            try:
                print(f"\nScraping {team}...")
                data = scrape_team(page, team)
                all_data["teams"][team] = data

                fwd_lines = len(data["forwards"])
                def_pairs = len(data["defense"])
                goalies = len(data["goalies"])
                print(f"  → {fwd_lines} fwd lines, {def_pairs} def pairs, {goalies} goalies")

                time.sleep(1.5)

            except Exception as e:
                print(f"  FAILED {team}: {e}")
                all_data["teams"][team] = {"forwards": [], "defense": [], "goalies": []}

        browser.close()

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_data, f, indent=2)

    populated = sum(1 for t in all_data["teams"].values() if t["forwards"])
    print(f"\n✓ Done — {populated}/{len(TEAMS)} teams have forward data.")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
