# Underscores in Literals and Invalid Positions in Java

## 1. Purpose: Making Long Numbers Easier to Read Without Changing Value

Since Java 7, Java source code allows using the underscore `_` as a **digit-grouping character** inside a *numeric literal* (integer or floating-point literal). The `_` character is purely a **source-code formatting convention**, not an operation or a digit that contributes to the numeric value.

Example:

```java
int population = 12_345_678;
long accountId = 1_234_567_890_123L;
double ratio = 3.141_592_653_589_793;
```

The expressions above have the exact same values as their versions without underscores:

```java
int population = 12345678;
long accountId = 1234567890123L;
double ratio = 3.141592653589793;
```

**Core principle:** Underscores are allowed **between digits of the same numeric part**. They are not allowed to replace digits, split base prefixes, or stand adjacent to a decimal point, exponent indicator, or type suffix.

A *literal* is a value written directly in **source code** (like `1_000`). It differs from string data `"1_000"` processed while the program runs. This is the source of many bugs when working with `Integer.parseInt`.

## 2. Where Do Integer Bases Allow `_`?

Java has four basic ways to write an *integer literal*:

| Base | Notation | Valid Example | Decimal Value |
| --- | --- | --- | ---: |
| 10 (decimal) | Digits `0..9`, multi-digit positive numbers normally do not start with `0` | `1_234_567` | 1234567 |
| 2 (binary) | Prefix `0b`/`0B` followed by `0`, `1` | `0b1010_0101` | 165 |
| 8 (octal) | Integer starting with `0`, digits `0..7` | `0_52` | 42 |
| 16 (hexadecimal) | Prefix `0x`/`0X`, digits `0..9`, `A..F` | `0xCA_FE` | 51966 |

Other valid examples:

```java
int a = 12_34;             // decimal
int b = 1__000;            // Multiple consecutive _ between digits are still valid.
int c = 0b1111_0000;       // binary
int d = 0xA_B_C_D;         // hexadecimal: A..F are also digits in base 16.
int e = 05_2;              // octal = 42.
int f = 0_52;              // octal = 42; _ right after the leading 0 digit is valid.
long g = 9_876_543_210L;   // L is the long suffix, no _ adjacent to L.
```

The rules have an easily confused detail:

- In **binary and hexadecimal** numbers, the two characters `0b`/`0B` and `0x`/`0X` are **prefixes**, not part of the numeric value's digits. After the prefix must come a valid digit: `0b_1010` and `0x_FF` are **invalid**.
- In **octal** numbers, the first `0` digit is **one of the literal's digits**, so `0_52` and `0__52` are both **valid**. This is unlike the `0x`/`0b` prefixes.
- In **decimal** numbers, you can start a group with a non-`0` digit and use `_` in between, e.g., `1_000_000`. The `_` does not make `0_52` a decimal number; that sequence is still octal.
- For integer literals with an `L`/`l` suffix (`L` is recommended since it is easy to distinguish from `1`), `_` must appear **before the final digit**, not between the final digit and the suffix.

**Type width remains unchanged.** `1_000_000` is still an `int` literal; `1_000_000L` is `long`. Underscores do not make an out-of-range number valid and do not change the meaning of base prefixes.

## 3. Underscores in Floating-Point Literals

A `float`/`double` literal can contain different parts: integer part, decimal point `.`, fractional part, exponent part (if present), and type suffix `F`/`f`/`D`/`d` (if present).

Valid examples:

```java
double a = 12_345.67_89;
float b = 3.14_15F;
double c = 1.2_5e1_0;
double d = 1_2.5_0e+1_0;
double e = 0x1.fp1_0;
double f = 0xA_B.C_Dp+1_0;
```

How to read them:

- `12_345.67_89` has underscores **inside** the integer part and fractional part; no `_` sits next to the decimal point.
- `1.2_5e1_0` has underscores within the digits of the fractional part and **within** the digits of the exponent; the letter `e` is not sandwiched by `_`.
- `0x1.fp1_0` is a **hexadecimal floating-point literal**. In this system, the significand uses base-16 digits, while the exponent after `p`/`P` is a power of 2 written in decimal digits. The `_` in `1_0` of the exponent is valid.
- `F`/`f` selects `float`; `D`/`d` selects `double` (without a suffix, an ordinary floating-point literal has type `double`). Do not place underscores adjacent to the suffixes.

You must not place underscores **immediately before or after** `.`, `e`/`E`, `p`/`P`, the `+`/`-` sign of the exponent, or the type suffixes. Individual digit regions may contain underscores **between digits**.

