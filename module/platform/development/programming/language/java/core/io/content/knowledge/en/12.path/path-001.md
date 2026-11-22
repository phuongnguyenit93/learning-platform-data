# Creating a Path with Path.of, Paths.get, and FileSystem in Java Core I/O

> **Context:** Java Core → I/O → **Path**. This lesson distinguishes the three ways to create a `java.nio.file.Path` object: `Path.of(...)`, `Paths.get(...)`, and `FileSystem.getPath(...)`; it explains the default file system, file system providers, URI handling, paths inside a ZIP archive, safe path manipulation, and API selection by JDK version. Complete examples compile/run with Java 17 unless noted otherwise.

## 1. What is Path? Creating a Path does not mean creating a file

`Path` in package `java.nio.file` represents **the identifying location of a path within a specific file system**. It describes the file/directory name structure understood by the **file system provider**: name components, root, relative or absolute path, how to join/normalize, and how to convert.

Example:

~~~java
import java.nio.file.Path;

Path report = Path.of("reports", "2026", "summary.csv");
~~~

This is a **fragment** placed inside a method. It creates a relative `Path` object pointing to the logical location `reports/2026/summary.csv` on systems using the `/` separator; on Windows, the representation returned when calling `toString()` may differ. **The statement above does not create a directory or file, does not check whether the file exists, and does not open an I/O handle**.

To interact with the actual filesystem, use `java.nio.file.Files`, such as:

~~~java
// Fragment: path is a valid Path; the method handles IOException.
boolean exists = Files.exists(path);
Files.createDirectories(path.getParent());
Files.writeString(path, "Hello", StandardCharsets.UTF_8);
~~~

The fragment needs to import `java.nio.file.Files` and `java.nio.charset.StandardCharsets`. **Do not equate** creating a `Path` (purely representational) with creating a file via `Files.createFile(...)`, creating directories via `Files.createDirectories(...)`, or opening a stream.

### What role does FileSystem play?

A `FileSystem` is the environment that interprets `Path` instances. The **default** file system typically reflects the file system on which the JVM is running; another provider may represent a ZIP/JAR file, a virtual filesystem, or external storage (if an appropriate provider is present).

~~~text
String / URI
    |
    +--> Path.of("...", "...") -----------+
    |                                     |
    +--> Paths.get("...", "...") ---------+--> default FileSystem --> Path
    |                                     |
    +--> FileSystems.getDefault()
              .getPath("...", "...") -----+

    +--> Another FileSystem (e.g. ZIP)
              .getPath("/docs/file.txt") ----> Path belonging to the ZIP FileSystem

Path + Files API --> actual operations on the corresponding filesystem
~~~

`Path` does not itself hold all file data; `Files` delegates file operations to the path's provider. Therefore, with the same `getPath` syntax, a path on disk and a path **inside a ZIP** can represent two different spaces.

## 2. Three Path creation APIs and their relationship

| API | Since JDK | File system environment | When to choose? |
| --- | --- | --- | --- |
| `Path.of(String first, String... more)` | **Java 11** | Default FileSystem | Concise choice for Java 11+ applications using the default filesystem. |
| `Paths.get(String first, String... more)` | **Java 7** | Default FileSystem | Source compatibility with Java 7/8 and legacy codebases; still valid on newer JDKs. |
| `FileSystems.getDefault().getPath(String first, String... more)` | **Java 7** | Explicitly specified Default FileSystem | When you want to explicitly state the default provider or already have a FileSystem variable. |
| `someFileSystem.getPath(String first, String... more)` | **Java 7** | The FileSystem is `someFileSystem` itself | When building a path **inside a ZIP** or custom provider, without assuming the default filesystem. |
| `Path.of(URI uri)` | **Java 11** | Provider found via the URI **scheme** | Convert an appropriate URI (e.g. `file:`) into a Path when a provider exists. |
| `Paths.get(URI uri)` | **Java 7** | Provider by URI | Older API equivalent in purpose to the above, useful when Java 8 is required. |

Key point: `Path.of(String, String...)` and `Paths.get(String, String...)` on Java 11+ create a `Path` using the **default FileSystem**; the modern implementation of `Paths.get` delegates to `Path.of`. There is no "faster" mechanism worth choosing solely because of the name. Choose based on **minimum JDK**, clarity, and reusability with other filesystems.

### 2.1. `Path.of("...")`

~~~java
Path file = Path.of("data.txt");
Path nested = Path.of("input", "archive", "2026.json");
Path absolute = Path.of(System.getProperty("user.home"), "notes.txt");
~~~

