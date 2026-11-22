# Investigating the Error of 0.1, Repeated Sums, and Addition Order in Java

## 1. Practice Objectives

Try directly in Java:

~~~java
double a = 0.1;
double b = 0.2;

System.out.println(a + b);          // 0.30000000000000004
System.out.println(a + b == 0.3);   // false
~~~

Mathematically, `0.1 + 0.2 = 0.3`. With `double`, however, operations are performed on **approximate binary values** of the decimal numbers the programmer wrote. Representation error and rounding error during computation cause the result to differ from the `double` value representing the literal `0.3`.

This practice investigates four questions:

1. Why `0.1` is not represented exactly by `double`.
2. Why repeatedly adding `0.1` multiple times can differ from multiplying `n * 0.1`.
3. Why **addition order** can change the result of floating-point numbers.
4. How to measure, explain, and handle errors: `Math.ulp`, absolute/relative error, compensated summation algorithms, and `BigDecimal`.

You must distinguish **the expected mathematical value**, **the actual value stored in the numeric type**, and **the printed character string**. The fact that `System.out.println(0.1)` prints `0.1` does not mean every decimal digit of the value stored in `double` equals exactly one-tenth.

## 2. Root Cause: 0.1 Has an Infinite Binary Expansion

The decimal number `0.1 = 1/10` cannot be represented as a fraction whose denominator is a power of 2 in a finite number of bits. Just as `1/3 = 0.3333...` has an infinite expansion in base 10, `1/10` has an infinite expansion in binary:

~~~text
0.1 (decimal) = 0.000110011001100110011... (binary)
                              ^ repeating 0011 pattern
~~~

Java's `double` uses IEEE 754 binary64 format: 64 bits consisting of a sign bit, exponent field, and 52 fraction bits, giving **53 bits of significand precision** for normalized values. It can only store finitely many bits of the binary expansion, so it must round to the nearest representable value.

Inspect the actual `double` value representing `0.1`:

~~~java
double x = 0.1;
System.out.println(Double.toHexString(x));
// 0x1.999999999999ap-4
System.out.println(new java.math.BigDecimal(x));
// 0.1000000000000000055511151231257827021181583404541015625
~~~

The hex string `0x1.999999999999ap-4` represents the exact bit-value of `double`. The constructor `new BigDecimal(double)` also lets you see the **exact decimal value of the stored double**; this is a case where we intentionally use this constructor to investigate error.

The stored value is greater than `0.1` by about `5.55 × 10^-18`. This is the **initial representation error**; subsequent additions may introduce additional rounding errors. Error in complex computations does not necessarily grow monotonically with the number of calls and can change sign.

### Why does System.out.println(0.1) only print 0.1?

`Double.toString` chooses a decimal representation short enough to uniquely distinguish/recover the corresponding `double` value when parsed, rather than printing the entire exact decimal expansion of the binary value. Therefore:

~~~java
System.out.println(0.1);                  // 0.1
System.out.println(new BigDecimal(0.1));  // 0.100000000000000005551...
~~~

The two lines are **representing the same double value in two different ways**. Never conclude that the first line proves the stored number is exactly 1/10.

## 3. 0.1 + 0.2 Differs from 0.3: What Actually Happened?

With `double`, the literals `0.1`, `0.2`, and `0.3` are individually rounded from decimal to binary64. Adding `0.1 + 0.2` on two approximate values produces a result that is then rounded to a representable double value:

~~~java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual);            // 0.30000000000000004
System.out.println(expected);          // 0.3
System.out.println(actual == expected); // false
~~~

The two values `actual` and `expected` are **two different representable binary points** near the decimal number 0.3. The `==` check compares the existing `double` values, not an ideal decimal calculation.

This is normal floating-point behavior, not a bug specific to `println` or Java. Libraries and languages follow mathematical rules on finite-bit numbers. Very close approximations may suffice for measurements, graphics, or approximations, but do not automatically satisfy an exact decimal contract.

## 4. Repeated Addition: 10 Times and 100 Times Can Differ from Multiplication

Compare three ways of computing what mathematically equals 10:

~~~java
double sum = 0.0;
for (int i = 0; i < 100; i++) {
    sum += 0.1;
}

double multiplication = 100 * 0.1;
~~~

On Java 17:

| Approach | Printed `double` value |
| --- | --- |
| Adding `0.1` 10 times from `0.0` | `0.9999999999999999` |
| Adding `0.1` 100 times from `0.0` | `9.99999999999998` |
| Multiplying `100 * 0.1` | `10.0` |

Why do they differ despite the same mathematical formula?

- With repeated addition, each iteration of `sum += 0.1` performs **one floating-point addition and rounding**. Error from the previous iteration enters the next iteration.
- With multiplication `100 * 0.1`, the input `0.1` is already approximate, yet multiplying and rounding once can lead to a different stored value; in this example it prints as exact `10.0`.
- There is no rule that "multiplication is always more accurate than addition," nor any guarantee that "the error of a sum always grows." The result depends on values, method, and operation sequence.

**Do not generalize from one example that `100 * 0.1` is always better in every situation.** It only shows that mathematically equivalent expressions can produce different `double` values.

### Why does exact equality comparison cause surprises?

~~~java
double sum = 0.0;
for (int i = 0; i < 10; i++) {
    sum += 0.1;
}
System.out.println(sum == 1.0); // false
~~~

The error here is small, yet `==` has no notion of "close enough." Whether the error magnitude matters depends on the application, so you need an evaluation criterion grounded in the real data domain rather than expecting bit-exact equality by default.

## 5. Addition Order: Double Addition Is Not Mathematically Associative

For ideal real numbers, `(a + b) + c = a + (b + c)`. For finite-bit floating-point numbers, **the two sides can differ** because each intermediate operation can round.

Choose:

~~~java
double huge = 1.0e16;

double first = (huge + (-huge)) + 1.0;
double second = (huge + 1.0) + (-huge);

System.out.println(first);  // 1.0
System.out.println(second); // 0.0
~~~

Explanation:

1. `huge + (-huge)` equals exact zero, and then `0.0 + 1.0` is `1.0`.
2. `huge + 1.0` is too close to `huge` relative to the spacing between representable double values around `1e16`: the `1.0` contribution is lost during rounding. The next step adds `-huge`, yielding `0.0`.

Therefore, even with **the exact same operands and the same addition operation**, changing the evaluation order can change the result.

| Way of adding three numbers | Value |
| --- | ---: |
| `(1e16 + (-1e16)) + 1.0` | `1.0` |
| `(1e16 + 1.0) + (-1e16)` | `0.0` |

This situation is commonly called **loss of significance** when adding a small number to a much larger number, combined with **cancellation**. Cancellation can expose errors that occurred in earlier steps.

### Array order and aggregation

For example, an array `[1e16, 1.0, -1e16]`:

~~~java
double[] values = {1e16, 1.0, -1e16};
double sum = 0.0;
for (double value : values) {
    sum += value;
}
System.out.println(sum); // 0.0
~~~

If changed to `[1e16, -1e16, 1.0]`, the sequential loop gives `1.0`. Hence, when comparing results across implementations, record **both the input order and the accumulation algorithm**.

In parallel processing, a reduction algorithm can group additions differently; floating-point results can differ from a sequential loop without necessarily violating the summation contract. Do not expect `parallelStream` to reproduce the exact bit-wise sum of a sequential `for` loop unless a specific contract is defined and verified.

## 6. Complete Runnable Java 17 Program for Comparison

Save the file `FloatingPointExperiment.java`:

~~~java
import java.math.BigDecimal;
import java.util.Locale;

public class FloatingPointExperiment {

    static double repeated(double term, int count) {
        double sum = 0.0;
        for (int i = 0; i < count; i++) {
            sum += term;
        }
        return sum;
    }

    static double kahan(double term, int count) {
        double sum = 0.0;
        double compensation = 0.0;
        for (int i = 0; i < count; i++) {
            double y = term - compensation;
            double t = sum + y;
            compensation = (t - sum) - y;
            sum = t;
        }
        return sum;
    }

    public static void main(String[] args) {
        double tenth = 0.1;

        System.out.printf(Locale.ROOT, "hex(0.1) = %a%n", tenth);
        System.out.println("exact(0.1) = " + new BigDecimal(tenth));
        System.out.println("valueOf(0.1) = " + BigDecimal.valueOf(tenth));

        System.out.println("0.1+0.2 = " + (0.1 + 0.2));
        System.out.println("equal 0.3 = " + ((0.1 + 0.2) == 0.3));

        System.out.println("10 additions = " + repeated(0.1, 10));
        System.out.println("100 additions = " + repeated(0.1, 100));
        System.out.println("100 multiplied = " + (100 * 0.1));
        System.out.println("Kahan 100 additions = " + kahan(0.1, 100));

        System.out.println("BigDecimal 100 additions = "
                + BigDecimal.valueOf(0.1)
                    .multiply(BigDecimal.valueOf(100)));

        double large = 1e16;
        System.out.println("(big + -big) + 1 = "
                + ((large + -large) + 1.0));
        System.out.println("(big + 1) + -big = "
                + ((large + 1.0) + -large));

        System.out.println("ulp(1.0) = " + Math.ulp(1.0));
    }
}
~~~

