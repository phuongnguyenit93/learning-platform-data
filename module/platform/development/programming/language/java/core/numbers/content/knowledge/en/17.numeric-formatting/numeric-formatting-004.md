# `toHexString` for Floating-Point Numbers in Java

In Java, **`Double.toHexString(double)`** and **`Float.toHexString(float)`** represent a **floating-point value** as a **hexadecimal floating-point number with a base-2 exponent**. This is a useful way to inspect the exact significant bits of a `float`/`double` value, especially when analyzing rounding, ULP, subnormals, and the difference between `0.1f` and `0.1d`.

```java
System.out.println(Double.toHexString(3.0));   // 0x1.8p1
System.out.println(Float.toHexString(1.0f));   // 0x1.0p0
System.out.println(Double.toHexString(0.1));   // 0x1.999999999999ap-4
```

The statements above are illustrative snippets that can be placed inside a Java method. **Do not confuse `Double.toHexString` with `Integer.toHexString`**: the first outputs **floating-point notation with a decimal point and `p`**, while the second outputs **hex digits of an integer pattern**. `Double.toHexString` is also **not** a direct dump of raw IEEE 754 bits or an endian-ordered byte sequence.

## 1. The two APIs and their purpose

| API | Argument | Return | Example |
| --- | --- | --- | --- |
| `Double.toHexString(double d)` | 64-bit `double` value | Hex floating-point `String` | `Double.toHexString(1.0)` → `"0x1.0p0"` |
| `Float.toHexString(float f)` | 32-bit `float` value | Hex floating-point `String` | `Float.toHexString(1.0f)` → `"0x1.0p0"` |

Both methods are **static**, called through the `Double` or `Float` class name. You do not need to call them on wrapper objects:

```java
double x = 3.0;
String formatted = Double.toHexString(x);  // "0x1.8p1"
```

The result is a **string for inspection/logging/text-based data exchange**, without altering the original value. The method does not round to a certain number of decimal places by locale; it represents the stored binary value in the appropriate hex notation.

The string format can be misleading at first: the significand digits are **hex**, but the exponent following `p` denotes a **power of 2**, not of 16 or 10. The `p` marker is a mandatory part of the hex floating-point syntax supported by Java.

## 2. Reading the string `0x1.8p1`

A finite normal hex floating-point number generally has the form:

```text
[-]0xH.FpE
    └─┬─┘ └┬┘
      │    └── E is the exponent written in decimal digits,
      │        but denotes a power of 2
      └─────── H.F is the significand written in base 16
```

For the string `0x1.8p1`:

- `0x`: indicates the significand is in **base 16**.
- `1.8`: significand = `1 + 8/16 = 1.5`.
- `p1`: multiply the significand by `2^1 = 2`.
- Value = `1.5 × 2 = 3.0`.

```text
0x1.8p1 = (1 + 8/16) × 2^1 = 3.0
0x1.0p0 = 1 × 2^0 = 1.0
0x1.0p-1 = 1 × 2^-1 = 0.5
0x1.0p3 = 1 × 2^3 = 8.0
0x1.fp3 = (1 + 15/16) × 2^3 = 15.5
```

After the dot, **each hex digit corresponds to four binary bits**, making this notation well suited for checking how close a value is to rounding thresholds. For example, `0x1.8` has `.8` corresponding to `.1000` in binary.

**Do not read `p1` as `×10^1` or `×16^1`**. For Java hex floating-point numbers, `p` uses a base-2 exponent; the decimal exponent symbol is `e` in decimal strings like `1.5e2`.

## 3. Normal `double` and `float` print with different numbers of significand digits

Both types follow IEEE 754 binary representation but have different precisions:

| Property | `float` | `double` |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Stored fraction bits | 23 | 52 |
| Effective significand bits in normal numbers | 24 | 53 |
| Unbiased exponent in normal range | -126 to +127 | -1022 to +1023 |
| ULP around `1.0` | `2^-23` | `2^-52` |

