# Listing and Traversing Directory Trees with `Files.list`, `Files.walk`, and `Files.find`

## 1. Objectives and Context

In the **`JAVA_STREAM_API`** module, a pipeline typically starts from a data source, chains lazy operations such as `filter` and `map`, and ends with `count`, `collect`, or `findFirst`. Besides `List`, arrays, and number sequences, the file system can also provide a **`Stream<Path>`** source.

In Java 8 and later, `java.nio.file.Files` offers three notable methods:

- **`Files.list(dir)`:** lists entries located **directly** inside a directory.
- **`Files.walk(root, ...)`:** traverses a **directory tree** from the root down to deeper levels.
- **`Files.find(root, maxDepth, matcher, ...)`:** traverses the tree and emits only paths matching a condition based on `Path` and `BasicFileAttributes`.

Unlike streams from in-memory collections, these streams can **hold I/O resources** such as directory handles. Therefore, you must close them with `try-with-resources`, even if the terminal operation stops early or fails.

After this lesson, you can:

1. Choose `list`, `walk`, or `find` appropriately based on the traversal scope.
2. Understand the meaning of `maxDepth`, the root path, and how to select files rather than directories.
3. Use `BasicFileAttributes` to find files by type, size, or modification time.
4. Handle lazy evaluation, I/O exceptions, and the stream source lifecycle.
5. Recognize limitations involving symbolic links, large trees, unspecified traversal order, and the need for subtree pruning.
6. Write file-counting, search, and aggregation pipelines with proper resource control.

This lesson belongs to the **I/O Sources and Resource Management** chapter. These principles are also important when studying Spliterators, parallel pipelines, or Stream Gatherers, where state retention and resource management require careful consideration.

## 2. Quick Differences Between the Three APIs

Suppose we have the following structure:

```text
du-lieu/
├── readme.txt
├── src/
│   ├── App.java
│   └── Util.java
└── assets/
    └── logo.png
```

| Method | Traversal scope | Includes `root` itself? | Result |
| --- | --- | --- | --- |
| `Files.list(root)` | Only direct entries of the `root` directory | No | `Stream<Path>` |
| `Files.walk(root)` | Tree starting from `root`, all depths by default | Yes | `Stream<Path>` |
| `Files.walk(root, 2)` | `root` and entries up to depth 2 | Yes | `Stream<Path>` |
| `Files.find(root, 2, matcher)` | Traverses up to depth 2, returns only paths accepted by `matcher` | Yes if `matcher` matches root | `Stream<Path>` |

With the tree above, `list` sees `readme.txt`, `src`, and `assets`; `walk` also sees `du-lieu` itself and deeper files; `find` can return `App.java` and `Util.java` specifically.

**Child entry order is not guaranteed to be alphabetical.** `walk` performs a *depth-first* traversal, but sibling order depends on the file system. If a report requires a deterministic order, sort explicitly while accounting for memory cost.

## 3. Complete Java 8 Example: Trying All Three Methods

The following program creates a small tree in a temporary directory and cleans up when finished. Cleanup uses `Files.walk` on the **temporary tree created by the program**; do not copy deletion logic onto a real directory without verifying the scope.

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Stream;

public class ThuFilesStream {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("stream-files-demo-");

        try {
            Path src = Files.createDirectories(root.resolve("src"));
            Files.createDirectories(root.resolve("assets"));
            Files.write(root.resolve("readme.txt"),
                Arrays.asList("Documentation"), StandardCharsets.UTF_8);
            Files.write(src.resolve("App.java"),
                Arrays.asList("class App {}"), StandardCharsets.UTF_8);
            Files.write(src.resolve("Util.java"),
                Arrays.asList("class Util {}"), StandardCharsets.UTF_8);

            System.out.println("LIST:");
            try (Stream<Path> entries = Files.list(root)) {
                entries.map(p -> p.getFileName().toString())
                    .sorted()
                    .forEach(System.out::println);
            }

            System.out.println("WALK:");
            try (Stream<Path> paths = Files.walk(root, 2)) {
                paths.map(p -> {
                    String r = root.relativize(p).toString();
                    return r.isEmpty() ? "." : r;
                })
                .sorted()
                .forEach(System.out::println);
            }

            System.out.println("FIND:");
            try (Stream<Path> matches = Files.find(root, 2,
                    (p, attrs) -> attrs.isRegularFile()
                        && p.getFileName() != null
                        && p.getFileName().toString().endsWith(".java"))) {
                matches.map(p -> root.relativize(p).toString())
                    .sorted()
                    .forEach(System.out::println);
            }
        } finally {
            // Only delete the contents of the created temporary directory.
            try (Stream<Path> paths = Files.walk(root)) {
                paths.sorted(Comparator.reverseOrder())
                    .forEach(p -> {
                        try {
                            Files.deleteIfExists(p);
                        } catch (IOException ex) {
                            throw new UncheckedIOException(ex);
                        }
                    });
            }
        }
    }
}
```

Representative output:

```text
LIST:
assets
readme.txt
src

