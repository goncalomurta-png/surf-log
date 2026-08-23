# Plan — Surf Log (Azores Water Gliders)
**Surfistas:** Rodrigo (11a) · Tomás (9a) · Spot: Milícias, Ponta Delgada, Açores  
**Última sessão:** Rodrigo S13 (rodrigo-s13) · Tomás S11 (tomas-s11) · 23 Mai 2026 · Sta. Bárbara  
**Última auditoria:** 2026-05-25 (iteração 6 · F.1 calc_matrix + S13/S11 + O.1 pendente)

---

## Estado actual

| Componente | Estado |
|---|---|
| surf_log.html | ✅ Sincronizado (S13 Rodrigo · S11 Tomás · 23 Mai 2026) · commit 6721027 |
| data/rodrigo.json | ✅ Completo (S0–S13, 14 sessões) · insert_before_id = rodrigo-s13 · ⚠️ next_sessao por corrigir (O.1) |
| data/tomas.json | ✅ Completo (S0–S11, 12 sessões) · insert_before_id = tomas-s11 · ⚠️ next_sessao por corrigir (O.1) |
| update_session.py | ✅ Bug acento corrigido (6fc528f) |
| validate_progression.py | ⚠️ Falha com KeyError:'surfer' — script desactualizado face ao schema JSON actual |
| fetch_conditions.py | ✅ Operacional (Open-Meteo) |
| Correlação Wave Power × Performance | r = 0.942 (6 pontos · recalcular com ≥2 novos) |

**Níveis actuais:**
- Rodrigo: Técnico Outside (S13 foi Sta. Bárbara Outside)
- Tomás: Autónomo Outside (S11 foi Sta. Bárbara Espuma)

---

## Bugs conhecidos

### B2 — recencia_ordem em next_sessao: não é actualizado pelo script ao adicionar sessão

**Sintoma:** Ao adicionar uma nova sessão, `next_sessao.recencia_ordem` não é actualizado automaticamente. O mapa continua a apontar para os html_ids anteriores, fazendo com que `validate_progression.py` atribua slots errados (s-0 aponta para sessão antiga).

**Causa:** O script `update_session.py` não tem lógica para fazer shift do recencia_ordem após inserir nova sessão em s-0.

**Fix sugerido:** Após inserir a nova sessão no JSON, fazer shift de todos os slots (s-0→s-1, s-1→s-2, etc.) e colocar o novo html_id em s-0. Garantir que o slot mais antigo (s-N) é removido se exceder o número de sessões existentes.

> **Nota:** B1 (acento surfer_id) foi corrigido em 2026-05-11 — commit `6fc528f`.

### G.1 — update_session.py não regenera radar+sparklines ("Evolução") · detectado 14 Ago 2026

**Sintoma:** ao correr o script, avisos `⚠ Secção Progressão não encontrada` / `⚠ SVG line chart não encontrado` / `⚠ evo-trend não encontrado`. Radar+sparklines ficam desactualizados a cada sessão nova, exigindo edição manual.

**Causa:** `V.2 · Remover Progressão + reordenar secções` (17 Mai 2026) substituiu a secção antiga por um card "Evolução" (radar+sparklines) sem actualizar `gerar_svg_line()`/`gerar_evo_trend()`/`gerar_prog_card()`.

**Instruções detalhadas:** ver `comments.md` → `G.1` (+ G.5 + G.6). Estado: `auditor_accepted` (22 Ago 2026 15:16).

**Auditoria [Claude Auditor]:** fórmulas reimplementadas de forma independente a partir dos JSONs — radar match exacto (2/2 atletas), sparklines 12/12, setas de tendência 12/12, valores+estrelas 12/12; nulls nunca desenhados a zero (Y dos pontos entre 8 e 40, `y=48` ausente); `spark-next` idênticos a HEAD e na mesma ordem; sem regressão em cards, KPIs, footer, prog-card, Condições preferidas ou balanço de `<div>`. G.3 resolvido na metade derivável. Abertos G.7 (scatter do Tomás uma sessão atrás — pré-existente, não causado por G.1) e G.8 (código morto). Ver `comments.md` → AUDIT_COMPLETE G.1.

