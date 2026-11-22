# Converting with File.toPath and Path.toFile in Java

## 1. Objectives and Scope

In Java, **`java.io.File`** is the file/directory path representation in the legacy I/O API; **`java.nio.file.Path`** is the path representation belonging to a `FileSystem` in the NIO.2 API (available since Java 7). A real-world project often encounters both: legacy libraries return `File`, while new code uses `Files`, `Path`, `DirectoryStream`, `FileChannel`, or `WatchService`.

The two direct bridges are:

- **`File.toPath()`**: converts a `File` into a `Path` belonging to the default file system.
- **`Path.toFile()`**: converts a `Path` belonging to the *default file system provider* into a `File`.

They allow reusing paths between old and new APIs without manually concatenating path strings:

~~~text
                    File.toPath()
java.io.File ------------------------------> java.nio.file.Path
              <------------------------------
                    Path.toFile()
        Paths on the default file system
~~~

You must grasp five limitations before applying them:

1. **Conversion does not create, open, move, or read a file.** It converts the path representation, performing no I/O operation on content.
2. **`Path.toFile()` cannot be used with every `Path`.** In particular, a `Path` created by a provider other than the default file system (e.g., a ZIP filesystem) may throw `UnsupportedOperationException`.
3. **Relative paths remain relative.** Conversion does not automatically call `toAbsolutePath()` or `toRealPath()`.
4. **Conversion does not normalize and does not confirm the file exists.** `..`, `.`, symbolic links, access permissions, and file status are separate concerns.
5. **When real operations are needed, choose the appropriate API.** For example, `Files.readString(path, UTF_8)`, `Files.size(path)`, and `Files.copy(...)` have their own behaviors and exceptions.

This lesson covers syntax, mechanics, conversion scenarios, provider limitations, path correctness, and standalone runnable Java 17 examples.

## 2. What Do File and Path Represent?

### 2.1. File Is an Abstract Pathname, Not an Open File

`java.io.File` represents an **abstract pathname** to a file or directory. Creating the object:

~~~java
File file = new File("data/report.txt");
~~~

does not create `data/report.txt` on disk; nor does it check whether the file exists. It is solely an object describing a path. Legacy methods such as `exists()`, `isFile()`, `length()`, `listFiles()`, `renameTo()`, and `delete()` perform the corresponding checks/operations, with their own return contracts and error handling.

`File` has existed since very early Java and appears in many APIs, for example:

~~~java
void uploadLegacy(File attachment);
File getLegacyConfigurationFile();
~~~

These are **illustrative signatures**, not a standalone runnable program. They remain valuable when integrating legacy libraries or interfaces requiring `File`.

### 2.2. Path Resides in NIO.2's FileSystem Model

`java.nio.file.Path` is an **interface** representing a path within a given `FileSystem`. For the default file system, you can create one using `Path.of(...)` (Java 11+) or `Paths.get(...)`:

~~~java
Path path = Path.of("data", "report.txt");
~~~

A `Path` provides operations for manipulating path components such as `getFileName()`, `getParent()`, `resolve()`, `relativize()`, `normalize()`, and `toAbsolutePath()`. Those operations usually only manipulate the path representation without reading file content.

An NIO file system can also come from another provider, such as a ZIP/JAR filesystem. This multi-provider capability explains why a `Path` cannot always be converted into a `File`.

### 2.3. `Files` Is Where Many NIO Operations Happen

`java.nio.file.Files` is a utility class with static methods that operate on `Path`:

~~~java
boolean regular = Files.isRegularFile(path);
long byteCount = Files.size(path);
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet assuming an existing `Path path`. Calls to `Files.size` and `Files.readString` can throw `IOException`; `Files.isRegularFile` reports results differently, and `false` does not necessarily distinguish "not a regular file" from "undetermined due to error." Converting `File` to `Path` before using `Files` merely supplies a path object of the right type; the conversion itself reads no data.

## 3. File.toPath(): Bringing Legacy APIs to Path

### 3.1. Basic Syntax

~~~java
import java.io.File;
import java.nio.file.Path;

File oldFile = new File("docs", "notes.txt");
Path path = oldFile.toPath();
~~~

`File.toPath()` returns a `Path` representing the same abstract pathname on the **default file system**. If `File` describes a relative path, the resulting `Path` is also relative. If `File` describes an absolute path, the corresponding `Path` is also absolute.

