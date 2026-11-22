# `Files.move()`, Renaming Files, and the `ATOMIC_MOVE` Option in Java

Renaming (`rename`) and moving (`move`) are two common operations in Java I/O: changing `draft.txt` to `report.txt`, moving a file from a temporary directory to a publishing directory, or renaming a directory. The modern API is **`java.nio.file.Files.move(Path source, Path target, CopyOption... options)`**. In Java NIO.2, renaming is usually just a special case of `move`: the source path and target path have different names, possibly within the same directory.

The easiest pitfall is that **`Files.move()` does not guarantee atomicity by default**. When an application needs a rename/move operation to occur as a single unified step where other processes cannot observe intermediate states, you can request **`StandardCopyOption.ATOMIC_MOVE`**. However, whether this is supported depends on the filesystem/provider, and this option has special rules when the target already exists.

This lesson explains the syntax, how to rename and move, the `REPLACE_EXISTING` and `ATOMIC_MOVE` options, guarantee boundaries, common errors, limits across filesystems, and how to build a safe file-publishing workflow.

## 1. Renaming Is a Case of `move`

A file can be renamed in the same directory by constructing a new `Path target`:

```java
// Illustrative snippet: source is already declared as java.nio.file.Path.
Path target = source.resolveSibling("renamed.txt");
Files.move(source, target);
```

`resolveSibling("renamed.txt")` places the new name **next to** the source, i.e., under the same parent path (if present). `Files.move(source, target)` requests moving the source entry to the target path. If successful, the old name is typically no longer usable to locate that entry, while the new name is used to access it.

Moving to another directory:

```java
// Illustrative snippet: source and targetDirectory are existing Paths.
Path target = targetDirectory.resolve(source.getFileName());
Files.move(source, target);
```

For the same file, the API does not have two independent mechanisms for "rename" and "move": the difference lies mainly in how the **target path** is specified.

**Note:** `Path` only represents a path. `Files.move` is the actual I/O operation; it can throw `IOException` due to a missing file, an existing target, access permissions, filesystem issues, a file currently in use, or other conditions. `move()` does not automatically create missing parent directories for the target.

### Example 1 — Renaming a Real File, Independent of the Project Directory

```java
// MoveRenameDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MoveRenameDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("move-rename-");
        Path source = directory.resolve("draft.txt");
        Path target = source.resolveSibling("report.txt");

        try {
            Files.writeString(source, "Java I/O", StandardCharsets.UTF_8);

            Path moved = Files.move(source, target);

            System.out.println("resultName=" + moved.getFileName());
            System.out.println("oldExists=" + Files.exists(source));
            System.out.println("newExists=" + Files.exists(target));
            System.out.println("content="
                    + Files.readString(target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 MoveRenameDemo.java
java MoveRenameDemo
```

Result when the file system completes the operations successfully:

```text
resultName=report.txt
oldExists=false
newExists=true
content=Java I/O
```

`Files.move()` returns a `Path` representing the target path; the example avoids using the temporary directory's name in stdout so the output is easy to check. The `finally` block cleans up the items created by the example; if an I/O error occurs during cleanup itself, that error should also be handled according to real application policy.

## 2. What Arguments Does `Files.move(...)` Accept?

Signature:

```java
public static Path move(
        Path source,
        Path target,
        CopyOption... options) throws IOException;
```

This is a **condensed API signature for explanation**, not a method you need to implement yourself.

- `source`: path of the entry to move.
- `target`: destination path, including the new file/directory name.
- `options`: operation options, among which `StandardCopyOption.REPLACE_EXISTING` and `StandardCopyOption.ATOMIC_MOVE` are commonly used.
- Result: `Path` representing the target if successful.
- May throw `IOException` and subtypes depending on cause; certain conditions such as Java security permissions or incompatible providers throw other exceptions per the API.

Three common call patterns:

```java
Files.move(source, target);

Files.move(source, target,
        StandardCopyOption.REPLACE_EXISTING);

Files.move(source, target,
        StandardCopyOption.ATOMIC_MOVE);
```

**Point to remember:** `REPLACE_EXISTING` and `ATOMIC_MOVE` are not two "increasing levels of safety" for the same property. One option specifies **how to handle an existing target** in a normal move; the other requests **atomicity of the move step**. Moreover, when `ATOMIC_MOVE` is present, other options are ignored per the `Files.move()` contract.

## 3. Passing No Options: What Happens If the Target Already Exists?

