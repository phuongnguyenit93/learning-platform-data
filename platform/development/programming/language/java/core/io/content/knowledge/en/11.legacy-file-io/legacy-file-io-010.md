# When Should You Prefer `Path` and `Files` Over `java.io.File`?

In Java, both `java.io.File` and the `java.nio.file` API suite can represent pathnames to files/directories and support common file system operations. However, when writing **new Java code on Java 17+**, most situations involving files and directories should **prefer `Path` + `Files`** instead of instantiating `File` and calling legacy methods.

The reason is not just shorter syntax. NIO.2 (introduced in Java 7) brings a clearer path model, file operations with exceptions carrying causes, parameter options for copy/move, modern read/write APIs, file attributes, directory tree traversal, symbolic links, directory change watching, and the ability to work with different **file system providers**.

This **does not mean `File` is no longer usable**, or that every project must immediately delete `java.io.File`. The goal is to recognize when `Path` + `Files` solves the right problem, when `File` must still be used for compatibility, and how to convert safely between them.

## 1. How Do `File`, `Path`, and `Files` Differ in Role?

### `java.io.File` — Path Representation with the Legacy API

A `File` object represents an **abstract pathname**. It can point to a file, a directory, a non-existent path, or an inaccessible location. Creating `new File("report.txt")` **does not automatically create a real file** on disk.

`File` combines quite a few functions into one class: pathname manipulation (`getName()`, `getParentFile()`), checks (`exists()`, `isFile()`), file/directory creation (`createNewFile()`, `mkdirs()`), deletion (`delete()`), renaming (`renameTo()`), listing (`listFiles()`), and more.

This API is still widely used by legacy libraries and code, yet has several drawbacks:

- Many operations return **`boolean`**: when `delete()` or `renameTo()` returns `false`, the caller does not immediately receive an exception explaining whether the file does not exist, permissions are missing, the file is in use, or the filesystem does not support it.
- Some listing APIs return `null` if it is not a directory **or** when an I/O error occurs; extra logic is required to distinguish them.
- Handling of symbolic links, attributes, and varied copy/move behaviors is not as uniform as in NIO.2.
- `File` is primarily tied to the environment's default filesystem, lacking a general provider model like `Path`.

### `java.nio.file.Path` — Represents a Path

`Path` is an **interface** representing a location in a filesystem: name, path elements, relative/absolute paths, operations such as `resolve`, `relativize`, `normalize`, `toAbsolutePath`, etc.

Example:

```java
Path source = Path.of("data", "report.txt");
Path backup = source.resolveSibling("report.bak");
```

This is an **illustrative snippet**, requiring `import java.nio.file.Path`. Similar to `File`, creating a `Path` **does not read, write, or check** whether a real file exists. `Path` also does not hold an open file descriptor.

`Path.of(...)` has existed since **Java 11**, while `Paths.get(...)` has existed since **Java 7**. In Java 17, `Path.of` is usually concise and sufficient.

### `java.nio.file.Files` — Operations on Files, Directories, and Attributes

`Files` is a utility class containing many static methods that accept `Path`:

```java
Files.createDirectories(directory);
Files.writeString(file, "Hello", StandardCharsets.UTF_8);
String text = Files.readString(file, StandardCharsets.UTF_8);
Files.copy(source, destination);
Files.move(oldPath, newPath);
Files.delete(file);
```

This is **illustrative code**, requiring the variables to be defined, `IOException` handled, and imports for `java.nio.file.Files`, `java.nio.charset.StandardCharsets`. Real filesystem operations can throw exceptions such as `NoSuchFileException`, `FileAlreadyExistsException`, or `AccessDeniedException` (depending on the provider), helping callers react much better than an unexplained `false`.

> **Practical rule:** Use **`Path` to carry paths**, **`Files` to perform operations**, and appropriate stream/channel/reader/writer classes when transferring data. `Path` + `Files` is not an alternate name for all of Java non-blocking I/O (*non-blocking I/O*); `Files` operations are still typically **blocking I/O**.

## 2. Comparison for Choosing an API

