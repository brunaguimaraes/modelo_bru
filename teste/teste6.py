# -*- coding: utf-8 -*-
"""
Created on Fri May 30 15:20:18 2025

@author: Bruna

Teste recomendado pelo Otto:
Inventar duas plantas. Cada uma com vida útil diferente: 30 e 35.
Dar duas opções de mitigação, com valores genéricos
Tentar fazer um código que reduza x% das emissões.
Usar Consumo energético da planta das principais fontes (eletricidade, carvão, etc), emissão e produção
CSA tem capacidade de produção x, uma geração.
Parâmetro genérico do Rafael e Pinto.
Não olhar pra mil medidas de eficiência energética, apenas para novas rotas tecnológicas.




Cheguei a conclusão que não quero parar em 2019, como eu estava prevendo. Quero fazer como o otto de ir até 2024. 
preciso rever isso ao longo de todo o modelo e tambem dos dados históricos.


entao meu current year deixa de ser 2019 e passa a ser 2024, conferir depois



eu parei na metade! quando parece que vai dar certo, começa a dar errado de novo. no final das contas pras
 plantas individuais eu só tenho dados de 2019. já pras outras coisas o otto tinha feito de 2005 pra frente eu acho. 
 vo ter q rever todo o codigo dele inicial,



    For a givining Year and emission goal, the function will return mitigation measures, energyintensity, 
    energy consumption, costs
R1 = Route BOF using Coal
R2 = Route BOF using Charcoal
R3 = Route EAF using scrap
R4 = Route Independet producers 
"""

import pandas as pd
import numpy as np


# ===== Integrando vida útil de plantas ao modelo de otimização =====

# 1) Carregar dados de plantas existentes (arquivo Excel com colunas: plant_id, route, capacity, remaining_life)
plants = pd.read_excel('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/teste/plants_teste.xlsx')  

# Ano base do seu script
current_year = 2023
# Horizon decenal:
future_years = list(range(current_year+1, 2051))  # 2023 a 2050 - future_years é simplesmente uma lista Python dos anos seguintes em que seu modelo vai instalar plantas, produzir e mitigar emissões.
routes = ['BF-BOF', 'EAF', 'R3', 'R4']
"""verificar os nomes das ROTAAAASSS"""
"""verificar os nomes das ROTAAAASSS"""
"""verificar os nomes das ROTAAAASSS"""

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


#%%
### inserindo mais dados históricos de produção
### inserindo mais dados históricos de produção conforme modelagem do Otto
### inserindo mais dados históricos de produção

"""Importing Crude Steel production by route in kt"""
steel_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/C:/Users/Bruna/Desktop/steel_production_v2') #in kt
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

#%%
"""Energy intensity of each route"""
R1_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R1'].iloc[:,2:].sum()
R1_EI_Total.index = R1_EI_Total.index.astype(int)
R2_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R2'].iloc[:,2:].sum()
R2_EI_Total.index = R2_EI_Total.index.astype(int)
R3_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R3'].iloc[:,2:].sum()
R3_EI_Total.index = R3_EI_Total.index.astype(int)
R4_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R4'].iloc[:,2:].sum()
R4_EI_Total.index = R4_EI_Total.index.astype(int)
       
#%%        
"""Energy Consumption"""


#R1 Energy Consumption:
R1_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'], dtype=float)
for ano in past_years:
    R1_EC_Total.loc[ano] = R1_EI_Total.loc[ano]*steel_production['BOF MC'][ano]

#R2 Energy_consumption:
R2_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'],  dtype=float)
for ano in past_years:
    R2_EC_Total.loc[ano] = R2_EI_Total.loc[ano]*steel_production['BOF CC'][ano]

#R3_Energy_Cosumption:
R3_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'], dtype=float)
for ano in past_years:
    R3_EC_Total.loc[ano] = R3_EI_Total.loc[ano]*steel_production['EAF'][ano]

#R4_Energy_Consumption:
R4_EC_Total = pd.DataFrame(index = R1_EI_Total.index, columns = ['Energy_Consumption'], dtype=float)
for ano in past_years:
    R4_EC_Total.loc[ano] = R4_EI_Total.loc[ano]*pig_iron_production['Independente CV'][ano]     
    
