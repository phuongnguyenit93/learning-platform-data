# `decode` and Radix Prefixes in Java

## 1. When a numeric string has a prefix, which radix does Java use?

Java lets you write integers in decimal, binary, octal, and hexadecimal. However, there is an important difference between **literals written in Java code** and **character strings parsed at runtime**.

For example, in source code:

```java
int decimal = 42;
int binary = 0b101010;
int octal = 052;
int hex = 0x2A;
// All four variables have the int value 42.
```

To read a string like `"0x2A"` or `"052"` at runtime, Java provides `Integer.decode(String)`. It recognizes **certain radix prefixes** and converts them into a signed integer.

```java
int a = Integer.decode("42");   // 42, decimal
int b = Integer.decode("052");  // 42, octal: 5*8+2
int c = Integer.decode("0x2A"); // 42, hexadecimal
int d = Integer.decode("#2A");  // 42, alternative hex syntax
```

**First warning:** `Integer.decode("010")` yields **8**, not 10, because a string starting with `0` is interpreted as octal. Meanwhile, `Integer.parseInt("010")` yields **10** because `parseInt(String)` defaults to decimal.

**Second warning:** even though the literal `0b101010` is valid in Java code, `Integer.decode("0b101010")` **does not support** the binary prefix `0b`. To read a binary string, you must use `Integer.parseInt("101010", 2)` or a custom function that handles the prefix.

This lesson focuses on the **mechanics of `decode`, valid prefixes, differences from `parseInt`, numeric type bounds, and safe input handling**.

## 2. Available `decode` methods

The integer wrapper classes provide a static `decode(String)` method:

| Method | Returns | Signed value range |
|---|---|---|
| `Byte.decode(text)` | `Byte` | -128 to 127 |
| `Short.decode(text)` | `Short` | -32_768 to 32_767 |
| `Integer.decode(text)` | `Integer` | -2_147_483_648 to 2_147_483_647 |
| `Long.decode(text)` | `Long` | -9_223_372_036_854_775_808 to 9_223_372_036_854_775_807 |

These are **`static` methods**: call them via the class name such as `Integer.decode("0xFF")`, without needing to instantiate an `Integer` object first.

The return value is a **wrapper**, not a primitive; however, Java can automatically **unbox** it when you assign the result to a primitive variable:

```java
Integer wrapper = Integer.decode("0x2A"); // Integer, value 42
int primitive = Integer.decode("0x2A");   // unboxing -> int 42
long large = Long.decode("0x100000000"); // 4294967296L
```

`decode` **does not support `Float` or `Double`** in the same sense of parsing integer strings with radix prefixes. If you need to read floating-point numbers, use the appropriate floating-point API such as `Double.parseDouble`; if you need to parse an integer string with a prefix and then convert it to `double`, those two steps have different semantics and must be decided explicitly.

## 3. Table of prefixes supported by `decode`

`Integer.decode` and `Long.decode` follow these standard forms:

| String form | Radix | Example | Decimal result |
|---|---:|---|---:|
| No prefix (and does not start with 0 under octal rules) | 10 | `"42"` | 42 |
| `0x` | 16 | `"0x2A"` | 42 |
| `0X` | 16 | `"0X2a"` | 42 |
| `#` | 16 | `"#2A"` | 42 |
| Starts with `0`, followed by digits | 8 | `"052"` | 42 |
| Binary prefix `0b`, `0B` | Not supported | `"0b101010"` | `NumberFormatException` |

Why is `"052"` equal to 42?

\[
5\times 8^1 + 2\times 8^0 = 40+2=42
\]

Why is `"0x2A"` equal to 42?

\[
2\times 16^1 + 10\times 16^0 = 32+10=42
\]

Letters `A` through `F` (or lowercase `a` through `f`) represent hex digits 10 through 15. The `#` character in `"#2A"` is also a **hex prefix**, not a new arithmetic operator.

**A leading `0` carries syntactic meaning.** For example:

- `Integer.decode("0")` → 0.
- `Integer.decode("00")` → 0.
- `Integer.decode("010")` → 8.
- `Integer.decode("077")` → 63.
- `Integer.decode("08")` → error, because digit 8 is invalid in octal.
- `Integer.decode("09")` → similar error.

Therefore, if an input is genuinely a **decimal number** and may have leading zeros (such as `"008"`), do not use `decode` by default.

