# Diagnostic: S2.assign < S1.assign — DC 1000001 (206 vs 173) y DC 1000009 (202 vs 195)

**Fecha:** 2026-07-20  
**DC analizado en profundidad:** 1000001 (gap máximo: 33 líneas)  
**Archivos tocados:** ninguno — solo lectura + script efímero en scratchpad

---

## 1. DEFINICIÓN DE assign_lines — ¿cuentan lo mismo?

### Stage 1 — `src/stage_one/post_processing/post_processing.py` línea 74

```python
self.assign_lines = len(finial_order_df[finial_order_df['order_allocation'] == 1])
```

- Tipo de `order_allocation`: **binario** (0 ó 1 exacto)  
- Sin dedup: cada fila del DataFrame cuenta independientemente  
- Unidad: número de **filas** con asignación total  

### Stage 2 — `src/stage_two/post_processing/post_processing.py` línea 85

```python
self.assign_lines = len(
    finial_order_df[finial_order_df['order_allocation'] >= 1]
    .drop_duplicates(subset=['sales_document','sales_document_item','schedule_line',
                             'material','po_number','requested_delivery_period'])
)
```

- Tipo de `order_allocation`: **entero** (puede ser 0, 1, 2, 3 … pallets asignados)  
- Con dedup por 6 claves: una orden dividida en dos camiones genera 2 filas, pero cuenta como 1 línea única  
- Umbral `>= 1`: una orden parcialmente asignada (1+ pallets) cuenta como "asignada"  
- Unidad: número de **líneas únicas** con al menos 1 pallet asignado  

### Las dos variables NO miden lo mismo

La asimetría más importante está en la **variable de slack**:

| Atributo | Stage 1 (`order_non_selection_var`) | Stage 2 (`order_non_selection_var`) |
|---|---|---|
| Tipo en el modelo | `GRB.BINARY` (0 ó 1) | `GRB.INTEGER` para órdenes divisibles; `GRB.BINARY` para no-divisibles |
| Rango (ub) | 0–1 | 0–`ub` (cantidad de pallet-spots de la orden) |
| Interpretación | "esta orden está rechazada completa" | "esta cantidad de pallet-spots fue rechazada" |
| TOTAL_ORDER_SLACK | **suma de órdenes rechazadas (conteo)** | **suma de pallet-spots rechazados (volumen)** |
| Límite global de TOTAL_ORDER_SLACK | — | `total_pallet_spots * 100` (confirmado en decision_variables.py línea 82) |

Una orden rechazada en Stage 1 contribuye **1** al TOTAL_ORDER_SLACK.  
La misma orden rechazada en Stage 2 contribuye **N pallet-spots** al TOTAL_ORDER_SLACK (donde N es la capacidad de pallet de esa orden).

---

## 2. PER-LEVEL Stage 2 — DC 1000001

### Niveles del loop lexicográfico de Stage 2

| Prioridad | Nombre objetivo | ¿Corrió? | Status SCIP | objVal | Elapsed | ¿Break? |
|---|---|---|---|---|---|---|
| P70 | TOTAL_ORDER_SLACK | **SÍ** | OPTIMAL (2) | 57.0 | ~0.5 s | Early stop **→ BREAK** |
| P60 | TRUCK_COUNT + PREF | **NO** | — | — | — | — |
| P40 | DELAY_COST | **NO** | — | — | — | — |
| P30 | ORDER_ITEM_SELECTION_SLACK | **NO** | — | — | — | — |
| P10 | ORDER_SPLIT_COST | **NO** | — | — | — | — |

**Solo se ejecutó 1 solve de SCIP para DC 1000001 en Stage 2.**

### Condición de early stop (confirmado en `src/stage_two/model_building/objectives.py`)

```python
if po_count is not None:
    if sum(truck_selection) >= po_count:
        logger.info(f"Stopping Stage 2: As Stage 1 PO Count and Stage 2 is same")
        break  # sin pin constraint para P70
```

Después de P70:

- `truck_selection` = [1, 1, 1] → PO01/period=3, PO22/period=4, PO25/period=3 → **suma = 3**  
- `proposed_po_count` (Stage 1) = **3**  
- Condición: 3 ≥ 3 → **True** → break inmediato  

P70 es además el primer nivel del loop. El break ocurre antes de añadir el pin constraint de P70, por lo que Stage 2 termina con el modelo P70 sin pinar.

### Implicación del early stop

Stage 2 nunca ejecutó P60 (optimización del conteo de camiones). La asignación de camiones a períodos queda fija por P70:

| Camión | Stage 1 período | Stage 2 período |
|---|---|---|
| PO01 | 4 | 3 |
| PO22 | 1 | **4** |
| PO25 | 1 | **3** |

Stage 1 asignó PO22 y PO25 al período 1 (después de correr P30 = DELAY_ADVANCE_COST). Stage 2 nunca corrió el nivel equivalente (P40) porque el early stop cortó antes.

---

## 3. SLACK REAL — comparación DC 1000001

### KPIs de solución

| KPI | Stage 1 | Stage 2 |
|---|---|---|
| TOTAL_ORDER_SLACK | **2.0** (unidad: órdenes) | **57.0** (unidad: pallet-spots) |
| TOTAL_ORDER_ITEM_SELECTION_SLACK | 0.0 | 394.0 (no optimizado — P30 no corrió) |
| TOTAL_DELAY_ADVANCE_COST | 5.0 | 13.0 (no optimizado — P40 no corrió) |
| TOTAL_ORDER_SPLIT_COST | — | 513.0 (no optimizado — P10 no corrió) |
| TOTAL_TRUCK_COUNT | 3.0 | 3.0 |

### Conteo de filas en `finial_order_df`

