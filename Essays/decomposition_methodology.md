# Temporal vs. Spatial Decomposition: 学术惯例与实现方案

> 本文梳理碳感知调度研究中 temporal/spatial 贡献分解的学术惯例，说明为何这是 mandatory analysis，并给出本论文的具体实现设计。

---

## 一、为什么必须做分解

LP 模型同时启用两种自由度：

- **时间维度**（temporal）：在截止时间内选择最优执行时段
- **空间维度**（spatial）：将负荷路由到碳强度最低的区域

如果只报告"LP 节碳 78.4%"，读者无法知道这 78.4% 从哪来：是因为时间调度有效，还是因为跨区域路由有效？审稿人必然追问这个问题。

Sukprasert et al.（EuroSys 2024）\[1\] 明确指出：prior work 最大的缺陷之一就是未能分离 temporal 和 spatial 贡献，导致结论缺乏可解释性。

---

## 二、文献中的标准做法

### 2.1 三变体法（Three-variant LP decomposition）

Sukprasert et al. \[1\] 及 "Spatio-temporal load shifting for truly clean computing"（Applied Energy 2024）\[2\] 采用的标准方法：

| 变体 | 时间自由度 | 空间自由度 | 描述 |
|------|-----------|-----------|------|
| **Uniform** | ✗ | ✗ | 均匀分配，作为零节碳基准 |
| **Spatial-only** | ✗（δ=1，立即服务）| ✓（σ=1，无地理限制）| 到达即路由到最近清洁区域 |
| **Temporal-only** | ✓（δ=24，全窗口）| ✗（σ=0，锁定在 home region）| 在 home region 内选最优时段 |
| **Full LP** | ✓ | ✓ | 两者同时优化 |

### 2.2 加法分解（Additive Decomposition）

全节碳可被分解为三个加法项 \[1,2\]：

$$\text{saving}_{\text{full}} = \underbrace{\text{saving}_{\text{spatial}}}_{\text{空间贡献}} + \underbrace{\text{saving}_{\text{temporal}}}_{\text{时间贡献}} + \underbrace{\Delta_{\text{interaction}}}_{\text{交叉项}}$$

其中：
$$\Delta_{\text{interaction}} = \text{saving}_{\text{full}} - \text{saving}_{\text{spatial}} - \text{saving}_{\text{temporal}}$$

**交叉项的含义**：联合优化所产生的"复利效应"——先把负荷路由到清洁区域，再在该区域内选最干净的时段，所获得的额外收益超过两者独立贡献之和。

### 2.3 为什么 temporal-only 可能是负数

Sukprasert et al. \[1\] 观察到：对于 home region 是高碳强度 grid（如 PJM，400–500 gCO₂/kWh）的情况，temporal-only 的结果可能**差于 Uniform baseline**。原因：

- Uniform baseline 自动将 20% 的负荷分配给 Finland、Belgium 等清洁区域（空间多样化）
- Temporal-only 强制将所有负荷锁定在 PJM（即使 PJM 是最脏的区域），且 PJM 的 CI 时间变异性很小（标准差/均值 ≈ 0.11），没有明显的低碳时段可以利用
- 净效果：temporal-only 反而排放更多碳

这不是 bug，这是 finding：**碳感知调度的时间维度对高碳 home region 反而有害**。

---

## 三、参数设计

三种变体在相同数据、相同目标函数权重（α=0.5）下运行，仅变化约束：

| 变体 | δ（截止时间）| σ（地理上限）| κ/ρ/η |
|------|-------------|-------------|--------|
| Spatial-only | 1 h（立即服务）| 1.0（无限制）| 全部 inactive |
| Temporal-only | 24 h（全窗口）| 0.0（锁定 home）| 全部 inactive |
| Full LP（无约束）| 24 h | 1.0 | 全部 inactive |

所有变体均关闭 C6/C7（κ=1.0, ρ=1.0）和公平项（η=0），以确保分解只反映时间/空间自由度的纯效果，不受操作性约束影响。

---

## 四、分解公式

记 C 为总碳排（731 个窗口聚合）：

| 符号 | 含义 |
|------|------|
| $C_U$ | Uniform 碳排（基准）|
| $C_S$ | Spatial-only LP 碳排 |
| $C_T$ | Temporal-only LP 碳排 |
| $C_F$ | Full LP 碳排 |

节碳率：
$$s_X = \frac{C_U - C_X}{C_U} \times 100\%$$

交叉项：
$$\Delta = s_F - s_S - s_T$$

若 $\Delta > 0$：时间与空间优化存在正向互补（先去干净区域，再择时调度）。

---

## 五、可视化方案

**主图（Waterfall / Additive Bar）**：

```
 节碳率(%)
 80 │
    │  ████████████████ spatial (75.6%)
 40 │  ████  interaction (38%)
    │
  0 ──────────────────────────────── baseline
    │                
-40 │  ████████████████ temporal (-35.6%)
    │
    Spatial   Temporal   Interaction   Full LP
```

标注：
- Full LP bar = spatial + temporal + interaction（展示加法关系）
- Temporal bar为负，明确标注颜色区分
- 可加一条水平线标注 Full LP 总值（78.4%）

---

## References

\[1\] Sukprasert, T., Souza, A., Bashir, N., Irwin, D., & Shenoy, P. (2024). On the Limitations of Carbon-Aware Temporal and Spatial Workload Shifting in the Cloud. *EuroSys 2024*. https://dl.acm.org/doi/10.1145/3627703.3650079

\[2\] Gholizadeh, H., Hajiesmaili, M. H., & Zheng, R. (2024). Spatio-temporal load shifting for truly clean computing. *Advances in Applied Energy*, 14, 100174. https://www.sciencedirect.com/science/article/pii/S2666792424000404

\[3\] Radovanović, A., Koningstein, R., Schneider, I., Chen, B., Duarte, A., Roy, B., ... & Vahdat, A. (2023). Carbon-aware computing for datacenters. *IEEE Transactions on Power Systems*, 38(2), 1270–1280. https://ieeexplore.ieee.org/document/9770383/

\[4\] Acun, B., Lee, B., Kazhamiaka, F., Maeng, K., Gupta, U., Chakkaravarthy, M., Brooks, D., & Wu, C.-J. (2023). Carbon Explorer: A holistic framework for designing carbon-aware datacenters. *ASPLOS 2023*. https://arxiv.org/pdf/2201.10036
