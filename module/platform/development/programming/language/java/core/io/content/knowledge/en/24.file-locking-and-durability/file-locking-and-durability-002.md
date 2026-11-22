# Exclusive Locks, Shared Locks, and Byte Regions with FileChannel (Java NIO.2)

When two processes read/write the same file concurrently, operating at the right offset **does not by itself protect content against concurrent updates**. Java NIO provides `FileChannel.lock(...)`, `tryLock(...)`, and `FileLock` to request a lock on a **byte region** of a file, in either **exclusive** or **shared** mode. These locks are primarily used to **coordinate between processes** through the operating system's file-locking mechanism.

The most important point: **FileLock is not a lock for coordinating threads within the same JVM; it is not a transaction; and it is not a guarantee that data has been durably written.** For a system to be correct, you must understand byte-region bounds, how the operating system enforces locks, when locks are acquired and released, and the relationship between locks, file contents, `force`, and application protocols.

After this lesson, you will be able to determine when to use shared/exclusive locks, how to partition byte regions, interpret the return values and exceptions of `lock/tryLock`, write Java 17+ code with clear lock lifecycles, and recognize the limitations of using file locking to protect data.

## 1. What Does a File Lock Protect?

Suppose two applications concurrently update a file `counter.dat` containing an integer. Each application performs "read current number → add one → write back". If both read the same value `41`, both may write `42` instead of the expected `43`. That is a **lost update**. A successful `FileChannel.write` call does not solve this business-logic contention.

An appropriate locking protocol might require:

1. Each process requests an **exclusive lock** on the region containing the counter.
2. Only after acquiring the lock does it read the current value.
3. Compute and write the new value while still holding the lock.
4. If durability is required, call `channel.force(...)` at the commit point.
5. Release the lock; only then may another process enter the update region under the same protocol.

For read-only tasks, multiple processes may simultaneously hold a **shared lock** on the same region if the platform supports it, provided writers request an exclusive lock and everyone obeys the protocol.

However, the degree to which the operating system **actually blocks access** differs: on platforms with **advisory locks**, a process that ignores the protocol can still open or modify the file; on systems with **mandatory locks**, certain conflicting operations may be blocked. Java recommends **always designing as if locks are advisory**, regardless of OS.

## 2. Shared Locks and Exclusive Locks

| Property | Exclusive lock | Shared lock |
| --- | --- | --- |
| Common purpose | Coordinating writers or read–modify–write operations | Coordinating concurrent readers |
| Conflict scope | An exclusive lock prevents overlapping shared/exclusive locks from being granted to another process under OS rules | Multiple overlapping shared locks may coexist; an overlapping exclusive lock request conflicts |
| Parameter flag | `shared=false` | `shared=true` |
| Channel open requirement | Channel must permit **WRITE** | Channel must permit **READ** |
| Portability | Depends on OS/filesystem lock support | Some platforms do not support shared locks; Java may **convert the request to exclusive** |
| How to check granted type | `lock.isShared() == false` | Check `lock.isShared()`, do not assume it is always `true` |

Imagine three processes accessing the same region `[0, 100)`:

- P1 holds a shared lock. P2 requests a shared lock on the same region: **may** be granted concurrently if the OS/provider supports shared locks.
- P1 holds a shared lock. P3 requests an exclusive lock on an overlapping region: must wait, fail immediately with `tryLock`, or fail with an error depending on conditions.
- P1 holds an exclusive lock. P2/P3 request an overlapping lock, whether shared or exclusive: cannot concurrently hold a conflicting lock type.

This is the inter-process protocol model. **Do not** infer from the table above that a single JVM may create two overlapping `FileLock` instances: the Javadoc forbids locks held within the **same JVM** from overlapping, even if both requests are shared. When an overlapping lock is already held or an overlapping request is waiting within the same JVM, the API throws `OverlappingFileLockException`.

If using shared locks for readers, remember that **not every reader automatically acquires a lock**: `Files.readAllBytes(path)` or `FileChannel.read(...)` does not "acquire a shared lock" for you. Coordination is reliable only when all participating parties use and adhere to the same rule.

## 3. Lock Regions Are Byte Ranges, Not Whole-File by Default

Primary signatures:

```java
FileLock lock(long position, long size, boolean shared) throws IOException;
FileLock tryLock(long position, long size, boolean shared) throws IOException;
```

