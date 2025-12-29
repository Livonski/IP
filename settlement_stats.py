"""
Utility module to compute tribe and settlement statistics based on the ruleset in README.
The calculations are split into small functions so the module can be reused from
other scripts or imported in tests.

Run the module directly to see an example with the default values from the rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Climate(Enum):
    TROPICAL = "tropical"
    TEMPERATE = "temperate"
    POLAR = "polar"
    SNOW = "snow"


class WaterBody(Enum):
    NONE = "none"
    RIVER = "river"
    SEA = "sea"
    ENDORHEIC_LAKE = "endorheic_lake"  # бесточное озеро
    FLOWING_LAKE = "flowing_lake"      # проточное озеро


class Cult(Enum):
    NONE = "none"
    STRENGTH = "strength"
    LABOUR = "labour"
    MIND = "mind"
    HEALTH = "health"
    BEAUTY = "beauty"
    RENUNCIATION = "renunciation"


@dataclass
class WeaponStock:
    clubs: int = 0
    spears: int = 0
    bows: int = 0

    def total(self) -> int:
        return self.clubs + self.spears + self.bows


@dataclass
class ToolCoverage:
    hammers_pct: int = 0  # multiples of 10%
    clothing_pct: int = 0  # multiples of 20%
    alcohol_pct: int = 0  # multiples of 5%
    rafts_pct: int = 0  # must be 0 or multiples of 20%


@dataclass
class Items:
    settlement: bool = False
    wagon: bool = False
    casino_totem: bool = False


@dataclass
class TechState:
    agriculture: bool = False
    husbandry: bool = False
    wheel: bool = False
    building: bool = False
    swimming: bool = False
    alcoholism: bool = False
    clothes: bool = False


@dataclass
class TraitEffects:
    fertility_bonus: int = 0
    cold_mortality_delta: int = 0
    disease_mortality_delta: int = 0
    production_pct: float = 0.0
    bm_pct: float = 0.0
    speed_delta: int = 0
    science_delta: int = 0


@dataclass
class TribeInput:
    population: int = 1000
    experience: int = 4
    base_fertility: int = 40
    climate: Climate = Climate.TROPICAL
    near_fresh_water: bool = False
    water_body: WaterBody = WaterBody.NONE
    has_fish_resource: bool = False
    tools: ToolCoverage = field(default_factory=ToolCoverage)
    weapons: WeaponStock = field(default_factory=WeaponStock)
    items: Items = field(default_factory=Items)
    tech: TechState = field(default_factory=TechState)
    cult: Cult = Cult.NONE
    trait_effects: TraitEffects = field(default_factory=TraitEffects)


@dataclass
class FertilityBreakdown:
    fertility: int
    cold_mortality: int
    disease_mortality: int
    raft_bonus: int

    @property
    def growth_rate(self) -> int:
        return self.fertility + self.raft_bonus - self.cold_mortality - self.disease_mortality


@dataclass
class ProductionStats:
    base_op: float
    hammer_bonus: float
    cult_modifier: float
    trait_modifier: float

    @property
    def total_op(self) -> float:
        return (self.base_op + self.hammer_bonus) * (1 + self.cult_modifier + self.trait_modifier)


@dataclass
class BattleStats:
    battle_power_raw: float
    battle_power_scaled: float
    weapon_usage: Dict[str, int]


@dataclass
class ScienceStats:
    passive_science: int
    cult_bonus: int
    item_bonus: int

    @property
    def total_science(self) -> int:
        return self.passive_science + self.cult_bonus + self.item_bonus


@dataclass
class TribeStats:
    fertility: FertilityBreakdown
    production: ProductionStats
    battle: BattleStats
    science: ScienceStats
    dna_income: Dict[str, int]
    speed: int
    max_squads: int


CLIMATE_COLD_MORTALITY = {
    Climate.TROPICAL: 0,
    Climate.TEMPERATE: 10,
    Climate.POLAR: 20,
    Climate.SNOW: 30,
}

CLIMATE_DISEASE_MORTALITY = {
    Climate.TROPICAL: 20,
    Climate.TEMPERATE: 15,
    Climate.POLAR: 10,
    Climate.SNOW: 5,
}

RAFT_FERTILITY_BONUS = {
    WaterBody.SEA: 4,
    WaterBody.RIVER: 6,
    WaterBody.ENDORHEIC_LAKE: 6,
    WaterBody.FLOWING_LAKE: 8,
}


def _apply_clothing(cold_mortality: int, coverage_pct: int) -> int:
    steps = coverage_pct // 20
    return max(0, cold_mortality - steps * 10)


def _apply_alcohol(disease_mortality: int, coverage_pct: int) -> int:
    steps = coverage_pct // 5
    return max(0, disease_mortality - steps)


def _raft_bonus(input_data: TribeInput) -> int:
    if input_data.tools.rafts_pct == 0:
        return 0
    steps = input_data.tools.rafts_pct // 20
    base_bonus = RAFT_FERTILITY_BONUS.get(input_data.water_body, 0)
    if base_bonus == 0:
        return 0
    fish_bonus = 2 if input_data.water_body == WaterBody.SEA else 3 if input_data.has_fish_resource else 0
    penalty = 0
    if input_data.tech.husbandry:
        penalty += 4 * steps
    if input_data.tech.agriculture:
        penalty += 4 * steps
    total_bonus = steps * (base_bonus + fish_bonus) - penalty
    return max(0, total_bonus)


def calculate_fertility(input_data: TribeInput) -> FertilityBreakdown:
    fertility = input_data.base_fertility + input_data.trait_effects.fertility_bonus
    if input_data.near_fresh_water:
        fertility += 10

    cold_mortality = CLIMATE_COLD_MORTALITY[input_data.climate] + input_data.trait_effects.cold_mortality_delta
    disease_mortality = CLIMATE_DISEASE_MORTALITY[input_data.climate] + input_data.trait_effects.disease_mortality_delta

    cold_mortality = _apply_clothing(cold_mortality, input_data.tools.clothing_pct if input_data.tech.clothes else 0)
    disease_mortality = _apply_alcohol(disease_mortality, input_data.tools.alcohol_pct if input_data.tech.alcoholism else 0)

    raft_bonus = _raft_bonus(input_data)

    return FertilityBreakdown(
        fertility=fertility,
        cold_mortality=cold_mortality,
        disease_mortality=disease_mortality,
        raft_bonus=raft_bonus,
    )


def _weapon_allocation(population: int, weapons: WeaponStock) -> Dict[str, int]:
    remaining = population
    usage: Dict[str, int] = {}
    bow_used = min(weapons.bows, remaining)
    remaining -= bow_used
    usage["bows"] = bow_used

    spear_used = min(weapons.spears, remaining)
    remaining -= spear_used
    usage["spears"] = spear_used

    club_used = min(weapons.clubs, remaining)
    remaining -= club_used
    usage["clubs"] = club_used
    return usage


def calculate_battle_stats(input_data: TribeInput) -> BattleStats:
    weapon_usage = _weapon_allocation(input_data.population, input_data.weapons)
    weapon_bonus = (
        weapon_usage["clubs"] * 1
        + weapon_usage["spears"] * 2
        + weapon_usage["bows"] * 3
    )
    raw_power = (input_data.population + weapon_bonus) * input_data.experience
    raw_power *= 1 + input_data.trait_effects.bm_pct
    scaled_power = raw_power / 4000.0
    if input_data.items.settlement:
        scaled_power *= 1.5
    return BattleStats(battle_power_raw=raw_power, battle_power_scaled=scaled_power, weapon_usage=weapon_usage)


def calculate_production(input_data: TribeInput) -> ProductionStats:
    base_op = float(input_data.population)
    hammer_bonus = (input_data.tools.hammers_pct // 10) * 0.05 * input_data.population

    cult_modifier = 0.0
    if input_data.cult == Cult.LABOUR:
        cult_modifier = 0.10
    elif input_data.cult == Cult.RENUNCIATION:
        cult_modifier = -0.10

    trait_modifier = input_data.trait_effects.production_pct
    return ProductionStats(
        base_op=base_op,
        hammer_bonus=hammer_bonus,
        cult_modifier=cult_modifier,
        trait_modifier=trait_modifier,
    )


def calculate_science(input_data: TribeInput) -> ScienceStats:
    passive = 0
    if input_data.items.settlement and input_data.tech.building:
        passive += 1
    passive += 2  # каждое поселение по дефолту генерирует 2 науки

    cult_bonus = 1 if input_data.cult == Cult.MIND else -1 if input_data.cult == Cult.RENUNCIATION else 0
    item_bonus = 0
    if input_data.items.casino_totem:
        item_bonus += 0  # ожидаемое значение оставляем нулём, шанс не моделируем детерминированно
    item_bonus += input_data.trait_effects.science_delta
    return ScienceStats(passive_science=passive, cult_bonus=cult_bonus, item_bonus=item_bonus)


def calculate_dna_income(input_data: TribeInput) -> Dict[str, int]:
    human = 1 + (1 if input_data.cult == Cult.RENUNCIATION else 0)
    animal = 1 if input_data.tech.husbandry else 0
    plant = 1 if input_data.tech.agriculture else 0
    # алкоголь удваивает
    if input_data.tech.alcoholism:
        human *= 2
        animal *= 2
        plant *= 2
    return {"human": human, "animal": animal, "plant": plant}


def calculate_speed_and_squads(input_data: TribeInput) -> (int, int):
    speed = 400 + input_data.trait_effects.speed_delta
    if input_data.items.wagon and input_data.tech.wheel:
        speed = int(speed * 1.5)
    if input_data.cult == Cult.HEALTH:
        speed += 50
    elif input_data.cult == Cult.RENUNCIATION:
        speed -= 50

    max_squads = 1
    fully_armed = input_data.weapons.bows >= input_data.population
    if not fully_armed:
        fully_armed = input_data.weapons.spears >= input_data.population
    if not fully_armed:
        fully_armed = input_data.weapons.clubs >= input_data.population

    if fully_armed:
        if input_data.weapons.bows >= input_data.population:
            max_squads = 4
        elif input_data.weapons.spears >= input_data.population:
            max_squads = 3
        else:
            max_squads = 2
    if input_data.items.wagon and input_data.tech.wheel:
        max_squads = max(max_squads, 4)  # повозка снимает ограничения дистанций
    return speed, max_squads


def compute_stats(input_data: TribeInput) -> TribeStats:
    fertility = calculate_fertility(input_data)
    production = calculate_production(input_data)
    battle = calculate_battle_stats(input_data)
    science = calculate_science(input_data)
    dna_income = calculate_dna_income(input_data)
    speed, squads = calculate_speed_and_squads(input_data)
    return TribeStats(
        fertility=fertility,
        production=production,
        battle=battle,
        science=science,
        dna_income=dna_income,
        speed=speed,
        max_squads=squads,
    )


def format_stats(stats: TribeStats) -> str:
    lines = []
    lines.append("[Рождаемость]")
    lines.append(
        f"Фертильность: {stats.fertility.fertility} | Смертность от холода: {stats.fertility.cold_mortality} | "
        f"Смертность от болезней: {stats.fertility.disease_mortality} | Бонус от плотов: {stats.fertility.raft_bonus}"
    )
    lines.append(f"Прирост населения за ход: {stats.fertility.growth_rate}%")

    lines.append("\n[Производство]")
    lines.append(
        f"База ОП: {stats.production.base_op:.1f}, бонус от молотков: {stats.production.hammer_bonus:.1f}, "
        f"итого: {stats.production.total_op:.1f}"
    )

    lines.append("\n[Боевая мощь]")
    lines.append(
        f"Используемое оружие: {stats.battle.weapon_usage}; БМ (сырое): {stats.battle.battle_power_raw:.0f}; "
        f"БМ (норм.): {stats.battle.battle_power_scaled:.2f}"
    )

    lines.append("\n[Наука]")
    lines.append(
        f"Пассивная наука: {stats.science.passive_science}; бонусы: {stats.science.cult_bonus + stats.science.item_bonus}; "
        f"Итого наука/ход: {stats.science.total_science}"
    )

    lines.append("\n[ДНК]")
    lines.append(f"Человек: {stats.dna_income['human']}; Животные: {stats.dna_income['animal']}; Растения: {stats.dna_income['plant']}")

    lines.append("\n[Скорость и отряды]")
    lines.append(f"Скорость: {stats.speed}; Максимум отрядов: {stats.max_squads}")

    return "\n".join(lines)


if __name__ == "__main__":
    default_input = TribeInput()
    stats = compute_stats(default_input)
    print(format_stats(stats))
