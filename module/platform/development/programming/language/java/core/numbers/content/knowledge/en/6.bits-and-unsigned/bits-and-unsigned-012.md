# Distinguishing Numeric Value from Byte Order When Exchanging Data in Java

An integer has its own **value**, for example `0x1234_5678` (decimal `305_419_896`). Yet when sending that number over a network or saving it to a binary file, both sides must agree on **how to turn the value into bytes** and **the order in which those bytes are arranged**. If the writer uses big-endian while the reader treats the data as little-endian, the exact same four bytes can be decoded into a completely different value.

This lesson belongs to the topic **Bits and Unsigned Numbers**: we must separate three concepts—**numeric value**, **fixed-width bit pattern**, and **byte order (endianness)**. Only then should we consider how Java interprets that bit pattern as a signed `int`, `long`, or an unsigned value.

## 1. One Numeric Value, Multiple Representations

In source code, the same value can be written in multiple radices:

```java
int decimal = 305_419_896;
int hexadecimal = 0x1234_5678;
int binary = 0b0001_0010_0011_0100_0101_0110_0111_1000;
// All three variables hold the same int value.
```

These are three illustrative declarations that can be placed inside a Java method. The `0x` prefix is a **literal syntax** in source code, not a byte automatically sent over the wire; `_` only improves readability. The number `0x1234_5678` has a 32-bit pattern split into four eight-bit groups:

```text
Hex:    12       34       56       78
Bit:  00010010 00110100 01010110 01111000
Byte:     1        2        3        4
```

Since one hex digit corresponds to 4 bits, **two hex digits correspond to one byte**. Those are only the logical byte groups of the number; when exchanging data, we must also decide **which byte appears first**.

Do not confuse:

- **Radix**: how humans write/read a value in decimal, binary, or hex.
- **Bit width**: how many bits represent it, such as 32-bit `int` or 64-bit `long`.
- **Signed/unsigned**: how the bit pattern is interpreted as a numeric value, especially when the highest bit is set.
- **Byte order**: the sequence in which the bytes of **a multi-byte value** are placed into a byte stream in a file, packet, or buffer.

## 2. Big-Endian and Little-Endian

For the 32-bit value `0x12345678`:

| Order | Byte at offset 0 | Offset 1 | Offset 2 | Offset 3 |
| --- | --- | --- | --- | --- |
| **Big-endian** | `12` | `34` | `56` | `78` |
| **Little-endian** | `78` | `56` | `34` | `12` |

**Big-endian** places the **most significant byte (MSB)** first. **Little-endian** places the **least significant byte (LSB)** first. In the example, `0x12` holds the most significant bits, and `0x78` holds the least significant bits.

Visualizing both sides:

```text
Logical value: 0x12345678

Big-endian:
offset       0    1    2    3
bytes       12   34   56   78

Little-endian:
offset       0    1    2    3
bytes       78   56   34   12
```

**Bit order inside each byte is not reversed.** Byte `0x12` remains `00010010` in both forms; the difference lies in the placement of bytes in the sequence. There is no "moving sign bit" caused by endianness: the sign-bearing bit belongs to the bit position of the 32/64-bit integer **after the bytes have been properly assembled**.

For a **single byte**, there is no byte-order difference. Endianness only matters when converting a multi-byte value into a byte sequence or vice versa.

## 3. Reading in the Wrong Order Changes the Number, Even Though the Bytes Did Not Change

Suppose four consecutive bytes are received:

```text
12 34 56 78
```

If the specification prescribes big-endian, the value is `0x12345678` = `305419896`. If **those exact four bytes** are read as little-endian, you get `0x78563412` = `2018915346`.

With bytes `b0`–`b3` interpreted as **unsigned values 0..255**, the decoding formulas are:

```text
Big-endian:
value = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3

Little-endian:
value = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
```

These are logical formulas over four byte values **already converted to unsigned**. In Java, be careful to promote/mask before shifting so unintended sign extension does not occur; the practical section below shows how to do this safely.

If two communicating endpoints disagree on endianness, the program can still run and receive all four bytes, yet **silently** produce the wrong value. That is a protocol bug, not an addition bug or packet loss.

