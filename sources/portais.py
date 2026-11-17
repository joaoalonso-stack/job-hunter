"""Portais que buscam um termo por vez, para o monitor de 3 em 3 horas: Gupy (via API, ver gupy.py),
Vagas.com.br, Catho e Glassdoor (RJ). A Gupy cobre as páginas de carreira de Itaú, Daycoval, Genial,
Opportunity, ABC Brasil, LCA Consultores e centenas de outras empresas."""
import html
import re
import time
import urllib.parse

from . import gupy
from .base import Bloqueado, Job, fetch, slug

TERMOS = [
    "economista", "economia", "macroeconomia", "pesquisa econômica", "assistente de pesquisa", "econometria",
    "middle office", "back office", "backoffice", "tesouraria", "analista de investimentos",
    "fundos de investimento", "controladoria de fundos", "asset management", "wealth management", "renda fixa",
    "mercado de capitais", "mercado financeiro", "derivativos", "custódia", "câmbio", "risco de mercado",
    "risco de crédito", "análise de crédito", "crédito estruturado", "trainee", "analista financeiro júnior",
    "planejamento financeiro", "relações com investidores", "inteligência de mercado", "commodities",
    "analista quantitativo",
]


def parse_vagascom(s):
    out = []
    for card in s.split('class="link-detalhes-vaga"')[1:]:
        t = re.search(r'title="([^"]+)"', card)
        h = re.search(r'href="(/vagas/v(\d+)/[^"]+)"', card)
        if not (t and h):
            continue
        e = re.search(r'class="emprVaga">\s*(.*?)\s*<', card, re.S)
        l = re.search(r'class="vaga-local">\s*<i[^>]*></i>\s*(.*?)\s*<', card, re.S)
        out.append(Job(id=f"vagascom:{h.group(2)}", fonte="Vagas.com.br", titulo=html.unescape(t.group(1)),
                       empresa=html.unescape(e.group(1)) if e else "", local=html.unescape(l.group(1)) if l else "",
                       url="https://www.vagas.com.br" + h.group(1)))
    return out


def parse_catho(s):
    out = []
    for art in s.split("<article")[1:]:
        a = re.search(r'<a href="(/vagas/[^"]+/(\d+))" title="([^"]+)"', art)
        if not a:
            continue
        e = re.search(r"<p[^>]*>\s*<span[^>]*>([^<]+)</span>\s*</p>", art)
        l = re.search(r"vagas?</strong>\s*-\s*([^<]+)<", art)
        out.append(Job(id=f"catho:{a.group(2)}", fonte="Catho", titulo=html.unescape(a.group(3)),
                       empresa=html.unescape(e.group(1)).strip() if e else "",
                       local=html.unescape(l.group(1)).strip() if l else "",
                       url="https://www.catho.com.br" + a.group(1)))
    return out


def parse_glassdoor(local):
    def parser(s):
        out = []
        for m in re.finditer(r'"@type":"ListItem","position":\d+,"name":"([^"]+)","url":"([^"]+jl=(\d+))"', s):
            # A URL traz "titulo-empresa-JV_..._KE<ini>,<fim>": os índices KE marcam a empresa no slug.
            emp = ""
            ke = re.search(r"/job-listing/(.+?)-JV_.*?_KE(\d+),(\d+)", m.group(2))
            if ke:
                emp = urllib.parse.unquote(ke.group(1))[int(ke.group(2)):int(ke.group(3))].replace("-", " ")
            out.append(Job(id=f"glassdoor:{m.group(3)}", fonte="Glassdoor", titulo=m.group(1), empresa=emp,
                           local=local, url=m.group(2)))
        return out
    return parser


def _pagina(url, parser, aceita, achadas):
    """Busca uma página de portal; se o site bloquear, desiste dele nesta rodada."""
    try:
        s = fetch(url, tentativas=1, espera=0)
    except Bloqueado:
        return False
    for job in parser(s):
        if aceita(job):
            achadas[job.id] = job
    time.sleep(1)
    return True


def coletar(aceita=lambda job: True, termos=TERMOS, incluir_gupy=True):
    # Gupy: uma página (até 100 vagas) por termo, publicadas nos últimos 7 dias. O pipeline diário passa
    # incluir_gupy=False porque roda a Gupy à parte, com mais páginas e a watchlist.
    achadas = {}
    if incluir_gupy:
        achadas = {j.id: j for j in gupy.coletar(termos, janela_dias=7, aceita=aceita, max_paginas=1)}
    ativos = {"vagascom": True, "catho": True, "glassdoor": True}
    for termo in termos:
        sl = slug(termo)
        if ativos["vagascom"]:
            ativos["vagascom"] = _pagina(f"https://www.vagas.com.br/vagas-de-{sl}?ordenar_por=mais_recentes",
                                         parse_vagascom, aceita, achadas)
        if ativos["catho"]:
            ativos["catho"] = _pagina(f"https://www.catho.com.br/vagas/{sl}/?order=dataAtualizacao",
                                      parse_catho, aceita, achadas)
        if ativos["glassdoor"]:
            ko = f"KO15,{15 + len(sl)}"
            ativos["glassdoor"] = _pagina(
                f"https://www.glassdoor.com.br/Vaga/rio-de-janeiro-{sl}-vagas-SRCH_IL.0,14_IC2402386_{ko}.htm?fromAge=7",
                parse_glassdoor("Rio de Janeiro, RJ"), aceita, achadas)
    return list(achadas.values())
