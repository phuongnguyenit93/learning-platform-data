# File Locks and Files in Use

In Spring Batch, jobs often read input files, write output files, or move files across `incoming`, `processing`, `archive`, and `error` directories. When multiple jobs, multiple workers, or an external process access the same file concurrently, conflicts can arise: a file is still being written while the batch job already starts reading, two jobs process the same file, a writer cannot open output because another program holds the file, or a restarted job writes to a resource that was replaced.

A **file lock** is a coordination mechanism to determine which process is allowed to use a resource during a period of time. However, file locks only work when all parties obey the locking protocol; behavior also depends on the operating system and filesystem. Spring Batch does not automatically lock every file used by readers or writers. The application must design how files are claimed, locked, released, and recovered when a process dies.

A safe batch workflow typically has three parts: the producer publishes the file only after finishing writing; the consumer claims the file so only one execution processes it; the writer creates separate output and publishes once the result is complete. If the job runs across multiple nodes, an appropriate distributed synchronization mechanism must be used instead of relying only on in-JVM `synchronized`.

## Common File Contention Scenarios

Errors related to files being in use typically appear at these moments:

- The producer is still writing a CSV file while the job has already started reading.
- Two different `JobExecution` instances read and process the same input file simultaneously.
- Two steps or two jobs write to the same output path.
- A process holds an open file handle, causing Windows to reject deletion, renaming, or overwriting.
- A job restart needs to reopen a file, but the file has been moved, deleted, or replaced.
- One node holds a lock while another node does not know whether the owner has died.
- Files reside on NFS, SMB, or object storage with semantics different from a local filesystem.

For example, two jobs launched with different `JobParameters` create two valid `JobInstance` records, yet both receive the same `inputFile`. Batch metadata does not automatically prevent them from reading the same resource. If both write output to `orders-result.csv`, data may be interleaved, overwritten, or one job may fail with a file-in-use error.

## What is a File Lock?

A file lock is a synchronization mechanism attached to a file or a byte range of a file. A process requests a lock before performing an operation requiring exclusivity; another process following the same protocol is denied a conflicting lock until the lock is released.

In Java NIO, `FileChannel.lock()` requests a lock and can block until acquired; `tryLock()` attempts to acquire the lock immediately and returns `null` if the region is held by another process. A `FileLock` can be shared or exclusive:

- **Exclusive lock:** one party holds exclusive lock rights over the file region; typically used for write operations or exclusive processing claims.
- **Shared lock:** multiple parties can hold compatible read locks if the OS/filesystem supports it and no conflicting exclusive lock exists.

Do not assume shared locks are supported identically across all platforms. Some filesystems or operating systems may only support exclusive locks or treat shared locks differently.

### File locks can be advisory

On many systems, file locks are *advisory*: they only prevent other processes from acquiring a conflicting lock if those processes also request locks using the same mechanism. Another program can still open and write to the file without checking the lock. Therefore, a file lock is not an absolute barrier against every application.

On some platforms, locks have more mandatory-like semantics or directly affect file-open behavior, but you should not rely on that behavior to build cross-platform applications. Check the operating system, filesystem, mount options, and Java runtime of the deployment environment.

### A lock is not the same as an open file handle

A file can be open without holding a lock. Conversely, a lock can be held on a channel while another application still reads the file if it ignores locks or the platform permits it. Therefore, the "file is being used by another process" error and the "file is locked" state are related, though not always identical concepts.

## Java NIO FileLock

`FileChannel` provides OS-level locking APIs. The example below requests an exclusive lock on a dedicated lock file:

```java
Path lockPath = Path.of("/batch/locks/orders.lock");

try (FileChannel channel = FileChannel.open(
        lockPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {

    FileLock lock = channel.tryLock();
    if (lock == null) {
        throw new FileBusyException("Another process owns the lock");
    }

    try (lock) {
        processOrdersFile();
    }
}
```

This snippet illustrates opening a channel, attempting to acquire a lock, and holding the lock across the processing scope. `FileBusyException` and `processOrdersFile()` are application-defined components. In production code, also handle I/O errors, overlapping locks within the same JVM, and wait policies.

