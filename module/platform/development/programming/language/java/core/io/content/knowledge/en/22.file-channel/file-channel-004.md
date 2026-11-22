# FileChannel: size, truncate, and File Length Modification Limits

## 1. File Size and Channel Position Are Two Different Concepts

In Java NIO, `java.nio.channels.FileChannel` lets you access a file by bytes, read and write at specific positions, and query or shrink its size. Three main concepts:

- `size()`: **the current length of the file**, measured in bytes, returning `long`.
- `position()` and `position(long)`: **the channel's current position** for the next read/write; the position does not necessarily match the length.
- `truncate(long)`: **trims the tail** if the file is larger than the requested size; it does not extend the file.

Example of a file with eight ASCII bytes:

~~~text
Index:        0 1 2 3 4 5 6 7 | 8
Content:      A B C D E F G H | EOF
Size = 8
Position can be 0, 3, 8, 100...
~~~

**Setting `position(100)` does not create 92 extra bytes.** Position is a logical cursor. Length normally changes by writing data past EOF or by truncating the file.

`FileChannel` implements `SeekableByteChannel` and adds operations for reading/writing at explicit offsets, mapping, file locks, and data synchronization (`force`). This article focuses on **the size and resizing** of a file, without treating position as a proxy for size.

## 2. Opening FileChannel in the Right Mode to Modify a File

Example of opening an existing file for both reading and writing:

~~~java
Path path = Path.of("data.bin");
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    System.out.println(channel.size());
}
~~~

This is an illustrative snippet, requiring imports for `java.nio.file.*` and `java.nio.channels.FileChannel`, as well as an existing `data.bin` file.

Options to distinguish:

| Option | Effect |
| --- | --- |
| `READ` | Allows reading; insufficient permission to change length. |
| `WRITE` | Allows writing/truncating when the filesystem and OS permissions permit. |
| `CREATE` | Creates the file if missing when paired with an appropriate write option. |
| `CREATE_NEW` | Creates only a new file; avoids accidentally using an existing file. |
| `TRUNCATE_EXISTING` | When opened for writing, an existing file is truncated to **0 bytes immediately upon opening**. |
| `APPEND` | Appends to the end per provider semantics; unsuitable when you need control over write offsets. |

Passing no options to `FileChannel.open(path)` defaults to `READ`. To modify content or call `truncate`, you must open the channel with `WRITE` permission and ensure the filesystem does not forbid the operation.

**`TRUNCATE_EXISTING` differs from `channel.truncate(n)`:** the first option takes effect **at open time**, whereas the second method takes effect **when called**. If you need to edit a few leading bytes of a file containing important data, avoid adding `TRUNCATE_EXISTING` out of habit because it can wipe out the content immediately.

Manage the lifecycle with `try-with-resources` to close the channel after use. When operating on a file accessed by multiple processes, simply closing the channel does not replace application-level synchronization and consistency guarantees.

## 3. How Many Bytes Does `size()` Return?

Signature:

~~~java
long size() throws IOException;
~~~

`size()` returns the **current logical length** of the file represented by the channel, not the read/write position, the number of elements currently in a ByteBuffer, or the allocated disk space.

~~~text
ASCII file "HELLO"
size() = 5
position() = 2
~~~

Length is measured in **bytes**. With UTF-8, a Vietnamese string typically has more bytes than visible characters. Do not use `String.length()` or text line counts to predict `size()` accurately unless you have determined the encoding and computed the actual byte length.

The `long` return type allows representing file sizes larger than the `int` limit. However, **API support does not guarantee that the filesystem accepts every size within `long`'s range**. Maximum size, quotas, physical disk space, and write permissions depend on the filesystem/provider/OS.

A sparse file may report a large `size()` without occupying that many bytes of physical storage. Likewise, `size()` is the value **at the moment of the call**; another task could extend or truncate the file immediately afterward. Do not treat `size()` as a transactional snapshot or a locking mechanism.

When you only have a `Path`, `Files.size(path)` can also read the size metadata. When operating on an open `FileChannel`, `channel.size()` binds directly to the same channel in use, though it still does not eliminate race conditions with other writers.

## 4. `position()` Can Differ from `size()`, Even Beyond EOF

FileChannel has two methods:

~~~java
long position() throws IOException;
FileChannel position(long newPosition) throws IOException;
~~~

Example:

~~~text
File content: ABCDEF
size = 6
position(2) → next relative read/write starts at offset 2
position(6) → currently at EOF
position(100) → past EOF; file still has size = 6
~~~

Setting a position greater than EOF is valid. Calling `read(buffer)` at a position past EOF on a normal file returns `-1` if there is no data; merely seeking does not make the file larger. Setting a negative position throws `IllegalArgumentException`.

