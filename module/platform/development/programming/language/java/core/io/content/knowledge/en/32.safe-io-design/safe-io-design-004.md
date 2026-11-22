# TOCTOU: The Gap Between Check and Use in Java I/O

## 1. What Is TOCTOU and Why Is It Dangerous?

**TOCTOU** stands for **Time-of-Check to Time-of-Use**: the application checks a condition at time **T1**, but only performs an action based on that condition at time **T2**. During the T1 → T2 interval, the checked state may have changed. If the application assumes the check result is still valid, it can corrupt business logic or introduce a security vulnerability.

In Java I/O, the most common targets are files and paths: the application checks a `Path`, then opens, writes, renames, or deletes the corresponding file. Another process may replace the file with a symbolic link (symlink), rename a directory, create the file first, or alter permissions between the two operations.

~~~text
Time             Application Thread               Other Actor
T1               Check: file does not exist
                 |                                Creates file with same name
                 |                                or swaps in a symlink
T2               Write file using checked name
                 |
Result           The operation may affect an object
                 different from what the application intended.
~~~

A race can occur even **without an attacker**: two concurrent requests, two workers, multiple JVMs, cleanup jobs, or external processes can all alter state. When an adversary actively manipulates directories/paths, this becomes a **race condition** attack.

**Distinguish three elements:**

- **Check:** a query or state inspection, such as `Files.exists(path)`, `Files.isReadable(path)`, `Files.isRegularFile(path)`, `Files.notExists(path)`, `Files.readAttributes(path, ...)`, or a filename check.
- **Gap:** the interval between the check and the subsequent operation; even if very short, it still exists, and thread scheduling can reorder execution.
- **Use:** creating, opening, reading, writing, moving, replacing, deleting, or modifying metadata of the file.

Not every two-step I/O sequence is a vulnerability. The problem arises when correctness or security **depends on the assumption that the state at T1 remains valid at T2**.

## 2. How TOCTOU Appears on the Filesystem

Suppose a program receives a filename from a client and only wants to create a new file if it does not already exist:

~~~java
Path target = uploadDir.resolve(requestedName);
if (Files.notExists(target)) {
    Files.writeString(target, content);
}
~~~

This is a **buggy illustrative snippet**, not a standalone program. The danger lies in:

1. `Files.notExists(target)` only reflects the state observed **at the moment of the call**. It acquires no lock and does not “reserve” the filename.
2. Another actor can create `target` after the method returns `true`.
3. `Files.writeString(target, content)` by default opens the file with behavior equivalent to `CREATE`, `TRUNCATE_EXISTING`, and `WRITE`. Thus the newly created file can be **overwritten/truncated**, instead of being protected by the “create only if absent” condition.
4. If part of the path is a symlink that another party can swap, the operation can be redirected to an unintended file.

`Files.exists` / `notExists` also have an important detail: when the status cannot be determined, **both can return `false`**. A non-existence result does not prove the file can safely be created; never use these two methods as a synchronization or access-control mechanism.

### 2.1. Typical Scenarios

| Pre-check | Subsequent Operation | Risk When State Changes Between Steps |
| --- | --- | --- |
| `if (!Files.exists(p))` | `Files.writeString(p, ...)` | File appears; another party's data is overwritten |
| `Files.isRegularFile(p)` | `Files.newInputStream(p)` | File is replaced or symlink retargeted; app reads another file |
| `Files.isWritable(p)` | `Files.newOutputStream(p)` | Permissions/state change; open fails or hits a different object |
| Check owner/permission/path | `Files.delete(p)` | Deletes a different entry than the one checked |
| `Files.size(p) <= limit` | `Files.readAllBytes(p)` | File grows, consuming more memory than expected |
| Check upload directory exists | Create child file in directory | Directory may be replaced by a symlink or moved elsewhere |

For example, checking `Files.size(p)` and then calling `readAllBytes(p)` **does not** establish a safe quota. If maximum size is a security invariant, bound the byte count **while reading** and reject when exceeded.

### 2.2. Actual Threat Depends on Other Actors' Privileges

