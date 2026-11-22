# Closing and Reopening Files with Verified Read/Write Positions

When a Java application uses CRaC, the process can be checkpointed and then restored after a period of time. If the application is reading or writing a file, it should not simply hold a `FileChannel` or `RandomAccessFile` in the heap and assume the file descriptor and read/write position will still be usable after restore. An explicit procedure needs to record the offset, complete in-flight I/O, flush necessary data, close the file before checkpoint, and then reopen the file and verify both content and position before continuing.

This practice exercise uses `FileChannel` to write two UTF-8 records, close the file, reopen it, read and check the offset, continue writing at the saved position, and open it again to confirm the data. The latter part integrates that procedure with CRaC `Resource` and explains the limitations when the file is modified while the process is paused.

## 1. Read/write position is a byte offset

`FileChannel.position()` returns the current position in bytes from the beginning of the file. `FileChannel.position(long)` sets the next position for sequential read/write operations on the channel. `RandomAccessFile.getFilePointer()` and `seek(long)` also work with byte offsets.

This is especially important with UTF-8. A Vietnamese character can occupy multiple bytes. The number of characters in a Java string is not necessarily equal to the number of bytes written to the file.

Example:

```java
String text = "Xin chào CRaC";
int javaChars = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

System.out.println("String.length=" + javaChars);
System.out.println("UTF-8 bytes=" + utf8Bytes);
```

Do not use `String.length()` as an offset to seek in a UTF-8 file. Store the exact number of bytes read/written or use a record format with clearly defined framing and offsets.

## 2. Distinguishing channel position and application-managed offset

A `FileChannel` has a current position. After a sequential `read(ByteBuffer)` or `write(ByteBuffer)`, this position is updated. When the channel is closed, the current position no longer resides in an open channel; when reopened, the new channel starts at the API's default position (usually byte 0), so the application must seek again.

There are two approaches:

| Approach | API | Effect on `channel.position()` |
| --- | --- | --- |
| Sequential I/O | `read(buffer)`, `write(buffer)`, `position(offset)` | Read/write updates the current position. |
| I/O at explicit offset | `read(buffer, offset)`, `write(buffer, offset)` | Does not change the channel's current position. The application manages the offset itself. |

If there is only one thread reading/writing, using the current position can be simple. If there are multiple threads or you need to keep the read cursor and write cursor independent, positional I/O is usually easier to control; synchronization is still needed if multiple write operations could overwrite the same byte region.

Do not let multiple threads concurrently modify `channel.position()` without a lock. One thread could seek while another thread is reading, causing the next operation to start at an unintended offset.

## 3. Preparing the practice file

The example below uses a binary file with UTF-8 content. We write the first record, save the ending offset, close the channel, reopen it, and verify the data before writing the second record.

