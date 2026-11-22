# Releasing FileLock When Closing Resources in Java NIO

When multiple programs operate on the same file concurrently, Java NIO provides `FileChannel.lock()` and `tryLock()` to request a **lock on a byte region of a file**. The `java.nio.channels.FileLock` object represents the granted lock. A lock requires a **clear lifecycle**: acquire the lock → perform work within the protected scope → release the lock → close the channel. If the resource is closed early, the lock also becomes invalid; if not released promptly, another program may block for a long time or fail to acquire the lock.

Key point: **a `FileLock` is released when `release()`/`close()` is called, when the channel that granted the lock is closed, or when the JVM terminates — whichever occurs first.** However, when coordinating multiple threads/processes and across different filesystems, you must also understand lock scope, OS rules, and exception handling.

## 1. Roles of FileChannel and FileLock

The two objects serve distinct roles:

- **`FileChannel`**: an open handle for reading/writing a file. The channel provides `lock(...)` or `tryLock(...)` to request locks and manage I/O resources.
- **`FileLock`**: a token representing **a currently held lock**, carrying byte range `position()` and `size()`, mode `isShared()`, and state `isValid()`.

A `FileLock` is valid only while the lock still exists and its corresponding channel remains open; `isValid()` reports the lock's state **at the moment of inspection**, not a guarantee that it will remain valid forever afterward.

```text
FileChannel.open(...)
        |
        v
    channel.lock() ------------> FileLock (valid)
        |                            |
        |                            | release() or close()
        |                            v
        |                       FileLock (invalid)
        |
        +-- channel.close() -------> all locks granted from channel are released
                                     (invalid)

JVM terminates -------------------> locks held by the JVM are released
```

Locks do not automatically persist the file durably to the storage device, back up contents, or provide transactions. A properly held lock can still accompany unflushed, un-`force()`d, or partially written data. **Lock management** and **data durability management** are two complementary responsibilities.

## 2. Three Ways a Lock Is Released

Under the `FileLock` contract:

| Action | Effect on Lock | Effect on Channel |
| --- | --- | --- |
| `lock.release()` | Releases a valid lock; afterward `isValid() == false`. | Channel remains open unless closed separately. |
| `lock.close()` | Invokes `release()`; suitable for `try-with-resources`. | Channel remains open. |
| `channel.close()` | Releases locks acquired through that channel, rendering them invalid. | Channel closes; cannot be used for further I/O. |
| JVM terminates | Locks held by the JVM are released by the operating system. | All process resources terminate. |

The recommended practice order is **release `FileLock` first, close `FileChannel` second**. Although closing the channel also releases the lock, closing sequentially helps bound the protected region and gives explicit control over release timing.

Once a `FileLock` becomes invalid, do not treat it as proof that the resource is still locked. Reopening the channel later does not make an old `FileLock` token valid again: to obtain a new lock, you must **call `lock()`/`tryLock()` anew**.

**Do not wait for garbage collection to release locks.** Use `try-with-resources` or `finally`. JVM termination is a last-resort cleanup mechanism, not a lock management strategy for long-running applications.

## 3. Standard try-with-resources Pattern: Close Lock Before Channel

A concise, lifecycle-safe pattern:

```java
// Snippet: file is a java.nio.file.Path that exists or will be created.
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    // Perform only the work requiring protection inside this block.
    // If writing data is needed, the channel must have WRITE permission.
}
```

The snippet above is a **fragment**; it requires importing `FileChannel`, `FileLock`, and `StandardOpenOption`. It cannot run standalone because `file` is defined in an outer context.

**Why does declaration order matter?**

1. `try-with-resources` initializes from left to right: open `FileChannel`, then acquire `FileLock`.
2. When exiting the block, Java closes **in reverse order**: calling `lock.close()` first, then `channel.close()`.
3. If the body throws an exception, Java **still** closes both resources. Exceptions thrown during close are recorded via suppressed exceptions; the primary exception is not silently overwritten by a close failure.
4. If `channel.lock()` throws an exception before `FileLock` is created, the already-initialized `channel` resource is still closed automatically.

If you open a channel and call `channel.lock()` but **forget to capture and release the token**, the lock persists until the channel closes. For a long-lived channel (e.g., tied to a service), that can force cooperating processes to wait far longer than intended.

## 4. Complete Java 17+ Example: Explicit release and Release on Channel Close

This example creates a dedicated temporary file, acquires a lock on a `FileChannel`, checks state before and after `FileLock` auto-closes; then acquires another lock and lets channel closure release it.

