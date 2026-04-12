# Workflow · Surf Log

## Estrutura da pasta
```
surf-log/
├── surf_log.html          ← ficheiro principal (abre no iPhone)
├── data/
│   ├── rodrigo.md         ← estado actual do Rodrigo (Claude mantém)
│   ├── tomas.md           ← estado actual do Tomás (Claude mantém)
│   └── condicoes_referencia.md  ← histórico de condições vs surf (Claude mantém)
├── sessions/
│   ├── rodrigo.md         ← TU preenches aqui os dados do Rodrigo
│   ├── tomas.md           ← TU preenches aqui os dados do Tomás
│   └── conditions/        ← screenshots do Windy (nome: YYYY-MM-DD.png)
└── WORKFLOW.md            ← este ficheiro
```

---

## Como adicionar uma nova sessão

### 1. Guardar o screenshot do Windy
- Guardar em `sessions/conditions/` com o nome `YYYY-MM-DD.png`

### 2. Preencher os ficheiros de sessão
- Abre `sessions/rodrigo.md` (sempre o mesmo ficheiro)
- Preenche com o que observaste — escreve livremente
- Idem para `sessions/tomas.md`

### 3. Dizer ao Claude para processar
Mensagem: **"processa as sessões pendentes"**

### O que o Claude faz:
1. Lê `sessions/rodrigo.md` e `sessions/tomas.md`
2. Interpreta o texto qualitativo → converte para estrelas (1–5) por competência
3. Mostra-te as estrelas propostas para confirmares
4. Após confirmação, edita `surf_log.html` de forma cirúrgica:
   - Insere o novo card de sessão no topo
   - Actualiza KPIs (sessões, horas, spots, pranchas)
   - Recalcula progressão ponderada
   - Actualiza Quiver e rodapé
   - Actualiza gráfico Swell × Performance
5. Actualiza `data/rodrigo.md`, `data/tomas.md`, `data/condicoes_referencia.md`
6. Limpa `sessions/rodrigo.md` e `sessions/tomas.md` → prontos para próxima sessão

---

## Avaliação de condições antes de ir à praia
Partilha um screenshot do Windy e diz **"vale a pena ir às Milícias?"**

Claude analisa wave power, swell e vento e dá veredicto imediato:
- ❌ Sem surf (~0 kW/m ou flat) 
- ⚠️ Marginal (2–4 kW/m ou vento sul forte)
- ✅ Surfável (4–18 kW/m + swell W/NW)
- ⚡ Exigente (>35 kW/m — discutir antes de ir)

---

## Fórmula de progressão ponderada
**Peso sessão = Recência × Factor condições**

| Recência       | Factor |   | Condições    | Wave Power    | Factor |
|----------------|--------|---|--------------|---------------|--------|
| S mais recente | ×1.0   |   | Fracas       | < 4 kW/m      | 0.35   |
| S-1            | ×0.6   |   | Aceitáveis   | 4–7 kW/m      | 0.65   |
| S-2            | ×0.4   |   | Boas         | >7–10 kW/m    | 0.85   |
| S-3 e antigas  | ×0.25  |   | Ideais       | >10–18 kW/m   | 1.00   |
|                |        |   | Exigentes    | >18–35 kW/m   | 0.70   |
|                |        |   | Muito exig.  | > 35 kW/m     | 0.55   |

**Wave Power** (se não fornecido): `P ≈ 0.5 × Hs² × T` (em kW/m)

---

## Cor da barra lateral do card de sessão
- `energy-fraca` (cinza) → < 4 kW/m
- `energy-media` (dourado) → 4–10 kW/m
- `energy-boa` (verde) → > 10 kW/m
