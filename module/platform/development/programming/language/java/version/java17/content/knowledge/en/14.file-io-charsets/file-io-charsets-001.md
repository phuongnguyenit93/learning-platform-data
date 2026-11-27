# Path and Files for File Operations in Java 17

In Java 17, the modern API for working with paths and files resides primarily in the `java.nio.file` package. The two most important types are:

- **`Path`** describes a path to a file or directory. It helps join, split, normalize, and compare paths according to the file system.
- **`Files`** provides actual operations on the file system: checking attributes, reading/writing content, creating directories, copying, moving, deleting, and traversing directory trees.

`Path` is the object describing a location; `Files` is the utility class performing operations at that location.

```text
Path
 │
 ├── of / resolve / normalize / relativize
 │       manipulate path structure
 │
 └── passed to Files
          ├── exists / isDirectory / size
          ├── readString / writeString
          ├── copy / move / delete
          └── list / walk / readAttributes
```

This lesson uses the standard APIs applicable in Java 17, preferring `Path.of` and `Files`. There is no need to concatenate path strings manually or rely on the legacy `java.io.File` API for new code.

## 1. Why Use Path and Files?

A common approach is concatenating paths using strings:

```java
String file = "data" + "/" + "reports" + "/" + "summary.txt";
```

This approach has several problems:

- Path separators can differ between Windows and Unix-like systems.
- It is difficult to distinguish relative paths, absolute paths, and path components.
- File operations still require exception handling and file type checks.
- Arbitrary string concatenation can easily produce invalid paths or path traversal vulnerabilities when external input is involved.

With `Path`:

```java
import java.nio.file.Path;

Path file = Path.of("data", "reports", "summary.txt");
System.out.println(file);
```

`Path.of` creates a `Path` object from one or more components. The default file system provider interprets path syntax appropriately for the platform.

Key benefits:

1. **Independent of path joining syntax:** use `resolve` instead of manually adding `/` or `\\`.
2. **Dedicated API:** retrieve file name, parent directory, root, component count, and normalize paths.
3. **Integrates naturally with Files:** most methods of `Files` accept `Path`.
4. **Easy to test:** temporary directories or fixture directories can be used.
5. **Clear error reporting:** file operations declare or throw `IOException` and specific error types.

## 2. Creating a Path with Path.of

`Path` is an interface. The common way in Java 17 is to call the static factory `Path.of`:

```java
import java.nio.file.Path;

Path relative = Path.of("documents", "notes.txt");
Path absolute = Path.of("C:\\", "work", "project", "README.md");
```

On Windows, an absolute path can take the form `C:\\work\\project\\README.md`. On Linux/macOS, an absolute path typically starts with `/`, for example `/home/dev/project/README.md`.

You can pass a single string:

```java
Path path = Path.of("data/reports/summary.txt");
```

Separator syntax is interpreted according to the file system in use. When creating a structured path, the multi-component form `Path.of("data", "reports", "summary.txt")` is often easier to read and less dependent on separators.

### 2.1. Path.of and Paths.get

`Paths.get(...)` is still a valid API in Java 17; it also creates a `Path`. For new code, `Path.of(...)` is usually the shorter and more direct choice:

```java
Path first = Path.of("data", "input.txt");
Path second = java.nio.file.Paths.get("data", "input.txt");
```

Both approaches serve the same purpose. You do not need to replace all working code just because you see `Paths.get`; it is not a deprecated or removed API in Java 17.

### 2.2. A Path Does Not Guarantee the File Exists

```java
Path path = Path.of("data", "input.txt");
```

The line above only creates an object describing the path. It **does not create a file**, does not check whether the file exists, and does not read from disk.

Only when calling operations such as `Files.exists(path)`, `Files.readString(path)`, or `Files.createFile(path)` does the program interact with the file system.

### 2.3. Path Is Immutable

Operations on a `Path` create a new `Path` without modifying the original object:

```java
Path base = Path.of("data");
Path report = base.resolve("report.txt");

System.out.println(base);   // data
System.out.println(report); // data/report.txt (display format depends on OS)
```

You can reuse `base` for many different paths without worrying that a previous `resolve` call will mutate it.

## 3. Distinguishing Relative and Absolute Paths

### 3.1. Relative Paths

A relative path does not start from the root of the file system:

```java
Path path = Path.of("data", "report.txt");

System.out.println(path.isAbsolute()); // false
```

It is resolved relative to the current working directory when it needs to be converted into an absolute path or used in a file operation.

The working directory is usually the directory from which the Java process is launched; it may differ from the directory containing the Java source files or the JAR file.

### 3.2. Absolute Paths

An absolute path specifies a location starting from the root of the filesystem:

```java
Path absolute = Path.of("/var/app/data/report.txt");

System.out.println(absolute.isAbsolute()); // true on Unix-like systems
```

The example above is a Unix-style path. Do not use that string as a Windows path and vice versa.

### 3.3. Converting to an Absolute Path

