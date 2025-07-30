import pandas as pd
import numpy as np

class Utility:
    NEL_req_percentile = 83

    ## nutritional requirements
    def construct_nutritional_req_table(DM_baseline, NEL_baseline, DM_vary, NEL_vary):
        """
        construct_nutritional_req_table

        Parameters
        ----------
        DM_baseline: float
            suggested DMI (kg/cow/d) from the NASEM or the actual DMI from the farm 

        NEL_baseline: float
            suggested NEL (Mcal/kg DMI) from the NASEM or the actual DMI from the farm 

        DM_vary: float
            a fraction value controlling the DM requirement variation (e.g. default of 0.03 is the DM_baseline plus and minus 3%)
        
        DM_vary: float
            a fraction value controlling the NEL requirement variation (e.g. default of 0.03 is the NEL_baseline plus and minus 3%)
        """
        # DM = 27
        # NEL = 1.86
        CP_min_pct_in_DM = 0.15
        CP_max_pct_in_DM = 0.20
        STARCH_min_pct_in_DM = 0.22
        STARCH_max_pct_in_DM = 0.30
        FAT_min_pct_in_DM = 0
        FAT_max_pct_in_DM = 0.07
        NDF_min_pct_in_DM = 0.25
        NDF_max_pct_in_DM = 0.33
        nutrient_data = {'minmax':['min', 'max'],
                'DM': [DM_baseline *(1-DM_vary), DM_baseline *(1+DM_vary)],
                'NEL': [DM_baseline * NEL_baseline *(1-NEL_vary), DM_baseline * NEL_baseline *(1+NEL_vary)],
                'CP': [DM_baseline * CP_min_pct_in_DM, DM_baseline * CP_max_pct_in_DM],
                'NDF': [DM_baseline * NDF_min_pct_in_DM, DM_baseline * NDF_max_pct_in_DM],
                'STARCH': [DM_baseline * STARCH_min_pct_in_DM, DM_baseline * STARCH_max_pct_in_DM],
                'FAT': [DM_baseline * FAT_min_pct_in_DM, DM_baseline * FAT_max_pct_in_DM]
            }
        nutrient_req_table = pd.DataFrame(nutrient_data)
        nutrient_req_table = nutrient_req_table.set_index('minmax').T
        return nutrient_req_table

    def get_farm_crop_library_table():
        # Read the crop library from the CSV file
        crop_nutrient = pd.read_csv("./data/selected_nutrients_Arlington.csv")
        crop_nutrient.rename(columns={
            'DM, % as fed': 'DM',
            'DE base, Mcal/kg': 'DE',
            'ME (Mcal/kg)': 'ME',
            'NEL (Mcal/kg)': 'NEL',
            'CP, % DM': 'CP',
            'NDF, % DM': 'NDF',
            'Starch, % DM': 'STARCH',
            'Crude fat, % DM': 'FAT',
            'TFAs, % DM': 'TFA',
            'DNDF, %DM': 'DNDF'
        }, inplace=True)
        crop_nutrient.loc[:, 'DM'] /= 100
        crop_nutrient.loc[:, 'NDF'] /= 100
        crop_nutrient.loc[:, 'STARCH'] /= 100
        crop_nutrient.loc[:, 'CP'] /= 100
        crop_nutrient.loc[:, 'FAT'] /= 100
        crop_nutrient.loc[:, 'TFA'] /= 100
        crop_nutrient.loc[:, 'DNDF'] /= 100
        crop_nutrient_table = crop_nutrient.set_index('index')
        # crop_nutrient_table = crop_nutrient_table.fillna(0)
        return crop_nutrient_table
    
    def get_min_max_feed_table():
        # PLACEHOLDER FOR NOW
        # Read the min and max feed amounts (unit: kg (as fed)) from the CSV file
        # users can change the csv path, but usually considered static
        crop_min_max_df = pd.read_csv("./data/min_max_crop_in_diet.csv").set_index('Ingredient')
        return crop_min_max_df

    def get_cow_raw_data(csv_path):
        # LACT	DIM	MILK	FAT	PROTEIN	BW	DMI NEL
        # BW (eqn.?), DMI (eqn.2-1), NEL (eqns.?) estimated by NASEM equation
        # DMI was corrected by a correction factor to match the actual DMI measured in Arlington
        cow_df = pd.read_csv(csv_path)
        return cow_df
    
    def two_group_by_dim(cow_df):
        sorted_df = cow_df.sort_values(by='DIM').reset_index(drop=True)
        mid_index = len(sorted_df) // 2
        group1_df = sorted_df.iloc[:mid_index]  # First half
        group2_df = sorted_df.iloc[mid_index:]  # Second half
        return group1_df, group2_df
    
    def two_group_by_nel(cow_df):
        sorted_df = cow_df.sort_values(by='NEL').reset_index(drop=True)
        mid_index = len(sorted_df) // 2
        group1_df = sorted_df.iloc[:mid_index]  # First half
        group2_df = sorted_df.iloc[mid_index:]  # Second half
        return group1_df, group2_df
    
    def two_group_by_my(cow_df):
        sorted_df = cow_df.sort_values(by='MILK').reset_index(drop=True)
        mid_index = len(sorted_df) // 2
        group1_df = sorted_df.iloc[:mid_index]  # First half
        group2_df = sorted_df.iloc[mid_index:]  # Second half
        return group1_df, group2_df
    
    def three_group_by_dim(cow_df):
        sorted_df = cow_df.sort_values(by='DIM').reset_index(drop=True)
        group1_df = sorted_df.iloc[:len(sorted_df)//3]
        group2_df = sorted_df.iloc[len(sorted_df)//3:2*len(sorted_df)//3]
        group3_df = sorted_df.iloc[2*len(sorted_df)//3:]
        return group1_df, group2_df, group3_df
    
    def three_group_by_nel(cow_df):
        sorted_df = cow_df.sort_values(by='NEL').reset_index(drop=True)
        group1_df = sorted_df.iloc[:len(sorted_df)//3]
        group2_df = sorted_df.iloc[len(sorted_df)//3:2*len(sorted_df)//3]
        group3_df = sorted_df.iloc[2*len(sorted_df)//3:]
        return group1_df, group2_df, group3_df
    
    def three_group_by_my(cow_df):
        sorted_df = cow_df.sort_values(by='MILK').reset_index(drop=True)
        group1_df = sorted_df.iloc[:len(sorted_df)//3]
        group2_df = sorted_df.iloc[len(sorted_df)//3:2*len(sorted_df)//3]
        group3_df = sorted_df.iloc[2*len(sorted_df)//3:]
        return group1_df, group2_df, group3_df

    @staticmethod
    def get_descriptive_stats(cow_df):
        # Calculate descriptive statistics
        print("cow number:", len(cow_df))
        stats = {}
        for k in cow_df.keys():
            if k != 'ID':
                stats[k+'_mean'] = cow_df[k].mean(),
                stats[k+'_std'] = cow_df[k].std()
        stats['NEL_req'] = np.percentile(cow_df['NEL'], Utility.NEL_req_percentile) # NOTE: this is the 81.8 percentile of NEL, based on Arlington data (Pupo, 2024)
        stats_df = pd.DataFrame(stats).transpose()
        return stats_df
    
    def calc_nutrient_composition(crop_df, crop_nutrient_table):
        # Calculate the nutrient composition of a given diet
        nutrient_composition = {}
        total_as_fed = crop_df['As fed'].sum()
        total_dmi = (crop_df['As fed'] * crop_nutrient_table['DM'].values).sum()
        nutrient_composition['Total as fed'] = total_as_fed
        nutrient_composition['Total DM'] = total_dmi
        nutrient_composition['DM%'] = total_dmi/total_as_fed * 100
        for nutrient in ['NEL', 'DE', 'ME', 'CP', 'NDF', 'STARCH', 'FAT', 'TFA', 'DNDF']:
            nutrient_composition[nutrient] = (
                (crop_df['As fed'] * crop_nutrient_table['DM'].values * crop_nutrient_table[nutrient].values).sum() / total_dmi
            )
        # Convert to percentage
        for nutrient in ['CP', 'NDF', 'STARCH', 'FAT', 'TFA', 'DNDF']:
            nutrient_composition[nutrient] = nutrient_composition[nutrient] * 100
        return pd.DataFrame([nutrient_composition])
    
    def calc_methane(nutrient_composition, methane_eqn):
        # nutrient_composition the dataframe from calc_nutrient_composition()
        # methane_eqn: 'NASEM' or 'Ellis'
        # return methane (kg/cow/d)
        if methane_eqn == 'NASEM':
            methane = (0.294 *nutrient_composition['Total DM'] - 0.347 * nutrient_composition['TFA'] + 0.0409 * nutrient_composition['DNDF'])*4.184/55.65
        elif methane_eqn == 'Ellis':
            me = 1.818 * nutrient_composition['Total DM']*nutrient_composition['NEL'] - 0.2319
            methane = (4.41 + 0.0224 * 4.184 * me + 0.98 * nutrient_composition['Total DM']*nutrient_composition['NDF']/100)/55.65,
            # or use directly 'nutrient_composition['Total DM']* nutrient_composition['ME']', but this gives lower methane
        return methane