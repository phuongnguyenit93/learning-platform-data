# TOCTOU: The Gap Between Check and Use in Java I/O

## 1. What Is TOCTOU and Why Is It Dangerous?

**TOCTOU** stands for **Time-of-Check to Time-of-Use**: an application checks a condition at time **T1**, but only performs the action based on that condition at **T2**. During the T1 → T2 window, the checked state may have changed. If the application assumes the check result is still valid, it can cause business logic errors or security vulnerabilities.

In Java I/O, the most common objects are files and paths: an application checks a `Path` and then opens, writes, renames, or deletes the corresponding file. Another process can replace the file with a symbolic link (symlink), rename a directory, create the file beforehand, or change permissions between the two operations.

~~~text
Time             Application thread             Other actor
T1               Check: file does not exist
                 |                              Creates file with same name
                 |                              or swaps symlink
T2               Writes file using checked name
                 |
Result           The operation may affect a different
                 object than the application intended.
~~~

Races can happen even **without an attacker**: two concurrent requests, two workers, multiple JVMs, cleanup jobs, or external processes can all change state. When an adversary actively controls the directory or path, this also becomes a **race condition** attack.

**Distinguish three elements:**

- **Check:** a query or inspection of state, such as `Files.exists(path)`, `Files.isReadable(path)`, `Files.isRegularFile(path)`, `Files.notExists(path)`, `Files.readAttributes(path, ...)`, or a filename check step.
- **Gap:** the interval between the check and the subsequent operation; even if very short, it exists and thread scheduling can reorder execution.
- **Use:** the operation that creates, opens, reads, writes, moves, replaces, deletes, or modifies file metadata.

Not every sequence of two I/O operations is a vulnerability. The problem arises when correctness or security **depends on assuming the state at T1 still holds at T2**.

## 2. How TOCTOU Occurs on the Filesystem

Suppose a program receives a filename from a client and only wants to create a new file if it does not already exist:

~~~java
Path target = uploadDir.resolve(requestedName);
if (Files.notExists(target)) {
    Files.writeString(target, content);
}
~~~

This is a **buggy illustrative snippet**, not a standalone program. The danger lies in:

1. `Files.notExists(target)` only reflects the state observed **at the instant of the call**. It places no lock and does not "reserve" the filename.
2. Another actor can create `target` after the method returns `true`.
3. `Files.writeString(target, content)` opens the file by default with behavior equivalent to `CREATE`, `TRUNCATE_EXISTING`, and `WRITE`. Thus, the newly created file can be **overwritten/truncated** instead of being protected by the "create only if absent" condition.
4. If part of the path is a symlink that another party can change, the operation can be redirected to an unintended file.

`Files.exists` / `notExists` also has an important detail: when the status cannot be determined, **both can return `false`**. A non-existent result does not by itself prove it is safe to create the file; never use these two functions as synchronization or access control mechanisms.

### 2.1. Typical Scenarios

| Pre-check | Subsequent operation | Risk if state changes between steps |
| --- | --- | --- |
| `if (!Files.exists(p))` | `Files.writeString(p, ...)` | File appears; another party's data is overwritten |
| `Files.isRegularFile(p)` | `Files.newInputStream(p)` | File is replaced or symlink target changes; app reads another file |
| `Files.isWritable(p)` | `Files.newOutputStream(p)` | Permissions/state change; open fails or hits a different object |
| Check owner/permission/path | `Files.delete(p)` | Deletes a different entry than the one checked |
| `Files.size(p) <= limit` | `Files.readAllBytes(p)` | File grows, consuming more memory than expected |
| Check upload directory exists | Create child file in directory | Directory may be replaced with a symlink or moved elsewhere |

For example, checking `Files.size(p)` and then calling `readAllBytes(p)` **does not** enforce a safe quota. If maximum size is a security invariant, limit the byte count **while reading** and reject when the limit is exceeded.

### 2.2. Actual Threat Depends on Other Actors' Privileges

An attacker can only exploit a race if they have a way to influence the relevant state: for instance, permission to modify entries in the upload directory, permission to alter symlinks, or the ability to send competing requests. In a directory writable only by the trusted program, exploitation risk is usually lower, though bugs from internal processes can still occur.

Therefore, before fixing an issue, determine **who owns the directory, who has permission to change entries, who decides filenames, and which operations must be safe**. Do not simply blame the JVM or OS scheduling latency.

## 3. Java 17+ Example: Reproducing the Check → Write Bug