`toAbsolutePath()` creates an absolute path based on the working directory if the original path is relative:

```java
Path relative = Path.of("data", "report.txt");
Path absolute = relative.toAbsolutePath();

System.out.println(absolute);
```

This method **does not guarantee** that the path exists, does not automatically create directories, and does not always resolve symbolic links. It produces an absolute representation according to the current filesystem.

### 3.4. Inspecting Path Components

```java
Path path = Path.of("reports", "2025", "summary.csv");

System.out.println(path.getFileName());  // summary.csv
System.out.println(path.getParent());    // reports/2025
System.out.println(path.getRoot());      // null if it is a relative path
System.out.println(path.getNameCount()); // number of name elements
System.out.println(path.getName(0));     // reports
System.out.println(path.isAbsolute());   // false
```

Notes:

- `getFileName()` returns the last component, which is not necessarily a file; it can be a directory name.
- `getParent()` returns the parent or `null` if there is no parent.
- `getRoot()` returns the root of an absolute path; for a relative path it is usually `null`.
- `getNameCount()` counts name elements, excluding the root.
- `getName(i)` retrieves a component by zero-based index.

Do not assume a path always has at least one component. Check `getNameCount()` and handle `null` when calling methods that may not return a result.

## 4. resolve, resolveSibling, and relativize

This is the most important group of operations when constructing paths.

### 4.1. resolve — Appending Components to a Base Path

`resolve` appends a child path to the current path:

```java
Path root = Path.of("data");
Path report = root.resolve("reports");
Path file = report.resolve("summary.txt");

System.out.println(file);
```

Diagram:

```text
data
  └── reports
        └── summary.txt
```

You can pass multiple components by creating a `Path` first:

```java
Path file = Path.of("data")
        .resolve(Path.of("reports", "2025", "summary.csv"));
```

If the argument to `resolve` is an absolute path, it is returned as the result instead of being appended to the base path:

```java
Path base = Path.of("data");
Path absolute = Path.of("/tmp/output.txt");

System.out.println(base.resolve(absolute)); // /tmp/output.txt on Unix
```

Therefore, when combining paths from user input, check whether the input is an absolute path; never assume `resolve` always keeps the result inside the base directory.

### 4.2. resolveSibling — Replacing the Last Component

`resolveSibling` creates a path with the same parent, replacing the last component with a new name or path:

```java
Path source = Path.of("data", "report.txt");
Path backup = source.resolveSibling("report.txt.bak");

System.out.println(backup); // data/report.txt.bak
```

It is commonly used when creating temporary file names, backup files, or output files alongside an original file.

### 4.3. relativize — Computing a Relative Path Between Two Paths

`relativize` computes a relative path from a base path to a target path:

```java
Path base = Path.of("data", "reports");
Path target = Path.of("data", "exports", "summary.csv");

Path relative = base.relativize(target);

System.out.println(relative); // ../exports/summary.csv
```

It does not read the filesystem and does not check whether the target path exists. This is a calculation based purely on path structure.

Both paths must belong to the same filesystem/provider and have compatible roots. On Windows, two paths on different drives cannot always be relativized; this may throw `IllegalArgumentException`.

### 4.4. normalize — Normalizing Dots and Double Dots

`normalize` removes syntactically redundant elements such as `.` and can collapse `name/..` pairs:

```java
Path path = Path.of("data", "reports", "..", "exports", ".", "summary.csv");

Path normalized = path.normalize();

System.out.println(normalized); // data/exports/summary.csv
```

`normalize` only manipulates the path representation and **does not access the filesystem**. It does not verify that the file exists and does not resolve symbolic links.

This matters when symbolic links are present: lexically collapsing `link/..` is not always equivalent to following the real link and then returning to its parent. Do not use `normalize` as a complete security validation mechanism.

## 5. toRealPath and Symbolic Links

`toRealPath()` accesses the filesystem to obtain the real path of an existing object:

```java
Path real = Path.of("data", "report.txt").toRealPath();
System.out.println(real);
```

Typically, this method:

- Converts the path into an absolute path.
- Verifies that the object exists.
- Removes redundant elements and resolves symbolic links by default.
- May throw `IOException` if the object is not found, inaccessible, or a filesystem error occurs.

You can request not following the final symbolic link using `LinkOption.NOFOLLOW_LINKS`:

```java
import java.nio.file.LinkOption;

Path realWithoutFollowingFinalLink =
        Path.of("data", "shortcut").toRealPath(LinkOption.NOFOLLOW_LINKS);
```

Depending on the filesystem and link structure, intermediate components may still be handled according to the provider's rules; consult the Javadoc when exact symbolic link control is required.

### 5.1. Distinguishing the Three Methods

| Method | Accesses filesystem? | Requires file to exist? | Symbolic link handling |
|---|---|---|---|
| `normalize()` | No | No | Does not resolve |
| `toAbsolutePath()` | Relies on filesystem/working directory | No | Does not guarantee link resolution |
| `toRealPath()` | Yes | Yes | Resolves links by default |

