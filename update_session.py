#!/usr/bin/env python3
"""
update_session.py — Surf Log · actualização automática após nova sessão

Uso:
  python3 update_session.py rodrigo
  python3 update_session.py tomas
  python3 update_session.py ambos          (default)

Pré-condições (Claude assegura antes de chamar este script):
  • data/<surfer>.json actualizado com nova sessão no TOPO de "sessoes"
  • Nova sessão tem campos completos: tags, notes, tide_strip, swell_duo,
    cond_grid, sea_src, corrente_paddle (opt.), skills {val+note por skill}
  • Todas as sessões em "sessoes" têm "skills_hist" [l,t,p,m,e,pos]
    OU "skills" (o script deriva skills_hist a partir de skills.*.val)
  • html.insert_before_id aponta para a sessão actualmente mais recente
    (o script insere a nova sessão ANTES dessa)

Após correr o script, Claude deve:
  • Verificar visualmente no browser
  • Actualizar html.insert_before_id no JSON para o novo html_id
  • git add surf_log.html && git commit && git push
"""

import sys, json, re, shutil, pathlib
from datetime import datetime

BASE      = pathlib.Path(__file__).parent
HTML_PATH = BASE / "surf_log.html"

# ── Constantes ────────────────────────────────────────────────────────────────

SKILL_ORDER  = ['leitura', 'takeoff', 'paddle', 'manobras', 'equilibrio', 'posicionamento']
SKILL_NAMES  = ['🌊 Leitura de onda', '🏄 Take-off', '🚣 Paddle',
                '↩️ Manobras', '⚖️ Equilíbrio', '🧭 Posicionamento']
SKILL_TREND  = ['🌊 Leitura', '🏄 Take-off', '🚣 Paddle',
                '↩️ Manobras', '⚖️ Equilíb.', '🧭 Posic.']
SKILL_COLORS = ['#2e86c1', '#e67e22', '#1e8449', '#c0392b', '#8e44ad', '#d4a017']
SKILL_DASHED = [False, False, True, False, False, False]  # paddle tem dash

# Escala scatter: piecewise linear (wave power kW/m → pixel x)
SCATTER_X = [(0,45), (2,56), (4,66), (18,140), (35,231), (50,310)]

# Mapeamento skill_order → chave no JSON progressao
PROG_KEYS = ['leitura_onda', 'takeoff', 'paddle', 'manobras', 'equilibrio', 'posicionamento']

MESES_ABR  = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
              7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
MESES_FULL = {1:'Janeiro',2:'Fevereiro',3:'Março',4:'Abril',5:'Maio',6:'Junho',
              7:'Julho',8:'Agosto',9:'Setembro',10:'Outubro',11:'Novembro',12:'Dezembro'}

# ── Funções matemáticas ───────────────────────────────────────────────────────

def nivel_to_y(n):
    """Nível 1–5 → coordenada Y no line chart (1→160, 5→20)."""
    return 160 - (int(n) - 1) * 35

def sessao_to_x(i, n_total):
    """Sessão i (0=mais antiga) de n_total → coordenada X no line chart."""
    if n_total <= 1:
        return 50
    return round(50 + i * 325 / (n_total - 1))

def wp_to_cx(wp):
    """Wave power kW/m → coordenada X no scatter chart."""
    wp = float(wp)
    for i in range(len(SCATTER_X) - 1):
        w0, x0 = SCATTER_X[i]
        w1, x1 = SCATTER_X[i + 1]
        if w0 <= wp <= w1:
            return round(x0 + (wp - w0) / (w1 - w0) * (x1 - x0))
    return SCATTER_X[-1][1]

def perf_to_cy(perf_media):
    """Performance média 1–5 → coordenada Y no scatter chart (5→15, 1→155)."""
    return round(155 - (perf_media - 1) * 35)

