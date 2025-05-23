# -*- coding: utf-8 -*-
"""
R1 = Route BOF using Coal
R2 = Route BOF using Charcoal
R3 = Route EAF using scrap
R4 = Route Independet producers 

TO DO: 
  - tudo
  - ajustar um excel com o ano base do chris e ver como está a situação atual e adicionar uma extra com esse valor restante
  - salvar esse excel na miha pasta e aprender a conectar a localiação aqui
  
"""
 
import pandas as pd
import numpy as np


# ===== Integrando vida útil de plantas ao modelo de otimização =====

# 1) Carregar dados de plantas existentes (arquivo Excel com colunas: plant_id, route, capacity, remaining_life)
plants = pd.read_excel('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/plants.xlsx')  

# Ano base do seu script
current_year = 2020
# Horizon decenal:
future_years = list(range(current_year+1, 2051))  # 2021 a 2050 - future_years é simplesmente uma lista Python dos anos seguintes em que seu modelo vai instalar plantas, produzir e mitigar emissões.
routes = ['R1', 'R2', 'R3', 'R4']

# 2) Calcular capacidade disponível de cada rota em cada ano, considerando vida útil restante
capacity_exist = {p: {t: 0.0 for t in future_years} for p in routes}
for _, row in plants.iterrows():
    p = row['Route']
    cap = float(row['Capacity'])
    retire_year = float(row['Retrofitdate'])
    for t in future_years:
        if t <= retire_year:
            capacity_exist[p][t] += cap

# 3) Iniciar acumulador de nova capacidade (decisão de investimento)
cum_new_cap = {p: 0.0 for p in routes}

# 4) Ajustar sua função de otimização para receber e usar essas capacidades
def optimization_module(year, emission_target, cap_exist, cum_new):
    model = ConcreteModel()

    # --- variáveis originais ---
    # model.X1, X2, ..., X9, CCS etc.
    # ... (mantém toda a lógica de medidas de mitigação) ...

    # --- nova variável: capacidade adicional anual por rota ---
    model.newCap = Var(routes, within=NonNegativeReals)

    # --- cálculo de produção (mantém o seu racional atual) ---
    production_R1 = (...)  # igual ao seu script
    production_R2 = (...)
    production_R3 = (...)
    production_R4 = (...)
    # produção de inovações (model.X5..X9)

    # --- restrições de vida útil / capacidade ---
    model.con = ConstraintList()
    model.con.add(production_R1 <= cap_exist['R1'][year] + cum_new['R1'] + model.newCap['R1'])
    model.con.add(production_R2 <= cap_exist['R2'][year] + cum_new['R2'] + model.newCap['R2'])
    model.con.add(production_R3 <= cap_exist['R3'][year] + cum_new['R3'] + model.newCap['R3'])
    model.con.add(production_R4 <= cap_exist['R4'][year] + cum_new['R4'] + model.newCap['R4'])

    # --- ajustes no CAPEX: custo de nova capacidade em vez de custo fixo por produção ---
    # Remova o termo +170*production_R1/1000 do capex_R1 e substitua por:
    capex_new_R1 = model.newCap['R1'] * 170   # US$ por unidade de capacidade instalada
    # (faça o mesmo para R2, R3, R4, usando seus valores de CAPEX)

    # Reconstrua capex_R1:
    # capex_existing_R1 = sum(...) * production_R1/1000  # medidas de mitigação
    # capex_R1 = capex_existing_R1 + capex_new_R1

    # --- objetivo: incluir capex_new_Ri no somatório de custos ---
    model.obj = Objective(expr=
        # ... seu termo atual de capex_total + opex + etc ...
        + capex_new_R1
        # + capex_new_R2 + capex_new_R3 + capex_new_R4
    )

    # --- resto da sua otimização (emissões, restrições, solver) ---
    solver = SolverFactory('ipopt')
    solver.solve(model, tee=False)

    # Retornar também as decisões de nova capacidade
    return model, value(model.obj), None, {p: value(model.newCap[p]) for p in routes}

# 5) Na rotina principal, acumule e passe as capacidades:
Results = pd.DataFrame(...)  # seu DataFrame existente
for year in future_years:
    model, cost, CE, new_caps = optimization_module(
        year,
        emission_calc(year) * Emission_reduction[year],
        capacity_exist,
        cum_new_cap
    )
    for p in routes:
        cum_new_cap[p] += new_caps[p]
        Results.loc[f'NewCap_{p}', year] = new_caps[p]
    # ... preencha o restante de Results conforme o script atual ...



#%%
"""1. Importing Data"""

#Confersion factor Gj to Ktoe    
tj_to_ktoe = 1/41.868
ktoe_to_tj = 41.868
dolar = 5.31 #1 dolar = 5.31 reais. mean value of 2021

#Greenhouse gases Global Warning Potential GWP:
GWP = {'CH4':28,'N2O':265}

"""Importing Crude Steel production by route in kt"""

steel_production = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/steel_production.csv") #in kt
steel_production = steel_production.set_index('Year')   
steel_production['Total']= steel_production.sum(axis=1)

"""Importing Pig Iron production by Route in kt"""
pig_iron_production = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Pig_iron_production.csv")
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
scrap_supply = pd.read_csv('https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Scrap_supply.csv')
scrap_supply = scrap_supply.set_index('Recovery_rate')

"""Importing Emission Factor"""
emission_factor = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/emission_factor.csv") #t/TJ or kg/GJ
emission_factor = emission_factor.set_index('Combustivel')
emission_factor['CO2e'] = emission_factor['CO2'] + emission_factor['CH4']*28 + emission_factor['N2O']*265

"""Importing Energy Consumption compatible with the Useful Energy Balance (BEU):
    In the META report they already separeted the Final Energy Consumption in the same nomenclature as the BEU
    """
EI_BEU = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/EI_Route_Step_year.csv")
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

"""Importing Mitigation measures:"""

mitigation_measures = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Iron_and_steel_mitigation_measures_V2.csv")
mitigation_measures['Total Reduction GJ/t'] = mitigation_measures['Energy reduction (Gj/t)']*mitigation_measures.Penetration

#lifetime of mitigation measures:
life_time = 20 #years
mitigation_measures_dict = {}
for route in pd.unique(mitigation_measures.Route):
    mitigation_dict = {}
    mitigation = {}
    for etapa in pd.unique(mitigation_measures.loc[mitigation_measures['Route']==route,'Step']):
#        mitigation=mitigation_measures.loc[mitigation_measures['Route']==route].loc[mitigation_measures['Step']==etapa].set_index('Mitigation measure').drop(['Route','Step'],axis = 1).transpose().to_dict()
#        mitigation_dict[etapa] = mitigation
        mitigation=mitigation_measures.loc[mitigation_measures['Route']==route].set_index('Mitigation measure').drop(['Route'],axis = 1).transpose().to_dict()
    mitigation_measures_dict[route] = mitigation
    
# teste = mitigation_measures.loc[mitigation_measures['Route']==route].set_index('Mitigation measure').drop(['Route'],axis = 1).transpose().to_dict()

#Percentual of intensity reduction within each route and step
mitigation_measures['Percentual of reduction'] = 0
for indice in mitigation_measures.index:
    intensidade_Route_etapa= float(pd.DataFrame((mitigation_measures.loc[mitigation_measures['Route'] == mitigation_measures.loc[indice]['Route']].groupby('Step').sum()['Total Reduction GJ/t'])).loc[mitigation_measures.loc[indice]['Step']])
    if intensidade_Route_etapa == 0:
        pass
    else:
        mitigation_measures.loc[indice,'Percentual of reduction'] = mitigation_measures.loc[indice]['Total Reduction GJ/t']/intensidade_Route_etapa
        
innovation_measures = pd.read_csv('https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Innovation_measures.csv')

