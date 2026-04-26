#!/usr/bin/env python3
"""
fetch_conditions.py — Recolha automática de condições de surf para São Miguel, Açores
Uso: python3 fetch_conditions.py 2026-04-08 09:00 12:00 milicias

Fontes:
  - Ondas + vento: Open-Meteo (gratuito, sem chave)
  - Marés: modelo harmónico para Ponta Delgada (M2+S2+N2+K1+O1)
"""

import urllib.request
import json
import math
import sys
from datetime import datetime, timedelta

# ─── Spots de São Miguel ────────────────────────────────────────────────────
SPOTS = {
    # Costa Sul
    'milicias':      {'lat': 37.750, 'lon': -25.670, 'nome': 'Milícias · Ponta Delgada',         'costa': 'sul'},
    'saoroque':      {'lat': 37.735, 'lon': -25.618, 'nome': 'São Roque · Ponta Delgada',         'costa': 'sul'},
    'aguadealto':    {'lat': 37.713, 'lon': -25.426, 'nome': 'Água de Alto · Vila Franca',        'costa': 'sul'},
    # Costa Norte
    'santabarbara':  {'lat': 37.823, 'lon': -25.525, 'nome': 'Santa Bárbara · Ribeira Grande',   'costa': 'norte'},
    'monteverde':    {'lat': 37.820, 'lon': -25.150, 'nome': 'Monteverde · Nordeste',             'costa': 'norte'},
    'ribeiraseca':   {'lat': 37.830, 'lon': -25.470, 'nome': 'Ribeira Seca · Farol do Cintrão',  'costa': 'norte'},
    # Costa Noroeste
    'mosteiros':     {'lat': 37.892, 'lon': -25.823, 'nome': 'Mosteiros · Costa Noroeste',        'costa': 'noroeste'},
}

# ─── Thresholds de corrente (offshore · calibrar com sessões) ────────────────────
# Rodrigo: Paddle 3.25, Posic 2.65 → limite estimado ~0.55 m/s
# Tomás:   Paddle 2.79, Posic 1.95 → limite estimado ~0.35 m/s

# Thresholds em m/s convertidos directamente dos kt documentados (1 kt = 0.5144 m/s)
# Milícias: 1.7 kt (R e T) · Norte: 1.0 kt R / 0.7 kt T · Mosteiros: 0.9 kt R / 0.6 kt T
# Norte (exposto): sem sessões ainda — conservador até haver dados
CORRENTE_THRESH = {
    # (lim_rodrigo, lim_tomas) em m/s — valor acima = aviso/bloqueio
    'milicias':     (0.875, 0.875),  # 1.7 kt · calibrado S4 (1.7 kt confirmou excesso)
    'saoroque':     (0.875, 0.875),  # 1.7 kt · extrapolado costa sul
    'aguadealto':   (0.875, 0.875),  # 1.7 kt · extrapolado costa sul
    'santabarbara': (0.515, 0.360),  # 1.0/0.7 kt · conservador, sem sessões
    'monteverde':   (0.515, 0.360),  # 1.0/0.7 kt · conservador (2 sessões à margem)
    'ribeiraseca':  (0.515, 0.360),  # 1.0/0.7 kt · conservador, sem sessões
    'mosteiros':    (0.463, 0.309),  # 0.9/0.6 kt · conservador, ponta rochosa
}

def avaliar_corrente(vel, spot_id):
    if vel is None: return '?', '?', 'desconhecida'
    lr, lt = CORRENTE_THRESH.get(spot_id, (0.50, 0.30))
    def grau(v, lim):
        if v < lim: return '✅'
        if v < lim * 1.35: return '⚠️'
        return '❌'
    cls = 'baixa' if vel < 0.20 else 'moderada' if vel < 0.40 else 'forte' if vel < 0.70 else 'muito forte'
    return grau(vel, lr), grau(vel, lt), cls

# ─── Modelo de marés para Ponta Delgada ─────────────────────────────────
# Timing: harmónico M2 (período 12.42h)
# Amplitude: modelo spring-neap calibrado a partir das sessões (precisão ±20%)
# Spring peak calibrado: 03 Abr 2026 → amplitude 1.26m; neap → 0.40m

