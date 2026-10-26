"""experimentos.py — Corre los mundos de prueba con ambos mecanismos y genera tablas y bitácoras.

    python experimentos.py                 # mundos m*.json + lote aleatorio (semillas 7000..7199)
    python experimentos.py --lote 0        # sin lote aleatorio
    python experimentos.py --salida carpeta

Salida (carpeta `resultados/` por defecto):
    tabla_metricas.{md,csv}        métricas de misión por mundo y mecanismo (cada uno juega su propia partida)
    comparacion_mecanismos.{md,csv} ambos mecanismos contestan el MISMO conjunto de consultas sobre la MISMA KB
    lote_aleatorio.md              tasas de éxito / bloqueo / muerte en N mundos aleatorios
    trazas/<mundo>_<mecanismo>.txt bitácora completa de cada partida (percepción → … → nuevo estado, con pruebas)
"""
import argparse
import csv
import glob
import os
import time
from collections import Counter

from agente import Agente
from entorno import EXITO, MUERTE_POZO, MUERTE_WUMPUS, Entorno
import oraculo                      # sólo EVALUACIÓN: contrasta las respuestas con la verdad por enumeración
from motor import ENCADENAMIENTO, RESOLUCION, Motor, Resultado
from wumpus_kb import simbolo

AQUI = os.path.dirname(os.path.abspath(__file__))
V, F, D = Resultado.VERDADERO, Resultado.FALSO, Resultado.DESCONOCIDO
NOMBRE = {RESOLUCION: "resolución", ENCADENAMIENTO: "enc. adelante"}


def tabla_md(cabeceras, filas):
    l = ["| " + " | ".join(cabeceras) + " |", "|" + "|".join("---:" if i else ":---" for i in range(len(cabeceras))) + "|"]
    l += ["| " + " | ".join(str(x) for x in f) + " |" for f in filas]
    return "\n".join(l)


def guardar_csv(ruta, cabeceras, filas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabeceras)
        w.writerows(filas)


def jugar(entorno, metodo, politica="salir"):
    a = Agente(entorno.vista_agente(), metodo, politica_bloqueo=politica)
    r = a.jugar()
    r["resultado"] = entorno.resultado
    r["exito"] = entorno.resultado == EXITO
    r["muerte"] = entorno.resultado in (MUERTE_POZO, MUERTE_WUMPUS)
    return a, r


def verdad_oraculo(kb, n):
    """Consecuencias exactas de lo observado (enumeración de modelos). Sólo 4×4."""
    obs = [((i, j), [p for p, s in (("Brisa", "B"), ("Hedor", "H"), ("Resplandor", "R"))
                     if kb.valor_directo(simbolo(s, i, j))]) for (i, j) in sorted(kb.casillas_visitadas)]
    return oraculo.consecuencias(n, obs, wumpus_vivo=not kb.wumpus_muerto, exclusion=True)


