# Decimal, Binary, Octal, and Hexadecimal Integer Literals in Java

> **Java core — language-basics / Literal**  
> **Environment:** JDK 17 or higher, no external libraries required.  
> **Objective:** Write and read integer literals accurately in bases 10, 2, 8, and 16; understand prefixes, the `L` suffix, the underscore `_`, `int`/`long` limits, and how Java interprets bits as signed numbers. Compile and run programs yourself, and distinguish literals in source code from numeric strings parsed at runtime.

## 1. What is an integer literal?

An **integer literal** is a way of writing an integer value directly **in Java source code**. For example:

~~~java
int students = 42;
long population = 8_000_000_000L;
~~~

`42` and `8_000_000_000L` are literals; `students` and `population` are variable names; `int` and `long` are data type keywords.

The same integer value can be written in multiple bases. Java 17 supports four common integer numeral systems:

| Base | Literal notation | Valid digits | Example representing 42 |
| --- | --- | --- | --- |
| **Decimal (10)** | No prefix required | `0–9` | `42` |
| **Binary (2)** | `0b` or `0B` | `0`, `1` | `0b101010` |
| **Octal (8)** | Starts with `0` followed by octal digits | `0–7` | `052` |
| **Hexadecimal (16)** | `0x` or `0X` | `0–9`, `a–f`, `A–F` | `0x2A` |

In the example above, all four literals have the value **42** when assigned to an `int`. The base name describes **how the constant is written in source code**, not four different variable types.

**Be careful with leading zeros:** `010` has the value **8**, not 10. Meanwhile, `09` is an error because `9` is not an octal digit. When you want to represent decimal 10, write `10` — do not write `010`.

## 2. Base conversion rules

The value of a number in base `b` is the sum of its digits multiplied by powers of `b` corresponding to their positions:

\[
(d_n \ldots d_1d_0)_b=\sum_{i=0}^{n} d_i b^i
\]

For example, with the same number 42:

| Literal | Calculation | Decimal result |
| --- | --- | ---: |
| `42` | `4 × 10 + 2` | 42 |
| `0b101010` | `1×32 + 0×16 + 1×8 + 0×4 + 1×2 + 0×1` | 42 |
| `052` | `5×8 + 2` | 42 |
| `0x2A` | `2×16 + A(10)` | 42 |

From `A` to `F` in base 16 represent the values 10 to 15, respectively. In base 2, `1010` is ten; in base 8, `52` is forty-two; do not read all digit strings as decimal numbers.

**When choosing a notation:** base 10 is easy to read for quantities; base 2 is useful for bit flags; base 8 occasionally appears in some permission/legacy compatibility contexts; base 16 makes bit groups easier to view concisely, such as the mask `0xFF`. Choose a notation that clearly expresses intent rather than simply because multiple bases are available.

## 3. Runnable Java 17+ program: IntegerLiteralsDemo.java

Create a file named **IntegerLiteralsDemo.java** with the following content:

~~~java
public class IntegerLiteralsDemo {
    public static void main(String[] args) {
        int decimal = 42;
        int binary = 0b101010;
        int octal = 052;
        int hexadecimal = 0x2A;

        System.out.println("values=" + decimal + "," + binary
                + "," + octal + "," + hexadecimal);
        System.out.println("equal=" + (decimal == binary
                && binary == octal && octal == hexadecimal));

        System.out.println("leadingZero010=" + 010);
        System.out.println("grouped=" + 1_000_000);

        System.out.println("binaryOf42=" + Integer.toBinaryString(decimal));
        System.out.println("octalOf42=" + Integer.toOctalString(decimal));
        System.out.println("hexOf42=" + Integer.toHexString(decimal));

        int allBits = 0xFFFF_FFFF;
        long positiveLong = 0xFFFF_FFFFL;
        System.out.println("intBits=" + allBits);
        System.out.println("longBits=" + positiveLong);
        System.out.println("unsignedIntBits=" + Integer.toUnsignedLong(allBits));

        System.out.println("parseHex=" + Integer.parseInt("2A", 16));
    }
}
~~~

**Compile and run** in Bash, PowerShell, or Command Prompt in the directory containing the file:

~~~bash
javac -encoding UTF-8 IntegerLiteralsDemo.java
java IntegerLiteralsDemo
~~~

If compilation succeeds, `javac` usually prints nothing. The `java` command produces **these exact lines**:

~~~text
values=42,42,42,42
equal=true
leadingZero010=8
grouped=1000000
binaryOf42=101010
octalOf42=52
hexOf42=2a
intBits=-1
longBits=4294967295
unsignedIntBits=4294967295
parseHex=42
~~~

**Explanation of three key results:**