| Need | Legacy approach | Typically preferred in Java 17+ | Key benefit |
|---|---|---|---|
| Create path object | `new File("data/report.txt")` | `Path.of("data", "report.txt")` | Clear path API, provider-aware |
| Create directory and parent directories | `file.mkdirs()` | `Files.createDirectories(path)` | Exceptions on failure, not just `false` |
| Create new empty file | `file.createNewFile()` | `Files.createFile(path)` | Reports existing file via `FileAlreadyExistsException` |
| Check path type | `isFile()`, `isDirectory()` | `Files.isRegularFile`, `Files.isDirectory` | Options for symbolic link handling |
| Read small text file | Open `FileReader`/`BufferedReader` | `Files.readString(path, UTF_8)` | Concise, explicit charset |
| Write small text file | Open `FileWriter` | `Files.writeString(path, text, UTF_8)` | Options for create/overwrite/append |
| Stream large file | `FileInputStream` or `BufferedReader` | `Files.newInputStream` / `Files.newBufferedReader` | Combines path, charset, and stream |
| Copy file | Write input/output loop manually | `Files.copy(source, target, options...)` | Has options and exceptions |
| Move/rename | `renameTo` | `Files.move(source, target, options...)` | Clear semantics, atomic option when supported |
| Delete file | `delete()` returns boolean | `Files.delete(path)` / `deleteIfExists(path)` | Distinguishes non-existent from errors |
| List directory | `listFiles()` | `Files.list(dir)` / `newDirectoryStream(dir)` | Flexible stream/filter; remember to close |
| Walk directory tree | Write recursion with `listFiles` | `Files.walk` / `walkFileTree` | Visitor, lifecycle and error control |
| Read metadata | `length()` / `lastModified()` | `Files.size` / `readAttributes` | Richer attributes |
| Symbolic links | Limited capabilities | `Files.isSymbolicLink`, `readSymbolicLink`, `NOFOLLOW_LINKS` | Intentional control |
| Watch directory changes | Manual polling | `WatchService` | Event-driven, with provider limits |

**Do not treat the table as an absolute rule.** If a library API strictly requires `File`, passing `File` is reasonable. For virtual filesystems or special providers, `Path` is the right model; `Path.toFile()` may not be supported.

## 3. When Is `Path` + `Files` the Preferred Choice?

### 3.1 When Starting a New File-Handling Feature

If a service needs to read, write, copy, move, or check files, the `Files` API typically reduces boilerplate. For example, instead of building path strings with `"/"` or `"\\"` by platform:

```java
Path directory = Path.of("data", "reports");
Path report = directory.resolve("october.txt");
```

`Path` interprets separators based on the corresponding filesystem. You do not need to manually concatenate `"data/" + name` and hope it works everywhere.

### 3.2 When You Need to Know **Why** an Operation Failed

`File.delete()` returns `false` when it cannot delete. `Files.delete(path)` declares `throws IOException` and can throw specialized classes such as `NoSuchFileException` or `DirectoryNotEmptyException`. The caller can distinguish:

- File does not exist: ignore if business logic permits, or report a specific error.
- Directory is not empty: decide whether a recursive operation is needed; `Files.delete` **does not delete recursively automatically**.
- Insufficient permissions or filesystem refusal: report an operational error instead of pretending "no file."

**Note:** Specific exceptions depend on the OS/file system provider; there is no guarantee every platform will throw the exact same subtype in all situations. You must still handle general `IOException`.

### 3.3 When Managing Directory Creation and File Writing with Options

`Files.createDirectories(path)` creates necessary parent directories; if the path is already a directory, the operation can succeed. Unlike `Files.createDirectory(path)`, it supports multiple non-existent levels.

`Files.writeString`/`write` supports explicit `StandardOpenOption`s. For example:

- The default of `Files.writeString(path, text, charset)` is to create the file if missing or truncate existing file content and write anew.
- `CREATE_NEW`: creates only if not already present, throwing an error if the path already exists (use when you must not overwrite).
- `APPEND`: appends content to the end; consider newlines and option compatibility.
- `TRUNCATE_EXISTING`: truncates the file to length 0 when opened for writing if selected.
- `WRITE`: opens for writing.

**Do not call `writeString` without considering the possibility of overwriting old content.** For configuration or important data, choose `CREATE_NEW` or a temporary-file strategy as required.

### 3.4 When Copying/Moving with Intentional Semantics

`Files.copy` and `Files.move` support options such as `StandardCopyOption.REPLACE_EXISTING` (replaces the destination within contract scope) and `StandardCopyOption.COPY_ATTRIBUTES` (when applicable to copy, subject to provider limits).

`StandardCopyOption.ATOMIC_MOVE` requests an atomic move operation if supported by the provider/filesystem; it may throw `AtomicMoveNotSupportedException` when unsupported. **Do not assume atomic move is always available**, especially across different filesystems. If falling back to a regular move, you must understand that it **no longer guarantees atomicity**.

Distinguish:

- **Copy:** keeps the source and creates a copy at the destination; `Files.copy(source, target)` does not recursively copy an entire directory tree. Copying a directory path under standard API rules does not mean all child contents are copied.
- **Move:** transfers the path or content per provider behavior; not synonymous with "copy then delete" always being safe or atomic.
- **Replace existing:** requires careful thought before overwriting the destination resource; do not enable it merely for shorter code.

