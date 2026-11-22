# `parseUnsignedInt`, `parseUnsignedLong`, and `toUnsignedString` in Java

## 1. Purpose and Context

Java has signed primitive types `byte`, `short`, `int`, and `long`; there is no separate primitive type for 32-bit or 64-bit unsigned integers. Nevertheless, the 32 or 64 bits of a value can still be **interpreted as unsigned** through APIs on `Integer` and `Long`.

This lesson explains three operations that commonly go together:

- `Integer.parseUnsignedInt(...)`: parses a string representing a 32-bit unsigned integer and returns the **bit pattern** as an `int`.
- `Long.parseUnsignedLong(...)`: parses a string representing a 64-bit unsigned integer and returns the **bit pattern** as a `long`.
- `Integer.toUnsignedString(...)` and `Long.toUnsignedString(...)`: interpret the bit pattern as unsigned and format it as a string.

Most important takeaway: **a negative value when printed as signed does not mean unsigned parsing failed**. The very same bit pattern simply has two interpretations.

## 2. Same Bits, Two Interpretations

| Width | Signed Interpretation | Unsigned Interpretation |
| --- | --- | --- |
| 32-bit (`int`) | −2³¹ to 2³¹ − 1 | 0 to 2³² − 1 = 4,294,967,295 |
| 64-bit (`long`) | −2⁶³ to 2⁶³ − 1 | 0 to 2⁶⁴ − 1 = 18,446,744,073,709,551,615 |

Java represents `int` and `long` using two's complement. All 1 bits have a signed value of `-1`, yet when treated as unsigned they correspond to 2³² − 1 or 2⁶⁴ − 1.

~~~java
int bits32 = -1;
long bits64 = -1L;

System.out.println(bits32);                           // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295
System.out.println(bits64);                           // -1
System.out.println(Long.toUnsignedString(bits64));    // 18446744073709551615
~~~

This is an *illustrative snippet placed inside a method*; the complete runnable Java program is in section 6. `toUnsignedString` does not modify the bits in the variable. It only chooses how to convert those bits into decimal characters.

For numbers whose sign bit is 0, such as `42`, the signed and unsigned strings are identical; the difference appears when the highest bit is 1.

## 3. `Integer.parseUnsignedInt`: String → 32-Bit Pattern

Two commonly used signatures:

~~~java
static int Integer.parseUnsignedInt(String s)
static int Integer.parseUnsignedInt(String s, int radix)
~~~

- If `radix` is omitted, the default base is **10**.
- `radix` ranges from **2 to 36**. Hexadecimal letters may be uppercase or lowercase.
- The string must represent a value in **0 to 4294967295**. Out-of-range values, invalid digits for the radix, an empty string, or a minus sign throw `NumberFormatException`.
- The method returns `int`, so the result can be negative under signed interpretation. To use the exact unsigned value in a larger type, call `Integer.toUnsignedLong(int)`.

Step-by-step example:

~~~java
int value = Integer.parseUnsignedInt("4294967295");
System.out.println(value);                           // -1
System.out.println(Integer.toUnsignedString(value)); // 4294967295
System.out.println(Integer.toUnsignedLong(value));   // 4294967295
~~~

`Integer.toUnsignedLong(value)` creates a `long` in `0..4294967295`; this is the easiest way to perform unsigned 32-bit arithmetic when you need a wider numeric range.

With base 16:

~~~java
int hexBits = Integer.parseUnsignedInt("FFFFFFFF", 16);
System.out.println(hexBits);                            // -1
System.out.println(Integer.toUnsignedString(hexBits, 16)); // ffffffff
~~~

The string `"FFFFFFFF"` has no `0x` prefix. When specifying radix 16, pass `"FF"` rather than `"0xFF"`; `parseUnsignedInt` does not automatically detect or strip prefixes. Likewise, user-supplied strings must have prefixes handled according to your application's rules before parsing.

## 4. `Long.parseUnsignedLong`: String → 64-Bit Pattern

Two corresponding signatures:

~~~java
static long Long.parseUnsignedLong(String s)
static long Long.parseUnsignedLong(String s, int radix)
~~~

This method accepts **0 to 18446744073709551615** (2⁶⁴ − 1), exceeding `Long.parseLong`'s positive limit of 9223372036854775807. The result is still a signed `long`: if the highest bit is 1, printing it directly yields a negative number.

