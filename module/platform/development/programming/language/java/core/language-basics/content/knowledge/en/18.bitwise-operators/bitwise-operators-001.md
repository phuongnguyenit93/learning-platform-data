# Bit Representation of Signed Integers — Java 17+

Java represents the **signed integer** types `byte`, `short`, `int`, and `long` using **two's complement** with a fixed bit width. Reading bit patterns accurately helps you understand negative numbers, bitwise operations, bit shifts, sign extension, and overflow.

Example with **8 bits**:

~~~text
Value       8-bit binary      Hex
     5      0000 0101         0x05
    -5      1111 1011         0xFB
     0      0000 0000         0x00
    -1      1111 1111         0xFF
  -128      1000 0000         0x80
   127      0111 1111         0x7F
~~~

**Key point:** the highest bit is the **sign bit** in the signed interpretation: a leading 0 indicates a non-negative value, and a leading 1 indicates a negative value. However, you do **not** simply flip the first bit to negate a number; all bits are interpreted according to the **two's complement** rule.

## 1. Bit Width and Value Range of Each Type

| Type | Bits | Signed value range |
| --- | ---: | --- |
| `byte` | 8 | −128 to 127 |
| `short` | 16 | −32,768 to 32,767 |
| `int` | 32 | −2,147,483,648 to 2,147,483,647 |
| `long` | 64 | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |

For bit width `w`, the two's complement range is:

\[
-2^{w-1}\ \leq\ x\ \leq\ 2^{w-1}-1
\]

The all-zero bit pattern represents 0; patterns whose highest bit is 1 represent negative numbers. The range is **asymmetric**: there is one more negative value than positive values; thus, for example, `Integer.MIN_VALUE` has no positive counterpart in `int`.

**Distinction:** `char` is also **16 bits** wide, but it is an **unsigned UTF-16 code unit** with values from 0 to 65,535. `boolean` is not an integer type used for manipulating sign bits.

## 2. How Does Two's Complement Work?

For a bit pattern of width `w`, its value can be interpreted using **bit weights**:

- Bits at positions 0 through `w-2` carry positive weights `2^i`.
- The highest bit, at position `w-1`, carries weight **`-2^(w-1)`**.

Example `11111011` (8 bits):

~~~text
Bit:      1   1  1  1  1  0  1  1
Weight: -128 64 32 16  8  4  2  1

Value: -128 + 64 + 32 + 16 + 8 + 0 + 2 + 1 = -5
~~~

One way to construct a negative bit pattern from a positive number at a fixed width:

1. Write the positive value in exactly `w` bits.
2. **Invert all bits** (0 ↔ 1).
3. **Add 1**, keeping only the low `w` bits.

~~~text
 +5:          0000 0101
 Invert bits: 1111 1010
 Add 1:       1111 1011    => -5
~~~

This rule applies to bit patterns at a fixed width. You cannot form `+128` in type `byte` to negate `-128` while staying in `byte`: `+128` is out of range.

### Relationship with Unsigned Interpretation

The same 8-bit pattern `11111011` can be read as:

- **Signed:** `-5`.
- **Unsigned:** `251`.

If a `w`-bit pattern has unsigned value `u`, its signed value is:

~~~text
If highest bit = 0:  signed = u
If highest bit = 1:  signed = u - 2^w
~~~

These are **two interpretations of the same bit pattern**, not two different bit sequences.

## 3. Standalone Runnable Java 17+ Program

Create a UTF-8 file named **`SignedIntegerBitsDemo.java`**:

~~~java
public class SignedIntegerBitsDemo {
    private static String padded(String bits, int width) {
        return "0".repeat(width - bits.length()) + bits;
    }

    private static String bits8(int n) {
        return padded(Integer.toBinaryString(n & 0xFF), 8);
    }

    private static String bits16(int n) {
        return padded(Integer.toBinaryString(n & 0xFFFF), 16);
    }

    private static String bits32(int n) {
        return padded(Integer.toBinaryString(n), 32);
    }

    private static String bits64(long n) {
        return padded(Long.toBinaryString(n), 64);
    }

