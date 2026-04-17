# -*- coding: utf-8 -*-
"""
Steel Production Optimization Model - Reorganized Version
Author: Bruna (reorganized with assistance)
Date: January 2026

This model optimizes steel production capacity expansion to meet production targets
while minimizing costs (CAPEX + OPEX) and respecting emission limits.
"""

#==============================================================================
# SECTION 1: IMPORT LIBRARIES
#==============================================================================

import pandas as pd
import numpy as np
from pyomo.environ import (
    ConcreteModel, Set, Var, Param, Constraint, Objective, NonNegativeReals,
    minimize
)
from pyomo.opt import SolverFactory
from amplpy import modules
import matplotlib.pyplot as plt
import os

#==============================================================================
# SECTION 2: LOAD RAW DATA
#==============================================================================

# Load existing plants data
plants = pd.read_excel('Plants_teste_chris.xlsx')

# Load technology parameters (CAPEX, OPEX, emission intensity, etc.)
tecnologias = pd.read_csv('Tecnologias_v2.csv', sep=";")
tecnologias.set_index('Route', inplace=True)

# Load historical steel production by route (kt)
steel_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/steel_production.csv')
steel_production = steel_production.set_index('Year')
steel_production['Total'] = steel_production.sum(axis=1)

# Load pig iron production to calculate BF-BOF CC vs MC shares
pig_iron_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Pig_iron_production_2.csv')
pig_iron_production = pig_iron_production.set_index('Ano')
pig_iron_production['Share BF-BOF CC'] = (
    pig_iron_production['Integrada CV'] / 
    (pig_iron_production['Integrada CV'] + pig_iron_production['Integrada CM'])
)
pig_iron_production['Share BF-BOF MC'] = 1 - pig_iron_production['Share BF-BOF CC']

# Load scrap supply data
scrap_supply = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Scrap_supply.csv')
scrap_supply = scrap_supply.set_index('Recovery_rate')

# Load emission factors
emission_factor = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/emission_factor.csv')
emission_factor = emission_factor.set_index('Combustivel')
emission_factor['CO2e'] = (
    emission_factor['CO2'] + 
    emission_factor['CH4'] * 28 + 
    emission_factor['N2O'] * 265
)

# Load energy intensity data
EI_BEU = pd.read_csv(
    'C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/teste/EI_Route_Step_year_novo3.csv', 
    sep=';'
)
EI_BEU = EI_BEU.fillna(0)

# Clean energy intensity data - remove unused fuels
fuels_to_remove = ['Lenha', 'Produtos da cana', 'Gasolina', 'Querosene', 
                   'Alcatrao', 'Alcool etilico', 'Outras fontes secundarias']
for fuel in fuels_to_remove:
    EI_BEU = EI_BEU[EI_BEU.Combustivel != fuel]

EI_BEU = EI_BEU.replace({'Combustivel': 'Gases cidade'}, 'Gas cidade')
EI_BEU = EI_BEU.replace({'Combustivel': 'Outras fontes primarias'}, 'Outras fontes secundarias')

#==============================================================================
# SECTION 3: PROCESS HISTORICAL PRODUCTION DATA
#==============================================================================

# Calculate BF-BOF production split between coal (MC) and charcoal (CC)
steel_production['BF-BOF MC'] = steel_production['BOF'] * pig_iron_production['Share BF-BOF MC']
steel_production['BF-BOF CC'] = steel_production['BOF'] * pig_iron_production['Share BF-BOF CC']

# Recalculate total (excluding EOF)
steel_production['Total'] = steel_production['BOF'] + steel_production['EAF']
steel_production = steel_production.drop('EOF', axis='columns')

# Calculate production shares
steel_production['Share_BOF_MC'] = steel_production['BF-BOF MC'] / steel_production['Total']
steel_production['Share_BOF_CC'] = steel_production['BF-BOF CC'] / steel_production['Total']
steel_production['Share_EAF'] = steel_production['EAF'] / steel_production['Total']

#==============================================================================
# SECTION 4: PREPARE BASE YEAR PLANT DATA
#==============================================================================

base_year = 2023

# Convert data types
plants['Startyear'] = plants['Startyear'].astype(int)
plants['Retrofitdate'] = plants['Retrofitdate'].astype(int)
plants['Capacity'] = plants['Capacity'].astype(float)

# Filter plants active in base year
plants_base = plants[
    (plants['Startyear'] <= base_year) &
    (plants['Retrofitdate'] >= base_year)
].copy()

# Get production and capacity by route for base year
production_by_route = steel_production.loc[base_year].drop('Total')
capacity_by_route = plants_base.groupby('Route')['Capacity'].sum()

