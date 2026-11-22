# `Float.toString`, `Double.toString`, and the Round-Trip Property in Java

> **Java core – numbers · Representation and Formatting**  
> **Goal:** Understand why a `float`/`double` value is printed as a short decimal string yet still parses back to the exact same binary value; distinguish *round-trip* from exact mathematical decimal representation; handle signed zero, subnormals, Infinity, NaN, and choose appropriate formatting when storing, exchanging, or displaying data.

## 1. Central question: why does Java print 0.1 instead of a long sequence of digits?

Run:

```java
double value = 0.1;
System.out.println(Double.toString(value)); // 0.1
System.out.println(Double.toHexString(value));
// 0x1.999999999999ap-4
```

The `double` value here is **not the exact mathematical fraction 1/10**. It is one of the binary numbers representable in IEEE 754 *binary64* that lies very close to 0.1.

So why does `Double.toString(value)` return only `"0.1"` instead of printing the entire decimal expansion of the stored binary number? Because the goal of `toString` is to produce a **compact decimal string sufficient to identify the original floating-point value when parsed back**, not to output every digit of the exact binary rational value.

More precisely, for a finite `double` value:

```java
double original = 0.1;
String text = Double.toString(original);
double recovered = Double.parseDouble(text);

System.out.println(text);                 // 0.1
System.out.println(recovered == original); // true
```

The string `"0.1"` describes the mathematical real number 0.1. When `Double.parseDouble` rounds that real number to the nearest `double`, it obtains the **exact stored binary64 value**.

**Distinguish these two statements:**

- "Printing and parsing back preserves the *original `double` value*" — this is the *round-trip* property.
- "The printed string describes *every exact decimal digit of the binary value*" — this is **not** what `Double.toString` promises.

## 2. `toString` and `parse` form a round-trip pair

The two typical API pairs are:

```java
String floatText = Float.toString(floatValue);
float restoredFloat = Float.parseFloat(floatText);

String doubleText = Double.toString(doubleValue);
double restoredDouble = Double.parseDouble(doubleText);
```

A *round-trip* is the journey:

```text
float bits (32 bits)
    └── Float.toString(float)
             └── decimal text
                      └── Float.parseFloat(text)
                               └── original float value

double bits (64 bits)
    └── Double.toString(double)
             └── decimal text
                      └── Double.parseDouble(text)
                               └── original double value
```

For **finite non-NaN** values, parsing the exact string produced by `toString` with the **same-type parser** restores the original floating-point value; this includes normal numbers, subnormals, and both signed zeros.

For `+Infinity` and `-Infinity`, the special strings parse back to the corresponding infinities.

For **NaN**, `toString` returns `"NaN"` and the parser produces a NaN, but **it is not guaranteed to preserve the sign or payload bits of each individual NaN**. There are many IEEE 754 bit patterns representing NaN, and they collapse into one common string.

### Checking round-trip via raw bits

For finite numbers, bit-inspection operations should be used for an exact check:

```java
double before = -0.0;
String text = Double.toString(before); // "-0.0"
double after = Double.parseDouble(text);

boolean sameBits = Double.doubleToRawLongBits(before)
        == Double.doubleToRawLongBits(after);
System.out.println(sameBits); // true
```

`before == after` is not strong enough to verify the sign of zero, because `+0.0 == -0.0` is `true` in Java arithmetic comparisons. For `float`, use `Float.floatToRawIntBits` and `Float.intBitsToFloat` when inspecting/encoding bits.

## 3. Digit rules of `toString` in Java 17

The Java 17 documentation describes printing decimal digits so that they are **just enough to distinguish the value being printed from adjacent floating-point values**, with extra digits kept to the minimum necessary.

For a finite, non-zero value, an appropriate decimal representation must round back to the original value when parsed under *round to nearest, ties to even*. The format also requires **at least one digit after the decimal point**, even when the value is a representable integer.

Examples:

```java
System.out.println(Float.toString(1.0f));  // 1.0
System.out.println(Double.toString(1.0)); // 1.0
```

`"1"` could be parsed into the same numeric value, but Java's `toString` format chooses `"1.0"`. Therefore, calling it the "shortest string" should be understood as a **short decimal representation following the specified formatting rules, sufficient to distinguish the value**, not necessarily the string with the fewest characters in every arbitrary text grammar.