Save as **`LockLifecycleDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class LockLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lock-lifecycle-", ".bin");
        try {
            FileLock releasedExplicitly;
            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                try (FileLock lock = channel.lock()) {
                    releasedExplicitly = lock;
                    System.out.println("during lock: " + lock.isValid());
                    channel.write(ByteBuffer.wrap(new byte[] {65, 66, 67}));
                }
                System.out.println("after FileLock.close: "
                        + releasedExplicitly.isValid());
            }

            FileLock releasedByChannel;
            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                releasedByChannel = channel.lock();
                System.out.println("before channel.close: "
                        + releasedByChannel.isValid());
                // When the channel closes, the channel's lock is automatically released.
            }
            System.out.println("after channel.close: "
                    + releasedByChannel.isValid());
            System.out.println("bytes: " + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run on JDK 17+ with a filesystem supporting `FileLock`:

```bash
javac -encoding UTF-8 LockLifecycleDemo.java
java LockLifecycleDemo
```

Stdout (verified by running the actual Java program):

```text
during lock: true
after FileLock.close: false
before channel.close: true
after channel.close: false
bytes: 3
```

**Explanation:**

- First, `channel.lock()` requests an **exclusive** lock for the entire default lock region; `isValid()` returns `true` inside the block. `ByteBuffer` holds the three bytes `A B C`, and `channel.write(...)` writes them to the file.
- Upon exiting `try (FileLock lock = ...)`, `lock.close()` automatically calls `release()`. The `releasedExplicitly` token becomes invalid, even though `channel` remains open.
- Second, a new channel is opened on the same file. The new lock `releasedByChannel` is held until `try (FileChannel channel = ...)` ends. `release()` is intentionally omitted here to illustrate **channel closure releasing the lock**.
- After the channel closes, `releasedByChannel.isValid()` is `false`. The file has exactly three bytes because the program only wrote three bytes in the first session.

This example uses a single process running sequentially with no contending writers. If the OS/filesystem does not support the requested lock type, lock acquisition may fail; the program will then throw an exception rather than printing the stdout above.

## 5. Using release() in finally When Not Using try-with-resources

If application structure requires manual management, retain the token and release it in `finally`:

```java
// Snippet: channel is a FileChannel opened with WRITE.
FileLock lock = null;
try {
    lock = channel.lock();
    // Protected operations here.
} finally {
    if (lock != null && lock.isValid()) {
        lock.release();
    }
}
```

This is an illustrative snippet requiring `IOException` to be handled or propagated. `finally` runs even if logic inside `try` throws an exception, though it is **not** an absolute guarantee against process kills or abrupt JVM termination. If `release()` itself throws `IOException`, handle the error deliberately; critical business exceptions must not be obscured in logs.

If the channel is also owned by this method, close the channel in `finally` or `try-with-resources` as well. Do not call `release()` after the channel has already closed expecting to "release again". Per the `FileLock` contract, `release()` on an invalid token performs no real unlock operation, and the API specifies exceptions in certain closed-channel scenarios; the cleanest approach is closing the lock **before** closing the channel.

Using `try-with-resources` usually yields cleaner code and also handles lock acquisition failures during resource initialization.

## 6. When a Lock Remains Active: Critical Section Scope

Example updating a counter in a file:

```text
Correct scope:
acquire lock ──> read old data ──> compute ──> write new data
                                                      |
                                                      v
                                                release lock

Prone to race:
acquire lock ──> read ──> release lock ──> compute ──> write
                              ^                          ^
                              |                          |
                  Another writer can modify the file between the two steps
