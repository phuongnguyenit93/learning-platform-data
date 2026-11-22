# Default File System and Installed Providers in Java NIO.2

## 1. Why does Java have `FileSystem` and `FileSystemProvider`?

When working with files using `java.nio.file`, an application usually starts with the machine's built-in file system: Windows drives or directories on Unix/Linux/macOS systems. Java calls this the **default file system**. However, NIO.2 does not restrict paths to the operating system's file system: a ZIP file can be opened as its own file system, or a library can provide a virtual file system.

Three concepts connect together:

- **`FileSystemProvider`** (`java.nio.file.spi.FileSystemProvider`): the provider that implements operations on file systems, paths, file channels, attributes, and more. Each provider has a URI scheme, such as `file` or `jar`.
- **`FileSystem`** (`java.nio.file.FileSystem`): a file system instance supplied by a provider. One provider can manage multiple `FileSystem` instances.
- **`Path`** (`java.nio.file.Path`): a path bound to the exact `FileSystem` that created it. Call `path.getFileSystem()` to check where the path belongs.

~~~text
FileSystemProvider with scheme "file" (default provider)
          └── default FileSystem
                  ├── Path "data/input.txt"
                  └── Path "logs/app.log"

FileSystemProvider with scheme "jar" (ZIP FS provider, when present)
          ├── FileSystem for archive-a.zip
          │       └── Path "/docs/a.txt"
          └── FileSystem for archive-b.zip
                  └── Path "/docs/b.txt"
~~~

The diagram illustrates the relationship, not a guarantee that every machine has a ZIP provider. **An installed provider does not mean a specific `FileSystem` is already open**. For example, the `jar` provider may be present while the application has not opened any ZIP yet.

## 2. Default file system: how to obtain it and basic guarantees

Core APIs:

~~~java
FileSystem defaultFs = FileSystems.getDefault();
FileSystemProvider provider = defaultFs.provider();

Path file = Path.of("data", "input.txt");
Path another = Paths.get("data", "input.txt");
~~~

These are **illustrative code snippets**; place them in a Java class/method and import `java.nio.file.*`, `java.nio.file.spi.FileSystemProvider` when using them.

`FileSystems.getDefault()` returns the JVM's default file system. On a typical JDK, it represents the running machine's file system environment. `Path.of(String, String...)` and `Paths.get(String, String...)` create paths on the default file system; `Paths.get` is the older API and can generally be replaced by `Path.of` since Java 11.

Key characteristics to remember:

1. `FileSystems.getDefault()` returns the same default file system for the process; use identity comparison `==` when checking whether two variables point to the same object.
2. The default filesystem's provider uses the **`file`** scheme. Therefore `defaultFs.provider().getScheme()` returns `"file"`.
3. `Path.of("relative.txt")` only creates a relative path object. It does **not** check whether the file exists and does **not** write any file.
4. The default file system is not managed with the same lifecycle as additionally opened file systems. Do not manually close `FileSystems.getDefault()`. In the default implementation, `close()` is unsupported.
5. `defaultFs.getSeparator()`, `defaultFs.getRootDirectories()`, and naming rules may differ across operating systems or providers. Do not assume `/`, drive letters, or case sensitivity are the same on every machine.

**Advanced configuration note:** The JDK supports the startup property `java.nio.file.spi.DefaultFileSystemProvider` to request a custom provider that wraps the default provider. This is a configuration option set before initializing the default filesystem, not an operation changed arbitrarily while the application is already using `Path` objects. Therefore, do not assume the actual class of the default provider is always fixed across every runtime; query it through the API.

## 3. Installed providers: `installedProviders()`

The list of providers visible in the current runtime environment is obtained via:

~~~java
List<FileSystemProvider> providers =
        FileSystemProvider.installedProviders();
~~~

`installedProviders()` returns a list of providers installed/discovered in the runtime. **The first element is the default provider**; other providers depend on the JDK, runtime modules, and additional libraries. This list is loaded and cached for reuse, so the call should not be understood as rescanning arbitrary JARs on every invocation.

Some common schemes:

| Scheme | Example meaning | Things to note |
| --- | --- | --- |
| `file` | Operating system's default file system | Present in the list, at the beginning |
| `jar` | ZIP/JAR filesystem (usually provided by the `jdk.zipfs` module) | May be absent in a trimmed runtime |
| `jrt` | Java runtime module image file system | Depends on runtime/JDK capabilities, not a regular disk drive |
| Custom scheme | Provider implemented by a library/application | Only usable when the provider is present and discovered by the appropriate loading mechanism |

The scheme name can be printed with `provider.getScheme()`. **A scheme is a type of resource address, not a path or filesystem instance**. For example, two ZIPs can share the provider with scheme `jar` while still being two different `FileSystem` instances.

