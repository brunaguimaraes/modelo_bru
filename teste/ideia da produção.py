# -*- coding: utf-8 -*-
"""
Created on Fri Jul 18 11:13:28 2025

@author: Bruna
foco na produção
"""




import pandas as pd
import numpy as np


#%%
### inserindo dados históricos de produção

"""Importing Crude Steel production by route in kt"""

steel_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/steel_production_v2.csv') #in kt
steel_production = steel_production.set_index('Year')   
steel_production['Total']= steel_production.sum(axis=1)

"""Importing Pig Iron production by Route in kt"""
pig_iron_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Pig_iron_production_2.csv')
pig_iron_production = pig_iron_production.set_index('Ano')
pig_iron_production['Share BOF CC'] = pig_iron_production['Integrada CV']/(pig_iron_production['Integrada CV']+pig_iron_production['Integrada CM'])
pig_iron_production['Share BOF MC']=1-pig_iron_production['Share BOF CC']

"""Charcoal and coal in BF-BOF production"""
#BOF Coal production in Mt
steel_production['BOF MC'] = steel_production.BOF*pig_iron_production['Share BOF MC']

#BOF Charcoal production in Mt
steel_production['BOF CC'] = steel_production.BOF*pig_iron_production['Share BOF CC']

steel_production['Total']= steel_production['BOF']+steel_production['EAF'] #Removing EOF from the total
steel_production = steel_production.drop('EOF',axis= 'columns')

steel_production['Share_BOF_MC'] = steel_production['BOF MC']/steel_production['Total']
steel_production['Share_BOF_CC'] = steel_production['BOF CC']/steel_production['Total']
steel_production['Share_EAF'] = steel_production['EAF']/steel_production['Total']

"""Scrap supply"""
scrap_supply = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Scrap_supply.csv')
scrap_supply = scrap_supply.set_index('Recovery_rate')

"""Importing Emission Factor"""
emission_factor = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/emission_factor.csv') #t/TJ or kg/GJ
emission_factor = emission_factor.set_index('Combustivel')
emission_factor['CO2e'] = emission_factor['CO2'] + emission_factor['CH4']*28 + emission_factor['N2O']*265




#%%
"""2. Historic Data"""

#Years from the historic data
past_years = np.linspace(2005,2020,2020-2005+1,dtype = int)

#Future years:
future_years = np.linspace(2021,2050,30,dtype = int)

#Base year (reference year for the projections)
base_year = 2023

#%%#%%
"""Steel production Projection"""

for year in np.linspace(2024,2050,2050-2024+1).astype(int):
    steel_production.loc[year] =np.full([len(steel_production.columns)],np.nan)
    pig_iron_production.loc[year] = np.full([len(pig_iron_production.columns)],np.nan)

Production_increase = {
        2025:1.037,
        2030:1.146,
        2035:1.306,
        2040:1.486,
        2045:1.699,
        2050:1.961,
        }

colunas = ['BOF','EAF',"Total","BOF MC","BOF CC"]
#Production route share will be equal to the values for the base year
for coluna in colunas:
    for ano in [2025, 2030, 2035, 2040, 2045, 2050]:
        steel_production.loc[ano, coluna] = float(steel_production.loc[base_year, coluna] * Production_increase[ano])

colunas = ['Integrada CM','Integrada CV','Independente CV']    
for coluna in colunas:
    for ano in [2025, 2030, 2035, 2040, 2045, 2050]:
        pig_iron_production.loc[ano, coluna] = float(pig_iron_production.loc[base_year, coluna] * Production_increase[ano])
    
steel_production.loc[2050, 'Share_BOF_MC'] = steel_production.loc[base_year, 'Share_BOF_MC']
steel_production.loc[2050, 'Share_BOF_CC'] = steel_production.loc[base_year, 'Share_BOF_CC']
steel_production.loc[2050, 'Share_EAF'] = steel_production.loc[base_year, 'Share_EAF']
pig_iron_production.loc[2050, 'Share BOF CC'] = pig_iron_production.loc[base_year, 'Share BOF CC']
pig_iron_production.loc[2050, 'Share BOF MC'] = pig_iron_production.loc[base_year, 'Share BOF MC']

steel_production = steel_production.interpolate()
pig_iron_production= pig_iron_production.interpolate()

# Garante que os anos estão na ordem certa
steel_production = steel_production.sort_index()
pig_iron_production = pig_iron_production.sort_index()


#%%#%%
# ===== Integrando vida útil de plantas ao modelo de otimização =====

# Carregar dados de plantas existentes (arquivo Excel com colunas: plant_id, route, capacity, remaining_life)
plants = pd.read_excel('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/teste/plants_teste.xlsx')  

# List of years to analyze
years = list(range(2023, 2051))

# Create a DataFrame to hold annual production per plant, indexed by year
plant_production = pd.DataFrame(index=years)

