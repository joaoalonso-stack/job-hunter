"""Filtro por regex do monitor de 3 em 3 horas (versão restrita de 19/10/2026), usado só pelos alertas
imediatos. O pipeline diário usa o filtro do YAML."""
import re

from sources.base import norm

MACRO_RE = re.compile(r"economista|economist|macroeconom|\bmacro\b|conjuntura|estudos economicos|"
                      r"pesquisa economica|economic research|economics|analise economica|inteligencia economica|"
                      r"research economico|economia (aplicada|brasileira|internacional)|politica monetaria|politica fiscal")
ECON_FALSO_RE = re.compile(r"economia circular|economia criativa|rede economia|economico.financeiro|fiscal de|"
                           r"nota fiscal|fiscal tributari|analista fiscal|escrita fiscal|fiscal contabil|fiscal\b.*loja")
# Termos de mercado financeiro: valem em qualquer empresa.
FIN_FORTE_RE = re.compile(
    r"middle ?office|investiment|investment|fundos?\b|\bfunds?\b|\basset\b|wealth|portfolio|renda fixa|"
    r"fixed income|mercado de capitais|derivativ|custodia|controladoria de fundos|liquidacao|risco de mercado|"
    r"market risk|liquidez|\bfidc\b|mercado financeiro|\botc\b|cotas|\bdtvm\b|securitiza|tesouraria de banco"
)
# Termos genéricos: só valem se a empresa for financeira.
FIN_FRACO_RE = re.compile(r"back ?office|tesouraria|treasury|analista financeiro|financial analyst|cambio|"
                          r"research|operacoes|trainee")
EMPRESA_FIN_RE = re.compile(
    r"banco|bank|asset|capital|invest|gestora|gestao de recursos|dtvm|corretora|securitiz|fidc|financ|wealth|"
    r"partners|previd|seguros|seguradora|itau|bradesco|santander|btg|\bxp\b|safra|daycoval|genial|vinci|patria|"
    r"sicredi|sicoob|nubank|\binter\b|\bc6\b|modal|bocom|\bbbm\b|abc brasil|sofisa|fibra|\bpine\b|original|stone|"
    r"\bb3\b|anbima|bndes|kinea|ibiuna|\bjgp\b|legacy|kapitalo|\bspx\b|opportunity|gavea|apex|vortx|"
    r"oliveira trust|pentagono|planner|warren|ourinvest|\bbv\b|votorantim|cambio|\bcielo\b|magnetis|nomos|"
    r"tesouro|fundo|credito|\bubs\b|morgan|goldman|citi\b|citibank|\bbnp\b|hsbc|credit suisse|\bjp\b|"
    r"barclays|deutsche|mufg|mizuho|scotia|\bbofa\b|bank of america|blackrock|\bot\b|vempraot|g5"
)
# Títulos que só existem no mercado financeiro: valem mesmo sem reconhecer a empresa.
MERCADO_CORE_RE = re.compile(
    r"middle ?office|\bmiddle\b|merc capit|\bfunds?\b|investment fund|fundos? de investimento|\bfidc\b|\basset\b|"
    r"renda fixa|fixed income|derivativ|mercado de capitais|custodia|controladoria de fundos|risco de mercado|"
    r"market risk|\botc\b|cotas|wealth|portfolio|tesouraria de banco|\bdtvm\b|securitiza"
)
# Perfil analítico (econometria/quant/consultoria econômica): vale em qualquer empresa.
ANALITICO_RE = re.compile(r"econometr|quantitativ|\bquant\b|consultori?a? econ|consultor econ")
# Vagas de pesquisa só em instituições de pesquisa/consultoria (evita P&D de indústria, pesquisa de campo).
PESQ_RE = re.compile(r"pesquisador|assistente de pesquisa|research assistant")
EMPRESA_PESQ_RE = re.compile(r"\bfgv\b|getulio|ibre|ipea|insper|cebri|iepe|casa das garcas|ibge|bndes|fipe|"
                             r"dieese|cebrap|universidade|\bpuc\b|ufrj|usp\b|consultoria|economia|instituto")
EXCLUI_RE = re.compile(
    r"\bs[eê]nior\b|\bsenior\b|\bsr\.?\b|\bpleno\b|\bpl\.?\b|coordena|gerente|\bmanager\b|\bhead\b|"
    r"diretor|director|especialista|specialist|\blead\b|supervis|superintend|estagi|\bintern\b|"
    r"internship|aprendiz|ssessor|assesor|advisor|banker|closer|vendas|vendedor|comercial|\bsales\b|"
    r"\bii\b|\biii\b|\biv\b|\bassociate\b|\bvp\b|partner|socio|caixa|contas a pagar|contas a receber|"
    r"contas medicas|faturamento|cobranca|auxiliar|(?<!pesquisador )assistente(?! de pesquisa)|tecnico|"
    r"desenvolvedor|developer|engenheir|engineer|summer|ferias|atendente|telemarketing|advogad|paralegal|"
    r"juridic|departamento pessoal|chefe|banco de talentos|temporari|enfermeir|pesquisador de campo|"
    r"pesquisa e desenvolvimento|consultor(?!ia econ| econ)|totvs|protheus|\bbpo\b|product owner|"
    r"agendamento|exames|consorcio"
)
OUTRAS_RE = re.compile(
    r"pesquisador|assistente de pesquisa|research assistant|consultor(ia)? econ|econometr|quantitativ|\bquant\b|"
    r"commodit|risco de credito|credit risk|analise de credito|analista de credito|credito estruturado|"
    r"\brating\b|relacoes com investidores|investor relations|\bri\b"
)
LOCAL_OK_RE = re.compile(r"rio de janeiro|niteroi|sao paulo|remot|brasil$|brazil$")
JUNIOR_RE = re.compile(r"junior|\bjr\b|trainee|entry|analista i\b|\bi\b$")

ORDEM = {"MACRO": 0, "PUBLICO": 1, "JR": 2, "FIN": 3, "OUTRAS": 4}


def classifica(job):
    """Categoria do alerta (MACRO, JR, FIN, OUTRAS) ou None se a vaga não interessa."""
    if job.extra.get("cat") == "PUBLICO":
        return "PUBLICO"
    t, e, loc = norm(job.titulo), norm(job.empresa), norm(job.local)
    if EXCLUI_RE.search(t):
        return None
    if MACRO_RE.search(t) and not ECON_FALSO_RE.search(t):
        return "MACRO"  # vale no Brasil todo, já que são raras
    if not LOCAL_OK_RE.search(loc):
        return None
    jr = bool(JUNIOR_RE.search(t))
    emp_fin = bool(EMPRESA_FIN_RE.search(e))
    if MERCADO_CORE_RE.search(t) or ((FIN_FRACO_RE.search(t) or FIN_FORTE_RE.search(t)) and emp_fin):
        return "JR" if jr else "FIN"
    if ANALITICO_RE.search(t):
        return "OUTRAS"
    if PESQ_RE.search(t) and (EMPRESA_PESQ_RE.search(e) or emp_fin):
        return "OUTRAS"
    if OUTRAS_RE.search(t) and emp_fin:
        return "OUTRAS"
    return None


def aceita(job):
    """Marca a categoria na vaga e diz se ela entra nos alertas."""
    cat = classifica(job)
    if cat:
        job.extra["cat"] = cat
    return cat is not None
