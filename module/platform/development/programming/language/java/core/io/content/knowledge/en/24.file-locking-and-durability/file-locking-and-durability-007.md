# Writing to a Temporary File and Replacing the Destination in Java NIO.2

## 1. Why Write to a Temporary File Before Replacing?

When updating a critical file such as `config.json`, `settings.properties`, a small index, or a state file, writing directly to the destination file has a flaw: if the program terminates midway, the file may contain only **part of the new content**, become truncated, or become invalid.

Example of a risky operation:

```java
Files.writeString(
        Path.of("config.txt"),
        "version=2\nmode=production\n",
        StandardCharsets.UTF_8
);
```

This is only an illustrative snippet; it requires importing `java.nio.file.Files`, `Path`, and `java.nio.charset.StandardCharsets`. If the destination file already exists, `Files.writeString` with default options can overwrite and truncate the old content. If an I/O error occurs or the process dies after modifying part of the data, readers may encounter corrupted content.

The **write temporary file, then replace destination** pattern solves the problem structurally:

1. **Create a new temporary file** in the same directory/on the same filesystem as the destination.
2. **Write the entire new content** to the temporary file and validate it.
3. If durability is required, **synchronize the temporary file's data** using `FileChannel.force(true)`.
4. **Close the handle** of the temporary file.
5. Use `Files.move(temp, destination, ...)` to replace the destination name with the new file; prefer `ATOMIC_MOVE` if supported by the system.
6. **Clean up the temporary file** if it was not moved successfully; design recovery for leftover temporary files if the system crashes.

Before replacement, the destination file still holds the complete old version. If the rename/move step is supported **atomically**, readers opening the destination path see either the old version or the new version, never a half-written file produced by this process.

That **does not equate to a database transaction**, does not guarantee every filesystem supports atomic replacement, and is not sufficient to conclude "power loss cannot lose the new version". We must distinguish three concepts: content integrity prior to publication, atomicity of name replacement, and storage durability.

## 2. Before-and-After State Model

Suppose `settings.json` holds version V1 and we want to update to V2:

```text
Phase A — before writing:
  settings.json                 [complete V1]

Phase B — writing temporary file:
  settings.json                 [complete V1]
  .settings-47392.tmp           [V2 being written, unpublished]

Phase C — written/validated/forced/closed:
  settings.json                 [complete V1]
  .settings-47392.tmp           [complete V2]

Phase D — atomic move/replace:
  settings.json                 [complete V2]
  .settings-47392.tmp           [no longer at temporary name]
```

If an atomic `move` is supported by the filesystem, the name `settings.json` switches the referenced file object in a single publication step. If the move is **non-atomic**, there may be an intermediate window where the destination is missing or in another transitional state depending on filesystem/provider implementation.

While writing V2 to a temp file, avoid accidentally using a fixed name like `settings.tmp` that causes two processes to overwrite each other. `Files.createTempFile(parent, prefix, suffix)` allocates a fresh nonexistent name via a filesystem file-creation operation, which is safer than assembling timestamp-based names manually.

## 3. "Atomic", "Durable", and "Consistent" Are Three Distinct Requirements

| Requirement | Question | Common Tools | Limitations |
|---|---|---|---|
| New content valid before publication | Was V2 completely written and validated? | Write temp file, verify size/checksum/format | Only as good as the format validation checks |
| Atomic visibility of destination name | Does a reader opening the destination path see complete V1 or complete V2? | `Files.move(..., ATOMIC_MOVE)` when supported | Not supported by every filesystem/provider or replacement mode |
| Crash durability | On power loss, does V2 survive reboot? | `FileChannel.force(true)` on temp file; OS metadata/directory sync mechanisms | Standard Java APIs offer no portable full guarantee for directory `fsync` + rename |
| Preventing overwrites from another writer | Can Writer A clobber a version just published by B? | Writer coordination, version/CAS, locking at an appropriate layer | Atomic rename only makes publication atomic; it does not solve lost updates |
| Updating multiple files together | Do two files switch from V1 to V2 in one step? | Manifest/version design, journal, or dedicated transaction engine | A single move affects only one destination entry |

**Atomic visibility ≠ crash durability.** Even if the move succeeds and readers see V2, the application must not assume all directory metadata is safe across power loss. If strict crash recovery is required, consult the specific filesystem/OS contract, synchronize the directory via system interfaces if needed, or use a proven transaction/journal engine.

## 4. Why Should the Temp File Be in the Same Directory as the Destination?