| Métrica | Stage 1 | Stage 2 |
|---|---|---|
| Filas totales | 208 | 211 |
| Filas asignadas (alloc==1 / alloc>=1) | 206 | 175 |
| Filas rechazadas (alloc==0) | 2 | 36 |
| Líneas únicas asignadas (tras dedup S2) | 206 | **173** |
| Flag "SolverResults" | 206 | 175 |
| Flag "Solver Rejected Line" | 2 | 36 |

### Cruce S1 no-asignadas vs S2 rechazadas

| Conjunto | Tamaño |
|---|---|
| S1 unassigned (2 órdenes) | {660413/sdi=240/sl=1, 660412/sdi=10/sl=1} |
| S2 rejected (36 órdenes) | Todas de PO01/SD 660413 (sdi=110 a 450+) |
| **Intersección** | **0** |
| S2 rechaza órdenes que S1 asignó | **36** |
| S1 rechaza órdenes que S2 asignó | **2** |

Las 36 órdenes que Stage 2 rechaza son órdenes que Stage 1 asignó exitosamente. Las 2 órdenes que Stage 1 rechazó, Stage 2 las asigna. Los conjuntos son completamente disjuntos.

### ¿Por qué Stage 2 rechaza 36 órdenes de PO01?

Stage 2 seleccionó PO01 en **período 3** (vs Stage 1 que usó período 4). El período de entrega afecta qué órdenes son compatibles con cada camión. Las 36 órdenes rechazadas, al ser de PO01, dependen de la capacidad de ese camión en el período seleccionado. Con PO01/period=3, las 36 órdenes no caben o no son compatibles; con PO01/period=4 (Stage 1), Stage 1 sí las asigna.

El optimizador P70 de Stage 2 eligió PO01/period=3 porque **minimiza pallet-spots rechazados** (no conteo de órdenes). Rechazar 36 órdenes pequeñas puede implicar menos pallet-spots rechazados que rechazar 2 órdenes grandes, incluso siendo peor en conteo.

---

## 4. VEREDICTO

### Clasificación de causas

**Causa (1) — Conteo distinto / benigno: PARCIAL — explica 2 de 33 líneas de diferencia**

El 6-key dedup de Stage 2 colapsa 2 órdenes divididas (175 filas → 173 líneas únicas). Estas 2 líneas son órdenes que están en 2 camiones simultáneamente; Stage 2 las cuenta una sola vez, Stage 1 no las tiene duplicadas porque no hay split en Stage 1. Contribución al gap: **2 de 33**.

**Causa (2) — Timeout / benigno pre-existente: VERDADERO para el grueso del gap**

No es timeout (P70 terminó OPTIMAL en ~0.5 s). Pero el comportamiento es igualmente pre-existente y benigno:

- Stage 2 nunca corrió P60 (truck-period optimization) debido al early stop diseñado por lógica de negocio.  
- Stage 2's P70 OPTIMAL solution minimiza **pallet-spots rechazados**, no conteo de órdenes. El solver legítimamente eligió PO01/period=3 como la asignación de camión que minimiza volumen rechazado, aunque resulte en más órdenes rechazadas en conteo.  
- La comparación numérica S1.TOTAL_ORDER_SLACK (2, en órdenes) vs S2.TOTAL_ORDER_SLACK (57, en pallet-spots) es **incomparable**: unidades diferentes. No se puede concluir que Stage 2 es "peor" en slack solo porque 57 > 2.  
- El comportamiento existía antes del fix c1; era invisible porque S1.assign siempre era 0 (bug c1) y BRANCH-A siempre disparaba.

**Causa (3) — Residuo de extracción en Stage 2 / bug nuestro: NO**

La extracción de Stage 2 es correcta. El snapshot cache del fix c1 funciona en Stage 2 exactamente igual que en Stage 1. Las 36 líneas rechazadas corresponden a decisiones reales del solver (order_allocation=0 en el modelo), no a lecturas incorrectas de var.x.

### Resumen ejecutivo

| Causa | Diagnóstico | Líneas explicadas |
|---|---|---|
| Dedup 6-key Stage 2 | Benigno — diseño de Stage 2 | 2 |
| P70 minimiza pallet-spots ≠ orden-count; early stop fija períodos subóptimos para conteo | Benigno pre-existente — comportamiento del modelo | 31 |
| Extracción incorrecta por fix c1 | NO aplica | 0 |

**Total gap explicado: 33/33. No hay bug introducido por fix c1.**

### Impacto en la selección S1/S2

El anomalía no afecta la selección actual:

- BRANCH-A: `S2.assign (173) > S1.assign (206)` → **False** → no dispara  
- BRANCH-B: `S1.proposed_po (3) <= S2.proposed_po (3)` → **True** → **Stage 1 gana**

El resultado de selección es correcto. Stage 1 gana vía BRANCH-B, no porque BRANCH-A haya fallado.

### Nota sobre la premisa "la región factible de S2 contiene la de S1"

La premisa es matemáticamente correcta para el espacio de decisión (Stage 2 puede replicar cualquier asignación binaria de Stage 1 fijando las variables enteras a 0 ó 1). Pero las dos etapas optimizan objetivos en **unidades distintas**: Stage 1 minimiza conteo de órdenes rechazadas; Stage 2 minimiza volumen de pallet-spots rechazados. La solución óptima de Stage 2 para SU objetivo no es necesariamente mejor en el objetivo de Stage 1. La inferencia "S2.assign_count ≥ S1.assign_count" solo valdría si ambas etapas maximizaran la misma métrica — y no lo hacen.

---

## Archivos modificados en esta sesión de diagnóstico

Ninguno. Solo lectura de CSVs de output, lectura de archivos de lógica (sin modificación), y script efímero en scratchpad (no persistido en el proyecto).
