import pytest

from pipeline.filtro_legado import classifica
from sources.base import Job

CASOS = [
    ("Analista de Middle Office Jr", "BTG Pactual", "Rio de Janeiro, RJ", "JR"),
    ("Economista", "Prefeitura", "Curitiba, PR", "MACRO"),            # macro vale no Brasil todo
    ("Analista de Back Office", "Telemarketing SA", "São Paulo, SP", None),
    ("Analista de Back Office Jr", "Vinci Compass", "Rio de Janeiro, RJ", "JR"),
    ("Trainee 2027", "Ternium", "Rio de Janeiro, RJ", None),
    ("Trainee 2027", "Banco Safra", "São Paulo, SP", "JR"),
    ("Pesquisador Assistente", "FGV IBRE", "Rio de Janeiro, RJ", "OUTRAS"),
    ("Assistente de Pesquisa", "ALS Life Sciences", "São Paulo, SP", None),
    ("Analista Financeiro Jr", "Hospital X", "Rio de Janeiro, RJ", None),
    ("Analista de Economia Circular", "Braskem", "São Paulo, SP", None),
    ("Funds Administration Analyst", "UBS", "São Paulo, SP", "FIN"),
    ("MIDDLE INTRAG | ANL SV MERC CAPIT", "Itaú Unibanco", "São Paulo, SP", "FIN"),
    ("Analista de Risco de Crédito II", "Voltz", "Rio de Janeiro, RJ", None),
    ("Asssessor de Investimentos", "XP", "Rio de Janeiro, RJ", None),
    ("Analista de Fundos Júnior", "Daycoval", "Curitiba, PR", None),   # fora de RJ/SP/remoto
]


@pytest.mark.parametrize("titulo,empresa,local,esperado", CASOS)
def test_classifica(titulo, empresa, local, esperado):
    assert classifica(Job(id="x", fonte="t", titulo=titulo, empresa=empresa, local=local)) == esperado


def test_publico_passa_direto():
    j = Job(id="pci:1", fonte="PCI Concursos", titulo="Concurso X", extra={"cat": "PUBLICO"})
    assert classifica(j) == "PUBLICO"
