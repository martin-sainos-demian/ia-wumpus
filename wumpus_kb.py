from collections.abc import Iterable

PERCEPCIONES = ("B", "S", "R")
ELEMENTOS = ("P", "W", "G")

log_file =  "kb.txt"


def simbolo(nombre: str, i: int, j: int) -> str:
    return f"{nombre}_{i}_{j}"


def negar(literal: str) -> str:
    return literal[1:] if literal.startswith("¬") else "¬" + literal


class BaseConocimiento:
    def __init__(self, ancho: int = 4, alto: int | None = None):
        self.ancho = ancho
        self.alto = ancho if alto is None else alto
        self.clausulas: list[tuple[str, ...]] = []
        self._vistas: set[tuple[int, int]] = set()
        self._indice_clausulas: set[tuple[str, ...]] = set()
        self.agregar_reglas_generales()

    def valida(self, i: int, j: int) -> bool:
        return 0 <= i < self.ancho and 0 <= j < self.alto

    def adyacentes(self, i: int, j: int) -> list[tuple[int, int]]:
        candidatos = [(i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)]
        return [(x, y) for x, y in candidatos if self.valida(x, y)]

    def agregar_clausula(self, *literales: str) -> None:
        clausula = tuple(sorted(set(literales)))
        if not clausula:
            clausula = ()
        if clausula not in self._indice_clausulas:
            self._indice_clausulas.add(clausula)
            self.clausulas.append(clausula)

    def agregar_reglas_equivalencia(self, percepcion: str, peligro: str) -> None:
        for i in range(self.ancho):
            for j in range(self.alto):
                vecinos = self.adyacentes(i, j)
                p = simbolo(percepcion, i, j)
                peligros = [simbolo(peligro, x, y) for x, y in vecinos]
                self.agregar_clausula(negar(p), *peligros)

                for q in peligros:
                    self.agregar_clausula(p, negar(q))

    def agregar_reglas_generales(self) -> None:
        self.agregar_reglas_equivalencia("B", "P")
        self.agregar_reglas_equivalencia("S", "W")
        self.agregar_reglas_equivalencia("R", "G")

    def traducir_percepciones(self, coordenadas: tuple[int, int], percepciones: Iterable[str], registrar_ausencias: bool = True) -> None:
        i, j = coordenadas
        if not self.valida(i, j):
            raise ValueError(f"Error coordenadas: {(i, j)}; ")

        recibidas = {str(p).strip().upper() for p in percepciones}
        desconocidas = recibidas - set(PERCEPCIONES)
        if desconocidas:
            raise ValueError(f"Error percepciones: {sorted(desconocidas)}")

        self._vistas.add((i, j))
        self.agregar_clausula(simbolo("V", i, j))

        for p in PERCEPCIONES:
            nombre = simbolo(p, i, j)
            if p in recibidas:
                self.agregar_clausula(nombre)
            elif registrar_ausencias:
                self.agregar_clausula(negar(nombre))

        self.agregar_clausula(negar(simbolo("P", i, j)))
        self.agregar_clausula(negar(simbolo("W", i, j)))

    def consultar(self, literal: str) -> bool | None:
        literal = literal.strip()
        if (literal,) in self._indice_clausulas:
            return True
        if (negar(literal),) in self._indice_clausulas:
            return False
        return None

    def mostrar(self, incluir_reglas: bool = True) -> str:
        lineas = []
        for n, clausula in enumerate(self.clausulas, start=1):
            if not incluir_reglas:
                if len(clausula) != 1:
                    continue
            texto = " ∨ ".join(clausula) if clausula else "-"
            lineas.append(f"c{n}: ({texto})")
        return "\n".join(lineas) if lineas else "KB vacia"
    
    def imprimir(self) -> str:
        print(self.mostrar(False))

    def cantidad_clausulas(self) -> int:
        return len(self.clausulas)

    def guardar_base(self) -> None:
        with open(log_file, "w") as f:
            f.write("")
        with open(log_file, "r+") as f:
            data = f.read()
            f.seek(0)
            f.write(self.mostrar(True))

    @property
    def casillas_visitadas(self) -> set[tuple[int, int]]:
        return set(self._vistas)