Do not assume every machine has the exact three schemes `file`, `jar`, `jrt`; a program should only rely on the providers discovered in the running runtime.

### Standalone Java 17+ example: discovering providers

Save to the file `InstalledProvidersDemo.java`:

~~~java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.spi.FileSystemProvider;
import java.util.List;

public class InstalledProvidersDemo {
    public static void main(String[] args) {
        FileSystem defaultFs = FileSystems.getDefault();
        List<FileSystemProvider> providers =
                FileSystemProvider.installedProviders();

        System.out.println("Default scheme: "
                + defaultFs.provider().getScheme());
        System.out.println("Path.of uses default: "
                + (Path.of("sample.txt").getFileSystem() == defaultFs));
        System.out.println("Default provider is first: "
                + (providers.get(0) == defaultFs.provider()));
        System.out.println("Provider count >= 1: "
                + (providers.size() >= 1));

        System.out.println("Installed schemes:");
        for (FileSystemProvider provider : providers) {
            System.out.println("  " + provider.getScheme());
        }
    }
}
~~~

Compile and run:

~~~bash
javac InstalledProvidersDemo.java
java InstalledProvidersDemo
~~~

The first part of stdout is consistent across JDKs following the API contract:

~~~text
Default scheme: file
Path.of uses default: true
Default provider is first: true
Provider count >= 1: true
Installed schemes:
~~~

**After the line `Installed schemes:`, the number of lines and scheme names depend on the runtime.** The `file` scheme comes first in the list; a full JDK usually also has `jar` or `jrt`. Because the list varies, there is no fixed complete stdout valid for all environments.

Output analysis:

- `Path.of("sample.txt")` gets its provider from the default filesystem, so the `FileSystem` object comparison prints `true`; the file `sample.txt` does not need to exist.
- `installedProviders().get(0)` is the default provider per the API contract; this does **not** prove there is only one provider.
- The loop prints the schemes that actually exist; you should not write check logic by comparing against a fixed list.

## 4. How are providers loaded?

NIO.2 uses the **service provider** mechanism to allow additional implementations. A provider conforms to the `java.nio.file.spi.FileSystemProvider` contract; the Java environment can discover implementations that are properly packaged/declared when the provider is installed.

At the application level, the conceptual flow is:

1. The default provider serves the process's file system.
2. The runtime discovers additionally installed providers via Java's service loading mechanism and built-in JDK providers.
3. `FileSystemProvider.installedProviders()` lets you enumerate those providers.
4. When asked to create/open a `FileSystem` by URI or resource, the API selects a provider capable of handling it.
5. The provider creates/returns a `FileSystem`; from this filesystem, `Path` objects are created.

Simply **having a provider class in a JAR** is not enough to guarantee `installedProviders()` sees it: it also depends on service declarations, modules, class loaders, and how the runtime starts up. For libraries using the Java Platform Module System, a provider can be declared with `provides ... with ...`; for JARs using the traditional service mechanism, provider information lives in `META-INF/services/java.nio.file.spi.FileSystemProvider`. If the runtime image is built with `jlink`, the provider list may differ from a development JDK.

Besides the installed providers visible to the global list, some overloads of `FileSystems.newFileSystem` support selecting a provider via a passed-in class loader. Therefore, the global installed list is not proof that **every** provider implementation loadable under every class loader has been listed.

### Can you call `newFileSystem` directly on a provider?

Yes, a `FileSystemProvider` object has SPI methods such as `newFileSystem(URI, Map<String, ?>)`, `getFileSystem(URI)`, and `getPath(URI)`. However, ordinary application code should prefer the `FileSystems`/`Path`/`Files` facade classes because they centralize provider selection and path operations.

Do not instantiate a `FileSystemProvider` manually via reflection just because you see the class on the classpath: behavior and configuration depend on the implementation, and not every provider is designed to be instantiated directly as an application object.

## 5. When does Java choose the default provider, and when does it choose another provider?

| Expression | How filesystem/provider is chosen | Purpose |
| --- | --- | --- |
| `FileSystems.getDefault()` | JVM's default filesystem | Obtain the default file system |
| `Path.of("folder/file.txt")` | Default filesystem | Create a path from strings in the default file system |
| `FileSystems.getDefault().getPath("x.txt")` | The default filesystem itself | Create a path belonging to a known `FileSystem` |
| `Path.of(uri)` | Provider supporting the URI's scheme | Obtain a path via URI; the provider may require an already-open `FileSystem` |
| `FileSystems.getFileSystem(uri)` | Provider matching the URI scheme | Retrieve an existing/registered filesystem; **not** used to create a new one |
| `FileSystems.newFileSystem(uri, env)` | Appropriate provider for the URI scheme | Create/open a new filesystem according to the provider's contract |
| `existingFs.getPath("entry")` | `existingFs` itself | Create a path in an existing file system |

