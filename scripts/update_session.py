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

import sys, json, re, shutil, pathlib, math
from datetime import datetime

BASE      = pathlib.Path(__file__).resolve().parent.parent
HTML_PATH = BASE / "surf_log.html"

# ── Constantes ────────────────────────────────────────────────────────────────

SKILL_ORDER  = ['leitura', 'takeoff', 'paddle', 'manobras', 'equilibrio', 'posicionamento']
SKILL_NAMES  = ['🌊 Leitura de onda', '🏄 Take-off', '🚣 Paddle',
                '↩️ Manobras', '⚖️ Equilíbrio', '🧭 Posicionamento']
SKILL_COLORS = ['#2e86c1', '#e67e22', '#1e8449', '#c0392b', '#8e44ad', '#d4a017']
SKILL_DASHED = [False, False, True, False, False, False]  # paddle tem dash

# Escala scatter: piecewise linear (wave power kW/m → pixel x)
SCATTER_X = [(0,45), (2,56), (4,66), (18,140), (35,231), (50,310)]

# Mapeamento skill_order → chave no JSON progressao
PROG_KEYS = ['leitura_onda', 'takeoff', 'paddle', 'manobras', 'equilibrio', 'posicionamento']

# Nomes de exibição — Sistema de Níveis (CLAUDE.md)
AUTONOMIA_NOMES = {'assistido': 'Assistido', 'autonomo': 'Autónomo', 'tecnico': 'Técnico', 'performer': 'Performer'}
ZONA_NOMES      = {'espuma': 'Espuma', 'inside': 'Inside', 'outside': 'Outside', 'largo': 'Largo'}
AUTONOMIA_ORDEM = ['assistido', 'autonomo', 'tecnico', 'performer']

# Títulos curtos por skill no card "Evolução" (spark-card)
SPARK_TITLES = ['🌊 Leitura', '🏄 Take-off', '🚣 Paddle', '↩️ Manobras', '⚖️ Equilíbrio', '🧭 Posicion.']

# Cores da banda "esperada" por veredicto (fundo, linha threshold) — G.1
BAND_COLORS = {
    'verde':    ('#edf8f1', '#60c080'),
    'laranja':  ('#fef9ec', '#e0c060'),
    'vermelha': ('#fdf0f0', '#e07060'),
}

# Direcções de swell marcadas como Desfavorável na rosa das Milícias (costa sul)
_DESFAV_DIRS_MILICIA = {'E', 'ENE', 'NE', 'NNE', 'S', 'SE', 'SSE', 'SSW'}

# Pesos de recência global (índice 0 = sessão mais recente)
_REC_W = [1.00, 1.00, 0.60, 0.40, 0.25, 0.15, 0.10, 0.07, 0.05, 0.03] + [0.02] * 100

# Fallback matriz wave power por nível quando não há sessões na classe
_MATRIX_FALLBACK = {
    #              Fracas  Aceit.  Boas  Ideais  Exig.  M.Exig.
    'iniciacao': ['⚠️',   '⚠️',  '❌', '❌',   '❌',  '❌'],
    'progresso': ['⚠️',   '✅',  '✅', '⚠️',   '❌',  '❌'],
    'autonomo':  ['⚠️',   '✅',  '✅', '⚠️',   '❌',  '❌'],
    'tecnico':   ['⚠️',   '✅',  '✅', '✅',    '⚠️',  '❌'],
    'avancado':  ['⚠️',   '✅',  '✅', '✅',    '✅',  '⚠️'],
}
_MATRIX_CLASSES = ['Fracas', 'Aceitáveis', 'Boas', 'Ideais', 'Exigentes', 'Muito exig.']

MESES_ABR  = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
              7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
MESES_FULL = {1:'Janeiro',2:'Fevereiro',3:'Março',4:'Abril',5:'Maio',6:'Junho',
              7:'Julho',8:'Agosto',9:'Setembro',10:'Outubro',11:'Novembro',12:'Dezembro'}

# ── Funções matemáticas ───────────────────────────────────────────────────────

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
    """Média dos skills não-nulos, ou None se nenhum skill for avaliável (G.7) —
    uma sessão sem avaliação não tem performance média; 0 seria inventar o pior resultado."""
    h = get_skills_hist(sessao)
    vals = [v for v in h if v is not None]
    return sum(vals) / len(vals) if vals else None

