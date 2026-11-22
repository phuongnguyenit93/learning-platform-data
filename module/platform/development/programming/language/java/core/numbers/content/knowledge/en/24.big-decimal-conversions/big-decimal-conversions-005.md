# BigDecimal `*ValueExact` Methods: Checking Fractional Parts and Target Type Limits

When converting `BigDecimal` to `byte`, `short`, `int`, `long`, or `BigInteger`, you must decide clearly whether **information loss is permitted**. The `byteValueExact()`, `shortValueExact()`, `intValueExact()`, `longValueExact()`, and `toBigIntegerExact()` methods are intended for cases requiring an **exact integer result**.

**Core rule:** an `*Exact` conversion succeeds only if the `BigDecimal` value has **no non-zero fractional part**; for fixed-width integer types, the value must also **fit within the target type's representation range**. If these conditions are not met, the method throws `ArithmeticException` instead of silently truncating the fraction, rounding, or overflowing.

```java
new BigDecimal("42.000").intValueExact(); // 42: exact
new BigDecimal("42.100").intValueExact(); // ArithmeticException: fractional part
new BigDecimal("2147483648").intValueExact(); // ArithmeticException: exceeds int
```

The snippet above illustrates individual expressions; the last two lines throw exceptions if executed without handling.

## 1. Two Independent Conditions: Integer by Value and Within Range

`BigDecimal` uses the representation `unscaledValue × 10^(-scale)`. `scale > 0` usually means there are decimal digit positions, **but it does not prove the number has a non-zero fractional part**.

Examples:

| `BigDecimal` Value | Scale | Integer by Value? | `intValueExact()` |
|---|---:|---|---|
| `"42"` | 0 | Yes | `42` |
| `"42.000"` | 3 | Yes: all digits after the decimal point are 0 | `42` |
| `"42.100"` | 3 | No: fractional part 0.100 | Throws `ArithmeticException` |
| `"-2.75"` | 2 | No | Throws `ArithmeticException` |
| `"0.000"` | 3 | Yes, equal to 0 | `0` |
| `"1E+3"` | -3 | Yes, equal to 1000 | `1000` |
| `"2147483647"` | 0 | Yes, fits `int` | `2147483647` |
| `"2147483648"` | 0 | Yes, but exceeds `int` | Throws `ArithmeticException` |

Note: an exact conversion checks the **fractional part by value**, rather than simply demanding `scale() == 0`. Thus `42.000` is valid and `1E+3` is also valid.

Two conditions should be examined in logical order:

1. **Integrality:** does an integer value exist that equals the exact input `BigDecimal`? `42.000` does; `42.100` does not.
2. **Range:** can that integer be accurately represented in `byte`, `short`, `int`, or `long`? `2147483648` is an integer, but it does not belong to `int`.

Do not guess which reason triggered the exception from the error message: the API guarantees `ArithmeticException` when an exact conversion cannot be performed, while the message text can vary across implementation versions. If your application needs distinct business messages for "has fractional part" and "out of bounds," check each condition separately beforehand or clearly explain the policy after catching the exception.

## 2. The Exact Conversion Methods

| Method | Return Type | Target Type Range | Condition to Succeed |
|---|---|---|---|
| `byteValueExact()` | `byte` | -128 to 127 | Integer value, within `byte` range |
| `shortValueExact()` | `short` | -32768 to 32767 | Integer value, within `short` range |
| `intValueExact()` | `int` | -2147483648 to 2147483647 | Integer value, within `int` range |
| `longValueExact()` | `long` | -9223372036854775808 to 9223372036854775807 | Integer value, within `long` range |
| `toBigIntegerExact()` | `BigInteger` | No fixed bit limit | Integer value; still subject to practical resource limits |

These methods **have no `RoundingMode` parameter**: if the value cannot be converted exactly, you must handle the error or explicitly round beforehand using a separate, well-defined step.

### Examples with `byte` and `short`

```java
new BigDecimal("127.00").byteValueExact(); // 127
new BigDecimal("128").byteValueExact();    // ArithmeticException
new BigDecimal("-128").byteValueExact();   // -128
new BigDecimal("-129").byteValueExact();   // ArithmeticException

new BigDecimal("32767").shortValueExact(); // 32767
new BigDecimal("32768").shortValueExact(); // ArithmeticException
```