Do not equate an absolute path with a real path. An absolute path can still contain symbolic link components or unnormalized names.

## 6. Inspecting Files and Directories with Files

`java.nio.file.Files` is a utility class containing static methods for filesystem operations.

### 6.1. Checking Existence

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "report.txt");

if (Files.exists(path)) {
    System.out.println("Path exists");
} else {
    System.out.println("Not found or cannot be determined");
}
```

Key point to remember: `Files.exists` also returns `false` if the provider cannot determine existence due to missing permissions or other errors. It does not guarantee that the subsequent operation will succeed.

`Files.notExists(path)` can also return `false` if existence cannot be determined. Therefore, when both `exists` and `notExists` return `false`, the status is unknown.

Do not write critical logic like "check exists first, then write" expecting to prevent all race conditions. Between the check and the operation, another process may alter the filesystem. Perform the intended operation and handle the actual exception.

### 6.2. Checking Object Types

```java
if (Files.isRegularFile(path)) {
    System.out.println("Regular file");
}

if (Files.isDirectory(path)) {
    System.out.println("Directory");
}

if (Files.isSymbolicLink(path)) {
    System.out.println("Symbolic link");
}
```

The `isRegularFile` and `isDirectory` methods follow symbolic links by default. If you need to inspect the link itself rather than its target, pass `LinkOption.NOFOLLOW_LINKS`:

```java
boolean isDirectoryWithoutFollowing =
        Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS);
```

With `NOFOLLOW_LINKS`, a symbolic link is not treated as its target directory in this check.

### 6.3. Checking Access Permissions

```java
System.out.println(Files.isReadable(path));
System.out.println(Files.isWritable(path));
System.out.println(Files.isExecutable(path));
```

These methods provide advisory information at the time of the check. Permissions may change before the operation runs; the filesystem, running user, and operating system policies all affect the result.

### 6.4. Size and Modification Time

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;

Path path = Path.of("data", "report.txt");

long size = Files.size(path);
FileTime modified = Files.getLastModifiedTime(path);

System.out.println("Bytes: " + size);
System.out.println("Modified: " + modified);
```

`Files.size` returns the size in bytes, not the number of characters. For compressed files, sparse files, or special filesystems, logical size and physical disk usage may differ.

Metadata-reading operations may throw `IOException` or `SecurityException` depending on the environment.

## 7. Reading Text Content with Files and UTF-8

In Java 17, `Files.readString` and `Files.writeString` are convenient APIs (available since Java 11). Always specify the charset explicitly so data remains consistent across developer machines, servers, and containers.

### 7.1. Reading an Entire File as a String

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "message.txt");

String content = Files.readString(path, StandardCharsets.UTF_8);

System.out.println(content);
```

`readString` reads the entire file content into a single `String`. Therefore, it is suitable for moderately sized text files. Do not use it for very large files if you do not want to hold the entire content in memory.

Java 17 also provides an overload `Files.readString(path)` that uses UTF-8 by API contract; passing `StandardCharsets.UTF_8` explicitly still makes the program's intent clearer.

### 7.2. Writing a String to a File

```java
String content = """
        Java 17
        Path and Files
        UTF-8
        """;

Path output = Path.of("data", "message.txt");

Files.writeString(output, content, StandardCharsets.UTF_8);
```

The basic overload creates the file if it does not exist and writes the content, replacing any previous content. If the file already exists, previous content is truncated.

If you want explicit control over options:

```java
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.TRUNCATE_EXISTING;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        output,
        content,
        StandardCharsets.UTF_8,
        CREATE,
        TRUNCATE_EXISTING,
        WRITE
);
```

Do not use the default overload if business requirements state that an existing file **must not be overwritten**. In that case, choose appropriate options or create the file with `CREATE_NEW`.

### 7.3. Appending Content to the End of a File

```java
import static java.nio.file.StandardOpenOption.APPEND;
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        output,
        "A new log line\n",
        StandardCharsets.UTF_8,
        CREATE,
        WRITE,
        APPEND
);
```

`APPEND` writes content to the end of the file if the filesystem supports this operation. When multiple threads or processes write concurrently, do not assume large writes will always be appended as atomic records. For concurrent logging, use a logging framework or an appropriate synchronization mechanism.

### 7.4. Reading a File Line by Line

If the file is large or requires sequential processing, use `BufferedReader`:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "users.txt");

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

`try-with-resources` automatically closes the reader even if an error occurs while reading. This is the recommended pattern for open file resources in a program.

### 7.5. Files.lines — Processing a File with Streams

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "users.txt");

try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank())
         .forEach(System.out::println);
}
```

The stream returned by `Files.lines` holds an open file resource. Therefore, you must close the stream using `try-with-resources`, even when the pipeline ends with a terminal operation.

Do not store this stream in a field or return it from a method without clearly defining who is responsible for closing it.

