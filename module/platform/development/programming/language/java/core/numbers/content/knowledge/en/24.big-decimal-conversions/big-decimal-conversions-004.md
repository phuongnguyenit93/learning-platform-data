# `BigDecimal.intValue()`, `longValue()`, and Potential Data Loss

## 1. Why Should You Thoroughly Understand Converting BigDecimal to Integers?

`BigDecimal` represents decimal numbers with arbitrary precision, whereas `int` holds only 32-bit signed integers and `long` holds only 64-bit signed integers. When you write:

~~~java
BigDecimal value = new BigDecimal("123.99");

int a = value.intValue();   // 123
long b = value.longValue(); // 123
~~~

Java **does not report an error** even though the `.99` part has vanished. These two methods perform a **lossy narrowing conversion**, not rounding according to a financial rule.

Even the integer part can be lost if it lies outside the target type's range:

~~~java
new BigDecimal("2147483648").intValue()  // -2147483648
new BigDecimal("4294967296").intValue()  // 0
~~~

Key points to remember:

- `intValue()` and `longValue()` **discard the fractional part toward zero**, and then narrow to the target type's bit width. They **do not check for data loss**.
- `intValueExact()` and `longValueExact()` **only return a result if the value is an exact integer and fits within the target type's range**; otherwise, they throw `ArithmeticException`.
- If business logic permits rounding, **explicitly choose a `RoundingMode` and round first**, then use the `...ValueExact()` methods to verify bounds.
- The fact that a program compiles or returns an `int`/`long` does not prove the conversion preserved the original value.

## 2. Two Independent Sources of Data Loss

### 2.1. Losing the Fractional Part: Truncating Toward Zero, Not Rounding

`intValue()` and `longValue()` drop the non-integer part. They keep only the integer part closest to zero:

| Input BigDecimal | `intValue()` | `longValue()` | What Is Lost |
| --- | ---: | ---: | --- |
| `123.999` | `123` | `123` | `0.999` |
| `-123.999` | `-123` | `-123` | `-0.999` |
| `0.999` | `0` | `0` | Entire non-zero value |
| `-0.999` | `0` | `0` | Entire non-zero value |
| `1.000` | `1` | `1` | No **numeric value** lost; only scale 3 is not retained |

For example, `new BigDecimal("-2.9").intValue()` is `-2`. This is **not** `Math.floor(-2.9)` (which gives `-3.0`), nor is it rounding to the nearest integer. The term "truncate" means **discarding the fractional part toward zero**.

`intValue()` and `longValue()` do not accept a `RoundingMode`. Modes like `HALF_UP`, `HALF_EVEN`, `DOWN`, and `FLOOR` only take effect if you actively use a rounding API such as `setScale`.

### 2.2. Losing Bits in the Integer Part: Numbers Can Flip Sign or Become 0

Java ranges for the two types:

| Type | Bit Width | Minimum Value | Maximum Value |
| --- | ---: | ---: | ---: |
| `int` | 32 | `-2147483648` | `2147483647` |
| `long` | 64 | `-9223372036854775808` | `9223372036854775807` |

After discarding the fractional part, if the integer part is too large or too small:

- `intValue()` keeps the **low 32 bits** of the integer part in two's complement representation, and interprets the result as a signed `int`.
- `longValue()` keeps the **low 64 bits** and interprets them as a signed `long`.
- No exception is thrown merely for exceeding the range; the resulting value can be completely different from the original number.

Examples:

| BigDecimal Value | `intValue()` | `longValue()` | Explanation |
| --- | ---: | ---: | --- |
| `2147483647` | `2147483647` | `2147483647` | Within range of both |
| `2147483648` | `-2147483648` | `2147483648` | Exceeds `int`, but fits `long` |
| `4294967296` (= 2^32) | `0` | `4294967296` | Low 32 bits are all 0 |
| `9223372036854775807` | `-1` | `9223372036854775807` | Fits `long`; low 32 bits are all 1s |
| `9223372036854775808` (= 2^63) | `0` | `-9223372036854775808` | Exceeds `long`, sign bit interpreted as negative |
| `18446744073709551616` (= 2^64) | `0` | `0` | Low 64 bits are all 0 |

Saying "keeps the low bits" here describes **the result according to the conversion specification**; you should not rely on assumptions about `BigDecimal`'s internal memory layout.

For example, `4294967296` becomes `0` because `4294967296 = 2^32`: keeping only the remainder modulo `2^32` yields 0. Negative numbers can also turn into positive ones: `new BigDecimal("-2147483649").intValue()` produces `2147483647`.

**Fractional truncation and bit loss can happen at the same time.** A number like `4294967296.75` loses `.75` first, and then turns the integer part `4294967296` into `0` when using `intValue()`.

## 3. Two Safer Methods: intValueExact and longValueExact

