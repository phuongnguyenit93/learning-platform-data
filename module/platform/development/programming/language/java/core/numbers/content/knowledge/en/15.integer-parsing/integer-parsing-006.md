# Why Doesn't `Integer.parseInt` Handle `0x` Prefixes or Underscores Like the Java Compiler?

Notations such as `0x`, `0b`, `_` between digits, or the `L` suffix are part of **numeric literal syntax in Java source code**. They are processed by the compiler when reading the program. By contrast, `Integer.parseInt(String)` is an API running **at runtime**, taking a string and converting it to an `int` value according to **its own syntax rules**. This method **is not a miniature Java compiler**.

```java
int sourceLiteral = 0x2A;                         // 42: Java compiler understands 0x.
int sourceUnderscore = 1_000;                     // 1000: Java compiler understands _.
int parsedHex = Integer.parseInt("2A", 16);       // 42: radix is passed separately.

// Integer.parseInt("0x2A", 16); // NumberFormatException.
// Integer.parseInt("1_000");    // NumberFormatException.
```

**Key takeaway:** Characters inside a `String` are **data**, not re-scanned by Java as language tokens. If an input looks like `"0x2A"`, you must choose an API that understands that prefix, such as `Integer.decode`, or validate and strip the prefix yourself before calling `parseInt`. If the input contains underscores, you must define **validity rules** and normalize; not every way of stripping underscores matches literal syntax.

## 1. Two completely different processing stages

### 1.1. Literals in source code: processed before the program runs

When the Java compiler reads code:

```java
int decimal = 42;
int hex = 0x2A;
int binary = 0b101010;
int octal = 052;
int separated = 1_000_000;
```

It parses **literal tokens** according to Java language syntax. Different notations can produce the same mathematical value, yet the compiler recognizes the structure: radix from prefix or leading digit, valid underscore placement, `L`/`l` suffix for type `long`, and value range. After compilation, the program works with **numeric values**, rather than preserving the textual `0x...` syntax inside an `int` variable.

For example, `0x2A` is a base-16 **integer literal**, `0b101010` is a base-2 literal, `052` is a base-8 literal because of the leading zero, and `42` is a decimal literal. `1_000_000` uses underscores so human readers can see digit groups, while the underscores carry no numeric value.

There is no such thing as an `int` variable remembering whether it was declared in decimal or hexadecimal. How a result is **displayed** is a separate decision, such as `Integer.toString(value)` or `Integer.toHexString(value)`.

### 1.2. `String` at runtime: processed by the parser according to the parser's contract

```java
String text = "0x2A";
String other = "1_000";

// Enclosed in quotation marks: this is String content, not an integer literal.
```

The compiler recognizes these only as **string literals**. It creates string values and **does not parse their contents into Java numeric tokens**. When `Integer.parseInt(text)` is called, the JVM is already at runtime; the method checks characters according to its own parser syntax.

This is the fundamental difference: the exact same visible sequence of characters can carry two meanings across the two contexts of **source-code token** and **string data**.

| Code line / input | Who processes it? | Result |
| --- | --- | --- |
| `int x = 0x2A;` | Java compiler | `x == 42` |
| `Integer.parseInt("2A", 16)` | `parseInt` at runtime | Returns `42` |
| `Integer.parseInt("0x2A", 16)` | `parseInt` at runtime | Throws `NumberFormatException` |
| `int x = 1_000;` | Java compiler | `x == 1000` |
| `Integer.parseInt("1_000")` | `parseInt` at runtime | Throws `NumberFormatException` |
| `int x = 010;` | Java compiler | `x == 8` because octal literal |
| `Integer.parseInt("010")` | `parseInt` at runtime | Returns `10` because default radix 10 |

Do not equate **syntax differences** with **value differences**. `0x2A` and `42` produce the same `int`; `parseInt` simply does not accept every literal notation as input.

## 2. The actual contract of `Integer.parseInt`

In Java SE 17, the core overloads include:

```java
int a = Integer.parseInt("42");      // Default radix = 10.
int b = Integer.parseInt("2A", 16);   // Hex digits, radix = 16.
int c = Integer.parseInt("101010", 2); // Binary digits, radix = 2.
int d = Integer.parseInt("-2A", 16);  // -42, minus sign allowed.
```

`Integer.parseInt(String s, int radix)` accepts:

1. An optional **leading** ASCII `+` or `-` sign.
2. Followed by at least one valid digit for `radix`.
3. No decorative characters such as `_`, `0x`, `0b`, `L` suffix, or unnormalized whitespace.
4. The numeric value after the sign must lie within the signed `int` range, from `Integer.MIN_VALUE` to `Integer.MAX_VALUE`.
5. `radix` between `Character.MIN_RADIX` (2) and `Character.MAX_RADIX` (36).

A digit character is determined via `Character.digit(character, radix)`; besides `0..9` and corresponding letters, Java can accept certain Unicode digit characters recognized by the `Character` API. If the application's input format **allows ASCII only**, you must enforce a separate constraint; do not treat the parser as an ASCII validator by default.

### The method does not guess the radix from the string

```java
System.out.println(Integer.parseInt("010"));     // 10.
System.out.println(Integer.parseInt("010", 10)); // 10.
System.out.println(Integer.parseInt("010", 8));  // 8.
```

The `radix` parameter handles the **base**, not **prefixes**. For example, radix 16 means the character `A` has value 10, not that the string is allowed to begin with `0x`.

```java
System.out.println(Integer.parseInt("FF", 16)); // 255.

// Integer.parseInt("0xFF", 16); // NumberFormatException because of letter 'x'.
// Integer.parseInt("0b101", 2); // NumberFormatException because of letter 'b'.
```

In `"0xFF"`, the character `0` can be a base-16 digit, but the character `x` is not a valid digit in radix 16. The parser has no rule to "treat the first two characters as a prefix and skip them."

### Minus and plus signs are exceptions recognized by the parser

```java
System.out.println(Integer.parseInt("-42"));     // -42.
System.out.println(Integer.parseInt("+42"));     // 42.
System.out.println(Integer.parseInt("-2A", 16)); // -42.
```

Accepting a leading sign **does not mean** the parser accepts full Java unary expression syntax. `Integer.parseInt("2+3")` does not evaluate expressions; `Integer.parseInt("--42")` is invalid; `Integer.parseInt("-0x2A",16)` is also invalid because the `0x` prefix remains.

### Errors are detected at runtime

Malformed syntax or out-of-range data causes `parseInt` to throw `NumberFormatException`, a subclass of `IllegalArgumentException`:

```java
// All of these fail:
Integer.parseInt("1_000");
Integer.parseInt("0x2A");
Integer.parseInt("3.14");
Integer.parseInt("42L");
Integer.parseInt("2147483648");
Integer.parseInt(" 42");
```

These are **standalone calls intentionally illustrating errors**, not a safe sequential program snippet. If you want the program to continue, catch the exception at the input boundary and report a contextual error.

## 3. Underscore syntax in compiler numeric literals

Since Java 7, one or more `_` characters are permitted **between digits** of a numeric literal subject to grammar restrictions. They make digit groups easier to read without changing the value.

```java
int million = 1_000_000;
int flags = 0b1010_0101;
int color = 0xCA_FE;
long big = 9_223_372_036_854_775_807L;
```

All of the above are **valid Java source code**. The compiler knows `_` is a grouping symbol and ignores it when determining the value.

However, a string with an underscore anywhere is not always a valid literal:

```java
// int a = _1000;  // Not a valid integer literal; may be parsed as an identifier.
// int b = 1000_;  // Invalid: trailing underscore after digits.
// int c = 0x_FF;  // Invalid: immediately after prefix, before first digit.
// int d = 0b_101; // Invalid: immediately after prefix.
// long e = 100_L; // Invalid: underscore immediately before L suffix.
```

Note that `100__0` **is a valid literal**: Java allows multiple consecutive underscores **between two digits**. Therefore, a validator allowing strictly **one** underscore between two digit groups is a **custom input format**, not identical to the full Java literal grammar.

