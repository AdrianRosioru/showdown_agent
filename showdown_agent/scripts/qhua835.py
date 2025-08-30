from poke_env.battle import AbstractBattle
from poke_env.player import Player
from poke_env.data import GenData
import re

SIDE_ROCKS = "stealthrock"
SIDE_SPIKES = "spikes"
#ndm impish
# ───────────────────────── TEAM (SV UBERS SERIES 9) ───────────────────────── #
team = """
Necrozma-Dusk-Mane @ Rocky Helmet  
Ability: Prism Armor  
Tera Type: Water  
EVs: 252 HP / 252 Atk / 4 SpD  
Adamant Nature  
- Sunsteel Strike  
- Earthquake  
- Outrage  
- Morning Sun

Koraidon @ Choice Band  
Ability: Orichalcum Pulse  
Tera Type: Fire  
EVs: 252 Atk / 4 SpD / 252 Spe  
Jolly Nature  
- Flare Blitz  
- Close Combat  
- Outrage 
- Iron Head

Kyogre @ Choice Specs  
Ability: Drizzle  
Tera Type: Water  
EVs: 252 HP / 252 SpA / 4 Spe  
Hasty Nature  
- Water Spout  
- Rock Slide  
- Ice Beam  
- Thunder 

Zacian-Crowned @ Rusted Sword  
Ability: Intrepid Sword  
Tera Type: Fairy  
EVs: 8 HP / 248 Atk / 252 Spe  
Jolly Nature  
- Behemoth Blade  
- Play Rough  
- Close Combat  
- Wild Charge

Ho-Oh @ Heavy-Duty Boots  
Ability: Regenerator  
Tera Type: Flying  
EVs: 4 HP / 252 Atk / 252 SpD  
Careful Nature  
- Sacred Fire  
- Brave Bird  
- Earthquake  
- Recover 

Arceus-Ground @ Earth Plate  
Ability: Multitype  
Tera Type: Ground  
EVs: 252 HP / 4 SpA / 252 Spe  
Timid Nature  
IVs: 0 Atk  
- Judgment  
- Calm Mind  
- Recover  
- Ice Beam
"""

# ─────────────────────────── Species typing fallback ───────────────────────── #
SPECIES_TYPING = {
    "eternatus":          ("poison", "dragon"),
    "kingambit":          ("dark", "steel"),
    "zacian-crowned":     ("fairy", "steel"),
    "zacian":             ("fairy",),
    "koraidon":           ("fighting", "dragon"),
    "hooh":              ("fire", "flying"),
    "necrozmaduskmane": ("psychic", "steel"),
    "kyogre":             ("water",),
    "arceus":             ("normal",),  # Base Arceus
    "arceusnormal":      ("normal",),
    "arceusfairy":       ("fairy",),
    "arceusground":      ("ground",),
    "arceusfire":        ("fire",),
    "arceuswater":       ("water",),
    "arceusgrass":       ("grass",),
    "arceuselectric":    ("electric",),
    "arceuspsychic":     ("psychic",),
    "arceusice":         ("ice",),
    "arceusdragon":      ("dragon",),
    "arceusdark":        ("dark",),
    "arceusfighting":    ("fighting",),
    "arceuspoison":      ("poison",),
    "arceusflying":      ("flying",),
    "arceusbug":         ("bug",),
    "arceusrock":        ("rock",),
    "arceusghost":       ("ghost",),
    "arceussteel":       ("steel",),
}


ABILITY_IMMUNITIES = {
    "waterabsorb": {"water"},
    "stormdrain": {"water"},
    "dryskin": {"water"},
    "flashfire": {"fire"},
    "voltabsorb": {"electric"},
    "lightningrod": {"electric"},
    "motordrive": {"electric"},
    "sapsipper": {"grass"},
    "levitate": {"ground"},  # Note: ignores niche Gravity/Smack Down/etc.
}

SPECIES_GUARANTEED_ABILITIES = {
    "volcanion": {"waterabsorb"},
}

