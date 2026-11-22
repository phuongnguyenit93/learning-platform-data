# Converting NaN, Infinity, and Out-of-Range Numbers to Integer Types in Java

In Java, casting from a floating-point number (`float`, `double`) to an integer (`byte`, `short`, `int`, `long`; as well as `char`) is a **narrowing primitive conversion**. This is not merely "dropping the fractional part": for **`NaN`**, **`+Infinity`**, **`-Infinity`**, or finite values outside the target type's range, Java defines specific conversion rules.

Three things to remember immediately:

1. **Finite values within range:** drop the fractional part **toward 0**; for example, `(int) 3.9 == 3` and `(int) -3.9 == -3`.
2. **Direct conversion of `float`/`double` to `int` or `long`:** `NaN` becomes `0`; overly large values or `+Infinity` become `MAX_VALUE`; overly negative values or `-Infinity` become `MIN_VALUE`.
3. **Conversion to `byte`, `short`, `char`:** Java **converts to `int` first**, then narrows `int` to the smaller type by discarding high bits. Thus `(byte) Double.POSITIVE_INFINITY` becomes **`-1`**, not `Byte.MAX_VALUE`.

These primitive conversions **do not automatically throw an exception on out-of-range overflow**. If a program must reject non-finite, out-of-range, or fractional data, it must **check explicitly before casting**.

## 1. Source and target: which conversion is being discussed?

This lesson covers only **`float` or `double` values converted to integer types**:

| Target type | Value range |
| --- | --- |
| `byte` | -128 to 127 |
| `short` | -32,768 to 32,767 |
| `int` | -2,147,483,648 to 2,147,483,647 |
| `long` | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |
| `char` | 0 to 65,535 (UTF-16 code unit, unsigned) |

`char` is included to accurately understand Java's conversion rules, though `char` should not be used to store counts or perform ordinary integer arithmetic.

`NaN` (*Not a Number*) and infinities (`+Infinity`, `-Infinity`) are special values of `float`/`double`, **not integer values**. `NaN` can arise from `0.0 / 0.0`, `+Infinity` can come from `1.0 / 0.0` or floating-point overflow, and `-Infinity` can come from `-1.0 / 0.0`. Moreover, `Double.MAX_VALUE`, while a **finite number**, is vastly larger than `Long.MAX_VALUE`.

Do not conflate three situations:

- **In-range fractional part:** can be truncated toward 0 without hitting bounds, e.g. `7.8 → 7`.
- **Out of range:** can receive the boundary value `MAX_VALUE`/`MIN_VALUE` when converting directly to `int`/`long`.
- **`NaN` or infinity:** special values handled by dedicated rules; they do not contain a finite integer to convert.

## 2. Exact Java rules: converting to `int` or `long`

According to Java's floating-point-to-integer narrowing rules, when the target type is `int` or `long`, it can be pictured in three steps:

1. If the source is **`NaN`**, the result is **`0`** of the target type.
2. If the source is a **finite non-NaN number** and the integer part after truncating toward 0 fits in range, the result is that integer part.
3. If the magnitude exceeds the range (including **`+Infinity`/`-Infinity`**), the result **is clamped at the target bound**: too large → `MAX_VALUE`, too negative → `MIN_VALUE`.

Step 2 uses **truncation toward zero**, not rounding to the nearest integer:

| Expression | Result |
| --- | ---: |
| `(int) 3.9` | `3` |
| `(int) -3.9` | `-3` |
| `(int) 0.99` | `0` |
| `(int) -0.99` | `0` |
| `(int) -0.0` | `0` |
| `(int) Double.NaN` | `0` |
| `(int) Double.POSITIVE_INFINITY` | `2147483647` |
| `(int) Double.NEGATIVE_INFINITY` | `-2147483648` |
| `(int) 1e100` | `2147483647` |
| `(long) -1e100` | `-9223372036854775808` |

**Key point:** `(int) Double.POSITIVE_INFINITY` yields `Integer.MAX_VALUE`, but that **does not mean** infinity is a large integer that can be stored accurately. Java simply defines a cast result. The original data was already unrepresentable in `int`.

Similarly, `(int) 1e100` and `(int) Double.POSITIVE_INFINITY` can both produce `Integer.MAX_VALUE`. Looking at the final `int` value, **you cannot tell** whether it came from a valid number, a clamped large number, or infinity; therefore, do not rely solely on the post-cast result to validate data.

