# Absolute, Relative, and Multi-Step Accumulated Error in Java

## 1. Objectives and Context

Computation results in Java can differ from ideal mathematical values due to finite number representation, rounding at each operation, execution order of operations, and inherent errors in input data. With `float` and `double`, tiny discrepancies can accumulate across thousands or millions of steps.

This lesson focuses on three questions:

1. **Absolute error**: by how many units does the computed result deviate from the reference value?
2. **Relative error**: how large or small is that deviation compared to the magnitude of the reference value?
3. **Accumulated error**: when performing many additions, subtractions, multiplications, divisions, or iterative steps, how does error propagate and grow, and how can we mitigate the risk?

We will use Java 17+, `double`, `BigDecimal`, `Math.ulp`, Kahan compensated summation, and scenarios involving loss of significant digits. There is no single fixed error threshold suitable for every business domain.

## 2. Reference Value, Approximate Value, and Error Sources

Notation:

- \(x\): the true value (or the accepted reference value in the problem).
- \(\hat{x}\): the approximate result computed by the program or measured.
- \(\hat{x}-x\): **signed error**; indicates whether the result is higher or lower than the reference.
- \(|\hat{x}-x|\): **error magnitude**; independent of sign.

Distinguish between:

| Error source | Example | Meaning |
| --- | --- | --- |
| Input data error | A sensor records 9.98 m instead of 10 m | The input is already not strictly exact |
| Representation error | `0.1` has no finite binary representation | Floating-point data is rounded immediately upon storage |
| Operation roundoff error | Adding two `double`s and storing the result in a `double` | The exact result may lie between two representable values |
| Algorithmic truncation error | Taking the first 5 terms of an infinite series | Approximation due to the mathematical method, even with ideal real numbers |
| Accumulated/propagated error | Adding many small values to a large sum | Step-by-step errors can alter the final result |

Representation error and operation roundoff error are commonly referred to together as **floating-point rounding error**. Truncation error stems from the algorithm and must be analyzed separately. For measurement problems, the "true" value may be unknown; in that case, one can only speak of error relative to a trustworthy reference, an uncertainty interval, or a proven error bound.

## 3. Absolute Error

**Definition**:

\[
E_{\mathrm{abs}} = |\hat{x} - x|
\]

Absolute error has the **same unit of measurement** as the original quantity. If a true length is 100 m and the program returns 99 m, then \(E_{\mathrm{abs}}=1\) m.

~~~java
double reference = 100.0;
double approximate = 99.0;
double absoluteError = Math.abs(approximate - reference);

System.out.println(absoluteError); // 1.0
~~~

This is an illustrative snippet placed inside a method.

**Advantage:** easy to interpret in business units. A deviation of 0.5°C, 1 mm, or 2 currency units carries direct meaning depending on the context.

**Limitation:** the same absolute error is not necessarily equally significant. A 1 m deviation on a 100 m road segment is vastly different from a 1 m deviation when measuring a 1,000,000 m length. To compare across scales, relative error is needed.

### Caution When Computing the Difference of Two doubles

The expression `Math.abs(approximate - reference)` is a common way to compute this, yet it still uses `double` arithmetic. If two extremely large finite numbers have opposite signs, subtraction can **overflow** to `Infinity`; for extremely small deviations, the difference may already be rounded to 0 before we measure it. Thus, error computed using `double` also has precision and representation range limits.

If exact decimal error is required and the input data is inherently decimal, keep it in `BigDecimal` from the start.

## 4. Relative Error

When \(x \ne 0\), relative error is defined as:

\[
E_{\mathrm{rel}} = \frac{|\hat{x}-x|}{|x|}
\]

It is a dimensionless ratio. Multiply by 100 to convert to percentage:

\[
E_{\%} = 100E_{\mathrm{rel}}\%
\]

For example, \(\hat{x}=99,\ x=100\):

\[
E_{\mathrm{abs}}=1,\qquad E_{\mathrm{rel}}=0.01,\qquad E_{\%}=1\%.
\]

~~~java
double reference = 100.0;
double approximate = 99.0;

double absError = Math.abs(approximate - reference);
double relativeError = absError / Math.abs(reference);
double percentError = relativeError * 100.0;