Since one hex digit corresponds to four bits, the fraction part of a normal `double` can take up to **13 hex digits** to describe 52 bits. A normal `float` takes at most **6 hex digits** to encode 23 fraction bits (the low bit of the last digit contains padding in the written form).

Example:

```java
System.out.println(Double.toHexString(0.1d));
// 0x1.999999999999ap-4

System.out.println(Float.toHexString(0.1f));
// 0x1.99999ap-4
```

The decimal value `0.1` has no finite binary representation, so the two types round to two different representation grids. The strings above clearly reveal the **actual stored binary values**; they are not two different "decorations" for an exact `1/10` value.

The hex digits are not an optional decimal precision forced by digits after the dot. `toHexString` produces a deterministic string from the existing `float` or `double` value, without increasing the variable's precision.

## 4. Why doesn't `0x1.0p0` write out all the zero digits of the fraction?

Java outputs a **compact, canonical form**, rather than always padding all 6 or 13 fraction digits.

```java
Double.toHexString(1.0);  // "0x1.0p0"
Double.toHexString(2.0);  // "0x1.0p1"
Double.toHexString(3.0);  // "0x1.8p1"
```

In `1.0`, the fraction is all zeros, so there is no need to write `0x1.0000000000000p0`. Java still keeps **at least one digit after the dot**, because this is a hex floating-point format rather than an integer hex format.

In the normal range, the leading digit is typically `1` because a **normalized significand** of a binary number has the form `1.fraction`. This differs from the **subnormal** range, where the leading part is printed as `0.` and the exponent is kept at the smallest normal bound.

Note that a value can have **multiple mathematically equivalent strings** before normalization, such as `0x1.0p0` and `0x2.0p-1`, both equal to 1. `toHexString` chooses the normalized format per the API specification; not every string accepted by the parser will be printed back verbatim.

## 5. Normal numbers: examples of threshold representations

For `double`:

| Value | `Double.toHexString` |
| --- | --- |
| `0.5` | `0x1.0p-1` |
| `1.0` | `0x1.0p0` |
| `2.0` | `0x1.0p1` |
| `3.0` | `0x1.8p1` |
| `Math.nextUp(1.0)` | `0x1.0000000000001p0` |
| `Double.MIN_NORMAL` | `0x1.0p-1022` |
| `Double.MAX_VALUE` | `0x1.fffffffffffffp1023` |

For `float`:

| Value | `Float.toHexString` |
| --- | --- |
| `1.0f` | `0x1.0p0` |
| `Math.nextUp(1.0f)` | `0x1.000002p0` |
| `Float.MIN_NORMAL` | `0x1.0p-126` |

In particular, `Double.MAX_VALUE` has a significand just below 2 multiplied by `2^1023`. It is the **largest finite** `double`, not Infinity; the hex string `0x1.fffffffffffffp1023` makes the exact fraction and exponent limits easy to see.

When `Math.nextUp(1.0)` adds the smallest ULP step above, the last fraction bit changes:

```text
1.0                  0x1.0p0
nextUp(1.0)          0x1.0000000000001p0
Math.ulp(1.0)        0x1.0p-52
```

Hex floating-point is an especially good testing tool at **rounding** boundaries, **exponent** boundaries, and in numerical functions with errors of only a few ULPs that default decimal printing can obscure.

## 6. Subnormals: why does `0x0....p-1022` appear?

The smallest positive `double` numbers lie in the **subnormal** range, i.e., below `Double.MIN_NORMAL`. In this range there is no implicit leading `1` bit of a normal significand. Therefore, `toHexString` has the form **`0x0.fractionp-1022`**.

Java 17 example:

```java
System.out.println(Double.toHexString(Double.MIN_NORMAL));
// 0x1.0p-1022

System.out.println(Double.toHexString(Double.MIN_VALUE));
// 0x0.0000000000001p-1022
```

Here:

- `Double.MIN_NORMAL = 2^-1022`: smallest positive **normal** number.
- `Double.MIN_VALUE = 2^-1074`: smallest **non-zero positive** `double`, which is subnormal.
- In `0x0.0000000000001p-1022`, the trailing fraction has value `16^-13 = 2^-52`; multiplying by `2^-1022` gives `2^-1074`.