These casts are **completely different** from narrowing `long` to `int`. For `long → int`, Java discards the high bits, so `(int) 3_000_000_000L` equals `-1294967296`. For `double → int`, the source value `3_000_000_000.0` instead becomes **`2147483647`** due to floating-point conversion rules.

## 3. Why do `byte` and `short` behave differently from `int`?

For targets `byte`, `short`, or `char`, Java applies a **two-stage** process:

1. Narrow `float`/`double` to **`int`**, following `NaN → 0`, truncate toward 0, clamp to `int` bounds if out of range.
2. Narrow the intermediate `int` value to `byte`, `short`, or `char` by **keeping the low bits** matching the target type.

For signed `byte`/`short`, the bit pattern is interpreted in two's complement; for `char`, it is a 16-bit unsigned value. The second step **does not clamp to `byte`/`short` limits**.

Example of converting `+Infinity` to `byte`:

```text
+Infinity
  → convert double to int: Integer.MAX_VALUE = 2147483647 (0x7FFFFFFF)
  → convert int to byte: keep low 8 bits = 0xFF
  → signed byte: -1
```

Therefore:

| Expression | Final value |
| --- | ---: |
| `(byte) Double.NaN` | `0` |
| `(short) Double.NaN` | `0` |
| `(byte) Double.POSITIVE_INFINITY` | `-1` |
| `(byte) Double.NEGATIVE_INFINITY` | `0` |
| `(short) Double.POSITIVE_INFINITY` | `-1` |
| `(short) Double.NEGATIVE_INFINITY` | `0` |
| `(byte) 130.9` | `-126` |
| `(byte) 1e100` | `-1` |
| `(char) Double.POSITIVE_INFINITY` | character with code `65535` |

For example, `(byte) 130.9`: step 1 truncates `130.9` to `int 130` (still within `int` range), and step 2 keeps the low 8 bits of `130`, which is `0x82`, interpreted as signed `byte` **-126**. These are two consecutive rules, **not** arithmetically rounding `130.9` down to -126.

**Do not infer** that casting from `double` to `byte` always "saturates at ±128." The result depends on the **bits of the intermediate `int`**; for `+Infinity`, a negative `byte` result is completely valid under the Java specification.

## 4. Converting NaN: why does it produce 0 without an error?

`Double.NaN` and `Float.NaN` represent the *Not a Number* state. For floating-point → integral narrowing, Java specifies that `NaN` becomes 0 in the conversion step to `int` or `long`. If the target is `byte`, `short`, or `char`, the intermediate `int 0` also yields 0.

```java
int a = (int) Double.NaN;     // 0
long b = (long) Float.NaN;    // 0L
byte c = (byte) Double.NaN;   // 0
```

The danger is that **0 can simultaneously be valid business data**. If a system receives an invalid measurement `NaN` and casts it straight to `int`, the result `0` can be misinterpreted as "zero quantity," "temperature equals 0," or a valid status code.

Do not use `value == Double.NaN` to detect NaN: `NaN` is not equal to itself in floating-point comparisons. Use `Double.isNaN(value)` or `Float.isNaN(value)`.

`Double.isFinite(value)`/`Float.isFinite(value)` is more convenient when **all special values** (both NaN and ±Infinity) must be rejected.

## 5. Infinity: cast rules differ from division by zero

`Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` are valid values of type `double` under IEEE 754 semantics. Dividing `1.0 / 0.0` returns `+Infinity`, unlike integer division `1 / 0`, which throws `ArithmeticException` when executed.

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;

int max = (int) positive;  // Integer.MAX_VALUE
int min = (int) negative;  // Integer.MIN_VALUE

long longMax = (long) positive; // Long.MAX_VALUE
long longMin = (long) negative; // Long.MIN_VALUE
```

In this primitive cast, Java does not throw `ArithmeticException`. Instead, infinity **is clamped** at the `int`/`long` boundary before any further narrowing to smaller types can happen.

However, there is a difference between the **source value before the cast** and the **chosen value after the cast**. A program that needs to preserve the meaning "source was invalid/infinite" must inspect the source **before converting**; after the cast, the information that it was ever infinite is gone.

## 6. Out-of-range finite numbers are still clamped: no NaN or Infinity needed

A `double` can be finite and many times larger than `Integer.MAX_VALUE`. For example, `1e100` is finite, yet vastly greater than even `Long.MAX_VALUE`:

```java
double big = 1e100;

