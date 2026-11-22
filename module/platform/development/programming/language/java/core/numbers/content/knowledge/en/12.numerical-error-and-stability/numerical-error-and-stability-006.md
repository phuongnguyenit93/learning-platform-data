# Problem Conditioning and Cases Where Input Error Is Amplified

In numerical computing, **a badly wrong result does not necessarily stem from buggy Java code**. Some problems are inherently sensitive: changing the input data by only a tiny amount causes **the output value to change drastically in relative terms**. This property is called **problem conditioning** (*conditioning*). An *ill-conditioned* problem can still be solved with a stable algorithm; conversely, a well-conditioned problem can still be computed inaccurately if an unstable formula or implementation is chosen.

A simple example is taking the difference of two close numbers:

```text
a = 1 + 2^-40
b = 1

a - b = 2^-40

If a increases by 2^-50:
(a + 2^-50) - b = 2^-40 + 2^-50
```

The **absolute change** in both input and output is `2^-50`, yet the **ratio of output change to the initial difference** is `2^-10 = 0.0009765625` (nearly 0.1%). Meanwhile, the relative change in `a` is only about `8.88 × 10^-16`. The relative discrepancy is amplified more than **one trillion times**.

This lesson explains absolute conditioning, relative conditioning, condition numbers, near-canceling subtraction, problems near singularities, and how to distinguish **inherent input sensitivity** from **algorithmic error** when programming in Java.

## 1. Two Types of Error to Separate

Given a mathematical problem that takes input `x` and computes output `f(x)`. In practice, the computer may receive `x̃` instead of `x` due to measurement data, text-to-floating-point conversion, or results of prior calculations. The computer then produces an approximate result `ŷ`.

We can analyze two distinct effects:

1. **Effect of input perturbation:** compare `f(x̃)` with `f(x)`. If a slight change in input causes the exact mathematical solution to change sharply, **the problem is sensitive**. This is conditioning.
2. **Effect of algorithm/machine arithmetic:** compare `ŷ` with `f(x̃)`. If the algorithm introduces substantial additional error due to rounding, overflow, underflow, or adverse transformations, that is an issue of **algorithmic stability** (*numerical stability*).

A concise summary:

```text
Ideal input x
      │ measurement/data-conversion error
      ▼
Actual input x̃ ──[mathematical problem]──► f(x̃)
      │                                       │
      └──────[actual numerical algorithm]────► ŷ
```

**Conditioning** pertains to the mathematical function itself and the input point; **stability** pertains to how that function is computed. A good algorithm can reduce **additional** computation error, but cannot guarantee recovering information absent from the input.

## 2. Absolute Error and Relative Error

For a true quantity `v` and an approximate quantity `ṽ`:

```text
Absolute error:         |ṽ - v|
Relative error:         |ṽ - v| / |v|    (when v is nonzero)
```

For example: the same absolute error of `0.001` is only a `10^-6` ratio at a value of `1000`, whereas at a value of `0.01` it is a `0.1` ratio, or **10%**. Thus, you must clarify whether you are referring to **absolute magnitude** or **relative ratio**.

For an output of 0 or very close to 0, relative error can be **undefined or huge** even when absolute error is tiny. In such cases, an absolute error criterion scaled to the business domain is usually more useful. Do not blindly divide by a near-zero value and interpret the huge number as "the algorithm is definitely buggy."

Note that Java `double` has finite values, `NaN`, Infinity, and `+0.0`/`-0.0`; if writing your own error-measurement tool, define how these cases are handled before dividing or comparing.

## 3. Absolute and Relative Conditioning of a Single-Variable Function

For a differentiable function `f(x)` and a small perturbation `δx`, the linear approximation is:

```text
δy = f(x + δx) - f(x) ≈ f'(x) × δx
```

**Local absolute sensitivity** is reflected by `|f'(x)|`: a large value indicates that a small absolute perturbation in `x` can produce a large absolute change in `f(x)`.

If `x ≠ 0` and `f(x) ≠ 0`, the **local relative condition number** is typically defined as:

```text
κ_rel(x) = |x × f'(x) / f(x)|
```

When `δx` is small enough for the linear approximation to hold:

```text
|δy| / |f(x)| ≈ κ_rel(x) × (|δx| / |x|)
```

