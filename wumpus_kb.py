"""wumpus_kb.py — Módulo 2: base de conocimiento (KB) proposicional del Mundo de Wumpus, en FNC.

NOTACIÓN. Todo símbolo es TIPO_i_j (i = columna, j = fila, desde 1), salvo M que no lleva casilla.
    P_i_j  hay un pozo en (i,j)                      W_i_j  el Wumpus está (o estaba) en (i,j)
    O_i_j  el oro está en (i,j)
    B_i_j  se percibe brisa en (i,j)                 H_i_j  se percibe hedor en (i,j)
    R_i_j  se percibe resplandor en (i,j)            V_i_j  (i,j) fue visitada
    S_i_j  (i,j) es SEGURA: sin pozo y sin Wumpus vivo
    M      el Wumpus está muerto (se afirma al percibir el Grito)
Un literal es un símbolo o su negación ("¬P_1_2"). Una cláusula es una disyunción de literales, guardada
como tupla ordenada. La KB es la conjunción de sus cláusulas.

AXIOMAS (reglas estáticas) y su conversión a FNC. Con a, b, … = casillas adyacentes a i:
    A1 inicio seguro      ¬P_1_1 ∧ ¬W_1_1                          ⇒ dos cláusulas unitarias
    A2 brisa              B_i ⇔ P_a ∨ P_b ∨ …                      ⇒ (¬B_i ∨ P_a ∨ P_b ∨ …) y (¬P_a ∨ B_i) por cada a
    A3 hedor              H_i ⇔ W_a ∨ W_b ∨ …                      ⇒ (¬H_i ∨ W_a ∨ W_b ∨ …) y (¬W_a ∨ H_i) por cada a
    A4 resplandor         R_i ⇔ O_i       (MISMA casilla)          ⇒ (¬R_i ∨ O_i) y (¬O_i ∨ R_i)
    A5 un solo Wumpus     W_1_1 ∨ … ∨ W_n_n   y   ¬(W_a ∧ W_b)     ⇒ una cláusula larga y (¬W_a ∨ ¬W_b) por cada par
    A6 un peligro/casilla ¬(P_i ∧ W_i)                              ⇒ (¬P_i ∨ ¬W_i)
                          (que no haya "dos pozos en una casilla" ya lo impone usar una sola proposición P_i)
    A7 seguridad          S_i ⇔ ¬P_i ∧ (¬W_i ∨ M)                  ⇒ (¬S_i ∨ ¬P_i), (¬S_i ∨ ¬W_i ∨ M),
                                                                     (S_i ∨ P_i ∨ W_i), (S_i ∨ P_i ∨ ¬M)
    A5' un solo oro (opcional, unicidad_oro=True)  igual que A5 con O.

WUMPUS MUERTO (decisión D1). W_i conserva su significado ("está o estaba en i"). Al percibir el Grito se
afirma M y, desde entonces, NO se registra más el hedor (presencia ni ausencia) ni ¬W en las casillas
visitadas: sin Wumpus vivo ya no son informativos y el agente puede pisar con vida la casilla donde yace.
La KB sigue siendo monótona (nunca se retira una cláusula) y consistente. M nunca se afirma como falso:
mientras no se perciba el Grito, M queda DESCONOCIDO y por eso S_i exige demostrar ¬W_i.

TRES CLASES DE CLÁUSULAS (campo `origen`): "regla" (axiomas), "observacion" (percepciones y visitas)
y "derivado" (conclusiones del motor, guardadas con sus premisas).
"""
from collections.abc import Iterable
from dataclasses import dataclass, field

PERCEPCIONES = ("Brisa", "Hedor", "Resplandor", "Golpe", "Grito")
_NORMALIZAR = {p.lower(): p for p in PERCEPCIONES}

