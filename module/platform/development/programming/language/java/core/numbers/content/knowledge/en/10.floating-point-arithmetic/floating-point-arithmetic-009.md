# Digit Cancellation When Subtracting Two Nearly Equal Numbers in Java

## 1. The Phenomenon to Understand

In floating-point computation, **digit cancellation** (*cancellation*) occurs when subtracting two numbers that are close in value. Matching leading digits cancel out, leaving a very small difference as the result. If both operands already contain rounding error, that error can account for a huge proportion of the difference. Cases that severely degrade relative precision are often called **catastrophic cancellation**.

For example, in mathematical real numbers:

\[
(10^{16}+1)-10^{16}=1.
\]

However, with Java `double`:

```java
double base = 1e16;
double plusOne = base + 1.0;
double difference = plusOne - base;

System.out.println(difference);  // 0.0
```

Reason: `1e16` is a representable `double` value, whereas the integer `10^16 + 1` lies between two adjacent `double` values in that region. The expression `base + 1.0` rounds back to `base`. By the time subtraction runs, the program is subtracting **two equal `double` values**, so it gets `0.0`. The true value sought is `1`, meaning an absolute error of `1` and a relative error of **100%**.

The core point: subtraction can execute completely accurately on the **two stored `double` values**, yet still differ widely from the difference of the **two original mathematical values**. Do not blame every error on the `-` operator alone; the source of error often arises during operand creation or an earlier operation.

## 2. Why Is Floating-Point Arithmetic Prone to Digit Cancellation?

`float` and `double` represent a finite set of binary numbers, with significand precision of about **24 bits** and **53 bits** respectively. Not every real number or large integer can be represented exactly. When a result falls between two representable values, Java must round according to IEEE 754 rules.

A simple error model:

\[
\widehat a=a+\delta_a,\qquad
\widehat b=b+\delta_b
\]

where `a` and `b` are the intended mathematical values, while `â` and `b̂` are the two stored values. When subtracting:

\[
\widehat a-\widehat b
=(a-b)+(\delta_a-\delta_b).
\]

If `a` and `b` are close to each other, then `|a-b|` is very small, whereas `δa` and `δb` can be relatively large **compared to the difference**. Example:

- True values: `a = 1_000_000_001`, `b = 1_000_000_000`, difference equals `1`.
- Suppose the two operands after rounding become `1_000_000_000` and `1_000_000_000` respectively. The computed difference is `0`, even though each operand's error was only about one part per billion relative to its magnitude.

The absolute error of subtraction may look small compared to the operands, yet the relative error of the result can be enormous. With `float`, the phenomenon appears at lower magnitudes than `double` because there are fewer precision bits.

### Sensitivity Metric of Subtraction

For `a != b`, a measure of sensitivity to relative errors in the two operands is:

\[
\kappa_{\mathrm{sub}}=\frac{|a|+|b|}{|a-b|}.
\]

When `a` and `b` are close yet have substantial magnitude, the denominator approaches 0 so `κ` becomes very large. This signals that **small relative errors in the inputs can be amplified** when computing the difference.

For instance, if `a ≈ 1_000_000` and `b ≈ 999_999`, then `|a-b| ≈ 1` and `κ` is about two million. This is a sensitivity property of the problem itself, not proof that a particular algorithm is wrong. If the inputs are exact numbers and the difference is representable, subtraction may introduce no additional error.

## 3. Digit Cancellation Does Not Mean "Subtraction Is Always Inaccurate"

There is an important theorem in floating-point arithmetic: **Sterbenz's lemma**. For two representable positive finite floating-point numbers `x` and `y`, if

\[
\frac{x}{2}\le y\le 2x,
\]

then in binary arithmetic with proper rounding and subnormal handling, the subtraction `x - y` can be represented **exactly**. Java uses IEEE 754 with subnormals, so this is a useful explanation for many subtractions of close numbers.

Example:

```java
double a = Math.nextUp(1.0);  // 1.0000000000000002
double b = 1.0;
double delta = a - b;         // 2.220446049250313E-16
```

