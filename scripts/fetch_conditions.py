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
import os
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

# ─── Pontos de referência offshore para CMEMS (fora da máscara de terra) ────────
# Célula afastada da ilha para capturar o swell sem sombra. Resolução CMEMS: ~9 km.
CMEMS_REF = {
    'milicias':     {'lat': 37.50, 'lon': -25.67},  # sul · 28 km offshore
    'saoroque':     {'lat': 37.50, 'lon': -25.62},  # sul
    'aguadealto':   {'lat': 37.50, 'lon': -25.43},  # sul
    'santabarbara': {'lat': 38.00, 'lon': -25.53},  # norte
    'monteverde':   {'lat': 38.00, 'lon': -25.15},  # norte
    'ribeiraseca':  {'lat': 38.00, 'lon': -25.47},  # norte
    'mosteiros':    {'lat': 37.92, 'lon': -26.00},  # noroeste
    'populo':       {'lat': 37.50, 'lon': -25.57},  # sul
    'caloura':      {'lat': 37.50, 'lon': -25.53},  # sul
    'feteiras':     {'lat': 37.50, 'lon': -25.73},  # sudoeste
}

def factor_swell(spot_id, dir_graus, period=None):
    """Factor offshore→praia para um swell na direcção dir_graus.
    dir_graus = direcção DE ONDE o swell vem (convenção meteorológica).
    Sul (Milícias): exposta a SW/W/S · bloqueada a N/NE pela ilha.

    Factores calibrados com 22 sessões (hs_obs vs hs_offshore CMEMS/OM):
      S T≥12s: 0.90  S T<12s: 0.85  (1 sessão — manter conservador)
      SW/W/WSW (225–290°): 1.0   calibrado f_real médio 1.42–1.87 · 4 sessões
      WNW/NW  (290–320°): 0.65  calibrado f_real 0.58 · 2 sessões
      NNW     (320–345°): 0.55  calibrado f_real 1.00 · 4 sessões (wrapping parcial)
      N/NNE/NE (345–90°): 0.35  calibrado f_real mediana 0.33 · 10 sessões puras N
      Costa norte NW/N/NE: 1.5  calibrado f_real 7.25 · 1 sessão (conservador)
    """
    if dir_graus is None:
        return None
    costa = SPOTS.get(spot_id, {}).get('costa', '')
    if costa == 'sul':
        if 135 <= dir_graus <= 225:              # S directo — exposição total
            return 0.90 if (period and period >= 12) else 0.85
        elif 225 < dir_graus < 290:              # SW / W / WSW — calibrado
            return 1.0
        elif 290 <= dir_graus < 320:             # WNW / NW — exposição parcial
            return 0.65
        elif 320 <= dir_graus < 345:             # NNW — wrapping parcial
            return 0.55
        elif 90 < dir_graus < 135:               # SE — refracção parcial costa este
            return 0.35
        else:                                    # N / NNE / NE (345–90°) — bloqueado
            return 0.35
    elif costa == 'norte':
        if dir_graus >= 270 or dir_graus <= 90:  # NW / N / NE — exposição directa
            return 1.5
        else:                                    # S não chega ao norte
            return 0.10
    elif costa == 'noroeste':
        if 225 <= dir_graus <= 360 or dir_graus <= 45:  # W / NW / N
            return 0.65
        else:
            return 0.20
    return None  # spot não calibrado

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

# ─── Copernicus Marine (CMEMS) — ondas completas ────────────────────────────────

