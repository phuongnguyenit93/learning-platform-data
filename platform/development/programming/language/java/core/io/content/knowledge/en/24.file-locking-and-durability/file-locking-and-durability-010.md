# Consistency Limits on Network File Systems in Java NIO

## 1. The Problem: Do Two Processes Viewing One File Over a Network See the Same Data?

A **network file system** allows multiple machines to access files stored on a server or shared storage service. Familiar examples include **NFS** on Linux/Unix, **SMB/CIFS** in file-sharing environments, and file shares mounted onto application hosts.

Suppose:

~~~text
          Host A                                Host B
      Java writer                            Java reader
        FileChannel                            Files.read...
            |                                       |
     OS page/attribute cache                 OS page/attribute cache
            |                                       |
            +-------------- Network ----------------+
                                 |
                           File server
                                 |
                          Backing storage
~~~

Host A writes `balance=900` and calls `channel.force(true)`, then Host B reads the same mounted path. We must distinguish **three independent questions**:

1. **Visibility:** will Host B immediately see the new version, or still see an older cached version?
2. **Durability:** has the change been persisted durably enough to survive a client, server, or storage crash?
3. **Concurrency/atomicity:** if A and B write concurrently, are lost updates, half-new/half-old records, or wrong lock ordering prevented?

**No single Java NIO method solves all three questions across every network file system.** Java APIs depend on the file-system provider, OS, client caches, network protocol, mount options, and storage server.

This lesson focuses on the consistency limits of `Files.*`, `FileChannel`, `FileLock`, `MappedByteBuffer`, and synchronization modes when files reside on a network file system. Observations specific to NFS do not automatically apply identically to SMB, strongly coherent distributed file systems, or object storage services.

## 2. Three Easily Confused Consistency Aspects

### 2.1. Visibility: Stale Reads Due to Caching

A Java application on Host B may read data from the OS page cache or metadata cache. When caches refresh depends on the protocol and configuration. Calling `Files.readAllBytes(path)` **carries no special meaning of "force the server to return the latest version across all clients"**.

Timeline example:

~~~text
t0  A and B both see version=1
t1  B caches version=1
t2  A writes version=2 and closes the file
t3  B reads again before cache refreshes -> may see version=1
t4  B reopens / cache is revalidated or expires -> may see version=2

Exact timing and behavior at t3/t4 depend on the filesystem,
protocol, mount options, and how the program opens/reads the file.
~~~

If an application requires every client to see a completed write immediately, it needs an **explicit consistency contract** from the storage system. Never infer that solely from sharing the same path name.

### 2.2. Durability: Newly Visible Data Is Not Necessarily Durable

A `write(...)` call may put data into the writer's cache without proving that the data is safely stored on physical media or committed by the server at the required level. Calling `force` has defined meaning for local files, yet **the Java 17 specification does not make the same guarantee for files on non-local devices**.

Even when the server acknowledges receiving data, survival across power loss, device failures, replicas, or multiple failure domains depends on server/storage policies.

### 2.3. Atomicity and Ordering: File Consistency Is Not a Transaction

Writing two fields sequentially:

~~~java
// Illustrative snippet; channel already opened for writing.
channel.write(header);
channel.write(body);
~~~

does not mean every reader on another host will always observe both `header` and `body` as a single atomic change. Each call may write partially, and the two calls may interleave with another writer's operations if uncoordinated.

**A successful I/O operation, cache coherence, atomic rename, mutual exclusion, and durability are distinct properties.** An application must specify each requirement separately.

## 3. NFS Commonly Provides Close-to-Open, Not Absolute Cache Coherence

In many common NFS implementations, the **close-to-open (CTO)** model is used:

1. Client A opens the file and updates its contents.
2. A closes the file; the NFS client has an opportunity to flush pending changes to the server.
3. Client B **opens the file afterward**; client B has an opportunity to revalidate file attributes/state with the server and refresh cached data as needed.
4. B reads the new version, **if** the system honors CTO under those conditions and configuration.

