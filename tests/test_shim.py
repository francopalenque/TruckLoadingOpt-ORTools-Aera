"""
test_shim.py — unit tests for gurobi_compat.py (PASO 3).

Three MILPs verifying the core shim API:
  1. Binary MILP           — addVar BINARY, addConstr, setObjective, optimize, .x
  2. INTEGER MILP          — addVar INTEGER, two-var MIP
  3. Lexicographic MILP    — two priority levels; setObjective + addConstr pin pattern
                             (mirrors the manual_hierarchical loop in objectives.py)

Run from TruckLoadingOpt-ORTools/:
    python -m pytest tests/test_shim.py -v
"""

import sys
import os

# Make the package root importable when run directly
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)

import pytest
from src.common.gurobi_compat import GRB, LinExpr, Model, min_, TempConstr


# ---------------------------------------------------------------------------
# Test 1 — Binary MILP
# ---------------------------------------------------------------------------

def test_binary_milp():
    """
    Maximize x + y  subject to  x + y <= 1,  x, y ∈ {0, 1}
    Optimal: obj = 1 (one of the two vars equals 1).
    """
    m = Model()
    m.setParam("MIPGap", 0.0)
    m.setParam("TimeLimit", 30)

    x = m.addVar(lb=0, ub=1, name="x", vtype=GRB.BINARY)
    y = m.addVar(lb=0, ub=1, name="y", vtype=GRB.BINARY)

    # Build sum expression via LinExpr.add(var, coeff) — constraints.py pattern
    expr = LinExpr()
    expr.add(x, 1)
    expr.add(y, 1)

    m.addConstr(expr <= 1, "cap")

    # Build objective via LinExpr.add(scalar * var) — objectives.py pattern
    obj_expr = LinExpr()
    obj_expr.add(1 * x)
    obj_expr.add(1 * y)
    m.setObjective(obj_expr, GRB.MAXIMIZE)

    m.optimize()

    assert m.status == GRB.OPTIMAL, f"Expected OPTIMAL (2), got {m.status}"
    assert abs(m.objVal - 1.0) < 1e-6, f"Expected objVal=1, got {m.objVal}"
    assert abs(x.x + y.x - 1.0) < 1e-6, f"Expected x+y=1, got {x.x + y.x}"


# ---------------------------------------------------------------------------
# Test 2 — INTEGER MILP
# ---------------------------------------------------------------------------

def test_integer_milp():
    """
    Minimize  2*x + 3*y  subject to  x + y >= 5,  x, y ∈ ℤ≥0
    Optimal: x=5, y=0, obj=10.
    """
    m = Model()
    m.setParam("MIPGap", 0.0)
    m.setParam("TimeLimit", 30)

    x = m.addVar(lb=0, ub=10, name="x", vtype=GRB.INTEGER)
    y = m.addVar(lb=0, ub=10, name="y", vtype=GRB.INTEGER)

    # Constraint: x + y >= 5
    cexpr = LinExpr()
    cexpr.add(x, 1)
    cexpr.add(y, 1)
    m.addConstr(cexpr >= 5, "lb_ct")

    # Objective: minimize 2x + 3y
    oexpr = LinExpr()
    oexpr.add(2 * x)
    oexpr.add(3 * y)
    m.setObjective(oexpr, GRB.MINIMIZE)

    m.optimize()

    assert m.status == GRB.OPTIMAL, f"Expected OPTIMAL (2), got {m.status}"
    assert abs(m.objVal - 10.0) < 1e-6, f"Expected objVal=10, got {m.objVal}"
    assert abs(x.x - 5.0) < 1e-6, f"Expected x=5, got {x.x}"
    assert abs(y.x - 0.0) < 1e-6, f"Expected y=0, got {y.x}"


# ---------------------------------------------------------------------------
# Test 3 — Lexicographic MILP (manual_hierarchical pattern)
# ---------------------------------------------------------------------------

