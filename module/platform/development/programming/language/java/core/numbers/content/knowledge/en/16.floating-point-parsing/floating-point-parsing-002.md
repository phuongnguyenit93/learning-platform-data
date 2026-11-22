# Decimal, Exponent, and Hex Forms Supported by Java Parsing APIs

## 1. Parsing strings into floating-point numbers: distinguish syntax from value

In Java, **Double.parseDouble(String)** and **Float.parseFloat(String)** convert a textual representation of a floating-point number into the corresponding IEEE 754 value. Both support standard decimal form, base-10 exponential notation, and hexadecimal floating-point form with a base-2 exponent. They also accept certain special representations such as NaN and Infinity.

Example:

~~~java
double a = Double.parseDouble("12.5");     // 12.5
double b = Double.parseDouble("1.25e2");   // 125.0
double c = Double.parseDouble("0x1.8p1");  // 3.0
float d = Float.parseFloat("-2.5E-1");    // -0.25f
~~~

Key point to remember: **strings passed to the API** and **literals written directly in Java source code** have similar syntax, but they are not identical. A string valid for the parser cannot necessarily be written verbatim as an untyped literal; conversely, underscore digit separators are allowed in certain Java literals but are not accepted by these parse methods.

## 2. Three main representation groups

| Group | Valid string examples | Meaning |
| --- | --- | --- |
| Standard decimal | "42", "-3.5", ".75", "8." | Base-10 digits, optional sign and decimal point |
| Decimal with exponent | "1e3", "-2.5E-2", "6.02e23" | Significand multiplied by 10 raised to the exponent |
| Hex with binary exponent | "0x1.8p1", "0X1P-2", "-0xA.BP3" | Significand written in base 16, multiplied by 2 raised to the exponent after p/P |

Here, the decimal separator in the string is always a **dot (.)**, even if users are accustomed to writing a comma. A plus/minus sign can precede the entire number; a plus/minus sign can also appear in the exponent immediately after e/E or p/P.

### 2.1. Decimal form

All of the following examples are valid for Double.parseDouble:

~~~text
0
123
+123.0
-0.125
.5
5.
0.000001
12f
12.5D
~~~

**f/F and d/D** are floating-point type suffixes accepted by the parser, even when the method returns the other type. For example, Double.parseDouble("12f") still returns a double value; the suffix in the string does not change the return type. In Java code, you should prefer suffix-free strings when receiving data from users or external systems.

Thousands separators must not be used in strings passed to Double.parseDouble: "1,000.5" is invalid. The string "1_000.5" is also invalid even though the literal 1_000.5 in *Java source code* is valid.

### 2.2. Decimal exponent notation: e/E

The intuitive syntax is:

~~~text
[+|-]significand[e|E][+|-]integer_exponent
~~~

The significand is a decimal number; the exponent is an integer representing a power of **10**.

- "1.5e2" = 1.5 × 10² = 150.0.
- "4E-3" = 4 × 10⁻³ = 0.004.
- "-2.5e+1" = -2.5 × 10¹ = -25.0.
- "1e0" = 1.0.

Once e/E appears, a valid exponent must follow it. "1e", "1e+", and "e3" are all invalid. The letter e/E does not mean Euler's mathematical constant; it is the decimal exponent indicator.

### 2.3. Hex form: 0x/0X and p/P

A hex floating-point number has three parts: a **0x or 0X** prefix, a significand in hex digits (0–9, a–f, A–F) optionally with a dot, and **p/P with a decimal integer exponent**. In terms of value:

~~~text
(hex_significand) × 2^(exponent)
~~~

For example, "0x1.8p1":

1. The hex integer part **1** has value 1.
2. The digit after the dot **8** in base 16 has value 8/16 = 0.5.
3. The significand equals 1.5.
4. p1 means multiply by 2¹, so the result equals **3.0**.

Other examples:

| String | Calculation | Result |
| --- | --- | --- |
| "0x1p0" | 1 × 2⁰ | 1.0 |
| "0x1p-2" | 1 × 2⁻² | 0.25 |
| "0x1.8p2" | (1 + 8/16) × 2² | 6.0 |
| "0XAp1" | 10 × 2¹ | 20.0 |
| "0xA.Bp-1" | (10 + 11/16) × 2⁻¹ | 5.34375 |

**p/P is mandatory in hex floating-point syntax**, even with an exponent of 0; "0x1" and "0xff" are not accepted by Double.parseDouble, whereas "0x1p0" and "0xffp0" are. The exponent after p/P is written in *decimal* digits (for instance, p10 means multiply by 2¹⁰); it is not a base-16 exponent. Because the letter e in the hex significand can be a hex digit, it cannot replace p/P.

