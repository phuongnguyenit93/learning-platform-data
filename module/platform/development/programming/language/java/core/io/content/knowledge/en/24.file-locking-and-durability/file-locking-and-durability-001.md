# FileLock, lock, and tryLock in Java NIO

When two processes read or modify a file concurrently, each process might write valid bytes, yet the overall result can still be wrong: content gets overwritten, updates are left incomplete, or one process reads while another is actively changing the data. `java.nio.channels.FileLock` provides a mechanism for **locking a region of a file at the file-system level** through `FileChannel`. The two most important operations are `lock()` (which may block to acquire the lock) and `tryLock()` (which attempts to acquire it immediately).

Understanding `FileLock` requires distinguishing between **exclusive and shared locks**, **conflicts across processes versus within the same JVM**, **locked byte ranges**, **lock lifecycle**, and the practical limitations of locking on each operating system. File locks also do not replace thread synchronization or guarantee that data has been durably written to the storage device.

## 1. What is FileLock and When to Use It?

`FileLock` represents a lock on a byte region in a file opened by a `FileChannel`. Its goal is to coordinate access to the **same file** among components, typically different processes. A lock can be of two types:

- **Exclusive lock:** Requires that no other conflicting locks exist on the same region. Suitable when a process is updating a file.
- **Shared lock:** Allows participants to hold shared locks concurrently if the system supports it, but conflicts with an exclusive lock on the same region. Useful when cooperating parties are only reading.

For example: two applications share `records.dat`. Before updating a record, program A requests an exclusive lock on the byte region containing that record. Program B also requesting an exclusive lock on the same region will have to wait, fail when trying without blocking, or receive an exception depending on the situation and API.

A lock does not automatically interpret records, recover content when a write fails, or validate data integrity on its own. To maintain consistency, you must define a **locking protocol that all participating components follow**.

### FileLock Is Not Like a Java Thread Lock

`synchronized`, `ReentrantLock`, and `FileLock` solve different classes of problems:

| Mechanism | Coordination Scope | Best Suited For |
| --- | --- | --- |
| `synchronized` or `ReentrantLock` | Threads using the same lock convention inside a single JVM | Protecting variables, objects, and sequences of operations |
| `FileLock` | File lock via OS mechanism, capable of coordinating multiple processes | Preventing cooperating processes from manipulating the same file region |
| Write temp file + controlled replacement | Whole-file update workflow, controlling visibility state | Avoiding leaving the target file half-written in certain scenarios |

In particular, **file locks are held on behalf of the entire JVM**, not the individual thread that acquired the lock. Therefore, do not use `FileLock` as a lock to coordinate threads within the same process. Multiple threads in a single JVM requesting locks on overlapping regions will not simply wait on each other like `ReentrantLock`.

## 2. Opening FileChannel with Appropriate Permissions

To request a lock with `FileChannel`, you must first open the file with compatible `OpenOption` flags.

```java
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

// Illustrated inside a method that handles IOException.
Path file = Path.of("records.dat");

try (FileChannel channel = FileChannel.open(
        file,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE)) {
    // Can request an exclusive lock and perform reads/writes.
}
```

This snippet only illustrates how to open the channel: `CREATE` creates the file if it does not exist; `READ + WRITE` grants read/write permissions to the channel. `CREATE` does not create parent directories; if the path is invalid or lacks permissions, `open` can still throw `IOException`.

Important rules for `FileChannel.lock(position, size, shared)`:

- **Exclusive lock** (`shared=false`) requires the channel to be opened for writing; otherwise, a `NonWritableChannelException` may be thrown.
- **Shared lock** (`shared=true`) requires the channel to be opened for reading; otherwise, a `NonReadableChannelException` may be thrown.
- On some platforms, a request for a shared lock may be fulfilled by the operating system as an exclusive lock. Therefore, after acquiring the lock, check `fileLock.isShared()` if the application depends strictly on the granted lock type.
- Do not assume that opening a file with `READ` guarantees that shared locks are supported on all systems.

When only coordinating writers, opening the channel with `WRITE` and requesting an exclusive lock is usually the simpler choice.

