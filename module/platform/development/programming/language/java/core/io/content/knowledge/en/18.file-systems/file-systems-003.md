# Relationship Between `Path` and the `FileSystem` That Created It

## 1. Core idea

In Java NIO.2 (`java.nio.file`), a `Path` is not merely a string describing a location. It is a **path object belonging to a specific `FileSystem`**. The `FileSystem` determines how names, separators, root paths, and certain operations on that path are parsed and handled.

- `FileSystem`: a model of a file system, such as the machine's default file system or a ZIP file opened as a file system.
- `Path`: the location of a file/directory *inside* that file system; `Path` itself does not guarantee that the actual file exists.
- `FileSystemProvider`: the component supplying the implementation for the corresponding file system type, for example the default provider with scheme `file` or the ZIP filesystem provider with scheme `jar`.

Core relationship:

~~~text
FileSystemProvider (implements how access works)
          |
          +--> FileSystem A --> Path A1, Path A2, ...
          |
          +--> FileSystem B --> Path B1, Path B2, ...
~~~

**A `Path` is always bound to a `FileSystem` via `path.getFileSystem()`.** One provider can manage multiple `FileSystem` instances; multiple `Path` instances can belong to the same `FileSystem`. Even if two paths have identical `toString()` outputs, they do not necessarily refer to the same file object if they belong to different file systems.

For example, `/docs/readme.md` inside a ZIP is not `/docs/readme.md` on the machine's disk, even though the text form looks similar.

## 2. A `Path` belongs to the `FileSystem` from which it was created

### Default file system paths

~~~java
Path p = Path.of("documents", "report.txt");
FileSystem owner = p.getFileSystem();
FileSystem defaultFs = FileSystems.getDefault();

System.out.println(owner == defaultFs); // true on a typical JDK
~~~

`Path.of(String, String...)` (like `Paths.get(String, String...)`) uses the **default file system**. `FileSystems.getDefault()` returns the process's default file system. The path may be relative or absolute; neither property changes which file system owns it.

### Paths created explicitly from a `FileSystem`

~~~java
Path p = someFileSystem.getPath("/docs/report.txt");
FileSystem owner = p.getFileSystem();
~~~

Here `p` belongs to `someFileSystem`. Calling `getPath` does not create any file yet. The syntax `"/docs/report.txt"` is interpreted by that specific file system; it should not be treated as an OS path in every case.

### Paths from a URI

`Path.of(URI)` selects a provider via the URI's scheme. For the `file` scheme, this normally creates a path on the default file system. For a URI such as `jar:file:...!/entry`, the corresponding ZIP file system usually must be opened/registered beforehand for retrieving the `Path` to succeed; if there is no suitable provider or file system, `ProviderNotFoundException` or `FileSystemNotFoundException` may occur. The easiest approach to control when you already hold a `FileSystem` object is to use `fs.getPath(...)` itself.

**Do not infer the file system from `path.toString()`.** Ask `path.getFileSystem()` directly, and when needed also query `path.getFileSystem().provider()`.

## 3. Two levels of relationship to distinguish

| Check | What it confirms | What cannot be inferred automatically |
| --- | --- | --- |
| `a.getFileSystem() == b.getFileSystem()` | Same `FileSystem` object in the process | Same file or same location |
| `a.getFileSystem().provider() == b.getFileSystem().provider()` | Same provider object | Same file system |
| `a.equals(b)` | Two path objects are equal according to the `Path` implementation's rules | Definitely the same physical file in all situations |
| `Files.isSameFile(a, b)` | The API attempts to determine whether two paths point to the same existing file | Does not avoid I/O access or always produce a result for every provider |

For example: two different ZIPs can be opened by the **same ZIP provider**, yet each ZIP forms **a separate `FileSystem`**. Each file system has its own `/docs/guide.txt`; those two paths are independent. Conversely, two different names within the same file system can still point to the same file because of symbolic links or hard links; `Path.equals` does not replace checking file identity.

`==` in the first two rows is **object identity** comparison. When you need to evaluate path equality, use `equals` per the provider's semantics; when you need to check whether two paths point to the same existing file, consider `Files.isSameFile` and handle `IOException`.

## 4. `Path` transformations that preserve the file system

Name-manipulation operations on a `Path` such as `getParent()`, `getFileName()`, `subpath(...)`, `normalize()`, `toAbsolutePath()`, and `resolve(String)` produce a resulting path in the **same `FileSystem`** as the original path (except when the API returns `null`, such as `getParent()` on a path with no parent).

~~~java
Path base = Path.of("data", "reports");
Path child = base.resolve("daily.txt");
Path absolute = child.toAbsolutePath().normalize();

