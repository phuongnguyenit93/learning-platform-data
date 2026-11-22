# Closing and Reopening InputStream, OutputStream, and FileChannel

In Java applications, InputStream, OutputStream, and FileChannel are commonly used APIs for reading or writing data. When an application supports CRaC, these objects need to be considered according to the lifecycle of the resources they represent. An open stream or channel may hold a file descriptor or I/O state managed by the operating system. The fact that a Java object still exists in the heap after restore does not guarantee that the underlying handle is still valid.

A common approach is to bring I/O to a safe state before checkpoint: stop ongoing operations, write all pending data, save the necessary information to resume, and then close the stream or channel. After restore, the application reopens the resource and restores the read/write position or state according to its design.

Not every InputStream or OutputStream can be closed and reopened in the same way. The recovery approach depends on the data source, file open mode, buffer state, read/write position, and the protocol of the external system.

## 1. Why Is It Necessary to Close and Reopen I/O Resources?

A stream or channel object is usually a Java layer representing an underlying resource:

- FileInputStream and FileOutputStream typically use a file descriptor to operate on a file.
- BufferedInputStream and BufferedOutputStream additionally hold buffered data in the heap while wrapping another stream.
- FileChannel provides positional read and write operations and can hold a file lock.
- A network stream may represent a socket connected to a remote peer.

Checkpoint saves the Java process state according to the CRaC runtime mechanism. During the time the process is paused, the file may be modified, a remote service may close the socket, access permissions may change, or a handle may not be supported for restoration in the current environment.

Therefore, one should not infer that a non-null Java field means the resource is still usable. For example:

~~~java
if (inputStream != null) {
    int value = inputStream.read();
}
~~~

The condition above only checks the Java reference. It does not prove that the file descriptor, socket, or peer state is still valid after restore.

For files, the application can usually reopen them using the path and access mode. For network streams, reopening often requires re-executing the connection protocol, authentication, subscription, or offset recovery. A general stream does not provide automatic read/write position recovery.

## 2. General Principles Before Checkpoint and After Restore

Before checkpoint, the I/O management component needs to coordinate with the consuming layer so that no thread continues reading or writing while the handle is being closed. A typical process includes:

1. Stop accepting new work that may use the stream or channel.
2. Wait for ongoing operations to complete or cancel them according to the application's rules.
3. Flush write data residing in buffers.
4. Record the position or logical checkpoint needed to resume.
5. Close the stream/channel and release references to the old handle.

After restore:

1. Re-read the current configuration, paths, and access permissions.
2. Open a new stream/channel with the appropriate read or write mode.
3. Restore the read/write position if the data source supports it and the application has saved that position.
4. Check the state of the file or external service before continuing.
5. Only allow new work after the resource is ready.

The CRaC API provides Resource for applications to participate in these two phases. The component that owns the resource can implement beforeCheckpoint to prepare and afterRestore to reopen. Closing and reopening must be performed according to the guidelines of the CRaC runtime and the libraries in use; some libraries already have their own CRaC integration.

## 3. Closing and Reopening InputStream

### InputStream Has No General Position API

InputStream provides byte-reading operations, but has no general method to query the current position or reset to an arbitrary position. This means an application cannot simply close an arbitrary InputStream, reopen it, and by default resume at the exact byte being read.

For files, the application can choose one of the following approaches:

- Re-read from the beginning if the data is small or can be safely reprocessed.
- Track the number of logical bytes consumed and reopen the file, then skip the exact number of bytes needed, if the file is stable and the source supports that approach.
- Use FileChannel to explicitly manage the read position.
- Use a record format with offsets or business checkpoints to resume at record boundaries.

Do not use InputStream.available() to determine the read position. available() only estimates the number of bytes that can be read without blocking; it does not return the total file size or the current offset.

### Mark and Reset Are Not a Durable Checkpoint Mechanism

Some InputStreams support mark/reset. mark() marks a position that can be returned to within the limit specified by the stream; reset() returns to that mark if the stream still supports it and the state has not been lost.

