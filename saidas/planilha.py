"""Gera relatorios/vagas.xlsx (abas Hoje / Ativas / Candidaturas / Resumo). As colunas Status, Data em que
apliquei e Observações são editáveis: antes de regerar, o que foi editado é lido e gravado no SQLite."""
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import db
from saidas.pagina import TRILHAS

COLUNAS = [  # (cabeçalho, chave, largura)
    ("Nota", "nota", 7), ("Cargo", "cargo", 42), ("Empresa", "empresa", 26), ("Trilha", "trilha", 18),
    ("Local", "local", 22), ("Modalidade", "modalidade", 12), ("Fonte", "fonte", 13), ("Publicada", "publicada", 11),
    ("Prazo", "prazo", 11), ("Link", "url", 12), ("Por que encaixa", "encaixe", 50), ("O que falta", "falta", 30),
    ("Red flags", "red_flags", 30), ("Status", "status", 13), ("Data em que apliquei", "data_aplicacao", 14),
    ("Observações", "observacoes", 40), ("ID", "id", 14),
]
EDITAVEIS = {"Status": "status", "Data em que apliquei": "data_aplicacao", "Observações": "observacoes"}
ABAS_LISTA = ["Hoje", "Ativas", "Candidaturas"]
CAB = PatternFill("solid", fgColor="1F5FBF")
VERDE, VERDE_CLARO, AMARELO, CINZA, VERMELHO = (PatternFill("solid", fgColor=c) for c in
                                                ("C6EFCE", "E2F0D9", "FFF2CC", "EDEDED", "FFC7CE"))


def ler_edicoes(caminho):
    """Lê as colunas editáveis da planilha existente: {id: [valores em cada aba onde a vaga aparece]}.
    A mesma vaga pode estar em Hoje, Ativas e Candidaturas; a edição pode ter sido feita em qualquer uma."""
    if not Path(caminho).exists():
        return {}
    wb = load_workbook(caminho, read_only=True, data_only=True)
    edicoes = {}
    for nome in ABAS_LISTA:
        if nome not in wb.sheetnames:
            continue
        ws = wb[nome]
        linhas = ws.iter_rows(values_only=True)
        cab = list(next(linhas, []))
        if "ID" not in cab:
            continue
        i_id = cab.index("ID")
        for row in linhas:
            if not row or not row[i_id]:
                continue
            d = {}
            edicoes.setdefault(str(row[i_id]), []).append(d)
            for col, chave in EDITAVEIS.items():
                if col in cab:
                    v = row[cab.index(col)]
                    if isinstance(v, datetime):
                        v = v.date().isoformat()
                    d[chave] = "" if v is None else str(v).strip()
    wb.close()
    return edicoes


def importar_edicoes(conn, caminho, linhas):
    """Grava no SQLite o que mudou na planilha desde a última geração (com o horário do arquivo)."""
    edicoes = ler_edicoes(caminho)
    if not edicoes:
        return 0
    quando = datetime.fromtimestamp(Path(caminho).stat().st_mtime).isoformat(timespec="seconds")
    atual = {l["id"]: l for l in linhas}
    n = 0
    for vid, por_aba in edicoes.items():
        antes = atual.get(vid, {})
        mudou = {}
        for ed in por_aba:  # vale o primeiro valor diferente do banco, em qualquer aba
            for k, v in ed.items():
                if k not in mudou and v != (antes.get(k) or ""):
                    mudou[k] = v
        if not mudou:
            continue
        if mudou.get("status", "") not in db.STATUS_VALIDOS:
            mudou.pop("status")
        if mudou and db.salvar_status(conn, vid, quando=quando, **mudou):
            n += 1
    return n


def _valor(l, chave):
    v = l.get(chave)
    if chave == "trilha":
        return TRILHAS.get(v, v or "")
    if chave in ("falta", "red_flags"):
        return "; ".join(v or [])
    if chave == "nota" and v is None:
        return None
    return v if v is not None else ""