Another common style locks the entire file region:

```java
FileLock lock = channel.tryLock(0L, Long.MAX_VALUE, false);
```

The final argument `false` requests an exclusive lock. Not every filesystem supports every lock region mode identically; choose a scope and lock type compatible with the application protocol.

### tryLock and possible outcomes

| Outcome | Meaning | Suggested Handling |
| --- | --- | --- |
| Returns `FileLock` | Lock acquired | Execute work within the lock scope |
| Returns `null` | Conflicting lock is currently held | Wait with a bound, report file busy, or requeue |
| `OverlappingFileLockException` | Current JVM already holds an overlapping lock on that region | Check multiple threads in the same JVM claiming the file |
| `IOException` | Error opening channel/lock or filesystem error | Classify I/O, permission, and filesystem errors |

`FileLock` is bound to a `FileChannel`. Closing the channel releases the lock; `release()` can also be called explicitly. Using try-with-resources avoids holding locks when code throws an exception.

### Locks within the same JVM

Java manages file locks per JVM. Two threads in the same JVM requesting overlapping locks may encounter `OverlappingFileLockException` rather than waiting on each other like two separate processes. If the application must coordinate multiple threads in the same JVM, combine `ConcurrentHashMap`, `ReentrantLock`, or an internal synchronization mechanism with the file lock.

`synchronized` or `ReentrantLock` only coordinates threads within the same JVM. They do not prevent another process or another node from accessing the file. When multiple application instances exist, an inter-process or distributed mechanism is required.

## Lock files and data files

A common pattern creates a separate lock file alongside the data file:

```text
incoming/
  orders-2026-11-15.csv
  orders-2026-11-15.csv.lock
```

Consumers agree that processing `orders-2026-11-15.csv` requires acquiring an exclusive lock on the `.lock` file. A separate lock file avoids modifying the data file content just to coordinate access.

Two approaches are easily confused:

1. **Holding an OS lock on a lock file:** the lock file persists stably; the process holds a `FileLock` on the channel. When the process dies or the channel closes, the OS/JVM releases the lock.
2. **Using marker file existence as a lock:** the application creates `orders.lock` and treats file presence as ownership. If the process dies, the marker may remain even though nobody holds a lock.

These two approaches have different semantics. An existing marker file does not prove an OS lock is actively held.

### Do not arbitrarily delete an in-use lock file

With the OS lock pattern, keep a stable lock file and only release the lock; do not delete the lock file after every run. If process A holds a lock on the file, process B has opened the same file and is waiting, then A deletes the file and process C recreates a file with the same name, B and C may operate on two different file objects. On inode-based filesystems, this can make both parties think they hold valid locks.

Keeping the lock file stable ensures processes always lock the same resource. Permissions on the lock directory must be managed to prevent processes from arbitrarily replacing or deleting files.

### Creating a marker with CREATE_NEW

If using a marker file as a claim mechanism, creation must be atomic with respect to file existence. In Java, `Files.createFile(path)` or `CREATE_NEW` ensures only one process succeeds when the path does not yet exist.

```java
try {
    Files.createFile(claimPath);
    // This process created the marker and is considered the owner under the protocol.
} catch (FileAlreadyExistsException busy) {
    // Another consumer has already claimed the resource.
}
```

Marker files can still remain after a crash. Owner metadata, leases/TTLs, or a reconciliation process are needed to reclaim stale claims safely. Do not simply check if a marker exists and delete it without verifying whether the owner is still active.

## Claiming files via atomic move

A common coordination approach for file pipelines moves files from an `incoming` directory to `processing`. Multiple consumers can attempt the claim concurrently, but only one succeeds if the filesystem provides an atomic rename/move for that operation.

```text
incoming/orders.csv
       |
       | atomic move / claim
       v
processing/orders.csv
       |
       | batch processing
       +------------------+
       |                  |
       v                  v
archive/orders.csv   error/orders.csv
```

Example:

```java
Path source = incoming.resolve(fileName);
Path claimed = processing.resolve(fileName);

try {
    Files.move(source, claimed, StandardCopyOption.ATOMIC_MOVE);
} catch (FileAlreadyExistsException alreadyClaimed) {
    // Another consumer has already claimed this file.
}
```

`ATOMIC_MOVE` is only supported when the filesystem/provider satisfies the requirements. Moving within the same filesystem is usually appropriate; moving across filesystems may not be atomic or supported. If atomic move cannot be used, use another protocol rather than assuming copy-then-delete is an atomic claim.

Atomic move also does not solve every crash scenario on its own. For example, a process can claim a file and then die before writing batch metadata. A recovery process is needed for files sitting in `processing`, cross-checking JobRepository and owner metadata to decide whether to restart or requeue.

## Producer must publish files after finishing writes

A common bug is a consumer starting to read a file while the producer is still writing it. Checking that a file exists or that its size has not changed over a short window is not absolute proof that the producer has finished.

A safer protocol:

1. The producer writes to a temporary name, such as `orders.csv.part`.
2. The producer flushes and closes the file.
3. The producer renames it to `orders.csv` on the same filesystem via atomic move if possible.
4. Consumers read only complete filenames or published manifests/ready markers.

```java
Path temporary = incoming.resolve("orders.csv.part");
Path ready = incoming.resolve("orders.csv");

writeAndClose(temporary);
Files.move(temporary, ready, StandardCopyOption.ATOMIC_MOVE);
```

`writeAndClose` is producer logic. After renaming, consumers can treat the file as ready under the protocol. If the filesystem does not support atomic move, use a manifest/ready marker created after closing the file, or a queue/metadata store with an explicit publish mechanism.

For large files or multi-file batches, create a manifest listing filenames, sizes, checksums, and the batch ID; publish the manifest once all files are ready. Consumers start only when the manifest is complete and checksums match.

## Preventing two JobExecutions from processing the same input

Spring Batch distinguishes `JobInstance` by job name and identifying parameters. This prevents duplicate launches of the same logical instance per repository rules, but it does not automatically prevent two different instances from sharing an input file.

Example:

```text
JobInstance A: importJob, businessDate=2026-11-15
JobInstance B: importJob, businessDate=2026-11-16

Both receive inputFile=/data/incoming/orders.csv
```

Two different instances can coexist and read the same file. If a file must be processed exactly once, a claim/lock layer keyed by file key or batch ID is needed. The claim key should be stable, such as normalized path + source version/checksum or producer batch ID.

Do not rely solely on filename if the producer can reuse that name for different content. The same path with different versions represents two distinct logical inputs; checksums or immutable object versions help distinguish them.

## Locks in the Spring Batch lifecycle

Locks can be managed at job or step scope depending on the shared resource.

### Job-level locks

If the entire job owns a file throughout its lifecycle, a lock can be acquired in `JobExecutionListener.beforeJob` and released in `afterJob`. This is straightforward, but remember `afterJob` is not guaranteed to run if the JVM is killed or the server loses power. OS locks are usually released when the process/channel ends; markers/leases need separate recovery.

### Step-level locks

If only one step uses the file, acquire the lock before opening the reader/writer and release it after the step finishes. A component implementing `ItemStream` or a tasklet/step listener can manage the lifecycle, ensuring the lock is held across the entire read/write period requiring protection.

Do not release the lock in `afterWrite` or mid-chunk callbacks if the step continues accessing the file. The lock must span the entire duration the resource requires protection.

### Locks in a wrapper service

Lock logic can be extracted into a `FileLockService` so steps share the same protocol:

```java
public interface FileLockService {
    FileLockHandle acquire(Path resource, Duration timeout);
}
```

`FileLockHandle` is an application-defined abstraction providing `close()` to release. Use try-with-resources at the execution site so the lock is released even when the reader, processor, or writer throws an exception.

## Example of FileLockService with timeout

A simple service can attempt locking within a bounded duration. The example below is a skeleton; production needs logging, filesystem error classification, and an appropriate backoff policy.

