# Distinguishing Casting, Rounding, and `exact` Conversion Checks in Java

## 1. Three distinct questions when converting numbers

When converting a value from one numeric type to another, separate three goals:

1. **Casting/conversion**: moving the value to another data type under Java's rules. The conversion may preserve the value, drop the fractional part, drop bits, or clamp the value at the target type's bounds.
2. **Rounding**: choosing a representative value according to an explicit rule (nearest, up, down, toward zero, tie-breaking rules, etc.). Rounding is not synonymous with changing types, nor does it guarantee the result fits within the target type's range.
3. **Exact conversion (`exact`)**: requiring the result to preserve the numeric value under an API contract; if a fractional part would have to be discarded or the target type's limits are exceeded, an error is reported, typically `ArithmeticException`.

Example with `12.8`:

- `(int) 12.8` yields `12` because converting `double` to `int` truncates the fractional part toward 0.
- `Math.round(12.8)` yields `13L`, because the method selects the nearest integer and returns `long` for a `double` argument.
- `new BigDecimal("12.8").intValueExact()` throws `ArithmeticException`, because `12.8` is not an integer.

None of these three operations automatically fits every business need. In particular, *`exact`* refers to converting without altering **the value currently stored**, rather than restoring precision lost in an earlier calculation step.

## 2. Foundation: value ranges, bit width, and precision

| Primitive type | Width | Range / key properties |
| --- | ---: | --- |
| `byte` | 8 bits | `-128` to `127` |
| `short` | 16 bits | `-32768` to `32767` |
| `char` | 16 bits | Unsigned `0` to `65535`; one UTF-16 code unit |
| `int` | 32 bits | `-2147483648` to `2147483647` |
| `long` | 64 bits | `-9223372036854775808` to `9223372036854775807` |
| `float` | 32 bits | Binary floating-point, ~24 bits of significand precision |
| `double` | 64 bits | Binary floating-point, ~53 bits of significand precision |

`float`/`double` values can also be `NaN`, `+Infinity`, `-Infinity`, and `+0.0`/`-0.0`. They do not represent every finite decimal number exactly; for instance, `0.1` has no exact finite binary representation in `double`.

### Widening does not always preserve precision

Some *widening* conversions are exact: `byte` → `short` → `int` → `long` preserves integer values; `float` → `double` preserves the **existing** `float` value exactly.

However, `int` → `float` and `long` → `double` can lose precision bits even though the target type is commonly called "wider." For example:

```java
long original = 9_007_199_254_740_993L; // 2^53 + 1
double converted = original;            // 2^53
long back = (long) converted;            // 9_007_199_254_740_992L
```

`double` has only 53 bits of significand precision, so it cannot represent two consecutive integers in this region. Once converted to `double`, information is lost; casting back or calling an `exact` method afterward cannot reconstruct the original number. When comparing directly with `original == converted`, Java converts `long` to `double` for the comparison, so that check can also mask the loss. Check before converting or use an appropriate numeric domain.

## 3. Primitive casting: results can lose data without throwing

### 3.1. From a larger integer to a smaller integer

Narrowing via a cast, such as `(int) someLong` or `(byte) someInt`, keeps the low bits matching the target type's width. For signed types, the resulting bit pattern is interpreted in two's complement.

```java
int a = 130;
byte b = (byte) a; // -126

long large = 3_000_000_000L;
int narrowed = (int) large; // -1294967296
```

For `130`, the low 8 bits are `1000_0010`, carrying the value `-126` in `byte`. For `3_000_000_000L`, the low 32 bits correspond to a negative `int` value. Java **does not throw an exception** when a primitive cast drops bits.

For `char`, the result falls in `0..65535`; larger values also keep only the low 16 bits. Because `char` is a UTF-16 code unit, casting a number to `char` should not be treated as converting an arbitrary Unicode code point into a full character.

### 3.2. From `float`/`double` to `int`/`long`

For finite values within the target type's range, Java **truncates the fractional part toward zero** (*truncation toward zero*), which differs from rounding to the nearest integer:

| Expression | Result |
| --- | ---: |
| `(int) 2.9` | `2` |
| `(int) -2.9` | `-2` |
| `(long) 2.9` | `2L` |
| `(long) -2.9` | `-2L` |

Crucial boundary rules:

- `NaN` converts to `int`/`long` as `0`.
- Overly large positive values (including `+Infinity`) convert to `Integer.MAX_VALUE` or `Long.MAX_VALUE`.
- Overly small negative values (including `-Infinity`) convert to `Integer.MIN_VALUE` or `Long.MIN_VALUE`.
- Casting does not throw `ArithmeticException` when these cases occur.

