# Reading Lines with Files.lines and Traversing Directory Trees with Files.walk in Java 17

When working with files in Java, two needs arise frequently: **reading content line by line** and **finding files inside a directory and its subdirectories**. Since Java 8, the **java.nio.file.Files** class provides **Files.lines()** and **Files.walk()** to perform both tasks using the Stream API. Both APIs remain supported and standard in Java 17.

**Files.lines()** returns a **Stream<String>** for processing each line of a file. **Files.walk()** returns a **Stream<Path>** for traversing paths in a directory tree. Because both return streams that can hold open I/O resources, **closing the stream properly with try-with-resources** is an essential part of using them.

This lesson covers how to read large files without loading the entire content into memory, choosing a charset, handling I/O errors, traversing directories with depth limits, filtering files, handling symbolic links, and applying these APIs in real-world programs.

## 1. What Problems Do the Two APIs Solve?

| API | Input | Result | Purpose |
| --- | --- | --- | --- |
| **Files.lines(path)** | Path to a file | **Stream<String>** | Read text line by line. |
| **Files.walk(path)** | Starting path of a directory tree or a file | **Stream<Path>** | Traverse the starting path and entries underneath it. |

For example, given a directory tree:

~~~text
project/
├── README.md
├── config/
│   └── app.properties
└── logs/
    ├── app.log
    └── archive/
        └── old.log
~~~

**Files.lines(Path.of("project/logs/app.log"))** reads the lines in a specific log file. **Files.walk(Path.of("project"))** traverses `project`, its subdirectories, and the files found within that tree.

Both APIs return streams, so they can be composed with operations such as `filter`, `map`, `flatMap`, `forEach`, `count`, or `collect`. Reading/traversing is performed lazily: elements are typically fetched as the stream is consumed, rather than forcing all results to be loaded when the stream is created.

## 2. Reading Line by Line with Files.lines()

### 2.1. Basic Syntax

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data", "messages.txt");

try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(System.out::println);
} catch (IOException e) {
    System.err.println("Cannot open file: " + e.getMessage());
}
~~~

Explanation:

- `Path.of(...)` creates the path to the file.
- `Files.lines(path)` opens the file and returns a `Stream<String>`.
- Each stream element is the content of one line, without line terminator characters.
- `forEach` is a terminal operation that consumes the lines to print them.
- `try-with-resources` calls `close()` on the stream when the block exits, even if the body encounters an error.

**Do not omit try-with-resources just because you called forEach.** Completing a terminal operation does not replace the responsibility of closing the stream. The stream holds the file's underlying resources until closed.

### 2.2. Files.lines() Is Lazy

The statement:

~~~java
Stream<String> lines = Files.lines(path);
~~~

does not mean all lines have already been read and stored in a list. The stream yields lines when a consuming operation runs, for example:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines.count();
    System.out.println("Line count: " + count);
}
~~~

This is useful for large files because the program does not need to hold the entire list of lines on the heap. However, lazy does not mean zero memory usage: the library still uses read buffers, and downstream operations may accumulate data themselves. For example, `collect(Collectors.toList())` still builds a list containing every line.

### 2.3. Conditional Reading

Streams allow filtering and transforming data while reading:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.filter(line -> !line.isBlank())
            .map(String::strip)
            .forEach(System.out::println);
}
~~~

In this example:

- `filter` drops empty or whitespace-only lines.
- `map(String::strip)` removes leading and trailing whitespace from each line.
- `forEach` processes the remaining lines.

Note that `strip()` alters the processed string. If leading or trailing whitespace is significant, such as in fixed-width data files, do not remove it.

## 3. Charsets and Text Interpretation

### 3.1. Choosing an Explicit Charset

`Files.lines(Path)` uses UTF-8. When you know the file's charset, you can pass it explicitly:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
}
~~~

Common charsets:

| Charset | When Encountered |
| --- | --- |
| StandardCharsets.UTF_8 | UTF-8 text; standard choice for new files and modern data exchange. |
| StandardCharsets.UTF_16 | Data encoded as UTF-16. |
| StandardCharsets.ISO_8859_1 | Certain legacy formats or protocols specifying Latin-1. |
| Charset.forName("...") | When supporting a specific charset required by a data contract. |

Example with a configured charset:

~~~java
Charset charset = Charset.forName("windows-1252");
try (Stream<String> lines = Files.lines(path, charset)) {
    lines.forEach(System.out::println);
}
~~~

Only choose a charset when you know the data is actually encoded with it. Reading a UTF-8 file as Windows-1252 may not throw an error, yet produces garbled characters (mojibake). Conversely, an incompatible charset can also cause the decoder to fail on certain input bytes.

### 3.2. Do Not Rely on the Machine's Default Charset

When processing multilingual text or data exchanged between systems, agree on an encoding and declare it explicitly in code:

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    // Process UTF-8 data.
}
~~~

This keeps file-reading behavior consistent across developer machines, CI, and production. Especially with legacy data, verify the source that produced the file rather than guessing the charset from how it visually appears.

### 3.3. BOM at the Start of a File

Some UTF-8 files begin with a byte order mark (BOM). UTF-8 does not need a BOM to determine byte order; if a file contains a BOM, normal decoding can include the character `U+FEFF` at the beginning of the first line. If your file format specifies stripping the BOM, handle it explicitly, for instance removing it only at the beginning of the first line:

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.map(line -> line.startsWith("\uFEFF")
                    ? line.substring(1)
                    : line)
            .forEach(System.out::println);
}
~~~

Do not strip `U+FEFF` everywhere arbitrarily if that character can appear as legitimate data.

## 4. Blank Lines, Line Terminators, and Empty Files

`Files.lines()` returns line contents excluding line terminator characters. Common line terminators—LF, CR, and CRLF—are all treated as boundaries between lines.

For example, given a file containing:

~~~text
alpha
beta
gamma
~~~

The stream contains three elements:

~~~text
alpha
beta
gamma
~~~

There is no trailing newline character at the end of each element. If you need to reconstruct multiline text, you must choose how to join lines explicitly.

### 4.1. Empty Files and Blank Lines

- An empty file yields a stream with zero elements; `count()` returns 0.
- A file with one line containing empty text due to a single line terminator can yield one empty string element.
- Blank lines in the middle of a file are returned as empty strings; `isBlank()` also returns true for whitespace-only lines.
- A file ending with a line terminator does not produce an extra trailing phantom line after the final terminator.
- A final line without a line terminator is still returned normally.

You can verify this with a self-contained file example:

~~~java
import java.nio.charset.StandardCharsets;

Path path = Path.of("sample-lines.txt");
Files.writeString(path, "first\n\nthird", StandardCharsets.UTF_8);

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(line -> System.out.println("[" + line + "]"));
}
~~~

Output:

~~~text
[first]
[]
[third]
~~~

If you need to know which line is first/last or track line numbers, use a counter during sequential processing or maintain a dedicated numbering step. Do not assume `Stream<String>` tracks line numbers automatically.

## 5. Handling Errors When Reading the Stream

`Files.lines()` can fail at two distinct points:

1. **When opening the file:** the method may throw `IOException` (for example, if the file does not exist or cannot be opened).
2. **While consuming the stream:** subsequent read errors are wrapped in `UncheckedIOException` and thrown from the stream operation triggering the read.

Example handling both:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data", "events.log");

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> line.contains("ERROR"))
            .forEach(System.out::println);
} catch (UncheckedIOException e) {
    System.err.println("Error while reading: " + e.getCause());
} catch (IOException e) {
    System.err.println("Error opening/closing file: " + e.getMessage());
}
~~~

`UncheckedIOException` is a runtime exception with `getCause()` providing access to the underlying `IOException`. `try-with-resources` still closes the stream when an exception occurs. In production code, explicitly decide whether to continue, report an error, retry, or abort the task; never swallow I/O errors and treat partial data as complete.

