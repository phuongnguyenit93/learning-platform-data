# `RandomAccessFile.length()`, `setLength()`, and Unwritten Data Regions

## 1. Purpose and scope

When performing random access with `java.io.RandomAccessFile`, a program can move the pointer to any valid byte position, read or write at that position, inspect the file length, and explicitly change the length. Three operations that are easily confused with one another are:

- `length()`: queries the **current logical length of the file**, in bytes.
- `seek(position)`: changes the **file pointer position** used for the next read/write operation.
- `setLength(newLength)`: changes the **logical length** of the file, either truncating or extending it.

This lesson focuses on the behavior of `RandomAccessFile` (Java 17+), especially the bytes residing in an extended region that have not yet been explicitly written with defined values by the application. You will learn when reads return EOF, why you must not assume the extended portion contains all `0` bytes, and how to explicitly initialize data when the file format requires deterministic results.

## 2. Two independent quantities: length and pointer

For a `RandomAccessFile raf`:

| API | Unit and meaning | Changes file length? |
| --- | --- | --- |
| `raf.length()` | `long`: total number of bytes in the file at the time of the call | No |
| `raf.getFilePointer()` | `long`: byte position of the next read/write operation | No |
| `raf.seek(pos)` | Sets the pointer to offset `pos` (from the beginning of the file, 0-based) | No, only moves the pointer |
| `raf.read()` | Reads the current byte, returning 0–255 or `-1` on EOF | No |
| `raf.write(value)` | Writes at the pointer and advances the pointer by one byte | **Possibly**, if writing at/beyond the end of the file |
| `raf.setLength(n)` | Sets the new logical length to `n` bytes | Yes, if `n` differs from the previous length |

Example of a file containing three written bytes `ABC`:

```text
offset             0    1    2    3
written bytes      A    B    C    | EOF
length() = 3                     ^
getFilePointer() can be 0, 2, 3, 10... depending on seek/read/write
```

Offsets are **byte offsets**, not Unicode character positions. A Vietnamese character encoded in UTF-8 can occupy multiple bytes; `length()` does not report the number of characters. Calling `seek(10)` on a 3-byte file is valid (as long as the position is non-negative); the pointer will be at offset 10, while `length()` remains 3. Until a write or length-changing operation occurs, the region between offsets 3 and 10 does not become part of the file merely because of `seek`.

Distinguish between these two concepts:

- **EOF (end of file)** is the boundary at the end of the logical length. If the pointer is at or past EOF, `read()` returns `-1`.
- **A region not explicitly written by the application** can **lie inside the logical length** after the file is extended. Do not treat such a region as EOF just because the application has not written content into it.

Both `length()` and `getFilePointer()` return `long` because files can exceed the range of `int`. File measurements can change when another process modifies the same file; these APIs do not create a consistent snapshot for subsequent operations.

## 3. `setLength(newLength)` when shrinking a file

If the current length is `L` and you call `setLength(n)` with `0 <= n < L`, bytes from offset `n` onward are removed from the logical contents of the file. This is **truncation**, an operation that can cause data loss.

Example before truncation:

```text
offset       0   1   2   3   4   5   6
byte         A   B   C   D   E   F   | EOF
length = 6
pointer = 5
```

After `setLength(3)`:

```text
offset       0   1   2   3
byte         A   B   C   | EOF
length = 3
pointer = 3
```

**Pointer rule:** if the current position is greater than the new length when shrinking, `RandomAccessFile` sets the pointer to `newLength`. If the current position is less than or equal to the new length, the pointer stays unchanged. For example: if the pointer is at 1 when truncating to 3, it stays at 1; if the pointer is at 5 when truncating to 3, it becomes 3.

Calling `setLength(0)` discards all file contents without deleting the file itself and without creating a backup. Use this call carefully on files holding valuable data. Truncating a file does not guarantee that the discarded portion can be recovered by extending the file back.

## 4. `setLength(newLength)` when extending a file