# ── Helpers de formatação ─────────────────────────────────────────────────────

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

def find_block_end(text, start):
    """A partir do índice de um '<div' de abertura em `start`, devolve o índice
    logo após o '</div>' de fecho correspondente (contagem balanceada). -1 se não fechar."""
    depth = 0
    for m in re.finditer(r'<div\b|</div>', text[start:]):
        if m.group() == '</div>':
            depth -= 1
            if depth == 0:
                return start + m.end()
        else:
            depth += 1
    return -1

def autonomia_banda(autonomia):
    """(low, mid, threshold) da banda 'esperada' para este nível de autonomia.
    Reverse-engineered a partir dos 2 níveis com dados reais no HTML (tecnico 3.0–4.0,
    autonomo 2.5–3.5): mid = 2.5 + 0.5*índice, banda = mid±0.5. Extrapolado para
    assistido/performer (mid=2.5 e mid=4.0) — sem dados reais desses 2 níveis para confirmar."""
    idx = AUTONOMIA_ORDEM.index(autonomia)
    mid = 2.5 + 0.5 * idx
    return mid - 0.5, mid, mid + 0.5

def spark_y(val):
    """Valor 1–5 → coordenada Y no sparkline (viewBox 0 0 100 44). Y = 48 - val*8."""
    return round(48 - val * 8)

def radar_point(valor, idx, cx=110, cy=110, escala=18):
    """Valor 1–5 no eixo `idx` (0=Leitura topo, sentido horário, 60° por eixo) →
    coordenada (x,y) no radar hexagonal (viewBox 0 0 220 220, centro 110,110, r=valor*18)."""
    ang = math.radians(idx * 60)
    r = valor * escala
    return round(cx + r * math.sin(ang)), round(cy - r * math.cos(ang))

_RADAR_STATIC = '''<svg viewBox="0 0 220 220" width="220" height="220" xmlns="http://www.w3.org/2000/svg" font-family="Barlow,sans-serif">
            <!-- Rings L1–L5 -->
            <polygon points="110,92 126,101 126,119 110,128 94,119 94,101" fill="none" stroke="#e8e4dc" stroke-width="0.7"/>
            <polygon points="110,74 141,92 141,128 110,146 79,128 79,92" fill="none" stroke="#e8e4dc" stroke-width="0.7"/>
            <polygon points="110,56 157,83 157,137 110,164 63,137 63,83" fill="none" stroke="#e8e4dc" stroke-width="0.7"/>
            <polygon points="110,38 172,74 172,146 110,182 48,146 48,74" fill="none" stroke="#e0dbd2" stroke-width="0.8"/>
            <polygon points="110,20 188,65 188,155 110,200 32,155 32,65" fill="none" stroke="#d5d0c8" stroke-width="1"/>
            <!-- Axis lines -->
            <g stroke="#e0ddd6" stroke-width="0.5">
              <line x1="110" y1="110" x2="110" y2="20"/>
              <line x1="110" y1="110" x2="188" y2="65"/>
              <line x1="110" y1="110" x2="188" y2="155"/>
              <line x1="110" y1="110" x2="110" y2="200"/>
              <line x1="110" y1="110" x2="32" y2="155"/>
              <line x1="110" y1="110" x2="32" y2="65"/>
            </g>
            <!-- Expected polygon — {nivel_label} midpoint r={mid_r} (tracejado) -->
            <polygon points="{esperado}" fill="none" stroke="#bbb" stroke-width="1.2" stroke-dasharray="4,3"/>
            <!-- Athlete polygon — {surfer} (leitura,takeoff,paddle,manobras,equilibrio,posic.) -->
            <polygon points="{atleta}" fill="rgba(41,128,185,0.15)" stroke="#2980b9" stroke-width="2" stroke-linejoin="round"/>
            <!-- Axis labels -->
            <text x="110" y="10" text-anchor="middle" font-size="9" fill="#555">Leitura</text>
            <text x="193" y="63" text-anchor="start" font-size="9" fill="#555">Take-off</text>
            <text x="193" y="158" text-anchor="start" font-size="9" fill="#555">Paddle</text>
            <text x="110" y="213" text-anchor="middle" font-size="9" fill="#555">Manobras</text>
            <text x="27" y="158" text-anchor="end" font-size="9" fill="#555">Equilíbrio</text>
            <text x="27" y="63" text-anchor="end" font-size="9" fill="#555">Posic.</text>
            <!-- Level labels on leitura axis -->
            <text x="114" y="128" font-size="7" fill="#ccc">1</text>
            <text x="114" y="110" font-size="7" fill="#ccc">2</text>
            <text x="114" y="92" font-size="7" fill="#ccc">3</text>
            <text x="114" y="74" font-size="7" fill="#ccc">4</text>
            <text x="114" y="56" font-size="7" fill="#ccc">5</text>
          </svg>'''

