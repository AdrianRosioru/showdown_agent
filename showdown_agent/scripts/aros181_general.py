from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.battle.side_condition import SideCondition
from typing import List, Optional, Dict

# --------------------
# Your team (unchanged)
# --------------------
team = """
Clodsire @ Black Sludge
Ability: Unaware
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Spikes
- Recover
- Haze
- Earthquake

Giratina-Origin @ Griseous Core
Ability: Levitate
Tera Type: Steel
EVs: 248 HP / 104 Atk / 112 Def / 44 Spe
Adamant Nature
- Defog
- Poltergeist
- Dragon Tail
- Will-O-Wisp

Ho-Oh @ Heavy-Duty Boots
Ability: Regenerator
Tera Type: Grass
EVs: 248 HP / 236 Def / 24 Spe
Impish Nature
- Sacred Fire
- Brave Bird
- Recover
- Whirlwind

Dondozo @ Leftovers
Ability: Unaware
Tera Type: Steel
EVs: 252 HP / 252 Def / 4 SpD
Impish Nature
- Liquidation
- Curse
- Rest
- Sleep Talk

Arceus-Fairy @ Pixie Plate
Ability: Multitype
Tera Type: Water
EVs: 252 HP / 196 Def / 60 Spe
Bold Nature
- Calm Mind
- Judgment
- Recover
- Earth Power

Eternatus @ Black Sludge
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Cosmic Power
- Recover
- Flamethrower
- Dragon Tail
"""

# =========================
# Minimal knobs
# =========================
HEAL_THRESHOLD = 0.40     # heal at/below this if healing keeps you alive
DIE_SWITCH_PAD = 0.00     # switch if worst-in >= hp + pad and you can't heal out
COUNTER_MARGIN  = 0.15    # proactive type-counter switch if it reduces incoming by >= this
ENTRY_SAFETY_PAD = 1e-6   # tiny pad for hazard-KO checks

