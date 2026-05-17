# Plan — Surf Log (Azores Water Gliders)
**Surfistas:** Rodrigo (11a) · Tomás (9a) · Spot: Milícias, Ponta Delgada, Açores  
**Última sessão:** Rodrigo S10 (rodrigo-s10) · 10 Mai 2026 · Tomás S9 (tomas-s9) · 10 Mai 2026  
**Última auditoria:** 2026-05-11 (iteração 5 · fix acento surfer_id · commit 6fc528f)

---

## Estado actual

| Componente | Estado |
|---|---|
| surf_log.html | ✅ Sincronizado (S10 Rodrigo · S9 Tomás · 10 Mai 2026) · 485 K |
| data/rodrigo.json | ✅ Completo (S0–S10) · insert_before_id = rodrigo-s10 |
| data/tomas.json | ✅ Completo (S0–S9) · insert_before_id = tomas-s9 |
| update_session.py | ✅ Bug acento corrigido (6fc528f) |
| validate_progression.py | ✅ Operacional (validação pesos e médias) |
| fetch_conditions.py | ✅ Operacional (Open-Meteo) |
| Correlação Wave Power × Performance | r = 0.942 (6 pontos · recalcular com ≥2 novos) |

**Níveis actuais:**
- Rodrigo: Técnico Outside (zona base; sessão S10 foi Milícias Outside)
- Tomás: Assistido Outside (zona base; sessão S9 foi Milícias Outside)

---

## Bugs conhecidos

### B2 — recencia_ordem em next_sessao: não é actualizado pelo script ao adicionar sessão

**Sintoma:** Ao adicionar uma nova sessão, `next_sessao.recencia_ordem` não é actualizado automaticamente. O mapa continua a apontar para os html_ids anteriores, fazendo com que `validate_progression.py` atribua slots errados (s-0 aponta para sessão antiga).

**Causa:** O script `update_session.py` não tem lógica para fazer shift do recencia_ordem após inserir nova sessão em s-0.

**Fix sugerido:** Após inserir a nova sessão no JSON, fazer shift de todos os slots (s-0→s-1, s-1→s-2, etc.) e colocar o novo html_id em s-0. Garantir que o slot mais antigo (s-N) é removido se exceder o número de sessões existentes.

> **Nota:** B1 (acento surfer_id) foi corrigido em 2026-05-11 — commit `6fc528f`.

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

## Log de steps (últimas 5 · histórico em `comments_archive.md`)

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
