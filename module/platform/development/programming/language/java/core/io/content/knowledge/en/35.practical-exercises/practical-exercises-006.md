# Updating Files via Write-Temp-Then-Replace in Java NIO.2

## 1. Practice Problem

Suppose an application has a `config.txt` file containing a stable working configuration. To save a new configuration, the simple approach is to overwrite directly:

~~~java
Files.writeString(target, newContent, StandardCharsets.UTF_8);
~~~

This is an **illustrative snippet** with `target` and `newContent` variables declared outside. If the application is interrupted after truncating the old file but before writing all the new content, the target file may become empty or contain only a partial new version. The same risk occurs on disk full, mid-serialization errors, or process termination.

The **write-temp-then-replace** pattern separates preparing data from publishing data:

~~~text
Initially:
  config.txt = VERSION_1

Step 1, create candidate:
  .update-xxxxx.tmp = (empty)
  config.txt        = VERSION_1

Step 2, write/validate new version:
  .update-xxxxx.tmp = VERSION_2
  config.txt        = VERSION_1

Step 3, rename via atomic move when supported by provider:
  config.txt        = VERSION_2
  .update-xxxxx.tmp = old name no longer exists
~~~

**If a failure happens before the publish step and no other writer exists**, the old target remains untouched by the replacement operation. If the move executes atomically per contract and succeeds, a reader opening the target by name will never observe byte-by-byte writing of the new version under that name.

However, four distinct guarantees must be understood:

1. **Serialization completion:** the candidate version has all bytes and a valid format.
2. **Atomic visibility:** publishing the target name happens as an atomic operation, if supported by the filesystem.
3. **Durability:** whether the data and name change survive a crash or power loss intact.
4. **Concurrency control:** whether multiple writers are prevented from accidentally overwriting each other's updates.

A single `Files.move` call only helps address the second goal. Do not assume it provides multi-file transactions, full metadata fsync, or inter-process locking.

## 2. Properly Ordered Update Flow

For a single file, the foundational workflow is:

1. Choose a `target` with a trusted parent and verified caller permissions.
2. Create a temporary file **in the same destination directory** using `Files.createTempFile(parent, prefix, suffix)`.
3. Write the **entire** content/serialized representation into the temporary file; if using `FileChannel`, loop over the actual bytes written.
4. Validate the candidate: syntax, size, checksum/version if required by business logic.
5. Request synchronization of the temp content to the desired durability level using `FileChannel.force(...)` and **close the channel**.
6. Call `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE)` to request atomic publication.
7. If the move succeeds, treat the new version as published per filesystem semantics. If it fails, do not delete the old target to "help the move work"; clean up the temp file in `finally`.
8. If `ATOMIC_MOVE` is unsupported, apply your **decided policy**: fail closed or deliberately allow a non-atomic fallback, without equating the two levels of guarantee.

Do not place `Files.delete(target)` between step 5 and step 6. That breaks continuity: if the process dies after deleting, the target disappears even though the temp file was ready.

### 2.1. Choosing the Right Location for Temp

~~~java
Path absolute = target.toAbsolutePath().normalize();
Path parent = absolute.getParent();
Path temp = Files.createTempFile(parent, ".update-", ".tmp");
~~~

This is a code snippet; it will not run standalone without a `target` variable, imports, and error handling. Creating under the same parent usually keeps temp and target on the same filesystem, which is required for atomic rename on many systems. Creating temp with `Files.createTempFile("update-", ".tmp")` without a parent may place it in the default temp directory on a **different filesystem**, making an atomic move impossible.

`createTempFile` creates a new entry with a unique name, yet does not eliminate all risks if the directory allows an attacker to delete/swap entries; the staging directory must have proper access controls.

### 2.2. Do Not Use a Fixed Temp Filename

~~~java
// Anti-pattern when multiple processes update concurrently:
Path temp = target.resolveSibling("config.tmp");
~~~

A fixed name easily causes contention, pre-existing file conflicts, or two runs overwriting each other. Use `createTempFile` so each run gets its own candidate and cleans up that exact `Path`.

