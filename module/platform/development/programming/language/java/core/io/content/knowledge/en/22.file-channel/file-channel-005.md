# FileChannel: `transferTo`, `transferFrom`, and Handling Actual Bytes Transferred

## 1. Objectives

`FileChannel` in `java.nio.channels` supports reading/writing, random-position access, and transferring data between channels. The two methods `transferTo` and `transferFrom` are especially useful when copying data from or into a file without having to organize a `ByteBuffer` loop on the normal path yourself.

Key point to remember immediately: **the `count` value is the maximum number of bytes requested to transfer, not a promise of how many bytes were actually transferred**. Each call returns a `long` value representing the **actual number of bytes transferred**. A program that must transfer all the data must inspect this return value, update the offset, and call again as appropriate.

After this lesson, you will be able to:

- Choose the right transfer direction between `transferTo` and `transferFrom`.
- Distinguish the `position` parameter from `FileChannel.position()` and the other channel's position.
- Write loops that handle positive counts smaller than requested as well as a return value of 0.
- Explain OS limits, EOF, non-blocking channels, and race conditions.
- Verify byte counts, contents, close resources, and detect incomplete copies.

## 2. API and Data Direction

Two core Java NIO.2 signatures:

~~~java
// Instance methods of FileChannel:
long transferTo(long position, long count, WritableByteChannel target)
        throws IOException;

long transferFrom(ReadableByteChannel src, long position, long count)
        throws IOException;
~~~

These are **API signatures**, not a standalone Java program.

| Method called on | Data direction | `position` belongs to | Other channel object |
| --- | --- | --- | --- |
| `sourceFile.transferTo(position, count, target)` | **From** source file **to** target channel | Starting position **in source file** `sourceFile` | `WritableByteChannel target` receives data |
| `destinationFile.transferFrom(src, position, count)` | **From** source channel **into** destination file | Starting position **in destination file** `destinationFile` | `ReadableByteChannel src` supplies data |

Diagram example:

~~~text
transferTo:
[Source FileChannel] --(position in source file, count)--> [Target WritableByteChannel]

transferFrom:
[Source ReadableByteChannel] --(count)--> [Target FileChannel at position]
~~~

**Do not swap the meaning of `position`:** With `transferTo`, `position` is the read offset; with `transferFrom`, `position` is the write offset. Both offsets are measured in **bytes** from the start of the file, not character indices.

The `position` and `count` parameters must not be negative; negative values throw `IllegalArgumentException`. In addition, the methods may throw `IOException` when data transfer fails, `ClosedChannelException` when a required channel is closed, or other exceptions depending on channel type and state. Do not rely on a single exception type alone.

### What Does the Return Value Mean?

~~~java
long actual = sourceFile.transferTo(offset, requested, target);
~~~

`actual` is the amount of data actually transferred successfully in **that single call**:

- `0 < actual < requested`: only partially transferred; more data may remain.
- `actual == requested`: the call transferred the exact requested amount.
- `actual == 0`: no bytes were transferred this time. **Do not automatically infer that EOF was reached**, especially with non-blocking channels or bounded implementations.
- The successful transfer result lies in `[0, requested]`; `actual` is neither the cumulative total from previous calls nor the ending position.

If `requested == 0`, returning 0 is normal. When the read `position` of `transferTo` is at or beyond the current file size, there are likewise no bytes at that position to transfer.

## 3. File Position and Channel Position After a Transfer Call

This causes more bugs than the copy operation itself.

With `source.transferTo(fromOffset, count, sink)`:

- `fromOffset` determines where to start **reading from the source file**, independent of `source`'s current position.
- The call **does not change** `source.position()`.
- If `sink` is a position-bearing channel, such as a `FileChannel`, data is written starting at `sink`'s current position and `sink`'s position advances by the amount of data written.
- Therefore, the next call must pass `fromOffset + actual` to continue through the source region; calling again with the same offset will re-read old bytes.

With `destination.transferFrom(src, toOffset, count)`:

- `toOffset` determines where to **write into the destination file**, independent of `destination.position()`.
- The call **does not change** `destination.position()`.
- If `src` has a position (for example, `FileChannel`), `src`'s read position typically advances by the number of bytes read.
- Therefore, the next call must pass `toOffset + actual` to `transferFrom`; meanwhile, `src`'s read position has usually already been updated and must not be manually incremented again.

