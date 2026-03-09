"""
Goals Against by Position Scraper
Pulls goal-scoring game data from the NHL Stats API and aggregates
goals against by defending team and scorer position.

Data source: api.nhle.com (NHL's public stats API)
Output: data/goals_against_by_position.json
"""

import requests
import json
import os
import time
from datetime import datetime, timedelta
from collections import defaultdict

API_BASE = "https://api.nhle.com/stats/rest/en/skater/summary"
SEASON_ID = 20252026
GAME_TYPE = 2  # Regular season
PAGE_SIZE = 500
DELAY_BETWEEN_REQUESTS = 2  # seconds, be respectful to NHL API

# All 32 NHL teams
NHL_TEAMS = [
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL",
    "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD",
    "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
    "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH"
]


def fetch_goal_rows():
    """
    Fetch all skater game rows where goals >= 1 for the current season.
    Uses pagination to pull all rows in chunks of PAGE_SIZE.
    """
    all_rows = []
    start = 0

    # First request to get total count
    params = build_params(start)
    print(f"Fetching initial page to get total count...")
    resp = requests.get(API_BASE, params=params)
    resp.raise_for_status()
    data = resp.json()
    total = data.get("total", 0)
    all_rows.extend(data.get("data", []))
    print(f"Total goal-scoring game rows: {total}")

    # Paginate through remaining rows
    start += PAGE_SIZE
    while start < total:
        time.sleep(DELAY_BETWEEN_REQUESTS)
        params = build_params(start)
        print(f"Fetching rows {start} - {start + PAGE_SIZE}...")
        resp = requests.get(API_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", [])
        if not rows:
            break
        all_rows.extend(rows)
        start += PAGE_SIZE

    print(f"Fetched {len(all_rows)} total rows")
    return all_rows


def build_params(start):
    """Build query parameters for the NHL Stats API."""
    return {
        "isAggregate": "false",
        "isGame": "true",
        "sort": '[{"property":"goals","direction":"DESC"}]',
        "start": start,
        "limit": PAGE_SIZE,
        "factCayenneExp": "goals>=1",
        "cayenneExp": f"seasonId={SEASON_ID} and gameTypeId={GAME_TYPE}"
    }


def get_team_game_counts(all_rows):
    """
    We also need total games played per team to calculate per-game averages.
    Fetch all game rows (not just goals) to count unique games per team.
    This uses the schedule approach instead — much fewer API calls.
    """
    # We'll calculate games played from the schedule endpoint instead
    # For now, we can derive it from the data we have or fetch separately
    pass


def aggregate_goals_against(rows):
    """
    Aggregate goal data into goals against by position per team.
    
    For each row: opponentTeamAbbrev gave up `goals` to positionCode.
    """
    # Structure: team -> split -> position -> count
    # Splits: ytd, home, away
    # We also track per-game-date for L10 calculation
    team_data = {}

    # Initialize all teams
    for team in NHL_TEAMS:
        team_data[team] = {
            "ytd": defaultdict(int),
            "home": defaultdict(int),   # goals against when team is HOME
            "away": defaultdict(int),   # goals against when team is AWAY
            "game_dates": defaultdict(set),  # track unique game dates per team
            "games_by_date": defaultdict(lambda: defaultdict(int))  # date -> pos -> goals
        }

    for row in rows:
        opponent = row.get("opponentTeamAbbrev")
        pos = row.get("positionCode")
        goals = row.get("goals", 0)
        home_road = row.get("homeRoad")  # H or R — this is the SCORER's home/road
        game_date = row.get("gameDate")

        if not opponent or not pos or not goals:
            continue

        # Normalize position: L and R -> LW and RW for clarity, or keep as-is
        # NHL API uses C, L, R, D
        pos_label = normalize_position(pos)

        # YTD totals
        team_data[opponent]["ytd"][pos_label] += goals

        # Home/Away splits (from defending team's perspective)
        # If scorer is "H" (home), then the defending team is AWAY
        # If scorer is "R" (road), then the defending team is HOME
        if home_road == "H":
            team_data[opponent]["away"][pos_label] += goals
        elif home_road == "R":
            team_data[opponent]["home"][pos_label] += goals

        # Track by game date for L10 calculation
        if game_date:
            team_data[opponent]["game_dates"][game_date].add(row.get("gameId"))
            team_data[opponent]["games_by_date"][game_date][pos_label] += goals

    return team_data


def normalize_position(pos):
    """Normalize position codes to readable labels."""
    mapping = {
        "C": "C",
        "L": "LW",
        "R": "RW",
        "D": "D"
    }
    return mapping.get(pos, pos)


def calculate_l10(team_data):
    """
    Calculate last 10 games goals against by position for each team.
    Uses the game_dates tracking to find the 10 most recent game dates.
    """
    l10_data = {}

    for team in NHL_TEAMS:
        data = team_data[team]
        # Get all unique game dates where this team was scored against, sorted desc
        all_dates = sorted(data["game_dates"].keys(), reverse=True)

        # We need the last 10 unique GAME dates for this team
        # Note: a team might not have been scored against in every game,
        # but we want the last 10 games regardless. For simplicity,
        # we use dates where goals were scored against them.
        last_10_dates = all_dates[:10]

        l10 = defaultdict(int)
        for date in last_10_dates:
            for pos, goals in data["games_by_date"][date].items():
                l10[pos] += goals

        l10_data[team] = dict(l10)

    return l10_data


def build_output(team_data, l10_data):
    """Build the final JSON output structure."""
    positions = ["C", "LW", "RW", "D"]

    output = {
        "lastUpdated": datetime.utcnow().strftime("%Y-%m-%d"),
        "season": "2025-26",
        "positions": positions,
        "teams": {}
    }

    for team in sorted(NHL_TEAMS):
        data = team_data[team]
        output["teams"][team] = {
            "ytd": {pos: data["ytd"].get(pos, 0) for pos in positions},
            "l10": {pos: l10_data[team].get(pos, 0) for pos in positions},
            "home": {pos: data["home"].get(pos, 0) for pos in positions},
            "away": {pos: data["away"].get(pos, 0) for pos in positions},
            "ytdTotal": sum(data["ytd"].get(pos, 0) for pos in positions),
            "l10Total": sum(l10_data[team].get(pos, 0) for pos in positions),
            "homeTotal": sum(data["home"].get(pos, 0) for pos in positions),
            "awayTotal": sum(data["away"].get(pos, 0) for pos in positions)
        }

    return output


def main():
    print("=" * 60)
    print("Goals Against by Position Scraper")
    print(f"Season: {SEASON_ID}")
    print("=" * 60)

    # Step 1: Fetch all goal-scoring game rows
    rows = fetch_goal_rows()

    # Step 2: Aggregate goals against by position
    print("\nAggregating goals against by position...")
    team_data = aggregate_goals_against(rows)

    # Step 3: Calculate L10 splits
    print("Calculating last 10 games splits...")
    l10_data = calculate_l10(team_data)

    # Step 4: Build and save output
    output = build_output(team_data, l10_data)

    # Ensure output directory exists
    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "goals_against_by_position.json")

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nOutput saved to {output_path}")
    print(f"Total API calls made: ~{(len(rows) // PAGE_SIZE) + 1}")

    # Print a quick summary
    print("\n--- Quick Summary ---")
    for team in sorted(NHL_TEAMS)[:5]:
        t = output["teams"][team]
        print(f"{team}: YTD total GA = {t['ytdTotal']} "
              f"(C:{t['ytd']['C']} LW:{t['ytd']['LW']} RW:{t['ytd']['RW']} D:{t['ytd']['D']})")
    print("... (showing first 5 teams)")


if __name__ == "__main__":
    main()