Do not treat mark/reset as a way to save the position for recovery after closing and reopening a stream:

- Mark usually only has meaning within the same stream instance.
- After close, the old instance can no longer be used to continue reading.
- The stream may not support mark.
- With BufferedInputStream, the read-ahead limit and buffer state affect reset.
- With sockets or remote streams, the peer may have changed state or may not allow replaying data.

If it is necessary to resume after restore, save the offset or logical checkpoint in an appropriate place and verify that the data source still corresponds to that offset.

### BufferedInputStream and Logical Position

BufferedInputStream may read ahead a region of data from the underlying stream and hold it in a buffer. Therefore, the physical position of the file descriptor may have advanced further than the position the application has actually consumed.

For example, the application has only processed 100 bytes, but BufferedInputStream may have already read ahead 8 KB from the file. If you take the position of the underlying file channel and reopen from that position, the application may skip the bytes still sitting in the buffer that have not been processed.

To resume accurately, it is necessary to save the logical position that the application has processed, usually the number of bytes consumed or the offset of the last completed record. Do not use the read-ahead position of the buffering layer as the business position.

### Example: Reopening File Input at a Processed Offset

The example below illustrates a text/binary file that can be re-read from a byte offset recorded by the application. The management class saves the logical offset and creates a new stream after restore.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResumableFileInput {
    private final Path path;
    private InputStream input;
    private long nextOffset;

    public ResumableFileInput(Path path) throws IOException {
        this.path = path;
        this.nextOffset = 0;
        openAtSavedOffset();
    }

    public synchronized int read() throws IOException {
        int value = input.read();
        if (value >= 0) {
            nextOffset++;
        }
        return value;
    }

    public synchronized void closeForCheckpoint() throws IOException {
        if (input != null) {
            input.close();
            input = null;
        }
    }

    public synchronized void reopenAfterRestore() throws IOException {
        openAtSavedOffset();
    }

    private void openAtSavedOffset() throws IOException {
        InputStream reopened = Files.newInputStream(path);
        try {
            long skipped = 0;
            while (skipped < nextOffset) {
                long count = reopened.skip(nextOffset - skipped);
                if (count == 0) {
                    if (reopened.read() < 0) {
                        throw new IOException(
                                "File ended before the saved offset");
                    }
                    count = 1;
                }
                skipped += count;
            }
            input = reopened;
        } catch (IOException | RuntimeException error) {
            reopened.close();
            throw error;
        }
    }
}
~~~

This is an illustrative example for a file source that can be reopened and is not unexpectedly modified. In a real application:

- nextOffset must represent the byte that business logic has successfully processed, not the byte that the buffer has read ahead.
- Ensure the file still has the same content or the same version. If the file is replaced or modified during checkpoint, the old offset may point to different data.
- If processing by line or record, save the offset at completed record boundaries to avoid missing or duplicating part of a record.
- For large files, skipping from the beginning to the offset can be time-consuming. FileChannel allows setting the position directly.

## 4. Closing and Reopening OutputStream

### Flush Before Close

OutputStream may be wrapped by BufferedOutputStream or another buffering class. Data written by the application may still remain in the Java buffer without having been transferred to the underlying stream.

Before checkpoint:

- Stop new writing threads.
- Wait for current write operations to complete.
- Call flush() to push data in the buffer down to the underlying stream.
- If it is necessary to ensure file data is synchronized to the storage device, use an appropriate mechanism such as FileChannel.force or the corresponding system API.
- Close the stream to release the underlying resources.

flush() does not mean all data has been durably written to the storage device. It usually only pushes data from the Java buffer to the next layer. Final durability also depends on the operating system, filesystem, and device.

### Choosing the Right Reopen Mode

When creating a new OutputStream, the file open mode determines whether old data is overwritten.

