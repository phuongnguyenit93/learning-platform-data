# Big-Endian, Signed Bytes, and Reading Unsigned Values in Java

When processing binary files or network protocols, a program must not only read enough bytes, it must also **interpret the bits correctly**. Two common sources of bugs are the **byte order** (*endianness*) of multi-byte numbers and **signed/unsigned representation** in Java.

Java uses signed `byte` values from -128 to 127, whereas a physical byte can hold any 8-bit pattern from `00` to `FF`. Java also provides unsigned reading APIs such as `DataInputStream.readUnsignedByte()`, `readUnsignedShort()`, and conversion helpers like `Byte.toUnsignedInt(...)` or `Integer.toUnsignedLong(...)`. Meanwhile, `DataInputStream` reads multi-byte integers in **big-endian**; `ByteBuffer` lets you choose either big-endian or little-endian.

This article explains the mechanics, safe bitwise operations, checking for missing bytes, and runnable Java 17+ examples.

## 1. A Raw Byte Differs from a Signed Byte Value

A byte holds 8 bits, having 256 bit patterns from `00000000` to `11111111`, corresponding to `0x00` through `0xFF`. **Bit patterns do not inherently carry the notion of a negative number**; that meaning is assigned by the program when interpreting them.

In Java, the primitive `byte` type is always **signed 8-bit** in two's complement representation, ranging from **-128..127**.

| Bit pattern / hex | As unsigned 8-bit | As Java `byte` |
|---|---:|---:|
| `00000000` / `0x00` | 0 | 0 |
| `01111111` / `0x7F` | 127 | 127 |
| `10000000` / `0x80` | 128 | -128 |
| `11111111` / `0xFF` | 255 | -1 |

From 0 to 127, signed and unsigned yield the same value. From 128 to 255, the highest bit is 1, so when stored in a `byte`, the value is represented as a negative number. This **does not mean the bits are corrupted**: `(byte) 0xFF` still holds the 8 bits `11111111`.

To convert a **`byte`'s bit pattern into an unsigned number 0..255**, there are two equivalent ways:

~~~java
// Illustrative snippet: b is an existing byte variable.
int unsigned1 = b & 0xFF;
int unsigned2 = Byte.toUnsignedInt(b);
~~~

The `& 0xFF` operator preserves the low 8 bits after `byte` is widened to `int`. For instance, `b = (byte) 0xFF` has value `-1` as a `byte`, yet both expressions evaluate to `255`.

**Do not use `Math.abs(b)` for unsigned conversion**. For `0xFF`, `Math.abs((int) b)` only gives `1`, not `255`.

## 2. Why Can Casting and Bit Shifting Cause Bugs?

In Java expressions, `byte` and `short` are usually **promoted to `int`** before computation. When widening a negative signed value, Java performs *sign extension*: the sign bit is replicated across the higher bits.

Example:

~~~java
byte b = (byte) 0x80;   // -128
int signed = b;         // -128
int unsigned = b & 0xFF; // 128
~~~

Conceptual view:

~~~text
Original byte:           1000 0000
Sign-extended to int:    11111111 11111111 11111111 10000000
After AND 0xFF:          00000000 00000000 00000000 10000000
~~~

If you combine multiple bytes with left-shift operators **without masking**, sign bits can bleed into higher bits and corrupt the result:

~~~java
// Wrong when high has bit 7 set to 1:
int wrong = (high << 8) | low;

// Correct for two source bytes in big-endian:
int unsigned16 = ((high & 0xFF) << 8) | (low & 0xFF);
~~~

This is an illustrative snippet, where `high` and `low` are `byte`. In `wrong`, if `high` is negative then the upper bits of `int` can be erroneously set; if `low` is negative, the OR can also smear 1 bits outside the low 8 bits. Masking each byte **before shifting/ORing** makes explicit that both source bytes are values in 0..255.

### Combining Four Bytes into an Unsigned 32-bit Value

An unsigned 32-bit value can reach **4,294,967,295**, exceeding `int`'s limit of 2,147,483,647. To keep the arithmetic result non-negative, use `long` and mask each byte:

~~~java
// Illustrative snippet: a, b, c, d are four byte variables in big-endian order.
long unsigned32 =
        ((long) (a & 0xFF) << 24)
      | ((long) (b & 0xFF) << 16)
      | ((long) (c & 0xFF) << 8)
      |  (long) (d & 0xFF);
~~~

Cast to `long` before shifting when you need to represent an unsigned 32-bit value as a non-negative number; if combined into an `int`, the bit pattern is still right, yet the Java numeric value can be negative. You can convert an already-read `int` into an unsigned 32-bit value with `Integer.toUnsignedLong(value)`.

## 3. Big-Endian and Little-Endian Are Byte Storage Orders

**Endianness** specifies the order of **bytes** within a multi-byte value (such as `short`, `int`, `long`). It does not change the bit order within each individual byte.

Suppose the 32-bit value is `0x12345678`:

| Order | Bytes in the order they appear in file/network |
|---|---|
| **Big-endian** | `12 34 56 78` |
| **Little-endian** | `78 56 34 12` |

- **Big-endian**: the *most significant byte* is written/read first.
- **Little-endian**: the *least significant byte* is written/read first.

For two bytes `12 34`, reading unsigned 16-bit as big-endian yields `0x1234 = 4660`; interpreting it as little-endian yields `0x3412 = 13330`.

**Signedness and endianness are two independent issues**:

- Signed/unsigned defines how the highest bit and value range are interpreted.
- Big/little-endian defines byte order when assembling a **multi-byte** value.
- A single byte has no endianness issue; it only has an 8-bit pattern and signed/unsigned interpretation.

When reading binary files, **do not guess** endianness from the machine running the code. The proper rule must come from the file format or protocol. In many network protocols, big-endian order is also called *network byte order*, though not every protocol defaults to big-endian.

## 4. InputStream.read() Already Returns Unsigned 8-bit — Distinguish EOF

`InputStream.read()` returns an `int`, with two kinds of results:

- `0..255`: the value of the byte just read successfully, already interpreted as **unsigned**.
- `-1`: no more bytes (EOF, *end of file/stream*).

Therefore, when reading byte `0xFF`, `read()` returns **255**, not `-1`. If you immediately cast the result to `byte` and compare against `-1`, the program may **mistake valid `0xFF` data for EOF**.

### Java 17+ Example: Signed Byte, Unsigned Byte, and EOF

