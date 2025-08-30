from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.battle.side_condition import SideCondition
from typing import Dict, List, Optional
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

# =========================================================
#                     Minimal Core
# =========================================================
class Core:
    # Type chart (immunities included)
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
        # prefer actual stats; fallback to base stats
        if not mon: return 0.0
        v = ((getattr(mon, "stats", {}) or {}).get(key))
        if v is None: v = ((getattr(mon, "base_stats", {}) or {}).get(key, 0))
        return float(v or 0.0)

    @staticmethod
    def ability(mon) -> str:
        return str(getattr(mon, "ability", "") or "").lower()

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
        # Natural Flying type or Levitate ability
        return ("Flying" in Core.types(mon)) or (Core.ability(mon) == "levitate")

    @staticmethod
    def type_eff(atk_type: Optional[str], def_types: List[str], defender=None) -> float:
        """Type effectiveness, honoring Levitate/Flying vs Ground."""
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
        """Very simple damage proxy in [0,1]: scales base power, STAB, effectiveness, stats, and accuracy."""
        if not attacker or not defender or not move or not Core.is_damaging(move):
            return 0.0

        bp = float(getattr(move, "base_power", 0) or 0)
        if bp <= 0: return 0.0

        atk_is_phys = Core.is_physical(move)
        atk_stat = Core.stat(attacker, "atk" if atk_is_phys else "spa")
        def_stat = Core.stat(defender, "def" if atk_is_phys else "spd")

        mtype = getattr(move, "type", None); mtype = getattr(mtype, "name", mtype)
        eff = Core.type_eff(mtype, Core.types(defender), defender=defender)
        if eff <= 0.0:
            return 0.0

        stab = 1.5 if (mtype and mtype in Core.types(attacker)) else 1.0
        acc = Core.acc(move)

        # Normalize: 90BP STAB neutral with equal stats ~ 0.45
        stat_ratio = max(0.1, atk_stat / max(1.0, def_stat))
        raw = (bp / 90.0) * 0.45 * stab * eff * stat_ratio * acc
        return float(max(0.0, min(1.0, raw)))

    @staticmethod
    def estimate_threat_fraction(attacker, defender) -> float:
        """If we don't know moves: assume a 90 BP STAB from the better attacking stat."""
        if not attacker or not defender: return 0.0

        # If we know their moves, use them.
        best_seen = 0.0
        for mv in (getattr(attacker, "moves", {}) or {}).values():
            best_seen = max(best_seen, Core.estimate_damage_fraction(attacker, defender, mv))
        if best_seen > 0.0:
            return best_seen

        # Otherwise, assume best STAB hits for 90 BP.
        atk_types = Core.types(attacker)
        def_types = Core.types(defender)
        # Choose phys/special lane by higher base stat
        use_phys = Core.base_stat(attacker, "atk") >= Core.base_stat(attacker, "spa")
        atk_stat = Core.stat(attacker, "atk" if use_phys else "spa")
        def_stat = Core.stat(defender, "def" if use_phys else "spd")
        best_eff = 1.0
        for t in atk_types:
            eff = Core.type_eff(t, def_types, defender=defender)
            best_eff = max(best_eff, eff)
        stat_ratio = max(0.1, atk_stat / max(1.0, def_stat))
        # 90 BP, STAB assumed, best effectiveness
        raw = (90 / 90.0) * 0.45 * 1.5 * best_eff * stat_ratio
        return float(max(0.0, min(1.0, raw)))

