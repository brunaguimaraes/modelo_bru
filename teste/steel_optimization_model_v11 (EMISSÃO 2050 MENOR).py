# -*- coding: utf-8 -*-

#esta rodada, eu quero permitir alguma entrada de mineral coal dali pra frente, mas com limite! O resultado leva a quedas mto grandes de emissão. 
#SR continua sendo prevalente!


"""
Steel Production Optimization Model - Version 5
Author: Bruna (reorganized with assistance)
Date: February 2026

This model optimizes steel production capacity expansion to meet production targets
while minimizing costs (CAPEX + OPEX + FUEL COSTS) and respecting emission limits.

Updates in V5:
- Emission constraint calculated from Production × EI × EF (by fuel)
- Follows methodology from Hebeda (2024)
- Emissions separated into PROCESS and ENERGY in results
- Process fuels: Coque, Carvão vegetal, Carvão metalúrgico (reducers)
- Energy fuels: Gas natural, Eletricidade, Óleo, etc. (thermal)
- Detailed outputs for CO2, CH4, N2O, CO2e
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
# SECTION 2: DEFINE UNIT CONVERSION CONSTANTS
#==============================================================================

# Unit conversions
TEP_TO_GJ = 41.868       # 1 tep (tonne of oil equivalent) = 41.868 GJ
KTOE_TO_TJ = 41.868      # 1 ktoe = 41.868 TJ
TJ_TO_GJ = 1000          # 1 TJ = 1000 GJ

# Economic parameters
DOLAR_TO_BRL = 5.31      # Exchange rate (1 USD = 5.31 BRL, mean value 2021)
INTEREST_RATE = 0.08     # Annual interest rate for levelized costs
PLANT_LIFETIME = 20      # Years for CAPEX levelization

# Calculate levelized cost factor (capital recovery factor)
LEVELIZED_FACTOR = (INTEREST_RATE * (1 + INTEREST_RATE)**PLANT_LIFETIME) / ((1 + INTEREST_RATE)**PLANT_LIFETIME - 1)

# GWP values (AR5 - IPCC)
GWP_CH4 = 28             # Global Warming Potential for CH4
GWP_N2O = 265            # Global Warming Potential for N2O

# === FUEL CLASSIFICATION (Hebeda 2024 methodology) ===
# Process fuels: participate in chemical reduction of iron ore
# Reaction: Fe2O3 + 3C → 2Fe + 3CO2
# Energy fuels: provide only thermal energy

COMBUSTIVEIS_PROCESSO = [
    'Coque de carvao mineral',
    'Carvao vegetal',
    'Carvao metalurgico'
]

COMBUSTIVEIS_ENERGIA = [
    'Gas natural',
    'Eletricidade',
    'Oleo combustivel',
    'Oleo diesel',
    'GLP',
    'Gases cidade',
    'Outras fontes primarias',
    'Outras fontes secundarias'
]

print("="*70)
print("STEEL PRODUCTION OPTIMIZATION MODEL - VERSION 7")
print("="*70)

print("\n=== PARAMETERS ===")
print(f"Exchange rate: 1 USD = {DOLAR_TO_BRL} BRL")
print(f"Interest rate: {INTEREST_RATE:.1%}")
print(f"Plant lifetime: {PLANT_LIFETIME} years")
print(f"Levelized cost factor: {LEVELIZED_FACTOR:.4f}")
print(f"GWP CH4: {GWP_CH4}, GWP N2O: {GWP_N2O}")

#==============================================================================
# SECTION 3: LOAD RAW DATA
#==============================================================================

print("\n=== LOADING DATA ===")

# Load existing plants data
plants = pd.read_excel('Plants_teste_chris.xlsx')
print("  - Plants data loaded")

# Load technology parameters (CAPEX, OPEX, emission intensity, etc.)
tecnologias = pd.read_csv('Tecnologias_v2.csv', sep=";")
tecnologias.set_index('Route', inplace=True)
print("  - Technology parameters loaded")

# Load historical steel production by route (kt)
steel_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/steel_production.csv')
steel_production = steel_production.set_index('Year')
steel_production['Total'] = steel_production.sum(axis=1)
print("  - Steel production history loaded")

# Load pig iron production to calculate BF-BOF CC vs MC shares
pig_iron_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Pig_iron_production_2.csv')
pig_iron_production = pig_iron_production.set_index('Ano')
pig_iron_production['Share BF-BOF CC'] = (
    pig_iron_production['Integrada CV'] / 
    (pig_iron_production['Integrada CV'] + pig_iron_production['Integrada CM'])
)
pig_iron_production['Share BF-BOF MC'] = 1 - pig_iron_production['Share BF-BOF CC']
print("  - Pig iron production loaded")

# Load scrap supply data
scrap_supply = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Scrap_supply.csv')
scrap_supply = scrap_supply.set_index('Recovery_rate')
print("  - Scrap supply data loaded")

# Load emission factors
emission_factor = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/emission_factor.csv')
emission_factor = emission_factor.set_index('Combustivel')
emission_factor['CO2e'] = (
    emission_factor['CO2'] + 
    emission_factor['CH4'] * GWP_CH4 + 
    emission_factor['N2O'] * GWP_N2O
)
print("  - Emission factors loaded")

#==============================================================================
# SECTION 3B: LOAD ENERGY INTENSITY BY ROUTE AND FUEL (for emission calculation)
#==============================================================================

print("\n=== LOADING ENERGY INTENSITY BY ROUTE AND FUEL ===")

# Load EI_Route_Fuel_SIMPLIFIED.csv
ei_route_fuel = pd.read_csv('EI_Route_Fuel_SIMPLIFIED.csv', sep=';')
print(f"  - Energy intensity data loaded: {len(ei_route_fuel)} records")
print(f"  - Routes: {ei_route_fuel['Route'].unique().tolist()}")

# Create dictionary for lookup: {(route, fuel): EI_GJ_t}
ei_by_route_fuel = {}
for _, row in ei_route_fuel.iterrows():
    key = (row['Route'], row['Combustivel'])
    ei_by_route_fuel[key] = row['EI_GJ_t']

# Get fuels per route
fuels_by_route = {}
for route in ei_route_fuel['Route'].unique():
    fuels_by_route[route] = ei_route_fuel[ei_route_fuel['Route'] == route]['Combustivel'].tolist()

# Map fuel names between EI file and emission_factor file
FUEL_NAME_MAPPING = {
    'Gas natural': 'Gas natural',
    'Eletricidade': 'Eletricidade',
    'Carvao vegetal': 'Carvao vegetal',
    'Carvao metalurgico': 'Carvao metalurgico',
    'Coque de carvao mineral': 'Coque de carvao mineral',
    'Gases cidade': 'Gas cidade',
    'Oleo combustivel': 'Oleo combustivel',
    'Oleo diesel': 'Oleo diesel',
    'GLP': 'GLP',
    'Outras fontes primarias': 'Outras primarias nao renovaveis',
    'Outras fontes secundarias': 'Outras fontes secundarias',
}

#==============================================================================
# SECTION 3C: CALCULATE EMISSION FACTOR BY ROUTE (Hebeda methodology)
#==============================================================================

print("\n=== CALCULATING EMISSION FACTOR BY ROUTE (Hebeda methodology) ===")

# EF_route (kg CO2e/t) = Σ (EI_fuel × EF_fuel) for all fuels in route
emission_factor_by_route = {}
emission_factor_by_route_detailed = {}

for route in ei_route_fuel['Route'].unique():
    route_data = ei_route_fuel[ei_route_fuel['Route'] == route]
    
    total_co2 = 0
    total_ch4 = 0
    total_n2o = 0
    
    for _, row in route_data.iterrows():
        fuel = row['Combustivel']
        ei = row['EI_GJ_t']
        
        mapped_fuel = FUEL_NAME_MAPPING.get(fuel, fuel)
        
        if mapped_fuel in emission_factor.index:
            ef_co2 = emission_factor.loc[mapped_fuel, 'CO2']
            ef_ch4 = emission_factor.loc[mapped_fuel, 'CH4']
            ef_n2o = emission_factor.loc[mapped_fuel, 'N2O']
        else:
            ef_co2, ef_ch4, ef_n2o = 0, 0, 0
            if ei > 0:
                print(f"  WARNING: No emission factor for '{fuel}' (mapped: '{mapped_fuel}')")
        
        total_co2 += ei * ef_co2
        total_ch4 += ei * ef_ch4
        total_n2o += ei * ef_n2o
    
    total_co2e = total_co2 + total_ch4 * GWP_CH4 + total_n2o * GWP_N2O
    
    
    # ── CCS CORRECTION ──────────────────────────────────────────────────
    # CCS captures only CO2 (not CH4 or N2O).
    # The corrected CO2e = CO2*(1-capture_rate) + CH4*GWP + N2O*GWP
    # Here we recalculate total_co2e for the CCS route specifically.
    CAPTURE_RATE_CCS = 0.80  # 80% CO2 capture rate
    if route == 'BF-BOF-CCS':
        total_co2_after_capture = total_co2 * (1 - CAPTURE_RATE_CCS)
        total_co2e = total_co2_after_capture + total_ch4 * GWP_CH4 + total_n2o * GWP_N2O
        print(f"  [CCS] CO2 before capture: {total_co2:.1f} kg/t  →  after 80% capture: {total_co2_after_capture:.1f} kg/t")
    # ────────────────────────────────────────────────────────────────────
    
    emission_factor_by_route[route] = total_co2e
    emission_factor_by_route_detailed[route] = {
        'CO2_kg_t': total_co2 if route != 'BF-BOF-CCS' else total_co2 * (1 - CAPTURE_RATE_CCS),
        'CH4_kg_t': total_ch4,
        'N2O_kg_t': total_n2o,
        'CO2e_kg_t': total_co2e
    }


print("\n  Emission Factor by Route (calculated from EI × EF):")
for route, ef in sorted(emission_factor_by_route.items(), key=lambda x: x[1], reverse=True):
    print(f"    {route}: {ef:.1f} kg CO2e/t = {ef/1000:.3f} t CO2e/t")


#==============================================================================
# SECTION 4: LOAD AND PROCESS ENERGY INTENSITY DATA (EI_BEU)
#==============================================================================

print("\n=== LOADING ENERGY INTENSITY DATA ===")

# Load energy intensity data (GJ/t by route and fuel)
EI_BEU = pd.read_csv(
    'C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/teste/EI_Route_Step_year_novo3.csv', 
    sep=';'
)
EI_BEU = EI_BEU.fillna(0)

# Rename 'Rota' column to 'Route' for consistency
if 'Rota' in EI_BEU.columns:
    EI_BEU = EI_BEU.rename(columns={'Rota': 'Route'})

# Clean energy intensity data - remove unused fuels
fuels_to_remove = ['Lenha', 'Produtos da cana', 'Gasolina', 'Querosene', 
                   'Alcatrao', 'Alcool etilico']
for fuel in fuels_to_remove:
    EI_BEU = EI_BEU[EI_BEU.Combustivel != fuel]

# Standardize fuel names to match fuel_prices
EI_BEU = EI_BEU.replace({'Combustivel': 'Gases cidade'}, 'Gas cidade')

print(f"  - Energy intensity data loaded: {len(EI_BEU)} records")
print(f"  - Routes in EI_BEU: {EI_BEU['Route'].unique().tolist()}")

# Create route mapping from R1/R2/R3/R4 to model route names
ROUTE_MAPPING = {
    'R1': 'BF-BOF MC',
    'R2': 'BF-BOF CC',
    'R3': 'EAF',
    'R4': 'Independent'  # Will be excluded from model
}

# Apply route mapping
EI_BEU['Route_Name'] = EI_BEU['Route'].map(ROUTE_MAPPING)

# Calculate total energy intensity by route (sum across all fuels)
year_columns = [col for col in EI_BEU.columns if col.isdigit() or (isinstance(col, str) and col.isnumeric())]
year_columns_int = [int(y) for y in year_columns]

print(f"  - Years available in EI_BEU: {min(year_columns_int)} to {max(year_columns_int)}")

# Create energy intensity summary by route
EI_by_route = {}
for route_code, route_name in ROUTE_MAPPING.items():
    if route_name != 'Independent':  # Exclude R4
        route_data = EI_BEU[EI_BEU['Route'] == route_code]
        # Sum energy intensity across all fuels for the base year (2023)
        if '2023' in route_data.columns:
            total_ei = route_data['2023'].sum()
        else:
            total_ei = route_data[year_columns[-1]].sum()  # Use latest year
        EI_by_route[route_name] = total_ei
        print(f"  - {route_name} ({route_code}): {total_ei:.2f} GJ/t")

# === EXTEND EI_by_route WITH INNOVATIVE ROUTES (from EI_Route_Fuel_SIMPLIFIED.csv) ===
# EI_by_route so far only has R1/R2/R3 (from EI_BEU).
# All other routes (DR-NG, DR-H2, SR, BF-BOF-CCS, Guseiros) come from ei_by_route_fuel.
# This avoids any hardcoded values in Section 28.

routes_already_in = set(EI_by_route.keys())

for route in ei_route_fuel['Route'].unique():
    if route not in routes_already_in:
        total_ei = sum(
            v for (r, f), v in ei_by_route_fuel.items() if r == route
        )
        EI_by_route[route] = total_ei
        print(f"  - {route} (from SIMPLIFIED): {total_ei:.2f} GJ/t")

print(f"\n  EI_by_route now contains {len(EI_by_route)} routes: {sorted(EI_by_route.keys())}")

#==============================================================================
# SECTION 5: LOAD AND PROCESS FUEL PRICES
#==============================================================================

print("\n=== LOADING FUEL PRICES ===")

# Load fuel prices
fuel_prices = pd.read_excel('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/teste/fuel_prices_V9.xlsx')
fuel_prices = fuel_prices.rename(columns={'Fuel': 'Combustivel'})
fuel_prices = fuel_prices.set_index('Combustivel')

# Convert prices to BRL/GJ
# Original prices are in BRL/tep, convert using: BRL/GJ = BRL/tep / 41.868
fuel_prices['BRL_per_GJ'] = fuel_prices['BRL2020/tep'] / TEP_TO_GJ

print("  - Fuel prices loaded and converted to BRL/GJ")
print("\n  Sample fuel prices (BRL/GJ):")
sample_fuels = ['Eletricidade', 'Gas natural', 'Carvao metalurgico', 'Carvao vegetal', 'Coque de carvao mineral']
for fuel in sample_fuels:
    if fuel in fuel_prices.index:
        price = fuel_prices.loc[fuel, 'BRL_per_GJ']
        print(f"    {fuel}: {price:.2f} BRL/GJ")

#==============================================================================
# SECTION 6: CREATE ENERGY SHARE BY ROUTE AND FUEL
#==============================================================================

print("\n=== CALCULATING ENERGY SHARE BY ROUTE ===")

# For each route, calculate the share of energy from each fuel
# Energy_share[route][fuel] = EI_fuel / EI_total

base_year_ei = '2023'  # Use 2023 as reference

energy_share = {}
energy_intensity_by_route_fuel = {}

for route_code, route_name in ROUTE_MAPPING.items():
    if route_name == 'Independent':
        continue  # Skip R4
    
    route_data = EI_BEU[EI_BEU['Route'] == route_code][['Combustivel', base_year_ei]].copy()
    route_data.columns = ['Combustivel', 'EI']
    route_data = route_data[route_data['EI'] > 0]  # Only fuels with positive EI
    
    total_ei = route_data['EI'].sum()
    
    if total_ei > 0:
        route_data['Share'] = route_data['EI'] / total_ei
        energy_share[route_name] = dict(zip(route_data['Combustivel'], route_data['Share']))
        energy_intensity_by_route_fuel[route_name] = dict(zip(route_data['Combustivel'], route_data['EI']))
        
        print(f"\n  {route_name} (Total EI: {total_ei:.2f} GJ/t):")
        for _, row in route_data.iterrows():
            print(f"    {row['Combustivel']}: {row['EI']:.3f} GJ/t ({row['Share']:.1%})")


#%% section 7
#==============================================================================
# SECTION 7: CALCULATE FUEL COST PER TONNE BY ROUTE
#==============================================================================
#
# Calculates fuel cost for ALL routes (existing AND innovative) using a
# single data source: ei_by_route_fuel from EI_Route_Fuel_SIMPLIFIED.csv
#
# Fuel cost per tonne (BRL/t) = Σ (EI_fuel × price_fuel) for each fuel in route
#
# No hardcoded energy intensities. All values come from CSV data.
# DR-H2 considers hydrogen production via electrolysis, so its energy
# input is captured as electricity in the EI file.
#==============================================================================

print("\n=== CALCULATING FUEL COST PER TONNE BY ROUTE ===")

# --- Mapping from EI fuel names to fuel_prices index names ---
# Most fuel names match directly. This mapping handles the exceptions.
FUEL_TO_PRICE_MAPPING = {
    'Gas natural': 'Gas natural',
    'Eletricidade': 'Eletricidade',
    'Carvao vegetal': 'Carvao vegetal',
    'Carvao metalurgico': 'Carvao metalurgico',
    'Coque de carvao mineral': 'Coque de carvao mineral',
    'Gases cidade': 'Gas cidade',
    'Oleo combustivel': 'Oleo combustivel',
    'Oleo diesel': 'Oleo diesel',
    'GLP': 'GLP',
    'Outras fontes primarias': 'Outras fontes secundarias',
    'Outras fontes secundarias': 'Outras fontes secundarias',
}

# --- Calculate fuel cost for ALL routes from ei_by_route_fuel ---
fuel_cost_per_tonne = {}

# Get all unique routes from the EI data
all_routes_in_ei = sorted(set(route for (route, fuel) in ei_by_route_fuel.keys()))

for route in all_routes_in_ei:
    total_fuel_cost = 0
    print(f"\n  {route}:")
    
    # Get all fuels for this route
    route_fuels = {fuel: ei for (r, fuel), ei in ei_by_route_fuel.items() if r == route}
    
    for fuel, ei in route_fuels.items():
        if ei == 0:
            continue  # Skip fuels with zero intensity
        
        # Map fuel name to fuel_prices index
        price_fuel_name = FUEL_TO_PRICE_MAPPING.get(fuel, fuel)
        
        if price_fuel_name in fuel_prices.index:
            price = fuel_prices.loc[price_fuel_name, 'BRL_per_GJ']
            cost = ei * price
            total_fuel_cost += cost
            print(f"    {fuel}: {ei:.3f} GJ/t x {price:.2f} BRL/GJ = {cost:.2f} BRL/t")
        else:
            print(f"    WARNING: {fuel} (mapped: '{price_fuel_name}') NOT FOUND in fuel_prices - using 0")
    
    fuel_cost_per_tonne[route] = total_fuel_cost
    print(f"    TOTAL: {total_fuel_cost:.2f} BRL/t = {total_fuel_cost/DOLAR_TO_BRL:.2f} USD/t")

# --- Summary ---
print("\n=== FUEL COST SUMMARY (BRL/t and USD/t) ===")
for route in sorted(fuel_cost_per_tonne.keys()):
    cost_brl = fuel_cost_per_tonne[route]
    cost_usd = cost_brl / DOLAR_TO_BRL
    print(f"  {route}: {cost_brl:>10.2f} BRL/t = {cost_usd:>8.2f} USD/t")

#%%
#==============================================================================
# SECTION 8: PROCESS HISTORICAL PRODUCTION DATA
#==============================================================================

print("\n=== PROCESSING HISTORICAL PRODUCTION DATA ===")

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

print("  - Historical production processed")


#%% calibration BEN

#==============================================================================
# SECTION 8B: CALIBRATE ENERGY INTENSITIES WITH NATIONAL ENERGY BALANCE (BEN)
#==============================================================================
#
# PURPOSE: Adjust the theoretical energy intensities (EI_BEU) so that the
# model's energy consumption matches the official National Energy Balance (BEN).
#
# METHODOLOGY (Hebeda 2024):
# For each fuel and year:
#   1. Model estimate = Σ (EI_fuel_route × Production_route) across all routes
#   2. BEN real = official consumption from CE_Siderurgia (in ktep → TJ)
#   3. Adjustment factor = BEN_real / Model_estimate
#   4. EI_calibrated = EI_original × factor
#
# After calibration: Σ (EI_calibrated × Production) = BEN exactly.
#
# POSITION: After Section 8 (steel_production has BF-BOF MC/CC/EAF shares).
# AFFECTS: EI_BEU, ei_by_route_fuel (conventional), EI_by_route (conventional),
#          emission_factor_by_route (conventional), fuel_cost_per_tonne (conventional),
#          energy_share, energy_intensity_by_route_fuel.
# DOES NOT AFFECT: Innovative routes (DR-NG, DR-H2, SR, BF-BOF-CCS) — no BEN data.
#
# IMPORTANT: This section OVERWRITES values calculated in Sections 3B, 3C, 4, 6, 7
# for conventional routes only. All existing code remains untouched.
#==============================================================================
 
print("\n" + "="*70)
print("SECTION 8B: BEN CALIBRATION OF ENERGY INTENSITIES")
print("="*70)
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Load BEN data (CE_Siderurgia)
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 1: Load BEN data ---")
 
Energy_consumption_BEN = pd.read_excel(
    'C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/teste/CE_Siderurgia 04-07-25.xlsx'
)
Energy_consumption_BEN = Energy_consumption_BEN.fillna(0)
 
# Standardize fuel names to match EI_BEU nomenclature
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES': 'Carvao mineral'}, 'Carvao metalurgico')
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES': 'Gas de coqueria'}, 'Gas cidade')
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES': 'Alcatrao'}, 'Outras fontes secundarias')
 
Energy_consumption_BEN = Energy_consumption_BEN.set_index('FONTES')
Energy_consumption_BEN.index = Energy_consumption_BEN.index.str.capitalize()
Energy_consumption_BEN.columns = Energy_consumption_BEN.columns.astype(int)
 
# Sum Biodiesel with Diesel
if 'Biodiesel' in Energy_consumption_BEN.index and 'Oleo diesel' in Energy_consumption_BEN.index:
    Energy_consumption_BEN.loc['Oleo diesel'] = (
        Energy_consumption_BEN.loc['Biodiesel'] + Energy_consumption_BEN.loc['Oleo diesel']
    )
    Energy_consumption_BEN = Energy_consumption_BEN.drop(index=['Biodiesel'])
 
# Fix naming
if 'Glp' in Energy_consumption_BEN.index:
    Energy_consumption_BEN = Energy_consumption_BEN.rename(index={'Glp': 'GLP'})
 
Energy_consumption_BEN = Energy_consumption_BEN.sort_index()
 
# Convert from ktep to TJ (1 ktep = 41.868 TJ)
Energy_consumption_BEN_TJ = Energy_consumption_BEN * KTOE_TO_TJ
 
print(f"  BEN data loaded: {Energy_consumption_BEN.shape[0]} fuels x {Energy_consumption_BEN.shape[1]} years")
print(f"  Years: {Energy_consumption_BEN.columns.min()} to {Energy_consumption_BEN.columns.max()}")
print(f"  Fuels in BEN: {sorted(Energy_consumption_BEN.index.tolist())}")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Calculate model-estimated consumption (BEFORE calibration)
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 2: Calculate model-estimated consumption (pre-calibration) ---")
 
# Production mapping: EI_BEU route code → production series
ROUTE_TO_PRODUCTION = {
    'R1': 'BF-BOF MC',
    'R2': 'BF-BOF CC',
    'R3': 'EAF',
}
# Note: R4 (Independent/Guseiros) excluded — not in the optimization model
 
# Identify years available in both EI_BEU and steel_production
ei_year_cols = [col for col in EI_BEU.columns if isinstance(col, str) and col.isnumeric()]
available_years = [int(y) for y in ei_year_cols if int(y) in steel_production.index]
 
print(f"  Calibration years: {min(available_years)} to {max(available_years)}")
 
# Calculate model estimate: for each fuel and year, sum(EI × production) across routes
def calc_model_estimate():
    """Calculate total energy consumption by fuel using current EI_BEU values"""
    model_est = pd.DataFrame(0.0, index=EI_BEU['Combustivel'].unique(), columns=available_years)
    
    for route_code, prod_col in ROUTE_TO_PRODUCTION.items():
        route_data = EI_BEU[EI_BEU['Route'] == route_code]
        
        for year in available_years:
            year_str = str(year)
            if year_str not in route_data.columns:
                continue
            if year not in steel_production.index:
                continue
                
            production = steel_production.loc[year, prod_col]
            
            for _, row in route_data.iterrows():
                fuel = row['Combustivel']
                ei = float(row[year_str])
                consumption_tj = ei * production  # GJ/t × kt = TJ
                model_est.loc[fuel, year] += consumption_tj
    
    return model_est
 
model_estimate_pre = calc_model_estimate()
 
# Show pre-calibration comparison for base year
cal_year = 2023 if 2023 in available_years else max(available_years)
print(f"\n  Pre-calibration comparison (year {cal_year}):")
print(f"  {'Fuel':<30s} {'BEN (TJ)':>12s} {'Model (TJ)':>12s} {'Ratio':>8s}")
print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*8}")
 
for fuel in sorted(model_estimate_pre.index):
    model_val = model_estimate_pre.loc[fuel, cal_year]
    if fuel in Energy_consumption_BEN_TJ.index and cal_year in Energy_consumption_BEN_TJ.columns:
        ben_val = Energy_consumption_BEN_TJ.loc[fuel, cal_year]
    else:
        ben_val = 0
    
    if model_val > 0:
        ratio = ben_val / model_val
        print(f"  {fuel:<30s} {ben_val:>12,.0f} {model_val:>12,.0f} {ratio:>8.3f}")
    elif ben_val > 0:
        print(f"  {fuel:<30s} {ben_val:>12,.0f} {model_val:>12,.0f}  {'N/A':>6s}")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Calculate and apply calibration factors
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 3: Apply calibration factors to EI_BEU ---")
 
calibration_factors = {}
fuels_calibrated = []
fuels_skipped = []
 
for fuel in EI_BEU['Combustivel'].unique():
    fuel_factors = {}
    
    for year in available_years:
        year_str = str(year)
        
        # Model estimate for this fuel and year
        model_val = model_estimate_pre.loc[fuel, year] if fuel in model_estimate_pre.index else 0
        
        # BEN value for this fuel and year
        if fuel in Energy_consumption_BEN_TJ.index and year in Energy_consumption_BEN_TJ.columns:
            ben_val = float(Energy_consumption_BEN_TJ.loc[fuel, year])
        else:
            ben_val = 0
        
        # Calculate factor
        if model_val > 0 and ben_val > 0:
            factor = ben_val / model_val
        elif model_val == 0 and ben_val == 0:
            factor = 1.0  # Both zero — no adjustment needed
        else:
            factor = 1.0  # Cannot calibrate — keep original
        
        fuel_factors[year] = factor
    
    calibration_factors[fuel] = fuel_factors
 
# Apply factors to EI_BEU
for idx in EI_BEU.index:
    fuel = EI_BEU.loc[idx, 'Combustivel']
    route = EI_BEU.loc[idx, 'Route']
    
    # Only calibrate conventional routes (R1, R2, R3)
    if route not in ROUTE_TO_PRODUCTION:
        continue
    
    for year in available_years:
        year_str = str(year)
        if year_str in EI_BEU.columns:
            factor = calibration_factors.get(fuel, {}).get(year, 1.0)
            EI_BEU.loc[idx, year_str] = float(EI_BEU.loc[idx, year_str]) * factor
 
# Verify: recalculate model estimate with calibrated values
model_estimate_post = calc_model_estimate()
 
print(f"\n  Post-calibration comparison (year {cal_year}):")
print(f"  {'Fuel':<30s} {'BEN (TJ)':>12s} {'Model (TJ)':>12s} {'Ratio':>8s}")
print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*8}")
 
for fuel in sorted(model_estimate_post.index):
    model_val = model_estimate_post.loc[fuel, cal_year]
    if fuel in Energy_consumption_BEN_TJ.index and cal_year in Energy_consumption_BEN_TJ.columns:
        ben_val = Energy_consumption_BEN_TJ.loc[fuel, cal_year]
    else:
        ben_val = 0
    
    if model_val > 0:
        ratio = ben_val / model_val
        print(f"  {fuel:<30s} {ben_val:>12,.0f} {model_val:>12,.0f} {ratio:>8.3f}")
 
print("\n  Calibration applied to EI_BEU for routes R1, R2, R3")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Update EI_by_route for conventional routes
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 4: Update EI_by_route (total energy intensity by route) ---")
 
base_year_str = str(cal_year)
 
for route_code, route_name in ROUTE_MAPPING.items():
    if route_name == 'Independent':
        continue
    
    route_data = EI_BEU[EI_BEU['Route'] == route_code]
    if base_year_str in route_data.columns:
        old_val = EI_by_route.get(route_name, 0)
        new_val = route_data[base_year_str].sum()
        EI_by_route[route_name] = new_val
        print(f"  {route_name}: {old_val:.2f} → {new_val:.2f} GJ/t")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Update ei_by_route_fuel for conventional routes
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 5: Update ei_by_route_fuel (by fuel) for conventional routes ---")
 
for route_code, route_name in ROUTE_MAPPING.items():
    if route_name == 'Independent':
        continue
    
    route_data = EI_BEU[EI_BEU['Route'] == route_code]
    
    for _, row in route_data.iterrows():
        fuel = row['Combustivel']
        old_val = ei_by_route_fuel.get((route_name, fuel), 0)
        new_val = float(row[base_year_str]) if base_year_str in row.index else 0
        
        if old_val != new_val and (old_val > 0 or new_val > 0):
            ei_by_route_fuel[(route_name, fuel)] = new_val
            # Also update fuels_by_route if fuel is new for this route
            if route_name in fuels_by_route:
                if fuel not in fuels_by_route[route_name] and new_val > 0:
                    fuels_by_route[route_name].append(fuel)
 
print(f"  Updated ei_by_route_fuel for: {[v for k, v in ROUTE_MAPPING.items() if v != 'Independent']}")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Recalculate emission_factor_by_route for conventional routes
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 6: Recalculate emission factors for conventional routes ---")
 
for route_code, route_name in ROUTE_MAPPING.items():
    if route_name == 'Independent':
        continue
    
    # Get calibrated fuels for this route
    route_fuels = {fuel: ei for (r, fuel), ei in ei_by_route_fuel.items() if r == route_name and ei > 0}
    
    total_co2 = 0
    total_ch4 = 0
    total_n2o = 0
    
    for fuel, ei in route_fuels.items():
        mapped_fuel = FUEL_NAME_MAPPING.get(fuel, fuel)
        
        if mapped_fuel in emission_factor.index:
            ef_co2 = emission_factor.loc[mapped_fuel, 'CO2']
            ef_ch4 = emission_factor.loc[mapped_fuel, 'CH4']
            ef_n2o = emission_factor.loc[mapped_fuel, 'N2O']
        else:
            ef_co2, ef_ch4, ef_n2o = 0, 0, 0
        
        total_co2 += ei * ef_co2
        total_ch4 += ei * ef_ch4
        total_n2o += ei * ef_n2o
    
    total_co2e = total_co2 + total_ch4 * GWP_CH4 + total_n2o * GWP_N2O
    
    old_ef = emission_factor_by_route.get(route_name, 0)
    emission_factor_by_route[route_name] = total_co2e
    emission_factor_by_route_detailed[route_name] = {
        'CO2_kg_t': total_co2,
        'CH4_kg_t': total_ch4,
        'N2O_kg_t': total_n2o,
        'CO2e_kg_t': total_co2e
    }
    
    print(f"  {route_name}: EF = {old_ef:.1f} → {total_co2e:.1f} kg CO2e/t")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Recalculate energy_share for conventional routes
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 7: Recalculate energy share by route ---")
 
for route_code, route_name in ROUTE_MAPPING.items():
    if route_name == 'Independent':
        continue
    
    # Get calibrated EI data for this route
    route_data = EI_BEU[EI_BEU['Route'] == route_code][['Combustivel', base_year_str]].copy()
    route_data.columns = ['Combustivel', 'EI']
    route_data = route_data[route_data['EI'] > 0]
    
    total_ei = route_data['EI'].sum()
    
    if total_ei > 0:
        route_data['Share'] = route_data['EI'] / total_ei
        energy_share[route_name] = dict(zip(route_data['Combustivel'], route_data['Share']))
        energy_intensity_by_route_fuel[route_name] = dict(zip(route_data['Combustivel'], route_data['EI']))
 
print(f"  Updated energy_share for conventional routes")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: Recalculate fuel_cost_per_tonne for conventional routes
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 8: Recalculate fuel costs for conventional routes ---")
 
for route_code, route_name in ROUTE_MAPPING.items():
    if route_name == 'Independent':
        continue
    
    route_fuels = {fuel: ei for (r, fuel), ei in ei_by_route_fuel.items() if r == route_name and ei > 0}
    
    total_fuel_cost = 0
    for fuel, ei in route_fuels.items():
        price_fuel_name = FUEL_TO_PRICE_MAPPING.get(fuel, fuel)
        if price_fuel_name in fuel_prices.index:
            price = fuel_prices.loc[price_fuel_name, 'BRL_per_GJ']
            total_fuel_cost += ei * price
    
    old_cost = fuel_cost_per_tonne.get(route_name, 0)
    fuel_cost_per_tonne[route_name] = total_fuel_cost
    print(f"  {route_name}: {old_cost:.2f} → {total_fuel_cost:.2f} BRL/t ({total_fuel_cost/DOLAR_TO_BRL:.2f} USD/t)")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 9: Verify charcoal in all routes after calibration
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 9: Charcoal (Carvao vegetal) presence after calibration ---")
 
for route_name in sorted(set(r for (r, f) in ei_by_route_fuel.keys())):
    cv_ei = ei_by_route_fuel.get((route_name, 'Carvao vegetal'), 0)
    if cv_ei > 0:
        print(f"  {route_name}: Carvao vegetal = {cv_ei:.4f} GJ/t")
 
print("\n  NOTE: If conventional routes now show small charcoal consumption,")
print("  this is correct — the BEN calibration distributes the national")
print("  charcoal consumption across all routes proportionally.")
 
print("\n" + "="*70)
print("BEN CALIBRATION COMPLETE")
print("="*70)
print("  All conventional route data (EI, EF, fuel costs) updated.")
print("  Innovative routes (DR-NG, DR-H2, SR, BF-BOF-CCS) unchanged.")
print("  The charcoal constraint (Constraint F) will now correctly")
print("  account for charcoal consumption across ALL routes.")



#==============================================================================
# SECTION 9: PREPARE BASE YEAR PLANT DATA
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
# SECTION 10: ADJUST EAF CAPACITY (create virtual plant if needed)
#==============================================================================

target_eaf = production_by_route['EAF']
capacity_eaf = capacity_by_route.get('EAF', 0)
missing_eaf = target_eaf - capacity_eaf

print(f"\nEAF capacity gap in {base_year}: {missing_eaf:.2f} kt")

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
# SECTION 11: CALCULATE UTILIZATION AND SPLIT BOF INTO MC/CC
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
# SECTION 12: CREATE MARGINAL CC PLANT IF NEEDED
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
# SECTION 13: UNIFY ALL EXISTING PLANTS
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
# SECTION 14: DEFINE FUNCTION TO ADD VIRTUAL PLANTS
#==============================================================================

def add_virtual_plant(plants_df, name, route, year, cap, retrofit=2050):
    """
    Add a virtual (candidate) plant to the plants dataframe.
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
# SECTION 15: CREATE CANDIDATE PLANTS FOR FUTURE EXPANSION
#==============================================================================

