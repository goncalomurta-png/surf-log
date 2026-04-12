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

# Thresholds calibrados (offshore Open-Meteo):
# Sul (Milicias/SaoRoque/AguaAlto): Rodrigo/Tomas surfaram OK ate 0.83 m/s
#   -> verde <0.85, amarelo <1.10, vermelho >=1.10
# Norte (exposto): sem dados ainda — conservador ate haver sessoes
CORRENTE_THRESH = {
    # (lim_rodrigo, lim_tomas) — valor acima = aviso/bloqueio
    'milicias':     (0.85, 0.85),   # calibrado: ambos OK ate 0.83 m/s
    'saoroque':     (0.85, 0.85),   # idem (costa sul similar)
    'aguadealto':   (0.85, 0.85),   # idem
    'santabarbara': (0.50, 0.35),   # norte exposto — conservador
    'monteverde':   (0.50, 0.35),
    'ribeiraseca':  (0.50, 0.35),
    'mosteiros':    (0.45, 0.30),   # ponta rochosa — mais conservador
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

_M2_PERIOD  = 12.4206   # horas
_M2_AMP     = 0.440     # metros (só para timing — não para amplitude absoluta)
_M2_PHASE   = 137.0     # graus (calibrado para Ponta Delgada)
_NIVEL_PDL  = 1.00      # nível médio acima do zero hidrográfico

# Spring-neap calibrado
_SPRING_PEAK = datetime(2026, 4, 3)  # pico de marés vivas mais próximo dos dados
_RANGE_VIV   = 1.26  # amplitude maré viva (m)
_RANGE_MORT  = 0.40  # amplitude maré morta (m)

def _m2_height(dt):
    """Variação M2 — usado apenas para encontrar timing de extremos."""
    epoca = datetime(2000, 1, 1)
    h = (dt - epoca).total_seconds() / 3600.0
    return _NIVEL_PDL + _M2_AMP * math.cos(math.radians(360.0 / _M2_PERIOD * h - _M2_PHASE))

def amplitude_prevista(data_str):
    """Amplitude spring-neap estimada para Ponta Delgada (±20%)."""
    dt = datetime.strptime(data_str, '%Y-%m-%d')
    days = (dt - _SPRING_PEAK).total_seconds() / 86400.0
    phase = (days % 14.77) / 14.77
    mid = (_RANGE_VIV + _RANGE_MORT) / 2
    half = (_RANGE_VIV - _RANGE_MORT) / 2
    return round(mid + half * math.cos(2 * math.pi * phase), 2)

def encontrar_extremos_mare(data_str, h_ini, h_fim):
    """Encontra horários de maré alta e baixa em torno da sessão."""
    base = datetime.strptime(data_str, '%Y-%m-%d')
    pontos = [(base + timedelta(minutes=m), _m2_height(base + timedelta(minutes=m)))
              for m in range(-480, (h_fim + 6) * 60, 10)]
    maximos, minimos = [], []
    for i in range(1, len(pontos) - 1):
        t, h = pontos[i]
        if h > pontos[i-1][1] and h > pontos[i+1][1]:
            maximos.append((t, h))
        elif h < pontos[i-1][1] and h < pontos[i+1][1]:
            minimos.append((t, h))
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
           f'ocean_current_velocity,ocean_current_direction'
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

    maximos, minimos = encontrar_extremos_mare(data_str, h_ini, h_fim)
    base = datetime.strptime(f'{data_str}T{hora_ini_str}', '%Y-%m-%dT%H:%M')
    mb = min(minimos, key=lambda x: abs((x[0]-base).total_seconds()), default=None)
    ma = min(maximos, key=lambda x: abs((x[0]-base).total_seconds()), default=None)
    amplitude = round(ma[1] - mb[1], 2) if ma and mb else None

    amp_est = amplitude_prevista(data_str)
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
        'amplitude': amp_est,
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
    amp_str = f"{c['amplitude']}m" if c['amplitude'] is not None else '?'
    wp = c['wave_power']
    cls = ('Fracas' if not wp or wp < 4 else 'Aceitaveis' if wp < 7 else
           'Boas' if wp < 10 else 'Ideais' if wp < 18 else
           'Exigentes' if wp < 35 else 'Muito exig.')
    curr_ms  = c.get('corrente_ms', None)
    curr_nos = ms_para_nos(curr_ms)
    curr_ms_str = f"{curr_ms} m/s" if curr_ms is not None else '?'
    print(f"""
Condicoes: {c['spot']}
{c['data']}  {c['hora_ini']}-{c['hora_fim']}
--------------------------------------------
Wave Power : {c['wave_power']} kW/m  [{cls}]
Hs={c['hs']}m  T={c['period']}s
Swell      : {c['swell_dir']} ({c['swell_dir_graus']} graus)  Hs={c['swell_hs']}m
Vento      : {c['vento_kmh']} km/h  {c['vento_dir']} ({c['vento_dir_graus']} graus)
Mare baixa : {c['mare_baixa_hora']} (est.)
Mare alta  : {c['mare_alta_hora']} (est.)
Amplitude  : {amp_str} (est.)
Corrente   : {curr_ms_str} ({curr_nos} kt)  {c.get('corrente_dir','?')}  [{c.get('corrente_cls','?')}]
  Rodrigo  : {c.get('corrente_r','?')}   Tomas: {c.get('corrente_t','?')}
--------------------------------------------""")

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print('Uso: python3 fetch_conditions.py YYYY-MM-DD HH:MM HH:MM spot_id')
        print('Spots disponiveis:', list(SPOTS.keys()))
        sys.exit(1)
    data_str, hora_ini, hora_fim, spot_id = sys.argv[1:5]
    c = obter_condicoes(data_str, hora_ini, hora_fim, spot_id)
    imprimir_resumo(c)
