# The `L` Suffix and Default Type of Integer Literals in Java

## 1. What type does an integer literal have?

An **integer literal** is a way of writing an integer value directly in Java code, such as `10`, `1_000`, `0xFF`, or `42L`. In **Java 17+**, the type of an integer literal is determined immediately when the compiler parses the expression, **without waiting to see what type the variable on the left has**.

Key rules:

- **Without an `L` or `l` suffix**: an integer literal has type **`int`** (32 bits).
- **With an `L` or `l` suffix**: an integer literal has type **`long`** (64 bits).
- Prefer writing **uppercase `L`**: `1L`, `100_000L` instead of `1l`, because lowercase `l` is easily confused with the digit `1`.
- Choosing **`long` for the receiving variable** does not automatically turn an oversized literal without `L` into a `long` literal.

~~~java
int a = 42;              // Literal 42 has type int
long b = 42;             // Valid: int is widened to long
long c = 42L;            // Literal 42L has type long
long d = 3_000_000_000L; // Valid: has L, exceeds int range
// long bad = 3_000_000_000; // Compile error: int literal too large
~~~

In the line `long b = 42;`, **`42` itself is still an `int` literal**. Java then allows a *widening primitive conversion* from `int` to `long` during assignment. It is necessary to distinguish between the **type of the literal** and the **type of the variable**.

## 2. Value ranges of int and long

| Type | Size | Minimum value | Maximum value |
|---|---:|---:|---:|
| `int` | 32 bits | −2,147,483,648 | 2,147,483,647 |
| `long` | 64 bits | −9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

