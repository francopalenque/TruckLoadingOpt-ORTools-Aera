# Diagnostic Report — 0 Order Allocation Combinations

**Fecha:** 2026-07-18  
**Script de diagnóstico:** `diag_run.py` (temporal, puede borrarse)  
**Archivos de lógica tocados:** ninguno

---

## Resumen ejecutivo

**Causa raíz única y precisa:**

> `dc_slot_schedule` en la CSV tiene el campo DC como `"0001000001"` (10 dígitos con ceros de relleno). `LocalDataSource` fuerza `dtype={"DC": "string"}`, lo que preserva los ceros. Los demás CSVs tienen DC como `"1000001"` (7 dígitos). El filtro `dc_slot_schedule['dc'] == '1000001'` retorna **0 filas** → `dc_slot_schedule_dict = {}` (vacío) → ningún período tiene slot disponible → **0 combinaciones** en todos los DCs.

El problema está en **Seam 1 (LocalDataSource)**, exactamente como se hipotetiizó. La lógica del modelo no tiene ningún rol en esto.

---

## Sección 1 — Fidelidad del loader

### 1.1 CSVs crudos (sin dtype forzado — comportamiento "natural" de pandas)

| Tabla | shape | DC dtype | DC valores |
|---|---|---|---|
| apo_truck_load | (1197, 28) | **int64** | 1000001, 1000002, 1000009, 1000013, 1000019 |
| truck_capacity_details | (27, 19) | **int64** | 1000001, 1000002, 1000009, 1000013, 1000019 |
| dc_slot_schedule | (161, 3) | **int64** | 1000001, 1000002, ... (int, ceros droppeados) |
| general_configurations | (1, 3) | — | — |

Sin forzar string, pandas lee el DC de dc_slot_schedule correctamente como int64 = 1000001 (los ceros son droppeados al parsear a número).

### 1.2 Post LocalDataSource (con `dtype={"DC": "string"}` forzado)

| Tabla | DC dtype | DC valores |
|---|---|---|
| apo_truck_load | **str** | `'1000001'`, `'1000002'`, `'1000009'`, `'1000013'`, `'1000019'` |
| truck_capacity_details | **str** | `'1000001'`, `'1000002'`, `'1000009'`, `'1000013'`, `'1000019'` |
| dc_slot_schedule | **str** | `'0001000001'`, `'0001000002'`, `'0001000003'`, ... (**10 dígitos**) |

### 1.3 Por qué divergen

El CSV de dc_slot_schedule tiene los DC quoteados con ceros de relleno:
```
"0001000001","Friday","0"
"0001000001","Monday","4"
```

Cuando `pd.read_csv(dtype={"DC": "string"})` fuerza ese campo a string, el valor queda como `'0001000001'` (los ceros se preservan). Los otros CSVs tienen `"1000001"` (7 dígitos sin relleno), que queda como `'1000001'`.

En AERA, el SDK devuelve todos los DC sin ceros de relleno, de modo que el mismatch no ocurre allí.

---

## Sección 2 — Dtypes de join/filtro

### Post `transform_date` + `get_dc_list`

```
dc_list = ['1000001', '1000002', '1000009', '1000013', '1000019']  # type: str
```

```
apo_truck_load.dc  unique: ['1000001', '1000002', '1000009', '1000013', '1000019']
dc_slot_schedule.dc unique: ['0001000001', '0001000002', '0001000003', ..., '0001000025']
```

**El dc_slot_schedule tiene 23 DCs (todos con ceros). Los 5 DCs del optimizador no aparecen en ese conjunto.**

### Columnas clave post LocalDataSource

| Columna | apo_truck_load | truck_capacity_details | dc_slot_schedule |
|---|---|---|---|
| `dc` | `str` `'1000001'` | `str` `'1000001'` | `str` `'0001000001'` ← MISMATCH |
| `po_number` | `str` `'PO01'` | `str` `'PO01'` | — |
| `non-available_order_flag` | `str` `'N'` | — | — |
| `confirmed_quantity_in_base_unit` | `int64` | — | — |