| Operation | `position` of the target FileChannel called on | Position of the opposite channel |
| --- | --- | --- |
| `fileSource.transferTo(...)` | **Unchanged** | A target channel with position advances as it receives bytes |
| `fileDestination.transferFrom(...)` | **Unchanged** | A source channel with position advances as it supplies bytes |

**Position calculation example:** `source.transferTo(100, 40, target)` returns 15. Next time, to continue the source region you must call `source.transferTo(115, 25, target)`. Similarly, if `destination.transferFrom(src, 100, 40)` returns 15, the next write offset is 115. If the target channel written to by `transferTo` was used beforehand, set `target.position(...)` to the intended location before starting the copy.

## 4. Why Can a Single Call Transfer Fewer Than `count` Bytes?

By the API contract, `transferTo` and `transferFrom` **can transfer fewer bytes than requested**. Typical reasons:

1. **Not enough data:** the file region being read has only a few bytes left; with `transferFrom`, the source channel may have reached end-of-stream (EOF).
2. **Operating system or channel provider limits:** a single transfer call may have a size cap, even when many bytes remain. Large file transfers must never be assumed to complete in one call.
3. **Non-blocking channels:** the reading side has no data yet or the writing side is not ready to accept more, so it may transfer less or return 0.
4. **File state modified concurrently:** another task truncates, extends, or edits the file during the transfer, so the expected size no longer reflects actual data.
5. **I/O errors:** a channel may fail and throw an exception mid-transfer; having transferred some bytes earlier does not mean the whole operation succeeded.

Some implementations can optimize transfers via an OS path (often called **zero-copy**), reducing copies through user-space buffers. However, **the API does not promise zero-copy will always be used or that every call will transfer all `count` bytes**. Behavior and performance depend on source/target, provider, operating system, and environment.

## 5. Loop to Transfer All Bytes with `transferTo`

With a stable source file and a blocking writable target channel, the basic handling pattern is:

~~~java
long remaining = source.size();
long offset = 0;

while (remaining > 0) {
    long transferred = source.transferTo(offset, remaining, target);

    if (transferred == 0) {
        throw new IOException("Không có tiến triển khi transferTo");
    }

    offset += transferred;
    remaining -= transferred;
}
~~~

This is an **illustrative snippet**, using already-opened `source` (`FileChannel`) and `target` (`WritableByteChannel`) variables, along with `java.io.IOException`.

**Why update both variables?** `offset` increases by the bytes just read so the next call does not copy already-transferred data again; `remaining` decreases correspondingly so we do not read beyond what was requested. If the initial request is `0`, the loop does not run.

**Why not `while` forever when receiving 0?** Calling repeatedly when there is no progress can burn CPU uselessly. In the normal file and synchronous write channel example, throwing `IOException` makes the failed operation explicit. In a non-blocking design, you must wait for channel readiness through an appropriate mechanism and then retry; do not use a tight busy-spin loop.

If you only want to transfer a slice `[start, start + length)` of the file, set `offset = start` and `remaining = length`. Before copying, check that `start >= 0`, `length >= 0`, and the required region lies within actual data; avoid `long` overflow in `start + length` by comparing safely against size (for example, `length <= size - start` when `start <= size`).

## 6. Loop to Transfer All Bytes with `transferFrom`

Reversing the API direction: the method is called on the **destination FileChannel**, and `position` is the write offset.

~~~java
long remaining = expectedBytes;
long destinationOffset = 0;

while (remaining > 0) {
    long transferred = destination.transferFrom(
            source, destinationOffset, remaining);

    if (transferred == 0) {
        throw new IOException(
                "Nguồn hết dữ liệu hoặc không sẵn sàng trong transferFrom");
    }

    destinationOffset += transferred;
    remaining -= transferred;
}
~~~

This is an **illustrative snippet**, where `destination` is a writable `FileChannel`, `source` is a `ReadableByteChannel` open for reading, `expectedBytes` is already known, and `IOException` is imported.

When `source` is a `FileChannel`, `transferFrom` uses the source's current position and advances it. Thus the loop only updates `destinationOffset` manually; if you also manually call `source.position(source.position() + transferred)`, you will **skip data**. When `source` is a network channel, data arriving in bursts can cause `transferred` to equal 0 even though the connection has not ended.

