# Meeting Script: LP Model Update (Follow-up)

For: Bissan Ghaddar
Duration: ~15 min
Context: follow-up to the 2026-06-15 meeting where you flagged the per-constraint
testing approach, the unconstrained-vs-constrained schedule comparison, and asked
me to verify whether kappa/rho/alpha having small aggregate impact was a bug.

---

## Opening

Since last time I addressed all three things you raised. I rewrote the validation
test, fixed the schedule comparison, redid the sensitivity and heuristic figures
as two separate plots, and ran a diagnostic to check whether kappa, rho, and alpha
having small effect is real or a bug. I'll go through each.

---

## 1. LP Model (unchanged, brief recap)

Five regions: PJM, NYISO, Finland, Belgium, Singapore. Decision variable x_{r,t}:
load assigned to region r at hour t. Three-term objective: carbon cost
(CI times one minus alpha times CFE), transfer cost (gamma per kWh routed
off-home), and equity (eta times M, the most-burdened region's carbon total).

Seven constraints, C1-C7, same as before. C6 (ramp rate) and C7 (dynamic range)
are written as two one-sided inequalities each, following Wijayawardana and Chien.

---

## 2. Validation — now two tests, not one

**Integration test (what I had before, kept as-is).** Full LP, all seven
constraints active simultaneously, on a representative instance: seven days of
real data, three regions, full-model parameters. All seven pass. Four binding
(C1, C4, C5, C6), three slack (C2, C3 upper, C7) — slack is informative, not a
failure, it means that constraint isn't the bottleneck for this particular window.

**New: perturbation test.** This addresses what you specifically asked for —
take all constraints together on a small instance, then change one parameter at
a time and check the solution reacts the way you'd expect by hand, rather than
just checking constraint satisfaction.

Instance: 3 regions, 6 hours, hand-designed CI (home flat-dirty, one region with
a clean dip mid-window, one flat-medium). All constraints active. Four scenarios:

- Raise the clean region's CI above the home region's → load should move to the
  new cheapest region. It does: clean region's share drops from 6.0 to 0.0 kWh,
  medium region's rises from 0.0 to 6.0.
- Raise demand from 10 to 18 kWh → all of it should still get served, and the
  previously-preferred region's load shouldn't decrease. Confirmed.
- Tighten the deadline so the batch can't reach the clean hour → carbon should
  rise. It does, from 2,087 to 2,350.
- Squeeze a region's capacity. I actually ran this twice, because the first
  version gave a false positive — a mild squeeze (3 kWh/h, window can still fit
  18 kWh) showed "no change" by design (capacity is a per-hour cap, so the LP
  just spreads load over more hours, doesn't need to overflow), but my pass/fail
  check had no tolerance margin and a floating-point rounding artifact made it
  print PASS for the wrong reason. Fixed by adding a tolerance and a genuinely
  severe squeeze (0.5 kWh/h) that does force real overflow to other regions.

All eleven checks pass for the right reason this time.

---

## 3. Solution Exhibit — fixed the comparison basis

You said comparing unconstrained-LP against constrained-LP doesn't make sense,
since neither represents what happens without the model — the right comparison
is no-shift versus LP-shift. I redid Figure F0 with that basis.

Left panel: no-shift, the batch served immediately at the home region, exactly
as it arrives — that's literally what FCFS reduces to here since capacity
matches the batch size. Right panel: LP-shift, with kappa 0.2 and rho 0.4 active.
In this window: no-shift costs 533 gCO2; LP routes to Finland and spreads over
five hours, costing 53 — a 90% reduction. I kept the framing explicit that this
is one illustrative window, and the two-year backtest is what the actual claims
rest on.

---

## 4. Sensitivity Analysis — split into LP-only, plus a diagnostic

Two things changed here. First, the figure is now LP-only — no heuristics mixed
in, exactly what you asked for. Second, I ran a diagnostic on why kappa, rho, and
alpha show small aggregate effect, since you said you didn't believe a flat
result across the parameter range.

**Result: it's not flat, and it's not a bug, but the explanation isn't what I
originally assumed either.** I checked the actual mechanism rather than just
asserting one.

For kappa and rho: each window injects one demand batch, so the unconstrained LP
always wants to dump it into a single best hour — meaning the ramp constraint is
at its structural maximum in literally every one of the 731 windows. Kappa and
rho are binding 100% of the time, not rarely. The reason the aggregate carbon
cost is still small is that the region the LP prefers usually has a locally
smooth CI profile around its best hour, so spreading the batch over a few more
hours to satisfy the ramp cap is cheap. That's a real, checked mechanism, not an
assumption.

For alpha: I compared the actual allocation, not just the resulting carbon, at
alpha=0 versus alpha=1 on a sample of 100 windows. The allocation differs in 43
of them — alpha is doing something real to the schedule. The carbon barely
moves because CI and CFE are strongly negatively correlated within each region
(r=-0.98 Finland, -0.98 Belgium, -0.87 NYISO, -0.61 PJM) — the hours the CFE
discount favors are usually already the low-CI hours, so the discount rarely
redirects the schedule toward something meaningfully worse. Singapore is the
exception (r=-0.24, flat 2.7% CFE), where alpha has almost nothing to act on.

Sigma is still completely dominant: +373.7% carbon from tightening 1.0 to 0.3,
an order of magnitude above everything else (eta +20.2%, delta +8.2%, rho +2.9%,
kappa +2.1%, alpha +0.2%).

---

## 5. Heuristic Analysis — separate figure, efficiency ratio

Also separated per your request — no longer mixed with the sensitivity sweep.
New metric: LP efficiency ratio, (C_Uniform − C_alg)/(C_Uniform − C_LP). LP is
100% by construction, Oracle 103.9% (longer look-ahead), Greedy 100.0%
(matches LP when C6/C7 are loose), FCFS −65.7% (worse than doing nothing —
concentrating in dirty PJM beats Uniform's automatic geographic spread).

---

## 6. Seasonal Analysis

Unchanged. Summer gives the highest LP saving (84.1%), spring the lowest
(73.4%). Finland absorbs the majority of load in every season, more in summer
as the CI gap versus PJM widens.

(I dropped the constraint-combination scenario table and figure that used to be
here — the conclusion depended on the order constraints were stacked in, which
isn't defensible, and the tornado diagram already makes the same point about
sigma dominance more rigorously.)

---

## 7. Decomposition and Cross-Region Analysis

Unchanged, numbers hold: spatial-only 75.6%, temporal-only −35.6%, joint 78.4%,
interaction 38.4%. Negative temporal-only is specific to PJM as home region —
Uniform already spreads a fifth of load to cleaner regions, so locking
everything to a dirty home region and only optimizing timing does worse than
that baseline.

CV regression: Finland/Belgium CV~0.40-0.42, temporal saving 13-28%; PJM/NYISO/
Singapore CV~0.11-0.13, temporal saving 5-8%. Framed explicitly as a five-point
diagnostic, not a formal regression.

---

## 8. Where Things Stand

Validation is now two tests covering different failure modes: constraint
satisfaction on a representative instance, and directional correctness on a
hand-traceable instance. Sensitivity has a checked explanation for why three of
six parameters show small effect, not just an assertion. The schedule exhibit
uses a defensible comparison basis. Sensitivity and heuristics are properly
separated.

Decomposition and CV regression are the parts I'd still flag as having the most
room to develop — five data points for the CV regression, and the temporal-only
finding is conditional on PJM being the home region.

---

Is there anything in the diagnostic reasoning you want me to dig into further,
or anything else from the previous meeting I should still address?