penetration_inovative = pd.read_csv('https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Penetration_innovative.csv')
penetration_inovative = penetration_inovative.set_index('Technology')

"""Importing Fuel prices"""
fuel_prices = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Fuel_price_3.csv")
#fuel_prices['BRL/TJ'] = fuel_prices['BRL/ktep']/ktoe_to_tj 
fuel_prices = fuel_prices.set_index('﻿Combustivel')
#fuel_prices.loc['Gas natural'] =fuel_prices.loc['Gas natural']/20

"""interest rate"""
interest_rate = 0.08
 
#%%
"""2. Historic Data"""

#Years from the historic data
past_years = np.linspace(2005,2023,2023-2005+1,dtype = int)

#Future years:
future_years = np.linspace(2024,2050,2050-2024+1,dtype = int)

#Base year (reference year for the projections)
base_year = 2023

#Energy Consumption in the Steel Production in the National Energy Balance (BEN)
 
# Energy_consumption_BEN = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Industry_Energy_Emissions_simulator/main/CE_Siderurgia.csv") #importing BEN_Steel
Energy_consumption_BEN = pd.read_excel("CE_Siderurgia novo.xlsx") #importing BEN_Steel
Energy_consumption_BEN = Energy_consumption_BEN.fillna(0) #filling NA with 0
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES':'Carvao mineral'},'Carvao metalurgico') #changing Outras primarias para outras secundarias
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES':'Gas de coqueria'},'Gas cidade') #changing Outras primarias para outras secundarias
Energy_consumption_BEN = Energy_consumption_BEN.replace({'FONTES':'Alcatrao'},'Outras fontes secundarias') #changing Outras primarias para outras secundarias
Energy_consumption_BEN = Energy_consumption_BEN.set_index('FONTES') #Changin index for Sources
Energy_consumption_BEN.index = Energy_consumption_BEN.index.str.capitalize() #Change all UPPER to Capitalize
Energy_consumption_BEN.columns = Energy_consumption_BEN.columns.astype(int) #Changing the columns type: from str to int

#Summing Biodeisel with Diesel to adjust the nomenclature:
Energy_consumption_BEN.loc['Oleo diesel'] = Energy_consumption_BEN.loc['Biodiesel']+Energy_consumption_BEN.loc['Oleo diesel']
Energy_consumption_BEN = Energy_consumption_BEN.drop(index = ['Biodiesel'])
Energy_consumption_BEN = Energy_consumption_BEN.rename(index = {'Glp': 'GLP'}) #fixing name
Energy_consumption_BEN = Energy_consumption_BEN .sort_index() #ordering the rows by fuel name
#Converting to Gj:
Energy_consumption_BEN_Gj = Energy_consumption_BEN*ktoe_to_tj 
#

#%%
"""Energy intensity of each route"""
R1_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R1'].iloc[:,3:].sum()
R1_EI_Total.index = R1_EI_Total.index.astype(int)
R2_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R2'].iloc[:,3:].sum()
R2_EI_Total.index = R2_EI_Total.index.astype(int)
R3_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R3'].iloc[:,3:].sum()
R3_EI_Total.index = R3_EI_Total.index.astype(int)
R4_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R4'].iloc[:,3:].sum()
R4_EI_Total.index = R4_EI_Total.index.astype(int)

#%%        
"""Energy Consumption"""

#R1 Energy Consumption:
R1_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'], data = 0)
for ano in past_years:
    R1_EC_Total.loc[ano] = R1_EI_Total.loc[ano]*steel_production['BOF MC'][ano]

#R2 Energy_consumption:
R2_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'], data = 0)
for ano in past_years:
    R2_EC_Total.loc[ano] = R2_EI_Total.loc[ano]*steel_production['BOF CC'][ano]

#R3_Energy_Cosumption:
R3_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'], data = 0)
for ano in past_years:
    R3_EC_Total.loc[ano] = R3_EI_Total.loc[ano]*steel_production['EAF'][ano]

#R4_Energy_Consumption:
R4_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'], data = 0)
for ano in past_years:
    R4_EC_Total.loc[ano] = R4_EI_Total.loc[ano]*pig_iron_production['Independente CV'][ano]    