`Integer.parseInt("1_000")` does not use literal grammar, so it throws `NumberFormatException` even though `int n = 1_000;` compiles successfully.

### Why shouldn't you blindly call `replace("_", "")`?

```java
String input = "1_000";
int n = Integer.parseInt(input.replace("_", "")); // 1000.
```

This snippet **can work if business rules dictate underscores may only appear between valid digits**. Yet a blind replacement also turns:

```text
_100 -> 100
100_ -> 100
1__0 -> 10
```

The first two examples **are not valid numeric literal notations**; the third can be valid in Java source yet may violate **stricter input policies** of the application. If you only use `replace`, all of them get accepted without distinguishing the original syntax.

**Rule:** before normalizing, **validate the entire string** against an explicit rule. Only then strip underscores and call `parseInt`. Do not use `replace` as a silent "auto-fix" step to accept unvalidated input.

## 4. Distinguishing `0x`, `0b`, and leading zeros

In Java source:

| Literal | Radix | Decimal value |
| --- | ---: | ---: |
| `42` | 10 | 42 |
| `0x2A` | 16 | 42 |
| `0X2a` | 16 | 42 |
| `0b101010` | 2 | 42 |
| `0B101010` | 2 | 42 |
| `052` | 8 | 42 |
| `010` | 8 | 8 |
| `000` | 8 | 0 |

The compiler determines the literal kind from **source token syntax**. `Integer.parseInt` takes the passed **`radix`** and corresponding digits, rather than inferring the base from source token rules.

```java
System.out.println(Integer.parseInt("052"));    // 52.
System.out.println(Integer.parseInt("052", 8)); // 42.
System.out.println(Integer.parseInt("0b101010", 2)); // Throws NumberFormatException.
```

The last line intentionally illustrates a case that throws an exception; when running a real program, do not call it directly if you expect subsequent lines to execute.

### The `010` and `09` trap

```java
int octalTen = 012;           // 10 decimal.
int octalEight = 010;         // 8 decimal.
int parsed = Integer.parseInt("010"); // 10 decimal.
```

In Java source, `09` is an **invalid literal**, because `9` is not an octal digit after a `0` prefix. Yet `Integer.parseInt("09")` returns **9** because the parser defaults to decimal.

This is why **you should not assume user-entered strings follow the same leading-zero rules as Java source code**. Many systems take postal codes, invoice numbers, version strings, or phone numbers; some data should not be parsed as numbers in the first place because leading zeros carry identifier meaning.

## 5. When should you use `Integer.decode`?

If an application's input **intentionally supports certain prefix forms**, the JDK provides `Integer.decode(String)`:

```java
System.out.println(Integer.decode("42"));    // 42.
System.out.println(Integer.decode("0x2A"));  // 42.
System.out.println(Integer.decode("0X2A"));  // 42.
System.out.println(Integer.decode("#2A"));   // 42.
System.out.println(Integer.decode("052"));   // 42.
System.out.println(Integer.decode("-0x2A")); // -42.
```

`decode` supports:
- No prefix: decimal.
- `0x` or `0X` or `#`: base 16.
- Leading `0` on a multi-digit string: base 8.
- Leading `+` or `-` sign, if present.

However, `Integer.decode` **is not a parser for all Java numeric literals**:

```java
// Integer.decode("0b101010"); // NumberFormatException.
// Integer.decode("1_000");    // NumberFormatException.
// Integer.decode("42L");      // NumberFormatException.
// Integer.decode("09");       // NumberFormatException (09 is treated as octal).
```

**Specifically:** `decode("09")` is treated as octal and fails, unlike `parseInt("09")` returning 9. If user input commonly starts with 0 yet must be interpreted in **base 10**, do not use `decode` as the default choice.

### `decode` and minus signs in base 16

```java
System.out.println(Integer.decode("-0x2A")); // -42.
```

`decode` understands a minus sign before the prefix. `parseInt("-2A",16)` also understands the minus sign but does **not** accept the `0x` prefix. If you normalize input by stripping prefixes, keep the sign in a valid position.

