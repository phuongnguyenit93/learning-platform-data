# Saving Read/Write Position and Verifying File Contents After Restore

In CRaC (Coordinated Restore at Checkpoint), a Java process can be restored from a checkpoint image and resume the work it was performing. If an application reads or writes files, restoration needs to preserve the exact processing position and confirm that the data on disk still matches the state saved in memory.

An offset stored on the heap only indicates how far the application had processed at the time of the checkpoint. It does not by itself guarantee that the external file remains intact upon restore. The file may have been replaced, truncated, appended to, or modified by another process while the application was stopped.

Therefore, the workflow needs to coordinate three things: synchronizing data being written, saving the read/write position at a safe boundary, and then reopening and verifying the file before continuing after restore.

## 1. How is a file's read/write position represented?

Java provides several APIs for reading and writing files. How the current position is obtained depends on the API being used.

| API | How to get position | Unit |
|---|---|---|
| FileChannel | position() | Byte |
| RandomAccessFile | getFilePointer() | Byte |
| InputStream | No general position API | Must be tracked manually |
| BufferedReader | Does not provide exact byte position | Must track logical position manually |
| BufferedInputStream | Does not provide reliable file offset directly | Must account for data already read ahead into the buffer |

With FileChannel, position() returns the current byte position in the file. After a read or write operation, the position is typically updated by the number of bytes processed. The position can be reset using position(long newPosition).

