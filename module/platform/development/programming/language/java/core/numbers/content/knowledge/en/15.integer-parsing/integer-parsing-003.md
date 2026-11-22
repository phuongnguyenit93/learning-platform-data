# Radix, Plus or Minus Sign, and Valid Range When Parsing Integers in Java

When receiving an integer as a `String`, Java must answer three independent questions: **which number base (radix) does the string use?**, **where is the sign placed and is it valid?**, **does the mathematical value fall within the target type's range?** Reading the characters accurately is not enough: a string containing only valid digits can still be rejected due to range overflow. This lesson focuses on `Integer.parseInt`, `Long.parseLong`, and appropriate options when the data is no longer a standard signed integer.

## 1. What is a radix?

The radix (base) determines the allowed set of digits and the positional value of each place. For a string of digits \(d_k\dots d_1d_0\) in base \(r\), the absolute value is:

\[
|n|=\sum_{i=0}^{k} d_i r^i,\qquad 0\le d_i<r.
\]

For example, `"1A"` in base 16 has value \(1\times16+10=26\); `"101101"` in base 2 has value \(32+8+4+1=45\). The same string `"10"` has value 2 in base 2, 10 in base 10, and 16 in base 16.

In parsing methods with a `radix` parameter, Java supports bases **from 2 to 36**, corresponding to `Character.MIN_RADIX` and `Character.MAX_RADIX`. Digits `0`–`9` carry values 0–9; letters `a`–`z` or `A`–`Z` carry values 10–35 when the base is large enough. Therefore `F` is valid in base 16, whereas `G` is invalid in base 16 (but valid in base 17 and above).

| Radix | Typical characters | Example and decimal value |
| --- | --- | --- |
| 2 (binary) | `0`, `1` | `101101` → 45 |
| 8 (octal) | `0`–`7` | `17` → 15 |
| 10 (decimal) | `0`–`9` | `17` → 17 |
| 16 (hexadecimal) | `0`–`9`, `A`–`F` | `7F` → 127 |
| 36 | `0`–`9`, `A`–`Z` | `Z` → 35 |

Basic APIs:

```java
int decimal = Integer.parseInt("255");       // defaults to radix 10
int binary  = Integer.parseInt("11111111", 2); // 255
int hex     = Integer.parseInt("ff", 16);      // 255
long big    = Long.parseLong("7fffffffffffffff", 16); // Long.MAX_VALUE
```

`Integer.parseInt(String)` **always uses base 10**. `Integer.parseInt(String, int)` uses the exact base passed in; Java does not infer the radix from a prefix or from a leading zero.

## 2. Plus sign, minus sign, and string syntax

In standard ASCII notation, the valid form for `parseInt`/`parseLong` is:

```text
[+|-]? <at least one valid digit in the radix>
```

- A `+` or `-` sign is **optional** and may only appear as the first character. `"+7F"` (radix 16) gives 127; `"-7F"` gives -127; standalone `"-"` and `"+"` are invalid.
- The sign applies only to the value of the entire digit sequence. `"-101"` (radix 2) is **-5**, not a two's complement bit pattern automatically interpreted as a negative number.
- `"0"`, `"+0"`, and `"-0"` all parse to the numeric value 0. Leading zeros are accepted, yet **do not turn the string into base 8**: `Integer.parseInt("010")` gives 10.
- Whitespace, commas, periods, underscores, and extra characters are not automatically skipped: `" 42"`, `"42 "`, `"1_000"`, `"1,000"`, and `"42L"` are all invalid for `parseInt`.
- `Integer.parseInt("0xFF", 16)` and `Integer.parseInt("0b1010", 2)` both fail because `x`/`b` in these strings are not valid digits at their respective positions. When specifying a radix manually, pass only the digit portion such as `"FF"` and `"1010"`.
- Lowercase/uppercase letters are equivalent in radices that include letters: `"aF"` and `"Af"` in base 16 are both 175.
- A radix outside 2–36, a digit whose value is greater than or equal to the radix, an empty string, and `null` all lead to `NumberFormatException` in `Integer.parseInt(String, int)`.

**Unicode detail:** `parseInt` uses digit logic based on `Character.digit(char, radix)`, so certain non-ASCII Unicode digit characters may also be accepted. If a data protocol allows only `[0-9A-Za-z]` or ASCII digits only, you must **validate the format separately before parsing**. Do not assume `parseInt` is synonymous with a strict ASCII validator.

### Table of commonly confused scenarios

