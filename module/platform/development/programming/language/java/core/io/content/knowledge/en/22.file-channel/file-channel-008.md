# Relationship Between FileChannel and FileInputStream, FileOutputStream, and RandomAccessFile

## 1. One File, Two Ways of Using APIs

In Java I/O, the three classes `java.io.FileInputStream`, `java.io.FileOutputStream`, and `java.io.RandomAccessFile` existed prior to Java NIO. NIO added `java.nio.channels.FileChannel`, enabling file operations through `ByteBuffer`, byte positions, channel-to-channel transfers, file mapping, and more.

All three classic I/O classes provide a **`getChannel()`** method. This method returns a **`FileChannel` bound to the very object that opened the file**, allowing you to work with the same file and associated state using both legacy APIs and the channel API.

~~~text
FileInputStream  ── getChannel() ──> FileChannel (READ)
FileOutputStream ── getChannel() ──> FileChannel (WRITE)
RandomAccessFile ── getChannel() ──> FileChannel (READ or READ+WRITE)
       │
       └── Shared resource, file position, and close lifecycle
~~~

**Core point:** a channel obtained via `getChannel()` is tightly coupled to its source object. Moving the position on the channel side affects the read/write position of the stream or `RandomAccessFile`, and vice versa. The file's content and length belong to the same underlying resource. Closing one side prevents the other side from continuing to operate.

This article clarifies exact read/write permissions, shared positions, lifecycle management, effects of append/buffering, and when to use `FileChannel.open(...)` directly.

## 2. Quick Comparison Table

| Source object | How to get the channel | Channel permissions obtained | Familiar I/O methods |
| --- | --- | --- | --- |
| `FileInputStream` | `input.getChannel()` | Read | `read()`, `read(byte[])` |
| `FileOutputStream` | `output.getChannel()` | Write | `write(int)`, `write(byte[])` |
| `RandomAccessFile(file, "r")` | `raf.getChannel()` | Read | `read(...)`, `seek(...)`, `getFilePointer()` |
| `RandomAccessFile(file, "rw")` | `raf.getChannel()` | Read and write | `read(...)`, `write(...)`, `seek(...)`, `setLength(...)` |

With `RandomAccessFile`, modes `"rws"` and `"rwd"` also allow reading/writing and request update synchronization per the mode's contract; there is a difference regarding metadata between the two modes. Actual synchronization also depends on the storage system.

`getChannel()` returns the unique channel object associated with **that stream/RAF object**. Calling `getChannel()` repeatedly on the same object returns the same linked channel; calling it again does not create an extra descriptor or an independent cursor.

Example:

~~~java
FileInputStream in = new FileInputStream("data.bin");
FileChannel first = in.getChannel();
FileChannel second = in.getChannel();
System.out.println(first == second); // true
in.close();
~~~

This is an **illustrative snippet** that only runs when `data.bin` exists; requires importing `java.io.FileInputStream` and `java.nio.channels.FileChannel`. In real applications, prefer `try-with-resources` as in the complete example below.

**Do not assume the `FileChannel` type automatically grants all permissions.** Calling `write(...)` on a channel obtained from `FileInputStream` is invalid because that channel is opened read-only; likewise, `read(...)` on a channel from `FileOutputStream` is invalid when the channel is opened write-only. Typical errors are `NonWritableChannelException` and `NonReadableChannelException` respectively.

## 3. FileInputStream and FileChannel: Sharing the Read Position

`FileInputStream` provides reading byte-by-byte or into byte arrays. The `FileChannel` for the same file supports reading into `ByteBuffer`, changing position, and using other NIO capabilities.

~~~java
try (FileInputStream input = new FileInputStream(path.toFile())) {
    FileChannel channel = input.getChannel();
    // ...
}
~~~

This is an illustrative snippet: `path` must be a valid `Path`; import types from `java.io`, `java.nio.file`, and `java.nio.channels`.

When the stream successfully reads `n` bytes, the channel's position increases by `n`. If you change `channel.position(offset)`, the next `input.read()` starts at the newly set position.

~~~text
File content: A B C D E
Offsets:      0 1 2 3 4

input.read()       → returns 'A', channel.position() = 1
channel.position(3)
input.read()       → returns 'D', channel.position() = 4
~~~

