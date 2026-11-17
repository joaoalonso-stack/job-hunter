import json
import os
import time
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook

import db
import notify
import preferencias
import run
from saidas import dados, pagina, planilha, status_import
from sources.base import Job

PREFS = preferencias.carregar()
HOJE = date.today().isoformat()


def _d(dias):
    return (date.today() + timedelta(days=dias)).isoformat()


@pytest.fixture
def base(tmp_path):
    conn = db.conectar(tmp_path / "s.db")
    jobs = [Job(id="a", fonte="Gupy", titulo="Economista Jr", empresa="Banco A", local="Rio de Janeiro, RJ",
                url="https://a", prazo=_d(2), descricao="x" * 1200),
            Job(id="b", fonte="LinkedIn", titulo="Analista de Fundos", empresa="Asset B", local="São Paulo, SP",
                url="https://b", prazo=_d(-1)),                                    # prazo vencido
            Job(id="c", fonte="Gupy", titulo="Analista de Crédito Jr", empresa="Banco C", local="São Paulo, SP",
                url="https://c"),
            Job(id="d", fonte="Gupy", titulo="</script><b>XSS</b>", empresa="E", local="Remoto", url="https://d")]
    db.upsert_vagas(conn, jobs)
    for j in jobs:
        db.atualizar_pipeline(conn, j.id, filtro_ok=1, rodada=HOJE, score_pre=50)
    conn.commit()
    db.salvar_triagens(conn, [{"id": "a", "nota": 88, "nota_base": 88, "trilha": "macro_research", "encaixe": "ótimo",
                               "falta": ["CPA-20"], "red_flags": []},
                              {"id": "c", "nota": 40, "nota_base": 50, "trilha": "credito_risco"}])
    db.salvar_status(conn, "c", status="descartei")
    (tmp_path / f"vagas_{HOJE}.jsonl").write_text('{"id": "a"}\n{"id": "c"}\n', "utf-8")
    return conn, tmp_path


def test_abas(base):
    conn, tmp = base
    L = {l["id"]: l for l in dados.linhas(conn, PREFS, HOJE, data_dir=tmp)}
    assert L["a"]["hoje"] and L["a"]["aba"] == "ativa" and L["a"]["urgente_prazo"]
    assert L["b"]["aba"] == "arquivada", "prazo vencido arquiva"
    assert L["c"]["aba"] == "arquivada", "descartada por você arquiva"
    assert L["a"]["falta"] == ["CPA-20"] and len(L["a"]["descricao"]) == 900
    assert [l["id"] for l in dados.linhas(conn, PREFS, HOJE, data_dir=tmp)][0] == "a", "maior nota primeiro"


def test_pagina_offline_e_segura(base):
    conn, tmp = base
    arq = pagina.gerar(dados.linhas(conn, PREFS, HOJE, data_dir=tmp), PREFS, tmp / "r" / "vagas.html", HOJE)
    html = arq.read_text("utf-8")
    assert "http://" not in html.split("<script id=\"dados\"")[0] and "cdn" not in html.lower()
    bloco = html.split('<script id="dados" type="application/json">')[1].split("</script>")[0]
    dados_json = json.loads(bloco.replace("<\\/", "</"))
    assert {v["id"] for v in dados_json["vagas"]} == {"a", "b", "c", "d"}
    assert "</script><b>" not in bloco, "título com </script> não pode quebrar a página"