WALK:
.
assets
readme.txt
src
src/App.java
src/Util.java

FIND:
src/App.java
src/Util.java
```

On Windows, the path separator in the `WALK` and `FIND` examples may be a backslash instead of `/`. The `.` represents the relative path of `root` itself.

The program intentionally uses `sorted` to make comparing results easier. For very large trees, `sorted` usually needs to receive all elements before emitting sorted results.

## 4. `Files.list`: Traversing One Level

Signature:

```java
public static Stream<Path> list(Path dir) throws IOException
```

`Files.list` returns `Path` objects corresponding to **direct entries** inside the directory, including files, subdirectories, and other entries. It does not descend further and does not include `dir` itself.

Example program reading an existing directory:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

public class LietKeThuMuc {
    public static void main(String[] args) throws IOException {
        Path dir = Paths.get("du-lieu");

        try (Stream<Path> entries = Files.list(dir)) {
            entries.forEach(System.out::println);
        }
    }
}
```

Precondition to run: the `du-lieu` directory must exist relative to the process's working directory. If the path does not exist, is not a directory, or lacks access permissions, the API may report an I/O error.

### 4.1. Selecting Regular Files Only

```java
Path dir = Paths.get("du-lieu");

try (Stream<Path> entries = Files.list(dir)) {
    entries.filter(Files::isRegularFile)
        .forEach(System.out::println);
}
```

`Files.isRegularFile(path)` checks the file type and by default **may follow symbolic links** to the target file. If your business logic wants only regular files and not symbolic links, use `Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)`.

### 4.2. Counting Direct Entries

```java
try (Stream<Path> entries = Files.list(dir)) {
    long tongMuc = entries.count();
    System.out.println(tongMuc);
}
```

The count here includes **subdirectories as well**. Add `filter(Files::isRegularFile)` if you only need to count regular files at the current level.

Do not replace `list(root)` with `walk(root)` for a simple single-level listing: `walk` includes the root and can traverse much deeper.

## 5. `Files.walk`: Tree Traversal and Depth Limits

Two overloads since Java 8:

```java
public static Stream<Path> walk(
    Path start,
    FileVisitOption... options
) throws IOException;

public static Stream<Path> walk(
    Path start,
    int maxDepth,
    FileVisitOption... options
) throws IOException;
```

`walk` creates a **depth-first** traversal source starting from `start`; `start` is also an element of the result. By default, traversal does not follow symbolic links into target directory trees.

### 5.1. Finding All `.java` Files in a Tree

```java
Path root = Paths.get("du-lieu");

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
        .filter(p -> p.getFileName() != null)
        .filter(p -> p.getFileName().toString().endsWith(".java"))
        .forEach(System.out::println);
}
```

`filter` only affects **which paths are emitted in the result**; it does not prevent `walk` from traversing inside a non-matching directory.

### 5.2. Meaning of `maxDepth`

```text
root/                      depth = 0
├── a.txt                  depth = 1
└── src/                   depth = 1
    ├── App.java           depth = 2
    └── nested/            depth = 2
        └── More.java      depth = 3
```

