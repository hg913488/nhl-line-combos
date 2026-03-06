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
    games = page_props.get("data", [])

    if not isinstance(games, list):
        print(f"  Unexpected data type: {type(games)}")
        return []

    print(f"  Found {len(games)} games")

    matchups = []
    for game in games:
        try:
            # Build W-L-OTL record string
            def make_record(prefix):
                w = game.get(f"{prefix}GoalieWins", "")
                l = game.get(f"{prefix}GoalieLosses", "")
                otl = game.get(f"{prefix}GoalieOvertimeLosses", "")
                if w != "" and l != "":
                    return f"{w}-{l}-{otl}" if otl != "" else f"{w}-{l}"
                return ""

            matchup = {
                "away": {
                    "team": game.get("awayTeamSlug", ""),
                    "goalie": (game.get("awayGoalieName", "") or "").upper(),
                    "status": game.get("awayNewsStrengthName", "") or "Unconfirmed",
                    "headshotUrl": game.get("awayGoalieHeadshotUrl", ""),
                    "stats": {
                        "record": make_record("away"),
                        "gaa": str(game.get("awayGoalieGoalsAgainstAvg", "")) if game.get("awayGoalieGoalsAgainstAvg") else "",
                        "svpct": str(game.get("awayGoalieSavePercentage", "")) if game.get("awayGoalieSavePercentage") else "",
                        "so": game.get("awayGoalieShutouts", ""),
                    },
                },
                "home": {
                    "team": game.get("homeTeamSlug", ""),
                    "goalie": (game.get("homeGoalieName", "") or "").upper(),
                    "status": game.get("homeNewsStrengthName", "") or "Unconfirmed",
                    "headshotUrl": game.get("homeGoalieHeadshotUrl", ""),
                    "stats": {
                        "record": make_record("home"),
                        "gaa": str(game.get("homeGoalieGoalsAgainstAvg", "")) if game.get("homeGoalieGoalsAgainstAvg") else "",
                        "svpct": str(game.get("homeGoalieSavePercentage", "")) if game.get("homeGoalieSavePercentage") else "",
                        "so": game.get("homeGoalieShutouts", ""),
                    },
                },
                "date": game.get("date", ""),
                "time": game.get("time", ""),
            }

            matchups.append(matchup)
            print(f"  {matchup['away']['team']} @ {matchup['home']['team']}: "
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
