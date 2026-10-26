# Proyecto 2 — Agente lógico en el mundo de Wumpus

Python 3.10+, sin dependencias externas. Todo se ejecuta desde esta carpeta.

## Módulos

| Módulo | Archivo | Qué hace |
|---|---|---|
| 1. Mundo | `entorno.py` | Genera y simula mundos reproducibles (semilla / JSON). El agente sólo ve `VistaAgente`. |
| 2. Traductor + KB | `wumpus_kb.py` | KB en FNC: axiomas, traducción de percepciones, origen de cada cláusula. (Es tu `wumpus_kb.py` adaptado.) |
| 3a. Motor | `motor.py` | Resolución por refutación y encadenamiento hacia adelante, escritos desde cero. Consultas trivaluadas con traza. |
| 3b. Agente | `agente.py` | Ciclo percepción → KB → inferencia → decisión → acción → nuevo estado, con bitácora. |
| Apoyo | `jugar.py`, `experimentos.py` | Jugar una partida / generar tablas y bitácoras. |
| Solo evaluación | `oraculo.py`, `referencia.py`, `auxiliar_pruebas.py` | Verdad por enumeración de modelos. **Ni el agente, ni el motor, ni la KB los importan** (lo verifica una prueba). |

## Cómo ejecutar

```bash
python -m unittest discover -p "pruebas_*.py"          # 73 pruebas (~1 min)
python jugar.py mundos/m3_wumpus_custodia_oro.json      # una partida con bitácora y pruebas
python jugar.py mundos/m1_sin_peligro_inicial.json --metodo encadenamiento
python jugar.py mundos/m5_bloqueo_brisa_inicial.json --politica arriesgar
python jugar.py --n 4 --semilla 13 --sin-trazas --kb kb.txt
python experimentos.py                                  # regenera resultados/ (tablas + trazas)
```

Uso desde código:

```python
from entorno import Entorno
from agente import Agente
e = Entorno.cargar("mundos/m3_wumpus_custodia_oro.json")
a = Agente(e.vista_agente(), metodo="resolucion")      # o "encadenamiento"
a.jugar();  print(e.resultado);  print(a.texto_bitacora())

from motor import Motor            # consultas sueltas sobre una KB
r, traza = a.motor.es_seguro(2, 1);  print(r, traza)
a.motor.hay_pozo(3, 1);  a.motor.hay_wumpus(1, 3)
a.motor.casillas_seguras();  a.motor.casillas_sospechosas();  print(a.motor.explicacion_de_consulta(2, 1))
```

## Cambios respecto a tu `wumpus_kb.py`

| Antes | Ahora | Por qué |
|---|---|---|
| Coordenadas desde 0 | Desde 1, `(i,j)` = (columna, fila), (1,1) abajo‑izquierda | Coincide con el simulador y el enunciado |
| Percepciones `B`, `S`, `R`; elementos `P`, `W`, `G` | Nombres del simulador (`Brisa`, `Hedor`, `Resplandor`, `Golpe`, `Grito`); símbolos `H` (hedor) y `O` (oro) | `S` choca con "segura" |
| `R` y `G` con la regla de vecinas | `R_i ⇔ O_i` (misma casilla) | El resplandor no se percibe desde casillas vecinas |
| Sin unicidad ni exclusión | A5 un solo Wumpus, A6 `¬P∨¬W`, A7 seguridad con `M` | Sin ellas casi no se deduce el Wumpus ni se justifica un disparo |
| Siempre `¬P`, `¬W` al visitar | Igual, pero tras el Grito deja de registrar hedor y `¬W` (decisión D1) | Con el Wumpus muerto el agente puede pisar su casilla; sin esto la KB se contradice con el mundo |
| `consultar` = buscar cláusula unitaria | `valor_directo` (sin inferencia) + el motor hace la inferencia | Una consulta unitaria no es inferencia |
| KB global | Una instancia por partida | Reproducibilidad |
| — | Origen de cada cláusula (regla / observación / derivado), turno y premisas | Explicabilidad |

## Decisiones de diseño (todas documentadas en el código)