TYPE_CHART = {
    "normal":  {"rock":0.5, "ghost":0.0, "steel":0.5},
    "fire":    {"fire":0.5, "water":0.5, "rock":0.5, "dragon":0.5, "grass":2.0, "ice":2.0, "bug":2.0, "steel":2.0},
    "water":   {"water":0.5, "grass":0.5, "dragon":0.5, "fire":2.0, "ground":2.0, "rock":2.0},
    "electric":{"electric":0.5, "grass":0.5, "dragon":0.5, "ground":0.0, "water":2.0, "flying":2.0},
    "grass":   {"fire":0.5, "grass":0.5, "poison":0.5, "flying":0.5, "bug":0.5, "dragon":0.5, "steel":0.5,
                "water":2.0, "ground":2.0, "rock":2.0},
    "ice":     {"fire":0.5, "water":0.5, "ice":0.5, "steel":0.5, "grass":2.0, "ground":2.0, "flying":2.0, "dragon":2.0},
    "fighting":{"poison":0.5, "flying":0.5, "psychic":0.5, "bug":0.5, "fairy":0.5, "ghost":0.0,
                "normal":2.0, "ice":2.0, "rock":2.0, "dark":2.0, "steel":2.0},
    "poison":  {"poison":0.5, "ground":0.5, "rock":0.5, "ghost":0.5, "steel":0.0, "grass":2.0, "fairy":2.0},
    "ground":  {"grass":0.5, "bug":0.5, "flying":0.0, "fire":2.0, "electric":2.0, "poison":2.0, "rock":2.0, "steel":2.0},
    "flying":  {"electric":0.5, "rock":0.5, "steel":0.5, "grass":2.0, "fighting":2.0, "bug":2.0},
    "psychic": {"psychic":0.5, "steel":0.5, "dark":0.0, "fighting":2.0, "poison":2.0},
    "bug":     {"fire":0.5, "fighting":0.5, "poison":0.5, "flying":0.5, "ghost":0.5, "steel":0.5, "fairy":0.5,
                "grass":2.0, "psychic":2.0, "dark":2.0},
    "rock":    {"fighting":0.5, "ground":0.5, "steel":0.5, "fire":2.0, "ice":2.0, "flying":2.0, "bug":2.0},
    "ghost":   {"dark":0.5, "normal":0.0, "psychic":2.0, "ghost":2.0},
    "dragon":  {"steel":0.5, "fairy":0.0, "dragon":2.0},
    "dark":    {"fighting":0.5, "dark":0.5, "fairy":0.5, "psychic":2.0, "ghost":2.0},
    "steel":   {"fire":0.5, "water":0.5, "electric":0.5, "steel":0.5, "ice":2.0, "rock":2.0, "fairy":2.0},
    "fairy":   {"fire":0.5, "poison":0.5, "steel":0.5, "fighting":2.0, "dragon":2.0, "dark":2.0},
}


# ──────────────────────── SIMPLE TYPE / MOVE HELPERS ──────────────────────── #
def hp_frac(poke) -> float:
    try:
        return poke.current_hp_fraction
    except Exception:
        return 1.0

def has_boost(poke) -> bool:
    try:
        return any(v > 0 for v in poke.boosts.values())
    except Exception:
        return False

def _canon(s: str) -> str:
    # lowercases and strips everything except [a-z0-9]
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def _norm_species(p):
    try:
        return _canon(p.species)
    except Exception:
        return ''
    
def _norm(s: str) -> str:
    return (s or "").lower().replace(" ", "")

def _type_name(t):
    # Works whether poke-env gives enum-like objects or strings
    if t is None:
        return None
    return (getattr(t, "name", None) or str(t)).lower()

def _enum_cls_from_context(*pokemons):
    """
    Find a PokemonType enum class by inspecting any present type/move.type
    from the provided pokemons. Returns the enum class or None.
    """
    for p in pokemons:
        if not p:
            continue
        # Try actual known types first
        try:
            for t in (p.types or []):
                if t is not None:
                    return t.__class__
        except Exception:
            pass
        # Then scan moves for a move.type
        try:
            for m in (p.moves or {}).values():
                if m and m.type is not None:
                    return m.type.__class__
        except Exception:
            pass
    return None