**Evidência (Builder, 22 Ago 2026):**
1. *Reverse-engineering das fórmulas* (contra HTML actual + `progressao{}` dos 2 atletas, antes de escrever código):
   - Radar: hexágono centro (110,110), 6 eixos a 60°, `r = valor*18`. Confirmado ponto a ponto contra o polígono do atleta existente (Rodrigo e Tomás, 6/6 eixos batem certo).
   - Banda "esperada" (polígono tracejado): `midpoint = 2.5 + 0.5*índice_autonomia` (assistido=0…performer=3), banda=[mid-0.5,mid+0.5]. Confirmado exactamente com os 2 níveis reais (tecnico→3.0–4.0, autonomo→2.5–3.5). **Assistido/performer são extrapolação da fórmula, não têm dado real para confirmar** — documentado no código e no ARCHITECTURE.md.
   - Sparkline: `x = round(2 + i*96/(n-1))`, `y = 48 - valor*8`. Confirmado contra os pontos reais das 2 páginas (Leitura Rodrigo n=22 e Leitura Tomás n=11, todos os pontos batem certo).
   - Cores de banda (verde/laranja/vermelha → fill+stroke) e cores fixas por skill: extraídas dos 3 veredictos já presentes no HTML (Tomás tinha os 3: verde, laranja, vermelha).
2. *Implementação* — `gerar_evo_card(sd, nivel_prox_preservado, spark_next_preservados)` substitui as chamadas a `gerar_svg_line`/`gerar_evo_trend`/marcadores "Progressão" nos passos 3–5 de `update_surfer()`; localização do bloco por `find_block_end()` (balanceamento de `<div>`/`</div>`, não regex frágil) a partir da âncora `class="evo-card"`. `gerar_prog_card` não tocado (dead-code preservado, serve conceptualmente "Condições preferidas", que é HTML manual).
3. *G.5 aplicado* — metade esquerda (`nivel_atual`) gerada sempre a partir do JSON; metade direita (`nivel_proximo`) lida de `sd['nivel_proximo']` se existir, senão **preservada verbatim** do HTML anterior (extraída antes de substituir o bloco) com aviso `⚠ nivel_proximo ausente — preservado do HTML`. Nenhum dos 2 JSONs tem `nivel_proximo` ainda — aviso disparado nos 2 testes, texto preservado correcto.
4. *G.6 aplicado* — sparklines saltam pontos `null` (não desenham a zero); testado com Tomás onde Leitura/Manobras/Posicionamento têm os 3 últimos valores (`s17,s18,s19`) todos `null` — o traço salta directamente para o último ponto não-nulo bem anterior, sem crash e sem inventar queda a zero. Trend compara os 2 últimos valores não-nulos; `<2` não-nulos → `→`. Caso extremo (Tomás `s19` com os 6 skills `null`) gera o card sem excepção.
5. *Verificação matemática* — polígono do atleta gerado recalculado independentemente em Python a partir de `progressao{}` e comparado byte-a-byte com o SVG gravado: **match exacto** para Rodrigo e Tomás.
6. *Aplicado ao ficheiro real* — `surf_log.html` actual (25 sessões Rodrigo, 20 Tomás) tinha o card desactualizado (bug real, não só risco futuro); apliquei a substituição do `evo-card` nas 2 páginas directamente (com backup local antes, apagado depois de confirmar). `python3 scripts/update_session.py ambos` corrido a seguir sobre o ficheiro corrigido: validação OK, sem avisos de `evo-card`/`spark-next`, `sys.exit(1)` esperado (sem sessão nova) — sem regressão.
7. *Efeito lateral: G.3 resolvido automaticamente* — `evo-nivel-atual` do Tomás agora lê "Autónomo · Outside" (era "Autónomo · Inside", inconsistente com o JSON). Sem decisão `[HUMAN]` necessária para esta metade.
8. `docs/ARCHITECTURE.md` (secção "update_session.py — referência técnica") actualizada: lista de passos, fórmulas SVG do radar/sparkline, nota sobre `gerar_prog_card` não chamada, dependência `math` acrescentada.
9. Não tocado: `gerar_svg_line`, `gerar_evo_trend`, `gerar_prog_card` (definições mantidas, apenas deixaram de ser chamadas); `detect_spot_override()` (fix do Auditor).

### G.3 / G.4 — decisões do owner · 22 Ago 2026

**G.3** — Gonçalo: o Tomás **ainda não está autónomo**; evolução segue o caminho do Rodrigo. `tomas.nivel_atual` → `assistido/outside`; `nivel_proximo` → `autonomo/outside`. As 20 sessões ficam intactas (decisão explícita: não reescrever histórico). Rodrigo recebe `nivel_proximo: performer/outside` — proposta do Auditor, sujeita a veto. Estado: `planned`.

