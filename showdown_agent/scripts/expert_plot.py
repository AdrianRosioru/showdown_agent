# node pokemon-showdown start --no-security

import asyncio
import importlib
import os
import sys
import threading
import queue
from typing import Dict, List, Tuple
from collections import defaultdict
import html
import time

import poke_env as pke
from poke_env import AccountConfiguration
from poke_env.player.player import Player
from tabulate import tabulate

# GUI: standard library only
import tkinter as tk


# ======================
# Config
# ======================
N_TOURNAMENT_RUNS = 100            # how many times to repeat the full evaluation
BATTLE_FORMAT = "gen9ubers"        # tweak in one place
BASE_DIR = os.path.dirname(__file__)


def rank_players_by_victories(results_dict, top_k=10):
    victory_scores = {}

    for player, opponents in results_dict.items():
        victories = [
            1 if (score is not None and score > 0.5) else 0
            for opp, score in opponents.items()
            if opp != player
        ]
        if victories:
            victory_scores[player] = sum(victories) / len(victories)
        else:
            victory_scores[player] = 0.0

    # Sort by descending victory rate
    sorted_players = sorted(victory_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_players[:top_k]


def gather_players() -> List[Player]:
    player_folders = os.path.join(BASE_DIR, "players")
    players = []

    replay_dir = os.path.join(BASE_DIR, "replays")
    if not os.path.exists(replay_dir):
        os.makedirs(replay_dir)

    for module_name in os.listdir(player_folders):
        if module_name.endswith(".py"):
            module_path = os.path.join(player_folders, module_name)

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)

            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "CustomAgent"):
                player_name = f"{module_name[:-3]}"
                agent_class = getattr(module, "CustomAgent")

                # per-agent replay dir (same as your original style)
                agent_replay_dir = os.path.join(replay_dir, f"{player_name}")
                if not os.path.exists(agent_replay_dir):
                    os.makedirs(agent_replay_dir)

                account_config = AccountConfiguration(player_name, None)
                player = agent_class(
                    account_configuration=account_config,
                    battle_format=BATTLE_FORMAT,
                )
                # keep saving replays if your agents do that internally
                player._save_replays = agent_replay_dir
                players.append(player)
    return players


def gather_bots() -> List[Player]:
    bot_folders = os.path.join(BASE_DIR, "bots")
    bot_teams_folders = os.path.join(bot_folders, "teams")

    generic_bots: List[Player] = []
    bot_teams: Dict[str, str] = {}

    for team_file in os.listdir(bot_teams_folders):
        if team_file.endswith(".txt"):
            with open(
                os.path.join(bot_teams_folders, team_file), "r", encoding="utf-8"
            ) as file:
                bot_teams[team_file[:-4]] = file.read()

    for module_name in os.listdir(bot_folders):
        if module_name.endswith(".py"):
            module_path = os.path.join(bot_folders, module_name)

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)

            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for team_name, team in bot_teams.items():
                if hasattr(module, "CustomAgent"):
                    agent_class = getattr(module, "CustomAgent")
                    config_name = f"{module_name[:-3]}-{team_name}"
                    account_config = AccountConfiguration(config_name, None)
                    generic_bots.append(
                        agent_class(
                            team=team,
                            account_configuration=account_config,
                            battle_format=BATTLE_FORMAT,
                        )
                    )
    return generic_bots


async def cross_evaluate(agents: List[Player]):
    return await pke.cross_evaluate(agents, n_challenges=3)


def evaluate_against_bots(agents: List[Player]) -> List[Tuple[str, float]]:
    """
    Cross-evaluates the given agents and returns a ranked list of (agent_name, winrate).
    The first element is the best (highest winrate).
    """
    print(f"{len(agents)} agents competing in this run")
    print("Running Cross Evaluations...")
    cross_evaluation_results = asyncio.run(cross_evaluate(agents))
    print("Evaluations Complete")

    table = [["-"] + [p.username for p in agents]]
    for p_1, results in cross_evaluation_results.items():
        table.append([p_1] + [cross_evaluation_results[p_1][p_2] for p_2 in results])

    headers = table[0]
    data = table[1:]
    print(tabulate(data, headers=headers, floatfmt=".2f"))

    print("Rankings")
    top_players = rank_players_by_victories(
        cross_evaluation_results, top_k=len(cross_evaluation_results)
    )
    return top_players