| Call | Result | Explanation |
| --- | --- | --- |
| `Integer.parseInt("+101", 2)` | `5` | Valid leading plus sign |
| `Integer.parseInt("-101", 2)` | `-5` | Minus sign applied to the magnitude |
| `Integer.parseInt("077")` | `77` | Still defaults to base 10 |
| `Integer.parseInt("077", 8)` | `63` | Base 8 was requested |
| `Integer.parseInt("7f", 16)` | `127` | `f` = 15 |
| `Integer.parseInt("2", 2)` | Error | `2` is not a base-2 digit |
| `Integer.parseInt("0xFF", 16)` | Error | Does not recognize `0x` prefix |
| `Integer.parseInt("--5")` | Error | Only one leading sign is allowed |
| `Integer.parseInt("1_000")` | Error | Underscore `_` is not parsed from strings |
| `Integer.parseInt(" 5 ")` | Error | Does not automatically `trim()` |

You should not unconditionally call `trim()`/`strip()` just to "make parsing succeed." Clearly define the input contract: for user input you may allow leading/trailing whitespace; for identifiers or machine data you should preserve the strict original format.

## 3. Value range: valid digits can still be rejected

Java's `int` and `long` are **signed** integers. The radix only changes the representation, **not the storable range**.

| Type | Width | Minimum value | Maximum value |
| --- | --- | --- | --- |
| `byte` | 8 bits | -128 | 127 |
| `short` | 16 bits | -32 768 | 32 767 |
| `int` | 32 bits | -2 147 483 648 | 2 147 483 647 |
| `long` | 64 bits | -9 223 372 036 854 775 808 | 9 223 372 036 854 775 807 |

Mathematically, a \(w\)-bit signed integer type has the range \([-2^{w-1},\,2^{w-1}-1]\). Therefore **the negative bound has an absolute value 1 greater than the positive bound**.

Key examples for `Integer.parseInt`:

```java
Integer.parseInt("2147483647");       // valid: Integer.MAX_VALUE
Integer.parseInt("-2147483648");      // valid: Integer.MIN_VALUE

Integer.parseInt("2147483648");       // NumberFormatException
Integer.parseInt("-2147483649");      // NumberFormatException

Integer.parseInt("7fffffff", 16);     //  2147483647, valid
Integer.parseInt("-80000000", 16);    // -2147483648, valid
Integer.parseInt("80000000", 16);     // NumberFormatException
Integer.parseInt("-80000001", 16);    // NumberFormatException
```

`"80000000"` in base 16 has the **positive** value 2 147 483 648, which exceeds signed `int`. Java does not automatically wrap around to -2 147 483 648 when calling `parseInt`; this is a range error. Similarly, a 64-bit string larger than `Long.MAX_VALUE` cannot be parsed with standard `Long.parseLong` even when the digits are completely valid.

Under the hood, the parser must check for overflow while multiplying the accumulated value by the radix and adding the next digit. The JDK can accumulate in the negative domain to handle `Integer.MIN_VALUE` safely as well, since the value `2147483648` cannot be represented as a positive `int`. This is why you should not hand-roll a parser with `int result = result * radix + digit` and only check the range at the end: the arithmetic can already overflow before the check.

For `byte` and `short`, use `Byte.parseByte`/`Short.parseShort`; they enforce their respective ranges. Parsing into `int` and casting `(byte)` or `(short)` can silently lose data:

```java
Byte.parseByte("128");  // NumberFormatException: exceeds 127
byte lost = (byte) Integer.parseInt("128"); // -128 due to narrowing conversion
```

When out-of-range data must be rejected, use the parser for the exact type or check bounds before converting types.

## 4. Distinguishing runtime strings, Java literals, and automatic prefix detection

Three mechanisms are frequently confused:

1. **Source-code literals** read by the Java compiler: `10` (decimal), `010` (octal), `0x10` (hexadecimal), `0b10` (binary). Since Java 7, literals can also contain `_` in valid positions, such as `1_000`.
2. **`Integer.parseInt(text, radix)`** reads a runtime string with a specified radix. It does not apply literal syntax: `"010"` with radix 10 is 10 and `"1_000"` is invalid.
3. **`Integer.decode(text)`** recognizes certain prefixes by its own rules: `0x`/`0X` or `#` for base 16, a leading `0` (with more than one digit) for base 8, and base 10 otherwise. A `+`/`-` sign may appear **before the prefix**, e.g. `"-0x2A"` → -42; placing the sign after the prefix like `"0x-2A"` is invalid.

Examples:

```java
Integer.parseInt("010");     // 10
Integer.parseInt("010", 8);  // 8
Integer.decode("010");       // 8
Integer.decode("0x10");      // 16
Integer.decode("#10");       // 16
Integer.decode("-0x2A");     // -42
Integer.decode("08");        // NumberFormatException: 8 is not in base 8
```

