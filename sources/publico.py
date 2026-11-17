"""Setor público: concursos do PCI (só RJ ou nacionais) e chamadas de bolsa do Ipea."""
import html
import re

from .base import Bloqueado, Job, fetch, norm

PCI_CARGOS = [
    "https://www.pciconcursos.com.br/cargos/economista",
    "https://www.pciconcursos.com.br/cargos/analista-de-planejamento-e-orcamento",
    "https://www.pciconcursos.com.br/cargos/analista-financeiro",
]
IPEA_LISTA = "https://www.ipea.gov.br/portal/bolsas-de-pesquisa-lista"
# Sigla de UF em maiúsculas em qualquer ponto do título ("Prefeitura X - MG", "SAA MS abre ...")
UF_RE = re.compile(r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b")


def parse_pci(s):
    out = []
    for href, titulo in re.findall(r'href="(https://www\.pciconcursos\.com\.br/noticias/[^"]+)"[^>]*title="([^"]+)"', s):
        titulo = html.unescape(titulo)
        uf = UF_RE.search(titulo)
        if uf and uf.group(1) != "RJ":
            continue
        out.append(Job(id="pci:" + href, fonte="PCI Concursos", titulo=titulo, empresa="Concurso público",
                       local=uf.group(1) if uf else "Nacional", url=href, extra={"cat": "PUBLICO"}))
    return out


def parse_ipea(s):
    out = []
    for sl in sorted(set(re.findall(r"bolsas-de-pesquisa-lista/(\d+-[a-z0-9-]+)", s))):
        out.append(Job(id="ipea:" + sl, fonte="Ipea", titulo=sl.split("-", 1)[1].replace("-", " "),
                       empresa="Bolsa Ipea", local="Ipea",
                       url=f"https://www.ipea.gov.br/portal/bolsas-de-pesquisa-lista/{sl}",
                       extra={"cat": "PUBLICO", "checar_ipea": True}))
    return out


def coletar():
    achadas = {}
    for url in PCI_CARGOS:
        try:
            achadas.update({j.id: j for j in parse_pci(fetch(url))})
        except Bloqueado:
            continue
    try:
        achadas.update({j.id: j for j in parse_ipea(fetch(IPEA_LISTA))})
    except Bloqueado:
        pass
    return list(achadas.values())


def ipea_elegivel(job):
    """Descarta chamadas só para doutores/mestres; mantém as de assistente/graduado."""
    try:
        t = norm(re.sub(r"<[^>]+>", " ", fetch(job.url)))
    except Bloqueado:
        return True
    if "fechad" in t and "aberta" not in t:
        return False
    return bool(re.search(r"assistente|graduad|bacharel|nivel superior", t))
