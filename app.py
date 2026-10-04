import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import modelo as m

import ui
from ui import TEAL, DARK, RED, GRAY, AMB_VIVO as AMB, como_ler, lead, resultado

COR_ESTADO = {"trabalhando": TEAL, "quebrada": RED, "bloqueada": AMB, "ociosa": "#CBD5E1"}
st.set_page_config(page_title="Linha de Produção · Digital Twin", page_icon=str(Path(__file__).parent / "icone.png"), layout="wide")
ui.aplicar()
st.markdown("""<style>
.flow { display:flex; gap:8px; align-items:stretch; flex-wrap:wrap; margin:6px 0 10px; }
.flow .st { border-radius:12px; padding:10px 14px; min-width:120px; color:#1E293B; background:#F1F7F6; border:1px solid #D5E8E5; }
.flow .st.gar { background:#0B2E2B; border-color:#0B2E2B; color:#fff; }
.flow .st small { display:block; opacity:.8; font-variant-numeric: tabular-nums; }
.flow .st b { font-size:1.02rem; }
.flow i { color:#94A3B8; font-style:normal; font-size:1.2rem; align-self:center; }
.flow .q { align-self:center; color:#B45309; font-size:.8rem; font-weight:600; font-variant-numeric: tabular-nums; }
</style>""", unsafe_allow_html=True)

ui.hero("Simulação de eventos discretos · gêmeo digital",
        "Linha de Produção",
        "Uma linha de confecção simulada peça por peça, com tempo de ciclo que varia, máquina que quebra e estoque "
        "limitado entre as estações. Você muda a fábrica na tabela e vê onde a produção trava, onde vale comprar a "
        "próxima máquina e quanto a variação do processo custa.",
        [("estações", "5"), ("gargalo", "Corte"), ("produção", "49,9 peças/h"), ("erro vs. teoria", "1,5%")],
        "Caio Gadotti · Projeto pessoal",
        origem='Nasceu da minha rotina na Descartee, onde desenvolvo os sistemas internos de controle de produção de uma fábrica de descartáveis em TNT. A linha de exemplo (desbobinar, corte, costura, dobra, embalagem) segue esse processo. A simulação e a estatística vêm do que estudo em Engenharia de Sistemas Ciberfísicos na PUC-SP.',
        links=[("Código no GitHub", "https://github.com/caiogadotti/linha-producao-digital-twin"),
               ("Como funciona (README)", "https://github.com/caiogadotti/linha-producao-digital-twin#readme")])
ui.escopo(
    "Numa linha em série, a estação mais lenta limita todas as outras. A conta de bolso (máquinas × 60 ÷ ciclo × "
    "disponibilidade) acha esse gargalo quando tudo é fixo, mas erra quando o tempo de ciclo varia, as máquinas "
    "quebram e o estoque entre estações é limitado. Aí a linha produz menos que o gargalo permitiria e às vezes o "
    "gargalo muda de lugar. Sem fórmula fechada para esse caso, o caminho é simular.",
    ["Linha em série com quantas estações quiser, cada uma com várias máquinas iguais",
     "Tempo de ciclo lognormal (média e coeficiente de variação)",
     "Quebras com tempo entre falhas e de reparo exponenciais",
     "Buffer finito com bloqueio: peça pronta sem vaga fica presa na máquina",
     "Replicações com intervalo de confiança de 95% e descarte de aquecimento",
     "Validação contra as filas M/M/1 e M/M/c e a Lei de Little"],
    ["Mix de produtos e tempo de troca (setup) entre eles",
     "Turnos, pausas e operadores como recurso",
     "Retrabalho e refugo",
     "Roteiros que não sejam em série (desvios, montagem)",
     "Dados reais da fábrica: os parâmetros são ilustrativos"])


def layout(fig, h=360, **kw):
    fig.update_layout(height=h, **kw)
    return fig