This is a fragment. `Path.of(first, more...)` requires `first` and optional `more` strings; non-empty components are joined according to the **rules of the default provider**. On Unix, `/` is typically used; Windows has drive syntax, UNC, and its own separator. The API does not require you to manually concatenate strings with `"/"` or `"\\"`.

**A path that looks absolute just because it has a long string is not necessarily valid on every OS.** For example, `Path.of("/tmp", "file.txt")` carries Unix root semantics, but on Windows it may be interpreted differently. Cross-platform code should obtain the root from configuration, a caller-supplied `Path`, or an environment API, and then use `resolve`.

### 2.2. `Paths.get("...")`

~~~java
import java.nio.file.Path;
import java.nio.file.Paths;

Path a = Paths.get("docs", "readme.md");
Path b = Path.of("docs", "readme.md"); // Available only since Java 11.
System.out.println(a.equals(b));     // true with the default provider.
~~~

If the project must run/compile with Java 8, use only `Paths.get` and do not write `Path.of`. Conversely, a Java 17 application can use either; `Paths.get` **has not been removed** from Java SE.

### 2.3. `FileSystem.getPath("...")`

~~~java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

FileSystem defaultFs = FileSystems.getDefault();
Path document = defaultFs.getPath("docs", "readme.md");
~~~

Also a fragment. The important effect is that the **FileSystem source can differ from default**:

~~~java
// Fragment: zipFs is a FileSystem opened from the ZIP provider.
Path member = zipFs.getPath("/docs", "readme.md");
~~~

The `member` Path represents an entry inside the ZIP, **not** the `/docs/readme.md` file on the host disk. APIs such as `Files.exists(member)` and `Files.readString(member)` will use that ZIP filesystem's provider.

**Avoid a common mistake:** receiving a `Path root` supplied by the caller, yet calling `Path.of("child.txt")` inside the method and assuming it is on the same filesystem as `root`. `Path.of` uses the default, whereas `root` may belong to a ZIP or another provider. You should use `root.resolve("child.txt")` or `root.getFileSystem().getPath(...)` depending on the intended semantics.

## 3. Standalone example: comparing the three factories on the default file system

Create the file **`PathFactoriesDemo.java`**:

~~~java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.Paths;

public class PathFactoriesDemo {
    public static void main(String[] args) {
        Path modern = Path.of("docs", "guide.md");
        Path legacy = Paths.get("docs", "guide.md");
        Path fromFs = FileSystems.getDefault()
                .getPath("docs", "guide.md");

        Path messy = Path.of("docs", ".", "draft", "..", "guide.md");

        System.out.println("equivalent="
                + (modern.equals(legacy) && modern.equals(fromFs)));
        System.out.println("relative=" + !modern.isAbsolute());
        System.out.println("names=" + modern.getNameCount());
        System.out.println("filename=" + modern.getFileName());
        System.out.println("parent=" + modern.getParent().getFileName());
        System.out.println("normalized=" + messy.normalize().equals(modern));
        System.out.println("uriRoundTrip="
                + Path.of(modern.toAbsolutePath().toUri())
                    .equals(modern.toAbsolutePath()));
    }
}
~~~

Run:

~~~bash
javac --release 17 PathFactoriesDemo.java
java PathFactoriesDemo
~~~

**Verified stdout:**

~~~text
equivalent=true
relative=true
names=2
filename=guide.md
parent=docs
normalized=true
uriRoundTrip=true
~~~

Because the example only prints structural facts and boolean comparisons, without printing `Path.toString()` containing the platform separator, stdout is designed to be consistent across typical default file systems. This is a demonstration with a simple valid path; results may differ on an unusual default provider with different naming rules.

Explanation:

1. The three calls all receive the names `docs` and `guide.md` on the default FileSystem, so the corresponding Paths are equal.
2. `isAbsolute()` returns `false` for a path without a root.
3. `getNameCount()` counts the number of name components, **not** the number of bytes, existing directories, or slashes. `getFileName()` retrieves the last component.
4. `normalize()` removes `.` and resolves name + `..` pairs **lexically**. It does not verify that the path actually exists.
5. `toAbsolutePath().toUri()` converts to a file URI; `Path.of(uri)` reconstructs the Path via the appropriate provider. Round-tripping with the default provider is guaranteed according to the `Path` Javadoc within the same JVM under the conditions stated there.

## 4. Relative and absolute paths

A `Path` can be **relative** or **absolute**:

- `Path.of("data", "users.csv")`: relative; interpreted in the context of the default directory when used for I/O.
- `Path.of("data", "users.csv").toAbsolutePath()`: creates a corresponding absolute path according to the provider, typically based on the process working directory.
- `Path.of("data", "users.csv").toRealPath()`: attempts to query the real filesystem to determine the real path; requires the file to exist and to be accessible. By default it can resolve symbolic links; the `LinkOption.NOFOLLOW_LINKS` option changes how links are handled.
- `Path.of(".").toAbsolutePath().normalize()`: commonly used to inspect the working directory as a lexically simplified absolute path.

Do not hard-code an absolute path like `C:\data\...` or `/home/worker/...` for every OS. The value of `user.dir` is a JVM property that typically reflects the working directory at launch; do not write programs that rely on changing `System.setProperty("user.dir", "...")` to control all relative path operations at runtime.

### 4.1. `toAbsolutePath()` is not `toRealPath()`

| API | Queries whether file exists? | Removes `.` / `..`? | Resolves symbolic links? |
| --- | --- | --- | --- |
| `toAbsolutePath()` | Does not need to check existence | Does not necessarily remove all redundant components | Does not perform symlink resolution |
| `normalize()` | No | Yes, **lexical** per Path rules | No |
| `toAbsolutePath().normalize()` | No | Yes | No |
| `toRealPath(...)` | May perform filesystem I/O and requires the path to exist | Returns real/absolute path per provider contract | May resolve symlinks by default; `NOFOLLOW_LINKS` changes behavior |

**Warning:** `normalize()` can sometimes **change the target a real path points to** if the path contains symbolic links. For example, a name preceding `..` might itself be a symlink to somewhere else; dropping the lexical pair may not be equivalent to actually traversing through the symlink. Do not use `normalize()` as complete proof that user-supplied data remains strictly inside an allowed directory.

### 4.2. `resolve`, `resolveSibling`, `relativize`

~~~java
// Fragment: base belongs to a specific FileSystem.
Path base = Path.of("app", "data");
Path child = base.resolve("users.csv");
Path sibling = child.resolveSibling("roles.csv");
Path relative = base.relativize(child);
~~~

When printed as text on Unix, these are typically represented as `app/data/users.csv`, `app/data/roles.csv`, and `users.csv`. To be portable, compare components or Path objects directly rather than comparing strings with fixed slashes.

- `base.resolve(other)` creates a path by appending `other` under `base` if `other` is a relative path; if `other` is an absolute path, the result depends on the provider's `resolve` rules (the default provider typically returns `other`).
- `resolveSibling(name)` replaces the last component with the new name in the same parent directory.
- `relativize(other)` constructs a relative path from this path to the other path; generally requires the same provider/FileSystem and the same absolute/relative status. Do not mix `absolute` and `relative` arbitrarily.
- Paths containing `..` need to be recomputed and semantically validated, especially with untrusted input.

## 5. Default FileSystem and arbitrary FileSystem

Obtaining the default filesystem:

~~~java
FileSystem fs = FileSystems.getDefault();
Path data = fs.getPath("data", "input.txt");

System.out.println(data.getFileSystem() == fs); // true
~~~

This is a fragment. `getDefault()` can be configured via a special default provider at JVM startup, but for most desktop/server applications, it is the OS file system. How it interprets absolute paths, separators, case sensitivity, and invalid names depends on the specific filesystem/provider.

A `FileSystem` also provides:

| API | Purpose |
| --- | --- |
| `getPath(first,more)` | Creates a path belonging to that same filesystem. |
| `getRootDirectories()` | Lists the roots known to the provider, not necessarily like `C:` drives on every OS. |
| `getSeparator()` | Name separator per provider; do not hard-code slashes to simulate a file system. |
| `getFileStores()` | The file stores exposed by the provider; information may change over time. |
| `getPathMatcher("glob:...")` | Creates a matcher for path names using glob/regex supported by the provider. |
| `isOpen()` | Checks whether a closable filesystem is open; the default is typically managed by the JVM. |
| `close()` | Releases resources of a **separately opened** filesystem; do not arbitrarily close the default filesystem. |

**Lifecycle:** `FileSystems.getDefault()` is managed by the JVM; the Javadocs state that the default filesystem cannot be closed, and calling `close()` on it throws `UnsupportedOperationException`. Conversely, `FileSystems.newFileSystem(...)` creates a separate filesystem such as ZIPFS and typically must be closed with try-with-resources to flush/release handles. After closing ZIPFS, `Path` instances belonging to that filesystem can no longer be used for Files I/O as they could while open.

## 6. Paths from URI: distinguishing Path from URL

There are two factory families that accept a `URI`:

~~~java
import java.net.URI;
import java.nio.file.Path;
import java.nio.file.Paths;

Path fromUri = Path.of(URI.create("file:///tmp/demo.txt")); // Java 11+.
Path oldStyle = Paths.get(URI.create("file:///tmp/demo.txt")); // Java 7+.
~~~

The example is a fragment illustrating a URI with the `file` scheme and a path syntax commonly seen on Unix operating systems; **it is not a portable snippet for a `C:` file on Windows**. With real data, prefer generating the URI from a Path on that same filesystem using `path.toUri()` and converting back if needed.

Do not write `Path.of("https://example.com/file.txt")` expecting to download a file over HTTP. The **String** overload creates a path on the **default filesystem**, whereas the **URI** overload looks up a provider by the URI's **scheme**. An `https` scheme does not have a built-in FileSystemProvider by default; `Path.of(URI.create("https://..."))` typically causes `FileSystemNotFoundException` or a corresponding provider error, and **does not download data over the network**. Use dedicated HTTP/URL client APIs for network access.

### 6.1. Does `Path.of(URI)` automatically create a new FileSystem?

Do not assume so. The contract of `Path.of(URI)` is to look up a FileSystemProvider matching the scheme and convert the URI into a Path; for schemes other than `file`, a provider may require the **FileSystem to already be mounted/opened** beforehand.

For example, with a URI pointing into a ZIP/JAR (of the form `jar:file:...!/entry`), you typically must open the corresponding file system using `FileSystems.newFileSystem(...)`, and then use `zipFs.getPath(...)` itself. Calling `Path.of(jarUri)` without an existing filesystem may result in `FileSystemNotFoundException`. Do not use `Paths.get(URI)` as a generic way to "auto-mount every kind of file".

Exceptions that may occur depending on the factory/provider: `InvalidPathException` for an invalid path string; `IllegalArgumentException` when the URI violates the required format; `FileSystemNotFoundException` when the filesystem does not yet exist; `ProviderNotFoundException` when no supporting provider exists; `SecurityException` or `IOException` on filesystem creation/opening APIs. Consult the specific overload documentation because not every exception is declared on every method.

## 7. Complete example: creating a Path in a ZIP FileSystem

A ZIP file can be opened as a separate filesystem if the runtime has a ZIP provider (typically the `jdk.zipfs` module on a standard JDK). `FileSystem.getPath("/docs", "readme.txt")` identifies an entry **inside the archive**, not a file of the same name on the host.