def extremos_mare_open_meteo(ondas_json, data_str, h_ini, h_fim):
    """Detecta MA/MB a partir de sea_level_height_msl (Open-Meteo).
    Interpolação parabólica para precisão ~±15 min.
    Devolve (maximos, minimos) como listas de (datetime, altura_m)."""
    horas  = ondas_json['hourly']['time']
    niveis = ondas_json['hourly'].get('sea_level_height_msl', [])
    if not niveis or all(v is None for v in niveis):
        return [], []

    base  = datetime.strptime(data_str, '%Y-%m-%d')
    t_ini = base + timedelta(hours=h_ini - 6)
    t_fim = base + timedelta(hours=h_fim + 6)

    pts = []
    for h_str, n in zip(horas, niveis):
        if n is None:
            continue
        t = datetime.strptime(h_str[:16], '%Y-%m-%dT%H:%M')
        if t_ini <= t <= t_fim:
            pts.append((t, float(n)))

    maximos, minimos = [], []
    for j in range(1, len(pts) - 1):
        tp, hp = pts[j-1]; tc, hc = pts[j]; tn, hn = pts[j+1]
        denom = hp - 2*hc + hn
        if abs(denom) >= 1e-9:
            offset = -(hn - hp) / (2 * denom)
            t_ext  = tc + timedelta(hours=offset)
            h_ext  = round(hc - (hn - hp)**2 / (8 * denom), 2)
        else:
            t_ext, h_ext = tc, round(hc, 2)
        if hc >= hp and hc >= hn and (hc > hp or hc > hn):
            maximos.append((t_ext, h_ext))
        elif hc <= hp and hc <= hn and (hc < hp or hc < hn):
            minimos.append((t_ext, h_ext))

    return maximos, minimos

# ─── Open-Meteo ──────────────────────────────────────────────────────────────

def fetch_url(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())

def fetch_ondas(lat, lon, data):
    url = (f'https://marine-api.open-meteo.com/v1/marine'
           f'?latitude={lat}&longitude={lon}'
           f'&hourly=wave_height,wave_period,wave_direction,'
           f'swell_wave_height,swell_wave_period,swell_wave_direction,'
           f'ocean_current_velocity,ocean_current_direction,'
           f'sea_level_height_msl'
           f'&start_date={data}&end_date={data}'
           f'&timezone=Atlantic%2FAzores')
    return fetch_url(url)

def fetch_vento(lat, lon, data):
    url = (f'https://api.open-meteo.com/v1/forecast'
           f'?latitude={lat}&longitude={lon}'
           f'&hourly=wind_speed_10m,wind_direction_10m'
           f'&start_date={data}&end_date={data}'
           f'&timezone=Atlantic%2FAzores'
           f'&wind_speed_unit=kmh')
    return fetch_url(url)

# ─── Utilitários ─────────────────────────────────────────────────────────────

def wave_power(hs, t):
    return round(0.5 * hs ** 2 * t, 1) if hs and t else None

def graus_para_cardinal(graus):
    if graus is None:
        return '?'
    dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
            'S','SSW','SW','WSW','W','WNW','NW','NNW']
    return dirs[round(graus / 22.5) % 16]

def hora_para_idx(prefixo, horas_list):
    target = prefixo[:13]
    for i, h in enumerate(horas_list):
        if h.startswith(target):
            return i
    return 0

