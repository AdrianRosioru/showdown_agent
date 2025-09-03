from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.battle.side_condition import SideCondition
from typing import Dict, List, Optional, Tuple
import math

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
# Tunable global thresholds
# =========================
HEAL_THRESHOLD = 0.40           # <= 40%: try to heal before anything else (if it saves you this turn)
NEAR_LETHAL_MULT = 0.85         # "almost lethal" bar for emergency heals
BAD_PRESSURE_THRESH = 0.22      # our best hit does <22% → we have poor pressure
CHUNKY_HIT_THRESH   = 0.40      # they chunk >=40% per worst hit
SWITCH_MARGIN       = 0.18      # bench counter score must beat current by this margin
SAFER_PAD           = 0.08      # how much safer the switch’s worst hit should be
RESIST_GAIN_NEEDED  = 0.80      # how many resist points better the switch should be
DAMAGE_TIE_EPS      = 0.03      # tie-breaker epsilon for move choice

# =========================================================
#                     Core (type-chart centric)
# =========================================================
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
    EFF_POINTS = {0.0: 3.0, 0.25: 2.0, 0.5: 1.0, 1.0: 0.0, 2.0: -1.0, 4.0: -2.0}
    TYPES_ORDER = ["normal","fire","water","electric","grass","ice","fighting","poison","ground","flying",
                   "psychic","bug","rock","ghost","dragon","dark","steel","fairy"]

    # --------- normalization helpers ----------
    @staticmethod
    def _norm_name(s: Optional[str]) -> str:
        return (str(s or "")).lower().replace("-", "")

    @staticmethod
    def types(mon) -> List[str]:
        out = []
        for t in (getattr(mon, "types", None) or []):
            if t:
                out.append(Core._norm_name(getattr(t, "name", str(t))))
        return out

    @staticmethod
    def base_stat(mon, key: str) -> float:
        if not mon: return 0.0
        return float(((getattr(mon, "base_stats", {}) or {}).get(key, 0)) or 0.0)

    @staticmethod
    def stat(mon, key: str) -> float:
        if not mon: return 0.0
        v = ((getattr(mon, "stats", {}) or {}).get(key))
        if v is None: v = ((getattr(mon, "base_stats", {}) or {}).get(key, 0))
        return float(v or 0.0)

    @staticmethod
    def ability(mon) -> str:
        return Core._norm_name(getattr(mon, "ability", "") or "")

    @staticmethod
    def item(mon) -> str:
        return (str(getattr(mon, "item", "") or "")).lower()

    @staticmethod
    def hp(mon) -> float:
        return float(getattr(mon, "current_hp_fraction", 0.0) or 0.0)

    @staticmethod
    def is_physical(move) -> bool:
        return getattr(move, "category", None) and getattr(move.category, "name", "") == "PHYSICAL"

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
    def has_ground_immunity(mon) -> bool:
        return ("flying" in Core.types(mon)) or (Core.ability(mon) == "levitate")

    @staticmethod
    def grounded(mon) -> bool:
        return not Core.has_ground_immunity(mon)

    @staticmethod
    def has_boots(mon) -> bool:
        return "boots" in Core.item(mon)

    @staticmethod
    def type_eff(atk_type: Optional[str], def_types: List[str], defender=None) -> float:
        if not atk_type: return 1.0
        atk_type = Core._norm_name(getattr(atk_type, "name", atk_type))
        if atk_type == "ground" and defender is not None and Core.has_ground_immunity(defender):
            return 0.0
        mult = 1.0
        chart = Core.TYPE_CHART.get(atk_type, {})
        for t in def_types or []:
            mult *= chart.get(t, 1.0)
        return mult

    @staticmethod
    def estimate_damage_fraction(attacker, defender, move) -> float:
        if not attacker or not defender or not move or not Core.is_damaging(move):
            return 0.0
        bp = float(getattr(move, "base_power", 0) or 0)
        if bp <= 0: return 0.0
        atk_is_phys = Core.is_physical(move)
        atk_stat = Core.stat(attacker, "atk" if atk_is_phys else "spa")
        def_stat = Core.stat(defender, "def" if atk_is_phys else "spd")
        mtype = getattr(move, "type", None); mtype = Core._norm_name(getattr(mtype, "name", mtype))
        eff = Core.type_eff(mtype, Core.types(defender), defender=defender)
        if eff <= 0.0: return 0.0
        stab = 1.5 if (mtype and mtype in Core.types(attacker)) else 1.0
        acc = Core.acc(move)
        stat_ratio = max(0.1, atk_stat / max(1.0, def_stat))
        raw = (bp / 90.0) * 0.45 * stab * eff * stat_ratio * acc
        return float(max(0.0, min(1.0, raw)))

    @staticmethod
    def _predict_lane(attacker) -> str:
        atk_b = Core.base_stat(attacker, "atk"); spa_b = Core.base_stat(attacker, "spa")
        return "phys" if atk_b >= spa_b else "spec"

    @staticmethod
    def estimate_type_damage_fraction(attacker, defender, atk_type: str) -> float:
        if not attacker or not defender or not atk_type:
            return 0.0
        lane = Core._predict_lane(attacker)
        atk_stat = Core.stat(attacker, "atk" if lane == "phys" else "spa")
        def_stat = Core.stat(defender, "def" if lane == "phys" else "spd")
        atk_type = Core._norm_name(atk_type)
        eff = Core.type_eff(atk_type, Core.types(defender), defender=defender)
        if eff == 0.0: return 0.0
        stab = 1.5 if atk_type in Core.types(attacker) else 1.0
        stat_ratio = max(0.1, atk_stat / max(1.0, def_stat))
        raw = 1.0 * 0.45 * stab * eff * stat_ratio
        return float(max(0.0, min(1.0, raw)))

    @staticmethod
    def estimate_bp_type_damage_fraction(attacker, defender, move_type: str, bp: float, category: str) -> float:
        if not attacker or not defender or not move_type or bp <= 0:
            return 0.0
        move_type = Core._norm_name(move_type)
        use_phys = (category == "phys")
        atk_stat = Core.stat(attacker, "atk" if use_phys else "spa")
        def_stat = Core.stat(defender, "def" if use_phys else "spd")
        eff = Core.type_eff(move_type, Core.types(defender), defender=defender)
        if eff == 0.0: return 0.0
        stab = 1.5 if move_type in Core.types(attacker) else 1.0
        stat_ratio = max(0.1, atk_stat / max(1.0, def_stat))
        raw = (bp / 90.0) * 0.45 * stab * eff * stat_ratio
        return float(max(0.0, min(1.0, raw)))

    @staticmethod
    def eff_points(mult: float) -> float:
        keys = sorted(Core.EFF_POINTS.keys())
        for i in range(len(keys)-1):
            if keys[i] <= mult <= keys[i+1]:
                a, b = keys[i], keys[i+1]
                ya, yb = Core.EFF_POINTS[a], Core.EFF_POINTS[b]
                if b == a: return ya
                t = (mult - a) / (b - a)
                return ya + t * (yb - ya)
        return Core.EFF_POINTS.get(mult, 0.0)

    @staticmethod
    def _entry_hazard_frac(battle, cand) -> float:
        if Core.has_boots(cand): return 0.0
        sc = battle.side_conditions or {}
        frac = 0.0
        if sc.get(SideCondition.STEALTH_ROCK, 0):
            mult = Core.type_eff("rock", Core.types(cand), defender=cand)
            frac += 0.125 * mult
        if Core.grounded(cand):
            layers = int(sc.get(SideCondition.SPIKES, 0) or 0)
            if layers == 1: frac += 1.0/8.0
            elif layers == 2: frac += 1.0/6.0
            elif layers >= 3: frac += 1.0/4.0
        return float(frac)

    @staticmethod
    def _toxic_spikes_effects(battle, cand) -> Dict[str, bool]:
        sc = battle.side_conditions or {}
        layers = int(sc.get(SideCondition.TOXIC_SPIKES, 0) or 0)
        if layers <= 0:
            return {"poison": False, "toxic": False, "absorb": False}
        grounded = Core.grounded(cand)
        types = set(Core.types(cand))
        if Core.has_boots(cand) or not grounded or "steel" in types:
            return {"poison": False, "toxic": False, "absorb": False}
        if "poison" in types:
            return {"poison": False, "toxic": False, "absorb": True}
        return {"poison": layers == 1, "toxic": layers >= 2, "absorb": False}

