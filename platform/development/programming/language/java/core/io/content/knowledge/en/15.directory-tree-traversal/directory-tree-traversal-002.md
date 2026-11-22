# `Files.list` Lists Direct Children Only — Single-Level Directory Traversal in Java

In Java NIO.2, `Files.list(Path)` is a concise way to obtain a `Stream<Path>` of **the direct child entries in a directory**. It does not automatically traverse items located deeper in subdirectories. This distinction is critical: a program searching for a file with `Files.list(root)` may completely miss a file located at `root/subdir/file.txt` even though that file exists.

This lesson belongs to the **Directory Tree Traversal** section of Java Core I/O and focuses specifically on **single-level traversal**: what `Files.list` returns, what it does not return, how to filter/sort/count, why the stream must be closed, and when to switch to `Files.walk`, `Files.find`, or `Files.walkFileTree`. The examples use Java 17+, create their own temporary directories, require no pre-existing data, and have been verified by running actual programs.

## 1. Understanding “Direct Children” Properly

Consider this directory tree:

```text
root/
├── alpha.txt
├── zeta.bin
└── docs/
    └── nested/
        └── deep.txt
```

Calling:

```java
try (Stream<Path> entries = Files.list(root)) {
    entries.forEach(System.out::println);
}
```

This is an **illustrative snippet**: it requires a `Path root` variable, imports for `java.nio.file.Files` and `java.util.stream.Stream`, and `IOException` handling.

`Files.list(root)` returns `Path` objects for the **three direct child entries**:

- `root/alpha.txt` — file directly inside `root`.
- `root/zeta.bin` — file directly inside `root`.
- `root/docs` — **subdirectory** directly inside `root`.

It **does not return** `root/docs/nested` and **does not return** `root/docs/nested/deep.txt`, because those two entries sit at a depth greater than one level. `root` is also **not included in the results**, because `list` enumerates **the entries inside the directory**, not the directory passed in itself.

A valid empty directory yields an empty stream. That differs from a nonexistent or inaccessible path, which may lead to an `IOException`.

**Rule of thumb:** `Files.list(dir)` is close to “list the contents of this directory,” not “find every file underneath this directory.”

## 2. Syntax and Return Type

Java SE 17 API:

```java
public static Stream<Path> list(Path dir) throws IOException
```

Key points:

1. `dir` is a `Path` to a **directory**. Creating `Path.of("root")` does not verify or create the directory.
2. The result is **`Stream<Path>`** — each element is a path to a child entry, **not** a filename `String` or file contents.
3. Elements may represent **regular files, directories, symbolic links, and other entry types**. `list` **does not automatically filter** to regular files only.
4. `Files.list` does not guarantee any **sort order** of entries. The order depends on the filesystem/provider; when deterministic output is required, you must use `sorted(...)`.
5. The stream created from listing a directory holds an underlying **system resource**; it **must be closed** using `try-with-resources` or equivalent management.
6. Entries are generally fetched **lazily** as the stream is consumed; this differs from taking an immutable snapshot of the entire tree at call time.
7. A stream can be used **only once** per the `Stream` contract. To traverse the directory again, create a new stream or intentionally store the results in a collection if the size is appropriate.

`Files.list` has existed since **Java 8**. NIO.2 `Path` and `Files` arrived in Java 7, while the stream-returning `list` method is a Java 8+ API. The examples here require **Java 17+** because they use `Path.of`, `Files.writeString`, and `Stream.toList` where appropriate.

### A `Path` Is Not File Data

`Path path = Path.of("docs", "notes.txt");` only describes a path's name/location. Operations such as `path.getFileName()` or `path.resolve("child")` are mostly **syntactic** operations. Operations like `Files.isDirectory(path)` or `Files.readString(path)` are what actually query/interact with the filesystem and can fail due to state or permissions.

`Files.list` gives you **paths** to pass to further `Files` operations; it does not read every file's contents, decode charsets, or open each file like an `InputStream`.

## 3. Example 1 — Proving `Files.list` Does Not Recurse

