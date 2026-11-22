# Representation Error vs. Algorithmic Error in Java

> **Java core – numbers · Error and stability**  
> **Objective:** Distinguish between error caused by storing numbers in `float`/`double` and error caused by how calculations or algorithms are constructed; explain why using `double` does not guarantee a correct result, and know how to measure, reduce, and test numerical error systematically.

## 1. The Same Discrepancy Can Have Completely Different Causes

Suppose a mathematical problem has the true result `T`, while a Java program returns `R`. The fact that `R ≠ T` is **not sufficient to conclude** "because computers cannot store real numbers accurately."

There are at least three distinct sources:

1. **Representation error:** an input value or mathematical constant cannot be represented accurately with the bits of the type being used, such as the `double` literal `0.1`.
2. **Operation roundoff error:** the result of addition, subtraction, multiplication, division, or a mathematical function is rounded to a finite format. It is related to floating-point arithmetic, but it can arise **after** the inputs have already been represented accurately.
3. **Algorithmic error:** the chosen computation method causes loss of information, amplifies error, stops an approximation too early, or uses a numerically unstable formula. Even when data is stored well, an algorithm can still yield poor results.

The two groups commonly contrasted in this topic are **representation error** and **algorithmic error**; roundoff error in operations is the crucial link connecting them. It is important to distinguish **problem/approximation error** (such as taking only a few terms of a Taylor series) from **implementation instability** (such as subtracting two nearly equal numbers).

| Issue | Where does it arise? | Symptom | Typical remedy |
| --- | --- | --- | --- |
| Representation | A mathematical number has no exact bit pattern in the type | `0.1 + 0.2` does not have the exact bits of `0.3` | Choose an appropriate format/type, `BigDecimal` for exact decimal |
| Step-by-step rounding | An operation's result falls between representable numbers | Adding 1 to `1e16` does not change the `double` value | Analyze ULP, grouping, magnitude, and intermediate error |
| Unstable algorithm | Formula/computation scheme amplifies error | `sqrt(x*x+1)-x` returns 0 even though the answer is positive | Rewrite into a more stable equivalent formula |
| Approximation error | Algorithm intentionally uses an approximation or stops early | Using `1+x` instead of `e^x` for large `x` | Increase approximation order, control stopping criteria |
| Input data | Measurement or rounding before reading into the program | Two data sources already differ before Java | Control measurement, input format, and data contracts |

**Key takeaway:** A numerical bug can be the combination of multiple error sources. Switching from `float` to `double` sometimes improves things significantly; however, if the computation formula is unstable or the problem is poorly approximated from the start, adding more bits will not necessarily solve the root cause.

## 2. What Is Representation Error?

Computers store a finite number of bits. `float` has 32 bits (24 bits of effective precision for normal numbers), and `double` has 64 bits (53 bits of effective precision for normal numbers). The set of numbers that can be stored accurately in them is **not the entire set of real numbers**.

In base 2, a number of the form `m / 2^k` can have a finite representation if it falls within the range and precision of the type. However, a decimal fraction like `1/10` has an infinite repeating binary representation:

```text
0.1 (decimal) = 0.000110011001100110011... (binary)
                                   ^ repeating
```

Therefore, the literal:

```java
double x = 0.1;
```

does not store the exact mathematical fraction `1/10`. Java selects the nearest `double` value according to the literal rounding rules.

```java
System.out.println(Double.toHexString(0.1));
// 0x1.999999999999ap-4
```

The hexadecimal floating-point form displays the actual binary number that was stored. This string accurately describes a `double` value close to 0.1, but it does **not** turn it into the exact decimal fraction 0.1.

A familiar manifestation:

```java
System.out.println(0.1 + 0.2);        // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

Here, there is already **input representation error** as well as addition/rounding. Printing a long string does not mean `System.out.println` itself computes incorrectly; it merely converts the stored binary value into a decimal string for display.

### When Numbers Can Be Represented Accurately

Not every decimal number suffers from representation error in binary:

```java
double a = 0.5;    // 1/2, exact representation
double b = 0.25;   // 1/4, exact representation
double c = 0.125;  // 1/8, exact representation