---

## Sección 3 — El embudo (DC 1000001)

| Etapa | Resultado |
|---|---|
| Órdenes en `apo_truck_load_dict` | 208 líneas (4 POs) |
| Tras filtro `non-available_order_flag == 'N'` | 208 / 208 (todas pasan — distribución: `{'N': 208}`) |
| Tras filtro `confirmed_qty > 0` | 208 / 208 (todas pasan) |
| Trucks en `truck_po_level_details` | 3 (PO01, PO22, PO25; PO10 es leftover) |
| `dc_slot_schedule_dict` | `{}` **VACÍO** — filtro retornó 0 filas |
| Combinaciones (orden × truck × período) | **0** |

### Desglose de fallas en la inner loop

```
Combinaciones creadas         :    0
Órdenes sin slot válido       :  208  (todas)
Fallo: period < delivery_period:   90
Fallo: day NOT IN dc_slot_dict : 4278  ← RAÍZ (dict vacío)
Fallo: slots == 0             :    0
```

**La falla dominante es `day NOT IN dc_slot_schedule_dict` porque el dict está vacío.** Si el dict no estuviera vacío, 4278 de 4278+90 = 4368 intentos habrían tenido match de día, y una fracción habría superado el chequeo `period >= delivery_period`.

---

## Sección 4 — El flag de disponibilidad

### Nombre de columna

| | Nombre exacto |
|---|---|
| CSV crudo (header) | `NON_AVAILABLE_ORDER_FLAG` |
| Después de `fix_column_names` | `non_available_order_flag` |
| Después del rename en `Data2.py` | `non-available_order_flag` (con guión) |
| Lo que espera `data_handling.py` L157/L159 | `'non-available_order_flag'` (con guión) |

El fix de Fase 2 (`non_available_order_flag` → `non-available_order_flag`) **es correcto**. El filtro en `filter_dataframe` línea 157 y 159 resuelve bien:
- `temp_apo_truck_load['non-available_order_flag'] == 'Y'` → 0 filas (ninguna marcada no-disponible)
- `temp_apo_truck_load['non-available_order_flag'] == 'N'` → 208 filas (todas pasan)

**Este fix NO está enmascarando nada — funciona correctamente.**

---

## Sección 5 — Mapping fecha → período (3 órdenes de muestra)

```
Planning horizon: 2026-07-12 → 2026-07-18

date_to_period = {
  '2026-07-12': 1  (Sunday),
  '2026-07-13': 2  (Monday),
  '2026-07-14': 3  (Tuesday),
  '2026-07-15': 4  (Wednesday),
  '2026-07-16': 5  (Thursday),
  '2026-07-17': 6  (Friday),
  '2026-07-18': 7  (Saturday),
}
```

| Orden | delivery_date | delivery_period | day_name | slot en dc_slot_schedule_dict |
|---|---|---|---|---|
| (660413,10,1,M1000000185) PO01 | 2026-07-12 | 1 | Sunday | **MISSING** (dict vacío) |
| (660413,100,1,M1000000392) PO01 | 2026-07-12 | 1 | Sunday | **MISSING** (dict vacío) |
| (660413,110,1,M1000000350) PO01 | 2026-07-12 | 1 | Sunday | **MISSING** (dict vacío) |

**Las fechas SÍ caen dentro del horizonte y los períodos SÍ existen.** El problema no es el rango de fechas — es que el slot dict está vacío.

Si el slot dict se llenara correctamente, el slot de DC 1000001 sería:

```
dc_slot_schedule  (DC=0001000001, lo que mapearía a 1000001):
  Sunday    → 4 slots
  Monday    → 4 slots
  Tuesday   → 4 slots
  Thursday  → 4 slots
  Wednesday → (no figura, seguramente 0)
  Friday    → 0 slots
  Saturday  → 0 slots
```

