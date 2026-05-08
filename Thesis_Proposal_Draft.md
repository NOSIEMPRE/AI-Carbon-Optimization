# Thesis Research Plan | 研究计划

**学生 / Student**: Yaxin (Isabel) Wu  
**导师 / Supervisor**: Prof. Bissan Ghaddar  
**项目 / Program**: Master of Business Analytics & Big Data, IE University  
**更新时间 / Last updated**: May 2026

---

## 1. 研究定位 | Research Positioning

**导师的核心问题**：如何建立一个系统框架，将电网碳强度信号转化为数据中心的实时调度决策？
*How to build a system framework that translates grid carbon intensity signals into real-time data center scheduling decisions?*

**本文的核心问题**：在这个框架下，如何用确定性数学优化方法（而非启发式规则），通过时间和空间两个维度的工作负载调度，最小化 AI 数据中心的碳排放？
*Within this framework, how can a deterministic mathematical optimization model — rather than heuristic rules — minimize AI data center carbon emissions through joint temporal and spatial workload scheduling?*

**两者的联系**：导师定义了问题框架（VCC 机制、数据来源、仿真架构），本文将框架中"Carbon-Aware Optimization"环节从规则驱动升级为可证明最优的数学规划，是对导师研究的深化和形式化。
*The supervisor defines the problem framework; this thesis formalizes the optimization component into a mathematically tractable program, deepening and extending the existing framework.*

---

## 2. 核心研究问题 | Core Research Question

**如何建立一个以碳强度（CI）、可再生能源占比（RF）、碳强度波动性（CV）为核心指标的确定性数学规划模型，通过时间维度（何时运行）和空间维度（在哪里运行）的联合工作负载调度，最小化跨五个地区的 AI 数据中心碳排放？**

*How can a deterministic mathematical programming model — driven by carbon intensity (CI), renewable energy fraction (RF), and CI variability (CV) — minimize AI data center carbon emissions through joint temporal (when to run) and spatial (where to run) workload scheduling across five grid regions?*

---

## 3. 数据 | Data

| 数据 | 来源 | 粒度 | 时间范围 |
|------|------|------|---------|
| 碳强度 CI (gCO₂eq/kWh) | ElectricityMaps API | Hourly | 2021–2025 |
| 可再生能源占比 RF (%) | ElectricityMaps API | Hourly | 2021–2025 |
| 电价（约束参数）| PJM / NYISO / ENTSO-E / EMC | Hourly | 2021–2025 |
| 工作负载 traces | Google Cluster Traces (public) | Per-job | — |

**五个目标地区 / Five target regions**：US-MIDA-PJM, US-NY-NYIS, FI, BE, SG

| 地区 | 电网特征 | CI 特点 | 调度机会 |
|------|---------|---------|---------|
| PJM | 煤/气/核混合 | 高且波动大 | 最大 |
| NYISO | 水电+核电为主 | 中等，日内波动明显 | 较大 |
| FI | 水电+核电+风电 | 整体偏低，季节性差异大 | 中等 |
| BE | 核电占比高，欧洲互联 | 中低，受邻国影响 | 中等 |
| SG | 几乎全天然气 | 高但稳定，波动小 | 最小 |

SG 是重要的对照案例：波动性低意味着时间维度优化收益有限，验证了"并非所有地区都适合 temporal shifting"的论点。

---

## 4. 方法论 | Methodology

本文核心工作为 Optimization。历史 CI/RF 数据直接作为模型输入，评估通过历史数据回放（backtesting）完成。

```
历史 CI/RF 数据（ElectricityMaps）
          ↓
Deterministic Optimization Model（Gurobi）
  Phase 1: Temporal Shifting
  Phase 2: Spatial Shifting
          ↓
Evaluation（Backtesting vs. Baselines）
```

---

### 核心指标的选择与来源 | Indicator Rationale and Data Source

#### 为什么选这三个指标？

**CI（碳强度）— 目标函数核心信号**
直接衡量单位用电的碳排放，是碳感知调度最基础的驱动变量，跨地区完全可比（gCO₂eq/kWh）。

