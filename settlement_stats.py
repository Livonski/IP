"""
Utility module to compute tribe and settlement statistics based on the ruleset in README.
The calculations are split into small functions so the module can be reused from
other scripts or imported in tests.

Run the module directly to see an example with the default values from the rules
or pass ``--ui`` to launch a small Tkinter-based visual interface for tweaking
inputs and recalculating the stats interactively.
"""
from __future__ import annotations

import argparse
import tkinter as tk
from dataclasses import dataclass, field
from enum import Enum
from tkinter import ttk
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


def launch_ui() -> None:
    root = tk.Tk()
    root.title("Расчёт статистики племени")

    content = ttk.Frame(root, padding=10)
    content.grid(column=0, row=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    def labeled_entry(parent: ttk.Frame, text: str, default: int, row: int, column: int = 0):
        ttk.Label(parent, text=text).grid(row=row, column=column, sticky="w", padx=(0, 6))
        var = tk.IntVar(value=default)
        entry = ttk.Entry(parent, textvariable=var, width=8)
        entry.grid(row=row, column=column + 1, sticky="w")
        return var

    row_idx = 0
    ttk.Label(content, text="Базовые параметры", font=("TkDefaultFont", 10, "bold")).grid(
        row=row_idx, column=0, columnspan=4, sticky="w"
    )
    row_idx += 1
    population_var = labeled_entry(content, "Население", 1000, row_idx)
    experience_var = labeled_entry(content, "Опыт", 4, row_idx, column=2)
    row_idx += 1
    fertility_var = labeled_entry(content, "Фертильность", 40, row_idx)

    climate_var = tk.StringVar(value=Climate.TROPICAL.value)
    ttk.Label(content, text="Климат").grid(row=row_idx, column=2, sticky="w", padx=(0, 6))
    ttk.Combobox(
        content,
        textvariable=climate_var,
        values=[c.value for c in Climate],
        state="readonly",
        width=14,
    ).grid(row=row_idx, column=3, sticky="w")
    row_idx += 1

    water_var = tk.StringVar(value=WaterBody.NONE.value)
    ttk.Label(content, text="Водоём рядом").grid(row=row_idx, column=0, sticky="w", padx=(0, 6))
    ttk.Combobox(
        content,
        textvariable=water_var,
        values=[w.value for w in WaterBody],
        state="readonly",
        width=14,
    ).grid(row=row_idx, column=1, sticky="w")

    fresh_water_var = tk.BooleanVar(value=False)
    tk.Checkbutton(content, text="Пресная вода рядом", variable=fresh_water_var).grid(
        row=row_idx, column=2, columnspan=2, sticky="w"
    )
    row_idx += 1

    has_fish_var = tk.BooleanVar(value=False)
    tk.Checkbutton(content, text="Есть ресурс рыбы", variable=has_fish_var).grid(
        row=row_idx, column=0, columnspan=2, sticky="w"
    )

    ttk.Label(content, text="Культ").grid(row=row_idx, column=2, sticky="w", padx=(0, 6))
    cult_var = tk.StringVar(value=Cult.NONE.value)
    ttk.Combobox(
        content, textvariable=cult_var, values=[c.value for c in Cult], state="readonly", width=14
    ).grid(row=row_idx, column=3, sticky="w")
    row_idx += 1

    ttk.Label(content, text="Технологии", font=("TkDefaultFont", 10, "bold")).grid(
        row=row_idx, column=0, columnspan=4, sticky="w", pady=(8, 0)
    )
    row_idx += 1
    tech_states = {
        "agriculture": tk.BooleanVar(value=False),
        "husbandry": tk.BooleanVar(value=False),
        "wheel": tk.BooleanVar(value=False),
        "building": tk.BooleanVar(value=False),
        "swimming": tk.BooleanVar(value=False),
        "alcoholism": tk.BooleanVar(value=False),
        "clothes": tk.BooleanVar(value=False),
    }
    tech_labels = {
        "agriculture": "Земледелие",
        "husbandry": "Скотоводство",
        "wheel": "Колесо",
        "building": "Строительство",
        "swimming": "Плавание",
        "alcoholism": "Алкоголизм",
        "clothes": "Одежда",
    }
    col = 0
    for key, label in tech_labels.items():
        tk.Checkbutton(content, text=label, variable=tech_states[key]).grid(row=row_idx, column=col, sticky="w")
        col += 1
        if col >= 2:
            col = 0
            row_idx += 1
    if col != 0:
        row_idx += 1

    ttk.Label(content, text="Инструменты и оружие", font=("TkDefaultFont", 10, "bold")).grid(
        row=row_idx, column=0, columnspan=4, sticky="w", pady=(8, 0)
    )
    row_idx += 1
    hammers_var = labeled_entry(content, "% молотков", 0, row_idx)
    clothing_var = labeled_entry(content, "% одежды", 0, row_idx, column=2)
    row_idx += 1
    alcohol_var = labeled_entry(content, "% алкоголя", 0, row_idx)
    rafts_var = labeled_entry(content, "% плотов", 0, row_idx, column=2)
    row_idx += 1
    clubs_var = labeled_entry(content, "Дубины", 0, row_idx)
    spears_var = labeled_entry(content, "Копья", 0, row_idx, column=2)
    row_idx += 1
    bows_var = labeled_entry(content, "Луки", 0, row_idx)
    row_idx += 1

    ttk.Label(content, text="Предметы", font=("TkDefaultFont", 10, "bold")).grid(
        row=row_idx, column=0, columnspan=4, sticky="w", pady=(8, 0)
    )
    row_idx += 1
    settlement_var = tk.BooleanVar(value=False)
    wagon_var = tk.BooleanVar(value=False)
    casino_var = tk.BooleanVar(value=False)
    tk.Checkbutton(content, text="Поселение", variable=settlement_var).grid(row=row_idx, column=0, sticky="w")
    tk.Checkbutton(content, text="Повозка", variable=wagon_var).grid(row=row_idx, column=1, sticky="w")
    tk.Checkbutton(content, text="Тотем казино", variable=casino_var).grid(row=row_idx, column=2, sticky="w")
    row_idx += 1

    ttk.Label(content, text="Черты (простые числовые модификаторы)", font=("TkDefaultFont", 10, "bold")).grid(
        row=row_idx, column=0, columnspan=4, sticky="w", pady=(8, 0)
    )
    row_idx += 1
    trait_fertility_var = labeled_entry(content, "Бонус фертильности", 0, row_idx)
    trait_cold_var = labeled_entry(content, "Δ смертность от холода", 0, row_idx, column=2)
    row_idx += 1
    trait_disease_var = labeled_entry(content, "Δ смертность от болезней", 0, row_idx)
    trait_prod_var = labeled_entry(content, "% к производству", 0, row_idx, column=2)
    row_idx += 1
    trait_bm_var = labeled_entry(content, "% к БМ", 0, row_idx)
    trait_speed_var = labeled_entry(content, "Δ скорости", 0, row_idx, column=2)
    row_idx += 1
    trait_science_var = labeled_entry(content, "Бонус науки", 0, row_idx)
    row_idx += 1

    output_box = tk.Text(content, width=80, height=18)
    output_box.grid(row=row_idx, column=0, columnspan=4, pady=(8, 0), sticky="nsew")
    content.rowconfigure(row_idx, weight=1)
    row_idx += 1

    def compute_and_show() -> None:
        try:
            input_data = TribeInput(
                population=max(0, population_var.get()),
                experience=max(0, experience_var.get()),
                base_fertility=fertility_var.get(),
                climate=Climate(climate_var.get()),
                near_fresh_water=fresh_water_var.get(),
                water_body=WaterBody(water_var.get()),
                has_fish_resource=has_fish_var.get(),
                tools=ToolCoverage(
                    hammers_pct=max(0, hammers_var.get()),
                    clothing_pct=max(0, clothing_var.get()),
                    alcohol_pct=max(0, alcohol_var.get()),
                    rafts_pct=max(0, rafts_var.get()),
                ),
                weapons=WeaponStock(
                    clubs=max(0, clubs_var.get()),
                    spears=max(0, spears_var.get()),
                    bows=max(0, bows_var.get()),
                ),
                items=Items(
                    settlement=settlement_var.get(),
                    wagon=wagon_var.get(),
                    casino_totem=casino_var.get(),
                ),
                tech=TechState(
                    agriculture=tech_states["agriculture"].get(),
                    husbandry=tech_states["husbandry"].get(),
                    wheel=tech_states["wheel"].get(),
                    building=tech_states["building"].get(),
                    swimming=tech_states["swimming"].get(),
                    alcoholism=tech_states["alcoholism"].get(),
                    clothes=tech_states["clothes"].get(),
                ),
                cult=Cult(cult_var.get()),
                trait_effects=TraitEffects(
                    fertility_bonus=trait_fertility_var.get(),
                    cold_mortality_delta=trait_cold_var.get(),
                    disease_mortality_delta=trait_disease_var.get(),
                    production_pct=trait_prod_var.get() / 100.0,
                    bm_pct=trait_bm_var.get() / 100.0,
                    speed_delta=trait_speed_var.get(),
                    science_delta=trait_science_var.get(),
                ),
            )
        except Exception as exc:  # pragma: no cover - GUI convenience path
            output_box.delete("1.0", tk.END)
            output_box.insert(tk.END, f"Ошибка ввода: {exc}")
            return

        stats = compute_stats(input_data)
        output_box.delete("1.0", tk.END)
        output_box.insert(tk.END, format_stats(stats))

    ttk.Button(content, text="Рассчитать", command=compute_and_show).grid(
        row=row_idx, column=0, columnspan=4, pady=8, sticky="ew"
    )

    compute_and_show()
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Tribe statistics calculator")
    parser.add_argument("--ui", action="store_true", help="Запустить графический интерфейс")
    args = parser.parse_args()

    if args.ui:
        launch_ui()
    else:
        default_input = TribeInput()
        stats = compute_stats(default_input)
        print(format_stats(stats))


if __name__ == "__main__":
    main()
