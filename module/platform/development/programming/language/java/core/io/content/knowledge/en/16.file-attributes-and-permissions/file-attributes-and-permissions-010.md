# `FileStore`, Capacity, and `supportedFileAttributeViews` in Java

When operating on files with Java NIO.2, a program sometimes needs to know **which storage store a file resides on**, **how much usable capacity remains**, or **whether the filesystem supports POSIX permissions, DOS attributes, ACLs, and other metadata types**. These are questions at the **filesystem and attribute** layer, distinct from reading the byte contents of a file.

Java 17 provides these main entry points:

- `Files.getFileStore(Path)`: locates the `FileStore` associated with a path's location.
- `FileStore.getTotalSpace()`, `getUnallocatedSpace()`, `getUsableSpace()`: capacity info measured in **bytes**.
- `FileStore.supportsFileAttributeView(...)`: queries whether a store supports a specific attribute view type.
- `FileSystem.supportedFileAttributeViews()`: retrieves the set of attribute view names reported as supported by the **filesystem**.
- `Files.readAttributes(...)`, `Files.getFileAttributeView(...)`: reads or accesses a view for **a specific path**.

Key point: **reported "usable" space is only a point-in-time snapshot, not a guarantee that the next write will succeed**; and **`FileSystem`'s `supportedFileAttributeViews` is not completely identical to checking support on an individual `FileStore`**. This lesson clearly explains these three layers through Java 17+ examples, selection tables, and notes on permissions, quotas, portability, and race conditions.

## 1. Distinguishing `Path`, `FileSystem`, `FileStore`, and Attribute Views

### `Path` — Location of an Entry

`Path` is a path to a file/directory or a non-existent location:

```java
Path path = Path.of("data", "report.txt");
```

This is **illustrative code**, requiring `import java.nio.file.Path`. Creating a `Path` does not open, create, or read a file. A `Path` is bound to a specific `FileSystem` and is interpreted per that filesystem's provider rules.

### `FileSystem` — Provider-Supplied Filesystem Model

`java.nio.file.FileSystem` represents a filesystem with roots, separators, path matchers, potentially supported attribute views, and a collection of file stores exposed by the provider.

To obtain the filesystem of a path:

```java
FileSystem fs = path.getFileSystem();
```

This is **illustrative code**, requiring `path` and importing `FileSystem`. To obtain the default filesystem:

```java
FileSystem defaultFs = FileSystems.getDefault();
```

Requires importing `java.nio.file.FileSystems`. An application may also work with non-default providers, such as a ZIP filesystem once the corresponding provider is opened.

### `FileStore` — Storage Location, with Capacity and Metadata Info

`java.nio.file.FileStore` describes a **storage store** exposed by the filesystem/provider. On real systems, it typically corresponds to a volume, mount, partition, network share, or logical storage object, yet **does not necessarily map 1-to-1 to a physical hard drive**.

```java
FileStore store = Files.getFileStore(path);
```

This is **illustrative code**, requiring imports for `FileStore`, `Files`, a `path` variable, and `IOException` handling. `Files.getFileStore` can access the filesystem, differing from simply calling `path.getFileSystem()`.

### Attribute Views — Structured Metadata Groups

`FileAttributeView` is an interface used to access a **metadata group** of a file. Common views:

| View | Purpose | Related APIs |
|---|---|---|
| `basic` | File type, size, creation/modification/access times, file key if available | `BasicFileAttributeView`, `BasicFileAttributes` |
| `posix` | POSIX-style permissions, owner, group | `PosixFileAttributeView`, `PosixFileAttributes` |
| `dos` | Hidden, read-only, system, archive | `DosFileAttributeView`, `DosFileAttributes` |
| `acl` | Provider-specific access-control list | `AclFileAttributeView` |
| `owner` | File owner | `FileOwnerAttributeView` |
| `user` | Application-defined extended attributes, when supported | `UserDefinedFileAttributeView` |

There is no guarantee **every filesystem supports every view**. POSIX is commonly found on Unix-like systems; DOS/ACL/user-defined views may appear on other providers, yet you must **check at runtime** rather than inferring with certainty from the operating system name alone.

## 2. Obtaining the `FileStore` of a Path

Use `Files.getFileStore(path)` when you care where data will be read/written:

```java
Path dir = Path.of("data").toAbsolutePath();
FileStore store = Files.getFileStore(dir);
```

This is **illustrative code** requiring imports for `Path`, `Files`, `FileStore`, and `data` must be a location where the provider can determine the store per contract. If the path does not exist or cannot be looked up in the provider, the operation can throw `IOException`; do not assume every imaginary path can report capacity.

