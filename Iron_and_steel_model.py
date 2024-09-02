# -*- coding: utf-8 -*-
"""
Created on Wed Nov 18 13:59:29 2020

@author: Otto


Energy and Emission Bottom-up modelling: Iron and Steel

R1 = Route BOF using Coal
R2 = Route BOF using Charcoal
R3 = Route EAF using scrap
R4 = Route Independet producers 

"""
import pandas as pd
import numpy as np

#%%
"""1. Importing Data"""

#Confersion factor Gj to Ktoe    
gj_to_ktoe = 1/41.868
ktoe_to_gj = 41.868
"""Importing Crude Steel production by route"""

steel_production = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/steel_production.csv")
steel_production = steel_production.set_index('Year')
steel_production['Total']= steel_production.sum(axis=1)

"""Importing Pig Iron production by Route"""
pig_iron_production = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Pig_iron_production.csv")
pig_iron_production = pig_iron_production.set_index('Ano')
pig_iron_production['Share BOF CC'] = pig_iron_production['Integrada CV']/(pig_iron_production['Integrada CV']+pig_iron_production['Integrada CM'])
pig_iron_production['Share BOF MC']=1-pig_iron_production['Share BOF CC']

"""Importing Energy Production Intensity"""

#Energy Production Intensity in Coal Route Gj/t crude steel
#R1_energy_production_intensity = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Iron_and_steel_IRC_energy_production_intensity.csv")
#R1_energy_production_intensity = R1_energy_production_intensity.set_index('Combustivel')
#
##Energy Production Intensity in Charcoal Route (R2) Gj/t crude steel
#R2_energy_production_intensity = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Iron_and_steel_charcoal_energy_production_intensity.csv")
#R2_energy_production_intensity = R2_energy_production_intensity.set_index('Combustivel')
#
##There is no Energy Production in this route
#
#"""Importing Energy Consumption Intensity"""
#
##Energy Consumption Intensity in Coal Route (R1) Gj/t crude steel
#R1_energy_consumption_intensity = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/iron_and_steel_IRC_energy_consumption_intensity.csv")
#R1_energy_consumption_intensity = R1_energy_consumption_intensity.set_index('Combustivel')
#
##Energy Consumption Intensity in Charcoal Route (R2) Gj/t crude steel
#R2_energy_consumption_intensity = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Iron_and_steel_charcoal_energy_consumption_intensity.csv")
#R2_energy_consumption_intensity = R2_energy_consumption_intensity.set_index('Combustivel')
#R2_energy_consumption_intensity = R2_energy_consumption_intensity.fillna(0)
#
##Energy Consumption Intensity in EAF route (R3) Gj/t crude steel 
#R3_energy_consumption_intensity = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Iron_and_steel_EAF_energy_consumption_intensity.csv")
#R3_energy_consumption_intensity = R3_energy_consumption_intensity.set_index('Combustivel')
#R3_energy_consumption_intensity = R3_energy_consumption_intensity.fillna(0)
#
##Energy consumption in Independent Production (Pig Iron) Tep/t pig iron:
#R4_energy_consumption_intensity  = pd.read_csv ('https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Independent_energy_consumption.csv')
#R4_energy_consumption_intensity = R4_energy_consumption_intensity.set_index('Combustivel')
#R4_energy_consumption_intensity = R4_energy_consumption_intensity*ktoe_to_gj

"""Importing Energy Consumption compatible with the Useful Energy Balance (BEU):
    In the META report they already separeted the Final Energy Consumption in the same nomenclature as the BEU
    """
R1_energy_consumption_intensity_BEU = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Integrated_MC_EI_BEU.csv")
R2_energy_consumption_intensity_BEU = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Integrated_CC_EI_BEU.csv")
R3_energy_consumption_intensity_BEU = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/EAF_IE_BEU.csv")
R4_energy_consumption_intensity_BEU = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/Independent_EI_BEU.csv")


R1_energy_consumption_intensity_BEU = R1_energy_consumption_intensity_BEU.set_index('Combustivel')
R2_energy_consumption_intensity_BEU = R2_energy_consumption_intensity_BEU.set_index('Combustivel')
R3_energy_consumption_intensity_BEU = R3_energy_consumption_intensity_BEU.set_index('Combustivel')
R4_energy_consumption_intensity_BEU = R4_energy_consumption_intensity_BEU.set_index('Combustivel')

