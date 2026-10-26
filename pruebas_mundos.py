"""Verifica que cada mundo de prueba (mundos/*.json) cumple la categoría para la que fue elegido.
Ejecutar:  python -m unittest pruebas_mundos -v"""
import glob
import json
import os
import unittest

from entorno import Entorno
from referencia import explorar

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTAS = sorted(glob.glob(os.path.join(AQUI, "mundos", "m*.json")))


def cargar(prefijo):
    ruta = next(r for r in RUTAS if os.path.basename(r).startswith(prefijo))
    return Entorno.cargar(ruta)


def percepciones_iniciales(e):
    return e.vista_agente().observar()[1]


def hay_ruta_segura(e):
    v = e.verdad()
    return Entorno._hay_ruta_segura(e.n, frozenset(v["pozos"]), v["wumpus"], v["oro"])


class MundosDePrueba(unittest.TestCase):
    def test_hay_al_menos_seis_mundos_validos(self):
        self.assertGreaterEqual(len(RUTAS), 6)
        for r in RUTAS:
            e = Entorno.cargar(r)
            self.assertTrue(e.id and e.descripcion, r)

    def test_resultados_de_referencia_coinciden_con_el_indice(self):
        """El explorador perfecto reproduce lo registrado en mundos/indice.json (detecta cambios accidentales)."""
        with open(os.path.join(AQUI, "mundos", "indice.json"), encoding="utf-8") as f:
            indice = json.load(f)
        for fila in indice:
            if fila["referencia"] is None:
                continue
            r = explorar(Entorno.cargar(os.path.join(AQUI, "mundos", fila["archivo"])))
            for k, esperado in fila["referencia"].items():
                self.assertEqual(r[k], esperado, f"{fila['archivo']}: {k}")

    def test_m1_sin_peligro_inicial(self):
        e = cargar("m1")
        self.assertEqual(percepciones_iniciales(e), [])
        self.assertTrue(explorar(e)["exito"])

    def test_m2_ambiguedad_de_pozos(self):
        r = explorar(cargar("m2"))
        self.assertTrue(r["exito"] and r["pozo_cierto"] and r["brisas"] >= 2)

    def test_m3_requiere_matar_al_wumpus(self):
        e = cargar("m3")
        self.assertFalse(hay_ruta_segura(e))                 # sin matarlo no hay camino seguro al oro
        r = explorar(e)
        self.assertTrue(r["exito"] and r["disparo"] and r["wumpus_cierto"])

    def test_m4_exige_retroceso(self):
        r = explorar(cargar("m4"))
        self.assertTrue(r["exito"])
        self.assertGreaterEqual(r["retro"], 4)

    def test_m5_y_m7_bloqueo_por_falta_de_conocimiento(self):
        for prefijo, percepcion in (("m5", "Brisa"), ("m7", "Hedor")):
            e = cargar(prefijo)
            self.assertIn(percepcion, percepciones_iniciales(e))
            self.assertTrue(hay_ruta_segura(e))              # el mundo SÍ tiene solución...
            r = explorar(e)
            self.assertTrue(r["bloqueo"] and r["movs"] == 0)  # ...pero la KB no puede justificar ningún paso
            self.assertFalse(r["exito"])

    def test_m6_mixto(self):
        r = explorar(cargar("m6"))
        self.assertTrue(r["exito"] and r["brisas"] >= 3 and r["hedores"] >= 1 and r["movs"] >= 14)

    def test_m8_5x5_tiene_ruta_segura(self):
        e = cargar("m8")
        self.assertEqual(e.n, 5)
        self.assertTrue(hay_ruta_segura(e))


if __name__ == "__main__":
    unittest.main()
