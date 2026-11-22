# `BigDecimal.stripTrailingZeros()` Can Produce a Negative `scale`

## 1. The Issue to Understand

In Java, `BigDecimal.stripTrailingZeros()` removes unnecessary trailing `0` digits from the **end of the integer without a decimal point (unscaled value)** of a `BigDecimal` representation, while adjusting `scale` so the **arithmetic value remains unchanged**. Consequently, the result can have `scale < 0`, even when the original object had `scale = 0` or `scale > 0`.

For example:

~~~java
BigDecimal original = new BigDecimal("600.00");
BigDecimal normalized = original.stripTrailingZeros();

System.out.println(normalized);         // 6E+2
System.out.println(normalized.scale()); // -2
~~~

`6E+2` is still **600**. `scale = -2` does not indicate a negative number, overflow error, or loss of precision. It is a valid representation of the exact same `BigDecimal` value.

After this lesson, you should be able to explain the `unscaledValue/scale` transformation, distinguish value comparison from representation comparison, and choose appropriate formatting or normalization.

## 2. How Does `BigDecimal` Store Numbers?

Conceptually, a finite `BigDecimal` value is defined by:

\[
\text{value}=\text{unscaledValue}\times 10^{-\text{scale}}
\]

Where:

- `unscaledValue()` returns a `BigInteger` containing the significant digits along with the sign, before placing the decimal point.
- `scale()` is the number of digits to the right of the decimal point according to the formula above. `scale` can be **positive, zero, or negative**.
- `precision()` is the number of digits in `unscaledValue` in decimal representation (excluding the sign; the number `0` has precision 1).
- Two objects can have the same mathematical value yet differ in `unscaledValue`, `scale`, and `precision`.

Examples:

| Representation | `unscaledValue` | `scale` | Value |
| --- | ---: | ---: | ---: |
| `600.00` | `60000` | `2` | `600` |
| `600` | `600` | `0` | `600` |
| `6E+2` | `6` | `-2` | `600` |
| `0.001000` | `1000` | `6` | `0.001` |

With `6E+2`, the formula gives `6 × 10^(-(-2)) = 6 × 10² = 600`. Thus **a negative scale means the decimal point position is shifted to the right of the unscaled value**, equivalent to multiplying by a positive power of 10.

Note: `scale` is not the number of significant digits; to inspect significant digits, use `precision()`. Nor should `scale` be treated as a fixed display formatting rule across all operations.

## 3. Why Does `stripTrailingZeros()` Make `scale` Negative?

The method returns a numerically equivalent `BigDecimal` object by stripping trailing factors of 10 from `unscaledValue`. Each time a trailing `0` digit is removed from `unscaledValue`, `scale` decreases by 1 to keep the multiplication result unchanged.

With `new BigDecimal("600.00")`:

| Step | `unscaledValue` | `scale` | Value |
| --- | ---: | ---: | ---: |
| Initial | `60000` | `2` | `600.00` |
| Strip one `0` | `6000` | `1` | `600.0` |
| Strip another `0` | `600` | `0` | `600` |
| Strip next `0` | `60` | `-1` | `600` |
| Strip final `0` | `6` | `-2` | `600` |

The result has `unscaledValue = 6` and `scale = -2`. `toString()` represents it as `6E+2`.

A common confusion is that the method does not only delete zeros **after the decimal point in a display string**. It can also strip trailing zeros **at the end of an integer** when the unscaled representation has factors of 10.

Some typical results:

| Input `new BigDecimal("...")` | After `stripTrailingZeros()` (`toString()` form) | Result `scale` |
| --- | --- | ---: |
| `"125.000"` | `125` | `0` |
| `"120.3000"` | `120.3` | `1` |
| `"1000"` | `1E+3` | `-3` |
| `"600.00"` | `6E+2` | `-2` |
| `"0.001000"` | `0.001` | `3` |
| `"0.000"` | `0` | `0` |

**Zero is a special case:** `stripTrailingZeros()` returns the `BigDecimal.ZERO` representation with `scale = 0`, regardless of how many digits after the decimal point the original zero had. You cannot infer the result's `scale` simply by counting `0` digits in the input string.

`stripTrailingZeros()` is an **exact** transformation—no rounding, no `MathContext`, and it does not mutate the source object (since `BigDecimal` is immutable). Arithmetic accuracy is preserved; the representation's `precision()` may change.

## 4. Standalone Runnable Java 17+ Example