**There is no fixed number of decimal digits** for all `float` or `double` values. Each value may need a different number of digits to distinguish it from its immediate representable neighbors. That is why Java sometimes prints `0.1`, and other times prints a longer number like `0.30000000000000004`.

**Version warning:** the digit-selection/formatting algorithm of `toString` has been improved across JDK versions. When tests require **exact character-by-character output**, target the specific Java version and follow that version's API contract. The property to protect in this lesson is the ability to parse back to the **same binary value**, rather than treating every output string across all JDK versions as immutable over time.

## 4. When does Java use plain decimal notation, and when does it use E?

According to formatting rules in Java 17, for a **finite non-zero positive magnitude**:

- From `10^-3` (inclusive) up to strictly less than `10^7`: displayed in plain decimal notation.
- Less than `10^-3` or `10^7` and above: displayed in *computerized scientific notation*, with an uppercase `E` and a decimal exponent.

Examples:

| Input `double` value | `Double.toString` |
| --- | --- |
| `0.0` | `"0.0"` |
| `-0.0` | `"-0.0"` |
| `1.0` | `"1.0"` |
| `0.001` | `"0.001"` |
| `0.0001` | `"1.0E-4"` |
| `1_000_000.0` | `"1000000.0"` |
| `10_000_000.0` | `"1.0E7"` |

Notes:

- `"1.0E7"` and `"10000000.0"` describe the same mathematical real number; this is a **formatting choice**.
- `E7` means **times 10^7**, not a binary exponent.
- `toString` does not use thousands grouping separators, currency symbols, or locale-dependent decimal commas.
- The decimal point of the default format is `.`, making the string easy to exchange across systems sharing the same convention.

**Do not use** `Float.toString` or `Double.toString` as user-facing formatting across all countries: localized UIs require `NumberFormat` or a formatting API with a specified `Locale`.

## 5. `Float` and `Double`: same written value, different bits

`float` and `double` have different precisions:

| Type | IEEE 754 Format | Effective significand precision bits (normal) |
| --- | --- | --- |
| `float` | binary32, 32 bits | 24 |
| `double` | binary64, 64 bits | 53 |

Observe:

```java
float f = 0.1f;
double d = 0.1;
double widened = f; // widening float -> double

System.out.println(Float.toString(f));    // 0.1
System.out.println(Double.toString(d));   // 0.1
System.out.println(Double.toString(widened));
// 0.10000000149011612
```

Why do `f` and `d` both print `"0.1"`, yet `widened` is different?

1. `0.1f` is rounded to a **binary32** value near 0.1.
2. `0.1` is rounded directly to a **binary64** value near 0.1, which is more accurate.
3. When converting `float f` to `double`, the binary32 value is preserved exactly in binary64; it **does not turn into the value of the `double 0.1` literal**.
4. The string `"0.10000000149011612"` is sufficient to distinguish that widened `double` value.

This also explains a pitfall:

```java
float f = 0.1f;
double fromFloatBits = (double) f;
double parsedAsDouble = Double.parseDouble(Float.toString(f));

System.out.println(fromFloatBits == parsedAsDouble); // false
```

`Float.toString(f)` guarantees round-trip **when using `Float.parseFloat`**. If you read that string with `Double.parseDouble`, you are parsing a decimal value into a **different format**, not directly decoding all bits of `float`.

**Rule:** When you need to preserve a `float` value, store and parse with the `float` type; when you need to preserve a `double` value, use the `double` API pair. Do not silently swap the target parser to a different type and assume all conversions remain identical.

## 6. Distinguishing a round-trip string from an exact decimal value

The `double 0.1` value is actually a finite binary rational number whose full decimal representation is much longer than `"0.1"`:

```java
import java.math.BigDecimal;

double d = 0.1;
System.out.println(Double.toString(d));
// 0.1

System.out.println(new BigDecimal(d));
// 0.1000000000000000055511151231257827021181583404541015625
```

The two strings differ because:

- `Double.toString(d)` picks text **compact enough to parse back to `d`**.
- `new BigDecimal(d)` constructs the decimal value describing the **exact existing binary64 value**, which may require many digits.

Similarly:

```java
System.out.println(BigDecimal.valueOf(0.1)); // 0.1
```

`BigDecimal.valueOf(double)` uses the canonical decimal representation of `double` (per `Double.toString`) to create a `BigDecimal`. This is a reasonable conversion choice in many situations, **but it cannot recover arithmetic intent or bits already lost** in earlier calculations.

