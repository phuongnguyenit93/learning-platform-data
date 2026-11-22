# URI, Path.toUri(), and conversion limits across FileSystemProviders in Java

`java.nio.file.Path` represents a path according to **the rules of a file system**. `java.net.URI` represents a **resource identifier with a scheme** such as `file:`, `jar:`, or `https:`. In Java NIO.2, `Path.toUri()` can convert a path into a URI defined by that path's provider; `Path.of(URI)` or `Paths.get(URI)` goes in the reverse direction **only if a matching `FileSystemProvider` exists and the provider's conditions are met**.

Three things to remember:

1. `Path.toUri()` **does not create a file**, does not open a resource, and does not promise every URI is `file:`.
2. `Path.of(uri)` **is not a URL downloader or universal URI converter**. It requires a provider capable of interpreting the scheme and may require an open `FileSystem`.
3. Results and two-way conversion capability **depend on the provider**. A `file:` URI of the default filesystem differs from a `jar:` URI of a ZIP filesystem, and an `https:` URI normally cannot be used directly as a Java NIO `Path`.

This lesson uses Java 17+, focusing on `Path`, `URI`, `toUri()`, `Path.of(URI)`, `FileSystems`, `FileSystemProvider`, boundaries between providers, and confusing error cases.

## 1. Path and URI solve two different problems

| API | Model | Example | Key point |
| --- | --- | --- | --- |
| `Path` | Path **within a FileSystem** | `Path.of("docs", "guide.txt")` | Has its own provider, filesystem, root, and path rules |
| `URI` | Resource identifier with general syntax | `URI.create("https://example.com/a")` | Has scheme and URI components; not a local file by default |
| `Path.toUri()` | Converts `Path` to a provider-represented URI | `path.toUri()` | URI format and round-trip guarantees depend on the provider |
| `Path.of(URI)` | Asks a provider to interpret a URI into a `Path` | `Path.of(fileUri)` | May succeed or throw an exception |
| `FileSystemProvider` | Provider of path/file handling | Default provider, ZIP/JAR provider | Defines scheme, Path type, and access mechanism |

Diagram:

```text
                     +----------------------+
                     | Path                 |
                     | belongs to FileSystem A |
                     +----------------------+
                             |
                             | path.toUri()
                             v
                    URI (scheme depends on A)
                             |
                             | Path.of(uri)
                             | select provider by scheme
                             v
                Corresponding FileSystemProvider
                             |
                +------------+-------------+
                |                          |
         provider & filesystem       missing provider / closed
         can resolve URI             filesystem / invalid URI
                |                          |
                v                          v
            New Path             Exception / cannot convert
```

A `Path` object can exist even when the file does not yet exist, similar to `java.io.File`. A bare `URI` also does not confirm that a resource exists. Creating a `Path`/`URI` and writing data to a filesystem are separate actions.

### The familiar two-way conversion

```java
Path path = Path.of("docs", "hello.txt");
URI uri = path.toUri();
Path restored = Path.of(uri);
```

This is a snippet; it needs imports for `java.nio.file.Path` and `java.net.URI`. In the default filesystem, the generated URI typically carries the `file` scheme in absolute form. The resulting path corresponds to the **absolute** path, not necessarily equal to the original relative path string.

Do not write `Path.of(uri.toString())` instead of `Path.of(uri)`: the `String` overload interprets the string according to **OS path syntax**, without parsing the URI scheme; on Windows, `file:...` may be an invalid path, while on Unix it may be interpreted as an unintended name.

## 2. Path.toUri(): the result is an absolute URI, not necessarily an existing file

Signature:

```java
URI uri = path.toUri();
```

With the default provider, `toUri()` creates an **absolute** URI with the `file` scheme, representing an absolute path. Examples (illustrative only, dependent on OS and working directory):

```text
Relative path: docs/hello world.txt
On Unix it may become:    file:///home/user/project/docs/hello%20world.txt
On Windows it may become: file:///C:/work/project/docs/hello%20world.txt
```