def get_skills_hist(sessao):
    """Extrai [l, t, p, m, e, pos] da sessão para o SVG.
    Prefere skills_hist (série contínua); cai para skills.val apenas se skills_hist ausente.
    Política de null: val=None fica em skills.val; skills_hist tem valores plausíveis para o chart."""
    if 'skills_hist' in sessao:
        return sessao['skills_hist']
    if 'skills' in sessao:
        return [sessao['skills'][s]['val'] for s in SKILL_ORDER]
    return []

def perf_media(sessao):
    h = get_skills_hist(sessao)
    vals = [v for v in h if v is not None]
    return sum(vals) / len(vals) if vals else 0

# ── Helpers de formatação ─────────────────────────────────────────────────────

def fmt_abrev(iso):
    """'2026-04-18' → '18 Abr 26'"""
    d = datetime.fromisoformat(iso)
    return f"{d.day:02d} {MESES_ABR[d.month]} {str(d.year)[2:]}"

def fmt_full(iso):
    """'2026-04-18' → '18 Abril 2026'"""
    d = datetime.fromisoformat(iso)
    return f"{d.day} {MESES_FULL[d.month]} {d.year}"

def fmt_dd_m(iso):
    """'2026-04-18' → '18/4'"""
    d = datetime.fromisoformat(iso)
    return f"{d.day}/{d.month}"

def energy_cls(wp):
    wp = float(wp)
    if wp < 4:   return 'energy-fraca'
    if wp <= 10: return 'energy-media'
    return 'energy-boa'

def ni_cls(tipo):
    if tipo == '+':          return 'plus'
    if tipo in ('−', '-'):   return 'minus'
    return 'neutral'

# ── Geradores de HTML ─────────────────────────────────────────────────────────

def stars_interativas(n, sid, idx):
    parts = []
    for i in range(1, 6):
        cls = 'star filled' if i <= n else 'star '
        parts.append(f'<span class="{cls}" onclick="setStar(this,{i},\'{sid}\',{idx})">★</span>')
    return ''.join(parts)

def stars_locked(n):
    parts = []
    for i in range(1, 6):
        cls = 'star filled locked' if i <= n else 'star  locked'
        parts.append(f'<span class="{cls}">★</span>')
    return ''.join(parts)