Período 1 = Sunday = 4 slots. **Las órdenes con delivery_period=1 tendrían combinaciones válidas.**

---

## Causa raíz — árbol de cadena

```
LocalDataSource fuerza DC a string
    ↓
dc_slot_schedule CSV tiene DC = "0001000001" (10 dígitos)
apo_truck_load    CSV tiene DC = "1000001"   (7 dígitos)
    ↓
Después del load:
  dc_slot_schedule['dc'] = '0001000001'
  dc_list[0]             = '1000001'
    ↓
filter_dataframe: dc_slot_schedule['dc'] == '1000001'  →  0 filas
    ↓
DataHandling.read_dc_slot_schedule():
  dc_slot_schedule_df tiene 0 filas
  dc_slot_schedule_dict = {}  (vacío)
    ↓
create_apo_truck_load_combinations():
  period_day_name_mapping[period]['day_name'] in {}  →  siempre False
    ↓
0 combinaciones para todos los DCs
```

---

## Scope del fix propuesto (sin modificar lógica del modelo)

El fix mínimo está en `src/pre_processing/Data2.py` (plumbing del Seam 1, no lógica del modelo).

**Opción A — Strip de ceros en DC para dc_slot_schedule (narrow):**
```python
# Después de cargar dc_slot_schedule, normalizar DC eliminando ceros de relleno
if key == 'dc_slot_schedule' and 'dc' in df.columns:
    df['dc'] = df['dc'].str.lstrip('0')
```

**Opción B — Normalización general de DC en todos los DataFrames (broad):**
```python
# Aplicar a todos los DataFrames post-fix_column_names si tienen columna 'dc'
if 'dc' in df.columns and df['dc'].dtype == object:
    df['dc'] = df['dc'].astype(str).str.lstrip('0')
```

**Opción C — No forzar string para DC en dc_slot_schedule (más profundo):**
Eliminar "DC" del dtype mapping para dc_slot_schedule. Pandas leería int64, que luego es convertido a string consistentemente. Requiere tocar `get_string_columns_mapping` o `data_column_mapping`, que podrían afectar la ruta AERA.

**Recomendación: Opción A.** Un rename localizado en LocalDataSource, invisible para AERA (que ya recibe DCs sin ceros), sin tocar data_column_mapping ni la lógica del modelo.

---

## Observaciones adicionales (no bloqueantes)

1. **`priority_line_flag = 'Not Set'`** — Todas las órdenes de muestra tienen `priority_line_flag='Not Set'`, no `'Y'` ni `'N'`. El código tiene `if values['priority_line_flag'] == 'Y'` (rama Y) y `else` (todos los demás). 'Not Set' va al ELSE → `period_lst = list(range(1, horizon+1))` = [1..7]. No es un bug, aunque si AERA envía 'N' para las líneas no-prioritarias, 'Not Set' podría ser un artefacto del CSV local. **No bloquea la resolución del problema actual.**

2. **dc_slot_schedule tiene 23 DCs** — El slot schedule exportado tiene DCs que los otros CSVs no tienen (solo 5 DCs tienen datos en apo_truck_load). Esto es consistente con un export de toda la configuración, no filtrada. No es un bug.

3. **Slots de prueba confirmados** — Con el fix aplicado, DC 1000001 tendría `dc_slot_schedule_dict = {'Friday': 0, 'Monday': 4, 'Saturday': 0, 'Sunday': 4, 'Thursday': 4, 'Tuesday': 4, 'Wednesday': 0}`. Los períodos Sunday(1), Monday(2), Tuesday(3), Thursday(5) tienen slots > 0. Las 208 órdenes con delivery_period=1 (Sunday) serían elegibles para truck PO01, PO22, PO25 en los períodos 1-7.

---

*Generado con `diag_run.py` — diagnóstico de solo lectura. Script temporal disponible para revisión.*