R1_energy_consumption_intensity_BEU = R1_energy_consumption_intensity_BEU.fillna(0)
R2_energy_consumption_intensity_BEU = R2_energy_consumption_intensity_BEU.fillna(0)
R3_energy_consumption_intensity_BEU = R3_energy_consumption_intensity_BEU.fillna(0)
R4_energy_consumption_intensity_BEU = R4_energy_consumption_intensity_BEU.fillna(0)

#Total intensity by Energy source:
R1_energy_consumption_intensity_BEU['Total'] = R1_energy_consumption_intensity_BEU.sum(1)
R2_energy_consumption_intensity_BEU['Total'] = R2_energy_consumption_intensity_BEU.sum(1)
R3_energy_consumption_intensity_BEU['Total'] = R3_energy_consumption_intensity_BEU.sum(1)

#Total intensity by production step:
R1_energy_consumption_intensity_BEU.loc['Total'] = R1_energy_consumption_intensity_BEU.sum()
R2_energy_consumption_intensity_BEU.loc['Total'] = R2_energy_consumption_intensity_BEU.sum()
R3_energy_consumption_intensity_BEU.loc['Total'] = R3_energy_consumption_intensity_BEU.sum()

R4_energy_consumption_intensity_BEU = R4_energy_consumption_intensity_BEU*ktoe_to_gj #Converting from ktoe to Gj
#%%
"""Historic Data"""

#Years from the historic data
past_years = np.linspace(2005,2019,2019-2005+1)
past_years = past_years.astype(int)

#Energy Consumption in the Steel Production in the National Energy Balance (BEN)
 
Energy_consumption_BEN = pd.read_csv("https://raw.githubusercontent.com/ottohebeda/Iron-and-steel-model/main/BEN_IronSteel_2019.csv") #importing BEN_Steel
Energy_consumption_BEN = Energy_consumption_BEN.fillna(0) #filling NA with 0
Energy_consumption_BEN = Energy_consumption_BEN.set_index('SOURCES') #Changin index for Sources
Energy_consumption_BEN.index = Energy_consumption_BEN.index.str.capitalize() #Change all UPPER to Capitalize
Energy_consumption_BEN.columns = Energy_consumption_BEN.columns.astype(int) #Changing the columns type: from str to int

#I'm going to drop Gás canalizado, Nafta and Querosene because they have value approximately zero:
Energy_consumption_BEN = Energy_consumption_BEN.drop(index = ['Gás canalizado',"Nafta",'Querosene '])

#Slicing the Enerngy_consumption_BEN to values in the historical data

Energy_consumption_BEN =Energy_consumption_BEN.drop(columns = Energy_consumption_BEN.columns[0:35])


#%%
"""Energy intensity
"""

##Estimating the Energy Intensity by productoin step and fuel
R1_energy_intensity = R1_energy_consumption_intensity_BEU.copy()
R2_energy_intensity = R2_energy_consumption_intensity_BEU.copy()
R3_energy_intensity = R3_energy_consumption_intensity_BEU.copy()
R4_energy_intensity = R4_energy_consumption_intensity_BEU.copy()


#%%        
"""Energy Consumption"""

#BOF Coal production in Mt
steel_production['BOF MC'] = steel_production.BOF*pig_iron_production['Share BOF MC']

#BOF Charcoal production in Mt
steel_production['BOF CC'] = steel_production.BOF*pig_iron_production['Share BOF CC']

#Energy Consumption in R1 (BOF Coal) in Gj
energy_consumption_R1 = pd.DataFrame(index = R1_energy_intensity.index, columns = past_years, data = 0)
for t in past_years:
    energy_consumption_R1[t] = steel_production['BOF MC'][t]*R1_energy_intensity.Total
    
#Energy Consumption in R2 (BOF Charcoal) in Gj
energy_consumption_R2 = pd.DataFrame(index = R2_energy_intensity.index, columns = past_years, data = 0)
for t in past_years:
    energy_consumption_R2[t] = steel_production['BOF CC'][t]*R2_energy_intensity.Total

#Energy Consumption in R3 (EAF) in Gj
energy_consumption_R3 = pd.DataFrame(index = R3_energy_intensity.index, columns = past_years, data = 0)
for t in past_years:
    energy_consumption_R3[t] = steel_production['EAF'][t]*R3_energy_intensity.Total
    
#Energy Consumption in R4 (Independent production) in GJ:
energy_consumption_R4 = pd.DataFrame(index = R4_energy_intensity.index, columns = past_years, data = 0)
for t in past_years:
    energy_consumption_R4[t] = pig_iron_production['Independente CV'][t]*R4_energy_intensity.sum(axis=1)   

