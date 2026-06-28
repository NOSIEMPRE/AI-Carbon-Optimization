# Meeting Script: LP Model Update (Follow-up)

For: Bissan Ghaddar
Duration: ~15 min
Context: follow-up to the 2026-06-15 meeting. You raised three things: the
per-constraint testing approach doesn't make sense, the schedule comparison
in Figure F0 compares the wrong things, and you didn't believe kappa, rho,
and alpha showing almost no effect was real.

---

## 1. The model hasn't changed

Five regions, three objective terms, seven constraints. Nothing below changed
the model, only how it is tested and how results are read.

---

## 2. Validation

Validation has two parts: a perturbation test and an integration check.

The perturbation test is what you asked for. A model could assign load to the
same region every window regardless of carbon intensity, satisfy every
constraint, and still be wrong about the mechanism. The perturbation test uses a
small constructed instance with a known expected outcome, then changes one
parameter at a time, with all seven constraints active throughout, to check
the solution moves in the expected direction. Figure F1 shows three
scenarios and their outcomes (demand increase, delta tightening, C_max
squeeze). The CI shock is verified in the thirteen checks but not plotted
as a separate panel.

The integration check was not something you asked for. I added it because
the perturbation test uses constructed CI values, not real data, so it only
tells you the logic is correct, not whether the formulation holds on the
actual data the thesis depends on. The integration check runs the full model
on 168 hours of real data with all seven constraints active, and confirms
none are violated. Figure F8 shows the binding/slack table and summary
statistics for all seven constraints.

Three real regions, six hours: PJM as home (CI 564--613), Finland as the
cleanest destination (CI 52--55), Belgium as the medium option (CI 100--138).
Data from 2024-07-17 00:00--05:00 UTC. Baseline: FI gets 6.0 kWh, PJM
gets 4.0 kWh, BE gets 0.

CI shock (not plotted in Figure F1): FI's CI raised from 52--55 to 700
flat, making it dirtier than PJM at around 600. FI's load drops to zero and
BE picks up the full 6.0 kWh. The model reroutes as soon as a region
becomes the dirtiest option. Two checks cover this scenario and both pass.

Panel A (demand): total demand raised from 10 to 18 kWh. All 18 get served
with no shortfall and FI's load scales up to 10.8 kWh. Extra demand goes to
the preferred destination first, not to a fallback.

Panel B (δ, max deferral time): tightened from 6 hours to 1 hour. With 6
hours the model reaches FI's low-CI hours; carbon is 2,574 gCO2. With 1
hour it has to serve at t=0 from PJM; carbon rises to 2,808. How long load
can be deferred is what makes carbon savings possible; δ directly caps how
much is achievable. The 8.2 percent sensitivity result in the backtest comes
from the same mechanism at scale.

Panel C (C_max, hourly capacity cap on FI): squeezed in two steps. A mild
squeeze (3 kWh/h) spreads FI's load over more hours without reducing the
total served, which stays at 6.0 kWh. A severe squeeze (0.5 kWh/h) makes
the window-total cap binding at 3 kWh, forcing the shortfall to BE and PJM.
Mild constraints change the shape of the schedule; severe ones reduce how
much can be served from the cleanest region.

All three plotted perturbations produce the expected response, with all
seven constraints active throughout. The constraints are not just feasible,
they are load-bearing: each one changes the solution in a predictable
direction when its parameter is tightened.

Thirteen checks total, all thirteen pass. The count: one baseline reference
check confirming the clean region dominates before any perturbation, then
two checks for the CI shock, three for the demand increase, two for δ
(max deferral time), two for the mild capacity squeeze, and three for the severe one.

One flag: the first version gave a false pass on the mild capacity squeeze
due to floating-point rounding. Adding a tolerance and the severe-squeeze
case fixed it. The fix changed what the test was actually checking.

---

## 3. Schedule exhibit (Figure F2)

You said comparing unconstrained LP to constrained LP doesn't show the
model's value. I changed the comparison to no-shift versus LP-shift.

Figure F2 overlays two schedules on the same 24-hour CI curve. No-shift
drops the entire batch in the first hour at PJM. LP-shift spreads load over
several hours and routes to Finland, tracking the CI curve. The gap between
the two shows the full value of the approach: most of it comes from routing,
not from timing within PJM. One window for illustration; the two-year
backtest carries the actual claims.

---

## 4. Sensitivity analysis (Figure F3)

You asked for the LP alone and didn't believe kappa, rho, and alpha could
have almost no effect. Both addressed: a separate LP-only figure and a
mechanism check for each near-zero parameter.