**RF（可再生能源占比）— 区分清洁电的来源质量**
CI 低不代表来源相同。芬兰凌晨的低 CI 来自核电（稳定、持续），比利时某风力大的下午的低 CI 来自风电（间歇、窗口短）。两种情况对调度策略的含义完全不同。加入 RF 后，模型在可再生能源充沛的时段额外给予激励，有助于消纳波动性可再生能源，而不只是追求低 CI。
*CI alone doesn't reveal why intensity is low. RF distinguishes stable clean energy (nuclear) from variable clean energy (wind/solar), enabling the model to prioritize renewable consumption, not just low-carbon moments.*

**CV（碳强度波动性）— 衡量各地区的调度机会大小**
CV 是 CI 时间序列的变异系数（标准差/均值），衡量"这个地区值不值得做时间维度的 shifting"。新加坡 CI 全天几乎不变，temporal shifting 收益接近零；PJM 日内 CI 波动剧烈，shifting 的收益很大。CV 本质上是优化模型在各地区能取得多少改善的预测指标，用于解释跨地区结果差异，是独立的分析贡献。
*CV (coefficient of variation of CI) measures how much a region can benefit from temporal shifting. High CV = high potential savings; low CV = limited gain. This explains regional result differences and is a novel analytical contribution.*

#### 数据来源 | Data Availability from ElectricityMaps

三个指标均来自导师指定的数据源 ElectricityMaps，无需额外采集。
*All three metrics are derived from ElectricityMaps, the data source specified by the supervisor.*

| 指标 | 是否直接提供 | 获取方式 |
|------|------------|---------|
| **CI** | 直接提供 | API 字段 `carbonIntensity`（gCO₂eq/kWh）|
| **RF** | 间接提供 | `powerBreakdown` 字段中风电+太阳能+水电占比加总 |
| **CV** | 不直接提供 | 从历史 CI 时间序列计算：std(CI) / mean(CI) |

#### 指标在模型中的角色 | Role in the Model

| 指标 | 在模型中的作用 |
|------|--------------|
| **CI(t)** | 目标函数的核心优化信号 |
| **RF(t)** | 进入目标函数，区分稳定清洁电（核电）和波动清洁电（风/光）|
| **CV**（地区层面）| 解释跨地区结果差异；辅助空间维度迁移决策 |
| **电价** | 各地区独立预算约束，不跨区比较绝对价格 |

---

### 核心优化模型 | Unified Joint Optimization Model

> 导师建议（May 2026）：时间和空间维度合并为一个统一 LP，模型自行决定最优地点和时间，不做两阶段分解。

**决策变量**：$x_{r,t} \geq 0$ — 地区 $r$ 在第 $t$ 小时承担的计算负载（kW）
*Compute load assigned to region r at hour t — covers both temporal and spatial dimensions simultaneously.*

**目标函数**：
$$\min \sum_{r \in R} \sum_{t \in T} x_{r,t} \cdot CI_r(t) \cdot (1 - \alpha \cdot RF_r(t))$$

- $CI_r(t)$：碳强度信号，来自 ElectricityMaps，是调度的核心驱动变量 [Ref: Radovanovic et al., 2023]
- $(1 - \alpha \cdot RF_r(t))$：RF 加权项，低碳 + 高可再生时段获得额外激励，区分核电与风/光 [Novel extension]
- 模型同时在 R 个地区、T 个时段中寻找全局最优分配，无需预设"先时间后空间"的顺序

**约束**：
```
(C1) 需求完成：  Σ_r Σ_t x_{r,t} = D                    [Ref: Liu et al., 2012]
(C2) 地区容量：  x_{r,t} ≤ C_max,r      ∀r,t            [Ref: Liu et al., 2012]
(C3) VCC 约束：  x_{flex,r,t} ≤ VCC_r(t) ∀r,t           [Ref: Colangelo et al., 2025]
(C4) 电价预算：  Σ_t x_{r,t}·P_r(t) ≤ Budget_r  ∀r      [Ref: Lin et al., 2026]
(C5) 非负：      x_{r,t} ≥ 0
```

**公式来源说明 | Model Validation References**：