System.out.println(absError);      // 1.0
System.out.println(relativeError); // 0.01
System.out.println(percentError);  // 1.0
~~~

### When the Reference Value Is Equal to or Very Close to 0

If \(x=0\), the relative error formula is **undefined**, because the denominator is 0. You should not report `Infinity`, `NaN`, or arbitrarily assign 0% without explanation. When the expected result is 0, you can use **absolute error** against a suitable threshold.

If \(x\) is very close to 0 but nonzero, even a tiny absolute error can produce a huge relative error:

| True value | Result | Absolute error | Relative error |
| --- | --- | --- | --- |
| 100 | 99 | 1 | 1% |
| 1 | 0.99 | 0.01 | 1% |
| 0.000001 | 0.000002 | 0.000001 | 100% |
| 0 | 0.000001 | 0.000001 | Undefined |

The third row shows that a tiny unit-level difference can represent a **100% deviation** from the target value.

### Relative Error vs. Relative Difference

True relative error requires a reference value \(x\). If you only have two approximate results `a` and `b`, you can compute **relative difference** using an application-defined denominator, such as \(\max(|a|,|b|)\), but you must not implicitly call it error relative to an unknown "true value."

## 5. Why Do Floating-Point Numbers Have Error?

Java `float` uses IEEE 754 binary32 and `double` uses binary64. A decimal number such as 0.1 has an infinite binary pattern, so it is stored as the nearest binary value representable by the data type.

~~~java
double value = 0.1 + 0.2;
System.out.println(value); // 0.30000000000000004
~~~

In ideal decimal arithmetic, \(0.1+0.2=0.3\); in binary64, both operands are already rounded before addition, and the addition itself also rounds. The printed value shows the observable difference between the two binary64 results.

**Note:** the number `0.30000000000000004` does not prove that Java performs addition arbitrarily. It is the result of deterministic rounding rules. Bugs happen when we expect binary operations to behave like exact decimal arithmetic.

### ULP, Machine Epsilon, and Unit Roundoff

- `Math.ulp(x)` returns the size of one **unit in the last place** at the value `x`, according to the Java API rules.
- `Math.ulp(1.0)` equals \(2^{-52}\approx 2.220446049250313\times10^{-16}\): the distance between 1.0 and the next larger `double`.
- With binary64 round-to-nearest, *unit roundoff* is usually denoted \(u=2^{-53}\approx1.1102230246251565\times10^{-16}\). In many references, the term "machine epsilon" is used for \(2^{-52}\) or sometimes for \(u\); always check the source's **definition** before comparing numbers.

~~~java
System.out.println(Math.ulp(1.0)); // 2.220446049250313E-16
System.out.println(1.0 + Math.ulp(1.0) > 1.0); // true
~~~

**ULP is not a constant across all magnitudes.** The spacing between adjacent `double` numbers changes with the exponent. At large values, one ULP step can be greater than 1; near 0, there are subnormal numbers with a minimum step of `Double.MIN_VALUE`.

## 6. Accumulated Error Through Repeated Addition

A simple example is adding `0.1` ten times:

~~~java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}
System.out.println(total); // 0.9999999999999999
~~~

The expected result in exact decimal arithmetic is 1.0. After each addition, Java stores a rounded `double` value. The error from previous steps becomes input data for the next step.

A multiplication is represented differently:

~~~java
System.out.println(0.1 * 10.0); // 1.0
~~~

In this case, the product rounds to exact `1.0`. Do not conclude that "multiplication is always more accurate than addition": two different sequences of operations lead to different roundings, and the opposite can happen with other data.

### Does Error Always Increase at Every Step?

No. Signed errors can accumulate, cancel out, or change direction; not every step makes the absolute error larger. However, over many operations, the **upper bound on error** typically grows and the result can become sensitive to calculation order.

This means two ways of aggregating the same set of real numbers can yield slightly different results, especially when the data spans many orders of magnitude.

## 7. Loss of Significant Digits (Catastrophic Cancellation)

Adding a very large number and a very small number can completely wipe out the small part:

~~~java
double large = 1e16;
System.out.println(large + 1.0 == large); // true
System.out.println(Math.ulp(large));       // 2.0
~~~