If the current length is `L` and `newLength > L`, the file is extended to the exact logical length `newLength`. According to the `RandomAccessFile` API contract, **the contents of the extended portion of the file are not defined**.

```text
Initial: length = 3
offset             0   1   2   3
content            A   B   C   | EOF

After setLength(8):
offset             0   1   2   3   4   5   6   7   8
content            A   B   C   ?   ?   ?   ?   ?   | EOF
                               └──── region with no application-defined values
length = 8
```

The `?` symbols do **not** represent EOF; they are valid byte positions inside the file, but you must not rely on their values under the Java contract. On many operating systems and file systems, such "holes" may read back as `0` bytes, but that is not a portable basis for designing a data format. How the file system physically allocates storage also does not mean the application has written and confirmed data there.

When **extending** a file, `setLength` does not move a pointer that was already at a valid position. The pointer may remain at an older offset or even beyond the new EOF from an earlier `seek`. Only the truncation rule when the pointer exceeds the new length adjusts the pointer automatically.

Notes:

- `setLength` accepts a non-negative `long`; a negative value throws `IllegalArgumentException`.
- If the file is not opened for writing (such as `"r"` mode), the length change request cannot succeed and may throw `IOException`.
- Extending, truncating, or querying metadata can also fail due to permissions, I/O errors, disk space limits, quotas, or file system issues. Do not suppress `IOException`.
- `setLength` does not guarantee that space is "preallocated" as actual physical disk blocks. File systems supporting sparse files may allocate blocks only when bytes are actually written.

## 5. `seek` past EOF followed by a write: what does the gap mean?

Suppose a file contains `ABC` (3 bytes long). After `seek(10)`:

```text
0  1  2  3  4  5  6  7  8  9 10
A  B  C  | EOF                  ^ pointer
length = 3; pointer = 10
```

Calling `read()` at this point returns `-1` because the pointer lies outside the logical length. If instead you call `writeByte('Z')` at offset 10, the write gives the file a length of at least 11 bytes. The byte at offset 10 was explicitly written by the application as `Z`; **bytes at offsets 3–9 must not be interpreted as validly initialized data**.

```text
0  1  2  3  4  5  6  7  8  9 10 11
A  B  C  ?  ?  ?  ?  ?  ?  ?  Z  | EOF
length = 11; pointer = 11
```

Do not conflate "never-written region", "region created by extension", and "EOF" into a single state. If a file format tracks valid records, you need a mechanism to mark created records—such as a bitmap, header, sentinel that you explicitly write—or you must thoroughly initialize every byte the program expects to read.

## 6. Runnable Java 17+ example: verifying length, pointer, and EOF

Save the file as **`RandomAccessLengthDemo.java`**:

```java
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class RandomAccessLengthDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("raf-length-", ".bin");

        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(path.toFile(), "rw")) {

                // Three explicit ASCII bytes: A B C
                raf.write(new byte[] {65, 66, 67});
                System.out.println("after write: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                // Moves pointer only; definitely does not lengthen the file yet.
                raf.seek(10);
                System.out.println("after seek(10): length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());
                System.out.println("read beyond EOF=" + raf.read());

                // Extend the file, but do not rely on unwritten bytes.
                raf.seek(3);
                raf.setLength(12);
                System.out.println("after setLength(12): length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                // Write and read a single byte whose value we know for sure.
                raf.seek(10);
                raf.writeByte('Z');
                raf.seek(10);
                System.out.println("known byte at 10="
                        + (char) raf.readUnsignedByte());

                raf.seek(12);
                System.out.println("read at 12=" + raf.read());

                // Pointer is at 12; truncating file to 2 => pointer moves to 2.
                raf.setLength(2);
                System.out.println("after setLength(2): length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                raf.seek(0);
                byte[] prefix = new byte[2];
                raf.readFully(prefix);
                System.out.println("remaining prefix="
                        + new String(prefix, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac RandomAccessLengthDemo.java
java RandomAccessLengthDemo
```

