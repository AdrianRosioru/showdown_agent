import logging
from poke_env.battle import AbstractBattle
from poke_env.player import Player

# Configure logging（DEBUG can be replaced with INFO to reduce output）
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

team = """
Landorus-Therian @ Rocky Helmet
Ability: Intimidate
Tera Type: Water
EVs: 252 HP / 240 Def / 16 Spe
Impish Nature
- Earthquake
- U-turn
- Stealth Rock
- Stone Edge

Gholdengo @ Leftovers
Ability: Good as Gold
Tera Type: Water
EVs: 248 HP / 40 SpA / 220 Spe
Timid Nature
IVs: 0 Atk
- Make It Rain
- Shadow Ball
- Thunderbolt
- Recover

Great Tusk @ Leftovers
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 HP / 44 Atk / 212 Spe
Jolly Nature
- Rapid Spin
- Earthquake
- Knock Off
- Ice Spinner

Iron Valiant @ Booster Energy
Ability: Quark Drive
Tera Type: Fairy
EVs: 24 Atk / 232 SpA / 252 Spe
Naive Nature
- Moonblast
- Close Combat
- Thunderbolt
- Encore

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Dark
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Kowtow Cleave
- Sucker Punch
- Iron Head
- Swords Dance

Dragapult @ Choice Specs
Ability: Infiltrator
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
IVs: 0 Atk
- Shadow Ball
- Draco Meteor
- Flamethrower
- U-turn
"""

class CustomAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(team=team, *args, **kwargs)

    @staticmethod
    def _has_move(battle, move_id: str):
        for move in battle.available_moves:
            if move.id == move_id:
                return move
        return None

    def _debug_status(self, battle: AbstractBattle):
        logging.info(
            f"[BattleID] {battle.battle_tag} [Ally]{battle.active_pokemon.species}"
            f"({battle.active_pokemon.current_hp}) vs [Opponent]"
            f"{battle.opponent_active_pokemon.species}"
            f"({battle.opponent_active_pokemon.current_hp}) Status："
            f"{battle.active_pokemon.status}/{battle.opponent_active_pokemon.status}"
        )

    def _move_score(self, move, attacker, defender, battle):
        stab = 1.5 if move.type in attacker.types else 1.0
        eff = defender.damage_multiplier(move.type)
        acc = move.accuracy or 100
        # Calculate attack and defense based on move category
        if move.category == "physical":
            atk = attacker.stats["atk"] or 100
            defense = defender.stats["def"] or 100
        else:
            atk = attacker.stats["spa"] or 100
            defense = defender.stats["spd"] or 100
        stat_factor = atk / max(1, defense)
        # Weather effects
        weather_factor = 1.0
        if battle.weather == "rain":
            if move.type == "water": weather_factor = 1.5
            elif move.type == "fire": weather_factor = 0.5
        elif battle.weather == "sunnyday":
            if move.type == "fire": weather_factor = 1.5
            elif move.type == "water": weather_factor = 0.5
        elif battle.weather == "sandstorm":
            if move.type == "rock": weather_factor = 1.5
            elif move.type == "ground": weather_factor = 1.5
            else: weather_factor = 0.5
        # Screen effects
        screen_factor = 1.0
        if move.category == "physical" and defender.side_conditions.get("reflect"):
            screen_factor = 0.5
        elif move.category == "special" and defender.side_conditions.get("lightscreen"):
            screen_factor = 0.5
        logging.info(f"[{move.id}] base_power={move.base_power or 0}, STAB={stab}, eff={eff}, acc={acc}, stat_factor={stat_factor}, weather_factor={weather_factor}, screen_factor={screen_factor}, score={(move.base_power or 0) * stab * eff * acc / 100 * stat_factor * weather_factor * screen_factor}")
        return (move.base_power or 0) * stab * eff * acc / 100 * stat_factor * weather_factor * screen_factor

    def _best_damage_move(self, battle: AbstractBattle):
        """Select the move with the highest expected damage from available moves, return (move, score)"""
        moves = battle.available_moves
        attacker = battle.active_pokemon
        foe = battle.opponent_active_pokemon

        if not moves:
            logging.info(f"[{attacker.species}] No available moves, best_damage_move returns None")
            return None, 0.0

        scored = [(self._move_score(m, attacker, foe, battle), m) for m in moves]
        best_score, best_move = max(scored, key=lambda x: x[0])
        logging.info(
            f"[{attacker.species}] Selected best damage move：{best_move.id}, Score＝{best_score:.2f}"
        )
        return best_move, best_score
       
    def _best_switch(self, battle: AbstractBattle):
        """Select the most advantageous teammate to switch into against the current opponent"""
        foe = battle.opponent_active_pokemon
        best_switch = None
        best_score = 0.0
        for mon in battle.available_switches:
            for move in mon.moves.values():
                if move.base_power:
                    score = self._move_score(move, mon, foe, battle)
                    if score > best_score:
                        best_score = score
                        best_switch = mon
        return best_switch, best_score

    def choose_move(self, battle: AbstractBattle):
        a = battle.active_pokemon
        foe = battle.opponent_active_pokemon

        self._debug_status(battle)

        # === Species-specific strategies ===
        if a.species == "landorustherian" and battle.turn == 1 and self._has_move(battle, "stealthrock"):
            logging.info("Landorus-T chooses Stealth Rock on the first turn.")
            return self.create_order(self._has_move(battle, "stealthrock"))

        if a.species == "gholdengo" and self._has_move(battle, "recover") and a.current_hp_fraction < 0.5:
            logging.info("Gholdengo HP < 50%, chooses Recover.")
            return self.create_order(self._has_move(battle, "recover"))

        if a.species == "greatusk":
            if self._has_move(battle, "rapidspin") and battle.opponent_side_conditions:
                logging.info("Great Tusk detects entry hazards, chooses Rapid Spin to remove them.")
                return self.create_order(self._has_move(battle, "rapidspin"))
            if self._has_move(battle, "knockoff") and foe.item:
                logging.info("Great Tusk detects opponent has an item, chooses Knock Off to remove it.")
                return self.create_order(self._has_move(battle, "knockoff"))

        if a.species == "kingambit" and self._has_move(battle, "swordsdance") and foe.current_hp_fraction < 0.3:
            logging.info("Kingambit chooses Swords Dance to boost offense.")
            return self.create_order(self._has_move(battle, "swordsdance"))

        # === General evaluation ===
        best_move, best_score = self._best_damage_move(battle)
        best_switch, switch_score = (None, 0.0)
        if battle.available_switches:
            best_switch, switch_score = self._best_switch(battle)

        threatened = any(a.damage_multiplier(t) > 1 for t in foe.types) and a.current_hp_fraction < 0.6

        if best_switch and (best_move is None or switch_score > best_score * 1.3 or (threatened and switch_score > best_score)):
            logging.info(f"Switching → {best_switch.species}, Expected score {switch_score:.2f}")
            return self.create_order(best_switch)

        if a.species == "kingambit" and self._has_move(battle, "suckerpunch"):
            logging.info("Kingambit uses Sucker Punch for priority KO.")
            return self.create_order(self._has_move(battle, "suckerpunch"))

        if a.species == "dragapult":
            draco = self._has_move(battle, "dracometeor")
            if draco and foe.damage_multiplier(draco.type) > 1:
                logging.info("Dragapult uses Draco Meteor for super effective damage.")
                return self.create_order(draco)

        if best_move:
            return self.create_order(best_move)
        
        logging.info("All rules failed, choosing a random move.")
        return self.choose_random_move(battle)