Characteristics:

- `path.toUri().isAbsolute()` is `true` because the result has a scheme.
- `path.toUri()` **does not require a physical file to already exist**. You can convert a path to a name intended to be created in the future.
- With the default provider, a relative path is converted to its **absolute path** counterpart when creating the URI.
- Spaces, `#` characters, and certain special characters are **percent-encoded** as needed; for example, `hello #.txt` has the corresponding segment `hello%20%23.txt` in ASCII URI form.
- When the target can be determined to be a directory, the URI of a directory path under the default provider may end with `/`. Do not rely on a trailing `/` as the sole validation that a resource is a directory.
- This URI does not prove that the file exists, is readable, or is actually a regular file.

`Path.toUri()` creates a URI representation; it is not equivalent to `toRealPath()`. `toRealPath()` queries the real path on the filesystem and generally requires the resource to exist; `toUri()` provides no such guarantee.

### Example proving no file-creation I/O occurs

```java
Path missing = Path.of("never-created.txt");
URI uri = missing.toUri();
System.out.println(Files.exists(missing)); // Usually false if not yet created
```

This is a snippet importing `java.nio.file.*` and `java.net.URI`. The result of `exists` depends on the working directory, because a file of that name might already exist prior to running. The main point is: `toUri()` itself **does not call any file-creation API**.

## 3. Round-trip rules of the default filesystem

In Java SE 17, the default provider offers an important guarantee: when creating and using objects **within the same JVM**, converting `Path` → `URI` → `Path` via the default provider satisfies the idea:

```java
Path p = Path.of("docs", "hello.txt");
boolean same = Path.of(p.toUri()).equals(p.toAbsolutePath());
```

This is a snippet requiring `import java.nio.file.Path`. With the default provider per the Java contract, the result is `true` in the context where that guarantee applies. When `p` is initially **relative**, do not compare `Path.of(p.toUri())` directly with `p` and be surprised when `equals` returns `false`: the left side already carries an absolute path.

However, **this guarantee does not automatically apply to all other providers**. A provider may use custom URIs, require an already-open filesystem, or disallow reconstructing a path solely from an externally stored URI. Furthermore:

- `Path.equals` is generally a **structural Path/provider comparison**, not proof that two paths point to the same physical entity.
- `Files.isSameFile(p1, p2)` is a different API to test whether two paths share the same real file (it may touch the filesystem and throw `IOException`); it does not replace round-trip syntax.
- `toAbsolutePath()` is not `toRealPath()`. An absolute path may still contain representational components not resolved against real filesystem state.
- If passing a URI across different machines/OSes, a default URI string generated on Windows is not guaranteed to turn into the same `Path` on Linux, and vice versa.

Round-trip capability should be understood within the **contract of the specific provider and environment**, not as a promise that a URI can be attached to any arbitrary runtime.

## 4. URI is a schemed object; not all URIs are files

`URI` has distinct syntactic components, for example:

```text
https://example.com/docs/guide.html?lang=vi#intro
\___/  \_________/ \______________/ \_____/ \___/
scheme  authority         path         query fragment

file:///tmp/hello%20world.txt
\__/   \_____________________/
scheme          raw path

jar:file:///tmp/sample.zip!/docs/guide.txt
\_/  \_________________________________/
scheme       scheme-specific part
```

Useful `URI` methods:

| Method | Meaning |
| --- | --- |
| `getScheme()` | Scheme such as `file`, `jar`, `https` |
| `isAbsolute()` | Whether the URI has a scheme; different from `Path.isAbsolute()` |
| `isOpaque()` | Whether the URI is opaque or hierarchical |
| `getPath()` | **Percent-decoded** path for hierarchical URIs, or `null` if that component is absent |
| `getRawPath()` | Path retaining URI character escapes, or `null` |
| `getSchemeSpecificPart()` | Scheme-specific component (decoded form) |
| `toASCIIString()` | ASCII representation with appropriate escaping |
| `resolve(...)` | Resolves URI references according to **URI rules**, not `Path.resolve` |