| 组件 | Reference |
| ---- | --------- |
| CI(t)·L(t) 碳成本目标形式 | Radovanovic et al. (2023), IEEE Trans. Power Systems, Eq. carbon objective |
| 多地区 LP 结构与需求/容量约束 | Liu et al. (2012), ACM SIGMETRICS, workload scheduling LP |
| VCC(t) 虚拟容量曲线约束 | Colangelo et al. (2025), arXiv:2507.00909, Section III |
| 跨地区时空联合调度框架 | Lin et al. (2026), Renewable Energy, multi-datacenter LP |
| RF 加权项 (1−α·RF) | 本文创新，受 Radovanovic et al. (2023) 启发，区分可再生能源质量 |

**输出**：最优分配矩阵 $x^*_{r,t}$，事后分解时间维度 vs. 空间维度各自的边际碳节省贡献。
*Post-hoc decomposition: compare x* against temporal-only and spatial-only counterfactuals to quantify each dimension's marginal contribution.*

**求解器**：Gurobi LP（连续变量）；若引入工作负载类型离散决策则升级为 MIP

---

### Evaluation — Backtesting

用两年历史数据回放验证优化效果，模拟"实时决策"场景（滚动窗口，不看未来）。

**Baselines**：

| Baseline | 描述 |
|----------|------|
| Carbon-Agnostic | 完全不考虑碳，均匀调度 |
| Simple Temporal Shifting | 规则驱动：把所有弹性负载推到 CI 最低时段 |
| Oracle | 完美预知未来 24h CI（理论上界）|
| **本文模型** | 确定性 LP/MIP，历史数据驱动的 VCC |

**核心分析**：
- 各地区碳节省量 vs. 三个 baseline
- Phase 1（时间）vs. Phase 2（空间）各自的边际贡献
- CV 与碳节省量的相关性（解释地区差异）

---

## 5. 主要贡献 | Expected Contributions

1. **形式化数学规划**：将导师的启发式 VCC 框架升级为可证明最优的 LP/MIP，引入 RF 指标区分可再生能源类型
2. **时空联合优化**：两阶段分解（时间 + 空间），量化各维度的边际贡献
3. **五地区实证评估**：用 CV 解释跨地区差异，提出 Carbon Scheduling Opportunity 的地区画像

---

## 6. 未来延伸方向 | Future Work

- **电力成本深度建模**：将电价约束升级为目标函数，结合各地区市场机制（PJM LMP、Nord Pool、USEP）建模
- **Surrogate / RL 模型**：用机器学习近似 Gurobi 最优解，实现实时调度（对应导师 Slide 5 Block ④）

---

## 7. 时间计划 | Timeline（8 Weeks）

| 周次 | 重点 | 交付物 |
|------|------|--------|
| Week 1 | 数据采集 + EDA | 五地区 CI/RF 清洗数据集；描述性统计；分布图与波动性分析 |
| Week 2 | 模型设计 + Gurobi 环境搭建 | 统一 LP 公式化；Gurobi 跑通单地区单天 |
| Week 3 | 单地区实现与验证 | 五地区时间维度验证；VCC 生成 |
| Week 4 | 完整联合模型实现 | 五地区统一 LP（时间+空间）；跑通全量 |
| Week 5 | Backtesting | 两年数据回放；碳节省 vs. 各 baseline 计算完毕 |
| Week 6 | 结果分析 | 地区对比；时间 vs. 空间边际贡献分解；CV 相关性分析 |
| Week 7 | 论文写作（核心章节）| Introduction, Methodology, Results 初稿 |
| Week 8 | 论文写作（收尾）| Literature Review, Discussion, Conclusion；修改提交 |

**Scope 边界**：若引入工作负载类型离散变量导致 MIP 求解时间过长，降级为 LP relaxation；电价深度建模为 future work。

---

## 8. 参考文献 | References

1. Radovanovic et al. (2023). Carbon-aware computing for datacenters. *IEEE Transactions on Power Systems*.
2. Liu et al. (2012). Renewable and cooling aware workload management for sustainable data centers. *ACM SIGMETRICS*.
3. Hanafy et al. (2025). CarbonFlex: Enabling carbon-aware provisioning and scheduling for cloud clusters. *arXiv*.
4. Lin et al. (2026). Carbon-aware optimization for Internet data centers with renewable generation and carbon emission trading. *Renewable Energy*.
5. Colangelo, Coskun et al. (2025). Turning AI data centers into grid-interactive assets. *arXiv:2507.00909*.
