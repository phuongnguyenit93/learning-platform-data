# `rotateLeft`, `rotateRight`, `reverse`, and `reverseBytes` in Java

## 1. What Problem Do These Four Bit Transformations Solve?

When working with integers at the bit level, we often need to rotate a sequence of bits circularly, reverse the order of individual bits, or swap the order of bytes. Java provides built-in static methods on **Integer** (32-bit) and **Long** (64-bit):

| Method | Meaning on a fixed-width bit sequence | Does it lose bits? |
| --- | --- | --- |
| **Integer.rotateLeft(x, distance)** / **Long.rotateLeft(x, distance)** | Rotates all bits left; bits exiting the left end wrap back to the right end | No |
| **Integer.rotateRight(x, distance)** / **Long.rotateRight(x, distance)** | Rotates all bits right; bits exiting the right end wrap back to the left end | No |
| **Integer.reverse(x)** / **Long.reverse(x)** | Reverses the order of **every bit** end to end | No |
| **Integer.reverseBytes(x)** / **Long.reverseBytes(x)** | Reverses the order of **bytes**, keeping the 8-bit order within each byte intact | No |

All of these are **value-returning** functions: they do not modify the passed-in variable. Each method preserves the count of `1` bits and `0` bits in the operand; what changes is the **positions** of those bits.

In Java, **int** is always 32 bits, **long** is always 64 bits, and both are **signed** in two's complement representation. Java has no primitive **unsigned int** or **unsigned long** types, yet these methods operate on the **bit pattern** regardless of sign interpretation. For example, **0x80000000** is a negative `int`, yet its highest bit still participates in rotations and reversals just like every other bit.

## 2. How Does Bit Rotation Differ from Bit Shifting?

Suppose we illustrate with only eight bits:

~~~text
Original value:      1000 0001
Left shift by 1:     0000 0010   (leftmost bit is discarded)
Rotate left by 1:    0000 0011   (leftmost bit wraps to the right)
Logical right by 1:  0100 0000   (rightmost bit is discarded)
Rotate right by 1:   1100 0000   (rightmost bit wraps to the left)
~~~

This 8-bit illustration is **not** the direct output of **Integer.rotateLeft** on `0x81`: **Integer** always rotates over **32 bits**. To rotate a single byte properly, custom code is needed as shown in section 6.

Three Java shift operators to distinguish:

- **<<**: left shift, discards bits shifted out, inserts `0` bits on the right.
- **>>**: arithmetic right shift, replicates the sign bit on the left.
- **>>>**: logical right shift, inserts `0` bits on the left.

Rotation feeds the shifted-out portion back into the opposite end so no information is lost. For a 32-bit width and rotation distance `d`, you can picture it as:

~~~text
rotateLeft(x, d)  = (x << d) | (x >>> (32 - d))
rotateRight(x, d) = (x >>> d) | (x << (32 - d))
~~~

This formula describes **d normalized to 0..31**; calling **Integer.rotateLeft/rotateRight** directly expresses intent more clearly and handles arbitrary rotation distances automatically. For **long**, the analogous formula uses 64 bits. In Java, shift distances for **int** use only the low 5 bits, and **long** uses only the low 6 bits; the illustrative formula does not replace understanding the actual operand width.

## 3. `rotateLeft` and `rotateRight`: Circular Rotation on 32/64 Bits

For **int**, the effective rotation distance is **distance modulo 32**; for **long**, it is **distance modulo 64**. Therefore:

- **Integer.rotateLeft(x, 40)** is equivalent to **Integer.rotateLeft(x, 8)**.
- **Integer.rotateLeft(x, -8)** is equivalent to **Integer.rotateRight(x, 8)**.
- Rotating by 0, 32, or a multiple of 32 on `int` returns the exact original bit pattern.
- For `long`, the wrap-around period is 64, not 32.

Negative rotation distances are valid: they rotate in the opposite direction. There is no need to take the absolute value manually before calling the method.

Example with the 32-bit pattern **0x12345678**:

~~~text
Original:           12 34 56 78
rotateLeft(x, 8):   34 56 78 12
rotateRight(x, 8):  78 12 34 56
~~~

Rotating by an exact multiple of 8 makes the byte groups look like they shifted positions, yet **rotateLeft/rotateRight** are still bit-level rotations across the entire sequence; the rotation distance does not have to be divisible by 8.

### Directly runnable Java 17+ example

Save as **BitTransforms.java**:

~~~java
public class BitTransforms {
    public static void main(String[] args) {
        int x = 0x12345678;

        System.out.printf("int x: %08X%n", x);
        System.out.printf("int left8: %08X%n", Integer.rotateLeft(x, 8));
        System.out.printf("int right8: %08X%n", Integer.rotateRight(x, 8));
        System.out.printf("int reverse: %08X%n", Integer.reverse(x));
        System.out.printf("int reverseBytes: %08X%n", Integer.reverseBytes(x));

        System.out.println("negative distance: "
                + (Integer.rotateLeft(x, -8) == Integer.rotateRight(x, 8)));
        System.out.println("distance modulo 32: "
                + (Integer.rotateLeft(x, 40) == Integer.rotateLeft(x, 8)));
        System.out.println("rotation round trip: "
                + (Integer.rotateRight(Integer.rotateLeft(x, 8), 8) == x));
        System.out.println("reverse round trip: "
                + (Integer.reverse(Integer.reverse(x)) == x));
        System.out.println("reverseBytes round trip: "
                + (Integer.reverseBytes(Integer.reverseBytes(x)) == x));

        System.out.printf("reverse(1) hex: %08X%n", Integer.reverse(1));
        System.out.println("reverse(1) signed: " + Integer.reverse(1));

        long y = 0x0123456789ABCDEFL;
        System.out.printf("long x: %016X%n", y);
        System.out.printf("long left8: %016X%n", Long.rotateLeft(y, 8));
        System.out.printf("long right8: %016X%n", Long.rotateRight(y, 8));
        System.out.printf("long reverse: %016X%n", Long.reverse(y));
        System.out.printf("long reverseBytes: %016X%n", Long.reverseBytes(y));
    }
}
~~~

Compile and run:

~~~bash
javac BitTransforms.java
java BitTransforms
~~~

Exact output (stdout):

~~~text
int x: 12345678
int left8: 34567812
int right8: 78123456
int reverse: 1E6A2C48
int reverseBytes: 78563412
negative distance: true
distance modulo 32: true
rotation round trip: true
reverse round trip: true
reverseBytes round trip: true
reverse(1) hex: 80000000
reverse(1) signed: -2147483648
long x: 0123456789ABCDEF
long left8: 23456789ABCDEF01
long right8: EF0123456789ABCD
long reverse: F7B3D591E6A2C480
long reverseBytes: EFCDAB8967452301
~~~

**%08X** formats an `int` as 8 zero-padded hex digits; **%016X** corresponds to 16 digits for `long`. This lets us compare the full **bit pattern**, even for negative numbers. The result of **Integer.reverse(1)** is **0x80000000**, whose signed decimal value is **-2147483648**; this does not mean `reverse` created or lost bits.

## 4. `reverse`: Reversing the Order of All Bits

**Integer.reverse(x)** maps the bit at position **i** (counting from the lowest bit, starting at 0) to position **31 - i**. **Long.reverse(x)** maps **i** to **63 - i**.

Visual illustration on a single byte:

~~~text
Original bits:  1101 0010
Reversed bits:  0100 1011
~~~

On `int`, reversal runs across **all 32 bits**; on `long`, across **64 bits**. The lowest bit of an `int` becomes the sign bit:

~~~text
Integer.reverse(0x00000001) = 0x80000000
Integer.reverse(0x80000000) = 0x00000001
~~~

**reverse** is symmetric: applying it twice restores the original bit pattern, i.e., **reverse(reverse(x)) == x**. It also preserves the number of `1` bits, though it generally **does not** preserve arithmetic value or sign.

Useful scenarios include normalizing bit order to a documented binary format, bitboard algorithms, protocol bit-order manipulation, or transformation steps in bit algorithms. Be sure to verify the format's **bit order**, because many formats specify **byte order** differently from **bit order**.

## 5. `reverseBytes`: Reversing Byte Order Without Reversing Bits Inside Bytes

One byte has 8 bits. **Integer.reverseBytes** swaps the four bytes of a 32-bit value as follows:

~~~text
Original (32 bits):
00010010 00110100 01010110 01111000
   12       34       56       78

reverseBytes:
01111000 01010110 00110100 00010010
   78       56       34       12
~~~

**Long.reverseBytes** does the same for the eight bytes of a `long`. Within each byte, the bit order remains unchanged. Therefore:

~~~text
Integer.reverseBytes(0x00000001) = 0x01000000
Integer.reverse(0x00000001)      = 0x80000000
~~~

The two results differ in both position and meaning. For **0x12345678**:

| Transformation | Hex Result | What Happened |
| --- | --- | --- |
| Original | **12345678** | Order of 4 bytes: 12 34 56 78 |
| **rotateLeft(x, 8)** | **34567812** | Circularly rotated 8 bits left |
| **rotateRight(x, 8)** | **78123456** | Circularly rotated 8 bits right |
| **reverse(x)** | **1E6A2C48** | Reversed all 32 bits |
| **reverseBytes(x)** | **78563412** | Reversed the order of the 4 bytes |