For example, `(int) 1e20` yields `2147483647`; `(int) Double.NaN` yields `0`. Thus casting is **not** an input validation check.

For `double` → `float`, Java can also round due to lower binary precision; magnitudes that are too large can become infinity, and very small values can become 0 (or subnormal numbers). This is a floating-point conversion rule, not the fractional-truncation behavior of `double` → `int`.

### 3.3. Cast syntax differs from parsing

`(int) d` converts an existing numeric value. `Integer.parseInt("123")` reads a **character string** into an integer, checks syntax and `int` bounds, and can throw `NumberFormatException`.

```java
int a = (int) 12.9;         // 12
int b = Integer.parseInt("12"); // 12
// Integer.parseInt("12.9"); // NumberFormatException
```

If user input must be an integer with no fractional loss, parse the string with an appropriate API (`Integer.parseInt`, or `BigDecimal` if decimal formatting needs validation), rather than parsing to `double` and casting.

## 4. Rounding: specify the direction and tie-breaking rule

### 4.1. Cast, `floor`, `ceil`, `round`, and `rint`

`Math` operations return results according to different rules:

| Operation | Rule | Example with `2.5` | Example with `-2.5` |
| --- | --- | --- | --- |
| `(int) x` | Truncate toward 0 (if finite, in range) | `2` | `-2` |
| `Math.floor(x)` | Greatest integer `<= x`, `double` result | `2.0` | `-3.0` |
| `Math.ceil(x)` | Smallest integer `>= x`, `double` result | `3.0` | `-2.0` |
| `Math.round(x)` | Nearest integer; on exact ties, choose the larger number | `3` | `-2` |
| `Math.rint(x)` | Nearest integer as `double`; ties pick the even number | `2.0` | `-2.0` |

In the table, `Math.round(double)` returns **`long`**, whereas `Math.round(float)` returns **`int`**. `Math.floor`, `Math.ceil`, and `Math.rint` return `double`; the **return types differ** even when the results look like integers.

More examples:

```java
Math.round(2.5);  // 3L
Math.round(-1.5); // -1L
Math.rint(3.5);   // 4.0
Math.rint(2.5);   // 2.0
Math.floor(-2.2); // -3.0
Math.ceil(-2.2);  // -2.0
```

`Math.round` also maps `NaN` to `0` and saturates at `int`/`long` bounds for infinity or out-of-range values. Therefore, despite the word "round," the method's output **does not mean** the input was validated against target-type limits. `Math.floor`/`ceil`/`rint` keep results as `double` and have their own rules for `NaN`/infinity; if you cast afterward, cast data-loss rules still apply.

### 4.2. `RoundingMode` of `BigDecimal`

When you need to control the number of decimal digits, especially for money, taxes, or data requiring a specified rounding rule, use `BigDecimal.setScale(scale, roundingMode)`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("12.345");
BigDecimal a = x.setScale(2, RoundingMode.HALF_UP);   // 12.35
BigDecimal b = x.setScale(2, RoundingMode.HALF_EVEN); // 12.34
```

Here `scale = 2` means two digits to the right of the decimal point; **not** two significant digits. Common modes:

| Mode | Core rule | Example rounding to integer |
| --- | --- | --- |
| `UP` | Away from 0 whenever nonzero digits are discarded | `-2.1 → -3` |
| `DOWN` | Toward 0 | `-2.9 → -2` |
| `CEILING` | Toward positive infinity | `-2.1 → -2` |
| `FLOOR` | Toward negative infinity | `-2.1 → -3` |
| `HALF_UP` | Nearest; exact ties go away from 0 | `-2.5 → -3` |
| `HALF_DOWN` | Nearest; exact ties go toward 0 | `-2.5 → -2` |
| `HALF_EVEN` | Nearest; exact ties pick the even last digit | `2.5 → 2`, `3.5 → 4` |
| `UNNECESSARY` | Disallows dropping nonzero value; throws if rounding is needed | `2.5` to scale 0 → error |

`Math.round(-2.5)` is `-2`, whereas `new BigDecimal("-2.5").setScale(0, RoundingMode.HALF_UP)` is `-3`. Both are right under their own rules; avoid loosely calling either "standard rounding."

For predictable decimal arithmetic, prefer `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)`. `new BigDecimal(0.1)` records the **exact binary value of the already-rounded `double`**, which is not exactly equal to `0.1` in base 10. `BigDecimal.valueOf(double)` uses the canonical decimal string of the `double` value, yet cannot recover digits that earlier floating-point operations already lost.

## 5. What do the `exact` conversion APIs check?

### 5.1. `Math.toIntExact(long)`: range-checked `long` → `int` narrowing

```java
int ok = Math.toIntExact(42L); // 42