# Define all available routes for expansion
routes = ['BF-BOF CC', 'BF-BOF MC', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS'] #notice that 'BF-BOF MC' is no longer an option

# Define maximum capacity per candidate plant
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
            retrofit=2070
        )
        candidate_count += 1

print(f"Created {candidate_count} candidate plants")
print(f"Total plants in model: {len(plants_unified)}")

#==============================================================================
# SECTION 16: PREPARE PLANT DATA STRUCTURES FOR PYOMO
#==============================================================================

# Create list of all plant names (existing + candidates)
plant_names = plants_unified["Plantname"].tolist()

# Create dictionary of plant attributes for quick lookup
plant_attr = plants_unified.set_index("Plantname").to_dict('index')

# Define model years
model_years = list(range(2023, 2051))

#==============================================================================
# SECTION 17: CREATE PRODUCTION TARGET TRAJECTORY
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
# SECTION 18: LOAD PENETRATION CONSTRAINTS
#==============================================================================

# Load penetration limits
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
# SECTION 19: CREATE TECHNOLOGY PARAMETERS DICTIONARY
#==============================================================================

# Create measures dictionary from tecnologias dataframe
measures_dict = tecnologias.T.to_dict()

# Add fuel costs to measures_dict
for route in measures_dict:
    if route in fuel_cost_per_tonne:
        measures_dict[route]['Fuel_cost_BRL_t'] = fuel_cost_per_tonne[route]
        measures_dict[route]['Fuel_cost_USD_t'] = fuel_cost_per_tonne[route] / DOLAR_TO_BRL
    else:
        measures_dict[route]['Fuel_cost_BRL_t'] = 0
        measures_dict[route]['Fuel_cost_USD_t'] = 0