#Total Energy Consumption
Total_energy_consumption =     energy_consumption_R1+energy_consumption_R2+energy_consumption_R3+energy_consumption_R4
Total_energy_consumption.loc['Total'] = Total_energy_consumption[:-1].sum()
Total_energy_consumption_ktoe = Total_energy_consumption*gj_to_ktoe

#Sorting the index:
Total_energy_consumption_ktoe = Total_energy_consumption_ktoe.sort_index()
Energy_consumption_BEN= Energy_consumption_BEN.sort_index()

#%%
"""Adjustments for the energy consumption'"""

"""First I'm going to create DF for the energy intensity for each route and step for each year"""

#R1_energy_intensity

R1_EI_Sintering = pd.DataFrame(index = R1_energy_intensity.index,  columns = past_years, data=0)
R1_EI_BlastFurnace = pd.DataFrame(index = R1_energy_intensity.index,  columns = past_years, data=0)
R1_EI_BOF = pd.DataFrame(index = R1_energy_intensity.index,  columns = past_years, data=0)
R1_EI_Rolling = pd.DataFrame(index = R1_energy_intensity.index,  columns = past_years, data=0)
R1_EI_Others = pd.DataFrame(index = R1_energy_intensity.index, columns = past_years, data = 0)

#R1_routes = R1_energy_consumption_intensity_BEU.columns[:4] #excpet Total

def Route_EI_step(Route_EI_by_step, EI_source, step):
    for i in past_years:
        Route_EI_by_step[i] = np.array(EI_source[step])
        

Route_EI_step(R1_EI_Sintering,R1_energy_consumption_intensity_BEU,'Sinterizacao')
Route_EI_step(R1_EI_BlastFurnace,R1_energy_consumption_intensity_BEU,'Alto-forno')
Route_EI_step(R1_EI_BOF,R1_energy_consumption_intensity_BEU,'Aciaria')
Route_EI_step(R1_EI_Rolling,R1_energy_consumption_intensity_BEU,'Laminacao')
Route_EI_step(R1_EI_Others, R1_energy_consumption_intensity_BEU,'Flare')

#R2_energy_intensity

R2_EI_Pelleting = pd.DataFrame( index = R2_energy_intensity.index, columns = past_years, data = 0)
R2_EI_BlastFurnace = pd.DataFrame( index = R2_energy_intensity.index, columns = past_years, data = 0)
R2_EI_BOF = pd.DataFrame( index = R2_energy_intensity.index, columns = past_years, data = 0)
R2_EI_Rolling = pd.DataFrame( index = R2_energy_intensity.index, columns = past_years, data = 0)
R2_EI_Others = pd.DataFrame(index = R2_energy_intensity.index, columns = past_years, data = 0)

Route_EI_step(R2_EI_Pelleting,R2_energy_consumption_intensity_BEU,'Pelotizacao')
Route_EI_step(R2_EI_BlastFurnace,R2_energy_consumption_intensity_BEU,'Alto-forno')
Route_EI_step(R2_EI_BOF,R2_energy_consumption_intensity_BEU,'Aciaria')
Route_EI_step(R2_EI_Rolling,R2_energy_consumption_intensity_BEU,'Laminacao')
Route_EI_step(R2_EI_Others, R2_energy_consumption_intensity_BEU,'Flare')

#R3_energy_intensity

R3_EI_EAF= pd.DataFrame( index = R3_energy_intensity.index, columns = past_years, data = 0)
R3_EI_Rolling = pd.DataFrame( index = R3_energy_intensity.index, columns = past_years, data = 0)
R3_EI_Others = pd.DataFrame(index = R3_energy_intensity.index, columns = past_years, data = 0)

Route_EI_step(R3_EI_EAF, R3_energy_consumption_intensity_BEU, 'Aciaria')
Route_EI_step(R3_EI_Rolling, R3_energy_consumption_intensity_BEU, 'Laminacao')
Route_EI_step(R3_EI_Others, R3_energy_consumption_intensity_BEU, 'Outros')

#R4_energy_intensity

R4_EI_Sintering = pd.DataFrame( index = R4_energy_intensity.index, columns = past_years, data = 0)
R4_EI_BlastFurnace = pd.DataFrame( index = R4_energy_intensity.index, columns = past_years, data = 0)

Route_EI_step(R4_EI_Sintering,R4_energy_consumption_intensity_BEU,'Pelotizacao')
Route_EI_step(R4_EI_BlastFurnace,R4_energy_consumption_intensity_BEU,'Alto-forno')