An installed scheme **does not guarantee** that `getFileSystem(uri)` will succeed. For example, with a ZIP filesystem, you may first have to create/open an instance with `newFileSystem`. `getFileSystem` can throw `FileSystemNotFoundException` if no matching filesystem exists yet; `newFileSystem` can throw `ProviderNotFoundException` when no provider handles the requested URI type.

`Path.of(uri)` can also fail if the appropriate provider does not yet have a ready filesystem; that is why once you have a `FileSystem`, using `fs.getPath(...)` is the most direct and clear approach.

**Do not convert a `Path` to a string and call `Path.of(String)` if you want to preserve the original provider.** Doing so always routes the new name to the default filesystem and can lose its meaning when the source belongs to a ZIP/JAR or virtual filesystem.

## 6. Practicing with the `jar` provider: installing and opening a filesystem are two separate steps

On a full JDK with `jdk.zipfs`, the provider with scheme `jar` allows opening a ZIP/JAR file as a filesystem. The program below checks for the `jar` provider itself before creating a ZIP, because a stripped-down Java runtime might not supply this provider.

Save as `ZipProviderDemo.java`:

~~~java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.spi.FileSystemProvider;
import java.util.Map;

public class ZipProviderDemo {
    public static void main(String[] args) throws Exception {
        boolean jarInstalled = FileSystemProvider.installedProviders()
                .stream()
                .anyMatch(provider ->
                        provider.getScheme().equalsIgnoreCase("jar"));

        if (!jarInstalled) {
            System.out.println("ZIP provider unavailable");
            return;
        }

        Path zipFile = Files.createTempFile("nio2-demo-", ".zip");
        Files.delete(zipFile); // Let the provider create a valid ZIP from scratch.

        try {
            URI zipUri = URI.create("jar:" + zipFile.toUri());

            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                Path entry = zipFs.getPath("/hello.txt");
                Files.writeString(entry, "Hello ZIP");

                System.out.println("ZIP scheme: "
                        + zipFs.provider().getScheme());
                System.out.println("Same as default: "
                        + (zipFs == FileSystems.getDefault()));
                System.out.println("Content: " + Files.readString(entry));
            }
        } finally {
            Files.deleteIfExists(zipFile);
        }
    }
}
~~~

Run:

~~~bash
javac ZipProviderDemo.java
java ZipProviderDemo
~~~

If an appropriate `jar` provider is installed and the environment permits creating/deleting temporary files, stdout is:

~~~text
ZIP scheme: jar
Same as default: false
Content: Hello ZIP
~~~

If the `jar` provider is absent, stdout is:

~~~text
ZIP provider unavailable
~~~

Read the mechanism carefully:

1. `installedProviders()` checks for *installed* providers. This check does not open any ZIP.
2. `Files.createTempFile` followed by `Files.delete` ensures we have a temporary location without a ZIP yet, while `"create" = "true"` tells the ZIP provider to create a new archive.
3. `FileSystems.newFileSystem(zipUri, Map.of("create", "true"))` hands the `jar`-scheme URI to the ZIP filesystem provider; this is when the `FileSystem` instance is opened.
4. `zipFs.getPath("/hello.txt")` creates a `Path` inside the ZIP, not the file `/hello.txt` on the default filesystem.
5. `Files.writeString` and `Files.readString` route I/O through the `Path`'s provider.
6. `try-with-resources` closes the ZIP filesystem and finishes writing the archive contents; `finally` deletes the temporary ZIP even if an error occurs.

The outer ZIP file (`zipFile`) is a `Path` belonging to the default filesystem, whereas the entry (`entry`) is a `Path` belonging to the ZIP filesystem. Both participate in the same example but do **not** belong to the same filesystem.

If the runner has restricted permissions for writing temporary files, is missing the ZIP module, or has a provider that behaves differently from the standard JDK ZIP provider, the program may throw an exception. Actual exception handling should be adapted to the environment.

## 7. Relationship between URI scheme, provider, and filesystem

A URI can carry indicators for selecting a provider:

~~~text
file:///home/user/data.txt
jar:file:///home/user/archive.zip!/docs/readme.txt
jrt:/java.base/java/lang/String.class
~~~

These are **examples of URI shapes**, not paths guaranteed to exist on the running machine.

- `file:` typically uses the default provider, though the URI must be valid according to OS path rules.
- `jar:` describes a resource related to a ZIP/JAR archive, typically using the ZIP provider. The part before `!` identifies the archive; the part after identifies the entry.
- `jrt:` represents a resource of the Java runtime image via the JRT filesystem when that provider is supplied.

