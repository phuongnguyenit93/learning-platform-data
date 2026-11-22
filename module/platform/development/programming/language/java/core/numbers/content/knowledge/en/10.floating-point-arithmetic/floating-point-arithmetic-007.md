# Why Floating-Point Arithmetic Does Not Guarantee Real-Number Associativity in Java

> **Java core – numbers · Floating-Point Arithmetic**  
> **Goal:** Understand precisely why addition/multiplication on `float` and `double` can yield different results when parentheses are moved; distinguish algebraic associativity from syntactic grouping and evaluation order in Java; know how to design more stable summations, test, and handle rounding error.

## 1. What Does Associativity Mean in Mathematics?

For mathematical real numbers with exact addition and multiplication, we have:

\[
(a+b)+c=a+(b+c)
\]
\[
(a\times b)\times c=a\times(b\times c)
\]

This is **associativity**. It allows re-parenthesizing a chain of real-number additions or multiplications without changing the final value.

However, `float` and `double` values in Java are not an infinite-precision set of real numbers. They store a **finite set of bit patterns** in the IEEE 754 binary floating-point standard. After many operations, the mathematical result must be **rounded** to a value the data type can represent.

Therefore, floating-point operations are **not guaranteed to be associative like addition and multiplication on mathematical real numbers**. This is not a Java bug or CPU bug: computing in finite precision and rounding at every step is the root cause of the difference.

Pitfall to avoid: **subtraction and division on mathematical real numbers are inherently non-associative**, so examples like `(a-b)-c` differing from `a-(b-c)` are not specific evidence of losing associativity due to IEEE 754. We use **addition** and **multiplication** to illustrate the phenomenon accurately.

## 2. The Right Model: Add Then Round, Not Infinite Real Addition

For an operation `op`, we can picture:

\[
\mathrm{fl}(a\ \mathrm{op}\ b)
 = \mathrm{round}_{\mathrm{format}}(a\ \mathrm{op}\ b)
\]

Where `fl` is the result represented in `float` or `double` after the operation is rounded. For ordinary operations on finite values, Java 17+ uses deterministic IEEE 754 semantics; the rounding mode applied to standard arithmetic operators is **round to nearest, ties to even**.

Consequently, two ways of grouping compute two different rounding sequences:

\[
\mathrm{fl}\big(\mathrm{fl}(a+b)+c\big)
\]
\[
\mathrm{fl}\big(a+\mathrm{fl}(b+c)\big)
\]

Once `fl(a+b)` or `fl(b+c)` already differs from the exact mathematical value, the next operation cannot automatically recover any discarded bits. The two chains can produce **two different final results**, even though both expressions are valid and conform to Java.

### Finite Precision

| Type | Width | Effective Precision Bits (normal) | Approximate Significant Decimal Digits |
| --- | ---: | ---: | --- |
| `float` | 32 | 24 bits | About 6–9 |
| `double` | 64 | 53 bits | About 15–17 |

These bits are not distributed uniformly along the real number line: the spacing between representable values is generally **larger when the magnitude of the number is larger**. From this arises the phenomenon where a small number added to a very large number may **fail to change** the large number.

## 3. Classic Counterexample: Same Three Numbers, Moving Parentheses Changes the Result

Choose:

```java
double a = 1.0e16;  // 10^16
double b = -1.0e16; // -10^16
double c = 1.0;
```

Over mathematical real numbers:

\[
(a+b)+c=(10^{16}-10^{16})+1=1
\]
\[
a+(b+c)=10^{16}+(-10^{16}+1)=1
\]

In Java `double`:

```java
double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);          // 1.0
System.out.println(right);         // 0.0
System.out.println(left == right); // false
```

**Why does the left-hand side give 1.0?**

1. `a+b`: the two numbers of equal magnitude and opposite sign cancel out, producing `0.0` exactly.
2. Adding `c=1.0` next gives `1.0` exactly.

**Why does the right-hand side give 0.0?**

1. In `b+c`, we attempt to add `1.0` to `-10^16`.
2. At magnitudes around `10^16`, two consecutive `double` numbers are spaced **2.0** apart. The mathematical value `-10^16+1` lies exactly halfway between representable values, and the *ties to even* rule rounds it to `-10^16`.
3. Then `a + b` becomes `10^16 + (-10^16)`, yielding `0.0`.

You can verify directly:

```java
System.out.println(Math.ulp(1.0e16)); // 2.0
System.out.println(-1.0e16 + 1.0 == -1.0e16); // true
```

