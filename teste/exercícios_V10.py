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
tecnologias = pd.read_csv('Tecnologias.csv', sep=";")
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
        print(f"  {route}: OK")
    else:
        print(f"  {route}: MISSING - will cause errors!")

#==============================================================================
# SECTION 15: DEFINE EMISSION LIMITS
#==============================================================================

# Emission limits (kt CO2 eq) - ADJUST THESE VALUES!
# Current values are placeholders - set realistic targets
emission_2020 = 57016  # Base year emissions
emission_2050 = 40000  # Target emissions in 2050 (example: ~30% reduction)

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

# --- CONSTRAINT A: Plant activity and capacity limits ---
def is_plant_active(plant, year):
    """Check if plant is operational in given year"""
    info = plant_attr[plant]
    return (year >= int(info['Startyear'])) and (year <= int(info['Retrofitdate']))

def cap_rule(m, plant, year):
    """Production limited by capacity when active, zero otherwise"""
    info = plant_attr[plant]
    if not is_plant_active(plant, year):
        return m.production[plant, year] == 0
    return m.production[plant, year] <= info['Capacity']

m.CapLimit = Constraint(m.Plant, m.Year, rule=cap_rule)

# --- CONSTRAINT B: National production target ---
def total_production_rule(m, year):
    """Total production must meet or exceed target"""
    prod_this_year = sum(m.production[plant, year] for plant in m.Plant)
    return prod_this_year >= m.ProductionTarget[year]

m.NationalProduction = Constraint(m.Year, rule=total_production_rule)

# --- CONSTRAINT C: Penetration limits by technology ---
def penetration_rule_production(m, tech, year):
    """Production by technology limited by penetration rate"""
    plants_of_tech = [plant for plant in m.Plant if plant_to_route[plant] == tech]
    penetration_lim = penetration_dict.get((tech, year), 0.0)
    
    if (not plants_of_tech) or penetration_lim == 0:
        return Constraint.Skip
    
    return (
        sum(m.production[plant, year] for plant in plants_of_tech)
        <= penetration_lim * m.ProductionTarget[year]
    )

m.PenetrationLimitProduction = Constraint(m.Tech, m.Year, rule=penetration_rule_production)

# --- CONSTRAINT D: Emission limits ---
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

#==============================================================================
# SECTION 20: EXTRACT AND PROCESS RESULTS
#==============================================================================

print("\n=== PROCESSING RESULTS ===")

# Production by plant and year
production_df = pd.DataFrame([
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

# Production by route
prod_by_route = production_df.groupby(["Final_route", "Year"])["Production"].sum().reset_index()

# Total production by year
production_total_df = (
    production_df
    .groupby("Year", as_index=False)["Production"]
    .sum()
    .rename(columns={"Production": "Total_Production"})
)

# Incremental production (new plants only)
incremental_production_df = production_df[
    production_df["Startyear"] == production_df["Year"]
].copy()
incremental_production_df["Technology"] = incremental_production_df["Final_route"]
incremental_production_df.rename(columns={"Production": "Production_Expansion"}, inplace=True)

# Calculate emissions by year
emissions = {}
for year in m.Year:
    total_emiss = sum(
        measures_dict[plant_to_route[plant]]['Emission_intensity'] * m.production[plant, year].value
        for plant in m.Plant
        if plant_to_route[plant] in measures_dict and m.production[plant, year].value is not None
    )
    emissions[year] = total_emiss

emissions_df = pd.DataFrame(list(emissions.items()), columns=["Year", "Emissions"])

#==============================================================================
# SECTION 21: VISUALIZE RESULTS
#==============================================================================

print("\n=== GENERATING PLOTS ===")

# Plot 1: Production by route over time
plt.figure(figsize=(12, 6))
for tech in prod_by_route["Final_route"].unique():
    subset = prod_by_route[prod_by_route["Final_route"] == tech]
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

output_path = r"C:\Users\Bruna\OneDrive\DOUTORADO\0.TESE\modelagem\modelo_bru\teste\resultados\resultados_modelo_V13.xlsx"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with pd.ExcelWriter(output_path) as writer:
    production_df.to_excel(writer, sheet_name="Production_by_Plant", index=False)
    prod_by_route.to_excel(writer, sheet_name="Production_by_Route", index=False)
    production_total_df.to_excel(writer, sheet_name="Total_Production", index=False)
    incremental_production_df.to_excel(writer, sheet_name="Incremental_Production", index=False)
    emissions_df.to_excel(writer, sheet_name="Emissions", index=False)
    
    # Add summary sheet
    summary_df = pd.DataFrame({
        'Metric': ['Base Year', 'Horizon End', 'Total Plants', 'Candidate Plants', 
                   'Base Production (kt)', 'Target 2050 (kt)', 'Emission Limit 2050 (kt CO2eq)'],
        'Value': [2023, 2050, len(plants_unified), candidate_count,
                  base_production, steel_total_target.loc[2050, 'Total'], emission_2050]
    })
    summary_df.to_excel(writer, sheet_name="Summary", index=False)

print(f"Results saved to: {output_path}")
print("\n=== MODEL RUN COMPLETE ===")