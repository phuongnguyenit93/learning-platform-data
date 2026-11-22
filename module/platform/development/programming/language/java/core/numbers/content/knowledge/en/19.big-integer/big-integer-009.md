# Bitwise Operations on Arbitrary-Length Integers with `BigInteger` in Java

`java.math.BigInteger` represents **arbitrary-precision integers**, rather than being fixed inside the 32 bits of `int` or 64 bits of `long`. Beyond addition, subtraction, multiplication, and division, this class provides **AND, OR, XOR, NOT, bit shifts, and individual bit operations**. These operations are useful when working with large status flags, bitsets, binary protocols, very large integer representations, and arithmetic algorithms.

However, there is a crucial difference: `BigInteger`'s bitwise operations behave **as if the value were stored in two's complement with infinitely extended virtual sign bits**. In particular, `not()` of a positive number returns a negative number, right-shifting a negative number preserves its sign, and `BigInteger` **has no unsigned right-shift operator `>>>`**. When a problem genuinely requires a fixed-width word of 8, 16, 32, or 256 bits, the developer must explicitly apply a **width-limiting mask**.

This lesson belongs to the **BigInteger** section in Java Core. Examples use Java 17+ and explain decimal values, binary bits, sign bits, exact results, and common traps.

## 1. Initializing `BigInteger` and Thinking Beyond Fixed Widths

`BigInteger` is an **immutable** class. Use the constructor taking a string and radix or `valueOf(long)`:

~~~java
import java.math.BigInteger;

BigInteger a = new BigInteger("101101", 2); // binary 101101 = 45
BigInteger b = new BigInteger("011110", 2); // binary 011110 = 30
BigInteger hex = new BigInteger("FF", 16);  // 255
BigInteger small = BigInteger.valueOf(45L);
~~~

Valid radixes are 2 through 36, and the string must follow the constructor's syntax. `new BigInteger("101101", 2)` is valid syntax, whereas `new BigInteger("0b101101", 2)` does not automatically accept a `0b` prefix. `toString(2)` yields the base-2 string representation, e.g., `"101101"` for positive 45.

A positive `BigInteger` can have thousands or millions of bits. Mathematically, bitwise operations remain defined on **two signed integers**, not on two fixed-size byte arrays. When needing to store as a packet or manipulate flags within a specific width, determine the width explicitly first.

**Key takeaway about negatives:** negative numbers are treated as having infinitely many leading 1 bits in two's complement representation. The number `-1` is pictured as `...11111111`, and `0` as `...00000000`. The ellipsis represents **virtual bits** of the mathematical model, not that the JVM actually allocates infinite memory.

## 2. AND, OR, XOR, and AND-NOT

With `a = 45` and `b = 30`:

~~~text
a = 101101₂  (45)
b = 011110₂  (30)
--------------
& = 001100₂  (12)
| = 111111₂  (63)
^ = 110011₂  (51)
~~~

Corresponding methods:

| Operation | BigInteger API | Bit-by-bit rule | Example result |
| --- | --- | --- | --- |
| AND | `a.and(b)` | 1 only when both bits are 1 | 12 |
| OR | `a.or(b)` | 1 when at least one bit is 1 | 63 |
| XOR | `a.xor(b)` | 1 when the two bits differ | 51 |
| AND NOT | `a.andNot(b)` | `a & ~b` | 33 |
| NOT | `a.not()` | Flips all bits under two's complement model | Depends on `a`; can be negative |

~~~java
BigInteger a = new BigInteger("101101", 2);
BigInteger b = new BigInteger("011110", 2);

BigInteger intersection = a.and(b); // 12
BigInteger combined = a.or(b);      // 63
BigInteger differences = a.xor(b);  // 51
BigInteger removed = a.andNot(b);   // 33
~~~

For bit flags, `and(mask)` is commonly used to extract selected bits; `or(mask)` sets a group of bits; `andNot(mask)` clears a group of bits; `xor(mask)` toggles a group of bits. These binary operations **do not mutate `a` or `b`**; they produce a new `BigInteger` result.

If the two operands have different lengths or different signs, `BigInteger` performs logic operations under the **sign-extended model** of both numbers. There is no need to pad 0s or 1s manually to match operand widths before calling `and`, `or`, and `xor`, unless the problem requires simulating a fixed-width bitvector.

## 3. NOT Is the Biggest Trap: `not()` Is Not N-Bit Inversion