```java
public final class FileLockService {

    public FileLockHandle acquire(Path lockPath, Duration timeout)
            throws IOException, InterruptedException {

        Files.createDirectories(lockPath.getParent());
        FileChannel channel = FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE);

        long deadline = System.nanoTime() + timeout.toNanos();
        try {
            while (System.nanoTime() < deadline) {
                try {
                    FileLock lock = channel.tryLock();
                    if (lock != null) {
                        return new FileLockHandle(channel, lock);
                    }
                } catch (OverlappingFileLockException busyInThisJvm) {
                    // Another thread in this JVM holds an overlapping lock region.
                }

                Thread.sleep(100);
            }

            throw new FileLockTimeoutException(lockPath.toString());
        } catch (IOException | InterruptedException | RuntimeException ex) {
            channel.close();
            throw ex;
        }
    }
}
```

`FileLockHandle` can implement `AutoCloseable` and close the lock/channel:

```java
public final class FileLockHandle implements AutoCloseable {

    private final FileChannel channel;
    private final FileLock lock;

    public FileLockHandle(FileChannel channel, FileLock lock) {
        this.channel = channel;
        this.lock = lock;
    }

    @Override
    public void close() throws IOException {
        try {
            if (lock.isValid()) {
                lock.release();
            }
        } finally {
            channel.close();
        }
    }
}
```

This snippet illustrates waiting with a timeout. In real implementations, use a safe deadline, avoid losing interrupts, handle errors when closing the channel, and avoid tight polling. `Thread.sleep` is only an example; exponential backoff with jitter can prevent multiple consumers from retrying in lockstep.

Do not hold locks while waiting indefinitely. If the timeout expires, the application can mark the file as not ready and retry on the next poll, or raise an alert for operator intervention.

## Files in use on Windows and Linux

Deleting, renaming, or overwriting an open file can behave differently across operating systems.

| Operation | Windows (typical) | Linux/Unix (typical) |
| --- | --- | --- |
| Open file for reading while another process reads | Usually allowed if sharing mode is compatible | Usually allowed |
| Open file for writing while another process holds a handle | May be denied depending on sharing flags/locks | May open, but still risks races/overwrites without coordination |
| Delete an open file | Usually denied if handle does not allow delete sharing | Can unlink filename while process keeps file descriptor open |
| Rename an open file | May be denied depending on handle/share mode | Usually can rename; open process still accesses old inode |
| File locks | Depends on FileChannel and filesystem | Usually advisory; depends on filesystem/mount |

This is common behavior, not an absolute contract for every filesystem or API. Antivirus software, indexing services, backup agents, editors, preview panes, or other processes can also hold handles on Windows and cause rename/delete operations to fail.

For cross-platform processing, avoid relying on deleting or renaming open files. Design producers to close files before publishing; consumers open only ready resources; outputs are written to separate paths and published after closing.

## File-in-use errors and classification

Several Java exceptions can occur:

- `AccessDeniedException`: insufficient permissions or operation denied by the operating system.
- `FileSystemException`: general filesystem error; message may describe a file in use.
- `FileAlreadyExistsException`: destination path already exists when creating a marker or moving.
- `NoSuchFileException`: file or directory no longer exists.
- `OverlappingFileLockException`: overlapping region lock in the same JVM.
- `IOException`: error opening, reading, writing, locking, or closing a resource.

Do not classify every `IOException` as a busy-file error. Wrong permissions, missing paths, disk full, read-only filesystems, and file lock conflicts require different handling.

A handling policy might include:

1. If the lock is held by another owner, wait with a bound or return the file to the queue.
2. If the error is transient due to antivirus or a short-lived process holding a handle, retry with bounded backoff.
3. If permissions or paths are invalid, fail fast and report configuration.
4. If disk is full or filesystem is read-only, do not retry endlessly; alert operations.
5. If the file disappears after claim, cross-check metadata/manifest and report source error.

Only retry errors that can recover on their own. Do not use a skip policy to skip busy-file errors if skipping a file loses business data.

## Retrying when a file is busy

