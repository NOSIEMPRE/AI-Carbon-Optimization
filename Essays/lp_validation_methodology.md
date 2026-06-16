# LP模型约束验证的通用做法

> 本文梳理优化模型约束验证的理论基础和学术惯例，解释为何本论文的验证方案应从"逐约束单独测试"改为"小样本集成测试"，并说明如何判断一个测试是否真正有效。

---

## 1. 理论基础：KKT条件与互补松弛

LP的最优解必须同时满足三个条件，合称**KKT条件**（Karush-Kuhn-Tucker conditions）：

1. **原始可行性（Primal feasibility）**：解满足所有约束。
2. **对偶可行性（Dual feasibility）**：每个约束对应的对偶变量（影子价格）非负。
3. **互补松弛（Complementary slackness）**：对每个不等式约束，要么约束紧（左右端相等），要么对应的影子价格为零，两者必居其一。

互补松弛条件的直接推论是：

> **如果一个约束的影子价格为零，则该约束不影响最优解。**  
> 换言之，去掉这个约束，最优解不变，目标函数值不变。

这就是"约束是否有效（binding）"的精确定义。一个在最优解处不紧的约束，其影子价格为零，对模型的结论没有贡献。验证它是否满足毫无意义——它在任何合理的解里都会自然满足 \[1,2\]。

---

## 2. 学术惯例：验证什么，怎么验证

### 2.1 正确性验证（Verification）

**验证的对象是：LP代码是否正确实现了数学公式。**

Williams（2013）在 *Model Building in Mathematical Programming* 中指出，模型验证包括两个层面：一是形式检验（formulation check），即对照原始问题确认目标函数系数、约束系数、变量边界是否写对；二是行为检验（behavioral check），即在已知答案的小实例上运行，确认解与预期一致 \[3\]。

Fourer、Gay和Kernighan在 *AMPL: A Modeling Language for Mathematical Programming* 中描述了类似的做法：在"toy instance"上运行完整模型，对照手算结果或枚举结果核验求解器输出。**关键要求：该实例必须让所有约束都有机会起作用，否则只是在验证可行性，而非约束逻辑 \[4\]。**

### 2.2 有效性验证（Validation）

**有效性的对象是：模型是否正确表达了现实问题。**

这通常通过以下手段结合进行：

- **影子价格（Shadow price / Dual variable）分析**：最优解的影子价格直接报告每个约束的边际成本。若约束 $c$ 的影子价格为零，则该约束在这个实例中不起约束作用，模型行为与移除该约束完全一致。
- **灵敏度分析（Sensitivity analysis）**：对每个约束参数从宽到严扫描一次，观察目标函数如何变化。若收紧某约束后目标变差，该约束是有效的；若毫无变化，说明该约束在当前参数组合下是冗余的。
- **基准比较（Baseline comparison）**：将约束版本与无约束版本对比，量化每个约束引入的"代价"（碳成本上升多少）。

---

## 3. 为什么逐约束单独测试是错的

逐约束测试（每个约束设计一个独立的玩具实例）有两个根本问题：

**问题一：约束交互被忽略。**  
多个约束同时激活时会产生交互效应。以C6（ramp rate）和C7（dynamic range）为例：若LP在24小时内试图将全部负载集中在2小时的清洁窗口，C6限制了每小时的爬坡速度，C7限制了全程峰谷差。两个约束同时存在时比单独任何一个都更紧——只测单个约束的玩具实例看不到这种效应。

**问题二：人工数据掩盖了真实数据的行为。**  
为了让某个约束在孤立实例中恰好binding而手工构造的CI序列，未必反映真实网格信号的统计特性（如季节性变化、多区域相关性）。在真实数据上不起作用的约束，在人工实例里可能人为地显得重要。

Williams（2013）明确建议：验证应在"representative instances"（代表性实例）而非"adversarial instances"（对抗性实例）上进行 \[3\]。前者反映模型的实际应用场景；后者只能证明在极端条件下不出错。

---

## 4. 正确的做法：集成测试 + 互补松弛报告

学术上被接受的验证框架是：