**G.4** — scatter fica com **todos os spots**, distinguidos por costa. Razão: o eixo X é `wp_ef` (já normalizado por costa), logo o gráfico é a ferramenta que valida esses factores; filtrar para Milícias deitaria fora os dados da costa norte, que ainda está por calibrar. Absorve a nota do rótulo "N sessões" que são pontos (de G.7). Estado: `planned`.

**G.9** — commit **e push** autorizados pelo owner dos 6 packages fechados (G.1, G.2, G.5, G.6, G.7, G.8). Só os 4 ficheiros modificados. Estado: `planned`.

**G.10** — os 4 ficheiros não rastreados ficam **suspensos**: o owner autorizou o commit deles sem saber que o repositório é público (`visibility: PUBLIC`). `premortem/continuidade_humana.md` discute os miúdos; `.gitignore` já exclui `data/`, `CLAUDE.md` e `comments*.md`, o que sugere que este material cai do mesmo lado. Devolvido `[HUMAN]`. **Resolvido 22 Ago:** o owner decidiu "apenas commit do habitual" — os 4 ficheiros não são commitados, nem agora nem depois, sem pedido explícito. Estado: `auditor_accepted` (decisão registada).

**G.3 (emenda)** — o owner vetou o `nivel_proximo` proposto para o Rodrigo. Fica `Técnico · Performer` preservado do HTML; o aviso de campo ausente continua a aparecer e é ruído esperado.

Instruções detalhadas em `comments.md`.

### G.2 — Cards de Agosto sob separador "Junho 2026" · detectado 22 Ago 2026

**Sintoma:** nas 2 páginas, S23/S24 (R) e S18/S19 (T) aparecem abaixo do separador `Junho 2026` e abaixo de uma sessão de Julho. Não existe separador `Agosto 2026`.
**Causa:** `insert_before_id` desactualizado (apontava a Junho) + `update_surfer()` insere depois do `month-sep` e nunca gera separadores.
**Instruções:** ver `comments.md` → `G.2`. Estado: `auditor_accepted` (22 Ago 2026 15:03).
**Auditoria:** ordem verificada de forma independente (monotonia de datas por página: R=25 OK, T=20 OK); 45 cards / 10 separadores / 0 ids duplicados; lógica de `update_surfer()` e guarda dos 3 casos conformes. Desequilíbrio `<div>` de +2 é pré-existente (igual em HEAD), não é regressão. Ver `comments.md` → AUDIT_COMPLETE G.2.

**Evidência (Builder, 22 Ago 2026):**
1. *Correcção de dados* — blocos `rodrigo-s24`/`s23` e `tomas-s19`/`s18` movidos (via script Python, cortados pelo `id=` do card seguinte) para acima do separador `Julho 2026`; `Agosto 2026` inserido antes deles. Ordem final verificada por `grep -n 'month-sep'`: Agosto→Julho→Junho→Maio→Abril em ambas as páginas. `session-card` count e `month-sep` count (10 total) inalterados — só reordenação, zero perda de conteúdo.
2. *Correcção estrutural* — `update_surfer()` agora compara `(ano,mês)` de `nova['data']` vs. da sessão-âncora (via JSON, não parse HTML); se diferente, gera `<div class="month-sep">` e recua a inserção com `re.search(r'<div class="month-sep">[^<]*</div>\s*$', ...)` para saltar um separador colado à âncora. Testado com sessão sintética (`update_surfer()` chamado directamente, sem tocar ficheiros reais): inserção de `rodrigo-s25` datada 5 Set 2026 antes de `rodrigo-s24` produz sequência `Setembro→s25→Agosto→s24→s23→Julho→s22→Junho→s21`; a mesma sessão datada 15 Ago (mesmo mês da âncora) não gera separador novo.
3. *Guarda em `validate_session_data()`* — testados os 3 casos isoladamente: `insert_id==sessoes[0]` (estado actual no disco) → `ok=True`, sem bloqueio; `insert_id==sessoes[1]` (correcto) → `ok=True`; `insert_id` desactualizado (nem sessoes[0] nem sessoes[1]) → `ok=False` com mensagem clara.
4. `python3 scripts/update_session.py ambos` sobre o estado real do disco: validação passa sem falsos positivos, `sys.exit(1)` esperado no aviso pré-existente "sessoes[0].html_id == insert_before_id" (nada para inserir) — sem regressão.
5. Não tocado: `detect_spot_override()` (fix do Auditor mantido intocado).

