# ceil, floor, rint, and round in Java: Four Confusable Rounding Methods

## 1. Objectives

Java provides several rounding-related methods in `java.lang.Math` and `java.lang.StrictMath`. The four most common names are `ceil`, `floor`, `rint`, and `round`. They are **not equivalent**, even though they sometimes return the same value.

After this lesson, you will be able to:

- Explain each method's rounding direction using its mathematical definition.
- Distinguish the rule for numbers **halfway between two integers**: `rint` uses *ties to even*, whereas `round` prefers the integer **toward positive infinity** when two options are equidistant.
- Predict results for negative numbers, `-0.0`, very large values, `NaN`, and `Infinity`.
- Choose the right method by **return type**: `ceil`/`floor`/`rint` return `double`; `round(float)` returns `int` and `round(double)` returns `long`.
- Know when `BigDecimal` and `RoundingMode` are needed instead of applying `Math.round` to financial values.
- Avoid data loss during casting, numeric conversions, and multi-step rounding.

The main examples run on **Java 17+** without preview features. Most rules also apply to the corresponding `StrictMath` methods.

## 2. First: What Is Rounding to an Integer?

Suppose we have a real number `x` and want an integer value close or related to `x`. Several reasonable rules exist, so **you must determine the rule before calculating**.

For example, `2.7`:

- The smallest integer greater than or equal to it is 3.
- The largest integer less than or equal to it is 2.
- The nearest integer is 3.

For example, `-2.7`:

- The smallest integer greater than or equal to it is **−2**.
- The largest integer less than or equal to it is **−3**.
- The nearest integer is **−3**.

This is why casual phrases like "round up" or "round down" easily cause confusion with **negative numbers**. In Java, use formal definitions:

| Method | Primary Rule | Mathematical Result for 2.7 | For −2.7 |
| --- | --- | --- | --- |
| `Math.ceil(x)` | Smallest integer **≥ x** | 3 | −2 |
| `Math.floor(x)` | Largest integer **≤ x** | 2 | −3 |
| `Math.rint(x)` | Nearest integer; ties pick **even** | 3 | −3 |
| `Math.round(x)` | Nearest integer; ties pick toward **+∞** | 3 | −3 |

The table above describes **mathematical values**. In terms of Java types, the first three methods return integer values **as `double`**, such as `3.0`; `Math.round(double)` returns primitive integer `long`, such as `3L`.

## 3. Math.ceil(double): Toward Positive Infinity

`Math.ceil(double a)` returns the `double` value equal to the **smallest mathematical integer not less than** the argument.

\[
\operatorname{ceil}(x)=\min\{n\in\mathbb Z:n\ge x\}
\]

~~~java
System.out.println(Math.ceil(2.1));  // 3.0
System.out.println(Math.ceil(2.9));  // 3.0
System.out.println(Math.ceil(-2.1)); // -2.0
System.out.println(Math.ceil(-2.9)); // -2.0
System.out.println(Math.ceil(3.0));  // 3.0
~~~

Short snippets like these go inside a method; a standalone program is in section 10.

**Key point:** for negative numbers, `ceil` can **decrease the absolute magnitude**, because the rounding direction is toward `+∞`, not "away from 0".

For example, `-2.9` lies between `-3` and `-2`; the smallest integer not less than `-2.9` is `-2`.

### Signed Zero

Java `double` distinguishes `+0.0` and `-0.0`. Under the `Math.ceil` contract, a negative argument greater than `-1.0` and less than `0.0` yields **`-0.0`**:

~~~java
System.out.println(Math.ceil(-0.3)); // -0.0
System.out.println(Math.ceil(+0.3)); // 1.0
~~~

Although `-0.0 == 0.0` is true, the sign of zero can be observed when printing or taking reciprocals (`1.0 / -0.0` is `-Infinity`). If the application does not care about zero's sign, you can intentionally normalize it after rounding.

## 4. Math.floor(double): Toward Negative Infinity

`Math.floor(double a)` returns the **largest mathematical integer not exceeding** the argument, though the return type remains `double`.

