import json

import db
import notify
from sources.base import Job


def _job(i, **kw):
    return Job(id=f"t:{i}", fonte="Teste", titulo=f"Analista de Fundos Jr {i}", empresa="Banco X",
               local="Rio de Janeiro, RJ", url=f"https://ex.com/{i}", extra={"cat": "JR"}, **kw)


def test_upsert_preserva_descricao_e_atualiza_ultima_vez(conn):
    db.upsert_vagas(conn, [_job(1, descricao="texto completo")])
    db.upsert_vagas(conn, [_job(1)])  # segunda aparição sem descrição
    row = conn.execute("SELECT descricao, primeira_vez, ultima_vez FROM vagas WHERE id='t:1'").fetchone()
    assert row["descricao"] == "texto completo"
    assert row["primeira_vez"] <= row["ultima_vez"]


def test_vistas(conn):
    db.marcar_vistas(conn, ["a", "b"])
    assert db.ja_vistas(conn, ["a", "c"]) == {"a"}


def test_migracao_do_legado(conn, tmp_path):
    (tmp_path / "vistas.json").write_text(json.dumps(["123", "k:abc|banco"]), "utf-8")
    (tmp_path / "fila.json").write_text(json.dumps([{"id": "x1", "cat": "JR", "titulo": "T", "empresa": "E",
                                                     "local": "L", "fonte": "F", "url": "https://u"}]), "utf-8")
    (tmp_path / "vagas_encontradas.md").write_text(
        # formato antigo (sem fonte, data vazia) e formato novo (com fonte)
        "## 16/10/2026 17:10\n- [PUBLICO] [Concurso X](https://www.pciconcursos.com.br/x) — Concurso público · RJ · \n\n"
        "## 19/10/2026 14:24\n- [JR] [Trainee Y](https://quark.gupy.io/job/1) — Quark · São Paulo, Brasil · Gupy · "
        "2026-10-19\n- [FIN] [Back Office](https://www.linkedin.com/jobs/view/4) — NAU · São Paulo · 2026-10-19\n",
        "utf-8")
    feito = db.migrar_legado(conn, tmp_path)
    assert feito == ["vistas", "fila", "historico"]
    assert db.ja_vistas(conn, ["123", "k:abc|banco"]) == {"123", "k:abc|banco"}
    assert [p["id"] for p in db.fila_listar(conn)] == ["x1"]
    fontes = {r[0] for r in conn.execute("SELECT fonte FROM vagas")}
    assert fontes == {"historico:PCI Concursos", "historico:Gupy", "historico:LinkedIn"}
    primeira = conn.execute("SELECT primeira_vez FROM vagas WHERE titulo='Concurso X'").fetchone()[0]
    assert primeira == "2026-10-16T17:10:00"
    assert not (tmp_path / "vistas.json").exists()
    assert db.migrar_legado(conn, tmp_path) == []  # idempotente


def test_montar_prioridades():
    p = notify.payload(_job(1))
    msg = notify.montar(p)
    assert msg["click"] == "https://ex.com/1" and msg["priority"] == 4 and msg["title"].startswith("[Jr]")
    assert notify.montar({**p, "cat": "MACRO"})["priority"] == 5


def test_fila_mantem_o_que_falha(conn):
    enviados = []

    def enviar(msg):
        if msg["click"].endswith("/2"):
            raise OSError("rede")
        enviados.append(msg["click"])

    n = notify.enviar_fila(conn, [notify.payload(_job(i)) for i in (1, 2, 3)], envio=enviar, pausa=0)
    assert n == 2 and len(enviados) == 2
    assert [p["id"] for p in db.fila_listar(conn)] == ["t:2"]


def test_registro_grava_em_arquivo_mesmo_sem_console(tmp_path, monkeypatch):
    import sys
    import registro
    monkeypatch.setattr(sys, "__stdout__", None)   # como no pythonw
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    arq = registro.configurar("teste", tmp_path)
    print("LinkedIn bloqueou temporariamente")
    arq.close()
    assert "LinkedIn bloqueou" in next(tmp_path.glob("teste_*.log")).read_text("utf-8")