Because the spacing between adjacent binary64 numbers at \(10^{16}\) is 2, adding 1 falls on the rounding tie boundary and the result rounds back to `large`. If we then subtract `large`, we get:

~~~java
double lost = (1e16 + 1.0) - 1e16;
double kept = (1e16 - 1e16) + 1.0;

System.out.println(lost); // 0.0
System.out.println(kept); // 1.0
~~~

In real arithmetic, both results are 1.0. In binary64, the intermediate result lost the 1, so subtraction cannot recover it.

**Cancellation** also occurs when subtracting two nearly equal numbers. The subtraction itself between two floating-point numbers may be rounded very well or even be exact, but the **relative error of the input data** is magnified when the true result of the subtraction is very close to 0. Therefore, you must examine the precision of both the inputs and the operations, rather than always blaming the final subtraction.

### Associativity Is No Longer Guaranteed

Mathematically, \((a+b)+c=a+(b+c)\). In floating point, rounding order differs, so addition is **not strictly associative**. Summation order, parallel multiplication, and how partial results are merged can affect the low-order bits of the result.

## 8. Estimating Error Across Many Computation Steps

Suppose we add \(n\) numbers in `double` using the standard relative rounding model:

\[
\operatorname{fl}(a+b) = (a+b)(1+\delta), \qquad |\delta|\le u
\]

with \(u=2^{-53}\) for binary64 round-to-nearest, when the operations lie in the domain where this model holds (without overflow or underflow issues that invalidate the model).

A commonly used bound in sequential summation analysis is:

\[
|\widehat{S}-S|\ \le\ \gamma_{n-1}\sum_{i=1}^{n}|x_i|,
\quad
\gamma_k=\frac{ku}{1-ku},
\quad ku<1,
\]

where \(S=\sum_i x_i\) is the exact sum of **the real numbers passed into the addition**, and \(\widehat{S}\) is the sum computed with rounding at each step. This is a theoretical bound under the stated assumptions; it **does not include errors from initially converting decimal or measured data into binary64**.

There are three points to understand:

1. When \(nu\) is small, \(\gamma_{n-1}\) is approximately \((n-1)u\); more additions can yield a larger error bound.
2. The bound contains \(\sum |x_i|\). If positive and negative numbers nearly cancel out, the true sum \(S\) can be small, so the **relative error of the sum** can be huge even while the absolute error remains small.
3. This is a **worst-case bound under the model**, not a promise that actual error equals \((n-1)u\) or grows steadily. Rounding errors can cancel out; in some random models, the actual error growth rate is smaller than the worst-case bound.

When a calculation has only a few steps, it is usually checked using boundary data and a sufficiently accurate reference solution. When the step count is large, beyond testing, one should choose stable algorithms and analyze the value range.

## 9. Kahan Compensated Summation to Reduce Loss During Accumulation

**Kahan compensated summation** keeps an extra small correction variable to compensate for the low-order bits lost when adding a small number to the running sum.

~~~java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double correction = 0.0;

    for (double value : values) {
        double adjusted = value - correction;
        double next = sum + adjusted;
        correction = (next - sum) - adjusted;
        sum = next;
    }
    return sum;
}
~~~

This is a **standalone class-level method** that can be placed inside a Java class and called from `main`. The algorithm uses ordinary floating-point operations and is beneficial for many long summation sequences.

Example usage:

~~~java
double[] tenths = new double[10];
java.util.Arrays.fill(tenths, 0.1);
System.out.println(kahanSum(tenths)); // 1.0
~~~

In this example, Kahan returns `1.0`, improving upon ordinary sequential addition's `0.9999999999999999`.

**Limitations:** Kahan does not turn all addition into exact real arithmetic; the result still depends on input representation, operation order, overflow, underflow, and sequence properties. Nor does it recover measurement errors or digits already lost **before** elements were put into the array.

Other approaches to consider include **pairwise summation** (summing in a balanced tree), sorting the sequence by magnitude when appropriate, using numerically stable algorithms, or increasing representation precision.

## 10. Complete Java 17+ Program