## 4. Plus sign, minus sign, and their valid placement

`decode` supports a **`+` or `-` sign placed before the prefix**, if present:

```java
int a = Integer.decode("-42");      // -42
int b = Integer.decode("+42");      // 42
int c = Integer.decode("-052");     // -42 (octal)
int d = Integer.decode("-0x2A");    // -42
int e = Integer.decode("+#2A");     // 42
int f = Integer.decode("-0X2a");    // -42
```

Core rule: **the sign leads the entire string**, followed by `0x`, `0X`, `#`, or `0`.

The following strings are invalid:

```java
// Integer.decode("0x-2A"); // invalid: sign is after prefix
// Integer.decode("#-2A");  // invalid
// Integer.decode("--42");  // invalid
// Integer.decode("++42");  // invalid
```

The sign may appear only once and must be at the very beginning. Separating sign and prefix in the proper order keeps negative hex/octal strings consistent in meaning with negative decimal values.

### The lowest negative value of `int` can still be read

`Integer.MIN_VALUE` equals -2_147_483_648. In hex, the corresponding magnitude is `0x80000000`. The negatively signed string:

```java
int min = Integer.decode("-0x80000000");
// -2147483648
```

is valid. However:

```java
// Integer.decode("0x80000000"); // NumberFormatException
```

is invalid because it represents the **positive value** 2_147_483_648, exceeding `Integer.MAX_VALUE`. `decode` reads **signed integers**, and does not automatically treat every 32-bit pattern as an unsigned value.

## 5. Comparing `decode`, `parseInt`, and `parseUnsignedInt`

This is the most important part when choosing an API.

| Purpose | Suitable API | How input is interpreted |
|---|---|---|
| Read strings with `0x`, `0X`, `#`, or octal `0` prefix | `Integer.decode(text)` | Automatically picks 10/8/16 from prefix |
| Read decimal numbers, including leading zeros | `Integer.parseInt(text)` | Fixed base 10 |
| Read a digit string in a specified radix | `Integer.parseInt(digits, radix)` | Radix determined by the `radix` parameter |
| Read an `int` bit pattern as an unsigned number | `Integer.parseUnsignedInt(digits, radix)` | Specified radix and range 0..2³²−1 |
| Read a 64-bit signed integer with prefixes | `Long.decode(text)` | Signed 10/8/16 |
| Read a 64-bit unsigned integer | `Long.parseUnsignedLong(digits, radix)` | Range 0..2⁶⁴−1, stored in `long` bit pattern |

Examples with the same string:

```java
int a = Integer.decode("010"); // 8, octal
int b = Integer.parseInt("010"); // 10, decimal
int c = Integer.parseInt("010", 8); // 8, specified radix
int d = Integer.parseInt("1010", 2); // 10, binary
```

Hex string examples:

```java
int a = Integer.decode("0xFF"); // 255
int b = Integer.parseInt("FF", 16); // 255
// Integer.parseInt("0xFF", 16); // error: parseInt does not automatically strip "0x"
```

**API selection rule:** If the protocol specifies that input is **decimal**, use `parseInt` or `parseLong`. If the protocol specifies that input **has multi-radix prefixes following `decode` rules**, use `decode`. If the base is specified externally, use the `parseInt(text, radix)` overload instead of inferring from leading zeros.

## 6. First Java 17+ example: decoding all radix forms

Create file `DecodePrefixesDemo.java`:

```java
public class DecodePrefixesDemo {
    public static void main(String[] args) {
        System.out.println("42 -> " + Integer.decode("42"));
        System.out.println("052 -> " + Integer.decode("052"));
        System.out.println("0x2A -> " + Integer.decode("0x2A"));
        System.out.println("0X2a -> " + Integer.decode("0X2a"));
        System.out.println("#2A -> " + Integer.decode("#2A"));
        System.out.println("-052 -> " + Integer.decode("-052"));
        System.out.println("-0x2A -> " + Integer.decode("-0x2A"));
        System.out.println("+0X2a -> " + Integer.decode("+0X2a"));
        System.out.println("010 via decode -> "
                + Integer.decode("010"));
        System.out.println("010 via parseInt -> "
                + Integer.parseInt("010"));
        System.out.println("binary via radix -> "
                + Integer.parseInt("101010", 2));
        System.out.println("long hex -> "
                + Long.decode("0x100000000"));
        System.out.println("short hex -> "
                + Short.decode("0x7FFF"));
        System.out.println("byte octal -> "
                + Byte.decode("0177"));
    }
}
```

