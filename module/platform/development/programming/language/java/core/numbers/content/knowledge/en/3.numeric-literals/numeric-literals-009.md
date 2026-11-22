# Literals, Constant Expressions, and Differences from `String` Parsing in Java

When writing `int n = 42;`, Java reads `42` directly as a **literal in source code**. When writing `int n = Integer.parseInt("42");`, Java receives a **character string** and performs **runtime parsing**. Meanwhile, `int n = 40 + 2;` is a **constant expression** that the compiler can evaluate. All three can yield the value 42, yet their valid syntax, error-checking phase, type-casting rules, and overflow behavior differ.

This lesson distinguishes these three mechanisms in Java 17+ so you can read literals across bases accurately, understand constant expressions, and convert text data into numbers safely.

## 1. Three Mechanisms, Three Processing Times

| Mechanism | Example | When Is It Processed? | Key Point to Remember |
| --- | --- | --- | --- |
| **Literal** in source code | `0x2A`, `42L`, `1.5e2` | Compiler parses the source code | Prefixes/suffixes are language syntax, not characters stored inside the value |
| **Compile-time constant expression** | `20 + 22`, `3 * (4 + 2)` | Value is determined per JLS rules at compile time | Only a subset of operators, literals, and constant variables are valid; ordinary method calls are not included |
| **Parsing `String` to a number** | `Integer.parseInt("42")` | At runtime | The method accepts a string, radix, and its own parser rules; invalid input can throw `NumberFormatException` |

Some examples with the same result:

```java
int fromLiteral = 42;
int fromExpression = 40 + 2;
int fromText = Integer.parseInt("42");
```

The first and second lines can be checked and resolved without runtime data. The third line **requires a method call** even when the argument is a string literal. `"42"` is a `String` literal, **not** an integer literal.

> **Quick distinction:** double quotes create a `String`; `0x`, `0b` prefixes, `L`/`F` suffixes, and underscores inside numeric literals follow source-code rules. Do not assume that `String` parsers accept all literal syntax.

## 2. Integer Literals: Base, Sign, Type, and Limits

### 2.1. Ways to Write the Same Value

```java
int decimal = 42;       // Base 10
int binary  = 0b101010; // Base 2
int octal   = 052;      // Base 8
int hex     = 0x2A;     // Base 16
```

All four variables have the mathematical value **42**. The base only affects **how it is written in source code**. After compilation, addition/subtraction/comparison operators work on the value and type, carrying no "original base." To display the value again in another base, use `Integer.toBinaryString`, `Integer.toOctalString`, `Integer.toHexString`, or `Integer.toString(value, radix)`.

| Literal Notation | Base | Decimal Value | Notes |
| --- | ---: | ---: | --- |
| `10` | 10 | 10 | Standard form |
| `0b1010` or `0B1010` | 2 | 10 | Only digits `0` and `1` |
| `012` | 8 | 10 | Starts with `0`; very easy to mistake for decimal |
| `0xA` or `0XA` | 16 | 10 | Digits `0-9` and `a-f`/`A-F` |
| `10L` | 10 | 10 | Literal of type `long` |

**Leading-zero pitfall:** in Java code, `010` is **octal 8**, whereas the string `"010"` carries no fixed base; the parser decides the string's meaning (see Section 4). Literals `08` or `09` are compile errors, because 8 and 9 do not belong to base 8.

### 2.2. `int` and `long` Literals

A decimal integer literal without an `L` suffix has type `int`, provided it lies within the allowed range (with a special syntax exception for `-2147483648`). The `L` or `l` suffix gives type `long`; write `L` so you do not mistake `l` for the digit `1`.

```java
int count = 2_000_000;
long largeCount = 3_000_000_000L;

// long invalid = 3_000_000_000; // Compile error: decimal literal exceeds int.
// long alsoValid = 3_000_000_000L;
```

For integers, writing `-42` is the **minus operator** placed before the literal `42`; the minus sign is not a character inside the numeric literal. Java has a special rule for writing minimum values:

```java
int minInt = -2147483648;
long minLong = -9223372036854775808L;
```

In that context, a positive decimal literal of magnitude `2^31` (or `2^63` with `L`) is only valid as the operand of unary minus according to language rules. You cannot use that same unsigned decimal digit sequence as a positive value of the corresponding type.

For base-16, base-8, and base-2 literals, Java also permits an all-ones bit pattern like `0xFFFF_FFFF` as an `int` with value **−1**. Do not assume a literal with only positive-looking hex digits guarantees a positive signed integer: **the type's width and sign** determine the interpretation.

