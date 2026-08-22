# Metodologia — Clusterização e Fatores de Pressão

Documentação técnica do módulo M2 (Benchmarking e Fatores de Pressão).
Cobre os cards #21 (K-Means e escolha de K), #22 (score e gravação) e
#39 (método de classificação do fator dominante).

Implementação: `analytics/kmeans.py` (modelo) e `etl/pipeline/ouro_transform.py`
(view `GLD_FATORES_HOSPITAL`).

---

## 1. Objetivo

A taxa de ocupação sozinha não permite comparação justa: um hospital psiquiátrico
com internações de 60 dias e um pronto-socorro com internações de 4 dias podem
ambos estar a 90%, mas com causas e soluções completamente diferentes.

O módulo resolve isso em duas etapas:

1. **Agrupar** os hospitais por perfil assistencial (o que o hospital *é*)
2. **Comparar** cada hospital com os pares do seu grupo, identificando qual
   dimensão explica melhor a pressão que ele sofre (por que ele *está* saturado)

---

## 2. Universo analisado

Partimos de 83 hospitais com leito SUS e movimento registrado em SP capital
(jan/2025 – mai/2026, 17 competências).

**Critério de atuação SUS ativa:** hospitais com `total_aihs < 300` no período
são classificados como **atuação residual** e excluídos do modelo — restam **78**.

Justificativa (não é corte arbitrário):

- **Salto na distribuição**: o 5º colocado tem 257 internações, o 6º tem 800.
  A partir daí a distribuição sobe suavemente, sem outra descontinuidade.
- **Presença intermitente**: os 5 hospitais abaixo do corte têm 1, 5, 8, 10 e 16
  meses com dado (de 17 possíveis); a partir do salto, praticamente todos têm os
  17 meses completos. Não são hospitais pequenos e estáveis — são unidades com
  atuação marginal e descontínua na rede SUS.
- **Efeito prático**: com poucas dezenas de internações, qualquer percentual vira
  artefato de amostra. O Hospital do Coração tem 1 internação no período inteiro;
  o Hospital Japonês Santa Cruz tem 38 em 10 meses, gerando "97% de urgência" —
  número que descreve um punhado de pacientes, não o perfil da instituição.

Os excluídos permanecem visíveis no painel com a flag `atuacao_sus_residual = 1`
e semáforo `RESIDUAL`; saem apenas do ranking, das médias da rede e do modelo.

---

## 3. Seleção de variáveis

**Variáveis usadas (6, todas estruturais):**

| Variável | O que representa |
|---|---|
| `leitos_sus` | porte da unidade |
| `perm_media` | dias médios de internação |
| `pct_urgencia` | proporção de internações de urgência vs. eletivas |
| `pct_alta_complex` | proporção de procedimentos de alta complexidade |
| `pct_diarias_uti` | intensidade de terapia intensiva |
| `idade_media` | perfil etário da população atendida |

**Variáveis deliberadamente excluídas:**

- `taxa_media`, `taxa_max`, `taxa_desvio` — a taxa de ocupação é a **variável de
  saída** que o projeto quer explicar. Usá-la também como entrada do agrupamento
  mistura causa com efeito: os grupos passariam a ser formados por "quão cheio o
  hospital está", e dizer depois que um hospital está acima da ocupação média do
  seu grupo se tornaria circular.
- `tx_mortalidade` — mesma lógica: é desfecho, não característica estrutural.
  Aparece como **dimensão de análise** (fator Gravidade), não como critério de
  agrupamento.
- `meses_com_dado` — completude do dado, não característica do hospital.
- Identificadores (`co_cnes`, nome, tipo de unidade) — sem valor preditivo.
  `tipo_unidade` poderia entrar como variável categórica (dummies) numa segunda
  rodada; ficou fora desta versão.

**Padronização:** `StandardScaler` (média 0, desvio 1). Obrigatório porque o
K-Means agrupa por distância euclidiana e as escalas são incomparáveis —
`leitos_sus` vai de 4 a 1.476 e os percentuais de 0 a 100. Sem padronizar, o
porte dominaria a distância e o agrupamento seria, na prática, por tamanho.

---

## 4. Escolha do número de grupos (K)

Três critérios, aplicados em conjunto:

| Critério | Resultado |
|---|---|
| Método do cotovelo | região 4–5 (a queda da inércia perde força após K=4) |
| Silhouette | K=6 tem o melhor valor (0,401), K=4 fica próximo (0,377) |
| Interpretabilidade | K=4 produz os únicos grupos clinicamente nomeáveis |