Compile and run with Java 17+:

```bash
javac DecodePrefixesDemo.java
java DecodePrefixesDemo
```

Exact output:

```text
42 -> 42
052 -> 42
0x2A -> 42
0X2a -> 42
#2A -> 42
-052 -> -42
-0x2A -> -42
+0X2a -> 42
010 via decode -> 8
010 via parseInt -> 10
binary via radix -> 42
long hex -> 4294967296
short hex -> 32767
byte octal -> 127
```

In the last three lines, the result still has to fit within the return type's range. For example, `Byte.decode("0177")` reads octal 177 and gets 127 within the signed `byte` range; `Byte.decode("0200")` does not wrap around to -128, but instead throws an error because the positive value 128 is **outside the `byte` range**.

## 7. `decode` does not understand every Java literal syntax

Literals in **Java source code** are processed by the compiler. Data strings passed to `decode` are checked by the method's own grammar; it is not a miniature Java compiler.

Comparison table:

| In Java source code | Valid? | Corresponding string passed to `Integer.decode` |
|---|---|---|
| `0b1010` | Yes: binary | `"0b1010"` → error |
| `0xFF` | Yes: hex | `"0xFF"` → 255 |
| `077` | Yes: octal | `"077"` → 63 |
| `1_000` | Yes: underscore digit grouping | `"1_000"` → error |
| `123L` | Yes: `long` literal | `"123L"` → error |
| `0xFFL` | Yes: hex `long` literal | `"0xFFL"` → error |
| `10` | Yes: decimal | `"10"` → 10 |

The underscore `_` **is allowed by the compiler in literals under specific rules**, yet is not accepted in strings parsed by `Integer.decode`, `Integer.parseInt`, or `Long.parseLong`.

Similarly, the `L`/`l` suffix is Java literal syntax, **not a valid digit** in a string for `Long.decode`. Write `Long.decode("123")` instead of `Long.decode("123L")`.

### Binary syntax must be handled separately

If the input is specified as a sequence of binary digits:

```java
int value = Integer.parseInt("101010", 2); // 42
```

If the input is specified as `"0b101010"`, you need to check and strip the prefix before parsing:

```java
String text = "0b101010";
if (text.startsWith("0b") || text.startsWith("0B")) {
    int value = Integer.parseInt(text.substring(2), 2); // 42
}
```

This is an **illustrative code snippet**, not a complete program. It only accepts a binary prefix at the start of a positive string; for signed data like `"-0b1010"`, you must define the sign convention and design the corresponding parser.

Do not assume `decode` automatically supports binary just because Java literals have `0b`.

## 8. Range limits: `decode` checks signed numbers, without wraparound

`Byte.decode`, `Short.decode`, `Integer.decode`, and `Long.decode` return **signed** integer wrappers. Out-of-range values cause `NumberFormatException`.

```java
int max = Integer.decode("2147483647");
int min = Integer.decode("-2147483648");

// Integer.decode("2147483648");  // too large
// Integer.decode("-2147483649"); // too small
// Integer.decode("0xFFFFFFFF"); // positive 4294967295, outside int range
```

For `Long`:

```java
long max = Long.decode("9223372036854775807");
long min = Long.decode("-9223372036854775808");

// Long.decode("9223372036854775808");  // outside long range
```

For `Byte` and `Short`:

```java
byte maxByte = Byte.decode("127");
byte minByte = Byte.decode("-0x80");
short maxShort = Short.decode("0x7FFF");

// Byte.decode("128");       // outside byte range
// Short.decode("0x8000");   // positive 32768, outside short range
```

If the goal is to convert a 32-bit **bit pattern** into a potentially negative `int`, do not use `Integer.decode("0xFFFFFFFF")`. It does not accept 4_294_967_295 as a valid signed number. Instead, use unsigned parsing with the appropriate radix (and strip the `0x` prefix before parsing), then work with the bits of the result.

## 9. Reading unsigned integers and preserving bit patterns

Java's `int` and `long` are signed primitive types, yet the standard library provides APIs to **read and display unsigned values** using the exact 32/64-bit patterns:

```java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
System.out.println(bits); // -1 when printed as signed int
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
```

