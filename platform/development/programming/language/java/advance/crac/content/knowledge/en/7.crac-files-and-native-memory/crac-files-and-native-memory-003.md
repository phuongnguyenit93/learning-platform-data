# Write Buffers, Flush Operations, and the Risk of Data Loss or Duplication

Java applications often do not write data directly to the destination at the moment `write()` is called. Data can pass through multiple buffering layers: buffers inside Java objects, library buffers, operating system buffers, storage device buffers, or socket send queues. Buffering helps reduce the number of I/O operations and increase throughput, but when using CRaC, it is necessary to answer accurately: at the time of checkpoint, which layer is the data in and where has it been acknowledged?

If a checkpoint is created while unflushed data still remains, that data may be included in the saved memory state. After restore, the application can continue writing the pending data. However, if the write operation has already reached the external system while the process state has not yet recorded the operation as completed, restore may re-execute that operation and create duplicate data. Conversely, if the application marks data as processed before the data is actually durably written, restore may skip the unsaved data and cause data loss.

Therefore, it is necessary to understand the exact meaning of `flush()`, distinguish flushing from durability, identify the buffer owner, and choose a checkpoint point where the in-memory state is consistent with the state of the external system.

## 1. Why do applications use write buffers?

Writing each byte or small record directly to the destination often generates many I/O calls. Each call incurs overhead for switching between user space and kernel, synchronization, syscalls, or network communication. Buffering batches multiple small writes into a larger write.

For example, an application writes 100,000 log records. If each record is written individually, the application may perform very many small I/O operations. If records are accumulated in a buffer and written in batches, the number of I/O calls can be reduced significantly.

Common buffering layers:

- `BufferedOutputStream` holds bytes in a Java buffer before writing to the underlying stream.
- `BufferedWriter` holds characters in a buffer, then passes them through an encoder and the underlying stream.
- `BufferedReader` mainly buffers read data; it is not a write buffer, but it is still I/O state to consider at checkpoint.
- `ByteBuffer` can hold data in the heap or in direct/native memory when working with NIO.
- Logging libraries, database drivers, HTTP clients, and message producers may have their own buffers or queues.
- The operating system has a page cache and I/O queues before data reaches the storage device.
- Sockets have a kernel-side send buffer; the receiving application protocol may also buffer further.

A successful `write()` call therefore does not necessarily mean the data has reached its final destination. It may only mean the data has been copied into the buffer of the current layer.

## 2. The data path during writes

For a file, the general path may look like this:

```text
Business code
    |
    | write(record)
    v
Java buffer (BufferedWriter / BufferedOutputStream)
    |
    | flush()
    v
Stream / encoder / FileChannel
    |
    | write to the operating system
    v
Operating system page cache
    |
    | force / sync and filesystem mechanisms
    v
Storage device
```

For the network, the path takes a different form:

```text
Business code
    |
    v
Client / producer buffer
    |
    | flush or send request
    v
Operating system socket send buffer
    |
    | TCP transmits data
    v
Destination-side socket receive buffer
    |
    v
Receiving application processes and acknowledges
```

The two diagrams show that there are multiple different boundaries. Data pushed out of a Java buffer is not necessarily durably written to disk; data placed into a socket is not necessarily processed or committed by the receiving application.

## 3. How do write(), flush(), and close() differ?

### 3.1. write()

`write()` puts data into a stream or channel. With a buffered stream, data may only be copied into an in-memory buffer. With some APIs, the call may write directly to a lower layer, but subsequent buffering layers still remain.

One should not infer that `write()` returning successfully means the data is durable. Read the contract of the specific API and determine at which layer it acknowledges.

### 3.2. flush()

`flush()` asks the buffering layer to push pending data down to the underlying stream or destination according to the API's contract. With `BufferedOutputStream`, this operation writes the bytes remaining in the buffer to the underlying stream and then calls `flush()` on that stream. With `BufferedWriter`, this operation pushes buffered characters through the underlying writer.

Importantly, `flush()` typically only guarantees that data has passed through the buffers belonging to the calling Java layer and been handed off to the lower layer. It does not automatically guarantee that data has been durably written to the storage device, nor does it guarantee that the remote application has processed the data.

### 3.3. close()

`close()` typically finishes using the stream, flushes any remaining data according to the stream's contract, and then releases resources. After closing, the stream usually cannot be written to anymore.

