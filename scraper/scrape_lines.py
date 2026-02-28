import json
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.dailyfaceoff.com/teams/{team}/line-combinations"
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
    "tampa-bay-lightning", "toronto-maple-leafs", "vancouver-canucks",
    "vegas-golden-knights", "washington-capitals", "winnipeg-jets",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def scrape_team(team_slug):
    url = BASE_URL.format(team=team_slug)
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "lxml")

    team_data = {
        "forwards": [],
        "defense": [],
        "goalies": []
    }

    sections = soup.find_all("h2")

    for header in sections:
        title = header.get_text(strip=True).lower()
        table = header.find_next("table")

        if not table:
            continue

        rows = table.find_all("tr")

        for row in rows:
            players = [a.get_text(strip=True) for a in row.find_all("a")]

            if not players:
                continue

            if "line" in title:
                team_data["forwards"].append(players)
            elif "pair" in title:
                team_data["defense"].append(players)
            elif "goalie" in title:
                team_data["goalies"].append(players)

    return team_data


def main():
    all_data = {
        "source": "dailyfaceoff.com",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "teams": {}
    }

    for team in TEAMS:
        try:
            print(f"Scraping {team}")
            all_data["teams"][team] = scrape_team(team)
            time.sleep(0.5)
        except Exception as e:
            print(f"Failed {team}: {e}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_data, f, indent=2)


if __name__ == "__main__":
    main()