By default, `Files.move(source, target)` **does not request replacing an existing target**. If target already contains another entry, the operation typically fails with `FileAlreadyExistsException`. There are implementation exceptions/details, yet in application code treat a target collision as an error that must be handled, without relying on implicit overwriting.

For example, both `draft.txt` and `final.txt` exist. The call:

```java
Files.move(Path.of("draft.txt"), Path.of("final.txt"));
```

should not be used expecting to reliably overwrite `final.txt`. If the business requirement is **never replace** the target file, keep the operation without `REPLACE_EXISTING`, catch collision errors, and review atomicity notes if strong guarantees against concurrent races are needed.

When source and target point to **the same file**, `Files.move` may return without doing anything per contract. Do not assume every `move` call implies an actual name change.

## 4. `REPLACE_EXISTING`: Allowing Target Replacement in a Normal Move

`StandardCopyOption.REPLACE_EXISTING` requests **replacing the entry at the target path if it already exists**, within provider and entry-type limits:

```java
Files.move(source, target,
        StandardCopyOption.REPLACE_EXISTING);
```

Suppose `source` and `target` are both regular files. After succeeding, target normally holds the entry/file moved from source rather than the old content.

However, this **must not** be taken as a promise that "every kind of target can be replaced": for example, a non-empty directory target may not be replaceable. File systems have differing rules for open files, ACLs, symbolic links, special entries, and cross-provider paths.

### Example 2 — Collision and Intentional Replacement

```java
// MoveReplaceDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class MoveReplaceDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("move-replace-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "NEW", StandardCharsets.UTF_8);
            Files.writeString(target, "OLD", StandardCharsets.UTF_8);

            try {
                Files.move(source, target);
                System.out.println("unexpected: move without replace");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("collision=true");
            }

            Files.move(source, target,
                    StandardCopyOption.REPLACE_EXISTING);

            System.out.println("targetText="
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("sourceExists=" + Files.exists(source));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac MoveReplaceDemo.java
java MoveReplaceDemo
```

Typical output on a standard local filesystem, when files exist and permissions allow:

```text
collision=true
targetText=NEW
sourceExists=false
```

Here replacement is **intentional**; it makes no sense if the business requirement is "never lose old target content." Nor should one conclude that merely adding `REPLACE_EXISTING` makes the operation atomic.

### When the Target Is a Symbolic Link

When target is a symbolic link, the replacement rule of `Files.move(..., REPLACE_EXISTING)` applies to **the link entry** rather than automatically deleting the target it points to. When source is a symbolic link, `Files.move()` moves **the link itself** rather than moving the link's target content like a dereferencing copy.

This matters when dealing with broken links or links pointing outside an intended directory. If source/target involves symbolic links or junctions, determine the operation contract based on the provider and problem; do not assume regular-file logic applies identically to every entry type.

## 5. `ATOMIC_MOVE`: Requesting an Atomic Move Step

A move operation is performed **atomically** when the filesystem/provider can execute it as a single operation on the file system's namespace, instead of another application/process observing intermediate states of a multi-step sequence such as copying data chunks and then deleting the source.

In Java:

```java
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

`ATOMIC_MOVE` is a **request** to the provider, not a guarantee that every file system can perform it. When an atomic move between the two given paths is unsupported, Java can throw `AtomicMoveNotSupportedException`. This signals the application to make a business decision: **stop** if atomicity is mandatory, or fall back to a non-atomic approach if permitted.

### What an Atomic Move Typically Aims For

- Changing the entry's name/path as **a single step** at the filesystem namespace level.
- Avoiding a half-finished state where another program sees a new target being **partially copied** during the atomic move operation itself.
- Serving as the foundation for the "prepare a separate file, then publish the final name" pattern on supporting providers.

### What an Atomic Move Does **Not** Automatically Guarantee

- **Not a multi-file transaction**: two separate move commands are not combined into one transaction.
- **Does not prove bytes survive power loss**: rename atomicity is not synonymous with `fsync`/storage durability.
- **Does not guarantee no one modifies file content** before, during, or after the operation. It does not place a lock over the whole read/write lifecycle.
- **Does not guarantee success when source/target are on different filesystems**, volumes, mounts, or providers.
- **Does not guarantee an atomic fallback** if `ATOMIC_MOVE` is rejected.
- **Does not guarantee identical handling of existing targets across all platforms**.

If you need atomic visibility, access permissions, crash durability, and multi-file updates together, you must design additional mechanisms beyond a single `Files.move`.

### Example 3 — Requesting `ATOMIC_MOVE` and Handling Unsupported Cases

```java
// AtomicMoveDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicMoveDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("atomic-demo-");
        Path source = directory.resolve("temporary.txt");
        Path target = directory.resolve("published.txt");

        try {
            Files.writeString(source, "COMPLETE", StandardCharsets.UTF_8);

            try {
                Files.move(source, target,
                        StandardCopyOption.ATOMIC_MOVE);
                System.out.println("atomicMove=performed");
                System.out.println("published="
                        + Files.readString(target, StandardCharsets.UTF_8));
            } catch (AtomicMoveNotSupportedException ex) {
                System.out.println("atomicMove=unsupported");
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac AtomicMoveDemo.java
java AtomicMoveDemo
```

If the provider supports atomic move in the temporary directory:

```text
atomicMove=performed
published=COMPLETE
```

If the provider reports the specific error because it is unsupported:

```text
atomicMove=unsupported
```

**There is no fixed stdout across all filesystems.** Other `IOException` errors (such as insufficient permissions or disk errors) are still propagated via `throws Exception` and are not misidentified as "atomic unsupported." This is better behavior than catching all `IOException` and silently falling back.

Even if both paths lie in the **same directory**, atomicity still requires provider support; being in the same directory improves practical likelihood of support but does not replace error handling.

## 6. Important Pitfall: `ATOMIC_MOVE` Causes Other Options to Be Ignored

A misleading example:

```java
Files.move(source, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
```

You might think that call simultaneously guarantees two things:

1. An atomic rename.
2. Always replacing an existing target.

**It is incorrect to deduce that.** Per the `Files.move()` contract, **when `ATOMIC_MOVE` is present, other options are ignored**. Whether an atomic move replaces an existing target is **implementation-specific** and cannot be guaranteed simply by including `REPLACE_EXISTING`.

This also means you cannot write a "universally atomically overwrite on all systems" utility merely by passing both constants without checking the provider, entry types, and application requirements.

| Call | Primary request | Target already exists |
| --- | --- | --- |
| `Files.move(src, dst)` | Normal move, no atomicity requested | Usually fails; does not enable overwrite by itself |
| `Files.move(src, dst, REPLACE_EXISTING)` | Allows replacing target under normal move rules | Can replace valid targets, yet does not promise atomicity |
| `Files.move(src, dst, ATOMIC_MOVE)` | Requests atomic move | Behavior if target exists is implementation-dependent |
| `Files.move(src, dst, ATOMIC_MOVE, REPLACE_EXISTING)` | Still an atomic move request | `REPLACE_EXISTING` is ignored; existing-target behavior remains implementation-dependent |

This table distinguishes **API rules** from **common behavior**. To know the degree of target-replacement guarantees on a specific platform, examine the filesystem/provider contract/documentation and real cases. Checking `Files.exists(target)` before moving is insufficient to eliminate races: a file can appear or disappear right after the check.

## 7. When Should Atomicity Be Mandatory? When Should Fallback Be Allowed?

Business examples:

- Publishing a complete configuration file under a name watched by a consumer: atomic rename is usually important so the consumer never sees a half-written file.
- Renaming a personal file inside a directory: a non-atomic move may be acceptable if the operation and file system allow it.
- Moving a file from an internal drive to a network drive: may require copying then deleting; if the application needs transactional semantics, a separate design is needed.
- Replacing an important file currently read by another application: you must simultaneously define target-existence policy, content versioning, atomicity, and how consumers open the file.

### Policy A: Fail If Atomicity Is Unavailable

```java
// Illustrative: source and target are already valid Paths.
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Do not copy/delete yourself when atomicity is a mandatory requirement.
    throw ex;
}
```

This is an **illustrative snippet**, requiring appropriate imports and placement in a method allowing `IOException`. In this design, "atomic unsupported" is a precondition failure, not a reason to silently use a weaker approach.

### Policy B: Fall Back Only If Business Rules Allow

```java
// Illustrative: Paths already exist, not a standalone program.
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Use only when non-atomic and target policy are explicitly accepted.
    Files.move(source, target);
}
```

**Limitations of fallback:** the second statement **does not guarantee atomicity**. If it has to copy then delete and fails mid-way, source/target state may not be as expected. You must also handle cases where target was created by another process, the parent directory changed, or the file system encountered an error. If the fallback wants to **replace** target, decide separately on using `REPLACE_EXISTING`; that also does not create atomicity.

Catch only `AtomicMoveNotSupportedException` for the unsupported-atomicity decision. Do not catch all `IOException` and fall back, because permission errors, out-of-space conditions, or filesystem corruption are not fixed by retrying under weaker semantics.

## 8. Moving Across Drives/Filesystems

A filesystem-level rename is usually much easier to perform atomically **within the same filesystem** than across volume/mount boundaries. For example:

```text
Drive/volume A              Drive/volume B
/data/draft.bin    ------>  /archive/draft.bin
```

If the filesystem does not support atomic moves between the two sides, requesting `ATOMIC_MOVE` can trigger `AtomicMoveNotSupportedException`. A normal move permitted by the provider might be carried out by copying data to the target then deleting the source, or might fail depending on entry type and provider. Never assume any multi-level directory is copied recursively just by calling `Files.move` once.

Another important difference: **when a non-atomic move throws `IOException`, file state may be indeterminate**. Source and target might both remain, target might be incomplete, or some metadata might not have been copied. The application must inspect/recover per policy instead of assuming "if move failed, nothing could have changed."

| Scenario | Risk or outcome |
| --- | --- |
| Rename in the same directory of a supporting filesystem | Usually a simple operation; atomicity is requested/checked only when `ATOMIC_MOVE` is used |
| Move between two directories on the same filesystem | Can be supported atomically; still provider-dependent |
| Move across different volumes, mounts, or providers | Atomic request may be rejected; normal move may execute multiple steps or fail |
| Move an entry that is a directory | Contract depends on provider, target state, filesystem boundaries, directory structure |
| Move a symbolic link | Moves the link itself; does not copy target content by default |
| Move while a file is open | OS/provider behavior decides; may succeed or hit sharing/permission errors |

Do not take a program succeeding on a local drive as proof that it will definitely work on a network share, container volume, mounted drive, or virtual storage provider.

## 9. Pattern: Publish Through a Temporary Name, Then Move to Target Name

An application often wants a producer to finish creating **complete** content before others read the target name:

```text
(1) Create temp file in target directory
          |
(2) Write full content and close writer
          |
(3) Files.move(temp, finalName, ATOMIC_MOVE)
          |
(4) Readers access finalName
```

The reason for placing the temp file **in the same directory as the target**: it increases the chance that entries reside on the same filesystem, reducing the chance that the move becomes a cross-volume transfer. However, this does not by itself prove the provider supports `ATOMIC_MOVE`.

### Example 4 — Publishing a New File Only When Atomic Move Is Available

This example picks a **new target name that does not yet exist** at the start, avoiding attempting to simulate updating/overwriting an existing target. It requires atomic move; if unsupported, it reports an error with **no silent fallback**.

```java
// AtomicPublishDemo.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicPublishDemo {
    static void publishNew(Path target, String text) throws IOException {
        Path absoluteTarget = target.toAbsolutePath();
        Path parent = absoluteTarget.getParent();
        Path temporary = Files.createTempFile(parent, ".draft-", ".tmp");

        try {
            Files.writeString(temporary, text, StandardCharsets.UTF_8);

            // Request atomic move; do not silently fall back to copy/delete.
            // Target name collision policy under concurrency must be
            // handled separately: ATOMIC_MOVE does not guarantee no-overwrite.
            Files.move(temporary, absoluteTarget,
                    StandardCopyOption.ATOMIC_MOVE);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("publish-demo-");
        Path published = directory.resolve("result.txt");

        try {
            publishNew(published, "complete");
            System.out.println("published="
                    + Files.readString(published, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(published);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac AtomicPublishDemo.java
java AtomicPublishDemo
```

When the provider supports atomic move, there is no target collision, and operations succeed:

```text
published=complete
```

If atomic move is not supported, the program **throws `AtomicMoveNotSupportedException`** and does not print `published=...`. This result is designed to **never silently downgrade semantics**. `finally` attempts to clean up the temporary file in either case.

**Concurrency warning:** this is not a "create only if absent" API carrying uniform guarantees across different systems. Another task can create target after the code chooses a name. The semantics of `ATOMIC_MOVE` when target already exists are implementation-specific, so if you strictly require **never overwriting someone else's file**, design a coordination/naming policy or use an appropriate create-new API instead of trusting `ATOMIC_MOVE` plus an `exists()` check.

### What If an Old Config Version Needs to Be Overwritten?

A practical pattern is writing the entire new version into a temp file on the same filesystem, completing the write, and then publishing under a stable name. However, additional decisions are required:

- Is **replacing** the target file permitted? If so, does the provider guarantee atomic replacement of an existing entry under a verified contract?
- What is the behavior if the file is currently open by another process? Windows and Unix in particular differ regarding renames with open handles.
- Must data survive power loss? Closing a writer and renaming atomically **do not automatically guarantee durability**; examine `FileChannel.force(...)`, metadata/directory syncing, and OS/filesystem guarantees.
- Are multiple writers competing? You need an appropriate versioning/locking/compare-and-swap mechanism rather than assuming atomic rename prevents lost updates.
- Should consumers reading a previously opened handle automatically switch to the new version? You cannot assume a rename alters the content seen by an already-open handle in the way the application wants.

For an application needing strong consistency, you must specify the **guarantee level** rather than using the word "atomic" for every property.

## 10. Order of Writing Data, Closing Streams, and Moving

Do not move a file to the published name while a writer still holds data in its buffer:

```java
// Illustrative: temp and finalPath are existing Paths,
// charset UTF_8; code inside a method that throws IOException.
try (BufferedWriter writer =
        Files.newBufferedWriter(temp, StandardCharsets.UTF_8)) {
    writer.write("new configuration");
}

// Writer is closed before publishing the new name.
Files.move(temp, finalPath, StandardCopyOption.ATOMIC_MOVE);
```

When `BufferedWriter` closes, buffered data not yet flushed is processed and the underlying stream is closed. However, **a successful close does not automatically mean data is durably synced to hardware**. For crash/power-loss safety, determine durability mechanisms separately.

If moving without `ATOMIC_MOVE`, the call may still succeed and within the same filesystem is often performed as a rename, yet **the API does not mandate** atomicity in all circumstances. Only when you **request** atomicity and the operation succeeds under the provider's contract can you rely on that property.

## 11. Common Exceptions When Moving

| Exception | Common meaning | How to handle |
| --- | --- | --- |
| `NoSuchFileException` | Source or a required component does not exist | Inspect source/parent; handle concurrent changes |
| `FileAlreadyExistsException` | Target collision in a non-replacing operation | Report collision or switch to a branch with explicit replace policy |
| `AtomicMoveNotSupportedException` | Provider does not support atomic move for this path pair/situation | If atomic is mandatory: stop; otherwise: approved fallback |
| `DirectoryNotEmptyException` | Attempted to replace a non-empty target directory in an unsupported scenario | Do not delete directory contents without explicit requirement |
| `AccessDeniedException` | Provider reports insufficient access permissions | Report error or require proper permissions; do not change permissions arbitrarily |
| `FileSystemException` | Filesystem error with additional details | Log source/target info and cause; handle per business rules |
| `IOException` | Remaining I/O errors | Do not assume source/target remain unchanged after a non-atomic failure |

Not every provider throws the exact subtype in the table for every error. Sometimes a general `IOException` is used instead of a specific subtype. When logging, record source/target paths in a way that avoids exposing sensitive data and preserve the relevant stack trace/exception.

### Do Not Catch All Errors and Retry Overwrite

This is an anti-pattern:

```java
// Snippet illustrating an UNSAFE approach:
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (IOException ex) {
    Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
}
```

Reason: `IOException` could be an access permission error or filesystem corruption, not necessarily lack of atomic support. That fallback can also **overwrite a different target** that happened to be created during execution. Furthermore, after certain non-atomic failures, actual state may need inspection before deciding what to do next.

### Checking `exists()` Does Not Eliminate Race Conditions

```java
if (!Files.exists(target)) {
    Files.move(source, target);
}
```

This is **an illustrative snippet with a race**, not a way to guarantee target stays absent at move time. This is the **TOCTOU** (time of check to time of use) problem. Another thread/process can create target right after the check.

Depending on requirements, rely on operation semantics guaranteed by the provider, handle formal exceptions, or use a coordination mechanism among writers. Do not pair `exists()` with a move and assume "it will definitely succeed."

## 12. Comparison with Legacy `File.renameTo()`

Pre-NIO.2 Java often used:

```java
// Illustrative snippet with oldFile and newFile of type java.io.File.
boolean renamed = oldFile.renameTo(newFile);
```

`File.renameTo(File)` still exists but is usually poorly suited for logic requiring clear error handling:

- Returns `boolean`, so on failure it usually **does not provide details like specialized I/O exceptions**.
- Platform-dependent behavior; may fail across filesystems or when files are open.
- Has no `ATOMIC_MOVE` argument equivalent to **request** atomicity via this API.
- Behavior regarding existing targets and different entry types can be hard to predict across systems.

For Java 17+ code needing explicit handling, prefer:

```java
Files.move(oldFile.toPath(), newFile.toPath());
```

This is an illustrative snippet. Converting `File` to `Path` via `toPath()` does not move or create a file; the actual action happens in `Files.move(...)`.

| Criterion | `File.renameTo()` | `Files.move()` |
| --- | --- | --- |
| Rename within the same directory | Can work | Yes |
| Move to another directory | Platform-dependent | Explicit API, still filesystem/provider-dependent |
| I/O error reporting | Usually just `false` | `IOException` and useful subtypes |
| Intentional target replacement | No equivalent NIO.2 option | `REPLACE_EXISTING` for normal moves |
| Requesting atomic move | No similar standard option | `ATOMIC_MOVE` |
| `Path`/provider handling | `File` tied to traditional pathnames | `Path` is a filesystem provider abstraction |

## 13. Moving Directories, Open Files, and Symbolic Links

### Directories

`Files.move()` can be applied to directories, yet that does not mean it will perform a **recursive copy of an entire data tree to another drive** in every situation. Within the same filesystem, renaming a directory can be a metadata operation; across filesystems, the request may be unsupported. A non-empty target directory is also a special case.

Do not confuse:

```text
rename directory (move directory entry)
```

with:

```text
traverse each child file -> copy -> verify -> delete source tree
```

The two workflows have very different failure modes, timings, permissions, and atomicity.

### Open Files

Some systems allow renaming/moving a file while a process still holds a read handle; other systems may reject it due to sharing/permission rules. Java does not promise identical results across Windows, Unix, network shares, and every provider. Do not treat a test result on a personal machine as a cross-platform contract.

### Symbolic Links

When source is a symbolic link, `Files.move` moves **the link object itself**. The link may continue pointing to the old path and become a broken link after moving if the link's target value is a relative path and the directory context changed. If the application wants to move the link's target content, handle it under a separate policy.

### Attributes and Permissions

Moving an entry can affect metadata depending on provider/volume. Do not assume all timestamps, ACLs, owner, file keys, or special attributes are preserved intact, especially when moving across filesystems. If business rules require certain attributes, read/verify them using appropriate APIs afterward.

## 14. Checklist for Choosing the Right Move Approach

1. **What is the goal?** Rename in the same directory, move elsewhere, or publish a new version?
2. **Does the source exist?** Do not just pre-check; still handle actual I/O results and errors from concurrent changes.
3. **Can target already exist?** Clearly decide "reject," "allow replacement," or "pick a different name."
4. **Is atomicity needed?** If yes, request `ATOMIC_MOVE` and fail cleanly if unsupported.
5. **Is atomic replace needed?** Do not assume `ATOMIC_MOVE + REPLACE_EXISTING` is a portable guarantee; existing-target behavior is implementation-specific.
6. **Same filesystem or not?** Place temp in the target directory to improve atomic move likelihood, without assuming certainty.
7. **Have writes finished and writers been closed?** Moving does not automatically flush data still sitting in a writer's buffer.
8. **Is power-loss durability required?** Separate this from atomic rename; `FileChannel.force()` and metadata syncing steps may be needed.
9. **Are source/target directories, symbolic links, or open files?** Check provider contracts and entry types.
10. **How to recover if move fails?** Especially with non-atomic moves, do not assume source/target remained untouched.
11. **Are multiple writers competing?** Need a synchronization/versioning protocol rather than relying only on filenames.
12. **How to test?** Test cases with/without existing target, providers supporting/not supporting atomic move, access permissions, and relevant failures/crashes.

## 15. Common Mistakes and How to Fix Them

| Misunderstanding or practice | Why it is wrong | How to fix |
| --- | --- | --- |
| Calling default `Files.move()` and claiming it is definitely atomic | The API does not request atomicity without options | Use `ATOMIC_MOVE` when needed and handle exceptions |
| Thinking `REPLACE_EXISTING` also means atomic | Replace and atomic are independent properties | Distinguish replacement conditions from atomicity |
| Thinking `ATOMIC_MOVE, REPLACE_EXISTING` guarantees atomic overwrite | When the atomic option is present, remaining options are ignored | Verify provider semantics and target policy |
| Catching `IOException` and falling back to non-atomic | Masks real errors and can break consistency | Fall back only on `AtomicMoveNotSupportedException` when approved |
| Creating temp on a different volume from target | Atomic move is usually unsupported across filesystems | Create temp beside target when appropriate |
| Moving file before closing `BufferedWriter` | Content may still sit in buffer | Finish writing and close writer before moving |
| Treating atomic rename as power-loss protection | Namespace atomicity differs from data durability | Design data and metadata synchronization separately |
| Assuming source is intact after a non-atomic move failure | Both files might exist or target might be half-written | Inspect state and recover carefully |
| Using `File.renameTo()` in code needing clear error causes | Boolean result lacks detail | Use `Files.move()` and catch specific errors |
| Treating cross-drive directory move as recursive copy | Not the general move contract | Design explicit copy/verify/delete if actually needed |
| Checking `!exists(target)` and trusting no one creates target | Subject to TOCTOU | Rely on operation contract and writer coordination |
| Treating every symlink as its target file | Moving a link does not move target content by default | Distinguish links from targets |

## 16. Self-Check

**Question 1.** Is renaming `a.txt` to `b.txt` in the same directory a form of move?

**Answer:** Yes. With NIO.2, use `Files.move(source, source.resolveSibling("b.txt"))`.

**Question 2.** Does default `Files.move(source, target)` promise atomicity?

**Answer:** No. If an atomic move is required, request `StandardCopyOption.ATOMIC_MOVE` and handle unsupported cases.

**Question 3.** Both `source.txt` and `target.txt` exist. Which option should be chosen to replace target under normal move rules?

**Answer:** `StandardCopyOption.REPLACE_EXISTING`, noting that replacement rules depend on entry type/provider and do not guarantee atomicity.

**Question 4.** Why does `Files.move(src, dst, ATOMIC_MOVE, REPLACE_EXISTING)` not guarantee "atomic replace"?

**Answer:** When `ATOMIC_MOVE` is present, other options are ignored; behavior when target already exists is implementation-specific.

**Question 5.** A file on drive A needs to move to drive B; can `ATOMIC_MOVE` always be performed?

**Answer:** No. Crossing filesystems/volumes may not support atomicity and may throw `AtomicMoveNotSupportedException`.

**Question 6.** Should you catch every `IOException` from an atomic move to call a non-atomic move?

**Answer:** No. Fall back only when the cause is appropriate (typically `AtomicMoveNotSupportedException`) and business rules permit giving up atomicity.

**Question 7.** Which `Path` does `Files.move` return on success?

**Answer:** The path representing **target**.

**Question 8.** Is an atomic move enough to ensure data survives power loss?

**Answer:** No. Atomicity of the rename operation is not synonymous with durability of content or metadata.

**Question 9.** When source is a symbolic link, does `Files.move` move the file content at the other end of the link or the link itself?

**Answer:** It moves **the symbolic link itself**, per the move contract.

**Question 10.** Why can't you assume "nothing changed" when a non-atomic move fails?

**Answer:** The operation may have partially copied data or changed metadata before failing; the API does not guarantee source/target state after a non-atomic failure.

**Question 11.** Does creating a temporary file in the target directory guarantee every move is atomic?

**Answer:** No. It reduces cross-filesystem risk, yet the provider may still not support `ATOMIC_MOVE`.

**Question 12.** When an application must publish a new file without allowing any overwrite, is using only `ATOMIC_MOVE` and `Files.exists(target)==false` enough?

**Answer:** Not enough. `exists()` is race-prone, and when atomic move encounters an existing target, handling semantics depend on implementation. You need a naming policy, locking/coordination, or a create-new mechanism and verification matching the requirement.

**Key takeaway:** `Files.move()` is the preferred API for **renaming or moving** files. `REPLACE_EXISTING` handles **existing-target** policy in normal moves; `ATOMIC_MOVE` requests **an atomic move** yet may be unsupported, and when used, **remaining options are ignored**. An atomic rename is neither a multi-file transaction nor a guarantee of durability across power loss. Allow non-atomic fallback only if the application intentionally accepts the risk, while always handling real operation state and exceptions.