Create the file **`ZipPathDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipPathDemo {
    public static void main(String[] args) throws IOException {
        Path tempDir = Files.createTempDirectory("zip-path-demo-");
        Path zip = tempDir.resolve("sample.zip");

        try {
            // 'zip' does not exist yet; provider receives env create=true.
            try (FileSystem zipFs =
                     FileSystems.newFileSystem(zip, Map.of("create", "true"))) {

                Path member = zipFs.getPath("/docs", "readme.txt");
                Files.createDirectories(member.getParent());
                Files.writeString(member, "Hello ZIP",
                                  StandardCharsets.UTF_8);

                System.out.println("exists=" + Files.exists(member));
                System.out.println("content="
                        + Files.readString(member, StandardCharsets.UTF_8));
                System.out.println("defaultFs="
                        + (member.getFileSystem() == FileSystems.getDefault()));
            } // close zipFs: finalizes and releases ZIP resources.

        } finally {
            Files.deleteIfExists(zip);
            Files.deleteIfExists(tempDir);
        }
    }
}
~~~

Run command:

~~~bash
javac --release 17 ZipPathDemo.java
java ZipPathDemo
~~~

**Verified stdout on a JDK with a ZIP provider:**

~~~text
exists=true
content=Hello ZIP
defaultFs=false
~~~

**Key points:**

- `Files.createTempDirectory` creates a **real directory** on the default filesystem; this is I/O. The `sample.zip` file **does not exist yet**, allowing the `create=true` env option so the provider creates the archive. Do not pre-create an **empty ZIP file with zero bytes** and assume it is a valid ZIP archive.
- `FileSystems.newFileSystem(zip, Map.of("create", "true"))` since Java 13 opens the appropriate provider for the archive path, with the provider-specific `create` configuration. The `Map` parameter and this key name belong to ZIPFS, not a universal option required by all providers.
- `zipFs.getPath("/docs", "readme.txt")` creates a path **inside ZIPFS**; `Files.createDirectories(member.getParent())` and `Files.writeString(member,...)` operate through the corresponding provider.
- Upon exiting try-with-resources, `zipFs.close()` closes the filesystem; then `finally` deletes the archive and temporary directory on the default filesystem.
- If the JDK runtime has been stripped down and does not include the ZIP provider, `newFileSystem` may encounter `ProviderNotFoundException`. The goal of the example is file system semantics; do not assume ZIPFS is present in every minimized runtime.

### 7.1. Which approach to use if Java 8 support is required?

The `FileSystems.newFileSystem(Path, Map)` overload shown above is only available since Java 13. With Java 8/11, you can use the URI overload available since Java 7:

~~~java
// Java 8 fragment: zipFile is a Path to the ZIP archive location to open.
// A URI of the form jar:<file-uri> is used by the zipfs provider.
URI uri = URI.create("jar:" + zipFile.toUri());
Map<String, String> env = new HashMap<>();
env.put("create", "true");

try (FileSystem zipFs = FileSystems.newFileSystem(uri, env)) {
    Path member = zipFs.getPath("/docs", "readme.txt");
    // Operate inside ZIPFS ...
}
~~~

The snippet requires importing `java.net.URI`, `java.nio.file.Files`, `java.nio.file.FileSystem`, `java.nio.file.FileSystems`, `java.nio.file.Path`, `java.util.Map`, `java.util.HashMap` and being inside a method that handles `IOException`. In a real program, you must manage the archive and filesystem after completion. The ZIPFS provider condition still applies; this API does not create a provider if the runtime lacks one.

## 8. Portability: do not manually concatenate file path strings

Instead of:

~~~java
// Anti-pattern: manually concatenating separators locks in OS/provider assumptions.
String path = base + "/" + fileName;
~~~

use:

~~~java
// base is already a Path provided by the caller.
Path file = base.resolve(fileName);
~~~

**Advantages:** `resolve` keeps the path on the same provider as `base`, interprets the separator according to the provider, and avoids manually handling trailing slashes. However, `resolve` **does not guarantee** that `fileName` is safe, does not necessarily prevent an absolute path from overriding `base`, and does not create the file itself.

Windows-specific example: the string `"C:\\data\\report.txt"` has valid syntax on Windows, whereas on Unix the backslash is typically treated as a normal filename character. Similarly, `Path.of("/var/log/app.log")` is an absolute Unix path, not a default cross-platform design for Windows.

### 8.1. Do not use `Path.toString()` as an OS-independent interchange format

`path.toString()` is defined by the provider and is typically used for **display/debugging/logging**; do not treat it as a standard URL or portable interchange format between Windows and Linux. When you need to identify a resource by URI, use `toUri()` where the provider supports it and mind the associated FileSystem lifecycle. For internationalized JSON/config standards, define explicit conventions for separators, path roots, and string escaping.

In HTML/HTTP, `/` is a URL path delimiter, not synonymous with a filesystem separator. `URLDecoder` decodes form encoding with different semantics; do not blindly pass a decoded URL path into `Path.of(...)` and consider it safely sandboxed.

## 9. Creating a Path does not prove existence or that it is a regular file

~~~java
Path p = Path.of("notes", "todo.txt");
System.out.println(p.isAbsolute()); // false on typical default FS.
// Files.exists(p) may be false if the file has not been created yet.
~~~

Merely creating a Path does not throw `NoSuchFileException` because the file does not exist. When you want to perform actual operations, use `Files`:

| Goal | API | Notes |
| --- | --- | --- |
| Check existence | `Files.exists(path)` | `false` can also result when status cannot be determined under certain conditions; do not use it alone as a race-condition lock. |
| Read attributes | `Files.readAttributes(...)` | May throw IOException; depends on provider and permissions. |
| Create parent directories | `Files.createDirectories(path.getParent())` | Check `getParent() != null` when the path has only a filename. |
| Create new file, no overwrite | `Files.createFile(path)` | Executes create-if-absent per contract; may throw `FileAlreadyExistsException`. |
| Read text | `Files.readString(path, UTF_8)` | Java 11+, performs I/O with charset. |
| Write text | `Files.writeString(path, content, UTF_8)` | Java 11+, creates/writes file depending on options; does not auto-create parent. |
| Open byte stream | `Files.newInputStream(path)` | Caller is responsible for closing the result. |
| Traverse tree | `Files.walk(path)` | Returns lazy `Stream<Path>` that must be closed, as it may hold resources. |
| Canonical/real | `path.toRealPath()` | Performs I/O, requires path to exist, handles symlinks per options. |

`Files.exists` followed by `Files.createFile` still suffers from **time-of-check to time-of-use (TOCTOU)**: another actor can create/modify the file between the two operations. If you need atomic operations or permission protection, use an API with an appropriate contract such as `createFile` or the `CREATE_NEW` option, rather than relying on `if (!exists)` as the sole safety check.

## 10. Controlling paths from user input

A common example is uploading files into a fixed directory. If the filename comes from an HTTP request, you must not join it onto the root and allow `..` to escape the storage area.

Practical example **purely manipulating Path, without writing files**:

Create the file **`PathGuardDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathGuardDemo {
    public static void main(String[] args) {
        Path root = Path.of("store").toAbsolutePath().normalize();

        Path good = root.resolve("docs")
                .resolve("note.txt").normalize();

        Path bad = root.resolve("..")
                .resolve("outside.txt").normalize();

        System.out.println("inside=" + good.startsWith(root));
        System.out.println("outside=" + bad.startsWith(root));
    }
}
~~~