`Math.ulp(x)` gives the size of one unit in the last significant bit position (*unit in the last place*) around `x`. Here an offset of 1.0 is smaller than the resolution needed to produce a new `double` value around `10^16`.

| Expression | Intermediate Value After Rounding | Result |
| --- | --- | --- |
| `(a+b)+c` | `a+b = 0.0` | **1.0** |
| `a+(b+c)` | `b+c = -1.0E16` | **0.0** |

**Takeaway from the counterexample:** Java does not guarantee `(a+b)+c == a+(b+c)` when variables are `float`/`double`. Just one valid case returning different results suffices to refute the assumption of universal associativity.

## 4. Syntactic Grouping Differs from Operand Evaluation Order

Three related but distinct concepts must be separated:

- **Precedence:** `*` binds operands more tightly than `+`.
- **Syntactic associativity:** the chain `a+b+c` is grouped left-to-right, i.e. `(a+b)+c`.
- **Evaluation order:** Java evaluates operands left-to-right, including observable side effects of method calls.

Example:

```java
double a = 1.0e16, b = -1.0e16, c = 1.0;

double defaultGroup = a + b + c;    // (a + b) + c -> 1.0
double otherGroup   = a + (b + c);  // 0.0
```

The second set of parentheses **changes the expression tree**, thereby changing where rounding occurs. However, parentheses on the right do not mean Java arbitrarily invokes methods on the right before methods standing on the left.

Example:

```java
double result = first() + (second() + third());
```

Java still evaluates the operands in order: `first()`, then `second()`, then `third()` (unless an exception interrupts execution). **The obtained results** are then combined according to the parentheses: `second+third` first, and only afterward added to `first`.

In Java 17+, floating-point expressions have **always-strict** semantics. The compiler/JVM must not arbitrarily rewrite `(a+b)+c` into `a+(b+c)` if doing so could alter Java-specified behavior. Optimizations must preserve observable semantics; developers must not assume two groupings are equal for "algebraic optimization".

## 5. Why Low Bits Can Vanish: Magnitude, ULP, and Absorption

A small integer may be exactly representable on its own, yet not large enough to alter a `double` that already has a large magnitude:

```java
double big = 1.0e16;
double small = 1.0;

System.out.println(big + small == big); // true
System.out.println(Math.ulp(big));      // 2.0
```

This phenomenon is often called **absorption** of the small term in floating-point addition. It is not that the number 1 "does not exist"; it exists, but when added to `10^16`, the mathematical result falls between the points representable with `double`'s 53 bits of precision.

The crux is **relative precision**, not merely the large/small range of the type:

- `double` can represent numbers up to nearly `1.8×10^308`.
- That does not mean every integer spaced by 1 is exactly representable near `10^308` or `10^16`.
- Within `double`'s integer range, every integer up to `2^53` is exactly representable, but beyond that a spacing of 1 is **no longer guaranteed**.

In `float`, this effect arrives sooner:

```java
float bigFloat = 100_000_000f;
float smallFloat = 1f;

System.out.println(bigFloat + smallFloat == bigFloat); // true
System.out.println(Math.ulp(bigFloat)); // 8.0
```

Because `float` has 24 effective bits of precision, the resolution around one hundred million is **8.0**. An increment of 1.0 is not enough to move to a different value.

**Do not use** `Float.MIN_VALUE` or `Double.MIN_VALUE` as "the step between two numbers" across the entire number line. Those two constants are only the smallest positive subnormal numbers; the ULP step around 1, around one million, and around a very large value are all different.

## 6. Cancellation Error: Losing Information Before Subtracting/Adding

*Adding two numbers that are close in magnitude but opposite in sign* can cause **cancellation**. Cancellation **by itself does not always cause huge error**: if both operands are stored exactly and the addition is exact, the result can still be exact. The problem arises when the operands **already carry rounding error**, where subtracting nearly equal values can blow up the relative error of the result.

Consider the expression:

```java
double a = 1.0e16;
double b = 1.0;
double c = -1.0e16;

double computed = (a + b) + c;
System.out.println(computed); // 0.0
```

The intended mathematical value is 1, yet `a+b` rounds to `a` and then adding `c` yields 0. **The final addition is not wrong given the already-rounded inputs**; the "+1" information was discarded in the previous step.

A different grouping:

```java
double betterForThisCase = (a + c) + b;
System.out.println(betterForThisCase); // 1.0
```

For this dataset, adding the two large opposite-sign numbers first brings the partial result down to 0 before adding 1, preserving the small term. However, **there is no single best grouping order for all datasets**; choosing a summation algorithm requires examining value ranges, signs, numerical conditioning, and reproducibility requirements.

