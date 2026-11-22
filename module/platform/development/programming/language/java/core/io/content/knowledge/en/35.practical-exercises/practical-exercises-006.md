# Updating Files Using Write-Temp-Then-Replace in Java NIO.2

## 1. Practice Problem

Suppose an application has a `config.txt` containing a known-good configuration. To save a new configuration, the simple approach is to overwrite directly:

~~~java
Files.writeString(target, newContent, StandardCharsets.UTF_8);
~~~

This is an **illustrative code snippet** with `target` and `newContent` variables declared externally. If the application is interrupted after truncating the old file but before writing all of the new content, the target file may be empty or contain only part of the new version. A similar risk arises on disk full, mid-way serialization errors, or process termination.

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

Step 3, swap name via atomic move when provider supports it:
  config.txt        = VERSION_2
  .update-xxxxx.tmp = old name no longer exists
~~~

**If an error occurs before the publish step and there are no other writers**, the old target has not yet been affected by the replacement. If the move operation is executed atomically per contract and succeeds, a reader opening by the target name will not observe the new version being written byte by byte under that name.

However, four distinct guarantees must be understood:

1. **Serialization completeness:** the candidate version has all bytes and a valid format.
2. **Atomic visibility:** publishing the target name happens as an atomic operation, if supported by the filesystem.
3. **Durability:** whether data and the name change survive a crash or power loss intact.
4. **Concurrency control:** whether multiple writers are allowed to accidentally overwrite each other's updates.

A single `Files.move` call only helps solve the second goal. Do not assume it is a multi-file transaction, a full-metadata fsync, or an inter-process locking mechanism.

## 2. Proper Update Flow in Order

For a single file, the foundational workflow is:

1. Choose a `target` with a trusted parent and verified caller permissions.
2. Create a temporary file **in the same destination directory** using `Files.createTempFile(parent, prefix, suffix)`.
3. Write the **entire** content/serialized representation to the temporary file; if using `FileChannel`, loop over the actual bytes written.
4. Validate the candidate: syntax, size, checksum/version if business logic requires it.
5. Request synchronization of temp contents to the desired durability level using `FileChannel.force(...)` and **close the channel**.
6. Call `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE)` to request atomic publication.
7. If the move succeeds, treat the new version as published under the filesystem's semantics. If it fails, do not delete the old target to "help the move succeed"; clean up the temp file in `finally`.
8. If `ATOMIC_MOVE` is unsupported, apply the **pre-decided policy**: fail closed or deliberately allow a non-atomic fallback, never equating the two guarantee levels.

Do not place `Files.delete(target)` between step 5 and step 6. That breaks continuity: if the application dies after delete, the target disappears even though the temp file was already prepared.

### 2.1. Choosing the Right Location for the Temp File

~~~java
Path absolute = target.toAbsolutePath().normalize();
Path parent = absolute.getParent();
Path temp = Files.createTempFile(parent, ".update-", ".tmp");
~~~

This is a snippet; it will not run standalone without a `target` variable, imports, and error handling. Creating in the same parent usually places temp and target on the same filesystem, which is required for atomic rename on many systems. Creating a temp file with `Files.createTempFile("update-", ".tmp")` without a parent may place it in the default temp directory on **a different filesystem**, making an atomic move impossible.

`createTempFile` creates a new entry with a unique name, though it does not eliminate all risks if the directory allows an attacker to delete/swap entries; the staging directory must be under appropriate control.

### 2.2. Do Not Use a Fixed Temp Filename

~~~java
// Anti-pattern when multiple processes update concurrently:
Path temp = target.resolveSibling("config.tmp");
~~~

A fixed name easily causes contention, pre-occupation, or two runs overwriting each other. Use `createTempFile` so each run gets its own candidate and cleans up that run's exact `Path`.

## 3. Writing All Data and Handling Short Writes

A temporary file is only safe when **it is not published before all new data has finished writing**. You can use `Files.writeString` or `Files.write` for small payloads. For large content or direct syncing, `FileChannel` gives explicit control:

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
                throw new IOException("Temp file write made no progress");
            }
        }

        file.force(true);
    }
}
~~~