def gerar_evo_card(sd, nivel_prox_preservado, spark_next_preservados):
    """Gera o card 'Evolução' completo (evo-nivel-row + radar + 6 sparklines) — G.1/G.5/G.6.

    nivel_prox_preservado: texto a usar em evo-nivel-prox quando 'nivel_proximo' não
      existe no JSON — preservado do HTML anterior, nunca inventado (G.5).
    spark_next_preservados: lista de 6 textos 'próx. nível' (ordem SKILL_ORDER),
      preservados do HTML anterior — são copy curada, não deriváveis dos dados.
    """
    sessoes       = sd['sessoes']
    sessoes_crono = list(reversed(sessoes))
    prog          = sd['progressao']
    nivel_atual   = sd['nivel_atual']
    n             = len(sessoes)

    nivel_atual_txt = f"{AUTONOMIA_NOMES[nivel_atual['autonomia']]} · {ZONA_NOMES[nivel_atual['zona']]}"
    nivel_prox_json = sd.get('nivel_proximo')
    if nivel_prox_json:
        nivel_prox_txt = f"{AUTONOMIA_NOMES[nivel_prox_json['autonomia']]} · {ZONA_NOMES[nivel_prox_json['zona']]}"
    else:
        nivel_prox_txt = nivel_prox_preservado
        print(f"  ⚠ [{sd['surfer']}] nivel_proximo ausente — preservado do HTML ('{nivel_prox_txt}')")

    low, mid, threshold = autonomia_banda(nivel_atual['autonomia'])
    esperado_pts = ' '.join(f'{x},{y}' for x, y in (radar_point(mid, i) for i in range(6)))
    atleta_pts   = ' '.join(f'{x},{y}' for x, y in (radar_point(prog[PROG_KEYS[i]]['media'], i) for i in range(6)))

    radar_svg = _RADAR_STATIC.format(
        nivel_label=AUTONOMIA_NOMES[nivel_atual['autonomia']].lower(), mid_r=round(mid * 18),
        esperado=esperado_pts, surfer=sd['surfer'], atleta=atleta_pts)

    y_thresh = spark_y(threshold)
    spark_blocks = []
    for i, sk_key in enumerate(SKILL_ORDER):
        hist = [get_skills_hist(s)[i] for s in sessoes_crono]
        nh   = len(hist)
        xs   = [round(2 + j * 96 / (nh - 1)) if nh > 1 else 50 for j in range(nh)]
        pts_render = [(xs[j], spark_y(hist[j])) for j in range(nh) if hist[j] is not None]

        media    = prog[PROG_KEYS[i]]['media']
        estrelas = prog[PROG_KEYS[i]]['estrelas']
        color    = SKILL_COLORS[i]

        if   media >= threshold: verdict = 'verde'
        elif media >= low:       verdict = 'laranja'
        else:                    verdict = 'vermelha'
        fill, stroke = BAND_COLORS[verdict]

        nao_nulos = [v for v in hist if v is not None]
        if len(nao_nulos) >= 2:
            ultimo, penultimo = nao_nulos[-1], nao_nulos[-2]
            if   ultimo > penultimo: tcls, tsym = 'up',   '↑'
            elif ultimo < penultimo: tcls, tsym = 'down', '↓'
            else:                    tcls, tsym = 'flat', '→'
        else:
            tcls, tsym = 'flat', '→'

        if pts_render:
            poly = ' '.join(f'{x},{y}' for x, y in pts_render)
            cx_last, cy_last = pts_render[-1]
            circle = f'<circle cx="{cx_last}" cy="{cy_last}" r="2.5" fill="{color}" stroke="white" stroke-width="1"/>'
        else:
            poly, circle = '', ''

        estrelas_txt = '★' * estrelas + '☆' * (5 - estrelas)

        spark_blocks.append(
            f'          <div class="spark-card">\n'
            f'            <div class="spark-header">\n'
            f'              <span class="spark-title">{SPARK_TITLES[i]}</span>\n'
            f'              <span class="spark-trend-{tcls}">{tsym}</span>\n'
            f'            </div>\n'
            f'            <div style="display:flex;align-items:baseline;gap:6px;margin-bottom:4px">\n'
            f'              <span class="spark-val" style="color:{color}">{media:.1f}</span>\n'
            f'              <span class="spark-stars" style="color:{color}">{estrelas_txt}</span>\n'
            f'            </div>\n'
            f'            <svg viewBox="0 0 100 44" width="100%" height="44" xmlns="http://www.w3.org/2000/svg">\n'
            f'              <rect x="2" y="{y_thresh}" width="96" height="8" fill="{fill}"/>\n'
            f'              <line x1="2" y1="{y_thresh}" x2="98" y2="{y_thresh}" stroke="{stroke}" stroke-width="0.7" stroke-dasharray="2,2"/>\n'
            f'              <polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>\n'
            f'              {circle}\n'
            f'            </svg>\n'
            f'            <div class="spark-next">{spark_next_preservados[i]}</div>\n'
            f'          </div>')

    d_ultima = datetime.fromisoformat(sessoes[0]['data'])
    sessions_label = f'{n} sessões · {MESES_ABR[d_ultima.month]} {d_ultima.year}'

    return (
        f'    <div class="evo-card">\n'
        f'      <div class="evo-header">\n'
        f'        <span class="evo-header-title">📈 Evolução por competência</span>\n'
        f'        <span class="evo-sessions-label">{sessions_label}</span>\n'
        f'      </div>\n'
        f'      <div class="evo-body">\n'
        f'        <div class="evo-nivel-row">\n'
        f'          <span class="evo-nivel-atual">{nivel_atual_txt}</span>\n'
        f'          <span class="evo-nivel-seta">→</span>\n'
        f'          <span class="evo-nivel-prox">{nivel_prox_txt}</span>\n'
        f'        </div>\n'
        f'        <div class="radar-wrap">\n'
        f'          {radar_svg}\n'
        f'        </div>\n'
        f'        <div class="spark-grid">\n'
        + '\n'.join(spark_blocks) + '\n'
        f'        </div>\n'
        f'      </div>\n'
        f'    </div>'
    )

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

        d_nova = datetime.fromisoformat(nova['data'])
        ancora = next((s for s in sessoes[1:] if s.get('html_id') == insert_id), None)
        mes_ancora = datetime.fromisoformat(ancora['data']) if ancora else None

        if mes_ancora is not None and (d_nova.year, d_nova.month) != (mes_ancora.year, mes_ancora.month):
            # recuar o ponto de inserção para antes de um month-sep colado à âncora
            m_sep = re.search(r'<div class="month-sep">[^<]*</div>\s*$', page[:div_start])
            if m_sep:
                div_start = m_sep.start()
            sep_html = f'    <div class="month-sep">{MESES_FULL[d_nova.month]} {d_nova.year}</div>\n'
            page = page[:div_start] + sep_html + gerar_card(sd, nova) + page[div_start:]
            print(f"  ✓ Card {nova['html_id']} inserido antes de {insert_id} · novo separador '{MESES_FULL[d_nova.month]} {d_nova.year}'")
        else:
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

    # ── 3-5. Card "Evolução" (radar + sparklines + evo-nivel-row) — G.1/G.5/G.6 ──
    evo_marker = '<div class="evo-card">'
    evo_start = page.find(evo_marker)
    evo_end = find_block_end(page, evo_start) if evo_start != -1 else -1
    if evo_start == -1 or evo_end == -1:
        print(f"  ⚠ evo-card não encontrado ou malformado — Evolução NÃO actualizada")
    else:
        evo_old = page[evo_start:evo_end]
        m_prox = re.search(r'<span class="evo-nivel-prox">([^<]*)</span>', evo_old)
        nivel_prox_preservado = m_prox.group(1) if m_prox else ''
        spark_next_preservados = re.findall(r'<div class="spark-next">([^<]*)</div>', evo_old)
        if len(spark_next_preservados) != 6:
            print(f"  ⚠ evo-card: {len(spark_next_preservados)} spark-next encontrados (esperado 6) — Evolução NÃO actualizada")
        else:
            page = page[:evo_start] + gerar_evo_card(sd, nivel_prox_preservado, spark_next_preservados) + page[evo_end:]
            print(f"  ✓ Evolução: radar + 6 sparklines regenerados · {n} sessões")

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
        pm = perf_media(nova)
        if pm is None:
            print(f"  ⚠ Scatter: {nova['html_id']} sem skills avaliáveis — ponto não adicionado")
        else:
            cx  = wp_to_cx(nova['wp_ef'])
            cy  = perf_to_cy(pm)
            lbl = fmt_dd_m(nova['data'])
            new_pt = (
                f'            <circle cx="{cx}" cy="{cy}" r="5" fill="#1e8449" opacity="0.9"/>\n'
                f'            <text x="{cx}" y="{cy-8}" text-anchor="middle" '
                f'font-family="Barlow,sans-serif" font-size="7" fill="#1e8449">{lbl}</text>\n            ')
            page = (page[:sm.start()] + sm.group(1) + sm.group(2)
                    + new_pt + sm.group(3) + page[sm.end():])
            print(f"  ✓ Scatter: {lbl} · cx={cx} cy={cy} (perf={pm:.2f})")

        # Contar pontos efectivamente desenhados (G.7) — não len(sessoes), para não
        # divergir do rótulo quando uma sessão fica sem ponto (skills todos null)
        sm2 = scatter_pat.search(page)
        n_pontos = len(re.findall(r'<circle\b', sm2.group(2))) if sm2 else n
    else:
        print(f"  ⚠ Scatter SVG não encontrado")
        n_pontos = n

    # Actualizar "N pontos" e "N sessões" no scatter
    page = re.sub(r'(Milícias · )\d+( pontos)', rf'\g<1>{n_pontos}\g<2>', page, count=1)
    page = re.sub(r'(Performance média \(6 competências\) vs\. wave power · )\d+( sessões)',
                  rf'\g<1>{n_pontos}\g<2>', page, count=1)

    # ── 8. Footer ────────────────────────────────────────────────────────────
    data_full = fmt_full(nova['data'])
    page = re.sub(r'(Actualizado )\d+ \w+ \d{4}', rf'\g<1>{data_full}', page, count=1)
    print(f"  ✓ Footer: {data_full}")

    return html[:p_start] + page + html[p_end:]