System.out.println(a + b + c); // 0.875
```

These examples are all sums of fractions whose denominators are powers of 2 and whose magnitudes fit within range. Conversely, sufficiently large integers can also lose information when converted to `double`, even if written entirely using decimal integer digits.

## 3. Representing Large Integers in double Also Has Limits

`double` has 53 bits of effective precision. It accurately represents every integer in the range from `−2^53` to `2^53`, but it cannot preserve **every** integer larger than that with a step size of 1.

```java
long original = 9_007_199_254_740_993L; // 2^53 + 1
double stored = original;

System.out.println((long) stored);
// 9007199254740992
```

The original `long` value is an exact integer, but converting it to `double` rounds it to `9_007_199_254_740_992`. If you later cast that `double` back to `long`, the lost digit **cannot be recovered**.

This is a clear example of **representation/data-conversion error**, requiring no complex algorithm at all. When storing IDs, currency in smallest integer units, or large counters, use an appropriate integer type (`long`, `BigInteger`) rather than going through `double`.

**Important rule:** Choose a data type based on **value range and precision requirements**, not just because `double` can represent very large numbers up to around `1.8×10^308`. A wide magnitude range does not imply a resolution of 1 across the entire range.

## 4. Operation Roundoff Error Differs from Input Error

Even when all operands are represented accurately, an **intermediate operation** can still produce a result that is not representable within the type's precision.

Example:

```java
double large = 1.0e16; // this integer is represented accurately by double
double one = 1.0;       // represented accurately

System.out.println(large + one == large); // true
System.out.println(Math.ulp(large));      // 2.0
```

`10^16` and 1 can each be represented accurately on their own. However, the spacing between adjacent `double` values around `10^16` is 2, so `10^16 + 1` lies between two representable values and is rounded to `10^16`.

Therefore, the claim "if the inputs are exact, the computed result is also exact" is **false** for floating-point numbers.

A counterexample involving addition order:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Both expressions have the same value in mathematical real numbers, but they differ because of **where rounding occurs**. This illustrates operation error and the impact of algorithm/grouping, not merely an error from typing the literal 0.1.

Floating-point operations are also subject to **exponent** limits: intermediate calculations can become `Infinity` (overflow) or get so close to 0 that they become `subnormal`/`0.0` (underflow). Choosing the order and form of a formula sometimes determines whether that happens.

## 5. What Is Algorithmic Error? Not Just "Buggy Code"

An algorithm is the **sequence of operations** chosen to find or approximate a solution. Algorithmic error can arise from different causes:

- Using a **mathematical approximation** instead of an exact function (for example, `e^x ≈ 1+x` when `x` is not sufficiently small).
- **Truncating a series or loop** before reaching the required tolerance.
- Choosing a **numerically unstable** formula that causes roundoff error or input error to be amplified.
- Using an **accumulation** strategy that causes small numbers to be absorbed into a large sum.
- Using an equation-solving or numerical differentiation scheme that is sensitive to step size, precision, or iteration count.

This is not necessarily a logic bug like "writing the wrong formula." Two formulas that are **strictly equivalent over the real numbers** can still have vastly different numerical quality when translated into a sequence of `double` operations.

### Distinguishing Truncation/Approximation Error from Floating-Point Rounding

An algorithm may deliberately take an approximation:

\[
e^x = 1+x+\frac{x^2}{2!}+\cdots
\]

If we use only the first two terms:

\[
e^x \approx 1+x
\]

then at `x = 1` the approximated value is **2**, whereas the mathematical value is about **2.718281828459045...**. This large discrepancy is primarily due to **dropping the series terms**, **not** because Java lacks bits to store the number 2.

```java
double firstOrder = 1.0 + 1.0;
double reference = Math.exp(1.0);

System.out.println(firstOrder); // 2.0
System.out.println(reference);  // 2.718281828459045
```

`Math.exp` still returns a rounded `double` value, not an infinite-digit number; nevertheless, this result is enough to show that the error of the two-term approximation is an **algorithmic** issue far larger than one ULP around 2.

## 6. A Mathematically Correct Formula with an Unstable Implementation

Consider the function:

\[
f(x)=\sqrt{x^2+1}-x,\qquad x>0.
\]

Over the real numbers, this expression is always **positive**. Yet if `x` is large enough, `x²+1` can round to `x²`, making the result close to 0 or equal to 0 in `double`.

Using `x = 100_000_000.0`:

```java
double x = 1.0e8;
double naive = Math.sqrt(x * x + 1.0) - x;