def _ability_name_set(poke) -> set:
    names = set()
    try:
        if getattr(poke, "ability", None):
            names.add(_norm(poke.ability))
    except Exception:
        pass
    try:
        for a in (poke.possible_abilities or []):
            if a:
                names.add(_norm(a))
    except Exception:
        pass
    # If we still know nothing, add guaranteed abilities by species
    try:
        sp = _norm(_norm_species(poke))
        for a in SPECIES_GUARANTEED_ABILITIES.get(sp, set()):
            names.add(a)
    except Exception:
        pass
    return names

def ability_makes_immune(move, target) -> bool:
    """True if target's (known/possible) ability would nullify this move's TYPE."""
    try:
        if not move or not move.type or not target:
            return False
        mtype = _norm(getattr(move.type, "name", ""))
        if not mtype:
            return False
        abil_set = _ability_name_set(target)
        if not abil_set:
            return False
        for abil in abil_set:
            if mtype in ABILITY_IMMUNITIES.get(abil, set()):
                return True
        return False
    except Exception:
        return False

def _types_of(poke):
    if not poke:
        return ()
    ts = getattr(poke, "types", None)
    if ts:
        return tuple(tn for t in ts if (tn := _type_name(t)))
    # Fallbacks some envs use
    return tuple(tn for t in (getattr(poke, "type_1", None), getattr(poke, "type_2", None))
                 if (tn := _type_name(t)))

# --- Pure chart multiplier used by everything underneath ---
def _type_chart_mult(attacking_type: str, defending_types: tuple[str, ...]) -> float:
    if not attacking_type:
        return 1.0
    chart = TYPE_CHART.get(attacking_type, {})
    m = 1.0
    for dt in defending_types or ():
        m *= chart.get(dt, 1.0)
    return m

# --- Adapter: accepts (move_or_type, target_or_types, battle=None) like your code expects ---
def _type_mult(move_or_type, target_or_types, battle=None) -> float:
    """
    Accepts either:
      - move_or_type: Move object OR type string
      - target_or_types: Pokemon object OR sequence of type strings/enum-like
    Returns the type effectiveness multiplier (0, 0.25, 0.5, 1, 2, 4, ...).
    NOTE: This is pure chart logic; ability/item immunities should be handled in move_is_immune().
    """
    # Figure out attacking type
    if isinstance(move_or_type, str):
        atk_type = move_or_type.lower()
    else:
        atk_type = _type_name(getattr(move_or_type, "type", None))

    # Figure out defending types
    if isinstance(target_or_types, (list, tuple)):
        def_types = tuple(
            (t.lower() if isinstance(t, str) else _type_name(t))
            for t in target_or_types
        )
        def_types = tuple(t for t in def_types if t)  # drop Nones
    else:
        # Assume a Pokemon-like object
        def_types = _types_of(target_or_types)

    if not atk_type:
        return 1.0

    return _type_chart_mult(atk_type, def_types)

def move_is_immune(move, target, battle=None) -> bool:
    # 1) Ability-based hard immunities (Volt Absorb / Water Absorb / Flash Fire / Levitate / etc.)
    if ability_makes_immune(move, target):
        return True

    # 2) Item-based: Air Balloon grants Ground immunity until popped
    try:
        if _type_name(getattr(move, "type", None)) == "ground":
            item = (getattr(target, "item", None) or "").lower()
            if item == "airballoon":
                return True
    except Exception:
        pass  # if your env doesn't expose items, just ignore

    # 3) Type-chart immunities via the compact chart helpers I gave earlier
    atk_type = _type_name(getattr(move, "type", None))
    def_types = _types_of(target)
    if atk_type and def_types and _type_mult(atk_type, def_types) == 0.0:
        return True

    return False

def is_stab(move, user) -> bool:
    try:
        return move.type in (user.types or [])
    except Exception:
        return False

def _effective_base_power(move, user, battle=None):
    bp = move.base_power or 0
    mid = getattr(move, "id", "")
    if mid in {"waterspout", "eruption"}:
        # Heuristic: 150 × current HP fraction (Showdown floors internally; close enough)
        return int(150 * hp_frac(user))
    return bp

