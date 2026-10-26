"""entorno.py — Módulo 1: generador y simulador del Mundo de Wumpus.

SEPARACIÓN SIMULADOR / AGENTE
    * `Entorno` guarda el estado REAL (pozos, Wumpus, oro) y aplica las reglas. Es del evaluador.
    * `VistaAgente` es lo ÚNICO que debe recibir el agente: sensores (percepciones de su casilla)
      y actuadores (avanzar, disparar, recoger, salir). No expone pozos, Wumpus ni oro.
    * Los módulos de KB, inferencia y agente NO deben importar `Entorno`; solo usan los datos
      que entrega `VistaAgente.observar()`.

CONVENCIONES
    * Casilla (i, j): i = columna (x), j = fila (y), ambas desde 1; (1,1) es la esquina inferior izquierda.
    * Adyacencia: 4 vecinos ortogonales (las diagonales no son vecinas).
    * Percepciones (cadenas): "Brisa", "Hedor", "Resplandor", "Golpe", "Grito".
        Brisa      : algún pozo en una casilla adyacente.
        Hedor      : el Wumpus VIVO está en una casilla adyacente.
        Resplandor : el oro está en la casilla actual (y no se ha recogido).
        Golpe      : el último movimiento intentó salir del tablero (dura un turno).
        Grito      : una flecha mató al Wumpus (dura un turno).
    * Acciones: ("avanzar", dir), ("disparar", dir), ("recoger", None), ("salir", None)
        con dir en {"arriba", "abajo", "izquierda", "derecha"}.
    * Flecha: UNA sola; vuela en línea recta, atraviesa todas las casillas de esa dirección
        y se detiene en el muro o al matar al Wumpus.
    * Terminación: muerte (pozo o Wumpus vivo), salir desde (1,1) (con o sin oro) o límite de pasos.
"""
import json
import random
import re
from collections import deque

INICIO = (1, 1)
DIRECCIONES = {"arriba": (0, 1), "abajo": (0, -1), "izquierda": (-1, 0), "derecha": (1, 0)}
PERCEPCIONES = ("Brisa", "Hedor", "Resplandor", "Golpe", "Grito")
ACCIONES = ("avanzar", "disparar", "recoger", "salir")
POLITICAS = ("ruta_segura", "aleatoria")

# Resultados posibles de una partida
EXITO = "exito"                      # salió de (1,1) con el oro
SALIO_SIN_ORO = "salio_sin_oro"      # salió de (1,1) sin el oro
MUERTE_POZO = "muerte_pozo"
MUERTE_WUMPUS = "muerte_wumpus"
LIMITE_PASOS = "limite_de_pasos"


class AccionInvalida(ValueError):
    """Acción ilegal en el estado actual (no consume turno)."""


class PartidaTerminada(RuntimeError):
    """Se intentó actuar u observar después de terminada la partida."""


def num_pozos(n, densidad=0.20):
    """Pozos = densidad·n² redondeado al entero más próximo (mitades hacia arriba)."""
    return int(densidad * n * n + 0.5)


def vecinas(n, c):
    """Casillas adyacentes a c dentro de un tablero n×n."""
    i, j = c
    return [(i + di, j + dj) for di, dj in DIRECCIONES.values()
            if 1 <= i + di <= n and 1 <= j + dj <= n]


def _casilla(valor, n, nombre):
    try:
        i, j = valor
    except (TypeError, ValueError):
        raise ValueError(f"{nombre}: se esperaba (i,j), se recibió {valor!r}")
    if not (isinstance(i, int) and isinstance(j, int) and 1 <= i <= n and 1 <= j <= n):
        raise ValueError(f"{nombre}: {valor!r} está fuera del tablero {n}×{n}")
    return (i, j)