Interpretation:

- `κ_rel ≈ 1`: output relative error is of the same order as input relative error (under the local model).
- `κ_rel ≫ 1`: input relative error can be **strongly amplified** in the output; this is poor relative conditioning.
- `κ_rel ≪ 1`: a small relative perturbation in input can produce an even smaller relative perturbation in output.

This is a **local approximation**, not a guarantee for large perturbations. The condition number also depends on **the input/output measurement norms and problem formulation**; near zero, absolute and relative scales can lead to different conclusions.

## 4. Subtracting Two Close Numbers: Small Output, High Relative Sensitivity

Consider `f(a,b) = a - b`. This is a two-input problem. If both `a` and `b` are perturbed:

```text
a → a + δa
b → b + δb

(a + δa) - (b + δb) = (a - b) + (δa - δb)
```

The absolute error of the difference **does not exceed** `|δa| + |δb|`, yet if `|a-b|` is very small relative to `|a|` and `|b|`, the relative error of the difference can be huge. A relative conditioning measure for subtraction (when input components have comparable relative errors) is:

```text
κ_sub ≈ (|a| + |b|) / |a - b|
```

When `a ≈ b`, the denominator is tiny, making `κ_sub` large. This does not mean the CPU's subtraction instruction is necessarily wrong. On the contrary, subtracting two sufficiently close floating-point numbers is sometimes **completely exact for the two represented values** (related to Sterbenz's lemma). The issue is that if the input data shifts slightly, **the exact answer to the problem also shifts significantly in proportion**.

An example chosen with exact representable binary numbers:

```java
double a = 1.0 + 0x1.0p-40;
double changedA = a + 0x1.0p-50;
double difference = a - 1.0;
double changedDifference = changedA - 1.0;
```

In Java hexadecimal floating-point literals, `0x1.0p-40` is `2^-40` and `0x1.0p-50` is `2^-50`. All of these values are represented accurately by `double`.

| Metric | Value |
| --- | --- |
| Initial difference `a - 1` | `2^-40` |
| Perturbation added to `a` | `2^-50` ≈ `8.881784197001252E-16` |
| Absolute change in difference | Also `2^-50` |
| Relative change in difference | `2^-10 = 0.0009765625` |
| Relative change in `a` | About `8.88E-16` |
| Relative amplification factor at this point | Nearly `2^40`, over one trillion times |

In this example where exactly one input varies, we view `f(a)=a-1`; the relative condition number is `|a/(a-1)| = 2^40+1`. The amplification factor computed from the two actual differences also equals **1_099_511_627_777** (printed as an integer), while the subtraction in the example **suffers no output rounding error**. This clearly demonstrates that poor conditioning and algorithmic instability **are not the same concept**.

## 5. Functions with a Near-Zero Denominator: Ill-Conditioning Near a Singularity

Consider:

```text
f(x) = 1 / (x - 1),   x ≠ 1

f'(x) = -1 / (x - 1)^2

κ_rel(x) = |x / (x - 1)|
```

As `x` approaches `1`, both the absolute derivative and the relative condition number can become very large. For instance, with `x = 1 + 2^-20`:

```text
f(x) = 2^20 = 1_048_576
κ_rel(x) ≈ 2^20
```

If `x` increases by `2^-40` (about `9.09 × 10^-13`), the output changes to nearly `1_048_575.0000009537`. The input changes by a tiny amount, yet the relative change in output has a magnitude of nearly one part per million—an amplification factor of roughly one million times relative to the input's relative error.

This is a consequence of the problem being **near a pole**, not because a programmer missed parentheses. A stable algorithm computing `1/(x-1)` must still suffer this sensitivity if the true value of `x` is uncertain.

At **exact `x = 1.0`**, dividing `1.0 / (x - 1.0)` in Java returns **`+Infinity`** per floating-point semantics; it does not throw `ArithmeticException` like **integer** division by zero. In real programs, check the domain and distance from the singularity before using the result.

## 6. Why Can't a "Stable Algorithm" Eliminate Ill-Conditioning?

An algorithm is called **numerically stable** when its computational error is well controlled relative to the requirements and the sensitivity of the problem. Distinguish two common evaluation perspectives:

- **Forward error:** `|ŷ - f(x)|`, i.e., the distance from the machine's answer to the ideal answer at the original input.
- **Backward error:** checking whether `ŷ` can be interpreted as the exact answer `f(x+Δx)` of **an input close to `x`**. If so, with `Δx` sufficiently small under the chosen norm, the algorithm can be judged *backward stable*.

For a well-conditioned problem, an algorithm with small backward error usually yields small forward error. For an ill-conditioned problem, **even a very small input change** can produce large forward error. A rule of thumb at the local approximation level is:

```text
output relative error
    ≈ condition number × input relative error
      + algorithmic error contribution
```

This formula is intuitive rather than an additive error law applicable verbatim to every function or `NaN`/Infinity case. Exact analysis requires specifying the norm, error terms, and input range. Nevertheless, the crucial principle is: **a good algorithm cannot turn an ill-conditioned problem into a well-conditioned one merely by rewriting the code**.

## 7. The Converse Case: Well-Behaved Problem, Unstable Formula

Consider the function:

```text
g(x) = sqrt(x + 1) - sqrt(x),  for x ≥ 0
```

When `x` is very large, the two square roots are nearly equal. Subtracting the two numbers after rounding can **cancel out almost all significant digits**. Yet we can transform it algebraically (for `x ≥ 0`):

```text
sqrt(x+1) - sqrt(x)
    = ((x+1)-x) / (sqrt(x+1)+sqrt(x))
    = 1 / (sqrt(x+1)+sqrt(x))
```

In Java:

```java
double x = 1.0e16;
double direct = Math.sqrt(x + 1.0) - Math.sqrt(x);
double stable = 1.0 / (Math.sqrt(x + 1.0) + Math.sqrt(x));
```

For `x = 1e16`, `x + 1.0` rounds back to `x` in `double`; the direct formula gives **`0.0`**. The denominator-based form gives roughly **`5.0E-9`**, close to the mathematical value `1/(2×10^8)`.

The key takeaway: **computing `g(x)` is not inherently hopeless at large `x`** (in terms of relative sensitivity, it is quite well-conditioned in this region), yet computing the difference of two close square roots introduces instability. Rewriting the formula avoids cancellation-inducing subtraction. This is an **algorithmic** flaw, unlike the `a-b` example with uncertain inputs and a tiny difference.

Do not blindly apply transformed formulas to every domain: check the domain of definition and risk of overflow/underflow of intermediates in the new formula. For the finite `x ≥ 0` and typical magnitudes in this example, the reciprocal form is a good choice to avoid cancellation.

## 8. A Better Formula Can Also Avoid Intermediate Overflow

Computing the length of a 2D vector:

```text
h(a,b) = sqrt(a^2 + b^2)
```

This problem is generally **not overly sensitive** to relative errors in its components when magnitudes are meaningful. However, the direct formula can overflow even though the final result still fits within the `double` range:

```java
double a = 1.0e200;
double naive = Math.sqrt(a * a + a * a); // Infinity.
double robust = Math.hypot(a, a);        // Finite, about 1.414e200.
```

Here `a*a = 1e400` exceeds `Double.MAX_VALUE` before calling `sqrt`. `Math.hypot` uses an appropriate method to avoid intermediate overflow/underflow in such cases. This example is not "fixing problem conditioning": it uses a **better algorithm** to compute a function whose result is inherently finite.

Practical message: before increasing numeric type precision, check whether a **library function or stable transformation** exists for the exact operation you are performing.

## 9. Standalone Java 17+ Program

Create the file **`ConditionSensitivityDemo.java`**:

```java
public class ConditionSensitivityDemo {
    public static void main(String[] args) {
        double x = 1.0 + 0x1.0p-40;
        double perturbed = x + 0x1.0p-50;
        double gap = x - 1.0;
        double perturbedGap = perturbed - 1.0;

        double relativeInputChange = (perturbed - x) / x;
        double relativeOutputChange = (perturbedGap - gap) / gap;
        System.out.println("gapHex=" + Double.toHexString(gap));
        System.out.println("changedGapHex=" + Double.toHexString(perturbedGap));
        System.out.println("absoluteInputChange=" + (perturbed - x));
        System.out.println("absoluteOutputChange=" + (perturbedGap - gap));
        System.out.println("relativeOutputChange=" + relativeOutputChange);
        System.out.println("relativeAmplificationRounded="
                + Math.round(relativeOutputChange / relativeInputChange));

        double p = 1.0 + 0x1.0p-20;
        double q = p + 0x1.0p-40;
        double fP = 1.0 / (p - 1.0);
        double fQ = 1.0 / (q - 1.0);
        System.out.println("nearPoleOriginal=" + fP);
        System.out.println("nearPoleChanged=" + fQ);
        System.out.println("nearPoleOutputChanged=" + (fP != fQ));

        double large = 1.0e16;
        double direct = Math.sqrt(large + 1.0) - Math.sqrt(large);
        double reformulated =
                1.0 / (Math.sqrt(large + 1.0) + Math.sqrt(large));
        System.out.println("directCancellation=" + direct);
        System.out.println("stableReformulation=" + reformulated);

        double a = 1.0e200;
        System.out.println("naiveHypotenuseInfinite="
                + Double.isInfinite(Math.sqrt(a * a + a * a)));
        System.out.println("hypotFinite=" + Double.isFinite(Math.hypot(a, a)));

        double threshold = 0x1.0p53;
        System.out.println("inputIncrementLost=" + (threshold + 1.0 == threshold));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 ConditionSensitivityDemo.java
java ConditionSensitivityDemo
```

Exact stdout output:

```text
gapHex=0x1.0p-40
changedGapHex=0x1.004p-40
absoluteInputChange=8.881784197001252E-16
absoluteOutputChange=8.881784197001252E-16
relativeOutputChange=9.765625E-4
relativeAmplificationRounded=1099511627777
nearPoleOriginal=1048576.0
nearPoleChanged=1048575.0000009537
nearPoleOutputChanged=true
directCancellation=0.0
stableReformulation=5.0E-9
naiveHypotenuseInfinite=true
hypotFinite=true
inputIncrementLost=true
```

These lines verify three groups of concepts:

1. **Relative sensitivity of subtraction:** `absoluteInputChange` and `absoluteOutputChange` are equal, yet `relativeOutputChange` is nearly `0.001`, and `relativeAmplificationRounded` exceeds `10^12`. This is a sensitive problem even though subtraction on the representable values is exact.
2. **Function near a singularity:** `nearPoleOriginal` and `nearPoleChanged` differ after a tiny perturbation in `x`.
3. **Stable vs. unstable algorithm:** `directCancellation=0.0` vs. `stableReformulation=5.0E-9`; `naiveHypotenuseInfinite=true` while `hypotFinite=true`.

The line `inputIncrementLost=true` demonstrates an additional fact: at `2^53`, `double` can no longer represent every consecutive integer, so `2^53 + 1.0` rounds to `2^53`. If a difference **was already lost when forming the input data**, downstream algorithms have no way to deduce it accurately from that `double` value.

## 10. Representation Precision Differs from Problem Conditioning

`float` has about 24 effective significand bits and `double` has about 53 bits; all operations are represented on a finite grid of values with magnitude-dependent spacing. `Math.ulp(x)` reports the representation step associated with `x`, while `Math.nextUp(x)` and `Math.nextDown(x)` let you inspect adjacent values.

Example:

```java
double limit = 0x1.0p53; // 2^53.
boolean lost = (limit + 1.0 == limit); // true.
double step = Math.ulp(limit);        // 2.0.
```

Measured/converted data can be rounded when creating a `double`, making `x̃` differ from the ideal value `x`. **Conditioning** describes the impact of that discrepancy on the mathematical answer, whereas **ULP and floating-point rules** describe a common source of computer discrepancy.

If a problem near a singularity has a very large `κ_rel`, an input relative error of just a few ULPs can still alter the output significantly. However, looking at ULP alone is not enough to judge data quality: sensor errors, missing data, modeling errors, or data-entry mistakes are often orders of magnitude larger than machine rounding error.

## 11. Choose Scale and Units Before Labeling a Problem "Sensitive"

Relative conditioning can change depending on the choice of input or scale. For example, `f(x)=x-1` near `x=1` is very sensitive in terms of **output relative error** because `f(x)` is near zero. Yet **absolute** sensitivity `|f'(x)|=1` is not large: whatever the input increases by, the output increases by the same amount.