An opaque URI like `jar:file:/...!/entry` typically has `getPath() == null`. Therefore, do not take `uri.getPath()` and pass it to `Path.of(...)` for arbitrary URIs. Do not manually strip `jar:`/`file:` via `substring(...)` or decode `%20` manually; URIs may contain delimiters carrying provider-specific meaning.

Example of a path containing `#`:

```java
Path p = Path.of("hello #.txt");
URI uri = p.toUri();
System.out.println(uri.getFragment()); // null for the URI generated for that filename
```

The `#` character **is inside the filename**, so `toUri` must escape it rather than interpreting it as a fragment. Conversely, if a programmer manually constructs `"file:///.../hello #.txt"` with `URI.create(...)`, the space makes the URI invalid and can throw `IllegalArgumentException`. Use `Path.toUri()` or appropriate `URI` constructors instead of assembling URIs from raw paths.

## 5. Path.of(URI) and Paths.get(URI): asking a provider to handle a URI

Two corresponding APIs:

```java
Path path1 = Path.of(uri);  // Java 11+
Path path2 = Paths.get(uri); // API available since Java 7
```

This is a snippet requiring `java.net.URI` and `java.nio.file.*`. Both rely on the **`FileSystemProvider` installation/discovery system** to handle the scheme. Do not assume they are only for `file:`, nor assume they automatically support every URI.

Logical flow:

1. Receive `URI`.
2. Inspect the scheme and select the matching provider.
3. Ask the provider to create a `Path` pointing into the corresponding filesystem.
4. The provider may return a Path or report that the URI is malformed, the filesystem does not exist, is not yet open, or the provider is not installed.

Exceptions that may occur (depending on situation/provider):

- `IllegalArgumentException`: the URI does not satisfy the provider's syntactic requirements or the argument is invalid.
- `FileSystemNotFoundException`: a matching filesystem cannot be found, such as a ZIP filesystem that has been closed or has not been initialized in a way the provider can look up.
- `ProviderNotFoundException`: a filesystem-creation operation cannot find a provider for the scheme per the relevant API's contract. Do not extrapolate that every `Path.of(URI)` call with a missing scheme necessarily throws this exact class.
- `SecurityException` or access exceptions may appear when security/access-control policy denies certain operations.

Do not write:

```java
Path remote = Path.of(URI.create("https://example.com/file.txt"));
```

and assume Java automatically downloads HTTP data. An `https:` URI is a web locator; standard Java NIO has no default HTTP filesystem provider that can interpret it directly as a `Path`. To download web content, use `HttpClient` or an appropriate network API, managing timeouts, HTTP errors, sizes, URL redirects, and security. After downloading, you can save it with `Files.write(...)` to a **separate** local Path.

**A valid URI does not guarantee conversion into a Path.** That is the design boundary between resource identifiers and filesystem namespaces.

## 6. Runnable Java 17+ example: file URI, escaped characters, and nonexistent paths

Create the file `PathUriDefaultDemo.java`:

```java
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathUriDefaultDemo {
    public static void main(String[] args) throws Exception {
        Path relative = Path.of("folder", "hello #.txt");
        URI uri = relative.toUri();

        System.out.println("scheme: " + uri.getScheme());
        System.out.println("URI absolute: " + uri.isAbsolute());
        System.out.println("path relative: " + relative.isAbsolute());
        System.out.println("escaped name: "
                + (uri.toASCIIString().contains("%20")
                && uri.toASCIIString().contains("%23")));
        System.out.println("fragment: " + uri.getFragment());
        System.out.println("round trip: "
                + Path.of(uri).equals(relative.toAbsolutePath()));

        Path root = Files.createTempDirectory("path-uri-");
        try {
            Path missing = root.resolve("not-created.txt");
            URI missingUri = missing.toUri();
            System.out.println("exists before: " + Files.exists(missing));
            System.out.println("same path: " + Path.of(missingUri).equals(missing));
            System.out.println("exists after: " + Files.exists(missing));
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Run:

```bash
javac PathUriDefaultDemo.java
java PathUriDefaultDemo
```

Stdout on a default filesystem with permission to create temporary directories, with no other actor modifying data between statements:

```text
scheme: file
URI absolute: true
path relative: false
escaped name: true
fragment: null
round trip: true
exists before: false
same path: true
exists after: false
```

Why is the output consistent even though absolute paths depend on the machine?

- It does not print the raw actual URI; it only checks scheme, absolute status, escaping of characters needing escapes, and round-trip equality.
- `relative` remains a relative Path, whereas `relative.toUri()` yields an absolute URI.
- The string `hello #.txt` contains a space and `#`. The URI has escapes `%20` and `%23`; no fragment appears.
- `Files.createTempDirectory` **actually creates a temporary directory**; conversely `missing.toUri()` and `Path.of(missingUri)` do not create `not-created.txt`.
- `Path.of(missingUri).equals(missing)` compares two absolute Paths on the same provider without requiring the file to exist.
- `finally` deletes the created temporary directory; the program does not rely on the dynamic value of the directory name for its output.

Only `Files.createTempDirectory` and `Files.deleteIfExists` modify the filesystem in this example. The `Path`/`URI` conversions create no resources.

## 7. What is FileSystemProvider?

`FileSystemProvider` in `java.nio.file.spi` is the extension point for file system types. The provider decides how to create filesystems, build Paths from URIs, read attributes, open channels, and perform file operations. Examples:

- The OS **default filesystem**: local paths, scheme typically `file`.
- **JDK ZIP/JAR filesystem provider** (when module `jdk.zipfs` is present): allows working with entries inside a ZIP/JAR as Paths, scheme `jar`.
- Third-party providers: may access in-memory filesystems, specialized data stores, virtual file systems, or other targets depending on implementation.

Calling `path.getFileSystem().provider().getScheme()` reveals the scheme of the provider owning `path`. However, knowing just the **scheme name** is not enough to guarantee a URI will reconstruct a Path from any process: it may also require installing the provider, configuring parameters, access permissions, registering a filesystem, or opening a connection.

Example:

```java
Path local = Path.of("hello.txt");
String scheme = local.getFileSystem().provider().getScheme();
// On common default filesystems: scheme is "file".
```

This is a snippet needing `java.nio.file.Path`. Scheme names vary across providers, and you cannot force every provider to use `file:/...` syntax or provide a URL accessible outside the JVM.

## 8. ZIP filesystem: one physical file with multiple Paths inside

An archive `sample.zip` can contain many entries such as `/notes/readme.txt`. With the ZIP filesystem provider, the following two kinds of Paths are very different:

```text
Default filesystem                        ZIP filesystem
----------------------------------        --------------------------------
Path.of("/tmp/sample.zip")                 zip.getPath("/notes/readme.txt")
  -> points to the physical archive        -> points to an entry *inside* the archive

file:///tmp/sample.zip                     jar:file:///tmp/sample.zip!/notes/readme.txt
scheme: file                               scheme: jar
```

The `jar:` URI (with an appropriate ZIP/JAR provider) contains both **the archive's URI** and **the entry's path**. The `!` symbol separates them according to ZIP/JAR provider syntax, not a universal rule for all URIs.

Therefore, you cannot take `URI.getPath()` of `jar:...` and assume it is a default filesystem path. A `jar:` URI is typically opaque, so `getPath()` is `null`. You must use the corresponding provider.

Important: `Path.of(jarUri)` can **fail even when the URI is well-formed**, if the ZIP FileSystem has not been opened/registered in a way the provider can look up. A ZIP archive existing on disk does not automatically make the FileSystem of its internal entries exist inside the JVM.

### Runnable Java 17+ example with ZIP filesystem