int toInt = (int) big;   // 2147483647
long toLong = (long) big; // 9223372036854775807
```

Out-of-range negative numbers are also clamped at the negative boundary:

```java
double small = -1e100;

int toInt = (int) small;   // -2147483648
long toLong = (long) small; // -9223372036854775808
```

For a value just slightly outside `int` range:

```java
double d = 2_147_483_648.0; // Integer.MAX_VALUE + 1, represented exactly as double
int converted = (int) d;    // 2147483647, not -2147483648
```

This differs from casting `(int) 2_147_483_648L` from `long`: a `long → int` cast truncates bits, yielding `-2147483648`. When casting from `double`, Java **clamps at `Integer.MAX_VALUE`**. Distinguishing the **source type** is critical before predicting the result.

## 7. Standalone runnable Java 17+ program

Create the file `FloatToIntegerDemo.java`:

```java
public class FloatToIntegerDemo {
    static int checkedInt(double v) {
        if (!Double.isFinite(v)
                || v < Integer.MIN_VALUE
                || v > Integer.MAX_VALUE
                || v != Math.rint(v)) {
            throw new IllegalArgumentException("not an in-range integer");
        }
        return (int) v;
    }

    public static void main(String[] args) {
        System.out.println("3.9 -> int: " + (int) 3.9);
        System.out.println("-3.9 -> int: " + (int) -3.9);
        System.out.println("-0.0 -> int: " + (int) -0.0);
        System.out.println("NaN -> int: " + (int) Double.NaN);
        System.out.println("+Infinity -> int: " + (int) Double.POSITIVE_INFINITY);
        System.out.println("-Infinity -> int: " + (int) Double.NEGATIVE_INFINITY);
        System.out.println("1e100 -> int: " + (int) 1e100);
        System.out.println("-1e100 -> long: " + (long) -1e100);
        System.out.println("+Infinity -> long: " + (long) Double.POSITIVE_INFINITY);
        System.out.println("+Infinity -> byte: " + (byte) Double.POSITIVE_INFINITY);
        System.out.println("-Infinity -> byte: " + (byte) Double.NEGATIVE_INFINITY);
        System.out.println("NaN -> short: " + (short) Double.NaN);
        System.out.println("130.9 -> byte: " + (byte) 130.9);
        System.out.println("1e100 -> byte: " + (byte) 1e100);
        System.out.println("1e100 -> char code: " + (int) (char) 1e100);
        System.out.println("NaN finite? " + Double.isFinite(Double.NaN));

        System.out.println("checkedInt(7.0): " + checkedInt(7.0));
        try {
            checkedInt(7.5);
        } catch (IllegalArgumentException ex) {
            System.out.println("checkedInt(7.5): rejected");
        }
        try {
            checkedInt(Double.POSITIVE_INFINITY);
        } catch (IllegalArgumentException ex) {
            System.out.println("checkedInt(Infinity): rejected");
        }
        try {
            new java.math.BigDecimal("2147483648").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigDecimal out of range: rejected");
        }
    }
}
```

Compile and run:

```bash
javac FloatToIntegerDemo.java
java FloatToIntegerDemo
```

Stdout output (values verified on the JDK):

```text
3.9 -> int: 3
-3.9 -> int: -3
-0.0 -> int: 0
NaN -> int: 0
+Infinity -> int: 2147483647
-Infinity -> int: -2147483648
1e100 -> int: 2147483647
-1e100 -> long: -9223372036854775808
+Infinity -> long: 9223372036854775807
+Infinity -> byte: -1
-Infinity -> byte: 0
NaN -> short: 0
130.9 -> byte: -126
1e100 -> byte: -1
1e100 -> char code: 65535
NaN finite? false
checkedInt(7.0): 7
checkedInt(7.5): rejected
checkedInt(Infinity): rejected
BigDecimal out of range: rejected
```

In this example:

- The `3.9`, `-3.9`, and `-0.0` lines demonstrate that conversion to `int` **truncates toward 0**, including losing the sign of `-0.0`.
- The `NaN`, `Infinity`, and `1e100` lines demonstrate **0 or boundary clamping** when the direct target is `int`/`long`.
- The `byte` and `char` lines demonstrate **converting through `int` and then discarding high bits**.
- `checkedInt` illustrates **detecting out-of-range, non-finite, or non-integer data** instead of silently losing information.
- `BigDecimal.intValueExact()` illustrates an API that throws an exception when an exact decimal number cannot be converted to the target integer while preserving its value.

## 8. Checked conversion: rejecting data loss instead of accepting casts

If business logic needs to convert a `double` measurement to `int` and **only accepts finite whole numbers within range**, check all three conditions **before casting**:

1. **Finite:** `Double.isFinite(v)` to exclude `NaN` and ±Infinity.
2. **In range:** `Integer.MIN_VALUE <= v && v <= Integer.MAX_VALUE` (both bounds are represented exactly in `double`).
3. **No fractional part:** `v == Math.rint(v)`. `Math.rint` returns the nearest integral `double` under its rounding rule; use it **to check whether `v` is already whole**, not to silently alter data with the `rint` result.

The `checkedInt` function in the full program performs all three checks. For a `NaN` source, the `Double.isFinite` condition is especially critical: comparisons like `v < min`, `v > max`, or `v != ...` must be properly understood with NaN. Validation code should normally include an explicit `isFinite` branch to avoid accidentally accepting NaN.

If the requirement **permits truncating the fractional part** (e.g., 7.9 becoming 7), omit the `Math.rint` condition, but still check `isFinite` and the range **before** the cast. If **rounding** per a policy (nearest, floor, ceiling) is required, apply the chosen rounding rule and then **check the result's range** before converting.

### Special check for `long`: watch the positive bound

Validating a `double` to safely cast to `long` is trickier than it looks, because **`Long.MAX_VALUE` is not represented exactly as a `double`**. When converting `Long.MAX_VALUE` to `double`, the value rounds to **`2^63`**, which lies **outside the `long` range**. Therefore, the expression:

```java
// NOT a complete check for double:
if (v <= Long.MAX_VALUE) {
    // Can accept v == 2^63 as well because Long.MAX_VALUE was rounded up.
}
```

is not strict enough for the positive boundary. With a `double` source, you can check the range using two exactly representable thresholds: **`-2^63`** (allowed) and **`+2^63`** (must be rejected):

```java
static long checkedLong(double v) {
    if (!Double.isFinite(v)
            || v < -0x1.0p63   // v less than Long.MIN_VALUE
            || v >= 0x1.0p63   // v greater than or equal to 2^63
            || v != Math.rint(v)) {
        throw new IllegalArgumentException("not an in-range integer");
    }
    return (long) v;
}
```

This is an **illustrative method snippet**; place it inside a class for real use. The floating-point hex literal `0x1.0p63` represents `2^63` exactly as a `double`. Thus `checkedLong` accepts `-2^63`, but rejects `+2^63`. The `Math.rint` condition rejects values with representable fractional parts.

Also note: a `double` source already **has finite precision**. Even if the validated value is an integer, you cannot infer that every digit of a very large original integer remained intact; an earlier `long → double` conversion could have rounded it. **Final validation cannot restore information lost prior to conversion.**

### When the input is exact decimal data

If reading from JSON/decimal strings and you need to distinguish numbers with fractions, out-of-range values, or preserve exactness, consider **`BigDecimal` from a string**:

```java
int valid = new java.math.BigDecimal("2147483647.0").intValueExact();
// 2147483647

