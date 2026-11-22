# Root Directories, `FileStore`, and Characteristics of `FileSystemProvider` in Java NIO.2

## 1. Goals and overall picture

When working with file systems, a program does not only need to know which file a `Path` points to. It may also need to know the roots provided by a `FileSystem`, the storage volume containing a path, usable disk space, support for POSIX/DOS attributes, and the provider that determines how NIO.2 operations behave.

After this lesson, you will be able to:

- Distinguish **root directory**, **`FileStore`**, and **`FileSystemProvider`**; avoid assuming each root corresponds strictly to one physical disk drive.
- Traverse roots and file stores, and select the right `FileStore` for an existing `Path`.
- Read capacity, read-only status, and support for file attribute views with proper error handling.
- Recognize OS/provider-dependent limitations and work with a ZIP file system using a different provider.

The related types in `java.nio.file` and `java.nio.file.spi` in Java NIO.2:

```text
FileSystemProvider (implementation of operations by scheme)
        │ creates/provides
        ▼
FileSystem (namespace, separator, roots, FileStores)
        │ creates/provides
        ├── Path (path inside the FileSystem)
        └── FileStore (storage metadata visible to the provider)
```

This is an API relationship diagram, **not** a physical partition diagram: one `FileSystem` can have multiple roots or multiple `FileStore` instances; these two concepts do not have a mandatory one-to-one relationship.

## 2. Root directory: the root of a path namespace

A **root directory** is the root component of an absolute path in a `FileSystem`. Use `FileSystem.getRootDirectories()` to obtain an `Iterable<Path>` representing the roots enumerated by the provider.

```java
FileSystem fs = FileSystems.getDefault();
for (Path root : fs.getRootDirectories()) {
    System.out.println(root);
}
```

On Unix environments there is usually the `/` root; on Windows you may see `C:\`, `D:\`, or other roots. These are only examples depending on the running machine. The order, count, representation, and access permissions are not fixed; do not hard-code the root list.

Distinguish:

| Concept | Meaning | Example |
| --- | --- | --- |
| `Path.getRoot()` | The root component of **one path**; may be `null` for a relative path | `/` in `/var/log/app.log` |
| `FileSystem.getRootDirectories()` | The roots **enumerated by the provider** for the file system | `/` or drive letters |
| Mount point | Location where a filesystem/volume is attached to the OS directory tree | `/mnt/data` may be a separate volume |
| `FileStore` | Represents a storage pool and its metadata according to the provider | volume, partition, mount, or logical storage unit |

Easy-to-miss point: on Linux, a separate volume mounted at `/mnt/data` does **not necessarily** appear as a second root in `getRootDirectories()`; applications still access the volume through `/mnt/data`. Conversely, a single root does not guarantee that the entire subtree underneath resides on the same `FileStore`, since mount points can appear deeper in the tree.

`Path.of(".")` is a relative path; `Path.of(".").toAbsolutePath().normalize()` yields a syntactically normalized absolute path. `normalize()` does not check file existence, resolve symbolic links, or prove that the path is accessible. When you need the real path on disk and existence verification, see `toRealPath()` and handle `IOException`.

## 3. `FileStore`: storage pool and metadata

`FileStore` provides information about where the provider stores files and the capabilities of that storage unit. Two commonly used access methods:

- `Files.getFileStore(existingPath)`: finds the storage pool for **a specific path**. Best suited when you need to determine the write target of a working file/directory. The path should exist and permissions must allow access; the call may throw `IOException`.
- `FileSystem.getFileStores()`: iterates over the `FileStore` instances that the file system/provider can enumerate. The result set and visibility depend on environment, permissions, and provider; the list is not a complete, immutable hardware map.

Key methods:

| API | What it returns | Interpretation and limits |
| --- | --- | --- |
| `name()`, `type()` | Name/type reported by the provider | May be empty strings or vary across OSes; do not use as permanent identifiers |
| `isReadOnly()` | Read-only state of the store | Does not replace checking access permissions for a specific path |
| `getTotalSpace()` | Total capacity (bytes) | Logical capacity reported by the provider, not necessarily physical device capacity |
| `getUnallocatedSpace()` | Number of unallocated bytes | May include space that the current account is not permitted to use |
| `getUsableSpace()` | Estimated bytes usable by the current JVM | May be restricted by quotas, policies, or the filesystem |
| `supportsFileAttributeView(String/Class)` | Store declares support for an attribute view | Check further for the specific path/operation if the application relies on that capability |
| `getAttribute(name)` | Extended metadata by name | Not guaranteed to have all attributes; may be unsupported |

All space measurements are in **bytes**, of type `long`, and represent an observation at the time of the call. Values can change immediately afterward; quotas, virtual filesystems, network storage, containers, and process privileges can affect results. In particular, `usableSpace` differs from `unallocatedSpace`: part of unallocated space may be reserved for the system or privileged users.

**Do not treat `getUsableSpace()` as a guarantee that a write operation will definitely succeed.** Free space can change; there are also quotas, inodes, permissions, network failures, mount states, and provider restrictions. Actual write operations must catch and handle errors.

## 4. Runnable example: roots, provider, and `FileStore` of the current directory

Save the code below as **`StorageOverview.java`**. The program uses Java 17+, and does not create, modify, or delete any files; it only observes metadata. Calls may fail if the system denies metadata access, so the example allows throwing `IOException` to show the cause to the runner.

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;

public class StorageOverview {
    public static void main(String[] args) throws IOException {
        FileSystem fs = FileSystems.getDefault();

        System.out.println("Provider scheme: " + fs.provider().getScheme());
        System.out.println("Separator: " + fs.getSeparator());
        System.out.println("Supported views: " + fs.supportedFileAttributeViews());

        for (Path root : fs.getRootDirectories()) {
            System.out.println("Root: " + root);
        }

        Path current = Path.of(".").toAbsolutePath().normalize();
        FileStore store = Files.getFileStore(current);

        System.out.println("Current: " + current);
        System.out.println("Store: " + store.name() + " / " + store.type());
        System.out.println("Read only: " + store.isReadOnly());
        System.out.println("Basic view: "
                + store.supportsFileAttributeView("basic"));
        System.out.println("Total bytes: " + store.getTotalSpace());
        System.out.println("Unallocated bytes: " + store.getUnallocatedSpace());
        System.out.println("Usable bytes: " + store.getUsableSpace());
    }
}
```