## 3. lock(): Requesting a Lock That May Block

Common overloads:

```java
FileLock entire = channel.lock();
FileLock range = channel.lock(100, 50, false);
FileLock shared = channel.lock(0, 1024, true);
```

These lines illustrate **independent calls** on an appropriate channel; do not run all three sequentially on the same file when the regions overlap. A lock must be released before requesting a conflicting lock.

- `lock()` is equivalent to requesting an exclusive lock on the region starting at byte 0 with length `Long.MAX_VALUE`. This region covers all accessible bytes of the file to lock the entire file by convention.
- `lock(position, size, shared)` requests a lock on a contiguous region starting at byte `position` with length `size`; `shared` specifies the requested lock type.
- If **another** process already holds a conflicting lock, `lock()` typically **blocks the calling thread**, waiting until the lock can be granted, the thread is interrupted, or an error occurs.
- If **the current JVM itself** already holds an overlapping lock, or a thread in the JVM is waiting for an overlapping lock, the request may throw `OverlappingFileLockException` immediately instead of waiting.

There is no built-in timeout in the `lock()` signature. If a task has a deadline or a UI needs to stay responsive, you must design appropriate timeout/cancellation and coordination mechanisms; do not call `lock()` on a UI thread or event loop that must not block.

A safe way to hold an exclusive lock throughout an update:

```java
// Illustrated with file as a valid Path; the method allows throwing IOException.
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock ignored = channel.lock()) {
    // Perform the designed sequence of update operations.
    // The lock is automatically released when leaving try.
}
```

The `try-with-resources` block helps prevent forgetting `release()` when an update throws an exception. The variable name `ignored` simply means the lock object does not need to be referenced inside the block body; it is still the resource holding the lock.

## 4. tryLock(): Non-Blocking Attempt

For code that needs to know immediately whether a lock is available:

```java
FileLock lock = channel.tryLock();
```

`tryLock()` defaults to requesting an exclusive lock on the entire file; `tryLock(position, size, shared)` lets you specify the region and lock type. Possible outcomes include:

| Status | `tryLock()` |
| --- | --- |
| Lock acquired successfully | Returns a valid `FileLock`; caller must release it |
| **Another process** holds a conflicting lock | Returns `null` instead of waiting |
| Current JVM already holds or is waiting for an overlapping lock | Throws `OverlappingFileLockException` |
| Incompatible channel permissions/options | Throws an exception such as `NonWritableChannelException` or `NonReadableChannelException` |
| Channel closed, file system error, or unsupported provider | Corresponding exception, possibly `IOException` |

**Never write `channel.tryLock().release()`**: the result can be `null`. Also, do not catch `OverlappingFileLockException` and treat it as a failure from another process; it specifically signals a **lock conflict within the current JVM**.

Common pattern:

```java
// Illustrated inside a method that handles IOException.
FileLock acquired = channel.tryLock();
if (acquired == null) {
    System.out.println("File is busy; retry later");
} else {
    try (acquired) {
        // Access the data requiring the lock.
    }
}
```

Here `acquired` is an effectively final variable assigned once, so it qualifies as a resource in Java 9+ `try (acquired)`. For `OverlappingFileLockException`, this snippet lets the exception propagate because it represents an intra-JVM coordination issue that must be handled separately.

### Should You Retry Multiple Times?

In applications that need retries, you should configure a maximum retry count, deadline, wait interval or exponential backoff, and a cancellation mechanism. A tight `while (channel.tryLock() == null) { }` spin loop can consume CPU and still fails to handle `OverlappingFileLockException`. If the file is continuously updated by multiple processes, a good retry strategy should also prevent starvation.

## 5. Byte Regions: Lock Position and Size

The `position` and `size` arguments describe a **byte region of the file**, not the current `channel.position()` and not `ByteBuffer.position()`.

Example:

```text
File:    |--------- bytes 0..99 ---------|---- 100..149 ----|---- 150..199 ----|
Lock A:                                    [100, 150)
Lock B:                                                   [150, 200)
Lock C:                                           [120, 140)
```

