# Distinguishing Digit Characters (`char`) from Numeric Values in Java

In Java, **a character that looks like a digit** and **the numeric value of that digit** are two different things. This is an important point when processing user input, converting strings to numbers, performing arithmetic, and validating characters.

## 1. How Do `'7'`, `7`, and `"7"` Differ?

| Syntax | Java Type | Meaning |
| --- | --- | --- |
| `'7'` | `char` | A digit character, with UTF-16 code unit value **55** (U+0037) |
| `7` | `int` | An integer with value **7**, used directly in arithmetic |
| `"7"` | `String` | A string containing one character `7`, which must be converted before use as a number |
| `'0'` | `char` | The character `0`, with UTF-16 code unit equal to **48** (U+0030) |

`char` is a primitive type representing **a 16-bit unsigned UTF-16 code unit** (0–65,535). Because of this, Java allows `char` in arithmetic expressions, but the number obtained from direct conversion is the **character's code**, not automatically the digit a human sees. For ASCII characters, `'0'` through `'9'` have decimal codes 48 through 57 respectively.

For example, both declarations below are valid but have different meanings:

```java
char character = '7'; // Character '7': UTF-16 code is 55.
int number = 7;       // Actual integer value is 7.

int codeUnit = character; // Widening conversion: codeUnit == 55.
int digit = character - '0'; // Difference of two character codes: 55 - 48 == 7.
```

The snippet above is illustrative code meant to be placed inside a Java method. **`(int) character` or `int codeUnit = character` does not parse the character into the number 7.** Subtracting `'0'` is what performs the mapping from an ASCII character to its digit value.

## 2. Why Does Subtracting `'0'` Work?

ASCII digits are arranged **consecutively** in the character table:

| Character | Decimal Code | Expression | Numeric Value |
| --- | ---: | --- | ---: |
| `'0'` | 48 | `'0' - '0'` | 0 |
| `'1'` | 49 | `'1' - '0'` | 1 |
| `'7'` | 55 | `'7' - '0'` | 7 |
| `'9'` | 57 | `'9' - '0'` | 9 |

In Java, when using arithmetic operators like `+` or `-`, `char` operands undergo **numeric promotion to `int`**. Therefore, `'7' - '0'` has result type `int` and value 7.

**Only use this subtraction when you know the character is in the ASCII range `'0'..'9'`.** For letters, punctuation, or digits from other scripts, subtracting character codes is not a general digit conversion method.

```java
static int asciiDigit(char c) {
    if (c < '0' || c > '9') {
        throw new IllegalArgumentException("Not an ASCII digit: " + c);
    }
    return c - '0';
}
```

This function is a method meant to be placed inside a Java class. Passing `'7'` yields `7`. Passing `'A'` or the Arabic-Indic digit `'٧'` intentionally throws an error because the character is not in the allowed ASCII digit set.

## 3. `char` in Arithmetic and When Printing

Distinguish between **printing a character**, **printing its code value**, and **performing arithmetic**:

```java
char c = '7';

System.out.println(c);              // 7 (printed as a character)
System.out.println((int) c);        // 55 (UTF-16 code value)
System.out.println(c + 1);          // 56 (integer addition)
System.out.println((char) (c + 1)); // 8 (cast result 56 back to character)
System.out.println(c - '0');        // 7 (digit value)
System.out.println("7" + 1);        // 71 (string concatenation)
```

These are illustrative statements meant to be placed in `main`. With `println(c)`, Java selects the overload accepting `char` and displays the character glyph. With `println(c + 1)`, the expression has already been evaluated as `int`, so it prints `56`. When a `String` is present with the `+` operator, Java can perform **string concatenation**: `"7" + 1` creates the string `"71"`, not the number 8.

Two easily confused situations:

- `'7' + '2'` adds two character codes: `55 + 50 = 105`, **not** the number 9 or 72.
- `(char) 7` creates the control character U+0007, **not** the character `'7'`. Conversely, `(char) ('0' + 7)` creates `'7'` because it lies within the ASCII digit range.

## 4. Standalone Runnable Java 17+ Program

