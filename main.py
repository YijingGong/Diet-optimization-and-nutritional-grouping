import pandas as pd
import numpy as np
from gurobipy import Model, GRB
from util import Utility as util

NEL_req_percentile = util.NEL_req_percentile
w = 1 # weight for methane in the weighted sum combined objective function
# cp_price = 0.59 # $/kg
# nel_price = 0.06 # $/Mcal

def optimize(animal_count, nutrient_req_table, crop_nutrient_table, methane_eqn, obj):
    """
    Optimize the diet of cows to minimize methane emissions while meeting nutritional requirements.
    Args:
        animal_count (int): Number of cows.
        crops (list): List of crops available on the farm.
        market_crops (list): List of crops available in the market.
        nutrient_req_table (pd.DataFrame): Nutritional requirements table for these cows.
        crop_nutrient_table (pd.DataFrame): Nutritional content of farm crops.
        market_crop_nutrient_table (pd.DataFrame): Nutritional content of market crops.
    """
    print(">>>Starting optimization...")
    # Model setup
    m = Model("diet_optimization")

    # set
    other_nutrients = ["NEL", "CP", "NDF", "STARCH", "FAT"]
    crops = list(crop_nutrient_table.index)
    # print(">>>Crops available on the farm:", crops)
    # print(crop_nutrient_table)

    # Decision variable
    dmi = m.addVar(name="dmi", lb=0) # kg/cow/d
    feed_on_farm = m.addVars(crops, lb=0, name="feed_on_farm") # kg/d for whole herd
    # for methane calculation
    nel = m.addVar(lb=0, name="nel") # Mcal/cow/d
    me = m.addVar(lb=0, name="me") # Mcal/cow/d
    cp = m.addVar(lb=0, name="cp") # kg/cow/d
    ndf = m.addVar(lb=0, name="ndf") # kg/cow/d
    tfa = m.addVar(lb=0, name="tfa") # kg/cow/d
    dndf = m.addVar(lb=0, name="dndf") # kg/cow/d
    methane = m.addVar(lb=0, name="methane") # kg/cow/d
    cost = m.addVar(lb=0, name="cost") # $/cow/d

    # Nutrient variables for results
    nutrient_vars = {n: m.addVar(lb=0, name=f"{n.lower()}") for n in other_nutrients}

    # PART 1: DMI & NUTRIENTS CONSTRAINTS
    m.addConstr(
        dmi == 
        (
            sum(feed_on_farm[c] * crop_nutrient_table.loc[c,'DM'] for c in crops) 
        )/animal_count,
        name="dmi_calc"
    )

    m.addConstr(
        dmi >= nutrient_req_table.loc['DM', 'min'],
        name="dmi_min"
    )

    m.addConstr(
        dmi <= nutrient_req_table.loc['DM', 'max'],
        name="dmi_max"
    )

    for n in other_nutrients:
        m.addConstr(
            nutrient_vars[n] ==
            (
                sum(feed_on_farm[c] * crop_nutrient_table.loc[c,'DM'] * crop_nutrient_table.loc[c,n] for c in crops) 
            ) / animal_count,
            name=f"{n.lower()}_calc"
        )
        m.addConstr(
            nutrient_vars[n] <= nutrient_req_table.loc[n, 'max'],
            name=f"{n.lower()}_calc_max"
        )
        m.addConstr(
            nutrient_vars[n] >= nutrient_req_table.loc[n, 'min'],
            name=f"{n.lower()}_calc_min"
        )

    # forage constraint (forage take 40% to 60% of DM)
    m.addConstr(
        (
            feed_on_farm['Corn silage'] * crop_nutrient_table.loc['Corn silage','DM']
         + 
            feed_on_farm['Legume silage, mid maturity'] * crop_nutrient_table.loc['Legume silage, mid maturity','DM']
         )/animal_count >= 0.4 * dmi,
        name="forage_min"
    )

    m.addConstr(
        (
            feed_on_farm['Corn silage'] * crop_nutrient_table.loc['Corn silage','DM']
         + 
            feed_on_farm['Legume silage, mid maturity'] * crop_nutrient_table.loc['Legume silage, mid maturity','DM']
         )/animal_count <= 0.6 * dmi,
        name="forage_max"
    )

    # PART 2: FEED MIN MAX CONSTRAINTS
    crop_min_max_df = util.get_min_max_feed_table()
    for c in crops:
        m.addConstr(feed_on_farm[c]/animal_count >= crop_min_max_df.loc[c, 'min'], name=f"min_crop_{c}")
        m.addConstr(feed_on_farm[c]/animal_count <= crop_min_max_df.loc[c, 'max'], name=f"max_crop_{c}")

    # PART 3: OPTIONAL SPECIAL CROP CONSTRAINTS
    m.addConstr(feed_on_farm['Corn silage'] >= feed_on_farm['Legume silage, mid maturity'], name=f"land_constraint1")
    m.addConstr(feed_on_farm['Corn silage'] <= 2*feed_on_farm['Legume silage, mid maturity'], name=f"land_constraint2")

    # PART 4: CALC ENTERIC METHANE
    m.addConstr(
        nel ==
        (
            sum(feed_on_farm[c] * crop_nutrient_table.loc[c,'DM'] * crop_nutrient_table.loc[c,'NEL'] for c in crops) 
        ) / animal_count,
        name="nel_calc"
    )

    m.addConstr(
        me == 1.818 * nel - 0.2319,
        name="me_calc"
    )

    m.addConstr(
        cp ==
        (
            sum(feed_on_farm[c] * crop_nutrient_table.loc[c,'DM'] * crop_nutrient_table.loc[c,'CP'] for c in crops) 
        ) / animal_count,
        name="cp_calc"
    )

    m.addConstr(
        ndf ==
        (
            sum(feed_on_farm[c] * crop_nutrient_table.loc[c,'DM'] * crop_nutrient_table.loc[c,'NDF'] for c in crops) 
        ) / animal_count,
        name="ndf_calc"
    )

    m.addConstr(
        tfa ==
        (
            sum(feed_on_farm[c] * crop_nutrient_table.loc[c,'DM'] * crop_nutrient_table.loc[c,'TFA'] for c in crops) 
        ) / animal_count,
        name="tfa_calc"
    )

    m.addConstr(
        dndf ==
        (
            sum(feed_on_farm[c] * crop_nutrient_table.loc[c,'DM'] * crop_nutrient_table.loc[c,'DNDF'] for c in crops) 
        ) / animal_count,
        name="dndf_calc"
    )

    price_df = util.get_feed_price_table()
    m.addConstr(
        # cost == cp*cp_price + nel*nel_price,
        cost == 
        (
            sum(feed_on_farm[c] * price_df.loc[c,'price ($/kg)'] for c in crops)
        ) / animal_count,
        name="cost_calc"
    )

    if methane_eqn == 'Ellis':
        # equation unit is MJ/d, need to convert to kg based on the energy density of methane (55.65 MJ/kg) (IPCC, 2019).
        # this is per cow
        m.addConstr(
            methane == (4.41 + 0.0224 * 4.184 * me + 0.98 * ndf)/55.65,
            name="methane_calc"
        )
    elif methane_eqn == 'NASEM':
        # equation unit is Mcal/d, need to convert to MJ (1Mcal = 4.184MJ), then to kg
        m.addConstr(
            methane == (0.294 *dmi - 0.347 * (tfa/dmi)*100 + 0.0409 * (dndf/dmi)*100)*4.184/55.65,
            name="methane_calc"
        )
    else:
        raise ValueError("Invalid methane equation. Use 'Ellis' or 'NASEM'.")

    # Objective
    if obj == 'methane':
        m.setObjective(methane, GRB.MINIMIZE)
    elif obj == 'cost':
        m.setObjective(cost, GRB.MINIMIZE)
    elif obj == 'both':
        m.setObjective(cost + w * methane, GRB.MINIMIZE)
    else:
        raise ValueError("Invalid objective function. Use 'methane', 'cost', or 'both'.")

    # Solve
    m.optimize()

    # Create a dataframe for feed_on_farm and feed_purchased
    feed_data = []
    total_as_fed = sum(feed_on_farm[c].X for c in crops)/animal_count
    for c in crops:
        if feed_on_farm[c].X > 0.01:
            feed_data.append({"Ingredient": c, "Amount as fed (kg/cow/d)": feed_on_farm[c].X/animal_count})
    feed_df = pd.DataFrame(feed_data)

    # Save solution
    # Create a dataframe for dmi, nel, ndf, methane, and other nutrients
    results_data = {
        "Variable": ["$/cow/d", "methane (g/cow/d)", "dmi (kg/cow/d)", "dm (%)", "NEL (Mcal/kg)", "CP (% in DM)", "NDF (% in DM)", "STARCH (% in DM)", "FAT (% in DM)", "TFA (% in DM)", "DNDF (% in DM)"], 
        "Value": [cost.X, methane.X*1000, dmi.X, dmi.X/total_as_fed*100, nel.X/dmi.X] + [nutrient_vars[n].X/dmi.X*100 for n in other_nutrients if n != 'NEL'] + [tfa.X/dmi.X*100, dndf.X/dmi.X*100]
    }
    results_df = pd.DataFrame(results_data)

    return results_df.round(2), feed_df.round(2)