# Categorías de cláusulas
CAT_INICIO = "A1 inicio seguro"
CAT_BRISA = "A2 brisa ⇔ pozo adyacente"
CAT_HEDOR = "A3 hedor ⇔ Wumpus adyacente"
CAT_RESPLANDOR = "A4 resplandor ⇔ oro aquí"
CAT_WUMPUS = "A5 un solo Wumpus"
CAT_ORO = "A5' un solo oro"
CAT_PELIGRO = "A6 un peligro por casilla"
CAT_SEGURA = "A7 seguridad"
CAT_OBSERVACION = "Observación"
CAT_DERIVADO = "Derivado"

M = "M"                                            # el Wumpus está muerto


def simbolo(nombre: str, i: int, j: int) -> str:
    return f"{nombre}_{i}_{j}"


def negar(literal: str) -> str:
    return literal[1:] if literal.startswith("¬") else "¬" + literal


@dataclass
class Info:
    """Datos de cada cláusula almacenada."""
    numero: int
    origen: str                                    # "regla" | "observacion" | "derivado"
    categoria: str
    turno: int | None = None
    premisas: tuple = ()                           # derivados: números de las cláusulas usadas
    metodo: str | None = None                      # derivados: "resolucion" | "encadenamiento"
    detalle: str = ""


@dataclass
class Actualizacion:
    """Resultado de traducir las percepciones de una casilla."""
    turno: int
    casilla: tuple
    percepciones: list
    nuevas: list = field(default_factory=list)      # [(cláusula, motivo)] agregadas
    repetidas: list = field(default_factory=list)   # [(cláusula, motivo)] que ya estaban
    ignoradas: list = field(default_factory=list)   # [(percepción, motivo)] sin cláusulas
    total_antes: int = 0
    total_despues: int = 0


