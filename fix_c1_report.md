# Fix Report: Bug (c1) — pywraplp Solution Lost After addConstr of Last Lexicographic Level

**Date:** 2026-07-20  
**File modified:** `src/common/gurobi_compat.py` only  
**Tests:** 9/9 unit tests PASS  
**Validator:** 12/12 checks PASS  
**Stage selection before fix:** Stage 2 always (BRANCH-A, S1.assign=0)  
**Stage selection after fix:** Stage 1 wins all 5 DCs (BRANCH-B)

---

## Root Cause (confirmed in diagnostic_stage_one_p2.md)

In pywraplp/OR-Tools, calling `solver.Constraint(lb, ub, name)` after a successful `Solve()` resets the solver's internal state to `NOT_SOLVED`. Subsequent calls to `variable.solution_value()` return 0 (the variable's lower bound) instead of the solved value.

Gurobi preserves the MIP solution until the next `model.optimize()` call, regardless of intervening `addConstr()` calls. The original model-building code (objectives.py) relies on this Gurobi behavior.

**The specific failure point:**

```
objectives.py — create_manual_hierarchical_objectives():
  ...
  P20: setObjective → optimize()  → trucks=5, orders=251 INSIDE optimize() ✓
       addConstr(ITEM_SLACK ≤ 0)  ← THIS resets pywraplp to NOT_SOLVED
                                     ↓
model_building.py reads var.x    → trucks=0, orders=0 ✗
```

P60, P50, P30 intermediate addConstr calls also reset pywraplp, but a subsequent `optimize()` call restores the solution. P20 is the last level — there is no subsequent optimize() call to restore it.

---

## Fix — Solution Snapshot Cache in `gurobi_compat.py`

Added a Python-level solution cache to `Model` that is populated immediately after each successful `Solve()`, before pywraplp has any chance to lose the solution. The cache lives in Python — completely independent of pywraplp's internal state — so `addConstr()` calls cannot affect it.

### Changes to `src/common/gurobi_compat.py`

**1. `Var.__init__` — accept back-reference to owning Model:**
```python
def __init__(self, pywraplp_var, model=None):
    self._var = pywraplp_var
    self._model = model
```

**2. `Var.x` / `Var.X` — read from snapshot when available:**
```python
@property
def x(self):
    if self._model is not None and self._model._solution_cache is not None:
        return self._model._solution_cache.get(self._var.name(), 0.0)
    return self._var.solution_value()  # fallback: pre-solve or no-model
```

**3. `Model.__init__` — initialize cache attributes:**
```python
self._solution_cache = None  # dict(var_name → float) populated by optimize()
self._obj_cache = None       # float populated by optimize()
```

**4. `Model._reset()` — clear cache on reset:**
```python
self._solution_cache = None
self._obj_cache = None
```

**5. `Model.addVar()` — pass self to Var:**
```python
return Var(pv, model=self)
```

**6. `Model.optimize()` — snapshot immediately after Solve():**
```python
raw = self._solver.Solve()
self._status = _PYWRAPLP_TO_GRB.get(raw, 12)
obj_val = self._solver.Objective().Value()
print(f"[SCIP] status={self._status} objVal={obj_val:.4f}", flush=True)

# Snapshot all variable values while pywraplp still holds the solution.
# raw=0 (OPTIMAL) and raw=1 (FEASIBLE/TIME_LIMIT) both have a valid assignment.
# addConstr() after this point resets pywraplp to NOT_SOLVED; the snapshot
# keeps var.x correct.  On INFEASIBLE/UNBOUNDED the previous snapshot is
# preserved — matches Gurobi, which also keeps the last feasible solution.
if raw in (0, 1):
    n = self._solver.NumVariables()
    self._solution_cache = {
        self._solver.variable(i).name(): self._solver.variable(i).solution_value()
        for i in range(n)
    }
    self._obj_cache = obj_val
```

**7. `Model.objVal` — serve cached value:**
```python
@property
def objVal(self):
    if self._obj_cache is not None:
        return self._obj_cache
    return self._solver.Objective().Value()
```

### Invariants

| Scenario | Cache behavior |
|---|---|
| OPTIMAL (raw=0) | Cache updated with full solution |
| TIME_LIMIT / FEASIBLE (raw=1) | Cache updated with best feasible solution found (covers c2) |
| INFEASIBLE / UNBOUNDED (raw=2,3) | Previous snapshot preserved (matches Gurobi) |
| `addConstr()` after optimize() | Cache unchanged (lives in Python, not in pywraplp) |
| `_reset()` | Cache cleared along with solver |
| `Var.x` before first optimize() | Falls back to `solution_value()` → 0 (pywraplp default) |

---

## New Unit Test — `test_solution_persists_after_addconstr`

Added to `tests/test_shim.py`. Reproduces the exact Stage 1 bug pattern:

```
P1: setObjective → optimize()  →  order=1, slack=0
P1 pin: addConstr(slack ≤ 0)   ← pywraplp reset (intermediate — OK)
P2: setObjective → optimize()  →  order=1 (forced by P1 pin), truck=0
P2 pin: addConstr(truck ≤ 0)   ← pywraplp reset (CRITICAL — no P3 to restore)
→ order.x must return 1 (not 0)
```

Without the fix: assertion `abs(order.x - 1.0) < 1e-6` fails (order.x = 0).  
With the fix: assertion passes (order.x = 1.0 from cache).