Compile/run with JDK 17 or newer:

~~~bash
javac FloatingPointExperiment.java
java FloatingPointExperiment
~~~

Verified output when running on Java 17:

~~~text
hex(0.1) = 0x1.999999999999ap-4
exact(0.1) = 0.1000000000000000055511151231257827021181583404541015625
valueOf(0.1) = 0.1
0.1+0.2 = 0.30000000000000004
equal 0.3 = false
10 additions = 0.9999999999999999
100 additions = 9.99999999999998
100 multiplied = 10.0
Kahan 100 additions = 10.0
BigDecimal 100 additions = 10.0
(big + -big) + 1 = 1.0
(big + 1) + -big = 0.0
ulp(1.0) = 2.220446049250313E-16
~~~

The program has four comparison groups:

- **Representation:** `0.1` in hex and exact decimal value of the double.
- **Accumulation:** `repeated` adding 10/100 times vs. single multiplication.
- **Algorithmic improvement:** `kahan` compensated summation to reduce accumulation loss in the example.
- **Large magnitude range:** the same three operands with two addition orders yielding `1.0` and `0.0`.

Numbers are printed from standard APIs, independent of system locale thanks to `Locale.ROOT` in the hex print call. The remaining print expressions rely on Java's default `Double.toString`.

## 7. Absolute Error, Relative Error, and ULP Units

To analyze results, define:

~~~text
expected = reference value
actual   = computed value

absoluteError = |actual - expected|
relativeError = absoluteError / |expected|   (when expected != 0)
~~~

**Absolute error** measures the difference in the quantity's units. For example, `9.99999999999998` compared to 10 has an absolute error of about `2 × 10^-14`.

**Relative error** expresses deviation relative to the magnitude of the reference value. It is unsuitable when the reference value is 0; if close to 0, a tiny denominator can inflate the ratio even when absolute error is small.

A related tool is `Math.ulp(x)` (*unit in the last place*): returns the spacing of one floating-point representation step at magnitude `x` as defined by Java. For example:

~~~java
System.out.println(Math.ulp(1.0));
// 2.220446049250313E-16
~~~

This value indicates double's granularity around 1.0. Spacing between representable double numbers **is not constant across the number line**: as the absolute magnitude of a number grows, the absolute spacing between adjacent numbers generally grows as well.

Note: You cannot take `Math.ulp(1.0)` as the right comparison threshold for every range. In `1e16 + 1.0`, the representation step at `1e16` is larger than `1.0`; that is why small contributions can be lost.

## 8. Approximate Equality Checks: Set Tolerance by Problem, Not an Arbitrary Epsilon

If the goal is to know whether a result is **close enough** to a reference, you can define a tolerance:

~~~java
double actual = 0.1 + 0.2;
double expected = 0.3;
double absoluteTolerance = 1e-12;

boolean nearEqual = Math.abs(actual - expected)
        <= absoluteTolerance;
System.out.println(nearEqual); // true
~~~

This is an **illustrative code snippet** placed in a Java method/class. The threshold `1e-12` is only an example for a problem with values around 0.3, **not a universal constant for all applications**.

Distinguish:

- **Absolute tolerance:** suitable when units and error thresholds have fixed meaning, especially around zero.
- **Relative tolerance:** appropriate for values spanning wide magnitudes; compares the difference against the scale of the data.
- **ULP-based comparison:** useful when testing carefully analyzed floating-point algorithms; must account for edge cases and varying ranges.

A commonly used combined rule conceptually:

~~~text
|actual - expected| <= max(absTolerance,
                           relTolerance * max(|actual|, |expected|))
~~~

Before applying in practice, ensure tolerances are non-negative, handle `NaN`, infinity, zero, and potential overflow/underflow in difference computation or tolerance multiplication. Do not apply this formula mechanically to every problem.