def calc_matrix(data):
    """Calcula emoji de capacidade por classe de condições para um atleta.

    Regras:
    - < 2 sessões na classe → fallback por nível (sem dados suficientes)
    - ≥ 2 sessões → média ponderada por recência global (índice no array sessoes[])
    """
    nivel = data['nivel_atual']['autonomia']
    fallback = _MATRIX_FALLBACK.get(nivel, _MATRIX_FALLBACK['progresso'])
    all_sessions = data['sessoes']  # índice 0 = mais recente
    result = {}
    cls_map = {}
    for i, cls in enumerate(_MATRIX_CLASSES):
        cls_idx = [(idx, s) for idx, s in enumerate(all_sessions)
                   if s.get('classe') == cls and s.get('skills_hist')]
        cls_map[cls] = cls_idx
        if len(cls_idx) >= 2:
            total_w = sum(_REC_W[idx] for idx, _ in cls_idx)
            media = sum(
                _REC_W[idx] * sum(v for v in s['skills_hist'] if v is not None) /
                max(1, sum(1 for v in s['skills_hist'] if v is not None))
                for idx, s in cls_idx
            ) / total_w
            result[cls] = '✅' if media >= 3.0 else ('⚠️' if media >= 2.5 else '❌')
        else:
            result[cls] = fallback[i]
    data_classes = {cls for cls, entries in cls_map.items() if len(entries) >= 2}
    result = _apply_monotonicity(result, data_classes)
    return result


