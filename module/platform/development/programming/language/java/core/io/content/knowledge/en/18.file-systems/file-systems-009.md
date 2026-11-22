# FileSystemProvider Extensibility and Java API Boundaries

## 1. The problem: sharing an API does not mean sharing every capability

Java NIO.2 (`java.nio.file`) allows writing code based on `Path` and `Files` to access different file systems: the OS default file system, ZIP/JAR contents, and backends implemented by third-party libraries. That mechanism relies on **FileSystemProvider**, an extensible Service Provider Interface (SPI).

For example, the same `Files.readString(path)` call can read a file on disk or an entry inside a ZIP, **provided `path`'s provider supports the required operation**.

Three layers of responsibility must be distinguished:

1. **Java API** defines the documented interfaces, data types, rules, and exceptions.
2. **File-system provider** turns API requests into operations on a specific backend and advertises the features it supports.
3. **Actual file system / file store** determines performance, access permissions, attribute types, atomicity, and platform limits.

Therefore, a method appearing in `Files` does not prove every file system has the same functionality or behavior guarantees.

## 2. Components that make up the architecture

| Component | Role | Example |
|---|---|---|
| `Path` | Represents a path bound to a specific `FileSystem` | `Path.of("data.txt")` or `zipFs.getPath("/data.txt")` |
| `FileSystem` | Manages roots, separator, provider, attribute views, and lifecycle of a file system | `FileSystems.getDefault()`, ZIP file system |
| `FileSystemProvider` | SPI to create/find file systems, convert URIs to Paths, and execute low-level file operations | Providers with `file` and `jar` schemes |
| `Files` | API-level convenience operations, typically using the provider of the corresponding `Path` objects | `readString`, `copy`, `walk`, `readAttributes` |
| `FileStore` | Storage pool information represented by the provider | `Files.getFileStore(path)` |

Conceptual flow:

~~~text
Application
   └── Path / Files / FileSystems (Java NIO.2 API)
          └── FileSystemProvider (SPI)
                 └── Default file system, ZIP, or specific backend
~~~

This is an architecture diagram; individual `Files` methods may coordinate multiple provider operations, not necessarily delegating to a single SPI method.

A `Path` is always bound to its `FileSystem`. To inspect which provider it belongs to:

~~~java
Path path = Path.of("data.txt");
FileSystem fs = path.getFileSystem();
System.out.println(fs.provider().getScheme()); // file with the default provider
~~~

This is an illustrative snippet, not a standalone program. The file `data.txt` does not need to exist to create the `Path`.

## 3. What does provider extensibility mean?

### 3.1. The default provider

`FileSystems.getDefault()` returns the JVM's default file system. The default provider uses the `file` URI scheme and creates `Path` objects from ordinary calls such as `Path.of("notes.txt")`.

Do not equate the `file` scheme with NTFS, ext4, or APFS. The same default provider can work with different file stores, with case sensitivity, permissions, locking, and timestamp precision rules depending on the platform.

### 3.2. Additional providers

A provider is a concrete subclass of `java.nio.file.spi.FileSystemProvider`, identified by a URI scheme, acting as a factory for one or more `FileSystem` instances.

Real example in JDK 17: **the `jdk.zipfs` module supplies the ZIP file-system provider** with scheme `jar`, to read/write entries inside a ZIP/JAR as `Path` objects.

Another library *may* provide an in-memory, network, or object-storage backend with its own scheme (for example `memory`). Hypothetical scheme names are not built-in capabilities of Java SE; they only have meaning if a corresponding provider is installed and supported.

A provider defines how URIs, paths, content, file attributes, and I/O operations are parsed and executed. As a result, application code can reuse many `Files` operations, within the contract that the provider implements.

### 3.3. ZIP as an accessible example

The ZIP provider enables using `Path` inside a ZIP file:

~~~java
URI uri = URI.create("jar:" + archive.toUri());
try (FileSystem zipFs =
         FileSystems.newFileSystem(uri, Map.of("create", "true"))) {
    Path entry = zipFs.getPath("/notes.txt");
    Files.writeString(entry, "Xin chao");
}
~~~

This is an illustrative snippet inside a method that already has `Path archive` and handles `IOException`. `create=true` is a **ZIP provider configuration**, not a universal parameter for all providers. A complete runnable example is in section 6.