## 8. Reading and Writing Bytes for Binary Files

Not every file is text. Images, PDFs, compressed archives, and encrypted data must be handled as bytes.

### 8.1. Reading All Bytes

```java
byte[] data = Files.readAllBytes(Path.of("data", "image.png"));
```

Suitable for small or medium files. For large files, reading everything into a `byte[]` can consume excessive memory.

### 8.2. Writing Bytes

```java
byte[] data = {0x01, 0x02, 0x03, 0x04};

Files.write(
        Path.of("data", "binary.dat"),
        data
);
```

`Files.write` with `byte[]` does not apply a charset. It writes the exact bytes provided.

### 8.3. Using Streams for Large Files

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("data", "large.bin");
Path target = Path.of("backup", "large.bin");

Files.createDirectories(target.getParent());

try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
```

You can use `Files.copy(source, target)` if you only need to copy a file; streams are suitable when you need to process content during transfer, such as computing a hash, filtering, or encrypting.

## 9. Creating Files and Directories

### 9.1. Creating a Single Directory

```java
Path directory = Path.of("data", "reports");

Files.createDirectory(directory);
```

`createDirectory` only creates **the final directory**. The parent must already exist; if the directory already exists, the operation usually throws `FileAlreadyExistsException`.

### 9.2. Creating All Missing Parent Directories

```java
Path directory = Path.of("output", "2025", "monthly");

Files.createDirectories(directory);
```

`createDirectories` also creates any missing parent directories. If a directory already exists, the method does not throw an error merely because it exists; however, if an existing component is not a directory, the operation can still fail.

This is a common pattern before writing a file into a new directory structure:

```java
Path output = Path.of("build", "reports", "summary.txt");
Files.createDirectories(output.getParent());
Files.writeString(output, "Report", StandardCharsets.UTF_8);
```

### 9.3. Creating a New File

```java
Path file = Path.of("data", "new.txt");

Files.createFile(file);
```

`createFile` creates an empty file and fails if the path already exists. It is useful when you need to guarantee that an existing file is not overwritten.

### 9.4. Creating Temporary Files and Directories

```java
Path tempFile = Files.createTempFile("app-", ".tmp");
Path tempDirectory = Files.createTempDirectory("app-work-");

System.out.println(tempFile);
System.out.println(tempDirectory);
```

You can specify a parent directory:

```java
Path workDir = Path.of("build", "tmp");
Files.createDirectories(workDir);

Path temp = Files.createTempFile(
        workDir,
        "report-",
        ".tmp"
);
```

Generated names are unique within the provider's mechanism. Temporary files are still disk resources; the application must have an appropriate cleanup policy, especially if the process can terminate abnormally.

## 10. Copying, Moving, and Deleting

### 10.1. Copy — Copying a File

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path source = Path.of("data", "report.txt");
Path target = Path.of("backup", "report.txt");

Files.createDirectories(target.getParent());

Files.copy(source, target);
```

By default, `Files.copy` does not overwrite an existing target. If you want to replace it:

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING
);
```

You can request copying basic attributes if supported by the provider:

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);
```

`COPY_ATTRIBUTES` requests copying file attributes; the exact level of support depends on the filesystem/provider.

For symbolic links, the default copy operation usually follows the link and copies the target object. If you want to copy the link itself, you can use `LinkOption.NOFOLLOW_LINKS`; detailed behavior depends on the provider.

### 10.2. Move — Moving or Renaming

```java
Path source = Path.of("data", "draft.txt");
Path target = Path.of("data", "final.txt");

Files.move(source, target);
```

If the target already exists, the operation does not overwrite it by default. You can request replacement:

```java
Files.move(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING
);
```

If the source and target are on the same filesystem, a move can often be performed as a rename operation. If they are on different filesystems, the provider may have to copy and then delete, or fail depending on the situation.

### 10.3. Atomic Move

When updating a configuration file or output file, you may want readers to see either the old version or the new version, never a half-written file. You can request `ATOMIC_MOVE`:

```java
Files.move(
        temporaryFile,
        destination,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING
);
```

If the filesystem does not support it, `AtomicMoveNotSupportedException` may be thrown. Do not assume atomic move works on every filesystem or across every mount/network share.

A common workflow:

1. Create a temporary file in the same directory/filesystem as the destination.
2. Write the full content to the temporary file.
3. Close the stream/writer.
4. Move the temporary file to the destination using `ATOMIC_MOVE` if supported by the provider.
5. Handle exceptions and clean up any leftover temporary file.

Creating the temporary file on the same filesystem increases the likelihood that atomic move is supported. Durability against power loss or hardware failure still depends on flush/fsync and the filesystem; an atomic rename does not automatically mean data has been durably persisted to the storage device.

### 10.4. Delete and deleteIfExists

```java
Files.delete(Path.of("data", "old.txt"));
```

`delete` throws `NoSuchFileException` if the path does not exist. To delete if present without failing solely because the file is absent:

```java
boolean deleted = Files.deleteIfExists(Path.of("data", "old.txt"));
System.out.println(deleted);
```

`deleteIfExists` returns `true` if the file was deleted, and `false` if there was no object to delete.

A directory can only be deleted when empty. If it still contains child entries, the operation usually throws `DirectoryNotEmptyException`.

**Be careful:** deleting files has real impact on data. Before deleting from a list or pattern, determine the exact scope and avoid letting user-supplied paths decide deletions arbitrarily.

## 11. Listing Directory Contents

### 11.1. Files.list — Direct Entries

```java
Path directory = Path.of("data");

try (var entries = Files.list(directory)) {
    entries.forEach(System.out::println);
}
```

`Files.list` only lists direct entries inside the directory; it does not descend into subdirectories.

The result is a `Stream<Path>` and must be closed. Use `try-with-resources` as shown in the example.

### 11.2. Filtering by Extension

```java
try (var entries = Files.list(Path.of("data"))) {
    entries.filter(Files::isRegularFile)
           .filter(path -> path.getFileName().toString().endsWith(".txt"))
           .forEach(System.out::println);
}
```

This is a simple way to find text files at a single directory level. Case sensitivity when comparing extensions depends on application conventions; not all filesystems handle case sensitivity the same way.

### 11.3. DirectoryStream

If you need to iterate entries using an iterator-style loop, use `DirectoryStream`:

```java
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path directory = Path.of("data");

try (DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory, "*.txt")) {
    for (Path entry : stream) {
        System.out.println(entry);
    }
}
```

The glob filter `*.txt` helps restrict entries by name. `DirectoryStream` is also a resource that must be closed.

## 12. Traversing Directory Trees with Files.walk

`Files.walk` creates a stream that traverses a directory tree depth-first. By default, it does not follow symbolic links.

```java
Path root = Path.of("project");

try (var paths = Files.walk(root)) {
    paths.forEach(System.out::println);
}
```

### 12.1. Limiting Depth

```java
try (var paths = Files.walk(Path.of("project"), 2)) {
    paths.forEach(System.out::println);
}
```

Depth 0 is the root itself; depth 1 is the direct entries; depth 2 descends one level further.

### 12.2. Finding Only .java Files

```java
try (var paths = Files.walk(Path.of("src"))) {
    paths.filter(Files::isRegularFile)
         .filter(path -> path.toString().endsWith(".java"))
         .forEach(System.out::println);
}
```

### 12.3. Files.find — Filtering with Attributes

`Files.find` accepts a predicate taking both `Path` and `BasicFileAttributes`:

```java
import java.nio.file.attribute.BasicFileAttributes;

try (var found = Files.find(
        Path.of("project"),
        10,
        (path, attrs) -> attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".log")
)) {
    found.forEach(System.out::println);
}
```

If multiple attributes are needed, the predicate can inspect `attrs.size()`, `attrs.lastModifiedTime()`, etc. This avoids issuing separate metadata queries for each path.

### 12.4. Files.walk and Symbolic Links

By default, `Files.walk` does not follow symbolic links. If you pass `FileVisitOption.FOLLOW_LINKS`, it can follow links and must handle filesystem cycles.

```java
import java.nio.file.FileVisitOption;

try (var paths = Files.walk(
        Path.of("project"),
        FileVisitOption.FOLLOW_LINKS
)) {
    paths.forEach(System.out::println);
}
```

Following symbolic links can lead outside the root directory or create cycles. Unless truly needed, keeping the default behavior is more predictable.

## 13. Files.walkFileTree for Advanced Traversal

When you need custom handling upon entering a directory, visiting a file, encountering access errors, or exiting a directory, use `Files.walkFileTree` with a `FileVisitor`.

Example printing only regular files:

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

Path root = Path.of("project");

