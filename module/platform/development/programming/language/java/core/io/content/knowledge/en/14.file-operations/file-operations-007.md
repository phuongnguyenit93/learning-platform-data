# Cross-Filesystem Operations and Provider Limits in Java NIO.2

## Objectives

Java NIO.2 enables file operations through `Path`, `FileSystem`, `FileSystemProvider`, and the `Files` utility class. A `Path` does not necessarily point to a file on the local machine's disk: it can represent an entry inside a ZIP/JAR, an in-memory file system, or a storage system provided by a library. Therefore, **operating on paths belonging to different file systems/providers** has its own rules and limits, and cannot be extrapolated from copying/renaming on the same drive.

In this lesson, you will:

- Distinguish `Path`, `FileSystem`, `FileSystemProvider`, and `FileStore`.
- Know how to determine the provider of a `Path` and identify when two paths belong to different providers.
- Clearly understand when `Files.copy(source, target)` / `Files.move(source, target)` can operate across providers; and why `ATOMIC_MOVE` may be unsupported.
- Know the limits of `Path.resolve`, `relativize`, `toFile`, file attributes, symbolic links, permissions, and closing file systems.
- Practice a Java 17+ example copying a file from the default filesystem into a ZIP filesystem.
- Design file operations with error checks, resource limits, and an appropriate rollback strategy.

## 1. What Are a File System and a Provider?

`java.nio.file.Path` represents a pathname **bound to a `FileSystem`**. `FileSystem` describes how paths are constructed and parsed, root directories, separators, supported attributes, and the lifecycle of the file system. A `FileSystemProvider` is the implementation that provides I/O operations for its associated file systems.

```text
                    java.nio.file.Files
                      (utility API)
                           |
                   delegates operations
                           v
                FileSystemProvider
                /                \
       "file" provider        "jar" provider
            |                      |
    Default FileSystem      ZIP/JAR FileSystem
            |                      |
        OS Path             Path in archive
    /tmp/report.txt         /docs/report.txt
```

Examples:

- The default **`file`** provider accesses the file system provided by the operating system. A single default `FileSystem` can see multiple drives/partitions/mounts.
- The **`jar`** provider (JDK module `jdk.zipfs`) enables reading and writing entries inside ZIP/JAR files via the `Path`/`Files` API.
- A library can add a provider for a specialized file system. Support for reading, writing, metadata, file locking, or symbolic links depends on the actual implementation.

**Do not conflate the three concepts:**

| Concept | Meaning |
| --- | --- |
| `FileSystemProvider` | Implementation of the filesystem access interface; usually identified by a URI scheme (`file`, `jar`, …). |
| `FileSystem` | A file system instance supplied by a provider; one provider can manage multiple instances. |
| `FileStore` | Storage area/storage unit reported by the filesystem (e.g., partition, volume, mount); not synonymous with provider. |

**Two paths on two drives do not necessarily have two different providers.** On a machine using the default `file` provider, multiple drives or mounts usually still belong to the same provider, even though atomic rename between them is not guaranteed.

## 2. Identifying the Provider of a `Path`

A path provides ways to retrieve its filesystem and provider:

```java
// Illustrative snippet: path is an already created Path.
FileSystem fs = path.getFileSystem();
FileSystemProvider provider = fs.provider();
String scheme = provider.getScheme();
```

You need `import java.nio.file.FileSystem` and `import java.nio.file.spi.FileSystemProvider` if using this snippet as part of a program.

For a path on the default filesystem, the scheme is typically `file`. For a ZIP entry path from the standard provider, the scheme is `jar`.

You can compare two providers with:

```java
boolean sameProvider =
        pathA.getFileSystem().provider()
        == pathB.getFileSystem().provider();
```

This is only a comparison of **provider objects**. It does not prove two paths belong to **the same `FileSystem`**, the same `FileStore`, the same physical device, or support atomic moves.

When you want to compare **the exact same FileSystem instance**, you can compare `pathA.getFileSystem() == pathB.getFileSystem()` in an appropriate context. When querying which storage area a filesystem resides on, `Files.getFileStore(path)` can provide information, yet the provider may not support or may restrict these details; handle `IOException`.

## 3. Which Operations Work Across Providers and Which Do Not

