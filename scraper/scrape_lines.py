import json
import time
import requests
from bs4 import BeautifulSoup

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


def scrape_team(team_slug):
    url = f"https://www.dailyfaceoff.com/teams/{team_slug}/line-combinations"
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        return {"forwards": [], "defense": [], "goalies": []}

    data = json.loads(script.string)
    players = (
        data.get("props", {})
            .get("pageProps", {})
            .get("combinations", {})
            .get("players", [])
    )

    # Group players by groupIdentifier, only even strength
    groups = {}
    for p in players:
        if p.get("categoryIdentifier") != "ev":
            continue
        group = p.get("groupIdentifier", "")
        if group not in groups:
            groups[group] = []
        groups[group].append(p.get("name", "").upper())

    forwards = [groups[k] for k in ["f1", "f2", "f3", "f4"] if k in groups and groups[k]]
    defense = [groups[k] for k in ["d1", "d2", "d3"] if k in groups and groups[k]]
    goalies = [[p] for p in groups.get("g", [])]

    return {"forwards": forwards, "defense": defense, "goalies": goalies}


def main():
    all_data = {
        "source": "dailyfaceoff.com",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "teams": {}
    }

    for team in TEAMS:
        try:
            print(f"Scraping {team}...")
            data = scrape_team(team)
            all_data["teams"][team] = data
            fwd = len(data["forwards"])
            dfn = len(data["defense"])
            gol = len(data["goalies"])
            print(f"  -> {fwd} fwd lines, {dfn} def pairs, {gol} goalies")
            time.sleep(1)
        except Exception as e:
            print(f"  FAILED {team}: {e}")
            all_data["teams"][team] = {"forwards": [], "defense": [], "goalies": []}

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_data, f, indent=2)

    populated = sum(1 for t in all_data["teams"].values() if t["forwards"])
    print(f"\nDone - {populated}/{len(TEAMS)} teams have forward data.")


if __name__ == "__main__":
    main()