### 3.5 When Needing File Attributes, Symbolic Links, and Different Filesystems

`Files.readAttributes`, `Files.getLastModifiedTime`, `Files.size`, `Files.getOwner`, and attribute view APIs retrieve richer information than `File.length()` or `lastModified()`. Available attributes depend on the filesystem and provider.

`Files.isSymbolicLink(path)` determines whether a path is a symbolic link; `NOFOLLOW_LINKS` is an option used in supporting operations to avoid following links automatically. This is critical for directory cleanup, backup, synchronization, and operating on externally supplied paths.

`Path` is bound to a `FileSystem` and provider. NIO.2 can work with other filesystem providers (such as a ZIP filesystem when a corresponding provider exists), whereas `java.io.File` typically works only with the default filesystem.

## 4. `Path` Represents a Name, Not a Guarantee the File Exists

`Path` methods mainly transform **path syntax** without touching disk:

- `getFileName()`: retrieves the last name component.
- `getParent()`: retrieves the parent path portion (may be `null`).
- `getRoot()`: retrieves the root (may be `null`).
- `resolve(other)`: combines paths; if `other` is an absolute path, `resolve` normally returns that absolute path.
- `resolveSibling(other)`: replaces the last name with a sibling path under the same parent.
- `normalize()`: removes `.` segments and resolves `..` syntactically, **without accessing the filesystem**.
- `toAbsolutePath()`: builds an absolute path per the provider's filesystem/context, without proving the file exists.
- `toRealPath(...)`: accesses the filesystem to retrieve the real path of an **existing** entry, usually resolving symbolic links per options, and can throw `IOException`.
- `relativize(other)`: constructs a relative path between two compatible `Path`s; can fail when mixing incompatible roots/absolute/relative forms.

### Example 1 — `resolve`, `normalize`, `resolveSibling`, `relativize`

Create the file `PathSemanticsDemo.java`:

```java
import java.nio.file.Path;

public class PathSemanticsDemo {
    public static void main(String[] args) {
        Path base = Path.of("workspace", "data").toAbsolutePath().normalize();
        Path report = base.resolve("..").resolve("report.txt").normalize();

        System.out.println("is absolute=" + report.isAbsolute());
        System.out.println("filename=" + report.getFileName());
        System.out.println("parent ends workspace="
                + report.getParent().endsWith("workspace"));
        System.out.println("resolveSibling matches="
                + report.equals(base.resolveSibling("report.txt")));
        System.out.println("relative name=" + report.getParent().relativize(report));
    }
}
```

Compile/run with Java 17 or higher:

```bash
javac -encoding UTF-8 --release 17 PathSemanticsDemo.java
java PathSemanticsDemo
```

Result:

```text
is absolute=true
filename=report.txt
parent ends workspace=true
resolveSibling matches=true
relative name=report.txt
```

The example does not need a real `report.txt` file. `base` is an absolute path from the current working directory, `resolve("..")` adds a parent segment syntactically, and `normalize()` removes redundant segments.

`Path.equals` compares paths **according to the provider's equality rules**, which is not necessarily equivalent to "both paths point to the same real file." For instance, paths going through symbolic links or differing in casing may still require `Files.isSameFile(a, b)` if asking whether two existing paths refer to the same file.

**Critical caveat:** `normalize()` **is not a security check**. If symbolic links exist among path segments, the syntactically normalized result may differ from the physical path. Do not use it alone to verify that uploaded data stays inside an allowed directory.

## 5. Example 2 — Working with Real Files Using `Files`

Create the file `FilesCrudDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.stream.Stream;

public class FilesCrudDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("path-files-");
        try {
            Path folder = Files.createDirectories(root.resolve("docs/notes"));
            Path source = folder.resolve("note.txt");
            String content = "Xin chào Java\n";
            Files.writeString(source, content, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            Path copy = root.resolve("copy.txt");
            Files.copy(source, copy);
            Path moved = root.resolve("moved.txt");
            Files.move(copy, moved);

            System.out.println("folder directory=" + Files.isDirectory(folder));
            System.out.println("UTF-8 round trip="
                    + content.equals(Files.readString(source, StandardCharsets.UTF_8)));
            System.out.println("copy remains=" + Files.exists(copy));
            System.out.println("moved regular file=" + Files.isRegularFile(moved));
            System.out.println("contents equal="
                    + Files.readString(source, StandardCharsets.UTF_8)
                        .equals(Files.readString(moved, StandardCharsets.UTF_8)));
            System.out.println("file size positive=" + (Files.size(source) > 0));
            try (Stream<Path> walk = Files.walk(root)) {
                System.out.println("regular files=" + walk.filter(Files::isRegularFile).count());
            }
        } finally {
            try (Stream<Path> walk = Files.walk(root)) {
                walk.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FilesCrudDemo.java
java FilesCrudDemo
```