~~~text
Client A: open -> write -> close
                                    Client B: open -> read -> close
                 ^ close-to-open boundary increases visibility likelihood
~~~

**CTO does not mean** every `read` on a long-held open handle immediately sees each byte A just wrote. Nor is B guaranteed to read an atomic snapshot of A's entire ongoing update sequence.

Points requiring special attention:

- NFS may cache **data** and **metadata/attributes** separately; the two caches have different refresh schedules.
- Observed behavior can vary by protocol version, client kernel, and mount options.
- The `nocto` mount option on some NFS clients can disable part of close-to-open behavior.
- The `noac` mount option on Linux NFS reduces attribute caching, **not meaning all data caching is disabled**, nor does it eliminate races.
- Other distributed file systems may provide stronger coherence than standard NFS; consult the exact product documentation.

**Practical takeaway:** When handing off complete data from A to B, it is usually best to structure a boundary of **"writer finishes → close/commit → signal new version → reader reopens/verifies"** under a tested protocol. Even then, this remains an **application workflow**, not an absolute guarantee from Java across all NFS/SMB setups.

## 4. What Confusion Does Metadata Caching Cause?

Operations such as:

- `Files.exists(path)`
- `Files.size(path)`
- `Files.getLastModifiedTime(path)`
- `Files.readAttributes(path, BasicFileAttributes.class)`
- directory traversal via `Files.list(...)` or `DirectoryStream`

may rely on file/directory metadata supplied by the OS or server, and that information may be cached on the client.

For example, Host A renames `ready.tmp` to `ready.dat` while Host B still holds a cached directory listing. Host B **might** not see the new entry at the exact moment the application expects. Observing the new entry is also affected by specific rename and invalidation rules.

An unsafe pattern:

~~~java
// Illustrates logic unsafe against concurrent changes:
if (Files.exists(path)) {
    long size = Files.size(path);
    byte[] bytes = Files.readAllBytes(path);
    // No guarantee that size and bytes come from the same point-in-time snapshot.
}
~~~

Between `exists`, `size`, and `readAllBytes`, the file may be modified, deleted, or replaced. This is **TOCTOU (time-of-check to time-of-use)**; it can happen on local filesystems too, and network/caching layers make observation even subtler.

**Never treat timestamps or sizes as definitive version identifiers.** Timer resolution, client/server clock skew, caching, and same-sized updates can cause such checks to miss changes. When exact version detection is needed, store an explicitly managed **version/counter, checksum, or manifest**.

## 5. `FileChannel.force(...)`: Local Guarantees Do Not Automatically Extend Over the Network

Java 17 defines:

~~~java
// Illustrative code; channel is an open FileChannel.
channel.force(false); // Request persisting content changes.
channel.force(true);  // Request persisting content and metadata.
~~~

Per the `FileChannel.force(boolean metaData)` specification:

- If the file is on a **local storage device**, when `force` returns, updates within the contract scope have been written to the device.
- If the file is **not on a local device**, **no equivalent guarantee applies**.
- `metaData=false` requests syncing content; `metaData=true` includes necessary metadata as well.
- When updates occur through a **memory-mapped buffer**, `FileChannel.force(...)` is **not guaranteed** to force dirty pages modified via the mapped buffer. Use `MappedByteBuffer.force()` for mapped contents.

This **does not mean** calling `force` on NFS/SMB is necessarily useless. It can still issue appropriate write/sync requests to the OS and server. What you must never claim is: **"Java guarantees data survives any network/server crash because `force(true)` returned."**

### `RandomAccessFile` and Synchronous Modes

| API/Mode | Meaning in Java | Limits on Networked Files |
|---|---|---|
| `RandomAccessFile(..., "rw")` | Read/write; no per-write sync required | No per-write checkpoint durability promised |
| `RandomAccessFile(..., "rwd")` | Syncs **content** on updates | Java provides no local-storage-equivalent guarantee on network devices |
| `RandomAccessFile(..., "rws")` | Syncs **content and metadata** on updates | Still subject to remote-storage limitations |
| `FileChannel.force(false/true)` | Explicitly requests content / content+metadata be written to device | Not proof of replica/quorum or server crash recovery |
| `MappedByteBuffer.force()` | Requests syncing changes in mapped region | Post-return guarantee is specified for local storage, not automatically extended remotely |