Both `a` and `b` are exact `double` values and their difference is represented exactly. If we **define the problem on those exact two `double` values**, subtraction loses no further digits.

However, if `a` and `b` are results of earlier approximate steps, the true difference of the **original data** can still differ significantly. Therefore:

1. **Cancellation** describes leading digits canceling out when taking a difference.
2. **Catastrophic cancellation** emphasizes prior error getting relatively amplified to the point of making the result unreliable.
3. **Rounding of subtraction itself** is a separate issue; sometimes subtraction between two close `double` numbers is performed exactly.

Recognizing this distinction helps pick the right remedy: reformulate to avoid losing information **before subtraction**, change how inputs are stored, or use higher precision when truly necessary.

## 4. ULP and an Example of Losing the Entire Difference

**ULP** (*unit in the last place*) is the spacing unit between representable values in a region. Java provides `Math.ulp(float)` and `Math.ulp(double)` to observe the ULP size at a given value.

```java
double x = 1e16;

System.out.println(Math.ulp(x));       // 2.0
System.out.println(x + 1 == x);        // true
System.out.println((x + 1) - x);       // 0.0
System.out.println((x + 2) - x);       // 2.0
```

At `1e16`, the gap between adjacent `double` numbers is `2`. Therefore:

- `x + 1` lies right halfway between two representable numbers; the ties-to-even rule rounds it to `x`.
- `x + 2` lands on the next `double`, so the difference is `2`.
- No exception is thrown; `0.0` is a valid `double` result.

If `double` is replaced by `float`, the spacing jumps to `2` right at `2^24 = 16_777_216`, causing nearby integers to collapse into the same value much sooner.

Avoid concluding that because `double` has "15–16 decimal digits", every difference of two 15-digit numbers has that many reliable digits. The reliable precision of a **difference** also depends on each operand's error and the distance between them.

## 5. Common Formula Pattern: Difference of Two Square Roots

Consider the expression:

\[
d(x)=\sqrt{x+1}-\sqrt{x},\qquad x\ge 0.
\]

When `x` is large, the two square roots are very close. If computed directly, the small difference can round down to 0. Multiply by the conjugate expression:

\[
\begin{aligned}
d(x)
&=\frac{(\sqrt{x+1}-\sqrt{x})(\sqrt{x+1}+\sqrt{x})}
{\sqrt{x+1}+\sqrt{x}}\\
&=\frac{(x+1)-x}{\sqrt{x+1}+\sqrt{x}}\\
&=\boxed{\frac{1}{\sqrt{x+1}+\sqrt{x}}}.
\end{aligned}
\]

The final formula **avoids directly subtracting two nearly equal numbers**. With `x = 1e16`:

```java
double x = 1e16;
double naive = Math.sqrt(x + 1.0) - Math.sqrt(x);
double stable = 1.0 / (Math.sqrt(x + 1.0) + Math.sqrt(x));

System.out.println(naive);  // 0.0
System.out.println(stable); // 5.0E-9
```

The true mathematical value is approximately `5 × 10^-9`. The conjugate formula gives a reasonable result here even when `x + 1.0` already rounded to `x`; the denominator mainly depends on `sqrt(x)`.

**Limitation to know:** algebraic transformation stabilizes calculations across many domains, but does not guarantee avoiding all overflow/underflow or rounding. When `x` is near `Double.MAX_VALUE`, `x + 1` itself can still equal `x`; when `x` is huge, the sum of roots can cause issues in other formula variants. Consider the input domain and accuracy requirements, especially for general formulas like `sqrt(a) - sqrt(b)`, where `(a - b)` may also have already lost information.

A useful general identity, when the denominator is non-zero:

\[
\sqrt{a}-\sqrt{b}=\frac{a-b}{\sqrt{a}+\sqrt{b}}.
\]

If `a` and `b` are both numbers already rounded to the same value, this transformation **does not** recover the lost difference; `a-b` must be preserved or computed more accurately from the original data.

## 6. Using Dedicated APIs: `Math.expm1` and `Math.log1p`