#==============================================================================
# SECTION 5: ADJUST EAF CAPACITY (create virtual plant if needed)
#==============================================================================

target_eaf = production_by_route['EAF']
capacity_eaf = capacity_by_route.get('EAF', 0)
missing_eaf = target_eaf - capacity_eaf

print(f"EAF capacity gap in {base_year}: {missing_eaf:.2f} kt")

if missing_eaf > 0:
    eaf_virtual = {
        'Plantname': 'EAF_virtual_2023',
        'Route': 'EAF',
        'Capacity': missing_eaf,
        'Startyear': base_year,
        'Retrofitdate': 2033,
        'Energy_intensity': np.nan,
        'Emission_intensity': np.nan
    }
    plants_base = pd.concat([plants_base, pd.DataFrame([eaf_virtual])], ignore_index=True)

#==============================================================================
# SECTION 6: CALCULATE UTILIZATION AND SPLIT BOF INTO MC/CC
#==============================================================================

# Calculate utilization rate by route
production_by_route_simple = steel_production.loc[base_year, ['BOF', 'EAF']]
capacity_by_route = plants_base.groupby('Route')['Capacity'].sum()
utilization_by_route = production_by_route_simple / capacity_by_route

plants_base['Utilization'] = plants_base['Route'].map(utilization_by_route)
plants_base['Production_2023'] = plants_base['Capacity'] * plants_base['Utilization']

# Separate BOF plants into BF-BOF MC and BF-BOF CC
bof_plants = plants_base[plants_base['Route'] == 'BOF'].copy()
target_mc = steel_production.loc[base_year, 'BF-BOF MC']
target_cc = steel_production.loc[base_year, 'BF-BOF CC']

# Sort by production and assign types
bof_plants = bof_plants.sort_values('Production_2023', ascending=False)
bof_plants['BOF_type'] = None
cum_mc = 0

for idx, row in bof_plants.iterrows():
    if cum_mc < target_mc:
        bof_plants.loc[idx, 'BOF_type'] = 'BF-BOF MC'
        cum_mc += row['Production_2023']
    else:
        bof_plants.loc[idx, 'BOF_type'] = 'BF-BOF CC'

# Check BOF split
print("\nBOF production split:")
print(bof_plants.groupby('BOF_type')['Production_2023'].sum())

#==============================================================================
# SECTION 7: CREATE MARGINAL CC PLANT IF NEEDED
#==============================================================================

current_cc = bof_plants[bof_plants['BOF_type'] == 'BF-BOF CC']['Production_2023'].sum()
missing_cc = target_cc - current_cc

print(f"\nBF-BOF CC capacity gap: {missing_cc:.2f} kt")

if missing_cc > 0:
    new_cc_plant = {
        'Plantname': 'BF-BOF_CC_virtual_2023',
        'Route': 'BOF',
        'BOF_type': 'BF-BOF CC',
        'Capacity': missing_cc,
        'Utilization': 1.0,
        'Production_2023': missing_cc,
        'Startyear': 2023,
        'Retrofitdate': 2040,
        'Energy_intensity': np.nan,
        'Emission_intensity': np.nan
    }
    bof_plants = pd.concat([bof_plants, pd.DataFrame([new_cc_plant])], ignore_index=True)

#==============================================================================
# SECTION 8: UNIFY ALL EXISTING PLANTS
#==============================================================================

# Prepare BOF plants
bof_final = bof_plants.copy()
bof_final['Final_route'] = bof_final['BOF_type']
bof_final['Production_2023_final'] = bof_final['Production_2023']
bof_final = bof_final[['Plantname', 'Final_route', 'Capacity', 'Production_2023_final', 
                        'Startyear', 'Retrofitdate']]

# Prepare EAF plants
eaf_final = plants_base[plants_base['Route'] == 'EAF'].copy()
eaf_final['Final_route'] = 'EAF'
eaf_final['Production_2023_final'] = eaf_final['Production_2023']
eaf_final = eaf_final[['Plantname', 'Final_route', 'Capacity', 'Production_2023_final', 
                        'Startyear', 'Retrofitdate']]

# Combine all existing plants
plants_unified = pd.concat([bof_final, eaf_final], ignore_index=True)

# Verification
print("\n=== EXISTING PLANTS VERIFICATION ===")
print("Production by route in plants_unified:")
print(plants_unified.groupby('Final_route')['Production_2023_final'].sum())
print("\nHistorical production in 2023:")
print(steel_production.loc[2023, ['BF-BOF MC', 'BF-BOF CC', 'EAF']])

#==============================================================================
# SECTION 9: DEFINE FUNCTION TO ADD VIRTUAL PLANTS
#==============================================================================