def test_lexicographic_milp():
    """
    Mirrors the create_manual_hierarchical_objectives() loop from objectives.py:

      Priority 1 (Maximize): maximize x0 + x1 + x2  s.t. sum <= 2, xi ∈ {0,1}
        → opt v1 = 2
      Pin:  x0 + x1 + x2 >= v1 * (1 - 1e-4)  (Maximization pin idiom)
      Priority 2 (Maximize): maximize x0
        → opt v2 = 1  (x0=1 is achievable while keeping sum=2)
    """
    m = Model()
    m.setParam("MIPGap", 0.0)
    m.setParam("TimeLimit", 30)

    x0 = m.addVar(lb=0, ub=1, name="x0", vtype=GRB.BINARY)
    x1 = m.addVar(lb=0, ub=1, name="x1", vtype=GRB.BINARY)
    x2 = m.addVar(lb=0, ub=1, name="x2", vtype=GRB.BINARY)

    # Capacity constraint
    s_expr = LinExpr()
    s_expr.add(x0, 1)
    s_expr.add(x1, 1)
    s_expr.add(x2, 1)
    m.addConstr(s_expr <= 2, "cap")

    # ----- Priority 1 -----
    # Build via LinExpr.add(var * scalar) — objectives.py pattern with Var.__mul__
    p1_expr = LinExpr()
    p1_expr.add(x0 * 1)
    p1_expr.add(x1 * 1)
    p1_expr.add(x2 * 1)
    m.setObjective(p1_expr, GRB.MAXIMIZE)
    m.optimize()

    assert m.status in [GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.INTERRUPTED], \
        f"Priority 1: unexpected status {m.status}"
    v1 = m.objVal
    assert abs(v1 - 2.0) < 1e-6, f"Priority 1 objVal expected 2, got {v1}"

    # Pin (Maximization path from objectives.py):
    #   self.model.addConstr(expression >= obj_val * (1 - 1e-4), name=f"ct_pin_p1")
    pin_expr = LinExpr()
    pin_expr.add(x0 * 1)
    pin_expr.add(x1 * 1)
    pin_expr.add(x2 * 1)
    m.addConstr(pin_expr >= v1 * (1 - 1e-4), name="ct_pin_p1")

    # ----- Priority 2 -----
    p2_expr = LinExpr()
    p2_expr.add(x0 * 1)
    m.setObjective(p2_expr, GRB.MAXIMIZE)
    m.optimize()

    assert m.status in [GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.INTERRUPTED], \
        f"Priority 2: unexpected status {m.status}"
    v2 = m.objVal
    assert abs(v2 - 1.0) < 1e-6, f"Priority 2 objVal expected 1, got {v2}"
    assert abs(x0.x - 1.0) < 1e-6, f"Expected x0=1, got {x0.x}"


# ---------------------------------------------------------------------------
# Test 4 — FAIL-LOUD inactive idioms
# ---------------------------------------------------------------------------

def test_fail_loud_min():
    with pytest.raises(NotImplementedError):
        min_(1, 2, 3)


def test_fail_loud_indicator():
    m = Model()
    b = m.addVar(lb=0, ub=1, name="b", vtype=GRB.BINARY)
    x = m.addVar(lb=0, ub=100, name="x")
    # (b == 1) >> (x >= 5)  must raise NotImplementedError
    with pytest.raises(NotImplementedError):
        tc = (b == 1)
        _ = tc >> (x >= 5)


def test_fail_loud_setObjectiveN():
    m = Model()
    with pytest.raises(NotImplementedError):
        m.setObjectiveN(LinExpr(), priority=1, weight=1, index=0, name="P1")


# ---------------------------------------------------------------------------
# Test 5 — clear_model / _reset contract
# ---------------------------------------------------------------------------

def test_reset_clears_model():
    """After _reset(), the solver has no variables or constraints."""
    m = Model()
    x = m.addVar(lb=0, ub=1, name="x", vtype=GRB.BINARY)
    m.setObjective(LinExpr(), GRB.MINIMIZE)
    m.optimize()
    assert m.status == GRB.OPTIMAL

    m._reset()
    assert m.status is None  # status cleared

    # After reset, a new fresh solve on empty model should succeed
    m.setObjective(LinExpr(), GRB.MINIMIZE)
    m.optimize()
    assert m.status == GRB.OPTIMAL


# ---------------------------------------------------------------------------
# Test 6 — Var.ub setter (used in constraints.py: var.ub = 0)
# ---------------------------------------------------------------------------