Create `ListOneLevelDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public class ListOneLevelDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("list-one-");
        try {
            Files.writeString(root.resolve("alpha.txt"), "A", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("zeta.bin"), "Z", StandardCharsets.UTF_8);
            Path nested = Files.createDirectories(root.resolve("docs").resolve("nested"));
            Files.writeString(nested.resolve("deep.txt"), "D", StandardCharsets.UTF_8);

            try (Stream<Path> entries = Files.list(root)) {
                entries.sorted(Comparator.comparing(
                        p -> p.getFileName().toString()))
                       .forEach(p -> System.out.println(
                               p.getFileName() + ":"
                                       + (Files.isDirectory(p) ? "directory" : "file")));
            }
            try (Stream<Path> entries = Files.list(root)) {
                System.out.println("direct children=" + entries.count());
            }
            try (Stream<Path> entries = Files.list(root)) {
                System.out.println("includes deep.txt=" + entries.anyMatch(
                        p -> p.getFileName().toString().equals("deep.txt")));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                paths.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try { Files.deleteIfExists(p); }
                    catch (IOException e) { throw new UncheckedIOException(e); }
                });
            }
        }
    }
}
```

Compile and run commands:

```bash
javac -encoding UTF-8 --release 17 ListOneLevelDemo.java
java ListOneLevelDemo
```

Verified output:

```text
alpha.txt:file
docs:directory
zeta.bin:file
direct children=3
includes deep.txt=false
```

**Analysis:**

- The temporary directory is created automatically. `Files.writeString` creates two files in root, `Files.createDirectories` creates `docs/nested`, and a file `deep.txt` is placed deeper inside.
- `Files.list(root)` sees only `alpha.txt`, `docs`, and `zeta.bin`. It sees neither `nested` nor `deep.txt`.
- `sorted(Comparator.comparing(...))` sorts by entry name before printing; if `sorted` is omitted, there is **no guarantee** that the files print in alphabetical order.
- `Files.isDirectory(p)` classifies each entry **at check time**; it may follow symbolic links by default, so the example uses only regular directories and files it just created.
- Calling `entries.count()` counts **direct entries**, including directories. The result is 3, **not the total file count of the entire tree**.
- `anyMatch` asks whether there is a **direct** entry named `deep.txt`. Getting `false` does not prove the file does not exist in deeper directories.
- The `finally` block uses `Files.walk` to clean up **the temporary directory tree owned by the program**. This is only example cleanup, **not an indication that `Files.list` performs recursive traversal**.

The program may throw `IOException` if the temporary filesystem does not permit the operations. The stdout lines above were recorded when running the example successfully on Java 17 with a normal filesystem.

## 4. Getting Names vs. Getting Full Paths?

`Files.list(dir)` returns a `Path` to each child entry, typically including the path prefix of `dir`. If you only need the **final name**, use `getFileName()`:

```java
try (Stream<Path> entries = Files.list(directory)) {
    entries.map(p -> p.getFileName().toString())
           .sorted()
           .forEach(System.out::println);
}
```

This is an **illustrative snippet**, requiring a valid `directory`, imports for `Files`, `Path`, and `Stream`, and `IOException` handling. `getFileName()` returns the last element; the path `root/docs` yields the name `docs`.

If you need to operate on the file afterward, **keep the `Path`** rather than only keeping the name: the string `"report.txt"` lacks enough information when multiple directories exist. Use `Path.resolve` when building another path instead of OS-specific string concatenation like `"dir/" + fileName`.

Metadata can be queried via `Files.size(path)`, `Files.isRegularFile(path)`, `Files.getLastModifiedTime(path)`, etc.; these operations are **not performed automatically by `Files.list`** and may incur extra I/O or races.

## 5. Filtering Direct Entries with the Stream API

Because the result is a `Stream<Path>`, you can use `filter`, `map`, `sorted`, `limit`, `count`, or `collect` like other Java streams.

Example retrieving **regular files directly in root** with the `.txt` extension:

```java
try (Stream<Path> entries = Files.list(root)) {
    List<Path> files = entries.filter(Files::isRegularFile)
            .filter(p -> p.getFileName().toString().endsWith(".txt"))
            .sorted(Comparator.comparing(p -> p.getFileName().toString()))
            .toList();
}
```

This is **illustrative code**, requiring imports for `Files`, `Path`, `List`, `Comparator`, and `Stream`, a `root` variable, and `IOException` handling. `Files.isRegularFile` checks the entry type; `endsWith(".txt")` only checks the name **as a string**, without reading contents or determining the actual MIME type.

### Distinguishing Filtering from Deep Traversal

`filter(Files::isRegularFile)` **does not make the stream recursive**. If `deep.txt` sits under `root/docs/nested`, the filter only examines the three direct entries provided by `Files.list(root)`; it does not enter `docs` to look for deeper files.

If your intent is to find “all `.txt` files at every level,” you need to switch to a deep traversal API or implement your own algorithm to walk subdirectories. `Files.walk(root)` or `Files.find(root, maxDepth, ...)` is more appropriate.

### `limit` Does Not Guarantee “the First N Files Alphabetically”