~~~bash
javac --release 17 PathGuardDemo.java
java PathGuardDemo
~~~

**Verified stdout:**

~~~text
inside=true
outside=false
~~~

Significance: after converting to absolute and **lexically** normalizing, `startsWith(root)` compares Path components, which is more reliable than `someString.startsWith("/root")` which can confuse `/rootA` with `/root`. Even so, **this is not a complete sandbox solution**, especially when the filesystem contains symlinks or other processes can modify the directory tree.

### 10.1. Limitations of lexical checks

For a genuine security boundary check, you must also consider:

1. **Is the input an absolute or relative path?** If a single filename is required, reject separators, `.`, and `..` per business policy; `Path.getFileName` can be helpful, though it does not automatically validate all inputs.
2. **Are there symlinks in the tree?** A path that is lexically inside `root` may actually lead outside if a component is a symbolic link. `toRealPath()` can help determine the current target, though races still exist.
3. **Are there races with other actors?** After checking but before opening, a symlink or directory entry may change. You need proper OS permissions, directories not modifiable by untrusted parties, or APIs such as `SecureDirectoryStream` when supported by the provider.
4. **Does the path belong to another filesystem/provider?** `root.resolve(other)` and cross-provider comparisons may not behave as expected. Keep child paths aligned with the exact filesystem of `root`.
5. **Are there Windows-specific rules?** Drive-relative paths, UNC, forbidden characters, case sensitivity, and normalization behavior can differ from Unix. Do not hard-code a single string check and assume it is safe across all platforms.

**Remember:** `normalize()` and `startsWith()` are useful for structural checks, but they do not prevent symlink traversal or TOCTOU without additional enforcement constraints.

## 11. Checking the relationship between FileSystems and Paths

A `Path` is not just a string. It is bound to its filesystem:

~~~java
Path path = Path.of("a.txt");
FileSystem owner = path.getFileSystem();
boolean defaultOwner = owner == FileSystems.getDefault();
~~~

The fragment on the default filesystem typically yields `defaultOwner == true`. For a path inside `zipFs`, `getFileSystem() == zipFs` is true instead.

Some operations may throw `ProviderMismatchException` or `IllegalArgumentException` when combining paths from different providers, depending on the API/provider (for example `relativize` between incompatible paths). `Files.copy(sourcePath, targetPath)` supports certain cross-provider operations under the Files contract, but it must not be equated with path-joining methods like `resolve/relativize`.

In a **reusable library**, Oracle's Javadoc for `Path.of(String,...)` notes that assuming the default FileSystem limits reusability. If a method is given a `Path base`, prefer building relative child names via `base.resolve(...)` rather than calling `Path.of(...)` at each step, especially when callers may pass a ZIPFS or virtual FS. For an API that only knows filename contents and needs to create a new path, it can accept an additional `FileSystem` from the caller.

## 12. Exception handling when converting String/URI to Path

Creating a Path from a string is generally a structural operation and can fail **immediately** if the name is invalid according to the provider:

~~~java
// Fragment: raw is a String taken from configuration/user input.
try {
    Path path = Path.of(raw);
    // Only upon reaching here do we know the string converts to a Path.
    // There is still no guarantee the file exists or is accessible.
} catch (java.nio.file.InvalidPathException ex) {
    // Return an appropriate validation error without leaking sensitive paths into logs.
}
~~~

Distinct scenarios:

- **`InvalidPathException`:** the string is not a valid path according to provider rules, e.g., forbidden characters or invalid structure.
- **`NoSuchFileException`:** typically appears when performing Files I/O on a nonexistent resource, **not** merely by calling `Path.of` for a name that does not exist yet.
- **`AccessDeniedException`/`IOException`:** permission or I/O errors when operating on a file/dir.
- **`FileSystemNotFoundException`/`ProviderNotFoundException`:** can occur when building a Path from a URI or opening a provider where no matching file system is found.
- **`ClosedFileSystemException`:** a path belonging to a closed file system is passed to provider-dependent operations.
- **`ProviderMismatchException`:** an API/provider detects a path belonging to an incompatible provider.
- **`SecurityException`:** some operations may involve permission checks in the corresponding environment.

**Do not replace all cases with `catch (Exception)` and assume simply recreating the Path is enough.** The path creation contract, nonexistent path errors, and read/write errors belong to different layers.

## 13. JDK version milestones to remember

| Milestone | Significance for this lesson |
| --- | --- |
| **Java 7** | NIO.2 introduced with `Path`, `Paths`, `FileSystems`, `Files`; use `Paths.get(...)` or `fs.getPath(...)`. |
| **Java 8** | Still does not have `Path.of`. Can use `Paths.get`, `Files.lines`, `Stream`, and `FileSystems.newFileSystem(URI,Map)`. |
| **Java 9** | Not the milestone that introduced `Path.of`; had other NIO/stream improvements, do not confuse them. |
| **Java 11** | Added `Path.of(String...)` and `Path.of(URI)`; added text I/O conveniences such as `Files.readString`/`Files.writeString`. |
| **Java 13** | Introduced the `FileSystems.newFileSystem(Path,Map)` overload used in the ZIPFS example. |
| **Java 17+** | All three ways of creating a Path and the ZIPFS overload in this lesson are available on a full JDK; code may still be constrained by the environment/specific provider. |

**If the build targets Java 8:** replace `Path.of(...)` with `Paths.get(...)` for the default provider or use `FileSystem.getPath(...)`; do not use `Files.readString/writeString` or `FileSystems.newFileSystem(Path,Map)`; replace those APIs with streams/readers and the corresponding URI overload. Use `javac --release 8` to verify source + available APIs rather than only changing `-source`/`-target` and assuming no newer API is called.

### API selection cheat sheet

~~~text
Java 11+ + default filesystem   → Path.of("dir", "file.txt")
Java 7/8 + default filesystem   → Paths.get("dir", "file.txt")
Already have Path base          → base.resolve("file.txt")
Already have FileSystem fs      → fs.getPath("dir", "file.txt")
Have valid URI + provider       → Path.of(uri) (Java 11+) / Paths.get(uri)
Need ZIP archive filesystem     → FileSystems.newFileSystem(...), then zipFs.getPath(...)
~~~

Do not pick `FileSystems.getDefault().getPath(...)` merely because the longer syntax looks "safer". It makes sense when you want to explicitly pass/select a file system; otherwise, Paths on the default provider created by the three main factories are generally equivalent.

## 14. Common mistakes and how to avoid them

1. **"Creating a Path means creating a file."** False: Path describes a location; `Files.createFile`/`Files.writeString` perform the I/O.
2. **"Path.of works starting from Java 8."** False: `Path.of` was added in Java 11; Java 8 uses `Paths.get`/`FileSystem.getPath`.
3. **"Paths.get has been removed."** False: still valid, very useful for legacy source and compatibility.
4. **"Path.of(String) and Path.of(URI) are the same."** False: String → default FS, URI → finds provider by scheme.
5. **"FileSystem.getPath is always the default FS."** False: it belongs to the specific FileSystem on which it is called, such as ZIPFS.
6. **"A Path inside a ZIP is a normal disk path."** False: `Path.getFileSystem()` is bound to the ZIP provider.
7. **"FileSystems.newFileSystem is a resource that doesn't need closing."** False for filesystems with handles like ZIPFS; close them properly with lifecycle management.
8. **"You can close the default FileSystem to free memory."** No: the default FS is managed by the JVM and cannot be closed via the API.
9. **"I use `/` so every Windows path is equivalent to Unix."** False: drives, UNC, separators, case sensitivity, and provider rules differ.
10. **"Path.toString is a URL."** False: it is a provider-specific representation; use `toUri` when an appropriate URI is needed.
11. **"normalize proves the file exists."** False: lexical, does not query the filesystem.
12. **"normalize followed by startsWith(root) is an absolute sandbox."** False: symlinks/races can still escape the scope.
13. **"toAbsolutePath checks the real file."** False: to get the canonical real path you need `toRealPath` with I/O semantics.
14. **"Files.exists then Files.createFile is atomic."** False: subject to TOCTOU; prefer an operation with an appropriate atomic contract.
15. **"resolve with a user-supplied name always stays under base."** False: absolute/`..` input can escape the root.
16. **"FileSystems only differ by slash character."** False: the provider determines URIs, roots, attributes, I/O capabilities, and lifecycle.
17. **"Any JAR URI passed to Path.of will auto-mount."** Not guaranteed: requires a provider and may require creating/opening the FileSystem first.
18. **"Path equality means two paths point to the same physical file."** Not always true: comparing Path objects differs from `Files.isSameFile`, which may query the filesystem, symlinks/hardlinks.
19. **"Just store the path string and reuse it on any machine."** May not be portable: root, name separator, encoding, provider, and permissions all depend on the environment.
20. **"A library receiving a base Path should create children with Path.of."** May use the wrong provider; prefer `base.resolve(...)`.