# ---------------------------------------------------------------- configuração
with st.sidebar:
    st.markdown("### A simulação")
    horas = st.slider("Horas simuladas por replicação", 8, 160, 40, 8,
                      help="Duração de cada rodada, sem contar as 4 h de aquecimento. Mais horas = resultado mais estável e mais lento.")
    reps = st.slider("Replicações (sementes diferentes)", 2, 20, 6,
                     help="Quantas vezes a mesma fábrica é simulada com sorteios diferentes. É daí que sai o intervalo de confiança.")
    semente = st.number_input("Semente inicial", 0, 9999, 0, help="Muda os sorteios. Mesma semente, mesmo resultado.")
    st.caption("Cada replicação descarta 4 h de aquecimento, para a linha começar cheia. "
               "Os números vêm com intervalo de confiança de 95% entre replicações.")
    st.divider()
    st.markdown("""**Como funciona**

Cada peça passa pelas estações em ordem. Uma estação tem uma ou mais máquinas, tempo de ciclo
aleatório (lognormal), quebras (tempo entre falhas exponencial) e um buffer de entrada.

Se o buffer seguinte está cheio, a peça pronta fica presa na máquina: ela fica **bloqueada**.
Se não chega peça, fica **ociosa**.""")
    st.divider()
    st.markdown("**Caio Gadotti** · Projeto pessoal")

COLS = {"nome": "Estação", "maquinas": "Máquinas", "tempo_medio": "Ciclo (min)", "cv": "Variação (CV)",
        "mtbf": "MTBF (min)", "mttr": "MTTR (min)", "buffer": "Buffer entrada"}

if "linha" not in st.session_state:
    st.session_state.linha = pd.DataFrame([{k: getattr(e, k) for k in COLS} for e in m.LINHA_PADRAO]).rename(columns=COLS)

ui.eyebrow("A fábrica")
lead("Edite a tabela: adicione ou remova estações, troque tempos, máquinas e buffers. Todas as abas usam esta "
     "linha. MTBF = 0 quer dizer máquina que não quebra. A primeira estação nunca fica sem matéria-prima, por isso o "
     "buffer dela não conta.")
