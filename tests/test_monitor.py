"""O monitor de 3h, já refatorado, precisa se comportar como antes: notifica cada vaga uma única vez,
deduplica entre portais e respeita --seed e --dry."""
import pytest

import db
import monitor_vagas
import notify
from sources.base import Job


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "m.db")
    monkeypatch.setattr(db, "BASE", tmp_path)
    monkeypatch.setattr(db, "LOG_PATH", tmp_path / "vagas_encontradas.md")
    enviados = []
    monkeypatch.setattr(notify, "enviar", lambda msg: enviados.append(msg))
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    vagas = {
        "publico": [Job(id="pci:1", fonte="PCI Concursos", titulo="INB Economista", empresa="Concurso público",
                        local="Nacional", url="https://pci/1", extra={"cat": "PUBLICO"})],
        "portais": [Job(id="gupy:1", fonte="Gupy", titulo="Analista de Fundos Júnior", empresa="Banco Daycoval",
                        local="São Paulo, São Paulo", url="https://gupy/1"),
                    Job(id="gupy:2", fonte="Gupy", titulo="Vendedor", empresa="Loja", local="São Paulo", url="u")],
        # mesma vaga da Gupy, vista pelo LinkedIn: não pode gerar segundo alerta
        "linkedin": [Job(id="999", fonte="LinkedIn", titulo="Analista de Fundos Júnior", empresa="Banco Daycoval",
                         local="São Paulo, SP", url="https://li/999")],
    }

    def coletor(nome, filtra=True):
        def f(aceita=lambda j: True):
            return [j for j in vagas[nome] if aceita(j)] if filtra else list(vagas[nome])
        return f

    monkeypatch.setattr(monitor_vagas.publico, "coletar", coletor("publico", filtra=False))
    monkeypatch.setattr(monitor_vagas.portais, "coletar", coletor("portais"))
    monkeypatch.setattr(monitor_vagas.linkedin_guest, "coletar", coletor("linkedin"))
    return enviados, tmp_path


def test_notifica_uma_vez_e_deduplica(ambiente):
    enviados, tmp = ambiente
    monitor_vagas.main(["x"])
    assert sorted(m["click"] for m in enviados) == ["https://gupy/1", "https://pci/1"]
    monitor_vagas.main(["x"])
    assert len(enviados) == 2, "segunda rodada não pode repetir alertas"
    assert "Analista de Fundos Júnior" in (tmp / "vagas_encontradas.md").read_text("utf-8")


def test_seed_e_dry_nao_enviam(ambiente):
    enviados, _ = ambiente
    monitor_vagas.main(["x", "--dry"])
    monitor_vagas.main(["x", "--seed"])
    monitor_vagas.main(["x"])
    assert enviados == []