Save the code as `ErrorMetricsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;

public class ErrorMetricsDemo {
    static double absoluteError(double approximate, double reference) {
        return Math.abs(approximate - reference);
    }

    static double relativeError(double approximate, double reference) {
        if (reference == 0.0) {
            throw new IllegalArgumentException("Reference must not be zero");
        }
        return absoluteError(approximate, reference) / Math.abs(reference);
    }

    static double naiveSum(double[] values) {
        double sum = 0.0;
        for (double value : values) {
            sum += value;
        }
        return sum;
    }

    static double kahanSum(double[] values) {
        double sum = 0.0;
        double correction = 0.0;
        for (double value : values) {
            double adjusted = value - correction;
            double next = sum + adjusted;
            correction = (next - sum) - adjusted;
            sum = next;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("absolute=" + absoluteError(99.0, 100.0));
        System.out.println("relative=" + relativeError(99.0, 100.0));

        double[] values = new double[10];
        Arrays.fill(values, 0.1);
        System.out.println("naive=" + naiveSum(values));
        System.out.println("kahan=" + kahanSum(values));
        System.out.println("product=" + (0.1 * 10.0));

        System.out.println("ulp(1)=" + Math.ulp(1.0));
        System.out.println("ulp(1e16)=" + Math.ulp(1e16));

        double lost = (1e16 + 1.0) - 1e16;
        double kept = (1e16 - 1e16) + 1.0;
        System.out.println("lost=" + lost);
        System.out.println("kept=" + kept);

        BigDecimal decimalSum = BigDecimal.ZERO;
        for (int i = 0; i < 10; i++) {
            decimalSum = decimalSum.add(new BigDecimal("0.1"));
        }
        System.out.println("decimal=" + decimalSum);
    }
}
~~~

Compile and run commands:

~~~bash
javac --release 17 ErrorMetricsDemo.java
java ErrorMetricsDemo
~~~

Stdout output:

~~~text
absolute=1.0
relative=0.01
naive=0.9999999999999999
kahan=1.0
product=1.0
ulp(1)=2.220446049250313E-16
ulp(1e16)=2.0
lost=0.0
kept=1.0
decimal=1.0
~~~

Explanation:

- The absolute error between 99 and 100 is 1, and the relative error is 0.01 = 1%.
- Sequentially adding `0.1` ten times does not yield exact `1.0`; Kahan reduces rounding loss in this example.
- `Math.ulp` at \(10^{16}\) is 2, so adding 1 cannot increase the stored value in this case.
- Two ways of parenthesizing subtraction prove that calculation order can change the result.
- `BigDecimal("0.1")` preserves the exact **decimal value 0.1**, so adding it ten times produces the decimal string `1.0`.

## 11. Comparing Floating-Point Numbers with Tolerance

Use `a == b` only when business logic genuinely requires **identical binary floating-point values**. When two results are computed through different procedures, approximate comparison typically combines an **absolute threshold** and a **relative threshold**:

\[
|a-b|\ \le\ \text{absTol}+\text{relTol}\times\max(|a|,|b|).
\]

- `absTol` has the same unit as the quantity and is useful when both values are near 0.
- `relTol` is dimensionless, allowing the tolerance to scale appropriately for large values.
- Thresholds must derive from **problem requirements or error bounds**, not an arbitrarily copied "epsilon" constant.

An illustrative example for finite numbers whose difference and threshold product remain representable in `double`:

~~~java
static boolean nearlyEqual(double a, double b,
                           double absTol, double relTol) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(absTol) || !Double.isFinite(relTol)
            || absTol < 0.0 || relTol < 0.0) {
        return false;
    }

    double limit = absTol
            + relTol * Math.max(Math.abs(a), Math.abs(b));
    return Math.abs(a - b) <= limit;
}
~~~

This is an **illustrative method inside a class**, not a standalone program. For very large values, `Math.abs(a-b)` or `limit` can overflow to Infinity; for high-precision comparisons across the entire `double` range, a comparison algorithm designed to avoid overflow/underflow or switching to a suitable representation model is needed.

For example, `nearlyEqual(0.1 + 0.2, 0.3, 1e-12, 1e-9)` returns `true` for these small values. However, that does not prove all close numbers are equivalent in business logic. For money, identifiers, exact counts, or safety conditions, tolerance may be inappropriate.

### What Should Error Testing Compare Against?

If no exact mathematical solution exists, you can use:

- Datasets with independently derived and trustworthy answers.
- Reference calculations using `BigDecimal` or high-precision numerical software when the mathematical model is compatible.
- Checking invariants and result bounds of the algorithm.
- Testing multiple summation orders, very large/small data, near-canceling numbers, and cases close to 0.

`BigDecimal` does not automatically solve algorithmic truncation error or measurement errors in the input. If constructed with `new BigDecimal(0.1)`, it holds **the approximated binary64 value**, which differs from `new BigDecimal("0.1")`.

## 12. Scenarios Where Accumulated Error Becomes a Major Problem

### 12.1. Summing Values of Vastly Different Magnitudes

For example, the sequence `[1e16, 1, 1, -1e16]` has an exact sum of 2. Yet naive sequential addition can lose both 1s and return 0. Purposeful sorting/grouping or compensated summation can improve some cases, but must be evaluated against the actual sequence characteristics.

### 12.2. Time-Step Accumulation Loops

Measuring time via `time += delta` over very many steps can cause the final value to differ from `steps * delta` due to accumulated error. If `delta` is fixed, it can be computed from an integer step index: `time = stepIndex * delta` when appropriate, avoiding a long accumulation chain. Multiplication still rounds, so the result must be checked against acceptable error.

### 12.3. Multi-Step Products and Quotients

Multiplication/division errors can accumulate as a relative factor. Products of many large/small numbers can overflow or underflow before reaching the desired result. For problems like very small probabilities, logarithmic space or normalization algorithms can be used to prevent intermediate values from leaving the representable range.

### 12.4. Error Propagation in Iterative Algorithms

An algorithm such as position updating `position += velocity * dt` accumulates error from input data, multiplication, addition, and step count. If the algorithm is also **sensitive to initial conditions**, small errors can grow rapidly over time. In such cases, merely using `double` is unlikely to suffice; one must analyze the model, step size, stability conditions, and stopping rules.

## 13. Forward Error, Backward Error, and Problem Conditioning

Three concepts enable deeper analysis:

- **Forward error:** the deviation between the computed result \(\hat{y}\) and the ideal result \(f(x)\) for the *same exact input* \(x\).
- **Backward error:** determining whether \(\hat{y}\) can be interpreted as the exact result \(f(x+\Delta x)\) of a slightly perturbed input.
- **Conditioning:** how sensitive the problem itself is to small input changes. This is a property of the problem, distinct from the stability of the algorithm's implementation.

An algorithm is called **backward stable** under appropriate analysis conditions when its result is equivalent to the exact solution for an input close to the original input. However, if the problem is *ill-conditioned*, small input errors can still cause huge changes in the output. Thus, a "stable algorithm" does not mean "output relative error is always small."

For instance, when subtracting two nearly equal numbers, the true result is much smaller than either operand. The relative error of the two input numbers can be amplified in their difference. Understanding problem conditioning avoids the unrealistic expectation that simply replacing `float` with `double` will preserve all significant digits.

## 14. Error-Reduction Measures and Data Type Selection

| Measure | Suitable when | Notes |
| --- | --- | --- |
| `double` instead of `float` | More precision and numeric range are needed | `double` still rounds |
| Kahan compensated or pairwise summation | Summing many floating-point numbers | Measure effectiveness on representative datasets |
| Reordering or transforming to a stable formula | Risk of digit loss/cancellation | Must preserve mathematical meaning and handle edge cases |
| `Math.fma(a, b, c)` | Computing \(a\times b+c\) needing a single rounding | Does not solve all errors or input data loss |
| `Math.hypot(x, y)` | Computing \(\sqrt{x^2+y^2}\) | Reduces intermediate overflow/underflow |
| `BigDecimal` with decimal strings | Money and decimal calculations needing precision | Division may require `MathContext`/rounding rules |
| High-precision reference values | Testing algorithm error bounds | Choose independent references matching the mathematical domain |
| Absolute + relative tolerance | Comparing approximate calculation results | Define thresholds based on business requirements |

### When Exact Numbers Should Be Prioritized

For countable integers within `long` range, use `long` to avoid `double` rounding error. For integers exceeding 64 bits, use `BigInteger`. For monetary amounts requiring decimal exactness, use `BigDecimal` or integer smallest currency units per business rules.

Adding more digits after the decimal point in a text representation **does not increase the precision** of an already computed `double` value.

## 15. Common Pitfalls

1. **Comparing `double` with `==` in all situations.** When calculations involve rounding, approximate comparison requires thresholds and problem context.
2. **Using `Double.MIN_VALUE` as epsilon.** This is the smallest positive subnormal number, not a typical relative error or resolution around 1.0.
3. **Treating `Math.ulp(1.0)` as the error bound for every number.** ULP depends on the magnitude of the number under consideration and the computation model.
4. **Computing relative error when the reference is 0.** The formula is undefined; an appropriate metric is needed.
5. **Assuming error always increases monotonically after every operation.** Errors can add up or cancel out; only error bounds and algorithm properties give reliable predictions.
6. **Believing `BigDecimal.valueOf(double)` or `new BigDecimal(double)` recovers lost measurement/string precision.** They construct from an already rounded `double`; to preserve exact textual decimal numbers, parse directly from strings.
7. **Testing only easy data like small integers.** You must test near 0, differences of nearly equal numbers, differing scales, long sums, boundary values, and different grouping orders.
8. **Reading the output printed by `System.out.println` as the complete true error.** `Double.toString` formatting and round-trip behavior do not provide a proof of an algorithm's error bound.
9. **Ignoring `NaN` and `Infinity`.** Special values can render comparisons/thresholds meaningless; input and output validation policies are required.

## 16. Self-Check Questions

**Question 1.** For a result of 198 compared to a reference of 200, what are the absolute, relative, and percentage errors?

Answer: \(E_{\mathrm{abs}}=2\), \(E_{\mathrm{rel}}=2/200=0.01\), which is **1%**.

**Question 2.** If the reference value is 0, why can't we say the relative error is 0%?

Answer: Because the denominator in \(|\hat{x}-x|/|x|\) is 0; the formula is undefined. Absolute error or a clearly defined alternative metric can be used.

**Question 3.** Why can adding `0.1` ten times differ from multiplying `10 * 0.1`?

Answer: The two expressions have different numbers and sequences of roundings. Repeated additions can accumulate error; multiplication has only one arithmetic operation after the operands are represented.

**Question 4.** Why can `(1e16 + 1.0) - 1e16` equal 0 while `(1e16 - 1e16) + 1.0` equals 1?

Answer: `1e16 + 1` does not increase the binary64 value at this magnitude, so the final subtraction loses information. Subtracting first preserves the 1.

**Question 5.** Does Kahan always produce a sum as exact as `BigDecimal`?

Answer: No. Kahan reduces some rounding error in floating-point summation, but still uses `double` and does not replace exact decimal arithmetic or solve every case.

**Question 6.** If the absolute error between two solutions is small while the relative error is huge, what should usually be checked?

Answer: The reference value may be very close to 0; check the scale, error criteria, possibility of cancellation, and problem sensitivity.

## 17. Key Takeaways and References

- **Absolute error:** \(E_{\mathrm{abs}}=|\hat{x}-x|\), in the same unit as the quantity.
- **Relative error:** \(E_{\mathrm{rel}}=E_{\mathrm{abs}}/|x|\) when \(x\ne0\), suitable for comparing across scales; exercise caution near 0.
- **Accumulated error:** each rounding can affect subsequent steps; operation order and problem conditioning determine result reliability.
- **Reducing error:** choose stable algorithms, Kahan/pairwise summation for long sums, `Math.fma`/numerically stable formulas when appropriate, test with trustworthy references, and define tolerances by business requirements.
- **Type selection:** `double` fits many approximate numerical problems; `BigDecimal`/integers fit when exact decimal or count results are required.

Official references:

- [Java Language Specification 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3).
- [Java SE 17 API — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `ulp`, `fma`, `hypot`.
- [Java SE 17 API — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): binary64 limits and representation.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact decimal numbers and rounding control.
