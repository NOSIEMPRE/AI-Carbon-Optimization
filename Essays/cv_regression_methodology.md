# CV Regression: 为什么各区域的 Temporal Saving 不一样

> 本文说明 coefficient of variation (CV) 与 temporal-only 节碳率之间关系的文献依据，以及本论文的实现方式。这是 [[decomposition_methodology]] 的延伸诊断，不是独立的因果检验。

---

## 一、动机

Decomposition 分析（见 [[decomposition_methodology]]）显示：以 PJM 为 home region 时，temporal-only 节碳率是 **−35.6%**（比 Uniform 还差）。问题是：这是 PJM 的特例，还是所有区域都这样？

直觉上，时间维度的调度收益应该取决于：**该区域碳强度在时间上的波动程度**。如果一个区域全天 CI 几乎不变（比如全靠核电的稳定供给），那无论怎么挑时段，结果都一样——temporal shifting 没有意义。如果 CI 波动很大（比如风光占比高的区域，白天夜晚、有风没风差异巨大），就有明显的"好时段"和"坏时段"可以利用。

---

## 二、文献依据

### 2.1 CV 作为波动性的标准度量

Coefficient of variation（CV = std / mean）是量化碳强度时间波动性的常用指标 \[1\]。

### 2.2 可再生能源占比 → 波动性 → 时间灵活性价值

Sukprasert et al.（EuroSys 2024）\[1\] 及相关文献指出：
- 可再生能源占比高的电网（如加州，风光约 50%）：碳强度均值低，但**波动性高**
- 化石燃料主导的电网（如煤电为主）：碳强度均值高，且**波动性低**（基荷发电平稳）
- **区域内 CI 波动越大，时间调度（temporal shifting）的潜在收益越高**——这是目前碳感知调度文献中被广泛验证的定性结论 \[1,2\]

这正是本论文 CV regression 想验证的关系：用 CV(CI) 作为自变量，预测 within-region temporal saving。

---

## 三、方法设计

对每个区域 $r$ 独立计算：

**自变量**：$CV_r = \dfrac{\text{std}(CI_r)}{\text{mean}(CI_r)}$，基于完整两年数据。

**因变量**：within-region temporal saving。即假设负荷被**锁定在区域 $r$ 内**（不能跨区域路由，对应 decomposition 中的 temporal-only 设定，但 home region 换成 $r$），与"区域 $r$ 内部均匀分配"基准比较：

$$\text{saving}_r = \frac{C_{\text{uniform},r} - C_{\text{temporal},r}}{C_{\text{uniform},r}} \times 100\%$$

其中：
- $C_{\text{uniform},r}$：demand 在区域 $r$ 内按小时均匀分布的碳排
- $C_{\text{temporal},r}$：LP 在区域 $r$ 内自由选择时段（σ=0 锁定 home=r，δ=24h 全窗口可调）的碳排

五个区域给出五个 $(CV_r, \text{saving}_r)$ 数据点，拟合简单 OLS 直线，报告斜率方向和 $R^2$。

---

## 四、统计局限性的诚实声明

**这不是一个有统计推断力的回归。** 只有 5 个数据点（5 个区域），自由度极低，$R^2$ 和 p-value 在这种样本量下没有传统意义上的统计显著性。

正确的定位：**诊断性图表（diagnostic plot）**，用于：
1. 说明 decomposition 里 PJM 的负 temporal saving 不是异常值，而是符合"低波动→低时间灵活性价值"这一普遍模式的一个样本点
2. 提供方向性证据（趋势是否符合理论预期），而非因果推断

这个定位在论文里需要明确写出来，避免被当作正式的统计检验来质疑。

---

## References

\[1\] Sukprasert, T., Souza, A., Bashir, N., Irwin, D., & Shenoy, P. (2024). On the Limitations of Carbon-Aware Temporal and Spatial Workload Shifting in the Cloud. *EuroSys 2024*. https://dl.acm.org/doi/10.1145/3627703.3650079

\[2\] Radovanović, A., Koningstein, R., Schneider, I., Chen, B., Duarte, A., Roy, B., ... & Vahdat, A. (2023). Carbon-aware computing for datacenters. *IEEE Transactions on Power Systems*, 38(2), 1270–1280. https://ieeexplore.ieee.org/document/9770383/