Create file **`SignedUnsignedByteDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class SignedUnsignedByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = {0x7F, (byte) 0x80, (byte) 0xFF};

        for (byte value : data) {
            System.out.printf("signed=%d unsigned=%d%n",
                    value, Byte.toUnsignedInt(value));
        }

        try (InputStream in = new ByteArrayInputStream(data)) {
            int value;
            while ((value = in.read()) != -1) {
                System.out.println("read()=" + value);
            }
            System.out.println("EOF=" + in.read());
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 SignedUnsignedByteDemo.java
java SignedUnsignedByteDemo
~~~

Stdout:

~~~text
signed=127 unsigned=127
signed=-128 unsigned=128
signed=-1 unsigned=255
read()=127
read()=128
read()=255
EOF=-1
~~~

Key points:

1. In `byte[]`, the two bytes `0x80` and `0xFF` have negative signed values.
2. `Byte.toUnsignedInt(...)` returns 128 and 255 respectively, preserving the bit patterns.
3. `InputStream.read()` already returns unsigned 8-bit as an `int`; `-1` is strictly EOF.
4. The loop checks `-1` **before casting or interpreting**. Do not use `byte value = (byte) in.read()` as the end-of-data condition.

With `InputStream.read(byte[] buffer)`, the **return value** is the number of bytes read (or `-1` on EOF), while **each element `buffer[i]` is still a signed `byte`**. To compute unsigned values from array elements, still use `buffer[i] & 0xFF`.

## 5. DataInputStream Reads Multi-Byte Numbers in Big-Endian

`java.io.DataInputStream` wraps an `InputStream` to read typed binary data. By contract of its multi-byte reading methods, it uses **big-endian**, independent of CPU and operating system.

| Method | Bytes Read | Return Type | Range or Meaning |
|---|---:|---|---|
| `readByte()` | 1 | `byte` | signed -128..127 |
| `readUnsignedByte()` | 1 | `int` | unsigned 0..255 |
| `readShort()` | 2 | `short` | signed -32768..32767, big-endian |
| `readUnsignedShort()` | 2 | `int` | unsigned 0..65535, big-endian |
| `readChar()` | 2 | `char` | unsigned UTF-16 unit 0..65535, big-endian |
| `readInt()` | 4 | `int` | signed 32-bit, big-endian |
| `readLong()` | 8 | `long` | signed 64-bit, big-endian |
| `readFloat()` | 4 | `float` | IEEE 754 bit pattern read in big-endian |
| `readDouble()` | 8 | `double` | IEEE 754 bit pattern read in big-endian |

`DataInputStream` does **not** have a dedicated `readUnsignedInt()` method in Java SE. The standard way is:

~~~java
// Illustrative snippet: dataIn is an opened DataInputStream.
long unsigned32 = Integer.toUnsignedLong(dataIn.readInt());
~~~

Although `readInt()` may produce a negative number, **the 32 bits obtained are still right**. `Integer.toUnsignedLong(...)` interprets that 32-bit pattern as a value `0..4294967295` in `long`.

Similarly, for an existing `short`, `Short.toUnsignedInt(value)` converts it to a non-negative `int` in `0..65535`.

### Do Not Read Multi-Byte Numbers Like a Single Byte Read

Calling `readUnsignedShort()` must fetch a full **two bytes** in big-endian order. If the stream ends after one byte, the method throws `EOFException` (a subclass of `IOException`), instead of silently returning a wrong number. `readInt()` similarly demands a full four bytes.

A binary message is read correctly only when **both sides agree** on byte counts, byte order, signedness, and field semantics; using the right method with the wrong schema still decodes incorrectly.

## 6. Java 17+ Example: DataOutputStream + DataInputStream

`DataOutputStream` writes primitives to bytes in an order compatible with `DataInputStream` (big-endian for multi-byte numbers). The following example uses an in-memory stream to observe each byte directly.

Create file **`BigEndianDataDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Locale;

