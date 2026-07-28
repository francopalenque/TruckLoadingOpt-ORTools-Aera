# Verify Report — TruckLoadingOpt-ORTools

**Fecha:** 2026-07-17  
**Alcance:** Pasada de verificación de solo lectura.  
**Ningún archivo de lógica fue modificado.**

---

## 1. Resolución de imports entre módulos

### 1.1 Estilo de imports usado

Todos los imports intra-proyecto en los archivos de model-building usan **rutas de paquete calificadas completas** rooted en `src.`. No hay ningún import relativo (`from . import` / `from .. import`) ni ningún import de módulo por nombre corto sin calificar.

| Archivo | Imports intra-proyecto (con línea) |
|---|---|
| `stage_one/model_building/model_building.py` | L2: `from src.stage_one.model_building.decision_variables import DecisionVariable`<br>L3: `from src.stage_one.model_building.constraints import Constraints`<br>L4: `from src.stage_one.model_building.objectives import ModelObjectives`<br>L6: `from src.common import constants`<br>L7: `from src.common.utilities import write_lp` |
| `stage_one/model_building/reshuffling_allocation_model.py` | L2: `from src.stage_one.model_building.decision_variables import ReshufflingStageOneDecisionVariable`<br>L3: `from src.stage_one.model_building.constraints import ReshufflingStageOneConstraints`<br>L4: `from src.stage_one.model_building.objectives import ModelObjectives`<br>L6: `from src.common import constants`<br>L7: `from src.common.utilities import write_lp`<br>L9: `from src.common.utils import find_valid_period` |
| `stage_one/model_building/constraints.py` | L2: `from src.common.logger_config import logger`<br>L3: `from src.common.constants import order_in_original_truck_slack, ...` |
| `stage_one/model_building/objectives.py` | L2: `from src.common.logger_config import logger`<br>L3: `from src.common.constants import lp_file`<br>L5: `from src.common.utilities import write_lp` |
| `stage_one/model_building/decision_variables.py` | L2: `from src.common.logger_config import logger`<br>L3: `from src.common.constants import order_in_original_truck_slack, ...` |
| `stage_two/model_building/model_building.py` | L2: `from src.stage_two.model_building.decision_variables import DecisionVariable`<br>L3: `from src.stage_two.model_building.constraints import Constraints`<br>L4: `from src.stage_two.model_building.objectives import ModelObjectives`<br>L6: `from src.common import constants`<br>L7: `from src.common.utilities import write_lp` |
| `stage_two/model_building/reshuffling_allocation_model.py` | L2: `from src.stage_two.model_building.decision_variables import ReshufflingStageTwoDecisionVariable`<br>L3: `from src.stage_two.model_building.constraints import ReshufflingStageTwoConstraints`<br>L4: `from src.stage_two.model_building.objectives import ModelObjectives`<br>L6: `from src.common import constants`<br>L7: `from src.common.utilities import write_lp`<br>L9: `from src.common.utils import find_valid_period` |
| `stage_two/model_building/constraints.py` | L2: `from src.common.logger_config import logger`<br>L3-4: `from src.common.constants import order_in_original_truck_slack_stage_two, ...` |
| `stage_two/model_building/objectives.py` | L2: `from src.common.logger_config import logger`<br>L3: `from src.common.constants import lp_file`<br>L5: `from src.common.utilities import write_lp` |
| `stage_two/model_building/decision_variables.py` | L3: `from src.common.logger_config import logger`<br>L4-5: `from src.common.constants import order_in_original_truck_slack_stage_two, ...` |

Los archivos hoja (`constraints.py`, `objectives.py`, `decision_variables.py`) **no importan nada de su propio paquete ni de la otra etapa**; solo importan de `src.common.*`, `gurobipy` y stdlib.

### 1.2 ¿Hay imports cruzados entre stage_one y stage_two?

**NO.** Ningún archivo de stage_one importa de stage_two ni viceversa. Cada etapa es completamente autocontenida en sus referencias intra-proyecto.

### 1.3 Riesgo de shadowing en sys.modules

**No hay riesgo bajo el código actual.** Porque los imports usan rutas calificadas completas:

```
sys.modules["src.stage_one.model_building.constraints"]  ← clave distinta
sys.modules["src.stage_two.model_building.constraints"]  ← clave distinta
```

