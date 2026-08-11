"""K-Means dos hospitais — exploração inicial (board #20/#21)."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# reaproveita a conexão do pipeline
RAIZ = Path(__file__).resolve().parent.parent
sys.path.append(str(RAIZ / "etl" / "pipeline"))

from db import get_connection  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)

conn = get_connection()
print("Conectado:", conn.version)

df = pd.read_sql("SELECT * FROM gld_features_hospital", conn)
conn.close()

print("\nDimensões:", df.shape)
print("\n--- tipos e nulos ---")
df.info()
print("\n--- estatísticas ---")
print(df.describe().T)

# Hospitais com atuacao_sus_residual=1 (regra definida em GLD_FEATURES_
# HOSPITAL: total_aihs < 300, ver comentário em ouro_transform.py) saem
# do clustering e das médias — com poucas dezenas de AIHs os percentuais
# viram artefato de amostra pequena, não característica do hospital.
# Continuam listados aqui, só não entram no modelo.
residuais = df[df["ATUACAO_SUS_RESIDUAL"] == 1]
print(f"\n--- {len(residuais)} hospitais com atuação SUS residual (fora do modelo) ---")
print(residuais[["NOME_ESTABELECIMENTO", "TOTAL_AIHS", "MESES_COM_DADO"]]
      .sort_values("TOTAL_AIHS").to_string(index=False))

df = df[df["ATUACAO_SUS_RESIDUAL"] == 0].reset_index(drop=True)
print(f"\nHospitais ativos usados no modelo: {len(df)}")

# Features só estruturais: taxa_media, taxa_max, taxa_desvio e
# tx_mortalidade saem da matriz. Motivo: taxa de ocupação é a variável
# de SAÍDA que o HOSPCHECK quer explicar (GLD_OCUPACAO_MENSAL já traz
# o semáforo por ela); usá-la também como feature de entrada do cluster
# mistura causa com efeito. Mortalidade tem o mesmo problema — é
# consequência do perfil do hospital, não uma característica estrutural
# dele. Os clusters passam a agrupar por "o que o hospital É"
# (porte, permanência, perfil de demanda), não por "como ele está
# performando agora".
# MESES_COM_DADO é completude de dado, não característica do hospital.
# CO_CNES/NOME/TIPO_UNIDADE são identificadores, não entram no modelo
# nesta primeira rodada (TIPO_UNIDADE fica pra uma 2a rodada, com dummies).
FEATURES = [
    "LEITOS_SUS", "PERM_MEDIA", "PCT_URGENCIA",
    "PCT_ALTA_COMPLEX", "PCT_DIARIAS_UTI", "IDADE_MEDIA",
]

print("\n--- features usadas no modelo ---")
print(FEATURES)

X_scaled = StandardScaler().fit_transform(df[FEATURES])

# --- método do cotovelo + silhouette: K de 2 a 10 ---
print("\n--- método do cotovelo + silhouette ---")
K_RANGE = range(2, 11)
inercias = []
silhouettes = []
for k in K_RANGE:
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels_k = km.fit_predict(X_scaled)
    inercias.append(km.inertia_)
    sil = silhouette_score(X_scaled, labels_k)
    silhouettes.append(sil)
    print(f"K={k:2d}  inertia={km.inertia_:10.1f}  silhouette={sil:.3f}")

melhor_k_silhouette = list(K_RANGE)[silhouettes.index(max(silhouettes))]
print(f"\nMelhor K pelo silhouette: {melhor_k_silhouette} (silhouette={max(silhouettes):.3f})")

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(list(K_RANGE), inercias, "o-")
ax.set_xlabel("Número de clusters (K)")
ax.set_ylabel("Inércia (soma das distâncias² ao centróide)")
ax.set_title(f"Método do cotovelo — HOSPCHECK SP ({len(df)} hospitais ativos)")
ax.set_xticks(list(K_RANGE))
ax.grid(True, alpha=0.3)
fig.tight_layout()

OUT_PATH = Path(__file__).resolve().parent / "elbow_kmeans.png"
fig.savefig(OUT_PATH, dpi=150)
print(f"\nGráfico salvo em: {OUT_PATH}")

# --- modelo final: K=4 (cotovelo + silhouette + interpretabilidade) ---
K_FINAL = 4
kmeans_final = KMeans(n_clusters=K_FINAL, n_init=10, random_state=42)
df["CLUSTER"] = kmeans_final.fit_predict(X_scaled)

print(f"\n--- perfil dos clusters (K={K_FINAL}) ---")
# taxa/mortalidade ficam de fora do modelo, mas entram aqui só pra
# checar se os grupos formados por perfil estrutural também fazem
# sentido em relação a como estão performando.
COLUNAS_PERFIL = FEATURES + ["TAXA_MEDIA", "TAXA_MAX", "TAXA_DESVIO", "TX_MORTALIDADE", "TOTAL_AIHS"]
perfil = df.groupby("CLUSTER")[COLUNAS_PERFIL].mean().round(1)
perfil.insert(0, "QTD_HOSPITAIS", df.groupby("CLUSTER").size())
print(perfil.T)

print("\n--- hospitais por cluster ---")
for c in sorted(df["CLUSTER"].unique()):
    hospitais = df.loc[df["CLUSTER"] == c, "NOME_ESTABELECIMENTO"].tolist()
    print(f"\nCluster {c} ({len(hospitais)} hospitais):")
    for h in hospitais:
        print(f"  - {h}")

print(f"\n--- perfil dos clusters (K={K_FINAL}, formato resumido) ---")
print(df.groupby("CLUSTER").agg(
    n=("CO_CNES", "count"),
    leitos=("LEITOS_SUS", "mean"),
    taxa=("TAXA_MEDIA", "mean"),
    permanencia=("PERM_MEDIA", "mean"),
    urgencia=("PCT_URGENCIA", "mean"),
    alta_complex=("PCT_ALTA_COMPLEX", "mean"),
    uti=("PCT_DIARIAS_UTI", "mean"),
).round(1))

# --- visualização: projeta as 12 dimensões em 2D via PCA ---
pca = PCA(n_components=2)
xy = pca.fit_transform(X_scaled)
print(f"\nVariância explicada pelas 2 componentes: {pca.explained_variance_ratio_.sum():.3f}")

outlier_idx = xy[:, 0].argmax()
print(f"Hospital mais à direita no PCA (maior PC1): "
      f"{df.loc[outlier_idx, 'NOME_ESTABELECIMENTO']} "
      f"(cluster {df.loc[outlier_idx, 'CLUSTER']}, "
      f"leitos={df.loc[outlier_idx, 'LEITOS_SUS']}, "
      f"taxa_media={df.loc[outlier_idx, 'TAXA_MEDIA']})")

fig2, ax2 = plt.subplots(figsize=(8, 6))
scatter = ax2.scatter(xy[:, 0], xy[:, 1], c=df["CLUSTER"], cmap="tab10")
ax2.set_xlabel("Componente principal 1")
ax2.set_ylabel("Componente principal 2")
ax2.set_title(f"Clusters dos hospitais ativos (K={K_FINAL}, n={len(df)}) — projeção PCA")
ax2.legend(*scatter.legend_elements(), title="Cluster")
ax2.grid(True, alpha=0.3)
fig2.tight_layout()

PCA_OUT_PATH = Path(__file__).resolve().parent / "clusters_pca.png"
fig2.savefig(PCA_OUT_PATH, dpi=150)
print(f"\nGráfico de clusters (PCA) salvo em: {PCA_OUT_PATH}")

# --- gravação no banco: GLD_CLUSTER (board #22) ---
# O índice que o KMeans atribui a cada cluster é arbitrário e muda a
# cada fit (não é estável entre execuções) — nomear por índice fixo
# {0: ..., 1: ...} quebra silenciosamente quando a ordem muda. Em vez
# disso, identifica cada cluster pelo seu perfil característico.
cluster_stats = df.groupby("CLUSTER")[["LEITOS_SUS", "PERM_MEDIA"]].mean()

cluster_longa = cluster_stats["PERM_MEDIA"].idxmax()
restantes = cluster_stats.drop(index=cluster_longa)
cluster_grande = restantes["LEITOS_SUS"].idxmax()
restantes = restantes.drop(index=cluster_grande)
cluster_pequeno = restantes["LEITOS_SUS"].idxmin()
cluster_geral = restantes.drop(index=cluster_pequeno).index[0]

NOMES = {
    cluster_grande: "Grandes / ensino",
    cluster_geral: "Gerais / urgência",
    cluster_longa: "Longa permanência",
    cluster_pequeno: "Pequenos especializados",
}

df["CLUSTER_NOME"] = df["CLUSTER"].map(NOMES)
df["PCA_X"] = xy[:, 0]
df["PCA_Y"] = xy[:, 1]
# distância ao próprio centróide: quão típico do grupo o hospital é
df["DIST_CENTROIDE"] = kmeans_final.transform(X_scaled).min(axis=1)

registros = [
    (r.CO_CNES, int(r.CLUSTER), r.CLUSTER_NOME,
     float(r.PCA_X), float(r.PCA_Y), float(r.DIST_CENTROIDE))
    for r in df.itertuples()
]
# residuais entram sem cluster, pra não sumirem dos JOINs do painel
registros += [
    (r.CO_CNES, None, "Atuação SUS residual", None, None, None)
    for r in residuais.itertuples()
]

conn = get_connection()
with conn.cursor() as cur:
    cur.execute("""
        BEGIN EXECUTE IMMEDIATE 'DROP TABLE gld_cluster PURGE';
        EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;
    """)
    cur.execute("""
        CREATE TABLE gld_cluster (
          co_cnes        VARCHAR2(7),
          cluster_id     NUMBER,
          cluster_nome   VARCHAR2(60),
          pca_x          NUMBER,
          pca_y          NUMBER,
          dist_centroide NUMBER
        )
    """)
    cur.executemany(
        "INSERT INTO gld_cluster VALUES (:1, :2, :3, :4, :5, :6)", registros)
    cur.execute("CREATE INDEX ix_gld_cluster_cnes ON gld_cluster (co_cnes)")
conn.commit()
print(f"\nGLD_CLUSTER gravada: {len(registros)} hospitais "
      f"({len(df)} ativos + {len(residuais)} residuais)")
conn.close()
