# SeekableByteChannel and Positioning Capabilities in Java NIO

## 1. The Problem: Sequential Read/Write Is Not Enough

When reading a regular data stream, a program consumes data sequentially and does not necessarily have a way to go back to previously read bytes. With files, many tasks require random access: reading a header at the beginning, jumping to a record at the end, modifying a field in the middle of the file, or trimming the tail.

In Java NIO, **`SeekableByteChannel`** (`java.nio.channels.SeekableByteChannel`) provides that mechanism: it is a channel that can read/write bytes, **knows the size of the resource**, and **allows changing the current position**.

~~~text
File:    a  b  c  d  e  f
Offset:  0  1  2  3  4  5
                               EOF at offset 6

position = 2
            ↑
next read starts from byte 'c'
next write starts overwriting from byte 'c'
~~~

**`position` is not file content.** It is a logical pointer indicating where the next relative read/write operation will begin. Moving the pointer does not itself add, delete, or copy bytes.

Scope of this lesson: understand the `SeekableByteChannel` contract, the relationship between `position` and `size`, how to read/write at arbitrary positions, `truncate`, and common pitfalls when using this API.

## 2. Role and Key Methods

`SeekableByteChannel` extends `ByteChannel`, meaning it inherits both `ReadableByteChannel` and `WritableByteChannel`. It is also a `Channel`, supporting resource closing via `close()` and checking `isOpen()`. However, **the open mode** may permit read-only, write-only, or both; an object having type `SeekableByteChannel` does not automatically grant permission in both directions.

Essential methods:

| Method | Effect | Things to Remember |
| --- | --- | --- |
| `long position()` | Gets the current position | Measured in bytes, 0-based offset |
| `SeekableByteChannel position(long newPosition)` | Moves the next read/write position | `newPosition < 0` is invalid; can be set past EOF |
| `long size()` | Gets the current size of the resource | Not the position; may change on write/truncate |
| `SeekableByteChannel truncate(long size)` | If the new size is smaller than the current size, cuts off the tail | Not used to extend a file |
| `int read(ByteBuffer dst)` | Reads bytes from the current position into buffer | Returns byte count read, or `-1` at EOF |
| `int write(ByteBuffer src)` | Writes bytes from buffer at the current position | May overwrite old bytes or extend the file |
| `close()` | Closes the channel | Should use `try-with-resources` |

Typically a `SeekableByteChannel` is backed by a file, though the interface does not promise every implementation is a file on disk. `FileChannel` also implements `SeekableByteChannel` and adds specialized features such as independent positional operations, memory mapping, file locking, and `force`.

### Three Quantities Easy to Confuse

Suppose a file has 6 bytes:

~~~text
Content: abcdef
size() = 6
position() = 2
ByteBuffer.remaining() = 4 (assuming the buffer has 4 spaces to read into)
~~~

- `channel.size()`: size of the data in the **file/resource**.
- `channel.position()`: current cursor of the **channel**.
- `buffer.position()`, `buffer.limit()`, `buffer.remaining()`: state of the **in-memory buffer**.

Each time `channel.read(buffer)` succeeds with `n` bytes, the channel position advances by `n` and the buffer position advances by `n`. Each time `channel.write(buffer)` succeeds with `n` bytes, both positions also advance by `n` accordingly. **Do not confuse the channel's position with the buffer's position.**

## 3. Creating a `SeekableByteChannel` and Determining Access Permissions

Common usage with the `Files` API:

~~~java
Path path = Path.of("data.bin");

// Read-only. When no options are passed, Files.newByteChannel defaults to READ.
try (SeekableByteChannel channel = Files.newByteChannel(path)) {
    System.out.println(channel.size());
}
~~~

This is an illustration snippet requiring imports `java.nio.file.*` and `java.nio.channels.SeekableByteChannel`; the file `data.bin` must exist if run directly.

To both read and write an existing file:

~~~java
try (SeekableByteChannel channel = Files.newByteChannel(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    // Work with channel inside the try block.
}
~~~

Several `StandardOpenOption` values to distinguish:

- **`READ`**: allows reading data.
- **`WRITE`**: allows writing data.
- **`CREATE`**: creates the file if it does not exist when used with an appropriate write option.
- **`CREATE_NEW`**: only creates a new file; fails if the target already exists.
- **`TRUNCATE_EXISTING`**: when opened for writing, truncates an existing file to size 0 immediately upon opening; do not use when you need to preserve data to seek and edit.
- **`APPEND`**: appends to the end according to provider semantics; unsuitable if the goal is controlling arbitrary write positions.

For example: `Files.newByteChannel(path, READ, WRITE)` does not create the file if it does not already exist. You can use `WRITE, CREATE` when you need to create if absent or continue writing as needed.

**Note on `APPEND`:** in append mode, before each write operation the channel may be moved to the end to append; combining `APPEND` with `READ` or `TRUNCATE_EXISTING` may not be supported by the provider. Certain combinations are rejected by the default JDK. Do not use `position(0)` expecting to overwrite the beginning of a file when the channel is opened with `APPEND`.

Because the API is based on `Path`, the filesystem and provider of `path` determine how the channel is opened, which features are supported, and the exact exceptions thrown.

## 4. `position(long)`: Moving the Cursor Before Reading/Writing

Suppose a file contains `abcdef`:

~~~text
Offset     0  1  2  3  4  5
Byte       a  b  c  d  e  f
Size       6
Position   0
~~~

Set:

~~~java
channel.position(2);
~~~

Then `channel.read(dst)` starts at offset 2, i.e., byte `c`. If 3 bytes are read, the channel has `position() == 5`. Calling `channel.write(src)` also begins writing at the current position (if the channel permits writing).

For a typical file:

- `position(0)` moves back to the beginning of the file.
- `position(channel.size())` puts the cursor at EOF so you can append from there if opened for writing.
- `position(2)` allows reading/writing starting from the third byte.
- `position(-1)` throws `IllegalArgumentException`.
- `position(newPosition)` does not change the file size merely because the position is greater than `size()`.

### Is Setting the Cursor Past EOF Valid?

Yes. For example, size = 6 and:

~~~java
channel.position(100);
~~~

`position()` can now be 100 while `size()` remains 6. For a finite-content file, a `read` call when the position is at or past EOF normally returns `-1` without extending the file.

If you **write data** at offset 100, the file may be extended to hold the new data and the gap between the old EOF and the write position. Per the `SeekableByteChannel` contract, **the byte values in that gap are unspecified across all implementations**. Do not assume it is always zero-filled. If a file format requires specific values, the application must write/initialize them explicitly.

Note: positions use type `long` to represent large offsets; do not cast to `int` when working with large files.

## 5. Writing at Arbitrary Positions: Overwriting and Extending

A channel opened with `WRITE` uses its current position to determine where bytes are written. If the position lies within existing data, writing **replaces the bytes in that region**; it does not automatically insert bytes and shift trailing bytes to the right.

~~~text
Initial file:
Offset 0 1 2 3 4 5
       a b c d e f
size = 6

position(2)
write("XY")

File after write:
Offset 0 1 2 3 4 5
       a b X Y e f
size = 6
position = 4
~~~

This is an **overwrite**, not a string insertion at index 2. Bytes `c` and `d` have been replaced by `X`, `Y`; bytes `e`, `f` remain untouched.

If a write extends past the end of the file, the size grows to accommodate the last byte written. If the write stays within the existing file range and there are no concurrent modifications, `size()` can remain unchanged.

### Why Not Assume One `write` Writes the Entire Buffer?

The `int write(ByteBuffer src)` method returns the number of bytes written. That count can be smaller than `src.remaining()` before the call, depending on the implementation and I/O state. Therefore, when you need to write the entire payload, you must loop until `src.hasRemaining()` is `false` or handle a no-progress situation.

~~~java
while (src.hasRemaining()) {
    int written = channel.write(src);
    if (written == 0) {
        // Depending on channel type, wait for writability and retry.
    }
}
~~~

This is an illustration of loop structure: in a real program, you need an appropriate wait/cancel/timeout mechanism; a loop calling `write` forever when it keeps returning 0 will burn CPU.

For typical blocking file channels and valid buffers, operations generally make progress, yet it is still good practice to program against the actual byte count rather than assuming a single write always finishes.

## 6. Reading at Arbitrary Positions and Handling EOF

With `read(ByteBuffer dst)`:

1. Bytes are read from the channel's current position.
2. Bytes are transferred into the buffer starting at `dst.position()`.
3. `channel.position()` and `dst.position()` advance by the actual number of bytes read.
4. When EOF is reached before any byte is read, `read` returns `-1`; the buffer receives no bytes.
5. `read` can also return `0` in situations where no bytes can be read, such as `dst` having no space left or a non-blocking implementation having no data ready yet.

Reading again from the start:

~~~java
channel.position(0);

ByteBuffer dst = ByteBuffer.allocate(16);
int count = channel.read(dst);
dst.flip();

// dst now holds the bytes read from the channel,
// not necessarily all 16 bytes.
~~~

This is an illustration snippet using an appropriately opened `channel` variable. `channel.position(0)` is **not** equivalent to `dst.clear()`: one moves the resource's cursor, while the other resets the in-memory buffer's state.

To read an exact specified number of bytes, you need to loop and check `-1`, `0`, or remaining buffer space. In particular, avoid calling `new String(dst.array())` when the buffer was not filled completely: doing so can include unread bytes from the buffer. Call `flip()` and decode only the valid data region, e.g. `StandardCharsets.UTF_8.decode(dst)` if the data is complete UTF-8.

## 7. `size()` and `truncate(long)`

`size()` reports the current size of the file/resource, independent of where the cursor currently is:

~~~text
size = 6; position = 2
size is still = 6 after position(100)
~~~

`truncate(newSize)` has important rules:

- If `newSize < size()`, the file is trimmed to `newSize` bytes, discarding the tail.
- If `newSize >= size()`, the size **does not increase** solely from calling `truncate`.
- If the current position is greater than the remaining size after truncation, the position is set to the new size; if the current position is within the retained range, it is preserved.
- `newSize < 0` is invalid and may throw `IllegalArgumentException`.
- The channel must be opened with appropriate write permission; otherwise `NonWritableChannelException` may be thrown.

Example:

~~~text
Initially: "abcdef"
size = 6
position = 100

truncate(4)

Remaining: "abcd"
size = 4
position = 4
~~~

**`truncate(100)` on a 4-byte file does not extend the file to 100 bytes.** If a fixed-size file format is required, the application must write additional data (and handle any gaps) according to its own rules.

Be careful with `TRUNCATE_EXISTING` when opening a channel: that option clears the content immediately at open time, unlike the `truncate(...)` method called at a point chosen by the program.

## 8. Standalone Java 17+ Example: Seek, Overwrite, EOF, and Truncate

The program uses a temporary file on the default filesystem, so it runs standalone without depending on a specific path on your machine. The sample strings are ASCII so byte-offset counting is completely unambiguous. Save as `SeekableByteChannelDemo.java`:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class SeekableByteChannelDemo {

    private static void writeFully(SeekableByteChannel channel, String data)
            throws IOException {
        ByteBuffer src = ByteBuffer.wrap(
                data.getBytes(StandardCharsets.US_ASCII));
        while (src.hasRemaining()) {
            int n = channel.write(src);
            if (n == 0) {
                throw new IOException("No write progress");
            }
        }
    }

    private static String readFully(SeekableByteChannel channel, int length)
            throws IOException {
        ByteBuffer dst = ByteBuffer.allocate(length);
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n == -1) {
                break;
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
        }
        dst.flip();
        return StandardCharsets.US_ASCII.decode(dst).toString();
    }

    public static void main(String[] args) throws IOException {
        Path temp = Files.createTempFile("seekable-demo-", ".bin");

        try {
            try (SeekableByteChannel channel = Files.newByteChannel(
                    temp,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                System.out.println("initial: position=" + channel.position()
                        + ", size=" + channel.size());

                writeFully(channel, "abcdef");
                System.out.println("after write: position=" + channel.position()
                        + ", size=" + channel.size());

                channel.position(2);
                writeFully(channel, "XY");
                System.out.println("after overwrite: position=" + channel.position()
                        + ", size=" + channel.size());

                channel.position(0);
                System.out.println("content=" + readFully(channel, 6));
                System.out.println("after read: position=" + channel.position());

                channel.position(100);
                int result = channel.read(ByteBuffer.allocate(1));
                System.out.println("read beyond EOF=" + result);
                System.out.println("position after EOF=" + channel.position());

                channel.truncate(4);
                System.out.println("after truncate: position=" + channel.position()
                        + ", size=" + channel.size());

                channel.position(0);
                System.out.println("truncated content=" + readFully(channel, 4));

                channel.position(10);
                System.out.println("seek beyond EOF: position=" + channel.position()
                        + ", size=" + channel.size());
                writeFully(channel, "!");
                System.out.println("after extension: position=" + channel.position()
                        + ", size=" + channel.size());
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

Compile and run:

~~~bash
javac SeekableByteChannelDemo.java
java SeekableByteChannelDemo
~~~

Stdout when run with a standard default file provider supporting these operations:

~~~text
initial: position=0, size=0
after write: position=6, size=6
after overwrite: position=4, size=6
content=abXYef
after read: position=6
read beyond EOF=-1
position after EOF=100
after truncate: position=4, size=4
truncated content=abXY
seek beyond EOF: position=10, size=4
after extension: position=11, size=11
~~~

How to read the output:

1. A new temporary file has size 0. `writeFully("abcdef")` writes 6 bytes and advances `position` to 6.
2. `position(2)` then writing `XY` overwrites the exact two bytes at offsets 2 and 3. The file remains 6 bytes long; after writing, `position=4`.
3. Moving `position` back to 0 and reading 6 bytes confirms content `abXYef`. The `readFully` helper decodes only the buffer region that actually received data.
4. Setting `position=100` even though the file has 6 bytes. Reading 1 more byte returns `-1` for EOF; the position remains 100.
5. `truncate(4)` trims the tail and also pulls `position` from 100 back to 4. Reading from the beginning confirms the remaining content is `abXY`.
6. `position(10)` does not change `size=4`; writing a `!` at offset 10 is what raises `size` to 11 and `position` to 11. The example **neither reads nor guesses** the values of bytes at offsets 4–9 because gap values are not guaranteed by the API across all providers.
7. `try-with-resources` closes the channel, and `finally` deletes the temporary file.

The two helper methods in the example intentionally throw `IOException` if the channel makes no progress. This works well to avoid infinite loops in a local file example; for channels capable of non-blocking and asynchronous operation, a dedicated coordination mechanism is needed instead of assuming 0 means error.

## 9. `SeekableByteChannel` vs. `FileChannel`: Which One to Use?

`FileChannel` implements `SeekableByteChannel`, so it also supports `position()`, `position(long)`, `size()`, `truncate(long)`, `read(ByteBuffer)`, and `write(ByteBuffer)`.

`FileChannel` adds useful APIs:

- `read(ByteBuffer dst, long position)`: reads starting from the supplied offset **without changing the channel's current position**.
- `write(ByteBuffer src, long position)`: writes at the supplied offset **without changing the channel's current position**.
- `map(...)`: maps a region of the file into memory.
- `transferTo(...)`/`transferFrom(...)`: transfers data between appropriate channels.
- `lock(...)`/`tryLock(...)`: locks file regions with system-dependent semantics.
- `force(boolean metaData)`: requests flushing updates out to the storage device per the API contract.

**Choose `SeekableByteChannel`** when you only need the common set of operations and want code that works across multiple implementations/providers. **Choose `FileChannel`** when you genuinely need an extended capability of `FileChannel`.

Illustrative snippet reading at an offset without modifying the global position, assuming an already open `FileChannel channel` with appropriate read permission:

~~~java
ByteBuffer dst = ByteBuffer.allocate(4);
int n = channel.read(dst, 128); // Does not change channel.position().
dst.flip();
~~~

This is an illustration snippet requiring `import java.nio.ByteBuffer`, and it does not assume the file has all 4 bytes at offset 128. `dst.position()` still advances by the number of bytes read; only the **`FileChannel`'s position** stays unchanged due to the positional read call.

With `SeekableByteChannel` in general, you do not have a `read(dst, offset)` overload; you must call `position(offset)` then `read(dst)`. If multiple tasks share one channel, the two separate calls can interleave, causing reads/writes at the wrong offset. You must manage channel synchronization/ownership or consider `FileChannel`'s independent positional APIs.

## 10. Concurrency, Resizing, and Consistency Issues

Seek and I/O operations can create race conditions when sharing a single channel:

~~~text
Thread A: position(100)
Thread B: position(0)
Thread A: read(buffer)   → may read from an unintended position
~~~

Therefore, you should not split `position(offset)` and `read/write` on a shared channel and assume they form an atomic operation. Manage thread access or use `FileChannel`'s positional read/write APIs where appropriate. Exact concurrency characteristics depend on channel/provider type and environment.

Similarly, `size()` reports the size **at the time of the call**. Another process may modify the file right afterward; logic like `if (position < size()) ...` is no guarantee that the bytes will still exist when reading. If an application requires consistency across multiple processes, an appropriate file coordination mechanism must be designed.

`truncate` can cause irrecoverable data loss if no backup or recovery information exists. In real applications, verify the right file, the right target size, and a backup strategy before using it on important files.

Some providers may be read-only or not support all open modes/operations, and may throw `UnsupportedOperationException`, `NonWritableChannelException`, `IOException`, or custom exceptions. Do not infer full capabilities from a file name or URI scheme; use the API and handle errors in context.

## 11. Common Mistakes

### Confusing `position` with `size`

**Wrong:** assuming setting `position(100)` automatically creates a 100-byte file.

**Right:** it only moves the cursor; `size` only grows when data is actually written past EOF (or another mechanism acts on it).

### Forgetting `ByteBuffer.flip()`

After `read(buffer)`, the buffer still has `position` at the end of the filled region. To read data from the buffer you must call `flip()` to set `limit=` old `position`, `position=0`. `channel.position(0)` only changes the **channel** position; it does not flip the buffer.

### Intending to Insert Bytes but Overwriting Instead

Writing `XY` at offset 2 of `abcdef` yields `abXYef`. If you need to insert bytes and shift subsequent data forward, you must implement a tail-shifting algorithm or create a new file; `write` has no insert semantics.

### Assuming `truncate` Can Extend a File

`truncate(100)` does not turn a 6-byte file into a 100-byte file. Extending requires writing or a specific supporting mechanism with a defined fill-byte policy.

### Accidentally Opening with `TRUNCATE_EXISTING`

Before seeking/overwriting an existing file, do not add `TRUNCATE_EXISTING` out of habit; this option erases data **immediately upon opening**.

### Ignoring the Actual Bytes Read/Written

Reading/writing with a `ByteBuffer` can transfer fewer bytes than `remaining()`. Always check the return value and buffer state. If you expect all `n` bytes, you must loop, handle EOF, or handle no-progress conditions.

### Using `APPEND` While Expecting `position(long)` to Control Write Location

`APPEND` is designed for appending to the end; do not use it when you need to overwrite at an arbitrary offset. Open with appropriate `WRITE` permission and omit `APPEND`.

### Counting Offsets by Unicode Characters

`position` counts **bytes**, not Java `char`s or Unicode code points. With UTF-8, the string “Việt” contains more bytes than visible characters. When seeking by text record, use a format with explicitly stored/indexed byte offsets, or decode sequentially; do not mechanically treat a character index as a byte offset.

## 12. Self-Check Exercises

1. A file `0123456789` has size 10. Set `position(3)` and write 2 bytes `AB`. Result? **`012AB56789`, size 10, position 5**.
2. A file has size 10 and position 4; call `truncate(7)`. Result? **size 7, position 4**. If position was 9 before truncation, afterward position becomes 7.
3. A file has size 10; call `truncate(20)`. Result? **size remains 10**.
4. A file has size 5; call `position(12)` then read. What happens? For a normal file, **`read` returns -1**, size is unchanged. Position does not automatically snap back to EOF.
5. File `abcdef`, cursor at 0 and buffer just `read` 4 bytes. What is the channel's `position` if all 4 bytes were available? **4**. Afterward, does `dst.flip()` move the channel back to 0? **No**.
6. Why does `FileChannel.read(dst, 100)` reduce risk when multiple readers access different offsets? Because it uses a **separate offset for that read** without modifying the channel's shared position. Other concurrency factors still need to be managed.
7. If you want to edit metadata at a fixed offset in a large binary file while keeping the rest intact, which mode will you open the channel with and what steps will you take? **Open with appropriate READ/WRITE, seek to the exact byte offset, write the exact-length bytes, verify the result, and close the channel**; do not use `TRUNCATE_EXISTING` or `APPEND`.

**Takeaway:** `SeekableByteChannel` enables **reading/writing at arbitrary positions** via `position(long)`, inspecting size with `size()`, and trimming the tail with `truncate(long)`. Moving the position does not alter contents; reading/writing is what advances the position. Always keep **channel** state separate from **ByteBuffer** state, understand open permissions, and check actual I/O byte counts.