#%%     
"""Energy Consumption By Fuel"""
#This function calculates the energy consumption by fuel.
def energy_consumption(Rota):
    """estimates the energy consumption using the Energy Intensity and the production"""
    
    EC_Total = pd.DataFrame(index = EI_BEU.index, columns = EI_BEU.columns, dtype=float)
    EC_Total.Rota = EI_BEU.Rota
    EC_Total.Combustivel = EI_BEU.Combustivel
  #######  EC_Total.Step = EI_BEU.Step  - removi isso porue não me interessam mais as etapas.
    
    #Energy consumption in R1:
    if Rota =='R1':      
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R1'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF MC'][int(ano)] 
            
    #Energy consumption in R2
    if Rota =='R2' :       
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R2'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF CC'][int(ano)]       
            
            #Energy consumption in R3   
    if Rota == 'R3':
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R3'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['EAF'][int(ano)]  
            
            #Energy consumption in R4
    if Rota == 'R4':
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R4'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*pig_iron_production['Independente CV'][int(ano)]     
                
    if Rota == 'todas':
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R1'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF MC'][int(ano)] 
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R2'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['BOF CC'][int(ano)]                     
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R3'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*steel_production['EAF'][int(ano)]  
        for ano in EI_BEU.columns[2:]:
            for indice in EC_Total.loc[EC_Total['Rota']=='R4'].index:
                EC_Total.loc[indice,str(ano)] = EI_BEU.loc[indice,str(ano)]*pig_iron_production['Independente CV'][int(ano)]     
                
    return EC_Total

#Energy consumption without calibration
Total_energy_consumption_R1 = energy_consumption('R1').groupby(['Combustivel'], as_index = False).sum()
Total_energy_consumption_R2 = energy_consumption('R2').groupby(['Combustivel'], as_index = False).sum()
Total_energy_consumption_R3 = energy_consumption('R3').groupby(['Combustivel'], as_index = False).sum()
Total_energy_consumption_R4 = energy_consumption('R4').groupby(['Combustivel'], as_index = False).sum()
Total_energy_consumption = energy_consumption('todas').groupby(['Combustivel'], as_index = False).sum()

#%%
"""Adjustments for the energy consumption'"""

#Matching the Energy Intensity of each fuel, route and step to the energy consumption in the Energy Balance
for combustivel in Total_energy_consumption['Combustivel']:
    for ano in past_years:
        for i in EI_BEU.loc[EI_BEU['Combustivel'] == combustivel].index:
            EI_BEU.loc[i, str(ano)] = (
                EI_BEU.loc[i, str(ano)] * 
                Energy_consumption_BEN_Gj.loc[combustivel, ano] / 
                float(Total_energy_consumption.loc[Total_energy_consumption['Combustivel'] == combustivel, str(ano)].values[0])
            )
            
  #%%          
"""Creating dictionary"""


EI_dict = {}

for Rota in pd.unique(EI_BEU['Rota']):
    # Filtra todas as linhas da rota atual
    df_rota = EI_BEU.loc[EI_BEU['Rota'] == Rota]
    
    # Remove a coluna 'Rota' para não duplicar informação
    df_rota = df_rota.drop(columns=['Rota'])
    
    # Define 'Combustivel' como índice para a conversão
    df_rota = df_rota.set_index('Combustivel')
    
    # Converte para dicionário (será um dict de colunas contendo dicts de combustíveis e valores)
    rota_dict = df_rota.to_dict()
    
    # Salva no dicionário principal com chave sendo a rota
    EI_dict[Rota] = rota_dict



#%%
"""Energy intensity of each routes ajdusted """
R1_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R1'].iloc[:,3:].sum()
R1_EI_Total.index = R1_EI_Total.index.astype(int)
R2_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R2'].iloc[:,3:].sum()
R2_EI_Total.index = R2_EI_Total.index.astype(int)
R3_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R3'].iloc[:,3:].sum()
R3_EI_Total.index = R3_EI_Total.index.astype(int)
R4_EI_Total = EI_BEU.loc[EI_BEU['Rota'] == 'R4'].iloc[:,3:].sum()
R4_EI_Total.index = R4_EI_Total.index.astype(int)


#%%

"""Energy share by routes"""