# Build annual production for each plant based on its lifetime
for _, row in plants.iterrows():
    production = []
    for year in years:
        # Use exact column names from Excel
        if row['Startyear'] <= year <= row['Retrofitdate']:
            production.append(row['Capacity'])
        else:
            production.append(0.0)
    plant_production[row['Plantname']] = production

# Assume steel_production['Total'] is already loaded and interpolated
production_target = steel_production['Total']
new_id = 1

# Prepare to collect new plants' production columns in a dict
new_plants_columns = {}

for year in years:
    total_production = plant_production.loc[year].sum()
    demand = production_target.loc[year]

    while total_production < demand:
        new_name = f'New_{year}_{new_id}'
        default_capacity = 2.0
        lifetime = 30
        end_year = min(year + lifetime, 2050)

        # Create production list for this new plant
        new_column = []
        for y in years:
            if year <= y <= end_year:
                new_column.append(default_capacity)
            else:
                new_column.append(0.0)
        
        # Store the new column temporarily (do NOT assign to plant_production yet)
        new_plants_columns[new_name] = new_column

        # Append new plant info to plants DataFrame (outside of loop ideally)
        plants = pd.concat([
            plants,
            pd.DataFrame([{
                'Plantname': new_name,
                'Route': 'R1',  # or 'R2'
                'Startyear': year,
                'Retrofitdate': end_year,
                'Capacity': default_capacity,
                'Lat': None,
                'Lon': None,
                'Coordinates': None
            }])
        ], ignore_index=True)

        total_production += default_capacity
        new_id += 1

# Once all new columns are created, concatenate at once:
if new_plants_columns:
    new_cols_df = pd.DataFrame(new_plants_columns, index=years)
    plant_production = pd.concat([plant_production, new_cols_df], axis=1)


#%%

#Build the plant_production DataFrame from the Excel data
years = list(range(2023, 2051))
plant_production = pd.DataFrame(index=years)

for _, row in plants.iterrows():
    production = []
    for year in years:
        if row['Startyear'] <= year <= row['Retrofityear']:
            production.append(row['capacity'])
        else:
            production.append(0.0)
    plant_production[row['plantname']] = production
    
    
#Add new plants dynamically if demand is not met
    
    production_target = steel_production['Total']
new_id = 1

for year in years:
    total_production = plant_production.loc[year].sum()
    demand = production_target.loc[year]

    while total_production < demand:
        new_name = f'New_{year}_{new_id}'
        default_capacity = 2.0
        lifetime = 30
        end_year = min(year + lifetime, 2050)

        # Add new column to plant_production
        new_column = []
        for y in years:
            if year <= y <= end_year:
                new_column.append(default_capacity)
            else:
                new_column.append(0.0)
        plant_production[new_name] = new_column

        # Optionally, append the new plant to your 'plants' DataFrame
        plants = pd.concat([
            plants,
            pd.DataFrame([{
                'plantname': new_name,
                'route': 'R1',  # or 'R2' if you want to alternate
                'startyear': year,
                'retrofityear': end_year,
                'capacity': default_capacity,
                'lat': None,
                'lon': None
            }])
        ], ignore_index=True)

        total_production += default_capacity
        new_id += 1



# Allocate production from existing plants
plant_production = pd.DataFrame(index=range(2023, 2051))  # or use your 'years' list

for plant_name, plant_info in plants.items():
    annual_production = []
    for year in plant_production.index:
        if plant_info['start_year'] <= year <= plant_info['retrofit_year']:
            annual_production.append(plant_info['capacity'])
        else:
            annual_production.append(0.0)
    plant_production[plant_name] = annual_production

# Check total production vs. demand
production_target = steel_production['Total']  # already interpolated

new_id = 1
for year in plant_production.index:
    total_production = plant_production.loc[year].sum()
    demand = production_target.loc[year]
    
    while total_production < demand:
        new_plant_name = f"New_{year}_{new_id}"
        default_capacity = 2.0
        lifetime = 30
        end_year = min(year + lifetime, 2050)

        # Add new plant to plant dictionary
        plants[new_plant_name] = {
            'start_year': year,
            'retrofit_year': end_year,
            'capacity': default_capacity
        }

        # Fill production DataFrame for new plant
        for y in range(year, end_year + 1):
            if new_plant_name not in plant_production.columns:
                plant_production[new_plant_name] = 0.0
            plant_production.loc[y, new_plant_name] += default_capacity

        total_production += default_capacity
        new_id += 1




#%%#%%


#Alocar produção de plantas existentes
for nome, dados in plants.items():
    production_year = []
    for year in year:
        if dados['Entrada'] <= year <= dados['Retrofitdate']:
            producao_ano.append(dados['Capacity'])
        else:
            producao_ano.append(0.0)
    producao_por_planta[nome] = producao_ano

#Verificar produção total vs. demanda
demanda_ano = steel_production['Total']  # ou soma de colunas de rotas, dependendo da estrutura

