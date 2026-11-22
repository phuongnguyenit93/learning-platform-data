# BigInteger: Converting to `byte[]` and the Extra Sign Byte Issue

`java.math.BigInteger` represents arbitrary-precision signed integers. When needing to store or transmit numbers in binary form, the **`BigInteger.toByteArray()`** method returns a byte array, but **not an array of unsigned magnitude digits**. It is a **signed two's complement representation, in big-endian byte order, with the minimum length sufficient to include the sign**.

The most surprising consequence: a **positive** integer like `128` may require an extra leading `0x00` byte. This byte is **not a meaningless extra digit from an API bug**: it keeps the sign bit of the two's complement representation at 0.

```java
import java.math.BigInteger;
import java.util.Arrays;

BigInteger number = BigInteger.valueOf(128);
byte[] bytes = number.toByteArray();

System.out.println(Arrays.toString(bytes)); // [0, -128]
System.out.println(new BigInteger(bytes));  // 128
```

The array above consists of `0x00 0x80`. Because `byte` in Java is signed from `-128` to `127`, byte `0x80` prints as `-128` when using `Arrays.toString`. At the bit level, however, it is still `1000_0000`; placing byte `0x00` in front prevents positive 128 from being misread as −128.

This lesson explains signs, extra bytes, negative cases, reconstructing numbers from bytes, converting to unsigned or fixed-width formats, byte order, and testing round-trips in Java 17+.

## 1. Understand Three Concepts Before Writing Code

| Concept | Meaning | Example |
| --- | --- | --- |
| **Integer value** | Mathematical value of the `BigInteger` object | `128` |
| **Signed two's complement representation** | Bit sequence encoding negative/positive, with the highest bit of the entire representation as the sign bit | `00 80` for `+128`; `80` for `-128` |
| **Wire/protocol format** | Agreement between sender and receiver: signed or unsigned, big-endian or little-endian, fixed or minimal length | unsigned uint8 `80` also represents 128 |

Three perspectives can lead to **the same physical bytes yielding different values**. Given a single byte `0x80`:
- If decoded as **8-bit signed two's complement**, the value is **−128**.
- If decoded as **8-bit unsigned**, the value is **128**.

No API can deduce that meaning from a byte array alone. **Signedness, byte order, and width must be stated in the data contract**.

### `BigInteger` Is Immutable, but Byte Arrays Are Not

A `BigInteger` object has no in-place mutation operation. By contrast, `byte[]` is a mutable Java object:

```java
BigInteger value = BigInteger.valueOf(128);
byte[] exported = value.toByteArray();
exported[0] = 99;

// value is still 128: modifying the returned byte[] does not modify BigInteger.
```

Similarly, when passing a byte array as input, understand that the constructor reads its **contents** to create a value. A byte array held in your application does not become immutable simply because it was used to construct a `BigInteger`.

## 2. Exact Contract of `BigInteger.toByteArray()`

Signature in `java.math.BigInteger`:

```java
public byte[] toByteArray()
```

The result has these properties:
1. **Signed two's complement:** represents positive/negative values using two's complement, not a separate sign-only byte.
2. **Big-endian:** more significant bytes appear first.
3. **Minimal length:** requires **at least one sign bit** along with the bits needed to represent the value. The method takes no width parameter.
4. **Not fixed to 1/2/4/8 bytes:** result length varies by value.
5. **Zero does not produce an empty array:** `BigInteger.ZERO.toByteArray()` returns a one-byte array `00`.
6. **Can have a leading `00` byte for positive numbers**, when the high bit of the first magnitude byte is 1.
7. **Does not pick protocol length automatically:** if a protocol requires exact N bytes, the application must encode per that contract.

Hexadecimal representation, where each pair of characters is one byte:

```text
Value       BigInteger.toByteArray() hex
0            00
127          7f
128          00 80
255          00 ff
256          01 00
-1           ff
-128         80
-129         ff 7f
-255         ff 01
-256         ff 00
```

These are real results verified with Java. Do not confuse the hex column with the default output of `Arrays.toString(byte[])`: that method prints **signed decimal bytes**, e.g. `[0, -128]` instead of `00 80`.

## 3. Why Is 128 Two Bytes `00 80`?

Consider one byte, i.e., 8 bits:

```text
Hex byte         0x80
Binary bits      1000 0000
Signed 8-bit     -128
Unsigned 8-bit   +128
```

In signed two's complement, the highest bit of the entire representation is the sign bit. If only byte `80` is used, the high bit is 1 ⇒ in signed two's complement, the value is **−128**.