The bit pattern `0xFFFFFFFF` can be represented by `int` -1, yet when interpreted as an unsigned number, it equals 4_294_967_295. **The return value still has type `int`**; no `unsigned int` type is created.

Similarly:

```java
long bits = Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16);
System.out.println(bits); // -1 when printed as signed long
System.out.println(Long.toUnsignedString(bits)); // 18446744073709551615
```

### Complete program: reading unsigned hex patterns

Create file `UnsignedDecodeDemo.java`:

```java
public class UnsignedDecodeDemo {
    public static void main(String[] args) {
        int signedMin = Integer.decode("-0x80000000");
        System.out.println("signed min: " + signedMin);

        int unsignedBits =
                Integer.parseUnsignedInt("80000000", 16);
        System.out.println("signed view: " + unsignedBits);
        System.out.println("unsigned view: "
                + Integer.toUnsignedString(unsignedBits));
        System.out.println("as unsigned long: "
                + Integer.toUnsignedLong(unsignedBits));

        int allOnes =
                Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("all bits signed: " + allOnes);
        System.out.println("all bits unsigned: "
                + Integer.toUnsignedString(allOnes));

        long longBits =
                Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16);
        System.out.println("long signed: " + longBits);
        System.out.println("long unsigned: "
                + Long.toUnsignedString(longBits));
    }
}
```

Run:

```bash
javac UnsignedDecodeDemo.java
java UnsignedDecodeDemo
```

Output:

```text
signed min: -2147483648
signed view: -2147483648
unsigned view: 2147483648
as unsigned long: 2147483648
all bits signed: -1
all bits unsigned: 4294967295
long signed: -1
long unsigned: 18446744073709551615
```

**Important trap:** `Integer.parseUnsignedInt("0xFFFFFFFF", 16)` is still invalid, because `parseUnsignedInt` accepts **digits in the specified radix** rather than stripping prefixes automatically. Verify the input format, remove `0x` when needed, and then parse.

## 10. `NumberFormatException` and invalid data

`decode` can throw `NumberFormatException` when encountering malformed syntax or out-of-range input. The examples below are invalid for `Integer.decode`:

| String | Reason |
|---|---|
| `"08"` | Starts with 0 so read as octal; digit 8 is invalid |
| `"09"` | Similar octal error |
| `"0b1010"` | `0b` prefix is not supported |
| `"0x"` | Missing hex digits |
| `"#"` | Missing hex digits |
| `"0x-10"` | Minus sign in wrong position |
| `"1_000"` | `_` is invalid in parsed strings |
| `"42L"` | Literal suffix `L` is not supported |
| `" 42"` | Leading space; `decode` does not automatically trim |
| `"42 "` | Trailing space |
| `""` | No digits |
| `"2147483648"` | Outside signed `int` range |

When accepting untrusted input, **catch the exception at the input boundary**, rather than letting errors propagate unchecked or forcing an arbitrary fallback value.

### Java 17+ example: classifying valid and invalid strings

Create file `DecodeValidationDemo.java`:

```java
public class DecodeValidationDemo {
    private static void check(String text) {
        try {
            int value = Integer.decode(text);
            System.out.println(text + " -> " + value);
        } catch (NumberFormatException e) {
            System.out.println(text + " -> invalid");
        }
    }

    public static void main(String[] args) {
        check("0x10");
        check("010");
        check("08");
        check("0b1010");
        check("0x");
        check("42L");
        check("1_000");
        check(" 42");
        check("-0x80000000");
        check("0x80000000");
    }
}
```

Compile and run:

```bash
javac DecodeValidationDemo.java
java DecodeValidationDemo
```

Output:

```text
0x10 -> 16
010 -> 8
08 -> invalid
0b1010 -> invalid
0x -> invalid
42L -> invalid
1_000 -> invalid
 42 -> invalid
-0x80000000 -> -2147483648
0x80000000 -> invalid
```

Note that the line `" 42"` contains a **space right at the start of the string**. Because `check` prints that string verbatim before `->`, the output has **a leading space on that line**. This is actual string printing behavior; it is not stripped when verifying output.

## 11. Using `decode` safely according to the input contract

To avoid confusion and unpredictable behavior, before choosing `decode`, determine:

1. **Are radix prefixes permitted?** If so, which prefixes are valid?
2. **Is a leading zero an identifier or a numeric value?** For instance, `"008"` may be a code with textual significance; parsing it as a number loses the leading zeros.
3. **Is the value signed or unsigned?** `decode` is only for signed integer types; if reading raw bit patterns intact, an appropriate unsigned API is required.
4. **Does the target type have enough range?** `Byte/Short/Integer/Long.decode` enforce different bounds.
5. **Do you need to accept whitespace or user-entered formats?** `decode` does not automatically trim; if policy permits, normalize in a controlled way beforehand.
6. **Are binary prefixes permitted?** `decode` does not accept `0b`; if needed, write a dedicated parser.
7. **How should errors be reported?** Catch `NumberFormatException` at the input layer and return a clear message, without treating invalid data as 0 by default.

Example for input **intentionally allowing leading/trailing whitespace**:

```java
static int decodeTrimmed(String input) {
    if (input == null) {
        throw new IllegalArgumentException("value is required");
    }
    String text = input.trim();
    if (text.isEmpty()) {
        throw new IllegalArgumentException("value is empty");
    }
    return Integer.decode(text);
}
```

This is **an illustrative method**, which must be placed inside a Java class. Using `trim()` is an **input policy decision**, not built-in behavior of `decode`. For machine protocols reading strictly formatted strings, you may want to reject whitespace instead of fixing it automatically.

If the data is a decimal number entered by a user, a more specific API could be:

```java
static int parseDecimal(String input) {
    if (input == null) {
        throw new IllegalArgumentException("value is required");
    }
    return Integer.parseInt(input.trim());
}
```

`parseInt` is used here because the input **is defined as decimal**, not an arbitrary prefixed string.

## 12. Distinguishing numeric values from identifiers

Not every all-digit string should be parsed into a number. The following codes may **need to be kept as `String`**:

- Customer ID: `"000123"`.
- Product code: `"008"`.
- Postal codes or area codes depending on country: may start with 0.
- Fixed-length configuration codes, e.g., `"0016"`.
- A binary string required to be 16 bits wide with leading zeros.

If you call `Integer.decode("000123")`, Java **interprets the string as an octal number**, completely losing the original code. `"008"` even causes an error. If a data field is an identifier, **keep it as `String`** and validate length/allowed characters instead of using `decode`.

This is a data modeling principle: **data that looks like a number does not necessarily have arithmetic semantics**.

## 13. `Integer.getInteger` differs from `Integer.decode`

A similarly named API pair that easily causes confusion:

- `Integer.decode("0x10")`: **parses the passed string itself**, yielding 16.
- `Integer.getInteger("name")`: reads the **Java system property** named `name`, then parses that property's value using the appropriate radix rules. It does **not** mean reading an integer string directly.

Illustrative example:

```java
System.setProperty("app.port", "0x1F90");
Integer port = Integer.getInteger("app.port"); // 8080
Integer fromText = Integer.decode("0x1F90");   // 8080
```

This code snippet belongs inside a method. `Integer.getInteger` can return `null` when the property does not exist or cannot be parsed validly; `decode` is not a call that reads a system property.

Similarly, `Long.getLong` is for system properties, not an alternative variant of `Long.decode` for parsing arbitrary numeric strings.

**Safety when using properties:** system properties can be configured by the execution environment; always define a default value and error-handling policy. Do not confuse a **property name** with a **numeric string** when calling the API.

## 14. `BigInteger` and data exceeding `long` limits

If a value can truly exceed the `long` range, `Long.decode` is unsuitable. Java provides `java.math.BigInteger` to handle integers of arbitrary magnitude.

```java
import java.math.BigInteger;

BigInteger decimal = new BigInteger("18446744073709551615");
BigInteger hex = new BigInteger("FFFFFFFFFFFFFFFF", 16);
```

This is an **illustrative code snippet**, which must be placed in a class/method with the proper import. Both objects have the same mathematical value of 18_446_744_073_709_551_615.

Unlike `decode`, the `BigInteger(String, radix)` constructor takes a **sequence of digits for the given radix** rather than automatically accepting `0x`:

```java
BigInteger value = new BigInteger("FF", 16); // 255
// new BigInteger("0xFF", 16); // NumberFormatException
```

If a protocol specifies strings with `0x` or `0b` and unbounded digit counts, you can build a parser that **accepts strictly the listed prefixes** and then invokes the constructor with the appropriate `radix`. You should not arbitrarily accept every Java-literal-like symbol because it increases validation complexity.

