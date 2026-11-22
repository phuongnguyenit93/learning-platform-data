# `BigDecimal.floatValue()`, `doubleValue()`: Conversion, Rounding, and Infinity

## 1. Meaning of Converting to Binary Floating-Point

`BigDecimal` accurately represents a decimal value with a finite number of digits via an unscaled value and a scale; whereas `float` and `double` are two IEEE 754 binary floating-point types. The two methods:

~~~java
BigDecimal amount = new BigDecimal("12.5");
float f = amount.floatValue();
double d = amount.doubleValue();
~~~

return the corresponding primitive numeric value. This is a **numeric value conversion**, not string formatting and not an operation with `MathContext`.

Valid `BigDecimal` data can encounter four situations during type conversion:

1. **Exact conversion:** numbers like `0.5`, `12.5`, or small integers can be represented exactly in binary.
2. **Rounded:** numbers like `0.1` have no strictly exact finite binary representation.
3. **Overflow:** the magnitude is too large, so the result becomes `Infinity` or `-Infinity`.
4. **Underflow:** an extremely small magnitude is rounded to a *subnormal* number, `0.0`, or `-0.0`.

Both methods allow precision loss or producing infinity. **They do not throw `ArithmeticException` merely because rounding is needed or the range is exceeded.** This differs from `BigDecimal` operations that enforce explicit rounding constraints.

## 2. How Do Precision and Range Differ?

| Property | `BigDecimal` | `float` | `double` |
| --- | --- | --- | --- |
| Representation | Unscaled integer × 10^(-scale) | IEEE 754 binary32 | IEEE 754 binary64 |
| Significant precision | Depends on value and memory | 24 binary bits | 53 binary bits |
| Approximate significant decimal digits | Unbounded | 6–9 | 15–17 |
| Has `NaN` and `Infinity` | No | Yes | Yes |
| Distinguishes signed zero | No | Yes | Yes |
| Represents decimal `0.1` exactly | Yes | No | No |

`float` has a finite value range up to approximately `3.4028235E38`, and `double` up to approximately `1.7976931348623157E308`. A wider range does not mean infinite precision: `double` still has only 53 significant bits.

Core mechanism: the conversion maps the decimal value onto the set of representable binary values, choosing the result according to binary round-to-nearest, and on exact ties choosing the value whose significand's least significant bit is even (*ties to even*). The spacing between representable numbers increases as their magnitude grows.

### 2.1. When `0.1` Still Prints as `0.1`

~~~java
BigDecimal decimal = new BigDecimal("0.1");
double binary = decimal.doubleValue();
System.out.println(binary); // 0.1
~~~

The output `0.1` **does not prove the conversion preserved the value**. `Double.toString` returns a short decimal representation that parses back to the same `double` value. The true binary value of `binary`, when converted back exactly to `BigDecimal`, is:

~~~text
0.1000000000000000055511151231257827021181583404541015625
~~~

This can be observed with:

~~~java
double binary = new BigDecimal("0.1").doubleValue();
System.out.println(new BigDecimal(binary).toPlainString());
~~~

`new BigDecimal("0.1")` is the exact decimal number 0.1 as written in text. `new BigDecimal(binary)` instead describes **the binary value stored** in the `double` variable; these two objects do not have the same mathematical value. Therefore, you must separate **the printed string** from **numeric accuracy**.

## 3. Rounding When Converting to `float` or `double`

### 3.1. Example with `float`: Losing One Unit on a Large Integer

~~~java
BigDecimal n = new BigDecimal("16777217");
float f = n.floatValue();
double d = n.doubleValue();

System.out.println(f); // 1.6777216E7 = 16777216
System.out.println(d); // 1.6777217E7 = 16777217
~~~

`16_777_216 = 2^24` is a key threshold: `float` can still represent that number accurately, but cannot represent every consecutive integer beyond it. The value `16_777_217` lies halfway between two adjacent `float` values `16_777_216` and `16_777_218`. The ties-to-even rule turns it into `16_777_216`.

`double` has higher precision so it still holds `16_777_217` accurately. That **does not mean every integer is exact in `double`**.

### 3.2. Example with `double`: Exceeding Consecutive Integer Limit

~~~java
BigDecimal n = new BigDecimal("9007199254740993");
System.out.println(n.doubleValue());
// 9.007199254740992E15 = 9007199254740992
~~~

`9_007_199_254_740_992 = 2^53` is the corresponding threshold for `double`. The number `2^53 + 1` cannot be represented exactly; after conversion, the value drops by one.

### 3.3. Not Only Integers Are Affected

A finite decimal number such as `0.1` often has an infinitely repeating binary fraction. Thus, even at very small magnitudes nowhere near overflow, conversion can still round.

