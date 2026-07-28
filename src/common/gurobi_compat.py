"""
gurobi_compat.py — OR-Tools/pywraplp shim for the Gurobi API.

Implements only the Gurobi API surface that TruckLoadingOpt model-building
files actually use (see phase1_report.md §6).  Inactive Gurobi idioms
(min_, setObjectiveN, >> indicator constraints) raise NotImplementedError so
breakage is loud rather than silent.
"""

import logging
from ortools.linear_solver import pywraplp

logger = logging.getLogger(__name__)

_INF = float("inf")


# ---------------------------------------------------------------------------
# GRB — constants namespace (integer values must match constants.optimization_status)
# ---------------------------------------------------------------------------

class GRB:
    BINARY = "B"
    INTEGER = "I"
    CONTINUOUS = "C"
    MINIMIZE = 1
    MAXIMIZE = -1
    # Status codes — {2, 9, 11} are keys in constants.optimization_status
    OPTIMAL = 2
    TIME_LIMIT = 9
    INTERRUPTED = 11
    INFEASIBLE = 3
    UNBOUNDED = 5


# ---------------------------------------------------------------------------
# TempConstr — result of comparison operators on Var / LinExpr
# ---------------------------------------------------------------------------

class TempConstr:
    """Uncommitted linear constraint produced by ==, <=, >= on Var/LinExpr."""

    __hash__ = object.__hash__

    def __init__(self, lhs, sense, rhs):
        self.lhs = lhs
        self.sense = sense  # '<=', '>=', '=='
        self.rhs = rhs

    def __rshift__(self, other):
        # (binary_var == value) >> (linear_expr sense bound)
        # Inactive in prod: stage_one_truck_count_not_within_range = False
        raise NotImplementedError(
            "[gurobi_compat] Indicator constraint '>>' is not implemented. "
            "Activate stage_one_truck_count_not_within_range and implement "
            "big-M linearization in gurobi_compat.py before enabling."
        )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _to_linexpr(val):
    """Coerce a Var, scalar, or existing LinExpr into a LinExpr."""
    if isinstance(val, LinExpr):
        return val
    if isinstance(val, Var):
        e = LinExpr()
        e._terms.append((1.0, val))
        return e
    e = LinExpr()
    e._const = float(val)
    return e


# ---------------------------------------------------------------------------
# Var — wraps a single pywraplp Variable
# ---------------------------------------------------------------------------

class Var:
    """Gurobi Var shim wrapping a pywraplp Variable."""

    # __eq__ returns TempConstr, not bool, so preserve identity-based hashing.
    __hash__ = object.__hash__

    def __init__(self, pywraplp_var, model=None):
        self._var = pywraplp_var
        self._model = model  # back-reference; enables reading from solution cache

    # --- solution values ---

    @property
    def x(self):
        # Read from the Model's snapshot when available.  pywraplp/SCIP resets
        # solution state after addConstr(); the snapshot preserves the last
        # successful Solve() result so var.x stays valid across addConstr() calls.
        if self._model is not None and self._model._solution_cache is not None:
            return self._model._solution_cache.get(self._var.name(), 0.0)
        return self._var.solution_value()

    @property
    def X(self):
        return self.x

    # --- bounds ---

    @property
    def lb(self):
        return self._var.lb()

    @lb.setter
    def lb(self, value):
        self._var.SetLb(float(value))

    @property
    def ub(self):
        return self._var.ub()

    @ub.setter
    def ub(self, value):
        self._var.SetUb(float(value))

    # --- arithmetic (all delegate to LinExpr) ---

    def __mul__(self, scalar):
        e = LinExpr()
        e._terms.append((float(scalar), self))
        return e

    def __rmul__(self, scalar):
        return self.__mul__(scalar)

    def __add__(self, other):
        return _to_linexpr(self).__add__(other)

    def __radd__(self, other):
        return _to_linexpr(self).__radd__(other)

    def __sub__(self, other):
        return _to_linexpr(self).__sub__(other)

    def __rsub__(self, other):
        return _to_linexpr(self).__rsub__(other)

    def __neg__(self):
        e = LinExpr()
        e._terms.append((-1.0, self))
        return e

    # --- comparisons → TempConstr ---

    def __le__(self, other):
        return TempConstr(self, "<=", other)

    def __ge__(self, other):
        return TempConstr(self, ">=", other)

    def __eq__(self, other):
        return TempConstr(self, "==", other)

    def __repr__(self):
        return f"<Var {self._var.name()}>"


