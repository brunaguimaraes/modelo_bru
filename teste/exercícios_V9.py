# -*- coding: utf-8 -*-
"""
Created on Fri Jul 25 16:52:07 2025

@author: Bruna


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

#%% EAF deu a menos - ETAPA A — AJUSTE EAF

target_eaf = production_by_route['EAF']
capacity_eaf = capacity_by_route['EAF']

missing_eaf = target_eaf - capacity_eaf
print(missing_eaf)


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

    plants_base = pd.concat(
        [plants_base, pd.DataFrame([eaf_virtual])],
        ignore_index=True
    )


#%% AJUSTANDO BOF

# produção observada por rota (somente rotas físicas)
production_by_route_simple = steel_production.loc[base_year, ['BOF', 'EAF']]

# capacidade total por rota (já com EAF virtual)
capacity_by_route = plants_base.groupby('Route')['Capacity'].sum()

# taxa de utilização ASSUMIDA por rota
utilization_by_route = production_by_route_simple / capacity_by_route

plants_base['Utilization'] = plants_base['Route'].map(utilization_by_route)

plants_base['Production_2023'] = (
    plants_base['Capacity'] * plants_base['Utilization']
)

#%% SEPARANDO ROTAS BOF


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


#%% CARAIO NEM ACREDITO



# Lista de plantas históricas/base
plant_names = plants_unified["Plantname"].tolist()
years = sorted(steel_production.index.tolist())
future_years = list(range(2023, 2051))


# Dicionário: atributos da planta
plant_attr = plants_unified.set_index("Plantname").to_dict('index')

# Se quiser adicionar anos futuros não no histórico:
for ano in future_years:
    if ano not in years:
        years.append(ano)
years = sorted(years)
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

production_dict = {int(y): float(v) for y,v in steel_total_target['Total'].to_dict().items() if int(y) in years}



#%% 5. otimização

#todo ano checa se a produção alvo é atendida
#se não for atendida, escolhe nova tecnologia tal que reduz o custo total da produção

# Ano base do script
current_year = 2023
# Horizon decenal:
future_years = list(range(current_year+1, 2051))  # 2023 a 2050 - future_years é simplesmente uma lista Python dos anos seguintes em que seu modelo vai instalar plantas, produzir e mitigar emissões.
routes = ['BF-BOF CC', 'BF-BOF MC', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']

# # Calcular capacidade existente de cada rota em cada ano, considerando vida útil restante
# production_exist = {p: {t: 0.0 for t in future_years} for p in routes}
# for _, row in plants.iterrows():
#     p = row['Final_route']
#     cap = float(row['Capacity'])
#     retire_year = float(row['Retrofitdate'])
#     for t in future_years:
#         if t <= retire_year:
#             production_exist[p][t] += cap

# # Calcular a capacidade existente total, equivalent à produção total somando todas as tecnologias:
# production_exist_total = {t: sum(production_exist[p][t] for p in routes) for t in future_years}    
    
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
m.Plant = Set(initialize=plant_names)


# Rotas das plantas
routes_in_plants = plants_unified["Final_route"].unique().tolist()
m.Route = Set(initialize=routes_in_plants)

# Mapear planta → rota
plant_to_route = {p: plant_attr[p]["Final_route"] for p in plant_names}

# Criar measures_dict também para fácil lookup dos parâmetros das tecnologias:
all_techs = set(tecnologias.index.tolist()).union(routes_in_plants)
measures_dict = tecnologias.T.to_dict()


# Restrição: definição do productiontarget
# Isso cria um dicionário {(tech, ano): valor_max, ...}
production_dict = {y: v for y, v in steel_total_target['Total'].to_dict().items() if y in years}
m.ProductionTarget = Param(m.Year, initialize=production_dict)


# 2. Variáveis de decisão:

# Produção de cada planta em cada ano [kt]
m.production = Var(m.Plant, m.Year, domain=NonNegativeReals)

# Planta virtual adicionada ("capacidade incremental") por ano: lista que será alimentada ao longo do tempo
virtual_plants = []




# a) Só opera se planta está ativa
def is_plant_active(plant, year):
    info = plant_attr[plant]
    return (year >= int(info['Startyear'])) and (year <= int(info['Retrofitdate']))

# Capacidade máxima: produção só é possível nos anos de atividade
def cap_rule(m, plant, year):
    info = plant_attr[plant]
    if not is_plant_active(plant, year):
        return m.production[plant, year] == 0
    return m.production[plant, year] <= info['Capacity']

m.CapLimit = Constraint(m.Plant, m.Year, rule=cap_rule)

# b) Restrição de produção nacional por ano (todos os anos!)
def total_production_rule(m, year):
    # Só pode chamar produção para plantas existentes até o ano ou plantas virtuais criadas!
    prod_this_year = sum(m.production[plant, year] for plant in m.Plant)
    return prod_this_year >= m.ProductionTarget[year]
m.NationalProduction = Constraint(m.Year, rule=total_production_rule)

# c) Restrição de produção por rota (agregada): pode querer garantir um mínimo/máximo, ou para checagem/controle
# Penetração máxima por tecnologia/ano (opcional):
# Soma as produções das plantas por rota e compara com as restrições:

penetration_dict = {(tech, int(year)): float(val)
                    for (tech, year), val in penetration_inovative.stack().to_dict().items()}
# def penetration_rule_production(m, tech, year):
#     return sum(m.production[plant, year] for plant in m.Plant if plant_to_route[plant]==tech) <= \
#         penetration_dict.get((tech, year), 0.0) * m.ProductionTarget[year]
        
def penetration_rule_production(m, tech, year):
    plants_of_tech = [plant for plant in m.Plant if plant_to_route[plant]==tech]
    penetration_lim = penetration_dict.get((tech, year), 0.0)
    if (not plants_of_tech) or penetration_lim == 0:
        return Constraint.Skip
    return (
        sum(m.production[plant, year] for plant in plants_of_tech)
        <= penetration_lim * m.ProductionTarget[year]
    )        
                
m.PenetrationLimitProduction = Constraint(m.Tech, m.Year, rule=penetration_rule_production)

# d) Emissões por rota/planta (opcional, pode ser na função objetivo ou restrição, igual seu código)


# #CUMPRIMENTO DO HISTÓRICO
# historical_routes = ['BF-BOF MC', 'BF-BOF CC', 'EAF']

# def historical_production_rule(m, tech, year):
#     if year <= current_year:
#         if tech in historical_routes:
#             # usa o dado oficial histórico
#             return m.production[tech, year] == steel_production.loc[year, tech]
#         else:
#             # tecnologias que NÃO existiam no histórico
#             return m.production[tech, year] == 0
#     return Constraint.Skip
# m.HistoricalProduction = Constraint(
#     m.Tech, m.Year,
#     rule=historical_production_rule
# )


# # Capacidade acumulada:
# def total_production(m, tech, year):
#     return production_exist.get(tech, {}).get(year, 0) + \
#         sum(m.production_expansion[tech, y] for y in m.Year if y <= year)
# m.TotalProduction = Expression(m.Tech, m.Year, rule=total_production)


# #essa restrição faz Produção por Tecnologia = histórico + produção incremental acumulada
# def production_balance_rule(m, tech, year):
#     return m.production[tech, year] == m.TotalProduction[tech, year]
# m.ProductionBalance = Constraint(m.Tech, m.Year, rule=production_balance_rule)

  
# # Restrição: expansão limitada pela penetração máxima da tecnologia     """Expansão só pode atender até a fração definida da produção alvo anual"""
# penetration_dict = {(tech, int(year)): float(val)
#                     for (tech, year), val in penetration_inovative.stack().to_dict().items()}

# def penetration_rule_production(m, tech, year):
#     return m.production[tech, year] <= penetration_dict.get((tech, year), 0.0) * m.ProductionTarget[year]
# m.PenetrationLimitProduction = Constraint(m.Tech, m.Year, rule=penetration_rule_production)


# def penetration_rule_expansion(m, tech, year):
#     return (
#         m.production_expansion[tech, year]
#         <= penetration_dict.get((tech, year), 0.0) * m.ProductionTarget[year]
#     )
# m.PenetrationLimitExpansion = Constraint(m.Tech, m.Year, rule=penetration_rule_expansion)


# def production_constraint(m, year):
#     if year <= current_year:
#         return Constraint.Skip
#     return sum(m.production[tech, year] for tech in m.Tech) >= m.ProductionTarget[year]
# m.ProductionConstraint = Constraint(m.Year, rule=production_constraint)


# # Restrição: a produção do meu modelo tem que ser igual ou menor à capacidade instalada de cada ano até 2050
# def capacity_constraint(m, tech, year):
#     return m.production[tech, year] <= m.TotalCapacity[tech, year]
# m.CapacityLimit = Constraint(m.Tech, m.Year, rule=capacity_constraint)





######
# 5. "Expansão" de capacidade - Novas plantas virtuais
######

# Função para adicionar planta virtual de expansão para um dado ano, rota, e capacidade:
def add_virtual_plant(plants_df, name, route, year, cap, retrofit=2050):
    newrow = {
        'Plantname': name,
        'Final_route': route,
        'Capacity': cap,
        'Production_2023_final': 0, # ou nan se for só futura
        'Startyear': year,
        'Retrofitdate': retrofit
    }
    return pd.concat([plants_df, pd.DataFrame([newrow])], ignore_index=True)

# Exemplo: digamos que ao rodar a otimização, no loop, verifique que a capacidade somada de todas as plantas não supre o ProductionTarget. Daí chame `add_virtual_plant()` para criar novas linhas/plants para aquele ano.

# Se quiser já criar plantas virtuais ANTES de rodar Pyomo (com heurística baseada na diferença entre capacidade total existente e production_target futuro):
#   - Calcule para cada ano a diferença: production_target - soma(capacidade ativa)
#   - Se positivo, crie planta virtual e incremente em plants_unified


"""Medidas de mitigação/tecnologias disponíveis para a escolha do modelo"""

measures_dict = tecnologias.T.to_dict()


"""Nível de emissão alvo"""

# === Limites de emissões GWP-AR5 (kt CO2 eq) ===
#emission_2020 = 57016
#emission_2050 = 70000  # sua meta ESCOLHER!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

emission_2020 = 158000000000000000000
emission_2050 = 20000000000000000000000000


year_start, year_end = 2020, 2050

### 1. Dicionário de limites de emissão por ano:
emission_limit_dict = {
    y: emission_2020 + (emission_2050 - emission_2020) * (y - year_start) / (year_end - year_start)
    for y in years
}
m.EmissionLimit = Param(m.Year, initialize=emission_limit_dict)


"""Otimização das emissões"""

### 2. Restrição de emissões — POR PLANTA
# Atribua a cada planta a sua "tecnologia principal" para buscar a intensidade no measures_dict.
def emission_rule(m, year):
    return sum(
        measures_dict[plant_to_route[plant]]['Emission_intensity'] * m.production[plant, year]
        for plant in m.Plant
    ) <= m.EmissionLimit[year]
m.TotalEmissions = Constraint(m.Year, rule=emission_rule)

### 3. Função objetivo — mínima soma CAPEX+OPEX (por planta)
def obj_rule(m):
    total = 0
    for plant in m.Plant:
        tech = plant_to_route[plant]
        capex = float(measures_dict[tech]['CAPEX']) if not pd.isna(measures_dict[tech]['CAPEX']) else 0
        opex = float(measures_dict[tech]['OPEX']) if not pd.isna(measures_dict[tech]['OPEX']) else 0
        for year in m.Year:
            # CAPEX ao "abrir" a planta (se ano = startyear)
            if int(plant_attr[plant]['Startyear']) == int(year):
                total += capex * plant_attr[plant]['Capacity']
            # OPEX todo ano
            total += opex * m.production[plant, year]
    return total
m.Objective = Objective(rule=obj_rule, sense=minimize)

      #%% BLOCO DE DEBUG!!!!
      


#%% Extrair e visualizar os resultados da otimização


from pyomo.opt import SolverFactory

solver_name = "ipopt"  # "highs", "cbc",  "couenne", "bonmin", "ipopt", "scip", or "gcg".
solver = SolverFactory(solver_name+"nl", executable=modules.find(solver_name), solve_io="nl")
    
result_solver = solver.solve(m, tee = True)


#Colocar resultados em DataFrame 

# Produção por planta/ano
# production_df = pd.DataFrame([
#     {"Plant": plant, "Final_route": plant_to_route[plant], "Year": year, "Production": m.production[plant, year].value}
#     for plant in m.Plant for year in m.Year
# ])

production_df = pd.DataFrame([
    {"Plant": plant,
     "Final_route": plant_to_route[plant],
     "Year": year,
     "Production": m.production[plant, year].value,
     "Startyear": plant_attr[plant]['Startyear'],
     "Retrofitdate": plant_attr[plant]['Retrofitdate'],
     "Capacity": plant_attr[plant]['Capacity']}
    for plant in m.Plant for year in m.Year
])

# Para obter produção por rota:
prod_by_route = production_df.groupby(["Final_route", "Year"])["Production"].sum().reset_index()


# Produção total agrupada (independente da tecnologia)

production_total_df = (
    production_df
    .groupby("Year", as_index=False)["Production"]
    .sum()
)
production_total_df.rename(columns={"Production": "Total_Production"}, inplace=True)


#Se quiser saber a produção de plantas novas instaladas a cada ano:
incremental_production_df = production_df[
    production_df["Startyear"] == production_df["Year"]
].copy()
incremental_production_df["Technology"] = incremental_production_df["Final_route"]  # só pra manter padrão antigo
incremental_production_df.rename(columns={"Production": "Production_Expansion"}, inplace=True)
# Se quiser soma por tecnologia:
inc_prod_by_tech = incremental_production_df.groupby(["Technology", "Year"])["Production_Expansion"].sum().reset_index()




# você pode até plotar:

import matplotlib.pyplot as plt

#Para novo modelo (só produção incremental faz sentido se for planta nova):
for tech in incremental_production_df["Technology"].unique():
    subset = incremental_production_df[incremental_production_df["Technology"] == tech]
    plt.plot(subset["Year"], subset["Production_Expansion"], label=tech)
plt.title("Expansão de capacidade por tecnologia")
plt.xlabel("Ano")
plt.ylabel("Capacidade adicionada")
plt.legend()
plt.show()

#Se quiser plotar produção anual TOTAL por rota (mais robusto):
for tech in prod_by_route["Final_route"].unique():
    subset = prod_by_route[prod_by_route["Final_route"] == tech]
    plt.plot(subset["Year"], subset["Production"], label=tech)
plt.title("Produção anual por rota")
plt.xlabel("Ano")
plt.ylabel("Produção (kt)")
plt.legend()
plt.show()




# ver as emissões efetivas resultantes (para comparar com o limite):

# emissions = {
#     year: sum(measures_dict[tech]['Emission_intensity'] * m.production[tech, year].value for tech in m.Tech)
#     for year in m.Year
# }

# emissions_df = pd.DataFrame(list(emissions.items()), columns=["Year", "Emissions"])
# # print(emissions_df)
emissions = {}
for year in m.Year:
    total_emiss = sum(
        measures_dict[plant_to_route[plant]]['Emission_intensity'] * m.production[plant, year].value
        for plant in m.Plant
    )
    emissions[year] = total_emiss
emissions_df = pd.DataFrame(list(emissions.items()), columns=["Year", "Emissions"])


#%% exportar os resultados para Excel 

# exportar os resultados para Excel 

import os

# Defina o caminho absoluto do arquivo
output_path = r"C:\Users\Bruna\OneDrive\DOUTORADO\0.TESE\modelagem\modelo_bru\teste\resultados\resultados_modelo_V12.xlsx"
os.makedirs(os.path.dirname(output_path), exist_ok=True)


# Salva o Excel no local desejado
with pd.ExcelWriter(output_path) as writer:
    incremental_production_df.to_excel(writer, sheet_name="Produção Incremental")      # Só se criou!
    production_df.to_excel(writer, sheet_name="Produção por Planta")
    prod_by_route.to_excel(writer, sheet_name="Produção por Tecnologia")
    production_total_df.to_excel(writer, sheet_name="Produção Total")
    emissions_df.to_excel(writer, sheet_name="Emissões")


    
    