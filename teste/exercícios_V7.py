# -*- coding: utf-8 -*-
"""
Created on Fri Jul 25 16:52:07 2025

@author: Bruna


dEPOIS TENHO QUE IR NA PLANILHA "PENETRATION INOVATIVE.CSV" E alterar a penetração dos BF-BOFS tradicionais 

"""

#%% 1 importar bibliotecas

import pandas as pd
import numpy as np
from pyomo.environ import (
    ConcreteModel, Set, Var, Param, Constraint, Objective, NonNegativeReals,
    Expression, minimize
) #ao importar o pyomo de forma simples estava dando erro, assim o erro foi resolvido
from amplpy import modules
#%% 2 importar dados

# Carregar dados de plantas existentes (arquivo Excel com colunas: plant_id, route, capacity, remaining_life)
plants=pd.read_excel('Plants_teste_chris.xlsx')


tecnologias=pd.read_csv('Tecnologias.csv',sep=";")

#Agora o meu dataframe utiliza a rota como índice para identificar cada uma das linhas de tecnologia
tecnologias.set_index('Route', inplace=True)

#%% 3 inserindo mais dados históricos de produção

### inserindo mais dados históricos de produção conforme modelagem do Otto

"""Importing Crude Steel production by route in kt"""
steel_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/steel_production.csv') #in kt
steel_production = steel_production.set_index('Year')   
steel_production['Total']= steel_production.sum(axis=1)

"""Importing Pig Iron production by Route in kt"""
pig_iron_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Pig_iron_production_2.csv')
pig_iron_production = pig_iron_production.set_index('Ano')
pig_iron_production['Share BF-BOF CC'] = pig_iron_production['Integrada CV']/(pig_iron_production['Integrada CV']+pig_iron_production['Integrada CM'])
pig_iron_production['Share BF-BOF MC']=1-pig_iron_production['Share BF-BOF CC']

"""Charcoal and coal in BF-BOF production"""
#BOF Coal production in Mt
steel_production['BF-BOF MC'] = steel_production.BOF*pig_iron_production['Share BF-BOF MC']

#BOF Charcoal production in Mt
steel_production['BF-BOF CC'] = steel_production.BOF*pig_iron_production['Share BF-BOF CC']

steel_production['Total']= steel_production['BOF']+steel_production['EAF'] #Removing EOF from the total
steel_production = steel_production.drop('EOF',axis= 'columns')

steel_production['Share_BOF_MC'] = steel_production['BF-BOF MC']/steel_production['Total']
steel_production['Share_BOF_CC'] = steel_production['BF-BOF CC']/steel_production['Total']
steel_production['Share_EAF'] = steel_production['EAF']/steel_production['Total']

"""Scrap supply"""
scrap_supply = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Scrap_supply.csv')
scrap_supply = scrap_supply.set_index('Recovery_rate')

"""Importing Emission Factor"""
emission_factor = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/emission_factor.csv') #t/TJ or kg/GJ
emission_factor = emission_factor.set_index('Combustivel')
emission_factor['CO2e'] = emission_factor['CO2'] + emission_factor['CH4']*28 + emission_factor['N2O']*265


"""Importing Energy Consumption compatible with the Useful Energy Balance (BEU):
    In the META report they already separeted the Final Energy Consumption in the same nomenclature as the BEU
    """
EI_BEU = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/teste/EI_Route_Step_year_novo3.csv', sep=';') #minha intensidade energetica por rota e combustivel, sem considerar as etapas
EI_BEU =EI_BEU.fillna(0)

#dropping null values: Lenha, Produtos da cana, Gasolina, Querosene, Alcatrao, Alcool etilico

EI_BEU = EI_BEU[EI_BEU.Combustivel != 'Lenha']
EI_BEU = EI_BEU[EI_BEU.Combustivel != 'Produtos da cana']
EI_BEU = EI_BEU[EI_BEU.Combustivel != 'Gasolina']
EI_BEU = EI_BEU[EI_BEU.Combustivel != 'Querosene']
EI_BEU = EI_BEU[EI_BEU.Combustivel != 'Alcatrao']
EI_BEU = EI_BEU[EI_BEU.Combustivel != 'Alcool etilico']
EI_BEU = EI_BEU[EI_BEU.Combustivel != 'Outras fontes secundarias'] 

