import pytest

import preferencias


def test_yaml_real_carrega_com_todas_as_chaves():
    p = preferencias.carregar()
    assert p["execucao"]["horario"] == "08:00"
    assert p["trilhas"]["macro_research"] == 1.0 and p["trilhas"]["outro"] == 0.2
    assert {l["nome"] for l in p["locais"]} == {"Rio de Janeiro", "São Paulo"}
    assert "estágio" in p["excluir"] and "trainee" in p["incluir"]
    assert p["limiares"] == {"destaque": 65, "urgente": 85, "minimo_alerta": 40, "prazo_dias": 3}


def test_yaml_incompleto_da_erro_claro(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("locais: []\n", "utf-8")
    with pytest.raises(ValueError, match="trilhas"):
        preferencias.carregar(f)


def test_perfil_existe():
    texto = preferencias.PERFIL_PATH.read_text("utf-8")
    assert "BOCOM BBM" in texto and "CR 8,5" in texto
