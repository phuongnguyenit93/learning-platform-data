# DataInput, DataOutput, and Primitive Data Formats in Java I/O

## 1. From Java Values to Binary Data

A file or network connection only transmits **bytes**. When storing an `int`, `long`, `boolean`, `float`, `double`, `char`, or a character string, a program must specify **how many bytes, in what order, and how they are interpreted**.

For example, the same value 300:

- Written as **UTF-8 text** `"300"`: hex bytes `33 30 30`, 3 bytes long; the reader must parse the numeric string.
- Written as **binary using `writeInt(300)`**: hex bytes `00 00 01 2C`, 4 bytes long; `readInt()` reconstructs the number 300 according to Java rules.

**`java.io.DataOutput`** is the interface specifying how to write Java primitive values and one form of string to a byte stream. **`java.io.DataInput`** is the interface specifying how to read them under the same byte contract.

Two typical implementations are **`DataOutputStream`**, wrapping an `OutputStream`, and **`DataInputStream`**, wrapping an `InputStream`. They convert between Java values and structured bytes; they do not inherently know field names, record schemas, record counts, or file versions.

~~~text
Writer                                    Reader
int, double, boolean, String             bytes in file/network
           |                                      |
           v                                      v
     DataOutputStream                        DataInputStream
           |                                      |
           +---- byte layout must match ----------+
~~~

**Core principle:** the reader must know the exact **order and types** used by the writer. If you write an `int` then a `double`, but read a `short` then a `double`, the data will misalign at byte boundaries; the error can sometimes silently produce wrong values before an EOF occurs.

## 2. Primitive Sizes and Byte Order

Under Java's `DataInput`/`DataOutput` contract:

| Write / Read | Bytes | Interpretation |
| --- | ---: | --- |
| `writeBoolean` / `readBoolean` | 1 | 0 = false, non-zero = true on read; writer writes 0 or 1 |
| `writeByte` / `readByte` | 1 | Reads as a signed byte (-128 to 127) |
| `writeByte` / `readUnsignedByte` | 1 | Reads the same 8 bits as an int 0–255 |
| `writeShort` / `readShort` | 2 | Signed 16-bit integer |
| `writeShort` / `readUnsignedShort` | 2 | Same 16 bits, returns int 0–65535 |
| `writeChar` / `readChar` | 2 | One Java UTF-16 code unit |
| `writeInt` / `readInt` | 4 | Signed 32-bit integer |
| `writeLong` / `readLong` | 8 | Signed 64-bit integer |
| `writeFloat` / `readFloat` | 4 | Float bits via Float.floatToIntBits |
| `writeDouble` / `readDouble` | 8 | Double bits via Double.doubleToLongBits |
| `writeUTF` / `readUTF` | 2 + N | Unsigned 16-bit length + N bytes of **modified UTF-8** |

For multi-byte types, the **most significant byte comes first**: this is **big-endian**, defined by DataInput/DataOutput and **independent of whether the CPU** runs big-endian or little-endian.

~~~text
writeInt(0x01020304) -> 01 02 03 04
writeShort(300)      -> 01 2C
writeChar('A')       -> 00 41
writeLong(1)         -> 00 00 00 00 00 00 00 01
~~~

Do not confuse this with little-endian: `0x01020304` in little-endian is normally `04 03 02 01`. If an external non-Java protocol requires little-endian, you can use **`ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)`** or an appropriate parser; **`DataInputStream.readInt()` has no little-endian option**.

An `int` argument passed to `writeByte`, `writeShort`, or `writeChar` has its **low 8 or 16 bits** extracted respectively. Do not treat `writeByte(300)` as a way to write the full number 300. To preserve the exact value, you must choose the field's size and signedness before writing.

## 3. Java 17+ Example: Writing and Reading a Binary Record

Create the file **PrimitiveBinaryDemo.java** (save the source file in UTF-8):

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Arrays;
import java.util.HexFormat;