### 5.1. Why Not Call forEach Outside try-with-resources?

The snippet below works for reading, but fails to close the stream:

~~~java
Files.lines(path).forEach(System.out::println);
~~~

Write instead:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(System.out::println);
}
~~~

Streams can hold file descriptors and other system resources. If unclosed, a long-running program reading many files may leak too many file handles.

### 5.2. Avoid Passing Open Streams Across Many Call Layers

Do not return a `Stream<String>` from a method that opened a file without clarifying who is responsible for closing it. If you must return a stream, the API contract must state that the caller must close it. A simpler option is processing within the method's scope:

~~~java
static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

This method returns the computed result and manages the stream lifecycle itself.

## 6. Example: Reading a Large Log File Line by Line

There is no need to load an entire log into a `List<String>` if you only want to count or filter:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class LogReader {
    public static void main(String[] args) throws IOException {
        Path logFile = Path.of("logs", "application.log");

        try (Stream<String> lines =
                Files.lines(logFile, StandardCharsets.UTF_8)) {
            long errorCount = lines
                    .filter(line -> line.contains("ERROR"))
                    .count();
            System.out.println("Total ERROR lines: " + errorCount);
        } catch (UncheckedIOException e) {
            throw new IOException("Failed to read entire log", e.getCause());
        }
    }
}
~~~

`count()` consumes the stream once. After a terminal operation, do not reuse the consumed stream. If you need to act on each line as it is read, use `forEach`; if you need an aggregated result, pick an appropriate collector or reduction.

## 7. Traversing Directory Trees with Files.walk()

### 7.1. Basic Syntax

`Files.walk(start)` returns a `Stream<Path>` containing the starting path and the entries in the directory tree beneath it:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path root = Path.of("project");

try (Stream<Path> paths = Files.walk(root)) {
    paths.forEach(System.out::println);
} catch (IOException e) {
    System.err.println("Cannot traverse directory: " + e.getMessage());
}
~~~

Key points to remember:

- The `root` path itself is also an element of the stream.
- If `root` is a directory, entries beneath it are traversed depth-first.
- If `root` is a file, the stream contains only that path.
- By default, `Files.walk` **does not follow symbolic links**.
- The stream must be closed with `try-with-resources`.

Ordering among sibling entries is not guaranteed to follow any specific name order. If deterministic output is required, sort the paths:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.map(Path::toString)
            .sorted()
            .forEach(System.out::println);
}
~~~

Sorting requires buffering or ordering entries before printing; for very large trees, this can significantly increase memory usage.

### 7.2. Selecting Regular Files Only

