# ARCHITECTURE.md · Surf Log — Azores Water Gliders
_Documento de arquitectura e estado do projecto. Actualizar quando houver mudanças estruturais._

---

## Visão geral

Diário de surf de dois irmãos (Rodrigo, 11; Tomás, 9) que treinam nas Milícias, São Miguel, Açores.
Pai (Gonçalo) fornece os dados qualitativos; Claude processa e mantém o sistema.

**Stack**: HTML/CSS/JS estático + GitHub Pages · Python (fetch + build) · JSON (estado)

---

## Arquitectura actual (desde 18 Abr 2026)

```
sessions/*.md          ← Gonçalo preenche (input qualitativo)
fetch_conditions.py    ← Claude corre (Open-Meteo + sea_level_height_msl para marés)
        │
        ▼
data/rodrigo.json      ← Fonte de verdade (Claude actualiza)
data/tomas.json        ← Fonte de verdade (Claude actualiza)
        │
        ▼
update_session.py      ← Script de build (Claude corre)
        │
        ▼
surf_log.html          ← Output gerado · GitHub Pages
```

### Princípios
- **JSON como fonte de verdade**: o HTML é gerado, nunca editado directamente
- **Script cirúrgico**: actualiza secções específicas do HTML por string anchoring (não regenera o ficheiro todo)
- **Backup automático**: `update_session.py` faz `.html.bak` antes de cada execução

---

## Decisões de arquitectura

### Por que script cirúrgico e não template Jinja2?

Auditoria de 18 Abr 2026 concluiu que Jinja2 era prematuro para a escala actual (2 surfistas, 6 sessões). Razões:

| Factor | Detalhe |
|--------|---------|
| Escala | Jinja2 justifica-se com 3+ surfistas ou 20+ sessões |
| Dados históricos | s0/s1/s2 têm dados incompletos no JSON — template exigiria lógica condicional complexa |
| SVG em template | Loops Jinja2 com 6 skills × n sessões × 2 charts × 2 surfistas = frágil e difícil de debugar |
| ROI | Script cirúrgico resolve 80% do problema em 20% do esforço (2–3h vs 10h) |

**Revisitar esta decisão quando:** ≥3 surfistas ou ≥20 sessões por surfista.

### Por que skills_hist como array no JSON?

O SVG line chart redistribui os X de todas as sessões quando se adiciona uma nova. Não é possível simplesmente "acrescentar um ponto" — é necessário recalcular todos os pontos. O script precisa dos valores históricos de todas as sessões para reconstruir o SVG. Guardar no JSON evita ter de parsear o HTML ou o SVG.

### Por que o scatter usa interpolação linear por segmentos (piecewise)?

O eixo X do scatter (Wave Power) não é linear nem logarítmico puro — a escala visual foi desenhada à mão para dar mais espaço à zona de surf habitual (2–18 kW/m). A interpolação piecewise entre os âncoras (0→45px, 2→56, 4→66, 18→140, 35→231, 50→310) é a única forma de replicar fielmente a escala existente.

---

## Estado actual dos dados (18 Abr 2026)

### Sessões registadas: 6 por surfista (S1–S6)

| Session | Data | WP ef. | Classe | skills_hist | div_id |
|---------|------|--------|--------|-------------|--------|
| s2 | 03 Abr | 4 kW/m | Aceitáveis | ✅ | false |
| s1 | 04 Abr | 7 kW/m | Aceitáveis | ✅ | false |
| s0 | 07 Abr | 45 kW/m | Muito exig. | ✅ | false |
| s3 | 08 Abr | 17 kW/m | Ideais | ✅ | true |
| s4 | 10 Abr | 3 kW/m | Fracas | ✅ | true |
| s5 | 18 Abr | 4.5 kW/m | Aceitáveis | ✅ + skills completo | true |

**Nota sobre div_id:** s0/s1/s2 não têm `id=` no div raiz do card (apenas `data-sid` nas stars). s3/s4/s5 têm `id=`. Sessões futuras (s6+) geradas pelo script terão sempre `id=`.

### Progressão actual

| | Rodrigo | Tomás |
|--|---------|-------|
| Leitura onda | ★★★★ (3.56) | ★★★★ (3.70) |
| Take-off | ★★★ (3.08) | ★★★ (2.88) |
| Paddle | ★★★★ (3.56) | ★★★ (3.23) |
| Manobras | ★★ (2.00) | ★★ (2.23) |
| Equilíbrio | ★★★ (3.11) | ★★★★ (3.89) |
| Posicionamento | ★★★ (3.16) | ★★ (1.89) |
| Peso total | 2.08 | 2.08 |