### G.3 — Nível do Tomás no card "Evolução" contradiz o JSON · detectado 22 Ago 2026

HTML: `Autónomo · Inside → Autónomo Outside`. JSON: `autonomo/outside`. Sub-caso de G.1.
Tem `[HUMAN]` pendente (qual o próximo nível do Tomás). Ver `comments.md` → `G.3`. Estado: `planned`.

### G.4 — Scatter rotulado "Milícias" inclui El Palmar / Monteverde / Sta. Bárbara · detectado 22 Ago 2026

25 pontos no gráfico, 15 são Milícias. Distorce a calibração wave-power↔performance (factor offshore→praia difere por costa).
Tem `[HUMAN]` pendente (filtrar vs. re-rotular). Ver `comments.md` → `G.4`. Estado: `planned`.

### G.7 — Scatter do Tomás uma sessão atrás · detectado 22 Ago 2026 (auditoria de G.1)

**Sintoma:** `perf_media()` devolvia `0` quando os 6 skills eram `null` (caso `tomas-s19`); `perf_to_cy(0)=190` fica fora do viewBox (altura 185) — o ponto ficaria invisível mesmo se fosse desenhado. Não causado por G.1, pré-existente.
**Instruções:** ver `comments.md` → `G.7`. Estado: `auditor_accepted` (22 Ago 2026 15:21).
**Auditoria:** ponto a `cy=190` fora do viewBox deixou de ser alcançável; contadores contam `<circle>` desenhados; disco coerente (R 25/25/25, T 19/19/19).

**Evidência (Builder, 22 Ago 2026):**
1. `perf_media()` devolve `None` (não `0`) quando não há skills avaliáveis. Único caller (scatter) confirmado por grep antes da mudança.
2. Passo "Scatter" em `update_surfer()`: se `perf_media(nova)` é `None`, não desenha ponto, emite `⚠ ... sem skills avaliáveis — ponto não adicionado`.
3. Contadores "N pontos"/"N sessões" passam a contar `<circle` desenhados no SVG, não `len(sessoes)` — evita nova divergência quando uma sessão fica sem ponto.
4. Testado: sessão sintética toda-`null` → sem ponto novo, sem `cy=190`, labels mantêm-se 19/19 coerentes; sessão sintética com skills reais → ponto novo, labels sobem para 20/20.
5. Estado real no disco (Tomás, 19 pontos/19/19) já estava internamente coerente com a nova regra — nada para corrigir nos dados, só no código (protege contra a próxima sessão nula).
6. `python3 scripts/update_session.py ambos` sobre disco real: sem regressão.

### G.8 — Código morto + frase errada em ARCHITECTURE.md · detectado 22 Ago 2026 (auditoria de G.1)

**Sintoma:** `gerar_prog_card`, `gerar_svg_line`, `gerar_evo_trend` (~110 linhas) deixaram de ser chamadas após G.1; `docs/ARCHITECTURE.md` dizia (incorrectamente, instrução do Auditor em G.1) que `gerar_prog_card` servia "Condições preferidas".
**Instruções:** ver `comments.md` → `G.8`. Estado: `auditor_accepted` (22 Ago 2026 15:21).
**Auditoria:** três funções removidas, `ast.parse` OK, sem referências pendentes, ARCHITECTURE.md corrigido; 2ª passagem aberta para 4 helpers + 1 constante órfãos.

**Evidência (Builder, 22 Ago 2026):**
1. Confirmado por grep: `gerar_prog_card`/`gerar_svg_line`/`gerar_evo_trend` sem nenhuma chamada restante no ficheiro. Removidas as 3 definições (mantidos os helpers `stars_locked`/`sessao_to_x`/`nivel_to_y`, fora do âmbito pedido — G.8 nomeou só as 3 funções).
2. `docs/ARCHITECTURE.md` corrigido: já não afirma que `gerar_prog_card` serve "Condições preferidas"; explica que essa secção é manual e as 3 funções foram removidas em G.8.
3. `python3 scripts/update_session.py ambos` sobre disco real após a remoção: sem regressão, sem erros de import/NameError.