~~~java
long bits = Long.parseUnsignedLong("18446744073709551615");

System.out.println(bits);                            // -1
System.out.println(Long.toUnsignedString(bits));      // 18446744073709551615
System.out.println(Long.toUnsignedString(bits, 16));  // ffffffffffffffff
~~~

No Java primitive type can hold **all** unsigned 64-bit values as positive numbers. If you need to represent them as positive numbers for calculations beyond 64 bits, use `java.math.BigInteger` after converting the bit pattern to a string:

~~~java
import java.math.BigInteger;

// Illustrative snippet inside a method:
long raw = Long.parseUnsignedLong("18446744073709551615");
BigInteger positiveValue = new BigInteger(Long.toUnsignedString(raw));
System.out.println(positiveValue.add(BigInteger.ONE)); // 18446744073709551616
~~~

You can also compute `BigInteger.valueOf(raw).add(BigInteger.ONE.shiftLeft(64))` when `raw < 0`. Never use `BigInteger.valueOf(raw)` alone when `raw` is negative if your goal is to obtain the **unsigned value**.

## 5. `toUnsignedString`: Bit Pattern → String and Radix

| API | Input Arguments | Meaning |
| --- | --- | --- |
| `Integer.toUnsignedString(int value)` | 32-bit pattern | Unsigned 32-bit decimal string |
| `Integer.toUnsignedString(int value, int radix)` | Bit pattern and radix | Unsigned 32-bit string in specified radix |
| `Long.toUnsignedString(long value)` | 64-bit pattern | Unsigned 64-bit decimal string |
| `Long.toUnsignedString(long value, int radix)` | Bit pattern and radix | Unsigned 64-bit string in specified radix |

Example with the same bit pattern:

~~~java
int n = 0x8000_0000;
System.out.println(Integer.toString(n));             // -2147483648
System.out.println(Integer.toUnsignedString(n));     // 2147483648
System.out.println(Integer.toUnsignedString(n, 16)); // 80000000
System.out.println(Integer.toUnsignedString(n, 2));  // 10000000000000000000000000000000
~~~

The output of `toUnsignedString(value, radix)` **does not automatically add prefixes** like `0x` or `0b` and uses lowercase letters for digits greater than 9. Invalid radices are handled by `toUnsignedString` according to the convention of `Integer.toString`/`Long.toString`: falling back to base 10; this differs from the parse methods, which throw an error when `radix` is outside 2..36.

Ideal round-trip pairs when exchanging data are `parseUnsignedInt` ↔ `Integer.toUnsignedString` or `parseUnsignedLong` ↔ `Long.toUnsignedString` with **the same radix**. The bit pattern may look negative when inspected as `int`/`long`, yet it still preserves the original unsigned value within the representable range.

## 6. Standalone Runnable Example on Java 17+

Create the file `UnsignedNumbersDemo.java`:

~~~java
import java.math.BigInteger;

public class UnsignedNumbersDemo {
    public static void main(String[] args) {
        int maxU32 = Integer.parseUnsignedInt("4294967295");
        long maxU64 = Long.parseUnsignedLong("18446744073709551615");

        System.out.println("u32 as int: " + maxU32);
        System.out.println("u32 decimal: " + Integer.toUnsignedString(maxU32));
        System.out.println("u32 as long: " + Integer.toUnsignedLong(maxU32));
        System.out.println("u32 from hex: " +
                Integer.toUnsignedString(Integer.parseUnsignedInt("FFFFFFFF", 16)));

        System.out.println("u64 as long: " + maxU64);
        System.out.println("u64 decimal: " + Long.toUnsignedString(maxU64));
        System.out.println("u64 hex: " + Long.toUnsignedString(maxU64, 16));

        System.out.println("compare u32 > 1: " +
                (Integer.compareUnsigned(maxU32, 1) > 0));
        System.out.println("u32 / 10: " + Integer.divideUnsigned(maxU32, 10));
        System.out.println("u32 % 10: " + Integer.remainderUnsigned(maxU32, 10));

        System.out.println("u64 / 10: " + Long.divideUnsigned(maxU64, 10L));
        System.out.println("u64 % 10: " + Long.remainderUnsigned(maxU64, 10L));

        BigInteger big = new BigInteger(Long.toUnsignedString(maxU64));
        System.out.println("u64 plus one: " + big.add(BigInteger.ONE));
    }
}
~~~

