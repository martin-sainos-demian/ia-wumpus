"""Pruebas del módulo 1 (entorno.py).  Ejecutar:  python -m unittest pruebas_entorno -v"""
import json
import os
import tempfile
import unittest

from entorno import (Entorno, VistaAgente, AccionInvalida, PartidaTerminada, INICIO, DIRECCIONES,
                     PERCEPCIONES, num_pozos, vecinas, EXITO, SALIO_SIN_ORO, MUERTE_POZO,
                     MUERTE_WUMPUS, LIMITE_PASOS)


def mundo_fijo(**cambios):
    """Mundo 4×4 colocado a mano: pozos (3,1),(2,3),(4,4); Wumpus (1,3); oro (2,2)."""
    d = {"n": 4, "pozos": [[3, 1], [2, 3], [4, 4]], "wumpus": [1, 3], "oro": [2, 2], "id": "fijo"}
    d.update(cambios)
    return Entorno(mundo=d)


class Generacion(unittest.TestCase):
    def test_invariantes(self):
        for n in (2, 3, 4, 5, 6, 8):
            for semilla in range(150):
                e = Entorno(n, semilla)
                v = e.verdad()
                self.assertNotIn(INICIO, v["pozos"])
                self.assertNotEqual(v["wumpus"], INICIO)
                self.assertNotEqual(v["oro"], INICIO)
                self.assertEqual(len(v["pozos"]), num_pozos(n))
                self.assertNotIn(v["wumpus"], v["pozos"])
                self.assertNotIn(v["oro"], v["pozos"])
                self.assertTrue(Entorno._hay_ruta_segura(n, frozenset(v["pozos"]), v["wumpus"], v["oro"]))

    def test_reproducible_por_semilla(self):
        a, b, c = Entorno(5, 11), Entorno(5, 11), Entorno(5, 12)
        self.assertEqual(a.a_dict(), b.a_dict())
        self.assertNotEqual(a.a_dict()["pozos"] + [a.a_dict()["wumpus"]], c.a_dict()["pozos"] + [c.a_dict()["wumpus"]])

    def test_numero_de_pozos(self):
        self.assertEqual([num_pozos(n) for n in (3, 4, 5, 6, 7, 8)], [2, 3, 5, 7, 10, 13])
        self.assertEqual(len(Entorno(4, 1, densidad=0.40).verdad()["pozos"]), 6)

    def test_politica_aleatoria_puede_dar_instancias_sin_solucion(self):
        sin_ruta = sum(not Entorno._hay_ruta_segura(4, frozenset(e.verdad()["pozos"]), e.verdad()["wumpus"], e.verdad()["oro"])
                       for e in (Entorno(4, s, politica="aleatoria") for s in range(300)))
        self.assertGreater(sin_ruta, 0)          # justifica la política "ruta_segura"

    def test_politica_invalida(self):
        with self.assertRaises(ValueError):
            Entorno(4, 1, politica="otra")


class Percepciones(unittest.TestCase):
    def test_contra_definicion_independiente(self):
        for semilla in range(60):
            e = Entorno(4, semilla)
            v = e.verdad()
            for i in range(1, 5):
                for j in range(1, 5):
                    ady = lambda c: abs(c[0] - i) + abs(c[1] - j) == 1
                    esperado = []
                    if any(ady(p) for p in v["pozos"]): esperado.append("Brisa")
                    if ady(v["wumpus"]):                esperado.append("Hedor")
                    if (i, j) == v["oro"]:              esperado.append("Resplandor")
                    self.assertEqual(e._percepciones_en((i, j)), esperado)

    def test_resplandor_solo_en_la_casilla_del_oro(self):
        e = mundo_fijo()                                  # oro en (2,2)
        self.assertNotIn("Resplandor", e._percepciones_en((2, 1)))   # adyacente al oro: NO hay resplandor
        self.assertIn("Resplandor", e._percepciones_en((2, 2)))

    def test_formato_observacion_y_nombres(self):
        casilla, perc = mundo_fijo().vista_agente().observar()
        self.assertEqual(casilla, (1, 1))
        self.assertIsInstance(perc, list)
        self.assertTrue(set(perc) <= set(PERCEPCIONES))