| Call | Results can contain |
| --- | --- |
| `Files.walk(root, 0)` | Only the `root` path. |
| `Files.walk(root, 1)` | The root and all direct entries beneath it. |
| `Files.walk(root, 2)` | Adds `App.java` and `nested`. |
| `Files.walk(root, 3)` | Adds `More.java`. |
| `Files.walk(root)` | The full depth that traversal can reach. |

`maxDepth` must be **non-negative**. The depth of the root is 0. `Files.walk(root, 1)` is close to a single-level listing, except it **still includes `root` itself**:

```java
try (Stream<Path> paths = Files.walk(root, 1)) {
    paths.filter(p -> !p.equals(root))
        .forEach(System.out::println);
}
```

If you want a single-level listing without the root, `Files.list(root)` remains clearer.

### 5.3. File Names and Relative Paths

```java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.filter(p -> p.getFileName() != null)
        .filter(p -> p.getFileName().toString().startsWith("Test"))
        .map(root::relativize)
        .forEach(System.out::println);
}
```

`getFileName()` retrieves the final name element, unlike inspecting the entire path. `root.relativize(p)` makes reports less dependent on installation location; all paths in the example belong to the same file system and are derived from `root`.

## 6. `Files.find`: Searching Using File Attributes

Signature:

```java
public static Stream<Path> find(
    Path start,
    int maxDepth,
    BiPredicate<Path, BasicFileAttributes> matcher,
    FileVisitOption... options
) throws IOException;
```

The `matcher` parameter receives both:

- `Path path`: the path being evaluated.
- `BasicFileAttributes attrs`: basic metadata obtained during traversal, including type, size, and modification time.

Unlike `Files.walk(...).filter(...)`, the `matcher` in `Files.find` can use attributes already read during traversal, avoiding redundant `Files.readAttributes` calls just to check the same information again.

### 6.1. Finding Java Files up to Depth 5

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

public class TimTepJava {
    public static void main(String[] args) throws IOException {
        Path root = Paths.get("du-lieu");

        try (Stream<Path> matches = Files.find(
                root,
                5,
                (p, attrs) ->
                    attrs.isRegularFile()
                    && p.getFileName() != null
                    && p.getFileName().toString().endsWith(".java")
            )) {
            matches.forEach(System.out::println);
        }
    }
}
```

### 6.2. Finding Files Larger Than 10 MiB

```java
long nguong = 10L * 1024 * 1024;

try (Stream<Path> matches = Files.find(
        root,
        Integer.MAX_VALUE,
        (p, attrs) -> attrs.isRegularFile()
            && attrs.size() > nguong
    )) {
    matches.forEach(System.out::println);
}
```

`attrs.size()` typically represents file length in bytes. Do not infer directory size from the metadata value of the directory entry itself; it is not the sum of child file sizes.

### 6.3. Finding Files Modified After a Timestamp

```java
import java.nio.file.attribute.FileTime;
import java.time.Instant;

FileTime moc = FileTime.from(
    Instant.parse("2026-01-01T00:00:00Z")
);

try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, attrs) -> attrs.isRegularFile()
            && attrs.lastModifiedTime().compareTo(moc) > 0
    )) {
    matches.forEach(System.out::println);
}
```

Using `FileTime` makes the timestamp explicit, but does not turn metadata into an **immutable snapshot**: files can still be modified or deleted during traversal.

### 6.4. Does `find` Automatically Skip Non-Matching Directories?

Do not treat `matcher` as a subtree-pruning directive. It decides **which paths are returned**, but a non-matching directory may still need to be opened to inspect its child files.

If the goal is **not to enter `build` directories**, a simple result filter such as `!p.toString().contains("build")` can both accidentally exclude valid files and fail to prevent traversing the subtree. Use `Files.walkFileTree` with `SKIP_SUBTREE` when you need branch-level traversal control.

## 7. Closing the Stream: `try-with-resources` Is Mandatory

These I/O-backed streams can keep directory handles open throughout traversal. Close them even when only calling `count` or `findFirst`:

```java
try (Stream<Path> paths = Files.walk(root)) {
    long soTep = paths
        .filter(Files::isRegularFile)
        .count();

    System.out.println(soTep);
} // close() runs automatically at the end of the try block
```

`collect` and `count` **do not guarantee closing** the source stream. `try-with-resources` releases the resource upon completion or exception.

### 7.1. Wrong: Returning a Stream from Inside a `try` Block

```java
// AVOID: the returned stream is already closed.
static Stream<Path> timSai(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile);
    }
}
```

When the method returns, the `try` block has exited and the stream is closed. External code cannot safely consume this pipeline.

If the data is small enough, collect the results directly inside the block:

```java
import java.util.List;
import java.util.stream.Collectors;