## 15. Self-check questions

1. Does `Path.of("hello.txt")` create a file on disk?
2. What are the similarities and differences between `Paths.get("a","b")` and `Path.of("a","b")`? Which API should Java 8 choose?
3. If the caller passes a `Path base` belonging to ZIPFS, why might `Path.of("child.txt")` be a bug?
4. Should `FileSystems.getDefault()` be closed using try-with-resources?
5. Does `Path.of("logs","app.log").toAbsolutePath()` require the file to exist? What about `toRealPath()`?
6. Does `Path.of(URI.create("https://example.com/x"))` download data over the network? Which other API is needed?
7. What type of filesystem does `Files.newFileSystem(zip, Map.of("create","true"))` in the demo create, and how must it be cleaned up?
8. Why can `normalize()` change the meaning of a path when symlinks are involved?
9. If `base.resolve(untrustedName)` is used for uploads, what checks besides `startsWith` are still needed?
10. Why does calling `Files.exists` right before `Files.createFile` not completely eliminate race conditions?
11. If a path belongs to a closed file system, what can happen with `Files.readString(path)`?
12. When writing reusable code for providers other than the default, should you accept `String`, `Path`, or `FileSystem` as a parameter?

**Suggested answers:**

1. No; you must call the Files API to create/write.
2. Both use the default FS for the string overload on JDK 11+; `Path.of` appeared in Java 11, while `Paths.get` has existed since Java 7 and works on Java 8.
3. `Path.of` takes the default FS, whereas `base.resolve` preserves the provider of `base`.
4. No, the default FS is managed by the JVM; `close()` is not supported.
5. `toAbsolutePath` does not check existence; `toRealPath` relies on the real filesystem and usually requires existence.
6. No; `Path.of(URI)` requires a provider for the scheme; use an appropriate HTTP client/network API.
7. A ZIP filesystem; close the `FileSystem` to commit/release handles, and clean up the archive file if it is only temporary data.
8. Lexically removing `name/..` can differ from the actual traversal through a symlink.
9. Validate absolute/relative status, `..` components, symlinks, TOCTOU, permissions, provider, and atomic file creation according to the threat model.
10. The two calls happen at two separate points in time; another actor can modify the filesystem in between.
11. It may throw `ClosedFileSystemException` when the provider requires an open filesystem.
12. Accept `Path base` if you need to resolve children, or `FileSystem` if you want the caller itself to decide the provider.

## 16. Official Java SE documentation

- [Oracle Java SE 21 — Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `of(String...)`, `of(URI)`, `resolve`, `normalize`, `toRealPath`, name component operations, and provider notes.
- [Oracle Java SE 21 — Paths](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Paths.html): `get(String...)` and `get(URI)`, default provider compatibility.
- [Oracle Java SE 21 — FileSystem](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html): `getPath`, separators, roots, lifecycle, and provider.
- [Oracle Java SE 21 — FileSystems](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): `getDefault`, `newFileSystem(URI,Map)`, `newFileSystem(Path,Map)`.
- [Oracle Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): creating/reading/writing files, actual operations, `exists`, `isSameFile`, directory streams.
- [Oracle Java SE 21 — InvalidPathException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/InvalidPathException.html): error when converting an invalid path string.
- [OpenJDK — ZIP File System Provider](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): ZIP/JAR context; when deploying ZIPFS, check module/provider availability on the runtime.

**Remember:** `Path.of` (Java 11+) and `Paths.get` (Java 7+) are convenient choices for the **default FileSystem**; `fs.getPath` creates a path in **that specific FileSystem**. Creating a `Path` does not create a file. When receiving a base Path from a caller, `base.resolve(child)` generally helps preserve the right provider; and when a path comes from a user, validate symlinks, permissions, and races before performing Files I/O.