"""Utilidades SOLO PARA PRUEBAS: exploración aleatoria que evita casillas letales (usa el mapa verdadero)
y la asignación de verdad del mundo real para comprobar la KB. El agente y la KB no importan este módulo."""
import random

from entorno import DIRECCIONES, Entorno, vecinas
from wumpus_kb import BaseConocimiento, M, simbolo


def asignacion_real(e: Entorno) -> dict:
    """Valor de verdad de TODOS los símbolos en el mundo real (R≡oro original, H/B estáticos, M si el Wumpus murió)."""
    v, n = e.verdad(), e.n
    pozos, w, oro = v["pozos"], v["wumpus"], v["oro"]
    a = {M: not v["wumpus_vivo"]}
    for j in range(1, n + 1):
        for i in range(1, n + 1):
            c = (i, j)
            a[simbolo("P", i, j)] = c in pozos
            a[simbolo("W", i, j)] = c == w
            a[simbolo("O", i, j)] = c == oro
            a[simbolo("R", i, j)] = c == oro
            a[simbolo("B", i, j)] = any(x in pozos for x in vecinas(n, c))
            a[simbolo("H", i, j)] = w in vecinas(n, c)
            a[simbolo("S", i, j)] = (c not in pozos) and (c != w or not v["wumpus_vivo"])
    return a


def clausula_verdadera(clausula, a: dict) -> bool:
    return any((not a[l[1:]]) if l.startswith("¬") else a[l] for l in clausula if l.lstrip("¬") in a)


def clausulas_falsas(kb: BaseConocimiento, e: Entorno) -> list:
    """Cláusulas de la KB que el mundo real falsifica (debe ser siempre []). Se ignoran V_i_j (no son del mundo)."""
    a = asignacion_real(e)
    malas = []
    for c in kb.clausulas:
        if all(l.lstrip("¬").startswith("V_") for l in c):
            continue
        if not clausula_verdadera(c, a):
            malas.append(c)
    return malas


def paso_aleatorio(vista, e: Entorno, rng: random.Random, p_disparo: float = 0.15):
    """Una acción aleatoria sin morir: nunca pisa una casilla letal. Devuelve la acción hecha o None."""
    pos = vista.posicion
    opciones = []
    for acc, d in vista.acciones_validas():
        if acc == "avanzar":
            di, dj = DIRECCIONES[d]
            dest = (pos[0] + di, pos[1] + dj)
            if 1 <= dest[0] <= e.n and 1 <= dest[1] <= e.n and e.casilla_peligrosa(dest):
                continue
            opciones.append((acc, d))
        elif acc == "disparar" and rng.random() < p_disparo:
            opciones.append((acc, d))
        elif acc == "recoger":
            opciones.append((acc, d))
    if not opciones:
        return None
    acc, d = rng.choice(opciones)
    vista.actuar(acc, d)
    return acc, d


def explorar_con_kb(e: Entorno, kb: BaseConocimiento, pasos: int, rng: random.Random, p_disparo: float = 0.15,
                    al_paso=None):
    """Recorre el mundo al azar traduciendo cada observación a la KB. `al_paso(k)` se llama tras cada actualización."""
    vista = e.vista_agente()
    kb.traducir_percepciones(*vista.observar())
    if al_paso:
        al_paso(0)
    for k in range(1, pasos + 1):
        if vista.terminado or paso_aleatorio(vista, e, rng, p_disparo) is None:
            break
        if vista.terminado:
            break
        kb.traducir_percepciones(*vista.observar())
        if al_paso:
            al_paso(k)
    return vista