| Open method | Behavior | Use case |
|---|---|---|
| Files.newOutputStream(path) with defaults | Creates a new file or truncates an existing file | Rewriting the entire file from the beginning when intended |
| Files.newOutputStream(path, CREATE, WRITE, APPEND) | Appends to the end of the file | Logs or append-only data |
| FileOutputStream(path, true) | Opens in append mode | Appending to a file |
| FileChannel with WRITE and CREATE | Opens for writing, does not automatically truncate just by opening | Resuming writes at a position managed by the application |

A common mistake is reopening an output file with the default mode after restore. If the file already exists, this operation can truncate the pre-checkpoint content. Explicitly choose CREATE, WRITE, APPEND, or TRUNCATE_EXISTING according to the application's goal.

### OutputStream Does Not Provide a General Write Position

OutputStream has no position API. For append-only files, reopening in append mode allows writing to the end of the file without needing to know the current offset. For files that need to be written at a specific position, FileChannel is more suitable because it provides position().

If the application writes records to a file, define record boundaries and how to handle cases where a checkpoint occurs after part of a record has been written. You can use record framing, checksums, commit markers, or writing to a temporary file followed by an atomic move to reduce the risk of incomplete data. Resending records after restore requires idempotency or a duplicate detection mechanism.

### Example: Reopening OutputStream in Append Mode