def add_virtual_plant(plants_df, name, route, year, cap, retrofit=2050):
    """
    Add a virtual (candidate) plant to the plants dataframe.
    
    Parameters:
    -----------
    plants_df : DataFrame - existing plants dataframe
    name : str - unique plant identifier
    route : str - technology route (e.g., 'EAF', 'DR-H2')
    year : int - start year of operation
    cap : float - maximum capacity (kt)
    retrofit : int - end of life year
    
    Returns:
    --------
    DataFrame with new plant added
    """
    newrow = {
        'Plantname': name,
        'Final_route': route,
        'Capacity': cap,
        'Production_2023_final': 0,
        'Startyear': year,
        'Retrofitdate': retrofit
    }
    return pd.concat([plants_df, pd.DataFrame([newrow])], ignore_index=True)

#==============================================================================
# SECTION 10: CREATE CANDIDATE PLANTS FOR FUTURE EXPANSION
#==============================================================================

# Define all available routes for expansion
routes = ['BF-BOF CC', 'BF-BOF MC', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']

# Define maximum capacity per candidate plant (adjust as needed)
# This represents the maximum size of a single new plant
MAX_CANDIDATE_CAPACITY = 5000  # kt per plant

# Create candidate plants for each technology and future year
print("\n=== CREATING CANDIDATE PLANTS ===")
candidate_count = 0

for year in range(2024, 2051):
    for route in routes:
        candidate_name = f"{route}_candidate_{year}"
        plants_unified = add_virtual_plant(
            plants_unified,
            name=candidate_name,
            route=route,
            year=year,
            cap=MAX_CANDIDATE_CAPACITY,
            retrofit=2070  # Long lifetime so they don't retire within horizon
        )
        candidate_count += 1

print(f"Created {candidate_count} candidate plants")
print(f"Total plants in model: {len(plants_unified)}")

#==============================================================================
# SECTION 11: PREPARE PLANT DATA STRUCTURES FOR PYOMO
#==============================================================================

# Create list of all plant names (existing + candidates)
plant_names = plants_unified["Plantname"].tolist()

# Create dictionary of plant attributes for quick lookup
plant_attr = plants_unified.set_index("Plantname").to_dict('index')

# Define model years
model_years = list(range(2023, 2051))

#==============================================================================
# SECTION 12: CREATE PRODUCTION TARGET TRAJECTORY
#==============================================================================

# Create production target dataframe
steel_total_target = steel_production[['Total']].copy()
steel_total_target.index.name = 'Year'

# Add future years as NaN
for year in range(2024, 2051):
    if year not in steel_total_target.index:
        steel_total_target.loc[year] = [np.nan]
steel_total_target.sort_index(inplace=True)

# Apply growth factors for key years
Production_increase = {
    2025: 1.037,
    2030: 1.146,
    2035: 1.306,
    2040: 1.486,
    2045: 1.699,
    2050: 1.961,
}

base_production = steel_total_target.loc[2023, 'Total']
for year, factor in Production_increase.items():
    steel_total_target.loc[year, 'Total'] = base_production * factor

# Interpolate intermediate years
steel_total_target['Total'] = steel_total_target['Total'].interpolate()
steel_total_target.index = steel_total_target.index.astype(int)

print("\n=== PRODUCTION TARGETS ===")
print(steel_total_target.loc[2023:2050:5, 'Total'])

#==============================================================================
# SECTION 13: LOAD PENETRATION CONSTRAINTS
#==============================================================================

# Load penetration limits (maximum share of production by technology per year)
penetration_innovative = pd.read_csv('Penetration_innovative.csv')
penetration_innovative = penetration_innovative.set_index('Technology')
penetration_innovative.columns = penetration_innovative.columns.astype(int)

# Create penetration dictionary
penetration_dict = {
    (tech, int(year)): float(val)
    for (tech, year), val in penetration_innovative.stack().to_dict().items()
}

print("\n=== PENETRATION LIMITS LOADED ===")
print(f"Technologies with limits: {list(penetration_innovative.index)}")

# Diagnostic: Show penetration limits for innovative technologies in early years
print("\n=== PENETRATION LIMITS FOR EARLY YEARS (2023-2030) ===")
early_years = [y for y in penetration_innovative.columns if 2023 <= y <= 2030]
print(penetration_innovative[early_years])

# Check if innovative technologies have zero penetration in early years
innovative_techs = ['DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']
print("\n=== INNOVATIVE TECH PENETRATION CHECK ===")
for tech in innovative_techs:
    if tech in penetration_innovative.index:
        limits_2023_2030 = penetration_innovative.loc[tech, early_years]
        print(f"{tech}: {limits_2023_2030.to_dict()}")

#==============================================================================
# SECTION 14: CREATE TECHNOLOGY PARAMETERS DICTIONARY
#==============================================================================

# Create measures dictionary from tecnologias dataframe
measures_dict = tecnologias.T.to_dict()

# Verify all routes have parameters
routes_in_plants = plants_unified["Final_route"].unique().tolist()
print("\n=== TECHNOLOGY PARAMETERS CHECK ===")
for route in routes_in_plants:
    if route in measures_dict:
        capex = measures_dict[route].get('CAPEX', 'N/A')
        opex = measures_dict[route].get('OPEX', 'N/A')
        emiss = measures_dict[route].get('Emission_intensity', 'N/A')
        print(f"  {route}: CAPEX={capex}, OPEX={opex}, Emission={emiss}")
    else:
        print(f"  {route}: MISSING - will cause errors!")

# Show all technologies in measures_dict
print("\n=== ALL TECHNOLOGIES IN Tecnologias.csv ===")
for tech in measures_dict:
    capex = measures_dict[tech].get('CAPEX', 'N/A')
    opex = measures_dict[tech].get('OPEX', 'N/A')
    emiss = measures_dict[tech].get('Emission_intensity', 'N/A')
    print(f"  {tech}: CAPEX={capex}, OPEX={opex}, Emission={emiss}")

#==============================================================================
# SECTION 15: DEFINE EMISSION LIMITS
#==============================================================================

# Emission limits (kt CO2 eq)
# Scenario: Constant emissions - maintain 2020 level through 2050
emission_2020 = 57016  # Base year emissions (kt CO2eq)
emission_2050 = 57016  # Target: maintain constant emissions (no reduction required)

year_start, year_end = 2020, 2050

# Create linear interpolation of emission limits
emission_limit_dict = {
    y: emission_2020 + (emission_2050 - emission_2020) * (y - year_start) / (year_end - year_start)
    for y in model_years
}

print("\n=== EMISSION LIMITS ===")
print(f"2020: {emission_2020:.0f} kt CO2eq")
print(f"2050: {emission_2050:.0f} kt CO2eq")

#==============================================================================
# SECTION 16: BUILD PYOMO OPTIMIZATION MODEL
#==============================================================================

print("\n=== BUILDING OPTIMIZATION MODEL ===")

m = ConcreteModel()

# --- SETS ---
m.Year = Set(initialize=model_years, ordered=True)
m.Plant = Set(initialize=plant_names)
m.Tech = Set(initialize=list(penetration_innovative.index))
m.Route = Set(initialize=routes_in_plants)

# --- PARAMETERS ---
production_dict = {y: v for y, v in steel_total_target['Total'].to_dict().items() if y in model_years}
m.ProductionTarget = Param(m.Year, initialize=production_dict)
m.EmissionLimit = Param(m.Year, initialize=emission_limit_dict)

# --- DECISION VARIABLES ---
# Production of each plant in each year (kt)
m.production = Var(m.Plant, m.Year, domain=NonNegativeReals)

# --- HELPER MAPPINGS ---
plant_to_route = {p: plant_attr[p]["Final_route"] for p in plant_names}

#==============================================================================
# SECTION 17: DEFINE MODEL CONSTRAINTS
#==============================================================================

# --- HELPER FUNCTIONS ---
def is_plant_active(plant, year):
    """Check if plant is operational in given year"""
    info = plant_attr[plant]
    return (year >= int(info['Startyear'])) and (year <= int(info['Retrofitdate']))

def is_existing_plant(plant):
    """Check if plant is an existing plant (not a candidate)"""
    return 'candidate' not in plant.lower()

def is_candidate_plant(plant):
    """Check if plant is a candidate plant"""
    return 'candidate' in plant.lower()

# --- Identify existing plants set ---
existing_plants = [p for p in plant_names if is_existing_plant(p)]
candidate_plants = [p for p in plant_names if is_candidate_plant(p)]

print(f"\n=== PLANT CLASSIFICATION ===")
print(f"Existing plants: {len(existing_plants)}")
print(f"Candidate plants: {len(candidate_plants)}")

# --- CONSTRAINT A: Plant capacity limits (upper bound) ---
def cap_rule_upper(m, plant, year):
    """Production cannot exceed capacity when active, must be zero when inactive"""
    info = plant_attr[plant]
    if not is_plant_active(plant, year):
        return m.production[plant, year] == 0
    return m.production[plant, year] <= info['Capacity']

m.CapLimitUpper = Constraint(m.Plant, m.Year, rule=cap_rule_upper)

# --- CONSTRAINT B: Minimum production for EXISTING plants ---
# Existing plants must produce at a minimum utilization rate while active
# This represents sunk costs - once built, plants should operate

# ============================================================
# CONFIGURABLE PARAMETER: Adjust this value if model is infeasible
# Lower values = more flexibility, Higher values = more realistic
# ============================================================
MINIMUM_UTILIZATION_EXISTING = 0.7  # 70% minimum utilization for existing plants
# ============================================================

print(f"\nMinimum utilization for existing plants: {MINIMUM_UTILIZATION_EXISTING:.0%}")

def min_production_existing_rule(m, plant, year):
    """Existing plants must produce at minimum utilization while active"""
    # Only apply to existing plants (not candidates)
    if is_candidate_plant(plant):
        return Constraint.Skip
    
    info = plant_attr[plant]
    
    # Only apply if plant is active
    if not is_plant_active(plant, year):
        return Constraint.Skip
    
    min_production = info['Capacity'] * MINIMUM_UTILIZATION_EXISTING
    return m.production[plant, year] >= min_production

m.MinProductionExisting = Constraint(m.Plant, m.Year, rule=min_production_existing_rule)

# --- CONSTRAINT C: National production target ---
def total_production_rule(m, year):
    """Total production must meet or exceed target"""
    prod_this_year = sum(m.production[plant, year] for plant in m.Plant)
    return prod_this_year >= m.ProductionTarget[year]

m.NationalProduction = Constraint(m.Year, rule=total_production_rule)

# --- CONSTRAINT D: Penetration limits by technology (IMPROVED) ---
# This constraint now properly handles the penetration limits

def penetration_rule_production(m, tech, year):
    """Production by technology limited by penetration rate"""
    # Find all plants of this technology
    plants_of_tech = [plant for plant in m.Plant if plant_to_route[plant] == tech]
    
    # Get penetration limit for this tech and year
    penetration_lim = penetration_dict.get((tech, year), None)
    
    # If no plants of this technology exist, skip
    if not plants_of_tech:
        return Constraint.Skip
    
    # If penetration limit is None or not defined, skip (no limit)
    if penetration_lim is None:
        return Constraint.Skip
    
    # If penetration limit is 0, no production allowed from this tech
    if penetration_lim == 0:
        return sum(m.production[plant, year] for plant in plants_of_tech) == 0
    
    # Otherwise, apply the penetration limit
    return (
        sum(m.production[plant, year] for plant in plants_of_tech)
        <= penetration_lim * m.ProductionTarget[year]
    )

m.PenetrationLimitProduction = Constraint(m.Tech, m.Year, rule=penetration_rule_production)

# --- CONSTRAINT E: Emission limits ---
def emission_rule(m, year):
    """Total emissions must not exceed limit"""
    total_emissions = sum(
        measures_dict[plant_to_route[plant]]['Emission_intensity'] * m.production[plant, year]
        for plant in m.Plant
        if plant_to_route[plant] in measures_dict
    )
    return total_emissions <= m.EmissionLimit[year]

m.TotalEmissions = Constraint(m.Year, rule=emission_rule)

#==============================================================================
# SECTION 18: DEFINE OBJECTIVE FUNCTION
#==============================================================================

def obj_rule(m):
    """Minimize total cost = CAPEX + OPEX"""
    total = 0
    for plant in m.Plant:
        tech = plant_to_route[plant]
        
        # Get cost parameters (default to 0 if missing)
        if tech in measures_dict:
            capex = float(measures_dict[tech].get('CAPEX', 0) or 0)
            opex = float(measures_dict[tech].get('OPEX', 0) or 0)
        else:
            capex = 0
            opex = 0
        
        for year in m.Year:
            # CAPEX charged in the start year
            if int(plant_attr[plant]['Startyear']) == int(year):
                total += capex * plant_attr[plant]['Capacity']
            
            # OPEX charged every year based on production
            total += opex * m.production[plant, year]
    
    return total

m.Objective = Objective(rule=obj_rule, sense=minimize)

print("Model built successfully!")
print(f"  - Plants: {len(plant_names)}")
print(f"  - Years: {len(model_years)}")
print(f"  - Variables: ~{len(plant_names) * len(model_years)}")

#==============================================================================
# SECTION 18.5: PRE-SOLVE FEASIBILITY CHECK
#==============================================================================

print("\n=== PRE-SOLVE FEASIBILITY CHECK ===")

# Check 1: Can existing plants meet production targets with minimum utilization?
print("\n--- Check 1: Existing Plant Capacity vs Production Target ---")
for year in model_years[:10]:  # Check first 10 years
    # Calculate total capacity from existing plants that are active
    existing_capacity = sum(
        plant_attr[p]['Capacity'] 
        for p in existing_plants 
        if is_plant_active(p, year)
    )
    
    # Calculate minimum production from existing plants (due to min utilization constraint)
    min_existing_production = sum(
        plant_attr[p]['Capacity'] * MINIMUM_UTILIZATION_EXISTING
        for p in existing_plants 
        if is_plant_active(p, year)
    )
    
    # Calculate maximum candidate capacity available
    candidate_capacity = sum(
        plant_attr[p]['Capacity']
        for p in candidate_plants
        if is_plant_active(p, year)
    )
    
    target = production_dict[year]
    total_max_capacity = existing_capacity + candidate_capacity
    
    status = "OK" if total_max_capacity >= target else "INSUFFICIENT CAPACITY"
    if min_existing_production > target:
        status = "WARNING: Min existing > target!"
    
    print(f"  {year}: Target={target:.0f}, Existing Cap={existing_capacity:.0f}, "
          f"Min Existing Prod={min_existing_production:.0f}, Candidate Cap={candidate_capacity:.0f} [{status}]")

# Check 2: Emission constraint feasibility
print("\n--- Check 2: Emission Constraint Check ---")
for year in [2023, 2030, 2040, 2050]:
    if year in model_years:
        # If all existing plants run at minimum, what are emissions?
        min_emissions = sum(
            plant_attr[p]['Capacity'] * MINIMUM_UTILIZATION_EXISTING * 
            measures_dict.get(plant_to_route[p], {}).get('Emission_intensity', 0)
            for p in existing_plants
            if is_plant_active(p, year) and plant_to_route[p] in measures_dict
        )
        
        limit = emission_limit_dict[year]
        status = "OK" if min_emissions <= limit else "INFEASIBLE - emissions exceed limit!"
        print(f"  {year}: Min Emissions={min_emissions:.0f}, Limit={limit:.0f} [{status}]")

# Check 3: Penetration constraints
print("\n--- Check 3: Penetration Limits for Existing Routes ---")
existing_routes = set(plant_to_route[p] for p in existing_plants)
for route in existing_routes:
    for year in [2023, 2025, 2030]:
        if year in model_years:
            pen_limit = penetration_dict.get((route, year), None)
            if pen_limit is not None:
                max_allowed = pen_limit * production_dict[year]
                existing_cap_route = sum(
                    plant_attr[p]['Capacity']
                    for p in existing_plants
                    if plant_to_route[p] == route and is_plant_active(p, year)
                )
                min_prod_route = existing_cap_route * MINIMUM_UTILIZATION_EXISTING
                
                if min_prod_route > max_allowed:
                    print(f"  {route} in {year}: CONFLICT! Min prod={min_prod_route:.0f} > Pen limit={max_allowed:.0f}")

print("\n" + "="*60)

#==============================================================================
# SECTION 19: SOLVE THE MODEL
#==============================================================================

print("\n=== SOLVING MODEL ===")

solver_name = "ipopt"
solver = SolverFactory(
    solver_name + "nl", 
    executable=modules.find(solver_name), 
    solve_io="nl"
)

result_solver = solver.solve(m, tee=True)

# Check solver status
print("\n=== SOLVER STATUS ===")
print(f"Termination condition: {result_solver.solver.termination_condition}")

if str(result_solver.solver.termination_condition) == "infeasible":
    print("\n*** MODEL IS INFEASIBLE ***")
    print("Possible causes:")
    print("  1. Minimum utilization constraint too high for existing plants")
    print("  2. Emission limits too restrictive")
    print("  3. Penetration limits conflict with existing plant capacity")
    print("  4. Production target cannot be met with available capacity")
    print("\nTry:")
    print("  - Reduce MINIMUM_UTILIZATION_EXISTING (currently {:.0%})".format(MINIMUM_UTILIZATION_EXISTING))
    print("  - Increase emission limits")
    print("  - Check penetration limits in Penetration_innovative.csv")

#==============================================================================
# SECTION 20: EXTRACT AND PROCESS RESULTS
#==============================================================================

print("\n=== PROCESSING RESULTS ===")

# --- RAW DATA: Production by plant and year (long format) ---
production_df_long = pd.DataFrame([
    {
        "Plant": plant,
        "Final_route": plant_to_route[plant],
        "Year": year,
        "Production": m.production[plant, year].value,
        "Startyear": plant_attr[plant]['Startyear'],
        "Retrofitdate": plant_attr[plant]['Retrofitdate'],
        "Capacity": plant_attr[plant]['Capacity']
    }
    for plant in m.Plant for year in m.Year
])

# --- PIVOTED FORMAT: Production by Plant (plants as rows, years as columns) ---
# First, create a base dataframe with plant attributes
plant_info = production_df_long[['Plant', 'Final_route', 'Startyear', 'Retrofitdate', 'Capacity']].drop_duplicates()

# Pivot production data: years become columns
production_pivot = production_df_long.pivot(
    index='Plant', 
    columns='Year', 
    values='Production'
).reset_index()

# Merge plant info with pivoted production
production_by_plant_wide = plant_info.merge(production_pivot, on='Plant')

# Reorder columns: Plant info first, then years in order
year_columns = sorted([col for col in production_by_plant_wide.columns if isinstance(col, int)])
info_columns = ['Plant', 'Final_route', 'Startyear', 'Retrofitdate', 'Capacity']
production_by_plant_wide = production_by_plant_wide[info_columns + year_columns]

# Sort by Final_route and Plant name
production_by_plant_wide = production_by_plant_wide.sort_values(['Final_route', 'Plant']).reset_index(drop=True)

print(f"Production by Plant table: {len(production_by_plant_wide)} plants x {len(year_columns)} years")

# --- PIVOTED FORMAT: Production by Route (routes as rows, years as columns) ---
prod_by_route_long = production_df_long.groupby(["Final_route", "Year"])["Production"].sum().reset_index()

production_by_route_wide = prod_by_route_long.pivot(
    index='Final_route',
    columns='Year',
    values='Production'
).reset_index()

# Rename index column for clarity
production_by_route_wide = production_by_route_wide.rename(columns={'Final_route': 'Route'})

# Add total row
total_row = production_by_route_wide.select_dtypes(include=[np.number]).sum()
total_row_df = pd.DataFrame([['TOTAL'] + total_row.tolist()], columns=production_by_route_wide.columns)
production_by_route_wide = pd.concat([production_by_route_wide, total_row_df], ignore_index=True)

print(f"Production by Route table: {len(production_by_route_wide)} routes x {len(year_columns)} years")

# --- Total production by year (single row, for reference) ---
production_total_df = (
    production_df_long
    .groupby("Year", as_index=False)["Production"]
    .sum()
    .rename(columns={"Production": "Total_Production"})
)

# Also create wide format for total
production_total_wide = production_total_df.set_index('Year').T
production_total_wide.index = ['Total_Production']

# --- Incremental production (new plants only) ---
incremental_production_df = production_df_long[
    production_df_long["Startyear"] == production_df_long["Year"]
].copy()
incremental_production_df["Technology"] = incremental_production_df["Final_route"]
incremental_production_df.rename(columns={"Production": "Production_Expansion"}, inplace=True)

# Pivoted incremental production by route
incremental_by_route = incremental_production_df.groupby(['Technology', 'Year'])['Production_Expansion'].sum().reset_index()
incremental_by_route_wide = incremental_by_route.pivot(
    index='Technology',
    columns='Year',
    values='Production_Expansion'
).fillna(0).reset_index()

# --- Calculate emissions by year ---
emissions = {}
for year in m.Year:
    total_emiss = sum(
        measures_dict[plant_to_route[plant]]['Emission_intensity'] * m.production[plant, year].value
        for plant in m.Plant
        if plant_to_route[plant] in measures_dict and m.production[plant, year].value is not None
    )
    emissions[year] = total_emiss

emissions_df = pd.DataFrame(list(emissions.items()), columns=["Year", "Emissions"])

# Also create wide format for emissions
emissions_wide = emissions_df.set_index('Year').T
emissions_wide.index = ['Emissions_ktCO2eq']

# Add emission limits row
emission_limits_row = pd.DataFrame(
    [[emission_limit_dict.get(y, np.nan) for y in sorted(emissions.keys())]],
    columns=sorted(emissions.keys()),
    index=['Emission_Limit_ktCO2eq']
)
emissions_comparison_wide = pd.concat([emissions_wide, emission_limits_row])

print("Results processing complete!")

#==============================================================================
# SECTION 21: VISUALIZE RESULTS
#==============================================================================

print("\n=== GENERATING PLOTS ===")

# Plot 1: Production by route over time
plt.figure(figsize=(12, 6))
for tech in prod_by_route_long["Final_route"].unique():
    subset = prod_by_route_long[prod_by_route_long["Final_route"] == tech]
    if subset["Production"].sum() > 0:  # Only plot routes with production
        plt.plot(subset["Year"], subset["Production"], label=tech, linewidth=2)

plt.title("Annual Production by Technology Route")
plt.xlabel("Year")
plt.ylabel("Production (kt)")
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('production_by_route.png', dpi=150)
plt.show()

# Plot 2: Capacity expansion by technology
plt.figure(figsize=(12, 6))
inc_prod_summary = incremental_production_df.groupby(["Technology", "Year"])["Production_Expansion"].sum().reset_index()
for tech in inc_prod_summary["Technology"].unique():
    subset = inc_prod_summary[inc_prod_summary["Technology"] == tech]
    if subset["Production_Expansion"].sum() > 0:
        plt.plot(subset["Year"], subset["Production_Expansion"], label=tech, linewidth=2)

plt.title("Capacity Expansion by Technology")
plt.xlabel("Year")
plt.ylabel("New Capacity Added (kt)")
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('capacity_expansion.png', dpi=150)
plt.show()

# Plot 3: Emissions trajectory
plt.figure(figsize=(10, 5))
plt.plot(emissions_df["Year"], emissions_df["Emissions"], 'b-', linewidth=2, label='Actual Emissions')
plt.plot(list(emission_limit_dict.keys()), list(emission_limit_dict.values()), 
         'r--', linewidth=2, label='Emission Limit')
plt.title("Emissions Trajectory vs Limit")
plt.xlabel("Year")
plt.ylabel("Emissions (kt CO2eq)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('emissions_trajectory.png', dpi=150)
plt.show()

#==============================================================================
# SECTION 22: EXPORT RESULTS TO EXCEL
#==============================================================================

print("\n=== EXPORTING RESULTS ===")

output_path = r"C:\Users\Bruna\OneDrive\DOUTORADO\0.TESE\modelagem\modelo_bru\teste\resultados\resultados_modelo_V14.xlsx"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with pd.ExcelWriter(output_path) as writer:
    # --- MAIN RESULTS (WIDE FORMAT - years as columns) ---
    
    # Production by Plant (wide): each plant is a row, years are columns
    production_by_plant_wide.to_excel(
        writer, 
        sheet_name="Production_by_Plant", 
        index=False,
        freeze_panes=(1, 5)  # Freeze header row and first 5 columns (plant info)
    )
    
    # Production by Route (wide): each route is a row, years are columns
    production_by_route_wide.to_excel(
        writer, 
        sheet_name="Production_by_Route", 
        index=False,
        freeze_panes=(1, 1)  # Freeze header row and route column
    )
    
    # Incremental Production by Route (wide)
    incremental_by_route_wide.to_excel(
        writer,
        sheet_name="Incremental_by_Route",
        index=False,
        freeze_panes=(1, 1)
    )
    
    # Emissions comparison (wide): emissions vs limits
    emissions_comparison_wide.to_excel(
        writer,
        sheet_name="Emissions",
        index=True
    )
    
    # --- SUPPORTING DATA (LONG FORMAT for detailed analysis) ---
    
    # Production by Plant (long format) - for detailed filtering/analysis
    production_df_long.to_excel(
        writer, 
        sheet_name="Production_Detail_Long", 
        index=False
    )
    
    # Total production by year
    production_total_df.to_excel(
        writer, 
        sheet_name="Total_Production", 
        index=False
    )
    
    # --- SUMMARY ---
    summary_df = pd.DataFrame({
        'Metric': [
            'Base Year', 
            'Horizon End', 
            'Total Plants (existing + candidates)', 
            'Existing Plants',
            'Candidate Plants', 
            'Base Production (kt)', 
            'Target 2050 (kt)', 
            'Emission Limit 2020 (kt CO2eq)',
            'Emission Limit 2050 (kt CO2eq)',
            'Minimum Utilization for Existing Plants'
        ],
        'Value': [
            2023, 
            2050, 
            len(plants_unified), 
            len(existing_plants),
            candidate_count,
            base_production, 
            steel_total_target.loc[2050, 'Total'], 
            emission_2020,
            emission_2050,
            MINIMUM_UTILIZATION_EXISTING
        ]
    })
    summary_df.to_excel(writer, sheet_name="Summary", index=False)
    
    # --- INPUTS REFERENCE ---
    # Save penetration limits used
    penetration_innovative.to_excel(writer, sheet_name="Input_Penetration_Limits")
    
    # Save technology parameters used
    tecnologias_export = pd.DataFrame(measures_dict).T
    tecnologias_export.index.name = 'Technology'
    tecnologias_export.to_excel(writer, sheet_name="Input_Technology_Params")

print(f"Results saved to: {output_path}")
print("\n=== SHEETS CREATED ===")
print("  1. Production_by_Plant    - Plants as rows, years as columns")
print("  2. Production_by_Route    - Routes as rows, years as columns")
print("  3. Incremental_by_Route   - New capacity by route per year")
print("  4. Emissions              - Emissions vs limits by year")
print("  5. Production_Detail_Long - Long format for detailed analysis")
print("  6. Total_Production       - Total production by year")
print("  7. Summary                - Model parameters summary")
print("  8. Input_Penetration_Limits - Penetration constraints used")
print("  9. Input_Technology_Params  - CAPEX/OPEX/Emissions used")

print("\n=== MODEL RUN COMPLETE ===")
