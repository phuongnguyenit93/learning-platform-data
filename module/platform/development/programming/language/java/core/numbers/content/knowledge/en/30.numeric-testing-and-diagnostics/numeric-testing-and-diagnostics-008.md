# Testing Parse, Format, and Radix Round-Trips in Java

## 1. What Is a Round-Trip and Why Must It Be Tested?

Numeric data often passes through two conversion directions:

```text
Numeric value -> format/toString -> text string
Text string   -> parse           -> numeric value
```

A **round-trip** is a conversion out and back again. Given a value `x` and a corresponding formatting/parsing mechanism, we want to verify:

```text
parse(format(x)) == x
```

However, the `==` symbol here must be clearly defined: **equal in numerical value**, **equal in all representation attributes** (such as `BigDecimal` scale), or **bitwise identical** (such as the negative sign of `-0.0` in `double`)?

An important example:

```java
BigDecimal a = new BigDecimal("1E+3");   // value 1000, scale -3
BigDecimal b = new BigDecimal(a.toPlainString()); // "1000", scale 0

System.out.println(a.compareTo(b) == 0); // true: same numerical value
System.out.println(a.equals(b));         // false: different scales
```

Thus, the string `"1000"` suffices to recover the **numerical value** yet does not suffice to recover the original **scale** of `1E+3`. If a system stores formatting or granularity via scale, a test using only `compareTo()` will miss the bug.

Round-trip testing is especially critical when numbers pass through configuration, CSV/JSON files, cross-system messages, display formats, and bases 2/8/10/16/36.

## 2. Three Levels to Test

| Round-trip level | Criterion | Example |
| --- | --- | --- |
| **Preserve numerical value** | Parses back to the same numeric value | `new BigDecimal("1E+3").compareTo(new BigDecimal("1000")) == 0` |
| **Preserve representation attributes** | Besides value, preserves scale, zero sign, etc. per contract | `BigDecimal.equals()` checks both value and scale |
| **Preserve bits** | Every bit of the numeric type after parsing matches the original | `Double.doubleToRawLongBits(a) == Double.doubleToRawLongBits(b)` |

Not every problem needs the same level. Values displayed to humans may allow rounding. Storage encodings meant to reconstruct an object faithfully may require preserving bits or representation attributes.

You must also distinguish the **original input string** from the **canonicalized string**. For instance, `Integer.parseInt("+00042")` yields 42, whereas `Integer.toString(42)` produces `"42"`. Value round-trip succeeds, while verbatim text round-trip fails. If preserving the `+` sign or leading zeros is required, store the original string as well.

## 3. Signed Integer Round-Trips Across Radices

### 3.1. `Integer.toString` and `Integer.parseInt`

For an `int value` and a valid `radix` in the range **2 to 36**:

```java
int value = -255;
String text = Integer.toString(value, 16); // "-ff"
int parsed = Integer.parseInt(text, 16);   // -255
```

Contract to test:

```java
Integer.parseInt(Integer.toString(value, radix), radix) == value
```

For every `int` value, including `Integer.MIN_VALUE` and `Integer.MAX_VALUE`, when both formatting and parsing use the same radix 2..36. Letters representing digits greater than 9 follow `a..z` or `A..Z` during parsing, while `toString` produces lowercase letters.

`Long.toString(longValue, radix)` and `Long.parseLong(text, radix)` work the same way for 64-bit integers.

Illustration table for one value:

| Radix | `Integer.toString(255, radix)` | `Integer.parseInt(text, radix)` |
| ---: | --- | ---: |
| 2 | `11111111` | 255 |
| 8 | `377` | 255 |
| 10 | `255` | 255 |
| 16 | `ff` | 255 |
| 36 | `73` | 255 |

`radix` is a parameter when parsing; `"ff"` cannot be decoded in base 10. `Integer.parseInt("ff", 16)` gives 255, whereas `Integer.parseInt("ff", 10)` throws `NumberFormatException`.

### 3.2. Negative Signs and Two's-Complement Bit Forms

Do not confuse:

```java
Integer.toString(-1, 16); // "-1"
Integer.toHexString(-1);   // "ffffffff"
```

`Integer.toString(value, radix)` formats a **signed number** with a `-` sign. Conversely, `Integer`'s `toHexString`, `toBinaryString`, and `toOctalString` use the **unsigned form of the two's-complement bit pattern**. Hence `Integer.toHexString(-1)` produces an 8-character string of `f`s.

If you want to restore the bit pattern from `"ffffffff"`, use:

```java
int bits = Integer.parseUnsignedInt("ffffffff", 16);
// bits == -1 under signed int interpretation;
// Integer.toUnsignedLong(bits) == 4294967295L
```

Do not use `Integer.parseInt("ffffffff", 16)` because 4,294,967,295 exceeds the signed `int` range.

### 3.3. Parsing Unsigned Values

Use `Integer.toUnsignedString(value)` and `Integer.parseUnsignedInt(text)` when text represents an **unsigned** 32-bit integer:

```java
int rawBits = -1;
String unsignedText = Integer.toUnsignedString(rawBits); // "4294967295"
int restoredBits = Integer.parseUnsignedInt(unsignedText); // -1
boolean sameBits = rawBits == restoredBits; // true
```

The final `-1` in `int` is the **restored original bit pattern**, not a failed parse. Likewise, Java provides `Long.toUnsignedString` and `Long.parseUnsignedLong`.

### 3.4. Radix Prefixes Are Not Automatically Accepted by `parseInt`

`Integer.parseInt("0xff", 16)` **does not** accept the `0x` prefix and throws `NumberFormatException`. `parseInt` itself parses only a valid sequence of digits (with an optional leading `+`/`-` sign) in the given radix.

`Integer.decode("0xff")` accepts prefix notations such as `0x`, `0X`, and `#`; it also interprets numbers with a leading zero under octal rules. **Do not swap `decode` and `parseInt` in a data protocol** without defining the input specification, because the same `"010"` can mean different things depending on the API.

Radices outside 2..36 and invalid digits are both cases to test. With `Integer.parseInt`, overly long/out-of-range inputs or strings containing spaces are not accepted as if `trim()` were called automatically.

## 4. Large Integers with `BigInteger`

`BigInteger` is not constrained by the signed `int`/`long` range. When data can exceed `Long.MAX_VALUE`, use:

```java
BigInteger original = new BigInteger("123456789012345678901234567890");
String base36 = original.toString(36);
BigInteger parsed = new BigInteger(base36, 36);
boolean same = original.equals(parsed); // true
```

Digit characters in base 36 range from `0` to `9` and `a` to `z`. Test positive numbers, negative numbers, 0, and values exceeding 64-bit range. When parsing, ensure the radix argument matches the format and handle `NumberFormatException` for invalid inputs.

**Scope note:** `BigInteger.toString(radix)` and the `new BigInteger(text, radix)` constructor are designed for **integral values**. Do not infer from them that `BigDecimal` can directly parse fractional parts in arbitrary bases. For base-2/16 fractions or other real-number notations, a dedicated format or algorithm must be defined; do not arbitrarily pass non-decimal syntax to `BigDecimal(String)`.

## 5. `BigDecimal`: Preserving Value Differs from Preserving Scale

### 5.1. `toString` Restores the `BigDecimal` Representation

`BigDecimal.toString()` produces a canonical string representation, using scientific notation when needed. When reconstructed with `new BigDecimal(text)`, it preserves **both numerical value and scale**:

```java
BigDecimal x = new BigDecimal("123.4500");
String encoded = x.toString();        // "123.4500"
BigDecimal back = new BigDecimal(encoded);

System.out.println(x.equals(back));   // true
System.out.println(back.scale());     // 4
```

This criterion is stricter than `compareTo() == 0`. `BigDecimal.equals()` distinguishes `1.0` and `1.00`, whereas `compareTo()` considers them numerically equal.

Also test:
- 0 with different scales (`"0"`, `"0.000"`);
- negative numbers and very large/small numbers;
- `"1E+3"` with **negative scale**;
- trailing zeros (`"123.4500"`);
- exact values with more than 15–17 digits, to confirm data did not accidentally pass through `double`.