### APIs related to larger types

- `Long.parseLong(text, radix)` and `Long.decode(text)` are the counterparts for `long`.
- `Byte.decode(text)` and `Short.decode(text)` support similar prefix syntax, with narrower value ranges.
- `new BigInteger(text, radix)` allows integers with more digits than `long`, though radix input still requires handling prefixes according to the constructor's contract.
- `Integer.parseUnsignedInt(text, radix)` is for **32-bit unsigned** values using unsigned `int` interpretation, and does not automatically accept `0x` or `_`.

Choose the API based on **value range and input format**, not just the method name.

## 6. Advanced trap: hexadecimal literals and signed `int` limits

Another difference not solved merely by stripping `0x` and underscores: **rules for unsigned integers in base-16 literal syntax versus signed integer parsers**.

```java
int allBitsSet = 0xFFFF_FFFF; // Valid; int value is -1.
System.out.println(allBitsSet); // -1.
```

`0xFFFF_FFFF` written as a base-16 literal represents the 32-bit all-`1`s pattern. The corresponding signed `int` value is **−1**.

If you use the signed `int` parser:

```java
// Integer.parseInt("FFFFFFFF", 16); // NumberFormatException:
// 4294967295 > Integer.MAX_VALUE.
```

`Integer.parseInt` does not treat the string as a 32-bit unsigned bit pattern by default. If your data **defines hex as a 32-bit unsigned representation**, use:

```java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
System.out.println(bits);                          // -1 (viewed as signed int).
System.out.println(Integer.toUnsignedString(bits)); // 4294967295.
```

`parseUnsignedInt` returns `int` because Java has no `uint` primitive, yet the bits can be interpreted as unsigned using `Integer.toUnsignedString`, `Integer.compareUnsigned`, `Integer.divideUnsigned`, etc.

**Do not conflate three distinct meanings:**
1. A signed integer with value in `[-2^31, 2^31-1]`.
2. A 32-bit pattern, which can be printed in base 16.
3. A 32-bit unsigned value in `[0, 2^32-1]`.

`parseInt` handles case 1; `parseUnsignedInt` supports case 3 and returns the same bit pattern in `int`. The compiler handles numeric literals with its own rules for case 2. `Integer.decode("0xFFFFFFFF")` is also not a solution for 32-bit unsigned intent; it enforces signed bounds.

### Do not confuse a minus sign with a negative literal

In Java grammar, a `-` sign before a numeric literal is essentially the **unary minus operator**, except for special compiler rules regarding the minimum value of an integral type. `-0x2A` in source means negating the literal 42. `Integer.parseInt("-2A",16)` treats the minus sign as part of the input string syntax. The two paths can yield the same value yet do not use the same mechanism.

If you need to parse expressions such as `"-0x2A"`, `"1 + 2"`, `"(0b101) << 3"`, you are designing an **input language/expression parser** rather than merely parsing an integer. Never feed untrusted input into a Java code runner.

## 7. Checking input errors: syntax, radix, and overflow

`Integer.parseInt` typically throws `NumberFormatException` if:

- The string is empty, has no digits after a sign, or contains digits invalid for the radix.
- It encounters `0x`/`0b` prefixes or underscores unsupported by the `parseInt` contract.
- It encounters leading/trailing whitespace or extra characters not handled beforehand.
- The value lies outside the signed `int` range.
- The radix lies outside `2..36`.

```java
// The calls below intentionally illustrate errors:
Integer.parseInt("");
Integer.parseInt(" 42 ");
Integer.parseInt("12.0");
Integer.parseInt("42L");
Integer.parseInt("999999999999999");
Integer.parseInt("2", 2);
Integer.parseInt("10", 1);
```

The snippet above **is not a continuous runnable example** because the first statement already throws an exception. The complete example in section 11 shows a helper that converts failed outcomes into the text `INVALID` so the program runs to completion.

### Why doesn't `trim` solve every difference?