#Energy consumption after calibration;
Total_energy_consumption_R1 = energy_consumption('R1').groupby(['Combustivel'], as_index = False).sum()
Total_energy_consumption_R2 = energy_consumption('R2').groupby(['Combustivel'], as_index = False).sum()
Total_energy_consumption_R3 = energy_consumption('R3').groupby(['Combustivel'], as_index = False).sum()
Total_energy_consumption_R4 = energy_consumption('R4').groupby(['Combustivel'], as_index = False).sum()

#Creating Energy Share DataFrame by routes
Energy_share_R1 = Total_energy_consumption_R1.set_index('Combustivel').drop(columns=['Rota'])
Energy_share_R2 = Total_energy_consumption_R2.set_index('Combustivel').drop(columns=['Rota'])
Energy_share_R3 = Total_energy_consumption_R3.set_index('Combustivel').drop(columns=['Rota'])
Energy_share_R4 = Total_energy_consumption_R4.set_index('Combustivel').drop(columns=['Rota'])

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
    Energy_share_R1[i]=Energy_share_R1[current_year]
    Energy_share_R2[i]=Energy_share_R2[current_year]
    Energy_share_R3[i]=Energy_share_R3[current_year]
    Energy_share_R4[i]=Energy_share_R4[current_year]

#Energy Intensity for future years
for i in future_years:
    R1_EI_Total[i] = R1_EI_Total[current_year]
    R2_EI_Total[i] = R2_EI_Total[current_year]
    R3_EI_Total[i] = R3_EI_Total[current_year]
    R4_EI_Total[i] = R4_EI_Total[current_year]
    
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
        steel_production.loc[ano, coluna] = float(steel_production.loc[current_year, coluna] * Production_increase[ano])

colunas = ['Integrada CM','Integrada CV','Independente CV']    
for coluna in colunas:
    for ano in [2025, 2030, 2035, 2040, 2045, 2050]:
        pig_iron_production.loc[ano, coluna] = float(pig_iron_production.loc[current_year, coluna] * Production_increase[ano])
    
steel_production.loc[2050, 'Share_BOF_MC'] = steel_production.loc[current_year, 'Share_BOF_MC']
steel_production.loc[2050, 'Share_BOF_CC'] = steel_production.loc[current_year, 'Share_BOF_CC']
steel_production.loc[2050, 'Share_EAF'] = steel_production.loc[current_year, 'Share_EAF']
pig_iron_production.loc[2050, 'Share BOF CC'] = pig_iron_production.loc[current_year, 'Share BOF CC']
pig_iron_production.loc[2050, 'Share BOF MC'] = pig_iron_production.loc[current_year, 'Share BOF MC']

steel_production = steel_production.interpolate()
pig_iron_production= pig_iron_production.interpolate()


#%%
### inserindo informações sobre as medidas de mitigação
### inserindo informações sobre as medidas de mitigação conforme modelagem do Otto
### inserindo informações sobre as medidas de mitigação


"""Importing Mitigation measures:"""

mitigation_measures = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Iron_and_steel_mitigation_measures_V2.csv')
mitigation_measures['Total Reduction GJ/t'] = mitigation_measures['Energy reduction (Gj/t)']*mitigation_measures.Penetration

#lifetime of mitigation measures:
life_time = 20 #years
mitigation_measures_dict = {}
for route in pd.unique(mitigation_measures.Route):
    mitigation = (
        mitigation_measures
        .loc[mitigation_measures['Route'] == route]
        .set_index('Mitigation measure')
        .drop(['Route'], axis=1)
        .transpose()
        .to_dict()
    )
mitigation_measures_dict[route] = mitigation
        
    #teste = mitigation_measures.loc[mitigation_measures['Route']==route].set_index('Mitigation measure').drop(['Route'],axis = 1).transpose().to_dict()


# Calcula o somatório total de redução por Route (independente do Step)
total_reduction_by_route = mitigation_measures.groupby('Route')['Total Reduction GJ/t'].transform('sum')

# Adiciona coluna com percentual de redução de cada linha dentro do respectivo Route
mitigation_measures['Percentual of reduction'] = (
    mitigation_measures['Total Reduction GJ/t'] / total_reduction_by_route
)
   
     
     
        
innovation_measures = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Innovation_measures_2.csv')