# ---------------------------------------------------------------------------
# LinExpr — linear combination of (coeff, Var) pairs plus a constant
# ---------------------------------------------------------------------------

class LinExpr:
    """Gurobi LinExpr shim backed by a list of (float, Var) pairs."""

    # __eq__ returns TempConstr; preserve identity-based hashing.
    __hash__ = object.__hash__

    def __init__(self):
        self._terms = []    # list of (float coeff, Var)
        self._const = 0.0

    def clear(self):
        """Reset to the zero expression (called between loop iterations)."""
        self._terms.clear()
        self._const = 0.0

    def add(self, term_or_var, coeff=None):
        """
        Two call patterns used in this codebase:
          expr.add(var, coeff)        — constraints (two-arg form)
          expr.add(scalar * var)      — objectives (one-arg LinExpr from Var.__mul__)
        """
        if coeff is not None:
            # expr.add(var, coeff)
            self._terms.append((float(coeff), term_or_var))
        elif isinstance(term_or_var, LinExpr):
            self._terms.extend(term_or_var._terms)
            self._const += term_or_var._const
        elif isinstance(term_or_var, Var):
            self._terms.append((1.0, term_or_var))
        else:
            self._const += float(term_or_var)

    # --- arithmetic ---

    def __add__(self, other):
        r = LinExpr()
        r._terms = list(self._terms)
        r._const = self._const
        if isinstance(other, LinExpr):
            r._terms.extend(other._terms)
            r._const += other._const
        elif isinstance(other, Var):
            r._terms.append((1.0, other))
        else:
            r._const += float(other)
        return r

    def __radd__(self, other):
        if isinstance(other, (int, float)):
            r = LinExpr()
            r._terms = list(self._terms)
            r._const = self._const + float(other)
            return r
        return self.__add__(other)

    def __sub__(self, other):
        r = LinExpr()
        r._terms = list(self._terms)
        r._const = self._const
        if isinstance(other, LinExpr):
            r._terms.extend((-c, v) for c, v in other._terms)
            r._const -= other._const
        elif isinstance(other, Var):
            r._terms.append((-1.0, other))
        else:
            r._const -= float(other)
        return r

    def __rsub__(self, other):
        r = LinExpr()
        if isinstance(other, (int, float)):
            r._terms = [(-c, v) for c, v in self._terms]
            r._const = float(other) - self._const
        elif isinstance(other, Var):
            r._terms = [(-c, v) for c, v in self._terms]
            r._terms.append((1.0, other))
            r._const = -self._const
        else:
            raise TypeError(f"[gurobi_compat] LinExpr.__rsub__: unsupported type {type(other)}")
        return r

    def __mul__(self, scalar):
        r = LinExpr()
        r._terms = [(c * float(scalar), v) for c, v in self._terms]
        r._const = self._const * float(scalar)
        return r

    def __rmul__(self, scalar):
        return self.__mul__(scalar)

    def __truediv__(self, scalar):
        return self.__mul__(1.0 / float(scalar))

    def __neg__(self):
        return self.__mul__(-1.0)

    # --- comparisons → TempConstr ---

    def __le__(self, other):
        return TempConstr(self, "<=", other)

    def __ge__(self, other):
        return TempConstr(self, ">=", other)

    def __eq__(self, other):
        return TempConstr(self, "==", other)

    def __repr__(self):
        return f"<LinExpr {len(self._terms)} terms, const={self._const}>"


# ---------------------------------------------------------------------------
# FAIL-LOUD stubs for inactive Gurobi idioms
# ---------------------------------------------------------------------------

def min_(*args):
    """Gurobi min_() general constraint — inactive in prod (truck_unused_cost=False)."""
    raise NotImplementedError(
        "[gurobi_compat] min_() is not implemented. "
        "Activate stage_one_truck_unused_cost / stage_two_truck_unused_cost and "
        "implement big-M linearization in gurobi_compat.py before enabling."
    )


# ---------------------------------------------------------------------------
# pywraplp solve-status → GRB status mapping
# pywraplp: OPTIMAL=0, FEASIBLE=1, INFEASIBLE=2, UNBOUNDED=3, ABNORMAL=4, NOT_SOLVED=6
# ---------------------------------------------------------------------------