Without `sorted`, when listing order is unspecified, `limit(10)` simply takes up to 10 entries in whatever order traversal sees them, **not necessarily the 10 smallest names**. If exact ordering is needed, sort first; keep in mind that `sorted` must process entries to determine order, which can consume significant memory for very large directories.

If you need stable pagination across queries in a concurrently modified directory, `Files.list` alone cannot provide a snapshot or fixed global order.

## 6. Example 2 — Filtering Direct Files vs. `Files.walk`

Create `ListVsWalkDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class ListVsWalkDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("list-walk-");
        try {
            Files.writeString(root.resolve("b.txt"), "B", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("a.txt"), "A", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("data.csv"), "1", StandardCharsets.UTF_8);
            Path folder = Files.createDirectories(root.resolve("sub"));
            Files.writeString(folder.resolve("inside.txt"), "I", StandardCharsets.UTF_8);

            try (Stream<Path> direct = Files.list(root)) {
                List<String> txtNames = direct.filter(Files::isRegularFile)
                        .map(p -> p.getFileName().toString())
                        .filter(name -> name.endsWith(".txt"))
                        .sorted().toList();
                System.out.println("direct .txt=" + txtNames);
            }
            try (Stream<Path> direct = Files.list(root)) {
                System.out.println("direct entries=" + direct.count());
            }
            try (Stream<Path> all = Files.walk(root)) {
                System.out.println("recursive regular files="
                        + all.filter(Files::isRegularFile).count());
            }
            try (Stream<Path> depthOne = Files.walk(root, 1)) {
                System.out.println("walk maxDepth1 entries=" + depthOne.count());
            }
        } finally {
            try (Stream<Path> all = Files.walk(root)) {
                all.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try { Files.deleteIfExists(p); }
                    catch (IOException e) { throw new UncheckedIOException(e); }
                });
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ListVsWalkDemo.java
java ListVsWalkDemo
```

```text
direct .txt=[a.txt, b.txt]
direct entries=4
recursive regular files=4
walk maxDepth1 entries=5
```

**Why do we get these numbers?**

- `Files.list(root)` gives four **direct** entries: `a.txt`, `b.txt`, `data.csv`, and directory `sub`. Thus `direct entries=4`.
- Filtering by `isRegularFile` and `.txt` yields only `a.txt` and `b.txt` in root. `inside.txt` is not in the `Files.list(root)` source, so it does not appear.
- `Files.walk(root)` by default traverses down the tree (not following symbolic links unless requested), including **both `root`** and descendant entries. When filtering for regular files, `inside.txt` deeper down is also counted; the total number of regular files is 4.
- `Files.walk(root, 1)` covers **root + entries up to depth 1**. Because `root` itself is included, the count is 5, unlike `Files.list(root)` which excludes `root`.

This is an easy-to-forget difference when comparing counts:

```text
Files.list(root)            -> direct child entries, DOES NOT include root
Files.walk(root, 1)         -> root AND direct child entries
Files.walk(root)            -> root and entries at multiple depths
Files.walk(root, 0)         -> root only
```

The element count of `Files.walk` can include directories as well; to count **regular files**, you must filter with `Files.isRegularFile` or use appropriate `BasicFileAttributes`.

## 7. Each `Files.list` Stream Is Single-Use Only

A Java `Stream` is not a `Collection` that can be freely iterated again. After a terminal operation such as `forEach`, `count`, or `toList`, the stream is considered consumed; calling a second terminal operation on the same stream typically throws `IllegalStateException`.

**Wrong** example:

```java
// Error illustration: do not reuse a Stream after a terminal operation.
try (Stream<Path> entries = Files.list(dir)) {
    long count = entries.count();
    entries.forEach(System.out::println); // Wrong: stream already consumed.
}
```

The right way when multiple passes are needed:

- **Open a new stream** with `Files.list(dir)` for each pass and close each stream.
- Or, if the directory is small enough, **collect** into a `List<Path>` once inside `try-with-resources`, then work with the list. The list only contains the enumerated `Path` objects; it does not guarantee each file still exists at later times.

Collection example:

```java
List<Path> snapshotOfNames;
try (Stream<Path> entries = Files.list(dir)) {
    snapshotOfNames = entries.sorted().toList();
}
System.out.println("Entries recorded=" + snapshotOfNames.size());
```

This is **illustrative code**. `toList()` is a Java 16+ method; the result is not an immutable snapshot of **file contents**, only a list of paths observed during traversal. Files may change or disappear immediately afterward.

