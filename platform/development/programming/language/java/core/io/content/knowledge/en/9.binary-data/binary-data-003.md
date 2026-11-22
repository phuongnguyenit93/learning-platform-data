# Write Order Must Match Read Order in Java Binary I/O

## 1. Core Principle: Binary Data Does Not Carry Field Names or Types

In binary I/O, `OutputStream` writes **contiguous bytes**. The bytes themselves do not indicate which segment is an integer, floating-point number, string, element count, or end of a record. The receiver must know the **protocol/format** in advance: what order the fields appear in, how many bytes each field uses, how it is encoded, and how it is bounded.

For example, if the writer executes:

```java
out.writeInt(42);
out.writeBoolean(true);
out.writeDouble(3.5);
```

then the matching reader must execute:

```java
int id = in.readInt();
boolean active = in.readBoolean();
double score = in.readDouble();
```

The two snippets above are illustrative only; `out` must be a `DataOutputStream`, `in` must be a `DataInputStream` reading the exact byte stream that was written, and `IOException` must be handled. Reading `double` before `int` or using `readShort()` instead of `readInt()` consumes the wrong number of bytes; from that point on, subsequent fields can be misinterpreted or hit EOF.

**Rule:** For each field written, the reader must use the **format-matching** decoding method, in the **exact same order**, while obeying all conventions for length, endianness, charset, version, and record boundaries.

## 2. Why Does Order Matter?

A normal byte stream only maintains a current read position (cursor). Each read operation:

1. Fetches a number of bytes from the current position.
2. Interprets those bytes according to the called method.
3. Advances the cursor by the exact number of bytes consumed by that method.

`readInt()` needs 4 bytes; `readShort()` needs 2 bytes; `readLong()` needs 8 bytes. If a 4-byte `int` was written but a 2-byte `short` is read, **2 bytes of the old field** remain in front of the next field. Every subsequent read can become misaligned.

Visualize a format with three fields:

```text
Write: [int id: 4 bytes][boolean active: 1 byte][double score: 8 bytes]
        └── 4 bytes ───┘ └─ 1 byte ──┘ └────── 8 bytes ──────┘

Correct read:
        readInt()       readBoolean()           readDouble()

Wrong read:
        readShort()     readBoolean()           readDouble()
        └ only 2 bytes ┘
                        ↑ cursor is now in the middle of the id field
```

The byte stream here describes a plain sequence of bytes. There is no implicit delimiter between `writeInt`/`writeDouble` calls; calling `flush()` or `close()` does not automatically insert field names.

Notably, **values can sometimes look valid even when misread**: 2 or 4 shifted bytes still form some valid Java integer. Relying solely on "no exception was thrown" is not enough to confirm that data was decoded correctly.

## 3. Matching Write/Read API Pairs in `DataOutputStream` and `DataInputStream`

`java.io.DataOutputStream`/`DataInputStream` provide representations of several primitive types according to Java's **binary** contract:

| Write | Matching Read | Bytes / Interpretation |
| --- | --- | --- |
| `writeBoolean(boolean)` | `readBoolean()` | 1 byte; writes `1` for `true`, `0` for `false` |
| `writeByte(int)` | `readByte()` or `readUnsignedByte()` | 1 byte; reads signed `-128..127` or unsigned `0..255` |
| `writeShort(int)` | `readShort()` or `readUnsignedShort()` | 2 bytes, big-endian; signed/unsigned |
| `writeChar(int)` | `readChar()` | 2 bytes, one UTF-16 code unit, big-endian |
| `writeInt(int)` | `readInt()` | 4 bytes, big-endian, signed integer |
| `writeLong(long)` | `readLong()` | 8 bytes, big-endian, signed integer |
| `writeFloat(float)` | `readFloat()` | 4 bytes, IEEE 754 bits per DataOutput specification |
| `writeDouble(double)` | `readDouble()` | 8 bytes, IEEE 754 bits per DataOutput specification |
| `writeUTF(String)` | `readUTF()` | 2 bytes writing **byte length**, then **modified UTF-8** content |
| `write(byte[])` | `readFully(byte[])` | Exact number of bytes in the array; length must be known beforehand |

The `writeByte`/`writeShort` methods only write the low-order bytes of the passed number; not every `int` value is preserved when narrowed. `readUnsignedByte`/`readUnsignedShort` are used when the protocol defines the field as unsigned; **the exact same byte** can be interpreted differently depending on the read API.