Create `ZipUriProviderDemo.java`:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipUriProviderDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("zip-uri-");
        Path archive = root.resolve("sample.zip");

        // ZIP filesystem URI: jar:<URI of the archive>
        URI zipFileSystemUri = URI.create("jar:" + archive.toUri());
        URI entryUri;

        try {
            // Open ZIP FS via URI so the provider registers it for lookup.
            try (FileSystem zip = FileSystems.newFileSystem(
                    zipFileSystemUri, Map.of("create", "true"))) {

                Path entry = zip.getPath("/lesson.txt");
                Files.writeString(entry, "hello", StandardCharsets.UTF_8);

                entryUri = entry.toUri();

                System.out.println("entry scheme: " + entryUri.getScheme());
                System.out.println("entry opaque: " + entryUri.isOpaque());
                System.out.println("provider scheme: "
                        + entry.getFileSystem().provider().getScheme());
                System.out.println("round trip while open: "
                        + Path.of(entryUri).equals(entry));
            }

            // FileSystem is closed; entry URI lookup may fail.
            try {
                Path.of(entryUri);
                System.out.println("round trip after close: available");
            } catch (FileSystemNotFoundException e) {
                System.out.println("round trip after close: unavailable");
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(root);
        }
    }
}
```

Run with JDK 17+ having the ZIP filesystem provider:

```bash
javac ZipUriProviderDemo.java
java ZipUriProviderDemo
```

Verified stdout on a JDK with `jdk.zipfs`:

```text
entry scheme: jar
entry opaque: true
provider scheme: jar
round trip while open: true
round trip after close: unavailable
```

Explanation:

1. `archive.toUri()` is the URI of the ZIP file in the **default** filesystem (`file:`).
2. `URI.create("jar:" + archive.toUri())` represents a ZIP filesystem that the `jar` provider can open.
3. `FileSystems.newFileSystem(zipFileSystemUri, Map.of("create", "true"))` creates/opens the ZIP filesystem; when the archive does not yet exist, the `create` option lets the provider create the archive per the ZIP provider's mechanism.
4. `zip.getPath("/lesson.txt")` is a Path **belonging to the ZIP filesystem**, not a `lesson.txt` file next to the archive on disk.
5. `entry.toUri()` has scheme `jar`; in this case the URI is opaque.
6. While the ZIP FileSystem is open/registered under its URI, `Path.of(entryUri)` can locate the entry Path again.
7. After `close()`, there is no longer a matching open filesystem; lookup can throw `FileSystemNotFoundException`. The physical ZIP file still existing **does not mean** the ZIP FileSystem remains open.

This example intentionally depends on the **built-in ZIP FileSystemProvider in the JDK**. Trimmed-module Java runtimes may lack `jdk.zipfs` and fail to run the ZIP portion; that itself illustrates provider limits.

**Advanced detail:** Opening a ZIP FileSystem via the `FileSystems.newFileSystem(Path, Map)` overload might not register that instance for `Path.of(jarUri)` lookups in the same way as the **URI** overload, depending on provider implementation. Therefore, do not assert that "filesystem is open" is the sole condition; how it was created and the lookup mechanism also matter.

## 9. Errors when converting URI to Path and how to handle them

### 9.1. Unsupported scheme

`URI.create("https://example.com/a")` is a valid URI, but it is not a URI for the default `file` or `jar` provider. `Path.of(...)` does not turn HTTP into a local file. If an application has a third-party provider supporting a given scheme, handling capability depends on that provider itself; do not hard-code assumptions across all runtimes.

### 9.2. Provider exists but FileSystem is not open

A ZIP entry URI such as `jar:file:///tmp/a.zip!/x.txt` requires the `jar` provider and an appropriate filesystem. When unopened, already closed, or registered differently, `Path.of(uri)` may throw `FileSystemNotFoundException`. The proper handling is to use `FileSystems.newFileSystem(...)`/`getFileSystem(...)` per the ZIP provider contract, **not** blindly switching the scheme to `file`.