```text
folder directory=true
UTF-8 round trip=true
copy remains=false
moved regular file=true
contents equal=true
file size positive=true
regular files=2
```

**Step-by-step explanation:**

1. `Files.createTempDirectory` creates a private temporary directory; the actual name has a random suffix, yet the example does not print the path so stdout stays deterministic.
2. `Files.createDirectories` creates both `docs` and `notes` inside the temporary directory.
3. `Files.writeString` writes Vietnamese text in `UTF-8` with `CREATE_NEW`, so it does not silently overwrite `note.txt`.
4. `Files.copy` creates `copy.txt`. After `Files.move(copy, moved)`, the path `copy.txt` is gone, while `moved.txt` is a valid file.
5. `Files.readString` reads text from both files and confirms the data is unchanged. `Files.size(source)` gives the **byte** count, not the Java `char` count.
6. `Files.walk(root)` traverses the entire tree, filters regular files, and finds two files: `note.txt`, `moved.txt`.
7. The `finally` block cleans up temporary files/directories from deepest to shallowest using `Comparator.reverseOrder()`; `walk` is closed inside `try-with-resources`.

Although the example imports `StandardCopyOption` for easy extension, this demo **does not use** `REPLACE_EXISTING`: if the destination already exists, normal copy/move operations can fail instead of overwriting. On a user-specified directory tree, recursive deletion is a dangerous action; the example only cleans up a temporary directory **that it just created itself**, and is not code for deleting an arbitrary path.

**Compatibility:** Files in the example are created on the default filesystem, so behavior matches Java 17 in standard environments. `IOException` can still occur if the environment denies writes/deletes or runs out of space; the program does not guarantee filesystem operations always succeed.

## 6. `Files.readString`, `writeString`, and Large Data

### Reading or Writing Small Text Files

With Java 11+:

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
```

This is an **illustrative snippet**: `Path path` must be declared, `Files`/`StandardCharsets` imported, and `IOException` handled. It is suitable for configs, small text files, and moderately sized snapshots.

If you need to read a large file line by line, choose `Files.newBufferedReader(path, UTF_8)` or `Files.lines(path, UTF_8)`, rather than putting the entire file into a single string. If you need to process binary files, choose `Files.newInputStream`, `Files.newOutputStream`, or `Files.newByteChannel`.

### Streaming APIs Must Be Closed

Example of reading line by line:

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank()).forEach(System.out::println);
}
```

This is an **illustrative snippet**, requiring imports for `java.util.stream.Stream`, `Path`, `Files`, and the corresponding charset. `Files.lines` holds an underlying file resource; **calling a terminal operation does not replace closing**. Use `try-with-resources` to close the stream.

Similarly, `Files.list(dir)`, `Files.walk(dir)`, and `Files.find(...)` return streams tied to system resources. Forgetting to close them leaks descriptors or handles, especially in continuously running services.

### Byte I/O and Charset Are Two Different Concerns

`Path` and `Files` do not automatically turn binary data into text. When reading text, specify an appropriate charset (typically `StandardCharsets.UTF_8`); when reading images/ZIPs, process bytes.

Do not use `String.length()` to compute the byte count of a UTF-8 file; a Vietnamese character or emoji can require multiple bytes. `Files.size(path)` measures the file's **byte count**, whereas `String.length()` measures the string's **UTF-16 code units**.

## 7. Example 3 — `java.io.File` Interoperability When Legacy Libraries Require It

Create the file `FileInteropDemo.java`:

```java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class FileInteropDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("interop-");
        try {
            Path child = root.resolve("report.txt");
            File legacy = child.toFile();
            System.out.println("same path=" + legacy.toPath().equals(child));
            System.out.println("before create=" + Files.exists(child));
            Files.writeString(child, "report", StandardCharsets.UTF_8);
            System.out.println("after create=" + legacy.isFile());
            System.out.println("legacy name=" + legacy.getName());
            System.out.println("read=" + Files.readString(child, StandardCharsets.UTF_8));
            try {
                Files.readString(root.resolve("missing.txt"));
            } catch (NoSuchFileException e) {
                System.out.println("missing exception=" + e.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(root.resolve("report.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileInteropDemo.java
java FileInteropDemo
```

