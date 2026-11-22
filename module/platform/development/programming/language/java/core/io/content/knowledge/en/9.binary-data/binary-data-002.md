# DataInputStream and DataOutputStream: Reading and Writing Typed Binary Data in Java

When a program needs to write multiple values such as a version number, count, status flag, or floating-point number to a binary file, manually converting each value into bytes is error-prone. Java provides two classes, **`DataOutputStream`** and **`DataInputStream`**, to write and read primitive data types using a **deterministic binary format**.

These two classes operate on **byte streams**, typically wrapping an existing `OutputStream` or `InputStream`. They are useful when both sides agree on **field order, field types, and byte representation**. They **do not know record structure on their own** and do not automatically reconstruct arbitrary Java objects.

## 1. What Do the Two Classes Do?

- **`java.io.DataOutputStream`**: accepts Java values such as `int`, `long`, `boolean`, `double`, `char`, and certain string forms, then writes them to an `OutputStream` as bytes.
- **`java.io.DataInputStream`**: reads bytes from an `InputStream` and decodes them via methods such as `readInt()`, `readLong()`, `readBoolean()`, `readDouble()`, `readChar()`, `readUTF()`, etc.
- **`DataOutput` and `DataInput`**: the two interfaces implemented by these classes, defining the contract for writing and reading typed data.

Class hierarchy:

~~~text
OutputStream
  └── FilterOutputStream
       └── DataOutputStream    (implements DataOutput)

InputStream
  └── FilterInputStream
       └── DataInputStream     (implements DataInput)
~~~

A typical pipeline:

~~~text
                  WRITE
Java values --DataOutputStream--> BufferedOutputStream --> FileOutputStream --> file.bin
                  READ
Java values <--DataInputStream--- BufferedInputStream <-- FileInputStream <-- file.bin
~~~

**Decisive point:** `DataOutputStream` does not add self-describing type metadata. If you write `int`, `boolean`, `long` in sequence, the reader must know to call `readInt()`, `readBoolean()`, `readLong()` **in the exact same order**. Reading with different types or order can produce wrong values or hit end-of-stream.

## 2. Binary Format of Primitive Types

The `DataOutput` and `DataInput` methods follow specific representation rules that do not arbitrarily depend on charset or CPU byte order. For multi-byte numbers, data is written in **big-endian** order (most significant byte first).

| Write | Corresponding Read | Bytes | Notes |
|---|---|---:|---|
| `writeBoolean(v)` | `readBoolean()` | 1 | `false` writes byte 0; `true` writes byte 1; any non-zero value reads as `true` |
| `writeByte(v)` | `readByte()` / `readUnsignedByte()` | 1 | Writes low 8 bits; reads signed or unsigned |
| `writeShort(v)` | `readShort()` / `readUnsignedShort()` | 2 | 16-bit integer, big-endian |
| `writeChar(v)` | `readChar()` | 2 | One 16-bit **UTF-16 code unit**, not a UTF-8 string |
| `writeInt(v)` | `readInt()` | 4 | 32-bit integer, big-endian |
| `writeLong(v)` | `readLong()` | 8 | 64-bit integer, big-endian |
| `writeFloat(v)` | `readFloat()` | 4 | According to IEEE 754 bits specified by Java |
| `writeDouble(v)` | `readDouble()` | 8 | According to IEEE 754 bits specified by Java |
| `writeUTF(text)` | `readUTF()` | 2 + N | 2-byte unsigned length, followed by N bytes of **modified UTF-8** |

Example:

~~~text
writeInt(0x01020304)  -> 01 02 03 04
writeShort(300)       -> 01 2C
writeBoolean(true)    -> 01
~~~

The bytes are shown in **hexadecimal (base 16)**. Writing `0x01020304` with `writeInt` does not produce four ASCII characters `"0102"`; it produces exactly **four bytes** `01 02 03 04`. Attempting to view binary data as text with `new String(bytes, UTF_8)` will not reflect the field structure.

