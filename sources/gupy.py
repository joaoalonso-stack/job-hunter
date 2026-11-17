"""Gupy pela API JSON pública que o próprio portal.gupy.io usa (rota /api/job-search/jobs; o robots.txt
do portal libera tudo). Cobre a busca por termo, as vagas remotas (que vêm sem cidade e sem estado) e as
páginas <empresa>.gupy.io da watchlist."""
import json
import re
import time
import urllib.parse
from datetime import date, timedelta

from .base import Bloqueado, Job, fetch

API = "https://portal.gupy.io/api/job-search/jobs"
LIMITE = 100          # máximo aceito pela API por página
MAX_PAGINAS = 5
PAUSA = 1

MODALIDADE = {"remote": "remoto", "hybrid": "hibrido", "on-site": "presencial"}
# Tipo de vaga da Gupy -> senioridade/forma de contratação (a /triagem usa como sinal, ex.: PJ é red flag)
TIPO = {"vacancy_type_internship": "estágio", "vacancy_type_trainee": "trainee", "vacancy_type_apprentice": "aprendiz",
        "vacancy_type_talent_pool": "banco de talentos", "vacancy_legal_entity": "PJ",
        "vacancy_type_temporary": "temporário", "vacancy_type_associate": "associado",
        "vacancy_type_lecturer": "docente", "vacancy_type_autonomous": "autônomo"}


def para_job(j):
    remoto = j.get("workplaceType") == "remote"
    cidade, uf = j.get("city") or "", j.get("state") or ""
    local = "Remoto" if remoto else ", ".join(p for p in (cidade, uf) if p)
    return Job(
        id=f"gupy:{j['id']}", fonte="Gupy", titulo=(j.get("name") or "").strip(),
        empresa=j.get("careerPageName") or "", local=local, modalidade=MODALIDADE.get(j.get("workplaceType"), ""),
        senioridade=TIPO.get(j.get("type"), ""), publicada=(j.get("publishedDate") or "")[:10],
        prazo=(j.get("applicationDeadline") or "")[:10], url=(j.get("jobUrl") or "").split("?")[0],
        descricao=j.get("description") or "",
        extra={"tipo_gupy": j.get("type"), "career_page": j.get("careerPageUrl")})


def parse_api(texto):
    d = json.loads(texto)
    return [para_job(j) for j in d.get("data", [])], d.get("pagination", {}).get("total", 0)


def _buscar(params, janela_dias=None, max_paginas=MAX_PAGINAS, buscar=fetch):
    """Pagina a API (ordenada da mais nova para a mais antiga) até acabar, atingir o limite de páginas
    ou passar da janela de publicação."""
    corte = (date.today() - timedelta(days=janela_dias)).isoformat() if janela_dias else ""
    vagas = []
    for pagina in range(max_paginas):
        q = {**params, "limit": LIMITE, "offset": pagina * LIMITE, "sortBy": "publishedDate", "sortOrder": "desc"}
        lote, total = parse_api(buscar(API + "?" + urllib.parse.urlencode(q), tentativas=2, espera=10))
        vagas += [j for j in lote if not corte or j.publicada >= corte]
        time.sleep(PAUSA)
        if not lote or (pagina + 1) * LIMITE >= total or (corte and lote[-1].publicada < corte):
            break
    return vagas


def nome_da_empresa(subdominio, buscar=fetch):
    """O filtro da API usa o nome oficial da página de carreira (ex.: 'BANCO DAYCOVAL'), que fica nos dados
    embutidos da página <empresa>.gupy.io."""
    s = buscar(f"https://{subdominio}.gupy.io/", tentativas=1, espera=0)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', s, re.S)
    if not m:
        return ""
    return json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("careerPage", {}).get("name", "")


def coletar(termos, watchlist=(), janela_dias=7, aceita=lambda job: True, max_paginas=MAX_PAGINAS, buscar=fetch):
    achadas = {}
    erros = []
    for termo in termos:
        try:
            for job in _buscar({"jobName": termo}, janela_dias, max_paginas, buscar):
                if aceita(job):
                    achadas[job.id] = job
        except (Bloqueado, ValueError) as e:
            erros.append(f"termo {termo!r}: {e}")
    # Remotas de todo o Brasil vêm sem cidade/estado; uma busca dedicada garante que não fiquem de fora.
    for termo in termos:
        try:
            for job in _buscar({"jobName": termo, "workplaceType": "remote"}, janela_dias, 1, buscar):
                if aceita(job):
                    achadas[job.id] = job
        except (Bloqueado, ValueError) as e:
            erros.append(f"remoto {termo!r}: {e}")
    # Watchlist: todas as vagas abertas da empresa, sem janela (são poucas e podem estar no ar há semanas).
    for sub in watchlist:
        try:
            nome = nome_da_empresa(sub, buscar)
            if not nome:
                erros.append(f"watchlist {sub!r}: página sem nome de empresa")
                continue
            for job in _buscar({"careerPageName": nome}, None, max_paginas, buscar):
                if aceita(job):
                    job.extra["watchlist"] = sub
                    achadas[job.id] = job
        except (Bloqueado, ValueError) as e:
            erros.append(f"watchlist {sub!r}: {e}")
    for e in erros:
        print("Gupy:", e)
    return list(achadas.values())