Each time `channel.read(dst)` succeeds with `n` bytes, the channel position increases by `n`. A successful `channel.write(src)` with `n` bytes likewise advances the channel position accordingly. At the same time, `ByteBuffer.position()` also increases by the number of bytes transferred. These are **two objects, two different positions**.

`channel.position(0)` moves the file read point back to the beginning without automatically calling `buffer.clear()` or `buffer.flip()`. Conversely, `buffer.flip()` only prepares to read bytes already received into the buffer without changing the channel's position.

## 5. The `truncate(long)` Contract: Shrinking Only

Signature:

~~~java
FileChannel truncate(long size) throws IOException;
~~~

Calling `truncate(newSize)` applies these rules:

1. If `newSize < oldSize`, the file loses all bytes from offset `newSize` onward and its size becomes `newSize`.
2. If `newSize >= oldSize`, the file length **remains unchanged**. The method does not pad additional data.
3. If the current position is greater than `newSize`, the position is set to `newSize`; if it is not greater, it remains unchanged.
4. `newSize < 0` throws `IllegalArgumentException`.
5. Missing write permission throws `NonWritableChannelException`; filesystem, device, quota, or other I/O conditions may throw `IOException`.

Example file `ABCDEFGH` (8 bytes):

~~~text
Offset:     0 1 2 3 4 5 6 7
Before:     A B C D E F G H
            position=3; size=8

truncate(5)

After:      A B C D E
            position=3; size=5
~~~

If before calling `truncate(5)` the channel was at `position=8`, the position is brought down to 5. If `truncate(100)` is called on a 5-byte file, **the file stays 5 bytes**.

### Truncating a File to 0 Bytes

`truncate(0)` removes all contents. This is an actual data-loss operation, not "resetting position to 0". It is especially dangerous when targeting the wrong log file, binary data file, or a file currently in use by another application.

`truncate(n)` returns the channel itself so you can chain further calls if appropriate; returning the object does not mean the operation is scheduled asynchronously.

## 6. To Increase Length: Write Data Past EOF

To create additional bytes at the end, you can set the position to EOF and then write:

~~~java
channel.position(channel.size());
ByteBuffer bytes = ByteBuffer.wrap(new byte[] {'X', 'Y'});
while (bytes.hasRemaining()) {
    int n = channel.write(bytes);
    if (n == 0) {
        throw new IOException("Write made no progress");
    }
}
~~~

The illustrative snippet above requires `channel` opened with `WRITE` permission, and imports for `java.nio.ByteBuffer` and `java.io.IOException`. Only use a loop with an appropriate error/progress handling policy; for example, choosing to throw an error if 0 bytes are written instead of spinning without progress.

If the file is 4 bytes long and you set `position(10)` then successfully write 1 byte:

~~~text
Before:        A B C D
Offsets:       0 1 2 3 | EOF=4

write 'Z' at offset 10

After:         A B C D ? ? ? ? ? ? Z
Offsets:       0 1 2 3 4 5 6 7 8 9 10 | EOF=11
position=11, size=11
~~~

**Do not assume the bytes marked `?` are always 0.** The byte values in the region between the old EOF and the start of the new write are not guaranteed by the general `FileChannel` contract. The filesystem may use sparse holes or another storage representation. If the data requires the gap to hold specific bytes, **explicitly write padding contents** into that region.

Writing at an existing offset is an **overwrite**, not an insertion that shifts the tail:

~~~text
Before: ABCDEFGH   size=8
position(2), write "xy"
After:  ABxyEFGH   size=8
~~~

Therefore, size only increases when writing past EOF (or when another task modifies the file). Writes that replace bytes inside the file may not change size.

## 7. Java 17+ Example: size, truncate, Position Beyond EOF, and Expansion

The program uses a temporary file containing only ASCII bytes so there is no confusion between characters and bytes. It does not print random filenames or read undefined gap regions, so stdout is consistent across common default filesystems.