def assign_marks(rank: int) -> float:
    modifier = 1.0 if rank > 10 else 0.5
    top_marks = 10.0 if rank < 10 else 5.0
    mod_rank = rank % 10
    marks = top_marks - (mod_rank - 1) * modifier
    return 0.0 if marks < 0 else marks


# ---------------------- Tkinter live plot (no extra deps) ----------------------
class LivePlot:
    """A tiny line-plotter on a Tkinter Canvas that redraws cumulative averages."""

    def __init__(self, title="Cumulative Average Player Score Over Time"):
        self.root = tk.Tk()
        self.root.title(title)

        # Canvas + controls
        self.canvas_w, self.canvas_h = 1100, 700
        self.canvas = tk.Canvas(self.root, width=self.canvas_w, height=self.canvas_h, bg="white")
        self.canvas.pack(fill="both", expand=True)

        controls = tk.Frame(self.root)
        controls.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(controls, textvariable=self.status_var).pack(side="left", padx=8)

        self.stop_after_current = False
        tk.Button(controls, text="Stop after current run", command=self._request_stop).pack(side="right", padx=8)

        # Plot area (margins)
        self.lpad, self.rpad, self.tpad, self.bpad = 80, 260, 60, 60
        self.x_ticks_target = 8

        # communication queue for worker thread
        self.q: "queue.Queue[dict]" = queue.Queue()

        # color palette (cycles)
        self.colors = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
            "#4e79a7", "#f28e2c", "#59a14f", "#e15759", "#76b7b2",
            "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab",
        ]

        # latest data
        self.cumavg: Dict[str, List[float]] = {}
        self.x_max = 1

        # poll for updates
        self.root.after(100, self._poll_queue)

    def _request_stop(self):
        self.stop_after_current = True
        self.status_var.set("Will stop after the current run finishes...")

    def push_update(self, run_idx: int, marks_history: Dict[str, List[float]], msg: str = ""):
        """Called from worker thread: enqueue data to redraw."""
        self.q.put({"run": run_idx, "marks": marks_history, "msg": msg})

    def _poll_queue(self):
        """Runs in GUI thread: apply updates and redraw."""
        try:
            while True:
                item = self.q.get_nowait()
                run_idx = item["run"]
                marks_history = item["marks"]
                msg = item.get("msg", "")

                # compute cumulative averages
                self.cumavg = {}
                self.x_max = 1
                for player, marks in marks_history.items():
                    total = 0.0
                    arr = []
                    for i, m in enumerate(marks, 1):
                        total += m
                        arr.append(total / i)
                    self.cumavg[player] = arr
                    print(arr)
                    self.x_max = max(self.x_max, len(arr))

                if msg:
                    self.status_var.set(msg)
                else:
                    self.status_var.set(f"Run {run_idx} complete.")

                self._redraw()
        except queue.Empty:
            pass

        self.root.after(100, self._poll_queue)

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        W, H = self.canvas_w, self.canvas_h
        LP, RP, TP, BP = self.lpad, self.rpad, self.tpad, self.bpad
        plot_w = W - LP - RP
        plot_h = H - TP - BP

        # axes bounds
        x_min, x_max = 1, max(1, self.x_max)
        y_min, y_max = 0.0, 10.0

        def x_to_px(x):
            return LP + (x - x_min) * (plot_w / max(1e-9, (x_max - x_min)))

        def y_to_px(y):
            return TP + (y_max - y) * (plot_h / max(1e-9, (y_max - y_min)))

        # title
        c.create_text(LP, TP - 25, text="Cumulative Average Player Score Over Time", anchor="w", font=("TkDefaultFont", 14, "bold"))

        # axes
        c.create_line(LP, TP, LP, H - BP, fill="#333", width=2)              # Y
        c.create_line(LP, H - BP, W - RP, H - BP, fill="#333", width=2)      # X

        # x ticks/grid
        steps = min(self.x_ticks_target, x_max - x_min + 1)
        steps = max(1, steps)
        for i in range(steps + 1):
            xv = x_min + i * (x_max - x_min) / steps
            xp = x_to_px(xv)
            c.create_line(xp, TP, xp, H - BP, fill="#eee")
            c.create_text(xp, H - BP + 16, text=str(int(round(xv))), anchor="n", font=("TkDefaultFont", 9))

        # y ticks every 2
        for yv in range(int(y_min), int(y_max) + 1, 2):
            yp = y_to_px(yv)
            c.create_line(LP, yp, W - RP, yp, fill="#f3f3f3")
            c.create_text(LP - 10, yp, text=str(yv), anchor="e", font=("TkDefaultFont", 9))

        # axis labels
        c.create_text((LP + (W - RP)) / 2, H - 10, text="Tournament Run #", anchor="s", font=("TkDefaultFont", 10))
        c.create_text(20, (TP + (H - BP)) / 2, text="Cumulative Average Mark", anchor="w", angle=90, font=("TkDefaultFont", 10))

        # series
        legend_x = W - RP + 20
        legend_y = TP + 10
        legend_step = 18

        for idx, (player, series) in enumerate(sorted(self.cumavg.items())):
            color = self.colors[idx % len(self.colors)]

            # polyline
            pts = []
            for i, v in enumerate(series, 1):
                pts.append((x_to_px(i), y_to_px(v)))

            if len(pts) == 1:
                x, y = pts[0]
                c.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline=color)
            else:
                # draw connected lines
                for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
                    c.create_line(x1, y1, x2, y2, fill=color, width=2)

            # legend
            ly = legend_y + idx * legend_step
            c.create_line(legend_x, ly, legend_x + 20, ly, fill=color, width=3)
            c.create_text(legend_x + 26, ly, text=player, anchor="w", font=("TkDefaultFont", 9))