def fetch_cmems_waves(spot_id, data_str, h_ini, h_fim):
    """Fetch wave partition data from CMEMS MFWAM.
    Usa ponto offshore de referência (CMEMS_REF) fora da máscara de terra.
    Devolve dict com sw1/sw2/ww ou None se falhar."""
    if spot_id not in CMEMS_REF:
        return None
    ref = CMEMS_REF[spot_id]
    lat_ref, lon_ref = ref['lat'], ref['lon']

    offset = _azores_utc_offset(data_str)
    h_ini_utc = h_ini - offset
    h_fim_utc = min(h_fim - offset, 23)
    start = f'{data_str}T{h_ini_utc:02d}:00:00'
    end   = f'{data_str}T{h_fim_utc:02d}:00:00'

    try:
        import copernicusmarine
        import numpy as np
        ds = copernicusmarine.open_dataset(
            dataset_id='cmems_mod_glo_wav_anfc_0.083deg_PT3H-i',
            variables=['VHM0','VHM0_SW1','VTM01_SW1','VMDR_SW1',
                       'VHM0_SW2','VTM01_SW2','VMDR_SW2',
                       'VHM0_WW','VTM01_WW','VMDR_WW'],
            minimum_latitude=lat_ref-0.05, maximum_latitude=lat_ref+0.05,
            minimum_longitude=lon_ref-0.05, maximum_longitude=lon_ref+0.05,
            start_datetime=start, end_datetime=end,
        )
    except Exception as e:
        print(f'  [CMEMS] erro: {e}')
        return None

    import numpy as np
    lats = ds.latitude.values
    lons = ds.longitude.values
    lat_idx = int(abs(lats - lat_ref).argmin())
    lon_idx = int(abs(lons - lon_ref).argmin())

    def avg_val(var):
        if var not in ds: return None
        vals = ds[var].values[:, lat_idx, lon_idx].astype(float)
        valid = vals[~np.isnan(vals)]
        return round(float(np.mean(valid)), 3) if len(valid) > 0 else None

    def avg_dir(var):
        if var not in ds: return None
        vals = ds[var].values[:, lat_idx, lon_idx].astype(float)
        valid = vals[~np.isnan(vals)]
        if len(valid) == 0: return None
        s = float(np.sum(np.sin(np.radians(valid))))
        c = float(np.sum(np.cos(np.radians(valid))))
        return round(float(np.degrees(np.arctan2(s, c))) % 360, 1)

    hs = avg_val('VHM0')
    if hs is None:
        return None

    sw1_hs = avg_val('VHM0_SW1'); sw1_t = avg_val('VTM01_SW1'); sw1_dir = avg_dir('VMDR_SW1')
    sw2_hs = avg_val('VHM0_SW2'); sw2_t = avg_val('VTM01_SW2'); sw2_dir = avg_dir('VMDR_SW2')
    ww_hs  = avg_val('VHM0_WW');  ww_t  = avg_val('VTM01_WW');  ww_dir  = avg_dir('VMDR_WW')

    def wp_ef_comp(hs_c, t_c, dir_c):
        if not hs_c or not t_c: return None
        f = factor_swell(spot_id, dir_c, t_c)
        if f is None: return None
        return round(0.5 * hs_c**2 * t_c * f, 2)

    wp1  = wp_ef_comp(sw1_hs, sw1_t, sw1_dir)
    wp2  = wp_ef_comp(sw2_hs, sw2_t, sw2_dir)
    f_ww = factor_swell(spot_id, ww_dir, ww_t)
    wp_ww = wp_ef_comp(ww_hs, ww_t, ww_dir) if (f_ww and f_ww >= 0.50) else None
    wp_total = round(sum(v for v in [wp1, wp2, wp_ww] if v), 2)

    return {
        'hs': hs,
        'sw1_hs': sw1_hs, 'sw1_t': sw1_t, 'sw1_dir': sw1_dir,
        'sw1_dir_c': graus_para_cardinal(sw1_dir),
        'sw1_factor': factor_swell(spot_id, sw1_dir, sw1_t), 'sw1_wp_ef': wp1,
        'sw2_hs': sw2_hs, 'sw2_t': sw2_t, 'sw2_dir': sw2_dir,
        'sw2_dir_c': graus_para_cardinal(sw2_dir),
        'sw2_factor': factor_swell(spot_id, sw2_dir, sw2_t), 'sw2_wp_ef': wp2,
        'ww_hs': ww_hs, 'ww_t': ww_t, 'ww_dir': ww_dir,
        'ww_dir_c': graus_para_cardinal(ww_dir), 'ww_factor': f_ww, 'ww_wp_ef': wp_ww,
        'wp_ef_total': wp_total,
        'ref_lat': float(lats[lat_idx]), 'ref_lon': float(lons[lon_idx]),
    }

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

# ─── Stormglass — segundo swell ─────────────────────────────────────────────────

def _azores_utc_offset(data_str):
    month = int(data_str.split('-')[1])
    return 0 if 4 <= month <= 10 else -1

def _load_stormglass_key():
    key = os.environ.get('STORMGLASS_API_KEY', '')
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith('STORMGLASS_API_KEY='):
                    return line.strip().split('=', 1)[1]
    except FileNotFoundError:
        pass
    return None

def _sg_val(entry, key):
    src = entry.get(key, {})
    for source in ('sg', 'noaa', 'meteo', 'icon'):
        if source in src and src[source] is not None:
            return src[source]
    vals = [v for v in src.values() if v is not None]
    return vals[0] if vals else None