**2ª passagem (Builder, 22 Ago 2026) — evidência:** removidos `SKILL_TREND` (constante), `nivel_to_y`, `sessao_to_x`, `fmt_abrev`, `stars_locked` — cada um confirmado sem outras referências por `grep` antes de apagar. `SKILL_NAMES` mantida (usada em `gerar_card`). Verificação independente por AST (`FunctionDef` vs `Call`, mesmo método do Auditor): lista de funções sem chamador = `[]`. `ast.parse` OK. `python3 scripts/update_session.py ambos` sobre disco real: sem regressão. Estado: `auditor_accepted` (22 Ago 2026 15:24).

**Auditoria [Claude Auditor]:** AST confirma 27 funções definidas e **zero sem chamador**; os 5 símbolos com 0 ocorrências; `SKILL_NAMES` viva (3) e `stars_interativas` viva (2); `ast.parse` OK, 968 linhas. HTML inalterado e coerente (45 cards, 10 separadores, 2 evo-card, 12 spark-card, scatter R 25/25 e T 19/19, balanço `<div>` igual a HEAD). Resíduo menor sem package próprio: `SKILL_DASHED` ficou órfã (2 ocorrências em HEAD → 1 agora, largada pela remoção de `gerar_svg_line`); `_RANK_EMOJI` já era órfã em HEAD, não é nossa. Ambas registadas em `comments.md` para irem à boleia da próxima task que toque no ficheiro.

---

## Calibração do Modelo — Plano de Acção

> **Fio condutor:** os modelos globais de ondas subestimam sistematicamente a energia nas Milícias. O objectivo é quantificar esse erro por direcção de swell e corrigir os factores offshore→praia em `fetch_conditions.py`.

### Problema identificado

As previsões de `wp_ef` (Wave Power efectivo) estavam 2–4× abaixo da realidade observada. Causa identificada:

1. **Open-Meteo** mostra sempre o swell de vento local (N/NE) como primário → ignora o swell W/SW/S que gera as ondas nas Milícias.
2. **CMEMS MFWAM** e **Stormglass** capturam SW1+SW2 mas subestimam o Hs offshore nas Ilhas dos Açores (efeito de ilha, resolução 0.083°).
3. **Factores offshore→praia** foram definidos empiricamente sem dados suficientes.

### Pipeline de calibração (criado 2026-05-11)

```
fetch_historical.py  →  data/backtest_cache.json  →  calibrate_factors.py
       ↓                                                       ↓
OM (sempre)                                        Ratios por direcção
CMEMS (≤10 dias)                                   factor_sugerido = f_actual × ratio_médio
Stormglass SW2 (budget 8 calls/run)                → actualizar fetch_conditions.py
```

**Fontes por ordem de qualidade (SW2):**
| Fonte | SW1 | SW2 | Limitação |
|-------|-----|-----|-----------|
| CMEMS MFWAM | ✅ | ✅ | Arquivo ~10 dias; subestima Hs |
| Stormglass | ✅ | ✅ | 10 calls/dia; histórico ilimitado |
| Open-Meteo | ✅ | ❌ | Apenas swell dominante; N/NE local swell |

### Resultados da calibração — 11 Mai 2026

**Base:** 22 entradas (11 sessões únicas × 2 surfistas) · 16 com dados Stormglass · 1 CMEMS (S11)

| Direcção | n sessões | Ratio médio | Factor actual | Factor sugerido | Confiança |
|----------|-----------|-------------|---------------|-----------------|-----------|
| N/NE (NNW vento local) | 13 | 3.18× | 0.25 | 0.79 | ⚠️ Baixa — ver nota |
| W/SW/WNW | 8 | 2.30× | 0.68 | 1.56 | Média (4 datas únicas) |
| S (T≥12s) | 1 | 3.04× | 0.90 | 2.74 | ⚠️ Muito baixa (1 ponto) |

**Acurácia de classe actual:** 2/22 (9%) → meta: ≥60% com 3+ pontos por bucket

> **Nota N/NE:** O ratio 3.18× para N/NE reflecte principalmente swell de vento local gerado perto das Milícias. O Stormglass atribui-lhe factor 0.25 (correcto — N/NE não forma picos na costa sul) mas a energia real vem do SW2 (W/SW). O problema é de **atribuição de componentes**, não do factor N/NE em si. A prioridade é garantir que o SW2 domina o cálculo quando a direcção primária é N/NE.

### Sessões em falta (Stormglass renova diariamente)