class Entorno:
    """Mundo de Wumpus completo (estado real). Uso exclusivo del simulador y del evaluador."""

    def __init__(self, n=4, semilla=None, densidad=0.20, politica="ruta_segura",
                 max_pasos=200, mundo=None, id_mundo=None):
        """Genera un mundo aleatorio reproducible o carga uno de `mundo` (dict, ver a_dict()).

        politica:
            "ruta_segura" (por defecto): se regenera el sorteo hasta que exista un camino desde (1,1)
                hasta el oro sin pasar por pozos ni por la casilla del Wumpus. Evita las instancias
                insolubles (oro rodeado de pozos o tapado por el Wumpus).
            "aleatoria": sin garantía de solución.
        En ambos casos: (1,1) sin peligros ni oro, el oro nunca está en un pozo, y cada casilla
        contiene a lo sumo un peligro (pozo o Wumpus).
        """
        if politica not in POLITICAS:
            raise ValueError(f"politica debe ser una de {POLITICAS}")
        self.max_pasos = max_pasos
        self.densidad = densidad
        self.politica = politica
        self.descripcion = ""
        self.intentos_generacion = 0
        if mundo is not None:
            n = mundo["n"]
            self.semilla = mundo.get("semilla")
            self.densidad = mundo.get("densidad", densidad)
            self.politica = mundo.get("politica", politica)
            self.descripcion = mundo.get("descripcion", "")
            self.n = n
            self._pozos, self._wumpus, self._oro = self._validar_mundo(
                n, mundo["pozos"], mundo["wumpus"], mundo["oro"])
            self.id = id_mundo or mundo.get("id") or f"n{n}-cargado"
        else:
            if n < 2:
                raise ValueError("n debe ser al menos 2")
            self.n = n
            self.semilla = semilla
            self._pozos, self._wumpus, self._oro = self._generar(random.Random(semilla))
            self.id = id_mundo or f"n{n}-s{semilla}-{self.politica}"
        self.reiniciar()

    # ------------------------------------------------------------------ generación
    def _generar(self, rng):
        n = self.n
        celdas = [(i, j) for j in range(1, n + 1) for i in range(1, n + 1)]
        candidatas = [c for c in celdas if c != INICIO]               # (1,1) siempre libre
        k = num_pozos(n, self.densidad)
        if k + 1 > len(candidatas):
            raise ValueError("Demasiados pozos para el tamaño del tablero")
        for intento in range(1, 10001):
            elegidas = rng.sample(candidatas, k + 1)                   # peligros en casillas distintas
            wumpus, pozos = elegidas[0], frozenset(elegidas[1:])
            oro = rng.choice([c for c in candidatas if c not in pozos])
            if self.politica == "aleatoria" or self._hay_ruta_segura(n, pozos, wumpus, oro):
                self.intentos_generacion = intento
                return pozos, wumpus, oro
        raise RuntimeError("No se pudo generar un mundo con solución; baja la densidad o usa otra semilla")

    @staticmethod
    def _hay_ruta_segura(n, pozos, wumpus, oro):
        """BFS desde (1,1) hasta el oro evitando pozos y la casilla del Wumpus."""
        visto, cola = {INICIO}, deque([INICIO])
        while cola:
            c = cola.popleft()
            if c == oro:
                return True
            for v in vecinas(n, c):
                if v not in visto and v not in pozos and v != wumpus:
                    visto.add(v)
                    cola.append(v)
        return False

    @staticmethod
    def _validar_mundo(n, pozos, wumpus, oro):
        pozos = frozenset(_casilla(p, n, "pozo") for p in pozos)
        wumpus = _casilla(wumpus, n, "wumpus")
        oro = _casilla(oro, n, "oro")
        if INICIO in pozos or wumpus == INICIO:
            raise ValueError("La casilla inicial (1,1) no puede tener peligros")
        if wumpus in pozos:
            raise ValueError("El Wumpus y un pozo no pueden compartir casilla")
        if oro in pozos:
            raise ValueError("El oro no puede estar dentro de un pozo")
        return pozos, wumpus, oro

    # ------------------------------------------------------------------ estado de la partida
    def reiniciar(self):
        """Vuelve al estado inicial de la partida (el mundo no cambia)."""
        self._pos = INICIO
        self._flechas = 1
        self._wumpus_vivo = True
        self._oro_en_mundo = True
        self._tiene_oro = False
        self._vivo = True
        self._terminado = False
        self._resultado = None
        self._golpe = False
        self._grito = False
        self._turnos = 0
        self._bitacora = []

    def _percepciones_en(self, c):
        vec = vecinas(self.n, c)
        p = []
        if any(v in self._pozos for v in vec):
            p.append("Brisa")
        if self._wumpus_vivo and self._wumpus in vec:
            p.append("Hedor")
        if self._oro_en_mundo and c == self._oro:
            p.append("Resplandor")
        if self._golpe:
            p.append("Golpe")
        if self._grito:
            p.append("Grito")
        return p

    def _observar(self):
        if self._terminado:
            raise PartidaTerminada("La partida ya terminó")
        return self._pos, self._percepciones_en(self._pos)

    def _acciones_validas(self):
        if self._terminado:
            return []
        acc = [("avanzar", d) for d in DIRECCIONES]
        if self._flechas:
            acc += [("disparar", d) for d in DIRECCIONES]
        if self._oro_en_mundo and self._pos == self._oro:
            acc.append(("recoger", None))
        if self._pos == INICIO:
            acc.append(("salir", None))
        return acc

    def _actuar(self, accion, direccion=None):
        if self._terminado:
            raise PartidaTerminada("La partida ya terminó")
        if (accion, direccion if accion in ("avanzar", "disparar") else None) not in self._acciones_validas():
            raise AccionInvalida(f"Acción no válida ahora: {accion!r} {direccion!r}")

        desde = self._pos
        self._golpe = self._grito = False                  # las percepciones transitorias duran un turno
        evento = None

        if accion == "avanzar":
            di, dj = DIRECCIONES[direccion]
            nueva = (desde[0] + di, desde[1] + dj)
            if not (1 <= nueva[0] <= self.n and 1 <= nueva[1] <= self.n):
                self._golpe = True
                evento = "golpe"
            else:
                self._pos = nueva
                if nueva in self._pozos:
                    self._terminar(MUERTE_POZO, vivo=False)
                    evento = "cae_en_pozo"
                elif nueva == self._wumpus and self._wumpus_vivo:
                    self._terminar(MUERTE_WUMPUS, vivo=False)
                    evento = "devorado"
        elif accion == "disparar":
            self._flechas -= 1
            di, dj = DIRECCIONES[direccion]
            c = desde
            evento = "flecha_sin_efecto"
            while True:                                    # vuelo en línea recta, atraviesa casillas
                c = (c[0] + di, c[1] + dj)
                if not (1 <= c[0] <= self.n and 1 <= c[1] <= self.n):
                    break
                if c == self._wumpus and self._wumpus_vivo:
                    self._wumpus_vivo = False
                    self._grito = True
                    evento = "wumpus_muerto"
                    break
        elif accion == "recoger":
            self._oro_en_mundo = False
            self._tiene_oro = True
            evento = "oro_recogido"
        else:                                              # salir
            self._terminar(EXITO if self._tiene_oro else SALIO_SIN_ORO)
            evento = "salida"

        self._turnos += 1
        if not self._terminado and self._turnos >= self.max_pasos:
            self._terminar(LIMITE_PASOS)
            evento = (evento or "") + "+limite_de_pasos"
        self._bitacora.append({"turno": self._turnos, "accion": accion, "direccion": direccion,
                               "desde": desde, "hasta": self._pos, "evento": evento})

    def _terminar(self, resultado, vivo=True):
        self._terminado = True
        self._vivo = vivo
        self._resultado = resultado

    # ------------------------------------------------------------------ vistas
    def vista_agente(self):
        """Entrega al agente su única interfaz con el mundo."""
        return VistaAgente(self)

    @property
    def terminado(self):
        return self._terminado

    @property
    def resultado(self):
        return self._resultado

    @property
    def turnos(self):
        return self._turnos

    # ------------------------------------------------------------------ SOLO EVALUADOR / DEPURACIÓN
    def verdad(self):
        """[EVALUADOR] Estado real del mundo. No pasar al agente ni a la KB."""
        return {"pozos": set(self._pozos), "wumpus": self._wumpus, "oro": self._oro,
                "pos": self._pos, "wumpus_vivo": self._wumpus_vivo, "oro_en_mundo": self._oro_en_mundo}

    def bitacora(self):
        """[EVALUADOR] Registro de cada acción con su desde/hasta y el evento ocurrido."""
        return [dict(b) for b in self._bitacora]

    def casilla_peligrosa(self, c):
        """[EVALUADOR] ¿Entrar en c mata al agente? (pozo o Wumpus vivo)."""
        return c in self._pozos or (c == self._wumpus and self._wumpus_vivo)

    def dibujar(self):
        """[EVALUADOR] Tablero completo: A agente, P pozo, W Wumpus (w si murió), G oro."""
        sep = "  +" + "+".join(["-----"] * self.n) + "+"
        filas = [sep]
        for j in range(self.n, 0, -1):
            celdas = []
            for i in range(1, self.n + 1):
                c, t = (i, j), ""
                if c == self._pos: t += "A"
                if c in self._pozos: t += "P"
                if c == self._wumpus: t += "W" if self._wumpus_vivo else "w"
                if c == self._oro and self._oro_en_mundo: t += "G"
                celdas.append(t.center(5))
            filas += [f"{j} |" + "|".join(celdas) + "|", sep]
        filas.append("   " + " ".join(str(i).center(5) for i in range(1, self.n + 1)))
        return "\n".join(filas)

    # ------------------------------------------------------------------ JSON
    def a_dict(self):
        return {"id": self.id, "n": self.n, "semilla": self.semilla, "densidad": self.densidad,
                "politica": self.politica, "descripcion": self.descripcion,
                "pozos": [list(c) for c in sorted(self._pozos, key=lambda c: (c[1], c[0]))],
                "wumpus": list(self._wumpus), "oro": list(self._oro)}

    def guardar(self, ruta, descripcion=None):
        if descripcion is not None:
            self.descripcion = descripcion
        texto = json.dumps(self.a_dict(), indent=2, ensure_ascii=False)
        texto = re.sub(r"\[\s+(\d+),\s+(\d+)\s+\]", r"[\1, \2]", texto)      # cada casilla en una línea: [i, j]
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
        return ruta

    @classmethod
    def desde_dict(cls, d, **opciones):
        return cls(mundo=d, **opciones)

    @classmethod
    def cargar(cls, ruta, **opciones):
        with open(ruta, encoding="utf-8") as f:
            return cls.desde_dict(json.load(f), **opciones)


class VistaAgente:
    """Única interfaz del agente con el mundo: percibir y actuar. No expone el mapa verdadero."""

    def __init__(self, entorno):
        self.__e = entorno

    @property
    def n(self):
        """Tamaño del tablero (es de conocimiento público)."""
        return self.__e.n

    @property
    def posicion(self):
        """Posición del propio agente."""
        return self.__e._pos

    @property
    def flechas(self):
        return self.__e._flechas

    @property
    def tiene_oro(self):
        return self.__e._tiene_oro

    @property
    def terminado(self):
        return self.__e._terminado

    def observar(self):
        """((i,j), [percepciones]) de la casilla actual: mismo formato que consume la KB."""
        return self.__e._observar()

    def acciones_validas(self):
        """Lista de (accion, direccion) legales ahora."""
        return self.__e._acciones_validas()

    def actuar(self, accion, direccion=None):
        """Ejecuta una acción. Lanza AccionInvalida (sin gastar turno) si no es legal."""
        self.__e._actuar(accion, direccion)