Expected stdout when I/O operations succeed:

```text
after write: length=3, pointer=3
after seek(10): length=3, pointer=10
read beyond EOF=-1
after setLength(12): length=12, pointer=3
known byte at 10=Z
read at 12=-1
after setLength(2): length=2, pointer=2
remaining prefix=AB
```

Why does this example produce deterministic output? The program **only reads bytes that were explicitly written** (`ABC`, `Z`) or reads at the EOF position (returning `-1`). It never prints or inspects the values of the extended region at offsets 3–9 and 11. `Files.createTempFile` creates a dedicated new file; `try-with-resources` closes `RandomAccessFile` before `finally` deletes the file.

If the machine does not allow creating/writing/deleting files in the temporary directory, the operation will throw an error and the example will not produce the full stdout above; that is an I/O environment error, not a change to byte-offset rules.

## 7. Initializing the extended region so data has deterministic values

If a file format requires new bytes to be 0 (such as an array of fixed records), **write zeros across the entire region to be initialized** instead of trusting `setLength` to do so under the API contract.

Complete example **`InitializeExtendedRegion.java`**:

```java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class InitializeExtendedRegion {
    private static void fillWithZeros(
            RandomAccessFile raf, long from, long endExclusive)
            throws IOException {
        if (from < 0 || endExclusive < from) {
            throw new IllegalArgumentException("Invalid byte interval");
        }

        byte[] zeros = new byte[8192];
        raf.seek(from);
        long remaining = endExclusive - from;

        while (remaining > 0) {
            int count = (int) Math.min((long) zeros.length, remaining);
            raf.write(zeros, 0, count);
            remaining -= count;
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("raf-initialize-", ".bin");
        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(path.toFile(), "rw")) {
                raf.write(new byte[] {10, 20});

                long originalLength = raf.length();
                long targetLength = originalLength + 5;

                raf.setLength(targetLength);
                fillWithZeros(raf, originalLength, targetLength);

                raf.seek(0);
                byte[] bytes = new byte[(int) raf.length()];
                raf.readFully(bytes);
                System.out.println(Arrays.toString(bytes));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac InitializeExtendedRegion.java
java InitializeExtendedRegion
```

Stdout on success:

```text
[10, 20, 0, 0, 0, 0, 0]
```

Mechanism: the program writes the first two bytes (`10`, `20`), extends the length from 2 to 7, and then writes **exactly five `0` bytes** across offsets 2–6. Because that region was explicitly written by the application, subsequent reads can rely on the `0` values (assuming no other actor modifies the file).

This is a small example meant to print the whole file. For large files, **do not** allocate a byte array of size `raf.length()`; read/write in bounded chunks, enforce limits, and check for overflow when calculating offsets. The `fillWithZeros` method writes in 8192-byte blocks to avoid allocating a massive array for the region being initialized.

**Important trade-off:** explicitly writing gigabytes of `0` bytes takes significant time and I/O, and can negate sparse-storage benefits. If the system only needs to distinguish whether a record exists or not, metadata tracking record status is usually far better than zero-initializing huge regions.

## 8. `read()`, `readFully()`, and unwritten contents

Read methods can also be misunderstood:

| Operation | When pointer is at or past EOF | When pointer is inside an uninitialized extended region |
| --- | --- | --- |
| `read()` | Returns `-1` | May read a byte; **do not rely on the returned value** |
| `read(byte[])` | Returns `-1` when no bytes can be read due to EOF | May return a byte count; data in an uninitialized region has no application-guaranteed value |
| `readFully(buffer)` | Throws `EOFException` if fewer than requested bytes remain | May complete if enough bytes exist within the logical length, but does not prove the bytes are a valid record |
| `length()` | Returns the total current length | Includes the extended portion of the file even though its contents are undefined |

`readFully` is helpful when the format requires reading exactly `N` bytes and you want to detect missing data caused by EOF. However, it **cannot by itself prove** that all `N` bytes were meaningfully initialized by the application. That is the job of the file format (header, record count, record status, checksum, or corresponding metadata).

