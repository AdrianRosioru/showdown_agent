from poke_env.battle import AbstractBattle
from poke_env.player import Player
from typing import Dict, List, Tuple, Optional

team = """
Ting-Lu @ Leftovers
Ability: Vessel of Ruin
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Stealth Rock
- Spikes
- Ruination
- Whirlwind

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

Eternatus @ Power Herb
Ability: Pressure
Tera Type: Dark
EVs: 248 HP / 8 SpA / 252 Spe
Timid Nature
- Cosmic Power
- Meteor Beam
- Dragon Tail
- Recover

"""

class CustomAgent(Player):
    # --- THREAT BOOK (extendable) ---
    # Preferred switch order is left->right. We pick the first healthy, available one.
    THREAT_SWITCH: Dict[str, List[str]] = {
        # Leads / hazards
        "Deoxys-Speed": ["Giratina"],

        # Physical breakers / setup
        "Zacian-Crowned": ["Dondozo", "Ho-Oh", "Giratina"],
        "Koraidon": ["Arceus-Fairy", "Ho-Oh", "Dondozo"],
        "Kingambit": ["Giratina", "Dondozo", "Ho-Oh"],
        "Rayquaza": ["Dondozo", "Ho-Oh", "Giratina"],

        # Special breakers / setup
        "Kyogre": ["Eternatus", "Arceus-Fairy", "Ho-Oh"],
        "Eternatus": ["Ho-Oh", "Giratina", "Eternatus"],  # we have phaze on all three

        # Bulky CM / Taunt users
        "Arceus-Fairy": ["Ting-Lu", "Ho-Oh", "Giratina"],

        # Utility / misc (safe defaults)
        "Groudon": ["Ho-Oh", "Giratina", "Arceus-Fairy"],
    }

    # Threats that imply immediate pressure -> avoid hazards/greed while they’re up
    HIGH_PRESSURE: Tuple[str, ...] = (
        "Zacian-Crowned", "Koraidon", "Kingambit", "Kyogre", "Eternatus", "Rayquaza"
    )

    # Common type → likely species (optional: used as a fallback heuristic)
    TYPE_POOLS: Dict[str, Tuple[str, ...]] = {
        "Fairy": ("Zacian-Crowned", "Arceus-Fairy"),
        "Dragon": ("Koraidon", "Rayquaza", "Eternatus"),
        "Dark": ("Kingambit",),
        "Water": ("Kyogre",),
        "Ground": ("Groudon",),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)

    # --- helpers ---
    def _move(self, battle: AbstractBattle, move_id: str):
        for m in (battle.available_moves or []):
            if m.id == move_id:
                return m
        return None

    def _hp(self, mon) -> float:
        return (getattr(mon, "current_hp_fraction", 0.0) or 0.0)

    def _opp_species(self, battle: AbstractBattle) -> str:
        o = battle.opponent_active_pokemon
        return (o.species or "") if o else ""

    def _is_pressure_turn(self, battle: AbstractBattle) -> bool:
        # pressure if foe is boosted OR a known high-pressure species is up
        opp = battle.opponent_active_pokemon
        if opp and getattr(opp, "boosts", None):
            if any(v > 0 for v in opp.boosts.values()):
                return True
        name = self._opp_species(battle)
        return any(t in name for t in self.HIGH_PRESSURE)

    def _bench_has(self, battle: AbstractBattle, name: str) -> Optional[object]:
        for p in (battle.available_switches or []):
            if name.lower() in (p.species or "").lower():
                return p
        return None

    def _preferred_switch(self, battle: AbstractBattle) -> Optional[object]:
        name = self._opp_species(battle)
        for key, prefs in self.THREAT_SWITCH.items():
            if key.lower() in name.lower():
                for cand in prefs:
                    sw = self._bench_has(battle, cand)
                    if sw and self._hp(sw) >= 0.4:
                        return sw
        return None

    def _best_attack(self, battle: AbstractBattle):
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon
        moves = battle.available_moves or []
        if not me or not opp or not moves:
            return None

        # stat bias: prefer our higher attacking stat
        atk_bias = 1.1 if (me.stats.get("atk", 0) >= me.stats.get("spa", 0)) else 1.0
        spa_bias = 1.1 if (me.stats.get("spa", 0) >  me.stats.get("atk", 0)) else 1.0

        def score(m):
            bp = (m.base_power or 0)
            if bp == 0:
                return 0  # status moves handled elsewhere
            # STAB
            stab = 1.2 if (m.type and me.types and m.type in me.types) else 1.0
            # Type effectiveness using poke-env’s multiplier
            try:
                eff = opp.damage_multiplier(m)
            except Exception:
                eff = 1.0
            # Accuracy & multi-hit expectation
            acc = (m.accuracy or 100) / 100.0
            hits = getattr(m, "expected_hits", 1) or 1
            # Category bias
            cat_bias = atk_bias if m.category.name == "PHYSICAL" else spa_bias
            return bp * stab * eff * acc * hits * cat_bias

        return max(moves, key=score)

    def _has_hazards_self(self, battle: AbstractBattle) -> bool:
        sc = battle.side_conditions or {}
        return any(k in sc for k in ("stealthrock", "spikes", "toxicspikes", "stickyweb"))

    def _has_hazards_opp(self, battle: AbstractBattle) -> bool:
        sc = battle.opponent_side_conditions or {}
        return any(k in sc for k in ("stealthrock", "spikes", "toxicspikes", "stickyweb"))

    # --- core policy ---
    def choose_move(self, battle: AbstractBattle):
        me  = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        if not me or not opp:
            return self.choose_random_move(battle)

        # 0) FORCED SWITCH — pick a designated check first, else healthiest
        fs = getattr(battle, "force_switch", False)
        is_forced = bool(fs if isinstance(fs, bool) else any(fs))
        if is_forced:
            switches = battle.available_switches or []
            if switches:
                pref = self._preferred_switch(battle)
                if pref:
                    return self.create_order(pref)
                return self.create_order(max(switches, key=lambda p: self._hp(p)))
            return self.choose_random_move(battle)

        # 1) EMERGENCY ACTIONS
        # 1a) If foe is boosted and we have phaze, do it immediately
        if opp and getattr(opp, "boosts", None) and any(v > 0 for v in opp.boosts.values()):
            ww = self._move(battle, "whirlwind")
            dt = self._move(battle, "dragontail")
            if ww: return self.create_order(ww)
            if dt: return self.create_order(dt)

        # 1b) Healing (Recover/Rest/Sleep Talk)
        recover = self._move(battle, "recover")
        rest    = self._move(battle, "rest")
        talk    = self._move(battle, "sleeptalk")
        if getattr(me, "status", None) == "SLP" and talk:
            return self.create_order(talk)
        if recover and self._hp(me) <= 0.45 and not self._is_pressure_turn(battle):
            return self.create_order(recover)
        if rest and self._hp(me) <= 0.35:
            return self.create_order(rest)

        # 2) DON’T TANK A BREAKER — pivot to the right check if we’re not it
        if self._is_pressure_turn(battle):
            # If we aren't the preferred check and a good switch exists, do it
            pref = self._preferred_switch(battle)
            if pref and (pref.species not in (me.species or "")):
                return self.create_order(pref)

        # 3) UTILITY (safe only)
        # 3a) Giratina-O: Defog our hazards when not under pressure
        if "Giratina" in (me.species or "") and self._has_hazards_self(battle) and not self._is_pressure_turn(battle):
            d = self._move(battle, "defog")
            if d: return self.create_order(d)
        # 3b) Giratina-O: Burn physicals by default if no Fire typing
        if "Giratina" in (me.species or ""):
            wisp = self._move(battle, "willowisp")
            if wisp and opp and opp.status is None and (not opp.types or "Fire" not in opp.types):
                return self.create_order(wisp)

        # 4) HAZARDS (only when not under pressure)
        if "Ting-Lu" in (me.species or "") and not self._is_pressure_turn(battle):
            rocks  = self._move(battle, "stealthrock")
            spikes = self._move(battle, "spikes")
            if rocks and "stealthrock" not in (battle.opponent_side_conditions or {}):
                return self.create_order(rocks)
            if spikes and "spikes" not in (battle.opponent_side_conditions or {}):
                return self.create_order(spikes)
            ruin = self._move(battle, "ruination")
            if ruin: return self.create_order(ruin)

        # 5) CONTROLLED SCALING (late/safe)
        # Don’t boost into Taunt/Blade/Beam; only when healthy and not under pressure.
        if not self._is_pressure_turn(battle) and self._hp(me) >= 0.6:
            if "Arceus-Fairy" in (me.species or ""):
                cm = self._move(battle, "calmmind")
                # avoid boosting into obvious Steel/Poison resist if we can just hit
                if cm and not (opp.types and (("Steel" in opp.types) or ("Poison" in opp.types))):
                    return self.create_order(cm)
            if "Eternatus" in (me.species or ""):
                cp = self._move(battle, "cosmicpower")
                if cp: return self.create_order(cp)

        # 6) ATTACK DEFAULT (simple robust scoring)
        atk = self._best_attack(battle)
        if atk:
            return self.create_order(atk)

        # 7) LAST-RESORT PIVOT
        if battle.available_switches and self._hp(me) < 0.3:
            return self.create_order(max(battle.available_switches, key=lambda p: self._hp(p)))

        return self.choose_random_move(battle)