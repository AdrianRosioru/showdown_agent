from typing import List

from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.battle.double_battle import DoubleBattle
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.pokemon import Pokemon
from poke_env.battle.side_condition import SideCondition
from poke_env.player.player import Player


team = """
Deoxys-Speed @ Focus Sash  
Ability: Pressure  
Tera Type: Ghost  
EVs: 248 HP / 8 SpA / 252 Spe  
Timid Nature  
IVs: 0 Atk  
- Thunder Wave  
- Spikes  
- Taunt  
- Psycho Boost  

Kingambit @ Dread Plate  
Ability: Supreme Overlord  
Tera Type: Dark  
EVs: 56 HP / 252 Atk / 200 Spe  
Adamant Nature  
- Swords Dance  
- Kowtow Cleave  
- Iron Head  
- Sucker Punch  

Zacian-Crowned @ Rusted Sword  
Ability: Intrepid Sword  
Tera Type: Flying  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Swords Dance  
- Behemoth Blade  
- Close Combat  
- Wild Charge  

Arceus-Fairy @ Pixie Plate  
Ability: Multitype  
Tera Type: Fire  
EVs: 248 HP / 72 Def / 188 Spe  
Bold Nature  
IVs: 0 Atk  
- Calm Mind  
- Judgment  
- Taunt  
- Recover  

Eternatus @ Power Herb  
Ability: Pressure  
Tera Type: Fire  
EVs: 124 HP / 252 SpA / 132 Spe  
Modest Nature  
IVs: 0 Atk  
- Agility  
- Meteor Beam  
- Dynamax Cannon  
- Fire Blast  

Koraidon @ Life Orb  
Ability: Orichalcum Pulse  
Tera Type: Fire  
EVs: 8 HP / 248 Atk / 252 Spe  
Jolly Nature  
- Swords Dance  
- Scale Shot  
- Flame Charge  
- Close Combat  
"""


class CustomAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)

    # Always lead in order 6 -> 1..5
    def teampreview(self, battle: AbstractBattle) -> str:
        return "/team 612345"

    # --- generic config (no species) ---
    ENTRY_HAZARDS = {
        "spikes": SideCondition.SPIKES,
        "stealthrock": SideCondition.STEALTH_ROCK,
        "stickyweb": SideCondition.STICKY_WEB,
        "toxicspikes": SideCondition.TOXIC_SPIKES,
    }
    ANTI_HAZARDS_MOVES = {"rapidspin", "defog", "mortalspin"}
    HEAL_MOVES = {"recover", "roost", "softboiled", "slackoff", "morningsun", "synthesis", "wish", "rest"}
    PHASE_MOVES = {"haze", "clearsmog", "roar", "whirlwind", "dragontail", "circlethrow"}
    SPEED_BOOST_MOVES = {"agility", "rockpolish", "flamecharge", "autotomize"}
    OFFENSE_BOOST_MOVES = {"swordsdance", "nastyplot", "calmmind", "dragondance", "workup", "quiverdance", "coil", "bulkup"}
    STATUS_MOVES = {"thunderwave", "willowisp", "toxic"}
    TWO_TURN_NUKES = {"meteorbeam"}  # extendable, kept minimal

    SPEED_TIER_COEFICIENT = 0.1
    HP_FRACTION_COEFICIENT = 0.4
    SWITCH_OUT_MATCHUP_THRESHOLD = -2

    # --------------- helpers (all generic) ----------------
    def _estimate_matchup(self, mon: Pokemon, opponent: Pokemon):
        our_eff = max([opponent.damage_multiplier(t) for t in (mon.types or []) if t is not None], default=1.0)
        their_eff = max([mon.damage_multiplier(t) for t in (opponent.types or []) if t is not None], default=1.0)
        score = our_eff - their_eff
        if mon.base_stats["spe"] > opponent.base_stats["spe"]:
            score += self.SPEED_TIER_COEFICIENT
        elif opponent.base_stats["spe"] > mon.base_stats["spe"]:
            score -= self.SPEED_TIER_COEFICIENT
        score += (mon.current_hp_fraction or 0) * self.HP_FRACTION_COEFICIENT
        score -= (opponent.current_hp_fraction or 0) * self.HP_FRACTION_COEFICIENT
        return score

    def _should_dynamax(self, battle: AbstractBattle, n_remaining_mons: int):
        if battle.can_dynamax:
            solo_full_hp = len([m for m in battle.team.values() if m.current_hp_fraction == 1]) == 1
            if solo_full_hp and battle.active_pokemon.current_hp_fraction == 1:
                return True
            if self._estimate_matchup(battle.active_pokemon, battle.opponent_active_pokemon) > 0 \
               and battle.active_pokemon.current_hp_fraction == 1 \
               and battle.opponent_active_pokemon.current_hp_fraction == 1:
                return True
            if n_remaining_mons == 1:
                return True
        return False

    def _should_switch_out(self, battle: AbstractBattle):
        active = battle.active_pokemon
        opponent = battle.opponent_active_pokemon
        if [
            m for m in (battle.available_switches or [])
            if self._estimate_matchup(m, opponent) > 0
        ]:
            if active.boosts["def"] <= -3 or active.boosts["spd"] <= -3:
                return True
            if active.boosts["atk"] <= -3 and active.stats["atk"] >= active.stats["spa"]:
                return True
            if active.boosts["spa"] <= -3 and active.stats["atk"] <= active.stats["spa"]:
                return True
            if self._estimate_matchup(active, opponent) < self.SWITCH_OUT_MATCHUP_THRESHOLD:
                return True
        return False

    def _stat_estimation(self, mon: Pokemon, stat: str):
        b = mon.boosts[stat]
        boost = (2 + b) / 2 if b >= 0 else 2 / (2 - b)
        return ((2 * mon.base_stats[stat] + 31) + 5) * boost

    def _have_hazards_our_side(self, battle: AbstractBattle) -> bool:
        sc = battle.side_conditions or {}
        return any(k in sc for k in (
            SideCondition.STEALTH_ROCK, SideCondition.SPIKES,
            SideCondition.STICKY_WEB, SideCondition.TOXIC_SPIKES
        ))

    def _opp_boost_sum(self, opp: Pokemon) -> int:
        b = getattr(opp, "boosts", {}) or {}
        return sum(max(0, v) for v in b.values())

    def _is_early_game(self, battle: AbstractBattle) -> bool:
        turn = getattr(battle, "turn", None)
        try:
            return turn is not None and int(turn) <= 3
        except Exception:
            return False

    # --- scoring for damage moves
    def _move_score(self, m, active: Pokemon, opponent: Pokemon, physical_ratio: float, special_ratio: float) -> float:
        priority_bonus = 1.05 if getattr(m, "priority", 0) > 0 else 1.0
        return (
            (m.base_power or 0)
            * (1.5 if (m.type in (active.types or []) if m.type is not None else False) else 1.0)
            * (physical_ratio if m.category == MoveCategory.PHYSICAL else special_ratio)
            * (m.accuracy if m.accuracy is not None else 1.0)
            * (getattr(m, "expected_hits", 1) or 1)
            * ((opponent.damage_multiplier(m.type) if m.type is not None else 1.0))
            * priority_bonus
        )

    def _best_damage_move(self, battle: AbstractBattle, active: Pokemon, opponent: Pokemon,
                          physical_ratio: float, special_ratio: float):
        if not (battle.available_moves or []):
            return None
        return max(
            battle.available_moves,
            key=lambda m: self._move_score(m, active, opponent, physical_ratio, special_ratio)
        )

    # --------------- generic tactical nudges (no names) ---------------
    def _utility_lead_play(self, battle: AbstractBattle):
        """Early generic line: TWave if slower foe, Taunt if faster than foe, else hazards (respect stacking)."""
        if not self._is_early_game(battle):
            return None
        moves = {m.id: m for m in (battle.available_moves or [])}
        has_hazard = any(mid in moves for mid in self.ENTRY_HAZARDS)
        has_taunt = "taunt" in moves
        has_twave = "thunderwave" in moves
        if not (has_hazard or has_taunt or has_twave):
            return None

        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        faster_opp = opp.base_stats["spe"] > me.base_stats["spe"]

        # Thunder Wave only when it can hit (no Ground/Electric immunity via typing)
        if faster_opp and has_twave:
            try:
                immune = (opp.damage_multiplier("Electric") == 0)
            except Exception:
                immune = False
            if not immune:
                return moves["thunderwave"]

        if has_taunt and (not faster_opp):
            return moves["taunt"]

        # Hazards with stacking limits
        opp_layers = battle.opponent_side_conditions or {}
        for mid, sc in self.ENTRY_HAZARDS.items():
            m = moves.get(mid)
            if not m:
                continue
            cur = int(opp_layers.get(sc, 0) or 0)
            if (sc == SideCondition.SPIKES and cur < 3) or \
               (sc == SideCondition.TOXIC_SPIKES and cur < 2) or \
               (sc in (SideCondition.STEALTH_ROCK, SideCondition.STICKY_WEB) and cur == 0):
                return m
        return None

    def _anti_boost(self, battle: AbstractBattle):
        """If opponent is boosted, use Haze/Clear Smog; else Roar/Whirlwind/DT/CT with basic immunity checks."""
        opp = battle.opponent_active_pokemon
        if self._opp_boost_sum(opp) <= 0:
            return None
        moves = {m.id: m for m in (battle.available_moves or [])}
        for mid in ("haze", "clearsmog"):
            if mid in moves:
                return moves[mid]
        for mid in ("roar", "whirlwind"):
            if mid in moves:
                return moves[mid]
        if "dragontail" in moves and "Fairy" not in (opp.types or []):
            return moves["dragontail"]
        if "circlethrow" in moves and "Ghost" not in (opp.types or []):
            return moves["circlethrow"]
        return None

    def _healing_gate(self, battle: AbstractBattle):
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        if me.current_hp_fraction is None:
            return None
        moves = {m.id: m for m in (battle.available_moves or [])}
        # Rest at very low HP; other heals at ~50%+neutral matchup
        if me.current_hp_fraction <= 0.35 and "rest" in moves:
            return moves["rest"]
        if me.current_hp_fraction <= 0.5 and self._estimate_matchup(me, opp) > -0.5:
            for mid in self.HEAL_MOVES:
                if mid in moves and mid != "rest":
                    return moves[mid]
        # Sleep Talk if sleeping
        if getattr(me, "status", None) == "SLP" and "sleeptalk" in moves:
            return moves["sleeptalk"]
        return None

    def _status_spread(self, battle: AbstractBattle):
        """Use TWave/WoW/Toxic under simple, type-safe rules when damage is poor."""
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        moves = {m.id: m for m in (battle.available_moves or [])}
        if not any(mid in moves for mid in self.STATUS_MOVES):
            return None

        # If we already threaten decent damage, skip status
        phys = self._stat_estimation(me, "atk") / max(1.0, self._stat_estimation(opp, "def"))
        spec = self._stat_estimation(me, "spa") / max(1.0, self._stat_estimation(opp, "spd"))
        best = self._best_damage_move(battle, me, opp, phys, spec)
        if best and self._move_score(best, me, opp, phys, spec) >= 90:
            return None

        # Paralyze when it hits
        if "thunderwave" in moves:
            try:
                immune = (opp.damage_multiplier("Electric") == 0)
            except Exception:
                immune = False
            if not immune:
                return moves["thunderwave"]

        # Burn likely physical threats (atk > spa) and not Fire-type (basic immunity)
        if "willowisp" in moves:
            if (opp.base_stats.get("atk", 0) > opp.base_stats.get("spa", 0)) and ("Fire" not in (opp.types or [])):
                return moves["willowisp"]

        # Toxic if target is not Steel/Poison
        if "toxic" in moves and ("Steel" not in (opp.types or []) and "Poison" not in (opp.types or [])):
            return moves["toxic"]

        return None

    def _speed_boost_gate(self, battle: AbstractBattle, physical_ratio: float, special_ratio: float):
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        moves = {m.id: m for m in (battle.available_moves or [])}
        if me.current_hp_fraction and me.current_hp_fraction >= 0.8 and self._estimate_matchup(me, opp) >= 0:
            if opp.base_stats["spe"] >= me.base_stats["spe"]:
                best = self._best_damage_move(battle, me, opp, physical_ratio, special_ratio)
                if not best or self._move_score(best, me, opp, physical_ratio, special_ratio) < 120:
                    for mid in self.SPEED_BOOST_MOVES:
                        if mid in moves:
                            return moves[mid]
        return None

    def _offense_boost_gate(self, battle: AbstractBattle, physical_ratio: float, special_ratio: float):
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        moves = {m.id: m for m in (battle.available_moves or [])}
        if me.current_hp_fraction and me.current_hp_fraction >= 0.8 and self._estimate_matchup(me, opp) >= 0.1:
            best = self._best_damage_move(battle, me, opp, physical_ratio, special_ratio)
            if not best or self._move_score(best, me, opp, physical_ratio, special_ratio) < 120:
                for mid in self.OFFENSE_BOOST_MOVES:
                    if mid in moves:
                        return moves[mid]
        return None

    def _two_turn_nuke_gate(self, battle: AbstractBattle, physical_ratio: float, special_ratio: float):
        """Use simple guard for common charge moves (e.g., Meteor Beam) when it's near best."""
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        moves = {m.id: m for m in (battle.available_moves or [])}
        for mid in self.TWO_TURN_NUKES:
            if mid in moves:
                nuke = moves[mid]
                # Prefer if it's close to our best immediate damage and we're healthy
                if (me.current_hp_fraction or 0) >= 0.8:
                    nuke_score = self._move_score(nuke, me, opp, physical_ratio, special_ratio)
                    best_other = max(
                        (self._move_score(m, me, opp, physical_ratio, special_ratio)
                         for m in (battle.available_moves or []) if m is not nuke),
                        default=0.0
                    )
                    if nuke_score >= best_other * 0.9:
                        return nuke
        return None

    def _priority_window(self, battle: AbstractBattle, physical_ratio: float, special_ratio: float):
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        prios = [m for m in (battle.available_moves or []) if getattr(m, "priority", 0) > 0]
        if not prios:
            return None
        slower = opp.base_stats.get("spe", 0) > me.base_stats.get("spe", 0)
        if not slower and (opp.current_hp_fraction or 1.0) > 0.35:
            return None
        best_p = max(prios, key=lambda m: self._move_score(m, me, opp, physical_ratio, special_ratio))
        best_n = self._best_damage_move(battle, me, opp, physical_ratio, special_ratio)
        if not best_n:
            return best_p
        if self._move_score(best_p, me, opp, physical_ratio, special_ratio) >= \
           self._move_score(best_n, me, opp, physical_ratio, special_ratio) * 0.92 \
           or (opp.current_hp_fraction or 1.0) <= 0.35:
            return best_p
        return None

    def _hazard_move_if_useful(self, battle: AbstractBattle):
        opp_layers = battle.opponent_side_conditions or {}
        opp_remaining = 6 - len([m for m in battle.opponent_team.values() if m.fainted])
        if opp_remaining < 3:
            return None
        for move in (battle.available_moves or []):
            sc = self.ENTRY_HAZARDS.get(move.id)
            if not sc:
                continue
            cur = int(opp_layers.get(sc, 0) or 0)
            if (sc == SideCondition.SPIKES and cur < 3) or \
               (sc == SideCondition.TOXIC_SPIKES and cur < 2) or \
               (sc in (SideCondition.STEALTH_ROCK, SideCondition.STICKY_WEB) and cur == 0):
                return move
        return None

    # ---------------- main policy ----------------
    def choose_move(self, battle: AbstractBattle):
        if isinstance(battle, DoubleBattle):
            return self.choose_random_doubles_move(battle)

        active = battle.active_pokemon
        opponent = battle.opponent_active_pokemon
        if active is None or opponent is None:
            return self.choose_random_move(battle)

        physical_ratio = self._stat_estimation(active, "atk") / max(1.0, self._stat_estimation(opponent, "def"))
        special_ratio  = self._stat_estimation(active, "spa") / max(1.0, self._stat_estimation(opponent, "spd"))

        # If we can attack (or must, because no good switch)
        if battle.available_moves and (not self._should_switch_out(battle) or not battle.available_switches):
            n_remaining_mons = len([m for m in battle.team.values() if not m.fainted])

            # 1) Early, simple utility line
            mv = self._utility_lead_play(battle)
            if mv: return self.create_order(mv)

            # 2) Anti-boost if needed
            mv = self._anti_boost(battle)
            if mv: return self.create_order(mv)

            # 3) Hazards (layer-aware)
            mv = self._hazard_move_if_useful(battle)
            if mv: return self.create_order(mv)

            # 4) Clear hazards only if we have them and we still have resources
            if self._have_hazards_our_side(battle) and n_remaining_mons >= 2:
                for move in (battle.available_moves or []):
                    if move.id in self.ANTI_HAZARDS_MOVES:
                        return self.create_order(move)

            # 5) Heal if safe/needed
            mv = self._healing_gate(battle)
            if mv: return self.create_order(mv)

            # 6) Status spread (type-safe) when damage is poor
            mv = self._status_spread(battle)
            if mv: return self.create_order(mv)

            # 7) Generic setup (speed then offense)
            mv = self._speed_boost_gate(battle, physical_ratio, special_ratio)
            if mv: return self.create_order(mv)
            mv = self._offense_boost_gate(battle, physical_ratio, special_ratio)
            if mv: return self.create_order(mv)

            # 8) Two-turn nuke (e.g., Meteor Beam) when near-best
            mv = self._two_turn_nuke_gate(battle, physical_ratio, special_ratio)
            if mv: return self.create_order(mv)

            # 9) Priority window to finish or cover speed deficit
            mv = self._priority_window(battle, physical_ratio, special_ratio)
            if mv: return self.create_order(mv)

            # 10) Default: best damage
            best = self._best_damage_move(battle, active, opponent, physical_ratio, special_ratio)
            if best:
                return self.create_order(best, dynamax=self._should_dynamax(battle, n_remaining_mons))

        # Otherwise: pivot to the best matchup
        if battle.available_switches:
            switches: List[Pokemon] = battle.available_switches
            return self.create_order(max(switches, key=lambda s: self._estimate_matchup(s, opponent)))

        return self.choose_random_move(battle)