## 7. Multiplication Also Has No Associativity Guarantee: Intermediate Overflow

Mathematical associativity allows:

\[
(a\times b)\times c=a\times(b\times c).
\]

However, in `double`:

```java
double a = 1.0e308;
double b = 2.0;
double c = 0.5;

System.out.println((a * b) * c); // Infinity
System.out.println(a * (b * c)); // 1.0E308
```

Analysis:

1. The left-hand side computes `a*b = 2×10^308`, exceeding the largest finite `double` value, so after rounding it becomes `+Infinity`. Multiplying `Infinity*0.5` remains `Infinity`.
2. The right-hand side computes `b*c = 1.0` first, then `a*1.0 = 1.0E308`, which stays finite.

Over mathematical real numbers, both sides equal `10^308`. With floating-point numbers having a limited exponent range, **changing parentheses can determine whether intermediate overflow occurs**.

You should not conclude that smaller operands must always be multiplied first; in a different problem, that strategy can cause **underflow**, increase rounding error, or change how special values need to be handled.

## 8. Intermediate Underflow Also Produces Different Results

Conversely to overflow, an intermediate result too close to 0 can be rounded to 0 even though the final mathematical result after multiplying subsequent factors is non-zero.

```java
double tiny = Double.MIN_VALUE;
double half = 0.5;
double two = 2.0;

System.out.println((tiny * half) * two); // 0.0
System.out.println(tiny * (half * two)); // 4.9E-324
```

`Double.MIN_VALUE` is the smallest positive non-zero `double`, equal to `2^-1074`. The mathematical value `tiny*0.5 = 2^-1075` lies halfway between 0 and the smallest positive representable value. Under round-to-nearest, ties-to-even, it rounds to `+0.0`. Multiplying by 2 afterward cannot recover the lost value.

The right-hand side computes `0.5*2.0=1.0` first, so `tiny*1.0` remains `Double.MIN_VALUE`.

This is **underflow at an intermediate step**, not a syntax error or an exception thrown by the program. Floating-point operations experiencing underflow/overflow typically produce IEEE 754 values rather than throwing `ArithmeticException` like integer division by 0.

## 9. Inexact Decimal Representation Is a Related Cause, Not the Only Cause

`0.1` has no finite binary representation. When you write:

```java
double tenth = 0.1;
System.out.println(Double.toHexString(tenth));
// 0x1.999999999999ap-4
```

Java stores the **`double` value closest to 0.1**, not the exact mathematical fraction 1/10. Subsequent operations use that stored value, then round intermediates again.

However, the main counterexample in Section 3 **does not need** a `0.1` literal: the values `10^16`, `-10^16`, and `1` are all exactly representable in `double`, yet **intermediate addition** still causes the small term to vanish. Thus it is incorrect to conclude that only decimal numbers with infinite binary expansions are affected.

An easy-to-see example of rounding:

```java
System.out.println(0.1 + 0.2);        // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

This is an example of representation and addition/rounding error; it **does not by itself demonstrate non-associativity** because it does not compare two different ways of parenthesizing.

## 10. Java 17+, `strictfp`, `Math.fma`, and Reproducibility

Starting in Java 17, JEP 306 restored **always-strict floating-point semantics**; the `strictfp` keyword is no longer needed to request those exact same rules for floating-point expressions.

This makes arithmetic behavior consistent with the Java specification, but **does not make addition/multiplication associative**. "Results follow the standard and are predictable" is completely different from "parentheses can be moved arbitrarily".

### Fused Multiply-Add

`Math.fma(a, b, c)` computes the idealized exact product `a*b` and adds `c` before rounding **once** to `float`/`double`; unlike the ordinary expression `a*b+c`, which rounds after the multiplication and then again after the addition.

```java
double fused = Math.fma(a, b, c);
double separate = a * b + c;
```

Here variable values depend on the code context; this is an **API illustration**, not a standalone program. Use `fma` when an algorithm is designed to leverage fused multiply-add. **It does not make every sum or every multiplication automatically associative**, nor does it replace overflow and underflow control across the whole algorithm.

### Do Not Assume Compilers May Re-associate

Algebraic transformations such as:

```java
// Do not assume both sides are equivalent for all float/double!
double left = (a + b) + c;
double right = a + (b + c);
```

must not be applied unconditionally. Expressions can differ due to rounding error, infinities, `NaN`, and signed zero. When performance or stability improvements are needed, evaluate **computed results on actual data**, not just algebraic manipulations on paper.

## 11. Summing Many Numbers: Iteration Order and Parallel Reduction Can Change Results

In a program summing an array, partial sums can vary with:

- element traversal order;
- how the array is partitioned into chunks;
- how results from different threads are combined;
- naive sequential summation, pairwise summation, or compensated summation algorithms.

Even with identical input data, changing the summation tree can change the rounding steps. For example:

```java
double[] values = {1.0e16, -1.0e16, 1.0};

