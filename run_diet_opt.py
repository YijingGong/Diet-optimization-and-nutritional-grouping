"""
Diet optimization CLI (Gurobi)

This script:
1) Loads cow data + crop nutrient library.
2) Optionally groups cows (1/2/3 groups) by a chosen criterion.
3) Runs a linear program to optimize diets under nutrient constraints.
4) Exports results (summary + ingredient amounts) to CSV.

Requirements:
- gurobipy installed and licensed
- your local util.py providing Utility methods used below
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple, Dict, List, Optional

import numpy as np
import pandas as pd
from gurobipy import Model, GRB, GurobiError

from util import Utility as util


# ----------------------------
# Configuration / constants
# ----------------------------

OTHER_NUTRIENTS = ["NEL", "CP", "NDF", "STARCH", "FAT"]

# This comes from your util. Keep it configurable if you want later.
NEL_REQ_PERCENTILE = util.NEL_req_percentile


# ----------------------------
# Core optimization
# ----------------------------

def optimize_diet(
    animal_count: int,
    nutrient_req_table: pd.DataFrame,
    crop_nutrient_table: pd.DataFrame,
    feed_price_table: pd.DataFrame,
    crop_min_max_table: pd.DataFrame,
    methane_eqn: str = "NASEM",
    obj: str = "cost",
    methane_weight: float = 1.0,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Optimize a single-group diet with Gurobi.

    Parameters
    ----------
    animal_count
        Number of cows in this group.
    nutrient_req_table
        Nutrient requirement table indexed by nutrient names (e.g., 'DM','NEL','CP',...),
        with columns at least ['min','max'].
        Units must match how you compute nutrients below.
    crop_nutrient_table
        Crop library indexed by ingredient name, containing at least columns:
        ['DM','NEL','CP','NDF','STARCH','FAT','TFA','DNDF'] plus anything else used.
        'DM' is assumed to be a fraction (0-1) converting as-fed to dry matter.
    methane_eqn
        'Ellis' or 'NASEM' methane prediction constraint.
    obj
        'methane', 'cost', or 'both' (weighted sum: cost + methane_weight*methane).
    methane_weight
        Weight used only if obj == 'both'. (Unit-sensitive!)
    verbose
        Print progress to stdout.

    Returns
    -------
    results_df
        Summary KPIs and nutrient composition (per cow per day).
    feed_df
        Ingredient amounts as-fed (kg/cow/d) for ingredients with non-trivial inclusion.
    """
    if animal_count <= 0:
        raise ValueError(f"animal_count must be positive, got {animal_count}.")

    methane_eqn = methane_eqn.strip().upper()
    obj = obj.strip().lower()

    if methane_eqn not in {"ELLIS", "NASEM"}:
        raise ValueError("Invalid methane_eqn. Use 'Ellis' or 'NASEM'.")
    if obj not in {"methane", "cost", "both"}:
        raise ValueError("Invalid obj. Use 'methane', 'cost', or 'both'.")

    crops = list(crop_nutrient_table.index)

    # Basic sanity checks for public users
    required_crop_cols = {"DM", "NEL", "CP", "NDF", "TFA", "DNDF"}
    missing_cols = required_crop_cols - set(crop_nutrient_table.columns)
    if missing_cols:
        raise ValueError(f"crop_nutrient_table missing columns: {sorted(missing_cols)}")

    for key in ["DM", "NEL", "CP", "NDF"]:
        if key not in nutrient_req_table.index:
            raise ValueError(f"nutrient_req_table must include row '{key}'.")

    if verbose:
        print(">>> Starting optimization (single group)...")

    # ----------------------------
    # Model setup
    # ----------------------------
    try:
        m = Model("diet_optimization")
        # Make it less noisy unless user wants verbose
        m.Params.OutputFlag = 1 if verbose else 0
    except GurobiError as e:
        raise RuntimeError(
            "Failed to create Gurobi model. Is Gurobi installed and licensed?"
        ) from e

    # Decision variables
    dmi = m.addVar(name="dmi", lb=0)  # kg DM/cow/d (computed)
    feed_on_farm = m.addVars(crops, lb=0, name="feed_on_farm")  # kg as-fed/d for whole herd

    # Helper variables for methane/cost calculations (per cow/day)
    nel = m.addVar(lb=0, name="nel")       # Mcal/cow/d
    me = m.addVar(lb=0, name="me")         # Mcal/cow/d
    cp = m.addVar(lb=0, name="cp")         # kg/cow/d
    ndf = m.addVar(lb=0, name="ndf")       # kg/cow/d
    tfa = m.addVar(lb=0, name="tfa")       # kg/cow/d
    dndf = m.addVar(lb=0, name="dndf")     # kg/cow/d
    methane = m.addVar(lb=0, name="methane")  # kg CH4/cow/d
    cost = m.addVar(lb=0, name="cost")        # $/cow/d

    # Nutrient variables (per cow/day) for reporting and constraints
    nutrient_vars: Dict[str, any] = {
        n: m.addVar(lb=0, name=n.lower()) for n in OTHER_NUTRIENTS
    }

    # ----------------------------
    # PART 1: DMI & Nutrient constraints
    # ----------------------------

    # Compute DMI from as-fed feed amounts * DM fraction, converted to per cow
    m.addConstr(
        dmi == sum(feed_on_farm[c] * crop_nutrient_table.loc[c, "DM"] for c in crops) / animal_count,
        name="dmi_calc",
    )
    m.addConstr(dmi >= float(nutrient_req_table.loc["DM", "min"]), name="dmi_min")
    m.addConstr(dmi <= float(nutrient_req_table.loc["DM", "max"]), name="dmi_max")

    # Other nutrient totals (per cow/day). Assumes crop_nutrient_table[n] is per kg DM.
    for n in OTHER_NUTRIENTS:
        if n not in crop_nutrient_table.columns:
            raise ValueError(f"crop_nutrient_table missing nutrient column '{n}'.")

        m.addConstr(
            nutrient_vars[n]
            == sum(
                feed_on_farm[c] * crop_nutrient_table.loc[c, "DM"] * crop_nutrient_table.loc[c, n]
                for c in crops
            )
            / animal_count,
            name=f"{n.lower()}_calc",
        )
        m.addConstr(
            nutrient_vars[n] >= float(nutrient_req_table.loc[n, "min"]),
            name=f"{n.lower()}_min",
        )
        m.addConstr(
            nutrient_vars[n] <= float(nutrient_req_table.loc[n, "max"]),
            name=f"{n.lower()}_max",
        )

    # Forage fraction constraint (example assumes these exact ingredient names exist)
    forage_ingredients = ["Corn silage", "Legume silage, mid maturity"]
    for ing in forage_ingredients:
        if ing not in crops:
            raise ValueError(
                f"Forage ingredient '{ing}' not found in crop_nutrient_table index. "
                "Either rename it in your CSV or update forage_ingredients."
            )

    forage_dm = (
        feed_on_farm[forage_ingredients[0]] * crop_nutrient_table.loc[forage_ingredients[0], "DM"]
        + feed_on_farm[forage_ingredients[1]] * crop_nutrient_table.loc[forage_ingredients[1], "DM"]
    ) / animal_count

    m.addConstr(forage_dm >= 0.4 * dmi, name="forage_min")
    m.addConstr(forage_dm <= 0.6 * dmi, name="forage_max")

    # ----------------------------
    # PART 2: Ingredient min/max constraints
    # ----------------------------
    for c in crops:
        if c not in crop_min_max_table.index:
            raise ValueError(
                f"Ingredient '{c}' not found in util.get_min_max_feed_table(). "
                "Update your min/max table or remove the ingredient."
            )
        m.addConstr(feed_on_farm[c] / animal_count >= float(crop_min_max_table.loc[c, "min"]), name=f"min_{c}")
        m.addConstr(feed_on_farm[c] / animal_count <= float(crop_min_max_table.loc[c, "max"]), name=f"max_{c}")

    # ----------------------------
    # PART 3: Optional special constraints (example)
    # ----------------------------
    # NOTE: This is a *domain-specific* constraint. Keep it, but document why.
    m.addConstr(
        feed_on_farm["Corn silage"] >= feed_on_farm["Legume silage, mid maturity"],
        name="land_constraint1",
    )
    m.addConstr(
        feed_on_farm["Corn silage"] <= 2 * feed_on_farm["Legume silage, mid maturity"],
        name="land_constraint2",
    )

    # ----------------------------
    # PART 4: Methane + cost calculations
    # ----------------------------
    m.addConstr(nel == nutrient_vars["NEL"], name="nel_calc_from_nutrients")
    m.addConstr(me == 1.818 * nel - 0.2319, name="me_calc")

    m.addConstr(cp == nutrient_vars["CP"], name="cp_calc_from_nutrients")
    m.addConstr(ndf == nutrient_vars["NDF"], name="ndf_calc_from_nutrients")

    # These are used by NASEM equation; must exist in crop table
    for extra in ["TFA", "DNDF"]:
        if extra not in crop_nutrient_table.columns:
            raise ValueError(f"crop_nutrient_table missing column '{extra}' required for methane calculation.")

    m.addConstr(
        tfa
        == sum(feed_on_farm[c] * crop_nutrient_table.loc[c, "DM"] * crop_nutrient_table.loc[c, "TFA"] for c in crops)
        / animal_count,
        name="tfa_calc",
    )
    m.addConstr(
        dndf
        == sum(feed_on_farm[c] * crop_nutrient_table.loc[c, "DM"] * crop_nutrient_table.loc[c, "DNDF"] for c in crops)
        / animal_count,
        name="dndf_calc",
    )

    # Cost calculation
    if "price ($/kg)" not in feed_price_table.columns:
        raise ValueError("Feed price table must have column 'price ($/kg)'.")
    for c in crops:
        if c not in feed_price_table.index:
            raise ValueError(f"Ingredient '{c}' missing from feed price table.")

    m.addConstr(
        cost == sum(feed_on_farm[c] * float(feed_price_table.loc[c, "price ($/kg)"]) for c in crops) / animal_count,
        name="cost_calc",
    )

    if methane_eqn == "ELLIS":
        # Ellis equation in MJ/d; convert to kg CH4 using 55.65 MJ/kg
        m.addConstr(
            methane == (4.41 + 0.0224 * 4.184 * me + 0.98 * ndf) / 55.65,
            name="methane_calc",
        )
    else:  # NASEM
        # NASEM equation in Mcal/d; convert to MJ (x 4.184), then to kg CH4 (divide 55.65)
        # Uses TFA and DNDF as fractions of DM intake; check unit assumptions in your crop library.
        m.addConstr(
            methane == (0.294 * dmi - 0.347 * (tfa / dmi) * 100 + 0.0409 * (dndf / dmi) * 100) * 4.184 / 55.65,
            name="methane_calc",
        )

    # ----------------------------
    # Objective
    # ----------------------------
    if obj == "methane":
        m.setObjective(methane, GRB.MINIMIZE)
    elif obj == "cost":
        m.setObjective(cost, GRB.MINIMIZE)
    else:
        # Weighted-sum: be explicit, because units differ ($ vs kg CH4)
        m.setObjective(cost + float(methane_weight) * methane, GRB.MINIMIZE)

    # Solve
    m.optimize()
    if m.Status not in (GRB.OPTIMAL, GRB.SUBOPTIMAL):
        raise RuntimeError(f"Optimization ended with status {m.Status}. Check feasibility / bounds.")

    # ----------------------------
    # Build outputs
    # ----------------------------
    total_as_fed = sum(feed_on_farm[c].X for c in crops) / animal_count

    feed_rows = [
        {"Ingredient": c, "Amount as fed (kg/cow/d)": feed_on_farm[c].X / animal_count}
        for c in crops
        if feed_on_farm[c].X / animal_count > 0.01
    ]
    feed_df = pd.DataFrame(feed_rows).sort_values("Amount as fed (kg/cow/d)", ascending=False)

    results_rows = [
        ("$/cow/d", cost.X),
        ("methane (g/cow/d)", methane.X * 1000),
        ("dmi (kg DM/cow/d)", dmi.X),
        ("dm (%)", (dmi.X / total_as_fed * 100) if total_as_fed > 0 else np.nan),
        ("NEL (Mcal/kg DM)", (nel.X / dmi.X) if dmi.X > 0 else np.nan),
        ("CP (% of DM)", (nutrient_vars["CP"].X / dmi.X * 100) if dmi.X > 0 else np.nan),
        ("NDF (% of DM)", (nutrient_vars["NDF"].X / dmi.X * 100) if dmi.X > 0 else np.nan),
        ("STARCH (% of DM)", (nutrient_vars["STARCH"].X / dmi.X * 100) if dmi.X > 0 else np.nan),
        ("FAT (% of DM)", (nutrient_vars["FAT"].X / dmi.X * 100) if dmi.X > 0 else np.nan),
        ("TFA (% of DM)", (tfa.X / dmi.X * 100) if dmi.X > 0 else np.nan),
        ("DNDF (% of DM)", (dndf.X / dmi.X * 100) if dmi.X > 0 else np.nan),
    ]
    results_df = pd.DataFrame(results_rows, columns=["Variable", "Value"])

    return results_df.round(4), feed_df.round(4)