Estas claves nunca colisionan, aunque los archivos físicos tengan el mismo nombre (`constraints.py`). Un riesgo de shadowing existiría **solo si** algún código agregara `src/stage_one/model_building/` o `src/stage_two/model_building/` directamente a `sys.path`, lo que haría que `import constraints` fuera ambiguo. Nada en el código actual hace eso.

### 1.4 Cómo manejaba el original Gurobi los nombres con espacios

**El proyecto Gurobi original nunca pudo ejecutarse via imports Python estándar.** Sus directorios físicos son:

```
src/Stage_One/model building/     ← espacio, todo minúscula
src/Stage_Two/Model Building/     ← espacio, CamelCase (inconsistente con Stage_One)
```

Sin embargo, los propios archivos dentro de esas carpetas ya usaban:

```python
# Stage_One/model building/model_building.py, línea 2:
from src.stage_one.model_building.decision_variables import DecisionVariable

# Stage_Two/Model Building/model_building.py, línea 2:
from src.stage_two.model_building.decision_variables import DecisionVariable
```

Estas rutas de import (`src.stage_one.model_building`, `src.stage_two.model_building`) **no corresponden** a la estructura física de directorios. Python no puede importar un paquete cuyo componente de ruta contiene un espacio. La copia ORTools no introdujo este esquema de calificación — lo heredó del original — y lo hizo funcionalmente correcto renombrando los directorios para que coincidan con lo que los imports ya esperaban.

**Nota de inconsistencia en el original:** Stage_One usa `model building` (minúscula, espacio) y Stage_Two usa `Model Building` (CamelCase, espacio). Ambos se renombraron a `model_building` en la copia.

---

## 2. Diff de contenido lógico (ORTools vs Gurobi)

Se compararon los 10 archivos de model-building entre ambas copias, mapeando el renombrado de directorios:

| Gurobi (ruta original) | ORTools (ruta renombrada) |
|---|---|
| `src/Stage_One/model building/X.py` | `src/stage_one/model_building/X.py` |
| `src/Stage_Two/Model Building/X.py` | `src/stage_two/model_building/X.py` |

### Resultado

| Archivo | ¿Idéntico al equivalente Gurobi? | Diferencias no-import |
|---|---|---|
| `stage_one/model_building/constraints.py` | **SÍ** | Ninguna |
| `stage_one/model_building/objectives.py` | **SÍ** | Ninguna |
| `stage_one/model_building/decision_variables.py` | **SÍ** | Ninguna |
| `stage_one/model_building/model_building.py` | **SÍ** | Ninguna |
| `stage_one/model_building/reshuffling_allocation_model.py` | **SÍ** | Ninguna |
| `stage_two/model_building/constraints.py` | **SÍ** | Ninguna |
| `stage_two/model_building/objectives.py` | **SÍ** | Ninguna |
| `stage_two/model_building/decision_variables.py` | **SÍ** | Ninguna |
| `stage_two/model_building/model_building.py` | **SÍ** | Ninguna |
| `stage_two/model_building/reshuffling_allocation_model.py` | **SÍ** | Ninguna |

**Los 10 archivos son byte-por-byte idénticos entre ambas copias.** Ni siquiera difieren en líneas de import: los archivos del original Gurobi ya contenían exactamente los mismos imports calificados (`src.stage_one.*`, `src.stage_two.*`) que la copia ORTools. La operación de copia no modificó ningún contenido de archivo, solo renombró directorios.

---

## 3. Confirmación de `reshuffling_allocation_model.py` en Stage Two

**CONFIRMADO. El archivo existe en ambas copias y es no-vacío.**

| | ORTools | Gurobi |
|---|---|---|
| Ruta | `src/stage_two/model_building/reshuffling_allocation_model.py` | `src/Stage_Two/Model Building/reshuffling_allocation_model.py` |
| Existe | SÍ | SÍ |
| Líneas | 197 | 197 |
| Primera línea | `import time` | `import time` |

El recon previo lo marcó como "inferido" — ahora está verificado directamente.

---

## 4. Observación de alcance (sin acción requerida)

Los 10 archivos de model-building en la copia ORTools siguen importando `gurobipy` a nivel de módulo (`from gurobipy import GRB, LinExpr, min_` / `import gurobipy`). Esto es esperado y correcto para Fase 1: el stub de gurobipy inyectado en `handler.py` hace que esos imports resuelvan sin error en LOCAL mode. La sustitución por OR-Tools es el objetivo de Fase 2, no de Fase 1.

---

*Generado automáticamente — pasada de solo lectura.*