Note that `sorted()` here uses `Path`'s natural comparison order, which depends on provider rules. If you want to sort **by filename** instead of by the full path, choose a comparator on `getFileName()`.

## 8. Why Is Closing the Stream Mandatory?

`Files.list` opens an entry-iteration source backed by a filesystem resource, such as a directory stream/handle. The JDK documentation specifies that the returned stream **contains a reference to an open directory**. Without closing it, the application can leak file descriptors/handles or hold resources longer than necessary.

Correct pattern:

```java
try (Stream<Path> entries = Files.list(dir)) {
    entries.forEach(this::processEntry);
}
```

This is only an **illustration inside an instance method** that has `processEntry(Path)` and variable `dir`; it is not a complete program. Required types must be imported and `IOException` handled.

**Common misconceptions:**

- Completing `entries.count()` **does not automatically close** the stream by contract.
- Completing `entries.forEach(...)` **does not automatically close** the stream.
- Completing `entries.toList()` **does not automatically close** the stream.
- Assigning `Files.list(dir)` to a static field to consume gradually over a service's lifetime makes lifecycle management difficult and easily causes leaks.
- `try-with-resources` closes the stream even when the terminal operation throws an exception.

If a library/API accepts a stream and processes it outside the method scope, clearly define **who owns the closing responsibility**. A cleaner choice is to process the data **inside** the `try` block, or collect small values that do not need to keep a file descriptor open after the block ends.

### Scope of Lazy Traversal and Closure

Intermediate operations like `filter`, `map`, and `sorted` only build a pipeline; terminal operations such as `count`, `forEach`, and `toList` trigger actual traversal. The directory can still change during traversal; `Files.list` does not create a fixed state snapshot.

Place both stream creation and the terminal operation inside the same `try-with-resources`, rather than creating a stream in one method and returning it to a caller unaware of the obligation to close it.

## 9. Errors When Opening or Iterating a Directory

`Files.list(dir)` declares `throws IOException`. Possible failure cases include:

- `dir` does not exist: with the default provider this is typically `NoSuchFileException`.
- `dir` is a regular file instead of a directory: may be `NotDirectoryException` or an appropriate system `IOException`.
- Missing permission to open/read the directory: may be `AccessDeniedException` or another `IOException`.
- The directory changes or a device fails **while iterating**: an I/O exception may occur after the stream is created.

Subtypes are not guaranteed to be identical across every OS/provider. Handle `IOException` with context rather than turning every failure into “empty directory.”

### Distinguishing Open-Time vs. Iteration-Time Exceptions

When failing immediately in `Files.list(dir)`, you receive an `IOException`. If an I/O error happens **after the stream has been created** while fetching entries, it may be wrapped in an **`UncheckedIOException`**, because the `Stream` mechanism does not declare checked exceptions at every pipeline step.

Illustrative handling pattern:

```java
try (Stream<Path> entries = Files.list(dir)) {
    entries.forEach(System.out::println);
} catch (UncheckedIOException e) {
    // I/O error while iterating the stream; check e.getCause().
} catch (IOException e) {
    // Error opening directory or closing resource.
}
```

This is **illustrative code**, requiring imports for `Files`, `Path`, `Stream`, `IOException`, and `UncheckedIOException`, plus a `dir` variable. Exceptions thrown inside the `forEach` callback must also be handled according to their meaning.

Avoid writing code like this:

```java
try (Stream<Path> entries = Files.list(dir)) {
    // ...
} catch (IOException e) {
    return List.of(); // Does not distinguish an empty directory from an I/O error!
}
```

This snippet illustrates an anti-pattern, assuming a method returning `List<Path>`. Returning an empty list on error can cause an auditing/search system to report “no data found” instead of reporting “could not inspect data.”

## 10. Example 3 — Missing Directory, Open Errors, and Stream Lifecycle

Create `ListErrorsDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public class ListErrorsDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("list-error-");
        try {
            Path file = root.resolve("single.txt");
            Files.writeString(file, "x", StandardCharsets.UTF_8);
            Path missing = root.resolve("missing");
            try (Stream<Path> ignored = Files.list(missing)) {
                System.out.println("unexpected");
            } catch (NoSuchFileException e) {
                System.out.println("missing directory=" + e.getClass().getSimpleName());
            }
            try (Stream<Path> one = Files.list(root)) {
                System.out.println("listed file=" + one.findFirst()
                        .orElseThrow().getFileName());
            }
            System.out.println("still open for new traversal="
                    + Files.isDirectory(root));
        } finally {
            try (Stream<Path> all = Files.walk(root)) {
                all.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try { Files.deleteIfExists(p); }
                    catch (IOException e) { throw new UncheckedIOException(e); }
                });
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ListErrorsDemo.java
java ListErrorsDemo
```