If a rename or file-open operation fails due to a temporary lock, it can be retried with bounds. Retries need an overall timeout, increasing intervals, and diagnostic information.

```java
int maxAttempts = 5;
long delayMillis = 200;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        openAndProcessFile(path);
        break;
    } catch (AccessDeniedException | FileSystemException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }
        Thread.sleep(delayMillis);
        delayMillis = Math.min(delayMillis * 2, 2_000);
    }
}
```

This only illustrates the idea. In Java, `AccessDeniedException` is a subclass of `FileSystemException`, so both cannot appear in the same multi-catch; real code must catch `FileSystemException` once and classify subtypes/messages appropriately. Avoid classifying by message strings if an exception type or clear OS error code can be used.

In Spring Batch, retries can be configured in a fault-tolerant step if the exception originates from the reader/writer and the exception type is properly classified. However, if the error happens before the step can open the resource, retries may be needed in tasklet/service orchestration or via scheduler job retries per policy. Never retry a long-held file indefinitely.

## Lock files and stale locks

If using marker files, a process can die after creating the marker without deleting it. The leftover marker is called a stale lock under the marker protocol. Do not delete it merely because the file is old; the owner might still be running a long job or a node might have experienced a temporary disconnect.

Marker metadata should include:

- Logical resource key or file identity.
- Unique owner ID for the execution.
- Host/node name and process ID for diagnostics.
- Acquisition timestamp and lease expiration timestamp.
- Fencing token or generation if needed to prevent an old owner from continuing to write.
- Job name, `JobExecution` ID, and correlation ID if available.

PID and host name are diagnostic information only, insufficient to prove the owner is alive. PIDs can be reused and nodes may be unreachable. Safely reclaiming stale locks requires time-bounded leases, heartbeats, and a fencing rule.

## Leases and fencing tokens for multiple nodes

When multiple nodes process files on shared storage, OS file locks are not always a reliable choice. A database lock/lease table or distributed coordination service can be used.

A claim table might store:

```text
batch_file_claim
----------------
file_key          PRIMARY KEY
owner_id
lease_until
fencing_token
updated_at
```

High-level workflow:

1. The consumer tries to insert or update the claim conditioned on the lease having expired.
2. The database guarantees only one transaction wins ownership at a time via unique constraint/conditional update.
3. The owner receives a monotonically increasing `fencing_token`.
4. The owner periodically renews the lease while still working.
5. Upon completion, the owner releases the claim conditioned on matching `owner_id` and token.
6. If the lease expires, another consumer can claim it with a new token.

Leases solve the case where an owner dies without releasing. However, TTL alone is not enough: an old owner may pause for a long time, its lease expires, and a new owner claims the file; then the old owner wakes up and resumes writing. Fencing tokens let the destination resource reject operations from the old owner if its token is lower than the latest token.

Do not keep a database transaction open for the entire job duration just to hold `SELECT ... FOR UPDATE`; long transactions hold connections and locks for a long time, causing contention. Separately committed lease rows with expirations and heartbeats are usually better suited for long-running work.

## File locks on NFS, SMB, and shared storage

When files reside on NFS or SMB, lock and cache semantics can differ from local disk. Behavior also depends on protocol version, mount options, server configuration, and client implementation. A lock that works well on a developer machine does not prove it coordinates properly across production containers or nodes.

Before choosing file locks on shared storage, verify:

- Does the filesystem support locks across clients or only within a single node?
- Are locks maintained across network partitions or server restarts?
- Are rename/create operations atomic within the target directory?
- Do clients cache directory entries or file attributes, delaying visibility of changes?
- When a node dies, how are locks released?
- Can owners be observed and locks safely reclaimed?

Without reliable semantics, use database leases, a distributed lock service, or a queue/metadata store with atomic claims. Do not rely on a marker file on a shared mount without testing multi-node and network-failure scenarios.

## Object storage lacks filesystem-style file locks

Object storage such as S3-compatible storage generally does not provide `FileChannel` or byte-range locks with local filesystem semantics. Instead, applications use object keys/versions, conditional create/update, metadata/manifests, and external claim mechanisms.