def gerar_card(sd, s):
    """Gera o HTML completo do card de sessão."""
    sid      = s['html_id']
    d        = datetime.fromisoformat(s['data'])
    prancha  = s.get('prancha', sd['quiver'][0]['nome'])
    spot_sub = s.get('spot_sub', s['spot'])
    zona     = s.get('nivel', {}).get('zona', 'outside')

    tags = ''.join(
        f'<span class="tag {t["cls"]}">{t["txt"]}</span>'
        for t in s.get('tags', []))

    notes = ''.join(
        f'<div class="note-item"><span class="ni {ni_cls(n["tipo"])}">{n["tipo"]}</span>'
        f'<span>{n["txt"]}</span></div>'
        for n in s.get('notes', []))

    tide = ''.join(
        f'<div class="t-item"><div class="t-lbl">{t["lbl"]}</div>'
        f'<div class="t-val">{t["val"]}</div></div>'
        for t in s.get('tide_strip', []))

    swell = ''.join(
        f'<div class="sw-card {sw.get("cls","")}"><div class="sw-lbl">{sw["lbl"]}</div>'
        f'<div class="sw-val">{sw["val"]}</div><div class="sw-dir">{sw["dir"]}</div></div>'
        for sw in s.get('swell_duo', []))

    cond = ''.join(
        f'<div class="c-item"><div class="c-lbl">{c["lbl"]}</div>'
        f'<div class="c-val">{c["val"]}</div></div>'
        for c in s.get('cond_grid', []))

    skill_items = []
    for idx, sk_key in enumerate(SKILL_ORDER):
        sk = s['skills'][sk_key]
        cp = ''
        if sk_key == 'paddle' and s.get('corrente_paddle'):
            cp = f'<div class="corrente-paddle">{s["corrente_paddle"]}</div>'
        if sk['val'] is None:
            skill_items.append(
                f'            <div class="skill-item">\n'
                f'              <div class="skill-name">{SKILL_NAMES[idx]}</div>\n'
                f'              <div class="skill-null">🚫 <span>Não observável</span></div>\n'
                f'              <div class="skill-note">{sk["note"]}</div>{cp}\n'
                f'            </div>')
        else:
            stars = stars_interativas(sk['val'], sid, idx)
            skill_items.append(
                f'            <div class="skill-item">\n'
                f'              <div class="skill-name">{SKILL_NAMES[idx]}</div>\n'
                f'              <div class="stars" data-sid="{sid}" data-skill="{sk_key}">{stars}</div>\n'
                f'              <div class="skill-note">{sk["note"]}</div>{cp}\n'
                f'            </div>')

    ss_weight = (
        f'🌊 {s["classe"]} · ~{s["wp_ef"]} kW/m ef.'
        f' &nbsp;·&nbsp; ×{s["rec"]:.2f} &nbsp;·&nbsp; Peso <strong>{s["peso"]:.2f}</strong>')

    return (
        f'    <div class="session-card {energy_cls(s["wp_ef"])}" id="{sid}" data-zona="{zona}" onclick="toggleSession(this)">\n'
        f'      <div class="session-summary">\n'
        f'        <div class="s-date"><div class="s-day">{d.day:02d}</div>'
        f'<div class="s-month">{MESES_ABR[d.month]} {str(d.year)[2:]}</div></div>\n'
        f'        <div class="s-main">\n'
        f'          <div class="s-spot">📍 {spot_sub}</div>\n'
        f'          <div class="s-board-line">🏄 {prancha}</div>\n'
        f'          <div class="s-time-line">⏱ {s.get("hora_inicio","")} – {s.get("hora_fim","")} · {s.get("duracao","")}</div>\n'
        f'          <div class="tag-row">{tags}</div>\n'
        f'        </div>\n'
        f'        <div class="s-toggle">⌄</div>\n'
        f'      </div>\n'
        f'      <div class="session-detail">\n'
        f'        <div class="session-notes">\n'
        f'          {notes}\n'
        f'        </div>\n'
        f'        <div class="tide-strip">\n'
        f'          {tide}\n'
        f'        </div>\n'
        f'        <div class="sea-block">\n'
        f'          <div class="swell-duo">\n'
        f'            {swell}\n'
        f'          </div>\n'
        f'          <div class="cond-grid">\n'
        f'            {cond}\n'
        f'          </div>\n'
        f'          <div class="sea-src">{s.get("sea_src", "")}</div>\n'
        f'        </div>\n'
        f'        <div class="session-skills">\n'
        f'          <div class="ss-header">\n'
        f'            <span class="ss-title">Avaliação desta sessão</span>\n'
        f'            <span class="ss-weight">{ss_weight}</span>\n'
        f'          </div>\n'
        f'          <div class="skill-grid">\n'
        + '\n'.join(skill_items) + '\n'
        f'          </div>\n'
        f'        </div>\n'
        f'      </div>\n'
        f'    </div>\n'
    )