double firstOrder = 0.0;
for (double value : values) {
    firstOrder += value;
}
// firstOrder = 1.0
```

If the order is changed to `{1.0e16, 1.0, -1.0e16}`, sequential addition gives `0.0`. If a **parallel reduction** groups elements differently, the result can differ. That does not mean every parallel run differs from run to run: a deterministic reduction schedule can be consistent; the point is **never to promise an association order that the API/algorithm does not guarantee**.

In data analysis, finance, scoring, or distributed sums across machines, you must define the goal:

1. **Good enough approximation** within business tolerance.
2. **Bit-for-bit reproducibility** under a fixed algorithm and ordering.
3. **Exact sum under a specific arithmetic rule** (e.g., exact decimals, compensated summation, or high-precision accumulation).

These three goals demand different implementation and testing strategies.

## 12. Reducing Error When Summing Many Values

### 12.1. Choosing an Addition Order Suited to the Data

In some cases, summing small numbers together before combining with large numbers can reduce absorption. Adding two large opposite-sign numbers first can also preserve small terms, as in the Section 6 counterexample.

However, **sorting by absolute magnitude is not a theorem guaranteeing the best result for every sequence**, especially when there are many mixed-sign values or boundary cases. Do not change ordering ad hoc if the system requires reproducible results under a fixed pipeline.

### 12.2. Pairwise Summation

*Pairwise summation* adds along a balanced binary tree instead of sequentially into a single accumulator. For many datasets, this can reduce error accumulation and fits parallel execution well.

However, changing the summation tree **changes the rounding steps**, so the result can differ from a sequential sum. When reproducibility is a goal, document the reduction algorithm and combination order.

### 12.3. Kahan and Compensated Summation Algorithms

*Compensated summation* (such as Kahan or Neumaier) maintains an extra compensation variable tracking the low-order error lost in one addition step. It can substantially improve accuracy compared to naive sequential addition.

You should not claim "Kahan gives the exact answer for every dataset": for example, large numbers of opposite sign, cancellation, and small numbers in between can require other compensated variants; Kahan does not guarantee every algebraic expression becomes associative.

An illustration of **Neumaier summation** in Java:

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

This is an **illustrative method** that belongs inside a Java class. With the array `{1.0e16, 1.0, -1.0e16}`, the algorithm retains the small term in the correction variable and returns `1.0`. It still uses `double`, is not arbitrary-precision arithmetic for all cases, and still needs testing with infinities, NaN, overflow, and resource limits.

### 12.4. When Exact Decimals Are Required, Use `BigDecimal` Intentionally

For currency and decimal values with specific rounding rules, consider `BigDecimal` created from **strings**:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("10000000000000000");
BigDecimal b = new BigDecimal("-10000000000000000");
BigDecimal c = new BigDecimal("1");

BigDecimal exact = a.add(b).add(c);
System.out.println(exact); // 1
```

`BigDecimal` additions without a precision-limiting `MathContext` are performed exactly according to the decimal digits of the operands (assuming sufficient resources). If a `MathContext` with bounded precision is applied or rounding happens at each step, **grouping order can still affect the result**. `BigDecimal` does not automatically fix `double` data that was already rounded earlier; `new BigDecimal("0.1")` represents decimal 0.1 exactly, whereas `new BigDecimal(0.1)` reflects the binary value of `double 0.1`.

## 13. Be Careful When Testing Approximate Equality

Because `double` has rounding error, many algorithms should not compare approximate results using `==` if they were computed via different operation chains. However, **there is no single fixed epsilon suitable for every problem**.

An absolute + relative tolerance check has the form:

```java
static boolean nearlyEqual(double a, double b,
                           double absTolerance, double relTolerance) {
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true; // includes two infinities of the same sign or +0.0 == -0.0
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double diff = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return diff <= Math.max(absTolerance, relTolerance * scale);
}
```