If business logic cares about **absolute error not exceeding `10^-9`**, a small output being off by 50% proportionally does not necessarily have consequences. Conversely, if the system uses **growth rates**, high relative sensitivity can be a serious problem.

When measuring perturbations, determine:

- Which inputs vary: one parameter, several parameters, or all?
- Which norm is used for the input vector (e.g., infinity norm `L∞` or Euclidean `L2`)?
- Is the perturbation absolute, relative, or described by a confidence interval from measurement data?
- Does the output require **significant digits**, absolute error, relative error, or a business bound?
- Are there points `f(x)=0`, `x=0`, singularities, or discontinuities that render the relative formula meaningless?

For multivariable problems, the **Jacobian** is the generalized version of the derivative; sensitivity depends on perturbation direction and chosen norm. In a linear system `Ax=b`, the matrix condition number `κ(A)` measures solution sensitivity to data perturbations under a specific norm. Do not apply the single-variable formula `|x f'/f|` verbatim to multidimensional equation systems.

## 12. Connecting Conditioning to Real-World Data Problems

**Scenario A — difference between two large measurements.** For example, measuring two masses near `1000 kg` and subtracting to find a `0.001 kg` difference. If each measurement has an uncertainty of `±0.01 kg`, the uncertainty of the difference can exceed the target result itself. Using `BigDecimal` to subtract recorded decimals accurately **cannot recover the original measurement precision**. You need better sensors/measurement procedures or to measure the differential quantity directly.

**Scenario B — dividing by a near-zero offset.** For example, computing an index `1/(p - p0)` when `p` is near `p0`. A tiny sensor error in `p` makes the index swing wildly. You must define a valid domain, enforce a distance threshold from `p0`, compute the output interval corresponding to input uncertainty, or change the model if near-singularity values have no business meaning.

**Scenario C — large geometric calculations.** Side lengths of `1e200` can still yield a finite diagonal, yet a formula using `a*a+b*b` in `double` overflows. `Math.hypot(a,b)` handles this better without needing to assume original data must be less accurate.

**Scenario D — computing the difference of two large square roots.** Direct `sqrt(x+1)-sqrt(x)` can return 0 even though the answer is positive. Transforming to `1/(sqrt(x+1)+sqrt(x))` fixes the **algorithm**, rather than reducing the inherent sensitivity of the function.

## 13. How to Test Sensitivity Systematically in Java

To evaluate a numerical function in an application, combine:

1. **Identify domains and difficult points:** near-zero denominators, square roots near boundaries, differences of close quantities, data spanning orders of magnitude, extreme conditions.
2. **Estimate condition numbers** when a derivative or mathematical model is available; distinguish absolute/relative and avoid dividing by zero.
3. **Create controlled perturbations** for inputs. You can use `Math.nextUp(x)`/`Math.nextDown(x)` to shift by one representation step, or perturb according to realistic measurement error.
4. **Compare two error sources:** run the algorithm on slightly perturbed inputs, then compare against a higher-precision reference method or analytical formula when feasible.
5. **Test additional boundary values:** near zero, Infinity, NaN, subnormal, very large values, `Double.MAX_VALUE`, and input regions causing cancellation.
6. **Test properties:** monotonicity if the model must be monotonic, non-negativity if quantities are non-negative, physical bounds, and backward-checking from solution to data.
7. **State the desired error scale clearly** in tests, instead of demanding that `double` match an ideal decimal answer bit-for-bit in every scenario.

Some calculations can use `BigDecimal` with a sufficiently precise `MathContext` to generate reference values, but **`BigDecimal` does not natively support all mathematical functions**, and it does not solve ill-conditioned models on its own. For expressions requiring transcendental functions, references may require high-precision arithmetic libraries or verified analytical transformations.

## 14. Forward/Backward Error: Properly Interpreting a Discrepancy

Suppose the ideal model has `f(x)`, the machine-stored input is `x̃`, and the machine result is `ŷ`. Analysis should ask each question:

| Question | What is it about? |
| --- | --- |
| How much does `x̃` differ from `x`? | Data/representation error |
| How much does `f(x̃)` differ from `f(x)`? | **Problem** sensitivity |
| How much does `ŷ` differ from `f(x̃)`? | **Algorithmic** error at the stored input |
| Does `ŷ` equal `f(x+Δx)` for a small `Δx`? | **Backward error** perspective |
| Does the whole system meet accuracy requirements? | Combination of model, data, algorithm, and conditioning |