# Add calculated emission factor (kg CO2e/t) to measures_dict
# This replaces the old Emission_intensity from Tecnologias.csv
for route in measures_dict:
    if route in emission_factor_by_route:
        measures_dict[route]['Emission_factor_kg_t'] = emission_factor_by_route[route]
    else:
        measures_dict[route]['Emission_factor_kg_t'] = 0
        print(f"  WARNING: No emission factor calculated for route '{route}'")

# Verify all routes have parameters
routes_in_plants = plants_unified["Final_route"].unique().tolist()
print("\n=== TECHNOLOGY PARAMETERS CHECK (V5 - with calculated EF) ===")
for route in routes_in_plants:
    if route in measures_dict:
        capex = measures_dict[route].get('CAPEX', 'N/A')
        opex = measures_dict[route].get('OPEX', 'N/A')
        ef_calc = measures_dict[route].get('Emission_factor_kg_t', 0)
        fuel = measures_dict[route].get('Fuel_cost_USD_t', 'N/A')
        print(f"  {route}: CAPEX={capex}, OPEX={opex}, EF={ef_calc:.1f} kg/t, Fuel={fuel:.2f} USD/t")
    else:
        print(f"  {route}: MISSING - will cause errors!")
#%%DEFINE EMISSION LIMITS - action!
#%%
#==============================================================================
# SECTION 20: DEFINE EMISSION LIMITS
#==============================================================================

# Emission limits (kt CO2 eq)
# Scenario: Constant emissions - maintain 2020 level through 2050
emission_2020 = 57016  # Base year emissions (kt CO2eq)
emission_2050 = 50016  # Target: maintain constant emissions (no reduction required)

year_start, year_end = 2020, 2050

# Create linear interpolation of emission limits
# emission_limit_dict = {
#     y: emission_2020 + (emission_2050 - emission_2020) * (y - year_start) / (year_end - year_start)
#     for y in model_years
# }

# Linear path from base_year (2023) to 2050, with 10% flexibility in intermediate years
emission_at_base_year = emission_2020 + (emission_2050 - emission_2020) * (base_year - year_start) / (year_end - year_start)

def linear_reference(year):
    if year <= base_year:
        return emission_at_base_year
    if year >= year_end:
        return emission_2050
    frac = (year - base_year) / (year_end - base_year)
    return emission_at_base_year + (emission_2050 - emission_at_base_year) * frac

flexibility = 0.10  # 10% above linear path allowed in intermediate years

emission_limit_dict = {}
for y in model_years:
    if y <= base_year:
        pass  # no emission constraint for historical years
    elif y >= year_end:
        emission_limit_dict[y] = emission_2050  # strict, no flexibility
    else:
        emission_limit_dict[y] = linear_reference(y) * (1.0 + flexibility)

print("\n=== EMISSION LIMITS ===")
print(f"2020: {emission_2020:.0f} kt CO2eq")
print(f"2050: {emission_2050:.0f} kt CO2eq")

#%% BAU
#==============================================================================
# SECTION 20B: BAU SCENARIO (Business-as-Usual)
#==============================================================================
#
# The BAU scenario maintains the 2023 calibrated production structure constant.
# Only the total production level changes, following the same ProductionTarget
# as the mitigation scenario. No innovative routes, no efficiency measures.
#
# Position: After Section 19 (measures_dict complete), before Section 21 (Pyomo).
# This section is pure arithmetic — no optimizer needed.
#
# Data sources (all from previous sections, ensuring consistency):
#   - Calibrated production shares: plants_unified (Section 13)
#   - Production trajectory: steel_total_target (Section 17)
#   - Energy intensity by fuel: ei_by_route_fuel (Section 3B)
#   - Emission factors: emission_factor_by_route_detailed (Section 3C)
#   - Fuel prices & costs: measures_dict (Section 19)
#   - Fuel classification: FUEL_GROUP (Section 28C — define here too for order)
#
# All outputs are prefixed with 'bau_' to distinguish from mitigation results.
#==============================================================================
 
print("\n" + "="*70)
print("BAU SCENARIO — BUSINESS-AS-USUAL (frozen 2023 structure)")
print("="*70)
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Calculate calibrated shares from Section 13 (plants_unified)
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 1: Calibrated production shares (from plants_unified) ---")
 
bau_production_2023 = plants_unified.groupby('Final_route')['Production_2023_final'].sum()
bau_total_2023 = bau_production_2023.sum()
bau_shares = bau_production_2023 / bau_total_2023
 
# Only include historical routes (no innovative routes in BAU)
BAU_ROUTES = [r for r in bau_shares.index if bau_shares[r] > 0]
 
print(f"  Base year total production: {bau_total_2023:,.0f} kt")
print(f"  Routes in BAU: {BAU_ROUTES}")
for route in BAU_ROUTES:
    print(f"    {route}: {bau_production_2023[route]:,.0f} kt ({bau_shares[route]:.1%})")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Project production by route (fixed shares × ProductionTarget)
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 2: Production projection (fixed shares) ---")
 
bau_production_records = []
 
for year in model_years:
    target = steel_total_target.loc[year, 'Total']
    for route in BAU_ROUTES:
        prod = bau_shares[route] * target
        bau_production_records.append({
            'Year': year,
            'Route': route,
            'Production_kt': prod,
        })
 
bau_production_df = pd.DataFrame(bau_production_records)
 
# Wide format: routes as rows, years as columns
bau_production_wide = bau_production_df.pivot_table(
    index='Route', columns='Year', values='Production_kt', aggfunc='sum'
).fillna(0)
bau_production_wide.loc['TOTAL'] = bau_production_wide.sum()
 
print(f"  Production target 2023: {steel_total_target.loc[2023, 'Total']:,.0f} kt")
print(f"  Production target 2050: {steel_total_target.loc[2050, 'Total']:,.0f} kt")
print(f"  Growth factor: {steel_total_target.loc[2050, 'Total'] / steel_total_target.loc[2023, 'Total']:.3f}x")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Calculate fuel consumption by fuel and year
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 3: Fuel consumption by fuel and year ---")
 