Note: `BigInteger` does not support the `+` operator between two objects; use `add`, `subtract`, and `multiply`.

## 15. Building a custom parser when `0b` is also required

Suppose the data requirements are:

- Unprefixed decimal strings.
- Hex with `0x` or `0X`.
- Binary with `0b` or `0B`.
- No support for octal via leading 0.
- Allow a leading `+` or `-` sign.
- Numbers outside the `int` range are errors.

This is **a different contract from `Integer.decode`**, so build a custom parser.

Create file `ExplicitRadixParserDemo.java`:

```java
public class ExplicitRadixParserDemo {
    static int parseFlexibleInt(String input) {
        if (input == null || input.isEmpty()) {
            throw new NumberFormatException("empty input");
        }

        int position = 0;
        boolean negative = false;

        char first = input.charAt(0);
        if (first == '-' || first == '+') {
            negative = first == '-';
            position = 1;
        }
        if (position == input.length()) {
            throw new NumberFormatException("missing digits");
        }

        int radix = 10;
        if (input.startsWith("0b", position)
                || input.startsWith("0B", position)) {
            radix = 2;
            position += 2;
        } else if (input.startsWith("0x", position)
                || input.startsWith("0X", position)) {
            radix = 16;
            position += 2;
        }
        if (position == input.length()) {
            throw new NumberFormatException("missing digits");
        }

        // Let parseInt validate digits and signed int bounds.
        String digits = input.substring(position);
        return Integer.parseInt((negative ? "-" : "") + digits, radix);
    }

    public static void main(String[] args) {
        System.out.println(parseFlexibleInt("42"));
        System.out.println(parseFlexibleInt("010"));
        System.out.println(parseFlexibleInt("0b101010"));
        System.out.println(parseFlexibleInt("-0B101010"));
        System.out.println(parseFlexibleInt("+0x2A"));
        System.out.println(parseFlexibleInt("-0x80000000"));
    }
}
```

Run:

```bash
javac ExplicitRadixParserDemo.java
java ExplicitRadixParserDemo
```

Output:

```text
42
10
42
-42
42
-2147483648
```

The parser above **intentionally differs from `decode`**: `"010"` is read in decimal as 10, rather than in octal as 8. It does not auto-trim, does not accept underscores or `L` suffixes, and always enforces `int` bounds via `Integer.parseInt`.

### Points to extend if used in production

- Limit input length to avoid excessive resource consumption.
- Constrain prefix types to match the protocol; if `#` is needed, add an explicit branch.
- Specify whether leading `+` signs or leading `0`s are allowed.
- Choose `long`/`BigInteger` if a larger range is needed.
- Report errors distinguishing "invalid character", "missing digits", and "out of range" when required by the API.
- Test empty strings, `null`, prefixes without digits, MIN/MAX values, and long inputs.

There is no need to write a custom parser if built-in `parseInt` or `decode` already **matches the input contract exactly**.

## 16. Common mistakes and how to fix them

| Error or misconception | Cause | Fix |
|---|---|---|
| `decode("010")` gives 8 instead of 10 | Leading zero triggers octal | Use `parseInt("010")` when input is decimal |
| `decode("08")` throws an error | 8 is invalid in octal | Use `parseInt("08")` if decimal is desired |
| `decode("0b1010")` fails | `decode` does not support binary prefix | `parseInt("1010", 2)` or a custom parser |
| `parseInt("0xFF",16)` fails | `parseInt` takes digits, does not strip prefixes | Use `parseInt("FF",16)` or `decode("0xFF")` |
| `decode("1_000")` fails | `_` is literal syntax, not parsed string syntax | Use a valid digit string |
| `decode("42L")` fails | `L` suffix is only for Java literals | `Long.decode("42")` |
| `decode(" 42")` fails | Does not automatically strip whitespace | Trim after checking policy |
| `decode("0x-1")` fails | Sign must precede the prefix | Write `"-0x1"` |
| `decode("0xFFFFFFFF")` fails | Exceeds signed `int` range | Use an unsigned parser after stripping `0x` |
| `Byte.decode("0200")` fails | Octal 200 equals 128, outside `byte` range | Choose a wider type or clarify signed/unsigned |
| `getInteger("123")` does not return 123 as expected | Looks up system property named `123` | Use `parseInt`/`decode` |
| Parsing code `"000123"` loses leading zeros | Treating an identifier as arithmetic | Keep as `String` |
| Accepting every prefix form by guesswork | Protocol has not defined the radix | Design a clear parser contract |