~~~java
try (FileChannel channel = FileChannel.open(
        Path.of("data.bin"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    long offset = channel.position();

    channel.position(128);
    // Read or write starting from byte 128.
}
~~~

RandomAccessFile provides getFilePointer() and seek(long position), also working in bytes:

~~~java
try (RandomAccessFile file = new RandomAccessFile("data.bin", "rw")) {
    long offset = file.getFilePointer();

    file.seek(128);
    // Read or write from byte 128.
}
~~~

An offset is the number of bytes from the beginning of the file, not the number of characters, lines, or records processed. This distinction is especially important when the file contains UTF-8 text or a format with variable-length records.

## 2. Why must the position be saved at a safe boundary?

Suppose a worker reads one record at a time from a file. If a checkpoint occurs in the middle of processing a record, after restore the application may:

- Re-read an already processed record and produce duplicate results.
- Skip the remainder of the record.
- Resume from the middle of a UTF-8 character.
- Re-write part of a record, leaving the output file malformed.

The application should choose a **resume point** with business meaning, such as:

- The first byte of the next unprocessed record.
- The byte immediately after the last committed record.
- The starting position of a checksummed data block.
- The offset after a write batch has been flushed and confirmed.

A checkpoint state may store:

~~~text
filePath          = /var/lib/myapp/input/events.dat
readOffset        = 1048576
lastRecordId      = 8200
expectedFileSize  = 2097152
expectedDigest    = ...
formatVersion     = 3
~~~

These fields are application metadata. They are saved in the heap along with the checkpoint image if they are part of the checkpointed object state. If the application needs to recover independently of the checkpoint image, the metadata can also be stored in a separate manifest with appropriate atomic write and synchronization rules.

### Saving the offset after completing a record

For example, a worker reads a record, processes it, and only updates the offset after the corresponding work has completed:

~~~java
while (hasNextRecord()) {
    Record record = readNextRecord();

    process(record);
    commitResult(record);

    // Update only after the record has been processed/committed.
    savedOffset = nextRecordByteOffset();
}
~~~

In practice, reading, processing, and committing may involve multiple systems. If the result has been written to the database but the offset has not been saved, restore may reprocess the record. If the offset is saved before the result is committed, restore may skip an incomplete record.

A consistent rule must be chosen, such as writing results with an idempotency key, committing the offset in the same transaction as the result, or accepting reprocessing and deduplicating. Saving the offset alone does not provide an exactly-once guarantee.

## 3. Byte offset and read buffers

A common mistake is taking the FileChannel position after reading through a BufferedReader or BufferedInputStream and treating it as the logical position the application has processed.

Buffered classes read ahead a chunk of data to reduce the number of system calls. As a result, the position of the underlying source may already be ahead of the data the application has actually consumed.

For example:

~~~text
File contents:
|---- record A ----|---- record B ----|---- record C ----|

Processed by the application:
|---- record A ----|

Buffer may have already read:
|---- record A ----|---- record B ----|---- record C ----|
                                      ^
                         FileChannel.position() may be here
~~~

If the channel position is saved in this situation, after restore the application may start from record D and skip B and C even though they have not been processed.

There are three common solutions:

1. Use FileChannel and manually manage the logical offset at record boundaries.
2. Use a parser capable of reporting the number of bytes consumed, instead of taking the position of a pre-read source.
3. If the buffer must be preserved, checkpoint both the buffer state and the decoder state with an explicit design; this approach is more complex and prone to depending on implementation details.

For record-by-record processing, the first approach is usually the easiest to control.

### UTF-8 and multi-byte characters

In UTF-8, a single character can occupy from one to four bytes. A byte offset is not equivalent to a character index.

For example, a string with Vietnamese diacritics may use multiple bytes per character. If the offset is saved in the middle of a character's byte sequence, decoding after restore may encounter invalid data or replacement characters.

Offsets should be saved at record boundaries or well-defined character boundaries. If the format uses newlines as delimiters, the bytes of the newline character must also be counted according to how the file was created on that platform. For binary formats, use record lengths and headers to determine boundaries.

If using a CharsetDecoder, both the remaining bytes in the input buffer and the decoder state must be coordinated. You cannot simply restore FileChannel.position() and assume the decoder is in the initial state of a new character.

## 4. Writing files: flush, force, and saving the write offset

For write operations, the application must push data still sitting in buffers down to the channel before saving the position. Then, if it is necessary to ensure data is pushed to the storage device, call FileChannel.force().

The three operations have different meanings:

- flush() on BufferedWriter or OutputStreamWriter pushes data from the Java class's buffer down to the underlying stream.
- FileChannel.force(true) requests that updates to the file's content and metadata be written out to the storage device according to the system's guarantees.
- position() gets the current offset of the channel.

A typical sequence when preparing for a checkpoint:

~~~text
Stop accepting new write batches
        |
        v
Complete the record currently being written
        |
        v
Flush writer/buffer
        |
        v
FileChannel.force(true)
        |
        v
Save write offset and metadata
        |
        v
Close channel if choosing the reopen-after-restore strategy
~~~

Example:

~~~java
writer.flush();

channel.force(true);

long committedOffset = channel.position();
long committedSize = channel.size();
~~~

This example assumes the writer and channel share the same underlying channel and there are no other concurrent writes. If there are multiple writers or multiple threads, they must be locked or drained before obtaining the offset.

force(true) does not replace the writer's flush(). If data is still in BufferedWriter's buffer, the channel has not received those bytes to force.

If the application writes directly using FileChannel without a Java-layer buffer, force(true) can be called after a write batch. If only content synchronization is needed without requiring metadata synchronization, force(false) may be suitable; the choice depends on data durability requirements.

### Appending and handling trailing data

Suppose the application is appending to a log file and has saved committedOffset = 4096. After restore:

- If the file size is smaller than 4096, committed data may have been lost or the file has been replaced. Do not blindly continue writing.
- If the size equals 4096 and the checksum matches, writing can resume at offset 4096.
- If the size is greater than 4096, data has appeared after the checkpoint. You need to determine whether that data belongs to a committed write, another process, or a partial write.

Only truncate to committedOffset when the application exclusively owns the file and the data policy determines the trailing portion is uncommitted data. If there is another writer or valid new data, truncating will cause data loss.

~~~java
if (channel.size() < committedOffset) {
    throw new IOException("File is shorter than committed offset");
}

if (channel.size() > committedOffset) {
    // Only perform this if the application exclusively owns the file
    // and has determined the trailing part is uncommitted data.
    channel.truncate(committedOffset);
}

channel.position(committedOffset);
~~~

For important data files, writes should be done in batches with markers or checksums to identify that the last record is complete. A partially written record at the end of a file should not be considered committed data.

## 5. Verifying file contents after restore

The checkpoint image stores process state, while the file is an external resource. Between checkpoint and restore, the file may be modified by:

- Another process.
- A log rotation or file replacement job.
- A deployment or data synchronization operation.
- A user editing manually.
- A storage system or remote mount.

Therefore, after restore the file must be verified before resetting the position and resuming reading/writing.

### Checking size

Get the current size:

~~~java
long currentSize = Files.size(path);
~~~

Compare with the size saved at checkpoint. This check is fast but does not detect content changes where the size remains unchanged.

### Checking modification time and file identity

Attributes can be read:

~~~java
BasicFileAttributes attributes = Files.readAttributes(
    path,
    BasicFileAttributes.class
);

long size = attributes.size();
FileTime modified = attributes.lastModifiedTime();
Object fileKey = attributes.fileKey();
~~~

These attributes help detect many cases where a file has been replaced or modified. However:

- lastModifiedTime may be preserved or have insufficient time resolution.
- fileKey may not be provided by the filesystem.
- fileKey is not necessarily stable across mounts or on remote filesystems.

Thus, metadata is a supporting signal; it should not be used alone to confirm content.

### Checking checksum or hash

If content verification is needed, the SHA-256 of the file can be computed at checkpoint and compared after restore.

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");

try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;

    while ((count = input.read(buffer)) != -1) {
        digest.update(buffer, 0, count);
    }
}

byte[] fileHash = digest.digest();
~~~

The hash should be saved as bytes or a stable string representation along with the checkpoint state. After restore, recompute it and compare using MessageDigest.isEqual() when comparing byte arrays.

Hashing the entire file can be time-consuming for large files. Other options include:

- Hashing the committed portion of data.
- Hashing the last block along with the offset and record ID.
- Using per-block checksums within the file format.
- Combining size, file identity, and a checksum of critical regions.

Choose the verification level based on data value and startup cost. Do not skip verification just because the file has the same size.

### Checking data structure

A hash confirms whether the bytes are identical, but it does not replace format validity checks. After restore, the application may need to:

- Verify the file header and version.
- Confirm the offset lies on a record boundary.
- Check that the last record is complete.
- Verify block or record checksums.
- Cross-check sequence numbers or record IDs against saved metadata.

If the file was validly modified by an external process, the application needs a reconciliation policy rather than assuming every difference is corruption.

## 6. Resource managing files across checkpoint and restore

A clear implementation approach is to create a Resource that owns the FileChannel. Before checkpoint, the resource synchronizes data, saves the offset and metadata, and then closes the channel. After restore, the resource reopens the file, verifies the contents, and restores the position.

The example below illustrates reading/writing a file exclusively owned by the application. The computeSha256() method represents a function that computes the SHA-256 of the file contents.

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointFileResource implements Resource {
    private final Path path;
    private final boolean writable;

    private FileChannel channel;
    private long savedPosition;
    private long expectedSize;
    private byte[] expectedHash;
    private boolean closedForCheckpoint;

    public CheckpointFileResource(Path path, boolean writable)
            throws IOException {
        this.path = path;
        this.writable = writable;
        openChannel();
        Core.getGlobalContext().register(this);
    }

    private void openChannel() throws IOException {
        if (writable) {
            channel = FileChannel.open(
                path,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE
            );
        } else {
            channel = FileChannel.open(
                path,
                StandardOpenOption.READ
            );
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        // External writers/buffers must be drained and flushed
        // before getting the channel position.
        if (writable) {
            channel.force(true);
        }

        savedPosition = channel.position();
        expectedSize = channel.size();
        expectedHash = computeSha256(path);

        channel.close();
        closedForCheckpoint = true;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        reopenAndValidate();
    }

    public synchronized void reopenAfterAbortedCheckpoint()
            throws Exception {
        if (closedForCheckpoint) {
            reopenAndValidate();
        }
    }

    private void reopenAndValidate() throws Exception {
        FileChannel reopened = null;

        try {
            if (writable) {
                reopened = FileChannel.open(
                    path,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE
                );
            } else {
                reopened = FileChannel.open(
                    path,
                    StandardOpenOption.READ
                );
            }

            if (reopened.size() != expectedSize) {
                throw new IOException("File size changed after checkpoint");
            }

            byte[] actualHash = computeSha256(path);
            if (!MessageDigest.isEqual(expectedHash, actualHash)) {
                throw new IOException("File content changed after checkpoint");
            }

            if (savedPosition < 0 || savedPosition > expectedSize) {
                throw new IOException("Saved file position is invalid");
            }

            reopened.position(savedPosition);
            channel = reopened;
            reopened = null;
            closedForCheckpoint = false;

        } finally {
            if (reopened != null) {
                reopened.close();
            }
        }
    }

    private byte[] computeSha256(Path file) throws Exception {
        // Read the file in blocks and return SHA-256.
        // Should be implemented using MessageDigest and Files.newInputStream().
        throw new UnsupportedOperationException("Implement SHA-256");
    }
}
~~~

This code is an illustrative skeleton; the SHA-256 implementation and writer synchronization policy need to be added. In production code, import MessageDigest and hash in blocks. If the file is large, replace full-file hashing with checksums by block or protected data region.

The example also assumes the channel is the sole read/write path. If a BufferedWriter or OutputStreamWriter also writes to the channel, they must be flushed before the callback obtains the position and calls force. No other thread may write while metadata is being saved.

### Handling aborted checkpoints

If beforeCheckpoint() closes the channel but the checkpoint is subsequently aborted, afterRestore() is not called for the original process. If the application calls Core.checkpointRestore() directly, it can catch CheckpointException and call reopenAfterAbortedCheckpoint():

~~~java
try {
    Core.checkpointRestore();
} catch (CheckpointException failure) {
    try {
        fileResource.reopenAfterAbortedCheckpoint();
    } catch (Exception reopenFailure) {
        failure.addSuppressed(reopenFailure);
        markApplicationNotReady();
    }

    throw failure;
}
~~~

If the checkpoint is triggered externally via jcmd, the application's calling flow does not have this catch block. In that case, choose a resource strategy suited to the runtime's recovery capabilities or build a management mechanism so the application coordinates the checkpoint itself. Do not assume that afterRestore() will run when a checkpoint is aborted.

## 7. Saving read position and restoring from a byte offset

The following example describes a reader using FileChannel and saving the offset after each record. The readNextRecord() function is assumed to return a complete record along with the next byte offset.

~~~java
public final class RecordReader {
    private FileChannel channel;
    private long nextOffset;

    public RecordReader(FileChannel channel, long savedOffset)
            throws IOException {
        this.channel = channel;
        this.nextOffset = savedOffset;
        this.channel.position(savedOffset);
    }

    public void processNext() throws Exception {
        RecordWithOffset item = readNextRecord(channel);

        process(item.record());
        commit(item.record());

        // Update after the record has been processed and committed.
        nextOffset = item.nextByteOffset();
    }

    public long checkpointOffset() {
        return nextOffset;
    }

    public void rebindChannel(FileChannel reopened) throws IOException {
        this.channel = reopened;
        this.channel.position(nextOffset);
    }
}
~~~

RecordWithOffset and readNextRecord() are illustrative types and functions. An actual parser must determine the next byte offset from the data consumed, not by taking the channel's position after a buffer has read ahead multiple records.

After restore:

1. Reopen the exact same file.
2. Verify the file and format.
3. Check that nextOffset is a valid record boundary.
4. Set channel.position(nextOffset).
5. Resume reading the next record.

If a record has been processed but its result has not been committed, the application needs to reprocess it according to an idempotency policy. Do not mark an offset as completed before the result is committed.

## 8. Saving write position and resuming append

For a writer, the position after the last fully written and synchronized record must be saved. For example:

~~~java
public final class AppendWriter {
    private FileChannel channel;
    private long committedOffset;

    public AppendWriter(FileChannel channel) throws IOException {
        this.channel = channel;
        this.committedOffset = channel.position();
    }

    public void append(byte[] record) throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(record);

        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }

        channel.force(true);
        committedOffset = channel.position();
    }

    public long checkpointOffset() {
        return committedOffset;
    }

    public void rebindChannel(FileChannel reopened) throws IOException {
        this.channel = reopened;
        this.channel.position(committedOffset);
    }
}
~~~