`"127.00"` is not rejected merely because its scale is 2; its value is still exactly the integer 127. `"128"` is rejected because the maximum `byte` is 127, even though it has no fractional part at all.

### Examples with `int` and `long`

```java
new BigDecimal("2147483647").intValueExact(); // 2147483647
new BigDecimal("2147483648").intValueExact(); // ArithmeticException

new BigDecimal("9223372036854775807").longValueExact(); // Long.MAX_VALUE
new BigDecimal("9223372036854775808").longValueExact(); // ArithmeticException
```

The same applies at the negative boundary: values smaller than `Integer.MIN_VALUE` or `Long.MIN_VALUE` cannot be converted exactly to the corresponding type.

### The `toBigIntegerExact()` Case

`BigInteger` has arbitrary integer precision, so it **does not encounter 8/16/32/64-bit limits**. However, it still cannot retain fractional parts:

```java
new BigDecimal("999999999999999999999.000").toBigIntegerExact();
// Returns a BigInteger with value 999999999999999999999

new BigDecimal("999999999999999999999.001").toBigIntegerExact();
// ArithmeticException: has non-zero fractional part
```

You can use `toBigIntegerExact()` when you need to convert a decimal value into a large integer while preserving **the entire value**.

## 3. Differences from Ordinary Conversion Methods

The group **without the `Exact` suffix** can return a value without reporting an error when losing information:

- `byteValue()`, `shortValue()`, `intValue()`, and `longValue()` return the integer part toward zero; if the number exceeds the target type's range, the low bits of the integer part are kept according to the corresponding width, which can flip the sign or produce a number unequal to the original.
- `toBigInteger()` discards the fractional part toward zero without checking whether any fractional part was lost.
- `floatValue()` and `doubleValue()` convert to binary floating-point numbers, which can lose precision digits, produce infinity when too large, or turn into 0 when too small. **There are no corresponding `floatValueExact()` or `doubleValueExact()` methods in `BigDecimal`.**

Examples:

| Input Value | Ordinary Call | Result | `Exact` Call |
|---|---|---|---|
| `"42.1"` | `intValue()` | `42` | `intValueExact()` throws exception |
| `"-2.75"` | `intValue()` | `-2` | `intValueExact()` throws exception |
| `"2147483648"` | `intValue()` | `-2147483648` | `intValueExact()` throws exception |
| `"128"` | `byteValue()` | `-128` | `byteValueExact()` throws exception |
| `"1.99"` | `toBigInteger()` | `1` | `toBigIntegerExact()` throws exception |
| `"-1.99"` | `toBigInteger()` | `-1` | `toBigIntegerExact()` throws exception |

In the `2147483648` example, `intValue()` returns `-2147483648` because it takes only the low 32 bits of the integer part, interpreted as a signed `int`. This is **not** a valid business rounding operation and not a way to check if a number fits a data type.

**Consequence:** using `intValue()` to convert prices, identifiers, quantities, accounting data, or fields requiring integrity can silently drop digits or produce wrong values. If the requirement is "only accept integers within range," `intValueExact()` is the direct choice.

## 4. Standalone Java 17+ Example and Verified stdout

Create a file named `BigDecimalExactConversionDemo.java`:

```java
import java.math.BigDecimal;
import java.util.function.Supplier;

public class BigDecimalExactConversionDemo {
    private static void check(String label, Supplier<?> conversion) {
        try {
            System.out.println(label + " -> " + conversion.get());
        } catch (ArithmeticException ex) {
            System.out.println(label + " -> ArithmeticException");
        }
    }

    public static void main(String[] args) {
        check("42.000 int",
                () -> new BigDecimal("42.000").intValueExact());
        check("42.100 int",
                () -> new BigDecimal("42.100").intValueExact());
        check("-2.75 int",
                () -> new BigDecimal("-2.75").intValueExact());

        check("2147483647 int",
                () -> new BigDecimal("2147483647").intValueExact());
        check("2147483648 int",
                () -> new BigDecimal("2147483648").intValueExact());

        check("127.00 byte",
                () -> new BigDecimal("127.00").byteValueExact());
        check("128 byte",
                () -> new BigDecimal("128").byteValueExact());
        check("32767 short",
                () -> new BigDecimal("32767").shortValueExact());
        check("32768 short",
                () -> new BigDecimal("32768").shortValueExact());

        check("long max",
                () -> new BigDecimal("9223372036854775807").longValueExact());
        check("long overflow",
                () -> new BigDecimal("9223372036854775808").longValueExact());

        check("big integer",
                () -> new BigDecimal("999999999999999999999.000")
                        .toBigIntegerExact());
        check("big fraction",
                () -> new BigDecimal("999999999999999999999.001")
                        .toBigIntegerExact());

        System.out.println("42.1 intValue = "
                + new BigDecimal("42.1").intValue());
        System.out.println("2147483648 intValue = "
                + new BigDecimal("2147483648").intValue());
        System.out.println("128 byteValue = "
                + new BigDecimal("128").byteValue());
        System.out.println("zero scale=3 -> int = "
                + new BigDecimal("0.000").intValueExact());
        System.out.println("scientific -> int = "
                + new BigDecimal("1E+3").intValueExact());
    }
}
```

