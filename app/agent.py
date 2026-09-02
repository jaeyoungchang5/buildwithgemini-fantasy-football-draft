# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import uuid
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.tool_context import ToolContext
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

MODEL = "gemini-3.6-flash"

# CRITICAL: Hardcode GCP Project ID, GCS Bucket Name, and Agent Engine Resource Name
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-04-3c7410bcd061"
GCS_BUCKET_NAME = "ff-draft-assets-qwiklabs-gcp-04-3c7410bcd061"
AGENT_ENGINE_RESOURCE_NAME = (
    "projects/246011044791/locations/us-central1/reasoningEngines/5574213340789473280"
)


def get_firestore_client():
    """Initializes Firestore client using the hardcoded project string."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def get_players_from_db(position: str = "ALL", status: str = "available") -> str:
    """Queries player records from the Firestore database.

    Args:
        position: Position filter ('QB', 'RB', 'WR', 'TE', or 'ALL').
        status: Status filter ('available', 'drafted', or 'ALL').

    Returns:
        Formatted summary of player records from Firestore.
    """
    db = get_firestore_client()
    players_ref = db.collection("players")
    docs = players_ref.stream()

    matching_players = []
    pos_upper = position.upper()
    status_lower = status.lower()

    for doc in docs:
        p = doc.to_dict()
        if pos_upper != "ALL" and p.get("position", "").upper() != pos_upper:
            continue
        if status_lower != "all" and p.get("status", "").lower() != status_lower:
            continue
        matching_players.append(p)

    if not matching_players:
        return f"No players found in Firestore for position='{position}' and status='{status}'."

    matching_players.sort(key=lambda x: x.get("adp", 999.0))

    lines = [f"=== Firestore Players Catalog ({position.upper()} | Status: {status}) ==="]
    for p in matching_players:
        lines.append(
            f"• {p['name']} ({p['position']} - {p['team']}) | ADP: {p['adp']} | Bye: Wk {p['bye_week']} | "
            f"OL Rank: #{p['ol_rank']} | Target Share: {int(p['target_share']*100)}% | "
            f"Status: {p['status']} | Notes: {p.get('notes', 'None')}"
        )
    return "\n".join(lines)


def get_league_draft_status(league_id: str = "home-league-2026") -> str:
    """Retrieves current draft board, user roster, and positional needs for a specific league from Firestore.

    Args:
        league_id: Unique ID of the league draft (e.g. 'home-league-2026').

    Returns:
        Summary string of current draft status, user's drafted players, and remaining needs.
    """
    db = get_firestore_client()
    doc_ref = db.collection("league_drafts").document(league_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"No draft record found for league ID '{league_id}' in Firestore."

    data = doc.to_dict()
    league_name = data.get("league_name", league_id)
    current_pick = data.get("current_pick", 1)
    user_roster = data.get("user_roster", [])
    drafted_picks = data.get("drafted_picks", [])
    roster_reqs = data.get("roster_requirements", {})
    roster_filled = data.get("roster_filled", {})

    output = [
        f"=== Firestore Draft Status: {league_name} ({league_id}) ===",
        f"Current Pick: #{current_pick} | User Draft Slot: #{data.get('user_pick_slot', 3)}",
        "",
        "--- 🏈 USER'S CURRENT ROSTER ---",
    ]

    if not user_roster:
        output.append("No players drafted yet.")
    else:
        for p in user_roster:
            output.append(
                f"• Round {p.get('round', 1)}, Pick {p.get('pick', 1)}: {p['name']} ({p['position']} - {p.get('team', '')}) "
                f"[Bye Week: {p.get('bye_week', 'N/A')}]"
            )

    output.extend(["", "--- 📋 ALL DRAFTED PICKS IN LEAGUE ---"])
    if not drafted_picks:
        output.append("No picks recorded yet.")
    else:
        for pick in drafted_picks:
            output.append(
                f"Pick #{pick.get('pick', 1)} (Rd {pick.get('round', 1)}): {pick.get('player', 'Unknown')} "
                f"({pick.get('position', 'N/A')}) -> Drafted by {pick.get('drafted_by', 'Other')}"
            )

    output.extend(["", "--- 🎯 REMAINING POSITIONAL NEEDS ---"])
    for pos, req in roster_reqs.items():
        filled = roster_filled.get(pos, 0)
        needed = max(0, req - filled)
        output.append(f"• {pos}: {filled}/{req} filled (Need {needed} more)")

    return "\n".join(output)


def record_draft_pick(
    player_name: str,
    drafted_by: str = "User",
    round_num: int = 1,
    pick_num: int = 1,
    league_id: str = "home-league-2026",
) -> str:
    """Records a player draft pick into a specific league's Firestore draft state and updates player status.

    Args:
        player_name: Full or partial name of the player drafted.
        drafted_by: Name of the team/user drafting ('User', 'Team 1', etc.).
        round_num: Round number of the pick.
        pick_num: Overall pick number.
        league_id: Unique ID of the league.

    Returns:
        Confirmation string.
    """
    db = get_firestore_client()

    # 1. Look up player in players collection
    players_ref = db.collection("players")
    player_doc = None
    player_data = None
    for doc in players_ref.stream():
        p = doc.to_dict()
        if player_name.lower() in p.get("name", "").lower():
            player_doc = doc.reference
            player_data = p
            break

    if not player_doc:
        return f"Player '{player_name}' not found in Firestore database."

    # Mark player drafted in players collection
    player_doc.update({"status": "drafted", "drafted_by": drafted_by})

    # 2. Update league_drafts document
    draft_ref = db.collection("league_drafts").document(league_id)
    draft_doc = draft_ref.get()

    if not draft_doc.exists:
        return f"League draft record '{league_id}' not found in Firestore."

    draft_data = draft_doc.to_dict()
    drafted_picks = draft_data.get("drafted_picks", [])
    user_roster = draft_data.get("user_roster", [])
    roster_filled = draft_data.get("roster_filled", {})

    new_pick_entry = {
        "pick": pick_num,
        "round": round_num,
        "player": player_data["name"],
        "position": player_data["position"],
        "drafted_by": drafted_by,
    }
    drafted_picks.append(new_pick_entry)

    pos = player_data["position"].upper()
    if drafted_by.lower() == "user":
        user_roster.append(
            {
                "name": player_data["name"],
                "position": pos,
                "team": player_data.get("team", ""),
                "round": round_num,
                "pick": pick_num,
                "bye_week": player_data.get("bye_week", 0),
            }
        )
        roster_filled[pos] = roster_filled.get(pos, 0) + 1

    draft_ref.update(
        {
            "drafted_picks": drafted_picks,
            "user_roster": user_roster,
            "roster_filled": roster_filled,
            "current_pick": pick_num + 1,
        }
    )

    return (
        f"✅ Firestore Pick Recorded for {draft_data.get('league_name', league_id)}!\n"
        f"Pick #{pick_num} (Rd {round_num}): {player_data['name']} ({pos} - {player_data.get('team', '')}) "
        f"drafted by {drafted_by}."
    )


def calculate_vorp(
    player_name: str,
    projected_weekly_pts: float,
    position: str = "RB",
    ppr_modifier: float = 1.0,
    replacement_baseline_pts: float = 11.0,
) -> str:
    """Calculates dynamic Value Over Replacement Player (VORP) for custom league rules and scoring quirks.

    Args:
        player_name: Name of the player.
        projected_weekly_pts: Projected base weekly fantasy points.
        position: Player position ('QB', 'RB', 'WR', 'TE').
        ppr_modifier: Scoring multiplier (e.g. 1.0 for PPR, 0.5 for Half-PPR, 1.5 for TE Premium).
        replacement_baseline_pts: Baseline weekly point threshold for a replacement player at that position.

    Returns:
        Detailed VORP analysis string.
    """
    adj_pts = projected_weekly_pts * ppr_modifier
    vorp = adj_pts - replacement_baseline_pts
    tier = (
        "HIGH PRIORITY (+5.0+ VORP)"
        if vorp >= 5.0
        else "SOLID STARTER (+2.0 to +4.9 VORP)"
        if vorp >= 2.0
        else "FLEX / BENCH VALUE"
    )
    return (
        f"=== VORP Analysis: {player_name} ({position.upper()}) ===\n"
        f"• Projected Base Points: {projected_weekly_pts:.1f} pts/wk\n"
        f"• PPR Scoring Modifier: {ppr_modifier:.2f}x -> Adjusted Projection: {adj_pts:.1f} pts/wk\n"
        f"• Positional Baseline ({position.upper()}): {replacement_baseline_pts:.1f} pts/wk\n"
        f"• Net VORP Score: {vorp:+.1f} pts/wk above replacement\n"
        f"• Value Tier: {tier}"
    )


def add_player_note_in_db(player_name: str, note: str) -> str:
    """Appends or updates custom notes for a player in the Firestore database.

    Args:
        player_name: Name of the player.
        note: Custom note or observation to add.

    Returns:
        Confirmation string.
    """
    db = get_firestore_client()
    players_ref = db.collection("players")
    docs = list(players_ref.stream())

    p_lower = player_name.lower()
    for doc in docs:
        data = doc.to_dict()
        if p_lower in data.get("name", "").lower():
            existing_note = data.get("notes", "")
            updated_note = f"{existing_note} | {note}" if existing_note else note
            doc.reference.update({"notes": updated_note})
            return f"✅ Firestore Note Updated for '{data['name']}': {updated_note}"

    return f"Player '{player_name}' not found in Firestore database."


async def generate_team_logo(
    team_name: str,
    prompt_details: str = "athletic vector mascot, vibrant colors, fantasy football theme",
    tool_context: ToolContext = None,
) -> str:
    """Generates a custom fantasy football team logo using gemini-3.1-flash-lite-image in the global region.

    Saves the generated image as a Playground artifact and uploads it to public Cloud Storage.

    Args:
        team_name: Name of the fantasy football team (e.g., 'Gridiron Lions').
        prompt_details: Additional visual style details or mascot description.
        tool_context: ADK ToolContext provided automatically by the agent runner.

    Returns:
        Public GCS HTTPS URL and artifact confirmation.
    """
    genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
    prompt = f"Fantasy football team logo for '{team_name}'. Style details: {prompt_details}."

    response = genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    part = response.candidates[0].content.parts[0]
    image_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/jpeg"
    ext = "png" if "png" in mime_type else "jpg"
    filename = f"team_logo_{uuid.uuid4().hex[:8]}.{ext}"

    # 1. Save artifact in Playground via ToolContext
    if tool_context:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload same image bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(f"logos/{filename}")
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/logos/{filename}"
    return (
        f"🎨 Team Logo generated successfully for '{team_name}'!\n"
        f"• Public GCS Image URL: {public_url}\n"
        f"• Playground Artifact Saved: '{filename}'"
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: After each turn, send session events to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an expert Fantasy Football Draft Assistant connected to a live Firestore database "
        "tracking players, custom league draft boards, user rosters, and positional needs."
    ),
    workflow_description=(
        "Analyze the user's request, perform necessary tool calls or calculations, and return structured A2UI UI when appropriate."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

domain_context = (
    "\n\nDATABASE & DRAFT TRACKING TOOLS:\n"
    "1. Use `get_players_from_db` to fetch live player rankings, ADP, OL rank, target share, and availability.\n"
    "2. Use `record_draft_pick` when a pick is made by the user or another team to update the league's draft board.\n"
    "3. Use `calculate_vorp` to calculate dynamic Value Over Replacement Player (VORP) adjusted for PPR and positional baselines.\n"
    "4. Use `get_league_draft_status` to view the full live draft status for a specific league (e.g., 'home-league-2026').\n"
    "5. Use `generate_team_logo` to generate a custom team logo/avatar image using gemini-3.1-flash-lite-image in the global region.\n"
    "6. Use `add_player_note_in_db` to record observations in Firestore.\n\n"
    "CODE EXECUTION SANDBOX:\n"
    "You have access to an Agent Platform Python Sandbox (`AgentEngineSandboxCodeExecutor`). "
    "You can write Python code in ```python blocks to execute complex calculations, VORP statistical math, or draft simulations safely in the sandbox.\n\n"
    "CRITICAL MEMORY INSTRUCTIONS:\n"
    "You use Vertex AI Memory Bank to remember user preferences across sessions:\n"
    "1. PLAYERS TO AVOID & WHY: Actively remember players the user avoids and do not recommend them.\n"
    "2. PLAYERS TO PRIORITIZE & WHY: Actively remember favorite players.\n"
    "3. STRATEGIES & RULES: Remember strategy preferences (Hero RB) and league settings.\n\n"
    "Always synthesize live Firestore draft state (user roster, drafted players, remaining needs) "
    "with remembered user preferences to recommend optimal next picks!"
)

full_instruction = a2ui_instruction + domain_context

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
    ),
    instruction=full_instruction,
    tools=[
        PreloadMemoryTool(),
        get_players_from_db,
        record_draft_pick,
        calculate_vorp,
        get_league_draft_status,
        generate_team_logo,
        add_player_note_in_db,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