Distinguish two types of limits:

- **Precision limit:** the value remains finite but differs slightly from the source due to rounding.
- **Range limit:** the result can become infinity or zero/subnormal.

If exact decimal digits must be preserved in monetary calculations, taxes, regulated interest rates, or accounting figures, keep `BigDecimal` throughout the calculation pipeline.

## 4. Overflow: A Finite `BigDecimal` Can Become Infinity

For values larger than the finite magnitude representable by the target type, `floatValue()` and `doubleValue()` can return `Infinity` or `-Infinity`:

~~~java
BigDecimal big = new BigDecimal("1E39");

System.out.println(big.floatValue());  // Infinity
System.out.println(big.doubleValue()); // 1.0E39

BigDecimal huge = new BigDecimal("1E309");
System.out.println(huge.doubleValue()); // Infinity

BigDecimal negativeHuge = new BigDecimal("-1E309");
System.out.println(negativeHuge.doubleValue()); // -Infinity
~~~

`1E39` exceeds the finite range of `float` while remaining within `double`'s range. `1E309` exceeds even `double`'s range. This is **overflow during type conversion**, not `BigDecimal` itself holding infinity.

`BigDecimal` has no `NaN` or infinity value. `new BigDecimal("Infinity")`, `new BigDecimal(Double.POSITIVE_INFINITY)`, and `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` all fail to construct a valid `BigDecimal` object and throw `NumberFormatException`.

When the target API forbids non-finite numbers, check **after conversion**:

~~~java
double converted = input.doubleValue();
if (!Double.isFinite(converted)) {
    throw new ArithmeticException("Value does not fit within finite double range");
}
~~~

This is a method snippet assuming `input` has type `BigDecimal`. `Double.isFinite` rejects `Infinity`, `-Infinity`, and `NaN`; converting a valid `BigDecimal` to `double` cannot itself produce `NaN`, yet this check is useful at system boundaries.

**Important:** `isFinite` only guarantees a finite result; it does not detect when `0.1` or a large integer was rounded to a different finite value.

## 5. Underflow: Subnormal Numbers and `0.0`/`-0.0` Results

Beyond the *normal* range, IEEE 754 also has a *subnormal* range that represents non-zero positive values smaller than the smallest positive normal number. If the source magnitude is even smaller than what can be represented after rounding, the result becomes zero.

| Constant | Meaning |
| --- | --- |
| `Float.MIN_NORMAL` | Smallest positive normal `float`, approximately `1.17549435E-38` |
| `Float.MIN_VALUE` | Smallest non-zero positive `float`, subnormal, approximately `1.4E-45` |
| `Double.MIN_NORMAL` | Smallest positive normal `double`, approximately `2.2250738585072014E-308` |
| `Double.MIN_VALUE` | Smallest non-zero positive `double`, subnormal, approximately `4.9E-324` |

Note that `MIN_VALUE` is **not the smallest negative number**. For `float`/`double`, it is the smallest non-zero positive magnitude.

~~~java
System.out.println(new BigDecimal("1E-50").doubleValue()); // 1.0E-50
System.out.println(new BigDecimal("1E-50").floatValue());  // 0.0

System.out.println(new BigDecimal("5E-324").doubleValue()); // 4.9E-324
System.out.println(new BigDecimal("1E-400").doubleValue()); // 0.0
System.out.println(new BigDecimal("-1E-400").doubleValue()); // -0.0
~~~

`5E-324` rounds to `Double.MIN_VALUE`, while `1E-400` becomes `0.0`. For `-1E-400`, the result is **zero with a negative sign bit**, printed as `-0.0`. Comparing `0.0` and `-0.0` with `==` yields `true`, yet their sign bits differ.

~~~java
double zero = new BigDecimal("-1E-400").doubleValue();
boolean negativeZero =
        Double.doubleToRawLongBits(zero) == Long.MIN_VALUE;
System.out.println(negativeZero); // true
~~~

`BigDecimal` itself does not distinguish negative zero from positive zero by sign bit like IEEE 754 does. So do not expect a round-trip through `BigDecimal` to preserve the `-0.0` bit representation when the mathematical value is 0.

**Underflow does not necessarily raise an exception.** It can be a serious business bug if a tiny non-zero number gets interpreted as zero (for example, probabilities, measurement factors, or scaling algorithms).

## 6. Standalone Runnable Java 17+ Example

Save the following as **BigDecimalFloatingConversionDemo.java**:

~~~java
import java.math.BigDecimal;