Choose `decode` when **the input specification genuinely allows** these prefix forms. For data requiring consistent base 10, use `parseInt(text, 10)` to avoid `"010"` unexpectedly being treated as base 8. `decode` is also subject to signed `int` limits; it does not solve overflow errors.

A subtle distinction: `0xFFFFFFFF` written directly as an `int` literal can represent the bit pattern -1 according to Java's literal rules, yet `Integer.parseInt("FFFFFFFF", 16)` still rejects it because it is a string representing the **positive value** 4 294 967 295, which exceeds `Integer.MAX_VALUE`.

## 5. When a string represents an unsigned value or a large number

In Java, the primitive types `int` and `long` are still stored in signed form. If the data specification is an **unsigned** integer, use the corresponding unsigned parse API, then interpret the result properly:

```java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
// bits == -1 if viewed as a signed int, but the bit pattern is 0xFFFFFFFF

long unsignedValue = Integer.toUnsignedLong(bits); // 4294967295
String decimal = Integer.toUnsignedString(bits);   // "4294967295"
String hex = Integer.toUnsignedString(bits, 16);    // "ffffffff"
```

`Integer.parseUnsignedInt` covers the arithmetic range 0 to \(2^{32}-1\), while `Long.parseUnsignedLong` covers 0 to \(2^{64}-1\). The return value is still a primitive `int`/`long`, so values with the sign bit set will display as negative numbers if passed to `System.out.println(bits)` or ordinary signed operations.

`Integer.parseUnsignedInt("-1", 10)` is invalid: a minus sign does not fit the unsigned range. After parsing, use the APIs containing `Unsigned` when comparing, dividing, or formatting with unsigned semantics (`Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.toUnsignedString`, etc.). For unsigned `long` values exceeding `Long.MAX_VALUE`, if you want to process them as large positive numbers in arithmetic, typically use `BigInteger`, for example:

```java
BigInteger maxUnsignedLong =
        new BigInteger("FFFFFFFFFFFFFFFF", 16); // 18446744073709551615
```

When a number can exceed the `int`, `long`, or `unsigned long` range, use `java.math.BigInteger(String value, int radix)`. `BigInteger` still requires a valid digit string for the radix and an optional leading sign; it does not automatically accept `"0x"` when radix 16 is passed. There is no fixed 32/64-bit limit as with primitive types, though you must still watch memory/resource limits for overly long inputs.

### Choosing the API by input contract

| Input to read | Recommended API | Key point to remember |
| --- | --- | --- |
| Signed base-10 number in 32-bit range | `Integer.parseInt(text)` | Does not accept prefixes or separators |
| Signed base 2–36 number in 32-bit range | `Integer.parseInt(text, radix)` | Leading sign, validates radix and overflow |
| Signed number in 64-bit range | `Long.parseLong(text, radix)` | Bounds of `long` |
| Text allowing `0x`, `#`, leading zeros | `Integer.decode(text)` | `010` becomes base 8 |
| 32-bit unsigned number | `Integer.parseUnsignedInt(text, radix)` | Result is an `int` holding the bit pattern |
| 64-bit unsigned number | `Long.parseUnsignedLong(text, radix)` | Result is a `long` holding the bit pattern |
| Arbitrary-size integer | `new BigInteger(text, radix)` | No fixed 32/64-bit limit |

## 6. Complete runnable Java 17+ program

Save as **`RadixParsingDemo.java`**:

```java
import java.math.BigInteger;

public class RadixParsingDemo {
    public static void main(String[] args) {
        show("101101", 2);
        show("+7f", 16);
        show("-80000000", 16);
        show("80000000", 16);
        show("2", 2);

        System.out.println("decode -0x2A = " + Integer.decode("-0x2A"));
        System.out.println("parseInt 010 = " + Integer.parseInt("010"));
        System.out.println("decode 010 = " + Integer.decode("010"));

        int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("uint bits = " + bits);
        System.out.println("uint value = " + Integer.toUnsignedLong(bits));

        BigInteger beyondInt = new BigInteger("100000000", 16);
        System.out.println("big = " + beyondInt);
        System.out.println("format = " + Integer.toString(255, 16));
    }

    private static void show(String input, int radix) {
        try {
            int value = Integer.parseInt(input, radix);
            System.out.println("\"" + input + "\" base " + radix + " -> " + value);
        } catch (NumberFormatException ex) {
            // Custom message so the example does not depend on how the JDK phrases errors.
            System.out.println("\"" + input + "\" base " + radix + " -> INVALID");
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 RadixParsingDemo.java
java RadixParsingDemo
```