1. `42`, `0b101010`, `052`, and `0x2A` are written differently but have the same value; `==` between `int` values compares numerically.
2. `Integer.toBinaryString`, `toOctalString`, and `toHexString` return a **character string** representing the number in the chosen base; `toHexString` uses lowercase for `a–f`. They **do not change the type of the `decimal` variable**.
3. `0xFFFF_FFFF` has a 32-bit pattern of all 1s; when represented as a signed `int`, it is **-1**. Adding the `L` suffix creates a `long` literal with the same hex digits, so the positive value is **4,294,967,295**. `Integer.toUnsignedLong(allBits)` also gives an unsigned view of those 32 bits.

### Tracing the path from source to output

~~~mermaid
flowchart LR
    A["Literals 0b101010, 052, 0x2A"] --> B["Compiler interprets int value: 42"]
    B --> C["int variable in program"]
    C --> D["println: displays decimal 42"]
    C --> E["toBinaryString: string 101010"]
    C --> F["toHexString: string 2a"]
~~~

When printing via string concatenation, `println` does not automatically remember which base a value was originally written in within the source code. To display in another base, use the corresponding method that converts the **value to a string**.

## 4. Integer type when written by base

The base determines **how digits are written**, while the suffix determines the **literal's type**: without `L` it is normally `int` (32 bits), and with `L` it is `long` (64 bits). For example, `42`, `0b101010`, and `0x2A` are all `int` with the value 42; `0x2AL` is a `long` with the same value.

~~~java
int count = 42;
long sameCount = 0x2AL;
long veryLarge = 4_000_000_000L;
// long invalid = 4_000_000_000; // Decimal int literal out of range.
~~~

Do not infer a literal's type from the target variable: `long x = 42;` still starts with an `int` literal and performs a widening conversion to `long`. For bit patterns with the sign bit set, how `int`/`long` are interpreted is illustrated directly in Section 7; number limits, the `L` suffix, arithmetic overflow, and casting are analyzed separately in the lesson **The L Suffix and Default Type of Integer Literals**.

## 5. Grouping digits in each base with `_`

You can write `1_000_000`, `0b1010_0101`, `07_52`, or `0xCA_FE` for readability. `_` does not change the value, base, or type of the literal. Do not place it next to a prefix or at the end of the numeric part: `0b_1010`, `0x_FF`, `123_L`, and `100_` are all invalid.

Detailed rules, consecutive `_` characters, decimal points, and exponents belong to the lesson **Underscores in Numeric Literals and Invalid Positions**.

## 6. The minus sign and minimum values

The `-` sign before a number is a **unary operator**, not part of the literal token itself: `-5` is parsed as the `-` operator and the literal `5`. The two decimal forms `-2147483648` and `-9223372036854775808L` are special cases that Java allows when the literal serves as the operand of the minus sign; removing the minus sign from those values leaves positive literals that exceed the `int`/`long` limits.

Section 7 continues by explaining why **bit patterns** in binary/octal/hex literals can represent negative numbers without writing a minus sign. The lesson on the `L` suffix dives deeper into range rules and integer expressions.

## 7. How bit patterns are interpreted for binary/octal/hex literals

For non-decimal literals, Java allows representing a **bit pattern** occupying all 32 bits of an `int` or 64 bits of a `long`; because Java `int`/`long` are signed types using two's complement representation, a pattern with the sign bit equal to 1 is interpreted as a negative number.