public class BigDecimalFloatingConversionDemo {
    private static void show(String text) {
        BigDecimal decimal = new BigDecimal(text);
        System.out.println(text
                + " -> double=" + decimal.doubleValue()
                + ", float=" + decimal.floatValue());
    }

    private static boolean exactAsDouble(BigDecimal original) {
        double converted = original.doubleValue();
        return Double.isFinite(converted)
                && original.compareTo(new BigDecimal(converted)) == 0;
    }

    private static boolean exactAsFloat(BigDecimal original) {
        float converted = original.floatValue();
        return Float.isFinite(converted)
                && original.compareTo(
                        new BigDecimal((double) converted)) == 0;
    }

    public static void main(String[] args) {
        show("0.1");
        show("16777217");
        show("1E39");
        show("1E309");
        show("1E-50");
        show("-1E-400");
        show("5E-324");

        double value = new BigDecimal("0.1").doubleValue();
        System.out.println("exact binary double decimal: "
                + new BigDecimal(value).toPlainString());
        System.out.println("shortest roundtrip decimal: "
                + BigDecimal.valueOf(value).toPlainString());

        System.out.println("0.1 exact double? "
                + exactAsDouble(new BigDecimal("0.1")));
        System.out.println("0.5 exact double? "
                + exactAsDouble(new BigDecimal("0.5")));
        System.out.println("16777217 exact float? "
                + exactAsFloat(new BigDecimal("16777217")));
        System.out.println("16777216 exact float? "
                + exactAsFloat(new BigDecimal("16777216")));

        double tinyNegative = new BigDecimal("-1E-400").doubleValue();
        System.out.println("negative zero bits? "
                + (Double.doubleToRawLongBits(tinyNegative)
                        == Long.MIN_VALUE));
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalFloatingConversionDemo.java
java BigDecimalFloatingConversionDemo
~~~

Exact output:

~~~text
0.1 -> double=0.1, float=0.1
16777217 -> double=1.6777217E7, float=1.6777216E7
1E39 -> double=1.0E39, float=Infinity
1E309 -> double=Infinity, float=Infinity
1E-50 -> double=1.0E-50, float=0.0
-1E-400 -> double=-0.0, float=-0.0
5E-324 -> double=4.9E-324, float=0.0
exact binary double decimal: 0.1000000000000000055511151231257827021181583404541015625
shortest roundtrip decimal: 0.1
0.1 exact double? false
0.5 exact double? true
16777217 exact float? false
16777216 exact float? true
negative zero bits? true
~~~

In the program, `show` prints both target-type results simultaneously for the same `BigDecimal`. The `exactAsDouble` and `exactAsFloat` methods perform the next verification step: instead of just looking at the printed value, they compare the **true binary value** against the source `BigDecimal`.

## 7. Checking Whether the Conversion Is Exact

The `exactAsDouble` method in the example applies these steps:

1. Call `doubleValue()`.
2. Check `Double.isFinite` to reject infinity (and NaN if the source were another floating-point type).
3. Use `new BigDecimal(converted)` to reconstruct the exact finite binary value as a decimal.
4. Compare with `compareTo` against the original `BigDecimal`. If it equals 0, the mathematical value was preserved.

For `float`, widening the resulting `float` to `double` before passing it to the `BigDecimal` constructor is valid: every finite `float` is represented accurately by `double`. Widening the type here loses no further data, though **it cannot restore digits already lost when converting from `BigDecimal` to `float`**.

These methods check **value exactness**, not preservation of `scale`, trailing zeros, or input text. `BigDecimal("12.500")` and `BigDecimal("12.5")` are equal under `compareTo`, even though their scales and `equals` results differ.

### 7.1. Why Not Use `BigDecimal.valueOf(double)` for Checking?

~~~java
BigDecimal source = new BigDecimal("0.1");
double d = source.doubleValue();

System.out.println(source.compareTo(BigDecimal.valueOf(d))); // 0
System.out.println(source.compareTo(new BigDecimal(d)));      // -1
~~~

The two results differ because:

- `BigDecimal.valueOf(d)` is based on the short decimal form `Double.toString(d)`, which is normally the form that round-trips back to the same `double` value (here, `0.1`).
- `new BigDecimal(d)` retains the exact actual binary value of `double` as a full decimal.

The `double` value corresponding to `0.1` is slightly **greater than** exact decimal 0.1, so `source.compareTo(new BigDecimal(d))` returns `-1`. **Comparing against `valueOf` can give a false "equal" result if the goal is to catch every conversion discrepancy.**

Do not call `new BigDecimal(Double.POSITIVE_INFINITY)`: that constructor only accepts finite values; check `isFinite` first.

### 7.2. Conversion Method That Only Accepts Exact `double` Values

~~~java
public static double requireExactDouble(BigDecimal input) {
    double value = input.doubleValue();
    if (!Double.isFinite(value)
            || input.compareTo(new BigDecimal(value)) != 0) {
        throw new ArithmeticException("Precision loss when converting to double");
    }
    return value;
}
~~~

This is an **illustrative method to place inside a class that imports `java.math.BigDecimal`**, not a standalone program. It accepts `0.5` and rejects `0.1`, out-of-range numbers, or tiny numbers that round to 0.

If data can be `null`, define how to handle it before calling `input.doubleValue()`; otherwise it will throw `NullPointerException`.

`BigDecimal` has no standard `doubleValueExact()` or `floatValueExact()` methods analogous to `intValueExact()` and `longValueExact()`. If the application requires converting to binary floating-point **without precision loss**, perform manual verification or design the interface to accept `BigDecimal`.

## 8. Choosing a Conversion Policy by Problem Requirements

| Business Requirement | Approach |
| --- | --- |
| Approximation is acceptable in calculations | Use `doubleValue()` or `floatValue()` once error bounds are understood |
| Result must be finite | After conversion, check `Double.isFinite`/`Float.isFinite` |
| Mathematical value must be preserved | Check `isFinite` then compare against `new BigDecimal(converted)` |
| Original scale/digits must be preserved | Continue using `BigDecimal`; validate scale and format separately |
| Monetary or decimal numbers needing accuracy | Compute with `BigDecimal` end-to-end, converting only at API boundaries that truly require it |
| Detect underflow from non-zero to zero | Compare source value against converted value; check zero when specific errors are needed |

**Do not confuse `RoundingMode.UNNECESSARY` with checking `double` conversion.** For example:

~~~java
BigDecimal x = new BigDecimal("0.10")
        .setScale(2, java.math.RoundingMode.UNNECESSARY);
double d = x.doubleValue();
~~~

`setScale(2, UNNECESSARY)` succeeds because that decimal number can be represented at scale 2 without changing its value. Yet `d` is still a binary approximation of 0.1. These are two exactness conditions in **different number bases**.

## 9. Common Mistakes

| Symptom or Misconception | Reality |
| --- | --- |
| Prints `0.1`, so decimal `0.1` must have been preserved accurately | `Double.toString` returns a short form; inspect `new BigDecimal(double)` to see the binary value |
| With `double`, every integer is exact | For very large integers, the gap between consecutive `double` values exceeds 1 |
| Converting a finite `BigDecimal` cannot produce `Infinity` | Overflow can yield `Infinity` or `-Infinity` without throwing an error |
| Underflow can only produce positive 0 | Sufficiently small negative values can become `-0.0` |
| `Float.MIN_VALUE` is the most negative number | It is the **smallest non-zero positive** number, in the subnormal range |
| `Double.isFinite` confirms exact precision | It only rules out non-finite values |
| `BigDecimal.valueOf(double)` always reproduces all binary digits of `double` | It uses the short decimal representation; the `double` constructor gives the exact representation |
| Widening a rounded `float` to `double` recovers lost digits | Lost digits cannot be recovered by casting |
| No exception means the conversion lost no information | Precision loss, overflow, and underflow can all occur during a successful conversion |

## 10. Self-Check

1. Is `new BigDecimal("0.5").doubleValue()` exact? **Yes:** `0.5 = 1/2` is represented exactly in binary.
2. Is `new BigDecimal("0.1").doubleValue()` equal to the exact decimal number 0.1? **No:** the nearest binary value is only an approximation.
3. What value does `new BigDecimal("16777217").floatValue()` produce? **16_777_216**, due to the 24-bit precision limit and rounding rule.
4. Are `new BigDecimal("1E39").floatValue()` and `doubleValue()` the same? **No:** the results are `Infinity` and `1.0E39`, respectively.
5. What does `new BigDecimal("1E-50").floatValue()` return? **`0.0`**, while `doubleValue()` remains `1.0E-50`.
6. When the returned value is `0.0`, can you conclude the source `BigDecimal` was 0? **No:** non-zero values can underflow to zero.
7. Does `Double.isFinite` verify digit-for-digit accuracy? **No:** it only checks that the result is finite.
8. To verify that a conversion to `double` preserved the value, what object do you compare against? **`new BigDecimal(result)`**, with a finite `result`; not just `BigDecimal.valueOf(result)`.

**Conclusion:** `floatValue()` and `doubleValue()` are conversions to binary floating-point numbers that can **round, overflow to infinity, or underflow to subnormal/zero**. Choose types according to your data contract, check `isFinite` when needed, and compare against the **true binary value** if preserving the exact value is mandatory.