## 4. `int` in Java Is Signed, Yet Exchanged Data Can Be Unsigned

Java `int` has **32 signed bits**, range `-2_147_483_648` to `2_147_483_647`. Some protocols define an **unsigned 32-bit** field, range `0` to `4_294_967_295`. Both ranges use **four bytes**; the difference is how the bits are interpreted after assembling the bytes.

Example with bit pattern `0xFEDCBA98`:

```text
32-bit pattern:            FE DC BA 98
Signed int value:          -19088744
Unsigned 32-bit value:     4275878552
```

If a Java receiver uses `ByteBuffer.getInt()`, the resulting `int` is `-19088744`. This **does not prove the data has the wrong byte order**: the 32-bit pattern is still `FEDCBA98`. When the protocol requires unsigned 32-bit, switch the interpretation using:

```java
int raw = 0xFEDC_BA98;
long unsigned = Integer.toUnsignedLong(raw); // 4275878552L
```

This is an illustrative snippet inside a method. `Integer.toUnsignedLong` zero-extends to preserve the exact **unsigned** 32-bit value as a `long`, rather than sign-extending. `Integer.toUnsignedString(raw)` can format the result as a string.

Avoid concluding "negative number means wrong endianness": **signedness and endianness are independent**. Always verify byte order first, and only then interpret the bit pattern according to the signed/unsigned contract.

## 5. Java `byte` Is Signed: Mask with `0xFF` Before Combining

A byte on the wire is often described in protocol docs as `0x00`–`0xFF` (0–255). However, Java's `byte` type is **8-bit signed**, ranging from -128 to 127. Example:

```java
byte b = (byte) 0xFE;
int signed = b;                 // -2: sign-extended to int.
int unsigned = b & 0xFF;        // 254: keeps low eight bits.
int alsoUnsigned = Byte.toUnsignedInt(b); // 254.
```

When `byte` is promoted to `int` for left shifting, if it is negative it can introduce extended `1` bits in the upper positions. Therefore, normalize each byte with `& 0xFF` or `Byte.toUnsignedInt` **before combining**.

A safe method to read an unsigned 32-bit big-endian value:

```java
static long readUnsigned32BigEndian(byte[] bytes) {
    if (bytes.length != 4) {
        throw new IllegalArgumentException("expected exactly four bytes");
    }
    return ((long) (bytes[0] & 0xFF) << 24)
            | ((long) (bytes[1] & 0xFF) << 16)
            | ((long) (bytes[2] & 0xFF) << 8)
            | (bytes[3] & 0xFFL);
}
```

This is a **method inside a Java class**, not a standalone program. Each byte is converted to 0–255, assembled in big-endian order, and stored in a `long` so the unsigned 32-bit result is always non-negative and does not overflow signed `int`. Avoid `return (bytes[0] << 24) | ...` without masking bytes: Java sign-extends negative `byte`s to `int`.

## 6. Java `ByteBuffer`: Writing and Reading in Agreed Byte Order

In `java.nio`, `ByteBuffer` supports configuring `ByteOrder.BIG_ENDIAN` and `ByteOrder.LITTLE_ENDIAN`:

```java
int value = 0x1234_5678;
byte[] bigEndian = java.nio.ByteBuffer.allocate(4)
        .order(java.nio.ByteOrder.BIG_ENDIAN)
        .putInt(value)
        .array();

byte[] littleEndian = java.nio.ByteBuffer.allocate(4)
        .order(java.nio.ByteOrder.LITTLE_ENDIAN)
        .putInt(value)
        .array();
```

The two byte arrays contain `12 34 56 78` and `78 56 34 12`, respectively. **`value` does not change.** `ByteBuffer.putInt` decides how to split the 32-bit pattern into 4 bytes based on the buffer's byte order.

When reading, you must set the same `ByteOrder` per the **data contract**:

```java
int fromBig = java.nio.ByteBuffer.wrap(bigEndian)
        .order(java.nio.ByteOrder.BIG_ENDIAN)
        .getInt(); // 0x12345678

int fromLittle = java.nio.ByteBuffer.wrap(littleEndian)
        .order(java.nio.ByteOrder.LITTLE_ENDIAN)
        .getInt(); // 0x12345678
```