**Important:** Do not use "approximate equality" checks to replace exact equality for identifiers, counts, monetary amounts, or invariants requiring exact values. Choosing the right algorithm/data type still matters more than increasing tolerance to pass tests.

### The == operator is not always wrong

With `double`, `==` is accurate when you **want to compare existing binary values** and know the conditions clearly. For example, `x == 0.0` is the right check for "x currently equals 0.0 under double comparison" (both `+0.0` and `-0.0` compare equal under `==`). What is unsafe is assuming approximate calculations will naturally produce bit-wise equality with an expected decimal literal.

`NaN` is a special case: `Double.NaN == Double.NaN` is false. Use `Double.isNaN(x)` when identifying NaN and `Double.isFinite(x)` when excluding both NaN/infinity. Do not assume a `false` result from `==` always comes from rounding error.

## 9. Kahan Compensated Summation: Reducing Accumulated Error Without Turning Double into Exact Decimal

Kahan's compensated summation algorithm maintains a `compensation` variable to estimate the small portion lost during addition:

~~~java
static double kahan(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;
    for (double value : values) {
        double y = value - compensation;
        double t = sum + y;
        compensation = (t - sum) - y;
        sum = t;
    }
    return sum;
}
~~~

This is a **method snippet** placed in a Java class. Intuitively, the steps are:

1. `y` adjusts the next term by the recorded error compensation.
2. `t` performs the addition into the running sum.
3. `compensation` stores an estimate of the rounding part from the addition just performed.
4. `sum` receives the updated accumulated result.

In the example of adding `0.1` 100 times, Kahan gives `10.0` instead of `9.99999999999998`. This is **an improvement in a specific example**, not a promise that every sum and every addition order becomes exact.

Limitations:

- Input `0.1` is still approximated in double; the algorithm cannot change the nature of the numeric type.
- Kahan helps with many accumulation cases, but does not perfectly resolve all cases of cancellation, overflow, imprecise inputs, or ill-conditioned data.
- Other algorithms such as *pairwise summation*, Neumaier summation, or sorting terms before adding can help depending on the problem; reordering may affect data-processing semantics and does not automatically guarantee exact results.
- In systems requiring reproducible results, you must keep the algorithm, ordering, and parallelism mode fixed by contract.

If it matters that **100 times the decimal number 0.1 equals exactly 10.0**, use an exact decimal representation like `BigDecimal` from strings, rather than treating Kahan as a general replacement.

## 10. BigDecimal: Exact Decimal Representation When Inputs Are Exact

`BigDecimal` can store exact decimal numbers defined in strings:

~~~java
BigDecimal tenth = new BigDecimal("0.1");
BigDecimal sum = BigDecimal.ZERO;

for (int i = 0; i < 100; i++) {
    sum = sum.add(tenth);
}

System.out.println(sum.toPlainString()); // 10.0
~~~

Fundamental differences:

- `new BigDecimal("0.1")` interprets the decimal in the string and stores the exact value 0.1.
- `BigDecimal.valueOf(0.1)` takes the canonical decimal representation of the **double value** via `Double.toString`, so for this literal it creates a `BigDecimal` with decimal value `0.1`. This is usually reasonable when the input source truly only provides a `double` and you want its canonical decimal representation.
- `new BigDecimal(0.1)` stores the exact **rounded binary value** of the double, hence the long decimal string `0.10000000000000000555...`, **not** exact 1/10.

Comparison:

~~~java
System.out.println(new BigDecimal("0.1"));
// 0.1

System.out.println(BigDecimal.valueOf(0.1));
// 0.1

System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625
~~~

`BigDecimal` uses arbitrary-precision decimal arithmetic to perform exact addition/multiplication when no rounding `MathContext` is required. However, **that does not mean every division has a finite decimal representation**. For example, `1 / 3` does not terminate in decimal; you must define scale and `RoundingMode` when dividing.

Additionally, `BigDecimal` is immutable, so you must **reassign** `sum = sum.add(tenth)`; calling `sum.add(tenth);` and discarding the result leaves `sum` unchanged.

## 11. How to Conduct a Meaningful Experiment

To compare errors across strategies, define upfront:

1. **Reference value:** in the 100 times 0.1 experiment, the ideal decimal value is 10.0. Produce the reference using `BigDecimal("0.1")`, not from the same double addition being tested.
2. **Data and ordering:** element count, initial values, input order, cases with vastly different magnitudes and opposite signs.
3. **Algorithm:** sequential loop, multiplication, Kahan, pairwise, or `BigDecimal`.
4. **Metrics:** printed value, absolute/relative error, and time and memory cost when relevant.
5. **Conclusion rules:** performance cannot be reliably evaluated from a single tiny measurement; accuracy cannot be evaluated from only one favorable example.

An illustrative experiment table:

| Test case | Algorithm | Result | Reference value |
| --- | --- | --- | --- |
| 10 × 0.1 | Repeated double addition | `0.9999999999999999` | 1.0 |
| 100 × 0.1 | Repeated double addition | `9.99999999999998` | 10.0 |
| 100 × 0.1 | Double multiplication | `10.0` | 10.0 |
| 100 × 0.1 | Kahan double | `10.0` | 10.0 |
| 100 × 0.1 | BigDecimal from string | `10.0` | 10.0 |
| 1e16, -1e16, 1 | Added in one order | `1.0` | 1.0 |
| 1e16, 1, -1e16 | Added in another order | `0.0` | 1.0 |

The last two rows are especially important: the result can be **off by a full 1.0**, not just in the last few digits, when terms differ vastly in magnitude and cancel out.

## 12. Streams and Parallelism: Do Not Accidentally Change the Accumulation Model

Java provides:

~~~java
double sum = java.util.Arrays.stream(values).sum();
~~~

When `values` is a `double[]` array, this is `DoubleStream.sum()`. Its implementation may use compensated summation or strategies described by Java to improve result quality. Do not assume this sum necessarily matches a `for (double x : values) sum += x` loop, especially when pipeline structure or parallel execution changes associativity grouping.

With floating-point numbers:

- A mathematical sum does not change under permutation, whereas a sum computed in finite-bit numbers can change.
- Parallel branch addition can alter associativity order; the result can depend on the reduction strategy.
- Benchmarks comparing accuracy and speed must clearly specify the dataset, algorithm, and execution conditions.
- Do not use `parallel()` while assuming arithmetic results must be bit-identical to a sequential loop.

If a result must be exactly reproducible, choose an algorithm with a sufficiently strict contract and control how results are partitioned and combined. If exact decimal is required, consider `BigDecimal` and a business rounding model rather than relying on `double` summation order.

## 13. When to Use double vs. BigDecimal?

| Need | Typically suitable choice | Points to check |
| --- | --- | --- |
| Graphics, simulation, sensors, scientific computing accepting approximations | `double` | Absolute/relative error, conditioning, stable algorithms |
| Summing many numbers of varying magnitudes | `double` with suitable summation method, if error policy allows | Ordering, cancellation risk, Kahan/pairwise, test against reference |
| Monetary amounts in exact decimal units | `BigDecimal` from strings or smallest unit in `long` when appropriate | Scale, rounding, overflow, currency units |
| Decimal values needing exact 0.1 + 0.2 = 0.3 | `BigDecimal("0.1")` + `BigDecimal("0.2")` | Do not pass through double |
| Integer counts | `int`, `long`, `BigInteger` by range | Overflow; do not use float/double if exact integers are needed |

There is no rule that `BigDecimal` is always better than `double`. It typically has higher compute/memory overhead and requires managing scale and rounding policies. Conversely, `double` is efficient and appropriate for many approximate numeric applications when results are evaluated with sound error criteria.

## 14. Common Mistakes and How to Fix Them

**Mistake 1 — Believing 0.1 stored in double is exact 1/10.** `println(0.1)` prints concisely; use `Double.toHexString` and `new BigDecimal(0.1)` when you need to inspect the exact double value.

**Mistake 2 — Comparing `0.1 + 0.2 == 0.3` to test approximate floating-point addition.** The comparison can be false due to representation and rounding. Use meaningful tolerances or an exact decimal model as required.

**Mistake 3 — Thinking repeated addition and multiplication must yield the same double.** Multiple additions perform multiple roundings; a single multiplication performs its own calculation/rounding step. Results can differ.

**Mistake 4 — Assuming floating-point addition is associative.** `(a+b)+c` and `a+(b+c)` can differ. Numbers with vastly different magnitudes or opposite signs easily expose such discrepancies.

**Mistake 5 — Using a single global error threshold for all numbers.** `1e-12` may make sense at scale 1, but be meaningless at scale 1e15 or 1e-20. Determine tolerance from units, business thresholds, and value magnitudes.