def rough_damage_score(move, user, target, battle=None) -> float:
    if move is None or move.base_power is None or move.base_power <= 0:
        return 0.0
    # Use the full immunity logic (ability + items + type)
    if move_is_immune(move, target, battle=battle):
        return 0.0
    power = _effective_base_power(move, user, battle=battle) if "_effective_base_power" in globals() else (move.base_power or 0)
    mult  = _type_mult(move, target, battle=battle)
    stab  = 1.5 if is_stab(move, user) else 1.0
    acc   = (move.accuracy if move.accuracy is not None else 1.0)
    return power * mult * stab * (0.9 + 0.1 * acc)


def _best_stab_offense(attacker, defender) -> float:
    atk_types = _types_of(attacker)
    def_types = _types_of(defender)
    if not atk_types or not def_types:
        return 1.0
    return max(_type_mult(t, def_types) for t in atk_types)

def _threat_type_set(attacker) -> set[str]:
    types = set(_types_of(attacker))
    try:
        for mv in (attacker.moves or {}).values():
            t = _type_name(getattr(mv, "type", None))
            if t:
                types.add(t)
    except Exception:
        pass

    sp = _norm_species(attacker)
    COMMON_COVERAGE = {
        "zaciancrowned": {"electric"},       # Wild Charge
        "eternatus":     {"rock", "fire"},   # Meteor Beam / Fire Blast
    }
    types |= COMMON_COVERAGE.get(sp, set())
    return types

def _worst_threat_on(defender, attacker) -> float:
    """Largest multiplier among attacker's threat types into defender."""
    def_types = _types_of(defender)
    if not def_types:
        return 1.0
    worst = 1.0
    for atk_t in _threat_type_set(attacker):
        worst = max(worst, _type_chart_mult(atk_t, def_types))
    return worst
    
def pick_strongest_attack(battle: AbstractBattle):
    if not battle.available_moves:
        return None
    their_active = battle.opponent_active_pokemon
    my_active = battle.active_pokemon
    scored = []
    enum_cls = _enum_cls_from_context(my_active, their_active)
    for m in battle.available_moves:
        # Hard avoid true immunities
        if move_is_immune(m, their_active, battle=battle):
            continue
        # (Your existing "pessimistic Fairy Arceus vs Dragon" guard can stay here too)
        score = rough_damage_score(m, my_active, their_active, battle=battle)
        if score > 0:
            scored.append((score, m))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]

def pick_counter_switch(battle):
    opp = battle.opponent_active_pokemon
    if not opp:
        return None
    best_sw, best_score = None, float("-inf")
    opp_threats = _threat_type_set(opp)  # includes STAB + revealed + heuristics

    for sw in (battle.available_switches or []):
        sw_sp = _norm_species(sw)

        # --- Hard skips for Ho-Oh into Water/Rock threats (e.g., Ogerpon-Wellspring/Cornerstone) ---
        if sw_sp == "hooh" and (("water" in opp_threats) or ("rock" in opp_threats)):
            continue

        worst_on_sw = _worst_threat_on(sw, opp)      # >=2 means super effective into this switch
        best_stab   = _best_stab_offense(sw, opp)

        # --- If this switch is 2x-weak and ANY alternative is <=1x, skip it outright ---
        if worst_on_sw >= 2.0:
            has_safer_alt = any(
                (_worst_threat_on(alt, opp) <= 1.0)
                for alt in (battle.available_switches or [])
                if alt is not sw
            )
            if has_safer_alt:
                continue

        # --- Your existing scoring (with stronger penalty for 4x) ---
        defense_score = 1.6 * (1.0 / max(0.25, worst_on_sw))
        if worst_on_sw >= 4.0:
            defense_score -= 8.0  # (or: continue)

        offense_score  = 1.0 * best_stab
        hp             = getattr(sw, "current_hp_fraction", 1.0) or 1.0
        low_hp_penalty = -3.0 if hp < 0.2 else 0.0

        score = defense_score + offense_score + low_hp_penalty
        if score > best_score:
            best_score, best_sw = score, sw

    return best_sw