\[
\operatorname{floor}(x)=\max\{n\in\mathbb Z:n\le x\}
\]

~~~java
System.out.println(Math.floor(2.1));  // 2.0
System.out.println(Math.floor(2.9));  // 2.0
System.out.println(Math.floor(-2.1)); // -3.0
System.out.println(Math.floor(-2.9)); // -3.0
System.out.println(Math.floor(-0.0)); // -0.0
~~~

With negative numbers, `floor` usually **increases the absolute magnitude**, because it moves toward `-∞`. For instance, `floor(-2.1) == -3.0`, not `-2.0`.

### floor Differs from Integer Casting

Casting `double` to `int` or `long` (in normal ranges) discards the fractional part **toward 0**, not toward negative infinity:

~~~java
double x = -2.9;
System.out.println((int) x);       // -2
System.out.println(Math.floor(x)); // -3.0
~~~

If you need to partition a negative coordinate axis into cells via `floor(x / cellSize)`, this difference is especially important. Use integer casting when you truly want truncation toward 0; use `floor` when you want the mathematical lower bound.

**Note:** casting floating-point numbers to `int`/`long` also has specific rules for `NaN` and out-of-range values. Do not replace `floor` with a cast if you want to preserve mathematical rules and special-value handling.

## 5. Math.rint(double): Nearest Integer, Ties to Even