Files.walkFileTree(root, new SimpleFileVisitor<>() {
    @Override
    public FileVisitResult visitFile(
            Path file,
            BasicFileAttributes attrs
    ) {
        if (attrs.isRegularFile()) {
            System.out.println(file);
        }
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFileFailed(
            Path file,
            IOException exc
    ) {
        System.err.println("Cannot visit " + file + ": " + exc);
        return FileVisitResult.CONTINUE;
    }
});
```

Important callbacks:

| Callback | Timing |
|---|---|
| `preVisitDirectory` | Before traversing directory contents |
| `visitFile` | When encountering a file or an unfollowed link |
| `visitFileFailed` | When a path cannot be accessed |
| `postVisitDirectory` | After finishing traversal of a directory |

`FileVisitResult` controls the traversal:

- `CONTINUE`: continue traversal.
- `SKIP_SUBTREE`: skip the rest of the current directory.
- `SKIP_SIBLINGS`: skip remaining sibling entries.
- `TERMINATE`: stop the entire traversal.

Use this API when building backup tools, file inventories, directory cleanup utilities, or detailed tree traversal error reporting.

## 14. Reading Attributes with BasicFileAttributes

`Files.readAttributes` allows reading a group of metadata in a single call:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

Path path = Path.of("data", "report.txt");

BasicFileAttributes attrs = Files.readAttributes(
        path,
        BasicFileAttributes.class
);

System.out.println("Regular file: " + attrs.isRegularFile());
System.out.println("Directory: " + attrs.isDirectory());
System.out.println("Symbolic link: " + attrs.isSymbolicLink());
System.out.println("Size: " + attrs.size());
System.out.println("Created: " + attrs.creationTime());
System.out.println("Modified: " + attrs.lastModifiedTime());
System.out.println("Accessed: " + attrs.lastAccessTime());
```

`BasicFileAttributes` is the baseline attribute set widely supported across platforms. Filesystems may expose additional attributes through other views such as POSIX or DOS, but you should not assume all operating systems support the same attribute set.

You can request reading the attributes of a symbolic link rather than its target:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS
);
```

File creation time is not supported with equal precision across all filesystems; timestamps may be rounded or unreliable. Do not rely on metadata timestamps as the sole guarantee of integrity or event ordering.

## 15. Charsets and File Data

Because this lesson belongs to the topic of files and character encoding, it is important to distinguish **reading bytes** from **reading text**.

### 15.1. Text Files: Specify UTF-8 at Both Ends

```java
Path path = Path.of("data", "greeting.txt");

Files.writeString(
        path,
        "Hello, Java 17!",
        StandardCharsets.UTF_8
);

String restored = Files.readString(path, StandardCharsets.UTF_8);
```

When reading files from another system, only use UTF-8 if the format/protocol specifies UTF-8. If the file was created with another charset, you must select the exact charset of that file.

### 15.2. Bytes Do Not Self-Report Their Charset

```java
byte[] bytes = Files.readAllBytes(Path.of("data", "message.txt"));

String text = new String(bytes, StandardCharsets.UTF_8);
```

`readAllBytes` only retrieves raw bytes. Interpreting them as text is performed by `new String(bytes, charset)`. If you choose the wrong charset, the bytes may still be read without error, but the resulting text can be corrupted.

### 15.3. Detecting Invalid UTF-8 Data

`new String(bytes, UTF_8)` may replace malformed byte sequences with replacement characters. If your application must reject files that are not valid UTF-8, use a decoder with `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

For large files, do not use `readAllBytes` as shown in this snippet; instead, apply the decoder incrementally over streams/buffers. This example focuses on illustrating the strict invalid-data detection policy.

### 15.4. Never Arbitrarily Convert Binary Files to String

Do not read images, PDFs, ZIP files, or ciphertext into a `String` using UTF-8 and write them back out. Some byte sequences are not valid UTF-8; decoding can replace bytes and corrupt data.

For binary files, use `byte[]`, `InputStream`, `OutputStream`, or channels.

## 16. Handling Exceptions During File Operations

`Files` methods commonly throw `IOException` or one of its subclasses. Do not ignore errors just to let the program continue.

| Exception | Common Scenario |
|---|---|
| `NoSuchFileException` | File or path component not found |
| `FileAlreadyExistsException` | Creating a file or directory that already exists |
| `AccessDeniedException` | Insufficient permissions or denied by the operating system |
| `DirectoryNotEmptyException` | Deleting a directory that still contains entries |
| `AtomicMoveNotSupportedException` | Filesystem does not support the requested atomic move |
| `FileSystemException` | Specific filesystem error, possibly including file path and reason |
| `InvalidPathException` | String cannot form a valid Path; this is a runtime exception |

Handling example:

```java
try {
    String content = Files.readString(
            Path.of("data", "config.txt"),
            StandardCharsets.UTF_8
    );
    System.out.println(content);
} catch (NoSuchFileException ex) {
    System.err.println("File not found: " + ex.getFile());
} catch (AccessDeniedException ex) {
    System.err.println("No permission to read file: " + ex.getFile());
} catch (IOException ex) {
    System.err.println("Error reading file: " + ex.getMessage());
}
```

Place specific exceptions before the parent `IOException` so detailed handlers can run.

For a simple file task, you can declare `throws IOException` so the caller handles it. Choose based on which layer has enough context to recover or report a meaningful error.

### 16.1. Do Not Use exists to Replace Exception Handling

A pattern prone to race conditions:

```java
if (Files.exists(path)) {
    String text = Files.readString(path);
}
```

Between checking existence and reading, the file could be deleted, have its permissions changed, or be replaced. Therefore, you still must handle exceptions from `readString`.

When the goal is to read, the clearer approach is to attempt the read directly and handle `NoSuchFileException`/`IOException` appropriately.

## 17. Path Traversal and Validating External Path Input

If the application allows users to specify a file name, do not concatenate strings directly:

```java
// Unsafe if userInput is controlled by the user.
Path file = Path.of("uploads/" + userInput);
```

An input such as `../../secrets.txt` can cause the application to access files outside the intended directory. This is a **path traversal** vulnerability.