## 3. Writing All Data and Handling Short Writes

A temporary file is only safe if **it is never published before all new data has finished writing**. You can use `Files.writeString` or `Files.write` for small payloads. For large content or direct syncing, `FileChannel` gives explicit control:

~~~java
static void writeCandidate(Path temp, byte[] bytes) throws IOException {
    try (FileChannel file = FileChannel.open(
            temp,
            StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING)) {

        ByteBuffer src = ByteBuffer.wrap(bytes);
        while (src.hasRemaining()) {
            int n = file.write(src);
            if (n == 0) {
                throw new IOException("Ghi file tạm không tiến triển");
            }
        }

        file.force(true);
    }
}
~~~

This is an **illustrative method**, requiring imports for `IOException`, `Path`, `ByteBuffer`, `FileChannel`, and `StandardOpenOption`.

- `FileChannel.write(src)` returns the actual bytes transferred and advances `src.position()` accordingly; never assume a single call writes everything.
- `src.hasRemaining()` determines when all bytes in the candidate have been consumed.
- `force(true)` requests synchronizing file changes per the JDK contract; the goal is preparing the candidate data before publishing.
- Closing the channel via `try-with-resources` ensures no serializer code keeps writing to temp after the preparation step.

If serialization/deserialization involves very large contiguous byte payloads, stream data via `InputStream`/`OutputStream` instead of holding everything in RAM, while clearly defining which steps flush, sync, verify, and close.

### 3.1. Writing to Temp vs. Writing to Target

~~~java
// Dangerous for preserving the old file if serialization fails:
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    serializer.writeTo(out);
}
~~~

This is pseudocode; `serializer` is supplied by the application. `TRUNCATE_EXISTING` alters the target file the moment it opens. If `serializer` throws mid-write, the old file is no longer intact.

The right approach in this pattern is to perform all write operations on `temp`, then rename via move at the end.

## 4. `ATOMIC_MOVE` Does Not Imply `REPLACE_EXISTING`

The `Files.move(source, target, options...)` API supports common options:

| Option | Meaning | Limit to Remember |
| --- | --- | --- |
| `StandardCopyOption.ATOMIC_MOVE` | Requests the move be performed as an atomic filesystem operation. | May throw `AtomicMoveNotSupportedException`. |
| `StandardCopyOption.REPLACE_EXISTING` | Allows replacing an existing target in a normal move. | Does not by itself make the operation atomic. |
| `StandardCopyOption.COPY_ATTRIBUTES` | Mainly used with `Files.copy` for metadata. | Not a solution for atomic publication. |

Example:

~~~java
Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
~~~

An easily overlooked detail in the **Java 17 Javadoc**: when `ATOMIC_MOVE` is present, **other options are ignored**; if the target already exists, whether it is replaced or the operation fails is **implementation-specific**. Therefore:

~~~java
Files.move(
        temp, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

does not prove every provider supports **atomic replacement of an existing target**, even when source and target share a directory. The call above is commonly used on filesystems with atomic rename replacement, yet production code must test actual behavior and define a policy when the provider rejects it.

**Never call `Files.deleteIfExists(target)` before moving** to work around `FileAlreadyExistsException`. Doing so opens a gap where readers see the target missing; if the process dies after deletion, the old version is lost too.

### 4.1. When `ATOMIC_MOVE` Is Unsupported

~~~java
try {
    Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException unsupported) {
    if (!allowNonAtomicFallback) {
        throw unsupported;
    }

    Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
}
~~~

This is a code snippet requiring `Path`, `AtomicMoveNotSupportedException`, `StandardCopyOption`, and an `allowNonAtomicFallback` variable.

The two options have different semantics:

- **Fail closed:** if atomicity is mandatory (critical config, state files), report an error and do not publish. The old target is preserved assuming no other writer intervenes.
- **Deliberate fallback:** only for resources permitting weaker guarantees (e.g., regenerable caches), fall back to a regular move with `REPLACE_EXISTING`. The fallback **is not guaranteed atomic** and can fail mid-step depending on the provider.

Do not catch **every `IOException`** and fall back to `Files.copy(temp, target, REPLACE_EXISTING)`. A permission/storage/locked-target error does not mean missing atomic support; direct copying can leave the target half-updated.

## 5. Distinguishing Atomic Visibility and Crash Durability

**Atomic visibility**: publishing swaps the target entry atomically when the filesystem satisfies the requirement.

**Durability**: data and name changes remain intact after power loss, kernel crash, or hardware failure.

~~~text
write temp
    |
    v
file.force(true)    <- requests syncing TEMP data/metadata
    |
    v
Files.move(temp, target, ATOMIC_MOVE)
    |
    v
Is the entry metadata in the DIRECTORY durable after a crash?
    |
    v
Depends on OS, filesystem, storage, and sync protocol.
~~~

`FileChannel.force(boolean metaData)` on the temp file:

- `force(false)` requests syncing file content (not necessarily all metadata).
- `force(true)` requests syncing content and metadata per contract.
- The strongest API guarantees apply to files on **local** storage devices; remote filesystems/providers have their own limitations.

However, **`force(true)` on the temp file does not automatically guarantee the directory entry rename is durable**. Java 17 has no universal portable procedure forcing every directory provider to sync name metadata after a rename. If strict crash-safety is required, design and verify on the target OS/filesystem or choose a transactional storage layer.

`OutputStream.flush()` only pushes Java buffers downstream; it does not promise data reached the device. `close()` likewise does not replace a full crash-consistency protocol.

## 6. Complete Java 17+ Program: Testing Failure Before Publish, Then Succeeding

The program uses an **application-owned temporary directory**. It creates `config.txt` containing `OLD`, intentionally injects an error **before moving** to verify the target is untouched, then writes `NEW` and checks cleanup.

To let the example run across multiple providers, the method accepts an `allowNonAtomicFallback` flag. The demo passes `true` to allow fallback if `ATOMIC_MOVE` is unsupported; **this is a choice for the exercise, not a default recommendation for critical files**. When production requires atomicity, pass `false`.

Save as `AtomicFileUpdateDemo.java`:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public class AtomicFileUpdateDemo {

    static void updateFile(
            Path target,
            byte[] newBytes,
            boolean allowNonAtomicFallback,
            boolean failBeforeMove) throws IOException {

        Path absolute = target.toAbsolutePath().normalize();
        Path directory = absolute.getParent();
        if (directory == null) {
            throw new IOException("Target không có thư mục cha");
        }

        Path temp = Files.createTempFile(
                directory, ".update-", ".tmp");

        try {
            try (FileChannel file = FileChannel.open(
                    temp,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer bytes = ByteBuffer.wrap(newBytes);
                while (bytes.hasRemaining()) {
                    int n = file.write(bytes);
                    if (n == 0) {
                        throw new IOException("Ghi file tạm không tiến triển");
                    }
                }

                file.force(true);
            }

            if (failBeforeMove) {
                throw new IOException("Injected failure before move");
            }

            try {
                Files.move(
                        temp, absolute,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException unsupported) {
                if (!allowNonAtomicFallback) {
                    throw unsupported;
                }

                Files.move(
                        temp, absolute,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("file-update-");
        Path target = dir.resolve("config.txt");

        try {
            Files.writeString(
                    target, "OLD", StandardCharsets.UTF_8);

            boolean injected = false;
            try {
                updateFile(
                        target,
                        "IGNORED".getBytes(StandardCharsets.UTF_8),
                        true,
                        true);
            } catch (IOException expected) {
                injected = true;
            }

            System.out.println("failureInjected=" + injected);
            System.out.println("afterFailure=" +
                    Files.readString(target, StandardCharsets.UTF_8));

            updateFile(
                    target,
                    "NEW".getBytes(StandardCharsets.UTF_8),
                    true,
                    false);

            System.out.println("afterSuccess=" +
                    Files.readString(target, StandardCharsets.UTF_8));

            long leftovers;
            try (Stream<Path> entries = Files.list(dir)) {
                leftovers = entries.filter(p ->
                        p.getFileName().toString().endsWith(".tmp"))
                        .count();
            }
            System.out.println("tempFiles=" + leftovers);
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile/run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 AtomicFileUpdateDemo.java
java AtomicFileUpdateDemo
~~~

**Expected stdout on filesystems allowing replacement of an existing target via atomic move or with the fallback branch enabled:**

~~~text
failureInjected=true
afterFailure=OLD
afterSuccess=NEW
tempFiles=0
~~~

If the provider disallows replacing an existing target via `ATOMIC_MOVE` and throws an exception other than `AtomicMoveNotSupportedException`, or if filesystem/permissions disallow the move, the program may throw `IOException` instead of printing the four lines above. Identical behavior across all platforms is not promised.

### 6.1. Why Does Target Remain OLD After the Injected Failure?

The error is triggered **after writing and closing temp, but before moving**. The workflow never opened `target` to truncate or write, so in this demo with no concurrent actors, `config.txt` still contains `OLD`. `finally` cleans up the temp file that was partially written or complete yet unpublished.

This tests **error handling while the process is still running**, not a power-loss simulation; do not conclude the file is guaranteed to exist with exact contents after every OS crash.

### 6.2. Why Does It Run Without Printing the Move Strategy?

The program does not print `atomic=true/false` so stdout is not tied to a specific provider. If `ATOMIC_MOVE` is supported, that branch runs; if it throws `AtomicMoveNotSupportedException` and fallback is enabled, `REPLACE_EXISTING` is used. The two branches carry **different guarantee levels** even though the file-check output in a simple single run looks identical.

Production applications should log/emit metrics on this downgrade event and generally forbid fallback for critical data.

### 6.3. Cleanup in `finally`

`Files.deleteIfExists(temp)` after a successful move normally finds no temp path because the entry has already been moved. If writing or moving fails, it attempts to delete the candidate file.

**Area for production improvement:** if cleanup throws `IOException` inside `finally`, it can mask the original error. A resilient implementation should catch cleanup errors, attach them via `addSuppressed(...)` to the primary error where possible, and never let cleanup cause the program to misreport publication status. You must also handle cases where the process dies before running `finally`: implement a safe orphan-temp cleanup job based on age/version.

## 7. What Do Readers Observe During Replacement?

When the provider supports atomic rename replacement:

~~~text
Before publish: target -> version A
Writing temp:   target -> version A, temp -> version B
After publish:  target -> version B
~~~

Readers opening `target` **after** publication succeeds can read version B. Readers that already opened a handle to version A beforehand **do not automatically switch** handles to version B. On many POSIX-style filesystems, old readers can keep reading the old inode; on Windows, sharing locks on open handles can even cause the move to fail.

Never assume "every reader on every OS always sees A or B the same way"; exact behavior depends on the provider, how the reader opens the file, and handle lifetimes.

If a client reads half a file, closes the handle, then reopens and reads from an offset, the two halves can belong to two different versions. Read an entire version through **one handle** or use version IDs / a consistent protocol.

## 8. Two Writers Can Still Cause Lost Updates

~~~text
target is currently A
Writer 1: reads A -> computes B1 -> writes temp1
Writer 2: reads A -> computes B2 -> writes temp2
Writer 1: atomic move temp1 -> target = B1
Writer 2: atomic move temp2 -> target = B2

B1 is overwritten by B2, even though each move may be atomic.
~~~

`ATOMIC_MOVE` does not mean "replace only if target is still the version I just read". Therefore, it **does not solve concurrency control by itself**.

Options include:

- **Single writer**: one process/thread owns the file and serializes all updates.
- **Cooperative file locks**: all writers obey the same locking protocol across the entire read → compute → publish cycle. Enforcement/availability varies by OS/filesystem.
- **Versioned files + manifest**: write immutable versioned files, then publish a pointer/manifest; you still need to coordinate two writers updating the manifest.
- **Transactional storage/CAS**: when lost updates must be strictly prevented at the system level, use a data store supporting compare-and-swap or real transactions.

Checking `Files.size()`, `getLastModifiedTime()`, or checksums before moving only describes the state at read time. Another writer can still modify the file **after the check and before the move** (*TOCTOU*). A plain `if` statement does not turn check-then-move into CAS.

## 9. Preserving Metadata, Permissions, and Ownership

Updating via rename typically puts a **new file object** under the target name. Thus attributes of the old file may not be preserved automatically:

- POSIX permissions (rwx), owner, group.
- Filesystem/provider ACLs.
- Modified time, creation time, extended attributes, security labels.
- Hard links: other names pointing to the old inode may still retain the old version.

Example copying permissions only when the provider actually supports POSIX:

~~~java
Set<PosixFilePermission> permissions =
        Files.getPosixFilePermissions(target);

Files.setPosixFilePermissions(temp, permissions);
~~~

This is an **illustrative snippet**, requiring `PosixFilePermission` and `Files`/`Set` imports. The API may throw `UnsupportedOperationException` on providers without a POSIX view. Copying mode bits **is not enough** to preserve ACLs, owner, xattrs, and security policies. If the file holds sensitive data, a better choice may be setting permissions from trusted configuration **at temp creation time** rather than blindly inheriting from an untrusted target.

Reading target metadata and applying it to temp also suffers from TOCTOU if another actor can swap target between the two calls. Ensure a trusted parent directory and proper system authorization.

## 10. Symlinks, Hard Links, and Untrusted Directories

The temporary-write pattern does not automatically create a path sandbox:

1. If a user supplies `../../config.txt`, `Path.normalize()` alone does not prove the operation stays inside an allowed root.
2. If an attacker can modify the parent directory, they can swap entries, symlinks, or temp files between API calls.
3. When the target involves symbolic links or hard links, replacing a directory entry has different semantics from modifying inode content. Define application policy explicitly rather than assuming all providers behave alike.
4. `Files.exists(...)`/`isRegularFile(...)` followed by `Files.move(...)` is not an atomic check-and-replace transaction.
5. If path-race resistance in shared untrusted directories is required, inspect `SecureDirectoryStream`, directory permissions, directory-handle-relative APIs, and provider capabilities; if required guarantees cannot be met, fail closed or change architecture.

**This pattern's primary protection is preventing readers from seeing half-written new output**, not blocking actors who already have permission to rename files.

## 11. Updating Very Large Files or Complex Formats

When a file can exceed RAM:

~~~text
Application supplies new data
     |
     v
Stream serializer -> temporary file
     |
     v
Re-parse/validate temp as needed
     |
     v
Sync temp per contract
     |
     v
Close writer -> atomic move -> target
~~~

Streaming serializer example:

~~~java
try (OutputStream out = Files.newOutputStream(
        temp,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {

    // serializer.writeTo(out) is an application-provided API.
    serializer.writeTo(out);
}
~~~

This is **pseudocode** because `serializer` is undeclared. After closing output, run an appropriate temp-file sync step if durability is required, and only then publish; never treat closing a stream as proof that all bytes are durable on disk.

Note that the temp-file approach requires holding **both the old and new versions** simultaneously, incurring significant disk-space overhead. `Files.getFileStore(path).getUsableSpace()` only reports space at call time and does not reserve storage exclusively; you must still catch `IOException` on disk full.

## 12. Failure Matrix

| Where Did Failure Occur? | Impact While Process Is Running (Assuming No Other Writer) | How to Handle |
| --- | --- | --- |
| Before creating temp | Old target untouched. | Report error. |
| While writing temp | Old target has not published changes; temp may be incomplete. | Do not move; clean up temp. |
| Candidate validation fails | Old target unpublished. | Discard candidate; clean up temp. |
| `force(temp)` throws error | Proper flow has not reached publish. | Do not move; keep old target. |
| Fault injection before move | Old target remains intact in demo. | Catch error; verify cleanup. |
| `ATOMIC_MOVE` unsupported | Requested guarantee cannot be met. | Fail closed or pre-approved fallback. |
| Move succeeds but caller misses response | Target may already have published the new version. | Retries need idempotency/versioning. |
| Power loss / crash | Cannot be inferred solely from Java APIs. | Test recovery and durability per filesystem. |

If the response to the caller is lost **after commit**, the caller may retry the same request. Designs should consider request IDs, version tokens, or idempotent handling rather than assuming the prior attempt definitely failed.

### 12.1. Atomic Move Is Not a Multi-File Transaction

To update `users.json` and `permissions.json` to the same version, two atomic rename calls **do not form an atomic transaction across both files**. A reader may observe one file updated and the other still old.

This can be addressed with versioned files plus a manifest/pointer to the complete version, or by storing data in a transactional store. The manifest itself also needs proper publish and recovery procedures.

## 13. Testing the Right Guarantees

### 13.1. Unit Testing Serialization with In-Memory Streams

Separate core serialization from file opening:

~~~java
void writeRepresentation(OutputStream out, Config config)
        throws IOException {
    // Application API: write in the defined format order.
}
~~~

This is **pseudocode**, not compilable as-is because `Config` and the body are omitted. Test the serializer using `ByteArrayOutputStream` or `StringWriter` for empty data, Unicode, large records, encoding errors, and invalid inputs.

### 13.2. Integration Testing Temporary Files

For `Files.move`, tests must run on a real filesystem. Important scenarios:

- Target initially holds `OLD`, failure before move: remains `OLD`.
- Normal update: target becomes `NEW` with zero orphan temp files.
- Atomic move unsupported: with fail-closed flag must throw and leave target unchanged.
- Fallback enabled: record the weaker guarantee level; do not label it atomic.
- Metadata permissions/ACLs after replacement match policy.
- Concurrent writers: test rules preventing silent last-writer-wins.
- Readers opened before and after publish: verify actual OS behavior.
- Disk full, permission denied, target locked open, read-only directory, cleanup errors.

JUnit Jupiter provides `@TempDir` for isolated test directories. In-memory stream unit tests are insufficient to verify OS-specific renames, ACLs, locks, and crash recovery.

### 13.3. Testing Crash Durability Requires Dedicated Infrastructure

A passing Java test does not prove what happens if hardware loses power at an arbitrary microsecond between steps. For strong durability requirements, use protocols proven on the target filesystem/OS or a transactional system, alongside recovery testing and isolated fault injection. Never treat `ATOMIC_MOVE` + `force(true)` as absolute proof across every storage stack.

## 14. Common Mistakes

### Mistake 1: writing directly to the original file

`TRUNCATE_EXISTING` destroys the target's old content before writing completes. **Fix:** write candidate to temp, validate, sync, and only then publish.

### Mistake 2: creating temp on a different volume

Temp under `java.io.tmpdir` may reside on another filesystem. **Fix:** use `Files.createTempFile(parent,...)`.

### Mistake 3: using a fixed temp filename

A fixed `config.tmp` invites collisions and races. **Fix:** use `createTempFile` for a unique entry and always clean up.

### Mistake 4: deleting target before calling `ATOMIC_MOVE`

Creates a visibility gap and risks losing the old version. **Fix:** never pre-delete target; rely on provider-supported replacement semantics.

### Mistake 5: assuming `REPLACE_EXISTING` guarantees atomic replace alongside `ATOMIC_MOVE`

When `ATOMIC_MOVE` is present, other options are ignored; existing-target behavior is implementation-specific. **Fix:** handle exceptions and verify actual provider behavior.

### Mistake 6: catching all `IOException`s and copying onto target

Can leave target half-written and mask the root error. **Fix:** fall back only per explicit policy; never silently downgrade guarantees.

### Mistake 7: failing to handle short writes

`FileChannel.write` does not promise to write the whole buffer in one call. **Fix:** loop while `remaining()` > 0.

### Mistake 8: thinking `force` before move guarantees crash durability

Syncing temp does not automatically sync directory rename metadata. **Fix:** implement a dedicated crash-consistency strategy when needed.

### Mistake 9: ignoring permissions on the new file

Temp has its own metadata; replacement does not necessarily preserve the old target's ACLs/owner. **Fix:** apply metadata policies to temp before publishing and verify.

### Mistake 10: two writers updating without coordination

Atomic rename does not prevent lost updates. **Fix:** single-writer, locks, or versioning/CAS/transactions.

### Mistake 11: ignoring symlinks and path traversal

Writing temp in the same directory does not stop an attacker who can modify directory entries. **Fix:** trusted root, name validation, permission checks, and secure directory handles when needed.

### Mistake 12: cleaning up temp after a write failure while masking the original error

`finally` can throw a cleanup error. **Fix:** preserve the original exception and attach cleanup errors via `addSuppressed(...)` where appropriate; log orphan temps.

### Mistake 13: not bounding temp storage usage

Space is needed for both old and new versions. **Fix:** size/disk quotas and disk-full handling.

### Mistake 14: reporting success before publish

If the move fails after the server sends an ACK, the caller receives false confirmation. **Fix:** acknowledge only after business commit conditions are met, with idempotency for retries.

## 15. Self-Check Exercises

1. **Why shouldn't `Files.writeString(target, text)` be used directly for critical config?** It can truncate/leave partial content on error.
2. **Why should temp be in the same parent?** Increases the chance of sharing the same filesystem for atomic move.
3. **How is `Files.createTempFile` better than a fixed filename?** Creates a unique entry, preventing multiple runs from overwriting the same temp file.
4. **Is `ATOMIC_MOVE` always supported?** No; it can throw `AtomicMoveNotSupportedException`.
5. **Does `ATOMIC_MOVE` paired with `REPLACE_EXISTING` guarantee replacing an existing target?** No; other options are ignored per Java 17, and replacing an existing target is implementation-specific.
6. **Should target be deleted before moving?** No, as it creates a gap with no target.
7. **If atomicity is mandatory, how should unsupported providers be handled?** Fail closed; do not downgrade to non-atomic.
8. **Why is a write loop needed for `FileChannel`?** `write` returns actual bytes written, which may be fewer than remaining.
9. **Does `force(true)` before rename prove the rename is durable on power loss?** No.
10. **Can two writers cause lost updates even if every move is atomic?** Yes.
11. **Does the new file automatically inherit the old target's ACLs/owner?** No.
12. **Do readers that already opened the old version automatically switch to the new version after rename?** Do not assume so.
13. **Does falling back to `Files.copy` guarantee avoiding partial files?** No; it can update partially.
14. **If updating three files, do three atomic moves form a transaction?** No.
15. **If the serializer fails, what state must target be in prior to publish?** Still the old version, assuming no other writer.
16. **Why must user-supplied paths be validated?** The temp strategy does not prevent path traversal or symlink races.
17. **How should failures before publish be tested?** Fault injection right after writing temp and before moving; verify target content and cleanup.
18. **Why is power loss after move but before response tricky?** The caller may not know commit occurred; versioning/idempotency is required.
19. **When should a database be chosen instead?** When multi-object transactions, optimistic locking/CAS, or strong durability are required.
20. **What issue arises if the new file is twice as large?** Extra temporary disk space is needed to hold both old and new versions simultaneously.

## 16. Java 17 Reference Documentation

- [Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): move contract and `ATOMIC_MOVE`.
- [StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `ATOMIC_MOVE`, `REPLACE_EXISTING`.
- [Files.createTempFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#createTempFile(java.nio.file.Path,java.lang.String,java.lang.String,java.nio.file.attribute.FileAttribute...)): creating temp files in a specified directory.
- [FileChannel.force](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean)): requesting sync of file data and metadata.
- [FileChannel.write](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#write(java.nio.ByteBuffer)): actual bytes written.
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): directory-handle operations when supported by the provider.

**Remember:** To update a file without exposing half-written versions to readers, **create temp in the same directory → write/verify/force appropriately → close → atomic move if supported → clean up temp**. Never pre-delete the target, never silently downgrade guarantees to copy/non-atomic, and never equate atomic visibility with crash durability, transactions, or multi-writer concurrency control.