- `position` is the **starting byte offset**, from `0`; must be non-negative.
- `size` is the number of bytes in the region; must be non-negative and `position + size` must not overflow into a negative value.
- For `size > 0`, the lock covers the half-open region **`[position, position + size)`**. The byte at the end index is **not included** in the region.
- `size == 0` has special meaning: it requests a lock from `position` through the end of the file space per the API contract, even if the file later grows or shrinks. The returned lock has size `Long.MAX_VALUE - position`.
- A lock region **does not have to lie within the current file size**. For instance, an 8-byte file can still have region `[100, 200)` locked on a supporting filesystem.
- A region with positive size is **fixed** once granted. If `[0, 100)` is locked and the file later grows from 20 bytes to 500 bytes, the portion `[100, 500)` lies outside the acquired lock region.

Region examples:

| Held Lock | Next Requested Region | Overlaps? | Explanation |
| --- | --- | --- | --- |
| `[0, 10)` | `[5, 15)` | Yes | Shares bytes `5..9` |
| `[0, 10)` | `[10, 20)` | No | Adjacent regions; endpoint `10` is outside the first region |
| `[100, 200)` | `[0, 100)` | No | End of the second region equals the start of the first |
| `[100, 200)` | `[199, 201)` | Yes | Shares byte `199` |
| `[50, 60)` | `[55, 56)` | Yes | Smaller region lies inside larger region |

`FileLock.overlaps(position, size)` checks geometric overlap between a **`FileLock` object's** region and the passed range. It **does not acquire another lock**, does not inspect other processes, and does not indicate whether the lock is still valid: to check the lock's own state, use `isValid()`.

### Distinguishing Byte Offsets and Records

If each record has a fixed size of 16 bytes, the `i`-th record (0-based) resides at `[i * 16, (i + 1) * 16)`. Locking a record uses:

```java
// Illustrated snippet: channel must be opened with appropriate permissions.
long offset = Math.multiplyExact(recordIndex, 16L);
try (FileLock lock = channel.lock(offset, 16, false)) {
    // Read/modify/write the record at offset while the lock remains valid.
}
```

`recordIndex` must be non-negative and the multiplication must not overflow. Record size is measured in **bytes**, not Unicode character count. For variable-length records, an explicit offset/length index or clear framing is required; locking 16 bytes when a record actually spans 50 bytes will not protect the entire record.

For files that can grow unpredictably, choose a locking strategy covering the region about to be appended or use a separate lock coordinating metadata/offsets. **Do not assume an existing lock automatically expands as the file grows**, except when requesting a region through EOF using `size=0` per contract.

## 4. How Do `FileChannel.lock` and `tryLock` Differ?

| API | Acquisition Behavior | When Another Process Holds an Overlapping Lock | When an Overlapping Lock Exists in the Same JVM |
| --- | --- | --- | --- |
| `channel.lock()` | Waits to acquire an **exclusive lock** for the entire file range (`0` to `Long.MAX_VALUE`) | May **block** until granted, the channel is closed, or the thread is interrupted | `OverlappingFileLockException` |
| `channel.lock(p, n, shared)` | Waits to acquire the exact requested region/type | May block | `OverlappingFileLockException` |
| `channel.tryLock()` | Attempts immediate whole-file exclusive lock | Returns **`null`** when conflicting with another process's lock | `OverlappingFileLockException` |
| `channel.tryLock(p, n, shared)` | Attempts immediate lock for the requested region/type | Returns **`null`** when conflicting with another process's lock | `OverlappingFileLockException` |

`tryLock` is often useful when an application wants to report "file is in use" or schedule a later retry rather than waiting indefinitely. It is **not** a promise to always return within a bounded time if the filesystem/OS itself stalls, and it can still throw exceptions for non-contention failures.

`lock` can block when another process holds a conflicting lock. If the waiting thread is interrupted, `FileLockInterruptionException` may be thrown; if the channel is closed by another thread, `AsynchronousCloseException` may occur. When designing a server, avoid letting a worker thread block indefinitely on a lock if latency has an SLA; consider `tryLock` with an application-managed deadline/backoff or an appropriate resource-coordination mechanism.

**Permission requirements:**

