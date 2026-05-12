#!/usr/bin/env python3
"""
fetch_historical.py — recolhe dados de ondas históricos para todas as sessões.

Fontes e prioridade:
  1. Open-Meteo  : sempre (swell primário + Hs total)
  2. CMEMS MFWAM : automático para sessões dos últimos ~10 dias (SW1+SW2+WW)
  3. Stormglass  : automático para sessões sem SW2 no cache (10 calls/dia)
                   reserva 2 calls para fetch_conditions.py (previsões)

Guarda em data/backtest_cache.json. Re-executa preserva o cache.

Uso:
  python3 fetch_historical.py              # fetch inteligente (OM+CMEMS+SG auto)
  python3 fetch_historical.py --force      # re-fetch tudo
  python3 fetch_historical.py --no-sg      # desactiva Stormglass (se calls esgotados)
  python3 fetch_historical.py --sg-budget 5  # limita a 5 calls Stormglass nesta execução
"""
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_conditions import (
    fetch_ondas,
    fetch_cmems_waves,
    fetch_stormglass_swell2,
    media_intervalo,
    dir_dominante,
    hora_para_idx,
    factor_swell,
    graus_para_cardinal,
    SPOTS,
)

CACHE_FILE   = Path('data/backtest_cache.json')
DATA_DIR     = Path('data')
CMEMS_WINDOW = 10   # dias de arquivo CMEMS anfc
SG_RESERVE   = 2    # calls reservadas para fetch_conditions (previsões)
SG_DAILY_MAX = 10

SPOT_MAP = {
    'milícias':      'milicias',
    'milicias':      'milicias',
    'monte verde':   'monteverde',
    'monteverde':    'monteverde',
    'santa bárbara': 'santabarbara',
    'santa barbara': 'santabarbara',
    'mosteiros':     'mosteiros',
    'ribeira seca':  'ribeiraseca',
    'feteiras':      'feteiras',
    'pópulo':        'populo',
    'populo':        'populo',
    'belém':         'populo',
    'caloura':       'caloura',
    'são roque':     'saoroque',
    'sao roque':     'saoroque',
    'água de alto':  'aguadealto',
    'agua de alto':  'aguadealto',
}


def spot_id_from_name(spot_str):
    sl = spot_str.lower()
    for k, v in SPOT_MAP.items():
        if k in sl:
            return v
    return None


def days_ago(data_str):
    try:
        d = datetime.strptime(data_str, '%Y-%m-%d').date()
        return (date.today() - d).days
    except Exception:
        return 999


def session_group_key(data_str, hora_ini, spot_id):
    """Chave que agrupa sessões do mesmo momento (Rodrigo + Tomás na mesma água)."""
    return f'{data_str}|{hora_ini[:2]}|{spot_id}'


def load_sessions():
    """Carrega sessões únicas. Para Stormglass, sessões partilhadas (mesmo dia/hora/spot)
    contam como 1 call — ver sg_groups em main()."""
    seen_ids = set()
    sessions = []
    for json_file in sorted(DATA_DIR.glob('*.json')):
        if json_file.stem in ('backtest_cache',):
            continue
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
        except Exception:
            continue
        if 'sessoes' not in data:
            continue
        for s in data['sessoes']:
            sid = s['html_id']
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            spot_id = spot_id_from_name(s.get('spot', ''))
            if not spot_id:
                print(f'  [SKIP] {sid}: spot "{s.get("spot","")}" não mapeado')
                continue
            hora_ini = s.get('hora_inicio', '10:00')
            hora_fim = s.get('hora_fim',    '12:00')
            sessions.append({
                'id':        sid,
                'surfer':    data['surfer'],
                'data':      s['data'],
                'hora_ini':  hora_ini,
                'hora_fim':  hora_fim,
                'has_time':  bool(s.get('hora_inicio')),
                'spot_id':   spot_id,
                'spot_nome': s.get('spot', ''),
                'wp_stored': s.get('wp_ef'),
                'classe':    s.get('classe'),
                'cond_obs':  s.get('cond_obs'),
                'hs_obs':    s.get('hs_obs'),
                'sg_key':    session_group_key(s['data'], hora_ini, spot_id),
            })
    return sessions


def fetch_om(spot_id, data_str, hora_ini, hora_fim):
    spot = SPOTS[spot_id]
    lat, lon = spot['lat'], spot['lon']
    try:
        ondas  = fetch_ondas(lat, lon, data_str)
        horas  = ondas['hourly']['time']
        i0     = hora_para_idx(f'{data_str}T{hora_ini}', horas)
        i1     = hora_para_idx(f'{data_str}T{hora_fim}', horas)
        sw_hs  = media_intervalo(ondas['hourly']['swell_wave_height'],  i0, i1)
        sw_t   = media_intervalo(ondas['hourly']['swell_wave_period'],  i0, i1)
        sw_dir = dir_dominante(ondas['hourly']['swell_wave_direction'], i0, i1)
        hs_tot = media_intervalo(ondas['hourly']['wave_height'],        i0, i1)
        t_med  = media_intervalo(ondas['hourly']['wave_period'],        i0, i1)
        f      = factor_swell(spot_id, sw_dir, sw_t)
        wp_ef  = round(0.5 * sw_hs**2 * sw_t * f, 2) if (sw_hs and sw_t and f) else None
        wp_raw = round(0.5 * hs_tot**2 * t_med, 2)   if (hs_tot and t_med) else None
        return {
            'hs_tot': hs_tot, 't_med': t_med, 'wp_raw': wp_raw,
            'sw_hs': sw_hs, 'sw_t': sw_t,
            'sw_dir': sw_dir, 'sw_dir_c': graus_para_cardinal(sw_dir),
            'factor': f, 'wp_ef': wp_ef,
        }
    except Exception as e:
        return {'error': str(e)}


