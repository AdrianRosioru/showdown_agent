# node pokemon-showdown start --no-security
import asyncio
import importlib
import os
import sys
from typing import List, Dict

import poke_env as pke
from poke_env import AccountConfiguration
from poke_env.player.player import Player
from tabulate import tabulate

# ---------------------------
# Config: battles per pairing
# ---------------------------
TOTAL_BATTLES_PER_PAIR = 100  # total across both directions (≈50 each way)
# pke.cross_evaluate runs "n_challenges" per *ordered* pair (A->B and B->A),
# so use half to get ~100 total per unordered pair:
N_CHALLENGES_PER_DIRECTION = max(1, TOTAL_BATTLES_PER_PAIR // 2)


def gather_players() -> List[Player]:
    player_folders = os.path.join(os.path.dirname(__file__), "players")
    players: List[Player] = []

    replay_dir = os.path.join(os.path.dirname(__file__), "replays")
    os.makedirs(replay_dir, exist_ok=True)

    for module_name in os.listdir(player_folders):
        if not module_name.endswith(".py"):
            continue

        module_path = f"{player_folders}/{module_name}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if hasattr(module, "CustomAgent"):
            player_name = module_name[:-3]
            agent_class = getattr(module, "CustomAgent")

            agent_replay_dir = os.path.join(replay_dir, player_name)
            os.makedirs(agent_replay_dir, exist_ok=True)

            account_config = AccountConfiguration(player_name, None)
            player = agent_class(
                account_configuration=account_config,
                battle_format="gen9ubers",
            )
            # save replays under per-player dir (poke-env uses this flag)
            player._save_replays = agent_replay_dir

            players.append(player)

    return players


async def cross_evaluate(agents: List[Player]):
    # Run N_CHALLENGES_PER_DIRECTION per ordered pair (A->B and B->A)
    return await pke.cross_evaluate(agents, n_challenges=N_CHALLENGES_PER_DIRECTION)


def compute_winrates(results: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    results[p1][p2] = winrate of p1 vs p2 for the p1->p2 challenges (size = N_CHALLENGES_PER_DIRECTION).
    We combine both directions to get ~TOTAL_BATTLES_PER_PAIR per unordered pair.
    """
    players = list(results.keys())
    wins = {p: 0.0 for p in players}
    games = {p: 0 for p in players}
    n = N_CHALLENGES_PER_DIRECTION

    for i, a in enumerate(players):
        for j, b in enumerate(players):
            if j <= i:
                continue
            s_ab = results.get(a, {}).get(b, 0.0) or 0.0  # A's winrate vs B (A->B)
            s_ba = results.get(b, {}).get(a, 0.0) or 0.0  # B's winrate vs A (B->A)
            # Total wins per player over 2n games in this pair
            wins[a] += s_ab * n + (1.0 - s_ba) * n
            wins[b] += s_ba * n + (1.0 - s_ab) * n
            games[a] += 2 * n
            games[b] += 2 * n

    # Avoid div-by-zero for edge cases (e.g., only 1 player)
    return {p: (wins[p] / games[p] if games[p] > 0 else 0.0) for p in players}


def print_winrate_table(winrates: Dict[str, float]):
    rows = sorted(((p, wr) for p, wr in winrates.items()), key=lambda x: x[1], reverse=True)
    print("\nFinal win rates ({} battles per pairing):".format(TOTAL_BATTLES_PER_PAIR))
    print(tabulate([(p, f"{wr:.2%}") for p, wr in rows], headers=["Player", "Win rate"]))


def main():
    players = gather_players()
    if len(players) < 2:
        print("Need at least 2 players in ./players to battle.")
        return

    print(f"Loaded {len(players)} players. Running cross-evaluation...")
    results = asyncio.run(cross_evaluate(players))

    # Optional: dump raw matrix
    header = ["-"] + [p for p in results.keys()]
    matrix = []
    for p1, row in results.items():
        matrix.append([p1] + [row.get(p2, None) if p2 in row else None for p2 in results.keys()])
    print("\nPer-direction winrates (initiator rows vs columns; each ≈ {} games):".format(N_CHALLENGES_PER_DIRECTION))
    print(tabulate(matrix, headers=header, floatfmt=".2f"))

    winrates = compute_winrates(results)
    print_winrate_table(winrates)


if __name__ == "__main__":
    main()