**reverseBytes(reverseBytes(x)) == x** because reversing byte order twice returns to the original state.

### Relation to endianness

**Big-endian** stores the most significant byte first; **little-endian** stores the least significant byte first. Reversing byte order can be useful when **converting the representation** of a value between the two byte-order conventions. However:

- **reverseBytes** only transforms an **`int`/`long` value**; it does not change the endianness of the CPU, JVM, byte arrays, or I/O streams.
- Do not blindly call **reverseBytes** every time you read or send network data. Check whether the protocol specification and the read/write API already handle endianness; swapping twice causes bugs.
- When working with byte arrays or buffers, **ByteBuffer.order(ByteOrder.BIG_ENDIAN / LITTLE_ENDIAN)** reads/writes in the desired endianness; that is usually more direct and expressive.
- **reverseBytes** does not replace **reverse** when bit-level reversal is required; **rotateRight(x, 8)** is also not an endianness swap because it circularly rotates bytes instead of reversing their full order.

## 6. Caution: Rotating a `byte` Differs from Rotating an `int`

For shift operators, Java applies **unary numeric promotion** separately to each operand: **byte**, **short**, and **char** on the left side are promoted to **int** before shifting. Passing a negative byte to a 32-bit method will not automatically perform an 8-bit rotation:

~~~java
byte b = (byte) 0x81;   // signed: -127
int promoted = b;       // 0xFFFFFF81 (sign extension)
int unsigned = b & 0xFF; // 0x00000081
~~~

Even after masking with **& 0xFF**, calling **Integer.rotateLeft(unsigned, 1)** still rotates **32 bits**, not 8 bits. To rotate within an 8-bit width, wrap overflowing bits back within **8 positions** and mask off bits outside the byte.

Standalone example, save as **ByteRotationDemo.java**:

~~~java
public class ByteRotationDemo {
    static int rotateLeft8(int rawByte, int distance) {
        int value = rawByte & 0xFF;
        int d = distance & 7;
        return ((value << d) | (value >>> (8 - d))) & 0xFF;
    }

    static int rotateRight8(int rawByte, int distance) {
        int value = rawByte & 0xFF;
        int d = distance & 7;
        return ((value >>> d) | (value << (8 - d))) & 0xFF;
    }

    public static void main(String[] args) {
        byte b = (byte) 0x81;

        System.out.printf("promoted: %08X%n", (int) b);
        System.out.printf("unsigned: %08X%n", b & 0xFF);
        System.out.printf("left8(81, 1): %02X%n", rotateLeft8(b, 1));
        System.out.printf("right8(81, 1): %02X%n", rotateRight8(b, 1));
        System.out.printf("Integer.rotateLeft(81, 1): %08X%n",
                Integer.rotateLeft(b & 0xFF, 1));
        System.out.println("8-bit round trip: "
                + (rotateRight8(rotateLeft8(b, 3), 3) == (b & 0xFF)));
    }
}
~~~

Run **javac ByteRotationDemo.java** then **java ByteRotationDemo**, stdout:

~~~text
promoted: FFFFFF81
unsigned: 00000081
left8(81, 1): 03
right8(81, 1): C0
Integer.rotateLeft(81, 1): 00000102
8-bit round trip: true
~~~

In the helper methods, **distance & 7** normalizes the step count modulo 8, including negative steps. **& 0xFF** restricts the result to 8 bits, preventing upper `int` bits from leaking into the byte value. If you need 16-bit transformations, design similarly with mask **0xFFFF** and modulo 16; do not confuse data width with `int` width.

## 7. Unsigned Numbers: Reading Results Correctly

Bit rotation and reversal methods do not distinguish signed from unsigned, yet when **displaying, comparing, or converting types**, you must pick the appropriate interpretation. For `int`:

~~~java
int bits = 0xFFFFFFFF;
System.out.println(bits);                          // -1
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.printf("%08X%n", bits);                  // FFFFFFFF
~~~

For `long`, **Long.toUnsignedString**, **Long.compareUnsigned**, **Long.divideUnsigned**, etc. are available for unsigned operations. However, **Integer.toUnsignedLong(x)** widens a 32-bit pattern to a non-negative 64-bit **long**; if you subsequently call **Long.rotateLeft**, the rotation takes place over **64 bits**. To rotate the original 32-bit pattern, call **Integer.rotateLeft** before widening.

To check the lowest bit or sign bit, you can use:

~~~java
int x = Integer.rotateLeft(1, 31);
boolean highBitSet = (x & 0x80000000) != 0; // true
boolean lowBitSet = (x & 1) != 0;          // false
~~~