def media_intervalo(lista, i0, i1):
    vals = [v for v in lista[i0:i1+1] if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None

def dir_dominante(lista, i0, i1):
    vals = [v for v in lista[i0:i1+1] if v is not None]
    if not vals:
        return None
    sin_sum = sum(math.sin(math.radians(v)) for v in vals)
    cos_sum = sum(math.cos(math.radians(v)) for v in vals)
    return round(math.degrees(math.atan2(sin_sum, cos_sum)) % 360, 1)

# ─── Função principal ─────────────────────────────────────────────────────────

def obter_condicoes(data_str, hora_ini_str, hora_fim_str, spot_id):
    if spot_id not in SPOTS:
        raise ValueError(f'Spot desconhecido: {spot_id}')
    spot = SPOTS[spot_id]
    lat, lon = spot['lat'], spot['lon']
    h_ini = int(hora_ini_str.split(':')[0])
    h_fim = int(hora_fim_str.split(':')[0])

    print(f'A recolher condições para {spot["nome"]} · {data_str} {hora_ini_str}-{hora_fim_str}...')

    ondas = fetch_ondas(lat, lon, data_str)
    horas = ondas['hourly']['time']
    i0 = hora_para_idx(f'{data_str}T{hora_ini_str}', horas)
    i1 = hora_para_idx(f'{data_str}T{hora_fim_str}', horas)

    hs       = media_intervalo(ondas['hourly']['wave_height'], i0, i1)
    t_med    = media_intervalo(ondas['hourly']['wave_period'], i0, i1)
    sw_hs    = media_intervalo(ondas['hourly']['swell_wave_height'], i0, i1)
    sw_t     = media_intervalo(ondas['hourly']['swell_wave_period'], i0, i1)
    sw_dir_g = dir_dominante(ondas['hourly']['swell_wave_direction'], i0, i1)
    wp       = wave_power(hs, t_med)

    vento    = fetch_vento(lat, lon, data_str)
    v_spd    = media_intervalo(vento['hourly']['wind_speed_10m'], i0, i1)
    v_dir_g  = dir_dominante(vento['hourly']['wind_direction_10m'], i0, i1)

    curr_vel  = media_intervalo(ondas['hourly'].get('ocean_current_velocity', [None]*24), i0, i1)
    curr_dir  = dir_dominante(ondas['hourly'].get('ocean_current_direction', [None]*24), i0, i1)
    curr_r, curr_t, curr_cls = avaliar_corrente(curr_vel, spot_id)

    maximos, minimos = extremos_mare_open_meteo(ondas, data_str, h_ini, h_fim)
    base = datetime.strptime(f'{data_str}T{hora_ini_str}', '%Y-%m-%dT%H:%M')
    mb = min(minimos, key=lambda x: abs((x[0]-base).total_seconds()), default=None)
    ma = min(maximos, key=lambda x: abs((x[0]-base).total_seconds()), default=None)
    amplitude = round(ma[1] - mb[1], 2) if ma and mb else None

    return {
        'spot': spot['nome'], 'spot_id': spot_id,
        'data': data_str, 'hora_ini': hora_ini_str, 'hora_fim': hora_fim_str,
        'hs': hs, 'period': t_med, 'wave_power': wp,
        'swell_hs': sw_hs, 'swell_t': sw_t,
        'swell_dir': graus_para_cardinal(sw_dir_g), 'swell_dir_graus': sw_dir_g,
        'vento_kmh': v_spd,
        'vento_dir': graus_para_cardinal(v_dir_g), 'vento_dir_graus': v_dir_g,
        'mare_baixa_hora': mb[0].strftime('%H:%M') if mb else '?',
        'mare_alta_hora':  ma[0].strftime('%H:%M') if ma else '?',
        'mare_baixa_alt':  mb[1] if mb else None,
        'mare_alta_alt':   ma[1] if ma else None,
        'amplitude': amplitude,
        'corrente_ms':  curr_vel,
        'corrente_kt':  round(curr_vel * 1.944, 1) if curr_vel is not None else None,
        'corrente_dir': graus_para_cardinal(curr_dir),
        'corrente_cls': curr_cls,
        'corrente_r':   curr_r,
        'corrente_t':   curr_t,
    }

def ms_para_nos(vel):
    """Converte m/s para nós (1 m/s = 1.944 kt)."""
    if vel is None:
        return '?'
    return round(vel * 1.944, 1)

def imprimir_resumo(c):
    amp_str    = f"{c['amplitude']}m" if c['amplitude'] is not None else '?'
    mb_alt_str = f"~{c.get('mare_baixa_alt')}m" if c.get('mare_baixa_alt') is not None else '?'
    ma_alt_str = f"~{c.get('mare_alta_alt')}m" if c.get('mare_alta_alt') is not None else '?'
    wp = c['wave_power']
    cls = ('Fracas' if not wp or wp < 4 else 'Aceitaveis' if wp < 7 else
           'Boas' if wp < 10 else 'Ideais' if wp < 18 else
           'Exigentes' if wp < 35 else 'Muito exig.')
    curr_nos = ms_para_nos(c.get('corrente_ms', None))
    print(f"""
Condicoes: {c['spot']}
{c['data']}  {c['hora_ini']}-{c['hora_fim']}
--------------------------------------------
Wave Power : {c['wave_power']} kW/m  [{cls}]
Hs={c['hs']}m  T={c['period']}s
Swell      : {c['swell_dir']} ({c['swell_dir_graus']} graus)  Hs={c['swell_hs']}m
Vento      : {c['vento_kmh']} km/h  {c['vento_dir']} ({c['vento_dir_graus']} graus)
Mare baixa : {c['mare_baixa_hora']}  {mb_alt_str}
Mare alta  : {c['mare_alta_hora']}  {ma_alt_str}
Amplitude  : {amp_str}
Corrente   : {curr_nos} kt  {c.get('corrente_dir','?')}  [{c.get('corrente_cls','?')}]
  Rodrigo  : {c.get('corrente_r','?')}   Tomas: {c.get('corrente_t','?')}
--------------------------------------------
📡 Marés: Open-Meteo Marine sea_level_height_msl · interpolação parabólica ±15 min.
  Para planeamento crítico confirmar em hidrografico.pt.
--------------------------------------------""")

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print('Uso: python3 fetch_conditions.py YYYY-MM-DD HH:MM HH:MM spot_id')
        print('Spots disponiveis:', list(SPOTS.keys()))
        sys.exit(1)
    data_str, hora_ini, hora_fim, spot_id = sys.argv[1:5]
    c = obter_condicoes(data_str, hora_ini, hora_fim, spot_id)
    imprimir_resumo(c)
