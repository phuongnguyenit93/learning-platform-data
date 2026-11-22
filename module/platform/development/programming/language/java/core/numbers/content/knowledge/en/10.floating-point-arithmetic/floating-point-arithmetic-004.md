# How the `%` Operator Differs from `Math.IEEEremainder` in Java

Java supports **two floating-point remainder operations with two different rules**:

- The **`%`** operator computes the remainder from division whose quotient is **truncated toward zero** (*truncation toward zero*), similar to C's `fmod` function.
- **`Math.IEEEremainder(double, double)`** computes the remainder from division whose quotient is rounded to the **nearest integer**; if halfway between two integers, it chooses the **even integer** (*ties to even*) per IEEE 754 definition.

They can yield two results with **opposite signs**, even when given the exact same pair of floating-point numbers.

```java
double x = 7.0;
double y = 2.0;

System.out.println(x % y);                  // 1.0
System.out.println(Math.IEEEremainder(x,y)); // -1.0
```

Both results are valid **under their respective quotient rules**. `7 / 2 = 3.5`; if truncated toward 0, the integer quotient is 3 and the remainder is `7 - 2*3 = 1`. If choosing the nearest integer quotient with ties-to-even, the quotient is 4 and the remainder is `7 - 2*4 = -1`.

This lesson focuses on the conceptual model, choosing the right API, remainder sign, special IEEE 754 cases, pitfalls when used for angles/periods, and how to verify results on Java 17+.

## 1. Two Different Concepts: Remainder From Which Quotient?

Let `x` be the **dividend**, `y` be the **divisor**, and assume both are finite with `y != 0`. Mathematically, a remainder is described by:

```text
r = x - y * q
```

The difference lies in how the **integer `q`** is chosen.

### `x % y`: Quotient Truncated Toward 0

With floating-point operands, Java's `%` operator determines a conceptual integer quotient:

```text
q = trunc(x / y)
r = x - q * y
```

`trunc` discards the fractional part toward 0. For example:

- `7 / 2 = 3.5`: `q = 3`, `r = +1`.
- `-7 / 2 = -3.5`: `q = -3`, `r = -1`.
- `7 / -2 = -3.5`: `q = -3`, `r = +1`.
- `-7 / -2 = 3.5`: `q = 3`, `r = -1`.

**If non-zero, the `%` remainder carries the sign of `x`**, not the sign of `y`. The absolute value of the remainder is strictly less than `|y|` when both operands are finite and the divisor is non-zero.

### `Math.IEEEremainder`: Nearest Integer Quotient, Ties to Even

The `Math.IEEEremainder(x, y)` method uses:

```text
q = nearest integer to the mathematical quotient x / y;
    if two integers are equidistant, choose the even integer.
r = x - q * y
```

For `7 / 2 = 3.5`, the two integers 3 and 4 are equidistant at 0.5. Since 4 is **even**, `q = 4` and `r = -1`. For `5 / 2 = 2.5`, the two candidates are 2 and 3, so `q = 2` and `r = +1`.

Key point to emphasize: "even integer" refers to the **quotient `q`**, **not** the remainder. This is not "0.5 always rounds up".

> The formulas above explain the **mathematical semantics**. You should not manually emulate `%` or `IEEEremainder` with the floating-point expression `x - y * (...)`, because intermediate division and multiplication can round or overflow, making the result differ from the defined API. Call the proper operator/method directly.

## 2. Comparison Table With Positive and Negative Numbers