To express **+128**, we need a representation whose sign bit is 0:

```text
00          80
00000000    10000000
^
sign bit 0 of the entire 16-bit representation
```

Thus `BigInteger.valueOf(128).toByteArray()` is `00 80`. The leading `00` byte preserves the positive sign without changing the magnitude.

Similarly:
- `127` has the leading bit of byte `7f` equal to 0 ⇒ **one byte** suffices.
- `128` has magnitude byte `80`, leading bit equal to 1 ⇒ **two bytes** `00 80`.
- `255` has magnitude byte `ff`, leading bit equal to 1 ⇒ **two bytes** `00 ff`.
- `256` has hex `01 00`, leading bit of `01` equal to 0 ⇒ **two bytes** suffice, no third `00` byte added.

**Not every multi-byte positive number gets a `00` byte added.** The extra sign byte is needed only when the minimal magnitude representation, aligned on byte boundaries, has its leading high bit equal to 1.

### Boundary 127 → 128

```java
byte[] a = BigInteger.valueOf(127).toByteArray();
byte[] b = BigInteger.valueOf(128).toByteArray();

System.out.println(a.length); // 1
System.out.println(b.length); // 2
```

The value increases by just 1, yet the byte count jumps from 1 to 2. This is why **`toByteArray()` length should never be mechanically treated as unsigned data width**.

### Boundary `0x7fff` → `0x8000`

Positive 32767 can be represented as `7f ff`. Yet 32768 requires `00 80 00`: the first byte `80` of the magnitude has high bit 1, so `00` must be prepended. This principle occurs at **every 7-bit boundary of signed representation**, not uniquely at 128.

## 4. For Negative Numbers, How Does Two's Complement Work?

Negative numbers are encoded in **two's complement**. In a fixed-width bit field, one way to picture it is inverting all bits of the absolute value and adding 1. With `BigInteger`, width is not fixed; `toByteArray()` picks the **minimum** length to describe the signed number.

```text
-1    -> ff       (11111111)
-128  -> 80       (10000000)
-129  -> ff 7f    (11111111 01111111)
-255  -> ff 01
-256  -> ff 00
```

Why does `-128` fit in one byte while `-129` requires two?

- For 8-bit signed, the range is **−128 to +127**.
- `-128` fits in range, with representation `80`.
- `-129` falls outside range, requiring 16 bits. 16-bit two's complement of `-129` is `ff 7f`.
- The leading `ff` byte carries the necessary extended sign bits. Stripping it leaves `7f`, i.e., +127, **not** −129.

**Never strip all leading `0xFF` bytes from a negative array**. Sometimes `ff` is **essential** sign extension (as in `-129`). Only a codec aware of value, width, and two's complement can shorten or extend a representation while preserving the number.

### Sign Extension When Fixed Signed Length Is Needed

To place `-1` from one byte `ff` into a 4-byte signed field, sign-extend with `ff` bytes:

```text
Signed minimal -1:  ff
Signed 32-bit -1:   ff ff ff ff
```

Similarly, `+1` in a 32-bit signed representation is padded with `00`:

```text
Signed minimal +1: 01
Signed 32-bit +1:  00 00 00 01
```

Hence **negative signed padding** uses `FF`, not `00`. Unsigned padding follows non-negative protocol rules, normally `00` on the left in big-endian.

## 5. Constructor `new BigInteger(byte[])` Reads Signed Two's Complement

The constructor:

```java
BigInteger(byte[] val)
```

interprets the input array as a **signed integer** in big-endian two's complement, compatible with `toByteArray()`.

```java
byte[] negativeEncoding = {(byte) 0x80};
BigInteger a = new BigInteger(negativeEncoding);
System.out.println(a); // -128.
```

Using `00 80` instead of `80`:

```java
byte[] positiveEncoding = {0, (byte) 0x80};
BigInteger b = new BigInteger(positiveEncoding);
System.out.println(b); // 128.
```

Both arrays share the same low byte; they differ only in the **leading byte that determines the sign bit of the signed field**.

### Signed Round-Trip

For any valid `BigInteger` value, you can serialize and parse back with the matching pair:

```java
BigInteger original = new BigInteger("-129");
byte[] bytes = original.toByteArray();
BigInteger restored = new BigInteger(bytes);

System.out.println(original.equals(restored)); // true
```

This is a **numeric-value** round-trip, not a promise to preserve the byte length of an existing *non-minimal* signed input. For instance, the constructor accepts `00 00 80` as +128, whereas `toByteArray()` produces the minimal signed representation `00 80`.