**Step 1：选取代表性小样本。**  
取真实数据的一个时间窗口（足够包含一次完整的调度周期，如7天），选择参数使每个约束都有机会成为binding。

**Step 2：运行完整模型，所有约束同时激活。**  
不分别测试约束，只跑一次完整LP。

**Step 3：验证原始可行性。**  
逐一检查所有约束是否满足（数值容差内）。这是最基本的"代码是否实现正确"检验。

**Step 4：报告互补松弛状态。**  
对每个约束，比较observed value与bound的差距：

| 约束 | Observed | Limit | 状态 |
|------|----------|-------|------|
| C1 等式 | $\sum x = D$ | $= D$ | 等式，必然紧 |
| C2 deadline | covered = required | 等于或接近 | 紧则说明deadline在约束调度 |
| C3 C_max | max(x) | C_max | 若 max(x) ≈ C_max 则紧 |
| C4 σ | max off-home fraction | σ | 若接近σ则紧 |
| C5 M (公平) | M | max regional carbon | 若相等则紧 |
| C6 κ | max ramp | κ·C_max | 若相等则紧 |
| C7 ρ | max swing | ρ·C_max | 若相等则紧 |

**若某约束不紧（slack远大于0），说明参数选取需要调整，使该约束在这个实例中实际起作用。**

**Step 5：验证约束集体产生了预期效果。**  
将约束版本的目标与松弛基准比较（如全留home region的碳成本）。若约束解的碳成本比松弛基准高，说明约束确实在压缩可行域。

---

## 5. 在本论文中的应用

本论文的LP有7个约束（C1-C7）。基于上述框架，正确的验证做法是：

- 取真实数据前7天（168小时），3个区域（PJM作home、Finland、Belgium）
- 选取参数使每个约束binding：σ=0.5使C4紧，κ=0.2使C6紧，ρ=0.3（而非0.4）使C7紧，delta=12（而非24）使C2紧
- 运行一次完整LP，输出所有约束的observed vs limit
- 报告影子价格（scipy的linprog通过`res.ineqlin.marginals`返回对偶变量）

当前验证代码（`src/test_validation.py`）已完成Step 2-3，需要补充Step 4的系统性binding报告和参数调整以确保所有约束紧。

---

## 6. 参考碳感知调度文献的做法

Wijayawardana & Chien（SoCC 2025）验证其LP调度模型时，并未逐约束构造人工实例，而是直接在真实云负载trace和电网数据上运行完整模型，然后：
1. 验证所有容量约束在解中满足
2. 通过sensitivity sweep展示每个参数（step size即κ，dynamic range即ρ）对goodput的影响——这同时证明了这些约束在现实场景中确实binding \[5\]

这与Williams的建议一致：用灵敏度分析替代逐约束孤立测试，既验证约束正确性，也量化约束的实际经济代价。

---

## References

\[1\] Boyd, S., & Vandenberghe, L. (2004). *Convex Optimization*. Cambridge University Press. Chapter 5 (KKT conditions). Available at: https://web.stanford.edu/~boyd/cvxbook/

\[2\] Vanderbei, R. J. (2020). *Linear Programming: Foundations and Extensions*, 5th ed. Springer. Chapter 6 (Sensitivity Analysis and the Dual). https://link.springer.com/book/10.1007/978-3-030-39415-8

\[3\] Williams, H. P. (2013). *Model Building in Mathematical Programming*, 5th ed. Wiley. Chapters 2–3 (model formulation and validation).

\[4\] Fourer, R., Gay, D. M., & Kernighan, B. W. (2003). *AMPL: A Modeling Language for Mathematical Programming*, 2nd ed. Thomson Brooks/Cole. https://vanderbei.princeton.edu/307/textbook/AMPLbook.pdf

\[5\] Wijayawardana, R., & Chien, A. A. (2025). Scheduling Cloud VMs on Variable Capacity Datacenters. *Proceedings of the 2025 ACM Symposium on Cloud Computing (SoCC '25)*. https://dl.acm.org/doi/10.1145/3772052.3772250

\[6\] MIT OpenCourseWare (2011). *Linear Programming Duality*. 15.053 Lecture Notes. https://web.mit.edu/15.053/www/AMP-Chapter-04.pdf
