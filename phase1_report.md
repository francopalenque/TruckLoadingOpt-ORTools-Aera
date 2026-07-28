# Phase 1 Report — TruckLoadingOpt-ORTools

**Fecha:** 2026-07-17  
**Scope:** Análisis de idioms de Gurobi para diseño del shim (Fase 2).  
Ningún modelo de solver fue modificado en esta fase.

---

## 1. Usos de `min_`

### Patrón único (idéntico en Stage_One y Stage_Two)

| Archivo | Línea | Clase | Función | Expresión |
|---------|-------|-------|---------|-----------|
| `src/Stage_One/model building/constraints.py` | 372 | `ReshufflingStageOneConstraints` | `create_min_truck_under_utilization_constraints()` | `truck_under_utilization == min_(unused_weight_percent, unused_volume_percent, unused_pallet_percent)` |
| `src/Stage_Two/Model Building/constraints.py` | 440 | `ReshufflingStageTwoConstraints` | `create_min_truck_under_utilization_constraints()` | Ídem |

#### Qué expresa
Gurobi `min_(v1, v2, v3)` crea una **general constraint** que fija una variable continua al mínimo de tres variables continuas (porcentajes de espacio no utilizado de peso, volumen y pallets).  
Semántica: `truck_under_utilization[po, period] = min(unused_weight%, unused_volume%, unused_pallet%)`

#### Estado actual en producción
**INACTIVO.** Ambas funciones son llamadas únicamente si `stage_one_truck_unused_cost = True` / `stage_two_truck_unused_cost = True` (`constants.py` líneas 273 y 312), que actualmente están en `False`. El código muerto no bloquea la ejecución de Fase 2.

#### Estrategia de linealización para el shim
pywraplp no tiene `AddGenConstrMin` (eso es SCIP C++ API, no la capa Python pywraplp). La linealización estándar con tres variables:

```
z = min(a, b, c)
```

Se modela con big-M o con tres constraints + una variable auxiliar:

```
z <= a
z <= b  
z <= c
z >= a - M*(1 - delta_a)   # al menos uno se iguala
z >= b - M*(1 - delta_b)
z >= c - M*(1 - delta_c)
delta_a + delta_b + delta_c >= 1
delta_a, delta_b, delta_c ∈ {0, 1}
```

Dado que el código está inactivo, se puede posponer a Fase 2b o simplificar a las tres constraints de upper bound (z <= a, z <= b, z <= c) que garantizan el mínimo cuando el objetivo penaliza valores altos de z.

**Recomendación:** Implementar la versión simplificada (solo upper bounds) en el shim y marcar con `# TODO-min_` para revisión posterior.

---

## 2. Patrones de `LinExpr`

### 2.1 Patrón acumulativo en constraints (dominante)

```python
# Todos los constraints siguen este patrón en ambos stages:
expr = LinExpr()
for key, po_list in self.input_data.order_truck_mapping.items():
    for (po, period) in po_list:
        expr.add(self.model_vars.order_allocation_var[(..., po, period)], 1)
    self.model.addConstr(expr == 1 - slk, ct_name)
    expr.clear()  # reuse en el siguiente key
```

**Firma usada:** `expr.add(var, coeff)` — dos argumentos, var primero, coeff después.  
`expr.clear()` se llama explícitamente para reusar el objeto entre iteraciones.

### 2.2 Patrón en objectives (blended y manual-hierarchical)

```python
# Blended (create_blended_objectives):
expression = LinExpr()
for key, value in self.objectives.items():
    expression.add(value['weight'] * global_variables[key])   # un argumento: LinExpr = scalar * Var

# Manual hierarchical (create_manual_hierarchical_objectives):
objective_expression_dict = {}
for key, value in self.objectives.items():
    if value['priority'] not in objective_expression_dict:
        objective_expression_dict[value['priority']] = LinExpr()
    objective_expression_dict[value['priority']].add(
        self.model_vars.global_var[key] * value['weight']     # un argumento: LinExpr = Var * scalar
    )
```

**Firma usada:** `expr.add(scalar * var)` — un argumento donde el argumento es ya un `LinExpr` producido por el operador `*` de Gurobi Var.

### 2.3 Resumen de firmas de LinExpr.add()

| Forma | Ejemplo en código | Frecuencia |
|-------|------------------|------------|
| `expr.add(var, coeff)` | constraints (todos) | ~30 usos |
| `expr.add(scalar * var)` | objectives | ~5 usos |

**No se usa `quicksum` en ningún archivo.**

### 2.4 Implicaciones para el shim

El shim necesita:

1. `LinExpr()` — constructor vacío.
2. `LinExpr.add(term, coeff=1.0)` — acepta tanto `(var, coeff)` como `(lin_expr,)`. Detectar tipo en runtime.
3. `Var.__mul__(scalar)` y `Var.__rmul__(scalar)` → devuelve `LinExpr` para soportar `scalar * var`.
4. `LinExpr.clear()` — reinicia la expresión (lista de términos vacía).
5. `LinExpr.__le__`, `LinExpr.__ge__`, `LinExpr.__eq__` — producen objetos de constraint que `addConstr` consume.