- Requesting a shared lock on a channel opened only for `WRITE` can throw `NonReadableChannelException`.
- Requesting an exclusive lock on a channel opened only for `READ` can throw `NonWritableChannelException`.
- Appropriate file access permissions and OS policies are also required; `AccessDeniedException`/`IOException` can occur even when Java open modes are valid.
- Some filesystems/providers lack support for the required mechanism or impose range restrictions. Avoid claiming "every operating system definitely allows every region".

## 5. Java 17+ Example Verifying Byte Regions and Overlapping Locks in One JVM

This program creates an 8-byte temporary file, opens two separate `FileChannel` instances to the **same file**, requests an exclusive lock on `[0, 4)`, tests region overlap, and tries another lock on `[4, 8)`.

Create the file `RegionLockDemo.java`:

```java
import java.nio.channels.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

public class RegionLockDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("region-lock-", ".dat");
        try {
            Files.writeString(file, "abcdefgh", StandardCharsets.US_ASCII);
            try (FileChannel first = FileChannel.open(file,
                         StandardOpenOption.READ, StandardOpenOption.WRITE);
                 FileChannel second = FileChannel.open(file,
                         StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                try (FileLock exclusive = first.lock(0, 4, false)) {
                    System.out.println("exclusive=" + !exclusive.isShared());
                    System.out.println("overlaps-3-5=" + exclusive.overlaps(3, 2));
                    System.out.println("overlaps-4-8=" + exclusive.overlaps(4, 4));
                    try {
                        second.tryLock(2, 2, false);
                        throw new AssertionError("Unexpected overlapping lock");
                    } catch (OverlappingFileLockException expected) {
                        System.out.println("same-jvm-overlap=rejected");
                    }
                    try (FileLock adjacent = second.lock(4, 4, false)) {
                        System.out.println("adjacent-lock=" + adjacent.isValid());
                    }
                }
                try (FileLock shared = first.lock(0, 4, true)) {
                    System.out.println("shared-request-acquired=" + shared.isValid());
                    // shared.isShared() may be false if the OS upgrades it to exclusive.
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run on Java 17+ with a local filesystem that supports locking:

```bash
javac --release 17 RegionLockDemo.java
java RegionLockDemo
```

Verified output:

```text
exclusive=true
overlaps-3-5=true
overlaps-4-8=false
same-jvm-overlap=rejected
adjacent-lock=true
shared-request-acquired=true
```

Explanation:

1. `first.lock(0, 4, false)` holds an exclusive lock on region `[0, 4)`; `isShared() == false`.
2. `overlaps(3, 2)` tests region `[3, 5)`, which intersects the first region at byte `3`, so it returns `true`. `overlaps(4, 4)` tests region `[4, 8)`, sharing no bytes, so it returns `false`.
3. `second.tryLock(2, 2, false)` is a request overlapping a lock held by the same JVM; it throws `OverlappingFileLockException`, **not returning `null`**. This holds even when using two separate channels.
4. `second.lock(4, 4, false)` does not overlap, so in the tested environment it can be granted. Upon exiting the `try-with-resources` blocks, both locks are released.
5. After releasing the exclusive lock, the program requests a shared lock `[0, 4)`. The line `shared-request-acquired=true` only confirms that the acquired lock is valid; **it does not assert `isShared() == true`** on every OS. Some platforms may convert shared requests to exclusive locks.

The example output was observed on a file system supporting the respective operations. On an unsupported file store or one with restrictive policies, operations can fail with I/O/permission errors; the remainder of the lesson explains how to handle them. The program intentionally does not create two overlapping shared locks within the same JVM, as doing so would **violate the Java contract**.

## 6. FileLock Lifecycle: Acquiring, Inspecting, Releasing, and Closing

`FileLock` is an object representing an acquired lock, implementing `AutoCloseable`. Its methods include:

- `position()`: starting byte position.
- `size()`: size of the granted lock region; when `size=0` was requested, the object may represent the range up to the end of the file domain per contract.
- `isShared()`: the **actual** lock type, not necessarily equal to the requested parameter on environments without shared-lock support.
- `isValid()`: whether the lock is still valid according to the Java object state.
- `overlaps(p, n)`: tests geometric range overlap.
- `release()` / `close()`: releases the lock; exiting a `try-with-resources` block automatically closes the lock.

A newly granted lock is valid; it becomes invalid when `release` is called, the owning channel is closed, or the JVM exits. **Keeping a `FileLock` reference in a collection does not make the lock outlive the channel**. If the program exits the lock scope too early, another writer may begin operating before your logic finishes.

Usage pattern:

```java
// Illustrated snippet: channel opened READ + WRITE, start/length validated.
try (FileLock lock = channel.lock(start, length, false)) {
    // Only after acquiring the lock should you read/modify/write the record.
    updateRecord(channel, start);
    // You may call channel.force(true) at the commit point if the app needs durability.
} // close() / release() ensures lock release even if operations throw an exception.
```

The snippet above is **not standalone source code**: `updateRecord` is an application-defined business method. When using `tryLock`, check for `null` **before** passing the lock to `try-with-resources` or using it:

```java
// Illustrated snippet for an existing channel and recordRange.
FileLock lock = channel.tryLock(start, length, false);
if (lock == null) {
    // Another process holds a conflicting lock: return an appropriate retry/busy status.
} else {
    try (lock) {
        // Perform the unit of work requiring the lock.
    }
}
```

Closing **a channel that owns a FileLock** invalidates the locks belonging to that channel. Notably, the Javadoc warns that on some platforms, **closing a channel can invalidate other locks held by the JVM on the same file**, even locks acquired from a different channel. Therefore, when using locks to coordinate processes, use **a single channel with a clearly managed lifecycle to hold locks** for that file, avoiding uncontrolled opening/closing of other channels while a lock must remain active. Also do not rely on finalizers or GC to release locks promptly; release explicitly with `try-with-resources`.

### How Long Should a Lock Be Held?

A lock must span **all operations belonging to the logical transaction** being coordinated. For read-modify-write, holding the lock only during `write` is insufficient: two processes could already have read the same old value before either writes. The right approach is to acquire the exclusive lock **before the initial read**, read the current value, compute, write completely, handle durability requirements, and then release.

Do not hold locks across unrelated work such as external network API calls, waiting for user input, UI rendering, or unnecessary CPU work. Long lock durations force other processes to wait and can lead to stalled workflows.

## 7. Java 17+ Example: Exclusive Lock for a File-Backed Counter

This second example shows how to turn the "read → add → write" sequence into an exclusive-locked unit. Each invocation is a separate Java process. The program uses the path passed by the user, so two consecutive runs increment the value from `0` to `1` and then `2`.

Create the file `LockedCounterDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.*;