EI_BEU = EI_BEU.replace({'Combustivel':'Gases cidade'},'Gas cidade') #changing Gases cidade for Gas Cidade
EI_BEU = EI_BEU.replace({'Combustivel':'Outras fontes primarias'},'Outras fontes secundarias') #changing Outras primarias para outras secundarias

#%% ajustando histórico por planta




plants['Startyear'] = plants['Startyear'].astype(int)
plants['Retrofitdate'] = plants['Retrofitdate'].astype(int)
plants['Capacity'] = plants['Capacity'].astype(float)

base_year = 2023

plants_base = plants[
    (plants['Startyear'] <= base_year) &
    (plants['Retrofitdate'] >= base_year)
].copy()

plants_base = plants[
    (plants['Startyear'] <= base_year) &
    (plants['Retrofitdate'] >= base_year)
].copy()

production_by_route = (
    steel_production
    .loc[base_year]
    .drop('Total')
)

capacity_by_route = (
    plants_base
    .groupby('Route')['Capacity']
    .sum()
)

utilization = production_by_route / capacity_by_route

print(utilization)


plants_base['Utilization'] = plants_base['Route'].map(utilization)

plants_base['Production_2023'] = (
    plants_base['Capacity'] * plants_base['Utilization']
)

#%% check: valores devem bater

check = (
    plants_base
    .groupby('Route')['Production_2023']
    .sum()
)

print(check)
print(production_by_route)


#%% SEPARANDO BOF

bof_plants = plants_base[plants_base['Route'] == 'BOF'].copy()

target_mc = steel_production.loc[base_year, 'BF-BOF MC']
target_cc = steel_production.loc[base_year, 'BF-BOF CC']

bof_plants = bof_plants.sort_values('Production_2023', ascending=False)

bof_plants['BOF_type'] = None
cum_mc = 0

for idx, row in bof_plants.iterrows():
    if cum_mc < target_mc:
        bof_plants.loc[idx, 'BOF_type'] = 'BF-BOF MC'
        cum_mc += row['Production_2023']
    else:
        bof_plants.loc[idx, 'BOF_type'] = 'BF-BOF CC'

#%% check: valores BOF

check = bof_plants.groupby('BOF_type')['Production_2023'].sum()
print(check)


#%% UNIFICANDO

bof_final = bof_plants.copy()

bof_final['Final_route'] = bof_final['BOF_type']
bof_final['Production_2023_final'] = bof_final['Production_2023']

bof_final = bof_final[[
    'Plantname',
    'Final_route',
    'Capacity',
    'Production_2023_final',
    'Startyear',
    'Retrofitdate'
]]


eaf_final = plants_base[plants_base['Route'] == 'EAF'].copy()

eaf_final['Final_route'] = 'EAF'
eaf_final['Production_2023_final'] = eaf_final['Production_2023']

eaf_final = eaf_final[[
    'Plantname',
    'Final_route',
    'Capacity',
    'Production_2023_final',
    'Startyear',
    'Retrofitdate'
]]

plants_unified = pd.concat(
    [bof_final, eaf_final],
    ignore_index=True
)

#%%check
check = (
    plants_unified
    .groupby('Final_route')['Production_2023_final']
    .sum()
)

print(check)

steel_production.loc[2023, ['BF-BOF MC', 'BF-BOF CC', 'EAF']]


#%%ajustando e criando planta marginal

target_cc = steel_production.loc[2023, 'BF-BOF CC']

current_cc = (
    bof_plants[bof_plants['BOF_type'] == 'BF-BOF CC']['Production_2023']
    .sum()
)

missing_cc = target_cc - current_cc

print(missing_cc)
    
new_cc_plant = {
    'Plantname': 'BF-BOF_CC_virtual_2023',
    'Route': 'BOF',
    'BOF_type': 'BF-BOF CC',
    'Capacity': missing_cc,          # assumindo utilização = 1
    'Utilization': 1.0,
    'Production_2023': missing_cc,
    'Startyear': 2023,                # ou 2023, depende da sua lógica
    'Retrofitdate': 2040,
    'Energy_intensity': np.nan,
    'Emission_intensity': np.nan
}