| Java source pattern | Literal type | Value if printed as signed decimal |
| --- | --- | ---: |
| `0x7FFF_FFFF` | `int` | 2,147,483,647 |
| `0x8000_0000` | `int` | -2,147,483,648 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0xFFFF_FFFFL` | `long` | 4,294,967,295 |
| `0x8000_0000_0000_0000L` | `long` | -9,223,372,036,854,775,808 |

For example, `0b1111_1111` only has 8 one-bits but is placed into a 32-bit `int` type, so its value is **255**, not `-1`; to represent `-1` with 32 one-bits, you must provide all 32 one-bits or write `0xFFFF_FFFF`.

**There is no `unsigned int` primitive type in Java 17.** When you need to interpret 32 bits as an unsigned number, use APIs such as `Integer.toUnsignedLong`, `Integer.compareUnsigned`, or appropriate shift/bitmask operations. The goal is to interpret the bits, not to create a new primitive.

## 8. Literals in source code vs. parsing strings at runtime

These are two different things:

- Writing `int color = 0xFF;` in source code: the **compiler** recognizes the `0x` prefix and produces the numeric value 255.
- Calling `Integer.parseInt("FF", 16)` at runtime: the Java API reads the string `"FF"` using **radix 16** and returns `255`.
- Calling `Integer.decode("0xFF")`: the API accepts several prefix styles and returns an `Integer` with value `255`.
- Calling `Integer.parseInt("0xFF", 16)`: **throws `NumberFormatException`**, because `parseInt` with radix 16 does not accept the `0x` prefix in the string.

Example:

~~~java
int fromLiteral = 0b1010;                // 10, interpreted by the compiler.
int fromString = Integer.parseInt("1010", 2); // 10, parsed by the API.
int fromHexString = Integer.parseInt("2A", 16); // 42.
int fromPrefix = Integer.decode("0x2A"); // 42.
~~~

The radix passed to `parseInt` can be from **2 to 36**. This is a string-parsing API, not an extension of the bases you can write directly as integer literals in Java source code.

Do not insert `0b`, `0x`, or underscores into parsed strings expecting them to behave like compiler literal syntax. For user data, you must explicitly normalize/validate according to the input contract.

## 9. Common mistakes

| Code / symptom | Issue | Fix |
| --- | --- | --- |
| `int n = 09;` | A number with a leading `0` is interpreted as octal; digit 9 is invalid | If you want decimal nine, write `9` |
| `int n = 010;` produces 8 | Not a compile error: `010` is octal | Write `10` if you want ten |
| `int x = 0b102;` | `2` is not a base-2 digit | Use only `0`, `1` |
| `int x = 0x1G;` | `G` is not a hex digit | Use `0–9`, `A–F` |
| `int x = 0x_FF;` | Underscore in an invalid position | Write `0xFF` or `0xF_F` |
| `long n = 8_000_000_000;` | Default `int` literal is too large | Use `8_000_000_000L` |
| `int n = 0x1_0000_0000;` | Un-suffixed literal exceeds 32 bits | Use `long n = 0x1_0000_0000L;` |
| `int n = 0xFFFF_FFFF;` prints -1 | Not an error: 32-bit all-ones pattern has a negative sign | Use `Integer.toUnsignedLong(n)` if an unsigned view is needed |
| `parseInt("1_000")` fails | Runtime strings do not follow numeric literal syntax | Pass a pure digit string or handle formatting explicitly |

**Important distinction:** errors caused by **literal syntax** are detected by the compiler at compile time; `NumberFormatException` from `parseInt` only occurs when **the program is running**.

## 10. Practice exercises

**Exercise 1 — Same value.** Write the decimal value 255 as binary, octal, and hex literals. Use `println` to prove all three produce `255`.

*Hint:* `0b1111_1111`, `0377`, `0xFF`.

**Exercise 2 — Base recognition.** Predict the values of `10`, `010`, `0b10`, and `0x10`.

*Answer:* **10**, **8**, **2**, **16**, respectively.

**Exercise 3 — Type limits.** Why is `long n = 8_000_000_000;` invalid while `long n = 8_000_000_000L;` is valid? Try adding the `L` suffix to binary and hex literals.

**Exercise 4 — Sign bit.** Predict the output of `System.out.println(0xFFFF_FFFF);` and `System.out.println(0xFFFF_FFFFL);`. Explain why the same hex digits produce two different numbers.

**Exercise 5 — Underscore `_`.** Classify `1_000`, `1__000`, `0b1010_0001`, `0x_FF`, `123_L`, and `10_` as valid/invalid. Do not jump to the conclusion that two consecutive underscores are always wrong.

**Exercise 6 — Literal vs. string.** In `IntegerLiteralsDemo`, compare `0x2A` with `Integer.parseInt("2A", 16)`. What happens when you write `Integer.parseInt("0x2A", 16)`? Try the `Integer.decode` method.

## 11. End-of-lesson checklist

- [ ] Remember **no prefix → base 10**, `0b`/`0B` → base 2, leading `0` on multi-digit octal numbers → base 8, `0x`/`0X` → base 16.
- [ ] Know that `09` is invalid and `010` has the value 8.
- [ ] Know that the `L` suffix determines a `long` literal; a `long` target variable does not automatically fix an oversized `int` literal.
- [ ] Place `_` **between digits**, not right after a prefix or next to a suffix.
- [ ] Understand that the minus sign is a **unary operator** and know the two minimum negative limit cases.
- [ ] Distinguish a **signed bit pattern** from a 32-bit unsigned view via `Integer.toUnsignedLong`.
- [ ] Know that a literal in source code differs from `parseInt` decoding a string at runtime.

**Summary:** The four bases are **four ways of writing integer values** in a Java program. Reading prefixes, suffixes, grouping underscores, and type limits accurately helps avoid ambiguous bugs like `010`, oversized literals, and hex bit patterns yielding negative values.
