"""Confirma, uma vez por dia, se cada vaga ativa ainda aceita candidaturas. Vaga encerrada vai para Arquivadas e
não entra no ranking nem na triagem.

Como cada fonte é confirmada:
- prazo vencido (qualquer fonte)                         -> encerrada;
- LinkedIn: página pública da vaga ("Não aceita mais candidaturas" / closed-job);
- Vagas.com.br e Catho: página da vaga (404/410 = removida; JobPosting.validThrough vencido = encerrada);
  de quebra preenche data de publicação, prazo e descrição;
- Gupy, Glassdoor (busca só dos últimos 7 dias), PCI: a listagem só mostra vagas abertas, então vista na coleta
  de hoje = aberta; não vista há mais de 2 dias = encerrada (Glassdoor bloqueia a página da vaga);
- Ipea: status da chamada na página ("Aberta"/"Fechada").
"""
import json
import random
import re
import time
from datetime import date, timedelta

from sources import descricoes
from sources.base import fetch_status, norm

PAUSA_LINKEDIN = (5, 15)
PAUSA_OUTRAS = (1, 2)
MAX_LINKEDIN = 40
SEM_CONFIRMACAO_DIAS = 2
POR_LISTAGEM = {"Gupy", "Glassdoor", "PCI Concursos"}


def _jobposting(s):
    for bloco in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', s, re.S):
        try:
            d = json.loads(bloco)
        except ValueError:
            continue
        for item in (d if isinstance(d, list) else [d]):
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return {}


def checar(job, hoje, visto_em, buscar=fetch_status):
    """Devolve (aberta: bool | None, motivo). None = não deu para confirmar agora (tenta de novo depois)."""
    if job.prazo and job.prazo < hoje:
        return False, f"prazo encerrado em {job.prazo}"
    if job.fonte in POR_LISTAGEM:
        if visto_em >= hoje:
            return True, "listada hoje na fonte"
        corte = (date.fromisoformat(hoje) - timedelta(days=SEM_CONFIRMACAO_DIAS)).isoformat()
        if visto_em < corte:
            return False, f"sumiu da listagem da fonte desde {visto_em}"
        return True, f"listada em {visto_em}"
    if job.fonte == "LinkedIn":
        if not job.id.isdigit():
            return None, ""
        cod, s = buscar(descricoes.LI_VAGA.format(id=job.id))
        if cod in (404, 410):
            return False, "vaga removida do LinkedIn"
        if cod != 200:
            return None, f"LinkedIn respondeu {cod}"
        if "closed-job" in s or "nao aceita mais candidaturas" in norm(s) or "no longer accepting" in s.lower():
            return False, "LinkedIn: não aceita mais candidaturas"
        if not job.descricao:
            job.descricao = descricoes.parse_linkedin(s)
        return True, "confirmada na página da vaga (LinkedIn)"
    if job.fonte in ("Vagas.com.br", "Catho"):
        cod, s = buscar(job.url)
        if cod in (404, 410):
            return False, f"vaga removida do {job.fonte}"
        if cod != 200:
            return None, f"{job.fonte} respondeu {cod}"
        jp = _jobposting(s)
        validade = str(jp.get("validThrough") or "")[:10]
        if not job.publicada and jp.get("datePosted"):
            job.publicada = str(jp["datePosted"])[:10]
        if validade and not job.prazo:
            job.prazo = validade
        if not job.descricao:
            job.descricao = descricoes.parse_vagascom(s) if job.fonte == "Vagas.com.br" else descricoes.parse_jobposting(s)
        if validade and validade < hoje:
            return False, f"validade da vaga encerrada em {validade}"
        if not jp and "vaga" in norm(s) and re.search(r"encerrad|expirad|nao esta mais disponivel", norm(s)):
            return False, f"{job.fonte}: vaga encerrada"
        return True, f"confirmada na página da vaga ({job.fonte})"
    if job.fonte == "Ipea":
        cod, s = buscar(job.url)
        if cod != 200:
            return None, f"Ipea respondeu {cod}"
        t = norm(re.sub(r"<[^>]+>", " ", s))
        if "fechad" in t and "aberta" not in t:
            return False, "chamada do Ipea fechada"
        return True, "chamada aberta no Ipea"
    return None, ""


def verificar(jobs, visto_em, hoje, buscar=fetch_status, dormir=time.sleep):
    """Confere as vagas e devolve [(job, aberta, motivo)]. Para uma fonte se ela começar a bloquear."""
    res, n_li, bloqueadas = [], 0, set()
    for j in jobs:
        if j.fonte in bloqueadas or (j.fonte == "LinkedIn" and n_li >= MAX_LINKEDIN):
            continue
        aberta, motivo = checar(j, hoje, visto_em.get(j.id, ""), buscar)
        res.append((j, aberta, motivo))
        if j.fonte in ("LinkedIn", "Vagas.com.br", "Catho", "Ipea"):
            if aberta is None and motivo:
                bloqueadas.add(j.fonte)
            if j.fonte == "LinkedIn":
                n_li += 1
            dormir(random.uniform(*(PAUSA_LINKEDIN if j.fonte == "LinkedIn" else PAUSA_OUTRAS)))
    return res