```text
same path=true
before create=false
after create=true
legacy name=report.txt
read=report
missing exception=NoSuchFileException
```

In the example, `root` belongs to the default filesystem so `child.toFile()` is valid. `File.toPath()` converts back to a `Path` representation and compares equal to the same path.

**`Path.toFile()` is not universal**: if `Path` belongs to a file system provider other than the default filesystem, the method can throw `UnsupportedOperationException`. Therefore **do not convert to `File` unless you genuinely need a legacy API**.

**`Files.exists(path)` is not a conclusive check:** the method can return `false` if existence state cannot be determined (for example, lacking permissions). When performing an operation requiring the file to exist, call `Files.readString`, `Files.newInputStream`, or the specific API directly and **handle `IOException`**, instead of blindly trusting a prior `exists` result.

## 8. Important Path-Manipulation Choices

### `Path.of` and Relative Paths

`Path.of("data", "output.txt")` creates a path **relative** to the filesystem's working context; on the default filesystem, this is usually the process's working directory. Across IDEs, terminals, test runners, and deployment environments, the working directory can differ.

When a file must live inside a configured directory, define a root and use `resolve` on that root rather than relying on a relative path of uncertain meaning.

`Path.of("data/output.txt").toAbsolutePath()` does not automatically verify the file exists, whereas `toRealPath()` normally requires the file entry to exist and be accessible.

### `normalize`, `toAbsolutePath`, and `toRealPath`

| Method | Property | Accesses filesystem? |
|---|---|---|
| `normalize()` | Collapses `.`, `..` syntactically | No |
| `toAbsolutePath()` | Converts to absolute path per provider | Usually does not check existence |
| `toRealPath()` | Resolves real path, handles links per options | Yes; usually requires entry to exist |
| `Files.isSameFile(a, b)` | Asks whether two current paths point to the same file | May access filesystem |

**A normalized path does not mean a safe path.** For example, an application has an allowed upload directory where users control part of the path; a path containing `..` can escape the root. Even after `normalize`, a symbolic link inside the root can point outside.

Do not use plain string checks like `candidate.toString().startsWith(root.toString())` to decide whether a path belongs under the root: the string `/data/uploads2` also starts with `/data/uploads`. `Path.startsWith(other)` compares by **path components**, which is better than string prefix checking, yet **still does not eliminate symlink or concurrent modification risks**.

## 9. Symbolic Links: A Major Reason to Use `Path` + `Files`

A **symbolic link** is a filesystem entry that references another path. When a path points to a symlink, operating through the link versus operating on **the symlink itself** can yield very different results.

APIs to know:

- `Files.isSymbolicLink(path)`: checks whether the entry is considered a symbolic link.
- `Files.readSymbolicLink(path)`: reads the target path stored by the symlink.
- `Files.createSymbolicLink(link, target)`: creates a symlink; may require special privileges/environment conditions.
- `LinkOption.NOFOLLOW_LINKS`: passed to supporting operations to avoid following symbolic links.
- `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)`: retrieves attributes of the link itself rather than the target object when needed.
- `Path.toRealPath(...)`: retrieves the real path based on the filesystem; by default normally resolves links unless `NOFOLLOW_LINKS` is used.

**When to pay the closest attention?** Scanning uploads, deleting files, synchronization, backups, reading user-supplied paths, confining operations within an allowed root.

A defense written solely as:

```java
Path candidate = root.resolve(userInput).normalize();
if (!candidate.startsWith(root)) {
    throw new SecurityException("Outside root");
}
```

is **illustrative and not safe enough to deploy directly**. It only blocks one class of paths escaping the root syntactically if `root` already has the same type/format and proper normalization. It does **not** block symlinks leading outside the root or attacks that swap links between check time and operation time (*TOCTOU*).

In sensitive workflows, you must define a threat model, use appropriate real-path checks when the entry exists, avoid following links unnecessarily, and when available use operations relative to a secure directory handle (e.g., `SecureDirectoryStream` if the provider supports it). Protecting against races requires explicit filesystem design; no single `normalize()` call solves everything by itself.

## 10. Creating, Deleting, and Traversing Directories Properly

### Creating Directories

`Files.createDirectory(path)` creates **one** directory, requiring an appropriate parent to already exist. `Files.createDirectories(path)` can create an entire chain of missing parents.

Note that `createDirectories` does not mean the multi-level operation is completely atomic: if an error happens halfway through, some parent directories may already have been created.

### Deleting

`Files.delete(path)` deletes a file, symlink, or empty directory; for directories with children, it **does not automatically delete recursively**. `Files.deleteIfExists(path)` ignores the non-existent path case, yet can still throw `IOException` for other errors.