bau_fuel_records = []
 
for year in model_years:
    target = steel_total_target.loc[year, 'Total']
    for route in BAU_ROUTES:
        prod = bau_shares[route] * target
        
        if prod == 0:
            continue
        
        # Get fuels for this route
        route_fuels = {fuel: ei for (r, fuel), ei in ei_by_route_fuel.items() if r == route}
        
        for fuel, ei in route_fuels.items():
            if ei == 0:
                continue
            
            consumption_tj = prod * ei  # kt × GJ/t = TJ
            consumption_ktep = consumption_tj / TEP_TO_GJ
            
            bau_fuel_records.append({
                'Year': year,
                'Route': route,
                'Combustivel': fuel,
                'Production_kt': prod,
                'EI_GJ_t': ei,
                'Consumption_TJ': consumption_tj,
                'Consumption_ktep': consumption_ktep,
            })
 
bau_fuel_df = pd.DataFrame(bau_fuel_records)
 
# Aggregate by fuel and year (wide)
bau_fuel_by_year = bau_fuel_df.groupby(['Combustivel', 'Year']).agg({
    'Consumption_TJ': 'sum', 'Consumption_ktep': 'sum'
}).reset_index()
 
bau_fuel_wide_tj = bau_fuel_by_year.pivot_table(
    index='Combustivel', columns='Year', values='Consumption_TJ', aggfunc='sum'
).fillna(0)
bau_fuel_wide_tj.loc['TOTAL'] = bau_fuel_wide_tj.sum()
 
bau_fuel_wide_ktep = bau_fuel_by_year.pivot_table(
    index='Combustivel', columns='Year', values='Consumption_ktep', aggfunc='sum'
).fillna(0)
bau_fuel_wide_ktep.loc['TOTAL'] = bau_fuel_wide_ktep.sum()
 
# Fuel shares
bau_fuel_share = bau_fuel_wide_tj.drop('TOTAL', errors='ignore').copy()
for col in bau_fuel_share.columns:
    total = bau_fuel_wide_tj.loc['TOTAL', col]
    if total > 0:
        bau_fuel_share[col] = bau_fuel_share[col] / total
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Energy group classification (Biomass / Electricity / Fossil)
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 4: Energy group shares ---")
 
BAU_FUEL_GROUP = {
    'Eletricidade': 'Electricity',
    'Carvao vegetal': 'Biomass',
    'Carvao metalurgico': 'Fossil',
    'Coque de carvao mineral': 'Fossil',
    'Gas natural': 'Fossil',
    'Oleo combustivel': 'Fossil',
    'Oleo diesel': 'Fossil',
    'GLP': 'Fossil',
    'Gas cidade': 'Fossil',
    'Gases cidade': 'Fossil',
    'Outras fontes primarias': 'Fossil',
    'Outras fontes secundarias': 'Fossil',
}
 
bau_fuel_grouped = bau_fuel_df.copy()
bau_fuel_grouped['Energy_Group'] = bau_fuel_grouped['Combustivel'].map(BAU_FUEL_GROUP).fillna('Fossil')
 
bau_group_by_year = bau_fuel_grouped.groupby(['Energy_Group', 'Year']).agg({
    'Consumption_TJ': 'sum'
}).reset_index()
 
bau_group_wide = bau_group_by_year.pivot_table(
    index='Energy_Group', columns='Year', values='Consumption_TJ', aggfunc='sum'
).fillna(0)
 
group_order = ['Biomass', 'Electricity', 'Fossil']
bau_group_wide = bau_group_wide.reindex([g for g in group_order if g in bau_group_wide.index])
bau_group_wide.loc['TOTAL'] = bau_group_wide.sum()
 
bau_group_share = bau_group_wide.drop('TOTAL', errors='ignore').copy()
for col in bau_group_share.columns:
    total = bau_group_wide.loc['TOTAL', col]
    if total > 0:
        bau_group_share[col] = bau_group_share[col] / total
 
print(f"  {'Year':>6} | {'Biomass':>8} | {'Electricity':>11} | {'Fossil':>7}")
print(f"  {'-'*6} | {'-'*8} | {'-'*11} | {'-'*7}")
for year in [2023, 2030, 2040, 2050]:
    if year in bau_group_share.columns:
        bio = bau_group_share.loc['Biomass', year] * 100 if 'Biomass' in bau_group_share.index else 0
        elec = bau_group_share.loc['Electricity', year] * 100 if 'Electricity' in bau_group_share.index else 0
        fos = bau_group_share.loc['Fossil', year] * 100 if 'Fossil' in bau_group_share.index else 0
        print(f"  {year:>6} | {bio:>7.1f}% | {elec:>10.1f}% | {fos:>6.1f}%")
 
print("  Note: BAU shares are CONSTANT (frozen 2023 structure)")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Calculate emissions (Process vs Energy, by gas)
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 5: Emissions (Process vs Energy, Hebeda methodology) ---")
 
bau_emissions_records = []
 
for year in model_years:
    target = steel_total_target.loc[year, 'Total']
    
    for route in BAU_ROUTES:
        prod = bau_shares[route] * target
        
        if prod == 0:
            continue
        
        if route not in fuels_by_route:
            continue
        
        proc_co2, proc_ch4, proc_n2o = 0, 0, 0
        ener_co2, ener_ch4, ener_n2o = 0, 0, 0
        
        for fuel in fuels_by_route[route]:
            ei = ei_by_route_fuel.get((route, fuel), 0)
            mapped_fuel = FUEL_NAME_MAPPING.get(fuel, fuel)
            
            if mapped_fuel in emission_factor.index:
                ef_co2 = emission_factor.loc[mapped_fuel, 'CO2']
                ef_ch4 = emission_factor.loc[mapped_fuel, 'CH4']
                ef_n2o = emission_factor.loc[mapped_fuel, 'N2O']
            else:
                ef_co2, ef_ch4, ef_n2o = 0, 0, 0
            
            # prod (kt) × ei (GJ/t) × ef (kg/GJ) / 1000 = kt
            emiss_co2 = prod * ei * ef_co2 / 1000
            emiss_ch4 = prod * ei * ef_ch4 / 1000
            emiss_n2o = prod * ei * ef_n2o / 1000
            
            if fuel in COMBUSTIVEIS_PROCESSO:
                proc_co2 += emiss_co2
                proc_ch4 += emiss_ch4
                proc_n2o += emiss_n2o
            else:
                ener_co2 += emiss_co2
                ener_ch4 += emiss_ch4
                ener_n2o += emiss_n2o
        
        proc_co2e = proc_co2 + proc_ch4 * GWP_CH4 + proc_n2o * GWP_N2O
        ener_co2e = ener_co2 + ener_ch4 * GWP_CH4 + ener_n2o * GWP_N2O
        
        bau_emissions_records.append({
            'Year': year,
            'Route': route,
            'Production_kt': prod,
            'Process_CO2_kt': proc_co2,
            'Process_CH4_kt': proc_ch4,
            'Process_N2O_kt': proc_n2o,
            'Process_CO2e_kt': proc_co2e,
            'Energy_CO2_kt': ener_co2,
            'Energy_CH4_kt': ener_ch4,
            'Energy_N2O_kt': ener_n2o,
            'Energy_CO2e_kt': ener_co2e,
            'Total_CO2e_kt': proc_co2e + ener_co2e,
        })
 
bau_emissions_df = pd.DataFrame(bau_emissions_records)
 
# Aggregate by year
bau_emissions_by_year = bau_emissions_df.groupby('Year').agg({
    'Production_kt': 'sum',
    'Process_CO2e_kt': 'sum',
    'Energy_CO2e_kt': 'sum',
    'Total_CO2e_kt': 'sum',
}).reset_index()
 
# Aggregate by route and year
bau_emissions_by_route = bau_emissions_df.groupby(['Route', 'Year']).agg({
    'Production_kt': 'sum',
    'Total_CO2e_kt': 'sum',
}).reset_index()
 
print("\nBAU Emissions (selected years, kt CO2e):")
for year in [2023, 2030, 2040, 2050]:
    if year in bau_emissions_by_year['Year'].values:
        row = bau_emissions_by_year[bau_emissions_by_year['Year'] == year].iloc[0]
        print(f"  {year}: Process={row['Process_CO2e_kt']:,.0f}, Energy={row['Energy_CO2e_kt']:,.0f}, "
              f"Total={row['Total_CO2e_kt']:,.0f} kt CO2e")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Calculate costs (CAPEX + OPEX + Fuel)
# ─────────────────────────────────────────────────────────────────────────────
 
print("\n--- Step 6: Costs ---")
 
bau_cost_records = []
 
for year in model_years:
    target = steel_total_target.loc[year, 'Total']
    year_capex = 0
    year_opex = 0
    year_fuel = 0
    
    for route in BAU_ROUTES:
        prod = bau_shares[route] * target
        
        if prod == 0 or route not in measures_dict:
            continue
        
        capex = float(measures_dict[route].get('CAPEX', 0) or 0)
        opex = float(measures_dict[route].get('OPEX', 0) or 0)
        fuel_cost = float(measures_dict[route].get('Fuel_cost_USD_t', 0) or 0)
        
        year_capex += capex * prod * LEVELIZED_FACTOR
        year_opex += opex * prod
        year_fuel += fuel_cost * prod
    
    bau_cost_records.append({
        'Year': year,
        'CAPEX_levelized': year_capex,
        'OPEX': year_opex,
        'Fuel_Cost': year_fuel,
        'Total_Cost': year_capex + year_opex + year_fuel,
    })
 
bau_cost_df = pd.DataFrame(bau_cost_records)
 
print("\nBAU Cost Summary (selected years, million USD):")
for year in [2023, 2030, 2040, 2050]:
    if year in bau_cost_df['Year'].values:
        row = bau_cost_df[bau_cost_df['Year'] == year].iloc[0]
        print(f"  {year}: CAPEX={row['CAPEX_levelized']/1e6:.1f}M, OPEX={row['OPEX']/1e6:.1f}M, "
              f"Fuel={row['Fuel_Cost']/1e6:.1f}M, Total={row['Total_Cost']/1e6:.1f}M USD")
 
# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Total energy consumption by year
# ─────────────────────────────────────────────────────────────────────────────
 
bau_total_energy = bau_fuel_df.groupby('Year').agg({
    'Consumption_TJ': 'sum',
    'Consumption_ktep': 'sum',
}).reset_index()
bau_total_energy.columns = ['Year', 'Total_Energy_TJ', 'Total_Energy_ktep']
 
print("\nBAU Energy Consumption (selected years):")
for year in [2023, 2030, 2040, 2050]:
    if year in bau_total_energy['Year'].values:
        row = bau_total_energy[bau_total_energy['Year'] == year].iloc[0]
        print(f"  {year}: {row['Total_Energy_TJ']:,.0f} TJ = {row['Total_Energy_ktep']:,.0f} ktep")
 
print("\n" + "="*70)
print("BAU SCENARIO COMPLETE")
print("="*70)

#%% PYOMO OPTIMIZATION MODEL

#==============================================================================
# SECTION 21: BUILD PYOMO OPTIMIZATION MODEL
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
m.EmissionLimit = Param(m.Year, initialize=emission_limit_dict, default=0)

# --- DECISION VARIABLES ---
m.production = Var(m.Plant, m.Year, domain=NonNegativeReals)

# --- HELPER MAPPINGS ---
plant_to_route = {p: plant_attr[p]["Final_route"] for p in plant_names}

#==============================================================================
# SECTION 22: DEFINE MODEL CONSTRAINTS
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
# ============================================================
# CONFIGURABLE PARAMETER: Minimum utilization for existing plants
# The model considers that existing plants, while active, must operate 
# at a minimum utilization rate. This reflects the economic incentive 
# to keep plants in operation once CAPEX has been invested.
# ============================================================
MINIMUM_UTILIZATION_EXISTING = 0.3  # 30% minimum utilization
# ============================================================

print(f"\nMinimum utilization for existing plants: {MINIMUM_UTILIZATION_EXISTING:.0%}")

def min_production_existing_rule(m, plant, year):
    """Existing plants must produce at minimum utilization while active"""
    if is_candidate_plant(plant):
        return Constraint.Skip
    
    info = plant_attr[plant]
    
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

# --- CONSTRAINT D: Penetration limits by technology ---
def penetration_rule_production(m, tech, year):
    """Production by technology limited by penetration rate"""
    plants_of_tech = [plant for plant in m.Plant if plant_to_route[plant] == tech]
    penetration_lim = penetration_dict.get((tech, year), None)
    
    if not plants_of_tech:
        return Constraint.Skip
    
    if penetration_lim is None:
        return Constraint.Skip
    
    if penetration_lim == 0:
        return sum(m.production[plant, year] for plant in plants_of_tech) == 0
    
    return (
        sum(m.production[plant, year] for plant in plants_of_tech)
        <= penetration_lim * m.ProductionTarget[year]
    )

m.PenetrationLimitProduction = Constraint(m.Tech, m.Year, rule=penetration_rule_production)

# # --- CONSTRAINT E: Emission limits (Hebeda 2024 methodology) ---
# def emission_rule(m, year):
#     """
#     Total emissions must not exceed limit.
    
#     Emission = Σ (Production × Emission_Factor_route) / 1000
    
#     Where Emission_Factor_route = Σ (EI_fuel × EF_fuel) for all fuels
#     Calculated in SECTION 3C using Hebeda (2024) methodology.
    
#     Units: 
#       Production: kt steel
#       Emission_Factor: kg CO2e/t steel
#       Result: kt CO2e (after dividing by 1000)
#     """
#     total_emissions = sum(
#         m.production[plant, year] * measures_dict.get(plant_to_route[plant], {}).get('Emission_factor_kg_t', 0) / 1000
#         for plant in m.Plant
#         if plant_to_route[plant] in measures_dict
#     )
#     return total_emissions <= m.EmissionLimit[year]

# m.TotalEmissions = Constraint(m.Year, rule=emission_rule)


def emission_rule(m, year):
    """
    Total emissions must not exceed limit.
    Historical/base years (not in emission_limit_dict) are skipped.
    Intermediate years (2024-2049): limit = linear path + 10% flexibility.
    Year 2050: strict target, no flexibility.
    """
    if year not in emission_limit_dict:
        return Constraint.Skip
    
    total_emissions = sum(
        m.production[plant, year] * measures_dict.get(plant_to_route[plant], {}).get('Emission_factor_kg_t', 0) / 1000
        for plant in m.Plant
        if plant_to_route[plant] in measures_dict
    )
    return total_emissions <= m.EmissionLimit[year]