```text
missing directory=NoSuchFileException
listed file=single.txt
still open for new traversal=true
```

Interpretation:

- `missing` was never created, so `Files.list(missing)` on a typical filesystem reports `NoSuchFileException`.
- `root` still exists with one child file. `Files.list(root)` supplies the `single.txt` entry.
- `findFirst()` requests a first element from a stream with **unspecified order**. Here there is only **one entry**, so output is deterministic. If a directory has multiple entries, do not infer that `findFirst` returns the alphabetically smallest name.
- The first stream is opened in a `try-with-resources` block. Because `Files.list(missing)` throws before creating a stream, no stream resource is assigned; control jumps to `catch`. For the successful stream, Java closes it upon leaving the block.
- Afterward, the example continues reading the directory normally. The demo files are cleaned up in `finally` because the program exclusively owns this temporary directory.

**Do not conclude** that `Files.list` “had to close so the directory would remain.” Closing the stream releases the handle; it **does not delete** the directory. `Files.isDirectory(root)` returning `true` merely checks that the directory currently exists at call time.

## 11. Comparing `Files.list`, `Files.walk`, `Files.find`, and `walkFileTree`

| API | Scope | Result / Behavior | Best Fit |
|---|---|---|---|
| `Files.list(dir)` | **One level**, direct children | `Stream<Path>`, excludes `dir` | Listing files/dirs immediately under one folder |
| `Files.walk(start)` | Recursive from `start` (subject to depth/options) | `Stream<Path>` **includes `start`** | Multi-level traversal, filtering paths |
| `Files.walk(start, maxDepth)` | Depth-bounded recursion | `Stream<Path>` includes `start` | Limiting traversal cost/scope |
| `Files.find(start, maxDepth, matcher, options...)` | Depth-bounded recursion | `Stream<Path>`, matcher receives `Path` and `BasicFileAttributes` | Searching by path together with metadata |
| `Files.walkFileTree(start, visitor)` | Callback-driven tree traversal | Invokes visitor before/on/after dir, reports errors | Controlled copy/delete/scan tree tools |
| `Files.newDirectoryStream(dir)` | One level, direct children | `DirectoryStream<Path>`, supports entry filtering | One-level iteration with iterator and provider handling |

### When You Only Need Depth 1

`Files.list(root)` is close to `Files.walk(root, 1)` in covering **direct children**, but the two APIs **do not produce the same result set**:

- `Files.list(root)` returns only child entries.
- `Files.walk(root, 1)` returns **root first, plus entries up to depth 1**, following `walk` traversal rules.

If comparing or migrating between `list` and `walk`, remember to exclude `root` if your business logic only wants direct children.

### When You Want Recursion

Do not write:

```java
Files.list(root).filter(p -> p.getFileName().toString().equals("deep.txt"))
```

and then conclude `deep.txt` does not exist anywhere under `root`. The file might be inside `root/docs/nested`.

If the requirement truly is to find files at all levels, a simple example is:

```java
try (Stream<Path> entries = Files.walk(root)) {
    entries.filter(Files::isRegularFile)
           .filter(p -> p.getFileName().toString().endsWith(".txt"))
           .forEach(System.out::println);
}
```

This is an **illustrative snippet**, not a standalone program; it requires `root`, imports, and `IOException` handling. `Files.walk` recurses by default through valid directory depths and **does not automatically follow symbolic links** unless `FOLLOW_LINKS` is passed. Avoid unbounded or overly expensive traversals on huge trees; when only direct children are needed, `Files.list` is simpler.

### When You Need Per-Directory State Handling

`walkFileTree` fits better when an application needs to know when it **enters** a directory, **exits** a directory, handles access errors per branch, or performs operations like deleting a tree rather than just inspecting paths. `Files.list` is not a whole-tree visitor.

## 12. `newDirectoryStream`: An Alternative for One-Level Traversal

`Files.newDirectoryStream(dir)` returns a `DirectoryStream<Path>` of direct entries. It also **must be closed**:

```java
try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir)) {
    for (Path entry : ds) {
        System.out.println(entry.getFileName());
    }
}
```

This is **illustrative code**, requiring imports for `java.nio.file.DirectoryStream`, `Files`, and `Path`, a `dir` variable, and `IOException` handling. This API is useful when you prefer an iterator style or filtering at directory-entry retrieval time:

```java
try (DirectoryStream<Path> ds =
             Files.newDirectoryStream(dir, "*.txt")) {
    for (Path entry : ds) {
        System.out.println(entry.getFileName());
    }
}
```