---

## 3. Otros idioms de Gurobi a cubrir en el shim

### 3.1 Indicator constraints (`>>`) — INACTIVOS

```python
# Stage_One/constraints.py líneas 383-385, Stage_Two líneas 451-453
self.model.addConstr(
    (truck_under_utilization_range_trigger == 1) >> (truck_under_utilization >= 5),
    name=ct_name
)
self.model.addConstr(
    (truck_under_utilization_range_trigger == 0) >> (truck_under_utilization <= 5),
    name=ct_name
)
```

Operador `>>` en Gurobi crea una constraint indicadora: si `binary_var == value`, entonces impone `linear_constraint`.

**Estado:** INACTIVO (`stage_one_truck_count_not_within_range = False`).  
**Linealización con big-M para el shim:**
```
# (trigger == 1) >> (x >= 5)
x >= 5 - M * (1 - trigger)
# (trigger == 0) >> (x <= 5)
x <= 5 + M * trigger
```
donde M = 100 (UB de under_utilization_var).

### 3.2 `model.addConstr` — firmas mixtas

```python
# Positional name (constraints.py):
self.model.addConstr(expr == 1 - slk, ct_name)  # segundo arg posicional
# Keyword name (objectives.py):
self.model.addConstr(expression <= obj_val * (1 + 1e-4), name=f"ct_...")
# Indicator (inactivo):
self.model.addConstr((trigger == 1) >> (expr >= val), name=ct_name)
```

El shim debe soportar `addConstr(constraint, name=None)` con el nombre como posicional o keyword.

### 3.3 `model.addVar` — firmas usadas

```python
model.addVar(lb=0, ub=1, name=var_name, vtype=GRB.BINARY)     # binaria
model.addVar(lb=0, ub=N, name=var_name, vtype=GRB.INTEGER)    # entera
model.addVar(lb=0, ub=N, name=var_name)                        # continua (sin vtype)
model.addVar(lb=0, ub=N, name=var_name, vtype=GRB.CONTINUOUS)  # continua explícita
```

`GRB.BINARY`, `GRB.INTEGER`, `GRB.CONTINUOUS` son los únicos vtypes usados.

### 3.4 `model.status` y status codes

```python
# model_building.py (ambas stages):
if self.optimization_model.status in [gurobipy.GRB.OPTIMAL, gurobipy.GRB.TIME_LIMIT, gurobipy.GRB.INTERRUPTED]:
    raw_output_dict['optimization_status'] = constants.optimization_status[self.optimization_model.status]
```

`constants.optimization_status = {2: 'OPTIMAL', 9: 'TIME_LIMIT_REACHED', 11: 'INTERRUPTED_BY_USER'}`

El status es comparado directamente como entero. El shim debe exponer `.status` como entero compatible con este dict.

Mapeo pywraplp → valores del shim:
| pywraplp status | Valor shim |
|----------------|------------|
| `OPTIMAL` | 2 |
| `FEASIBLE` | 9 (tratarlo como TIME_LIMIT con solución parcial) |
| `INFEASIBLE` | status separado — devolver string 'INFEASIBLE' directamente |
| `ABNORMAL` / `NOT_SOLVED` | mapear a string de error |

### 3.5 `model.objVal` (no `.ObjVal`)

```python
obj_val = self.model.objVal   # minúscula 'al'
```

El shim debe exponer `.objVal` (lowercase). En pywraplp: `solver.Objective().Value()`.

### 3.6 `clear_model()` en utils.py

```python
def clear_model(model):
    model.remove(model.getGenConstrs())
    model.remove(model.getConstrs())
    model.remove(model.getVars())
    model.remove(model.getQConstrs())
    model.remove(model.getSOSs())
    model.setObjective(0.0)
    model.NumObj = 0
    model.update()
    return model
```

Llama a `getGenConstrs()`, `getConstrs()`, `getVars()`, `getQConstrs()`, `getSOSs()`, `setObjective(0.0)`, `model.NumObj = 0` (atributo de escritura), `update()`.

**Estrategia recomendada para el shim:** En `clear_model()`, en vez de implementar `getGenConstrs()` / `remove()` / etc., instanciar un solver SCIP fresco y reasignarlo a `model._solver`. Los métodos de Gurobi que `clear_model` llama deben simplemente retornar listas vacías y ser no-ops en pywraplp.

### 3.7 `model.dispose()` al final del handler

```python
opt_client.model.dispose()
```

No-op en el shim (pywraplp no requiere liberación explícita en Python).

### 3.8 `setObjectiveN` — INACTIVO en producción