For a negative `int`, `writeInt` writes the 32-bit (two's complement) representation in big-endian. `readInt` restores the exact same `int` value if all four original bytes are intact and unmodified.

### Signed and Unsigned Reads

`writeByte(255)` writes the exact byte `FF`, yet `readByte()` returns `-1` because it interprets it as a signed 8-bit number. If the record specification defines this as a value from 0 to 255, use `readUnsignedByte()` to get `255`. Similarly, `readUnsignedShort()` returns a value from 0 to 65535. Never change the read method solely because "the value looks weird"; follow the **data schema**.

### `writeChar` Is Not "Writing a UTF-8 Character"

`writeChar('A')` writes two bytes `00 41`, whereas encoding the string `"A"` in UTF-8 produces one byte `41`. A Unicode character outside the BMP is represented by a **surrogate pair** in a Java `String`, so you cannot assume "one user-perceived character = one `writeChar` call". When exchanging general text, explicitly define the encoding and length rule instead of using `writeChar` as a general string format.

## 3. Stream Composition and Resource Closing Rules

Typically, code opens the file itself using `Files.newOutputStream(path)`, wraps it in `BufferedOutputStream` to reduce writes to the lower layer, and finally uses `DataOutputStream` to write typed values:

~~~java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(Files.newOutputStream(path)))) {
    out.writeInt(42);
    out.writeBoolean(true);
}
~~~

This is an **illustrative snippet**; it requires importing `java.io.*` and `java.nio.file.*`, having a `Path path`, and handling/declaring `IOException`. If the code opens the source/destination stream itself, it **owns** the resource and using `try-with-resources` on the outermost wrapper is appropriate. Calling `close()` on the outermost decorator closes the inner layers under the standard JDK contract; `BufferedOutputStream` flushes remaining buffered data to the underlying layer when closed.

Reading back:

~~~java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    int count = in.readInt();
    boolean enabled = in.readBoolean();
}
~~~

The read matches the **two fields** that were written. However, a helper that only **borrows** an `InputStream` or `OutputStream` from its caller should not arbitrarily close its wrapper, because closing the wrapper may also close the resource owned by the caller. The API contract must clearly specify who closes and when.

**Note:** `DataOutputStream.flush()` forwards the flush request to the underlying output; however, flushing does not mean data is guaranteed to be durably persisted on disk. Never call `close` just to fulfill a flush need on a borrowed stream.

## 4. Complete Java 17 Example: Writing and Reading the Same Format

The following example uses `ByteArrayOutputStream` and `ByteArrayInputStream` so it can run standalone easily, though the wrapper architecture is the same when writing/reading files. The record consists of:

1. An `int` **magic** field: `0x01020304`, taking 4 bytes.
2. A `short` field with value `300`, taking 2 bytes.
3. A `boolean` field `true`, taking 1 byte.
4. A `String` field written via `writeUTF`, having a 2-byte length prefix and **modified UTF-8** text payload.

Save as **`BinaryDataStreamsDemo.java`**:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;

public class BinaryDataStreamsDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream storage = new ByteArrayOutputStream();
        String message = "A" + '\0' + "é";

        try (DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(storage))) {
            out.writeInt(0x01020304);
            out.writeShort(300);
            out.writeBoolean(true);
            out.writeUTF(message);
        }

        byte[] encoded = storage.toByteArray();
        System.out.println("Total bytes: " + encoded.length);

        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(new ByteArrayInputStream(encoded)))) {
            int magic = in.readInt();
            int count = in.readUnsignedShort();
            boolean enabled = in.readBoolean();
            String decoded = in.readUTF();

            System.out.printf("Magic: 0x%08X%n", magic);
            System.out.println("Count: " + count);
            System.out.println("Enabled: " + enabled);
            System.out.println("Text equal: " + message.equals(decoded));
            System.out.println("Text length: " + decoded.length());
            System.out.println("Next byte: " + in.read());
        }
    }
}
~~~

Compile and run in the directory containing the source file:

~~~bash
javac --release 17 -encoding UTF-8 BinaryDataStreamsDemo.java
java BinaryDataStreamsDemo
~~~

Expected output:

~~~text
Total bytes: 14
Magic: 0x01020304
Count: 300
Enabled: true
Text equal: true
Text length: 3
Next byte: -1
~~~

Exact breakdown of the **14-byte** size:

- `writeInt` writes 4 bytes `01 02 03 04`.
- `writeShort(300)` writes 2 bytes `01 2C`.
- `writeBoolean(true)` writes 1 byte `01`.
- `writeUTF("A" + '\0' + "é")` writes 2 length bytes **`00 05`**, followed by 5 bytes `41 C0 80 C3 A9`.
- Total **4 + 2 + 1 + 2 + 5 = 14 bytes**.
- `DataInputStream.readUnsignedShort()` reads back the 2-byte field and returns `300`. `readUTF()` knows to read the exact length prefix and the 5 bytes of that string.
- `decoded.length()` is `3`: the character `A`, the NUL character `\0`, and the character `é`, each being one UTF-16 code unit. The string is not printed directly to `System.out` because the NUL character is unsuitable for terminal display.
- After reading the four fields properly, `in.read()` returns `-1` because no bytes remain. That does not mean `readInt()` at EOF would return `-1`: `readInt()` **throws `EOFException`** when fewer than four bytes remain.

