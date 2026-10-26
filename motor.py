"""motor.py — Módulo 3 (parte A): motor de inferencia proposicional escrito desde cero.

Dos mecanismos sobre la misma KB (wumpus_kb.BaseConocimiento), sin librerías de inferencia:

1) RESOLUCIÓN POR REFUTACIÓN  (completa para lógica proposicional)
   KB ⊨ α  ⇔  KB ∧ ¬α es insatisfacible  ⇔  de KB ∧ ¬α se deriva la cláusula vacía □.
   * Meta α = cláusula (disyunción de literales); ¬α = una cláusula unitaria por literal.
   * Selección de cláusulas: CONJUNTO DE SOPORTE. Sólo se resuelve una cláusula del soporte (¬α, los supuestos
     y sus resolventes) contra la KB o contra otra cláusula del soporte ya procesada. Así la búsqueda se dirige
     a la meta y se evita explorar toda la KB.
   * Orden: PREFERENCIA POR CLÁUSULAS CORTAS (cola de prioridad por longitud; las unitarias primero).
   * Base simplificada por RESOLUCIÓN UNITARIA (incremental): cada hecho nuevo (cláusula unitaria, observada o
     derivada) se resuelve con las cláusulas que contienen su complemento y elimina las que lo contienen (quedan
     subsumidas). Cada paso es un nodo de la prueba (aparece en las trazas como `uN`) y su costo se contabiliza
     como `mantenimiento`. Sin esto la búsqueda satura sobre cientos de cláusulas irrelevantes.
   * Símbolos LATENTES (B, H, R, S de una casilla): sus cláusulas "duermen" mientras no haya un hecho ni una meta
     que los mencione. Es la eliminación de Davis‑Putnam: todo resolvente sobre ellos es una tautología, así que
     omitirlos no cambia ninguna consecuencia que no los mencione. Se despiertan (de forma permanente) al
     observarse el símbolo o al consultarlo.
   * Podas: se descartan tautologías y resolventes SUBSUMIDOS (existe una cláusula igual o más corta contenida
     en él), por ejemplo cualquier resolvente que contenga un literal que ya es hecho de la KB.
   * Poda por longitud: se descartan los resolventes con más de `longitud_maxima` literales (por defecto 6). Es
     una concesión práctica DECLARADA: la cláusula "hay un Wumpus" (n² literales) cruzada con ¬P∨¬W genera miles de
     consecuencias válidas pero irrelevantes. Con la poda la búsqueda deja de ser completa en teoría; la traza
     marca `podadas` y una respuesta DESCONOCIDO con podas se reporta como inconclusa. Se valida contra el oráculo.
   * Condición de parada: (a) se deriva □ → DEMOSTRADO; (b) se agota el soporte (saturación) → NO es consecuencia;
     (c) se alcanza el tope de resoluciones → inconcluso, se responde DESCONOCIDO y se marca `agotado`.

2) ENCADENAMIENTO HACIA ADELANTE  (completo sólo para cláusulas de Horn; aquí es incompleto en general)
   Cada cláusula (l1 ∨ … ∨ lk) se lee como k reglas  ¬lj (j≠i)  →  li  (antecedente conjuntivo de literales
   positivos/negativos, conclusión un literal). Con los hechos conocidos (cláusulas unitarias) se dispara toda regla
   cuyo antecedente se cumple, hasta un punto fijo. Implementación por contadores: una cláusula dispara cuando
   le queda un solo literal no falsificado. NO sustituye a la resolución: no razona por casos (no deriva
   disyunciones ni conclusiones que dependan de elegir entre alternativas).

CONSULTAS trivaluadas: VERDADERO (KB ⊨ α), FALSO (KB ⊨ ¬α) o DESCONOCIDO (ninguna de las dos). Desconocido ≠ falso.
Si la KB es inconsistente, el motor no entrega conclusiones: devuelve DESCONOCIDO con `inconsistente=True`.

SUPUESTO DE MUNDO CERRADO SOBRE M. Mientras no se perciba el Grito, el Wumpus vive (sólo una flecha puede matarlo y
el agente oye siempre el Grito). Por eso `es_seguro` consulta con el supuesto ¬M; el supuesto aparece en la traza
y se retira solo al afirmarse M. Las consultas hay_pozo / hay_wumpus no lo usan.
"""
from __future__ import annotations

