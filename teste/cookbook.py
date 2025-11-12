# -*- coding: utf-8 -*-
"""
Created on Fri Aug  1 11:27:23 2025

@author: Bruna

pyomo cookbook
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pyomo.environ import ConcreteModel, Var, Objective, Constraint, NonNegativeReals, minimize, SolverFactory, value, maximize

#%% 2.1.3. Production plan: Product Y

model = ConcreteModel()

#declare decision variable
model.y = Var(domain=NonNegativeReals)

#declare objective
model.profit = Objective(
    expr = 30*model.y,
    sense = maximize)

#declare constraints
model.laborA = Constraint(expr = model.y <= 80)
model.laborB = Constraint(expr = model.y <= 100)

#solve
#solver = SolverFactory(
#    'cbc',
#    executable=r"C:\Users\Bruna\anaconda3\Library\bin\cbc.exe"
#)

results = SolverFactory('cbc',
executable=r"C:\Users\Bruna\anaconda3\Library\bin\cbc.exe").solve(model, tee=True)
results.write()

print("Valor ótimo de y:", value(model.y))
print("Lucro máximo:", value(model.profit))