**Warning:** an empty array does not represent 0 in this signed constructor; handle empty input per codec policy (in Java, the signed constructor on a zero-length byte array throws `NumberFormatException`).

## 6. Constructor `new BigInteger(signum, magnitude)` for Unsigned Magnitude

Another overload:

```java
BigInteger(int signum, byte[] magnitude)
```

allows passing a **separate sign** and an **unsigned magnitude array** in big-endian order. `signum` can only be `-1`, `0`, or `1`.

```java
byte[] oneByte = {(byte) 0x80};

BigInteger signed = new BigInteger(oneByte);
BigInteger unsignedMagnitude = new BigInteger(1, oneByte);

System.out.println(signed);            // -128
System.out.println(unsignedMagnitude); // 128
```

This is the right way to read **a single byte `80` as unsigned positive 128**. Instead of prepending `00` to the input array to "fix" the sign, it supplies sign +1 to the constructor.

Cases:
- `new BigInteger(1, bytes)`: non-negative magnitude; applies positive sign (unless magnitude is 0, giving 0).
- `new BigInteger(-1, bytes)`: negative value with the bytes' magnitude.
- `new BigInteger(0, bytes)`: valid only if magnitude is actually 0; `signum` 0 with nonzero magnitude is rejected.
- `signum` outside −1/0/1: invalid.

`new BigInteger(1, bytes)` is especially useful when a system receives an **unsigned big-endian byte string** as a positive number. Still, for fixed-length protocols, you must verify the byte count and expected range.

### A Single Byte `ff` Can Be −1 or +255

```java
byte[] ff = {(byte) 0xff};
System.out.println(new BigInteger(ff));    // -1
System.out.println(new BigInteger(1, ff)); // 255
```

You cannot tell the right answer from hex `ff` unless the schema defines signed vs. unsigned.

## 7. Why Does the Highest Bit of a Byte Affect Total Length?

The length of `toByteArray()` depends not only on the bit length of the **absolute magnitude**, but must also reserve **at least one sign bit** under signed two's complement.

Table of positive landmarks:

| Value | Minimal magnitude hex | `toByteArray()` hex | Length |
| ---: | --- | --- | ---: |
| 0 | `00` | `00` | 1 |
| 1 | `01` | `01` | 1 |
| 127 | `7f` | `7f` | 1 |
| 128 | `80` | `00 80` | 2 |
| 255 | `ff` | `00 ff` | 2 |
| 256 | `01 00` | `01 00` | 2 |
| 32767 | `7f ff` | `7f ff` | 2 |
| 32768 | `80 00` | `00 80 00` | 3 |
| 65535 | `ff ff` | `00 ff ff` | 3 |
| 65536 | `01 00 00` | `01 00 00` | 3 |

The table shows **an extra sign byte is not added every time magnitude width increases**. What matters is whether the high bit of the first byte in the magnitude representation would be mistaken for a negative sign bit.

### `bitLength()` Is Not Wire Byte Count

`BigInteger.bitLength()` describes bit length per the class definition (excluding the sign bit in minimal representation). It does not automatically translate into signed `toByteArray()` length or unsigned protocol length without understanding how to add sign bits and round up by bytes.

For **non-negative numbers**, minimal magnitude byte count is often computed by rounding up `bitLength/8`, with zero needing a separate policy. However, using `bitLength()` as a general codec while forgetting zero, negatives, sign bytes, and width limits easily creates boundary bugs. When actually outputting bytes, take `toByteArray()` and apply a checked **signedness policy**.

## 8. `BigInteger.toByteArray()` Is Not a Fixed-Width Unsigned Encoder

Suppose a protocol requires a **64-bit unsigned big-endian** field, exactly **8 bytes**. The maximum value is:

\[
2^{64}-1 = 18446744073709551615
\]

`BigInteger` can represent this value. However:

```java
BigInteger maxUnsigned64 =
        BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE);
byte[] signedBytes = maxUnsigned64.toByteArray();
```

`signedBytes` has **9 bytes**:

```text
00 ff ff ff ff ff ff ff ff
```

The `00` byte is the guard byte ensuring a positive number when read back with the signed constructor. In an **unsigned 64-bit** wire format, this case requires exactly **8 bytes**:

```text
ff ff ff ff ff ff ff ff
```

Sending all 9 bytes directly **violates the protocol length**. If the receiver reads those 8 bytes via `new BigInteger(bytes)`, it sees −1 instead of `2^64−1`.

**Right approach:** on the sender side, apply a **range-checked unsigned fixed-width codec**; on the receiver side, use `new BigInteger(1, bytes)` and validate length. Never change signedness merely by renaming variables.