Compile and run:

~~~bash
javac UnsignedNumbersDemo.java
java UnsignedNumbersDemo
~~~

Expected output:

~~~text
u32 as int: -1
u32 decimal: 4294967295
u32 as long: 4294967295
u32 from hex: 4294967295
u64 as long: -1
u64 decimal: 18446744073709551615
u64 hex: ffffffffffffffff
compare u32 > 1: true
u32 / 10: 429496729
u32 % 10: 5
u64 / 10: 1844674407370955161
u64 % 10: 5
u64 plus one: 18446744073709551616
~~~

Explanation:

1. Both `parseUnsigned...` calls return all-1 bit patterns, which print directly as `-1` under signed formatting.
2. Both `toUnsignedString` calls decode the bit patterns accurately into the unsigned range; the call with `radix = 16` outputs lowercase `f`.
3. `Integer.toUnsignedLong` widens the 32-bit pattern to a positive `long`, avoiding the *sign extension* of `(long) maxU32`.
4. `compareUnsigned`, `divideUnsigned`, and `remainderUnsigned` apply unsigned semantics, so the largest 32/64-bit unsigned value is greater than 1 and dividing by 10 leaves remainder 5.
5. `BigInteger` allows adding past the unsigned 64-bit limit without overflow.

## 7. Boundary Checks, Invalid Data, and Radix

Test representative cases:

| Call | Result |
| --- | --- |
| `Integer.parseUnsignedInt("0")` | `0` |
| `Integer.parseUnsignedInt("2147483648")` | `-2147483648` (bits of 2³¹) |
| `Integer.parseUnsignedInt("4294967295")` | `-1` |
| `Integer.parseUnsignedInt("4294967296")` | `NumberFormatException`: exceeds 32-bit unsigned |
| `Long.parseUnsignedLong("9223372036854775808")` | `Long.MIN_VALUE` |
| `Long.parseUnsignedLong("18446744073709551615")` | `-1L` |
| `Long.parseUnsignedLong("18446744073709551616")` | `NumberFormatException`: exceeds 64-bit unsigned |
| `Integer.parseUnsignedInt("1010", 2)` | `10` |
| `Long.parseUnsignedLong("ff", 16)` | `255L` |
| `Integer.parseUnsignedInt("-1")` | `NumberFormatException`: minus sign not allowed |
| `Integer.parseUnsignedInt("0xFF", 16)` | `NumberFormatException`: `0x` is not a base-16 digit |
| `Integer.parseUnsignedInt("12 3")` | `NumberFormatException`: internal whitespace |

Strings may have a leading plus sign (`"+42"`) and leading zeros (`"00042"`); they do not change the value. However, the parse methods do not automatically `trim()` whitespace, do not accept Java literal `_` separators, and do not accept a minus sign even if that negative number has a valid bit pattern. Normalize input (such as calling `trim()` or stripping a prefix) only when your input format rules allow it.

Distinguish parser errors from valid negative values in the result:

~~~java
try {
    int bits = Integer.parseUnsignedInt("4294967296");
    System.out.println(Integer.toUnsignedString(bits));
} catch (NumberFormatException ex) {
    System.out.println("Value is outside the unsigned 32-bit range");
}
~~~

The snippet above prints only:

~~~text
Value is outside the unsigned 32-bit range
~~~

Do not catch `NumberFormatException` and silently default to `0` if `0` is a meaningful business value; report the input error or return an explicit validation result.

## 8. Comparing and Computing with Correct Unsigned Semantics

Parsing and formatting strings are not enough if the application also needs to compare, divide, or take remainders.

~~~java
int a = Integer.parseUnsignedInt("4294967295");
int b = 1;

System.out.println(a < b);                           // true: signed comparison (-1 < 1)
System.out.println(Integer.compareUnsigned(a, b) > 0); // true: unsigned comparison
System.out.println(Integer.divideUnsigned(a, 2));     // 2147483647
System.out.println(Integer.remainderUnsigned(a, 2));  // 1
~~~

This is an illustrative snippet inside a method. `Long` has corresponding APIs: `Long.compareUnsigned`, `Long.divideUnsigned`, `Long.remainderUnsigned`. `+`, `-`, and `*` on `int`/`long` keep the low bits and can wrap (modulo 2³²/2⁶⁴); Java does not report overflow for these operators automatically. If business logic requires detecting overflow **within the unsigned range**, check separately or compute with `BigInteger` and validate bounds.