### 2.3. Underscores Aid Readability Without Belonging to the Value

Java permits `_` **between digits** inside a numeric literal:

```java
int population = 1_234_567;
long flags = 0b1111_0000L;
double amount = 1_234.50;
```

They do not alter the value. Underscores **must not** be placed at the start/end of a literal, right next to a decimal point, before/after a type suffix, or in positions where they do not sit between valid digits. For example, `1_.0`, `1._0`, `42_L`, `_42` (which is read as an identifier), and `42_` are not valid numeric literal notations as intended.

**`"1_234"` is different text data:** the underscore actually exists in the string, and `Integer.parseInt("1_234")` throws `NumberFormatException`. The parser does not automatically apply the compiler's numeric literal formatting rules.

## 3. Floating-Point Literals and Representation Effects

`double` is the default type for literals with a decimal point or decimal exponent; the `f`/`F` suffix selects `float`; `d`/`D` can explicitly specify `double`:

```java
double a = 1.5;
double b = 15e-1;
double c = 1.5D;
float d = 1.5f;
double e = 0x1.8p1; // Base-16 floating-point literal: 1.5 * 2^1 = 3.0.
```

Base-16 floating-point literals start with `0x` and use a `p`/`P` exponent as a power of **2**, e.g., `0x1.8p1` equals 3.0. This notation is useful when you need to describe binary bits/digits accurately; the `e` exponent is for decimal floating-point literals.

`0.1` in code is a `double` literal, yet the mathematical value 1/10 has no finite representation in binary64; the stored value is the nearest binary number. That the expression `0.1 + 0.2` prints `0.30000000000000004` is a **floating-point representation** issue, distinct from what string syntax a parser accepts.

There is no Java numeric literal corresponding directly to the tokens `NaN` or `Infinity`; use `Double.NaN` and `Double.POSITIVE_INFINITY`. Conversely, `Double.parseDouble("NaN")` or `Double.parseDouble("Infinity")` can parse those special strings. Therefore, the set of strings accepted by parsers does not completely match the language's numeric literal syntax.

If you need exact decimal arithmetic matching text input, consider `BigDecimal` from a string: `new BigDecimal("0.1")` preserves exact decimal 0.1; `new BigDecimal(0.1)` receives the approximation already inside `double` and can produce an unexpectedly long decimal expansion.

## 4. `String` Parsing: Radix, Prefixes, Signs, and Exceptions

### 4.1. `parseInt` Uses Base 10 by Default

```java
int a = Integer.parseInt("42");      // 42
int b = Integer.parseInt("+42");     // 42
int c = Integer.parseInt("-42");     // -42
int d = Integer.parseInt("010");     // 10, not octal.
int e = Integer.parseInt("FF", 16);  // 255
int f = Integer.parseInt("1010", 2); // 10
```

`Integer.parseInt(String)` parses in **base 10**; `Integer.parseInt(String, int radix)` uses the specified radix from `Character.MIN_RADIX` (2) to `Character.MAX_RADIX` (36). Base 16 accepts hex digit characters without requiring `0x`. For bases greater than 10, letters represent digits with values 10 and above.

**Easily confused cases:**

| Input and API | Result |
| --- | --- |
| `Integer.parseInt("010")` | 10 (decimal) |
| `Integer.parseInt("010", 8)` | 8 (octal) |
| `Integer.parseInt("FF", 16)` | 255 |
| `Integer.parseInt("0xFF")` | `NumberFormatException` |
| `Integer.parseInt("0xFF", 16)` | `NumberFormatException` because `0x` prefix is invalid for `parseInt` |
| `Integer.parseInt("1_000")` | `NumberFormatException` |
| `Integer.parseInt(" 42 ")` | `NumberFormatException` due to whitespace |
| `Integer.parseInt("2147483648")` | `NumberFormatException` because it exceeds `int` range |
| `Long.parseLong("2147483648")` | 2147483648 as a `long` |

A leading `+`/`-` sign is valid according to parser rules. Never silently ignore `NumberFormatException`: it is usually a signal of malformed input or a value exceeding allowed bounds.

### 4.2. `Integer.decode` Supports Radix Prefixes, but Watch Out for Leading 0

`Integer.decode(String)` recognizes `0x`/`0X`/`#` prefixes as base 16, a leading `0` as base 8, and everything else as base 10. It can accept a sign **before** the prefix. A corresponding method exists on `Long.decode`.