bof_plants = pd.concat(
    [bof_plants, pd.DataFrame([new_cc_plant])],
    ignore_index=True
)
#%%
check = (
    bof_plants
    .groupby('BOF_type')['Production_2023']
    .sum()
)

print(check)
print(steel_production.loc[2023, ['BF-BOF MC', 'BF-BOF CC']])



#%% UNIFICANDO NOVAMENTE

bof_final = bof_plants.copy()

bof_final['Final_route'] = bof_final['BOF_type']
bof_final['Production_2023_final'] = bof_final['Production_2023']

bof_final = bof_final[[
    'Plantname',
    'Final_route',
    'Capacity',
    'Production_2023_final',
    'Startyear',
    'Retrofitdate'
]]


eaf_final = plants_base[plants_base['Route'] == 'EAF'].copy()

eaf_final['Final_route'] = 'EAF'
eaf_final['Production_2023_final'] = eaf_final['Production_2023']

eaf_final = eaf_final[[
    'Plantname',
    'Final_route',
    'Capacity',
    'Production_2023_final',
    'Startyear',
    'Retrofitdate'
]]

plants_unified = pd.concat(
    [bof_final, eaf_final],
    ignore_index=True
)


#%%check FINAL
check = (
    plants_unified
    .groupby('Final_route')['Production_2023_final']
    .sum()
)

print(check)

steel_production.loc[2023, ['BF-BOF MC', 'BF-BOF CC', 'EAF']]

#%% 4 projetar produção alvo

#criando um dataframe do alvo de produção
steel_total_target = steel_production[['Total']].copy()
steel_total_target.index.name = 'Year'  # só para garantir

#Adicionando anos até 2050 como NaN, se não existirem
for year in range(2024, 2051):
    if year not in steel_total_target.index:
        steel_total_target.loc[year] = [np.nan]
steel_total_target.sort_index(inplace=True)

#Aplicando os fatores apenas nos anos-alvo
Production_increase = {
    2025: 1.037,
    2030: 1.146,
    2035: 1.306,
    2040: 1.486,
    2045: 1.699,
    2050: 1.961,
}

# Usando a produção de 2023 como base
valor_base = steel_total_target.loc[2023, 'Total']

# Preenche os anos-chave (multiplicados)
for ano, fator in Production_increase.items():
    steel_total_target.loc[ano, 'Total'] = valor_base * fator

#Interpola os anos entre os anos-alvo
steel_total_target['Total'] = steel_total_target['Total'].interpolate()



#%% 5. otimização

#todo ano checa se a produção alvo é atendida
#se não for atendida, escolhe nova tecnologia tal que reduz o custo total da produção

