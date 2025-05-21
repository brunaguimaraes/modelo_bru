# -*- coding: utf-8 -*-
"""
Created on Wed May 21 11:57:16 2025

@author: Bruna
"""


"""
INFO:
R1 = Route BOF using Coal
R2 = Route BOF using Charcoal
R3 = Route EAF using scrap
R4 = Route Independet producers 
"""

""""1. Leitura dos Dados"""

import pandas as pd

plants = pd.read_excel('C:/Users/Bruna/OneDrive/DOUTORADO/0.TESE/modelagem/modelo_bru/plants.xlsx')
# Garantir que Retrofitdate é inteiro/ano
plants['Retrofitdate'] = pd.to_numeric(plants['Retrofitdate'], errors='coerce').astype(int)


"""2. Capacidade ativa de cada planta em um dado ano:
    Vamos assumir que TODAS as linhas do excel são plantas existentes,
    e estão ativas até o ano do (exclusive)
    """

def get_active_capacity_existing(year, plants_df):
    # Planta está ativa se ano < Retrofitdate
    ativos = plants_df[year < plants_df['Retrofitdate']]
    return ativos.groupby('Route')['Capacity'].sum().to_dict()

print("Capacidade existente em 2019:", get_active_capacity_existing(2019, plants))
print("Capacidade existente em 2020:", get_active_capacity_existing(2020, plants))


"""2. Adicione vida útil padrão (exemplo: 31 anos):"""
plants['life'] = 31  # ou o valor real de vida útil se você tiver

"""
3. Entrada de novas plantas (investimento a partir do modelo):
Quando você criar/decidir investir em novas plantas, adicione linhas em um novo DataFrame, por exemplo:
"""
novas_plantas = pd.DataFrame(columns=['Plantname', 'Route', 'StartDate', 'Life', 'Capacity'])

# Exemplo: investe nova planta R3 em 2025
novas_plantas = novas_plantas.append({
    'Plantname': 'Nova_R3_2025',
    'Route': 'R3',
    'StartDate': 2025,
    'Life': 31,
    'Capacity': 1200
}, ignore_index=True)





"""5. Somando a capacidade em um determinado anoo: Generalizando com função (para qualquer ano):"""
def get_active_capacity(year, plants_df):
    ativos = plants_df[(plants_df['Retrofitdate'] <= year) & (year < plants_df['Retrofitdate'] + plants_df['life'])]
    return ativos.groupby('Route')['Capacity'].sum().to_dict()

print("Capacidade ativa em 2019:", get_active_capacity(2019, plants))