public class LockedCounterDemo {
    private static long readCounter(FileChannel channel) throws IOException {
        if (channel.size() == 0) return 0;
        if (channel.size() != Long.BYTES) {
            throw new IOException("Invalid counter file size");
        }
        ByteBuffer buf = ByteBuffer.allocate(Long.BYTES);
        long offset = 0;
        while (buf.hasRemaining()) {
            int n = channel.read(buf, offset);
            if (n <= 0) throw new IOException("Incomplete counter");
            offset += n;
        }
        buf.flip();
        return buf.getLong();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java LockedCounterDemo counter.dat");
        }
        Path file = Path.of(args[0]);
        try (FileChannel channel = FileChannel.open(file,
                StandardOpenOption.CREATE, StandardOpenOption.READ,
                StandardOpenOption.WRITE);
             FileLock ignored = channel.lock()) {
            long updated = Math.addExact(readCounter(channel), 1);
            ByteBuffer buf = ByteBuffer.allocate(Long.BYTES).putLong(updated);
            buf.flip();
            long offset = 0;
            while (buf.hasRemaining()) {
                int n = channel.write(buf, offset);
                if (n <= 0) throw new IOException("Write made no progress");
                offset += n;
            }
            channel.force(true);
            System.out.println("counter=" + updated);
        }
    }
}
```

Compile and run in a directory where `counter.dat` does not yet exist:

```bash
javac --release 17 LockedCounterDemo.java
java LockedCounterDemo counter.dat
java LockedCounterDemo counter.dat
```

Verified output when the file initially does not exist:

```text
counter=1
counter=2
```

Things to observe:

1. `FileChannel.open` with `CREATE`, `READ`, `WRITE` permits reading and writing the same file; `channel.lock()` requests a **whole-file exclusive lock**.
2. The program **reads the counter only after acquiring the lock**, preventing two cooperating processes from reading the same stale value.
3. On the first run, the file is empty so its value is interpreted as `0`; on subsequent runs, the file must contain exactly `Long.BYTES` (8) bytes. A corrupted/partially written file of any size other than 0 or 8 triggers an error.
4. `ByteBuffer.putLong` stores the number in the buffer's default byte order (big-endian); the reader in the same program uses the matching `getLong`. Do not confuse this binary layout with decimal ASCII digits in a text file.
5. `channel.write(buf, offset)` uses an absolute offset and loops until the buffer is drained. `force(true)` is called **before releasing the lock and printing success**, to request synchronization of file contents and metadata under Java's contract.
6. `try-with-resources` releases the lock and closes the channel whether execution succeeds or throws an exception.

**Important limitation:** This is an example of **cooperating process coordination**, not a full crash-safe transaction mechanism. If the program or OS fails midway through writing the 8 bytes, the value may be partially updated; `force` does not turn an 8-byte write into an atomic transaction. Production deployments require checksums, a journal/WAL, versioned records, recovery, or a database if power loss must never corrupt the counter. Furthermore, every process must obey the file lock; a process ignoring advisory locks can corrupt the data. If two instances are launched concurrently, console output ordering is not guaranteed, though each process follows the same locking protocol on supporting environments.

## 8. Why FileLock Is Not Meant for Synchronizing Threads in the Same JVM

`FileLock` instances are **held on behalf of the entire JVM**. According to the Javadoc, locked regions held within one JVM must not overlap; this applies even when acquired on two different `FileChannel` instances for the same file. Therefore:

```java
// Illustrates a logic error; channelA/channelB point to the same file.
FileLock first = channelA.lock(0, 100, true);
FileLock second = channelB.lock(0, 100, true); // OverlappingFileLockException
```

The snippet above is an example that **should not be used as a synchronization solution** (and leaves variables undeclared and locks unclosed); it illustrates why two Java threads cannot rely on "shared file locks" the way multiple processes do.

For **threads within a single JVM**:

- Use `synchronized`, `ReentrantLock`, `ReadWriteLock`, or a single dedicated owner worker to protect the business unit of work on a record.
- If multiple concurrent readers are desired, use an application-level `ReadWriteLock`: multiple threads hold the read lock while a writer holds the write lock; do not attempt to acquire multiple overlapping `FileLock` instances inside the JVM.
- For processes outside the JVM, hold **one OS-level FileLock** representing the inter-process protocol; inside the JVM, still use thread/record locks where needed.
- `FileChannel` synchronizes certain position-related I/O calls, but that **does not** turn a `read → compute → write` sequence into a safe transaction.

For example, if two threads increment a counter while the JVM already holds an exclusive `FileLock`, **both threads can still race with each other inside the JVM** unless guarded by a mutex or single-owner design. `FileLock` only addresses coordination **outside** the JVM.

## 9. Advisory vs. Mandatory: Differences Across OS and Filesystems

Java file locking maps to the native locking subsystem. Whether access is actually blocked depends on the OS, filesystem, network mount, and configuration.

| Context | What to Expect |
| --- | --- |
| Linux / Unix with a supporting local filesystem | Region locks may be **advisory**: uncooperative programs can still open/read/write the file region. Do not assume a lock held by JVM A blocks every `write` call from JVM B if JVM B ignores the protocol. |
| Windows with an appropriate filesystem | Some region-locking mechanisms may enforce conflicting OS read/write operations; file-open sharing policies and permissions can make behavior differ from Unix. Do not build logic assuming "mandatory on every Windows volume". |
| NFS/SMB, network drives | Locking semantics can depend on the server, network partitions, leases/reconnects, and mount options. Disconnect/stale-lock scenarios must be tested separately. |
| Docker/containers / shared volumes | Containers may use host FS, overlay FS, network mounts, or different user permissions. Two containers can coordinate only if the backend/filesystem genuinely supports the same locking mechanism. |
| Virtual/in-memory filesystems / custom providers | Locking capabilities may be absent or behave differently; test on the exact provider. |

For portability, **treat FileLock as advisory** and require every reader/writer to honor the application locking contract. Never claim that locking a byte region grants read/write permissions on its own or blocks all access from an uncooperative program.

Some OSes impose restrictions on file mapping: acquiring a mandatory lock on a memory-mapped file region may fail, or mapping after acquiring a lock may be rejected. When combining `MappedByteBuffer` and `FileLock`, test directly on the target filesystem; do not assume the two APIs are always compatible.

### Do Not Treat a Lock as "Full Detection of Processes Opening the File"

A successful `tryLock()` only means the JVM acquired a lock region under the OS mechanism. It **does not** prove no other process has the file open, no reader is inspecting its contents, or no out-of-protocol writer exists. Conversely, failing with an exception may stem from permissions, OS capabilities, or channel state rather than "someone else holds the lock".

## 10. Data Durability: Locking Does Not Replace FileChannel.force

These are two distinct goals:

- **Locking:** coordinates permission to perform concurrent operations among cooperating parties during the lock-holding interval.
- **Durability:** once the application reports a transaction complete, whether the data survives a crash under the storage contract.

`channel.force(true)` requests synchronization of file content and metadata within `FileChannel`'s contract, but **does not lock data**. `FileLock` reduces contention among cooperating processes, but **does not flush data to disk**.

Common workflow for read-modify-write on a local file:

```text
Request exclusive lock on the appropriate record region
          |
          v
