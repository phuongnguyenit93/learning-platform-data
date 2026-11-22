# Copying Files with REPLACE_EXISTING and COPY_ATTRIBUTES in Java NIO

When copying files in Java 17+, the standard API is `java.nio.file.Files.copy(Path source, Path target, CopyOption... options)`. Two options commonly used together are:

- **`StandardCopyOption.REPLACE_EXISTING`**: if the target file already exists, allows replacing the target file under conditions supported by the API.
- **`StandardCopyOption.COPY_ATTRIBUTES`**: requests attempting to copy attributes of the source file to the target file, at a minimum including the last-modified time if both file stores support it.

Typical example:

~~~java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);
~~~

However, **allowing replacement does not mean atomic copying**, and **requesting attribute copying does not mean all metadata is strictly preserved**. You need to understand each option individually, how they combine, exception cases, and the risk of a partially written target file.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the contract of `Files.copy(Path, Path, CopyOption...)`, its return type, and important exceptions.
2. Distinguish default behavior when a target file already exists from `REPLACE_EXISTING`.
3. Distinguish copying **byte content** from copying **file attributes**, as well as the limits of `COPY_ATTRIBUTES`.
4. Know what happens when the source is a symbolic link or a directory, when the target is a symbolic link, or when source and target point to the same file.
5. Understand why `Files.copy` does not guarantee atomicity, rollback, or protection against concurrent modification.
6. Build runnable Java 17+ examples using temporary directories, cleanup, content verification with `Files.mismatch`, and metadata inspection.
7. Choose a temporary-file and `Files.move` strategy when a controlled result-publishing workflow is required.
8. Avoid common pitfalls regarding paths, permissions, file stores, attributes, and data safety.

## 2. Syntax Overview and Meaning

Signature of the overload covered here:

~~~java
public static Path copy(
        Path source, Path target, CopyOption... options
) throws IOException;
~~~

Where:

- `source`: the `Path` of the source to copy.
- `target`: the destination `Path` to be created or replaced.
- `options`: options controlling behavior, such as `StandardCopyOption.REPLACE_EXISTING`, `StandardCopyOption.COPY_ATTRIBUTES`, or `LinkOption.NOFOLLOW_LINKS`.
- Return value: the target `Path` itself.
- `IOException`: reports errors during copying; a specific subclass such as `FileAlreadyExistsException` may be received.

Clearly distinguish this overload from:

~~~java
long bytes = Files.copy(inputStream, target, copyOptions);
long bytes = Files.copy(source, outputStream);
~~~

The other two overloads have a `long` return type and their own option sets/contracts. **You cannot assume `COPY_ATTRIBUTES` applies to copying from an arbitrary `InputStream`** because a stream source does not carry a set of `Path`-based file attributes to copy.

### When Passing No Options

~~~java
Path copied = Files.copy(source, target);
~~~

By default, when `target` already exists (including as a symbolic link), the operation fails, **except when source and target are determined to be the same file**: in that case, the method can complete without performing a copy.

If they are two different files and the target already exists, the provider typically throws `FileAlreadyExistsException`; according to Java documentation, this is an *optional specific exception*: production code must still handle general `IOException` because not all providers are required to use the exact same specialized exception type.

By default, it also **does not request copying file attributes** beyond the content and information the provider needs to create the target file. To request preserving attributes, explicitly specify `COPY_ATTRIBUTES`.

## 3. `REPLACE_EXISTING`: Replaces the Target File, Does Not Append

~~~java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

This option permits replacing an entry at the target path if it already exists. It does **not** mean:

- Appending data to the end of the old file (*append*).
- Writing only differing bytes or incremental synchronization.
- Creating any missing parent directories.
- Automatically backing up old content or restoring on error.
- Performing an atomic replacement operation.
- Allowing deletion of a **non-empty target directory** to replace it.

By the `Files.copy` contract, `REPLACE_EXISTING` cannot replace a target that is a **non-empty directory**. Handle `DirectoryNotEmptyException` if the provider uses this specific error; otherwise you must still handle `IOException`.

### Comparison

| Situation | `Files.copy(source, target)` | With `REPLACE_EXISTING` |
| --- | --- | --- |
| Target does not exist yet | Creates a new copy if conditions allow | Also creates a new copy |
| Target is already a regular file different from source | Usually `FileAlreadyExistsException` | Allows replacing the target file |
| Target is a symbolic link | Treated as target already existing by default, so usually errors | Replaces **the link itself**, not the file the link points to |
| Target is a non-empty directory | Does not overwrite | Cannot replace a non-empty directory |
| Source and target are the same file | Completes without actual copying per contract | Also no copy needed when recognized as the same file |

