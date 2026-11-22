# Confusing Precision with Decimal Places in Java `BigDecimal`

## 1. The Core Mistake

In Java, **precision** and **scale** of `BigDecimal` are two distinct concepts:

- **Precision (significant digits):** the number of significant digits in the decimal representation of the unscaled value. `BigDecimal.precision()` returns the digit count of the unscaled value, ignoring sign; zero itself has precision 1.
- **Scale:** the exponent adjusting the decimal point position in `unscaledValue × 10^(-scale)`. For ordinary decimal notation with a non-negative scale, scale corresponds to the number of digits after the decimal point in the **current representation**. Scale can also be negative.

For example, `new BigDecimal("123.4500")` has **precision = 7** and **scale = 4**, not precision = 4. When writing `new MathContext(3, HALF_UP)`, the number 3 does **not** mean "keep three digits after the decimal point"; it means "at most three significant digits".

Compare:

~~~java
BigDecimal number = new BigDecimal("1234.567");
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(number.round(mc));                         // 1.23E+3
System.out.println(number.setScale(3, RoundingMode.HALF_UP));  // 1234.567
~~~

This is an **illustrative snippet requiring `import java.math.*` and placement inside a method**; the standalone runnable program is in Section 9.

Both calls contain the number 3, yet they mean completely different things:

- `round(mc)`: keeps only three significant digits, so 1234.567 becomes roughly 1230, printed as `1.23E+3`.
- `setScale(3, ...)`: requires three digits after the decimal point, which `1234.567` already has, so no rounding occurs.

**How to remember:** `MathContext` controls **the number of significant digits of the entire result**; `setScale` controls **the decimal point position / fractional digit count of the representation**.

## 2. Fundamental Formula: `unscaledValue`, Scale, and Precision

A `BigDecimal` consists of an unscaled integer and an integer scale:

~~~text
numericValue = unscaledValue × 10^(-scale)
~~~

Examples:

| Input String | Unscaled value | Scale | Precision |
| --- | ---: | ---: | ---: |
| `"12"` | 12 | 0 | 2 |
| `"12.0"` | 120 | 1 | 3 |
| `"12.00"` | 1200 | 2 | 4 |
| `"123.4500"` | 1234500 | 4 | 7 |
| `"0.00120"` | 120 | 5 | 3 |
| `"0.0000"` | 0 | 4 | 1 |
| `"1E+3"` | 1 | -3 | 1 |

Reading the table accurately:

1. `"0.00120"` has 5 places after the decimal point yet only **3 significant digits**: 1, 2, and the trailing 0. Leading zeros before digit 1 only establish the decimal point position.
2. `"123.4500"` has **7 significant digits** in its unscaled value 1234500. Trailing zeros are still digits stored in the representation and count toward the current object's precision.
3. `"1E+3"` has mathematical value 1000 yet scale **-3**: `1 × 10^3`. You cannot define scale simply by "counting after the dot" on `toString()`.
4. Zero has precision 1, yet can have many different scales. `"0"` and `"0.0000"` are equal in value, not in scale.

Do not guess precision or scale merely from magnitude, and do not discard trailing zeros if the data contract needs to preserve them.

### 2.1. `toString()` Does Not Always Produce Plain Decimal Format

After rounding or normalization, `BigDecimal.toString()` may use scientific notation such as `1.23E+3`. This does not mean the number turned into `double`, nor is it a calculation bug; it is `BigDecimal`'s text format for its current precision and scale.

`toPlainString()` produces a string without exponent notation. However, do not inspect display strings to determine precision or scale; call `precision()` and `scale()` directly.

## 3. Object `precision()` vs. Precision in `MathContext`

The two occurrences of "precision" are related yet play different roles:

- `value.precision()` **reads the current state** of a `BigDecimal`: how many significant digits are currently stored in its unscaled value.
- `new MathContext(p, mode)` **sets a precision cap for results of operations using that context**, where `p > 0` is the maximum number of significant digits.

Example:

~~~java
BigDecimal value = new BigDecimal("123.4500");
System.out.println(value.precision()); // 7
System.out.println(value.scale());     // 4

BigDecimal rounded = value.round(
        new MathContext(4, RoundingMode.HALF_UP));
System.out.println(rounded);            // 123.5
System.out.println(rounded.precision()); // 4
System.out.println(rounded.scale());     // 1
~~~