def test_var_ub_setter():
    m = Model()
    x = m.addVar(lb=0, ub=10, name="x", vtype=GRB.CONTINUOUS)
    obj = LinExpr()
    obj.add(x, 1)
    m.setObjective(obj, GRB.MAXIMIZE)
    m.optimize()
    assert abs(x.x - 10.0) < 1e-6, f"Expected x=10, got {x.x}"

    # Tighten upper bound and re-solve
    x.ub = 3
    m.setObjective(obj, GRB.MAXIMIZE)
    m.optimize()
    assert abs(x.x - 3.0) < 1e-6, f"Expected x=3 after ub=3, got {x.x}"


# ---------------------------------------------------------------------------
# Test 7 — Solution cache survives addConstr (regression for bug c1)
# ---------------------------------------------------------------------------

def test_solution_persists_after_addconstr():
    """
    Exact bug pattern from Stage 1 lexicographic loop (bug c1):

      optimize() [last level]  →  addConstr(pin)  →  var.x

    In pywraplp, solver.Constraint() resets internal state to NOT_SOLVED, so
    solution_value() returns 0 afterward.  The Model._solution_cache must
    preserve the solution captured immediately after each successful Solve().

    Model structure mirrors the Stage-1 lexicographic loop:
      - P1 (ORDER_SLACK): minimize slack  → optimal: slack=0, order=1
      - P1 pin: addConstr(slack <= 0)     → pywraplp reset (intermediate)
      - P2 (last level): minimize truck   → optimal: truck=0, order stays 1
      - P2 pin: addConstr(truck <= 0)     → pywraplp reset (the real trigger)
      - Read order.x here: must return 1 (not 0) — this is the bug check.
    """
    m = Model()
    m.setParam("MIPGap", 0.0)
    m.setParam("TimeLimit", 30)

    order = m.addVar(lb=0, ub=1, name="order", vtype=GRB.BINARY)
    slack = m.addVar(lb=0, ub=1, name="slack", vtype=GRB.BINARY)

    # One-selection: order + slack == 1  (mirrors constraints.py per-order ct)
    sel = LinExpr()
    sel.add(order, 1)
    sel.add(slack, 1)
    m.addConstr(sel == 1, "one_sel")

    # ---- P1: minimize slack (TOTAL_ORDER_SLACK objective) ----
    p1_obj = LinExpr()
    p1_obj.add(slack, 1)
    m.setObjective(p1_obj, GRB.MINIMIZE)
    m.optimize()

    assert m.status == GRB.OPTIMAL, f"P1: expected OPTIMAL, got {m.status}"
    v1 = m.objVal
    assert abs(v1) < 1e-6, f"P1 objVal expected 0 (all orders assigned), got {v1}"
    assert abs(order.x - 1.0) < 1e-6, f"P1: order should be 1, got {order.x}"

    # P1 pin — same pattern as objectives.py MINIMIZE path
    p1_pin = LinExpr()
    p1_pin.add(slack, 1)
    m.addConstr(p1_pin <= v1 * (1 + 1e-4), name="ct_p1_pin")

    # ---- P2 (last level): minimize truck (ORDER_ITEM_SELECTION_SLACK) ----
    truck = m.addVar(lb=0, ub=1, name="truck", vtype=GRB.BINARY)
    p2_obj = LinExpr()
    p2_obj.add(truck, 1)
    m.setObjective(p2_obj, GRB.MINIMIZE)
    m.optimize()

    assert m.status == GRB.OPTIMAL, f"P2: expected OPTIMAL, got {m.status}"
    v2 = m.objVal
    assert abs(v2) < 1e-6, f"P2 objVal expected 0, got {v2}"

    # ---- BUG TRIGGER: addConstr AFTER the last solve ----
    # This call resets pywraplp's internal state to NOT_SOLVED, so
    # solution_value() returns 0 without the snapshot cache.
    p2_pin = LinExpr()
    p2_pin.add(truck, 1)
    m.addConstr(p2_pin <= v2 * (1 + 1e-4), name="ct_p2_pin")

    # order.x must reflect the P2 solve, not the pywraplp reset
    assert abs(order.x - 1.0) < 1e-6, (
        f"Bug (c1): addConstr after last solve cleared var.x. "
        f"Expected order=1, got {order.x}"
    )
    assert abs(m.objVal) < 1e-6, (
        f"objVal must remain valid after addConstr. Expected 0, got {m.objVal}"
    )