def gerar_prog_card(prog, n_sessoes, data_iso):
    """Gera o bloco prog-card 'Nível geral ponderado' completo."""
    skill_items = []
    for i, sk_key in enumerate(PROG_KEYS):
        sk = prog[sk_key]
        skill_items.append(
            f'      <div class="skill-item">\n'
            f'        <div class="skill-name">{SKILL_NAMES[i]}</div>\n'
            f'        <div class="stars">{stars_locked(sk["estrelas"])}</div>\n'
            f'        <div class="skill-note">Média ponderada: {sk["media"]:.2f} / 5</div>\n'
            f'      </div>')
    return (
        f'  <div class="prog-card">\n'
        f'    <div class="prog-header">\n'
        f'      <span class="prog-header-title">Nível geral ponderado</span>\n'
        f'      <span class="prog-date">{fmt_abrev(data_iso)}</span>\n'
        f'    </div>\n'
        f'    <div class="prog-body">\n'
        f'      <div class="prog-comment empty">— Comentário geral do treinador a preencher —</div>\n'
        f'      <div class="prog-formula">Peso = Recência × Condições &nbsp;|&nbsp; {n_sessoes} sessões'
        f' &nbsp;|&nbsp; Peso total: {prog["peso_total"]:.2f}<br>'
        f'<small>Escala: Fracas 0,35 · Aceitáveis 0,65 · Boas 0,85 · Ideais 1,0 · Exigentes 0,70 · Muito exig. 0,55</small></div>\n'
        f'      <div class="skill-grid">' + ''.join(skill_items) + '\n'
        f'      </div>\n'
        f'    </div>\n'
        f'  </div>'
    )

def gerar_svg_line(sessoes_crono):
    """Gera o SVG do line chart a partir das sessões em ordem cronológica."""
    n    = len(sessoes_crono)
    xs   = [sessao_to_x(i, n) for i in range(n)]
    xmax = xs[-1]
    vb_w = xmax + 50

    L = []
    L.append(f'<svg viewBox="0 0 {vb_w} 190" xmlns="http://www.w3.org/2000/svg" font-family="Barlow,sans-serif">')
    L.append(f'  <!-- SVG line chart')
    L.append(f'       Área útil: x 50–{xmax}, y 20–160  (largura {xmax-50}, altura 140)')
    L.append(f'       Escala Y: 1→160, 2→125, 3→90, 4→55, 5→20  (passo 35px por nível)')
    L.append(f'       Escala X: {n} sessões → x={",".join(str(x) for x in xs)}')
    L.append(f'  -->')
    L.append(f'  <rect x="50" y="20" width="{xmax-50}" height="140" fill="#fafaf8" rx="4"/>')
    L.append('  <!-- Grelha horizontal Y (níveis 1–5) -->')
    L.append('  <g stroke="#e8e4dc" stroke-width="0.7">')
    for y, lbl in [(160,'1'),(125,'2'),(90,'3'),(55,'4'),(20,'5')]:
        L.append(f'    <line x1="50" y1="{y}" x2="{xmax}" y2="{y}"/> <!-- y={lbl} -->')
    L.append('  </g>')
    L.append('  <!-- Labels Y -->')
    L.append('  <g font-size="9" fill="#b0bec5" text-anchor="end">')
    for y_lbl, y in [(1,163),(2,128),(3,93),(4,58),(5,23)]:
        L.append(f'    <text x="44" y="{y}">{y_lbl}</text>')
    L.append('  </g>')
    L.append(f'  <!-- Linhas verticais por sessão — {n} sessões x={",".join(str(x) for x in xs)} -->')
    L.append('  <g stroke="#e8e4dc" stroke-width="0.7" stroke-dasharray="2,3">')
    for x in xs:
        L.append(f'    <line x1="{x}" y1="20" x2="{x}" y2="160"/>')
    L.append('  </g>')
    L.append('  <!-- Labels X — datas das sessões -->')
    L.append('  <g font-size="8" fill="#7f8c8d" text-anchor="middle">')
    for x, s in zip(xs, sessoes_crono):
        d = datetime.fromisoformat(s['data'])
        L.append(f'    <text x="{x}" y="178">{d.day:02d} {MESES_ABR[d.month]}</text>')
    L.append('  </g>')

    for sk_idx, (sk_key, color, dashed) in enumerate(zip(SKILL_ORDER, SKILL_COLORS, SKILL_DASHED)):
        hist = [get_skills_hist(s)[sk_idx] for s in sessoes_crono]
        ys   = [nivel_to_y(h) for h in hist]
        pts  = ' '.join(f'{x},{y}' for x, y in zip(xs, ys))
        vals = ','.join(str(h) for h in hist)
        ystr = ','.join(str(y) for y in ys)
        dash = ' stroke-dasharray="5,2"' if dashed else ''
        L.append(f'\n  <!-- {sk_key.capitalize()}: {vals} → y: {ystr} -->')
        L.append(f'  <polyline points="{pts}"')
        L.append(f'    fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"{dash}/>')
        for i, (x, y) in enumerate(zip(xs, ys)):
            is_last = (i == n - 1)
            r     = '3.5' if is_last else '3'
            extra = ' stroke="white" stroke-width="1.5"' if is_last else ''
            L.append(f'  <circle cx="{x}"  cy="{y}"  r="{r}" fill="{color}"{extra}/>')

    L.append('\n  <text x="12" y="95" font-size="8" fill="#b0bec5" transform="rotate(-90,12,95)" text-anchor="middle">Nível (1–5)</text>')
    L.append('</svg>')
    return '\n          '.join(L)

