# Underscores in Numeric Literals and Invalid Positions

> **Java core — language-basics / Literal**  
> **Requirements:** JDK 17+; a standalone Java program without external libraries.  
> **Objective:** Know when `_` may be written in a numeric literal, recognize forbidden positions, and distinguish compile-time literal syntax from strings parsed at runtime.

## 1. What is the `_` character used for?

Java allows inserting underscores between digits in **numeric literals** to improve readability, for example:

~~~java
int population = 1_000_000;
long distance = 9_000_000_000L;
double rate = 12.3_4;
~~~

The `_` here **does not change the value or data type**. `1_000_000` and `1000000` are the exact same `int` value; `9_000_000_000L` is still a `long` literal because of the `L` suffix.

| Notation | Value | Why is it valid? |
| --- | ---: | --- |
| `1_000_000` | 1000000 | Groups decimal digits |
| `0b1111_0000` | 240 | Groups bits after the binary prefix `0b` |
| `05_2` | 42 | Groups digits of an octal literal (starts with `0`) |
| `0xCA_FE` | 51966 | Groups hexadecimal digits |
| `1__000` | 1000 | **Multiple** consecutive `_` characters between two digits are still valid |
| `12.3_4` | 12.34 | Groups digits in the fractional part of a floating-point literal |
| `1.2e1_0` | 1.2 × 10¹⁰ | Underscore lies between digits of the exponent part |

Practical rule: **insert `_` between digits of the same literal part; do not place it at the boundary of a prefix, decimal point, exponent symbol, or type suffix.**

## 2. Invalid positions

| Invalid syntax | Reason | Valid syntax if preserving intent |
| --- | --- | --- |
| `123_` | Ends the literal with `_` | `123` or `1_23` |
| `0b_1010` | Immediately after the `0b` prefix | `0b1010` or `0b10_10` |
| `0x_FF` | Immediately after the `0x` prefix | `0xFF` or `0xF_F` |
| `1_.25` | Immediately before the decimal point | `1.25` |
| `1._25` | Immediately after the decimal point | `1.25` or `1.2_5` |
| `1e_10` | Immediately after the exponent symbol `e` | `1e10` or `1e1_0` |
| `1e+_10` | Immediately after the `+` sign of the exponent | `1e+10` |
| `123_L` | Immediately before the `L` type suffix | `123L` or `1_23L` |
| `12_f` | Immediately before the `f` suffix | `12f` or `1_2f` |

In addition, `_123` is a **potentially valid identifier**, **not** the numeric literal 123. Writing `int n = _123;` looks up a **variable named `_123`**, rather than putting the number 123 into `n`. A **lone** `_` cannot be used as an identifier in Java 17.

**Important distinction:** `1__000` is **valid**; do not infer that two consecutive underscores are always wrong. Its position relative to **digits, separators, and suffixes** is what decides validity.

## 3. Which numeric literal types does this apply to?

Underscore `_` syntax works for **integer literals** and **floating-point literals** in valid positions:

- Integers: decimal `4_200`, binary `0b1010_0101`, octal `07_52`, hexadecimal `0xAB_CD`, `long` such as `1_000L`.
- Floating-point: `3.14_15`, `1_2.5_0f`, or exponent `6.02e2_3`.
- Hexadecimal floating-point literals also have their own rules for digits and the `p` exponent; for example, `0x1.8p1_0` is a valid `double` literal (value 1536.0).

**Do not insert `_` arbitrarily into a prefix or syntax construct assuming the compiler will simply strip it out.** For instance, `0x_FF` and `1_.0` are not valid numeric literals.

Note that `-1_000` has the **unary minus operator** in front of the literal `1_000`; `_` still only serves to group digits. `L`, `f`, and `d` specify the literal type under their respective rules, not digits that `_` can sit next to.

## 4. Runnable Java 17+ program

Create the file **NumericUnderscoreDemo.java** and copy the full code:

~~~java
public class NumericUnderscoreDemo {
    public static void main(String[] args) {
        int decimal = 4_2;
        int binary = 0b1111_0000;
        int octal = 05_2;
        int hex = 0xCA_FE;
        int repeated = 1__000;
        long large = 9_000_000_000L;
        double fraction = 12.3_4;

        System.out.println("decimal=" + decimal);
        System.out.println("binary=" + binary);
        System.out.println("octal=" + octal);
        System.out.println("hex=" + hex);
        System.out.println("repeated=" + repeated);
        System.out.println("large=" + large);
        System.out.println("fraction=" + fraction);
        System.out.println("same42=" + (decimal == octal));

        try {
            Integer.parseInt("1_000");
            System.out.println("parse=OK");
        } catch (NumberFormatException exception) {
            System.out.println("parse=ERROR");
        }
    }
}
~~~

In a terminal (Bash, PowerShell, or Command Prompt), from the directory containing the file:

~~~bash
javac -encoding UTF-8 NumericUnderscoreDemo.java
java NumericUnderscoreDemo
~~~

**Expected output:**

~~~text
decimal=42
binary=240
octal=42
hex=51966
repeated=1000
large=9000000000
fraction=12.34
same42=true
parse=ERROR
~~~

Here `05_2` is an **octal** number: \(5 \times 8 + 2 = 42\). `0xCA_FE` is the hex number `CAFE` (51966 in decimal). Both are simply **ways of writing values in source code**, not special strings printed verbatim.

## 5. The compiler and input strings do not use the same rules

This is an essential distinction:

~~~java
int fromSource = 1_000;             // Valid: compiler understands Java literal.
int fromText = Integer.parseInt("1000"); // Valid: parses digit-only string.
~~~

However:

~~~java
Integer.parseInt("1_000"); // Throws NumberFormatException at runtime.
~~~

`Integer.parseInt` does not automatically strip `_` the way the Java compiler processes numeric literals. If an application wants users to enter `1_000`, you must define **format validation rules**, then process the input before converting its type. Do not blindly remove every `_` without checking, because invalid strings such as `_123` or `123_` could unintentionally become valid numbers.

Similarly, the literal `1_000L` contains the `L` suffix of **source code**, yet `Long.parseLong("1_000L")` does not accept that string.

## 6. Traps to check

| Misconception | What is true |
| --- | --- |
| "Having `_` turns a number's type into String." | False. A numeric literal still has its corresponding numeric type. |
| "`1__000` is always invalid." | False. Consecutive `_` characters between digits are permitted. |
| "`0x_FF` is equivalent to `0xFF`." | False. You cannot insert `_` right after a prefix. |
| "Line breaks or spaces next to `_` are also allowed." | False when it breaks a literal: `1_ 000` is no longer a valid numeric literal. |
| "`123_L` is a valid `long`." | False. The `L` suffix must follow a syntactically valid digit sequence. |
| "`parseInt("1_000")` works just like the compiler." | False. `parseInt` does not recognize `_` as a digit separator. |

**Deliberate experiment:** pick one invalid example from the table in Section 2, put it on its own line in `NumericUnderscoreDemo.java`, and run `javac` to observe the error. Then fix it and compile again. Do not put all invalid examples into the main program at once, because the program will fail to compile.

## 7. Short exercises

**Exercise 1 — Valid or invalid?** Classify the literals `1_234`, `1__234`, `1_`, `0b10_01`, `0b_1001`, `0xA_B`, `0x_AB`, `3.1_4`, and `3._14`. State the *position* that determines the result, rather than just writing "syntax error".

**Exercise 2 — Preserve the value.** Rewrite `1000000000L`, `0b11110000`, and `0xCAFEBABE` using `_` for readability without changing their values. Try printing each value to verify for yourself.

**Exercise 3 — Source vs. runtime.** Why does `Integer.parseInt("1000")` succeed while `Integer.parseInt("1_000")` fails? If you were building a configuration reader that accepts `_`, how would you validate underscore positions?

**Exercise 4 — Debug.** Fix the two invalid literals `1e_10` and `9_000_L`, and explain why the exponent symbol and suffix are not valid positions for `_`.

### Key takeaway

**The `_` character is a symbol to help humans read numeric literals more clearly; it carries no value and does not automatically extend runtime string parser syntax.** Place it **between valid digits**, optionally with multiple consecutive underscores; do **not** place it at the start/end of a literal or next to a prefix, decimal point, exponent symbol, or type suffix.