**Mistake 6 — Inferring Kahan always produces exact results.** It reduces accumulated error in many cases, yet does not fix all cancellation cases and does not turn double data into exact decimals.

**Mistake 7 — Using `new BigDecimal(0.1)` to represent exact one-tenth.** That constructor receives the already-approximated double bit-value. Construct from the string `"0.1"` when the original source is decimal.

**Mistake 8 — Calling `sum.add(...)` without assigning the result.** `BigDecimal` is immutable; you must write `sum = sum.add(...)`.

**Mistake 9 — Concluding a double value is wrong simply because its printed form differs from expectations.** Quantify the error against a reference value, considering requirements and numerical conditioning. A small discrepancy may be acceptable, or it may accumulate into a large error.

**Mistake 10 — Treating negative zero, NaN, and Infinity as ordinary values.** These special values affect comparisons and error measurements. Use `Double.isFinite` and clear input handling rules.

**Mistake 11 — Comparing a loop result with DoubleStream.sum and claiming Java is buggy.** The accumulation algorithm and ordering may differ. Only draw conclusions after comparing under the same assumptions and contract.

**Mistake 12 — Relying on a single test suite with 0.1 to conclude an algorithm is stable.** Also test very large/small numbers, opposite signs, subtraction of nearly equal values, many additions, random inputs, and deliberate counterexamples.

## 15. Practice Exercises and Answers

### Exercise 1 — Predict and explain

~~~java
double s = 0.0;
for (int i = 0; i < 10; i++) {
    s += 0.1;
}
System.out.println(s);
System.out.println(s == 1.0);
~~~

**Answer:**

~~~text
0.9999999999999999
false
~~~

Each addition uses an approximate double and may round. Final error makes the represented value differ from `1.0`.

### Exercise 2 — Changing addition order

With `a=1e16`, `b=-1e16`, `c=1.0`, predict:

~~~java
double left = (a + b) + c;
double right = (a + c) + b;
~~~

**Answer:** `left = 1.0`, `right = 0.0`. The `a+c` branch loses `1.0` during rounding because the larger number is too big.

### Exercise 3 — BigDecimal: choosing the constructor

Predict:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b).toPlainString());
~~~

**Answer:** `0.3`. Both are constructed accurately from decimal strings, and `add` requires no rounding.

If you replace `new BigDecimal("0.1")` with `new BigDecimal(0.1)`, the input data is already an approximate binary value, no longer exact 1/10.

### Exercise 4 — Designing error checks

You need to test an algorithm summing sensor data with values around `10^-6` and `10^6`. Should you use a single absolute epsilon such as `1e-12`?

**Answer:** Not by default. You must consider units, value scales, measurement noise, error requirements, and cancellation risk; you may need a combination of absolute error, relative error, or dedicated statistical criteria. Tolerance is a specification, not a trick to make every test pass.

### Exercise 5 — Does Kahan replace BigDecimal?

In the example of adding `0.1` 100 times, Kahan gives `10.0`. Can we conclude Kahan stores exact `0.1`?

**Answer:** No. The input representation is still approximate binary64; Kahan helps compensate for accumulated error. For business logic requiring exact decimal values, use `BigDecimal` from strings and explicit rounding rules.

## 16. Checklist When Investigating a Floating-Point Bug

1. **What is the actual input value?** Decimal from string, already-rounded double, or sensor data?
2. **What is the reference value?** Was it produced independently by a sufficiently accurate model?
3. **Have you distinguished representation error from operation error and accumulated error?**
4. **Are there very large numbers alongside very small numbers in the same sum?** Is there cancellation or changed addition order?
5. **Do tests inspect printed values, hex bit-values, absolute/relative errors, and ULP when needed?**
6. **When summing many elements, did you choose an appropriate accumulation algorithm and define processing order?**
7. **If exact decimal is needed, did you use `BigDecimal` from strings or an integer type representing the smallest unit?**
8. **If using tolerance, does the threshold come from business/unit requirements and have NaN/infinity been handled?**

**Conclusion:** `0.1` cannot be represented exactly in binary64, so `0.1 + 0.2`, repeated sums, and additions in different orders can produce different `double` results. This is a limitation of finite-bit floating-point numbers. Experiment, measure errors, and choose the right algorithm/numeric type; do not confuse **good enough approximation** with **exact equality by decimal value**.