System.out.println(naive); // 0.0
```

Step-by-step explanation:

1. `x*x = 10^16` is representable.
2. When adding 1.0 to `10^16`, the `double` representation step around it has width 2.0, so `10^16+1` is rounded back to `10^16`.
3. `sqrt(10^16)` returns `10^8`.
4. Subtracting `x=10^8` yields `0.0`.

**Literal representation error is not the main culprit:** `x = 1e8` and 1.0 are both represented accurately. The problem lies in **how intermediate computations are structured**, causing the +1 term to be lost and then subtracting two nearly equal numbers.

### Transforming the Formula for Better Stability

Multiply both numerator and denominator by the conjugate expression:

\[
\sqrt{x^2+1}-x
=\frac{(\sqrt{x^2+1}-x)(\sqrt{x^2+1}+x)}
       {\sqrt{x^2+1}+x}
=\frac{1}{\sqrt{x^2+1}+x}.
\]

Applying this:

```java
double x = 1.0e8;
double stable = 1.0 / (Math.sqrt(x * x + 1.0) + x);
System.out.println(stable); // 5.0E-9
```

Although computing `sqrt(x*x+1)` still yields `x` for this dataset, dividing `1/(2*x)` preserves the **correct magnitude** of the tiny result: around `5×10^-9`, instead of 0.

The two formulas are **equal in real-number algebra** (for `x>0`), yet under `double` they behave completely differently in terms of stability.

**Limitations of this trick:** The transformed formula can still overflow if `x*x` exceeds the `double` range, or have issues in other input domains. For many large-magnitude problems, consider `Math.hypot(x, 1.0)` to compute `sqrt(x*x+1)` in a way that reduces overflow/underflow risks. Never assume a single conjugate transformation handles every input perfectly.

## 7. Logarithm Formula: log1p Avoids Losing x Near 0

In mathematics:

\[
\log(1+x)
\]

is a completely valid formula. However, when `x` is extremely small, adding `1+x` in `double` can immediately round to 1 before calling the logarithm.

```java
double x = 1.0e-16;