Closing a stream can be an appropriate action before a checkpoint if the resource needs to be reopened after restore. However, closing a writer does not replace checking durability. If file data needs to be durable, flush and then use the appropriate force/sync API before closing.

## 4. Flush does not mean durability

This is the most important distinction when handling file data.

With `BufferedOutputStream` or `BufferedWriter`, calling `flush()` pushes data remaining in the Java buffer down to the underlying stream. If the destination is a file, the underlying stream usually hands the data to the operating system. The operating system may keep the data in the page cache before writing it to the device.

To request that file data be pushed down to the storage device, it may be necessary to call `FileChannel.force(...)` or `FileDescriptor.sync()` after flushing. These APIs request the operating system to synchronize modified data according to their contracts. The final level of guarantee still depends on the filesystem, device, and storage configuration.

| Operation | Typical meaning | What should not be inferred |
|---|---|---|
| `write()` | Puts data into a stream or channel | Data has left all buffers |
| `flush()` | Pushes pending data in the current layer's buffer to the lower layer | Data is durable on the device or has been processed by the remote application |
| `FileChannel.force(false)` | Requests synchronizing modified file content with the storage device per the API contract | All related metadata has been synchronized |
| `FileChannel.force(true)` | Requests synchronizing modified file content and metadata | Can replace all application commit protocols |
| `FileDescriptor.sync()` | Requests synchronizing modified file data and attributes to the device | Business transaction or data in another system has committed |
| Remote application ACK | Receiving side acknowledges according to the application protocol | ACK always means data is durably stored; must read the receiver's contract |

Example of writing a file using `BufferedOutputStream`:

```java
import java.io.BufferedOutputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

Path path = Path.of("events.log");

try (FileOutputStream file = new FileOutputStream(path.toFile(), true);
     BufferedOutputStream out = new BufferedOutputStream(file)) {

    byte[] record = "order-created".getBytes(StandardCharsets.UTF_8);
    out.write(record);
    out.write('\n');

    // Push data out of the BufferedOutputStream buffer.
    out.flush();

    // Request synchronization of modified file data/attributes.
    file.getFD().sync();
}
```

In the example, `flush()` transfers buffered bytes down to `FileOutputStream`. `sync()` requests file synchronization. If `sync()` is omitted, data may still remain in the operating system's page cache after `flush()` returns. `sync()` has I/O cost and can reduce throughput, so the application needs to choose appropriate durability boundaries rather than calling it after every byte.

With NIO, `FileChannel.force(true)` can be used after writing. If a writer is wrapped over a channel, ensure the writer is flushed before calling `force()` so that bytes remaining in the character or byte buffer are transferred down to the channel.

## 5. What does flush mean over the network?

With a socket, `flush()` usually pushes data out of the Java stream's buffer down to the socket or underlying network layer. Data may still sit in the kernel's send buffer, be in transit over TCP, or have arrived at the destination machine without yet being read by the receiving application.

TCP acknowledgement confirms data receipt at the TCP layer according to the protocol mechanism. It does not necessarily confirm that the receiving application has processed the record, written to the database, or committed the transaction.

If the requirement is “the message has been received and processed by the system”, the application needs an ACK at the business protocol layer. The ACK should carry a clear meaning, such as that the message ID has been durably stored or the transaction has committed. Only after receiving an ACK matching the contract should the producer mark the message as completed.

With a message broker or asynchronous client, the `flush()` method may have different meanings across libraries. Some clients use it to wait for pending send requests to complete; some clients only push internal buffers out to the network. Check the documentation of the exact client and broker configuration. Do not apply the meaning of `OutputStream.flush()` to every method with the same name.

## 6. How do write buffers affect checkpointing?

CRaC saves process state at a checkpoint. Buffers located in the Java heap can be part of the saved memory state. After restore, the application can continue with data still pending in the buffer, depending on the resource and how the runtime supports it.

This can be useful when the buffer contains valid data that does not need to be sent immediately. However, it also creates risk if the process preparing for checkpoint has already performed part of an external side effect without updating the corresponding in-memory state.

For example, an application has a `BufferedWriter` and a `lastWrittenSequence` variable:

```text
Java buffer:       [record 101, record 102]
External file:     already has up to record 100
lastWrittenSequence = 100
```

If the checkpoint saves the pending buffer, restore can continue writing records 101 and 102. This may be the right behavior if the file is still at the right position and no other writes have occurred. However, if part of the data has already been written to the file while the buffer state or write position in the process does not accurately reflect the external result, restore may write duplicates or create an inconsistent file.