### 5.2. `toPlainString` Prioritizes Readability and May Not Preserve Negative Scale

`BigDecimal.toPlainString()` omits exponential notation, suitable when plain notation is needed. However, for numbers with a negative scale, a round-trip through `toPlainString()` and `new BigDecimal(...)` can change the scale:

```java
BigDecimal original = new BigDecimal("1E+3"); // scale -3
String plain = original.toPlainString();       // "1000"
BigDecimal reparsed = new BigDecimal(plain);  // scale 0

boolean equalValue = original.compareTo(reparsed) == 0; // true
boolean equalRepresentation = original.equals(reparsed); // false
```

If strict scale recovery is required, prefer `toString()` (or store `unscaledValue` and `scale` separately under an explicit schema). If only numerical value matters, `toPlainString()` may be appropriate.

### 5.3. `setScale`, `stripTrailingZeros`, and Rounding Formats

`setScale` can round according to `RoundingMode`; `stripTrailingZeros()` preserves numerical value yet can change scale. Therefore tests must clarify:
- is changing the value acceptable?
- is changing the scale acceptable?
- are decimal places determined by **source data** or **display rules**?

For instance, formatting `12.3456` as `"12.35"` discards information. Parsing back into `BigDecimal` yields 12.35, and cannot recover 12.3456.

Do not use `new BigDecimal(doubleValue)` as a way to reconstruct a decimal string without understanding `double`'s binary representation error. For decimal data already in string form, construct directly with `new BigDecimal(text)`.

## 6. `double` and `float` Round-Trips

### 6.1. `Double.toString` / `Double.parseDouble`

For finite `double` values, `Double.toString(value)` produces a decimal string with enough information for `Double.parseDouble(text)` to restore the **exact same `double` value** (including the bit pattern of `-0.0`). Example:

```java
double value = Math.PI;
String text = Double.toString(value);
double back = Double.parseDouble(text);

boolean identicalBits =
        Double.doubleToRawLongBits(value)
        == Double.doubleToRawLongBits(back); // true
```

Boundary points to test include `0.0`, `-0.0`, very small (*subnormal*) numbers, `Double.MIN_VALUE`, `Double.MAX_VALUE`, and values near representation boundaries. For `float`, `Float.toString()` and `Float.parseFloat()` follow the same idea.

**Do not use `a == b` as the bit round-trip check in all cases:**
- `0.0 == -0.0` is `true`, even though the sign bits differ.
- `Double.NaN == Double.NaN` is `false` even though both are NaN.
- `Double.doubleToLongBits` normalizes NaN bits to canonical form; `Double.doubleToRawLongBits` preserves the raw payload bits of the value being inspected.

`Double.toString(Double.NaN)` produces `"NaN"` and `Double.parseDouble("NaN")` restores the NaN state; **it does not guarantee preserving every payload bit** of every representable NaN. If exact round-tripping of **every bit pattern**, including NaN payloads, is mandatory, serialize the output of `Double.doubleToRawLongBits(x)` using a fixed bit protocol and restore via `Double.longBitsToDouble(bits)`.

Similarly, `Infinity` and `-Infinity` are understood by `Double.toString`/`parseDouble`, yet not every data interchange format (such as strict standard JSON) permits these two non-finite values. Distinguish the **Java parser's contract** from the **storage format's contract**.

### 6.2. Formatting with Few Digits Can Break Round-Trips

`String.format(Locale.US, "%.2f", Math.PI)` returns `"3.14"`. When passed to `Double.parseDouble`, the parsed value is the `double` near 3.14, differing bitwise from `Math.PI`.

```java
String shown = String.format(Locale.US, "%.2f", Math.PI);
// shown = "3.14"; this is a rounded display format
double reconstructed = Double.parseDouble(shown);
// reconstructed does not have the same bits as Math.PI
```

