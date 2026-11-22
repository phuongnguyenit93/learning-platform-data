# File Locks Are JVM-Scoped and Do Not Replace Thread Locks

## 1. Two Kinds of Contention When Accessing a File

In Java NIO, `FileLock` is used to coordinate access to a file or byte region of a file, especially when **multiple processes** share interest in a resource. However, a Java application can also run **multiple threads within the same JVM**. The two problems require different mechanisms:

- **Intra-JVM synchronization:** coordinates read–modify–write operations across threads, protects Java objects, and establishes memory happens-before relationships. Use `synchronized`, `ReentrantLock`, or an appropriate concurrency primitive.
- **Inter-process coordination:** uses `FileChannel.lock(...)`/`tryLock(...)` to request a byte-region lock, subject to filesystem/OS capabilities. Every participating program must adhere to the same locking protocol, especially when locks are advisory.

A file lock is held **on behalf of the entire JVM**. It is not a monitor or a mutex for individual Java threads. Therefore, per the `java.nio.channels.FileLock` contract, **file locks are not suitable for controlling file access among threads within the same JVM**.

~~~text
                  SAME JVM A                             JVM B
      +--------------------------------+             +----------+
      | Thread A       Thread B        |             | Process B|
      |    \              /            |             +-----+----+
      |     \            /             |                   |
      |   synchronized / ReentrantLock |                   |
      |     protects critical section  |                   |
      |                |               |                   |
      |         FileChannel.lock() ----+-------+-----------+
      +--------------------------------+       |
                                     Operating system / filesystem
                               file lock capable of process coordination
~~~

**A file lock does not automatically lock Java variables, collections, or buffers.** Nor does a file lock guarantee that non-JVM applications will obey it if the operating system implements advisory locking.

## 2. FileChannel and FileLock APIs

Primary `FileChannel` methods:

~~~java
FileLock lock() throws IOException;
FileLock lock(long position, long size, boolean shared) throws IOException;

FileLock tryLock() throws IOException;
FileLock tryLock(long position, long size, boolean shared)
        throws IOException;
~~~

These are **API signature illustrations**, not a standalone runnable program.

`lock()` requests an exclusive lock on the byte region starting at offset 0 with length `Long.MAX_VALUE`. `lock(position, size, shared)` requests a specific region:

- `position` is the non-negative starting byte offset.
- `size` is the non-negative length of the byte region; offset and length must be valid.
- `shared = false` requests an exclusive lock.
- `shared = true` requests a shared lock, if supported by the platform/provider. If shared locks are unsupported, the provider may grant an exclusive lock; use `FileLock.isShared()` to determine the actual lock type granted.

`FileLock` provides `position()`, `size()`, `isShared()`, `isValid()`, `release()`, and `channel()`. Do not confuse `FileLock.position()` with `FileChannel.position()`: the former indicates the start of the **locked region**, while the latter indicates the current **relative read/write position**.

### Differences Between lock and tryLock

| State | `lock(...)` | `tryLock(...)` |
| --- | --- | --- |
| Lock can be granted | Returns `FileLock` | Returns `FileLock` |
| Conflicting lock held by another process | May block (or fail on interruption/error) | Returns `null` if it cannot be granted immediately |
| Lock region overlaps an already-held or pending lock **in the same JVM** | `OverlappingFileLockException` | `OverlappingFileLockException` |
| Channel lacks permission or I/O error occurs | Corresponding exception | Corresponding exception |

**Do not confuse `tryLock() == null` with every form of contention.** When the current JVM itself holds an overlapping lock, `tryLock` throws `OverlappingFileLockException` rather than returning `null` for a thread to silently retry.

## 3. Where Does JVM Scope Show Up?

Suppose a JVM opens two separate `FileChannel` instances to the same file:

~~~text
FileChannel A ── lock [0, 100) ── acquired
FileChannel B ── tryLock [0,100) ── overlapping region, same JVM
~~~

An attempt to lock an overlapping region on B will be detected and throw `OverlappingFileLockException`. This can happen even when A and B belong to two different threads. The JVM **does not** treat each channel or each thread as an independent lock owner for file-lock overlap purposes.