Expected stdout:

```text
"101101" base 2 -> 45
"+7f" base 16 -> 127
"-80000000" base 16 -> -2147483648
"80000000" base 16 -> INVALID
"2" base 2 -> INVALID
decode -0x2A = -42
parseInt 010 = 10
decode 010 = 8
uint bits = -1
uint value = 4294967295
big = 4294967296
format = ff
```

In the example, `show()` distinguishes valid data from invalid digits or out-of-range data by catching `NumberFormatException`. Both `"80000000"` (signed int range error) and `"2"` in base 2 (invalid digit) are rejected; if an application needs to report the exact cause, it must additionally check the format, radix, and range according to business rules. Do not rely on the verbatim JDK error message to classify failures because messages may vary across versions.

## 7. Designing a reliable input layer

To handle input from forms, CSVs, network protocols, or configuration files:

1. **Define the contract first:** fixed radix or prefixed? Is the `+` sign allowed? Are negatives accepted? Are leading zeros, whitespace, Unicode digits, or thousands separators accepted? Is there a length limit?
2. **Normalize deliberately:** only `strip()` whitespace when the contract allows it. If notation like `0x` must be accepted, detect it, strip the prefix, and choose the radix per the protocol rules; or use `decode` if its rules match exactly.
3. **Validate radix and syntax:** radix in 2–36. If only signed ASCII hex is accepted, for example you can validate the string with `[+-]?[0-9A-Fa-f]+`; for other radices you need to validate each digit's value accordingly (or let the parser validate it).
4. **Use a parser matching the numeric range:** parse into `int`/`long` when the application domain fits; use unsigned APIs for unsigned quantities; use `BigInteger` when values must exceed 64 bits.
5. **Handle errors explicitly:** catch `NumberFormatException` at the input boundary, report the invalid value to the user or return a structured error. Do not silently convert errors to `0` because that mixes them up with real `"0"` data.
6. **Bound resources:** for untrusted input, limit the length before parsing, especially before constructing a `BigInteger`; avoid allocating or scanning huge blocks of data unnecessarily.

A helper enforcing the policy "optional-sign ASCII hex without prefix", then delegating range checking to `parseInt`:

```java
static int parseAsciiHexSignedInt(String text) {
    if (text == null || !text.matches("[+-]?[0-9A-Fa-f]+")) {
        throw new IllegalArgumentException("Requires an optionally signed ASCII hex string");
    }
    return Integer.parseInt(text, 16);
}
```

This helper snippet **is not a standalone runnable program**: place it inside an appropriate class. The regex checks **ASCII syntax**, while `Integer.parseInt` checks whether **the value fits in a signed `int`**. `IllegalArgumentException` thrown by the helper is for syntax; the parser's `NumberFormatException` is still used for range overflow. Because `String.matches` compiles the regex on every call, for frequently executed paths you can predeclare a `Pattern` and use `matcher(text).matches()`.

If the input contract allows Unicode digits as in Java, do not use an ASCII regex like the above. If the contract mandates radix 10 and a 0–100 bound, check the business range after parsing (`0 <= value && value <= 100`) in addition to the technical range of `int`.

## 8. Common mistakes and self-check

- **Confusing radix with range:** switching from radix 10 to 16 does not let `int` store larger numbers; it only changes how they are written.
- **Confusing negative signs with the sign bit:** `"-FF"` is -255, whereas `"FFFFFFFF"` is textually the positive number 4 294 967 295; to read an unsigned bit pattern, use `parseUnsignedInt`.
- **Assuming prefixes are always understood:** `parseInt("0xFF", 16)` is invalid, whereas `decode("0xFF")` is valid.
- **Applying literal rules to Strings:** `1_000` is valid in Java code, whereas `"1_000"` cannot be parsed directly.
- **Treating every leading-zero number as octal:** only interpretations such as `decode` (and certain literals) have that rule; `parseInt("010")` is still 10.
- **Truncating data via casting:** `(byte) 128` becomes -128; this is not range validation.
- **Believing valid digits always parse:** `"2147483648"` contains only valid base-10 characters yet still exceeds `int`.
- **Catching overly broad `Exception` or defaulting to 0:** loses the root cause and corrupts data semantics.

Quick self-check before calling a parser: **radix ∈ [2,36] → sign (if any) only at the front → at least one digit remaining → every digit belongs to the radix → value lies within the target type's range**. Only then decide whether the integer is signed, unsigned, or requires `BigInteger`. Input strings, bit representation, and value range are three separate concerns; keeping them separate prevents most integer parsing bugs in Java.