Therefore:
- use `Double.toString()` for text round-trips that must preserve the exact `double` value;
- use `String.format`/`DecimalFormat` with fixed precision for **display**, understanding that information is usually lost;
- do not assume 2 decimal places suffice for any arbitrary `double`.

Cases like `0.1 + 0.2` are also subject to `double`'s binary nature. A round-trip test can pass 100%, yet that **does not prove the input calculation was exact in decimal**.

## 7. Locale, Separators, and `DecimalFormat`

The same number 12345.67 can be displayed as:

| Context | Sample text | Meaning |
| --- | --- | --- |
| Machine-readable, locale-independent | `12345.67` | Period is the decimal separator |
| German, thousands grouping and decimal | `12.345,67` | Period for grouping, comma for decimal |
| Rounded display to two digits | `12,35` from 12.3456 (per pattern and rounding mode) | Exact information has been discarded |

To parse strings under regional conventions, you need the **matching Locale, format pattern, and rounding rules**. Example with `DecimalFormat`:

```java
DecimalFormat german = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
german.setParseBigDecimal(true);

BigDecimal source = new BigDecimal("12345.67");
String text = german.format(source);   // "12.345,67"

ParsePosition position = new ParsePosition(0);
Number parsed = german.parse(text, position);
// parsed instanceof BigDecimal == true
// position.getIndex() == text.length()
```