### When Can the Leading `00` Byte Be Dropped?

Only when the **target format is unsigned magnitude** and you have confirmed the `00` byte is truly a **sign byte added for positive representation**, not a meaningful byte of a wider fixed-width field. To convert a **non-negative value** from `toByteArray` into minimal unsigned magnitude, you can strip **exactly one** leading `00` byte if the array has at least two bytes and the first byte is `00`.

```java
byte[] signed = value.toByteArray();
int offset = signed.length > 1 && signed[0] == 0 ? 1 : 0;
```

The condition `signed.length > 1` is vital: `BigInteger.ZERO.toByteArray()` is `00`. Deleting the lone zero byte leaves an empty array; the protocol must **explicitly specify** how zero is represented rather than letting that happen by accident.

Never write "strip all leading `00` bytes" if the protocol is fixed-width and leading zero bytes are valid padding that must remain.

## 9. Writing a Safe Unsigned Fixed-Width Codec

The method below requires:
- `value` must be **non-negative**.
- `length` is the **byte count of the wire field**, greater than 0.
- Value must fit in unsigned range `[0, 2^(8*length)-1]`.
- Output is **exactly `length` big-endian bytes**.
- If the value does not fit, **throw an exception rather than truncating high bits**.

```java
static byte[] toUnsignedFixed(BigInteger value, int length) {
    if (value.signum() < 0 || length <= 0) {
        throw new IllegalArgumentException(
                "requires nonnegative number and positive length");
    }

    byte[] encoded = value.toByteArray();
    int offset = encoded.length > 1 && encoded[0] == 0 ? 1 : 0;
    int count = encoded.length - offset;

    if (count > length) {
        throw new IllegalArgumentException("does not fit unsigned width");
    }

    byte[] out = new byte[length]; // Automatically zero-fills high bytes.
    System.arraycopy(encoded, offset, out, length - count, count);
    return out;
}
```

This is an **illustrative method**, to be placed in a class with `import java.math.BigInteger`.

### Why Is Range Checking Critical?

For `uint8`, there is exactly one byte; the range must be `0..255`.

```java
toUnsignedFixed(BigInteger.valueOf(255), 1); // ff
// toUnsignedFixed(BigInteger.valueOf(256), 1); // IllegalArgumentException.
```

If you silently take the low byte of 256, you send `00` and the receiver thinks the number is 0. This bug resembles out-of-range integer casting yet is harder to spot because the bytes still look valid.

### Decoding Unsigned Big-Endian

```java
byte[] wire = {(byte) 0xff};
BigInteger restored = new BigInteger(1, wire);
System.out.println(restored); // 255.
```

For **fixed-width**, validate `wire.length` equals the schema-specified byte count before parsing; `new BigInteger(1,bytes)` itself does not enforce a particular field length.

Round-trip comparison:

```java
BigInteger value = new BigInteger("18446744073709551615");
byte[] wire8 = toUnsignedFixed(value, 8);
BigInteger restored = new BigInteger(1, wire8);
System.out.println(value.equals(restored)); // true.
```

The 8-byte width here is part of the **schema**, not the natural length of `BigInteger.toByteArray()`.

## 10. Signed Fixed-Width Codec: Must Sign-Extend

If a protocol requires **16-bit signed big-endian** (2 bytes), the valid range is `−32768..32767`. You cannot just call `toByteArray()` and blindly zero-pad, because negative numbers need **`ff` padding** to preserve their sign.

Examples:
- `−129` has minimal signed `ff 7f`, fitting exactly in 2 bytes.
- `−1` has minimal signed `ff`, needing `ff ff` for 2-byte signed.
- `+128` has minimal signed `00 80`, fitting 2 bytes.
- `+32767` has `7f ff`, fitting 2 bytes.
- `+32768` does not fit 16-bit signed and must **fail**, not take the low two bytes `80 00` and turn into −32768.

An illustrative codec:

```java
static byte[] toSignedFixed(BigInteger value, int length) {
    // The 1000-byte limit is only an example quota, not a BigInteger rule.
    if (length <= 0 || length > 1000) {
        throw new IllegalArgumentException("invalid length");
    }

    int bits = length * 8;
    BigInteger limit = BigInteger.ONE.shiftLeft(bits - 1);
    BigInteger min = limit.negate();
    BigInteger max = limit.subtract(BigInteger.ONE);

    if (value.compareTo(min) < 0 || value.compareTo(max) > 0) {
        throw new IllegalArgumentException("does not fit signed width");
    }

    byte[] raw = value.toByteArray();
    byte[] out = new byte[length];
    Arrays.fill(out, value.signum() < 0 ? (byte) 0xff : 0);
    System.arraycopy(raw, 0, out, length - raw.length, raw.length);
    return out;
}
```