For `float`, the distinction is analogous, though the exponent and bit width differ:

```java
System.out.println(Float.toHexString(Float.MIN_NORMAL));
// 0x1.0p-126

System.out.println(Float.toHexString(Float.MIN_VALUE));
// 0x0.000002p-126
```

`Float.MIN_VALUE = 2^-149` and `0x0.000002` corresponds to `2^-23`; multiplying by `2^-126` yields `2^-149`.

**Do not mistake `Double.MIN_VALUE` for the smallest negative number**. It is the positive value closest to 0; the finite negative number with the largest magnitude is `-Double.MAX_VALUE`.

## 7. `+0.0`, `-0.0`, and signs in hex strings

Java uses IEEE 754 with **two zero bit patterns**:

```java
System.out.println(Double.toHexString(+0.0)); // 0x0.0p0
System.out.println(Double.toHexString(-0.0)); // -0x0.0p0
System.out.println(-0.0 == +0.0);             // true
```

The two zeros compare equal with the `==` operator, but differ in their **sign bit**. `toHexString` preserves the distinction with a leading `-` sign.

This matters if you need to distinguish results at boundaries or verify a **bit-level round-trip**. Parsing `"-0x0.0p0"` back with `Double.parseDouble` yields the negative zero bit pattern; you should not rely on `==` to test the two zero patterns.

An explicit way to check:

```java
double original = -0.0;
double parsed = Double.parseDouble(Double.toHexString(original));
boolean sameBits = Double.doubleToRawLongBits(original)
        == Double.doubleToRawLongBits(parsed); // true
```

`Math.signum`, division by zero, and other operations can also behave differently on the two zero signs. Do not strip the minus sign from hex output if you want to preserve the full floating-point semantics.

## 8. `NaN` and `Infinity` are not printed as finite hex numbers

Both `toHexString` methods return **special value names** instead of building a `0x...` number:

| Input | Resulting string |
| --- | --- |
| `Double.NaN`, `Float.NaN` | `"NaN"` |
| `Double.POSITIVE_INFINITY`, `Float.POSITIVE_INFINITY` | `"Infinity"` |
| `Double.NEGATIVE_INFINITY`, `Float.NEGATIVE_INFINITY` | `"-Infinity"` |

Example:

```java
Double.toHexString(Double.NaN);               // "NaN"
Double.toHexString(Double.POSITIVE_INFINITY); // "Infinity"
Double.toHexString(Double.NEGATIVE_INFINITY); // "-Infinity"
```

`NaN` (Not a Number) can have **many payload bit patterns**, but `toHexString` returns a single common string `"NaN"`. Therefore, **you cannot use `toHexString` output to preserve a NaN payload**. When exact bits of a `NaN` value are needed, use the appropriate raw-bits API and a transport format that stores all bits.

`Double.parseDouble("NaN")` can produce a valid NaN pattern without knowing the original value's payload. Similarly, `Float.parseFloat("NaN")` does not recover the original `float` payload. Distinguish **round-trip of special value kind** from **bit-for-bit round-trip**.

## 9. Parsing back: `Double.parseDouble` and `Float.parseFloat`

`Double.parseDouble` and `Float.parseFloat` accept both decimal floating-point notation and **hex floating-point**, provided the string follows parser rules:

```java
double d = Double.parseDouble("0x1.8p1");  // 3.0
float f = Float.parseFloat("0x1.8p1");    // 3.0f

double x = 0.1;
String hex = Double.toHexString(x);
double restored = Double.parseDouble(hex);
```

For **finite** numbers, the string format from `Double.toHexString` contains enough information to parse back into the **exact same `double` bit pattern** under Java's rules. The same holds for `Float.toHexString` and `Float.parseFloat` for `float`.

The hex string `"0x1.8p1"` is different from an integer hex string `"1A"`; do not pass it to `Integer.parseInt(...,16)` expecting a floating-point value. For hex floating-point, **`p` and the binary exponent** are key syntactic components.

Round-trip verification example:

```java
double original = Math.PI;
String valueAsText = Double.toHexString(original);
double reconstructed = Double.parseDouble(valueAsText);

boolean sameRawBits =
        Double.doubleToRawLongBits(original)
        == Double.doubleToRawLongBits(reconstructed);
```

In the finite `Math.PI` case, `sameRawBits` is `true`. For `NaN`, payloads are an exception requiring special handling; for Infinity, the string still properly identifies infinity without containing any floating-point fraction.

## 10. `toHexString` differs from `toString` and decimal formatting

| Display style | Example with `double 0.1` | Purpose |
| --- | --- | --- |
| `Double.toString(x)` | `0.1` | Short, readable decimal representation supporting round-trip per Java rules |
| `Double.toHexString(x)` | `0x1.999999999999ap-4` | Reveals the stored binary value as a hex significand and power of 2 |
| `String.format("%.2f", x)` | `0.10` | Presents decimal number by precision/locale; may round the output string |
| `Double.doubleToRawLongBits(x)` | 64-bit `long` | Extracts sign bit, exponent, and fraction pattern; not a floating-point text format |

These are distinct tasks. `Double.toString(0.1)` prints `0.1` because it is a suitable short decimal representation for the `double` value, **not proof that the stored value equals the exact decimal fraction 1/10**.

If the goal is simply reporting prices/units to readers, hex strings can be confusing and inappropriate. If the goal is **inspecting arithmetic error, rounding effects, ULP spacing, or normal/subnormal boundaries**, hex strings eliminate ambiguity about the binary significand.

`String.format("%a", x)` is also a way to present hex floating-point in Java's formatter system, though it differs in API, locale configuration, and precision. When you want a concise, consistent print format independent of format strings, `Double.toHexString`/`Float.toHexString` are direct choices.

## 11. Distinguishing `Double.toHexString` from raw IEEE 754 bits

These are **two different representations** of the same value `1.0`:

```java
System.out.println(Double.toHexString(1.0));
// 0x1.0p0

System.out.println(Long.toHexString(Double.doubleToRawLongBits(1.0)));
// 3ff0000000000000
```

The first string is the **mathematical value expressed as a hex significand times a power of 2**. The second string is the **64 IEEE 754 data bits as a hex-formatted `long` integer**, containing the sign bit, biased exponent, and fraction in fixed bit positions.

Similarly for `float`:

```java
System.out.println(Float.toHexString(1.0f));
// 0x1.0p0

System.out.println(Integer.toHexString(Float.floatToRawIntBits(1.0f)));
// 3f800000
```

Some beginners see `toHexString` and assume it prints the raw bit pattern. How to tell them apart:

- **Floating-point value form:** typically `0x1.xxxxxpE`, `0x0.xxxpE`, `-0x0.0p0`, `NaN`, or `Infinity`.
- **Raw bit-pattern form:** uses `Long.toHexString`/`Integer.toHexString` on the return value of `doubleToRawLongBits`/`floatToRawIntBits`, which is a hex string **without `p`**.

`Double.doubleToLongBits` (without `Raw`) **normalizes NaN** to a canonical pattern; if your task requires inspecting payloads, use `Double.doubleToRawLongBits`. The same applies to `Float.floatToIntBits` versus `Float.floatToRawIntBits`.

And do not confuse **raw bits** with **byte order (endianness)** on the network or in files. For byte-for-byte serialization, you also have to choose byte order and field layout; merely generating the string `0x1.0p0` does not determine the four or eight bytes transmitted.

## 12. Standalone Java 17+ example and verified stdout

Save as **`FloatingHexDemo.java`**:

```java
public class FloatingHexDemo {
    private static void showDouble(String name, double x) {
        System.out.println(name + "=" + Double.toHexString(x));
    }

    private static void showFloat(String name, float x) {
        System.out.println(name + "=" + Float.toHexString(x));
    }

    public static void main(String[] args) {
        showDouble("dZero", 0.0);
        showDouble("dNegativeZero", -0.0);
        showDouble("dOne", 1.0);
        showDouble("dHalf", 0.5);
        showDouble("dThree", 3.0);
        showDouble("dPointOne", 0.1);
        showDouble("dMinNormal", Double.MIN_NORMAL);
        showDouble("dMinSubnormal", Double.MIN_VALUE);
        showDouble("dMaxFinite", Double.MAX_VALUE);
        showDouble("dNextUpOne", Math.nextUp(1.0));
        showDouble("dPositiveInfinity", Double.POSITIVE_INFINITY);
        showDouble("dNegativeInfinity", Double.NEGATIVE_INFINITY);
        showDouble("dNaN", Double.NaN);

        showFloat("fOne", 1.0f);
        showFloat("fPointOne", 0.1f);
        showFloat("fMinNormal", Float.MIN_NORMAL);
        showFloat("fMinSubnormal", Float.MIN_VALUE);
        showFloat("fNextUpOne", Math.nextUp(1.0f));
        showFloat("fNegativeZero", -0.0f);

        System.out.println("parseHexDouble="
                + Double.parseDouble("0x1.8p1"));
        System.out.println("parseHexFloat="
                + Float.parseFloat("0x1.8p1"));
        System.out.println("negativeZeroEqualsPositiveZero="
                + (-0.0 == 0.0));
        System.out.println("negativeZeroRoundTripBits="
                + (Double.doubleToRawLongBits(-0.0)
                == Double.doubleToRawLongBits(
                        Double.parseDouble(Double.toHexString(-0.0)))));

        String textDouble = Double.toHexString(Math.PI);
        double parsedDouble = Double.parseDouble(textDouble);
        System.out.println("doubleRoundTripBits="
                + (Double.doubleToRawLongBits(Math.PI)
                == Double.doubleToRawLongBits(parsedDouble)));

        String textFloat = Float.toHexString(0.1f);
        float parsedFloat = Float.parseFloat(textFloat);
        System.out.println("floatRoundTripBits="
                + (Float.floatToRawIntBits(0.1f)
                == Float.floatToRawIntBits(parsedFloat)));

        System.out.println("floatOneRawBits="
                + Integer.toHexString(Float.floatToRawIntBits(1.0f)));
        System.out.println("doubleOneRawBits="
                + Long.toHexString(Double.doubleToRawLongBits(1.0)));

        double nanPayload = Double.longBitsToDouble(0x7ff8000000000001L);
        String nanText = Double.toHexString(nanPayload);
        System.out.println("nanText=" + nanText);
        System.out.println("nanPayloadLost="
                + (Double.doubleToRawLongBits(nanPayload)
                != Double.doubleToRawLongBits(Double.parseDouble(nanText))));
    }
}
```

