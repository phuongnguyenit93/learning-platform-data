# FileSystem, FileSystems, and FileSystemProvider in Java NIO.2

## 1. Why does Java have these three components?

When writing I/O programs, we often work with `Path` and `Files`: opening files, creating directories, copying, or reading attributes. However, **not every path belongs to the operating system's default file system**. Java NIO.2 (packages `java.nio.file` and `java.nio.file.spi`) allows accessing many different file systems through a *provider* architecture.

For example, the same Java application can use:

- The machine's default file system: Windows drives, Linux partitions, macOS…
- A file system representing the contents of a ZIP/JAR file when a ZIP filesystem provider is available.
- A read-only filesystem providing an image of the Java Runtime (JRT) modules.
- A virtual file system installed by a library or application, if a corresponding provider exists.

Three easily confused names have different roles:

| Component | Type and package | Main responsibility |
| --- | --- | --- |
| `FileSystems` | Utility class `java.nio.file.FileSystems` | Provides the default filesystem; finds an already-open filesystem; initializes/mounts a filesystem through the appropriate provider. |
| `FileSystem` | Abstract class `java.nio.file.FileSystem` | Represents **one file system instance**; creates a `Path` belonging to it, provides roots, separator, file stores, supported metadata, and manages lifecycle. |
| `FileSystemProvider` | SPI abstract class `java.nio.file.spi.FileSystemProvider` | Implementation of I/O operations and filesystem management for a URI scheme, such as `file` or `jar`. |

Overview of the relationship:

~~~text
FileSystems (entry point / factory)
       |
       +-- getDefault(), getFileSystem(), newFileSystem()
                           |
                           v
                  FileSystem (instance)
                    |        |
                    |        +--> provider(): FileSystemProvider
                    |
                    +--> getPath(...) --> Path --> Files.readString/copy/delete/...
                                            |
                                            +--> provider performs the corresponding I/O
~~~

`Files` is the API class for operations on `Path`. When data access is needed, Java works with the provider of the file system that owns that path. As a result, most code using `Files` does not need to know whether the path resides on a disk drive or inside a ZIP filesystem.

## 2. `FileSystems`: getting, finding, and opening a filesystem

### 2.1. The default file system: `getDefault()`

~~~java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

FileSystem fs = FileSystems.getDefault();
Path path = fs.getPath("data", "report.txt");
System.out.println(path.getFileSystem() == fs);
~~~

This is an **illustrative code snippet** with the necessary imports; to run it standalone, place it inside a Java class's `main` method.

- `FileSystems.getDefault()` returns the default filesystem object that the application uses to work with the machine's file system. Common calls like `Path.of("data.txt")` create paths belonging to the default filesystem.
- `fs.getPath("data", "report.txt")` creates a `Path` based on the syntax of `fs`; how separators are represented depends on the provider/platform.
- `path.getFileSystem()` returns the filesystem that owns that `Path`. The comparison result in the example is `true`.

Do not proactively close `FileSystems.getDefault()`; the default filesystem is managed by the Java runtime and cannot be closed like a user-created filesystem.

### 2.2. Opening a filesystem via a provider: `newFileSystem(...)`

~~~java
FileSystem fs = FileSystems.newFileSystem(uri, options);
~~~

For the overload accepting `URI` and `Map<String, ?>`, Java locates a provider matching the **scheme** in `uri`, then asks the provider to create the filesystem. `options` are provider-specific options: Java does not guarantee that every provider understands a common set of keys.

Some common overloads:

| API | Meaning |
| --- | --- |
| `FileSystems.newFileSystem(URI, Map<String, ?>)` | Creates a filesystem with a URI and environment options. |
| `FileSystems.newFileSystem(Path)` | Finds a provider that supports using a path to a file as the backing store for a filesystem; for example, ZIP/JAR on a JDK with a ZIP provider, depending on the runtime. |
| `FileSystems.newFileSystem(Path, Map<String, ?>)` | Similar to the `Path` overload, with additional environment options. |
| `FileSystems.newFileSystem(URI, Map<String, ?>, ClassLoader)` | Allows using a class loader to locate custom providers in addition to built-in providers; resolution details depend on the overload and runtime configuration. |