m.TotalEmissions = Constraint(m.Year, rule=emission_rule)










#%% AQUI TEM UM VALOR MANUAL! DEFINIR X_ANNUAL_EMISSION_REDUCTION
#%% PEENCHEU??
# #%%
# # --- CONSTRAINT E2: Emission Floor (max annual reduction rate) ---
# # Emissions cannot drop more than 5% per year compared to the previous year.
# # This reflects the inertia of the steel industry: technical barriers,
# # institutional resistance, supply chain constraints, and the time needed
# # for technology deployment prevent abrupt transitions.
# #
# # Without this constraint, the optimizer may switch routes too aggressively
# # (e.g., replacing BF-BOF MC with SR in 2-3 years), which is unrealistic.
# #
# # Combined with Constraint E (emission ceiling), this creates a corridor:
# #   Emissions(year) <= EmissionLimit(year)          ← ceiling (Constraint E)
# #   Emissions(year) >= Emissions(year-1) × (1-0.05) ← floor (Constraint E2)
# #
# # The model must reduce emissions gradually, even if faster reduction
# # would be economically optimal.
 
# MAX_ANNUAL_EMISSION_REDUCTION = 0.02  # 2% maximum drop per year
 
# def emission_floor_rule(m, year):
#     """Emissions cannot drop more than 2% compared to previous year"""
    
#     # Skip the first model year (no previous year to compare)
#     if year == min(m.Year):
#         return Constraint.Skip
    
#     prev_year = year - 1
#     if prev_year not in m.Year:
#         return Constraint.Skip
    
#     # Current year emissions
#     emissions_current = sum(
#         m.production[plant, year] * measures_dict.get(plant_to_route[plant], {}).get('Emission_factor_kg_t', 0) / 1000
#         for plant in m.Plant
#         if plant_to_route[plant] in measures_dict
#     )
    
#     # Previous year emissions
#     emissions_previous = sum(
#         m.production[plant, prev_year] * measures_dict.get(plant_to_route[plant], {}).get('Emission_factor_kg_t', 0) / 1000
#         for plant in m.Plant
#         if plant_to_route[plant] in measures_dict
#     )
    
#     # Floor: current >= previous × (1 - max_reduction)
#     return emissions_current >= emissions_previous * (1 - MAX_ANNUAL_EMISSION_REDUCTION)
 
# m.EmissionFloorE2 = Constraint(m.Year, rule=emission_floor_rule)
 
# print(f"  Constraint E2 added: Emission floor — max {MAX_ANNUAL_EMISSION_REDUCTION:.0%} drop per year")
# print(f"    Emissions corridor: ceiling (Constraint E) + floor (Constraint E2)")



#%%
# # --- CONSTRAINT F: Charcoal (Carvao vegetal) supply limit ---
# # Total charcoal consumption across ALL routes cannot exceed national availability.
# # Source: Otto Hebeda (2024) — 576,812 TJ/year × 80% availability = 461,450 TJ/year
# # Routes consuming charcoal (from EI_Route_Fuel_SIMPLIFIED.csv):
# #   SR:         22.000 GJ/t
# #   BF-BOF CC:   6.533 GJ/t
# #   Guseiros:   17.610 GJ/t
# # Unit check: production (kt) × EI (GJ/t) = TJ  [no conversion needed]

# CHARCOAL_POTENTIAL_TJ = 576812
# CHARCOAL_AVAILABILITY_FACTOR = 0.80
# CHARCOAL_LIMIT_TJ = CHARCOAL_POTENTIAL_TJ * CHARCOAL_AVAILABILITY_FACTOR

# CHARCOAL_ROUTES = ['SR', 'BF-BOF CC', 'Guseiros']

# def charcoal_limit_rule(m, year):
#     """Total charcoal consumption (TJ) <= national availability (TJ/yr)
#     Unit: production (kt) × EI (GJ/t) = TJ
#     """
#     total_charcoal_TJ = sum(
#         m.production[plant, year] * ei_by_route_fuel.get((plant_to_route[plant], 'Carvao vegetal'), 0)
#         for plant in m.Plant
#         if plant_to_route[plant] in CHARCOAL_ROUTES
#     )
#     return total_charcoal_TJ <= CHARCOAL_LIMIT_TJ

# m.CharcoalLimit = Constraint(m.Year, rule=charcoal_limit_rule)
# print(f"  Constraint F added: Charcoal limit = {CHARCOAL_LIMIT_TJ:,.0f} TJ/yr")
#%%



# --- CONSTRAINT F (UPDATED): Charcoal supply limit — ALL routes ---
# After BEN calibration, small amounts of charcoal may appear in routes
# like BF-BOF MC and EAF. The constraint must now sum charcoal consumption
# across ALL routes, not just CHARCOAL_ROUTES.
#
# This replaces the previous Constraint F that only counted SR, BF-BOF CC, Guseiros.
 
CHARCOAL_POTENTIAL_TJ = 576812
CHARCOAL_AVAILABILITY_FACTOR = 0.80
CHARCOAL_LIMIT_TJ = CHARCOAL_POTENTIAL_TJ * CHARCOAL_AVAILABILITY_FACTOR
 
def charcoal_limit_rule(m, year):
    """Total charcoal consumption (TJ) <= national availability (TJ/yr)
    Sums across ALL routes (after BEN calibration, any route may have charcoal).
    Unit: production (kt) × EI (GJ/t) = TJ
    """
    total_charcoal_TJ = sum(
        m.production[plant, year] * ei_by_route_fuel.get((plant_to_route[plant], 'Carvao vegetal'), 0)
        for plant in m.Plant
    )
    return total_charcoal_TJ <= CHARCOAL_LIMIT_TJ
 
m.CharcoalLimit = Constraint(m.Year, rule=charcoal_limit_rule)
print(f"  Constraint F added: Charcoal limit = {CHARCOAL_LIMIT_TJ:,.0f} TJ/yr (ALL routes)")
 


# --- CONSTRAINT G: Scrap supply limit for EAF ---
# Physical limit: EAF scrap consumption cannot exceed annual scrap availability.
# EAF uses approximately 85% scrap per tonne of steel produced.
# Source: Scrap_supply.csv — 'High' recovery rate scenario (kt/yr)
# Reference: Otto Hebeda (2024)
#
# Units: production_EAF (kt) × 0.85 (t scrap/t steel) = kt scrap

EAF_SCRAP_RATE = 0.85

def scrap_limit_rule(m, year):
    """Total EAF scrap consumption (kt) <= annual scrap supply High scenario (kt)"""
    total_eaf_production = sum(
        m.production[plant, year]
        for plant in m.Plant
        if plant_to_route[plant] == 'EAF'
    )
    scrap_available = float(scrap_supply.loc['High', str(year)])
    return total_eaf_production * EAF_SCRAP_RATE <= scrap_available

m.ScrapLimit = Constraint(m.Year, rule=scrap_limit_rule)
print("  Constraint G added: Scrap limit from Scrap_supply.csv (High scenario)")


# --- CONSTRAINT H: Monotonicity / Irreversibility ---
# Once production from a route grows, it cannot decrease the following year.
# Physical justification: A steel plant, once built, operates for 20-40 years.
#
# Applied to ALL routes EXCEPT BF-BOF MC (which is the one being displaced).
# This includes:
#   - Innovative routes: DR-NG, DR-H2, SR, BF-BOF-CCS (only candidate plants)
#   - Growing existing routes: EAF, BF-BOF CC (existing + new candidate plants)
#
# BF-BOF MC is excluded because it is the route being replaced by the others.
# Its production naturally declines as plants retire and are not replaced.
# Existing BF-BOF MC plants are already protected by the 70% min utilization.
 
ROUTES_WITH_MONOTONICITY = ['BF-BOF CC', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']
 
def monotonicity_rule(m, route, year):
    """Production from growing routes cannot decrease year-over-year"""
    
    # Skip the first model year (no previous year to compare)
    if year == min(m.Year):
        return Constraint.Skip
    
    prev_year = year - 1
    
    if prev_year not in m.Year:
        return Constraint.Skip
    
    # Get all plants of this route
    plants_of_route = [p for p in m.Plant if plant_to_route[p] == route]
    
    if not plants_of_route:
        return Constraint.Skip
    
    # Total production this year >= total production previous year
    return (
        sum(m.production[p, year] for p in plants_of_route)
        >= sum(m.production[p, prev_year] for p in plants_of_route)
    )
 
m.MonotonicityConstraint = Constraint(
    ROUTES_WITH_MONOTONICITY, m.Year,
    rule=monotonicity_rule
)
 
print("  Constraint H added: Monotonicity for {ROUTES_WITH_MONOTONICITY}")
print("    Production from these routes cannot decrease year-over-year")
print("    BF-BOF MC excluded (it is the route being displaced)")
 
 
# --- CONSTRAINT I: Share Balance (innovative routes replace BF-BOF MC only) ---
# The total production from innovative routes cannot exceed the historical
# BF-BOF MC share of total production. This reflects the physical reality that
# DR-NG, DR-H2, SR, and BF-BOF-CCS can only replace coal-based BF-BOF production.
# They cannot replace EAF (which uses scrap) or BF-BOF CC (which uses charcoal).
#
# Reference: Hebeda (2024) — X5+X6+X7+X8+X9+CCS <= Share_BOF_MC
# In Otto's model, X variables represent shares transferred FROM BF-BOF MC.
#
# In our plant-level model, this simplifies to:
#   sum(production from innovative routes) <= Share_BOF_MC * ProductionTarget
#
# Note: EAF and BF-BOF CC growth is controlled by their own constraints
# (scrap supply, charcoal limit, penetration limits).
 
INNOVATIVE_ROUTES = ['DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']
BASE_SHARE_BOF_MC = steel_production.loc[2023, 'Share_BOF_MC']
 
print(f"\n  BF-BOF MC base share (2023): {BASE_SHARE_BOF_MC:.3f} ({BASE_SHARE_BOF_MC:.1%})")
 
def share_balance_rule(m, year):
    """
    Innovative routes can only replace BF-BOF MC production.
    Total innovative production <= Share_BOF_MC * ProductionTarget
    """
    innovative_production = sum(
        m.production[p, year]
        for p in m.Plant
        if plant_to_route[p] in INNOVATIVE_ROUTES
    )
    
    return innovative_production <= BASE_SHARE_BOF_MC * m.ProductionTarget[year]
 
m.ShareBalance = Constraint(m.Year, rule=share_balance_rule)
 
print(f"  Constraint I added: Share balance — innovative routes <= {BASE_SHARE_BOF_MC:.1%} of production")
print(f"    Innovative routes: {INNOVATIVE_ROUTES}")
print(f"    Max innovative production in 2050: {BASE_SHARE_BOF_MC * steel_total_target.loc[2050, 'Total']:.0f} kt")





# --- CONSTRAINT J: BF-BOF CC Share Limit (16% of total production) ---
# Integrated production using charcoal uses only small blast furnaces,
# limiting the maximum share of this route in total steel production.
# Source: Pinto et al. (2018); Hebeda et al. (2023), Section 3.2
#
# Units: production (kt) / ProductionTarget (kt) = share (dimensionless)
 
CHARCOAL_ROUTE_SHARE_LIMIT = 0.16  # 16% maximum
 
def charcoal_route_share_rule(m, year):
    """BF-BOF CC production cannot exceed 16% of total steel production"""
    total_bfbof_cc = sum(
        m.production[p, year]
        for p in m.Plant
        if plant_to_route[p] == 'BF-BOF CC'
    )
    return total_bfbof_cc <= CHARCOAL_ROUTE_SHARE_LIMIT * m.ProductionTarget[year]
 
m.CharcoalRouteShareLimit = Constraint(m.Year, rule=charcoal_route_share_rule)
 
print(f"  Constraint J added: BF-BOF CC <= {CHARCOAL_ROUTE_SHARE_LIMIT:.0%} of total production")
print(f"    Source: Pinto et al. (2018) — small blast furnace scale limitation")
print(f"    Max BF-BOF CC in 2050: {CHARCOAL_ROUTE_SHARE_LIMIT * steel_total_target.loc[2050, 'Total']:.0f} kt")
 
 
# --- CONSTRAINT K: SR Share Limit (24% of total production) ---
# Smelting Reduction (Tecnored) uses charcoal but in different furnaces
# than BF-BOF CC, so it has a separate limit. The 24% represents the
# maximum penetration observed in the most ambitious scenario (SDS+)
# from Hebeda et al. (2023), consistent with biomass availability
# and technology maturity.
#
# Note: SR is ALSO constrained by:
#   - Constraint F: total charcoal consumption in TJ/yr
#   - Penetration limits from Penetration_innovative.csv
 
SR_SHARE_LIMIT = 0.24  # 24% maximum
 
def sr_share_rule(m, year):
    """SR production cannot exceed 24% of total steel production"""
    total_sr = sum(
        m.production[p, year]
        for p in m.Plant
        if plant_to_route[p] == 'SR'
    )
    return total_sr <= SR_SHARE_LIMIT * m.ProductionTarget[year]
 
m.SRShareLimit = Constraint(m.Year, rule=sr_share_rule)
 
print(f"  Constraint K added: SR <= {SR_SHARE_LIMIT:.0%} of total production")
print(f"    Source: Hebeda et al. (2023) — max observed in SDS+ scenario")
print(f"    Max SR in 2050: {SR_SHARE_LIMIT * steel_total_target.loc[2050, 'Total']:.0f} kt")



# --- CONSTRAINT L: BF-BOF MC Share Cap ---
# BF-BOF MC production cannot exceed its historical share of total production.
# This is the direct translation of Otto's formulation:
#   production_R1 = (Share_BOF_MC - X5 - X6 - X7 - X8 - X9 - CCS) × Total
# In his model, MC automatically shrinks as innovative routes enter.
# In our plant-level model, we enforce this as an upper bound.
#
# Effect: In BAU (no innovative routes), MC grows proportionally with demand
# maintaining its 2023 share. In mitigation, MC is displaced by innovative
# routes and can shrink below the cap.
#
# ═══════════════════════════════════════════════════════════════════════════
# FUTURE SCENARIO — OPTION B: Remove BF-BOF MC from candidates entirely
# ═══════════════════════════════════════════════════════════════════════════
# In a more ambitious scenario, BF-BOF MC would NOT be available for new
# construction. Existing MC plants operate until retirement (retrofitdate)
# and are NOT replaced. All new capacity comes from other routes.
#
# To implement Option B:
#   1. In Section 15, change candidate_routes to exclude 'BF-BOF MC':
#      candidate_routes = ['BF-BOF CC', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']
#   2. Remove or skip this Constraint L (it becomes redundant)
#
# Option B represents a "phase-out" scenario where no new coal-based
# steelmaking is built. This would show the cost of accelerated
# decarbonization and can be compared against Option A (the current scenario)
# to quantify the additional investment needed for a coal-free steel industry.
# ═══════════════════════════════════════════════════════════════════════════
 
# Calculate base share from calibrated data (Section 13)
bau_mc_production = plants_unified[
    plants_unified['Final_route'] == 'BF-BOF MC'
]['Production_2023_final'].sum()
 
bau_total = plants_unified['Production_2023_final'].sum()
BASE_SHARE_MC = bau_mc_production / bau_total
 
print(f"\n  BF-BOF MC base share (2023, calibrated): {BASE_SHARE_MC:.3f} ({BASE_SHARE_MC:.1%})")
 
def mc_share_cap_rule(m, year):
    """BF-BOF MC production cannot exceed its 2023 historical share"""
    total_mc = sum(
        m.production[p, year]
        for p in m.Plant
        if plant_to_route[p] == 'BF-BOF MC'
    )
    return total_mc <= BASE_SHARE_MC * m.ProductionTarget[year]
 
m.MCShareCap = Constraint(m.Year, rule=mc_share_cap_rule)
 
print(f"  Constraint L added: BF-BOF MC <= {BASE_SHARE_MC:.1%} of total production")
print(f"    Max BF-BOF MC in 2050: {BASE_SHARE_MC * steel_total_target.loc[2050, 'Total']:.0f} kt")
print(f"    (Option A — Otto's approach: MC share frozen at 2023 level)")
print(f"    (Option B — phase-out scenario: registered for future implementation)")
 

#%% model

#==============================================================================
# SECTION 23: DEFINE OBJECTIVE FUNCTION (CAPEX + OPEX + FUEL COSTS)
#==============================================================================
#
# Minimize total cost = CAPEX (levelized) + OPEX + FUEL COSTS
#
# Following Hebeda (2024) methodology:
#   - CAPEX: USD/t × production × LEVELIZED_FACTOR, charged EVERY active year
#   - OPEX:  USD/t × production, charged every active year
#   - FUEL:  USD/t × production, charged every active year
#
# CAPEX is annualized: the one-time investment per tonne is converted to an
# annual payment via the capital recovery factor (LEVELIZED_FACTOR).
# This annual payment is charged in every year the plant operates.
#
# Both CAPEX and OPEX are proportional to PRODUCTION (not capacity).
# This means the optimizer sees the true per-tonne cost of each technology.
#==============================================================================
 
def obj_rule(m):
    """
    Minimize total cost = CAPEX (levelized) + OPEX + FUEL COSTS
    
    All costs are proportional to production (kt) and in consistent units.
    CAPEX uses LEVELIZED_FACTOR to convert one-time investment to annual cost.
    """
    total = 0
    
    for plant in m.Plant:
        tech = plant_to_route[plant]
        
        # Get cost parameters (default to 0 if missing)
        if tech in measures_dict:
            capex = float(measures_dict[tech].get('CAPEX', 0) or 0)        # USD/t
            opex = float(measures_dict[tech].get('OPEX', 0) or 0)          # USD/t
            fuel_cost = float(measures_dict[tech].get('Fuel_cost_USD_t', 0) or 0)  # USD/t
        else:
            capex = 0
            opex = 0
            fuel_cost = 0
        
        for year in m.Year:
            # Only charge costs when plant is active
            if not is_plant_active(plant, year):
                continue
            
            # CAPEX: annualized payment, charged every active year
            # Annual CAPEX = CAPEX_per_tonne × production × levelized_factor
            total += capex * m.production[plant, year] * LEVELIZED_FACTOR
            
            # OPEX: charged every year based on production
            total += opex * m.production[plant, year]
            
            # FUEL COSTS: charged every year based on production
            total += fuel_cost * m.production[plant, year]
    
    return total
 
m.Objective = Objective(rule=obj_rule, sense=minimize)
 
print("Model built successfully!")
print(f"  - Plants: {len(plant_names)}")
print(f"  - Years: {len(model_years)}")
print(f"  - Variables: ~{len(plant_names) * len(model_years)}")
print(f"  - Objective: minimize(CAPEX_levelized + OPEX + FUEL_COSTS)")
print(f"  - CAPEX method: annuity every active year (production x CAPEX x {LEVELIZED_FACTOR:.4f})")
print(f"  - OPEX method: every active year (production x OPEX)")
print(f"  - FUEL method: every active year (production x fuel_cost_USD_t)")



#==============================================================================
# SECTION 24: PRE-SOLVE FEASIBILITY CHECK
#==============================================================================

print("\n=== PRE-SOLVE FEASIBILITY CHECK ===")

# Check 1: Capacity vs Production Target
print("\n--- Check 1: Existing Plant Capacity vs Production Target ---")
for year in model_years[:10]:
    existing_capacity = sum(
        plant_attr[p]['Capacity'] 
        for p in existing_plants 
        if is_plant_active(p, year)
    )
    
    min_existing_production = sum(
        plant_attr[p]['Capacity'] * MINIMUM_UTILIZATION_EXISTING
        for p in existing_plants 
        if is_plant_active(p, year)
    )
    
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
          f"Min Prod={min_existing_production:.0f} [{status}]")