# =========================
# Tiny core (just enough)
# =========================
class Core:
    TYPE_CHART: Dict[str, Dict[str, float]] = {
        "normal":  {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
        "fire":    {"grass": 2, "ice": 2, "bug": 2, "steel": 2, "fire": 0.5, "water": 0.5, "rock": 0.5, "dragon": 0.5},
        "water":   {"fire": 2, "ground": 2, "rock": 2, "water": 0.5, "grass": 0.5, "dragon": 0.5},
        "electric":{"water": 2, "flying": 2, "electric": 0.5, "grass": 0.5, "dragon": 0.5, "ground": 0.0},
        "grass":   {"water": 2, "ground": 2, "rock": 2, "fire": 0.5, "grass": 0.5, "poison": 0.5, "flying": 0.5, "bug": 0.5, "dragon": 0.5, "steel": 0.5},
        "ice":     {"grass": 2, "ground": 2, "flying": 2, "dragon": 2, "fire": 0.5, "water": 0.5, "ice": 0.5, "steel": 0.5},
        "fighting":{"normal": 2, "ice": 2, "rock": 2, "dark": 2, "steel": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "fairy": 0.5, "ghost": 0.0},
        "poison":  {"grass": 2, "fairy": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0},
        "ground":  {"fire": 2, "electric": 2, "poison": 2, "rock": 2, "steel": 2, "grass": 0.5, "bug": 0.5, "flying": 0.0},
        "flying":  {"grass": 2, "fighting": 2, "bug": 2, "electric": 0.5, "rock": 0.5, "steel": 0.5},
        "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5, "steel": 0.5, "dark": 0.0},
        "bug":     {"grass": 2, "psychic": 2, "dark": 2, "fire": 0.5, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "ghost": 0.5, "steel": 0.5, "fairy": 0.5},
        "rock":    {"fire": 2, "ice": 2, "flying": 2, "bug": 2, "fighting": 0.5, "ground": 0.5, "steel": 0.5},
        "ghost":   {"psychic": 2, "ghost": 2, "dark": 0.5, "normal": 0.0},
        "dragon":  {"dragon": 2, "steel": 0.5, "fairy": 0.0},
        "dark":    {"psychic": 2, "ghost": 2, "fighting": 0.5, "dark": 0.5, "fairy": 0.5},
        "steel":   {"ice": 2, "rock": 2, "fairy": 2, "fire": 0.5, "water": 0.5, "electric": 0.5, "steel": 0.5},
        "fairy":   {"fighting": 2, "dragon": 2, "dark": 2, "fire": 0.5, "poison": 0.5, "steel": 0.5},
    }

    def teampreview(self, battle):
        return "/team 612345"

    @staticmethod
    def _norm(s: Optional[str]) -> str:
        return (s or "").lower().replace("-", "")

    @staticmethod
    def types(mon) -> List[str]:
        ts = []
        for t in (getattr(mon, "types", None) or []):
            if t:
                ts.append(Core._norm(getattr(t, "name", str(t))))
        return ts

    @staticmethod
    def hp(mon) -> float:
        return float(getattr(mon, "current_hp_fraction", 0.0) or 0.0)

    @staticmethod
    def stat(mon, key: str) -> float:
        if not mon: return 0.0
        v = ((getattr(mon, "stats", {}) or {}).get(key))
        if v is None: v = ((getattr(mon, "base_stats", {}) or {}).get(key, 0))
        return float(v or 0.0)

    @staticmethod
    def is_damaging(move) -> bool:
        try:
            return (getattr(move, "base_power", 0) or 0) > 0
        except Exception:
            return False

    @staticmethod
    def acc(move) -> float:
        a = getattr(move, "accuracy", 100)
        if a is True or a is None: return 1.0
        try: return max(0.0, min(1.0, float(a) / 100.0))
        except Exception: return 1.0

    @staticmethod
    def type_eff(atk_type: Optional[str], def_types: List[str], defender=None) -> float:
        if not atk_type: return 1.0
        atk_type = Core._norm(getattr(atk_type, "name", atk_type))
        # simple ground immunity check
        if atk_type == "ground" and (("flying" in def_types) or (getattr(defender, "ability", "") and "Levitate" in str(defender.ability))):
            return 0.0
        mult = 1.0
        chart = Core.TYPE_CHART.get(atk_type, {})
        for t in def_types or []:
            mult *= chart.get(t, 1.0)
        return mult

    @staticmethod
    def estimate_damage_fraction(attacker, defender, move) -> float:
        """Very rough expected damage fraction (includes accuracy)."""
        if not attacker or not defender or not move or not Core.is_damaging(move):
            return 0.0
        bp = float(getattr(move, "base_power", 0) or 0)
        if bp <= 0: return 0.0
        is_phys = (getattr(getattr(move, "category", None), "name", "") == "PHYSICAL")
        atk = Core.stat(attacker, "atk" if is_phys else "spa")
        dfn = Core.stat(defender, "def" if is_phys else "spd")
        mtype = getattr(move, "type", None); mtype = Core._norm(getattr(mtype, "name", mtype))
        eff = Core.type_eff(mtype, Core.types(defender), defender=defender)
        if eff <= 0.0: return 0.0
        stab = 1.5 if (mtype and mtype in Core.types(attacker)) else 1.0
        acc = Core.acc(move)
        stat_ratio = max(0.1, atk / max(1.0, dfn))
        # tuned constant just to scale into [0,1] ish
        raw = (bp / 90.0) * 0.45 * stab * eff * stat_ratio * acc
        return float(max(0.0, min(1.0, raw)))

    @staticmethod
    def opp_attack_types(opp) -> List[str]:
        seen = []
        for mv in (getattr(opp, "moves", {}) or {}).values():
            if Core.is_damaging(mv):
                t = getattr(mv, "type", None); t = Core._norm(getattr(t, "name", t))
                if t and t not in seen:
                    seen.append(t)
        return seen or Core.types(opp)

    @staticmethod
    def worst_expected_hit(defender, opp) -> float:
        worst = 0.0
        for t in Core.opp_attack_types(opp):
            # pretend a 90 BP STAB-ish move of that type
            lane_phys = (Core.stat(opp, "atk") >= Core.stat(opp, "spa"))
            atk = Core.stat(opp, "atk" if lane_phys else "spa")
            dfn = Core.stat(defender, "def" if lane_phys else "spd")
            eff = Core.type_eff(t, Core.types(defender), defender=defender)
            if eff == 0.0:
                continue
            stab = 1.5 if t in Core.types(opp) else 1.0
            raw = (90.0/90.0) * 0.45 * stab * eff * max(0.1, atk/max(1.0, dfn))
            worst = max(worst, min(1.0, raw))
        return worst

    @staticmethod
    def entry_hazard_frac(battle, cand) -> float:
        """SR + Spikes that will hit us (rough)."""
        frac = 0.0
        sc = battle.side_conditions or {}
        # Stealth Rock
        if sc.get(SideCondition.STEALTH_ROCK, 0):
            eff = Core.type_eff("rock", Core.types(cand), defender=cand)
            frac += 0.125 * eff
        # Spikes (grounded only; rough)
        is_flying = ("flying" in Core.types(cand))
        has_levi = (getattr(cand, "ability", "") and "Levitate" in str(cand.ability))
        grounded = not (is_flying or has_levi)
        if grounded:
            layers = int(sc.get(SideCondition.SPIKES, 0) or 0)
            if layers == 1: frac += 1/8
            elif layers == 2: frac += 1/6
            elif layers >= 3: frac += 1/4
        return float(max(0.0, min(1.0, frac)))

# =========================================================
#                Minimal “Switch / Heal / Hit (+counter)” agent
# =========================================================
class CustomAgent(Player, Core):
    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)

    # ----- tiny helpers -----
    def _me(self, battle):  return battle.active_pokemon
    def _opp(self, battle): return battle.opponent_active_pokemon

    def _move_by_id(self, battle: AbstractBattle, move_id: str):
        for m in (battle.available_moves or []):
            if m.id == move_id and not getattr(m, "disabled", False) and (getattr(m, "pp", 1) or 1) > 0:
                return m
        return None

    def _best_damaging_move(self, battle, me, opp):
        best, score = None, -1.0
        for mv in (battle.available_moves or []):
            if not Core.is_damaging(mv):
                continue
            d = Core.estimate_damage_fraction(me, opp, mv)  # accuracy-weighted expected damage
            if d > score:
                best, score = mv, d
        return best, max(0.0, score)

    def _heal_move(self, battle):
        for hid in ("recover","roost","slackoff","moonlight","rest"):
            mv = self._move_by_id(battle, hid)
            if mv: return mv
        return None

    def _safest_switch(self, battle, opp):
        """Pick the switch that minimizes (hazard chip + worst expected hit)."""
        cands = battle.available_switches or []
        if not cands:
            return None
        def cost(p):
            hz = Core.entry_hazard_frac(battle, p)
            worst = Core.worst_expected_hit(p, opp)
            if Core.hp(p) <= hz + ENTRY_SAFETY_PAD:
                return 999.0  # would KO on entry
            return hz + worst
        return min(cands, key=cost)

    def _counter_switch_if_better(self, battle, me, opp) -> Optional[object]:
        """If a switch clearly reduces incoming damage, do it (type counter)."""
        if getattr(me, "trapped", False):
            return None
        current_cost = Core.worst_expected_hit(me, opp)
        sw = self._safest_switch(battle, opp)
        if not sw:
            return None
        hz = Core.entry_hazard_frac(battle, sw)
        if Core.hp(sw) <= hz + ENTRY_SAFETY_PAD:
            return None
        new_cost = hz + Core.worst_expected_hit(sw, opp)
        if (current_cost - new_cost) >= COUNTER_MARGIN:
            return sw
        return None

    # ----- main decision -----
    def choose_move(self, battle: AbstractBattle):
        me, opp = self._me(battle), self._opp(battle)

        # 1) Forced switch: choose the safest switch.
        fs = getattr(battle, "force_switch", False)
        need_switch = bool(fs if isinstance(fs, bool) else any(fs))
        if need_switch and opp:
            sw = self._safest_switch(battle, opp)
            if sw:
                return self.create_order(sw)
            return self.choose_random_move(battle)

        if not me or not opp:
            return self.choose_random_move(battle)

        # 2) Proactive counter-type switch BEFORE heal/attack (only if it's clearly safer).
        counter_sw = self._counter_switch_if_better(battle, me, opp)
        if counter_sw:
            return self.create_order(counter_sw)

        my_hp = Core.hp(me)
        worst_in = Core.worst_expected_hit(me, opp)

        # 3) Heal if low AND healing keeps us alive this turn (Rest=full, others≈50%).
        heal = self._heal_move(battle)
        if heal and my_hp <= HEAL_THRESHOLD:
            heal_gain = 1.0 if heal.id == "rest" else 0.5
            if (my_hp + heal_gain) > worst_in or heal.id == "rest":
                return self.create_order(heal)

        # 4) If we are likely to die this turn and we can't heal out, switch (if not trapped).
        if not getattr(me, "trapped", False):
            if worst_in >= my_hp + DIE_SWITCH_PAD and not (heal and (my_hp + (1.0 if heal.id == "rest" else 0.5)) > worst_in):
                sw = self._safest_switch(battle, opp)
                if sw:
                    return self.create_order(sw)

        # 5) Otherwise, just hit with the biggest expected damage move.
        best_mv, _ = self._best_damaging_move(battle, me, opp)
        if best_mv:
            return self.create_order(best_mv)

        # 6) If no damaging moves are available, pick anything legal at random.
        return self.choose_random_move(battle)
