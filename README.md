# Diet Optimization with Gurobi (Cost & Methane)

This repository provides a command-line script to **group dairy cows** (optional) and **optimize a ration** using a linear program in **Gurobi**. The model enforces **nutrient constraints**, **ingredient min/max bounds**, and a **forage fraction constraint**, and can optimize for:

- `cost` (minimize $/cow/day)
- `methane` (minimize kg CH₄/cow/day)
- `both` (minimize `cost + w * methane`)

Methane can be computed using either the **NASEM** or **Ellis** equation (as implemented in the script).

---

## What’s included

- `run_diet_opt.py` — CLI entrypoint:
  - reads cow and crop nutrient CSVs
  - groups cows into 1/2/3 groups (optional)
  - builds and solves a Gurobi model per group
  - writes results to CSV

- `util.py` — helper functions (data loading, min/max tables, prices, grouping logic, nutrient requirement construction).  
  > This script assumes your `util.py` exposes the methods used in `run_diet_opt.py`.

---

## Requirements

- Python 3.9+ (recommended)
- Gurobi + valid license (required)
- Python packages:
  - `gurobipy`
  - `pandas`
  - `numpy`

Install dependencies (example with pip):

```bash
pip install -r requirements.txt

Note: gurobipy requires that Gurobi is installed and licensed on your machine.

Repository structure (recommended)
.
├─ run_diet_opt.py          # main CLI script
├─ util.py                  # helper functions (data loading, grouping, constraints)
├─ data/
│  ├─ cow_raw_data.csv
│  └─ selected_nutrients_Arlington.csv
├─ outputs/
└─ requirements.txt

Input data
1) Cow data (--cow-path)

CSV file loaded via util.get_cow_raw_data(...).

The following columns are required (directly or indirectly):

DMI – dry matter intake (kg/cow/day)

NEL – net energy for lactation (used for percentile-based requirement)

Additional columns required by grouping functions (e.g., DIM, milk yield)

2) Crop nutrient library (--crop-path)

CSV file loaded via util.get_farm_crop_library_table(...).

The DataFrame must be indexed by ingredient name and include at least:

Column	Description
DM	Dry matter fraction (as-fed → DM)
NEL	Net energy for lactation
CP	Crude protein
NDF	Neutral detergent fiber
STARCH	Starch
FAT	Fat
TFA	Total fatty acids
DNDF	Digestible NDF

Ingredient names must also match:

util.get_min_max_feed_table()

util.get_feed_price_table()

Forage constraint (important)

The model currently assumes these forage ingredients by name:

Corn silage

Legume silage, mid maturity

A forage inclusion constraint enforces:

40–60% of total dry matter intake

If your ingredient names differ, update the forage_ingredients list in run_diet_opt.py.

Installation
git clone https://github.com/YOUR_ORG/YOUR_REPO.git
cd YOUR_REPO
pip install -r requirements.txt


Ensure your Gurobi license is active:

python -c "import gurobipy as gp; m = gp.Model(); print('Gurobi OK')"

Usage
Basic example
python run_diet_opt.py \
  --cow-path ./data/cow_raw_data.csv \
  --crop-path ./data/selected_nutrients_Arlington.csv \
  --group-num 2 \
  --criteria milk \
  --dm-vary 0.01 \
  --nel-vary 0.01 \
  --methane-eqn NASEM \
  --obj both \
  --methane-weight 1.0 \
  --out-dir ./outputs

Command-line options
| Argument           | Description                              | Default     |
| ------------------ | ---------------------------------------- | ----------- |
| `--cow-path`       | Path to cow input CSV                    | required    |
| `--crop-path`      | Path to crop nutrient CSV                | required    |
| `--group-num`      | Number of groups (1, 2, or 3)            | `1`         |
| `--criteria`       | Grouping criterion: `dim`, `nel`, `milk` | `milk`      |
| `--dm-vary`        | DMI requirement variation (see `util`)   | `0.01`      |
| `--nel-vary`       | NEL requirement variation (see `util`)   | `0.01`      |
| `--methane-eqn`    | Methane equation: `NASEM` or `Ellis`     | `NASEM`     |
| `--obj`            | Objective: `cost`, `methane`, `both`     | `cost`      |
| `--methane-weight` | Weight on methane when `obj=both`        | `1.0`       |
| `--out-dir`        | Output directory                         | `./outputs` |
| `--quiet`          | Suppress solver output                   | off         |


See full help:

python run_diet_opt.py -h

Output files

For each group, the script writes:

results_groupX.csv

Summary statistics per cow per day:

Feed cost ($/cow/day)

Methane emissions (g/cow/day)

Dry matter intake

Nutrient composition (% of DM)

feed_groupX.csv

Ingredient inclusion rates:

Ingredient name

As-fed amount (kg/cow/day)

Objective functions

Cost-only

--obj cost


Methane-only

--obj methane


Joint objective (weighted sum)

--obj both --methane-weight 1.0


⚠️ Cost and methane use different units. The methane weight controls trade-offs and should be chosen carefully.