In an **8-bit** bitvector, inverting the bits of `00000101₂` gives `11111010₂`, meaning **250 if viewed as unsigned**. However, `BigInteger.valueOf(5).not()` returns **-6**, not 250:

~~~java
BigInteger five = BigInteger.valueOf(5);
System.out.println(five.not()); // -6
~~~

Because the model is infinitely sign-extended two's complement, the mathematical identity holding for every integer `x` is:

~~~text
~x = -x - 1
~5 = -6
~-1 = 0
~~~

If you want **inversion within 8 bits**, build the mask `0xFF = 255` and keep only the low eight bits:

~~~java
BigInteger mask8 =
        BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE);
BigInteger inverted8 = five.not().and(mask8);
// inverted8 = 250 (binary 11111010 in 8 bits)
~~~

In general, for width `w > 0`, the mask is `2^w - 1`:

~~~java
static BigInteger mask(int width) {
    if (width <= 0) {
        throw new IllegalArgumentException("width must be positive");
    }
    return BigInteger.ONE.shiftLeft(width).subtract(BigInteger.ONE);
}
~~~

The method above is **only an illustrative snippet**, needing placement in a class and reasonable resource bounds on `width`. A very large `width` can consume heavy memory; arbitrary length does not mean unbounded execution cost.

With the same mask, `value.and(mask)` is also a way to obtain the **non-negative** remainder in `0..2^w-1` of a `w`-bit representation: `BigInteger.valueOf(-1).and(mask8)` returns 255. This is a **projection onto an unsigned `w`-bit bitvector**, not making the original negative integer disappear.

## 4. Left Shift and Right Shift: Sign Is Preserved Arithmetic-Style

`shiftLeft(n)` resembles `<<` and `shiftRight(n)` resembles `>>` for signed integers. Left-shifting by `n` bits normally multiplies the value by `2^n`; right-shifting by `n` bits corresponds to **taking the floor when dividing by `2^n`**, which matters greatly for negative numbers.

~~~java
BigInteger a = BigInteger.valueOf(45);
BigInteger left = a.shiftLeft(3);  // 360 = 45 * 8
BigInteger right = a.shiftRight(2); // 11 = floor(45 / 4)

BigInteger negative = BigInteger.valueOf(-3);
BigInteger arithmeticRight = negative.shiftRight(1); // -2
~~~

With `-3 >> 1`, the result is `-2` due to floor rounding in arithmetic shifts, **not `-1`** from Java integer division `-3 / 2`, which truncates toward 0.

Compared to primitive `int`/`long`, `BigInteger` has several differences:

- Shift distance `n` is not taken modulo 32/64 like primitive bit counts. For instance, `BigInteger.ONE.shiftLeft(32)` is `4294967296`, not wrapping back to 1.
- `BigInteger` allows **negative shift distances**: `shiftLeft(-2)` is equivalent to shifting right 2 bits; `shiftRight(-2)` is equivalent to shifting left 2 bits.
- Virtual sign bits are extended when right-shifting; `BigInteger.valueOf(-1).shiftRight(100)` remains `-1`.
- Left-shifting large numbers can allocate very large values/data blocks; bound bit counts per business and resource constraints.

Examples:

~~~java
BigInteger a = BigInteger.valueOf(45);
a.shiftLeft(-2);  // 11 (same direction as shiftRight(2))
a.shiftRight(-2); // 180 (same direction as shiftLeft(2))
~~~

**There is no `BigInteger.unsignedShiftRight` or `>>>` operator for `BigInteger`.** For a number with infinitely extended virtual 1 sign bits, "shifting 0s in from the left" is undefined without first picking a machine word width. To simulate unsigned right shift at width `w`, normalize with a mask and then call `shiftRight` on the non-negative value in `0..2^w-1`.

## 5. Nth-Bit Operations: `testBit`, `setBit`, `clearBit`, and `flipBit`

In single-bit APIs, **bit 0 is the least significant bit (LSB)**. For example, `45 = 101101₂` has bits 0, 2, 3, and 5 equal to 1.

| Method | Meaning |
| --- | --- |
| `testBit(n)` | Reads state of bit `n` (`boolean`) |
| `setBit(n)` | Returns a new number with bit `n` set to 1 |
| `clearBit(n)` | Returns a new number with bit `n` set to 0 |
| `flipBit(n)` | Returns a new number with bit `n` toggled |
| `getLowestSetBit()` | Returns index of lowest 1 bit; returns `-1` for 0 |