def _aba(wb, titulo, linhas, hoje, prazo_dias):
    ws = wb.create_sheet(titulo)
    ws.append([c for c, _, _ in COLUNAS])
    for c in ws[1]:
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), CAB, Alignment(vertical="center", wrap_text=True)
    for l in linhas:
        ws.append([_valor(l, k) for _, k, _ in COLUNAS])
        r = ws.max_row
        link = ws.cell(r, [k for _, k, _ in COLUNAS].index("url") + 1)
        if l.get("url"):
            link.hyperlink, link.value, link.style = l["url"], "Candidatar", "Hyperlink"
    for i, (_, _, larg) in enumerate(COLUNAS, 1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=c.column_letter in ("B", "K", "L", "M", "P"))
    ultima = max(ws.max_row, 2)
    ref = f"A1:{get_column_letter(len(COLUNAS))}{ultima}"
    ws.auto_filter.ref = ref
    ws.freeze_panes = "C2"
    # nota colorida
    faixa = f"A2:A{ultima}"
    ws.conditional_formatting.add(faixa, CellIsRule(operator="greaterThanOrEqual", formula=["85"], fill=VERDE))
    ws.conditional_formatting.add(faixa, CellIsRule(operator="between", formula=["65", "84"], fill=VERDE_CLARO))
    ws.conditional_formatting.add(faixa, CellIsRule(operator="between", formula=["50", "64"], fill=AMARELO))
    ws.conditional_formatting.add(faixa, CellIsRule(operator="lessThan", formula=["50"], fill=CINZA))
    # prazo em vermelho quando faltar até N dias (prazo está como texto AAAA-MM-DD)
    ws.conditional_formatting.add(
        f"I2:I{ultima}", FormulaRule(formula=[f'AND(I2<>"",DATEVALUE(I2)-TODAY()<={prazo_dias})'], fill=VERMELHO))
    dv = DataValidation(type="list", formula1='",interessado,apliquei,descartei"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"N2:N{max(ultima, 500)}")
    return ws


def _resumo(wb, linhas, hoje):
    ws = wb.create_sheet("Resumo")
    ws.append(["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M")])
    blocos = [
        ("Por aba", Counter({"hoje": "Hoje", "ativa": "Ativas", "arquivada": "Arquivadas"}[l["aba"]] if not l["hoje"]
                            else "Hoje" for l in linhas)),
        ("Por trilha (triadas)", Counter(TRILHAS.get(l["trilha"], l["trilha"]) for l in linhas if l["trilha"])),
        ("Por fonte", Counter(l["fonte"] for l in linhas)),
        ("Por status", Counter(l["status"] or "sem status" for l in linhas)),
        ("Notas (triadas)", Counter("≥85" if l["nota"] >= 85 else "65–84" if l["nota"] >= 65 else "50–64"
                                    if l["nota"] >= 50 else "<50" for l in linhas if l["nota"] is not None)),
    ]
    for titulo, cont in blocos:
        ws.append([])
        ws.append([titulo])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        for k, v in cont.most_common():
            ws.append([k, v])
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 18


def gerar(conn, linhas, prefs, destino, hoje):
    """Importa as edições da planilha atual, gera a nova e guarda uma cópia datada em historico/."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    pd = prefs["limiares"]["prazo_dias"]
    _aba(wb, "Hoje", [l for l in linhas if l["hoje"] and l["aba"] == "ativa"], hoje, pd)
    _aba(wb, "Ativas", [l for l in linhas if l["aba"] == "ativa" and l["status"] != "descartei"], hoje, pd)
    _aba(wb, "Candidaturas", [l for l in linhas if l["status"] in ("interessado", "apliquei")], hoje, pd)
    _resumo(wb, linhas, hoje)
    try:
        wb.save(destino)
        salvo = destino
    except PermissionError:  # aberta no Excel: salva ao lado para não perder a rodada
        salvo = destino.with_name(f"vagas_{datetime.now():%Y-%m-%d_%H%M}.xlsx")
        wb.save(salvo)
        print(f"vagas.xlsx está aberta no Excel; a versão nova foi salva como {salvo.name}")
    hist = destino.parent / "historico"
    hist.mkdir(exist_ok=True)
    shutil.copy2(salvo, hist / f"vagas_{hoje}.xlsx")
    return salvo