Compile and run (Java 17 or newer):

```bash
javac BigDecimalExactConversionDemo.java
java BigDecimalExactConversionDemo
```

stdout output:

```text
42.000 int -> 42
42.100 int -> ArithmeticException
-2.75 int -> ArithmeticException
2147483647 int -> 2147483647
2147483648 int -> ArithmeticException
127.00 byte -> 127
128 byte -> ArithmeticException
32767 short -> 32767
32768 short -> ArithmeticException
long max -> 9223372036854775807
long overflow -> ArithmeticException
big integer -> 999999999999999999999
big fraction -> ArithmeticException
42.1 intValue = 42
2147483648 intValue = -2147483648
128 byteValue = -128
zero scale=3 -> int = 0
scientific -> int = 1000
```

The `check` method catches `ArithmeticException` to illustrate each failure case without halting the entire program. It intentionally prints the **exception class name** instead of `ex.getMessage()`, because the message wording is not a stable contract to depend on.

Observe two conclusions from the program: `42.000` and `1E+3` convert accurately despite scales of 3 and -3 respectively; conversely, `2147483648` cannot be converted accurately to `int`, even though it is purely an integer.

## 5. When Should You Round Before Converting?

`*ValueExact` **does not apply a rounding policy automatically**. If business logic allows rounding, separate the rounding decision into an explicit step in code, then convert accurately:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal quantity = new BigDecimal("12.7");

int rounded = quantity
        .setScale(0, RoundingMode.HALF_UP)
        .intValueExact(); // 13

int truncated = quantity
        .setScale(0, RoundingMode.DOWN)
        .intValueExact(); // 12