Usually you do not want to print directories, only files:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.isRegularFile(path)` checks whether the path points to a regular file. By default, this check follows symbolic links; if a path is a symlink to a regular file, it can return true.

If you want only entries that are regular files **and are not themselves symlinks**, use `LinkOption.NOFOLLOW_LINKS`:

~~~java
import java.nio.file.LinkOption;

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(path ->
                    Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
            .forEach(System.out::println);
}
~~~

### 7.3. Filtering by Extension

Example finding `.java` files:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .filter(path -> path.getFileName().toString().endsWith(".java"))
            .forEach(System.out::println);
}
~~~

`endsWith(".java")` is case-sensitive. If the system must also match `.JAVA`, normalize the name with an appropriate locale or perform a case-insensitive check:

~~~java
.filter(path -> path.getFileName().toString()
        .toLowerCase(Locale.ROOT).endsWith(".java"))
~~~

Do not call `toLowerCase()` with the default locale on technical identifiers when consistent cross-machine results are needed.

### 7.4. Finding Files by Name

~~~java
String expectedName = "application.properties";

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .filter(path -> path.getFileName() != null)
            .filter(path -> path.getFileName().toString()
                    .equals(expectedName))
            .forEach(System.out::println);
}
~~~

`getFileName()` can return `null` on certain root paths, so checking for null before converting to a string makes the example more general.

## 8. Limiting Depth with Files.walk(start, maxDepth, ...)

The overload accepting `maxDepth` lets you limit traversal depth:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
~~~

Depth is measured from `start`:

~~~text
root/                    depth 0
├── README.md            depth 1
├── config/              depth 1
│   └── app.properties   depth 2
└── logs/                depth 1
    └── app.log          depth 2
~~~

With `maxDepth = 2`, entries up to depth 2 are included in the stream; directories at that depth are not traversed any deeper.

| maxDepth | Scope |
| --- | --- |
| 0 | Only the starting path. |
| 1 | The starting path and its immediate entries. |
| 2 | One additional subdirectory level. |
| Integer.MAX_VALUE | Largest practical limit allowed by the API; the `walk(start)` overload uses this maximum depth. |

`maxDepth` is not a file count limit. It limits **the number of directory levels** traversed. If you only want a maximum number of results, you can use `limit(n)`, keeping in mind that traversal may stop before scanning the entire tree:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .limit(20)
            .forEach(System.out::println);
}
~~~

## 9. Symbolic Links and FileVisitOption.FOLLOW_LINKS

By default, `Files.walk` does not follow symbolic links. A symlink to a directory appears as a path entry, but the target directory tree is not traversed through that link.

If you truly need to follow symlinks, pass `FileVisitOption.FOLLOW_LINKS`:

~~~java
import java.nio.file.FileVisitOption;

try (Stream<Path> paths = Files.walk(
        root,
        Integer.MAX_VALUE,
        FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
~~~

### 9.1. Risk of Link Loops

Symlinks can form cycles:

~~~text
root/
└── child/
    └── back-to-root -> ../..
~~~

When following links, traversal can revisit a directory it already entered. Java detects symlink cycles while following links and can report `FileSystemLoopException`. With `Files.walk`, I/O errors encountered during stream traversal are wrapped in `UncheckedIOException`.

Only enable `FOLLOW_LINKS` when explicitly required. Keeping the default avoids accidentally traversing outside the intended tree or encountering link cycles.

### 9.2. Explicitly Checking for Symlinks

If you want to exclude all symlinks from results:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(path -> !Files.isSymbolicLink(path))
            .filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.isSymbolicLink(path)` inspects the path entry itself. If your application must distinguish symlinks, junctions, or reparse points per OS specifics, check the behavior of the filesystem provider in use.

## 10. I/O Errors During Directory Tree Traversal

Like `Files.lines`, `Files.walk` can throw `IOException` when starting traversal and wrap I/O errors raised during stream consumption in `UncheckedIOException`.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path root = Path.of("data");

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
} catch (UncheckedIOException e) {
    System.err.println("Error while traversing tree: " + e.getCause());
} catch (IOException e) {
    System.err.println("Cannot start/close traversal: " + e.getMessage());
}
~~~

Common causes:

- the directory does not exist;
- the running account lacks access permissions;
- an entry is deleted or renamed during traversal;
- filesystem or storage device error;
- a symbolic link loop when `FOLLOW_LINKS` is enabled.

`Files.isRegularFile()` and related attribute checks return `false` if the file type cannot be determined reliably; they do not replace traversal error handling. If your application needs to report each access failure individually and continue traversing the rest, `Files.walkFileTree()` with a `FileVisitor` may be a better fit.

### 10.1. Directory Trees Can Change During Traversal

`Files.walk` does not create an immutable snapshot of the filesystem. If files or directories are added, deleted, or renamed while the stream is active, whether those changes are observed depends on the filesystem provider and timing.

If consistent results at a specific point in time are needed, coordinate application-level locking/snapshotting or work on a stable copy. Do not assume the stream is an atomic snapshot of the entire tree.

## 11. Combining Files.walk() with Files.lines()

