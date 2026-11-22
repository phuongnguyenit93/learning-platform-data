# `compareUnsigned`, `divideUnsigned`, and `remainderUnsigned` in Java

## 1. The Problem: Signed `int`/`long` vs. Data That Must Be Read as Unsigned

Java only has **signed** 32-bit `int` and 64-bit `long` primitive types; there are no primitive `uint` or `ulong` types. However, the same sequence of bits can be interpreted as either a signed or an unsigned number:

| Bit Pattern | Signed Interpretation | Unsigned Interpretation |
| --- | ---: | ---: |
| `int` all `0` bits | 0 | 0 |
| `int` `0x7FFFFFFF` | 2,147,483,647 | 2,147,483,647 |
| `int` `0x80000000` | -2,147,483,648 | 2,147,483,648 |
| `int` `0xFFFFFFFF` | -1 | 4,294,967,295 |
| `long` `0xFFFFFFFFFFFFFFFFL` | -1 | 18,446,744,073,709,551,615 |

With 32 bits, the unsigned range is `0..2^32-1`; with 64 bits, the unsigned range is `0..2^64-1`. The two views **do not alter the stored bits**. They only change the meaning of comparing, dividing, taking the remainder, or displaying those bits.

For example, `int value = -1;` has the bit pattern `0xFFFFFFFF`. Under signed rules, `-1 < 1`; when interpreted as a 32-bit unsigned number, `4_294_967_295 > 1`. Java provides static methods to perform **operations under unsigned semantics** while still using `int`/`long`.

Three main API groups (available since Java 8):

- `Integer.compareUnsigned(int x, int y)` and `Long.compareUnsigned(long x, long y)`.
- `Integer.divideUnsigned(int dividend, int divisor)` and `Long.divideUnsigned(long dividend, long divisor)`.
- `Integer.remainderUnsigned(int dividend, int divisor)` and `Long.remainderUnsigned(long dividend, long divisor)`.

These methods are appropriate when a **protocol, bit field, file format, counter, or identifier** defines the bits as an unsigned integer. They do not turn Java into a language with new unsigned primitive types.

## 2. Semantics of `compareUnsigned`

`compareUnsigned(x, y)` compares two bit patterns after interpreting them as **unsigned numbers**, and returns an `int`:

- **Negative** value: `x` is less than `y` in unsigned order.
- `0`: both bit patterns are equal.
- **Positive** value: `x` is greater than `y` in unsigned order.

Do not rely on the exact return value being `-1` or `1`; the method's contract is the **sign of the result**. When using a Comparator, check `< 0`, `== 0`, or `> 0`.

```java
int a = -1;  // bits 0xFFFFFFFF => unsigned 4294967295.
int b = 1;

System.out.println(Integer.compare(a, b) < 0);         // true.
System.out.println(Integer.compareUnsigned(a, b) > 0); // true.
```

Under ordinary comparison, `-1 < 1`. Under unsigned semantics, `0xFFFFFFFF` represents `4_294_967_295`, so it is greater than `1`.

A quick way to read bit patterns:

- If two `int`s both have sign bit `0`, signed and unsigned comparisons have the same order.
- If two `int`s both have sign bit `1`, their relative comparison order is also the same (both lie in the upper half of the unsigned range).
- If one value has sign bit `1` (appearing negative) and the other has sign bit `0`, **the value appearing negative is greater as unsigned**.

The same rule applies to 64-bit `long`.

### Example: sorting in unsigned order

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(-1, 2, 0, -2));
numbers.sort(Integer::compareUnsigned);
System.out.println(numbers); // [0, 2, -2, -1]
```

The list still prints the values in **signed** `int` form, yet the sort order is based on unsigned meaning: `0`, `2`, `4_294_967_294`, `4_294_967_295`. Do not use `Comparator.naturalOrder()` or signed `<` comparison when a field must be ordered as unsigned.

Note that `Arrays.sort(int[])` sorts as signed `int`. To use an unsigned comparator, the example above uses a `List<Integer>`, or else you need to implement a custom unsigned sorting strategy.

## 3. Semantics of `divideUnsigned` and `remainderUnsigned`

Given two bit patterns of the same bit width `w`, let:

- `A` be the unsigned value of `dividend`, in `0..2^w-1`.
- `B` be the unsigned value of `divisor`, which **must be nonzero**.
- `Q = floor(A / B)` be the unsigned integer quotient.
- `R = A - B * Q` be the remainder, satisfying `0 <= R < B`.

When `divisor` has an all-zero bit pattern, both unsigned divide and remainder methods throw `ArithmeticException`, just like ordinary integer division.

### Example with `int`

```java
int dividend = -1; // 0xFFFFFFFF, unsigned value = 4294967295.
int divisor = 10;