# Check 2: Emission constraint feasibility
print("\n--- Check 2: Emission Constraint Check ---")
for year in [2023, 2030, 2040, 2050]:
    if year in model_years:
        min_emissions = sum(
            plant_attr[p]['Capacity'] * MINIMUM_UTILIZATION_EXISTING * 
            measures_dict.get(plant_to_route[p], {}).get('Emission_intensity', 0)
            for p in existing_plants
            if is_plant_active(p, year) and plant_to_route[p] in measures_dict
        )
        
        limit = emission_limit_dict[year]
        status = "OK" if min_emissions <= limit else "INFEASIBLE!"
        print(f"  {year}: Min Emissions={min_emissions:.0f}, Limit={limit:.0f} [{status}]")

print("\n" + "="*60)

#==============================================================================
# SECTION 25: SOLVE THE MODEL
#==============================================================================

print("\n=== SOLVING MODEL ===")

solver_name = "ipopt"
solver = SolverFactory(
    solver_name + "nl", 
    executable=modules.find(solver_name), 
    solve_io="nl"
)

result_solver = solver.solve(m, tee=True)



#%% 
print("\n=== DIAGNOSTIC: Emission Floor E2 ===")
if hasattr(m, 'EmissionFloorE2'):
    print(f"  Constraint exists: YES")
    for year in list(m.Year)[1:]:
        prev = year - 1
        emiss_curr = sum(
            m.production[p, year].value * measures_dict.get(plant_to_route[p], {}).get('Emission_factor_kg_t', 0) / 1000
            for p in m.Plant if plant_to_route[p] in measures_dict
        )
        emiss_prev = sum(
            m.production[p, prev].value * measures_dict.get(plant_to_route[p], {}).get('Emission_factor_kg_t', 0) / 1000
            for p in m.Plant if plant_to_route[p] in measures_dict
        )
        if emiss_prev > 0:
            drop = (emiss_prev - emiss_curr) / emiss_prev * 100
            flag = " *** VIOLATION ***" if drop > 5.1 else ""
            if drop > 3:
                print(f"  {prev}->{year}: {emiss_prev:,.0f} -> {emiss_curr:,.0f} ({drop:+.1f}%){flag}")
else:
    print("  Constraint EmissionFloorE2 NOT FOUND!")

#%%


# Check solver status
print("\n=== SOLVER STATUS ===")
print(f"Termination condition: {result_solver.solver.termination_condition}")

if str(result_solver.solver.termination_condition) == "infeasible":
    print("\n*** MODEL IS INFEASIBLE ***")
    print("Possible causes:")
    print("  1. Minimum utilization constraint too high")
    print("  2. Emission limits too restrictive")
    print("  3. Penetration limits conflict with existing capacity")
    print(f"\nTry reducing MINIMUM_UTILIZATION_EXISTING (currently {MINIMUM_UTILIZATION_EXISTING:.0%})")

#==============================================================================
# SECTION 26: EXTRACT AND PROCESS RESULTS
#==============================================================================

print("\n=== PROCESSING RESULTS ===")

# --- Production by plant and year (long format) ---
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

# --- Production by Plant (wide format) ---
plant_info = production_df_long[['Plant', 'Final_route', 'Startyear', 'Retrofitdate', 'Capacity']].drop_duplicates()
production_pivot = production_df_long.pivot(index='Plant', columns='Year', values='Production').reset_index()
production_by_plant_wide = plant_info.merge(production_pivot, on='Plant')

year_columns = sorted([col for col in production_by_plant_wide.columns if isinstance(col, int)])
info_columns = ['Plant', 'Final_route', 'Startyear', 'Retrofitdate', 'Capacity']
production_by_plant_wide = production_by_plant_wide[info_columns + year_columns]
production_by_plant_wide = production_by_plant_wide.sort_values(['Final_route', 'Plant']).reset_index(drop=True)

print(f"Production by Plant table: {len(production_by_plant_wide)} plants x {len(year_columns)} years")

# --- Production by Route (wide format) ---
prod_by_route_long = production_df_long.groupby(["Final_route", "Year"])["Production"].sum().reset_index()
production_by_route_wide = prod_by_route_long.pivot(index='Final_route', columns='Year', values='Production').reset_index()
production_by_route_wide = production_by_route_wide.rename(columns={'Final_route': 'Route'})

total_row = production_by_route_wide.select_dtypes(include=[np.number]).sum()
total_row_df = pd.DataFrame([['TOTAL'] + total_row.tolist()], columns=production_by_route_wide.columns)
production_by_route_wide = pd.concat([production_by_route_wide, total_row_df], ignore_index=True)

print(f"Production by Route table: {len(production_by_route_wide)} routes x {len(year_columns)} years")

# --- Total production by year ---
production_total_df = (
    production_df_long
    .groupby("Year", as_index=False)["Production"]
    .sum()
    .rename(columns={"Production": "Total_Production"})
)

production_total_wide = production_total_df.set_index('Year').T
production_total_wide.index = ['Total_Production']

# --- Incremental production (new plants only) ---
incremental_production_df = production_df_long[
    production_df_long["Startyear"] == production_df_long["Year"]
].copy()
incremental_production_df["Technology"] = incremental_production_df["Final_route"]
incremental_production_df.rename(columns={"Production": "Production_Expansion"}, inplace=True)

incremental_by_route = incremental_production_df.groupby(['Technology', 'Year'])['Production_Expansion'].sum().reset_index()
incremental_by_route_wide = incremental_by_route.pivot(
    index='Technology', columns='Year', values='Production_Expansion'
).fillna(0).reset_index()

#==============================================================================
# SECTION 26B: CALCULATE DETAILED EMISSIONS (Hebeda 2024 methodology)
#==============================================================================

print("\n=== CALCULATING DETAILED EMISSIONS (Process vs Energy) ===")

emissions_detailed = []

for plant in m.Plant:
    route = plant_to_route[plant]
    
    for year in m.Year:
        prod = m.production[plant, year].value or 0
        
        if prod == 0:
            continue
        
        if route not in fuels_by_route:
            # Route not in EI file - use zero emissions
            continue
        
        # Initialize
        proc_co2, proc_ch4, proc_n2o = 0, 0, 0
        ener_co2, ener_ch4, ener_n2o = 0, 0, 0
        
        for fuel in fuels_by_route[route]:
            ei = ei_by_route_fuel.get((route, fuel), 0)
            mapped_fuel = FUEL_NAME_MAPPING.get(fuel, fuel)
            
            if mapped_fuel in emission_factor.index:
                ef_co2 = emission_factor.loc[mapped_fuel, 'CO2']
                ef_ch4 = emission_factor.loc[mapped_fuel, 'CH4']
                ef_n2o = emission_factor.loc[mapped_fuel, 'N2O']
            else:
                ef_co2, ef_ch4, ef_n2o = 0, 0, 0
            
            # prod (kt) × ei (GJ/t) × ef (kg/GJ) / 1000 = kt
            emiss_co2 = prod * ei * ef_co2 / 1000
            emiss_ch4 = prod * ei * ef_ch4 / 1000
            emiss_n2o = prod * ei * ef_n2o / 1000
            
            # === CCS CAPTURE CORRECTION ===
            # Applied only for BF-BOF-CCS route.
            # CCS captures 80% of CO2 only — CH4 and N2O are unaffected.
            if route == 'BF-BOF-CCS':
                emiss_co2 = emiss_co2 * (1 - CAPTURE_RATE_CCS)
            # (no change to emiss_ch4 or emiss_n2o)
            
            # Classify as process or energy (Hebeda methodology)
            if fuel in COMBUSTIVEIS_PROCESSO:
                proc_co2 += emiss_co2
                proc_ch4 += emiss_ch4
                proc_n2o += emiss_n2o
            else:
                ener_co2 += emiss_co2
                ener_ch4 += emiss_ch4
                ener_n2o += emiss_n2o
        
        # Calculate CO2e using GWP
        proc_co2e = proc_co2 + proc_ch4 * GWP_CH4 + proc_n2o * GWP_N2O
        ener_co2e = ener_co2 + ener_ch4 * GWP_CH4 + ener_n2o * GWP_N2O
        
        emissions_detailed.append({
            'Plant': plant,
            'Route': route,
            'Year': year,
            'Production_kt': prod,
            'Process_CO2_kt': proc_co2,
            'Process_CH4_kt': proc_ch4,
            'Process_N2O_kt': proc_n2o,
            'Process_CO2e_kt': proc_co2e,
            'Energy_CO2_kt': ener_co2,
            'Energy_CH4_kt': ener_ch4,
            'Energy_N2O_kt': ener_n2o,
            'Energy_CO2e_kt': ener_co2e,
            'Total_CO2e_kt': proc_co2e + ener_co2e,
        })

emissions_detailed_df = pd.DataFrame(emissions_detailed)

# Aggregate by year
emissions_by_year = emissions_detailed_df.groupby('Year').agg({
    'Production_kt': 'sum',
    'Process_CO2_kt': 'sum',
    'Process_CH4_kt': 'sum',
    'Process_N2O_kt': 'sum',
    'Process_CO2e_kt': 'sum',
    'Energy_CO2_kt': 'sum',
    'Energy_CH4_kt': 'sum',
    'Energy_N2O_kt': 'sum',
    'Energy_CO2e_kt': 'sum',
    'Total_CO2e_kt': 'sum',
}).reset_index()