This is an **illustrative method** that must be placed inside a class. Tolerance thresholds must be **non-negative, finite, and suited to the problem**; production code must validate them. This formula is a basic check pattern, not a universal solution for all magnitude ranges because subtraction, absolute value, and tolerance multiplication themselves can be affected by overflow, underflow, and rounding.

In testing, distinguish:

- **Bitwise correctness:** requires the exact bit pattern specified by the algorithm/pipeline, including zero's sign when meaningful.
- **Numerical approximation:** discrepancies acceptable within a chosen tolerance.
- **Business correctness:** e.g. monetary amounts needing fixed decimal rounding rules, better designed with `BigDecimal` from the start.

Do not use `Double.MIN_VALUE` as a generic epsilon: it is the smallest positive subnormal number, not a reflection of error near 1, 100, or `10^16`.

## 14. Standalone Java 17+ Program

Create the file **`FloatingPointAssociativityDemo.java`**:

```java
import java.math.BigDecimal;

public class FloatingPointAssociativityDemo {
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
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        System.out.println("(a+b)+c = " + ((a + b) + c));
        System.out.println("a+(b+c) = " + (a + (b + c)));
        System.out.println("same = " + (((a + b) + c) == (a + (b + c))));
        System.out.println("ulp(1e16) = " + Math.ulp(a));
        System.out.println("-1e16 + 1 == -1e16 = " + (b + c == b));

        double big = 1.0e308;
        System.out.println("multiply left = " + ((big * 2.0) * 0.5));
        System.out.println("multiply right = " + (big * (2.0 * 0.5)));

        double min = Double.MIN_VALUE;
        System.out.println("underflow left = " + ((min * 0.5) * 2.0));
        System.out.println("underflow right = " + (min * (0.5 * 2.0)));

        double[] values = {1.0e16, 1.0, -1.0e16};
        double naive = 0.0;
        for (double x : values) {
            naive += x;
        }
        System.out.println("naive sum = " + naive);
        System.out.println("compensated sum = " + neumaierSum(values));

        BigDecimal decimal = new BigDecimal("10000000000000000")
                .add(new BigDecimal("-10000000000000000"))
                .add(new BigDecimal("1"));
        System.out.println("decimal exact = " + decimal);
    }
}
```

Compile/run in the directory containing the file:

```bash
javac FloatingPointAssociativityDemo.java
java FloatingPointAssociativityDemo
```

**Standard output on Java 17+:**

```text
(a+b)+c = 1.0
a+(b+c) = 0.0
same = false
ulp(1e16) = 2.0
-1e16 + 1 == -1e16 = true
multiply left = Infinity
multiply right = 1.0E308
underflow left = 0.0
underflow right = 4.9E-324
naive sum = 0.0
compensated sum = 1.0
decimal exact = 1
```

**Reading the output:**

1. The left grouping of addition cancels the two large numbers first, keeping 1; the right grouping rounds away the +1 term before cancellation.
2. `Math.ulp(1e16)` equal to 2.0 explains why adding 1.0 to a number of magnitude `10^16` does not change the result.
3. In multiplication, intermediate overflow turns the left grouping into Infinity even though the right grouping stays finite.
4. In the underflow example, multiplying by 0.5 first loses `Double.MIN_VALUE`, whereas multiplying the factors 0.5 and 2.0 first preserves it.
5. The sequential sum of `{1e16,1,-1e16}` loses the 1; Neumaier compensated summation retains it in this case. `BigDecimal` with exact decimal inputs also produces 1.

## 15. Common Mistakes

| Misconception | Reality |
| --- | --- |
| "Addition and multiplication on `double` are always associative because math says so" | `double` operations perform intermediate rounding, so associativity is not guaranteed |
| "Only decimal numbers like 0.1 cause errors" | Even exact numbers like `1e16` and `1.0` suffer absorption when added |
| "Parentheses are just for readability" | For `float`/`double`, changing parentheses can change the final value |
| "Syntactic associativity equals mathematical associativity" | `a+b+c` groups left syntactically; that does not guarantee `a+(b+c)` yields the same result |
| "`*` has higher precedence so methods producing its operands run before the left-hand method" | Precedence is grouping; Java specifies operand evaluation order separately |
| "`double` has a huge range so all integers are spaced by 1" | ULP spacing grows with magnitude; around `1e16` the spacing is 2 |
| "Overflow always throws an exception like integer division by 0" | IEEE 754 can return ±Infinity; underflow can return subnormals or ±0 |
| "`Math.fma` makes all calculations infinitely exact" | FMA only rounds once for a single multiply-add; it does not eliminate all error |
| "Kahan/Neumaier always give the exact mathematical answer" | They reduce error in many cases, but are not infinite-precision arithmetic |
| "`BigDecimal` is always associative even with bounded precision" | When rounding at each step with `MathContext`, different groupings can differ |
| "`Double.MIN_VALUE` works as epsilon for all comparisons" | It is the smallest subnormal, not a general error threshold |
| "Parallel sum always produces the exact same bits as sequential sum" | Different addition groupings can yield different results unless the algorithm commits to a matching reduction rule |

