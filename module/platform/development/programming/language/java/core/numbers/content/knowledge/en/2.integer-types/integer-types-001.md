# `byte`, `short`, `int`, and `long` in Java

Java has four signed primitive integer types: **`byte` (8-bit), `short` (16-bit), `int` (32-bit), `long` (64-bit)**. They store integers accurately **within each type's value range**, but can overflow when an operation's result exceeds the range. To use them correctly, you need to understand their bounds, literals, type conversions, promotion rules during calculations, and integer division operations.

## 1. Width, Range, and Nature of the Four Types

| Type | Width | Minimum | Maximum | Wrapper |
| --- | ---: | ---: | ---: | --- |
| `byte` | 8-bit | -128 | 127 | `Byte` |
| `short` | 16-bit | -32,768 | 32,767 | `Short` |
| `int` | 32-bit | -2,147,483,648 | 2,147,483,647 | `Integer` |
| `long` | 64-bit | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 | `Long` |

A signed integer type of `n` bits has a range from `-2^(n-1)` to `2^(n-1)-1`. For example, `byte` has a range from `-2^7 = -128` to `2^7-1 = 127`. The negative side has one extra value because the non-negative range must also include 0.

Java specifies that these four types use **two's complement** representation for signed integer operations. The value `-1` has all bits equal to 1 across the width being used. The bit width of each type **does not change** between 32-bit and 64-bit machines. Among the signed integer types, `int` is usually the default choice for counters and general arithmetic; `long` is used when a larger range is needed.

Wrapper constants help look up bounds safely: `Byte.MIN_VALUE`, `Short.MAX_VALUE`, `Integer.MIN_VALUE`, `Long.MAX_VALUE`. Do not confuse the value width with the actual size of an object in memory: object headers, alignment, boxing, and collection structures have additional overhead. With `int[]` or `byte[]`, the elements are primitives, but the array itself still has JVM management overhead.

You should distinguish `char`: although it is 16-bit, it represents an **unsigned** UTF-16 code unit and is not one of the four signed integer types discussed here. `boolean` is not an integer type either.

## 2. Variable Declaration, Default Values, and Literals

```java
byte level = 25;
short year = 2026;
int users = 100_000_000;
long count = 3_000_000_000L;
long smallCount = 100;  // int literal 100 is widened accurately to long
```

An unsuffixed **decimal** integer literal is normally `int` if it fits within the `int` range. If the number is larger than `Integer.MAX_VALUE` and needs the `long` type, append an uppercase `L`:

```java
long ok = 5_000_000_000L;
// long wrong = 5_000_000_000; // Error: decimal literal exceeds int range
```

Use uppercase `L` instead of lowercase `l` to avoid confusing the letter `l` with the digit `1`. Underscores `_` between digits improve readability without changing the value; they cannot be placed arbitrarily at the start/end of a literal or immediately before a suffix.

Java also has binary literals `0b1010`, octal literals `012`, and hexadecimal literals `0x0A`; all three examples have the value **10**. Note `012` is octal: a leading 0 on an integer literal has syntactic meaning, not normal decimal notation.

Primitive fields and primitive array elements are initialized to **0** by default (`long` has value 0L). Local variables in a method **are not automatically initialized to 0 so they can be read right away**; Java requires them to be definitely assigned before use.

For `final` constants, the compiler can apply compile-time constant assignment rules. For example:

```java
byte first = 127;          // Valid: int constant 127 is within byte range
final int LIMIT = 100;
byte second = LIMIT;       // Valid: constant expression within byte range
int variable = 100;
// byte third = variable; // Invalid: ordinary int does not automatically narrow to byte
// byte fourth = 128;    // Invalid: outside byte range
```

This is a **conditional constant assignment rule**, not that every `int → byte` conversion is automatic.

## 3. Widening Conversion: No Integer Loss Among the Four Types

The typical widening chain is:

```text
byte → short → int → long
```

Every value of a type on the left can be represented by the types on the right:

```java
byte original = -100;
short a = original;
int b = a;
long c = b;        // c is still -100
```