# ===== Known movekits for YOUR team (used before moves are revealed) =====
TEAM_KNOWN_MOVES: Dict[str, List[Tuple[str,int,str]]] = {
    "clodsire":        [("ground", 100, "phys")],
    "giratinaorigin":  [("ghost", 110, "phys"), ("dragon", 60, "phys")],
    "hooh":            [("fire", 100, "phys"), ("flying", 120, "phys")],
    "dondozo":         [("water", 85, "phys")],
    "arceusfairy":     [("fairy", 100, "spec"), ("ground", 90, "spec")],
    "eternatus":       [("fire", 90, "spec"), ("dragon", 60, "phys")],
}
USER_TYPES = {
    "clodsire": {"ground","poison"},
    "giratinaorigin": {"ghost","dragon"},
    "hooh": {"fire","flying"},
    "dondozo": {"water"},
    "arceusfairy": {"fairy"},
    "eternatus": {"poison","dragon"},
}
def _species_key(p) -> str:
    return (getattr(p, "species", "") or "").lower().replace("-", "")

# =========================================================
#                Counter-aware Agent (switch+heal safe)
# =========================================================
class CustomAgent(Player, Core):
    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)

    def _me(self, battle):  return battle.active_pokemon
    def _opp(self, battle): return battle.opponent_active_pokemon

    def _move(self, battle: AbstractBattle, move_id: str):
        for m in (battle.available_moves or []):
            if m.id == move_id and not getattr(m, "disabled", False) and (getattr(m, "pp", 1) or 1) > 0:
                return m
        return None

    # ---------- Matchup modeling ----------
    def _opp_attacking_types(self, opp) -> List[str]:
        seen = []
        for mv in (getattr(opp, "moves", {}) or {}).values():
            if Core.is_damaging(mv):
                t = getattr(mv, "type", None); t = Core._norm_name(getattr(t, "name", t))
                if t and t not in seen:
                    seen.append(t)
        return seen or Core.types(opp)

    def _resist_points_vs(self, cand, opp) -> float:
        pts = 0.0
        for t in self._opp_attacking_types(opp):
            mult = Core.type_eff(t, Core.types(cand), defender=cand)
            pts += Core.eff_points(mult)
        return pts

    def _worst_expected_hit(self, cand, opp) -> float:
        worst = 0.0
        for t in self._opp_attacking_types(opp):
            worst = max(worst, Core.estimate_type_damage_fraction(opp, cand, t))
        return worst

    def _best_offense(self, battle, cand, opp) -> float:
        best = 0.0
        if cand is self._me(battle):
            for mv in (battle.available_moves or []):
                if Core.is_damaging(mv):
                    best = max(best, Core.estimate_damage_fraction(cand, opp, mv))
        for mv in (getattr(cand, "moves", {}) or {}).values():
            if Core.is_damaging(mv):
                best = max(best, Core.estimate_damage_fraction(cand, opp, mv))
        if best > 0:
            return best
        for (t, bp, cat) in TEAM_KNOWN_MOVES.get(_species_key(cand), []):
            best = max(best, Core.estimate_bp_type_damage_fraction(cand, opp, t, bp, cat))
        if best > 0:
            return best
        best_eff = 1.0
        for t in Core.types(cand):
            best_eff = max(best_eff, Core.type_eff(t, Core.types(opp), defender=opp))
        lane = Core._predict_lane(cand)
        atk_stat = Core.stat(cand, "atk" if lane == "phys" else "spa")
        def_stat = Core.stat(opp, "def" if lane == "phys" else "spd")
        stat_ratio = max(0.1, atk_stat / max(1.0, def_stat))
        return float(max(0.0, min(1.0, 1.0 * 0.45 * 1.5 * best_eff * stat_ratio)))

    def _immunity_bonus(self, cand, opp) -> float:
        for t in self._opp_attacking_types(opp):
            if Core.type_eff(t, Core.types(cand), defender=cand) == 0.0:
                return 0.6
        return 0.0

    def _utility_bonus(self, cand, opp) -> float:
        bonus = 0.0
        boosted = any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values())
        if boosted and Core.ability(cand) == "unaware":
            bonus += 0.25
        has_haze = any(getattr(mv, "id", "") == "haze" for mv in (getattr(cand, "moves", {}) or {}).values())
        has_ww   = any(getattr(mv, "id", "") == "whirlwind" for mv in (getattr(cand, "moves", {}) or {}).values())
        has_dt   = any(getattr(mv, "id", "") == "dragontail" for mv in (getattr(cand, "moves", {}) or {}).values())
        if boosted and (has_haze or has_ww or has_dt):
            bonus += 0.2
        if "poison" in Core.types(cand) and ("fairy" in self._opp_attacking_types(opp)):
            bonus += 0.1
        return bonus

    def _hazard_penalties(self, battle, cand) -> float:
        frac = Core._entry_hazard_frac(battle, cand)
        ts = Core._toxic_spikes_effects(battle, cand)
        if Core.hp(cand) <= frac + 1e-6:
            return 10.0
        penalty = 1.05 * frac
        if ts["poison"]: penalty += 0.10
        if ts["toxic"]:  penalty += 0.18
        if ts["absorb"]: penalty -= 0.20
        sc = battle.side_conditions or {}
        if sc.get(SideCondition.STICKY_WEB, 0) and Core.grounded(cand) and not Core.has_boots(cand):
            penalty += 0.05
        return max(0.0, penalty)

    def _counter_score(self, battle, cand, opp) -> float:
        if not cand or not opp: return -1e9
        if Core.hp(cand) <= Core._entry_hazard_frac(battle, cand) + 1e-6:
            return -1e9
        resist_pts = self._resist_points_vs(cand, opp)
        worst_in   = self._worst_expected_hit(cand, opp)
        offense    = self._best_offense(battle, cand, opp)
        imm        = self._immunity_bonus(cand, opp)
        util       = self._utility_bonus(cand, opp)
        hazards    = self._hazard_penalties(battle, cand)
        score = (1.10 * resist_pts) + (0.90 * imm) + (0.72 * offense) + (0.30 * util) \
                - (0.65 * worst_in) - (1.00 * hazards)
        if offense < 0.15: score -= 0.70
        score += 0.12 * Core.hp(cand)
        return score

    # ---------- Switch helpers ----------
    def _best_counter_switch(self, battle, opp):
        cands = (battle.available_switches or [])
        if not cands: return None, -1e9
        best, best_score = None, -1e9
        for sw in cands:
            s = self._counter_score(battle, sw, opp)
            if s > best_score:
                best, best_score = sw, s
        return best, best_score

    def _bad_matchup(self, battle, me, opp, best_dmg: float, worst_in: float) -> bool:
        if getattr(me, "trapped", False): return False
        bad_pressure = best_dmg < BAD_PRESSURE_THRESH
        chunky_hit   = worst_in >= CHUNKY_HIT_THRESH
        very_bad_resist = self._resist_points_vs(me, opp) <= -1.0
        return (bad_pressure and (chunky_hit or very_bad_resist)) or (chunky_hit and very_bad_resist)

    # ---------- Move helpers ----------
    def _best_damage_move(self, battle, me, opp):
        best, score = None, -1.0
        best_eff = 0.0
        for mv in (battle.available_moves or []):
            if not Core.is_damaging(mv): continue
            d = Core.estimate_damage_fraction(me, opp, mv)
            if d >= Core.hp(opp): d += 0.40  # KO nudge
            # tie-break: prefer higher type multiplier when close in damage
            mtype = getattr(mv, "type", None); mtype = Core._norm_name(getattr(mtype, "name", mtype))
            eff = Core.type_eff(mtype, Core.types(opp), defender=opp)
            if d > score + DAMAGE_TIE_EPS or (abs(d - score) <= DAMAGE_TIE_EPS and eff > best_eff):
                best, score, best_eff = mv, d, eff
        return best, max(0.0, score)

    def _maybe_hazards_or_utility(self, battle, me, opp):
        if getattr(me, "status", "") == "slp":
            st = self._move(battle, "sleeptalk")
            if st: return st
        if "clodsire" in (getattr(me, "species","") or "").lower().replace("-", ""):
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                hz = self._move(battle, "haze")
                if hz: return hz
            sp = self._move(battle, "spikes")
            if sp:
                opp_sc = battle.opponent_side_conditions or {}
                layers = int(opp_sc.get(SideCondition.SPIKES, 0) or 0)
                if layers < 3 and Core.hp(me) >= 0.70 and self._worst_expected_hit(me, opp) < 0.25:
                    return sp
        if "giratina" in (getattr(me, "species","") or "").lower().replace("-", ""):
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                dt = self._move(battle, "dragontail")
                if dt and self._worst_expected_hit(me, opp) < Core.hp(me) - 0.05:
                    return dt
        if "hooh" in (getattr(me, "species","") or "").lower().replace("-", ""):
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                ww = self._move(battle, "whirlwind")
                if ww and self._worst_expected_hit(me, opp) < Core.hp(me) - 0.05:
                    return ww
        if "dondozo" in (getattr(me, "species","") or "").lower().replace("-", ""):
            rst = self._move(battle, "rest")
            if rst and (Core.hp(me) <= 0.45 or self._worst_expected_hit(me, opp) >= Core.hp(me)):
                return rst
        return None

    def _get_heal_move(self, battle):
        for hid in ("recover","roost","slackoff","moonlight","rest"):
            mv = self._move(battle, hid)
            if mv: return mv
        return None

    # ---------- Main decision loop ----------
    def choose_move(self, battle: AbstractBattle):
        me, opp = self._me(battle), self._opp(battle)

        # Forced switch (lead/after KO)
        fs = getattr(battle, "force_switch", False)
        need_switch = bool(fs if isinstance(fs, bool) else any(fs))
        if need_switch:
            if opp:
                sw, _ = self._best_counter_switch(battle, opp)
                if sw: return self.create_order(sw)
            cands = battle.available_switches or []
            if cands:
                def bulk_ok(p):
                    dmg = Core._entry_hazard_frac(battle, p)
                    return Core.stat(p, "def") + Core.stat(p, "spd") + 2*Core.stat(p, "hp") - 2000.0*dmg
                viable = [p for p in cands if Core.hp(p) > Core._entry_hazard_frac(battle, p) + 1e-6]
                return self.create_order(max(viable or cands, key=bulk_ok))
            return self.choose_random_move(battle)

        if not me or not opp:
            return self.choose_random_move(battle)

        # Quick KO check first
        best_mv, best_dmg = self._best_damage_move(battle, me, opp)
        if best_mv and best_dmg >= Core.hp(opp):
            return self.create_order(best_mv)

        worst_in = self._worst_expected_hit(me, opp)
        my_hp = Core.hp(me)

        # If asleep, try Sleep Talk before anything else
        if getattr(me, "status", "") == "slp":
            util = self._maybe_hazards_or_utility(battle, me, opp)
            if util: return self.create_order(util)

        # ===== PRIORITY: Heal at <= 40% if it actually keeps us alive (or it's Rest) =====
        heal_mv = self._get_heal_move(battle)
        if heal_mv and my_hp <= HEAL_THRESHOLD:
            heal_gain = 1.0 if heal_mv.id == "rest" else 0.5
            heals_out = (my_hp + heal_gain) > worst_in
            if heal_mv.id == "rest" or heals_out:
                return self.create_order(heal_mv)

        # >>> EARLY SWITCH DECISION <<<
        # Switch before utility/heal if matchup is bad or a bench counter is clearly better.
        if not getattr(me, "trapped", False):
            my_score = self._counter_score(battle, me, opp)
            sw, sw_score = self._best_counter_switch(battle, opp)
            if sw:
                margin = sw_score - my_score
                safer = self._worst_expected_hit(sw, opp) + SAFER_PAD < worst_in
                resist_gain = (self._resist_points_vs(sw, opp) - self._resist_points_vs(me, opp)) >= RESIST_GAIN_NEEDED
                if (margin > SWITCH_MARGIN and (safer or resist_gain)) or self._bad_matchup(battle, me, opp, best_dmg or 0.0, worst_in):
                    return self.create_order(sw)

        # Emergency heal if it prevents a KO and we didn't switch
        if heal_mv:
            lethal = worst_in >= my_hp
            near_lethal = (my_hp <= HEAL_THRESHOLD) or (worst_in >= my_hp * NEAR_LETHAL_MULT)
            heal_gain = 1.0 if heal_mv.id == "rest" else 0.5
            heals_out = (my_hp + heal_gain) > worst_in
            if (lethal or near_lethal) and heals_out:
                return self.create_order(heal_mv)

        # Useful utility (Haze/Phaze/Spikes/Rest-on-Dozo)
        util = self._maybe_hazards_or_utility(battle, me, opp)
        if util:
            return self.create_order(util)

        # Regular heal if still valuable
        if heal_mv:
            heal_gain = 1.0 if heal_mv.id == "rest" else 0.5
            if (my_hp <= HEAL_THRESHOLD) or (worst_in >= my_hp and (my_hp + heal_gain) > worst_in):
                return self.create_order(heal_mv)

        # Otherwise push best damage
        if best_mv:
            return self.create_order(best_mv)

        # Last-resort utility
        for aux_id in ("willowisp","dragontail","whirlwind","defog","spikes"):
            aux = self._move(battle, aux_id)
            if aux:
                return self.create_order(aux)

        return self.choose_random_move(battle)

    # ===== Optional: print tables for move effectiveness/power =====
    def dump_move_effectiveness_tables(self):
        moves = [
            ("Earthquake", "ground", 100, "phys", "clodsire"),
            ("Poltergeist", "ghost", 110, "phys", "giratinaorigin"),
            ("Dragon Tail (Gira-O)", "dragon", 60, "phys", "giratinaorigin"),
            ("Sacred Fire", "fire", 100, "phys", "hooh"),
            ("Brave Bird", "flying", 120, "phys", "hooh"),
            ("Liquidation", "water", 85, "phys", "dondozo"),
            ("Judgment (Fairy)", "fairy", 100, "spec", "arceusfairy"),
            ("Earth Power", "ground", 90, "spec", "arceusfairy"),
            ("Flamethrower", "fire", 90, "spec", "eternatus"),
            ("Dragon Tail (Eternatus)", "dragon", 60, "phys", "eternatus"),
        ]

        def mult_row(move_type: str) -> Dict[str,float]:
            return {def_t: Core.TYPE_CHART.get(move_type, {}).get(def_t, 1.0) for def_t in Core.TYPES_ORDER}

        print("\n=== Move effectiveness (pure type multipliers) ===")
        header = ["User","Move","Type"] + Core.TYPES_ORDER
        print("\t".join(header))
        for (name, mtype, bp, cat, user) in moves:
            row = [user, name, mtype] + [str(mult_row(mtype)[def_t]) for def_t in Core.TYPES_ORDER]
            print("\t".join(row))

        print("\n=== Move power index (BP × STAB × type multiplier) ===")
        print("\t".join(header))
        for (name, mtype, bp, cat, user) in moves:
            stab = 1.5 if mtype in USER_TYPES.get(user, set()) else 1.0
            vals = []
            for def_t in Core.TYPES_ORDER:
                mult = Core.TYPE_CHART.get(mtype, {}).get(def_t, 1.0)
                vals.append(str(bp * stab * mult))
            row = [user, name, mtype] + vals
            print("\t".join(row))