After restore, reopen the file, verify the size and contents up to committedOffset, and then position the channel at that offset to continue writing.

If data after committedOffset might belong to another process, do not truncate automatically. Use file locks, leases, or a coordination mechanism between writers to ensure file ownership.

If multiple instances restore from the same checkpoint image and write to a shared file concurrently, they may overwrite or append data in a race. Separate files per instance or an out-of-process synchronization protocol is required.

## 9. Managing files that change while the application is checkpointed

There are files that are allowed to change while the application is stopped. For example, an input log that continues to be appended to by another system.

Not every change is an error. A policy should be defined based on the role of the file:

| File type | Post-restore policy |
|---|---|
| Immutable input | Require hash/identity match; stop if contents changed |
| Append-only input | Verify the already-read portion, then continue reading new data from the saved offset |
| Application-exclusively-owned output | Verify the committed portion; handle trailing data according to commit rules |
| Shared output | Use locks/leases or coordinated writing; do not truncate automatically |
| Rotated log | Locate the exact file generation by ID/inode or manifest; do not rely solely on path name |

For append-only input, the current size can be larger than the checkpoint size without being an error. The application needs to verify that the processed prefix is unchanged, then continue from savedOffset to read the new part.

If a log has rotated, the old path may point to a new file while the old data was renamed. Generation identifiers or file identity information should be saved, and the log system's manifest should be used to locate the right file.

