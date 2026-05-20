# AI + Carbon-Aware Computing — Weekly Digest
## Isabel Wu | IE University MBADS Capstone

**Purpose:** Track new developments in AI energy consumption, carbon-aware scheduling, and data center sustainability. Updated weekly. Each entry is self-contained — you can read any issue without context from prior ones.

**Thesis context:** LP-based joint spatio-temporal workload scheduling across 5 grid regions (PJM, NYISO, Finland, Belgium, Singapore) to minimize AI data center carbon emissions using ElectricityMaps CI and RF data.

---

## How to Update This Digest

Run the script from the project root (every Monday, or whenever):

```bash
cd "Desktop/Thesis Project"
python src/weekly_digest_update.py           # last 7 days (default)
python src/weekly_digest_update.py --days 14 # catch up after two weeks
python src/weekly_digest_update.py --dry-run # preview without writing
```

The script fetches new arXiv preprints, filters by relevance, and inserts a draft Issue at the top of this file. Then open this file and:

1. Fill in `*Thesis relevance: [fill in]*` for papers you want to keep
2. Delete entries that aren't relevant
3. Fill in **Field Developments** and **Thesis Implications** manually
4. If a paper is worth tracking long-term, add it to `reading_notes.md` and `references.bib`

---

## Issue 2 — Week of 2026-05-18
*Auto-generated draft. Review, trim, and fill in "Thesis relevance" before finalizing.*
*arXiv window: 2026-05-11 → 2026-05-18 | Categories searched: cs.DC, eess.SY, cs.NI, cs.LG*

### New Papers This Week (3 found)

**Sohaib Afifi (2026-05-14)**  
*An Amortized Efficiency Threshold for Comparing Neural and Heuristic Solvers in Combinatorial Optimization*  
arXiv:2605.14624 — https://arxiv.org/abs/2605.14624  
A common critique of neural combinatorial-optimization solvers is that they are less energy-efficient than CPU metaheuristics, given the operational energy cost of training them on GPUs. This paper examines the inferential step from "training is expensive" to "neural solvers are …  
*Thesis relevance: [fill in]*

---

**H. Moore et al. (2026-05-13)**  
*MARLIN: Multi-Agent Game-Theoretic Reinforcement Learning for Sustainable LLM Inference in Cloud Datacenters*  
arXiv:2605.13496 — https://arxiv.org/abs/2605.13496  
Large Language Models (LLMs) have become increasingly prevalent in cloud-based platforms, propelled by the introduction of AI-based consumer and enterprise services. LLM inference requests in particular account for up to 90% of total LLM lifecycle energy use, dwarfing training …  
*Thesis relevance: [fill in]*

---

**P. Ramicetty et al. (2026-05-13)**  
*Sustainable Graph Analytics Workload Scheduling with Evolutionary Reinforcement Learning in Edge-Cloud Systems*  
arXiv:2605.13489 — https://arxiv.org/abs/2605.13489  
Graph analytics powers modern intelligent systems such as smart cities, cyber-physical infrastructure, IoT security, and large-scale social networks. As these workloads scale in complexity, their execution in heterogeneous edge-cloud environments results in higher energy use and …  
*Thesis relevance: [fill in]*

### Field Developments
- [Fill in: industry news, policy, grid data updates]

### Thesis Implications
- [Fill in: how new findings affect your model or argument]

### Reading Queue Update
Added to reading_notes.md:
- [ ] *[list papers you decide to keep]*

---

## Issue 1 — Week of 2026-05-18

### Context
First digest entry. This issue summarizes the state of the field as of thesis writing, rather than tracking new publications.

### Field State Summary (as of May 2026)

**Carbon-aware scheduling is mainstream but joint optimization remains rare.**
Google's production carbon-aware system (Radovanovic et al. 2023) has been running since 2020, establishing temporal shifting as an industry norm. However, the vast majority of deployed systems treat temporal and spatial shifting as separate decisions. A systematic review (Asadov & Coroama, *Sustainability* 2025) confirms this gap remains open.

**AI GPU workloads are the next frontier.**
The Colangelo et al. (arXiv:2507.00909) Phoenix field demonstration showed that production AI GPU clusters can participate in demand response with zero SLA violations. GREEN (Xu et al., NSDI 2025) showed 30% carbon reduction via temporal shifting for ML clusters. Both validate that AI workloads have sufficient flexibility for scheduling — a key assumption this thesis rests on.

**Grid carbon intensity data is now high-quality and accessible.**
ElectricityMaps (formerly Tomorrow) provides verified hourly CI data across 50+ regions via API, underpinning this thesis's dataset. Their data has been used by Radovanovic et al. (2023), Xu et al. (2025), and Hanafy et al. (2025), establishing it as the field standard.

**Renewable fraction vs. carbon intensity: a live debate.**
Riepin et al. (2025) argue for 24/7 CFE fraction as the scheduling signal; Radovanovic et al. use CI directly. This thesis's RF-weighted objective `(1 − α·RF)` bridges both signals, which is a novel contribution worth emphasizing.

**Multi-year real-data backtesting is rare.**
Most LP papers use simulation or <1 year of data. This thesis's 17,544-hour (2024–2025) rolling-window backtesting on 5 structurally diverse regions fills a methodological gap.

### Thesis Implications
- The CV metric (σ/μ of CI) directly formalizes the region-dependence finding from Wiesner et al. 2024 — cite explicitly in Ch. 5 Discussion.
- The Riepin et al. 300–400 km finding informs region selection rationale — use in Ch. 3 System Model.
- The Colangelo VCC mechanism needs to be described more carefully in C3 — it's the most recent and specific reference for that constraint.

### Reading Queue This Week
**Priority reads (directly needed for thesis writing):**
- [ ] Riepin, Brown, Zavala 2025 (arXiv:2405.00036) — closest prior LP; need to understand exact differences
- [ ] Wiesner et al. 2024 (EuroSys) — read section on CV and regional variation
- [ ] Attenni et al. 2024 (arXiv:2512.08725) — check their MILP constraints vs. our LP

**Secondary reads:**
- [ ] Asadov & Coroama 2025 (*Sustainability*) — literature review section useful for Ch. 2 positioning

---

## Issue 0 — Template (copy this for future issues)

```markdown
## Issue N — Week of YYYY-MM-DD

### New Papers This Week

**[1] Author et al. (YYYY)**
*Title* | Venue | arXiv:XXXX.XXXXX
One-sentence summary. Thesis implication: ...

### Field Developments
- [Bullet point per development]

### Thesis Implications
- [Direct impact on this thesis's argument or methodology]

### Reading Queue Update
Added to reading_notes.md:
- [ ] Paper A
Removed / deprioritized:
- Paper B (reason: ...)
```

---

## Archived Issues

*(Issues will be moved here when more than 8 weeks old to keep the active section short.)*

---

*Maintained by Isabel Wu. For thesis advising context, see [ch3_methodology.tex](../Overleaf/chapters/ch3_methodology.tex) and [reading_notes.md](reading_notes.md).*