`MathContext` does not merely "set a metadata flag". When an exact result has more significant digits than the limit, `BigDecimal` **rounds the value** according to the rounding mode. Sometimes rounding only drops trailing zeros without changing numeric value; other times rounding genuinely alters the number.

### 3.1. Precision = 0 in `MathContext`

~~~java
MathContext unlimited = MathContext.UNLIMITED;
// unlimited.getPrecision() == 0
~~~

Precision 0 in `MathContext` means **unlimited significant digits**, not "keep 0 digits" and not "keep 0 digits after the decimal point". It does not magically give non-terminating decimal operations, such as `1 ÷ 3`, a finite exact `BigDecimal` representation.

`MathContext.DECIMAL32`, `DECIMAL64`, and `DECIMAL128` have precisions 7, 16, and 34 respectively, using `HALF_EVEN`. They likewise control **significant digits**, not scales of 7/16/34.

## 4. `setScale()`: Rules for Decimal Point Position

When the requirement is "a value with **exact two digits after the decimal point**", you typically use:

~~~java
BigDecimal stored = value.setScale(2, RoundingMode.HALF_EVEN);
~~~

`setScale(2, ...)` returns a `BigDecimal` with scale exactly 2 or throws an exception if that cannot be achieved under the specified rule. In standard notation, the result has exactly two decimal places when printed in scale-2 form.

Examples:

| Initial Value | Call | Result |
| --- | --- | --- |
| `12` | `setScale(2, HALF_UP)` | `12.00` |
| `12.3` | `setScale(2, HALF_UP)` | `12.30` |
| `12.345` | `setScale(2, HALF_UP)` | `12.35` |
| `12.345` | `setScale(2, HALF_EVEN)` | `12.34` |
| `-1.236` | `setScale(2, HALF_UP)` | `-1.24` |
| `12.3400` | `setScale(2, UNNECESSARY)` | `12.34` |

`setScale` can increase scale by appending zeros without changing numeric value; when decreasing scale, it must drop digits and may need to round. Therefore, specify the **rounding mode** per business requirements, not just the scale.

If changing the value is forbidden, use `RoundingMode.UNNECESSARY`:

~~~java
BigDecimal exact = new BigDecimal("12.3400")
        .setScale(2, RoundingMode.UNNECESSARY); // 12.34

// Throws ArithmeticException if executed:
// new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
~~~

**`UNNECESSARY` does not mean rounding down or ignoring digits:** it requires the scale adjustment to be **exact**, otherwise failing with an error.

## 5. `round(new MathContext(...))`: Capping Significant Digits

Consider the same number under both transformations:

| Input | Precision 3 with `HALF_UP` | Scale 3 with `HALF_UP` |
| --- | --- | --- |
| `1234.567` | `1.23E+3` (= 1230) | `1234.567` |
| `0.0012345` | `0.00123` | `0.001` |
| `9.995` | `10.0` | `9.995` |
| `12.34` | `12.3` | `12.340` |

Why does `0.0012345` with precision 3 become `0.00123`? Leading zeros before the digit 1 do not consume precision. Meanwhile, `setScale(3)` allows only three digits after the decimal point, so it must round to `0.001`.

### 5.1. Carries Change Integer Length and Scale

Example:

~~~java
BigDecimal value = new BigDecimal("9.995");
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal rounded = value.round(mc);
System.out.println(rounded);             // 10.0
System.out.println(rounded.precision());  // 3
System.out.println(rounded.scale());      // 1

BigDecimal scaled = value.setScale(2, RoundingMode.HALF_UP);
System.out.println(scaled);              // 10.00
System.out.println(scaled.precision());   // 4
System.out.println(scaled.scale());       // 2
~~~

Both have numeric value 10 after rounding, yet **the precision and scale of the results differ**. They are not interchangeable in a contract requiring scale 2.

When rounding causes a carry from 9 to 10, the number of integer digits can increase. This matters greatly when checking database column limits, monetary value ranges, or report widths.

### 5.2. Trailing Zeros Still Affect Precision

~~~java
BigDecimal value = new BigDecimal("1000.00");
System.out.println(value.precision()); // 6
System.out.println(value.scale());     // 2

BigDecimal result = value.round(
        new MathContext(3, RoundingMode.HALF_UP));
System.out.println(result);            // 1.00E+3
~~~

In this example, rounding can **drop excess zero digits** without losing mathematical value. The result `1.00E+3` has precision 3 and scale -1, not scale 2.

If the requirement is to keep two digits after the decimal point in the output, **`MathContext(3)` does not fulfill that requirement**.