```java
Integer.parseInt("010");    // 10
Integer.decode("010");      // 8
Integer.decode("0xFF");     // 255
Integer.decode("#FF");      // 255
Integer.decode("-0xA");     // -10
```

**Do not use `decode` indiscriminately for user-supplied numeric codes** if the business format is always decimal, because the string `"010"` might mean an identifier or the number 10 yet get interpreted as octal 8. Determine the data's radix via the **input contract**, not parser convenience.

### 4.3. Other Parsers Have Different Contracts

- `Long.parseLong(String)`/`Long.parseLong(String, radix)`: similar behavior to `Integer.parseInt`, but with a larger `long` range; `parseLong` does not accept `0x` automatically.
- `Integer.parseUnsignedInt(String)`: parses an **unsigned 32-bit** integer in the range 0 to 4,294,967,295 while returning the bit pattern as `int`. Use `Integer.toUnsignedLong` or `Integer.toUnsignedString` to manipulate/display it as unsigned; Java still has no separate `unsigned int` primitive.
- `Double.parseDouble(String)` and `Float.parseFloat(String)`: accept floating-point syntax, exponents, hex floating-point forms, and special strings like `NaN`/`Infinity`. They do not support underscores meant solely for source-code numeric literals.
- `new BigInteger(String, radix)`: parses an arbitrary-magnitude integer in the specified radix; `new BigDecimal(String)`: parses an exact decimal number per `BigDecimal` syntax. Do not assume they understand Java literal prefixes or locale grouping characters.

For user input, `parseInt` does not strip whitespace; you can **explicitly** call `strip()` when the contract allows. `Double.parseDouble` handles certain whitespace according to its own rules, so do not rely on identical whitespace behavior across all parsers. Explicitly specify whether whitespace, `+` signs, and non-ASCII digits are permitted; for strictly standardized sources (APIs, identifiers), validate syntax before parsing.

### 4.4. Radix When Converting Numbers to Strings

```java
int number = 255;
String hex = Integer.toString(number, 16);  // "ff"
String binary = Integer.toBinaryString(number); // "11111111"
int restored = Integer.parseInt(hex, 16);   // 255
```

`Integer.toHexString`/`toBinaryString` operate on the bit representation for negative numbers; for instance, `Integer.toHexString(-1)` produces `"ffffffff"`. That string means 4,294,967,295 if interpreted as an **unsigned 32-bit** number, so `Integer.parseInt("ffffffff", 16)` throws `NumberFormatException` because it exceeds `Integer.MAX_VALUE`. To restore the bits with unsigned semantics, use `Integer.parseUnsignedInt("ffffffff", 16)` or logic matching your requirements.

## 5. What Is a Compile-Time Constant Expression?

A **compile-time constant expression** is an expression that the Java Language Specification allows to be evaluated at compile time, built from literals, certain operators, and **constant variables**. Not every expression that always evaluates to the same value is a constant expression by the language definition.

Example:

```java
int a = 2 * (3 + 4);             // Constant expression: 14.
String label = "Java " + "17";  // String concatenation constant expression.

final int base = 10;
int b = base + 4;                // base is a constant variable, b = 14.

int c = Integer.parseInt("14"); // Runtime method call: not a constant expression.
int d = Math.abs(-14);          // Method call: not a constant expression.
```

A **constant variable** is a `final` variable of primitive type or `String` initialized with a constant expression. A `final` variable is not automatically a constant variable:

```java
final int fixed = 20;                    // Constant variable.
final int parsed = Integer.parseInt("20"); // final, but not a constant variable.
final Integer boxed = 20;               // Wrapper Integer is not a constant variable.
```

Even though a developer sees that `Integer.parseInt("20")` always returns 20 in this case, **method calls are not allowed** in compile-time constant expressions under Java's rules. "The compiler can optimize code" also does not mean "the language treats that expression as a compile-time constant."

### 5.1. Narrowing Conversion for Constant Expressions

Java permits certain conversions from an `int` constant expression to `byte`, `short`, or `char` **without a cast**, if the compile-time value fits in the target range:

```java
byte total = 100 + 20; // Valid: constant 120 fits in byte.
char letter = 65;      // Valid: value 65 fits in char.

final int offset = 20;
byte alsoFine = 100 + offset; // Valid: constant variable.

int runtimeOffset = 20;
// byte notAllowed = 100 + runtimeOffset; // Compile error: non-constant int expression.
// byte tooBig = 100 + 30;               // Compile error: 130 does not fit in byte.
```

