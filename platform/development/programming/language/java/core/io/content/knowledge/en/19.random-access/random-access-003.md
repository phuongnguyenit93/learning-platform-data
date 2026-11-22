# Reading and Writing Primitive Data via DataInput and DataOutput in Java

`DataInput` and `DataOutput` are two interfaces in `java.io` that define **how to read and write structured binary data**: integers, floating-point numbers, characters, `boolean`s, and strings by convention. They are especially useful when storing records in files or transferring data between Java components. In the topic of **random access**, `RandomAccessFile` is an important example: it implements both interfaces while also providing `seek(long)` to read or modify data at a specific byte position.

This lesson explains the binary contract, how to combine streams and `RandomAccessFile`, how to design fixed-length records, how to guard against format mismatches, and the limitations of updating files in place.

## 1. Why are DataInput and DataOutput needed?

A binary file does not self-describe its data types. For example, the byte sequence `00 00 00 2A` may represent the integer 42 in big-endian byte order, but the program must **know in advance** that this is an `int` in order to read it correctly. If you simply write bytes and guess the types when reading, the result can easily be wrong or raise errors due to insufficient data.

The two interfaces act as a **contract for structure and field order**:

- `DataOutput` provides `writeInt`, `writeLong`, `writeDouble`, `writeBoolean`, `writeChar`, `writeUTF`, and other methods.
- `DataInput` provides the corresponding `readInt`, `readLong`, `readDouble`, `readBoolean`, `readChar`, `readUTF`, along with `readFully` and `skipBytes`.
- The program **decides the schema itself**: which field appears first, the meaning and length of each field, the format version, and the number of records.
- Both are **interfaces**, not concrete streams you can instantiate with `new DataInput()` or `new DataOutput()`.

Common implementations:

| Class | DataInput | DataOutput | Access pattern |
| --- | --- | --- | --- |
| `DataInputStream` | Yes | No | Sequential reading from an `InputStream`. |
| `DataOutputStream` | No | Yes | Sequential writing to an `OutputStream`. |
| `RandomAccessFile` | Yes | Yes | Reading/writing and moving positions in a file with `seek`. |

Distinguish `DataInputStream`/`DataOutputStream` from `ObjectInputStream`/`ObjectOutputStream`: this lesson writes **primitive values according to a self-defined schema**, without using Java object serialization.

## 2. Byte conventions: read in the exact order you wrote

The numeric methods of `DataInput`/`DataOutput` use **big-endian** byte order (most significant byte first). Common sizes:

| API pair | Byte count | Rules and notes |
| --- | ---: | --- |
| `writeBoolean` / `readBoolean` | 1 | Writes 1 for `true`, 0 for `false`; when reading, any non-zero byte is also treated as `true`. |
| `writeByte` / `readByte` | 1 | Reads as a signed `byte` (-128..127); `readUnsignedByte` returns 0..255. |
| `writeShort` / `readShort` | 2 | Signed `short`; `readUnsignedShort` returns 0..65535. |
| `writeChar` / `readChar` | 2 | A **UTF-16 code unit**, not necessarily an entire Unicode character if it is a surrogate pair. |
| `writeInt` / `readInt` | 4 | Signed `int`, big-endian. |
| `writeLong` / `readLong` | 8 | Signed `long`, big-endian. |
| `writeFloat` / `readFloat` | 4 | IEEE 754 bit representation; may include `NaN`/infinity. |
| `writeDouble` / `readDouble` | 8 | IEEE 754 bit representation; watch out for precision errors when used for money. |
| `writeUTF` / `readUTF` | Variable | String in **modified UTF-8**, with a 2-byte unsigned length prefix. |

For example, `writeInt(0x01020304)` produces four bytes in the exact order `01 02 03 04`. Reading it back with `readInt()` yields `0x01020304`. However, if you read with `readShort()` followed by `readInt()`, the read pointer becomes misaligned with the schema; subsequent fields will be misinterpreted or throw `EOFException`.

These rules apply across **all** compliant `DataInput`/`DataOutput` implementations, including `RandomAccessFile`. Never assume byte order depends on the CPU architecture. If interoperating with a little-endian format, you must use a reader/writer configured accordingly (such as `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)`) or swap bytes explicitly; the `readInt`/`writeInt` methods of the `DataInput`/`DataOutput` contract have no little-endian option.

## 3. Complete example: fixed-record file and updates via seek

Suppose we store member scores. Each record contains:

- `id`: `int` = 4 bytes.
- `points`: `long` = 8 bytes.
- `active`: `boolean` = 1 byte.

Total **13 bytes/record**, with no padding. The file starts with a header containing `magic`, `version`, and `count`, each an `int` (12 bytes total).

```text
Offset (byte)   Content                          Length
0..3            magic = 0x44494F31 ("DIO1")       4
4..7            version = 1                      4
8..11           count = 3                        4
12..24          record[0]                        13
25..37          record[1]                        13
38..50          record[2]                        13

Position of record[i] = 12 + i * 13
Within record[i]: id at +0, points at +4, active at +12
```

Goal: create the file sequentially using `DataOutputStream`, jump straight to the second record to add 500 points using `RandomAccessFile`, then read the entire file using `DataInputStream`. The example uses Java 17+, creates a temporary file, and cleans up at the end.

Save as **`DataIoRandomAccessDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInput;
import java.io.DataInputStream;
import java.io.DataOutput;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class DataIoRandomAccessDemo {
    private static final int MAGIC = 0x44494F31; // ASCII "DIO1"
    private static final int VERSION = 1;
    private static final int COUNT = 3;
    private static final int HEADER_BYTES = 3 * Integer.BYTES;
    private static final int RECORD_BYTES =
            Integer.BYTES + Long.BYTES + 1;

    private record Member(int id, long points, boolean active) {}

    private static void writeMember(DataOutput out, Member m)
            throws IOException {
        out.writeInt(m.id());
        out.writeLong(m.points());
        out.writeBoolean(m.active());
    }

    private static Member readMember(DataInput in) throws IOException {
        int id = in.readInt();
        long points = in.readLong();
        boolean active = in.readBoolean();
        return new Member(id, points, active);
    }

    private static long offsetOf(int index) {
        if (index < 0 || index >= COUNT) {
            throw new IndexOutOfBoundsException("index=" + index);
        }
        return HEADER_BYTES + (long) index * RECORD_BYTES;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("data-io-", ".bin");
        try {
            // Pass 1: write a new file sequentially using DataOutputStream.
            try (DataOutputStream out = new DataOutputStream(
                    new BufferedOutputStream(Files.newOutputStream(file)))) {
                out.writeInt(MAGIC);
                out.writeInt(VERSION);
                out.writeInt(COUNT);
                writeMember(out, new Member(101, 1200, true));
                writeMember(out, new Member(102, 2250, false));
                writeMember(out, new Member(103, 900, true));
            }

            // Pass 2: access record[1] directly using RandomAccessFile.
            try (RandomAccessFile raf =
                    new RandomAccessFile(file.toFile(), "rw")) {
                long second = offsetOf(1); // byte 25
                raf.seek(second);
                Member before = readMember(raf);
                if (before.id() != 102) {
                    throw new IOException("Sai bản ghi tại byte " + second);
                }

                // Overwrite only the 8 bytes of the points field.
                raf.seek(second + Integer.BYTES);
                raf.writeLong(before.points() + 500);
            }

            // Pass 3: read sequentially using DataInputStream.
            try (DataInputStream in = new DataInputStream(
                    new BufferedInputStream(Files.newInputStream(file)))) {
                int magic = in.readInt();
                int version = in.readInt();
                int count = in.readInt();

                if (magic != MAGIC || version != VERSION ||
                        count != COUNT) {
                    throw new IOException("Header không hợp lệ");
                }

                System.out.printf(
                        "magic=%08X version=%d count=%d%n",
                        magic, version, count);

                for (int i = 0; i < count; i++) {
                    Member member = readMember(in);
                    System.out.printf(
                            "id=%d points=%d active=%b%n",
                            member.id(), member.points(), member.active());
                }

                System.out.println("EOF after records: " +
                        (in.read() == -1));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run:

```bash
javac DataIoRandomAccessDemo.java
java DataIoRandomAccessDemo
```

Expected stdout (independent of the temporary file path):

```text
magic=44494F31 version=1 count=3
id=101 points=1200 active=true
id=102 points=2750 active=false
id=103 points=900 active=true
EOF after records: true
```

**Why is the code divided into three passes?**

1. When writing, `DataOutputStream` provides `writeInt`, `writeLong`, and `writeBoolean`, but it only advances forward through an `OutputStream`. Closing the stream before opening the file for editing ensures buffers are flushed and released.
2. `RandomAccessFile(file.toFile(), "rw")` opens the file with read and write permissions, while implementing both `DataInput` and `DataOutput`. `seek(25)` places the pointer at the start of the second record. After `readMember`, the pointer has moved 13 bytes; `seek(25 + 4)` returns to the exact first byte of `points`. `writeLong` overwrites exactly eight bytes, leaving `id` and `active` intact.
3. `DataInputStream` reads the header and then exactly `count` records in the **same order and types** they were written. `in.read() == -1` confirms that the stream has ended right after the expected records, with no trailing bytes left over.
4. Both helper methods accept `DataOutput` and `DataInput` instead of concrete stream classes, so they work seamlessly with both sequential streams and `RandomAccessFile`.

The sample code uses `long` for `points`. When representing monetary values, store the count of smallest currency units in a `long` along with a clear unit/scale convention, or use a well-defined `BigDecimal` representation; do not rely on `double` for exact decimal arithmetic.

## 4. RandomAccessFile and pointer position

`RandomAccessFile` has these common open modes:

- `"r"`: read-only; the file must exist, and calling write methods fails.
- `"rw"`: read and write; creates the file if it does not exist. File creation alone does not guarantee a valid schema.
- `"rws"` and `"rwd"`: require synchronous update persistence respectively, potentially at higher cost; actual semantics and guarantees also depend on the OS/filesystem.

Related methods:

| Method | Meaning |
| --- | --- |
| `seek(long pos)` | Sets the next byte position to read/write, starting from 0; negative positions are invalid. |
| `getFilePointer()` | Gets the current byte position. |
| `length()` | Gets the file size in bytes. |
| `setLength(long newLength)` | Truncates or extends the file; extending does not guarantee valid record data by default. |
| `readInt()`/`writeInt(int)` | Reads/writes 4 bytes at the pointer, then advances the position by 4 bytes. |
| `readFully(byte[])` | Reads the exact length of the array or throws an error on premature EOF. |

Keep in mind:

- `seek` past EOF **does not add data on its own**; writing there can lengthen the file and leave an intervening gap without valid record content.
- `RandomAccessFile` operates on regular files and accepts a `File` or OS path string; unlike `Files.newByteChannel(Path, ...)`, which can work with other NIO providers.
- Do not modify a file with `RandomAccessFile` while simultaneously reading through an older `BufferedInputStream`: the buffer may still hold stale data from before the update. Close/sync the write session and open a fresh reader when consistent results are required.
- Fixed-size records allow direct offset computation. If a record contains variable-length fields such as `writeUTF`, subsequent records' positions **are no longer** `headerSize + index * recordSize`. In that case, you need an offset index table, length-prefixed framing, or a different storage design.

When computing offsets from untrusted indices and sizes, check bounds and use `Math.multiplyExact`/`Math.addExact` (with `long`) to detect overflow. Verify `offset + recordSize <= file.length()` before reading if you want to report clear error messages.

## 5. Sequential reading: helper methods of DataInput

Besides `readInt` and `readLong`, `DataInput` provides useful byte-handling methods:

- **`readFully(byte[] dst)`** reads all `dst.length` bytes or throws `EOFException`. `readFully(dst, off, len)` fills a slice of the array. Useful for payloads with a known length.
- **`readUnsignedByte()`** and **`readUnsignedShort()`** return an unsigned `int` for the bytes read. The same byte `FF` is interpreted as -1 by `readByte()`, but as 255 by `readUnsignedByte()`.
- **`skipBytes(int n)`** may skip **fewer than n bytes** (especially near EOF); always check the return value and do not treat it as a guaranteed seek.
- **`readUTF()`** reads strings encoded according to the `writeUTF()` convention; do not use it to read arbitrary UTF-8 strings.
- **`readLine()`** on `DataInput` is deprecated; for text, use `BufferedReader` with an explicit charset.

Distinguish `InputStream.read(byte[])` (which may return **fewer** bytes than requested even before EOF) from `DataInput.readFully` (which tries to read everything or fails). Example of a binary frame with a 4-byte length + payload:

```java
int length = in.readInt();
if (length < 0 || length > 1_048_576) {
    throw new IOException("Kích thước payload không hợp lệ: " + length);
}
byte[] payload = new byte[length];
in.readFully(payload);
```

This is a **snippet** assuming `in` is an open `DataInput` and `IOException` is handled or propagated. The 1 MiB limit is only an example; in production applications choose limits based on your protocol contract and available resources. For large payloads, do not allocate arrays directly from arbitrary untrusted length fields: read in chunks with a quota and verify actual bytes read.

## 6. Strings: writeUTF is not standard UTF-8

`DataOutput.writeUTF(String)` writes a **2-byte unsigned** prefix containing *the byte count of the encoded payload*, followed by the string in **modified UTF-8**. `DataInput.readUTF()` reads this exact format. Notable differences:

- The length prefix is the encoded byte count, **not the number of Java characters**.
- `writeUTF` limits the encoded payload to at most 65,535 bytes and may throw `UTFDataFormatException` if exceeded.
- Modified UTF-8 encodes null characters (`\u0000`) and UTF-16 surrogates differently from standard UTF-8; strings written/read via `writeUTF/readUTF` are not inherently compatible with UTF-8 parsers in other languages.
- `writeChars(String)` writes each UTF-16 code unit as 2 bytes and **does not** write a length prefix; `writeBytes(String)` writes only the low 8 bits of each `char`, which can silently drop Unicode information. Avoid these two methods for general text interchange.

A valid matching example given an `out` variable of type `DataOutput` and an `in` variable of type `DataInput` positioned at the corresponding spot in the same format:

```java
out.writeUTF("Tiếng Việt");   // Write modified UTF-8 with length.
String text = in.readUTF();  // Read using that exact format.
```

These two lines are **separate illustrations**, not sequential statements run on the same object. Do not call `readUTF` on data written with `Files.writeString(..., UTF_8)` because that output has no length prefix and uses standard UTF-8.

If you need a format readable across languages, you can define **standard UTF-8 + 4-byte big-endian length**:

```java
// Writer side (out: DataOutput, text: String)
byte[] bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
out.writeInt(bytes.length);
out.write(bytes);