def fetch_cmems(spot_id, data_str, hora_ini, hora_fim):
    h_ini = int(hora_ini.split(':')[0])
    h_fim = int(hora_fim.split(':')[0])
    try:
        return fetch_cmems_waves(spot_id, data_str, h_ini, h_fim)
    except Exception:
        return None


def fetch_sg(spot_id, data_str, hora_ini, hora_fim):
    spot = SPOTS[spot_id]
    lat, lon = spot['lat'], spot['lon']
    h_ini = int(hora_ini.split(':')[0])
    h_fim = int(hora_fim.split(':')[0])
    try:
        return fetch_stormglass_swell2(lat, lon, data_str, h_ini, h_fim)
    except Exception:
        return None


def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding='utf-8'))
    return {}


def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def main():
    force      = '--force'  in sys.argv
    no_sg      = '--no-sg'  in sys.argv

    # budget Stormglass: por defeito deixa 2 calls para fetch_conditions
    sg_budget  = SG_DAILY_MAX - SG_RESERVE
    for arg in sys.argv:
        if arg.startswith('--sg-budget='):
            sg_budget = int(arg.split('=')[1])
    sg_used = 0

    sessions = load_sessions()
    cache    = load_cache()

    print(f'Sessões: {len(sessions)}  |  Cache: {len(cache)} entradas  |  '
          f'SG budget: {sg_budget} calls  |  force={force}')
    print()

    updated = 0
    for s in sessions:
        key   = s['id']
        entry = cache.get(key, {})
        age   = days_ago(s['data'])

        prefix = f'  {key} ({s["data"]} {s["hora_ini"]}–{s["hora_fim"]} · {s["spot_id"]}) [{age}d]'

        # ── Metadados da sessão (sempre actualizar para reflectir JSONs correntes) ──
        if entry.get('session') != s:
            entry['session'] = s
            updated += 1

        # ── Open-Meteo ──────────────────────────────────────────────────────
        if force or 'om' not in entry:
            print(f'{prefix}  OM...', end=' ', flush=True)
            entry['om']      = fetch_om(s['spot_id'], s['data'], s['hora_ini'], s['hora_fim'])
            print('OK' if 'error' not in entry['om'] else f'ERRO: {entry["om"].get("error","")[:40]}')
            time.sleep(0.2)
            updated += 1
        else:
            print(f'{prefix}  OM=cache', end='')

        # ── CMEMS (automático para sessões recentes) ─────────────────────────
        if age <= CMEMS_WINDOW and (force or 'cmems' not in entry):
            print(f'  CMEMS...', end=' ', flush=True)
            entry['cmems'] = fetch_cmems(s['spot_id'], s['data'], s['hora_ini'], s['hora_fim'])
            print('OK' if entry['cmems'] else 'sem dados')
            updated += 1
        elif age <= CMEMS_WINDOW:
            print(f'  CMEMS=cache', end='')

        # ── Stormglass SW2 (automático quando sem SW2 e budget disponível) ──
        has_sw2 = (entry.get('cmems') and entry['cmems'].get('sw2_hs')) \
               or entry.get('sg')
        needs_sg = not has_sw2 and not no_sg and sg_used < sg_budget

        if needs_sg and (force or 'sg' not in entry):
            print(f'  SG[{sg_used+1}/{sg_budget}]...', end=' ', flush=True)
            sg_result = fetch_sg(s['spot_id'], s['data'], s['hora_ini'], s['hora_fim'])
            entry['sg'] = sg_result
            if sg_result:
                sg_used += 1
                print(f'OK ({sg_result.get("swell2_dir","?")} {sg_result.get("swell2_hs","?")}m/{sg_result.get("swell2_t","?")}s)')
            else:
                print('sem dados (402 ou erro)')
            updated += 1
        elif entry.get('sg'):
            print(f'  SG=cache', end='')

        print()
        cache[key] = entry

    if updated:
        save_cache(cache)
        print(f'\nCache guardado: {CACHE_FILE}  ({updated} actualizações)')
    else:
        print('\nNada a actualizar — usa --force para re-fetch.')

    if sg_used > 0:
        print(f'Stormglass: {sg_used} calls usadas hoje (reservadas {SG_RESERVE} para previsões → restam {SG_DAILY_MAX - sg_used} no dia).')
    elif not no_sg:
        print(f'Stormglass: 0 calls usadas (todas as sessões já têm SW2 ou calls esgotadas).')

    print(f'\nPróximo passo: python3 calibrate_factors.py')


if __name__ == '__main__':
    main()