~~~java
BigInteger a = BigInteger.valueOf(45); // 101101₂
boolean bit3 = a.testBit(3);            // true
BigInteger withBit1 = a.setBit(1);      // 47
BigInteger withoutBit3 = a.clearBit(3); // 37
BigInteger flippedBit2 = a.flipBit(2);  // 41
~~~

`a` remains 45 after these calls because `BigInteger` is immutable. To keep the result, reassign: `a = a.setBit(1);`. The bit index must be a **non-negative** integer; `testBit(-1)`, `setBit(-1)`, `clearBit(-1)`, or `flipBit(-1)` throws `ArithmeticException`.

**For negative numbers**, testing bits far to the left can still return `true` due to sign extension:

~~~java
BigInteger minusOne = BigInteger.valueOf(-1);
boolean highBit = minusOne.testBit(100); // true
~~~

Do not infer that `minusOne` must physically store at least 101 bits. Those high bits are part of the **infinite two's complement model**.

## 6. `bitLength()`, `bitCount()`, and `getLowestSetBit()`

These three methods are **not interchangeable**:

- `bitLength()` returns the number of bits in the **minimal two's complement representation, excluding the sign bit**. For positive numbers, this matches ordinary binary length; for example, 256 needs 9 bits.
- `bitCount()` counts the number of bits in the two's complement representation that **differ from its sign bit**. For non-negative numbers, this is the count of 1 bits; for negative numbers, this is the finite count of 0 bits differing from the infinite trailing 1 sign bits.
- `getLowestSetBit()` returns the index of the lowest 1 bit, or `-1` if the value is 0.

~~~java
BigInteger a = BigInteger.valueOf(45); // 101101₂

a.bitLength(); // 6
a.bitCount();  // 4
BigInteger.valueOf(40).getLowestSetBit(); // 3
BigInteger.ZERO.getLowestSetBit();        // -1
~~~

Easily confused cases:

| Value | `bitLength()` | `bitCount()` | Why? |
| --- | ---: | ---: | --- |
| `0` | 0 | 0 | No 1 bits |
| `45` | 6 | 4 | `101101₂` has 6 bits, four 1 bits |
| `256` | 9 | 1 | `1` followed by eight 0 bits |
| `-1` | 0 | 0 | Virtual sign sequence `...111111`; no bits differ from sign |
| `-8` | 3 | 3 | Two's complement `...11111000`; three low 0 bits differ from sign |

Therefore **`bitLength(-1) == 0` does not mean -1 is 0 or has no 1 bits**. If an algorithm requires the bit length of an *unsigned* number or a protocol field's bit width, normalize to a non-negative number and apply that field's width definition.

## 7. Simulating a `w`-Bit Word with Masks: AND, NOT, Shift, and Rotate

When working with a **fixed-width** word/bitfield, first construct a mask and normalize:

~~~java
int width = 8;
BigInteger modulus = BigInteger.ONE.shiftLeft(width);
BigInteger mask = modulus.subtract(BigInteger.ONE);

BigInteger unsigned = BigInteger.valueOf(-1).and(mask); // 255
BigInteger inverted = BigInteger.valueOf(5).not().and(mask); // 250
BigInteger unsignedRight = unsigned.shiftRight(1); // 127
~~~

For a bounded non-negative input, `shiftRight` shifts 0s into the left because the value has no negative sign. **ANDing with the mask before shifting** is critical for negative inputs.

Example **8-bit rotate-left** of `0x81`:

~~~java
BigInteger mask8 =
        BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE);
BigInteger word = new BigInteger("10000001", 2); // 0x81 = 129

BigInteger rotated = word.shiftLeft(1).and(mask8)
        .or(word.shiftRight(7));
// rotated = 3 (binary 00000011)
~~~

This is a 1-bit rotate-left **implemented on an 8-bit bitvector**, not a built-in `BigInteger` rotate method. To rotate by an arbitrary distance `n`, first normalize `n` modulo `width`, reject invalid width 0 separately, and mask the result. When using bitvectors for protocols, specify **endianness when converting to bytes**, bit numbering, signedness, and width.

Another bit-field example is extracting the four bits at positions 4–7:

~~~java
BigInteger packetWord = new BigInteger("AB3", 16);
BigInteger fourBits = packetWord.shiftRight(4)
        .and(BigInteger.valueOf(15));
// fourBits = 11 (0xB)
~~~

If a word holds multiple fields at fixed offsets and widths, write a field-extraction helper with offset/width checks instead of scattering cryptic mask literals across the codebase.

## 8. `toByteArray()` and Signed/Unsigned Bytes

`BigInteger.toByteArray()` returns a **big-endian byte array in signed two's complement representation, including enough sign bits**. Hence a positive number whose first byte's high bit is 1 may need a leading `0x00` byte to avoid being interpreted as negative.

~~~java
BigInteger value = BigInteger.valueOf(255);
byte[] signedBytes = value.toByteArray();
// byte array: [0, -1] in Arrays.toString(...) output
~~~

In Java, `byte` is signed so byte `0xFF` prints as `-1` when printed as a `byte`. Two ways of building `BigInteger` from the same `0xFF` byte carry different meanings:

~~~java
byte[] raw = {(byte) 0xFF};

BigInteger signed = new BigInteger(raw);    // -1
BigInteger unsigned = new BigInteger(1, raw); // 255
~~~

The `new BigInteger(byte[])` constructor takes **signed two's complement**, while `new BigInteger(signum, magnitude)` takes **a separate sign and magnitude**, with `signum = 1` for positive. Never assume both raw-byte constructors mean the same thing.

`toByteArray()` does not return a **fixed-length unsigned** byte array. If a protocol requires exactly 16 or 32 bytes, you must:

1. Check whether the value fits the corresponding unsigned/signed range.
2. Confirm byte order (this API returns big-endian).
3. Check and strip any extra sign-guard 0 byte when **safe** and when the protocol expects unsigned magnitude.
4. Pad with `0x00` on the proper side to reach the required length, or convert to `width`-bit two's complement per the protocol spec.

Do not arbitrarily drop a leading byte just because it equals 0 if the protocol requires preserving length or uses a different signedness policy.

## 9. Complete Java 17+ Example and Execution Output

Save file `BigIntegerBitsDemo.java`:

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public class BigIntegerBitsDemo {
    public static void main(String[] args) {
        BigInteger a = new BigInteger("101101", 2);
        BigInteger b = new BigInteger("011110", 2);
        BigInteger mask8 =
                BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE);

        System.out.println("a = " + a);
        System.out.println("b = " + b);
        System.out.println("a & b = " + a.and(b));
        System.out.println("a | b = " + a.or(b));
        System.out.println("a ^ b = " + a.xor(b));
        System.out.println("a andNot b = " + a.andNot(b));
        System.out.println("not 5 = "
                + BigInteger.valueOf(5).not());
        System.out.println("not 5 in 8 bits = "
                + BigInteger.valueOf(5).not().and(mask8));

        System.out.println("a << 3 = " + a.shiftLeft(3));
        System.out.println("a >> 2 = " + a.shiftRight(2));
        System.out.println("-3 >> 1 = "
                + BigInteger.valueOf(-3).shiftRight(1));
        System.out.println("-1 testBit(100) = "
                + BigInteger.valueOf(-1).testBit(100));
        System.out.println("-1 & 255 = "
                + BigInteger.valueOf(-1).and(mask8));

        System.out.println("a testBit(3) = " + a.testBit(3));
        System.out.println("a setBit(1) = " + a.setBit(1));
        System.out.println("a clearBit(3) = " + a.clearBit(3));
        System.out.println("a flipBit(2) = " + a.flipBit(2));

        System.out.println("bitLength(256) = "
                + BigInteger.valueOf(256).bitLength());
        System.out.println("bitLength(-1) = "
                + BigInteger.valueOf(-1).bitLength());
        System.out.println("bitCount(a) = " + a.bitCount());
        System.out.println("bitCount(-1) = "
                + BigInteger.valueOf(-1).bitCount());
        System.out.println("lowest set bit(40) = "
                + BigInteger.valueOf(40).getLowestSetBit());
        System.out.println("a binary = " + a.toString(2));

        byte[] one = {(byte) 0xFF};
        System.out.println("from signed byte = "
                + new BigInteger(one));
        System.out.println("from unsigned byte = "
                + new BigInteger(1, one));
        System.out.println("255 bytes = "
                + Arrays.toString(BigInteger.valueOf(255).toByteArray()));

        BigInteger x = new BigInteger("10000001", 2);
        System.out.println("rotate left 8-bit 0x81 = "
                + x.shiftLeft(1).and(mask8).or(x.shiftRight(7)));
        System.out.println("a unchanged = " + a);
    }
}
~~~