Save as `FileChannelLengthDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelLengthDemo {

    static void writeAscii(FileChannel ch, String text) throws IOException {
        ByteBuffer src = ByteBuffer.wrap(
                text.getBytes(StandardCharsets.US_ASCII));
        while (src.hasRemaining()) {
            if (ch.write(src) == 0) {
                throw new IOException("No write progress");
            }
        }
    }

    static String readExactly(FileChannel ch, int bytes) throws IOException {
        ByteBuffer dst = ByteBuffer.allocate(bytes);
        while (dst.hasRemaining()) {
            int n = ch.read(dst);
            if (n == -1) {
                throw new EOFException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
        }
        dst.flip();
        return StandardCharsets.US_ASCII.decode(dst).toString();
    }

    static void state(String title, FileChannel ch) throws IOException {
        System.out.println(title + ": position=" + ch.position()
                + ", size=" + ch.size());
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("length-demo-", ".bin");
        try {
            try (FileChannel ch = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                state("initial", ch);

                writeAscii(ch, "ABCDEFGH");
                state("written", ch);

                ch.position(3);
                ch.truncate(5);
                state("truncate 5", ch);

                ch.position(100);
                state("seek 100", ch);

                ch.truncate(4);
                state("truncate 4", ch);

                ch.truncate(20);
                state("truncate 20", ch);

                ch.position(0);
                System.out.println("prefix=" + readExactly(ch, 4));
                state("after read", ch);

                ch.position(6);
                writeAscii(ch, "Z");
                state("write beyond EOF", ch);

                ch.truncate(2);
                state("truncate 2", ch);

                ch.position(0);
                System.out.println("final=" + readExactly(ch, 2));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run commands:

~~~bash
javac FileChannelLengthDemo.java
java FileChannelLengthDemo
~~~

Stdout:

~~~text
initial: position=0, size=0
written: position=8, size=8
truncate 5: position=3, size=5
seek 100: position=100, size=5
truncate 4: position=4, size=4
truncate 20: position=4, size=4
prefix=ABCD
after read: position=4, size=4
write beyond EOF: position=7, size=7
truncate 2: position=2, size=2
final=AB
~~~

Step-by-step explanation:

1. The new temporary file has size 0; opening with `READ, WRITE` does not destroy content. Initial position is 0.
2. Writing all 8 bytes `ABCDEFGH`: position increases to 8, size becomes 8.
3. Seek to offset 3 then `truncate(5)`: `ABCDE` remains, size=5, position stays 3 because it is before the new limit.
4. `position(100)` does not increase size; the next print shows size is still 5.
5. `truncate(4)` drops `E` and pulls position from 100 down to 4.
6. `truncate(20)` does not lengthen the file; both size and position in this case remain 4.
7. Reading from the beginning yields `ABCD`. `readExactly` reads the exact requested byte count, checks for EOF, and `flip`s the buffer before decoding.
8. Writing `Z` at offset 6: size becomes 7, position becomes 7. The example makes no assumptions about the contents at offsets 4 and 5.
9. `truncate(2)` shrinks the file to `AB`, pulling position to 2; reading again from the start confirms `AB`.
10. `try-with-resources` closes the channel; `finally` deletes the temporary file even if an I/O operation fails.

The program throws `IOException` when reads/writes make no progress. For non-blocking channels in real application systems, an appropriate wait/retry mechanism is needed. The core of this article is the `FileChannel` contract with regular files, not designing non-blocking I/O handling.

## 8. Overloads with Explicit Offsets and Their Effect on Size

Besides `read(dst)` and `write(src)` which use the shared position, `FileChannel` supports:

~~~java
int read(ByteBuffer dst, long position);
int write(ByteBuffer src, long position);
~~~

Here the passed `position` is an offset **specific to that call**, without changing `channel.position()`. However, `ByteBuffer.position()` still advances by the number of bytes read/written.

With positional write:

~~~java
ch.position(2);
ByteBuffer payload = ByteBuffer.wrap(new byte[] {'X', 'Y'});
int count = ch.write(payload, 100);
// ch.position() is still 2.
// ch.size() may increase if the write succeeds past EOF.
~~~

This is an illustrative snippet with an existing variable `ch` that has write access. `count` may be less than 2; if you need to write everything, check the actual byte count and loop with a new offset based on total bytes written. Do not repeat the same fixed offset 100 if the goal is to finish the remaining bytes.

Effects table:

| Method | Changes shared position? | Can change size? |
| --- | --- | --- |
| `position(newPosition)` | Yes | No |
| `size()` | No | No |
| `read(dst)` | Yes when bytes are read | Reading itself does not expand |
| `write(src)` | Yes when bytes are written | Yes if writing past EOF |
| `read(dst, offset)` | No | Reading itself does not expand |
| `write(src, offset)` | No | Yes if writing past EOF |
| `truncate(newSize)` | May pull position down | May decrease; never increases |

Other tasks can still modify the file concurrently, so the table describes the **direct effect** of each call.

## 9. Real Limits of Changing File Length

### Filesystem Limits, Quotas, and Permissions

Methods taking `long` do not guarantee you can create arbitrarily long files. Maximum size depends on the filesystem, runtime, provider, quota, disk space, write permissions, device limits, and process resources.

If the file cannot be written or truncated, the operation may throw `IOException` or API-defined exceptions such as `NonWritableChannelException`. Files on a read-only filesystem and files controlled by another process may have different restrictions.

### Data Loss When Truncating

`truncate` can slice through the middle of a record in a binary/log file. If a file structure consists of headers, lengths, checksums, indices, and footers, shrinking can render the entire file invalid. Before truncating, understand **valid data boundaries** and have a backup/recovery mechanism if the data is critical.

~~~text
[record A][record B][record C][record D partially written]
                             ^
                   end of valid record C
~~~

A recovery strategy can verify the last valid record and truncate the incomplete part after it. The truncation position must be a verified **byte** offset, not a line count or visible character count.

### Concurrency and Unstable Size State

Two threads sharing one channel can affect the shared position; two separate channels/processes can modify the file concurrently. The pattern:

~~~java
long end = ch.size();
ch.position(end);
ch.write(data);
~~~

is an illustrative snippet and **is not an atomic append transaction** when other writers exist. Both sides could observe the same `end` and overwrite each other. You need a channel ownership strategy, access synchronization, file locks when appropriate, or an append mechanism that meets platform requirements.

Similarly, reading size and using it as an immutable bound will fail if another process truncates the file right afterward. When high consistency is needed, coordinate at the application level and manage data using an appropriate transaction/protocol.

### Mapping and Truncated File Regions

If the application is using a `MappedByteBuffer` over a truncated region, accessing a mapped region no longer backed by the file can lead to fatal errors or exceptions depending on the platform/runtime. Do not truncate a file underneath mapped regions actively used by other threads without handling the mapping's lifecycle and synchronization.

### Data Durability

`truncate()` returning does not mean all changes are durable on the storage device after power loss. `FileChannel.force(boolean metaData)` provides a request to synchronize relevant updates per the API contract; the level of guarantee depends on the provider, OS, and device. `force` does not turn multiple `write` and `truncate` operations into an atomic transaction.

## 10. Common Mistakes and How to Fix Them

**Mistake 1 — Using `truncate` to increase length.** `truncate(1024)` on a 10-byte file does not create 1,014 new bytes. You must write past EOF if you genuinely need to grow size.

**Mistake 2 — Treating position as size.** Setting `position(100)` does not change `size()`. Query `channel.size()` directly and remember it can change concurrently.

**Mistake 3 — Opening with `TRUNCATE_EXISTING` by mistake.** When intending to update an existing file, this option can erase its contents right before you seek to the offset to edit.

**Mistake 4 — Opening a read-only channel and calling `truncate`.** You need `WRITE` permission and filesystem support. Do not catch every exception as "file not found"; distinguish permission errors, I/O errors, negative values, and closed state.

**Mistake 5 — Counting offsets in characters.** FileChannel works with bytes; UTF-8 characters can occupy multiple bytes. For text data, encode into bytes and determine valid boundaries.

**Mistake 6 — Writing in the middle of a file and expecting automatic insertion.** `write` overwrites; to insert, you must shift the tail or write a new file using an appropriate algorithm.

**Mistake 7 — Assuming the gap after writing past EOF is definitely zero-filled.** Gap contents are not universally guaranteed by the API; if a deterministic format is needed, write explicit padding bytes.

**Mistake 8 — Ignoring the return value of `write`.** A single write may not consume the entire buffer. Use `hasRemaining()`, the returned byte count, and handle zero-progress cases.

**Mistake 9 — Truncating a file currently being written by another task.** Without coordination, you can lose records, corrupt checksums, or cause readers reading the tail to fail.

## 11. Self-Check

1. File is 12 bytes, position=3; call `truncate(8)`. Result: **size=8, position=3**.
2. File is 12 bytes, position=11; call `truncate(8)`. Result: **size=8, position=8**.
3. File is 4 bytes; call `truncate(20)`. Result: **size remains 4**.
4. File is 4 bytes; call `position(10)`. Result: **size remains 4** if nothing is written or modified externally.
5. File is 4 bytes; successfully write one byte at offset 10. Result: **size=11**; do not assume bytes at offsets 4–9 are 0.
6. File `ABCDEFGH`, write `xy` at offset 2. Result **`ABxyEFGH`**, size remains 8.
7. Why not use `TRUNCATE_EXISTING` when editing a header? Because it can truncate the file to 0 bytes immediately upon opening.
8. Does `write(payload, 100)` change `channel.position()`? **No**. It can change size if writing past EOF.
9. Does calling `size()` before another writer acts guarantee the size stays the same? **No**; it is only a point-in-time observation.

**Takeaway:** `size()` measures **current length in bytes**; `position()` determines **the next read/write position**; `truncate(n)` **shrinks** the file when needed and may pull position down, but **never extends** the file. To increase length, you must write data past EOF while handling gap bytes, environment limits, consistency, and I/O permissions.
