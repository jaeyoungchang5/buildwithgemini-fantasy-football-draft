# Copyright 2026 Google LLC
# Seed script for Fantasy Football Draft Assistant Firestore Backend

from google.cloud import firestore

# CRITICAL: Hardcode GCP Project ID as a string to avoid project number issues on Agent Platform
PROJECT_ID = "qwiklabs-gcp-04-3c7410bcd061"

INITIAL_PLAYERS = [
    {
        "id": "ceedee-lamb",
        "name": "CeeDee Lamb",
        "position": "WR",
        "team": "DAL",
        "bye_week": 7,
        "adp": 1.5,
        "ol_rank": 7,
        "target_share": 0.31,
        "upside_tier": "Elite Alpha",
        "risk_level": "Very Low",
        "status": "drafted",
        "drafted_by": "user",
        "notes": "Uncontested #1 option in DAL offense. PPR monster.",
    },
    {
        "id": "christian-mccaffrey",
        "name": "Christian McCaffrey",
        "position": "RB",
        "team": "SF",
        "bye_week": 9,
        "adp": 2.1,
        "ol_rank": 3,
        "target_share": 0.18,
        "upside_tier": "Overall #1 RB",
        "risk_level": "Medium (Injury Concerns)",
        "status": "drafted",
        "drafted_by": "Team 1",
        "notes": "Elite efficiency behind top 3 OL. Monitor durability.",
    },
    {
        "id": "tyreek-hill",
        "name": "Tyreek Hill",
        "position": "WR",
        "team": "MIA",
        "bye_week": 6,
        "adp": 3.2,
        "ol_rank": 18,
        "target_share": 0.29,
        "upside_tier": "Game-Breaker",
        "risk_level": "Low",
        "status": "drafted",
        "drafted_by": "Team 2",
        "notes": "Explosive speed, high weekly ceiling.",
    },
    {
        "id": "breece-hall",
        "name": "Breece Hall",
        "position": "RB",
        "team": "NYJ",
        "bye_week": 12,
        "adp": 4.5,
        "ol_rank": 10,
        "target_share": 0.15,
        "upside_tier": "Top 3 RB",
        "risk_level": "Low",
        "status": "available",
        "drafted_by": "",
        "notes": "Dual-threat receiving RB with improved OL.",
    },
    {
        "id": "bijan-robinson",
        "name": "Bijan Robinson",
        "position": "RB",
        "team": "ATL",
        "bye_week": 12,
        "adp": 5.8,
        "ol_rank": 4,
        "target_share": 0.14,
        "upside_tier": "Workhorse",
        "risk_level": "Low",
        "status": "available",
        "drafted_by": "",
        "notes": "Top 5 OL, projected heavy volume.",
    },
    {
        "id": "saquon-barkley",
        "name": "Saquon Barkley",
        "position": "RB",
        "team": "PHI",
        "bye_week": 5,
        "adp": 8.2,
        "ol_rank": 1,
        "target_share": 0.12,
        "upside_tier": "TD Ceiling",
        "risk_level": "Low",
        "status": "available",
        "drafted_by": "",
        "notes": "Best OL in football, high TD potential.",
    },
    {
        "id": "josh-allen",
        "name": "Josh Allen",
        "position": "QB",
        "team": "BUF",
        "bye_week": 12,
        "adp": 20.5,
        "ol_rank": 8,
        "target_share": 0.0,
        "upside_tier": "Overall #1 QB",
        "risk_level": "Low",
        "status": "available",
        "drafted_by": "",
        "notes": "Rushing touchdowns baseline + passing floor.",
    },
    {
        "id": "travis-kelce",
        "name": "Travis Kelce",
        "position": "TE",
        "team": "KC",
        "bye_week": 6,
        "adp": 24.0,
        "ol_rank": 5,
        "target_share": 0.22,
        "upside_tier": "Tier 1 TE",
        "risk_level": "Low",
        "status": "available",
        "drafted_by": "",
        "notes": "Top red-zone target for Patrick Mahomes.",
    },
]

INITIAL_LEAGUE_DRAFT = {
    "league_id": "home-league-2026",
    "league_name": "12-Team PPR Home League",
    "total_teams": 12,
    "user_pick_slot": 3,
    "current_pick": 4,
    "user_roster": [
        {
            "name": "CeeDee Lamb",
            "position": "WR",
            "team": "DAL",
            "round": 1,
            "pick": 3,
            "bye_week": 7,
        }
    ],
    "drafted_picks": [
        {
            "pick": 1,
            "round": 1,
            "player": "Christian McCaffrey",
            "position": "RB",
            "drafted_by": "Team 1",
        },
        {
            "pick": 2,
            "round": 1,
            "player": "Tyreek Hill",
            "position": "WR",
            "drafted_by": "Team 2",
        },
        {
            "pick": 3,
            "round": 1,
            "player": "CeeDee Lamb",
            "position": "WR",
            "drafted_by": "User",
        },
    ],
    "roster_requirements": {
        "QB": 1,
        "RB": 2,
        "WR": 2,
        "TE": 1,
        "FLEX": 1,
        "K": 1,
        "DST": 1,
    },
    "roster_filled": {
        "QB": 0,
        "RB": 0,
        "WR": 1,
        "TE": 0,
        "FLEX": 0,
        "K": 0,
        "DST": 0,
    },
}


def seed_firestore():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)

    # Seed players collection
    players_ref = db.collection("players")
    for player in INITIAL_PLAYERS:
        doc_ref = players_ref.document(player["id"])
        doc_ref.set(player)
        print(f"Seeded player: {player['name']} ({player['position']} - {player['team']})")

    # Seed league_drafts collection
    drafts_ref = db.collection("league_drafts")
    drafts_ref.document(INITIAL_LEAGUE_DRAFT["league_id"]).set(INITIAL_LEAGUE_DRAFT)
    print(f"Seeded league draft state: {INITIAL_LEAGUE_DRAFT['league_name']} ({INITIAL_LEAGUE_DRAFT['league_id']})")

    print("✅ Firestore seed complete!")


if __name__ == "__main__":
    seed_firestore()