## 6. `MathContext` in Arithmetic Operations Is Not the Same as Final `setScale`

Several `BigDecimal` methods accept a `MathContext`:

~~~java
BigDecimal total = left.add(right, mc);
BigDecimal product = left.multiply(right, mc);
BigDecimal quotient = left.divide(right, mc);
~~~

When a context caps precision, **the result of each individual operation** can be rounded to the allowed significant digits. This differs from the strategy:

~~~java
BigDecimal exactTotal = left.add(right);
BigDecimal stored = exactTotal.setScale(2, RoundingMode.HALF_EVEN);
~~~

The first approach restricts **significant digits at every operation result**; the second computes the exact sum and then normalizes to **scale 2** per storage policy.

When adding many amounts, the two rules can yield different sums. For example, with `1.234 + 0.004 + 0.004` and `MathContext(3, HALF_UP)`:

- Exact addition yields `1.242`, then `round(mc)` gives `1.24`.
- Using `add(x, mc)` on **each addition** can yield `1.23`, because small increments are lost during intermediate rounding.

If the contract only states "the final total has two digits after the decimal point", never assume `new MathContext(2, ...)` expresses the same requirement. It would restrict the entire sum to just **two significant digits**, including integer digits.

### 6.1. Division Shows the Difference Even More Clearly

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");

BigDecimal byScale = one.divide(
        eight, 2, RoundingMode.HALF_UP); // 0.13

BigDecimal byPrecision = one.divide(
        eight, new MathContext(2, RoundingMode.HALF_UP)); // 0.13
~~~

The two results **happen to match in this division**. However, if you change the dividend or ratio, their meanings remain distinct: `divide(divisor, scale, mode)` selects the result scale; `divide(divisor, MathContext)` selects the result precision. Never conclude two overloads are equivalent from a single test case.

A clearer distinguishing example:

~~~java
BigDecimal numerator = new BigDecimal("1234");
BigDecimal denominator = new BigDecimal("8");

BigDecimal byScale = numerator.divide(
        denominator, 2, RoundingMode.HALF_UP); // 154.25

BigDecimal byPrecision = numerator.divide(
        denominator, new MathContext(2, RoundingMode.HALF_UP)); // 1.5E+2
~~~

With precision-2 context, 154.25 must be rounded down to 150, whereas scale 2 preserves the exact result 154.25.

## 7. Data Design: Precision and Scale in Databases

In many database management systems, `DECIMAL(p, s)` or `NUMERIC(p, s)` uses:

- `p`: total number of decimal digits allowed by the column definition.
- `s`: number of digits after the decimal point, per the DBMS/column definition.

Typically `DECIMAL(5,2)` allows values like `999.99`, whereas `1234.56` exceeds the maximum three integer digits of that format.

This **does not mean** using `new MathContext(5, ...)` guarantees compatibility with `DECIMAL(5,2)`. A context does not fix the scale and can alter the value. A two-step check under an explicit policy is needed:

~~~java
BigDecimal scaled = value.setScale(2, RoundingMode.UNNECESSARY);
if (scaled.precision() > 5) {
    throw new IllegalArgumentException("Value exceeds DECIMAL(5,2) limit");
}
~~~

This is an **illustrative snippet** that must be placed inside a method with a `BigDecimal value` variable. Under a contract forbidding rounding, `UNNECESSARY` ensures the value is not altered; then `precision() > 5` rejects values exceeding the total digit count of the normalized representation. If the application permits rounding before storage, a different policy applies the approved rounding mode prior to checking precision.

**Caution:** each database has its own rules for range limits, overflow handling, write-time rounding behavior, and negative scale support. Read the schema and verify against the actual database/driver. The example here expresses two independent checks, not a substitute for integration testing.

### 7.1. Overflow After Rounding

A value sitting right on the threshold can gain **more integer digits** after rounding. For example, when normalizing to scale 2, `999.995` with `HALF_UP` becomes `1000.00`. This post-rounding value no longer fits in a typical `DECIMAL(5,2)`, even though the source value looked close to the limit.

Therefore, check precision/value range **after applying the chosen scale rule**, not only before rounding.

## 8. Testing Against the Right Contract: Value, Scale, Precision, and Text

A good assertion suite distinguishes four conditions:

| Contract | Suggested Check |
| --- | --- |
| Mathematically equal values | `expected.compareTo(actual) == 0` |
| Both value and scale match | `expected.equals(actual)` or two separate assertions |
| Scale equals exactly 2 | `actual.scale() == 2` |
| Precision does not exceed 5 | `actual.precision() <= 5` after appropriate normalization |
| Wire string matches format `"12.00"` | Test serialized or formatted output separately |

