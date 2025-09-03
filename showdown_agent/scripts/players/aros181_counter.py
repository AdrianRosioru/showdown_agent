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
    """V6.5 – unified threat pivot dictionary"""

    # ------------ settings ------------
    STATIC_LEAD_NAME: Optional[str] = "eternatus"  # lead with eternatus

    THREAT_SWITCH: Dict[str, Tuple[str, ...]] = {
        # --- originals ---
        "deoxysspeed":   ("giratina",),
        "zaciancrowned": ("dondozo", "hooh", "giratina"),
        "zacian":        ("dondozo", "hooh", "giratina"),
        "koraidon":      ("arceusfairy", "hooh", "dondozo"),
        "kingambit":     ("giratina", "dondozo", "hooh"),
        "rayquaza":      ("dondozo", "hooh", "giratina"),
        "kyogre":        ("eternatus", "arceusfairy", "hooh"),
        "eternatus":     ("clodsire", "arceusfairy", "eternatus"),
        "arceusfairy":   ("clodsire", "hooh", "giratina"),
        "groudon":       ("hooh", "giratina", "arceusfairy"),

        # --- OU6 adds ---
        "tornadustherian": ("hooh", "eternatus", "arceusfairy"),
        "rotomwash":       ("clodsire", "eternatus", "arceusfairy"),
        "metagross":       ("dondozo", "hooh", "giratina"),
        "cobalion":        ("hooh", "giratina", "dondozo"),
        "zarudedada":      ("hooh", "dondozo", "arceusfairy"),
        "zarude":          ("hooh", "dondozo", "arceusfairy"),
        "clodsire":        ("arceusfairy", "hooh", "giratina"),
    }

    HIGH_PRESSURE: Tuple[str, ...] = (
        "zaciancrowned", "zacian", "koraidon", "kingambit", "eternatus",
    )

    SWITCH_COOLDOWN_TURNS = 1
    LEAD_PRIORITY = ["eternatus", "clodsire", "giratina", "dondozo", "arceusfairy", "hooh"]

    # --- micro-tuning knobs for uber-simple ---
    GENERIC_RECOVER_THRESHOLD = 0.45
    ETERNATUS_CP_MINHP = 0.62
    SECURE_KO_HP = 0.28
    PHYSICAL_THREATS = {
        "zaciancrowned", "koraidon",
        "kingambit",
        "metagross", "cobalion", "zarude", "zarudedada"
    }
    EARLY_SPIKES_TARGETS = {
        "arceusfairy", "groudon", "kingambit", "zaciancrowned",
        "koraidon", "deoxysspeed",
        "tornadustherian", "rotomwash", "cobalion", "metagross", "zarudedada"
    }

    def teampreview(self, battle):
         return "/team 512346"

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

    def _preferred_switch(self, battle: AbstractBattle):
        tag = self._opp_tag(battle)
        if tag == "eternatus":
            o = self._opp(battle)
            boosted = bool(o and getattr(o, "boosts", None) and o.boosts.get("spa", 0) > 0)
            order = ["clodsire", "giratina", "arceusfairy"] + ([] if boosted else ["eternatus"])
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

    def choose_move(self, battle: AbstractBattle):
        me, opp = self._me(battle), self._opp(battle)

        # --- small helpers (local, no deps) ---
        def opp_has_move(mid: str) -> bool:
            try:
                moves = getattr(opp, "moves", {}) or {}
                return (mid in moves) or any(getattr(m, "id", "") == mid for m in moves.values())
            except Exception:
                return False

        def can_use(m_id: str):
            return self._move(battle, m_id)

        def safe_dt():
            """Dragontail that auto-disables into Fairy immunities."""
            m = can_use("dragontail")
            if m and self._opp_has_type(battle, "Fairy"):
                return None
            return m

        def try_switch(order, base_th=0.16):
            # Boosted foe -> lower switching threshold to respond faster
            th = base_th - 0.08 if opp_boosted else base_th
            for name in order:
                sw = self._bench_has(battle, name)
                if sw and self._hp(sw) >= 0.40 and self._switch_gain(battle, sw) > th:
                    self._note_switch(battle)
                    return self.create_order(sw)
            return None

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

        oname = self._opp_name(battle)      # lower + no hyphen per your setup
        me_name = (me.species or "")
        tag = self._opp_tag(battle)

        # Quick read
        opp_boosts = getattr(opp, "boosts", {}) or {}
        opp_boosted = any(v > 0 for v in opp_boosts.values())

        # --- SLP policy: always click Sleep Talk; never Rest while sleeping ---
        if getattr(me, "status", None) == "SLP":
            st = can_use("sleeptalk")
            if st:
                return self.create_order(st)

        # --- High-urgency utilities BEFORE KO-tunnel ---
        #  A) Immediate anti-boost tools (DT/Haze) fired early
        if opp_boosted:
            if ("giratina" in me_name or "eternatus" in me_name):
                dt = safe_dt()
                if dt:
                    return self.create_order(dt)
            if "clodsire" in me_name:
                hz = can_use("haze")
                if hz:
                    return self.create_order(hz)

        #  B) Giratina Defog has priority once hazards are on our side
        if "giratina" in me_name and self._has_hazards_self(battle):
            df = can_use("defog")
            if df and self._hp(me) >= 0.30:
                return self.create_order(df)

        #  C) Eternatus must not take Zacian/Koraidon — pivot with low threshold
        if "eternatus" in me_name and tag in {"zaciancrowned", "koraidon"}:
            if tag == "zaciancrowned":
                mv = try_switch(("dondozo", "hooh", "giratina"), base_th=-0.05)
                if mv: return mv
            else:  # koraidon
                mv = try_switch(("arceusfairy", "hooh", "dondozo"), base_th=-0.05)
                if mv: return mv

        # Secure-KO (after utilities so we don't DT into Fairy etc.)
        atk = self._best_attack(battle)
        if atk and self._hp(opp) <= self.SECURE_KO_HP:
            return self.create_order(atk)

        # ---------------- Threat table (12) ----------------
        THREATS = {
            # Ubers
            "deoxysspeed":   ("giratina", "eternatus"),
            "kingambit":     ("giratina", "dondozo", "arceusfairy"),
            "zaciancrowned": ("dondozo", "hooh", "giratina"),
            "arceusfairy":   ("clodsire", "hooh", "giratina"),
            "eternatus":     ("clodsire", "giratina", "eternatus"),
            "koraidon":      ("arceusfairy", "hooh", "dondozo"),
            # OU six
            "tornadustherian": ("hooh", "eternatus", "arceusfairy"),
            "rotomwash":       ("clodsire", "eternatus", "arceusfairy"),
            "metagross":       ("hooh", "dondozo", "giratina"),
            "cobalion":        ("hooh", "giratina", "dondozo"),
            "zarudedada":      ("hooh", "dondozo", "arceusfairy"),
            "zarude":          ("hooh", "dondozo", "arceusfairy"),
            "clodsire":        ("arceusfairy", "hooh", "giratina"),
        }

        # -------------- Play tightly into the 12 matchups --------------
        order = THREATS.get(tag)

        if order:
            # zacian hazard-aware Dondozo routing (choose Ho-Oh first if Dozo entry is unsafe)
            if tag == "zaciancrowned" and all(top not in me_name for top in order[:2]):
                d = self._bench_has(battle, "dondozo")
                if d:
                    post = self._hp(d) - self._hazard_chip_estimate(battle, d)
                    if post < 0.65:
                        mv = try_switch(("hooh", "dondozo", "giratina"), base_th=-0.05)
                        if mv: return mv

            # If we’re not already on one of the top two answers, pivot (lower th for Zac/Kora)
            if all(top not in me_name for top in order[:2]):
                base = -0.05 if tag in {"zaciancrowned", "koraidon"} else 0.16
                mv = try_switch(order, base_th=base)
                if mv:
                    return mv

            # We’re on (or stuck into) our check: run set-aware micro
            # ===== UBERS =====
            if tag == "deoxysspeed":
                # If hazards are up, Defog first; else DT to stop stacking
                if "giratina" in me_name:
                    if self._has_hazards_self(battle):
                        df = can_use("defog")
                        if df: return self.create_order(df)
                    dt = safe_dt()
                    if dt: return self.create_order(dt)
                if "eternatus" in me_name:
                    dt = safe_dt()
                    if dt: return self.create_order(dt)
                mv = try_switch(("giratina",), base_th=0.12)
                if mv: return mv

            elif tag == "kingambit":
                if "giratina" in me_name:
                    w = can_use("willowisp")
                    if w and opp and opp.status is None and (not opp.types or "Fire" not in opp.types):
                        return self.create_order(w)
                    dt = safe_dt()
                    if dt: return self.create_order(dt)
                if "dondozo" in me_name:
                    # Prefer non-damaging into Sucker Punch when healthy
                    if opp_has_move("suckerpunch"):
                        cr = can_use("curse")
                        if cr and self._hp(me) > 0.50 and getattr(me, "status", None) != "SLP":
                            return self.create_order(cr)
                    r = can_use("rest")
                    if r and getattr(me, "status", None) != "SLP" and self._hp(me) <= 0.72:
                        return self.create_order(r)
                    liq = can_use("liquidation")
                    if liq: return self.create_order(liq)
                if "arceusfairy" in me_name:
                    ep = can_use("earthpower")
                    if ep: return self.create_order(ep)
                # If Dozo is already <65, allow free pivot to Giratina
                if "giratina" not in me_name:
                    dozo = self._bench_has(battle, "dondozo")
                    if dozo and self._hp(dozo) < 0.65:
                        mv = try_switch(("giratina",), base_th=0.00)
                        if mv: return mv
                if "eternatus" in me_name:
                    ft = can_use("flamethrower")
                    if ft and self._hp(me) >= 0.72:
                        return self.create_order(ft)

            elif tag == "zaciancrowned":
                wc_seen = opp_has_move("wildcharge")
                if "hooh" in me_name:
                    sf_or_bb = can_use("sacredfire") or can_use("bravebird")
                    if sf_or_bb: return self.create_order(sf_or_bb)
                    if wc_seen:
                        mv = try_switch(("dondozo", "arceusfairy"), base_th=0.10)
                        if mv: return mv
                if "dondozo" in me_name:
                    if wc_seen:
                        af = self._bench_has(battle, "arceusfairy")
                        if af and self._hp(af) >= 0.62:
                            mv = try_switch(("arceusfairy",), base_th=0.05)
                            if mv: return mv
                    r = can_use("rest")
                    if r and getattr(me, "status", None) != "SLP" and self._hp(me) <= 0.70:
                        return self.create_order(r)
                    liq = can_use("liquidation")
                    if liq: return self.create_order(liq)
                if "giratina" in me_name:
                    dt = safe_dt()
                    if dt: return self.create_order(dt)

            elif tag == "arceusfairy":
                taunt_seen = opp_has_move("taunt")
                if "clodsire" in me_name:
                    if not taunt_seen:
                        hz = can_use("haze")
                        if hz and opp_boosted:
                            return self.create_order(hz)
                    eq = can_use("earthquake")
                    if eq: return self.create_order(eq)
                    rec = can_use("recover")
                    if rec and self._hp(me) <= 0.55:
                        return self.create_order(rec)
                if "giratina" in me_name:
                    mv = try_switch(("hooh", "clodsire"), base_th=0.10)
                    if mv: return mv
                if "hooh" in me_name:
                    rec = can_use("recover")
                    if rec and self._hp(me) <= 0.52:
                        return self.create_order(rec)
                    bb = can_use("bravebird")
                    if bb: return self.create_order(bb)
                    sf = can_use("sacredfire")
                    if sf: return self.create_order(sf)

            elif tag == "eternatus":
                beam_core = opp_has_move("meteorbeam") or opp_has_move("agility")
                if "clodsire" in me_name:
                    if opp_boosted:
                        hz = can_use("haze")
                        if hz: return self.create_order(hz)
                    eq = can_use("earthquake")
                    if eq: return self.create_order(eq)
                    rec = can_use("recover")
                    if rec and self._hp(me) <= 0.58:
                        return self.create_order(rec)
                if "giratina" in me_name or "eternatus" in me_name:
                    dt = safe_dt()
                    if dt: return self.create_order(dt)
                if beam_core:
                    mv = try_switch(("clodsire",), base_th=0.05)
                    if mv: return mv
                    cl = self._bench_has(battle, "clodsire")
                    if (not cl) or self._hp(cl) < 0.35:
                        mv = try_switch(("arceusfairy",), base_th=0.08)
                        if mv: return mv

            elif tag == "koraidon":
                fc_seen = opp_has_move("flamecharge")
                if "arceusfairy" in me_name:
                    rec = can_use("recover")
                    if rec and self._hp(me) <= 0.64 and not self._is_pressure_turn(battle):
                        return self.create_order(rec)
                    jd = can_use("judgment")
                    if jd: return self.create_order(jd)
                if "hooh" in me_name:
                    sf = can_use("sacredfire")
                    if sf: return self.create_order(sf)
                if "dondozo" in me_name:
                    r = can_use("rest")
                    if r and getattr(me, "status", None) != "SLP" and self._hp(me) <= 0.70:
                        return self.create_order(r)
                if "arceusfairy" not in me_name:
                    mv = try_switch(("arceusfairy",), base_th=0.08 if fc_seen else 0.12)
                    if mv: return mv

            # ===== OU SIX =====
            elif tag == "tornadustherian":
                if "eternatus" in me_name:
                    if opp_boosted:
                        dt = safe_dt()
                        if dt: return self.create_order(dt)
                    ft = can_use("flamethrower")
                    if ft: return self.create_order(ft)
                if "hooh" in me_name:
                    sf = can_use("sacredfire")
                    if sf: return self.create_order(sf)

            elif tag == "rotomwash":
                # Never EQ into Levitate; Spikes -> Recover -> soft pivot
                if "clodsire" in me_name:
                    s = can_use("spikes")
                    if s and not self._has_hazards_opp(battle):
                        return self.create_order(s)
                    rec = can_use("recover")
                    if rec and self._hp(me) <= 0.56:
                        return self.create_order(rec)
                    mv = try_switch(("eternatus", "arceusfairy"), base_th=0.04)
                    if mv: return mv

            elif tag == "metagross":
                if "hooh" in me_name:
                    sf = can_use("sacredfire")
                    if sf: return self.create_order(sf)
                if "dondozo" in me_name:
                    r = can_use("rest")
                    if r and getattr(me, "status", None) != "SLP" and self._hp(me) <= 0.72:
                        return self.create_order(r)
                    liq = can_use("liquidation")
                    if liq: return self.create_order(liq)
                if "giratina" in me_name:
                    w = can_use("willowisp")
                    if w: return self.create_order(w)

            elif tag == "cobalion":
                if "hooh" in me_name:
                    sf = can_use("sacredfire")
                    if sf: return self.create_order(sf)
                if "giratina" in me_name:
                    w = can_use("willowisp")
                    if w: return self.create_order(w)

            elif tag in ("zarudedada", "zarude"):
                if "hooh" in me_name:
                    sf = can_use("sacredfire")
                    if sf: return self.create_order(sf)
                if "dondozo" in me_name:
                    r = can_use("rest")
                    if r and getattr(me, "status", None) != "SLP" and self._hp(me) <= 0.70:
                        return self.create_order(r)
                    liq = can_use("liquidation")
                    if liq: return self.create_order(liq)
                if "arceusfairy" in me_name:
                    jd = can_use("judgment")
                    if jd: return self.create_order(jd)

            elif tag == "clodsire":
                if "arceusfairy" in me_name:
                    ep = can_use("earthpower")
                    if ep: return self.create_order(ep)

        # ---------------- generic rails (kept light) ----------------
        # Eternatus generic (safe pattern)
        if "eternatus" in me_name:
            if opp_boosted:
                dt = safe_dt()
                if dt: return self.create_order(dt)
            rec = can_use("recover")
            if rec and self._hp(me) <= 0.50:
                return self.create_order(rec)
            ft = can_use("flamethrower")
            if ft:
                return self.create_order(ft)

        # Hazard control when on Giratina
        if "giratina" in me_name and self._has_hazards_self(battle):
            df = can_use("defog")
            if df and self._hp(me) >= 0.30:
                return self.create_order(df)

        # Phaze for chip if they have hazards up and no Fairy immunity to DT
        if self._has_hazards_opp(battle) and not self._opp_has_type(battle, "Fairy"):
            if "giratina" in me_name or "eternatus" in me_name:
                dt = safe_dt()
                if dt: return self.create_order(dt)
            if "hooh" in me_name and tag != "eternatus":
                ww = can_use("whirlwind")
                if ww: return self.create_order(ww)

        # Greedy but safe heals
        if not self._is_pressure_turn(battle):
            rec = can_use("recover")
            if rec and self._hp(me) <= self.GENERIC_RECOVER_THRESHOLD:
                return self.create_order(rec)
        if getattr(me, "status", None) != "SLP" and can_use("rest") and self._hp(me) <= 0.45:
            return self.create_order(can_use("rest"))

        # Default: best attack; last-resort pivot if losing badly
        atk = self._best_attack(battle)
        if atk:
            return self.create_order(atk)

        cur = self._matchup_score(me, opp)
        if battle.available_switches and (self._hp(me) < 0.30 or cur <= -1.0):
            pick = self._pick_replacement(battle)
            if pick:
                self._note_switch(battle)
                return self.create_order(pick)

        return self.choose_random_move(battle)
