import json
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.dailyfaceoff.com/teams/{team}/line-combinations"
OUTPUT_PATH = "data/lines.json"

TEAMS = [
    "anaheim-ducks", "arizona-coyotes", "boston-bruins", "buffalo-sabres",
    "calgary-flames", "carolina-hurricanes", "chicago-blackhawks",
    "colorado-avalanche", "columbus-blue-jackets", "dallas-stars",
    "detroit-red-wings", "edmonton-oilers", "florida-panthers",
    "los-angeles-kings", "minnesota-wild", "montreal-canadiens",
    "nashville-predators", "new-jersey-devils", "new-york-islanders",
    "new-york-rangers", "ottawa-senators", "philadelphia-flyers",
    "pittsburgh-penguins", "san-jose-sharks", "seattle-kraken",
    "st-louis-blues", "tampa-bay-lightning", "toronto-maple-leafs",
    "vancouver-canucks", "vegas-golden-knights", "washington-capitals",
    "winnipeg-jets",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def scrape_team(team_slug):
    url = BASE_URL.format(team=team_slug)
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    team_data = {
        "forwards": [],
        "defense": [],
        "goalies": []
    }

    sections = soup.select(".line-combination")

    for section in sections:
        title = section.select_one(".line-combination__title")
        players = [p.get_text(strip=True) for p in section.select(".player-name")]

        if not title or not players:
            continue

        title_text = title.get_text(strip=True).lower()

        if "line" in title_text:
            team_data["forwards"].append(players)
        elif "pair" in title_text:
            team_data["defense"].append(players)
        elif "goalie" in title_text:
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
            print(f"Scraping {team}...")
            all_data["teams"][team] = scrape_team(team)
            time.sleep(0.5)  # be polite
        except Exception as e:
            print(f"Failed to scrape {team}: {e}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_data, f, indent=2)

    print("Done.")


if __name__ == "__main__":
    main()
