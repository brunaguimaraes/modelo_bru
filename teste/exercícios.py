# -*- coding: utf-8 -*-
"""
Created on Fri Jul 25 16:52:07 2025

@author: Bruna
"""

#%%
"""1.importar bibliotecas"""

import pandas as pd
import numpy as np
from pyomo.environ import (
    ConcreteModel, Set, Var, Param, Constraint, Objective, NonNegativeReals,
    Expression, minimize
)
#%%
"""2. importar dados"""

# Carregar dados de plantas existentes (arquivo Excel com colunas: plant_id, route, capacity, remaining_life)
plants=pd.read_excel('Plants_teste.xlsx')
tecnologias=pd.read_csv('Tecnologias.csv',sep=";")

#Agora o meu dataframe utiliza a rota como índice para identificar cada uma das linhas de tecnologia
tecnologias.set_index('Route', inplace=True)

#%%
### inserindo mais dados históricos de produção
### inserindo mais dados históricos de produção conforme modelagem do Otto

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




#%%
"""3. projetar demanda"""

#criar um dataframe da demanda entre 2024 e 2050: A demanda é equivalente ao nível de produção calculado no PROJETO IMAGINE.

"""Steel production Projection"""

for year in np.linspace(2024,2050,2050-2024+1).astype(int):
    steel_production.loc[year] =np.full([len(steel_production.columns)],np.nan)

Production_increase = {
        2025:1.037,
        2030:1.146,
        2035:1.306,
        2040:1.486,
        2045:1.699,
        2050:1.961,
        }

steel_production = steel_production.interpolate()



#%%
"""4. otimização"""

#todo ano checa se a demanda é atendida
#se não for atendida, escolhe nova tecnologia tal que reduz o custo total da produção


# Ano base do seu script
current_year = 2023
# Horizon decenal:
future_years = list(range(current_year+1, 2051))  # 2023 a 2050 - future_years é simplesmente uma lista Python dos anos seguintes em que seu modelo vai instalar plantas, produzir e mitigar emissões.
routes = ['BF-BOF', 'EAF', 'DR-NG', 'DR-H2', 'SR', 'BF-BOF-CCS']

# Calcular capacidade disponível de cada rota em cada ano, considerando vida útil restante
capacity_exist = {p: {t: 0.0 for t in future_years} for p in routes}
for _, row in plants.iterrows():
    p = row['Route']
    cap = float(row['Capacity'])
    retire_year = float(row['Retrofitdate'])
    for t in future_years:
        if t <= retire_year:
            capacity_exist[p][t] += cap

# Calcular a capacidade disponível total, equivalent à produção total somando todas as tecnologias:
capacity_total = {t: sum(capacity_exist[p][t] for p in routes) for t in future_years}    
    
# Iniciar acumulador de nova capacidade (decisão de investimento)
#cum_new_cap = {p: 0.0 for p in routes}

#%%

"""Carregando os dados de limites de penetração"""

"""essa primeira etapa de carregar as medidas, eu já imputei lá nas etapas iniciais, na tabela de "tecnologias"""
# 1. Carregar medidas de inovação (parâmetros associados a cada tecnologia inovadora)
#innovation_measures = pd.read_csv('Innovation_measures_2.csv')
# Esperando colunas típicas: ['Technology', 'Route', 'Emission_factor', 'Cost', 'Start_year', ...]
# Pode conter tecnologias que são melhorias/retrofit em rotas existentes OU rotas novas de fato

# 2. Carregar restrições de penetração (quanto pode instalar de cada tecnologia por ano)
penetration_inovative = pd.read_csv('Penetration_innovative.csv')  # Ex: colunas 'Technology', '2023', '2024',...
penetration_inovative = penetration_inovative.set_index('Technology')

#Ligando aos conjuntos do modelo Pyomo
# -------------------
# 1. Conjuntos:
# Supondo...

techs = list(penetration_inovative.index)
years = [int(y) for y in penetration_inovative.columns]
m = ConcreteModel()
m.Tech = Set(initialize=techs)
m.Year = Set(initialize=years, ordered=True)


# 2. Variáveis de decisão:
m.capacity_expansion = Var(m.Tech, m.Year, domain=NonNegativeReals)    # [capacidade instalada nova]
# Capacidade adicional (expansão) instalada em cada tecnologia por ano
m.production = Var(m.Tech, m.Year, domain=NonNegativeReals)            # [produção realizada]

# 3. Parâmetros:
# penetration_dict
# production_dict / m.ProductionTarget
# measures_dict
# capacity_exist
# m.EmissionLimit



# 4. Capacidade acumulada:
def total_capacity(m, tech, year):
    return capacity_exist.get(tech, {}).get(year, 0) + \
        sum(m.capacity_expansion[tech, y] for y in m.Year if y <= year)
m.TotalCapacity = Expression(m.Tech, m.Year, rule=total_capacity)


# 5. Restrições:
penetration_dict = penetration_inovative.stack().to_dict()
# Isso cria um dicionário {(tech, ano): valor_max, ...}

production_dict = steel_production['Total'].to_dict()
m.ProductionTarget = Param(m.Year, initialize=production_dict)
  
# Restrição: expansão limitada pela penetração máxima da tecnologia     """Expansão só pode atender até a fração definida da demanda anual"""
def penetration_rule(m, tech, year):
    return m.capacity_expansion[tech, year] <= penetration_dict.get((tech, year), 0) * m.ProductionTarget[year]
m.PenetrationLimit = Constraint(m.Tech, m.Year, rule=penetration_rule)

def capacity_constraint(m, tech, year):
    return m.production[tech, year] <= m.TotalCapacity[tech, year]
m.CapacityLimit = Constraint(m.Tech, m.Year, rule=capacity_constraint)

def demand_constraint(m, year):
    return sum(m.production[tech, year] for tech in m.Tech) >= m.ProductionTarget[year]
m.Demand = Constraint(m.Year, rule=demand_constraint)


"""conferir isso"""

measures_dict = tecnologias.T.to_dict()

def emission_rule(m, year):
    return sum(measures_dict[tech]['Emission_factor'] * m.production[tech, year] for tech in m.Tech) <= m.EmissionLimit[year]
m.TotalEmissions = Constraint(m.Year, rule=emission_rule)

# 6. Função objetivo:
def obj_rule(m):
    return \
        sum(measures_dict[tech]['CAPEX'] * m.capacity_expansion[tech, year]
            for tech in m.Tech for year in m.Year) + \
        sum(measures_dict[tech]['OPEX'] * m.production[tech, year]
            for tech in m.Tech for year in m.Year)
m.Objective = Objective(rule=obj_rule, sense=minimize)










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