"""Energy Consumption By Fuel"""
#This function calculates the energy consumption by fuel.
def energy_consumption(Route):
    """estimates the energy consumption using the Energy Intensity and the production"""
    
    EC_Total = pd.DataFrame(index = EI_BEU.index, columns = EI_BEU.columns, data = 0)
    EC_Total.Route = EI_BEU.Route
    EC_Total.Combustivel = EI_BEU.Combustivel
    EC_Total.Step = EI_BEU.Step
    
    #Energy consumption in R1:
    if Route =='R1':      
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R1'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF MC'][int(ano)] 
            
    #Energy consumption in R2
    if Route =='R2' :       
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R2'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF CC'][int(ano)]       
            
            #Energy consumption in R3   
    if Route == 'R3':
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R3'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['EAF'][int(ano)]  
            
            #Energy consumption in R4
    if Route == 'R4':
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R4'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*pig_iron_production['Independente CV'][int(ano)]     
                
    if Route == 'todas':
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R1'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF MC'][int(ano)] 
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R2'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF CC'][int(ano)]                     
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R3'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['EAF'][int(ano)]  
        for ano in EI_BEU.columns[3:]:
            for indice in EC_Total.loc[EC_Total['Route']=='R4'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*pig_iron_production['Independente CV'][int(ano)]     
                
    return EC_Total

#Energy consumption without calibration
Total_energy_consumption_R1 = energy_consumption('R1').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R2 = energy_consumption('R2').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R3 = energy_consumption('R3').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R4 = energy_consumption('R4').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption = energy_consumption('todas').groupby(['Combustivel'], axis =0, as_index = False).sum()

#%%
"""Adjustments for the energy consumption'"""

#Matching the Energy Intensity of each fuel, route and step to the energy consumption in the Energy Balance
for combustivel in Total_energy_consumption['Combustivel']:
    for ano in past_years:
        for i in EI_BEU.loc[EI_BEU['Combustivel'] == combustivel].index:
            EI_BEU[str(ano)][i] = EI_BEU[str(ano)][i]*Energy_consumption_BEN_Gj[ano][combustivel]/Total_energy_consumption.loc[Total_energy_consumption['Combustivel']==combustivel][str(ano)]

"""Creating dictionary"""

EI_dict= {}
a_dict = {}
for Route in pd.unique(EI_BEU['Route']):
    a_dict={}
    for etapa in pd.unique(EI_BEU.loc[EI_BEU['Route']==Route]['Step']):
        a =  EI_BEU.loc[EI_BEU['Route']==Route].loc[EI_BEU['Step']==etapa].set_index('Combustivel').drop(['Route','Step'],axis =1)
        a = a.to_dict()
        a_dict[etapa] = a
    EI_dict[Route] = a_dict   
#%%
"""Energy intensity of each route ajdusted """
R1_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R1'].iloc[:,3:].sum()
R1_EI_Total.index = R1_EI_Total.index.astype(int)
R2_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R2'].iloc[:,3:].sum()
R2_EI_Total.index = R2_EI_Total.index.astype(int)
R3_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R3'].iloc[:,3:].sum()
R3_EI_Total.index = R3_EI_Total.index.astype(int)
R4_EI_Total = EI_BEU.loc[EI_BEU['Route'] == 'R4'].iloc[:,3:].sum()
R4_EI_Total.index = R4_EI_Total.index.astype(int)

"""Energy share by route"""

#Energy consumption after calibration;
Total_energy_consumption_R1 = energy_consumption('R1').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R2 = energy_consumption('R2').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R3 = energy_consumption('R3').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R4 = energy_consumption('R4').groupby(['Combustivel'], axis =0, as_index = False).sum()

#Creating Energy Share DataFrame by Route
Energy_share_R1 = Total_energy_consumption_R1.set_index('Combustivel').drop(columns=['Route','Step'])
Energy_share_R2 = Total_energy_consumption_R2.set_index('Combustivel').drop(columns=['Route','Step'])
Energy_share_R3 = Total_energy_consumption_R3.set_index('Combustivel').drop(columns=['Route','Step'])
Energy_share_R4 = Total_energy_consumption_R4.set_index('Combustivel').drop(columns=['Route','Step'])

Energy_share_R1.columns = Energy_share_R1.columns.astype(int)
Energy_share_R2.columns = Energy_share_R2.columns.astype(int)
Energy_share_R3.columns = Energy_share_R3.columns.astype(int)
Energy_share_R4.columns = Energy_share_R4.columns.astype(int)

#EnergyShare = Energy consumption/Total energy consumption
Energy_share_R1 = Energy_share_R1/Energy_share_R1.sum()
Energy_share_R2 = Energy_share_R2/Energy_share_R2.sum()
Energy_share_R3 = Energy_share_R3/Energy_share_R3.sum()
Energy_share_R4 = Energy_share_R4/Energy_share_R4.sum()

#Energy share will be conserved for future years:
for i in future_years:
    Energy_share_R1[i]=Energy_share_R1[base_year]
    Energy_share_R2[i]=Energy_share_R2[base_year]
    Energy_share_R3[i]=Energy_share_R3[base_year]
    Energy_share_R4[i]=Energy_share_R4[base_year]

#Energy Intensity for future years
for i in future_years:
    R1_EI_Total[i] = R1_EI_Total[base_year]
    R2_EI_Total[i] = R2_EI_Total[base_year]
    R3_EI_Total[i] = R3_EI_Total[base_year]
    R4_EI_Total[i] = R4_EI_Total[base_year]
    
#%%
"""Emission Base Reference"""
#Emission base reference is the amount of emissions when no measure is considered.
year = 2023
carbon_content = 0.01
def emission_calc (year):
    """This function estimates the emission in a given year. It uses the production in each route, the fuel share and the emission factor. After it removes the amount of carbon in the steel considering 1%"""
    emission = ((
        float(R1_EI_Total[year])*(float(steel_production.loc[year]['Share_BOF_MC']))*steel_production.loc[year]['Total']*sum(Energy_share_R1.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R1.index)
        +(float(R2_EI_Total[year]))*steel_production.loc[year]['Total']*(steel_production.loc[year]['Share_BOF_CC'])*sum(Energy_share_R2.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R2.index)
        +(float(R3_EI_Total[year]))*steel_production.loc[year]['EAF']*sum(Energy_share_R3.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R3.index)
        +(float(R4_EI_Total[year]))*pig_iron_production.loc[year]['Independente CV']*sum(Energy_share_R4.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R4.index)
        )/10**6
    -steel_production['Total'][year]*carbon_content*44/12/10**3)
    return emission

Emission_Reference = emission_calc (2023)      
    
#%%
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
    steel_production[coluna][2025] = float(steel_production.loc[base_year][coluna]*Production_increase[2025])
    steel_production[coluna][2030] = float(steel_production.loc[base_year][coluna]*Production_increase[2030])
    steel_production[coluna][2035] = float(steel_production.loc[base_year][coluna]*Production_increase[2035])
    steel_production[coluna][2040] = float(steel_production.loc[base_year][coluna]*Production_increase[2040])
    steel_production[coluna][2045] = float(steel_production.loc[base_year][coluna]*Production_increase[2045])
    steel_production[coluna][2050] = float(steel_production.loc[base_year][coluna]*Production_increase[2050])

colunas = ['Integrada CM','Integrada CV','Independente CV']    
for coluna in colunas:    
    pig_iron_production[coluna][2025] = float(pig_iron_production.loc[base_year][coluna]*Production_increase[2025])
    pig_iron_production[coluna][2030] = float(pig_iron_production.loc[base_year][coluna]*Production_increase[2030])
    pig_iron_production[coluna][2035] = float(pig_iron_production.loc[base_year][coluna]*Production_increase[2035])
    pig_iron_production[coluna][2040] = float(pig_iron_production.loc[base_year][coluna]*Production_increase[2040])
    pig_iron_production[coluna][2045] = float(pig_iron_production.loc[base_year][coluna]*Production_increase[2045])
    pig_iron_production[coluna][2050] = float(pig_iron_production.loc[base_year][coluna]*Production_increase[2050])
    
steel_production['Share_BOF_MC'][2050] = steel_production['Share_BOF_MC'][base_year]
steel_production['Share_BOF_CC'][2050] = steel_production['Share_BOF_CC'][base_year]
steel_production['Share_EAF'][2050] = steel_production['Share_EAF'][base_year]
pig_iron_production['Share BOF CC'][2050] = pig_iron_production['Share BOF CC'][base_year]
pig_iron_production['Share BOF MC'][2050] = pig_iron_production['Share BOF MC'][base_year]

steel_production = steel_production.interpolate()
pig_iron_production= pig_iron_production.interpolate()

#%%
"""Optimization"""
#Creating model
def optimization_module(year,emission):
    
    """"For a givining Year and emission goal, the function will return mitigation measures, energy intensity, energy consumption, costs
R1 = Route BOF using Coal
R2 = Route BOF using Charcoal
R3 = Route EAF using scrap
R4 = Route Independet producers 
"""
    model = ConcreteModel()
         
    #Creating variables
    k1 = mitigation_measures_dict['R1'].keys() #list of the number of energy mitigation measures
    k2 = mitigation_measures_dict['R2'].keys()
    k3 = mitigation_measures_dict['R3'].keys()
    k4 =  mitigation_measures_dict['R4'].keys()
    
    model.X1 =  Var (k1,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 1
    model.X2 =  Var (k2,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 2
    model.X3 =  Var (k3,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 3
    model.X4 =  Var (k4,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 4
    model.X5= Var(within = NonNegativeReals) #DR-NG share 
    model.X6 = Var(within = NonNegativeReals) #Charcoal share
    model.X7 = Var(within = NonNegativeReals) #DR-H2 share
    model.X8 = Var(within= NonNegativeReals) #Smelting Reduction share
    model.X9 = Var(within = NonNegativeReals) #EAF
    model.CCS = Var(within = NonNegativeReals) #CCS in BF

    production_R1 = (float(steel_production.loc[year]['Share_BOF_MC'])-model.X5-model.X6-model.X7-model.X8-model.X9-model.CCS)*steel_production.loc[year]['Total']
    production_R2 = steel_production.loc[year]['Total']*(model.X6 + steel_production.loc[year]['Share_BOF_CC'])
    production_R3 = steel_production.loc[year]['Total']*(model.X9+steel_production.loc[year]['Share_EAF'])
    production_R4 = pig_iron_production.loc[year]['Independente CV']
    production_R5 = model.X5*steel_production.loc[year]['Total']
    production_R6 = model.X7*steel_production.loc[year]['Total']
    production_R7 = model.X8*steel_production.loc[year]['Total']
    production_CCS = model.CCS*steel_production.loc[year]['Total']
    
    #Capex of each route
    capex_R1 = sum((mitigation_measures_dict['R1'][i]['CAPEX ($/t)'])*model.X1[i]*production_R1/1000 for i in k1) +170*production_R1/1000 #170 é o capex
    capex_R2 = sum((mitigation_measures_dict['R2'][i]['CAPEX ($/t)'])*model.X2[i]*production_R2/1000 for i in k2)+170*production_R2/1000 #170 é o capex
    capex_R3 = sum((mitigation_measures_dict['R3'][i]['CAPEX ($/t)'])*model.X3[i]*production_R3/1000 for i in k3)+184*production_R3/1000
    capex_R4 = sum((mitigation_measures_dict['R4'][i]['CAPEX ($/t)'])*model.X4[i]*production_R4/1000 for i in k4)
    capex_R5 = (model.X5*steel_production.loc[year]['Total']*innovation_measures.loc[0]['CAPEX (Euro/t)']/1000)
    capex_R6 = (model.X7*steel_production.loc[year]['Total']*innovation_measures.loc[2]['CAPEX (Euro/t)']/1000)
    capex_R7 = (model.X8*steel_production.loc[year]['Total']*innovation_measures.loc[4]['CAPEX (Euro/t)']/1000)
    capex_CCS = (model.CCS*steel_production.loc[year]['Total']*innovation_measures.loc[6]['CAPEX (Euro/t)']/1000)
    
    
    opex_R1 = sum((mitigation_measures_dict['R1'][i]['OPEX ($/t)'])*model.X1[i]*production_R1/1000 for i in k1)+80*production_R1/1000 #80 é o opex base
    opex_R2 = sum((mitigation_measures_dict['R2'][i]['OPEX ($/t)'])*model.X2[i]*production_R2/1000 for i in k2)+80*production_R2/1000 #80 é o opex base
    opex_R3 = sum((mitigation_measures_dict['R3'][i]['OPEX ($/t)'])*model.X3[i]*production_R3/1000 for i in k3)+88*production_R3/1000 #80+10% é o opex base
    opex_R4 = sum((mitigation_measures_dict['R4'][i]['OPEX ($/t)'])*model.X4[i]*production_R4/1000 for i in k4)
    opex_R5 = (model.X5*steel_production.loc[year]['Total']*innovation_measures.loc[0]['OPEX']/1000)
    opex_R6 = (model.X7*steel_production.loc[year]['Total']*innovation_measures.loc[2]['OPEX']/1000)
    opex_R7 = (model.X8*steel_production.loc[year]['Total']*innovation_measures.loc[4]['OPEX']/1000)
    opex_CCS = (model.CCS*steel_production.loc[year]['Total']*innovation_measures.loc[6]['OPEX']/1000)
    
#    Emission mitigated considering energy efficiency measures and fuel shift
    Emission_mitigated_R1 = sum(model.X1[i]*mitigation_measures_dict['R1'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023'][x]/sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023'].values())*emission_factor.loc[x]['CO2e'] for x in EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023']) for i in k1)*production_R1/10**6
    Emission_mitigated_R2 = sum(model.X2[i]*mitigation_measures_dict['R2'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023'][x]/sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023'].values())*emission_factor.loc[x]['CO2e'] for x in EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023']) for i in k2)*production_R2/10**6
    Emission_mitigated_R3 = sum(model.X3[i]*mitigation_measures_dict['R3'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023'][x]/sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023'].values())*emission_factor.loc[x]['CO2e'] for x in EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023']) for i in k3)*production_R3/10**6
    Emission_mitigated_R4 = sum(model.X4[i]*mitigation_measures_dict['R4'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023'][x]/sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023'].values())*emission_factor.loc[x]['CO2e'] for x in EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023']) for i in k4)*production_R4/10**6

#Energy consumption of new measures              
    EC_R5_calc = +model.X5*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']
    EC_R6_calc = +model.X7*steel_production.loc[year]['Total']*innovation_measures.loc[2]['Energy_intensity (GJ/t)']
    EC_R7_calc = +model.X8*steel_production.loc[year]['Total']*innovation_measures.loc[4]['Energy_intensity (GJ/t)']
    
    EF_CCS = (1-0.8)*(innovation_measures.loc[7]['Energy_intensity (GJ/t)']*emission_factor.loc['Carvao metalurgico']['CO2e']
                 +innovation_measures.loc[8]['Energy_intensity (GJ/t)']*emission_factor.loc['Gas natural']['CO2e']
                 +innovation_measures.loc[9]['Energy_intensity (GJ/t)']*emission_factor.loc['Oleo combustivel']['CO2e']
                 ) #emission factor CO2e/t
    
    Unitario_preco_CCS = (innovation_measures.loc[6]['Energy_intensity (GJ/t)']*fuel_prices.loc['Eletricidade']['BRL/TJ']
                           +innovation_measures.loc[7]['Energy_intensity (GJ/t)']*fuel_prices.loc['Carvao metalurgico']['BRL/TJ']
                 +innovation_measures.loc[8]['Energy_intensity (GJ/t)']*fuel_prices.loc['Gas natural']['BRL/TJ']
                 +innovation_measures.loc[9]['Energy_intensity (GJ/t)']*fuel_prices.loc['Oleo combustivel']['BRL/TJ']
                 )
    
    #Energy consumption by route without energy efficiency measures:
    EC_R1_no_measure = (float(R1_EI_Total[year]))*production_R1
    EC_R2_no_measure=  (float(R2_EI_Total[year]))*production_R2
    EC_R3_no_measure=+(float(R3_EI_Total[year]))*production_R3
    EC_R4_no_measure= +(float(R4_EI_Total[year]))*production_R4
    
    Emission_Baseline = (
            (EC_R1_no_measure*sum(Energy_share_R1.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R1.index)/10**6
            +EC_R2_no_measure * sum(Energy_share_R2.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R2.index)/10**6
            +EC_R3_no_measure *sum(Energy_share_R3.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R3.index)/10**6
            +EC_R4_no_measure*sum(Energy_share_R4.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R4.index)/10**6)
            
            )
    
##    Fuel cost when applying mitigation measures: REFAZER
    #Acho que posso estar esquecendo de colocar o acréscimo do custo de combustíveis ao usar carvão vegetal
    #Energy saving = Penetration of a given technology * Reduction in GJ/t  * (energy share * fuel price) * production
    Energy_saving_R1 = sum(model.X1[i]*mitigation_measures_dict['R1'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023'][x]/sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023'].values())*fuel_prices.loc[x]['BRL/TJ'] for x in EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023']) for i in k1)*production_R1/10**6
    Energy_saving_R2 = sum(model.X2[i]*mitigation_measures_dict['R2'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023'][x]/sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023'].values())*fuel_prices.loc[x]['BRL/TJ'] for x in EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023']) for i in k2)*production_R2/10**6
    Energy_saving_R3 = sum(model.X3[i]*mitigation_measures_dict['R3'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023'][x]/sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023'].values())*fuel_prices.loc[x]['BRL/TJ'] for x in EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023']) for i in k3)*production_R3/10**6
    Energy_saving_R4 = sum(model.X4[i]*mitigation_measures_dict['R4'][i]['Energy reduction (Gj/t)']*sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023'][x]/sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023'].values())*fuel_prices.loc[x]['BRL/TJ'] for x in EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023']) for i in k4)*production_R4/10**6

    Energy_cost_innovation = (
            +(model.X5*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)'] + model.X7*steel_production.loc[year]['Total']*innovation_measures.loc[2]['Energy_intensity (GJ/t)']+model.CCS*steel_production.loc[year]['Total']*innovation_measures.loc[8]['Energy_intensity (GJ/t)'])*fuel_prices.loc['Gas natural']['BRL/TJ']/10**6
    +(model.X8*steel_production.loc[year]['Total']*innovation_measures.loc[4]['Energy_intensity (GJ/t)'])*fuel_prices.loc['Carvao vegetal']['BRL/TJ']/10**6
    +(model.X5*steel_production.loc[year]['Total']*innovation_measures.loc[1]['Energy_intensity (GJ/t)'] + model.X7*steel_production.loc[year]['Total']*innovation_measures.loc[3]['Energy_intensity (GJ/t)']+model.X8*steel_production.loc[year]['Total']*innovation_measures.loc[5]['Energy_intensity (GJ/t)']+model.CCS*steel_production.loc[year]['Total']*innovation_measures.loc[6]['Energy_intensity (GJ/t)'])*fuel_prices.loc['Eletricidade']['BRL/TJ']/10**6
    +model.CCS*innovation_measures.loc[7]['Energy_intensity (GJ/t)']*fuel_prices.loc['Carvao metalurgico']['BRL/TJ']*steel_production.loc[year]['Total']
    +model.CCS*innovation_measures.loc[9]['Energy_intensity (GJ/t)']*fuel_prices.loc['Oleo combustivel']['BRL/TJ']*steel_production.loc[year]['Total']
    )
  
#    Fuel economy: Fuel cost A - Fuel cost saving
    fuel_saving = (Energy_saving_R1+ Energy_saving_R2 + Energy_saving_R3+ Energy_saving_R4)
        
    fuel_cost = sum(EC_R1_no_measure*Energy_share_R1[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ']
    +EC_R2_no_measure*Energy_share_R2[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ']
    +EC_R3_no_measure*Energy_share_R3[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ']
    +EC_R4_no_measure*Energy_share_R4[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ'] for fuel in Energy_share_R1.index)/10**6
    
    levelized = interest_rate*((1+interest_rate)**20)/((1+interest_rate)**20-1)
    
    capex_total = (capex_R1 + capex_R2+capex_R3 + capex_R4 + capex_R5+ capex_R6+capex_R7+capex_CCS)*levelized
#    capex_total = (capex_R1+ capex_R2+capex_R3 + capex_R4 + capex_R5+ capex_R6+capex_R7+capex_CCS)*interest_rate*((1+interest_rate)**20)/((1+interest_rate)**20-1)
    opex_total =     opex_R1+opex_R2+opex_R3+opex_R4+opex_R5+opex_R6+opex_R7+opex_CCS

    model.obj= Objective(expr =(capex_total
                         +opex_total
                         +(fuel_cost+Energy_cost_innovation-fuel_saving)/dolar)
    )
    
    #Restrictions
    model.con = ConstraintList()
    
    ##Penetration
    for i in k1:
        model.con.add(model.X1[i] <= float(mitigation_measures_dict['R1'][i]['Penetration']))
    for i in k2:
        model.con.add (model.X2[i]<=float(mitigation_measures_dict['R2'][i]['Penetration']))
    for i in k3:
        model.con.add (model.X3[i]<=float(mitigation_measures_dict['R3'][i]['Penetration']))
    for i in k4:
        model.con.add (model.X4[i]<=float(mitigation_measures_dict['R4'][i]['Penetration']))
        
           
    model.con.add(model.X5<=innovation_measures.loc[0]['Penetration']) #NG
    # model.con.add(model.X5<=0.25) #NG in REF scenario
    model.con.add(model.X6+steel_production['Share_BOF_CC'][year]<=0.16) #charcoal limite
    model.con.add(model.X7<=penetration_inovative[str(year)]['DR-H2']) #H2
    model.con.add(model.X8<=penetration_inovative[str(year)]['SR']) #SR
    model.con.add(model.X8<=0.0) #SR
#    model.con.add(model.X9+steel_production['Share_EAF'][year]<=0.3) #EAF
#    model.con.add(model.X6+steel_production['Share_BOF_CC'][year]+model.X8<=0.50)
    model.con.add(model.X5+model.X6+model.X7+model.X8 +model.X9+model.CCS <= float(steel_production.loc[year]['Share_BOF_MC']))
    model.con.add(model.CCS<=penetration_inovative[str(year)]['BF-BOF-CCS'])
    

    if year ==2023:
        pass
    else:
        model.con.add((model.X5+model.X7)*steel_production['Total'][year]>=Results[year-1]['H2']*steel_production['Total'][year-1]+Results[year-1]['GN']*steel_production['Total'][year-1])
#        model.con.add(model.X8*steel_production['Total'][year]>=Results[year-1]['SR']*steel_production['Total'][year-1])


    #Add restriction to charcoal consumption    
    model.con.add(model.X8*steel_production.loc[year]['Total']*innovation_measures.loc[4]['Energy_intensity (GJ/t)'] 
+((EC_R1_no_measure*Energy_share_R1.loc['Carvao vegetal'][year]
            +EC_R2_no_measure *Energy_share_R2.loc['Carvao vegetal'][year]
            +EC_R3_no_measure *Energy_share_R3.loc['Carvao vegetal'][year]
            +EC_R4_no_measure*Energy_share_R4.loc['Carvao vegetal'][year]     
            )
        -(sum(model.X1[i]*mitigation_measures_dict['R1'][i]['Energy reduction (Gj/t)']*EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023']['Carvao vegetal']/sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023'].values()) for i in k1)*production_R1
    +sum(model.X2[i]*mitigation_measures_dict['R2'][i]['Energy reduction (Gj/t)']*EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023']['Carvao vegetal']/sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023'].values()) for i in k2)*production_R2
     +sum(model.X3[i]*mitigation_measures_dict['R3'][i]['Energy reduction (Gj/t)']*EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023']['Carvao vegetal']/sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023'].values()) for i in k3)*production_R3
    +sum(model.X4[i]*mitigation_measures_dict['R4'][i]['Energy reduction (Gj/t)']*EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023']['Carvao vegetal']/sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023'].values()) for i in k4)*production_R4
)
    )
        <= 576812*0.8)
        # <= 692750)
        #Potential is equal to 3 845 418 GJ // 449.280.000
    
    #Scrap consumption
    model.con.add((model.X9+steel_production['Share_EAF'][year])*steel_production.loc[year]['Total']*.85<= scrap_supply[str(year)]['High'])
    
    #exemplo de como posso fazer o calculo das emissoes
    def emission_calc_route (route):
        emission = 0
        for step in EI_dict[route].keys():
            emission = emission+sum(EI_dict[route][step]['2023'][f]*emission_factor.loc[f]['CO2e'] for f in EI_dict[route][step]['2023'].keys())
        return emission
    
    Emission_R1 = emission_calc_route('R1')
    Emission_R2 = emission_calc_route('R2')
    Emission_R3 = emission_calc_route('R3')
    Emission_R4 = emission_calc_route('R4')
    #Emission_R1 = sum(EI_dict['R1']['Alto-forno']['2023'][f]*emission_factor.loc[f]['CO2e'] for f in EI_dict['R1']['Alto-forno']['2023'].keys())

    #Tem que colocar o 5 e o 6 como redução das emissões.
    model.con.add(
            Emission_Baseline
            -(Emission_mitigated_R1
            +Emission_mitigated_R2
            +Emission_mitigated_R3
            +Emission_mitigated_R4)
            +EC_R5_calc*emission_factor.loc['Gas natural']['CO2e']/10**6
            +EC_R6_calc*emission_factor.loc['Gas natural']['CO2e']/10**6
            +EC_R7_calc*emission_factor.loc['Carvao vegetal']['CO2e']/10**6
            +model.CCS*EF_CCS*steel_production['Total'][year]/10**6
            -steel_production['Total'][year]*carbon_content*44/12/10**3
            ==emission
            )
    
    
    # Solving the problem:
    solver = SolverFactory('ipopt')
    result_solver = solver.solve(model, tee = True)
    
    CE =(
            EC_R1_no_measure()*Energy_share_R1[year]
            +EC_R2_no_measure()*Energy_share_R2[year]
            +EC_R3_no_measure()*Energy_share_R3[year]
            +EC_R4_no_measure*Energy_share_R4[year]
            )

    for fuel in CE.index:
        CE[fuel] = (CE[fuel]
        -sum(model.X1[i]()*mitigation_measures_dict['R1'][i]['Energy reduction (Gj/t)']*EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023'][fuel]/sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2023'].values()) for i in k1)*production_R1()
        -sum(model.X2[i]()*mitigation_measures_dict['R2'][i]['Energy reduction (Gj/t)']*EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023'][fuel]/sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]['Step']]['2023'].values())for i in k2)*production_R2()
        -sum(model.X3[i]()*mitigation_measures_dict['R3'][i]['Energy reduction (Gj/t)']*EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023'][fuel]/sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]['Step']]['2023'].values()) for i in k3)*production_R3()
        -sum(model.X4[i]()*mitigation_measures_dict['R4'][i]['Energy reduction (Gj/t)']*EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023'][fuel]/sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]['Step']]['2023'].values()) for i in k4)*production_R4
        )
#    
    #Summing the energy consumption from innovative measures (SR, H-DR, GN-DR, BF-BOF CCS:
    CE['Gas natural'] = (CE['Gas natural']
    +model.X5()*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)'] 
      + model.X7()*steel_production.loc[year]['Total']*innovation_measures.loc[2]['Energy_intensity (GJ/t)']
      + model.CCS()*steel_production.loc[year]['Total']*innovation_measures.loc[7]['Energy_intensity (GJ/t)']
      )
    
    CE['Eletricidade'] = (
            CE['Eletricidade']
            +model.X5()*steel_production.loc[year]['Total']*innovation_measures.loc[1]['Energy_intensity (GJ/t)'] 
            + model.X7()*steel_production.loc[year]['Total']*innovation_measures.loc[3]['Energy_intensity (GJ/t)']
            +model.X8()*steel_production.loc[year]['Total']*innovation_measures.loc[5]['Energy_intensity (GJ/t)']
            +model.CCS()*steel_production.loc[year]['Total']*innovation_measures.loc[6]['Energy_intensity (GJ/t)']
            )
    
    CE['Carvao vegetal'] = (
            CE['Carvao vegetal']
            +model.X8()*steel_production.loc[year]['Total']*innovation_measures.loc[4]['Energy_intensity (GJ/t)'])
    
    CE['Carvao metalurgico'] =(CE['Carvao metalurgico']
            +model.CCS()*steel_production.loc[year]['Total']*innovation_measures.loc[7]['Energy_intensity (GJ/t)']
    )
    
    CE['Oleo combustivel'] =(CE['Oleo combustivel'] 
    +model.CCS()*steel_production.loc[year]['Total']*innovation_measures.loc[9]['Energy_intensity (GJ/t)']
    )
    
    #Gerando resultado agregado do capex eficiência
    capex_eficiencia = (sum((mitigation_measures_dict['R1'][i]['CAPEX ($/t)'])*model.X1[i]()*production_R1/1000 for i in k1)
                        +sum((mitigation_measures_dict['R2'][i]['CAPEX ($/t)'])*model.X2[i]()*production_R2/1000 for i in k2)
                        +sum((mitigation_measures_dict['R3'][i]['CAPEX ($/t)'])*model.X3[i]()*production_R3/1000 for i in k3)
                        +sum((mitigation_measures_dict['R4'][i]['CAPEX ($/t)'])*model.X4[i]()*production_R4/1000 for i in k4)
                        )()*levelized
    
    opex_eficiencia = (sum((mitigation_measures_dict['R1'][i]['OPEX ($/t)'])*model.X1[i]()*production_R1/1000 for i in k1)
                         +sum((mitigation_measures_dict['R2'][i]['OPEX ($/t)'])*model.X2[i]()*production_R2/1000 for i in k2)
                         +sum((mitigation_measures_dict['R3'][i]['OPEX ($/t)'])*model.X3[i]()*production_R3/1000 for i in k3)
                         +sum((mitigation_measures_dict['R4'][i]['OPEX ($/t)'])*model.X4[i]()*production_R4/1000 for i in k4)
                         )()
    
    -fuel_saving() #Fuel saving da eficiencia

#mitigação das medidas de eficiência energética    
    mitigacao_eficiencia = (Emission_mitigated_R1
    +Emission_mitigated_R2
    +Emission_mitigated_R3
    +Emission_mitigated_R4)()

#Mitigação das rotas
        
    EI_R1 = ((EC_R1_no_measure*sum(Energy_share_R1.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R1.index)/10**6)() - Emission_mitigated_R1())/production_R1()*1000
    EI_R2 = ((EC_R2_no_measure*sum(Energy_share_R2.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R2.index)/10**6)() - Emission_mitigated_R2())/production_R2()*1000
    EI_R3 = ((EC_R3_no_measure*sum(Energy_share_R3.loc[f][year]*emission_factor.loc[f]['CO2e'] for f in Energy_share_R3.index)/10**6)() - Emission_mitigated_R3())/production_R3()*1000
    EI_R5 = EC_R5_calc()*emission_factor.loc['Gas natural']['CO2e']/10**6/production_R5() * 1000
    EI_R6 = 0 #é zero mesmo
    EI_R7 = EC_R7_calc()*emission_factor.loc['Carvao vegetal']['CO2e']/10**6/production_R7() * 1000

    R2_mitigacao = (EI_R1-EI_R2)*model.X6()*steel_production.loc[year]['Total']
    R3_mitigacao = (EI_R1-EI_R3)*model.X9()*steel_production.loc[year]['Total']
    R5_mitigacao = (EI_R1-EI_R5)*production_R5()
    R6_mitigacao = (EI_R1-EI_R6)*production_R6()
    R7_mitigacao = (EI_R1-EI_R7)*production_R7()
    
    mitigacao_total = mitigacao_eficiencia*1000 + R2_mitigacao + R3_mitigacao + R5_mitigacao + R6_mitigacao + R7_mitigacao
    
#Diferença do CAPEX    
    R2_capex_mitigacao = -(.170 -.170)*model.X6()*steel_production.loc[year]['Total']*levelized
    R3_capex_mitigacao = -(.170 -.184)*model.X9()*steel_production.loc[year]['Total']*levelized
    # (capex_R1()/production_R1() -capex_R4()/production_R4)*production_R4
    R5_capex_mitigacao = -(.170 -capex_R5()/production_R5())*production_R5()*levelized
    R6_capex_mitigacao = -(.170 -capex_R6()/production_R6())*production_R6()*levelized
    R7_capex_mitigacao = -(.170 -capex_R7()/production_R7())*production_R7()*levelized
       

#diferença do OPEX
    R2_opex_mitigacao = -(opex_R1()/production_R1() -opex_R2()/production_R2())*model.X6()*steel_production.loc[year]['Total']
    R3_opex_mitigacao = -(opex_R1()/production_R1() -opex_R3()/production_R3())*model.X9()*steel_production.loc[year]['Total']
    # (opex_R1()/production_R1() -opex_R4()/production_R4)*production_R4
    R5_opex_mitigacao = -(opex_R1()/production_R1() -opex_R5()/production_R5())*production_R5()
    R6_opex_mitigacao = -(opex_R1()/production_R1() -opex_R6()/production_R6())*production_R6()
    R7_opex_mitigacao = -(opex_R1()/production_R1() -opex_R7()/production_R7())*production_R7()

#Custos unitários de combustível
    custo_comb_R1 = (sum(EC_R1_no_measure*Energy_share_R1[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ'] for fuel in Energy_share_R1.index)/10**6)()/dolar/production_R1()
    # custo_comb_R1 = ((sum(EC_R1_no_measure*Energy_share_R1[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ'] for fuel in Energy_share_R1.index)/10**6)() - Energy_saving_R1())/dolar/production_R1()
    custo_comb_R2 = (sum(EC_R2_no_measure*Energy_share_R2[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ'] for fuel in Energy_share_R1.index)/10**6)()/dolar/production_R2()
    custo_comb_R3 = (sum(EC_R3_no_measure*Energy_share_R3[year][fuel]*fuel_prices.loc[fuel]['BRL/TJ'] for fuel in Energy_share_R1.index)/10**6)()/dolar/production_R3()
    custo_comb_R5 = (model.X5()*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']*fuel_prices.loc['Gas natural']['BRL/TJ']
                         +model.X5()*steel_production.loc[year]['Total']*innovation_measures.loc[1]['Energy_intensity (GJ/t)']*fuel_prices.loc['Eletricidade']['BRL/TJ'])/10**6/dolar/production_R5()
    custo_comb_R6 = (model.X7()*steel_production.loc[year]['Total']*innovation_measures.loc[2]['Energy_intensity (GJ/t)']*fuel_prices.loc['Gas natural']['BRL/TJ']
                         +model.X7()*steel_production.loc[year]['Total']*innovation_measures.loc[3]['Energy_intensity (GJ/t)']*fuel_prices.loc['Eletricidade']['BRL/TJ'])/10**6/dolar/production_R6()
    custo_comb_R7 = (model.X8()*steel_production.loc[year]['Total']*innovation_measures.loc[4]['Energy_intensity (GJ/t)']*fuel_prices.loc['Carvao vegetal']['BRL/TJ']
                         +model.X8()*steel_production.loc[year]['Total']*innovation_measures.loc[5]['Energy_intensity (GJ/t)']*fuel_prices.loc['Eletricidade']['BRL/TJ'])/10**6/dolar/production_R7()
    
    R2_economia_comb = (custo_comb_R2-custo_comb_R1)*model.X6()*steel_production.loc[year]['Total']
    R3_economia_comb = (custo_comb_R3-custo_comb_R1)*model.X9()*steel_production.loc[year]['Total']
    R5_economia_comb = (custo_comb_R5-custo_comb_R1)*production_R5()
    R6_economia_comb = (custo_comb_R6-custo_comb_R1)*production_R6()
    R7_economia_comb = (custo_comb_R7-custo_comb_R1)*production_R7()

    
    mitigacao = {
        'Capex':{
            'Carvao vegetal':R2_capex_mitigacao,
            'EAF': R3_capex_mitigacao,
            'DR-GN': R5_capex_mitigacao,
            'DR-H2': R6_capex_mitigacao,
            'SR-CV' : R7_capex_mitigacao,
            'Eficiencia':capex_eficiencia
            },
        'Opex':{
            'Carvao vegetal':R2_opex_mitigacao,
            'EAF': R3_opex_mitigacao,
            'DR-GN': R5_opex_mitigacao,
            'DR-H2': R6_opex_mitigacao,
            'SR-CV' : R7_opex_mitigacao,
            'Eficiencia': opex_eficiencia
            },
        'Gasto comb':{
            'Carvao vegetal':R2_economia_comb,
            'EAF': R3_economia_comb,
            'DR-GN': R5_economia_comb,
            'DR-H2': R6_economia_comb,
            'SR-CV' : R7_economia_comb,
            'Eficiencia' : -fuel_saving()/1000
            },
        'Mitigacao':{
            'Carvao vegetal':R2_mitigacao,
            'EAF': R3_mitigacao,
            'DR-GN': R5_mitigacao,
            'DR-H2': R6_mitigacao,
            'SR-CV' : R7_mitigacao,
            'Eficiencia' : mitigacao_eficiencia*1000
            }
        }
        
        
        
    return model,capex_total,CE ,mitigacao , opex_total

#%%
"""Future emissions, costs and energy consumption"""
# Criar os anos como índices
anos = list(range(2023, 2051))

Emission_reduction = pd.DataFrame(data = np.linspace(1,0.70,28),index= anos)
Emission_reduction = Emission_reduction[0].to_dict()

Emission_base = pd.DataFrame(data = np.linspace(1,1,28),index= anos)
Emission_base = Emission_base[0].to_dict()

Results = pd.DataFrame(columns = anos,index = [
    'Cost Decarbonization' ,'Cost reference','Emission base','Emissions','Capex_decarb','Capex_bau','Opex_decarb','Opex_bau','Fuel_saving','BF-BOF','GN','CV','H2','SR','EAF','BF-BOF CCS'],
    data= 0,
    dtype=float)

X1 = pd.DataFrame(columns = anos, index =  mitigation_measures_dict['R1'].keys(),data= 0,dtype=float)
X2 = pd.DataFrame(columns = anos, index =  mitigation_measures_dict['R2'].keys(),data= 0,dtype=float)
CE_mit = pd.DataFrame(columns = anos,index =Energy_share_R1.index,data=0, dtype=float )
CE_ref =  pd.DataFrame(columns = anos,index =Energy_share_R1.index,data=0, dtype=float )

#Criando dataframe para os resultados da MAC Definir os níveis das colunas
primeiro_nivel = ['Carvao vegetal', 'EAF', 'DR-GN', 'DR-H2', 'SR-CV', 'Eficiencia']
segundo_nivel = ['Capex', 'Opex', 'Gasto comb', 'Mitigacao']

# Criar um MultiIndex para as colunas
colunas = pd.MultiIndex.from_product([primeiro_nivel, segundo_nivel])

# Criar o DataFrame preenchido com zeros
mitigacao_df = pd.DataFrame(0, index=anos, columns=colunas)

for i in Emission_reduction:
    y,capex_total2,CE_2,mitigacao_2,opex2= optimization_module(i,emission_calc(i))
    Results[i]['Cost reference']=float(y.obj())
    Results[i]['Capex_bau']=capex_total2()
    Results[i]['Opex_bau']=opex2()
    CE_ref[i] = CE_2

#Gerando resultados
for i in Emission_reduction:
    x,capex_total,CE_1,mitigacao,opex= optimization_module(i,emission_calc(i)*Emission_reduction[i]) 
#    
    Results[i]['Cost Decarbonization'] = float(x.obj())    
#    Results[i]['Cost reference']=float(y.obj())
    Results[i]['Emissions'] = emission_calc(i)*Emission_reduction[i]
#    Results[i]['Emissions'] = emission_calc(i)
    Results[i]['Emission base'] = emission_calc(i)
    Results[i]['Capex_decarb'] = capex_total()
    Results[i]['Opex_decarb'] = opex()
    Results.loc['BF-BOF'][i] = 1-(x.X5()+x.X6()+steel_production['Share_BOF_CC'][i]+x.X7()+x.X8()+x.X9()+steel_production['Share_EAF'][i]+x.CCS())
    Results.loc['GN'][i]= float(x.X5())
    Results.loc['CV'][i]= x.X6()+steel_production['Share_BOF_CC'][i]
    Results.loc['H2'][i]= x.X7()
    Results.loc['SR'][i]=x.X8()
    Results.loc['EAF'][i]=x.X9() +steel_production['Share_EAF'][i]
    Results.loc['BF-BOF CCS'][i]=x.CCS()
    CE_mit[i] = CE_1
    
    X1[i] =x.X1[:]()
    X2[i]=x.X2[:]()
    
    for tecnologia in primeiro_nivel:
        for parametro in segundo_nivel:
            valor = mitigacao[parametro][tecnologia]
            
            # Substituir NaN por zero
            if pd.isna(valor):
                valor = 0
            
            mitigacao_df.loc[i, (tecnologia, parametro)] = valor


    mitigacao_df.loc[i,('Eficiencia','Gasto comb')] = (
                                                       +((Results[i]['Cost Decarbonization'] - Results[i]['Cost reference']) 
                                                         - (Results[i]['Capex_decarb'] - Results[i]['Capex_bau']) 
                                                         - (Results[i]['Opex_decarb'] - Results[i]['Opex_bau'])
                                                         -sum(mitigacao_df.loc[i, ( tecnologia, 'Gasto comb')] for tecnologia in primeiro_nivel if tecnologia != 'Eficiencia')
                                                         )
                                                       )

lista_comb = [item for item in CE_mit.index if item != "Total"]
lista_comb_processo = ['Coque de carvao mineral','Carvao vegetal','Carvao metalurgico']
lista_comb_energia = [item for item in lista_comb if item not in lista_comb_processo]

emissoes_gas_processo = pd.DataFrame(data = 0, index = ['CO2','CH4', 'N2O'], columns = CE_mit.columns)
emissoes_gas_energia = pd.DataFrame(data = 0, index = ['CO2','CH4', 'N2O'], columns = CE_mit.columns)

for year in CE_mit.columns:

    co2 = (sum(CE_mit[year][fuel]*emission_factor.loc[fuel]['CO2'] for fuel in lista_comb_processo)/10**6
           +Results.loc['GN'][year]*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']*emission_factor.loc['Gas natural']['CO2']/10**6
           -steel_production['Total'][year]*carbon_content*44/12/10**3
           )
    ch4 = (sum(CE_mit[year][fuel]*emission_factor.loc[fuel]['CH4'] for fuel in lista_comb_processo)/10**6
           +Results.loc['GN'][year]*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']*emission_factor.loc['Gas natural']['CH4']/10**6
           )
    
    n2o = (sum(CE_mit[year][fuel]*emission_factor.loc[fuel]['N2O'] for fuel in lista_comb_processo)/10**6
           +Results.loc['GN'][year]*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']*emission_factor.loc['Gas natural']['N2O']/10**6
           )
    
    emissoes_gas_processo[year]['CO2'] = co2
    emissoes_gas_processo[year]['CH4'] = ch4
    emissoes_gas_processo[year]['N2O'] = n2o
    
for year in CE_mit.columns:

    co2 = (sum (CE_mit[year][fuel]*emission_factor.loc[fuel]['CO2'] for fuel in lista_comb_energia)/10**6
           -Results.loc['GN'][year]*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']*emission_factor.loc['Gas natural']['CO2']/10**6
           )
    
    ch4 = (sum (CE_mit[year][fuel]*emission_factor.loc[fuel]['CH4'] for fuel in lista_comb_energia)/10**6
           -Results.loc['GN'][year]*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']*emission_factor.loc['Gas natural']['CH4']/10**6
           )
    
    n2o = (sum (CE_mit[year][fuel]*emission_factor.loc[fuel]['N2O'] for fuel in lista_comb_energia)/10**6
           -Results.loc['GN'][year]*steel_production.loc[year]['Total']*innovation_measures.loc[0]['Energy_intensity (GJ/t)']*emission_factor.loc['Gas natural']['N2O']/10**6
           )
    
    emissoes_gas_energia[year]['CO2'] = co2
    emissoes_gas_energia[year]['CH4'] = ch4
    emissoes_gas_energia[year]['N2O'] = n2o

#Adicionando os anos antigos
for year in Energy_consumption_BEN.columns[10:-1]:
    CE_mit[year] = Energy_consumption_BEN[year]*ktoe_to_tj

CE_mit = CE_mit.sort_index(axis=1)
#%%
"""Exporting values to excel"""

import os
from openpyxl import load_workbook

# Specify the output directory and file path
output_directory = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/'
##output_filename = 'Energia_50%.xlsx'
#excel_file = pd.ExcelFile(file_path)
#
#writer = pd.ExcelWriter(file_path)

tab_name = 'Steel'

# Define the Excel file name
excel_file = 'Energia_Imagine_MIT1_V1.xlsx'

# Function to save DataFrame to a specific sheet in an Excel file
def save_to_excel(df, file_path, sheet_name):
    # Check if file exists
    if os.path.exists(file_path):
        # Open the file in write mode, and overwrite the sheet if it exists
        with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)
    else:
        # Create a new Excel file with the given sheet name
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)

# Path to the Excel file
# file_path = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/Energia_Imagine_CPS_V0.xlsx'
file_path = output_directory + excel_file
save_to_excel(CE_mit/ktoe_to_tj, file_path, tab_name)
    
"""Custos"""
# Define the Excel file name
excel_file = 'Custos_Imagine_MIT1_V1.xlsx'

# Specify the output directory and file path
output_directory = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/'

# Function to save DataFrame to a specific sheet in an Excel file
def save_to_excel(df, file_path, sheet_name):
    # Check if file exists
    if os.path.exists(file_path):
        # Open the file in write mode, and overwrite the sheet if it exists
        with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)
    else:
        # Create a new Excel file with the given sheet name
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)

# Path to the Excel file
# file_path = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/Energia_Imagine_CPS_V0.xlsx'
file_path = output_directory + excel_file
save_to_excel(Results, file_path, tab_name)

"""Custos de mitigacao"""
# Define the Excel file name
excel_file = 'MAC_Imagine_MIT1_V1.xlsx'

# Specify the output directory and file path
output_directory = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/'

# Function to save DataFrame to a specific sheet in an Excel file
def save_to_excel(df, file_path, sheet_name):
    # Check if file exists
    if os.path.exists(file_path):
        # Open the file in write mode, and overwrite the sheet if it exists
        with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)
    else:
        # Create a new Excel file with the given sheet name
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)

# Path to the Excel file
# file_path = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/Energia_Imagine_CPS_V0.xlsx'
file_path = output_directory + excel_file
save_to_excel(mitigacao_df, file_path, tab_name)

"""Emissões"""
# Define the Excel file name
excel_file = 'EmissoesEnergia_Imagine_MIT1_V1.xlsx'

# Specify the output directory and file path
output_directory = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/'

# Function to save DataFrame to a specific sheet in an Excel file
def save_to_excel(df, file_path, sheet_name):
    # Check if file exists
    if os.path.exists(file_path):
        # Open the file in write mode, and overwrite the sheet if it exists
        with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)
    else:
        # Create a new Excel file with the given sheet name
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=True)