---

## Unit Test Results

```
tests/test_shim.py::test_binary_milp                          PASSED
tests/test_shim.py::test_integer_milp                         PASSED
tests/test_shim.py::test_lexicographic_milp                   PASSED
tests/test_shim.py::test_fail_loud_min                        PASSED
tests/test_shim.py::test_fail_loud_indicator                  PASSED
tests/test_shim.py::test_fail_loud_setObjectiveN              PASSED
tests/test_shim.py::test_reset_clears_model                   PASSED
tests/test_shim.py::test_var_ub_setter                        PASSED
tests/test_shim.py::test_solution_persists_after_addconstr    PASSED

9 passed in 0.13s
```

---

## E2E Results — run_local.py (5 DCs)

### Stage 1 Lexicographic Loop — per DC

| DC | P60 | P50 | P30 | P20 | S1.assign | S1.trucks |
|---|---|---|---|---|---|---|
| 1000001 | OPTIMAL, 2.0 | OPTIMAL, 2150.2 | OPTIMAL, 5.0 | OPTIMAL, 0.0 | **206** | 3 |
| 1000002 | OPTIMAL, 0.0 | OPTIMAL, 3842.4 | OPTIMAL, 5.0 | OPTIMAL, 0.0 | **251** | 5 |
| 1000009 | OPTIMAL, 12.0 | TIME_LIMIT, 3977.9 | OPTIMAL, 3.0 | OPTIMAL, 0.0 | **202** | 5 |
| 1000013 | OPTIMAL, 0.0 | OPTIMAL, 6955.7 | OPTIMAL, 9.0 | OPTIMAL, 0.0 | **79** | 3 |
| 1000019 | OPTIMAL, 0.0 | TIME_LIMIT, 11454.7 | OPTIMAL, 40.0 | OPTIMAL, 0.0 | **278** | 9 |

Before fix: S1.assign = 0 for ALL DCs.

### Stage Selection Rule — per DC

| DC | BRANCH | S1.proposed_po | S2.proposed_po | Stage won |
|---|---|---|---|---|
| 1000001 | **B** | 3 | 3 | **Stage 1** |
| 1000002 | **B** | 5 | 5 | **Stage 1** |
| 1000009 | **B** | 5 | 5 | **Stage 1** |
| 1000013 | **B** | 3 | 3 | **Stage 1** |
| 1000019 | **B** | 9 | 9 | **Stage 1** |

**Before fix:** BRANCH-A fired for all 5 DCs (S2.assign > S1.assign=0 → Stage 2 always won).  
**After fix:** BRANCH-B fires for all 5 DCs (S1.proposed_po ≤ S2.proposed_po → Stage 1 wins).

S1.assign vs S2.assign by DC:

| DC | S1.assign | S2.assign | BRANCH-A condition (S2>S1) |
|---|---|---|---|
| 1000001 | 206 | 173 | False — Stage 1 assigns MORE |
| 1000002 | 251 | 251 | False — tied |
| 1000009 | 202 | 195 | False — Stage 1 assigns MORE |
| 1000013 | 79 | 79 | False — tied |
| 1000019 | 278 | 278 | False — tied |

### (c2) Timeout Coverage — Confirmed

DCs 1000009 (P50: 180s) and 1000019 (P50: 180s) both hit TIME_LIMIT. The fix handles this:
- `raw = 1` (pywraplp FEASIBLE) → `raw in (0, 1)` → cache updated with best feasible solution
- Subsequent `addConstr()` calls and `var.x` reads work correctly from the snapshot

---

## validate_output.py Results

```
VALIDATION SUMMARY
  [PASS]  1-3_capacity_final
  [PASS]  5_dc_slots_final
  [PASS]  6_truck_balance_final
  [PASS]  7_delivery_date_final
  [PASS]  8_shuffle_final
  [PASS]  9_soft_final
  [PASS]  4a_no_split_s1
  [PASS]  4b_split_conservation_s2
  [PASS]  1-3_capacity_s2
  [PASS]  5_dc_slots_s2
  [PASS]  7_delivery_date_s2
  [PASS]  schema

  Total: 12 passed, 0 failed out of 12 checks

  All constraints verified. Solution is feasible.
```

(Validator added 3 Stage 2 capacity checks vs the 9 checked previously; all pass.)

---

## Files Modified

| File | Change |
|---|---|
| `src/common/gurobi_compat.py` | 5 targeted edits (cache init, snapshot in optimize, Var reads from cache, addVar passes model=self, objVal serves cache) |
| `tests/test_shim.py` | 1 new test: `test_solution_persists_after_addconstr` |

**No logic files touched** (objectives.py, constraints.py, decision_variables.py, model_building.py, reshuffling_allocation_model.py for Stage 1 or Stage 2).

---

## Summary

The bug was a behavioral difference between Gurobi and pywraplp/OR-Tools: after `addConstr()`, Gurobi preserves the last MIP solution; pywraplp resets its internal state to NOT_SOLVED. The fix implements a Python-level snapshot that mirrors Gurobi's behavior: immediately after each successful `Solve()`, all variable values are captured into `Model._solution_cache`. This cache is immune to pywraplp state resets, so `var.x` always returns the last solved value, regardless of subsequent `addConstr()` calls.

Result: Stage 1 now produces valid assignments for all 5 DCs, enabling the S1/S2 selection rule to function as designed.