## 10. Safely writing checkpoint metadata

If the offset and checksum reside in checkpointed Java objects, they travel with the process's heap state. However, it may be necessary to write metadata to a separate file to support recovery, auditing, or reconciliation with external data.

When writing a separate manifest, avoid updating the active metadata file in place. A common approach is:

1. Write the new contents to a temporary file on the same filesystem.
2. Flush and force the temporary file.
3. Rename the temporary file to the main manifest file using an atomic move operation if the filesystem supports it.
4. Sync the directory metadata if system durability requirements demand this operation and the platform provides a way to perform it.
5. Only after the manifest is committed should the offset be considered valid checkpoint metadata.

A manifest may contain:

~~~text
version=1
file=/var/lib/myapp/input/events.dat
offset=1048576
size=2097152
sha256=...
lastRecordId=8200
~~~

Upon restore, validate the metadata version, file path, offset, size, checksum, and record ID. If the metadata is invalid, transition the application to a controlled error state rather than guessing the offset.

If using an off-heap manifest, the timing of committing the manifest must be coordinated with when the checkpoint image is created. A new manifest written when the checkpoint fails may not match the heap state of the original process. A generation ID or checkpoint attempt ID can be stored to identify which attempt the manifest belongs to.

## 11. Common errors and how to handle them