`channel.position()` represents the file's byte cursor, not a text character offset. `input.read()` returns a byte as an integer 0–255, or `-1` at EOF. Casting to `char` like `(char) input.read()` only makes direct sense for single-byte ASCII data.

### FileInputStream Reads; FileChannel Can Seek but Not Write

`FileInputStream.getChannel()` returns a channel open for **READ**. Some permitted operations:

~~~java
FileChannel channel = input.getChannel();
long fileSize = channel.size();
channel.position(0);
ByteBuffer dst = ByteBuffer.allocate(16);
int read = channel.read(dst);
~~~

This is also an illustrative snippet; it uses an open `input` and requires importing `java.nio.ByteBuffer`. After `channel.read(dst)`, if you need to extract data from the buffer, you must call `dst.flip()`.

Write calls like `channel.write(src)`, `truncate(...)`, or `map(FileChannel.MapMode.READ_WRITE, ...)` are not allowed merely because you hold a `FileChannel`. To write, you must open the file with a writable source.

### Can `FileChannel.read(dst, offset)` Be Used?

Yes. `FileChannel` has the overload `read(ByteBuffer dst, long position)` which reads at an **explicit offset** without modifying the shared `channel.position()`. Because the channel and `FileInputStream` share the common position, this positional read does not advance `input`'s logical cursor either.

However, `dst.position()` still advances by the number of bytes received. Do not confuse the channel's unchanged position with `ByteBuffer` remaining unchanged.

## 4. FileOutputStream and FileChannel: Sharing the Write Position

`FileOutputStream` writes bytes to a file. Its channel is opened for **WRITE**, and the positions of the stream and channel are linked:

~~~java
try (FileOutputStream output = new FileOutputStream(path.toFile())) {
    FileChannel channel = output.getChannel();
    output.write(new byte[] {'A', 'B', 'C'});
    System.out.println(channel.position()); // 3
}
~~~

This is an illustrative snippet; the constructor `new FileOutputStream(file)` **truncates/overwrites an old file immediately upon opening** if the file already exists. Therefore, choose the right file and mode before executing.

Once you have the output stream's channel, you can use `channel.position(index)` and then call `output.write(...)` to overwrite at the set index:

~~~text
Initial: A B C D E
Offset:  0 1 2 3 4

channel.position(2)
output.write('X')

Result:  A B X D E
          position = 3
~~~

**Overwriting is not inserting:** `C` is replaced by `X`, and bytes D and E do not automatically shift right.

A channel obtained from `FileOutputStream` **is not opened for reading**, so if you want to read back data just written, you cannot simply call `channel.read(dst)`. Use `RandomAccessFile("rw")`, `FileChannel.open(path, READ, WRITE)`, or an independent input channel with appropriate coordination rules.

### Append Mode Is a Very Important Exception

You can create an appending stream:

~~~java
FileOutputStream output = new FileOutputStream(file, true);
~~~

The argument `true` means append. In that case, the initial position of the linked channel reflects the **file size**, and writes through the stream go to the end of the file. Interaction between manual seeks on the channel and provider/platform append behavior has constraints; do not rely on `channel.position(0)` to try overwriting the start of a file when the stream was opened for append.

If the problem requires random access and overwriting arbitrary offsets, **open without append mode**. If the problem only needs appending logs, use the appropriate mode and synchronize when there are multiple writers. `append` does not mean a sequence of read-size → seek → write is guaranteed atomic.

## 5. RandomAccessFile and FileChannel: Two APIs for the Same Cursor

`RandomAccessFile` differs from unidirectional input/output streams because it natively supports **reading, writing, seeking, and resizing**. It is the clearest bridge between classic I/O APIs and `FileChannel`.

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    FileChannel channel = raf.getChannel();
    raf.seek(10);
    System.out.println(channel.position()); // 10

    channel.position(3);
    System.out.println(raf.getFilePointer()); // 3
}
~~~

This is an illustrative snippet; `file` must be a valid `java.io.File` and the file is opened `"rw"`. `raf.seek(long)` and `channel.position(long)` control the same file position. `raf.getFilePointer()` and `channel.position()` reflect the same logical offset.