There is no rule saying "if providers differ, every NIO.2 API fails." You must read the contract of **each method**.

| Operation | When source and target have different providers |
| --- | --- |
| `Files.copy(Path, Path, ...)` | The high-level API **allows** source and target from different providers; can still fail due to permissions, file type, provider limits, attributes, or resources. |
| `Files.move(Path, Path, ...)` | The high-level API also allows targets from another provider; when direct rename is impossible, a non-atomic operation may copy then delete and has many failure modes. |
| `Files.move(..., ATOMIC_MOVE)` | **Not guaranteed** across filesystems/`FileStore`/providers; if atomic execution is impossible, throws `AtomicMoveNotSupportedException`. |
| `source.resolve(other)` | Path resolution belongs to one filesystem; passing `other` from another provider can throw `ProviderMismatchException`. |
| `source.relativize(other)` | Requires compatible paths; differing providers can throw `ProviderMismatchException` or path-type errors. |
| `Files.isSameFile(source, target)` | If the two paths are attached to different providers, the result is `false`, not an inference about whether the two files' contents are equal. |
| `path.toFile()` | Supported only for the default filesystem; ZIP/non-default `Path` typically throws `UnsupportedOperationException`. |
| `Files.readAttributes` / `getAttribute` | View names and attributes must be supported by the provider; there is no guarantee every provider supports POSIX, DOS, owner, ACL, symlink, or timestamps with identical precision. |

Distinguish **`Files.copy`** (the high-level facade method that can coordinate two providers) from **`FileSystemProvider.copy`** (the SPI of a single provider, which by contract requires both `Path` arguments to belong to that provider). When writing normal application code, use `Files.copy` instead of calling `provider.copy` directly with two different path types.

### "Can Be Performed" Does Not Mean "Always Succeeds"

Even `Files.copy` designed for two different providers can reject an operation because:

- The target is a read-only or already closed filesystem.
- Creating that file type, symbolic links, attributes, or copy options is unsupported.
- Target file/directory already exists, parent path does not exist, or permissions are insufficient.
- The source file changes while being read.
- Out of space, quota limit, network I/O error, or data exceeds provider limits.

Therefore, treat cross-filesystem operations as **an I/O transfer that can fail mid-way**, not an instant rename statement.

## 4. Java 17+ Example: Copying a File from the Default Filesystem into a ZIP

The following example uses the JDK's ZIP filesystem to demonstrate **two genuinely different providers** without requiring two physical drives. The program creates a temporary directory, creates a source file, opens a ZIP archive as a filesystem, copies data into the ZIP, checks the providers, and reads the content back. At the end, it closes the ZIP and cleans up the temporary files.

Save the file **`CrossProviderCopyDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderMismatchException;
import java.util.Map;

public class CrossProviderCopyDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("provider-demo-");
        Path source = root.resolve("hello.txt");
        Path archive = root.resolve("sample.zip");

        try {
            Files.writeString(source, "Hello ZIP", StandardCharsets.UTF_8);

            URI zipUri = URI.create("jar:" + archive.toUri());
            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {
                Path entry = zip.getPath("/hello.txt");
                Files.copy(source, entry);

                System.out.println("source scheme = "
                        + source.getFileSystem().provider().getScheme());
                System.out.println("target scheme = "
                        + entry.getFileSystem().provider().getScheme());
                System.out.println("same provider = "
                        + (source.getFileSystem().provider()
                           == entry.getFileSystem().provider()));
                System.out.println("copied content = "
                        + Files.readString(entry, StandardCharsets.UTF_8));

                try {
                    source.resolve(zip.getPath("other.txt"));
                } catch (ProviderMismatchException e) {
                    System.out.println("resolve = ProviderMismatchException");
                }

                try {
                    entry.toFile();
                } catch (UnsupportedOperationException e) {
                    System.out.println("ZIP toFile = UnsupportedOperationException");
                }
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(root);
        }
    }
}
```

Run on **JDK 17+ with the `jdk.zipfs` module** (standard full JDKs provide this module):

```bash
javac CrossProviderCopyDemo.java
java CrossProviderCopyDemo
```

Stdout in a standard JDK environment supporting the ZIP filesystem:

```text
source scheme = file
target scheme = jar
same provider = false
copied content = Hello ZIP
resolve = ProviderMismatchException
ZIP toFile = UnsupportedOperationException
```