Do not conclude a bit transformation is wrong just because the printed number is negative: **int/long** is merely a signed interpretation of the bit pattern. When analyzing data, print full-width hex or zero-padded binary representations.

## 8. Important Properties and Self-Verification

Let **ROL(x, d)** and **ROR(x, d)** denote the two rotations of the same width:

1. **ROR(ROL(x, d), d) == x** and **ROL(ROR(x, d), d) == x**.
2. **ROL(x, a + b) == ROL(ROL(x, a), b)**, with rotation distance arithmetic modulo the corresponding width.
3. **ROL(x, d) == ROR(x, -d)**, even when `d` exceeds the width.
4. **reverse(reverse(x)) == x**.
5. **reverseBytes(reverseBytes(x)) == x**.

These identities hold on the **bit patterns** even for negative numbers, zero, all-1 bits, and negative rotation distances. In Java, **==** directly compares `int`/`long` bit patterns because both sides share the same primitive type.

A few handy manual sanity checks:

~~~text
int 0x00000000: every transformation returns 0x00000000
int 0xFFFFFFFF: every rotation/reversal returns 0xFFFFFFFF
reverse(0x00000001):      0x80000000
reverseBytes(0x00000001): 0x01000000
rotateLeft(0x80000001,1): 0x00000003
rotateRight(0x80000001,1):0xC0000000
~~~

Rotations and reversals only **permute bit positions**, so they preserve the count of `1` bits. However, they are not the same permutation and are not interchangeable. **Integer.bitCount(x)** or **Long.bitCount(x)** can be used to verify `1`-bit count preservation if needed.

## 9. Practical Applications and Limitations

- **Hashing and bit mixing:** rotation is often combined with XOR, modular addition, or other operations to diffuse information across bit positions. Bit rotation alone does **not** make a good hash function and provides **no** cryptographic security.
- **Protocols/binary formats:** **reverseBytes** is useful when representing a value in the opposite byte order; **reverse** fits when a specification requires reversing bit order. Read the specification carefully to confirm whether the unit is **bit** or **byte**.
- **Bit-manipulation algorithms:** reorienting bitmasks, processing bitmaps/bitboards, reversing bit positions, or testing fixed-width binary data structures.
- **Data recovery:** reversals and rotations have clear inverses, making them convenient for algorithms requiring reversible transformations; they **do not securely encrypt** data.

For performance, prefer the standard methods on **Integer/Long**: clear semantics, fewer sign/shift-distance bugs, and platform-level JDK optimizations. Do not claim they always compile to a single CPU instruction or are always faster than every manual implementation; that depends on the JVM, hardware, and context.

## 10. Common Mistakes to Avoid

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Using **>>** instead of **>>>** when emulating right rotation | **>>** extends the sign bit, corrupting the combined bits | Use the standard method or logical shift **>>>** |
| Thinking **Integer.rotateLeft** rotates exactly 8 bits for a byte input | The method always operates on 32 bits | Write an 8-bit rotate helper and mask with **& 0xFF** |
| Confusing **reverse** with **reverseBytes** | One reverses every bit; the other reverses only bytes | Draw 8-bit groups and compare against the specification |
| Treating **rotateRight(x, 8)** as an endianness swap | Circular rotation differs from reversing byte order | Use **reverseBytes** when a byte swap is actually needed |
| Assuming a negative result is an error | The highest bit of `int`/`long` is the sign bit | Print full-width hex or format as unsigned |
| Manually applying **% 32** and assuming negative cases turn positive | Java's **%** operator can return negative values | Call **rotateLeft/Right** directly, or normalize properly |
| Mixing **Integer** and **Long** | Rotation width changes from 32 to 64 bits | Pick the method matching the format's bit width |
| Swapping byte order twice | Restores original value, corrupting transmitted data | Convert only at verified boundaries |

### Self-Practice Questions

1. For **int x = 1**, why is **Integer.rotateLeft(x, 1) == 2**, whereas **Integer.reverse(x) == 0x80000000**?
2. For **0x12345678**, explain why **rotateRight(x, 8) = 0x78123456** while **reverseBytes(x) = 0x78563412**.
3. Why is **Integer.rotateLeft(x, 40) == Integer.rotateLeft(x, 8)**, whereas you cannot draw the same conclusion for **Long.rotateLeft**?
4. For a byte **0x81**, predict the 1-bit left and right rotations in **8 bits**, then run **ByteRotationDemo** to verify.
5. If a protocol requires little-endian, which step when writing with **ByteBuffer** should specify byte order? Would also calling **reverseBytes** still be right?

Understanding the three concepts of **bit width**, **bit order**, and **byte order** will help you pick the right transformation and avoid subtle binary bugs that are invisible when printing only decimal numbers.