`ByteArrayOutputStream` retains written bytes even after the `DataOutputStream` wrapper is closed. This is a property of the in-memory stream; for files/sockets, closing the wrapper can still release or terminate the underlying resource.

## 5. `writeUTF` and `readUTF`: Modified UTF-8 Is Not Standard UTF-8

The name `writeUTF` can easily lead to wrong conclusions. This method uses **modified UTF-8**, which differs from standard UTF-8:

- Writes **two big-endian bytes** describing the encoded payload length that follows, so the maximum encoded length is **65535 bytes** (not a maximum of 65535 Java characters).
- The `U+0000` (NUL) character is encoded as **`C0 80`** instead of a `00` byte as in standard UTF-8.
- Other BMP characters appropriately use one, two, or three bytes. Characters outside the BMP are represented by two **UTF-16 surrogate code units**, each encoded separately as three bytes (six bytes total), unlike standard UTF-8's four-byte mechanism.
- `readUTF()` accepts the matching format. Reading with an ordinary UTF-8 decoder like `new String(payload, UTF_8)` is not guaranteed to be correct, especially for NUL and non-BMP characters.
- `writeUTF` may throw `UTFDataFormatException` if the required modified UTF-8 length exceeds the limit; `readUTF` may throw an error if the UTF format is invalid.

Therefore, **`writeUTF`/`readUTF` are suitable when both sides understand the exact Java DataInput/DataOutput format**. They are not the default choice when generating standard UTF-8 for external systems to read.

Comparison table:

| Write Approach | Byte Structure | Correct Reader |
|---|---|---|
| `out.writeUTF(text)` | 2-byte length + modified UTF-8 | `in.readUTF()` |
| `out.write(text.getBytes(UTF_8))` | Only UTF-8 bytes, no length | Needs boundary known externally |
| `out.writeInt(bytes.length); out.write(bytes)` | 4-byte length + standard UTF-8 bytes | `readInt()` then `readFully`, then decode UTF-8 |
| `Files.writeString(path, text, UTF_8)` | Text UTF-8 bytes | `Files.readString(path, UTF_8)` or an appropriate Reader |

**Do not replace `readUTF()` with `readLine()`.** `DataInputStream.readLine()` is deprecated because it converts bytes to characters incorrectly for common charsets. For line-oriented text data, use `BufferedReader` with an explicit charset such as UTF-8.

## 6. Storing Standard UTF-8 Strings by Defining Your Own Length

Suppose an application must communicate with a non-Java system and your specification requires **length-prefixed UTF-8**: the first four bytes are the payload length as a big-endian `int`, followed by exact N UTF-8 bytes.

**Method demonstration** code, using `java.io.*` and `java.nio.charset.StandardCharsets` imports:

~~~java
static void writeUtf8(DataOutputStream out, String text)
        throws IOException {
    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    out.writeInt(bytes.length);
    out.write(bytes);
}

static String readUtf8(DataInputStream in) throws IOException {
    int length = in.readInt();
    final int MAX_TEXT_BYTES = 1_048_576; // Application-defined limit.
    if (length < 0 || length > MAX_TEXT_BYTES) {
        throw new IOException("Độ dài chuỗi không hợp lệ: " + length);
    }
    byte[] bytes = new byte[length];
    in.readFully(bytes);
    return new String(bytes, StandardCharsets.UTF_8);
}
~~~

Unlike `writeUTF`, this approach explicitly enforces standard `UTF-8` and a 4-byte length prefix. When reading, **validate the length before allocating** to prevent malformed or untrusted data from causing excessive memory usage.

In the example, `new String(bytes, UTF_8)` may **replace malformed UTF-8 bytes** according to the constructor's decoder policy. If the protocol requires rejecting invalid data, use a `CharsetDecoder` with `CodingErrorAction.REPORT` to fail explicitly. Additionally, the demonstration code is not yet a full protocol with versioning, checksums, or acknowledgments; those features depend on application requirements.

### Why Must `readFully` Be Used?

The following snippet is **not safe enough** when you need to receive exactly N bytes:

~~~java
byte[] buffer = new byte[length];
in.read(buffer); // Wrong if assuming this read always returns all length bytes.
~~~