Create a standard Java project, then add the following class. The example uses Java 11 or later and requires no external libraries:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public final class FilePositionDemo {

    private static void writeFully(FileChannel channel, ByteBuffer source)
            throws IOException {
        while (source.hasRemaining()) {
            int written = channel.write(source);
            if (written == 0) {
                Thread.yield();
            }
        }
    }

    private static void readFully(FileChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            int read = channel.read(target);
            if (read < 0) {
                throw new EOFException("File ended before the buffer was full");
            }
            if (read == 0) {
                Thread.yield();
            }
        }
    }

    private static void requirePosition(long actual, long expected, String label) {
        if (actual != expected) {
            throw new IllegalStateException(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Path.of("build", "file-position-demo.bin");
        Files.createDirectories(file.getParent());

        byte[] firstRecord = "id=1;message=Đã lưu trước checkpoint\n"
                .getBytes(StandardCharsets.UTF_8);
        byte[] secondRecord = "id=2;message=Tiếp tục sau khi mở lại\n"
                .getBytes(StandardCharsets.UTF_8);

        long savedWritePosition;

        // First open: create the file and write the first record.
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            channel.position(0);
            writeFully(channel, ByteBuffer.wrap(firstRecord));

            savedWritePosition = channel.position();
            requirePosition(savedWritePosition, firstRecord.length,
                    "write position after first record");

            // Push file content and metadata according to the OS/storage capabilities.
            channel.force(true);
        }

        // Second open: read back the old data, verify the cursor, then continue writing.
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            channel.position(0);
            ByteBuffer firstRead = ByteBuffer.allocate(firstRecord.length);
            readFully(channel, firstRead);

            if (!Arrays.equals(firstRecord, firstRead.array())) {
                throw new IllegalStateException("First record content mismatch");
            }

            requirePosition(channel.position(), savedWritePosition,
                    "read position after first record");

            // Seek to the offset saved before closing the channel.
            channel.position(savedWritePosition);
            requirePosition(channel.position(), savedWritePosition,
                    "reopened write position");

            writeFully(channel, ByteBuffer.wrap(secondRecord));
            channel.force(true);

            long expectedEnd = savedWritePosition + secondRecord.length;
            requirePosition(channel.position(), expectedEnd,
                    "write position after second record");
        }

        // Third open: verify the second record starts at the exact saved offset.
        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            channel.position(savedWritePosition);
            ByteBuffer secondRead = ByteBuffer.allocate(secondRecord.length);
            readFully(channel, secondRead);

            if (!Arrays.equals(secondRecord, secondRead.array())) {
                throw new IllegalStateException("Second record content mismatch");
            }

            long expectedEnd = savedWritePosition + secondRecord.length;
            requirePosition(channel.position(), expectedEnd,
                    "read position after second record");
        }

        System.out.println("File: " + file.toAbsolutePath());
        System.out.println("Saved write position: " + savedWritePosition + " bytes");
        System.out.println("Final file size: " + Files.size(file) + " bytes");
        System.out.println("Read/write positions and record contents verified.");
    }
}
```

The program intentionally uses `readFully` and `writeFully`. A single read/write on a channel is not guaranteed to process the entire `ByteBuffer`; the code must loop until the buffer has no remaining data. When reading reaches EOF before the buffer is full, the example throws `EOFException` instead of silently treating incomplete data as valid.

`force(true)` requests the channel to write file content and metadata changes to storage according to the capabilities of the operating system and device. It does not replace database transactions, does not guarantee every filesystem/network storage has the same semantics, and does not automatically make a file rename in the parent directory durable across all platforms.

## 4. Running and observing the result

Compile and run the class:

```bash
javac FilePositionDemo.java
java FilePositionDemo
```

The output includes the file path, the offset after the first record, the final size, and a successful verification message. The offset numbers are calculated in UTF-8 bytes; because the strings contain Vietnamese diacritics, they can be larger than the number of displayed characters.

You can inspect the file using operating system commands:

```bash
cat build/file-position-demo.bin
wc -c build/file-position-demo.bin
```

The `cat` command is only appropriate because the example writes UTF-8 text to the file. In production applications, do not use commands that display the entire file if it may contain sensitive data.

## 5. Why verify both position and content?

Simply calling `channel.position(savedOffset)` and reading back `channel.position()` proves that the channel accepted the offset, but does not prove that the offset points to the expected data.

For example, the file could be truncated, replaced with another file, have bytes inserted, or have its content modified while the application was closed. In that case:

- The offset is still within the file bounds but points to a different record.
- The file size remains the same, but the content has been replaced.
- The offset is in the middle of a record or in the middle of a UTF-8 sequence.
- The file path points to a different inode after the file is rotated/replaced.

Therefore, upon reopening, you should check at least:

1. The file exists and has appropriate read/write permissions.
2. The file size complies with the policy.
3. The offset is non-negative and does not exceed valid bounds.
4. The offset aligns with record boundaries if the file has record framing.
5. The header, generation id, record id, or checksum at the relevant region matches the saved metadata.
6. After seeking, read a sample record/marker and verify it before continuing to write or process.

For a file managed by a single process, you can require the size to remain unchanged between closing and reopening. If an external writer is allowed to append, you need to clearly define a high-water mark and verify the prefix; do not mechanically apply the `size == expectedSize` condition.

## 6. Using `RandomAccessFile` to check the file pointer

`RandomAccessFile` is another simple API for operating at an offset. `seek(long)` sets the file pointer and `getFilePointer()` returns the current position in bytes.

```java
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

