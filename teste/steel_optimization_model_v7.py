# -*- coding: utf-8 -*-

#esta rodada, eu não permito entrar nada de mineral coal dali pra frente! O resultado leva a quedas mto grandes de emissão. 
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

# #==============================================================================
# # SECTION 7: CALCULATE FUEL COST PER TONNE BY ROUTE
# #==============================================================================

# print("\n=== CALCULATING FUEL COST PER TONNE BY ROUTE ===")

# # Fuel cost per tonne = sum(EI_fuel * price_fuel) for each fuel in route
# fuel_cost_per_tonne = {}

# for route_name, fuel_ei_dict in energy_intensity_by_route_fuel.items():
#     total_fuel_cost = 0
#     print(f"\n  {route_name}:")
    
#     for fuel, ei in fuel_ei_dict.items():
#         # Get price for this fuel
#         if fuel in fuel_prices.index:
#             price = fuel_prices.loc[fuel, 'BRL_per_GJ']
#             cost = ei * price
#             total_fuel_cost += cost
#             print(f"    {fuel}: {ei:.3f} GJ/t × {price:.2f} BRL/GJ = {cost:.2f} BRL/t")
#         else:
#             # Try to find matching fuel name
#             matching = [f for f in fuel_prices.index if fuel.lower() in f.lower() or f.lower() in fuel.lower()]
#             if matching:
#                 price = fuel_prices.loc[matching[0], 'BRL_per_GJ']
#                 cost = ei * price
#                 total_fuel_cost += cost
#                 print(f"    {fuel} (matched to {matching[0]}): {ei:.3f} GJ/t × {price:.2f} BRL/GJ = {cost:.2f} BRL/t")
#             else:
#                 print(f"    {fuel}: PRICE NOT FOUND - using 0")
    
#     fuel_cost_per_tonne[route_name] = total_fuel_cost
#     print(f"    TOTAL FUEL COST: {total_fuel_cost:.2f} BRL/t = {total_fuel_cost/DOLAR_TO_BRL:.2f} USD/t")

# # Add fuel costs for innovative routes (using literature values)
# # These routes don't have historical EI_BEU data
# print("\n  Adding fuel costs for innovative routes (estimated):")

# # DR-NG: Uses natural gas (~14.9 GJ/t) and electricity (~5 GJ/t)
# DR_NG_gas_ei = 14.9  # GJ/t natural gas
# DR_NG_elec_ei = 5.0  # GJ/t electricity
# DR_NG_fuel_cost = (DR_NG_gas_ei * fuel_prices.loc['Gas natural', 'BRL_per_GJ'] + 
#                    DR_NG_elec_ei * fuel_prices.loc['Eletricidade', 'BRL_per_GJ'])
# fuel_cost_per_tonne['DR-NG'] = DR_NG_fuel_cost
# print(f"    DR-NG: {DR_NG_fuel_cost:.2f} BRL/t (NG: {DR_NG_gas_ei} GJ/t, Elec: {DR_NG_elec_ei} GJ/t)")

# # DR-H2: Uses hydrogen (estimated ~50 GJ/t) and electricity (~6 GJ/t)
# # Note: Hydrogen price is estimated - not in fuel_prices file
# H2_PRICE_BRL_GJ = 30.0  # BRL/GJ - estimated, highly variable
# DR_H2_h2_ei = 14.2  # GJ/t hydrogen (from Zotin table)
# DR_H2_elec_ei = 6.0  # GJ/t electricity
# DR_H2_fuel_cost = (DR_H2_h2_ei * H2_PRICE_BRL_GJ + 
#                    DR_H2_elec_ei * fuel_prices.loc['Eletricidade', 'BRL_per_GJ'])
# fuel_cost_per_tonne['DR-H2'] = DR_H2_fuel_cost
# print(f"    DR-H2: {DR_H2_fuel_cost:.2f} BRL/t (H2: {DR_H2_h2_ei} GJ/t @ {H2_PRICE_BRL_GJ} BRL/GJ, Elec: {DR_H2_elec_ei} GJ/t)")

