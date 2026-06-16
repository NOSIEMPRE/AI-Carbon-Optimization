"""
lp_model.py — Carbon-aware compute scheduling LP.

Objective (three components)
─────────────────────────────────────────────────────────────────────────────
min   Σ_{r,t}  x[r,t] · CI[r,t] · (1 − α · CFE[r,t])   (i)  carbon cost
    + γ · Σ_{r≠r₀, t}  x[r,t]                           (ii) transfer cost
    + η · M                                              (iii) equity

where M ≥ Σ_t x[r,t] · CI[r,t]  ∀ r   (linearised max over regional carbon)

Setting γ=0 and η=0 recovers the single-component baseline.

Constraints
─────────────────────────────────────────────────────────────────────────────
C1  Σ_{r,t} x[r,t] = D^flex                                demand completion
C2  Σ_r Σ_{t'=τ}^{τ+δ} x[r,t'] ≥ D_τ^flex  ∀ τ           latency bound
C3  C_min[r] ≤ x[r,t] ≤ C_max[r]  ∀ r,t               capacity bounds
    (non-negativity follows from C_min[r] ≥ 0)
C4  Σ_{r≠r₀} x[r,t] ≤ σ · Σ_r x[r,t]  ∀ t                transfer limit
C5  M ≥ Σ_t x[r,t] · CI[r,t]  ∀ r                        equity auxiliary
C6  |x[r,t] − x[r,t−1]| ≤ κ · C_max[r]  ∀ r, t≥1         ramp rate
C7  max_t x[r,t] − min_t x[r,t] ≤ ρ · C_max[r]  ∀ r      dynamic range

C6 is active when κ < 1.0; C7 is active when ρ < 1.0.
Both are inspired by Wijayawardana & Chien (SoCC 2025), who characterise
capacity variation in terms of step size and dynamic range.

Shape convention: (R, T) throughout.
Solvers: scipy HiGHS (default) or Gurobi (pass solver='gurobi').

Gurobi setup (free academic license):
  1. Register at https://www.gurobi.com/academia/academic-program-and-licenses/
  2. pip install gurobipy
  3. grbgetkey <your-license-key>
  Then call solve(..., solver='gurobi').
"""

from dataclasses import dataclass
import numpy as np
from scipy.optimize import linprog


@dataclass
class LPResult:
    x         : np.ndarray   # (R, T) flexible load [kWh]
    carbon    : float        # Σ x[r,t]·CI[r,t]           [gCO2]
    transfer  : float        # Σ_{r≠r0,t} x[r,t]         [kWh]
    equity_M  : float        # max_r Σ_t x[r,t]·CI[r,t]  [gCO2]
    obj_value : float        # weighted objective value
    status    : str