byte[] payload = "record-10: dữ liệu mẫu\n".getBytes(StandardCharsets.UTF_8);
long savedPosition;

try (RandomAccessFile file = new RandomAccessFile("records.dat", "rw")) {
    file.seek(0);
    file.write(payload);
    savedPosition = file.getFilePointer();
    file.getFD().sync();
}

try (RandomAccessFile file = new RandomAccessFile("records.dat", "rw")) {
    file.seek(0);
    byte[] actual = new byte[payload.length];
    file.readFully(actual);

    if (!Arrays.equals(payload, actual)) {
        throw new IllegalStateException("Content mismatch");
    }

    file.seek(savedPosition);
    if (file.getFilePointer() != savedPosition) {
        throw new IllegalStateException("File pointer mismatch");
    }

    file.write("record-11: tiếp tục\n".getBytes(StandardCharsets.UTF_8));
    file.getFD().sync();
}
```

The `"rw"` mode opens the file for reading/writing and does not automatically truncate old content. If you want to overwrite from the beginning, you need to explicitly truncate with `setLength(0)` or use `FileChannel` with `TRUNCATE_EXISTING`. Do not confuse `seek(0)` with truncate: seek only moves the pointer, it does not delete data.

`RandomAccessFile` is convenient for sequential practice exercises. `FileChannel` is more flexible when you need positional I/O, `ByteBuffer`, file locking, or integration with NIO.

## 7. Integrating with CRaC: save offset, flush, and close before checkpoint

During checkpoint, Java objects can be kept in the heap, but file descriptors/channels need to be managed according to the lifecycle. A simple approach is to save the offset into a field of `Resource`, force the data if the application has just written, and then close the channel in `beforeCheckpoint`. After restore, reopen the file, check the size/marker, and seek to the saved offset.

The example below illustrates the core part. The `stopAcceptingFileWork()` and `awaitInFlightFileWork()` operations belong to the application's coordinator; they must prevent new operations and drain in-flight I/O before saving the cursor.

```java
import org.crac.Context;
import org.crac.Resource;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public final class ReopenableFileResource implements Resource {
    private static final int ANCHOR_BYTES = 16;

    private final Path path;
    private FileChannel channel;
    private long savedPosition;
    private long expectedSize;
    private byte[] anchor = new byte[0];
    private boolean accepting = true;

    public ReopenableFileResource(Path path) throws IOException {
        this.path = path;
        this.channel = FileChannel.open(
                path, StandardOpenOption.READ, StandardOpenOption.WRITE);
        this.expectedSize = channel.size();
        this.savedPosition = channel.position();
        this.anchor = captureAnchor(channel, savedPosition);
    }

    public synchronized void seek(long byteOffset) throws IOException {
        ensureOpen();
        if (byteOffset < 0 || byteOffset > channel.size()) {
            throw new IllegalArgumentException("Offset outside file bounds");
        }
        channel.position(byteOffset);
    }

    public synchronized long position() throws IOException {
        ensureOpen();
        return channel.position();
    }

    @Override
    public synchronized void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        accepting = false;
        try {
            stopAcceptingFileWork();
            awaitInFlightFileWork();

            if (channel == null || !channel.isOpen()) {
                throw new IOException("File channel is not open");
            }
            savedPosition = channel.position();
            expectedSize = channel.size();
            anchor = captureAnchor(channel, savedPosition);

            channel.force(true);
            channel.close();
            channel = null;
        } catch (Exception e) {
            if (channel != null && channel.isOpen()) {
                accepting = true;
            }
            throw e;
        }
    }

    @Override
    public synchronized void afterRestore(Context<? extends Resource> context)
            throws Exception {
        reopenAndVerify();
        accepting = true;
        resumeFileWork();
    }

    // Use if the checkpoint attempt is aborted after beforeCheckpoint has closed the file.
    // This is the application's rollback path, not CRaC afterRestore.
    public synchronized void resumeAfterAbortedCheckpoint() throws IOException {
        if (channel == null || !channel.isOpen()) {
            reopenAndVerify();
        }
        accepting = true;
        resumeFileWork();
    }

    private void reopenAndVerify() throws IOException {
        FileChannel reopened = FileChannel.open(
                path, StandardOpenOption.READ, StandardOpenOption.WRITE);
        try {
            long actualSize = reopened.size();
            if (actualSize != expectedSize) {
                throw new IOException("File size changed while channel was closed: expected="
                        + expectedSize + ", actual=" + actualSize);
            }

            if (savedPosition < 0 || savedPosition > actualSize) {
                throw new IOException("Saved position is outside the reopened file");
            }

            byte[] actualAnchor = captureAnchor(reopened, savedPosition);
            if (!Arrays.equals(anchor, actualAnchor)) {
                throw new IOException("File content near saved position changed");
            }

            reopened.position(savedPosition);
            if (reopened.position() != savedPosition) {
                throw new IOException("Could not restore the saved file position");
            }

            channel = reopened;
        } catch (IOException | RuntimeException e) {
            reopened.close();
            throw e;
        }
    }

    private static byte[] captureAnchor(FileChannel channel, long position)
            throws IOException {
        int length = (int) Math.min(ANCHOR_BYTES, position);
        ByteBuffer buffer = ByteBuffer.allocate(length);
        long start = position - length;
        while (buffer.hasRemaining()) {
            int count = channel.read(buffer, start);
            if (count < 0) {
                throw new IOException("Unexpected EOF while reading anchor");
            }
            if (count == 0) {
                Thread.yield();
            } else {
                start += count;
            }
        }
        return buffer.array();
    }

    private void ensureOpen() throws IOException {
        if (!accepting || channel == null || !channel.isOpen()) {
            throw new IOException("File operations are paused or the channel is closed");
        }
    }

    private void stopAcceptingFileWork() {
        // Notify the application coordinator to reject new file operations.
    }

    private void awaitInFlightFileWork() {
        // Wait with a bounded deadline using a coordinator that does not need
        // this object's monitor. All file I/O must pass through this ownership boundary.
    }

    private void resumeFileWork() {
        // Allow file operations only after reopen and verification succeed.
    }
}
```

This is a lifecycle skeleton, in which the three coordinator methods need to be connected to the application's actual worker management mechanism. `synchronized` prevents the object's methods from running concurrently while the callback holds the monitor, but it does not automatically stop other threads operating directly on the channel or file; all I/O must pass through the same ownership boundary.

The anchor only checks 16 bytes immediately preceding the cursor. It helps detect some cases where the file was modified, but does not prove the entire file is identical. In production, you should use a file generation id/header, record sequence, immutable file identity, or checksum of the data region to be protected. `BasicFileAttributes.fileKey()` can be useful as an additional signal, but is not supported by all filesystems and is not a portable identifier across hosts/restores.

The example requires `actualSize == expectedSize` because it assumes the file is managed solely by this resource during the checkpoint window. If another process is allowed to append during that time, use a high-water mark and verify the prefix according to policy instead of enforcing strict size equality.

## 8. Registering the Resource and triggering checkpoint

After creating the resource, register it with the CRaC global context using the runtime's API:

```java
ReopenableFileResource resource =
        new ReopenableFileResource(Path.of("data", "records.bin"));