A newly created `ByteBuffer` has a **default order of `BIG_ENDIAN`**. However, do not blindly rely on the default when designing protocols: call `.order(...)` explicitly to state the contract and avoid misinterpretation.

`putInt`/`getInt` handle **exactly four bytes**; `putShort`/`getShort` handle two bytes; `putLong`/`getLong` handle eight bytes. `put`/`get` for **a single byte** are unaffected by endianness. With `ByteBuffer.allocate(4)`, `.putInt(...)` advances the position to 4; `.array()` retrieves the backing array. If switching from writing to reading on the **same buffer**, you generally need to call `flip()` before `getInt()`. In the `wrap(byte[])` example, the new buffer starts at position = 0 so it can be read immediately.

Note that a `ByteBuffer` can be direct or read-only and may not always have an accessible backing array via `.array()`; this example uses a heap buffer from `allocate(4)` which has a backing array. In real applications, write to a `ByteBuffer` and transfer its bytes via I/O APIs instead of assuming `.array()` is always callable.

## 7. Complete Java 17+ Example: Same Number, Two Byte Orders

Create the file **`ByteOrderDemo.java`** with the following code:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class ByteOrderDemo {
    static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte b : bytes) {
            if (out.length() > 0) {
                out.append(' ');
            }
            out.append(String.format("%02X", Byte.toUnsignedInt(b)));
        }
        return out.toString();
    }

    static long readUnsigned32BigEndian(byte[] bytes) {
        if (bytes.length != 4) {
            throw new IllegalArgumentException("expected exactly four bytes");
        }
        return ((long) (bytes[0] & 0xFF) << 24)
                | ((long) (bytes[1] & 0xFF) << 16)
                | ((long) (bytes[2] & 0xFF) << 8)
                | (bytes[3] & 0xFFL);
    }

    public static void main(String[] args) {
        int number = 0x1234_5678;
        byte[] big = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN)
                .putInt(number)
                .array();
        byte[] little = ByteBuffer.allocate(4)
                .order(ByteOrder.LITTLE_ENDIAN)
                .putInt(number)
                .array();

        System.out.println("value=" + String.format("0x%08X", number));
        System.out.println("bigEndian=" + hex(big));
        System.out.println("littleEndian=" + hex(little));
        System.out.println("readBE=" + String.format("0x%08X",
                ByteBuffer.wrap(big).order(ByteOrder.BIG_ENDIAN).getInt()));
        System.out.println("readLE=" + String.format("0x%08X",
                ByteBuffer.wrap(little).order(ByteOrder.LITTLE_ENDIAN).getInt()));
        System.out.println("wrongOrder=" + String.format("0x%08X",
                ByteBuffer.wrap(big).order(ByteOrder.LITTLE_ENDIAN).getInt()));

        int rawBits = 0xFEDC_BA98;
        byte[] payload = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN)
                .putInt(rawBits)
                .array();
        int decoded = ByteBuffer.wrap(payload)
                .order(ByteOrder.BIG_ENDIAN)
                .getInt();
        System.out.println("signedInt=" + decoded);
        System.out.println("unsignedInt=" + Integer.toUnsignedLong(decoded));
        System.out.println("wireBytes=" + hex(payload));
        System.out.println("manualUnsigned=" + readUnsigned32BigEndian(payload));

        byte signedByte = (byte) 0xFE;
        System.out.println("signedByte=" + signedByte);
        System.out.println("unsignedByte=" + Byte.toUnsignedInt(signedByte));
    }
}
```

Run from the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 ByteOrderDemo.java
java ByteOrderDemo
```

Exact stdout:

```text
value=0x12345678
bigEndian=12 34 56 78
littleEndian=78 56 34 12
readBE=0x12345678
readLE=0x12345678
wrongOrder=0x78563412
signedInt=-19088744
unsignedInt=4275878552
wireBytes=FE DC BA 98
manualUnsigned=4275878552
signedByte=-2
unsignedByte=254
```