def solve(
    CI             : np.ndarray,
    CFE            : np.ndarray,
    D_flex_batches : np.ndarray,
    C_min          : np.ndarray,
    C_max          : np.ndarray,
    alpha  : float = 0.5,
    gamma  : float = 0.0,
    eta    : float = 0.0,
    delta  : int   = 24,
    sigma  : float = 1.0,
    r0     : int   = 0,
    kappa  : float = 1.0,
    rho    : float = 1.0,
    solver : str   = 'highs',
) -> LPResult:
    """
    Solve the carbon-aware scheduling LP.

    Parameters
    ----------
    CI             : (R, T) carbon intensity [gCO2/kWh]
    CFE            : (R, T) carbon-free energy fraction [0, 1]
    D_flex_batches : (T,)   flexible demand arriving at each hour [kWh]
    C_min          : (R,)   minimum flexible load per region per hour [kWh/h]; must be ≥ 0
    C_max          : (R,)   maximum flexible load per region per hour [kWh/h]
    alpha          : CFE discount coefficient
    gamma          : transfer cost [gCO2-equiv per kWh routed off-home]
    eta            : equity weight on max-regional carbon term
    delta          : latency window in hours; window = [τ, τ+δ) exclusive
    sigma          : max fraction of hourly load outside home region [0, 1]
    r0             : home region index
    kappa          : ramp-rate cap as fraction of C_max per hour (C6);
                     1.0 = inactive
    rho            : dynamic-range cap as fraction of C_max over horizon (C7);
                     1.0 = inactive
    solver         : 'highs' (default, via scipy) or 'gurobi' (requires gurobipy
                     with a valid license — free academic license available at
                     gurobi.com/academia)
    """
    R, T  = CI.shape
    N     = R * T
    has_dyn = rho < 1.0
    N_TOT = N + 1 + (2 * R if has_dyn else 0)
    M_IDX = N

    def idx(r, t):
        return r * T + t

    def u_idx(r):   # upper envelope auxiliary for C7
        return N + 1 + r

    def l_idx(r):   # lower envelope auxiliary for C7
        return N + 1 + R + r

    # ── Objective ─────────────────────────────────────────────────────────────
    c_obj = np.zeros(N_TOT)
    for r in range(R):
        pen = gamma if r != r0 else 0.0
        for t in range(T):
            c_obj[idx(r, t)] = CI[r, t] * (1.0 - alpha * CFE[r, t]) + pen
    c_obj[M_IDX] = eta
    # U[r] and L[r] carry zero objective coefficient

    # ── C1: total demand equality ─────────────────────────────────────────────
    A_eq        = np.zeros((1, N_TOT))
    A_eq[0, :N] = 1.0
    b_eq        = np.array([float(D_flex_batches.sum())])

    # ── Inequality constraints ────────────────────────────────────────────────
    rows, rhs = [], []

    # C2: latency bound
    for tau in range(T):
        if D_flex_batches[tau] <= 0:
            continue
        row   = np.zeros(N_TOT)
        t_end = min(tau + delta, T)
        for r in range(R):
            for tp in range(tau, t_end):
                row[idx(r, tp)] -= 1.0
        rows.append(row)
        rhs.append(-float(D_flex_batches[tau]))

    # C4: geographic transfer limit
    if sigma < 1.0:
        for t in range(T):
            row = np.zeros(N_TOT)
            for r in range(R):
                row[idx(r, t)] = (1 - sigma) if r != r0 else -sigma
            rows.append(row)
            rhs.append(0.0)

    # C6: equity auxiliary  Σ_t CI[r,t]·x[r,t] − M ≤ 0  ∀ r
    if eta > 0.0:
        for r in range(R):
            row = np.zeros(N_TOT)
            for t in range(T):
                row[idx(r, t)] = CI[r, t]
            row[M_IDX] = -1.0
            rows.append(row)
            rhs.append(0.0)

    # C7: ramp rate  |x[r,t] − x[r,t−1]| ≤ κ·C_max[r]  ∀ r, t ≥ 1
    if kappa < 1.0:
        for r in range(R):
            limit = kappa * C_max[r]
            for t in range(1, T):
                # ramp-up:   x[r,t] - x[r,t-1] ≤ limit
                row_up = np.zeros(N_TOT)
                row_up[idx(r, t)]   =  1.0
                row_up[idx(r, t-1)] = -1.0
                rows.append(row_up)
                rhs.append(limit)
                # ramp-down: x[r,t-1] - x[r,t] ≤ limit
                row_dn = np.zeros(N_TOT)
                row_dn[idx(r, t)]   = -1.0
                row_dn[idx(r, t-1)] =  1.0
                rows.append(row_dn)
                rhs.append(limit)

    # C8: dynamic range  max_t x[r,t] − min_t x[r,t] ≤ ρ·C_max[r]  ∀ r
    # Linearised via per-region auxiliary variables U[r] ≥ max_t and L[r] ≤ min_t.
    if has_dyn:
        for r in range(R):
            for t in range(T):
                # x[r,t] ≤ U[r]  →  x[r,t] − U[r] ≤ 0
                row = np.zeros(N_TOT)
                row[idx(r, t)] =  1.0
                row[u_idx(r)]  = -1.0
                rows.append(row)
                rhs.append(0.0)
                # L[r] ≤ x[r,t]  →  L[r] − x[r,t] ≤ 0
                row = np.zeros(N_TOT)
                row[l_idx(r)]  =  1.0
                row[idx(r, t)] = -1.0
                rows.append(row)
                rhs.append(0.0)
            # U[r] − L[r] ≤ ρ·C_max[r]
            row = np.zeros(N_TOT)
            row[u_idx(r)] =  1.0
            row[l_idx(r)] = -1.0
            rows.append(row)
            rhs.append(rho * C_max[r])

    A_ub = np.array(rows) if rows else None
    b_ub = np.array(rhs)  if rhs  else None

    # ── Bounds: C3 + auxiliary variables ─────────────────────────────────────
    bounds = []
    for r in range(R):
        for t in range(T):
            bounds.append((C_min[r], C_max[r]))
    bounds.append((0.0, None))   # M ≥ 0
    if has_dyn:
        for r in range(R):
            bounds.append((0.0, None))   # U[r] ≥ 0
        for r in range(R):
            bounds.append((0.0, None))   # L[r] ≥ 0

    # ── Solve ─────────────────────────────────────────────────────────────────
    if solver == 'gurobi':
        return _solve_gurobi(
            c_obj, A_ub, b_ub, A_eq, b_eq, bounds,
            N, R, T, M_IDX, CI, r0,
        )

    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub,
                  A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method='highs')

    if res.status != 0:
        return LPResult(
            x=np.zeros((R, T)), carbon=0.0, transfer=0.0,
            equity_M=0.0, obj_value=float('inf'), status=res.message,
        )

    x        = res.x[:N].reshape(R, T)
    transfer = float(x[[r for r in range(R) if r != r0]].sum()) if R > 1 else 0.0

    return LPResult(
        x        = x,
        carbon   = float((x * CI).sum()),
        transfer = transfer,
        equity_M = float(res.x[M_IDX]),
        obj_value= float(res.fun),
        status   = res.message,
    )