| ID | Data | Motivo | Acção |
|----|------|--------|-------|
| rodrigo-s1 / tomas-s1 | 2026-04-04 | Sem SG (calls esgotadas) | `fetch_historical.py` amanhã |
| rodrigo-s2 / tomas-s2 | 2026-04-03 | Sem SG | `fetch_historical.py` amanhã |
| rodrigo-s8 | 2026-04-26 | Sem SG | `fetch_historical.py` amanhã |

→ 3 calls Stormglass necessárias (sessões partilhadas contam como 1 call)

### Sessão S11 — Rodrigo · 11 Mai 2026 (pendente de registo)

- Spot: Milícias Outside · 14:00–16:00
- Prancha: CI Ultra Light (dimensões a confirmar com Gonçalo)
- Ondas: muito boas (pro surfers: 360 aéreo, surf no tubo, 10s de surf)
- 3–4 ondas apanhadas: 2× engolido pela espuma; 2× caiu após takeoff
- `wp_stored` preliminar: 8.5 kW/m (Boas) — confirmar com calibração
- Swell: N primário + S 14.2s secundário · CMEMS: 2.83 kW/m (subestimado ~3×)
- **Próximo passo:** propor estrelas → confirmar com Gonçalo → gravar JSON → correr script

### Próximos passos (por ordem)

- [ ] **Hoje** — Registar S11 (Rodrigo): propor estrelas, confirmar, actualizar JSON + script
- [ ] **Amanhã** — `python3 fetch_historical.py` (3 calls SG: Apr 3, 4, 26) → `python3 calibrate_factors.py`
- [ ] **Após calibração com 5+ datas W/SW** — actualizar factores em `fetch_conditions.py`
- [ ] Separar bucket NW (270–320°) de N/NE (>320°) quando houver dados suficientes
- [ ] Calibrar factores para costa norte (Monte Verde, Santa Bárbara) — sem dados ainda
- [ ] Fix ERA5 bbox: usar `area=[38.0,-26.5,37.0,-24.5]` (resolução mínima 0.5°)

---

## Roadmap

### P1 — Operacional (sessões)
- [ ] Adicionar sessões seguintes conforme ocorram
- [ ] Recalcular Pearson quando ≥2 novas sessões adicionadas
- [ ] Monitorizar transição de nível (4+ sessões consecutivas ★★★★+)

### P2 — Calibração (médio prazo)
- [x] Pipeline backtest: `fetch_historical.py` + `calibrate_factors.py` (2026-05-11)
- [x] Dados Stormglass históricos: 16/22 sessões cobertas
- [ ] Completar cobertura SW2 (3 sessões em falta: Apr 3, 4, 26)
- [ ] Aplicar factores corrigidos em `fetch_conditions.py` (aguarda ≥5 pontos W/SW)
- [ ] Calibrar limiares de corrente para Santa Bárbara, Monteverde, Ribeira Seca
- [ ] Calibrar factor para costa norte/noroeste

### P3 — Escalabilidade (>10 sessões ou >2 surfistas)
- [ ] Avaliar migração para Jinja2 (revisar com ≥20 sessões/surfista ou ≥3 surfistas)
- [x] Fallback fetch_conditions.py se Open-Meteo indisponível → `docs/condicoes_manuais.md`
- [ ] Exportar relatório por período

### P4 — Melhorias opcionais
- [ ] Responsiveness mobile <400px (media queries insuficientes)
- [ ] Histórico de fotos por sessão (screenshots Windy)

---

## Understanding restatement — G.2 + G.1 (Builder) · 22 Ago 2026 · estado: `understanding_confirmed`

> **[Claude Auditor] UNDERSTANDING_CONFIRMED G.2+G.1 · 22 Ago 2026 14:45** — restatement corresponde ao intent. Divergência da ordem dos cards (Agosto acima de Julho) e os 3 casos da guarda do anchor verificados no ficheiro. Builder libertado para `in_progress` em G.2 e depois G.1. G.3/G.4 permanecem `planned` — bloqueados `[HUMAN]`. Ressalva registada em `comments.md` → G.5.

**Âmbito desta sessão:** G.2 primeiro, depois G.1 (ordem sugerida pelo Auditor). **G.3 e G.4 não arrancam** — bloqueados `[HUMAN]`, dependem de decisão do Gonçalo.