// Throws ArithmeticException because it exceeds Integer.MAX_VALUE:
int overflow = Math.toIntExact(3_000_000_000L);
```

`Math.toIntExact` has no overload taking `double` or `BigDecimal`; it is only for a `long` value being converted to `int`. Unlike `(int) someLong`, this method **rejects** values outside the `int` range. When you need overflow checks on integer addition/multiplication during calculation, related methods exist such as `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, etc.; those check **arithmetic operations**, not casts.

### 5.2. `BigInteger.intValueExact()` / `longValueExact()`

`BigInteger` can exceed the `long` range. `intValueExact()` and `longValueExact()` throw `ArithmeticException` if the value does not fit in the target type.

```java
import java.math.BigInteger;

BigInteger small = new BigInteger("2147483647");
int ok = small.intValueExact(); // 2147483647

BigInteger tooLarge = new BigInteger("2147483648");
// tooLarge.intValueExact(); // ArithmeticException
long fitsLong = tooLarge.longValueExact(); // 2147483648L
```

Meanwhile, `.intValue()`/`.longValue()` can drop bits; names without `Exact` do not guarantee preserving the value.

### 5.3. `BigDecimal.intValueExact()` / `longValueExact()`

For `BigDecimal`, `exact` checks **both fractional parts and range**:

```java
import java.math.BigDecimal;

new BigDecimal("12.00").intValueExact(); // 12: fractional part is all zeros
new BigDecimal("-4").longValueExact();   // -4L

// new BigDecimal("12.01").intValueExact();  // ArithmeticException: has fractional part
// new BigDecimal("2147483648").intValueExact(); // ArithmeticException: out of range
```

The condition is not `scale == 0`: `12.00` has scale 2 yet still represents the exact integer 12. The regular `.intValue()` and `.longValue()` methods give no signal when dropping a fractional part or exceeding the range.

If the goal is **requiring an integer**, call `intValueExact()` directly on the original `BigDecimal`. If business rules allow rounding first, explicitly choose a `RoundingMode` and then call `intValueExact()` on the rounded value. These two workflows have different meanings:

```java
BigDecimal input = new BigDecimal("12.8");

// Cannot silently lose the fraction: input.intValueExact() will throw.
int rounded = input.setScale(0, java.math.RoundingMode.HALF_UP)
                   .intValueExact(); // 13
```

`setScale(0, ...)` settles the fractional part; `intValueExact()` afterward still validates the `int` range. If rounding must never occur, you can use `RoundingMode.UNNECESSARY` and verify exactness.

### 5.4. Is there an `exact` method for `double` → `int`?

There is no `Math.toIntExact(double)` in Java 17. For existing `double` data, check finiteness, integrality, and `int` range **before casting**:

```java
static int requireInt(double value) {
    if (!Double.isFinite(value)
            || value != Math.rint(value)
            || value < Integer.MIN_VALUE
            || value > Integer.MAX_VALUE) {
        throw new ArithmeticException("Cannot convert exactly to int");
    }
    return (int) value;
}
```

Here `Math.rint(value)` confirms the current `double` value is whole (needs no rounding); `==`/`!=` compares accurately in this case because we are comparing two `double`s after filtering out `NaN`/infinity. `-0.0` is accepted as `int` 0, since `int` does not distinguish signed zeros.

**`long` boundary trap:** do not blindly copy `value > Long.MAX_VALUE` into a `double` → `long` check. `Long.MAX_VALUE` rounds to `2^63` when converted to `double`, so that comparison can wrongly accept an out-of-range value. If you need to convert `double` to `long` matching the **current `double` value**, use a half-open bound, such as:

```java
static long requireLong(double value) {
    if (!Double.isFinite(value)
            || value != Math.rint(value)
            || value < -0x1.0p63
            || value >= 0x1.0p63) {
        throw new ArithmeticException("Cannot convert exactly to long");
    }
    return (long) value;
}
```

`0x1.0p63` is a `double` literal representing `2^63` exactly; `Long.MIN_VALUE == -2^63` is still valid, whereas `+2^63` already exceeds `Long.MAX_VALUE`. Even so, if a large `long` was previously converted to `double` and lost bits, neither this check nor casting can detect or repair the original `long` value. When starting with decimal data, keep it in `BigDecimal` and call `...ValueExact()` directly on that source.