This is an **illustrative snippet**; the glob `"*.txt"` applies to **direct entry names**, without recursion. In some situations, `DirectoryStream.Filter<? super Path>` allows filtering by custom conditions. Whether using `newDirectoryStream` or `Files.list`, neither walks the entire tree automatically.

When you are already processing data in `Stream` style, `Files.list` is concise. When you want a direct loop over directory entries, `newDirectoryStream` is equally suitable. There is no reason to force every piece of code into Streams when the iterator API solves the problem cleanly.

## 13. Filesystems, Symbolic Links, and Entry Types

### `Files.list` Does Not Mean “Regular Files Only”

`Files.list(dir)` returns directory entries. Inside a directory there may be:

- Regular files.
- Subdirectories.
- Symbolic links.
- Other special entry types depending on the filesystem.

`Files.isRegularFile(p)` checks whether a `Path` points to a regular file. By default, many path checks **follow symbolic links** to their target if present; if you want to inspect the link itself, pass `LinkOption.NOFOLLOW_LINKS` to APIs that support it.

Example checks (illustrative code):

```java
boolean isRegular = Files.isRegularFile(entry);
boolean isDirectory = Files.isDirectory(entry);
boolean isLink = Files.isSymbolicLink(entry);
```

Requires a `Path entry` and importing `Files`; each result reflects information at check time and may change immediately afterward.

### Does `Files.list` Follow Symlinks to Recurse?

**There is no recursion in the first place.** If an entry is a symlink to another directory, `Files.list(root)` only yields that **direct symlink entry** as a `Path`; it does not open the target directory tree to include grandchild entries in the same stream.

If you **pass a `Path` pointing through a symlink to a directory** as the `dir` argument itself, how the provider resolves paths may allow listing the target directory. That is a different scenario from recursing into an entry found inside `root`.

With `Files.walk`, whether to follow links is controlled by options such as `FOLLOW_LINKS`; when following links on a tree containing a cycle, traversal may report `FileSystemLoopException`. Therefore, deep traversal code must account for symlinks before enabling follow links.

### “Hidden Files” Are Still Entries

`Files.list` does not automatically exclude hidden files, dot-prefixed filenames, or other entries simply because a file manager UI hides them. If you want to skip entries considered hidden, consider `Files.isHidden(path)`, keeping in mind that its semantics depend on the filesystem and it may throw `IOException`. Never assume “filename starts with `.`” is the universal definition of a hidden file across all OSes.

## 14. Limitations of `Files.list` to Know

### 14.1 No Default Ordering

If your application builds a UI table or exports reports requiring stability, you must explicitly decide to sort by **name**, modification time, size, or another criterion. Do not treat arbitrary filesystem order as business data order.

### 14.2 Does Not Create an Immutable Snapshot

The directory can be modified by other threads/processes while the stream is open. Modifications may or may not appear in the listed entries; `Files.list` is **weakly consistent** per the documentation and does not provide an atomic snapshot.

If you need a guarantee of “the list at a single point in time,” use a snapshot mechanism, coordinate with the producer, or adopt an appropriate versioning/synchronization strategy. `toList()` only records the `Path` objects seen; it does not lock files or freeze metadata.

### 14.3 Does Not Automatically Fetch Metadata for Filtering

`Files.list` returns `Path`; operations like `Files.isRegularFile`, `Files.size`, or `Files.getLastModifiedTime` may perform additional filesystem queries, and state can change between calls. If you need deep traversal together with each entry's metadata, `Files.find` accepts a predicate taking `BasicFileAttributes`, expressing that job directly.

### 14.4 Does Not Bypass Permission Errors

Having permission to see a filename does not guarantee permission to open or read that file's contents. Conversely, `Files.list` may fail when a directory cannot be read even if a specific `Path` elsewhere can still be accessed directly. Design your code to separate **listing**, **reading files**, **writing files**, and **deeper directory traversal**.

### 14.5 Listing Very Large Directories Has Costs

Creating a stream does not mean loading all results into RAM up front. However, `sorted()`, `toList()`, or `collect` can retain many entries in memory. For directories with millions of entries, consider limiting processing, batching, streaming, bounding depth, timeouts, and storage/index designs instead of blindly collecting everything.

### 14.6 Parallel Traversal Is Not Automatically Better

`entries.parallel()` does not turn the filesystem into a source that supports efficient parallel traversal. Metadata I/O and ordering requirements can keep performance from improving or make resource management harder. Prefer clear sequential execution for standard listing tasks; only parallelize when needed and after real measurement.