Requires `import java.util.Arrays;`. This method illustrates **big-endian** signed two's complement, applying signed range limits and appropriate sign padding. The `1000 byte` quota prevents absurd lengths or `int` overflow in width multiplication in this example. Real systems must choose quotas based on schema, needs, and actual resources.

When decoding signed:

```java
byte[] signedTwoBytes = {(byte) 0xff, (byte) 0x7f};
BigInteger n = new BigInteger(signedTwoBytes);
System.out.println(n); // -129.
```

If you tried `new BigInteger(1,signedTwoBytes)` on those same bytes, the result would be **positive** (653... depending on bytes); that **changes the protocol semantics** rather than being an alternate way to parse signed data.

## 11. Big-Endian Differs from Little-Endian

`BigInteger.toByteArray()` and the related byte-array constructors use **big-endian**. For example, positive 256:

```text
BigInteger.toByteArray() of +256:
01 00
^ high byte first
```

A little-endian protocol might expect `00 01`. If you send `01 00` and the receiver assumes little-endian, it may read 1 instead of 256 or another value depending on width.

**Do not simply reverse bytes without knowing signedness and width.** If using `toByteArray()`'s natural length, an extra sign byte alters how many bytes get reversed. For fixed-width protocols, usually:
1. Encode with the right **signed/unsigned width** in big-endian.
2. If the protocol is little-endian, reverse **the exact N bytes**.
3. On the receiving side, reverse the exact N bytes back and create `BigInteger` with the matching constructor.

`ByteBuffer` can be configured with `ByteOrder.LITTLE_ENDIAN` for 16/32/64-bit primitive reads/writes, yet `BigInteger` **has no** simple constructor taking `ByteOrder`. For arbitrary-size numbers, the codec must specify byte order explicitly.

### Do Not Confuse with Bit Order Inside Each Byte

Big-endian/little-endian describes **byte order**, and does not reverse bit order within individual bytes. Byte `80` still has bit pattern `1000_0000`, not `0000_0001`.

## 12. Important Cases When Handling Zero

`BigInteger.ZERO.toByteArray()` returns `00`, not an empty array.

```java
byte[] zero = BigInteger.ZERO.toByteArray();
System.out.println(zero.length); // 1.
System.out.println(zero[0]);     // 0.
```

In 4-byte fixed signed width, zero is `00 00 00 00`. The same holds in 4-byte fixed unsigned width. However, if a protocol defines zero magnitude as an **empty array**, you cannot infer that automatically from `toByteArray()`; an explicit special case is needed.

Likewise, `new BigInteger(new byte[]{0})` is 0. Never confuse `BigInteger.ZERO` with `null` (no object) or with "value absent" in a schema.

**Include dedicated tests for 0** because many "strip leading sign zero byte" functions accidentally turn zero into an empty array, causing decoding errors or exceptions.

## 13. Using `Arrays.toString`: Java `byte` Is Signed

`Arrays.toString(byte[])` prints elements as **signed `byte`s**, not unsigned hex:

```java
byte[] bytes = {0, (byte) 0x80, (byte) 0xff};
System.out.println(Arrays.toString(bytes)); // [0, -128, -1].
```

To inspect bytes in hex, iterate each byte and **mask `& 0xff`** before formatting:

```java
static String hex(byte[] bytes) {
    StringBuilder b = new StringBuilder();
    for (byte x : bytes) {
        if (b.length() > 0) {
            b.append(" ");
        }
        b.append(String.format(
                java.util.Locale.ROOT, "%02x", x & 0xff));
    }
    return b.toString();
}
```

This is a debugging/teaching helper, not the most optimal encoder for arbitrarily large byte arrays. `x & 0xff` converts the byte to an **unsigned 0..255 value** before formatting. Do not call `Integer.toHexString((int)x)` directly on a negative byte and be surprised by `ffffff80` from sign extension to `int`.

### When Printing a `BigInteger` Value in Hex

`big.toString(16)` represents the **signed value** (for instance, `-80` for −128), whereas `hex(big.toByteArray())` represents the **signed byte pattern** (for instance, `80` for −128). These are **two different questions**.

Example:

```java
BigInteger n = BigInteger.valueOf(-1);
System.out.println(n.toString(16));   // -1
System.out.println(hex(n.toByteArray())); // ff
```

Do not use the signed-value hex string as a substitute for protocol byte-stream hex.