Read data inside the lock
          |
          v
Compute and write all bytes
          |
          v
force(true) if data durability is required
          |
          v
Report success only when the commit contract completes
          |
          v
Release the lock
```

Even with this workflow, **durability and recoverability are not absolute**: Java offers different guarantees on remote storage, directory entries have separate contracts, and a crash midway through a multi-step record can leave a partial state. For WAL/databases, the commit mechanism is more complex than one lock and one `force`.

Key point to remember: calling `force` while holding a `FileLock` is useful when guarding commit boundaries among **cooperating processes**; there is no rule that `FileLock` automatically calls `force` or that `force` acquires a lock.

## 11. Errors and Exceptions to Handle

| Exception / Result | Common Cause | Handling Approach |
| --- | --- | --- |
| `tryLock(...) == null` | An overlapping lock is held by **another process**. | Return busy status, retry with backoff/deadline, or enqueue per requirements. |
| `OverlappingFileLockException` | The current JVM already holds or is waiting for an overlapping lock on the same file. | Fix ownership/region locking inside the JVM; do not loop-retry endlessly as with `null`. |
| `NonReadableChannelException` | Shared lock requested on a non-readable channel. | Open channel with `READ`, check file/OS permissions. |
| `NonWritableChannelException` | Exclusive lock requested on a non-writable channel. | Open channel with `WRITE`, check file/OS permissions. |
| `IllegalArgumentException` | Negative `position` or `size`, or invalid arithmetic overflow in range sum. | Validate offset and length; use `Math.addExact` / `Math.multiplyExact` when computing regions. |
| `ClosedChannelException` | Channel already closed when calling lock/tryLock. | Centralize channel lifecycle management and avoid use after close. |
| `FileLockInterruptionException` | Thread interrupted while waiting on a blocking lock request. | Follow cancellation/shutdown policy; never swallow the error and pretend the lock was acquired. |
| `AsynchronousCloseException` | Channel closed by another thread while waiting or performing I/O. | Abort/recover lifecycle properly; do not treat the lock as held. |
| `IOException` / file store error | Native I/O, permission, mount, network, device, or platform-support error. | Log path, lock region, operation, and apply proper retry policy without corrupting existing data. |

Do not catch every exception and continue reading/writing as if the lock were granted. With `tryLock`, `null` specifically means **failed to acquire due to contention outside the JVM**; exceptions represent distinct conditions requiring separate analysis. When `lock` is interrupted or the channel closes, never assume the lock was acquired.

### Deadlock Issues with Multiple Regions

Suppose a transaction must lock records A and B:

- Process 1 holds A and waits for B.
- Process 2 holds B and waits for A.

If both use blocking `lock`, they can get stuck in an inter-process deadlock. To avoid this:

1. Standardize lock acquisition order (e.g., ascending byte offset).
2. Do not hold one lock and wait indefinitely without a timeout for another lock.
3. If using `tryLock` and failing to acquire all required locks, release any already-held locks and retry per an appropriate policy.
4. Avoid calling external services or waiting for user input while holding multiple file locks.

Some OSes provide native deadlock detection, but **Java FileLock does not promise to resolve business-logic deadlocks for you**.

## 12. Design Checklist

Before deploying a file-sharing system:

1. **Who participates?** Multiple threads in one JVM, multiple JVMs/processes, or both? Threads use application mutexes/locks; processes use `FileLock` if all parties cooperate and the OS supports it.
2. **What is the lock region?** Where do byte offset and length come from? Fixed or variable-length records? Can regions overlap or the file grow?
3. **Shared or exclusive needed?** Readers need concurrent reading across processes; writers/read-modify-write need exclusive. Shared locks may be upgraded to exclusive by the system.
4. **Does the channel have the right permissions?** `READ` for shared, `WRITE` for exclusive; does OS policy allow locking?
5. **Are `null` and exceptions handled separately?** `tryLock` encountering contention from another process returns `null`, while same-JVM overlap throws `OverlappingFileLockException`.
6. **Is the lock lifecycle clear?** Acquire before the protected read, hold until writes/`force` finish per contract, release in `try-with-resources`.
7. **Are other channels being closed?** On some OSes, closing any channel to the same file can drop other locks held by the JVM; maintain a single file/lock owner.
8. **Could uncooperative processes exist?** Advisory locks require every reader/writer to obey the protocol; a successful `tryLock` does not prove nobody else is accessing the file.
9. **Is durability required?** If so, use `force` and a recovery protocol suited to the storage type; a lock is not a flush.
10. **Test in the target environment:** local/network filesystem, Windows/Linux/macOS, containers/VMs, user permissions, process-crash scenarios, timeouts, and network disconnects.
11. **Measure lock contention cost:** overly coarse lock granularity hurts throughput; overly narrow regions lose protection. Test with multiple real processes rather than threads alone.
12. **Is there recovery for mid-write crashes?** Use verifiable record formats, WAL, atomic replace, or a storage engine when data corruption is unacceptable.

### Self-Check Questions

**1. If two processes only read region `[0, 10)`, can they request shared locks concurrently?**

Under shared-lock semantics, overlapping requests from multiple processes can coexist if the platform supports it and all parties follow the protocol. Some OSes may promote shared to exclusive, so actual concurrency varies.

**2. Can two channels in the same JVM always acquire shared locks on the same region?**

**No.** The Javadoc forbids overlapping `FileLock` instances within the same JVM, even when both request shared locks; `OverlappingFileLockException` is thrown. Use `ReadWriteLock`/mutexes inside the JVM.

**3. If `[0, 100)` is locked, does requesting `[100, 200)` overlap?**

**No.** Regions are half-open: byte `100` does not belong to the first lock.

**4. How does `tryLock` returning `null` differ from `OverlappingFileLockException`?**

`null` indicates lock contention from **another process**; `OverlappingFileLockException` indicates an overlapping lock already held or an overlapping request waiting within the same JVM.

**5. If a file is 8 bytes long and the program locks `[100, 200)`, must the lock fail?**

**No.** The contract allows locking regions beyond the current file size, provided the system supports it. If the file grows later, a fixed-size lock still covers only the specified bytes.

**6. Why aren't acquiring a FileLock and writing data enough to guarantee power-loss safety?**

Because `FileLock` manages access coordination and does not instruct data to be flushed to the physical device. You need `force` and a recovery protocol suited to the OS/filesystem, while also accounting for partial writes.

**7. Can `FileLock` be treated as security blocking any process from reading a file?**

**No.** It is a file I/O coordination mechanism that may be advisory. Access control belongs to filesystem ACLs/modes and OS policies; uncooperative processes can ignore locks on some platforms.

## Official Documentation

- [Java SE 21 — FileLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): shared/exclusive locks, lifecycle, `isShared`/`isValid`/`overlaps`, advisory/mandatory semantics, and JVM restrictions.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): `lock`/`tryLock`, byte regions, `size=0` parameter, exceptions, and `force`.
- [Java SE 21 — OverlappingFileLockException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/OverlappingFileLockException.html): overlapping locks within the same JVM.
- [Java SE 21 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): locking APIs in asynchronous I/O with callbacks/`Future` and platform limitations.

Bottom line: **exclusive/shared locks define read/write coordination rules across processes; `position` and `size` specify the exact byte region; file locks do not replace intra-JVM thread mutexes; and ensuring data survives crashes additionally requires `force` alongside proper update and recovery protocols.**