_PYWRAPLP_TO_GRB = {
    0: GRB.OPTIMAL,     # 2
    1: GRB.TIME_LIMIT,  # 9 — partial solution treated as TIME_LIMIT
    2: GRB.INFEASIBLE,  # 3
    3: GRB.UNBOUNDED,   # 5
    4: 12,              # ABNORMAL
    6: 12,              # NOT_SOLVED
}


# ---------------------------------------------------------------------------
# Model — wraps pywraplp.Solver (SCIP backend)
# ---------------------------------------------------------------------------

class Model:
    """
    Gurobi Model shim backed by pywraplp/SCIP.

    Lifecycle:
      - Instantiated once per DC iteration by _LocalOptClient.__init__.
      - clear_model() calls _reset() to get a fresh solver between Stage 1
        and Stage 2 (and after reshuffling).
      - setObjective() calls obj.Clear() before setting new coefficients,
        supporting the lexicographic loop pattern (one setObjective per level).
    """

    def __init__(self):
        self._mip_gap = 0.001          # matches handler.py setParam('MIPGap', 0.001)
        self._time_limit_ms = 180_000  # matches handler.py setParam('TimeLimit', 180)
        self._obj_sense = GRB.MINIMIZE
        self._model_name = ""
        self._status = None
        self._solver = pywraplp.Solver.CreateSolver("SCIP")
        self._solver.SuppressOutput()
        self._solution_cache = None  # dict(var_name → float) populated by optimize()
        self._obj_cache = None       # float populated by optimize()
        # Gurobi no-op attributes that model-building code may assign
        self.NumObj = 0
        self.modelSense = GRB.MINIMIZE

    def _reset(self):
        """
        Recreate the underlying SCIP solver from scratch.
        Called by clear_model() in utils.py instead of Gurobi's remove() chain.
        """
        del self._solver
        self._solver = pywraplp.Solver.CreateSolver("SCIP")
        self._solver.SuppressOutput()
        self._status = None
        self._solution_cache = None
        self._obj_cache = None

    # --- model parameters ---

    @property
    def ModelName(self):
        return self._model_name

    @ModelName.setter
    def ModelName(self, value):
        self._model_name = str(value)

    def setParam(self, param, value):
        if param == "MIPGap":
            self._mip_gap = float(value)
        elif param == "TimeLimit":
            self._time_limit_ms = int(float(value) * 1000)
        # Other params silently ignored

    # --- variable creation ---

    def addVar(self, lb=0.0, ub=_INF, name="", vtype=GRB.CONTINUOUS):
        if vtype == GRB.BINARY:
            pv = self._solver.BoolVar(name)
        elif vtype == GRB.INTEGER:
            ub_val = self._solver.infinity() if ub == _INF else ub
            pv = self._solver.IntVar(lb, ub_val, name)
        else:
            ub_val = self._solver.infinity() if ub == _INF else ub
            pv = self._solver.NumVar(lb, ub_val, name)
        return Var(pv, model=self)

    # --- constraint addition ---

    def addConstr(self, constr, name=None):
        """
        Accepts both positional and keyword `name`:
          addConstr(expr <= rhs, "ct_name")          # constraints.py style
          addConstr(expr <= rhs, name="ct_name")     # objectives.py style
        """
        if not isinstance(constr, TempConstr):
            raise TypeError(
                f"[gurobi_compat] addConstr expected TempConstr, got {type(constr).__name__}. "
                "Indicator constraints (>>) raise in TempConstr.__rshift__."
            )

        lhs_e = _to_linexpr(constr.lhs)
        rhs_e = _to_linexpr(constr.rhs)

        # diff = lhs - rhs;  constraint is: diff.terms sense (-diff.const)
        diff = lhs_e - rhs_e
        rhs_val = -diff._const
        sense = constr.sense
        ct_name = name or ""

        if sense == "<=":
            ct = self._solver.Constraint(-_INF, rhs_val, ct_name)
        elif sense == ">=":
            ct = self._solver.Constraint(rhs_val, _INF, ct_name)
        elif sense == "==":
            ct = self._solver.Constraint(rhs_val, rhs_val, ct_name)
        else:
            raise ValueError(f"[gurobi_compat] Unknown constraint sense '{sense}'")

        # Accumulate duplicate-variable coefficients before passing to pywraplp.
        # pywraplp SetCoefficient replaces (not adds) on repeated calls for the same var.
        coeff_map = {}
        for coeff, var in diff._terms:
            pv = var._var
            coeff_map[pv] = coeff_map.get(pv, 0.0) + coeff
        for pv, coeff in coeff_map.items():
            ct.SetCoefficient(pv, coeff)

    # --- objective ---

    def setObjective(self, expr, sense=None):
        """
        Set (replace) the objective function.

        Calls obj.Clear() first — required because the manual-hierarchical loop
        calls setObjective once per priority level on the same solver instance.
        sense: GRB.MINIMIZE (1) or GRB.MAXIMIZE (-1); None preserves current.
        """
        obj = self._solver.Objective()
        obj.Clear()

        if sense is not None:
            self._obj_sense = sense

        if not isinstance(expr, (int, float)):
            e = _to_linexpr(expr)
            # Accumulate same-var coefficients (objective has no constraint limit)
            coeff_map = {}
            for coeff, var in e._terms:
                pv = var._var
                coeff_map[pv] = coeff_map.get(pv, 0.0) + coeff
            for pv, coeff in coeff_map.items():
                obj.SetCoefficient(pv, coeff)
            obj.SetOffset(e._const)

        if self._obj_sense == GRB.MAXIMIZE:
            obj.SetMaximization()
        else:
            obj.SetMinimization()

    # --- solve ---

    def optimize(self):
        """Solve and map the pywraplp status to GRB integer codes."""
        n_vars = self._solver.NumVariables()
        n_cstrs = self._solver.NumConstraints()
        # DIAG: log MILP size so run_local.py output shows non-trivial models
        print(f"[SCIP] optimize(): {n_vars} vars, {n_cstrs} constraints", flush=True)
        self._solver.set_time_limit(self._time_limit_ms)
        # SCIP-specific MIP gap parameter
        param_str = f"limits/gap = {self._mip_gap}"
        ok = self._solver.SetSolverSpecificParametersAsString(param_str)
        if not ok:
            logger.warning("[gurobi_compat] MIPGap parameter not applied via SCIP string")
        raw = self._solver.Solve()
        self._status = _PYWRAPLP_TO_GRB.get(raw, 12)
        obj_val = self._solver.Objective().Value()
        print(f"[SCIP] status={self._status} objVal={obj_val:.4f}", flush=True)

        # Snapshot all variable values while pywraplp still holds the solution.
        # raw=0 (OPTIMAL) and raw=1 (FEASIBLE/TIME_LIMIT) both have a valid
        # variable assignment.  addConstr() after this point resets pywraplp's
        # internal state to NOT_SOLVED; the snapshot keeps var.x correct.
        # On INFEASIBLE/UNBOUNDED the previous snapshot is preserved — matches
        # Gurobi, which also keeps the last feasible solution accessible.
        if raw in (0, 1):
            n = self._solver.NumVariables()
            self._solution_cache = {
                self._solver.variable(i).name(): self._solver.variable(i).solution_value()
                for i in range(n)
            }
            self._obj_cache = obj_val

    # --- properties ---

    @property
    def status(self):
        return self._status

    @property
    def objVal(self):
        """Return the cached objective value, falling back to the live solver query."""
        if self._obj_cache is not None:
            return self._obj_cache
        return self._solver.Objective().Value()

    # --- clear_model() plumbing stubs ---
    # Real reset is via _reset(); these exist so the original Gurobi code path
    # in clear_model() doesn't crash if called with a shim model by mistake.

    def getGenConstrs(self):
        return []

    def getConstrs(self):
        return []

    def getVars(self):
        return []

    def getQConstrs(self):
        return []

    def getSOSs(self):
        return []

    def remove(self, items):
        pass

    # --- no-ops ---

    def update(self):
        pass

    def dispose(self):
        pass

    def setObjectiveN(self, *args, **kwargs):
        # Inactive in prod: manual_hierarchical = True bypasses this code path
        raise NotImplementedError(
            "[gurobi_compat] setObjectiveN() is not implemented. "
            "Set manual_hierarchical = False to activate, then implement "
            "multi-objective support in gurobi_compat.py."
        )