System.out.println(1.0 + x == 1.0); // true
System.out.println(Math.log(1.0 + x)); // 0.0
System.out.println(Math.log1p(x));     // 1.0E-16
```

Because `x` is smaller than half a ULP around 1.0, `1+x` is rounded to 1.0. Then `log(1.0)=0` is the accurate result for the **already-rounded** input value, not because `Math.log` itself "does not know logarithms."

`Math.log1p(x)` is designed to compute **log(1+x)** more accurately when `x` is near 0, avoiding forming the imprecise intermediate `1+x`. Similarly, `Math.expm1(x)` computes **exp(x)-1** with better accuracy when `x` is near 0 compared to writing `Math.exp(x)-1.0`.

This is an important example for distinguishing:

- **Input representation error:** `x=1e-16` is stored as a `double` value close to that decimal number.
- **Computation-method error:** the expression `1+x` loses the small change before applying `log`.
- **Solution:** choose a **specialized numerical function** to avoid intermediates with insufficient resolution.

## 8. Summing a Sequence: Different Algorithms Can Preserve or Lose Small Terms

Given the sequence:

```java
double[] values = {1.0e16, 1.0, -1.0e16};
```

The exact real-number sum is 1. Sequential summation:

```java
double sum = 0.0;
for (double value : values) {
    sum += value;
}
System.out.println(sum); // 0.0
```

After `sum=1e16`, adding 1.0 rounds back to `1e16`. Adding `-1e16` next gives 0.0. The +1 term is lost.

If you change the order to `{1e16, -1e16, 1.0}`, sequential summation gives 1.0. The difference arises from **where rounding occurs**, not because individual input terms cannot be represented.

### Neumaier Compensated Summation

One algorithm that reduces cumulative addition error is *Neumaier summation*, belonging to the **compensated summation** family. The algorithm maintains a compensation variable to record a portion of the discarded error:

```java
static double neumaierSum(double[] values) {
    double sum = 0.0;
    double correction = 0.0;

    for (double x : values) {
        double t = sum + x;
        if (Math.abs(sum) >= Math.abs(x)) {
            correction += (sum - t) + x;
        } else {
            correction += (x - t) + sum;
        }
        sum = t;
    }
    return sum + correction;
}
```

This is an **illustrative method** that must be placed inside a Java class. On the sequence above, it returns 1.0. However, the algorithm does not guarantee an infinite-digit exact result for every dataset, especially in the presence of overflow, NaN, infinity, or data outside its stability domain. The difference lies in the **accumulation algorithm**, even though the `double` type and input data remain the same.

For large summation problems, there is also **pairwise summation** (summing in a balanced tree) or specialized algorithms targeting bit-for-bit reproducibility. Accuracy and reproducibility requirements should be clearly defined before choosing how to parallelize a sum.

## 9. Input-Sensitive Problems: Condition Number Is Not Representation Error

Not every wildly fluctuating result is caused by a poor algorithm.

Suppose the problem requires computing:

\[
g(x)=\frac{1}{1-x}.
\]

When `x` approaches 1, even a tiny change in the input causes the result to change dramatically. For example, over the real numbers:

\[
g(0.99)=100,\qquad g(0.999)=1000.
\]

Two input values differ by only 0.009, yet the results differ by a factor of 10. This is the inherent **input sensitivity of the problem** (*conditioning*), not merely an artifact of the programming language.

Distinguish between:

- **Well-conditioned problem:** small changes in input generally cause only correspondingly small changes in output under the metric being considered.
- **Ill-conditioned problem:** small changes in input can produce large changes in output.
- **Numerically stable algorithm:** a computation method that does not amplify error unreasonably relative to the inherent sensitivity of the problem; a quantitative statement requires specifying the norm, domain, and type of stability (for example, *backward stability*).

A good algorithm cannot "defeat" all inherent sensitivity of the data. For instance, if the input contains measurement error from a sensor, switching to `BigDecimal` cannot magically recover physical information that was never measured accurately.

**Diagnostic principle:** before blaming `double` for every discrepancy, ask "given exact data, is the problem itself sensitive?" and "at which step is the algorithm introducing additional error?"

## 10. Measuring Error: Absolute, Relative, and ULP

Suppose we have a high-confidence reference result `T` and a computed result `R`.

### 10.1. Absolute Error

\[
E_{\mathrm{abs}} = |R-T|
\]

For example, expecting 100.0 and receiving 100.01 gives an absolute error of 0.01. It is measured in the **same unit** as the value (currency, meters, seconds, etc.), making it easy to relate to business logic.

### 10.2. Relative Error

When `T ≠ 0`:

\[
E_{\mathrm{rel}} = \frac{|R-T|}{|T|}
\]

Relative error is useful when data magnitudes span a wide range. However, near `T=0`, this expression can become very large or undefined; **do not use relative error alone** as a comparison criterion when the true baseline is zero or near zero.

### 10.3. ULP (Unit in the Last Place)

`Math.ulp(x)` expresses the size of one representation step around `x`. For example:

```java
System.out.println(Math.ulp(1.0));    // 2.220446049250313E-16
System.out.println(Math.ulp(1.0e16)); // 2.0
```

ULP helps explain why `double` "with high precision" still loses +1 when added to `1e16`. However, **a ULP bound** is only suitable when the problem requires evaluating error tied to `double` values; not every business error is well described by ULP.

### 10.4. When Is a Reference Trustworthy?

Do not treat another `double` computation as the "absolute answer" if it suffers from the same flaw. Better reference sources may include:

- analytical mathematical results or exact solutions for simple cases;
- exact integer/powers-of-10 arithmetic if the problem permits;
- `BigDecimal` initialized from strings with sufficient precision and a defined rounding mode;
- high-precision libraries, verified algorithms, or independent benchmark data.

For practical approximate computations, you should test across multiple magnitudes, especially regions **near 0**, **near boundaries**, **nearly equal data**, and **inputs that switch algorithmic branches**.

## 11. Does Choosing BigDecimal Fix All Errors?

**No.** `BigDecimal` helps represent and compute **exact decimal numbers according to the input format**, within appropriate computation and resource bounds. It is especially useful for money or decimal data where the last digit carries legal or business significance.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b)); // 0.3
```