### 9.3. URI violates provider requirements

For the default `file` provider, the URI generally must be a **hierarchical, absolute** file URI with an appropriate path and without arbitrary components like query/fragment; the authority must also conform to provider/platform rules. For instance, manually built URIs that fail these requirements can cause `Path.of(uri)` to throw `IllegalArgumentException`.

Do not manually assemble:

```java
URI bad = URI.create("file:///tmp/hello world.txt");
```

Because the space is unescaped in the raw URI string; `URI.create` throws `IllegalArgumentException` even before the Path step. A real path should be constructed with `Path.of(...)` and then converted via `toUri()` so Java handles escaping.

### 9.4. Different machines and different providers

A `file:///C:/...` URI can be a valid file path on Windows, but you cannot assume it will have the same meaning on another operating system. With third-party filesystems, round-trip capability in another JVM also depends on provider installation, filesystem state, and access configuration.

When handling URIs from outside the system, verify:

- The scheme is in an **allowlist** that the application genuinely supports.
- The provider is available, and the required filesystem/credentials have been initialized.
- The URI structure is valid for the provider; do not manually parse provider-specific syntax unnecessarily.
- The converted path does not violate allowed scope, access permissions, or application security policy.
- If you want to read the actual file, call `Files.newInputStream(...)`, `Files.readString(...)`, or an equivalent API and handle `IOException`; merely having a `Path` does not mean access succeeds.

### Example catching errors by case

```java
try {
    Path result = Path.of(uri);
    // result is only a Path; actual I/O operations still require separate handling.
} catch (FileSystemNotFoundException e) {
    // The provider could not find a matching open filesystem.
} catch (IllegalArgumentException e) {
    // The URI does not meet provider requirements / invalid input.
}
```

This is a **snippet**: it needs `java.net.URI`, `java.nio.file.*`; the `uri` variable already exists. If business logic uses a custom provider, you must also understand other exception types per the API/implementation. Do not swallow errors and pretend the URI is a local path.

## 10. File.toURI(), Path.toUri(), and URI.toURL()

APIs that are often mixed up:

| API | Input → output | When to use |
| --- | --- | --- |
| `new File(name)` | Path name → `File` | Working with the `java.io.File` API |
| `file.toURI()` | `File` → `URI` | Need a URI for a path in the legacy File model |
| `file.toPath()` | `File` → `Path` | Converting to NIO |
| `path.toUri()` | `Path` → `URI` | The Path's provider determines the URI format |
| `Path.of(uri)` | `URI` → `Path` | Only when a provider for the scheme and matching filesystem exist |
| `uri.toURL()` | `URI` → `URL` | Converts to a URL object if scheme/handler supports it; does not auto-read |
| `Path.of(uri.toString())` | URI string → raw path name | **Not** a proper URI conversion; avoid |

Example with the default filesystem:

```java
File legacy = new File("notes.txt");
URI legacyUri = legacy.toURI();

Path modern = legacy.toPath();
URI modernUri = modern.toUri();
```

The snippet requires `java.io.File`, `java.net.URI`, `java.nio.file.Path`. The two URIs may represent the same resource address, though you should not assume the string of every overload/API is always identical in all circumstances. When holding a `Path` from a non-default provider (such as ZIP), **`Path.toUri()`** reflects the provider owning the Path; forcing everything through `java.io.File` is not always supported (for example `Path.toFile()` may throw `UnsupportedOperationException` if the Path does not belong to the default filesystem).

If you need to read content over HTTP, `URI.toURL()`/`URL.openStream()` or `HttpClient` is a separate network layer, not equivalent to creating a `Path`. In modern code, `HttpClient` usually provides clearer management of timeouts, HTTP responses, and errors.

## 11. Why shouldn't you manually parse or assemble file URIs?

Suppose a filename contains spaces, `#`, `%`, or Unicode characters. Manually assembling:

```java
String text = "file://" + path.toString();
```

can produce an invalid URI because:

- `Path.toString()` uses the provider's separator/syntax; on Windows it may contain `\`, drive letters, or UNC, unsuitable for direct concatenation like a URL.
- `#` may be interpreted as a fragment rather than part of the filename.
- `%` may be interpreted as the start of an escape sequence; double-encoding manually also causes bugs.
- Opaque URIs of providers like `jar` have special structure; you cannot impose `file:` syntax on them.
- A relative path does not automatically become a properly formed absolute file URI.

Instead:

```java
Path path = Path.of("folder", "hello #.txt");
URI uri = path.toUri();
```

That is a snippet requiring `import java.nio.file.Path`, `java.net.URI`. If you must work with HTTP URI components, construct URIs using URI/URL syntax rather than using `Path` to build web URLs.

### getPath() and getRawPath() are not the same

`uri.getPath()` returns the path component with URI escapes decoded, whereas `uri.getRawPath()` retains escapes such as `%20`. Calling `URLDecoder.decode(...)` an extra time or taking the decoded string and writing it back into a URI improperly can cause **double decoding** or alter the meaning of special characters like `+`, `%`, and `#`.

When you need to convert a **real file URI** to a `Path`, use `Path.of(uri)`. When only displaying URI components, distinguish raw/decoded as needed. With the `jar` provider, `getPath()` may have no value because the URI is opaque.

## 12. Security, untrusted data, and filesystem scope

A URI or path received from an API/user is not automatically safe. Several cautions:

1. **Do not allow arbitrary schemes** if the application only supports `file`. Arbitrary schemes can trigger unexpected providers or access mechanisms.
2. **Do not treat `normalize()` as a complete security check**: it only processes syntactic `.`/`..` components and does not verify the real path. Symbolic links can alter the target.
3. If restricting within a root directory is required, validate and operate under an appropriate policy, considering `toRealPath()`/`Files.isSameFile` when needed and handling exceptions. Beware races between check time and open time.
4. Do not use `Files.exists(path)` as a guarantee that the file will still exist when read. The filesystem can change instantaneously.
5. Do not assume systems outside the JVM share the same provider or credential context. A virtual provider's Path does not necessarily have a local file representation.
6. A URI may be an **identifier**, not authorization to access. Successfully converting to a Path does not prove read/write permission.
7. When creating real resources, choose appropriate NIO operations such as `Files.createFile`, `Files.newInputStream`, `Files.writeString` with controlled options and exceptions.

Example of an application receiving external URIs that only allows `file`:

```java
if (!"file".equalsIgnoreCase(uri.getScheme())) {
    throw new IllegalArgumentException("Only file: URIs are supported");
}
Path path = Path.of(uri);
// Continue validating application scope/real path before opening I/O.
```

This is only a **scheme check**, not yet a complete security boundary for all file paths. Restricting access within a safe directory requires designing appropriate authorization and traversal/symlink/race-mitigation logic.

## 13. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Thinking `toUri()` creates a file | Concluding the resource already exists | `toUri()` only builds a URI; use `Files` when I/O is needed |
| Using `Path.of(uri.toString())` | The URI string is parsed as a raw path | `Path.of(uri)` |
| Assuming every `Path.toUri()` is `file:` | Wrong for ZIP/JAR/custom providers | Query the actual scheme/provider |
| Assuming every valid URI converts to a Path | Missing provider/filesystem | Convert only URIs supported by an NIO provider |
| Using `Path.of(httpsUri)` to download web files | Not an HTTP operation | Use a network API and save to a separate Path |
| Ignoring `FileSystemNotFoundException` for JAR URIs | Cannot find the required ZIP filesystem | Open/register the appropriate filesystem provider |
| Assuming an existing ZIP archive means ZIP FS is open | Entry URIs still cannot round-trip | Manage the `FileSystem` lifecycle |
| Calling `uri.getPath()` on `jar:` | May receive `null` | Use the provider; recognize opaque URIs |
| Manually joining `"file://" + path` | Broken escaping, slashes, Windows paths | `path.toUri()` |
| Treating `getPath()` and `getRawPath()` as identical | Broken percent-encoding | Distinguish decoded/raw |
| Comparing round-tripped Path directly against a relative Path | Wrong result due to absolute/relative | Compare per provider contract, using `toAbsolutePath()` |
| Thinking local round-trip is guaranteed on another machine | OS/provider differences | Rely only on guarantees within documented scope |
| Calling `toFile()` on a ZIP Path at any time | May throw `UnsupportedOperationException` | Use Files APIs directly on Path |
| Thinking having a Path means the file is readable | May not exist/lack permission | Perform I/O and handle `IOException` |
| Using `normalize()` as the sole traversal barrier | Misses symlinks/races | Design dedicated security checks |