For many types of resources, external state does not reside entirely in the heap. File descriptors, sockets, page cache, and native buffers have their own rules. Do not assume that a heap snapshot means all kernel or device buffers are also snapshotted in the same way. Follow the guidance of the CRaC JDK, libraries, and platform being used.

## 7. Two opposite failures: data loss and data duplication

### 7.1. Data loss

Data loss can occur when the application records progress in memory before the data is actually delivered to or durably stored at the destination.

Example:

1. The application receives record 205.
2. The application increments `lastProcessedSequence` to 205.
3. The data is still in the Java buffer, not yet flushed.
4. A checkpoint is created and saves `lastProcessedSequence = 205`.
5. After restore, the application continues from record 206.
6. Record 205 was never written to the destination and is not resent.

The progress state moved ahead of the actual data. This is the cause of data loss.

### 7.2. Data duplication

Data duplication occurs when an external side effect has succeeded, but the checkpoint saves the process state before that success is recorded.

Example:

1. The application sends record 205 to the destination system.
2. The destination system writes record 205 successfully.
3. The application has not yet updated `lastProcessedSequence` or saved the ACK to durable state.
4. A checkpoint is created with the old state.
5. After restore, the application resends record 205.
6. The destination system receives a duplicate operation if there is no deduplication mechanism.

This is a common problem when a process must coordinate in-memory state with external side effects. A checkpoint does not automatically create an atomic transaction between the Java heap and a database, file, or broker.

### 7.3. Comparison table

| Sequence | Checkpointed state | Possible outcome |
|---|---|---|
| Marked complete before data is saved | Progress incremented, data not yet written | Data loss |
| External data written, progress not yet updated | Destination already has data, process thinks it is incomplete | Data duplication when restore resends |
| Buffer still has data and is kept in checkpoint | Pending data is snapshotted with the process | Can continue writing; must ensure destination and write position are consistent |
| Buffer flushed and state confirmed before checkpoint | Buffer empty, progress reflects confirmed result | Easiest to recover if resources are reopened properly |

## 8. Designing a consistency point before checkpoint

Before checkpointing, the application should reach a state where pending data, processing progress, and external side effects can be reconciled.

A quiesce procedure for a write flow may include:

1. Stop accepting new work from HTTP, queues, or schedulers.
2. Wait for in-flight write operations to complete or move to a retryable state.
3. Block new producers from putting data into the buffer.
4. Flush buffers according to the stream/client contract.
5. Wait for application-level ACKs or commit results if the destination supports them.
6. Persist processing progress according to the same consistency rules.
7. Call `force()` or `sync()` if file durability requirements demand it.
8. Close or prepare to recreate I/O resources according to CRaC guidelines.
9. Allow checkpointing only after all owners report ready.

Not every application needs to force files or wait for broker ACKs at every checkpoint. The procedure must be based on data requirements: logs may tolerate losing a small amount of data; financial ledgers or critical events may require stronger durability. What matters is clearly defining the guarantee level and placing the checkpoint at an appropriate boundary.

If a flush or commit operation fails, the checkpoint preparation callback must report an error so the checkpoint process does not proceed as if the data were safe. There must be logs and metrics for this error. Do not swallow exceptions and let the process checkpoint with an unclear state.

## 9. CRaC Resource managing buffers and streams

The CRaC API provides `org.crac.Resource` with two main callbacks:

- `beforeCheckpoint(...)`: prepares the resource before process state is saved. For write resources, the owner may stop new writes, flush, force/sync if needed, and close the stream.
- `afterRestore(...)`: recreates or verifies the resource after the process is restored. For files, the owner may reopen the file and restore the write position by design. For network, the owner typically creates a new connection.

The example below illustrates an owner managing an append file. For simplicity, the class assumes a coordinator has stopped producers and waited for write calls to finish before CRaC calls `beforeCheckpoint(...)`.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.locks.ReentrantLock;

public final class CheckpointAwareFileWriter implements Resource {
    private final Path path;
    private final ReentrantLock lock = new ReentrantLock();
    private FileChannel channel;
    private BufferedWriter writer;

    public CheckpointAwareFileWriter(Path path) throws IOException {
        this.path = path;
        open();
        Core.getGlobalContext().register(this);
    }