penetration_inovative = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Penetration_innovative.csv')
penetration_inovative = penetration_inovative.set_index('Technology')
#Essa etapa do penetration_inovative:
    #Lê um arquivo de limites máximos permitidos (por ano, por tecnologia de ponta/innovativa).
    #Reestrutura para que a busca desses limites seja por nome da tecnologia (como índice).
    #Essa tabela será usada como restrição, dentro do otimizador, para impedir que inovações sejam adotadas antes do tempo/pleno mercado.

"""Importing Fuel prices"""
fuel_prices = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/Fuel_price_3.csv')
#fuel_prices['BRL/TJ'] = fuel_prices['BRL/ktep']/ktoe_to_tj 
fuel_prices = fuel_prices.set_index('﻿Combustivel')
#fuel_prices.loc['Gas natural'] =fuel_prices.loc['Gas natural']/20

"""interest rate"""
interest_rate = 0.08


#%%



#até aqui parece que está tudo certo


#%%
#Optimization
#Creating model
#def optimization_module(year,emission):
""""For a givining Year and emission goal, the function will return mitigation measures, energy intensity, energy consumption, costs
    R1 = Route BOF using Coal
    R2 = Route BOF using Charcoal
    R3 = Route EAF using scrap
    R4 = Route Independet producers 
"""
from pyomo.environ import ConcreteModel, Var, NonNegativeReals
def optimization_module(year, emission):
    model = ConcreteModel()
         
    # variáveis absolutas de produção por rota no ano dado
    model.prod_R1 = Var(within=NonNegativeReals)
    model.prod_R2 = Var(within=NonNegativeReals)
    model.prod_R3 = Var(within=NonNegativeReals)
    model.prod_R4 = Var(within=NonNegativeReals)
    model.prod_R5 = Var(within=NonNegativeReals)
    model.prod_R6 = Var(within=NonNegativeReals)
    model.prod_R7 = Var(within=NonNegativeReals)
    model.prod_CCS = Var(within=NonNegativeReals)

    """R1  #Energy efficiency mitigation measure in Route 1 (Route BOF using Coal)
    R2  #Energy efficiency mitigation measure in Route 2 (Route BOF using Charcoal)
    R3  #Energy efficiency mitigation measure in Route 3 (Route EAF using scrap)
    R4  #Energy efficiency mitigation measure in Route 4 (Route Independet producers )
    R5  #DR-NG
    R6  #Charcoal share
    R7  #DR-H2 share
    R8  #Smelting Reduction share
    R9  #EAF
    CCS #CCS in BF
    """
    
    # capacidade nova instalada (variável de decisão)
    model.newcap_R1 = Var(within=NonNegativeReals)
    model.newcap_R2 = Var(within=NonNegativeReals)
    model.newcap_R3 = Var(within=NonNegativeReals)
    model.newcap_R4 = Var(within=NonNegativeReals)
    model.newcap_R5 = Var(within=NonNegativeReals)
    model.newcap_R6 = Var(within=NonNegativeReals)
    model.newcap_R7 = Var(within=NonNegativeReals)
    model.newcap_CCS = Var(within=NonNegativeReals)
    
    # Restrição de capacidade: só pode produzir até o máximo daquela rota (existente + nova capacidade instalada) naquele ano:
    model.con.add(model.prod_R1 <= cap_exist['R1'][year] + model.newcap_R1)
    model.con.add(model.prod_R2 <= cap_exist['R2'][year] + model.newcap_R2)
    model.con.add(model.prod_R3 <= cap_exist['R3'][year] + model.newcap_R3)
    model.con.add(model.prod_R4 <= cap_exist['R4'][year] + model.newcap_R4)
    model.con.add(model.prod_R5 <= cap_exist['R5'][year] + model.newcap_R5)
    model.con.add(model.prod_R6 <= cap_exist['R6'][year] + model.newcap_R6)
    model.con.add(model.prod_R7 <= cap_exist['R7'][year] + model.newcap_R7)
    model.con.add(model.prod_CCS <= cap_exist['CCS'][year] + model.newcap_CCS)
    
    # Fechamento: ATENDER toda demanda naquele ano:
    model.con.add(model.prod_R1 + model.prod_R2 + model.prod_R3 + model.prod_R4 + model.prod_R5 + model.prod_R6 + model.prod_R7 + model.prod_R8 + model.prod_R9 + model.prod_CCS == steel_production.loc[year]['Total'])
    
    
    
    #Creating mitigation measures varieables variables
    k1 = mitigation_measures_dict['R1'].keys() #list of the number of energy mitigation measures
    k2 = mitigation_measures_dict['R2'].keys()
    k3 = mitigation_measures_dict['R3'].keys()
    k4 =  mitigation_measures_dict['R4'].keys()
    
    # produção de inovações
    model.X1 =  Var (k1,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 1
    model.X2 =  Var (k2,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 2
    model.X3 =  Var (k3,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 3
    model.X4 =  Var (k4,within =NonNegativeReals) #Energy efficiency mitigation measure in Route 4
    
    
    
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
    
    
#Restrictions
model.con = ConstraintList()
    
#Penetration
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
        -(sum(model.X1[i]*mitigation_measures_dict['R1'][i]['Energy reduction (Gj/t)']*EI_dict['R1'][mitigation_measures_dict['R1'][i]]['2023']['Carvao vegetal']/sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]]['2023'].values()) for i in k1)*production_R1
    +sum(model.X2[i]*mitigation_measures_dict['R2'][i]['Energy reduction (Gj/t)']*EI_dict['R2'][mitigation_measures_dict['R2'][i]]['2023']['Carvao vegetal']/sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]]['2023'].values()) for i in k2)*production_R2
     +sum(model.X3[i]*mitigation_measures_dict['R3'][i]['Energy reduction (Gj/t)']*EI_dict['R3'][mitigation_measures_dict['R3'][i]]['2023']['Carvao vegetal']/sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]]['2023'].values()) for i in k3)*production_R3
    +sum(model.X4[i]*mitigation_measures_dict['R4'][i]['Energy reduction (Gj/t)']*EI_dict['R4'][mitigation_measures_dict['R4'][i]]['2023']['Carvao vegetal']/sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]]['2023'].values()) for i in k4)*production_R4
)
    )
        <= 576812*0.8)
        # <= 692750)
        #Potential is equal to 3 845 418 GJ // 449.280.000
    
    #Scrap consumption
    model.con.add((model.X9+steel_production['Share_EAF'][year])*steel_production.loc[year]['Total']*.85<= scrap_supply[str(year)]['High'])
    
    #exemplo de como posso fazer o calculo das emissoes
    def emission_calc_route(route):
        # Agora pega só os combustíveis do ano 2023 da rota, sem step
        return sum(EI_dict[route]['2023'][f]*emission_factor.loc[f]['CO2e'] for f in EI_dict[route]['2023'].keys())
    
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
        -sum(model.X1[i]()*mitigation_measures_dict['R1'][i]['Energy reduction (Gj/t)']*EI_dict['R1'][mitigation_measures_dict['R1'][i]]['2023'][fuel]/sum(EI_dict['R1'][mitigation_measures_dict['R1'][i]]['2023'].values()) for i in k1)*production_R1()
        -sum(model.X2[i]()*mitigation_measures_dict['R2'][i]['Energy reduction (Gj/t)']*EI_dict['R2'][mitigation_measures_dict['R2'][i]]['2023'][fuel]/sum(EI_dict['R2'][mitigation_measures_dict['R2'][i]]['2023'].values())for i in k2)*production_R2()
        -sum(model.X3[i]()*mitigation_measures_dict['R3'][i]['Energy reduction (Gj/t)']*EI_dict['R3'][mitigation_measures_dict['R3'][i]]['2023'][fuel]/sum(EI_dict['R3'][mitigation_measures_dict['R3'][i]]['2023'].values()) for i in k3)*production_R3()
        -sum(model.X4[i]()*mitigation_measures_dict['R4'][i]['Energy reduction (Gj/t)']*EI_dict['R4'][mitigation_measures_dict['R4'][i]]['2023'][fuel]/sum(EI_dict['R4'][mitigation_measures_dict['R4'][i]]['2023'].values()) for i in k4)*production_R4
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
    
    
        
        
    return model,CE,















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
        
        