This is exact decimal addition because both operands are created from **strings**.

However:

```java
BigDecimal fromDouble = new BigDecimal(0.1);
System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625
```

The constructor taking `double` interprets the **exact stored binary value**, so it cannot know that the user originally intended the fraction 1/10. If you have a `double` and want to create a `BigDecimal` from the decimal string produced by `Double.toString`, you can use `BigDecimal.valueOf(double)`; however, this is **a different conversion rule**, not a recovery of any lost precision.

Additionally, when using a `MathContext` that limits precision, `BigDecimal` also performs rounding; and when a formula is poorly approximated or an algorithm stops too early, changing types does not automatically make the algorithm exact.

Decision table:

| Scenario | Choice |
| --- | --- |
| Money in decimal digits, requiring deterministic rounding | `BigDecimal` from string/decimal input, specifying scale and rounding |
| Scientific computing needing speed, tolerating numerical error | `double` with a stable algorithm and testing |
| Need to preserve very large integers accurately | `BigInteger` |
| Need to compute `log(1+x)` when `x` is very small | `Math.log1p(x)` |
| Need long sums where cumulative error is significant | Compensated/pairwise summation suited to the data |
| Problem whose inputs are inherently imprecise | Evaluate source error, sensitivity, and uncertainty |
| Algorithm approximation is too coarse | Increase order/steps or change algorithm, not just the type |

## 12. Safe Numerical Testing Practices

A near-equality check function can combine absolute and relative tolerances while checking special values:

```java
static boolean nearlyEqual(double a, double b,
                           double absoluteTolerance,
                           double relativeTolerance) {
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(absoluteTolerance,
                                  relativeTolerance * scale);
}
```

This is an **illustrative method** that needs to reside inside a class. A production implementation must validate that both tolerances are **finite and non-negative**, and handle potential overflow when computing the difference or relative product if the data domain can be very large. No arbitrary threshold like `1e-9` fits every problem.

The comparison contract must be clarified:

- **Bitwise representation equality:** requires the exact same IEEE 754 pattern; to distinguish signed zeros or raw NaN bits, use the appropriate raw-bits API.
- **Ordinary arithmetic equality:** `+0.0 == -0.0` is `true`; `NaN == NaN` is `false`.
- **Business-level near equality:** based on measurement units, input magnitudes, error bounds, and acceptable safety margins.

**Do not use `Double.MIN_VALUE` as a general epsilon.** That is the smallest positive subnormal number, not a reasonable error threshold around arbitrary values.

## 13. Standalone Java 17+ Program

Create the file **`RepresentationVsAlgorithmErrorDemo.java`**:

```java
import java.math.BigDecimal;

public class RepresentationVsAlgorithmErrorDemo {
    private static double neumaierSum(double[] values) {
        double sum = 0.0;
        double correction = 0.0;

        for (double x : values) {
            double t = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - t) + x;
            } else {
                correction += (x - t) + sum;
            }
            sum = t;
        }
        return sum + correction;
    }

    public static void main(String[] args) {
        // Decimal representation in binary floating-point type.
        System.out.println("0.1 hex = " + Double.toHexString(0.1));
        System.out.println("0.1 + 0.2 = " + (0.1 + 0.2));
        BigDecimal exactDecimal =
                new BigDecimal("0.1").add(new BigDecimal("0.2"));
        System.out.println("decimal sum = " + exactDecimal);

        // Information loss when converting an overly large integer to double.
        long original = 9_007_199_254_740_993L;
        double rounded = original;
        System.out.println("long preserved = "
                + ((long) rounded == original));
        System.out.println("rounded long = " + (long) rounded);

        // Two mathematically equivalent formulas with different stability.
        double x = 1.0e8;
        double naive = Math.sqrt(x * x + 1.0) - x;
        double stable = 1.0 / (Math.sqrt(x * x + 1.0) + x);
        System.out.println("naive formula = " + naive);
        System.out.println("stable formula = " + stable);

        // Specialized function preserves accuracy near 0 better.
        double tiny = 1.0e-16;
        System.out.println("log(1+x) = " + Math.log(1.0 + tiny));
        System.out.println("log1p(x) = " + Math.log1p(tiny));

        // Accumulation using two different algorithms.
        double[] values = {1.0e16, 1.0, -1.0e16};
        double normalSum = 0.0;
        for (double value : values) {
            normalSum += value;
        }
        System.out.println("simple sum = " + normalSum);
        System.out.println("corrected sum = " + neumaierSum(values));

        // Approximation error from intentionally truncating Taylor series,
        // not simply because 2.0 is stored inaccurately.
        double firstOrder = 1.0 + 1.0;
        System.out.println("first-order exp(1) = " + firstOrder);
        System.out.println("Math.exp(1) = " + Math.exp(1.0));
    }
}
```

