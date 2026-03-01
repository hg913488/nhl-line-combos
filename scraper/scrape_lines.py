import json
import time
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
    page.goto(url, wait_until="domcontentloaded", timeout=30000)

    # Wait for the line combo grid to appear
    try:
        page.wait_for_selector("div.w-1\\/3", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(1500)

    result = page.evaluate("""() => {
        const out = { forwards: [], defense: [], goalies: [] };

        // Player name is in a div with class containing "text-center"
        // that is a child of a flex-row container (one row = one line/pair)
        // Each player card: div.w-1/3.text-center > a[href*="/players/"] > img + div(name)

        function getPlayerName(card) {
            // Name is usually the last text node or a div after the image
            const a = card.querySelector('a[href*="/players/"]');
            if (!a) return null;
            // Get all text inside the anchor, skip image alt text
            const clone = a.cloneNode(true);
            // Remove img tags
            clone.querySelectorAll('img').forEach(i => i.remove());
            const text = clone.innerText || clone.textContent || '';
            const name = text.trim().replace(/\\s+/g, ' ');
            return name.length > 1 ? name.toUpperCase() : null;
        }

        // Find all flex-row line containers
        // From the DOM: div.mb-4.flex.flex-row.flex-wrap.justify-evenly.border-b
        // Each contains player cards (div.w-1/3 or similar)
        const lineRows = document.querySelectorAll(
            'div[class*="flex-row"][class*="justify-evenly"], ' +
            'div[class*="flex-row"][class*="justify-center"], ' +
            'div[class*="flex-row"][class*="border-b"]'
        );

        // Track what section we're in by walking through headings and line rows in DOM order
        // Get all relevant elements in document order
        const allEls = Array.from(document.querySelectorAll(
            'h2, h3, h4, div[class*="flex-row"][class*="justify-evenly"], div[class*="flex-row"][class*="border-b"]'
        ));

        let currentSection = 'forwards'; // default

        for (const el of allEls) {
            if (['H2','H3','H4'].includes(el.tagName)) {
                const text = (el.innerText || el.textContent || '').toLowerCase();
                if (text.includes('forward') || text.includes('line')) currentSection = 'forwards';
                else if (text.includes('defensive') || text.includes('pair') || text.includes('defense')) currentSection = 'defense';
                else if (text.includes('goalie') || text.includes('starter') || text.includes('backup')) currentSection = 'goalies';
                continue;
            }

            // It's a flex row — extract player cards from it
            // Cards are children that contain a player link
            const cards = el.querySelectorAll('div[class*="w-1"]');
            const players = [];

            for (const card of cards) {
                const name = getPlayerName(card);
                if (name && name.length > 2) players.push(name);
            }

            // Filter: forwards rows have 3 players, defense pairs have 2, goalies have 1-2
            if (players.length >= 1) {
                if (currentSection === 'forwards' && players.length >= 2) {
                    out.forwards.push(players);
                } else if (currentSection === 'defense' && players.length >= 1) {
                    out.defense.push(players);
                } else if (currentSection === 'goalies') {
                    out.goalies.push(players);
                } else if (players.length >= 3) {
                    out.forwards.push(players);
                } else if (players.length === 2) {
                    out.defense.push(players);
                }
            }
        }

        // Dedupe
        for (const key of ['forwards', 'defense', 'goalies']) {
            const seen = new Set();
            out[key] = out[key].filter(line => {
                const sig = JSON.stringify(line);
                if (seen.has(sig)) return false;
                seen.add(sig);
                return true;
            });
        }

        return out;
    }""")

    return result


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
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = context.new_page()

        # Warm up with homepage visit for cookies
        print("Warming up session on dailyfaceoff.com...")
        try:
            page.goto("https://www.dailyfaceoff.com", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"  Warmup warning: {e}")

        for team in TEAMS:
            try:
                print(f"Scraping {team}...")
                data = scrape_team(page, team)
                all_data["teams"][team] = data

                fwd = len(data["forwards"])
                dfn = len(data["defense"])
                gol = len(data["goalies"])
                print(f"  → {fwd} fwd lines, {dfn} def pairs, {gol} goalies")

                time.sleep(2)

            except Exception as e:
                print(f"  FAILED {team}: {e}")
                all_data["teams"][team] = {"forwards": [], "defense": [], "goalies": []}

        browser.close()

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_data, f, indent=2)

    populated = sum(1 for t in all_data["teams"].values() if t["forwards"])
    print(f"\nDone — {populated}/{len(TEAMS)} teams have forward data.")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