Key correspondences:

| RandomAccessFile | FileChannel | Relationship |
| --- | --- | --- |
| `raf.seek(pos)` | `channel.position(pos)` | Sets the shared byte cursor |
| `raf.getFilePointer()` | `channel.position()` | Queries current position |
| `raf.length()` | `channel.size()` | Queries logical length of the same file |
| `raf.read(...)` | `channel.read(buffer)` | Reads at current position, advancing the cursor |
| `raf.write(...)` | `channel.write(buffer)` | Writes at current position, advancing the cursor |
| `raf.setLength(n)` | `channel.truncate(n)` | Both relate to length, yet differ when **n is larger than old size** |

### Major Difference: `setLength` Can Extend, `truncate` Cannot

This is the easiest boundary to confuse.

- `RandomAccessFile.setLength(n)`: if `n` is less than the old size, it truncates; if `n` is greater, it **extends** the file. Bytes in the newly extended region are **not generally defined** by the API.
- `FileChannel.truncate(n)`: if `n` is less than the old size, it truncates; if `n` is greater than or equal to the old size, it **does not** extend the file.

~~~text
Current size = 5

raf.setLength(8)       → new size = 8
channel.size()         → 8
bytes at offsets 5..7 → undefined by the API

channel.truncate(4)    → new size = 4
raf.length()           → 4
~~~

When shrinking the file, a cursor past the new limit is adjusted downward. `setLength` may also adjust the file pointer per the method's contract. These operations mutate **the same file**, so `raf.length()` and `channel.size()` observe the same length after a successful update.

Do not treat newly extended, unwritten regions as meaningful data. When a file format requires deterministic padding, write explicit padding bytes.

## 6. Complete Java 17+ Program: Three Objects and How They Share State

The following program uses a temporary file and opens the three source objects **one after another**, not concurrently. That way, we can observe full cursor-sharing behavior without mixing in I/O contention issues.

Save as `FileChannelLegacyBridgeDemo.java`:

~~~java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileChannelLegacyBridgeDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("channel-bridge-", ".bin");

        try {
            FileChannel outputChannel;

            try (FileOutputStream out =
                         new FileOutputStream(file.toFile())) {
                outputChannel = out.getChannel();

                out.write("ABCDE".getBytes(StandardCharsets.US_ASCII));
                System.out.println("output position after write="
                        + outputChannel.position());

                outputChannel.position(2);
                out.write('X');
                System.out.println("output position after seek/write="
                        + outputChannel.position());
            }

            System.out.println("output channel open after close="
                    + outputChannel.isOpen());

            try (FileInputStream in =
                         new FileInputStream(file.toFile())) {
                FileChannel inputChannel = in.getChannel();

                System.out.println("input first=" + (char) in.read());
                System.out.println("input channel position="
                        + inputChannel.position());

                inputChannel.position(3);
                System.out.println("input after channel seek="
                        + (char) in.read());
                System.out.println("input position after read="
                        + inputChannel.position());
            }

            try (RandomAccessFile raf =
                         new RandomAccessFile(file.toFile(), "rw")) {
                FileChannel randomChannel = raf.getChannel();

                raf.seek(1);
                System.out.println("raf.seek channel position="
                        + randomChannel.position());

                randomChannel.position(4);
                System.out.println("channel.position raf pointer="
                        + raf.getFilePointer());

                raf.writeByte('Z');
                System.out.println("raf write channel position="
                        + randomChannel.position());

                raf.setLength(7);
                System.out.println("after setLength: raf.length="
                        + raf.length() + ", channel.size="
                        + randomChannel.size());

                randomChannel.truncate(4);
                System.out.println("after truncate: raf.length="
                        + raf.length() + ", raf pointer="
                        + raf.getFilePointer());
            }

            System.out.println("final="
                    + Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac FileChannelLegacyBridgeDemo.java
java FileChannelLegacyBridgeDemo
~~~

Expected stdout on common default filesystems:

~~~text
output position after write=5
output position after seek/write=3
output channel open after close=false
input first=A
input channel position=1
input after channel seek=D
input position after read=4
raf.seek channel position=1
channel.position raf pointer=4
raf write channel position=5
after setLength: raf.length=7, channel.size=7
after truncate: raf.length=4, raf pointer=4
final=ABXD
~~~

Step-by-step explanation:

1. `FileOutputStream` writes `ABCDE`, making channel position 5. Moving the channel to offset 2 and calling `out.write('X')` replaces byte C with X, yielding `ABXDE`. The shared position becomes 3.
2. Exiting `try (out)` closes the stream; the linked channel is closed as well. `outputChannel.isOpen()` therefore returns `false`.
3. `FileInputStream` reopens the file from the beginning, reads `A` at offset 0 so channel position = 1. `inputChannel.position(3)` causes the next `in.read()` to read byte D, advancing position to 4.
4. `RandomAccessFile("rw")` opens the file allowing both reading and writing. `raf.seek(1)` is reflected as position 1 on the channel. `randomChannel.position(4)` is reflected as file pointer 4 on RAF.
5. `raf.writeByte('Z')` replaces E with Z, turning the file into `ABXDZ` and position into 5.
6. `raf.setLength(7)` extends the file from 5 to 7 bytes. `randomChannel.size()` immediately reflects 7; the example **does not read** the two new bytes because their values are not guaranteed by the API.
7. `randomChannel.truncate(4)` shrinks the file from 7 to 4 bytes, pulling the file pointer from 5 down to 4. The final file holds only `ABXD`.
8. `Files.readString` reads after RAF has been closed to verify the final result; `finally` deletes the temporary file.

The characters `A` and `D` are cast safely from byte to `char` in the example because the data is ASCII only. For multi-byte UTF-8 text, use an appropriate charset decoder instead of casting individual bytes.

## 7. Closing the Stream vs. Closing the Channel: One Lifecycle Relationship

A channel obtained via `getChannel()` is **not an independent handle to be managed like a second file**.

- `input.close()` closes the channel linked to `FileInputStream`; `output.close()` and `raf.close()` also close their respective channels.
- By the `FileChannel` contract, **closing the linked channel also closes the original stream or RAF object**.
- Once closed, subsequent I/O operations on the channel fail, typically with `ClosedChannelException`; operations on the closed stream/RAF can no longer proceed either.
- Calling `getChannel()` multiple times on the same object does not reopen it after closing.

Preferred pattern:

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    FileChannel channel = raf.getChannel();
    // Use both raf and channel within the same ownership scope.
}
~~~

This is an illustrative snippet, with `file` being a valid `File`. Declaring only the **resource-owning source** in `try-with-resources` is sufficient for a normal lifecycle. If code closes `channel` mid-way and then keeps using `raf`, the design breaks due to the closed resource.

If passing a channel out of an internal helper, agree on **who owns closing it**. For instance, a utility method accepting a caller's `FileChannel` normally should not close it if the caller is still using the linked `FileInputStream`.

## 8. Two Ways of Opening FileChannel Without the Same Ownership Relationship

There are two paths:

**A. Obtaining a channel from an already-open Java I/O object**

~~~java
FileChannel channel = stream.getChannel();
~~~

When using this style, the channel is tied directly to the passed-in `FileInputStream`/`FileOutputStream`/`RandomAccessFile`, sharing position and lifecycle.

**B. Opening directly from a Path**

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        java.nio.file.StandardOpenOption.READ,
        java.nio.file.StandardOpenOption.WRITE)) {
    // This channel is managed independently.
}
~~~

When opening directly, there is no source `FileInputStream`/`FileOutputStream`/`RandomAccessFile` sharing a pointer via `getChannel()`. If another stream also opens the same file, both may **observe the same file contents**, yet they are not a linked stream–channel pair. On normal filesystems, independent opens have independent cursors; do not infer that because the two paths are identical, `channel.position(...)` automatically moves the pointer of every other stream open on that file.

If you simply want to read and write using `ByteBuffer`, `FileChannel.open(path, options)` is usually clearer. If you already have a stream or RAF and need to interoperate with the newer API, `getChannel()` avoids opening an unnecessary extra resource.

## 9. ByteBuffer and Byte Arrays: Shifting Your Mindset When Mixing APIs

Classic streams accept or return individual bytes or byte arrays:

~~~java
int value = in.read();
out.write(new byte[] {'A', 'B'});
~~~

FileChannel primarily works with `ByteBuffer`:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
int n = channel.read(buffer);
buffer.flip(); // Prepare to consume the n bytes just read.
~~~

The snippets above use variables `in`, `out`, and `channel` already initialized in appropriate modes; they are not standalone programs.

Distinguish two groups of cursors:

- **File cursor** of the linked stream/RAF/channel: the next byte in the open resource.
- **`ByteBuffer`'s `position`/`limit`**: the next byte in the memory buffer.

When `channel.read(buffer)` reads `n` bytes, both the file position and the buffer position advance by `n`. Calling `buffer.flip()` at that point only resets bounds to read from the buffer; it does not move the file position back to the start.

When `channel.write(buffer)` writes to the file, both the buffer position and file position advance by the bytes written. If `write` transfers only a partial slice, do not call `buffer.clear()` and discard the unwritten portion.

**Be cautious when mixing stream + channel with high-level buffered wrappers.** If you wrap a `FileInputStream` with `BufferedInputStream` or `InputStreamReader`, the wrapper may read ahead many bytes into its internal memory. At that point, the physical file position has already moved past the bytes observed by the application. Changing the position through the channel while the wrapper still holds buffered data can cause observed data to repeat, skip, or behave unexpectedly. With `BufferedOutputStream`, bytes awaiting flush may be written after code has sought via the channel, leading to unintended contents.

When random access is needed, prefer one consistent I/O path; if forced to mix wrappers, manage `flush`/buffer state and file position explicitly rather than assuming they stay synchronized automatically.

## 10. What Does FileChannel Add Compared to the Three Source Classes?

`getChannel()` is particularly valuable because `FileChannel` offers APIs that the three classic Java I/O classes do not provide in the same form:

- `read(ByteBuffer, long)` and `write(ByteBuffer, long)`: read/write at a specified offset without changing the channel's shared position.
- `transferTo(...)`, `transferFrom(...)`: transfer data between compatible channels with potential provider optimizations.
- `map(...)`: map a file region into memory.
- `lock(...)`/`tryLock(...)`: lock a file region subject to platform limits and cooperating applications.
- `force(boolean)`: request pushing updates to the storage device per API contract.
- `size()`, `truncate(long)`, and `position(long)`: observe/adjust byte length and position through the NIO API.

If you only need sequential byte-by-byte `read()`, `FileInputStream` may suffice. If you only write a byte array, `FileOutputStream` is simpler. If you need to read and write records by offset mixed with primitive types, `RandomAccessFile` provides `readInt`, `writeLong`, `seek`, etc. When you need ByteBuffer, positional I/O, or channel-to-channel transfers, `FileChannel` fits better.

**`getChannel()` cannot be viewed as a privilege escalation.** A channel from `FileInputStream` remains read-only; a channel from `FileOutputStream` remains write-only. Every special operation also depends on file permissions and OS/provider support.

## 11. Concurrency: Sharing a Pointer Can Create Race Conditions

Shared position is convenient in a single-threaded program, yet requires great care if multiple threads share a stream/channel:

~~~text
Thread A: input.getChannel().position(100)
Thread B: input.read()              // Reads byte at position 100
Thread A: input.read()              // Not guaranteed to still be at position 100
~~~

In the example, the second line may advance the cursor before thread A reads. `position(offset)` followed by `read()` are **two operations**, not automatically atomic when mixing APIs across threads.

To reduce conflicts:

1. Assign a linked stream/channel pair to a single component responsible for managing position.
2. If sharing is unavoidable, synchronize the entire seek + read/write sequence at the application level.
3. Consider `FileChannel.read(dst, offset)`/`write(src, offset)` overloads to operate at explicit offsets without altering the shared position, if access permissions allow.
4. Distinguish **cursor** conflicts from **file-content** conflicts: positional I/O prevents stepping on a shared position, yet does not eliminate multiple writers overwriting the same data region.

Closing the channel from one thread while another thread is using the stream can cause the other thread's operation to fail. Designing close ownership is just as important as cursor ownership.

## 12. Common Mistakes

### Mistake 1. Thinking `getChannel()` creates a new independent file/channel