import heapq
import itertools
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from wumpus_kb import BaseConocimiento, M, negar, simbolo

RESOLUCION = "resolucion"
ENCADENAMIENTO = "encadenamiento"
METODOS = (RESOLUCION, ENCADENAMIENTO)


class Resultado(Enum):
    VERDADERO = "demostrado verdadero"
    FALSO = "demostrado falso"
    DESCONOCIDO = "desconocido"


# ---------------------------------------------------------------------------------------------- trazas
@dataclass
class Traza:
    consulta: str
    metodo: str
    resultado: Resultado = Resultado.DESCONOCIDO
    supuestos: tuple = ()
    premisas: list = field(default_factory=list)       # [(etiqueta, texto, categoría)] cláusulas de la KB usadas
    pasos: list = field(default_factory=list)           # líneas: resoluciones o reglas activadas
    conclusion: str = ""
    efecto: str = ""                                    # lo rellena quien usa la conclusión (agente)
    resoluciones: int = 0                               # resolventes calculados
    generadas: int = 0                                  # resolventes conservados
    subsumidas: int = 0                                 # resolventes descartados (tautología/subsumidos)
    podadas: int = 0                                    # resolventes descartados por exceder la longitud máxima
    activaciones: int = 0                               # reglas disparadas (encadenamiento)
    comprobaciones: int = 0                             # cláusulas examinadas (encadenamiento)
    tiempo: float = 0.0
    agotado: bool = False
    inconsistente: bool = False
    desde_memoria: bool = False
    partes: list = field(default_factory=list)          # trazas de las dos refutaciones (α y ¬α)

    @property
    def esfuerzo(self) -> int:
        """Unidad común de esfuerzo: resoluciones calculadas + reglas disparadas + cláusulas examinadas."""
        return self.resoluciones + self.activaciones + self.comprobaciones

    def texto(self, detalle: bool = True) -> str:
        enc = f"[{self.metodo}] {self.consulta} → {self.resultado.value}"
        if self.desde_memoria:
            enc += "  (resultado ya demostrado antes; se reutiliza)"
        lineas = [enc]
        if self.supuestos:
            lineas.append("  Supuestos: " + ", ".join(self.supuestos) + "  (mundo cerrado: sin Grito el Wumpus vive)")
        if self.inconsistente:
            lineas.append("  ¡KB INCONSISTENTE! No se aceptan conclusiones como evidencia de seguridad.")
        if detalle:
            if self.premisas:
                lineas.append("  Premisas usadas:")
                lineas += [f"    {e}: {t}   [{c}]" for e, t, c in self.premisas]
            if self.pasos:
                lineas.append("  Pasos:")
                lineas += [f"    {p}" for p in self.pasos]
        if self.conclusion:
            lineas.append("  Conclusión: " + self.conclusion)
        if self.efecto:
            lineas.append("  Efecto en la decisión: " + self.efecto)
        if self.metodo == RESOLUCION:
            lineas.append(f"  Esfuerzo: {self.resoluciones} resoluciones, {self.generadas} resolventes guardados, "
                          f"{self.subsumidas} descartados, {self.podadas} podados" + (", TOPE ALCANZADO (inconcluso)" if self.agotado else "")
                          + f", {self.tiempo * 1000:.2f} ms")
        else:
            lineas.append(f"  Esfuerzo: {self.activaciones} reglas disparadas, {self.comprobaciones} cláusulas "
                          f"examinadas, {self.tiempo * 1000:.2f} ms")
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.texto()


def _texto_clausula(c) -> str:
    return " ∨ ".join(sorted(c)) if c else "□"


def _simb(lit: str) -> str:
    return lit[1:] if lit.startswith("¬") else lit


# ---------------------------------------------------------------------------------------------- cierre (encadenamiento)
@dataclass
class _Cierre:
    version: int
    supuestos: tuple
    hechos: dict = field(default_factory=dict)          # literal → justificación
    contradicciones: list = field(default_factory=list)  # [(literal, texto)]
    activaciones: int = 0
    comprobaciones: int = 0
    tiempo: float = 0.0