An attacker can only exploit a race if they have a way to influence the relevant state: such as permission to alter entries in the upload directory, permission to modify symlinks, or the ability to send competing requests. In a directory where only a trusted program has write access, exploitation risk is usually lower, though bugs from internal processes can still occur.

Therefore, before fixing the bug, determine **who owns the directory, who can alter entries, who decides filenames, and which operations must be safe**. Do not simply blame the JVM or OS latency.

## 3. Java 17+ Example: Reproducing the Check → Write Flaw

The following example **deterministically simulates the interleaving order**, so the result is stable without hoping two threads race at the right instant. It creates all files in its own temporary directory.

Create the file `ToctouCreateDemo.java`:

~~~java
import java.nio.file.*;

import static java.nio.file.StandardOpenOption.*;

public class ToctouCreateDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("toctou-demo-");
        Path unsafe = dir.resolve("unsafe.txt");
        Path safe = dir.resolve("safe.txt");

        try {
            // T1: Application observes the file does not exist.
            boolean absent = Files.notExists(unsafe);

            if (absent) {
                // Simulate another process creating the file between T1 and T2.
                Files.writeString(unsafe, "other", CREATE_NEW, WRITE);

                // T2: Application acts on the stale check result.
                Files.writeString(unsafe, "app",
                        CREATE, TRUNCATE_EXISTING, WRITE);
            }

            System.out.println("unsafe=" + Files.readString(unsafe));

            // File already exists: CREATE_NEW refuses to overwrite.
            Files.writeString(safe, "other", CREATE_NEW, WRITE);
            try {
                Files.writeString(safe, "app", CREATE_NEW, WRITE);
            } catch (FileAlreadyExistsException expected) {
                System.out.println("safe=rejected");
            }

            System.out.println("safe-content=" + Files.readString(safe));
        } finally {
            Files.deleteIfExists(unsafe);
            Files.deleteIfExists(safe);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Run:

~~~bash
javac ToctouCreateDemo.java
java ToctouCreateDemo
~~~

Stdout:

~~~text
unsafe=app
safe=rejected
safe-content=other
~~~

**Explanation:** In the first branch, `notExists` was true initially, but by the time `writeString` ran, the file already existed. The `CREATE` and `TRUNCATE_EXISTING` options caused the application to overwrite `"other"` with `"app"`.

In the second branch, `CREATE_NEW` combines the “file does not exist” condition and file creation into **one atomic operation with respect to creating an entry of the same name** per the `Files` contract. When the entry already exists, it throws `FileAlreadyExistsException` (on the illustrated provider), leaving the content intact. There is no need to call `Files.notExists` first.

**Limitation of `CREATE_NEW`:** atomicity applies to creating the entry at the path resolved by the filesystem. If **parent directories or ancestor components** can be modified by an attacker, `CREATE_NEW` alone is not a complete defense against symlink redirection on those components. Likewise, “not overwritten at creation time” does not mean the file cannot be replaced after creation.

## 4. Close the Gap with Atomic Operations, Not Faster Checks

A practical principle: if a condition must hold **at the exact moment of the operation**, look for an API that checks the condition and performs the action **in the same operation**.

### 4.1. Create a File Only If Absent

- `Files.createFile(path)` checks that the name is absent and creates an empty file as **an atomic operation**; if it exists, it fails.
- `Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE))` opens a channel and requires exclusive creation, avoiding check-then-open.
- `Files.writeString(path, text, CREATE_NEW, WRITE)` does the same for string content in the example above.

Do not interpret “atomic create” as “writing the entire content atomically”. `CREATE_NEW` protects the filename-creation step; another process may still observe a partially written file. To ensure readers only see a **complete version of the content**, use a **write-to-staging-then-publish** strategy.

### 4.2. Write to Staging, Then Publish via Atomic Move

Common pattern for an output file:

1. Create a new temporary file using `Files.createTempFile(parent, prefix, suffix)` **in the destination directory or on the same `FileStore`**, with appropriate permissions.
2. Write the entire content to the temporary file, finish processing, and close the stream/channel.
3. Call `Files.move(temp, destination, StandardCopyOption.ATOMIC_MOVE)` to ask the filesystem to swap the entry in one atomic operation.
4. If the provider throws `AtomicMoveNotSupportedException`, handle it per the application's contract: reject the publish, choose a controlled mechanism, or roll back. Never silently fall back to a regular `move` and claim the operation is still atomic.

Example publish logic (code **inside a method with `throws IOException`**, with `parent` and `destination` already safely determined):

~~~java
Path staging = Files.createTempFile(parent, ".publish-", ".part");
try {
    Files.writeString(staging, payload,
            StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING);

    // May throw AtomicMoveNotSupportedException.
    Files.move(staging, destination, StandardCopyOption.ATOMIC_MOVE);
} finally {
    Files.deleteIfExists(staging);
}
~~~

Two things must be remembered:

- With `ATOMIC_MOVE`, Java documentation specifies that **other options are ignored**; when `destination` already exists, whether it replaces or rejects is **implementation-dependent**. Therefore **`ATOMIC_MOVE` does not guarantee “create only, never overwrite”** for an existing destination. If you need both atomic publish and exclusive creation, choose a protocol/storage mechanism supporting that exact property and test it on the target filesystem.
- Atomic rename/move primarily protects **the visibility consistency of the entry**, without automatically guaranteeing data has been durably flushed to storage across power loss. If durability is needed, also consider `FileChannel.force(...)`, directory flushing, and OS/filesystem guarantees.

### 4.3. Are File Locks and Mutexes Enough?

- `synchronized` and `ReentrantLock` only coordinate threads **sharing the exact same lock** inside one JVM. Other processes do not participate.
- `FileChannel.lock()` / `tryLock()` is a file-locking coordination mechanism; lock enforcement and scope depend on the platform. Many filesystems use advisory locks or behave differently over a network; processes that ignore the lock protocol can still cause issues.
- Distributed locks are also only effective when **every writer obeys the protocol** and expiration/fencing conditions are handled properly.

To prevent overwrites, `CREATE_NEW` is usually stronger and simpler than “check with `exists` then lock/write”. If multiple writers concurrently update a value, design proper concurrency control rather than just wrapping a `Path` in a lock.

## 5. Symlink Race: Checking One Path, Opening Another Object

### 5.1. Mechanism

Suppose a privileged service accepts the name `report.txt` inside a directory where users can alter entries:

~~~text
T1: /uploads/report.txt -> normal file, check passes
       |
       | attacker replaces report.txt with a symlink
       v
T2: /uploads/report.txt -> /some/other/location
    service opens by path, action is redirected
~~~

Symlinks are not the only cause. A file object can also be **renamed/replaced**, and a parent path component such as `/uploads/current` can be swapped for a symlink; checking symlinks only on the **final filename** does not protect every component.

Operations like `Path.normalize()` and `Path.toAbsolutePath()` manipulate path names, do not lock the filesystem, and do not guarantee the opened object is the one checked earlier. `toRealPath()` resolves symlinks to get the real path at **the moment of the call**, yet the file can still change before the next use. Thus “call `toRealPath` then open the file” still has TOCTOU.

### 5.2. How Does `NOFOLLOW_LINKS` Help?

`LinkOption.NOFOLLOW_LINKS` instructs supporting APIs **not to follow symbolic links** during the corresponding access. Example:

~~~java
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
import java.util.Set;

try (SeekableByteChannel channel = Files.newByteChannel(
        path, Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
    // Read from the opened channel.
}
~~~

This is an **illustrative snippet**, assuming `path` is declared and the code is inside a method with `throws IOException`. `NOFOLLOW_LINKS` in this channel-opening call avoids following the **final symlink** per provider rules. It does not make a prior `Files.isRegularFile(path, NOFOLLOW_LINKS)` atomic, does not protect mutable parent paths, and does not replace directory permission controls.

Only pass `NOFOLLOW_LINKS` to APIs that actually accept it; do not assume every API accepting `Path` follows the same semantics.

### 5.3. `SecureDirectoryStream`: Operations Relative to an Open Directory

Java NIO.2 provides `java.nio.file.SecureDirectoryStream<Path>` for programs that need to perform file operations relative to a **handle to an already-open directory**. Java documentation describes its goal as avoiding races when moving, deleting, and accessing files in a directory tree where paths may change at runtime.

How it differs from `Files.isRegularFile(fullPath)` followed by `Files.newInputStream(fullPath)`:

- `SecureDirectoryStream` resolves names **relative to the open directory**, rather than starting from a full pathname each time.
- You can open a child entry with `newByteChannel(relativeName, options)`, use `getFileAttributeView` on a child file, `deleteFile(relativeName)`, `move(...)`, or open a subdirectory via `newDirectoryStream(relativeDir, NOFOLLOW_LINKS)`.
- Opening subdirectories keeps operations handle-relative down each level of the tree, avoiding dependence on outer directory names that could be renamed/replaced.
- **Not every provider supports it.** `Files.newDirectoryStream(dir)` only returns an implementation of `SecureDirectoryStream` if the OS and provider supply the underlying mechanism. Never cast blindly or assume the feature is always present.

Example file `SecureDirectoryStreamDemo.java`, reading a single file in a program-created temporary directory:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Set;

public class SecureDirectoryStreamDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("secure-dir-");
        Path file = dir.resolve("data.txt");

        try {
            Files.writeString(file, "hello",
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

            try (DirectoryStream<Path> raw = Files.newDirectoryStream(dir)) {
                if (!(raw instanceof SecureDirectoryStream<?>)) {
                    System.out.println("secure-stream=unavailable");
                } else {
                    @SuppressWarnings("unchecked")
                    SecureDirectoryStream<Path> secure =
                            (SecureDirectoryStream<Path>) raw;

                    try (SeekableByteChannel channel = secure.newByteChannel(
                            Path.of("data.txt"),
                            Set.of(StandardOpenOption.READ,
                                   LinkOption.NOFOLLOW_LINKS))) {
                        ByteBuffer buffer = ByteBuffer.allocate(64);
                        channel.read(buffer);
                        buffer.flip();
                        System.out.println(
                                StandardCharsets.UTF_8.decode(buffer));
                    }
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run:

~~~bash
javac SecureDirectoryStreamDemo.java
java SecureDirectoryStreamDemo
~~~

There are **two valid outputs depending on the provider**:

~~~text
hello
~~~

or:

~~~text
secure-stream=unavailable
~~~

In the supported branch, `newByteChannel` takes the relative name `data.txt` and operates against the open directory stream. This is an API example for a simple entry; in a real service you must validate input names, avoid absolute names or `..`, ensure the initial handle opens a trusted directory, and implement a **fail closed** policy if the environment requires race resistance when the provider lacks support.

**Important limitation:** holding a directory handle does not automatically verify **application-level access rights to the content** or data being read. You must verify inputs, targets, and permissions at the appropriate time. When precise OS-level operation control is required, native APIs equivalent to `openat` or dedicated OS mechanisms may be needed — Java NIO.2 does not guarantee all security properties across every filesystem.

## 6. Path Validation: Necessary but Not Sufficient

Suppose only direct filenames inside directory `root` are allowed:

~~~java
Path root = approvedRoot.toAbsolutePath().normalize();
Path candidate = root.resolve(requestedName).normalize();

if (!candidate.startsWith(root)) {
    throw new SecurityException("Path escapes root");
}
~~~

This is an **illustrative snippet inside a method** with input variables `approvedRoot` and `requestedName` already declared. It eliminates **name-based** path traversal such as `../../outside.txt` after normalization. However:

- `startsWith` checks path components, not the real target on the filesystem.
- A symlink can point outside even though the normalized pathname stays under `root`.
- If another process can alter directory entries, a check at T1 does not protect an open at T2.
- If only a **single-level filename** is allowed, verify `requestedName` is actually a single filename with no separators or `..` components before resolving.
- Restrict directory write permissions, use server-controlled filenames where appropriate, and prefer handle-relative APIs or atomic open options.

Validating the input path remains necessary to define scope. Clearly separate **path validation** from **filesystem object identity**; the two problems must be solved with appropriate mechanisms.

## 7. Read, Write, Modify, and Delete: Choose Measures by Action

| Goal | Insufficient Approach | Better Design Direction |
| --- | --- | --- |
| Create only, never overwrite | `if (!exists) write` | `CREATE_NEW` or `Files.createFile` |
| Disallow reading through final symlink | `isSymbolicLink` then `newInputStream` | Open with an API supporting `NOFOLLOW_LINKS`; consider parent paths too |
| Work in a directory tree that may change | Check real path then open repeatedly by full path | `SecureDirectoryStream` when supported; explicit policy if unsupported |
| Publish complete file | Write directly to final file | Write to staging then `ATOMIC_MOVE`; check destination replacement semantics |
| Delete only the selected entry | `isRegularFile(p)` then `delete(p)` | Locate entry relative to trusted directory handle; when appropriate, `SecureDirectoryStream.deleteFile` |
| Bound bytes read | `Files.size(p)` then `readAllBytes(p)` | Read stream/channel with a byte counter and stop immediately if exceeded |
| Update a record by version | `read -> validate -> write` without concurrency control | Compare-and-set, optimistic locking with version, transaction, or unique constraint |

Atomicity in one step does not make an entire multi-step workflow atomic. For example, creating a file successfully and then failing to insert a DB row still leaves an incomplete state; when cross-resource consistency is needed, use transactions/compensation or an equivalent protocol.

## 8. Non-File TOCTOU Example: Limits of Check-Before-Update

TOCTOU also occurs in APIs/DBs. Suppose two requests process the same coupon code concurrently:

~~~text
A: SELECT remaining -> 1
B: SELECT remaining -> 1
A: UPDATE remaining -> 0; redemption allowed
B: UPDATE remaining -> 0; redemption also allowed
~~~

If the application relies solely on the prior `SELECT`, both requests can be accepted. The right approach is to turn the condition into a **concurrency-controlled storage operation**, such as:

~~~sql
UPDATE coupon
SET remaining = remaining - 1
WHERE id = ? AND remaining > 0;
~~~

This SQL snippet merely illustrates a conditional decrement. The application must check the **updated row count** and ensure proper locking/identifiers and transaction isolation. If `UPDATE` affects 0 rows, reject the redemption; never confirm success using the stale `SELECT` result.

File and DB problems share the same essence: a “passing check” is no guarantee the condition still holds when another operation begins.

## 9. Solutions That Look Right but Still Race

### 9.1. “Re-check Right Before Opening”

~~~java
if (Files.exists(path) && Files.isReadable(path)) {
    // A race can still occur right here.
    try (var in = Files.newInputStream(path)) {
        // ...
    }
}
~~~

The window may be shorter, yet check+open is still not a single operation. `exists` and `isReadable` also have semantics that do not guarantee the subsequent open will succeed. Design around **an open/operation with appropriate constraints** and handle the result of that operation directly.

### 9.2. “Using `synchronized` Solves It”

`synchronized` only applies across code paths using **the same monitor** within a single JVM; other workers, other JVMs, external processes, and attackers are not bound by it. Use it for internal synchronization, not as protection for shared file uploads.

### 9.3. “Using `NOFOLLOW_LINKS` at Check Time”

`Files.isRegularFile(path, NOFOLLOW_LINKS)` observes the link at a single instant. If you then open without `NOFOLLOW_LINKS`, a swap window remains. Even `NOFOLLOW_LINKS` at open time must be evaluated alongside **ancestor path** risks.

### 9.4. “Comparing `fileKey` Before and After”

`BasicFileAttributes.fileKey()` can sometimes help identify a file on supporting providers, yet not all providers return reliable or stable keys. Comparing twice is still **post-facto detection**, not a substitute for opening and operating on the same bound object. Once a write/delete hits the wrong file, detecting it afterward may be too late.

### 9.5. “Just Catch `IOException` and Retry”

Retrying the same path without re-evaluating safety conditions can repeat the race or hit a new entry. Distinguish `FileAlreadyExistsException`, `NoSuchFileException`, `AccessDeniedException`, and `AtomicMoveNotSupportedException`; the reaction depends on the operation's contract.

### 9.6. “Moving a File Is Atomic on Every Drive”

Plain `Files.move` has no universal atomicity guarantee across all providers. `ATOMIC_MOVE` may also be unsupported, especially across filesystems. Do not assume a pre-check with `exists` solves target replacement in `ATOMIC_MOVE`, because the specification allows implementation-defined behavior if the target already exists.

## 10. Design Workflow to Prevent TOCTOU

1. **Identify the invariant to preserve**: no overwrite; no read outside directory; no deleting the wrong file; only one request claims a job; no processing beyond quota.
2. **Identify actors and contention scope**: same-JVM threads, other processes, users able to modify directory entries, symlinks, network filesystems, or DB transactions.
3. **Find an atomic primitive matching the contract**: `CREATE_NEW`, directory-handle operations, conditional updates, transactions, compare-and-set, or a commit protocol.
4. **Keep the handle/reference stable when needed**: once a proper file/channel is opened, operate on that handle. Avoid checking by path and reopening by name when identity changes are dangerous.
5. **Protect directory entries and control permissions**: server-generated names, directories writable only by the service, appropriate no-follow options, and providers supporting `SecureDirectoryStream` when needed.
6. **Define failure behavior on race**: typically treat “file already exists” as a valid conflict, not a reason to fall back to overwriting. Log minimal context and return an appropriate error.
7. **Test controlled interleavings**: use latches/barriers, mock hooks, or fixtures to force T1–actor state mutation–T2. Never rely on `Thread.sleep(...)` hoping a race happens naturally.
8. **Verify on the actual target filesystem**: providers differ in symlink support, `SecureDirectoryStream`, atomic move, ACLs, and locking semantics.

A useful negative test is having a second actor create the entry **immediately after the check**, then verifying the application does not overwrite it. For symlink races, test on the actual OS/provider with symlink creation enabled and clearly bound what is protected; do not extrapolate from dev-machine results alone.

## 11. Self-Check Questions

**Question 1.** `Files.notExists(path)` returns `true`; does that guarantee a subsequent `Files.writeString(path, ...)` creates a new file without overwriting?

**Answer:** No. The entry can appear after the check. If the requirement is “create only”, pass `CREATE_NEW` directly in the open/write call.

**Question 2.** Does atomic `Files.createFile(path)` mean the entire file content written by subsequent `write` calls is also atomic?

**Answer:** No. Atomicity here applies to the check-and-create behavior for the entry. Publishing complete content is a separate problem, typically requiring staging + atomic move and understanding filesystem guarantees.

**Question 3.** After calling `Path.toRealPath()`, is a service guaranteed immune to symlink races if it continues opening by that path?

**Answer:** No. `toRealPath` reflects the state at the moment of the call; it does not lock entries. You must consider who can alter parents and leverage directory-handle-relative opens or APIs with safe options.

**Question 4.** Why is `NOFOLLOW_LINKS` on a single `isRegularFile` call not enough?

**Answer:** It is still a check separated from the open, so the entry can be swapped afterward. Passing the option at open time is more effective for the final symlink, though it does not automatically protect ancestor paths.

**Question 5.** Why does `synchronized` alone fail to stop an attacker modifying files from another process?

**Answer:** A Java monitor only synchronizes threads within the same JVM using that exact monitor. Other processes are not constrained by it.

**Question 6.** If the provider does not support `SecureDirectoryStream` and the system requires preventing directory-entry swaps during read/delete, what should you do?

**Answer:** Do not silently cast or fall back to check/open sequences if that breaks the security invariant. Reject the feature, change provider/environment, tighten directory permissions, or build and test an appropriate native mechanism.

## 12. References

- [Java SE 17 `Files` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `exists`, `notExists`, `createFile`, `newByteChannel`, `move`, and `ATOMIC_MOVE`.
- [Java SE 17 `SecureDirectoryStream` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): directory-handle-relative access and race-avoidant open/delete/move operations per interface goals.
- [Java SE 17 `LinkOption` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): semantics of `NOFOLLOW_LINKS`.
- [Java SE 17 `StandardOpenOption` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `TRUNCATE_EXISTING`, `WRITE`.
- [Java SE 17 `FileChannel` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `lock`, `tryLock`, and `force`.

**Core takeaway:** TOCTOU is a flaw of **multi-step protocols built on mutable state**. The solution is not shaving microseconds between check and use, but designing so the condition is enforced **within the constrained operation itself**, or holding a stable reference to the exact object being processed.