JUnit 5 example (**place inside a test method and add JUnit dependencies**):

~~~java
BigDecimal actual = new BigDecimal("12.00");

assertEquals(0, new BigDecimal("12").compareTo(actual));
assertEquals(2, actual.scale());
assertTrue(actual.precision() <= 5);
~~~

These assertions use `org.junit.jupiter.api.Assertions.assertEquals` and `assertTrue`. They test three **separate** requirements. `actual.equals(new BigDecimal("12"))` would be `false` because their scales differ despite equal numeric values.

If a non-negative number with two decimal places is needed, beyond scale you must also check value bounds (e.g., `signum() >= 0`). Do not use precision/scale to infer all business constraints.

### 8.1. `stripTrailingZeros` Changes Precision and Scale

~~~java
BigDecimal raw = new BigDecimal("1000.00");
BigDecimal compact = raw.stripTrailingZeros();

System.out.println(compact);             // 1E+3
System.out.println(compact.precision()); // 1
System.out.println(compact.scale());     // -3
~~~

`stripTrailingZeros()` removes trailing zeros while preserving **mathematical value**. Thus it typically lowers both precision and scale; scale can become **negative**. It is not a method for setting "number of decimal places" and should not be used to mask a scale bug in an API promising `scale == 2`.

For zero, `stripTrailingZeros()` can return `BigDecimal.ZERO` with scale 0, even if the input was `0.0000`. If tests require preserving zero's scale, check that separately.

## 9. Complete Java 17+ Program

Create **PrecisionVsScaleDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionVsScaleDemo {
    private static void inspect(String label, BigDecimal value) {
        System.out.println(label + ": " + value
                + " (precision=" + value.precision()
                + ", scale=" + value.scale() + ")");
    }

    public static void main(String[] args) {
        inspect("literal", new BigDecimal("123.4500"));
        inspect("small", new BigDecimal("0.00120"));
        inspect("zero", new BigDecimal("0.0000"));
        inspect("scientific", new BigDecimal("1E+3"));

        BigDecimal original = new BigDecimal("1234.567");
        MathContext threeDigits =
                new MathContext(3, RoundingMode.HALF_UP);

        inspect("round precision3", original.round(threeDigits));
        inspect("set scale3",
                original.setScale(3, RoundingMode.HALF_UP));

        BigDecimal small = new BigDecimal("0.0012345");
        System.out.println("small precision3: "
                + small.round(threeDigits));
        System.out.println("small scale3: "
                + small.setScale(3, RoundingMode.HALF_UP));

        inspect("carry precision3",
                new BigDecimal("9.995").round(threeDigits));
        inspect("carry scale2",
                new BigDecimal("9.995")
                        .setScale(2, RoundingMode.HALF_UP));

        inspect("round trailing zeros",
                new BigDecimal("1000.00").round(threeDigits));

        BigDecimal a = new BigDecimal("12.0");
        BigDecimal b = new BigDecimal("12.00");
        System.out.println("same numeric value: "
                + (a.compareTo(b) == 0));
        System.out.println("same value and scale: "
                + a.equals(b));

        try {
            new BigDecimal("12.345")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("strict scale: ArithmeticException");
        }
    }
}
~~~

Run:

~~~bash
javac PrecisionVsScaleDemo.java
java PrecisionVsScaleDemo
~~~

Exact output:

~~~text
literal: 123.4500 (precision=7, scale=4)
small: 0.00120 (precision=3, scale=5)
zero: 0.0000 (precision=1, scale=4)
scientific: 1E+3 (precision=1, scale=-3)
round precision3: 1.23E+3 (precision=3, scale=-1)
set scale3: 1234.567 (precision=7, scale=3)
small precision3: 0.00123
small scale3: 0.001
carry precision3: 10.0 (precision=3, scale=1)
carry scale2: 10.00 (precision=4, scale=2)
round trailing zeros: 1.00E+3 (precision=3, scale=-1)
same numeric value: true
same value and scale: false
strict scale: ArithmeticException
~~~

This program uses only the Java standard library. The `inspect` lines demonstrate that the 3 in `MathContext` and the 3 in `setScale` affect **two distinct properties**. Notice that `9.995` after rounding has the same numeric value 10 yet is represented as `10.0` or `10.00` depending on the policy.