Separately opened `FileSystem` instances such as ZIP should be closed with `try-with-resources`. `Path` objects pointing to a closed file system cannot continue normal I/O; do not keep a ZIP `Path` after closing and assume it remains readable.

A custom runtime image (for example built with `jlink`) may lack the `jdk.zipfs` module. In that case, the application must handle the unavailable-provider error rather than assuming every Java distribution includes the ZIP provider.

## 4. Discovering, loading, and initializing providers

Relevant APIs:

- `FileSystems.getDefault()`: gets the default file system.
- `FileSystemProvider.installedProviders()`: gets the list of providers loaded via SPI, including the default provider.
- `FileSystems.newFileSystem(URI, Map)`: finds a provider by URI scheme and asks it to create a file system with provider-defined parameters.
- `FileSystems.getFileSystem(URI)`: gets an existing file system; not a creation command.
- `FileSystems.newFileSystem(Path)`: attempts to open a file as a file system using an available format/provider, such as ZIP.
- `Path.of(URI)` or `Paths.get(URI)`: converts a URI into a `Path` using a provider. Depending on the provider, the corresponding file system may need to be initialized beforehand.

Example distinguishing them:

~~~java
URI uri = URI.create("jar:file:/tmp/sample.zip");

// newFileSystem: creates a file system session when permitted by the provider
FileSystem created = FileSystems.newFileSystem(uri, Map.of());

// getFileSystem: requests retrieving an already existing file system by URI
FileSystem existing = FileSystems.getFileSystem(uri);
~~~

This is illustrative code, **not a standalone runnable snippet**. It assumes the ZIP file actually exists, the `jar` provider is available, and `created` is still open. Specific URI path syntax depends on the OS/provider.

Common exceptions:

| Case | Exception |
|---|---|
| No provider for the URI scheme | `ProviderNotFoundException` |
| No matching file system yet when calling `getFileSystem` | `FileSystemNotFoundException` |
| Creating a duplicate file system when the provider forbids it | `FileSystemAlreadyExistsException` |
| File system already closed | `ClosedFileSystemException` |
| Corrupted data/archive or backend failure | `IOException` or specific exception |

**Loading plugins via ServiceLoader**

A JAR on the classpath typically contains a concrete subclass of `FileSystemProvider` with a no-argument constructor, along with a service descriptor file:

~~~text
META-INF/services/java.nio.file.spi.FileSystemProvider
~~~

The descriptor file contains one or more lines with fully qualified provider class names, such as `com.example.CustomProvider`. This name is **for illustration only** and requires the class to actually exist and properly implement the SPI.

With a named module, it can be declared in `module-info.java`:

~~~java
provides java.nio.file.spi.FileSystemProvider
        with com.example.CustomProvider;
~~~

This is only an illustrative JPMS declaration, **not a complete module**. The module and provider class must be built, supplied on the module path/runtime, and implement the SPI contract.

Additional providers are discovered via `ServiceLoader`; applications must not arbitrarily rely on provider loading order. If a URI scheme collides with an earlier selected provider, the later duplicate provider may be ignored; do not design provider selection logic based on list position.

**Extending the default provider is a different case:** the system property `java.nio.file.spi.DefaultFileSystemProvider` can specify a chain of provider classes wrapping the default provider. Those classes accept a `FileSystemProvider` via a single-argument constructor and share the `file` scheme. This is not the mechanism to use when simply adding a new scheme like `jar`.

## 5. Boundary between common APIs and backend capabilities

### 5.1. Not every operation is supported

| Need | Why check the provider/file store? |
|---|---|
| Symbolic links, hard links | The backend may not support them or may deny link-creation permission |
| POSIX owner/permissions, ACL | Only available on supported attribute views |
| WatchService | May be unsupported, or may notify differently |
| File locking, memory mapping, async channels | Not every provider offers full channel capabilities |
| `ATOMIC_MOVE` | Only possible if the backend supports atomic moves in that situation |
| File modification times and attribute copying | Precision and copied attributes depend on the file store/provider |
| Case sensitivity, roots, separators, and path syntax | Rules defined by the `FileSystem` |
| Latency, consistency, and error handling | Differ across local FS, ZIP, and remote backends |

Query the provider for capabilities instead of inferring from the OS name:

~~~java
FileSystem fs = path.getFileSystem();
boolean supportsPosix =
        fs.supportedFileAttributeViews().contains("posix");
~~~

This is an illustrative snippet with an existing `path`. To check a specific attribute view for a `Path`, you can call `Files.getFileAttributeView(path, PosixFileAttributeView.class)`; it may return `null` if the view is unavailable. Supporting a view does not guarantee every permission operation on every file will succeed.

### 5.2. Never lose a Path's file system

Two `Path` objects can have identical printed strings yet belong to two different providers. Therefore:

- `Path.equals` does not consider two `Path` objects from different file systems equal.
- `Files.isSameFile(a, b)` returns `false` if the two paths belong to different providers.
- Operations like `resolve(Path)` with incompatible arguments may throw `ProviderMismatchException`.
- `Path.of(zipEntry.toString())` creates a **new `Path` on the default file system**, no longer a ZIP `Path`.
- Use `zipFs.getPath("/entry.txt")` or `directoryInZip.resolve("entry.txt")` to stay with the ZIP provider.

Using the same-named API does not merge the backend identity of two `Path` objects into one.

### 5.3. Cross-provider copy does not mean an atomic operation

`Files.copy(source, target)` supports cases where source and target belong to different providers. Java can coordinate reading from the source provider and writing to the target provider.

However, understand the guarantees clearly:

1. Copying creates an independent target file; identical content does not make two files the same file.
2. Copying is not atomic; if an error occurs mid-way, the target may be incomplete.
3. Copying attributes depends on the platform/provider/options, may lose timestamp precision, or may fail to copy certain attributes.
4. `Files.copy` on a directory **does not recursively copy the entire tree**; you must traverse the tree if you want to transfer the whole structure.
5. Moving across providers/file stores may not be possible or may require another mechanism; `ATOMIC_MOVE` is not guaranteed and may throw `AtomicMoveNotSupportedException`.

A shared API call does not turn ZIP/local/network into a single transaction.

### 5.4. Reject properly when a feature does not exist

Depending on the method and provider, Java may throw `UnsupportedOperationException` for unsupported options/features/attribute views, `IOException` for I/O errors, `ProviderMismatchException` for incompatible Paths, or other specific exceptions per the API documentation.

Do not turn everything into the conclusion "file does not exist". Missing-provider errors, closed-file-system errors, permission errors, and I/O errors require different handling strategies.

## 6. Runnable Java 17+ example: local and ZIP providers

The following program creates a local file, creates a ZIP file system, copies the file into the ZIP, and then closes and reopens the ZIP to prove the data was persisted. It uses a JDK with the `jdk.zipfs` module and requires no external dependencies.

**File: `ProviderBoundaryDemo.java`**

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ProviderBoundaryDemo {
    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("provider-demo-");
        Path source = work.resolve("source.txt");
        Path archive = work.resolve("bundle.zip");

        try {
            Files.writeString(source, "Xin chao", StandardCharsets.UTF_8);
            URI zipUri = URI.create("jar:" + archive.toUri());

            try (FileSystem zipFs =
                    FileSystems.newFileSystem(zipUri, Map.of("create", "true"))) {
                Path entry = zipFs.getPath("/message.txt");
                Files.copy(source, entry);

                System.out.println(
                        source.getFileSystem().provider().getScheme());
                System.out.println(
                        entry.getFileSystem().provider().getScheme());
                System.out.println(Files.readString(entry));
                System.out.println(Files.isSameFile(source, entry));
            }

            try (FileSystem reopened = FileSystems.newFileSystem(archive)) {
                System.out.println(
                        Files.readString(reopened.getPath("/message.txt")));
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(work);
        }
    }
}
~~~

Compile and run in the directory containing the source file:

~~~bash
javac ProviderBoundaryDemo.java
java ProviderBoundaryDemo
~~~

**Stdout when the ZIP provider is available:**

~~~text
file
jar
Xin chao
false
Xin chao
~~~

Output explanation:

1. `source` is on the default provider (`file`).
2. `entry` resides inside the ZIP (`jar`).
3. The same `Files.copy` and `Files.readString` APIs operate across two different providers.
4. `Files.isSameFile` returns `false` because the two providers differ.
5. Reopening the ZIP from the file after closing proves `message.txt` remained stored in the archive.