static List<Path> timTep(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile)
            .collect(Collectors.toList());
    }
}
```

`List<Path>` here stores only paths, without opening the contents of each file. For huge trees, avoid collecting all paths into RAM; consider processing each entry within the stream scope or using a batched API.

### 7.2. A Stream Can Only Be Consumed Once

```java
try (Stream<Path> entries = Files.list(root)) {
    long soMuc = entries.count();

    // NOT ALLOWED: the stream has already been consumed.
    // entries.forEach(System.out::println);
}
```

If you need both to count and to list, create a new stream from the same source, or collect the data into a collection if the data is small and requirements allow it. `try-with-resources` does not make a stream reusable.


## 8. Lazy Evaluation and Short-Circuiting Terminal Operations

Streams returned by `Files.list`, `Files.walk`, and `Files.find` are **lazily populated**: the file system can be traversed on demand by the terminal operation rather than fetching all file names up front. However, **calling the stream-creating method may still perform initial I/O** and throw `IOException` at initialization time.

### 8.1. Checking Whether Any `.java` File Exists

```java
try (Stream<Path> paths = Files.walk(root)) {
    boolean coJava = paths
        .anyMatch(p -> p.getFileName() != null
            && p.getFileName().toString().endsWith(".java"));

    System.out.println(coJava);
}
```

`anyMatch` is a **short-circuiting** terminal operation: it can stop once it encounters a matching element. Because sibling order is not guaranteed, you must not rely on *which specific file* gets inspected first.

### 8.2. `limit` Bounds Output, Not Guaranteed Entry Reads

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.limit(10)
        .forEach(System.out::println);
}
```

With this pipeline, at most 10 paths are passed to `forEach`. If you place a `filter` before `limit`, the system may have to examine far more than 10 entries to obtain 10 matching paths:

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p -> p.getFileName() != null)
        .filter(p -> p.getFileName().toString().endsWith(".rare"))
        .limit(10)
        .forEach(System.out::println);
}
```

If no `.rare` files exist, the entire tree within the traversal scope may be inspected before finishing. `limit` is not a mechanism for pruning subdirectories out of traversal.

### 8.3. `sorted` Usually Needs to Observe the Entire Source

```java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.map(p -> root.relativize(p).toString())
        .sorted()
        .limit(10)
        .forEach(System.out::println);
}
```

`sorted` is a **stateful** intermediate operation: for a finite input, it generally needs to gather the values before emitting results in the new order. Thus `sorted().limit(10)` does not mean only 10 paths are visited. Reordering to `limit(10).sorted()` reduces the data sorted, but also **changes the requirement**: it then sorts only the first 10 entries encountered, not the 10 smallest entries across the whole tree.

When selecting the largest or newest files from a massive tree, you may need a bounded-memory top-k algorithm instead of calling `sorted` over all elements.

## 9. Symbolic Links and `FOLLOW_LINKS`

By default, `Files.walk` and `Files.find` do not descend into a directory tree referenced through a **symbolic link**. The link path itself may still be emitted, but traversal does not follow the link deeper.

If business requirements genuinely call for it, you can enable `FileVisitOption.FOLLOW_LINKS`:

```java
import java.nio.file.FileVisitOption;