For multi-byte types in `DataOutputStream`, the byte order is **big-endian** (most significant byte first). `DataInputStream` reads using that same convention. When interoperating with software using little-endian or custom structures, follow the other side's specification exactly, e.g., via `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` or an appropriate API; do not assume every system's binary format matches Data Streams.

### Distinguishing `read()`, `readFully()`, and `readInt()`

- `InputStream.read()` fetches **one byte** and returns an integer `0..255`, or `-1` on EOF.
- `InputStream.read(byte[])` is permitted to return **fewer bytes than the array length** even before EOF. It does not guarantee filling the array in a single read.
- `DataInputStream.readFully(byte[])` attempts to read the full requested number of bytes; if EOF occurs first, it throws `EOFException`.
- `DataInputStream.readInt()` reads exactly 4 bytes and interprets them as an `int`; it is not like calling `read()` and assuming a full field's data is already there.

A successful read only means that method read according to **its own rules**; the program remains responsible for ensuring those rules match the file schema.

## 4. Runnable Example: Writing and Reading in the Right Order

Create file **`BinaryWriteReadOrderDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Locale;

public class BinaryWriteReadOrderDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(42);
            out.writeBoolean(true);
            out.writeDouble(3.5);
            out.writeUTF("Cà phê");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            int id = in.readInt();
            boolean active = in.readBoolean();
            double score = in.readDouble();
            String name = in.readUTF();

            System.out.println("id=" + id);
            System.out.println("active=" + active);
            System.out.printf(Locale.ROOT, "score=%.1f%n", score);
            System.out.println("name=" + name);
            System.out.println("remaining=" + in.available());
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac -encoding UTF-8 BinaryWriteReadOrderDemo.java
java BinaryWriteReadOrderDemo
```

Output:

```text
id=42
active=true
score=3.5
name=Cà phê
remaining=0
```

Points to understand:

1. `DataOutputStream` writes sequentially **`int` → `boolean` → `double` → length-prefixed string**. No field names or separators are added.
2. `DataInputStream` reads in the **exact order and with the matching API pair**, recovering the four original values.
3. `writeUTF`/`readUTF` is the matching pair for *Data Streams' modified UTF-8*, not raw UTF-8 byte writes. Accented characters in the example still round-trip properly.
4. `DataOutputStream` is closed before `toByteArray()` is called so all writer layers finish. Although the example only uses an in-RAM buffer, the flush/close completion principle is crucial when combining files or other wrappers.
5. `available() == 0` on **this specific `ByteArrayInputStream`** indicates no bytes remain in the array. **Do not use `available() == 0` as a general EOF check for every `InputStream`**, especially sockets or complex streams.

This is an in-RAM pure binary example; if you switch the source/destination to a file, the order of operations must still be preserved.

## 5. Wrong-Order Read Example: Program Still Runs but Data Is Wrong

An `int` field takes 4 bytes and a `short` field takes 2 bytes. This allows an exact demonstration without relying on random failure behavior.

Create file **`WrongBinaryOrderDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Locale;

public class WrongBinaryOrderDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(0x01020304);
            out.writeShort(0x0506);
        }

        byte[] content = bytes.toByteArray();

        try (DataInputStream right = new DataInputStream(
                new ByteArrayInputStream(content))) {
            System.out.printf(Locale.ROOT, "correct=%08X,%04X%n",
                    right.readInt(), right.readUnsignedShort());
        }

        try (DataInputStream wrong = new DataInputStream(
                new ByteArrayInputStream(content))) {
            System.out.printf(Locale.ROOT, "wrong=%04X,%08X%n",
                    wrong.readUnsignedShort(), wrong.readInt());
        }
    }
}
```

Run:

```bash
javac WrongBinaryOrderDemo.java
java WrongBinaryOrderDemo
```

Output:

```text
correct=01020304,0506
wrong=0102,03040506
```

Byte-by-byte explanation:

```text
Actually written: 01 02 03 04 | 05 06
                  └── int ───┘   short

Correct read:     01 02 03 04 | 05 06
                  readInt        readUnsignedShort

Wrong read:       01 02 | 03 04 05 06
                  short   int (boundary shifted)
```

Noticeably, both wrong reads **have enough bytes to complete**, so an exception does not necessarily occur. To analyze bugs, check the schema and offsets, or compare bytes in hex; merely catching `EOFException` is not enough.

**Note:** If the remaining bytes are insufficient for `readInt()`, Java throws `EOFException`. If enough bytes remain even for the wrong field, Java still constructs a value from those bytes. These two situations must be diagnosed differently.