This is an **illustrative method**, requiring imports for `IOException`, `Path`, `ByteBuffer`, `FileChannel`, and `StandardOpenOption`.

- `FileChannel.write(src)` returns the actual number of bytes transferred and advances `src.position()` accordingly; never assume every call writes everything.
- `src.hasRemaining()` determines when all bytes in the candidate have been consumed.
- `force(true)` requests synchronizing file changes per the JDK contract; the goal is preparing the candidate data before publishing.
- Closing the channel with `try-with-resources` ensures no serializer code continues writing to temp after the preparation step.

If deserializing/serializing needs to handle very large continuous byte streams, route the data through `InputStream`/`OutputStream` so the whole payload is not held in RAM, and clearly define which steps flush, sync, verify, and close.

### 3.1. Writing to Temp Differs from Writing to Target

~~~java
// Dangerous for preserving the old file if serialization fails:
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    serializer.writeTo(out);
}
~~~

This is pseudocode, with `serializer` supplied by the application. `TRUNCATE_EXISTING` modifies the destination file immediately upon opening. If `serializer` throws mid-way, the old file is no longer intact.

The right approach in this model is performing all write operations on `temp`, then using move to swap the name at the end.

## 4. `ATOMIC_MOVE` Does Not Mean `REPLACE_EXISTING`

The `Files.move(source, target, options...)` API supports common options:

| Option | Meaning | Limits to Remember |
| --- | --- | --- |
| `StandardCopyOption.ATOMIC_MOVE` | Requests the move be performed as an atomic filesystem operation. | May throw `AtomicMoveNotSupportedException`. |
| `StandardCopyOption.REPLACE_EXISTING` | Allows replacing an existing target in a normal move. | Does not by itself make the operation atomic. |
| `StandardCopyOption.COPY_ATTRIBUTES` | Mainly used with `Files.copy` for metadata. | Not a solution for atomic publication. |

Example:

~~~java
Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
~~~

Something easily overlooked in the **Java 17 Javadoc**: when `ATOMIC_MOVE` is present, **other options are ignored**; if the target already exists, whether it is replaced or the operation fails is **implementation-specific**. Therefore:

~~~java
Files.move(
        temp, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

does not prove every provider supports **atomic replacement of an existing target**, even when source and target are in the same directory. The call above is commonly used on filesystems with atomic rename replacement, but production code must verify actual behavior and have a policy when the provider refuses.

**Do not call `Files.deleteIfExists(target)` before moving** to work around `FileAlreadyExistsException`. That creates a gap where readers may see the target missing; if the process dies after deletion, the old version is lost too.

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

This is a snippet requiring `Path`, `AtomicMoveNotSupportedException`, `StandardCopyOption`, and the variable `allowNonAtomicFallback`.

The two options have different meanings:

- **Fail closed:** if atomicity is mandatory (critical configuration, state files), report an error and do not publish. The old target is preserved under the assumption of no other writers.
- **Deliberate fallback:** only for resources that tolerate weaker guarantees (such as a regenerable cache), perform a normal move with `REPLACE_EXISTING`. The fallback **is not guaranteed atomic** and may fail partway depending on the provider.

Do not catch **every `IOException`** and fall back to `Files.copy(temp, target, REPLACE_EXISTING)`. A permission, storage, or open-target error does not mean atomic move is unsupported; direct copying can leave the target partially updated.

## 5. Distinguishing Atomic Visibility from Crash Durability

**Atomic visibility**: the publish operation swaps the target entry atomically when the filesystem satisfies the requirement.

**Durability**: data and name changes remain intact after power loss, kernel crash, or device failure.

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
Is the directory entry metadata durable after a crash?
    |
    v
Depends on OS, filesystem, storage, and sync protocol.
~~~

`FileChannel.force(boolean metaData)` on the temp file:

- `force(false)` requests syncing file contents (not necessarily all metadata).
- `force(true)` requests syncing file contents and metadata per contract.
- The strongest API guarantees apply to files on **local** storage devices; remote filesystems/providers have their own limitations.

However, **`force(true)` on the temp file does not automatically guarantee the directory entry rename is durable**. In Java 17 there is no universal portable procedure forcing every directory provider to sync name metadata after rename. If strict crash-safety is required, design and verify against the target OS/filesystem or choose a transactional storage layer.

`OutputStream.flush()` only pushes Java buffers downstream; it does not commit data to the device. `close()` likewise does not replace a full crash-consistency protocol.

## 6. Complete Java 17+ Program: Injecting Failure Before Publish, Then Succeeding

The program uses a **temporary directory owned by the application**. It creates `config.txt` containing `OLD`, deliberately injects an error **before move** to verify the target was not altered, then writes `NEW` and checks cleanup.

So the example can run on many providers, the method takes an `allowNonAtomicFallback` flag. The demo passes `true` to allow fallback if `ATOMIC_MOVE` is unsupported; **this is a choice for the practice exercise, not a default recommendation for critical files**. When production requires atomicity, pass `false`.

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
            throw new IOException("Target has no parent directory");
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
                        throw new IOException("Temp file write made no progress");
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

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 AtomicFileUpdateDemo.java
java AtomicFileUpdateDemo
~~~

**Expected stdout on a filesystem that supports replacing an existing target with atomic move or when the fallback branch is enabled:**

~~~text
failureInjected=true
afterFailure=OLD
afterSuccess=NEW
tempFiles=0
~~~

If the provider does not allow replacing an existing target with `ATOMIC_MOVE` and throws an exception other than `AtomicMoveNotSupportedException`, or if filesystem/permissions disallow moving, the program may throw `IOException` instead of printing the four lines above. Identical behavior is not promised across every platform.

### 6.1. Why Does Target Remain `OLD` After Injected Failure?

The error is raised **after writing and closing temp, but before moving**. The workflow never opened target to truncate or write, so in this demo with no external actor, `config.txt` still holds `OLD`. `finally` cleans up the partially or completely written temp file that was not published.

This tests **error handling while the process is running**, not a power-loss simulation; do not conclude the file is guaranteed to exist with exact content after any OS crash.

### 6.2. Why Can It Run Without Printing Which Move Mode Ran?

The program does not print `atomic=true/false` so stdout is not tied to a specific provider. If `ATOMIC_MOVE` is supported, that branch runs; if it throws `AtomicMoveNotSupportedException` and fallback is enabled, `REPLACE_EXISTING` is used. The two branches carry **different guarantee levels** even though the file check in a single simple run looks identical.

Production applications should log/record metrics for this downgrade event and usually disallow fallback for critical data.

### 6.3. Cleanup in `finally`

`Files.deleteIfExists(temp)` after a successful move normally does not find the temp path because the entry was moved. If writing/moving fails, it attempts to delete the candidate file.

**Production improvement:** if cleanup throws `IOException` in `finally`, it can mask the original error. A hardened implementation should catch cleanup errors, attach them as a **suppressed exception** to the primary error where possible, and avoid letting cleanup misreport publish status. Also handle cases where the process dies before `finally` runs: have a safe age/version-based orphan-temp cleanup job.

## 7. What Do Readers Observe During Replace?

When the provider supports atomic rename replacement:

~~~text
Before publish: target -> version A
Writing temp:   target -> version A, temp -> version B
After publish:  target -> version B
~~~

A reader opening `target` **after** a successful publish can read version B. A reader that already opened a handle to version A earlier **does not automatically switch** its handle to version B. On many POSIX-like filesystems, the old reader can continue reading the old inode; on Windows, sharing modes of open handles can even cause the move to fail.

Do not assume "every reader on every operating system always sees A or B the same way"; exact behavior depends on the provider, how readers open the file, and file handle lifetimes.

If a client reads half a file, closes the handle, then reopens and resumes by offset, the two halves could belong to two different versions. Read an entire version through **one handle** or use version IDs/consistent protocols.

## 8. Two Writers Can Still Cause Lost Updates

~~~text
target is currently A
Writer 1: read A -> compute B1 -> write temp1
Writer 2: read A -> compute B2 -> write temp2
Writer 1: atomic move temp1 -> target = B1
Writer 2: atomic move temp2 -> target = B2

B1 is overwritten by B2, even though each move may be atomic.
~~~

`ATOMIC_MOVE` has no semantics of "replace only if target is still the version I just read". Thus it **does not solve concurrency control by itself**.

Options include:

- **Single writer**: one process/thread owns the file and serializes all updates.
- **Cooperative file locks**: all writers follow the same locking protocol across the entire read → compute → publish cycle. Enforcement/availability depends on OS/filesystem.
- **Versioned files + manifest**: write immutable versioned files, then publish a pointer/manifest; concurrent updates to the manifest itself still need resolution.
- **Transactional storage/CAS**: when lost updates must be strictly prevented at the system level, use a data store supporting compare-and-swap or true transactions.

Checking `Files.size()`, `getLastModifiedTime()`, or checksums before moving only describes state at the moment of reading. Another writer can still change the file **after the check and before the move** (*TOCTOU*). Do not turn check-then-move into CAS with a mere `if` statement.

## 9. Preserving Metadata, Permissions, and Ownership

A rename-based update usually places a **new file object** at the target name. Therefore, attributes of the old file may not be preserved automatically:

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

This is an **illustrative snippet**, requiring `PosixFilePermission` and imports for `Files`/`Set`. The API can throw `UnsupportedOperationException` on providers without a POSIX view. Copying mode bits **is not enough** to preserve ACLs, owner, xattrs, and security policies. If the file holds sensitive data, a better choice may be setting permissions from a trusted configuration **when creating temp**, rather than blindly inheriting from an untrusted target.

Reading target metadata and applying it to temp also suffers from TOCTOU if another actor can swap target between the two steps. Ensure trusted parent directories and authorization per system design.

## 10. Symlinks, Hard Links, and Untrusted Directory Areas

The write-temp pattern does not create a path sandbox on its own:

1. If a user inputs `../../config.txt`, `Path.normalize()` alone is not enough to prove the operation stays inside the permitted area.
2. If an attacker can modify the parent directory, they can swap entries, symlinks, or temp files between API calls.
3. When target involves symbolic links or hard links, the semantics of replacing an entry versus modifying inode contents differ. Define application policy rather than assuming all providers behave identically.
4. `Files.exists(...)`/`isRegularFile(...)` followed by `Files.move(...)` is not an atomic check-and-replace transaction.
5. If path-race resistance is needed in shared untrusted directories, evaluate `SecureDirectoryStream`, directory permissions, directory-handle-relative APIs, and provider capabilities; if required guarantees cannot be met, fail closed or change architecture.

**The primary protection scope of this pattern is not publishing partially written output**, not defending against every actor with permission to alter filenames.

## 11. Updating Very Large Files or Complex Formats

When a file may exceed RAM:

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

    // serializer.writeTo(out) is an application API.
    serializer.writeTo(out);
}
~~~