This is an **illustrative snippet**: it requires importing `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, `java.text.ParsePosition`, `java.math.BigDecimal`, and `java.util.Locale`, placed inside a method/class.

Notes:
1. `DecimalFormat` formats and parses according to a pattern. If the pattern **rounds or truncates information**, re-parsing cannot recover the original value.
2. `setParseBigDecimal(true)` parses into `BigDecimal` instead of returning `Long` or `Double` automatically; this matters when decimal exactness is required.
3. `NumberFormat.parse`/`DecimalFormat.parse` can parse a **prefix** of the string and stop before an invalid character. Therefore checking for a non-null return is not enough: verify that the **entire string was consumed**, e.g., `ParsePosition.getIndex() == text.length()`, and check parse errors if any.
4. Do not assume these locale-formatted strings are understood by `Double.parseDouble` or `new BigDecimal(text)`; those standard numeric parsers use their own syntax, not a universal locale parser.
5. When testing formats with grouping separators, currency symbols, non-Latin digits, or special negative signs, define the input schema and full acceptance criteria. A parser supporting grouping characters does not necessarily enforce **all strict grouping rules**; separate pattern validation may be needed.

**Note for monetary amounts:** Some display strings have a fixed number of decimal places, such as `"12.30"`, while the source `BigDecimal("12.3")` has scale 1. A **numerical value** round-trip may succeed while `equals()` fails because the formatter intentionally appended trailing zeros. Decide whether you are testing value or scale.

## 8. Standalone Java 17 Program: Testing Multiple Round-Trip Kinds

Create file **`NumberRoundTripDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberRoundTripDemo {
    static void require(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        int[] sample = {Integer.MIN_VALUE, -255, -1, 0, 1, 255, Integer.MAX_VALUE};
        int[] bases = {2, 8, 10, 16, 36};
        int checked = 0;
        for (int base : bases) {
            for (int number : sample) {
                String text = Integer.toString(number, base);
                require(Integer.parseInt(text, base) == number, "int base=" + base);
                checked++;
            }
        }
        System.out.println("integerCases=" + checked);
        System.out.println("minus255Hex=" + Integer.toString(-255, 16));

        String unsigned = Integer.toUnsignedString(-1);
        int u = Integer.parseUnsignedInt(unsigned);
        require(u == -1, "unsigned bits");
        System.out.println("unsignedText=" + unsigned + ",signedBits=" + u);

        BigInteger big = new BigInteger("123456789012345678901234567890");
        String base36 = big.toString(36);
        require(new BigInteger(base36, 36).equals(big), "BigInteger");
        System.out.println("bigBase36=" + base36);

        BigDecimal amount = new BigDecimal("123.4500");
        BigDecimal restored = new BigDecimal(amount.toString());
        System.out.println("decimalEquals=" + amount.equals(restored)
                + ",scale=" + restored.scale());

        BigDecimal exponential = new BigDecimal("1E+3");
        BigDecimal plainBack = new BigDecimal(exponential.toPlainString());
        System.out.println("plainValueEqual=" + (exponential.compareTo(plainBack) == 0)
                + ",plainEquals=" + exponential.equals(plainBack)
                + ",scales=" + exponential.scale() + "," + plainBack.scale());

        double[] values = {0.0, -0.0, 0.1, Math.PI,
                Double.MIN_VALUE, Double.MAX_VALUE,
                Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY};
        int doubleCount = 0;
        for (double original : values) {
            double back = Double.parseDouble(Double.toString(original));
            require(Double.doubleToRawLongBits(original)
                    == Double.doubleToRawLongBits(back), "double bits");
            doubleCount++;
        }
        System.out.println("doubleBitCases=" + doubleCount);
        String roundedPi = String.format(Locale.US, "%.2f", Math.PI);
        System.out.println("piText=" + roundedPi
                + ",bitwiseEqual=" + (Double.doubleToRawLongBits(Math.PI)
                    == Double.doubleToRawLongBits(Double.parseDouble(roundedPi))));

        DecimalFormat german = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.GERMANY));
        german.setParseBigDecimal(true);
        BigDecimal localizedValue = new BigDecimal("12345.67");
        String localized = german.format(localizedValue);
        ParsePosition position = new ParsePosition(0);
        Number parsed = german.parse(localized, position);
        require(parsed instanceof BigDecimal, "localized parse type");
        require(position.getIndex() == localized.length(), "complete locale parse");
        require(((BigDecimal) parsed).compareTo(localizedValue) == 0,
                "localized number value");
        System.out.println("germanText=" + localized
                + ",parsed=" + parsed + ",fullyConsumed=true");

        ParsePosition trailing = new ParsePosition(0);
        german.parse(localized + "X", trailing);
        System.out.println("trailingJunkDetected="
                + (trailing.getIndex() != (localized + "X").length()));

        try {
            Integer.parseInt("0xff", 16);
            throw new AssertionError("expected parse failure");
        } catch (NumberFormatException expected) {
            System.out.println("prefixedHexRejected=true");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac NumberRoundTripDemo.java
java NumberRoundTripDemo
```

Actual output, compiled with `javac --release 17` and executed:

```text
integerCases=35
minus255Hex=-ff
unsignedText=4294967295,signedBits=-1
bigBase36=byw97um9s91dlz68tsi
decimalEquals=true,scale=4
plainValueEqual=true,plainEquals=false,scales=-3,0
doubleBitCases=8
piText=3.14,bitwiseEqual=false
germanText=12.345,67,parsed=12345.67,fullyConsumed=true
trailingJunkDetected=true
prefixedHexRejected=true
```

Explanation of the evidence:
- **35 integer cases** = 7 boundary/typical values × 5 radices. Every case parses back to the original `int`.
- **Unsigned**: string `4294967295` preserves the 32-bit pattern of `-1`, rather than returning `long`.
- **BigInteger**: a number far exceeding `long` was converted via base 36 and restored intact.
- **BigDecimal**: `toString()` preserves scale 4, whereas `toPlainString()` on a negative scale loses the scale attribute.
- **double**: eight cases including `-0.0`, tiny/huge numbers, and both infinities all preserve raw bits via `toString/parseDouble`. NaN payload values are not in this set of eight.
- **Two-digit formatting**: `Math.PI` becomes `"3.14"`, so parsing does not preserve the original bits.
- **German locale**: separators are produced per Locale and the parser consumes the entire valid string; trailing `X` is caught by checking the parse position.
- **Hex prefix**: `parseInt("0xff", 16)` is rejected as required by the contract.

## 9. Designing Thorough Parse/Format Tests

### 9.1. Valid Case Combinations

For integers:
- 0, 1, -1;
- type min/max (`Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, `Long.MAX_VALUE`);
- ordinary values, negative numbers, powers of the radix, values just before/after thresholds (e.g., 15, 16, 17 in radix 16);
- bases 2, 8, 10, 16, 36, and optionally all bases from 2 to 36;
- uppercase/lowercase letter formatting, `+`/`-` signs, and leading zeros if allowed by the parser contract.