## 6. Variable-Length Fields: Agreeing on a "Framing" Rule

`int`, `long`, and `double` have fixed lengths, but `String` and array data usually **do not have fixed lengths**. If you write multiple consecutive strings as raw UTF-8 bytes without boundary info, the reader cannot tell where the first string's bytes end.

A common approach is a **length prefix**: write the length first as an `int`, then write that exact number of bytes. The reader calls `readInt()` to get the length, validates it, and then calls `readFully(...)` to retrieve the exact payload.

Example two-record format:

```text
[int count]
    [int id][int nameByteLength][nameUtf8Bytes]
    [int id][int nameByteLength][nameUtf8Bytes]
```

Here, string length is measured in **UTF-8 byte count**, not `String.length()` (number of UTF-16 code units). For instance, a name containing Vietnamese diacritics may occupy more bytes than the number of visible characters.

Runnable Java 17+ example **`LengthPrefixedRecordsDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class LengthPrefixedRecordsDemo {
    private static void writeRecord(
            DataOutputStream out, int id, String name) throws IOException {
        byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
        out.writeInt(id);
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(2); // number of records
            writeRecord(out, 7, "An");
            writeRecord(out, 8, "Bình");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            int count = in.readInt();
            if (count < 0 || count > 100) {
                throw new IOException("Invalid record count: " + count);
            }

            for (int i = 0; i < count; i++) {
                int id = in.readInt();
                int length = in.readInt();

                if (length < 0 || length > 1024) {
                    throw new IOException("Invalid name length: " + length);
                }

                byte[] payload = new byte[length];
                in.readFully(payload);
                String name = new String(payload, StandardCharsets.UTF_8);

                System.out.println("id=" + id + ", name=" + name);
            }
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 LengthPrefixedRecordsDemo.java
java LengthPrefixedRecordsDemo
```

Output:

```text
id=7, name=An
id=8, name=Bình
```

The corresponding steps are very clear:

| Step | Write | Read |
| ---: | --- | --- |
| 1 | `out.writeInt(2)` | `int count = in.readInt()` |
| 2 | `out.writeInt(id)` | `int id = in.readInt()` |
| 3 | `out.writeInt(utf8.length)` | `int length = in.readInt()` |
| 4 | `out.write(utf8)` | `in.readFully(payload)` |
| 5 | Repeat steps 2–4 for the next record | Loop for exact `count` records |

If the writer writes UTF-8 bytes but the reader calls `readUTF()`, the data is incompatible: `readUTF()` expects a **2-byte prefix and modified UTF-8**, whereas the example uses a **4-byte prefix and standard UTF-8**. Simply calling both "strings" is not enough; you must agree on **every byte of the string format**.

**Protection when reading untrusted data:** Validate `count` and `length` before allocating `byte[]`. The maximum bound depends on business logic; `1024` in the example is just an illustrative limit. Do not let input data trigger gigabyte-sized array allocations or huge loops by declaring an enormous record count.

## 7. EOF, Truncated Records, and Whether Enough Bytes Were Read

`EOFException` usually indicates that a method like `readInt()`, `readLong()`, or `readFully()` could not retrieve enough required bytes. With a fixed protocol, this typically indicates a **truncated** file/stream, incomplete transmission, or a schema mismatch between the two sides.

Distinguish:

- **Valid termination:** all declared records have been read, or a protocol-defined end marker was encountered.
- **Unexpected termination:** the schema requires more fields or bytes, yet bytes ran out, resulting in `EOFException`.
- **Wrong value without EOF:** reading at a misaligned boundary produces a number still valid as a Java type, yet invalid under business rules.
- **Source has no data yet:** a network stream may block and wait; that does not mean EOF. `available()` does not provide reliable record boundaries.

Do not use `catch (EOFException e) { /* ignore */ }` as a general rule. Only treat EOF as normal completion if **the format permits EOF as a terminator** and no record is partially read. When record count or length is declared, EOF in the middle of a record is an error.

If the format must detect trailing bytes beyond valid data, after reading all records you can check one more byte:

```java
int extra = in.read();
if (extra != -1) {
    throw new IOException("Unexpected trailing bytes");
}
```

This is an **illustrative snippet** assuming `DataInputStream in` has finished reading the valid portion and importing `IOException`. This read may block on an open network source; it is suitable when a protocol/file is expected to have ended or has an explicit end signal, and should not be applied unconditionally to long-lived streaming connections.