The `BigDecimal` API provides:

~~~java
int exactInt = value.intValueExact();
long exactLong = value.longValueExact();
~~~

They require **both conditions simultaneously**:

1. **The mathematical value must be an exact integer**: no non-zero fractional part may be discarded.
2. **The integer value must fit within the range** of `int` or `long`.

If either condition fails, `ArithmeticException` is thrown. Not every operation fails just because `scale() > 0`:

~~~java
new BigDecimal("1.000").intValueExact(); // 1: fractional part has value 0
new BigDecimal("1.001").intValueExact(); // ArithmeticException
~~~

`1.000` has scale 3, but its mathematical value is the integer 1. Therefore, **do not look only at the number of digits after the decimal point** to decide whether an exact conversion is possible.

Selection table:

| Input Data | `intValueExact()` | `longValueExact()` |
| --- | --- | --- |
| `123` | `123` | `123` |
| `1.000` | `1` | `1` |
| `123.999` | `ArithmeticException` | `ArithmeticException` |
| `2147483648` | `ArithmeticException` | `2147483648` |
| `9223372036854775807` | `ArithmeticException` | `9223372036854775807` |
| `9223372036854775808` | `ArithmeticException` | `ArithmeticException` |

If explicit error handling is needed in the application:

~~~java
BigDecimal input = new BigDecimal("123.99");

try {
    long converted = input.longValueExact();
    System.out.println(converted);
} catch (ArithmeticException ex) {
    System.out.println("Value has a fractional part or exceeds the long range");
}
~~~

This snippet sits inside an appropriate method or block with `import java.math.BigDecimal;`; the output will be the message line in the `catch` block. Specific JDK exception messages should not be used for business conditions, as they can vary by situation or version.

## 4. Complete Illustrative Java 17+ Program

Create a file named **`BigDecimalIntegerConversionDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalIntegerConversionDemo {
    public static void main(String[] args) {
        String[] samples = {
                "123.999",
                "-123.999",
                "2147483648",
                "4294967296",
                "9223372036854775808",
                "18446744073709551616",
                "1.000",
                "1.001"
        };

        for (String input : samples) {
            BigDecimal value = new BigDecimal(input);
            System.out.println(input
                    + " | int=" + value.intValue()
                    + " | long=" + value.longValue()
                    + " | intExact=" + exactInt(value)
                    + " | longExact=" + exactLong(value));
        }

        BigDecimal amount = new BigDecimal("12.75");
        System.out.println("truncate: " + amount.intValue());
        System.out.println("HALF_UP: "
                + amount.setScale(0, RoundingMode.HALF_UP).intValueExact());

        BigDecimal negative = new BigDecimal("-12.75");
        System.out.println("negative HALF_UP: "
                + negative.setScale(0, RoundingMode.HALF_UP).intValueExact());

        System.out.println("BigInteger trunc: "
                + new BigDecimal("1.999").toBigInteger());
    }

    private static String exactInt(BigDecimal value) {
        try {
            return Integer.toString(value.intValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    private static String exactLong(BigDecimal value) {
        try {
            return Long.toString(value.longValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalIntegerConversionDemo.java
java BigDecimalIntegerConversionDemo
~~~

Output:

~~~text
123.999 | int=123 | long=123 | intExact=ArithmeticException | longExact=ArithmeticException
-123.999 | int=-123 | long=-123 | intExact=ArithmeticException | longExact=ArithmeticException
2147483648 | int=-2147483648 | long=2147483648 | intExact=ArithmeticException | longExact=2147483648
4294967296 | int=0 | long=4294967296 | intExact=ArithmeticException | longExact=4294967296
9223372036854775808 | int=0 | long=-9223372036854775808 | intExact=ArithmeticException | longExact=ArithmeticException
18446744073709551616 | int=0 | long=0 | intExact=ArithmeticException | longExact=ArithmeticException
1.000 | int=1 | long=1 | intExact=1 | longExact=1
1.001 | int=1 | long=1 | intExact=ArithmeticException | longExact=ArithmeticException
truncate: 12
HALF_UP: 13
negative HALF_UP: -13
BigInteger trunc: 1
~~~

**How to read the output:** The `int` and `long` columns always display an integer value, even when severely inaccurate. The `intExact` and `longExact` columns make it clear which cases cannot be converted accurately. `2147483648` is a particularly useful test: `intValue()` flips to a negative number, `intValueExact()` reports an error, while `longValueExact()` succeeds because it still fits within 64 bits.

The program explicitly catches `ArithmeticException` in helper methods to demonstrate all cases in a single run. In production business code, it is usually better to **let the error propagate to the validation layer** or turn it into a validation error with appropriate input context, rather than silently returning a default value.

## 5. When Business Logic Genuinely Requires Rounding or Truncating Fractions

Choose the policy according to requirements, then clearly separate the **fractional-part handling step** from the **integer-range verification step**.

### 5.1. Rounding According to a Defined Rule

~~~java
BigDecimal amount = new BigDecimal("12.75");

int halfUp = amount
        .setScale(0, RoundingMode.HALF_UP)
        .intValueExact(); // 13
~~~

`setScale(0, HALF_UP)` is a business choice: round to the nearest integer, and when exactly halfway, round away from zero. Once the integer value has been produced via intentional rounding, `intValueExact()` further guarantees it lies within the `int` range.

Do not do the following if the goal is to compute the rounded integer:

~~~java
int wrongForRounding = new BigDecimal("12.75").intValue(); // 12, not 13
~~~

Example modes for `-12.75` at scale 0:

| Mode | Result |
| --- | ---: |
| `DOWN` | `-12` |
| `UP` | `-13` |
| `HALF_UP` | `-13` |
| `HALF_EVEN` | `-13` |
| `CEILING` | `-12` |
| `FLOOR` | `-13` |

For `-12.75`, several modes happen to return the same number. To distinguish modes at exact halfway points, test both `2.5` and `-2.5`. For instance, `HALF_EVEN` rounds `2.5` to `2`, while `HALF_UP` rounds it to `3`.

### 5.2. If Truncating Toward Zero Is Intentional, Still Check for Overflow

~~~java
BigDecimal quantity = new BigDecimal("-12.75");

long truncatedChecked = quantity
        .setScale(0, RoundingMode.DOWN)
        .longValueExact(); // -12
~~~

`RoundingMode.DOWN` means moving **toward zero**, not always decreasing the value. The result rounded to scale 0 is represented as an integer, and then `longValueExact()` verifies the range.

This approach is suitable when you want to maintain the policy of dropping the fractional part **while refusing to misconvert due to 64-bit overflow**. If you want to **forbid any non-zero fractional part**, do not use `DOWN`: call `longValueExact()` directly.

### 5.3. For Integers Larger Than long: Use BigInteger

If the problem genuinely needs an integer that may exceed `Long.MAX_VALUE`, do not force it into `long`:

~~~java
BigDecimal huge = new BigDecimal("9223372036854775808");

java.math.BigInteger whole = huge.toBigIntegerExact();
// 9223372036854775808, no data loss.
~~~

Distinguish:

- `toBigInteger()`: discards the fractional part (if any), with no 32/64-bit limit.
- `toBigIntegerExact()`: **rejects** any non-zero fractional part with `ArithmeticException`, still without the 32/64-bit limits of the two primitive integer types.
- `toBigInteger().intValue()`: ultimately **can still lose high bits**. Converting to `BigInteger` does not automatically make any subsequent cast to `int`/`long` safe.

For counts, sizes, or IDs that must strictly be integers, another option is to process the input string with `Integer.parseInt`, `Long.parseLong`, or `new BigInteger(text)`, according to the valid range and input format. There is no need to route through `BigDecimal` if business rules reject decimal numbers from the outset.

## 6. Display Value, Precision, Scale, and Conversion to Integer Types

A `BigDecimal` has **precision** (number of significant digits) and **scale** (number of decimal digits in its representation). `intValue()` and `longValue()` do not carry those two attributes into the integer type; the result is merely a primitive integer.

Example:

~~~java
BigDecimal input = new BigDecimal("00123.4500");

System.out.println(input);          // 123.4500
System.out.println(input.scale());  // 4
System.out.println(input.intValue()); // 123
~~~

Even though `00123.4500` was entered, the `BigDecimal` object no longer retains leading zeros in its canonical `toString()`. After calling `intValue()`, the fractional digits `.4500` are also lost. It is impossible to reverse-engineer `123` to tell whether the original value was `123.45`, `123.99`, or `123.000`.

Specifically:

~~~java
new BigDecimal("1.000").intValueExact(); // succeeds: 1
new BigDecimal("1.001").intValueExact(); // fails: has non-zero fractional part
~~~

Rounding when creating `BigDecimal` with a `MathContext` can also **lose data before** `intValueExact()` is called. For instance, if an input `1.001` was rounded to `1.0` in an earlier step, the Exact method in the later step can only inspect the **current** value and cannot detect the already-discarded fractional part. Therefore, validate input before any unintended rounding step.

## 7. Common Application Mistakes

**Mistake 1 — Converting currency amounts to `int` with `intValue()` and assuming it rounded.** With `12.75`, the result is `12`, causing discrepancies in reporting or accounting. Clearly define the unit (dong, cents, or smallest unit), rounding policy, and timing of rounding. If money must be represented in its smallest unit as an integer, multiply by the exact factor, round per contract, and then use `longValueExact()` to verify.

**Mistake 2 — Checking that a `BigDecimal` is non-negative and assuming converting to `int` will also be non-negative.** `2147483648` is positive, but `intValue()` turns negative due to range overflow. For non-lossy data like IDs or resource limits, use Exact conversions and check business domain bounds.

**Mistake 3 — Only checking value ≤ `Integer.MAX_VALUE`.** Besides the upper bound, there is a lower bound and the fractional part. Manual checks easily miss edge cases; `intValueExact()` solves both core conditions.

**Mistake 4 — Assuming `longValue()` is safe because `long` is very wide.** A `BigDecimal` can still exceed 64 bits; `9223372036854775808` converts to `long` as `Long.MIN_VALUE`.

**Mistake 5 — Catching every `ArithmeticException` and returning `0`.** `0` might be a valid value and mask corrupted data. Distinguish non-integer or out-of-range data per business requirements and preserve helpful error information.

**Mistake 6 — Using `setScale(0, DOWN)` when fractional parts are forbidden.** `DOWN` deliberately truncates the fractional part; call `intValueExact()` or `longValueExact()` directly if fractions must be rejected.

**Mistake 7 — Assuming converting from `double` to `BigDecimal` recovers the original value.** `new BigDecimal(double)` reflects the exact binary value of `double`, which may differ from the decimal number the user intended. When input is decimal text, prefer parsing from the exact string; do not ignore the data source before choosing a conversion method.

**Mistake 8 — Using `longValue()` to check whether a number fits in a long.** This method **always returns a `long`** with a value that may be wrong due to truncation/overflow. `longValueExact()` is the complete conversion check.

## 8. API Selection Checklist

| Need | Approach | Checks Fractional Part? | Checks int/long Range? |
| --- | --- | --- | --- |
| Accept fractional truncation and potential bit loss | `intValue()` / `longValue()` | No | No |
| Accept only integers fitting in `int` | `intValueExact()` | Yes | Yes, 32-bit |
| Accept only integers fitting in `long` | `longValueExact()` | Yes | Yes, 64-bit |
| Intentional rounding, then safe conversion | `setScale(0, mode).intValueExact()` or `...longValueExact()` | Rounds per selected mode | Yes |
| Truncate fractional part, disallow overflow | `setScale(0, DOWN).longValueExact()` | Intentionally truncates fraction | Yes |
| Preserve exact integer, even very large | `toBigIntegerExact()` | Yes | Not limited to 32/64 bits |
| Accept fractional truncation into BigInteger | `toBigInteger()` | No | Not limited to 32/64 bits |

During code review, ask yourself: **is discarding the fractional part allowed? Is a specific rounding rule required? Must the final value fit strictly within 32 or 64 bits?** If an invalid conversion must be caught, the `...ValueExact()` methods are the right default choice.

## 9. Practice Questions

**Question 1.** What is `new BigDecimal("-7.99").intValue()`? Is that rounding down (floor)?

**Answer:** `-7`. This is truncation toward zero; `FLOOR` rounding to an integer would be `-8`.

**Question 2.** Why is `new BigDecimal("4294967296").intValue()` equal to `0` while `longValue()` still gives `4294967296`?

**Answer:** `4294967296 = 2^32` exceeds the `int` range; all 32 low bits are 0. That value still fits within the `long` range.

**Question 3.** Does `new BigDecimal("4.000").intValueExact()` throw an error?

**Answer:** No, the result is `4` because the mathematical value is an integer. Scale 3 is not a failure condition; a non-zero fractional part is the issue.

**Question 4.** To turn `9.6` into the integer `10` while still detecting `int` overflow, what should you write?

~~~java
int result = new BigDecimal("9.6")
        .setScale(0, RoundingMode.HALF_UP)
        .intValueExact();
~~~

**Question 5.** Does `new BigDecimal("9223372036854775808").longValue()` throw `ArithmeticException`? What about `longValueExact()`?

**Answer:** `longValue()` does not throw and returns `-9223372036854775808`. `longValueExact()` throws `ArithmeticException` because the positive input exceeds `Long.MAX_VALUE`.

## 10. References

- [BigDecimal — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): describes `intValue()`, `longValue()`, `intValueExact()`, `longValueExact()`, `toBigInteger()`, and `toBigIntegerExact()`.
- [RoundingMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): rounding rules, especially `DOWN`, `HALF_UP`, `HALF_EVEN`, and `UNNECESSARY`.
- [Integer and Long — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): Java integer type limit constants; for 64-bit refer to [Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html).

**Takeaway:** `intValue()`/`longValue()` are convenient, but **can silently lose fractional parts and high bits**. `intValueExact()`/`longValueExact()` help uphold the data contract by failing if the number is not an integer or does not fit the target type. Intentional rounding is a **separate step** requiring explicit business rules.