`Integer.parseInt(" 42 ")` fails, while `Integer.parseInt(" 42 ".trim())` returns 42. This is an **application-chosen whitespace normalization policy**. Yet `trim` does not turn `0x` into valid digits, does not remove underscores, and does not strip literal suffixes; it only handles a group of whitespace characters as defined by `String.trim`. `String.strip()` has Unicode whitespace behavior different from `trim()`.

If data must match an interchange standard exactly, you should not silently "auto-correct" invalid strings. Some protocols require rejecting whitespace to prevent inconsistent interpretation across systems.

### Leading zeros can carry data meaning, not numeric syntax

The string `"00042"` is sometimes an **identifier**. If parsed into `42`, you lose the three leading zeros. When storing codes of this kind, keep them as `String`, and validate length and character set per code rules instead of calling `parseInt`.

## 8. When an application wants hex input with underscores: validate then normalize

If the system contract defines **hex strings with a `0x` or `0X` prefix**, optionally with a sign and separating underscores **under a deliberate rule**, build a dedicated parser before calling `Integer.parseInt`.

The example below intentionally accepts only **one or more ASCII hex digits** with **at most one underscore between two digit groups**. This is a **stricter input policy** than Java grammar (Java allows multiple consecutive underscores between digits).

```java
static int parseHexInput(String input) {
    if (input == null ||
            !input.matches("[+-]?0[xX][0-9a-fA-F]+(?:_[0-9a-fA-F]+)*")) {
        throw new NumberFormatException("Invalid hex input");
    }
    boolean hasSign = input.startsWith("-") || input.startsWith("+");
    String sign = input.startsWith("-") ? "-" : "";
    String digits = input.substring(hasSign ? 3 : 2).replace("_", "");
    return Integer.parseInt(sign + digits, 16);
}
```

Examples:

```java
System.out.println(parseHexInput("0x2A"));  // 42.
System.out.println(parseHexInput("+0x2_A")); // 42.
System.out.println(parseHexInput("-0x2A")); // -42.
// parseHexInput("0x_2A");    // NumberFormatException.
// parseHexInput("0x2__A");   // NumberFormatException under this policy.
// parseHexInput("0xFFFFFFFF"); // NumberFormatException due to exceeding signed int range.
```

**Important:** the example method does not try to mimic the entire Java compiler. It expresses a **signed hex input format with restricted underscores and a signed int result**. If you need to support hex as a 32-bit unsigned bit pattern, you must use `parseUnsignedInt` and redesign the sign policy; you cannot just swap the method name.

If the application only needs simple hex without underscores, `Integer.decode` is convenient and more readable. If only hex digits **without a prefix** are needed, `Integer.parseInt(text,16)` directly is best.

### Which regex should be used?

A validator can accept:
- Digits by radix and ASCII/Unicode per contract.
- Presence or absence of prefix, sign, and underscores.
- Presence or absence of whitespace.
- Signed or unsigned numeric range.

**Do not try to write one giant regex covering all Java numeric literals** if the business domain only needs one specific input format. The more syntaxes you support, the greater the ambiguity (for example, should `010` be octal or decimal?).

## 9. Distinguishing compile-time errors from runtime exceptions

With Java source code:

```java
int valid = 0x2A;
int formatted = 1_000;

// int invalid = 0x_2A; // Invalid underscore placement: compile error.
// int invalidOctal = 09; // Invalid octal digit: compile error.
```

Literal syntax errors are caught at **compile time**. However, the expression:

```java
String incoming = "0x_2A";
int parsed = Integer.parseInt(incoming, 16);
```

still **compiles successfully**, because the compiler only checks that `incoming` is a `String` and a matching overload for `parseInt` exists. At runtime when reaching the call, the parser sees invalid input and throws `NumberFormatException`.

Even input in a **fixed** string literal such as `Integer.parseInt("0x2A",16)` is not flagged by the compiler for numeric syntax: it is a type-valid method call and will fail **at runtime**.

This matters when processing data from CSV/JSON files, environment variables, UIs, API requests, or command-line arguments. You must validate and manage runtime errors at the **trust boundary**, not rely on the fact that the code compiled.