class Motor:
    def __init__(self, kb: BaseConocimiento, limite_resoluciones: int = 5000, memoria: bool = True,
                 longitud_maxima: int = 6):
        self.kb = kb
        self.limite = limite_resoluciones
        self.longitud_maxima = longitud_maxima
        self.memoria = memoria
        self.registro: list[Traza] = []                  # todas las consultas (para métricas)
        self._cierres: dict = {}
        self._memoria: dict = {}                         # (literales, método, supuestos) → Traza demostrada
        self.eventos_contradiccion: list[str] = []
        # --- base de resolución: DAG de pruebas + cláusulas activas (simplificadas por resolución unitaria)
        self._nodos: list = []                           # id → (cláusula, padres, nombre)
        self._activas: dict[int, frozenset] = {}         # id → cláusula no unitaria vigente
        self._idx: dict[str, set] = defaultdict(set)     # literal → ids de cláusulas activas que lo contienen
        self._hechos: dict[str, int] = {}                # literal → id del nodo unitario
        self._vacia: int | None = None                   # nodo □ si la base se contradice
        self._n_sync = 0
        self._n_red = 0
        self._dormidas: dict[str, list] = defaultdict(list)   # símbolo latente → ids de nodos en espera
        self._m_asumida = False                          # ¬M integrada a la base (mundo cerrado)
        self.mant_resoluciones = 0                       # pasos de resolución unitaria de mantenimiento
        self.mant_tiempo = 0.0

    # ------------------------------------------------------------------ base simplificada (resolución unitaria)
    def _nodo(self, clausula: frozenset, padres, nombre: str) -> int:
        self._nodos.append((clausula, padres, nombre))
        return len(self._nodos) - 1

    def _reiniciar_base(self) -> None:
        self._nodos.clear(); self._activas.clear(); self._idx.clear(); self._hechos.clear()
        self._dormidas.clear(); self._vacia = None; self._n_sync = 0; self._n_red = 0
        self._memoria.clear()
        self._m_asumida = False

    def _sincronizar(self) -> None:
        """Incorpora a la base las cláusulas nuevas de la KB (la KB sólo crece). Mientras no se haya oído el Grito
        la base incluye el supuesto ¬M; al oírlo, la base se reconstruye una vez sin ese supuesto."""
        if self._m_asumida and self.kb.wumpus_muerto:
            self._reiniciar_base()
        if self._n_sync == len(self.kb.clausulas) and (self._m_asumida or self.kb.wumpus_muerto):
            return
        t0 = time.perf_counter()
        pendientes: list[int] = []
        if not self._m_asumida and not self.kb.wumpus_muerto:
            self._m_asumida = True
            pendientes.append(self._nodo(frozenset([negar(M)]), ("supuesto", negar(M)), "sup¬M"))
        for numero in range(self._n_sync, len(self.kb.clausulas)):
            c = frozenset(self.kb.clausulas[numero])
            pendientes.append(self._nodo(c, ("kb", numero + 1), f"c{numero + 1}"))
        self._n_sync = len(self.kb.clausulas)
        for nid in pendientes:
            self._insertar(nid)
        self.mant_tiempo += time.perf_counter() - t0

    @staticmethod
    def _latente(lit: str) -> bool:
        return _simb(lit)[:2] in ("B_", "H_", "R_", "S_")

    def _despertar(self, simbolos) -> None:
        """Activa (de forma permanente) las cláusulas dormidas de los símbolos dados."""
        t0 = time.perf_counter()
        for s in simbolos:
            for nid in self._dormidas.pop(s, []):
                self._insertar(nid, despertando=True)
        self.mant_tiempo += time.perf_counter() - t0

    def _insertar(self, nid: int, despertando: bool = False) -> None:
        """Reduce la cláusula con los hechos conocidos; si queda unitaria, es un hecho nuevo que se propaga."""
        cola = [nid]
        while cola:
            nid = cola.pop()
            c = self._nodos[nid][0]
            if any(l in self._hechos for l in c):          # contiene un hecho: subsumida, se descarta
                continue
            while True:
                falso = next((l for l in sorted(c) if negar(l) in self._hechos), None)
                if falso is None:
                    break
                u = self._hechos[negar(falso)]
                r = c - {falso}
                self._n_red += 1
                self.mant_resoluciones += 1
                nid = self._nodo(r, ("res", nid, u, falso), f"u{self._n_red}")
                c = r
            if not c:
                if self._vacia is None:
                    self._vacia = nid
                continue
            if len(c) > 1:                                  # ¿contiene un símbolo latente aún sin hecho ni meta?
                lat = next((_simb(l) for l in sorted(c) if self._latente(l)), None)
                if lat is not None and not despertando:
                    self._dormidas[lat].append(nid)
                    continue
            if len(c) == 1:
                (lit,) = c
                if lit in self._hechos:
                    continue
                if negar(lit) in self._hechos:              # dos hechos opuestos → □
                    self._n_red += 1
                    self.mant_resoluciones += 1
                    v = self._nodo(frozenset(), ("res", nid, self._hechos[negar(lit)], lit), f"u{self._n_red}")
                    if self._vacia is None:
                        self._vacia = v
                    continue
                self._hechos[lit] = nid
                if self._latente(lit):                      # el símbolo ya fue observado: despertar sus cláusulas
                    for d in self._dormidas.pop(_simb(lit), []):
                        cola.append(d)
                for k in list(self._idx.get(lit, ())):      # cláusulas que contienen el hecho: subsumidas
                    self._quitar(k)
                for k in list(self._idx.get(negar(lit), ())):   # cláusulas con el complemento: se reducen
                    ck = self._activas[k]
                    self._quitar(k)
                    self._n_red += 1
                    self.mant_resoluciones += 1
                    cola.append(self._nodo(ck - {negar(lit)}, ("res", k, nid, negar(lit)), f"u{self._n_red}"))
            else:
                self._activas[nid] = c
                for l in c:
                    self._idx[l].add(nid)

    def _quitar(self, k: int) -> None:
        for l in self._activas.pop(k):
            self._idx[l].discard(k)

    # ------------------------------------------------------------------ ENCADENAMIENTO HACIA ADELANTE
    def _cierre(self, supuestos: tuple = ()) -> _Cierre:
        """Punto fijo de las reglas de la KB (con caché por versión de la KB y supuestos)."""
        clave = (len(self.kb.clausulas), supuestos)
        if clave in self._cierres:
            return self._cierres[clave]
        t0 = time.perf_counter()
        cl = self.kb.clausulas
        cierre = _Cierre(clave[0], supuestos)
        ocurre: dict[str, list[int]] = defaultdict(list)
        for k, c in enumerate(cl):
            for lit in c:
                ocurre[lit].append(k)
        restantes = [len(c) for c in cl]
        satisfecha = [False] * len(cl)
        cola: list[str] = []

        def afirmar(lit: str, just) -> None:
            if lit in cierre.hechos:
                return
            if negar(lit) in cierre.hechos:
                cierre.contradicciones.append((lit, f"{lit} y {negar(lit)} quedan afirmados a la vez"))
                return
            cierre.hechos[lit] = just
            cola.append(lit)

        for s in supuestos:
            afirmar(s, ("supuesto",))
        for k, c in enumerate(cl):
            if len(c) == 1:
                afirmar(c[0], ("unitaria", k + 1))
        while cola:
            lit = cola.pop(0)
            for k in ocurre[lit]:
                satisfecha[k] = True
            for k in ocurre[negar(lit)]:
                cierre.comprobaciones += 1
                if satisfecha[k]:
                    continue
                restantes[k] -= 1
                if restantes[k] == 0:
                    cierre.contradicciones.append((cl[k][0], f"c{k + 1} queda con todos sus literales falsos"))
                elif restantes[k] == 1:
                    libre = [x for x in cl[k] if negar(x) not in cierre.hechos]
                    if len(libre) == 1 and libre[0] not in cierre.hechos:
                        concl = libre[0]
                        ante = [negar(x) for x in cl[k] if x != concl]
                        cierre.activaciones += 1
                        afirmar(concl, ("regla", k + 1, tuple(ante)))
                    elif not libre:
                        cierre.contradicciones.append((cl[k][0], f"c{k + 1} queda con todos sus literales falsos"))
        cierre.tiempo = time.perf_counter() - t0
        self._cierres[clave] = cierre
        return cierre

    def _explicar_hecho(self, cierre: _Cierre, lit: str, traza: Traza, vistos: set) -> None:
        """Reconstruye hacia atrás la cadena de reglas que justifica `lit` (en orden de aplicación)."""
        if lit in vistos:
            return
        vistos.add(lit)
        just = cierre.hechos[lit]
        if just[0] == "supuesto":
            traza.pasos.append(f"supuesto: {lit}")
        elif just[0] == "unitaria":
            n = just[1]
            traza.premisas.append((f"c{n}", _texto_clausula(self.kb.clausulas[n - 1]),
                                   self.kb.info[self.kb.clausulas[n - 1]].categoria))
        else:
            _, n, ante = just
            for a in ante:
                self._explicar_hecho(cierre, a, traza, vistos)
            c = self.kb.clausulas[n - 1]
            traza.premisas.append((f"c{n}", _texto_clausula(c), self.kb.info[c].categoria))
            regla = (" ∧ ".join(ante) if ante else "⊤") + " → " + lit
            traza.pasos.append(f"regla de c{n}: {regla}")

    def _sup_fc(self, supuestos: tuple) -> tuple:
        """Supuestos efectivos del encadenamiento: los pedidos más ¬M (mundo cerrado) mientras no haya Grito."""
        return supuestos if self.kb.wumpus_muerto else tuple(supuestos) + (negar(M),)

    def _consultar_encadenamiento(self, literal: str, supuestos: tuple) -> Traza:
        supuestos = self._sup_fc(supuestos)
        t0 = time.perf_counter()
        nuevo = (len(self.kb.clausulas), supuestos) not in self._cierres
        cierre = self._cierre(supuestos)
        tr = Traza(literal, ENCADENAMIENTO, supuestos=supuestos)
        if nuevo:                                         # el esfuerzo se carga a quien obliga a recalcular
            tr.activaciones, tr.comprobaciones = cierre.activaciones, cierre.comprobaciones
        else:
            tr.desde_memoria = False
        if cierre.contradicciones:
            tr.inconsistente = True
            tr.conclusion = "contradicción: " + cierre.contradicciones[0][1]
        elif literal in cierre.hechos:
            tr.resultado = Resultado.VERDADERO
            self._explicar_hecho(cierre, literal, tr, set())
            tr.conclusion = f"{literal} es un hecho del cierre"
        elif negar(literal) in cierre.hechos:
            tr.resultado = Resultado.FALSO
            self._explicar_hecho(cierre, negar(literal), tr, set())
            tr.conclusion = f"{negar(literal)} es un hecho del cierre; luego {literal} es falso"
        else:
            tr.conclusion = f"ni {literal} ni {negar(literal)} se alcanzan con las reglas (punto fijo)"
        tr.tiempo = time.perf_counter() - t0 + (cierre.tiempo if nuevo else 0.0)
        return tr

    # ------------------------------------------------------------------ RESOLUCIÓN POR REFUTACIÓN
    def _refutar(self, meta: tuple, supuestos: tuple, etiqueta: str) -> Traza:
        """Intenta demostrar KB ∧ supuestos ⊨ (meta = disyunción de literales) por refutación (conjunto de soporte)."""
        t0 = time.perf_counter()
        self._sincronizar()
        self._despertar({_simb(l) for l in meta if self._latente(l)} |
                        {_simb(s) for s in supuestos if self._latente(s)})
        tr = Traza(etiqueta, RESOLUCION, supuestos=supuestos)
        n_base = len(self._nodos)
        procesadas: dict[str, list] = defaultdict(list)    # literal → [(cláusula, id)] del soporte ya procesadas
        generadas: dict[str, list] = defaultdict(list)     # literal → [cláusula] todo el soporte (subsunción)
        cola: list = []
        orden = itertools.count()

        def nueva(c: frozenset, padres, nombre: str) -> int:
            nid = self._nodo(c, padres, nombre)
            for lit in c:
                generadas[lit].append(c)
            heapq.heappush(cola, (len(c), next(orden), nid))
            return nid

        def subsumida(r: frozenset) -> bool:
            for lit in r:
                if lit in self._hechos:
                    return True
                for k in self._idx.get(lit, ()):
                    d = self._activas[k]
                    if len(d) <= len(r) and d <= r:
                        return True
                for d in generadas.get(lit, ()):
                    if len(d) <= len(r) and d <= r:
                        return True
            return False

        vacia = self._vacia
        if vacia is None:
            for k, lit in enumerate(meta, 1):               # ¬α
                nueva(frozenset([negar(lit)]), ("meta", lit), f"¬meta{k}")
            for k, s in enumerate(supuestos, 1):            # hipótesis
                nueva(frozenset([s]), ("supuesto", s), f"sup{k}")
        while cola and vacia is None:
            _, _, nid = heapq.heappop(cola)
            c = self._nodos[nid][0]
            for lit in sorted(c):
                comp = negar(lit)
                socios = []
                if comp in self._hechos:
                    socios.append((frozenset([comp]), self._hechos[comp]))
                socios += [(self._activas[k], k) for k in sorted(self._idx.get(comp, ()))]
                socios += list(procesadas.get(comp, ()))
                for d, did in socios:
                    if tr.resoluciones >= self.limite:
                        tr.agotado = True
                        break
                    r = (c - {lit}) | (d - {comp})
                    tr.resoluciones += 1
                    if len(r) > self.longitud_maxima:
                        tr.podadas += 1
                        continue
                    if any(negar(x) in r for x in r) or subsumida(r):
                        tr.subsumidas += 1
                        continue
                    tr.generadas += 1
                    rid = nueva(r, ("res", nid, did, lit), f"r{tr.generadas}")
                    if not r:
                        vacia = rid
                        break
                if tr.agotado or vacia is not None:
                    break
            if tr.agotado:
                break
            for l2 in c:
                procesadas[l2].append((c, nid))
        tr.tiempo = time.perf_counter() - t0
        if vacia is not None:
            tr.resultado = Resultado.VERDADERO
            self._reconstruir(tr, vacia)
        del self._nodos[n_base:]                            # el soporte de esta consulta no persiste
        return tr

    def _reconstruir(self, tr: Traza, raiz: int) -> None:
        """Extrae del DAG sólo la prueba de la cláusula `raiz` (premisas de la KB y pasos, en orden)."""
        usados: set[int] = set()
        pila = [raiz]
        while pila:
            nid = pila.pop()
            if nid in usados:
                continue
            usados.add(nid)
            padres = self._nodos[nid][1]
            if padres[0] == "res":
                pila += [padres[1], padres[2]]
        kb_usadas = []
        for nid in sorted(usados):
            c, padres, nombre = self._nodos[nid]
            if padres[0] == "kb":
                kb_usadas.append(padres[1])
            elif padres[0] == "meta":
                tr.pasos.append(f"{nombre}: ({_texto_clausula(c)})   [negación de la meta {padres[1]}]")
            elif padres[0] == "supuesto":
                tr.pasos.append(f"{nombre}: ({_texto_clausula(c)})   [supuesto de mundo cerrado]"
                                if padres[1] == negar(M) else f"{nombre}: ({_texto_clausula(c)})   [supuesto]")
                if padres[1] == negar(M) and "¬M" not in tr.supuestos:
                    tr.supuestos = tr.supuestos + (negar(M),)
            else:
                _, a, b, lit = padres
                nom = "□" if not c else nombre
                tr.pasos.append(f"{nom} = res({self._nodos[a][2]}, {self._nodos[b][2]}) sobre {_simb(lit)}"
                                f"  →  ({_texto_clausula(c)})")
        for n in sorted(kb_usadas):
            cl = self.kb.clausulas[n - 1]
            tr.premisas.append((f"c{n}", _texto_clausula(cl), self.kb.info[cl].categoria))

    # ------------------------------------------------------------------ consistencia
    def contradicciones(self) -> list[str]:
        """Contradicciones detectadas por resolución unitaria sobre la KB (lista vacía = ninguna detectada).
        Cada contradicción nueva se anota, con su prueba de □, en `eventos_contradiccion` (bitácora)."""
        self._sincronizar()
        if self._vacia is None:
            return []
        tr = Traza("□", RESOLUCION)
        self._reconstruir(tr, self._vacia)
        texto = "KB inconsistente: □ derivada por resolución unitaria\n" + "\n".join("  " + p for p in tr.pasos) + \
                "\n  de las cláusulas: " + ", ".join(f"c{n}" for n, _, _ in [(e[1:], 0, 0) for e, _, _ in tr.premisas])
        if texto not in self.eventos_contradiccion:
            self.eventos_contradiccion.append(texto)
        return [texto]

    def es_consistente(self) -> bool:
        return not self.contradicciones()

    # ------------------------------------------------------------------ consulta general
    def consultar_clausula(self, literales, metodo: str = RESOLUCION, supuestos: tuple = ()) -> tuple[Resultado, Traza]:
        """¿KB ⊨ (l1 ∨ … ∨ lk)?  → VERDADERO si se demuestra; FALSO si se demuestra la negación (todos los li falsos);
        DESCONOCIDO en otro caso.  Con encadenamiento sólo se reconocen disyunciones con algún literal-hecho."""
        literales = tuple(literales)
        etiqueta = " ∨ ".join(literales)
        if metodo not in METODOS:
            raise ValueError(f"Método desconocido: {metodo!r}")
        clave = (literales, metodo, supuestos)
        self._sincronizar()                                  # primero: un Grito nuevo invalida la memoria
        if self.memoria and clave in self._memoria:
            previa = self._memoria[clave]
            if not self.contradicciones():
                tr = Traza(etiqueta, metodo, previa.resultado, supuestos, list(previa.premisas), list(previa.pasos),
                           previa.conclusion, desde_memoria=True)
                self.registro.append(tr)
                return tr.resultado, tr
        inconsistente = bool(self.contradicciones())
        if inconsistente:
            tr = Traza(etiqueta, metodo, supuestos=supuestos, inconsistente=True,
                       conclusion="la KB es inconsistente; " + "; ".join(self.contradicciones()[:2]))
            self.registro.append(tr)
            return Resultado.DESCONOCIDO, tr

        if metodo == ENCADENAMIENTO:
            if len(literales) == 1:
                tr = self._consultar_encadenamiento(literales[0], supuestos)
            else:
                supuestos = self._sup_fc(supuestos)
                cierre = self._cierre(supuestos)
                tr = Traza(etiqueta, metodo, supuestos=supuestos)
                if any(l in cierre.hechos for l in literales):
                    tr.resultado = Resultado.VERDADERO
                    lit = next(l for l in literales if l in cierre.hechos)
                    self._explicar_hecho(cierre, lit, tr, set())
                    tr.conclusion = f"el disyuntivo se cumple porque {lit} es un hecho"
                elif all(negar(l) in cierre.hechos for l in literales):
                    tr.resultado = Resultado.FALSO
                    for l in literales:
                        self._explicar_hecho(cierre, negar(l), tr, set())
                    tr.conclusion = "todos los literales son falsos"
                else:
                    tr.conclusion = "las reglas no alcanzan para decidir la disyunción (se necesita razonar por casos)"
        else:
            neg = tuple(negar(l) for l in literales)
            a = self._refutar(literales, supuestos, etiqueta)                      # ¿KB ⊨ α?
            tr = a
            if a.resultado is Resultado.VERDADERO:
                tr.conclusion = f"□ derivada de KB ∧ ¬({etiqueta}): KB ⊨ {etiqueta}"
            else:
                b = self._refutar(neg, supuestos, "¬(" + etiqueta + ")")           # ¿KB ⊨ ¬α?
                tr = Traza(etiqueta, RESOLUCION, supuestos=supuestos)
                for campo in ("resoluciones", "generadas", "subsumidas", "podadas", "tiempo"):
                    setattr(tr, campo, getattr(a, campo) + getattr(b, campo))
                tr.agotado = a.agotado or b.agotado
                tr.partes = [a, b]
                if b.resultado is Resultado.VERDADERO:
                    tr.resultado = Resultado.FALSO
                    tr.premisas, tr.pasos = b.premisas, b.pasos
                    tr.conclusion = f"□ derivada de KB ∧ ({etiqueta}): KB ⊨ ¬({etiqueta})"
                else:
                    tr.conclusion = (f"ni ({etiqueta}) ni su negación se demuestran: "
                                     + ("se alcanzó el tope de resoluciones (inconcluso)" if tr.agotado
                                        else "el soporte se saturó sin derivar □ pero hubo podas por longitud "
                                             f"({tr.podadas}): inconcluso" if tr.podadas
                                        else "el soporte se saturó sin derivar □ (no es consecuencia)"))
        if self.memoria and tr.resultado is not Resultado.DESCONOCIDO:
            self._memoria[clave] = tr
        self.registro.append(tr)
        return tr.resultado, tr

    def consultar(self, literal: str, metodo: str = RESOLUCION, supuestos: tuple = ()) -> tuple[Resultado, Traza]:
        """Consulta trivaluada de un literal. Devuelve (Resultado, Traza)."""
        return self.consultar_clausula((literal,), metodo, supuestos)

    # ------------------------------------------------------------------ las seis consultas obligatorias
    def es_seguro(self, i: int, j: int, metodo: str = RESOLUCION) -> tuple[Resultado, Traza]:
        """VERDADERO: sin pozo y sin Wumpus vivo (demostrado). FALSO: hay pozo o Wumpus vivo (demostrado).
        DESCONOCIDO: no se puede asegurar ni lo uno ni lo otro."""
        return self.consultar(simbolo("S", i, j), metodo)

    def hay_pozo(self, i: int, j: int, metodo: str = RESOLUCION) -> tuple[Resultado, Traza]:
        return self.consultar(simbolo("P", i, j), metodo)

    def hay_wumpus(self, i: int, j: int, metodo: str = RESOLUCION) -> tuple[Resultado, Traza]:
        """VERDADERO: el Wumpus está (o estaba, si ya murió) en (i,j)."""
        return self.consultar(simbolo("W", i, j), metodo)

    def casillas_seguras(self, metodo: str = RESOLUCION) -> list[tuple[int, int]]:
        """Casillas demostradas seguras."""
        return [c for c in self.kb.casillas() if self.es_seguro(*c, metodo)[0] is Resultado.VERDADERO]

    def casillas_peligrosas(self, metodo: str = RESOLUCION) -> list[tuple[int, int]]:
        """Casillas demostradas peligrosas (pozo o Wumpus vivo)."""
        return [c for c in self.kb.casillas() if self.es_seguro(*c, metodo)[0] is Resultado.FALSO]

    def casillas_sospechosas(self, metodo: str = RESOLUCION) -> list[tuple[int, int]]:
        """Casillas NO visitadas con peligro posible: no demostradas seguras ni demostradas peligrosas.
        (Las demostradas peligrosas se piden con casillas_peligrosas().)"""
        visitadas = self.kb.casillas_visitadas
        return [c for c in self.kb.casillas()
                if c not in visitadas and self.es_seguro(*c, metodo)[0] is Resultado.DESCONOCIDO]

    def explicacion_de_consulta(self, i: int, j: int, metodo: str = RESOLUCION) -> str:
        """Explicación legible de lo que se sabe de (i,j): seguridad, pozo y Wumpus con sus trazas."""
        partes = [f"=== Explicación para la casilla ({i},{j}) con {metodo} ==="]
        for nombre, f in (("es_seguro", self.es_seguro), ("hay_pozo", self.hay_pozo), ("hay_wumpus", self.hay_wumpus)):
            r, t = f(i, j, metodo)
            partes.append(f"{nombre}({i},{j}) = {r.value}\n" + t.texto())
        return "\n\n".join(partes)

    # ------------------------------------------------------------------ métricas
    def metricas(self) -> dict:
        """Totales de todo lo consultado hasta ahora."""
        reg = self.registro
        nuevas = [t for t in reg if not t.desde_memoria]
        return {
            "consultas": len(reg),
            "desde_memoria": len(reg) - len(nuevas),
            "verdadero": sum(t.resultado is Resultado.VERDADERO for t in reg),
            "falso": sum(t.resultado is Resultado.FALSO for t in reg),
            "desconocido": sum(t.resultado is Resultado.DESCONOCIDO for t in reg),
            "resoluciones": sum(t.resoluciones for t in nuevas),
            "activaciones": sum(t.activaciones for t in nuevas),
            "comprobaciones": sum(t.comprobaciones for t in nuevas),
            "esfuerzo": sum(t.esfuerzo for t in nuevas) + self.mant_resoluciones,
            "mantenimiento": self.mant_resoluciones,
            "tiempo_s": sum(t.tiempo for t in nuevas) + self.mant_tiempo,
            "agotadas": sum(t.agotado for t in reg),
            "contradicciones": len(self.eventos_contradiccion),
        }
