# CLAUDE.md · Surf Log — Azores Water Gliders

## Contexto do projecto
Diário de surf de dois irmãos (Rodrigo, 11 anos; Tomás, 9 anos) que treinam nas Milícias, Ponta Delgada, São Miguel, Açores.
O pai (Gonçalo) fornece os dados; Claude actualiza o HTML e mantém os ficheiros de estado.

## Ficheiros principais
- `surf_log.html` — ficheiro de visualização (abre no iPhone)
- `data/rodrigo.md` — estado actual do Rodrigo (IDs HTML, KPIs, progressão)
- `data/tomas.md` — estado actual do Tomás
- `data/condicoes_referencia.md` — histórico de condições + modelo de veredicto
- `sessions/rodrigo.md` — input de nova sessão do Rodrigo (Gonçalo preenche)
- `sessions/tomas.md` — input de nova sessão do Tomás
- `sessions/conditions/` — screenshots do Windy (formato YYYY-MM-DD.png)
- `WORKFLOW.md` — instruções detalhadas do processo

## Regras obrigatórias

### Ao processar uma nova sessão
1. Ler `sessions/rodrigo.md` ou `sessions/tomas.md`
2. Ler `data/rodrigo.md` ou `data/tomas.md` (NUNCA ler o HTML completo)
3. Interpretar o texto qualitativo do Gonçalo → propor estrelas (1–5) por competência
4. **Mostrar as estrelas ao Gonçalo para confirmar antes de escrever no HTML**
5. Após confirmação: fazer edições cirúrgicas no HTML (grep para encontrar linha exacta)
6. Actualizar `data/rodrigo.md` e `data/tomas.md`
7. Actualizar `data/condicoes_referencia.md` com os novos dados de condições
8. Limpar `sessions/rodrigo.md` e `sessions/tomas.md` → prontos para próxima sessão

### Edições no HTML — NUNCA ler o ficheiro inteiro
- Usar `grep -n` para encontrar a linha de inserção exacta
- Usar `sed -n 'X,Yp'` para ler só o trecho necessário
- Editar com Python ou sed targeted — nunca reescrever o ficheiro todo
- Pontos de inserção: ver `data/rodrigo.md` e `data/tomas.md` (secção "HTML: linhas de referência")

### Avaliação de condições (quando Gonçalo pede veredicto)
1. Identificar wave power, direcção swell, vento e amplitude de maré
2. Aplicar as regras em `data/condicoes_referencia.md` (por ordem de prioridade)
3. Dar veredicto: ❌ / ⚠️ / ✅ / ⚡ com justificação breve
4. Registar o dia em `data/condicoes_referencia.md` (mesmo sem sessão)

### Após cada nova sessão
- Recalcular Pearson em `data/condicoes_referencia.md` se tiver ≥2 novos pontos
- Verificar se os pesos dos factores mudaram

## Estrutura HTML — referência rápida

### IDs de sessão (próximos a usar)
- Rodrigo: `rodrigo-s5` (S6)
- Tomás: `tomas-s5` (S6)

### Fórmula progressão ponderada
Peso = Recência × Factor condições
- Recência: ×1.0 / ×0.6 / ×0.4 / ×0.25 (s-3 e anteriores)
- Condições: Fracas 0.35 · Aceitáveis 0.65 · Boas 0.85 · Ideais 1.0 · Exig. 0.70 · M.Exig. 0.55

### Cor do card de sessão
- `energy-fraca` → < 4 kW/m
- `energy-media` → 4–10 kW/m
- `energy-boa` → > 10 kW/m

### Cascade de actualizações por sessão
1. Novo card (inserir no topo da secção "Sessões registadas")
2. KPIs header (Sessões, No Água, Spots, Pranchas)
3. Progressão ponderada (prog-formula + skill-notes + estrelas locked)
4. Quiver (Última sessão da prancha usada)
5. Rodapé (data)
6. Gráfico SVG Swell×Performance (adicionar novo ponto)

## Língua
Sempre português de Portugal.