This is **pseudocode** because `serializer` is undeclared. After closing output, run an appropriate temp-file sync step if durability is required, and only then publish; do not treat closing the stream as proof all data is durably on disk.

Note that the temp approach must hold **both old and new versions** simultaneously, incurring significant disk space overhead. `Files.getFileStore(path).getUsableSpace()` only reports information at the moment of the call and does not reserve exclusive space; you must still catch `IOException` on disk-full.

## 12. Failure Matrix

| Where Does the Failure Occur? | Impact While Process Is Running, Assuming No Other Writer | How to Handle |
| --- | --- | --- |
| Before creating temp | Old target untouched. | Report error. |
| While writing temp | Old target has no changes published; temp may be incomplete. | Do not move, clean up temp. |
| Candidate validation fails | Old target unpublished. | Discard candidate, clean up temp. |
| `force(temp)` throws | Proper flow never reached publish. | Do not move, keep old target. |
| Fault injection before move | Old target remains intact in demo. | Catch error, verify cleanup. |
| `ATOMIC_MOVE` unsupported | Required guarantee not met. | Fail closed or pre-approved fallback. |
| Move succeeded but caller missed response | Target may already have new version published. | Retry requires idempotency/versioning. |
| Power loss / crash | Cannot be fully inferred from Java APIs alone. | Test recovery and durability per filesystem. |