def comparar_mecanismos(ruta_o_entorno_fn):
    """Juega con resolución y, tras cada ciclo, plantea a DOS motores independientes (uno por mecanismo, sin memoria)
    las mismas consultas sobre la misma KB: es_seguro / hay_pozo / hay_wumpus de todas las casillas."""
    e = ruta_o_entorno_fn()
    a = Agente(e.vista_agente(), RESOLUCION)
    mr, mf = Motor(a.kb, memoria=False), Motor(a.kb, memoria=False)
    acum = {"pares": Counter(), "consultas": 0, "inconclusas": 0, "e_res": 0, "e_enc": 0, "t_res": 0.0, "t_enc": 0.0,
            "res_vs_or": 0, "enc_mal": 0, "enc_incompleto": 0, "con_oraculo": 0}
    n = e.n

    def al_ciclo(ag, ciclo):
        o = verdad_oraculo(ag.kb, n) if n == 4 else None
        vivo = not ag.kb.wumpus_muerto
        for c in ag.kb.casillas():
            for nombre in ("es_seguro", "hay_pozo", "hay_wumpus"):
                rr, tr_r = getattr(mr, nombre)(*c, RESOLUCION)
                rf, tr_f = getattr(mf, nombre)(*c, ENCADENAMIENTO)
                if o is not None and (nombre != "hay_wumpus" or vivo):
                    if nombre == "es_seguro":
                        real = V if c in o["seguras"] else F if c in o["peligro_cierto"] else D
                    elif nombre == "hay_pozo":
                        real = V if c in o["pozo_cierto"] else F if c not in o["pozo_posible"] else D
                    else:
                        real = V if o["wumpus_cierto"] == c else F if c not in o["wumpus_posible"] else D
                    acum["con_oraculo"] += 1
                    acum["res_vs_or"] += rr is not real
                    acum["enc_mal"] += rf is not D and rf is not real
                    acum["enc_incompleto"] += rf is D and real is not D
                acum["pares"][(rr.name, rf.name)] += 1
                acum["consultas"] += 1
                acum["inconclusas"] += rr is D and (tr_r.agotado or tr_r.podadas > 0)
                acum["e_res"] += tr_r.esfuerzo
                acum["e_enc"] += tr_f.esfuerzo
                acum["t_res"] += tr_r.tiempo
                acum["t_enc"] += tr_f.tiempo

    a.jugar(al_ciclo=al_ciclo)
    acum["e_res"] += mr.mant_resoluciones
    acum["t_res"] += mr.mant_tiempo
    return acum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", type=int, default=200)
    ap.add_argument("--semilla-lote", type=int, default=7000)
    ap.add_argument("--salida", default=os.path.join(AQUI, "resultados"))
    args = ap.parse_args()
    os.makedirs(os.path.join(args.salida, "trazas"), exist_ok=True)
    rutas = sorted(glob.glob(os.path.join(AQUI, "mundos", "m*.json")))

    # 1) métricas de misión ----------------------------------------------------------------
    cab = ["mundo", "mecanismo", "resultado", "ciclos", "movs", "visitadas", "disparos", "bloqueo", "riesgo", "muerte",
           "consultas", "V", "F", "D", "resoluc.", "reglas", "esfuerzo", "t total ms", "t/consulta ms", "contrad.", "|KB|"]
    filas = []
    for r in rutas:
        nombre = os.path.basename(r)[:-5]
        for met in (RESOLUCION, ENCADENAMIENTO):
            e = Entorno.cargar(r)
            a, m = jugar(e, met)
            filas.append([nombre, NOMBRE[met], m["resultado"], m["ciclos"], m["movimientos"], m["casillas_visitadas"],
                          m["disparos"], "sí" if m["bloqueo"] else "no", m["entradas_riesgo"], "sí" if m["muerte"] else "no",
                          m["consultas"], m["verdadero"], m["falso"], m["desconocido"],
                          m["resoluciones"] + m["mantenimiento"], m["activaciones"], m["esfuerzo"],
                          f'{m["tiempo_s"] * 1000:.1f}', f'{m["tiempo_s"] * 1000 / max(1, m["consultas"]):.3f}',
                          m["contradicciones"], m["clausulas_kb"]])
            with open(os.path.join(args.salida, "trazas", f"{nombre}_{met}.txt"), "w", encoding="utf-8") as f:
                f.write(f"MUNDO {nombre} — mecanismo: {met}\n{e.dibujar()}\nResultado: {e.resultado}\n"
                        f"Resumen: {m}\n\n{a.texto_bitacora()}\n")
                if a.motor.eventos_contradiccion:
                    f.write("\nCONTRADICCIONES:\n" + "\n".join(a.motor.eventos_contradiccion))
    guardar_csv(os.path.join(args.salida, "tabla_metricas.csv"), cab, filas)
    md = "# Métricas por mundo y mecanismo\n\n" + tabla_md(cab, filas) + "\n"
    open(os.path.join(args.salida, "tabla_metricas.md"), "w", encoding="utf-8").write(md)

    # 2) comparación sobre consultas comunes ---------------------------------------------------
    cab2 = ["mundo", "consultas", "coinciden", "res decide / enc desconoce", "contradicciones entre mecanismos",
            "res ≠ oráculo", "enc incorrectas", "enc incompletas", "res: D con poda", "esfuerzo res", "esfuerzo enc",
            "t res ms", "t enc ms"]
    filas2 = []
    for r in rutas:
        ac = comparar_mecanismos(lambda r=r: Entorno.cargar(r))
        p = ac["pares"]
        coinciden = sum(v for (x, y), v in p.items() if x == y)
        pierde = sum(v for (x, y), v in p.items() if x != "DESCONOCIDO" and y == "DESCONOCIDO")
        choque = sum(v for (x, y), v in p.items() if "DESCONOCIDO" not in (x, y) and x != y) + \
            sum(v for (x, y), v in p.items() if x == "DESCONOCIDO" and y != "DESCONOCIDO")
        orc = lambda k: ac[k] if ac["con_oraculo"] else "n/a"
        filas2.append([os.path.basename(r)[:-5], ac["consultas"], coinciden, pierde, choque, orc("res_vs_or"),
                       orc("enc_mal"), orc("enc_incompleto"), ac["inconclusas"],
                       ac["e_res"], ac["e_enc"], f'{ac["t_res"] * 1000:.1f}', f'{ac["t_enc"] * 1000:.1f}'])
    guardar_csv(os.path.join(args.salida, "comparacion_mecanismos.csv"), cab2, filas2)
    open(os.path.join(args.salida, "comparacion_mecanismos.md"), "w", encoding="utf-8").write(
        "# Comparación de mecanismos sobre las mismas consultas y la misma KB\n\n"
        "Tras cada ciclo se consulta es_seguro, hay_pozo y hay_wumpus de TODAS las casillas con ambos mecanismos.\n\n"
        + tabla_md(cab2, filas2) + "\n\n"
        "- *res decide / enc desconoce*: respuestas demostradas por resolución que el encadenamiento no alcanza.\n"
        "- *contradicciones*: respuestas opuestas, o en las que el encadenamiento demuestra algo que la resolución no "
        "(debe ser 0: ambos son correctos).\n"
        "- *res ≠ oráculo / enc incorrectas / enc incompletas*: contraste con la verdad por enumeración de modelos "
        "(sólo 4×4; el hay_wumpus se excluye tras el Grito). Deben ser 0 / 0 / —.\n"
        "- *res: D con poda*: respuestas DESCONOCIDO de la resolución en cuya búsqueda se podó algún resolvente por "
        "longitud (o se alcanzó el tope): el motor no puede *garantizar* que sean indemostrables; el oráculo confirma que lo son.\n")

    # 3) lote aleatorio -------------------------------------------------------------------
    if args.lote:
        cont, extra = Counter(), Counter()
        t0 = time.perf_counter()
        for k in range(args.lote):
            for met in (RESOLUCION, ENCADENAMIENTO):
                e = Entorno(4, semilla=args.semilla_lote + k)
                a, m = jugar(e, met)
                cont[(met, "exito" if m["exito"] else "bloqueo" if m["bloqueo"] else "otro")] += 1
                cont[(met, "muerte")] += m["muerte"]
                extra[(met, "riesgo")] += m["entradas_riesgo"]
                extra[(met, "esfuerzo")] += m["esfuerzo"]
                extra[(met, "t")] += m["tiempo_s"]
                extra[(met, "disparos")] += m["disparos"]
        n = args.lote
        filas3 = [[NOMBRE[met], f'{cont[(met, "exito")]} ({100 * cont[(met, "exito")] / n:.1f} %)',
                   f'{cont[(met, "bloqueo")]} ({100 * cont[(met, "bloqueo")] / n:.1f} %)', cont[(met, "muerte")],
                   extra[(met, "riesgo")], extra[(met, "disparos")], f'{extra[(met, "esfuerzo")] / n:.0f}',
                   f'{extra[(met, "t")] * 1000 / n:.1f}'] for met in (RESOLUCION, ENCADENAMIENTO)]
        open(os.path.join(args.salida, "lote_aleatorio.md"), "w", encoding="utf-8").write(
            f"# Lote aleatorio: {n} mundos 4×4 (semillas {args.semilla_lote}..{args.semilla_lote + n - 1})\n\n"
            + tabla_md(["mecanismo", "misión cumplida", "salió sin oro (bloqueo)", "muertes", "acciones de riesgo",
                        "disparos", "esfuerzo medio/partida", "t medio/partida ms"], filas3)
            + f"\n\n(tiempo de cómputo del lote: {time.perf_counter() - t0:.1f} s)\n")
    print("Listo →", args.salida)
    print(md)
    print(open(os.path.join(args.salida, "comparacion_mecanismos.md"), encoding="utf-8").read())
    if args.lote:
        print(open(os.path.join(args.salida, "lote_aleatorio.md"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
