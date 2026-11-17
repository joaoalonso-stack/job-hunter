"""Monitor de 3 em 3 horas: coleta as fontes, aplica o filtro legado e manda cada vaga nova ao celular
via ntfy.sh. Convive com o pipeline diário (run.py) enquanto o usuário avalia os dois.

Uso:
  python monitor_vagas.py              # varre e notifica as vagas novas
  python monitor_vagas.py --seed       # marca as vagas atuais como vistas, sem notificar
  python monitor_vagas.py --dry        # mostra o que notificaria, sem enviar nem salvar
  python monitor_vagas.py --so-fila    # só reenvia a fila pendente
  python monitor_vagas.py --so-publicas | --sem-linkedin
"""
import sys
from datetime import datetime

import db
import notify
import registro
from pipeline import filtro_legado
from sources import linkedin_guest, portais, publico
from sources.publico import ipea_elegivel


def main(argv=sys.argv):
    seed, dry = "--seed" in argv, "--dry" in argv
    conn = db.conectar()
    db.migrar_legado(conn)
    inicio = db.agora()
    if "--so-fila" in argv:
        notify.enviar_fila(conn, [])
        return

    # Fontes públicas primeiro: não dependem do LinkedIn, que às vezes bloqueia.
    achadas = {j.id: j for j in publico.coletar() if filtro_legado.aceita(j)}
    if "--so-publicas" not in argv:
        achadas.update({j.id: j for j in portais.coletar(aceita=filtro_legado.aceita)})
        if "--sem-linkedin" not in argv:
            achadas.update({j.id: j for j in linkedin_guest.coletar(aceita=filtro_legado.aceita)})
    if not dry:
        db.upsert_vagas(conn, achadas.values())

    # A mesma vaga costuma estar em mais de um portal: deduplica também por título + empresa.
    vistas = db.ja_vistas(conn, [k for j in achadas.values() for k in (j.id, j.chave_legada())])
    novas, chaves_rodada = [], set()
    for j in achadas.values():
        if j.id in vistas or j.chave_legada() in vistas or j.chave_legada() in chaves_rodada:
            continue
        chaves_rodada.add(j.chave_legada())
        novas.append(j)
    if not seed:
        novas = [j for j in novas if not j.extra.get("checar_ipea") or ipea_elegivel(j)]
    novas.sort(key=lambda j: (filtro_legado.ORDEM[j.extra["cat"]], "rio de janeiro" not in j.local.lower()))

    if dry:
        for j in novas:
            print(f"[{j.extra['cat']}] {j.titulo} | {j.empresa} | {j.local} | {j.fonte} | {j.url}")
        return

    if not seed:
        notify.enviar_fila(conn, [notify.payload(j) for j in novas])
        if novas:
            with db.LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(f"\n## {datetime.now():%d/%m/%Y %H:%M}\n")
                for j in novas:
                    f.write(f"- [{j.extra['cat']}] [{j.titulo}]({j.url}) — {j.empresa} · {j.local} · "
                            f"{j.fonte} · {j.publicada}\n")

    db.marcar_vistas(conn, [k for j in achadas.values() for k in (j.id, j.chave_legada())])
    detalhe = f"{len(achadas)} vagas aderentes, {len(novas)} novas{' (seed, sem notificar)' if seed else ''}"
    db.registrar_execucao(conn, "monitor_3h", inicio, True, detalhe)
    print(detalhe)


if __name__ == "__main__":
    registro.configurar("monitor_3h")
    registro.manter_acordado()
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