int signedQuotient = dividend / divisor;
int signedRemainder = dividend % divisor;
int unsignedQuotient = Integer.divideUnsigned(dividend, divisor);
int unsignedRemainder = Integer.remainderUnsigned(dividend, divisor);

System.out.println(signedQuotient);   // 0
System.out.println(signedRemainder);  // -1
System.out.println(unsignedQuotient); // 429496729
System.out.println(unsignedRemainder);// 5
```

As unsigned, `4_294_967_295 = 10 × 429_496_729 + 5`. The unsigned results differ completely from `-1 / 10 == 0` and `-1 % 10 == -1` under signed operations. This is a **change in arithmetic rules**, not merely a change in how numbers are printed.

### Case where the divisor has sign bit 1

```java
int dividend = 10;
int divisor = -1; // Unsigned value = 4294967295.

System.out.println(Integer.divideUnsigned(dividend, divisor));    // 0
System.out.println(Integer.remainderUnsigned(dividend, divisor)); // 10
```

Under unsigned interpretation, the divisor is larger than the dividend, so the quotient is 0 and the remainder equals the dividend itself. Do not treat the divisor `-1` as a negative number when reasoning about unsigned results.

## 4. Unsigned Division Results Still Have Type `int`/`long`

This is the easiest point to misunderstand: the unsigned APIs **return Java's signed primitive types**.

`Integer.divideUnsigned` returns `int`; `Long.divideUnsigned` returns `long`. If the unsigned quotient exceeds the positive range of that type, the resulting bit pattern can appear as **a negative number** when printed directly.

```java
int x = -1; // unsigned 4294967295.
int q = Integer.divideUnsigned(x, 1);

System.out.println(q);                         // -1
System.out.println(Integer.toUnsignedString(q)); // 4294967295
System.out.println(Integer.toUnsignedLong(q));   // 4294967295
```

Reason: the actual unsigned quotient is `4_294_967_295`, which has the bit pattern `0xFFFFFFFF`. The API returns that bit pattern as an `int`, so `System.out.println(q)` prints `-1` under signed interpretation. To read it properly as unsigned, use `Integer.toUnsignedString(q)` or convert to an unsigned `long` via `Integer.toUnsignedLong(q)`.

**Especially with `long`**:

```java
long allBits = -1L; // unsigned 18446744073709551615.
long quotient = Long.divideUnsigned(allBits, 1L);

System.out.println(quotient);                       // -1
System.out.println(Long.toUnsignedString(quotient)); // 18446744073709551615
```

No Java primitive type can store the entire unsigned 64-bit range as a **non-negative number**. If you need to represent mathematical integers from 0 to `2^64-1`, you can use `BigInteger` via the unsigned string:

```java
import java.math.BigInteger;

long bits = -1L;
BigInteger asPositive = new BigInteger(Long.toUnsignedString(bits));
System.out.println(asPositive); // 18446744073709551615
```

Do not use `BigInteger.valueOf(bits)` when you want an **unsigned** number: it preserves the signed value `-1`.

## 5. Unsigned Conversion Is Not Ordinary Widening Conversion

A negative `int` assigned directly to `long` is **sign-extended**:

```java
int bits = -1;

long signedWiden = bits;
long unsignedWiden = Integer.toUnsignedLong(bits);

System.out.println(signedWiden);   // -1
System.out.println(unsignedWiden); // 4294967295
```

`Integer.toUnsignedLong(bits)` is equivalent to `bits & 0xFFFF_FFFFL`. The mask keeps the exact 32 bits of the `int` and clears the upper bits in `long`. This is useful when you want to do unsigned 32-bit arithmetic using a type **wide enough to hold every 32-bit value in non-negative form**.

```java
int a = -1;
int b = 2;

