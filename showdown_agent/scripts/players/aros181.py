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
    # -------- settings --------
    STATIC_LEAD_NAME: Optional[str] = None  # use smart preview-based lead

    # Threat → preferred checks (first healthy one chosen)
    THREAT_SWITCH: Dict[str, List[str]] = {
        "Deoxys-Speed":   ["Giratina"],
        "Zacian-Crowned": ["Dondozo", "Ho-Oh", "Giratina"],
        "Koraidon":       ["Arceus", "Ho-Oh", "Dondozo"],
        "Kingambit":      ["Ho-Oh", "Giratina", "Dondozo"],  # changed: Ho-Oh first
        "Rayquaza":       ["Dondozo", "Ho-Oh", "Giratina"],
        "Kyogre":         ["Eternatus", "Arceus", "Ho-Oh"],
        "Eternatus":      ["Clodsire", "Eternatus", "Arceus", "Giratina"],  # Haze/DT first
        "Arceus-Fairy":   ["Clodsire", "Ho-Oh", "Giratina"],
        "Groudon":        ["Ho-Oh", "Giratina", "Arceus"],
    }

    HIGH_PRESSURE: Tuple[str, ...] = (
        "Zacian-Crowned", "Koraidon", "Kingambit", "Kyogre", "Eternatus", "Rayquaza"
    )

    # switch/emergency tuning
    SWITCH_COOLDOWN_TURNS = 1
    EMERGENCY_SPA = 1      # trigger at +1 (Meteor Beam turn)
    EMERGENCY_SPE = 1

    # team preview priority (fallback)
    LEAD_PRIORITY = ["Ho-Oh", "Giratina", "Clodsire", "Dondozo", "Arceus", "Eternatus"]

    def teampreview(self, battle):
        mons = list(battle.team.values())
        if not mons:
            return None
        desired = []
        if self.STATIC_LEAD_NAME:
            for i, mon in enumerate(mons):
                if mon and self.STATIC_LEAD_NAME.lower() in (mon.species or "").lower():
                    desired.append(i)
                    break
        if not desired:
            # Ho-Oh lead if they show Kingambit
            if self._opp_team_has(battle, "Kingambit"):
                for i, mon in enumerate(mons):
                    if mon and "ho-oh" in (mon.species or "").lower():
                        desired.append(i)
                        break
            # otherwise by LEAD_PRIORITY
            for want in self.LEAD_PRIORITY:
                for i, mon in enumerate(mons):
                    if i in desired or not mon:
                        continue
                    if want.lower() in (mon.species or "").lower():
                        desired.append(i)
                        break
        for i in range(len(mons)):
            if i not in desired:
                desired.append(i)
        return "/team " + "".join(str(i + 1) for i in desired)

    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)
        self._last_switch_turn: Dict[str, int] = {}
        self._last_switch_target: Dict[str, str] = {}

    # -------- helpers --------
    def _move(self, battle: AbstractBattle, move_id: str):
        for m in (battle.available_moves or []):
            if m.id == move_id:
                return m
        return None

    def _hp(self, mon) -> float:
        return (getattr(mon, "current_hp_fraction", 0.0) or 0.0)

    def _turn(self, battle: AbstractBattle) -> int:
        try:
            return int(getattr(battle, "turn", 0))
        except Exception:
            return 0

    def _opp_species_raw(self, battle: AbstractBattle) -> str:
        o = battle.opponent_active_pokemon
        return (o.species or "") if o else ""

    def _opp_tag(self, battle: AbstractBattle) -> str:
        o = battle.opponent_active_pokemon
        if not o:
            return ""
        name = (o.species or "")
        if "Arceus" in name and o.types and ("Fairy" in o.types):
            return "Arceus-Fairy"
        return name

    def _opp_team_has(self, battle: AbstractBattle, name: str) -> bool:
        for p in (battle.opponent_team or {}).values():
            if p and name.lower() in (p.species or "").lower():
                return True
        return False

    def _preferred_lead(self, battle: AbstractBattle):
        # explicit early rules
        if self._opp_team_has(battle, "Kingambit"):     return self._bench_has(battle, "Ho-Oh")
        if self._opp_team_has(battle, "Deoxys-Speed"):  return self._bench_has(battle, "Giratina")
        if self._opp_team_has(battle, "Kyogre"):        return self._bench_has(battle, "Eternatus")
        if self._opp_team_has(battle, "Eternatus"):     return self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Eternatus")
        if self._opp_team_has(battle, "Zacian-Crowned"):return self._bench_has(battle, "Dondozo")
        if self._opp_team_has(battle, "Koraidon"):      return self._bench_has(battle, "Arceus")
        # fallback ordering
        for want in self.LEAD_PRIORITY:
            b = self._bench_has(battle, want)
            if b: return b
        return None

    def _is_pressure_turn(self, battle: AbstractBattle) -> bool:
        o = battle.opponent_active_pokemon
        if o and getattr(o, "boosts", None) and any(v > 0 for v in o.boosts.values()):
            return True
        name = self._opp_species_raw(battle)
        return any(tag in name for tag in self.HIGH_PRESSURE)

    def _bench_has(self, battle: AbstractBattle, name: str):
        for p in (battle.available_switches or []):
            if name.lower() in (p.species or "").lower():
                return p
        return None

    def _preferred_switch(self, battle: AbstractBattle):
        tag = self._opp_tag(battle)
        if tag in self.THREAT_SWITCH:
            for cand in self.THREAT_SWITCH[tag]:
                sw = self._bench_has(battle, cand)
                if sw and self._hp(sw) >= 0.4:
                    return sw
        name = self._opp_species_raw(battle)
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
        atk_bias = 1.1 if me.stats.get("atk",0) >= me.stats.get("spa",0) else 1.0
        spa_bias = 1.1 if me.stats.get("spa",0) >  me.stats.get("atk",0) else 1.0
        def score(m):
            bp = m.base_power or 0
            if bp == 0:
                return 0
            stab = 1.2 if (m.type and me.types and m.type in me.types) else 1.0
            try:
                eff = opp.damage_multiplier(m)
            except Exception:
                eff = 1.0
            acc  = (m.accuracy or 100)/100.0
            hits = getattr(m, "expected_hits", 1) or 1
            catb = atk_bias if getattr(m, "category", None) and getattr(m.category, "name", "") == "PHYSICAL" else spa_bias
            return bp*stab*eff*acc*hits*catb
        return max(moves, key=score)

    def _matchup_score(self, me, opp) -> float:
        if not me or not opp:
            return 0.0
        try:
            our_types = [t for t in (me.types or []) if t is not None]
            their_types = [t for t in (opp.types or []) if t is not None]
            our_eff = max((opp.damage_multiplier(t) for t in our_types), default=1.0)
            their_eff = max((me.damage_multiplier(t) for t in their_types), default=1.0)
        except Exception:
            our_eff, their_eff = 1.0, 1.0
        spd = 0.1 if me.base_stats.get("spe",0) > opp.base_stats.get("spe",0) else (-0.1 if me.base_stats.get("spe",0) < opp.base_stats.get("spe",0) else 0.0)
        hp_term = (self._hp(me) - self._hp(opp)) * 0.3
        return (our_eff - their_eff) + spd + hp_term

    # ---- hazard/switch helpers ----
    def _hazard_chip_estimate(self, battle: AbstractBattle, target=None) -> float:
        # ignore if Heavy-Duty Boots
        try:
            item = (getattr(target, "item", "") or "").lower()
            if item == "heavydutyboots":
                return 0.0
        except Exception:
            pass
        sc = battle.side_conditions or {}
        chip = 0.0
        if SideCondition.STEALTH_ROCK in sc:
            chip += 0.125
        spikes_layers = int(sc.get(SideCondition.SPIKES, 0) or 0)
        chip += min(0.25, 0.125 * spikes_layers)
        return chip

    def _can_switch_now(self, battle: AbstractBattle, emergency: bool=False) -> bool:
        key = battle.battle_tag
        last = self._last_switch_turn.get(key, -999)
        if emergency:
            return True
        return (self._turn(battle) - last) > self.SWITCH_COOLDOWN_TURNS

    def _note_switch(self, battle: AbstractBattle, target_species: str):
        key = battle.battle_tag
        self._last_switch_turn[key] = self._turn(battle)
        self._last_switch_target[key] = target_species or ""

    def _is_emergency_boost(self, opp) -> bool:
        if not opp or not getattr(opp, "boosts", None):
            return False
        return (opp.boosts.get("spa", 0) >= self.EMERGENCY_SPA) or (opp.boosts.get("spe", 0) >= self.EMERGENCY_SPE)

    # ---------- replacement picker (after KOs/phaze) ----------
    def _pick_replacement(self, battle: AbstractBattle):
        pref = self._preferred_switch(battle)
        if pref:
            return pref
        cands = []
        for p in (battle.available_switches or []):
            bad_sleep = (getattr(p, "status", None) == "SLP")
            has_talk = False
            try:
                has_talk = any(m.id == "sleeptalk" for m in (p.moves or {}).values())
            except Exception:
                pass
            if bad_sleep and not has_talk:
                continue
            cands.append(p)
        if not cands:
            cands = battle.available_switches or []
        opp = battle.opponent_active_pokemon
        def ms(p):
            base = self._matchup_score(p, opp)
            return base + self._hp(p) * 0.25
        return max(cands, key=ms) if cands else None

    def _has_hazards_self(self, battle: AbstractBattle) -> bool:
        sc = battle.side_conditions or {}
        return any(k in sc for k in (
            SideCondition.STEALTH_ROCK, SideCondition.SPIKES,
            SideCondition.TOXIC_SPIKES, SideCondition.STICKY_WEB
        ))

    def _has_hazards_opp(self, battle: AbstractBattle) -> bool:
        sc = battle.opponent_side_conditions or {}
        return any(k in sc for k in (
            SideCondition.STEALTH_ROCK, SideCondition.SPIKES,
            SideCondition.TOXIC_SPIKES, SideCondition.STICKY_WEB
        ))

    # -------- policy --------
    def choose_move(self, battle: AbstractBattle):
        me  = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        # Forced switch: covers team preview (no foe yet) AND post-KO replacements.
        fs = getattr(battle, "force_switch", False)
        is_forced = bool(fs if isinstance(fs, bool) else any(fs))
        if is_forced:
            switches = battle.available_switches or []
            if switches:
                if not opp or not (opp.species or ""):
                    lead = self._preferred_lead(battle)
                    if lead:
                        self._note_switch(battle, lead.species or "")
                        return self.create_order(lead)
                pick = self._pick_replacement(battle)
                if pick:
                    self._note_switch(battle, pick.species or "")
                    return self.create_order(pick)
                pick = max(switches, key=lambda p: self._hp(p))
                self._note_switch(battle, pick.species or "")
                return self.create_order(pick)
            return self.choose_random_move(battle)

        if not me or not opp:
            return self.choose_random_move(battle)

        # --- Deoxys-S dedicated handling ---
        if "Deoxys-Speed" in self._opp_species_raw(battle):
            # get to Giratina first
            if "Giratina" not in (me.species or ""):
                pref = self._bench_has(battle, "Giratina")
                if pref:
                    return self.create_order(pref)
            # on Giratina: Defog hazards first
            if "Giratina" in (me.species or "") and self._has_hazards_self(battle):
                d = self._move(battle, "defog")
                if d:
                    return self.create_order(d)
            # remove it with DT (avoids Poltergeist fail edge-cases)
            if "Giratina" in (me.species or ""):
                dt = self._move(battle, "dragontail")
                if dt:
                    return self.create_order(dt)

        # 1) Eternatus safety vs Ho-Oh (avoid WW into Meteor Beam lines)
        if "Eternatus" in self._opp_species_raw(battle) and "Ho-Oh" in (me.species or ""):
            pref = self._preferred_switch(battle)
            if pref and self._can_switch_now(battle, emergency=True):
                self._note_switch(battle, pref.species or "")
                return self.create_order(pref)

        # 2) Boost handling: Haze/DT now; prefer non-Ho-Oh phazers
        opp_boosted = any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values())
        if opp_boosted:
            if "Clodsire" in (me.species or ""):
                hz = self._move(battle, "haze")
                if hz:
                    return self.create_order(hz)
            dt = self._move(battle, "dragontail")
            if dt:
                return self.create_order(dt)
            ww = self._move(battle, "whirlwind")
            if ww and "Eternatus" not in self._opp_species_raw(battle):
                return self.create_order(ww)
            pref = self._preferred_switch(battle)
            if pref and self._can_switch_now(battle, emergency=True):
                self._note_switch(battle, pref.species or "")
                return self.create_order(pref)

        # 3) Healing (avoid under pressure)
        recover = self._move(battle, "recover")
        rest    = self._move(battle, "rest")
        talk    = self._move(battle, "sleeptalk")
        if getattr(me, "status", None) == "SLP" and talk:
            return self.create_order(talk)
        if recover and self._hp(me) <= 0.45 and not self._is_pressure_turn(battle):
            return self.create_order(recover)
        if rest and self._hp(me) <= 0.35:
            return self.create_order(rest)

        # 4) Threat-driven pivot
        if self._is_pressure_turn(battle):
            pref = self._preferred_switch(battle)
            if pref and (pref.species not in (me.species or "")) and self._can_switch_now(battle, emergency=False):
                self._note_switch(battle, pref.species or "")
                return self.create_order(pref)

        # 4.25) General hazard-aware anti-churn gate
        chip_now = self._hazard_chip_estimate(battle)
        cur = self._matchup_score(me, opp)
        if chip_now >= 0.125 and cur > -0.4:
            atk = self._best_attack(battle)
            if atk:
                return self.create_order(atk)

        # 4.5) Anti-bounce specific to Clodsire (use real chip & Boots)
        if battle.available_switches:
            pref = self._preferred_switch(battle)
            if pref and ("Clodsire" in (pref.species or "")):
                chip = self._hazard_chip_estimate(battle, pref)
                if chip >= 0.125 and not self._is_emergency_boost(opp):
                    if "Clodsire" in (me.species or ""):
                        rec = self._move(battle, "recover")
                        if rec and self._hp(me) <= 0.6:
                            return self.create_order(rec)
                        eq = self._move(battle, "earthquake")
                        if eq:
                            return self.create_order(eq)
                    if not self._can_switch_now(battle, emergency=False):
                        dt = self._move(battle, "dragontail")
                        if dt:
                            return self.create_order(dt)
                        ww = self._move(battle, "whirlwind")
                        if ww:
                            return self.create_order(ww)

        # 5) Generic matchup pivot with emergency losing override
        emergency_losing = (cur <= -1.0)
        best_sw, best_sw_score = None, -999
        for p in (battle.available_switches or []):
            s = self._matchup_score(p, opp) + self._hp(p) * 0.25
            if s > best_sw_score:
                best_sw, best_sw_score = p, s
        if best_sw and (emergency_losing or best_sw_score >= cur + 0.5) and self._can_switch_now(battle, emergency=emergency_losing):
            self._note_switch(battle, best_sw.species or "")
            return self.create_order(best_sw)

        # 6) Safe utility
        if "Giratina" in (me.species or "") and self._has_hazards_self(battle) and not self._is_pressure_turn(battle):
            d = self._move(battle, "defog")
            if d:
                return self.create_order(d)
        if "Giratina" in (me.species or ""):
            w = self._move(battle, "willowisp")
            if w and opp and opp.status is None and (not opp.types or "Fire" not in opp.types):
                return self.create_order(w)

        # 7) Hazards when safe (Clodsire)
        if "Clodsire" in (me.species or "") and not self._is_pressure_turn(battle):
            s = self._move(battle, "spikes")
            if s and not self._has_hazards_opp(battle):
                return self.create_order(s)
            eq = self._move(battle, "earthquake")
            if eq:
                return self.create_order(eq)

        # 8) Controlled scaling (late / safe)
        if not self._is_pressure_turn(battle) and self._hp(me) >= 0.6:
            if "Arceus" in (me.species or ""):
                cm = self._move(battle, "calmmind")
                if cm and not (opp.types and (("Steel" in opp.types) or ("Poison" in opp.types))):
                    return self.create_order(cm)
            if "Eternatus" in (me.species or ""):
                cp = self._move(battle, "cosmicpower")
                if cp:
                    return self.create_order(cp)

        # 9) Attack default
        atk = self._best_attack(battle)
        if atk:
            return self.create_order(atk)

        # 10) Last-resort pivot
        if battle.available_switches and self._hp(me) < 0.3 and self._can_switch_now(battle, emergency=False):
            pick = max(battle.available_switches, key=lambda p: self._hp(p))
            self._note_switch(battle, pick.species or "")
            return self.create_order(pick)

        return self.choose_random_move(battle)