public class BigEndianDataDemo {
    public static void main(String[] args) throws IOException {
        byte[] bytes;

        try (ByteArrayOutputStream memory = new ByteArrayOutputStream();
             DataOutputStream out = new DataOutputStream(memory)) {
            out.writeShort(0x1234);
            out.writeInt(0x89ABCDEF);
            out.writeByte(0xFF);
            out.flush();
            bytes = memory.toByteArray();
        }

        StringBuilder hex = new StringBuilder();
        for (byte b : bytes) {
            if (hex.length() > 0) {
                hex.append(' ');
            }
            hex.append(String.format(Locale.ROOT, "%02X", b & 0xFF));
        }
        System.out.println("bytes=" + hex);

        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(bytes))) {
            int unsigned16 = in.readUnsignedShort();
            int signed32 = in.readInt();
            int unsigned8 = in.readUnsignedByte();

            System.out.println("u16=" + unsigned16);
            System.out.println("i32=" + signed32);
            System.out.println("u32=" + Integer.toUnsignedLong(signed32));
            System.out.println("u8=" + unsigned8);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 BigEndianDataDemo.java
java BigEndianDataDemo
~~~

Exact stdout:

~~~text
bytes=12 34 89 AB CD EF FF
u16=4660
i32=-1985229329
u32=2309737967
u8=255
~~~

Analysis:

- `writeShort(0x1234)` produces two bytes `12 34`. `readUnsignedShort()` returns `4660`.
- `writeInt(0x89ABCDEF)` produces `89 AB CD EF`. The 32-bit sign bit is 1 so `readInt()` returns a negative signed number, whereas `Integer.toUnsignedLong(...)` yields the unsigned number `2309737967`.
- `writeByte(0xFF)` writes only the low 8 bits. `readUnsignedByte()` returns `255`.
- `String.format("%02X", b & 0xFF)` prints a byte as two-digit hex; `& 0xFF` prevents sign-extension issues.
- `ByteArrayOutputStream` holds data in RAM; this example is for learning. For real files or sockets, manage stream lifecycles, data sizes, and I/O errors accordingly.

**Do not write and read the same stream by guessing the format**: `DataOutputStream.writeUTF/readUTF` has its own modified UTF-8 and length-prefix convention, which is **not** equivalent to writing a raw UTF-8 string. Learning endianness with numeric fields does not mean text follows the same encoding style.

## 7. ByteBuffer: Big-Endian by Default, Configurable Order

`java.nio.ByteBuffer` provides `getShort()`, `getInt()`, `getLong()`, and corresponding `put...` methods. It has a `ByteOrder` property specifying the byte order of **multi-byte** read/write operations.

- A new `ByteBuffer` defaults to **`ByteOrder.BIG_ENDIAN`**.
- It can be changed via `buffer.order(ByteOrder.LITTLE_ENDIAN)`.
- The order property applies to multi-byte accessors such as `getShort/getInt/putInt`; it does **not** reverse bytes when calling `get()` for a single byte.
- `getInt()` still returns a **signed `int`** regardless of byte order; if the value must be treated as unsigned, use `Integer.toUnsignedLong(...)`.

### Java 17+ Example: Same Four Bytes, Two Different Values

Create file **`ByteOrderDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class ByteOrderDemo {
    public static void main(String[] args) {
        byte[] data = {0x01, 0x02, 0x03, 0x04};

        int big = ByteBuffer.wrap(data)
                .order(ByteOrder.BIG_ENDIAN)
                .getInt();

        int little = ByteBuffer.wrap(data)
                .order(ByteOrder.LITTLE_ENDIAN)
                .getInt();

        System.out.println("big=" + big);
        System.out.println("little=" + little);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ByteOrderDemo.java
java ByteOrderDemo
~~~

Stdout:

~~~text
big=16909060
little=67305985
~~~

Explanation:

- Big-endian interprets `01 02 03 04` as `0x01020304`, which is `16909060`.
- Little-endian interprets the same byte sequence as `0x04030201`, which is `67305985`.
- No bytes in `data` are altered; only the rule for combining them into an `int` differs.

`ByteOrder.nativeOrder()` reports the platform's native byte order for memory/native interop scenarios. **Do not use it to decide how to read a file format or protocol**: the format itself dictates big- or little-endian.

`DataInputStream` does not have `order(ByteOrder.LITTLE_ENDIAN)`. If a protocol uses little-endian, use a properly configured `ByteBuffer`, read individual bytes and assemble manually, or use an I/O library with a little-endian API.

## 8. Manually Combining Unsigned 16-bit and Unsigned 32-bit in Big-Endian

When a format has a custom byte layout or you prefer not to use `DataInputStream`, you can combine bytes using shifts and OR. For two bytes `hi`, `lo`, the big-endian unsigned 16-bit value is:

\[
(\mathrm{hi}\ \&\ 255)\times 256 + (\mathrm{lo}\ \&\ 255)
\]

For four bytes `a, b, c, d`, the big-endian unsigned 32-bit value is:

\[
((a\ \&\ 255)\ll 24)\;|\;((b\ \&\ 255)\ll 16)\;|\;((c\ \&\ 255)\ll 8)\;|\;(d\ \&\ 255)
\]

In Java, use `long` if you want to print a **non-negative unsigned 32-bit** value. When reading directly from `InputStream.read()`, each byte value is already `0..255`; however, you still must check EOF (`-1`) **before combining**. If a byte is missing, never feed `-1` into shifts and treat it as valid data.

### Java 17+ Example: Masking and Shifting with Unsigned Values

Create file **`UnsignedBitwiseDemo.java`**:

~~~java
public class UnsignedBitwiseDemo {
    public static void main(String[] args) {
        byte high = (byte) 0xAB;
        byte low = (byte) 0xCD;

        int u16 = ((high & 0xFF) << 8) | (low & 0xFF);
        short signed16 = (short) u16;

        System.out.println("u16=" + u16);
        System.out.println("s16=" + signed16);

        byte[] four = {
                (byte) 0xFF, (byte) 0xFF,
                (byte) 0xFF, (byte) 0xFF
        };

        long u32 = ((long) (four[0] & 0xFF) << 24)
                 | ((long) (four[1] & 0xFF) << 16)
                 | ((long) (four[2] & 0xFF) << 8)
                 |  (long) (four[3] & 0xFF);

        System.out.println("u32=" + u32);
        System.out.println("asInt=" + (int) u32);
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnsignedBitwiseDemo.java
java UnsignedBitwiseDemo
~~~

Stdout:

~~~text
u16=43981
s16=-21555
u32=4294967295
asInt=-1
~~~

The two bytes `AB CD` have the **same 16-bit pattern**, yet `int u16` holds the unsigned meaning 43981, whereas casting to signed `short` gives -21555. Four bytes `FF FF FF FF` represent the largest unsigned 32-bit number `4294967295`; casting to `int` preserves the 32 bits but interprets them as signed -1.

If you only need to convert an existing 16/32-bit signed pattern, avoid rewriting all the bitwise logic:

~~~java
// Illustrative snippet with short s and int i already read.
int unsigned16 = Short.toUnsignedInt(s);
long unsigned32 = Integer.toUnsignedLong(i);
~~~

Standard helpers make intent clear and prevent many mask/shift bugs.

## 9. Reading "Unsigned" Beyond 32 Bits in Java

Java has no separate `unsigned byte`, `unsigned short`, `unsigned int`, or `unsigned long` primitive types like some languages. However, you can **preserve the exact bit pattern** and use unsigned interpretation APIs.

| Unsigned Bits | Range | Suitable Java Representation |
|---|---|---|
| 8 | 0..255 | `int` with `Byte.toUnsignedInt(byte)` or `DataInputStream.readUnsignedByte()` |
| 16 | 0..65535 | `int` with `Short.toUnsignedInt(short)` or `DataInputStream.readUnsignedShort()` |
| 32 | 0..4294967295 | `long` with `Integer.toUnsignedLong(int)` |
| 64 | 0..18446744073709551615 | Bit pattern in `long` with unsigned helpers, or `BigInteger` if mathematical values above `Long.MAX_VALUE` are needed |

For 64-bit unsigned data:

- `DataInputStream.readLong()` reads a full 8 big-endian bytes, returning a signed `long` holding the **exact 64-bit pattern**.
- `Long.toUnsignedString(value)` displays that value as an unsigned decimal string.
- `Long.compareUnsigned(a, b)` and `Long.divideUnsigned(...)`/`remainderUnsigned(...)` support unsigned comparisons and division.
- `BigInteger` can represent the full 0..2^64-1 range when an application needs arithmetic beyond signed `long` limits. Converting bytes to `BigInteger` must specify **sign, length, and byte order**; the constructor `new BigInteger(1, magnitudeBigEndian)` accepts a big-endian magnitude array and forces a positive sign.

Do not manually add `2^64` in a `long` expression, because that number cannot be represented in a signed `long`. Avoid implicit overflow arithmetic as if it were an unbounded positive integer.

## 10. Binary Reading Mistakes to Avoid

### 10.1. Confusing `0xFF` with EOF

Wrong:

~~~java
// Illustrative snippet: wrong because int returned by read() is cast to byte first.
byte value = (byte) input.read();
if (value == -1) {
    // Cannot distinguish byte 0xFF from EOF.
}
~~~

Correct:

~~~java
// Illustrative snippet: input is an open InputStream.
int value = input.read();
if (value == -1) {
    // EOF.
} else {
    int unsigned8 = value; // 0..255
}
~~~

### 10.2. Shifting a Negative `byte` Before Masking

Wrong:

~~~java
// Illustrative snippet: b0 and b1 are bytes that may be negative.
int combined = (b0 << 8) | b1;
~~~

Correct:

~~~java
int combined = ((b0 & 0xFF) << 8) | (b1 & 0xFF);
~~~

If four bytes must become a non-negative unsigned 32-bit number, use `long` as shown in section 8.

### 10.3. Reading Unsigned Values into Too Small a Type

Wrong:

~~~java
// Illustrative snippet: readUnsignedShort() can return 65535.
short size = (short) dataIn.readUnsignedShort();
~~~

For values above 32767, `size` becomes negative due to casting to `short`. Correct is keeping it in an `int`:

~~~java
int size = dataIn.readUnsignedShort();
~~~

### 10.4. Using the Right Type with the Wrong Endianness

If a file contains two bytes `34 12` defined as the little-endian number `0x1234`, calling `DataInputStream.readUnsignedShort()` yields `0x3412`, **not** the expected value 4660. You must read little-endian according to the source contract.

### 10.5. Assuming One `read(byte[])` Always Fills the Length

`InputStream.read(byte[])` may return fewer bytes than the array size even before reaching EOF. When fixed data requires a full N bytes, use `DataInputStream.readFully(byte[])`, `readNBytes(...)` with a count check, or loop until complete. `readFully(...)` throws `EOFException` when it cannot read all requested bytes.

`DataInputStream.readInt()`/`readUnsignedShort()` internally read the required number of bytes, unlike an unchecked single `read(byte[])` call.

## 11. When to Use Which API?

| Need | Practical Choice | Notes |
|---|---|---|
| Fetch byte by byte from stream | `InputStream.read()` | Returns `0..255` or `-1` on EOF |
| Interpret a signed `byte` as unsigned | `Byte.toUnsignedInt(b)` or `b & 0xFF` | Does not alter bits |
| Read big-endian unsigned 16-bit | `DataInputStream.readUnsignedShort()` | Returns `int`, throws if fewer than 2 bytes |
| Read big-endian unsigned 32-bit | `Integer.toUnsignedLong(in.readInt())` | Returns `long` 0..4294967295 |
| Read consecutive big-endian types | `DataInputStream` | Same schema as the writer |
| Read int/short with selectable endianness | `ByteBuffer.order(...).getInt()/getShort()` | Remember unsigned conversion if needed |
| Parse a custom binary format | Read bytes and mask/shift per spec | Must verify length, EOF, and order |
| Unsigned 64-bit | `Long.toUnsignedString` or `BigInteger` | No primitive positive type covers the full range |

### Checklist When Designing or Parsing a Binary Format

1. **Length:** how many bytes is the field? Is there a length prefix or padding?
2. **Byte order:** is it big-endian or little-endian?
3. **Signed or unsigned:** what is the valid value range?
4. **Result storage type:** is its range wide enough? E.g., unsigned 16-bit needs `int`, non-negative unsigned 32-bit needs `long`.
5. **Enough bytes read:** was EOF (`-1`/`EOFException`) handled instead of feeding missing values into bit operations?
6. **Bounded input sizes:** never use an untrusted file's length field to allocate arrays arbitrarily.
7. **Raw bytes differ from text:** `DataInputStream` numeric methods do not replace charset rules for character strings.

## 12. Key Takeaways

- Java `byte` is **signed -128..127**, while the 8-bit data pattern can still be interpreted as **unsigned 0..255** via `b & 0xFF` or `Byte.toUnsignedInt(b)`.
- `InputStream.read()` returns `int 0..255` for valid bytes and `-1` for **EOF**; never cast to `byte` before checking EOF.
- **Big-endian** places the most significant byte first; **little-endian** places the least significant byte first. Endianness is unrelated to the sign of an individual byte.
- `DataInputStream`/`DataOutputStream` use **big-endian** when reading/writing multi-byte numbers. `ByteBuffer` defaults to big-endian and lets you choose `ByteOrder.LITTLE_ENDIAN`.
- `readUnsignedByte()` returns `int`; `readUnsignedShort()` returns `int`. For unsigned 32-bit, use `Integer.toUnsignedLong(readInt())`.
- When combining bytes, **mask before shifting/ORing**, store the result in a wide-enough type, and verify enough input bytes were read.
- Any decoded value is only valid when **length, endianness, signedness, and schema** match the format/protocol specification.

### Official Documentation

- [Java SE 17 — Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html)
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html)
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — Integer.toUnsignedLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toUnsignedLong(int))