* **Wumpus muerto (D1):** `W_i` = "el Wumpus está o estaba en i"; el Grito afirma `M`. La KB nunca retira nada (es monótona).
* **Un peligro por casilla (D2):** `¬P_i ∨ ¬W_i`. "Dos pozos en una casilla" es imposible porque hay una sola proposición `P_i`.
* **Mundo cerrado sobre `M`:** mientras no se oiga el Grito, el motor supone `¬M` (sólo una flecha puede matar al Wumpus y el agente oye siempre el Grito). Aparece como `sup¬M` en las trazas y se retira solo al afirmarse `M`.
* **Resolución:** conjunto de soporte, preferencia por cláusulas cortas, poda de tautologías y subsumidos. Se detiene al derivar □, al saturar el soporte, o al llegar al tope de 5 000 resoluciones (→ `DESCONOCIDO`).
* **Dos concesiones de eficiencia, declaradas:** (1) la base se mantiene simplificada por *resolución unitaria* (cada paso es un nodo `uN` de la prueba y se cuenta como esfuerzo de mantenimiento); (2) las cláusulas de símbolos B/H/R/S de casillas sin observar ni consultar "duermen" (eliminación de Davis‑Putnam: todo resolvente sobre ellos es tautología). Sin esto una consulta desconocida tardaba ~7 s en 4×4.
* **Poda por longitud (6 literales):** hace la resolución incompleta *en teoría*. En la práctica el oráculo no encontró ni una discrepancia (ver abajo), pero una respuesta `DESCONOCIDO` con podas se marca como no garantizada.
* **Encadenamiento:** cada cláusula se lee como reglas "¬otros literales → literal". Punto fijo por contadores. No razona por casos, y por eso es incompleto.
* **Disparo:** sólo si la KB demuestra `W_c1 ∨ … ∨ W_ck` para las casillas de una línea de tiro (ni siquiera hace falta localizar al Wumpus exactamente). Si la flecha no da el Grito, se registra `¬W` en esa línea y la contradicción se detecta.
* **Bloqueo:** se reporta (`razon_bloqueo`) y se vuelve a (1,1) para salir. Con `--politica arriesgar` se entra a la sospechosa más cercana y cada entrada cuenta como acción de riesgo.

## Resultados (carpeta `resultados/`)

**Corrección.** La resolución coincide con el oráculo de enumeración de modelos en las 315 comparaciones de la prueba sobre mundos aleatorios (490 en una corrida previa más amplia) y en los 7 mundos 4×4 (incluida la deducción *por casos*: con brisa y hedor en (2,1), `(3,1)` y `(2,2)` son peligrosas aunque no se sepa cuál es el pozo y cuál el Wumpus). El encadenamiento nunca afirma algo falso, pero en esas 315 comparaciones dejó de demostrar 48 casillas peligrosas que la resolución sí demostró. La KB nunca contradice el mundo real en 300 mundos con disparos, Grito y oro.

**Misión en los 8 mundos de prueba** (`tabla_metricas.md`): la resolución cumple m1, m2, m3 (con disparo justificado), m4, m6 y m8 (5×5); se bloquea correctamente en m5 y m7. El encadenamiento cumple m2, m3, m6, m8 pero **se bloquea en m1 y m4**: necesita razonar por casos.

**Lote de 200 mundos aleatorios 4×4** (`lote_aleatorio.md`): resolución 68 éxitos (34 %), encadenamiento 67 (33.5 %); **0 muertes y 0 acciones de riesgo en ambos**. El 66 % restante son bloqueos genuinos (nada seguro es demostrable con lo percibido): un razonador perfecto y prudente tampoco los supera (referencia: 90/260).

**Costo.** Cuando demuestra, la resolución es barata (decenas de operaciones). Cuando tiene que *saturar* para concluir "desconocido" cuesta mucho más: en la comparación sobre consultas comunes, m2 pasa de 9 ms (encadenamiento) a 3.3 s (resolución, sin memoria).

## Limitaciones conocidas

* La poda por longitud y el tope hacen que `DESCONOCIDO` de la resolución no sea siempre una garantía de indemostrabilidad (validado empíricamente en 4×4, no demostrado).
* El oráculo es exponencial: sólo valida 4×4. El mundo 5×5 (m8) mide costo, no corrección.
* La detección de contradicciones es por resolución unitaria: encuentra las que se manifiestan entre hechos, no toda inconsistencia posible.
* `casillas_sospechosas()` devuelve las casillas **no visitadas** con peligro posible; las de peligro demostrado se piden con `casillas_peligrosas()`.