If the original business source is a decimal string requiring exactness (such as money), consider constructing:

```java
BigDecimal exact = new BigDecimal("0.1");
```

Do not take an already-computed `double` result and assume `BigDecimal.valueOf(result)` turns the entire calculation history infinitely exact.

## 7. Subnormals and boundaries: strings can be very short even for tiny numbers

Example:

```java
System.out.println(Float.toString(Float.MIN_VALUE));
// 1.4E-45
System.out.println(Double.toString(Double.MIN_VALUE));
// 4.9E-324
```

`Float.MIN_VALUE` and `Double.MIN_VALUE` are the **smallest non-zero positive numbers** representable by their respective types, belonging to the *subnormal* range. Their exact binary values are:

\[
\mathrm{Float.MIN\_VALUE} = 2^{-149}
\]
\[
\mathrm{Double.MIN\_VALUE} = 2^{-1074}
\]

The strings `"1.4E-45"` and `"4.9E-324"` do not display all decimal digits of these two values. They are sufficient for the parser to round back to the **exact smallest subnormal bit** of the target type.

Largest boundary values:

```java
System.out.println(Float.toString(Float.MAX_VALUE));
// 3.4028235E38
System.out.println(Double.toString(Double.MAX_VALUE));
// 1.7976931348623157E308
```

Important points when serializing:

- Do not impose a fixed limit like "real numbers must have at most 6 digits after the decimal point" and expect round-trip for every `double`.
- Very large/very small values require an **E exponent**; the parser reads the canonical string back accurately if the matching API is used.
- Values in the subnormal range are sensitive to additional rounding; do not arbitrarily format them shorter.

## 8. Signed zeros: `+0.0` and `-0.0` must be distinguished when inspecting bits

IEEE 754 has two representations of zero:

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(Double.toString(positiveZero)); // 0.0
System.out.println(Double.toString(negativeZero)); // -0.0
```

The `==` operator treats both zeros as equal in **numeric value**, yet `Double.toString` preserves the minus sign.

```java
double recovered = Double.parseDouble("-0.0");
System.out.println(Double.doubleToRawLongBits(recovered)
        == Double.doubleToRawLongBits(-0.0)); // true
```

When digitally signing data, distinguishing bit representations, or running exact tests, the `-0.0` sign can carry useful information. In many mathematical comparisons, however, both zeros are equivalent in value.

Similarly for `float`:

```java
float negativeZero = -0.0f;
String text = Float.toString(negativeZero); // "-0.0"
float restored = Float.parseFloat(text);
```

If you need to preserve **the entire bit pattern of non-NaN numbers**, use a same-type round-trip and verify with `floatToRawIntBits`/`doubleToRawLongBits`.

## 9. `NaN` and `Infinity`: special cases of round-trip

Three important strings:

| Value | String from `Double.toString` / `Float.toString` |
| --- | --- |
| `Double.POSITIVE_INFINITY` | `"Infinity"` |
| `Double.NEGATIVE_INFINITY` | `"-Infinity"` |
| `Double.NaN` | `"NaN"` |

Example:

```java
double pos = Double.parseDouble("Infinity");
double neg = Double.parseDouble("-Infinity");
double nan = Double.parseDouble("NaN");

System.out.println(Double.isInfinite(pos)); // true
System.out.println(neg < 0.0);              // true
System.out.println(Double.isNaN(nan));      // true
```

### Why doesn't `NaN` have raw-bit round-trip like finite numbers?

IEEE 754 has many NaN bit patterns, with different signs and payloads. However, `Double.toString` returns the same text `"NaN"` for NaN, so **this text carries no information about the payload or sign bit**. When parsed back, the result is a NaN, not a guarantee to reproduce the exact raw bits of the original NaN.

Conceptual example:

```java
long raw = 0x7ff8000000000001L; // NaN with a payload different from the canonical value
double customNan = Double.longBitsToDouble(raw);

String text = Double.toString(customNan); // "NaN"
double parsed = Double.parseDouble(text);

