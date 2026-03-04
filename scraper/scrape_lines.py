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

ESPN_TEAM_IDS = {
    "anaheim-ducks": 25, "boston-bruins": 1, "buffalo-sabres": 2,
    "calgary-flames": 3, "carolina-hurricanes": 7, "chicago-blackhawks": 4,
    "colorado-avalanche": 17, "columbus-blue-jackets": 29,
    "dallas-stars": 9, "detroit-red-wings": 11, "edmonton-oilers": 22,
    "florida-panthers": 26, "los-angeles-kings": 8, "minnesota-wild": 30,
    "montreal-canadiens": 15, "nashville-predators": 18,
    "new-jersey-devils": 12, "new-york-islanders": 13,
    "new-york-rangers": 14, "ottawa-senators": 16,
    "philadelphia-flyers": 10, "pittsburgh-penguins": 19,
    "san-jose-sharks": 28, "seattle-kraken": 36, "st-louis-blues": 21,
    "tampa-bay-lightning": 27, "toronto-maple-leafs": 20,
    "utah-mammoth": 37, "vancouver-canucks": 23,
    "vegas-golden-knights": 35, "washington-capitals": 24,
    "winnipeg-jets": 31,
}

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
        return {"forwards": [], "defense": [], "goalies": [], "pp1": [], "pp2": []}

    data = json.loads(script.string)
    players = (
        data.get("props", {})
            .get("pageProps", {})
            .get("combinations", {})
            .get("players", [])
    )

    ev_groups = {}
    pp_groups = {}

    for p in players:
        category = p.get("categoryIdentifier", "")
        group = p.get("groupIdentifier", "")
        name = p.get("name", "").upper()

        if category == "ev":
            if group not in ev_groups:
                ev_groups[group] = []
            ev_groups[group].append(name)
        elif category == "pp":
            if group not in pp_groups:
                pp_groups[group] = []
            pp_groups[group].append(name)

    forwards = [ev_groups[k] for k in ["f1", "f2", "f3", "f4"] if k in ev_groups and ev_groups[k]]
    defense  = [ev_groups[k] for k in ["d1", "d2", "d3"]       if k in ev_groups and ev_groups[k]]
    goalies  = [[p] for p in ev_groups.get("g", [])]

    pp1 = pp_groups.get("pp1", [])
    pp2 = pp_groups.get("pp2", [])

    return {
        "forwards": forwards,
        "defense":  defense,
        "goalies":  goalies,
        "pp1":      pp1,
        "pp2":      pp2,
    }


def scrape_espn_injuries():
    """Fetch injury data for all teams from ESPN's core API."""
    injuries = {}
    debug_printed = False

    for slug, espn_id in ESPN_TEAM_IDS.items():
        try:
            url = (
                f"https://sports.core.api.espn.com/v2/sports/hockey/"
                f"leagues/nhl/teams/{espn_id}/injuries?limit=100"
            )
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            # Debug: print raw response for first team so we can see the structure
            if not debug_printed:
                print(f"  DEBUG raw ESPN response for {slug}:")
                print(f"  Keys: {list(data.keys())}")
                items = data.get("items", [])
                print(f"  Items count: {len(items)}")
                if items:
                    print(f"  First item keys: {list(items[0].keys())}")
                    print(f"  First item: {json.dumps(items[0], indent=2)[:1000]}")
                else:
                    # Maybe the data is under a different key
                    print(f"  Full response (first 1500 chars): {json.dumps(data)[:1500]}")
                debug_printed = True

            team_injuries = []
            for item in data.get("items", []):
                player_name = ""
                player_pos = ""
                status = ""
                description = ""

                # Get athlete info — follow $ref if needed
                athlete = item.get("athlete", {})
                if isinstance(athlete, dict) and "$ref" in athlete:
                    try:
                        ath_resp = SESSION.get(athlete["$ref"], timeout=10)
                        ath_data = ath_resp.json()
                        player_name = ath_data.get("displayName", "")
                        player_pos = ath_data.get("position", {}).get("abbreviation", "")
                    except Exception as e:
                        print(f"    Failed to fetch athlete ref for {slug}: {e}")
                elif isinstance(athlete, dict):
                    player_name = athlete.get("displayName", "")
                    player_pos = athlete.get("position", {}).get("abbreviation", "")

                # Get injury status
                status_obj = item.get("status", "")
                if isinstance(status_obj, str):
                    status = status_obj
                elif isinstance(status_obj, dict):
                    # Could be nested: status.type.description or status.description
                    status = (
                        status_obj.get("type", {}).get("description", "")
                        or status_obj.get("description", "")
                        or status_obj.get("name", "")
                    )

                # Get injury description / type
                inj_type = item.get("type", {})
                if isinstance(inj_type, dict):
                    description = inj_type.get("description", "") or inj_type.get("name", "")
                elif isinstance(inj_type, str):
                    description = inj_type

                # Fallback: check for longComment or shortComment
                if not description:
                    description = item.get("longComment", "") or item.get("shortComment", "") or item.get("details", {}).get("detail", "") if isinstance(item.get("details"), dict) else ""

                if player_name:
                    team_injuries.append({
                        "name": player_name.upper(),
                        "pos": player_pos or "?",
                        "status": status or "Unknown",
                        "desc": description or "",
                    })

            if team_injuries:
                injuries[slug] = team_injuries
                print(f"  Injuries for {slug}: {len(team_injuries)} players")

            time.sleep(0.3)

        except Exception as e:
            print(f"  ESPN injury fetch failed for {slug}: {e}")

    return injuries


def main():
    all_data = {
        "source":     "dailyfaceoff.com",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "teams":      {},
        "injuries":   {},
    }

    for team in TEAMS:
        try:
            print(f"Scraping {team}...")
            data = scrape_team(team)
            all_data["teams"][team] = data
            print(f"  -> {len(data['forwards'])} fwd lines, {len(data['defense'])} def pairs, "
                  f"{len(data['goalies'])} goalies, "
                  f"PP1: {len(data['pp1'])} players, PP2: {len(data['pp2'])} players")
            time.sleep(1)
        except Exception as e:
            print(f"  FAILED {team}: {e}")
            all_data["teams"][team] = {"forwards": [], "defense": [], "goalies": [], "pp1": [], "pp2": []}

    print("\nFetching injuries from ESPN...")
    all_data["injuries"] = scrape_espn_injuries()
    print(f"Injury data for {len(all_data['injuries'])} teams.")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    populated = sum(1 for t in all_data["teams"].values() if t["forwards"])
    print(f"\nDone - {populated}/{len(TEAMS)} teams have forward data.")


if __name__ == "__main__":
    main()
