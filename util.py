"""
Utility functions for dairy diet optimization.

This module provides helper functions for:
- Constructing nutrient requirement tables
- Loading crop libraries, feed prices, and cow data
- Grouping cows into nutritional groups
- Post-processing diets (nutrient composition, cost, methane)

All functions are written to be reusable, transparent, and suitable
for public release and academic reproducibility.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class Utility:
    """
    Collection of static helper functions used by the diet optimization model.

    Notes
    -----
    - Units matter. Carefully check whether quantities are expressed as:
        * as-fed (kg)
        * dry matter (kg DM)
        * fraction of DM (0–1) or percent of DM (0–100)
    - Ingredient names must be consistent across all input tables.
    """

    #: Percentile of herd NEL distribution used to define energy requirements
    NEL_req_percentile: int = 83

    # ------------------------------------------------------------------
    # Nutritional requirement construction
    # ------------------------------------------------------------------

    @staticmethod
    def construct_nutritional_req_table(
        DM_baseline: float,
        NEL_baseline: float,
        DM_vary: float,
        NEL_vary: float,
    ) -> pd.DataFrame:
        """
        Construct a min/max nutrient requirement table for a cow group.

        Parameters
        ----------
        DM_baseline
            Baseline dry matter intake (kg DM/cow/day).
        NEL_baseline
            Baseline net energy for lactation (Mcal/kg DM).
        DM_vary
            Fractional variation applied to DM requirement (e.g., 0.03 = ±3%).
        NEL_vary
            Fractional variation applied to NEL requirement (e.g., 0.03 = ±3%).

        Returns
        -------
        pandas.DataFrame
            Nutrient requirement table indexed by nutrient name with
            columns ['min', 'max'], expressed in kg or Mcal per cow per day.
        """

        # Nutrient bounds expressed as fractions of DM
        CP_min, CP_max = 0.15, 0.20
        STARCH_min, STARCH_max = 0.22, 0.30
        FAT_min, FAT_max = 0.00, 0.07
        NDF_min, NDF_max = 0.25, 0.33

        nutrient_data = {
            "minmax": ["min", "max"],
            "DM": [
                DM_baseline * (1 - DM_vary),
                DM_baseline * (1 + DM_vary),
            ],
            "NEL": [
                DM_baseline * NEL_baseline * (1 - NEL_vary),
                DM_baseline * NEL_baseline * (1 + NEL_vary),
            ],
            "CP": [DM_baseline * CP_min, DM_baseline * CP_max],
            "NDF": [DM_baseline * NDF_min, DM_baseline * NDF_max],
            "STARCH": [DM_baseline * STARCH_min, DM_baseline * STARCH_max],
            "FAT": [DM_baseline * FAT_min, DM_baseline * FAT_max],
        }

        return pd.DataFrame(nutrient_data).set_index("minmax").T

    # ------------------------------------------------------------------
    # Data loading utilities
    # ------------------------------------------------------------------

    @staticmethod
    def get_farm_crop_library_table(path: str) -> pd.DataFrame:
        """
        Load and standardize a crop nutrient library CSV.

        Expected columns (before renaming):
        - 'DM, % as fed'
        - 'NEL (Mcal/kg)'
        - 'CP, % DM'
        - 'NDF, % DM'
        - 'Starch, % DM'
        - 'Crude fat, % DM'
        - 'TFAs, % DM'
        - 'DNDF, %DM'

        Returns
        -------
        pandas.DataFrame
            Indexed by ingredient name with nutrient values expressed
            as fractions (0–1) where appropriate.
        """

        crop_nutrient = pd.read_csv(path)

        crop_nutrient = crop_nutrient.rename(
            columns={
                "DM, % as fed": "DM",
                "DE base, Mcal/kg": "DE",
                "ME (Mcal/kg)": "ME",
                "NEL (Mcal/kg)": "NEL",
                "CP, % DM": "CP",
                "NDF, % DM": "NDF",
                "Starch, % DM": "STARCH",
                "Crude fat, % DM": "FAT",
                "TFAs, % DM": "TFA",
                "DNDF, %DM": "DNDF",
            }
        )

        # Convert percentages to fractions
        for col in ["DM", "CP", "NDF", "STARCH", "FAT", "TFA", "DNDF"]:
            if col in crop_nutrient.columns:
                crop_nutrient[col] /= 100.0

        return crop_nutrient.set_index("index")

    @staticmethod
    def get_min_max_feed_table(path: str = "./data/min_max_crop_in_diet.csv") -> pd.DataFrame:
        """
        Load ingredient-level minimum and maximum inclusion rates.

        Parameters
        ----------
        path
            Path to CSV with columns ['Ingredient', 'min', 'max']
            expressed as kg as-fed per cow per day.

        Returns
        -------
        pandas.DataFrame
            Indexed by ingredient name.
        """

        return pd.read_csv(path).set_index("Ingredient")

    @staticmethod
    def get_feed_price_table(path: str) -> pd.DataFrame:
        """
        Load feed prices.

        Parameters
        ----------
        path
            Path to CSV with columns ['Ingredient', 'price ($/kg)'].
        """

        return pd.read_csv(path).set_index("Ingredient")

    @staticmethod
    def get_cow_raw_data(csv_path: str) -> pd.DataFrame:
        """
        Load raw cow-level data.

        The CSV must include, at minimum:
        - DMI
        - NEL
        plus any columns required for grouping (DIM, MILK, etc.).
        """

        return pd.read_csv(csv_path)

    # ------------------------------------------------------------------
    # Grouping utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _split_into_n_groups(sorted_df: pd.DataFrame, n: int):
        size = len(sorted_df)
        return tuple(
            sorted_df.iloc[i * size // n : (i + 1) * size // n]
            for i in range(n)
        )

    @staticmethod
    def two_group_by_dim(cow_df: pd.DataFrame):
        return Utility._split_into_n_groups(cow_df.sort_values("DIM"), 2)

    @staticmethod
    def two_group_by_nel(cow_df: pd.DataFrame):
        return Utility._split_into_n_groups(cow_df.sort_values("NEL"), 2)

    @staticmethod
    def two_group_by_my(cow_df: pd.DataFrame):
        return Utility._split_into_n_groups(cow_df.sort_values("MILK"), 2)

    @staticmethod
    def three_group_by_dim(cow_df: pd.DataFrame):
        return Utility._split_into_n_groups(cow_df.sort_values("DIM"), 3)

    @staticmethod
    def three_group_by_nel(cow_df: pd.DataFrame):
        return Utility._split_into_n_groups(cow_df.sort_values("NEL"), 3)

    @staticmethod
    def three_group_by_my(cow_df: pd.DataFrame):
        return Utility._split_into_n_groups(cow_df.sort_values("MILK"), 3)

    # ------------------------------------------------------------------
    # Diagnostics and post-processing
    # ------------------------------------------------------------------

    @staticmethod
    def get_descriptive_stats(cow_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute simple descriptive statistics for a cow group.
        """

        stats = {}
        for col in cow_df.columns:
            if col != "ID":
                stats[f"{col}_mean"] = cow_df[col].mean()
                stats[f"{col}_std"] = cow_df[col].std()

        stats["NEL_req"] = np.percentile(
            cow_df["NEL"], Utility.NEL_req_percentile
        )

        return pd.DataFrame.from_dict(stats, orient="index", columns=["value"])

    @staticmethod
    def calc_nutrient_composition(
        diet_df: pd.DataFrame,
        crop_nutrient_table: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Calculate nutrient composition of a diet.

        Parameters
        ----------
        diet_df
            DataFrame with columns ['Ingredient', 'As fed'].
        crop_nutrient_table
            Crop nutrient library indexed by ingredient.

        Returns
        -------
        pandas.DataFrame
            Single-row DataFrame summarizing diet composition.
        """

        total_as_fed = diet_df["As fed"].sum()
        total_dm = (
            diet_df["As fed"]
            * crop_nutrient_table.loc[diet_df["Ingredient"], "DM"].values
        ).sum()

        out = {
            "Total as fed": total_as_fed,
            "Total DM": total_dm,
            "DM%": 100 * total_dm / total_as_fed,
        }

        for nutrient in ["NEL", "DE", "ME", "CP", "NDF", "STARCH", "FAT", "TFA", "DNDF"]:
            if nutrient in crop_nutrient_table.columns:
                out[nutrient] = (
                    diet_df["As fed"]
                    * crop_nutrient_table.loc[diet_df["Ingredient"], "DM"].values
                    * crop_nutrient_table.loc[diet_df["Ingredient"], nutrient].values
                ).sum() / total_dm

        # Convert selected nutrients to % of DM
        for nutrient in ["CP", "NDF", "STARCH", "FAT", "TFA", "DNDF"]:
            if nutrient in out:
                out[nutrient] *= 100

        return pd.DataFrame([out])

    @staticmethod
    def calc_price(diet_df: pd.DataFrame, price_df: pd.DataFrame) -> float:
        """
        Calculate feed cost for a diet.
        """

        return float(
            (diet_df["As fed"] * price_df.loc[diet_df["Ingredient"], "price ($/kg)"].values).sum()
        )

    @staticmethod
    def calc_methane(nutrient_df: pd.DataFrame, methane_eqn: str) -> float:
        """
        Calculate enteric methane emissions (kg/cow/day).

        Parameters
        ----------
        nutrient_df
            Output from `calc_nutrient_composition`.
        methane_eqn
            'NASEM' or 'Ellis'.
        """

        methane_eqn = methane_eqn.upper()

        if methane_eqn == "NASEM":
            methane = (
                0.294 * nutrient_df["Total DM"]
                - 0.347 * nutrient_df["TFA"]
                + 0.0409 * nutrient_df["DNDF"]
            ) * 4.184 / 55.65

        elif methane_eqn == "ELLIS":
            me = 1.818 * nutrient_df["Total DM"] * nutrient_df["NEL"] - 0.2319
            methane = (
                4.41 + 0.0224 * 4.184 * me
                + 0.98 * nutrient_df["Total DM"] * nutrient_df["NDF"] / 100
            ) / 55.65

        else:
            raise ValueError("methane_eqn must be 'NASEM' or 'Ellis'.")

        return float(methane)