Widening conversions among **`byte`, `short`, `int`, and `long`** are implicit and preserve the exact value. However, do not assume that converting a large `long` to `double` also always preserves every integer digit accurately: the significand precision of floating-point numbers is finite.

## 4. Narrowing Conversion: Casting Can Change the Value

To assign from a larger type to a smaller type, Java generally requires an explicit cast:

```java
int number = 130;
byte small = (byte) number; // -126

long huge = 3_000_000_000L;
int changed = (int) huge;   // -1294967296
```

For narrowing integer conversions, Java keeps **the low-order bits**, discards the high-order bits, and then interprets the result according to the signed target type. For example, 130 has the low eight bits `1000_0010`, so when read as a signed `byte`, the resulting value is -126. Casting **does not round**, **does not clamp at `MIN_VALUE`/`MAX_VALUE`**, and **does not automatically throw an error** if the number exceeds the target range.

If you need to convert a `long` to `int` and detect out-of-range values, use `Math.toIntExact(value)`: it throws `ArithmeticException` when the value cannot be represented in `int`. For `int` to `byte` or `short`, check the target type's bounds before casting.

## 5. Promotion Rules in Arithmetic Expressions

In many binary operations such as `+`, `-`, `*`, `/`, and `%`, `byte` or `short` operands are promoted to **`int`** before calculation (*binary numeric promotion*). When one operand is `long` and the other is one of these four integer types, the operation is performed as `long`.

```java
byte a = 10;
byte b = 20;
int sum = a + b;            // Valid: expression type is int
// byte wrong = a + b;      // Compile error: int does not automatically narrow to byte
byte smallSum = (byte) (a + b);

int x = 1_000_000;
long wrongProduct = x * x;          // int multiplication overflows before assigning to long
long correctProduct = (long) x * x; // 1_000_000_000_000L
```

**The type of the receiving variable does not determine the intermediate type of the expression**. `long wrongProduct = x * x` still multiplies as `int`. Casting one operand to `long` **before the operation** is what makes the multiplication run as `long`; even then, you must still ensure the result fits within `long` bounds.

Unary operators `+`, `-`, and `~` promote `byte`/`short` to `int`. For bit shifts `<<`, `>>`, and `>>>`, the promoted left-hand operand determines the result type (`int` or `long`).

### Why does `byte counter += 1` compile?

```java
byte counter = 127;
counter += 1;             // Valid, result will be -128
// counter = counter + 1;  // Error: counter + 1 has type int
```

The compound assignment `counter += 1` includes an implicit cast back to `byte` (similar to `counter = (byte) (counter + 1)`, except the left-hand expression is evaluated only once). This is syntactically convenient, but **does not protect against overflow**.

## 6. Overflow and Safe Arithmetic

If the mathematical result exceeds the value range, addition/subtraction/multiplication on primitive integer types produces a result within the fixed bit width. For example:

- `Integer.MAX_VALUE + 1` gives `Integer.MIN_VALUE`.
- `Long.MAX_VALUE + 1L` gives `Long.MIN_VALUE`.
- `Math.abs(Integer.MIN_VALUE)` still gives `Integer.MIN_VALUE` because the corresponding positive value cannot be represented in `int`.