A normal atomic rename operates **within the same filesystem**. If you create the temp file in the system-wide temp directory, the destination may reside on a different volume, causing `ATOMIC_MOVE` to be unsupported.

Example you should not assume is safe:

```java
Path temporary = Files.createTempFile("update-", ".tmp");
Path destination = Path.of("/mnt/data/config.json");
```

This illustrative snippet may create the temp file in `java.io.tmpdir`, while the destination lives on another filesystem. Even if the destination and temp paths look like they share a drive, mounts, bind mounts, or network filesystems can affect semantics.

Instead, choose **the destination's own parent directory**:

```java
Path destination = Path.of("config.json").toAbsolutePath();
Path parent = destination.getParent();
Path temporary = Files.createTempFile(parent, ".config-", ".tmp");
```

- `Files.createTempFile` creates a new file and returns a concrete `Path`, avoiding name collisions under normal conditions.
- Temp and destination reside in the same directory, increasing the likelihood that atomic move is supported.
- The temp path is typically **not** a long-lived backup file: after the move, the temporary name disappears as the file is renamed to the destination name.
- The parent directory must exist and permit creating, renaming, and deleting entries.
- For sensitive data, consider the default permissions of the temp file upon creation and apply permissions/ACLs per policy before publishing, because temp is a **new file object**.

Being in the same directory is only a **favorable precondition**, not a guarantee that `ATOMIC_MOVE` works; a provider/filesystem may still lack support or enforce its own replacement rules.

## 5. Writing All Data to the Temp File

When using `FileChannel`, a single call to `write(ByteBuffer)` **does not guarantee** the entire buffer was written. Check `hasRemaining()` and the byte count returned:

```java
static void writeFully(FileChannel channel, ByteBuffer source)
        throws IOException {
    while (source.hasRemaining()) {
        int n = channel.write(source);
        if (n == 0) {
            throw new IOException("Write made no progress");
        }
    }
}
```

This is an illustrative method requiring imports for `FileChannel`, `ByteBuffer`, and `IOException`. If the format has multi-byte binary fields, configure a consistent `ByteOrder`. If writing UTF-8, encode explicitly with `StandardCharsets.UTF_8`. Never use character count as byte count; UTF-8 characters can occupy more than one byte.

With the temp file created by `createTempFile`, open a channel to write:

```java
try (FileChannel channel = FileChannel.open(
        temporary,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    ByteBuffer bytes = StandardCharsets.UTF_8.encode("version=2\n");
    writeFully(channel, bytes);
    channel.force(true);
}
```

This snippet assumes `temporary` has been created with valid write permissions; corresponding imports must be declared. `TRUNCATE_EXISTING` here targets the **temp file**, not the destination file, so it does not harm V1. Closing the channel before moving also avoids restrictions on renaming open files on operating systems with different handle semantics.

### Validating the File Before Publishing

Completing `write` only confirms bytes were handed off to I/O. If the data is JSON, CSV, binary records, certificates, a manifest, or an index, consider **validating before moving**:

- Reasonable size and no truncation.
- Correct structure/version/schema as required.
- Valid values, cross-references, checksums, or hashes if required by the format.
- Permissions/owner/ACL appropriate for the application once the temp file becomes the destination.

You do not necessarily need to re-read the entire temp file for every file type; choose validation depth based on serializer reliability and the impact of publishing a broken file. For critical transactional data, design deliberate checks instead of merely waiting for `write` to return.

## 6. `Files.move`, `ATOMIC_MOVE`, and `REPLACE_EXISTING`

Java NIO.2 API:

```java
Files.move(
        temporary,
        destination,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING
);
```

- `ATOMIC_MOVE` **requires** the system to perform the move as an atomic filesystem operation. If impossible, it may throw `AtomicMoveNotSupportedException`.
- `REPLACE_EXISTING` is used in standard moves to allow replacing an existing destination name, subject to other provider limitations.
- **Important detail:** per the `Files.move` documentation, when `ATOMIC_MOVE` is specified, **other options are ignored**; if the target already exists, whether replacement succeeds or fails is **implementation-dependent**. Therefore, passing both options alone does not guarantee atomic replacement is supported on every system.
- If `ATOMIC_MOVE` fails, do not silently discard it and proceed as if the operation were still atomic.
- If you choose to fall back to a non-atomic move, treat it as a **change in guarantee level** affecting readers and error recovery.

You can try an atomic move first:

```java
try {
    Files.move(temp, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} catch (AtomicMoveNotSupportedException ex) {
    // Policy 1: report error and leave destination intact; clean up temp as appropriate.
    throw new IOException("Filesystem không hỗ trợ atomic move", ex);
}
```

This is an illustrative snippet requiring imports for `Path`, `Files`, `StandardCopyOption`, `AtomicMoveNotSupportedException`, and `IOException`. It implements a **require-atomic** policy: if unsupported, abort rather than silently downgrading guarantees.

On some providers, an atomic move when the target already exists can fail with `FileAlreadyExistsException` per implementation rules. When strict atomic replacement is needed, never treat that as a cue to delete the destination first and then rename: **deleting the destination first creates an observable gap**.

## 7. Complete Java 17+ Program: Writing a Temp File and Replacing the Destination

The following example creates a destination file containing `old`, writes `new` to a temp file **in the same directory**, calls `force(true)`, and closes the channel before moving. The example includes an **explicitly declared fallback policy**: if atomic replacement fails because the provider does not support atomic move or does not allow atomically replacing an existing target, the program permits a non-atomic `REPLACE_EXISTING` move. In production systems requiring strict atomicity, set `ALLOW_NON_ATOMIC_FALLBACK` to `false` to abort instead of downgrading guarantees.

Save as **`TempFileReplaceDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public class TempFileReplaceDemo {
    // Example allows fallback so it runs across more filesystems.
    // Set false if business requirements mandate atomic replacement.
    private static final boolean ALLOW_NON_ATOMIC_FALLBACK = true;

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("replace-demo-");
        Path target = folder.resolve("config.txt");

        try {
            Files.writeString(target, "old\n", StandardCharsets.UTF_8);
            replaceWithText(target, "new\n");

            System.out.println("Destination: "
                    + Files.readString(target, StandardCharsets.UTF_8).strip());
            System.out.println("Destination exists: " + Files.exists(target));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(folder);
        }
    }

    private static void replaceWithText(Path target, String text)
            throws IOException {
        Path parent = target.toAbsolutePath().getParent();
        Path temporary = Files.createTempFile(
                parent, ".config-", ".tmp");

        try {
            ByteBuffer data = StandardCharsets.UTF_8.encode(text);

            try (FileChannel channel = FileChannel.open(
                    temporary,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                while (data.hasRemaining()) {
                    int written = channel.write(data);
                    if (written == 0) {
                        throw new IOException("Write made no progress");
                    }
                }
                channel.force(true);
            }

            try {
                Files.move(
                        temporary,
                        target,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException
                     | FileAlreadyExistsException ex) {
                if (!ALLOW_NON_ATOMIC_FALLBACK) {
                    throw ex;
                }
                // Explicit fallback: atomic guarantee no longer applies.
                Files.move(
                        temporary,
                        target,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            // If move succeeded, the temporary path no longer exists.
            // If an error occurred before move, clean up the temp file best-effort.
            Files.deleteIfExists(temporary);
        }
    }
}
```

Compile and run:

```bash
javac TempFileReplaceDemo.java
java TempFileReplaceDemo
```

**Stdout when create/write/read/move/delete succeed** (whether the atomic or fallback branch is taken):

```text
Destination: new
Destination exists: true
```

Explanation:

1. `Files.writeString(target,"old\n")` merely creates initial state for the demo. In a real application, this file already exists and would not be rewritten before every update.
2. `Files.createTempFile(parent,...)` creates a separate file in the same directory as the destination. V1 remains untouched while code starts writing V2.
3. `ByteBuffer` encodes UTF-8; the `write` loop ensures all data goes into the channel. `force(true)` requests synchronization of the file's content and relevant metadata per API semantics.
4. Exiting `try-with-resources` closes the channel. Only then is atomic `Files.move` attempted.
5. If the provider reports atomic moves are unsupported or refuses to atomically replace an existing target per implementation behavior, the example **intentionally** falls back to a standard move. The output can still be `new`, though the fallback **does not guarantee atomic visibility**.
6. The helper's `finally` cleans up temp if it still exists. Once the move succeeds, temp has been renamed and `deleteIfExists(temporary)` does not delete the destination.
7. `main` cleans up the demo file and directory after reading/printing the result. In a real application, **do not delete the destination after publishing**; cleanup in `main` is strictly for the demo harness.