**SYNC/DSYNC** in `StandardOpenOption` likewise express synchronous update requests, yet should not be treated as bypassing network protocol/server limits. A file provider may lack support for certain options or implement them in its own way.

### Why Reading Back Immediately After `force` Does Not Prove Durability

After `write` and `force`, a read on the same client can return data from a cache already holding the new version, **even if the server/storage has not achieved the durability level the application requires**.

To verify, you must test the exact NFS/SMB system, server version, mount options, and failure model. Simulating crashes, network drops, failovers, and reads from another client is vital. Even passing tests prove behavior only for the tested configuration/conditions, not a general Java API guarantee.

## 6. `FileLock`: Coordinating Write Access, While Checking NFS Support

Java provides `FileChannel.lock(...)`, `tryLock(...)`, and `java.nio.channels.FileLock`.

~~~java
// Illustrative snippet: FileChannel opened with appropriate write permission.
try (FileLock lock = channel.lock()) {
    // Code region protected under the shared locking convention.
    updateSharedFile();
    channel.force(true);
} // lock.close()/release() releases the lock.
~~~

Key details from the specification:

1. **Locks are scoped to files/byte ranges**, e.g., `channel.lock(0, 128, false)` requests an **exclusive** lock on a 128-byte region.
2. `lock(position, size, true)` requests a **shared lock**, though systems lacking shared-lock support may upgrade it to exclusive. Check `FileLock.isShared()` if this distinction matters.
3. File locks are **JVM-scoped**, not designed to coordinate threads within the same JVM. For threads, use appropriate Java synchronization primitives such as `synchronized` or `ReentrantLock`.
4. Some platforms use **advisory locks**: processes not following the locking protocol can still access the file. Other platforms have mandatory mechanisms; never assume uniform behavior.
5. On network filesystems, lock support depends on protocol version, server, client, mount/configuration, and lock-region styles. Java warns that some NFS setups do not support locking mapped regions unless page-aligned or impose offset/length limits.
6. Closing a channel on some operating systems can unexpectedly release locks associated with that file in the JVM. Use **one dedicated channel to manage locks on a file** within a workflow.

Therefore, **"acquired a FileLock" does not by itself prove cluster-wide consistency**. You must verify that all clients interact through the same lock service, no client bypasses locks, locks are not silently lost during network partitions/failovers, and the application handles failure to renew or verify ownership.

### Example: Preventing Lost Updates When Two Writers Modify a Balance

Two writers following the wrong workflow:

~~~text
A reads balance = 1000
B reads balance = 1000
A computes 1000 - 100 = 900, writes 900
B computes 1000 - 200 = 800, writes 800
Final result may be 800; A's update is lost.
~~~

To serialize properly, both A and B must follow:

~~~text
acquire lock
    -> open/read current version under a verified cache-coherence workflow
    -> verify version / update precondition
    -> write new version
    -> request synchronization per durability policy
release lock
~~~

Even with a lock, if B reads a **stale cache** or the server loses lock state during failover, results can still be wrong. Use **version numbers + compare-and-swap logic** at the application or storage layer when strictness is required. Even a program checking a version before writing to a regular file can race if the two steps are not guarded by a reliable coordination mechanism.

### `tryLock()` and Failures When Locks Are Unavailable

- `channel.tryLock()` typically returns `null` if the lock cannot be acquired immediately because another process holds a conflicting lock.
- If an overlapping lock already exists within the same JVM, `OverlappingFileLockException` can occur instead of `null`.
- A lock call can fail with `IOException` or because the provider/OS does not support the requested behavior.
- Never spin indefinitely calling `tryLock()` without designed backoff/timeout. On NFS, slow responses or network errors must be handled explicitly.

## 7. Atomic Rename Does Not Mean Data Durability or Cross-Client Snapshots

A common file-publication workflow:

1. Write complete content to a temporary file **in the same directory**.
2. Flush/sync the temporary file as supported by the platform.
3. Rename the temporary file to the name readers consume.
4. Readers process only the published file.

In Java, you can request:

~~~java
// Illustrative snippet; temp and target are validly prepared.
Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
~~~

**Important limitations:**

- `ATOMIC_MOVE` requests that the move be an **atomic filesystem operation**. If unsupported, Java throws `AtomicMoveNotSupportedException`. Typically source and destination must share the same `FileStore`/provider; not guaranteed across different mounts.
- If the target already exists, whether `ATOMIC_MOVE` replaces it or fails is **implementation-specific** in Java; never assume replacement always succeeds.
- A rename executed atomically on the server **does not automatically ensure** all clients invalidate their caches immediately or read a consistent multi-file snapshot.
- `ATOMIC_MOVE` also **does not guarantee durability** of the temp file's content, metadata, or directory entry across a server crash.
- Without `ATOMIC_MOVE`, races can happen between existence checks and the move; the move may not be atomic with respect to other filesystem operations.

Avoid the wrong approach:

~~~java
// Illustrates what to avoid when data is uncoordinated.
Files.writeString(target, largeDocument); // Readers may observe a mid-write state.
~~~

Publishing via a temp file and rename is generally better for **readers needing only complete versions**, yet you must still verify shared-filesystem semantics and reader reopen/verification rules.

### Manifests and Checksums for Multi-File Data

If a "data version" consists of `data-1.bin`, `data-2.bin`, and `metadata.json`, renaming each file separately does not create a transaction across all three files. A common design:

- Write new version files under **unique, immutable names**.
- Force/sync per storage capabilities and verify checksums.
- Once everything is ready, publish a **manifest** pointing to the names/versions of the new files.
- Readers read the manifest, verify versions/checksums, and consume only matching-version files.
- If checksums or versions mismatch, readers **retry under a bounded policy** rather than silently treating mixed content as valid.

This pattern improves detection of **mixed-version reads**. It still does not eliminate the need to persist the manifest durably or make assumptions about system cache coherence.

## 8. Runnable Java 17+ Program: Demonstrating Lock, Write, and Force on a Local File

The following program uses **a local temporary file**, running reliably without requiring an NFS mount. It illustrates the Java APIs and state observable by a reader **in the same test environment**. The result **does not prove** NFS provides the same visibility or durability.