**Practical risk:** if the caller specifies the wrong `target`, this option can cause important old data to be lost. Use this option when the business requirement is genuinely replacement. When the requirement is "do not overwrite," **omit `REPLACE_EXISTING`** and handle conflicts.

`REPLACE_EXISTING` is also **not** a solution against TOCTOU (*time-of-check/time-of-use*): the target state can change between checking and copying, and the documentation states that checking existence and creating the new file is not necessarily atomic with respect to other file system activity.

## 4. `COPY_ATTRIBUTES`: Attempts to Copy Metadata, Not Every Attribute

~~~java
Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES);
~~~

`COPY_ATTRIBUTES` asks the system to attempt copying attributes associated with the source file to the target file. According to Java 17 documentation:

- **Which exact attributes get copied depends on the platform and file system**.
- At a minimum, `last-modified-time` is copied **if both the source and target file stores support it**.
- Copying timestamps can **lose precision** due to the time resolution of the file store.
- Access permissions, ACLs, owner, group, extended attributes, or other metadata **are not guaranteed to be identical** across all systems.
- If copying a **symbolic link** with `NOFOLLOW_LINKS`, copying attributes for the link itself is implementation-dependent; `COPY_ATTRIBUTES` may be ignored for links.

Therefore, you should not claim:

> "`COPY_ATTRIBUTES` preserves 100% of permissions, owner, creation time, and all ACLs."

That goes beyond the Java contract. If a problem genuinely requires preserving a specific attribute, use the corresponding attribute APIs to **read, compare, and handle discrepancies** within what the provider supports, for example:

~~~java
FileTime sourceTime = Files.getLastModifiedTime(source);
FileTime targetTime = Files.getLastModifiedTime(target);

System.out.println("sameTimestamp=" + sourceTime.equals(targetTime));
~~~

This snippet requires importing `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.file.attribute.FileTime`. The comparison result can differ when the target has lower timestamp resolution. `false` does not by itself mean byte data was copied incorrectly; it shows that the timestamps did not match exactly under this comparison.

### Combining REPLACE_EXISTING with COPY_ATTRIBUTES

~~~java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);
~~~

This means:

1. Allow copying to the target path even if the target is an old file needing replacement.
2. Simultaneously request attempting to copy source attributes to the new result.

**There is no guarantee of "replaced and all attributes definitely copied" if an error occurs.** The documentation states that if an `IOException` occurs, the target file may be only partially copied or some attributes may not have been copied yet.

## 5. Runnable Java 17+ Example: Default Fails, Then Replacement Succeeds

