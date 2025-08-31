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
        "Normal":  {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
        "Fire":    {"Grass": 2, "Ice": 2, "Bug": 2, "Steel": 2, "Fire": 0.5, "Water": 0.5, "Rock": 0.5, "Dragon": 0.5},
        "Water":   {"Fire": 2, "Ground": 2, "Rock": 2, "Water": 0.5, "Grass": 0.5, "Dragon": 0.5},
        "Electric":{"Water": 2, "Flying": 2, "Electric": 0.5, "Grass": 0.5, "Dragon": 0.5, "Ground": 0.0},
        "Grass":   {"Water": 2, "Ground": 2, "Rock": 2, "Fire": 0.5, "Grass": 0.5, "Poison": 0.5, "Flying": 0.5, "Bug": 0.5, "Dragon": 0.5, "Steel": 0.5},
        "Ice":     {"Grass": 2, "Ground": 2, "Flying": 2, "Dragon": 2, "Fire": 0.5, "Water": 0.5, "Ice": 0.5, "Steel": 0.5},
        "Fighting":{"Normal": 2, "Ice": 2, "Rock": 2, "Dark": 2, "Steel": 2, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Fairy": 0.5, "Ghost": 0.0},
        "Poison":  {"Grass": 2, "Fairy": 2, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0},
        "Ground":  {"Fire": 2, "Electric": 2, "Poison": 2, "Rock": 2, "Steel": 2, "Grass": 0.5, "Bug": 0.5, "Flying": 0.0},
        "Flying":  {"Grass": 2, "Fighting": 2, "Bug": 2, "Electric": 0.5, "Rock": 0.5, "Steel": 0.5},
        "Psychic": {"Fighting": 2, "Poison": 2, "Psychic": 0.5, "Steel": 0.5, "Dark": 0.0},
        "Bug":     {"Grass": 2, "Psychic": 2, "Dark": 2, "Fire": 0.5, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Ghost": 0.5, "Steel": 0.5, "Fairy": 0.5},
        "Rock":    {"Fire": 2, "Ice": 2, "Flying": 2, "Bug": 2, "Fighting": 0.5, "Ground": 0.5, "Steel": 0.5},
        "Ghost":   {"Psychic": 2, "Ghost": 2, "Dark": 0.5, "Normal": 0.0},
        "Dragon":  {"Dragon": 2, "Steel": 0.5, "Fairy": 0.0},
        "Dark":    {"Psychic": 2, "Ghost": 2, "Fighting": 0.5, "Dark": 0.5, "Fairy": 0.5},
        "Steel":   {"Ice": 2, "Rock": 2, "Fairy": 2, "Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Steel": 0.5},
        "Fairy":   {"Fighting": 2, "Dragon": 2, "Dark": 2, "Fire": 0.5, "Poison": 0.5, "Steel": 0.5},
    }
    EFF_POINTS = {0.0: 3.0, 0.25: 2.0, 0.5: 1.0, 1.0: 0.0, 2.0: -1.0, 4.0: -2.0}
    TYPES_ORDER = ["Normal","Fire","Water","Electric","Grass","Ice","Fighting","Poison","Ground","Flying",
                   "Psychic","Bug","Rock","Ghost","Dragon","Dark","Steel","Fairy"]

    @staticmethod
    def types(mon) -> List[str]:
        out = []
        for t in (getattr(mon, "types", None) or []):
            if t: out.append(getattr(t, "name", str(t)))
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
        return str(getattr(mon, "ability", "") or "").lower()

    @staticmethod
    def item(mon) -> str:
        return str(getattr(mon, "item", "") or "").lower()

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
        return ("Flying" in Core.types(mon)) or (Core.ability(mon) == "levitate")

    @staticmethod
    def grounded(mon) -> bool:
        return not Core.has_ground_immunity(mon)

    @staticmethod
    def has_boots(mon) -> bool:
        return "boots" in Core.item(mon)

    @staticmethod
    def type_eff(atk_type: Optional[str], def_types: List[str], defender=None) -> float:
        if not atk_type: return 1.0
        atk_type = getattr(atk_type, "name", atk_type)
        if atk_type == "Ground" and defender is not None and Core.has_ground_immunity(defender):
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
        mtype = getattr(move, "type", None); mtype = getattr(mtype, "name", mtype)
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
            mult = Core.type_eff("Rock", Core.types(cand), defender=cand)
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
        if Core.has_boots(cand) or not grounded or "Steel" in types:
            return {"poison": False, "toxic": False, "absorb": False}
        if "Poison" in types:
            return {"poison": False, "toxic": False, "absorb": True}
        return {"poison": layers == 1, "toxic": layers >= 2, "absorb": False}

# ===== Known movekits for YOUR team (used before moves are revealed) =====
TEAM_KNOWN_MOVES: Dict[str, List[Tuple[str,int,str]]] = {
    "clodsire":        [("Ground", 100, "phys")],
    "giratina-origin": [("Ghost", 110, "phys"), ("Dragon", 60, "phys")],
    "ho-oh":           [("Fire", 100, "phys"), ("Flying", 120, "phys")],
    "dondozo":         [("Water", 85, "phys")],
    "arceus-fairy":    [("Fairy", 100, "spec"), ("Ground", 90, "spec")],
    "eternatus":       [("Fire", 90, "spec"), ("Dragon", 60, "phys")],
}
USER_TYPES = {
    "clodsire": {"Ground","Poison"},
    "giratina-origin": {"Ghost","Dragon"},
    "ho-oh": {"Fire","Flying"},
    "dondozo": {"Water"},
    "arceus-fairy": {"Fairy"},
    "eternatus": {"Poison","Dragon"},
}
def _species_key(p) -> str:
    return (getattr(p, "species", "") or "").lower()

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
                t = getattr(mv, "type", None); t = getattr(t, "name", t)
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
        if "Poison" in Core.types(cand) and ("Fairy" in self._opp_attacking_types(opp)):
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
            mtype = getattr(mv, "type", None); mtype = getattr(mtype, "name", mtype)
            eff = Core.type_eff(mtype, Core.types(opp), defender=opp)
            if d > score + DAMAGE_TIE_EPS or (abs(d - score) <= DAMAGE_TIE_EPS and eff > best_eff):
                best, score, best_eff = mv, d, eff
        return best, max(0.0, score)

    def _maybe_hazards_or_utility(self, battle, me, opp):
        if getattr(me, "status", "") == "slp":
            st = self._move(battle, "sleeptalk")
            if st: return st
        if "clodsire" in (getattr(me, "species","") or "").lower():
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                hz = self._move(battle, "haze")
                if hz: return hz
            sp = self._move(battle, "spikes")
            if sp:
                opp_sc = battle.opponent_side_conditions or {}
                layers = int(opp_sc.get(SideCondition.SPIKES, 0) or 0)
                if layers < 3 and Core.hp(me) >= 0.70 and self._worst_expected_hit(me, opp) < 0.25:
                    return sp
        if "giratina" in (getattr(me, "species","") or "").lower():
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                dt = self._move(battle, "dragontail")
                if dt and self._worst_expected_hit(me, opp) < Core.hp(me) - 0.05:
                    return dt
        if "ho-oh" in (getattr(me, "species","") or "").lower():
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                ww = self._move(battle, "whirlwind")
                if ww and self._worst_expected_hit(me, opp) < Core.hp(me) - 0.05:
                    return ww
        if "dondozo" in (getattr(me, "species","") or "").lower():
            rst = self._move(battle, "rest")
            if rst and (Core.hp(me) <= 0.45 or self._worst_expected_hit(me, opp) >= Core.hp(me)):
                return rst
        return None

    def _get_heal_move(self, battle):
        # include common heals; you can add more like 'synthesis','morningSun','shoreup' if you use them
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
            # Enforce heal under 40%: if we can survive to benefit, do it (even if we could KO)
            if heal_mv.id == "rest" or heals_out:
                return self.create_order(heal_mv)
            # If healing won't save us, we'll prefer a safer switch next.

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

        # Regular heal if still valuable (keeps you out of 2HKO range, etc.)
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
            ("Earthquake", "Ground", 100, "phys", "clodsire"),
            ("Poltergeist", "Ghost", 110, "phys", "giratina-origin"),
            ("Dragon Tail (Gira-O)", "Dragon", 60, "phys", "giratina-origin"),
            ("Sacred Fire", "Fire", 100, "phys", "ho-oh"),
            ("Brave Bird", "Flying", 120, "phys", "ho-oh"),
            ("Liquidation", "Water", 85, "phys", "dondozo"),
            ("Judgment (Fairy)", "Fairy", 100, "spec", "arceus-fairy"),
            ("Earth Power", "Ground", 90, "spec", "arceus-fairy"),
            ("Flamethrower", "Fire", 90, "spec", "eternatus"),
            ("Dragon Tail (Eternatus)", "Dragon", 60, "phys", "eternatus"),
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