### 17.1. Normalizing and Verifying Containment Within the Root Directory

A basic validation step:

```java
Path base = Path.of("uploads").toAbsolutePath().normalize();

Path candidate = base.resolve(userInput).normalize();

if (!candidate.startsWith(base)) {
    throw new SecurityException("Path escapes upload directory");
}
```

`startsWith(Path)` compares by path components, which is safer than `candidate.toString().startsWith(base.toString())`. String comparison could mistakenly treat `/srv/uploads-evil` as a child of `/srv/uploads`.

However, lexical validation with `normalize` **is not sufficient to stop all attacks** if someone can create or replace symbolic links inside the directory.

### 17.2. Symbolic Link and Race Condition Considerations

In systems with high security requirements:

- Determine the real root directory using `toRealPath`.
- Verify actual parent directories to prevent symbolic links from pointing outside.
- Do not trust a one-time path check and assume filesystem state will not change.
- Consider `SecureDirectoryStream` if supported by the provider and safe relative operations inside an open directory are needed.
- Restrict process write permissions and symbolic link creation privileges inside upload directories.

The example below illustrates additionally verifying the existing parent directory before creating a file:

```java
Path baseReal = Path.of("uploads").toRealPath();
Path candidate = baseReal.resolve(userInput).normalize();

if (!candidate.startsWith(baseReal)) {
    throw new SecurityException("Path escapes upload directory");
}

Path parentReal = candidate.getParent().toRealPath();

if (!parentReal.startsWith(baseReal)) {
    throw new SecurityException("Parent escapes upload directory");
}

Path safeCandidate = parentReal.resolve(candidate.getFileName());
```

This is still an illustrative example, not a complete race-condition defense for every threat model. If a directory can be modified concurrently by untrusted processes, design operations around appropriate directory handles/providers rather than relying on multi-step path-name checks.

## 18. Filesystem and Portability Notes

### 18.1. Separators

Do not assume the separator is `/`. You can retrieve the default filesystem separator:

```java
String separator = java.nio.file.FileSystems.getDefault().getSeparator();
System.out.println(separator);
```

However, when joining components, use `Path.of` and `resolve` instead of manually concatenating separators.

### 18.2. Case Sensitivity in File Names

Windows commonly treats file names case-insensitively in typical configurations, whereas Linux typically treats them case-sensitively. macOS behavior may depend on the filesystem and how the volume is formatted.

Do not write applications assuming `Report.txt` and `report.txt` are always two separate files or always the same file. For portability, enforce consistent naming conventions.

### 18.3. Special Characters in File Names

Certain characters are forbidden or carry special meaning on some operating systems (for example, colons in Windows path components). `Path.of` may throw `InvalidPathException` if syntax is invalid for the provider.

Do not accept raw file names from users without a suitable filtering/sanitization policy.

### 18.4. Non-Uniform File Permissions

`Files.isReadable` or `Files.isWritable` are convenient checks, but actual access depends on user, ACLs, mounts, filesystem, and OS policies. Do not assume POSIX permissions exist on Windows or every provider.

### 18.5. Network Filesystems and Containers

On network shares, container volumes, or virtual filesystems, certain attributes and operations may behave differently than on local filesystems. Atomic moves, file locks, timestamps, and permissions must be verified against the deployment environment.

## 19. Complete Example: Reading, Writing, and Backing Up a UTF-8 File

Create the file `FileManagerDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class FileManagerDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Path.of("workspace", "reports");
        Path source = directory.resolve("summary.txt");
        Path backup = directory.resolve("summary.txt.bak");

        // Create parent directory if it does not exist.
        Files.createDirectories(directory);

        // Write UTF-8 content.
        String content = """
                Java 17
                Path and Files
                Safe file operations
                """;

        Files.writeString(source, content, StandardCharsets.UTF_8);

        // Read the content back using the same charset.
        String loaded = Files.readString(source, StandardCharsets.UTF_8);
        System.out.println(loaded);

        // Back up and replace any existing backup.
        Files.copy(
                source,
                backup,
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.COPY_ATTRIBUTES
        );

        // Display attributes.
        System.out.println("Size: " + Files.size(source));
        System.out.println("Exists: " + Files.exists(backup));

        // List direct entries in the directory.
        try (var files = Files.list(directory)) {
            files.forEach(System.out::println);
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 FileManagerDemo.java
java FileManagerDemo
```

This example demonstrates the basic operations in one workflow:

1. Use `Path.of` to construct a path.
2. Use `resolve` to create child file paths.
3. Use `createDirectories` to prepare the directory.
4. Use `writeString`/`readString` with UTF-8.
5. Use `copy` to create a backup.
6. Use `size` and `exists` to inspect attributes.
7. Use `Files.list` to list the directory and close the stream properly.

## 20. Quick Reference Table for Path and Files APIs in Java 17

