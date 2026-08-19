# Bug de plataforma: ORA-20404 `my$cloud_domain` no Select AI (OCI GenAI)

**Status:** ENCERRADO — bug de plataforma confirmado e contornado. O M3 está em produção via REST direto (ver §Desfecho).
**Data:** 03/ago/2026 · **Afeta:** SPIKE Select AI (board #30) / módulo M3
**Ambiente:** ADB 26ai Always Free · região sa-saopaulo-1 · patch DBMS_CLOUD `PDBCS_260724`

## Sintoma

Perfil criado com sucesso via `DBMS_CLOUD_AI.CREATE_PROFILE` (provider `oci`,
`OCI$RESOURCE_PRINCIPAL`, modelo `meta.llama-3.3-70b-instruct`), mas qualquer
`SELECT AI ...` falha com:

```
ORA-20404: Object not found -
https://inference.generativeai.sa-saopaulo-1.oci.my$cloud_domain/20231130/actions/chat
ORA-06512: em "C##CLOUD$SERVICE.DBMS_CLOUD$PDBCS_260724_0", line 2291
ORA-06512: em "C##CLOUD$SERVICE.DBMS_CLOUD_AI", line 21243
```

## Diagnóstico

A URL do endpoint deveria terminar em `...oci.oraclecloud.com`. O trecho
`my$cloud_domain` é uma **variável de substituição interna não resolvida**
pelo pacote `DBMS_CLOUD_AI` ao montar o endpoint de inferência — ou seja,
a requisição morre antes de chegar ao serviço.

Não é erro de configuração nossa. Evidências:

1. Autenticação OK — policy de resource principal criada e aceita
   (`allow any-user to manage generative-ai-family in tenancy where
   request.principal.type = 'autonomousdatabase'`); o erro é 404 (objeto),
   não 401 (autorização).
2. Serviço disponível — console Generative AI acessível em sa-saopaulo-1,
   com 12 modelos de chat listados (Cohere e Meta Llama).
3. Mesmo erro ocorre com região default (us-chicago-1) e com região explícita.
4. **Bug reportado publicamente** com o mesmo placeholder:
   [Cloud Customer Connect — ORA-20404 (nov/2025)](https://community.oracle.com/customerconnect/discussion/923511/ora-20404)

## Workarounds

### Tentativa 1 — endpoint explícito no perfil (em teste)

Contornar a montagem da URL informando `provider_endpoint`:

Resultados dos testes:

| Variação | Resultado |
|---|---|
| sem `provider_endpoint` (montagem automática) | ORA-20404 — URL com `my$cloud_domain` não resolvido |
| `provider_endpoint` = hostname (sem esquema) | ORA-20006 — "Unsupported object store URI" |
| `provider_endpoint` = `https://...oraclecloud.com` (com esquema) | ORA-20006 — mesmo erro; pacote ignora/rejeita o override |

### Tentativa 2 — provedor alternativo (ADOTADA)

Select AI é agnóstico de provedor. Perfil com Gemini (tier gratuito):
ACL para `generativelanguage.googleapis.com` + credencial com API key +
`"provider":"google"`, `"model":"gemini-2.0-flash"`. Mesmo `object_list`,
mesma experiência no APEX. Voltar ao OCI GenAI se o bug for corrigido
antes da entrega.

### Plano C (já previsto no board, #34)

Vídeo demo gravado do fluxo de perguntas.

## Impacto no projeto

- M3 (Select AI) **continua viável** — a arquitetura não muda, só o provedor.
- O achado vira ponto da apresentação: bug de plataforma identificado,
  documentado com evidência pública e mitigado sem alterar o desenho.

## Referências

- [Thread do bug — Cloud Customer Connect](https://community.oracle.com/customerconnect/discussion/923511/ora-20404)
- [DBMS_CLOUD_AI — documentação oficial](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/dbms-cloud-ai-package.html)
- [Select AI — gerenciamento de perfis](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/select-ai-manage-profiles.html)

---

## Desfecho: o M3 funcionando

A rota via perfil `DBMS_CLOUD_AI` foi abandonada. A capacidade equivalente foi
reconstruída chamando o modelo diretamente por `DBMS_CLOUD.SEND_REQUEST` — o
mesmo pacote que a plataforma usa para acessar o Object Storage, e que funciona
normalmente.

### Como chegamos ao provedor que funciona

| Tentativa | Resultado |
|---|---|
| OCI Generative AI via `DBMS_CLOUD_AI` | ORA-20404 · `my$cloud_domain` não resolvido |
| Google via `DBMS_CLOUD_AI` | trava até o timeout de 5 min do gateway ORDS |
| `DBMS_CLOUD.SEND_REQUEST` para o mesmo host | responde em segundos ⇒ **o egress funciona; o defeito é do pacote de IA** |
| REST direto · `gemini-2.0-flash` e `2.5-flash/pro` | HTTP 429 e 404 — cota zerada no free tier |
| REST direto · `llama-3.3-70b-versatile` (Groq) | HTTP 400 — nome de modelo aposentado |
| REST direto · **`gemma-4-31b-it`** | **HTTP 200** ✅ |

### Implementação final

`sql/ia/02_ask_ai.sql` — pacote `PKG_ASK_AI`:

- chave e modelo em tabela de configuração (`CFG_AI`), fora do código;
- prompt montado **a partir dos comentários do dicionário** (`user_tab_comments`
  e `user_col_comments`) — melhorar a documentação de uma coluna melhora o SQL
  gerado, sem tocar no PL/SQL;
- parse ignorando as partes marcadas com `"thought": true` (raciocínio do
  modelo); a resposta é a parte sem a flag;
- guarda de segurança: só `SELECT` ou `WITH` passam; qualquer DDL/DML é
  bloqueado antes do `EXECUTE IMMEDIATE`;
- toda pergunta registrada em `LOG_ASK_AI` (auditoria e base da bateria de
  testes).

Integração no APEX (página "Pergunte à IA"): processo *Processing* chama
`pkg_ask_ai.gerar_sql_seguro`, grava o SQL em item de página, e a região de
resultado é um Classic Report do tipo *Function Body returning SQL Query* com
*Generic Column Names* ligado.

### Armadilhas encontradas na integração

Registradas porque custaram tempo e não são óbvias:

1. **Schema errado nos grants.** O parsing schema da aplicação é
   `WKSP_HOSPCHECK` (criado pelo APEX), não `HOSPCHECK_APP` (usuário criado por
   engano no início). Conferir em App Builder → Edit Application Properties →
   Security → Parsing Schema.
2. **Processo em *Before Header*** refazia a chamada à API a cada abertura da
   página. Movido para *Processing*, com condição de request, roda só ao
   clicar.
3. **Um processo "Clear Session State"** com escopo de página apagava o item
   logo depois de ele ser preenchido. O debug do APEX mostrou as duas linhas em
   sequência — sem ele, o diagnóstico seria impossível.
4. **`SQLERRM` não pode ir direto num comando SQL** — precisa passar por
   variável (ORA-00984).
5. **HTTP 400 "Request Header Or Cookie Too Large"** é problema de cookie do
   navegador, não da aplicação. Resolve em janela anônima.

### O que declarar na apresentação

O caminho oficial do produto está indisponível nesta plataforma por um defeito
que não é de configuração — reproduzido em duas instâncias, três configurações
e dois provedores, com relato público idêntico de terceiros. A funcionalidade
foi entregue por implementação própria sobre a mesma infraestrutura, com
transparência do SQL gerado e controle de segurança que o produto pronto não
oferece por padrão. Se a Oracle corrigir o pacote, voltar ao `DBMS_CLOUD_AI` é
trocar a configuração de um perfil.