These values can be accessed via `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, and `Long.MAX_VALUE`.

~~~java
int largestInt = 2_147_483_647;
long firstBeyondInt = 2_147_483_648L;
long largestLong = 9_223_372_036_854_775_807L;
~~~

**Why does the second line need `L`?** Because `2_147_483_648` without a suffix is parsed as a decimal `int` literal, which exceeds the range of `int`, so the program is rejected at the compilation step. A target variable of type `long` cannot fix an already invalid literal.

**`L` does not make `long` infinite.** Writing a positive value larger than `Long.MAX_VALUE`, even with `L`, is also rejected by the compiler:

~~~java
// long tooBig = 9_223_372_036_854_775_808L; // Invalid
~~~

If you genuinely need integers whose magnitude exceeds `long`, use `java.math.BigInteger` and initialize it from a string; no integer literal suffix turns a literal into a `BigInteger`.

## 3. Negative numbers and the two special MIN_VALUE values

The `-` sign is a **unary operator** (*unary minus*), not a character belonging to a positive integer literal. For example, `-5L` is interpreted as the `-` operator applied to the literal `5L`.

Java makes a special case for the negative limits of `int` and `long` when the corresponding decimal literal appears directly under the unary minus operator:

~~~java
int minInt = -2147483648;                 // Valid
long minLong = -9223372036854775808L;    // Valid

// int invalid = 2147483648;            // Invalid, positive int literal too large
// long invalidLong = 9223372036854775808L; // Invalid, positive long literal too large
~~~

**Why is there an asymmetry?** A signed integer range in two's complement (*two's complement*) has one more negative value than positive values. Thanks to the rule for the `-` operator, Java allows writing `Integer.MIN_VALUE` and `Long.MIN_VALUE` directly.

Do not apply this exception to ordinary addition or a `long` target variable. For example, `long x = 2147483648;` is still an error. If you only need the minimum value, writing `Integer.MIN_VALUE` or `Long.MIN_VALUE` is usually easier to read.

## 4. Default types do not apply only to decimal

Java integer literals have multiple notations:

| Notation | Literal | Decimal value | Type when unsuffixed |
|---|---|---:|---|
| Decimal | `26` | 26 | `int` |
| Hexadecimal | `0x1A` or `0X1A` | 26 | `int` |
| Binary | `0b11010` or `0B11010` | 26 | `int` |
| Octal | `032` | 26 | `int` |
| Decimal with suffix | `26L` | 26 | `long` |
| Hexadecimal with suffix | `0x1AL` | 26 | `long` |

**Note on leading zero:** `010` is an **octal** literal with value **8**, not 10. Writing `08` is invalid because the digit 8 is not valid in octal.

### When non-decimal literals overflow into the sign part

For **hexadecimal, binary, or octal** literals, Java allows directly representing a bit pattern within the width of `int` or `long`. A bit pattern whose sign bit is 1 is interpreted as a negative number in two's complement representation.

~~~java
int intBits = 0xFFFF_FFFF;
long longBits = 0xFFFF_FFFFL;
long allLongBits = 0xFFFF_FFFF_FFFF_FFFFL;

System.out.println(intBits);      // -1
System.out.println(longBits);     // 4294967295
System.out.println(allLongBits);  // -1
~~~

**Subtle point:** with the same digits `0xFFFF_FFFF`, the unsuffixed literal is a 32-bit `int` (value `-1`), whereas `0xFFFF_FFFFL` is a 64-bit `long` (value `4_294_967_295`). Because the width changed, the highest bit of this `long` is not the sign bit.

Do not wrongly generalize that "hex literals are always positive" or "only decimals can be negative".

## 5. Underscores `_` aid readability without changing type

Java allows underscores **between digits** of many kinds of literals:

~~~java
int population = 1_000_000;
long distance = 12_345_678_901L;
int mask = 0b1010_1100;
long colorCode = 0xAB_CD_EFL;
~~~

`1_000_000` is still an `int`; `12_345_678_901L` is still a `long`. Underscores do not increase type limits or replace the `L` suffix.

Examples of **invalid** syntax:

~~~java
// int a = _123;          // This is the identifier _123, not the number 123
// int b = 123_;          // Cannot place _ at the end of a literal
// int c = 0x_FF;         // Cannot place _ immediately after the 0x prefix
// long d = 123_L;        // Cannot place _ immediately before the L suffix
~~~

To keep code readable, group digits meaningfully (`1_000_000L`, `0xFF_00_00_00L`) rather than placing `_` arbitrarily.

## 6. Expression type is determined before assignment

This is one of the most common Java mistakes when learning the `L` suffix.

~~~java
long wrong = 2_000_000_000 + 2_000_000_000;
long correct = 2_000_000_000L + 2_000_000_000;

System.out.println(wrong);   // -294967296
System.out.println(correct); // 4000000000
~~~

Because both operands on the first line are `int` literals, the expression `int + int` is evaluated in **32 bits** and overflows before being converted to `long`. Java still allows assigning the overflowed `int` result to `long`; it **does not recompute the addition in 64 bits**.

In the `correct` line, one operand has the `L` suffix, so the addition uses `long` due to **binary numeric promotion**. The result of 4 billion fits within the `long` range.

Two correct ways to write this calculation:

~~~java
long bySuffix = 2_000_000_000L + 2_000_000_000;
long byCast = (long) 2_000_000_000 + 2_000_000_000;
~~~

**Where the cast is placed determines the result:**

~~~java
long stillWrong = (long) (2_000_000_000 + 2_000_000_000);
// Overflowed int inside the parentheses before converting to long.
~~~

With multiplication, the same principle applies:

~~~java
long wrongProduct = 1_500_000_000 * 3;
long rightProduct = 1_500_000_000L * 3;
// rightProduct = 4500000000; wrongProduct already overflowed int.
~~~

When handling large counts or money, do not assume "declaring a `long` variable is enough." You must control the **type of the operation** starting from the operands.

## 7. Complete Java 17 example and run output

Create the file **`IntegerLiteralDemo.java`** with the following content:

~~~java
public final class IntegerLiteralDemo {
    private IntegerLiteralDemo() {}

    static String overload(int value) {
        return "int: " + value;
    }

    static String overload(long value) {
        return "long: " + value;
    }

    public static void main(String[] args) {
        int defaultInt = 42;
        long widened = 42;
        long explicitLong = 42L;
        long bigLong = 3_000_000_000L;

        int hexInt = 0xFFFF_FFFF;
        long hexLong = 0xFFFF_FFFFL;
        int octal = 017;
        int binary = 0b1010;

        long overflowBeforeWiden = 2_000_000_000 + 2_000_000_000;
        long promoteFirst = 2_000_000_000L + 2_000_000_000;
        long castFirst = (long) 2_000_000_000 + 2_000_000_000;

        int minInt = -2147483648;
        long minLong = -9223372036854775808L;

        byte small = 127; // int constant is validly narrowed
        var inferredInt = 7;
        var inferredLong = 7L;

        System.out.println("int default: " + defaultInt);
        System.out.println("widened into long: " + widened);
        System.out.println("explicit long: " + explicitLong);
        System.out.println("big long: " + bigLong);
        System.out.println("hex int: " + hexInt);
        System.out.println("hex long: " + hexLong);
        System.out.println("octal: " + octal);
        System.out.println("binary: " + binary);
        System.out.println("overflow before widen: " + overflowBeforeWiden);
        System.out.println("long before add: " + promoteFirst);
        System.out.println("cast before add: " + castFirst);
        System.out.println("minimum int: " + minInt);
        System.out.println("minimum long: " + minLong);
        System.out.println("byte from int literal: " + small);
        System.out.println(overload(inferredInt));
        System.out.println(overload(inferredLong));
    }
}
~~~

Open a terminal in the directory containing the file and use **JDK 17 or newer**.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 IntegerLiteralDemo.java
java -cp . IntegerLiteralDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\IntegerLiteralDemo.java
java -cp . IntegerLiteralDemo
~~~

**Expected output:**

~~~text
int default: 42
widened into long: 42
explicit long: 42
big long: 3000000000
hex int: -1
hex long: 4294967295
octal: 15
binary: 10
overflow before widen: -294967296
long before add: 4000000000
cast before add: 4000000000
minimum int: -2147483648
minimum long: -9223372036854775808
byte from int literal: 127
int: 7
long: 7
~~~

Three points you should verify yourself:

1. `42` and `42L` can print **the same value**, yet carry **different types**.
2. `0xFFFF_FFFF` differs from `0xFFFF_FFFFL` due to the bit width of `int`/`long`.
3. The two overloads `overload(int)` and `overload(long)` show that `var inferredInt = 7` has type `int`, while `var inferredLong = 7L` has type `long`.

The example is designed to be standalone; the output above is the **expected result to verify after running it yourself**, not a claim that the program has already been executed on your machine.

## 8. Why can byte or short accept an unsuffixed literal?

Although an unsuffixed integer literal has type `int`, the compiler permits a **special narrowing conversion for constant expressions** in certain assignment/initialization contexts, provided the value fits within the target type's range:

~~~java
byte a = 127;      // Valid even though 127 is an int literal
short b = 30_000;  // Valid even though 30000 is an int literal
char c = 65;       // Valid: character 'A'

// byte invalid = 128;       // Error: outside byte range
// short invalid2 = 40_000;  // Error: outside short range
// byte invalid3 = 127L;     // Error: long literal does not narrow automatically like this
~~~

This **does not change the default type of the literal**: `127` is still an `int`. Assignment conversion rules explain why the first lines are valid.

With variables or non-constant expressions, the compiler does not automatically allow narrowing:

~~~java
int source = 127;
// byte target = source; // Error because source is an int variable
byte target = (byte) source; // Explicit cast; only use after checking range
~~~

Do not use a cast to "hide" an out-of-range value: casting an overly large integer down to a smaller type can truncate bits and corrupt data.

## 9. Common mistakes and how to fix them

| Situation | Why is it wrong or surprising? | How to fix |
|---|---|---|
| `long n = 3_000_000_000;` | Decimal int literal is too large even though target variable is long | `3_000_000_000L` |
| `int n = 3_000_000_000L;` | Long literal does not narrow automatically to int | Choose `long` if the data is genuinely large |
| `long sum = 2_000_000_000 + 2_000_000_000;` | int addition overflows before assignment | Use `L` on one operand, or cast before the operation |
| `long n = 9223372036854775808L;` | Exceeds `Long.MAX_VALUE` | Choose a valid data range or `BigInteger` |
| `int n = 08;` | Leading `0` starts an octal literal | Write `8` for decimal |
| `long n = 0xFFFF_FFFF;` | int literal has sign bit 1, becoming `-1` before widening | `0xFFFF_FFFFL` if you want 4,294,967,295 |
| `int n = 123_L;` | `_` cannot appear immediately before the suffix | `123L` or `1_23L` |
| Using `1l` | Valid, but `l` is easily misread as `1` | Use `1L` |
| `var value = 1;` while expecting long | `var` infers int from the initializer | `var value = 1L;` |

**Distinguish the two stages:** a literal outside its valid range usually causes a **compile-time error**; however, arithmetic operations on valid `int` literals can still **overflow during evaluation** without automatically throwing an exception. For addition or multiplication where overflow must be detected, look at `Math.addExact` and `Math.multiplyExact` depending on data requirements.

## 10. Practice exercises with answers

### Exercise A — identify type and value

Classify `100`, `100L`, `0b1010`, `0xFFL`, `010`.

**Answer:** `100` is int 100; `100L` is long 100; `0b1010` is int 10; `0xFFL` is long 255; `010` is int 8 (octal).

### Exercise B — error despite long target

~~~java
long population = 4_000_000_000;
~~~

**Answer:** compile error because the literal `4_000_000_000` has no suffix and exceeds the `int` range. Fix it to `long population = 4_000_000_000L;`.

### Exercise C — predict multiplication

~~~java
long x = 1_500_000_000 * 3;
long y = 1_500_000_000L * 3;
~~~

**Answer:** `x = 205032704` (the int multiplication 4,500,000,000 overflows modulo 2³², then widens to long); `y = 4500000000`. If the calculation requires the exact 4.5 billion value, you must perform the multiplication using `long` first.

### Exercise D — distinguish the same hex pattern

~~~java
int a = 0xFFFF_FFFF;
long b = 0xFFFF_FFFFL;
~~~

**Answer:** `a == -1`, `b == 4294967295L`. Same hex digits, but different **bit width and sign bit** of the literal type.

### Exercise E — fix three invalid lines

~~~java
// long a = 2147483648;
// int b = 2147483648L;
// long c = 9223372036854775808L;
~~~

**Suggested answers:** for `a`, add `L`. For `b`, change the variable to `long` if that value is needed. For `c`, the number exceeds the `long` range, so you must change the data requirement, use `BigInteger`, or handle out-of-range input — **there is no integer suffix larger than `L` in Java**.

## 11. Checklist and conclusion

- [ ] Understand that an integer literal **without `L` has type `int`**, and with `L` has type `long`.
- [ ] Do not confuse the literal's type with the variable's type on the left-hand side of an assignment.
- [ ] Remember the limits of 32-bit `int` and 64-bit `long`.
- [ ] Know how to write `Integer.MIN_VALUE` and `Long.MIN_VALUE` using the unary minus operator with the corresponding literal.
- [ ] Recognize decimal, hex, binary, and octal notations and the effect of the sign bit.
- [ ] Use uppercase `L`; use `_` between digits strictly for readability.
- [ ] Know that `int` addition/multiplication can overflow **before assignment to long**.
- [ ] Understand that `var x = 1` infers int, while `var x = 1L` infers long.
- [ ] Do not confuse the constant narrowing rule `byte b = 127;` with a byte literal type.
- [ ] Compile and run `IntegerLiteralDemo.java`, verifying the entire output.

**Conclusion:** In Java, the **`L` suffix determines that an integer literal has type `long` instead of `int`**. The type is decided **before** assignment or arithmetic operations are applied. Placing `L` in the right spot not only lets you represent numbers beyond `int`, but also ensures expressions requiring 64-bit width are computed as `long` rather than overflowing `int` before conversion.