Save file under the name `BigDecimalNegativeScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalNegativeScaleDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("600.00");
        BigDecimal normalized = original.stripTrailingZeros();

        System.out.printf(
                "original: %s, unscaled=%s, scale=%d%n",
                original, original.unscaledValue(), original.scale()
        );
        System.out.printf(
                "normalized: %s, unscaled=%s, scale=%d%n",
                normalized, normalized.unscaledValue(), normalized.scale()
        );

        System.out.println("plain: " + normalized.toPlainString());
        System.out.println("equals: " + original.equals(normalized));
        System.out.println("compareTo: " + original.compareTo(normalized));
        System.out.println(
                "fixed scale 2: "
                        + normalized.setScale(2, RoundingMode.UNNECESSARY)
        );

        BigDecimal zero = new BigDecimal("0.000").stripTrailingZeros();
        System.out.printf("zero: %s, scale=%d%n", zero, zero.scale());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac BigDecimalNegativeScaleDemo.java
java BigDecimalNegativeScaleDemo
~~~

Stdout output:

~~~text
original: 600.00, unscaled=60000, scale=2
normalized: 6E+2, unscaled=6, scale=-2
plain: 600
equals: false
compareTo: 0
fixed scale 2: 600.00
zero: 0, scale=0
~~~

Explanation:

1. The original value `600.00` has `unscaledValue = 60000`, `scale = 2`; the normalized object has `unscaledValue = 6`, `scale = -2`.
2. `toString()` may use scientific notation (`6E+2`), whereas `toPlainString()` returns an ordinary decimal representation (`600`).
3. `equals()` returns `false` because the two objects differ in `scale` despite having the same arithmetic value.
4. `compareTo()` returns `0` because it compares **arithmetic value**.
5. `setScale(2, RoundingMode.UNNECESSARY)` creates a new object with `scale = 2` and value `600.00`; in this case it only adds zeros, needing no rounding.
6. Zero after stripping trailing zeros has `scale = 0`.

## 5. Important Consequences for `equals()`, `compareTo()`, and Hashing

`BigDecimal.equals(Object)` checks both **value** and **scale**. `BigDecimal.compareTo(BigDecimal)` compares arithmetic value, ignoring differences due only to scale.

~~~java
BigDecimal a = new BigDecimal("1000");
BigDecimal b = a.stripTrailingZeros(); // 1E+3; scale = -3

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

In `HashSet<BigDecimal>` and `HashMap<BigDecimal, ...>` keys, `equals()` and `hashCode()` determine key collisions. Hence, `1000` and `1E+3` can be **two separate keys**. In `TreeSet<BigDecimal>`, which uses natural `compareTo()` ordering, they are considered equivalent under ordering comparison.

This is not unique to negative `scale`; the `equals`/`compareTo` distinction already exists for `1.0` and `1.00`. Calling `stripTrailingZeros()` can make representation differences more visible.

If business logic requires comparing **monetary amounts or measurements**, normally use `compareTo() == 0`. If it requires matching the exact representation, including scale, use `equals()`. For hash-based collections, decide and apply a uniform input canonicalization rule while considering whether original scale must be preserved.

## 6. Distinguishing Value, Scale, and Display

Several APIs look similar yet solve different problems:

| API | Purpose | What to watch out for |
| --- | --- | --- |
| `stripTrailingZeros()` | Removes excess factors of 10 in representation | Can create negative scale and does not preserve original decimal digit count |
| `scale()` | Reads current scale | Negative scale is valid |
| `toString()` | Prints canonical representation; may use scientific notation | `new BigDecimal("600.00").stripTrailingZeros().toString()` is `6E+2` |
| `toPlainString()` | Prints ordinary decimal form, no scientific notation | Changes only the **display string**, not the object or scale |
| `setScale(n, mode)` | Creates a new object with specified scale | May require rounding, or throw if `UNNECESSARY` and rounding is needed |
| `compareTo()` | Compares arithmetic value | Does not require matching scales |
| `equals()` | Compares value and scale | Can return `false` for two numbers of equal value |

For instance, when you only want the string `"600"` instead of `"6E+2"`:

~~~java
BigDecimal x = new BigDecimal("600.00").stripTrailingZeros();
String plain = x.toPlainString(); // "600"; x.scale() is still -2
~~~

Do not confuse `toPlainString()` with internal data normalization: parsing `"600"` back with `new BigDecimal(plain)` creates an object with `scale = 0`, different from the original `scale = -2`. If data exchange requires preserving both representation and value, define the wire format clearly.

If a UI must always display two decimal places, specify formatting or scale rules at the presentation boundary; `stripTrailingZeros()` does not serve that requirement:

~~~java
BigDecimal amount = new BigDecimal("600.00");
BigDecimal fixed = amount.stripTrailingZeros()
                         .setScale(2, RoundingMode.UNNECESSARY);
// fixed.toPlainString() -> "600.00"
~~~

When changing `scale` on a number whose fractional part does not fit (e.g., `12.345` to scale 2), `RoundingMode.UNNECESSARY` throws `ArithmeticException` because a nonzero digit would have to be dropped. Choose a rounding policy per business requirements rather than arbitrarily discarding remainders.

## 7. Appropriate Usage in Practice

**Case A — only wanting display without scientific notation.** Use `toPlainString()` after normalization. Do not assume `scale >= 0`:

~~~java
BigDecimal value = new BigDecimal("1000").stripTrailingZeros();
System.out.println(value.toString());      // 1E+3
System.out.println(value.toPlainString()); // 1000
~~~

**Case B — needing a fixed scale per data contract.** Use `setScale(targetScale, roundingMode)` with a clearly decided rounding policy. For example, VND amounts without fractional units can use scale 0; currencies with two decimal digits can use scale 2 if the application actually uses that rule. Do not apply `stripTrailingZeros()` after setting scale if a fixed representation must be kept.

**Case C — checking if a number is an integer in value.** The following check is wrong for a round integer with negative scale:

~~~java
BigDecimal value = new BigDecimal("1000").stripTrailingZeros();
boolean wrong = value.scale() == 0; // false even though value is an integer
~~~

For finite `BigDecimal` values, after `stripTrailingZeros()`, the condition `scale() <= 0` identifies an integer value. When you actually need a `BigInteger` and want to verify exactness with no fractional part, use `toBigIntegerExact()`: it throws `ArithmeticException` if there is a nonzero fractional part.

**Case D — normalizing numbers for comparison or as keys.** Establish a consistent rule upon ingesting values. `stripTrailingZeros()` can be helpful when you accept discarding scale to unify representations of equal value (e.g., `1.0` and `1.00` both become `1`). However, this loses original scale information, so it is unsuitable if scale carries business meaning.

## 8. Common Mistakes and How to Avoid Them

1. **Assuming `stripTrailingZeros()` always yields `scale >= 0`.** A round number like `1000` becomes `1E+3` with `scale = -3`. Write code that accepts positive, zero, and negative scales.
2. **Thinking negative `scale` means a negative number or altered value.** Scale is the exponent in the representation formula; check value with `compareTo()`.
3. **Using `equals()` when only wanting value comparison.** `600.00` does not `equals` `6E+2` even though `compareTo() == 0`.
4. **Using `stripTrailingZeros()` to try to keep two decimal places for money.** The method does the opposite: it strips scale information not needed to preserve mathematical value. Specify scale or formatting separately.
5. **Thinking `toPlainString()` changes the object's scale.** It only generates a string; `x.scale()` does not change.
6. **Using `new BigDecimal(0.1)` to test decimals and blaming `stripTrailingZeros()`.** Binary `double` generally does not represent `0.1` exactly. When wanting an exact decimal literal, use `new BigDecimal("0.1")`; when receiving an existing `double`, consider `BigDecimal.valueOf(double)` per input contract.

## 9. Self-Check

Consider the code snippet:

~~~java
BigDecimal x = new BigDecimal("1200.00");
BigDecimal y = x.stripTrailingZeros();
~~~

Answer:

1. What are `x.unscaledValue()` and `x.scale()`?
2. What are `y.unscaledValue()`, `y.scale()`, `y.toString()`, and `y.toPlainString()`?
3. What do `x.equals(y)` and `x.compareTo(y)` return?
4. If an API requires exactly two digits after the decimal point, how should you handle `y`?

**Answers:** `x` has `unscaledValue = 120000` and `scale = 2`; `y` has `unscaledValue = 12`, `scale = -2`, `toString() = "1.2E+3"`, and `toPlainString() = "1200"`. `equals` is `false`, `compareTo` is `0`. To represent two decimal digits, use `y.setScale(2, RoundingMode.UNNECESSARY)` and `toPlainString()` when outputting a string, giving `"1200.00"`.

Key point: `stripTrailingZeros()` preserves **value** yet can change **representation**. When the reduced representation of a number contains powers of 10 in its integer part, negative `scale` is an exact result fully supported by `BigDecimal`.