If the environment rejects the rename because the file is open, lacks permissions, the filesystem is locked, disk space is full, or another I/O error occurs, the program can throw `IOException` instead of printing those two lines. The example does not swallow such errors. The fallback branch triggers only for the two stated exceptions; do not assume every `FileSystemException` can be recovered via a standard move.

**Why not fall back automatically in strict systems?** Because writers and readers must agree on the guarantee. A product requiring readers to see only complete snapshots must declare atomic replacement mandatory; if the filesystem lacks support, it should fail, preserve V1, and recover appropriately rather than pretending the fallback is equivalent.

## 8. What Does `force(true)` Help With, and What Does It Not Guarantee?

`FileChannel.force(boolean metaData)` requests pushing file updates made through the channel down to the storage device per API contract:

```java
channel.force(true);
```

- `force(false)`: requests synchronizing file **content**.
- `force(true)`: requests synchronizing content **and file metadata**.
- Calling `force` before renaming reduces the risk of publishing a file object whose new bytes are still sitting in cache rather than pushed to storage.
- `force` does not combine multiple records into a transaction; it does not prove readers cannot observe the destination being replaced non-atomically.
- Actual guarantee strength also depends on device type and filesystem; Java's contract differs for files not on local storage devices.

**Temp file metadata is not the same as the destination directory's metadata.** Renaming typically modifies a directory entry. On POSIX systems, a stronger crash-durability procedure usually requires syncing file data, renaming, and then syncing the **parent directory**. Standard Java SE 17 **has no portable API guaranteed to support directory sync across all providers**; opening a directory to call `force` may be rejected. Never write a generic Java example claiming `force(true)` on the temp file completes every step of a crash-safe rename.

If power-loss durability requirements are very high, consult and test against target OS/filesystem documentation or choose a storage engine with proper transactions/journaling. A single successful run does not prove power-loss guarantees.

## 9. What Happens If the Application Crashes at Each Stage?

| Failure Point | Typical State | What to Do |
|---|---|---|
| Before creating temp | Destination still holds V1 | Safe to retry |
| While writing temp, before move | Destination is still V1; temp may be incomplete | Do not publish incomplete temp; clean up/inspect per policy |
| Temp written and closed, not yet moved | Destination is V1; temp is a V2 candidate | Can validate and recover if a manifest/version exists |
| Atomic move completed | Readers opening destination path after move see V2 | Must still consider directory durability on power loss |
| Non-atomic fallback move interrupted | Destination state depends on filesystem/provider; neither complete V1 nor V2 guaranteed | Recovery, checksum/version verification, keep backups if needed |
| Move succeeded, process dies before receiving response | Destination **may already be V2**; writer does not know if commit took effect | Design retry/idempotency and verify version/hash |

Java's `finally` **does not run on power loss, `kill -9`, or abrupt system crashes**. Therefore, you must have a strategy to detect and handle leftover temp files. Do not blindly clean up by filename prefix while multiple writers might still be active; use ownership, file age, locks, or transaction identifiers appropriately.

## 10. Concurrent Readers During Replacement

When a rename/replace is genuinely atomic:

- Readers that **opened the destination path before** replacement may continue reading from their open handle pointing to the old file object, depending on OS and filesystem.
- Readers that **open the destination path after** replacement resolve the new directory entry and typically see V2.
- A reader does not necessarily "switch" to V2 automatically just because the path was renamed while it keeps a handle open. To reload configuration, the program must actively reopen/reload.
- Renaming does not synchronize a reader's internal logic. For example, a reader reading two separate files or reading V2 while caching part of V1 elsewhere can still suffer logical inconsistency.

Thus, the temp + rename pattern is very useful for **a single complete file**: publishing the file at a single name-switch point, while readers decide when to reopen.

Do not confuse `Files.move` with **in-place content writes**. If another program holds a hard link to the V1 file object, that hard link can keep seeing V1 after the destination name is replaced by the V2 object. If a symlink points to the destination name, re-reading through the symlink can reach the new file; however, replacing a destination that is itself a symlink has its own replacement rules.

## 11. Multiple Concurrent Writers and Lost Updates

Atomic replace provides guarantees about the rename operation if supported, **not that only one valid writer exists**.

Example:

```text
Writer A reads V1, computes V2-A, writes temp-A.
Writer B reads V1, computes V2-B, writes temp-B.
Writer A atomic replaces → destination is V2-A.
Writer B atomic replaces → destination is V2-B.
Result: A's changes can be lost (lost update).
```

Solutions depend on the problem:

1. Assign a single writer responsible for the file, funneling all requests through one queue.
2. Use an application-level lock or a dedicated lock file with a clearly designed lock/recovery protocol.
3. Use version numbers/checksums and conditional update logic at the data layer; `Files.move` alone has no CAS "replace only if old version is still V1".
4. For concurrent multi-entity updates, use a proper transaction mechanism rather than just renaming a single file.

**Do not assume a `FileLock` on the current destination file always protects the destination name across every replacement.** A file lock may attach to the old file object/handle while rename swaps the object behind the destination name; enforcement strength also depends on the platform. If using locks, follow a sound protocol and do not equate "locking the old file" with "locking the right to publish the destination name".

## 12. Permissions, Metadata, and Symbolic Links

### Metadata Can Change

Because temp is a **new file**, when it replaces the destination, attributes of the old destination file do not automatically transfer to temp:

- Access permissions/ACLs, owner/group.
- Timestamps and filesystem-specific attributes.
- Extended attributes, security labels, sparse/compression flags on some systems.
- Hard links still referencing the old file.

If business logic must preserve specific permissions/owner/ACL, define a policy and apply/verify attributes on temp **before publishing**. Avoid blindly copying overly permissive rights; permissions must fit your security model. `Files.createTempFile` and `Files.getFileAttributeView`/`setAttribute` support attributes partially depending on the provider; not every attribute has a portable API.

### Symlinks and Untrusted Directories

If the destination path is a symbolic link, `Files.move(temp, destination, ...)` typically operates on the **destination name entry**, rather than following the symlink and overwriting the target file's contents. Whether the symlink is replaced or the call fails depends on move semantics and the provider.

If another actor can swap files/links/directories between checking and moving (TOCTOU), prior `Files.exists`/`Files.isSymbolicLink` checks provide no absolute security guarantee. When handling paths from untrusted users, control directories, permissions, ownership, symlink policies, and publication architecture properly; never rely on a single pre-check assuming the path will not change.

## 13. Common Mistakes

1. **Writing directly to the destination with `TRUNCATE_EXISTING` and then writing new data.** Readers can see an empty file or half a record if an error happens midway.
2. **Creating temp in `java.io.tmpdir` even when the destination is on another volume.** Cross-filesystem atomic moves are usually unsupported; create temp in the destination's directory.
3. **Ignoring short writes.** `FileChannel.write(ByteBuffer)` can write fewer bytes than remaining. Loop until the buffer is drained.
4. **Not closing temp before renaming.** On some OSes, an open handle causes move/replace to fail.
5. **Catching `AtomicMoveNotSupportedException` and silently falling back.** If the system requires atomicity, fallback must be rejected; if accepted, document the downgraded guarantee clearly.
6. **Believing `ATOMIC_MOVE + REPLACE_EXISTING` always guarantees atomic overwrite.** When `ATOMIC_MOVE` is present, other options are ignored; existing-target behavior is implementation-dependent.
7. **Deleting the destination first and then renaming temp.** Creates a window where the destination name does not exist and can lose V1 on failure.
8. **Assuming `force(true)` on temp equals completely durable rename.** Directory metadata matters too; Java does not offer portable directory `fsync` across all environments.
9. **Writing the temp file without validating its format.** Atomically publishing a schema-invalid file still produces completely broken business data.
10. **Forgetting temp permissions/ACLs.** The published file is a new file object whose metadata may differ from the old destination.
11. **Treating atomic replace as a lock/CAS.** Two writers can still overwrite each other's results; coordination is still needed.
12. **Assuming `finally` always cleans up temp.** After power loss or abrupt kills, leftover temp files can remain and require startup recovery.
13. **Assuming every reader with an open handle automatically sees new content.** Old handles may still point to V1; readers must reopen when needing a fresh snapshot.
14. **Assuming one move solves multi-file transactions.** Atomically publishing one file does not synchronize versions across multiple files.

## 14. When Do You Need Backups or a Manifest?

Temp + replace reduces the risk of a **half-written** file, but does not by itself protect against:

- Publishing **syntactically valid but logically wrong data**.
- A newer writer overwriting an earlier update.
- Storage corruption or file deletion after publication.
- Needing to roll back to an older version when a component depending on V2 is incompatible.

In those cases, consider **keeping an independent copy of V1**, checksummed version history, or a manifest pointing to version-named data files:

```text
data-v1.bin
data-v2.bin
manifest.json  → {"active":"data-v2.bin"}
```