**Decisão: K = 4.**

O silhouette tende a premiar fragmentação — valores mais altos aparecem quando
grupos pequenos e isolados se separam. Com 78 hospitais, K=6 produziria grupos de
poucas unidades sem identidade clínica reconhecível. Como a diferença entre 0,377
e 0,401 é pequena e o cotovelo aponta a mesma região, o desempate foi pela
capacidade de nomear e comunicar os grupos — que é o requisito do benchmarking:
um gestor precisa reconhecer seus pares.

Nota: o silhouette de ~0,38 indica grupos existentes mas com fronteiras suaves,
o que é esperado em dados de saúde, onde os perfis são contínuos e não categorias
discretas. Não invalida o agrupamento; recomenda cautela ao tratá-lo como
classificação rígida.

**Reprodutibilidade:** `random_state=42` e `n_init=10` fixos. O índice numérico
que o algoritmo atribui a cada cluster é arbitrário e pode mudar entre execuções —
por isso os nomes são derivados do perfil (maior permanência → "Longa permanência",
maior porte → "Grandes / ensino"), nunca de um índice fixo.

---

## 5. Grupos identificados

| Grupo | n | Leitos SUS | Permanência | Urgência | Alta complex. | UTI |
|---|---|---|---|---|---|---|
| Grandes / ensino | 8 | 684 | 6,2 d | 51% | 42% | 28% |
| Gerais / urgência | 48 | 182 | 5,6 d | 83% | 2% | 10% |
| Pequenos especializados | 14 | 81 | 4,7 d | 30% | 41% | 10% |
| Longa permanência | 8 | 162 | 22,6 d | 0,3% | 0% | 0% |

Leitura dos grupos:

- **Grandes / ensino** — complexos de referência (HC-FMUSP, ICESP, Santa Marcelina).
  Porte muito acima da rede, alta densidade tecnológica.
- **Gerais / urgência** — a espinha dorsal da rede municipal. Volume alto de
  urgência, permanência curta, baixa complexidade.
- **Pequenos especializados** — unidades de menor porte com perfil eletivo e
  alta complexidade concentrada.
- **Longa permanência** — psiquiatria e reabilitação. O algoritmo isolou esse
  grupo sem nenhuma informação sobre especialidade, apenas pelo padrão de
  permanência (22,6 dias contra ~5 dos demais) e ausência total de UTI e alta
  complexidade. A separação é nítida nos dados, embora seja o único cluster sem
  validação externa independente (ver seção 6).

---

## 6. Validação externa (o que dá pra provar, e o que não dá)

Duas métricas usadas até aqui — cotovelo e silhouette — são **internas**: medem
se os pontos ficaram geometricamente bem agrupados olhando só para os próprios
dados de entrada. Isso confirma que o algoritmo convergiu para uma estrutura
consistente, mas não prova que essa estrutura corresponde a alguma coisa real
no mundo. Um K-Means sempre encontra grupos, inclusive em ruído puro.

**Validação externa** é diferente: compara o cluster contra uma variável
**independente**, que o modelo nunca viu durante o treino. Se bater, é evidência
de que o agrupamento capturou um padrão real — não é o modelo "confirmando a si
mesmo".

### O teste que temos

A API do CNES (`brz_cnes_api_raw` → `slv_estabelecimento`) traz o campo oficial
`codigo_atividade_ensino_unidade`, que classifica cada estabelecimento como
unidade de ensino/pesquisa ou não. Essa variável:

- não entrou em nenhuma das 6 features do K-Means (seção 3);
- vem de um cadastro público, preenchido pelo próprio hospital junto ao
  Ministério da Saúde — fonte independente da nossa análise.

Depois do cluster pronto, cruzamos `cluster_nome` × `tem_atividade_ensino`:

| Cluster | % oficialmente ensino (CNES) |
|---|---|
| Grandes / ensino | **100%** |
| Pequenos especializados | 64% |
| Gerais / urgência | 46% |
| Longa permanência | 25% |

Os 8 hospitais que o algoritmo agrupou por porte, complexidade e UTI — sem
nenhuma informação sobre ensino — são **exatamente** os 8 que o CNES classifica
como unidades de ensino. Isso é o mais próximo de uma prova que este projeto
tem: uma correlação perfeita com um rótulo que o modelo não usou.

