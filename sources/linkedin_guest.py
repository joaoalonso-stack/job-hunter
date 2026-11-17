"""LinkedIn pela busca pública (sem login), em poucas buscas agrupadas com OR."""
import html
import re
import time
import urllib.parse

from .base import Bloqueado, Job, fetch

LI_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
BRASIL = {"geoId": "106057199"}
RJ = {"location": "Rio de Janeiro, Rio de Janeiro, Brazil"}
SP = {"location": "São Paulo, São Paulo, Brazil"}

# (palavra-chave com OR, locais, páginas). Macro: Brasil inteiro, já que são raras.
# Poucas buscas agrupadas para não esbarrar no limite de requisições do LinkedIn (HTTP 429).
BUSCAS = [
    ('economista OR macroeconomia OR "macro research" OR "pesquisa econômica" OR "estudos econômicos" '
     'OR "economic research" OR economist', [BRASIL], 3),
    ('"middle office" OR "back office" OR backoffice OR tesouraria OR treasury OR "renda fixa" OR derivativos '
     'OR custódia OR "risco de mercado"', [RJ, SP], 3),
    ('"analista de investimentos" OR "fundos de investimento" OR "asset management" OR "wealth management" '
     'OR "mercado financeiro" OR trainee OR "analista financeiro"', [RJ, SP], 3),
    # Outras áreas aderentes ao CV: pesquisa/consultoria econômica, dados/econometria, commodities,
    # risco e crédito (estágio Genial), FP&A e RI.
    ('"consultoria econômica" OR "assistente de pesquisa" OR pesquisador OR econometria OR quantitativo '
     'OR "inteligência de mercado" OR commodities OR "analista de dados"', [RJ, SP], 2),
    ('"risco de crédito" OR "análise de crédito" OR "crédito estruturado" OR rating OR "planejamento financeiro" '
     'OR "FP&A" OR "relações com investidores"', [RJ, SP], 2),
]
PAUSA = 4


def parse(s):
    vagas = []
    for card in s.split("base-card")[1:]:
        t = re.search(r'base-search-card__title">\s*(.*?)\s*</h3>', card, re.S)
        u = re.search(r'href="(https://[a-z]+\.linkedin\.com/jobs/view/[^"?]+)', card)
        if not (t and u):
            continue
        c = re.search(r'base-search-card__subtitle">.*?>\s*(.*?)\s*</a>', card, re.S)
        l = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', card, re.S)
        d = re.search(r'datetime="([^"]+)"', card)
        jid = re.search(r"-(\d{8,})$", u.group(1))
        vagas.append(Job(
            id=jid.group(1) if jid else u.group(1),
            fonte="LinkedIn",
            titulo=html.unescape(t.group(1)).strip(),
            empresa=html.unescape(c.group(1)).strip() if c else "",
            local=html.unescape(l.group(1)).strip() if l else "",
            publicada=d.group(1) if d else "",
            url=f"https://www.linkedin.com/jobs/view/{jid.group(1)}" if jid else u.group(1),
        ))
    return vagas


def coletar(aceita=lambda job: True):
    """Devolve as vagas das últimas 24h que passam em `aceita`. Se o LinkedIn bloquear (HTTP 429),
    fica com o parcial; o resto sai na próxima rodada."""
    achadas = {}
    for kw, locais, paginas in BUSCAS:
        for loc in locais:
            for start in range(0, 25 * paginas, 25):
                params = {"keywords": kw, "f_TPR": "r86400", "start": str(start), **loc}
                try:
                    s = fetch(LI_SEARCH + "?" + urllib.parse.urlencode(params))
                except Bloqueado:
                    print("LinkedIn bloqueou temporariamente; resultado parcial.")
                    return list(achadas.values())
                cards = parse(s)
                for job in cards:
                    if aceita(job):
                        achadas[job.id] = job
                time.sleep(PAUSA)
                if len(cards) < 10:
                    break
    return list(achadas.values())