df = st.data_editor(
    st.session_state.linha, num_rows="dynamic", width="stretch", hide_index=True, key="editor",
    column_config={
        "Estação": st.column_config.TextColumn(help="Nome da etapa do processo"),
        "Máquinas": st.column_config.NumberColumn(min_value=1, max_value=10, step=1, help="Máquinas iguais trabalhando em paralelo nesta estação"),
        "Ciclo (min)": st.column_config.NumberColumn(min_value=0.05, max_value=60.0, step=0.05, format="%.2f",
                                                     help="Tempo médio que uma máquina leva para fazer uma peça"),
        "Variação (CV)": st.column_config.NumberColumn(min_value=0.0, max_value=2.0, step=0.05, format="%.2f",
                                                       help="Desvio-padrão / média do tempo de ciclo"),
        "MTBF (min)": st.column_config.NumberColumn(min_value=0.0, step=10.0, help="Tempo médio de operação entre quebras"),
        "MTTR (min)": st.column_config.NumberColumn(min_value=0.0, step=1.0, help="Tempo médio de reparo"),
        "Buffer entrada": st.column_config.NumberColumn(min_value=0, max_value=200, step=1,
                                                         help="Vagas de estoque antes da estação. Cheio, a estação anterior trava com a peça pronta"),
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

tabs = st.tabs([":material/sports_esports: Brinque", ":material/dashboard: Visão geral", ":material/target: Gargalo e cenários",
                ":material/inventory_2: Buffers", ":material/casino: Variabilidade", ":material/verified: Validação"], on_change="rerun", key="aba")

# ---------------------------------------------------------------- brinque
with tabs[0]:
    if tabs[0].open:
        st.markdown("### A fábrica rodando na sua frente")
        lead("Simulação ao vivo no seu navegador, com a mesma lógica do modelo (tempos lognormais, quebras exponenciais, "
             "bloqueio por buffer cheio). Começa com a linha da tabela acima. As outras abas rodam a simulação completa "
             "com várias replicações e medem os resultados com intervalo de confiança.")
        dados = {"estacoes": [{"nome": e.nome, "maquinas": e.maquinas, "tempo": e.tempo_medio, "cv": e.cv, "mtbf": e.mtbf,
                               "mttr": e.mttr, "buffer": e.buffer} for e in estacoes],
                 "cap_gargalo": cap_g}
        html = (Path(__file__).parent / "brinque.html").read_text(encoding="utf-8").replace("__DADOS__", json.dumps(dados))
        ui.roteiro([
            ("Ache o gargalo",
             "deixe a fábrica rodar até o gráfico passar de 1 hora.",
             "o <b>Corte</b> fica marcado como gargalo. As máquinas antes dele ficam amarelas (peça pronta sem vaga) e as depois, cinza (esperando peça).",
             "É assim que se acha o gargalo olhando o chão de fábrica, sem planilha."),
            ("Compre uma máquina",
             "clique em <b>+</b> nas máquinas do Corte.",
             "a produção sobe e, depois de alguns minutos, o gargalo passa para outra estação.",
             "Reforçar o gargalo não acaba com ele: o limite muda de lugar."),
            ("Quebre uma máquina",
             "clique na máquina do Corte para quebrá-la e conserte depois de alguns segundos. Repita com o buffer antes da Costura em 0.",
             "com buffer, a Costura continua trabalhando com as peças da fila; sem buffer, para na hora.",
             "Estoque entre estações compra tempo quando algo quebra, ao custo de mais peças paradas."),
        ])
        st.iframe(html, height=580)
        como_ler([
            ("Anel da máquina", "% do ciclo", "Quanto da peça atual já foi feito."),
            ("Cor da máquina", "estado", "Verde trabalhando, amarelo bloqueada (peça pronta sem vaga à frente), cinza ociosa (sem peça), vermelho quebrada."),
            ("Quadradinhos laranja", "peças", "Peças esperando no buffer. Tracejado é vaga livre."),
            ("Produção (última hora)", "peças/h", "Peças que saíram da última estação na última hora simulada."),
            ("Peças em processo", "peças", "Tudo que já entrou e ainda não saiu: nos buffers e dentro das máquinas."),
            ("Gargalo agora", "estação", "A estação que passou mais tempo ocupada (trabalhando ou quebrada) nos últimos minutos."),
            ("Velocidade", "min por s", "Minutos de fábrica a cada segundo real."),
        ])

# ---------------------------------------------------------------- visão geral
with tabs[1]:
    if tabs[1].open:
        c = st.columns(4)
        c[0].metric("Produção (peças/h)", f"{thr:.1f}", f"± {thr_h:.1f}", delta_color="off", delta_arrow="off",
                    help="Throughput: peças que saem da última estação por hora. O ± é o intervalo de confiança de 95% entre replicações.")
        c[1].metric("Lead time médio (min)", f"{lt:.1f}", f"± {lt_h:.1f}", delta_color="off", delta_arrow="off",
                    help="Tempo de atravessamento: da peça entrar na primeira estação até sair da última, contando as filas.")
        c[2].metric("Peças em processo (WIP)", f"{wip:.1f}", f"± {wip_h:.1f}", delta_color="off", delta_arrow="off",
                    help="Work in process: média de peças dentro da linha (em máquinas e buffers) ao longo do tempo.")
        c[3].metric("Eficiência do gargalo", f"{100 * thr / cap_g:.0f}%",
                    f"limite {cap_g:.1f} peças/h", delta_color="off", delta_arrow="off",
                    help="Produção dividida pela capacidade efetiva da estação mais lenta. Abaixo de 100% é produção perdida para variação, quebras e buffers.")

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
            ui.eyebrow("Onde cada estação gasta o tempo")
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

        como_ler([
            ("Produção (throughput)", "peças/h", "Peças acabadas por hora, medidas depois do aquecimento."),
            ("Intervalo de confiança", "± valor", "Com 95% de confiança, o valor real da média está dentro desse ±. Mais replicações estreitam a faixa."),
            ("Lead time", "min", "Tempo que uma peça leva do início ao fim da linha. Mediana e P95 (95% das peças levam menos que isso) aparecem no histograma."),
            ("WIP", "peças", "Estoque em processo. Lei de Little: WIP = produção × lead time."),
            ("Capacidade efetiva", "peças/h", "Máquinas × 60 ÷ ciclo × disponibilidade, onde disponibilidade = MTBF ÷ (MTBF + MTTR)."),
            ("Trabalhando", "% do tempo", "Máquina processando uma peça."),
            ("Quebrada", "% do tempo", "Máquina parada em reparo."),
            ("Bloqueada", "% do tempo", "Peça pronta, mas o buffer da frente está cheio. Típico de estações antes do gargalo."),
            ("Ociosa", "% do tempo", "Sem peça para trabalhar. Típico de estações depois do gargalo."),
            ("fila x/y", "peças/vagas", "Média de peças no buffer de entrada e o total de vagas."),
        ])

# ---------------------------------------------------------------- gargalo
with tabs[2]:
    if tabs[2].open:
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
        como_ler([
            ("Capacidade bruta", "peças/h", "Máquinas × 60 ÷ tempo de ciclo, como se nada quebrasse."),
            ("Disponibilidade", "%", "Fração do tempo em que a máquina não está quebrada: MTBF ÷ (MTBF + MTTR)."),
            ("Capacidade efetiva", "peças/h", "Capacidade bruta × disponibilidade. A menor delas é o gargalo pela conta de bolso."),
            ("Produção com +1 máquina", "peças/h", "Produção simulada da linha inteira se aquela estação ganhasse mais uma máquina."),
            ("Ganho", "peças/h", "Diferença para a linha atual. Valores perto de zero (ou levemente negativos) são ruído da simulação."),
        ])

# ---------------------------------------------------------------- buffers
with tabs[3]:
    if tabs[3].open:
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
            alvo = c1.selectbox("Buffer na entrada de", opcoes, index=max(g_sim - 1, 0) if g_sim > 0 else 0,
                                help="O buffer que vai variar. Os outros ficam como estão na tabela.")
            maxb = c2.slider("Até quantas vagas", 5, 60, 30, 5, help="Tamanho máximo testado; a curva usa 11 pontos de 0 até aqui.")
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
            como_ler([
                ("Vagas no buffer", "peças", "Quantas peças cabem esperando antes da estação escolhida."),
                ("Produção", "peças/h ± IC 95%", "Linha verde. Sobe com o buffer porque uma quebra deixa de parar a vizinha na hora."),
                ("Lead time", "min", "Linha pontilhada. Sobe porque cada peça a mais na fila é tempo a mais de espera."),
                ("90% do ganho", "vagas", "Menor buffer que entrega 90% da subida total da produção. A partir daí cada vaga rende pouco."),
            ])

# ---------------------------------------------------------------- variabilidade
with tabs[4]:
    if tabs[4].open:
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
        como_ler([
            ("CV", "desvio-padrão ÷ média", "Coeficiente de variação do tempo de ciclo. CV 0 = toda peça leva o mesmo tempo; CV 1 = o desvio é do tamanho da média."),
            ("Buffers atuais", "linha verde", "Produção com os buffers da tabela."),
            ("Sem buffer", "linha vermelha", "Mesma linha com uma vaga só entre estações: qualquer atraso trava a vizinha."),
            ("Capacidade do gargalo", "peças/h", "Teto teórico. A distância até ele é a produção perdida para a variação."),
        ])

# ---------------------------------------------------------------- validação
with tabs[5]:
    if tabs[5].open:
        st.markdown("### O simulador acerta onde existe resposta exata?")
        st.markdown('<div class="box">Uma linha inteira não tem fórmula fechada, por isso se simula. Mas casos '
                    'particulares têm: uma estação com chegadas de Poisson e tempo exponencial é a fila '
                    '<b>M/M/1</b>, e com c máquinas é a <b>M/M/c</b> (Erlang C). Se o simulador bate com elas, '
                    'dá para confiar nele quando não há fórmula.</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c = c1.slider("Máquinas (c)", 1, 4, 1, help="1 = fila M/M/1; mais de 1 = fila M/M/c, calculada pela fórmula de Erlang C.")
        mu = 1 / c2.slider("Tempo médio de atendimento (min)", 0.5, 3.0, 1.0, 0.25, help="1/μ: tempo médio que uma máquina leva por peça.")
        rhos = np.round(np.arange(0.3, 0.95, 0.1), 2)
        hv = c3.slider("Horas por replicação", 50, 400, 200, 50, help="Filas perto de ρ = 1 demoram para estabilizar; mais horas reduzem o erro.")

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
        como_ler([
            ("λ (lambda)", "peças/min", "Taxa de chegada: quantas peças chegam por minuto, em média."),
            ("μ (mi)", "peças/min", "Taxa de atendimento de uma máquina: 1 ÷ tempo médio de atendimento."),
            ("ρ (rô)", "λ ÷ (c·μ)", "Ocupação. Perto de 1 a fila explode; acima de 1 ela cresce sem parar."),
            ("W", "min", "Tempo médio no sistema (fila + atendimento)."),
            ("L", "peças", "Número médio de peças no sistema."),
            ("Lei de Little", "L = λ·W", "Vale para qualquer sistema estável. Serve de conferência independente da simulação."),
            ("erro W", "%", "Diferença entre o W simulado e o da fórmula."),
        ])