# # SR: Uses coal and electricity
# SR_coal_ei = 15.0  # GJ/t non-coking coal
# SR_elec_ei = 5.0  # GJ/t electricity
# SR_fuel_cost = (SR_coal_ei * fuel_prices.loc['Carvao metalurgico', 'BRL_per_GJ'] + 
#                 SR_elec_ei * fuel_prices.loc['Eletricidade', 'BRL_per_GJ'])
# fuel_cost_per_tonne['SR'] = SR_fuel_cost
# print(f"    SR: {SR_fuel_cost:.2f} BRL/t (Coal: {SR_coal_ei} GJ/t, Elec: {SR_elec_ei} GJ/t)")

# # BF-BOF-CCS: Similar to BF-BOF MC but with additional electricity for CCS
# # Assume 20% additional energy for CCS (mainly electricity)
# if 'BF-BOF MC' in fuel_cost_per_tonne:
#     CCS_additional_elec = 3.0  # GJ/t additional electricity for CCS
#     BFBOF_CCS_fuel_cost = (fuel_cost_per_tonne['BF-BOF MC'] + 
#                            CCS_additional_elec * fuel_prices.loc['Eletricidade', 'BRL_per_GJ'])
#     fuel_cost_per_tonne['BF-BOF-CCS'] = BFBOF_CCS_fuel_cost
#     print(f"    BF-BOF-CCS: {BFBOF_CCS_fuel_cost:.2f} BRL/t (BF-BOF MC + {CCS_additional_elec} GJ/t elec for CCS)")