    private void open() throws IOException {
        channel = FileChannel.open(path,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
        writer = new BufferedWriter(new OutputStreamWriter(
                Channels.newOutputStream(channel), StandardCharsets.UTF_8));
    }

    public void writeRecord(String record) throws IOException {
        lock.lock();
        try {
            writer.write(record);
            writer.newLine();
        } finally {
            lock.unlock();
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        lock.lock();
        try {
            if (writer != null) {
                writer.flush();
                channel.force(true);
                writer.close();
                writer = null;
                channel = null;
            }
        } finally {
            lock.unlock();
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        lock.lock();
        try {
            open();
        } finally {
            lock.unlock();
        }
    }
}
```

In the example, `writer.flush()` pushes data out of the character buffer down to the channel; `channel.force(true)` requests synchronization of modified file content and metadata; then the writer is closed. Upon restore, the file is reopened in append mode. Reopening avoids depending on the old stream state.

This is a skeleton example, not a complete file-writing class for every application. In a real system, it is necessary to add:

- A true quiesce mechanism to prevent producers from calling `writeRecord()` after checkpoint preparation begins. The lock in the example only serializes in-flight calls; it does not by itself prevent new calls after the callback returns.
- Exception handling when flush, force, close, or open fails. If flush/force errors, the data must not be marked as durable.
- A policy for persisting the written position or sequence to detect duplicate records and resume at the right point.
- Verification of paths, mounts, and file permissions after restore.
- Rules if multiple restored processes write to files concurrently: use per-instance files or a well-designed synchronization/append mechanism. Do not let multiple replicas share writing to the same file just because they started from the same checkpoint.
- Handling if the checkpoint fails after the callback has already flushed and closed the writer. The application needs a procedure to resume serving or reinitialize resources according to the lifecycle supported by the runtime.

If the file contains important business records, use a record format with a sequence or unique ID so integrity can be checked and duplicate operations eliminated on recovery.

## 10. Preventing duplicate writes with idempotency and sequences

It is not always possible to create an atomic transaction between process state and external systems. A practical approach is to design write operations so they can be re-executed without creating additional side effects.

### 10.1. Idempotency key

Each operation has a stable ID. When the system receives the same ID again, it recognizes that the operation has already been processed and does not apply the side effect a second time.

For example, an event has a stable `eventId`. The database stores the processed event ID in the same transaction as the business change. If the restored process resends the event, the database detects that the ID already exists and returns the appropriate result.

Idempotency must be enforced on the destination system side or within a consistent transaction. Simply storing the ID in a heap variable and checkpointing is not enough because that variable can diverge from the external outcome.

### 10.2. Sequence number and offset

For ordered record streams, use a durable sequence or offset. The application only marks an offset complete after the destination has confirmed the operation according to the contract. Upon restore, read the committed offset from the durable source and continue according to the system's rules.

With multiple consumers, partition or lease assignment must be managed by the broker or coordinator. Do not copy an offset in the heap and let multiple processes resume from the same position without a work-partitioning mechanism.

### 10.3. Transactional outbox or appropriate transactions

When updating a database and emitting an event need to be consistent, a transactional outbox can be used: write the business change and the outbox record in the same database transaction; a publisher reads the outbox and sends the event with a stable ID. The publisher can resend when uncertain whether an ACK arrived, while the consumer processes idempotently.

This pattern does not eliminate all possibilities of network duplication, but it helps control duplication using IDs and durable state. Similarly, if the destination system supports transactions or exactly-once semantics, understand the scope and conditions of that mechanism clearly before relying on it.

## 11. Buffers across different resource types

### 11.1. Files and writers

For files, distinguish between Java buffers, the page cache, and the storage device. Before checkpoint, the writer needs to be quiesced; buffers flushed; forced/synced if durability is required; and then closed and reopened after restore when appropriate. If a file is used by multiple processes, there must be append rules, locking, or separate files.

### 11.2. Logging frameworks

Logging frameworks may have async appenders and their own queues. Calling `flush()` on a stream does not necessarily drain the logging framework's queue. Use the shutdown/flush API of the exact appender or logger, wait for log-writing workers to finish, and verify write errors. For logs that can tolerate some data loss, the durability level may differ from business data.

### 11.3. Message producers

Asynchronous producers often buffer messages before sending. `flush()` may wait for pending sends to complete, but the exact meaning depends on the client. Wait for send results or ACKs according to the broker's contract before checkpointing, and persist offsets/progress in a way that avoids loss or duplicate sends. After restore, recreate the producer if the old client or socket is not supported.

### 11.4. HTTP clients and sockets

HTTP clients may buffer request bodies, batch requests, or send asynchronously. Calling `flush()` alone does not prove the server has committed. For requests requiring confirmation, wait for the application-layer response/ACK. Before checkpoint, complete or cancel in-flight requests according to a clear policy; after restore, create a new client or connection if needed.

### 11.5. Direct buffers and native memory

`ByteBuffer.allocateDirect()` uses direct memory instead of a regular heap byte array. Native libraries may maintain their own buffers and pointers. These memory regions must be reviewed according to the support of the JVM, CRaC, and the native library. Do not assume all native state has the same lifecycle as an ordinary Java object.

With `MappedByteBuffer`, the `force()` method requests writing changes in the mapped memory region to the storage device per the API contract. The application needs to verify the mapping, file, and position after restore; do not rely on an old mapping always being valid in a new environment.

## 12. Flush policy: when and at what level?

Flushing frequently reduces the amount of data that could be lost if the process fails, but it can significantly reduce throughput. Flushing too infrequently increases batch write performance but lengthens the window during which data remains in buffers.

Choose a policy based on data type:

| Data type | Commonly considered policy | Reason |
|---|---|---|
| Regular diagnostic logs | Batch or time-based buffering; drain before checkpoint | Balances throughput and the possibility of losing a small amount of logs |
| Critical audit logs | Flush and durability at business boundaries | Needs to reduce the risk of losing confirmed events |
| Financial transactions | Durable transactions and commit confirmation | Cannot rely solely on in-heap buffers |
| Regenerable export files | Batch flush, checkpoint at record boundaries | Can be regenerated on failure if the original data source exists |
| Message producers | Wait for ACK or completion per client contract | Avoids marking complete when the broker has not confirmed |
| HTTP requests with side effects | Wait for business response and use idempotency keys | Avoids resending operations with unclear outcomes |

An application may flush by byte count, record count, time, or transaction boundary. However, when preparing for checkpoint, the policy needs an explicit drain/flush operation to ensure data is no longer in an indeterminate state.

## 13. Handling errors during flush and checkpoint

Flush or force can fail due to disk full, I/O error, closed file descriptor, changed permissions, or storage device failure. Over the network, send or ACK can time out while the receiving side has already processed part or all of the data.

When the outcome is unclear, do not automatically conclude that the operation failed completely. For example, a timeout when sending a request may happen after the server has committed but the response was lost. Retrying in that case can create duplicates if there is no idempotency.

A handling policy should distinguish:

- **Definite failure before sending:** Can retry because the destination has not received the data, if the API guarantees that.
- **Failure during sending or waiting for ACK:** Outcome may be indeterminate; look up by operation ID or perform an idempotent retry.
- **Destination confirmed, but progress not yet recorded:** Risk of resending after restore; deduplication is needed.
- **Progress recorded but data not yet durable:** Risk of data loss; only update progress after the appropriate confirmation point.
- **Flush/force failed before checkpoint:** Do not mark the resource as ready; block the checkpoint or bring the application to a recoverable state.

Error logs should include resource ID, operation ID, sequence, write destination, and confirmation status. Avoid logging sensitive payloads just to debug I/O errors.

## 14. Buffer preparation procedure before checkpoint

A general procedure for an application with multiple write threads:

```text
Checkpoint preparation request
          |
          v
Stop accepting new work
          |
          v
Drain in-flight requests / messages / jobs
          |
          v
Block producers from writing more to buffers
          |
          v
Flush each buffer by owner
          |
          v
Wait for application-layer ACK / commit if needed
          |
          v
Force / sync files if durability is required
          |
          v
Close or re-prepare I/O resources
          |
          v
Confirm consistent state
          |
          v
Allow checkpoint
```

Upon restore:

```text
Restore process
       |
       v
Recreate file handles / clients / connections
       |
       v
Re-read configuration and durable progress
       |
       v
Verify buffers are empty or in valid buffer state
       |
       v
Start producers / consumers / workers
       |
       v
Readiness succeeds
```

Not every resource necessarily has to be closed. Some libraries have CRaC integration and their own procedures; follow their contracts strictly. The key point is that the owner must confirm that buffers and side effects are in a recoverable state.

## 15. Testing for data loss and duplication

A checkpoint/restore test should verify both the written output and the progress state. Merely confirming that the process can be restored is not enough.

A simple test scenario:

1. Create a record generator with incrementing IDs, for example 1 to 10,000.
2. Write records to the destination and persist confirmed IDs using a durable mechanism.
3. Ask the application to quiesce and create a checkpoint at a defined boundary.
4. Restore the process from the image.
5. Continue sending the remaining records.
6. Read the data at the destination and check for missing IDs, duplicate IDs, ordering, and checksums.
7. Repeat with checkpoints occurring while buffers contain data, while waiting for ACKs, and after the destination has written but before the process updates progress.

Failure cases to test:

- Inject an I/O error during flush or force.
- Disrupt the connection after the server receives the request but before the client receives the ACK.
- Make the database or broker temporarily unavailable after restore.
- Stop a process in the middle of processing a batch.
- Restore multiple instances from the same image if the system has a multi-restore model.
- Have two instances receive the same record to test idempotency and the work-partitioning mechanism.

Metrics to collect include the number of records generated, number of records confirmed, actual number of records at the destination, number of duplicate IDs, number of missing IDs, retry count, flush/force time, and resource recovery time.

## 16. Common mistakes

**Assuming `flush()` means writing to disk.** Flushing a Java stream usually pushes data to the underlying layer; for files, the page cache and force/sync APIs must be considered if durability is required.

**Assuming flushing a socket means the server has processed it.** Data may only have been placed into the send buffer or TCP. Wait for an application-layer ACK if processing confirmation is required.

**Checkpointing while producers are still writing.** Buffers can change during checkpoint preparation and progress state is hard to keep consistent. Stop producers, drain, and coordinate owners.

**Marking progress before the destination confirms.** After restore, the application may skip unwritten data. Only update progress at a defined durable confirmation point.

**Resending without idempotency.** If the destination already processed the request but the ACK was lost, retrying can create duplicate side effects. Use stable operation IDs and deduplication.

**Assuming Java buffers are the entire I/O state.** Native buffers, kernel buffers, page cache, and external service states have their own lifecycles. Check all relevant layers.

**Swallowing errors in callbacks.** If flush or force fails but the callback still reports success, the checkpoint may contain an inconsistent state. Propagate errors and block the checkpoint according to policy.

**Calling flush after every write without considering performance.** This can reduce throughput. Choose flush boundaries based on data type and durability requirements.

**Sharing an append file across multiple restored processes.** Multiple processes may write duplicates or contend on offsets. Use separate files, inter-process locking, or a centralized writing system designed for concurrent writers.

## 17. Checklist for buffers and write operations when using CRaC

- [ ] Have buffers in Java, libraries, direct/native memory, and the operating system been listed?
- [ ] Has an owner been identified for each buffer, stream, channel, and producer?
- [ ] Is it known at which layer `write()` and `flush()` of the specific API confirm?
- [ ] Has `flush` been distinguished from `force`/`sync` and application ACKs?
- [ ] Are producers stopped from accepting new data before checkpoint?
- [ ] Are in-flight write operations drained or completed?
- [ ] Are buffers flushed by the right owner before checkpoint?
- [ ] Is critical data forced/synced or committed according to durability requirements?
- [ ] Is processing progress updated only after the appropriate confirmation point?
- [ ] Do write operations have IDs or sequences to detect duplicates?
- [ ] Are streams, channels, and clients recreated or verified after restore?
- [ ] Have I/O errors, ACK timeouts, data loss, and duplicate sends been tested?
- [ ] Does readiness wait for write resources and essential dependencies to recover?

## Conclusion

Write buffers help Java reduce I/O overhead but create multiple layers of state that must be coordinated at checkpoint. `write()` may only put data into a buffer; `flush()` pushes data down to the underlying layer; `force` or `sync` requests file synchronization; and only an application-layer ACK can confirm that the destination system has processed it according to its contract. These operations cannot substitute for one another.

To avoid data loss or duplication, identify the owner of each buffer, stop producers and drain work before checkpointing, flush and confirm as required, and persist progress at a consistent boundary. After restore, recreate appropriate resources, read durable progress, and use IDs, sequences, or idempotency to handle cases where external outcomes are unclear. When in-memory data and destination state are coordinated intentionally, CRaC can shorten startup time while preserving the correctness of write flows.
