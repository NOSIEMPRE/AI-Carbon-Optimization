# Sensitivity Analysis 与 Heuristic Comparison 的学术惯例

> 本文梳理这两类分析在优化/调度论文中的标准做法，指出当前实现的问题，并给出重新设计方案。

---

## 一、Sensitivity Analysis

### 1.1 标准方法：OAT（One-At-a-Time）

对于参数数量较少（≤10）的优化模型，学术上最常用的是 **OAT（一次变动一个参数）** 法 \[1,2\]：

- 固定其他参数在 baseline 值
- 对目标参数扫描其合理范围
- 记录每个参数值下的目标函数值（碳排放量）
- 重复对每个参数

OAT 是 **local sensitivity analysis**，分析的是模型在 baseline 附近对每个参数的局部响应。Saltelli et al. \[1\] 指出，OAT 适合参数交互效应较小、主效应主导的模型；对于强交互模型应使用 Sobol 等全局方法。LP 是线性模型，参数间无高阶交互，OAT 合适。

### 1.2 标准可视化：Tornado Diagram

OAT 分析的标准可视化是 **Tornado Diagram（龙卷风图）**，来自 INFORMS Interfaces \[3\]：

- **横轴**：目标函数值的变化量（或相对于 baseline 的百分比变化）
- **纵轴**：各参数，按影响幅度从大到小排列（最大的在上方，形似龙卷风）
- **每行**：一个横向条形，左端为参数在某一极端值时的结果，右端为另一极端值时的结果
- **中心竖线**：baseline 处的目标值（0% 变化）

这种图的优势：一张图呈现所有参数的相对重要性，排名关系一目了然。

**不应该做的**：
- 多个独立子图各自有不同 y 轴（标准化方式不一致，难以比较参数间重要性）
- 用百分比节省 vs Uniform 作为纵轴（把 LP 本身的能力和参数效果混在一起）
- 在 sensitivity 图里放其他 solver（Greedy、FCFS、Oracle）——这是 heuristic 分析的内容

### 1.3 应用到本论文

**X 轴**：LP 碳排相对于 baseline LP 的百分比变化（baseline = 全量参数下的 LP 碳排，即 σ=1, κ=1, ρ=1, η=0, δ=24）

**Y 轴**：6 个参数，按影响幅度降序排列

**每行的两端**：
- 约束参数（σ, κ, ρ, δ）：最紧 → 最松
- 目标参数（η）：最大权重 → 0
- α：全范围（α 影响较小，排在下方）

---

## 二、Heuristic Analysis

### 2.1 标准方法：Optimality Gap / Efficiency Ratio

在调度算法比较中，学术惯例是以 **LP（或精确最优）作为参考基准**，衡量每个启发式算法与最优解的差距 \[4,5\]：

**Optimality Gap**（最优性差距）：
$$\text{gap}_{\text{alg}} = \frac{C_{\text{alg}} - C_{\text{LP}}}{C_{\text{LP}}} \times 100\%$$

LP 的 gap 定义为 0%，其他算法的 gap 表示相对于最优解多排放了多少碳。

**Efficiency Ratio**（另一种常见形式）：
$$\text{eff}_{\text{alg}} = \frac{C_{\text{Uniform}} - C_{\text{alg}}}{C_{\text{Uniform}} - C_{\text{LP}}} \times 100\%$$

即"该算法捕获了LP潜在节碳空间的多少比例"：
- LP = 100%（全部捕获）
- Oracle > 100%（超过 LP，因为更长的look-ahead）
- Greedy ≈ 100%（在无约束情况下匹配 LP）
- Uniform = 0%（无节碳）
- FCFS < 0%（不仅没有节碳，反而比 Uniform 还差）

这个指标比"相对于 Uniform 的节碳百分比"更清晰，因为它直接回答了"每个启发式距最优有多远"的问题。

Carbon Explorer \[5\]（Google, ASPLOS 2022）和 LinTS \[6\] 均采用类似框架：以 LP Oracle 作为 ceiling，测量启发式对最优节碳空间的捕获率。

### 2.2 可视化标准

- **主图**：分组条形图（按算法分组，或按季节分组）
- **Y 轴**：efficiency ratio（% of LP saving captured），或 optimality gap
- **排序**：按整体性能从好到坏
- **季节分解**：作为次图，验证结论在不同季节是否稳健
- **LP 作为基准线**（efficiency=100% 或 gap=0%），Oracle 标注 look-ahead 收益

**不应该做的**：
- 在 heuristic 图里放 sensitivity 曲线
- 用 Uniform 作为基准（Uniform 是"什么都不做"，不是一个有意义的算法比较基准）
- 对所有算法用同一 y 轴而不区分 LP 这条基准线

---

## 三、本论文的重新设计方案

### Sensitivity：Tornado Diagram
- X 轴：LP 碳排相对 baseline 的变化（%）
- 每个参数一条横向 bar，从该参数最紧值到最松值
- 按 bar 宽度降序排列
- 竖线标注 baseline（0% 变化）

### Heuristic：Efficiency Ratio Bar Chart
- Y 轴：efficiency ratio = (C_Uniform - C_alg) / (C_Uniform - C_LP) × 100%
- LP = 100%，Oracle > 100%，FCFS < 0%（直观展示 FCFS 的反效果）
- 整体 + 季节分解

---

## References

\[1\] Saltelli, A., Ratto, M., Andres, T., Campolongo, F., Cariboni, J., Gatelli, D., Saisana, M., & Tarantola, S. (2008). *Global Sensitivity Analysis: The Primer*. John Wiley & Sons. https://www.researchgate.net/publication/253328104_Global_Sensitivity_Analysis_The_Primer

\[2\] Pannell, D. J. (1997). Sensitivity analysis of normative economic models: Theoretical framework and practical strategies. *Agricultural Economics*, 16(2), 139–152. https://www.sciencedirect.com/science/article/abs/pii/S0169515096012005 (also: Pannell 1997 — "Sensitivity analysis in LP: just be careful!" *EJOR*)

\[3\] Eschenbach, T. G., & McKeague, L. S. (1989). Exposition on using graphs for sensitivity analysis. *The Engineering Economist*, 34(4). Cited in: Eschenbach (1992). Spiderplots versus tornado diagrams for sensitivity analysis. *Interfaces*, 22(6), 40–46. https://pubsonline.informs.org/doi/10.1287/inte.22.6.40

\[4\] Dolan, E. D., & Moré, J. J. (2002). Benchmarking optimization software with performance profiles. *Mathematical Programming*, 91(2), 201–213. https://link.springer.com/article/10.1007/s101070100263

\[5\] Acun, B., Lee, B., Kazhamiaka, F., Maeng, K., Gupta, U., Chakkaravarthy, M., Brooks, D., & Wu, C.-J. (2023). Carbon Explorer: A holistic framework for designing carbon-aware datacenters. *ASPLOS 2023*. https://arxiv.org/pdf/2201.10036

\[6\] Khaled, A. R., et al. (2025). Carbon-aware temporal data transfer scheduling across cloud datacenters. arXiv:2506.04117. https://arxiv.org/pdf/2506.04117