A common puzzling case:

```java
byte x = 10;
byte y = 20;
// byte z = x + y; // Error: integer addition promotes byte operands to int.
int z = x + y;     // Valid.
```

The fact that two `byte` variables hold small values **does not give `x + y` type `byte`**. The compiler checks **the expression's type** and conversion rules, not merely whether the values look small when reading the code.

### 5.2. Constants in `case` and Annotations

For integer-based `switch` statements (Java 17), `case` labels must be valid constant expressions:

```java
final int code = 10;
int input = 11;
switch (input) {
    case code + 1 -> System.out.println("matched"); // Valid.
    default -> System.out.println("other");
}

// case Integer.parseInt("11") -> ... // Invalid: method call is not a constant expression.
```

Many annotation elements also require compile-time constant values (or special expression kinds compatible with the annotation element type). When a runtime API is needed instead of a source constant, move the logic to an appropriate place; you cannot turn `parseInt` into a constant expression simply by marking the result `final`.

### 5.3. Overflow Also Occurs Inside Constant Expressions

Java does not automatically widen `int` to `long` just because the target variable is `long`. An integer constant expression evaluated as `int` can overflow, and then **the overflowed result** is assigned:

```java
long wrong = 1_000_000 * 3_000;   // -1294967296: int multiplication overflows.
long correct = 1_000_000L * 3_000; // 3000000000: long multiplication.
```

Because the expression has type `int`, the compiler can precompute the result according to `int` arithmetic rules, including overflow; compiling successfully **does not guarantee the expected mathematical result**. `Math.multiplyExact` can detect overflow in runtime calculations; if a product needs type `long`, ensure at least one operand is `long` **before the multiplication**.

## 6. Why Runtime Parsers and Constant Expressions Require Different Error Handling

Errors fall into two distinct groups:

| Situation | Phase / Behavior | How to Handle |
| --- | --- | --- |
| `int x = 0b102;` | Fails to compile: digit not in base 2 | Fix the literal in source code |
| `int x = 08;` | Fails to compile: invalid octal literal | Use `8` if decimal is intended |
| `long x = 3000000000;` | Fails to compile: unsuffixed decimal literal exceeds `int` | Add `L` |
| `byte b = 130;` | Fails to compile: constant expression does not fit target type | Change type/upper bound or handle data |
| `Integer.parseInt("0xFF")` | Runtime `NumberFormatException` | Specify radix on unprefixed string, or use `decode` intentionally |
| `Integer.parseInt("2147483648")` | Runtime `NumberFormatException` from overflow | Use `Long.parseLong` if domain allows |
| `Integer.parseInt(userInput)` with invalid string | Runtime `NumberFormatException` | Validate per contract, catch at input boundary |
| `new BigDecimal("0.1")` | Runtime creates exact decimal number | Choose precision/scale and rounding policy as needed |

You cannot "catch" a literal syntax error in `try/catch`, because the program has not even compiled successfully. Conversely, `String` parsing is a runtime operation so input sources must be validated, especially at APIs, CLIs, data files, and input forms.

### 6.1. Controlled Input Parsing

```java
static int parseNonNegativeCount(String input) {
    if (input == null || !input.matches("[0-9]+")) {
        throw new IllegalArgumentException("Count must contain decimal digits");
    }
    int count = Integer.parseInt(input); // May throw NumberFormatException if exceeding int.
    return count;
}
```

The illustrative example above **intentionally restricts input to ASCII digits 0–9, no sign, and no whitespace**. The regex accepts `"0007"` as 7; business rules may permit or forbid leading zeros. If you need to support all Unicode digits or plus/minus signs, adjust validation per your contract. A syntactically valid regex **does not guarantee the number fits in `int`**; you still must handle `NumberFormatException` on overflow.

Do not arbitrarily "sanitize" input by stripping all `_`, commas, dots, or spaces: `"1,234"` may be a thousands-grouped number in one locale yet a decimal separator in another. For locale-formatted numeric input, use `NumberFormat` formatting/parsing and explicitly define locale rules; for machine protocols, prefer canonical numeric formats and explicit radixes.

## 7. Standalone Runnable Java 17+ Example

Save the file as `LiteralConstantParsingDemo.java`:

```java
import java.math.BigDecimal;

public class LiteralConstantParsingDemo {
    public static void main(String[] args) {
        int binary = 0b101010;
        int octal = 052;
        int hex = 0x2A;
        System.out.println("Three radices: " + binary + ", " + octal + ", " + hex);

        final int base = 10;
        byte folded = 100 + base;
        System.out.println("Constant expression to byte: " + folded);

        System.out.println("Literal 010: " + 010);
        System.out.println("parseInt 010: " + Integer.parseInt("010"));
        System.out.println("decode 010: " + Integer.decode("010"));
        System.out.println("parseInt FF radix 16: " + Integer.parseInt("FF", 16));
        System.out.println("decode 0xFF: " + Integer.decode("0xFF"));

        long wrong = 1_000_000 * 3_000;
        long correct = 1_000_000L * 3_000;
        System.out.println("Overflow before long: " + wrong);
        System.out.println("Long multiplication: " + correct);

        System.out.println("Hex float: " + 0x1.8p1);
        System.out.println("Exact decimal sum: "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));

        try {
            Integer.parseInt("1_000");
        } catch (NumberFormatException ex) {
            System.out.println("Underscore in parsed String: invalid");
        }

        try {
            Integer.parseInt("2147483648");
        } catch (NumberFormatException ex) {
            System.out.println("Beyond int: invalid");
        }

        System.out.println("Long parser: " + Long.parseLong("2147483648"));
    }
}
```

Run in the directory containing the file with JDK 17 or newer:

```bash
javac LiteralConstantParsingDemo.java
java LiteralConstantParsingDemo
```

Output:

```text
Three radices: 42, 42, 42
Constant expression to byte: 110
Literal 010: 8
parseInt 010: 10
decode 010: 8
parseInt FF radix 16: 255
decode 0xFF: 255
Overflow before long: -1294967296
Long multiplication: 3000000000
Hex float: 3.0
Exact decimal sum: 0.3
Underscore in parsed String: invalid
Beyond int: invalid
Long parser: 2147483648
```

Here, the value 42 from the three radix literals is identical, whereas the string `"010"` can be interpreted as 10 or 8 depending on the parser. `byte folded` is valid thanks to a compile-time constant expression. `int` multiplication produces an already overflowed result when assigned to `long`; with `L`, the expression uses `long` from the start. Both `NumberFormatException` exceptions are caught because they are **runtime parsing** errors.

## 8. Checklist When Reading and Writing Numbers in Java

1. **Is the number written in code or coming from external data?** If it is in Java code, apply literal rules. If receiving a string, use a parser with a clear contract.
2. **Is the radix unambiguous?** `0b`/`0x` literals or leading zero have meaning in source code; `parseInt` defaults to decimal, while `decode` handles prefixes and octal. Choose the parser matching the data format.
3. **Does the syntax depend on compilation?** `_` separators, `L`/`F` suffixes, and hex float literals are part of source-code grammar; string parsers accept input according to their own rules.
4. **Is this truly a compile-time constant expression?** Permitted literals and operations can be constant; calling `parseInt` is not constant even with argument `"42"`. `final` is only one necessary condition for a constant variable.
5. **Are the value range and operation type appropriate?** Use `L` when a decimal literal is large or an operation needs `long`; do not assign after an `int` expression has already overflowed.
6. **Where will invalid runtime input be handled?** Define rules for signs, whitespace, radix, digit grouping, locale, and error reporting. Catch `NumberFormatException` at data ingestion boundaries; do not hide errors behind undesigned default values.
7. **Are exact decimals or integers beyond `long` needed?** Use `BigDecimal(String)`/`BigInteger` per the data contract rather than trying to force everything through `double` or `int`.

### Self-Check Questions

- Why does `010` in Java have value 8 while `Integer.parseInt("010")` has value 10? What value does `Integer.decode("010")` produce?
- Why does `byte b = 100 + 20;` compile, whereas `int x = 20; byte b = 100 + x;` does not?
- Why does `final int x = Integer.parseInt("5");` not make `x` a constant variable by Java's definition?
- Why does `long total = 1_000_000 * 3_000;` give a different value from `long total = 1_000_000L * 3_000;`?
- Is `"0xFF"` valid with `Integer.parseInt(..., 16)` or `Integer.decode(...)`? For an API that only accepts decimal numbers, which option avoids misinterpreting `"010"`?
- Why can a **syntactically** valid numeric input string still throw `NumberFormatException`?

**Rule of thumb:** literals belong to Java syntax at compile time; constant expressions are a narrower concept than "calculations that always return the same result"; `String` parsing is a runtime contract with its own radix, syntax, and range-checking rules. Keeping these three mechanisms distinct prevents bugs involving bases, casting, overflow, and input data.