Figure F3 is a horizontal tornado diagram, one bar per parameter, sorted by
width. Sigma's bar completely dominates; the other five are clustered near
zero at the same scale. Geographic flexibility is the binding constraint on
what the model can achieve.

One methodological note: in the OAT sweep, each parameter is tested with all
others at their loosest values. The near-zero effects for kappa, rho, and
alpha are not an artifact of other constraints masking the signal.

Kappa and rho are binding in almost every window, but the carbon cost of
complying is small because the preferred region's CI profile is smooth around
its best hour. Tightening the schedule shape costs almost nothing in carbon.

Alpha changes which hours are chosen in a meaningful share of windows, but
lands on the same low-carbon slots regardless, because CI and CFE are
strongly correlated in most regions. The exception is Singapore, where CFE
barely varies.

The near-zero carbon effect for all three is a property of the data, not a
model failure.

One note on delta: the 48-hour and 24-hour settings produce identical
results. A 24-hour planning window already captures every available
scheduling opportunity; the sensitivity cost from delta comes entirely from
tightening below 24 hours.

---

## 5. Scheduler comparison (Figure F5)

This separates LP from the heuristics, which you asked for. I follow the
convention from the carbon-aware scheduling literature: put every method on
one axis, showing how much carbon each saves relative to the no-optimization
baseline. Positive means it saves carbon versus doing nothing, negative means
it does worse. I changed this from an earlier LP-efficiency-ratio version,
because that pinned LP at 100% by definition and made the comparison look
circular.

All four methods run under the same full operational constraints: sigma=0.6,
kappa=0.5, rho=0.7, delta=24. These reflect a real deployment, not the
loosest possible settings.

The four methods bracket the LP from above and below. Oracle, the LP with a
full week of look-ahead, saves 36.8%. It beats the LP only because it assumes
perfect knowledge of a week of future carbon intensity, which you do not have
at deployment time. It is a ceiling, not a competitor.

Greedy saves 31.5%, essentially identical to the LP on this data. But that
closeness is luck, not a guarantee: Greedy only enforces the sigma geographic
cap and silently violates the ramp and range limits a deployed system has to
respect. Its near-optimal carbon is a property of this dataset, not of the
algorithm, which is exactly the uncertainty a provably constrained LP removes.

FCFS saves -51.5%, meaning it emits about half as much again as doing nothing.
At PJM's consistently high CI, serving jobs in arrival order front-loads them
into the dirtiest hours. FCFS is a common default in production schedulers, so
this is the realistic status quo, not a straw man.

The takeaway: the LP captures almost all the saving available to a
realistically-informed scheduler, 31.4% against Oracle's 36.8% ceiling, and
it is the only method that both reaches that saving and provably respects
every constraint. Greedy ties it only by ignoring constraints; FCFS, the
status quo, is actively harmful. The ranking holds across all four seasons.

For context, the 78.4% headline figure in the decomposition (Figures F6 and
F7) is the unconstrained result at sigma=1.0 and is a different scenario.

---

## 6. Seasonal analysis (Figure F4)

Not something you asked for. I dropped the constraint-combination figure
because its conclusion depended on the order constraints were stacked, which
is not defensible. The tornado makes the same point about sigma without that
order-dependence.

Figure F4 has two panels: seasonal LP savings and a regional breakdown by
season. Savings are consistent across all four seasons. Finland dominates the
regional breakdown in every season, more so in summer as its CI advantage
over PJM widens. The model's performance is driven by one region's structural
carbon advantage, and that advantage holds year-round.

---

## 7. Decomposition and cross-region analysis (Figures F6, F7)

Not directly requested. It answers a question the headline saving cannot:
does the 78 percent come from picking better regions or better times?

Figure F6 decomposes the saving into routing-only, timing-only, and an
interaction term. Routing accounts for nearly all of it. Timing alone is
negative: locking all load to PJM and only optimising the hour performs worse
than the uniform baseline, because PJM does not vary enough intra-day to
compensate. Where you schedule matters far more than when.

Figure F7 is a scatter plot of timing-only saving against CI variability, one
point per region. High-variability regions like Finland and Belgium show
meaningful timing gains; low-variability regions like PJM, NYISO, and
Singapore show almost none. Time-shifting only helps in regions where CI
actually moves. Five points, diagnostic only.

---

## 8. Where this leaves us

Kappa, rho, and alpha each have a checked mechanism. Sigma's dominance is the
central practical finding. The schedule exhibit compares the right two things.
Sensitivity and heuristics are separate.

Two limitations still flagged: the negative timing result is specific to PJM
being the home region, and the CV regression has five data points and is
illustrative.

---

Anything in how I checked kappa, rho, or alpha you want me to push further
on? Anything from last time I haven't closed out?