The scheme answers **which provider can handle it**, while `FileSystem` answers **which instance contains the path**. Distinguish them carefully:

~~~text
Scheme "jar"
    │
    ▼
ZIP FileSystemProvider
    ├── opened archive A → FileSystem A → Path "/docs/readme.txt"
    └── opened archive B → FileSystem B → Path "/docs/readme.txt"
~~~

Two `Path` objects can print as the same string yet have different `FileSystem` objects and contain completely different data. Therefore, inspect `path.getFileSystem()` and `path.getFileSystem().provider()` to understand their origin.

**Do not arbitrarily concatenate `"jar:"` or filesystem paths using generic rules.** Building URIs requires paying attention to encoding special characters, separators, and provider syntax; `zipFile.toUri()` in the example provides an already properly escaped URI for the archive on the default file system.

## 8. Common mistakes and how to handle them

### Assuming a provider is present on every JDK

**Wrong:** assuming by default that `jar`, `jrt`, or a third-party provider is always installed.

**Right:** check `FileSystemProvider.installedProviders()` or handle `ProviderNotFoundException` when creating a filesystem, and make the application's runtime/module requirements explicit.

### Confusing installing a provider with opening a filesystem

**Wrong:** seeing `jar` in the list and immediately calling `FileSystems.getFileSystem(uri)` to retrieve an unopened archive.

**Right:** use `FileSystems.newFileSystem(...)` according to the provider's contract when opening a new instance. `getFileSystem(uri)` is only appropriate when the corresponding filesystem already exists; once created, it may need to be closed at the right time and duplicate opens avoided.

### Using `Path.of(String)` for paths inside a ZIP

**Wrong:**

~~~java
Path entry = Path.of("/docs/hello.txt");
~~~

This is a path on the default filesystem, regardless of whether the application has an open `zipFs`.

**Right** (when `zipFs` is already open):

~~~java
Path entry = zipFs.getPath("/docs/hello.txt");
~~~

These two snippets only illustrate individual statements, not standalone programs.

### Forgetting the lifecycle of additionally opened file systems

A `Path` can still exist as an object after its `FileSystem` is closed, but I/O operations on it may throw `ClosedFileSystemException`. For newly opened filesystems, use `try-with-resources` and ensure `Path` is used while the filesystem remains open. Conversely, do not close the default filesystem as if it were a temporary resource.

### Mixing `Path` objects from different providers in name operations

`resolve(Path)` or `relativize(Path)` are not APIs for transferring files between filesystems. Some implementations throw `ProviderMismatchException` if you combine arguments from incompatible providers. When you need to transfer data, consider `Files.copy(source, target)` with two paths created on their proper source/target filesystems, and handle `IOException` and provider capabilities/support.

### Thinking `installedProviders()` is a map of all drives and archives

The API returns **provider types**, not a listing of drives, mount points, open ZIPs, existing files, or resources inside each file system. To inspect the root directories of a specific filesystem, use `fileSystem.getRootDirectories()`; to check files, use `Files.*` APIs on a `Path`.

## 9. Practice exercises

1. Run `InstalledProvidersDemo` in two different Java environments (for example a full JDK and a packaged runtime). Compare the schemes at the end of stdout; explain why the number of providers can change.
2. Replace `Path.of("sample.txt")` with `FileSystems.getDefault().getPath("sample.txt")` and verify the relationship `getFileSystem() == FileSystems.getDefault()`.
3. In `ZipProviderDemo`, print `zipFile.getFileSystem().provider().getScheme()` and `entry.getFileSystem().provider().getScheme()` before closing the ZIP. Predict the result (`file` and `jar` if the provider is present).
4. Try using `zipFs.getPath("another.txt")` to create a second entry, then read it back with `Files.readString`. Check when you need to create parent directories if an entry resides in a subdirectory.
5. Explain why `installedProviders()` returning `jar` is still not enough to conclude that `FileSystems.getFileSystem(uri)` will return the filesystem of a ZIP that has never been opened.

## 10. Remember

- `FileSystems.getDefault()` provides **one default file system**; `Path` instances created from strings via `Path.of` belong to that system.
- `FileSystemProvider.installedProviders()` lists the **installed providers** in the runtime; the default provider appears first in the list, while other providers may vary across environments.
- **Provider → FileSystem → Path** is the core relationship. The scheme identifies the provider type, `FileSystem` is the instance, and `Path` belongs to a specific instance.
- `FileSystems.newFileSystem(...)` is used to open/create a filesystem when supported by the provider; `getFileSystem(...)` is used to look up an existing filesystem.
- Do not assume every path is a disk path; keep each `Path` paired with its `FileSystem`, check the provider when needed, and close additionally opened filesystems according to their lifecycle.