A workflow might:

- Producer uploads an object with an immutable key/version.
- Producer publishes a manifest or `READY` status after upload completes.
- Consumer claims the batch ID in the database via conditional update.
- Job stores the object key and version ID in `JobParameters` or `ExecutionContext`.
- Writer outputs a temporary object, then updates a manifest/pointer upon successful publish.

Do not assume object renaming is an atomic operation like local file renaming; on many object stores, rename is emulated via copy then delete. Use conditional write/versioning APIs and an appropriate metadata store.

## Coordinating file locks with FlatFileItemReader

`FlatFileItemReader` reads files via streams and can save read position for restart. It does not automatically establish an OS lock preventing producers or other jobs from writing the same file.

If input could be modified while reading, ensure the file was closed and published by the producer before the reader opens it. You can claim the file using atomic move or a lock service, then configure the reader to read the path inside `processing`.

Example reader receiving resource via step scope:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['claimedFile']}") String claimedFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(claimedFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`claimedFile` must remain stable across restarts. If the initial run moved the file to `processing`, restart must reuse that path or a persistently stored resource identity. Do not re-claim the file by generating a new identifying parameter if you want to restart the same `JobInstance`.

## Coordinating file locks with FlatFileItemWriter

`FlatFileItemWriter` supports state and restart, but that does not mean multiple jobs can safely write to the same file concurrently. Each logical execution should have its own output resource or an explicit exclusive locking protocol.

For example, the output path can be tied to business date and a stable execution identity:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(order ->
                    order.orderId() + "," + order.amount())
            .saveState(true)
            .build();
}
```

Keep `outputFile` and the writer name stable for the same logical execution so restarts restore state. Two different executions must not share the same output path unless the writer is specifically designed for concurrent coordination.

### Writing a temporary file then publishing

If consumers may only see complete files, the writer can write to `orders.csv.part`. After the step/job completes and the file is closed, a finalize step renames it to `orders.csv` or publishes a manifest. If the job fails, the `.part` file is kept for restart or moved to quarantine per workflow.

Renaming requires the same filesystem for atomicity. If copying across filesystems is required, consumers must wait for a completion marker/manifest and verify checksums.

## Lock lifecycle with Spring Batch

One implementation approach is creating an `ItemStream`/service that holds the lock handle and releases it when the step closes:

```java
public class LockedFileResource implements ItemStream {

    private final FileLockService lockService;
    private final Path lockPath;
    private FileLockHandle handle;

    public LockedFileResource(FileLockService lockService, Path lockPath) {
        this.lockService = lockService;
        this.lockPath = lockPath;
    }

    @Override
    public void open(ExecutionContext context) {
        handle = lockService.acquire(lockPath, Duration.ofSeconds(30));
    }

    @Override
    public void update(ExecutionContext context) {
        // Lock ownership does not need checkpointing like reader position.
    }

    @Override
    public void close() throws ItemStreamException {
        if (handle != null) {
            try {
                handle.close();
            } catch (IOException ex) {
                throw new ItemStreamException("Cannot release file lock", ex);
            }
        }
    }
}
```

This is a skeleton illustrating the lifecycle. Ensure the stream is registered with the step and opened before the reader/writer accesses the file. In real applications, the lock handle can be managed by a resource wrapper or appropriate listener. If `open` fails, the step must not proceed to read/write the resource.

Do not store `FileLock`, `FileChannel`, or open handle objects in the `ExecutionContext`; these are runtime resources that cannot be serialized or restarted. Only store file/claim identifiers and acquire a new lock on the corresponding execution/restart.

## When to release the lock?

Locks must be held for the exact duration the resource requires exclusivity:

- Input file: from before the reader opens the file until the step no longer reads it.
- Output file: from before the writer opens the file until the writer closes and output is finalized.
- Claim file: from when the consumer receives processing ownership until the file is archived/errored or processing status is committed.

Releasing too early allows another job to open the file while the current step is still using it. Holding a lock too long reduces throughput and can block other consumers unnecessarily.

With OS locks, closing the channel normally releases the lock even if code skips `release()` due to an exception. With markers/leases, release conditionally by owner ID/token; never delete another owner's claim.

## Job restart and file locks

When a job stops or fails, runtime locks must be released. On restart, the job must re-acquire the lock before opening the file. A lock handle cannot be serialized in context and expected to remain valid after a new process starts.

A typical restart flow:

```text
First run
  claim input
  acquire lock
  read/write some chunks
  chunk error -> rollback
  release lock when step finishes
  JobExecution FAILED