try (Stream<Path> paths = Files.walk(
        root,
        3,
        FileVisitOption.FOLLOW_LINKS
    )) {
    paths.forEach(System.out::println);
}
```

Risks to weigh:

- A link may point **outside the root directory scope** that the application is permitted to read.
- Two links can form a **cycle**, causing errors during traversal such as `FileSystemLoopException`.
- Permissions or link targets can change during scanning.
- `maxDepth` only limits **depth**, not security policies on target paths.

**Do not enable `FOLLOW_LINKS` by default** in directory-scanning tools without an explicit policy on scope and access permissions.

### `Files.isRegularFile` and Links Can Produce Surprising Results

`Files.isRegularFile(path)` follows symbolic links by default. Therefore:

```java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
        .forEach(System.out::println);
}
```

`walk` does not enter a directory pointed to by a link, but the `isRegularFile` filter may treat a link to a **regular file** as a regular file. If you want to check the entry itself without following links:

```java
import java.nio.file.LinkOption;

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p ->
        Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS)
    ).forEach(System.out::println);
}
```

When using `Files.find`, `BasicFileAttributes` in the matcher reflects the link-following policy of the traversal itself; `attrs.isRegularFile()` is more consistent than issuing a separate attribute check with a different policy.

## 10. I/O Errors: `IOException`, `UncheckedIOException`, and Tree Mutations

Reading a directory tree can fail due to missing files, lack of permissions, moved directories, broken symbolic links, or file system issues. Two common error points:

| Stage | Typical error type | Why |
| --- | --- | --- |
| Calling `Files.list` / `Files.walk` / `Files.find` | `IOException` (checked) | Cannot initialize access, open the path, or fetch required info. |
| Traversing inside a terminal operation | `UncheckedIOException` | The lazy stream wraps an I/O error raised while reading additional entries. |
| Running a custom I/O lambda | Checked `IOException` to handle in the lambda | Standard functional interfaces do not declare checked exceptions. |

A basic file-counting method:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long demTep(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile).count();
    }
}
```

Startup `IOException` is declared via `throws IOException`; `UncheckedIOException` during traversal can still propagate because it is a runtime exception.

If a lambda directly calls an I/O operation that throws a checked exception, handle it explicitly:

```java
import java.io.UncheckedIOException;

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
        .forEach(p -> {
            try {
                System.out.println(Files.size(p));
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
}
```

In a real application, the calling layer can catch both `IOException` and `UncheckedIOException` to report the directory and cause clearly. Never silently catch all errors and return `0`: "**there are no files**" is completely different from "**the files could not be read**".

### Case Where a File Changes Between Check and Use

A `Path` in the stream is only a path reference, **not a copy of file contents**. After the matcher concludes `attrs.isRegularFile()`, another process can delete, change permissions on, or overwrite the file before your application opens it.

That is a *time-of-check to time-of-use* (TOCTOU) condition. For sensitive operations or where consistency is required, validate when actually opening/using the resource and follow safe file-opening practices; do not treat scanned metadata as immutable state.

## 11. Pruning an Entire Subtree: When to Switch to `Files.walkFileTree`?

`filter` after `walk` and the `matcher` in `find` only **select paths to include in the output**. They are not a general command to **prevent traversal from entering a subdirectory**.

When you need to skip the contents of `build` directories, use `Files.walkFileTree` with `FileVisitResult.SKIP_SUBTREE`:

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

static void duyetBoQuaBuild(Path root) throws IOException {
    Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult preVisitDirectory(
                Path dir,
                BasicFileAttributes attrs) throws IOException {

            Path ten = dir.getFileName();
            if (!dir.equals(root)
                    && ten != null
                    && ten.toString().equals("build")) {
                return FileVisitResult.SKIP_SUBTREE;
            }
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFile(
                Path file,
                BasicFileAttributes attrs) throws IOException {

            if (attrs.isRegularFile()) {
                System.out.println(file);
            }
            return FileVisitResult.CONTINUE;
        }
    });
}
```

`preVisitDirectory` runs before visiting a directory's contents; `SKIP_SUBTREE` skips everything underneath. `visitFile` receives the visited files.

`walkFileTree` uses a **visitor callback** model and does not return a `Stream<Path>`. It is well suited when you need to control traversal, handle errors per file, or perform controlled tree copying or deletion. For a straightforward need like "get all Java files in a tree", `Files.find` or `Files.walk` remains easier to read.

## 12. Practical Recipes

The short snippets below assume `Path root` already exists; when placed inside a standalone Java class, add imports such as `java.nio.file.*`, `java.util.*`, `java.util.stream.*`, and `java.io.*`.

### 12.1. Counting Regular Files at Exactly One Level

```java
try (Stream<Path> entries = Files.list(root)) {
    long soTep = entries
        .filter(Files::isRegularFile)
        .count();

    System.out.println(soTep);
}
```

### 12.2. Finding All Java Files Only Up to Depth Three

```java
try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, attrs) -> attrs.isRegularFile()
            && p.getFileName() != null
            && p.getFileName().toString().endsWith(".java")
    )) {
    matches.forEach(System.out::println);
}
```

### 12.3. Collecting Paths into a List After Closing the Source

```java
import java.util.List;
import java.util.stream.Collectors;