**Explanation:**

1. `source` belongs to the default filesystem (`file`). `entry` belongs to the ZIP filesystem (`jar`).
2. `Files.copy(source, entry)` transfers content into the ZIP entry even though the two providers differ. This is the high-level `Files` API, not the result of coercing both paths into the same type.
3. `source.resolve(zip.getPath("other.txt"))` attempts to mix a ZIP `Path` into a `resolve` call on a default-filesystem path, so it throws `ProviderMismatchException`. With these path types, `Path` is not a plain character string that can be mixed arbitrarily.
4. `entry.toFile()` cannot be used because `java.io.File` represents default-filesystem paths, not ZIP entry paths.
5. `try-with-resources` **closes the ZIP `FileSystem`** before deleting the archive file. Paths inside the ZIP can no longer be used for I/O after that filesystem has closed.
6. The example creates a real ZIP file at the temporary path `sample.zip`. Custom JRE-only environments lacking `jdk.zipfs` may throw `ProviderNotFoundException`; file-creation permissions or quotas can also cause I/O errors.

**Key lesson:** `Files.copy` works across multiple providers, yet **does not turn a ZIP `Path` into an OS `Path`**. Keep and use each path created by its corresponding filesystem.

## 5. `Files.move` and the Limits of `ATOMIC_MOVE`

When renaming a file within the same directory on the same storage volume, the OS can usually finish quickly without copying content. When moving data to a different filesystem or provider, you cannot assume such a rename operation is still possible.

```java
// Snippet: source and target are already defined Paths.
Files.move(source, target);
```

`Files.move` allows the target path to have a different provider, yet in practice it may amount to **creating a copy and then deleting the source**. As a result:

- It can take time proportional to file size.
- Metadata preservation is not completely uniform.
- If an error occurs mid-way, source and target may **both exist**, target may be missing data, or another state may occur depending on implementation.
- There is no guarantee that a complex directory tree is automatically moved recursively.
- There is no guarantee of atomic execution merely because the method is named `move`.

### Requesting Atomic Move

