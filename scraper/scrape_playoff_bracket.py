import json
import datetime
import urllib.request

OUTPUT_PATH = "data/playoff_bracket.json"
SEASON = "20252026"

# Scan window: R1 typically starts mid-April; give 45-day lookahead for future games
SCAN_START = datetime.date(2026, 4, 14)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main():
    scan_end = datetime.date.today() + datetime.timedelta(days=45)

    series_map = {}  # letter -> {meta, games: {gnum: game}}

    d = SCAN_START
    while d <= scan_end:
        try:
            data = fetch(f"https://api-web.nhle.com/v1/schedule/{d}")
        except Exception:
            d += datetime.timedelta(days=1)
            continue

        for day in data.get("gameWeek", []):
            for g in day.get("games", []):
                if g.get("gameType") != 3:
                    continue
                ss = g.get("seriesStatus", {})
                letter = ss.get("seriesLetter", "?")
                gnum = ss.get("gameNumberOfSeries", 0)

                if letter not in series_map:
                    series_map[letter] = {"meta": ss, "games": {}}
                series_map[letter]["meta"] = ss  # always keep latest

                state_raw = g.get("gameState", "FUT")
                if state_raw == "OFF":
                    state = "final"
                elif state_raw == "FUT":
                    state = "scheduled"
                else:
                    state = "live"

                series_map[letter]["games"][gnum] = {
                    "gameNumber": gnum,
                    "date": day["date"],
                    "awayAbbr": g["awayTeam"]["abbrev"],
                    "homeAbbr": g["homeTeam"]["abbrev"],
                    "awayScore": g.get("awayTeam", {}).get("score"),
                    "homeScore": g.get("homeTeam", {}).get("score"),
                    "state": state,
                }

        d += datetime.timedelta(days=1)

    if not series_map:
        print("No playoff games found — skipping output")
        return

    # Group by round number
    by_round = {}
    for letter, s in series_map.items():
        rnd = s["meta"].get("round", 0)
        by_round.setdefault(rnd, []).append(letter)

    r1_letters = sorted(by_round.get(1, []))
    r2_letters = sorted(by_round.get(2, []))
    r3_letters = sorted(by_round.get(3, []))
    r4_letters = sorted(by_round.get(4, []))

    # East = first half of sorted letters per round, West = second half
    mid1 = len(r1_letters) // 2
    r1_east = r1_letters[:mid1]
    r1_west = r1_letters[mid1:]
    mid2 = len(r2_letters) // 2
    r2_east = r2_letters[:mid2]
    r2_west = r2_letters[mid2:]

    # ECF/WCF/SCF identified by seriesAbbrev
    ecf_letter = wcf_letter = scf_letter = None
    for letter in r3_letters:
        abbrev = series_map[letter]["meta"].get("seriesAbbrev", "")
        if abbrev == "ECF":
            ecf_letter = letter
        elif abbrev == "WCF":
            wcf_letter = letter
    if r4_letters:
        scf_letter = r4_letters[0]

    def conf_for(letter):
        if letter in r1_east or letter in r2_east:
            return "E"
        if letter in r1_west or letter in r2_west:
            return "W"
        if series_map.get(letter, {}).get("meta", {}).get("seriesAbbrev") == "ECF":
            return "E"
        if series_map.get(letter, {}).get("meta", {}).get("seriesAbbrev") == "WCF":
            return "W"
        return ""

    def build_series(letter):
        s = series_map[letter]
        m = s["meta"]
        top = m.get("topSeedTeamAbbrev", "TBD")
        bot = m.get("bottomSeedTeamAbbrev", "TBD")
        tw = m.get("topSeedWins", 0)
        bw = m.get("bottomSeedWins", 0)
        needed = m.get("neededToWin", 4)
        rnd = m.get("round", 0)

        if tw == needed:
            status, winner = "final", top
        elif bw == needed:
            status, winner = "final", bot
        elif tw > 0 or bw > 0:
            status, winner = "in-progress", None
        else:
            status, winner = "upcoming", None

        games_list = [s["games"][k] for k in sorted(s["games"].keys())]
        next_game_date = next((g["date"] for g in games_list if g["state"] == "scheduled"), None)
        conf = conf_for(letter)
        sid = f"R{rnd}{conf}-{letter}-{top}-{bot}"

        return sid, {
            "id": sid,
            "round": rnd,
            "conference": conf,
            "seriesLetter": letter,
            "topSeed": top,
            "bottomSeed": bot,
            "topWins": tw,
            "bottomWins": bw,
            "status": status,
            "winnerAbbr": winner,
            "nextGameDate": next_game_date,
            "games": games_list,
        }

    def placeholder(sid, rnd, conf):
        return sid, {
            "id": sid, "round": rnd, "conference": conf, "seriesLetter": None,
            "topSeed": "TBD", "bottomSeed": "TBD", "topWins": 0, "bottomWins": 0,
            "status": "upcoming", "winnerAbbr": None, "nextGameDate": None, "games": [],
        }

    all_series = {}

    def add_group(letters):
        ids = []
        for letter in letters:
            sid, sdata = build_series(letter)
            all_series[sid] = sdata
            ids.append(sid)
        return ids

    r1e_ids = add_group(r1_east)
    r1w_ids = add_group(r1_west)
    r2e_ids = add_group(r2_east)
    r2w_ids = add_group(r2_west)

    if ecf_letter:
        ecf_id, ecf_data = build_series(ecf_letter)
    else:
        ecf_id, ecf_data = placeholder("R3E-ECF-TBD-TBD", 3, "E")
    if wcf_letter:
        wcf_id, wcf_data = build_series(wcf_letter)
    else:
        wcf_id, wcf_data = placeholder("R3W-WCF-TBD-TBD", 3, "W")
    all_series[ecf_id] = ecf_data
    all_series[wcf_id] = wcf_data

    if scf_letter:
        scf_id, scf_data = build_series(scf_letter)
    else:
        scf_id, scf_data = placeholder("R4-SCF-TBD-TBD", 4, "")
    all_series[scf_id] = scf_data

    bracket = {
        "season": SEASON,
        "updatedAt": str(datetime.date.today()),
        "series": all_series,
        "round1East": r1e_ids,
        "round1West": r1w_ids,
        "round2East": r2e_ids,
        "round2West": r2w_ids,
        "confFinals": [ecf_id, wcf_id],
        "final": scf_id,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(bracket, f, indent=2)

    total_games = sum(len(s["games"]) for s in all_series.values())
    print(f"playoff_bracket.json — {len(all_series)} series, {total_games} games, updated {bracket['updatedAt']}")


if __name__ == "__main__":
    main()
