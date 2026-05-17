#!/usr/bin/env python3
"""validate_progression.py — valida pesos e médias de progressao nos JSONs.

Recalcula peso_total e médias por skill a partir dos dados brutos
e imprime divergências face aos valores armazenados em progressao{}.
Sai com código 0 se não houver divergências, 1 caso contrário.
"""

import json
import glob
import sys
from pathlib import Path

TOLERANCE = 0.02  # margem para erros de arredondamento acumulado
SKILLS = ["leitura", "takeoff", "paddle", "manobras", "equilibrio", "posicionamento"]
PROG_KEY = {
    "leitura":        "leitura_onda",
    "takeoff":        "takeoff",
    "paddle":         "paddle",
    "manobras":       "manobras",
    "equilibrio":     "equilibrio",
    "posicionamento": "posicionamento",
}


def slot_index(slot: str) -> int:
    """'s-0' → 0, 's-10+' → 10."""
    return 10 if slot.endswith("+") else int(slot.split("-")[1])


def rec_for_index(idx: int, table: dict) -> float:
    return table.get(min(idx, 10), 0.02)


def validate_surfer(path: str) -> tuple[str, list[str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    name = data["surfer"]
    errors = []

    factores    = data["factores_condicoes"]
    rec_table   = {slot_index(k): v for k, v in data["recencia"].items()}
    rec_ordem   = data["next_sessao"]["recencia_ordem"]
    id_to_slot  = {v: slot_index(k) for k, v in rec_ordem.items()}

    # Acumuladores
    peso_total  = 0.0
    skill_num   = {sk: 0.0 for sk in SKILLS}
    skill_den   = {sk: 0.0 for sk in SKILLS}

    for sess in data["sessoes"]:
        html_id = sess["html_id"]
        classe  = sess.get("classe")

        if not classe:
            errors.append(f"  [{html_id}] campo 'classe' em falta — sessão ignorada no cálculo")
            continue

        fator_entry = factores.get(classe)
        if fator_entry is None:
            errors.append(f"  [{html_id}] classe '{classe}' não encontrada em factores_condicoes")
            continue

        fator       = fator_entry["factor"]
        slot_idx    = id_to_slot.get(html_id, 10)
        rec_calc    = rec_for_index(slot_idx, rec_table)
        peso_calc   = rec_calc * fator

        # Verificar rec e peso armazenados
        stored_rec  = sess.get("rec")
        stored_peso = sess.get("peso")
        if stored_rec is not None and abs(stored_rec - rec_calc) > TOLERANCE:
            errors.append(
                f"  [{html_id}] rec: armazenado={stored_rec}, calculado={rec_calc:.4f}"
            )
        if stored_peso is not None and abs(stored_peso - peso_calc) > TOLERANCE:
            errors.append(
                f"  [{html_id}] peso: armazenado={stored_peso}, calculado={peso_calc:.4f}"
            )

        peso_total += peso_calc

        # Acumular skills (excluir null)
        for sk in SKILLS:
            val = sess.get("skills", {}).get(sk, {}).get("val")
            if val is not None:
                skill_num[sk] += val * peso_calc
                skill_den[sk] += peso_calc

    # Verificar peso_total
    stored_pt = data["progressao"]["peso_total"]
    if abs(stored_pt - peso_total) > TOLERANCE:
        errors.append(
            f"  peso_total: armazenado={stored_pt}, calculado={peso_total:.4f}"
        )

    # Verificar médias e estrelas por skill
    progressao = data["progressao"]
    for sk in SKILLS:
        pk = PROG_KEY[sk]
        if pk not in progressao:
            continue

        stored_media    = progressao[pk]["media"]
        stored_estrelas = progressao[pk]["estrelas"]

        if skill_den[sk] == 0:
            errors.append(f"  {sk}: denominador zero — nenhuma sessão com valor observável?")
            continue

        media_calc    = skill_num[sk] / skill_den[sk]
        estrelas_calc = round(media_calc)

        if abs(stored_media - media_calc) > TOLERANCE:
            errors.append(
                f"  {sk} média: armazenado={stored_media}, calculado={media_calc:.4f}"
            )
        if stored_estrelas != estrelas_calc:
            errors.append(
                f"  {sk} estrelas: armazenado={stored_estrelas}, calculado={estrelas_calc} "
                f"(média={media_calc:.4f})"
            )

    return name, errors


def main() -> int:
    json_files = sorted(glob.glob("data/*.json"))
    if not json_files:
        print("Nenhum ficheiro JSON encontrado em data/")
        return 1

    total_errors = 0
    for path in json_files:
        name, errors = validate_surfer(path)
        if errors:
            print(f"\n❌ {name} — {len(errors)} divergência(s):")
            for e in errors:
                print(e)
            total_errors += len(errors)
        else:
            print(f"✅ {name} — sem divergências")

    if total_errors:
        print(f"\nTotal: {total_errors} divergência(s) encontrada(s).")
        return 1

    print("\nTodos os surfistas: OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