def fetch_stormglass_swell2(lat, lon, data_str, h_ini, h_fim):
    key = _load_stormglass_key()
    if not key:
        return None
    offset = _azores_utc_offset(data_str)
    h_ini_utc = h_ini - offset
    h_fim_utc = h_fim - offset
    start = f"{data_str}T{h_ini_utc:02d}:00:00Z"
    end   = f"{data_str}T{h_fim_utc:02d}:00:00Z"
    params = 'secondarySwellHeight,secondarySwellDirection,secondarySwellPeriod'
    url = (f'https://api.stormglass.io/v2/weather/point'
           f'?lat={lat}&lng={lon}&params={params}&start={start}&end={end}')
    req = urllib.request.Request(url, headers={'Authorization': key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f'  [Stormglass] erro: {e}')
        return None
    hours = data.get('hours', [])
    if not hours:
        return None
    hs_list, dir_list, t_list = [], [], []
    for h in hours:
        hs_v  = _sg_val(h, 'secondarySwellHeight')
        dir_v = _sg_val(h, 'secondarySwellDirection')
        t_v   = _sg_val(h, 'secondarySwellPeriod')
        if hs_v  is not None: hs_list.append(hs_v)
        if dir_v is not None: dir_list.append(dir_v)
        if t_v   is not None: t_list.append(t_v)
    if not hs_list:
        return None
    avg_hs  = round(sum(hs_list) / len(hs_list), 2)
    avg_t   = round(sum(t_list)  / len(t_list),  2) if t_list else None
    avg_dir = dir_dominante(dir_list, 0, len(dir_list) - 1) if dir_list else None
    return {
        'swell2_hs': avg_hs,
        'swell2_dir_graus': avg_dir,
        'swell2_dir': graus_para_cardinal(avg_dir),
        'swell2_t': avg_t,
    }

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

    cmems = fetch_cmems_waves(spot_id, data_str, h_ini, h_fim)

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

    swell2 = fetch_stormglass_swell2(lat, lon, data_str, h_ini, h_fim)

    return {
        'spot': spot['nome'], 'spot_id': spot_id,
        'data': data_str, 'hora_ini': hora_ini_str, 'hora_fim': hora_fim_str,
        'hs': hs, 'period': t_med, 'wave_power': wp,
        'swell_hs': sw_hs, 'swell_t': sw_t,
        'swell_dir': graus_para_cardinal(sw_dir_g), 'swell_dir_graus': sw_dir_g,
        'swell2': swell2,
        'cmems': cmems,
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
    curr_nos = ms_para_nos(c.get('corrente_ms', None))
    cmems = c.get('cmems')
    if cmems:
        def fmt_comp(pfx, hs, t, dir_c, dir_g, f, wp):
            if not hs: return ''
            f_str = f'f={f:.2f}' if f is not None else 'f=?'
            wp_str = f'WP_ef={wp:.1f}' if wp is not None else 'WP_ef=?'
            t_str = f'T={t:.1f}s' if t else ''
            if wp is None: return f'  {pfx}: {dir_c} ({dir_g}°)  Hs={hs}m  f={f:.2f}  → descartado'
            return f'  {pfx}: {dir_c} ({dir_g}°)  Hs={hs}m  {t_str}  {f_str}  → {wp_str} kW/m'
        cls_ef = ('Fracas' if not cmems['wp_ef_total'] or cmems['wp_ef_total'] < 4 else
                  'Aceitaveis' if cmems['wp_ef_total'] < 7 else 'Boas' if cmems['wp_ef_total'] < 10 else
                  'Ideais' if cmems['wp_ef_total'] < 18 else 'Exigentes' if cmems['wp_ef_total'] < 35 else 'Muito exig.')
        sw_lines = [fmt_comp('SW1',cmems['sw1_hs'],cmems['sw1_t'],cmems['sw1_dir_c'],cmems['sw1_dir'],cmems['sw1_factor'],cmems['sw1_wp_ef']),
                    fmt_comp('SW2',cmems['sw2_hs'],cmems['sw2_t'],cmems['sw2_dir_c'],cmems['sw2_dir'],cmems['sw2_factor'],cmems['sw2_wp_ef']),
                    fmt_comp('WW ',cmems['ww_hs'], cmems['ww_t'], cmems['ww_dir_c'], cmems['ww_dir'], cmems['ww_factor'], cmems['ww_wp_ef'])]
        sw_block = chr(10).join(l for l in sw_lines if l)
        wave_hdr = f"Wave Power ef: {cmems['wp_ef_total']} kW/m  [{cls_ef}]  (CMEMS MFWAM · ref {cmems['ref_lat']:.3f}N {cmems['ref_lon']:.3f}W)"
        wave_det = f"Hs offshore={cmems['hs']}m{chr(10)}{sw_block}"
    else:
        swell_t_str = f"  T={c['swell_t']}s" if c.get('swell_t') else ''
        swell2 = c.get('swell2')
        s2_line = ''
        if swell2 and swell2.get('swell2_hs'):
            t2 = f"  T={swell2['swell2_t']}s" if swell2.get('swell2_t') else ''
            s2_line = chr(10) + f"  Swell 2: {swell2['swell2_dir']} ({swell2['swell2_dir_graus']}°)  Hs={swell2['swell2_hs']}m{t2}  [Stormglass]"
        wave_hdr = f"Wave Power : {c['wave_power']} kW/m  [{cls}]"
        wave_det = f"Hs={c['hs']}m  T={c['period']}s{chr(10)}  Swell 1: {c['swell_dir']} ({c['swell_dir_graus']}°)  Hs={c['swell_hs']}m{swell_t_str}{s2_line}"
    print(f"""
Condicoes: {c['spot']}
{c['data']}  {c['hora_ini']}-{c['hora_fim']}
--------------------------------------------
{wave_hdr}
{wave_det}
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
