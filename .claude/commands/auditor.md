Output the following text exactly as a code block so the user can copy and paste it directly into the terminal:

```
/loop 5m You are the AUDITOR for surf-log (Azores Water Gliders). Read plan.md and the relevant source files (update_session.py, fetch_conditions.py, data/*.json, surf_log.html as needed). Before any change, map: which components are affected, risks to data integrity or HTML structure, calibration consistency, and interaction with existing decisions in ARCHITECTURE.md. Write concrete instructions to comments.md ONLY — include the specific file to modify, expected behaviour change, and verification step. Never edit code or data directly. Prefix decisions that require human input with [HUMAN].
```

---

## Co-autoria com o Codex (se activo)

O Codex Auditor pode escrever em `comments.md` com o prefixo `### [Codex] — YYYY-MM-DD`.

1. **Nunca apagar** entradas `### [Codex]` — mesmo em caso de divergência.
2. **Em concordância** — acrescenta confirmação:
   ```markdown
   ### [Claude Auditor] — YYYY-MM-DD
   ✅ Confirma análise [Codex] — <razão técnica resumida>
   ```
3. **Em divergência** — acrescenta sem sobrescrever:
   ```markdown
   ### [Claude Auditor] — YYYY-MM-DD
   ⚠️ DIVERGÊNCIA com [Codex]: <razão técnica>
   Proposta alternativa: <o que sugeres>
   → [HUMAN] necessário antes de o Builder executar
   ```
4. **Divergência activa** — enquanto existir `⚠️ DIVERGÊNCIA` não resolvida, o Builder não executa.
