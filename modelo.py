"""Simulação de eventos discretos de uma linha de produção em série (SimPy).

Cada estação tem k máquinas idênticas, tempo de ciclo aleatório, quebras e um
buffer finito na entrada. Peça que termina e não encontra vaga no buffer seguinte
fica parada na máquina (bloqueio após o serviço), como numa linha real.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import factorial

import numpy as np
import simpy
from scipy import stats

ESTADOS = ("trabalhando", "quebrada", "bloqueada", "ociosa")


@dataclass
class Estacao:
    nome: str
    tempo_medio: float          # min por peça
    cv: float = 0.3             # coeficiente de variação do tempo de ciclo
    maquinas: int = 1
    mtbf: float = 0.0           # min de operação entre quebras (0 = não quebra)
    mttr: float = 0.0           # min médios de reparo
    buffer: int = 10            # vagas na fila de entrada (ignorado na 1ª estação)
    distribuicao: str = "lognormal"  # "lognormal" | "exponencial" | "fixo"

    @property
    def capacidade_bruta(self) -> float:
        """Peças/h sem quebras nem perdas de fluxo."""
        return 60.0 * self.maquinas / self.tempo_medio

    @property
    def disponibilidade(self) -> float:
        if self.mtbf <= 0:
            return 1.0
        return self.mtbf / (self.mtbf + self.mttr)

    @property
    def capacidade_efetiva(self) -> float:
        return self.capacidade_bruta * self.disponibilidade


@dataclass
class Resultado:
    horizonte: float
    pecas: int
    throughput_h: float
    lead_time_medio: float
    lead_times: np.ndarray
    wip_medio: float
    wip_serie: np.ndarray        # (tempo, wip)
    estados: dict                # nome -> {estado: fração}
    fila_media: dict             # nome -> peças médias no buffer
    saidas: np.ndarray = field(default_factory=lambda: np.array([]))


def _sorteia_tempo(rng: np.random.Generator, media: float, cv: float, dist: str) -> float:
    if dist == "fixo" or cv <= 0:
        return media
    if dist == "exponencial":
        return rng.exponential(media)
    sigma2 = np.log(1 + cv * cv)
    return rng.lognormal(np.log(media) - sigma2 / 2, np.sqrt(sigma2))


class _Relogio:
    """Acumula tempo por estado de uma máquina, só depois do aquecimento."""

    def __init__(self, aquecimento: float):
        self.aq = aquecimento
        self.t = {e: 0.0 for e in ESTADOS}
        self.estado, self.desde = "ociosa", 0.0

    def entra(self, estado: str, agora: float):
        ini = max(self.desde, self.aq)
        if agora > ini:
            self.t[self.estado] += agora - ini
        self.estado, self.desde = estado, agora


def simular(estacoes: list[Estacao], horas: float = 40.0, aquecimento_h: float = 4.0,
            semente: int = 0, chegada_media: float | None = None) -> Resultado:
    """Roda uma replicação.

    chegada_media=None: linha saturada (sempre há matéria-prima na 1ª estação).
    chegada_media=x: chegadas de Poisson com intervalo médio x min, fila infinita na entrada.
    """
    rng = np.random.default_rng(semente)
    env = simpy.Environment()
    aq = aquecimento_h * 60.0
    fim = aq + horas * 60.0

    n = len(estacoes)
    # buffer 0 vira 1 vaga de passagem: SimPy não aceita Store de capacidade zero
    filas = [simpy.Store(env) if i == 0 else simpy.Store(env, capacity=max(est.buffer, 1))
             for i, est in enumerate(estacoes)]
    saida = simpy.Store(env)
    relogios = [[_Relogio(aq) for _ in range(e.maquinas)] for e in estacoes]
    area_fila = [0.0] * n
    ultimo_fila = [aq] * n
    tam_fila = [0] * n
    wip = {"n": 0, "area": 0.0, "t": aq}
    serie: list[tuple[float, int]] = []
    lead: list[float] = []
    saidas: list[float] = []

    def marca_wip(delta: int):
        t = env.now
        if t > aq:
            wip["area"] += wip["n"] * (t - max(wip["t"], aq))
        wip["t"] = t
        wip["n"] += delta
        serie.append((t / 60.0, wip["n"]))

    def marca_fila(i: int, delta: int):
        t = env.now
        if t > aq:
            area_fila[i] += tam_fila[i] * (t - max(ultimo_fila[i], aq))
        ultimo_fila[i] = t
        tam_fila[i] += delta

    def nova_peca():
        marca_wip(+1)
        return {"entrada": env.now}

    def chegadas():
        while True:
            yield env.timeout(rng.exponential(chegada_media))
            marca_fila(0, +1)
            yield filas[0].put(nova_peca())

    def maquina(i: int, j: int):
        est = estacoes[i]
        rel = relogios[i][j]
        ate_quebra = rng.exponential(est.mtbf) if est.mtbf > 0 else np.inf
        while True:
            rel.entra("ociosa", env.now)
            if i == 0 and chegada_media is None:
                peca = nova_peca()
            else:
                peca = yield filas[i].get()
                marca_fila(i, -1)

            falta = _sorteia_tempo(rng, est.tempo_medio, est.cv, est.distribuicao)
            while falta > 0:
                rel.entra("trabalhando", env.now)
                passo = min(falta, ate_quebra)
                yield env.timeout(passo)
                falta -= passo
                ate_quebra -= passo
                if ate_quebra <= 0:
                    rel.entra("quebrada", env.now)
                    yield env.timeout(rng.exponential(est.mttr))
                    ate_quebra = rng.exponential(est.mtbf)

            rel.entra("bloqueada", env.now)
            if i + 1 < n:
                yield filas[i + 1].put(peca)
                marca_fila(i + 1, +1)
            else:
                yield saida.put(peca)
                marca_wip(-1)
                if env.now >= aq:
                    lead.append(env.now - peca["entrada"])
                    saidas.append(env.now / 60.0)

    if chegada_media is not None:
        env.process(chegadas())
    for i, est in enumerate(estacoes):
        for j in range(est.maquinas):
            env.process(maquina(i, j))
    env.run(until=fim)

    marca_wip(0)
    for i in range(n):
        marca_fila(i, 0)
    total = fim - aq
    estados = {}
    for i, est in enumerate(estacoes):
        for r in relogios[i]:
            r.entra(r.estado, fim)
        cap = total * est.maquinas
        estados[est.nome] = {e: sum(r.t[e] for r in relogios[i]) / cap for e in ESTADOS}

    lt = np.array(lead)
    return Resultado(
        horizonte=horas,
        pecas=len(lt),
        throughput_h=len(lt) / horas,
        lead_time_medio=float(lt.mean()) if len(lt) else float("nan"),
        lead_times=lt,
        wip_medio=wip["area"] / total,
        wip_serie=np.array(serie) if serie else np.zeros((0, 2)),
        estados=estados,
        fila_media={est.nome: area_fila[i] / total for i, est in enumerate(estacoes)},
        saidas=np.array(saidas),
    )


def intervalo(valores, conf: float = 0.95) -> tuple[float, float]:
    """Média e meia-largura do IC t-Student entre replicações."""
    v = np.asarray(valores, dtype=float)
    if len(v) < 2:
        return float(v.mean()), 0.0
    h = stats.t.ppf((1 + conf) / 2, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v))
    return float(v.mean()), float(h)


def replicar(estacoes, reps: int = 5, semente: int = 0, **kw) -> list[Resultado]:
    return [simular(estacoes, semente=semente + r, **kw) for r in range(reps)]


def gargalo(estacoes: list[Estacao]) -> int:
    """Estação de menor capacidade efetiva (análise estática, antes de simular)."""
    return int(np.argmin([e.capacidade_efetiva for e in estacoes]))


def mm1_teorico(lam: float, mu: float) -> dict:
    """Fila M/M/1 (taxas por minuto): L, W, Lq, Wq."""
    rho = lam / mu
    return {"rho": rho, "L": rho / (1 - rho), "W": 1 / (mu - lam),
            "Lq": rho * rho / (1 - rho), "Wq": rho / (mu - lam)}


def mmc_teorico(lam: float, mu: float, c: int) -> dict:
    """Fila M/M/c via fórmula de Erlang C."""
    a = lam / mu
    rho = a / c
    soma = sum(a ** k / factorial(k) for k in range(c))
    ultimo = a ** c / (factorial(c) * (1 - rho))
    p_espera = ultimo / (soma + ultimo)
    wq = p_espera / (c * mu - lam)
    return {"rho": rho, "P_espera": p_espera, "Wq": wq, "W": wq + 1 / mu, "Lq": lam * wq, "L": lam * (wq + 1 / mu)}


LINHA_PADRAO = [
    Estacao("Desbobinar", tempo_medio=0.9, cv=0.2, maquinas=1, mtbf=480, mttr=15, buffer=0),
    Estacao("Corte", tempo_medio=1.1, cv=0.35, maquinas=1, mtbf=300, mttr=20, buffer=8),
    Estacao("Costura", tempo_medio=2.0, cv=0.5, maquinas=2, mtbf=600, mttr=25, buffer=8),
    Estacao("Dobra", tempo_medio=0.8, cv=0.3, maquinas=1, mtbf=0, mttr=0, buffer=6),
    Estacao("Embalagem", tempo_medio=0.7, cv=0.25, maquinas=1, mtbf=900, mttr=10, buffer=6),
]