Restart
  use same identifying JobParameters
  confirm input resource still exists
  acquire new lock
  restore reader/writer checkpoint
  continue processing
  complete -> archive input / publish output
  release lock
```

If a file is moved out of `processing` or archived before job metadata commits, a restart may fail to find the resource. The order of file updates and batch metadata updates must be designed to recover from a crash between the two operations. Database claim/manifest statuses can be cross-checked against `JobExecution` so archiving occurs only after the job completes.

## Idempotency and duplicate processing

File locks reduce the chance of two consumers processing a file simultaneously, but they do not by themselves guarantee a file is processed exactly once across all crash scenarios.

For instance, a job writes business data successfully, then the process dies before updating the file manifest to `PROCESSED`. The next poll may re-claim the file. If the writer is not idempotent, data will be written twice.

Additional mechanisms:

- Unique batch ID or file identity in the database.
- Unique constraints for business keys or a processing ledger.
- Output paths tied to logical execution and source version.
- Manifest recording `CLAIMED`, `PROCESSING`, `COMPLETED`, or `FAILED` states.
- Transactional outbox for events emitted after writing business data.
- Reconciliation of input/output counts and checksums.

Locks coordinate concurrent access; idempotency ensures safe handling when work is replayed. The two mechanisms complement each other.

## Monitoring and operations

To troubleshoot file contention, logs should include enough information while avoiding sensitive payloads:

- Normalized file key/path.
- Source version, checksum, or batch ID.
- Job name and `JobExecution` ID.
- Step name and `StepExecution` ID.
- Owner ID, host/node, and fencing token if present.
- Acquisition time, lock hold duration, and release time.
- Retry count and lock wait time.
- Claim, archive, quarantine, or publish outcome.
- Exception type and classified I/O cause.

Useful metrics:

- Files pending, claimed, and processing.
- Successful/failed lock acquisitions.
- Average and high-percentile lock wait times.
- Expired leases/stale claims reclaimed.
- Reprocessed files and duplicates detected.
- Rename/delete/open errors and remaining disk space.

Do not log tokens/secrets or full file contents. If paths contain customer information, log file IDs or hashes instead of full paths per security policy.

## Testing file locks

Lock testing should cover both threads within the same JVM and separate processes if production runs multiple processes/nodes.

### Two threads competing for the same lock

Open the same lock path from two threads. The first thread acquires the lock and holds it until the test releases it; the second thread must not be granted a conflicting lock. Use `CountDownLatch` to control timing rather than `Thread.sleep` to guess ordering.

### Two processes competing for the same lock

Launch two test JVM processes concurrently requesting a lock on a supported filesystem. Verify only one process acquires the exclusive lock at a time. This test matters because `synchronized` cannot test inter-process coordination.

### Process dying while holding an OS lock

Have a test process acquire a lock and terminate abnormally. Verify the OS releases the lock when the channel/process closes according to environment semantics. If using marker files, verify the marker remains and the lease/reconciliation workflow handles it; do not confuse a lingering marker with an active OS lock.

### Producer still writing a file

Simulate a producer keeping a `.part` file open while the consumer only watches `ready` files. Verify the consumer does not read the file before the producer closes and publishes the marker/rename.

### Two consumers claiming the same file

Have two workers concurrently attempt an atomic move from `incoming` to `processing`. Verify only one consumer succeeds on a filesystem supporting atomic move. Test separately on the actual production storage type.

### Busy file and retry timeout

Hold a lock from a test thread and have a consumer attempt to acquire with a bounded timeout. Verify the consumer exits on time, reports the file busy, and does not spin in an infinite loop.

### Restart after claim

Have a job claim a file, commit some chunks, and then fail. Restart with the same identifying parameters and verify the file remains at its saved location, the lock is re-acquired, reader/writer checkpoints are restored, and output has no duplicates.

### Stale leases and fencing

In a database lease test, let owner A's lease expire, have owner B claim with a new fencing token, and simulate owner A returning. The target resource must reject operations carrying the old token if fencing is implemented.

## Common Pitfalls

### Checking only file existence before reading

The producer may still be writing. Use a publish-after-close protocol, manifest, or ready marker.

### Using `synchronized` to lock files across multiple nodes

`synchronized` only applies within a single JVM. Use filesystem-supported OS locks, atomic claims, or distributed leases.

### Assuming every program respects FileLock

Many file locks are advisory. Processes not participating in the protocol can still read/write the file.

### Deleting the lock file after releasing

This can create a race when processes have opened different file objects under the same name. For OS locks on sidecar files, keep the file stable and only release the lock.

### Using markers without TTL/owner

A process crash can leave a marker permanently. Record owner metadata, leases, and safe reclamation procedures.

### Deleting stale locks solely due to age

The owner might still be active or experiencing a pause/network partition. Use leases/heartbeats and fencing rather than timestamp comparisons alone.

### Using FileLock on shared filesystems without testing

NFS/SMB have different semantics from local disk. Verify locking, renaming, caching, and crash recovery in the actual environment.

### Two jobs using the same output path

JobRepository does not automatically lock output files. Use separate output paths per logical execution or claim an exclusive lock.

### Holding locks across unbounded I/O

A hung API or database call can hold a file lock indefinitely. Set timeouts on every resource and provide stop/recovery mechanisms.

### Assuming restart automatically reclaims old locks

Lock handles are not serialized. Restarts must acquire a new lock and verify the file/resource is still the right version.

### Assuming locks guarantee exactly-once processing

A crash can occur between business commit and file status update. Idempotency, ledgers, manifests, or outboxes are needed to handle replays.

## Design principles

When building a file-based batch pipeline, determine:

1. How does the producer publish files so consumers know writing is complete?
2. Which path, batch ID, version, or checksum forms the file identity?
3. Do multiple consumers claim files via OS locks, atomic moves, or database leases?
4. Does the locking mechanism work across processes/nodes and on the production filesystem?
5. How long is the lock held and in which lifecycle is it released?
6. When a process dies, does the OS lock auto-release or do markers/leases need recovery?
7. Is there a fencing token to prevent an old owner from continuing to write after lease expiration?
8. Are input/output paths stable across restarts?
9. Does the writer have state, transactions, or idempotency to prevent duplicate output?
10. Are files archived/published only after batch metadata and business output reach the proper state?
11. Can monitoring identify owners, lock durations, and stuck files?
12. Do integration tests simulate contention, crashes, stale locks, and restarts?

For local or single-host pipelines, `FileChannel`/`FileLock` can fit if every consumer obeys the same protocol and the filesystem supports it. For multi-node, shared storage, or object storage, choose claim/lease mechanisms with clear semantics and test failure modes. Combine locks with checkpoints, idempotency, and complete file-publishing workflows so jobs can stop, restart, and recover safely.

## Key takeaways

File locks help coordinate access among processes following the same protocol; Java NIO provides `FileChannel.lock()` and `tryLock()`, though locks may be advisory and filesystem-dependent. `synchronized` only locks within one JVM; multiple nodes require atomic claims, database leases, or appropriate distributed coordination. Producers should write temporary files, close them, and publish via atomic move/manifest; consumers claim files before processing. Hold locks throughout the duration the resource requires protection, release via an explicit lifecycle, and never serialize `FileLock` into `ExecutionContext`. On crashes, OS locks may release while markers can remain; leases, heartbeats, and fencing enable safe reclamation. Spring Batch does not lock files automatically for readers/writers; coordinate locks with `ItemStream`, checkpoints, stable output paths, restarts, and idempotency to avoid duplicate processing or data loss.