Some methods of `FileStore`:

- `name()`: name reported by the provider, **may be an empty string**.
- `type()`: store/filesystem type reported by the provider, e.g., a filesystem format name; not a single standardized classification code across providers.
- `isReadOnly()`: whether the provider considers the store read-only; **not sufficient proof** you have permission to write to a specific file.
- `getTotalSpace()`: total capacity of the store.
- `getUnallocatedSpace()`: unallocated space on the store.
- `getUsableSpace()`: capacity **usable by this Java VM** as assessed by the provider.
- `supportsFileAttributeView(...)`: checks attribute view support on the store.
- `getAttribute(String)`: **store-specific** attribute by a provider-supported name; not a universal standard API across all attribute types.

### Do Not Treat `name()` as a Unique ID

A program might run inside a container, virtual environment, network mount, or provider with an empty store name. Do not use `store.name()` as a unique key to identify files or decide whether two paths share the same physical device.

In the test example below on an NTFS filesystem, `name()` returned **an empty string**. Therefore, real programs must accept cases where the display name carries no useful information.

## 3. Three Capacity Quantities: Total, Unallocated, Usable

| Method | Unit | Practical Meaning |
|---|---|---|
| `getTotalSpace()` | Bytes | Total capacity reported by the store |
| `getUnallocatedSpace()` | Bytes | Unallocated space in the store |
| `getUsableSpace()` | Bytes | Store capacity expected to be usable by **the current Java VM/caller** |

The most important difference is between **unallocated** and **usable**:

- A filesystem may have plenty of physical free space while a user/process is limited by quotas or space reserved for the system.
- In that case, **usable** space can be lower than **unallocated** space.
- On some systems, these two numbers are equal; that is only the provider's state at call time, not a universal rule.
- These figures are measured on **the store**, not the size of a single file.
- The numbers **can change immediately after reading** as other processes write/delete data, quotas shift, filesystems remount, or due to provider characteristics.

Do not use `getUnallocatedSpace()` in place of `getUsableSpace()` to conclude the application **is allowed to use** all free space. Conversely, `getUsableSpace()` also **does not guarantee** a new file can be created successfully: there are also ACLs, permissions, inode/entry limits, invalid paths, unreflected quotas, network limits, and many other causes.

### Bytes, KiB, MiB, GiB vs. kB, MB, GB

Capacity APIs return **bytes** as `long`. To display in binary units:

- `1 KiB = 1,024 bytes`.
- `1 MiB = 1,024 KiB = 1,048,576 bytes`.
- `1 GiB = 1,024 MiB = 1,073,741,824 bytes`.

Decimal units used on some storage manufacturer labels:

- `1 kB = 1,000 bytes`.
- `1 MB = 1,000,000 bytes`.
- `1 GB = 1,000,000,000 bytes`.

The two conventions should not be mislabeled as each other. For example, dividing `bytes / (1024.0 * 1024.0 * 1024.0)` produces **GiB**, not decimal GB.

### Do Not Truncate Capacity Data to `int`

`long` is the appropriate choice for large byte counts. A store holding hundreds of GiB easily exceeds the 32-bit `int` limit. Also watch for overflow when computing `requiredBytes + overhead`: for untrusted inputs, check before adding or use appropriate limit comparisons.

## 4. Example 1 — Querying Capacity of a Real Directory

Create the file `FileStoreCapacityDemo.java` (Java 17+):

```java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class FileStoreCapacityDemo {
    static double toGiB(long bytes) {
        return bytes / (1024.0 * 1024.0 * 1024.0);
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("store-capacity-");
        try {
            FileStore store = Files.getFileStore(dir);
            long total = store.getTotalSpace();
            long unallocated = store.getUnallocatedSpace();
            long usable = store.getUsableSpace();
            System.out.println("store name=" + store.name());
            System.out.println("store type=" + store.type());
            System.out.println("total bytes=" + total);
            System.out.println("unallocated bytes=" + unallocated);
            System.out.println("usable bytes=" + usable);
            System.out.println("nonnegative byte counts="
                    + (total >= 0 && unallocated >= 0 && usable >= 0));
            System.out.printf(Locale.ROOT, "one GiB formatted=%.2f%n",
                    toGiB(1L << 30));
        } finally {
            Files.deleteIfExists(dir);
        }
    }
}
```

Compile, run:

```bash
javac -encoding UTF-8 --release 17 FileStoreCapacityDemo.java
java FileStoreCapacityDemo
```

Result **observed in one Java 17 run on NTFS**:

```text
store name=
store type=NTFS
total bytes=499024654336
unallocated bytes=203543601152
usable bytes=203543601152
nonnegative byte counts=true
one GiB formatted=1.00
```

**Do not treat the numbers above as fixed stdout on every machine.** `name()`, `type()`, `total`, `unallocated`, and `usable` are live data from the filesystem where the example runs; they will differ across machines, drives, quotas, or even a subsequent run. This is why code reads actual values instead of hardcoding example capacities.

**Mechanics:**

1. `Files.createTempDirectory` creates an isolated directory in the default temp location, avoiding dependence on user files.
2. `Files.getFileStore(dir)` retrieves the store corresponding to the newly created directory path.
3. The three capacity methods return `long` and are all in **bytes**.
4. `toGiB` illustrates unit conversion without integer division, avoiding truncation from `long / long`.
5. The `finally` block cleans up the temporary directory after querying. If the filesystem forbids the operation, the relevant call can throw `IOException` and must be handled in real applications.

Do not write tests asserting exact capacity numbers on the test machine. More reliable tests verify data types, error handling, and conversion formulas with **fixed mock numbers**, while integration tests only check properties under environment-appropriate assumptions.

## 5. Distinguishing `FileSystem.supportedFileAttributeViews()` and `FileStore.supportsFileAttributeView(...)`

Two APIs have similar names yet **different scopes**.

### 5.1 View Set at the `FileSystem` Layer

`FileSystem.supportedFileAttributeViews()` returns a `Set<String>` of view names that the filesystem/provider reports supporting:

```java
Set<String> views =
        FileSystems.getDefault().supportedFileAttributeViews();
```

This is an **illustrative snippet**, requiring imports for `java.nio.file.FileSystems` and `java.util.Set`.

Names can be `"basic"`, `"posix"`, `"dos"`, `"acl"`, `"owner"`, or `"user"`, depending on the provider. **Do not assume the list is always identical** across Windows, Linux, containers, network filesystems, and custom providers.

`supportedFileAttributeViews()` has **provider/filesystem-level** scope. If a provider manages multiple file stores, a view included in the set might **not be supported on every store or every path**. It also does not mean you have **read/write permission** for all metadata on a specific file.

### 5.2 Checking Views on a `FileStore`

`FileStore` has two important overloads:

```java
boolean byName = store.supportsFileAttributeView("posix");
boolean byClass =
        store.supportsFileAttributeView(PosixFileAttributeView.class);
```

This is an **illustrative snippet**, requiring `store` to be a `FileStore` and importing `PosixFileAttributeView`.

- The `String` form takes the provider-defined **view name**; for standard views, use `"basic"`, `"posix"`, `"dos"`, etc.
- The `Class<? extends FileAttributeView>` form takes the view interface class.
- A store supporting `basic` does not imply supporting `posix` or `acl`.
- If the view is unsupported, the result is typically `false` per contract; also handle argument/provider errors per specific documentation.

**Do not confuse `supportedFileAttributeViews()` (plural, on `FileSystem`) with `supportsFileAttributeView(...)` (querying an individual `FileStore`).** `FileStore` does not have a matching method returning a `Set<String>` by that name like `FileSystem`.

### 5.3 Checking Views at a `Path` and Reading Attributes

To access a specific file's view:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
        path, BasicFileAttributeView.class);
```

This is an **illustrative snippet**, requiring imports for `Files` and `BasicFileAttributeView`. The value can be `null` if the view is unsupported. Even when a view is returned, calls like `view.readAttributes()` can throw `IOException` due to access permissions, a disappearing file, or filesystem errors.

Reading a group of attributes:

```java
BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class);
long fileSizeBytes = attrs.size();
boolean isDirectory = attrs.isDirectory();
```

This is **illustrative code**, requiring imports for `BasicFileAttributes`, `Files`, and `IOException` handling. `attrs.size()` is **the size of the file/entry**, not the total capacity of the `FileStore`. Distinguish:

```text
FileStore.getTotalSpace()      -> total capacity of the store (bytes)
FileStore.getUsableSpace()     -> estimated space usable by the JVM (bytes)
BasicFileAttributes.size()     -> size of a single entry/path (bytes)
```

## 6. Example 2 — Three Levels of Checking Attribute Views

Create the file `FileStoreViewsDemo.java`:

```java
import java.nio.file.FileStore;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;
import java.util.Set;