Compile and run commands on Java 17+:

~~~bash
javac BigIntegerBitsDemo.java
java BigIntegerBitsDemo
~~~

Exact stdout:

~~~text
a = 45
b = 30
a & b = 12
a | b = 63
a ^ b = 51
a andNot b = 33
not 5 = -6
not 5 in 8 bits = 250
a << 3 = 360
a >> 2 = 11
-3 >> 1 = -2
-1 testBit(100) = true
-1 & 255 = 255
a testBit(3) = true
a setBit(1) = 47
a clearBit(3) = 37
a flipBit(2) = 41
bitLength(256) = 9
bitLength(-1) = 0
bitCount(a) = 4
bitCount(-1) = 0
lowest set bit(40) = 3
a binary = 101101
from signed byte = -1
from unsigned byte = 255
255 bytes = [0, -1]
rotate left 8-bit 0x81 = 3
a unchanged = 45
~~~

The first lines verify exact AND/OR/XOR/AND-NOT. The `not`, `shiftRight`, and `testBit(100)` lines demonstrate the **infinite two's complement model**, while the mask/rotate lines show how to return to the **8-bit bitvector** world. The last line proves `BigInteger` is immutable: bitwise results are produced anew without altering `a`.

## 10. Comparison with `int`, `long`, and `BitSet`

| Property | `int`/`long` | `BigInteger` | `java.util.BitSet` |
| --- | --- | --- | --- |
| Width | Fixed 32/64 bits | Scales with value | Flexible bitset |
| Sign semantics | Signed two's complement | Two's complement with virtual sign extension | Usually non-negative bit positions |
| Operator syntax | `&`, `|`, `^`, `~`, `<<`, `>>`, `>>>` | Methods `and`, `or`, `xor`, `not`, `shiftLeft`, `shiftRight` | `set`/`clear`/`flip`/`get` API and set operations |
| Unsigned right shift | Has `>>>` | Not directly available | Not a signed integer |
| Value after operation | Primitive value | New immutable object | `BitSet` typically mutates internal state |

**Choose `BigInteger`** when the main entity is a **large integer** needing both arithmetic and bitwise operations. **Choose `BitSet`** when the main entity is a **set of boolean positions**, needing to toggle many bits and wanting a data-structure API; `BitSet` has different semantics and mutability from `BigInteger`. **Choose `int`/`long`** when fixed width and overflow/unsigned shift behaviors are clearly specified.

Do not swap these types based on a gut feeling that "all of them hold bits": check signedness, size, immutability, output format, and high-bit semantics.

## 11. Performance, Memory, and Safety Traps

**Expandable length still has practical limits.** Evaluating `BigInteger.ONE.shiftLeft(1_000_000)` can build a very large number and allocate memory; accepting arbitrary user-supplied widths/bit indices without validation can exhaust resources. Java can throw exceptions for unsupported values/lengths or run out of resources.

**Not every bitwise operation is constant-time.** Operations on `BigInteger` generally depend on value/representation size. When using `BigInteger` for cryptography, you must consider **constant-time** requirements, timing leaks, and dedicated cryptographic libraries; side-channel safety cannot be inferred solely from arbitrary precision.

**Narrowing to primitives can lose bits.** `intValue()` and `longValue()` can drop high-order bits; if zero data loss is required, use `intValueExact()` or `longValueExact()` as appropriate and handle `ArithmeticException` when out of range.

**Do not use `bitLength()` as a security bound for unsigned raw bytes when negative numbers are still accepted.** Check `signum() >= 0` and verify the value falls within the format's range. For `w`-bit unsigned numbers, the range is typically `0 <= x < 2^w`; applying a mask to interpret/extract bits is different from **rejecting** out-of-range input.

**Do not roll `xor` as a secure encryption algorithm.** XOR is a basic bitwise operation, not by itself a secure cryptographic protocol. Encryption/hashing/signature verification require algorithms and libraries designed for those purposes.

## 12. Common Mistakes

