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


#%%
### inserindo mais dados históricos de produção
### inserindo mais dados históricos de produção conforme modelagem do Otto
### inserindo mais dados históricos de produção

"""Importing Crude Steel production by route in kt"""

steel_production = pd.read_csv('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/steel_production.csv') #in kt
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
                float(Total_energy_consumption.loc[Total_energy_consumption['Combustivel']==combustivel, str(ano)])
            )
"""Creating dictionary"""

EI_dict= {}
a_dict = {}
for Rota in pd.unique(EI_BEU['Rota']):
    a_dict={}
    for etapa in pd.unique(EI_BEU.loc[EI_BEU['Rota']==Rota]):
        a =  EI_BEU.loc[EI_BEU['Rota']==Rota].set_index('Combustivel').drop(['Rota'],axis =1)
        a = a.to_dict()
        a_dict[etapa] = a
    EI_dict[Rota] = a_dict   
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

"""Energy share by routes"""

#Energy consumption after calibration;
Total_energy_consumption_R1 = energy_consumption('R1').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R2 = energy_consumption('R2').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R3 = energy_consumption('R3').groupby(['Combustivel'], axis =0, as_index = False).sum()
Total_energy_consumption_R4 = energy_consumption('R4').groupby(['Combustivel'], axis =0, as_index = False).sum()

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
    
#%%