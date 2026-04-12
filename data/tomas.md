---
# Estado Tomás — fonte para actualizar surf_log.html sem reler o ficheiro completo
# Actualizar este ficheiro SEMPRE que processar uma nova sessão
---

## HTML: linhas de referência (aproximadas — verificar com grep se necessário)
- Inserção nova sessão: logo após linha com `<div class="sec-label">Sessões registadas</div>` (~linha 1063)
- Progressão formula: ~linha 1397 (`prog-formula`)
- Progressão stars/notas: ~linhas 1398–1423
- SVG gráfico: ~linhas 1448–1615 (actualizar eixo X ao adicionar sessão)
- KPIs header: ~linha 1051 (kpi-row com Sessões / No Água / Spots / Pranchas)

## KPIs actuais
- Sessões: 5
- No Água: 9h50
- Spots únicos: 1
- Pranchas únicas: 1

## Sessões registadas (mais recente → mais antiga)
| html-id   | Nº | Data       | Spot                    | Wave Power   | Classe       | Rec. | Peso |
|-----------|----|------------|-------------------------|--------------|--------------|------|------|
| tomas-s4  | S5 | 10 Abr 26  | Milícias                | ~3 kW/m ef.  | Fracas       | ×1.0 | 0.35 |
| tomas-s3  | S4 | 08 Abr 26  | Milícias · Outside esq. | 17 kW/m      | Ideais       | ×0.6 | 0.60 |
| tomas-s0  | S3 | 07 Abr 26  | Milícias · Outside esq. | 45 kW/m      | Muito exig.  | ×0.4 | 0.22 |
| tomas-s1  | S2 | 04 Abr 26  | Milícias · Outside esq. | 7 kW/m       | Aceitáveis   | ×0.25| 0.16 |
| tomas-s2  | S1 | 03 Abr 26  | Milícias                | 4 kW/m       | Aceitáveis   | ×0.25| 0.05 |

Notas sobre IDs: s0/s1/s2 são as sessões originais (numeradas do topo para baixo quando foram criadas).
Os cards s0/s1/s2 NÃO têm id= no div — apenas data-sid nas estrelas.

## Progressão ponderada actual (10 Abr 26 · 5 sessões · peso total: 1.38)
| Competência      | Média ponderada | Estrelas |
|------------------|-----------------|----------|
| Leitura de onda  | 3.58 / 5        | ★★★★☆   |
| Take-off         | 2.79 / 5        | ★★★☆☆   |
| Paddle           | 2.79 / 5        | ★★★☆☆   |
| Manobras         | 1.79 / 5        | ★★☆☆☆   |
| Equilíbrio       | 3.58 / 5        | ★★★★☆   |
| Posicionamento   | 1.95 / 5        | ★★☆☆☆   |

## Próxima sessão
- html-id a usar: **tomas-s5**
- Número da sessão: **S6**
- Recência após adicionar S6: s5=×1.0 · s4=×0.6 · s3=×0.4 · s0,s1,s2=×0.25

## Quiver (estado actual)
- Ocean Storm 6'0" → **Em uso** · Última sessão: 10 Abr 26

## Factores de condições (para cálculo de peso)
| Classe       | Wave Power    | Factor |
|--------------|---------------|--------|
| Fracas       | < 4 kW/m      | 0.35   |
| Aceitáveis   | 4–7 kW/m      | 0.65   |
| Boas         | >7–10 kW/m    | 0.85   |
| Ideais       | >10–18 kW/m   | 1.00   |
| Exigentes    | >18–35 kW/m   | 0.70   |
| Muito exig.  | > 35 kW/m     | 0.55   |

Recência: ×1.0 (mais recente) · ×0.6 (s-1) · ×0.4 (s-2) · ×0.25 (s-3 e anteriores)
Peso sessão = Recência × Factor condições