```python
# create_hierarchical_objectives() — nunca llamada (manual_hierarchical=True)
self.model.setObjectiveN(expr, priority=p, weight=1, index=i, name="Priority " + str(p))
self.model.modelSense = self.objective_sense
```

Función presente en código pero no ejecutada en producción (`manual_hierarchical = True`). El shim puede implementar un no-op o lanzar `NotImplementedError` si se llama.

---

## 4. Confirmación: `Stage_Two/Model Building/reshuffling_allocation_model.py`

**CONFIRMADO que existe.** No era solo inferido por el recon.

Ruta real: `TruckLoadingOpt-Gurobi/src/Stage_Two/Model Building/reshuffling_allocation_model.py`

Contiene la clase `ReshufflingStageTwoModelConstruction` con el método `allocation_model_construction()`, simétrico a `ReshufflingStageOneModelConstruction`. Ambos importan `import gurobipy` y usan `model.addVar`, `model.addConstr`, `model.optimize` y el mapeo de `constants.optimization_status`.

---

## 5. Columna `rank` ausente en `truck_capacity_details`

**Diagnóstico:** La columna `Rank` está en `data_column_mapping['truck_capacity_details']` (constants.py línea 196) pero **no aparece en el CSV local** `TRUCKLOAD_UTILIZATION_07-15-2026-08-46-56.csv`.

**Impacto:** Ninguno en la práctica. `convert_dict()` itera sobre las claves del mapping e intenta acceder a `df[col]`; como el CSV no tiene "Rank", la excepción es capturada por el `except: pass` bare ya presente en `convert_dict`. La columna simplemente no existe en el DataFrame resultante.

**Verificación de uso downstream:** Búsqueda exhaustiva en todos los archivos Python de `src/` no encontró ningún acceso a `rank`, `rank_`, ni columna "Rank" en el código de data handling, constraints, objectives o post-processing. La entrada en `data_column_mapping` es residual (probablemente de una versión anterior del reporte AERA) y no tiene efecto funcional.

**Acción en LocalDataSource:** No se sintetiza la columna. Se documenta aquí para trazabilidad. Si una versión futura del reporte AERA incluye "Rank", el LocalDataSource la leerá automáticamente.

**Columna "Total Order Quantity" vs "Total Qty":** Diferencia análoga — `data_column_mapping` define "Total Qty" pero el CSV tiene "Total Order Quantity". Búsqueda downstream confirma que `total_qty` tampoco se accede en el código; la columna relevante es `leftover_truck_flag` (presente en CSV pero ausente del mapping, leída correctamente con dtype auto-detectado).

---

## 6. Resumen de superficie del shim (Fase 2)

| API Gurobi | Prioridad | Notas |
|-----------|-----------|-------|
| `Model.addVar(lb, ub, name, vtype)` | Alta | BINARY, INTEGER, CONTINUOUS |
| `Model.addConstr(expr, name)` | Alta | positional y keyword name |
| `Model.setObjective(expr, sense)` | Alta | llamado en cada nivel del loop jerárquico |
| `Model.optimize()` | Alta | corazón del shim |
| `Model.status` (int) | Alta | {2, 9, 11} para el dict de constants |
| `Model.objVal` | Alta | lowercase 'al' |
| `Model.dispose()` | Media | no-op |
| `LinExpr()` | Alta | constructor vacío |
| `LinExpr.add(var, coeff)` y `LinExpr.add(lin_expr)` | Alta | dos firmas |
| `LinExpr.clear()` | Alta | reusar objeto |
| `Var.__mul__` / `Var.__rmul__` | Alta | scalar * var → LinExpr |
| `LinExpr.__le__/__ge__/__eq__` | Alta | constraint objects |
| `GRB.BINARY / INTEGER / CONTINUOUS / MINIMIZE / MAXIMIZE / OPTIMAL / TIME_LIMIT / INTERRUPTED / INFEASIBLE` | Alta | constantes numéricas |
| `clear_model()` (utils.py) | Alta | reimplementar con solver fresco |
| `Model.ModelName` | Media | atributo de escritura — no-op |
| `Model.setParam('MIPGap', v)` | Media | SCIP param equivalent |
| `Model.setParam('TimeLimit', v)` | Media | pywraplp: `set_time_limit(v * 1000)` |
| `model.update()` | Baja | no-op en pywraplp |
| `model.NumObj = 0` | Baja | atributo ignorable |
| `Model.setObjectiveN(...)` | Baja | INACTIVO — no-op o NotImplementedError |
| `Model.modelSense` | Baja | INACTIVO |
| `min_(v1, v2, v3)` | Baja | INACTIVO — big-M linearization cuando se active |
| Indicator `>>` | Baja | INACTIVO — big-M linearization cuando se active |
| `getGenConstrs/getConstrs/getVars/getQConstrs/getSOSs/remove` | Media | solo en `clear_model()` — devolver [] |
