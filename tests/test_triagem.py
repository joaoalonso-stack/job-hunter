import json
from types import SimpleNamespace

import pytest

import db
import preferencias
import triagem

PREFS = preferencias.carregar()


def test_extrair_json_do_bloco_markdown():
    assert triagem.extrair_json('ok\n```json\n[{"id": "a", "nota_base": 80}]\n```') == [{"id": "a", "nota_base": 80}]
    with pytest.raises(ValueError):
        triagem.extrair_json("sem json aqui")


def test_validar_aplica_peso_da_trilha_e_limpa_dados():
    itens = [{"id": "a", "nota_base": 90, "trilha": "macro_research", "encaixe": "x"},
             {"id": "b", "nota_base": 90, "trilha": "inteligencia_mercado_fpa"},
             {"id": "c", "nota_base": 150, "trilha": "inexistente", "falta": None},
             {"id": "intrusa", "nota_base": 99, "trilha": "macro_research"}]
    v = {t["id"]: t for t in triagem.validar(itens, {"a", "b", "c"}, PREFS)}
    assert set(v) == {"a", "b", "c"}, "ids fora do arquivo do dia são ignorados"
    assert v["a"]["nota"] == 90 and v["b"]["nota"] == round(90 * 0.65)
    assert v["c"]["nota_base"] == 100 and v["c"]["trilha"] == "outro" and v["c"]["nota"] == 20
    assert v["c"]["falta"] == []


def test_rodar_chama_claude_e_grava_no_banco(tmp_path, monkeypatch):
    monkeypatch.setattr(triagem, "BASE", tmp_path)
    monkeypatch.setattr(triagem, "claude_exe", lambda: "claude.exe")
    (tmp_path / "data").mkdir()
    jsonl = tmp_path / "data" / "vagas_2026-11-13.jsonl"
    jsonl.write_text(json.dumps({"id": "g1"}) + "\n" + json.dumps({"id": "g2"}) + "\n", "utf-8")
    conn = db.conectar(tmp_path / "t.db")
    chamadas = []

    def executar(cmd, **kw):
        chamadas.append((cmd, kw))
        resultado = '```json\n[{"id":"g1","nota_base":80,"trilha":"asset_fundos","encaixe":"bom",' \
                    '"falta":["CPA-20"],"red_flags":[]},{"id":"g2","nota_base":10,"trilha":"outro"}]\n```'
        return SimpleNamespace(returncode=0, stdout=json.dumps({"is_error": False, "result": resultado}), stderr="")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-nao-usar")
    msg = triagem.rodar(jsonl, conn=conn, executar=executar)
    cmd, kw = chamadas[0]
    assert cmd[1:3] == ["-p", "/triagem data/vagas_2026-11-13.jsonl --so-json"]
    assert "ANTHROPIC_API_KEY" not in kw["env"], "nunca usar a API paga"
    assert "2 vagas triadas" in msg and (tmp_path / "data" / "triagem_2026-11-13.json").exists()
    r = conn.execute("SELECT nota, nota_base, trilha, falta FROM triagens WHERE vaga_id='g1'").fetchone()
    assert (r["nota"], r["nota_base"], r["trilha"]) == (72, 80, "asset_fundos")
    assert json.loads(r["falta"]) == ["CPA-20"]


def test_rodar_falha_com_mensagem_clara(tmp_path, monkeypatch):
    monkeypatch.setattr(triagem, "BASE", tmp_path)
    monkeypatch.setattr(triagem, "claude_exe", lambda: "claude.exe")
    (tmp_path / "data").mkdir()
    jsonl = tmp_path / "data" / "vagas_2026-11-13.jsonl"
    jsonl.write_text('{"id": "g1"}\n', "utf-8")
    executar = lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="não autenticado")
    with pytest.raises(RuntimeError, match="não autenticado"):
        triagem.rodar(jsonl, conn=db.conectar(tmp_path / "t.db"), executar=executar)


def test_comando_triagem_existe_e_pede_rigor():
    texto = (triagem.BASE / ".claude" / "commands" / "triagem.md").read_text("utf-8")
    assert "$ARGUMENTS" in texto and "--so-json" in texto and "não infle" in texto
