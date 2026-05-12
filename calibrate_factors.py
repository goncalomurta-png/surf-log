#!/usr/bin/env python3
"""
calibrate_factors.py — compara predições do modelo vs sessões reais.

Lê data/backtest_cache.json e produz:
  1. Tabela sessão a sessão: WP_ef modelo vs WP_ef armazenado
  2. Relatório de calibração por direcção de swell
  3. Sugestão de novos factores para fetch_conditions.py

Fontes usadas (por ordem de prioridade para cada componente):
  SW1 (primário) : CMEMS SW1  →  Open-Meteo primary swell
  SW2 (secundário): CMEMS SW2  →  Stormglass SG
  WW              : CMEMS WW   →  (sem fallback)

Uso:
  python3 calibrate_factors.py            # relatório completo
  python3 calibrate_factors.py --verbose  # detalhes por componente
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_conditions import factor_swell, graus_para_cardinal

CACHE_FILE = Path('data/backtest_cache.json')

CLASSE_RANGES = [
    ('Fracas',       0,   4),
    ('Aceitáveis',   4,   7),
    ('Boas',         7,  10),
    ('Ideais',      10,  18),
    ('Exigentes',   18,  35),
    ('Muito exig.', 35, 999),
]

FACTORES_ACTUAIS_SUL = {
    'S (T≥12s)':      0.90,
    'S (T<12s)':      0.85,
    'W/SW/WNW':       1.00,  # calibrado: f_real 1.42–1.87 para WSW/W (225–290°)
    'NW (270–320°)':  0.65,  # calibrado: f_real 0.58 para NW (290–320°)
    'NNW (320–345°)': 0.55,  # calibrado: f_real 1.00 para NNW wrapping parcial
    'N/NE':           0.35,  # calibrado: f_real mediana 0.33 para N puro bloqueado
    'SE':             0.35,
}

CARDINAL_GRAUS = {
    'N': 0, 'NNE': 22.5, 'NE': 45, 'ENE': 67.5,
    'E': 90, 'ESE': 112.5, 'SE': 135, 'SSE': 157.5,
    'S': 180, 'SSW': 202.5, 'SW': 225, 'WSW': 247.5,
    'W': 270, 'WNW': 292.5, 'NW': 315, 'NNW': 337.5,
}


def cardinal_para_graus(cardinal):
    if not cardinal:
        return None
    return CARDINAL_GRAUS.get(cardinal.upper())


def wp_para_classe(wp):
    if wp is None:
        return '?'
    for nome, lo, hi in CLASSE_RANGES:
        if lo <= wp < hi:
            return nome
    return 'Muito exig.'


def dir_bucket(dir_graus, period=None):
    if dir_graus is None:
        return 'desconhecida'
    if dir_graus >= 345 or dir_graus <= 45:
        return 'N/NE'
    if 320 <= dir_graus < 345:
        return 'NNW (320–345°)'
    if 290 <= dir_graus < 320:
        return 'NW (270–320°)'
    if 225 < dir_graus < 290:
        return 'W/SW/WNW'
    if 135 <= dir_graus <= 225:
        return 'S (T≥12s)' if (period and period >= 12) else 'S (T<12s)'
    if 90 <= dir_graus < 135:
        return 'SE'
    if 45 < dir_graus < 90:
        return 'NE/E'
    return 'outra'


def compute_wp_ef(spot_id, entry, verbose=False):
    """
    Calcula WP_ef total combinando todas as fontes disponíveis.
    Retorna (wp_ef_total, lista_de_componentes, fonte_principal).
    """
    # ── Override (Stormglass recuperado de sessão anterior) ──────────────────
    override = entry.get('wp_ef_override')
    if override and override.get('wp_total') is not None:
        components = []
        if override.get('sw1_wp') is not None:
            components.append({
                'fonte': 'SG-SW1', 'hs': override.get('sw1_hs'), 't': None,
                'dir': cardinal_para_graus(override.get('sw1_dir')),
                'dir_c': override.get('sw1_dir', '?'),
                'factor': None, 'wp_ef': override['sw1_wp'],
            })
        if override.get('sw2_wp') is not None:
            components.append({
                'fonte': 'SG-SW2', 'hs': override.get('sw2_hs'), 't': None,
                'dir': cardinal_para_graus(override.get('sw2_dir')),
                'dir_c': override.get('sw2_dir', '?'),
                'factor': None, 'wp_ef': override['sw2_wp'],
            })
        if verbose:
            for c in components:
                hs_s = f'Hs={c["hs"]}m' if c['hs'] else ''
                print(f'      {c["fonte"]:12s} {c["dir_c"]:6s} {hs_s}  → {c["wp_ef"]} kW/m')
        return override['wp_total'], components, 'SG-override'

    cmems = entry.get('cmems')
    sg    = entry.get('sg')
    om    = entry.get('om', {})
    components = []

    # ── SW1: CMEMS SW1 → OM primary swell ───────────────────────────────────
    if cmems and cmems.get('sw1_hs') and cmems.get('sw1_wp_ef') is not None:
        components.append({
            'fonte': 'CMEMS-SW1',
            'hs': cmems['sw1_hs'], 't': cmems['sw1_t'],
            'dir': cmems['sw1_dir'], 'dir_c': cmems['sw1_dir_c'],
            'factor': cmems['sw1_factor'], 'wp_ef': cmems['sw1_wp_ef'],
        })
    elif om.get('sw_hs') and om.get('sw_t') and om.get('factor') is not None:
        components.append({
            'fonte': 'OM-SW1',
            'hs': om['sw_hs'], 't': om['sw_t'],
            'dir': om.get('sw_dir'), 'dir_c': om.get('sw_dir_c', '?'),
            'factor': om['factor'], 'wp_ef': om.get('wp_ef'),
        })

    # ── SW2: CMEMS SW2 → Stormglass SG ─────────────────────────────────────
    if cmems and cmems.get('sw2_hs') and cmems.get('sw2_wp_ef') is not None:
        components.append({
            'fonte': 'CMEMS-SW2',
            'hs': cmems['sw2_hs'], 't': cmems['sw2_t'],
            'dir': cmems['sw2_dir'], 'dir_c': cmems['sw2_dir_c'],
            'factor': cmems['sw2_factor'], 'wp_ef': cmems['sw2_wp_ef'],
        })
    elif sg and sg.get('swell2_hs'):
        sg_dir = sg.get('swell2_dir_graus')
        sg_t   = sg.get('swell2_t')
        sg_hs  = sg.get('swell2_hs')
        sg_f   = factor_swell(spot_id, sg_dir, sg_t)
        sg_wp  = round(0.5 * sg_hs**2 * sg_t * sg_f, 2) if (sg_f and sg_f >= 0.50 and sg_t) else None
        components.append({
            'fonte': 'SG-SW2',
            'hs': sg_hs, 't': sg_t,
            'dir': sg_dir, 'dir_c': sg.get('swell2_dir', '?'),
            'factor': sg_f, 'wp_ef': sg_wp,
        })

    # ── WW: CMEMS WW (só se factor ≥ 0.50) ──────────────────────────────────
    if cmems and cmems.get('ww_wp_ef') is not None:
        components.append({
            'fonte': 'CMEMS-WW',
            'hs': cmems['ww_hs'], 't': cmems['ww_t'],
            'dir': cmems['ww_dir'], 'dir_c': cmems['ww_dir_c'],
            'factor': cmems['ww_factor'], 'wp_ef': cmems['ww_wp_ef'],
        })

    wp_total = round(sum(c['wp_ef'] for c in components if c.get('wp_ef')), 2) if components else None
    fontes   = '+'.join(c['fonte'] for c in components) or 'nenhuma'

    if verbose:
        for c in components:
            print(f'      {c["fonte"]:12s} {c["dir_c"]:6s} Hs={c["hs"]}m T={c["t"]}s '
                  f'f={c["factor"]}  → {c["wp_ef"]} kW/m')

    return wp_total, components, fontes


def dominant_dir(components):
    """Direcção do componente com maior wp_ef."""
    if not components:
        return None, None
    best = max(components, key=lambda c: c.get('wp_ef') or 0)
    return best.get('dir'), best.get('t')


def offshore_sw1(entry):
    """Devolve (hs_offshore, t, dir_graus, dir_c) do SW1 dominante (CMEMS → OM)."""
    cmems = entry.get('cmems')
    om    = entry.get('om', {})
    if cmems and cmems.get('sw1_hs') and cmems.get('sw1_t'):
        return cmems['sw1_hs'], cmems['sw1_t'], cmems.get('sw1_dir'), cmems.get('sw1_dir_c', '?')
    if om.get('sw_hs') and om.get('sw_t'):
        return om['sw_hs'], om['sw_t'], om.get('sw_dir'), om.get('sw_dir_c', '?')
    return None, None, None, None


def load_cache():
    if not CACHE_FILE.exists():
        print(f'Cache não encontrado: {CACHE_FILE}')
        print('Executa primeiro: python3 fetch_historical.py')
        sys.exit(1)
    return json.loads(CACHE_FILE.read_text(encoding='utf-8'))


def main():
    verbose = '--verbose' in sys.argv
    cache   = load_cache()

    print(f'Cache: {len(cache)} sessões\n')

    # Contagem de fontes disponíveis
    n_cmems = sum(1 for e in cache.values() if e.get('cmems'))
    n_sg    = sum(1 for e in cache.values() if e.get('sg') and e['sg'])
    print(f'Fontes: CMEMS={n_cmems}  Stormglass={n_sg}  OM=todos')
    print()

    print('─' * 96)
    print(f'{"ID":18s} {"Data":10s} {"Dir dom.":8s} {"T":5s} {"WP_model":9s} '
          f'{"WP_stored":9s} {"Ratio":7s} {"Cl.M":11s} {"Cl.R":11s} {"Fontes"}')
    print('─' * 96)

    calibration = {}
    rows        = []

    for key in sorted(cache):
        entry     = cache[key]
        s         = entry.get('session', {})
        spot_id   = s.get('spot_id', 'milicias')
        wp_stored = s.get('wp_stored')
        classe_r  = s.get('classe', '?')

        wp_model, components, fontes = compute_wp_ef(spot_id, entry, verbose=(verbose and bool(entry.get('cmems') or entry.get('sg'))))

        dir_graus, sw_t = dominant_dir(components)
        dir_c     = graus_para_cardinal(dir_graus) if dir_graus else '?'
        bucket    = dir_bucket(dir_graus, sw_t)
        classe_m  = wp_para_classe(wp_model)

        ratio     = None
        ratio_str = '—'
        if wp_model and wp_stored and wp_model > 0:
            ratio     = round(wp_stored / wp_model, 2)
            ratio_str = f'{ratio:.2f}×'
            calibration.setdefault(bucket, []).append(ratio)

        t_str    = f'{sw_t:.1f}s' if sw_t else '?'
        wp_m_str = f'{wp_model:.1f}' if wp_model else '?'
        wp_s_str = f'{wp_stored:.1f}' if wp_stored else '?'

        print(f'{key:18s} {s.get("data","?"):10s} {dir_c:8s} {t_str:5s} '
              f'{wp_m_str:9s} {wp_s_str:9s} {ratio_str:7s} {classe_m:11s} {classe_r:11s} {fontes}')
        rows.append((classe_m, classe_r))

    # ── Calibração por bucket ────────────────────────────────────────────────
    print()
    print('═' * 96)
    print('CALIBRAÇÃO POR DIRECÇÃO (factor actual × ratio = factor sugerido)')
    print()
    print(f'  {"Bucket":20s} {"n":3s}  {"Ratio médio":12s} {"Med.":7s}  {"f_actual":9s}  {"f_sugerido"}')
    print(f'  {"─"*20} {"─"*3}  {"─"*12} {"─"*7}  {"─"*9}  {"─"*10}')

    for bucket in sorted(calibration):
        ratios  = calibration[bucket]
        n       = len(ratios)
        mean_r  = sum(ratios) / n
        med_r   = sorted(ratios)[n // 2]
        f_act   = FACTORES_ACTUAIS_SUL.get(bucket, '?')
        f_act_s = f'{f_act:.2f}' if isinstance(f_act, float) else str(f_act)
        f_sug   = round(f_act * mean_r, 2) if isinstance(f_act, float) else '?'
        print(f'  {bucket:20s} {n:3d}  {mean_r:.2f}×{"":8s} {med_r:.2f}×  {f_act_s:9s}  {f_sug}')

    # ── Acurácia ─────────────────────────────────────────────────────────────
    print()
    valid   = [(m, r) for m, r in rows if m != '?' and r != '?']
    correct = sum(1 for m, r in valid if m == r)
    print(f'Acurácia de classe: {correct}/{len(valid)} ({100*correct/len(valid):.0f}%)'
          if valid else 'Sem dados suficientes')

    # ── Calibração real baseada em hs_obs ────────────────────────────────────
    print()
    print('═' * 60)
    print('CALIBRAÇÃO REAL — forecast vs observação (hs_obs)')
    print()

    obs_calibration = {}
    n_com_obs = 0
    n_sem_obs = 0

    for key in sorted(cache):
        entry   = cache[key]
        s       = entry.get('session', {})
        hs_obs  = s.get('hs_obs')
        spot_id = s.get('spot_id', 'milicias')

        if hs_obs is None:
            n_sem_obs += 1
            continue

        n_com_obs += 1
        hs_off, t_dom, dir_graus, dir_c = offshore_sw1(entry)

        if not hs_off or not t_dom or hs_off <= 0:
            print(f'  {key:18s}  hs_obs={hs_obs}m  sem Hs offshore — ignorado')
            continue

        # f_real: factor que reconcilia offshore com observação
        # wp = 0.5 × Hs_off² × T × f  →  f = (hs_obs/hs_off)²
        f_real  = round((hs_obs / hs_off) ** 2, 3)
        bucket  = dir_bucket(dir_graus, t_dom)
        f_atual = FACTORES_ACTUAIS_SUL.get(bucket)
        delta_s = f'{f_real - f_atual:+.3f}' if f_atual else '?'

        obs_calibration.setdefault(bucket, []).append(f_real)
        print(f'  {key:18s}  hs_obs={hs_obs}m  hs_off={hs_off}m  T={t_dom:.1f}s  '
              f'dir={dir_c:4s}  f_real={f_real:.3f}  f_atual={f_atual}  δ={delta_s}')

    print()
    if n_com_obs == 0:
        print(f'  Nenhuma sessão tem hs_obs. Preencher no Passo 1b do workflow (pergunta de condições).')
        print(f'  {n_sem_obs} sessões sem hs_obs.')
    else:
        print(f'  {n_com_obs} sessão(ões) com hs_obs · {n_sem_obs} sem hs_obs')
        if obs_calibration:
            print()
            print(f'  {"Bucket":20s} {"n":3s}  {"f_real médio":13s} {"f_real med.":11s} {"f_atual":8s}  {"δ":8s}  {"Acção"}')
            print(f'  {"─"*20} {"─"*3}  {"─"*13} {"─"*11} {"─"*8}  {"─"*8}  {"─"*20}')
            for bucket in sorted(obs_calibration):
                fs      = obs_calibration[bucket]
                n       = len(fs)
                mean_f  = round(sum(fs) / n, 3)
                med_f   = sorted(fs)[n // 2]
                f_at    = FACTORES_ACTUAIS_SUL.get(bucket)
                f_at_s  = f'{f_at:.2f}' if f_at else '?'
                delta   = round(mean_f - f_at, 3) if f_at else None
                delta_s = f'{delta:+.3f}' if delta is not None else '?'
                acao    = ('↑ aumentar' if delta and delta > 0.05
                           else '↓ reduzir' if delta and delta < -0.05
                           else '✓ ok') if delta is not None else '?'
                print(f'  {bucket:20s} {n:3d}  {mean_f:.3f}{"":10s} {med_f:.3f}{"":8s} {f_at_s:8s}  {delta_s:8s}  {acao}')

    # ── Status de cobertura ───────────────────────────────────────────────────
    print()
    print('─' * 60)
    print('COBERTURA DE SW2:')
    for key in sorted(cache):
        entry   = cache[key]
        s       = entry.get('session', {})
        cmems   = entry.get('cmems')
        sg      = entry.get('sg')
        has_sw2 = (cmems and cmems.get('sw2_hs')) or (sg and sg.get('swell2_hs'))
        src     = 'CMEMS' if (cmems and cmems.get('sw2_hs')) else ('SG' if (sg and sg.get('swell2_hs')) else '—')
        flag    = '✅' if has_sw2 else '❌'
        print(f'  {flag} {key:18s} {s.get("data","?"):10s}  SW2={src}')

    print()
    print('Sessões sem SW2: correr amanhã "python3 fetch_historical.py" (Stormglass renova 10 calls/dia).')


if __name__ == '__main__':
    main()
