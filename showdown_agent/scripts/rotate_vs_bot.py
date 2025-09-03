# scripts/rotate_vs_bot.py
# Requires a local Showdown server running:
#   node pokemon-showdown start --no-security

import argparse
import asyncio
import importlib.util
import os
import random
import sys
import types
from typing import Tuple

from poke_env import AccountConfiguration
from poke_env.player.player import Player


# ---------- Helpers ----------
def here(*parts):
    return os.path.join(os.path.dirname(__file__), *parts)

def load_module(path: str):
    path = os.path.abspath(path)
    name = os.path.splitext(os.path.basename(path))[0] + f"_{random.randrange(10**5)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module at {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def team_order_for_lead(pos: int) -> str:
    # Build a 6-digit order string putting (pos+1) first, keeping others in original order.
    base = [1, 2, 3, 4, 5, 6]
    lead = base.pop(pos)
    order = [lead] + base
    return "".join(str(x) for x in order)

def patch_teampreview(agent: Player, order_str: str):
    # Force /team order_str for the entire battle
    def _tp(self, battle):
        return f"/team {order_str}"
    agent.teampreview = types.MethodType(_tp, agent)

def short_user(prefix: str) -> str:
    # 18 chars max; keep it short and unique
    return f"{prefix}{random.randrange(10000,99999)}"[:18]


# ---------- Core duel ----------
async def duel_block(player: Player, bot: Player, n_battles: int) -> Tuple[int, int]:
    """Play n_battles and return (player_wins, bot_wins)."""
    p_before = player.n_won_battles
    b_before = bot.n_won_battles
    await player.battle_against(bot, n_battles=n_battles)
    p_wins = player.n_won_battles - p_before
    b_wins = bot.n_won_battles - b_before
    return p_wins, b_wins

async def stop_safely(agent: Player):
    try:
        await agent.stop_listening()
    except Exception:
        pass


# ---------- Runner ----------
async def run_all(player_file: str, bot_name: str, runs: int, battle_format: str):
    # Resolve paths relative to this script
    players_dir = here("players")
    bots_dir    = here("bots")
    teams_dir   = os.path.join(bots_dir, "teams")

    # Load your player module (expects class CustomAgent using its own internal `team`)
    player_mod  = load_module(os.path.join(players_dir, os.path.basename(player_file)))

    # Resolve bot module path by name
    bot_file_map = {
        "simple":     "simple.py",
        "max_damage": "max_damage.py",
        "random":     "random.py",
    }
    if bot_name not in bot_file_map:
        raise ValueError(f"--bot must be one of {list(bot_file_map)}")
    bot_mod  = load_module(os.path.join(bots_dir, bot_file_map[bot_name]))

    # Always use bots/teams/uber.txt
    bot_team_raw = read_text(os.path.join(teams_dir, "uber.txt"))

    print("\n=== Rotate-vs-Bot ===")
    print(f"Player file : {os.path.join('players', os.path.basename(player_file))}")
    print(f"Bot module  : {os.path.join('bots', bot_file_map[bot_name])}")
    print(f"Bot team    : {os.path.join('bots', 'teams', 'uber.txt')}")
    print(f"Format      : {battle_format}")
    print(f"Runs/lead   : {runs}")
    print(f"Positions   : {list(range(6))}\n")

    total_wins = 0
    total_games = 0

    for pos in range(6):
        if pos != 4:
            continue
        order = team_order_for_lead(pos)
        print(f"→ Lead position {pos} (sending /team {order})")

        # Fresh instances per block to avoid lingering state
        PClass = getattr(player_mod, "CustomAgent")
        BClass = getattr(bot_mod, "CustomAgent")

        player = PClass(
            account_configuration=AccountConfiguration(short_user("p"), None),
            battle_format=battle_format,
            max_concurrent_battles=1,
        )
        # Force team order with teampreview
        patch_teampreview(player, order)

        bot = BClass(
            team=bot_team_raw,
            account_configuration=AccountConfiguration(short_user("b"), None),
            battle_format=battle_format,
            max_concurrent_battles=1,
        )

        try:
            p_wins, b_wins = await duel_block(player, bot, runs)
            total_wins += p_wins
            total_games += (p_wins + b_wins)
            print(f"   Result: {p_wins}-{b_wins} (win rate {p_wins / max(1, (p_wins+b_wins)):.2f})")
        finally:
            await stop_safely(player)
            await stop_safely(bot)

    avg_wr = total_wins / max(1, total_games)
    print("\n=== Summary ===")
    print(f"Total: {total_wins}-{total_games - total_wins} over {total_games} games")
    print(f"Average win rate across 6 leads: {avg_wr:.3f}")


# ---------- CLI ----------
def parse_args():
    ap = argparse.ArgumentParser(description="Rotate leads and battle a simple bot in gen9ubers.")
    ap.add_argument("--player", required=True, help="Path under scripts/players (e.g., players/dhal592_v7.py)")
    ap.add_argument("--bot",    required=True, choices=["simple", "max_damage", "random"], help="Bot to face")
    ap.add_argument("--runs",   type=int, default=5, help="Battles per lead position (default 5)")
    ap.add_argument("--format", default="gen9ubers", help="Showdown format (default gen9ubers)")
    return ap.parse_args()

def main():
    args = parse_args()
    asyncio.run(run_all(args.player, args.bot, args.runs, args.format))

if __name__ == "__main__":
    main()