_CLS_HARDER_FIRST = ['Muito exig.', 'Exigentes', 'Ideais', 'Boas', 'Aceitáveis']
# Fracas excluída — tem semântica diferente ("pouco surf", não incapacidade)
_EMOJI_RANK = {'✅': 2, '⚠️': 1, '❌': 0}
_RANK_EMOJI = {2: '✅', 1: '⚠️', 0: '❌'}


def _apply_monotonicity(result, data_classes):
    """Propaga: se classe mais exigente tem melhor rating E ambas têm dados reais → eleva a mais fácil."""
    for i in range(len(_CLS_HARDER_FIRST) - 1):
        harder = _CLS_HARDER_FIRST[i]
        easier = _CLS_HARDER_FIRST[i + 1]
        if harder in data_classes and easier in data_classes:
            if _EMOJI_RANK[result[harder]] > _EMOJI_RANK[result[easier]]:
                result[easier] = result[harder]
    return result


def _matrix_row(label, r_val, t_val, inferred_r, inferred_t):
    r_cell = f'<td class="matrix-cell matrix-inferred" title="inferido por nível">{r_val}</td>' if inferred_r else f'<td class="matrix-cell">{r_val}</td>'
    t_cell = f'<td class="matrix-cell matrix-inferred" title="inferido por nível">{t_val}</td>' if inferred_t else f'<td class="matrix-cell">{t_val}</td>'
    return f'            <tr><td class="matrix-cond">{label}</td>{r_cell}{t_cell}</tr>'