No file-open or I/O permission check occurs simply from using `toPath()`. Thus code can write:

~~~java
File missing = new File("not-created.txt");
Path missingPath = missing.toPath();
~~~

even when `not-created.txt` does not exist. That does not mean a subsequent read operation will succeed.

### 3.2. Converting to Use the Files API

A practical reason to call `File.toPath()` is to take advantage of newer APIs:

~~~java
File oldFile = obtainLegacyFile();
Path path = oldFile.toPath();

long size = Files.size(path);
byte[] bytes = Files.readAllBytes(path);
~~~

This is a **non-standalone illustrative snippet**: `obtainLegacyFile()` represents a real function in the application, and the enclosing method must declare or catch `IOException`. `Files.readAllBytes` holds all data in RAM; for large files, read via a stream rather than assuming enough memory is available.

Another practical use is retrieving metadata, moving, or copying:

~~~java
Path source = oldFile.toPath();
Path target = Path.of("archive", oldFile.getName());
Files.copy(source, target);
~~~

This is also an illustrative snippet. `Files.copy` can throw `IOException` if the destination file already exists, permissions are missing, the parent directory does not exist, or the source encounters an error. **`File.toPath()` does not prevent these exceptions.**

### 3.3. `toPath()` Does Not Mutate the File Object

After the call:

~~~java
Path path = oldFile.toPath();
~~~

the `oldFile` object remains a `File`; it is not converted "in place" and is not invalidated. `path` is a separate object describing the same path in the NIO model. You do not need to "convert back" to keep using legacy APIs on `oldFile`.

## 4. Path.toFile(): Integrating APIs Requiring java.io.File

### 4.1. Syntax

~~~java
import java.io.File;
import java.nio.file.Path;

Path path = Path.of("docs", "notes.txt");
File file = path.toFile();
~~~

`Path.toFile()` converts a path belonging to the **default file system** into a `java.io.File` object. For example, a third-party or older library accepting `File`:

~~~java
Path path = Path.of("reports", "daily.txt");
legacyProcess(path.toFile());
~~~

This snippet is illustrative; `legacyProcess(File)` is a hypothetical function provided by an application/library. Choose `toFile()` when a `File` is genuinely required; if all subsequent steps use NIO, there is no need to convert back and forth needlessly.

### 4.2. Do Not Blindly Call toFile() on Paths from Other Providers

A `Path` can belong to a ZIP filesystem, virtual filesystem, or another provider. `Path.toFile()` is entitled to throw `UnsupportedOperationException` if the `Path` is not associated with the default provider. Conceptual example:

~~~text
Default FileSystem:
    Path.of("logs", "app.log")      → toFile() is supported

ZIP/JAR FileSystem:
    zipFs.getPath("/entry.txt")     → toFile() is not supported
                                      (UnsupportedOperationException)
~~~

This is a model, not standalone Java commands. If you are using a ZIP filesystem, use `Files` APIs directly on that `Path` instead of trying to force it into a `File`. A path inside a ZIP file is not naturally a regular file on the default file system.

**Provider limitation is a key difference between the two conversion directions:** `File.toPath()` goes into the default filesystem; `Path.toFile()` does not guarantee turning every provider into a corresponding `File`.

### 4.3. Why Not Use new File(path.toString()) Instead of toFile()?

For a `Path` belonging to the default file system, `path.toFile()` clearly expresses type-conversion intent per the API. Manually calling:

~~~java
File file = new File(path.toString());
~~~

might look similar on the current machine, yet it **discards information about which `FileSystem` the `Path` belongs to** and creates no official bridge for other providers. For a `Path` from a ZIP filesystem, the string `"/entry.txt"` is an internal ZIP path; creating `new File("/entry.txt")` points to a path on the default filesystem instead, which has a completely different meaning.

Therefore, **do not use string conversion to fake provider support**. If an API only accepts `File`, data from another provider may need to be extracted to a temporary file on the default filesystem per application contract, or an API accepting `InputStream`/`Path` is needed to avoid extraction.

## 5. Java 17 Example: Round-Trip Conversion Using Relative Paths

Save the file **FilePathRoundTripDemo.java**:

~~~java
import java.io.File;
import java.nio.file.Path;