### Offset is greater than file size

The cause may be that the file was truncated, replaced, or the metadata was saved incorrectly.

How to handle: do not seek and continue. Check the file identity, checksum, backup copies, or data source. Only restart from the beginning when business rules allow it.

### Offset is valid but contents have changed

The size may remain unchanged while bytes inside were modified. Compare the hash or checksum of the committed data region. If it does not match, stop reading/writing and treat it as a different data version.

### Skipping data because the buffer read ahead

Do not directly save channel.position() after a parser has read through a BufferedReader or a large buffer. Track the logical offset of committed records or restore both the buffer and decoder state.

### Incomplete writes due to missing flush

If only the offset is saved without flushing the writer, data remaining in the buffer may not be in the file. Flush the writer, force the channel when durability is required, and only then save the committed offset.

### Partially written trailing data

If the last write did not complete, restore may encounter a record missing bytes or having a bad checksum. Use record lengths, markers, or checksums to detect this. Only truncate the trailing part when the application exclusively owns the file and knows the exact committed offset.

### File replaced while keeping the same name

A path is only a locator name, not proof that the file is still the same object. Check file identity when provided by the platform and verify contents with a hash or checksum.

### Channel closed before checkpoint but checkpoint aborted

If beforeCheckpoint() closes the channel, the old process may continue after a checkpoint failure with the channel still closed. With Core.checkpointRestore(), catch CheckpointException and reopen the channel according to the saved state. With external jcmd, an appropriate recovery procedure is needed because the application cannot catch the exception in the API call flow.

## 12. Implementation workflow

A file read/write workflow across CRaC can be organized as follows.

### Before checkpoint

1. Stop accepting new work related to the file.
2. Wait for in-flight read/write operations to complete at a record or batch boundary.
3. Flush writers and buffers.
4. Force data if required by durability needs.
5. Save the committed byte offset.
6. Save the appropriate size, file identity, version, and checksum.
7. Close the channel if choosing the reopen-after-restore strategy.
8. Register the Resource with CRaC so the runtime invokes the callbacks.

### After restore

1. Reopen the exact path or locate the exact file generation.
2. Check size and identity.
3. Verify the checksum or contents of the committed region.
4. Confirm the offset is within bounds and at a valid record boundary.
5. Reset channel.position(savedOffset).
6. Reinitialize readers/writers and buffers in a consistent state.
7. Only resume work after all checks succeed.

### When verification fails

Do not resume reading/writing using the old offset if the file contents no longer match. Log the file details, offset, size, generation, and checksum; keep the application in a not-ready state; then choose a recovery policy such as re-reading from the source, using a valid replica, or requiring operator intervention.

## 13. Key principles to remember

- FileChannel.position() and RandomAccessFile.getFilePointer() represent positions in bytes.
- Do not confuse byte offsets with the number of characters or records processed.
- Choose offsets at committed record or batch boundaries.
- Read-ahead buffers can cause the channel position to advance beyond the application's logical position.
- Flush writers before obtaining the position; use force() when data must be synchronized to storage.
- Saving both the offset and metadata helps detect file modifications.
- After restore, reopen the file and verify contents before seeking and continuing.
- Do not truncate trailing data if the application does not exclusively own the file.
- Distinguish between an aborted checkpoint and a successful restore to recover the channel along the right branch.
- For large or append-only files, verify by block, committed prefix, or record checksums to reduce overhead.
- If multiple instances restore simultaneously, coordinate write access or use separate files per instance.

Saving the read/write position is only meaningful when it is tied to verified data and a consistent processing boundary. When an application flushes data, saves the committed offset, verifies the file after restore, and only resumes when conditions are met, the CRaC lifecycle can continue file work without silently skipping or duplicating data.