Ordinary addition, subtraction, and multiplication **do not automatically throw an exception on overflow**. If you need to detect overflow rather than receive a wrapped result, use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.incrementExact`, `Math.decrementExact`, `Math.negateExact`, or perform range checks. They throw `ArithmeticException` for the overflow cases handled by the API. `Math.toIntExact` is specifically useful for converting `long` to `int`.

To compute with integers beyond 64 bits, use `java.math.BigInteger`. `BigInteger` does not have a fixed width like `long`, though it is still subject to memory and processing time limits.

## 7. Integer Division, Remainder, and Division by Zero

Dividing two integers produces an integer result, **truncating the fractional part toward 0**:

- `7 / 3 == 2`.
- `-7 / 3 == -2`, not -3.
- `7 % 3 == 1`.
- `-7 % 3 == -1` (a non-zero remainder has the same sign as the dividend).

If the divisor is 0, `x / 0` and `x % 0` with integer operands throw `ArithmeticException`. As a special case, `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE` according to the fixed-width integer rule, without throwing an exception.

When business logic requires division **rounded toward negative infinity**, `Math.floorDiv` and `Math.floorMod` follow different rules from `/` and `%` when negative numbers are involved. These APIs do not replace general overflow checks.

## 8. Are There Unsigned Integer Types?

All four primitives discussed here are **signed**. However, Java provides APIs to **interpret the bits as unsigned values** in protocols or binary files:

- `Byte.toUnsignedInt(b)`: reads the 8-bit pattern of a `byte` as a number from 0 to 255, returning an `int`.
- `Short.toUnsignedInt(s)`: reads the 16-bit pattern as a number 0..65535.
- `Integer.toUnsignedLong(i)`: reads the 32-bit pattern as a number 0..4294967295 as a `long`.
- `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Long.compareUnsigned`, and `Long.toUnsignedString`: support operations and representations with unsigned semantics.

For example, `Integer.toUnsignedLong(-1)` equals `4_294_967_295L` because all 32 bits of -1 are 1. The original `int` variable **is still -1**; this is a change in bit interpretation, not a new `unsigned int` primitive type.

## 9. Complete Example Running on Java 17+

Save the file `IntegerTypesDemo.java`:

```java
public class IntegerTypesDemo {
    public static void main(String[] args) {
        byte b = 127;
        short s = 30_000;
        int i = 2_000_000_000;
        long l = 3_000_000_000L;

        System.out.println("byte: " + Byte.MIN_VALUE + " .. " + Byte.MAX_VALUE);
        System.out.println("short: " + Short.MIN_VALUE + " .. " + Short.MAX_VALUE);
        System.out.println("int: " + Integer.MIN_VALUE + " .. " + Integer.MAX_VALUE);
        System.out.println("long: " + Long.MIN_VALUE + " .. " + Long.MAX_VALUE);
        System.out.println("values: " + b + ", " + s + ", " + i + ", " + l);

        byte a = 10, c = 20;
        int sum = a + c;
        System.out.println("byte + byte -> int: " + sum);

        System.out.println("int overflow: " + (Integer.MAX_VALUE + 1));
        System.out.println("promote before add: " + ((long) Integer.MAX_VALUE + 1));
        System.out.println("narrowing long -> int: " + (int) 3_000_000_000L);

        System.out.println("division: " + (-7 / 3) + ", remainder: " + (-7 % 3));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact: overflow detected");
        }
        System.out.println("unsigned view of -1: " + Integer.toUnsignedLong(-1));
    }
}
```

Compile/run:

```bash
javac IntegerTypesDemo.java
java IntegerTypesDemo
```

Output:

```text
byte: -128 .. 127
short: -32768 .. 32767
int: -2147483648 .. 2147483647
long: -9223372036854775808 .. 9223372036854775807
values: 127, 30000, 2000000000, 3000000000
byte + byte -> int: 30
int overflow: -2147483648
promote before add: 2147483648
narrowing long -> int: -1294967296
division: -2, remainder: -1
addExact: overflow detected
unsigned view of -1: 4294967295
```

**Explanation:** Adding two `byte` values is processed as `int`; adding `Integer.MAX_VALUE + 1` overflows the `int` range; promoting one operand to `long` before adding preserves `2147483648`; casting `3_000_000_000L` to `int` drops the high bits; negative division truncates the fractional remainder toward 0; `Math.addExact` proactively detects overflow; `Integer.toUnsignedLong` only changes how the bits are interpreted.

## 10. Wrapper Utilities and Boxing

| Task | API | Notes |
| --- | --- | --- |
| Read bounds | `Integer.MIN_VALUE`, `Long.MAX_VALUE` | Avoid hard-coded magic numbers that are hard to verify |
| Parse string to number | `Integer.parseInt("42")`, `Long.parseLong("3000000000")` | `NumberFormatException` if malformed or out of range |
| Convert number to string | `Integer.toString(x)`, `Long.toString(y)` | Does not expand the data range |
| Compare | `Integer.compare(x, y)`, `Long.compare(x, y)` | Safer than comparing using the sign of `x-y` when subtraction can overflow |
| Checked arithmetic | `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact` | Detects certain overflow errors |
| Bitwise interpretation | `Byte.toUnsignedInt`, `Integer.toUnsignedLong` | Useful for binary/network protocols |

`Byte`, `Short`, `Integer`, and `Long` are **wrapper reference types**, unlike primitive `byte`, `short`, `int`, and `long`. `List<Integer>` holds wrappers, involving boxing/unboxing. A wrapper can be `null`, and **unboxing `null` throws `NullPointerException`**. For an `int[]` array, the elements are primitive values, not individual `Integer` objects.

## 11. Choosing the Right Type

| Need | Suggested Type | Why |
| --- | --- | --- |
| Counts, counters, loops, array indices, general arithmetic | `int` | Sufficient for most everyday integers and aligns with promotion rules |
| Timestamps, millisecond durations, very large counters | `long` | Wider range than `int`; arithmetic overflow still needs checking |
| A byte of data in a file, buffer, or protocol | `byte`/`byte[]` | Matches the 8-bit data unit; can be interpreted as unsigned when needed |
| Source data specifically requiring a signed 16-bit integer | `short` | Accurately reflects 16-bit bounds/format |
| Integers exceeding the 64-bit range | `BigInteger` | Not restricted to a fixed 64-bit width |

Do not use `byte` or `short` just thinking arithmetic will be more efficient; many Java operators still promote them to `int`. If source data allows values up to 255, a signed `byte` **cannot** directly represent every value 0..255 under signed semantics. Determine the unit, value range, and conversion rules before choosing a type.

## 12. Common Mistakes and How to Avoid Them

1. **Mistaking `int` for 64-bit on a 64-bit machine:** Java keeps fixed 32/64-bit widths.
2. **Forgetting `L` on large decimal literals:** `long x = 3_000_000_000;` is invalid; `3_000_000_000L` is required.
3. **Assigning `byte + byte` back to `byte`:** the expression's result is `int`; change the target declaration or cast after range checking.
4. **Casting after the expression has already overflowed:** `long r = (long) (x * y);` does not recover lost bits; widen an operand before multiplication.
5. **Assuming casting automatically throws an error or clamps to bounds:** `(byte) 130` equals `-126`, not 127.
6. **Assuming integer addition automatically throws on overflow:** addition/subtraction/multiplication normally wrap around; use the `Exact` methods when needed.
7. **Dividing integers and expecting a fractional result:** `1 / 2` equals 0; use floating-point operations or decimal representations as required.
8. **Assuming `-7 / 3` equals -3:** integer division `/` truncates toward 0, so it equals -2.
9. **Using `x - y` to get the comparison sign:** the difference can overflow; use relational comparisons or `Integer.compare`.
10. **Assuming `byte` is an integer from 0..255:** that is the unsigned interpretation; primitive signed `byte` is -128..127.

## 13. Self-Check

- Can `short` hold 40,000? **No**, because its maximum is 32,767.
- Does `long id = 5_000_000_000;` compile? **No**; the decimal literal must have `L`.
- If `byte a = 5, b = 6;`, what type does `a + b` have? **`int`**.
- Does `int x = 1_500_000_000; long y = x * 2;` give 3 billion? **No**, the `int` multiplication expression overflowed. Use `x * 2L`.
- Does `Math.addExact(Integer.MAX_VALUE, 1)` return a wrapped `int`? **No**; it throws `ArithmeticException`.
- What is `Integer.toUnsignedLong(-1)`? **4_294_967_295L**, while the input `int` variable remains -1.

**Remember:** `byte`/`short`/`int`/`long` all store integers accurately **within their own ranges**. The core difference is **8 / 16 / 32 / 64 bits**. Before computing, check the types of **literals and operands**; before narrowing, check the range; when overflow detection is needed, use the appropriate checking API.