public class FileStoreViewsDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("store-views-");
        try {
            Set<String> providerViews =
                    FileSystems.getDefault().supportedFileAttributeViews();
            FileStore store = Files.getFileStore(dir);
            System.out.println("provider basic="
                    + providerViews.contains("basic"));
            System.out.println("store basic by name="
                    + store.supportsFileAttributeView("basic"));
            System.out.println("store basic by class="
                    + store.supportsFileAttributeView(BasicFileAttributeView.class));
            BasicFileAttributes attrs =
                    Files.readAttributes(dir, BasicFileAttributes.class);
            System.out.println("directory via basic=" + attrs.isDirectory());
            System.out.println("provider posix="
                    + providerViews.contains("posix"));
            System.out.println("store posix="
                    + store.supportsFileAttributeView(PosixFileAttributeView.class));
            System.out.println("store dos="
                    + store.supportsFileAttributeView(DosFileAttributeView.class));
        } finally {
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileStoreViewsDemo.java
java FileStoreViewsDemo
```

Output **verified in a Java 17 environment using NTFS**:

```text
provider basic=true
store basic by name=true
store basic by class=true
directory via basic=true
provider posix=false
store posix=false
store dos=true
```

**The `posix`/`dos` lines may differ on Linux, macOS, network stores, or other providers.** This is an environment-specific result, **not a universal expectation**. Even across two file stores on the same operating system, the supported view set can differ.

**Meaning of each check group:**

1. `providerViews.contains("basic")` asks whether the default filesystem layer advertises the `basic` view.
2. Both `store.supportsFileAttributeView(...)` forms ask whether **the store where the temporary directory resides** supports `basic`.
3. `Files.readAttributes(dir, BasicFileAttributes.class)` actually accesses metadata of **the path** and sees that it is a directory.
4. `PosixFileAttributeView` and `DosFileAttributeView` are queried separately because support is a provider/store property, not an option the application turns on.
5. All queries run against the current environment. To avoid hardcoding programs to Windows/Linux, **branch behavior based on runtime capabilities**.

**Note:** the code only *queries* support; it does not alter permissions, hidden flags, or ACLs. If the core feature requires writing POSIX permissions, checking support is only the first step; you still must handle access privileges and actual errors when calling `Files.setPosixFilePermissions` or view methods.

## 7. `basic`, `posix`, `dos`, `acl`, and `user`: Choosing the Right View for the Problem

### `basic` View

`BasicFileAttributes` reports:

- `size()`: file/entry size, in bytes.
- `lastModifiedTime()`, `lastAccessTime()`, `creationTime()`: timestamps when supported appropriately by the provider.
- `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `isOther()`: entry type.
- `fileKey()`: identifier key returned by the provider, **may be `null`**.

This is the foundational metadata group, usually easiest to use when only inspecting file type or size. There is no need to call `Files.getFileStore` just to read `BasicFileAttributes` of a path.

### `posix` View

`PosixFileAttributeView` and `PosixFileAttributes` provide the POSIX-style permissions, owner/group model. On supporting providers, you can use:

```java
Set<PosixFilePermission> perms = Files.getPosixFilePermissions(path);
```

This is **illustrative code**; it requires importing `Set`, `PosixFilePermission`, and `Files`; the method can throw `IOException` or `UnsupportedOperationException` if unsupported by the filesystem.

**Do not write programs that unconditionally call `Files.setPosixFilePermissions` without checking**, as that API can fail on environments supporting only DOS/ACL. In addition, POSIX permission bits do not fully capture every complex security model.

### `dos` View

`DosFileAttributeView` supports attributes such as **read-only**, **hidden**, **system**, and **archive** per provider. They **differ** from `FileStore.isReadOnly()`:

- `FileStore.isReadOnly()` describes writability of **the store** as a whole.
- `DosFileAttributes.isReadOnly()` describes an attribute of **a single file/entry**.
- A store reporting writable does not mean every file is writable, because ACLs/permissions/locks still apply.

### `acl` and `owner` Views

`AclFileAttributeView` is for access-control lists and `FileOwnerAttributeView` is for owner when supported by the provider. ACL permission models can be more complex than the 9-bit POSIX model. Avoid translating ACLs into `rwx` strings yourself and claiming the security policy was preserved.

### `user` View

`UserDefinedFileAttributeView` allows accessing application-set **extended attributes**, depending on the filesystem and provider. Do not treat it as a durable, unlimited-size key-value store available in every environment. If metadata is an essential part of the application, prepare fallback/data-migration options and suitable tests.

## 8. Using Supported Capabilities to Choose Execution Paths

A portable workflow for a feature **requiring POSIX permissions** can look like:

```java
FileStore store = Files.getFileStore(path);
if (!store.supportsFileAttributeView(PosixFileAttributeView.class)) {
    throw new UnsupportedOperationException(
            "POSIX file permissions are not available here");
}
Set<PosixFilePermission> permissions =
        Files.getPosixFilePermissions(path);
```

This is an **illustrative snippet** requiring imports for `FileStore`, `Files`, `PosixFileAttributeView`, `PosixFilePermission`, `Set`, a `path` variable, and `IOException` handling. If the view is absent, the error is surfaced clearly rather than secretly trying POSIX and ignoring failures.

However, **a support check is not access permission**: right after returning `true`, the file can still be deleted, have permissions changed, or the next operation can be denied. **Do not treat a support-check result as a guarantee the operation will succeed**.

If POSIX is only an optional feature, the application can choose an appropriate alternative policy. For example, a backup tool might record which metadata was present/absent rather than silently discarding permissions when the goal requires preserving security metadata.

## 9. When Should You List `FileStore`s of a Filesystem?

Besides `Files.getFileStore(path)`, Java allows listing **the `FileStore`s exposed by a `FileSystem`**:

```java
for (FileStore store : FileSystems.getDefault().getFileStores()) {
    System.out.println(store.name() + " / " + store.type());
}
```

This is **illustrative code** requiring imports for `FileStore` and `FileSystems`. The number of stores listed, order, names, and accessible stores all depend on the provider/environment.

**Choose the right API for the question:**

- "Which store will an output file in directory `/data/export` be written to?" → `Files.getFileStore(exportDirectory)`.
- "Which stores does the default provider expose for listing?" → `FileSystems.getDefault().getFileStores()`.
- "Which attribute views does the provider/filesystem support?" → `fileSystem.supportedFileAttributeViews()`.
- "Does the store holding this path support POSIX?" → `store.supportsFileAttributeView("posix")`.
- "What hidden/permissions attributes does a specific file have?" → `Files.readAttributes` or `Files.getFileAttributeView` with the appropriate view.

Do not iterate `getFileStores()` and guess by picking a store whose name resembles the path. `Files.getFileStore(path)` is the right query when you already have a target path.

## 10. Checking Capacity Before Writing: Useful Yet Not a Guarantee

An application needing to create a file expected to be 4 GiB may want to warn if the store has too few usable bytes left:

```java
FileStore store = Files.getFileStore(destinationDirectory);
long usableBytes = store.getUsableSpace();
if (usableBytes < expectedBytes) {
    throw new IOException("Insufficient estimated usable space");
}
```

This is **illustrative code** requiring `destinationDirectory`, `expectedBytes`, and handling/declaring `IOException`. `expectedBytes` must be **the expected byte count of data actually written**, not the `String.length()` character count when UTF-8 encoded.

Yet this check is only a **preflight advisory**:

1. Between reading `usableBytes` and writing, another process may consume the space (**TOCTOU**).
2. Space for the current JVM does not fully reflect per-file/user/container quotas or every system limit across all providers.
3. Writing a file may require metadata, directory entries, block allocation, or journal overhead.
4. The file may land on a different mount path after moves or due to symlink/mount changes.
5. Access rights, permissions/ACLs, file locks, and parent paths can still cause the operation to fail even when usable space is huge.
6. Compression/sparse writes can make physical space differ from logical size; payload-based estimates are not always exact.

**Therefore:** use `getUsableSpace` for preliminary warnings/planning, yet still **catch and handle `IOException` during writing**, verify size/checksum when necessary, and have a rollback/cleanup strategy for incomplete files.

### Pay Attention to Encoding When Calculating Bytes

`"Xin chào 😊".length()` is the number of UTF-16 code units in the Java string, whereas UTF-8 encoded data can be longer:

```java
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
long expectedBytes = encoded.length;
```

This is **illustrative code** requiring `String text` and importing `StandardCharsets`. For large streams, do not allocate a `byte[]` holding the entire payload just to find its length; calculate/estimate bytes from the format or count during serialization when architecture permits.

## 11. Example 3 — Checking Estimates with Safe Comparison

Create the file `SpacePreflightDemo.java`:

```java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public class SpacePreflightDemo {
    static boolean enoughForEstimate(long estimatedBytes, long usableBytes) {
        if (estimatedBytes < 0 || usableBytes < 0) {
            throw new IllegalArgumentException("Negative size");
        }
        return usableBytes >= estimatedBytes;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("zero estimate="
                + enoughForEstimate(0, 0));
        System.out.println("estimate fits="
                + enoughForEstimate(1024, 4096));
        System.out.println("estimate exceeds="
                + enoughForEstimate(4097, 4096));

        Path temp = Files.createTempDirectory("preflight-space-");
        try {
            FileStore store = Files.getFileStore(temp);
            long usable = store.getUsableSpace();
            System.out.println("usable nonnegative=" + (usable >= 0));
            System.out.println("zero bytes within measured usable="
                    + enoughForEstimate(0, usable));
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 SpacePreflightDemo.java
java SpacePreflightDemo
```

Verified output in an environment where space queries succeed:

```text
zero estimate=true
estimate fits=true
estimate exceeds=false
usable nonnegative=true
zero bytes within measured usable=true
```

Concrete numeric tests demonstrate the meaning of `enoughForEstimate`:

- If 1,024 bytes are estimated and 4,096 bytes are usable, the comparison yields `true`.
- If 4,097 bytes are estimated and 4,096 bytes are usable, the result is `false`.
- If an input is negative, the method throws `IllegalArgumentException` to avoid silently accepting a nonsensical size.
- The example directly measures `store.getUsableSpace()` on a temporary directory created by the program, instead of using a fake configured number as actual space.

**Important:** A `true` value means *the estimate does not exceed the usable bytes read at check time*, **not** "writing will definitely succeed". In the example, checking **0 bytes** is almost always available, yet creating a new file itself can still fail due to permissions, entry/inode quotas, a read-only filesystem, or other I/O errors.

If business logic demands high reliability, combine:
- identifying the store of **the actual target directory**, not an accidental different drive;
- estimating bytes and reasonable overhead;
- writing a temporary file while tracking bytes written;
- catching write errors and cleaning up the temp file on failure;
- publishing/committing only after writing and validation finish completely.

## 12. `FileStore.isReadOnly()` Differs from a File's Permissions

`store.isReadOnly()` returns the read-only state of **the file store** per the provider. This is a useful signal when considering a write operation, yet does not replace path permissions/ACLs.

A few scenarios:

- Store reports `isReadOnly() == true`: write operations on it are usually disallowed; still check provider-specific semantics and errors.
- Store reports `false`: you **might still lack write permission** in a directory due to ACL/POSIX permissions, owner, quotas, or other policies.
- A file having the DOS read-only flag does not mean the entire store is read-only.
- A file currently used/locked by another application can cause writes to fail even if the store and permissions theoretically allow it.

A `Files.isWritable(path)` check is also point-in-time information and **does not guarantee the next write will succeed**. Especially for a file not yet created, knowing whether a file can be created in a directory cannot rely solely on the file not existing yet.

## 13. Is `FileStore`'s `getAttribute(String)` a Standard API for All Stores?

`FileStore.getAttribute(String attribute)` allows fetching a provider-defined attribute at the **store** layer. Attribute names and return values **do not have a single mandatory universal set** across all filesystems.

Do not write:

```java
Object x = store.getAttribute("someProviderKey");
```

assuming every JVM/provider must support that key. This is **illustrative code**, where the key name is purely symbolic; applications must consult specific provider documentation and handle `UnsupportedOperationException`/`IOException` when unsupported.

Distinguish:

- `FileStore.getAttribute(...)`: **store-specific** attribute.
- `Files.getAttribute(path, "basic:size")`: **file/path-specific** attribute per `Files`' `view:name` syntax.
- `Files.readAttributes(path, BasicFileAttributes.class)`: strongly typed read of a file metadata group.
- `FileStore.getUsableSpace()`: standard API for querying usable bytes; no need to guess provider attribute names.

If the goal is capacity, prefer the three standard capacity methods rather than non-portable `getAttribute`.

## 14. Do Not Assume All Files Belong to the Same Store

In an application with multiple mounts, container volumes, network shares, or virtual filesystems:

- Two paths can share the same `FileSystem` provider yet reside on **different `FileStore`s**.
- A path inside a directory tree can cross a mount point onto another store.
- Temporary files created by `Files.createTempFile(...)` in system temp might not reside on the same store as the output file.
- Move operations across stores may not support atomic moves; copy/move and metadata behavior can be restricted by the provider.

Therefore, if you need to check capacity for a file planned to be written in `/data/export`, determine the store associated with **a valid target location**, usually via the existing target directory. Do not check capacity of `Path.of(".")` and apply it indiscriminately everywhere.

To avoid races when the path does not exist yet, a program can locate **an existing parent directory** as the preflight reference point; however, the result remains an estimate and subsequent filesystem changes must still be handled.

## 15. Permissions, Symbolic Links, and Path State

`Files.getFileStore(path)` and attribute APIs can be affected by:

- Directory traversal permissions.
- Symbolic links and target resolution per provider.
- Files deleted or replaced between two queries.
- Devices unmounted/remounted.
- Network filesystems losing connection.
- A relative path interpreted against a different working directory.

**Do not use `normalize()` results as proof a path has been resolved on the filesystem.** `Path.normalize()` only cleans up `.` and `..` syntactically without validating symlinks or access permissions.

For user-supplied path inputs, validate roots, access rights, and symlinks/races per your threat model. Even after picking a `FileStore`, still perform the actual operation and **catch exceptions**, never trusting prior metadata reads as a guarantee of future state.

When querying `Files.getFileAttributeView(path, clazz, LinkOption.NOFOLLOW_LINKS)`, it can help query attributes of **the symlink itself** rather than the target when supported by the provider. Do not assume every view or metadata operation supports `NOFOLLOW_LINKS` and identical permissions.

## 16. Using `supportedFileAttributeViews` to Build Portable Applications

A sensible strategy for a cross-OS file management tool:

1. Determine the path and filesystem provider the data actually uses.
2. Query `path.getFileSystem().supportedFileAttributeViews()` for **filesystem/provider-level** information.
3. When working with a specific store, query `Files.getFileStore(path)` and `store.supportsFileAttributeView(...)`.
4. Before operating on file attributes, pick the appropriate view and access via `Files.getFileAttributeView` / `Files.readAttributes`.
5. If a view is unsupported, reject mandatory features or use an **intentional** fallback, without silently faking attributes.
6. Even if support checks return `true`, still handle `IOException`, `UnsupportedOperationException`, and insufficient permissions.
7. Write tests covering at least the real filesystem configurations you need to support, especially POSIX/DOS/ACL/ZIP/network mounts.
8. For security-meaningful metadata (permissions, ACLs), do not silently drop them during backup/migration if the contract requires preserving them.

### Decision Example: "Set Hidden Flag" Feature

If `FileStore` does not support the DOS attribute view, you cannot unconditionally call `Files.setAttribute(path, "dos:hidden", true)` and expect cross-platform execution. You can choose an application-UI-level hiding feature instead of modifying file attributes, or clearly report "unsupported on this store".

Similarly, changing owner or POSIX `chmod` requires verifying the appropriate view and privileges. Never use a `FileStore` support check as a substitute for real security controls.

## 17. Common Mistakes

1. **Confusing a `FileStore` with a single file.** `FileStore.getTotalSpace()` is store capacity; `BasicFileAttributes.size()` is the size of one file.
2. **Using `getTotalSpace()` to decide if there is enough room to write.** Total includes used space; consult `getUsableSpace()`.
3. **Assuming `getUnallocatedSpace()` always equals `getUsableSpace()`.** Quotas/reserved space can make the two numbers differ.
4. **Ignoring byte units.** APIs return bytes, not KB/MB/GiB directly.
5. **Using `int` to store capacities.** Risks integer overflow; use `long`.
6. **Using `String.length()` to measure UTF-8 bytes.** Java strings have UTF-16 code units; encoded bytes can differ.
7. **Believing `usable >= size` guarantees writes will succeed.** Capacity changes, plus permissions/ACLs/inodes/quotas/overhead and I/O errors exist.
8. **Measuring capacity on temp and applying it to output on a different store.** Reference the appropriate destination location.
9. **Assuming `FileStore.name()` is always non-empty or unique.** Providers can return an empty string.
10. **Relying on `FileStore.type()` as a cross-platform standard.** It is a provider-dependent string and may not be portable.
11. **Confusing `FileSystem.supportedFileAttributeViews()` with `FileStore.supportsFileAttributeView(...)`.** Provider layer vs. specific store.
12. **Assuming every view in the set works on every path.** Store, permissions, and path state must still be considered.
13. **Using POSIX APIs on systems with only DOS views.** Can be unsupported; check and have a policy.
14. **Thinking the DOS read-only flag equals store read-only.** One is a file attribute, the other is storage capability.
15. **Assuming a supported view implies permission to modify metadata.** Support is not authorization.
16. **Ignoring exceptions from metadata reads.** Disappearing paths, permission changes, or network failures can still occur.
17. **Overusing `getAttribute("...")` with provider-specific keys.** There is no universal mandatory key list.
18. **Listing `getFileStores()` and guessing by name.** Use `Files.getFileStore(path)` when you care where a path resides.
19. **Ignoring symlink/mount/quota changes.** Metadata results can become stale.
20. **Thinking `isReadOnly() == false` guarantees writability.** You still must open/write and handle real errors.

## 18. API Selection Table by Question

| Question to Answer | Appropriate API | Notes |
|---|---|---|
| Which store does the current path belong to? | `Files.getFileStore(path)` | May throw `IOException` |
| How many total bytes does the store have? | `store.getTotalSpace()` | Not usable space |
| How many unallocated bytes exist? | `store.getUnallocatedSpace()` | May differ from usable |
| Roughly how many bytes can the JVM currently use? | `store.getUsableSpace()` | Snapshot/estimate only |
| Is the store in read-only mode? | `store.isReadOnly()` | Does not replace file-specific permissions |
| Which view names does the filesystem provider support? | `path.getFileSystem().supportedFileAttributeViews()` | Set of view names at filesystem level |
| Does the target store support the POSIX view? | `store.supportsFileAttributeView("posix")` | May differ from other stores |
| What basic metadata does a specific path have? | `Files.readAttributes(path, BasicFileAttributes.class)` | Reads file/entry attributes |
| Is an attribute view accessible? | `Files.getFileAttributeView(path, Class)` | May be `null` or fail on use |
| Which stores does the filesystem allow listing? | `fileSystem.getFileStores()` | Not automatic path mapping |
| How many bytes long is a specific file? | `Files.size(path)` | Not store capacity |
| Did writing the destination file succeed? | Open/write/close, verify result | Never replace with preflight metadata |

## 19. Self-Practice Questions

**Question 1.** Do `getTotalSpace()` and `getUsableSpace()` have the same meaning?  
**Answer:** No. Total is total store capacity; usable is the capacity usable by the JVM per the provider at measurement time.

**Question 2.** Why shouldn't you use `getUnallocatedSpace()` to guarantee the application can write that many bytes?  
**Answer:** Permissions, quotas, reserved space, filesystem overhead, and race conditions can restrict actual writable bytes.

**Question 3.** How does `FileSystem.supportedFileAttributeViews()` differ from `FileStore.supportsFileAttributeView("posix")`?  
**Answer:** The former returns the set of view names at the filesystem/provider level; the latter asks whether the `posix` view is supported on one specific store.

**Question 4.** A store reports supporting `posix`. Is changing permissions guaranteed to be allowed on every file in that store?  
**Answer:** No. Support does not mean operation permission; files may be locked, deleted, or restricted by permissions.

**Question 5.** On the NTFS system in the example, `name()` is an empty string. Does that mean `getFileStore` failed?  
**Answer:** No. `name()` is a provider-supplied name and may be empty, while the other methods still return normal info.

**Question 6.** To find the size of `report.txt`, is calling `store.getTotalSpace()` correct?  
**Answer:** No; use `Files.size(reportPath)` or `BasicFileAttributes.size()`.

**Question 7.** Preflight shows `usableBytes >= expectedBytes`. Can you skip handling `IOException` when writing?  
**Answer:** No. It is only an advisory check at measurement time; the write operation can still fail.

**Question 8.** An application wants to display capacity in GiB; should it divide by 1,000,000,000 or 1,073,741,824?  
**Answer:** GiB uses 1,073,741,824; decimal GB uses 1,000,000,000.

**Question 9.** To inspect DOS hidden on a file, is checking `store.isReadOnly()` enough?  
**Answer:** No. That is a different attribute; use `DosFileAttributeView`/`DosFileAttributes` according to support.

**Question 10.** Why might a `Path` belonging to the same default filesystem as another path not reside on the same `FileStore`?  
**Answer:** A filesystem/provider can span multiple volumes, mounts, network shares, or distinct logical stores.

## Conclusion

**`FileStore`** is where Java queries store-level capacity and attributes: `getTotalSpace`, `getUnallocatedSpace`, `getUsableSpace`, `isReadOnly`, and `supportsFileAttributeView`. **`FileSystem.supportedFileAttributeViews()`** provides attribute support info at the filesystem/provider level. To read attributes of a real file, use **`Files.readAttributes` / `Files.getFileAttributeView`** with the appropriate view.

When deciding whether there is enough room to write a file, prefer **`getUsableSpace`** over `getTotalSpace`/`getUnallocatedSpace`, while always recognizing it as a **mutable estimate**, never a substitute for exception handling, quotas, permissions, and post-write integrity verification. Choose attribute views **based on runtime environment support**, without hardcoding assumptions like "Windows always means DOS, Linux always means POSIX" across all providers/stores.

### Java SE 17 Documentation

- [`FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
- [`Files.getFileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`FileSystem.supportedFileAttributeViews`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html)
- [`FileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttributeView.html)
- [`BasicFileAttributeView` / `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html)
- [`PosixFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [`DosFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributeView.html)
- [`AclFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html)
- [`UserDefinedFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/UserDefinedFileAttributeView.html)