- `lock(100, 50, false)` requests a lock on bytes 100 through 149 (the half-open interval `[100,150)`).
- `lock(150, 50, false)` requests the adjacent region: **non-overlapping in byte coordinates** with the previous region.
- `lock(120, 20, false)` overlaps with the first lock and will be treated as a conflict depending on the lock type as well as JVM/process boundaries.
- Lock regions can lie **beyond the current EOF**; the position and length of a lock region do not automatically grow the file size.
- Negative values, invalid ranges, or `position + size` overflowing representable limits are required by the API to fail with an exception such as `IllegalArgumentException`.

For a fixed-record file containing records of uniform size `recordSize`, you can select the lock region for record `index`:

```java
// Illustrated inside a method that handles IOException.
long offset = Math.multiplyExact(index, recordSize);
try (FileLock recordLock =
        channel.lock(offset, recordSize, false)) {
    // Update only the corresponding record.
}
```

This snippet assumes `index` and `recordSize` are non-negative, `recordSize > 0`, the channel has write permission, and data is accessed using an exact offset convention; `Math.multiplyExact` helps detect multiplication overflow. You must also ensure `offset + recordSize` does not overflow `long` and that the file contains valid data if you intend to read an existing record.

**Do not rely strictly on fine-grained region locking across all platforms.** The file system, provider, or how the filesystem implements locking can affect the ability to grant region locks and how non-JVM applications respect them. When broad compatibility is required, test this mechanism in the target deployment environment.

## 6. Complete Java 17+ Program: lock, tryLock, and Intra-JVM Conflict

The following example creates a new temporary file and opens **two independent FileChannels pointing to the same file within a single JVM**. The first channel acquires an exclusive lock. The second channel calls `tryLock()` while the region is locked, demonstrating that a **same-JVM** conflict is reported via `OverlappingFileLockException`, not `null`. Once the first lock is released, the second channel can acquire the lock successfully.

Create the file **`FileLockDemo.java`**:

```java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileLockDemo {
    private FileLockDemo() {}

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("file-lock-demo-", ".bin");
        try {
            try (FileChannel first = FileChannel.open(file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE);
                 FileChannel second = FileChannel.open(file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                FileLock holder = first.lock();
                try {
                    System.out.println("first valid=" + holder.isValid());
                    System.out.println("first shared=" + holder.isShared());

                    try (FileLock unexpected = second.tryLock()) {
                        // A conflict within the same JVM must be reported via exception.
                        throw new AssertionError("Unexpected overlapping lock");
                    } catch (OverlappingFileLockException expected) {
                        System.out.println("same JVM overlap=exception");
                    }
                } finally {
                    holder.release();
                }

                System.out.println("first after release="
                        + holder.isValid());

                try (FileLock acquired = second.tryLock()) {
                    if (acquired == null) {
                        throw new IOException("File locked by another process");
                    }
                    System.out.println("second acquired=" + acquired.isValid());
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run:

```bash
javac FileLockDemo.java
java FileLockDemo
```

Output in a local temporary file environment that supports file locking without external interference:

```text
first valid=true
first shared=false
same JVM overlap=exception
first after release=false
second acquired=true
```

Explanation:

1. `Files.createTempFile` creates a new file name in the temporary directory. Both channels use the same path, so both lock requests target the same file.
2. `first.lock()` requests a whole-file exclusive lock; `holder.isValid()` is `true` and `holder.isShared()` is `false`.
3. `second.tryLock()` requests an overlapping exclusive lock within the same JVM, so it throws `OverlappingFileLockException`, which is caught explicitly.
4. `holder.release()` releases the lock; `isValid()` becomes `false`.
5. After release, `second.tryLock()` acquires the exclusive lock. The `try-with-resources` blocks close the `FileLock` object and channels in the proper resource order; finally, the temporary file is deleted.

This example **does not demonstrate `tryLock()` returning `null` in an inter-process conflict**. To test that branch, you need **two separate JVM processes**: the first process holds the lock while the second process attempts to lock the same region before the first releases it. On a system supporting appropriate locking, the attempt in the second process returns `null`. Do not simulate this using two `FileChannel` instances in the same JVM expecting `null`.

## 7. Releasing Locks and Managing Lifecycle

The `FileLock` object provides:

| API | Meaning |
| --- | --- |
| `position()` | Starting position of the requested lock region |
| `size()` | Length of the lock region |
| `isShared()` | Indicates whether the granted lock is shared or exclusive |
| `isValid()` | Whether the lock is still valid according to API state |
| `release()` | Requests release of the lock |
| `close()` | `AutoCloseable` method enabling release in `try-with-resources` |
| `acquiredBy()` | Returns the channel that acquired the lock |

A valid lock remains in effect until `release()` is called, its associated channel is closed, or the JVM terminates (depending on the OS release mechanism). `FileLock.isValid()` checks the known state, though it is not an immutable guarantee if resources are closed concurrently.

Special note: on **some operating systems**, closing *any channel* to the same file can release **all locks held by the JVM on that file**, including locks acquired through other channels. Therefore, do not arbitrarily open and close multiple channels to the same file while relying on a lock held by another channel. If the logic is sensitive, manage file/channel ownership and lock duration clearly, and test in the target runtime environment.

Preferred lock-closing pattern:

```java
// Illustrated: file is a Path; IOException handling is required.
try (FileChannel channel = FileChannel.open(file,
        StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    // Access the coordinated resource according to protocol.
}
// Lock is released, channel is closed.
```

However, if code inside the lock scope creates additional views/mappings or passes resources to another thread, ensure that no other thread continues operating after the lock has been released.

## 8. Exceptions and Lock-Waiting Scenarios

| Scenario | API Response |
| --- | --- |
| Overlapping region lock within the same JVM | `OverlappingFileLockException` |
| `lock()` must wait for another process | Thread may block until the lock is granted or an error occurs |
| `tryLock()` encounters a conflicting lock in another process | `null` |
| Exclusive lock from a non-writable channel | `NonWritableChannelException` |
| Shared lock from a non-readable channel | `NonReadableChannelException` |
| Thread interrupted while `lock()` is waiting | May throw `FileLockInterruptionException` |
| Channel closed while thread is waiting for lock | May throw `AsynchronousCloseException` |
| File/channel encounters an I/O error | `IOException` or an appropriate subclass |
| Invalid lock region coordinates | `IllegalArgumentException` |
| Channel already closed before operation | Usually `ClosedChannelException` |

For background tasks, interruption and channel closure should be handled intentionally. Avoid catching every exception and logging "file is busy": `OverlappingFileLockException` indicates an intra-JVM lock management issue; `IOException` can mean device failure or lost permissions; and `null` from `tryLock()` is the API-contract outcome for a non-blocking attempt blocked by another process's lock.

If a bounded wait is needed instead of indefinite blocking, a deadline-based retry loop over `tryLock()` can be easier to control than `lock()`, provided you throttle retry frequency, handle interruption, and distinguish `null` from exceptions.

## 9. Practical Limitations of FileLock

### 9.1. Advisory vs. Mandatory Locks

Not all systems force ordinary read/write operations to obey `FileLock`. Some systems implement **advisory locks**: only programs that participate in the locking convention avoid conflicts. Others support or use **mandatory locks** in certain modes. Java does not promise identical enforcement behavior across all providers/file systems.

Consequence: if application A holds an exclusive lock but another tool ignores the locking convention and writes directly, behavior can vary by environment. **Do not rely on FileLock as an enforced security barrier** against all other applications; use file permissions, ownership protocols, and real-world testing.

### 9.2. Not a Transaction, No Atomicity or Durability Guarantee

Acquiring a lock successfully **does not automatically**:

- Combine multiple `channel.write()` calls into an indivisible transaction.
- Prevent the operating system or device from failing during writes.
- Recover data if the process crashes midway.
- Ensure data has reached durable device storage.

For critical data, in addition to a locking convention, you may need `FileChannel.force(boolean)` per durability requirements, temporary file writes with controlled replacement policies, or a recoverable logging structure. `force` also has device/provider-dependent guarantees; it does not replace lock management and error recovery.

### 9.3. File Locks and Memory-Mapped Buffers

`FileChannel.map()` creates a memory mapping of a file; accesses to the mapped region can interact with file locks in operating-system-dependent ways. **Do not assume a FileLock will prevent all reads/writes to a mapped region on all platforms.** If an application uses both mapping and locking, design and test an explicit synchronization protocol.

### 9.4. NFS, SMB, Containers, and OS Limitations

File locking depends on the provider, filesystem capabilities, and sometimes network configuration. On network filesystems or multi-container environments, implementation and disconnect-handling semantics can differ from local disks. Test on the exact target infrastructure, especially when locks guard exclusive jobs or data written by multiple hosts.

Holding locks for too long can also reduce throughput and cause logical deadlocks if multiple files/locks are acquired in inconsistent orders. When multiple resources must be locked, establish a fixed ordering, keep the locked scope as small as safely possible, and always release via `try-with-resources`.

## 10. Using FileLock to Ensure a Single Owner Process

A common use case is allowing only one worker instance to update a data file at a time. Logic example:

1. Open the channel with appropriate `READ/WRITE` options, ensuring the lock file resides on storage shared by all participating processes.
2. Call `tryLock()`. If it returns `null`, the application can exit or schedule a retry rather than blocking.
3. If a `FileLock` is returned, hold the lock throughout the entire read, validation, update, and related verification steps.
4. In `finally` or `try-with-resources`, release the lock and close the channel. Log or handle I/O errors explicitly instead of ignoring them.

This pattern requires every participating process to follow the same locking convention. If a shared physical path/filesystem or consistent provider behavior cannot be guaranteed, a distributed lock or external coordination mechanism may be necessary.

A separate **lock file** (such as `worker.lock`) can help avoid touching the data file directly, but the workflow must not **delete and recreate the lock file** while another process holds the old lock: deleting and recreating can yield two different underlying file objects at the same pathname, breaking the assumption that all parties lock the same object. Distinguish between a file existing at a path and an OS lock held on an underlying file object.

## 11. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Expecting `tryLock()` to block like `lock()` | Does not block; returns `null` if another process holds the lock | Handle `null` or use `lock()` when blocking is truly desired |
| Assuming an overlapping lock in the same JVM makes `tryLock()` return `null` | Throws `OverlappingFileLockException` | Coordinate with Java thread locks and distinguish intra-JVM errors |
| Using `FileLock` instead of `ReentrantLock` for multithreading | Race conditions/logical deadlocks, overlapping-region exceptions | Use dedicated thread-synchronization primitives |
| Requesting an exclusive lock on a read-only channel | `NonWritableChannelException` | Open the channel with `WRITE` permission |
| Assuming shared locks are always supported | Actual lock granted may be exclusive | Check `isShared()` |
| Forgetting `release()` or not closing the channel | Holds locks/resources for too long | Use `try-with-resources` |
| Holding a lock while freely closing another channel to the same file | Some systems may unintentionally release the lock | Centralize channel and lock management |
| Locking one region while writing outside that region | Data outside the lock range is unprotected by convention | Compute offset/size clearly and validate in business logic |
| Believing `FileLock` forces every other program to comply | Uncooperative processes can still modify the file on advisory systems | Enforce permissions and shared locking conventions |
| Believing lock = durable write | A crash can still lose or truncate data | Separate locking, `force`, temp-file writes, and recovery |
| Tightly spinning `tryLock()` when busy | Wastes CPU and can cause starvation | Use deadlines, retry/backoff, and cancellation |

**Key takeaway:** `FileChannel.lock()` requests a lock and may wait for another process; `tryLock()` returns immediately when another process holds a conflicting lock, yet still throws `OverlappingFileLockException` on intra-JVM overlaps. `FileLock` protects **byte regions under the system's locking semantics**, requiring careful management of channel open options, lock type, region bounds, errors, lifecycle, and cross-process coordination.