For example, `1.25e1_0` is valid; `1.25e_10` is invalid; `1.25e+1_0` is valid; `1.25e+_10` is invalid.

**Distinguishing hexadecimal integers from hexadecimal floats:** `0xA_B` is an integer literal; `0x1.fp1_0` is a floating-point literal and requires the `p`/`P` exponent part. In both, `_` cannot be placed immediately after `0x`.

## 4. Invalid Positions: Quick Reference Table

The snippets in the "Invalid" column are **intentionally invalid code fragments** and should not be put directly into a compiling program.

| Invalid Position | Invalid | Valid | Why |
| --- | --- | --- | --- |
| Before first digit | `_123` (when intending a literal) | `123` | `_123` is parsed as an **identifier**, not a numeric literal. |
| After last digit | `123_` | `12_3` | The digit section cannot end with `_`. |
| Between `0` and `x` | `0_xFF` | `0xFF` | Cannot insert a separator into the base-16 prefix. |
| Immediately after `0x` | `0x_FF` | `0xF_F` | A hex digit must immediately follow the prefix. |
| Between `0` and `b` | `0_b101` | `0b101` | Cannot insert a separator into the base-2 prefix. |
| Immediately after `0b` | `0b_101` | `0b1_01` | A binary digit must immediately follow the prefix. |
| Before integer suffix | `1_000_L` | `1_000L` | There is no digit after `_` before `L`. |
| Before decimal point | `3_.1415` | `3.141_5` | `_` cannot sit next to `.`. |
| After decimal point | `3._1415` | `3.14_15` | `_` cannot start the fractional part. |
| Before exponent indicator | `1_e2` | `1e2` | Underscore cannot end the digit sequence before `e`. |
| After exponent indicator | `1e_2` | `1e2` | Underscore cannot start the exponent digit sequence. |
| After exponent sign | `1e+_2` | `1e+2` | `+`/`-` must be directly followed by exponent digits. |
| End of exponent | `1e2_` | `1e2_0` | Digit sequence cannot end with `_`. |
| Before `F`/`D` suffix | `3.14_F`, `2.0_D` | `3.14F`, `2.0D` | Suffixes are not digits. |
| Before hex `p` | `0x1.f_p4` | `0x1.fp4` | `_` cannot sit next to the binary exponent indicator. |
| After hex `p` | `0x1.fp_4` | `0x1.fp4` | Exponent must start with a digit, optionally preceded by a sign. |

A self-check rule: only use `_` to separate digits within **a contiguous group of digits**. If `_` would touch `.`, a **structural** letter (`x`, `b`, `e`, `p`, `L`, `F`, `D`), or an exponent `+`/`-` sign, rewrite it.

Distinguish these two cases: `0xA_B` is **valid** because `A` and `B` are hex digits; `0xA_p1` is **invalid** because `p` is the exponent indicator, not a hex digit.

## 5. Can Multiple Consecutive `_` Be Used?

**Yes**, as long as the entire run of underscores lies *between two digits belonging to the same numeric component*. Java rules do not restrict each spot to a single `_`.

```java
int number = 1________0;      // Valid: value 10.
int hex = 0xA___B;             // Valid: value 171.
int octal = 0__7;              // Valid: value 7 (octal).
double fraction = 1.2___5;     // Valid: value 1.25.
```

In practice, however, group digits sensibly—for example `1_000_000`, `0xCAFE_BABE`, or `0b1111_0000`; `1________0`, though valid, is hard to read.

With position-checking rules, an underscore run having **valid digits on both sides** is a necessary indicator, but remember both sides must belong to **the same digit section**: do not mistake a base prefix, decimal point, or exponent indicator for a digit.

## 6. Difference Between Source-Code Syntax and Runtime String Data

The `_` character is recognized by the *compiler* in a literal. At runtime, the value stored in the variable is the **numeric value**, carrying none of the grouping separators from the original notation.

```java
int amount = 1_000;
System.out.println(amount); // Prints 1000, does not print 1_000.
```

However, standard string-parsing functions **do not apply the compiler's literal syntax**:

```java
Integer.parseInt("1000");      // 1000.
Integer.parseInt("1_000");     // Throws NumberFormatException.
Double.parseDouble("3.1415");  // 3.1415.
Double.parseDouble("3.14_15"); // Throws NumberFormatException.
```

Therefore, if you receive input from an API, config file, or form containing underscores, you must define whether the **data format** permits this grouping character. If it does, validate the input against a clear rule before converting to a number. Do not blindly strip all `_`, because doing so could turn invalid strings like `"_100"` or `"10_"` into unexpectedly accepted data.

