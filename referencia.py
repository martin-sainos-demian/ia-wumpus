"""referencia.py — Explorador de REFERENCIA para evaluar mundos y agentes. NO es el agente del proyecto.

Usa el oráculo (enumeración de modelos) y por eso solo sirve en 4×4. Se usa para:
  * comprobar que cada mundo de prueba cumple la categoría para la que fue elegido, y
  * dar una línea base: lo que un razonador PERFECTO y prudente (sin riesgos) logra en cada mundo.
El agente del proyecto debe razonar con su propia KB, resolución y encadenamiento, sin importar este módulo.
"""
from collections import deque
from entorno import Entorno, DIRECCIONES, vecinas, INICIO
from oraculo import consecuencias

def direccion(a, b):
    """Dirección del paso entre dos casillas vecinas."""
    d = (b[0]-a[0], b[1]-a[1]); return next(k for k, v in DIRECCIONES.items() if v == d)

def camino(n, ini, meta, permitidas):
    prev, q = {ini: None}, deque([ini])
    while q:
        c = q.popleft()
        if c == meta:
            r = []
            while c is not None: r.append(c); c = prev[c]
            return r[::-1]
        for v in vecinas(n, c):
            if v not in prev and (v in permitidas or v == meta):
                prev[v] = c; q.append(v)
    return None

def explorar(entorno, tope=80):
    """Explora solo por casillas demostradas seguras (según el oráculo), dispara si localiza al Wumpus y no hay otra salida.
    Devuelve un dict de métricas: exito, bloqueo, movs, retro, brisas, hedores, pozo_cierto, wumpus_cierto, disparo..."""
    v = entorno.vista_agente(); n = v.n
    obs, vivo = {}, True
    r = dict(exito=False, bloqueo=False, movs=0, retro=0, brisas=0, hedores=0, pozo_cierto=False,
             wumpus_cierto=False, disparo=False, hedor_inicio=False, brisa_inicio=False, pasos_inicio=None, resultado=None)
    visitadas = set()
    def ir(dest, permit):
        ruta = camino(n, v.posicion, dest, permit)
        for a, b in zip(ruta, ruta[1:]):
            if b in visitadas: r['retro'] += 1 if not v.tiene_oro else 0
            v.actuar("avanzar", direccion(a, b)); r['movs'] += 1
            visitadas.add(v.posicion)
    for _ in range(tope):
        if v.terminado: break
        pos, perc = v.observar(); visitadas.add(pos)
        if pos not in obs:
            obs[pos] = set(p for p in perc if p in ("Brisa", "Hedor", "Resplandor"))
            r['brisas'] += "Brisa" in perc; r['hedores'] += "Hedor" in perc
            if pos == INICIO: r['hedor_inicio'] = "Hedor" in perc; r['brisa_inicio'] = "Brisa" in perc
        if "Grito" in perc: vivo = False
        if "Resplandor" in perc:
            v.actuar("recoger")
            ir(INICIO, visitadas); v.actuar("salir"); break
        c = consecuencias(n, list(obs.items()), vivo)
        if c["inconsistente"]: r['resultado'] = "inconsistente"; return r
        if c["pozo_cierto"]: r['pozo_cierto'] = True
        if c["wumpus_cierto"] and vivo: r['wumpus_cierto'] = True
        objetivos = [t for t in c["seguras"] if t not in visitadas]
        if objetivos:
            # el más cercano pasando por casillas visitadas
            mejor = None
            for t in objetivos:
                for u in vecinas(n, t):
                    if u in visitadas:
                        p = camino(n, v.posicion, u, visitadas)
                        if p and (mejor is None or len(p) < len(mejor[0])): mejor = (p, t)
            if mejor is None: r['bloqueo'] = True; break
            ir(mejor[1], visitadas | {mejor[1]})
            continue
        if c["wumpus_cierto"] and vivo and v.flechas:
            w = c["wumpus_cierto"]
            cand = [u for u in visitadas if (u[0] == w[0] or u[1] == w[1]) and u != w]
            if cand:
                u = min(cand, key=lambda u: len(camino(n, v.posicion, u, visitadas)))
                ir(u, visitadas)
                d = "arriba" if w[1] > u[1] else "abajo" if w[1] < u[1] else "derecha" if w[0] > u[0] else "izquierda"
                v.actuar("disparar", d); r['disparo'] = True
                continue
        r['bloqueo'] = True; break
    r['exito'] = entorno.resultado == "exito"; r['resultado'] = entorno.resultado
    return r