1. **Assuming `BigInteger` has exactly 64 bits because it came from `long`.** It holds a numeric value and can grow in subsequent operations.
2. **Expecting `BigInteger.valueOf(5).not()` to return 250 like an 8-bit NOT.** `not()` means `~5 = -6`; to get 250, apply an 8-bit mask.
3. **Treating negative numbers as having a finite number of sign bits reported by `bitLength()`.** Virtual sign bits in two's complement extend infinitely.
4. **Calling `shiftRight` an unsigned right shift.** On negative numbers it is an arithmetic right shift preserving sign; there is no direct `>>>` on `BigInteger`.
5. **Assuming `BigInteger` shift distances are taken modulo 32/64.** Unlike primitives, `BigInteger` does not apply that shift-distance masking mechanism.
6. **Thinking `-3.shiftRight(1)` is -1 because integer division `-3/2` gives -1.** Negative right-shift uses floor rounding, yielding -2.
7. **Assuming `bitCount()` is always the finite count of 1 bits.** On negative numbers, it counts bits differing from the sign bit; `bitCount(-1) == 0`.
8. **Thinking `bitLength(-1) == 0` means the number has no 1 bits.** `-1` has virtual sign bits equal to 1; `bitLength` has a different definition.
9. **Forgetting to assign the result of `setBit`, `clearBit`, `flipBit`.** `BigInteger` is immutable; the original variable does not change.
10. **Using negative bit indices or unchecked input widths.** Negative indices throw `ArithmeticException`; huge indices can cause memory pressure.
11. **Treating `toByteArray()` as fixed-length unsigned bytes.** It returns big-endian signed two's complement, which may include a `0x00` sign byte.
12. **Confusing `new BigInteger(bytes)` with `new BigInteger(1, bytes)`.** For `0xFF`, the two produce -1 and 255.
13. **Using `toString(2)` expecting to see N two's complement bits of a negative number.** The base-2 string of a negative number shows a minus sign and magnitude, not a fixed `w`-bit pattern.
14. **Masking and assuming out-of-range input was validated.** Masking truncates high bits; if out-of-bounds data should fail, validate beforehand rather than silently discarding bits.

## 13. Practice Questions

**1.** Why does `BigInteger.valueOf(5).not()` return -6 instead of 250? How do you compute the 8-bit NOT of 5?

**Answer:** Under infinite two's complement, `~x = -x-1`. Use `BigInteger.valueOf(5).not().and(BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE))` to get 250.

**2.** Compute `BigInteger.valueOf(45).and(BigInteger.valueOf(30))`, `or`, and `xor`.

**Answer:** 12, 63, and 51 respectively; write both numbers in binary `101101` and `011110` to verify column by column.

**3.** What does `BigInteger.valueOf(-3).shiftRight(1)` return, and why does it differ from `-3 / 2` in Java?

**Answer:** -2, because arithmetic right-shift corresponds to taking the floor when dividing by 2, whereas Java integer division truncates toward 0.

**4.** Is `BigInteger.valueOf(-1).testBit(100)` true or false? Does that allocate a 101-bit array?

**Answer:** True because virtual 1 sign bits extend infinitely; it does not imply the physical object holds 101 bits.

**5.** What do `BigInteger.valueOf(-1).bitCount()` and `bitLength()` both give?

**Answer:** Both give 0 per the distinct definitions of the two methods. This is not the value 0.

**6.** With the same single-element byte array `0xFF`, why do `new BigInteger(bytes)` and `new BigInteger(1, bytes)` differ?

**Answer:** The first constructor reads signed two's complement (-1); the second reads a non-negative magnitude with positive signum (255).

**7.** Does `BigInteger` have a direct unsigned right shift like `>>>`? How do you perform one on a negative 8-bit word?

**Answer:** No. Pick width 8, apply mask `0xFF` to interpret the value into 0..255, and then call `shiftRight` on the non-negative number.

**8.** When must `intValueExact()` be used instead of `intValue()`?

**Answer:** When losing high-order bits is an error and you need to detect and reject `BigInteger` values exceeding the `int` range instead of silently truncating.

## References

- [Oracle Java SE 21 — BigInteger API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html): bitwise semantics, sign extension, negative shift distances, `bitCount`, `bitLength`, and `toByteArray`.
- [Java Language Specification `15.19 — Shift Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.19): primitive shift rules for comparison.
- [Java Language Specification `15.22 — Bitwise and Logical Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.22).
- [Oracle Java SE 21 — BitSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/BitSet.html): comparing bitset semantics and mutability with `BigInteger` integers.