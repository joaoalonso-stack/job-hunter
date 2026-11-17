from sources import linkedin_guest, portais, publico


def _basico(jobs, fonte, prefixo=""):
    assert jobs, f"{fonte}: nenhuma vaga lida da fixture"
    for j in jobs:
        assert j.fonte == fonte
        assert j.titulo.strip()
        assert j.url.startswith("http")
        assert j.id.startswith(prefixo)
    assert len({j.id for j in jobs}) == len(jobs), "ids repetidos"


def test_linkedin(fixture_txt):
    jobs = linkedin_guest.parse(fixture_txt("linkedin_search.html"))
    _basico(jobs, "LinkedIn")
    assert all(j.id.isdigit() for j in jobs), "id do LinkedIn deve ser o número puro (compatível com o legado)"
    assert all(j.url == f"https://www.linkedin.com/jobs/view/{j.id}" for j in jobs)


def test_vagascom(fixture_txt):
    _basico(portais.parse_vagascom(fixture_txt("vagascom.html")), "Vagas.com.br", "vagascom:")


def test_catho(fixture_txt):
    jobs = portais.parse_catho(fixture_txt("catho.html"))
    _basico(jobs, "Catho", "catho:")
    assert any(j.local for j in jobs)


def test_glassdoor_extrai_empresa_pelos_indices_ke(fixture_txt):
    jobs = portais.parse_glassdoor("Rio de Janeiro, RJ")(fixture_txt("glassdoor.html"))
    _basico(jobs, "Glassdoor", "glassdoor:")
    assert sum(1 for j in jobs if j.empresa) >= len(jobs) // 2


def test_pci_so_rj_ou_nacional(fixture_txt):
    # a página real muda de semana para semana (hoje só tem MG/RS); confere o formato e o filtro por UF
    real = publico.parse_pci(fixture_txt("pci.html"))
    assert all(j.local in ("RJ", "Nacional") for j in real)
    trecho = ('<a href="https://www.pciconcursos.com.br/noticias/inb-abre-concurso" title="INB abre concurso">'
              '<a href="https://www.pciconcursos.com.br/noticias/pref-rio" title="Prefeitura do Rio - RJ abre concurso">'
              '<a href="https://www.pciconcursos.com.br/noticias/pref-bh" title="Prefeitura de BH - MG abre concurso">'
              '<a href="https://www.pciconcursos.com.br/noticias/saa-ms" title="SAA MS abre processo seletivo">')
    jobs = publico.parse_pci(trecho)
    _basico(jobs, "PCI Concursos", "pci:")
    assert [j.local for j in jobs] == ["Nacional", "RJ"]
    assert all(j.extra["cat"] == "PUBLICO" for j in jobs)


def test_ipea(fixture_txt):
    jobs = publico.parse_ipea(fixture_txt("ipea_lista.html"))
    _basico(jobs, "Ipea", "ipea:")
    assert all(j.extra.get("checar_ipea") for j in jobs)


def test_fetch_descompacta_gzip_nao_pedido():
    import gzip
    from sources.base import decodificar
    assert decodificar(gzip.compress("Ipea – bolsas".encode())) == "Ipea – bolsas"
    assert decodificar("texto puro".encode()) == "texto puro"