## 14. Java 17+: Complete Runnable Program

Save as `ByteArraySignDemo.java`:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Locale;

public class ByteArraySignDemo {
    static String hex(byte[] bytes) {
        StringBuilder b = new StringBuilder();
        for (byte x : bytes) {
            if (b.length() > 0) {
                b.append(" ");
            }
            b.append(String.format(Locale.ROOT, "%02x", x & 0xff));
        }
        return b.toString();
    }

    static byte[] toUnsignedFixed(BigInteger n, int length) {
        if (n.signum() < 0 || length <= 0) {
            throw new IllegalArgumentException(
                    "requires nonnegative number and positive length");
        }
        byte[] encoded = n.toByteArray();
        int offset = encoded.length > 1 && encoded[0] == 0 ? 1 : 0;
        int count = encoded.length - offset;
        if (count > length) {
            throw new IllegalArgumentException("does not fit unsigned width");
        }
        byte[] out = new byte[length];
        System.arraycopy(encoded, offset, out, length - count, count);
        return out;
    }

    static byte[] toSignedFixed(BigInteger n, int length) {
        if (length <= 0 || length > 1000) {
            throw new IllegalArgumentException("invalid length");
        }
        int bits = length * 8;
        BigInteger limit = BigInteger.ONE.shiftLeft(bits - 1);
        if (n.compareTo(limit.negate()) < 0
                || n.compareTo(limit.subtract(BigInteger.ONE)) > 0) {
            throw new IllegalArgumentException("does not fit signed width");
        }
        byte[] raw = n.toByteArray();
        byte[] out = new byte[length];
        Arrays.fill(out, n.signum() < 0 ? (byte) 0xff : 0);
        System.arraycopy(raw, 0, out, length - raw.length, raw.length);
        return out;
    }

    public static void main(String[] args) {
        long[] values = {
                0, 127, 128, 255, 256, -1, -128, -129, -255, -256
        };
        for (long n : values) {
            BigInteger x = BigInteger.valueOf(n);
            byte[] b = x.toByteArray();
            System.out.println(n + " -> " + hex(b)
                    + " -> " + new BigInteger(b));
        }

        byte[] one = {(byte) 0x80};
        System.out.println("80 as signed: " + new BigInteger(one));
        System.out.println("80 as unsigned: " + new BigInteger(1, one));
        System.out.println("0080 as signed: "
                + new BigInteger(new byte[] {0, (byte) 0x80}));

        BigInteger max64 =
                BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE);
        System.out.println("2^64-1 signed bytes: "
                + hex(max64.toByteArray()));
        byte[] wire = toUnsignedFixed(max64, 8);
        System.out.println("2^64-1 unsigned 8 bytes: " + hex(wire));
        System.out.println("2^64-1 unsigned decoded: "
                + new BigInteger(1, wire));

        System.out.println("negative -129 signed 2 bytes: "
                + hex(toSignedFixed(BigInteger.valueOf(-129), 2)));
        System.out.println("signed 2 bytes decoded: "
                + new BigInteger(toSignedFixed(
                        BigInteger.valueOf(-129), 2)));