If the response to the caller is lost **after commit**, the caller may retry the same request. The design should consider request IDs, version tokens, or duplicate-handling mechanisms rather than assuming the previous attempt definitely failed.

### 12.1. Atomic Move Is Not a Multi-File Transaction

To update `users.json` and `permissions.json` to the same version, two atomic rename calls **do not form an atomic transaction across both files**. A reader may observe one file updated and the other still old.

This can be solved using versioned files and a manifest/pointer to the complete version, or storing data in a transactional store. The manifest itself also needs proper publish and recovery procedures.

## 13. Testing Guarantees Properly

### 13.1. Unit Testing Serialization with In-Memory Streams

Separate the core serializer from opening files:

~~~java
void writeRepresentation(OutputStream out, Config config)
        throws IOException {
    // Application API: write in the defined format order.
}
~~~

This is **pseudocode**, incomplete to compile because `Config` and the body are omitted. Test the serializer using `ByteArrayOutputStream` or `StringWriter` for empty data, Unicode, large records, encoding errors, and invalid input.

### 13.2. Integration Testing Temp Files

With `Files.move`, tests must run on a real filesystem. Key scenarios:

- Target starts with `OLD`, error before move: still `OLD`.
- Normal update: target becomes `NEW` with no orphan temp files.
- Atomic move unsupported: with fail-closed flag must throw and not alter target.
- Permitted fallback: document weaker guarantee, do not call it atomic.
- Metadata permissions/ACLs after replace match policy.
- Concurrent writers: test rules preventing last-writer-wins.
- Readers opened before and after publish: real OS-specific behavior.
- Insufficient disk space, missing permissions, open target handle, read-only directory, cleanup errors.

JUnit Jupiter provides `@TempDir` to create isolated test directories. In-memory stream unit tests cannot verify OS-specific renames, ACLs, locks, and crash recovery.

### 13.3. Crash Durability Testing Needs Dedicated Infrastructure

A passing Java test does not prove what happens when hardware loses power in a microsecond between steps. For strong durability requirements, use a protocol verified for the target filesystem/OS or a transactional system, along with isolated recovery and fault-injection tests. Do not treat `ATOMIC_MOVE` + `force(true)` as absolute proof across all storage.

## 14. Common Mistakes

### Mistake 1: Writing Directly to the Original File

`TRUNCATE_EXISTING` wipes old target content before writing finishes. **Fix:** write candidate to temp, validate, sync, and only then publish.

### Mistake 2: Creating Temp on Another Drive

Temp in `java.io.tmpdir` may live on a different filesystem. **Fix:** use `Files.createTempFile(parent,...)`.

### Mistake 3: Using a Fixed Temp Filename

Creating a fixed `config.tmp` invites collisions/races. **Fix:** `createTempFile` creates a fresh entry and always clean up.

### Mistake 4: Deleting Target Before `ATOMIC_MOVE`

Creates an absence gap and risks losing the old version. **Fix:** do not pre-delete target; use provider-supported replace semantics.

### Mistake 5: Assuming `REPLACE_EXISTING` Guarantees Atomic Replace Alongside `ATOMIC_MOVE`

When `ATOMIC_MOVE` is set, other options are ignored; existing target behavior is implementation-specific. **Fix:** handle exceptions and verify the real provider.

### Mistake 6: Catching Every `IOException` and Copying Over Target

Can leave target partial and mask the root error. **Fix:** allow fallback only per explicit policy, never silently downgrade guarantees.

### Mistake 7: Not Handling Short Writes

`FileChannel.write` does not promise writing the entire buffer in one call. **Fix:** loop on `remaining()`.

### Mistake 8: Assuming `force` Before Move Guarantees Crash Durability

Syncing temp does not automatically sync directory rename metadata. **Fix:** adopt a dedicated crash-consistency strategy when needed.

### Mistake 9: Ignoring Permissions on the New File