## 10. Choosing an API by input requirement

| Input contract | Example | Appropriate API or strategy |
| --- | --- | --- |
| Simple signed decimal digits | `"123"`, `"-42"` | `Integer.parseInt(text)` |
| Digits of a fixed radix, **no prefix** | `"2A"` with radix 16 | `Integer.parseInt(text,16)` |
| Hex prefix, octal-style leading zero per decode rules | `"0x2A"`, `"052"` | `Integer.decode(text)` |
| Hex with prefix and underscores, signed int | `"0x2_A"` | Validator + strip formatting chars + `parseInt` |
| Binary with `0b` prefix | `"0b101010"` | Validated prefix detection/removal + `parseInt(digits,2)` |
| `long` integer with wider range | `"4294967296"` | `Long.parseLong` or `Long.decode` when format matches |
| Very large integer | `"1234567890123456789012345"` | `BigInteger` with explicit radix and normalization |
| Hex as 32-bit unsigned bit pattern | `"FFFFFFFF"` | `Integer.parseUnsignedInt(...,16)` |
| Codes keeping leading zeros, no arithmetic | `"00042"` | Keep `String`, validate schema |
| Full Java numeric expressions with operators | `"1 + 0x2A"` | Dedicated expression parser, do not use `parseInt` |
| Potentially malformed or malicious data | Arbitrary input | Validate format, radix, range; catch errors at boundary |

A common wrong choice is **using `decode` for all numeric data** just because it understands `0x`. If input has `"010"` and the business means ten, `decode` will return eight. Decide the **leading-zero policy** before picking the API.

## 11. Standalone runnable Java 17+ program

Save as `ParseVsLiteralDemo.java`:

```java
public class ParseVsLiteralDemo {
    static String parse(String text, int radix) {
        try {
            return Integer.toString(Integer.parseInt(text, radix));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    static String decode(String text) {
        try {
            return Integer.toString(Integer.decode(text));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        int hex = 0x2A;
        int binary = 0b101010;
        int separated = 1_000_000;
        int octal = 010;
        System.out.println("Literals: " + hex + ", " + binary
                + ", " + separated + ", " + octal);

        System.out.println("parseInt(2A,16): " + parse("2A", 16));
        System.out.println("parseInt(0x2A,16): " + parse("0x2A", 16));
        System.out.println("decode(0x2A): " + decode("0x2A"));

        System.out.println("parseInt(101010,2): " + parse("101010", 2));
        System.out.println("parseInt(0b101010,2): "
                + parse("0b101010", 2));

        System.out.println("parseInt(1_000): " + parse("1_000", 10));
        System.out.println("parseInt(1_000 after removing underscore): "
                + parse("1_000".replace("_", ""), 10));

        System.out.println("parseInt(010): " + parse("010", 10));
        System.out.println("decode(010): " + decode("010"));
        System.out.println("parseInt(09): " + parse("09", 10));
        System.out.println("decode(09): " + decode("09"));

        System.out.println("parseInt(-2A,16): " + parse("-2A", 16));
        System.out.println("decode(-0x2A): " + decode("-0x2A"));
        System.out.println("parseInt(42L): " + parse("42L", 10));
        System.out.println("parseInt(space42): " + parse(" 42", 10));
        System.out.println("parseInt(2147483648): "
                + parse("2147483648", 10));

        int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("unsigned bits: " + bits);
        System.out.println("unsigned decimal: "
                + Integer.toUnsignedString(bits));
    }
}
```

Compile and run:

```bash
javac --release 17 ParseVsLiteralDemo.java
java ParseVsLiteralDemo
```

Stdout:

```text
Literals: 42, 42, 1000000, 8
parseInt(2A,16): 42
parseInt(0x2A,16): INVALID
decode(0x2A): 42
parseInt(101010,2): 42
parseInt(0b101010,2): INVALID
parseInt(1_000): INVALID
parseInt(1_000 after removing underscore): 1000
parseInt(010): 10
decode(010): 8
parseInt(09): 9
decode(09): INVALID
parseInt(-2A,16): -42
decode(-0x2A): -42
parseInt(42L): INVALID
parseInt(space42): INVALID
parseInt(2147483648): INVALID
unsigned bits: -1
unsigned decimal: 4294967295
```