For `BigDecimal`:
- 0 with multiple scales;
- trailing zeros;
- very large and very small numbers;
- negative scales and exponential notation;
- formatting operations that preserve value while changing scale;
- post-rounding numbers that may differ from original values.

For `double` and `float`:
- +0 and -0;
- extrema and subnormals;
- normal numbers and values near rounding points;
- NaN and infinities per the schema's **specific rules**;
- randomly generated bit patterns to explore broad cases, separating NaN payloads.

### 9.2. Invalid Input Cases

Tests checking only the “happy path” easily miss parsing bugs. Add:
- empty strings, whitespace-only strings, duplicate `+`/`-` signs;
- digits invalid for the radix (e.g., `"2"` in radix 2, `"g"` in radix 16);
- radix less than 2 or greater than 36;
- large numbers exceeding `int` or `long` range;
- `0x` prefix mistakenly passed to `parseInt`;
- grouping separators with a mismatched Locale;
- valid string with trailing garbage;
- negative-signed string when the unsigned parser contract forbids it.

For strict string parsers like `Integer.parseInt`, verify `NumberFormatException`. For `DecimalFormat.parse`/`NumberFormat.parse`, simultaneously check **returned numeric type**, **parse errors**, **consumed index**, and **rounding rules**, since there are situations where the parser stops after a valid prefix without signaling an error in the way the program expects.

### 9.3. Properties to Test

Several useful *properties*:

```text
Signed radix:
parseInt(toString(n, r), r) == n, for all n and 2 <= r <= 36.

BigInteger:
new BigInteger(n.toString(r), r).equals(n).

BigDecimal representation:
new BigDecimal(x.toString()).equals(x).

BigDecimal numeric value, when using an intentional format:
parsed.compareTo(x) == 0 (if the format does not round).

Double finite:
rawBits(parseDouble(Double.toString(x))) == rawBits(x).

Localized format:
a parser with the right Locale must consume the entire string;
if formatting is lossless, compare results per objective.
```

These are **reference properties**, not standalone Java code snippets. With random data generators, log the *seed* to reproduce failing cases, enforce timeouts, and capture the input value, intermediate string, and radix/Locale on assertion failures.

## 10. Radix Testing and Cross-System Consistency

**Radix is part of the format.** The string `"10"` represents 2 in radix 2, 8 in radix 8, 10 in radix 10, and 16 in radix 16. If sender and receiver do not agree on the radix, a round-trip can parse **syntactically successfully yet produce the wrong value**.

For storage protocols, clearly specify:
1. value type and range (signed/unsigned, integer/floating-point);
2. radix, sign notation, and whether prefixes are permitted;
3. digit alphabet/casing for radices above 10;
4. whether leading zeros, whitespace, or separators are allowed;
5. Locale, grouping separator, and decimal separator when formatting for display;
6. round-trip definition: exact number, exact scale, exact raw bits, or exact string;
7. error policy: reject invalid input, never silently switch radix or truncate data.

For example, sending `"ff"` without specifying the radix when the receiver calls `Integer.parseInt(text)` (which defaults to base 10) will fail; yet sending `"10"` without specifying the radix is more dangerous because the parser can return a **different value without throwing an error**.

## 11. Common Bugs and How to Prevent Them

