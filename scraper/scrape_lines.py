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


def fetch_espn_team_ids():
    """Fetch ESPN team IDs dynamically by matching slugs from the teams endpoint."""
    url = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams"
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    espn_map = {}
    for sport in data.get("sports", []):
        for league in sport.get("leagues", []):
            for team_entry in league.get("teams", []):
                t = team_entry.get("team", {})
                espn_slug = t.get("slug", "")
                espn_id = t.get("id", "")
                if espn_slug and espn_id:
                    espn_map[espn_slug] = int(espn_id)

    # Map our slugs to ESPN IDs
    slug_to_espn = {}
    for slug in TEAMS:
        if slug in espn_map:
            slug_to_espn[slug] = espn_map[slug]
        else:
            # Try partial match
            for espn_slug, espn_id in espn_map.items():
                if slug.replace("-", "") in espn_slug.replace("-", "") or espn_slug.replace("-", "") in slug.replace("-", ""):
                    slug_to_espn[slug] = espn_id
                    break

    print(f"  Matched {len(slug_to_espn)}/{len(TEAMS)} teams to ESPN IDs")
    for slug in TEAMS:
        if slug not in slug_to_espn:
            print(f"  WARNING: No ESPN match for {slug}")

    return slug_to_espn


def scrape_espn_injuries(espn_team_ids):
    """Fetch injury data for all teams from ESPN's core API."""
    injuries = {}

    for slug, espn_id in espn_team_ids.items():
        try:
            url = (
                f"https://sports.core.api.espn.com/v2/sports/hockey/"
                f"leagues/nhl/teams/{espn_id}/injuries?limit=100"
            )
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            team_injuries = []
            for item in data.get("items", []):
                ref_url = item.get("$ref", "")
                if not ref_url:
                    continue

                try:
                    inj_resp = SESSION.get(ref_url, timeout=10)
                    inj_data = inj_resp.json()
                except Exception as e:
                    print(f"    Failed to fetch injury ref for {slug}: {e}")
                    continue

                # Extract player name
                player_name = ""
                player_pos = ""
                athlete = inj_data.get("athlete", {})
                if isinstance(athlete, dict):
                    if "$ref" in athlete:
                        try:
                            ath_resp = SESSION.get(athlete["$ref"], timeout=10)
                            ath_data = ath_resp.json()
                            player_name = ath_data.get("displayName", "")
                            player_pos = ath_data.get("position", {}).get("abbreviation", "")
                        except Exception:
                            pass
                    else:
                        player_name = athlete.get("displayName", "")
                        player_pos = athlete.get("position", {}).get("abbreviation", "")

                # Extract status
                status = ""
                status_obj = inj_data.get("status", "")
                if isinstance(status_obj, str):
                    status = status_obj
                elif isinstance(status_obj, dict):
                    status = (
                        status_obj.get("type", {}).get("description", "")
                        or status_obj.get("description", "")
                        or status_obj.get("name", "")
                    )

                # Extract injury description
                description = ""
                inj_type = inj_data.get("type", {})
                if isinstance(inj_type, dict):
                    description = inj_type.get("description", "") or inj_type.get("name", "")
                elif isinstance(inj_type, str):
                    description = inj_type

                if not description:
                    description = (
                        inj_data.get("longComment", "")
                        or inj_data.get("shortComment", "")
                        or inj_data.get("description", "")
                    )

                if player_name:
                    team_injuries.append({
                        "name": player_name.upper(),
                        "pos": player_pos or "?",
                        "status": status or "Unknown",
                        "desc": description or "",
                    })

                time.sleep(0.1)

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

    # Fetch ESPN team ID mapping dynamically
    print("\nFetching ESPN team IDs...")
    espn_team_ids = fetch_espn_team_ids()

    # Scrape injuries
    print("\nFetching injuries from ESPN...")
    all_data["injuries"] = scrape_espn_injuries(espn_team_ids)
    print(f"Injury data for {len(all_data['injuries'])} teams.")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    populated = sum(1 for t in all_data["teams"].values() if t["forwards"])
    print(f"\nDone - {populated}/{len(TEAMS)} teams have forward data.")


if __name__ == "__main__":
    main()