# ---------------------- Worker thread (runs the tournaments) ----------------------
def run_tournaments(gui: LivePlot, stop_event: threading.Event):
    # Collect agents once
    generic_bots = gather_bots()
    players = gather_players()
    player_names = [p.username for p in players]

    print(f"Players detected: {player_names}")
    print(f"Generic bots detected: {[b.username for b in generic_bots]}")

    # History of marks for plotting
    marks_history: Dict[str, List[float]] = defaultdict(list)

    for run_idx in range(1, N_TOURNAMENT_RUNS + 1):
        if stop_event.is_set():
            gui.push_update(run_idx - 1, marks_history, "Stopped before starting next run.")
            break

        print("=" * 80)
        print(f"Starting tournament run {run_idx}/{N_TOURNAMENT_RUNS}")
        print("=" * 80)

        # Evaluate each *player* vs all bots
        for player in players:
            agents: List[Player] = [player] + generic_bots
            print(f"\nEvaluating player: {player.username} (run {run_idx})")

            agent_rankings = evaluate_against_bots(agents)

            # Rank. Player - Win Rate - Mark
            print("Rank. Player - Win Rate - Mark")
            player_rank = len(agents) + 1
            player_mark = 0.0

            for rank, (agent_name, winrate) in enumerate(agent_rankings, 1):
                mark = assign_marks(rank)
                print(f"{rank}. {agent_name} - {winrate:.2f} - {mark:.2f}")
                if agent_name == player.username:
                    player_rank = rank
                    player_mark = mark

            print(f"{player.username} ranked #{player_rank} with a mark of {player_mark:.2f}\n")

            # Update history + GUI (thread-safe via queue)
            marks_history[player.username].append(player_mark)
            gui.push_update(run_idx, marks_history, f"Run {run_idx}: updated {player.username}")

        # If user requested stop, break after finishing this run
        if gui.stop_after_current:
            gui.push_update(run_idx, marks_history, "Stopped after current run.")
            break

    print("Worker finished.")


def main():
    # Build GUI
    gui = LivePlot()
    stop_event = threading.Event()

    # Start worker in a separate thread so the GUI remains responsive
    worker = threading.Thread(target=run_tournaments, args=(gui, stop_event), daemon=True)
    worker.start()

    # Close handling
    def on_close():
        gui.status_var.set("Shutting down...")
        stop_event.set()
        # give worker a moment to exit gracefully
        gui.root.after(200, gui.root.destroy)

    gui.root.protocol("WM_DELETE_WINDOW", on_close)

    # Enter GUI loop (window stays open until you close it)
    gui.root.mainloop()


if __name__ == "__main__":
    main()