Byte lock regions are represented as half-open intervals:

~~~text
A: [0,100)       includes offsets 0 through 99
B: [100,200)     does not overlap A
C: [50,150)      overlaps both A and B
~~~

Two non-overlapping regions can be locked independently as supported by the provider. Locks do not have to lie solely within the existing file size. For example, locking `[0, Long.MAX_VALUE)` can be acquired even when the file is currently empty.

Intra-JVM overlap detection **does not** turn `FileLock` into an internal mutex, because:

1. Another thread in the same JVM is **not automatically blocked by a monitor** when reading/writing data or mutating program state.
2. If that thread requests an overlapping lock, it can **receive an exception immediately** instead of queuing up as with `ReentrantLock.lock()`.
3. File locks do not provide full happens-before relationships for all Java variables manipulated by threads.
4. Another thread might use another channel without obeying the locking protocol; the degree to which direct access is prevented depends on the OS/provider.

## 4. Java 17+ Example: Two Channels in One JVM

This program uses a temporary file with two channels in the **same Java process**. It acquires a lock using the first channel, attempts to lock an overlapping region using the second channel, and then releases the first lock to demonstrate that the region can be re-acquired.

Save as `JvmFileLockDemo.java`:

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class JvmFileLockDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lock-demo-", ".bin");

        try {
            try (FileChannel first = FileChannel.open(
                        file, StandardOpenOption.READ, StandardOpenOption.WRITE);
                 FileChannel second = FileChannel.open(
                        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

                try (FileLock held = first.lock()) {
                    System.out.println("first lock valid: " + held.isValid());

                    boolean rejected = false;
                    try {
                        FileLock unexpected = second.tryLock();
                        if (unexpected != null) {
                            unexpected.release();
                        }
                    } catch (OverlappingFileLockException ex) {
                        rejected = true;
                    }
                    System.out.println("same JVM overlap rejected: " + rejected);
                }

                try (FileLock after = second.tryLock()) {
                    System.out.println("lock after release: "
                            + (after != null && after.isValid()));
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac JvmFileLockDemo.java
java JvmFileLockDemo
~~~

Stdout on a default file system supporting exclusive file locks, with no other process contending on the temp file:

~~~text
first lock valid: true
same JVM overlap rejected: true
lock after release: true
~~~

Explanation:

1. Both channels point to the same temp file and coexist within one JVM.
2. `first.lock()` acquires an exclusive lock on the default whole-file range, and `held.isValid()` is `true`.
3. `second.tryLock()` requests an overlapping lock; the JVM detects the overlapping lock and throws `OverlappingFileLockException`.
4. `try-with-resources` closes `held` (releasing the lock). Afterward, `second.tryLock()` acquires a new lock.
5. The temp file is cleaned up in `finally`; channels and locks are closed in proper order.

This example intentionally **does not** spawn a second thread: two channels in the same JVM suffice to observe the overlap behavior. Understanding multi-threaded real-world scenarios requires adding internal locking as covered in the following sections. If the filesystem does not support locks or process permissions are insufficient, the result may be an I/O exception instead of the stdout above.

## 5. Why FileLock Does Not Replace Synchronization Between Threads

Consider two threads appending data concurrently:

~~~text
File currently has 100 bytes

Thread A: size() returns 100
Thread B: size() returns 100
Thread A: position(100), write(10 bytes)
Thread B: position(100), write(20 bytes)

The two writes can overlap and lose a record.
~~~

With a shared channel, `position(...)` and `write(...)` calls can even interleave. With two separate channels, both observing `size=100` does not reserve separate write space either. If both try to acquire overlapping file locks in the same JVM, one thread can receive `OverlappingFileLockException` rather than automatically queuing.

Proper synchronization here protects the **entire logical operation** with the same mutex that every participating thread must use:

~~~java
private final java.util.concurrent.locks.ReentrantLock mutex =
        new java.util.concurrent.locks.ReentrantLock();

void performUpdate() {
    mutex.lock();
    try {
        // Read existing data, compute offset, modify, and write.
        // Every thread in the same JVM must go through this same mutex.
    } finally {
        mutex.unlock();
    }
}
~~~

This is a code fragment inside a class without `main`.

`synchronized` on a shared object can protect a similar critical section. `ReentrantLock` fits when you need `tryLock`, timeouts, interruptible lock acquisition, or custom wait policies. Most importantly, **threads must share the same lock instance**. Creating a `new ReentrantLock()` on every call prevents threads from coordinating.

If Java state such as a `HashMap`, cache, counter, buffer, or record list is also modified, a file lock does not replace the thread-safety rules for those objects.

## 6. When You Need Both Intra-JVM and Inter-Process Coordination

A common pattern uses **two-tier** coordination:

1. Acquire the shared mutex for threads inside the JVM.
2. Open the channel with the proper mode, then acquire the file lock according to the region/protocol accepted by external processes.
3. While holding both, execute the complete read–modify–write sequence.
4. Release the file lock, close the channel, and then release the mutex in `finally`.

Example class using one shared instance for all threads writing to the same file:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.locks.ReentrantLock;

final class CoordinatedAppender {
    private final Path file;
    private final ReentrantLock inProcess = new ReentrantLock();

    CoordinatedAppender(Path file) {
        this.file = file;
    }

    void append(byte[] record) throws IOException {
        inProcess.lock();
        try {
            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.CREATE, StandardOpenOption.WRITE)) {
                try (FileLock ignored = channel.lock()) {
                    channel.position(channel.size());
                    ByteBuffer bytes = ByteBuffer.wrap(record);
                    while (bytes.hasRemaining()) {
                        if (channel.write(bytes) == 0) {
                            throw new IOException("No write progress");
                        }
                    }
                }
            }
        } finally {
            inProcess.unlock();
        }
    }
}
~~~

This is an **illustrative class**, not a program with `main`. Several limitations must be understood clearly:

- Within the same JVM, **threads must share the same `CoordinatedAppender` or the same mutex for that file**. Creating multiple instances with separate mutexes breaks coordination guarantees.
- Any other process wanting to coordinate must **itself use a compatible file lock**; on advisory systems, a non-compliant process can still operate on the file.
- `APPEND` is not used in this pattern: the write position is chosen after `size()` while holding the lock.
- This pattern does not automatically provide transactional recovery if a crash happens mid-record; real applications may need a length-prefix, checksum, commit marker, and `FileChannel.force(...)` when durability is required.
- If multiple threads hold different locks, enforce a consistent lock-acquisition order to reduce deadlock risk.

The two tiers address two separate concerns. The mutex protects critical sections and state within one JVM; the file lock coordinates with external processes when the provider and participating programs support it.

## 7. Operating System and Filesystem Limitations

### Advisory vs. Mandatory

On some operating systems/filesystems, file locks are **advisory**: only processes actively participating in the protocol respect one another. On other platforms, certain operations are enforced by the OS with mandatory semantics. **Java does not promise that any external process will be blocked from all read/write operations.**

Therefore, file locks are not an access-control system or a general security boundary. If a file holds sensitive data, use proper permissions and dedicated security mechanisms.

### Shared and Exclusive Locks

Exclusive locks typically serve file updates. Shared locks typically serve multiple concurrent readers, though actual support depends on the provider/OS. A shared request may be fulfilled with an exclusive lock; `FileLock.isShared()` identifies the granted type.

### Locks and Closing Channels

`FileLock` implements `AutoCloseable`, allowing `try (FileLock lock = channel.lock())` for automatic release. If the channel is closed, the lock is released and `lock.isValid()` returns `false`.

**Important note:** on some platforms, closing any channel to the same file within the same JVM can release all file locks held by the JVM on that file, including locks created from other channels. Hence, avoid arbitrarily opening and closing channels to the same file while still relying on a lock; manage channel lifecycles centrally.

### Network Filesystems and Different Providers

NFS/SMB, virtual filesystems, specialized providers, and different OSes can vary in lock semantics, granularity, and errors. Where a provider lacks support, `IOException` or an appropriate exception may occur. Test against the actual deployment filesystem before relying on file locks to protect critical data.

## 8. Errors and Appropriate Responses

| Case | Possible Outcome |
| --- | --- |
| Overlapping lock region within the same JVM (already held or waiting) | `OverlappingFileLockException` |
| `tryLock` conflicts with a lock from another process | `null` |
| Exclusive lock requested on a non-writable channel | `NonWritableChannelException` |
| Shared lock requested on a non-readable channel | `NonReadableChannelException` |
| Channel already closed | `ClosedChannelException` |
| Thread interrupted while waiting on `lock` | `FileLockInterruptionException` |
| Already released or channel closed | `FileLock.isValid() == false` |

Exceptions must be caught and handled intentionally. For instance, if a thread receives `OverlappingFileLockException` due to another operation in the same JVM, repeatedly calling `tryLock` in a loop will not fix the design issue: internal mutex coordination is needed.

A non-blocking attempt pattern:

~~~java
try {
    FileLock lock = channel.tryLock();
    if (lock == null) {
        // Another process holds a conflicting lock.
    } else {
        try (lock) {
            // Lock acquired.
        }
    }
} catch (OverlappingFileLockException ex) {
    // This JVM itself holds or is waiting for an overlapping lock region.
}
~~~

Illustrative snippet inside a method with an open `channel` and appropriate imports.

## 9. Common Mistakes

**Mistake 1:** using `FileLock` to replace `ReentrantLock` across two threads. An overlapping-region request can throw `OverlappingFileLockException` instead of blocking.

**Mistake 2:** assuming `tryLock()` always returns `null` when a lock is unavailable. You must distinguish inter-process contention from intra-JVM overlap.

**Mistake 3:** creating a new mutex on every call; the two threads do not actually share a lock object to coordinate with.

**Mistake 4:** assuming a file lock establishes memory visibility for all Java variables. You need `synchronized` or appropriate Java concurrency utilities.

**Mistake 5:** holding a file lock while other code arbitrarily opens/closes channels to the same file. On some OSes, closing a channel can invalidate held locks.

**Mistake 6:** assuming file locks block every process. Advisory locks require all parties to cooperate.

**Mistake 7:** locking incompatible byte ranges across processes. If A locks `[0,100)` while B only locks `[100,200)`, they are not protecting a shared region.

**Mistake 8:** forgetting to release in `finally` or `try-with-resources`; letting an exception leave a mutex unreleased.

**Mistake 9:** believing a file lock is a transaction. A lock does not automatically roll back partial writes, verify checksums, or guarantee durability on storage devices.

## 10. Self-Check Questions

1. Two threads in the same JVM want to lock the same byte region. Will the second thread always wait? **No.** It may receive `OverlappingFileLockException`.
2. What does `tryLock()` returning `null` mean? **The lock could not be acquired immediately due to a conflict with another process.** Intra-JVM conflicts throw a distinct exception.
3. Does a file lock automatically synchronize a `HashMap` modified by two threads? **No.** Java's thread-safety rules are still required.
4. Do two `FileChannel` instances pointing to the same file within one JVM have separate lock scopes? **No**, with respect to JVM overlap detection.
5. Is another process that does not participate in the locking protocol guaranteed to be blocked from writing? **This cannot be guaranteed across all OSes/filesystems**, especially with advisory locks.
6. In what order should the two-tier pattern acquire locks? **Intra-JVM mutex first, then file lock**; release in reverse order consistently across all code paths.
7. Is a shared lock always granted as shared? **No.** Check `FileLock.isShared()`.
8. Why use `try-with-resources` for `FileLock`? **To release the lock promptly even when operations fail.**

**Key takeaway:** `FileLock` is **JVM-scoped** with respect to ownership and overlap detection, making it useful in inter-process file coordination protocols. It does **not** replace `synchronized` or `ReentrantLock` for coordinating threads, protecting program state, or turning a read–modify–write sequence into a Java critical section.