long unsignedA = Integer.toUnsignedLong(a);
long unsignedB = Integer.toUnsignedLong(b);

long quotient = unsignedA / unsignedB; // 2147483647
long remainder = unsignedA % unsignedB; // 1
```

For `int`, widening properly into `long` and then dividing works because `long` can hold `0..2^32-1`. However, for **unsigned `long`**, `long` cannot serve as a container for the full 0..2^64-1 range as non-negative values. That is why `Long.divideUnsigned`/`Long.remainderUnsigned` are especially valuable; if you need arithmetic on large numbers beyond that range, use `BigInteger`.

## 6. Unsigned 64-Bit Example: Comparing and Dividing Without Losing Bits

```java
long maxUnsignedBits = -1L; // 0xFFFFFFFFFFFFFFFF.
long divisor = 2L;

System.out.println(Long.compare(maxUnsignedBits, 1L) < 0); // true.
System.out.println(Long.compareUnsigned(maxUnsignedBits, 1L) > 0); // true.

long q = Long.divideUnsigned(maxUnsignedBits, divisor);
long r = Long.remainderUnsigned(maxUnsignedBits, divisor);

System.out.println(Long.toUnsignedString(q)); // 9223372036854775807
System.out.println(Long.toUnsignedString(r)); // 1
```

Unsigned `2^64-1` divided by `2` gives quotient `2^63-1`, remainder `1`. In this case the quotient happens to fit in the positive range of `long`, yet other divisions can return bit patterns with a negative sign bit; therefore using `Long.toUnsignedString` is a good habit when formatting output as unsigned.

**Note:** `Long.divideUnsigned(x, y)` does not perform floating-point division, does not round, and does not return `Infinity`. It is **64-bit unsigned integer division**; a divisor of `0L` throws `ArithmeticException`.

## 7. Relationship Between the Three Operations and the Division-with-Remainder Identity

For unsigned values `A` and `B != 0`, division guarantees:

```text
A = B * Q + R
0 <= R < B
Q = floor(A / B)
```

The mathematical expressions above are understood **over the domain of unsigned integers**. If you verify them using Java's `*` and `+` operators at the same bit width, intermediate computations can wrap under fixed-width integer arithmetic and display as signed values.

To verify an unsigned 32-bit example in a readable way, use `long` and `Integer.toUnsignedLong`:

```java
int a = -1;
int b = 10;
int q = Integer.divideUnsigned(a, b);
int r = Integer.remainderUnsigned(a, b);

long A = Integer.toUnsignedLong(a);
long B = Integer.toUnsignedLong(b);
long Q = Integer.toUnsignedLong(q);
long R = Integer.toUnsignedLong(r);

System.out.println(A == B * Q + R); // true.
System.out.println(R < B);          // true.
```

For unsigned 64-bit division, multiplying `B * Q` can exceed the range of `long`, so to verify mathematically without data loss you can use `BigInteger` (or compare using appropriate modular arithmetic).

## 8. Converting Unsigned Data to and from Strings

If external communication uses unsigned decimal text, do not default to `String.valueOf(value)` or `Integer.parseInt` for values exceeding `Integer.MAX_VALUE`.

| Purpose | API | Result / Notes |
| --- | --- | --- |
| Print `int` as unsigned | `Integer.toUnsignedString(value)` | Prints from 0 to 4294967295. |
| Print `long` as unsigned | `Long.toUnsignedString(value)` | Prints from 0 to 18446744073709551615. |
| Parse unsigned 32-bit string | `Integer.parseUnsignedInt(text)` | Returns `int` holding the exact bit pattern; may look negative when printed signed. |
| Parse unsigned 64-bit string | `Long.parseUnsignedLong(text)` | Returns `long` holding the exact bit pattern; may look negative when printed signed. |
| Read `int` as unsigned into positive `long` | `Integer.toUnsignedLong(value)` | Keeps 32 bits and interprets as 0..4294967295. |
| Read unsigned `long` as positive mathematical integer | `new BigInteger(Long.toUnsignedString(value))` | Can represent the entire 64-bit range. |

Example:

```java
int u32 = Integer.parseUnsignedInt("4294967295");
long u64 = Long.parseUnsignedLong("18446744073709551615");