System.out.println(base.getFileSystem() == child.getFileSystem());    // true
System.out.println(base.getFileSystem() == absolute.getFileSystem()); // true
~~~

`normalize()` only simplifies name elements such as `.` and `..` syntactically; it does **not** verify existence, follow symbolic links, or guarantee that two paths access the same file. `toAbsolutePath()` converts the representation from relative to absolute in the context of the file system in use; it does not move the path to another file system.

In particular, `Path.resolve(Path other)` and `Path.relativize(Path other)` require compatible paths according to the implementation's rules. Mixing a `Path` from another provider normally leads to `ProviderMismatchException`. `relativize` can also throw `IllegalArgumentException` when a valid relative relationship cannot be formed (for example, mismatched absolute/relative types on typical providers).

## 5. Runnable example: default file system and ZIP filesystem

The Java 17+ program below creates a temporary ZIP file, opens it with the ZIP provider included in typical JDK distributions (`jdk.zipfs`), creates a file *inside the ZIP*, and compares the origins of the `Path` objects. The random ZIP file name is not printed so stdout remains deterministic.

Save as `PathFileSystemDemo.java`:

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderMismatchException;
import java.util.Map;

public class PathFileSystemDemo {
    public static void main(String[] args) throws IOException {
        Path hostPath = Path.of("notes.txt");
        FileSystem defaultFs = FileSystems.getDefault();
        System.out.println("host belongs to default: "
                + (hostPath.getFileSystem() == defaultFs));

        Path archive = Files.createTempFile("path-fs-demo-", ".zip");
        // The ZIP provider needs a fresh ZIP file when using create=true.
        Files.delete(archive);

        try {
            URI jarUri = URI.create("jar:" + archive.toUri());
            FileSystem zipFs = FileSystems.newFileSystem(
                    jarUri, Map.of("create", "true"));

            try (zipFs) {
                Path insideZip = zipFs.getPath("/docs/hello.txt");
                Files.createDirectories(insideZip.getParent());
                Files.writeString(insideZip, "Xin chao NIO.2");

                System.out.println("zip path belongs to zipFs: "
                        + (insideZip.getFileSystem() == zipFs));
                System.out.println("same filesystem: "
                        + (hostPath.getFileSystem() == insideZip.getFileSystem()));
                System.out.println("zip content: " + Files.readString(insideZip));

                try {
                    insideZip.resolve(hostPath);
                    System.out.println("unexpected resolve success");
                } catch (ProviderMismatchException expected) {
                    System.out.println("cross-provider resolve rejected: true");
                }
            }

            System.out.println("zip filesystem open: " + zipFs.isOpen());
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
~~~

Compile and run with JDK 17 or later containing the `jdk.zipfs` module:

~~~bash
javac PathFileSystemDemo.java
java PathFileSystemDemo
~~~

Stdout:

~~~text
host belongs to default: true
zip path belongs to zipFs: true
same filesystem: false
zip content: Xin chao NIO.2
cross-provider resolve rejected: true
zip filesystem open: false
~~~

Read the example in order:

1. `hostPath` is created from `Path.of(String)`, so it belongs to the default file system, even though `notes.txt` **does not need to exist**.
2. `jarUri` points to **the ZIP file itself on disk**, whereas `zipFs.getPath("/docs/hello.txt")` represents **an entry inside the ZIP**. These are two different addressing layers.
3. `Files.createDirectories` and `Files.writeString` operate through `insideZip`'s provider; the data is written as a ZIP entry, not as a `/docs` directory on the default disk.
4. `insideZip.resolve(hostPath)` is rejected because the argument `hostPath` belongs to the default provider, which differs from the ZIP provider. If you only need to append a *relative name* inside the ZIP, use `insideZip.getParent().resolve("another.txt")` or `zipFs.getPath(...)`.
5. `try (zipFs)` closes the ZIP filesystem and completes updating the ZIP file. `zipFs.isOpen()` is then `false`; new I/O operations on a `Path` belonging to the closed file system may throw `ClosedFileSystemException`.
6. `finally` cleans up the temporary ZIP file. Closing and cleaning up resources must happen even if an exception occurs in between.

**Limitation of the example:** a customized JRE build may lack `jdk.zipfs`, in which case the ZIP provider portion cannot run without adding the module. On a standard JDK, the example runs standalone with no external libraries.

## 6. When coordinating two file systems

There are two different operations that are very easy to confuse:

**Joining or computing relative paths**: operates on *names* within one file system. Create both operands using the same `FileSystem` if you use `resolve(Path)` or `relativize(Path)`; or use a relative string when you intend to form a child name inside the target file system.

**Copying data between two file systems**: `Files.copy(source, target, options...)` accepts a source path and a target path that may belong to different providers. The API performs the copy according to the providers' capabilities, and may throw `IOException` or errors for unsupported options/attributes. Case from ZIP to disk:

~~~java
// insideZip belongs to zipFs, destination belongs to the default file system.
// This snippet must run while zipFs is still open.
Path destination = Path.of("exported-hello.txt");
Files.copy(insideZip, destination);
~~~

This is an **illustrative snippet placed inside the `try (zipFs)` block** of the example above, not a standalone program. For a program run multiple times, remember to handle the case where the target file already exists (for example, use `StandardCopyOption.REPLACE_EXISTING` if you genuinely want to replace it).

`Files.move` across providers has different limitations than an internal rename: moving may be performed by copying and then deleting, which is not atomic; requesting `ATOMIC_MOVE` may cause `AtomicMoveNotSupportedException`. Do not assume that every operation on `Path` is safe or has the same performance when crossing different file systems.

## 7. `FileSystem`-dependent rules

Beyond ownership, `FileSystem` affects the following rules and capabilities:

- **Name separation**: `fs.getSeparator()` may be `/` or `\` depending on the provider/OS; do not hardcode OS paths for every provider.
- **Roots and absolute paths**: `fs.getRootDirectories()` and `path.getRoot()` are interpreted per file system; a ZIP path has root `/` even though the ZIP is just a single file on the machine.
- **Path matchers**: `fs.getPathMatcher("glob:*.txt")` creates a matcher according to provider syntax and characteristics; results depend on the file system's rules.
- **File attributes**: `fs.supportedFileAttributeViews()` indicates which views are supported; providers do not necessarily support POSIX, DOS, owner, or ACL attributes uniformly.
- **State/access**: `fs.isOpen()`, `fs.isReadOnly()`, and `Files.*` calls can lead to `ClosedFileSystemException`, `ReadOnlyFileSystemException`, or `IOException` in the corresponding situations.

All of these are reasons to pass a `Path` or `FileSystem` to library functions instead of passing only a string and reconstructing the path using the default file system in an inner layer.

For example, a function accepting `Path root` should be written:

~~~java
Path output = root.resolve("output.txt");
~~~

This keeps `output` in the file system that owns `root`. If replaced with `Path.of(root.toString(), "output.txt")`, the code unintentionally **binds the new path to the default file system** and can cause errors when `root` resides inside a ZIP or another provider.

## 8. `FileSystem` lifecycle and error handling

- `FileSystems.getDefault()` manages the default file system for the application. **Do not close** the default filesystem yourself; calling `close()` on typical default implementations may throw `UnsupportedOperationException`.
- Additional file systems opened via `FileSystems.newFileSystem(...)` generally have their lifecycle managed by your code and should be closed with `try-with-resources` when finished. Do not return a `Path` from a ZIP filesystem out of scope and close the filesystem before the caller accesses the data.
- If you open the same URI of an already registered file system twice, depending on the provider you may receive `FileSystemAlreadyExistsException`. `FileSystems.getFileSystem(uri)` looks up a registered file system, but will throw `FileSystemNotFoundException` when none exists yet.
- When receiving a `Path` from outside, check with `path.getFileSystem()` if the API requires a specific filesystem; if the API can handle any provider, preserve the caller's `Path` rather than converting through `toString()` and `Path.of(...)`.

**Distinguish three error types:** `ProviderMismatchException` (combining two incompatible `Path` objects), `FileSystemNotFoundException` (failing to find a registered filesystem for a URI), and `ClosedFileSystemException` (using a resource of a closed filesystem). They indicate different problems, so their remedies also differ.

## 9. Self-check questions

1. If two paths both print as `/config/app.yml`, can we conclude they point to the same file? **No**: you need to know the `FileSystem` and may need to check the actual file.
2. Why can't `zipFs.getPath("/x.txt")` be arbitrarily replaced by `Path.of("/x.txt")`? Because the latter creates a `Path` belonging to the default filesystem, not the ZIP.
3. Do `normalize()` or `resolve(String)` convert a ZIP path into a host path? **No**: they preserve the owning filesystem.
4. To bring content from a `Path` inside a ZIP out to disk, should you join paths or copy? Use `Files.copy` with `target` created in the target filesystem and handle errors and resource lifecycles.
5. Should a multi-provider file-manipulation API accept `String path` or `Path path`? Usually **`Path`**, because it retains both the name structure and the owning file system information.

**Remember:** A `Path` carries the identity of the `FileSystem` that created it. Manipulating *path names* must respect this identity; *transferring data* between file systems must use the appropriate I/O APIs.