System.out.println(Double.isNaN(parsed)); // true
// Do not infer that Double.doubleToRawLongBits(parsed) == raw.
```

If you need to transmit or record **all IEEE 754 raw bits**, including NaN payloads, use explicit bit encoding (such as `Double.doubleToRawLongBits` and a fixed-width hex format) along with the reverse API `Double.longBitsToDouble`. Byte order, signedness, and JSON/transport rules must also be agreed upon when exchanging over a network.

**Note:** Standard JSON **does not have `NaN` or `Infinity` literals**. Java's `"NaN"` string suits Java parsers, but putting an unquoted `NaN` token directly into standard JSON makes the data invalid.

## 10. How are `toString`, `String.valueOf`, and `println` related?

Common ways to print:

```java
double x = 12.5;
String a = Double.toString(x);
String b = String.valueOf(x);
System.out.println(x);
```

For a regular primitive `double`, `String.valueOf(double)` uses the conversion corresponding to `Double.toString`, and `println(double)` also provides a display string according to Java's conversion semantics. For the `Double` wrapper, calling `wrapper.toString()` returns the string of the underlying value.

```java
Double wrapper = Double.valueOf(12.5);
String text = wrapper.toString(); // "12.5"
```

However:

```java
Double maybe = null;
// String text = maybe.toString(); // NullPointerException
String text = String.valueOf(maybe); // "null"
```

The two methods differ when the object reference is `null`: `String.valueOf(Object)` can return `"null"`. The string `"null"` is **not** a valid number for `Double.parseDouble` to read as a numeric value; API designs must represent null separately.

Similarly, when `Float wrapper = null`, `wrapper.toString()` also throws NPE, whereas `String.valueOf(wrapper)` can return `"null"`.

## 11. Round-trip is not the same as fixed-digit display formatting

For example, a UI wants to print exactly 2 digits after the decimal point:

```java
import java.util.Locale;

double pi = Math.PI;

String display = String.format(Locale.ROOT, "%.2f", pi);
System.out.println(display); // 3.14

double parsed = Double.parseDouble(display);
System.out.println(parsed == pi); // false
```

Two-decimal fixed formatting has **rounded away precision information**, so the original `Math.PI` cannot be recovered.

Compare with the round-trip approach:

```java
String canonical = Double.toString(Math.PI);
System.out.println(canonical); // 3.141592653589793
System.out.println(Double.parseDouble(canonical) == Math.PI); // true
```

**Use the right tool for the purpose:**

| Goal | Usually suitable API |
| --- | --- |
| Java string that parses back to the same `float` | `Float.toString` ↔ `Float.parseFloat` |
| Java string that parses back to the same `double` | `Double.toString` ↔ `Double.parseDouble` |
| Printing numbers for humans, thousands grouping, regional decimal separator | `NumberFormat` with a chosen `Locale` |
| Fixed 2 decimal places for report display | `String.format(Locale.ROOT, "%.2f", x)` or business formatting |
| Decimal precision by scale/rounding needed | `BigDecimal` with defined construction/rounding rules |
| Preserving IEEE 754 bits including NaN payloads | Raw bits + explicitly specified binary/hex encoding |

Avoid using `String.format("%.2f", x)` to serialize floating-point numbers needing an exact round-trip. Conversely, `Double.toString` does not automatically satisfy an invoice requirement of "always having exactly 2 decimal places".

## 12. How to test round-trip properly?

### 12.1. Use bits for finite numbers and signed zero

```java
static boolean doubleRoundTrips(double x) {
    if (Double.isNaN(x)) {
        return Double.isNaN(
                Double.parseDouble(Double.toString(x)));
    }
    double y = Double.parseDouble(Double.toString(x));
    return Double.doubleToRawLongBits(x)
            == Double.doubleToRawLongBits(y);
}
```

This is an illustrative method to be placed inside a class. It checks bits for every **non-NaN** value, including both zeros and Infinity; for NaN, it checks that **NaN status is preserved**, without requiring identical payloads.

For `float`, a similar test pattern:

```java
static boolean floatRoundTrips(float x) {
    if (Float.isNaN(x)) {
        return Float.isNaN(
                Float.parseFloat(Float.toString(x)));
    }
    float y = Float.parseFloat(Float.toString(x));
    return Float.floatToRawIntBits(x)
            == Float.floatToRawIntBits(y);
}
```

If `Double.doubleToLongBits` is used instead of `Double.doubleToRawLongBits`, NaN patterns will be **canonicalized**. That is useful in certain value comparisons but **does not reflect the original raw payload**. Clarify whether you want to test "same floating-point value" or "same bit pattern".

### 12.2. What should the test dataset include?

- `+0.0`, `-0.0`;
- normal numbers like `1.0`, `0.1`, `Math.PI`;
- subnormal numbers like `Double.MIN_VALUE`, `Float.MIN_VALUE`;
- normal boundaries like `Float.MIN_NORMAL`, `Double.MIN_NORMAL`;
- largest finite boundaries like `Float.MAX_VALUE`, `Double.MAX_VALUE`;
- positive/negative `Infinity` and `NaN`;
- large numbers with ULP > 1 to check for information loss when converting through other data types.

A good test does not just inspect strings visually; it **parses with the exact matching type** and checks the result against the criteria to preserve.

## 13. Avoid confusing decimal formatting with hex floating-point representation

Besides decimal `toString`, Java also has:

```java
System.out.println(Double.toHexString(0.1));
// 0x1.999999999999ap-4
System.out.println(Float.toHexString(0.1f));
// 0x1.99999ap-4
```

This describes the **binary value** using a base-16 significand and an exponent **of 2** (character `p`/`P`).

For example, `0x1.8p1` represents `1.5 × 2^1 = 3.0`, not `1.8 × 10^1`.

`Double.parseDouble` and `Float.parseFloat` accept valid hex floating-point syntax, so `toHexString` is also useful when exact binary arithmetic needs to be written in text form.

However, `toHexString` still prints `"NaN"` for NaN; thus it is **not** a way to serialize NaN payloads via a value-representation string. Use raw-bits APIs when that is needed.

**Comparison:**

- `Double.toString(0.1)` → `"0.1"`: readable decimal form, sufficient for round-trip.
- `Double.toHexString(0.1)` → `"0x1.999999999999ap-4"`: explicitly reveals the stored binary value.
- `Long.toHexString(Double.doubleToRawLongBits(0.1))` → hex string of the **64 storage bits**, reflecting sign bit, exponent, and fraction rather than the `0x...p...` numeric formula.

The three forms serve different purposes. Do not mix them when defining a data protocol or comparing output.

## 14. Complete Java 17+ program

Create the file **`FloatingPointRoundTripDemo.java`**:

```java
import java.util.Locale;

