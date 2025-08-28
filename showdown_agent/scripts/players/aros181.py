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
    """V6.4 – Eternatus lead + matchup-aware Eternatus turns

    - Force Eternatus lead
    - Eternatus checks matchup first (Koraidon/Zacian/Groudon/etc.) before acting
    - Safe Cosmic Power gate for Eternatus
    - Keep switch damping (matchup gain – hazard chip) to avoid ping-pong
    """

    # ------------ settings ------------
    STATIC_LEAD_NAME: Optional[str] = "Eternatus"  # lead with Eternatus

    THREAT_SWITCH: Dict[str, List[str]] = {
        "Deoxys-Speed":   ["Giratina"],
        "Zacian-Crowned": ["Dondozo", "Ho-Oh", "Giratina"],
        "Zacian":         ["Dondozo", "Ho-Oh", "Giratina"],
        "Koraidon":       ["Arceus", "Ho-Oh", "Dondozo"],
        "Kingambit":      ["Giratina", "Dondozo", "Ho-Oh"],
        "Rayquaza":       ["Dondozo", "Ho-Oh", "Giratina"],
        "Kyogre":         ["Eternatus", "Arceus", "Ho-Oh"],
        "Eternatus":      ["Clodsire", "Arceus", "Eternatus"],
        "Arceus-Fairy":   ["Clodsire", "Ho-Oh", "Giratina"],
        "Groudon":        ["Ho-Oh", "Giratina", "Arceus"],
    }

    HIGH_PRESSURE: Tuple[str, ...] = (
        "Zacian-Crowned", "Zacian", "Koraidon", "Kingambit", "Kyogre", "Eternatus", "Rayquaza"
    )

    SWITCH_COOLDOWN_TURNS = 1
    LEAD_PRIORITY = ["Eternatus", "Clodsire", "Giratina", "Dondozo", "Arceus", "Ho-Oh"]

    # ------------ lifecycle hooks ------------
    def teampreview(self, battle):
        mons = list(battle.team.values())
        if not mons:
            return None

        try:
            opp_has = [p.species or "" for p in (battle.opponent_team or {}).values() if p]

            def idx(name: str):
                for i, m in enumerate(mons):
                    if m and name.lower() in (m.species or "").lower():
                        return i
                return None

            # keep your smart cases; static lead still enforced below
            if any("koraidon" in n.lower() for n in opp_has):
                ai = idx("Arceus")
                if ai is not None:
                    desired = [ai] + [i for i in range(len(mons)) if i != ai]
                    return "/team " + "".join(str(i + 1) for i in desired)
            if any("zacian" in n.lower() for n in opp_has) or any("kingambit" in n.lower() for n in opp_has):
                di = idx("Dondozo")
                if di is not None:
                    desired = [di] + [i for i in range(len(mons)) if i != di]
                    return "/team " + "".join(str(i + 1) for i in desired)
        except Exception:
            pass

        desired = []
        if self.STATIC_LEAD_NAME:
            for i, mon in enumerate(mons):
                if mon and self.STATIC_LEAD_NAME.lower() in (mon.species or "").lower():
                    desired.append(i)
                    break
        if not desired:
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

    # ------------ helpers ------------
    def _move(self, battle: AbstractBattle, move_id: str):
        for m in (battle.available_moves or []):
            if m.id == move_id:
                return m
        return None

    def _hp(self, mon) -> float:
        return float(getattr(mon, "current_hp_fraction", 0.0) or 0.0)

    def _turn(self, battle: AbstractBattle) -> int:
        return int(getattr(battle, "turn", 0) or 0)

    def _opp(self, battle):
        return battle.opponent_active_pokemon

    def _me(self, battle):
        return battle.active_pokemon

    def _opp_name(self, battle) -> str:
        o = self._opp(battle)
        return (o.species or "") if o else ""

    def _opp_tag(self, battle) -> str:
        o = self._opp(battle)
        if not o:
            return ""
        name = (o.species or "")
        if "Arceus" in name and o.types and ("Fairy" in o.types):
            return "Arceus-Fairy"
        if "Zacian" in name:
            return "Zacian-Crowned" if "Crowned" in name else "Zacian"
        if "Deoxys" in name and "Speed" in name:
            return "Deoxys-Speed"
        return name

    def _opp_has_type(self, battle: AbstractBattle, type_name: str) -> bool:
        o = self._opp(battle)
        try:
            return bool(o and o.types and type_name in o.types)
        except Exception:
            return False

    def _opp_team_has(self, battle: AbstractBattle, name: str) -> bool:
        for p in (battle.opponent_team or {}).values():
            if p and name.lower() in (p.species or "").lower():
                return True
        return False

    def _is_pressure_turn(self, battle: AbstractBattle) -> bool:
        o = self._opp(battle)
        if o and getattr(o, "boosts", None) and any(v > 0 for v in o.boosts.values()):
            return True
        return False  # presence alone doesn't force pivots

    def _bench_has(self, battle: AbstractBattle, name: str):
        for p in (battle.available_switches or []):
            if name.lower() in (p.species or "").lower():
                return p
        return None

    def _preferred_lead(self, battle: AbstractBattle):
        if self.STATIC_LEAD_NAME:
            lead = self._bench_has(battle, self.STATIC_LEAD_NAME)
            if lead:
                return lead
        if self._opp_team_has(battle, "Deoxys-Speed"):
            return self._bench_has(battle, "Giratina")
        if self._opp_team_has(battle, "Kyogre"):
            return self._bench_has(battle, "Eternatus")
        if self._opp_team_has(battle, "Eternatus"):
            return self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Eternatus")
        if self._opp_team_has(battle, "Zacian") or self._opp_team_has(battle, "Zacian-Crowned"):
            return self._bench_has(battle, "Dondozo")
        if self._opp_team_has(battle, "Koraidon"):
            return self._bench_has(battle, "Arceus")
        return self._bench_has(battle, "Eternatus") or self._bench_has(battle, "Clodsire")

    def _preferred_switch(self, battle: AbstractBattle):
        tag = self._opp_tag(battle)
        if tag == "Eternatus":
            o = self._opp(battle)
            boosted = bool(o and getattr(o, "boosts", None) and o.boosts.get("spa", 0) > 0)
            order = ["Clodsire", "Giratina", "Arceus"] + ([] if boosted else ["Eternatus"])
            for cand in order:
                sw = self._bench_has(battle, cand)
                if sw and self._hp(sw) >= 0.4:
                    return sw
        table = self.THREAT_SWITCH.get(tag)
        if table:
            for cand in table:
                sw = self._bench_has(battle, cand)
                if sw and self._hp(sw) >= 0.4:
                    return sw
        oname = self._opp_name(battle).lower()
        for key, prefs in self.THREAT_SWITCH.items():
            if key.lower() in oname:
                for cand in prefs:
                    sw = self._bench_has(battle, cand)
                    if sw and self._hp(sw) >= 0.4:
                        return sw
        return None

    def _best_attack(self, battle: AbstractBattle):
        me = self._me(battle)
        opp = self._opp(battle)
        moves = battle.available_moves or []
        if not me or not opp or not moves:
            return None
        if "Giratina" in (me.species or "") and "Kingambit" in (opp.species or ""):
            moves = [m for m in moves if m.id != "poltergeist"] or moves
        atk_bias = 1.1 if me.stats.get("atk", 0) >= me.stats.get("spa", 0) else 1.0
        spa_bias = 1.1 if me.stats.get("spa", 0) > me.stats.get("atk", 0) else 1.0

        def score(m):
            bp = m.base_power or 0
            if bp == 0:
                return 0
            stab = 1.2 if (m.type and me.types and m.type in me.types) else 1.0
            try:
                eff = opp.damage_multiplier(m)
            except Exception:
                eff = 1.0
            acc = (m.accuracy or 100) / 100.0
            hits = getattr(m, "expected_hits", 1) or 1
            catb = atk_bias if getattr(m, "category", None) and getattr(m.category, "name", "") == "PHYSICAL" else spa_bias
            return bp * stab * eff * acc * hits * catb

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
        spd = 0.1 if me.base_stats.get("spe", 0) > opp.base_stats.get("spe", 0) else (-0.1 if me.base_stats.get("spe", 0) < opp.base_stats.get("spe", 0) else 0.0)
        hp_term = (self._hp(me) - self._hp(opp)) * 0.3
        return (our_eff - their_eff) + spd + hp_term

    def _has_hazards_self(self, battle: AbstractBattle) -> bool:
        sc = battle.side_conditions or {}
        return any(k in sc for k in (SideCondition.STEALTH_ROCK, SideCondition.SPIKES, SideCondition.TOXIC_SPIKES, SideCondition.STICKY_WEB))

    def _has_hazards_opp(self, battle: AbstractBattle) -> bool:
        sc = battle.opponent_side_conditions or {}
        return any(k in sc for k in (SideCondition.STEALTH_ROCK, SideCondition.SPIKES, SideCondition.TOXIC_SPIKES, SideCondition.STICKY_WEB))

    def _hazard_chip_estimate(self, battle: AbstractBattle, target=None) -> float:
        try:
            if ((getattr(target, "item", "") or "").lower() == "heavydutyboots"):
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

    # --- switch damping: only switch if real gain exceeds hazard cost
    def _switch_gain(self, battle: AbstractBattle, candidate) -> float:
        me, opp = self._me(battle), self._opp(battle)
        if not me or not opp or not candidate:
            return -999.0
        gain = (self._matchup_score(candidate, opp) - self._matchup_score(me, opp))
        gain -= self._hazard_chip_estimate(battle, candidate)
        return gain

    def _note_switch(self, battle: AbstractBattle):
        self._last_switch_turn[battle.battle_tag] = self._turn(battle)

    def _can_switch_now(self, battle: AbstractBattle, emergency: bool = False) -> bool:
        if emergency:
            return True
        last = self._last_switch_turn.get(battle.battle_tag, -999)
        return (self._turn(battle) - last) > self.SWITCH_COOLDOWN_TURNS

    def _pick_replacement(self, battle: AbstractBattle):
        pref = self._preferred_switch(battle)
        if pref:
            return pref
        opp = self._opp(battle)
        cands = battle.available_switches or []
        if not cands:
            return None

        def ms(p):
            return self._matchup_score(p, opp) + self._hp(p) * 0.25

        return max(cands, key=ms)

    # --- new: Eternatus setup safety gate
    def _eternatus_setup_safe(self, battle: AbstractBattle) -> bool:
        """Only allow Cosmic Power if opp likely can't punish immediately."""
        opp = self._opp(battle)
        if not opp:
            return False
        name = (opp.species or "")
        # hard no into these threats/types
        scary_names = ("Koraidon", "Zacian", "Kingambit", "Rayquaza", "Groudon", "Deoxys-Speed")
        if any(s in name for s in scary_names):
            return False
        scary_types = ("Ground", "Psychic", "Ice", "Dragon")
        if any(self._opp_has_type(battle, t) for t in scary_types):
            return False
        # don't try at low HP
        me = self._me(battle)
        return self._hp(me) >= 0.70

    # extra: simple predicate for safe early Spikes (unchanged)
    def _clod_should_spike_now(self, battle: AbstractBattle) -> bool:
        opp = self._opp(battle)
        me = self._me(battle)
        if not opp or not me:
            return False
        if self._has_hazards_opp(battle):
            return False
        if self._is_pressure_turn(battle):
            return False
        tag = self._opp_tag(battle)
        safe_targets = {"Arceus-Fairy", "Groudon", "Kingambit"}
        return tag in safe_targets and self._hp(me) >= 0.6

    # ------------ policy ------------
    def choose_move(self, battle: AbstractBattle):
        me, opp = self._me(battle), self._opp(battle)

        # Forced switch: lead / post-KO
        fs = getattr(battle, "force_switch", False)
        if bool(fs if isinstance(fs, bool) else any(fs)):
            if (not opp or not (opp.species or "")):
                lead = self._preferred_lead(battle)
                if lead:
                    self._note_switch(battle)
                    return self.create_order(lead)
            pick = self._pick_replacement(battle)
            if pick:
                self._note_switch(battle)
                return self.create_order(pick)
            return self.choose_random_move(battle)

        if not me or not opp:
            return self.choose_random_move(battle)

        oname = self._opp_name(battle)
        me_name = (me.species or "")

        # --- NEW: Eternatus field logic happens first (no blind fighting)
        if "Eternatus" in me_name:
            # 1) immediate threat-specific pivots (gated by real gain)
            if "Koraidon" in oname:
                sw = self._bench_has(battle, "Arceus")
                if sw and self._switch_gain(battle, sw) > 0.25:
                    self._note_switch(battle); return self.create_order(sw)
            if "Zacian" in oname:
                sw = self._bench_has(battle, "Dondozo") or self._bench_has(battle, "Ho-Oh")
                if sw and self._switch_gain(battle, sw) > 0.25:
                    self._note_switch(battle); return self.create_order(sw)
            if "Groudon" in oname:
                sw = self._bench_has(battle, "Ho-Oh") or self._bench_has(battle, "Giratina")
                if sw and self._switch_gain(battle, sw) > 0.20:
                    self._note_switch(battle); return self.create_order(sw)
            if "Rayquaza" in oname:
                sw = self._bench_has(battle, "Dondozo") or self._bench_has(battle, "Ho-Oh")
                if sw and self._switch_gain(battle, sw) > 0.20:
                    self._note_switch(battle); return self.create_order(sw)
            if "Kingambit" in oname:
                # If healthy, we can Flamethrower; otherwise pivot to Giratina
                ft = self._move(battle, "flamethrower")
                if self._hp(me) >= 0.70 and ft:
                    return self.create_order(ft)
                sw = self._bench_has(battle, "Giratina") or self._bench_has(battle, "Dondozo")
                if sw and self._switch_gain(battle, sw) > 0.15:
                    self._note_switch(battle); return self.create_order(sw)
            if "Arceus-Fairy" in oname:
                sw = self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Ho-Oh")
                if sw and self._switch_gain(battle, sw) > 0.15:
                    self._note_switch(battle); return self.create_order(sw)
            if "Deoxys-Speed" in oname:
                sw = self._bench_has(battle, "Giratina")
                if sw and self._switch_gain(battle, sw) > 0.20:
                    self._note_switch(battle); return self.create_order(sw)

            # 2) mirrors & Eternatus checks
            if "Eternatus" in oname:
                dt = self._move(battle, "dragontail")
                if dt and not self._opp_has_type(battle, "Fairy"):
                    return self.create_order(dt)
                sw = self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Giratina")
                if sw and self._switch_gain(battle, sw) > 0.10:
                    self._note_switch(battle); return self.create_order(sw)

            # 3) safe setup or proactive phazing
            if self._eternatus_setup_safe(battle):
                cp = self._move(battle, "cosmicpower")
                if cp: return self.create_order(cp)

            # 4) default Eternatus actions: DT vs boosters / Flamethrower chip / Recover
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                dt = self._move(battle, "dragontail")
                if dt and not self._opp_has_type(battle, "Fairy"):
                    return self.create_order(dt)
            rec = self._move(battle, "recover")
            if rec and self._hp(me) <= 0.50:
                return self.create_order(rec)
            ft = self._move(battle, "flamethrower")
            if ft:
                return self.create_order(ft)
            # fallthrough to general logic if nothing above fired

        # -------- existing logic below --------

        # 0) Hard counters & critical patterns (tempered by switch_gain in our Eternatus section already)
        if "Deoxys-Speed" in oname and "Giratina" not in me_name:
            sw = self._bench_has(battle, "Giratina")
            if sw and self._switch_gain(battle, sw) > 0.20:
                self._note_switch(battle)
                return self.create_order(sw)

        if "Kingambit" in oname:
            if "Giratina" in me_name:
                w = self._move(battle, "willowisp")
                if w and opp and opp.status is None and (not opp.types or "Fire" not in opp.types):
                    return self.create_order(w)
                dt = self._move(battle, "dragontail")
                if dt:
                    return self.create_order(dt)
            if "Arceus" in me_name:
                ep = self._move(battle, "earthpower")
                if ep:
                    return self.create_order(ep)
            pref = self._preferred_switch(battle)
            if pref and self._switch_gain(battle, pref) > 0.35:
                self._note_switch(battle)
                return self.create_order(pref)

        if ("Zacian" in oname) and ("Ho-Oh" in me_name):
            sf = self._move(battle, "sacredfire") or self._move(battle, "bravebird")
            if sf:
                return self.create_order(sf)

        if "Eternatus" in oname and "Ho-Oh" in me_name:
            pref = self._preferred_switch(battle)
            if not pref:
                for name in ("Clodsire", "Giratina", "Arceus", "Dondozo"):
                    sw = self._bench_has(battle, name)
                    if sw: pref = sw; break
            if pref and self._switch_gain(battle, pref) > 0.25:
                self._note_switch(battle)
                return self.create_order(pref)

        if "Koraidon" in oname and "Arceus" not in me_name:
            sw = self._bench_has(battle, "Arceus")
            if sw and self._switch_gain(battle, sw) > 0.25:
                self._note_switch(battle)
                return self.create_order(sw)

        if ("Zacian" in oname) and ("Dondozo" in me_name):
            r = self._move(battle, "rest")
            if r and self._hp(me) <= 0.62:
                return self.create_order(r)

        if "Eternatus" in oname and "Arceus" in me_name:
            pref = self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Giratina")
            if pref and self._switch_gain(battle, pref) > 0.15:
                self._note_switch(battle)
                return self.create_order(pref)

        if "Eternatus" in oname and "Clodsire" in me_name:
            hz = self._move(battle, "haze")
            eq = self._move(battle, "earthquake")
            if any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values()):
                if hz: return self.create_order(hz)
            if eq: return self.create_order(eq)

        if "Koraidon" in oname and "Arceus" in me_name:
            rec = self._move(battle, "recover")
            if rec and self._hp(me) <= 0.60:
                return self.create_order(rec)
            jd = self._move(battle, "judgment")
            if jd:
                return self.create_order(jd)

        # 1) Emergency vs boosts
        opp_boosted = any(v > 0 for v in (getattr(opp, "boosts", {}) or {}).values())
        if opp_boosted:
            if self._opp_has_type(battle, "Fairy"):
                if "Giratina" in me_name:
                    w = self._move(battle, "willowisp")
                    if w and opp and opp.status is None and (not opp.types or "Fire" not in opp.types):
                        return self.create_order(w)
                    polt = self._move(battle, "poltergeist")
                    if polt:
                        return self.create_order(polt)
                if "Clodsire" in me_name:
                    hz = self._move(battle, "haze")
                    if hz:
                        return self.create_order(hz)
                pref = self._bench_has(battle, "Clodsire") or self._bench_has(battle, "Arceus") or self._preferred_switch(battle)
                if pref and self._switch_gain(battle, pref) > -0.1:
                    self._note_switch(battle)
                    return self.create_order(pref)
            if "Clodsire" in me_name:
                hz = self._move(battle, "haze")
                if hz:
                    return self.create_order(hz)
            dt = self._move(battle, "dragontail")
            if dt and not self._opp_has_type(battle, "Fairy"):
                return self.create_order(dt)
            ww = self._move(battle, "whirlwind")
            if ww and "Eternatus" not in oname:
                return self.create_order(ww)
            pref = self._preferred_switch(battle)
            if pref and self._switch_gain(battle, pref) > 0.0:
                self._note_switch(battle)
                return self.create_order(pref)

        # 2) Hazard control — Defog with Giratina if we have hazards
        if "Giratina" in me_name and self._has_hazards_self(battle):
            df = self._move(battle, "defog")
            if df and self._hp(me) >= 0.4:
                return self.create_order(df)

        # 3) Proactive phazing vs Eternatus (if not handled above)
        if "Eternatus" in oname:
            dt = self._move(battle, "dragontail")
            ww = self._move(battle, "whirlwind")
            if dt and not self._opp_has_type(battle, "Fairy"):
                return self.create_order(dt)
            if ww:
                return self.create_order(ww)

        # 4) Healing
        if not self._is_pressure_turn(battle):
            rec = self._move(battle, "recover")
            if rec and self._hp(me) <= 0.50:
                return self.create_order(rec)
        if self._move(battle, "rest") and self._hp(me) <= 0.45:
            return self.create_order(self._move(battle, "rest"))
        if getattr(me, "status", None) == "SLP" and self._move(battle, "sleeptalk"):
            return self.create_order(self._move(battle, "sleeptalk"))

        # 5) Clodsire – safe early Spikes
        if "Clodsire" in me_name and self._clod_should_spike_now(battle):
            s = self._move(battle, "spikes")
            if s:
                return self.create_order(s)

        # 6) Optional pivot if gain justifies it
        pref = self._preferred_switch(battle)
        if pref and ((pref.species or "") != (me.species or "")) and self._switch_gain(battle, pref) > 0.35:
            self._note_switch(battle)
            return self.create_order(pref)

        # 7) Utility: burn physicals after hazards handled
        if "Giratina" in me_name and (not self._has_hazards_self(battle)):
            w = self._move(battle, "willowisp")
            if w and opp and opp.status is None and (not opp.types or "Fire" not in opp.types):
                return self.create_order(w)

        # 8) Clodsire default if not spiking
        if "Clodsire" in me_name and not self._is_pressure_turn(battle):
            eq = self._move(battle, "earthquake")
            if eq:
                return self.create_order(eq)

        # 9) Controlled scaling
        if not self._is_pressure_turn(battle) and self._hp(me) >= 0.6:
            if "Arceus" in me_name:
                cm = self._move(battle, "calmmind")
                if cm and not (opp.types and (("Steel" in opp.types) or ("Poison" in opp.types))):
                    return self.create_order(cm)
            if "Eternatus" in me_name:
                cp = self._move(battle, "cosmicpower")
                if cp:
                    return self.create_order(cp)

        # 10) Default: best attack
        atk = self._best_attack(battle)
        if atk:
            return self.create_order(atk)

        # 11) Last resort pivot
        cur = self._matchup_score(me, opp)
        if battle.available_switches and (self._hp(me) < 0.3 or cur <= -1.0):
            pick = self._pick_replacement(battle)
            if pick:
                self._note_switch(battle)
                return self.create_order(pick)

        return self.choose_random_move(battle)