def group_and_opt(group_num, criteria, cow_df, crop_nutrient_table, DM_vary, NEL_vary, methane_eqn='NASEM', obj='cost'):
    """
    Group cows based on the specified criteria and optimize their diet.
    Args:
        criteria (str): The criteria for grouping cows ('dim', 'nel', or 'milk').
        group_num (int): The number of groups to create.
        cow_df (pd.DataFrame): Dataframe containing cow data.
        crops (list): List of crops available on the farm.
        market_crops (list): List of crops available in the market.
        crop_nutrient_table (pd.DataFrame): Nutritional content of farm crops.
        market_crop_nutrient_table (pd.DataFrame): Nutritional content of market crops.
    """
    print(f"Total number of cows: {len(cow_df)}")
    if group_num == 1:
        print(">>>No grouping")
        group1_df = cow_df
    elif group_num == 2:
        print(">>>Grouping into 2 groups with same size based on", criteria)
        if criteria == 'dim':
            group1_df, group2_df = util.two_group_by_dim(cow_df)
        elif criteria == 'nel':
            group1_df, group2_df = util.two_group_by_nel(cow_df)
        elif criteria == 'milk':
            group1_df, group2_df = util.two_group_by_my(cow_df)
        else:
            raise ValueError("Invalid criteria. Use 'dim', 'nel', or 'milk'.")
    elif group_num == 3:
        print(">>>Grouping into 3 groups with same size based on", criteria)
        if criteria == 'dim':
            group1_df, group2_df, group3_df = util.three_group_by_dim(cow_df)
        elif criteria == 'nel':
            group1_df, group2_df, group3_df = util.three_group_by_nel(cow_df)
        elif criteria == 'milk':
            group1_df, group2_df, group3_df = util.three_group_by_my(cow_df)
        else:
            raise ValueError("Invalid criteria. Use 'dim', 'nel', or 'milk'.")
    else:
        raise ValueError("Invalid group number. Use 1, 2, or 3.")

    print("Group 1 stats:", util.get_descriptive_stats(group1_df))
    nutrient_req_table1 = util.construct_nutritional_req_table(DM_baseline=group1_df['DMI'].mean(), NEL_baseline=np.percentile(group1_df['NEL'], NEL_req_percentile), DM_vary=DM_vary, NEL_vary=NEL_vary)
    print("Nutritional requirement table for Group 1:")
    print(nutrient_req_table1)
    results_df1, feed_df1 = optimize(len(group1_df), nutrient_req_table1, crop_nutrient_table, methane_eqn=methane_eqn, obj=obj)
    print(">>>Results for Group 1:")
    print(results_df1)
    print(">>>Feed for Group 1:")
    print(feed_df1)
    results_df1.to_csv('results_group1.csv', index=False)
    feed_df1.to_csv('feed_group1.csv', index=False)

    if group_num >= 2:
        print("Group 2 stats:", util.get_descriptive_stats(group2_df))
        nutrient_req_table2 = util.construct_nutritional_req_table(DM_baseline=group2_df['DMI'].mean(), NEL_baseline=np.percentile(group2_df['NEL'], NEL_req_percentile), DM_vary=DM_vary, NEL_vary=NEL_vary)
        results_df2, feed_df2 = optimize(len(group2_df), nutrient_req_table2, crop_nutrient_table, methane_eqn=methane_eqn, obj=obj)
        print(">>>Results for Group 2:")
        print(results_df2)
        print(">>>Feed for Group 2:")
        print(feed_df2)
        results_df2.to_csv('results_group2.csv', index=False) 
        feed_df2.to_csv('feed_group2.csv', index=False)
        print("avg cost:", (results_df1.loc[results_df1['Variable'] == '$/cow/d', 'Value'].values[0]+results_df2.loc[results_df2['Variable'] == '$/cow/d', 'Value'].values[0])/2)
        print("avg methane:", (results_df1.loc[results_df1['Variable'] == 'methane (g/cow/d)', 'Value'].values[0]+results_df2.loc[results_df2['Variable'] == 'methane (g/cow/d)', 'Value'].values[0])/2)
    
        if group_num == 3: # Group 3 (if applicable)
            print("Group 3 stats:", util.get_descriptive_stats(group3_df))
            nutrient_req_table3 = util.construct_nutritional_req_table(DM_baseline=group3_df['DMI'].mean(), NEL_baseline=np.percentile(group3_df['NEL'], NEL_req_percentile), DM_vary=DM_vary, NEL_vary=NEL_vary)
            results_df3, feed_df3 = optimize(len(group3_df), nutrient_req_table3, crop_nutrient_table, methane_eqn=methane_eqn, obj=obj)
            print(">>>Results for Group 3:")
            print(results_df3)
            print(">>>Feed for Group 3:")
            print(feed_df3)
            results_df3.to_csv('results_group3.csv', index=False) 
            feed_df3.to_csv('feed_group3.csv', index=False)

# # Crop info # considered static in this study
crop_path = "./data/selected_nutrients_Arlington.csv"
crop_nutrient_table = util.get_farm_crop_library_table(crop_path)
print(crop_nutrient_table)

# # Check existing diet
# diet_df = pd.read_csv('./data/current_Arlington_diet.csv')
# price_df = pd.read_csv('./data/feed_price.csv')
# print(diet_df)
# nutrient_composition_df = util.calc_nutrient_composition(diet_df, crop_nutrient_table)
# print(nutrient_composition_df.T)
# price = util.calc_price(diet_df, price_df)
# print("feed cost per cow per day: ", price)
# methane = util.calc_methane(nutrient_composition_df, 'NASEM')
# print("NASEM methane:", methane)
# methane = util.calc_methane(nutrient_composition_df, 'Ellis')
# print("Ellis methane:", methane)

# Animals
DM_vary = 0.01
NEL_vary = 0.01
cow_df = util.get_cow_raw_data('./data/cow_raw_data.csv') 
group_and_opt(2,'milk', cow_df, crop_nutrient_table, DM_vary, NEL_vary, methane_eqn='NASEM', obj = 'both')