### Segundo teste: tipo de unidade (CNES)

O campo `ds_tipo_unidade` do CNES — também ausente das features do modelo —
classifica o estabelecimento como HOSPITAL GERAL, HOSPITAL ESPECIALIZADO e
outros. Cruzando contra os clusters:

| Cluster | % ESPECIALIZADO | % GERAL |
|---|---|---|
| Pequenos especializados | **71%** | 29% |
| Longa permanência | 62% | 38% |
| Grandes / ensino | 38% | **63%** |
| Gerais / urgência | 19% | **81%** |

Percentuais arredondados; podem somar 101% em grupos de 8 hospitais.

Os dois extremos confirmam os rótulos: o cluster que chamamos de "Gerais /
urgência" é o mais oficialmente *geral* da rede (81%), e o "Pequenos
especializados" é o mais oficialmente *especializado* (71%).

Esta validação é **mais fraca que a anterior**: a correlação não é perfeita e as
categorias se sobrepõem — 19% dos "Gerais / urgência" são classificados como
especializados no CNES. É evidência direcional, não prova.

"Grandes / ensino" aparecer como majoritariamente *geral* (63%) não contradiz o
agrupamento: são hospitais gerais de grande porte com atividade de ensino
(HC-FMUSP, Santa Marcelina), o que é coerente com a validação da seção
anterior.

"Longa permanência" fica em 62% especializado — próximo dos "Pequenos
especializados" (71%), portanto o campo **não discrimina** esse cluster.
Continua sem validação externa: psiquiatria e reabilitação são de fato
especializadas, mas isso não separa esse grupo dos demais. Validá-lo exigiria
outra fonte, como o cadastro de leitos psiquiátricos ou da RAPS.

### O que isso NÃO cobre

Somando os dois testes, três dos quatro clusters têm alguma validação externa —
mas com forças diferentes, e nenhuma delas prova o modelo inteiro:

| Cluster | Validação disponível | Natureza |
|---|---|---|
| Grandes / ensino | atividade de ensino (CNES) — correlação perfeita | **Externa, forte** |
| Gerais / urgência | tipo de unidade (CNES) — 81% HOSPITAL GERAL | **Externa, parcial** |
| Pequenos especializados | tipo de unidade (CNES) — 71% HOSPITAL ESPECIALIZADO | **Externa, parcial** |
| Longa permanência | nenhuma fonte independente discriminante | interna + leitura qualitativa |

O cluster **Longa permanência** é o que fica sem prova. O que o sustenta é (a) a
coerência interna do K-Means (silhouette, seção 4) e (b) o fato de os hospitais
que caem nele fazerem sentido clínico ao serem inspecionados por nome — o grupo
reúne Instituto de Psiquiatria, Lucy Montoro (reabilitação) e o hospital do
sistema penitenciário. É um indício forte, mas é leitura qualitativa, não um
teste estatístico contra um rótulo independente. A formulação correta para ele é
**"provavelmente correto"**, não "confirmado".

Vale registrar também o que **nenhum** dos testes cobre: eles validam que os
grupos correspondem a categorias reais de estabelecimento, não que a
**comparação de desempenho dentro do grupo** seja a mais justa possível. Essa
premissa — de que hospitais do mesmo perfil são pares adequados para
benchmarking — é razoável e é a prática usual em saúde, mas não foi testada
empiricamente neste projeto.

---

## 7. Visualização (PCA)

O espaço do modelo tem 6 dimensões, impossível de desenhar. Aplicamos **PCA**
para projetar em 2 componentes, preservando **54,3%** da variância — as
coordenadas ficam gravadas em `GLD_CLUSTER.pca_x` / `pca_y`.

**Limitação a declarar:** com ~54% da variância retida, o gráfico 2D é uma sombra
do espaço real. Grupos que aparecem sobrepostos no desenho podem estar bem
separados nas dimensões não representadas. O gráfico serve para ilustrar a
estrutura, não para concluir sobre separação.

---

## 8. Fator dominante — método de classificação (card #39)

**Método adotado: z-score dentro do cluster.** Não usamos limiar fixo.

Para cada hospital, mede-se o quanto ele se afasta da média do **seu próprio
grupo** em quatro dimensões:

```
z = (valor do hospital − média do cluster) ÷ desvio-padrão do cluster
```