Key takeaways:

- The `bigEndian` and `littleEndian` lines differ in **byte order**, while `value` still reflects the single value `0x12345678`.
- `readBE` and `readLE` match when the reader uses the **exact endianness of the writer**; `wrongOrder=0x78563412` proves reading with the wrong endianness alters the number.
- `signedInt=-19088744` and `unsignedInt=4275878552` share the same bit pattern `0xFEDCBA98`. The negative number comes from signed reading, not a byte-order error.
- `manualUnsigned=4275878552` confirms you can assemble big-endian data manually with proper shifts and masks.
- `signedByte=-2` and `unsignedByte=254` demonstrate the need to handle `byte` signedness before assembling multi-byte integers.

## 8. When Communicating Over a Network, What Must Be Agreed Upon?

In many traditional network protocols, multi-byte integer fields use **network byte order (big-endian)**. For instance, many IPv4/TCP header fields use big-endian. However, **not every protocol running over TCP automatically uses big-endian**: application protocols may prescribe little-endian, per-field byte orders, or text/variable-length encodings.

A data contract should clearly state:

| Attribute | Example Convention |
| --- | --- |
| Field type | unsigned 32-bit |
| Byte count | Exactly 4 |
| Byte order | Big-endian |
| Valid range | 0 to 4_294_967_295 |
| Position in message | Offset 0–3 after header |
| Handling incomplete data | Do not decode field until all 4 bytes arrive |
| Data validation | Reject values outside business range |

For example, a `length` field is specified as **4-byte unsigned big-endian**. The sender must write 4 bytes in the exact order; the receiver must read **all 4 bytes** before computing the unsigned `long` value and checking against the maximum acceptable length. Do not allocate buffers based on a received length before validating range, quota, and data limits.

**TCP provides only a byte stream**; it does not mark "this is one `int`" or guarantee that every `read` call returns a complete field. Message framing, handling partial reads, numeric types, and endianness are the responsibility of protocol design.

## 9. `DataInputStream`, `DataOutputStream`, and Differences from `ByteBuffer`

Java's `DataOutputStream.writeInt(int)` and `DataInputStream.readInt()` mandate **big-endian** encoding for four-byte values. This is a convenient option if your protocol also uses that format.

```java
java.io.ByteArrayOutputStream buffer = new java.io.ByteArrayOutputStream();
try (java.io.DataOutputStream out = new java.io.DataOutputStream(buffer)) {
    out.writeInt(0x1234_5678);
}
byte[] bytes = buffer.toByteArray(); // 12 34 56 78
```

This is a snippet inside a Java method with proper exception handling; it is not a standalone program. If the protocol specifies little-endian, **do not use `DataOutputStream.writeInt` as if it adapts endianness automatically**; use `ByteBuffer.order(LITTLE_ENDIAN)` or write bytes in the required order.

`ByteBuffer.getInt` and `DataInputStream.readInt` both return a **signed `int`**. If the actual field is unsigned 32-bit, the `int` result still holds the exact 32 bits and you can use `Integer.toUnsignedLong` to read the unsigned value.

## 10. Confusing Endianness with Bit Order, Characters, and Text-Encoded Numbers

Endianness is strictly **byte order in a multi-byte representation**. Do not mix it up with these other concepts:

**Bit order:** Some protocols specify whether high or low bits are transmitted first within a byte or frame; that is a bit-level rule. Changing big-endian to little-endian **does not reverse the order of bits within each byte**.

**Text encoding:** When sending the string `"305419896"` in UTF-8, you send **character bytes** (for example, byte `0x33` for the character `'3'`), not the four binary bytes `12 34 56 78`. The receiver must know whether it is receiving a numeric string or a binary integer. In JSON format, numbers are normally represented as text characters; the byte order of a binary `int` does not apply automatically there.

**UTF-16 code unit order:** Some 16-bit string encodings have their own endianness concept. Despite sharing the big/little endian names, text encoding rules must be determined through the charset and text specification, not inferred backward from a binary numeric field's endianness.