| `x` | `y` | `trunc(x/y)` | Nearest `q` (ties-even) | `x % y` | `Math.IEEEremainder(x,y)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 2 | 3 | 4 | 1 | −1 |
| 5 | 2 | 2 | 2 | 1 | 1 |
| 3 | 2 | 1 | 2 | 1 | −1 |
| −7 | 2 | −3 | −4 | −1 | 1 |
| 7 | −2 | −3 | −4 | 1 | −1 |
| −7 | −2 | 3 | 4 | −1 | 1 |
| 6 | 4 | 1 | 2 | 2 | −2 |
| −6 | 4 | −1 | −2 | −2 | 2 |
| 8 | 3 | 2 | 3 | 2 | −1 |

In this table, all numbers are small integers represented **exactly** as `double`, so the table does not mix in decimal-literal rounding error.

Easy-to-confuse cases:

- **`5.0 % 2.0 == Math.IEEEremainder(5.0,2.0)`:** both equal 1, because ties-even chooses quotient 2.
- **`7.0 % 2.0 != Math.IEEEremainder(7.0,2.0)`:** 1 differs from −1, because ties-even chooses quotient 4.
- **`6.0 % 4.0` equals 2, while `Math.IEEEremainder(6.0,4.0)` equals −2:** quotient 1.5 lies halfway between 1 and 2, so IEEE chooses 2.
- **Negating the divisor** can negate the quotient without automatically flipping the sign of the remainder in the corresponding examples: results are governed by the quotient selection rule and the sign of the dividend.

To memorize quickly, just remember `7.0` and `2.0`: it suffices as a counterexample to the claim "both are modulo so they are identical".

## 3. Why Does the Name "IEEEremainder" Not Mean "Always Positive Remainder"?

With `%` on floating-point numbers, if the result is non-zero, its sign follows the **dividend `x`**. However, with `Math.IEEEremainder`, the remainder can be positive **or negative**, not depending solely on the sign of `x` or `y`.

When `x`, `y` are finite and `y != 0`:

- The `%` remainder has magnitude **strictly less than** `|y|`.
- The `IEEEremainder` remainder has magnitude **no greater than half** of `|y|` under the mathematical relation of the nearest rounded quotient.
- At an exact half-period position, the sign of the `IEEEremainder` result is indirectly determined by **ties-to-even of the quotient**, so both `+|y|/2` and `-|y|/2` can appear depending on the case.

Example:

```java
System.out.println(Math.IEEEremainder(5.0, 2.0)); // 1.0
System.out.println(Math.IEEEremainder(7.0, 2.0)); // -1.0
```

Both values have the same magnitude 1.0 yet **opposite signs** even though both `x` and `y` are positive. Therefore, `Math.IEEEremainder` **is not suitable for directly generating indices from 0 to n−1**.

The word *remainder* in an API is not synonymous with the convention "non-negative modulo". When designing data contracts, state clearly what interval the remainder belongs to and whether the divisor may be negative.

## 4. Ties at Half a Unit: Ties-to-Even Differs from `Math.round`

The tie-breaking rule of `Math.IEEEremainder` aligns with the principle of rounding to the nearest integer, choosing the even integer. Java provides `Math.rint(double)` following nearest-integer with ties-to-even, yet `Math.IEEEremainder` must **not** be treated simply as `x - Math.rint(x/y) * y` across all inputs.

```java
System.out.println(Math.rint(2.5));  // 2.0
System.out.println(Math.round(2.5)); // 3
```

`Math.round` is a **different** API: for cases halfway between two integers, it chooses the direction toward **positive infinity** according to that method's rule. Meanwhile, `Math.rint(2.5)` chooses 2 because 2 is even. `Math.rint(3.5)` chooses 4 because 4 is even.

Be careful: computing `x/y` beforehand in `double` can round to a value different from the true mathematical quotient, or overflow to infinity when `x` is very large and `y` is extremely small. Multiplying `q*y` can also round. Therefore, use `Math.rint` to **illustrate the ties-even rule**, but use `Math.IEEEremainder` when you need exact **IEEE remainder semantics**.

### What About `Math.floor` and `Math.floorMod`?

- `Math.floor(double)` returns the `double` value of the greatest mathematical integer less than or equal to the argument; this is not a remainder operation.
- `Math.floorMod` takes **integer** arguments (`int`/`long`), and **has no overload taking `double`**. With a positive integer modulus, it produces a non-negative remainder even when the dividend is negative.
- `Math.IEEEremainder` uses the **nearest** quotient, **not** `floor` or `trunc`.

These three ways of choosing a quotient (*truncation*, *floor*, *nearest-ties-even*) are three distinct rules; only substitute one for another when you prove the result satisfies the problem's contract.

## 5. Special Cases: Zero, NaN, and Infinity

Java floating-point has `NaN`, `+Infinity`, `-Infinity`, `+0.0`, and `-0.0`. The behavior of `%` **differs significantly** from integer `%` when dividing by 0.

| Floating-Point Scenario | `x % y` | `Math.IEEEremainder(x,y)` |
| --- | --- | --- |
| Either operand is `NaN` | `NaN` | `NaN` |
| `x` is ±Infinity, `y` is finite non-zero | `NaN` | `NaN` |
| `y` is `+0.0` or `-0.0` | `NaN` | `NaN` |
| `x` is finite, `y` is ±Infinity | Returns `x` unchanged | Returns `x` unchanged |
| `x` is `+0.0` or `-0.0`, `y` is finite non-zero | Returns zero with same sign as `x` | Returns zero with same sign as `x` |
| Non-zero result, both operands finite | Sign matches `x` | Sign depends on nearest rounded quotient |
| Result is exactly 0 | Zero with same sign as `x` | Zero with same sign as `x` |

`Math.IEEEremainder` is a method that takes and returns `double`. There is no `IEEEremainder(float,float)` overload: if two `float` values are passed, Java widens them to `double` and the method returns `double`.

### Remainder by 0 Is `NaN`, Not `ArithmeticException`

```java
double a = 7.0 % 0.0;
double b = Math.IEEEremainder(7.0, 0.0);
System.out.println(Double.isNaN(a)); // true
System.out.println(Double.isNaN(b)); // true
```

Contrast with:

```java
// int invalid = 7 % 0; // Integer % by 0 is invalid;
// with a zero integer divisor at runtime, Java throws ArithmeticException.
```

With floating-point operands, `%` does not throw a runtime exception for a zero divisor. Also, `NaN` does not compare equal to itself under `==`, so check with `Double.isNaN`.

### Negative Zero Still Carries a Sign

```java
double r1 = -4.0 % 2.0;
double r2 = Math.IEEEremainder(-4.0, 2.0);