**G.2 — separadores de mês (revisto após correcção do Auditor 22 Ago 14:30 — REV-CHECK COMMENTS-REV-20260822-1430):**
- Correcção de dados — não é só reposicionar separadores, é **mover os cards de Agosto**. Ordem final por página (newest-first): `Agosto 2026` → s24/s19 (9 Ago) → s23/s18 (8 Ago) → `Julho 2026` → s22/s17 (26 Jul) → `Junho 2026` → s21/s16 → …
  Operações: (a) recortar os blocos completos `id="rodrigo-s24"`…`id="rodrigo-s23"` (delimitar pelo `id=` do card seguinte, não por contagem de `</div>` — há `</div>` aninhados) e colar acima de `<div class="month-sep">Julho 2026</div>`; (b) inserir `<div class="month-sep">Agosto 2026</div>` imediatamente antes de `rodrigo-s24`; (c) mover `<div class="month-sep">Junho 2026</div>` para imediatamente antes de `rodrigo-s21`. Igual em Tomás (s19/s18/s17/s16).
- Correcção estrutural em `update_surfer()` (`scripts/update_session.py:378-385`): antes de inserir o card, calcular `mes_novo` a partir de `nova['data']` (fonte JSON) e `mes_ancora` a partir da sessão `insert_id` no JSON (não parse de HTML). Se diferentes → gerar `<div class="month-sep">{MESES_FULL[mes]} {ano}</div>` e recuar `div_start` para antes de qualquer `month-sep` colado ao card-âncora. Se iguais → comportamento actual (sem alteração).
- Guarda nova em `validate_session_data()` (~L754, junto à validação existente de `insert_before_id`), três casos distintos:
  - `len(sessoes) < 2` → não validar (primeira sessão do atleta, `sessoes[1]` daria `IndexError`).
  - `insert_before_id == sessoes[0]['html_id']` → não é erro desta guarda (caso "script corrido sem sessão nova", já avisado em `main():866-868`; não duplicar). É o caso actual no disco (`rodrigo-s24`/`tomas-s19`) — não deve bloquear.
  - `insert_before_id != sessoes[1]['html_id']` e `!= sessoes[0]['html_id']` → erro bloqueante (anchor desactualizado, causa raiz de G.2).
- Boundary: `gerar_prog_card` / scatter / KPIs / footer não são tocados nesta task.
- Ambiguidade: nenhuma detectada — instrução do Auditor é auto-contida.

**G.1 — card "Evolução" (radar+sparklines):**
- Nova função `gerar_evo_card(sd)` substitui os 3 blocos que hoje falham silenciosamente (`gerar_svg_line`, `gerar_evo_trend`, `gerar_prog_card` *nesta* secção — `gerar_prog_card` mantém-se intocado para a secção "Condições preferidas"/scatter, que é diferente e funciona).
- Âncora nova: `class="evo-card"` (em vez dos marcadores obsoletos `sec-label">Progressão</div>` / `Objetivos` / `evo-trend`).
- Deve emitir: radar SVG (6 eixos, polígono do atleta + polígono "esperado" tracejado por `nivel_atual.autonomia`), 6 `spark-card` (uma por skill, valor+estrelas+sparkline+trend+texto "próx. nível"), e `evo-nivel-row` (nível actual→próximo a partir de `nivel_atual`) — isto último também resolve G.3 estruturalmente, mas **não decide o texto do "próximo nível" do Tomás** (isso é o `[HUMAN]` de G.3, fora de âmbito).
- Fórmulas (raio radar, eixo Y sparkline) a obter por reverse-engineering dos valores actuais no HTML vs. `progressao{}`/`skills_hist` dos JSONs antes de escrever código — não inventar constantes.
- Verificação: correr `update_session.py rodrigo` e `tomas`, confirmar zero avisos dos 3 tipos antigos, e conferir 2-3 valores manualmente.
- `docs/ARCHITECTURE.md` (~L145) actualizado no fim, a descrever a nova âncora/função.
- Nota lateral já aplicada pelo Auditor em `detect_spot_override()` (filtro de `None` em `skills_hist`) — não mexer, não desfazer.

**Ambiguidade em aberto (G.1):** a fórmula exacta do eixo Y das sparklines não está fixada no comments.md (`Y=48-val*8` "aparece nalguns" — a confirmar por reverse-engineering, não assumida a priori).