All `INVALID` lines are produced by the helper **intentionally catching `NumberFormatException`**, not a syntactic expression returned by `parseInt`. In real applications, errors should carry field/line/input-policy context and be handled appropriately, rather than silently turning malformed data into a valid number.

The example simultaneously demonstrates:
- The compiler accepts `0x`, `0b`, and underscores in numeric literals.
- `parseInt` requires **unprefixed digits** and an explicit radix.
- `decode` understands certain prefixes yet has its own octal policy.
- `parseUnsignedInt` interprets all 32 bits when an unsigned input exceeds `Integer.MAX_VALUE`.

## 12. Testing the input parser against the contract

When building a numeric input API, do not test only small valid numbers. At minimum, include:

| Group | Example | Question to answer |
| --- | --- | --- |
| Normal decimal | `"42"`, `"-42"`, `"+42"` | Are signs supported? |
| Hex prefix | `"0x2A"`, `"0X2A"`, `"#2A"` | Which parser accepts them? |
| Prefixed binary | `"0b1010"` | Should `0b` be stripped automatically? |
| Leading zero | `"010"`, `"09"`, `"00042"` | Base 8, base 10, or an identifier? |
| Valid underscore | `"1_000"`, `"0xCA_FE"` | Is group separation allowed? |
| Boundary underscore | `"_100"`, `"100_"`, `"0x_FF"` | Are they rejected? |
| Repeated underscores | `"1__0"` | Java literals allow between digits; does input policy allow it? |
| `L` suffix | `"42L"` | Should the suffix be stripped, and what is the target type? |
| Whitespace | `" 42 "`, tab, newline | Trim, strip, or reject? |
| Out of bounds | `"2147483648"`, `"-2147483649"` | How is signed overflow reported? |
| 32-bit unsigned | `"FFFFFFFF"` | Do we need to keep bit pattern and print unsigned? |
| Invalid radix | `1`, `37` | Does the parser throw `NumberFormatException`? |
| Empty/digitless string | `""`, `"-"`, `"0x"` | Is the error message clear? |
| Non-ASCII characters | Unicode digits, typographic minus signs | Is there a clear policy? |

If building a custom parser, always test **consistency between validation and parsing**: a string passing the validator must never be interpreted in a different radix or value than expected; an invalid input must be rejected rather than "fixed to run."

### How should untrusted data be handled?

A transparent processing flow is:

1. Document the input **schema**: signed/unsigned, radix, prefix, sign, underscores, whitespace, length, and numeric range.
2. Check null, empty, and length limits before processing overly large strings.
3. Validate the syntax of the entire string, not just "contains a digit."
4. Normalize **only allowed symbols**, such as valid prefixes and underscores.
5. Call the parser for the proper radix and value range.
6. Catch `NumberFormatException` at the boundary and report errors per schema; never catch all exceptions and return 0.
7. Test numbers near `Integer.MIN_VALUE`/`Integer.MAX_VALUE`, unsigned cases, and boundary inputs.

Appropriate length limits are especially important if the parser receives huge strings from requests or large datasets. In all cases, never use runtime evaluation of user-supplied Java code just to "get the same literal syntax."

## 13. Common misconceptions