```

This is an **illustrative snippet** to be placed inside an appropriate Java method, not a standalone Java class with `main`. `setScale(0, ...)` makes the fractional-handling policy explicit. Afterward, `intValueExact()` still **checks the `int` range**: rounding beforehand does not guarantee an overly large number becomes type-compatible.

Rounding modes have distinct meanings; for example, `HALF_UP` rounds to the nearest integer and rounds away from zero at ties, while `DOWN` discards the fractional part toward zero. Which mode to choose must follow the business contract, not developer preference.

If business logic **forbids losing any fractional part**, calling `intValueExact()` directly is right; do not round first to "bypass" exactness checks.

## 6. Use in Input Parsing, APIs, and Error Handling

A typical example: receiving a quantity from JSON, CSV, or a database as a `BigDecimal`, then converting it to `int`. If the system requires the quantity to be a non-negative integer not exceeding a maximum count, perform separate steps:

1. **Validate business domain:** the quantity must be non-negative or positive, and must meet business limits. `intValueExact()` only checks integrality and technical bounds; it **does not** check "must be positive," "cannot be 0," or "maximum 100 items."
2. **Convert accurately:** use `intValueExact()`, `longValueExact()`, etc. to reject invalid fractional parts and type overflow.
3. **Map errors:** catch `ArithmeticException` at the appropriate boundary to produce a clear input error, rather than letting the application process corrupted data.

Example method that can be placed inside a request-handling class:

```java
static int parseQuantity(BigDecimal raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Quantity is required");
    }
    final int quantity;
    try {
        quantity = raw.intValueExact();
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException(
                "Quantity must be a 32-bit integer", ex);
    }
    if (quantity < 0 || quantity > 100) {
        throw new IllegalArgumentException(
                "Quantity must be between 0 and 100");
    }
    return quantity;
}
```

The method above is meant for an appropriate Java class (or placed into an example with `main`) and does not run standalone as a file. It distinguishes a **conversion error** (decimal value or exceeds `int`) from a **domain rule error** (an integer, yet outside 0–100). Avoid simply writing `int x = raw.intValue()`, as it can silently alter the value undetected.

If you need to retain very large integers while still rejecting fractional parts, use `toBigIntegerExact()` instead of forcing them into `long` or `int`.

## 7. Distinguishing Mathematical Exactness from Data Representation

Some common misconceptions:

- **`scale() > 0` does not mean an `Exact` conversion will fail.** `"5.000"` is an integer by value.
- **`scale() == 0` does not guarantee an `Exact` conversion will succeed.** `"999999999999999999999"` exceeds the `long` range even though it has no fractional part.
- **`precision()` does not replace range checking.** Precision tells you the number of significant digits, while sign, scale, and target limits still matter. Calling the right `*Exact` method is a concise way to let the API enforce the constraints.
- **Non-zero fractional parts also include very small values.** `"0.0000001"` cannot be converted to 0 via `intValueExact()`, even though `intValue()` gives 0.
- **`-0.000` still equals the integer 0.** Its numeric value is 0, so it converts accurately to 0 regardless of how it was originally written.
- **`BigDecimal` is immutable.** Conversion methods return values of the target type; they do not alter the scale or round the `BigDecimal` object itself.

Additionally, a `BigDecimal` can be constructed from `double`. `new BigDecimal(0.1)` represents the exact approximate binary value of `double`, which differs from the desired decimal value `0.1`. When the input data is inherently decimal, prefer `new BigDecimal("0.1")` or a suitable decimal source; do not conflate **whether the number source is accurate** with **whether conversion to an integer type is exact**.

## 8. Quick Method Selection Guide

| Requirement | Approach |
|---|---|
| Only accept integers fitting in `byte` | `byteValueExact()` |
| Only accept integers fitting in `short` | `shortValueExact()` |
| Only accept integers fitting in `int` | `intValueExact()` |
| Only accept integers fitting in `long` | `longValueExact()` |
| Accept integers beyond 64 bits, reject fractional parts | `toBigIntegerExact()` |
| Allow rounding per an explicit policy | `setScale(0, roundingMode)` then `*ValueExact()` |
| Intentionally truncate fractional parts and accept potential information loss | `intValue()`, `longValue()`, `toBigInteger()` respectively; document intent and risks |
| Need floating-point `double` / `float` | Use `doubleValue()` / `floatValue()`, accepting potential precision loss or checking application conditions separately |

## 9. Self-Check

**Question 1.** Does `new BigDecimal("7.000").intValueExact()` throw an error?  
**Answer:** No; the result is 7 because the fractional part is 0, even though the scale is 3.

**Question 2.** What does `new BigDecimal("7.001").intValueExact()` return?  
**Answer:** It throws `ArithmeticException` because it has a non-zero fractional part.

**Question 3.** How does `new BigDecimal("128").byteValueExact()` compare with `byteValue()`?  
**Answer:** `byteValueExact()` throws `ArithmeticException` because 128 exceeds `byte`; `byteValue()` returns -128 because it keeps only the low 8 bits.

**Question 4.** Does `new BigDecimal("2147483648").toBigIntegerExact()` succeed?  
**Answer:** Yes; `BigInteger` is not constrained by 32 bits. `intValueExact()` on the same value will throw an exception.

**Question 5.** When is `new BigDecimal("12.7").setScale(0, RoundingMode.HALF_UP).intValueExact()` the right choice?  
**Answer:** When business rules **permit and require** rounding to units using `HALF_UP`; the result is 13. If the requirement is to accept integers verbatim, `12.7` must be rejected using `intValueExact()`.

**Question 6.** What does `new BigDecimal("1E+3").intValueExact()` return?  
**Answer:** 1000. A negative scale does not prevent exact conversion as long as the numeric value is an integer and within range.

**Takeaway:** `*ValueExact` acts as a guardrail against silent data loss when converting `BigDecimal` to **integers**: there must be **no fractional part** and it must **fit the target type's range** (except `BigInteger`, which has no fixed bit limit). Do not confuse truncation, rounding, and exact conversion as the same operation.
