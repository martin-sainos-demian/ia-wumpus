"""agente.py

El agente NO conoce el mapa: sólo usa la interfaz `VistaAgente` (observar / acciones_validas / actuar). No importa
`entorno`, `oraculo` ni `referencia` (lo verifica una prueba).

CICLO (cada iteración deja una entrada en la bitácora):
    percepción → traducción a la KB → inferencia → decisión → acción → nuevo estado

POLÍTICA (en este orden de prioridad)
  1. KB inconsistente  → no se acepta ninguna conclusión como evidencia de seguridad: sólo se retrocede por
                         casillas ya pisadas (experiencia propia) hasta (1,1) y se sale.
  2. Resplandor y sin oro → recoger.
  3. Con oro           → volver a (1,1) por casillas DEMOSTRADAS seguras y salir.
  4. Casillas no visitadas demostradas seguras → ir a la más cercana (camino por casillas demostradas seguras).
  5. Sin movimientos seguros → disparar SÓLO si la KB demuestra que el Wumpus está en una línea de tiro
     (KB ⊨ W_c1 ∨ … ∨ W_ck para las casillas de esa línea) y hay flecha; si no estoy alineado, voy a una casilla
     segura desde la que sí lo esté.
  6. Si nada de lo anterior → BLOQUEO: no es un fallo de la lógica (nada seguro es demostrable con lo percibido);
     se reporta y, según `politica_bloqueo`, se vuelve a (1,1) y se sale ("salir") o se arriesga ("arriesgar":
     se entra a la casilla sospechosa más cercana; cada entrada así cuenta como acción de riesgo).
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from motor import ENCADENAMIENTO, RESOLUCION, Motor, Resultado
from wumpus_kb import BaseConocimiento, simbolo

V, F, D = Resultado.VERDADERO, Resultado.FALSO, Resultado.DESCONOCIDO
INICIO = (1, 1)
ORDEN = ("arriba", "derecha", "abajo", "izquierda")          # desempate determinista
_DELTA = {"arriba": (0, 1), "abajo": (0, -1), "izquierda": (-1, 0), "derecha": (1, 0)}


def direccion_hacia(a, b) -> str:
    d = (b[0] - a[0], b[1] - a[1])
    return next(n for n, v in _DELTA.items() if v == d)


@dataclass
class Ciclo:
    n: int
    turno_kb: int
    posicion: tuple
    percepciones: list
    kb_nuevas: list = field(default_factory=list)          # observaciones nuevas (texto)
    kb_total: int = 0
    seguras: list = field(default_factory=list)
    seguras_nuevas: list = field(default_factory=list)
    sospechosas: list = field(default_factory=list)
    peligrosas: list = field(default_factory=list)
    pozos: list = field(default_factory=list)              # demostrados
    wumpus: list = field(default_factory=list)             # demostrado
    contradicciones: list = field(default_factory=list)
    decision: str = ""
    razon: str = ""
    accion: tuple | None = None
    traza_decisiva: str = ""
    nuevo_estado: str = ""
    consultas: int = 0
    esfuerzo: int = 0
    tiempo: float = 0.0


class Agente:
    def __init__(self, vista, metodo: str = RESOLUCION, politica_bloqueo: str = "salir", max_ciclos: int = 300,
                 limite_resoluciones: int = 5000, memoria: bool = True, kb: BaseConocimiento | None = None):
        if politica_bloqueo not in ("salir", "arriesgar"):
            raise ValueError("politica_bloqueo debe ser 'salir' o 'arriesgar'")
        self.vista = vista
        self.metodo = metodo
        self.politica_bloqueo = politica_bloqueo
        self.max_ciclos = max_ciclos
        self.kb = kb or BaseConocimiento(vista.n)                    # una KB nueva por partida
        self.motor = Motor(self.kb, limite_resoluciones=limite_resoluciones, memoria=memoria)
        self.bitacora: list[Ciclo] = []
        self.visitadas: set = set()
        self.bloqueo = False
        self.razon_bloqueo = ""
        self.disparos = 0
        self.movimientos = 0
        self.entradas_riesgo = 0
        self.acciones_hechas: list = []
        self._previas: set = set()
        self._ultimo_disparo = None
        self._plan_disparo = None

    # ------------------------------------------------------------------ utilidades de búsqueda
    def _ruta(self, origen, permitidas: set, objetivos: set):
        """BFS por casillas permitidas hasta el objetivo más cercano. Devuelve la lista de casillas (sin el origen)."""
        if origen in objetivos:
            return []
        previo = {origen: None}
        cola = deque([origen])
        while cola:
            c = cola.popleft()
            for nombre in ORDEN:
                d = _DELTA[nombre]
                v = (c[0] + d[0], c[1] + d[1])
                if v in previo or v not in permitidas:
                    continue
                previo[v] = c
                if v in objetivos:
                    ruta = [v]
                    while previo[ruta[-1]] != origen:
                        ruta.append(previo[ruta[-1]])
                    return ruta[::-1]
                cola.append(v)
        return None

    def _linea(self, desde, nombre):
        d = _DELTA[nombre]
        c, res = (desde[0] + d[0], desde[1] + d[1]), []
        while self.kb.valida(*c):
            res.append(c)
            c = (c[0] + d[0], c[1] + d[1])
        return res

    # ------------------------------------------------------------------ inferencia
    def _inferir(self, pos, entrada: Ciclo):
        kb, mo, m = self.kb, self.motor, self.metodo
        visitadas = kb.casillas_visitadas
        frontera = {a for c in visitadas for a in kb.adyacentes(*c)} - visitadas
        candidatas = sorted(visitadas | frontera, key=lambda c: (c[1], c[0]))
        estado, trazas = {}, {}
        for c in candidatas:
            r, tr = mo.es_seguro(*c, m)
            estado[c], trazas[c] = r, tr
        seguras = {c for c in candidatas if estado[c] is V}
        peligrosas = {c for c in candidatas if estado[c] is F}
        sospechosas = {c for c in frontera if estado[c] is D}
        pozos, wumpus = [], []
        for c in sorted(sospechosas | peligrosas, key=lambda c: (c[1], c[0])):
            if mo.hay_pozo(*c, m)[0] is V:
                pozos.append(c)
            if mo.hay_wumpus(*c, m)[0] is V:
                wumpus.append(c)
        entrada.seguras = sorted(seguras)
        entrada.seguras_nuevas = sorted(seguras - self._previas)
        entrada.sospechosas = sorted(sospechosas)
        entrada.peligrosas = sorted(peligrosas)
        entrada.pozos, entrada.wumpus = pozos, wumpus
        self._previas = set(seguras)
        return seguras, sospechosas, peligrosas, trazas

    # ------------------------------------------------------------------ disparo justificado
    def _buscar_disparo(self, pos, seguras):
        if self.kb.wumpus_muerto or self.vista.flechas <= 0 or not any(
                self.kb.valor_directo(simbolo("H", *c)) for c in self.kb.casillas_visitadas):
            return None                          # sin flecha, Wumpus ya muerto o ningún hedor que lo localice
        alcanzables = []
        for s in seguras:
            ruta = self._ruta(pos, seguras, {s})
            if ruta is not None:
                alcanzables.append((len(ruta), s[1], s[0], s))
        for _, _, _, s in sorted(alcanzables):
            for nombre in ORDEN:
                linea = self._linea(s, nombre)
                if not linea:
                    continue
                r, tr = self.motor.consultar_clausula([simbolo("W", *c) for c in linea], self.metodo)
                if r is V:
                    return s, nombre, linea, tr
        return None

    # ------------------------------------------------------------------ decisión
    def _decidir(self, pos, per, seguras, sospechosas, peligrosas, inconsistente):
        """Devuelve (tipo, accion, razon, traza). accion = (nombre, direccion) o None si no hay acción posible."""
        visitadas = self.kb.casillas_visitadas
        tiene_oro = self.vista.tiene_oro

        if inconsistente:
            self.bloqueo, self.razon_bloqueo = True, "KB inconsistente: no se acepta ninguna conclusión como evidencia"
            return self._regresar(pos, visitadas, "KB inconsistente: retrocedo por casillas ya pisadas y salgo")
        if "Resplandor" in per and not tiene_oro:
            return "recoger", ("recoger", None), "hay Resplandor en la casilla actual: el oro está aquí", None
        if tiene_oro:
            return self._regresar(pos, seguras, "tengo el oro: vuelvo a (1,1) por casillas demostradas seguras")

        objetivos = {c for c in seguras if c not in visitadas}
        if objetivos:
            ruta = self._ruta(pos, seguras, objetivos)
            if ruta:
                destino = ruta[-1]
                return ("explorar", ("avanzar", direccion_hacia(pos, ruta[0])),
                        f"voy hacia {destino}, casilla no visitada demostrada segura (ruta de {len(ruta)} pasos)",
                        self._traza_texto(destino))
        # sin movimientos seguros nuevos
        plan = self._buscar_disparo(pos, seguras)
        if plan:
            s, nombre, linea, tr = plan
            if s == pos:
                self.disparos += 1
                self._ultimo_disparo = linea
                return ("disparar", ("disparar", nombre),
                        f"la KB demuestra que el Wumpus está en {linea[0]}…{linea[-1]} (hacia {nombre}) y tengo flecha",
                        tr.texto(detalle=not tr.desde_memoria))
            ruta = self._ruta(pos, seguras, {s})
            return ("alinear", ("avanzar", direccion_hacia(pos, ruta[0])),
                    f"voy a {s} para disparar hacia {nombre}: la KB demuestra que el Wumpus está en esa línea",
                    tr.texto(detalle=not tr.desde_memoria))
        # bloqueo
        if not self.bloqueo:
            self.bloqueo = True
            self.razon_bloqueo = (f"sin casillas seguras sin visitar y sin disparo justificado; "
                                  f"{len(sospechosas)} casillas con peligro posible, {len(peligrosas)} con peligro demostrado")
        if self.politica_bloqueo == "arriesgar" and sospechosas and not self.vista.tiene_oro:
            ruta = self._ruta(pos, seguras | sospechosas, set(sospechosas))
            if ruta:
                return ("arriesgar", ("avanzar", direccion_hacia(pos, ruta[0])),
                        f"BLOQUEO: asumo riesgo y entro a {ruta[-1]}, la sospechosa más cercana (peligro posible, no demostrado)",
                        self._traza_texto(ruta[-1]))
        return self._regresar(pos, seguras, "BLOQUEO: nada seguro es demostrable con lo percibido; vuelvo a (1,1) y salgo",
                              tipo="bloqueo")

    def _regresar(self, pos, permitidas, razon, tipo="regresar"):
        if pos == INICIO:
            return "salir", ("salir", None), razon + " — ya estoy en (1,1): salgo", None
        ruta = self._ruta(pos, set(permitidas) | {INICIO}, {INICIO})
        if not ruta:
            return "sin_accion", None, razon + " — pero no hay ruta segura a (1,1)", None
        return tipo, ("avanzar", direccion_hacia(pos, ruta[0])), razon + f" (faltan {len(ruta)} pasos)", None

    def _traza_texto(self, c):
        for t in reversed(self.motor.registro):
            if t.consulta == simbolo("S", *c) and t.metodo == self.metodo:
                return t.texto(detalle=not t.desde_memoria)
        return None

    # ------------------------------------------------------------------ un ciclo completo
    def ciclo(self) -> Ciclo:
        vista, kb, mo = self.vista, self.kb, self.motor
        n = len(self.bitacora) + 1
        t0 = time.perf_counter()
        m0, e0 = len(mo.registro), mo.metricas()["esfuerzo"]
        pos, per = vista.observar()                                              # 1. percepción
        if self._ultimo_disparo and "Grito" not in per:                          # flecha sin efecto → conocimiento
            kb.registrar_flecha_sin_efecto(self._ultimo_disparo, n)
        self._ultimo_disparo = None
        entrada = Ciclo(n, n, pos, list(per))
        self.visitadas.add(pos)
        act = kb.traducir_percepciones(pos, per, turno=n)                        # 2. KB
        entrada.kb_nuevas = [c[0] for c, _ in act.nuevas]
        entrada.kb_total = len(kb)
        contr = mo.contradicciones()                                             # 3. inferencia
        entrada.contradicciones = contr
        if contr:
            seguras, sosp, pel, _ = set(self.visitadas), set(), set(), {}
            self._previas = set(seguras)
        else:
            seguras, sosp, pel, _ = self._inferir(pos, entrada)
        tipo, accion, razon, traza = self._decidir(pos, per, seguras, sosp, pel, bool(contr))   # 4. decisión
        entrada.decision, entrada.razon, entrada.traza_decisiva = tipo, razon, traza or ""
        entrada.accion = accion
        if accion is not None:                                                   # 5. acción
            if tipo == "arriesgar":                                              # entrada a casilla no demostrada segura
                self.entradas_riesgo += 1
            vista.actuar(*accion)
            self.acciones_hechas.append(accion)
            if accion[0] == "avanzar":
                self.movimientos += 1
        entrada.nuevo_estado = (f"posición {vista.posicion}, flechas {vista.flechas}, "
                                f"oro {'sí' if vista.tiene_oro else 'no'}" + (", partida terminada" if vista.terminado else ""))
        met = mo.metricas()
        entrada.consultas = len(mo.registro) - m0
        entrada.esfuerzo = met["esfuerzo"] - e0
        entrada.tiempo = time.perf_counter() - t0
        self.bitacora.append(entrada)
        return entrada

    def jugar(self, al_ciclo=None) -> dict:
        while not self.vista.terminado and len(self.bitacora) < self.max_ciclos:
            c = self.ciclo()
            if al_ciclo:
                al_ciclo(self, c)
            if c.accion is None:
                break
        return self.resumen()

    # ------------------------------------------------------------------ salida
    def resumen(self) -> dict:
        met = self.motor.metricas()
        return {"metodo": self.metodo, "ciclos": len(self.bitacora), "movimientos": self.movimientos,
                "casillas_visitadas": len(self.kb.casillas_visitadas), "disparos": self.disparos,
                "bloqueo": self.bloqueo, "razon_bloqueo": self.razon_bloqueo,
                "entradas_riesgo": self.entradas_riesgo, "tiene_oro": self.vista.tiene_oro,
                "contradicciones": len(self.motor.eventos_contradiccion),
                "wumpus_muerto": self.kb.wumpus_muerto, "clausulas_kb": len(self.kb), **met}

    @staticmethod
    def texto_ciclo(c: Ciclo, con_trazas: bool = True) -> str:
        f = lambda xs: ", ".join(map(str, xs)) if xs else "—"
        l = [f"── Ciclo {c.n} " + "─" * 60,
             f"Percepción   : en {c.posicion} → {f(c.percepciones) if c.percepciones else 'nada'}",
             f"KB           : +{len(c.kb_nuevas)} observaciones ({f(c.kb_nuevas)}); total {c.kb_total} cláusulas"]
        if c.contradicciones:
            l.append("CONTRADICCIÓN: " + c.contradicciones[0].splitlines()[0])
        l += [f"Inferencia   : seguras {f(c.seguras)}" + (f"  (nuevas: {f(c.seguras_nuevas)})" if c.seguras_nuevas else ""),
              f"               sospechosas {f(c.sospechosas)} · peligro demostrado {f(c.peligrosas)}",
              f"               pozo demostrado en {f(c.pozos)} · Wumpus demostrado en {f(c.wumpus)}",
              f"Decisión     : [{c.decision}] {c.razon}",
              f"Acción       : {c.accion[0] + (' ' + c.accion[1] if c.accion[1] else '') if c.accion else '(ninguna)'}",
              f"Nuevo estado : {c.nuevo_estado}",
              f"Esfuerzo     : {c.consultas} consultas, {c.esfuerzo} operaciones de inferencia, {c.tiempo * 1000:.1f} ms"]
        if con_trazas and c.traza_decisiva:
            l.append("Traza decisiva:\n" + "\n".join("   " + x for x in c.traza_decisiva.splitlines()))
        return "\n".join(l)

    def texto_bitacora(self, con_trazas: bool = True) -> str:
        return "\n\n".join(self.texto_ciclo(c, con_trazas) for c in self.bitacora)