Core.getGlobalContext().register(resource);
```

The application needs to import `org.crac.Core` and use the appropriate CRaC dependency supported by the JDK/runtime. Registration must happen once in the appropriate lifecycle phase; avoid creating multiple Resources managing the same file/channel.

When a checkpoint is requested, CRaC calls `beforeCheckpoint`; after the process is restored, the runtime calls `afterRestore`. It can be triggered via the API or command provided by the CRaC JDK. The exact syntax and semantics depend on the distribution/version. Do not assume that calling callbacks manually is equivalent to an actual checkpoint/restore.

After `afterRestore`, only resume read/write workers when `reopenAndVerify()` succeeds. If the file is no longer valid, report an error and keep the component unavailable instead of continuing to write at an uncertain offset.

## 9. Why must I/O be drained before saving the position?

If the callback reads `channel.position()` while another thread is writing, the saved offset may not reflect the record boundary the application expects. If an application buffer still holds unwritten data, `channel.position()` may reflect the number of bytes sent to the channel, but not the logical data remaining in the buffer.

Before checkpoint:

1. Stop accepting new file work.
2. Wait for current read/write operations to complete.
3. Flush `BufferedOutputStream`, writers, or application buffers if any.
4. Call `FileChannel.force(true)` if it is necessary to request that file content and metadata be pushed to storage.
5. Save the offset after all buffers have been processed.
6. Close the channel.

Do not take the offset from `FileChannel` and ignore higher-level buffers. For example, `BufferedWriter` may be holding characters not yet written to the channel; the channel's cursor will be lower than the writer's logical position.

If the application has multiple writers, a coordinator/lock is needed to wrap the entire drain, flush, capture cursor, and close sequence. Do not lock only the `channel.position()` line.

## 10. BufferedReader and read-ahead position

A common mistake is using `BufferedReader` to read text and then taking `FileChannel.position()` as the offset of the line just read. `BufferedReader` and decoders can read ahead many bytes into an internal buffer. The channel position at that point may be past the end of the logical line the application just received.

Example:

```text
File bytes:  [line 1][line 2][line 3][line 4]
Application: finished reading line 1
BufferedReader: may have already loaded line 2 and part of line 3
FileChannel position: may be past line 1
```

If the checkpoint saves the channel position, after restore the application may skip the data that was read ahead but not yet processed.

Solutions:

- Use `FileChannel` and a byte-level parser with explicit offset management.
- Use record framing with a fixed length or delimiter handled at the byte layer.
- Track the logical cursor managed by the parser itself; do not take the channel position when there is a read-ahead buffer.
- If using `BufferedReader`, a wrapper mechanism is needed to track the consumed logical offset; do not infer the offset from the underlying channel.

With UTF-8, the newline delimiter is byte `0x0A`, but character content can consist of multiple bytes. The parser needs to handle the case where the buffer ends in the middle of a multi-byte encoded sequence. Use `CharsetDecoder` properly or explicit byte framing; do not arbitrarily slice strings by character index.

## 11. Partial read/write and EOF checking

Do not assume a single `read` or `write` call processes the entire buffer. The NIO API allows reading/writing fewer bytes than remaining. This is especially important when using non-blocking channels, network channels, or file operations in special environments.

Rules:

- Loop until `ByteBuffer.hasRemaining()` returns false.
- When read returns `-1`, handle EOF; if expecting a full record, this is truncated data.
- When read returns `0`, do not advance the offset; wait or retry according to an appropriate policy.
- Only update the logical cursor after the entire record has been successfully read/written.
- If a write fails mid-record, do not mark the record as complete; upon restart, check/truncate the partial tail according to the file format.

With blocking regular file channels, operations usually make progress, but general code should still handle partial I/O. Do not use `channel.size()` as a substitute for checking record completeness.

## 12. Storing the cursor in heap or metadata file?

If the goal is to restore the exact process image, fields in the `Resource` object can be kept in the heap and restored with the process. For example, `savedPosition` in the skeleton is such a field.

If it is necessary to continue after a cold restart without a checkpoint, or to recover when the checkpoint artifact is lost, the offset must be stored in separate durable metadata. You can store:

- File generation id or logical file identity.
- Read offset and write offset.
- File size/high-water mark.
- Last processed record id/sequence.
- Checksum/anchor of the data region around the cursor.
- File format version.

Metadata should be written in a way that avoids half-written states: write a temporary file, force its contents, then perform an atomic move within the same filesystem if the provider supports it. If atomic move is not supported, design an appropriate recovery marker or storage transaction.

An offset is only meaningful when paired with a file generation/version. If the file is rotated or replaced with a new file, the old offset must not be automatically applied to the new file even if the size is the same.

## 13. Handling files modified during checkpoint

The application must define who owns the file while the process is checkpointed.

| Scenario | Handling |
| --- | --- |
| No other writers and file is immutable | Check size, generation/header, and anchor; require size match. |
| File is only appended to by another writer | Save high-water mark; verify prefix up to high-water mark; decide whether to read the newly appended part. |
| File is rotated/replaced | Use generation id or file identity; do not use the old offset on the new file. |
| File is truncated | Detect `size < savedPosition` or checksum/record validation failure; stop processing. |
| Content is modified but size is unchanged | Check record id/version or checksum; size alone is not enough. |
| File is on a network filesystem | Confirm cache/locking/rename/force semantics of the filesystem and test on the actual mount. |

If the file is managed by another service, use a protocol/lease to confirm the file generation and high-water mark. Do not rely on the path still existing.

## 14. Appending and avoiding data overwrites

To continue writing from the end of the file, you can get `size()` and seek there, but this is only safe when write access is coordinated. If another writer appends concurrently between reading the size and writing, both writers could pick the same offset and overwrite each other.

With a single writer:

```java
long end = channel.size();
channel.position(end);
writeFully(channel, ByteBuffer.wrap(recordBytes));
```

With multiple writers, use an appropriate serialization/locking mechanism, or use positional writes into separately allocated regions. `FileLock` in Java can assist with inter-process coordination on some filesystems, but locks are often advisory and semantics depend on the OS/filesystem. It does not replace a distributed lock or storage protocol.

Do not assume `StandardOpenOption.APPEND` combined with `position()` will produce the desired seek-and-overwrite behavior on every provider. If you need to write at a specific offset, open the channel with `READ`/`WRITE`, use explicit offsets, and manage concurrency clearly.

## 15. Writing files safely when updating metadata

If the offset is stored in a sidecar, avoid overwriting the metadata file in place and leaving partial content if the process is stopped. A common pattern:

1. Write the full metadata to a temporary file on the same filesystem.
2. Call `force(true)` on the temporary file.
3. Close the file.
4. Use `Files.move(temp, target, ATOMIC_MOVE, REPLACE_EXISTING)` if the filesystem supports it.
5. If `AtomicMoveNotSupportedException` occurs, use a recovery strategy with versions/markers instead of assuming the move is still atomic.

Atomic rename prevents readers from seeing a half-written metadata file when supported by the filesystem. It does not by itself guarantee that the directory entry is durably flushed across all power loss events; ultimate durability depends on the filesystem and storage.

## 16. Errors and rollback when checkpoint fails

An important scenario: `beforeCheckpoint` has closed the file, but the dump operation fails. The original process may continue without running `afterRestore`.

Therefore, a separate rollback/resume path is needed:

- The coordinator knows which Resources were closed.
- If the checkpoint aborts, call the resume method for the original process.
- Reopen the file, verify generation/size/anchor, and seek back to the cursor.
- Only resume workers after verification succeeds.
- If it cannot be reopened safely, keep the component `NOT_READY` and report an error.

Do not use `afterRestore` as a rollback callback for a failed checkpoint. `afterRestore` belongs to the restore flow; it is not guaranteed to run when a checkpoint attempt is aborted.

If the file was modified during the aborted checkpoint, do not automatically continue writing at the old offset. Reconcile with the file owner or recover from metadata/backup according to policy.

## 17. File locking and multiple processes

If multiple processes access the file concurrently, synchronization semantics must be defined. `FileChannel.lock()` can lock a region or the entire file depending on the overload; `tryLock()` allows checking without blocking indefinitely. However:

- File locks may be advisory; other processes that do not honor the lock can still write.
- Behavior depends on the OS and filesystem.
- A lock object should not be considered valid across a checkpoint if the channel was closed.
- After restore, a new channel must be opened and a new lock acquired.
- Do not hold locks while waiting for a checkpoint if doing so causes other processes to deadlock or time out.

A safe procedure is to stop accepting work, drain operations, release the lock, checkpoint; after restore, open the file, check generation, and reacquire the lock before continuing. If the file is shared across multiple hosts, use locking/coordination supported by the storage instead of assuming local `FileLock` provides distributed mutual exclusion.

## 18. Permissions, symbolic links, and paths

After restore, the file path may point to a different location if the mount namespace or volume mapping changed. Check:

- The path resolves in the correct mount namespace/container.
- The process's User/UID/GID has read/write permissions.
- The file has not been replaced by a symbolic link pointing outside the intended directory.
- The parent directory has appropriate access permissions.
- The volume is mounted and ready before `afterRestore` opens the file.
- The file has not been deleted or unexpectedly rotated by a cleanup job.

If the path comes from external input, canonicalize it and verify it lies within the permitted data area. Do not open an arbitrary path from checkpoint metadata without validation.

## 19. Testing edge cases

In addition to the happy path, test:

- Empty file, offset 0.
- Offset at exact EOF.
- Negative offset or offset greater than file size.
- File truncated before reopen.
- File replaced with another file of the same size.
- Last byte of a record missing.
- Write only completes part of a record and then fails.
- UTF-8 character split across two buffers.
- BufferedReader reading ahead across multiple lines.
- Two threads concurrently seeking/reading/writing.
- Two processes concurrently appending.
- Permissions changed after restore.
- Mount/volume not yet ready.
- Checkpoint aborted after the channel was closed.
- Repeated restores from the same artifact.

Check both content and position. An arithmetically valid offset that points to the wrong record is still a bug.

## 20. Common errors table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| After reopening, reads from the beginning of the file | New channel has not been seeked | Restore the saved offset and verify `position()`. |
| Skips part of the data | Offset calculated in characters instead of bytes, or BufferedReader read-ahead | Store logical byte offset at the parser/framing layer. |
| Overwrites old records | Stale write offset or two writers using the same position | Check high-water mark and synchronize writers. |
| Reads incomplete record | Assumed a single `read()` fills the buffer | Use a `readFully` loop and detect EOF. |
| File size is correct but content is wrong | File was replaced or modified with the same size | Check generation id, record sequence, or checksum. |
| File loses data after checkpoint | Application buffers not flushed or not forced per policy | Drain, flush higher layers, `force(true)`, and confirm storage semantics. |
| Resource fails to reopen after restore | Volume not mounted, permissions changed, or wrong path | Validate mount/identity/permissions before resuming. |
| Original process stuck after checkpoint abort | Channel was closed with no rollback path | Call a separate resume coordinator; do not wait for `afterRestore`. |
| Lock is gone after restore | Lock was tied to the old channel/descriptor | Open a new channel and reacquire the lock. |

## 21. Practice checklist

- [ ] Use byte offsets, not `String.length()` for UTF-8 files.
- [ ] Record the offset after the operation completes, not in the middle of a record.
- [ ] Use `readFully`/`writeFully` to handle partial I/O.
- [ ] Distinguish channel position from application-explicit offset.
- [ ] Drain workers and flush buffers before capturing the cursor.
- [ ] Call `force(true)` when durability of file content/metadata is required.
- [ ] Close the channel before checkpoint according to the resource lifecycle.
- [ ] After restore, open a new channel and check permissions/path.
- [ ] Verify file size, generation/header, anchor, or record id.
- [ ] Seek to the saved offset and check `channel.position()`.
- [ ] Only resume workers after validation succeeds.
- [ ] Have a rollback/reopen path if the checkpoint is aborted.
- [ ] Define a policy if the file is appended to, rotated, or modified externally.
- [ ] Do not rely on `BufferedReader` read-ahead position as the logical cursor.
- [ ] If multiple writers/processes exist, have explicit locking/coordination.
- [ ] Tested truncation, partial records, UTF-8, permissions, and mount failures.

## 22. Conclusion

To close and reopen a file safely, save the offset in bytes after I/O has completed, flush necessary data, close the channel, open a new channel, and seek to the saved offset. Checking `channel.position()` proves the cursor has been set; re-reading a marker or record at the relevant region is what proves the cursor points to the expected data.

In CRaC, place this procedure in the Resource lifecycle: stop accepting work and drain I/O before checkpoint, save the cursor in restored state, force/close the file, then reopen/verify after restore before resuming workers. If the checkpoint aborts, a separate rollback path is needed to reopen the file in the original process. With UTF-8, buffered readers, file rotation, or multiple writers, logical offset and file identity must be managed explicitly; merely keeping a PID/offset number or a channel object in the heap is not enough.