def test_planilha_gera_abas_links_e_preserva_edicoes(base):
    conn, tmp = base
    destino = tmp / "r" / "vagas.xlsx"
    linhas = dados.linhas(conn, PREFS, HOJE, data_dir=tmp)
    planilha.gerar(conn, linhas, PREFS, destino, HOJE)
    wb = load_workbook(destino)
    assert wb.sheetnames == ["Hoje", "Ativas", "Candidaturas", "Resumo"]
    ws = wb["Hoje"]
    cab = [c.value for c in ws[1]]
    i_link, i_id, i_st, i_obs = (cab.index(x) + 1 for x in ("Link", "ID", "Status", "Observações"))
    linha_a = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, i_id).value == "a")
    assert ws.cell(linha_a, i_link).hyperlink.target == "https://a"
    assert ws.freeze_panes == "C2" and ws.auto_filter.ref
    assert (tmp / "r" / "historico" / f"vagas_{HOJE}.xlsx").exists()
    # você edita a planilha...
    ws.cell(linha_a, i_st).value = "apliquei"
    ws.cell(linha_a, i_obs).value = "mandei carta"
    wb.save(destino)
    os.utime(destino, (time.time() + 5, time.time() + 5))
    # ...e a próxima rodada lê as edições antes de regerar
    assert planilha.importar_edicoes(conn, destino, dados.linhas(conn, PREFS, HOJE, data_dir=tmp)) == 1
    s = conn.execute("SELECT status, observacoes FROM status WHERE vaga_id='a'").fetchone()
    assert (s["status"], s["observacoes"]) == ("apliquei", "mandei carta")
    planilha.gerar(conn, dados.linhas(conn, PREFS, HOJE, data_dir=tmp), PREFS, destino, HOJE)
    wb = load_workbook(destino)
    assert "a" in [c.value for c in wb["Candidaturas"]["Q"]], "candidatura aparece na aba Candidaturas"


def test_status_exportado_pela_pagina_entra_no_banco(base, tmp_path):
    conn, _ = base
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "status_vagas_2026-11-13.json").write_text(
        json.dumps([{"id": "b", "status": "interessado", "quando": "2099-01-01T00:00:00"},
                    {"id": "a", "status": "invalido", "quando": "2099-01-01T00:00:00"}]), "utf-8")
    n = status_import.importar(conn, pastas=[downloads], destino=tmp_path / "importados")
    assert n == 1 and not list(downloads.glob("*.json"))
    assert conn.execute("SELECT status FROM status WHERE vaga_id='b'").fetchone()[0] == "interessado"


def test_edicao_mais_antiga_nao_sobrescreve():
    conn = db.conectar(":memory:")
    db.salvar_status(conn, "x", status="apliquei", quando="2026-11-13T12:00:00")
    assert db.salvar_status(conn, "x", status="interessado", quando="2026-11-13T09:00:00") is False
    assert conn.execute("SELECT status FROM status").fetchone()[0] == "apliquei"


def test_aviso_top_do_dia_sem_repetir(base, monkeypatch):
    conn, tmp = base
    monkeypatch.setattr(dados, "BASE", tmp.parent)
    monkeypatch.setattr(dados, "ids_de_hoje", lambda hoje, data_dir=None: ["a", "c"])
    enviados = []
    monkeypatch.setattr(notify, "enviar", lambda msg: enviados.append(msg))
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    run.avisar_top(conn, PREFS, HOJE)
    assert [m["click"] for m in enviados] == ["https://a"], "a vaga 'c' foi descartada por você: não vai ao celular"
    assert enviados[0]["title"].startswith("[88]") and enviados[0]["priority"] == 5
    run.avisar_top(conn, PREFS, HOJE)
    assert len(enviados) == 1, "não reenvia o mesmo top no mesmo dia"


def test_aviso_top_ignora_nota_baixa(base, monkeypatch):
    conn, tmp = base
    db.salvar_triagens(conn, [{"id": "d", "nota": 1, "nota_base": 5, "trilha": "outro"}])
    monkeypatch.setattr(dados, "ids_de_hoje", lambda hoje, data_dir=None: ["a", "d"])
    enviados = []
    monkeypatch.setattr(notify, "enviar", lambda msg: enviados.append(msg))
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    run.avisar_top(conn, PREFS, HOJE)
    assert [m["click"] for m in enviados] == ["https://a"], "nota 1 fica só na página, não vai ao celular"


def test_sem_triagem_nao_avisa(base, monkeypatch):
    conn, tmp = base
    conn.execute("DELETE FROM triagens")  # a triagem do dia falhou
    monkeypatch.setattr(dados, "ids_de_hoje", lambda hoje, data_dir=None: ["a", "d"])
    enviados = []
    monkeypatch.setattr(notify, "enviar", lambda msg: enviados.append(msg))
    assert run.avisar_top(conn, PREFS, HOJE).startswith("0 alertas") and not enviados
