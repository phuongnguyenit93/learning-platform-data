# Do Not Assume `Math.round` Equals Every `HALF_UP` Mode

## 1. Key Points to Remember

In Java, **`Math.round` is not another name for `RoundingMode.HALF_UP`**. The two mechanisms can produce the same result in many cases, yet they **differ at exact-half points when the value is negative**, differ in input/output data types, precision handling, and special values.

- `Math.round(float)` returns `int`; `Math.round(double)` returns `long`. It selects **the nearest integer**, and if lying exactly halfway between two integers, it chooses the larger one, meaning **toward positive infinity** (`+∞`).
- `RoundingMode.HALF_UP` is a rounding rule used with APIs such as `BigDecimal.setScale`, `divide`, or `MathContext`. It chooses the nearest result; if **exact halfway**, it chooses the result **farther from 0**.
- `Math.round(-1.5) == -1` whereas `new BigDecimal("-1.5").setScale(0, RoundingMode.HALF_UP)` gives `-2`. This counterexample suffices to disprove the claim that the two mechanisms are equivalent.

The goal is to choose the **business rule** first and then choose the API, rather than looking at a few positive examples and generalizing to all inputs.

## 2. The Rule at Exact Halfway: Where Exactly Do They Differ?

Consider rounding a number to an integer: the two adjacent integers are equidistant at inputs of `n + 0.5`.

With `Math.round`, at the exact halfway point Java picks the numerically larger integer. For example, `-2` is greater than `-3`, so `Math.round(-2.5)` gives `-2`.

With `HALF_UP`, "UP" in the name of `RoundingMode` **does not mean increasing value toward `+∞`**. It means **increasing absolute magnitude, i.e., moving away from 0** on exact halves. Therefore, `-2.5` becomes `-3`.

| Input value | `Math.round(double)` | `BigDecimal.setScale(0, HALF_UP)` | Remark |
| ---: | ---: | ---: | --- |
| `2.4` | `2` | `2` | Both choose the nearest integer. |
| `2.5` | `3` | `3` | Positive exact half: matching result. |
| `1.5` | `2` | `2` | Positive exact half: matching result. |
| `0.5` | `1` | `1` | Positive exact half: matching result. |
| `-0.5` | `0` | `-1` | Negative exact half: **different**. |
| `-1.5` | `-1` | `-2` | Negative exact half: **different**. |
| `-2.5` | `-2` | `-3` | Negative exact half: **different**. |
| `-2.4` | `-2` | `-2` | Not exact half: both choose the nearest integer. |

The `.5` inputs in the table are exactly representable in `double`, so this difference truly stems from **the tie-breaking policy**, not floating-point error.

You cannot explain `Math.round(x)` as "always round up" because `Math.round(2.1) == 2`, nor can you say it always rounds toward 0 because `Math.round(-1.6) == -2`. The complete rule is: **nearest integer; on a tie, choose the larger number**.

A simple way to remember: for finite inputs whose result is within the representable range and free from floating-point addition precision subtleties, `Math.round`'s rule acts like rounding to the nearest integer with ties breaking toward `+∞`. Do not replace the entire implementation with the floating-point formula `(long)Math.floor(x + 0.5)`: the addition `x + 0.5` is also subject to binary rounding, and casting/range clamping have separate rules.

## 3. Distinguishing Easily Confused `RoundingMode` Values

For a fair comparison, set the same target **scale = 0** in `BigDecimal` (no remaining decimal places):

| Mode | Rule at exact halfway | `2.5` | `-2.5` |
| --- | --- | ---: | ---: |
| `HALF_UP` | Away from 0 | `3` | `-3` |
| `HALF_DOWN` | Toward 0 | `2` | `-2` |
| `HALF_EVEN` | Choose the even neighbor | `2` | `-2` |
| `UP` | Away from 0 for any non-zero fraction | `3` | `-3` |
| `DOWN` | Toward 0 for any non-zero fraction | `2` | `-2` |
| `CEILING` | Toward `+∞` | `3` | `-2` |
| `FLOOR` | Toward `-∞` | `2` | `-3` |

Note that `CEILING` is also not a general substitute for `Math.round`: `CEILING` turns `2.1` into `3`, whereas `Math.round(2.1)` returns `2`. Likewise, `FLOOR` is not nearest-rounding because `Math.floor(-1.1) == -2.0`.