Save the following content into **`DigitVsCharDemo.java`**:

```java
public class DigitVsCharDemo {
    static int asciiDigit(char c) {
        if (c < '0' || c > '9') {
            throw new IllegalArgumentException("Not an ASCII digit: " + c);
        }
        return c - '0';
    }

    public static void main(String[] args) {
        char symbol = '7';
        int rawCodeUnit = symbol;
        int digit = asciiDigit(symbol);

        System.out.println("char=" + symbol);
        System.out.println("UTF-16 code unit=" + rawCodeUnit);
        System.out.println("decimal digit=" + digit);
        System.out.println("add 1=" + (symbol + 1));
        System.out.println("next char=" + (char) (symbol + 1));
        System.out.println("text concat=" + ("7" + 1));
        System.out.println("Unicode decimal digit=" + Character.digit('\u0667', 10));
        System.out.println("hex A=" + Character.digit('A', 16));
        System.out.println("digit 7 -> char=" + Character.forDigit(7, 10));
        System.out.println("two digits=" + (asciiDigit('4') * 10 + asciiDigit('2')));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 DigitVsCharDemo.java
java DigitVsCharDemo
```

Expected stdout output:

```text
char=7
UTF-16 code unit=55
decimal digit=7
add 1=56
next char=8
text concat=71
Unicode decimal digit=7
hex A=10
digit 7 -> char=7
two digits=42
```

The last line shows how to combine the **numeric values** of two characters `'4'` and `'2'` into the number `42`: multiply the tens digit by 10 and add the units digit. This is arithmetic on `int`, not character concatenation.

## 5. When Data Contains Unicode Digits

Not every character rendered as the digit `7` has the same code as `'7'`. For example:

- `'7'`: ASCII digit, code U+0037.
- `'٧'`: Arabic-Indic digit seven, code U+0667.
- `'７'`: fullwidth digit seven, code U+FF17.

All three can represent the **decimal digit 7**, yet `c - '0'` only works for the ASCII case. When processing Unicode digits, use the `Character` API, which has well-defined rules:

```java
char ascii = '7';
char arabicIndic = '٧';
char letter = 'A';

System.out.println(Character.isDigit(ascii));            // true
System.out.println(Character.isDigit(arabicIndic));      // true
System.out.println(Character.digit(arabicIndic, 10));    // 7
System.out.println(Character.digit(letter, 10));         // -1
System.out.println(Character.digit(letter, 16));         // 10
```

This snippet is placed in `main`. `Character.digit(c, radix)` returns the digit value in the specified **radix**, or `-1` if invalid. For example, the letter `A` has value 10 in base 16, but is not a valid digit in base 10. Supported radices range from `Character.MIN_RADIX` (2) to `Character.MAX_RADIX` (36).

Combine checking and conversion when accepting strictly **one decimal digit character**:

```java
static int decimalDigit(char c) {
    int value = Character.digit(c, 10);
    if (!Character.isDigit(c) || value < 0) {
        throw new IllegalArgumentException("Not a decimal digit");
    }
    return value;
}
```

This is a method placed inside a Java class. `Character.isDigit(c)` checks the Unicode decimal digit property; `Character.digit(c, 10)` extracts the value needed for arithmetic. `c - '0'` only checks code relationships, so it cannot replace this API pair when input allows multiple scripts.

**Limitation of `char`:** Some Unicode characters lie outside the Basic Multilingual Plane (BMP) and require **two UTF-16 code units** (a surrogate pair). `charAt(index)` only reads one code unit; in that case use `String.codePointAt(index)` and the overloads `Character.digit(int codePoint, int radix)` / `Character.isDigit(int codePoint)`.

```java
String s = "𝟠"; // MATHEMATICAL DOUBLE-STRUCK DIGIT EIGHT (U+1D7E0).
System.out.println(s.length());                       // 2: two UTF-16 units.
System.out.println(Character.digit(s.charAt(0), 10)); // -1: only one surrogate.
System.out.println(Character.digit(s.codePointAt(0), 10)); // 8.
```