The following example **simulates exact interleaving order**, so the result is deterministic without hoping two threads race at the right moment. It creates all files inside a dedicated temporary directory.

Create file `ToctouCreateDemo.java`:

~~~java
import java.nio.file.*;

import static java.nio.file.StandardOpenOption.*;

public class ToctouCreateDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("toctou-demo-");
        Path unsafe = dir.resolve("unsafe.txt");
        Path safe = dir.resolve("safe.txt");

        try {
            // T1: Application observes that the file does not exist.
            boolean absent = Files.notExists(unsafe);

            if (absent) {
                // Simulate another process creating the file between T1 and T2.
                Files.writeString(unsafe, "other", CREATE_NEW, WRITE);

                // T2: Application acts based on the stale check result.
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

**Explanation:** In the first branch, `notExists` was true when checked, but by the time `writeString` ran, the file already existed. The `CREATE` and `TRUNCATE_EXISTING` options caused the application to overwrite `"other"` with `"app"`.

In the second branch, `CREATE_NEW` makes the "file does not exist" check and file creation **an atomic operation with respect to creating an entry of the same name** under the `Files` contract. When the entry already exists, it throws `FileAlreadyExistsException` (on the illustrated provider), keeping the original content intact. Calling `Files.notExists` beforehand is unnecessary.

**Limitation of `CREATE_NEW`:** atomicity applies to creating the entry at the path resolved by the filesystem. If **the parent directory or ancestor components** can be modified by an attacker, `CREATE_NEW` alone is not a complete solution against redirection through symlinks in those components. Likewise, "not overwritten at creation" does not mean the file cannot be altered after creation.

## 4. Close the Gap With Atomic Operations, Not Faster Checks

A practical principle: if a condition must hold **at the exact time of the operation**, look for an API that checks the condition and performs the action **in the same operation**.

### 4.1. Creating a File Only If Absent

- `Files.createFile(path)` checks that the name is absent and creates an empty file as **an atomic operation**; if it exists, it fails.
- `Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE))` opens a channel and requires exclusive creation, avoiding the check-then-open sequence.
- `Files.writeString(path, text, CREATE_NEW, WRITE)` does the same for string content in the example above.

Do not interpret "atomic create" as "writing the entire content atomically." `CREATE_NEW` protects the filename creation step; another process can observe a partially written file. To ensure readers only see a **complete version of the content**, use a **write-to-staging-then-publish** strategy.

### 4.2. Writing to Staging Then Publishing With Atomic Move

Common pattern for an output file:

1. Create a new temporary file via `Files.createTempFile(parent, prefix, suffix)` **in the target directory or on the same `FileStore`**, with appropriate permissions.
2. Write all content to the temporary file, finish processing, and close the stream/channel.
3. Call `Files.move(temp, destination, StandardCopyOption.ATOMIC_MOVE)` to ask the filesystem to swap the entry in an atomic operation.
4. If the provider throws `AtomicMoveNotSupportedException`, handle it per the application contract: refuse publishing, choose a controlled mechanism, or roll back. Do not silently fall back to a regular `move` and claim the operation is still atomic.

Example publish logic (code inside a **method with `throws IOException`**, where `parent` and `destination` have already been safely determined):

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

Two things to remember:

- For `ATOMIC_MOVE`, the Java specification states that **other options are ignored**; when `destination` already exists, whether it replaces or rejects is **implementation-dependent**. Therefore, **`ATOMIC_MOVE` does not guarantee "create only, strictly no overwrite"** for an existing destination. If you need both atomic publishing and exclusive creation, choose a protocol/storage supporting that exact property and test on the target filesystem.
- Atomic rename/move primarily protects **visibility consistency of the entry**, without guaranteeing that data has been durably flushed to storage across power loss. If durability is needed, you must also consider `FileChannel.force(...)`, directory flushing, and OS/filesystem guarantees.

### 4.3. Are File Locks and Mutexes Enough?

- `synchronized` and `ReentrantLock` only coordinate threads **sharing the exact same lock** inside the JVM. Other processes are not required to participate.
- `FileChannel.lock()` / `tryLock()` is a file-locking coordination mechanism; lock enforcement and scope are platform-dependent. Many filesystems use advisory locks or behave differently over networks; processes not following the lock protocol can still cause issues.
- Distributed locks also only hold when **every writer obeys the protocol** and expiration/fencing conditions are handled properly.

If avoiding overwrites is the goal, `CREATE_NEW` is usually stronger and simpler than "check with `exists` then lock/write." If the problem involves multiple writers updating a value concurrently, design proper concurrency control rather than just wrapping a `Path` in a lock.

## 5. Symlink Race: Checking One Path, Opening Another Object

### 5.1. Mechanism

Suppose a high-privilege service accepts a filename `report.txt` inside a directory where a user can modify entries:

~~~text
T1: /uploads/report.txt -> normal file, check passes
       |
       | attacker replaces report.txt with a symlink
       v
T2: /uploads/report.txt -> /some/other/location
    service opens by path, action is redirected
~~~

Symlinks are not the only cause. File objects can also be **renamed/replaced**, and a parent path component such as `/uploads/current` can be swapped into a symlink; checking only whether the **final filename** is a symlink does not protect all components.

Operations like `Path.normalize()` and `Path.toAbsolutePath()` manipulate path names, do not lock the filesystem, and do not guarantee that the opened object is the same one previously checked. `toRealPath()` resolves symlinks to obtain the real path at the **time of the call**, but the file can still change before subsequent use. Thus, "call `toRealPath` then open the file" still has TOCTOU.

### 5.2. How Does `NOFOLLOW_LINKS` Help?

`LinkOption.NOFOLLOW_LINKS` instructs supporting APIs **not to follow symbolic links** in that access operation. Example:

~~~java
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
import java.util.Set;

try (SeekableByteChannel channel = Files.newByteChannel(
        path, Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
    // Read from the opened channel.
}
~~~

This is an **illustrative snippet**, assuming `path` is declared and the code is inside a method with `throws IOException`. `NOFOLLOW_LINKS` in this channel-opening call helps avoid following the **final symlink** according to provider rules. It does not make a prior `Files.isRegularFile(path, NOFOLLOW_LINKS)` atomic, does not automatically protect mutable parent paths, and does not replace directory permission controls.

Only pass `NOFOLLOW_LINKS` to APIs that actually accept it; do not assume every API taking a `Path` obeys the same semantics.

### 5.3. `SecureDirectoryStream`: Operations Relative to an Open Directory

Java NIO.2 provides the `java.nio.file.SecureDirectoryStream<Path>` interface for programs needing file operations relative to an **open directory handle**. Java documentation describes its goal as avoiding races when moving, deleting, and accessing files in a directory tree whose paths may be altered during execution.

How it differs from `Files.isRegularFile(fullPath)` followed by `Files.newInputStream(fullPath)`:

- `SecureDirectoryStream` locates names **relative to the open directory**, rather than starting from a full pathname each time.
- It can open child entries with `newByteChannel(relativeName, options)`, use `getFileAttributeView` for child files, `deleteFile(relativeName)`, `move(...)`, or open subdirectories with `newDirectoryStream(relativeDir, NOFOLLOW_LINKS)`.
- Opening subdirectories can keep operations handle-relative across each tree level, avoiding dependence on outer directory names that might be renamed or replaced.
- **Not every provider supports it.** `Files.newDirectoryStream(dir)` only returns an instance implementing `SecureDirectoryStream` if the OS and provider supply the underlying mechanism. Never cast blindly or assume the feature is always available.

Example file `SecureDirectoryStreamDemo.java`, reading only a file inside a temporary directory created by the program:

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

Compile:

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

In the supported branch, `newByteChannel` accepts the relative name `data.txt` and operates against the open directory stream. This is an API example for a single entry; in a real service, you must validate input names, reject absolute names or `..`, ensure the initial handle opens a trusted directory, and implement a **fail-closed** policy if the environment requires race resistance and the provider does not support it.

**Important limitation:** holding a directory handle does not by itself verify **application access permissions on the content** or data being read. Inputs, objects, and permissions must be verified at the appropriate points. When precise OS-level control is required, native equivalents like `openat` or dedicated OS mechanisms may be necessary—Java NIO.2 does not guarantee all security properties across every filesystem.

## 6. Path Validation: Necessary but Insufficient

Suppose only direct filenames inside directory `root` are allowed:

~~~java
Path root = approvedRoot.toAbsolutePath().normalize();
Path candidate = root.resolve(requestedName).normalize();

if (!candidate.startsWith(root)) {
    throw new SecurityException("Path escapes root");
}
~~~

This is an **illustrative snippet inside a method** with input variables `approvedRoot` and `requestedName` already declared. It eliminates **name-based** path traversal cases such as `../../outside.txt` after normalization. However:

- `startsWith` checks path components, not the real target on the filesystem.
- Symlinks can point outside even when the normalized pathname stays under `root`.
- If another process has permission to change directory entries, a check at T1 does not protect an open at T2.
- If only **single-level filenames** are allowed, verify that `requestedName` is genuinely a single filename with no separators or `..` components before resolving.
- Restrict write permissions on the directory, use server-controlled filenames where appropriate, and use handle-relative APIs or atomic open options.

Validating input paths remains necessary because it defines scope. Clearly distinguish **path validation** from **filesystem object identity**; the two problems must be solved with appropriate mechanisms.

## 7. Read, Write, Modify, and Delete: Choose Measures by Action

| Goal | Insufficient approach | Better design direction |
| --- | --- | --- |
| Create only if absent, never overwrite | `if (!exists) write` | `CREATE_NEW` or `Files.createFile` |
| Disallow reading through final symlink | `isSymbolicLink` then `newInputStream` | Open with API supporting `NOFOLLOW_LINKS`; consider parent path too |
| Work in a mutable directory tree | Check real path then repeatedly open by full path | `SecureDirectoryStream` when provider supports it; policy if unsupported |
| Publish a complete file | Write directly to final file | Write to staging then `ATOMIC_MOVE`; check target replacement semantics |
| Delete only the selected entry | `isRegularFile(p)` then `delete(p)` | Locate entry relative to trusted directory handle; when suitable, `SecureDirectoryStream.deleteFile` |
| Limit bytes read | `Files.size(p)` then `readAllBytes(p)` | Read stream/channel with byte counter and stop immediately when limit exceeded |
| Update a versioned record | `read -> validate -> write` unlocked | Compare-and-set, optimistic locking with version, transaction, or appropriate unique constraint |

Being atomic at one step does not mean a multi-step business workflow is atomic. For example, creating a file successfully and then failing to insert a DB row still leaves an inconsistent state; when cross-resource consistency is needed, use transactions, compensation, or an appropriate protocol.

## 8. Non-File TOCTOU Example: Limits of Check-Before-Update

TOCTOU also occurs in APIs/DBs. Suppose two requests concurrently process a coupon code:

~~~text
A: SELECT remaining -> 1
B: SELECT remaining -> 1
A: UPDATE remaining -> 0; allow use
B: UPDATE remaining -> 0; also allow use
~~~

If the application relies only on the prior `SELECT`, both requests can be accepted. The right approach is to turn the condition into a **concurrency-controlled operation** at storage level, such as:

~~~sql
UPDATE coupon
SET remaining = remaining - 1
WHERE id = ? AND remaining > 0;
~~~

This SQL snippet only illustrates a conditional decrement operation. The application must inspect **the updated row count**, ensure proper locking/identifiers, and use appropriate transactions/isolation. If `UPDATE` affects 0 rows, reject the coupon use; do not confirm success using the stale `SELECT` result.

File and DB problems share the same nature: a "passing check" is not a guarantee that the condition still holds when another operation starts.

## 9. Solutions That Look Right but Still Have Races

### 9.1. "Check Again Right Before Opening"

~~~java
if (Files.exists(path) && Files.isReadable(path)) {
    // A race can still happen right here.
    try (var in = Files.newInputStream(path)) {
        // ...
    }
}
~~~

The window may be shorter, but it has not merged check+open into a single operation. `exists` and `isReadable` also have semantics that do not guarantee the subsequent open will succeed. Design around **appropriately constrained open/operation primitives** and handle the outcome at that operation itself.

### 9.2. "Just Use `synchronized`"

`synchronized` only applies between code paths using **the exact same monitor** within a single JVM; other workers, other JVMs, external processes, and attackers are not bound by it. Use it for internal synchronization, not as protection for shared upload files.

### 9.3. "Use `NOFOLLOW_LINKS` on the Check Call"

`Files.isRegularFile(path, NOFOLLOW_LINKS)` observes the link at a point in time. If opened afterward by a command without `NOFOLLOW_LINKS`, a swap window still exists. Even `NOFOLLOW_LINKS` on the open call must be evaluated alongside **ancestor path** risks.

### 9.4. "Compare `fileKey` Before and After"

`BasicFileAttributes.fileKey()` can sometimes help identify a file on supporting providers, but not all providers return reliable or stable keys. Comparing twice is still **post-event detection**, not a substitute for opening and operating on the same bound object. Once a write/delete has occurred on the wrong file, detecting it afterward may be too late.

### 9.5. "Just Catch `IOException` and Retry"

Retrying the same path without re-evaluating safety conditions can repeat the race or act on a new entry. Distinguish `FileAlreadyExistsException`, `NoSuchFileException`, `AccessDeniedException`, and `AtomicMoveNotSupportedException`; the response depends on the operation's contract.

### 9.6. "File Moves Are Atomic on Every Disk"

Regular `Files.move` has no universal atomic guarantee across all providers. `ATOMIC_MOVE` may also be unsupported, especially across different filesystems. Never assume a prior `exists` check solves target replacement in `ATOMIC_MOVE`, since the specification allows different semantics when the target already exists.

## 10. Design Process Against TOCTOU

1. **Identify invariants to preserve:** no overwrite; no reading outside the directory; no deleting the wrong file; only one request claims a job; no processing beyond allowed capacity.
2. **Identify actors and contention scope:** same-JVM threads, other processes, users with permissions to edit directory entries, symlinks, network filesystems, or DB transactions.
3. **Find an atomic primitive matching the contract:** `CREATE_NEW`, directory-handle operations, conditional updates, transactions, compare-and-set, or commit protocols.
4. **Keep stable handles/references when needed:** after opening the appropriate file/channel, prefer operating on that handle directly. Avoid checking a path and reopening by the same name when identity changes are hazardous.
5. **Protect directory entries and access permissions:** server-generated names, directories writable only by the service, appropriate no-follow options, and providers supporting `SecureDirectoryStream` when needed.
6. **Define behavior when a race fails:** normally treat "file already exists" as a valid conflict, not a reason to fall back to overwriting. Log minimal context and return an appropriate error.
7. **Test controlled interleavings:** use latches/barriers, mock hooks, or fixtures to force T1–actor state mutation–T2. Do not rely on `Thread.sleep(...)` hoping a race happens naturally.
8. **Verify on the actual deployment filesystem:** providers differ in symlink support, `SecureDirectoryStream`, atomic move, ACLs, and locking capabilities.

A useful negative test is having a second actor create the entry **immediately after the check**, then verifying the application does not overwrite it. For symlink races, test on an OS/provider that genuinely has symlink-creation privileges and clearly bound what is protected; do not extrapolate from results on a developer laptop.

## 11. Self-Check Questions

**Question 1.** `Files.notExists(path)` returns `true`; does that guarantee the subsequent `Files.writeString(path, ...)` creates a new file without overwriting?

**Answer:** No. The entry can appear after the check. If the requirement is "create new only," pass `CREATE_NEW` on the open/write call itself.

**Question 2.** Does `Files.createFile(path)` being atomic mean all content written across subsequent `write` calls is also atomic?

**Answer:** No. Atomicity here applies to check-and-create on the entry. Publishing complete content is a separate problem, usually requiring staging + atomic move and understanding filesystem guarantees.

**Question 3.** After `Path.toRealPath()`, is a service definitely immune to symlink races if it continues opening by that path?

**Answer:** No. `toRealPath` reflects the state at call time and does not lock entries. Examine who can modify parents and leverage directory-handle-relative opens or APIs with safe options.

**Question 4.** Why is `NOFOLLOW_LINKS` on a single `isRegularFile` call insufficient?

**Answer:** It is still a check separated from the open, so the entry can be swapped after checking. The option on the open operation itself is more effective for the final symlink, though it still does not protect ancestor paths by itself.

**Question 5.** Why does `synchronized` alone not stop an attacker from modifying a file via another process?

**Answer:** Java monitors only synchronize threads in the same JVM using that exact monitor. Other processes are not constrained by it.

**Question 6.** If the provider does not support `SecureDirectoryStream` while the system requires resistance against directory entry swaps during read/delete, what should be done?

**Answer:** Do not silently cast or fall back to check/open steps if doing so breaks the security invariant. Reject the feature, change provider/environment, tighten directory permissions, or build an appropriate native mechanism and test it.

## 12. References

- [Java SE 17 `Files` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `exists`, `notExists`, `createFile`, `newByteChannel`, `move`, and `ATOMIC_MOVE`.
- [Java SE 17 `SecureDirectoryStream` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): access relative to a directory handle, open/delete/move operations aimed at avoiding races.
- [Java SE 17 `LinkOption` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): semantics of `NOFOLLOW_LINKS`.
- [Java SE 17 `StandardOpenOption` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `TRUNCATE_EXISTING`, `WRITE`.
- [Java SE 17 `FileChannel` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `lock`, `tryLock`, and `force`.

**Core takeaway:** TOCTOU is a flaw of **multi-step protocols built on mutable state**. The solution is not shaving microseconds between check and use, but designing so the condition is enforced **within the constrained operation itself**, or maintaining a stable reference to the exact object being processed.