# print("\n=== FUEL COST SUMMARY (BRL/t and USD/t) ===")
# for route, cost_brl in fuel_cost_per_tonne.items():
#     cost_usd = cost_brl / DOLAR_TO_BRL
#     print(f"  {route}: {cost_brl:.2f} BRL/t = {cost_usd:.2f} USD/t")

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
routes = ['BF-BOF CC', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS'] #notice that 'BF-BOF MC' is no longer an option

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

#==============================================================================
# SECTION 20: DEFINE EMISSION LIMITS
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

#%%

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
m.EmissionLimit = Param(m.Year, initialize=emission_limit_dict)

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
MINIMUM_UTILIZATION_EXISTING = 0.7  # 70% minimum utilization
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

# --- CONSTRAINT E: Emission limits (Hebeda 2024 methodology) ---
def emission_rule(m, year):
    """
    Total emissions must not exceed limit.
    
    Emission = Σ (Production × Emission_Factor_route) / 1000
    
    Where Emission_Factor_route = Σ (EI_fuel × EF_fuel) for all fuels
    Calculated in SECTION 3C using Hebeda (2024) methodology.
    
    Units: 
      Production: kt steel
      Emission_Factor: kg CO2e/t steel
      Result: kt CO2e (after dividing by 1000)
    """
    total_emissions = sum(
        m.production[plant, year] * measures_dict.get(plant_to_route[plant], {}).get('Emission_factor_kg_t', 0) / 1000
        for plant in m.Plant
        if plant_to_route[plant] in measures_dict
    )
    return total_emissions <= m.EmissionLimit[year]

m.TotalEmissions = Constraint(m.Year, rule=emission_rule)


# --- CONSTRAINT F: Charcoal (Carvao vegetal) supply limit ---
# Total charcoal consumption across ALL routes cannot exceed national availability.
# Source: Otto Hebeda (2024) — 576,812 TJ/year × 80% availability = 461,450 TJ/year
# Routes consuming charcoal (from EI_Route_Fuel_SIMPLIFIED.csv):
#   SR:         22.000 GJ/t
#   BF-BOF CC:   6.533 GJ/t
#   Guseiros:   17.610 GJ/t
# Unit check: production (kt) × EI (GJ/t) = TJ  [no conversion needed]

CHARCOAL_POTENTIAL_TJ = 576812
CHARCOAL_AVAILABILITY_FACTOR = 0.80
CHARCOAL_LIMIT_TJ = CHARCOAL_POTENTIAL_TJ * CHARCOAL_AVAILABILITY_FACTOR

CHARCOAL_ROUTES = ['SR', 'BF-BOF CC', 'Guseiros']

def charcoal_limit_rule(m, year):
    """Total charcoal consumption (TJ) <= national availability (TJ/yr)
    Unit: production (kt) × EI (GJ/t) = TJ
    """
    total_charcoal_TJ = sum(
        m.production[plant, year] * ei_by_route_fuel.get((plant_to_route[plant], 'Carvao vegetal'), 0)
        for plant in m.Plant
        if plant_to_route[plant] in CHARCOAL_ROUTES
    )
    return total_charcoal_TJ <= CHARCOAL_LIMIT_TJ

m.CharcoalLimit = Constraint(m.Year, rule=charcoal_limit_rule)
print(f"  Constraint F added: Charcoal limit = {CHARCOAL_LIMIT_TJ:,.0f} TJ/yr")


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

# #==============================================================================
# # SECTION 27: CALCULATE COSTS BY COMPONENT
# #==============================================================================

# print("\n=== CALCULATING COST BREAKDOWN ===")

# # Calculate costs by year and component
# cost_breakdown = []

# for year in m.Year:
#     year_capex = 0
#     year_opex = 0
#     year_fuel = 0
    
#     for plant in m.Plant:
#         tech = plant_to_route[plant]
#         prod = m.production[plant, year].value or 0
        
#         if tech in measures_dict:
#             capex = float(measures_dict[tech].get('CAPEX', 0) or 0)
#             opex = float(measures_dict[tech].get('OPEX', 0) or 0)
#             fuel_cost = float(measures_dict[tech].get('Fuel_cost_USD_t', 0) or 0)
            
#             # CAPEX in start year
#             if int(plant_attr[plant]['Startyear']) == int(year):
#                 year_capex += capex * plant_attr[plant]['Capacity'] * LEVELIZED_FACTOR
            
#             # OPEX and fuel costs based on production
#             year_opex += opex * prod
#             year_fuel += fuel_cost * prod
    
#     cost_breakdown.append({
#         'Year': year,
#         'CAPEX_levelized': year_capex,
#         'OPEX': year_opex,
#         'Fuel_Cost': year_fuel,
#         'Total_Cost': year_capex + year_opex + year_fuel
#     })

# cost_df = pd.DataFrame(cost_breakdown)

# print("\nCost Summary (selected years, million USD):")
# for year in [2023, 2030, 2040, 2050]:
#     if year in cost_df['Year'].values:
#         row = cost_df[cost_df['Year'] == year].iloc[0]
#         print(f"  {year}: CAPEX={row['CAPEX_levelized']/1e6:.1f}M, OPEX={row['OPEX']/1e6:.1f}M, "
#               f"Fuel={row['Fuel_Cost']/1e6:.1f}M, Total={row['Total_Cost']/1e6:.1f}M USD")

# # Create cost breakdown wide format
# cost_wide = cost_df.set_index('Year').T

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
        
        
        
        # if route in EI_by_route:
        #     ei = EI_by_route[route]
        # else:
        #     # Use estimated values for innovative routes (GJ/t)
        #     ei_estimates = {
        #         'DR-NG': 19.9,
        #         'DR-H2': 20.2,
        #         'SR': 19.4,
        #         'BF-BOF-CCS': 21.0
        #     }
        #     ei = ei_estimates.get(route, 0)
        
        # Energy consumption in ktep
        # prod (kt) = prod * 1000 (t)
        # EC (GJ) = prod * 1000 * ei
        # EC (tep) = EC (GJ) / 41.868 = prod * 1000 * ei / 41.868
        # EC (ktep) = EC (tep) / 1000 = prod * ei / 41.868
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

output_path = r"C:\Users\Bruna\OneDrive\DOUTORADO\0.TESE\modelagem\modelo_bru\teste\resultados\resultados_modelo_V7_2.xlsx"
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

print("\n=== MODEL V5 RUN COMPLETE ===")

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