## 10. Rules for Choosing the Right API

### Want Exactly N Significant Digits

Use `MathContext`:

~~~java
MathContext mc = new MathContext(4, RoundingMode.HALF_EVEN);
BigDecimal rounded = value.round(mc);
~~~

This caps the result's **precision to at most 4**, without forcing scale to 4. It fits when the contract specifies results in significant digits, such as measurement reports or precision-bounded calculations.

### Want Exactly N Digits After the Decimal Point

Use `setScale`:

~~~java
BigDecimal scaled = value.setScale(2, RoundingMode.HALF_EVEN);
~~~

The result has **scale exactly 2** on success. It fits fixed-scale storage contracts, fixed-scale decimal displays, or monetary rules with well-defined rounding points.

### Want No Value Change Allowed

Specify `UNNECESSARY` in the corresponding normalization or operation:

~~~java
BigDecimal exactAtTwoPlaces =
        value.setScale(2, RoundingMode.UNNECESSARY);
~~~

If the value cannot be represented exactly at the requested scale, `ArithmeticException` is thrown. `UNNECESSARY` does not automatically enforce value bounds or integer digit counts.

### Want Both Scale 2 and Total Digit Limit

Normalize **according to the approved policy**, then check both scale and precision/range, for example:

~~~java
BigDecimal normalized =
        value.setScale(2, RoundingMode.UNNECESSARY);

if (normalized.precision() > 5) {
    throw new IllegalArgumentException("Precision exceeds 5");
}
~~~

If the contract permits rounding, replace `UNNECESSARY` with the approved mode and validate data **after** rounding. Never use `round(new MathContext(5, ...))` as a full replacement for checking `DECIMAL(5,2)`.

## 11. Common Mistakes

| Misconception | Correct Fact |
| --- | --- |
| `MathContext(2)` means two decimal places | Precision 2 means two significant digits across the entire result |
| `precision()` counts digits after the decimal point | It counts digits in the unscaled value, ignoring sign; zero has precision 1 |
| `scale()` is always non-negative | Scale can be negative, e.g. `1E+3` has scale -3 |
| `0.00120` has precision 5 | Precision is 3, while scale is 5 |
| Rounding only changes the fractional part | `MathContext` can round integer digits and switch to scientific notation |
| `setScale` only appends zeros | When decreasing scale, it can change the value per mode or throw an error |
| `UNNECESSARY` means skip rounding | It rejects any operation that would alter the value |
| `BigDecimal.toString()` always prints ordinary decimal point format | Can print exponential notation depending on scale and representation |
| Equal numeric value implies equal scale | `compareTo == 0` does not guarantee `equals == true` |
| `DECIMAL(5,2)` only needs `MathContext(5)` | Must check scale, precision, and DB bounds |
| `stripTrailingZeros()` sets scale to 0 | It can produce a negative scale and change zero's representation |

## 12. Self-Check

1. What is `new BigDecimal("123.4500").precision()`? **7**; scale is **4**.
2. Does `new BigDecimal("0.00120")` have precision 5 because it has 5 digits after the dot? **No**; precision is **3**, scale is **5**.
3. For `1234.567`, what do `MathContext(3, HALF_UP)` and `setScale(3, HALF_UP)` return respectively? **`1.23E+3`** and **`1234.567`**.
4. Why is `new BigDecimal("1E+3").scale()` equal to -3? **Value = 1 × 10^3**, so by formula scale is -3.
5. Does `new BigDecimal("12").setScale(2)` change the numeric value? **No**; it becomes `12.00` with scale 2.
6. Does `new BigDecimal("12.345").setScale(2, UNNECESSARY)` succeed? **No**; digit 5 would have to be dropped, so it throws `ArithmeticException`.
7. Why can `9.995` become `10.0` with precision 3, yet `10.00` with scale 2? **Two different representation constraints even though the rounded value is the same**.
8. If an API requires exact scale 2 and exact value, is `MathContext(2)` alone enough? **No**; use `setScale(2, UNNECESSARY)` or an equivalent check, along with any remaining constraints.
9. When two `BigDecimal`s have equal numeric value but different scales, how should you check them? **`compareTo == 0`** if the contract only cares about value; **`equals`** or separate scale checks if the contract requires both.

**Final takeaway:** **Precision = significant digits; scale = decimal point position in the representation.** Use `MathContext` when limiting operation precision, use `setScale` when fixing the number of decimal places, and verify both when the data contract demands it.