## 16. Self-Check Exercises and Solutions

**Exercise 1.** With `a=1e16`, `b=-1e16`, `c=1.0` of type `double`, compute `(a+b)+c` and `a+(b+c)`.  
**Answer:** `1.0` and `0.0`. `b+c` rounds to `b` because the gap between adjacent `double` numbers around `1e16` is 2.

**Exercise 2.** Why does `double x=1e16; x+1.0 == x` evaluate to `true`?  
**Answer:** `Math.ulp(1e16) == 2.0`, so adding 1 falls right at the midpoint between two representable numbers and rounds back to `x` by ties-to-even.

**Exercise 3.** What do `(1e308*2.0)*0.5` and `1e308*(2.0*0.5)` print?  
**Answer:** `Infinity` and `1.0E308`. The left expression suffers intermediate overflow; the right expression multiplies 2 and 0.5 first to produce 1.

**Exercise 4.** Does `(Double.MIN_VALUE*0.5)*2` preserve `Double.MIN_VALUE`?  
**Answer:** No, it produces `0.0` due to underflow in the first multiplication. `Double.MIN_VALUE*(0.5*2)` stays equal to `Double.MIN_VALUE`.

**Exercise 5.** Why does `0.1+0.2 == 0.3` returning `false` not by itself prove non-associativity?  
**Answer:** Because it is one addition and one comparison, not a comparison of two different groupings of **the same three operands**. It illustrates representation/rounding error.

**Exercise 6.** How is `a+b+c` grouped in Java? Is it automatically equivalent to `a+(b+c)`?  
**Answer:** Grouped as `(a+b)+c` by left-associative syntax. For floating-point numbers, it is **not guaranteed** to give the same value as right-associative grouping.

**Exercise 7.** If array summation order affects the result, what is needed to make a report reproducible?  
**Answer:** Specify the summation algorithm, input order/chunking scheme, and testing rules; when higher accuracy is needed, use compensated summation or a method suited to the domain. If exact decimals are required, consider `BigDecimal` with clear precision/rounding rules.

**Exercise 8.** Does using `BigDecimal` guarantee any grouping yields the same result?  
**Answer:** With exact decimal operands and additions that do not round under bounded precision, associativity of addition is preserved (when operations complete). However, setting a bounded-precision `MathContext` and rounding at each step can make the result order-dependent.

## 17. Checklist When Designing Floating-Point Calculations

1. **Specify the type:** `float` or `double`? Are there casts, `f`-suffixed literals, or conversions from decimals?
2. **Inspect the grouping:** `(a+b)+c` differs from `a+(b+c)` not only on paper, but potentially at runtime too.
3. **Check magnitude ratios:** is a tiny value being added to a large accumulator? Use `Math.ulp` to assess resolution around real values.
4. **Watch for overflow/underflow:** intermediate results can become infinity or 0 before remaining factors are applied.
5. **Mind signs and special values:** `NaN`, ±Infinity, ±0.0 have their own rules; check `isFinite`/`isNaN` when needed.
6. **Do not re-parenthesize unconditionally:** even compilers must not apply transformations that violate Java semantics; algebraic rewrites must be proven safe for the data domain.
7. **Pick the summation algorithm:** sequential, pairwise, compensated, or a method matching bit-level reproducibility needs.
8. **Define acceptable error:** test tolerances according to business units and magnitudes; do not use `MIN_VALUE` as a generic epsilon.
9. **Use `BigDecimal` when appropriate:** especially for money/decimal data with rounding rules; construct values from strings and understand `MathContext`'s impact.
10. **Verify with counterexamples:** use `1e16`, `-1e16`, `1.0`, and overflow/underflow cases to demonstrate behavior directly when explaining code.

**Remember:** Mathematical real numbers have associative addition and multiplication, whereas `float`/`double` perform **each operation and round at every step**. Changing parentheses moves where rounding happens, so the result can change. Correct Java programming respects **grouping**, **evaluation order**, **representation limits**, and **summation algorithms** instead of assuming every algebraic rewrite preserves the result.