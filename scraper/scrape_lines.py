import json
import time
import requests
from bs4 import BeautifulSoup

OUTPUT_PATH = "data/goalies.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Map DailyFaceoff team names/slugs to our app slugs
TEAM_SLUG_MAP = {
    "anaheim-ducks": "anaheim-ducks",
    "boston-bruins": "boston-bruins",
    "buffalo-sabres": "buffalo-sabres",
    "calgary-flames": "calgary-flames",
    "carolina-hurricanes": "carolina-hurricanes",
    "chicago-blackhawks": "chicago-blackhawks",
    "colorado-avalanche": "colorado-avalanche",
    "columbus-blue-jackets": "columbus-blue-jackets",
    "dallas-stars": "dallas-stars",
    "detroit-red-wings": "detroit-red-wings",
    "edmonton-oilers": "edmonton-oilers",
    "florida-panthers": "florida-panthers",
    "los-angeles-kings": "los-angeles-kings",
    "minnesota-wild": "minnesota-wild",
    "montreal-canadiens": "montreal-canadiens",
    "nashville-predators": "nashville-predators",
    "new-jersey-devils": "new-jersey-devils",
    "new-york-islanders": "new-york-islanders",
    "new-york-rangers": "new-york-rangers",
    "ottawa-senators": "ottawa-senators",
    "philadelphia-flyers": "philadelphia-flyers",
    "pittsburgh-penguins": "pittsburgh-penguins",
    "san-jose-sharks": "san-jose-sharks",
    "seattle-kraken": "seattle-kraken",
    "st-louis-blues": "st-louis-blues",
    "tampa-bay-lightning": "tampa-bay-lightning",
    "toronto-maple-leafs": "toronto-maple-leafs",
    "utah-mammoth": "utah-mammoth",
    "vancouver-canucks": "vancouver-canucks",
    "vegas-golden-knights": "vegas-golden-knights",
    "washington-capitals": "washington-capitals",
    "winnipeg-jets": "winnipeg-jets",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def name_to_slug(name):
    """Convert a team display name to our slug format."""
    overrides = {
        "Vegas Golden Knights": "vegas-golden-knights",
        "Utah Mammoth": "utah-mammoth",
        "Montréal Canadiens": "montreal-canadiens",
        "Montreal Canadiens": "montreal-canadiens",
    }
    if name in overrides:
        return overrides[name]
    return name.lower().replace(" ", "-").replace(".", "")


def scrape_starting_goalies():
    """Scrape today's starting goalies from DailyFaceoff."""
    url = "https://www.dailyfaceoff.com/starting-goalies"
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        print("  No __NEXT_DATA__ found, falling back to HTML parsing")
        return parse_goalies_html(soup)

    data = json.loads(script.string)
    page_props = data.get("props", {}).get("pageProps", {})

    # Debug: print available keys
    print(f"  pageProps keys: {list(page_props.keys())}")

    # Try to find the games/matchups data
    games = (
        page_props.get("games", [])
        or page_props.get("matchups", [])
        or page_props.get("goalieMatchups", [])
        or page_props.get("data", {}).get("games", [])
        or []
    )

    if not games:
        # Print first 2000 chars to debug structure
        print(f"  DEBUG pageProps (first 2000 chars): {json.dumps(page_props)[:2000]}")
        print("  No games found in __NEXT_DATA__, falling back to HTML parsing")
        return parse_goalies_html(soup)

    print(f"  Found {len(games)} games in __NEXT_DATA__")

    matchups = []
    for game in games:
        try:
            away_team = game.get("awayTeam", {})
            home_team = game.get("homeTeam", {})
            away_goalie = game.get("awayGoalie", {}) or game.get("awayStarter", {})
            home_goalie = game.get("homeGoalie", {}) or game.get("homeStarter", {})

            matchup = {
                "away": {
                    "team": name_to_slug(away_team.get("name", "") or away_team.get("teamName", "")),
                    "goalie": (away_goalie.get("name", "") or away_goalie.get("playerName", "")).upper(),
                    "status": away_goalie.get("status", "") or away_goalie.get("confirmation", "Unconfirmed"),
                    "stats": {
                        "record": away_goalie.get("record", ""),
                        "gaa": away_goalie.get("gaa", ""),
                        "svpct": away_goalie.get("savePct", "") or away_goalie.get("svPct", ""),
                    },
                },
                "home": {
                    "team": name_to_slug(home_team.get("name", "") or home_team.get("teamName", "")),
                    "goalie": (home_goalie.get("name", "") or home_goalie.get("playerName", "")).upper(),
                    "status": home_goalie.get("status", "") or home_goalie.get("confirmation", "Unconfirmed"),
                    "stats": {
                        "record": home_goalie.get("record", ""),
                        "gaa": home_goalie.get("gaa", ""),
                        "svpct": home_goalie.get("savePct", "") or home_goalie.get("svPct", ""),
                    },
                },
            }
            matchups.append(matchup)
        except Exception as e:
            print(f"    Error parsing game: {e}")

    return matchups


def parse_goalies_html(soup):
    """Fallback: parse starting goalies from the rendered HTML."""
    matchups = []

    # Look for matchup sections — each game has away @ home with goalie info
    # The HTML structure shows team names and goalie names in specific patterns
    text = soup.get_text()

    # Simple pattern: find all "Team A at Team B" blocks
    # This is a rough fallback — the __NEXT_DATA__ approach is preferred
    print("  HTML fallback parsing not fully implemented — check __NEXT_DATA__ debug output")
    return matchups


def main():
    print("Fetching starting goalies from DailyFaceoff...")
    matchups = scrape_starting_goalies()

    output = {
        "source": "dailyfaceoff.com",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "matchups": matchups,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Done — {len(matchups)} matchups saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
