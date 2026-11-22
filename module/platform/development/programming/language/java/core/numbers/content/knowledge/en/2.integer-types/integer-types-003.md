# Representing Negative Numbers with Two's Complement in Java

> **Java core – numbers · Integer Types**  
> **Goal:** Read bit patterns of negative integers; encode/decode two's complement manually; understand why Java shifts bits, sign-extends, and overflows the way it does; apply this correctly when handling bytes, masks, and binary data.

## 1. Why Represent Negative Numbers in Bits?

Computers store `0` and `1` bits. With the same 8 bits, the pattern `11111011` does not inherently mean “−5” or “251”: **the data type and interpretation convention** decide its meaning. Treated as an **unsigned** 8-bit integer, this pattern equals 251; treated as a **signed two's complement** integer, it equals −5.

Java uses two's complement representation for the signed integer types `byte`, `short`, `int`, and `long`. Thanks to this, the same binary adder circuit can handle both positive and negative numbers using arithmetic modulo a power of two. Two's complement also explains the bit patterns of negative numbers, how the sign propagates during widening, and the results of bit shifts.

This lesson covers only **fixed-width integers**. `float`/`double` follow IEEE 754 floating-point rules and do **not** represent their negative values using two's complement. `char` is an unsigned 16-bit UTF-16 code unit; it is not a signed negative integer type either.

## 2. Bit Width, Sign Bit, and Value Range

With **n bits**, there are exactly `2^n` distinct bit patterns. In two's complement:

- The leftmost bit (most significant bit, **MSB**) is the **sign bit**: `0` means non-negative; `1` means negative.
- The value range is **−2^(n−1) to 2^(n−1) − 1**. The most negative number is one greater in magnitude than the largest positive number because of the value `0`.
- The rightmost bit (least significant bit, **LSB**) is bit index `0`; bit indices increase from right to left.

| Java Type | Width | Value Range | Sign Bit |
| --- | ---: | --- | ---: |
| `byte` | 8 | −128 to 127 | 7 |
| `short` | 16 | −32,768 to 32,767 | 15 |
| `int` | 32 | −2,147,483,648 to 2,147,483,647 | 31 |
| `long` | 64 | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | 63 |

8-bit example:

```text
Bit index:      7 6 5 4 3 2 1 0
                ^             ^
             sign bit        LSB

 0000 0000 =    0
 0000 0001 =   +1
 0111 1111 = +127
 1000 0000 = -128
 1111 1110 =   -2
 1111 1111 =   -1
```

It is **not** “the first bit is the sign, and the remaining 7 bits are the magnitude”. That is a different representation called *sign–magnitude*. In two's complement, all 8 bits contribute to the value according to its specific rule; `1000 0000` is **−128**, not “−0”. Hence two's complement has a single unique representation for zero at a fixed width.

## 3. From Positive to Negative: Invert Bits Then Add 1

To find the representation of **−x** for `x > 0` where `x` fits within the valid range of the given width:

1. Write `+x` in **all n bits**, padding with `0` on the left if needed.
2. **Invert all n bits**: `0 ↔ 1` (one's complement).
3. **Add 1**, keeping the low n bits if a carry extends past n bits.

Example of `−5` in **8 bits**:

```text
 +5:                   0000 0101
 Invert each bit:      1111 1010
 Add 1:              + 0000 0001
                       ---------
 -5:                   1111 1011
```

The pattern `11111011` is `0xFB` in hexadecimal. Interpreted as **unsigned**, it equals `251`; interpreted as **signed two's complement**, it equals `−5`. Going from 251 to −5 here is **changing how the same 8-bit pattern is interpreted**, not changing the bits.

We can also see `2^8 − 5 = 256 − 5 = 251`. In general, for a negative number `−x` in n bits, the corresponding unsigned bit pattern is `2^n − x` (for `1 ≤ x ≤ 2^(n−1)`).

Example of `−13` in 8 bits:

```text
 +13:       0000 1101
 Invert:    1111 0010
 Add 1:     1111 0011   = 0xF3 = 243 if read unsigned
 Read signed: 243 - 256 = -13
```

**Be careful with width:** bitwise inversion using the `~` operator in Java on an `int` operates on 32 bits; to illustrate an 8-bit pattern, extract the low 8 bits with the mask `& 0xFF`. The “invert then add 1” method presented here applies to the **chosen width**, not automatically to however many digits happen to be printed on screen.

## 4. Decoding a Two's Complement Bit Pattern

Given an n-bit pattern, let `U` be its value if read as **unsigned** (0 to `2^n − 1`). The **signed** value `S` is:

```text
If sign bit = 0: S = U
If sign bit = 1: S = U - 2^n
```

8-bit example `1110 0111`:

- Unsigned: `128 + 64 + 32 + 4 + 2 + 1 = 231`.
- Sign bit = `1`, so signed: `231 − 256 = −25`.
- Reverse check: `+25 = 0001 1001`; invert `1110 0110`; add 1 to get `1110 0111`.

An equivalent method is the **negative weight on the highest bit** rule:

```text
For 8 bits:
b7 b6 b5 b4 b3 b2 b1 b0
 |
 └── weight -128, remaining bits have weights +64,+32,+16,+8,+4,+2,+1

1110 0111 = -128 + 64 + 32 + 4 + 2 + 1 = -25
```

Both decoding methods always produce the same value. The `U − 2^n` method is especially convenient when reading bytes from a file or network as unsigned values.

## 5. Why Can Addition, Subtraction, and Negation Use the Same Representation?

Addition and subtraction on fixed-width integers keep the **low n bits** of the result, equivalent to addition/subtraction **modulo `2^n`**. 8-bit example:

```text
    0000 0101  (+5)
  + 1111 1011  (-5)
  -----------
  1 0000 0000  (9 bits)
    0000 0000  (keep low 8 bits) = 0
```

That is why `x + (−x) = 0` at the bit-pattern level, even when the calculation temporarily produces a carry out of the width. In Java, `~x + 1` produces the same bit pattern as `-x` when `x` is an `int` (and similarly for `long`). Therefore:

```java
int x = 5;
int negative = ~x + 1; // -5
int bitwiseNot = ~x;   // -6; because ~x = -x - 1
```

However, a carry out of the width is **not** the sole criterion for **signed overflow**. For example, adding two positive 8-bit numbers `127 + 1` gives the pattern `1000 0000`, which is `−128` when interpreted as signed. The mathematical sum is 128, but 128 is outside the 8-bit signed range.

### When Does Overflow Occur?

For two signed numbers of the same width, addition overflows in signed arithmetic if **both operands have the same sign** yet the result has **the opposite sign**. In Java, ordinary `int` or `long` addition does not throw an error on overflow; the result keeps the low bits according to the type's width.

Special note for `byte`/`short`: in an expression like `(byte) (127 + 1)`, the addition `127 + 1` takes place in **`int`** and yields 128, and then the narrowing cast to `byte` takes the low 8 bits to produce `−128`. Thus you should not call this “direct 8-bit addition in Java”.

Use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, and `Math.negateExact` for `int`/`long` when you want to **detect overflow** via `ArithmeticException`. Use `BigInteger` if operations genuinely need integers larger than the `long` range.

## 6. Minimum Negative Value and Asymmetry

With 8 bits:

```text
 0111 1111 = +127   (MAX)
 1000 0000 = -128   (MIN)
```

There is no `+128` in `byte`. If you invert the bits of `1000 0000` and add 1 within 8 bits, you get `1000 0000` back: `−(−128)` has mathematical value +128, which does not fit in the representable range, so the bit pattern wraps back to −128.

Similarly:

```java
int min = Integer.MIN_VALUE;
System.out.println(min);             // -2147483648
System.out.println(-min);            // -2147483648 (overflow)
System.out.println(Math.abs(min));   // -2147483648 (still negative)
```

This is a **special boundary case**, not a general property that “negating a negative number always returns itself”. `Math.negateExact(Integer.MIN_VALUE)` throws `ArithmeticException` to signal that the corresponding positive value cannot be represented as an `int`.

If you need the corresponding positive value of `Integer.MIN_VALUE`, **widen first**: `long positive = -(long) Integer.MIN_VALUE;` gives `2147483648L`. For `Long.MIN_VALUE`, there is no larger primitive integer type than `long`; you can use `BigInteger.valueOf(Long.MIN_VALUE).negate()`.

## 7. Sign Extension on Type Conversion: Why Does `byte -5` Become `int -5`?

When converting a signed integer from a narrower type to a wider type, Java performs **sign extension**: it copies the sign bit into the newly added high bits to preserve the value.

```text
byte -5 (8-bit):   1111 1011

int -5 (32-bit):   1111 1111 1111 1111 1111 1111 1111 1011
                   ^^^^^^^^^^^^^^^^^^^^^^^^
                   new bits are all 1 because the original number is negative

Hex:
byte pattern:      FB
int -5:            FFFFFFFB
```

Example:

```java
byte signedByte = (byte) 0xFB; // -5
int signedInt = signedByte;    // -5, due to sign extension
int unsigned = signedByte & 0xFF; // 251, keeping the exact low 8 bits
int viaApi = Byte.toUnsignedInt(signedByte); // 251
```

**Mask `0xFF`** has its low eight bits set to 1. After `signedByte` is promoted to `int`, `& 0xFF` clears the upper 24 bits, preserves the byte pattern intact, and interprets it as a value in 0..255. This is a foundational operation when parsing binary protocols with **unsigned octets**.

Distinguish between:

- `byte → int`: **sign extension**, preserving the signed value.
- `byte & 0xFF`: **extracting the low 8 bits**, giving an unsigned interpretation.
- `int → byte`: **narrowing cast**, keeping only the low 8 bits and interpreting them in two's complement; high bits are discarded. For example, `(byte) 255 == -1`.
- `char → int`: converts the **unsigned** `char` code to a positive integer, without sign extension like a negative `short`. `char` and `short` are both 16 bits but have different interpretations.

## 8. Bit Shifting Negative Numbers: `>>` vs `>>>`

Shift operators work only on **bit patterns**, and then the Java type determines how the result is interpreted. Three key operators:

| Operator | Behavior | Common Meaning |
| --- | --- | --- |
| `<<` | Shift left, filling new low bits with `0`; high bits are discarded | Multiply by `2^k` within representable range; can overflow |
| `>>` | **Arithmetic** right shift, filling from the left with the sign bit | Preserves sign; for negative numbers, corresponds to dividing by `2^k` rounded toward −∞ |
| `>>>` | **Logical** right shift, filling from the left with `0` | Treats the bit pattern as unsigned at `int`/`long` width |

For `int x = -5`:

```text
x (int):  11111111 11111111 11111111 11111011   = -5
x >> 1:  11111111 11111111 11111111 11111101   = -3
x >>> 1: 01111111 11111111 11111111 11111101   = 2147483645
```

In Java, integer division `-5 / 2` returns **−2** because integer division truncates toward 0, whereas `-5 >> 1` returns **−3** (arithmetic right shift rounds toward −∞ for negative numbers). **Do not mechanically replace** `x / 2` with `x >> 1` if `x` can be negative.

Be careful with `byte`, `short`, and `char`: before performing `<<`, `>>`, or `>>>`, the left-hand operand is **promoted to `int`**. For example:

```java
byte b = -5;
int promotedShift = b >>> 1;        // 2147483645 (32-bit shift of -5)
int unsignedByteShift = (b & 0xFF) >>> 1; // 125 (shifts the unsigned byte value 251)
```

A detail about the shift distance: for `int`, only the low 5 bits of the shift count are used (effectively modulo 32); for `long`, it is the low 6 bits (modulo 64). Therefore `1 << 32` equals `1`, not 0; `1L << 32` produces a different result because the left operand is `long`.

## 9. Bitwise Operators and Hexadecimal When Reading Two's Complement

The operators `&` (AND), `|` (OR), `^` (XOR), and `~` (NOT) manipulate bits. Hexadecimal is convenient because **one hex digit corresponds to exactly 4 bits**.

```text
8-bit:     1111 1011  = 0xFB
32-bit:    11111111 11111111 11111111 11111011 = 0xFFFFFFFB

Java:
Integer.toHexString(-5)    -> "fffffffb"
Integer.toBinaryString(-5) -> 32 bit characters, starting with '1'
```

`Integer.toBinaryString` for negative numbers returns all 32 two's complement bits; for non-negative numbers it does not pad leading `0`s to reach 32 bits. `Long.toBinaryString` behaves similarly for 64 bits. When you want to print **exactly the low 8 bits**, use a mask and pad leading `0`s yourself.

**Note on hex literals:** `int raw = 0xFFFFFFFF;` carries a 32-bit pattern of all `1`s, read as `-1` when signed. If the same 32-bit pattern is interpreted as **unsigned**, the mathematical value is `4_294_967_295`; the `int` variable still holds the exact same bits.

The APIs `Integer.toUnsignedString(int)`, `Integer.toUnsignedLong(int)`, `Integer.parseUnsignedInt(String)`, and `Integer.compareUnsigned` handle the **unsigned interpretation** of 32 bits. Java has no separate `unsigned int` primitive; these APIs do not turn `int` into a new numeric type.

## 10. Standalone Runnable Java 17+ Program

Create the file **`TwosComplementDemo.java`** with the following full content:

```java
public class TwosComplementDemo {
    // Take the low 8 bits and pad with leading zeros to display all 8 bits.
    private static String bits8(int value) {
        String binary = Integer.toBinaryString(value & 0xFF);
        return String.format("%8s", binary).replace(' ', '0');
    }

    public static void main(String[] args) {
        byte minusFive = -5;

        System.out.println("+5   : " + bits8(5));
        System.out.println("~5+1 : " + bits8(~5 + 1));
        System.out.println("-5   : " + bits8(minusFive));

        System.out.println("signed byte: " + minusFive);
        System.out.println("unsigned byte: " + Byte.toUnsignedInt(minusFive));
        System.out.println("sign-extended int hex: "
                + Integer.toHexString(minusFive));

        System.out.println("-5 >> 1 = " + (-5 >> 1));
        System.out.println("-5 >>> 1 = " + (-5 >>> 1));
        System.out.println("8-bit unsigned >>> 1 = "
                + ((minusFive & 0xFF) >>> 1));

        System.out.println("(byte) 128 = " + (byte) 128);
        System.out.println("int MAX + 1 = " + (Integer.MAX_VALUE + 1));
        System.out.println("-int MIN = " + (-Integer.MIN_VALUE));
        System.out.println("unsigned int(-1) = "
                + Integer.toUnsignedString(-1));

        try {
            Math.negateExact(Integer.MIN_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("negateExact(MIN): overflow detected");
        }
    }
}
```

Run in the directory containing the file:

```bash
javac TwosComplementDemo.java
java TwosComplementDemo
```

**Expected output:**

```text
+5   : 00000101
~5+1 : 11111011
-5   : 11111011
signed byte: -5
unsigned byte: 251
sign-extended int hex: fffffffb
-5 >> 1 = -3
-5 >>> 1 = 2147483645
8-bit unsigned >>> 1 = 125
(byte) 128 = -128
int MAX + 1 = -2147483648
-int MIN = -2147483648
unsigned int(-1) = 4294967295
negateExact(MIN): overflow detected
```

**Reading the output mechanism by mechanism:**

1. `bits8(~5 + 1)` uses the `int` result and masks 8 bits; the final pattern `11111011` matches `byte -5`.
2. The same pattern `11111011` reads as `−5` as a signed byte, and as `251` as an unsigned byte.
3. When widened from a negative `byte` to `int`, the high bits are filled with `1`s; hence the hex display is `fffffffb`.
4. `>>` preserves the sign bit, while `>>>` fills `0`s across 32 bits; masking before shifting yields an 8-bit logical shift.
5. Casting `(byte) 128` returns `−128` because `128` has low bits `10000000`.
6. `int MAX + 1` and `-int MIN` both illustrate the 32-bit signed range; `negateExact` detects the second case.

## 11. Applying This When Reading Binary Data

Suppose a protocol specifies **an unsigned octet** containing a length 0..255. A byte with bits `1000 0001` stored in a Java `byte` will have the value `−127`, but the length according to the protocol is **129**.

```java
byte lengthOctet = (byte) 0x81;
int length = Byte.toUnsignedInt(lengthOctet); // 129
```

Conversely, if the protocol specifies an **8-bit signed two's complement** integer, the value `−127` is the correct one. No “convert to unsigned” rule is right for every dataset; you must read the **protocol specification**, determine bit-width and signedness, and only then interpret the bits.

When combining two octets into a 16-bit unsigned number in *big-endian* order:

```java
byte high = (byte) 0xAB;
byte low = (byte) 0xCD;
int unsigned16 = ((high & 0xFF) << 8) | (low & 0xFF);
// unsigned16 = 43981 (0xABCD)
```

Masking each `byte` **before** combining prevents negative sign bits from propagating into the upper bits. If `low` is not masked, ORing with the sign-extended `int` can corrupt many bits of the result. If you want to interpret `0xABCD` as a **16-bit signed** integer, the value will be `43981 − 65536 = −21555`; you can use `(short) unsigned16`.

## 12. Common Misconceptions and Self-Checks

| Misconception | What to Remember |
| --- | --- |
| The first bit is the sign, the rest is magnitude | That is sign–magnitude; two's complement decodes via negative MSB weight or `U−2^n` |
| `11111111` always equals −1 | Only when interpreted as **signed 8-bit**; as unsigned it is 255 |
| `~5` equals `−5` | `~5` is −6; `~5 + 1` is −5 |
| `int result = 127 + 1` produces `byte -128` | The `int` expression is 128; only narrowing to `byte` turns it into −128 |
| `-Integer.MIN_VALUE` produces a positive number | It overflows and still equals `Integer.MIN_VALUE` |
| `-5 >> 1` and `-5 / 2` are the same | Arithmetic right shift gives −3; integer division gives −2 |
| `byteValue >>> 1` shifts 8 bits | `byte` is promoted to `int` and shifted across **32 bits** |
| `Integer.toBinaryString(x)` always returns 32 characters | Non-negative numbers may omit leading `0`s |
| Java has a primitive `unsigned int` | No; use `int` and unsigned APIs to interpret 32-bit patterns |
| `double` also stores negative numbers in two's complement | `double` uses IEEE 754; this lesson covers only signed integers |

To handle bits correctly, always determine **three pieces of information** first: (1) width 8/16/32/64 bits, (2) signed or unsigned, and (3) whether the operation happens **before or after** promotion/cast. For binary operations, write out an example in binary or hex and verify the result with the right-width mask.

## 13. Self-Check Exercises

**Exercise 1.** Represent `−18` in 8-bit two's complement.  
**Exercise 2.** Interpret `1101 0000` as unsigned and signed 8-bit.  
**Exercise 3.** Predict the result of `(byte) 255` and `((byte) 255) & 0xFF`.  
**Exercise 4.** Why is `Integer.MIN_VALUE` a negative number with no corresponding positive value in `int`?  
**Exercise 5.** Explain why `byte b = -2; int x = b >>> 1;` is not equivalent to an 8-bit logical right shift of `11111110`.

**Answers and Explanations:**

1. `+18 = 0001 0010` → invert `1110 1101` → add 1 `1110 1110`, which is `0xEE`.
2. Unsigned: `0xD0 = 208`. Signed: `208 − 256 = −48`.
3. `(byte)255` keeps the low eight bits `1111 1111`, so it is `−1`; after masking `& 0xFF`, the result is `int 255`.
4. The `int` range is `−2^31 .. 2^31−1`, lacking `+2^31`. When negated in 32 bits, the bit pattern `1000...0000` maps back to itself; `Math.negateExact` detects the overflow.
5. `b` is promoted to `int -2` (32 bits with thirty-one `1`s and a final `0`); `>>> 1` yields `2147483647`. To shift the **8-bit** pattern as unsigned `254`, do `(b & 0xFF) >>> 1` to get `127`.

**Key takeaway:** Two's complement is a way to **interpret and compute fixed-width bit patterns**. Mastering the `U−2^n` rule, `invert bits + 1`, sign extension, and keeping low bits will help you explain most negative integer, cast, and bit-shift results in Java.