A common scenario is finding all logs in a directory, then reading each file and counting lines containing a keyword.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class SearchLogs {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("logs");
        String keyword = "ERROR";

        try (Stream<Path> files = Files.walk(root)) {
            files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString()
                            .endsWith(".log"))
                    .forEach(path -> {
                        try (Stream<String> lines =
                                Files.lines(path, StandardCharsets.UTF_8)) {
                            long count = lines
                                    .filter(line -> line.contains(keyword))
                                    .count();
                            System.out.println(path + ": " + count);
                        } catch (IOException | UncheckedIOException e) {
                            System.err.println("Unable to read "
                                    + path + ": " + e.getMessage());
                        }
                    });
        } catch (UncheckedIOException e) {
            throw new IOException("Error traversing log directory",
                    e.getCause());
        }
    }
}
~~~

There are two independent streams, hence two resource-closing scopes:

1. `files` holds the traversal resource of `Files.walk`.
2. Each `lines` holds the currently scanned log file and is closed right after counting.

Do not close the traversal stream before finishing path processing. Likewise, do not collect all paths and all file contents into memory when processing one file at a time suffices.

## 12. Using Files.walk for Directory Tree Statistics

Example counting regular files by extension:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;

public class ExtensionReport {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("project");
        Map<String, Long> counts = new TreeMap<>();

        try (Stream<Path> paths = Files.walk(root)) {
            paths.filter(Files::isRegularFile)
                    .forEach(path -> {
                        Path name = path.getFileName();
                        String fileName = name == null
                                ? ""
                                : name.toString();
                        int dot = fileName.lastIndexOf('.');
                        String extension = dot >= 0
                                ? fileName.substring(dot).toLowerCase(Locale.ROOT)
                                : "(no extension)";
                        counts.merge(extension, 1L, Long::sum);
                    });
        }

        counts.forEach((extension, count) ->
                System.out.println(extension + ": " + count));
    }
}
~~~

This example uses a `TreeMap` to report results ordered by key. Normalizing extensions with `Locale.ROOT` keeps output independent of the host machine's default locale.

## 13. When to Use Files.walkFileTree() Instead of Files.walk()?

`Files.walk()` is ideal when processing a directory tree with stream transformations. However, if fine-grained traversal control is needed, `Files.walkFileTree()` with a `FileVisitor` may be more appropriate:

| Need | API to Consider |
| --- | --- |
| Obtain paths and filter/map/count | `Files.walk()` |
| Read one file line by line | `Files.lines()` |
| Prune an entire subdirectory | `Files.walkFileTree()` and `SKIP_SUBTREE` |
| Custom work before/after entering a directory | `FileVisitor.preVisitDirectory` / `postVisitDirectory` |
| Handle per-file/directory errors and decide whether to continue | `FileVisitor.visitFileFailed` |
| Deep copy, delete, or act on traversal events | `Files.walkFileTree()` is usually more suitable |

An important point: `Files.walk(root).filter(...)` only filters **the elements emitted by the stream**. It does not prevent `Files.walk` from descending into filtered-out subdirectories. If you need to prune an entire subtree to save traversal work, use `walkFileTree` and return `FileVisitResult.SKIP_SUBTREE` at the directory to skip.

## 14. Performance and Resource Considerations

### 14.1. Close Streams Promptly

Both `Files.lines` and `Files.walk` must be closed. Always wrap them in `try-with-resources`, even if the pipeline uses `filter`, `map`, `count`, or `forEach`.

### 14.2. Do Not Collect All Data Unnecessarily

For very large files:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.filter(line -> line.contains("WARN"))
            .count();
}
~~~

typically uses far less memory than:

~~~java
List<String> allLines = Files.readAllLines(path);
long count = allLines.stream()
        .filter(line -> line.contains("WARN"))
        .count();
~~~

`readAllLines` is convenient for small files and when repeated access to all lines is needed; it loads every line into a list, making it unsuitable for large files under memory constraints.

### 14.3. Be Careful with parallel()

Streams from `Files.lines` or `Files.walk` can be turned into parallel streams, but do not add `parallel()` merely because you are processing a lot of data. Filesystem reads are often bounded by I/O, the filesystem provider, buffering, and processing order. Parallel downstream stages can also make print/log order non-deterministic or introduce contention on shared accumulators.