## 6. Choosing the right operation for business requirements

| Requirement | Appropriate choice | Caveat |
| --- | --- | --- |
| Convert `int` to `long` | Direct assignment `long n = i;` | Preserves value |
| Convert `long` to `int`, must be intact | `Math.toIntExact(n)` | Throws `ArithmeticException` if out of range |
| Convert `long` to `int`, intentionally keep low bits | `(int) n` | Can change sign/value |
| Convert float/double to integer by truncating toward 0 | Cast after validating range if needed | `NaN` and out-of-range have special results |
| Round to nearest integer, ties toward positive | `Math.round(...)` | Do not use to prove input is in range |
| Round to nearest integer, ties to even | `Math.rint(double)` or `BigDecimal` `HALF_EVEN` | `rint` still returns `double` |
| Round money to two decimal places | `BigDecimal.setScale(2, mode)` | `mode` must come from business rules |
| Convert decimal to `int` losslessly | `BigDecimal.intValueExact()` | Must be whole and fit in `int` |
| Convert `BigInteger` to `long` losslessly | `BigInteger.longValueExact()` | Throws if it does not fit |
| Parse integer string from user | `Integer.parseInt` / `Long.parseLong` | Syntax/range errors throw `NumberFormatException` |

Do not choose `Math.round` merely because its name sounds "safe." `round`, `cast`, and `exact` answer three different questions about handling fractions, range overflow, and data loss.

## 7. Complete Java 17 example and verified output

Save the file `NumericConversionDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NumericConversionDemo {
    public static void main(String[] args) {
        System.out.println("cast 2.9 = " + (int) 2.9);
        System.out.println("cast -2.9 = " + (int) -2.9);
        System.out.println("cast byte 130 = " + (byte) 130);
        System.out.println("cast NaN = " + (int) Double.NaN);
        System.out.println("cast 1e20 = " + (int) 1e20);

        System.out.println("round 2.5 = " + Math.round(2.5));
        System.out.println("round -2.5 = " + Math.round(-2.5));
        System.out.println("rint 2.5 = " + Math.rint(2.5));
        System.out.println("rint 3.5 = " + Math.rint(3.5));
        System.out.println("floor -2.2 = " + Math.floor(-2.2));
        System.out.println("ceil -2.2 = " + Math.ceil(-2.2));

        BigDecimal negativeHalf = new BigDecimal("-2.5");
        BigDecimal positiveHalf = new BigDecimal("2.5");
        System.out.println("HALF_UP -2.5 = "
                + negativeHalf.setScale(0, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN 2.5 = "
                + positiveHalf.setScale(0, RoundingMode.HALF_EVEN));

        System.out.println("Math.toIntExact(42) = " + Math.toIntExact(42L));
        System.out.println("BigDecimal 12.00 exact = "
                + new BigDecimal("12.00").intValueExact());

        try {
            Math.toIntExact(3_000_000_000L);
        } catch (ArithmeticException e) {
            System.out.println("long to int overflow: ArithmeticException");
        }

        try {
            new BigDecimal("12.5").intValueExact();
        } catch (ArithmeticException e) {
            System.out.println("decimal with fraction: ArithmeticException");
        }
    }
}
```

Compile and run:

```bash
javac NumericConversionDemo.java
java NumericConversionDemo
```

Output:

```text
cast 2.9 = 2
cast -2.9 = -2
cast byte 130 = -126
cast NaN = 0
cast 1e20 = 2147483647
round 2.5 = 3
round -2.5 = -2
rint 2.5 = 2.0
rint 3.5 = 4.0
floor -2.2 = -3.0
ceil -2.2 = -2.0
HALF_UP -2.5 = -3
HALF_EVEN 2.5 = 2
Math.toIntExact(42) = 42
BigDecimal 12.00 exact = 12
long to int overflow: ArithmeticException
decimal with fraction: ArithmeticException
```

The example uses `double` literals and explicit string-based `BigDecimal`s to avoid mixing binary rounding results with decimal rounding rules.

## 8. When data comes from strings or decimal calculations

Consider the requirement: the user enters a product quantity as `"12.00"`, and the system accepts only whole quantities in the `int` range. An appropriate approach is:

```java
import java.math.BigDecimal;

public class QuantityParser {
    public static int parseQuantity(String raw) {
        BigDecimal parsed = new BigDecimal(raw);
        int quantity = parsed.intValueExact();
        if (quantity < 0) {
            throw new IllegalArgumentException("Quantity must be non-negative");
        }
        return quantity;
    }

    public static void main(String[] args) {
        System.out.println(parseQuantity("12.00")); // 12
    }
}
```