A single `read(byte[])` call can return fewer bytes than requested, especially over a network. `DataInputStream.readFully(buffer)` loops until the buffer is full or throws `EOFException` if the source ends early. Even with files, you should use the API matching the contract rather than relying on luck.

In a complex record, every variable-sized field (string, array, list) needs a **boundary rule**: a length prefix, an appropriate delimiter, or a known element count. `DataInputStream` only provides tools to read bytes/types; it **does not infer record boundaries on its own**.

## 7. Wrong Order, Wrong Types, and Missing Fields Errors

Suppose the writer does:

~~~java
out.writeInt(1000);      // 4 bytes
out.writeBoolean(true);  // 1 byte
out.writeLong(9000L);    // 8 bytes
~~~

Correct reader:

~~~java
int number = in.readInt();
boolean flag = in.readBoolean();
long id = in.readLong();
~~~

These are **two illustrative snippets** where `out` is a `DataOutputStream` and `in` is a `DataInputStream`, not a standalone program. If the reader calls `readBoolean()` first, it consumes the most significant byte of `int 1000`, not the written flag; all subsequent fields become misaligned. The result may **look valid while being wrong**, or trigger `EOFException`.

### When Does `EOFException` Occur?

- `readInt()` needs a full 4 bytes, `readLong()` needs a full 8 bytes, `readDouble()` needs a full 8 bytes. When insufficient bytes remain, these methods throw `EOFException` (a subtype of `IOException`).
- `readFully(byte[])` throws `EOFException` if the source ends before filling the array.
- `read()` inherited from the byte stream contract returns `-1` at end of stream, because it only asks for **one byte** or the EOF signal.
- `readUTF()` may throw `EOFException` if data ends prematurely or `UTFDataFormatException` if encoded data is invalid.

Use exceptions meaningfully: **a file cut off mid-record** indicates incomplete data. Never catch `EOFException` and treat it as "record read successfully" when the structure requires all fields to be present.

### `available()` Is Not File Length or Guaranteed Remaining Bytes

`DataInputStream.available()` reflects how many bytes can be read without blocking per the underlying stream's contract, not a reliable way to predict the entire remaining data of a network stream or file. Never use `available() >= 4` as a general condition to decide whether an `int` can be read. Once you know the schema, read using `readInt`/`readFully` and handle `EOFException` properly.

## 8. Writing Real Files: Lifecycle, Overwriting, and Buffering

Example code that opens and owns its binary file:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class BinaryFileExample {
    static void write(Path file, int version, long timestamp)
            throws IOException {
        try (DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(Files.newOutputStream(file)))) {
            out.writeInt(version);
            out.writeLong(timestamp);
        }
    }

    static long readTimestamp(Path file) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(file)))) {
            int version = in.readInt();
            if (version != 1) {
                throw new IOException("Unsupported version: " + version);
            }
            return in.readLong();
        }
    }
}
~~~

This is a **compilable utility class** without a `main` method. Callers can invoke `write(file, 1, someTimestamp)` and then `readTimestamp(file)` to retrieve `someTimestamp`.

Notes:

1. `Files.newOutputStream(file)` with default options may **create a new file or truncate an existing file**. If you want to avoid overwriting, choose an option such as `StandardOpenOption.CREATE_NEW` and define an error-handling strategy.
2. `try-with-resources` closes streams **opened by your code**, even if read/write operations throw an exception. You do not need to close each wrapper manually inside the block.
3. `BufferedOutputStream` may retain bytes in its buffer, so proper flush/close lifecycle management is necessary. Closing at the right time does not by itself guarantee data is durably persisted to the storage device.
4. Checking the **version** field on read helps avoid applying the wrong schema as the format evolves. If the file contains multiple records, you must add a record count/length rule or define an end marker.
5. For critical data, an interrupted write can leave a file with **only partial bytes**. When preserving the old file is needed, you can write to a temporary file and replace it using a safe update strategy appropriate for the filesystem.

## 9. Distinguishing from Other I/O APIs

| Tool | When to Use? | What Can It Not Do on Its Own? |
|---|---|---|
| `DataInputStream/DataOutputStream` | Reading/writing typed primitives in deterministic binary | Does not define object schemas, does not create a self-describing format |
| `InputStream/OutputStream` | General byte reading/writing | Has no direct `readInt`, `writeDouble` |
| `BufferedInputStream/BufferedOutputStream` | Adding buffering to reduce lower-layer interactions | Does not understand data types |
| `Reader/Writer` | Reading/writing characters and text by charset | Unsuitable for arbitrarily interpreting all binary bytes |
| `ObjectInputStream/ObjectOutputStream` | Java object serialization via its own mechanism | Not the same format as `DataInputStream`; do not confuse them |
| `ByteBuffer` | Representing bytes and reading/writing primitives in a buffer, configurable byte order | Does not define or transmit a protocol on its own |
| `Files.copy` / `InputStream.transferTo` | Copying raw byte data as-is | Does not parse primitive fields |