def gerar_evo_trend(sessoes_crono, prog):
    """Gera o bloco evo-trend com histórico de cada skill."""
    items = []
    for idx, (sk_key, prog_key, color, sk_short) in enumerate(
            zip(SKILL_ORDER, PROG_KEYS, SKILL_COLORS, SKILL_TREND)):
        hist    = [get_skills_hist(s)[idx] for s in sessoes_crono]
        current = hist[-1]
        prev    = hist[-2] if len(hist) >= 2 else current
        if   current > prev: dcls, dsym = 'up',   '↑'
        elif current < prev: dcls, dsym = 'down',  '↓'
        else:                dcls, dsym = 'same',  '→'
        hist_str = '→'.join(str(v) for v in hist)
        items.append(
            f'          <div class="evo-trend-item">\n'
            f'            <div class="evo-trend-skill" style="color:{color}">{sk_short}</div>\n'
            f'            <div class="evo-trend-val">{prog[prog_key]["estrelas"]}/5</div>\n'
            f'            <div class="evo-trend-delta {dcls}">{dsym} {hist_str}</div>\n'
            f'          </div>')
    return '\n'.join(items)

# ── Função principal de actualização por surfista ─────────────────────────────

def update_surfer(html, surfer_id, sd):
    """Modifica o HTML para um surfista. Devolve o HTML actualizado."""

    # Delimitar a região deste surfista
    p_start = html.find(f'id="page-{surfer_id}"')
    p_end   = html.find('id="page-tomas"') if surfer_id == 'rodrigo' else html.find('id="page-quiver"')
    page    = html[p_start:p_end]

    sessoes       = sd['sessoes']             # mais recente primeiro
    sessoes_crono = list(reversed(sessoes))   # mais antiga primeiro (para SVG)
    nova          = sessoes[0]                # sessão a inserir
    n             = len(sessoes)
    prog          = sd['progressao']

    print(f"\n  ── {sd['surfer']} ({n} sessões, nova: {nova['html_id']}) ──")

    # ── 1. Inserir card de sessão ────────────────────────────────────────────
    insert_id = sd['html']['insert_before_id']
    idx = page.find(f'id="{insert_id}"')
    if idx == -1:
        print(f"  ⚠ insert_before_id '{insert_id}' não encontrado — card NÃO inserido")
    else:
        div_start = page.rfind('<', 0, idx)
        page = page[:div_start] + gerar_card(sd, nova) + page[div_start:]
        print(f"  ✓ Card {nova['html_id']} inserido antes de {insert_id}")

    # ── 2. KPIs ─────────────────────────────────────────────────────────────
    kpis = sd['kpis']
    page = re.sub(r'(<div class="kpi"><div class="kpi-num">)\d+(</div><div class="kpi-lbl">Sessões</div></div>)',
                  rf'\g<1>{kpis["sessoes"]}\g<2>', page, count=1)
    page = re.sub(r'(<div class="kpi"><div class="kpi-num">)[^<]+(</div><div class="kpi-lbl">No Água</div></div>)',
                  rf'\g<1>{kpis["no_agua"]}\g<2>', page, count=1)
    page = re.sub(r'(<div class="kpi"><div class="kpi-num">)\d+(</div><div class="kpi-lbl">Spots</div></div>)',
                  rf'\g<1>{kpis["spots"]}\g<2>', page, count=1)
    page = re.sub(r'(<div class="kpi"><div class="kpi-num">)\d+(</div><div class="kpi-lbl">Pranchas</div></div>)',
                  rf'\g<1>{kpis["pranchas"]}\g<2>', page, count=1)
    print(f"  ✓ KPIs: {kpis['sessoes']} sessões · {kpis['no_agua']} · {kpis['spots']} spots · {kpis['pranchas']} pranchas")

    # ── 3. Progressão — substituir prog-card "Nível geral ponderado" ─────────
    prog_start_marker = '<div class="sec-label">Progressão</div>'
    prog_end_marker   = '    <div class="sec-label">Objetivos</div>'
    ps = page.find(prog_start_marker)
    pe = page.find(prog_end_marker, ps)
    if ps == -1 or pe == -1:
        print(f"  ⚠ Secção Progressão não encontrada")
    else:
        new_prog = f'{prog_start_marker}\n{gerar_prog_card(prog, n, nova["data"])}\n'
        page = page[:ps] + new_prog + page[pe:]
        print(f"  ✓ Progressão: peso_total={prog['peso_total']:.2f} · {n} sessões")

    # ── 4. SVG line chart — substituir por versão reconstruída ───────────────
    svg_line_pat = re.compile(r'<svg viewBox="0 0 \d+ 190"[^>]*>.*?</svg>', re.DOTALL)
    m = svg_line_pat.search(page)
    if m:
        page = page[:m.start()] + gerar_svg_line(sessoes_crono) + page[m.end():]
        print(f"  ✓ SVG line chart: {n} sessões · x={','.join(str(sessao_to_x(i,n)) for i in range(n))}")
    else:
        print(f"  ⚠ SVG line chart não encontrado")

    # ── 5. Evo-trend — substituir bloco ─────────────────────────────────────
    trend_start_marker = '<div class="evo-trend">'
    trend_end_marker   = '    <div class="sec-label">Condições preferidas</div>'
    ts = page.find(trend_start_marker)
    te = page.find(trend_end_marker, ts)
    if ts == -1 or te == -1:
        print(f"  ⚠ evo-trend não encontrado")
    else:
        new_trend = (f'{trend_start_marker}\n'
                     + gerar_evo_trend(sessoes_crono, prog)
                     + '\n        </div>\n      </div>\n    </div>\n')
        page = page[:ts] + new_trend + page[te:]
        print(f"  ✓ Evo-trend actualizado")

    # ── 6. Evo-sessions-label ────────────────────────────────────────────────
    d_nova = datetime.fromisoformat(nova['data'])
    label  = f'{n} sessões · {MESES_ABR[d_nova.month]} {d_nova.year}'
    page   = re.sub(r'(<span class="evo-sessions-label">)[^<]+(</span>)',
                    rf'\g<1>{label}\g<2>', page, count=1)
    print(f"  ✓ Evo-sessions-label: {label}")

    # ── 7. Scatter — adicionar novo ponto ────────────────────────────────────
    scatter_pat = re.compile(r'(<svg viewBox="0 0 320 185"[^>]*>)(.*?)(</svg>)', re.DOTALL)
    sm = scatter_pat.search(page)
    if sm:
        cx  = wp_to_cx(nova['wp_ef'])
        pm  = perf_media(nova)
        cy  = perf_to_cy(pm)
        lbl = fmt_dd_m(nova['data'])
        new_pt = (
            f'            <circle cx="{cx}" cy="{cy}" r="5" fill="#1e8449" opacity="0.9"/>\n'
            f'            <text x="{cx}" y="{cy-8}" text-anchor="middle" '
            f'font-family="Barlow,sans-serif" font-size="7" fill="#1e8449">{lbl}</text>\n            ')
        page = (page[:sm.start()] + sm.group(1) + sm.group(2)
                + new_pt + sm.group(3) + page[sm.end():])
        print(f"  ✓ Scatter: {lbl} · cx={cx} cy={cy} (perf={pm:.2f})")
    else:
        print(f"  ⚠ Scatter SVG não encontrado")

    # Actualizar "N pontos" e "N sessões" no scatter
    page = re.sub(r'(Milícias · )\d+( pontos)', rf'\g<1>{n}\g<2>', page, count=1)
    page = re.sub(r'(Performance média \(6 competências\) vs\. wave power · )\d+( sessões)',
                  rf'\g<1>{n}\g<2>', page, count=1)

    # ── 8. Footer ────────────────────────────────────────────────────────────
    data_full = fmt_full(nova['data'])
    page = re.sub(r'(Actualizado )\d+ \w+ \d{4}', rf'\g<1>{data_full}', page, count=1)
    print(f"  ✓ Footer: {data_full}")

    return html[:p_start] + page + html[p_end:]


