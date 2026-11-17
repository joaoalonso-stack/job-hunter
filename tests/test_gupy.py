import json
import urllib.parse
from datetime import date, timedelta

import pytest

from sources import gupy
from sources.base import Bloqueado


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(gupy.time, "sleep", lambda s: None)


def test_parse_api_fixture_real(fixture_txt):
    jobs, total = gupy.parse_api(fixture_txt("gupy_api.json"))
    assert jobs and total >= len(jobs)
    for j in jobs:
        assert j.id.startswith("gupy:") and j.fonte == "Gupy" and j.titulo
        assert j.url.startswith("https://") and "?" not in j.url
        assert len(j.publicada) == 10 and j.descricao
    assert any(j.senioridade == "trainee" for j in jobs), "o tipo da Gupy indica trainee"


def test_remotas_sem_cidade_viram_remoto(fixture_txt):
    jobs, _ = gupy.parse_api(fixture_txt("gupy_api_remoto.json"))
    assert jobs and all(j.modalidade == "remoto" and j.local == "Remoto" for j in jobs)


def test_tipo_pj_vira_sinal():
    j = gupy.para_job({"id": 1, "name": "Analista", "type": "vacancy_legal_entity", "workplaceType": "hybrid",
                       "city": "Rio de Janeiro", "state": "Rio de Janeiro", "jobUrl": "https://x.gupy.io/job/1?a=b"})
    assert j.senioridade == "PJ" and j.modalidade == "hibrido" and j.local == "Rio de Janeiro, Rio de Janeiro"
    assert j.url == "https://x.gupy.io/job/1"


def test_nome_da_empresa_pela_pagina(fixture_txt):
    html = fixture_txt("gupy_empresa.html")
    assert gupy.nome_da_empresa("bancodaycoval", buscar=lambda url, **kw: html) == "BANCO DAYCOVAL"


def _api_falsa(vagas, chamadas):
    """Simula a API: filtra por jobName/careerPageName/workplaceType e pagina por limit/offset."""
    def buscar(url, **kw):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        chamadas.append(q)
        sel = [v for v in vagas
               if q.get("jobName", "") in v["name"].lower()
               and q.get("careerPageName", v["careerPageName"]) == v["careerPageName"]
               and q.get("workplaceType", v["workplaceType"]) == v["workplaceType"]]
        sel.sort(key=lambda v: v["publishedDate"], reverse=True)
        ini, lim = int(q["offset"]), int(q["limit"])
        return json.dumps({"data": sel[ini:ini + lim], "pagination": {"total": len(sel)}})
    return buscar


def _vaga(i, dias_atras, nome="analista de fundos", empresa="BANCO X", modalidade="on-site"):
    return {"id": i, "name": nome, "careerPageName": empresa, "workplaceType": modalidade, "city": "São Paulo",
            "state": "São Paulo", "publishedDate": (date.today() - timedelta(days=dias_atras)).isoformat() + "T00:00",
            "jobUrl": f"https://x.gupy.io/job/{i}", "type": "vacancy_type_effective"}


def test_paginacao_para_na_janela(monkeypatch):
    monkeypatch.setattr(gupy, "LIMITE", 2)
    vagas = [_vaga(i, dias_atras=i) for i in range(10)]  # uma vaga por dia, de hoje até 9 dias atrás
    chamadas = []
    jobs = gupy.coletar(["fundos"], janela_dias=3, buscar=_api_falsa(vagas, chamadas))
    assert sorted(int(j.id.split(":")[1]) for j in jobs) == [0, 1, 2, 3]
    paginas_termo = [c for c in chamadas if "workplaceType" not in c]
    # páginas de 2: [0,1] [2,3] [4,5] — a 3ª é a primeira que passa da janela; [6,7] e [8,9] não são pedidas
    assert len(paginas_termo) == 3, "deve parar de paginar na primeira página que passa da janela"


def test_busca_remota_dedicada_e_watchlist(monkeypatch):
    vagas = [_vaga(1, 1), _vaga(2, 1, modalidade="remote"), _vaga(3, 40, nome="analista de crédito", empresa="BANCO Y")]
    html = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"careerPage":{"name":"BANCO Y"}}}}</script>'
    api = _api_falsa(vagas, [])

    def buscar(url, **kw):
        return html if url == "https://bancoy.gupy.io/" else api(url)

    jobs = {j.id: j for j in gupy.coletar(["fundos"], watchlist=["bancoy"], janela_dias=7, buscar=buscar)}
    assert set(jobs) == {"gupy:1", "gupy:2", "gupy:3"}
    assert jobs["gupy:3"].extra["watchlist"] == "bancoy", "watchlist ignora a janela de publicação"
    assert jobs["gupy:2"].modalidade == "remoto"


def test_falha_de_um_termo_nao_derruba_os_outros(capsys):
    vagas = [_vaga(1, 0, nome="economista")]
    api = _api_falsa(vagas, [])

    def buscar(url, **kw):
        if "middle" in url:
            raise Bloqueado(url)
        return api(url)

    jobs = gupy.coletar(["middle office", "economista"], buscar=buscar)
    assert [j.id for j in jobs] == ["gupy:1"]
    assert "middle office" in capsys.readouterr().out