**Field width:** Sending the number `1` as one byte `01`, two bytes `00 01`, or four bytes `00 00 00 01` represents three different contracts. Picking an endianness does not replace agreeing on byte count, signed/unsigned width, and field boundaries.

## 11. Common Mistakes When Exchanging Binary Numbers

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Sender writes big-endian, receiver reads little-endian | `12 34 56 78` becomes `0x78563412` | Define byte order and configure both sides to match |
| Assuming a negative `int` means swapped bytes | Confusing signedness with endianness | Inspect bit pattern and `Integer.toUnsignedLong` |
| Combining negative `byte`s without masking | Sign extension corrupts upper bits | Use `& 0xFF` or `Byte.toUnsignedInt` |
| Using `byte[]` with no type contract | Length, signedness, and byte order are undefined | Define an explicit schema for each field |
| Calling `ByteBuffer.getInt()` after `putInt` without `flip()` | Wrong position or buffer underflow | Call `flip()` when switching from writing to reading on the same buffer |
| Assuming `DataOutputStream.writeInt` uses CPU endianness | Output stream does not match expected format | Know that this API writes big-endian |
| Using `Integer.parseInt` to decode four bytes | Parsing expects numeric digit characters, not binary format | Use `ByteBuffer`, bit shifts, or `DataInputStream` |
| Using `0x12345678` in text as if those were the transmitted bytes | Confusing literal syntax with actual payload | Specify binary or text encoding explicitly |
| Assuming TCP `read` always returns all four bytes | Decoding incomplete data | Read in a loop or use a `readFully` API |
| Treating unsigned 32-bit as a plain positive `int` | Values above `Integer.MAX_VALUE` display as negative | Use `long` and unsigned conversion |

## 12. Design and Testing Checklist

Before writing an encoder/decoder, verify for **each field** whether it is 8/16/32/64-bit or variable-length; signed or unsigned; big-endian or little-endian; its offset and byte count; and its valid business range. For unsigned 32-bit fields in Java, prefer `long` as the external API type and validate `0 <= value <= 0xFFFF_FFFFL` before converting to four bytes.

A minimal test suite should include:

1. **Asymmetric recognizable value:** `0x12345678` to detect byte swapping. Big-endian `12 34 56 78`; little-endian `78 56 34 12`.
2. **Unsigned 32-bit boundaries:** `0x00000000`, `0x7FFFFFFF`, `0x80000000`, `0xFFFFFFFF`. Reading/writing must preserve exact bits regardless of temporary negative `int` values.
3. **Round-trip:** write a value and read it back with the matching byte order, comparing the **bit pattern** and unsigned value if specified.
4. **Intentional wrong endianness:** read big-endian bytes as little-endian to ensure the test catches the expected discrepancy.
5. **Short/incomplete message:** feed 1–3 bytes when expecting 4 bytes; the decoder must wait for more or clearly report missing data.
6. **Out-of-bounds input:** test overly large lengths, out-of-contract values, and malformed data, ensuring no unsafe allocations or processing proceed.

**Self-check questions:**

- For the same number `0x12345678`, do big-endian and little-endian have different numeric values? **No**, if decoded under the right convention. Only the order of the four bytes when stored/transmitted differs.
- Which byte appears first in little-endian? **The least significant byte**, here `0x78`.
- Why can `ByteBuffer.getInt()` return a negative number for an unsigned 32-bit field? Because **Java `int` is signed**; use `Integer.toUnsignedLong` to read its unsigned interpretation.
- What is `& 0xFF` used for? Keeping the **low 8 bits** and removing sign-extension effects when promoting a negative `byte` to a wider type.
- If a protocol uses little-endian yet a developer uses `DataOutputStream.writeInt`, what happens? The bytes on the wire **violate the little-endian convention**, because that API writes big-endian.

**Remember:** numeric value does not dictate payload byte order. Endianness is part of the **serialization contract**, signedness is how a **bit pattern is interpreted**, and Java's `byte` is signed so manual byte assembly requires masking. When both sides agree on width, endianness, and signed/unsigned rules and verify against known byte sequences, binary data is exchanged accurately.