~~~java
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class AppendFileOutput {
    private final Path path;
    private OutputStream output;

    public AppendFileOutput(Path path) throws IOException {
        this.path = path;
        open();
    }

    public synchronized void writeRecord(byte[] record)
            throws IOException {
        output.write(record);
        output.write('\n');
    }

    public synchronized void beforeCheckpoint() throws IOException {
        if (output != null) {
            output.flush();
            output.close();
            output = null;
        }
    }

    public synchronized void afterRestore() throws IOException {
        open();
    }

    private void open() throws IOException {
        OutputStream file = Files.newOutputStream(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
        output = new BufferedOutputStream(file);
    }
}
~~~

APPEND mode is suitable for the append-writing example. It does not solve the issue where a record may only be partially written before the process checkpoints or encounters an error. The application needs a record format capable of detecting incomplete writes and rules for handling resends.

Do not close an OutputStream while another thread is writing. The synchronized methods in the example only protect calls going through the same instance; the application still needs to coordinate threads and stop accepting new work before the callback closes the stream.

## 5. Closing and Reopening FileChannel

### FileChannel Has an Explicit Read/Write Position

FileChannel provides read and write operations on files and supports position():

- position() returns the current position of the channel.
- position(long) sets the current position.
- size() returns the file size.
- truncate(long) truncates the file to the specified size.
- force(boolean) requests synchronizing the file's updates to the storage device according to the system's guarantees.
- close() closes the channel and releases associated resources.

After close(), the channel cannot be used to continue reading or writing. After restore, the application needs to open a new FileChannel and then reset the position if it wants to continue from the saved offset.

### Saving the Position and Reopening the Channel

A typical process:

1. Stop ongoing read or write operations.
2. Save channel.position() into the Resource's state.
3. If data was written, call force(true) when data durability is required.
4. Close the channel.
5. After restore, open a new channel with the appropriate StandardOpenOptions.
6. Set the new channel's position to the saved offset.

Do not use TRUNCATE_EXISTING if the goal is to continue the old file. Only use this option when you want to erase the old content and write from the beginning.

### Example: Resource Managing FileChannel

The following example manages a read/write channel. The channel is closed before checkpoint; after restore, a new channel is opened and reset to the saved position.

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointFileChannel implements Resource {
    private final Path path;
    private FileChannel channel;
    private long savedPosition;

    public CheckpointFileChannel(Path path) throws IOException {
        this.path = path;
        this.savedPosition = 0;
        open();
        Core.getGlobalContext().register(this);
    }

    public synchronized int read(ByteBuffer destination)
            throws IOException {
        return channel.read(destination);
    }

    public synchronized int write(ByteBuffer source)
            throws IOException {
        return channel.write(source);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (channel != null && channel.isOpen()) {
            savedPosition = channel.position();
            channel.force(true);
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        open();
        channel.position(savedPosition);
    }

    private void open() throws IOException {
        channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE);
    }
}
~~~

In the example:

- Resource registers the instance owning the channel with the global context.
- beforeCheckpoint saves the current position, requests synchronization of file data, and then closes the channel.
- afterRestore opens a new channel and restores the position.
- CREATE, READ, and WRITE allow creating the file if it does not exist and opening an existing file for reading and writing. Without TRUNCATE_EXISTING, old content is not deleted simply by reopening.

force(true) is used here to illustrate requesting synchronization of file content and metadata. Applications should only pay this synchronization cost when data durability is required; force can impact performance and remains subject to filesystem, device, and platform limitations.

The example assumes only one thread or one coordinator uses the channel at a time. If multiple threads read/write concurrently, they must be stopped and drained before the callback; simply having synchronized on the wrapper's methods does not protect channel references shared elsewhere.

## 6. FileChannel Position Is Not Always the Business Position

FileChannel.position() is useful when the application reads or writes directly through the channel. However, this position may not represent business progress if:

- A buffering layer has read data ahead, but the application has not processed it yet.
- The application writes data to its own buffer before sending it down to the channel.
- A record is written in multiple parts and a checkpoint occurs midway.
- Multiple threads operate on the channel concurrently.
- Another process also modifies the file during the checkpoint period.

For example, the channel has read up to byte 4096, but the parser has only finished processing a record ending at byte 3000. If restored at position 4096, the data from byte 3000 to 4095 may be skipped. It is necessary to save the offset of the successfully processed record, or ensure the buffer is completely consumed before saving the position.

Similarly for writing data: position is the I/O position, not proof that the entire record has been committed from a business standpoint. If a record can be partially written, a format is needed that allows detecting and recovering the incomplete part.

## 7. File Locks and Memory Mapping

### FileLock

FileChannel can create a FileLock to lock a region of a file. A file lock is tied to the channel and operating system resources. When the channel closes, the associated lock is released. Do not keep a FileLock object in the heap and assume the lock is still valid after restore.

If exclusive operations need to continue:

- Close the channel and release the lock before checkpoint according to the application's rules.
- After restore, open a new channel.
- Request the lock again.
- Check whether acquiring the lock succeeded before modifying the file.

Another process may have acquired the lock while the application was paused. Restoring the old Java object does not restore lock ownership at the operating system level.

### MappedByteBuffer

FileChannel.map() creates a file-mapped memory region via MappedByteBuffer. Mapped regions have a lifecycle and behavior dependent on the JVM, operating system, and checkpoint implementation. Closing FileChannel should not be treated as proof that all mapped regions have been released or can be safely recreated.

If an application uses memory-mapped files, check the support of the specific CRaC runtime and deployment platform. When there are no clear guarantees, design to finish operations with the mapped region before checkpoint and create a new mapping after restore using a new channel. Also ensure no thread continues accessing the old ByteBuffer.

## 8. Cases Where Simply Closing and Reopening Is Not Enough

### Streams from Sockets or Remote Services

Closing a network stream usually closes the current connection. Opening a new socket does not mean the old protocol session is restored. The application may need to:

- Reconnect to the current host.
- Re-perform the TLS handshake and authentication.
- Re-register subscriptions.
- Read the acknowledged offset or sequence number.
- Use acknowledgement, idempotency, or deduplication to handle messages that may be resent.

Do not save a socket InputStream or OutputStream and reuse it after restore without verifying the connection.

### Streams from One-Time Resources

Some sources only allow reading once or do not support seeking, such as pipes, live data streams, or a request's response body. After closing, there is no way to reopen at the exact next byte unless the source provides a resume mechanism.

In that case, the application must design checkpointing at the protocol or business layer. For example, saving an acknowledged message offset, a recreatable cursor, or a resume token provided by the service.

### ByteArrayInputStream and Purely In-Heap Streams

ByteArrayInputStream reads from a byte array in the heap and does not hold a file descriptor. If both the byte array and the read state reside in the heap, they are usually restored along with the process. There is no need to close/reopen just because it is an InputStream.

Similarly, distinguish between the wrapper and the underlying source. A BufferedInputStream wrapping a FileInputStream still depends on the file; a wrapper around a ByteArrayInputStream has a different lifecycle. Identify the actual owned resource before registering a Resource.

## 9. Integrating the I/O Lifecycle into CRaC Resource

A component that owns a stream or channel can implement org.crac.Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class MyIoResource implements Resource {
    public MyIoResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Stop I/O, flush, and close handles owned by the component.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Reopen handles and restore necessary offsets/state.
    }
}
~~~