In the directory containing the file:

```bash
javac RepresentationVsAlgorithmErrorDemo.java
java RepresentationVsAlgorithmErrorDemo
```

**Expected output on Java 17+:**

```text
0.1 hex = 0x1.999999999999ap-4
0.1 + 0.2 = 0.30000000000000004
decimal sum = 0.3
long preserved = false
rounded long = 9007199254740992
naive formula = 0.0
stable formula = 5.0E-9
log(1+x) = 0.0
log1p(x) = 1.0E-16
simple sum = 0.0
corrected sum = 1.0
first-order exp(1) = 2.0
Math.exp(1) = 2.718281828459045
```

**Output explanation by error source:**

1. `0.1` cannot be stored accurately in finite binary form: **representation error**.
2. `2^53 + 1` cannot be preserved intact when placed into `double`: **conversion/representation error**, even though the integer input is completely exact.
3. `sqrt(x*x+1)-x` produces 0 while the conjugate formula produces around `5e-9`: **formula/algorithm is unstable under rounding**.
4. `log(1+x)` produces 0 while `log1p(x)` preserves the small number: **choosing a more stable computation function**.
5. Sequential sum loses +1 while compensated sum preserves +1: **difference in summation algorithm** on the same data.
6. `1+x` in place of `exp(x)` at `x=1` has large error because of **truncating the approximation series**, even with simple numbers that can be stored accurately.

## 14. Common Misconceptions

| Wrong conclusion | Correct understanding |
| --- | --- |
| "Every calculation is wrong because `double` cannot store 0.1 accurately" | Errors arise from representation, operation rounding, algorithms, data, and problem conditioning |
| "If inputs are exact binary numbers, the output is definitely exact" | Intermediate operations can round or overflow |
| "Using `double` instead of `float` fixes every bug" | Improves precision, but does not fix an unstable algorithm or bad approximation |
| "Algebraically equivalent formulas give identical Java results" | Changing parentheses/formula form changes where rounding occurs |
| "Running more iterations always increases accuracy" | Can reduce truncation error while accumulating roundoff or instability |
| "An input-sensitive problem is caused by a badly programmed algorithm" | Conditioning is a property of the problem; stability is a property of the algorithm |
| "Subtracting nearly equal numbers is automatically wrong" | It can be exact on the stored operands; the risk is exposing or magnifying existing relative error |
| "`BigDecimal` fixes an already corrupted double input" | Cannot recover already rounded data or unmeasured information |
| "`Math.log(1+x)` is as good as `Math.log1p(x)` near 0" | The `1+x` step can wipe out `x` before `log` runs |
| "Summing an array in any order gives the same result" | Floating-point results depend on rounding steps and grouping order |
| "`Double.MIN_VALUE` is a good default tolerance" | No; tolerances must be determined by scale and business requirements |
| "Reference `Math.exp` is an infinitely exact real number" | The method returns a finite `double` value with approximation/rounding error per the API contract |

## 15. Self-Check Exercises and Solutions