| Misconception | Reality | How to avoid |
| --- | --- | --- |
| "`parseInt` can read any Java `int` literal" | The parser has a different grammar from the compiler | Specify the exact input format and choose the API |
| "`radix=16` will automatically understand `0x`" | `x` is not a radix-16 digit | Strip prefix with validation or use `decode` |
| "`parseInt("010")` is like literal `010`" | Decimal parser gives 10; octal literal gives 8 | Fix the radix/leading-zero policy |
| "`decode` is always better than `parseInt`" | `decode("010") == 8`, `decode("09")` errors | Only use if prefix/octal policy is needed |
| "Compiler allows underscores so the parser accepts them too" | `parseInt("1_000")` errors | Deliberate validation + normalization |
| "Stripping all underscores is always right" | Can accept invalid strings like `_100` | Run validator before replace |
| "`parseInt("42L")` understands the long suffix" | `L` suffix is source syntax | Choose `Long.parseLong("42")` if `long` is needed |
| "Failing to parse 32-bit hex means the literal is invalid" | `0xFFFFFFFF` can be a valid bit-pattern int literal | Distinguish signed parser from unsigned pattern |
| "A `String` containing numeric code is parsed by compiler as a Java token" | Strings are only data | Separate runtime parser, never evaluate code |
| "All digit characters must be ASCII" | `Character.digit` supports Unicode in many cases | Set a separate ASCII policy if schema requires it |
| "`trim` is enough to parse every numeric form" | Does not handle prefixes/underscores/suffixes | Parse according to defined format |
| "`parseInt` failure is a compile error" | `NumberFormatException` occurs at runtime | Catch/propagate errors at boundary |
| "Writing a regex easily mimics all Java numeric literals" | Grammar has complex edge cases and width/suffix semantics | Only accept syntax actually needed |

## 14. Self-check questions

1. Why does `int x = 0x2A;` compile while `Integer.parseInt("0x2A",16)` throws an exception? How does `Integer.parseInt("2A",16)` differ?
2. For `0b101010` and `"0b101010"`, which component processes the source token and which processes the String content?
3. What values do `Integer.parseInt("010")`, `Integer.parseInt("010",8)`, and literal `010` have?
4. Why is literal `09` a compile error while `Integer.parseInt("09")` returns 9?
5. What does `Integer.decode("09")` return? Should `decode` be used when input often starts with 0 yet must be decimal?
6. Why does `Integer.parseInt("1_000")` fail? If stripping underscores, which positions must be checked first?
7. Is literal `1__0` valid in Java? Must an input API necessarily accept it?
8. What common value do `Integer.parseInt("-2A",16)` and `Integer.decode("-0x2A")` return? Which API accepts the prefix?
9. Why is `int x = 0xFFFF_FFFF;` valid and equal to −1, whereas `Integer.parseInt("FFFFFFFF",16)` errors? Which case does `parseUnsignedInt` solve?
10. When should `"00042"` be kept as a `String` instead of converting to a number?
11. If receiving the string `"42L"` from a file, is it a Java numeric literal or simply a text value? What should the input contract decide?
12. State the difference between a compile-time syntax error in a literal and a runtime `NumberFormatException` during parsing.
13. If a parser following the **entire** Java expression syntax is needed, is `Integer.parseInt` enough? Why should user source code not be executed directly?

## 15. Official documentation

- [Java Language Specification `3.10.1 — Integer Literals (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.1): literal grammar for decimal, hexadecimal, octal, binary, underscores, and the `L` suffix.
- [Java SE 17 — `Integer.parseInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String,int)): radix requirement, sign, valid digits, signed range.
- [Java SE 17 — `Integer.decode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#decode(java.lang.String)): accepts `0x`/`0X`/`#` prefixes, octal leading 0, sign.
- [Java SE 17 — `Integer.parseUnsignedInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseUnsignedInt(java.lang.String,int)): parses 32-bit unsigned integer representations.
- [Java SE 17 — `Character.digit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#digit(char,int)): how radix-compatible digits are determined.

**Key takeaway:** The Java compiler handles `0x`, `0b`, leading zeros, underscores, and suffixes as **source-code numeric literal syntax**. `Integer.parseInt` processes **runtime String data**: optional leading sign, digits in the radix, without automatically understanding prefixes/underscores/suffixes. Use `Integer.decode` if you genuinely want hex/octal prefixes, `parseUnsignedInt` for 32-bit unsigned patterns, or build deliberate validation + normalization. What matters is **defining the input schema clearly**, rather than expecting the parser to behave like the compiler.