class BaseConocimiento:
    def __init__(self, ancho: int = 4, alto: int | None = None, unicidad_oro: bool = False):
        self.ancho = ancho
        self.alto = ancho if alto is None else alto
        self.unicidad_oro = unicidad_oro
        self.clausulas: list[tuple[str, ...]] = []                   # en orden de inserción
        self.info: dict[tuple[str, ...], Info] = {}
        self._vistas: set[tuple[int, int]] = set()
        self._con_resplandor: set[tuple[int, int]] = set()          # casillas donde se vio el oro
        self._indice_clausulas: set[tuple[str, ...]] = set()
        self.actualizaciones: list[Actualizacion] = []
        self.agregar_reglas_generales()

    # ------------------------------------------------------------ geometría (coordenadas desde 1)
    def valida(self, i: int, j: int) -> bool:
        return 1 <= i <= self.ancho and 1 <= j <= self.alto

    def adyacentes(self, i: int, j: int) -> list[tuple[int, int]]:
        candidatos = [(i, j + 1), (i, j - 1), (i - 1, j), (i + 1, j)]
        return [(x, y) for x, y in candidatos if self.valida(x, y)]

    def casillas(self) -> list[tuple[int, int]]:
        return [(i, j) for j in range(1, self.alto + 1) for i in range(1, self.ancho + 1)]

    # ------------------------------------------------------------ agregar cláusulas
    def agregar_clausula(self, *literales: str, origen: str = "regla", categoria: str = "",
                         turno: int | None = None, premisas: tuple = (), metodo: str | None = None,
                         detalle: str = "") -> bool:
        """Agrega una cláusula (tupla ordenada, sin repetidos). Devuelve True si era nueva.
        Se descartan las tautologías (X ∨ ¬X) y las cláusulas repetidas."""
        conjunto = set(literales)
        if any(negar(l) in conjunto for l in conjunto):
            return False
        clausula = tuple(sorted(conjunto))
        if clausula in self._indice_clausulas:
            return False
        self._indice_clausulas.add(clausula)
        self.clausulas.append(clausula)
        self.info[clausula] = Info(len(self.clausulas), origen, categoria, turno, premisas, metodo, detalle)
        return True

    def agregar_derivado(self, literal: str, premisas: tuple, metodo: str, turno: int | None = None,
                         detalle: str = "") -> bool:
        """Guarda una conclusión del motor como cláusula unitaria derivada (con las premisas usadas)."""
        return self.agregar_clausula(literal, origen="derivado", categoria=CAT_DERIVADO, turno=turno,
                                     premisas=premisas, metodo=metodo, detalle=detalle)

    # ------------------------------------------------------------ axiomas (reglas estáticas)
    def _regla(self, *literales: str, categoria: str) -> None:
        self.agregar_clausula(*literales, origen="regla", categoria=categoria)

    def agregar_reglas_equivalencia(self, percepcion: str, peligro: str, categoria: str) -> None:
        """X_i ⇔ ⋁ peligro_vecinas  ⇒  (¬X_i ∨ peligros…) y (X_i ∨ ¬peligro_a) por cada vecina a."""
        for i, j in self.casillas():
            p = simbolo(percepcion, i, j)
            peligros = [simbolo(peligro, x, y) for x, y in self.adyacentes(i, j)]
            self._regla(negar(p), *peligros, categoria=categoria)
            for q in peligros:
                self._regla(p, negar(q), categoria=categoria)

    def agregar_unicidad(self, tipo: str, categoria: str) -> None:
        """Exactamente uno: al menos uno, y no hay dos distintos."""
        celdas = self.casillas()
        self._regla(*[simbolo(tipo, i, j) for i, j in celdas], categoria=categoria)
        for k, (i1, j1) in enumerate(celdas):
            for i2, j2 in celdas[k + 1:]:
                self._regla(negar(simbolo(tipo, i1, j1)), negar(simbolo(tipo, i2, j2)), categoria=categoria)

    def agregar_reglas_generales(self) -> None:
        self._regla(negar(simbolo("P", 1, 1)), categoria=CAT_INICIO)                    # A1
        self._regla(negar(simbolo("W", 1, 1)), categoria=CAT_INICIO)
        self.agregar_reglas_equivalencia("B", "P", CAT_BRISA)                           # A2
        self.agregar_reglas_equivalencia("H", "W", CAT_HEDOR)                           # A3
        for i, j in self.casillas():                                                    # A4  R_i ⇔ O_i
            self._regla(negar(simbolo("R", i, j)), simbolo("O", i, j), categoria=CAT_RESPLANDOR)
            self._regla(negar(simbolo("O", i, j)), simbolo("R", i, j), categoria=CAT_RESPLANDOR)
        self.agregar_unicidad("W", CAT_WUMPUS)                                          # A5
        if self.unicidad_oro:
            self.agregar_unicidad("O", CAT_ORO)                                         # A5'
        for i, j in self.casillas():                                                    # A6
            self._regla(negar(simbolo("P", i, j)), negar(simbolo("W", i, j)), categoria=CAT_PELIGRO)
        for i, j in self.casillas():                                                    # A7
            s, p, w = simbolo("S", i, j), simbolo("P", i, j), simbolo("W", i, j)
            self._regla(negar(s), negar(p), categoria=CAT_SEGURA)
            self._regla(negar(s), negar(w), M, categoria=CAT_SEGURA)
            self._regla(s, p, w, categoria=CAT_SEGURA)
            self._regla(s, p, negar(M), categoria=CAT_SEGURA)

    # ------------------------------------------------------------ percepciones → observaciones
    @property
    def wumpus_muerto(self) -> bool:
        """True si M ya está en la KB (percibido o derivado)."""
        return (M,) in self._indice_clausulas

    def traducir_percepciones(self, coordenadas: tuple[int, int], percepciones: Iterable[str],
                              registrar_ausencias: bool = True, turno: int | None = None) -> Actualizacion:
        """Traduce ((i,j), [percepciones]) a observaciones y las agrega a la KB (nunca borra nada).

        Presentes: Brisa → B_i_j, Hedor → H_i_j, Resplandor → R_i_j.  Ausentes: ¬B, ¬H, ¬R (Brisa, Hedor y
        Resplandor siempre son observables en una casilla visitada).  Además: V_i_j y ¬P_i_j (el agente sigue
        vivo) y, mientras el Wumpus viva, ¬W_i_j.
        Sin cláusulas: Golpe (indica un muro, no describe la casilla).  Grito → M (Wumpus muerto; desde entonces
        no se registran hedor ni ¬W).  Sin Resplandor en una casilla donde ya se vio el oro: lo recogió el agente."""
        try:
            i, j = coordenadas
        except (TypeError, ValueError):
            raise ValueError(f"Coordenadas inválidas: {coordenadas!r}; se esperaba (i,j)")
        if not (isinstance(i, int) and isinstance(j, int) and self.valida(i, j)):
            raise ValueError(f"Coordenadas fuera del mundo {self.ancho}×{self.alto}: {(i, j)}")
        if isinstance(percepciones, str):
            raise ValueError("Las percepciones deben ir en una lista, p. ej. ['Brisa']")
        recibidas = set()
        for p in percepciones:
            clave = str(p).strip().lower()
            if clave not in _NORMALIZAR:
                raise ValueError(f"Percepción desconocida: {p!r}. Válidas: {', '.join(PERCEPCIONES)}")
            recibidas.add(_NORMALIZAR[clave])

        turno = turno if turno is not None else len(self.actualizaciones) + 1
        act = Actualizacion(turno, (i, j), sorted(recibidas, key=PERCEPCIONES.index), total_antes=len(self.clausulas))

        def observar(literal: str, motivo: str) -> None:
            nueva = self.agregar_clausula(literal, origen="observacion", categoria=CAT_OBSERVACION, turno=turno,
                                          detalle=motivo)
            (act.nuevas if nueva else act.repetidas).append(((literal,), motivo))

        self._vistas.add((i, j))
        if "Grito" in recibidas:
            observar(M, "se oyó el Grito: el Wumpus está muerto")
        observar(simbolo("V", i, j), f"({i},{j}) visitada")
        observar(negar(simbolo("P", i, j)), f"el agente sigue vivo en ({i},{j}): no hay pozo")
        if self.wumpus_muerto:
            act.ignoradas.append(("¬W", "el Wumpus ya murió: el agente puede pisar su casilla con vida"))
        else:
            observar(negar(simbolo("W", i, j)), f"el agente sigue vivo en ({i},{j}): no hay Wumpus")

        if "Brisa" in recibidas:
            observar(simbolo("B", i, j), "hay Brisa")
        elif registrar_ausencias:
            observar(negar(simbolo("B", i, j)), "no hay Brisa (ausencia)")

        if self.wumpus_muerto:
            act.ignoradas.append(("Hedor" if "Hedor" in recibidas else "ausencia de Hedor",
                                  "con el Wumpus muerto el hedor no se registra"))
        elif "Hedor" in recibidas:
            observar(simbolo("H", i, j), "hay Hedor")
        elif registrar_ausencias:
            observar(negar(simbolo("H", i, j)), "no hay Hedor (ausencia)")

        if "Resplandor" in recibidas:
            self._con_resplandor.add((i, j))
            observar(simbolo("R", i, j), "hay Resplandor")
        elif (i, j) in self._con_resplandor:
            act.ignoradas.append(("ausencia de Resplandor", "el oro de esta casilla ya fue recogido"))
        elif registrar_ausencias:
            observar(negar(simbolo("R", i, j)), "no hay Resplandor (ausencia)")

        if "Golpe" in recibidas:
            act.ignoradas.append(("Golpe", "indica un muro al moverse; no describe la casilla"))
        act.total_despues = len(self.clausulas)
        self.actualizaciones.append(act)
        return act

    def registrar_flecha_sin_efecto(self, celdas, turno: int | None = None) -> list:
        """La flecha recorrió `celdas` sin dar el Grito: si el Wumpus vivía, no estaba en ninguna de ellas.
        Agrega ¬W para cada una (si el Wumpus ya había muerto no aporta nada y no se agrega)."""
        if self.wumpus_muerto:
            return []
        nuevas = []
        for (i, j) in celdas:
            if self.agregar_clausula(negar(simbolo("W", i, j)), origen="observacion", categoria=CAT_OBSERVACION,
                                     turno=turno, detalle="la flecha pasó por aquí sin dar el Grito"):
                nuevas.append((i, j))
        return nuevas

    # ------------------------------------------------------------ consultar y mostrar (sin inferencia)
    def __len__(self) -> int:
        return len(self.clausulas)

    def __contains__(self, clausula) -> bool:
        return tuple(sorted(set(clausula))) in self._indice_clausulas

    def valor_directo(self, literal: str) -> bool | None:
        """True/False si el literal (o su negación) está como cláusula UNITARIA; None si no. NO es inferencia."""
        if (literal,) in self._indice_clausulas:
            return True
        if (negar(literal),) in self._indice_clausulas:
            return False
        return None

    def contar(self, origen: str | None = None) -> int:
        return sum(1 for i in self.info.values() if origen is None or i.origen == origen)

    def resumen(self) -> dict[str, int]:
        r: dict[str, int] = {}
        for i in self.info.values():
            r[i.categoria] = r.get(i.categoria, 0) + 1
        return r

    def clausulas_de(self, origen: str | None = None, categoria: str | None = None, simbolo_: str | None = None,
                     solo_unitarias: bool = False) -> list[tuple[str, ...]]:
        res = []
        for c in self.clausulas:
            inf = self.info[c]
            if origen and inf.origen != origen:
                continue
            if categoria and inf.categoria != categoria:
                continue
            if solo_unitarias and len(c) != 1:
                continue
            if simbolo_ and not any(l.lstrip("¬") == simbolo_ for l in c):
                continue
            res.append(c)
        return res

    def hechos(self) -> dict[str, bool]:
        """Hechos conocidos (cláusulas unitarias): {símbolo: True/False}."""
        h = {}
        for c in self.clausulas_de(solo_unitarias=True):
            (l,) = c
            h[l.lstrip("¬")] = not l.startswith("¬")
        return h

    def contradicciones_directas(self) -> list[str]:
        """Símbolos afirmados y negados a la vez como cláusulas unitarias (revisión barata)."""
        unidades = {c[0] for c in self.clausulas if len(c) == 1}
        return sorted(l for l in unidades if not l.startswith("¬") and negar(l) in unidades)

    def formatear(self, clausula: tuple[str, ...], detalle: bool = False) -> str:
        inf = self.info[clausula]
        texto = " ∨ ".join(clausula) if clausula else "□"
        base = f"c{inf.numero}: ({texto})"
        if detalle:
            base += f"   [{inf.origen}: {inf.categoria}" + (f", turno {inf.turno}" if inf.turno else "") + "]"
        return base

    def mostrar(self, incluir_reglas: bool = True, origen: str | None = None, detalle: bool = False) -> str:
        lineas = []
        for c in self.clausulas:
            inf = self.info[c]
            if (not incluir_reglas and inf.origen == "regla") or (origen and inf.origen != origen):
                continue
            lineas.append(self.formatear(c, detalle))
        return "\n".join(lineas) if lineas else "KB vacia"

    def imprimir(self, incluir_reglas: bool = False) -> None:
        print(self.mostrar(incluir_reglas))

    def cantidad_clausulas(self) -> int:
        return len(self.clausulas)

    def texto_hechos(self, ancho: int = 76, sangria: str = "    ") -> str:
        import textwrap
        lits = [(s if v else negar(s)) for s, v in self.hechos().items()]
        return textwrap.fill("  ".join(lits), width=ancho, initial_indent=sangria,
                             subsequent_indent=sangria) if lits else sangria + "(ninguno)"

    def guardar_base(self, ruta: str = "kb.txt") -> str:
        """Escribe toda la KB, agrupada por categoría y con el origen de cada cláusula."""
        lineas = [f"BASE DE CONOCIMIENTO {self.ancho}×{self.alto}: {len(self)} cláusulas en FNC", ""]
        for cat, k in self.resumen().items():
            lineas.append(f"# {cat}  [{k}]")
            lineas += [self.formatear(c) for c in self.clausulas_de(categoria=cat)]
            lineas.append("")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))
        return ruta

    @property
    def casillas_visitadas(self) -> set[tuple[int, int]]:
        return set(self._vistas)