Benchmark with realistic workloads. If switching to parallel processing, ensure tasks do not misuse or close a shared outer stream prematurely; each file must have its own open/close scope.

### 14.4. Do Not Rely on Default Traversal Order

`Files.walk` traverses depth-first, but makes no guarantee on filename ordering among siblings. If your algorithm requires deterministic ordering, sort the results or order by a business key. For very large trees, sorting all results can consume substantial memory.

### 14.5. Relative Paths and Working Directory

`Path.of("data")` creates a relative path against the process's current working directory, not necessarily the directory containing the `.java` file. When launched from an IDE, Gradle, a service, or a container, the working directory may differ.

You can print the absolute path for diagnostics:

~~~java
Path root = Path.of("data");
System.out.println(root.toAbsolutePath().normalize());
~~~

`normalize()` eliminates `.` and `..` syntax elements; it does not verify existence or access the filesystem. Only `toRealPath()` accesses the filesystem and can throw `IOException`.

## 15. Complete Program: Searching Keywords Across a Log Tree

Create the file `LogTreeSearch.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class LogTreeSearch {
    public static void main(String[] args) throws IOException {
        Path root = Path.of(args.length > 0 ? args[0] : "logs");
        String keyword = args.length > 1 ? args[1] : "ERROR";
        long totalMatches = 0;

        try (Stream<Path> paths = Files.walk(root, 10)) {
            var iterator = paths.iterator();
            while (iterator.hasNext()) {
                Path path = iterator.next();
                if (!Files.isRegularFile(path)
                        || !path.getFileName().toString().endsWith(".log")) {
                    continue;
                }

                try (Stream<String> lines =
                        Files.lines(path, StandardCharsets.UTF_8)) {
                    long matches = lines
                            .filter(line -> line.contains(keyword))
                            .count();
                    totalMatches += matches;
                    System.out.println(path + ": " + matches);
                } catch (IOException | UncheckedIOException e) {
                    System.err.println("Skipping file " + path
                            + " due to read error: " + e.getMessage());
                }
            }
        } catch (UncheckedIOException e) {
            throw new IOException("Error traversing directory tree",
                    e.getCause());
        }

        System.out.println("Total matching lines: " + totalMatches);
    }
}
~~~

Compile and run:

~~~bash
javac LogTreeSearch.java
java LogTreeSearch ./logs ERROR
~~~

The program:

1. Traverses the `logs` tree up to 10 levels deep from the root directory.
2. Selects only regular files whose names end with `.log`.
3. Reads each file as UTF-8 using `Files.lines`.
4. Counts lines containing the keyword.
5. Closes the file-reading stream after each scan and closes the tree-traversal stream when finished.

The example uses an iterator to process paths sequentially and accumulate the total in a local variable. This also makes clear that only one log file is open at a time. In larger applications, extract per-file processing into a separate helper method for easier testing.

## 16. Common Errors and Resolutions

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| File remains locked or program opens too many files | Stream from `Files.lines` was not closed. | Use `try-with-resources` for every file-reading stream. |
| Accented text displays incorrectly | Decoding charset does not match file encoding. | Identify encoding and pass `StandardCharsets.UTF_8` or the matching charset. |
| Last line appears missing | Code may assume files must end with a line terminator or stream was not consumed. | The last line does not require a line terminator; verify terminal operation and source data. |
| `Files.lines` throws `NoSuchFileException` | Path does not exist or working directory differs from expectation. | Print `toAbsolutePath()`, check the path and permissions. |
| Read error occurs inside `forEach` instead of at `Files.lines` call | I/O error happens during stream consumption, wrapped in `UncheckedIOException`. | Catch `UncheckedIOException` around the pipeline. |
| `Files.walk` returns both directories and files | Stream includes the root path and subdirectories. | Filter with `Files.isRegularFile`. |
| Symlink does not traverse into target directory | `Files.walk` does not follow symbolic links by default. | Pass `FOLLOW_LINKS` only if genuinely required. |
| Infinite loop traversal or `FileSystemLoopException` | Following symlinks hit a cycle. | Keep default no-follow behavior or handle cycle errors. |
| `maxDepth = 1` misses files in subdirectories | Root depth is 0; immediate entries are depth 1. | Increase `maxDepth` to cover required levels. |
| `filter` excludes a directory yet its descendants still appear | `filter` only filters results, not traversal descent. | Use `walkFileTree` if you need `SKIP_SUBTREE`. |
| Traversal output is not ordered by name | Filesystem provider does not guarantee sibling order. | Sort when deterministic order is required. |
| `readAllLines` consumes too much memory | All lines are loaded into a list. | Use `Files.lines` for sequential streaming processing. |

## 17. Practice Exercises

### Exercise 1 — Counting Non-Blank Lines

Write a method accepting a `Path` and returning the count of non-blank lines using `Files.lines`. Ensure the stream is always closed and the method handles `IOException`.

Hint:

~~~java
static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

### Exercise 2 — Finding All .java Files

Write a program accepting a root directory and using `Files.walk` to list `.java` files. Include only regular files and do not follow symbolic links.

### Exercise 3 — Limiting Depth

Given the tree:

~~~text
root/
├── a.txt
├── one/
│   ├── b.txt
│   └── two/
│       └── c.txt
└── d/
    └── e.txt
~~~

Determine which paths are emitted into the stream when calling `Files.walk(root, 1)`, `Files.walk(root, 2)`, and `Files.walk(root, 3)`. Remember that `root` is at depth 0.

### Exercise 4 — Searching a Keyword Across All Logs

Combine `Files.walk` and `Files.lines` to find lines containing `WARN` in all `.log` files. Print each filename along with its matching line count. Ensure both the traversal stream and each file stream are closed.

### Exercise 5 — When Is walkFileTree Needed?

Suppose an `archive/` directory contains millions of files and you want to skip that entire subtree. Explain why `Files.walk(root).filter(...)` does not stop traversal from descending into `archive/`, and describe how to use `FileVisitor` with `SKIP_SUBTREE`.

### Exercise 6 — Verifying Encoding

Create a UTF-8 file containing accented text, read it with `Files.lines(path, StandardCharsets.UTF_8)`, then try reading it with a different charset. Observe the output and explain why encoding selection must follow the data contract rather than whether a string "looks readable."

## 18. Key Takeaways for Files.lines and Files.walk

- `Files.lines(path)` reads lines as a `Stream<String>`; charset overloads allow specifying the encoding explicitly.
- `Files.lines` operates lazily; use `count`, `forEach`, `collect`, or another terminal operation to consume the stream.
- Returned lines exclude line terminators; empty files yield an empty stream and the final line does not require a trailing newline.
- Always close the stream from `Files.lines` using `try-with-resources`; open errors throw `IOException`, while read errors during consumption may be wrapped in `UncheckedIOException`.
- `Files.walk(root)` emits both `root` and descendant paths in depth-first order; sibling order is not guaranteed.
- `maxDepth` counts `root` as level 0; `filter` filters stream elements but does not stop traversal into excluded directories.
- `Files.walk` does not follow symbolic links by default; use `FOLLOW_LINKS` only intentionally and handle loops.
- `Files.walk` also returns a resource-backed stream, so close it with `try-with-resources`.
- Use `Files.walkFileTree` when you need to prune subtrees or handle individual traversal events and errors.
- Use `Files.lines` for sequential processing without loading the entire file; use `readAllLines` only when the file is small enough and all lines are needed in memory.

### References

- [Java SE 17 API — Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)) — line reading and default UTF-8 charset.
- [Java SE 17 API — Files.walk](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walk(java.nio.file.Path,java.nio.file.FileVisitOption...)) — directory tree traversal using streams.
- [Java SE 17 API — Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)) — traversal with `FileVisitor` and subtree control.
- [Java SE 17 API — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html) — options for following symbolic links.
- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html) — lazy operations and managing resource-backed streams.