System.out.println(u32);                         // -1.
System.out.println(Integer.toUnsignedString(u32)); // 4294967295.
System.out.println(u64);                         // -1.
System.out.println(Long.toUnsignedString(u64)); // 18446744073709551615.
```

`parseUnsignedInt` and `parseUnsignedLong` validate the range of the corresponding unsigned type and throw `NumberFormatException` on invalid strings or out-of-range numbers. They **do not** widen the variable into a new unsigned type.

The same data can be displayed very differently. When designing APIs, logs, or file storage, agree explicitly on **whether a field is signed or unsigned**, and use the corresponding conversion methods.

## 9. Comparison with `byte`/`short` and Bit Handling

`compareUnsigned`, `divideUnsigned`, and `remainderUnsigned` are directly provided on `Integer` and `Long`. For `byte` and `short`, convert to positive values in the unsigned range before comparing or dividing:

```java
byte raw = (byte) 0xFF;
int u8 = Byte.toUnsignedInt(raw); // 255.

short raw16 = (short) 0xFFFF;
int u16 = Short.toUnsignedInt(raw16); // 65535.

System.out.println(u8 / 10);   // 25
System.out.println(u8 % 10);   // 5
System.out.println(u16 > u8);  // true
```

`Byte.toUnsignedInt` is equivalent to `raw & 0xFF`; `Short.toUnsignedInt` is equivalent to `raw16 & 0xFFFF`. After converting to a positive `int`, ordinary signed comparisons and divisions give the same result as unsigned **because all operands lie within a wide enough positive range**.

When binary data is assembled into `int` or `long`, determine the byte order (*endianness*) and field interpretation from the protocol. A 32-bit field with its highest bit set to 1 will look negative in Java, even though the protocol defines it as a large unsigned integer; in that case, the three APIs above preserve the required semantics.

## 10. Complete Java 17+ Example

Create the file **`UnsignedOperationsDemo.java`**:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

public class UnsignedOperationsDemo {
    public static void main(String[] args) {
        int x = -1;
        int divisor = 10;

        System.out.println("signed compare -1 < 1 = "
                + (Integer.compare(x, 1) < 0));
        System.out.println("unsigned compare -1 > 1 = "
                + (Integer.compareUnsigned(x, 1) > 0));
        System.out.println("signed quotient = " + (x / divisor));
        System.out.println("signed remainder = " + (x % divisor));
        System.out.println("unsigned quotient = "
                + Integer.divideUnsigned(x, divisor));
        System.out.println("unsigned remainder = "
                + Integer.remainderUnsigned(x, divisor));
        System.out.println("unsigned int text = "
                + Integer.toUnsignedString(x));

        List<Integer> items = new ArrayList<>(List.of(-1, 2, 0, -2));
        items.sort(Integer::compareUnsigned);
        System.out.println("unsigned sorted = " + items);

        long bigBits = -1L;
        long quotient64 = Long.divideUnsigned(bigBits, 2L);
        long remainder64 = Long.remainderUnsigned(bigBits, 2L);
        System.out.println("unsigned long quotient = "
                + Long.toUnsignedString(quotient64));
        System.out.println("unsigned long remainder = "
                + Long.toUnsignedString(remainder64));

        long allBitsQuotient = Long.divideUnsigned(bigBits, 1L);
        System.out.println("quotient signed view = " + allBitsQuotient);
        System.out.println("quotient unsigned view = "
                + Long.toUnsignedString(allBitsQuotient));

        BigInteger fullUnsignedLong =
                new BigInteger(Long.toUnsignedString(bigBits));
        System.out.println("BigInteger view = " + fullUnsignedLong);

        int parsed = Integer.parseUnsignedInt("4294967295");
        System.out.println("parsed unsigned int bits = " + parsed);

        try {
            Integer.divideUnsigned(123, 0);
        } catch (ArithmeticException ex) {
            System.out.println("division by zero detected");
        }
    }
}
```

Compile and run:

```bash
javac UnsignedOperationsDemo.java
java UnsignedOperationsDemo
```

Output:

```text
signed compare -1 < 1 = true
unsigned compare -1 > 1 = true
signed quotient = 0
signed remainder = -1
unsigned quotient = 429496729
unsigned remainder = 5
unsigned int text = 4294967295
unsigned sorted = [0, 2, -2, -1]
unsigned long quotient = 9223372036854775807
unsigned long remainder = 1
quotient signed view = -1
quotient unsigned view = 18446744073709551615
BigInteger view = 18446744073709551615
parsed unsigned int bits = -1
division by zero detected
```

The example uses the exact same bits yet compares, divides, and prints them under two different interpretations. Note that `items` after sorting still displays signed values; the important point is that the comparator ordered them in **unsigned order**.

## 11. Common Mistakes

1. **Using `x < y` to compare unsigned protocol fields.** If sign bits differ, signed order can be the opposite of unsigned order. Use `compareUnsigned`.
2. **Using `x / y` or `x % y` on two unsigned bit patterns.** Default division/remainder interprets operands as signed. Use `divideUnsigned`/`remainderUnsigned` when the data rules are unsigned.
3. **Thinking `divideUnsigned` results always display as non-negative.** The return type is still `int` or `long`. For results exceeding the positive signed range, use `toUnsignedString` or convert to a suitably wide type.
4. **Converting a negative `int` to `long` by direct assignment and assuming it is unsigned.** Ordinary widening conversion preserves the sign. Use `Integer.toUnsignedLong` or `x & 0xFFFF_FFFFL`.
5. **Assuming `Long.toUnsignedString(x)` modifies `x`.** The method only produces a string representation of the same 64-bit pattern.
6. **Calling `Math.abs(x)` to handle unsigned integers.** Absolute value does not change bit interpretation, and for `MIN_VALUE` it also has an overflow trap.
7. **Forgetting to check for a 0 divisor.** Both unsigned divide and remainder throw `ArithmeticException` when the divisor has all 0 bits.
8. **Equating `Math.floorDiv`/`Math.floorMod` with unsigned operations.** `floorDiv`/`floorMod` apply rounding/sign rules on signed operands, not unsigned 32/64-bit semantics.
9. **Parsing the maximum unsigned `long` with `Long.parseLong`.** The value `2^64-1` exceeds `Long.MAX_VALUE`; use `Long.parseUnsignedLong` and display with `Long.toUnsignedString`.
10. **Confusing "bit pattern" with "mathematical integer".** Unsigned APIs define how to process 32/64-bit patterns; when you need to store positive values from 0 to `2^64-1` as mathematical numbers, convert to `BigInteger` appropriately.

## 12. Which API to Choose in Practice?

| Need | What to Use |
| --- | --- |
| Compare order of two unsigned 32-bit fields | `Integer.compareUnsigned(a, b)` |
| Compare order of two unsigned 64-bit fields | `Long.compareUnsigned(a, b)` |
| Unsigned 32-bit division | `Integer.divideUnsigned(a, b)` |
| Unsigned 32-bit remainder | `Integer.remainderUnsigned(a, b)` |
| Unsigned 64-bit division/remainder | `Long.divideUnsigned(a, b)`, `Long.remainderUnsigned(a, b)` |
| Print unsigned number accurately | `Integer.toUnsignedString(x)`, `Long.toUnsignedString(x)` |
| Parse unsigned number from string | `Integer.parseUnsignedInt(s)`, `Long.parseUnsignedLong(s)` |
| Widen unsigned 32-bit to positive number | `Integer.toUnsignedLong(x)` |
| Represent unsigned 64-bit as arbitrary positive number | `new BigInteger(Long.toUnsignedString(x))` |

**Remember:** Java still stores `int`/`long` as signed integer types, yet `compareUnsigned`, `divideUnsigned`, and `remainderUnsigned` perform operations under the **unsigned interpretation of the same bit pattern**. Distinguish the arithmetic operation from how the result is formatted, handle a 0 divisor, and use unsigned conversion/string APIs when communicating externally.

**References:** [Java SE 21 Integer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html), [Java SE 21 Long API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html), [Java Language Specification §4.2.1 — Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.1).