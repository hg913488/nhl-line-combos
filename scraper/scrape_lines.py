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
    page.goto(url, wait_until="networkidle", timeout=30000)

    team_data = {"forwards": [], "defense": [], "goalies": []}

    # Forward lines — each line combo section has a heading and a grid of player cards
    # Daily Faceoff uses sections with class patterns like "line-combo-section"
    # We grab all player name elements within each section block

    sections = page.query_selector_all(".line-combination-section, [class*='line-combo'], [class*='LineCombo']")

    if not sections:
        # Fallback: try finding line tables by header text
        headers = page.query_selector_all("h2, h3, [class*='section-title'], [class*='SectionTitle']")
        for header in headers:
            text = (header.inner_text() or "").lower()
            # Get the container after this header
            container = header.evaluate_handle(
                "el => el.closest('section') || el.parentElement"
            )
            if not container:
                continue
            player_links = container.query_selector_all("a[href*='/players/']")
            players = [a.inner_text().strip() for a in player_links if a.inner_text().strip()]
            if not players:
                continue
            if "line" in text:
                team_data["forwards"].append(players)
            elif "pair" in text or "defense" in text:
                team_data["defense"].append(players)
            elif "goalie" in text or "starter" in text:
                team_data["goalies"].append(players)
    else:
        for section in sections:
            heading_el = section.query_selector("h2, h3, [class*='title']")
            heading = (heading_el.inner_text() if heading_el else "").lower()
            player_links = section.query_selector_all("a[href*='/players/']")
            players = [a.inner_text().strip() for a in player_links if a.inner_text().strip()]
            if not players:
                continue
            if "line" in heading:
                team_data["forwards"].append(players)
            elif "pair" in heading or "defense" in heading:
                team_data["defense"].append(players)
            elif "goalie" in heading:
                team_data["goalies"].append(players)

    # Last resort: grab ALL player links on page and bucket them by position via page structure
    if not any([team_data["forwards"], team_data["defense"], team_data["goalies"]]):
        print(f"  Fallback: grabbing all player links for {team_slug}")
        all_links = page.query_selector_all("a[href*='/players/']")
        players = list(dict.fromkeys(  # dedupe preserving order
            a.inner_text().strip() for a in all_links if a.inner_text().strip()
        ))
        # Without position context, dump into forwards as raw list
        if players:
            team_data["forwards"] = [players]

    return team_data


def main():
    all_data = {
        "source": "dailyfaceoff.com",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "teams": {}
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for team in TEAMS:
            try:
                print(f"Scraping {team}...")
                data = scrape_team(page, team)
                all_data["teams"][team] = data
                fwd_count = sum(len(line) for line in data["forwards"])
                def_count = sum(len(line) for line in data["defense"])
                print(f"  forwards: {fwd_count} players, defense: {def_count} players")
                time.sleep(1)
            except Exception as e:
                print(f"  FAILED {team}: {e}")
                all_data["teams"][team] = {"forwards": [], "defense": [], "goalies": []}

        browser.close()

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_data, f, indent=2)

    print(f"\nDone. Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