def update_quiver(html, sd_list):
    """Actualiza a página Quiver (Última sessão + footer)."""
    q_start = html.find('id="page-quiver"')
    q_end_m = re.search(r'id="page-(?!quiver)[^"]*"', html[q_start + 20:])
    q_end   = q_start + 20 + q_end_m.start() if q_end_m else len(html)
    qpage   = html[q_start:q_end]

    for sd in sd_list:
        nova      = sd['sessoes'][0]
        data_full = fmt_full(nova['data'])
        qpage = re.sub(
            r'(Última sessão</div><div class="bc-val">)[^<]+(</div>)',
            rf'\g<1>{data_full} · {nova["spot"]}\g<2>',
            qpage, count=1)

    data_full = fmt_full(sd_list[0]['sessoes'][0]['data'])
    qpage = re.sub(r'(Actualizado )\d+ \w+ \d{4}', rf'\g<1>{data_full}', qpage, count=1)
    print(f"\n  ✓ Quiver · footer: {data_full}")

    return html[:q_start] + qpage + html[q_end:]


# ── Validação de dados ────────────────────────────────────────────────────────

def validate_session_data(sd, surfer):
    """Valida o JSON de um surfista antes de processar. Devolve True se OK."""
    ok = True
    nome = sd.get('surfer', surfer)

    if not sd.get('sessoes'):
        print(f"  ✗ [{nome}] 'sessoes' vazio ou ausente")
        return False

    nova = sd['sessoes'][0]

    # Campos obrigatórios na nova sessão
    required = ['html_id', 'data', 'wp_ef', 'classe', 'rec', 'peso']
    missing = [f for f in required if f not in nova]
    if missing:
        print(f"  ✗ [{nome}] Campos em falta em sessoes[0]: {missing}")
        ok = False

    # Precisa de skills ou skills_hist
    if 'skills' not in nova and 'skills_hist' not in nova:
        print(f"  ✗ [{nome}] sessoes[0] não tem 'skills' nem 'skills_hist'")
        ok = False

    # Validar todas as sessões
    for i, s in enumerate(sd['sessoes']):
        sid = s.get('html_id', f'sessao[{i}]')
        hist = get_skills_hist(s) if ('skills' in s or 'skills_hist' in s) else None
        if hist is None:
            print(f"  ⚠ [{nome}] {sid}: sem skills_hist nem skills")
        elif len(hist) != 6:
            print(f"  ✗ [{nome}] {sid}: skills_hist tem {len(hist)} elementos (esperado 6)")
            ok = False
        elif not all(v is None or 1 <= v <= 5 for v in hist):
            print(f"  ✗ [{nome}] {sid}: skills fora do intervalo 1–5: {hist}")
            ok = False

    # Validar insert_before_id aponta para sessão existente
    insert_id = sd.get('html', {}).get('insert_before_id')
    ids_json = [s.get('html_id') for s in sd['sessoes']]
    if insert_id and insert_id not in ids_json:
        print(f"  ✗ [{nome}] insert_before_id '{insert_id}' não existe em sessoes[]")
        ok = False

    # Validar nivel na nova sessão (P2.1)
    nova_nivel = nova.get('nivel')
    if nova_nivel is None:
        print(f"  ⚠ [{nome}] sessoes[0]: 'nivel' ausente — usar nivel_atual como fallback")
    else:
        valid_auto = {'assistido', 'autonomo', 'tecnico', 'performer'}
        valid_zona = {'espuma', 'inside', 'outside', 'largo'}
        if nova_nivel.get('autonomia') not in valid_auto:
            print(f"  ✗ [{nome}] sessoes[0]: nivel.autonomia '{nova_nivel.get('autonomia')}' inválido")
            ok = False
        if nova_nivel.get('zona') not in valid_zona:
            print(f"  ✗ [{nome}] sessoes[0]: nivel.zona '{nova_nivel.get('zona')}' inválido")
            ok = False

    # Validar progressão presente
    if 'progressao' not in sd:
        print(f"  ✗ [{nome}] 'progressao' ausente no JSON")
        ok = False

    if ok:
        print(f"  ✓ [{nome}] Dados validados ({len(sd['sessoes'])} sessões)")
    return ok


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args or args == ['ambos']:
        surfers = ['rodrigo', 'tomas']
    else:
        surfers = args

    for s in surfers:
        if s not in ('rodrigo', 'tomas'):
            print(f"Surfer inválido: '{s}'. Usar: rodrigo · tomas · ambos")
            sys.exit(1)

    html = HTML_PATH.read_text(encoding='utf-8')
    print(f"HTML: {len(html):,} bytes · {html.count(chr(10))+1} linhas")

    bak = HTML_PATH.with_suffix('.html.bak')
    shutil.copy(HTML_PATH, bak)
    print(f"Backup: {bak.name}")

    sd_list = []
    errors = False
    for surfer in surfers:
        json_path = BASE / f"data/{surfer}.json"
        if not json_path.exists():
            print(f"Ficheiro não encontrado: {json_path}")
            sys.exit(1)
        try:
            sd = json.loads(json_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON inválido em {json_path.name}: {e}")
            sys.exit(1)
        sd_list.append(sd)

        if not validate_session_data(sd, surfer):
            errors = True

    if errors:
        print("\n✗ Erros de validação — corrigir JSON antes de continuar.")
        sys.exit(1)

    for sd in sd_list:
        surfer = sd['surfer'].lower()
        nova = sd['sessoes'][0]
        insert_id = sd['html']['insert_before_id']
        if nova['html_id'] == insert_id:
            print(f"\n  ⚠ [{sd['surfer']}] sessoes[0].html_id == insert_before_id ('{insert_id}')")
            print(f"     O script só deve ser executado para inserir uma NOVA sessão.")
            print(f"     Actualiza sessions/{surfer}.md e o JSON com a nova sessão primeiro.")
            sys.exit(1)
        html = update_surfer(html, surfer, sd)

    html = update_quiver(html, sd_list)

    HTML_PATH.write_text(html, encoding='utf-8')
    print(f"\n✅ surf_log.html gravado: {len(html):,} bytes")
    print("\nPróximos passos:")
    print("  1. Verificar no browser (GitHub Pages local ou abrir ficheiro)")
    print("  2. Actualizar html.insert_before_id nos JSONs → novo html_id da sessão inserida")
    print("  3. git add surf_log.html && git commit -m 'Sessão SX' && git push")


if __name__ == '__main__':
    main()