```java
// Snippet, requires importing java.nio.file.Files;
// java.nio.file.StandardCopyOption.
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

`ATOMIC_MOVE` requests an atomic move at the filesystem level. If unsupported, the method throws `AtomicMoveNotSupportedException`. Source and target being on different `FileStore`s or different providers are typical cases where atomic rename cannot be performed.

**Never silently drop `ATOMIC_MOVE`** if business logic relies on the rule "readers see only the old version or the new version, never a half-copied file." A non-atomic fallback can break the application's safety contract.

A semantically sound way to handle the exception:

```java
// Snippet: source/target defined, method declares IOException.
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (java.nio.file.AtomicMoveNotSupportedException e) {
    // Business rule requires atomicity: report unsupported,
    // do not automatically convert to a regular move.
    throw new java.io.IOException(
            "The destination cannot provide an atomic move", e);
}
```

If business rules **accept a non-atomic move**, explicitly design a separate workflow with staging, content verification, cleanup, and error recovery. Switching from atomic to non-atomic is not simply editing a parameter to make the exception go away.

### `REPLACE_EXISTING` Does Not Solve Everything

`StandardCopyOption.REPLACE_EXISTING` helps replace certain types of existing target files. It does not guarantee:

- Replacing a non-empty target directory.
- Atomic writes or rollback when copying fails.
- Preserving all attributes of the source file.
- Absence of races between existence checking and replacement.

When `ATOMIC_MOVE` is specified, other move options are ignored per specification; how an existing target file is handled can depend on implementation. Do not treat `REPLACE_EXISTING` plus `ATOMIC_MOVE` as a guaranteed atomic replacement on every provider.

## 6. `Files.copy`: Content, Attributes, and Symbolic Links

Copy a regular file with:

```java
// Snippet: source/target are Paths, handle IOException at caller.
Files.copy(source, target);
```

To replace the target file if policy allows:

```java
Files.copy(source, target,
        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
```

Some options:

- **`REPLACE_EXISTING`:** attempts to replace an existing target within API limits; does not automatically wipe a non-empty directory tree.
- **`COPY_ATTRIBUTES`:** requests attempting to copy attributes. Which attributes are **actually** copied depends on the provider and file store; `lastModifiedTime` is the stated minimum when both sides support it, and timestamp precision can vary.
- **`NOFOLLOW_LINKS`:** does not follow source symbolic links during copying. Creating a corresponding symbolic link at the target can fail if the target provider does not support symbolic links.

Copying is not an atomic operation. If `IOException` arises, the target file may already exist and be **incomplete**. For important content, you usually need to:

1. Choose a temporary destination on **the final target's** filesystem.
2. Copy into the temporary destination and verify content as required (size, checksum, or format).
3. Only afterward apply the final-target publishing method; if atomicity is required, attempt an atomic rename **within the same compatible storage area**.
4. If atomic rename is unsupported and business logic mandates atomicity, report an error rather than assuming a fallback is equivalent.
5. Clean up temporary files you own on error; note that crashes can still leave temp files behind for a recovery process to handle.

Staging on the target filesystem helps **reduce** the risk of an incomplete final file appearing; it does not automatically solve durability, fsync, security, or recovery.

## 7. Directories Are Not Recursively Copied/Moved by a Single Call

`Files.copy(sourceDir, targetDir)` **does not automatically copy all child files**. Under the general contract, when source is a directory, the copy operation creates a corresponding target directory without copying entries inside. To copy a tree, implement custom traversal logic, such as `Files.walkFileTree`, handling:

- Creating each target directory in the proper order.
- Copying child files.
- Resolving symbolic links and avoiding loops.
- Limits on entry count, depth, total bytes, and access errors.
- Mapping metadata based on target provider capabilities.
- Behavior if source files change during copying or targets collide.

### Java 17+ Example: Directory Copy Does Not Automatically Copy Child Files

Save as **`DirectoryCopyDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryCopyDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("directory-copy-");
        Path source = root.resolve("source");
        Path target = root.resolve("target");

        try {
            Files.createDirectory(source);
            Files.writeString(source.resolve("child.txt"),
                    "data", StandardCharsets.UTF_8);

            Files.copy(source, target);
            System.out.println("target directory exists = "
                    + Files.isDirectory(target));
            System.out.println("child was copied = "
                    + Files.exists(target.resolve("child.txt")));
        } finally {
            Files.deleteIfExists(source.resolve("child.txt"));
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
```

Run:

```bash
javac DirectoryCopyDemo.java
java DirectoryCopyDemo
```

Stdout:

```text
target directory exists = true
child was copied = false
```

This example is not a cross-provider copy; it isolates an important limitation **that applies even on the same filesystem**. When copying trees across providers, the limitation becomes even more significant because the two sides may differ in symlinks, attributes, and permissions.

## 8. `ProviderMismatchException`: Errors from Mixing Incompatible Paths

`Path` is **an object belonging to a specific filesystem**, not merely an arbitrary path string. For example, a `/docs/report.txt` path inside a ZIP does not specify the OS file `/docs/report.txt`.

Operations like `resolve` and `relativize` belong to **that filesystem's own pathname rule system**. Passing a path from another provider into them can throw `ProviderMismatchException`.

**Avoid the wrong approach:**

```java
// Illustrative snippet: nativePath belongs to the "file" provider,
// zipPath belongs to the "jar" provider.
Path wrong = nativePath.resolve(zipPath);
```

Do not work around it by coercing `zipPath.toString()` into a native `Path` and treating it as the same file. The string `/docs/report.txt` does not contain enough information about the provider, archive, or mount. Doing so usually **changes the meaning of the path** rather than converting a ZIP path into a native path.

**The right approach:** When copying, pass **the two original `Path` objects** directly to `Files.copy(nativePath, zipPath)`. When constructing child paths inside a ZIP, use `zipPath.getFileSystem().getPath(...)` or `zipDirectory.resolve("child.txt")` with relative components belonging to that filesystem.

### `Path.toFile()` Is Not a Bridge Across All Providers

`java.io.File` was designed for the default filesystem. Therefore:

```java
// Snippet: zipEntry is a Path from a ZIP FileSystem.
File legacy = zipEntry.toFile(); // UnsupportedOperationException.
```

When a legacy API only accepts `File` while data sits inside a ZIP, you must change **the processing strategy**, such as using `Files.newInputStream(zipEntry)` with an API accepting `InputStream`, or extracting to a temporary file on the default filesystem if a physical file is genuinely required. Never "fix" it by altering separators in `zipEntry.toString()`.

## 9. File Attributes and Capabilities Differ by Provider

Even when `Files.copy` successfully copies **content**, do not assume metadata is kept intact identically.

| Capability | Why it can differ |
| --- | --- |
| `basic` attributes | Size, timestamps, or file type info may have varying support levels and precision. |
| `posix` permissions | Not every provider models Unix-style `rwx` permission bits. |
| `dos` attributes | Not every system supports hidden/read-only/archive/system like DOS/Windows. |
| ACL/owner/group | Principals and permission models may be incompatible between source and target. |
| Symbolic links | Some providers do not support them, or represent links differently. |
| Hard links | `Files.createLink` may be unsupported or valid only within compatible filesystems. |
| File locking/memory mapping | Capabilities and exceptions depend on provider/channel. |
| Timestamp granularity | Copying timestamps may lose precision. |
| FileStore / quota | Not every provider reports quota/capacity in a useful way. |

Check the filesystem's list of supported attribute views:

```java
// Snippet: path is a valid Path.
System.out.println(path.getFileSystem()
        .supportedFileAttributeViews());
```

Keep in mind the result reflects advertised **provider/filesystem** capabilities; operations on a specific file can still fail due to permissions or object type.

For example, if the target provider does not support `posix`, calling `Files.getPosixFilePermissions(target)` can throw `UnsupportedOperationException`. Do not attempt to manually copy a set of POSIX permissions into a ZIP filesystem without checking provider support and specifications.

**`COPY_ATTRIBUTES` does not mean copying all metadata.** Which attributes get copied depends on source, target, and attribute type. When metadata is an important business requirement, explicitly list mandatory attributes, check support, and **re-verify on the target**.

## 10. Lifecycle of ZIP Filesystems and Custom Providers

A ZIP filesystem created via `FileSystems.newFileSystem(...)` must be **closed** to release resources and finalize necessary internal operations. Once a filesystem is closed:

- Its `Path` objects may still exist as Java objects yet **are no longer usable for I/O**; relevant operations can throw `ClosedFileSystemException`.
- Do not assume `Files.readString(entry)` still works after the `try (FileSystem zip = ...)` block ends.
- Do not delete the ZIP archive while a filesystem is still operating on it if data consistency is needed.
- Do not share one filesystem across multiple components without explicitly defining **who is allowed to call `close()`**.

For third-party providers, the provider's documentation defines opening/closing rules, URI schemes, attributes, concurrency support, and error policies. A `Path` name or filename extension is insufficient to conclude which provider is in use.

## 11. Designing Safer Cross-Filesystem Operations

A real-world workflow usually needs more steps than a single `Files.move` call:

1. **Identify source/target types**: regular file, directory, symlink, or special file; check capabilities of the target filesystem.
2. **Validate paths**: for external input, check absolute paths, `..`, symlinks, and permissions under a security model; do not treat `normalize` alone as safe.
3. **Set resource limits**: byte size, entry count, directory depth, total disk usage, time, and quotas.
4. **Choose a write strategy**: copy directly when partial target files on failure are acceptable; otherwise, copy into a staging area on the target.
5. **Verify**: check size or content checksum (when format and business rules require it), plus attributes that must genuinely be preserved.
6. **Publish results**: if atomic replacement guarantees are required, use `ATOMIC_MOVE` only when the filesystem actually supports it; otherwise, report that the requirement cannot be satisfied.
7. **Delete source only when safe**: if moving via copy+delete, delete only after verifying target data meets criteria. Even then, this does not become an atomic transaction across two filesystems.
8. **Recover from errors**: log state, know which temporary files the application created, avoid deleting valid source/target data; design retry/idempotency if needed.

When using network storage, cloud mounts, or virtual file systems, you must also account for dropped connections, metadata consistency, and separate access-authentication mechanisms. There is no "just call `Files.move`" approach that guarantees equal transaction quality across all providers.

## 12. Common Pitfalls

1. **Assuming every `Path` belongs to `FileSystems.getDefault()`.** ZIP, memory filesystems, and other providers have separate namespaces.
2. **Assuming two drives mean two providers.** They may share the `file` provider while belonging to different `FileStore`s.
3. **Assuming different providers always make `Files.copy` throw `ProviderMismatchException`.** The `Files.copy` facade allows targets from other providers; `Path.resolve`/`relativize` is a different story.
4. **Assuming cross-provider `Files.move` is automatically atomic.** There is no guarantee; `ATOMIC_MOVE` can fail.
5. **Catching `AtomicMoveNotSupportedException` and switching to a normal move without checking business requirements.** Fallback can break consistency expected by readers.
6. **Assuming `COPY_ATTRIBUTES` preserves all ownership/timestamps/ACLs.** Features and precision vary by provider.
7. **Assuming `Files.copy` recursively copies an entire directory.** It does not copy child entries; a custom tree-traversal algorithm is needed.
8. **Assuming `REPLACE_EXISTING` is a rollback mechanism.** An incomplete target file may remain if I/O fails mid-way.
9. **Calling `zipPath.toFile()`.** The `File` API cannot represent arbitrary non-default-filesystem paths.
10. **Taking `zipPath.toString()` and creating `Path.of(...)`.** That loses the ZIP provider meaning and may point to a completely different file.
11. **Continuing to use paths after closing a ZIP filesystem.** Can throw `ClosedFileSystemException`.
12. **Failing to check symbolic links and security boundaries.** Copying a link differs from copying the link target's data; traversal/races need explicit policy.
13. **Checking only `Files.exists` before operating and thinking races cannot happen.** Files can change between the two calls.
14. **Using metadata size as the sole data-limiting mechanism.** The source can change or data can be oversized; count and enforce limits during processing.

## 13. Self-Check Questions

**1.** Must a path on drive C: and a path on drive D: have different providers?

**Answer:** No. They can both use the default `file` provider while belonging to different `FileStore`s, and atomic moves between them may still be unsupported.

**2.** Can you call `Files.copy(pathOnDisk, pathInsideZip)`?

**Answer:** Yes, if the ZIP filesystem is open for writing, the target is valid, and the provider supports the required operation. High-level `Files.copy` allows paths from two different providers.

**3.** Why is `pathOnDisk.resolve(pathInsideZip)` not the way to construct a ZIP entry address?

**Answer:** The two paths belong to different namespaces. Default-filesystem resolution does not understand ZIP paths and can throw `ProviderMismatchException`. Use the ZIP filesystem to create the target path.

**4.** `Files.move(source, target, ATOMIC_MOVE)` fails across filesystems. Can you automatically drop `ATOMIC_MOVE`?

**Answer:** Only when business rules **accept non-atomicity** and appropriate verification/recovery logic has been designed. If atomicity is mandatory, you must report unsupported.

**5.** Does `Files.copy(sourceDirectory, targetDirectory)` copy the entire subtree?

**Answer:** No. To copy a directory tree, you must traverse and copy each entry yourself according to symbolic link and error policies.

**6.** When using `COPY_ATTRIBUTES`, is it guaranteed to preserve all POSIX permissions and ACLs inside a ZIP?

**Answer:** No. Supported and transferred attributes depend on the provider/`FileStore`; check and verify the attributes that truly matter.

**7.** Why must a ZIP `FileSystem` be closed?

**Answer:** To release resources and finalize necessary internal operations. Once a ZIP filesystem is closed, its `Path` entries are no longer usable for normal I/O.

**8.** Do the schemes `jar` and `file` imply two storage areas on two different physical devices?

**Answer:** No. The ZIP archive itself can sit on the exact same storage device as the source file; a different provider describes **how it is accessed and its namespace**, not necessarily hardware.

## 14. Java 17 Documentation

- [`Files.copy`, `Files.move`, and options](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`FileSystemProvider` and SPI/high-level API differences](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html)
- [`Path` — `resolve`, `relativize`, `toFile`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [`jdk.zipfs` — properties and options of the ZIP File System](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html)

**Key takeaway:** A `Path` is always tied to a filesystem/provider. `Files.copy` and `Files.move` can work **across providers** under the API contract, yet there is no guarantee that all attributes are preserved or that moves are atomic. Do not mix `Path` objects from two namespaces via `resolve`, do not assume `toFile()` works with ZIPs, and always handle errors, provider limits, metadata, and resource lifecycles explicitly.