One illustration for an **unsigned decimal format allowing one or more `_` between digits**:

```java
static int parseGroupedDecimal(String input) {
    if (!input.matches("[0-9]+(?:_+[0-9]+)*")) {
        throw new IllegalArgumentException("Invalid decimal grouping");
    }
    return Integer.parseInt(input.replace("_", ""));
}
```

This is an **application-level rule** (supporting only unsigned decimal integers), not a complete parser for all Java literals. Data after stripping separators can still exceed the `int` range, in which case `Integer.parseInt` still throws `NumberFormatException`. If accepting very large decimal numbers, consider `BigInteger` and bound the input length.

Outside numeric literals, `_` can also appear in identifiers (subject to naming rules) or character/string literals; those occurrences do not automatically mean "digit grouping." Note that **a standalone single `_`** has been a reserved keyword since Java 9 and cannot be used as an independent variable name.

## 7. Runnable Java 17+ Example

Save in the file **`UnderscoreLiteralDemo.java`**:

```java
public class UnderscoreLiteralDemo {
    public static void main(String[] args) {
        int decimal = 1_234_567;
        int repeated = 1__000;
        int octal = 0_52;
        int hex = 0xCA_FE;
        int binary = 0b1010_0101;
        double fraction = 3.14_15;
        double scientific = 1.25e1_0;
        double hexadecimalFloat = 0x1.fp1_0;
        long id = 1_234_567_890L;

        System.out.println("decimal=" + decimal);
        System.out.println("repeated=" + repeated);
        System.out.println("octal=" + octal);
        System.out.println("hex=" + hex);
        System.out.println("binary=" + binary);
        System.out.println("fraction=" + fraction);
        System.out.println("scientific valid=" + (scientific == 12_500_000_000.0));
        System.out.println("hex float=" + hexadecimalFloat);
        System.out.println("long=" + id);

        try {
            Integer.parseInt("1_000");
        } catch (NumberFormatException ex) {
            System.out.println("String 1_000 cannot be parsed as int directly");
        }
    }
}
```

Compile and run commands:

```bash
javac UnderscoreLiteralDemo.java
java UnderscoreLiteralDemo
```

Output:

```text
decimal=1234567
repeated=1000
octal=42
hex=51966
binary=165
fraction=3.1415
scientific valid=true
hex float=1984.0
long=1234567890
String 1_000 cannot be parsed as int directly
```

You can verify compile errors yourself by **adding each of the following lines inside `main` and recompiling**. The lines are commented out so the complete example above remains runnable:

```java
// int invalid1 = 123_;
// int invalid2 = 0x_FF;
// int invalid3 = 0b_1010;
// long invalid4 = 1_000_L;
// double invalid5 = 3_.1415;
// double invalid6 = 3._1415;
// double invalid7 = 1e_3;
// double invalid8 = 1e+_3;
// double invalid9 = 0x1.fp_4;
```

These lines illustrate **literal syntax errors caught at compile time**, not `NumberFormatException` at runtime. Conversely, `Integer.parseInt("1_000")` in source code is completely valid syntax; it fails when the string-parsing method runs at runtime.

## 8. Coding Conventions for Readability

`_` is most helpful when grouping digits in a clear, meaningful way:

- Decimal numbers in groups of three digits from right to left: `1_000`, `25_000_000`.
- Binary numbers by byte or nibble: `0b1100_1010`, `0b1111_0000_1010_0101`.
- Hexadecimal numbers by byte/word: `0xFF_00_7F`, `0xCAFE_BABE`.
- Floating-point numbers with many digits can group integer, fractional, or exponent parts independently, but never place underscores next to delimiters.

There is no need to add `_` to very short numbers like `12` or `0xFF`. Avoid arbitrary grouping that obscures meaning, such as `12_34_56` when the rest of the project groups decimal digits by threes.

**In summary:** In Java, `_` helps humans read numeric literals while **changing neither the numeric value nor the data type**. Place it only between digits of the same numeric part; remember the important case that octal `0_52` is valid, whereas `0x_FF` and `0b_101` are invalid. Parsing string data is a separate task that must be handled according to the input format.

**References:** [Java Language Specification §3.10.1 — Integer Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.1), [§3.10.2 — Floating-Point Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.2), and [Oracle — Underscores in Numeric Literals](https://docs.oracle.com/javase/8/docs/technotes/guides/language/underscores-literals.html).