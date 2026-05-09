# Plan — Surf Log (Azores Water Gliders)
**Surfistas:** Rodrigo (11a) · Tomás (9a) · Spot: Milícias, Ponta Delgada, Açores  
**Última sessão:** Rodrigo S10 (rodrigo-s9) · 9 Mai 2026 · Tomás S9 (tomas-s8) · 9 Mai 2026  
**Última auditoria:** 2026-05-06 (premortem · F2/F3/F4 · reorganização raiz)

---

## Estado actual

| Componente | Estado |
|---|---|
| surf_log.html | ✅ Sincronizado (S10/S9) |
| data/rodrigo.json | ✅ Completo (S0–S9) |
| data/tomas.json | ✅ Completo (S0–S8) |
| update_session.py | ⚠️ Bug iCloud subprocess — ver secção Bugs |
| validate_progression.py | ✅ Operacional (validação pesos e médias) |
| fetch_conditions.py | ✅ Operacional (Open-Meteo) |
| Correlação Wave Power × Performance | r = 0.942 (6 pontos · recalcular com ≥2 novos) |

**Níveis actuais:**
- Rodrigo: Técnico Inside (sessão S10 foi Inside — Outside flat com swell N)
- Tomás: Autónomo Inside (sessão S9 foi Inside)

---

## Bugs conhecidos (para corrigir em sessão Auditor/Builder)

### B1 — update_session.py: `id="page-tomas"` retorna -1 em subprocess iCloud

**Sintoma:** Ao correr `python3 update_session.py` normalmente (subprocess), a função que procura `id="page-tomas"` no HTML obtém `p_start = -1`, fazendo com que todas as actualizações da secção Tomás sejam silenciosamente ignoradas. A secção Rodrigo funciona correctamente.

**Causa suspeita:** O iCloud Drive pode servir uma versão do ficheiro diferente da que está em disco quando lido via path de filesystem normal em subprocess. O script lê `surf_log.html` como `open(BASE / 'surf_log.html').read()`, mas em contexto iCloud a string retornada pode estar truncada ou ter encoding diferente.

**Evidência:** Debug print mostrou `len(html)` consistente, mas `html.find('id="page-tomas"')` = -1 mesmo com a string presente no ficheiro. O método `open().read()` em subprocess não encontra o marcador; o mesmo conteúdo lido com `git show HEAD:surf_log.html` funciona.

**Workaround aplicado:** Importar as funções de `update_session.py` directamente (não via subprocess) e passar o HTML lido de `git show HEAD:surf_log.html`. Funciona correctamente.

**Fix sugerido:** Substituir a leitura directa de `surf_log.html` no script por `subprocess.run(['git', 'show', 'HEAD:surf_log.html'], ...)` ou forçar re-leitura via `pathlib.Path.read_bytes().decode('utf-8')` com gestão explícita de encoding. Investigar se o problema é encoding, newlines (CRLF vs LF), ou BOM introduzido pelo iCloud sync.

### B2 — recencia_ordem em next_sessao: não é actualizado pelo script ao adicionar sessão

**Sintoma:** Ao adicionar uma nova sessão, `next_sessao.recencia_ordem` não é actualizado automaticamente. O mapa continua a apontar para os html_ids anteriores, fazendo com que `validate_progression.py` atribua slots errados (s-0 aponta para sessão antiga).

**Causa:** O script `update_session.py` não tem lógica para fazer shift do recencia_ordem após inserir nova sessão em s-0.

**Fix sugerido:** Após inserir a nova sessão no JSON, fazer shift de todos os slots (s-0→s-1, s-1→s-2, etc.) e colocar o novo html_id em s-0. Garantir que o slot mais antigo (s-N) é removido se exceder o número de sessões existentes.

---

## Roadmap

### P1 — Operacional (sessões)
- [ ] Adicionar sessões seguintes conforme ocorram
- [ ] Recalcular Pearson quando ≥2 novas sessões adicionadas
- [ ] Monitorizar transição de nível (4+ sessões consecutivas ★★★★+)

### P2 — Calibração (médio prazo)
- [ ] Afinar factores offshore→praia com novos dados
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

## Log de steps (últimas iterações · histórico em `comments_archive.md`)

| Step | Estado | Evidência |
|---|---|---|
| A2-F2 · pre-flight anchors update_session.py | `completed` | `preflight_anchors()` linha 548; abort `✗ PRE-FLIGHT FALHOU` |
| A2-F3 · validate_progression.py | `completed` | recalcula peso_total + médias; imprime divergências |
| A2-F4 · docs/condicoes_manuais.md | `completed` | criado; referência em CLAUDE.md linha 27 |