Deleting an entire directory tree requires clear logic for ownership and deletion order. When data belongs to users or contains symlinks, control is even more critical. **Do not copy a temporary-directory cleanup example into a feature that deletes arbitrary paths taken from a form.**

### Single-Level vs. Recursive Traversal

- `Files.list(dir)`: direct entries in the directory, does not traverse deeper automatically.
- `Files.newDirectoryStream(dir)`: directory entry iterator, useful for controlled directory iteration.
- `Files.walk(dir)`: stream walking the directory tree, depth-first in traversal details, with depth options.
- `Files.walkFileTree(root, visitor)`: visitor callbacks, controlling directory entry/exit and per-entry I/O error handling; suited for copying/deleting trees or scanning tools with multiple processing branches.

Do not blindly call `Files.walk(root)` and force traversing an entire tree of millions of files just to check one specific name when a simpler algorithm exists. Close streams and consider depth, permissions, symbolic links, cycles, and exception-handling strategies.

### When You Need to Watch Filesystem Changes

`WatchService` can monitor create, delete, and modify events in directories on supporting providers. It is not an absolute synchronization solution: events can be coalesced, missed under certain conditions, or report `OVERFLOW`; a rescan mechanism is needed if the application demands exact state. Do not assume `WatchService` "watches all subdirectories" by default; specific directories usually must be registered by design.

## 11. Avoiding TOCTOU Bugs: "Check Before Acting" Gives No Guarantee

**TOCTOU** (*time-of-check to time-of-use*) is a bug where system state changes between the check step and the action step. Example:

```java
if (!Files.exists(target)) {
    Files.writeString(target, text);
}
```

This is **illustrative code showing a racy pattern**, not a safe solution. Another thread/process can create `target` right after `exists` returns `false` and before `writeString`; the default write mode could then **overwrite** the newly created file.

If the intent is **to create only when it does not yet exist**, use `CREATE_NEW` so the filesystem enforces the file-creation condition under the operation's semantics:

```java
Files.writeString(target, text, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
```

This is an **illustrative snippet** requiring `target`, `text`, and `IOException` handling. For untrusted data and symlinks, you must still examine parent directory permissions, the provider, and the entire protection model.

Similarly, `Files.exists`/`isRegularFile`/`isReadable` are merely **point-in-time state queries**; afterward the file can be deleted, have permissions changed, or be replaced. For tasks requiring accurate results, perform the required operation and handle exceptions.

## 12. Safe File Writing and Atomicity

If a program writes directly to an important config file or document, a mid-operation failure can leave a half-written file. `Files.writeString` does not automatically provide an all-or-nothing write transaction.

A common strategy:

1. Create a temporary file **in the same target directory or filesystem** if appropriate.
2. Write the new content into the temporary file and close/flush the writer.
3. Validate content or verify checksums as required.
4. Move the temporary file to the destination, optionally requesting `ATOMIC_MOVE` when supported by the filesystem.
5. If `ATOMIC_MOVE` is unsupported, explicitly decide whether to **reject the operation** or **fall back non-atomically**, based on requirements.
6. Clean up the temporary file on failure; consider permissions, attributes, and crash recovery.

Illustrative pattern, **not a standalone program**:

```java
Path temporary = Files.createTempFile(target.getParent(), "write-", ".tmp");
try {
    Files.writeString(temporary, text, StandardCharsets.UTF_8);
    Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
} finally {
    Files.deleteIfExists(temporary);
}
```

The snippet above requires imports for `Path`, `Files`, `StandardCharsets`, and `StandardCopyOption`, requires `target.getParent()` to be an existing directory, and defined variables. It does **not** include a target replacement policy and has no fallback. `ATOMIC_MOVE` can throw `AtomicMoveNotSupportedException`. **An atomic rename does not mean data is durable on disk across power loss**; true durability may require syncing the file/directory and mechanisms suited to the filesystem.

Do not assume `REPLACE_EXISTING` + `ATOMIC_MOVE` always has identical replacement semantics across every provider. For critical file writes, check actual support and contracts.

## 13. Where Does `File` Still Fit?

### 13.1 Legacy Library APIs Requiring `File`

Many libraries, frameworks, test tools, or legacy SDKs have constructors like `SomeLibrary(File source)`. If you already have a `Path` on the default filesystem, you can use `path.toFile()` at the integration boundary.

If receiving a `File` from a legacy API, call `file.toPath()` and continue operating with `Files`. This is a **simple compatibility conversion**; there is no need to rewrite all data through intermediate streams.

### 13.2 Maintaining a System That Consistently Uses `File`