The program uses a random temporary directory name without printing it, so the displayed output is deterministic. `finally` cleans up files; deletion can still fail with `IOException` if the backend/OS encounters an error. On a runtime without `jdk.zipfs`, opening `jar` may report that no provider was found.

## 7. What must you do if writing your own FileSystemProvider?

A provider is not just a "file-reading adapter". A developer must implement a concrete `FileSystemProvider` and `FileSystem`/`Path` types with consistent semantics.

Main groups of responsibilities:

- **Identity/initialization:** `getScheme()`, `newFileSystem(URI, env)`, `getFileSystem(URI)`, `getPath(URI)`.
- **Paths:** roots, relative/absolute, names and separators, comparison/normalization, file system lifecycle.
- **I/O:** `newByteChannel`, reading/writing data, `newDirectoryStream`, creating/deleting/copying/moving files and directories.
- **Metadata:** `checkAccess`, `isSameFile`, `getFileStore`, `readAttributes`, `getFileAttributeView`, `setAttribute`, along with view support.
- **Errors and concurrency:** throwing contract-compliant exceptions, handling resource closing, concurrent I/O, and changing file state.

There are SPI methods required to be implemented (`abstract`) and methods with defaults that may report unsupported. Before implementing, read the Javadoc of each method rather than copying logic from one backend type and assuming it applies to every system.

With object storage, for example, a "directory" may just be a way of representing key prefixes, rename may not be atomic, and file listings behave differently from POSIX. If writing a provider, clearly document boundaries regarding semantics, consistency, and performance. If you only need ZIP access, using the built-in `jdk.zipfs` is usually far simpler than writing your own SPI.

## 8. Principles for writing code that works with multiple providers

- **Preserve `Path` and its file system:** pass `Path` across layers, avoiding converting through `toString()` and rebuilding with `Path.of(...)`.
- **Resolve child paths in the current file system:** `directory.resolve("child.txt")` or `directory.getFileSystem().getPath(...)`. Avoid concatenating OS separator strings.
- **Check capabilities before provider-specific features:** attribute views, file stores, link/watch/channel support, and atomic moves.
- **Use `Files` when the contract meets your needs:** common read/write/copy operations are reusable, but do not assume optional flags are always available.
- **Handle errors by category:** distinguish missing provider, closed file system, missing feature, permission errors, and I/O errors.
- **Manage lifecycles:** close separately opened `FileSystem` instances like ZIP, channels, streams, and `Stream<Path>` from `Files.walk`. Do not manually close the JVM's default file system.
- **Test directly against the target provider:** test filesystem behavior, atomicity, attributes, and performance. Unit tests on a local temp directory do not replace integration tests for a specialized backend.
- **Do not ignore cost:** remote providers can trigger many requests/network I/O calls from seemingly small operations like `exists`, `list`, or `readAttributes`.

## 9. Common misconceptions

1. **"Since `Files.readString` exists, every backend can read."** Wrong: the provider must support the operation and the data must be accessible.
2. **"Files inside a ZIP and local files are both `Path`, so they can be compared/joined freely."** Wrong: they belong to two different file systems/providers.
3. **"`getFileSystem(uri)` auto-creates a file system if none exists."** Wrong: it retrieves an existing file system, unlike `newFileSystem`.
4. **"`Files.copy` copies an entire subtree and preserves all attributes."** Wrong: recursion must be handled manually; attributes depend on the provider.
5. **"`ATOMIC_MOVE` will succeed between two providers."** Not guaranteed.
6. **"A service descriptor alone makes a custom provider work."** Wrong: you need a class implementing the contract, proper registration, and proper packaging.
7. **"Every Java runtime includes `jdk.zipfs`."** Minimal runtimes may omit this module.

## 10. Remember

~~~text
Java API: describes how the application requests operations.
FileSystemProvider: executes requests on a specific backend.
Backend/file store: determines actual capabilities, limits, and costs.
~~~

Before relying on a capability, ask: **Which provider does this `Path` belong to? What does the Java contract promise? Does the provider/file store actually support the feature and guarantee level the application needs?**

### Official documentation

- [Java 17: FileSystemProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html)
- [Java 17: FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html)
- [Java 17: Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java 17: Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [JDK 17: jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html)