For example, with the 3-byte file `ABC`: `seek(2)` followed by `readFully(new byte[2])` throws `EOFException` because only 1 byte remains. Conversely, after `setLength(10)`, reading 2 bytes from offset 2 may succeed in returning two bytes by length, yet the byte at offset 3 belongs to a region where the application never wrote a defined value.

For `read(byte[])`, never assume it always fills the entire array in a single call; check the return value or use `readFully` when an exact byte count is required.

## 9. Logical length, physical storage, and sparse files

When you call `setLength(1_000_000_000L)`, `length()` can return one billion bytes even though the process has not written a billion bytes of data. Many file systems support **sparse files**, where regions without actual disk blocks are mapped or allocated according to file system policies.

Three concepts must be kept distinct:

1. **Logical size:** the file length reported by Java via `length()` or `Files.size(path)`.
2. **Allocated storage:** the actual disk blocks/storage allocated by the file system; this can differ significantly from the logical size.
3. **Initialized application data:** the bytes actually written by the application, or verified by format evidence to be interpretable as valid data.

`RandomAccessFile.setLength` is not an API that guarantees physical block allocation or guarantees that enough disk space exists for all future writes. Sparse files, quotas, compression, and network file systems cause actual storage behavior to vary. If you need to preallocate physical storage with specific guarantees, look into OS/file-system-specific APIs instead of treating `setLength` as a portable guarantee.

Do not interpret a large logical size as owning that much reserved disk space or being guaranteed to fill the entire file without hitting `IOException`. Also do not use `FileStore` space statistics to verify whether individual bytes have been initialized.

## 10. Applied scenario: a random-access record format

Suppose a file stores fixed-length 32-byte records with a 16-byte header:

```text
header        record 0       record 1       record 2
[0 .. 15]     [16 .. 47]     [48 .. 79]     [80 .. 111]
```

The starting offset of record `i` is `16 + i * 32` (in **bytes**, with `i >= 0`). `raf.seek(offset)` allows reading or writing a record without scanning all preceding records. An important question: if you have only written record 0 and record 2, is record 1 valid?

**You cannot answer that using `length()` alone.** Writing record 2 extends the logical size past record 1. A 32-byte read at offset 48 can succeed based on logical size, even though the application never defined those bytes as record 1. Appropriate design approaches depending on requirements include:

- Maintaining a record count/bitmap/slot-status table and **writing the valid-status marker only after writing the full payload** (considering crash safety in real deployments).
- Initializing all readable slots with a default value explicitly written by the application, with a defined convention for what that value means.
- Writing a header containing the format version, record size, and validity metadata; checking offsets/lengths before interpreting bytes.

When computing `offset = headerSize + index * recordSize`, validate the input index, check for `long` overflow (`Math.multiplyExact` / `Math.addExact` can help), verify record size, and check access permissions. An arithmetically valid `seek` does not mean valid data exists at that position.

## 11. Comparison of related APIs

| API | Notable point |
| --- | --- |
| `RandomAccessFile.length()` | Current logical length (bytes) |
| `RandomAccessFile.setLength(n)` | Can shrink **or extend** to `n`; extended region has undefined contents |
| `RandomAccessFile.seek(n)` | Moves pointer only; without a write, does not change length |
| `Files.size(path)` | Retrieves logical size via path; can also fail if metadata cannot be read |
| `FileChannel.size()` | Retrieves file size via channel |
| `FileChannel.truncate(n)` | If `n` is less than current size, truncates to `n`; if `n` >= current size, **does not extend the file** |
| `FileChannel.position(n)` | Changes channel position; changing position alone does not extend the file |

Pitfall to avoid: calling `channel.truncate(1000)` on a 10-byte file **is not equivalent** to `raf.setLength(1000)`. `FileChannel.truncate` only shrinks the file when the specified size is smaller than the current size. Even though they operate on the same file, the APIs have different contracts.