## 8. Strings in Binary Formats: `writeUTF` Does Not Equal Standard UTF-8

Java Data Streams provide the pair:

```java
out.writeUTF(text);
String restored = in.readUTF();
```

This is an **illustrative snippet**, requiring corresponding `out`/`in`. `writeUTF` writes **2 unsigned length bytes** (maximum 65,535 encoded payload bytes), followed by data in **modified UTF-8**. `readUTF` reads this exact convention. For strings whose encoded form is too long, `writeUTF` may throw `UTFDataFormatException`.

`DataOutputStream`'s modified UTF-8 is not identical to standard UTF-8:

- The NUL character `U+0000` is represented differently from standard UTF-8's single byte `00`.
- Unicode characters outside the BMP go through UTF-16 surrogate code units and can use **6 bytes** in modified UTF-8, instead of 4 standard UTF-8 bytes.
- `writeUTF`'s length prefix is only 2 bytes; with a custom `writeInt(length)` prefix, the prefix is 4 bytes long.

Therefore, before reading **any string**, answer: were these bytes produced by `writeUTF`, or are they UTF-8/UTF-16/another charset under a published format? Do not use `readUTF()` to read data written by `OutputStreamWriter(UTF_8)`, unless the writer deliberately constructed the exact prefix and modified UTF-8.

Similarly, `writeChars(String)` writes **each `char` as 2 bytes** in big-endian without a length prefix. `writeBytes(String)` writes the low 8 bits of each `char` and can lose Unicode data. Neither is equivalent to `writeUTF` or standard UTF-8 encoding.

## 9. Other Rules Beyond Order That Must Be Agreed Upon

Order is a necessary condition, but not sufficient. A binary "data contract" should clearly specify:

1. **Magic/header:** whether there is a format-identifying signature; e.g., a 4-byte constant to avoid misreading the wrong file.
2. **Version:** schema version; lets the reader know which version's layout to apply for what follows.
3. **Field order:** which field comes first, which comes next; mandatory vs. optional fields.
4. **Primitive encoding:** bit width, signed/unsigned, endianness, boolean and floating-point representation.
5. **String encoding:** standard UTF-8, modified UTF-8, UTF-16..., and how length is bounded.
6. **Framing:** record count, length prefix, delimiter, sentinel, or what EOF means.
7. **Bounds and validation:** count/length limits, value ranges, and checksums if needed.
8. **Compatibility:** rules when adding fields, removing fields, or changing types.

### Example: Adding a Version at the Beginning of a File

A schema can be designed as:

```text
[int magic = 0x4A494F31]
[short version = 1]
[int recordCount]
[record 1]
[record 2]
...
```

The writer calls `writeInt(magic)` → `writeShort(version)` → `writeInt(recordCount)` → write records. The reader must follow the exact order `readInt` → `readShort` → `readInt` → read records, validating magic/version before proceeding. This is an **illustrative format diagram**, not a universal Java standard file format.

When bumping a version, do not just "append a field at the end" and expect old readers to understand it. If old readers still read subsequent records, the extra field can be mistaken for the start of the next record. Compatibility mechanisms must be defined, such as headers/versions, length-prefixed records to skip unknown fields, or self-describing formats like Protocol Buffers. Do not confuse custom-designed binary records with Java Object Serialization (`ObjectOutputStream`/`ObjectInputStream`), which has its own format and rules.

## 10. Multiple Stream Layers, Files, and Buffering

You can combine buffering to reduce physical I/O calls without **changing field order**:

```java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(
                Files.newOutputStream(path)))) {
    out.writeInt(42);
    out.writeLong(123L);
}
```

This is an **illustrative snippet**, requiring `Path path`, imports for `java.nio.file.Files`, `java.io.BufferedOutputStream`, `java.io.DataOutputStream`, and `IOException` handling. `Files.newOutputStream(path)` by default may **create or truncate the file**. For critical data, choose the file path and open options intentionally.

Matching read:

```java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(
                Files.newInputStream(path)))) {
    int id = in.readInt();
    long value = in.readLong();
}
```

This is an **illustrative snippet**, requiring appropriate imports and `IOException` handling.

The write data flow travels from application through `DataOutputStream` → `BufferedOutputStream` → byte destination. The read side goes from byte source → `BufferedInputStream` → `DataInputStream` → application. Buffering improves byte transfer efficiency without inserting delimiters or altering the schema.

