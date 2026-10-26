"""jugar.py — Juega una partida con el agente lógico y muestra la bitácora de cada ciclo.

    python jugar.py mundos/m3_wumpus_custodia_oro.json
    python jugar.py mundos/m1_sin_peligro_inicial.json --metodo encadenamiento
    python jugar.py --n 4 --semilla 13 --sin-trazas
    python jugar.py mundos/m5_bloqueo_brisa_inicial.json --politica arriesgar
"""
import argparse

from agente import Agente
from entorno import Entorno
from motor import ENCADENAMIENTO, RESOLUCION


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mundo", nargs="?", help="archivo .json de un mundo (si se omite se genera con --n/--semilla)")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--semilla", type=int, default=None)
    ap.add_argument("--metodo", choices=[RESOLUCION, ENCADENAMIENTO], default=RESOLUCION)
    ap.add_argument("--politica", choices=["salir", "arriesgar"], default="salir", help="qué hacer ante un bloqueo")
    ap.add_argument("--sin-trazas", action="store_true", help="no imprimir las pruebas de cada decisión")
    ap.add_argument("--kb", metavar="ARCHIVO", help="guardar la KB final (kb.txt)")
    args = ap.parse_args()

    e = Entorno.cargar(args.mundo) if args.mundo else Entorno(args.n, semilla=args.semilla)
    print("MAPA (vista del EVALUADOR; el agente no lo conoce):\n" + e.dibujar() + "\n")
    a = Agente(e.vista_agente(), args.metodo, politica_bloqueo=args.politica)
    resumen = a.jugar()
    print(a.texto_bitacora(con_trazas=not args.sin_trazas))
    print("\n" + "=" * 70)
    print(f"RESULTADO: {e.resultado}")
    if a.bloqueo:
        print(f"BLOQUEO (no es un fallo lógico): {a.razon_bloqueo}")
    for k in ("ciclos", "movimientos", "casillas_visitadas", "disparos", "entradas_riesgo", "consultas", "verdadero",
              "falso", "desconocido", "esfuerzo", "contradicciones", "clausulas_kb"):
        print(f"  {k:20s} {resumen[k]}")
    print(f"  {'tiempo de inferencia':20s} {resumen['tiempo_s'] * 1000:.1f} ms")
    if args.kb:
        print("KB guardada en", a.kb.guardar_base(args.kb))


if __name__ == "__main__":
    main()