    public static void main(String[] args) {
        System.out.println("== widths and ranges ==");
        System.out.println("byte=" + Byte.SIZE + ":"
                + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE);
        System.out.println("short=" + Short.SIZE + ":"
                + Short.MIN_VALUE + ".." + Short.MAX_VALUE);
        System.out.println("int=" + Integer.SIZE + ":"
                + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("long=" + Long.SIZE + ":"
                + Long.MIN_VALUE + ".." + Long.MAX_VALUE);

        System.out.println("== two's complement ==");
        System.out.println("byte5=" + bits8(5));
        System.out.println("byteMinus5=" + bits8(-5));
        System.out.println("byteMinus1=" + bits8(-1));
        System.out.println("byteMin=" + bits8(Byte.MIN_VALUE));
        System.out.println("byteMax=" + bits8(Byte.MAX_VALUE));
        System.out.println("intMinus5=" + bits32(-5));
        System.out.println("longMinus1=" + bits64(-1L));
        System.out.println("intMinHex="
                + Integer.toHexString(Integer.MIN_VALUE));
        System.out.println("minusOneHex="
                + Integer.toHexString(-1));
        System.out.println("notFour=" + (~4));
        System.out.println("negateFive=" + (~5 + 1));

        System.out.println("== sign extension ==");
        byte minusOne = -1;
        int widened = minusOne;
        System.out.println("widenedValue=" + widened);
        System.out.println("widenedHex="
                + Integer.toHexString(widened));
        System.out.println("lowByte=" + bits8(widened));
        System.out.println("maskedByte=" + (minusOne & 0xFF));
        System.out.println("unsignedByte="
                + Byte.toUnsignedInt(minusOne));

        short minusTwo = -2;
        System.out.println("shortBits=" + bits16(minusTwo));
        System.out.println("widenedShortHex="
                + Integer.toHexString(minusTwo));
        System.out.println("unsignedShort="
                + Short.toUnsignedInt(minusTwo));

        char maximumChar = (char) 0xFFFF;
        System.out.println("charValue=" + (int) maximumChar);
        System.out.println("charBits=" + bits16(maximumChar));
        System.out.println("castFFToByte=" + ((byte) 0xFF));

        System.out.println("== shifts ==");
        int negative = -8;
        System.out.println("minus8=" + bits32(negative));
        System.out.println("arithmeticRight=" + (negative >> 1));
        System.out.println("arithmeticBits="
                + bits32(negative >> 1));
        System.out.println("logicalRight=" + (negative >>> 1));
        System.out.println("logicalBits="
                + bits32(negative >>> 1));
        System.out.println("longLogicalRight="
                + (-8L >>> 1));
        System.out.println("byteShift=" + ((byte) -8 >> 1));
        System.out.println("oneShift32=" + (1 << 32));

        System.out.println("== limits ==");
        System.out.println("intOverflow="
                + (Integer.MAX_VALUE + 1));
        System.out.println("negatedIntMin="
                + (-Integer.MIN_VALUE));
        System.out.println("leadingZerosOne="
                + Integer.numberOfLeadingZeros(1));
        System.out.println("leadingZerosMinusOne="
                + Integer.numberOfLeadingZeros(-1));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file, using **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SignedIntegerBitsDemo.java
java SignedIntegerBitsDemo
~~~

**Exact expected stdout** of the `java SignedIntegerBitsDemo` command alone:

~~~text
== widths and ranges ==
byte=8:-128..127
short=16:-32768..32767
int=32:-2147483648..2147483647
long=64:-9223372036854775808..9223372036854775807
== two's complement ==
byte5=00000101
byteMinus5=11111011
byteMinus1=11111111
byteMin=10000000
byteMax=01111111
intMinus5=11111111111111111111111111111011
longMinus1=1111111111111111111111111111111111111111111111111111111111111111
intMinHex=80000000
minusOneHex=ffffffff
notFour=-5
negateFive=-5
== sign extension ==
widenedValue=-1
widenedHex=ffffffff
lowByte=11111111
maskedByte=255
unsignedByte=255
shortBits=1111111111111110
widenedShortHex=fffffffe
unsignedShort=65534
charValue=65535
charBits=1111111111111111
castFFToByte=-1
== shifts ==
minus8=11111111111111111111111111111000
arithmeticRight=-4
arithmeticBits=11111111111111111111111111111100
logicalRight=2147483644
logicalBits=01111111111111111111111111111100
longLogicalRight=9223372036854775804
byteShift=-4
oneShift32=1
== limits ==
intOverflow=-2147483648
negatedIntMin=-2147483648
leadingZerosOne=31
leadingZerosMinusOne=0
~~~

The two JDK version check commands print machine-dependent information and are not part of the fixed stdout block. `bits8` and `bits16` in the demo **mask out the high bits** before printing so you observe **exactly 8/16 bits** instead of accidentally printing the sign-extended `int` pattern.

## 4. Why Do Negative Numbers Print Many `1` Bits?

~~~java
System.out.println(Integer.toBinaryString(-1));
~~~

With a 32-bit `int`, `-1` has a two's complement pattern consisting of **32 `1` bits**. `Integer.toBinaryString` returns **the bit string in the two's complement representation of `int`**; for negative numbers, the string has length 32.

However, with a `byte`:

~~~java
byte value = -1;
System.out.println(Integer.toBinaryString(value));
~~~

The result is still **32 `1` bits**, because `byte` is **promoted to `int` before being passed as an argument**. To inspect only the low 8 bits:

~~~java
byte value = -1;
String eightBits = Integer.toBinaryString(value & 0xFF);
// eightBits == "11111111".
~~~

For positive numbers, `Integer.toBinaryString(5)` only prints `101` and **does not automatically pad to 32 bits**. The `padded` method in the program helps produce fixed-width strings for comparison.

**Note:** hex/binary display is a representation of data; it does not turn a negative number into a positive one just because there is no minus sign in the string. `Integer.toHexString(-1)` is `"ffffffff"`, corresponding to the 32-bit two's complement pattern.

## 5. Sign Extension When Converting `byte`/`short` to `int`

When widening a narrower **signed** integer type to a wider type, Java preserves the value by performing **sign extension**.

~~~text
byte  -1:           11111111            (8 bits)
int   -1:  11111111111111111111111111111111  (32 bits)
~~~

Therefore:

~~~java
byte value = -1;
int wide = value;        // -1, not 255.
int unsigned = value & 0xFF; // 255.
~~~

- `int wide = value` preserves the **signed value**.
- `value & 0xFF` keeps the **low 8 bits** and interprets them as a non-negative integer 0–255.
- `Byte.toUnsignedInt(value)` clearly expresses the intent to read a `byte` as an unsigned number.

For `short`, you can use `Short.toUnsignedInt(value)` to read the 16 bits as 0–65,535.

### Why Is `char` Different from `short`?

Both are 16 bits wide, yet:

~~~java
short signed = -1;
char unsigned = (char) 0xFFFF;

int fromShort = signed;    // -1.
int fromChar = unsigned;   // 65535.
~~~

`short` **sign-extends** when converted to `int`; `char` **zero-extends** because it is an **unsigned** code unit. Do not arbitrarily use `char` as a substitute for an "unsigned short" in character-handling code, because `char` carries specific UTF-16 semantics.

## 6. Negative Numbers in Bit Shifts

Signed bit patterns also explain why different right-shift operators produce different results. For `int -8` (`0xFFFFFFF8`), `>>` fills with the sign bit `1`, whereas `>>>` fills with `0`:

~~~java
System.out.println(-8 >> 1);  // -4: still negative.
System.out.println(-8 >>> 1); // 2147483644: new high bit is 0.
~~~

`<<` shifts left and inserts `0` bits on the right; bits shifted past the width of `int`/`long` are discarded. This is a bitwise operation, not an overflow-safe multiplication. `byte`, `short`, and `char` are promoted to `int` before shifting; `int` uses the low 5 bits of the shift distance, and `long` uses the low 6 bits. That is why `1 << 32` is 1. The lessons on bit shifts examine each mechanism and edge case individually.

## 7. Bit Inversion, Negation, and Overflow

In fixed-width two's complement representation, `~x` inverts all bits, and `-x == ~x + 1` in Java integer arithmetic. For example, `~4` is -5; `~5 + 1` is also -5. Overflow does not automatically throw an exception: `Integer.MAX_VALUE + 1` and `-Integer.MIN_VALUE` both evaluate to `Integer.MIN_VALUE`.

~~~java
int min = Integer.MIN_VALUE;
System.out.println(-min);            // -2147483648 (int overflow).
System.out.println(-(long) min);     // 2147483648 (widened first).
~~~

If you need overflow detection in business calculations, choose `Math.addExact`/`Math.negateExact`; if you need a range larger than `long`, use `BigInteger`. It is the fixed bit width and signed interpretation of the bit pattern that determine these outcomes.

## 8. Reading Binary and Hex Literals

Java supports base-2 literals with the `0b` prefix and base-16 literals with the `0x` prefix:

~~~java
int positive = 0b0000_0101; // 5.
int mask = 0xFF;           // 255.
byte minusOne = (byte) 0xFF; // -1, keeps the low 8 bits.
~~~

Underscores are purely for literal readability and do not change the value.

**Do not confuse the literal `0xFF` with `byte -1`**: without a cast, `0xFF` is the positive integer 255 of type `int`. When narrowed to `byte`, the low 8-bit pattern `11111111` is interpreted as **-1**.

Hex/binary `int` literals can express all 32 bits, so a literal such as `0x80000000` corresponds to the bit pattern of `Integer.MIN_VALUE`. Whether the same bit sequence represents a negative or positive value depends on **the bit width and signed/unsigned interpretation**.

## 9. In-Memory Data and Bit Patterns Are Not the Same Issue as Byte Order

**Two's complement** answers the question: *which bits represent a signed integer value?* **Endianness** (big-endian/little-endian) answers a different question: *when multiple bytes are stored or transmitted, which byte comes first?*

For example, a 32-bit `int` has the same arithmetic value and the same 32 bits, yet the ordering of its four bytes in a binary format must follow storage/transmission conventions. When reading files or protocols, you must explicitly select the byte order (for example via `ByteBuffer.order(...)`); do not infer endianness from seeing a negative number whose sign bit is 1.

## 10. Common Pitfalls

| Misconception | Correct understanding |
| --- | --- |
| "Negative numbers only differ from positive numbers in the sign bit." | Two's complement involves the **entire bit pattern**, not just flipping the leading bit |
| "`byte -1` becomes 255 when converted to `int`." | Signed widening performs **sign extension**, so it remains -1 |
| "`Integer.toBinaryString(negative byte)` prints 8 bits." | `byte` is promoted to `int`, typically printing 32 bits when negative |
| "`0xFF` is `byte -1` by default." | `0xFF` is 255 of type `int` |
| "`char` is 16 bits, so it is a signed integer type." | `char` is an **unsigned** UTF-16 code unit |
| "`>>` and `>>>` behave the same on negative numbers." | `>>` fills with the sign bit; `>>>` fills with 0 |
| "`1 << 32` evaluates to 0." | For `int`, the shift distance is masked; the result is 1 |
| "`-Integer.MIN_VALUE` always produces a positive number." | `int` overflows, so it remains `MIN_VALUE` |
| "Two's complement dictates the order of bytes in memory." | Endianness is a separate concern |

## 11. Self-Check Exercises

1. What is the 8-bit representation of `-1`?  
   *Answer:* `11111111`.
2. What signed value does the 8-bit sequence `11111011` represent? What unsigned value?  
   *Answer:* **-5** and **251**.
3. Why does `byte b = -1; int x = b;` produce `x = -1` instead of 255?  
   *Answer:* Sign extension occurs when widening a signed type to a wider type.
4. Write an expression to obtain the byte `-1` bit pattern as an unsigned `int` value 255.  
   *Answer:* `b & 0xFF` or `Byte.toUnsignedInt(b)`.
5. What are `-8 >> 1` and `-8 >>> 1` respectively?  
   *Answer:* **-4** and **2147483644**.
6. What is `1 << 32` with an `int` operand?  
   *Answer:* **1**, because the shift distance uses only the low 5 bits.
7. What is `~4` in `int`?  
   *Answer:* **-5**.
8. What does `Integer.MAX_VALUE + 1` produce?  
   *Answer:* **Integer.MIN_VALUE = -2147483648**, due to `int` overflow.
9. Given `short s = -1; char c = (char) 0xFFFF;`, how do `s` and `c` differ when converted to `int`?  
   *Answer:* `s` becomes **-1**, and `c` becomes **65535**.

## Checklist

- [ ] Know that `byte`, `short`, `int`, and `long` are **signed, two's complement** integer types of 8/16/32/64 bits.
- [ ] Can explain why the highest bit has a negative weight and why the pattern `111...111` equals -1.
- [ ] Understand how to form two's complement: invert bits and add 1 at a fixed width.
- [ ] Distinguish between **signed** and **unsigned** interpretations of the same bit pattern.
- [ ] Know that widening a negative `byte`/`short` to `int` performs **sign extension**.
- [ ] Use masks and `Byte.toUnsignedInt`/`Short.toUnsignedInt` when reading raw unsigned data.
- [ ] Distinguish `>>` (sign-preserving) from `>>>` (zero-filling) and understand numeric promotion.
- [ ] Recognize overflow, `Integer.MIN_VALUE`, and shift distance masking.
- [ ] Do not confuse two's complement with endianness.

**Conclusion:** Two's complement defines how Java interprets the bit patterns of signed integers. To use bitwise operators correctly, always track **type width**, **sign bit**, **widening/narrowing conversions**, and **bit-shift rules**, rather than guessing from printed strings of 0s and 1s alone.