Compile/run in the directory containing the file:

```bash
javac StorageOverview.java
java StorageOverview
```

The output has the structure `Provider scheme: ...`, `Root: ...`, `Store: ...`, and the space numbers. **There is no fixed stdout** for this example: the path, filesystem type, provider, number of roots, and actual capacities are all determined by the running machine. A typical JVM uses the default provider with scheme `file`, but the code does not need to assume volume names, presence or absence of the `posix` view, or specific capacities.

Why call `Files.getFileStore(current)` after selecting `current`? Because the `/` root can contain multiple child mount points; obtaining the store of the actual target directory is more reliable than guessing from the first root.

In production, keep `IOException` with context (which path, which metadata read), and do not let one temporarily disconnected volume break an entire status screen if other volumes remain readable.

## 5. Safely enumerating `FileStore` instances

To build a diagnostic page, you can iterate over `fs.getFileStores()`. Each store can independently fail when querying space, so scope error handling per store:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.FileSystems;

public class ListStores {
    public static void main(String[] args) {
        for (FileStore store : FileSystems.getDefault().getFileStores()) {
            try {
                System.out.printf(
                        "name=%s, type=%s, readOnly=%s, usable=%d bytes%n",
                        store.name(),
                        store.type(),
                        store.isReadOnly(),
                        store.getUsableSpace()
                );
            } catch (IOException | SecurityException ex) {
                System.err.println("Cannot inspect store " + store.name()
                        + ": " + ex.getMessage());
            }
        }
    }
}
```

Save as **`ListStores.java`**, then:

```bash
javac ListStores.java
java ListStores
```

The summary lines and their order depend entirely on the environment; with some providers, the list may be empty or certain stores may be inaccessible. Do not infer that the line count equals the number of physical disks. Nor should you cache a `FileStore` for a long time and assume its metadata remains static when filesystems can be unmounted/mounted or quotas changed.

## 6. Provider: who actually implements file operations?

`FileSystemProvider` is NIO.2's SPI, defining how to access a type of filesystem. Each provider is associated with a URI **scheme**, for example:

- `file`: the OS default provider, typically serving local machine paths.
- `jar`: the ZIP filesystem provider (`jdk.zipfs` in standard JDKs), allowing the contents of a ZIP/JAR file to be viewed as a `Path` tree.
- Third-party providers can represent network filesystems, in-memory files, or custom storage; consult the provider's documentation because capabilities are not uniform.

Practical relationships:

1. `FileSystems.getDefault()` returns the default filesystem; `fs.provider()` returns its provider.
2. A `Path` is always bound to a `FileSystem`: `path.getFileSystem()`. Two `Path` objects from two providers may have different syntax and cannot always be used together.
3. `Files.readString`, `Files.copy`, `Files.getFileStore`, etc. operate through the provider corresponding to the path. When combining paths from different providers, the API may perform cross-provider byte transfer in some operations, while other operations reject it or have distinct semantics. Do not assume equivalent move, permission, or atomicity behavior across all providers.
4. `FileSystem` determines `getSeparator()`, `getRootDirectories()`, `getFileStores()`, and `supportedFileAttributeViews()`. The same application can use multiple filesystems/providers.

**A URI scheme is not a physical filesystem name.** `file` or `jar` refers to the provider mechanism handling paths; `FileStore.type()` may return a filesystem type like NTFS, ext4, or another name, and has no fixed portable format.

You can list available providers with `FileSystemProvider.installedProviders()`; the result depends on the JDK and classpath/module-path. Do not assume every Java runtime includes the ZIP provider, especially custom runtime images that omit `jdk.zipfs`.

## 7. Runnable example: the `jar` provider with a ZIP filesystem

The following example creates a temporary ZIP in the OS temporary directory, writes a text file into the ZIP via a `Path` of the ZIP filesystem, reads it back, closes the filesystem, and deletes the ZIP. Run on **JDK 17+ with the `jdk.zipfs` module**.

Save as **`ZipProviderDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipProviderDemo {
    public static void main(String[] args) throws IOException {
        Path archive = Files.createTempFile("nio-provider-", ".zip");
        try {
            // The new file created by createTempFile is empty:
            // delete the placeholder so ZipFileSystem creates a valid archive.
            Files.delete(archive);
            URI zipUri = URI.create("jar:" + archive.toUri());

            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {
                Path entry = zipFs.getPath("/docs/message.txt");
                Files.createDirectories(entry.getParent());
                Files.writeString(entry, "Xin chào ZIP",
                        StandardCharsets.UTF_8);

                System.out.println(Files.readString(
                        entry, StandardCharsets.UTF_8));
                System.out.println(zipFs.provider().getScheme());
            }
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
```

```bash
javac ZipProviderDemo.java
java ZipProviderDemo
```

Stdout on a successful run:

```text
Xin chào ZIP
jar
```

Explanation:

- `archive` is a `Path` of the default filesystem, whereas `entry` is a `Path` **inside the ZIP filesystem**. Both are `Path` objects, but they have different `getFileSystem()` values.
- A URI of the form `jar:file:...` selects the `jar` provider. The environment `Map.of("create", "true")` requests creating the ZIP if it does not yet exist.
- `zipFs.getPath("/docs/message.txt")` represents a path inside the archive; the `/` character here is the ZIP filesystem separator, even when the host runs Windows.
- `try-with-resources` closes the ZIP filesystem, completes writing, and releases resources. The `entry` path can no longer be used normally after its filesystem closes (`ClosedFileSystemException` may occur).
- `finally` deletes the temporary ZIP file; avoid relying on the ZIP file remaining after the example finishes.

In a runtime missing `jdk.zipfs`, opening the `jar` scheme may throw `ProviderNotFoundException`. On a machine forbidding temporary file creation/deletion, the program may throw `IOException`. The example does not claim that the ZIP provider has the same capacity, file attribute views, or atomic write capabilities as the default filesystem.

## 8. Attribute support: checking at the right layer

NIO.2 provides **file attribute views** such as `basic`, `dos`, `posix`, `acl`, `owner`, and `user`. Support depends on the provider, filesystem, `FileStore`, operating system, and possibly the path itself.

Three different questions:

| Question | Check API | Notes |
| --- | --- | --- |
| Which view names does this filesystem report supporting? | `fs.supportedFileAttributeViews()` | List at the `FileSystem` level; does not assert every path can use them |
| Does this specific store report supporting this view? | `store.supportsFileAttributeView("posix")` | Should use the exact `FileStore` of the target path |
| Can a specific path retrieve/modify the attributes? | `Files.getFileAttributeView(path, PosixFileAttributeView.class)` and the corresponding read/write call | May return `null` or throw an error; permissions also depend on the running user |

Short example, assuming `path` is a valid existing `Path`:

```java
FileSystem fs = path.getFileSystem();
FileStore store = Files.getFileStore(path);

if (fs.supportedFileAttributeViews().contains("posix")
        && store.supportsFileAttributeView("posix")) {
    // This only checks capability, not a guarantee of read/write permission.
    var view = Files.getFileAttributeView(
            path, java.nio.file.attribute.PosixFileAttributeView.class);
    if (view != null) {
        var attrs = view.readAttributes(); // can still throw IOException
        System.out.println(attrs.permissions());
    }
}
```

This snippet is **illustrative**, not a standalone program: you must declare `path`, import the APIs used, and handle `IOException` in the enclosing method. Do not force all `Path` objects to have POSIX permissions on Windows or on the ZIP provider. For portable requirements, use `BasicFileAttributes` / `Files.readAttributes(path, BasicFileAttributes.class)` for basic information, and only use advanced views after confirming support.

`FileStore.getAttribute(String)` is also provider-specific. If you query an unrecognized attribute, you may receive `UnsupportedOperationException`; retrieval can also fail with `IOException`. Read the provider documentation before relying on attribute names outside the common API.

## 9. Choosing an API by real-world scenario

**Scenario A — displaying roots for the user to pick a directory.** Use `FileSystems.getDefault().getRootDirectories()` to suggest starting points. Do not assume it lists every mount point; allow users to choose or enter a valid `Path` elsewhere.

**Scenario B — estimating free space to export a report.** Pick **the actual directory that will hold the output**, create the target directory if business rules allow, and then call `Files.getFileStore(destinationDirectory)` and `getUsableSpace()`. Do not check a drive by the first character of the path or pick `/` arbitrarily. Use the result only for warnings or sorting choices; when writing, still handle errors and clean up partial data.

**Scenario C — running on Linux, Windows, and ZIP filesystems.** Obtain `Path`, `FileSystem`, and provider directly from the object in use; check `supportedFileAttributeViews()` / `supportsFileAttributeView()` before using POSIX/DOS. Do not build child paths by concatenating the host separator if the path belongs to a ZIP/other provider: use `path.resolve("child")`.

**Scenario D — processing a directory on a network volume or removable media.** A store may disappear or stop responding between two calls. Wrap `Files.getFileStore`, space queries, directory listing, and file operations in appropriate `IOException` handling; do not treat earlier diagnostic results as an immutable snapshot.

## 10. Common mistakes and limitations to remember

1. **Counting roots as counting partitions/volumes.** Roots describe namespaces; volumes may be mounted deep in the tree.
2. **Using the root's store to measure a child path.** A subdirectory may reside on a different mount point. Obtain the store from the exact target path.
3. **Treating `usableSpace` as a guaranteed writable quota.** It is an instantaneous estimate and does not replace error handling during writes.
4. **Treating `isReadOnly() == false` as permission to write a file.** Access permissions also depend on ACLs, file permissions, quotas, paths, and runtime state. `Files.isWritable(path)` likewise does not replace handling errors from actual write operations.
5. **Hard-coding `/`, `C:\`, or store names/types.** Use `Path`/`resolve`; display `name()/type()` only as diagnostic data.
6. **Assuming every provider has POSIX, DOS, ACL, or reliable file space metrics.** Check supported capabilities and accept `UnsupportedOperationException` / `IOException` per the API contract.
7. **Continuing to use a `Path` of a closed ZIP.** A `Path`'s lifecycle is bound to its `FileSystem`; close resources with `try-with-resources`, and use them only while still open.
8. **Equating the provider with the storage device.** Schemes like `jar` or `file` identify how access is implemented; filesystem type and store are information at a different layer.

## 11. Self-check questions

- Why might `getRootDirectories()` on Linux show only `/`, while `Files.getFileStore(Path.of("/mnt/data"))` returns metadata for a separate volume?
- If you need to check free space before writing to `/mnt/data/reports`, which path's `FileStore` should you obtain? What condition must hold for that path?
- Distinguish `getUnallocatedSpace()` and `getUsableSpace()`. Why does a check result not guarantee that a subsequent `Files.writeString()` call will succeed?
- Why should a `Path` created by `zipFs.getPath(...)` not be handled like an OS `Path.of(...)`, even though both implement the `Path` API?
- Is `fs.supportedFileAttributeViews().contains("posix")` enough to guarantee you can change permissions on every file in the system? Why or why not?

## 12. Summary

Think of a **root directory** as the root of a path namespace, **`FileStore`** as the metadata source for where data is stored, and **`FileSystemProvider`** as the component implementing file operations. When you need capacity or attribute views, start from the **target `Path`**, determine its `FileSystem` and `FileStore`, read its advertised capabilities, and handle exceptions on the actual operation. This approach is far more resilient to Unix/Windows differences, mount points, network storage, and providers such as ZIP.