System.out.println(r1); // -0.0
System.out.println(r2); // -0.0
```

Even though `-0.0 == +0.0` is `true`, they have different sign bit patterns. If a data format or protocol requires preserving negative zero, you can inspect `Double.doubleToRawLongBits`.

Do not use `Math.abs` assuming every remainder now has the desired modulo meaning: the absolute value of a negative remainder can give a position **completely different** from the equivalent position in the cycle.

## 6. Expression Type: `float`, `double`, and Numeric Promotion

The `%` operator can be used with `int`, `long`, `float`, or `double`. For an operation with operands of different types, Java applies **binary numeric promotion**. For example:

```java
float a = 7.0f;
float b = 2.0f;

float floatRemainder = a % b; // Result of % is float.
double ieeeRemainder = Math.IEEEremainder(a, b); // Both floats are widened to double.
```

The values in the example are `floatRemainder == 1.0f` and `ieeeRemainder == -1.0`. When `double` is in one operand of `%`, the operation is evaluated in `double`:

```java
float x = 7.0f;
double y = 2.0;
double mixed = x % y; // Result is double.
```

For decimal numbers not exactly representable in binary32/binary64, the data was already rounded **before calling the method** or executing the operator. Therefore, a calculation intended as "x % 0.1" can leave an unexpected tiny remainder because `0.1` itself is an approximate binary value.

To verify correctness, separate two issues:

1. **Quotient rule**: truncate or nearest-ties-even?
2. **Operand representation**: does `float`/`double` store the input numbers accurately?

`Math.IEEEremainder` addresses the first rule; it does **not** turn every `double` value into an exact decimal.

## 7. Standalone Runnable Example on Java 17+

Save the code as `RemainderComparisonDemo.java`:

```java
public class RemainderComparisonDemo {
    public static void main(String[] args) {
        double[][] samples = {
                {7, 2}, {5, 2}, {3, 2},
                {-7, 2}, {7, -2}, {-7, -2},
                {6, 4}, {-6, 4}, {8, 3}
        };

        for (double[] sample : samples) {
            double x = sample[0];
            double y = sample[1];
            System.out.println(x + " % " + y + " = " + (x % y)
                    + " | IEEE = " + Math.IEEEremainder(x, y));
        }

        System.out.println("rint(2.5) = " + Math.rint(2.5));
        System.out.println("round(2.5) = " + Math.round(2.5));

        System.out.println("zero divisor with % -> NaN: "
                + Double.isNaN(7.0 % 0.0));
        System.out.println("zero divisor with IEEE -> NaN: "
                + Double.isNaN(Math.IEEEremainder(7.0, 0.0)));
        System.out.println("infinite dividend -> NaN: "
                + Double.isNaN(Math.IEEEremainder(
                        Double.POSITIVE_INFINITY, 2.0)));

        System.out.println("finite % infinity = "
                + (5.0 % Double.POSITIVE_INFINITY));
        System.out.println("finite IEEE infinity = "
                + Math.IEEEremainder(5.0, Double.POSITIVE_INFINITY));

        System.out.println("signed zero from %: " + (-4.0 % 2.0));
        System.out.println("signed zero from IEEE: "
                + Math.IEEEremainder(-4.0, 2.0));
        System.out.println("negative zero detected: "
                + (Double.doubleToRawLongBits(
                        Math.IEEEremainder(-4.0, 2.0)) == Long.MIN_VALUE));

        float floatRemainder = 7.0f % 2.0f;
        double ieeeRemainder = Math.IEEEremainder(7.0f, 2.0f);
        System.out.println("float remainder = " + floatRemainder
                + ", IEEE returns double = " + ieeeRemainder);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 RemainderComparisonDemo.java
java RemainderComparisonDemo
```

Stdout output:

```text
7.0 % 2.0 = 1.0 | IEEE = -1.0
5.0 % 2.0 = 1.0 | IEEE = 1.0
3.0 % 2.0 = 1.0 | IEEE = -1.0
-7.0 % 2.0 = -1.0 | IEEE = 1.0
7.0 % -2.0 = 1.0 | IEEE = -1.0
-7.0 % -2.0 = -1.0 | IEEE = 1.0
6.0 % 4.0 = 2.0 | IEEE = -2.0
-6.0 % 4.0 = -2.0 | IEEE = 2.0
8.0 % 3.0 = 2.0 | IEEE = -1.0
rint(2.5) = 2.0
round(2.5) = 3
zero divisor with % -> NaN: true
zero divisor with IEEE -> NaN: true
infinite dividend -> NaN: true
finite % infinity = 5.0
finite IEEE infinity = 5.0
signed zero from %: -0.0
signed zero from IEEE: -0.0
negative zero detected: true
float remainder = 1.0, IEEE returns double = -1.0
```

The program demonstrates: results with opposite signs for the same data, the ties-to-even rule, zero divisor/infinity handling, negative zero, and the return type difference when calling `Math.IEEEremainder` with `float`.

## 8. Which API to Choose in Real-World Problems?

### Case A — Remainder From Division Truncated Toward 0

Choose **`%`** when the contract wants the sign of the remainder to follow the dividend, matching Java's integer remainder behavior.

For example, computing the remainder of a displacement `-7.0` over a step size `2.0`:

```java
double offset = -7.0 % 2.0; // -1.0
```

This is a valid calculation if your logic needs a **signed remainder following the displacement**. However, it is **not** an always-non-negative modulo index coordinate.

### Case B — Deviation Closest to 0 in a Periodic Domain

Choose **`Math.IEEEremainder`** when you want a remainder closer to 0, such as in a **signed phase difference** convention or periodic deviation measured on a symmetric interval around 0. With a finite non-zero modulus, the remainder's magnitude is at most half the modulus.

```java
double angle = 350.0;
double signedRemainder = Math.IEEEremainder(angle, 360.0);
// -10.0, because quotient 1 is chosen instead of 0.
```

This can be a convenient way to express the shortest angular offset around 0. However, right at the **half-period** (±180 degrees for period 360), the result can be +180 or −180 depending on the rounded quotient and initial position; explicitly specify whether you want `[-180,180]`, `[-180,180)`, or `(-180,180]` and normalize the boundary if needed.

`Math.IEEEremainder` also does not guarantee finite values when inputs are NaN/Infinity or the period is 0. Validate inputs at business boundaries.

### Case C — Non-Negative Circular Index

If you are indexing arrays/lists, you should normally use **integers**, with `Math.floorMod`:

```java
int size = 5;
int index = Math.floorMod(-1, size); // 4
```

`Math.floorMod` has no overload for `double`. If your data is actually an integer index, do not convert to `double` to use `IEEEremainder`.

For floating-point angles or phases that need normalization into `[0,period)`, you can start with `%` and adjust when the remainder is negative, though you must consider that adding `period` can round at the boundary. Illustrative example for **finite inputs, positive period**, not a formula guaranteeing absolute precision:

```java
double value = -10.0;
double period = 360.0;
double r = value % period;
if (r < 0.0) r += period;
if (r >= period) r = 0.0; // Guard against rounding up to exact period.
System.out.println(r); // 350.0
```

If you need angle normalization with exact boundary rules, write explicit tests for ±0, multiples of the period, half-periods, very large inputs, and near-boundary cases. Do not blindly apply `Math.abs(value % period)`, because `Math.abs(-10.0 % 360.0)` is 10.0, **not** the equivalent position 350.0.

### Case D — Currency or Exact Decimal Numbers

If the problem involves money or decimals requiring exact rules, neither `%` on `double` nor `Math.IEEEremainder` solves binary's inability to represent `0.1` exactly.

You can use `BigDecimal`:

```java
java.math.BigDecimal amount = new java.math.BigDecimal("7.5");
java.math.BigDecimal step = new java.math.BigDecimal("2.0");
java.math.BigDecimal r = amount.remainder(step); // 1.5
```

`BigDecimal.remainder` has its own contract based on a quotient truncated toward 0, **not** nearest IEEE remainder. It operates on an exact decimal representation, though you still must ensure a non-zero divisor and define scale/precision policies for your calculations.

## 9. Common Mistakes

| Misconception | Consequence | Correct Approach |
| --- | --- | --- |
| Assuming `x % y` and `Math.IEEEremainder(x,y)` are the same operation | Wrong sign and boundary when quotient has fractional part | Decide whether truncate or nearest-ties-even is required |
| Assuming `IEEEremainder` always returns a non-negative number | `IEEEremainder(7,2) == -1` | Use the API matching the business result interval |
| Confusing ties-to-even with `Math.round` | Ties at 2.5 are handled differently | Understand IEEE quotient is nearest, ties-even |
| Manually computing `x - Math.rint(x / y) * y` instead of calling the method | Intermediate operations may round/overflow | Call `Math.IEEEremainder` directly |
| Using `IEEEremainder` as an array index | Remainder can be negative, and is `double` | Use `Math.floorMod` for integer indices |
| Calling `Math.floorMod` with `double` | Does not compile | Use integer overloads or redesign floating-point normalization |
| Expecting `7.0 % 0.0` to throw `ArithmeticException` | Actual result is `NaN` | Check divisor and `Double.isNaN` |
| Forgetting signed zero | `-0.0` has a negative sign bit despite equaling `+0.0` under `==` | Check raw bits only if business rules require it |
| Passing `float` to `IEEEremainder` and assuming a `float` result | The method returns `double` | Declare `double` and consider narrowing if needed |
| Choosing `%` to normalize angles into `[0,360)` | Negative numbers still yield negative remainders | Adjust with checks and boundary tests |
| Assuming "IEEE" means decimal exact | Does not change binary64 storage | Use `BigDecimal` if the problem requires exact decimals |
| Reading `Math.IEEEremainder` as division returning a quotient | It is the **remainder**, not the quotient | Use `/`, `floorDiv`, or the appropriate quotient algorithm |

## 10. Minimal Test Suite and Review Questions

When replacing one remainder calculation with another API, test at least these groups:

1. **Even/odd integer quotients and tie cases:** `(5.0,2.0)`, `(7.0,2.0)`, `(6.0,4.0)`.
2. **Operand signs:** `(-7.0,2.0)`, `(7.0,-2.0)`, `(-7.0,-2.0)`.
3. **Exact multiples and negative zero:** `(-4.0,2.0)`, `(+0.0,3.0)`, `(-0.0,3.0)`.
4. **Special values:** either operand NaN, dividend Infinity, divisor ±0, divisor Infinity.
5. **Application practical limits:** very large/very small numbers, approximate binary decimals, half-periods, and near-boundary inputs.

Answer for yourself:

- Why is `7.0 % 2.0` equal to 1.0 while `Math.IEEEremainder(7.0,2.0)` equals −1.0?
- Why is `Math.IEEEremainder(5.0,2.0)` equal to +1.0? What is the role of the even quotient?
- If you always need a remainder in `[0,n)` for a positive integer `n`, should you choose `%`, `IEEEremainder`, or `floorMod`?
- How does Java handle `7.0 % 0.0` differently from `7 % 0`?
- Why does `Math.rint(x/y)` only help explain the rule and is not a reliable manual implementation of IEEE remainder for all `double` values?
- For an angle of 350 degrees and a period of 360 degrees, what does `Math.IEEEremainder` return? Why do ±180 boundary conventions matter?
- When a function accepts `float` yet calls `Math.IEEEremainder`, what is the actual return type?
- For exact decimal data, why is switching to `BigDecimal.remainder` also a change in **operation contract**, not merely a change in bit count?

## 11. Official Documentation

- [Java Language Specification, `15.17.3 — Remainder Operator % (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3): integer and floating-point `%`; truncation rule, remainder sign, and special cases.
- [`Math.IEEEremainder` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#IEEEremainder(double,double)): definition of nearest quotient, ties-to-even, signed zero, and NaN/Infinity handling.
- [`Math.rint` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#rint(double)): rounding to nearest integer, ties to even.
- [`Math.floorMod` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#floorMod(int,int)): modulo operation for integer types.

**Conclusion:** `%` and `Math.IEEEremainder` are not two ways to write the same operation. `%` computes the remainder from a quotient **truncated toward 0**, so a non-zero result carries the sign of the dividend. `Math.IEEEremainder` computes the remainder from the **nearest integer quotient, ties to even**, so it can produce a remainder with the opposite sign of the dividend. Choose the operation based on the **value range and rounding policy** of the problem; check for NaN, Infinity, zero divisor, and near-boundary data before deploying to production.