Idea: write and validate file V2 first, then update **a small manifest** via temp + atomic replacement. Readers read the manifest, then open the corresponding versioned file. This design identifies snapshots cleanly, though it still requires a cleanup strategy for old versions and metadata/durability handling; replacing a manifest once does not solve all transaction or concurrency problems.

This is a suitable extension when applications have large data files, readers need immutable snapshots, or rollback is required; for a small config file, temp + replace with validation may suffice.

## 15. Application Readiness Checklist

Before publishing a new file, verify in order:

1. **Identify trusted destination and directory:** permissions to create temp and replace exist; symlink policy is settled.
2. **Create an independent temp file in the same directory:** avoid fixed names prone to contention.
3. **Write all bytes reliably:** use explicit encoding, format, and an I/O write loop.
4. **Validate and apply required metadata:** schema/checksum, permissions/ACL, size.
5. **Sync temp if business logic requires:** `FileChannel.force(true)`, understanding filesystem limits.
6. **Close temp before moving.**
7. **Publish according to chosen guarantees:** strict atomic or an architecturally approved fallback policy; never delete destination beforehand.
8. **Verify final state when needed:** destination exists, version/hash matches, log outcome; recognize failures can occur after commit.
9. **Clean up leftover temp files:** `finally` during normal runs and startup recovery after crashes.
10. **Coordinate writers/readers:** prevent lost updates; readers reopen when fresh data is needed.

If **readers must never see a half-written version**, the environment must support an appropriate atomic publication mechanism; if unavailable, reject the update or change storage design. If **survival across power loss** is required, add OS/filesystem durability measures and failure testing rather than relying on a single move call alone.

## 16. Self-Check Questions

**Question 1.** Why not write V2 content directly into the V1 destination file?  
**Answer:** Writing directly can truncate/half-write V1 before V2 finishes. Writing to a temp file preserves V1 throughout V2 construction and only publishes afterward.

**Question 2.** When using `ATOMIC_MOVE`, does `REPLACE_EXISTING` guarantee overwriting an existing target?  
**Answer:** No. Per `Files.move` documentation, when `ATOMIC_MOVE` is specified, other options are ignored; replacing an existing target is implementation-dependent.

**Question 3.** After `channel.force(true)` on temp and `Files.move(..., ATOMIC_MOVE)` succeed, is the new destination name guaranteed not to vanish on power loss?  
**Answer:** That cannot be concluded portably. Directory entry/rename durability still depends on the filesystem/OS, and standard Java does not guarantee directory `fsync` across all providers.

**Question 4.** Writers A and B both build new versions from V1, and both perform atomic replace. Is lost update avoided?  
**Answer:** No. The later publish can overwrite the earlier writer's version. Serialization, version checking, or proper transactions are needed.

**Question 5.** If atomic rename is unsupported, can we always fall back to `REPLACE_EXISTING` so the program keeps running?  
**Answer:** Only if business requirements **accept losing the atomic guarantee** and corresponding read/recovery handling exists. When atomicity is mandatory, fail with an error.

**Question 6.** If the Java process is killed mid-write of the temp file, is `finally` guaranteed to run?  
**Answer:** No. You need a mechanism to detect and clean up/recover leftover temp files after a crash, while avoiding files actively used by valid writers.

**Question 7.** After atomic replace, will a reader already holding an open handle to V1 necessarily see V2 on its next read?  
**Answer:** No. The old handle may keep referencing V1; the reader must reopen the destination path if it wants the current snapshot.

## 17. Key Takeaways

- **Write completely + validate the temp file first, replace the destination name afterward** to avoid publishing half-written files.
- **Create temp in the same directory** to maximize atomic move support; use `Files.createTempFile` to avoid name collisions.
- **`Files.move(..., ATOMIC_MOVE)` must be supported by the provider**, and existing-target handling is implementation-dependent. Never silently assume a fallback is atomic.
- **`FileChannel.force(true)` aids file durability**, but does not mean directory renames are durably flushed on every platform.
- **Atomic replace is not a transaction, CAS, or multi-writer lock**. Dedicated mechanisms are required for consistency, rollback, and crash recovery when needed.

### Java 17 API References

- [Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...))
- [StandardCopyOption.ATOMIC_MOVE / REPLACE_EXISTING](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [FileChannel.force](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean))
- [Files.createTempFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#createTempFile(java.nio.file.Path,java.lang.String,java.lang.String,java.nio.file.attribute.FileAttribute...))