def update_wave_matrix(html, sd_list):
    """Substitui os tbodys das tabelas Wave Power com valores calculados a partir dos JSONs."""
    # Normalizar nomes para lookup (tomás → tomas)
    by_name = {sd.get('surfer', '').lower().replace('á', 'a').replace('ã', 'a'): sd for sd in sd_list}
    # Se só um surfista foi processado, carregar o outro JSON para a matriz
    for surfer in ('rodrigo', 'tomas'):
        if surfer not in by_name:
            json_path = BASE / f'data/{surfer}.json'
            if json_path.exists():
                by_name[surfer] = json.loads(json_path.read_text(encoding='utf-8'))
    r_data = by_name.get('rodrigo')
    t_data = by_name.get('tomas')
    if r_data is None or t_data is None:
        print('  ⚠ Wave matrix: dados de um surfista em falta — a saltar')
        return html

    r_matrix = calc_matrix(r_data)
    t_matrix = calc_matrix(t_data)

    r_nivel = r_data['nivel_atual']['autonomia']
    t_nivel = t_data['nivel_atual']['autonomia']
    r_n_sess = sum(1 for s in r_data['sessoes'] if s.get('skills_hist'))
    t_n_sess = sum(1 for s in t_data['sessoes'] if s.get('skills_hist'))

    labels = [
        '&lt; 4 kW/m · Fracas',
        '4–7 kW/m · Aceitáveis',
        '7–10 kW/m · Boas',
        '10–18 kW/m · Ideais',
        '18–35 kW/m · Exigentes',
        '&gt; 35 kW/m · Muito exig.',
    ]
    rows = []
    for label, cls in zip(labels, _MATRIX_CLASSES):
        r_sessoes = [s for s in r_data['sessoes'] if s.get('classe') == cls and s.get('skills_hist')]
        t_sessoes = [s for s in t_data['sessoes'] if s.get('classe') == cls and s.get('skills_hist')]
        rows.append(_matrix_row(label, r_matrix[cls], t_matrix[cls], len(r_sessoes) < 2, len(t_sessoes) < 2))

    tbody_content = '\n'.join(rows)
    _d = datetime.now()
    data_hoje = f"{_d.day} {MESES_ABR[_d.month]} {_d.year}"
    footnote = (f'<p class="matrix-footnote">Gerado automaticamente · '
                f'Rodrigo: {r_n_sess} sessões ({r_nivel}) · '
                f'Tomás: {t_n_sess} sessões ({t_nivel}) · '
                f'actualizado em {data_hoje} · '
                f'<span style="opacity:.6">célula acinzentada = inferido por nível</span></p>')

    # Substituir os tbodys de todas as tabelas Wave Power (identificadas pelo header th "Wave Power")
    count = 0
    result = html
    search_start = 0
    while True:
        wp_pos = result.find('>Wave Power</th>', search_start)
        if wp_pos == -1:
            break
        tbody_start = result.find('<tbody>', wp_pos)
        tbody_end = result.find('</tbody>', tbody_start) + len('</tbody>')
        if tbody_start == -1 or tbody_end == -1:
            break
        old_tbody = result[tbody_start:tbody_end]
        new_tbody = f'<tbody>\n{tbody_content}\n          </tbody>'
        result = result[:tbody_start] + new_tbody + result[tbody_end:]
        # Also update the footnote after </table></div> following this matrix
        table_end = result.find('</table>', tbody_start + len(new_tbody)) + len('</table>')
        div_end = result.find('</div>', table_end) + len('</div>')
        # Remove existing footnote if any
        existing_fn = re.search(r'\s*<p class="matrix-footnote">[^<]*(?:<[^>]+>[^<]*)*</p>', result[div_end:div_end+400])
        if existing_fn:
            fn_start = div_end + existing_fn.start()
            fn_end = div_end + existing_fn.end()
            result = result[:fn_start] + result[fn_end:]
            div_end = div_end  # recalculate if needed
        result = result[:div_end] + f'\n      {footnote}' + result[div_end:]
        search_start = div_end + len(footnote) + 10
        count += 1

    print(f'  ✓ Wave Power matrix: {count} tabela(s) actualizadas · Rodrigo {r_nivel} · Tomás {t_nivel}')
    return result