# Path to the Excel file
# file_path = 'C:/Users/ottoh/OneDrive/Doutorado/Tese/Resultados/Imagine/Energia_Imagine_CPS_V0.xlsx'
file_path = output_directory + excel_file
save_to_excel(emissoes_gas_energia, file_path, tab_name)

excel_file = 'EmissoesProcesso_Imagine_MIT1_V1.xlsx'
file_path = output_directory + excel_file
save_to_excel(emissoes_gas_processo, file_path, tab_name)
#%% 
    
"""Creating a Cost Curve for the Steel industry"""
#
#cost_curve = pd.DataFrame(columns = ['Cost'],index = np.linspace(0.99,0.40,20),data = 0, dtype=float)
#emission_mitigated = pd.DataFrame(columns = ['Emission mitigated'], index = np.linspace(0.99,0.40,20), data = 0, dtype = float)
#
#for i in np.linspace(0.99,0.4,20):
#    x= optimization_module(2020,emission_calc(2020)*i)
#    emission_mitigated.loc[i] = emission_calc(2020)-emission_calc(2020)*i
#    cost_curve.loc[i] = float(x.obj())/float(emission_mitigated.loc[i])
#
#plt.plot(emission_mitigated, cost_curve)
    

#for step in EI_dict['R1'].keys():
#    for measure in mitigation_measures_dict['R1']:
#        if  step == mitigation_measures_dict['R1'][measure]['Step']:
#            print(measure,mitigation_measures_dict['R1'][measure]['Step'],step == mitigation_measures_dict['R1'][measure]['Step'])
#        else:
#            pass
#        
#for i in k1:
#    for x in EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2020']:
#        EI_dict['R1'][mitigation_measures_dict['R1'][i]['Step']]['2020'][x] *=1-model.X1()*mitigation_measures_dict['R1'][i]['Energy reduction (Gj/t)']
        
        