| Need | API |
|---|---|
| Create a path | `Path.of(...)` |
| Get parent / last name | `getParent()` / `getFileName()` |
| Check if absolute | `isAbsolute()` |
| Convert to absolute | `toAbsolutePath()` |
| Normalize `.` and `..` | `normalize()` |
| Append child path | `resolve(...)` |
| Replace last component | `resolveSibling(...)` |
| Compute relative path | `relativize(...)` |
| Resolve real path | `toRealPath(...)` |
| Check existence | `Files.exists(...)` |
| Check file/directory/link | `Files.isRegularFile` / `isDirectory` / `isSymbolicLink` |
| Read UTF-8 text | `Files.readString(path, UTF_8)` |
| Write UTF-8 text | `Files.writeString(path, text, UTF_8)` |
| Read bytes | `Files.readAllBytes(...)` |
| Write bytes | `Files.write(...)` |
| Read line by line | `Files.newBufferedReader(...)` / `Files.lines(...)` |
| Create parent directories | `Files.createDirectories(...)` |
| Create empty file | `Files.createFile(...)` |
| Create temporary file | `Files.createTempFile(...)` |
| Copy | `Files.copy(...)` |
| Move/rename | `Files.move(...)` |
| Delete | `Files.delete(...)` / `deleteIfExists(...)` |
| List one level | `Files.list(...)` / `newDirectoryStream(...)` |
| Traverse directory tree | `Files.walk(...)` / `walkFileTree(...)` |
| Read metadata | `Files.size(...)` / `readAttributes(...)` |

## 21. Practice Exercises

### Exercise 1 — Building a Separator-Independent Path

Create a path to the file `data/logs/app.log` without manually concatenating slashes.

**Answer:**

```java
Path log = Path.of("data", "logs", "app.log");
```

### Exercise 2 — Resolving and Normalizing Paths

Given:

```java
Path base = Path.of("project", "src");
Path target = base.resolve(Path.of("main", "..", "test", "Demo.java"));
System.out.println(target.normalize());
```

**Answer:** `project/src/test/Demo.java` (the displayed separator depends on the OS).

### Exercise 3 — Writing and Reading Multilingual UTF-8 Text

Write `"Hello Java 17 — Xin chào"` to a file and read it back without depending on the default charset.

**Answer:**

```java
Path file = Path.of("hello.txt");

Files.writeString(file, "Hello Java 17 — Xin chào", StandardCharsets.UTF_8);
String text = Files.readString(file, StandardCharsets.UTF_8);
```

### Exercise 4 — Listing .txt Files in a Directory

Use `Files.list`, keep only regular files ending with `.txt`, and close the stream properly.

**Answer:**

```java
try (var entries = Files.list(Path.of("data"))) {
    entries.filter(Files::isRegularFile)
           .filter(path -> path.getFileName().toString().endsWith(".txt"))
           .forEach(System.out::println);
}
```

### Exercise 5 — Why Does normalize Not Defend Against Symbolic Links?

**Answer:** `normalize` only simplifies path components syntactically. It does not access the filesystem, does not know where a link points, and does not guarantee the path stays inside the intended real directory. For security requirements, you must consider real paths, symbolic links, and race conditions.

### Exercise 6 — Choosing readString or Streams?

A log file of several gigabytes needs sequential line-by-line processing. What should you choose?

**Answer:** Use `Files.lines` or `Files.newBufferedReader` inside `try-with-resources`. `readString` loads the entire content into memory, which is unsuitable for very large files.

### Exercise 7 — Copy or Move?

You want to create a backup while keeping the original file.

**Answer:** Use `Files.copy`. `Files.move` relocates the source file to the destination, so the original file no longer remains at its initial path after a successful move.

## 22. Key Takeaways

- **`Path` describes a path; `Files` performs operations on the filesystem.**
- Use `Path.of` and `resolve` to construct paths; avoid manual separator string concatenation.
- `normalize` only normalizes path structure; `toRealPath` accesses the filesystem and resolves symbolic links by default.
- `exists` does not guarantee that the next operation will succeed; handle exceptions from the actual operation.
- For text, specify the charset explicitly, typically `StandardCharsets.UTF_8`.
- For binary files, use byte arrays or streams; do not arbitrarily convert them to `String`.
- `Files.lines`, `Files.list`, and `Files.walk` return streams that hold resources; close them with `try-with-resources`.
- Copy, move, and delete have dedicated options; do not assume atomic move is supported on every filesystem.
- When accepting paths from users, check for path traversal and symbolic links according to your threat model; `normalize` alone is not a complete security measure.

## Official Java 17 References

- [Java SE 17 API — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html).
- [Java SE 17 API — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [Java SE 17 API — `java.nio.file.StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html).
- [Java SE 17 API — `java.nio.file.StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html).
- [Java SE 17 API — `java.nio.file.DirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html).
- [Java SE 17 API — `java.nio.file.FileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html).
- [Java SE 17 API — `java.nio.file.attribute.BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html).
- [Java SE 17 API — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