def detect_spot_override(nova):
    """Avisa se swell desfavorável produziu perf ≥ 2.5 — candidato a spot_override."""
    swell_duo = nova.get('swell_duo', [])
    if not swell_duo or not nova.get('skills_hist'):
        return
    dir_raw = swell_duo[0].get('dir', '')
    # extrair cardinal do formato "↗ ENE 66°"
    parts = dir_raw.split()
    cardinal = parts[1] if len(parts) >= 2 else parts[0] if parts else ''
    if cardinal not in _DESFAV_DIRS_MILICIA:
        return
    vals = [v for v in nova['skills_hist'] if v is not None]
    if not vals:
        return
    pm = sum(vals) / len(vals)
    if pm >= 2.5:
        print(f"\n  ⚠  SPOT OVERRIDE DETECTADO: swell {dir_raw} (marcado Desfavorável) · perf média {pm:.1f}")
        print(f"     Considera adicionar spot_override a esta sessão no JSON.")


def agg_spot_overrides(sd_list):
    """Agrega todos os spot_override existentes nas sessões de todos os atletas."""
    overrides = []
    for sd in sd_list:
        for s in sd.get('sessoes', []):
            if 'spot_override' in s:
                overrides.append({
                    'data': s['data'],
                    'html_id': s['html_id'],
                    'surfer': sd.get('surfer', ''),
                    **s['spot_override']
                })
    return sorted(overrides, key=lambda x: x['data'])


