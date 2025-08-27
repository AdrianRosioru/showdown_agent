from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.battle.side_condition import SideCondition
from typing import Dict, List, Tuple, Optional

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

class CustomAgent(Player):
    # ------------ settings ------------
    STATIC_LEAD_NAME: Optional[str] = "Clodsire"

    # Reordered: NEVER mirror their Eternatus if it’s boosting
    THREAT_SWITCH: Dict[str, List[str]] = {
        "Deoxys-Speed":   ["Giratina"],
        "Zacian-Crowned": ["Dondozo", "Ho-Oh", "Giratina"],
        "Koraidon":       ["Arceus", "Ho-Oh", "Dondozo"],
        "Kingambit":      ["Giratina", "Dondozo", "Ho-Oh"],
        "Rayquaza":       ["Dondozo", "Ho-Oh", "Giratina"],
        "Kyogre":         ["Eternatus", "Arceus", "Ho-Oh"],
        "Eternatus":      ["Clodsire", "Giratina", "Arceus", "Eternatus"],  # <-- changed
        "Arceus-Fairy":   ["Clodsire", "Ho-Oh", "Giratina"],
        "Groudon":        ["Ho-Oh", "Giratina", "Arceus"],
    }

    HIGH_PRESSURE: Tuple[str, ...] = (
        "Zacian-Crowned", "Koraidon", "Kingambit", "Kyogre", "Eternatus", "Rayquaza"
    )

    SWITCH_COOLDOWN_TURNS = 1
    EMERGENCY_SPA = 1
    EMERGENCY_SPE = 1

    LEAD_PRIORITY = ["Clodsire", "Giratina", "Dondozo", "Arceus", "Eternatus", "Ho-Oh"]

    # ------------ lifecycle hooks ------------
    def teampreview(self, battle):
        mons = list(battle.team.values())
        if not mons:
            return None
        desired = []
        if self.STATIC_LEAD_NAME:
            for i, mon in enumerate(mons):
                if mon and self.STATIC_LEAD_NAME.lower() in (mon.species or "").lower():
                    desired.append(i); break
        if not desired:
            for want in self.LEAD_PRIORITY:
                for i, mon in enumerate(mons):
                    if i in desired or not mon: continue
                    if want.lower() in (mon.species or "").lower():
                        desired.append(i); break
        for i in range(len(mons)):
            if i not in desired: desired.append(i)
        return "/team " + "".join(str(i + 1) for i in desired)

    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)
        self._last_switch_turn: Dict[str, int] = {}

    # ------------ helpers ------------
    def _move(self, battle: AbstractBattle, move_id: str):
        for m in (battle.available_moves or []):
            if m.id == move_id: return m
        return None

    def _hp(self, mon) -> float:
        return float(getattr(mon, "current_hp_fraction", 0.0) or 0.0)

    def _turn(self, battle: AbstractBattle) -> int:
        return int(getattr(battle, "turn", 0) or 0)

    def _opp(self, battle): return battle.opponent_active_pokemon
    def _me(self, battle):  return battle.active_pokemon

    def _opp_name(self, battle) -> str:
        o = self._opp(battle); return (o.species or "") if o else ""

    def _opp_tag(self, battle) -> str:
        o = self._opp(battle)
        if not o: return ""
        name = (o.species or "")
        if "Arceus" in name and o.types and ("Fairy" in o.types): return "Arceus-Fairy"
        return name

    def _opp_team_has(self, battle: AbstractBattle, name: str) -> bool:
        for p in (battle.opponent_team or {}).values():
            if p and name.lower() in (p.species or "").lower(): return True
        return False

    def _is_pressure_turn(self, battle: AbstractBattle) -> bool:
        o = self._opp(battle)
        if o and getattr(o, "boosts", None) and any(v > 0 for v in o.boosts.values()):
            return True
        return any(tag in self._opp_name(battle) for tag in self.HIGH_PRESSURE)

    def _bench_has(self, battle: AbstractBattle, name: str):
        for p in (battle.available_switches or []):
            if name.lower() in (p.species or "").lower(): return p
        return None

    def _preferred_lead(self, battle: AbstractBattle):
        if self.STATIC_LEAD_NAME:
            lead = self._bench_has(battle, self.STATIC_LEAD_NAME)
            if lead: return lead
        if self._opp_team_has(battle, "Deoxys-Speed"):   return self._bench_has(battle, "Giratina")
        if self._opp_team_has(battle, "Kyogre"):         return self._bench_has(battle, "Eternatus")
        if self._opp_team_has(battle, "Eternatus"):      return self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Eternatus")
        if self._opp_team_has(battle, "Zacian-Crowned"): return self._bench_has(battle, "Dondozo")
        if self._opp_team_has(battle, "Koraidon"):       return self._bench_has(battle, "Arceus")
        return self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Giratina")

    def _preferred_switch(self, battle: AbstractBattle):
        tag = self._opp_tag(battle)
        # Special guard: never switch our Eternatus into theirs if they have SpA boosts
        if tag == "Eternatus":
            o = self._opp(battle)
            boosted = bool(o and getattr(o, "boosts", None) and o.boosts.get("spa", 0) > 0)
            order = ["Clodsire", "Giratina", "Arceus"] + ([] if boosted else ["Eternatus"])
            for cand in order:
                sw = self._bench_has(battle, cand)
                if sw and self._hp(sw) >= 0.4:
                    return sw
        # Default table
        table = self.THREAT_SWITCH.get(tag)
        if table:
            for cand in table:
                sw = self._bench_has(battle, cand)
                if sw and self._hp(sw) >= 0.4:
                    return sw
        # Fallback by fuzzy match
        for key, prefs in self.THREAT_SWITCH.items():
            if key.lower() in self._opp_name(battle).lower():
                for cand in prefs:
                    sw = self._bench_has(battle, cand)
                    if sw and self._hp(sw) >= 0.4:
                        return sw
        return None

    def _best_attack(self, battle: AbstractBattle):
        me = self._me(battle); opp = self._opp(battle)
        moves = battle.available_moves or []
        if not me or not opp or not moves: return None
        atk_bias = 1.1 if me.stats.get("atk",0) >= me.stats.get("spa",0) else 1.0
        spa_bias = 1.1 if me.stats.get("spa",0) >  me.stats.get("atk",0) else 1.0
        def score(m):
            bp = m.base_power or 0
            if bp == 0: return 0
            stab = 1.2 if (m.type and me.types and m.type in me.types) else 1.0
            try: eff = opp.damage_multiplier(m)
            except Exception: eff = 1.0
            acc  = (m.accuracy or 100)/100.0
            hits = getattr(m, "expected_hits", 1) or 1
            catb = atk_bias if getattr(m, "category", None) and getattr(m.category, "name", "") == "PHYSICAL" else spa_bias
            return bp*stab*eff*acc*hits*catb
        return max(moves, key=score)

    def _matchup_score(self, me, opp) -> float:
        if not me or not opp: return 0.0
        try:
            our_types   = [t for t in (me.types or []) if t is not None]
            their_types = [t for t in (opp.types or []) if t is not None]
            our_eff   = max((opp.damage_multiplier(t) for t in our_types), default=1.0)
            their_eff = max((me.damage_multiplier(t) for t in their_types), default=1.0)
        except Exception:
            our_eff, their_eff = 1.0, 1.0
        spd =  0.1 if me.base_stats.get("spe",0) >  opp.base_stats.get("spe",0) else \
              (-0.1 if me.base_stats.get("spe",0) <  opp.base_stats.get("spe",0) else 0.0)
        hp_term = (self._hp(me) - self._hp(opp)) * 0.3
        return (our_eff - their_eff) + spd + hp_term

    def _has_hazards_self(self, battle: AbstractBattle) -> bool:
        sc = battle.side_conditions or {}
        return any(k in sc for k in (SideCondition.STEALTH_ROCK, SideCondition.SPIKES,
                                     SideCondition.TOXIC_SPIKES, SideCondition.STICKY_WEB))

    def _has_hazards_opp(self, battle: AbstractBattle) -> bool:
        sc = battle.opponent_side_conditions or {}
        return any(k in sc for k in (SideCondition.STEALTH_ROCK, SideCondition.SPIKES,
                                     SideCondition.TOXIC_SPIKES, SideCondition.STICKY_WEB))

    def _hazard_chip_estimate(self, battle: AbstractBattle, target=None) -> float:
        # basic, boots-aware
        try:
            if ((getattr(target, "item", "") or "").lower() == "heavydutyboots"):
                return 0.0
        except Exception:
            pass
        sc = battle.side_conditions or {}
        chip = 0.0
        if SideCondition.STEALTH_ROCK in sc: chip += 0.125
        spikes_layers = int(sc.get(SideCondition.SPIKES, 0) or 0)
        chip += min(0.25, 0.125 * spikes_layers)
        return chip

    def _note_switch(self, battle: AbstractBattle):
        self._last_switch_turn[battle.battle_tag] = self._turn(battle)

    def _can_switch_now(self, battle: AbstractBattle, emergency: bool=False) -> bool:
        if emergency: return True
        last = self._last_switch_turn.get(battle.battle_tag, -999)
        return (self._turn(battle) - last) > self.SWITCH_COOLDOWN_TURNS

    def _pick_replacement(self, battle: AbstractBattle):
        # On replacements, always try named counter first
        pref = self._preferred_switch(battle)
        if pref: return pref
        # Generic fallback by matchup + HP
        opp = self._opp(battle)
        cands = battle.available_switches or []
        if not cands: return None
        def ms(p): return self._matchup_score(p, opp) + self._hp(p) * 0.25
        return max(cands, key=ms)

    # ------------ policy ------------
    def choose_move(self, battle: AbstractBattle):
        me, opp = self._me(battle), self._opp(battle)

        # Forced switch: turn-0 lead AND post-KO replacements
        fs = getattr(battle, "force_switch", False)
        if bool(fs if isinstance(fs, bool) else any(fs)):
            # If preview sometimes isn’t honored, enforce our desired lead here too
            if (not opp or not (opp.species or "")):
                lead = self._preferred_lead(battle)
                if lead: self._note_switch(battle); return self.create_order(lead)
            pick = self._pick_replacement(battle)
            if pick: self._note_switch(battle); return self.create_order(pick)
            return self.choose_random_move(battle)

        if not me or not opp:
            return self.choose_random_move(battle)

        # A) Do NOT keep Ho-Oh in vs Eternatus (Power Herb Meteor Beam risk)
        if "Eternatus" in self._opp_name(battle) and "Ho-Oh" in (me.species or ""):
            pref = self._preferred_switch(battle)
            if pref and self._can_switch_now(battle, emergency=True):
                self._note_switch(battle)
                return self.create_order(pref)

        # B) Emergency vs boosts (Eternatus CM/Meteor Beam; CM Arceus, etc.)
        opp_boosted = any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values())
        if opp_boosted:
            # Highest priority: Clodsire Haze
            if "Clodsire" in (me.species or ""):
                hz = self._move(battle, "haze")
                if hz: return self.create_order(hz)
            # Then phaze (Dragon Tail preferred)
            dt = self._move(battle, "dragontail")
            if dt: return self.create_order(dt)
            ww = self._move(battle, "whirlwind")
            if ww and "Eternatus" not in self._opp_name(battle):
                return self.create_order(ww)
            # Last resort: hard switch to the proper check even if we just switched
            pref = self._preferred_switch(battle)
            if pref and self._can_switch_now(battle, emergency=True):
                self._note_switch(battle)
                return self.create_order(pref)

        # C) HAZARD CONTROL — Defog ASAP when safe (fixes the replay spiral)
        if "Giratina" in (me.species or "") and self._has_hazards_self(battle):
            # Safe if foe is Deoxys-S or anything that’s unlikely to 2HKO us now
            safe = ("Deoxys" in self._opp_name(battle)) or (self._hp(me) >= 0.5 and not self._is_pressure_turn(battle))
            if safe:
                df = self._move(battle, "defog")
                if df: return self.create_order(df)

        # D) Healing (avoid when a named breaker is in)
        if not self._is_pressure_turn(battle):
            rec = self._move(battle, "recover")
            if rec and self._hp(me) <= 0.45: return self.create_order(rec)
        if self._move(battle, "rest") and self._hp(me) <= 0.35:
            return self.create_order(self._move(battle, "rest"))
        if getattr(me, "status", None) == "SLP" and self._move(battle, "sleeptalk"):
            return self.create_order(self._move(battle, "sleeptalk"))

        # E) Threat-driven pivot (but avoid chip-wasting ping-pong)
        if self._is_pressure_turn(battle):
            pref = self._preferred_switch(battle)
            if pref and (pref.species not in (me.species or "")) and self._can_switch_now(battle, emergency=False):
                # If switching into Clodsire would take big hazard chip and it isn’t emergency,
                # prefer to make progress instead of bouncing.
                if "Clodsire" in (pref.species or "") and self._hazard_chip_estimate(battle, pref) >= 0.125:
                    # Try phaze / attack instead
                    dt = self._move(battle, "dragontail")
                    if dt: return self.create_order(dt)
                self._note_switch(battle)
                return self.create_order(pref)

        # F) Utility: burn physicals when not Fire, once hazards are handled
        if "Giratina" in (me.species or "") and (not self._has_hazards_self(battle)):
            w = self._move(battle, "willowisp")
            if w and opp and opp.status is None and (not opp.types or "Fire" not in opp.types):
                return self.create_order(w)

        # G) Hazards when safe (Clodsire)
        if "Clodsire" in (me.species or "") and not self._is_pressure_turn(battle):
            s = self._move(battle, "spikes")
            if s and not self._has_hazards_opp(battle): return self.create_order(s)
            eq = self._move(battle, "earthquake")
            if eq: return self.create_order(eq)

        # H) Controlled scaling (late/safe only)
        if not self._is_pressure_turn(battle) and self._hp(me) >= 0.6:
            if "Arceus" in (me.species or ""):
                cm = self._move(battle, "calmmind")
                if cm and not (opp.types and (("Steel" in opp.types) or ("Poison" in opp.types))):
                    return self.create_order(cm)
            if "Eternatus" in (me.species or ""):
                cp = self._move(battle, "cosmicpower")
                if cp: return self.create_order(cp)

        # I) Default: click our best attack
        atk = self._best_attack(battle)
        if atk: return self.create_order(atk)

        # J) Last resort: bail out if we’re losing the matchup hard
        cur = self._matchup_score(me, opp)
        if battle.available_switches and (self._hp(me) < 0.3 or cur <= -1.0) and self._can_switch_now(battle, emergency=(cur<=-1.0)):
            pick = self._pick_replacement(battle)
            if pick: self._note_switch(battle); return self.create_order(pick)

        return self.choose_random_move(battle)