---

## Política de null (skills não observáveis)

Skills com `val = null` são **excluídas** da média ponderada (numerador e denominador reduzidos pelo mesmo peso). `skills_hist` fornece a série contínua para o SVG — contém valores plausíveis imputados e nunca null. `skills.*.val` é a fonte qualitativa/quantitativa real.

## Reconciliação 22 Abr 2026 — Escala de recência

A escala de recência foi clarificada de `s-0=1, s-1=0.6, s-2=0.4, s-3+=0.25` (plateau antigo) para a curva granular:

| s- | rec |
|----|-----|
| 0 | 1.00 |
| 1 | 1.00 |
| 2 | 0.60 |
| 3 | 0.40 |
| 4 | 0.25 |
| 5 | 0.15 |
| 6 | 0.10 |
| 7 | 0.07 |
| 8 | 0.05 |
| 9 | 0.03 |
| 10+ | 0.02 (floor) |

`peso_total` passou de 1.61 (mistura de escalas) para **2.08**. Nenhuma estrela mudou na reconciliação.

---

## Calibrações do modelo de condições

### Factor offshore→praia (costa sul São Miguel)
- **W/WNW (<320°)**: 0.65–0.72 — calibrado empiricamente (múltiplas sessões)
- **NNW/N (≥320°)**: 0.25 — swell de norte não forma picos na costa sul
- **S**: 0.70–0.90 — exposição directa; T≥12s → factor próximo de 0.90 (calibrado 18 Abr S+NW manhã)
- **Limite crítico**: ~320° — abaixo usa 0.65, acima usa 0.25

### Corrente — limiares por spot
| Spot | Limiar R | Limiar T | Estado |
|------|----------|----------|--------|
| Milícias | 1.7 kt | 1.7 kt | Calibrado (6 sessões OK até 1.6 kt) |
| Costa norte | 1.0 kt | 0.7 kt | Conservador — sem sessões |
| Mosteiros | 0.9 kt | 0.6 kt | Conservador — ponta rochosa |

### Pearson (Wave Power × Performance) — 6 pontos
- r = 0.942 (muito forte) — WP é o factor dominante
- Maré: r = −0.20 (marginal)
- ⚠ Recalibrar com mais sessões

---

## update_session.py — referência técnica

### O que actualiza (por ordem de execução)
1. **Card de sessão** — gera HTML completo, insere antes de `html.insert_before_id`
2. **KPIs** — regex por label dentro da região do surfista
3. **Prog-card** — substitui bloco completo entre âncoras "Progressão" e "Objetivos"
4. **SVG line chart** — reconstrói SVG inteiro com todos os pontos (viewBox dinâmico)
5. **Evo-trend** — recalcula histórico e setas ↑↓→ por skill
6. **Evo-sessions-label** — "N sessões · Mmm AAAA"
7. **Scatter** — insere novo ponto; actualiza "N pontos" e "N sessões"
8. **Footer** — actualiza data
9. **Quiver** — actualiza "Última sessão"

### Fórmulas SVG
```python
# Line chart
y = 160 - (nivel - 1) * 35          # nível 1–5 → pixel (1→160, 5→20)
x = round(50 + i * 325 / (n - 1))   # sessão i de n → pixel (distribuição uniforme)

# Scatter
# Eixo X: piecewise linear entre âncoras [(0,45),(2,56),(4,66),(18,140),(35,231),(50,310)]
y = round(155 - (perf_media - 1) * 35)  # perf 1–5 → pixel (5→15, 1→155)
```

### Dependências (stdlib apenas — sem pip install)
`sys · json · re · shutil · pathlib · datetime`

---

## Roadmap

| Horizonte | Acção | Trigger |
|-----------|-------|---------|
| Próximas sessões | Nenhuma mudança estrutural | — |
| ≥10 sessões | Backfill completo de skills em s0/s1/s2 no JSON | Dados históricos incompletos podem causar imprecisão no Pearson |
| ≥3 surfistas ou ≥20 sessões/surfista | Avaliar migração para Jinja2 | ROI positivo nessa escala |
| Novo spot com sessões | Calibrar factor offshore→praia e limiar de corrente | Primeira sessão real no spot |

---

_Actualizado: 18 Abr 2026 · Migração para update_session.py (script cirúrgico) · 6 sessões/surfista_
