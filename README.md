# Diet Optimization with Gurobi (Cost & Methane)

This repository provides a command-line tool to **group dairy cows** (optionally) and **optimize dairy rations** using a linear programming model solved with **Gurobi**.  
The model enforces **nutrient requirements**, **ingredient min/max bounds**, and **forage inclusion constraints**, and supports optimization for:

- **Feed cost** ($/cow/day)
- **Enteric methane emissions** (kg CH₄/cow/day)
- A **weighted combination** of cost and methane

Methane emissions can be calculated using either the **NASEM** or **Ellis** equations.

---

## Features

- Single-group or multi-group (1–3 groups) ration optimization
- Grouping criteria based on:
  - days in milk (DIM)
  - net energy requirement (NEL)
  - milk production
- Cost-only, methane-only, or joint-objective optimization
- CSV-based inputs and outputs
- Reproducible command-line interface

---

## Requirements

- Python **3.9+**
- **Gurobi Optimizer** with a valid license
- Python packages:
  - `numpy`
  - `pandas`
  - `gurobipy`

Example `requirements.txt`:

```txt
numpy
pandas
gurobipy
```

> **Note**: `gurobipy` requires that Gurobi is installed and licensed on your system.

---

## Repository structure (recommended)

```text
.
├─ run_diet_opt.py          # main CLI script
├─ util.py                  # helper functions (data loading, grouping, constraints)
├─ data/
│  ├─ cow_raw_data.csv
│  └─ selected_nutrients_Arlington.csv
├─ outputs/
└─ requirements.txt
```

---

## Input data

### Cow data (`--cow-path`)

CSV file loaded via `util.get_cow_raw_data(...)`.

Required columns (directly or indirectly):

- `DMI` — dry matter intake (kg/cow/day)
- `NEL` — net energy for lactation (used for percentile-based requirement)
- Additional columns required by grouping functions (e.g., DIM, milk yield)

---

### Crop nutrient library (`--crop-path`)

CSV file loaded via `util.get_farm_crop_library_table(...)`.

The DataFrame must be indexed by **ingredient name** and include at least:

| Column | Description |
|------|------------|
| `DM` | Dry matter fraction (as-fed → DM) |
| `NEL` | Net energy for lactation |
| `CP` | Crude protein |
| `NDF` | Neutral detergent fiber |
| `STARCH` | Starch |
| `FAT` | Fat |
| `TFA` | Total fatty acids |
| `DNDF` | Digestible NDF |

Ingredient names must also match those used in:

- `util.get_min_max_feed_table()`
- `util.get_feed_price_table()`

---

## Forage constraint (important)

The model currently assumes the following forage ingredients **by name**:

- `Corn silage`
- `Legume silage, mid maturity`

A forage inclusion constraint enforces:

- **40–60% of total dry matter intake**

If your ingredient names differ, update the `forage_ingredients` list in `run_diet_opt.py`.

---

## Installation

```bash
git clone https://github.com/YOUR_ORG/YOUR_REPO.git
cd YOUR_REPO
pip install -r requirements.txt
```

Verify that Gurobi is correctly installed and licensed:

```bash
python -c "import gurobipy as gp; m = gp.Model(); print('Gurobi OK')"
```

---

## Usage

### Basic example

```bash
python run_diet_opt.py \
  --cow-path ./data/cow_raw_data.csv \
  --crop-path ./data/selected_nutrients_Arlington.csv \
  --feed-price-path ./data/feed_price.csv \
  --group-num 2 \
  --criteria milk \
  --dm-vary 0.01 \
  --nel-vary 0.01 \
  --methane-eqn NASEM \
  --obj both \
  --methane-weight 1.0 \
  --out-dir ./outputs
```

---

## Command-line options

| Argument | Description | Default |
|--------|-------------|---------|
| `--cow-path` | Path to cow input CSV | required |
| `--crop-path` | Path to crop nutrient CSV | required |
| `--group-num` | Number of groups (1, 2, or 3) | `1` |
| `--criteria` | Grouping criterion: `dim`, `nel`, `milk` | `milk` |
| `--dm-vary` | DMI requirement variation (see `util`) | `0.01` |
| `--nel-vary` | NEL requirement variation (see `util`) | `0.01` |
| `--methane-eqn` | Methane equation: `NASEM` or `Ellis` | `NASEM` |
| `--obj` | Objective: `cost`, `methane`, `both` | `cost` |
| `--methane-weight` | Weight on methane when `obj=both` | `1.0` |
| `--out-dir` | Output directory | `./outputs` |
| `--quiet` | Suppress solver output | off |

---

## Output files

For each group, the script writes:

### `results_groupX.csv`

Summary statistics per cow per day, including:
- Feed cost ($/cow/day)
- Methane emissions (g/cow/day)
- Dry matter intake
- Nutrient composition (% of DM)

### `feed_groupX.csv`

Ingredient inclusion rates:
- Ingredient name
- As-fed amount (kg/cow/day)

---

## License

Add a `LICENSE` file to specify usage terms.  
The **MIT License** is commonly used for academic code releases.