# =========================================================
#                   Simple Agent
# =========================================================
class CustomAgent(Player, Core):
    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)

    # --- Helpers
    def _me(self, battle):  return battle.active_pokemon
    def _opp(self, battle): return battle.opponent_active_pokemon

    def _move(self, battle: AbstractBattle, move_id: str):
        for m in (battle.available_moves or []):
            if m.id == move_id:
                return m
        return None

    # NEW: predict opponent lane (physical vs special) for switching logic
    def _predict_lane(self, attacker) -> str:
        atk_b = Core.base_stat(attacker, "atk")
        spa_b = Core.base_stat(attacker, "spa")
        return "phys" if atk_b >= spa_b else "spec"

    # NEW: lane bonus for a candidate into this attacker (prefers Def vs phys, SpD vs spec)
    def _lane_bonus(self, cand, opp) -> float:
        lane = self._predict_lane(opp)
        opp_off = Core.stat(opp, "atk" if lane == "phys" else "spa")
        cand_def = Core.stat(cand, "def" if lane == "phys" else "spd")
        ratio = cand_def / max(1.0, opp_off)
        # scale and clamp
        return max(-0.40, min(0.40, 0.35 * (ratio - 1.0)))

    def _best_damage_move(self, battle, me, opp):
        best, score = None, -1.0
        for mv in (battle.available_moves or []):
            if not Core.is_damaging(mv): 
                continue
            d = Core.estimate_damage_fraction(me, opp, mv)
            # KO nudge
            if d >= Core.hp(opp):
                d += 0.4
            if d > score:
                best, score = mv, d
        return best, max(0.0, score)

    def _should_switch(self, battle, me, opp) -> Optional[object]:
        """Switch if we're hard-losing AND a bench mon clearly improves it (lane-aware)."""
        if not battle.available_switches:
            return None

        # Our pressure vs theirs
        _, my_dmg = self._best_damage_move(battle, me, opp)
        their_dmg = Core.estimate_threat_fraction(opp, me)
        lane_me = self._lane_bonus(me, opp)
        current_score = (my_dmg - their_dmg) + lane_me  # penalize bad lane

        # Evaluate each possible switch
        best_sw, best_gain = None, -1e9
        for sw in battle.available_switches:
            # sw pressure
            sw_dmg = 0.0
            for mv in (getattr(sw, "moves", {}) or {}).values():
                sw_dmg = max(sw_dmg, Core.estimate_damage_fraction(sw, opp, mv))
            if sw_dmg == 0.0:
                # fallback neutral 90BP STAB proxy
                best_eff = 1.0
                for t in Core.types(sw):
                    best_eff = max(best_eff, Core.type_eff(t, Core.types(opp), defender=opp))
                atk_stat = max(Core.stat(sw, "atk"), Core.stat(sw, "spa"))
                def_stat = min(Core.stat(opp, "def"), Core.stat(opp, "spd"))
                sw_dmg = (90/90.0)*0.45*1.5*best_eff*max(0.1, atk_stat/max(1.0, def_stat))
                sw_dmg = float(max(0.0, min(1.0, sw_dmg)))

            opp_vs_sw = Core.estimate_threat_fraction(opp, sw)

            # lane improvement term (prefer SpD into special attackers, etc.)
            lane_sw = self._lane_bonus(sw, opp)

            gain = (sw_dmg - opp_vs_sw) + lane_sw - current_score

            # nudge for true immunities to opponent's STAB types
            if any(Core.type_eff(t, Core.types(sw), defender=sw) == 0.0 for t in Core.types(opp)):
                gain += 0.20

            if gain > best_gain:
                best_sw, best_gain = sw, gain

        # Switch only if there's clear improvement and we're losing or getting chunked
        my_hp = Core.hp(me)
        losing = (their_dmg > my_dmg + 0.15) or (lane_me < -0.12 and their_dmg >= my_hp * 0.45) or (their_dmg >= my_hp * 0.60)
        if best_sw and best_gain > 0.15 and losing:
            return best_sw
        return None

    def _maybe_hazards_or_utility(self, battle, me, opp):
        """Very light utility: Haze vs boosts; Spikes when very safe; Sleep Talk/Rest basics."""
        # Sleep Talk when asleep (Dondozo)
        if getattr(me, "status", "") == "slp":
            st = self._move(battle, "sleeptalk")
            if st: return st

        # Haze if they have positive boosts and we're Clodsire
        if "clodsire" in (getattr(me, "species","") or "").lower():
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                hz = self._move(battle, "haze")
                if hz: return hz

            # Spikes if we're very safe and they have <3 layers
            sp = self._move(battle, "spikes")
            if sp:
                opp_sc = battle.opponent_side_conditions or {}
                layers = int(opp_sc.get(SideCondition.SPIKES, 0) or 0)
                # "very safe": we take small damage this turn
                if layers < 3 and Core.estimate_threat_fraction(opp, me) < 0.25 and Core.hp(me) >= 0.7:
                    return sp

        # Giratina-O: Dragon Tail if they boosted and we likely live
        if "giratina" in (getattr(me, "species","") or "").lower():
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                dt = self._move(battle, "dragontail")
                if dt and Core.estimate_threat_fraction(opp, me) < Core.hp(me) - 0.05:
                    return dt

        # Ho-Oh: Whirlwind if they boosted and we live
        if "ho-oh" in (getattr(me, "species","") or "").lower():
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                ww = self._move(battle, "whirlwind")
                if ww and Core.estimate_threat_fraction(opp, me) < Core.hp(me) - 0.05:
                    return ww

        # Dondozo Rest when low and threatened
        if "dondozo" in (getattr(me, "species","") or "").lower():
            rst = self._move(battle, "rest")
            if rst:
                if Core.hp(me) <= 0.45 or Core.estimate_threat_fraction(opp, me) >= Core.hp(me):
                    return rst

        return None

    # --- Main decision loop
    def choose_move(self, battle: AbstractBattle):
        me, opp = self._me(battle), self._opp(battle)

        # Forced switch (lead or after KO)
        fs = getattr(battle, "force_switch", False)
        need_switch = fs if isinstance(fs, bool) else any(fs)
        if need_switch:
            # Still simple, but lane-aware: pick decent typing + the right bulk
            cands = battle.available_switches or []
            if cands:
                lane = self._predict_lane(opp) if opp else "phys"
                def lead_score(p):
                    eff = 1.0
                    if opp:
                        eff = 1.0 / max(0.25, Core.type_eff(Core.types(opp)[0] if Core.types(opp) else None, Core.types(p), defender=p))
                    bulk_lane = Core.stat(p, "def" if lane == "phys" else "spd") / 200.0
                    bulk_all = (Core.stat(p, "def") + Core.stat(p, "spd")) / 800.0
                    return eff + 0.9*bulk_lane + 0.4*bulk_all
                lead = max(cands, key=lead_score)
                return self.create_order(lead)
            return self.choose_random_move(battle)

        if not me or not opp:
            return self.choose_random_move(battle)

        # --- 0) EMERGENCY HEAL comes first ---
        my_hp = Core.hp(me)
        their_dmg = Core.estimate_threat_fraction(opp, me)
        best_mv, best_dmg = self._best_damage_move(battle, me, opp)

        heal_ids = ("recover","roost","slackoff","moonlight","rest")
        heal_mv = None
        for hid in heal_ids:
            h = self._move(battle, hid)
            if h:
                heal_mv = h
                break
        if heal_mv:
            lethal = their_dmg >= my_hp
            near_lethal = (my_hp <= 0.35) or (their_dmg >= my_hp * 0.85)
            heal_gain = 1.0 if heal_mv.id == "rest" else 0.5
            heals_out = (my_hp + heal_gain) > their_dmg
            # Heal if we're about to die / nearly die AND we don't already have a clean KO
            if (lethal or near_lethal) and heals_out and not (best_mv and best_dmg >= Core.hp(opp)):
                return self.create_order(heal_mv)

        # 1) Consider a survival/utility action (very light)
        util = self._maybe_hazards_or_utility(battle, me, opp)
        if util:
            return self.create_order(util)

        # 2) Clean KO? take it
        if best_mv and best_dmg >= Core.hp(opp):
            return self.create_order(best_mv)

        # 3) If the matchup is bad and a bench mon clearly improves it, switch (now lane-aware)
        sw = self._should_switch(battle, me, opp)
        if sw:
            return self.create_order(sw)

        # 4) Regular heal if it still changes the outcome
        if heal_mv and ((my_hp <= 0.45) or (their_dmg >= my_hp and (my_hp + (1.0 if heal_mv.id == "rest" else 0.5)) > their_dmg)):
            return self.create_order(heal_mv)

        # 5) Otherwise, push best damage.
        if best_mv:
            return self.create_order(best_mv)

        # fallback utilities when no good damage available
        for aux_id in ("willowisp","dragontail","whirlwind","defog","spikes"):
            aux = self._move(battle, aux_id)
            if aux:
                return self.create_order(aux)

        # Absolute fallback
        return self.choose_random_move(battle)