public class PrimitiveBinaryDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(0x01020304);
            out.writeShort(300);
            out.writeBoolean(true);
            out.writeDouble(1.5);
            out.writeUTF("Hi");
        }

        byte[] data = buffer.toByteArray();
        System.out.println("bytes=" + data.length);
        System.out.println("prefix="
                + HexFormat.of().formatHex(Arrays.copyOf(data, 7)));

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(data))) {
            System.out.printf("id=%08X%n", in.readInt());
            System.out.println("count=" + in.readUnsignedShort());
            System.out.println("enabled=" + in.readBoolean());
            System.out.println("ratio=" + in.readDouble());
            System.out.println("label=" + in.readUTF());
            System.out.println("eof=" + in.read());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PrimitiveBinaryDemo.java
java PrimitiveBinaryDemo
~~~

Output:

~~~text
bytes=19
prefix=01020304012c01
id=01020304
count=300
enabled=true
ratio=1.5
label=Hi
eof=-1
~~~

Explanation of the 19-byte layout:

| Field | Bytes (hex) | Length |
| --- | --- | ---: |
| id, `writeInt` | 01 02 03 04 | 4 |
| count, `writeShort` | 01 2C | 2 |
| enabled, `writeBoolean` | 01 | 1 |
| ratio, `writeDouble(1.5)` | 3F F8 00 00 00 00 00 00 | 8 |
| label, `writeUTF("Hi")` | 00 02 48 69 | 4 |
| **Total** | | **19** |

**`HexFormat` is built in since Java 17**. `Arrays.copyOf(data, 7)` takes only the first seven bytes to show the bytes of the int, short, and boolean. `readUnsignedShort()` restores count=300, and the final `in.read()` returns `-1` because the entire record has been consumed.

Use **try-with-resources** to close the wrapper. In the example, ByteArrayOutputStream keeps data in memory without needing a physical file; the same logic can wrap Files.newOutputStream/Files.newInputStream to write/read files.

## 4. Why DataInput/DataOutput Is Not Yet a Complete File Format

`writeInt` only writes four bytes. There is no field name `id`, no field sequence number, and no automatic storage of version, checksum, or record delimiter. Therefore, two programs can read the same sequence of bytes into different results if their schemas differ.

Suppose a format specifies:

~~~text
record = [id:int, 4 bytes][score:double, 8 bytes]
record = [id:int, 4 bytes][score:double, 8 bytes]
~~~

Each record is 12 bytes long. If a file has two records, the total record data is 24 bytes. The reader must know there are two records, or have a `count` header, or have a defined termination rule.

A stable binary format should have a clear layout:

~~~text
+----------------+---------+--------------+------------------+
| MAGIC (4 bytes)| VERSION | RECORD_COUNT | RECORDS ...      |
+----------------+---------+--------------+------------------+
~~~

- **Magic** identifies the file type, helping reject data that is not in the same format.
- **Version** tells the reader which layout is used.
- **Record count** or **length prefix** makes it possible to determine data boundaries rather than guessing with an arbitrary EOF condition.
- **Schema per field** describes size, endianness, signedness, string charset, ordering, and valid ranges.

If version 1 has `int id` then `double score`, while version 2 inserts `boolean active` in between, a v1 reader will read the score bytes at the wrong offset. Creating a new version and a compatible parser is the right solution; never assume inserting a byte is automatically compatible.

**DataOutputStream is not ObjectOutputStream.** It does not automatically write an object graph or class metadata; the application explicitly converts objects into primitive fields according to its own schema. Java Object Serialization is a different mechanism with its own format and security requirements.

## 5. writeUTF/readUTF: Modified UTF-8 with a Length Prefix

This is a very important point when interoperating across languages.

**`DataOutput.writeUTF(String)` does not write pure standard UTF-8**. It writes:

1. Two big-endian bytes containing the **payload length in bytes**, in the range 0–65535.
2. N bytes encoded in Java's **modified UTF-8**.

**`DataInput.readUTF()`** reads this exact structure: reads an unsigned 16-bit length, then decodes N bytes according to modified UTF-8.

Differences from standard UTF-8:

- The NUL character `U+0000` is written as `C0 80` in modified UTF-8, instead of the `00` byte in standard UTF-8.
- Code points outside the BMP (for example, some emojis) are represented by two UTF-16 surrogate units and each unit is encoded separately, usually totaling 6 bytes, whereas standard UTF-8 encodes that code point directly into 4 bytes.
- The length value is the **actual number of modified UTF-8 bytes**, not the String character count or `String.length()`.
- If the modified UTF-8 payload needs more than **65,535 bytes**, `writeUTF` throws `UTFDataFormatException`.

Byte examples:

~~~text
writeUTF("Hi")    -> 00 02 48 69
writeUTF("")      -> 00 00
writeUTF(U+0000)  -> 00 02 C0 80
~~~

This means an ordinary UTF-8 TXT file **cannot be read with `readUTF`** if the file does not have the length prefix and modified UTF-8 following the convention above. The first two bytes of the file would be misinterpreted as the length, causing errors, waiting for more data, or producing wrong results.

For external non-Java protocols requiring **standard UTF-8**, you should write UTF-8 bytes using `String.getBytes(StandardCharsets.UTF_8)` and define a **length prefix or delimiter** according to your own contract.

## 6. Java 17+ Example: Standard UTF-8 String with a 4-Byte Length

Create the file **LengthPrefixedUtf8Demo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class LengthPrefixedUtf8Demo {
    public static void main(String[] args) throws IOException {
        String original = "café";
        byte[] payload = original.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(payload.length);
            out.write(payload);
        }

        byte[] wire = buffer.toByteArray();
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(wire))) {
            int length = in.readInt();
            if (length < 0 || length > 1_000_000) {
                throw new IOException("Invalid length: " + length);
            }

            byte[] content = new byte[length];
            in.readFully(content);

            String restored = new String(
                    content, StandardCharsets.UTF_8);
            System.out.println("length=" + length);
            System.out.println("hex=" + HexFormat.of().formatHex(content));
            System.out.println("text=" + restored);
            System.out.println("wireBytes=" + wire.length);
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LengthPrefixedUtf8Demo.java
java LengthPrefixedUtf8Demo
~~~

Stdout:

~~~text
length=5
hex=636166c3a9
text=café
wireBytes=9
~~~

Layout on the wire:

~~~text
00 00 00 05 | 63 61 66 C3 A9
  4 bytes   |    5 standard UTF-8 bytes
  length=5  |    "café"
~~~

The reader knows the first four bytes are a big-endian int length, and then must read **exactly length bytes**. Because both sides agree on the layout and standard UTF-8, another Python/Go/C program can also read it if it implements the specification correctly; there is no need to call Java's `readUTF`.

**`readFully(content)` differs from `read(content)`**: `readFully` reads the full requested number of bytes or throws `EOFException` if the stream ends early; `read(byte[])` may read fewer bytes without an error. In a fixed-length frame, `readFully` helps detect a truncated payload.

In the example, the threshold `1_000_000` is only an **application demonstration limit**, not a general Java standard. If receiving length/count from untrusted input, you must validate limits before allocating arrays, computing sizes, or looping to read many records.

## 7. Signed/Unsigned and the Difference Between Data FF and EOF

Java `byte` is a **signed** type. The hex value `FF` represents 8 bits all set to 1:

- `DataInput.readByte()` returns `byte -1`.
- `DataInput.readUnsignedByte()` returns `int 255`.
- `InputStream.read()` reads a raw byte and returns `int 255`, reserving **`-1` separately** to signal EOF.

Therefore, never equate `readByte() == -1` with EOF: **-1 can be a valid byte value** when reading signed bytes. When bytes are missing, `readByte()` throws **EOFException**.

Similarly, `readShort()` returns a signed number in the range -32768..32767, while `readUnsignedShort()` returns an int from 0..65535. The writer uses `writeShort` to write 16 bits; the reader chooses signed/unsigned according to the field contract.

One detail with boolean: `writeBoolean(true)` writes byte `01`; `writeBoolean(false)` writes `00`. `readBoolean()` accepts **any non-zero byte as true**. If your application protocol only permits 0 or 1, the reader should explicitly inspect the byte to reject values like 2, 3... instead of relying solely on readBoolean.

## 8. EOF and Truncated Files

There is a difference between **reading bytes until the end** and **reading a fixed field without enough bytes**:

- `InputStream.read()` returns **-1** when at EOF.
- `DataInputStream.readInt()` needs a full 4 bytes. If only 2 bytes remain before EOF, it throws **EOFException** instead of padding with 0.
- `DataInputStream.readDouble()` needs 8 bytes; if short, it also throws EOFException.
- `DataInputStream.readFully(byte[])` requires the exact length and throws EOFException if short.
- `DataInputStream.readUTF()` requires the full length prefix and valid encoded payload; it may throw EOFException or UTFDataFormatException on error.

**Do not treat every EOFException as a successful termination.** If the protocol requires 10 records and the 9th record is only halfway written, EOFException is evidence of truncation and must be reported as an error. If a protocol intentionally uses EOF to end a list of complete records, there must be logic distinguishing EOF at a **record boundary** from EOF mid-record.

In particular, **do not write a loop `while (in.readInt() != -1)`** to detect EOF. The integer value -1 is completely valid and can appear in data; furthermore, `readInt()` signals missing bytes via an exception. Use a count, length-prefixed records, or a clearly defined, unambiguous marker.

**`available()` is not the remaining byte count and not an EOF check** for all sources: for networks/pipes, it usually only estimates bytes readable immediately without blocking. `available() == 0` does not prove that the stream has ended.

## 9. Buffering, Flushing, and Closing Streams

You can combine a buffer with a data stream:

~~~java
// Code snippet inside a method that already has Path path,
// along with appropriate Java imports and IOException handling.
try (DataOutputStream out = new DataOutputStream(
        new java.io.BufferedOutputStream(
                java.nio.file.Files.newOutputStream(path)))) {
    out.writeInt(123);
    out.writeDouble(4.5);
}
~~~

On the reading side:

~~~java
try (DataInputStream in = new DataInputStream(
        new java.io.BufferedInputStream(
                java.nio.file.Files.newInputStream(path)))) {
    int id = in.readInt();
    double score = in.readDouble();
    // Process the two fields according to the file schema.
}
~~~

`BufferedOutputStream` batches data to reduce I/O operations. It **does not change the byte order** or format of DataOutputStream. Closing via try-with-resources closes the wrapper and the underlying stream layer, and flushes buffered data if closing succeeds. When a protocol requires the receiver to read data **while the stream remains open**, call `flush()` at appropriate points; flushing does not equate to durable synchronization of data to disk.

Do not read and write concurrently on the same file using multiple uncoordinated wrappers and expect stable byte ordering. Do not insert Reader/Writer in the middle of binary data because character decoding/encoding steps can alter bytes.

## 10. Comparison with Other Java I/O APIs

| API | Used for | Notes |
| --- | --- | --- |
| `InputStream`/`OutputStream` | Raw bytes | Unaware of int/double fields |
| `DataInput`/`DataOutput` | Binary contract for primitives | Does not manage whole-file schema |
| `DataInputStream`/`DataOutputStream` | Stream implementation of DataInput/DataOutput | Writes/reads in a defined order |
| `BufferedInputStream`/`BufferedOutputStream` | Reducing I/O calls | Only optimizes buffering, does not change format |
| `Reader`/`Writer` | Characters/charsets | Not for preserving arbitrary binary bytes |
| `ObjectInputStream`/`ObjectOutputStream` | Java object serialization | Has its own format, not equivalent to primitive records |
| `ByteBuffer` | Byte and primitive buffer with configurable endianness | Used when external non-Java formats require little-endian |

**DataOutputStream does not automatically make a file "portable" in the sense that every application can read it.** It provides a machine-independent layout per write operation. For cross-language interoperability, you must share the exact **structure specification**: magic, version, byte size per field, byte order, signedness, string encoding, null representation, length, and checksum if any.

## 11. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Writing int, reading short | Misaligns subsequent fields | Pair writes/reads strictly by schema |
| Assuming DataInput auto-detects endianness | Misreads little-endian files | Choose a parser/ByteBuffer with the right byte order |
| Calling readUTF on a UTF-8 TXT file | First two bytes treated as length | Use only for writeUTF payloads |
| Confusing modified UTF-8 with standard UTF-8 | Wrong NUL/emoji characters, broken protocol | Define charset and framing explicitly |
| Assuming String.length() equals byte count | Wrong length prefix for multi-byte chars | Use encodedBytes.length |
| Exceeding the writeUTF limit | UTFDataFormatException | Use another length prefix/payload format |
| Calling read(byte[]) only once | Payload may be incomplete | Use readFully or loop until complete |
| Ignoring EOFException mid-record | Accepts truncated files | Treat truncation as an error |
| Trusting arbitrary count/length | Excessive allocation or processing | Validate limits upfront |
| Using available() to measure total stream size | Stops too early or misdetects EOF | Rely on count, length, or read/EOF |
| Changing schema without versioning | Old/new files incompatible | Write a version and branch parsing |
| Failing to close/flush buffers | Missing data or resource leaks | Use try-with-resources, flush when needed |

## 12. Self-Check Questions

**Q1.** For the same number 300, why does writeInt write 4 bytes while UTF-8 text "300" writes 3 bytes?  
**Answer:** writeInt writes the 32-bit binary representation of the integer; text writes digit characters and must be parsed to obtain an int.

**Q2.** Does DataInputStream.readInt use big-endian or little-endian?  
**Answer:** Big-endian by Java contract, independent of CPU architecture.

**Q3.** How many bytes does writeUTF("Hi") write?  
**Answer:** Four bytes: 00 02 as the payload length, and 48 69 as the modified UTF-8 content of the two ASCII characters.

**Q4.** Can you read any arbitrary UTF-8 TXT file with readUTF?  
**Answer:** No. readUTF requires a two-byte length prefix and modified UTF-8.

**Q5.** Is writeUTF limited to 65,535 characters or 65,535 bytes?  
**Answer:** 65,535 **modified UTF-8 encoded bytes**.

**Q6.** If data formatted as int + double has only 6 bytes left, what does readDouble do after readInt?  
**Answer:** Only 2 bytes remain while double needs 8; readDouble throws EOFException.

**Q7.** Why is readFully needed for length-prefixed records?  
**Answer:** It reads the full declared number of bytes or throws EOFException; read(byte[]) can return a partial read without throwing an error.

**Q8.** What do readByte and readUnsignedByte return for a byte FF?  
**Answer:** -1 and 255 respectively, if each read is positioned before a corresponding FF byte.

**Q9.** Why does changing a layout from int+double to int+boolean+double require a version?  
**Answer:** The boolean field inserts an extra byte, causing an older reader to decode the double's bytes at the wrong offset.

## 13. Java SE 17 API References

- [DataInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html): primitives, signed/unsigned, big-endian, readFully, modified UTF-8.
- [DataOutput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html): byte layout of write methods.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): reading primitives from an InputStream.
- [DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): writing primitives to an OutputStream.
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): primitives in a byte buffer, with configurable byte order.

**Takeaway:** DataInput/DataOutput solves **how to encode and decode each primitive value into bytes**. To build a data format that can be reliably read back and exchanged long-term, you still must specify **field order, types, lengths, byte order, charset, version, and how truncated files are handled**. In particular, writeUTF/readUTF uses **modified UTF-8 with a 2-byte prefix**, which differs from standard UTF-8.