1. **Testing `Integer.toString(n)` and parsing in radix 16.** Formatting and parsing use mismatched radices. Always pass a consistent radix on both sides.
2. **Confusing `toHexString(-1)` with `Integer.toString(-1,16)`.** One represents unsigned bits `ffffffff`, the other represents the signed number `-1`.
3. **Assuming `Integer.parseInt("0xff",16)` understands prefixes.** It does not: handle prefixes per protocol or use an appropriate decode API.
4. **Using only `BigDecimal.compareTo()` when scale must be preserved.** Numerically equal values can have different scales; use `equals()` if full representation matters.
5. **Using `toPlainString()` to serialize `BigDecimal` while expecting negative scale to survive.** It can turn `1E+3` into `1000` and lose scale -3. Use `toString()` or store scale separately.
6. **Using `%.2f` or `DecimalFormat` as a lossless storage scheme.** Display formats can round or alter scale; store original data in a format matching the preservation level needed.
7. **Checking `double` with `==` and overlooking `-0.0`/`NaN`.** Compare bits as needed; handle NaN payloads separately if raw bits must be preserved.
8. **Assuming German or Vietnamese locales always use a period decimal point.** Decimal/grouping separators depend on Locale and format. Explicitly set the Locale on both encode and decode.
9. **Parsing only a leading prefix and treating it as success.** With `DecimalFormat`, verify `ParsePosition.getIndex() == input.length()`.
10. **Skipping overflow and invalid input tests.** Round-tripping small numbers does not prove the parser handles type boundaries or invalid radices.
11. **Confusing `double` precision with round-trip capability.** You can accurately serialize/parse an *already approximate `double` value*, yet it still differs from the ideal decimal number.
12. **Comparing normalized text against the original input string.** Representations like `"0007"` and `"7"` have the same value. If preserving the original text is required, store the original text.

## 12. Self-Check Exercises

**Exercise 1.** What does `Integer.toString(31,16)` return, and how is it parsed back?  
**Answer:** string `"1f"`; `Integer.parseInt("1f",16)` returns 31.

**Exercise 2.** Why does `Integer.parseInt(Integer.toHexString(-1),16)` fail?  
**Answer:** `toHexString(-1)` returns `"ffffffff"` representing unsigned bits, whose value exceeds signed `int` range. Use `Integer.parseUnsignedInt("ffffffff",16)` to recover the same bit pattern.

**Exercise 3.** Does `new BigDecimal("5.00").toString()` parse back with the same scale?  
**Answer:** yes. Reconstructing with `new BigDecimal("5.00")` preserves scale 2, so `equals()` returns true.

**Exercise 4.** If `BigDecimal("1E+3")` is formatted with `toPlainString()` and parsed back, what does `equals()` return?  
**Answer:** false because scale changes from -3 to 0; `compareTo() == 0` remains true.

**Exercise 5.** Does `String.format(Locale.US, "%.2f", Math.PI)` produce a string that can restore every bit of π as a `double`?  
**Answer:** no. The string `"3.14"` is rounded and lacks information.

**Exercise 6.** A Locale parser returned a number when given `"12.345,67X"`. Should this be considered a success?  
**Answer:** no, if the schema requires the entire input to be valid. Use `ParsePosition` to check that the parser consumed the entire text.

**Exercise 7.** Why can `"10"` be more dangerous than `"ff"` when sender and receiver do not agree on the radix?  
**Answer:** `"10"` is syntactically valid in many radices yet has different values, failing silently; `"ff"` is rejected by a decimal parser.

## 13. Conclusion

- **Round-trips must clearly define their target:** preserving numerical value, representation attributes like scale, floating-point bits, or verbatim text.
- For integers, use `toString(value, radix)` and `parseInt(text, radix)`/`parseLong(text, radix)` within 2..36; distinguish signed from unsigned and two's-complement notation.
- For large integers, use `BigInteger`; for `BigDecimal` where scale must be preserved, use `toString()` and `new BigDecimal(text)` to round-trip under `equals()`.
- For `double`/`float`, use `toString/parseDouble` or `toString/parseFloat` to preserve the floating-point value. If *raw NaN payloads* must be preserved, use a dedicated bit format.
- For Locale/display formats, check rounding, parsed type, separators, and full input consumption.
- A reliable test suite must cover boundary cases, radices, invalid strings, overflow, and comparisons aligned with the data contract.

Official reference documentation (Java SE 17):
- [`Integer` — toString, parseInt, unsigned](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html)
- [`Long`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html)
- [`BigInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [`Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html)
- [`DecimalFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [`ParsePosition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)