List<Path> ketQua;

try (Stream<Path> paths = Files.walk(root, 2)) {
    ketQua = paths.filter(Files::isRegularFile)
        .collect(Collectors.toList());
}

// List<Path> can be used after the I/O source has closed.
System.out.println(ketQua.size());
```

The elements in `ketQua` are `Path` objects, not file contents. Opening files via those paths later can still fail if the tree has changed. Collecting all paths into a list also consumes memory and is unsuitable for unbounded trees.

### 12.4. Total Bytes of Files at Maximum Depth Two

```java
try (Stream<Path> matches = Files.find(
        root,
        2,
        (p, attrs) -> attrs.isRegularFile()
    )) {
    long tongByte = matches.mapToLong(p -> {
        try {
            return Files.size(p);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }).sum();

    System.out.println(tongByte);
}
```

This example calls `Files.size(p)` a second time after the matcher and may encounter files that changed or were deleted. If you want to sum directly from `BasicFileAttributes` in a single pass, `Files.walkFileTree` with `visitFile` and `attrs.size()` is a suitable choice. Also note that `long` can overflow if the total exceeds its representable range.

### 12.5. Printing Relative Paths in Deterministic Order

```java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.filter(p -> !p.equals(root))
        .map(p -> root.relativize(p).toString())
        .sorted()
        .forEach(System.out::println);
}
```

`sorted` makes output easy to test, but incurs the cost of sorting all paths within the traversed scope.

## 13. API Selection Table and Common Mistakes

| Need | Choice | Key point to remember |
| --- | --- | --- |
| List exactly one level | `Files.list(dir)` | Excludes `dir` itself. |
| Traverse tree to depth N | `Files.walk(root, N)` | Includes `root`; root depth is 0. |
| Filter by type, size, or modification time | `Files.find(root, N, matcher)` | `matcher` receives `BasicFileAttributes` directly. |
| Skip an entire branch | `Files.walkFileTree` | Use `SKIP_SUBTREE`. |
| Only need to know if one matching file exists | `anyMatch` / `findFirst` | Can short-circuit; still must be closed. |
| Symbolic links exist, do not follow targets | Do not pass `FOLLOW_LINKS` | Add `NOFOLLOW_LINKS` checks when needed. |
| Want deterministic print order | `sorted` / comparator | Requires processing and holding data before sorting. |
| Data is too large | Limit scope, depth, or process in batches | Do not unconditionally collect/sort the entire tree. |

Common mistakes:

- **Forgetting `try-with-resources`:** leaving directory handles unclosed even after calling `count` or `collect`.
- **Confusing `walk(root, 1)` with `list(root)`:** forgetting that `walk` also emits `root`.
- **Using `walk(root)` when only one level is needed:** unnecessarily traversing deep trees.
- **Using `filter` to "prevent entering subdirectories":** filters only exclude output elements.
- **Using `contains("build")` on path strings to prune branches:** prone to false exclusions and does not stop traversal.
- **Relying on default traversal order:** directory entry order is not guaranteed to be alphabetical.
- **Enabling `FOLLOW_LINKS` automatically:** risks cycles and out-of-scope access.
- **Returning a stream out of a `try` block:** the stream is already closed when the caller receives it.
- **Reusing a stream after a terminal operation:** a stream can only be consumed once.
- **Swallowing `IOException` and returning an empty result:** hides system errors.
- **Sorting an entire huge tree just to take a few elements:** undermines lazy processing benefits.
- **Assuming files cannot change after the matcher checks them:** creates TOCTOU risks.

## 14. Practice Exercises

Suppose you have this tree:

```text
kho/
├── notes.txt
├── src/
│   ├── Main.java
│   ├── Model.java
│   └── nested/
│       └── Test.java
├── docs/
│   └── guide.md
└── build/
    └── classes.bin