# Ano base do script
current_year = 2023
# Horizon decenal:
future_years = list(range(current_year+1, 2051))  # 2023 a 2050 - future_years é simplesmente uma lista Python dos anos seguintes em que seu modelo vai instalar plantas, produzir e mitigar emissões.
routes = ['BF-BOF', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']

# Calcular capacidade existente de cada rota em cada ano, considerando vida útil restante
production_exist = {p: {t: 0.0 for t in future_years} for p in routes}
for _, row in plants.iterrows():
    p = row['Route']
    cap = float(row['Capacity'])
    retire_year = float(row['Retrofitdate'])
    for t in future_years:
        if t <= retire_year:
            production_exist[p][t] += cap

# Calcular a capacidade existente total, equivalent à produção total somando todas as tecnologias:
production_exist_total = {t: sum(production_exist[p][t] for p in routes) for t in future_years}    
    
#%% carregando restrições

# Parâmetros:
# penetration_dict
# production_dict / m.ProductionTarget
# measures_dict
# capacity_exist
# m.EmissionLimit


# Carregar restrições de penetração (quanto pode instalar de cada tecnologia por ano)
penetration_inovative = pd.read_csv('Penetration_innovative.csv')  # Ex: colunas 'Technology', '2023', '2024',...
penetration_inovative = penetration_inovative.set_index('Technology')

# converter nomes das colunas para inteiros (evita mismatch string/int)
penetration_inovative.columns = penetration_inovative.columns.astype(int)

#Ligando aos conjuntos do modelo Pyomo
#  Conjuntos:
techs = list(penetration_inovative.index)
years = [int(y) for y in penetration_inovative.columns]
steel_total_target.index = steel_total_target.index.astype(int)  # Garante que os anos são inteiros

m = ConcreteModel()
m.Year = Set(initialize=years, ordered=True)
m.Tech = Set(initialize=techs)



# 2. Variáveis de decisão:
m.production_expansion = Var(m.Tech, m.Year, domain=NonNegativeReals)    # [capacidade instalada nova = adicional]

m.production = Var(m.Tech, m.Year, domain=NonNegativeReals)            # [produção realizada total]

#
# Restrição: definição do productiontarget
# Isso cria um dicionário {(tech, ano): valor_max, ...}
production_dict = {y: v for y, v in steel_total_target['Total'].to_dict().items() if y in years}
m.ProductionTarget = Param(m.Year, initialize=production_dict)


#CUMPRIMENTO DO HISTÓRICO
historical_routes = ['BF-BOF MC', 'BF-BOF CC', 'EAF']

def historical_production_rule(m, tech, year):
    if year <= current_year:
        if tech in historical_routes:
            # usa o dado oficial histórico
            return m.production[tech, year] == steel_production.loc[year, tech]
        else:
            # tecnologias que NÃO existiam no histórico
            return m.production[tech, year] == 0
    return Constraint.Skip
m.HistoricalProduction = Constraint(
    m.Tech, m.Year,
    rule=historical_production_rule
)


# Capacidade acumulada:
def total_production(m, tech, year):
    return production_exist.get(tech, {}).get(year, 0) + \
        sum(m.production_expansion[tech, y] for y in m.Year if y <= year)
m.TotalProduction = Expression(m.Tech, m.Year, rule=total_production)


#essa restrição faz Produção por Tecnologia = histórico + produção incremental acumulada
def production_balance_rule(m, tech, year):
    return m.production[tech, year] == m.TotalProduction[tech, year]
m.ProductionBalance = Constraint(m.Tech, m.Year, rule=production_balance_rule)

  
# Restrição: expansão limitada pela penetração máxima da tecnologia     """Expansão só pode atender até a fração definida da produção alvo anual"""
penetration_dict = {(tech, int(year)): float(val)
                    for (tech, year), val in penetration_inovative.stack().to_dict().items()}

# def penetration_rule_production(m, tech, year):
#     return m.production[tech, year] <= penetration_dict.get((tech, year), 0.0) * m.ProductionTarget[year]
# m.PenetrationLimitProduction = Constraint(m.Tech, m.Year, rule=penetration_rule_production)


def penetration_rule_expansion(m, tech, year):
    return (
        m.production_expansion[tech, year]
        <= penetration_dict.get((tech, year), 0.0) * m.ProductionTarget[year]
    )
m.PenetrationLimitExpansion = Constraint(m.Tech, m.Year, rule=penetration_rule_expansion)


def production_constraint(m, year):
    if year <= current_year:
        return Constraint.Skip
    return sum(m.production[tech, year] for tech in m.Tech) >= m.ProductionTarget[year]
m.ProductionConstraint = Constraint(m.Year, rule=production_constraint)


# # Restrição: a produção do meu modelo tem que ser igual ou menor à capacidade instalada de cada ano até 2050
# def capacity_constraint(m, tech, year):
#     return m.production[tech, year] <= m.TotalCapacity[tech, year]
# m.CapacityLimit = Constraint(m.Tech, m.Year, rule=capacity_constraint)


"""Medidas de mitigação/tecnologias disponíveis para a escolha do modelo"""

measures_dict = tecnologias.T.to_dict()


"""Nível de emissão alvo"""

# === Limites de emissões GWP-AR5 (kt CO2 eq) ===
#emission_2020 = 57016
#emission_2050 = 70000  # sua meta ESCOLHER!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

emission_2020 = 158000000000000000000
emission_2050 = 20000000000000000000000000


year_start, year_end = 2020, 2050

emission_limit_dict = {
    y: emission_2020 + (emission_2050 - emission_2020) * (y - year_start) / (year_end - year_start)
    for y in years
}

m.EmissionLimit = Param(m.Year, initialize=emission_limit_dict)

"""Otimização das emissões"""

def emission_rule(m, year):
    return sum(measures_dict[tech]['Emission_intensity'] * m.production[tech, year] for tech in m.Tech) <= m.EmissionLimit[year]
m.TotalEmissions = Constraint(m.Year, rule=emission_rule)

# 6. Função objetivo:
def obj_rule(m):
    return \
        sum(measures_dict[tech]['CAPEX'] * m.production_expansion[tech, year]
            for tech in m.Tech for year in m.Year) + \
        sum(measures_dict[tech]['OPEX'] * m.production[tech, year]
            for tech in m.Tech for year in m.Year)
m.Objective = Objective(rule=obj_rule, sense=minimize)

      #%% BLOCO DE DEBUG!!!!
      
for year in years:
    print(f"\nAno {year}")
    for tech in m.Tech:
        cap = production_exist.get(tech, {}).get(year, 0)
        pen = penetration_dict.get((tech, year), 0)
        max_allowed = pen * steel_total_target.loc[year, 'Total']
        if cap > max_allowed + 1e-6:
            print(f"VIOLAÇÃO: {tech} cap={cap:.2f} > pen*target={max_allowed:.2f}")      
      
        #%% BLOCO DE DEBUG!!!!
      
      
""" 7. debug"""
import numpy as np

print("\n---- CHECANDO ProductionTarget ----")
for y in m.Year:
    try:
        v = float(m.ProductionTarget[y])
        if np.isnan(v) or np.isinf(v):
            print(f"ProductionTarget inválido para {y}: {v}")
    except Exception as e:
        print(f"(Exception) ProductionTarget[{y}]: {e}")

print("\n---- CHECANDO EmissionLimit ----")
for y in m.Year:
    try:
        v = float(m.EmissionLimit[y])
        if np.isnan(v) or np.isinf(v):
            print(f"EmissionLimit inválido para {y}: {v}")
    except Exception as e:
        print(f"(Exception) EmissionLimit[{y}]: {e}")

print("\n---- CHECANDO penetration_dict ----")
for key, v in penetration_dict.items():
    if np.isnan(v) or np.isinf(v):
        print(f"penetration_dict inválido para {key}: {v}")

print("\n---- CHECANDO capacidade_existente (production_exist, SE USADO) ----")
if 'production_exist' in globals():
    for tech in m.Tech:
        for year in m.Year:
            v = production_exist.get(tech, {}).get(year, 0)
            try:
                v = float(v)
                if np.isnan(v) or np.isinf(v):
                    print(f"production_exist inválido para {(tech, year)}: {v}")
            except Exception as e:
                print(f"(Exception) production_exist[{tech}, {year}]: {e}")

print("\n---- CHECANDO Emission_intensity das tecnologias ----")
for tech in m.Tech:
    try:
        emiss = measures_dict[tech]['Emission_intensity']
        if isinstance(emiss, str):
            emiss = float(emiss.replace(',','.'))
        if np.isnan(emiss) or np.isinf(emiss):
            print(f"Emission_intensity inválido para {tech}: {emiss}")
    except Exception as e:
        print(f"(Exception) Emission_intensity[{tech}]: {e}")

print("\n---- CHECANDO CAPEX das tecnologias ----")
for tech in m.Tech:
    try:
        capex = measures_dict[tech]['CAPEX']
        if isinstance(capex, str):
            capex = float(capex.replace(',','.'))
        if np.isnan(capex) or np.isinf(capex):
            print(f"CAPEX inválido para {tech}: {capex}")
    except Exception as e:
        print(f"(Exception) CAPEX[{tech}]: {e}")

print("\n---- CHECANDO OPEX das tecnologias ----")
for tech in m.Tech:
    try:
        opex = measures_dict[tech]['OPEX']
        if isinstance(opex, str):
            opex = float(opex.replace(',','.'))
        if np.isnan(opex) or np.isinf(opex):
            print(f"OPEX inválido para {tech}: {opex}")
    except Exception as e:
        print(f"(Exception) OPEX[{tech}]: {e}")

print("\n==== FIM DAS CHECAGENS DE INPUT ====\n")
      


# Verifique para CADA ANO se a soma das penetrações dá >= 1
for year in years:
    total_penetration = penetration_inovative[year].sum()
    print(f"Ano {year}: penetração total = {total_penetration}")

(penetration_inovative.sum(axis=0) < 1).any()
# True => tem algum ano com penetração insuficiente


#%% Extrair e visualizar os resultados da otimização


from pyomo.opt import SolverFactory

solver_name = "ipopt"  # "highs", "cbc",  "couenne", "bonmin", "ipopt", "scip", or "gcg".
solver = SolverFactory(solver_name+"nl", executable=modules.find(solver_name), solve_io="nl")
    
result_solver = solver.solve(m, tee = True)


#Colocar resultados em DataFrame 

# Capacidade adicionada
incremental_production_df = pd.DataFrame([
    {"Technology": tech, "Year": year, "Production_Expansion": m.production_expansion[tech, year].value}
    for tech in m.Tech for year in m.Year
])

# Produção por tecnologia
production_df = pd.DataFrame([
    {"Technology": tech, "Year": year, "Production": m.production[tech, year].value}
    for tech in m.Tech for year in m.Year
])

# Produção total agrupada (independente da tecnologia)
production_total_df = (
    production_df
    .groupby("Year", as_index=False)["Production"]
    .sum()
)
production_total_df.rename(columns={"Production": "Total_Production"}, inplace=True)

# # Capacidade total (Expression)
# total_capacity_df = pd.DataFrame([
#     {"Technology": tech, "Year": year, "Total_Capacity": m.TotalCapacity[tech, year]()}
#     for tech in m.Tech for year in m.Year
# ])




# você pode até plotar:

import matplotlib.pyplot as plt

for tech in incremental_production_df["Technology"].unique():
    subset = incremental_production_df[incremental_production_df["Technology"] == tech]
    plt.plot(subset["Year"], subset["Production_Expansion"], label=tech)

plt.title("Expansão de capacidade por tecnologia")
plt.xlabel("Ano")
plt.ylabel("Capacidade adicionada")
plt.legend()
plt.show()

# print("Custo total ótimo:", m.Objective())



# ver as emissões efetivas resultantes (para comparar com o limite):

emissions = {
    year: sum(measures_dict[tech]['Emission_intensity'] * m.production[tech, year].value for tech in m.Tech)
    for year in m.Year
}

emissions_df = pd.DataFrame(list(emissions.items()), columns=["Year", "Emissions"])
# print(emissions_df)


#%% exportar os resultados para Excel 

# exportar os resultados para Excel 

import os

# Defina o caminho absoluto do arquivo
output_path = r"C:\Users\Bruna\OneDrive\DOUTORADO\0.TESE\modelagem\modelo_bru\teste\resultados\resultados_modelo_V12.xlsx"
os.makedirs(os.path.dirname(output_path), exist_ok=True)


# Salva o Excel no local desejado
with pd.ExcelWriter(output_path) as writer:
    incremental_production_df.to_excel(writer, sheet_name="Produção Incremental")
    production_df.to_excel(writer, sheet_name="Produção por Tecnologia")
    production_total_df.to_excel(writer, sheet_name="Produção Total")
    emissions_df.to_excel(writer, sheet_name="Emissões")
    

#Capacidade incremental = expansão nova do ano
#Capacidade total = tudo o que está disponível para operar
#Produção = o que é de fato produzido anualmente, considerando a capacidade total disponível    
    

    
    
#%% 
    
    

"""OBS DE UM OUTRO MOMENTO: Você pode criar variáveis diferentes em Pyomo:
    
m.new_innov_plants[tech, year] (instalar nova planta inovadora)
m.retrofit[tech, year] (planta existente convertendo para inovadora)
m.prod_innovative[tech, year] (produção pela rota inovadora)

Você pode ligar isso aos parâmetros do innovation_measures assim:"""

          
            

#%%
"""5. visualização de resultado"""



# depois, se conseguiu, coloca mais tecnologias
# depois coloca mais tecnologias atuais (que estao funcionando)
# depois melhora a descrição das tecnologias (consumo de energia por fonte)
# colocar restrições
# aumentar granularidade (localização das plantas). Por exemplo, qual o custo de carvão vegetal por estado? eltricidade, GN, Potencial eólico, etc...