Certain library functions are specifically designed for small differences to avoid digit cancellation.

### `Math.expm1(x)` Instead of `Math.exp(x) - 1`

When `x` is near 0, `e^x` is very close to `1`. If `Math.exp(x)` rounds to `1.0`, subtracting `1.0` yields `0` even though the mathematical result is close to `x`.

```java
double tiny = 1e-16;

System.out.println(Math.exp(tiny) - 1.0); // 0.0
System.out.println(Math.expm1(tiny));     // 1.0E-16
```

`Math.expm1(x)` is defined as `e^x - 1` and implemented for higher accuracy when `x` is near 0. In small compound-interest accumulation, probability distribution functions, or exponential transformations, this is usually a direct, meaningful replacement.

### `Math.log1p(x)` Instead of `Math.log(1 + x)`

Similarly, when `x` is too small, the expression `1.0 + x` can round to `1.0` before calling `Math.log`:

```java
double tiny = 1e-16;

System.out.println(Math.log(1.0 + tiny)); // 0.0
System.out.println(Math.log1p(tiny));     // 1.0E-16
```

`Math.log1p(x)` computes `ln(1 + x)` with better accuracy near 0. The real domain of `log1p(x)` is `x >= -1` (`x = -1` gives negative infinity, `x < -1` gives `NaN`). Do not blindly convert other algebraic expressions into `log1p` if they do not share the same mathematical meaning.

Common thread: these APIs accept the **small offset `x` upfront**, avoiding constructing a value near `1` and then subtracting or taking a logarithm. As a result, the offset is not lost at an intermediate step.

## 7. Roots of a Quadratic Equation: Computing Without Subtracting Nearly Equal Numbers

Consider `a*x^2 + b*x + c = 0` with `a != 0` and discriminant `D = b*b - 4*a*c >= 0`. The familiar formula:

\[
x_{1,2}=\frac{-b\pm\sqrt D}{2a}.
\]

If `-b` and `sqrt(D)` are close in value, one root can suffer severe error when subtracting. For example, `a = 1`, `b = -10^8`, `c = 1`: the smaller root is around `10^-8`, while the two subtracted terms are both around `10^8`.

An alternative formula when `q != 0`:

\[
q=-\frac12\left(b+\operatorname{copySign}(\sqrt D,b)\right),
\qquad x_1=\frac qa,\quad x_2=\frac cq.
\]

In `Math.copySign(magnitude, sign)`, the sign of the second parameter is applied to the magnitude of the first parameter. Computing `q` chooses **adding two quantities of the same sign** to avoid cancellation in the large root; the remaining root uses Vieta's product of roots `x1*x2 = c/a`.

Step-by-step illustrative example:

```java
double a = 1.0;
double b = -1e8;
double c = 1.0;
double discriminant = b * b - 4 * a * c;
double root = Math.sqrt(discriminant);

double naiveSmall = (-b - root) / (2 * a);
double q = -0.5 * (b + Math.copySign(root, b));
double stableLarge = q / a;
double stableSmall = c / q;

System.out.println(naiveSmall);  // 7.450580596923828E-9
System.out.println(stableSmall); // 1.0E-8
System.out.println(stableLarge); // 1.0E8
```

Subtracting to compute the small root with the direct formula introduces significant error; using `c/q` gives a much closer result. This is an example of **restructuring the operations**, rather than merely widening from `float` to `double`.

This is **not yet a complete quadratic equation solver**. In production code you must handle `a == 0`, `D < 0`, `q == 0`, repeated roots, infinities/`NaN`, overflow/underflow when computing the discriminant, and very large or very small value ranges. Do not use this illustrative snippet as a general solver for arbitrary inputs.

## 8. Complete, Runnable Java 17 Demo

Save the program as `CancellationDemo.java`:

```java
import java.math.BigDecimal;

public class CancellationDemo {
    public static void main(String[] args) {
        double base = 1e16;
        double plusOne = base + 1.0;

        System.out.println("ulp = " + Math.ulp(base));
        System.out.println("plusOne equals base = " + (plusOne == base));
        System.out.println("difference = " + (plusOne - base));

        double x = 1e16;
        double naiveRoot = Math.sqrt(x + 1.0) - Math.sqrt(x);
        double stableRoot = 1.0 / (Math.sqrt(x + 1.0) + Math.sqrt(x));
        System.out.println("sqrt naive = " + naiveRoot);
        System.out.println("sqrt stable = " + stableRoot);

        double tiny = 1e-16;
        System.out.println("exp naive = " + (Math.exp(tiny) - 1.0));
        System.out.println("expm1 = " + Math.expm1(tiny));
        System.out.println("log naive = " + Math.log(1.0 + tiny));
        System.out.println("log1p = " + Math.log1p(tiny));

        BigDecimal preciseA = new BigDecimal("10000000000000001");
        BigDecimal preciseB = new BigDecimal("10000000000000000");
        System.out.println("decimal difference = "
                + preciseA.subtract(preciseB));

        double a = 1.0;
        double b = -1e8;
        double c = 1.0;
        double disc = b * b - 4 * a * c;
        double squareRoot = Math.sqrt(disc);
        double naiveSmall = (-b - squareRoot) / (2 * a);
        double q = -0.5 * (b + Math.copySign(squareRoot, b));
        double stableSmall = c / q;
        System.out.println("quadratic naive small = " + naiveSmall);
        System.out.println("quadratic stable small = " + stableSmall);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac CancellationDemo.java
java CancellationDemo
```

Output:

```text
ulp = 2.0
plusOne equals base = true
difference = 0.0
sqrt naive = 0.0
sqrt stable = 5.0E-9
exp naive = 0.0
expm1 = 1.0E-16
log naive = 0.0
log1p = 1.0E-16
decimal difference = 1
quadratic naive small = 7.450580596923828E-9
quadratic stable small = 1.0E-8
```

The example uses `BigDecimal` from two **unrounded** decimal strings. Therefore, subtracting `10000000000000001 - 10000000000000000` preserves the exact difference `1`. Conversely, calling `BigDecimal.valueOf(plusOne)` and `BigDecimal.valueOf(base)` here would only see the same `double` value `1e16`; `BigDecimal` cannot recover the `+1` already lost.

The outputs of the floating-point operations in the example reflect Java's behavior for the chosen values; when modifying parameters, results and error levels can change.

## 9. Ways to Reduce Digit Cancellation Risk

### Reformulate Before Computing

When the difference of two close values is the target, look for an equivalent mathematical expression with fewer subtractions. Classic examples:

- `sqrt(x+1) - sqrt(x)` → `1 / (sqrt(x+1) + sqrt(x))` for `x >= 0`.
- `exp(x) - 1` → `Math.expm1(x)` when `x` is small.
- `log(1+x)` → `Math.log1p(x)` when `x` is small.
- Small root of a quadratic equation → method using `q` and the product-of-roots relation, with valid domain checks.

The goal is to avoid generating and then subtracting two values that were rounded to nearly equal values.

### Preserve Exact Representation From the Source When Business Logic Requires It

If inputs are exact decimals, keep them as strings or `BigDecimal` and perform calculations in base 10:

```java
BigDecimal a = new BigDecimal("10000000000000001");
BigDecimal b = new BigDecimal("10000000000000000");
BigDecimal diff = a.subtract(b); // 1
```

Do not write `new BigDecimal(0.1)` expecting it to recover the exact decimal `0.1`; the `double` constructor converts the **existing binary value**. Use `new BigDecimal("0.1")` when the source data is an exact decimal. `BigDecimal.valueOf(double)` is often handy when you want the short decimal representation per `Double.toString`, yet it still cannot recover information lost in an earlier calculation.

`BigDecimal` is not the default choice for all scientific computations: you must weigh performance, division/rounding rules (`MathContext` when needed), and correctness of the numerical model.

### Choose Appropriate Precision