nova_id = 1
for ano in anos:
    producao_total = producao_por_planta.loc[ano].sum()
    demanda = demanda_ano.loc[ano]
    
    while producao_total < demanda:
        nome_planta = f'Nova_{ano}_{nova_id}'
        capacidade_nova = 2.0  # definir padrão ou função
        vida_util = 30

        # Adiciona a nova planta
        plantas_existentes[nome_planta] = {
            'entrada': ano,
            'fim': min(ano + vida_util, 2050),
            'capacidade': capacidade_nova
        }
        
        # Atualiza DataFrame de produção
        for a in range(ano, plantas_existentes[nome_planta]['fim'] + 1):
            if nome_planta not in producao_por_planta.columns:
                producao_por_planta[nome_planta] = 0.0
            producao_por_planta.loc[a, nome_planta] += capacidade_nova
        
        producao_total += capacidade_nova
        nova_id += 1



#%%
"""2. Historic Data - energy consumption"""

# Anos do histórico
past_years = np.linspace(2005, 2023, 2023-2005+1, dtype=int)


#Energy Consumption in the Steel Production in the National Energy Balance (BEN)
 
# Energy_consumption_BEN = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/CE_Siderurgia.csv') #importing BEN_Steel
Energy_consumption_BEN = pd.read_excel("C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/CE_Siderurgia_novo_2.xlsx") #importing BEN_Steel 2025 (DADOS ATE 2024)
Energy_consumption_BEN = Energy_consumption_BEN.fillna(0) #filling NA with 0
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES':'Carvao mineral'},'Carvao metalurgico') #changing Outras primarias para outras secundarias
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES':'Gas de coqueria'},'Gas cidade') #changing Outras primarias para outras secundarias
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES':'Alcatrao'},'Outras fontes secundarias') #changing Outras primarias para outras secundarias
Energy_consumption_BEN = Energy_consumption_BEN.set_index('FONTES') #Changin index for Sources
Energy_consumption_BEN.index = Energy_consumption_BEN.index.str.capitalize() #Change all UPPER to Capitalize
Energy_consumption_BEN.columns = Energy_consumption_BEN.columns.astype(int) #Changing the columns type: from str to int

#nao fiz issooooooooo - Summing Biodeisel with Diesel to adjust the nomenclature:
#Energy_consumption_BEN.loc['Oleo diesel'] = Energy_consumption_BEN.loc['Biodiesel']+Energy_consumption_BEN.loc['Oleo diesel']
#Energy_consumption_BEN = Energy_consumption_BEN.drop(index = ['Biodiesel'])
Energy_consumption_BEN = Energy_consumption_BEN.rename(index = {'Glp': 'GLP'}) #fixing name
Energy_consumption_BEN = Energy_consumption_BEN .sort_index() #ordering the rows by fuel name
#Converting to Gj:
ktoe_to_tj = 41.868
Energy_consumption_BEN_Gj = Energy_consumption_BEN*ktoe_to_tj 
#

#%%#%%
"""Steel production Projection"""

for year in np.linspace(2024,2050,2050-2024+1).astype(int):
    steel_production.loc[year] =np.full([len(steel_production.columns)],np.nan)
    pig_iron_production.loc[year] = np.full([len(pig_iron_production.columns)],np.nan)

Production_increase = {
        2025:1.037,
        2030:1.146,
        2035:1.306,
        2040:1.486,
        2045:1.699,
        2050:1.961,
        }

colunas = ['BOF','EAF',"Total","BOF MC","BOF CC"]
#Production route share will be equal to the values for the base year
for coluna in colunas:
    for ano in [2025, 2030, 2035, 2040, 2045, 2050]:
        steel_production.loc[ano, coluna] = float(steel_production.loc[base_year, coluna] * Production_increase[ano])

colunas = ['Integrada CM','Integrada CV','Independente CV']    
for coluna in colunas:
    for ano in [2025, 2030, 2035, 2040, 2045, 2050]:
        pig_iron_production.loc[ano, coluna] = float(pig_iron_production.loc[base_year, coluna] * Production_increase[ano])
    
steel_production.loc[2050, 'Share_BOF_MC'] = steel_production.loc[base_year, 'Share_BOF_MC']
steel_production.loc[2050, 'Share_BOF_CC'] = steel_production.loc[base_year, 'Share_BOF_CC']
steel_production.loc[2050, 'Share_EAF'] = steel_production.loc[base_year, 'Share_EAF']
pig_iron_production.loc[2050, 'Share BOF CC'] = pig_iron_production.loc[base_year, 'Share BOF CC']
pig_iron_production.loc[2050, 'Share BOF MC'] = pig_iron_production.loc[base_year, 'Share BOF MC']

steel_production = steel_production.interpolate()
pig_iron_production= pig_iron_production.interpolate()


#%%#%%
"""Steel production Projection"""