public class FloatingPointRoundTripDemo {
    private static boolean sameDoubleBits(double a, double b) {
        return Double.doubleToRawLongBits(a)
                == Double.doubleToRawLongBits(b);
    }

    private static boolean sameFloatBits(float a, float b) {
        return Float.floatToRawIntBits(a)
                == Float.floatToRawIntBits(b);
    }

    public static void main(String[] args) {
        float f = 0.1f;
        double d = 0.1;
        double widenedFloat = f;

        System.out.println("float text = " + Float.toString(f));
        System.out.println("double text = " + Double.toString(d));
        System.out.println("widened float = "
                + Double.toString(widenedFloat));
        System.out.println("double hex = " + Double.toHexString(d));

        float parsedF = Float.parseFloat(Float.toString(f));
        double parsedD = Double.parseDouble(Double.toString(d));
        System.out.println("float round-trip = "
                + sameFloatBits(f, parsedF));
        System.out.println("double round-trip = "
                + sameDoubleBits(d, parsedD));

        double parsedFloatTextAsDouble =
                Double.parseDouble(Float.toString(f));
        System.out.println("wrong target type = "
                + (widenedFloat == parsedFloatTextAsDouble));

        System.out.println("float minimum = "
                + Float.toString(Float.MIN_VALUE));
        System.out.println("double minimum = "
                + Double.toString(Double.MIN_VALUE));
        System.out.println("double maximum = "
                + Double.toString(Double.MAX_VALUE));

        System.out.println("plain lower = "
                + Double.toString(0.001));
        System.out.println("scientific lower = "
                + Double.toString(0.0001));
        System.out.println("plain upper = "
                + Double.toString(1_000_000.0));
        System.out.println("scientific upper = "
                + Double.toString(10_000_000.0));

        double negativeZero = -0.0;
        double restoredZero =
                Double.parseDouble(Double.toString(negativeZero));
        System.out.println("negative zero = "
                + Double.toString(negativeZero));
        System.out.println("negative zero round-trip = "
                + sameDoubleBits(negativeZero, restoredZero));
        System.out.println("signed zeros == = "
                + (+0.0 == -0.0));

        System.out.println("infinity = "
                + Double.toString(Double.POSITIVE_INFINITY));
        System.out.println("NaN parsed = "
                + Double.isNaN(
                        Double.parseDouble(Double.toString(Double.NaN))));

        String display = String.format(Locale.ROOT, "%.2f", Math.PI);
        System.out.println("display Pi = " + display);
        System.out.println("display round-trip = "
                + sameDoubleBits(Math.PI,
                        Double.parseDouble(display)));
    }
}
```

Run from the directory containing the file:

```bash
javac FloatingPointRoundTripDemo.java
java FloatingPointRoundTripDemo
```

**Expected output on Java 17:**

```text
float text = 0.1
double text = 0.1
widened float = 0.10000000149011612
double hex = 0x1.999999999999ap-4
float round-trip = true
double round-trip = true
wrong target type = false
float minimum = 1.4E-45
double minimum = 4.9E-324
double maximum = 1.7976931348623157E308
plain lower = 0.001
scientific lower = 1.0E-4
plain upper = 1000000.0
scientific upper = 1.0E7
negative zero = -0.0
negative zero round-trip = true
signed zeros == = true
infinity = Infinity
NaN parsed = true
display Pi = 3.14
display round-trip = false
```

**What the program verifies:**

1. `0.1f` and `0.1` both have the short decimal representation `0.1`, yet are different binary values; widening `float` to `double` makes the difference visible.
2. `toString` → `parseXxx` of the same type preserves the raw bits of `0.1f`/`0.1`.
3. Parsing the text of `Float.toString(f)` with `Double.parseDouble` can yield a `double` different from the `double` converted from `f`.
4. Extremely small/large values have compact scientific representations and can be parsed back by the corresponding parser.
5. The string `"-0.0"` preserves the sign bit across a round-trip; the arithmetic comparison `+0.0 == -0.0` remains true.
6. `NaN` is restored by **value kind**, without guaranteeing payload; fixed two-digit formatting loses precision on `Math.PI`.

## 15. Common mistakes to avoid

| Misconception | Correct explanation |
| --- | --- |
| "`Double.toString(0.1)` returning 0.1 means double stores exact 1/10" | The string is chosen to parse back to the same binary value; the stored value is still an approximation near 1/10 |
| "If Float and Double both print 0.1, their raw bits have the same numeric value" | The two types have different precisions; widening `0.1f` gives `0.10000000149011612` |
| "A round-trip string can have any number of digits and still stay intact" | Further shortening/rounding can turn it into a different value when parsed |
| "Round-trip means preserving all bits of every NaN" | The `"NaN"` string does not preserve NaN payload/sign |
| "Using `==` to test round-trip is enough even for -0.0" | `+0.0 == -0.0`; raw bit comparison is needed if signed zero matters |
| "`Double.toString` always prints decimal without E" | Java uses `E` when the magnitude is outside the plain decimal display range |
| "`String.format("%.2f")` allows an exact round-trip" | This format restricts digits and can lose precision |
| "`Double.toHexString` is raw 64-bit hex" | `0x...p...` represents the binary value; raw bits require `doubleToRawLongBits` |
| "`String.valueOf(null Double)` is always the same as calling `wrapper.toString`" | `String.valueOf(Object)` returns `"null"`; calling a method on null throws NPE |
| "Increasing the number of printed digits can fix arithmetic errors that already occurred" | Formatting cannot restore information lost during prior arithmetic/rounding |
| "Locale never affects display formatting" | `NumberFormat`/`String.format` can be locale-sensitive; `Double.toString` is a locale-independent Java format |
| "`Infinity` and `NaN` are valid as numbers in standard JSON" | Standard JSON lacks these literals; protocols must define how to handle them |
| "Every JDK must print identical characters across all number-conversion algorithms" | When comparing literal output, you must know the JDK contract/version; the primary goal is a value-preserving round-trip |

## 16. Exercises with solutions

**Exercise 1.** Why does `Double.toString(0.1)` return `"0.1"` even though `new BigDecimal(0.1)` prints many more digits?  
**Solution:** `toString` finds decimal text short enough to parse back to the same `double`; `new BigDecimal(double)` describes the exact stored binary value in decimal.

**Exercise 2.** With `float f = 0.1f;`, does `Float.parseFloat(Float.toString(f))` recover the original `float` value?  
**Solution:** Yes. That is the proper API pair guaranteeing round-trip for `float`, including the bit pattern of non-NaN values.

**Exercise 3.** Why is `Double.parseDouble(Float.toString(0.1f))` not necessarily equal to `(double)0.1f`?  
**Solution:** The string `"0.1"` was chosen to parse **back to `float`**. When parsed directly into `double`, it becomes the binary64 value nearest 0.1 rather than the binary64 value representing the exact widened binary32 value.

**Exercise 4.** What does `Double.toString(-0.0)` print? Does `Double.parseDouble` preserve the sign of zero?  
**Solution:** It prints `"-0.0"` and parses back to negative zero. Verify raw bits with `Double.doubleToRawLongBits`; `==` cannot distinguish ±0.

**Exercise 5.** What string does `Double.toString(Double.MIN_VALUE)` return, and does it print the entire exact decimal expansion of `2^-1074`?  
**Solution:** `"4.9E-324"` on Java 17. It is a string sufficient to parse back to `Double.MIN_VALUE`, not every decimal digit of the exact binary rational value.

**Exercise 6.** Since `Double.toString(Double.NaN)` returns `"NaN"`, can any original NaN payload be recreated with `parseDouble`?  
**Solution:** No. It is only guaranteed to parse into a NaN. If payloads must be preserved, raw bits must be serialized.

**Exercise 7.** Explain why `String.format(Locale.ROOT, "%.2f", Math.PI)` does not guarantee round-trip.  
**Solution:** It produces `"3.14"`, dropping the digits needed to distinguish `Math.PI` from neighboring `double`s. Parsing it back yields a different `double`.

**Exercise 8.** In what form does `Double.toString` print `10_000_000.0` in Java 17?  
**Solution:** `"1.0E7"`, because the range using plain decimal notation only includes magnitudes strictly less than `10^7`.

**Exercise 9.** Which API is suitable for writing the exact bit pattern of NaNs with different payloads?  
**Solution:** `Double.doubleToRawLongBits` or `Float.floatToRawIntBits`, then encode the bits yourself per your data format; when reading, use `Double.longBitsToDouble` or `Float.intBitsToFloat`.

**Exercise 10.** Can `Double.toString` replace invoice formatting that always requires exactly two fractional digits?  
**Solution:** No. It is optimized for parseable floating-point value strings, and does not guarantee fractional length or financial rounding rules. Choose `BigDecimal` and format according to the contract.

## 17. Checklist for float and double I/O

1. **Determine the goal:** outputting for human reading, storing/exchanging with round-trip, or preserving raw bits?
2. **Use matching type pairs:** `Float.toString` ↔ `Float.parseFloat`; `Double.toString` ↔ `Double.parseDouble`.
3. **Do not infer backward from text:** a string `0.1` does not mean binary floating-point stores exact decimal 0.1.
4. **Do not use few-digit formatting** if bit values must be preserved; especially for numbers with small ULP or complex computation chains.
5. **Check signed zero:** `-0.0` may need to be preserved; raw bit comparison is worthwhile when testing serialization.
6. **Handle `NaN` separately:** text round-trip preserves NaN status but does not guarantee payload; `Infinity` must also be allowed by the protocol.
7. **Recognize scientific notation:** `E` is a power of 10; `p` in `toHexString` is a power of 2.
8. **Check locale/protocol:** `toString` is stable per Java rules, while UIs and JSON/CSV have their own formatting constraints.
9. **If decimal exactness is needed**, store from a `String` source or use `BigDecimal` per business rules, rather than converting types after `double` has already rounded in hopes of "recovering data".
10. **Test boundaries:** ±0, subnormals, max, infinity, NaN, and the difference between widening `float → double` and parsing decimal into `double`.

### Java 17 Documentation

- [Float – toString, parseFloat, toHexString, floatToRawIntBits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html)
- [Double – toString, parseDouble, toHexString, doubleToRawLongBits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html)
- [BigDecimal – constructor from double and valueOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

**Takeaway:** `Float.toString` and `Double.toString` choose decimal text **sufficient to parse back to the exact floating-point value**, rather than outputting the full mathematical decimal of the bit pattern. Use the **same-type** parser, inspect bits when distinguishing signed zeros, handle `NaN` separately, and choose dedicated formats when the requirement is UI display, currency, or preserving raw bits.