This example is placed in `main`; iterating an entire string by code point should advance the index by `Character.charCount(codePoint)` or use `String.codePoints()`, rather than assuming each `char` is a complete Unicode character.

## 6. Converting Back: Number to Digit Character

When you have a **numeric value** from 0 to 9 and need an ASCII character:

```java
int n = 7;
char c1 = (char) ('0' + n);             // '7', provided 0 <= n <= 9.
char c2 = Character.forDigit(n, 10);    // '7'.
String text = Integer.toString(n);     // "7" (String).
```

`Character.forDigit(digit, radix)` also works for digits in other bases (for example, `Character.forDigit(10, 16)` returns `'a'`). The API returns the NUL character `'\0'` when the digit/radix arguments are invalid, so validate input conditions to avoid unexpected results. Do not use `(char) ('0' + n)` for `n = 12`: the result is `'<'`, **not** the string `"12"`. For multi-digit numbers, use `Integer.toString(n)` or `String.valueOf(n)`.

## 7. A Single Digit Character vs. a Multi-Digit String

- For **one ASCII character** `'7'`, after range checking, use `c - '0'`.
- For **one Unicode digit code point**, use `Character.digit(codePoint, 10)` and handle the `-1` case.
- For **a string representing an integer**, such as `"2048"`, use `Integer.parseInt(text)` or an appropriate numeric type. A string can contain a sign and multiple digits; a single `char` cannot represent that entire integer.

Example:

```java
String input = "2048";
int parsed = Integer.parseInt(input);
System.out.println(parsed + 2); // 2050
```

Placed in `main`. `Integer.parseInt` throws `NumberFormatException` when the string does not have valid integer syntax or the value exceeds the `int` range. A `null` input cannot be converted either. If you need data larger than the `int` limit, consider `Long.parseLong` or `BigInteger`.

Special note on `Character.getNumericValue`: this API covers a **wider range of Unicode numeric values than decimal digits**, for example returning 10 for `'A'` or the value of a Roman numeral character. Do not use `getNumericValue` alone to decide whether a character is a decimal digit; choose `Character.isDigit` / `Character.digit(..., 10)` according to input requirements.

## 8. Common Mistakes and How to Avoid Them

| Mistake | Problem | Correct Approach |
| --- | --- | --- |
| `int n = '7';` expecting `n == 7` | `n` is actually 55 | Validate and use `'7' - '0'` or `Character.digit('7', 10)` |
| `char c = (char) 7;` to get `'7'` | 7 is the code of a control character, not the digit character | `(char) ('0' + 7)` after range checking |
| `'7' + '2'` to add 7 and 2 | Java adds **character codes**, yielding 105 | `('7' - '0') + ('2' - '0')` yields 9 |
| `c - '0'` on arbitrary Unicode characters | Only valid for ASCII `'0'..'9'` | Use `Character.digit` when Unicode is allowed |
| `Character.getNumericValue(c) >= 0` means decimal digit | Some letters/numeric symbols also have a numeric value | Use `Character.isDigit(c)` and radix 10 |
| `s.charAt(0)` to read any Unicode digit | Characters outside BMP may consist of two `char`s | Use code points and the `int` overload |
| Using `"7" + 1` to compute `8` | String concatenation produces `"71"` | Convert to a number before adding |

**Self-Check:**

1. What is `(int) '5'`? **53**, because that is the character code of `'5'`.
2. What is `'5' - '0'`? **5**, because it is normalized relative to the ASCII digit code `'0'`.
3. Does `'9' + 1` print as the character `':'`? **No**, the expression has type `int` and value **58**; it must be cast to `char` to become `':'`.
4. How do you read the digit `'٧'` from Unicode input? **`Character.digit('٧', 10)`** returns `7`.
5. How do you convert the integer `27` to text? **`Integer.toString(27)`** returns the string `"27"`; both digits cannot fit into a single `char`.

Key point to remember when studying **integer types**: `char` can participate in arithmetic operations because it stores a 16-bit code unit, but its **digit meaning** is a separate interpretation step. For ASCII, subtracting `'0'` is the simple approach; for Unicode, use `Character`; for multi-digit strings, use integer parsing APIs.