It returns the channel bound to the open source. Same cursor and lifecycle; seeking via the channel affects the stream/RAF. Opening a new independent file handle with `FileChannel.open(path, ...)` is a different case.

### Mistake 2. Getting a channel from an input stream and calling write

`FileInputStream.getChannel()` produces a read-only channel. Calling `write` on that channel throws `NonWritableChannelException`. To read and write, choose `RandomAccessFile("rw")` or open `FileChannel` directly with appropriate permissions.

### Mistake 3. Getting a channel from an output stream and calling read

`FileOutputStream.getChannel()` is a write-only channel. It does not gain read access just by having type `FileChannel`; `read` fails with `NonReadableChannelException`.

### Mistake 4. Closing the channel and continuing to use the stream or RAF

Because both objects share the same lifecycle, closing the channel prevents the source from continuing to operate. Use one `try-with-resources` with clear ownership; do not close a caller-managed resource inside a utility.

### Mistake 5. Thinking RandomAccessFile and FileChannel have two cursors

`raf.seek(offset)` changes `channel.position()`; `channel.position(offset)` changes `raf.getFilePointer()`. If using both, account for the fact that they control a single position.

### Mistake 6. Using `truncate` to make a file longer

`FileChannel.truncate(newSize)` only shrinks when needed; conversely, `RandomAccessFile.setLength(newSize)` can extend a file. The extended region is not guaranteed to hold defined byte values.

### Mistake 7. Trying to overwrite the start of a file from an append stream

`new FileOutputStream(file, true)` is meant for appending at the end. Do not design seek/overwrite logic assuming append will honor a manual cursor the way you expect.

### Mistake 8. Mixing buffered wrappers with a channel and assuming application cursor matches file cursor

Wrappers may read ahead, buffer unflushed bytes, or decode into characters. The byte count consumed in the wrapper differs from the channel position. Manage buffers explicitly or stick to one consistent access API.

### Mistake 9. Ignoring permissions and I/O errors

Important exceptions include `NonReadableChannelException`, `NonWritableChannelException`, `ClosedChannelException`, and `IOException`. There are also missing files, permissions, caching, locking, and unsupported filesystems. Pick the right source and mode right at open time.

## 13. Self-Check Questions

1. Can `FileInputStream.getChannel()` write data? **No**, the channel is opened for reading.
2. The stream has read 3 bytes; what is `input.getChannel().position()` typically? **3**, assuming no other operation moved the position.
3. Why can `channel.position(10)` change the next byte returned by `in.read()`? Because they share the position on the same source object.
4. Can `FileOutputStream.getChannel()` read back data just written? **No**, the channel is opened for writing.
5. `RandomAccessFile("rw")` calls `raf.seek(7)`. What is `raf.getChannel().position()`? **7**.
6. RAF's channel calls `position(2)`; does `raf.getFilePointer()` change? **Yes, to 2**.
7. A file is 5 bytes long; after `raf.setLength(8)`, what is `raf.getChannel().size()`? **8**. Are the contents of the three added bytes defined? **No**.
8. A file is 5 bytes long; does `raf.getChannel().truncate(8)` change size to 8? **No, it remains 5**.
9. After closing `FileOutputStream`, can you still call `out.getChannel().write(...)`? **No**, the linked resource is closed.
10. Why shouldn't two threads freely call `raf.seek(...)` and `channel.read(...)` on the same RAF? Because the read position is shared, execution interleaving can cause reads from the wrong offset.
11. When using `FileChannel.read(dst, 100)`, does the channel/RAF position change? **Not from this positional call**, though `dst.position()` increases by the actual bytes read.
12. When you only need an independent FileChannel from a `Path`, which API do you use? **`FileChannel.open(path, options)`**, managing the channel lifecycle with `try-with-resources`.

**Takeaway:** `getChannel()` is the direct bridge from `FileInputStream`, `FileOutputStream`, and `RandomAccessFile` to NIO. It **preserves the source's I/O permissions**, while **sharing position, data, length, and close lifecycle** with that source. `RandomAccessFile.setLength` can increase size whereas `FileChannel.truncate` only shrinks; keep these two behaviors distinct when designing random file access.
