# File pointer, `seek`, and `getFilePointer` in Java

## 1. What is the file pointer position?

In **random access**, a program can read or write at any byte position in a file without sequentially reading all preceding bytes. In `java.io.RandomAccessFile`, the current position used for reading and writing is called the **file pointer**.

The file pointer is a **byte offset from the beginning of the file**, starting at **0**. It is not a memory address, not a line number, and not necessarily a character position in a Unicode string.

Example of a five-byte file:

```text
Offset:       0     1     2     3     4
Content:     10    20    30    40    50
                              ^
                       file pointer = 3
```

Calling `read()` at pointer 3 reads the byte value 40 (decimal) and advances the pointer to 4. Calling `seek(1)` moves the pointer back to 1; the next read retrieves the byte at offset 1.

Core concepts:

- **`seek(position)`** explicitly sets the absolute read/write position.
- **`getFilePointer()`** returns the current position.
- **A successful read/write operation** advances the pointer by the actual number of bytes read/written.
- **`length()`** reports the file length in bytes, regardless of where the pointer currently is.

This API is well suited for binary files with a clear structure, such as fixed-length records, header regions, indexes, and data that must be updated at known offsets.

## 2. `RandomAccessFile` and related methods

Instantiate it with a path and an access mode:

```java
try (RandomAccessFile raf = new RandomAccessFile("data.bin", "rw")) {
    // Read/write at byte offsets.
}
```

This is an **illustrative snippet**; a complete program must import `java.io.RandomAccessFile` and handle `IOException`.

Common modes:

| Mode | Meaning |
| --- | --- |
| `"r"` | Read-only; the file must exist, and write operations are rejected |
| `"rw"` | Read and write; can create the file if it does not exist |
| `"rws"` | Read/write requiring synchronous writes of content and metadata to the storage device |
| `"rwd"` | Read/write requiring synchronous writes of content changes to the storage device |

`"rws"` and `"rwd"` incur higher I/O overhead depending on the system; they do not replace a crash-safe transaction design for power loss or multi-step related updates.

| Method | Important behavior |
| --- | --- |
| `long getFilePointer()` | Gets the current byte offset |
| `void seek(long pos)` | Sets the pointer to the absolute offset `pos` |
| `long length()` | Gets the current file size in bytes |
| `int read()` | Reads an unsigned byte (0–255) or returns `-1` at EOF |
| `void readFully(byte[] b)` | Reads the exact requested number of bytes or throws `EOFException` |
| `void write(int b)` | Writes the low eight bits of the integer and advances the pointer by one byte |
| `void writeInt(int value)` | Writes a 32-bit integer as **4 bytes**, in big-endian order |
| `int readInt()` | Reads **4 bytes** as an integer; throws `EOFException` if fewer bytes remain |
| `void setLength(long newLength)` | Truncates or extends the logical length of the file |

`seek` requires a non-negative position. `seek(-1)` causes `IOException`. All of `seek`, `getFilePointer`, `length`, reads, and writes can throw `IOException` due to file/system errors. Always close resources using `try-with-resources`.

## 3. How does the file pointer move?

Imagine a file that starts empty, with the pointer at offset 0.

| Operation | Result | Pointer after operation | `length()` after operation |
| --- | --- | ---: | ---: |
| Open empty file | No bytes yet | 0 | 0 |
| `writeInt(2026)` | Writes 4 bytes at offsets 0–3 | 4 | 4 |
| `writeByte(65)` | Writes 1 byte at offset 4 | 5 | 5 |
| `seek(0)` | Moves back to the start of the file, no read/write | 0 | 5 |
| `readInt()` | Reads 4 bytes | 4 | 5 |
| `readUnsignedByte()` | Reads one byte with value 65 | 5 | 5 |
| `read()` at EOF | Returns `-1` | 5 | 5 |
| `seek(4)` | Moves back to the fifth byte's position | 4 | 5 |
| `writeByte(66)` | **Overwrites** the byte at offset 4 | 5 | 5 |

**`seek` itself neither reads nor writes any bytes**, so it never increases the file length on its own. Only moving the pointer and then reading/writing at that position affects data.

Misconceptions to avoid:

- **Offsets differ from "character" indices**: UTF-8 text has multi-byte characters.
- **The fifth byte is at offset 4**, not 5.
- After reading 4 bytes from offset 0, the pointer is at **4**, which is the position used for the next operation.
- **Writing at an existing offset normally overwrites**, rather than inserting and shifting trailing data to the right.

## 4. Standalone runnable Java 17+ example: observing every pointer change

This program creates a temporary file, writes two values, moves and inspects the pointer, and then overwrites the last byte. The temporary file is closed and cleaned up.