Why hex form is useful: it directly expresses binary fractions and powers of 2. Many values like 0.5, 0.25, and 3.0 can be represented exactly in this form; decimal forms such as 0.1 usually require rounding when converted to binary.

## 3. Special strings accepted

In addition to finite numeric strings, both APIs accept **"NaN"** (*not a number*) and **"Infinity"**, optionally prefixed with a sign for special forms. The names are case-sensitive: "NaN" is valid, "nan" is not; "Infinity" is valid, "infinity" is not.

- "NaN": special value for a non-numeric result.
- "Infinity": positive infinity.
- "-Infinity": negative infinity.
- "-0.0": zero with a negative sign bit; it can matter in certain arithmetic and bit-level operations.

Do not conclude that every parsed result is finite merely because no NumberFormatException occurred. When a number is too large to represent, the parser may return Infinity; when the magnitude is too small, the parser may round to 0.0 or a *subnormal* value instead of throwing an exception.

## 4. Complete example: run and verify output

Create the file **FloatingTextFormsDemo.java**:

~~~java
public class FloatingTextFormsDemo {
    public static void main(String[] args) {
        String[] samples = {
                "12.5",
                "6.02e2",
                "0x1.8p1",
                "0x1p-2",
                "-0xA.Bp-1",
                "NaN",
                "Infinity",
                "1_000",
                "0xff",
                "1e"
        };

        for (String sample : samples) {
            try {
                double value = Double.parseDouble(sample);
                System.out.println(sample + " -> " + value);
            } catch (NumberFormatException exception) {
                System.out.println(sample + " -> INVALID");
            }
        }

        System.out.println("Hex form of 3.0: "
                + Double.toHexString(3.0));
        System.out.println("Overflow: "
                + Double.parseDouble("1e309"));
        System.out.println("Underflow: "
                + Double.parseDouble("1e-4000"));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac FloatingTextFormsDemo.java
java FloatingTextFormsDemo
~~~

Expected output:

~~~text
12.5 -> 12.5
6.02e2 -> 602.0
0x1.8p1 -> 3.0
0x1p-2 -> 0.25
-0xA.Bp-1 -> -5.34375
NaN -> NaN
Infinity -> Infinity
1_000 -> INVALID
0xff -> INVALID
1e -> INVALID
Hex form of 3.0: 0x1.8p1
Overflow: Infinity
Underflow: 0.0
~~~

The program illustrates four things: all three valid syntaxes go through the same API; hex form can be converted back via Double.toHexString; syntactically invalid strings raise NumberFormatException; and overflow or loss of magnitude can return special values or 0.0.

**Double.toHexString(double)** generates the hex representation of an existing double value (e.g., 3.0 becomes "0x1.8p1"); it is not a method for parsing an input string. Converting back and forth lets you inspect the stored binary value, but it does not turn binary floating-point numbers into an arbitrary-precision decimal numeric type.

## 5. Literal syntax in Java code differs from API input string syntax

Distinguish the contexts:

~~~java
double fromLiteral = 1_000.5;                  // Valid in Java code
double fromString = Double.parseDouble("1000.5"); // Valid
double fromHexLiteral = 0x1.8p1;             // Valid in Java code
double fromHexString = Double.parseDouble("0x1.8p1");
~~~

The following cannot be used to parse successfully:

~~~java
// Compiles, but throws NumberFormatException at runtime:
Double.parseDouble("1_000.5");
Double.parseDouble("0xff");
Double.parseDouble("0b1010");
Double.parseDouble("1,25");
~~~

Key differences:

| Expression or string | Java source code | Double.parseDouble |
| --- | --- | --- |
| 1_000.5 | Valid literal | String "1_000.5" is invalid |
| 0x1.8p1 | Valid double literal | String "0x1.8p1" is valid |
| 0xff | Valid hex integer literal | String "0xff" is invalid as a hex float |
| 0b1010 | Valid binary integer literal | String "0b1010" is invalid |
| 1,25 | Not a floating-point literal | String "1,25" is invalid |

The examples in the table compare **compile-time context** and **runtime String values**. Do not put quotation marks around numeric literals; in the API column, they represent a string.

## 6. Details that determine parser behavior

### 6.1. No locale-based comma rules

Double.parseDouble and Float.parseFloat do not use Locale to determine the decimal separator: standard strings require a dot. If data comes from a localized user interface (e.g., written as "1.234,5"), use NumberFormat or DecimalFormat with an explicit Locale and a policy to check the remainder of the string. NumberFormat.parse has different rules and result types from Double.parseDouble; some configurations may read only a valid prefix, so you must check the parse position when the entire string must be valid.

### 6.2. Leading/trailing whitespace vs. internal whitespace

Floating-point parse methods accept certain **leading and trailing** control/whitespace characters matching String.trim() behavior (characters with code points no greater than U+0020). For instance, "  1.5  " is valid. You cannot arbitrarily place spaces between digits, the decimal point, the exponent indicator, and the exponent: "1 e3" or "0x1.8 p1" is invalid. Do not assume that all Unicode whitespace characters are automatically stripped by the parser.

### 6.3. Precision, overflow, and non-finite values

- **double** has 64 bits under IEEE 754, roughly 15–17 significant decimal digits; **float** has 32 bits, roughly 6–9 significant digits.
- The parser recognizes the syntax and then converts to binary representation with appropriate rounding. A valid string does not guarantee exact representation of all decimal digits.
- Double.parseDouble("1e309") returns Infinity; Double.parseDouble("1e-4000") returns 0.0.
- Float.parseFloat accepts the same syntax family but has a narrower range and lower precision; the same string may yield a different rounded value than double.
- If business data only allows finite values, check using Double.isFinite/Float.isFinite after parsing. If you need to detect precision loss or out-of-range values, define the data rules before conversion.

Example utility method that accepts only finite double numbers:

~~~java
public static double parseFiniteDouble(String text) {
    double value = Double.parseDouble(text);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Value must be finite");
    }
    return value;
}
~~~

This is a **method snippet to place inside a class**, not a standalone Java program. The method accepts every syntax that Double.parseDouble accepts, but rejects NaN and Infinity results (including Infinity from overflow). It can still accept a very small number rounded to 0.0; add verification steps depending on the problem.

### 6.4. Exceptions and related methods

- **NumberFormatException**: the string does not match the supported floating-point syntax, e.g., "", "1e", "0x1", or "3,14".
- **NullPointerException**: passing null to Double.parseDouble/Float.parseFloat; handle null separately if input may be missing.
- **Double.valueOf(String)** and **Float.valueOf(String)** accept the same syntax and return the corresponding wrapper class; parseDouble/parseFloat return primitive types.
- **Double.toString** and **Float.toString** produce the decimal string representation of the stored value; **Double.toHexString** and **Float.toHexString** produce the hex representation of the corresponding value.

When a system needs exact decimal numbers for money or storing data with decimal rules, consider **BigDecimal(String)** with valid decimal strings. BigDecimal is not a drop-in replacement for Double.parseDouble: it does not accept hex floating-point syntax, NaN, or Infinity, and it has different precision semantics. Do not construct a BigDecimal from a double if the goal is to preserve the exact input decimal string; use the constructor that takes a String.

## 7. Common errors and diagnostics

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| "1,23" is rejected | Comma is not the parser's decimal separator | Use a dot or a Locale-aware parser |
| "1e" is rejected | Missing digits after e/E | Supply an exponent, e.g., "1e0" |
| "0x10" is rejected | Hex floating-point form lacks p/P and exponent | Use "0x10p0" if it is truly a hex float |
| "1_000.0" is rejected | Underscore is only literal syntax in Java code | Remove underscores before parsing if data allows |
| Parsing succeeds but yields Infinity | Value exceeds float/double range | Check isFinite and range constraints |
| Parsing succeeds but yields 0.0 | Nonzero value is too small for the target type | Check range limits and pick an appropriate representation |
| Displays trailing odd digits | Binary rounding of float/double | Do not compare floating-point values as if they were always exact |

You should not handle every NumberFormatException by silently substituting 0. This conflates syntactically invalid data with a valid value of 0. For external input, clearly specify whether strings may use hex format or NaN/Infinity; if only finite decimal forms are permitted, enforce that extra validation rule.

## 8. Self-check

1. Why does "1.2e3" have value 1200.0 whereas "0x1.2p3" has value 9.0? Because e uses powers of **10**, whereas p uses powers of **2**; the hex significand 0x1.2 equals 1 + 2/16 = 1.125, times 2³ equals 9.0.
2. What does Double.parseDouble("0x1p-1") return? **0.5**.
3. Does Double.parseDouble("0x1e2") succeed? **No**: it lacks the p/P indicator and binary exponent. The letter e sits within the hex digits.
4. Does Double.parseDouble("1e309") throw NumberFormatException? **No**: the syntax is valid, but the value exceeds double range, so the result is Infinity.
5. To accept decimal numbers with locale-specific separators and verify that the entire input was read, what should you do? Use **NumberFormat/DecimalFormat with an explicit Locale** and check the parse end position; do not assume Double.parseDouble handles locales automatically.

**Remember:** With Java's standard floating-point parsing APIs, e/E denotes a base-10 exponent; 0x...p/P... denotes a hex significand with a base-2 exponent; both are supported by Double.parseDouble and Float.parseFloat. Verify **valid syntax**, **valid value range**, and **required precision** together.