        try {
            toUnsignedFixed(BigInteger.valueOf(-1), 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative unsigned: rejected");
        }
        try {
            toUnsignedFixed(BigInteger.valueOf(256), 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("256 in uint8: rejected");
        }
        try {
            toSignedFixed(BigInteger.valueOf(128), 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("128 in int8: rejected");
        }

        System.out.println("signed zero bytes: "
                + hex(BigInteger.ZERO.toByteArray()));
        System.out.println("byte[] reused immutable? "
                + BigInteger.valueOf(128).equals(
                    new BigInteger(BigInteger.valueOf(128).toByteArray())));
    }
}
```

Compile and run commands:

```bash
javac --release 17 ByteArraySignDemo.java
java ByteArraySignDemo
```

Verified stdout:

```text
0 -> 00 -> 0
127 -> 7f -> 127
128 -> 00 80 -> 128
255 -> 00 ff -> 255
256 -> 01 00 -> 256
-1 -> ff -> -1
-128 -> 80 -> -128
-129 -> ff 7f -> -129
-255 -> ff 01 -> -255
-256 -> ff 00 -> -256
80 as signed: -128
80 as unsigned: 128
0080 as signed: 128
2^64-1 signed bytes: 00 ff ff ff ff ff ff ff ff
2^64-1 unsigned 8 bytes: ff ff ff ff ff ff ff ff
2^64-1 unsigned decoded: 18446744073709551615
negative -129 signed 2 bytes: ff 7f
signed 2 bytes decoded: -129
negative unsigned: rejected
256 in uint8: rejected
128 in int8: rejected
signed zero bytes: 00
byte[] reused immutable? true
```

The demo confirms minimal signed two's complement, extra `00` byte on positive numbers, signed vs. unsigned constructors, `FF` negative sign extension, range-checked fixed-width codecs, zero, and round-trip behavior. The example uses only types/methods available on Java 17+.

## 15. Decision Table: Which API to Use?

| Input/output contract | Appropriate approach | Warning |
| --- | --- | --- |
| Signed `BigInteger` round-trip as minimal bytes | `toByteArray()` ↔ `new BigInteger(bytes)` | Signed two's complement, big-endian, variable length |
| Read **unsigned** magnitude, big-endian | `new BigInteger(1, bytes)` | Validate schema length and range |
| Write **unsigned** magnitude, free length | `toByteArray()`, strip `00` sign byte conditionally | Zero needs clear policy |
| Write **unsigned N bytes** | Checked `toUnsignedFixed` codec | Non-negative, verify fit in N bytes, `00` padding |
| Write **signed N bytes** | Checked `toSignedFixed` codec | Signed range, negative sign extension `FF` |
| Read **signed N bytes** big-endian | Validate exact N bytes then `new BigInteger(bytes)` | Never strip sign byte arbitrarily |
| Read **unsigned N bytes** big-endian | Validate exact N bytes then `new BigInteger(1,bytes)` | Same bytes yield a different number if read signed |
| Little-endian protocol | Swap byte order after encoding to exact width | Do not reverse bits; do not forget sign byte |
| Need to log bytes in hex | `hex(bytes)` with `b & 0xff` | `Arrays.toString` prints signed decimal bytes |
| Need to display number in base 16 | `big.toString(16)` | Not equivalent to raw byte hex |
| Need math precision on decimal String data | `new BigInteger(decimalText)` | Do not parse through `double` |
| Need to send JSON / CSV | Text schema or structured data codec | Do not treat `byte[]` as text; usually needs base64/hex if schema requires |

### Real-World Scenario: 128-Bit IDs and Digests

Suppose a system sends an **unsigned 128-bit** identifier over the network in 16 big-endian bytes. Calling `BigInteger.toByteArray()` directly on an ID with its highest bit set produces **17 bytes** due to the extra `00` byte. A receiver expecting exact 16 bytes rejects the length.

Conversely, unconditionally taking the last 16 bytes of any `BigInteger` risks **truncating significant bits** of a value exceeding 128 bits. The right approach is validating `0 <= value < 2^128` and serializing **exact 16 unsigned bytes**.

**Distinguishing digests and numbers:** 16/32-byte hash values in many protocols are **byte strings** rather than signed integers. When exact preservation of all bytes including leading zeros is required, it is often better to **keep `byte[]`/`ByteBuffer` directly or use a byte-data wrapper**, rather than converting to `BigInteger` when arithmetic is unnecessary.

## 16. Common Mistakes and Fixes

| Mistake | Wrong outcome | Right approach |
| --- | --- | --- |
| Assuming `toByteArray()` returns unsigned magnitude | `128` becomes `00 80` instead of `80` | Understand signed two's complement; use unsigned codec when needed |
| Stripping all leading `00` bytes | Can lose valid padding and mishandle zero | Strip only extra sign byte per schema |
| Stripping all leading `FF` bytes on negative numbers | `-129` becomes `+127` | Sign extension depends on signed range |
| Using `new BigInteger(new byte[]{(byte)0x80})` to get 128 | Yields −128 | `new BigInteger(1, bytes)` |
| Using `new BigInteger(1,bytes)` on negative signed bytes | Yields large positive instead of negative | Signed constructor `new BigInteger(bytes)` |
| Sending `toByteArray()` into a `uint64` field | Can produce 9 bytes | 8-byte unsigned codec, range-checked |
| Truncating high bytes to fit a field | Silently alters value | Check fit before encoding |
| Padding negative numbers with `00` | Can corrupt sign or value | Pad `FF` for signed negatives |
| Not testing zero | Can turn `00` into an empty array | Define zero in schema |
| Confusing `Arrays.toString` with hex dump | Sees `-128` instead of `80` | Format bytes with `& 0xff` |
| Confusing `big.toString(16)` with `hex(big.toByteArray())` | Value hex differs from raw byte hex | Pick the intended meaning |
| Thinking `BigInteger` has configurable byte order | Constructor/`toByteArray` use big-endian | Codec swaps bytes for little-endian protocols |
| Using signed integer for hash byte strings | Loses length and leading-zero semantics | Keep raw bytes if arithmetic is not needed |
| Thinking every `BigInteger.toByteArray()` is 8 bytes for `long`-sized values | Length varies dynamically with value | Fixed-width codec per schema |
| Computing length as `bitLength()/8` without sign handling | Fails at 127/128 boundaries and 0 | Test boundaries and include sign rules |
| Using Java `byte` thinking it is unsigned | `(byte)0xff == -1` | Mask `& 0xff` when needing 0..255 |
| Failing to validate input byte array length | Receiver may accept schema-violating data | Verify exact N bytes before constructing `BigInteger` |

## 17. Test Suite and Self-Assessment Questions

### Minimal Boundary Tests

A proper codec should include test groups for:

1. **Zero:** `0` as minimal signed, fixed signed, fixed unsigned.
2. **Just below and above the byte sign bit:** `127`, `128`, `255`, `256`.
3. **Negative numbers near signed-byte boundaries:** `-1`, `-128`, `-129`, `-255`, `-256`.
4. **16-bit boundaries:** `32767`, `32768`, `-32768`, `-32769`.
5. **64-bit unsigned boundaries:** `2^64-1` (fits `uint64`), `2^64` (exceeds `uint64`).
6. **Unsigned domain:** reject negative numbers, reject values exceeding `8N` bits.
7. **Signed domain:** reject `128` in `int8`, accept `-128`, reject `-129` in `int8`.
8. **Width:** `N=1`, `N=2`, `N=8`; reject length 0 or negative.
9. **Byte order:** big-endian and little-endian must round-trip if the codec supports them.
10. **Byte count:** output exact N bytes when schema demands; never silently change N.
11. **Immutability:** modifying the returned `toByteArray()` array does not change the original `BigInteger`.
12. **Protocol integrity:** test arrays starting with `00` and bytes with high bit 1, ensuring no data loss.

### Self-Check Questions

1. Why does `BigInteger.valueOf(128).toByteArray()` return `00 80` instead of `80`?
2. What value do the two bytes `00 80` represent in big-endian signed? What does one byte `80` represent in signed vs. unsigned?
3. Why does `127` need only one byte, whereas `128` needs two bytes in `toByteArray()`?
4. Why is `BigInteger.valueOf(-128).toByteArray()` `80` while `-129` is `ff 7f`?
5. Why must we not strip all leading `ff` bytes from a negative array?
6. How do the contracts of `new BigInteger(bytes)` and `new BigInteger(1,bytes)` differ?
7. How long is `toByteArray()` for `2^64-1`? How many bytes are needed when transmitting `uint64`?
8. If a protocol requires signed 16-bit, what value range must you validate before encoding?
9. Why does `ff` padding for negative numbers differ from `00` padding for positive numbers?
10. Why does `BigInteger.ZERO.toByteArray()` return `00` instead of an empty array? What if a wire schema defines zero differently?
11. How do you ensure a byte-array round-trip preserves both **value** and **exact length N bytes**?
12. Why is the output of `Arrays.toString(new byte[]{(byte)0xff})` `[-1]`? How do you print hex `ff`?
13. Does `big.toString(16)` equal the hex dump of `big.toByteArray()` for all negative numbers?
14. Can a little-endian protocol use `toByteArray()` directly? Which codec steps are missing?
15. For a 16-byte digest/ID with leading zeros, should you automatically convert to `BigInteger`? When should the byte array be kept intact?

## 18. Official References

- [Java SE 17 — `BigInteger.toByteArray()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html#toByteArray()): describes the **big-endian two's complement** array, minimal length, and sign bit.
- [Java SE 17 — `BigInteger(byte[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html#%3Cinit%3E(byte%5B%5D)): constructor accepting signed two's complement representation.
- [Java SE 17 — `BigInteger(int,byte[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html#%3Cinit%3E(int,byte%5B%5D)): constructor accepting signum and big-endian magnitude.
- [Java SE 17 — `Arrays.toString(byte[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#toString(byte%5B%5D)): prints byte elements as signed values.
- [Java Language Specification `4.2.1 — Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): 8-bit signed `byte` type and Java integer ranges.

**Conclusion:** `BigInteger.toByteArray()` represents **signed** integers in **minimal-length big-endian two's complement**, so it can prepend `00` when a positive number's magnitude has its high bit equal to 1. For negative numbers, an `ff` byte can be **essential sign extension**. Never strip sign bytes or pad/truncate haphazardly: define the target format's **signedness, byte order, and fixed width**, validate ranges, and use the matching encoder/decoder pair to preserve both value and data length.