For files, close `DataOutputStream` to flush buffers down the chain. For sockets, `flush()` can push bytes currently held in buffers, but **does not mean the receiver has read or processed them successfully**. If the protocol requires confirmation, design an application-layer ACK/response.

Do not close a wrapper while the underlying stream is still needed; closing the outermost layer typically closes the layers it owns. Clearly design caller/callee closing responsibilities.

## 11. Testing Write-Read Correspondence

It is best to test binary formats with both **round-trip** and **golden bytes**.

### Round-trip

Write a record into a `ByteArrayOutputStream`, read it with `DataInputStream` over a `ByteArrayInputStream`, and compare every field. The runnable examples above use this technique. Also test:

- Boundary values: `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MAX_VALUE`, negative numbers, zero, boolean false.
- Empty strings, strings with Vietnamese diacritics, emojis, and NUL characters.
- Empty byte arrays, payloads larger than the read buffer size.
- Multiple consecutive records, valid count and invalid count.
- Data truncated mid-way through a 2/4/8-byte field or mid-way through a string payload.

### Golden bytes

Verify the exact output bytes against the published format. For example, `writeInt(0x01020304)` must write `01 02 03 04` in big-endian; `writeShort(0x0506)` next must produce `05 06`. Golden bytes catch cases where both writer and reader share **the exact same bug**: round-trip tests still pass, yet the data is incompatible with other languages/software.

### Deliberate wrong-order reading tests

Create a valid record, deliberately read `readShort` instead of `readInt`, or swap two fields. Expect **wrong values, EOFException, or validation failures** rather than assuming only one single error mode. Check error messages and recovery behavior: does it skip the record, abort the whole file, or request retransmission?

A good parser should retain **offset/record context** when reporting errors, e.g., "record 12, invalid field nameLength", instead of just "cannot read file".

## 12. Common Mistakes and Checklist

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Writing `int` but reading `short` | Cursor shifts by a 2-byte boundary | Use `readInt` matching `writeInt` |
| Writing fields A → B → C but reading A → C → B | Values are misinterpreted | Define a schema with clear field order |
| Writing UTF-8 string bytes but reading with `readUTF` | Wrong prefix/charset, possible EOF or Unicode errors | Align encode/decode pair and framing |
| Using `String.length()` as UTF-8 byte count | Under/over-reading with accented chars/emojis | Compute length from `getBytes(UTF_8).length` |
| Calling `read(byte[])` once and trusting it is full | Payload may be partially read | `readFully` or a loop handling returned byte count |
| Using `available()` to compute record length | Does not reflect data boundaries across all streams | Length prefix or schema/framing |
| Not validating input-declared lengths | May allocate too much memory or crash | Bound count/length before allocating |
| Swallowing all `EOFException` | Silently ignores truncated data | Only treat EOF as valid if the schema specifies it |
| Changing byte order without changing the decoder | Wrong numeric values | Agree on big-/little-endian |
| Adding a field without incrementing version | Old readers lose synchronization | Version/header and compatibility rules |
| Reading arbitrary bytes with a `Reader` | Charset decoding can alter bytes arbitrarily | For binary, use `InputStream`/`DataInputStream` |
| Reader opens file before writer flushes/closes | Data not fully flushed from buffers | Finish the writer before the reader reads |

**Checklist before saving or sending a binary protocol:**

- [ ] Document the field order from first byte to last byte.
- [ ] Define size, signedness, endianness, and data type of each field.
- [ ] Define string charset, length prefix byte width, and length unit.
- [ ] Explicitly specify how record count or end markers are determined.
- [ ] Verify writer/reader use matching API pairs and the same schema/version.
- [ ] Reject unreasonable lengths and counts before allocating.
- [ ] Test valid data, truncated data, wrong order, and trailing bytes.
- [ ] For multi-language formats, inspect actual bytes instead of relying only on Java round-trips.

**Self-practice exercise:** Design a format `[int count][int id][short age][int utf8Length][utf8NameBytes]` for two people. Write it with `DataOutputStream` and read it back with `DataInputStream`. Then intentionally swap the read order of `age` and `utf8Length`, observe where things start going wrong, and explain why the failure might not appear on the very first field.

**Takeaway:** **Write order is part of the binary data format.** Readers must adhere to the exact same order, sizes, and encoding. `DataOutputStream`/`DataInputStream` help read and write structured bytes, but it is the **schema agreed upon by both sides** that ensures data is understood correctly.