## 17. Self-check exercises

**Q1.** What are `Integer.decode("010")` and `Integer.parseInt("010")` respectively?  
**Answer:** 8 and 10; `decode` sees octal while `parseInt(String)` uses decimal.

**Q2.** Are `Integer.decode("0x2A")` and `Integer.decode("#2A")` the same?  
**Answer:** Yes, both equal 42 because both use base 16.

**Q3.** Does `Integer.decode("0b101010")` yield 42?  
**Answer:** No, it throws `NumberFormatException`. Use `Integer.parseInt("101010", 2)`.

**Q4.** Why does `Integer.decode("08")` fail while `Integer.parseInt("08")` returns 8?  
**Answer:** The leading 0 causes `decode` to treat it as octal, where digit 8 is invalid; `parseInt` defaults to decimal.

**Q5.** Where should the minus sign be placed in a hex string?  
**Answer:** Before the prefix: `"-0x2A"`, not `"0x-2A"`.

**Q6.** Can `Integer.MIN_VALUE` be read in hex form?  
**Answer:** Yes: `Integer.decode("-0x80000000")` returns -2_147_483_648.

**Q7.** Does `Integer.decode("0xFFFFFFFF")` return -1?  
**Answer:** No, the string represents a positive hex number outside the signed `int` range. Use `Integer.parseUnsignedInt("FFFFFFFF",16)` to get the bit pattern, then read it unsigned via `toUnsignedString`.

**Q8.** Why does `Integer.parseInt("FF",16)` work while `Integer.parseInt("0xFF",16)` does not?  
**Answer:** The `parseInt(text, radix)` overload accepts **digits** in the base, and does not automatically handle prefixes.

**Q9.** If a data column contains the code `"008"`, should `decode` be used to store it in the system?  
**Answer:** Usually no. This may be an identifier that needs to preserve leading zeros; use `String`.

**Q10.** What does `Long.decode("0x100000000")` equal?  
**Answer:** 4_294_967_296, within the signed `long` range.

**Q11.** To read an integer too large for `long` from the hex string `"FFFFFFFFFFFFFFFF"` as a **positive mathematical value**, what should you use?  
**Answer:** `new BigInteger("FFFFFFFFFFFFFFFF", 16)`. If you only need the 64-bit unsigned bit pattern, use `Long.parseUnsignedLong("FFFFFFFFFFFFFFFF",16)` along with appropriate unsigned display/comparison APIs.

**Q12.** How does `Integer.getInteger("app.port")` differ from `Integer.decode("0x1F90")`?  
**Answer:** The first reads the **value of the system property** named `app.port` and parses it; the second parses the **argument string** directly.

## 18. API selection checklist and references

Before implementing a parser for integer strings:

1. Determine whether the data field is a **number** or an **identifier**.
2. Define valid **radices** and prefixes in the API/protocol.
3. Decide how to handle **signs**, leading zeros, and whitespace.
4. Choose the target type `byte`, `short`, `int`, `long`, `BigInteger` and range limits.
5. Decide whether the input is a **signed value** or an **unsigned bit pattern**.
6. Use `decode` only when the `0x`/`0X`/`#`/octal-`0` rules are genuinely desired.
7. Use `parseInt(text)` or `parseLong(text)` for decimal; use `parseInt(text, radix)` when the base is specified.
8. Catch `NumberFormatException` and translate it into an appropriate error at the data boundary.
9. Test MIN/MAX numbers, valid/invalid prefixes, long inputs, misplaced signs, and whitespace.
10. Do not infer from the ability to parse a string that the data satisfies business rules if other constraints remain.

**Key takeaway:** `Integer.decode` and `Long.decode` support **decimal**, **octal when the string starts with 0**, and **hex with `0x`, `0X`, `#`**; a `+/-` sign precedes **the prefix**. They **do not** understand `0b` prefixes, `_` underscores, or `L` suffixes in runtime strings. If the requirement is decimal, prefer `parseInt`; if it is an unsigned bit pattern or a very large numeric range, use a more appropriate API.

Standard documentation:
- [Java SE 17 — Integer.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#decode(java.lang.String))
- [Java SE 17 — Long.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html#decode(java.lang.String))
- [Java SE 17 — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String,int))
- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)