Distinguish between **creating a new instance** and **getting an existing instance**. Calling `newFileSystem` for a filesystem/URI already managed by a provider may throw `FileSystemAlreadyExistsException`. Do not assume that calling it again will return the existing object.

### 2.3. Getting an already-open filesystem: `getFileSystem(URI)`

~~~java
FileSystem mounted = FileSystems.getFileSystem(uri);
~~~

This method asks the provider to look up an **existing** filesystem by URI. It does not create a new filesystem on its own. If the provider cannot find a matching instance, it may throw `FileSystemNotFoundException`.

Depending on the provider, the URI identifying a filesystem may differ from the URI identifying **a file inside** it. For a ZIP filesystem, a URI such as `jar:file:/.../archive.zip` describes the archive used to open the filesystem; to reach a specific entry, the direct and clear approach is to obtain a `Path` from the opened `FileSystem` object.

## 3. `FileSystem`: a specific path namespace

Once you have a `FileSystem`, you can query its characteristics and create paths inside it.

| Method | Purpose | Notes |
| --- | --- | --- |
| `getPath(first, more...)` | Creates a `Path` according to the current filesystem's syntax. | Does not read content or verify that the file exists. |
| `provider()` | Accesses the provider implementing the filesystem. | You can inspect the scheme via `provider().getScheme()`. |
| `getSeparator()` | Name separator character in paths according to the provider. | Do not assume all systems use the same `/` or `\`. |
| `getRootDirectories()` | Lists the roots provided by the filesystem. | There may be multiple roots or a single root; not forced into Windows drive format. |
| `getFileStores()` | The file stores that the provider allows enumerating. | May fail or be incomplete depending on environment and permissions. |
| `supportedFileAttributeViews()` | Attribute views that may be supported (for example `basic`). | Do not assume `posix`, `dos`, or `acl` are present by default. |
| `getPathMatcher("glob:...")` | Creates a path matcher using a syntax supported by the provider. | Depends on the provider and `glob` or `regex` syntax. |
| `isOpen()`, `isReadOnly()` | Checks open/closed state and writability. | Virtual file systems may be read-only. |
| `close()` | Releases resources of a closable filesystem. | Do not close the default filesystem; close custom filesystems when finished. |

A `Path` is always **bound to a specific `FileSystem`**:

~~~java
Path local = FileSystems.getDefault().getPath("notes.txt");
FileSystem owner = local.getFileSystem();
~~~

Two `Path` objects that look identical in name can still belong to two different filesystems. Some path operations such as `relativize` or `resolve` with a `Path` from another provider may throw `ProviderMismatchException`. Creating paths via **`fs.getPath(...)` of the target filesystem** is a reliable way to avoid namespace confusion.

For example, `zipFs.getPath("/notes.txt")` is an entry inside the ZIP; `Path.of("notes.txt")` is a path on the default filesystem. They do not point to the same place even though the name part in both is `notes.txt`.

## 4. `FileSystemProvider`: the operation implementation and extension mechanism

`FileSystemProvider` resides in `java.nio.file.spi`. A provider advertises a URI scheme through `getScheme()` and implements the methods for working with resources of that scheme.

The provider is responsible for foundational operations such as:

- Creating, locating, and returning filesystems: `newFileSystem(...)`, `getFileSystem(URI)`, and `getPath(URI)`.
- Opening I/O or channels: `newByteChannel(...)`, `newInputStream(...)`, `newOutputStream(...)` (some methods have default implementations).
- Entry operations: `createDirectory(...)`, `delete(...)`, `copy(...)`, `move(...)`, and `checkAccess(...)`.
- Reading/writing attributes and supporting operations related to links, directory streams, and permissions depending on the provider's capabilities.

You can list the providers installed and discovered in the runtime:

~~~java
import java.nio.file.spi.FileSystemProvider;

for (FileSystemProvider provider : FileSystemProvider.installedProviders()) {
    System.out.println(provider.getScheme());
}
~~~

This is a **snippet for use in `main`**. On a typical JDK you may see `file` and `jar`, and possibly `jrt` or additional providers; **do not rely on the order or number of providers** in your program. With a runtime minimized using `jlink`, the ZIP provider module (`jdk.zipfs`) may not be present.

The SPI architecture allows libraries to supply a new provider. When building your own provider, besides extending `FileSystemProvider`, you must also implement appropriate `FileSystem`, `Path`, and I/O operation objects, and handle lifecycle, errors, and access permissions. A provider on the classpath is typically declared in the service file:

~~~text
META-INF/services/java.nio.file.spi.FileSystemProvider
~~~

The content is the fully qualified class name of a provider class that can be instantiated according to service provider rules. In a **named module**, you can use the declaration `provides java.nio.file.spi.FileSystemProvider with ...;` in `module-info.java` instead of the classpath declaration mechanism. This is the work of developing a complete filesystem provider, not a requirement when you only want to read/write files with NIO.2.

## 5. Java 17+ example: creating, writing, closing, and reopening a ZIP filesystem

**Goal:** use a `FileSystemProvider` with the `jar` scheme to treat a ZIP file as a filesystem. The program creates a ZIP in a temporary directory, creates a file inside the ZIP, reads its content, closes the filesystem, and then reopens it to prove the data was persisted.

Save all of the following code to `FileSystemDemo.java`:

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class FileSystemDemo {
    public static void main(String[] args) throws IOException {
        FileSystem defaultFs = FileSystems.getDefault();
        System.out.println("defaultScheme=" + defaultFs.provider().getScheme());

        Path local = defaultFs.getPath("example.txt");
        System.out.println("localUsesDefault=" + (local.getFileSystem() == defaultFs));

        Path tempDir = Files.createTempDirectory("nio-fs-demo-");
        Path archive = tempDir.resolve("example.zip");
        URI zipUri = URI.create("jar:" + archive.toUri());

        try {
            // "create" is an option of the ZIP filesystem provider,
            // not a shared option across all providers.
            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                Path entry = zipFs.getPath("/message.txt");
                Files.writeString(entry, "Hello, ZipFS", StandardCharsets.UTF_8);

                System.out.println("zipScheme=" + zipFs.provider().getScheme());
                System.out.println("zipText=" +
                        Files.readString(entry, StandardCharsets.UTF_8));
            }

            // Reopen the same archive after the previous ZIP instance has been closed.
            try (FileSystem reopened = FileSystems.newFileSystem(
                    zipUri, Map.of())) {

                Path entry = reopened.getPath("/message.txt");
                System.out.println("reopenedText=" +
                        Files.readString(entry, StandardCharsets.UTF_8));
            }
        } finally {
            // Only delete the archive after the ZIP filesystem has been closed.
            Files.deleteIfExists(archive);
            Files.deleteIfExists(tempDir);
        }
    }
}
~~~

Compile and run commands for JDK 17 or later:

~~~bash
javac FileSystemDemo.java
java FileSystemDemo
~~~

Typical output on a full JDK with the default `file` provider and `jdk.zipfs`:

~~~text
defaultScheme=file
localUsesDefault=true
zipScheme=jar
zipText=Hello, ZipFS
reopenedText=Hello, ZipFS
~~~

Step-by-step explanation:

1. `defaultFs` is the machine's filesystem; `local` is a `Path` belonging to that filesystem. The program does not create `example.txt` on disk; it only creates the path object.
2. `tempDir` is an actual temporary directory created on disk; `archive` specifies the ZIP file to be created. `URI.create("jar:" + archive.toUri())` builds the URI for the ZIP provider to identify the archive.
3. `FileSystems.newFileSystem(zipUri, Map.of("create", "true"))` asks the ZIP provider to create/open a filesystem on the archive; the provider records data inside the ZIP. The `create` key only has meaning for the ZIP provider.
4. `zipFs.getPath("/message.txt")` is an **entry path inside the ZIP**, not a direct `Path` to a file on disk. `Files.writeString` and `Files.readString` operate through the provider of `zipFs`.
5. The `try-with-resources` block calls `close()` when leaving the block. Closing the ZIP filesystem is crucial to finish writing the archive structure and release resources.
6. The second block creates a new ZIP filesystem instance on the saved archive, reads `message.txt` again, and prints `reopenedText`. Only after closing does the `finally` code clean up the archive and temporary directory.

The values `defaultScheme=file` and `zipScheme=jar` are characteristics of the providers in the example runtime environment. If `jdk.zipfs` is missing, the provider is disabled, or filesystem permissions are lacking, the example may throw an exception. That is an environment condition to check, not an alternative stdout.

Another way to access an **existing** ZIP is `FileSystems.newFileSystem(Path.of("archive.zip"))` (an overload supported on Java 17), when the runtime has a provider accepting that file type. This differs from creating a new archive using a URI and the `create` option.

## 6. URI, filesystem instance, and path: choosing the right operation

Three types of access are often placed side by side:

~~~java
FileSystem defaultFs = FileSystems.getDefault();      // Get default
FileSystem mounted = FileSystems.getFileSystem(uri);   // Get already-open instance
FileSystem created = FileSystems.newFileSystem(uri, Map.of()); // Create new instance
~~~

This is an **illustrative snippet**, assuming the `uri` variable is already defined and a corresponding provider exists. Do not run these three lines back-to-back on an arbitrary URI and expect all of them to always succeed: `getFileSystem` requires an existing instance, while `newFileSystem` requires valid creation/opening conditions.

Distinguish `Path.of(URI)` from `FileSystem.getPath(...)`:

- `Path.of(URI)` asks Java to find the provider for the URI and obtain the corresponding `Path`. Not every URI contains enough information to create a `Path`, and the provider may require the filesystem to have already been initialized.
- `fileSystem.getPath("/inside.txt")` simply creates a path **within that filesystem**; there is no need to re-translate the scheme from a URI each time.
- `Path.of("relative.txt")` uses the default filesystem, even if a ZIP filesystem is currently open in the program.

With ZIP/JAR, avoid manually concatenating URIs or paths based on OS assumptions. Open the filesystem using the appropriate API and create entries using `zipFs.getPath(...)` itself. Do not use `Path.of("/message.txt")` to refer to a ZIP entry.

A path between two providers can be transferred as data for copying via `Files.copy(source, target)` when the operation/provider supports it, but that does not mean the two `Path` objects belong to the same namespace; options for attributes, symbolic links, and atomicity may differ between providers. Do not assume a cross-filesystem `move` is atomic.

## 7. Lifecycle and support limits

**Default filesystem:** owned by the Java runtime and exists for the entire lifetime of the application. Do not call `close()` on the default filesystem.

**Manually opened filesystem:** if it is closable (for example a ZIP filesystem), use `try-with-resources`. After closing:

- `isOpen()` normally returns `false` for that instance.
- I/O operations based on a `Path` belonging to the closed instance may throw `ClosedFileSystemException`.
- A `Path` does not automatically switch over to a newly reopened filesystem; after reopening, obtain a new `Path` from the new instance.
- Reading metadata or operating on a closed filesystem depends on method contracts, so do not reuse a closed object to keep working.

`isReadOnly()` helps detect a read-only filesystem. Not every provider uniformly supports symbolic links, watch services, file attribute views, permissions, or synchronous operations. When reading only static data, do not assume file creation is available; for constrained operations, check the supported APIs and handle actual exceptions.

For JAR/JRT/virtual providers, `FileStore` and roots can differ greatly from traditional drive layouts. `getRootDirectories()` is a more appropriate data source than guessing `C:\` or `/` roots.

## 8. Exceptions worth distinguishing

| Exception | Common situation | How to handle |
| --- | --- | --- |
| `ProviderNotFoundException` | No matching provider found when a filesystem needs to be created. | Verify the scheme and provider module/library, such as `jdk.zipfs`. |
| `FileSystemAlreadyExistsException` | Attempting to create a filesystem when the provider already manages an instance for that URI. | Use the currently open instance when appropriate, or close the instance before reopening. |
| `FileSystemNotFoundException` | `getFileSystem(uri)` cannot find an already-open filesystem. | Verify the lifecycle and timing of the `newFileSystem` call. |
| `ClosedFileSystemException` | Using a closed filesystem. | Reopen the filesystem and obtain a new `Path`. |
| `ReadOnlyFileSystemException` | Attempting to write to a read-only filesystem. | Choose a different write destination or perform read-only operations. |
| `ProviderMismatchException` | Combining provider-incompatible path objects in an operation requiring the same provider. | Create/interpret paths using the proper owning filesystem. |
| `UnsupportedOperationException` | The provider does not support the requested method or feature. | Check the provider's capabilities and choose a compatible operation. |
| `IOException` and subclasses | File errors, access permissions, archive format issues, or I/O problems during create/read/write/close. | Handle according to business logic; do not treat an I/O error as a nonexistent filesystem. |

Several exceptions in the table are unchecked; `IOException` is a checked exception. When using `try-with-resources`, errors arising from `close()` can also be I/O errors that need handling. Do not swallow errors if write results are not guaranteed to have been persisted.

## 9. Common mistakes when designing NIO.2 code

**Confusing `FileSystems` with `FileSystem`.** `FileSystems` is just an entry point with static methods. It is the `FileSystem` **instance** itself that determines `getPath`, roots, provider, and open/closed state.

**Creating `Path.of("...")` and expecting to access a ZIP.** `Path.of(String...)` always uses the default filesystem. To work inside a ZIP, use `zipFs.getPath(...)`.

**Calling `newFileSystem` repeatedly without closing.** If that URI already has an instance, the provider may reject it; moreover, leaking ZIP resources impairs archive management operations. Use `try-with-resources` and clearly define which object owns the lifecycle.

**Guessing schemes, providers, or supported features.** Do not assume every runtime has `jar` or every provider has `posix`. Use `FileSystemProvider.installedProviders()` when diagnosing; check according to actual needs.

**Confusing a filesystem with a directory.** A `FileSystem` is the entire space of paths/I/O objects provided by a provider; it is not synonymous with a directory. A ZIP archive can be presented as its own filesystem, whereas a directory is usually just a `Path` inside an existing filesystem.

**Assuming any path is compatible with any provider.** A `Path` carries information about its owning filesystem. When building an API that accepts an external `Path`, preserve its filesystem instead of silently converting it via `Path.of(path.toString())`, because doing so can change the path's meaning.

**Believing an API guarantees access rights.** The provider is responsible for checking access, format, and OS permissions. Errors between checking and the actual operation can still occur if the file system changes concurrently. When handling user-supplied paths, apply appropriate security and authorization rules.

## 10. When do you need each API?

| Need | Choose API |
| --- | --- |
| Reading/writing ordinary local files | `Path.of(...)` and `Files.*`; rarely need to call `FileSystems.getDefault()` manually. |
| Need to know which filesystem a path belongs to | `path.getFileSystem()`. |
| Need to create a `Path` inside an already-open ZIP filesystem | `zipFs.getPath(...)`. |
| Need to create/open a special filesystem | `FileSystems.newFileSystem(...)` with the appropriate URI/Path and provider options. |
| Need to reuse an already-open filesystem identified by URI | `FileSystems.getFileSystem(uri)` if supported by the provider and the instance exists. |
| Need to know which provider is performing operations | `path.getFileSystem().provider()`. |
| Need to list discovered providers | `FileSystemProvider.installedProviders()`. |
| Need to support a new protocol/file system in a library | Implement `FileSystemProvider` along with appropriate `FileSystem`/`Path` and register via SPI. |

## 11. Self-check

1. **Does `FileSystems.getDefault()` return a `FileSystem` or a `FileSystemProvider`?** It returns a `FileSystem`; you can obtain the provider with `provider()`.
2. **Do two `Path` objects with the same name string definitely point to the same file?** No. They may belong to different filesystems or be resolved in different contexts.
3. **After opening a ZIP, does `Path.of("/message.txt")` point to the entry inside the ZIP?** No. It belongs to the default filesystem; you must use `zipFs.getPath("/message.txt")`.
4. **Why is it necessary to close a ZIP filesystem?** To finalize writing/flushing archive data according to the provider and release resources; `try-with-resources` should be used.
5. **How do `getFileSystem(uri)` and `newFileSystem(uri, env)` differ?** The first retrieves an existing filesystem; the second asks the provider to create a filesystem instance.
6. **Why shouldn't you hard-code a list of providers?** Runtime components, modules, and libraries can vary across execution environments.

**Remember:** `FileSystems` is where you **get or initialize** a filesystem; `FileSystem` represents **a specific path namespace**; `FileSystemProvider` is the **implementation of I/O operations** for that namespace. When a path is not on the default filesystem, always obtain the `Path` from the right `FileSystem` and manage the lifecycle of the opened filesystem.