# Aggregate by route and year
emissions_by_route_year = emissions_detailed_df.groupby(['Route', 'Year']).agg({
    'Production_kt': 'sum',
    'Process_CO2e_kt': 'sum',
    'Energy_CO2e_kt': 'sum',
    'Total_CO2e_kt': 'sum',
}).reset_index()

# For backward compatibility - create emissions_df like before
emissions_df = emissions_by_year[['Year', 'Total_CO2e_kt']].copy()
emissions_df.columns = ['Year', 'Emissions']

emissions_wide = emissions_df.set_index('Year').T
emissions_wide.index = ['Emissions_ktCO2eq']

emission_limits_row = pd.DataFrame(
    [[emission_limit_dict.get(y, np.nan) for y in sorted(emissions_df['Year'])]],
    columns=sorted(emissions_df['Year']),
    index=['Emission_Limit_ktCO2eq']
)
emissions_comparison_wide = pd.concat([emissions_wide, emission_limits_row])

print("\nEmissions by Year (Process vs Energy, kt CO2e):")
for year in [2023, 2030, 2040, 2050]:
    if year in emissions_by_year['Year'].values:
        row = emissions_by_year[emissions_by_year['Year'] == year].iloc[0]
        print(f"  {year}: Process={row['Process_CO2e_kt']:,.0f}, Energy={row['Energy_CO2e_kt']:,.0f}, "
              f"Total={row['Total_CO2e_kt']:,.0f} kt CO2e")


#%%
#==============================================================================
# SECTION 27: CALCULATE COSTS BY COMPONENT
#==============================================================================
#
# Must mirror the objective function logic exactly (Section 23):
#   - CAPEX: production × CAPEX_per_tonne × LEVELIZED_FACTOR, every active year
#   - OPEX:  production × OPEX_per_tonne, every active year
#   - FUEL:  production × fuel_cost_USD_t, every active year
#==============================================================================
 
print("\n=== CALCULATING COST BREAKDOWN ===")
 
cost_breakdown = []
 
for year in m.Year:
    year_capex = 0
    year_opex = 0
    year_fuel = 0
    
    for plant in m.Plant:
        tech = plant_to_route[plant]
        prod = m.production[plant, year].value or 0
        
        if prod == 0:
            continue
        
        if tech in measures_dict:
            capex = float(measures_dict[tech].get('CAPEX', 0) or 0)
            opex = float(measures_dict[tech].get('OPEX', 0) or 0)
            fuel_cost = float(measures_dict[tech].get('Fuel_cost_USD_t', 0) or 0)
            
            # CAPEX: annualized, every active year, proportional to production
            year_capex += capex * prod * LEVELIZED_FACTOR
            
            # OPEX: every year, proportional to production
            year_opex += opex * prod
            
            # FUEL: every year, proportional to production
            year_fuel += fuel_cost * prod
    
    cost_breakdown.append({
        'Year': year,
        'CAPEX_levelized': year_capex,
        'OPEX': year_opex,
        'Fuel_Cost': year_fuel,
        'Total_Cost': year_capex + year_opex + year_fuel
    })
 
cost_df = pd.DataFrame(cost_breakdown)
 
print("\nCost Summary (selected years, million USD):")
for year in [2023, 2030, 2040, 2050]:
    if year in cost_df['Year'].values:
        row = cost_df[cost_df['Year'] == year].iloc[0]
        print(f"  {year}: CAPEX={row['CAPEX_levelized']/1e6:.1f}M, OPEX={row['OPEX']/1e6:.1f}M, "
              f"Fuel={row['Fuel_Cost']/1e6:.1f}M, Total={row['Total_Cost']/1e6:.1f}M USD")
 
# Create cost breakdown wide format
cost_wide = cost_df.set_index('Year').T

#==============================================================================
# SECTION 28: CALCULATE ENERGY CONSUMPTION BY ROUTE
#==============================================================================

print("\n=== CALCULATING ENERGY CONSUMPTION ===")

# Energy consumption calculation:
# Production (kt) * Energy Intensity (GJ/t) = 1000 t * GJ/t = 1000 GJ
# Convert to ktep: 1000 GJ / 41.868 = ktep (since 1 tep = 41.868 GJ)
# Simplified: EC (ktep) = Production (kt) * EI (GJ/t) / 41.868

energy_consumption = []
    
for year in m.Year:
    for route in routes_in_plants:
        # Get total production for this route
        prod = sum(
            m.production[plant, year].value or 0
            for plant in m.Plant
            if plant_to_route[plant] == route
        )
        
        # Get energy intensity for this route (GJ/t)
        # Get energy intensity for this route (GJ/t)
        # All routes (existing + innovative) are in EI_by_route
        # populated in Section 4 from EI_BEU + EI_Route_Fuel_SIMPLIFIED.csv
        ei = EI_by_route.get(route, 0)
        

        ec_ktep = prod * ei / TEP_TO_GJ
        
        energy_consumption.append({
            'Year': year,
            'Route': route,
            'Production_kt': prod,
            'Energy_Intensity_GJ_t': ei,
            'Energy_Consumption_ktep': ec_ktep
        })

energy_df = pd.DataFrame(energy_consumption)

# Pivot for wide format
energy_by_route_wide = energy_df.pivot_table(
    index='Route',
    columns='Year',
    values='Energy_Consumption_ktep',
    aggfunc='sum'
).reset_index()

# Total energy consumption by year
total_energy_by_year = energy_df.groupby('Year')['Energy_Consumption_ktep'].sum().reset_index()
total_energy_by_year.columns = ['Year', 'Total_Energy_ktep']

print("\nTotal Energy Consumption (selected years, ktep):")
for year in [2023, 2030, 2040, 2050]:
    if year in total_energy_by_year['Year'].values:
        val = total_energy_by_year[total_energy_by_year['Year'] == year]['Total_Energy_ktep'].values[0]
        print(f"  {year}: {val:,.0f} ktep")

print("\nResults processing complete!")


#==============================================================================
# SECTION 28B: CALCULATE ENERGY CONSUMPTION BY FUEL AND YEAR
#==============================================================================
#
# Disaggregates total energy consumption into individual fuels.
# For each year: consumption_fuel = Σ (production_route × EI_route_fuel)
#
# Data sources:
#   - Production by route/year: from optimization results (prod_by_route_long)
#   - EI by route and fuel: ei_by_route_fuel from EI_Route_Fuel_SIMPLIFIED.csv
#
# Output units: TJ (production in kt × EI in GJ/t = TJ)
# Also converted to ktep for compatibility with BEN (1 ktep = 41.868 TJ)
#==============================================================================
 
print("\n=== CALCULATING ENERGY CONSUMPTION BY FUEL AND YEAR ===")
 
# Build fuel consumption table
fuel_consumption_records = []
 
for year in m.Year:
    for route in routes_in_plants:
        # Get total production for this route in this year
        prod = sum(
            m.production[plant, year].value or 0
            for plant in m.Plant
            if plant_to_route[plant] == route
        )
        
        if prod == 0:
            continue
        
        # Get all fuels for this route from ei_by_route_fuel
        route_fuels = {fuel: ei for (r, fuel), ei in ei_by_route_fuel.items() if r == route}
        
        for fuel, ei in route_fuels.items():
            if ei == 0:
                continue
            
            # consumption: prod (kt) × ei (GJ/t) = TJ
            consumption_tj = prod * ei
            consumption_ktep = consumption_tj / TEP_TO_GJ
            
            fuel_consumption_records.append({
                'Year': year,
                'Route': route,
                'Combustivel': fuel,
                'Production_kt': prod,
                'EI_GJ_t': ei,
                'Consumption_TJ': consumption_tj,
                'Consumption_ktep': consumption_ktep,
            })
 
fuel_consumption_df = pd.DataFrame(fuel_consumption_records)
 
# --- Aggregate by fuel and year (main result table) ---
fuel_by_year = fuel_consumption_df.groupby(['Combustivel', 'Year']).agg({
    'Consumption_TJ': 'sum',
    'Consumption_ktep': 'sum',
}).reset_index()
 
# Wide format: fuels as rows, years as columns (TJ)
fuel_by_year_wide_tj = fuel_by_year.pivot_table(
    index='Combustivel',
    columns='Year',
    values='Consumption_TJ',
    aggfunc='sum'
).fillna(0)
 
# Wide format: fuels as rows, years as columns (ktep)
fuel_by_year_wide_ktep = fuel_by_year.pivot_table(
    index='Combustivel',
    columns='Year',
    values='Consumption_ktep',
    aggfunc='sum'
).fillna(0)
 
# Add total row
fuel_by_year_wide_tj.loc['TOTAL'] = fuel_by_year_wide_tj.sum()
fuel_by_year_wide_ktep.loc['TOTAL'] = fuel_by_year_wide_ktep.sum()
 
# --- Aggregate by fuel, route, and year (detailed breakdown) ---
fuel_by_route_year = fuel_consumption_df.groupby(['Route', 'Combustivel', 'Year']).agg({
    'Consumption_TJ': 'sum',
    'Consumption_ktep': 'sum',
}).reset_index()
 
# --- Fuel share by year ---
fuel_share_by_year = fuel_by_year_wide_tj.copy()
for col in fuel_share_by_year.columns:
    total = fuel_share_by_year.loc['TOTAL', col]
    if total > 0:
        fuel_share_by_year[col] = fuel_share_by_year[col] / total
# Remove total row from share (it would be 1.0)
fuel_share_by_year = fuel_share_by_year.drop('TOTAL', errors='ignore')
 
# --- Print summary ---
print("\nFuel consumption by fuel (selected years, TJ):")
for year in [2023, 2030, 2040, 2050]:
    if year in fuel_by_year_wide_tj.columns:
        print(f"\n  {year}:")
        col = fuel_by_year_wide_tj[year]
        for fuel in col.index:
            if fuel != 'TOTAL' and col[fuel] > 0:
                share = col[fuel] / col['TOTAL'] * 100 if col['TOTAL'] > 0 else 0
                print(f"    {fuel}: {col[fuel]:>12,.0f} TJ ({share:>5.1f}%)")
        print(f"    {'TOTAL':}: {col['TOTAL']:>12,.0f} TJ")
 
print("\nFuel consumption tables created:")
print(f"  - fuel_by_year_wide_tj:    {fuel_by_year_wide_tj.shape[0]} fuels x {fuel_by_year_wide_tj.shape[1]} years (TJ)")
print(f"  - fuel_by_year_wide_ktep:  {fuel_by_year_wide_ktep.shape[0]} fuels x {fuel_by_year_wide_ktep.shape[1]} years (ktep)")
print(f"  - fuel_share_by_year:      {fuel_share_by_year.shape[0]} fuels x {fuel_share_by_year.shape[1]} years (%)")
print(f"  - fuel_by_route_year:      {len(fuel_by_route_year)} records (long format, by route)")



#==============================================================================
# SECTION 28C: ENERGY SOURCE CLASSIFICATION (Electricity, Biomass, Fossil)
#==============================================================================
#
# Classifies all fuels into three groups and calculates their share
# in total energy consumption over time.
#
# Groups:
#   - Electricity: Eletricidade
#   - Biomass: Carvao vegetal (renewable, planted forests)
#   - Fossil: all others (coal, coke, natural gas, oil, LPG, etc.)
#
# This analysis shows the energy transition trajectory of the steel sector.
# Reference: Hebeda (2024) Table 20 and Table 24.
#==============================================================================
 
print("\n=== ENERGY SOURCE CLASSIFICATION (Electricity / Biomass / Fossil) ===")
 
# --- Classification of fuels into groups ---
FUEL_GROUP = {
    'Eletricidade': 'Electricity',
    'Carvao vegetal': 'Biomass',
    'Carvao metalurgico': 'Fossil',
    'Coque de carvao mineral': 'Fossil',
    'Gas natural': 'Fossil',
    'Oleo combustivel': 'Fossil',
    'Oleo diesel': 'Fossil',
    'GLP': 'Fossil',
    'Gas cidade': 'Fossil',
    'Gases cidade': 'Fossil',
    'Outras fontes primarias': 'Fossil',
    'Outras fontes secundarias': 'Fossil',
}
 
# Add group column to fuel consumption data
fuel_consumption_grouped = fuel_consumption_df.copy()
fuel_consumption_grouped['Energy_Group'] = fuel_consumption_grouped['Combustivel'].map(FUEL_GROUP)
 
# Check for unmapped fuels
unmapped = fuel_consumption_grouped[fuel_consumption_grouped['Energy_Group'].isna()]['Combustivel'].unique()
if len(unmapped) > 0:
    print(f"  WARNING: Unmapped fuels (defaulting to 'Fossil'): {unmapped.tolist()}")
    fuel_consumption_grouped['Energy_Group'] = fuel_consumption_grouped['Energy_Group'].fillna('Fossil')
 
# --- Aggregate by group and year ---
group_by_year = fuel_consumption_grouped.groupby(['Energy_Group', 'Year']).agg({
    'Consumption_TJ': 'sum',
    'Consumption_ktep': 'sum',
}).reset_index()
 
# Wide format: groups as rows, years as columns (TJ)
group_by_year_wide_tj = group_by_year.pivot_table(
    index='Energy_Group',
    columns='Year',
    values='Consumption_TJ',
    aggfunc='sum'
).fillna(0)
 
# Ensure consistent row order
group_order = ['Biomass', 'Electricity', 'Fossil']
group_by_year_wide_tj = group_by_year_wide_tj.reindex(
    [g for g in group_order if g in group_by_year_wide_tj.index]
)
 
# Add total row
group_by_year_wide_tj.loc['TOTAL'] = group_by_year_wide_tj.sum()
 
# --- Calculate shares ---
group_share_by_year = group_by_year_wide_tj.drop('TOTAL', errors='ignore').copy()
for col in group_share_by_year.columns:
    total = group_by_year_wide_tj.loc['TOTAL', col]
    if total > 0:
        group_share_by_year[col] = group_share_by_year[col] / total
 
# --- Renewable vs Fossil summary ---
# Renewable = Biomass + Electricity (Brazil's grid is ~90% renewable)
renewable_share = group_share_by_year.copy()
renewable_share.loc['Renewable (Biomass + Electricity)'] = (
    renewable_share.loc['Biomass'] + renewable_share.loc['Electricity']
)
renewable_share.loc['Fossil'] = renewable_share.loc['Fossil']
renewable_summary = renewable_share.loc[['Renewable (Biomass + Electricity)', 'Fossil']]
 