// new java.math.BigDecimal("2147483648").intValueExact();
// ArithmeticException: exceeds int range.

// new java.math.BigDecimal("7.5").intValueExact();
// ArithmeticException: has fractional part.
```

`BigDecimal.intValueExact()` and `longValueExact()` test whether conversion is possible **without losing value**. However, `BigDecimal` constructed from finite decimal strings **does not directly represent NaN or infinity**; special data must be handled by input validation rules. Creating a `BigDecimal` from an already-rounded `double` also cannot recover lost original integer digits.

## 9. Distinguishing cast, `Math.round`, and `Math.toIntExact`

| Conversion method | Primary behavior | Reports an error when out of range? |
| --- | --- | --- |
| `(int) someDouble` | Truncates fraction toward 0; NaN → 0; out of range → `int` bound | No |
| `(long) someDouble` | Same, using `long` range | No |
| `(byte) someDouble` | Through `int`, then discards high bits down to 8 bits | No |
| `Math.round(double)` | Rounds to nearest integer per API rules; returns `long` | No; NaN/±Infinity handled specially |
| `Math.round(float)` | Rounds to nearest integer per API rules; returns `int` | No; NaN/±Infinity handled specially |
| `Math.toIntExact(long)` | Converts `long` to `int` and checks range | **Yes**: `ArithmeticException` if out of range |
| `BigDecimal.intValueExact()` | Converts exact decimal value to `int`, checks fraction/range | **Yes**: `ArithmeticException` if not exact |

`Math.round` is a **rounding operation**, not synonymous with truncating toward 0 via cast: `(int) 3.9 == 3`, whereas `Math.round(3.9) == 4L`. For NaN, `Math.round` returns 0; for ±Infinity, it returns the integer bound of the return type. You must select the API matching the desired **rounding policy**.

`Math.toIntExact` **has no overload taking `double`**. Writing `Math.toIntExact((long) value)` may already have **clamped the value to the `long` range or truncated its fraction before checking**. This does not replace validating the `double` source.

When solving problems involving money, transaction IDs, pagination, quantities, or bounded measurements, specify clearly whether `NaN`/Infinity can occur, whether fractions are allowed, what the valid range is, and which rounding policy is permitted. A simple cast is appropriate only when Java's lossy semantics are acceptable.

## 10. Common misconceptions

1. **"Casting `double` to `int` wraps around like casting `long` to `int`."** False. `double → int` clamps at bounds when out of range, whereas `long → int` discards high bits.
2. **"`NaN` always throws an error when cast to an integer."** False: primitive narrowing turns NaN into 0.
3. **"`+Infinity` converted to `byte` equals `127`."** False: the `double → int` step gives `Integer.MAX_VALUE`, then `int → byte` gives `-1`.
4. **"`(int) -3.9` equals -4."** False: it truncates toward 0, so it equals -3; it is not `Math.floor`.
5. **"Out-of-range casts automatically raise `ArithmeticException`."** False: primitive casts follow conversion rules and do not throw on out-of-range values.
6. **"Checking `v <= Long.MAX_VALUE` with `double` is enough."** False at the positive bound because `Long.MAX_VALUE` rounds to `2^63` when converted to `double`.
7. **"Checking `v < min || v > max` alone catches all bad values."** False: NaN has special comparison behavior; validate finiteness explicitly.
8. **"If Infinity does not appear after casting, the data was valid."** False: very different sources all produce `MAX_VALUE`, `MIN_VALUE`, or 0.
9. **"`Math.round` and casting both strip the decimal part toward 0."** False: `Math.round` performs rounding.
10. **"`BigDecimal.valueOf(double)` automatically restores lost digits."** False: converting a large integer through `double` may have rounded earlier; lost information cannot be retrieved.

## 11. Self-check

- What does `(int) Double.NaN` equal? **0**.
- What does `(long) Double.NEGATIVE_INFINITY` equal? **Long.MIN_VALUE**.
- What does `(byte) Double.POSITIVE_INFINITY` equal? **-1**, because it converts through `int` and keeps the low 8 bits.
- What does `(int) -8.99` equal? **-8**, due to truncating the fractional part toward 0.
- What does `(int) 3_000_000_000.0` equal? **Integer.MAX_VALUE**, not the result of casting from `long`.
- Does `Math.toIntExact((long) Double.NaN)` detect NaN? **No**: casting to `long` already produced 0 before `toIntExact` received the argument.
- To accept *only* finite integer values within the `int` range, what should you do? **Check `Double.isFinite`, min/max, and no fractional part before casting**, or use an exact decimal solution appropriate for the data source.

**Remember:** converting `float`/`double` to `int`/`long` **truncates toward 0, NaN → 0, out-of-range/±Infinity → bound**. Converting to `byte`/`short`/`char` adds a **narrowing step from `int`**, so the result can be negative or unexpected. If data must be exact and valid, **validate before converting**, instead of inspecting already-lossy values after the cast.
