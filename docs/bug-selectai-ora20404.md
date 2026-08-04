# Bug de plataforma: ORA-20404 `my$cloud_domain` no Select AI (OCI GenAI)

**Status:** Rota 1 esgotada (3 variações falharam) · **Rota 2 (Gemini) acionada** — ver `sql/09_selectai_gemini.sql`
**Data:** 03/ago/2026 · **Afeta:** SPIKE Select AI (board #30) / módulo M3
**Ambiente:** ADB 23ai Always Free · região sa-saopaulo-1 · patch DBMS_CLOUD `PDBCS_260724`

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