# --- Print summary ---
print("\nEnergy source shares (selected years):")
print(f"  {'Year':>6} | {'Biomass':>8} | {'Electricity':>11} | {'Fossil':>7} | {'Renewable':>9}")
print(f"  {'-'*6} | {'-'*8} | {'-'*11} | {'-'*7} | {'-'*9}")
for year in [2023, 2025, 2030, 2035, 2040, 2045, 2050]:
    if year in group_share_by_year.columns:
        bio = group_share_by_year.loc['Biomass', year] * 100
        elec = group_share_by_year.loc['Electricity', year] * 100
        fos = group_share_by_year.loc['Fossil', year] * 100
        ren = bio + elec
        print(f"  {year:>6} | {bio:>7.1f}% | {elec:>10.1f}% | {fos:>6.1f}% | {ren:>8.1f}%")
 
print(f"\n  Classification:")
print(f"    Biomass:     Carvao vegetal (planted forests)")
print(f"    Electricity: Eletricidade (~90% renewable in Brazil)")
print(f"    Fossil:      Coal, coke, natural gas, oil, LPG, etc.")

#%% parar DIAGNOSTIC:
# --- DIAGNOSTIC: What fuels are actually in the model? ---
print("\n=== DIAGNOSTIC: All fuels in ei_by_route_fuel ===")
all_fuels_in_model = sorted(set(fuel for (route, fuel) in ei_by_route_fuel.keys()))
for fuel in all_fuels_in_model:
    routes_using = [r for (r, f) in ei_by_route_fuel.keys() if f == fuel and ei_by_route_fuel[(r,f)] > 0]
    group = FUEL_GROUP.get(fuel, '*** UNMAPPED ***')
    print(f"  {fuel:.<40s} {group:<12s}  used by: {routes_using}")
#%% parar

#==============================================================================
# SECTION 29: VISUALIZE RESULTS
#==============================================================================

print("\n=== GENERATING PLOTS ===")

# Plot 1: Production by route over time
plt.figure(figsize=(12, 6))
for tech in prod_by_route_long["Final_route"].unique():
    subset = prod_by_route_long[prod_by_route_long["Final_route"] == tech]
    if subset["Production"].sum() > 0:
        plt.plot(subset["Year"], subset["Production"], label=tech, linewidth=2)

plt.title("Annual Production by Technology Route")
plt.xlabel("Year")
plt.ylabel("Production (kt)")
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('production_by_route.png', dpi=150)
plt.show()

# Plot 2: Cost breakdown over time
plt.figure(figsize=(12, 6))
plt.stackplot(cost_df['Year'], 
              cost_df['CAPEX_levelized']/1e6, 
              cost_df['OPEX']/1e6, 
              cost_df['Fuel_Cost']/1e6,
              labels=['CAPEX (levelized)', 'OPEX', 'Fuel Costs'],
              alpha=0.8)
plt.title("Annual Cost Breakdown")
plt.xlabel("Year")
plt.ylabel("Cost (Million USD)")
plt.legend(loc='upper left')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('cost_breakdown.png', dpi=150)
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

# Plot 4: Energy consumption by route
plt.figure(figsize=(12, 6))
energy_pivot = energy_df.pivot_table(index='Year', columns='Route', values='Energy_Consumption_ktep', aggfunc='sum')
energy_pivot.plot(kind='area', stacked=True, figsize=(12, 6), alpha=0.8)
plt.title("Energy Consumption by Route")
plt.xlabel("Year")
plt.ylabel("Energy Consumption (ktep)")
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('energy_consumption.png', dpi=150)
plt.show()

#==============================================================================
# SECTION 30: EXPORT RESULTS TO EXCEL
#==============================================================================

print("\n=== EXPORTING RESULTS ===")

output_path = r"C:\Users\Bruna\OneDrive\DOUTORADO\0.TESE\modelagem\modelo_bru\teste\resultados\resultados_modelo_V17.xlsx"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with pd.ExcelWriter(output_path) as writer:
    # --- MAIN RESULTS ---
    production_by_plant_wide.to_excel(writer, sheet_name="Production_by_Plant", index=False, freeze_panes=(1, 5))
    production_by_route_wide.to_excel(writer, sheet_name="Production_by_Route", index=False, freeze_panes=(1, 1))
    incremental_by_route_wide.to_excel(writer, sheet_name="Incremental_by_Route", index=False, freeze_panes=(1, 1))
    emissions_comparison_wide.to_excel(writer, sheet_name="Emissions", index=True)
    
    # --- DETAILED EMISSIONS (Hebeda 2024 methodology) ---
    emissions_by_year.to_excel(writer, sheet_name="Emissions_Detailed_Year", index=False)
    emissions_by_route_year.to_excel(writer, sheet_name="Emissions_by_Route_Year", index=False)
    
    # Emission factors summary (calculated from EI × EF)
    ef_summary = pd.DataFrame([
        {'Route': route, 
         'EF_kg_CO2e_per_t': emission_factor_by_route.get(route, 0),
         'EF_t_CO2e_per_t': emission_factor_by_route.get(route, 0) / 1000}
        for route in sorted(emission_factor_by_route.keys())
    ])
    ef_summary.to_excel(writer, sheet_name="Emission_Factors_by_Route", index=False)
    
    # --- COST RESULTS ---
    cost_df.to_excel(writer, sheet_name="Cost_Breakdown", index=False)
    cost_wide.to_excel(writer, sheet_name="Cost_by_Year", index=True)
    
    # --- ENERGY RESULTS (in ktep) ---
    energy_by_route_wide.to_excel(writer, sheet_name="Energy_by_Route_ktep", index=False)
    total_energy_by_year.to_excel(writer, sheet_name="Total_Energy_ktep", index=False)
    
    # --- ENERGY GROUP RESULTS ---
     # Energy consumption by group (Biomass/Electricity/Fossil) in TJ
    group_by_year_wide_tj.to_excel(writer, sheet_name="Energy_Groups_TJ", index=True)
    
    # Energy group shares by year (%)
    group_share_by_year.to_excel(writer, sheet_name="Energy_Groups_Share", index=True)
    
    # Renewable vs Fossil summary
    renewable_summary.to_excel(writer, sheet_name="Renewable_vs_Fossil", index=True)
    
    
    # --- SUPPORTING DATA ---
    production_df_long.to_excel(writer, sheet_name="Production_Detail_Long", index=False)
    production_total_df.to_excel(writer, sheet_name="Total_Production", index=False)
    
    # --- FUEL COST PARAMETERS ---
    fuel_cost_df = pd.DataFrame([
        {'Route': route, 'Fuel_Cost_BRL_t': cost, 'Fuel_Cost_USD_t': cost/DOLAR_TO_BRL}
        for route, cost in fuel_cost_per_tonne.items()
    ])
    fuel_cost_df.to_excel(writer, sheet_name="Fuel_Cost_Parameters", index=False)
    
    # --- SUMMARY ---
    summary_df = pd.DataFrame({
        'Metric': [
            'Model Version',
            'Base Year', 
            'Horizon End', 
            'Total Plants', 
            'Existing Plants',
            'Candidate Plants', 
            'Base Production (kt)', 
            'Target 2050 (kt)', 
            'Emission Limit 2020 (kt CO2eq)',
            'Emission Limit 2050 (kt CO2eq)',
            'Minimum Utilization Existing',
            'Levelized Cost Factor',
            'Exchange Rate (USD to BRL)',
            'Emission Methodology'
        ],
        'Value': [
            'V5',
            2023, 
            2050, 
            len(plants_unified), 
            len(existing_plants),
            candidate_count,
            base_production, 
            steel_total_target.loc[2050, 'Total'], 
            emission_2020,
            emission_2050,
            MINIMUM_UTILIZATION_EXISTING,
            LEVELIZED_FACTOR,
            DOLAR_TO_BRL,
            'Hebeda (2024) - EI x EF'
        ]
    })
    summary_df.to_excel(writer, sheet_name="Summary", index=False)
    
    
    
    # --- INPUT PARAMETERS ---
    penetration_innovative.to_excel(writer, sheet_name="Input_Penetration_Limits")
    
    tecnologias_export = pd.DataFrame(measures_dict).T
    tecnologias_export.index.name = 'Technology'
    tecnologias_export.to_excel(writer, sheet_name="Input_Technology_Params")
    
    
    
    # --- BAU SCENARIO RESULTS ---
 
    # BAU Production by route (wide)
    bau_production_wide.to_excel(writer, sheet_name="BAU_Production_by_Route", index=True)
    
    # BAU Emissions by year (Process vs Energy)
    bau_emissions_by_year.to_excel(writer, sheet_name="BAU_Emissions_by_Year", index=False)
    
    # BAU Emissions by route and year
    bau_emissions_by_route.to_excel(writer, sheet_name="BAU_Emissions_by_Route", index=False)
    
    # BAU Cost breakdown
    bau_cost_df.to_excel(writer, sheet_name="BAU_Cost_Breakdown", index=False)
    
    # BAU Fuel consumption by fuel (TJ)
    bau_fuel_wide_tj.to_excel(writer, sheet_name="BAU_Fuel_TJ", index=True)
    
    # BAU Fuel consumption by fuel (ktep)
    bau_fuel_wide_ktep.to_excel(writer, sheet_name="BAU_Fuel_ktep", index=True)
    
    # BAU Fuel shares
    bau_fuel_share.to_excel(writer, sheet_name="BAU_Fuel_Share", index=True)
    
    # BAU Energy groups (Biomass/Electricity/Fossil)
    bau_group_wide.to_excel(writer, sheet_name="BAU_Energy_Groups_TJ", index=True)
    bau_group_share.to_excel(writer, sheet_name="BAU_Energy_Groups_Share", index=True)
    
    # BAU Total energy consumption
    bau_total_energy.to_excel(writer, sheet_name="BAU_Total_Energy", index=False)
    
    # --- SCENARIO COMPARISON ---
    # Emissions: BAU vs Mitigation side by side
    bau_emiss_simple = bau_emissions_by_year[['Year', 'Total_CO2e_kt']].copy()
    bau_emiss_simple.columns = ['Year', 'BAU_Emissions_kt']
    
    mit_emiss_simple = emissions_df[['Year', 'Emissions']].copy()
    mit_emiss_simple.columns = ['Year', 'Mitigation_Emissions_kt']
    
    scenario_comparison = bau_emiss_simple.merge(mit_emiss_simple, on='Year', how='outer')
    scenario_comparison['Emission_Reduction_kt'] = (
        scenario_comparison['BAU_Emissions_kt'] - scenario_comparison['Mitigation_Emissions_kt']
    )
    scenario_comparison['Reduction_Percent'] = (
        scenario_comparison['Emission_Reduction_kt'] / scenario_comparison['BAU_Emissions_kt'] * 100
    )
    
    # Costs: BAU vs Mitigation
    bau_cost_simple = bau_cost_df[['Year', 'Total_Cost']].copy()
    bau_cost_simple.columns = ['Year', 'BAU_Total_Cost']
    
    mit_cost_simple = cost_df[['Year', 'Total_Cost']].copy()
    mit_cost_simple.columns = ['Year', 'Mitigation_Total_Cost']
    
    cost_comparison = bau_cost_simple.merge(mit_cost_simple, on='Year', how='outer')
    cost_comparison['Additional_Cost'] = (
        cost_comparison['Mitigation_Total_Cost'] - cost_comparison['BAU_Total_Cost']
    )
    
    # Merge emission and cost comparisons
    full_comparison = scenario_comparison.merge(cost_comparison, on='Year', how='outer')
    full_comparison['MAC_USD_tCO2e'] = np.where(
        full_comparison['Emission_Reduction_kt'] > 0,
        full_comparison['Additional_Cost'] / full_comparison['Emission_Reduction_kt'],
        np.nan
    )
    
    full_comparison.to_excel(writer, sheet_name="Scenario_Comparison", index=False)
 

print(f"Results saved to: {output_path}")

print("\n=== SHEETS CREATED (V5) ===")
print("  1. Production_by_Plant       - Plants as rows, years as columns")
print("  2. Production_by_Route       - Routes as rows, years as columns")
print("  3. Incremental_by_Route      - New capacity by route per year")
print("  4. Emissions                 - Emissions vs limits by year")
print("  5. Emissions_Detailed_Year   - Process vs Energy emissions (Hebeda)")
print("  6. Emissions_by_Route_Year   - Emissions by route and year")
print("  7. Emission_Factors_by_Route - Calculated EF (kg CO2e/t)")
print("  8. Cost_Breakdown            - CAPEX, OPEX, Fuel costs by year")
print("  9. Cost_by_Year              - Costs in wide format")
print(" 10. Energy_by_Route_ktep      - Energy consumption by route (ktep)")
print(" 11. Total_Energy_ktep         - Total energy consumption by year")
print(" 12. Production_Detail_Long    - Long format for analysis")
print(" 13. Total_Production          - Total production by year")
print(" 14. Fuel_Cost_Parameters      - Fuel costs by route")
print(" 15. Summary                   - Model parameters")
print(" 16. Input_Penetration_Limits")
print(" 17. Input_Technology_Params")

print("\n=== MODEL V17 RUN COMPLETE ===")

# #%%


# print("\n--- All routes with Carvao vegetal in ei_by_route_fuel ---")
# for (route, fuel), ei in ei_by_route_fuel.items():
#     if fuel == 'Carvao vegetal':
#         print(f"  {route}: {ei} GJ/t")
#   #%%      
# print("\n--- Charcoal budget check: what do existing routes already consume? ---")
# for year in [2023, 2030]:
#     charcoal_existing = 0
#     for plant in plant_names:
#         if 'candidate' in plant.lower():
#             continue
#         route = plant_to_route[plant]
#         prod = plant_attr[plant]['Capacity']  # usando capacidade como proxy
#         ei_cv = ei_by_route_fuel.get((route, 'Carvao vegetal'), 0)
#         charcoal_existing += prod * ei_cv
#         if ei_cv > 0:
#             print(f"  {route}: {prod:.0f} kt × {ei_cv} GJ/t = {prod*ei_cv:.0f} TJ")
#     print(f"  {year} | Existing charcoal = {charcoal_existing:.0f} TJ | "
#           f"Budget = {CHARCOAL_LIMIT_TJ:.0f} TJ | "
#           f"Remaining for SR = {CHARCOAL_LIMIT_TJ - charcoal_existing:.0f} TJ | "
#           f"Max SR = {(CHARCOAL_LIMIT_TJ - charcoal_existing)/22:.0f} kt")