## 15. When Should You Use `Files.list` in Applications?

### Scenario A — Displaying the Immediate Contents of a Folder

A file manager application needs to list items under the current path: `Files.list(currentDirectory)` is the right model. Each entry can be displayed with its name, type, size, and an action to open a subdirectory when clicked. **Only when the user navigates into a subdirectory** does the application list that subdirectory.

### Scenario B — Processing All Import Files Directly Inside an Inbox

A file-ingestion service for an `inbox` folder has a rule: process only files placed **directly in `inbox`**, without scanning `inbox/archived` or `inbox/failed`. `Files.list(inbox).filter(Files::isRegularFile)` fits well because it will not accidentally sweep subdirectories.

Even so, if a file is currently being copied into `inbox`, you may observe a partial file or an entry changing between listing and reading. Establish a complete-file publishing convention (such as writing to a temp location and renaming/moving per contract) rather than treating `list` as confirmation that the file is ready.

### Scenario C — Finding a File with an Exact Name at the Current Level

If you already know the filename, you usually **do not need to list**:

```java
Path candidate = dir.resolve("config.json");
if (Files.isRegularFile(candidate)) {
    // Work with candidate and handle errors when actually opening it.
}
```

This is **illustrative code**, requiring `dir`, class imports, and I/O handling. Constructing the exact path and opening it can be simpler and more efficient than scanning the entire directory for a fixed name.

Only when you must find “`config.json` in any subdirectory” should you consider `Files.walk`/`Files.find` or a dedicated file index.

### Scenario D — Single-Level Reporting

For counting **how many child entries** or **how many regular files are at the current level**, `Files.list` matches the requirement directly. If you only need to count regular files:

```java
try (Stream<Path> entries = Files.list(dir)) {
    long directFiles = entries.filter(Files::isRegularFile).count();
}
```

This is **illustrative code**, not a standalone program. The result excludes deeper files, and there is no guarantee that the filesystem remains unchanged during counting.

## 16. Do Not Treat Listing Results as Sufficient Security Validation

A `Path` from `Files.list` may be used for deleting, moving, uploading, or authorization logic. Yet **merely seeing an entry under root** does not guarantee all subsequent operations are safe:

- Symbolic links can point elsewhere.
- Files can be modified or replaced after listing (**TOCTOU**, time-of-check-to-time-of-use).
- A listed entry can vanish before it is opened.
- Directory read permissions differ from file content read or write permissions.
- If the application appends a user-supplied name to a path, handle `..`, absolute paths, root boundaries, and symlinks according to your threat model.

`normalize()` only cleans up path syntax; it **does not** lock the filesystem or resolve symlinks. `Path.startsWith(root)` is better than string prefix checks, yet still insufficient against symlinks/races for untrusted input.

For sensitive file-management programs, perform the required operation directly and handle errors; consider directory-handle-based APIs such as `SecureDirectoryStream` where supported by the provider, along with filesystem permissions and appropriate TOCTOU defenses.

## 17. Self-Check and Common Pitfalls

**Pitfall 1 — Thinking `Files.list` is recursive.** Only direct children are included; deeper files are not in the stream.

**Pitfall 2 — Forgetting that results also include directories.** If counting regular files, use `filter(Files::isRegularFile)`.

**Pitfall 3 — Forgetting to close the stream.** Terminal operations do not guarantee closing the directory handle; use `try-with-resources`.

**Pitfall 4 — Thinking the list is sorted.** Order is not guaranteed; use an appropriate comparator.

**Pitfall 5 — Reusing the stream after `count()` or `forEach()`.** A stream cannot be consumed again; open a new stream or collect when scale allows.

**Pitfall 6 — Confusing `Files.walk(dir, 1)` and `Files.list(dir)` counts.** `walk` also includes `dir` itself.

**Pitfall 7 — Using `.getFileName()` while expecting a full file path.** Keeping only the final name loses directory context.

**Pitfall 8 — Returning an empty list when lacking read permission.** “Empty directory” and “read failure” must remain two distinct states.

**Pitfall 9 — Failing to handle `UncheckedIOException`.** It can be thrown during stream traversal after the stream was opened successfully.

**Pitfall 10 — Using `Files.isRegularFile` as a guarantee the file won't change.** A file can be deleted, moved, or have permissions changed after the check.

**Pitfall 11 — Automatically following links to recurse without handling cycles.** `Files.list` does not recurse; when using `walk` with `FOLLOW_LINKS`, have a strategy for links and loops.