def can_tera_now(battle, declared: bool, used: bool) -> bool:
    # If we already used or declared this turn, don't offer it again
    if used or declared:
        return False
    try:
        req = battle._request
        if not isinstance(req, dict):
            return False

        team_flag = bool(req.get("canTerastallize", False))

        per_flag = team_flag
        active = req.get("active", [])
        if active and isinstance(active, list) and isinstance(active[0], dict):
            # prefer explicit per-active if present
            per_flag = active[0].get("canTerastallize", per_flag)
            per_flag = bool(per_flag)

        # IMPORTANT: allow if EITHER flag is true
        return bool(team_flag or per_flag)
    except Exception:
        return False



def order_with_optional_tera(self, battle, move):
    bid = id(battle)
    declared = self._tera_declared.get(bid, False)
    used     = self._tera_used.get(bid, False)

    if self._want_tera_now(battle, move) and can_tera_now(battle, declared, used):
        self._tera_declared[bid] = True
        self._log(f"[T{battle.turn}] DECLARE TERA with {battle.active_pokemon.species} using {move.id}")
        return self.create_order(move, terastallize=True)

    return self.create_order(move)


# ──────────────────────────── CORE POLICY LOGIC ───────────────────────────── #
class CustomAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)
        self._ndm_first_entry_done = {}
        self._tera_declared = {}   # battle_id -> bool (we sent terastallize=True)
        self._tera_used     = {}   # battle_id -> bool (server has consumed it)
        self._last_switch_turn = {}
        self._consecutive_switches = {}

    def _log(self, *a):
        try:
            self.logger.info(" ".join(str(x) for x in a))
        except Exception:
            print(*a)

    # Quick identity helpers
    def _is(self, p, name):  # name fragment match
        try:
            return _canon(name) in _norm_species(p)
        except Exception:
            return False
        
    def teampreview(self, battle):
        """
        Simple teampreview that relies on the team order.
        Since NDM is first in our team string, it should be the default lead.
        We'll just return the default team order.
        """
        try:
            # Get the team in order
            team_order = "/team " + "".join(str(i) for i in range(1, len(battle.team) + 1))
            return team_order
        except Exception:
            # If anything fails, use the library's random teampreview
            return self.random_teampreview(battle)

    def _ensure_battle_state(self, battle):
        bid = id(battle)
        self._last_switch_turn.setdefault(bid, -999)
        self._consecutive_switches.setdefault(bid, 0)

    def _switch(self, battle, sw):
        """Create a switch order and update anti-loop counters."""
        self._ensure_battle_state(battle)
        bid = id(battle)
        self._consecutive_switches[bid] = (
            self._consecutive_switches[bid] + 1
            if self._last_switch_turn[bid] == battle.turn - 1 else 1
        )
        self._last_switch_turn[bid] = battle.turn
        return self.create_order(sw)

    def _should_attack_instead_of_switch(self, battle) -> bool:
        """Return True if switching now is pointless/risky (prevents ping-pong)."""
        self._ensure_battle_state(battle)
        bid = id(battle)

        # Cooldown: don't switch on consecutive turns unless it's clearly better
        if self._last_switch_turn[bid] == battle.turn - 1:
            return True
        if self._consecutive_switches[bid] >= 2:
            return True

        me  = battle.active_pokemon
        opp = battle.opponent_active_pokemon
        if not me or not opp or not (battle.available_switches or []):
            return False

        # Current danger/offense
        cur_worst = _worst_threat_on(me, opp)
        cur_off   = _best_stab_offense(me, opp)

        # Best we can get by switching
        best_worst = min(_worst_threat_on(sw, opp) for sw in battle.available_switches)
        best_off   = max(_best_stab_offense(sw, opp) for sw in battle.available_switches)

        # Only switch if it REALLY helps: defend goes from SE (>=2x) to <=1x,
        # or offense strictly improves.
        improves_def = (cur_worst >= 2.0) and (best_worst <= 1.0)
        improves_off = best_off > cur_off + 0.0

        # Endgame rule: if we have <=2 alive and they have 1, be stricter on switching.
        try:
            my_alive  = sum(1 for p in battle.team.values() if not p.fainted)
            opp_alive = sum(1 for p in battle.opponent_team.values() if not p.fainted)
        except Exception:
            my_alive = opp_alive = 6
        if my_alive <= 2 and opp_alive <= 1:
            improves_def = (cur_worst >= 2.0) and (best_worst <= 0.5)

        return not (improves_def or improves_off)

    def _want_tera_now(self, battle: AbstractBattle, chosen_move) -> bool:
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon
        if not me or not opp or not chosen_move:
            return False

        # --- NEW: pull our per-battle flags and pass them to can_tera_now ---
        bid = id(battle)
        declared = self._tera_declared.get(bid, False)
        used     = self._tera_used.get(bid, False)

        # --- HARD SAFETY GATES ---
        if not can_tera_now(battle, declared, used):
            return False
        if "arceus" in (me.species or "").lower():  # common ladder rule; delete if you want to allow it
            return False

        # --- Light heuristics (unchanged) ---
        if "kyogre" in me.species.lower() and chosen_move.id in {"waterspout", "originpulse"}:
            if hp_frac(me) > 0.8 and _type_mult(chosen_move, opp, battle=battle) >= 1.0:
                return True

        if "koraidon" in me.species.lower() and chosen_move.id == "flareblitz":
            return True

        if "zaciancrowned" in me.species.lower() and chosen_move.id in {"behemothblade", "playrough"}:
            if len(battle.opponent_team) <= 2:
                return True

        if "necrozmaduskmane" in me.species.lower():
            if hp_frac(me) < 0.6 and battle.turn > 3:
                return True

        if "arceus" in me.species.lower() and chosen_move.id == "judgment":
            try:
                if me.boosts.get("spa", 0) >= 1:
                    return True
            except Exception:
                pass

        if "hooh" in me.species.lower() and chosen_move.id == "bravebird":
            if has_boost(opp):
                return True

        return False

    def _ndm_policy(self, battle):
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon
        self._ndm_first_entry_done[id(battle)] = True
        battle_id = id(battle)
        
        # Decide if the current matchup is bad (we get hit hard and don't threaten much)
        bad_defense = _worst_threat_on(me, opp) >= 2.0          # we take SE from their STAB
        weak_offense = _best_stab_offense(me, opp) <= 1.0     # we don't hit SE with our STAB

        if bad_defense and weak_offense and (battle.available_switches or []):
            if self._should_attack_instead_of_switch(battle):
                pass
            else:
                sw = pick_counter_switch(battle)
                if sw:
                    return self._switch(battle=battle, sw=sw)

        if hp_frac(battle.active_pokemon) <= 0.50:
            for m in (battle.available_moves or []):
                if m.id in {"morningsun"}:
                    return self.create_order(m)

        best = pick_strongest_attack(battle)
        if best:
            return order_with_optional_tera(self, battle, best)

        return self.choose_random_move(battle)


    def _kyogre_policy(self, battle: AbstractBattle):
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        best = pick_strongest_attack(battle)

        spout = next((m for m in (battle.available_moves or []) if m.id == "waterspout"), None)
        if spout and opp:
            if not ability_makes_immune(spout, opp):
                if best is None or rough_damage_score(spout, me, opp, battle=battle) >= rough_damage_score(best, me, opp, battle=battle):
                    return order_with_optional_tera(self, battle, spout)
        
        if opp and _norm_species(opp) == "eternatus":
            ice = next((m for m in (battle.available_moves or []) if m.id == "icebeam"), None)
            if ice:
                return order_with_optional_tera(self, battle, ice)

            for sw in (battle.available_switches or []):
                if _norm_species(sw) == "arceusground":
                    return self.create_order(sw)

        # Decide if the current matchup is bad (we get hit hard and don't threaten much)
        bad_defense = _worst_threat_on(me, opp) >= 2.0          # we take SE from their STAB
        weak_offense = _best_stab_offense(me, opp) <= 1.0     # we don't hit SE with our STAB

        if bad_defense and weak_offense and (battle.available_switches or []):
            if self._should_attack_instead_of_switch(battle):
                pass
            else:
                sw = pick_counter_switch(battle)
                if sw:
                    return self._switch(battle=battle, sw=sw)

        if best:
            return order_with_optional_tera(self, battle, best)

        return self.choose_random_move(battle)


    def _koraidon_policy(self, battle: AbstractBattle):
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon
        def _stage_multiplier(stage: int) -> float:
            # Showdown stage math for speed
            # stage ∈ [-6..6]
            if stage >= 0:
                return (2 + stage) / 2
            return 2 / (2 - stage)

        def _guess_speed(poke) -> float:
            """Approximate current speed using base speed, known boosts, and known item.
            Works great for *your* mons (item known). For opponents, it's a conservative guess."""
            if poke is None:
                return 0.0
            base = float(getattr(poke, "base_speed", 0) or 0)
            try:
                stage = int(getattr(poke, "boosts", {}).get("spe", 0))
            except Exception:
                stage = 0
            mult = _stage_multiplier(stage)

            # Only trust item for our own mon; but reading it is fine if exposed
            item_mult = 1.0
            try:
                item = (getattr(poke, "item", None) or "").lower()
                if item == "choicescarf":
                    item_mult *= 1.5
            except Exception:
                pass

            return base * mult * item_mult

        def _probably_faster(me, opp) -> bool:
            return _guess_speed(me) >= _guess_speed(opp)

        if opp and self._is(opp, "kingambit"):
            fb = next((m for m in (battle.available_moves or []) if m.id == "flareblitz"), None)
            if fb:
                # If Flare Blitz is in available_moves, we are NOT choice-locked away from it.
                # Only take it if we (probably) outspeed; otherwise we can still fall back to your switching logic.
                if _probably_faster(me, opp):
                    return order_with_optional_tera(self, battle, fb)

        if opp and self._is(opp, "zaciancrowned"):
            fb = next((m for m in (battle.available_moves or []) if m.id == "flareblitz"), None)
            if fb:
                # If Flare Blitz is in available_moves, we are NOT choice-locked away from it.
                # Only take it if we (probably) outspeed; otherwise we can still fall back to your switching logic.
                if _probably_faster(me, opp):
                    return order_with_optional_tera(self, battle, fb)

        if opp and self._is(opp, "zaciancrowned") and (battle.available_switches or []):
            ndm = next((sw for sw in battle.available_switches if self._is(sw, "necrozmaduskmane")), None)
            if ndm:
                # avoid sacking an NDM at 1 HP; tune threshold if you like
                hp_frac = getattr(ndm, "current_hp_fraction", 1.0) or 1.0
                if hp_frac > 0.25:
                    return self.create_order(ndm)

        # Decide if the current matchup is bad (we get hit hard and don't threaten much)
        bad_defense = _worst_threat_on(me, opp) >= 2.0          # we take SE from their STAB
        weak_offense = _best_stab_offense(me, opp) <= 1.0     # we don't hit SE with our STAB

        if bad_defense and weak_offense and (battle.available_switches or []):
            if self._should_attack_instead_of_switch(battle):
                pass
            else:
                sw = pick_counter_switch(battle)
                if sw:
                    return self._switch(battle=battle, sw=sw)

        best = pick_strongest_attack(battle)
        if best:
            return order_with_optional_tera(self, battle, best)
        
        return self.choose_random_move(battle)


    def _zacian_policy(self, battle: AbstractBattle):
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon
        # Decide if the current matchup is bad (we get hit hard and don't threaten much)
        bad_defense = _worst_threat_on(me, opp) >= 2.0          # we take SE from their STAB
        weak_offense = _best_stab_offense(me, opp) <= 1.0     # we don't hit SE with our STAB

        if bad_defense and weak_offense and (battle.available_switches or []):
            if self._should_attack_instead_of_switch(battle):
                pass
            else:
                sw = pick_counter_switch(battle)
                if sw:
                    return self._switch(battle=battle, sw=sw)

        best = pick_strongest_attack(battle)
        if best:
            return order_with_optional_tera(self, battle, best)
        
        return self.choose_random_move(battle)


    def _hooh_policy(self, battle: AbstractBattle):
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        if opp and self._is(opp, "kingambit"):
            fb = next((m for m in (battle.available_moves or []) if m.id == "sacredfire"), None)
            if fb:
                return order_with_optional_tera(self, battle, fb)

        # Decide if the current matchup is bad (we get hit hard and don't threaten much)
        bad_defense = _worst_threat_on(me, opp) >= 2.0          # we take SE from their STAB
        weak_offense = _best_stab_offense(me, opp) <= 1.0     # we don't hit SE with our STAB

        if bad_defense and weak_offense and (battle.available_switches or []):
            if self._should_attack_instead_of_switch(battle):
                pass
            else:
                sw = pick_counter_switch(battle)
                if sw:
                    return self._switch(battle=battle, sw=sw)

        if hp_frac(me) <= 0.5:
            for m in battle.available_moves or []:
                if m.id == "recover":
                    return self.create_order(m)

        best = pick_strongest_attack(battle)
        if best:
            return order_with_optional_tera(self, battle, best)
        
        return self.choose_random_move(battle)

    def _arceus_ground_policy(self, battle: AbstractBattle):
        me = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        # Decide if the current matchup is bad (we get hit hard and don't threaten much)
        bad_defense = _worst_threat_on(me, opp) >= 2.0          # we take SE from their STAB
        weak_offense = _best_stab_offense(me, opp) <= 1.0     # we don't hit SE with our STAB

        if bad_defense and weak_offense and (battle.available_switches or []):
            if self._should_attack_instead_of_switch(battle):
                pass
            else:
                sw = pick_counter_switch(battle)
                if sw:
                    return self._switch(battle=battle, sw=sw)

        if opp and (self._is(opp, "koraidon") or self._is(opp, "kingambit") or self._is(opp, "zaciancrowned")):
            for m in (battle.available_moves or []):
                if m.id == "judgment":
                    return self.create_order(m)

        if opp and not has_boost(me) and (self._is(opp, "eternatus")) and hp_frac(me) >= 0.6:
            for m in (battle.available_moves or []):
                if m.id == "calmmind":
                    return self.create_order(m)
        elif opp and (self._is(opp, "eternatus")) and hp_frac(me) < 0.6:
            for m in battle.available_moves or []:
                if m.id == "recover":
                    return self.create_order(m)

        if hp_frac(me) < 0.40:
            for m in battle.available_moves or []:
                if m.id == "recover":
                    return self.create_order(m)

        if opp and not has_boost(me) and hp_frac(me) >= 0.8:
            for m in battle.available_moves or []:
                if m.id == "calmmind":
                    return self.create_order(m)

        best = pick_strongest_attack(battle)
        if best:
            return self.create_order(best)

        return self.choose_random_move(battle)

    # ───────────────────────────── Main policy ───────────────────────────── #
    def choose_move(self, battle: AbstractBattle):
        bid = id(battle)
        self._tera_declared.setdefault(bid, False)
        self._tera_used.setdefault(bid, False)

        # Probe current request flags to see if Tera is still available
        try:
            req = battle._request if isinstance(battle._request, dict) else {}
            team_flag = bool(req.get("canTerastallize", False))
            per_flag  = bool((req.get("active",[{}])[0]).get("canTerastallize", team_flag)) if isinstance(req.get("active",[]), list) else team_flag

            # If we previously declared and now both flags are false, the server consumed Tera last turn
            if self._tera_declared[bid] and not (team_flag or per_flag):
                self._tera_used[bid] = True
                self._log(f"[T{battle.turn}] SERVER CONSUMED TERA")
        except Exception:
            pass

        # # Soft matchup rule: vs Kingambit, don't stay Zacian; prefer Koraidon or hooh
        opp = battle.opponent_active_pokemon
        me  = battle.active_pokemon

        # Route to role-specific policies
        if self._is(me, "necrozmaduskmane"):
            return self._ndm_policy(battle)
        if self._is(me, "kyogre"):
            return self._kyogre_policy(battle)
        if self._is(me, "koraidon"):
            return self._koraidon_policy(battle)
        if self._is(me, "zaciancrowned"):
            return self._zacian_policy(battle)
        if self._is(me, "hooh"):
            return self._hooh_policy(battle)
        if self._is(me, "arceus"):
            return self._arceus_ground_policy(battle)