If you simultaneously use `RandomAccessFile` and its `getChannel()`, the file descriptor/channel position is shared; understand how operations update the position and avoid assuming they are independent. In learning examples, operating on a single `RandomAccessFile` instance keeps behavior simple and easy to verify.

## 12. Common pitfalls, testing, and error handling

1. **Assuming `seek(largeOffset)` extends the file:** only a write after seeking or calling `setLength` can change the length.
2. **Assuming the extended portion is always `0`:** Java leaves those contents undefined; explicitly write any required data.
3. **Using `length()` as the count of written records:** "holes" can exist within the logical length; track valid records via metadata.
4. **Thinking `setLength(0)` rewinds the pointer without losing data:** it deletes all contents. To move back to the start, just call `seek(0)`.
5. **Ignoring the pointer rule during truncation:** if the pointer exceeds `newLength`, the API resets it to `newLength`. Check `getFilePointer()` whenever code relies on position.
6. **Assuming extension performs physical preallocation:** logical size, allocated size, and guaranteed writability are different things.
7. **Not handling exceptions:** `seek(-1)` and `setLength(-1)` are invalid; I/O operations can fail due to permissions, external file changes, or exhausted storage.
8. **Confusing bytes with characters:** handle binary offsets in bytes; if using UTF-8, define explicit encoding and record structure.
9. **Writing/truncating a file in use by another process without coordination:** can cause lost data, overlapping writes, or inconsistent reads. Permissions, locks, and update protocols must be properly designed.
10. **Testing values not guaranteed by the API:** portable tests should assert `length`, pointer rules, EOF, and explicitly written bytes—never assert values of unwritten regions.

A test suite should include these cases:

- New file has length 0; after `seek(100)`, `length()` is still 0.
- Write 3 bytes; `length()` equals 3; reading at offset 3 returns `-1`.
- `setLength(8)`; `length()` equals 8, pointer remains unchanged if not exceeding truncation condition.
- After explicitly writing the extended region, reading back those exact bytes succeeds.
- `setLength(2)` on a longer file; bytes after offset 1 no longer belong to the logical file, and a pointer beyond 2 is reset to 2.
- `setLength(0)` followed by reading from the beginning reports EOF.
- Test negative values, read-only mode, and appropriate I/O errors, avoiding turning environment failures into false conclusions about unwritten contents.

## 13. Self-check questions

1. A file is 5 bytes long. After `seek(100)`, what are `length()` and `getFilePointer()` respectively? What happens if you call `read()`?
2. A file is 5 bytes long, with the pointer at 4. After `setLength(20)`, what are the length and pointer? Can you assert that the byte at offset 19 equals 0?
3. A file is 20 bytes long, with the pointer at 18. After `setLength(7)`, what is the pointer? Are bytes at offsets 7–19 still readable as current file data?
4. Why might `readFully(new byte[5])` at offset 10 after `setLength(20)` read all 5 bytes without proving it is a valid record?
5. If you need to initialize 2 GiB of `0` bytes in an application-verifiable way, how do you avoid allocating a massive array? What is the trade-off with sparse storage?
6. Do `FileChannel.truncate(100)` and `RandomAccessFile.setLength(100)` produce the same result when the file is initially 10 bytes long?

## 14. Key takeaways

- `length()` is the current **logical byte count**; `getFilePointer()` is the next read/write **position**. The two values are independent.
- `seek()` alone does not extend a file. Only writing past EOF or calling `setLength` to extend can increase the logical length.
- Shrinking with `setLength` discards trailing contents and clamps the pointer to `newLength` if the pointer was beyond the new length.
- Extending with `setLength` creates bytes inside the logical file whose **contents are undefined by Java**; do not treat them as initialized data.
- If business logic requires explicit default data, **explicitly write the bytes to initialize** or manage valid state with a separate data structure. Check logical length, pointer, EOF, written data, and I/O errors together.