public class FilePathRoundTripDemo {
    public static void main(String[] args) {
        Path original = Path.of("data", "report.txt");
        File legacy = original.toFile();
        Path restored = legacy.toPath();

        System.out.println("Relative: " + !original.isAbsolute());
        System.out.println("Same path: " + original.equals(restored));
        System.out.println("Name: " + restored.getFileName());
        System.out.println("Absolute result: "
                + restored.toAbsolutePath().isAbsolute());
    }
}
~~~

Compile and run commands:

~~~bash
javac -encoding UTF-8 FilePathRoundTripDemo.java
java FilePathRoundTripDemo
~~~

Result on a typical default file system:

~~~text
Relative: true
Same path: true
Name: report.txt
Absolute result: true
~~~

Explanation:

- `Path.of("data", "report.txt")` constructs a relative path using OS syntax.
- `original.toFile()` provides a `File` for legacy APIs; `legacy.toPath()` converts back.
- `Path.equals` returns true here because both represent the same relative path on the default provider with matching component structure.
- `getFileName()` returns the last component of the path.
- `toAbsolutePath()` creates an absolute representation in the filesystem context, **without confirming the file exists**.

The program does not create the `data` directory or `report.txt`. Therefore you must not infer from `Same path: true` that the file exists or is readable.

## 6. Conversion Neither Checks Existence Nor Opens the File

Distinguish these four operations:

| Call | Meaning | Accesses file content? |
| --- | --- | --- |
| `file.toPath()` | Converts a File representation to Path | No |
| `path.toFile()` | Converts a default-FS Path to File | No |
| `Files.exists(path)` | Checks existence per API contract | Checks filesystem, does not read content |
| `Files.readString(path, UTF_8)` | Opens/reads and decodes text | Yes; may throw IOException |

`Files.exists(path)` returns false if it does not exist **or if it cannot be determined** due to permissions, I/O errors, or other provider situations. Thus `false` should not be treated as certain proof that the file does not exist in all cases. For operations requiring a real file, performing the operation and catching exceptions is more reliable than splitting into "check then act."

Example of wrong expectation:

~~~java
File source = new File("missing.txt");
Path path = source.toPath();   // Can still create Path.
String text = Files.readString(path); // May throw IOException.
~~~

This is an illustrative snippet. `toPath()` neither makes the file "vanish" nor "appear"; the error arises from the read action.

### 6.1. TOCTOU: Checking Beforehand Does Not Guarantee the Next Operation

Even when `Files.exists(path)` returns true at check time, another process can delete or replace the file before `Files.newInputStream(path)` actually opens it. This is a *time-of-check to time-of-use* (TOCTOU) condition.

Therefore, existence checks are useful for UI or preliminary logic, yet **do not replace `IOException` handling on the actual operation**. Likewise, `File ↔ Path` conversion creates no lock or guarantee about filesystem state.

## 7. Relative Paths, Absolute Paths, and Working Directory

### 7.1. Relative Remains Relative

~~~java
File oldFile = new File("reports", "2026.txt");
Path path = oldFile.toPath();

System.out.println(path.isAbsolute()); // false
~~~

This is an illustrative snippet. Conversion does not automatically prepend the working directory to the path. A relative path is interpreted according to the runtime environment's and filesystem's default directory rules when performing an operation requiring access.

To obtain an absolute representation, call it explicitly:

~~~java
Path absolute = path.toAbsolutePath();
~~~

`toAbsolutePath()` does not require the file to exist; it works at the path-representation level. Do not confuse it with the real path with symbolic links resolved.

### 7.2. normalize() Processes Syntax, Does Not Validate the Filesystem

Example:

~~~java
Path raw = Path.of("docs", ".", "drafts", "..", "final.txt");
Path normalized = raw.normalize();
~~~

After normalizing, the logical path is `docs/final.txt`. However, `normalize()` is a **lexical** operation; it does not need to open files or inspect symbolic links. When a path traverses a symbolic link, removing `..` can change how the path resolves in the real filesystem.

Therefore, only normalize when it aligns with your application's rules; do not treat `normalize()` as an automatic way to make paths safe or unify all paths pointing to the same file.

### 7.3. toRealPath() Is What Checks Reality

`path.toRealPath()` returns the real/canonical path per the filesystem contract and requires the entry to exist when default options apply. It can throw `IOException` and normally resolves symbolic links; `LinkOption.NOFOLLOW_LINKS` can be supplied to change link handling.

Differences:

~~~text
file.toPath()               Converts representation; does not read filesystem
path.toAbsolutePath()       Builds absolute path; does not check existence
path.normalize()            Collapses . and .. syntactically
path.toRealPath()           Queries filesystem, may throw IOException
~~~

An absolute path is not necessarily a real path; a normalized path does not necessarily exist.

## 8. Java 17 Example: Legacy File Using the Files API to Read Text

Save the file **LegacyFileModernFilesDemo.java**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LegacyFileModernFilesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("file-path-");
        Path path = directory.resolve("note.txt");

        try {
            Files.writeString(path, "Java 17", StandardCharsets.UTF_8);
            File legacyFile = path.toFile();

            Path converted = legacyFile.toPath();
            System.out.println("File exists: " + legacyFile.isFile());
            System.out.println("Path exists: "
                    + Files.isRegularFile(converted));
            System.out.println("Size: " + Files.size(converted));
            System.out.println("Text: "
                    + Files.readString(converted, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(path);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 LegacyFileModernFilesDemo.java
java LegacyFileModernFilesDemo
~~~

Result in a normal file environment with permissions to create/delete temporary files:

~~~text
File exists: true
Path exists: true
Size: 7
Text: Java 17
~~~

Explanation:

1. `Files.createTempDirectory` creates a real temporary directory exclusively for the program.
2. `Files.writeString` writes text in UTF-8.
3. `path.toFile()` converts `Path` to `File` to simulate a legacy API holding that object.
4. `legacyFile.toPath()` goes back to `Path` to use `Files.isRegularFile`, `Files.size`, and `Files.readString`.
5. `Files.size` returns the **byte count**, not the code point or character count. The ASCII text `Java 17` is 7 bytes.
6. `finally` deletes the file and then the temporary directory, even if the `try` body fails. In real software, if cleanup also fails, both the primary error and cleanup error should be preserved and recorded according to application strategy.

This example demonstrates the advantage of using the bridge when data starts as a `File` yet we want to operate with modern APIs, **without** manually turning paths into strings.

## 9. Using Path.toFile When a Legacy Library Requires File

Suppose a legacy library interface is:

~~~java
void attachFile(File file);
~~~

You are managing paths in an application using NIO:

~~~java
Path attachment = Path.of("uploads", "image.png");
attachFile(attachment.toFile());
~~~

These two snippets are **illustrative signatures/calls**, not a standalone Java program. This is a reasonable conversion if `attachment` belongs to the default filesystem and the library genuinely requires `File`.

Two further questions must be asked:

- Does the legacy library **only use the path** or require the file to already exist and be readable? `toFile()` does not satisfy those conditions.
- Is `Path` guaranteed to belong to the default provider? If not, `toFile()` can throw `UnsupportedOperationException`.

If the legacy API accepts `InputStream`, sometimes opening `Files.newInputStream(path)` and passing the stream is preferable to converting through `File`. You must determine who closes the stream; resources must be managed with a proper lifecycle.

## 10. Providers: Limits of Path.toFile and the ZIP Case

`Path` is bound to a `FileSystem`, whereas legacy `File` works primarily with the default file system. Therefore:

~~~java
Path defaultPath = Path.of("data", "report.txt");
File legacy = defaultPath.toFile(); // Valid on the default filesystem.
~~~

However, a `Path` created by a ZIP filesystem can represent an entry *inside* a ZIP archive. That entry does not automatically become a separate OS file. Calling `toFile()` with a non-default provider will throw `UnsupportedOperationException`.

### 10.1. Distinguishing the Two Paths When Working with ZIP

Suppose the ZIP file is at `/tmp/archive.zip` and contains `/docs/a.txt`:

~~~text
Path of the ZIP on the default file system:
    /tmp/archive.zip          → toFile() can be used

Path of the entry inside the ZIP filesystem:
    /docs/a.txt               → not a direct OS File
                                → toFile() is not supported
~~~

Do not work around this with `new File(entry.toString())`: the resulting path may point to `/docs/a.txt` outside on the default filesystem, rather than the entry inside the ZIP.

### 10.2. Handling with the Files API or Intentional Extraction

If you only need to read the entry, work directly with `Path`:

~~~java
byte[] payload = Files.readAllBytes(zipEntryPath);
~~~

Illustrative snippet with an already-opened `Path zipEntryPath` from a ZIP filesystem. No `File` is needed.

If a library strictly requires a real `File`, the application can **extract to a temporary file on the default filesystem**, pass that file, and manage timely deletion of the temporary file. This is intentional data copying, **not** a `Path.toFile` conversion. You must check entry sizes, permissions, and untrusted ZIP archive risks before extracting.

### 10.3. When to Catch UnsupportedOperationException?

`UnsupportedOperationException` is an unchecked exception. If a public API accepts any `Path` yet internally must return a `File`, document the provider limitation clearly, or convert at the integration boundary and handle the unsupported case according to the business contract.

Do not use `catch(Exception)` to turn every error into "file not found": `UnsupportedOperationException` indicates **the conversion model is unsupported**, not necessarily that the file inside the provider does not exist.

## 11. Preserving Path Semantics Across Windows, Linux, and macOS

The same character string can be interpreted differently across operating systems and filesystems:

- On Windows, there are drive letters, UNC paths, separator characters, and special path forms.
- On Linux/macOS, path rules and handling of `\` differ from Windows.
- Case sensitivity, Unicode, and symbolic link rules can depend on the filesystem, not only the operating system.

Instead of manually concatenating:

~~~java
String name = folder + "/" + fileName;
~~~

use path APIs:

~~~java
Path full = Path.of(folder).resolve(fileName);
~~~

Both illustrative snippets assume `folder` and `fileName` are supplied strings. `Path.resolve` follows filesystem rules and clearly expresses component joining. Still, be careful if `fileName` is untrusted input: it could contain `..` or be an absolute path that alters intent. `normalize()` alone **is not a guarantee against path traversal**, especially when symbolic links or concurrent filesystem changes exist.

To compare two paths, do not merely compare strings `file.getPath()` and `path.toString()` and conclude they point to the same file. Two representations may differ in relative/absolute form, `.`/`..`, casing, or symbolic links.

Choose the comparison according to purpose:

- `Path.equals`: compares `Path` objects according to provider rules and path structure; does not guarantee identifying the same physical file.
- `Path.normalize()`: compares after syntactic normalization if the contract permits.
- `Files.isSameFile(a, b)`: when you need to check whether two paths identify the same file according to the filesystem; may access the filesystem and throw `IOException`.

## 12. File.toPath Differs from File.getAbsoluteFile, File.getCanonicalFile

An older application might use:

~~~java
File absolute = file.getAbsoluteFile();
File canonical = file.getCanonicalFile();
~~~

`getAbsoluteFile()` returns an absolute `File` representation according to environment rules. `getCanonicalFile()` attempts to build a canonical path per the filesystem; it can throw `IOException` and is affected by current filesystem state.

The equivalent expressions in **purpose** in NIO are typically:

~~~java
Path absolutePath = file.toPath().toAbsolutePath();
Path normalizedPath = file.toPath().toAbsolutePath().normalize();
Path realPath = file.toPath().toRealPath();
~~~

These are illustrative snippets requiring an existing `File file` and `IOException` handling for `toRealPath()`. Do not treat the three results as completely equivalent:

- `getCanonicalFile()` and `toRealPath()` have different contracts, behaviors when the file does not exist yet, and link-handling options.
- `normalize()` processes syntax; it is not equivalent to resolving the full physical path.
- `toRealPath()` requires the file to exist under default usage and may throw a file system error.

If migrating legacy code, determine the true purpose of the "canonicalize" step before replacing it with a syntactically similar NIO call.

## 13. Converting When Copying, Moving, and Deleting

A common scenario when modernizing an application is replacing legacy `File` methods with `Files` APIs:

| Legacy File code | NIO approach with File.toPath() | Point to remember |
| --- | --- | --- |
| `file.exists()` | `Files.exists(file.toPath())` | False can include cases that cannot be determined |
| `file.isDirectory()` | `Files.isDirectory(file.toPath())` | Involves symbolic links/options |
| `file.length()` | `Files.size(file.toPath())` | `Files.size` may throw IOException |
| `file.delete()` | `Files.delete(file.toPath())` | NIO throws exceptions on failure instead of just boolean |
| `file.renameTo(dest)` | `Files.move(file.toPath(), dest.toPath())` | Not an absolute behavioral equivalent; options/providers affect it |
| `file.listFiles()` | `Files.list(file.toPath())` | Returns Stream<Path>; must close the returned stream |
| `file.mkdirs()` | `Files.createDirectories(file.toPath())` | NIO reports more detailed errors; races/filesystem conditions remain |

Be careful during conversion: APIs with similar intent do not necessarily share the same overwrite conditions, symbolic link handling, permissions, or failure outcomes. Some `File` methods return booleans; many `Files` methods throw `IOException` allowing clearer error classification. Do not swallow exceptions just to reconstruct booleans if the application needs diagnostics.

Specifically, `Files.list` returns a `Stream<Path>` tied to an open directory resource. If used, close the stream via `try-with-resources`; this is a concrete example where `File.toPath()` itself is **not** responsible for resource management.

### 13.1. Example Converting File.renameTo to Files.move

Save **MoveWithPathDemo.java**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MoveWithPathDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("move-bridge-");
        Path sourcePath = folder.resolve("old.txt");
        Path targetPath = folder.resolve("new.txt");

        try {
            Files.writeString(sourcePath, "moved", StandardCharsets.UTF_8);

            File legacySource = sourcePath.toFile();
            Files.move(legacySource.toPath(), targetPath);

            System.out.println("Old exists: "
                    + Files.exists(legacySource.toPath()));
            System.out.println("New content: "
                    + Files.readString(targetPath, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(targetPath);
            Files.deleteIfExists(sourcePath);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MoveWithPathDemo.java
java MoveWithPathDemo
~~~

Result on a normal writable filesystem:

~~~text
Old exists: false
New content: moved
~~~

Points to note: source and destination are in the same temporary directory, and the destination does not exist yet. This is a simple example to avoid overwrite controversies. `Files.move` can throw `IOException` (e.g., missing permissions, target exists, device error) or other exceptions per contract. If an atomic move is required, consider `StandardCopyOption.ATOMIC_MOVE` and handle when unsupported; do not infer that every default `move` call is always atomic.

## 14. File, Path, and URL/URI: Avoid Confusing Conversion Types

Three easily confused classes:

- `File`: legacy abstract pathname.
- `Path`: path inside a `FileSystem`.
- `URI`: resource identifier per URI syntax, potentially containing schemes such as `file:` or `jar:`.

For a `File` on the default filesystem:

~~~java
URI uri = file.toURI();
Path path = file.toPath();
~~~

The two calls are not equivalent in **return type**: `toURI()` creates a URI, `toPath()` creates a Path. Given a valid `file:` URI, `Path.of(uri)` can produce a Path via the filesystem provider supporting that URI. However, a `jar:` URI or a network service URI cannot be turned into a `File` by arbitrarily stripping the scheme.

Also do not use `Path.toString()` as a form of URI to send over a network, because that is a provider path representation, not URI encoding.

### 14.1. Illustrative Example: URI Does Not Replace File

~~~java
Path path = Path.of("data", "report.txt");
File file = path.toFile();       // File for legacy APIs.
URI uri = file.toURI();          // file: URI for identification.
Path recovered = Path.of(uri);   // Path on the corresponding provider.
~~~

This is an illustrative snippet requiring imports for `java.net.URI`, `java.io.File`, `java.nio.file.Path`. Here `URI` comes from `File.toURI()`, so it has the `file` scheme. Only use `Path.of(uri)` with URIs that an appropriate provider can handle; it does not work by default for arbitrary HTTP URLs.

## 15. Exceptions and Safety Issues During Conversion

The bridge operation itself is relatively lightweight, yet important situations can still arise:

| Case | Exception / consequence | How to handle |
| --- | --- | --- |
| `File.toPath()` with pathname not representable as a valid default-FS Path | May throw `InvalidPathException` | Validate/sanitize input per application contract; do not guess OS |
| `Path.toFile()` on non-default provider | `UnsupportedOperationException` | Use `Files` on `Path` or intentionally extract if legacy API strictly requires |
| `Files.readString(path)` when file is missing | Usually `NoSuchFileException` | Catch `IOException` in context |
| `Files.size(path)` when lacking permission | May be `AccessDeniedException`/other `IOException` | Report accurate error cause |
| Path to file with symbolic link | Operation may follow link depending on API/option | Choose appropriate `LinkOption`, test |
| Building paths from untrusted input | Risk of path traversal | Define valid root, perform real safety checks |
| Legacy code calling `new File(path.toString())` on foreign-provider Path | May point to **a different file** on default FS | Do not use string coercion |

**`InvalidPathException`** is an unchecked exception; on some systems, a path string with invalid characters is rejected at the `Path` creation stage. Missing-file/permission errors usually only surface when actually accessing the filesystem, such as during `Files.newInputStream` or `Files.readAttributes`.

**`SecurityException`** may arise in some environments with corresponding security mechanisms; it is not an `IOException`. You should not lump every path-creation/conversion failure into a single "file read failed" bucket.

## 16. Resource Management: File and Path Do Not Need close

`File` and `Path` are objects describing paths. Having the name `File` does not mean this object has opened a file descriptor, and there is no need to use `try-with-resources` merely for creation/conversion:

~~~java
File file = new File("example.txt");
Path path = file.toPath();
// No need to close file or path.
~~~

When **opening a stream, channel, or directory stream**, you must close it properly per lifecycle:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[4096];
    int count;
    while ((count = input.read(buffer)) != -1) {
        // Process buffer[0..count).
    }
}
~~~

This illustrative snippet requires importing `java.io.InputStream` and `java.nio.file.Files`, with the enclosing method handling `IOException`. `try-with-resources` manages `InputStream`; it has nothing to do with closing `path`.

Similarly, `Files.lines(path)` and `Files.list(path)` return Streams that must be closed when finished to release resources. Short convenience methods like `Files.readString(path)` manage opening/closing themselves per their contracts, yet can still report errors.

## 17. Testing and Common Project Scenarios

### 17.1. Legacy API Returns File, New Code Needs NIO Metadata

**Problem:** `legacyApi.getFile()` returns `File`; need to read metadata or text with `Files`.

~~~java
File file = legacyApi.getFile();
Path path = file.toPath();
long size = Files.size(path);
~~~

This is an illustrative snippet with `legacyApi` provided by a library. If the file is missing or inaccessible, `Files.size` reports the error per contract, not `File.toPath()`.

### 17.2. New Code Holds Path, Legacy Library Only Accepts File

**Problem:** An NIO path belongs to the default filesystem and needs to be passed to a legacy library.

~~~java
Path report = Path.of("reports", "daily.pdf");
oldLibrary.upload(report.toFile());
~~~

This illustrative snippet assumes `oldLibrary.upload(File)` exists. If the path actually belongs to a ZIP filesystem, do not use `toFile()` as a universal cast; change the workflow or extract according to policy.

### 17.3. Want to Know If File and Path Point to the Same Resource?

If both point to the default filesystem:

~~~java
boolean same = Files.isSameFile(file.toPath(), path);
~~~

This is an illustrative snippet; `IOException` must be handled. `isSameFile` asks about the entity in the filesystem rather than merely comparing two strings. However, the filesystem can change between the check and the next operation; this is not a locking mechanism.

### 17.4. Legacy Code Uses renameTo and Lacks Detailed Error Reporting

When modernizing:

~~~java
Files.move(sourceFile.toPath(), targetFile.toPath());
~~~

This is an illustrative snippet. `Files.move` can throw exceptions for specific reasons instead of returning a boolean like `File.renameTo`. You must review policies on existing target files, symlinks, cross-provider moves, and atomicity, rather than just swapping the method name.

### 17.5. Tests Should Not Depend on Pre-Existing Files

The example programs above use `Files.createTempDirectory` to create an isolated directory, add files written by the program itself, and clean up at the end. This limits dependence on the learner's machine, though it still requires permission to create/delete temporary files. When testing errors, proactively create missing or already-existing file scenarios rather than assuming some arbitrary name in the working directory is definitely unoccupied.

## 18. Common Mistakes When Learning File.toPath / Path.toFile

| Misconception | Consequence | Correct understanding |
| --- | --- | --- |
| `toPath()` "turns the file into an opened object" | Assumes data was read and forgets `IOException` | Only converts path representation |
| `toFile()` creates a physical file | Assumes the file exists after calling | Only creates a `File` object |
| Any `Path` can call `toFile()` | Crashes on ZIP/other providers | Only the default filesystem supports it |
| `new File(path.toString())` always equals `path.toFile()` | Loses provider semantics, may point to a different file | Use `toFile()` when supported |
| Converting automatically creates an absolute path | Accesses the wrong directory | Use `toAbsolutePath()` when needed |
| Converting removes `.`/`..` and symlinks | Wrong comparisons/security | Distinguish `normalize` from `toRealPath` |
| `Files.exists` guarantees the next read succeeds | TOCTOU, permissions change | Handle `IOException` from the actual operation |
| Using `File.exists()` to handle all error cases | Unclear why it returned false | Choose `Files` APIs that throw exceptions when needed |
| Comparing paths by string alone | Ignores structure/provider/aliases | Compare by purpose, consider `isSameFile` |
| Manually concatenating `"/"` between components | May violate platform rules | Use `Path.of`/`resolve` |
| Assuming `File.renameTo` and `Files.move` are identical in all respects | Wrong replacement policy, errors, and atomicity | Read API contracts, use appropriate options |
| Closing `File` or `Path` like a stream | Confuses resource model | Close streams/channels, not path objects |
| Getting a `Path` from ZIP then calling `toFile` to pass to legacy library | `UnsupportedOperationException` | Use `Files` directly or extract to a valid temporary file |

## 19. Practice Exercises

### Exercise 1 — Relative Path and Round-Trip

Create `Path.of("logs", "app.log")`, convert to `File` and back to `Path`. Check `isAbsolute()`, `getFileName()`, `equals()`. Why can all of these execute even without a real file?

**Hint:** These operations do not need to open content. `toAbsolutePath()` also does not require the file to exist.

### Exercise 2 — Reading Metadata via File.toPath

Create a temporary file in the program's temporary directory, write `"12345"` in UTF-8, convert to `File`, and then use `Files.size(file.toPath())`. What is the result in this case?

**Answer:** 5 bytes. This is ASCII data so each character occupies one UTF-8 byte. If changed to accented text or emojis, do not infer byte count from `String.length()`.

### Exercise 3 — Non-Default Provider

Suppose a library returns a `Path` to an entry in a ZIP filesystem. Why can't you simply call `path.toFile()`? If a legacy library only accepts a real `File`, what must you do?

**Answer:** `Path.toFile()` does not support non-default providers. You can continue processing via `Files` with the original `Path`; if an OS `File` is mandatory, extract content to a temporary file on the default filesystem and manage that file's lifecycle.

### Exercise 4 — normalize Is Not toRealPath

For the path `a/./b/../c.txt`, what does `normalize()` do? Does it verify that `c.txt` exists?

**Answer:** Syntactically simplifies to `a/c.txt` without checking whether the file exists. With symbolic links, this transformation does not necessarily preserve physical path resolution.

### Exercise 5 — Checking Safety of Migrating Legacy Code

A legacy snippet uses `file.delete()` returning a boolean. If replaced with `Files.delete(file.toPath())`, how must the error-handling contract change?

**Answer:** `Files.delete` can throw `IOException`, including missing-file/permission causes, plus other runtime exceptions per contract. Callers must handle/declare errors instead of only checking true/false. If missing files should not be treated as errors, consider `Files.deleteIfExists`, though I/O failures must still be handled.

### Exercise 6 — Handling User-Supplied Paths

A child path received from outside is `"../../secrets.txt"`. Why is calling `normalize()` and then `toFile()` not enough to guarantee the user only accesses within the allowed directory?

**Answer:** The string can escape the intended root; symlinks and filesystem mutations can change the real target. You must have proper path-scope controls and access permissions rather than relying solely on type conversion or `normalize()`.

## 20. Core Takeaways

- **`File.toPath()`** converts a legacy API path into a `Path` on the default file system.
- **`Path.toFile()`** converts back when `Path` belongs to the **default file system provider**; not every `Path` supports it.
- **Conversion only changes representation.** It does not open, read, write, create, or delete files; it does not guarantee the path exists or is accessible.
- **Relative/absolute and canonical paths are separate concerns.** Use `toAbsolutePath`, `normalize`, and `toRealPath` with their exact meanings, not interchangeably.
- **To modernize legacy code,** use `file.toPath()` at the boundary and then use `Files` APIs with explicit exception handling.
- **To integrate legacy libraries,** only use `path.toFile()` when you know the provider supports it; for ZIP/virtual filesystems, prefer APIs accepting `Path`/streams or perform intentional extraction.
- **Do not confuse `File`/`Path` with an open resource.** Close streams/channels/directory streams with `try-with-resources`, not path representation objects.

### Official API Documentation (Java SE 17)

- [File.toPath() — java.io.File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html#toPath())
- [Path.toFile() — java.nio.file.Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#toFile())
- [Path — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileSystem — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html)
- [StandardCopyOption — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)