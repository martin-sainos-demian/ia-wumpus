"""Pruebas del agente lógico (agente.py). Ejecutar:  python -m unittest pruebas_agente -v"""
import ast
import glob
import json
import os
import unittest

from agente import Agente
from entorno import EXITO, SALIO_SIN_ORO, MUERTE_POZO, Entorno
from motor import ENCADENAMIENTO, RESOLUCION

AQUI = os.path.dirname(os.path.abspath(__file__))


def mundo(prefijo):
    return Entorno.cargar(next(r for r in sorted(glob.glob(os.path.join(AQUI, "mundos", "m*.json")))
                               if os.path.basename(r).startswith(prefijo)))


class Aislamiento(unittest.TestCase):
    def test_ni_el_agente_ni_el_motor_ni_la_kb_importan_el_simulador(self):
        for nombre in ("agente.py", "motor.py", "wumpus_kb.py"):
            with open(os.path.join(AQUI, nombre), encoding="utf-8") as f:
                arbol = ast.parse(f.read())
            mods = {n.names[0].name.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.Import)}
            mods |= {n.module.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertFalse(mods & {"entorno", "oraculo", "referencia", "auxiliar_pruebas"}, (nombre, mods))

    def test_el_agente_solo_usa_la_interfaz_publica_de_la_vista(self):
        class Estrecha:
            """Expone únicamente la interfaz documentada; cualquier otro acceso falla."""
            _OK = {"n", "posicion", "flechas", "tiene_oro", "terminado", "observar", "acciones_validas", "actuar"}

            def __init__(self, v):
                object.__setattr__(self, "_v", v)

            def __getattr__(self, nombre):
                if nombre not in self._OK:
                    raise AssertionError(f"el agente accedió a {nombre!r}, que no es de la interfaz")
                return getattr(self._v, nombre)

        e = mundo("m3")
        Agente(Estrecha(e.vista_agente())).jugar()
        self.assertEqual(e.resultado, EXITO)


class MundosDePrueba(unittest.TestCase):
    def jugar(self, prefijo, metodo=RESOLUCION, **kw):
        e = mundo(prefijo)
        a = Agente(e.vista_agente(), metodo, **kw)
        a.jugar()
        return e, a

    def test_resolucion_gana_donde_hay_ruta_demostrable(self):
        for p in ("m1", "m2", "m3", "m4", "m6"):
            e, a = self.jugar(p)
            self.assertEqual(e.resultado, EXITO, p)
            self.assertFalse(a.bloqueo, p)
            self.assertEqual(a.entradas_riesgo, 0, p)

    def test_bloqueos_se_reportan_y_no_son_fallos_logicos(self):
        for p in ("m5", "m7"):
            for met in (RESOLUCION, ENCADENAMIENTO):
                e, a = self.jugar(p, met)
                self.assertEqual(e.resultado, SALIO_SIN_ORO, p)
                self.assertTrue(a.bloqueo)
                self.assertIn("sin casillas seguras", a.razon_bloqueo)
                self.assertEqual(a.bitacora[-1].accion, ("salir", None))
                self.assertEqual(a.entradas_riesgo, 0)
                self.assertEqual(a.movimientos, 0)

    def test_m3_dispara_una_vez_con_justificacion_y_mata_al_wumpus(self):
        e, a = self.jugar("m3")
        self.assertEqual(a.disparos, 1)
        self.assertTrue(a.kb.wumpus_muerto)
        ciclo = next(c for c in a.bitacora if c.decision == "disparar")
        self.assertIn("W_1_3", ciclo.traza_decisiva)
        self.assertIn("KB ⊨", ciclo.traza_decisiva)

    def test_m1_y_m4_el_encadenamiento_se_bloquea_y_la_resolucion_no(self):
        for p in ("m1", "m4"):
            _, a = self.jugar(p, ENCADENAMIENTO)
            self.assertTrue(a.bloqueo, p)
            e, b = self.jugar(p, RESOLUCION)
            self.assertEqual(e.resultado, EXITO)

    def test_politica_arriesgar_cuenta_el_riesgo(self):
        e, a = self.jugar("m5", politica_bloqueo="arriesgar")
        self.assertGreaterEqual(a.entradas_riesgo, 1)
        self.assertTrue(any(c.decision == "arriesgar" for c in a.bitacora))

    def test_la_bitacora_registra_el_ciclo_completo(self):
        _, a = self.jugar("m6")
        for c in a.bitacora:
            self.assertTrue(c.decision and c.razon and c.nuevo_estado and c.accion)
            self.assertIn("Percepción", Agente.texto_ciclo(c))
        self.assertEqual(a.bitacora[-1].accion, ("salir", None))
        self.assertIn("Decisión", a.texto_bitacora())


class SinRiesgosEnMundosAleatorios(unittest.TestCase):
    def test_ni_muertes_ni_riesgo_ni_contradicciones(self):
        exitos = {RESOLUCION: 0, ENCADENAMIENTO: 0}
        for k in range(60):
            for met in (RESOLUCION, ENCADENAMIENTO):
                e = Entorno(4, semilla=7000 + k, politica="aleatoria" if k % 4 == 0 else "ruta_segura")
                a = Agente(e.vista_agente(), met)
                r = a.jugar()
                self.assertIn(e.resultado, (EXITO, SALIO_SIN_ORO), (k, met, e.resultado))
                self.assertEqual(r["entradas_riesgo"], 0)
                self.assertEqual(r["contradicciones"], 0)
                self.assertEqual(a.kb.wumpus_muerto, r["disparos"] > 0)    # todo disparo justificado acertó
                exitos[met] += e.resultado == EXITO
        self.assertGreaterEqual(exitos[RESOLUCION], exitos[ENCADENAMIENTO])


class Contradicciones(unittest.TestCase):
    def test_con_kb_inconsistente_no_se_confia_y_se_sale_por_lo_pisado(self):
        e = mundo("m6")
        a = Agente(e.vista_agente())
        inyectado = []

        def sabotaje(ag, ciclo):
            if ciclo.n == 4 and not inyectado:                       # observación falsa: brisa donde no hubo
                pos = ciclo.posicion
                ag.kb.agregar_clausula(f"B_{pos[0]}_{pos[1]}", origen="observacion", categoria="Observación")
                ag.kb.agregar_clausula(f"¬B_{pos[0]}_{pos[1]}", origen="observacion", categoria="Observación")
                inyectado.append(pos)

        a.jugar(al_ciclo=sabotaje)
        self.assertTrue(a.motor.eventos_contradiccion)
        self.assertTrue(a.bloqueo)
        self.assertIn("inconsistente", a.razon_bloqueo)
        self.assertIn(e.resultado, (EXITO, SALIO_SIN_ORO))            # no murió: sólo pisó casillas ya pisadas
        self.assertTrue(any(c.contradicciones for c in a.bitacora))


if __name__ == "__main__":
    unittest.main()