class Reglas(unittest.TestCase):
    def test_partida_ganadora_completa(self):
        e = mundo_fijo(); v = e.vista_agente()
        v.actuar("avanzar", "derecha");  self.assertEqual(v.observar(), ((2, 1), ["Brisa"]))
        v.actuar("avanzar", "arriba");   self.assertEqual(v.observar(), ((2, 2), ["Brisa", "Resplandor"]))
        v.actuar("recoger");             self.assertEqual(v.observar(), ((2, 2), ["Brisa"]))
        self.assertTrue(v.tiene_oro)
        v.actuar("avanzar", "izquierda"); self.assertEqual(v.observar(), ((1, 2), ["Hedor"]))
        v.actuar("disparar", "arriba");  self.assertEqual(v.observar(), ((1, 2), ["Grito"]))
        v.actuar("avanzar", "abajo");    self.assertEqual(v.observar(), ((1, 1), []))   # el grito dura un turno
        v.actuar("salir")
        self.assertTrue(e.terminado)
        self.assertEqual(e.resultado, EXITO)
        self.assertEqual(e.turnos, 7)

    def test_golpe_dura_un_turno_y_no_mueve(self):
        e = mundo_fijo(); v = e.vista_agente()
        v.actuar("avanzar", "izquierda")
        self.assertEqual(v.observar(), ((1, 1), ["Golpe"]))
        v.actuar("avanzar", "arriba")
        self.assertNotIn("Golpe", v.observar()[1])

    def test_flecha_atraviesa_varias_casillas_y_es_unica(self):
        e = mundo_fijo(wumpus=[1, 4], pozos=[[3, 1], [2, 3], [4, 4]]); v = e.vista_agente()
        v.actuar("disparar", "arriba")                         # desde (1,1): atraviesa (1,2),(1,3) y mata en (1,4)
        self.assertIn("Grito", v.observar()[1])
        self.assertEqual(v.flechas, 0)
        with self.assertRaises(AccionInvalida):
            v.actuar("disparar", "arriba")
        self.assertNotIn(("disparar", "arriba"), v.acciones_validas())

    def test_flecha_que_falla_no_da_grito(self):
        e = mundo_fijo(); v = e.vista_agente()
        v.actuar("disparar", "derecha")
        self.assertEqual(v.observar()[1], [])
        self.assertTrue(e.verdad()["wumpus_vivo"])

    def test_wumpus_muerto_sin_hedor_y_casilla_pisable(self):
        e = mundo_fijo(); v = e.vista_agente()
        v.actuar("avanzar", "arriba")                          # (1,2): hedor
        self.assertIn("Hedor", v.observar()[1])
        v.actuar("disparar", "arriba")
        self.assertNotIn("Hedor", v.observar()[1])
        v.actuar("avanzar", "arriba")                          # casilla del cadáver: seguro
        self.assertFalse(e.terminado)
        self.assertEqual(v.posicion, (1, 3))

    def test_muertes(self):
        e = mundo_fijo(); v = e.vista_agente()
        v.actuar("avanzar", "derecha"); v.actuar("avanzar", "derecha")
        self.assertEqual(e.resultado, MUERTE_POZO)
        e = mundo_fijo(); v = e.vista_agente()
        v.actuar("avanzar", "arriba"); v.actuar("avanzar", "arriba")
        self.assertEqual(e.resultado, MUERTE_WUMPUS)
        with self.assertRaises(PartidaTerminada):
            v.actuar("avanzar", "arriba")
        with self.assertRaises(PartidaTerminada):
            v.observar()

    def test_acciones_ilegales_no_consumen_turno(self):
        e = mundo_fijo(); v = e.vista_agente()
        for malo in [("recoger", None), ("avanzar", "norte"), ("avanzar", None), ("saltar", None)]:
            with self.assertRaises(AccionInvalida):
                v.actuar(*malo)
        v.actuar("avanzar", "arriba")
        with self.assertRaises(AccionInvalida):               # salir solo en (1,1)
            v.actuar("salir")
        self.assertEqual(e.turnos, 1)

    def test_salir_sin_oro_y_limite_de_pasos(self):
        e = mundo_fijo(); e.vista_agente().actuar("salir")
        self.assertEqual(e.resultado, SALIO_SIN_ORO)
        e = Entorno(mundo=dict(n=4, pozos=[[3, 1], [2, 3], [4, 4]], wumpus=[1, 3], oro=[2, 2]), max_pasos=5)
        v = e.vista_agente()
        for _ in range(5):
            v.actuar("avanzar", "izquierda")                   # golpes contra el muro
        self.assertEqual(e.resultado, LIMITE_PASOS)

    def test_reiniciar_conserva_el_mundo(self):
        e = mundo_fijo(); antes = e.a_dict()
        e.vista_agente().actuar("avanzar", "arriba"); e.reiniciar()
        self.assertEqual(e.vista_agente().posicion, INICIO); self.assertEqual(e.a_dict(), antes)

    def test_bitacora(self):
        e = mundo_fijo(); v = e.vista_agente()
        v.actuar("avanzar", "derecha"); v.actuar("avanzar", "derecha")
        b = e.bitacora()
        self.assertEqual([x["evento"] for x in b], [None, "cae_en_pozo"])
        self.assertTrue(e.casilla_peligrosa((3, 1)))