In the `a = 1 + 2^-40` example, subtracting nearby numbers **is not the main culprit**: both original and perturbed values can be stored and subtracted accurately. Relative amplification is an inherent property of taking **a tiny difference between two values of size ~1**.

Conversely, in the `sqrt(x+1)-sqrt(x)` example, choosing the direct formula causes loss of significant digits when intermediates are rounded. Switching to the reciprocal form reduces computational error; that is an algorithmic improvement, not a redefinition of the mathematical answer.

## 15. Common Misconceptions

| Misconception | Why it is wrong | Correct approach |
| --- | --- | --- |
| A large output error must mean Java `double` implementation is buggy | The problem itself may have a huge condition number | Analyze mathematical sensitivity first |
| A stable algorithm will always give an answer close to `f(x)` | Input data `x̃` may already differ from `x`; problem is sensitive | Separate data error from algorithmic error |
| Subtracting two close numbers is always miscomputed by the CPU | For sufficiently close floating-point numbers, subtraction can be exact | Analyze input perturbation and algorithm separately |
| Large relative error implies large absolute error | Very small outputs easily have huge relative errors | Specify error criteria suited to the measurement domain |
| Upgrading from `float` to `double` always fixes ill-conditioning | Increasing precision does not change the mathematical function's nature | Analyze condition number and data quality |
| `BigDecimal` fixes sensor noise | It only increases control over representation/computation | Improve measurement or model if needed |
| `sqrt(a*a+b*b)` is safe whenever the final result is finite | Intermediate `a*a` can overflow | Use `Math.hypot(a,b)` |
| `sqrt(x+1)-sqrt(x)` is always safe because it is mathematically positive | The two square roots round to nearly equal numbers | Use a stable algebraic transformation |
| Single-variable condition number applies identically to multiple variables | Multivariable sensitivity depends on norms and perturbation direction | Examine the Jacobian and appropriate condition number |
| Comparing `double` with `==` suffices to verify correctness | Results are rounded and may be very close | Use designed error criteria and boundary tests |

## 16. Self-Check Questions

1. **What is conditioning?** The sensitivity of the mathematical answer to small changes in input, at a given point/domain and under a chosen measurement norm.
2. **How does numerical stability differ from conditioning?** Stability concerns errors introduced by **the computation algorithm**, while conditioning concerns **the problem itself**.
3. **For `f(x)=x-1`, at `x` very close to 1, why does output relative error spike?** Because `f(x)` is tiny while absolute perturbation of `x` still passes into the difference; the relative condition number `|x/(x-1)|` is large.
4. **Does subtracting two close numbers necessarily round inaccurately?** No. It can be exact on the two stored numbers, yet the result is highly sensitive to **input relative error**.
5. **For `f(x)=1/(x-1)`, what happens when `x` is near 1?** Both the derivative and relative condition number can be huge; a small error in `x` can cause `f(x)` to change sharply.
6. **Why can `sqrt(1e16 + 1) - sqrt(1e16)` equal zero in `double`?** Because intermediate values round to identical numbers; the direct formula suffers cancellation.
7. **What is a more stable transformation of `sqrt(x+1)-sqrt(x)` for `x≥0`?** `1/(sqrt(x+1)+sqrt(x))`.
8. **Why can `Math.hypot(1e200,1e200)` be finite while `Math.sqrt(a*a+a*a)` is Infinity?** `a*a` overflows before taking the square root; `Math.hypot` avoids that unnecessary intermediate.
9. **If a measurement has large physical error, does switching from `double` to `BigDecimal` recover the exact value?** No. Representation precision cannot recover information that does not exist in the measurement.
10. **When should absolute error be used instead of relative error?** When the output can be zero/near zero or business rules specify a concrete absolute tolerance.

**Takeaway:** input error can be **amplified by problem conditioning**, even when the algorithm is completely exact on stored values. Measure both **absolute and relative error**, analyze condition numbers near sensitive points, separate data errors from algorithmic errors, and choose numerically stable formulas (`Math.hypot`, cancellation-avoiding transformations, domain checks) and precision appropriate to requirements.
