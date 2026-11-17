"""Dedup fuzzy por empresa + título + cidade (rapidfuzz). A mesma vaga aparece na Gupy, no LinkedIn, no
Glassdoor...; fica a da fonte original (página da empresa) em vez da do agregador."""
from rapidfuzz import fuzz, utils

from sources.base import norm

# Menor = preferida. Fontes originais (ATS da empresa, órgão público) antes dos agregadores.
PRIORIDADE = {"Gupy": 0, "Greenhouse": 0, "Lever": 0, "PCI Concursos": 0, "Ipea": 0,
              "Vagas.com.br": 1, "Catho": 1, "LinkedIn": 2, "Indeed": 2, "Glassdoor": 2, "Google Jobs": 3}
LIMIAR_TITULO = 90
LIMIAR_EMPRESA = 85


def cidade(job):
    if job.modalidade == "remoto" or "remot" in norm(job.local):
        return "remoto"
    return norm(job.local).split(",")[0].split("/")[0].strip()


def mesma_vaga(a, b):
    ca, cb = cidade(a), cidade(b)
    if ca and cb and ca != cb:
        return False
    ea, eb = norm(a.empresa), norm(b.empresa)
    if not ea or not eb or fuzz.token_set_ratio(ea, eb, processor=utils.default_process) < LIMIAR_EMPRESA:
        return False
    # processor tira pontuação: "Júnior - Asset" e "Júnior (Asset)" são o mesmo título
    return fuzz.token_sort_ratio(norm(a.titulo), norm(b.titulo), processor=utils.default_process) >= LIMIAR_TITULO


def _melhor(a, b):
    chave = lambda j: (PRIORIDADE.get(j.fonte, 2), -len(j.descricao or ""))
    return a if chave(a) <= chave(b) else b


def deduplicar(jobs):
    """Devolve (únicas, {id_duplicada: id_mantida})."""
    mantidas, dups = [], {}
    for j in jobs:
        for i, m in enumerate(mantidas):
            if mesma_vaga(j, m):
                vence = _melhor(m, j)
                perde = j if vence is m else m
                mantidas[i] = vence
                dups[perde.id] = vence.id
                # quem apontava para a perdedora passa a apontar para a vencedora
                for k, v in dups.items():
                    if v == perde.id:
                        dups[k] = vence.id
                break
        else:
            mantidas.append(j)
    return mantidas, dups