Compile/run in the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 FloatingHexDemo.java
java FloatingHexDemo
```

Exact stdout:

```text
dZero=0x0.0p0
dNegativeZero=-0x0.0p0
dOne=0x1.0p0
dHalf=0x1.0p-1
dThree=0x1.8p1
dPointOne=0x1.999999999999ap-4
dMinNormal=0x1.0p-1022
dMinSubnormal=0x0.0000000000001p-1022
dMaxFinite=0x1.fffffffffffffp1023
dNextUpOne=0x1.0000000000001p0
dPositiveInfinity=Infinity
dNegativeInfinity=-Infinity
dNaN=NaN
fOne=0x1.0p0
fPointOne=0x1.99999ap-4
fMinNormal=0x1.0p-126
fMinSubnormal=0x0.000002p-126
fNextUpOne=0x1.000002p0
fNegativeZero=-0x0.0p0
parseHexDouble=3.0
parseHexFloat=3.0
negativeZeroEqualsPositiveZero=true
negativeZeroRoundTripBits=true
doubleRoundTripBits=true
floatRoundTripBits=true
floatOneRawBits=3f800000
doubleOneRawBits=3ff0000000000000
nanText=NaN
nanPayloadLost=true
```

Result analysis:

1. **Group `dZero` to `dThree`:** illustrates sign, hex significand, and binary exponent; the number 3 is represented as `0x1.8p1`.
2. **`dPointOne` and `fPointOne`:** same idea of `0.1`, but the two types store different fraction bits; `float` is less precise than `double`.
3. **`dMinNormal`, `dMinSubnormal`, `fMinNormal`, `fMinSubnormal`:** normal/subnormal boundaries and the `0x0....pE` form.
4. **`dNextUpOne`, `fNextUpOne`:** observes one floating-point grid step of each type.
5. **`dPositiveInfinity`, `dNegativeInfinity`, `dNaN`:** special cases that do not output hex significand notation.
6. **`parseHexDouble`, `parseHexFloat`:** `parseDouble` and `parseFloat` accept strings with `p` notation and return the value 3.
7. **`negativeZeroRoundTripBits`, `doubleRoundTripBits`, `floatRoundTripBits`:** verifies that parsing back preserves the bit pattern of the tested finite values, including the negative sign of zero.
8. **`floatOneRawBits`, `doubleOneRawBits`:** illustrates raw IEEE bits **differing from** `toHexString`.
9. **`nanPayloadLost=true`:** the `"NaN"` string does not encode the payload of a NaN pattern created from raw bits.

The program uses `showDouble`/`showFloat` helpers to avoid repeated `println` calls. There is only one `public class FloatingHexDemo`, matching the filename, with no libraries outside Java 17.

## 13. Application in debugging ULP, adjacent numbers, and rounding errors

Suppose an algorithm is expected to return `1.0`, yet actually returns the `double` value immediately above it:

```java
double exact = 1.0;
double actual = Math.nextUp(exact);