```bash
javac QuantityParser.java
java QuantityParser
```

```text
12
```

`new BigDecimal(raw)` can throw `NumberFormatException` if the string is invalid; `intValueExact()` can throw `ArithmeticException` if the number has a fraction or exceeds range. Only then are business rules checked (e.g., non-negative). Thus each error has a clear meaning and data is never silently truncated.

Conversely, if the requirement *permits fractional values and rounds the quantity*, an explicit `RoundingMode` must be chosen before calling `intValueExact()`. Do not pick `HALF_UP` or `HALF_EVEN` purely out of habit.

A similar situation occurs when calculating money. If a total needs two decimal places, keep the value in `BigDecimal`, compute with suitable precision, and then call `setScale(2, mode)` per accounting requirements. Casting to `int` only keeps the integer part and drops the fraction, which is not equivalent to rounding to the smallest currency unit.

## 9. Common errors and how to spot them

1. **Assuming casting is rounding.** `(int) -2.9 == -2`, whereas `Math.floor(-2.9) == -3.0`; the operations serve different purposes.
2. **Assuming casting automatically reports overflow.** `(int) 3_000_000_000L` produces a negative value; only `Math.toIntExact(3_000_000_000L)` throws `ArithmeticException`.
3. **Assuming `Math.round` guarantees in-range results.** `Math.round(Double.POSITIVE_INFINITY)` returns `Long.MAX_VALUE`; `Math.round(Double.NaN)` returns `0`.
4. **Mixing tie-breaking rules when rounding.** `Math.round(-2.5) == -2`, `HALF_UP` on `BigDecimal("-2.5")` gives `-3`, and `HALF_EVEN` picks the even last digit.
5. **Creating `BigDecimal` from `double` without understanding the source data.** `new BigDecimal(0.1)` records the binary value of `double`; if exact decimal `0.1` from input is required, use strings or original decimal data.
6. **Losing data before checking `exact`.** `(long) someDouble` may already have truncated/saturated; `Math.toIntExact((long) someDouble)` checks only the `long` after the cast, unable to inspect fractions or infinity from the original source.
7. **Using `Long.MAX_VALUE` as the upper bound for `double` → `long`.** `Long.MAX_VALUE` converted to `double` is not exact; the safe upper bound is `value < 0x1.0p63`.
8. **Checking only for fractions while forgetting target type limits.** `1e20` is a `double` with no fractional part, yet it does not fit in `int` or `long`; checking `x == Math.rint(x)` is insufficient.
9. **Confusing `Exact` with "always produces an exact decimal answer."** `BigDecimal.intValueExact` guarantees converting the existing integer value, not fixing errors from earlier `double` math.
10. **Ignoring return types.** `Math.round(float)` returns `int`, `Math.round(double)` returns `long`, and `Math.floor`/`Math.ceil`/`Math.rint` return `double`. Casting onward to a narrower type needs separate checking.
11. **Using `parseInt` to interpret decimal strings.** `"12.00"` is invalid for `Integer.parseInt` even though `BigDecimal.intValueExact()` can convert it to 12 after parsing as decimal.
12. **Picking `RoundingMode` by intuition.** Accounting, grading, statistics, and display rules can differ; explicitly document how fractions, negative signs, and exact ties are handled.

## 10. Self-check exercises

Predict the result or exception before running Java:

```java
(int) -7.9
Math.round(-7.5)
Math.rint(7.5)
Math.toIntExact((long) Integer.MAX_VALUE + 1)
new java.math.BigDecimal("15.000").intValueExact()
new java.math.BigDecimal("15.001").intValueExact()
new java.math.BigDecimal("-1.5")
    .setScale(0, java.math.RoundingMode.HALF_UP)
```

**Answers in order:**

1. `-7` because casting truncates the fractional part toward 0.
2. `-7L` because `Math.round` picks the nearest integer and exact ties go toward positive.
3. `8.0` because `Math.rint` ties to the even number.
4. `ArithmeticException` because it exceeds `Integer.MAX_VALUE`.
5. `15` because the fractional part contains only zeros.
6. `ArithmeticException` because a nonzero fractional part remains.
7. `-2` as a `BigDecimal` because `HALF_UP` goes away from 0 on exact ties.

**Rule to remember:** when you want to **change types** you can cast (accepting the data-loss rules), when you want to **pick a value near a level** you must specify rounding, and when you want to **preserve the value** use `...Exact()` or an equivalent check **before** casting. If data starts as decimal strings, keep it in decimal form until validation and required rounding are complete.