**File `FilePointerDemo.java`**

```java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilePointerDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("file-pointer-", ".bin");

        try {
            try (RandomAccessFile raf =
                     new RandomAccessFile(path.toFile(), "rw")) {

                raf.setLength(0);
                raf.writeInt(2026);
                System.out.println("Sau writeInt: " + raf.getFilePointer());

                raf.writeByte(65);
                System.out.println("Sau writeByte: " + raf.getFilePointer());

                raf.seek(0);
                System.out.println("Sau seek(0): " + raf.getFilePointer());

                int year = raf.readInt();
                System.out.println("Gia tri int: " + year);
                System.out.println("Sau readInt: " + raf.getFilePointer());

                int lastByte = raf.readUnsignedByte();
                System.out.println("Byte thu nam: " + lastByte);
                System.out.println("Read EOF: " + raf.read());
                System.out.println("Pointer tai EOF: " + raf.getFilePointer());

                raf.seek(4);
                System.out.println("Sau seek(4): " + raf.getFilePointer());

                raf.writeByte(66);
                System.out.println("Sau ghi de: " + raf.getFilePointer());

                raf.seek(0);
                System.out.println(
                    "Du lieu cuoi: " + raf.readInt()
                    + ", " + raf.readUnsignedByte());
                System.out.println("Do dai file: " + raf.length());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile and run:

```bash
javac FilePointerDemo.java
java FilePointerDemo
```

**Exact stdout when all file operations succeed:**

```text
Sau writeInt: 4
Sau writeByte: 5
Sau seek(0): 0
Gia tri int: 2026
Sau readInt: 4
Byte thu nam: 65
Read EOF: -1
Pointer tai EOF: 5
Sau seek(4): 4
Sau ghi de: 5
Du lieu cuoi: 2026, 66
Do dai file: 5
```

Explanation:

1. `writeInt(2026)` always writes **4 bytes** per the `DataOutput` contract, so the pointer moves from 0 to 4.
2. `writeByte(65)` writes one byte and increments the pointer to 5.
3. `seek(0)` returns to the beginning, then `readInt()` consumes four bytes and reconstructs the number 2026.
4. `readUnsignedByte()` reads byte 65 at offset 4 and advances the pointer to EOF = 5.
5. `read()` at EOF returns `-1` without consuming any bytes; the pointer stays at 5.
6. `seek(4)` and `writeByte(66)` replace the value 65 with 66 at the same offset. No bytes are inserted, and `length()` remains 5.

This program demonstrates the nature of **byte-positioned reading/writing**, as opposed to forward-only stream reading.

## 5. `seek` past EOF: valid, but requires caution

**EOF** (*end of file*) is at offset `length()`. For a 5-byte file, existing bytes occupy offsets 0 through 4; a pointer at 5 indicates the position immediately after the last byte.

`RandomAccessFile.seek(pos)` **can set the pointer past EOF** as long as `pos` is non-negative. For example:

```java
// Suppose raf points to a file that is exactly 5 bytes long.
raf.seek(10);
System.out.println(raf.getFilePointer()); // 10
System.out.println(raf.length());         // 5
```

This is just an illustrative snippet requiring an open `raf`. `seek(10)` **does not** make the file 10 bytes long. Calling `read()` past EOF returns `-1`. If you call `writeByte(7)` after `seek(10)`, the file is extended to hold the new byte at offset 10, and the final length becomes **11**.

**Never assume the gap between the old EOF and the newly written byte is always filled with zeros.** The Java contract does not guarantee the values of intermediate bytes when extending a file; exact behavior depends on the platform and file system. If your data format requires specific byte values, write those bytes explicitly.

`setLength(newLength)` has its own rules:

- If `newLength` is smaller than the current length, the file is truncated. If the previous pointer was greater than the new length, the pointer is reset to the new length.
- If `newLength` is greater than the current length, the file is extended, but **the contents of the new bytes are unspecified**.
- If you only change the length via `setLength` and the pointer does not exceed the new length, the pointer remains unchanged.

A common mistake is thinking `seek(1000)` "allocates" 1,000 bytes or assuming `setLength(1000)` always initializes the extended region with zeros.

## 6. Practical example: locating and updating fixed-length records

Random access is effective when every record has a **fixed byte size**. Suppose each record consists of:

| Field | Write method | Size |
| --- | --- | ---: |
| `id` | `writeInt` | 4 bytes |
| `quantity` | `writeInt` | 4 bytes |
| **Total per record** |  | **8 bytes** |

With a 0-based record `index`, the starting position of the record is:

\[
\text{offset} = \text{index} \times 8
\]

For example, the third record (index = 2) starts at offset **16**. This formula works because every record has the same 8-byte size, regardless of integer values. If variable-length UTF-8 strings were used, you could no longer simply multiply the index by 8 without a different packing scheme.

**File `FixedRecordDemo.java`**

```java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class FixedRecordDemo {
    private static final int RECORD_SIZE = 8;

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("records-", ".bin");

        try {
            try (RandomAccessFile raf =
                     new RandomAccessFile(path.toFile(), "rw")) {
                raf.setLength(0);

                raf.writeInt(101);
                raf.writeInt(5);

                raf.writeInt(102);
                raf.writeInt(7);

                raf.writeInt(103);
                raf.writeInt(9);

                long thirdOffset = 2L * RECORD_SIZE;
                raf.seek(thirdOffset);
                int thirdId = raf.readInt();
                int thirdQuantity = raf.readInt();
                System.out.println("Ban ghi thu ba: "
                        + thirdId + ", " + thirdQuantity);
                System.out.println("Pointer sau doc: "
                        + raf.getFilePointer());

                long secondQuantityOffset = 1L * RECORD_SIZE + 4;
                raf.seek(secondQuantityOffset);
                raf.writeInt(70);

                raf.seek(1L * RECORD_SIZE);
                int secondId = raf.readInt();
                int secondQuantity = raf.readInt();
                System.out.println("Ban ghi thu hai: "
                        + secondId + ", " + secondQuantity);
                System.out.println("Kich thuoc tep: " + raf.length());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Run:

```bash
javac FixedRecordDemo.java
java FixedRecordDemo
```

**Exact stdout when operations succeed:**

```text
Ban ghi thu ba: 103, 9
Pointer sau doc: 24
Ban ghi thu hai: 102, 70
Kich thuoc tep: 24
```

**Why does this happen?** There are three 8-byte records, totaling 24 bytes. `seek(16)` moves to the third record; two `readInt()` calls read 8 bytes, leaving the pointer at 24. The `quantity` field of the second record starts at offset `1 * 8 + 4 = 12`; `seek(12)` followed by `writeInt(70)` overwrites only bytes 12–15 without affecting other records or changing the file length.

In real applications, compute offsets using `long` from the start (e.g., `(long) index * RECORD_SIZE`) to avoid 32-bit integer overflow; verify `index >= 0`, check that `offset` does not overflow, and ensure `offset + RECORD_SIZE <= raf.length()` before reading an existing record. If the file can be modified concurrently by another actor, the length check may also become stale before the read occurs.

## 7. EOF, partial reads, and exceptions

`read()` can return `-1` when no bytes remain. However, **not every read method uses `-1`**:

- `readInt()` requires all four bytes; missing any byte throws `EOFException`.
- `readUnsignedByte()` requires exactly one byte; calling it at EOF also throws `EOFException`.
- `readFully(byte[])` means it must retrieve the full requested byte count; if the file ends early, it throws `EOFException`.
- `read(byte[])` may return fewer bytes than the array's length; never assume a single read always fills the array.

For example, if a file has only three bytes, executing `raf.seek(0); raf.readInt();` throws `EOFException` because `readInt` needs four bytes. When a multi-byte read fails, do not assume the pointer rolls back to its position before the read: some bytes may have already been consumed. If you need "all-or-nothing" read behavior, the program must implement proper error handling and position restoration.

A defensive practice when reading fixed records is to check the file length against the computed offsets, and **still catch and handle I/O errors during the actual read**.

## 8. Pointer movement when reading/writing data types and strings

`RandomAccessFile` implements the methods of `DataInput` and `DataOutput`. Therefore, the pointer advance depends on the **number of encoded bytes**, not the number of calls or characters.

| Call | Bytes normally written/read |
| --- | ---: |
| `writeByte(int)` / `readUnsignedByte()` | 1 |
| `writeShort(int)` / `readShort()` | 2 |
| `writeChar(int)` / `readChar()` | 2 |
| `writeInt(int)` / `readInt()` | 4 |
| `writeLong(long)` / `readLong()` | 8 |
| `writeFloat(float)` / `readFloat()` | 4 |
| `writeDouble(double)` / `readDouble()` | 8 |
| `writeUTF(String)` / `readUTF()` | **Variable** length |

Multi-byte primitive types are encoded in **big-endian** order in `RandomAccessFile`. For example, the integer `0x01020304` is written as four bytes `01 02 03 04`; the pointer advances by 4.

`writeUTF` uses **modified UTF-8** with a **2-byte** prefix containing the length of the encoded payload. The number of bytes written **is not simply equal to** `string.length()` or `string.getBytes(StandardCharsets.UTF_8).length`. If you need direct random access to the Nth element in a file of variable-length strings, you must maintain an offset index, a length table, or a predefined fixed-record format.

When combining multiple read/write operations on the same file, you must keep track of the binary format and the offset of each field. Reading a `writeInt` value with `readShort` does not automatically "understand" the structure; it simply reads two bytes and leaves the pointer at the corresponding position.

## 9. `RandomAccessFile`, `FileChannel`, and concurrency

`RandomAccessFile` is an easy-to-learn API when you need to read/write typed data at a specific position. In NIO, `FileChannel` lets you work with `ByteBuffer`, manipulate positions via `position(long)`, or perform explicit positional reads/writes such as `read(buffer, position)` and `write(buffer, position)`.

If you obtain a channel via `raf.getChannel()`, **the channel's position and `RandomAccessFile`'s file pointer are linked**. Changing the position on one side or performing reads/writes that advance the position can affect the position seen from the other side. Do not mix operations on the same handle while assuming two independent pointers exist.

Additionally, **the file pointer is mutable state**. If multiple threads share a single `RandomAccessFile` and execute `seek(offset)` → `writeInt(value)` pairs, another thread can change the pointer in between, causing the write to happen at the wrong offset. To preserve logical operations, you need appropriate synchronization, or positional read/write APIs where suitable. The right choice also depends on atomicity, consistency, and file-locking requirements; never assume a shared file pointer is safe in concurrent applications.

Good practice is to clearly own resources via `try-with-resources`, avoid sharing a handle without a synchronization design, and explicitly document the binary format stored in the file.

## 10. Common mistakes and how to fix them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Thinking `seek(5)` advances 5 bytes forward | Reads/writes at the wrong position | `seek` sets an **absolute offset**; to advance from the current position, compute `getFilePointer() + delta` and check for overflow |
| Using record index instead of byte offset | Misaligned data | `seek(index * recordSize)` using `long` arithmetic |
| Using `writeInt` while thinking it advances 1 byte | Wrong field offset calculations | Remember an `int` takes 4 bytes |
| Thinking `seek` extends the file on its own | Unexpected file length | Only writes or `setLength` can extend the file |
| Expecting `writeByte` to "insert" a byte | Overwrites existing data | Design a data-shifting routine when insertion is needed |
| Unconditionally calling `readInt` at EOF | `EOFException` | Check bounds and handle exceptions |
| Treating characters as bytes | Wrong offsets for Unicode text | Track actual byte counts and charset/encoding format |
| Assuming newly extended regions are always 0 | Undefined data | Initialize required values with explicit writes |
| Sharing one pointer across unsynchronized threads | Corrupted reads/writes at wrong positions | Synchronize access or switch to an explicit positional design |
| Forgetting to close `RandomAccessFile` | Descriptor/file-lock leaks | `try-with-resources` |

## 11. Self-check

Suppose a `RandomAccessFile` newly opened in `"rw"` mode points to an empty file:

```java
raf.writeLong(10L);       // A
raf.seek(2);              // B
raf.writeByte(99);        // C
raf.seek(8);              // D
int value = raf.read();   // E
```

This is a code snippet for reasoning, not a complete Java program. Assuming all I/O calls succeed:

- After **A**, the pointer is **8**, and the file length is **8**.
- After **B**, the pointer is **2**, and the length is still **8**.
- After **C**, the pointer is **3**, and the length is still **8** because only one byte at offset 2 is overwritten.
- After **D**, the pointer is **8**.
- At **E**, `value == -1` because the pointer is at EOF; the pointer remains **8**.

This exercise shows that the file pointer is **the byte coordinate for the next I/O operation**, while `length()` is the data length; the two values often match at EOF, but they do not mean the same thing.

## 12. Key takeaways

1. **`getFilePointer()` returns the current byte offset** as a `long`, not a line/character count.
2. **`seek(pos)` sets a non-negative absolute offset**; it may go past EOF, but it does not change `length()` by itself.
3. Reads and writes advance the pointer by the **number of bytes processed**; writing at an existing position overwrites data.
4. Watch out for **EOF, `EOFException`, offset overflow, uninitialized extended regions, byte layout, and I/O errors**.
5. For fixed-length records, compute `offset = index * recordSize` in `long` and verify bounds.
6. Do not share a file pointer across threads without synchronization; always close files with `try-with-resources`.

**Official documentation:** Java SE 17 API for `java.io.RandomAccessFile`, `java.io.DataInput`, `java.io.DataOutput`, and `java.nio.channels.FileChannel`.