class JSON(unittest.TestCase):
    def test_ida_y_vuelta(self):
        e = Entorno(5, 7)
        with tempfile.TemporaryDirectory() as d:
            ruta = e.guardar(os.path.join(d, "m.json"), descripcion="prueba")
            e2 = Entorno.cargar(ruta)
        self.assertEqual(e.a_dict() | {"descripcion": "prueba"}, e2.a_dict())
        self.assertEqual(e.dibujar(), e2.dibujar())

    def test_validaciones(self):
        base = {"n": 4, "pozos": [[3, 1]], "wumpus": [1, 3], "oro": [2, 2]}
        malos = [dict(base, pozos=[[1, 1]]), dict(base, wumpus=[1, 1]), dict(base, wumpus=[3, 1]),
                 dict(base, oro=[3, 1]), dict(base, oro=[5, 5]), dict(base, pozos=[[0, 2]])]
        for m in malos:
            with self.assertRaises(ValueError, msg=str(m)):
                Entorno(mundo=m)


class SeparacionAgente(unittest.TestCase):
    def test_la_vista_no_expone_el_mapa_verdadero(self):
        v = mundo_fijo().vista_agente()
        publicos = {a for a in dir(v) if not a.startswith("_")}
        self.assertEqual(publicos, {"n", "posicion", "flechas", "tiene_oro", "terminado",
                                    "observar", "acciones_validas", "actuar"})

    def test_modulos_del_agente_no_importan_entorno(self):
        """Los módulos de KB, inferencia y agente (si existen) solo deben usar VistaAgente.observar()."""
        import ast
        for nombre in ("wumpus_kb.py", "kb.py", "motor.py", "agente.py", "inferencia.py"):
            if not os.path.exists(nombre):
                continue
            arbol = ast.parse(open(nombre, encoding="utf-8").read())
            for nodo in ast.walk(arbol):
                modulos = []
                if isinstance(nodo, ast.Import):
                    modulos = [a.name for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom):
                    modulos = [nodo.module or ""]
                self.assertNotIn("entorno", modulos, f"{nombre} importa entorno")
                self.assertNotIn("oraculo", modulos, f"{nombre} importa oraculo")
                self.assertNotIn("referencia", modulos, f"{nombre} importa referencia")


if __name__ == "__main__":
    unittest.main()