// Reader side (in: DataInput)
int len = in.readInt();
if (len < 0 || len > 1_048_576) {
    throw new IOException("Độ dài chuỗi không hợp lệ");
}
byte[] encoded = new byte[len];
in.readFully(encoded);
String decoded = new String(
        encoded, java.nio.charset.StandardCharsets.UTF_8);
```

These are two independent snippets following the same schema, using externally declared variables. The reader must obey the exact same byte order, charset, and limits. The `new String(bytes, UTF_8)` constructor replaces malformed byte sequences by default; if you need to **reject** invalid UTF-8, use a `CharsetDecoder` with `CodingErrorAction.REPORT`. When data integrity is critical, also specify Unicode normalization, empty fields, and how `null` is represented in the schema.

## 7. Designing a safe and evolvable binary file

A record layout is a contract between writer and reader. A well-designed file typically includes:

1. **Magic number**: confirms the file type before reading other fields; for example, the four bytes of `0x44494F31`.
2. **Version**: distinguishes layout versions. If a version is unsupported, reject it or migrate using explicit rules; do not guess unfamiliar schemas.
3. **Count/length**: indicates the number of records or payload size; validate for reasonable bounds before looping or allocating memory.
4. **Record layout**: specifies types, order, byte sizes, units, encoding, sentinel values, and whether padding exists.
5. **Integrity policy**: when needed, use checksums/hashes, write to a temporary file, and perform controlled replacement; headers and counts alone do not prove the data is uncorrupted.

The example in Section 3 can be verified for a valid file:

```text
expectedLength = 12 + 3 * 13 = 51 bytes
```

If the size does not match, there may be truncation, extra trailing bytes, or a different layout version. For files with variable-length payloads, validate field by field rather than using a fixed formula. Never trust `count` blindly on untrusted input: an enormous count can trigger long loops, I/O errors, or resource exhaustion.

**Random access supports in-place updates when field sizes do not change.** Writing a new `long` over 8 existing bytes works cleanly; inserting a longer string into the middle of a file would shift all subsequent bytes, and `RandomAccessFile` does not automatically shift data or rebuild indexes. If you need variable-length records or complex lookups, consider an indexed/append-only structure or a database depending on your requirements.

## 8. Common errors and root causes

| Symptom | Root cause | Prevention |
| --- | --- | --- |
| `EOFException` in `readInt/readLong/readFully` | The file ends before the field's required byte count. | Verify header, count/length, and file bounds; handle corrupted data. |
| Values read back as nonsense | Wrong field order, signed/unsigned mismatch, wrong byte order. | Document the schema clearly; read in the exact same order; test with byte fixtures. |
| `UTFDataFormatException` | Corrupted modified UTF-8 or string too long during `writeUTF`. | Use matching API pairs; enforce encoded byte limits; choose another format when needed. |
| Wrong offset during `seek` | Computing index by element count while forgetting the header or miscalculating primitive sizes. | Use size constants and `long` arithmetic; check bounds. |
| Unintended file truncation | Opening an existing file with default `Files.newOutputStream(path)`. | Distinguish create, append, and update; maintain a clear overwrite policy. |
| Reading stale data | Unflushed buffered output stream or stale buffered reader. | Finish/close the writer before re-reading; avoid mixing stale buffers. |
| File corruption after interrupted write | Multi-field update interrupted mid-way; non-transactional writes. | Write the new version to a temporary file, verify, and replace using a controlled policy with backups. |
| Sudden memory spike | Trusting an input length/count field and allocating a huge array. | Enforce quotas and check for overflow; stream large payloads. |

Multi-byte read methods specified by `DataInput` throw `EOFException` when too few bytes remain. By contrast, `InputStream.read()` returns `-1` on normal EOF. **Do not catch `EOFException` as a substitute for a schema with count/length** when the file already defines a record count; an unexpected EOF usually indicates truncated or corrupted data.

`DataInputStream` and `DataOutputStream` should be closed via `try-with-resources`. When wrapping `BufferedInputStream`/`BufferedOutputStream`, closing the outer stream also closes the underlying stream. `flush()` pushes buffered bytes to the OS stream, but **does not mean** the data is durably persisted on the storage device. Similarly, `RandomAccessFile` handles resource closing, but does not turn a sequence of updates into a transaction.

## 9. When should you choose another solution?

- **Sequential streams + DataInput/DataOutput:** good for compact binary protocols, files with clear schemas, and one-way write followed by one-way read.
- **RandomAccessFile:** suitable for local OS files with fixed-size records that need reading/writing at specific offsets and where concurrent access can be controlled.
- **`FileChannel` or `SeekableByteChannel`:** appropriate when you need byte-position access, buffers, NIO interoperability, or high-volume I/O; `ByteBuffer` lets you choose byte order, unlike the `DataInput`/`DataOutput` contract.
- **`ObjectOutputStream`/`ObjectInputStream`:** intended for Java object serialization, which is a different mechanism with its own versioning, interoperability, and deserialization security concerns; do not casually substitute it for a fixed binary schema.
- **Database or schema-aware file formats:** better suited when you have variable-length records, multiple concurrent writers, queries/indexes, transactions, or long-term schema evolution needs.

**Do not default to Java serialization** just because you need to store a few `int` and `long` values. When designing a custom format, you also take responsibility for compatibility, error handling, and data integrity; the right choice depends on your data characteristics and maintenance horizon.

## 10. Practice exercises

**Exercise 1 — Offset calculation and byte inspection.** Using the example layout, determine the first byte of `record[2]` and the first byte of its `active` field. Answer: `12 + 2 * 13 = 38` and `38 + 4 + 8 = 50`. Try `raf.seek(50); raf.readBoolean()` on the file before deleting it to verify the value `true`.

**Exercise 2 — Safe update.** Add a method `updatePoints(Path file, int index, long increment)`. Open the file in `"rw"` mode, verify magic/version/count, the computed offset, and the file length, then use `Math.addExact` for the new score and overwrite only the corresponding 8 bytes. Explain why multiple writers still need synchronization.

**Exercise 3 — Detecting file corruption.** After creating the file, call `setLength(30)` on `RandomAccessFile` to intentionally truncate the records. Run the reader program and observe when `EOFException` is thrown. Then add a check for `file.length() == HEADER_BYTES + count * RECORD_BYTES` to detect size mismatches earlier.

**Exercise 4 — Variable-length strings.** Add `writeUTF` at the end of a record and observe why `RECORD_BYTES` is no longer constant. Propose an offset index table or length-prefixed framing to access variable-sized records accurately.

**Self-check:** Why doesn't `DataInput` store data types automatically? When is `readUnsignedByte` more appropriate than `readByte`? Why is `readFully` more useful than `read` for binary frames? Why is `writeUTF` not equivalent to standard UTF-8? And why is `seek` only safe once positions, sizes, and schema are clearly defined?

The principles to carry into real projects are: **design the format first, keep read/write order symmetric, verify headers/lengths, compute exact byte offsets, and manage resources/file lifecycles carefully**. `DataInput`/`DataOutput` handle converting primitives to bytes; data integrity, concurrency safety, and compatibility remain the program's responsibility.