```

### Exercise 1 — Compare `list` and `walk`

Given `root = Paths.get("kho")`, which paths does `Files.list(root)` return? What extra element does `Files.walk(root, 1)` include? Does `Files.walk(root, 2)` contain `src/nested/Test.java`?

### Exercise 2 — Find Java Files

Write `Files.find(root, 3, matcher)` to get regular files ending with `.java`. Close the source with `try-with-resources`. Predict the resulting files.

### Exercise 3 — Count Files at Exactly One Level

Use `Files.list` to count regular files directly under `kho`, excluding directories. What is the result?

### Exercise 4 — Only Need Two Files with a Rare Extension

If you call `Files.walk(root).filter(p -> p.toString().endsWith(".jar")).limit(2)`, and the tree has no `.jar` files, does Java inspect only two paths and stop? Why? Do you still have to close the stream?

### Exercise 5 — Requirement to Avoid Accessing the `build` Directory

Why does `Files.find` with a matcher rejecting paths containing `"build"` fail to satisfy the requirement? Which API and return value should be used to skip the entire subtree?

### Reference Answers

**Exercise 1:** `Files.list(root)` returns `notes.txt`, `src`, `docs`, and `build` in unspecified order. `Files.walk(root, 1)` also includes `root` itself. `src/nested/Test.java` is at depth **3**, so it is not included in `walk(root, 2)`.

**Exercise 2:**

```java
try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, attrs) -> attrs.isRegularFile()
            && p.getFileName() != null
            && p.getFileName().toString().endsWith(".java")
    )) {
    matches.map(p -> root.relativize(p).toString())
        .sorted()
        .forEach(System.out::println);
}
```

The output is `src/Main.java`, `src/Model.java`, and `src/nested/Test.java` (path separators depend on the OS).

**Exercise 3:**

```java
try (Stream<Path> entries = Files.list(root)) {
    long count = entries.filter(Files::isRegularFile).count();
    System.out.println(count); // 1 (notes.txt)
}
```

**Exercise 4:** No. `limit(2)` applies to **the number of elements passing `filter`**; if there are no `.jar` files, traversal may inspect the entire tree. The stream still must be closed even when there are no results.

**Exercise 5:** The matcher in `find` chooses which paths are emitted, but provides no subtree-pruning command. `Files.walkFileTree` allows overriding `preVisitDirectory` and returning `FileVisitResult.SKIP_SUBTREE` when encountering a directory named `build`; other directories return `CONTINUE`.

## 15. Summary

```java
// Direct entries only:
try (Stream<Path> s = Files.list(root)) {
    s.forEach(System.out::println);
}

// Tree up to depth 3, including root:
try (Stream<Path> s = Files.walk(root, 3)) {
    s.forEach(System.out::println);
}

// Only emit paths accepted by matcher:
try (Stream<Path> s = Files.find(
        root, 3,
        (p, attrs) -> attrs.isRegularFile()
    )) {
    s.forEach(System.out::println);
}
```

- **`Files.list`** lists a single level; **`Files.walk`** traverses a tree; **`Files.find`** traverses a tree with a predicate receiving `BasicFileAttributes`.
- Always use **`try-with-resources`** to close I/O stream sources, even when no elements are emitted.
- `maxDepth` limits depth from the root; symbolic links are not followed by default.
- `filter` and `matcher` select outputs; they **do not prune traversal branches**. To skip a subtree, use `Files.walkFileTree` and `SKIP_SUBTREE`.
- Handle `IOException` at initialization and `UncheckedIOException` that may occur during traversal; never equate I/O errors with an empty dataset.
- Directory order is not guaranteed; sort when deterministic output is required, while weighing cost on large trees.

Combining these three file sources properly with `filter`, `map`, `count`, and `collect` helps build file-system exploration tools that are clear, resource-efficient, and resilient to I/O environment changes.
