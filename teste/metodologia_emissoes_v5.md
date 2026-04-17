# Metodologia de Cálculo de Emissões - Modelo V5

## 1. Visão Geral

O cálculo de emissões do modelo segue a metodologia desenvolvida por Hebeda (2024), adaptada para os dados do presente estudo. As emissões são calculadas a partir do consumo energético por combustível, utilizando fatores de emissão específicos para cada fonte energética.

## 2. Fórmula Geral

A emissão total de gases de efeito estufa (GEE) é calculada como:

$$
Emissão_{total} = \sum_{planta} \sum_{combustível} \left( Produção_{planta} \times IE_{rota,combustível} \times FE_{combustível} \right)
$$

Onde:
- **Produção** = produção de aço da planta (kt)
- **IE** = intensidade energética da rota por combustível (GJ/t aço)
- **FE** = fator de emissão do combustível (kg CO₂e/GJ)

## 3. Separação entre Emissões de Processo e Energia

### 3.1 Fundamentação

Na siderurgia, os combustíveis carbonosos exercem dupla função no alto-forno:

1. **Função térmica**: fornecem calor através da combustão
2. **Função redutora**: participam da reação química de redução do minério de ferro

A reação de redução do minério de ferro pode ser representada de forma simplificada como:

$$
Fe_2O_3 + 3C \rightarrow 2Fe + 3CO_2
$$

Nesta reação, o carbono presente no coque ou carvão vegetal atua como agente redutor, sendo convertido em CO₂ como parte do processo químico de produção do ferro metálico.

### 3.2 Simplificação Metodológica

A separação rigorosa entre as emissões provenientes da função térmica e da função redutora exigiria o cálculo do carbono estequiométrico necessário para a redução do minério versus o carbono excedente queimado para geração de calor. Esta separação demandaria dados operacionais detalhados de cada alto-forno, raramente disponíveis.

Seguindo a abordagem de Hebeda (2024), adotou-se uma simplificação metodológica que classifica os combustíveis em dois grupos:

**Combustíveis de Processo (redutores):**
- Coque de carvão mineral
- Carvão vegetal
- Carvão metalúrgico

**Combustíveis de Energia (térmicos):**
- Gás natural
- Eletricidade
- Óleo combustível
- Óleo diesel
- GLP
- Gases de cidade
- Outras fontes

### 3.3 Justificativa

Esta classificação atribui 100% das emissões dos combustíveis redutores como "emissões de processo", considerando que estes combustíveis participam diretamente da reação química de redução. Os demais combustíveis, que fornecem apenas energia térmica ao processo, têm suas emissões classificadas como "emissões de energia".

Esta abordagem é consistente com metodologias utilizadas em inventários nacionais de emissões e é aceita na literatura científica do setor siderúrgico.

## 4. Implementação no Modelo de Otimização

### 4.1 Restrição de Emissão

Durante a otimização, o modelo utiliza a emissão total (processo + energia) como restrição:

$$
\sum_{planta} \sum_{combustível} \frac{Produção_{planta,ano} \times IE_{rota,comb} \times FE_{comb,CO_2e}}{1000} \leq Limite_{ano}
$$

O otimizador seleciona a combinação de tecnologias que atende ao limite de emissão com o menor custo total.

### 4.2 Cálculo Detalhado nos Resultados

Após a otimização, as emissões são desagregadas para fins de análise:

**Emissões de Processo:**
$$
Emissão_{processo,gás} = \sum_{planta} \sum_{comb \in redutores} \frac{Prod_{planta} \times IE_{rota,comb} \times FE_{comb,gás}}{1000}
$$

**Emissões de Energia:**
$$
Emissão_{energia,gás} = \sum_{planta} \sum_{comb \in térmicos} \frac{Prod_{planta} \times IE_{rota,comb} \times FE_{comb,gás}}{1000}
$$

Onde *gás* representa CO₂, CH₄ ou N₂O.

### 4.3 CO₂ Equivalente

O total em CO₂ equivalente é calculado utilizando os potenciais de aquecimento global (GWP) do AR5 do IPCC:

$$
CO_2e = CO_2 + CH_4 \times 28 + N_2O \times 265
$$

## 5. Fontes de Dados

| Parâmetro | Fonte |
|-----------|-------|
| Intensidade Energética (IE) por rota e combustível | BEN/BEU, Hebeda (2024) |
| Fatores de Emissão (FE) por combustível | Inventário Nacional de Emissões |
| GWP (CH₄ = 28, N₂O = 265) | IPCC AR5 |

## 6. Verificação

A consistência do cálculo é verificada através da identidade:

$$
Emissão_{total} = Emissão_{processo} + Emissão_{energia}
$$

## 7. Referências

- HEBEDA, Otto. [Título da Tese]. Tese de Doutorado, COPPE/UFRJ, 2024.
- IPCC. Climate Change 2014: Synthesis Report. Contribution of Working Groups I, II and III to the Fifth Assessment Report of the Intergovernmental Panel on Climate Change. Geneva, 2014.
- BRASIL. Inventário Nacional de Emissões de Gases de Efeito Estufa. MCTI, 2020.