```

The lock must be held across the **entire read-modify-write sequence** when writers need the operation seen as a single critical section. Locking only the read and closing the lock before the write leaves a race window.

However, **proper lock scope does not mean a transaction**. If the process dies mid-write, partial data may persist even when only one cooperating writer was active at write time. For recoverable data, add record framing/checksums, temporary files, and appropriate commit/rollback strategies.

Avoid holding locks across unrelated time-consuming work such as HTTP calls, waiting for user input, or long sleeps. Precompute whatever can be done outside the critical section, then hold the lock only for reading the latest state and updating.

## 7. lock() and tryLock(): Different Waiting Behavior, Same Release Responsibility

`FileChannel.lock()` is a **blocking** call that waits until the region is locked, the channel is closed, or the waiting thread is interrupted. `tryLock()` **does not wait**: it either returns a `FileLock`, or returns `null` if another program/process already holds a conflicting lock; in other error conditions it may throw an exception.

Safe `tryLock` pattern:

```java
// Snippet: channel opened with WRITE and no overlapping lock exists in this JVM.
FileLock lock = channel.tryLock();
if (lock == null) {
    System.out.println("File đang được tiến trình khác sử dụng");
} else {
    try (lock) {
        // Critical section: runs only while holding the lock.
    }
}
```

Using a resource variable `lock` in `try(lock)` is supported since Java 9 if the variable is final or effectively final; here its value does not change after assignment. Never enter the critical section with a `null` token.

Cases to distinguish:

| Condition | Typical Behavior |
| --- | --- |
| Another process holds a conflicting lock | `lock()` blocks; `tryLock()` returns `null`. |
| Same JVM already holds an overlapping lock on the same file | `OverlappingFileLockException`, even when using a different channel in the JVM. |
| Attempting an exclusive lock on a non-writable channel | `NonWritableChannelException`. |
| Attempting a shared lock on a non-readable channel | `NonReadableChannelException`. |
| Channel already closed | `ClosedChannelException`. |
| Closing the channel while a thread waits on `lock()` | May throw `AsynchronousCloseException`. |
| Interrupting the thread while waiting on `lock()` | May throw `FileLockInterruptionException`; interrupt status is set. |

Do not "fix" `OverlappingFileLockException` with an infinite busy `tryLock` loop. Because `FileLock` is held **at the JVM level**, multiple threads within the same JVM must use a separate application-level synchronization mechanism (`synchronized`, `ReentrantLock`, or a writer queue). File locks are primarily a coordination mechanism **between processes** that honor the locking protocol.

## 8. Whole-File Locks and Byte-Region Locks

`channel.lock()` is equivalent to:

```java
FileLock lock = channel.lock(0L, Long.MAX_VALUE, false);
```

Here `position=0`, `size=Long.MAX_VALUE`, `shared=false`; this is an **exclusive** request. This snippet is illustrative only; `lock` must be closed/released after processing.

When locking a data partition:

```java
// Snippet: lock region [100, 200) using a writable channel.
try (FileLock lock = channel.lock(100L, 100L, false)) {
    // Operate only on the file portion defined by the app's region-locking convention.
}
```

The range is `[position, position + size)`, meaning the end boundary is **excluded** from the locked region. A lock region may extend past EOF; it does not automatically grow file contents. A lock with a fixed `size` does not expand automatically with the file; if the file grows beyond that range, the newly added portion is uncovered.

Helpful `FileLock` methods:

- `position()`: starting position.
- `size()`: size of the locked region.
- `overlaps(start, length)`: checks whether two regions intersect; does not acquire a new lock.
- `isShared()`: confirms whether the granted lock is shared or exclusive. Some platforms may convert shared requests into exclusive locks.
- `acquiredBy()`: returns the channel that granted the lock; for `FileChannel`, `channel()` can also be used.

Do not assume a file can be split into many independent lock regions across every filesystem; native locking constraints vary by platform, especially on network filesystems.

## 9. Pitfall: Closing Another Channel Can Drop Your Lock

This is a platform difference **explicitly warned about by the JDK**: on some systems, **closing a channel to the same file** can release **all file locks held by the JVM on that file**, including locks acquired via a **different channel**.

Conceptual scenario:

```text
channel A ── lock region [0, 100) ──> lockA still expected to be valid
channel B ── same underlying file ──> close channel B
                                        |
                                        v
                On some OSes, lockA may also be released.