A stable module with a public API using `File` and hundreds of call sites does not have to be converted all at once. When adding new functionality requiring copy/move, metadata, symlinks, or specific exceptions, you can convert `File` to `Path` locally and use `Files`, instead of breaking the public API and triggering a massive migration.

### 13.3 When Needs Are Simple and the Contract Is Sufficient

`File` is not "wrong" if logic genuinely only needs to check a path in a test or legacy integration. What matters is **understanding the semantics** of `exists`, `delete`, `renameTo`, and failure cases, rather than enforcing an absolute ban.

### 13.4 Very Old Java Versions

`Path`/`Files` appeared in Java 7, while `Path.of` and `Files.readString/writeString` appeared in Java 11. Projects constrained to Java 6 or earlier lack standard NIO.2. However, on **Java 17+**, there is normally no technical reason to keep writing all new file operations with `File` solely for Java version compatibility.

## 14. Notes on Providers and Portability

**`Path` is not just a string.** A `Path` belongs to a `FileSystem` with its own provider and rules. Two paths from different providers or filesystems may be incompatible for certain combine, comparison, or move operations.

Points to remember:

- `Path.of(...)` creates a `Path` in the runtime's **default filesystem**.
- `FileSystem.getPath(...)` can create a `Path` for a specific provider.
- `File.toPath()` works with `File` and the default filesystem.
- `Path.toFile()` can throw `UnsupportedOperationException` for a `Path` from a non-default provider.
- Some `Files` methods can throw `UnsupportedOperationException`, `IOException`, or corresponding exceptions if a feature is unsupported.
- POSIX file permissions, owner/group, ACLs, or extended attributes are not uniform across Windows/Linux/virtual filesystems.
- Symlink creation may require special privileges. Do not assume symlink-creation tests work on every machine.
- `Files.copy` across different providers depends on contract, may lose metadata, or may fail; test your target system rather than making blanket inferences.

The `Path` and `Files` APIs **help clarify filesystem boundaries**, yet do not automatically guarantee all operations behave uniformly across all providers. When building cross-OS tools, testing against real filesystems and permissions is just as important as choosing the API.

## 15. Common Mistakes When Switching from `File` to `Path`/`Files`

1. **Thinking creating a `Path` creates a file:** `Path.of("x.txt")` only creates a path object; you must call `Files.createFile`, `writeString`, etc.
2. **Treating `normalize` as the real path:** it only transforms syntax, without resolving symlinks or guaranteeing the entry exists.
3. **Relying on the working directory unknowingly:** relative paths may point to different places between IDEs and production.
4. **Reading huge files with `Files.readString`:** easily consumes memory; use buffered readers/streams when processing large data.
5. **Forgetting to close `Files.lines`/`list`/`walk`:** streams hold system resources; use `try-with-resources`.
6. **Believing `Files.copy(dir, target)` copies recursively:** copying a directory entry **does not** automatically copy all children; a tree traversal strategy is needed.
7. **Thinking `Files.delete` deletes non-empty directories:** the method does not clean up an entire tree automatically.
8. **Using `Files.exists` then writing without options:** creates a race and risks overwriting data; use `CREATE_NEW` when create-only-if-absent is required.
9. **Thinking `Files.exists(path) == false` proves the file definitely does not exist:** it could be due to undetermined state; run the operation and handle exceptions.
10. **Enabling `REPLACE_EXISTING` thoughtlessly:** easily destroys existing data.
11. **Assuming `ATOMIC_MOVE` is always supported:** handle `AtomicMoveNotSupportedException` and decide a sensible fallback.
12. **Believing atomic move guarantees durability:** atomic rename and flush/fsync are two different requirements.
13. **Converting every `Path` to `File`:** non-default providers may not support `toFile()`.
14. **Scanning/deleting directories from user-supplied paths while ignoring symlinks:** can escape the allowed area; requires a threat model and race controls.
15. **Reading text without managing charset:** use `StandardCharsets.UTF_8` or the format-mandated charset; do not assume a filename extension dictates encoding.
16. **Not checking filesystem errors:** permissions, missing paths, modified files, or locks can cause operations to fail; do not lump every error into "file not found."
17. **Forgetting the difference between file metadata and file content:** `Files.size` returns bytes; `String.length()` returns UTF-16 code units.
18. **Testing on only one OS:** path separators, valid filename characters, case sensitivity, symbolic links, and permissions can differ.
19. **Concluding `Files` is non-blocking I/O:** it is a filesystem utility API; synchronous reads/writes normally still block the thread.
20. **Using `isSameFile` instead of syntactic comparison when only comparing names:** `isSameFile` can hit the filesystem and throw `IOException`; `Path.equals` has a different meaning.