System.out.println(Double.toHexString(exact));  // 0x1.0p0
System.out.println(Double.toHexString(actual)); // 0x1.0000000000001p0
System.out.println(Double.toHexString(Math.ulp(exact))); // 0x1.0p-52
```

Only the last hex significand digit changed. That lets you concretely identify a single step near `1.0`, rather than vaguely noting "a small error". But be careful: at **power-of-2 boundaries**, the step above and the step below can differ. `Math.ulp(1.0)` equals `2^-52`, whereas `1.0-Math.nextDown(1.0)` equals `2^-53`. Do not treat all nearby `double` numbers as lying on a globally fixed-step grid.

When comparing the outputs of two algorithms, `toHexString` helps reveal differences in the **represented significand pattern**. Still, **differing by a few hex digits does not by itself determine which algorithm is more accurate**: you need a reference answer, an error metric (absolute/relative/ULP), and problem constraints.

In boundary testing, both decimal and hex outputs can be logged for both readability and analysis:

```java
double result = Math.nextUp(1.0);
System.out.println("decimal=" + result);
System.out.println("hex=" + Double.toHexString(result));
```

## 14. Application in data exchange

If an API exchanges **text strings** explicitly specified as Java hex floating-point syntax, you can use:

```java
String payload = Double.toHexString(0.1);
double received = Double.parseDouble(payload);
```

For **finite values**, parsing back can preserve the exact `double` bit pattern of the original value. Explicitly state in API documentation that this is a **hex floating-point string with `p`**, not an unsigned integer hex or 8-byte binary data.

However, keep in mind:

- **Recipient language/system:** many languages support an equivalent hex floating-point form, but not all JSON, CSV, or numeric parsers accept `0x1.8p1`.
- **Special values:** `NaN`, `Infinity`, and `-Infinity` need separate conventions, especially in JSON exchange standards that do not treat them as valid numbers.
- **NaN values with payloads:** do not round-trip bit-exactly via `"NaN"`.
- **Input canonicalization:** parsers may accept equivalent strings; if a canonical representation is needed for hashing/signing data, define the format clearly and check the canonical string rather than merely checking whether parsing succeeds.
- **Safety:** check length limits, valid types, and business ranges before trusting input. Java parsers throw `NumberFormatException` for malformed syntax but know nothing about application logic bounds.

If the contract requires sending the **exact 32/64 raw bits** of an IEEE 754 value, use `floatToRawIntBits`/`doubleToRawLongBits`, clearly define byte order, and encode as bytes or an 8/16-digit hex bit pattern. That is **a different format** from `toHexString`.

## 15. Common mistakes and fixes

| Confusion | Reality | Correct approach |
| --- | --- | --- |
| `Double.toHexString(3.0)` returns `"3"` or `"0x3"` | Returns `"0x1.8p1"` | Remember hex significand and base-2 exponent |
| The character `p` is a power of 10 | `pE` means multiply by `2^E` | Interpret in base 2 |
| `Float.toHexString` has the same precision as `Double.toHexString` | Float has 24 significand bits; double has 53 | Keep the type you intend to inspect |
| The method outputs a raw IEEE bit pattern | It represents the **floating-point value**, not bit fields | Use `floatToRawIntBits`/`doubleToRawLongBits` |
| `Double.MIN_VALUE` is the smallest negative number | It is the smallest positive subnormal | Distinguish `MIN_NORMAL`, `MIN_VALUE`, `MAX_VALUE` |
| Every value has the form `0x1.xxxpE` | Subnormals have the form `0x0.xxxpE` | Check subnormal boundaries |
| `-0.0` and `+0.0` must produce the same string | `toHexString` preserves the `-0.0` sign | Test both zero patterns |
| `NaN` in hex contains the full payload | Returns generic `"NaN"` | Use raw bits if bit-exactness is required |
| `Integer.parseInt("0x1.8p1",16)` reads hex floats | Not an integer syntax | Use `Double.parseDouble`/`Float.parseFloat` |
| `0.1` printed in decimal stores exact 1/10 | `double` rounds in binary | Use hex output to inspect, or `BigDecimal` for exact decimal |
| Hex floating-point implies endianness in memory | Endianness applies to byte order in serialization | Define byte order separately |
| Seeing two different hex strings immediately shows which algorithm has error | Hex only shows a representation difference | Compare against a reference answer and error threshold |

## 16. Self-check questions

1. **What does `Double.toHexString(3.0)` return?** `"0x1.8p1"` because `(1+8/16)×2=3`.
2. **What is `0x1.0p-1` equal to?** `0.5`.
3. **Does the exponent `p5` mean multiplying by `2^5` or `16^5`?** Multiplying by `2^5`.
4. **Why does `Double.toHexString(0.1)` have many hex digits while `Double.toString(0.1)` prints only `0.1`?** The hex string displays the exact stored binary significand/exponent; the short decimal string optimizes display and does not imply storing exact 1/10.
5. **Does `Double.MIN_VALUE` output in normal form `0x1...pE`?** No: `0x0.0000000000001p-1022`, because it is the smallest positive subnormal.
6. **What does `Float.MIN_VALUE` output?** `0x0.000002p-126`.
7. **How does `Double.toHexString(-0.0)` differ from `Double.toHexString(+0.0)`?** The minus sign, `-0x0.0p0` versus `0x0.0p0`.
8. **Can `Double.toHexString(Double.NaN)` preserve a NaN payload?** No, only `"NaN"`; raw bits must be used if the payload is needed.
9. **What is used to parse `0x1.8p1` back?** `Double.parseDouble("0x1.8p1")` or `Float.parseFloat(...)`, not `Integer.parseInt`.
10. **Which API must be called to print all 64 bits of `double 1.0`?** `Long.toHexString(Double.doubleToRawLongBits(1.0))`; the result is `"3ff0000000000000"`, not `"0x1.0p0"`.
11. **At `1.0`, what string does `Math.nextUp(1.0)` output?** `0x1.0000000000001p0`: one representation step above.
12. **Is using `toHexString` sufficient to send a binary wire format?** No. This is a text string; a binary wire format must separately define byte order, width, and special-value handling.

**Takeaway:** `Double.toHexString` and `Float.toHexString` represent a **binary floating-point value** in the form `0xH.FpE`, where **the fraction is written in hex and the exponent is a power of 2**. This form is especially useful for debugging precision, ULP, normal/subnormal values, and signed zero. To parse back, use `Double.parseDouble`/`Float.parseFloat`; to preserve exact raw IEEE bit patterns or NaN payloads, use **RawBits** APIs, and do not confuse them with `toHexString`.