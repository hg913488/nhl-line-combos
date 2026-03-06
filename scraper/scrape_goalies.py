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

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def name_to_slug(name):
    """Convert a team display name to our slug format."""
    overrides = {
        "Vegas Golden Knights": "vegas-golden-knights",
        "Utah Mammoth": "utah-mammoth",
        "Montréal Canadiens": "montreal-canadiens",
        "Montreal Canadiens": "montreal-canadiens",
        "St. Louis Blues": "st-louis-blues",
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
        print("  No __NEXT_DATA__ found")
        return []

    raw = json.loads(script.string)
    page_props = raw.get("props", {}).get("pageProps", {})

    # pageProps.data is a list of game objects
    games = page_props.get("data", [])
    if not isinstance(games, list):
        print(f"  Unexpected data type: {type(games)}")
        print(f"  DEBUG: {json.dumps(page_props)[:2000]}")
        return []

    print(f"  Found {len(games)} games")

    # Debug: print first game structure
    if games:
        print(f"  First game keys: {list(games[0].keys())}")
        print(f"  First game (first 1500 chars): {json.dumps(games[0])[:1500]}")

    matchups = []
    for game in games:
        try:
            # Extract team and goalie info — adapt keys based on debug output
            away_team_name = (
                game.get("awayTeam", {}).get("name", "")
                or game.get("awayTeamName", "")
                or game.get("away_team", "")
                or ""
            )
            home_team_name = (
                game.get("homeTeam", {}).get("name", "")
                or game.get("homeTeamName", "")
                or game.get("home_team", "")
                or ""
            )

            # Try multiple possible structures for goalie data
            away_goalie = (
                game.get("awayGoalie", {})
                or game.get("awayStarter", {})
                or game.get("away_goalie", {})
                or {}
            )
            home_goalie = (
                game.get("homeGoalie", {})
                or game.get("homeStarter", {})
                or game.get("home_goalie", {})
                or {}
            )

            if isinstance(away_goalie, str):
                away_goalie = {"name": away_goalie}
            if isinstance(home_goalie, str):
                home_goalie = {"name": home_goalie}

            def extract_goalie(g):
                if not g:
                    return {"goalie": "", "status": "Unconfirmed", "stats": {}}
                name = (
                    g.get("name", "")
                    or g.get("playerName", "")
                    or g.get("displayName", "")
                    or ""
                )
                status = (
                    g.get("status", "")
                    or g.get("confirmation", "")
                    or g.get("confirmedStatus", "")
                    or "Unconfirmed"
                )
                stats = {}
                # Try to get stats from various possible keys
                for k in ["record", "wlt", "w_l_otl"]:
                    if g.get(k):
                        stats["record"] = g[k]
                        break
                for k in ["gaa", "goalsAgainstAverage"]:
                    if g.get(k):
                        stats["gaa"] = str(g[k])
                        break
                for k in ["savePct", "svPct", "savePercentage", "sv_pct"]:
                    if g.get(k):
                        stats["svpct"] = str(g[k])
                        break
                return {
                    "goalie": name.upper(),
                    "status": status,
                    "stats": stats,
                }

            away_slug = name_to_slug(away_team_name) if away_team_name else ""
            home_slug = name_to_slug(home_team_name) if home_team_name else ""

            matchup = {
                "away": {
                    "team": away_slug,
                    **extract_goalie(away_goalie),
                },
                "home": {
                    "team": home_slug,
                    **extract_goalie(home_goalie),
                },
            }
            matchups.append(matchup)
            print(f"  {away_slug} @ {home_slug}: "
                  f"{matchup['away']['goalie']} ({matchup['away']['status']}) vs "
                  f"{matchup['home']['goalie']} ({matchup['home']['status']})")

        except Exception as e:
            print(f"    Error parsing game: {e}")

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

    print(f"\nDone — {len(matchups)} matchups saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