Save the file **`NetworkFileConsistencyDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class NetworkFileConsistencyDemo {

    private static void writeAll(FileChannel channel, ByteBuffer data)
            throws IOException {
        while (data.hasRemaining()) {
            int n = channel.write(data);
            if (n == 0) {
                throw new IOException("No write progress");
            }
        }
    }

    private static void readExactly(FileChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n < 0) {
                throw new EOFException("Incomplete record");
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("fs-consistency-");
        Path file = dir.resolve("record.bin");

        try {
            try (FileChannel writer = FileChannel.open(file,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE);
                 FileLock lock = writer.lock()) {

                ByteBuffer record = ByteBuffer.allocate(16);
                record.putLong(1L);    // version
                record.putLong(900L);  // balance
                record.flip();

                writeAll(writer, record);
                writer.force(true); // Has defined Java guarantee on a local file.
                System.out.println("writer: version=1, balance=900");
            }

            // Reopen after the writer has finished and closed its channel.
            try (FileChannel reader = FileChannel.open(
                    file, StandardOpenOption.READ)) {
                ByteBuffer record = ByteBuffer.allocate(16);
                readExactly(reader, record);
                record.flip();

                System.out.println("reader: version="
                        + record.getLong() + ", balance="
                        + record.getLong());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile/run:

~~~bash
javac NetworkFileConsistencyDemo.java
java NetworkFileConsistencyDemo
~~~

**Expected stdout when the local filesystem permits the operations:**

~~~text
writer: version=1, balance=900
reader: version=1, balance=900
~~~

**Explanation:**

1. `ByteBuffer.allocate(16)` holds two `long` values, 8 bytes each. `putLong` writes in the default big-endian binary format.
2. Writer acquires `FileLock`, writes until `ByteBuffer` has no remaining bytes, and calls `force(true)` before closing.
3. After writer and lock have closed, reader opens the file, reads all 16 bytes, and decodes version/balance.
4. If run on NFS/SMB, stdout **may** match this output, yet that does not test crash, replication, or coherence behavior. `lock`, `force`, `close`, and `read` calls must be verified against the concrete storage setup.

**Note:** on some operating systems, deleting a file immediately while a mapping/handle is still open can fail; the program uses `try-with-resources` to close lock and channel before cleanup. If the filesystem encounters an I/O/permission error, the program throws an exception without printing full stdout.

### Testing Visibility Across Two Real Clients

To specifically test NFS behavior, you need **two real hosts or two mounts/clients** pointing to the same shared filesystem. Run a writer program on A and a reader on B following a timed test script. Collect:

- NFS/SMB version, server OS and file-system type, mount options, and cache policy.
- Sequence of open → write → force → close on A; open → read on B.
- Checksums/versions seen by each side, time until updates become visible, and any I/O errors.
- Outcomes when B keeps a handle open continuously versus closing and reopening.
- Behavior after network partitions, reconnects, server restarts, or controlled failovers.

Even consistently passing test runs **cannot prove every client always sees changes immediately**, though they serve as operational evidence for the tested environment.

## 9. Network Partitions, Failover, and Lost Locks

When connectivity drops, clients may continue holding stale cached data. The file server or storage service may recover sessions, leases, or locks in protocol-dependent ways. In particular, never infer:

- If a JVM previously held a valid `FileLock`, the server is guaranteed to honor the old lock across every network failure.
- If server failover succeeds, all recent writes from every client have the same durability level.
- If a write times out, it "definitely did not execute": the server may have received and applied the change while the response was lost.
- Retrying a balance-update write will not debit twice. Retries can cause business-logic bugs when operations are not idempotent.

For critical data, design **idempotency keys**, versions/fencing tokens, ownership re-verification steps, and network-error recovery rules. These requirements often fit a database or transactional store with an explicit consistency contract better than a raw shared file used as concurrent state.

### "Exactly Once" Does Not Come from FileChannel

Imagine an application writing a transaction record and losing connection before receiving confirmation. It cannot tell from a Java exception alone whether the server **committed or not**. Proper workflows typically use stable transaction IDs and query server/manifest state before retrying; raw file I/O does not provide exactly-once semantics.

## 10. Differences Across NFS, SMB, and Other Distributed File Systems

**Do not treat these systems as identical:**

| System Type | What Must Be Verified? |
|---|---|
| NFS (various versions) | Close-to-open, attribute/data caching, session/lock behavior, mount options, server commit semantics |
| SMB/CIFS | Oplocks/leases, cache invalidation, share modes, durability, and failover semantics of the deployed version |
| Strongly coherent cluster/distributed file systems | Consistency contracts, cross-client serialization, metadata transactions, failure behavior |
| Object storage mounted as a filesystem | Provider/FUSE semantics: rename, locking, append, list consistency, and sync/force can differ from POSIX |
| Local filesystem | Still requires atomicity, locking, and durability considerations, though Java's guarantees for local `force` are better defined |

Avoid blanket tricks like disabling all caches or constantly reopening files as a "universal solution": they can cause heavy network I/O and still fail to solve transactions or partitions. Design against the published contract of your storage system.

## 11. Common Mistakes

| Misconception | Reality |
|---|---|
| "Once A finishes writing, B immediately reads the new version" | Caching/client coherence can introduce delays; verify the exact filesystem. |
| "`Files.size()` always returns the latest server-side length" | Metadata caches and races can make the value stale by the time it is used. |
| "`force(true)` is durable on every network drive" | Java only guarantees local storage; remote storage carries no equivalent promise. |
| "`rws/rwd` replaces distributed transactions" | They only request synchronous I/O; they do not provide transactions or isolation. |
| "`FileLock` is always mandatory on every host" | Locks may be advisory, depending on implementation and server/client support. |
| "Holding `FileLock` is enough regardless of stale caches" | Requires cache coherence, reading the right version, and ownership verification. |
| "Close-to-open means every read on an old handle sees fresh data" | CTO mainly concerns close/open boundaries and specific cache policies. |
| "`ATOMIC_MOVE` is always supported and durable on every mount" | May be unsupported; namespace atomicity does not imply durability or cache visibility. |
| "Timestamps and sizes are reliable version markers" | Can collide, be cached, lack resolution, or change between check and use. |
| "One accurate read from client B proves crash safety" | That only shows point-in-time visibility, not crash/durability testing. |
| "Writing multiple files commits atomically via renames" | Per-file renames do not form cross-file transactions. |
| "A network timeout guarantees the write failed" | The server may have processed it and only the response was lost; idempotency/verification is needed. |

## 12. Checklist for Designing Applications Using Shared Files

1. **Define the consistency contract:** does the app tolerate eventual/close-to-open consistency, or truly need linearizable reads/writes?
2. **Define the durability contract:** does the server acknowledge to RAM cache, local disk, or replica/quorum? Can it recover if the server dies?
3. **Define owner/writer policy:** single writer or multiple competing writers? Do file locks work across all clients?
4. **Manage versions:** use version IDs/checksums/manifests for critical data so readers detect stale or incomplete data.
5. **Publish safely:** consider temp file + atomic move where supported, along with platform `force`/directory durability rules.
6. **Handle uncertain-commit failures:** use bounded, idempotent retries; never deduce state solely from timeouts.
7. **Test in a real environment:** two separate clients, verified mount options, and fault injection/network partitions/server restarts where feasible.
8. **Consider alternative technology:** when strong multi-writer transactions are required, a database or coordination service with clear contracts is usually far easier to guarantee than raw shared files.

### Self-Check Questions

1. A writes a file and calls `FileChannel.force(true)` on NFS. Under Java 17, can you claim the data survives any server crash? **No.** Local `force` guarantees do not apply generally to remote storage.
2. B keeps a file open for a long time and reads again after A updates it. Is B guaranteed to see the new version via CTO? **Not guaranteed.** You must examine cache policies, close/open boundaries, and filesystem behavior.
3. `Files.exists()` returns `true` and then the app opens the file. Is the file guaranteed to still exist intact? **No.** A race exists between check and use.
4. With `FileLock`, are all processes on every platform prevented from modifying the file? **No.** Locks may be advisory and support varies.
5. Does `Files.move(temp,target,ATOMIC_MOVE)` mean contents survive power loss? **No.** Atomic move and durability are two independent properties.
6. Can `MappedByteBuffer.force()` generally be replaced with `FileChannel.force(true)`? **No**; the `FileChannel` specification does not guarantee forcing dirty mapped pages.
7. If a request sent to the server times out, is it guaranteed not to have been written? **No.** Only the response may have been lost; check version/ID before retrying.
8. You need to ensure readers never consume mixed-version multi-file data. One design approach? **Versioned immutable files + manifest + checksum + verified publication protocol.**
9. Does `noac` on Linux NFS mean all data caching and all races are disabled? **No.**
10. When should you consider a database or coordination service? **When strong transactions, ordering, and isolation are needed across multiple writers or multiple failure domains.**

## 13. Official Documentation

- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force(boolean)`, `lock(...)`, reads/writes, local/remote guarantee scope.
- [Java SE 17 — FileLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): system-level nature, advisory/mandatory semantics, shared/exclusive modes, network filesystem specifics.
- [Java SE 17 — RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html): `"rw"`, `"rwd"`, `"rws"`, and local-device synchronization.
- [Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()` and limits on non-local storage files.
- [Java SE 17 — Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): `ATOMIC_MOVE`, unsupported cases, and provider-dependent behavior.
- [Linux man-pages — nfs(5), Data and Metadata Coherence](https://man7.org/linux/man-pages/man5/nfs.5.html): caching, close-to-open, attribute cache, and Linux NFS mount options.