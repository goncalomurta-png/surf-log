---
# Estado Rodrigo — fonte para actualizar surf_log.html sem reler o ficheiro completo
# Actualizar este ficheiro SEMPRE que processar uma nova sessão
---

## HTML: linhas de referência (aproximadas — verificar com grep se necessário)
- Inserção nova sessão: logo após linha com `<div class="sec-label">Sessões registadas</div>` (~linha 480)
- Progressão formula: ~linha 816 (`prog-formula`)
- Progressão stars/notas: ~linhas 817–842
- SVG gráfico: ~linhas 868–1035 (actualizar eixo X ao adicionar sessão)
- KPIs header: ~linha 468 (kpi-row com Sessões / No Água / Spots / Pranchas)

## KPIs actuais
- Sessões: 5
- No Água: 10h50
- Spots únicos: 1
- Pranchas únicas: 1

## Sessões registadas (mais recente → mais antiga)
| html-id     | Nº | Data       | Spot                    | Wave Power   | Classe       | Rec. | Peso |
|-------------|----|------------|-------------------------|--------------|--------------|------|------|
| rodrigo-s4  | S5 | 10 Abr 26  | Milícias                | ~3 kW/m ef.  | Fracas       | ×1.0 | 0.35 |
| rodrigo-s3  | S4 | 08 Abr 26  | Milícias · Outside esq. | 17 kW/m      | Ideais       | ×0.6 | 0.60 |
| rodrigo-s0  | S3 | 07 Abr 26  | Milícias · Outside esq. | 45 kW/m      | Muito exig.  | ×0.4 | 0.22 |
| rodrigo-s1  | S2 | 04 Abr 26  | Milícias · Outside esq. | 7 kW/m       | Aceitáveis   | ×0.25| 0.16 |
| rodrigo-s2  | S1 | 03 Abr 26  | Milícias                | 4 kW/m       | Aceitáveis   | ×0.25| 0.05 |

Notas sobre IDs: s0/s1/s2 são as sessões originais (numeradas do topo para baixo quando foram criadas).
Os cards s0/s1/s2 NÃO têm id= no div — apenas data-sid nas estrelas.

## Progressão ponderada actual (10 Abr 26 · 5 sessões · peso total: 1.38)
| Competência      | Média ponderada | Estrelas |
|------------------|-----------------|----------|
| Leitura de onda  | 3.25 / 5        | ★★★☆☆   |
| Take-off         | 3.10 / 5        | ★★★☆☆   |
| Paddle           | 3.25 / 5        | ★★★☆☆   |
| Manobras         | 2.00 / 5        | ★★☆☆☆   |
| Equilíbrio       | 3.25 / 5        | ★★★☆☆   |
| Posicionamento   | 2.65 / 5        | ★★★☆☆   |

## Próxima sessão
- html-id a usar: **rodrigo-s5**
- Número da sessão: **S6**
- Recência após adicionar S6: s5=×1.0 · s4=×0.6 · s3=×0.4 · s0,s1,s2=×0.25

## Quiver (estado actual)
- Flowt 6'0" Premium Performance · 38L → **Em uso** · Última sessão: 10 Abr 26
- Flowt 6'6" Premium Performance · 43L → Referência
- Brain Child 5'8" FCS II · 38L · Hard epoxy → A testar (requer ≥10 kW/m)

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