`Math.rint(double a)` returns the `double` closest in value to an integer. If **two integers are equidistant**, it picks the **even** value (*round half to even*, also called *ties to even* or *banker's rounding*).

~~~java
System.out.println(Math.rint(2.3));  // 2.0
System.out.println(Math.rint(2.7));  // 3.0
System.out.println(Math.rint(2.5));  // 2.0
System.out.println(Math.rint(3.5));  // 4.0
System.out.println(Math.rint(-2.5)); // -2.0
System.out.println(Math.rint(-3.5)); // -4.0
~~~

Because 2 and 4 are even, the midpoints `2.5` and `3.5` are handled differently. For negative numbers, `-2` and `-4` are still even integers.

### Why Pick Even on Ties?

Picking even reduces one-directional bias when many values **exactly halfway** between two integers are rounded. However, that **does not guarantee** the sum of an arbitrary dataset will be error-free or unbiased: data distribution and calculation order still matter.

For example, with consecutive exact half-integers:

| Input | Two Nearest Candidates | `rint` Result |
| --- | --- | --- |
| 1.5 | 1 or 2 | 2.0 |
| 2.5 | 2 or 3 | 2.0 |
| 3.5 | 3 or 4 | 4.0 |
| 4.5 | 4 or 5 | 4.0 |
| −1.5 | −2 or −1 | −2.0 |
| −2.5 | −3 or −2 | −2.0 |
| −3.5 | −4 or −3 | −4.0 |

### rint Returns double, Not int or long

~~~java
double nearest = Math.rint(2.5); // 2.0
// int n = Math.rint(2.5);       // compile error: double does not convert to int automatically
~~~

If you need an `int`, check finiteness and range before converting:

~~~java
double nearest = Math.rint(input);
if (!Double.isFinite(nearest)
        || nearest < Integer.MIN_VALUE
        || nearest > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Rounded value outside int range");
}
int count = (int) nearest;
~~~

This is an illustrative snippet inside a method with variable `input`. The check above ensures the result is finite and within `int` range; business domain requirements (e.g., `count >= 0`) must still be checked separately.

### Special Case of −0.5

`Math.rint(-0.5)` returns **`-0.0`** under the tie-breaking rule selecting the even integer (0) while preserving the sign of zero. Do not immediately cast to `int` assuming there was no sign difference:

~~~java
System.out.println(Math.rint(-0.5)); // -0.0
~~~

## 6. Math.round(float) and Math.round(double): Nearest, Ties Toward Positive

Unlike the previous three methods, `Math.round` has **two overloads**:

~~~java
int roundedFloat = Math.round(2.5f);
long roundedDouble = Math.round(2.5);
~~~

Signatures:

| Overload | Parameter | Return Type |
| --- | --- | --- |
| `Math.round(float a)` | `float` | `int` |
| `Math.round(double a)` | `double` | `long` |

The rule is to pick the nearest integer; **if two integers are equidistant**, pick the integer toward **positive infinity**.

~~~java
System.out.println(Math.round(2.5));   // 3 (long)
System.out.println(Math.round(3.5));   // 4 (long)
System.out.println(Math.round(-2.5));  // -2 (long)
System.out.println(Math.round(-3.5));  // -3 (long)
System.out.println(Math.round(-0.5));  // 0 (long)
~~~

For `-2.5`, the two equidistant integers are `-3` and `-2`. The one in the **more positive direction** is `-2`, so `Math.round(-2.5) == -2L`.

**Do not describe `Math.round` simply as "round half away from zero".** For negative exact halves, `Math.round` chooses the `+∞` direction, so `-2.5` becomes `-2` rather than `-3`.

### round Differs from rint at Ties

~~~java
System.out.println(Math.rint(2.5));  // 2.0 (double)
System.out.println(Math.round(2.5)); // 3 (long)

System.out.println(Math.rint(-0.5));  // -0.0 (double)
System.out.println(Math.round(-0.5)); // 0 (long)
~~~

When choosing a method, always check both the **tie-breaking rule** and the **output data type**.

## 7. Comparison Table of Confusable Cases

Entries in the three columns `ceil`/`floor`/`rint` use `double` representation; the `round` column uses `long`.

| `x` | `ceil(x)` | `floor(x)` | `rint(x)` | `round(x)` |
| ---: | ---: | ---: | ---: | ---: |
| 2.1 | 3.0 | 2.0 | 2.0 | 2 |
| 2.5 | 3.0 | 2.0 | 2.0 | 3 |
| 3.5 | 4.0 | 3.0 | 4.0 | 4 |
| −2.1 | −2.0 | −3.0 | −2.0 | −2 |
| −2.5 | −2.0 | −3.0 | −2.0 | −2 |
| −3.5 | −3.0 | −4.0 | −4.0 | −3 |
| −0.5 | −0.0 | −1.0 | −0.0 | 0 |
| 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| −0.0 | −0.0 | −0.0 | −0.0 | 0 |

Conclusions from the table:

1. `ceil`/`floor` always follow **mathematical upper/lower direction**, not away from/toward zero.
2. `rint` and `round` usually give the same value when not at an exact midpoint.
3. At exact midpoints, `rint` chooses even; `round` chooses the positive side.
4. `round` always returns a primitive **integer** type, so it cannot preserve `-0.0`.
5. If the input is not a finite number or is too large, additional rules in section 8 apply.

## 8. NaN, Infinity, Signed Zero, and Out-of-Range Values

### 8.1. ceil, floor, and rint Preserve Special Values

For `Math.ceil`, `Math.floor`, and `Math.rint`:

- If the argument is `NaN`, the result is `NaN`.
- If the argument is `+Infinity` or `-Infinity`, the result is that same infinity.
- If the argument is `+0.0` or `-0.0`, the result preserves zero with its corresponding sign.
- If already a mathematical integer in `double` form, there is no fractional part to round; the value remains unchanged.

~~~java
System.out.println(Math.ceil(Double.NaN));              // NaN
System.out.println(Math.floor(Double.POSITIVE_INFINITY)); // Infinity
System.out.println(Math.rint(Double.NEGATIVE_INFINITY));  // -Infinity
System.out.println(Math.floor(-0.0));                   // -0.0
~~~

These methods can return a `double` with very large values beyond `long` limits without needing to cast to an integer, since the return type itself remains `double`.

### 8.2. round Converts to a Finite-Range Integer Type

`Math.round(double)` returns `long`; `Math.round(float)` returns `int`. They have well-defined rules when the input cannot round into the target integer range:

- `NaN` → `0` (`int` or `long` depending on overload).
- `+Infinity` or values too large positively → `Integer.MAX_VALUE` / `Long.MAX_VALUE`.
- `-Infinity` or values too large negatively → `Integer.MIN_VALUE` / `Long.MIN_VALUE`.
- `-0.0` → `0` (cannot preserve zero sign).

~~~java
System.out.println(Math.round(Double.NaN));             // 0
System.out.println(Math.round(Double.POSITIVE_INFINITY)); // 9223372036854775807
System.out.println(Math.round(Double.NEGATIVE_INFINITY)); // -9223372036854775808
System.out.println(Math.round(Float.POSITIVE_INFINITY)); // 2147483647
System.out.println(Math.round(Float.NEGATIVE_INFINITY)); // -2147483648
~~~

**Risk:** `Math.round` **does not report an error** on `NaN` or out-of-range numbers; it can return 0 or an extreme value of the integer type. If 0, `Integer.MAX_VALUE`, or `Long.MAX_VALUE` are valid business values, you could silently accept corrupt numbers undetected.

For user/configuration data, check `Double.isFinite` or `Float.isFinite`, range bounds, and rounding rules before storing results.

### 8.3. Precision Loss Before Rounding

`double` has about 53 significant bits of precision. Integers larger than `2^53` are not always represented exactly, so `Math.round` **cannot recover** digits lost when a decimal string or calculation was previously rounded to binary64.

~~~java
double input = Double.parseDouble("9007199254740993");
System.out.println(input);          // 9.007199254740992E15
System.out.println(Math.round(input)); // 9007199254740992
~~~

If data must be an exact integer, prefer `Long.parseLong` or `BigInteger` from the **original string**, rather than parsing to `double` and rounding.

## 9. ceil/floor/rint vs. Casting: Completely Different Goals

Java casting from `double` to `int`/`long` converts to the integer range; for finite values with fractional parts in normal range, the fractional part is truncated **toward 0**.

~~~java
double positive = 2.8;
double negative = -2.8;

System.out.println((int) positive);  // 2
System.out.println((int) negative);  // -2
System.out.println(Math.floor(negative)); // -3.0
System.out.println(Math.ceil(negative));  // -2.0
~~~

Do not use `(int) Math.ceil(x)` when x's range is unknown; the result of `ceil` is still `double` and the cast step handles extremes/NaN via conversion rules, losing information. If you want an `int` result from rounding, validate finiteness, range, and semantics first.

### Choosing floor for Cell Indices on a Negative Axis

Suppose you divide a plane into cells of width 10, and the cell containing `x` is indexed by `floor(x / 10)`:

~~~java
double coordinate = -1.0;
int cell = (int) Math.floor(coordinate / 10.0);
System.out.println(cell); // -1
~~~

If replaced with `(int) (coordinate / 10.0)`, you get 0, breaking the region semantics on the negative side. This example uses a small controlled range; for coordinates outside `int` range, validate before casting.

## 10. Complete Java 17+ Program with Exact Output

Create file `RoundingMethodsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingMethodsDemo {
    private static void compare(double x) {
        System.out.println(
                "x=" + x +
                " ceil=" + Math.ceil(x) +
                " floor=" + Math.floor(x) +
                " rint=" + Math.rint(x) +
                " round=" + Math.round(x));
    }

    public static void main(String[] args) {
        compare(2.5);
        compare(3.5);
        compare(-2.5);
        compare(-3.5);
        compare(-0.5);

        System.out.println("round(float)=" + Math.round(2.5f));
        System.out.println("round(double)=" + Math.round(2.5));
        System.out.println("rint(2.5)=" + Math.rint(2.5));

        System.out.println("round(NaN)=" + Math.round(Double.NaN));
        System.out.println("round(+Infinity)=" +
                Math.round(Double.POSITIVE_INFINITY));
        System.out.println("round(-Infinity)=" +
                Math.round(Double.NEGATIVE_INFINITY));

        System.out.println("ceil(-0.3)=" + Math.ceil(-0.3));
        System.out.println("strict rint=" + StrictMath.rint(2.5));

        BigDecimal tie = new BigDecimal("-2.5");
        System.out.println("HALF_UP=" +
                tie.setScale(0, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN=" +
                tie.setScale(0, RoundingMode.HALF_EVEN));
    }
}
~~~

Compile on Java 17:

~~~bash
javac --release 17 RoundingMethodsDemo.java
java RoundingMethodsDemo
~~~

Stdout:

~~~text
x=2.5 ceil=3.0 floor=2.0 rint=2.0 round=3
x=3.5 ceil=4.0 floor=3.0 rint=4.0 round=4
x=-2.5 ceil=-2.0 floor=-3.0 rint=-2.0 round=-2
x=-3.5 ceil=-3.0 floor=-4.0 rint=-4.0 round=-3
x=-0.5 ceil=-0.0 floor=-1.0 rint=-0.0 round=0
round(float)=3
round(double)=3
rint(2.5)=2.0
round(NaN)=0
round(+Infinity)=9223372036854775807
round(-Infinity)=-9223372036854775808
ceil(-0.3)=-0.0
strict rint=2.0
HALF_UP=-3
HALF_EVEN=-2
~~~

Explanation:

1. For `2.5`, `rint` returns 2.0 by choosing even; `round` returns 3 due to positive direction on ties.
2. For `-3.5`, `rint` returns −4.0 (even), whereas `round` returns −3 (positive side).
3. For `-0.5`, `ceil` and `rint` preserve negative zero sign; `round` returns integer 0.
4. `Math.round(double)` has type `long` and cannot represent `NaN`/`Infinity`; results are specified as 0 or the corresponding limits.
5. `StrictMath.rint(2.5)` follows the same ties-to-even rule.
6. `RoundingMode.HALF_UP` rounds midpoints **away from 0**, so −2.5 becomes −3; `RoundingMode.HALF_EVEN` picks even, so −2.5 becomes −2.

This is a standalone program using `Math`, `StrictMath`, and `BigDecimal` on Java 17. It does not depend on locale or OS settings for how numbers print in the expressions above.

## 11. StrictMath vs. Math for These Four Methods

Both classes reside in `java.lang`, so no extra import is needed:

~~~java
double a = Math.ceil(-1.2);
double b = StrictMath.ceil(-1.2);

double c = Math.rint(2.5);
double d = StrictMath.rint(2.5);

long e = Math.round(-2.5);
long f = StrictMath.round(-2.5);
~~~

`StrictMath` was designed with strict cross-platform result reproducibility requirements, which is especially important for many complex mathematical functions. However, for **ceil, floor, rint, and round**, result rules are clearly defined by the API; there is no "secret rounding policy" differing between `Math` and `StrictMath` in these examples.

| Name | Math | StrictMath | Notable Differences |
| --- | --- | --- | --- |
| `ceil(double)` | Yes | Yes | Same definition toward +∞ |
| `floor(double)` | Yes | Yes | Same definition toward −∞ |
| `rint(double)` | Yes | Yes | Same ties-to-even |
| `round(float)` | Yes | Yes | Same `int` type and ties-to-positive-infinity |
| `round(double)` | Yes | Yes | Same `long` type and ties-to-positive-infinity |

Do not guess that `StrictMath` is "always slower" or "always more accurate" in every environment. Performance depends on JDK/JVM/hardware, and these rounding functions have specifically defined semantics. Choose APIs based on system requirements and measure with representative benchmarks if speed is a concern.

## 12. Rounding Decimals: Avoid Misusing Math.round

A commonly seen pattern for rounding to two decimal places:

~~~java
double x = 1.005;
double result = Math.round(x * 100.0) / 100.0;
~~~

This approach **does not guarantee** the decimal result users expect:

- Many decimal numbers are not represented accurately by `double`.
- Multiplying `x * 100.0` can also round, so a value that appears to be at a tie may not actually equal the exact tie in binary64.
- At very large magnitudes, multiplying by a scale factor can overflow.
- For negative exact ties, `Math.round`'s rule is ties to +∞, not round half away from 0 as in many financial policies.
- The final result is still a `double`, so formatting to two digits for display does not mean the data is stored with fixed decimal precision.

If **exact decimal** rounding is required, parse directly from the decimal string into `BigDecimal` and choose a `RoundingMode`.

~~~java
BigDecimal price = new BigDecimal("1.005");
BigDecimal halfUp = price.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = price.setScale(2, RoundingMode.HALF_EVEN);

System.out.println(halfUp);   // 1.01
System.out.println(halfEven); // 1.00
~~~

Note that `new BigDecimal("1.005")` preserves the exact decimal value `1.005`. Conversely, `new BigDecimal(1.005)` constructs a `BigDecimal` from the already approximated binary64 value, which can cause different rounding results. If the source data is a user-entered string, use the original string.

## 13. BigDecimal Modes vs. Math

Related `RoundingMode` modes:

| Mode | Behavior on Non-Integers | Example 2.5 | Example −2.5 |
| --- | --- | --- | --- |
| `CEILING` | Toward `+∞` | 3 | −2 |
| `FLOOR` | Toward `-∞` | 2 | −3 |
| `DOWN` | **Toward 0** | 2 | −2 |
| `UP` | **Away from 0** | 3 | −3 |
| `HALF_UP` | Nearest; ties **away from 0** | 3 | −3 |
| `HALF_DOWN` | Nearest; ties **toward 0** | 2 | −2 |
| `HALF_EVEN` | Nearest; ties pick **even** value | 2 | −2 |
| `UNNECESSARY` | Reject if rounding needed | Error | Error |

This table shows rounding to **scale 0** using `BigDecimal.setScale(0, mode)`.

### Similarities and Differences

- `Math.ceil(x)` has a direction equivalent to `RoundingMode.CEILING` (though data type and representation differ).
- `Math.floor(x)` has a direction equivalent to `RoundingMode.FLOOR`.
- `Math.rint(x)` aligns closely with `HALF_EVEN` at integer values.
- `Math.round(x)` **has no single standalone `RoundingMode` name equivalent for both positive and negative numbers**: on ties, it always prefers **+∞**, whereas `HALF_UP` prefers **away from 0**.

Choose the rounding policy according to business requirements such as tax regulations, invoicing, statistics, or signal processing, not merely because a method name is easy to remember.

## 14. Not Every double Input Has a Meaningful "Fractional Part"

At very large magnitudes, the spacing between representable `double` values can be **2, 4, 8, or more**, so every value around there is already a mathematical integer in binary64 representation. `Math.ceil`, `Math.floor`, or `Math.rint` will not add precision on their own.

Example:

~~~java
double large = 1e20;
System.out.println(Math.rint(large) == large); // true
~~~

Even though `large` is already a mathematical integer in binary64, it **exceeds the `long` range**. Therefore:

~~~java
System.out.println(Math.round(1e20)); // 9223372036854775807
~~~

The result above is **`Long.MAX_VALUE`**, not `100000000000000000000`, because `Math.round(double)` only returns `long`.

Bottom line: "already rounded to an integer" and "can fit in the target integer type" are **two different questions**.

## 15. Rounding in Calculations vs. Rounding for Display

If the goal is solely to **display** 2 decimal places, formatting with `NumberFormat`/`DecimalFormat` or `String.format` using the chosen locale and rounding mode can be more appropriate than altering the computed value.

Example with `BigDecimal`:

~~~java
BigDecimal amount = new BigDecimal("12.345");
String display = amount.setScale(2, RoundingMode.HALF_EVEN).toPlainString();
System.out.println(display); // 12.34
~~~

When handling money, using `BigDecimal` or storing integers in the smallest unit is a common design choice. **Do not round at every intermediate calculation step** unless business rules mandate it; repeated rounding can accumulate error.

If only displaying, keep internal calculation values at appropriate precision and format at the output boundary. If an API specifies "two-decimal-place number" as an actual data invariant, enforce `scale`/representation at input and storage boundaries.

## 16. Common Mistakes

| Misconception | Issue | Fix |
| --- | --- | --- |
| "ceil always increases absolute value" | For negative numbers, ceil moves toward +∞, bringing them closer to 0 | Understand the definition `ceil(x) >= x` |
| "floor truncates the fractional part" | For negative numbers, `floor(-2.8)=-3` while cast gives −2 | Pick `floor` or cast for the right goal |
| "rint and round are the same" | Differ in tie rule and return type | `rint` ties-even; `round` ties +∞ |
| "round is half-away-from-zero" | `round(-2.5)=-2` | Use `BigDecimal.HALF_UP` when away from 0 is needed |
| "round returns double" | `round(float)` returns int, `round(double)` returns long | Check the exact overload |
| "rint returns int" | `rint` returns double | Convert with range checks |
| "round(NaN) throws an error" | Returns 0, which can hide bad data | Check `isFinite` beforehand |
| "round(Infinity) throws an error" | Returns int/long extreme bounds | Check range beforehand |
| "ceil/floor/rint(NaN) becomes 0" | Returns NaN | Check special values |
| "−0.0 is identical to +0.0" | `==` is true but sign bits differ | Decide whether to preserve zero sign |
| "Math.round helps parse large integers" | `double` can lose digits first | Parse `long`/`BigInteger` from string |
| "multiplying by 100 then round is always decimal-exact" | Binary64 error/overflow | Use `BigDecimal(String)` and `setScale` |
| "HALF_UP equals Math.round for negative numbers" | HALF_UP goes away from 0, Math.round prefers +∞ | Check policy at ties |
| "Math and StrictMath have different tie rules" | Both APIs share published rounding semantics | Read each method's contract |

## 17. Self-Check Questions

**Question 1.** What are the results of `Math.ceil(-4.2)` and `Math.floor(-4.2)`?

**Answer:** `-4.0` and `-5.0`. Ceil goes toward +∞; floor goes toward −∞.

**Question 2.** Why is `Math.rint(2.5)` equal to `2.0`, while `Math.round(2.5)` is `3`?

**Answer:** `rint` chooses the **even** integer on ties; `round` chooses the integer toward **+∞** on ties. Also `rint` returns double, while `round(double)` returns long.

**Question 3.** Does `Math.round(-2.5)` equal `-3` like `HALF_UP`?

**Answer:** No. `Math.round(-2.5)` equals `-2`, whereas `new BigDecimal("-2.5").setScale(0, HALF_UP)` equals `-3`.

**Question 4.** Why is `Math.round(Double.NaN)` dangerous if used to process input data?

**Answer:** It returns `0L` instead of failing, which can mask an invalid value. Check `Double.isFinite` before rounding.

**Question 5.** Why does `Math.round(1e20)` not return the mathematical integer value \(10^{20}\)?

**Answer:** `Math.round(double)` returns `long`, and \(10^{20}\) exceeds `Long.MAX_VALUE`, so the result clamps to `Long.MAX_VALUE`.

**Question 6.** Decimal data `"1.005"` needs rounding to two decimal places with `HALF_UP`. What should be used?

**Answer:** `new BigDecimal("1.005").setScale(2, RoundingMode.HALF_UP)` yields `1.01`; do not rely on `Math.round(x*100)/100` when decimal precision is required.

**Question 7.** What are the results of `Math.rint(-0.5)` and `Math.round(-0.5)`?

**Answer:** `-0.0` (double) and `0` (long). `rint` can preserve zero sign; `round` returns an integer type without negative zero.

## 18. Summary and References

Remember four short lines:

1. **`ceil`:** to the integer **above** on the number line (`+∞`).
2. **`floor`:** to the integer **below** on the number line (`-∞`).
3. **`rint`:** nearest integer, **ties to even**, returns `double`.
4. **`round`:** nearest integer, **ties toward positive**, returns `int` or `long`.

For strict data, check `NaN`/`Infinity`, target type bounds, and accuracy requirements **before** rounding. For decimal numbers needing clear and exact rounding rules, prefer `BigDecimal` with `RoundingMode`. Do not confuse rounding **computed values** with formatting **display strings**.

Official sources:

- [Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): definitions of `ceil`, `floor`, `rint`, `round`, and special-value handling.
- [Java SE 17 — StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): corresponding methods and reproducibility.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): `HALF_UP`, `HALF_EVEN`, `CEILING`, `FLOOR`, and other modes.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `setScale` and decimal precision.
- [JLS Java SE 17 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): precision, NaN, infinity, and signed zero.