For **unsigned 32-bit values**, you can also widen both operands with `Integer.toUnsignedLong` and use signed comparisons/divisions on `long`, because every unsigned 32-bit value fits in the positive range of `long`. The same trick does not cover all of unsigned 64-bit: use `Long`'s unsigned APIs or `BigInteger` instead.

## 9. Application: 32-Bit Identifiers from a Protocol or Binary File

A protocol may specify a `requestId` field as a 32-bit unsigned integer. The value `4026531841` has bit pattern `0xF0000001`; if stored in an `int`, Java displays it as a negative number. Yet we can still pass and serialize the exact unsigned decimal string:

~~~java
int requestIdBits = Integer.parseUnsignedInt("4026531841");
String wireText = Integer.toUnsignedString(requestIdBits);

System.out.println(requestIdBits); // -268435455
System.out.println(wireText);      // 4026531841
~~~

This is an illustrative snippet inside a method. When reading data from a byte stream, byte order (*endianness*) and bit assembly are separate concerns; `parseUnsignedInt` accepts a **digit string**, and does not decode a byte array directly or handle byte order. If you need to read a single byte as 0..255, use `Byte.toUnsignedInt(byteValue)` to avoid sign extension effects.

## 10. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using `Integer.parseInt("4294967295")` | Exceeds `Integer.MAX_VALUE` | `Integer.parseUnsignedInt` |
| Using `Long.parseLong` for 2⁶⁴ − 1 | Exceeds `Long.MAX_VALUE` | `Long.parseUnsignedLong` |
| Printing `System.out.println(bits)` and thinking data is wrong | Shows a negative number | `Integer.toUnsignedString` or `Long.toUnsignedString` |
| Casting `(long) intBits` for unsigned 32-bit | Negative due to sign extension | `Integer.toUnsignedLong(intBits)` |
| Comparing `a < b` on unsigned bits | Uses signed ordering | `compareUnsigned(a, b)` |
| Dividing `a / b` when an operand has sign bit 1 | Uses signed division | `divideUnsigned` and `remainderUnsigned` |
| Passing `"0xFF"` with radix 16 | Parsing fails | Strip prefix, pass `"FF"` |
| Writing large literal `18446744073709551615L` | Fails to compile | Parse from string; use `BigInteger` when positive value is needed |
| Expecting parse to strip whitespace or `_` | `NumberFormatException` | Normalize input in a controlled way |

## 11. Self-Check

**Question 1.** Why does `Integer.parseUnsignedInt("4294967295")` return `-1` without throwing an exception?

Because the string is valid for a 32-bit unsigned integer; the method returns the exact 32 all-1 bits as a signed `int`. `Integer.toUnsignedString` converts those same 32 bits back to `"4294967295"`.

**Question 2.** How do you obtain the largest 32-bit unsigned value as a positive number so you can add 1 without losing data?

~~~java
int raw = Integer.parseUnsignedInt("4294967295");
long sum = Integer.toUnsignedLong(raw) + 1L;
System.out.println(sum); // 4294967296
~~~

This is an illustrative snippet inside a method; `long` has a wide enough positive range for this result.

**Question 3.** Can you add `+1` to the largest 64-bit unsigned value and store the positive number 18446744073709551616 in a `long`?

No. `long` cannot hold that positive number. Convert to `BigInteger` as shown in section 4 before adding.

**Question 4.** If the input is `"ffffffffffffffff"` in base 16, which APIs should be used to preserve the full bit pattern?

`Long.parseUnsignedLong("ffffffffffffffff", 16)`, and then `Long.toUnsignedString(result, 16)` to format it back. The output is `"ffffffffffffffff"`.

## 12. Remember

- `parseUnsignedInt` and `parseUnsignedLong` **validate the unsigned range** and return the bit pattern in the corresponding signed type.
- `toUnsignedString` **formats the bits in the unsigned range**, without altering the stored bit pattern.
- For 32 bits, `Integer.toUnsignedLong` converts to a positive `long`; for 64 bits you need `BigInteger` if you need positive values exceeding `Long.MAX_VALUE`.
- The radix when parsing and formatting must match the data format. Pay attention to error conditions, unsigned comparison/division, and overflow during arithmetic.