**Pitfall 12 — Collecting/sorting every entry of a massive directory.** This can exhaust RAM and time; choose streaming or indexing according to goals.

**Pitfall 13 — Thinking `.txt` proves text content.** An extension is only part of a name; it does not guarantee valid charset, MIME type, or content.

**Pitfall 14 — Thinking `Files.list` reads file contents.** It only supplies paths; reading files requires other APIs.

**Pitfall 15 — Using `limit(N)` before sorting and expecting “the first N alphabetical files.”** Consider operation order and output requirements; `list` has no default ordering.

**Pitfall 16 — Relying on an unchanging filesystem.** `Files.list` provides no atomic snapshot and may reflect concurrent changes during iteration.

## 18. Quick Decision Table

| Goal | Recommended API | Notes |
|---|---|---|
| List entries immediately in one directory | `Files.list(dir)` | One level, excludes `dir`; remember to close |
| Get filenames at the current level | `list(dir).map(p -> p.getFileName())` | Not automatically sorted |
| Count direct regular files | `list(dir).filter(Files::isRegularFile).count()` | Excludes files in subdirectories |
| Filter filenames by glob at current level | `Files.newDirectoryStream(dir, "*.txt")` | Not recursive; must close |
| Find files at all levels | `Files.walk(dir)` | Includes root; can be resource-intensive |
| Traverse only up to depth 1 from root | `Files.walk(dir, 1)` | Includes root; differs from `list` |
| Search by name + metadata across a tree | `Files.find(dir, depth, predicate)` | Provides `BasicFileAttributes` |
| Perform conditional tree copy/delete | `Files.walkFileTree` | Visitor/error handling |
| Access a file **whose exact path is known** | `dir.resolve(name)` then open/check | No need to list the entire directory |
| Build a single-level file browser UI | `Files.list(currentDir)` | Display folders as entries; descend on request |

## 19. Practice Questions

**Question 1.** Directory `root` contains `a.txt` and `docs`; `docs` contains `b.txt`. Does `Files.list(root)` return `b.txt`?  
**Answer:** No. Only `a.txt` and `docs` are direct children.

**Question 2.** Is `Files.list(root).count()` the total number of files in the whole tree?  
**Answer:** No. It counts entries at one level, including directories, symlinks, or other entries if present.

**Question 3.** Can `Files.list(root).filter(Files::isRegularFile)` find regular files inside `root/docs`?  
**Answer:** No; a filter does not make it recursive. You need a deep traversal API or to open `docs` separately.

**Question 4.** Why can `Files.walk(root, 1).count()` be greater than `Files.list(root).count()` by exactly 1?  
**Answer:** `walk(root, 1)` also yields `root` itself, whereas `list` yields only direct children.

**Question 5.** If a `Files.list` stream has already called `count()`, can you call `forEach()` on it afterward?  
**Answer:** No. You need a new stream or to collect the data on the first pass.

**Question 6.** After `Files.list(dir).toList()`, does the directory handle close automatically?  
**Answer:** There is no guarantee of automatic closure from a terminal operation alone; create the stream in `try-with-resources`.

**Question 7.** Does `Files.list` always return names alphabetically?  
**Answer:** No; sort explicitly when needed.

**Question 8.** If `Files.list` fails due to missing read permissions on a directory, should you report “empty directory”?  
**Answer:** No; report/record the access error separately.

**Question 9.** An entry is a symbolic link to a directory containing many files. Does `Files.list(root)` automatically add all files in the link's target to the results?  
**Answer:** No; it only lists the link entry at the direct level. Traversing further is a separate decision.

**Question 10.** Why does calling `Files.isRegularFile(p)` right after listing not guarantee `Files.readString(p)` will succeed?  
**Answer:** Permissions and filesystem state can change between checking and opening; the file can also be replaced or deleted.

## Conclusion

**`Files.list(dir)` lists only the direct child entries of `dir` — it does not automatically descend into subdirectories and does not include `dir` itself.** It returns a `Stream<Path>` so you can filter, map, count, or sort, but it **guarantees no ordering**, **does not filter to regular files automatically**, and **must be closed** because it holds a directory resource.

When a task requires only one level, `Files.list` is the right, simple tool. When a task requires multiple levels, use `Files.walk`, `Files.find`, or `Files.walkFileTree` depending on the level of control required. In all cases, properly handle I/O exceptions, symbolic links, stream lifecycles, and a filesystem state that may change concurrently.

### Java SE 17 Documentation

- [`Files.list(Path)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#list(java.nio.file.Path))
- [`Files.walk`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`Files.find` and `walkFileTree`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`DirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html)
- [`Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [`UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html)