| Step | Estado | Evidência |
|---|---|---|
| A2-F4 · docs/condicoes_manuais.md | `auditor_accepted` | criado; referência em CLAUDE.md linha 27 |
| B.1 · fix acento surfer_id update_session.py | `auditor_accepted` | `zip(surfers, sd_list)` linha 625; HTML 485 K sem duplicação |
| B.2 · actualizar insert_before_id JSONs | `auditor_accepted` | rodrigo→s10 · tomas→s9 verificados |
| B.3 · git commit + push S10/S9 | `auditor_accepted` | commit `6fc528f` · branch sincronizada |
| V.1 · Radar + Sparklines (ambos atletas) | `auditor_accepted` | radar valores corretos vs JSON; sparklines 2×3 com bandas e threshold; textos Tomás corrigidos; HTML corrompido L1777 corrigido · 17 Mai 2026 |
| A.1 · notas/cond_grid/horas s0–s4 (ambos) | `auditor_accepted` | zero campos vazios; rodrigo-s0 hora+trainer_comment confirmados; rodrigo-s3 wp_ef=17 ✓ · 17 Mai 2026 |
| V.2 · Remover Progressão + reordenar secções | `auditor_accepted` | Progressão removida (Rodrigo+Tomás); Evolução movida antes de Objetivos; CSS prog- classes mantidas (usadas em Swell×Perf) · 17 Mai 2026 |
| V.5 · Links pranchas + quiver sincronizado | `auditor_accepted` | CI OG Flyer card adicionado (Rodrigo·Principal·link CI); Flowt 6'0" → Tomás·Cedida; Joselito: "Shaper artesanal · cabo-verdiano" (sem website) · 17 Mai 2026 |
| V.3 · Matriz Wave Power gerada automaticamente | `auditor_accepted` | calc_matrix() + update_wave_matrix() em update_session.py; 7 tabelas actualizadas; 6 classes (Boas separadas); fallback por nível; célula acinzentada = inferido · 17 Mai 2026 |
| V.4 · spot_override: detecção + secção HTML | `auditor_accepted` | detect_spot_override() + agg_spot_overrides() + update_spot_overrides_section(); anchors HTML; rosa-badge; CSS so-*; 2 overrides detectados (s11+s12) · 17 Mai 2026 |
| V.6 · Reordenar secções macro (ambos atletas) | `auditor_accepted` | Rodrigo+Tomás: Evolução→Objetivos→Condições→Sessões; KPIs intactos; verificado com grep de sec-labels · 17 Mai 2026 |
| N.1 · Nível actual + próximo na secção Evolução | `auditor_accepted` | CSS evo-nivel-row/atual/seta/prox; Rodrigo "Autónomo·Outside→Técnico Inside"; Tomás "Autónomo·Inside→Autónomo Outside" · 18 Mai 2026 |
| N.2 · Numeração 1→4 Autonomia no Guia | `auditor_accepted` | 1·Assistido / 2·Autónomo / 3·Técnico / 4·Performer em nivel-name (L3146–3158) · 18 Mai 2026 |
| N.3 · Separadores de mês nas sessões (ambos) | `auditor_accepted` | CSS month-sep; Rodrigo: Maio(s13+s12→s9) Abril(s8→s0); Tomás: Maio(s11+s10→s7) Abril(s6→s0) · 18 Mai 2026 |
| S13/S11 · Sessões Sta. Bárbara · 23 Mai 2026 | `auditor_accepted` | JSON+HTML correctos; KPIs: R=14s/28h20/3spots; T=12s/22h20/2spots; month-sep Maio correcto · 25 Mai 2026 |
| F.1 · Fix calc_matrix() — mín 2 sessões + recência | `auditor_accepted` | _REC_W + calc_matrix() ponderada + _apply_monotonicity(); HTML regenerado (commit 6721027); R:⚠️✅✅✅❌; T:⚠️✅✅⚠️❌❌ · 25 Mai 2026 |
| S20+S21 · Rodrigo · Monteverde · 16 Jun 2026 | `completed` | S20 09:30 Ideais 11.9kW/m mar grande ~2.2m (hs_obs/modelo ratio 1.8×); S21 13:30 Ideais 10.3kW/m 2 ondas + trimming; progressão peso_total=3.283; sparklines+radar actualizados (22s); validate OK · 16 Jun 2026 |
| O.1 · Fix next_sessao após S13/S11 | `evidence_pending` | rodrigo: html_id=s14 n=15 s-0=s13; tomas: html_id=s12 n=13 s-0=s11; data/ no .gitignore — edição local · 25 Mai 2026 |
