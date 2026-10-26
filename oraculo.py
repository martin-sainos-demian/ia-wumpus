"""oraculo.py — Verdad de referencia por enumeración de modelos. SOLO PARA PRUEBAS Y EVALUACIÓN.

Dado lo observado, enumera todos los mundos posibles y calcula lo que se DEDUCE de verdad.
Sirve para comprobar que la inferencia del proyecto (resolución / encadenamiento) es correcta
(no deduce de más) y completa (no deja sin deducir lo que sí se deduce). Es exponencial: solo para 4×4.

Mundos posibles (mismos axiomas que la KB): cualquier subconjunto de casillas ≠ (1,1) con pozos;
exactamente un Wumpus ≠ (1,1); con `exclusion=True`, ninguna casilla tiene pozo y Wumpus a la vez;
las casillas visitadas no tienen peligros.
"""
from entorno import INICIO, vecinas


def consecuencias(n, observaciones, wumpus_vivo=True, exclusion=True):
    """observaciones: [((i,j), percepciones)] de casillas visitadas.
    Si wumpus_vivo=False el Wumpus ya murió: ya no es peligro y el hedor no se usa.
    Devuelve dict: seguras, sospechosas, pozo_cierto, pozo_posible, wumpus_cierto (casilla o None),
    wumpus_posible, n_modelos, inconsistente."""
    celdas = [(i, j) for j in range(1, n + 1) for i in range(1, n + 1)]
    libres = [c for c in celdas if c != INICIO]
    bit = {c: 1 << k for k, c in enumerate(libres)}
    visitadas = {c for c, _ in observaciones}
    prohibidos = sum(bit[c] for c in visitadas if c in bit)
    restr = [(sum(bit[v] for v in vecinas(n, c) if v in bit), "Brisa" in p) for c, p in observaciones]

    modelos_pozo = [m for m in range(1 << len(libres))
                    if not m & prohibidos and all(bool(m & mk) == b for mk, b in restr)]

    if wumpus_vivo:
        candidatos = [w for w in libres if w not in visitadas and all(
            (w in vecinas(n, c)) == ("Hedor" in p) for c, p in observaciones)]
    else:
        candidatos = [None]

    en_alguno, en_todos, total, wumpus_ok = 0, (1 << len(libres)) - 1, 0, set()
    peligro_todos = (1 << len(libres)) - 1          # casillas peligrosas (pozo o Wumpus vivo) en TODOS los modelos
    for w in candidatos:
        sub = modelos_pozo if (w is None or not exclusion) else [m for m in modelos_pozo if not m & bit[w]]
        if not sub:
            continue
        if w is not None:
            wumpus_ok.add(w)
        total += len(sub)
        for m in sub:
            en_alguno |= m
            en_todos &= m
            peligro_todos &= m | (bit[w] if w is not None else 0)
    if total == 0:
        return {"inconsistente": True, "n_modelos": 0}

    pozo_posible = {c for c in libres if en_alguno & bit[c]}
    pozo_cierto = {c for c in libres if en_todos & bit[c]}
    seguras = {c for c in celdas if c not in pozo_posible and c not in wumpus_ok}
    return {"inconsistente": False, "n_modelos": total,
            "seguras": seguras, "sospechosas": set(celdas) - seguras,
            "peligro_cierto": {c for c in libres if peligro_todos & bit[c]},
            "pozo_cierto": pozo_cierto, "pozo_posible": pozo_posible,
            "wumpus_cierto": next(iter(wumpus_ok)) if len(wumpus_ok) == 1 else None,
            "wumpus_posible": wumpus_ok}