Temp has its own metadata; replacement does not necessarily preserve the old target's ACLs/owner. **Fix:** apply metadata policy to temp before publishing and verify.

### Mistake 10: Two Writers Writing Without Coordination

Atomic rename does not prevent lost updates. **Fix:** single-writer, locking, or versioning/CAS/transactions.

### Mistake 11: Ignoring Symlinks and Path Traversal

Temp writing in the same directory does not block an attacker swapping directory entries. **Fix:** trusted root, name validation, permission controls, and secure directory handle mechanisms where needed.

### Mistake 12: Cleaning Up Temp After Failure and Masking the Root Error

`finally` can throw during cleanup. **Fix:** preserve the primary exception and attach cleanup exceptions via `addSuppressed(...)` when appropriate; log orphan temps.

### Mistake 13: Not Bounding Temp Disk Usage

Space is needed for both old and new versions. **Fix:** disk/size quotas and disk-full handling.

### Mistake 14: Reporting Success Before Publishing

If the move fails after the server sends ACK, the caller gets false information. **Fix:** report success only after reaching the business commit condition, with idempotency on retries.

## 15. Self-Check Exercises

1. **Why should you avoid `Files.writeString(target, text)` directly for critical configs?** It can truncate/write partially if an error occurs.
2. **Why should temp reside in the same parent?** Increases the chance of sharing a filesystem so atomic move works.
3. **How is `Files.createTempFile` better than a fixed filename?** Creates a unique new entry, preventing multiple runs from colliding on the same temp file.
4. **Is `ATOMIC_MOVE` always supported?** No; it may throw `AtomicMoveNotSupportedException`.
5. **Does `ATOMIC_MOVE` paired with `REPLACE_EXISTING` always replace an existing target?** No; other options are ignored in Java 17, and existing-target behavior is implementation-specific.
6. **Should you delete target before moving?** No, because that creates a window with no target.
7. **If atomicity is mandatory, how should unsupported errors be handled?** Fail closed; do not downgrade to non-atomic.
8. **Why is a `FileChannel` write loop needed?** `write` returns actual bytes written, which may be fewer than remaining.
9. **Does `force(true)` before rename prove the rename is durable on power loss?** No.
10. **Can two writers cause a lost update even if each move is atomic?** Yes.
11. **Does the new file automatically inherit the old target's ACL/owner?** No.
12. **Does a reader already holding the old file open switch automatically to the new version after rename?** Do not assume so.
13. **Does falling back to `Files.copy` guarantee avoiding partial files?** No, it can update partially.
14. **If updating three files, do three atomic moves form a transaction?** No.
15. **If the serializer fails, what state must target be in before publish?** Still the old version, assuming no other writer.
16. **Why validate user-supplied paths?** A temp strategy does not stop path traversal/symlink races.
17. **How should failures before publish be tested?** Fault injection after writing temp and before moving; verify target file and cleanup.
18. **Why is power loss after move but before response hard to handle?** The caller may not know commit occurred; versioning/idempotency is required.
19. **When should a database be chosen instead?** When multi-object transactions, optimistic locking/CAS, or strong durability are needed.
20. **What problem arises if the new file is twice as large?** Additional temporary disk space is required to hold both old and new versions.

## 16. Java 17 Official References

- [Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): move contract and `ATOMIC_MOVE`.
- [StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `ATOMIC_MOVE`, `REPLACE_EXISTING`.
- [Files.createTempFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#createTempFile(java.nio.file.Path,java.lang.String,java.lang.String,java.nio.file.attribute.FileAttribute...)): creating temp in a specified directory.
- [FileChannel.force](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean)): requesting sync of file data and metadata.
- [FileChannel.write](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#write(java.nio.ByteBuffer)): actual bytes written.
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): directory-handle-relative operations when supported by the provider.

**Remember:** To update a file without exposing a half-written version to readers, **create temp in the same directory → write/verify/force appropriately → close → atomic move if supported → clean up temp**. Never pre-delete target, never silently downgrade to copy/non-atomic, and never equate atomic visibility with crash durability, transactions, or multi-writer control.