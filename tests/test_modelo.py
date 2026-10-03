import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelo as m  # noqa: E402


def _media(res, attr):
    return np.mean([getattr(r, attr) for r in res])


@pytest.mark.parametrize("rho", [0.5, 0.8])
def test_mm1_tempo_no_sistema_bate_com_formula(rho):
    mu = 1.0
    lam = rho * mu
    est = [m.Estacao("M/M/1", tempo_medio=1 / mu, distribuicao="exponencial")]
    res = m.replicar(est, reps=8, horas=400, aquecimento_h=20, chegada_media=1 / lam)
    teo = m.mm1_teorico(lam, mu)
    assert _media(res, "lead_time_medio") == pytest.approx(teo["W"], rel=0.08)
    assert _media(res, "wip_medio") == pytest.approx(teo["L"], rel=0.08)


def test_mmc_erlang_c():
    lam, mu, c = 2.4, 1.0, 3
    est = [m.Estacao("M/M/3", tempo_medio=1 / mu, maquinas=c, distribuicao="exponencial")]
    res = m.replicar(est, reps=8, horas=300, aquecimento_h=20, chegada_media=1 / lam)
    teo = m.mmc_teorico(lam, mu, c)
    assert _media(res, "lead_time_medio") == pytest.approx(teo["W"], rel=0.08)


def test_lei_de_little_na_linha_completa():
    r = m.simular(m.LINHA_PADRAO, horas=80, semente=3)
    lam = r.throughput_h / 60
    assert r.wip_medio == pytest.approx(lam * r.lead_time_medio, rel=0.05)


def test_fracoes_de_estado_somam_um():
    r = m.simular(m.LINHA_PADRAO, horas=20, semente=1)
    for fr in r.estados.values():
        assert sum(fr.values()) == pytest.approx(1.0, abs=1e-9)


def test_throughput_nao_passa_do_gargalo():
    caps = [e.capacidade_efetiva for e in m.LINHA_PADRAO]
    res = m.replicar(m.LINHA_PADRAO, reps=5, horas=60)
    media, h = m.intervalo([r.throughput_h for r in res])
    assert media - h <= min(caps)
    assert m.LINHA_PADRAO[m.gargalo(m.LINHA_PADRAO)].nome == "Corte"


def test_deterministica_sem_quebra_atinge_capacidade():
    est = [m.Estacao("A", 1.0, cv=0, distribuicao="fixo", buffer=2),
           m.Estacao("B", 2.0, cv=0, distribuicao="fixo", buffer=2)]
    r = m.simular(est, horas=10)
    assert r.throughput_h == pytest.approx(30, abs=0.5)


def test_mesma_semente_mesmo_resultado():
    a = m.simular(m.LINHA_PADRAO, horas=10, semente=42)
    b = m.simular(m.LINHA_PADRAO, horas=10, semente=42)
    assert a.pecas == b.pecas and a.lead_time_medio == b.lead_time_medio


def test_buffer_maior_nao_reduz_producao():
    def linha(buf):
        return [m.Estacao("A", 1.0, cv=0.8, mtbf=120, mttr=15, buffer=0),
                m.Estacao("B", 1.0, cv=0.8, mtbf=120, mttr=15, buffer=buf)]
    pequeno = _media(m.replicar(linha(1), reps=6, horas=60), "throughput_h")
    grande = _media(m.replicar(linha(30), reps=6, horas=60), "throughput_h")
    assert grande > pequeno