| Dimensão | Métrica | Evidência exibida |
|---|---|---|
| Volume | `total_aihs` | nº de internações |
| Permanência | `perm_media` | dias médios |
| Gravidade | `tx_mortalidade` | mortalidade % |
| Complexidade | `val_medio_aih` | valor médio da AIH (R$) |

O **maior z-score** define o fator dominante. Se nenhum ultrapassa **1,0**, o
hospital é classificado como `MULTIFATORIAL` — sem esse piso, um hospital sem
desvio relevante receberia um "fator dominante" que seria apenas ruído. Quando
o maior z-score é negativo ou zero, o hospital está abaixo dos pares em todas
as dimensões e recebe `SEM PRESSAO`.

**Por que z-score e não limiar fixo ou percentil:**

- **Limiar fixo** (ex.: "permanência > 10 dias") não funciona entre grupos
  heterogêneos: 10 dias é excepcional para um pronto-socorro e baixo para uma
  unidade psiquiátrica. O mesmo número teria significados opostos.
- **Percentil** é robusto a outliers, mas com clusters de 8 hospitais os
  percentis ficam grosseiros demais (cada hospital representa ~12 pontos
  percentuais) e não expressam magnitude — apenas ordem.
- **Z-score** expressa a distância em unidades de desvio-padrão do próprio grupo,
  é comparável entre dimensões de escalas diferentes e permite o piso de
  relevância (1,0). A limitação é a sensibilidade a valores extremos em grupos
  pequenos, mitigada pela exclusão dos hospitais de atuação residual.

**Saídas da view `GLD_FATORES_HOSPITAL`:** além do `fator_dominante` e dos quatro
z-scores, a view entrega o valor do hospital e a média do cluster lado a lado
(`taxa_media`/`taxa_cluster`, `perm_media`/`perm_cluster`...), a posição no grupo
(`rank_no_cluster` de `n_cluster`), uma `evidencia` formatada e um `insight` em
linguagem natural.

**Ressalva sobre as recomendações:** o campo `recomendacao` traduz o fator
dominante em uma direção de investigação (ex.: permanência elevada → gestão de
altas e retaguarda). São hipóteses de trabalho para orientar onde o gestor deve
olhar, **não prescrições clínicas ou administrativas validadas**. A investigação
da causa e a decisão sobre a intervenção permanecem com a gestão da unidade.

---

## 9. Limitações

1. **Recorte temporal**: as features agregam 17 competências. Hospitais que
   mudaram de perfil no período aparecem com a média, não com a tendência.
2. **Silhouette moderado (0,38)**: fronteiras suaves entre grupos; hospitais
   próximos da divisa poderiam pertencer a mais de um perfil.
3. **PCA com 54% de variância**: a visualização 2D é parcial.
4. **Dependência do SIH-RD**: as features clínicas (permanência, complexidade,
   UTI, mortalidade) vêm dos microdados de internação. Competências não
   carregadas reduzem a base de cálculo.
5. **Ocupação acima de 100%** em alguns hospitais indica leitos subdeclarados no
   CNES, não superlotação real. O modelo usa a taxa limitada a 100%; o painel
   exibe o valor real com sinalização.
6. **Validação externa parcial** (seção 6): "Grandes / ensino" tem correlação
   perfeita com o rótulo de atividade de ensino do CNES; "Gerais / urgência" e
   "Pequenos especializados" têm validação direcional pelo tipo de unidade. Só
   "Longa permanência" fica sem fonte independente discriminante, apoiado em
   coerência interna e leitura qualitativa.
7. **Recorte do perfil clínico**: as views de diagnóstico cobrem apenas
   hospitais com ocupação calculável. Estabelecimentos que faturam AIH mas
   não declaram leito no CNES ficam fora — cerca de 12% das internações,
   concentradas em procedimentos eletivos de curta permanência.

---

## 10. Como reproduzir

```
python etl/pipeline/bronze_api_cnes.py    # cadastro do CNES (JSON)
python etl/pipeline/prata_transform.py    # camada Prata
python etl/pipeline/ouro_transform.py     # views Ouro (features)
python analytics/kmeans.py                # modelo + GLD_CLUSTER
```

Saídas geradas: `analytics/elbow_kmeans.png`, `analytics/clusters_pca.png` e a
tabela `GLD_CLUSTER` no banco. A view `GLD_FATORES_HOSPITAL` passa a retornar
dados assim que a `GLD_CLUSTER` existe.