**Difference from `transferTo`:** `transferFrom`'s write at an offset can extend the destination file when the offset is within or right at the end of the file. If `position` is greater than the current file size, the API permits transferring zero bytes. To create holes or perform random writes, use an appropriate positioning/writing strategy and verify against the filesystem.

## 7. Complete Java 17+ Example: Running Both Directions and Verifying Contents

The following program creates a source file with fixed 11-byte ASCII data (`Java NIO.2\n`), copies in both directions, verifies transferred byte counts and position state, and compares contents. It intentionally handles the case where **each call transfers only a portion** by using loops.

Save as **`FileChannelTransferDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.channels.FileChannel;

public class FileChannelTransferDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("channel-transfer-");
        Path sourceFile = directory.resolve("source.txt");
        Path toFile = directory.resolve("copy-to.txt");
        Path fromFile = directory.resolve("copy-from.txt");

        try {
            Files.writeString(
                    sourceFile, "Java NIO.2\n", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            long transferredTo;
            long sourcePositionAfterTo;
            try (FileChannel source = FileChannel.open(
                         sourceFile, StandardOpenOption.READ);
                 FileChannel target = FileChannel.open(
                         toFile, StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE)) {

                long required = source.size();
                long offset = 0;

                while (offset < required) {
                    long n = source.transferTo(
                            offset, required - offset, target);
                    if (n == 0) {
                        throw new IOException(
                                "transferTo không có tiến triển tại " + offset);
                    }
                    offset += n;
                }

                transferredTo = offset;
                sourcePositionAfterTo = source.position();
            }

            long transferredFrom;
            long destinationPositionAfterFrom;
            try (FileChannel source = FileChannel.open(
                         sourceFile, StandardOpenOption.READ);
                 FileChannel target = FileChannel.open(
                         fromFile, StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE)) {

                long required = source.size();
                long destinationOffset = 0;

                while (destinationOffset < required) {
                    long n = target.transferFrom(
                            source, destinationOffset,
                            required - destinationOffset);
                    if (n == 0) {
                        throw new IOException(
                                "transferFrom không có tiến triển tại "
                                        + destinationOffset);
                    }
                    destinationOffset += n;
                }

                transferredFrom = destinationOffset;
                destinationPositionAfterFrom = target.position();
            }

            boolean equalCopies = Files.mismatch(sourceFile, toFile) == -1
                    && Files.mismatch(sourceFile, fromFile) == -1;

            System.out.println("Source bytes: " + Files.size(sourceFile));
            System.out.println("transferTo bytes: " + transferredTo);
            System.out.println("transferFrom bytes: " + transferredFrom);
            System.out.println(
                    "Source position after transferTo: "
                            + sourcePositionAfterTo);
            System.out.println(
                    "Destination position after transferFrom: "
                            + destinationPositionAfterFrom);
            System.out.println("Copies match: " + equalCopies);
        } finally {
            Files.deleteIfExists(toFile);
            Files.deleteIfExists(fromFile);
            Files.deleteIfExists(sourceFile);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 FileChannelTransferDemo.java
java FileChannelTransferDemo
~~~

When the normal file transfers complete, **stdout** is:

~~~text
Source bytes: 11
transferTo bytes: 11
transferFrom bytes: 11
Source position after transferTo: 0
Destination position after transferFrom: 0
Copies match: true
~~~

### Reading the Example Closely

1. The string `"Java NIO.2\n"` has 11 UTF-8 bytes: 10 visible ASCII characters and one newline character. In this example, character count and byte count match because everything is ASCII; **that is not true for every Unicode string**.
2. `source.size()` is taken as the expected byte count. With a stable source, the loop copies until total `n` reaches `required`; if any call returns 0, the program reports an error instead of treating it as success or looping forever.
3. `transferTo(offset, remaining, target)` preserves `source.position()`. Because the source was newly opened at position 0 and nothing changed it, the printed value is 0.
4. `target.transferFrom(source, destinationOffset, remaining)` uses an explicit write offset and does not change `target.position()`. Because the destination channel was newly opened at position 0, the printed value remains 0, **even though the destination file already contains 11 bytes**.
5. `Files.mismatch(a, b) == -1` confirms identical byte contents, complementing the total byte-count check.
6. `try-with-resources` closes channels even when an error occurs; the `finally` block cleans up the temporary files created in the example.

The byte counts and positions above do not depend on the temporary directory name. If the environment denies an I/O operation, the program reports an exception and may not print all stdout; this is an intentional failure path.

## 8. Do Not Confuse EOF with Temporarily Having No Progress

Suppose you need to receive 1,000 bytes from a non-blocking network `ReadableByteChannel` and call:

~~~java
long n = destination.transferFrom(networkSource, offset, 1000 - offset);
~~~

If `n == 0`, several possibilities exist: no bytes are available to read yet, the sender closed after finishing data, or the direct transfer mechanism temporarily could not move bytes. **A single 0 result does not provide enough information to conclude EOF**. For channels supporting non-blocking mode, waiting via `Selector` or an appropriate synchronization/event mechanism must be designed per channel type and business logic, potentially combined with timeouts or cancellation.

With a **regular source file of known size**, the program can request transferring the exact known byte count. If the source was truncated or no bytes remain at the read offset, receiving 0 before meeting the requirement should be treated as an incomplete-transfer error; do not mark it as success.

When transferring data from a **source of unknown total length**, you cannot simply set an arbitrarily large `expectedBytes` and treat 0 as EOF. You need a protocol defining the end (such as total length from a header or an explicit end signal), or use a `read` loop that distinguishes `-1` (EOF) from `0` (no bytes read yet), depending on the protocol.

A **fallback** pattern for FileChannel-to-FileChannel when optimized transfer makes no progress can use a `ByteBuffer` to read from a specific offset and write to the target position; even then you must handle actual byte counts of both `read` and `write`. Fallbacks add complexity, so include them only when truly needed for specific environments, and never write an unbounded continuous retry loop.

## 9. Copying a File Region: Offset, Byte Count, and Bounds

To copy 4 KiB starting at byte 8 KiB of the source file:

~~~java
long start = 8L * 1024;
long requested = 4L * 1024;
long size = source.size();

if (start > size || requested > size - start) {
    throw new IOException("Vùng yêu cầu vượt dữ liệu hiện có");
}

long copied = 0;
while (copied < requested) {
    long n = source.transferTo(
            start + copied, requested - copied, target);
    if (n == 0) {
        throw new IOException("Chuyển thiếu dữ liệu trong vùng yêu cầu");
    }
    copied += n;
}
~~~

This is an illustrative snippet using already-opened `source` (`FileChannel`), `target` (`WritableByteChannel`), and an `IOException` import. If you do not want to loop until complete, you must **explicitly accept** that the result is only the number of bytes already transferred; the API does not automatically finish the remainder.

The check `requested > size - start` (after ensuring `start <= size`) avoids computing `start + requested` too early and causing `long` overflow. In a real application, validate that both `start` and `requested` are non-negative as well.

**For very large files:** totals, offsets, and remaining variables should use type `long`; do not cast `size` to `int`. A multi-GiB request may be fulfilled by the API/OS across many shorter transfers. Stop only when the desired total is reached or an uncompletable condition is handled cleanly.

## 10. Writing to a Destination File and Avoiding Leftover Data

`transferTo` writes starting at the **destination channel's current position** if the destination is a FileChannel. If you open an old destination file without truncating and the new content is shorter than the old content, the old tail may remain in the file. To copy into a fresh file, you should:

- Open a non-existent file with `CREATE_NEW, WRITE`, or
- Intentionally open an existing file with `CREATE, WRITE, TRUNCATE_EXISTING` if replacing contents is permitted, then ensure the write position is 0.

With `transferFrom`, the write offset is passed directly; writing into an old file can likewise leave leftover data beyond the written range. Depending on the application contract, `FileChannel.truncate(expectedLength)` after completion can be used to cap the destination size, but **you must clearly know which data is allowed to be removed**. Do not truncate arbitrarily if the file contains other data regions.

Avoid having two threads simultaneously mutate the position of the same shared channel during a transfer. Position can be shared state, so interleaving with `position()` or other write operations can produce unexpected results. Establish clear channel ownership and synchronize if a channel is genuinely shared.

## 11. Correctness, I/O Errors, and Data Integrity

A loop summing byte counts is **necessary but not sufficient** to prove a copy is accurate in every scenario.

- **Source changes during reading:** `source.size()` obtained earlier may no longer be accurate. If a consistent copy is needed, coordinate locking/freezing data, snapshots, or an appropriate versioning mechanism; `FileChannel.lock()` has limitations regarding semantics and cooperating processes.
- **Destination fails after partial data:** the target file may hold an incomplete copy. Use a temporary file, verify, and then rename/move per application policy to limit exposing corrupt copies.
- **Total bytes match but contents do not:** equal length does not guarantee equal data. You can compare bytes with `Files.mismatch`; for distributed systems or later verification, add checksums/hashes and an appropriate trust mechanism.
- **`force()` and data durability:** transferring all bytes into a FileChannel does not mean all bytes are durable on the storage device. If durability is required, consider `FileChannel.force(true)` on the destination and a platform-appropriate write/rename workflow.
- **Resources:** use `try-with-resources` to close source and destination; do not mask the original exception if cleanup also fails.

In critical file-copy workflows, the result report should include expected bytes, actual bytes, an integrity check flag, and error details if the operation fails.

## 12. Common Mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Calling `transferTo(0, size, target)` once and assuming it's done | May miss bytes on some systems | Read the return value; loop advancing offset by actual bytes |
| Calling `transferFrom(src, 0, count)` repeatedly on partial transfers | Overwrites already-transferred bytes at the start of destination | Increment write `position` by cumulative actual bytes |
| Manually advancing `source.position()` after `transferFrom` with a FileChannel source | Skips unread data | Let the source channel advance its position via the read operation |
| Assuming `FileChannel.position()` of the target receiver increases | Subsequent read/write occurs at the wrong position | Use the offset passed to the API and track it separately |
| Treating `0` as always meaning EOF | Premature termination with non-blocking channels | Distinguish source/file/protocol; wait for readiness or fail properly |
| Infinite retry on `0` | Busy-spin, high CPU usage | Have a wait policy, timeout, fallback, or fail fast |
| Using `int` to count bytes of large files | Integer overflow, truncated data | Use `long` |
| Ignoring existing destination file and write position | Old data lingers or gets written at unintended offsets | Specify create/truncate and offset explicitly |
| Comparing only file sizes | Fails to detect corrupted content bytes | Compare contents or an appropriate checksum |
| Assuming transfer is always zero-copy | Relies on a property not guaranteed by the API | Measure real performance and have a partial-transfer strategy |

## 13. Self-Check Questions

**Question 1.** A source file is 1,000 bytes long. `source.transferTo(0, 1000, target)` returns 600. How should you continue transferring?

**Answer:** The copy cannot be considered complete yet. While source data and target remain ready, call `source.transferTo(600, 400, target)` and continue based on the returned value.

**Question 2.** `destination.transferFrom(source, 100, 50)` returns 20. Is `destination.position()` guaranteed to increase by 20?

**Answer:** No. The position of the destination channel invoked on is **unchanged**. The next transfer writes at offset `120`; a position-bearing source will typically have advanced by the data read.

**Question 3.** `transferFrom` returns 0 from a non-blocking `SocketChannel`. Can you conclude the peer closed the connection?

**Answer:** No. There may simply be no data yet or the transfer cannot proceed yet; you must rely on readiness notification and the read protocol to detect EOF.

**Question 4.** When copying an 8 GiB file, can you request `count = 8 GiB` once and skip checking the result?

**Answer:** No. Even though `count` is a `long`, platform limits may cause a single call to transfer only a portion. Always accumulate actual bytes transferred.

**Question 5.** Are two copies that are both 11 bytes long guaranteed to have identical content?

**Answer:** No. Equal total bytes is only one condition; for example, use `Files.mismatch` to compare bytes.

## 14. Takeaways

- **`transferTo`:** source `FileChannel` → target `WritableByteChannel`; `position` is the **source** offset.
- **`transferFrom`:** source `ReadableByteChannel` → target `FileChannel`; `position` is the **destination** offset.
- Both return the **actual number of bytes transferred**, do not default to `count`, and do not change the position of the `FileChannel` on which the method is called.
- To transfer all data, use a `long` loop, advance the offset by each call's result, guard against `0`, and verify integrity after completion.