`HALF_EVEN` chooses the even number only on exact halves: `2.5 → 2`, `3.5 → 4`, `-2.5 → -2`, `-3.5 → -4`. It does not share the same rule as `Math.round`, and even though `Math.rint(double)` resolves ties to even integers, it **returns a `double`**, can preserve the sign of zero, and still suffers from binary representation limitations.

The phrase "round up" in conversation is often ambiguous: it could mean `UP` (away from 0), `CEILING` (toward `+∞`), or `HALF_UP` (handling half points only). In code, use **specific mode names** instead of vague phrases.

## 4. Differences in API and Data Types

### 4.1. `Math.round` Returns a Fixed Integer Type

The two standard overloads are:

~~~java
int nearestInt = Math.round(2.5f);    // float -> int
long nearestLong = Math.round(2.5d);  // double -> long
~~~

`Math.round` does not accept a `RoundingMode` or number of decimal places. It rounds to **an integer**; there is no standard `Math.round(x, 2)` version in the JDK for rounding to two decimal places.

Returning `int`/`long` also has **range overflow** consequences: out-of-bounds results are clamped at the corresponding extrema, unable to carry all digits of the input. This is neither an exact arithmetic check nor an out-of-range error reporting mechanism.

### 4.2. `BigDecimal` Can Round by Scale or Precision

~~~java
BigDecimal amount = new BigDecimal("-2.5");
BigDecimal asInteger = amount.setScale(0, RoundingMode.HALF_UP);
// -3: returns a new BigDecimal, amount is unchanged.

BigDecimal price = new BigDecimal("12.345");
BigDecimal cents = price.setScale(2, RoundingMode.HALF_UP);
// 12.35: exactly two digits after the decimal point.
~~~

`setScale(2, ...)` requests **two decimal places** (scale 2). Meanwhile:

~~~java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal result = new BigDecimal("123.45").round(mc);
// 123: keeps 3 significant digits, not 3 digits after the decimal point.
~~~

`MathContext` limits **the result's significant digits**, so `round(mc)` with precision 3 is equivalent neither to `setScale(3, ...)` nor to `Math.round`.

In decimal source examples, prefer `new BigDecimal("...")` to preserve exact textual values. When the input is already a `double`, `BigDecimal.valueOf(value)` converts using the canonical decimal representation of `Double.toString(value)`; that is a value based on the **existing double**, unable to recover information lost in earlier calculations. Meanwhile, `new BigDecimal(value)` represents the exact binary value of `double`, which can produce an unexpectedly long decimal string.

## 5. Runnable Java 17+ Program and Output

