"""Busca a descrição completa das vagas que a listagem não traz: LinkedIn (página pública da vaga), Vagas.com.br e
Catho. Roda só para as vagas que passaram no filtro, parando no primeiro bloqueio de cada site. No LinkedIn as
pausas são longas (5-15 s); nos outros, curtas."""
import html
import json
import random
import re
import time

from .base import Bloqueado, fetch

LI_VAGA = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
MAX_POR_FONTE = 40


def _texto(fragmento):
    texto = re.sub(r"<br\s*/?>|</p>|</li>", "\n", fragmento)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", texto)).strip()


def parse_linkedin(s):
    m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', s, re.S)
    return _texto(m.group(1)) if m else ""


def parse_vagascom(s):
    m = re.search(r'class="[^"]*job-description__text[^"]*"[^>]*>(.*?)</div>', s, re.S)
    return _texto(m.group(1)) if m else ""


def parse_jobposting(s):
    """Páginas com dados estruturados schema.org (Catho e outras)."""
    for bloco in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', s, re.S):
        try:
            d = json.loads(bloco)
        except ValueError:
            continue
        for item in (d if isinstance(d, list) else [d]):
            if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                return _texto(item["description"])
    return ""


FONTES = {  # fonte -> (url da página da vaga, parser, pausa em segundos)
    "LinkedIn": (lambda j: LI_VAGA.format(id=j.id) if j.id.isdigit() else None, parse_linkedin, (5, 15)),
    "Vagas.com.br": (lambda j: j.url, parse_vagascom, (1, 2)),
    "Catho": (lambda j: j.url, parse_jobposting, (1, 2)),
}


def completar(jobs, maximo=MAX_POR_FONTE, buscar=fetch, dormir=time.sleep):
    """Preenche job.descricao das vagas sem descrição. Devolve {fonte: quantas preencheu}."""
    feitas, bloqueadas = {}, set()
    for j in jobs:
        if j.descricao or j.fonte not in FONTES or j.fonte in bloqueadas or feitas.get(j.fonte, 0) >= maximo:
            continue
        url_de, parser, pausa = FONTES[j.fonte]
        url = url_de(j)
        if not url:
            continue
        try:
            j.descricao = parser(buscar(url, tentativas=1, espera=0))
        except Bloqueado:
            print(f"{j.fonte} bloqueou a leitura das descrições; o resto fica para a próxima rodada.")
            bloqueadas.add(j.fonte)
            continue
        feitas[j.fonte] = feitas.get(j.fonte, 0) + 1
        dormir(random.uniform(*pausa))
    return feitas