```

This is **operating-system-dependent** behavior; there is no fixed deterministic output for this experiment. Do not assume `lockA.isValid() == true` always holds after any other channel closes.

Recommended design guidelines:

1. Within each program, prefer **a single channel owned by one component that requests all locks on the same file**.
2. Clearly define channel ownership and lock ownership; avoid helper functions unexpectedly opening and closing a second channel to a currently locked file.
3. When multiple threads need access, coordinate through a channel-management service or intra-JVM synchronization rather than having each thread open channels and contend on the same lock region.
4. Do not rely on a small test on one OS to guarantee compatibility across all platforms.

Note that closing the channel **that granted the lock** always releases that lock per contract. Whether closing **another channel** affects that lock is the non-portable behavior.

## 10. Shared Locks, Exclusive Locks, and OS Limitations

Two modes:

- **Exclusive lock:** requests exclusive control, preventing cooperating processes from acquiring overlapping shared/exclusive locks while it remains active.
- **Shared lock:** multiple programs can concurrently request shared locks on a region, but they conflict with exclusive requests.

To request a shared lock:

```java
// Snippet: channel must be opened with READ.
try (FileLock lock = channel.lock(0L, Long.MAX_VALUE, true)) {
    System.out.println("shared actually: " + lock.isShared());
}
```

Some platforms do not support shared locks: a shared request may be converted into an exclusive lock. Therefore, check `lock.isShared()` if the actual mode matters to the application. Exclusive locks require write permission on the channel; shared locks require read permission.

**Do not treat FileLock as an absolute security barrier.** On some OSes, locks are *advisory*: uncooperative processes can still read/write the file. On other OSes, locks may enforce mandatory restrictions on file operations; certain configurations/filesystems may restrict simultaneous mapping and locking. When protecting data against unauthorized access, use permissions/ACLs, identity controls, and system boundaries; file locking does not replace them.

Especially on NFS/SMB/network shares, lock granting and revocation can be affected by protocol details and server configuration. Include tests for lock timeouts, reconnects, crashes, and access permissions in the real deployment environment.

## 11. Closing Resources Safely When Exceptions Occur

A file-writing program must handle both **work errors** and **cleanup errors**. With `try-with-resources`, Java closes resources in reverse declaration order. If the `try` body throws an exception and `close()` also throws an exception, the close failure is typically attached to the primary exception as **suppressed**.

Template example:

```java
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    writeRecord(channel);  // May throw IOException.
} // FileLock.close() then FileChannel.close().
```

This is a snippet; `file` and `writeRecord` must be provided by the program. The program does not need a `catch` block just to guarantee lock release. For thorough error logging, you can log `ex.getSuppressed()` alongside the primary exception.

**Notes to avoid logical deadlocks:**

- Do not hold a lock while waiting on another task that also needs a lock on an overlapping region.
- Do not acquire multiple locks across multiple files in arbitrary orders across processes; define a **fixed ordering** to reduce deadlock risk.
- Do not wait indefinitely when the application has a deadline: `lock()` can block. Design deadline-bounded retry/backoff with `tryLock()`, without polling too aggressively.
- If task cancellation is required, handle interrupts and channel closure knowing that a blocking `lock()` operation may be interrupted and throw an exception.

Closing locks promptly reduces resource hold times across the system, provided all protected work has completed first.

## 12. Locks and Data Durability: release Is Not commit

Suppose the program has a single writer holding a valid lock. When executing:

```java
try (FileLock lock = channel.lock()) {
    while (buffer.hasRemaining()) {
        channel.write(buffer);
    }
    channel.force(true);
}
```

this snippet uses an already-declared `channel` and `buffer`. `force(true)` requests that relevant content and metadata updates be pushed to the storage device per `FileChannel`'s contract, with exact guarantees depending on whether the device is **local** or **non-local**.

Clear distinctions:

| Event | What It Does | What It Does Not Do |
| --- | --- | --- |
| `lock.release()` / `lock.close()` | Releases ownership of the lock region. | Does not force data to be flushed/synced to disk. |
| `channel.close()` | Closes the handle and releases the channel's locks. | Does not create a transaction with rollback. |
| `channel.force(false)` | Requests writing relevant content changes to the device. | Does not make multiple writes atomic. |
| `channel.force(true)` | Requests both relevant content and metadata sync. | Does not validate record schema or checksums. |
| `SYNC` / `DSYNC` | File open options requesting synchronous data updates. | Does not replace locking, record framing, or commit protocols. |

If a file holds multiple records, add length prefixes, checksums, versioning, journaling, or a temp-file replacement strategy as required. In systems requiring strong crash consistency, a successful `write` does not mean the entire read-modify-write sequence committed atomically.

Scheduling `force` **before** leaving the critical section can make sense when another writer may proceed only after data synchronization has been requested, though the performance cost can be high. Match the policy to business requirements; forcing on every single record is unnecessary if periodic durability suffices.

## 13. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Another process waits on lock forever | Forgot `release` while channel stays open long, or critical section is too wide. | Use `try-with-resources`, narrow the scope, set deadlines. |
| `isValid() == false` without calling `release()` | Granting channel closed, JVM exited, or system revoked lock. | Review channel lifecycle; acquire a new lock if needed. |
| Lock held yet another process modifies file | OS uses advisory locking or process does not cooperate. | Require all writers to follow protocol; combine with access permissions. |
| `OverlappingFileLockException` | JVM already holds an overlapping lock or another thread is waiting on one. | Use JVM-level synchronization; avoid contending on the same file within one JVM. |
| `tryLock() == null` | Conflicting lock held by another process. | Skip task, report busy, or retry with deadline/backoff. |
| `NonWritableChannelException` | Exclusive lock requested on non-writable channel. | Open channel with `WRITE`. |
| `NonReadableChannelException` | Shared lock requested on non-readable channel. | Open channel with `READ`. |
| `ClosedChannelException` | Channel closed while requesting or using lock. | Manage resource ownership; never use channel after close. |
| Other lock lost when closing secondary channel | Some OSes associate locks per file with broader release semantics. | Use a single lock-managing channel per file in the program. |
| Data still corrupted despite lock | Partial write, crash, missing framing/transaction. | Use proper format and recovery, plus `force` per policy. |

A frequent code-review bug is placing `FileChannel` in a `try-with-resources` block that is too **short** relative to the logic requiring protection, placing critical writes/updates outside after the channel has closed. Having `channel.lock()` in the code is not enough: **when the lock is released determines exactly which code is protected**.

## 14. Practice Exercises

**Exercise 1 — Observing lock state.** Run the `LockLifecycleDemo` example and record the points where `isValid()` transitions `true → false`. Try refactoring the program into a single `try (FileChannel channel = ...; FileLock lock = channel.lock())` form and verify that close order is the reverse of declaration order.

**Exercise 2 — Running two processes.** Write process A to acquire an exclusive lock, wait for a user signal, and then exit `try`. Have process B use `tryLock()` to check before, during, and after A holds the lock. On a supporting filesystem, B will receive `null` while A holds the lock and succeed after A releases it. Avoid fixed sleeps to simulate overlap timing; use explicit test signals/events.

**Exercise 3 — Protecting read-modify-write.** Store a `long` at file offset 0; have two processes concurrently read, add one, and write back. Hold the lock across the entire read + write, then compare with releasing the lock before writing. Why can an individual read or write still succeed while producing the wrong final result?

**Exercise 4 — Region locking.** Divide a file into two non-overlapping byte regions, acquire separate locks for each region, and observe OS behavior. Test `FileLock.overlaps` on intervals `[0, 100)`, `[100, 200)`, and `[50, 150)`. Explain why two regions touching at a boundary do not overlap.

**Exercise 5 — Error mid-critical-section.** After acquiring a lock, deliberately throw a test `IOException`. Verify that `try-with-resources` releases the resources and a cooperating process can acquire the lock afterward. Add logging for suppressed exceptions during resource cleanup.

**Exercise 6 — Durability.** Build a program that writes a complete record with a checksum and calls `channel.force(true)` before `lock.close()`. Explain the difference if you only release the lock without calling `force`, and why even `force` does not turn the write sequence into a transaction.

## 15. Application Readiness Checklist

- File/channel opened with permissions matching the lock mode (exclusive needs `WRITE`, shared needs `READ`).
- Who owns and closes `FileChannel`? Who owns and closes `FileLock`? Is a second channel to the same file opened unexpectedly?
- Is all code requiring synchronization **inside** the critical section? Is a lock held across network calls or long waits?
- Are `try-with-resources`/`finally` used, with lock acquisition/close exceptions handled properly?
- Do multiple threads in the same JVM have their own synchronization? Do separate processes follow the same lock protocol?
- Does the target runtime platform support the requested lock type/region? Do tasks have deadlines or timeout/retry plans?
- Have you distinguished **releasing a lock**, **closing a channel**, **syncing data**, and **transactions**?
- Have you tested recovery procedures if the process crashes after partial writes but before `release()`/`force()`?

## 16. Official References

- [Java SE 21 — FileLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): lock validity conditions, `release()`, `close()`, state, and platform-dependent limitations.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): `lock()`, `tryLock()`, `force()`, region locks, errors, and lifecycle.
- [Java SE 21 — try-with-resources](https://docs.oracle.com/en/java/javase/tutorial/essential/exceptions/tryResourceClose.html): order and mechanics of automatic resource closing in Java.

**Key takeaway:** `FileLock` is an `AutoCloseable` resource. Use `try-with-resources` to release the lock **before** closing the channel; closing the channel that granted the lock also invalidates the lock. Establish clear ownership, avoid casually mixing multiple channels to lock the same file, and never equate lock release with a durable commit.