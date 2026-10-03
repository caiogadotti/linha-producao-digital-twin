import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import modelo as m

TEAL, AMB, DARK, RED, GRAY = "#0F766E", "#F59E0B", "#0B2E2B", "#DC2626", "#94A3B8"
COR_ESTADO = {"trabalhando": TEAL, "quebrada": RED, "bloqueada": AMB, "ociosa": "#CBD5E1"}
st.set_page_config(page_title="Linha de Produção · Digital Twin", page_icon="🏭", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
h1, h2, h3 {{ font-family: 'Instrument Serif', serif !important; font-weight: 400 !important; }}
.hero {{ background: {DARK}; color: #fff; padding: 28px 32px; border-radius: 18px; margin-bottom: 18px; }}
.hero h1 {{ color: #fff; margin: 0; font-size: 2.8rem !important; }}
.hero p {{ color: #99F6E4; font-size: 1.1rem; margin: 6px 0 0; }}
.box {{ background: #E6F2F1; color: #1E293B; border-radius: 14px; padding: 14px 18px; margin-bottom: 12px; }}
.box b {{ color: {TEAL}; }}
.eyebrow {{ color: {TEAL}; font-weight: 600; letter-spacing: .12em; font-size: .78rem; text-transform: uppercase; }}
.result {{ background: {DARK}; color: #fff; border-radius: 14px; padding: 16px 20px; margin-bottom: 12px; }}
.result .num {{ font-family: 'Instrument Serif', serif; font-size: 2.4rem; color: {AMB}; line-height: 1.1; }}
div[data-testid="stMetric"] {{ background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 10px 14px; }}
.stTabs [data-baseweb="tab"] {{ font-size: 1rem; padding: 10px 16px; }}
.stTabs [data-baseweb="tab-list"] {{ flex-wrap: wrap; }}
.flow {{ display:flex; gap:8px; align-items:stretch; flex-wrap:wrap; margin:6px 0 18px; }}
.flow .st {{ border-radius:12px; padding:10px 14px; min-width:120px; color:#1E293B; background:#E6F2F1; }}
.flow .st.gar {{ background:{DARK}; color:#fff; }}
.flow .st small {{ display:block; opacity:.75; }}
.flow .st b {{ font-size:1.05rem; }}
.flow i {{ color:{GRAY}; font-style:normal; font-size:1.3rem; align-self:center; }}
.flow .q {{ align-self:center; color:#B45309; font-size:.8rem; font-weight:600; }}
.hint {{ color:#475569; font-size:.95rem; background:#FFF7ED; border-radius:10px; padding:10px 14px; margin-top:10px; }}
</style>""", unsafe_allow_html=True)

st.markdown("""<div class="hero"><h1>🏭 Linha de Produção · Digital Twin</h1>
<p>Simulação de eventos discretos: mude a fábrica no painel e veja onde a produção trava</p>
<p style="color:#CBD5E1;font-size:.95rem;margin-top:14px">Caio Gadotti · Projeto da faculdade · ESCF, Engenharia de Sistemas Ciberfísicos · PUC-SP</p></div>""",
            unsafe_allow_html=True)


def layout(fig, h=360, **kw):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="#fff",
                      paper_bgcolor="#fff", font=dict(family="Inter", color="#1E293B"),
                      legend=dict(orientation="h", y=1.12), **kw)
    fig.update_xaxes(gridcolor="#F1F5F9")
    fig.update_yaxes(gridcolor="#F1F5F9")
    return fig


def resultado(num, texto):
    st.markdown(f'<div class="result"><div class="num">{num}</div>{texto}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- configuração
with st.sidebar:
    st.markdown("### A simulação")
    horas = st.slider("Horas simuladas por replicação", 8, 160, 40, 8)
    reps = st.slider("Replicações (sementes diferentes)", 2, 20, 6)
    semente = st.number_input("Semente inicial", 0, 9999, 0)
    st.caption("Cada replicação descarta 4 h de aquecimento, para a linha começar cheia. "
               "Os números vêm com intervalo de confiança de 95% entre replicações.")
    st.divider()
    st.markdown("""**Como funciona**

Cada peça passa pelas estações em ordem. Uma estação tem uma ou mais máquinas, tempo de ciclo
aleatório (lognormal), quebras (tempo entre falhas exponencial) e um buffer de entrada.

Se o buffer seguinte está cheio, a peça pronta fica presa na máquina: ela fica **bloqueada**.
Se não chega peça, fica **ociosa**.""")
    st.divider()
    st.markdown("**Caio Gadotti**  \nProjeto da faculdade · ESCF (Engenharia de Sistemas Ciberfísicos), PUC-SP")

COLS = {"nome": "Estação", "maquinas": "Máquinas", "tempo_medio": "Ciclo (min)", "cv": "Variação (CV)",
        "mtbf": "MTBF (min)", "mttr": "MTTR (min)", "buffer": "Buffer entrada"}

if "linha" not in st.session_state:
    st.session_state.linha = pd.DataFrame([{k: getattr(e, k) for k in COLS} for e in m.LINHA_PADRAO]).rename(columns=COLS)

st.markdown('<div class="eyebrow">A fábrica</div>', unsafe_allow_html=True)
st.caption("Edite a tabela: adicione ou remova estações, troque tempos, máquinas e buffers. "
           "MTBF = 0 significa máquina que não quebra. O buffer da primeira estação é ignorado (matéria-prima sempre disponível).")
df = st.data_editor(
    st.session_state.linha, num_rows="dynamic", width="stretch", hide_index=True, key="editor",
    column_config={
        "Máquinas": st.column_config.NumberColumn(min_value=1, max_value=10, step=1),
        "Ciclo (min)": st.column_config.NumberColumn(min_value=0.05, max_value=60.0, step=0.05, format="%.2f"),
        "Variação (CV)": st.column_config.NumberColumn(min_value=0.0, max_value=2.0, step=0.05, format="%.2f",
                                                       help="Desvio-padrão / média do tempo de ciclo"),
        "MTBF (min)": st.column_config.NumberColumn(min_value=0.0, step=10.0, help="Tempo médio de operação entre quebras"),
        "MTTR (min)": st.column_config.NumberColumn(min_value=0.0, step=1.0, help="Tempo médio de reparo"),
        "Buffer entrada": st.column_config.NumberColumn(min_value=0, max_value=200, step=1),
    })
df = df.dropna(subset=["Estação", "Ciclo (min)"]).fillna({"Máquinas": 1, "Variação (CV)": 0.3, "MTBF (min)": 0,
                                                            "MTTR (min)": 0, "Buffer entrada": 5})
if df.empty:
    st.warning("Adicione pelo menos uma estação.")
    st.stop()
linha_t = tuple((str(r["Estação"]), int(r["Máquinas"]), float(r["Ciclo (min)"]), float(r["Variação (CV)"]),
                 float(r["MTBF (min)"]), float(r["MTTR (min)"]), int(r["Buffer entrada"])) for _, r in df.iterrows())


def para_estacoes(t):
    return [m.Estacao(n, tempo_medio=c, cv=cv, maquinas=k, mtbf=b, mttr=r, buffer=buf)
            for n, k, c, cv, b, r, buf in t]


@st.cache_data(show_spinner=False)
def rodar(t, horas, reps, semente):
    return m.replicar(para_estacoes(t), reps=reps, semente=semente, horas=horas)


@st.cache_data(show_spinner=False)
def tp(t, horas, reps, semente):
    res = rodar(t, horas, reps, semente)
    return m.intervalo([r.throughput_h for r in res])


estacoes = para_estacoes(linha_t)
with st.spinner("Simulando a linha..."):
    res = rodar(linha_t, horas, reps, int(semente))
nomes = [e.nome for e in estacoes]
g_est = m.gargalo(estacoes)
estado_med = {n: {s: np.mean([r.estados[n][s] for r in res]) for s in m.ESTADOS} for n in nomes}
g_sim = int(np.argmax([estado_med[n]["trabalhando"] + estado_med[n]["quebrada"] for n in nomes]))

thr, thr_h = m.intervalo([r.throughput_h for r in res])
lt, lt_h = m.intervalo([r.lead_time_medio for r in res])
wip, wip_h = m.intervalo([r.wip_medio for r in res])
cap_g = estacoes[g_est].capacidade_efetiva

tabs = st.tabs(["📊 Visão geral", "🎯 Gargalo e cenários", "📦 Buffers", "🎲 Variabilidade", "✅ Validação"])

# ---------------------------------------------------------------- visão geral
with tabs[0]:
    c = st.columns(4)
    c[0].metric("Produção (peças/h)", f"{thr:.1f}", f"± {thr_h:.1f}", delta_color="off", delta_arrow="off")
    c[1].metric("Lead time médio (min)", f"{lt:.1f}", f"± {lt_h:.1f}", delta_color="off", delta_arrow="off")
    c[2].metric("Peças em processo (WIP)", f"{wip:.1f}", f"± {wip_h:.1f}", delta_color="off", delta_arrow="off")
    c[3].metric("Eficiência do gargalo", f"{100 * thr / cap_g:.0f}%",
                f"limite {cap_g:.1f} peças/h", delta_color="off", delta_arrow="off")

    partes = []
    for i, e in enumerate(estacoes):
        if i > 0:
            fila = np.mean([r.fila_media[e.nome] for r in res])
            partes.append(f'<i>→</i><span class="q">fila {fila:.1f}/{max(e.buffer, 1)}</span><i>→</i>')
        uso = estado_med[e.nome]["trabalhando"]
        partes.append(f'<div class="st {"gar" if i == g_sim else ""}"><b>{e.nome}</b>'
                      f'<small>{e.maquinas}× · {e.tempo_medio:.2f} min</small>'
                      f'<small>trabalhando {100 * uso:.0f}%</small></div>')
    st.markdown('<div class="flow">' + "".join(partes) + "</div>", unsafe_allow_html=True)
    st.caption("Em destaque: a estação que mais fica ocupada na simulação (o gargalo observado).")

    a, b = st.columns([3, 2])
    with a:
        st.markdown('<div class="eyebrow">Onde cada estação gasta o tempo</div>', unsafe_allow_html=True)
        fig = go.Figure()
        for s in m.ESTADOS:
            fig.add_bar(y=nomes, x=[100 * estado_med[n][s] for n in nomes], name=s, orientation="h",
                        marker_color=COR_ESTADO[s], hovertemplate="%{y}: %{x:.1f}%<extra>" + s + "</extra>")
        layout(fig, barmode="stack", xaxis_title="% do tempo", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
        st.markdown('<div class="hint">Antes do gargalo as máquinas ficam <b>bloqueadas</b> (amarelo): '
                    'produzem, mas não têm onde pôr a peça. Depois dele ficam <b>ociosas</b> (cinza): '
                    'esperam peça. É assim que se acha o gargalo olhando o chão de fábrica.</div>',
                    unsafe_allow_html=True)
    with b:
        st.markdown('<div class="eyebrow">Tempo de atravessamento (lead time)</div>', unsafe_allow_html=True)
        todos = np.concatenate([r.lead_times for r in res])
        corte = np.percentile(todos, 99.5)
        fig = go.Figure(go.Histogram(x=todos[todos <= corte], nbinsx=40, marker_color=TEAL, opacity=.85))
        for q, nome, cor, pos in [(50, "mediana", DARK, "top left"), (95, "P95", AMB, "top right")]:
            v = np.percentile(todos, q)
            fig.add_vline(x=v, line_color=cor, line_dash="dash", annotation_text=f"{nome} {v:.0f} min",
                          annotation_position=pos)
        layout(fig, xaxis_title="minutos da entrada até sair embalada", yaxis_title="peças", showlegend=False)
        st.caption(f"Mostra até o percentil 99,5. A peça mais lenta levou {todos.max():.0f} min, presa atrás de uma quebra.")
        st.plotly_chart(fig, width="stretch")

    st.markdown('<div class="eyebrow">Peças em processo ao longo do turno (1ª replicação)</div>', unsafe_allow_html=True)
    s0 = res[0].wip_serie
    s0 = s0[s0[:, 0] >= 4]
    passo = max(len(s0) // 3000, 1)
    fig = go.Figure(go.Scatter(x=s0[::passo, 0], y=s0[::passo, 1], line=dict(color=TEAL, width=1, shape="hv"),
                               fill="tozeroy", fillcolor="rgba(15,118,110,.08)"))
    fig.add_hline(y=res[0].wip_medio, line_color=AMB, line_dash="dash", annotation_text="média")
    layout(fig, 260, xaxis_title="hora", yaxis_title="WIP", showlegend=False)
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- gargalo
with tabs[1]:
    st.markdown("### Se eu puder comprar uma máquina, onde coloco?")
    st.markdown('<div class="box">A conta de bolso diz: na estação de <b>menor capacidade</b> '
                '(máquinas × 60 / ciclo × disponibilidade). A simulação testa cada opção de verdade, '
                'com variabilidade, quebras e buffers, e mostra quanto a produção sobe em cada uma.</div>',
                unsafe_allow_html=True)
    cap = pd.DataFrame({"Estação": nomes,
                        "Capacidade bruta (peças/h)": [e.capacidade_bruta for e in estacoes],
                        "Disponibilidade": [e.disponibilidade for e in estacoes],
                        "Capacidade efetiva (peças/h)": [e.capacidade_efetiva for e in estacoes]})
    with st.spinner("Testando +1 máquina em cada estação..."):
        ganhos = []
        for i in range(len(linha_t)):
            t2 = list(linha_t)
            n_, k_, *resto = t2[i]
            t2[i] = (n_, k_ + 1, *resto)
            ganhos.append(tp(tuple(t2), horas, reps, int(semente)))
    cap["Produção com +1 máquina"] = [g[0] for g in ganhos]
    cap["Ganho (peças/h)"] = cap["Produção com +1 máquina"] - thr
    a, b = st.columns([3, 2])
    with a:
        fig = go.Figure(go.Bar(x=nomes, y=cap["Ganho (peças/h)"], error_y=dict(array=[g[1] for g in ganhos]),
                               marker_color=[DARK if i == int(np.argmax(cap["Ganho (peças/h)"])) else TEAL
                                             for i in range(len(nomes))]))
        layout(fig, yaxis_title="peças/h a mais", showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with b:
        melhor = int(np.argmax(cap["Ganho (peças/h)"]))
        resultado(f"+{cap['Ganho (peças/h)'][melhor]:.1f} peças/h",
                  f"colocando a máquina em <b>{nomes[melhor]}</b>. "
                  f"Em qualquer outra estação o ganho fica entre "
                  f"{cap['Ganho (peças/h)'].drop(melhor).min():.1f} e {cap['Ganho (peças/h)'].drop(melhor).max():.1f}.")
        if melhor == g_est:
            st.success(f"A conta de bolso acertou: {nomes[g_est]} é a de menor capacidade efetiva.")
        else:
            st.warning(f"A conta de bolso apontava {nomes[g_est]}, mas a simulação mostra {nomes[melhor]}. "
                       "Variabilidade e buffers mudaram o gargalo.")
    st.dataframe(cap.style.format({"Capacidade bruta (peças/h)": "{:.1f}", "Disponibilidade": "{:.1%}",
                                   "Capacidade efetiva (peças/h)": "{:.1f}", "Produção com +1 máquina": "{:.1f}",
                                   "Ganho (peças/h)": "{:+.1f}"}), width="stretch", hide_index=True)
    st.markdown('<div class="hint">Depois de reforçar o gargalo, ele muda de lugar. Experimente somar a máquina '
                'na tabela lá em cima e rodar de novo: a segunda compra quase sempre vai para outra estação.</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------- buffers
with tabs[2]:
    st.markdown("### Quanto estoque intermediário vale a pena?")
    st.markdown('<div class="box">Buffer absorve quebras e oscilações: quando uma máquina para, a vizinha '
                'continua trabalhando com o que está na fila. Só que buffer custa espaço e dinheiro parado, '
                'e todo item nele aumenta o <b>lead time</b>. A curva mostra o retorno de cada vaga.</div>',
                unsafe_allow_html=True)
    opcoes = nomes[1:]
    if not opcoes:
        st.info("Com uma estação só não há buffer entre máquinas.")
    else:
        c1, c2 = st.columns([2, 1])
        alvo = c1.selectbox("Buffer na entrada de", opcoes, index=max(g_sim - 1, 0) if g_sim > 0 else 0)
        maxb = c2.slider("Até quantas vagas", 5, 60, 30, 5)
        idx = nomes.index(alvo)
        tamanhos = sorted(set(np.linspace(0, maxb, 11).astype(int)))
        pontos = []
        with st.spinner("Simulando cada tamanho de buffer..."):
            for bsz in tamanhos:
                t2 = list(linha_t)
                *ini, _ = t2[idx]
                t2[idx] = (*ini, int(bsz))
                rr = rodar(tuple(t2), horas, max(reps, 12), int(semente))
                pontos.append((bsz, *m.intervalo([r.throughput_h for r in rr]),
                               np.mean([r.lead_time_medio for r in rr])))
        pts = np.array(pontos)
        fig = go.Figure()
        fig.add_scatter(x=pts[:, 0], y=pts[:, 1], error_y=dict(array=pts[:, 2]), name="produção (peças/h)",
                        line=dict(color=TEAL, width=3), mode="lines+markers")
        fig.add_scatter(x=pts[:, 0], y=pts[:, 3], name="lead time (min)", yaxis="y2",
                        line=dict(color=AMB, width=2, dash="dot"), mode="lines+markers")
        layout(fig, 400, xaxis_title=f"vagas no buffer antes de {alvo}", yaxis_title="peças/h",
               yaxis2=dict(title="lead time (min)", overlaying="y", side="right", showgrid=False))
        st.plotly_chart(fig, width="stretch")
        st.caption("Esta aba usa no mínimo 12 replicações por ponto: o efeito do buffer é pequeno perto do ruído das quebras.")
        envelope = np.maximum.accumulate(pts[:, 1])
        alvo90 = envelope[0] + 0.9 * (envelope[-1] - envelope[0])
        joelho = int(pts[np.argmax(envelope >= alvo90), 0])
        resultado(f"{joelho} vagas",
                  f"já entregam 90% do ganho possível nesse ponto ({pts[0, 1]:.1f} → {envelope[-1]:.1f} peças/h). "
                  "Daí para frente o buffer quase só aumenta o lead time.")

# ---------------------------------------------------------------- variabilidade
with tabs[3]:
    st.markdown("### Mesma média, menos produção")
    st.markdown('<div class="box">Duas linhas com o <b>mesmo tempo médio</b> de ciclo não produzem o mesmo. '
                'Quanto mais o tempo varia (CV = desvio / média), mais as estações se desencontram: '
                'uma fica bloqueada esperando vaga enquanto a outra fica ociosa esperando peça. '
                'Aqui o CV de todas as estações é trocado pelo valor do eixo, sem mexer em mais nada.</div>',
                unsafe_allow_html=True)
    cvs = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5]
    curvas = {}
    with st.spinner("Simulando níveis de variabilidade..."):
        for fator in (1.0, 0.0):
            nome = "buffers atuais" if fator else "sem buffer (1 vaga)"
            ys = []
            for cv in cvs:
                t2 = tuple((n_, k_, c_, cv, b_, r_, buf if fator else 1) for n_, k_, c_, _, b_, r_, buf in linha_t)
                ys.append(tp(t2, horas, reps, int(semente)))
            curvas[nome] = np.array(ys)
    fig = go.Figure()
    for (nome, ys), cor in zip(curvas.items(), [TEAL, RED]):
        fig.add_scatter(x=cvs, y=ys[:, 0], error_y=dict(array=ys[:, 1]), name=nome,
                        line=dict(color=cor, width=3), mode="lines+markers")
    fig.add_hline(y=cap_g, line_dash="dash", line_color=GRAY, annotation_text="capacidade efetiva do gargalo")
    layout(fig, 400, xaxis_title="CV do tempo de ciclo (todas as estações)", yaxis_title="peças/h")
    st.plotly_chart(fig, width="stretch")
    base = curvas["buffers atuais"]
    resultado(f"−{100 * (1 - base[-1, 0] / base[0, 0]):.0f}%",
              f"de produção indo de CV 0 para CV 1,5 com os buffers atuais. Sem buffer a perda é de "
              f"{100 * (1 - curvas['sem buffer (1 vaga)'][-1, 0] / curvas['sem buffer (1 vaga)'][0, 0]):.0f}%. "
              "Reduzir variação (padronizar setup, manutenção, treinamento) é capacidade que não custa máquina.")

# ---------------------------------------------------------------- validação
with tabs[4]:
    st.markdown("### O simulador acerta onde existe resposta exata?")
    st.markdown('<div class="box">Uma linha inteira não tem fórmula fechada, por isso se simula. Mas casos '
                'particulares têm: uma estação com chegadas de Poisson e tempo exponencial é a fila '
                '<b>M/M/1</b>, e com c máquinas é a <b>M/M/c</b> (Erlang C). Se o simulador bate com elas, '
                'dá para confiar nele quando não há fórmula.</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c = c1.slider("Máquinas (c)", 1, 4, 1)
    mu = 1 / c2.slider("Tempo médio de atendimento (min)", 0.5, 3.0, 1.0, 0.25)
    rhos = np.round(np.arange(0.3, 0.95, 0.1), 2)
    hv = c3.slider("Horas por replicação", 50, 400, 200, 50)

    @st.cache_data(show_spinner=False)
    def valida(c, mu, hv, reps, semente):
        linhas = []
        for rho in rhos:
            lam = rho * c * mu
            est = [m.Estacao("fila", tempo_medio=1 / mu, maquinas=c, distribuicao="exponencial")]
            rr = m.replicar(est, reps=reps, semente=semente, horas=hv, aquecimento_h=10, chegada_media=1 / lam)
            teo = m.mm1_teorico(lam, mu) if c == 1 else m.mmc_teorico(lam, mu, c)
            w, wh = m.intervalo([r.lead_time_medio for r in rr])
            L = np.mean([r.wip_medio for r in rr])
            linhas.append({"ρ": rho, "W teórico": teo["W"], "W simulado": w, "± IC95": wh,
                           "L teórico": teo["L"], "L simulado": L,
                           "λ·W (Little)": lam * w, "erro W": w / teo["W"] - 1})
        return pd.DataFrame(linhas)

    with st.spinner("Comparando com a teoria de filas..."):
        v = valida(c, mu, hv, reps, int(semente))
    a, b = st.columns([3, 2])
    with a:
        fig = go.Figure()
        xs = np.linspace(rhos.min(), rhos.max(), 100)
        ws = [(m.mm1_teorico(r * c * mu, mu) if c == 1 else m.mmc_teorico(r * c * mu, mu, c))["W"] for r in xs]
        fig.add_scatter(x=xs, y=ws, name="fórmula", line=dict(color=DARK, width=2))
        fig.add_scatter(x=v["ρ"], y=v["W simulado"], error_y=dict(array=v["± IC95"]), name="simulação",
                        mode="markers", marker=dict(color=AMB, size=10))
        layout(fig, 380, xaxis_title="ocupação ρ = λ / (c·μ)", yaxis_title="tempo no sistema W (min)")
        st.plotly_chart(fig, width="stretch")
    with b:
        resultado(f"{100 * v['erro W'].abs().mean():.1f}%",
                  "de erro médio entre o tempo simulado e a fórmula. O erro cresce perto de ρ = 1, onde a fila "
                  "demora mais para estabilizar: aumente as horas por replicação e ele cai.")
        st.latex(r"W_{M/M/1} = \frac{1}{\mu-\lambda} \qquad L = \lambda W")
    st.dataframe(v.style.format({"ρ": "{:.1f}", "W teórico": "{:.2f}", "W simulado": "{:.2f}", "± IC95": "{:.2f}",
                                 "L teórico": "{:.2f}", "L simulado": "{:.2f}", "λ·W (Little)": "{:.2f}",
                                 "erro W": "{:+.1%}"}), width="stretch", hide_index=True)
    st.markdown('<div class="hint">A coluna λ·W confere a <b>Lei de Little</b> (L = λW) com os números da própria '
                'simulação. Ela vale para qualquer sistema estável, inclusive a linha da primeira aba: '
                f'lá, {thr / 60:.3f} peças/min × {lt:.1f} min = {thr / 60 * lt:.1f}, contra WIP medido de {wip:.1f}.</div>',
                unsafe_allow_html=True)