`double` generally lowers risk compared to `float` because it has 53 significand bits versus 24 bits. However, `double` **does not** automatically cure sensitive expressions. If results must distinguish large consecutive integers, use `long` or `BigInteger` instead of storing them in `double`; if decimal data must be exact, consider `BigDecimal` from an exact source.

### Evaluate Error With Purposeful Test Data

You should test inputs such as:

- Two operands that are equal or differ by only about one ULP.
- Two very large operands with a very small expected difference.
- Values near 0, negative values, `+0.0`/`-0.0`, and boundaries prone to overflow/underflow.
- Cases with a root near 0 in quadratic formulas or differences of roots.
- A higher-precision reference dataset (such as `BigDecimal` from strings, symbolic arithmetic, or specialized software), when comparison is meaningful.

Comparing against a reference can use absolute error `|computed - expected|` and relative error `|computed - expected|/|expected|` when `expected != 0`. If the true value is near or equal to 0, using relative error alone can be misleading; combine it with an absolute threshold based on business units.

### Do Not Use Measures That Fail to Address the Root Cause

- **`Math.abs(a - b) < epsilon` only tests approximate equality**; it does not restore a difference that lost precision. A fixed `epsilon` threshold can also be meaningless across vastly different scales.
- **Formatting extra digits when printing** (`printf`, `DecimalFormat`) does not recreate lost digits.
- **Casting and casting back** does not recover information discarded when converting `long` to `double` or when adding `1` to an overly large `double`.
- **Kahan summation** can reduce error when accumulating many numbers, but cannot fix two operands that already collapsed to the same value prior to subtraction. That is a different problem.
- **Using `BigDecimal` after computing inaccurately with `double`** merely moves an inaccurate value into another representation; it does not recreate original data.

## 10. Exercises and Solutions

**Exercise 1.** Explain why the following program prints `true`:

```java
double n = 1e16;
System.out.println(n == n + 1.0);
```

**Answer:** `Math.ulp(1e16) == 2.0`. The spacing between representable `double` numbers is `2` in this region; `n + 1` lies right halfway between two values, and the ties-to-even rule sends the result back to `n`.

**Exercise 2.** What results do the direct and conjugate computations of `sqrt(1e16+1) - sqrt(1e16)` produce?

**Answer:** Direct: `0.0`. Via `1 / (sqrt(1e16+1) + sqrt(1e16))`: `5.0E-9` in Java for the chosen values. In exact real arithmetic, the true value is close to `5 × 10^-9`.

**Exercise 3.** `Math.exp(1e-16) - 1` can become `0.0`. Which function should be used if the goal is `e^x - 1` for very small `x`?

**Answer:** `Math.expm1(x)`. Similarly, for `ln(1+x)` with small `x`, use `Math.log1p(x)`.

**Exercise 4.** "Subtracting two very close `double` numbers always loses digits during the subtraction itself." True or false?

**Answer:** False. Sterbenz's lemma shows that many subtractions of two representable floating-point values that are close enough are computed exactly. Severe error typically comes from **operands that were already approximate** or from a formula that causes the relative error of the difference to blow up.

**Exercise 5.** Why does `BigDecimal.valueOf(base + 1.0).subtract(BigDecimal.valueOf(base))` not return `1` when `base = 1e16`?

**Answer:** The addition `base + 1.0` already rounded to `base` in type `double` before `BigDecimal.valueOf` was called; exact subtraction of two equal values yields `0`.

**Exercise 6.** Someone wants to measure the difference between two measurements `1000000.001` and `1000000.000`. What should they pay attention to?

**Answer:** The accuracy of each measurement and how inputs are stored determine how reliable the `0.001` difference is. You need to know the units, measurement resolution, instrument error, and business requirements; subtraction in `double` cannot make a difference more accurate than the source information. If inputs are decimals whose published digits must be preserved verbatim, `BigDecimal` from strings can be used.

**Remember:** Digit cancellation makes the difference of two close numbers especially sensitive to errors in each operand. Check the source of errors, observe ULP, prefer stable formulations (`expm1`, `log1p`, conjugates, appropriate root-finding formulas), and keep data in an exact representation before information is rounded away.