`DataInputStream` and `DataOutputStream` are very useful for small, stable, well-controlled formats. However, when cross-language communication, complex schema evolution, or long-term compatibility is needed, consider a format/protocol with an explicit specification. Whichever tool you pick, document the exact **field order**, **field width**, **endianness**, **charset**, and **version**.

## 10. Common Mistakes

| Misconception | Consequence | Correct Approach |
|---|---|---|
| Writing `writeInt` then reading `readShort` | Reads too few bytes, subsequent fields misaligned | Read in the exact order and type written |
| Thinking numbers are written as digit strings | Trying to decode a binary file as text, "garbled" output | Understand primitives are written as binary bytes |
| Forgetting big-endian | Writing an external parser with reversed bytes | Document most-significant-byte-first order in the spec |
| Thinking `writeUTF` is standard UTF-8 | External readers receive the wrong payload | Use matching `readUTF` or define standard UTF-8 |
| Calling `read(byte[])` once and assuming it's enough | Remaining bytes may be lost | `readFully` or a read loop matching the contract |
| Reading length from a file and allocating unboundedly | Memory errors or vulnerability to spoofed data | Validate length before allocating |
| Using `available()` as total remaining bytes | Fails on streams reporting only non-blocking bytes | Use schema and explicit EOF handling |
| Failing to close wrappers you own | Lost buffered bytes or resource leaks | `try-with-resources` at the owning layer |
| Closing a wrapper over a caller-provided stream | May close a shared resource prematurely | Clarify ownership; borrowing helpers must not close |
| Writing to an existing file without considering open options | Old file may be truncated | Choose `StandardOpenOption` matching requirements |
| Thinking `DataInputStream` automatically understands any binary format | Wrong values read or exceptions | Read according to the application/protocol schema |

## 11. Self-Check

**Q1.** Code writes `writeInt(0x01020304)`; which four hex bytes are in the file?

> **Answer:** `01 02 03 04` because `DataOutputStream` uses **big-endian** for multi-byte integers.

**Q2.** Writing `writeByte(255)`, what does `readByte()` return? What should you use to get 255?

> **Answer:** `readByte()` returns `-1` due to signed 8-bit interpretation. Use `readUnsignedByte()` to get `255`.

**Q3.** Why does `writeUTF("A" + '\0' + "é")` take 7 bytes instead of 5 bytes?

> **Answer:** Modified UTF-8 of the string is **5 bytes** (`41 C0 80 C3 A9`), plus **2 bytes for the length prefix** making **7 bytes**.

**Q4.** `DataInputStream.readInt()` encounters EOF with only two bytes left: does it return `-1` or throw an exception?

> **Answer:** Throws **`EOFException`** because there are not enough four bytes to form an `int`. `-1` is the EOF sentinel value of `InputStream.read()`.

**Q5.** Should you read an N-byte string with a single `in.read(bytes)` call and assume you got all the data?

> **Answer:** No. A single read can return fewer than N bytes. Use **`readFully(bytes)`** after validating N, or a read loop ensuring all N bytes are read.

**Q6.** Can `readUTF()` be used to read an ordinary UTF-8 file?

> **Answer:** Not in general. `readUTF()` requires **two length bytes** and **modified UTF-8** data per `DataInput`. An ordinary UTF-8 text file does not inherently have that structure.

**Q7.** Code borrows a framework's `OutputStream` and wraps it in `DataOutputStream`. Should `DataOutputStream` be closed at the end of the helper?

> **Answer:** Only if the contract delegates stream-closing ownership to the helper. If the helper only borrows it, closing the wrapper may also close the framework's output. The caller/owning layer controls the lifecycle.

## Key Takeaways

**`DataOutputStream` encodes primitives into bytes; `DataInputStream` decodes bytes into primitives.** Both sides must agree on field order, field widths, big-endian order, and string format. Remember three special points: **`writeUTF/readUTF` uses modified UTF-8 with a 2-byte length prefix**, **`readFully` guarantees reading the full payload or reporting EOF**, and **wrapper closing must follow stream ownership**.

**References:** [Java SE 17 — `DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), [`DataOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html), [`DataInput`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html), [`DataOutput`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html).