**Exercise 1.** Why can `0.1 + 0.2 == 0.3` evaluate to `false`? Is this representation error or algorithmic error?  
**Answer:** `0.1`, `0.2`, and `0.3` are rounded from decimal values to binary `double` values; addition also involves rounding. This example demonstrates the effect of representation and rounding, and **does not by itself prove that the algorithm's formula is wrong**.

**Exercise 2.** Does `long n = 9_007_199_254_740_993L; double d = n;` preserve `n`?  
**Answer:** No. `n=2^53+1` cannot be represented as an exact `double`; `d` rounds to `2^53`. This is data loss during type conversion.

**Exercise 3.** When `x=1e8`, why does `sqrt(x*x+1)-x` yield 0 even though the mathematical result is positive?  
**Answer:** `x*x+1` rounds to `x*x`; the square root returns `x`, and subtracting `x` becomes 0. The conjugate formula `1/(sqrt(x*x+1)+x)` avoids the unstable subtraction for this value range.

**Exercise 4.** Why is `Math.log1p(1e-16)` better than `Math.log(1+1e-16)`?  
**Answer:** `1+1e-16` in `double` rounds to 1, losing the small magnitude before taking the logarithm. `log1p` is designed to compute `log(1+x)` accurately when `x` is near 0 without suffering from that intermediate error.

**Exercise 5.** If a program uses `1+x` to approximate `exp(x)` at `x=1`, will replacing `double` with `BigDecimal` make the answer equal `e`?  
**Answer:** No. The error comes from dropping second-order and higher terms of the Taylor series; you must change or increase the accuracy of the approximation algorithm.

**Exercise 6.** Distinguish an *ill-conditioned* problem from an *unstable* algorithm.  
**Answer:** Ill-conditioned means the mathematical solution is sensitive to small changes in the input. Unstable means the numerical computation introduces error beyond acceptable bounds relative to the problem's sensitivity. You can have a sensitive problem with a relatively stable algorithm, or a well-conditioned problem with a poor implementation.

**Exercise 7.** When comparing results near 0, why can using relative error ratio alone be problematic?  
**Answer:** Because a reference denominator near 0 makes the ratio very large or undefined when the reference is 0. Absolute tolerance is more meaningful in this region, combined with relative tolerance at larger magnitudes.

**Exercise 8.** For the array `{1e16,1.0,-1e16}`, the naive approach gives 0.0 while the mathematical sum is 1. Which algorithm can improve this?  
**Answer:** Compensated summation such as Neumaier or an algorithm suited to the data can preserve the 1 in this example. You should test when changing data rather than assuming every compensation method is universally exact.

## 16. Error Analysis Checklist Before Fixing a Program

1. **Define the true result**: an ideal real number, a contractual decimal value, or an algorithmic result with a tolerance?
2. **Inspect input data**: is there already measurement error, parsing, casting, decimal literals, or `long → double` conversion?
3. **Inspect intermediates**: are very small numbers added to large ones, two nearly equal numbers subtracted, or is there overflow/underflow or bit loss?
4. **Inspect the formula**: is there a more stable equivalent form, `Math.log1p`/`Math.expm1`/`Math.hypot`, or a specialized algorithm?
5. **Separate approximation error**: do the series order, step size, stopping criterion, and iteration count meet the goal?
6. **Assess conditioning**: how sensitive is the problem to inputs; do the measured inputs have the necessary precision?
7. **Choose types and algorithms for the goal**: primitives, `BigInteger`, `BigDecimal`, compensated summation, or high-precision algorithms?
8. **Set clear metrics**: absolute error, relative error, or ULP; handle 0, NaN, infinity, and very large value ranges.
9. **Test edge cases**: values differing by many orders of magnitude, nearly equal numbers, near zero, values near type limits, and alternating positive/negative data.
10. **Document assumptions and tolerances** in APIs, tests, and docs; never patch a bug with an arbitrary fixed epsilon without justification.

**Conclusion:** *Representation error* occurs when a value does not fit accurately in the storage format; *operation error* occurs when calculation steps must round; *algorithmic error* occurs because the choice of computation/approximation can lose or amplify information. All three sources can compound. To fix it properly, find **the first step where information is lost**, evaluate the problem's characteristics, and then choose the appropriate data type and formula rather than merely printing more digits.