def update_spot_overrides_section(html, sd_list):
    """Actualiza a secção 'Observações locais · Milícias' e o badge das rosas."""
    overrides = agg_spot_overrides(sd_list)
    n = len(overrides)

    # Badge das rosas: substituir contagem
    badge_txt = f'{n} observações locais' if n != 1 else '1 observação local'
    badge_style = ' style="background:#e67e22;color:white"' if n >= 3 else ''
    new_badge = f'<span class="rosa-badge"{badge_style}>{badge_txt}</span>'
    html = re.sub(r'<span class="rosa-badge"[^>]*>[^<]*</span>', new_badge, html)

    # Secção de overrides: substituir entre anchors
    anchor_start = '<!-- SPOT-OVERRIDES-START -->'
    anchor_end = '<!-- SPOT-OVERRIDES-END -->'
    if anchor_start not in html:
        return html

    if not overrides:
        section_html = ''
    else:
        items = []
        for ov in overrides:
            data_fmt = fmt_dd_m(ov['data'])
            items.append(
                f'          <div class="so-item">'
                f'<span class="so-dir">{ov.get("dir_swell","?")}</span> · '
                f'<span class="so-cond">{ov.get("condicao","?")}</span> · '
                f'{data_fmt} · perf {ov.get("performance","?")}<br>'
                f'<span class="so-nota">"{ov.get("nota","")}"</span> '
                f'<a href="#{ov["html_id"]}" class="so-link">[{ov["html_id"]}]</a>'
                f'</div>'
            )
        items_html = '\n'.join(items)
        section_html = f'''        <div class="so-card">
          <div class="so-header">Observações locais · Milícias</div>
          <p class="so-intro">Estas observações contradizem as classificações teóricas.<br>Revê as rosas quando houver ≥3 observações na mesma direcção.</p>
{items_html}
        </div>'''

    start_pos = html.find(anchor_start)
    end_pos = html.find(anchor_end) + len(anchor_end)
    html = html[:start_pos] + anchor_start + section_html + anchor_end + html[end_pos:]

    print(f'  ✓ Spot overrides: {n} observações locais · badge actualizado')
    return html


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

    # Campos de schema completo — avisos (⚠) para campos em falta mas não bloqueiam
    schema_warn = ['cond_obs', 'hs_obs', 'nivel', 'tags', 'notes', 'tide_strip', 'swell_duo', 'cond_grid']
    for campo in schema_warn:
        if campo not in nova:
            print(f"  ⚠ [{nome}] sessoes[0]: campo '{campo}' ausente")

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

    # Validar frescura do insert_before_id (G.2): tem de ser a sessão imediatamente
    # anterior à nova, senão o card entra na posição errada (ex: sob separador de mês antigo)
    if insert_id and len(sd['sessoes']) >= 2:
        sid_anterior = sd['sessoes'][1].get('html_id')
        sid_nova = sd['sessoes'][0].get('html_id')
        if insert_id != sid_nova and insert_id != sid_anterior:
            print(f"  ✗ [{nome}] insert_before_id '{insert_id}' desactualizado — devia ser '{sid_anterior}' (sessão imediatamente anterior)")
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


# ── Pre-flight ───────────────────────────────────────────────────────────────

def preflight_anchors(html, surfers, sd_list):
    """Verifica que todos os anchors críticos existem no HTML antes de qualquer escrita.
    Devolve True se OK; imprime erros claros e devolve False se algum faltar."""
    missing = []

    # Boundaries de página necessários
    page_ids = set(surfers) | {'quiver'}
    if 'rodrigo' in surfers:
        page_ids.add('tomas')

    for pid in sorted(page_ids):
        if f'id="page-{pid}"' not in html:
            missing.append(f'id="page-{pid}"')

    # insert_before_id — anchor HTML onde o novo card será inserido
    for sd in sd_list:
        insert_id = sd.get('html', {}).get('insert_before_id', '')
        if insert_id and f'id="{insert_id}"' not in html:
            missing.append(f'id="{insert_id}" (insert_before_id de {sd["surfer"]})')

    n_checked = len(page_ids) + len(sd_list)
    if missing:
        print("\n✗ PRE-FLIGHT FALHOU — anchors em falta no HTML:")
        for m in missing:
            print(f"    • {m}")
        print("  Corrigir o HTML ou o JSON antes de continuar.")
        return False

    print(f"  ✓ Pre-flight: {n_checked} anchor(s) verificado(s) — OK")
    return True


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

    if not preflight_anchors(html, surfers, sd_list):
        sys.exit(1)

    for surfer, sd in zip(surfers, sd_list):
        nova = sd['sessoes'][0]
        insert_id = sd['html']['insert_before_id']
        if nova['html_id'] == insert_id:
            print(f"\n  ⚠ [{sd['surfer']}] sessoes[0].html_id == insert_before_id ('{insert_id}')")
            print(f"     O script só deve ser executado para inserir uma NOVA sessão.")
            print(f"     Actualiza sessions/{surfer}.md e o JSON com a nova sessão primeiro.")
            sys.exit(1)
        detect_spot_override(nova)
        html = update_surfer(html, surfer, sd)

    html = update_wave_matrix(html, sd_list)
    html = update_spot_overrides_section(html, sd_list)
    html = update_quiver(html, sd_list)

    HTML_PATH.write_text(html, encoding='utf-8')
    print(f"\n✅ surf_log.html gravado: {len(html):,} bytes")
    print("\nPróximos passos:")
    print("  1. Verificar no browser (GitHub Pages local ou abrir ficheiro)")
    print("  2. Actualizar html.insert_before_id nos JSONs → novo html_id da sessão inserida")
    print("  3. git add surf_log.html && git commit -m 'Sessão SX' && git push")


if __name__ == '__main__':
    main()