Create the file **`CopyOptionsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class CopyOptionsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-options-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "NEW", StandardCharsets.UTF_8);
            Files.writeString(target, "OLD", StandardCharsets.UTF_8);

            try {
                Files.copy(source, target);
                System.out.println("unexpected success");
            } catch (FileAlreadyExistsException exception) {
                System.out.println("withoutReplace=FileAlreadyExistsException");
            }

            Path returned = Files.copy(
                    source,
                    target,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES
            );

            System.out.println("returnedTarget=" + returned.equals(target));
            System.out.println("targetText=" +
                    Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("sourceText=" +
                    Files.readString(source, StandardCharsets.UTF_8));
            System.out.println("sameBytes=" +
                    (Files.mismatch(source, target) == -1L));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CopyOptionsDemo.java
java CopyOptionsDemo
~~~

**Stdout on a typical default file system, when no other process modifies the temporary directory:**

~~~text
withoutReplace=FileAlreadyExistsException
returnedTarget=true
targetText=NEW
sourceText=NEW
sameBytes=true
~~~

Explanation:

- Both `source.txt` and `target.txt` exist before copying.
- The call **without options** is rejected because target already exists.
- The call with `REPLACE_EXISTING` copies the source's content to target.
- Adding `COPY_ATTRIBUTES` requests copying metadata within supported limits. The example does not print timestamps because the result depends on the file system, so one should not assert a fixed time string.
- `Files.copy` returns the target `Path`, so `returned.equals(target)` is `true`.
- `Files.mismatch` (Java 12+) returns `-1L` when two files have identical byte contents. That is a content comparison, **not** confirmation that all attributes match.
- Copying does not delete the source; `sourceText=NEW` verifies the source file remains intact in the demo case.
- `finally` cleans up the temporary files and directory so the demo does not depend on fixed machine paths.

### Why `BufferedInputStream` Is Not Needed

`Files.copy(Path, Path, CopyOption...)` delegates the copy work to the file system provider/JDK. You do not need to write your own `read/write` loop just to specify `REPLACE_EXISTING` and `COPY_ATTRIBUTES`. Only when you need to transform content during copying, compute a streaming checksum, or apply a special format should you consider streams/channels with your own metadata and error handling model.

## 6. Observing the lastModifiedTime Attribute

To verify the meaning of `COPY_ATTRIBUTES`, you can assign a last-modified time to the source before copying:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

// Snippet: source and target are declared and have appropriate parents.
FileTime expectedTime = FileTime.from(
        Instant.parse("2020-02-03T04:05:06Z"));

Files.setLastModifiedTime(source, expectedTime);

Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);

FileTime sourceTime = Files.getLastModifiedTime(source);
FileTime targetTime = Files.getLastModifiedTime(target);

System.out.println("sourceTime=" + sourceTime);
System.out.println("targetTime=" + targetTime);
~~~

This is an **illustrative snippet** that must be placed inside a method handling `IOException`. It does not produce invariant stdout across every file system: a provider may store time at a different resolution, so the value read back may be rounded.

The proper check is evaluating **according to application requirements**: for example, if a file store supports one-second precision, compare to the second, or require an exact match on a specified environment. If timestamps matter but the target does not support the same precision, that is a platform limitation to document rather than silently claiming "copied all attributes."

Also distinguish:

- `size`: byte content size; if content copies successfully, the file size normally reflects the new content, and is **not** something requiring `COPY_ATTRIBUTES` to appear.
- `lastModifiedTime`: the minimum time attribute requested to be copied when both file stores support it.
- `lastAccessTime`, `creationTime`, `owner`, `permissions`, `ACL`, and extended metadata: must not be assumed identical from a single `COPY_ATTRIBUTES` call alone.

## 7. What If `COPY_ATTRIBUTES` Is Not Added?

~~~java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

Data is copied under the `Files.copy` contract, without requesting **preservation of source metadata**. The target can receive new timestamps or attributes according to the system's file creation rules.

Examples:

- A system receiving an exported file needs the new content and does not need to keep the source file's modification time: using only `REPLACE_EXISTING` suffices.
- A backup/data-copy workflow wants to preserve `lastModifiedTime` for user comparison: add `COPY_ATTRIBUTES`, then verify the attributes that truly matter.

**Do not confuse** the requirement "copy a file" with "copy a file along with all security attributes." Those are two different contract levels; the latter must explicitly specify which attributes must be preserved and the behavior when the system does not support them.

## 8. When Source or Target Is a Symbolic Link

A symbolic link has two aspects: the **link entry** itself and the **target it points to**.

### When the Source Is a Symbolic Link

By default, `Files.copy(sourceLink, target)` **follows the source symbolic link** and copies **the file the link points to**, if the link can be resolved.

If you want to copy **the symbolic link itself**, use `LinkOption.NOFOLLOW_LINKS`:

~~~java
Files.copy(
        sourceLink,
        targetLink,
        LinkOption.NOFOLLOW_LINKS
);
~~~

This is a snippet requiring `Files`, `LinkOption`, and appropriate `Path` objects. It requires the provider to support symbolic link operations; it may not run on every operating system, file system, or permission configuration.

| Source | Option | Object requested to copy |
| --- | --- | --- |
| Symlink pointing to a file | Default | The file the link points to |
| Symlink | `NOFOLLOW_LINKS` | The symbolic link itself |
| Symlink + `COPY_ATTRIBUTES` + `NOFOLLOW_LINKS` | Both options | The link itself; copying **the link's attributes** may be ignored depending on implementation |

### When the Target Is a Symbolic Link

With `REPLACE_EXISTING`, if `target` is currently a symbolic link, **the symbolic link itself is replaced**, not the file the link points to. This is a common point of confusion:

~~~text
targetLink --> important.txt

Files.copy(source, targetLink, REPLACE_EXISTING)

Requested result:
- the targetLink entry is replaced by the copy
- content is NOT written directly into important.txt through the link
~~~

Still, do not treat this as a general defense against all symlink races: the directory tree and parent components can still be altered under another actor's control. For paths from untrusted data, you must evaluate permissions, parent paths, policy, and the atomicity of actual operations.

## 9. Directory Copy Is Shallow, Not Automatically Recursive

A common misconception is that `Files.copy(sourceDirectory, targetDirectory)` automatically copies the entire file tree. According to Java 17:

> When the source is a directory, this API creates an **empty directory** at the target; it does not automatically copy the entries inside.

Runnable example: create a directory containing a child file and then copy that directory.

Create **`DirectoryCopyDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryCopyDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("directory-copy-");
        Path source = Files.createDirectory(root.resolve("source"));
        Path child = Files.writeString(
                source.resolve("inside.txt"), "hello",
                StandardCharsets.UTF_8
        );
        Path target = root.resolve("target");

        try {
            Files.copy(source, target);

            System.out.println("sourceChildExists=" +
                    Files.exists(child));
            System.out.println("targetIsDirectory=" +
                    Files.isDirectory(target));
            System.out.println("targetChildExists=" +
                    Files.exists(target.resolve("inside.txt")));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(child);
            Files.deleteIfExists(source);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run:

~~~bash
javac DirectoryCopyDemo.java
java DirectoryCopyDemo
~~~

Stdout in a normal environment:

~~~text
sourceChildExists=true
targetIsDirectory=true
targetChildExists=false
~~~

To copy **an entire tree**, you need recursive traversal, such as `Files.walkFileTree` with a `FileVisitor` and separate operations for each directory/file. When doing so, you must clearly decide whether to follow symbolic links, directory creation order, depth limits, error handling, and which metadata to restore after copying children. Adding `COPY_ATTRIBUTES` to a directory copy **does not turn it into a recursive copy**.

## 10. `Files.copy` Is Not an Atomic Operation

Java documentation explicitly states that copying a file **is not an atomic operation**. If an `IOException` occurs mid-way:

- The target may have already been replaced and contain only **partial data**.
- Some attributes may have been copied while others have not.
- The target's old content may be gone; there is no automatic rollback.
- Other readers may observe intermediate states of the target during certain stages, depending on provider and implementation.
- An error while copying metadata can still cause the operation to fail even after content was partially or completely transferred.

Therefore, the following **should not** be viewed as a completely safe transaction:

~~~java
Files.copy(source, target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
System.out.println("published");
~~~

The line `published` only proves the `copy` call completed without throwing an exception. It does not prove that checksums/metadata per business policy were verified, that the file was durably synced to disk, or that remote readers already see the content.

If an error occurs, code must assess the target's state, cleanup policy, and retry feasibility. **Do not blindly delete target** if target could be shared data or may have already been replaced by another task while processing.

## 11. A Safer Pattern When Publishing Files

A commonly used approach is:

1. Create a **temporary file in the target directory** (usually to facilitate moving within the same file store).
2. Copy source to the temporary file, with `COPY_ATTRIBUTES` if needed.
3. If required, verify bytes using `Files.mismatch`, size, checksum, or metadata.
4. Move the temporary file to the official name; you may **request** `ATOMIC_MOVE` if the provider supports it.
5. Delete the temporary file in `finally` if it has not been moved away.

Java 17 utility class example, **`StagedCopy.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class StagedCopy {
    private StagedCopy() {}

    public static void publish(Path source, Path target)
            throws IOException {
        Path parent = target.toAbsolutePath().getParent();
        if (parent == null) {
            throw new IllegalArgumentException("Target needs a parent");
        }

        // parent must exist and the caller must have confirmed write permission.
        Path staged = Files.createTempFile(
                parent, ".staged-copy-", ".part");

        try {
            // createTempFile already created staged; REPLACE_EXISTING is needed
            // so copy can write into that temporary name.
            Files.copy(
                    source,
                    staged,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES
            );

            if (Files.mismatch(source, staged) != -1L) {
                throw new IOException("Content mismatch after copy");
            }

            Files.move(
                    staged,
                    target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING
            );
        } finally {
            Files.deleteIfExists(staged);
        }
    }
}
~~~

This is a **compilable class without `main`**. The caller passes suitable source and target; the method can throw `IOException` if it cannot complete. The snippet shows a **strategy**, not a promise of uniform support across all systems.

Limitations to understand thoroughly:

- `Files.move(..., ATOMIC_MOVE, REPLACE_EXISTING)`: when `ATOMIC_MOVE` is specified, **other options are ignored per the `Files.move` contract**; if target already exists, whether it **replaces or errors** is implementation-dependent. Do not assume it is always "atomic replace existing" on every provider.
- If the provider does not support atomic move, `AtomicMoveNotSupportedException` can occur. In the example, the method **does not silently downgrade** to a non-atomic move.
- The **copy into staged** itself is still non-atomic, though it does not publish under the final target name until the move step succeeds.
- `Files.mismatch` verifies byte content as read at two moments; the source can still be modified **concurrently** during or between copy and verification. If a consistent snapshot is required, you need locks, versioning, immutable sources, or another system mechanism.
- `ATOMIC_MOVE` does not mean all bytes have been `fsync`'d/durably persisted to hardware against power loss. If durability is required, design an appropriate synchronization mechanism within platform capabilities.
- If the move succeeds, `staged` is no longer at the temporary name, so `deleteIfExists(staged)` does not delete target. If the move fails, cleanup attempts to delete the temporary file. Unexpected states may still require manual monitoring.
- With untrusted directories/targets, parent paths and symlinks need additional protection mechanisms.

If the application genuinely requires **atomically replacing an existing target**, you must confirm that the deployment environment's file system/provider supports the exact desired behavior. Do not feel confident merely seeing both `ATOMIC_MOVE` and `REPLACE_EXISTING` in the call.

## 12. Exceptions: Knowing What Errors Can Occur

`Files.copy(Path, Path, CopyOption...)` declares `throws IOException` and can produce errors such as:

| Case | Typical exception / signal |
| --- | --- |
| Target already exists without `REPLACE_EXISTING` | `FileAlreadyExistsException` or `IOException` |
| Target is a non-empty directory that cannot be replaced | `DirectoryNotEmptyException` or `IOException` |
| Source or an essential component does not exist | `NoSuchFileException` or `IOException` |
| Insufficient access permissions | `AccessDeniedException` or `IOException` |
| Device, file store, or network filesystem read/write failure | `IOException` |
| Option unsupported by provider | `UnsupportedOperationException` |
| Certain arguments are `null` | `NullPointerException` per API contract |

Specialized I/O subclasses can be **optional specific exceptions**: never omit general `IOException` handling.

Minimal handling pattern:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class CopyWithErrors {
    private CopyWithErrors() {}

    public static Path copy(Path source, Path target)
            throws IOException {
        try {
            return Files.copy(
                    source, target,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES
            );
        } catch (AccessDeniedException exception) {
            throw new IOException(
                    "Access denied while copying to " + target,
                    exception
            );
        } catch (FileAlreadyExistsException exception) {
            // May happen in specific environments/providers or
            // when a concurrent operation changes state.
            throw new IOException(
                    "Target collision while copying to " + target,
                    exception
            );
        }
    }
}
~~~

Example class without `main`. It preserves `cause` so the caller has diagnostic information. Unless there is a specific business-classification need, **propagating the original `IOException`** is usually simpler than wrapping it with a similar message.

Avoid arbitrarily logging sensitive paths. Not every failure should be retried: `AccessDeniedException`, directory-not-empty, or misconfigured paths are usually not solved by repeated retries.

## 13. Factors That Make Results Environment-Dependent

### File Stores, Timestamps, and Permissions

Copying within the same filesystem generally has better conditions than copying between two different providers/file stores, yet one cannot deduce this guarantees identical attributes. Timestamp precision, ownership, ACLs, extended attributes, and copy implementations can all differ across Windows, Linux, macOS, and network filesystems.

If the program requires an essential attribute such as POSIX permissions or ACLs, check capability and use `Files.readAttributes`/attribute view APIs to verify explicitly rather than relying on `COPY_ATTRIBUTES` as a blanket guarantee for all metadata.

### Parent Directory of Target

`Files.copy` has no contract to automatically create an entire directory tree. If `target` is `output/reports/data.txt` and `output/reports` does not exist yet, copying can fail.

When the application is permitted to create parent directories:

~~~java
Path parent = target.toAbsolutePath().getParent();
if (parent != null) {
    Files.createDirectories(parent);
}
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

This is a **snippet** with `Path` `source/target` and `IOException` handling. Creating parent directories is a **separate operation** that can fail and can partially create the tree before erroring.

### Source and Target Are the Same File

According to `Files.copy`, when source and target are considered **the same file**, the method completes without creating a copy. This is not just path-string comparison: hard links or two different paths representing the same file may need the file system to identify them. When you truly want to know whether two paths point to the same file right now, see `Files.isSameFile`, though this too is not a lock preventing concurrent changes.

### Copying Across Multiple Providers

`Files.copy` can work with two `Path` instances belonging to different providers within the Java contract. In that case, support for metadata, symlinks, permissions, and performance varies. Do not assume cross-provider copies can always replace, preserve attributes, and run at the same speed as local disk copies.

## 14. Does File Copying Preserve Text Content?

`Files.copy(Path, Path, ...)` copies files at the file level without decoding UTF-8 and re-encoding as you would manually with `BufferedReader`/`BufferedWriter`. Therefore it is suited for:

- Images, PDFs, ZIPs, and binary files.
- Text files that do not need encoding or line-ending changes.
- Any data needing exact byte-for-byte copying when the operation succeeds.

If you need to convert UTF-8 to UTF-16, change newlines, or edit content, a separate text-processing step is required; neither `COPY_ATTRIBUTES` nor `REPLACE_EXISTING` performs charset conversion.

After copying, bytes can be compared using:

~~~java
long difference = Files.mismatch(source, target);
boolean identical = difference == -1L;
~~~

`Files.mismatch` is not a cryptographic checksum; it compares content readable by the API and can throw `IOException`. It also does not compare permissions, ACLs, or timestamps.

## 15. Common Mistakes

**Mistake 1 — Forgetting `REPLACE_EXISTING` and thinking copy overwrites by default.**  
By default, an existing target causes copy to be rejected (except when source/target are the same file). Choose the overwrite policy explicitly.

**Mistake 2 — Using `REPLACE_EXISTING` when the business rule actually forbids overwriting.**  
This can cause loss of the old target file. If "create only" is needed, omit the option and handle conflicts per contract.

**Mistake 3 — Thinking `COPY_ATTRIBUTES` preserves all metadata identically.**  
Incorrect. The attribute list and precision depend on the system; at minimum last-modified-time if both stores support it. Explicitly verify any attributes truly required.

**Mistake 4 — Thinking `Files.copy` has rollback and atomicity.**  
No. On an I/O error, target may be incomplete or partially replaced. For important data, consider staging files and appropriate publishing.

**Mistake 5 — Copying a directory and expecting all child trees.**  
`Files.copy` on a directory creates an empty target directory; recursion requires walking the file tree separately.

**Mistake 6 — Confusing symbolic link behavior.**  
A symlink source follows the link by default; `NOFOLLOW_LINKS` copies the link itself. A symlink target with `REPLACE_EXISTING` replaces **the link entry**, without writing through to the target file the link points to.

**Mistake 7 — Using `COPY_ATTRIBUTES` for the `InputStream` copy overload.**  
That is a different overload; a stream source has no corresponding `Path`-style attribute set. Read the contract of each overload.

**Mistake 8 — Assuming REPLACE_EXISTING deletes every kind of target.**  
It cannot replace a non-empty target directory via copy as one might hope. Additionally, permissions, file stores, and concurrency can cause failures.

**Mistake 9 — Only checking `Files.exists(target)` before copying.**  
State can change, and `exists==false` does not always prove the file is absent. Let the `copy` call itself execute and handle errors.

**Mistake 10 — Extrapolating from one local test to all OSes/providers.**  
Timestamp precision, permissions, symlink handling, specific exceptions, and atomic move capabilities differ. Test on the deployment environment, especially if business logic depends on metadata.

## 16. Option Selection Workflow for Real Scenarios

| Need | How to use | What to verify |
| --- | --- | --- |
| Copy only if target does not exist yet | `Files.copy(source, target)` | Handle existing target and I/O errors |
| Allow replacing target | `Files.copy(source, target, REPLACE_EXISTING)` | Is losing old target content truly permitted? |
| Replace and retain some source metadata | `Files.copy(source, target, REPLACE_EXISTING, COPY_ATTRIBUTES)` | Check mandatory metadata and provider limits |
| Copy the symbolic link itself | Add `LinkOption.NOFOLLOW_LINKS` | Provider supports symlinks and link attributes are not guaranteed |
| Copy an entire directory tree | `Files.walkFileTree` + copy each entry | Order, error recovery, symlinks, depth, attributes |
| Publish a file with atomic replacement capability | Copy to staging then request `ATOMIC_MOVE` | Not all providers support it and behavior when target exists depends on implementation |
| Only copy bytes to a stream | `Files.copy(source, outputStream)` | Different overload; no Path→Path `COPY_ATTRIBUTES` |
| Copy from a stream into a file | `Files.copy(inputStream, target, options)` | Limited option support, no source metadata to copy |
| Verify identical content | `Files.mismatch(source, target) == -1L` | Does not check metadata, races, or durable persistence |

## 17. Checklist for Production Code Review

- [ ] Is the source a **regular file**, directory, or symbolic link; is the link-following behavior chosen appropriately?
- [ ] If target exists, does policy permit **replacement**?
- [ ] If metadata is needed, was `COPY_ATTRIBUTES` added and **which attributes** are mandatory identified?
- [ ] Is it understood that timestamps can lose precision and owner/ACL are not automatically guaranteed identical?
- [ ] Has target's parent directory been confirmed to exist, have permissions, and be protected from unintended interference?
- [ ] Are `IOException` and provider-specific cases handled without assuming a subclass always appears?
- [ ] Is there a policy when a copy fails to avoid publishing an incomplete file?
- [ ] Were same-file source/target, symlinks, and races checked if paths come from outside?
- [ ] Have you avoided accidentally copying a directory while thinking all contents inside were copied?
- [ ] If atomic publishing is needed, were `ATOMIC_MOVE`, replace-existing limits, and avoiding silent downgrade considered?
- [ ] If byte content guarantees are required, is verification done with `Files.mismatch`/hashing as needed?
- [ ] If true file durability or remote ACK is required, is there a dedicated mechanism outside `Files.copy`?
- [ ] Do unit tests use temporary directories, clean up, and avoid depending on fixed paths?
- [ ] Are private data/paths kept out of public log channels when errors occur?

## 18. Self-Check Questions

**1.** What does `Files.copy(source, target)` do when target already exists?  
**Answer:** Fails by default (unless source and target are the same file); `FileAlreadyExistsException` can typically be observed.

**2.** Does `REPLACE_EXISTING` automatically make the copy operation atomic?  
**Answer:** No. `Files.copy` is not an atomic operation by contract.

**3.** Does `COPY_ATTRIBUTES` guarantee POSIX permissions/ACLs/owner are identical?  
**Answer:** No. Actual copied attributes depend on provider and file store; at minimum copying last-modified-time is requested when both support it, with possible precision loss.

**4.** If target is a symbolic link, does adding `REPLACE_EXISTING` mean overwriting the file the link points to?  
**Answer:** No. It replaces **the symbolic link itself at the target path**.

**5.** If source is a symbolic link without `NOFOLLOW_LINKS`, what gets copied?  
**Answer:** By default it copies the item the symlink points to; add `NOFOLLOW_LINKS` to copy the link itself if the provider supports it.

**6.** Does `Files.copy(sourceDir, targetDir, COPY_ATTRIBUTES)` copy all child files?  
**Answer:** No. A single directory copy creates only an empty target directory; a separate tree-traversal algorithm is needed.

**7.** If copying fails mid-way, is target guaranteed to still keep its old bytes?  
**Answer:** No. Target may have been replaced or be incomplete; design appropriate error handling and data publishing.

**8.** What does `Files.mismatch(source, target) == -1L` prove?  
**Answer:** The byte contents compared are identical during that operation; it does not assert all metadata, file identity, or durable storage.

**9.** What if you want to enforce atomic publishing and the provider does not support `ATOMIC_MOVE`?  
**Answer:** Handle `AtomicMoveNotSupportedException`, report that the requirement cannot be met or choose a separately evaluated solution; do not treat a regular move as equivalent.

**Key takeaway:** `REPLACE_EXISTING` decides **whether replacing an existing target entry is permitted**. `COPY_ATTRIBUTES` requests **attempting to copy metadata within what the file system supports**. Combining both still **does not** yield an atomic transaction, automatic backup, or guarantee of identical metadata. Choose options per business contract, handle errors, and use staging/verification when data matters.

## Official API Documentation (Java SE 17)

- [`Files.copy(Path, Path, CopyOption...)` and notes on atomicity, attributes, symlinks](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#copy(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...))
- [`StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [`LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
- [`FileTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html)
- [`Files.mismatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path))