Create the file `RoundingComparison.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingComparison {
    public static void main(String[] args) {
        double[] examples = {
                2.5, -2.5, 2.4, -2.4,
                1.5, -1.5, 0.5, -0.5
        };

        for (double value : examples) {
            BigDecimal decimal = BigDecimal.valueOf(value);

            System.out.println(value
                    + " | Math.round=" + Math.round(value)
                    + " | HALF_UP=" + decimal.setScale(0, RoundingMode.HALF_UP)
                    + " | HALF_EVEN=" + decimal.setScale(0, RoundingMode.HALF_EVEN));
        }

        System.out.println("float -> int: " + Math.round(2.5f));
        System.out.println("double -> long: " + Math.round(2.5d));

        System.out.println("NaN: " + Math.round(Double.NaN));
        System.out.println("+Infinity: " + Math.round(Double.POSITIVE_INFINITY));
        System.out.println("-Infinity: " + Math.round(Double.NEGATIVE_INFINITY));
        System.out.println("large: " + Math.round(1e30));

        double scaled = 1.005 * 100;
        System.out.println("scaled = " + scaled);
        System.out.println("scaled Math.round = " + Math.round(scaled) / 100.0);

        System.out.println("decimal HALF_UP = "
                + new BigDecimal("1.005")
                    .setScale(2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("decimal HALF_EVEN = "
                + new BigDecimal("1.005")
                    .setScale(2, RoundingMode.HALF_EVEN).toPlainString());

        System.out.println("rint 2.5=" + Math.rint(2.5)
                + ", rint -1.5=" + Math.rint(-1.5));
    }
}
~~~

Run:

~~~bash
javac RoundingComparison.java
java RoundingComparison
~~~

Output:

~~~text
2.5 | Math.round=3 | HALF_UP=3 | HALF_EVEN=2
-2.5 | Math.round=-2 | HALF_UP=-3 | HALF_EVEN=-2
2.4 | Math.round=2 | HALF_UP=2 | HALF_EVEN=2
-2.4 | Math.round=-2 | HALF_UP=-2 | HALF_EVEN=-2
1.5 | Math.round=2 | HALF_UP=2 | HALF_EVEN=2
-1.5 | Math.round=-1 | HALF_UP=-2 | HALF_EVEN=-2
0.5 | Math.round=1 | HALF_UP=1 | HALF_EVEN=0
-0.5 | Math.round=0 | HALF_UP=-1 | HALF_EVEN=0
float -> int: 3
double -> long: 3
NaN: 0
+Infinity: 9223372036854775807
-Infinity: -9223372036854775808
large: 9223372036854775807
scaled = 100.49999999999999
scaled Math.round = 1.0
decimal HALF_UP = 1.01
decimal HALF_EVEN = 1.00
rint 2.5=2.0, rint -1.5=-2.0
~~~

**Reading the output:** The four rows `-2.5`, `-1.5`, `-0.5`, and `0.5` show the different rounding policies. The `0.5` row also helps distinguish `HALF_UP` from `HALF_EVEN`. `Math.rint` is an extra example of the "tie to even" rule; it also differs in return type from `Math.round`.

## 6. Tricky Point: Binary `double` Makes Perceived ".5" Not Exactly .5

Decimal numbers like `0.1` and `1.005` generally **have no exact representation in `double`**. Thus the result of multiplication or division before rounding may lie slightly above or below the decimal tie point that the human eye expects.

A common idiom for getting two digits after the decimal point:

~~~java
double rounded = Math.round(1.005 * 100) / 100.0;
~~~

The program above shows:

~~~text
scaled = 100.49999999999999
scaled Math.round = 1.0
decimal HALF_UP = 1.01
~~~

`1.005 * 100` in `double` produces `100.49999999999999`, **less than 100.5**, so `Math.round` returns `100` and after division gives `1.0`. Conversely, `new BigDecimal("1.005")` preserves the exact decimal input, so `setScale(2, HALF_UP)` returns `1.01`. These are **two separate issues**:

1. **Tie-breaking rule:** `Math.round` picks toward `+∞`; `HALF_UP` picks away from 0.
2. **Input representation:** `double` operations can cause a decimal tie point to no longer lie at exact half.

One cannot conclude every `Math.round(value * 100) / 100.0` expression is wrong: it may be acceptable when an approximate `double` result is fine, the range is small, and the tie rule is agreed upon. However, for monetary prices or decimal rounding regulations, this approach usually fails to express the business contract accurately, not to mention `int`/`long` overflow risk when multiplying by large factors.

When using `BigDecimal` for money or contractually decimal quantities, clearly determine: **where the input comes from, how many digits after the decimal point, which rounding mode, and at which step**. For example:

~~~java
BigDecimal amount = new BigDecimal("1.005");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
// 1.01
~~~

If earlier operations already ran on `double` and lost precision, merely converting to `BigDecimal` at the final step **does not guarantee** recovering the original decimal value.

## 7. `NaN`, Infinity, Very Large Numbers, and Negative Zero

Java documentation specifies special cases for `Math.round`:

- Input `NaN` → `0`.
- `Math.round(double)` with `+Infinity` or too large positive values → `Long.MAX_VALUE`; with `-Infinity` or too large negative values → `Long.MIN_VALUE`.
- `Math.round(float)` applies similarly with `Integer.MAX_VALUE` and `Integer.MIN_VALUE`.
- `Math.round(-0.0)` returns integer `0`; integer types do not retain the sign of zero.

These are **specified return values**, not exceptions and not proof that the input is valid for business logic. For example, `Math.round(Double.NaN) == 0` can lose the signal of invalid data if you treat `0` as a normal number.

Need an input rounded exactly to `long`? With `BigDecimal`, after rounding with the chosen mode, `longValueExact()` throws `ArithmeticException` if the value cannot be represented exactly as a `long`. You can explicitly check `Double.isFinite(value)` before sending a `double` through a pipeline. Choose an explicit policy for infinity, `NaN`, and out-of-range values instead of relying implicitly on `Math.round`'s clamping behavior.

## 8. Choosing an Option Based on Requirements

| Requirement | Usually suitable API | Points to verify |
| --- | --- | --- |
| `float`/`double` value to nearest integer, exact half toward `+∞` | `Math.round(value)` | Returns `int` or `long`; check `NaN`, infinity, and out-of-range if data requires. |
| Decimal exact half **away from 0** | `BigDecimal.setScale(scale, HALF_UP)` | Scale and how `BigDecimal` is created must reflect intended input. |
| Decimal exact half toward 0 | `setScale(scale, HALF_DOWN)` | Differs from `Math.round` at positive half points. |
| Decimal exact half choosing even digit | `setScale(scale, HALF_EVEN)` | Use when business contract allows; do not default for every app. |
| Any fraction rounded toward `+∞` | `CEILING` or `Math.ceil` depending on input type | Differs from rounding to nearest number. |
| Round to 2 digits **after the decimal point** | `setScale(2, mode)` | Do not confuse with `MathContext(2, mode)` which is 2 significant digits. |
| Keep max significant digits in decimal operations | `MathContext(precision, mode)` | Precision differs from scale; not equivalent to `Math.round`. |
| Must detect unintended rounding | `setScale(scale, UNNECESSARY)` | Throws exception if a non-zero digit would be dropped. |

Case of converting from rounded decimal to integer type:

~~~java
BigDecimal input = new BigDecimal("-2.5");
long result = input.setScale(0, RoundingMode.HALF_UP).longValueExact();
// result == -3L
~~~

This snippet must sit inside a valid class/method with `java.math` imports; this is an **illustrative snippet**, not a standalone program.

## 9. Review Checklist and Common Mistakes

1. **Testing only positive numbers** like `1.5`, `2.5` and concluding `Math.round == HALF_UP`. You must test at least `-0.5`, `-1.5`, `-2.5`.
2. **Reading "UP" as toward larger numbers.** `HALF_UP` moves away from 0 on exact halves; `CEILING` is what moves toward `+∞`.
3. **Writing `Math.round(x * 100) / 100` and assuming a decimal two-place result.** `/ 100` with two integer operands performs integer division; `/ 100.0` produces a `double`, still carrying binary error.
4. **Assuming `Math.round` accepts arbitrary precision.** It only rounds `float`/`double` to `int`/`long`.
5. **Ignoring `NaN`, infinity, or range overflow.** The API returns 0/extrema instead of throwing errors, which can mask anomalous data.
6. **Using `new BigDecimal(double)` unconditionally.** This constructor reflects the exact binary value of `double`, not necessarily the decimal string a user sees.
7. **Comparing `Math.round` with `setScale(2)` and blaming differences on rounding mode.** Align the rounding target (in the opening example, scale 0) before comparing.
8. **Rounding at every step unintentionally.** Results can differ from rounding once at the end; clearly specify when rounding occurs.
9. **Confusing `Math.rint` with `Math.round`.** Both accept `double`, yet `rint` returns `double` and chooses even on ties, while `round` returns `long` and chooses toward `+∞` on ties.

## 10. Self-Check Exercises

**Exercise 1.** Predict `Math.round(-3.5)` and `new BigDecimal("-3.5").setScale(0, HALF_UP)`.

**Answer:** `-3` and `-4`. The input is equidistant from `-3` and `-4`, yet they choose opposite directions.

**Exercise 2.** Are these two expressions always equivalent?

~~~java
Math.round(x)
BigDecimal.valueOf(x).setScale(0, RoundingMode.HALF_UP)
~~~

**Answer:** No. They differ on negative exact-half values; in addition, they differ in return type and handling of special values, numeric range, and precision/representation.

**Exercise 3.** Why can `Math.round(1.005 * 100) / 100.0` produce `1.0`, while `new BigDecimal("1.005").setScale(2, HALF_UP)` gives `1.01`?

**Answer:** Multiplication on `double` yields `100.49999999999999`, smaller than the half point `100.5`; whereas the decimal string in `BigDecimal` keeps the value `1.005` exactly.

**Exercise 4.** To round `-2.5` to `-2` under the rule of picking the nearest integer with ties toward `+∞`, which API should be called?

**Answer:** `Math.round(-2.5d)`. If expressing the rule for decimals, you can compute with `BigDecimal` using a solution that selects the appropriate mode conditionally; do not default to calling `HALF_UP`.

## 11. Java Documentation for Reference

- [`Math.round(float)`, `Math.round(double)` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#round(double)): defines nearest integer and tie-breaking toward `+∞`; special cases.
- [`RoundingMode` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): describes `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`, `UP`, `DOWN`, `CEILING`, and `FLOOR`.
- [`BigDecimal` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `setScale`, `round`, `valueOf`, and `longValueExact`.

**Takeaway:** `Math.round` = nearest, **ties toward `+∞`**; `HALF_UP` = nearest, **ties away from 0**. For negative numbers at `.5` points, results often differ. Also control data types and binary representation before using one rounding operation in place of another.