def _solve_gurobi(c_obj, A_ub, b_ub, A_eq, b_eq, bounds,
                  N, R, T, M_IDX, CI, r0) -> LPResult:
    """Gurobi backend. Requires: pip install gurobipy + valid license."""
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError:
        raise ImportError(
            "gurobipy not installed. Run: pip install gurobipy\n"
            "Then obtain a free academic license at gurobi.com/academia"
        )

    n_vars = len(c_obj)
    m = gp.Model("carbon_lp")
    m.Params.OutputFlag = 0   # suppress console output

    # Variables with bounds
    lb = np.array([b[0] if b[0] is not None else -GRB.INFINITY for b in bounds])
    ub = np.array([b[1] if b[1] is not None else  GRB.INFINITY for b in bounds])
    x_var = m.addMVar(n_vars, lb=lb, ub=ub, obj=c_obj, name="x")

    # Equality constraints (C1)
    if A_eq is not None:
        m.addMConstr(A_eq, x_var, '=', b_eq)

    # Inequality constraints (C2–C7)
    if A_ub is not None:
        m.addMConstr(A_ub, x_var, '<', b_ub)

    m.ModelSense = GRB.MINIMIZE
    m.optimize()

    if m.Status != GRB.OPTIMAL:
        return LPResult(
            x=np.zeros((R, T)), carbon=0.0, transfer=0.0,
            equity_M=0.0, obj_value=float('inf'),
            status=f"Gurobi status {m.Status}",
        )

    sol      = x_var.X
    x        = sol[:N].reshape(R, T)
    transfer = float(x[[r for r in range(R) if r != r0]].sum()) if R > 1 else 0.0

    return LPResult(
        x        = x,
        carbon   = float((x * CI).sum()),
        transfer = transfer,
        equity_M = float(sol[M_IDX]),
        obj_value= float(m.ObjVal),
        status   = "Optimal",
    )