## 14. Self-check quiz

1. **Does `Path.toUri()` create a physical file?** No; it only creates a URI representing the Path according to the provider.
2. **Is the URI of a relative Path on the default provider typically relative or absolute?** An absolute URI with scheme `file`, corresponding to the absolute path.
3. **Does `Path.of(uri)` support an `https:` URI by default as a local file?** No. It is an NIO provider operation, not an HTTP download.
4. **Why shouldn't `Path.of(path.toUri())` be compared directly with a relative path?** The round-trip result of the default provider corresponds to `path.toAbsolutePath()`.
5. **Why does the filename `hello #.txt` contain `%23` in its URI?** Because `#` must be escaped so it is not treated as a fragment.
6. **What is the typical scheme of a Path inside a ZIP FS?** `jar` when using the JDK ZIP filesystem provider.
7. **Why can `Path.of(jarUri)` throw `FileSystemNotFoundException`?** No open/registered ZIP filesystem matching the URI was found.
8. **Does a `jar:...` URI always have `getPath()`?** No; it is usually opaque, so `getPath()` returns `null`.
9. **If a ZIP FileSystem has been closed, does the physical archive file still exist?** It may still exist, but Path/URI lookup for entries requires the filesystem to be opened again.
10. **Does `Path.toFile()` work for a ZIP Path?** Not guaranteed; a Path outside the default filesystem can throw `UnsupportedOperationException`.
11. **Can `Path.of(uri.toString())` be used instead of `Path.of(uri)`?** No; the two overloads interpret inputs under two different models.
12. **How do you know whether a URI can become a Path?** Check the scheme/provider, filesystem conditions, and handle errors from `Path.of(URI)` per the provider contract.
13. **Does round-tripping confirm the file exists or is accessible?** No.
14. **Which API do you use to read the real file after obtaining a Path?** `Files.newInputStream`/`Files.readString` or an appropriate API, with I/O error handling.
15. **Is an external URI/Path safe merely because it has been normalized?** No; traversal, symlinks, permissions, and races still remain.

## Java 17 API references

- [`Path` — `toUri()`, `toFile()`, `toAbsolutePath()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html).
- [`Path.of(URI)` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#of(java.net.URI)).
- [`Paths.get(URI)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html).
- [`URI` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html).
- [`FileSystemProvider` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html).
- [`FileSystems` — `newFileSystem(...)` / `getFileSystem(...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html).
- [`FileSystemNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemNotFoundException.html).
- [`Files` — actual I/O operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [JDK ZIP File System Provider](https://docs.oracle.com/en/java/javase/17/docs/specs/zipfs.html).

**Conclusion:** `Path.toUri()` is the bridge from a path belonging to **a specific FileSystem** to a provider-defined URI. `Path.of(URI)` is a request to **the corresponding provider and FileSystem** to convert a URI back into a Path, not a tool to turn any URI into a file. With the default `file` provider there is a round-trip guarantee within the same JVM; with `jar`, ZIP, or third-party providers, you must account for scheme, how the filesystem is opened, lifecycle, and the provider's specific contract.