The code snippet only illustrates the callback structure. Actual logic must handle synchronization with threads using I/O, reopen failures, and uninitialized resource states. Do not register a redundant Resource if a framework or library has already registered a Resource to manage the same stream/channel.

When an application has multiple files, there can be one Resource per component that owns a file or one Resource managing a set of resources with the same lifecycle. Keep ownership boundaries clear to avoid two callbacks closing the same handle.

## 10. Common Mistakes

**Checking only that the stream is non-null and continuing to read.**

A remaining reference does not prove the underlying handle is valid. After restore, reopen or verify the resource according to the supported mechanism.

**Using available() as an offset.**

available() does not return the current position. Track the logical offset or use FileChannel when positional access is needed.

**Using mark/reset to resume after reopening.**

Mark is tied to the old stream instance and is not a checkpoint that can be recovered after close. Save the offset or business state independently.

**Forgetting to flush before closing OutputStream.**

Data remaining in the buffer may not have been transferred to the underlying stream. Stop writing, flush, and close in the proper order.

**Reopening an output file with the default mode.**

The default mode may truncate the existing file. Choose APPEND or FileChannel with the appropriate position.

**Restoring position while ignoring buffers.**

The physical position of the channel may differ from the logical position the application has processed. Save the offset at completed data boundaries.

**Keeping an old FileLock across restore.**

Closing the channel releases the lock. Open a new channel and request the lock again before modifying the file.

**Closing a handle while another thread is still performing I/O.**

Ongoing operations may fail or write incomplete data. Stop accepting new work and drain current operations before the callback.

## 11. Design and Testing Checklist

When introducing I/O into a CRaC-enabled application, determine:

- Is the data source a file, memory, socket, or remote service?
- Which stream/channel actually owns the underlying resource?
- Who is responsible for stopping threads and closing handles?
- Are there read-ahead buffers or unflushed write buffers?
- Is the offset to be saved a physical position or business progress?
- After restore, can the file be modified by another process?
- Does reopening the file require READ, WRITE, CREATE, APPEND, or truncate?
- Is there a FileLock or mapping that needs to be recreated?
- If reopening fails, is the application allowed to receive traffic?
- If part of a record was written or processed before checkpoint, how are duplicates detected and handled?

Test on the exact JDK/CRaC runtime, operating system, and filesystem intended for deployment. Include checkpointing while a file is being read, when the output buffer has data, after the file or external service changes, and when the reopen operation fails. Test across multiple cycles to detect leaked handles, duplicate open streams, or incorrect offsets.

## 12. Conclusion

Closing and reopening InputStream, OutputStream, and FileChannel is part of managing the I/O lifecycle when an application uses CRaC. Before checkpoint, the application needs to stop ongoing operations, flush write data, save necessary progress, and close the appropriate handles. After restore, the application creates a new stream or channel, chooses the right open mode, and restores the offset based on business state.

InputStream and OutputStream do not provide a general position API; FileChannel has an explicit position, but the I/O position can still differ from business progress when buffers or multiple threads are involved. Safe design requires understanding the data source, handle ownership, file open modes, buffers, and the resume capabilities of external systems.