## 16. Quick Selection Checklist

| If the application needs... | Prefer... | Why |
|---|---|---|
| New Java 17 code handling paths/files | `Path` + `Files` | Clear API, options, exceptions |
| Resolving parent/child or relative paths | `resolve`, `relativize`, `normalize` | No manual string concatenation |
| Reading/writing small text files | `Files.readString/writeString` | Concise, explicit charset |
| Reading large text files line by line | `Files.newBufferedReader` or `Files.lines` | Avoids holding the whole file in RAM |
| Copying/moving/deleting | `Files.copy/move/delete` | Has options and error descriptions |
| Traversing, filtering, or operating on directory trees | `Files.list/walk/walkFileTree` | Suited for tree structures, error handling |
| Inspecting attributes or handling symbolic links | `Files.readAttributes`, `LinkOption` | Clearer information |
| Detecting directory changes | `WatchService` | Event system with defined limits |
| Integrating a library accepting only `java.io.File` | `path.toFile()` if supported | Preserves compatibility |
| Receiving `File` from a legacy library then operating modernly | `file.toPath()` + `Files` | Easy clarity improvement without full migration |
| Creating a file only if it does not exist yet | `Files.writeString(..., CREATE_NEW, WRITE)` | Avoids check-then-write race |
| Writing important files without exposing half-written versions | Temp file + validate + checked move | Explicit atomicity and error strategy |

## 17. Self-Check Knowledge Questions

**Q1.** Does calling `Path.of("notes.txt")` create a file on disk?  
**Answer:** No. `Path` is only a path representation. You must call an API such as `Files.createFile` or `Files.writeString` to affect the filesystem.

**Q2.** A `file.delete()` call returns `false`; why is `Files.delete(path)` usually more useful?  
**Answer:** `Files.delete` can throw `IOException`/specific subtypes and helps show whether failure was due to a missing file, non-empty directory, or another reason (depending on the provider).

**Q3.** Does `Files.copy(sourceDirectory, targetDirectory)` copy the entire subtree?  
**Answer:** No. A separate recursive copy design is needed when wanting to copy an entire tree.

**Q4.** Is `Files.readString(path, UTF_8)` suitable for a 100 GB file?  
**Answer:** Normally no, because it loads data into memory. Use a buffered reader, stream, or chunked processing.

**Q5.** Does checking `Files.exists(path) == false` and then calling `Files.writeString(path, data)` guarantee not overwriting a concurrently created file?  
**Answer:** No. There is a TOCTOU gap; use `CREATE_NEW` if it must only be created when absent.

**Q6.** Why is `normalize()` not enough to guarantee a child path stays inside an upload root?  
**Answer:** It only processes `.` and `..` syntactically; symbolic links and concurrent filesystem modifications can direct operations to another location.

**Q7.** Is `Path.toFile()` guaranteed to work with a ZIP filesystem?  
**Answer:** No. A `Path` from a non-default provider may not support conversion to `File`.

**Q8.** If `Files.move(source, target, ATOMIC_MOVE)` throws `AtomicMoveNotSupportedException`, what should you do?  
**Answer:** Depends on requirements: fail in a controlled way if atomicity is mandatory, or decide on a non-atomic fallback and report/design handling for intermediate states.

**Q9.** When is it still reasonable to use `java.io.File`?  
**Answer:** When legacy APIs require `File`, the project does not yet need a large migration, or small needs have a clear contract; you can convert to `Path` at boundaries needing NIO.2 features.

**Q10.** Once `Files.walk(dir).count()` finishes, does the stream close automatically?  
**Answer:** Do not assume so. The `Files.walk` stream holds resources and must be closed inside `try-with-resources`.

## Conclusion

For **Java 17+**, treat **`Path` + `Files` as the default choice** for new code handling paths, files, and directories. `Path` describes locations and path manipulation, while `Files` interacts with the filesystem via clear APIs, rich exceptions, create/copy/move options, metadata, and tree traversal. `java.io.File` remains useful at **legacy compatibility boundaries**; you can convert via `file.toPath()` or `path.toFile()` when supported by the provider.

Even more important than API names is understanding the contracts: **creating a path differs from creating a file; querying state differs from performing an operation; `normalize` differs from real path; copying a directory differs from recursive copying; atomic move differs from durability; streams hold resources that must be closed**. When these principles are applied properly, `Path` and `Files` make Java code easier to read, easier to debug, and easier to extend.

### Java SE 17 Documentation

- [`Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html) and [`Paths`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html)
- [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`java.io.File`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html)
- [`StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [`StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [`LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html), [`FileVisitOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html)
- [`BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
- [`WatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)