# ----------------------------
# Grouping wrapper
# ----------------------------

def group_and_optimize(
    group_num: int,
    criteria: str,
    cow_df: pd.DataFrame,
    crop_nutrient_table: pd.DataFrame,
    feed_price_table: pd.DataFrame,  
    crop_min_max_table: pd.DataFrame,
    DM_vary: float,
    NEL_vary: float,
    methane_eqn: str = "NASEM",
    obj: str = "cost",
    methane_weight: float = 1.0,
    out_dir: Path = Path("."),
    verbose: bool = True,
) -> None:
    """
    Group cows and optimize each group, saving CSV outputs.

    Parameters
    ----------
    group_num
        1, 2, or 3.
    criteria
        'dim', 'nel', or 'milk' when group_num > 1.
    cow_df
        Must include columns used by util grouping functions (e.g., DMI, NEL, DIM, milk yield).
    out_dir
        Directory to write CSV files.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    criteria = criteria.strip().lower()
    if group_num not in {1, 2, 3}:
        raise ValueError("group_num must be 1, 2, or 3.")
    if group_num > 1 and criteria not in {"dim", "nel", "milk"}:
        raise ValueError("criteria must be one of: dim, nel, milk.")

    if verbose:
        print(f"Total number of cows: {len(cow_df)}")

    # --- grouping
    if group_num == 1:
        groups = [cow_df]
        if verbose:
            print(">>> No grouping (single group).")
    elif group_num == 2:
        if verbose:
            print(f">>> Grouping into 2 equal-size groups by '{criteria}'.")
        if criteria == "dim":
            groups = list(util.two_group_by_dim(cow_df))
        elif criteria == "nel":
            groups = list(util.two_group_by_nel(cow_df))
        else:
            groups = list(util.two_group_by_my(cow_df))
    else:
        if verbose:
            print(f">>> Grouping into 3 equal-size groups by '{criteria}'.")
        if criteria == "dim":
            groups = list(util.three_group_by_dim(cow_df))
        elif criteria == "nel":
            groups = list(util.three_group_by_nel(cow_df))
        else:
            groups = list(util.three_group_by_my(cow_df))

    # --- optimize each group
    for i, gdf in enumerate(groups, start=1):
        if verbose:
            print(f"\n=== Group {i} ===")
            print("Stats:", util.get_descriptive_stats(gdf))

        nutrient_req_table = util.construct_nutritional_req_table(
            DM_baseline=float(gdf["DMI"].mean()),
            NEL_baseline=float(np.percentile(gdf["NEL"], NEL_REQ_PERCENTILE)),
            DM_vary=float(DM_vary),
            NEL_vary=float(NEL_vary),
        )

        if verbose:
            print("Nutritional requirement table:")
            print(nutrient_req_table)

        results_df, feed_df = optimize_diet(
            animal_count=len(gdf),
            nutrient_req_table=nutrient_req_table,
            crop_nutrient_table=crop_nutrient_table,
            feed_price_table=feed_price_table,
            crop_min_max_table=crop_min_max_table,
            methane_eqn=methane_eqn,
            obj=obj,
            methane_weight=methane_weight,
            verbose=verbose,
        )

        if verbose:
            print(">>> Results:")
            print(results_df)
            print(">>> Feed:")
            print(feed_df)

        results_path = out_dir / f"results_group{i}.csv"
        feed_path = out_dir / f"feed_group{i}.csv"
        results_df.to_csv(results_path, index=False)
        feed_df.to_csv(feed_path, index=False)

    # Optional: print simple averages for 2 groups (kept from your original)
    if group_num == 2:
        try:
            r1 = pd.read_csv(out_dir / "results_group1.csv")
            r2 = pd.read_csv(out_dir / "results_group2.csv")
            avg_cost = (
                float(r1.loc[r1["Variable"] == "$/cow/d", "Value"].values[0])
                + float(r2.loc[r2["Variable"] == "$/cow/d", "Value"].values[0])
            ) / 2.0
            avg_methane = (
                float(r1.loc[r1["Variable"] == "methane (g/cow/d)", "Value"].values[0])
                + float(r2.loc[r2["Variable"] == "methane (g/cow/d)", "Value"].values[0])
            ) / 2.0
            if verbose:
                print(f"\nAvg cost across 2 groups: {avg_cost:.4f} $/cow/d")
                print(f"Avg methane across 2 groups: {avg_methane:.4f} g/cow/d")
        except Exception:
            # don't crash the public script because of a printing convenience
            pass


# ----------------------------
# CLI
# ----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Group cows and optimize diets with Gurobi.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    p.add_argument("--cow-path", type=Path, required=True, help="Path to cow_raw_data.csv")
    p.add_argument("--crop-path", type=Path, required=True, help="Path to selected_nutrients_*.csv for crop library")
    p.add_argument("--feed-price-path", type=Path, default=Path("./data/example_feed_price.csv"), help="Path to feed price CSV")
    p.add_argument("--crop-min-max-path", type=Path, default=Path("./data/example_min_max_crop_in_diet.csv"), help="Path to crop min/max inclusion CSV")

    p.add_argument("--group-num", type=int, default=1, choices=[1, 2, 3], help="Number of nutritional groups")
    p.add_argument("--criteria", type=str, default="milk", choices=["dim", "nel", "milk"], help="Grouping criterion")

    p.add_argument("--dm-vary", type=float, default=0.01, help="DMI requirement variation (fraction or absolute per your util)")
    p.add_argument("--nel-vary", type=float, default=0.01, help="NEL requirement variation (fraction or absolute per your util)")

    p.add_argument("--methane-eqn", type=str, default="NASEM", choices=["NASEM", "Ellis", "ELLIS"], help="Methane equation")
    p.add_argument("--obj", type=str, default="cost", choices=["cost", "methane", "both"], help="Objective function")
    p.add_argument("--methane-weight", type=float, default=1.0, help="Weight on methane if obj='both' (cost + w*methane)")

    p.add_argument("--out-dir", type=Path, default=Path("./outputs"), help="Output directory for CSV results")
    p.add_argument("--quiet", action="store_true", help="Suppress solver/log prints")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Load inputs
    if not args.crop_path.exists():
        raise FileNotFoundError(f"Crop file not found: {args.crop_path}")
    if not args.cow_path.exists():
        raise FileNotFoundError(f"Cow file not found: {args.cow_path}")

    crop_nutrient_table = util.get_farm_crop_library_table(str(args.crop_path))
    cow_df = util.get_cow_raw_data(str(args.cow_path))
    feed_price_table = util.get_feed_price_table(str(args.feed_price_path))
    crop_min_max_table = util.get_min_max_feed_table(str(args.crop_min_max_path))

    group_and_optimize(
        group_num=args.group_num,
        criteria=args.criteria,
        cow_df=cow_df,
        crop_nutrient_table=crop_nutrient_table,
        feed_price_table=feed_price_table,
        crop_min_max_table=crop_min_max_table,
        DM_vary=args.dm_vary,
        NEL_vary=args.nel_vary,
        methane_eqn=args.methane_eqn,
        obj=args.obj,
        methane_weight=args.methane_weight,
        out_dir=args.out_dir,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
