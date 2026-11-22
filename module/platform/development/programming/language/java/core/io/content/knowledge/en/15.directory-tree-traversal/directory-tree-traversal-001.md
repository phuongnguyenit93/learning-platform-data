# DirectoryStream and Closing Directory Handles in Java NIO.2

## 1. Why Do We Need DirectoryStream?

A directory on a filesystem may contain a few files, thousands of entries, or a set of items that changes continuously while the program is running. When you need to **iterate over the direct entries inside a directory**, Java NIO.2 provides `java.nio.file.DirectoryStream<Path>` and the most common factory method:

~~~java
DirectoryStream<Path> stream = Files.newDirectoryStream(directory);
~~~

`DirectoryStream` is an **`Iterable` of `Path` objects** representing the entries discovered in the directory. Unlike simply holding a list of names in RAM, it can be implemented on top of an operating system directory-iteration resource and therefore **must be closed**.

The most important takeaway of this lesson: **`DirectoryStream` is a resource with a lifecycle, not just a collection you can leave to GC**. Open it in a `try-with-resources` block, iterate while it is open, and close it immediately when finished or when an exception occurs.

~~~text
           Directory Path
                │
                ▼
    Files.newDirectoryStream(dir)
                │
                ▼
    DirectoryStream<Path> (OPEN)
       │         │        │
       ▼         ▼        ▼
   file.txt    logs/    image.png
       │         │        │
       └──── iterate ─────┘
                │
                ▼
       close() via try-with-resources
                │
                ▼
       Directory handle is released
~~~

This lesson helps you:

- Open a `DirectoryStream` to list **direct** child entries.
- Understand the difference between a `Path` representing a directory, a `DirectoryStream` holding a real handle, and Java Streams' `Stream<Path>`.
- Iterate properly with a `for-each` loop, avoiding reusing an iterator multiple times or assuming an ordering.
- Filter by **glob** and `DirectoryStream.Filter<Path>`.
- Handle errors when **opening**, **iterating**, **filtering**, and **closing** a directory.
- Traverse nested directories without leaking handles.
- Choose among `DirectoryStream`, `Files.list`, `Files.walk`, and `Files.walkFileTree` depending on the situation.
- Recognize risks related to symbolic links, concurrent modifications, untrusted paths, and resource lifecycles.

## 2. Core APIs and Data Types

| Component | Role | Key Points to Remember |
| --- | --- | --- |
| `Path` | Describes a path | Creating a `Path` does not open the directory |
| `Files.newDirectoryStream(dir)` | Opens a source to iterate direct entries of a directory | May throw `IOException` immediately upon opening |
| `DirectoryStream<Path>` | Both `Iterable<Path>` and `Closeable` | Must be closed when done |
| `DirectoryStream.Filter<Path>` | Condition to accept/reject an entry | May throw `IOException` |
| `Files.newDirectoryStream(dir, "*.txt")` | Retrieves only entries whose names match the glob | Glob syntax differs from regex syntax |
| `DirectoryIteratorException` | Reports an I/O error occurring **during iteration** | Unchecked; retrieve the underlying cause via `getCause()` |
| `Files.isDirectory(path)` | Checks whether the path represents a directory | Behavior with symbolic links depends on `LinkOption` |
| `Files.list(dir)` | Returns a `Stream<Path>` of direct entries | This `Stream` also needs to be closed |
| `Files.walk(root)` | Creates a `Stream<Path>` for deeper traversal | Needs to be closed; avoid unbounded usage |
| `Files.walkFileTree(...)` | Traverses a tree with controlled callbacks | Useful for recursion, error handling, and access permissions |

**`DirectoryStream` is not a `java.util.stream.Stream`.** It implements `Iterable` and `Closeable`, so it is convenient to use with a `for (Path entry : stream)` loop, but it does not directly have the `map/filter/collect` operations of Java Streams. If you want the Stream API, `Files.list` is a separate option and also carries the responsibility of closing the resource.

## 3. Open, Iterate, Close: The Standard Pattern

A properly structured block:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(directory)) {
    for (Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

This is an illustrative snippet, not a standalone program; `directory` is a valid `Path`, and the enclosing method declares or catches `IOException`. Required imports:

~~~java
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
~~~

How the statement executes:

1. `Files.newDirectoryStream(directory)` asks the provider to open directory iteration.
2. If opening succeeds, `entries` represents a usable stream.
3. `for-each` retrieves each child `Path` one by one and processes it.
4. Upon exiting the `try` block, Java automatically calls `entries.close()`, even if an exception is thrown inside the block body.
5. Once the resource is closed, do not continue using the old `DirectoryStream` for further iteration.

Creating `Path.of("folder")` only creates an abstract path. **There is no directory handle to close at the `Path` creation step**. A handle may be acquired when calling `Files.newDirectoryStream`, `Files.list`, opening another `DirectoryStream`, or using I/O APIs that actually access the filesystem.

### 3.1. What Is the Bug of Failing to Close a Stream?

If you open many `DirectoryStream` instances and forget to `close()`, the process can hold directory handles/file descriptors longer than necessary. The consequences depend on the OS and provider:

- Increasing the number of open handles until reaching the limit where no more can be opened.
- Making it difficult to delete, rename, or replace certain directories on operating systems with locking mechanisms.
- Causing unnecessary resource consumption, especially when a server handles many requests.
- Leaving resources behind when an exception occurs mid-iteration if closing is only done on the success path.

The garbage collector **is not a reliable lifecycle strategy** for this kind of resource. `try-with-resources` expresses the release timing clearly and safely.

## 4. Complete Java 17 Example: Iterating Over a Temporary Directory

To ensure the example runs on any machine without depending on user files, the program creates its own temporary directory, three entries, and deletes them after the experiment. Because iteration order **is not guaranteed**, the program collects the **names** and sorts them before printing.

Save as **DirectoryStreamBasicsDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class DirectoryStreamBasicsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("dir-stream-basics-");
        Path alpha = dir.resolve("alpha.txt");
        Path beta = dir.resolve("beta.log");
        Path subdir = dir.resolve("subdir");

        try {
            Files.writeString(alpha, "A", StandardCharsets.UTF_8);
            Files.writeString(beta, "B", StandardCharsets.UTF_8);
            Files.createDirectory(subdir);

            List<String> names = new ArrayList<>();

            try (DirectoryStream<Path> entries =
                         Files.newDirectoryStream(dir)) {
                for (Path entry : entries) {
                    names.add(entry.getFileName().toString());
                }
            }

            Collections.sort(names);
            System.out.println(names);
        } finally {
            Files.deleteIfExists(alpha);
            Files.deleteIfExists(beta);
            Files.deleteIfExists(subdir);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 DirectoryStreamBasicsDemo.java
java DirectoryStreamBasicsDemo
~~~

Output when the filesystem allows creating/iterating/deleting the temporary directory:

~~~text
[alpha.txt, beta.log, subdir]
~~~

**Explanation:**

- `Files.createTempDirectory` creates a real directory with a random name; the program does not print that name so stdout stays deterministic.
- `Files.writeString` and `Files.createDirectory` create entries with deterministic names.
- `Files.newDirectoryStream(dir)` iterates over the **three direct entries** of the directory; it does not descend into `subdir`.
- `entry.getFileName()` retrieves the final component of the path to print the name.
- `Collections.sort(names)` makes the printed order predictable. `DirectoryStream` itself **does not promise alphabetical order**, creation order, or physical storage order.
- `try-with-resources` closes the `DirectoryStream` before `finally` deletes the directory and files. This is an important detail on platforms with strict handle management.

In a real application, cleanup errors can also throw `IOException` and should be reported properly; this is a short demo for learning purposes.

## 5. DirectoryStream Iterates Direct Children Only, Without Automatic Recursion

Example structure:

~~~text
project/
├─ pom.xml
├─ README.md
└─ src/
   ├─ Main.java
   └─ test/
      └─ ExampleTest.java
~~~

`Files.newDirectoryStream(project)` normally returns only the entries `pom.xml`, `README.md`, and `src`. It **does not automatically descend into `src/Main.java`** or `src/test/ExampleTest.java`.

If you need to traverse deeper levels, you must open additional streams for subdirectories, or use an API designed for tree traversal such as `Files.walkFileTree`. Using nested `DirectoryStream` instances requires paying attention to the fact that **each stream has its own handle**.

### 5.1. Checking File/Directory Type During Iteration

You can inspect the entry type:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        if (Files.isDirectory(entry)) {
            // Directory according to the current check rules.
        } else if (Files.isRegularFile(entry)) {
            // Regular file.
        } else {
            // May be a symbolic link, special entry, or unknown.
        }
    }
}
~~~

This is an illustrative snippet assuming an existing `Path dir`. By default, `Files.isDirectory` and `Files.isRegularFile` may **follow symbolic links**. If you need to classify the symbolic link itself or avoid following it during recursion, consider `LinkOption.NOFOLLOW_LINKS`. In addition, `false` does not always mean “definitely not of this type”: it may simply be unqueryable due to filesystem conditions.

`DirectoryStream` returns `Path` objects; there is no guarantee an entry still exists or remains the same type when you actually open it afterward. This is a property of filesystems that can change concurrently.

## 6. DirectoryStream Is a Resource: When `close()` Runs Matters

`DirectoryStream<Path>` extends `Closeable`, so it has `close()`. After closing, you should not continue calling `iterator()` or iterating over it. `close()` releases the provider's directory-iteration resource; the `Path` objects already obtained remain **path-representation objects**, which does not mean they become invalid as types.

A proper structure:

~~~java
List<Path> paths = new ArrayList<>();

try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        paths.add(entry);
    }
}

// At this point, the DirectoryStream is closed.
// The paths can still be used, but the files may have changed.
for (Path path : paths) {
    System.out.println(path.getFileName());
}
~~~

Illustrative snippet, requiring `List`/`ArrayList` and NIO imports; not a standalone program. It **accumulates all `Path` objects into RAM**, which is suitable for small directories when results must be used after closing. If the directory is very large, process each entry right inside the `try` block instead of collecting all of them.

### 6.1. Do Not Return an Iterator Dependent on a Closed Stream

Anti-pattern:

~~~java
static Iterator<Path> badIterator(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        return entries.iterator(); // Wrong: stream closes on return.
    }
}
~~~

This is an illustrative method snippet (requires importing `java.util.Iterator`). The iterator still references a source that the method has already closed; the caller cannot rely on it for further iteration.

Better designs are usually:

- **Finish processing within the `try` scope** and return a small business result (count, summary, etc.).
- **Return a copied list of Paths** if the number of entries is small and iteration has already completed.
- **Let the caller own the DirectoryStream** if the public API contract requires the caller to close and manage the lifecycle.
- If you want a lazy Stream API, consider `Files.list`, while still specifying who closes the Stream.

You should not return a `Stream<Path>` from `Files.list` while forgetting to make the caller's closing responsibility explicit.

### 6.2. Transfer Ownership Explicitly

If a method opens the stream itself, it usually must close it:

~~~java
static long countEntries(Path dir) throws IOException {
    long count = 0;
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        for (Path ignored : entries) {
            count++;
        }
    }
    return count;
}
~~~

This is an illustrative method snippet requiring imports for `IOException`, `DirectoryStream`, `Files`, and `Path`. It returns the number of entries successfully iterated; if iteration fails, it does not return a partial count as a complete result.

If a method **receives** a `DirectoryStream` opened by the caller, do not close it unless the contract explicitly transfers ownership. The resource may still need to be used at the call site.

## 7. DirectoryStream's Iterator: Single-Use Iterator and No Guaranteed Order

`DirectoryStream` is `Iterable<Path>`, but unlike many ordinary collections, its contract **supports creating at most one `Iterator`** per stream. Requesting an iterator a second time may throw `IllegalStateException`.

Therefore, do not use patterns that rely on multiple passes:

~~~java
try (DirectoryStream<Path> entries = Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        // First traversal pass.
    }
    for (Path entry : entries) {
        // Wrong: requesting a second iterator on the same DirectoryStream.
    }
}
~~~

This is an example of **incorrect usage**, not a program to run as a working demo.

If you must iterate again:

- Open **a new DirectoryStream** with `Files.newDirectoryStream(dir)`.
- Or collect the needed entries into a list during the first pass, accepting the RAM usage.
- If the directory can change, understand that opening a new stream may yield a different set of entries.

The order in which entries are returned is not guaranteed. Do not assume filenames will be returned alphabetically, by creation time, by modification time, or in command-line listing order. If ordering is needed for display or computation, sort intentionally and keep memory cost in mind.

### 7.1. Iteration Can Be Lazy and Weakly Consistent

The filesystem may be modified by another process **while** you are iterating: adding files, deleting files, or renaming subdirectories. This kind of iterator does not provide a transactional snapshot. It may or may not reflect certain changes, depending on the provider and timing.

Do not infer from having seen `entry` that:

- The entry will definitely still exist when calling `Files.readString(entry)`.
- The entry is still a regular file after `Files.isRegularFile(entry)`.
- The set of entries received is a consistent snapshot of the entire directory.
- The loop has locked the directory against other changes.

In systems that require preserving consistency, you need to design snapshots/transactions/locks/checks appropriate for the environment; `DirectoryStream` alone does not provide those guarantees.

## 8. Filtering by Glob with `Files.newDirectoryStream(Path, String)`

To iterate only over entries whose **names match a glob**, use the overload:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir, "*.txt")) {
    for (Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

This is an illustrative snippet. The pattern `"*.txt"` is applied according to the **filename glob** rules of `Files.newDirectoryStream(dir, glob)`, not arbitrary Java regex syntax.

Key points to know:

- Glob `*` generally matches a sequence of characters in a name.
- Glob `?` matches a single character in a name according to glob rules.
- `"*.txt"` targets entries whose names end with `.txt` in the directory being iterated.
- Case sensitivity may depend on the provider/filesystem; do not rely on identical behavior across all platforms.
- This API checks **direct entries only**; it does not automatically search for all `.txt` files in the subtree.
- It filters by **entry name**, not implicitly guaranteeing a regular file: a **directory** named `notes.txt` can also match by name.

### 8.1. Glob Is Not a Regular Expression

Another example:

~~~java
Files.newDirectoryStream(dir, "*.{txt,md}");
~~~

This is an illustrative snippet; the glob selects names ending in `.txt` **or** `.md` using Java's glob alternation syntax. Do not interpret it as Java regex `".*\\.(txt|md)"`: the two pattern languages have different rules.

If you only need a specific file extension, `"*.txt"` is easier to read than a complex regex. If you need to check size, entry type, or metadata, use the `Filter<Path>` overload in the next section.

### 8.2. Java 17 Example: Filtering `.txt` and Producing Deterministic Output

Save as **DirectoryStreamGlobDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class DirectoryStreamGlobDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("glob-demo-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");
        Path log = dir.resolve("notes.log");
        Path child = dir.resolve("child");

        try {
            Files.writeString(a, "A", StandardCharsets.UTF_8);
            Files.writeString(b, "B", StandardCharsets.UTF_8);
            Files.writeString(log, "log", StandardCharsets.UTF_8);
            Files.createDirectory(child);
            Files.writeString(child.resolve("nested.txt"),
                    "nested", StandardCharsets.UTF_8);

            List<String> names = new ArrayList<>();
            try (DirectoryStream<Path> entries =
                         Files.newDirectoryStream(dir, "*.txt")) {
                for (Path entry : entries) {
                    names.add(entry.getFileName().toString());
                }
            }

            Collections.sort(names);
            System.out.println(names);
        } finally {
            Files.deleteIfExists(child.resolve("nested.txt"));
            Files.deleteIfExists(child);
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(log);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamGlobDemo.java
java DirectoryStreamGlobDemo
~~~

Output:

~~~text
[a.txt, b.txt]
~~~

`nested.txt` does not appear even though its name matches the pattern: it is an entry **inside `child`**, not a direct entry of `dir`. This is the core difference between listing a single directory and traversing an entire tree.

## 9. Filtering with `DirectoryStream.Filter<Path>`

When you need conditions beyond a filename glob, use the overload:

~~~java
DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir, entry -> condition(entry));
~~~

This is a **syntax illustration**, with `condition(Path)` being a hypothetical application method. `DirectoryStream.Filter<Path>` is a functional interface with an `accept(Path entry)` method returning `boolean` that may declare `throws IOException`.

Example selecting **regular files** whose names start with `report-` and end with `.txt`:

~~~java
try (DirectoryStream<Path> entries = Files.newDirectoryStream(
        dir,
        entry -> Files.isRegularFile(entry)
                && entry.getFileName().toString().startsWith("report-")
                && entry.getFileName().toString().endsWith(".txt"))) {

    for (Path entry : entries) {
        // Process the selected files.
    }
}
~~~

This snippet illustrates usage with an existing `Path dir`. `Files.isRegularFile` may access filesystem metadata and follows symbolic links when `LinkOption.NOFOLLOW_LINKS` is not passed; if it cannot query the metadata, it may return false. If your logic needs to distinguish metadata errors from “not a regular file”, use an API like `Files.readAttributes` and handle `IOException` instead of treating every false return as a normal case.

### 9.1. The Filter Is Called During Iteration

A filter condition should not have dangerous side effects (deleting/renaming entries, recording non-idempotent transactions, modifying the entire directory), because when and how filtering executes is tied to retrieving elements from the source. Design filters to favor concise, pure entry-acceptance checks.

If a filter must access file attributes, it can be slow and error-prone; iterating over large directories must account for the cost of **each check**.

### 9.2. `IOException` Inside a Filter

`Filter.accept(Path)` may throw `IOException`. According to the `DirectoryStream` contract, I/O errors while retrieving entries—including errors from the filter—may surface as **`DirectoryIteratorException`** during iteration. This type is unchecked, but `getCause()` holds the original `IOException`.

Do not write `catch(IOException)` around the entire loop and assume it will catch every error originating from the iterator. You should understand the two error paths:

- Errors when **opening/closing the stream** normally surface as `IOException`.
- Errors **when the iterator fetches the next entry** are normally wrapped in `DirectoryIteratorException`.

Illustrative handling snippet:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir, filter)) {
    for (Path entry : entries) {
        process(entry);
    }
} catch (DirectoryIteratorException e) {
    IOException cause = e.getCause();
    // Report iteration or filtering error, preserving cause.
} catch (IOException e) {
    // Report error opening or closing the stream.
}
~~~

This is an illustrative snippet, **not a standalone program**; `dir`, `filter`, and `process` are provided by the application. According to the API, `DirectoryIteratorException.getCause()` returns `IOException`. Avoid saving only `getMessage()` while discarding the stack trace and cause.

## 10. Java 17 Example: Filtering with a Lambda and Entry Name

The example below checks for regular files starting with `report-` and ending with `.txt`; the listed order is sorted before printing.

Save as **DirectoryStreamFilterDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class DirectoryStreamFilterDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("filter-demo-");
        Path first = dir.resolve("report-1.txt");
        Path second = dir.resolve("report-2.log");
        Path other = dir.resolve("other.txt");
        Path namedDir = dir.resolve("report-dir.txt");

        try {
            Files.writeString(first, "ok", StandardCharsets.UTF_8);
            Files.writeString(second, "log", StandardCharsets.UTF_8);
            Files.writeString(other, "other", StandardCharsets.UTF_8);
            Files.createDirectory(namedDir);

            List<String> names = new ArrayList<>();

            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(dir, entry ->
                                 Files.isRegularFile(entry)
                                 && entry.getFileName().toString()
                                         .startsWith("report-")
                                 && entry.getFileName().toString()
                                         .endsWith(".txt"))) {
                for (Path entry : stream) {
                    names.add(entry.getFileName().toString());
                }
            }

            Collections.sort(names);
            System.out.println(names);
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(other);
            Files.deleteIfExists(namedDir);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamFilterDemo.java
java DirectoryStreamFilterDemo
~~~

Output:

~~~text
[report-1.txt]
~~~

The other two files are excluded because their names do not satisfy all conditions. The directory `report-dir.txt` has a matching name, but fails `Files.isRegularFile`. Note: if a symbolic link points to a regular file, `Files.isRegularFile` with default options may treat it as a regular file; define a link policy if you do not want that behavior.

## 11. Errors in Three Phases: Open, Iterate, and Close

Do not treat “listing a directory” as a single step. It has at least three phases that can fail:

| Phase | Typical API | Error Types to Consider |
| --- | --- | --- |
| Open | `Files.newDirectoryStream(dir)` | `NotDirectoryException`, `NoSuchFileException`, `AccessDeniedException`, or other `IOException` |
| Iterate / Apply Filter | `iterator().hasNext()` / `next()` via for-each | `DirectoryIteratorException` wrapping an I/O cause |
| Close | `DirectoryStream.close()` | `IOException` from releasing resources |

For example, a path may exist yet be a **regular file**, not a directory. Calling `Files.newDirectoryStream` may throw `NotDirectoryException` or `IOException` depending on the provider. A directory may also be deleted or lose permissions mid-iteration, causing the iterator to fail after returning several entries.

**Do not treat a mid-loop error as “iteration finished.”** The result at that point may only be a subset, not a complete list.

### 11.1. Iterator EOF Differs from an Error

A `for (Path entry : stream)` loop ends normally when no entries remain; no exception is thrown. `DirectoryIteratorException` means an error occurred while discovering entries, not normal end-of-directory termination.

For business logic that requires counting every entry, when the iterator throws an exception you must mark it as a **failure**, not return the count collected so far as a complete result.

### 11.2. `IOException` During `close()` Still Matters

Even after iterating through all entries, `close()` can still report an `IOException`. `try-with-resources` lets this exception propagate properly. If the `try` body already threw an exception and closing also fails, the close error is attached as a **suppressed exception** on the primary error, preserving full diagnostics.

If your logic catches `DirectoryIteratorException`, preserve both `getCause()` and any relevant suppressed exceptions instead of printing only a simple message string.

## 12. Example Testing Iterator Errors with a Filter Intentionally Throwing `IOException`

To verify the error path without relying on unpredictable OS permissions, we intentionally create a filter that throws `IOException` for an entry in a test directory. The program does not depend on iteration order because the directory has only one entry.

Save as **DirectoryStreamErrorDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryStreamErrorDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("iterator-error-");
        Path file = dir.resolve("one.txt");

        try {
            Files.writeString(file, "x", StandardCharsets.UTF_8);

            try (DirectoryStream<Path> entries =
                    Files.newDirectoryStream(dir, entry -> {
                        throw new IOException("Filter failed");
                    })) {
                for (Path ignored : entries) {
                    System.out.println("Unexpected entry");
                }
            } catch (DirectoryIteratorException e) {
                System.out.println("Cause: " + e.getCause().getMessage());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamErrorDemo.java
java DirectoryStreamErrorDemo
~~~

Output with the default filesystem provider following the filter error-wrapping contract:

~~~text
Cause: Filter failed
~~~

The goal of this example is not to “cause a real disk error,” but to practice **the difference between `IOException` and `DirectoryIteratorException`**. `Filter.accept` throws `IOException`, and the iterator wraps the error so the caller sees it through `DirectoryIteratorException.getCause()`.

`Files.newDirectoryStream` still needs to be closed even if the loop processed zero entries. `try-with-resources` ensures that happens.

## 13. Handle-Safe Recursion: Do Not Open Unbounded Nested Streams

To traverse multiple levels using `DirectoryStream`, an intuitive approach is recursion:

~~~java
static void visit(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        for (Path entry : entries) {
            if (Files.isDirectory(entry)) {
                visit(entry);
            } else {
                // Process the file.
            }
        }
    }
}
~~~

This is an **illustrative method snippet**, not a standalone program. It has notable limitations:

- Each call to `visit` keeps the parent directory's stream **open** while opening the child directory's stream. On a very deep directory tree, many simultaneous handles may remain open.
- Deep recursion also risks high stack usage and even `StackOverflowError`.
- `Files.isDirectory(entry)` follows symbolic links by default, leading to loops if links form a cycle.
- Every stream must be closed, even when recursion or entry processing fails.
- Classifying entries via `Files.isDirectory` can still suffer from TOCTOU: state may change right after the check.

For tasks requiring deep tree traversal and control over symlinks, errors, and permissions, consider `Files.walkFileTree` with `FileVisitor` instead of simple manual recursion.

### 13.1. Two-Level Traversal Using Two `try-with-resources` Scopes

If you only need to descend into a few subdirectories, you can write nested `try` blocks:

~~~java
try (DirectoryStream<Path> top =
        Files.newDirectoryStream(root)) {
    for (Path entry : top) {
        if (Files.isDirectory(entry)) {
            try (DirectoryStream<Path> children =
                    Files.newDirectoryStream(entry)) {
                for (Path child : children) {
                    // Process child.
                }
            }
        }
    }
}
~~~

Illustrative snippet with `Path root`. When exiting the inner loop, the child stream is closed while the parent stream stays open to iterate through the rest. When exiting the outer block, the parent stream is closed. This controls resources better than collecting `DirectoryStream` objects into a list and closing them all after many steps.

If you want to avoid opening a child stream when a link points to a directory, use `Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS)`. This is only an identification step; you still need to handle access errors or vanished entries at the actual point of opening.

## 14. Symbolic Links, Concurrent Changes, and `SecureDirectoryStream`

### 14.1. Symbolic Links Can Cause Traversal to Go Farther Than Intended

Suppose:

~~~text
root/
  docs/
  jump -> /outside/
~~~

When using `Files.isDirectory(jump)` with default options, a symbolic link pointing to another directory can be recognized as a directory. If you recurse into it, the program may leave the `root` tree or enter a cycle.

To avoid unintentionally following links:

~~~java
boolean physicalDirectory =
        Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS);
~~~

This is an illustrative snippet; requires importing `java.nio.file.LinkOption`. It distinguishes checking the entry itself from following the link target. However, checking and then opening still has a **race condition** if the entry is replaced between the two operations.

Do not use `normalize()` alone as a security measure against path traversal. `normalize()` only simplifies path syntax; it does not resolve symbolic links or lock paths.

### 14.2. What Is `SecureDirectoryStream`?

Some providers may supply `SecureDirectoryStream<Path>`, a subtype that allows performing operations relative to the open directory in a way that can reduce path race risks. Not all providers support it.

Check pattern:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    if (entries instanceof SecureDirectoryStream<Path> secure) {
        // Can use APIs relative to the open directory.
    } else {
        // The provider does not support this feature.
    }
}
~~~

This is an illustrative snippet; requires importing `java.nio.file.SecureDirectoryStream`. Do not assume this capability is always available on every filesystem. If software processes paths supplied by untrusted users, evaluate permissions and race risks at the architectural level rather than relying solely on an `isDirectory` check.

### 14.3. A Directory Changing During Iteration

`DirectoryStream` normally iterates over the provider's live state and does not freeze a transactional snapshot. If another process adds/deletes/renames entries:

- Some new entries may not appear, even though they exist when the loop finishes.
- An entry already returned may disappear before you access its contents.
- Checking metadata and opening the file immediately afterward may yield different results.

If an auditable listing is required, you need controlled input processes, capture timing, immutability, or business-level snapshot storage. `DirectoryStream` by itself is only an entry-listing mechanism, not a transaction.

## 15. Comparing `DirectoryStream`, `Files.list`, `Files.walk`, and `walkFileTree`

| Purpose | Suitable API | Resource Management |
| --- | --- | --- |
| Iterate direct entries with a `for-each` loop | `Files.newDirectoryStream(dir)` | Close `DirectoryStream` |
| Iterate direct entries, filter by glob name | `Files.newDirectoryStream(dir, "*.txt")` | Close `DirectoryStream` |
| Iterate direct entries, filter by metadata/custom logic | `Files.newDirectoryStream(dir, filter)` | Close `DirectoryStream` |
| Want Java Stream `filter/map/collect` on direct children | `Files.list(dir)` | Close `Stream<Path>` |
| Traverse multiple depth levels via `Stream<Path>` | `Files.walk(root, maxDepth)` | Close `Stream<Path>` |
| Traverse a tree needing `visitFileFailed` callbacks and continue/skip control | `Files.walkFileTree` | API manages traversal internally |

### 15.1. `Files.list` Also Opens a Resource That Must Be Closed

~~~java
try (java.util.stream.Stream<Path> paths =
        Files.list(dir)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

This is an illustrative snippet with an existing `Path dir`. `Files.list` returns a lazy `Stream<Path>` backed by a directory-iteration resource; do **not** create a stream, grab its iterator, and forget to close it.

A general `java.util.stream.Stream` is not always tied to an OS resource, but `Files.list` and `Files.walk` are examples that **require closing** by contract.

### 15.2. `Files.walk` Goes Deeper, but Must Be Bounded

~~~java
try (java.util.stream.Stream<Path> paths =
        Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
~~~

Illustrative snippet with `Path root`. `maxDepth=2` limits how many levels down to descend as defined by the API; the root element is at depth 0. If you want per-file error handling and granular skip/continue policies, `walkFileTree` can be clearer.

### 15.3. `Files.walkFileTree` Enables Callback-Based Error Handling

`Files.walkFileTree` invokes `FileVisitor` methods to traverse and report errors. It is useful when traversing an entire tree, counting or processing files, allowing subtree skipping and `visitFileFailed` handling. Avoid using it just to list 2–3 direct entries when `DirectoryStream` is enough.

Mental model:

~~~text
DirectoryStream:   open 1 directory → iterate direct children → close
Files.list:        open 1 directory → Stream operations → close
Files.walk:        deep traversal with Stream<Path> → close
walkFileTree:      deep traversal via FileVisitor callbacks
~~~

## 16. Java 17 Example: Counting Direct Entries and Comparing with `Files.list`

Save as **DirectoryStreamCountDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class DirectoryStreamCountDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("count-demo-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");
        Path child = dir.resolve("child");

        try {
            Files.createFile(a);
            Files.createFile(b);
            Files.createDirectory(child);
            Files.createFile(child.resolve("nested.txt"));

            long viaDirectoryStream = 0;
            try (DirectoryStream<Path> entries =
                         Files.newDirectoryStream(dir)) {
                for (Path ignored : entries) {
                    viaDirectoryStream++;
                }
            }

            long viaFilesList;
            try (Stream<Path> entries = Files.list(dir)) {
                viaFilesList = entries.count();
            }

            System.out.println("DirectoryStream: "
                    + viaDirectoryStream);
            System.out.println("Files.list: " + viaFilesList);
        } finally {
            Files.deleteIfExists(child.resolve("nested.txt"));
            Files.deleteIfExists(child);
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamCountDemo.java
java DirectoryStreamCountDemo
~~~

Output:

~~~text
DirectoryStream: 3
Files.list: 3
~~~

Both APIs list only the **direct children** of `dir`. The entry `child` is counted once, while `child/nested.txt` is not in the direct-children set. The example intentionally creates a nested file to make this clear. Both streams are closed before the program deletes the directories.

Do not infer that the counts will always match if the directory is changing concurrently: this example uses a dataset controlled by the program.

## 17. Exception Handling: Do Not Turn an Iteration Error into a Valid List

A common design mistake:

~~~java
List<Path> result = new ArrayList<>();
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        result.add(entry);
    }
} catch (Exception e) {
    // Ignore all errors.
}
return result;
~~~

This is an **anti-pattern** shown as a method body, not a standalone program. If an error happens mid-loop, the caller receives a list **containing only some entries** without knowing it is incomplete.

More appropriate approaches:

1. Let `IOException` and `DirectoryIteratorException` propagate to where business decisions can be made.
2. If collecting multiple independent directories, record success/failure status **per directory**.
3. Only return a “complete” result when both iteration and closing finish successfully.
4. When partial results must be provided, use a result type with explicit status (`partial`, processed count, root error, etc.).
5. Preserve `cause`, `suppressed exceptions`, and safe path context when logging.

### 17.1. Catch `IOException` and `DirectoryIteratorException` at the Right Layer

A method can be written as:

~~~java
static void printDirectory(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        for (Path entry : entries) {
            System.out.println(entry.getFileName());
        }
    } catch (DirectoryIteratorException e) {
        throw new IOException("Failed while iterating: " + dir,
                e.getCause());
    }
}
~~~

This is an illustrative method snippet; requires importing `DirectoryIteratorException`, `DirectoryStream`, `Files`, `Path`, and `IOException`. Open/close errors are already `IOException` and propagate naturally; iterator errors are wrapped into `IOException` with a contextual message and the original `cause`.

This wrapping is appropriate if an outer API layer only wants to expose checked `IOException`. If the outer layer needs to distinguish specific error types, you can keep `DirectoryIteratorException` or use a domain error type with a status code. Avoid wrapping all errors into the same meaningless message.

### 17.2. `try-with-resources` When an Error Occurs Simultaneously with `close()`

If the `try` body throws an exception and `DirectoryStream.close()` also throws an exception, Java attaches the close error as a **suppressed** exception on the primary error. When diagnosing issues, inspect `Throwable.getSuppressed()`. Careless manual closing in `finally` can mask the original error.

Only call `close()` when you truly own the stream; do not close a stream supplied by the caller unless the contract grants ownership.

## 18. Permissions, Paths, and Data Correctness

### 18.1. `DirectoryStream` Does Not Guarantee Read Access to Every Entry's Contents

Having permission to list a directory does not mean having permission to read every file inside it, open subdirectories, modify/delete entries, or read metadata for every entry. Actual permissions depend on the filesystem and access control mechanisms.

After iterating and receiving a `Path entry`, an operation like:

~~~java
String text = Files.readString(entry);
~~~

can still fail because `entry` has disappeared, is a directory, is not text, or is not permitted to be read. This is an illustrative snippet, not a complete loop.

### 18.2. Do Not Blindly Trust Filenames from Untrusted Sources

When turning an entry name into a URL, shell command, query, or target filename, apply separate policies for escaping, subpaths, symbolic links, and permissions. `DirectoryStream` only gives you a `Path`; it does not replace input validation.

For example, when iterating over a user upload directory, do not take `entry.getFileName().toString()` and concatenate it directly into a shell command string. Use appropriate APIs to prevent command injection and handle special characters.

### 18.3. Check-Then-Act Can Have Race Conditions

The snippet:

~~~java
if (Files.isRegularFile(entry)) {
    byte[] bytes = Files.readAllBytes(entry);
}
~~~

illustrates checking before reading. Between `isRegularFile` and `readAllBytes`, the entry may be changed. Therefore, the application must still handle `IOException` on the read operation and not treat the prior check as absolute proof.

## 19. Performance and Memory

Some considerations when iterating over large directories:

- `DirectoryStream` lets you iterate over `Path` objects incrementally; it does not force the application to create a `List<Path>` holding every entry up front.
- If you only need to count or process each entry independently, use a `for-each` loop inside `try-with-resources` and avoid unbounded accumulation.
- If you need to sort names for display, you **must pay the memory/CPU cost** of collecting and sorting (or apply an external sorting mechanism).
- A filter that checks metadata repeatedly can trigger many I/O operations; optimize according to needs and measure.
- If a directory contains millions of entries, do not keep a `DirectoryStream` open for a long time just waiting for user interaction. Iterate/close within a unit of work, or switch to a suitable query/index architecture.
- Do not use `DirectoryStream` as a “watch” mechanism to detect changes: if you want to monitor create/delete/modify events, look at `WatchService` with its own rules. Iterating once does not register event notifications.
- A single `DirectoryStream` has no consistent snapshot guarantee; do not draw transactional conclusions merely from the fact that the loop completed.

### 19.1. When Does a Collection Seem Easier?

If a directory is very small and you only need names for display, creating a sorted `List<String>` can be simpler than working directly with an iterator. However, **retrieving the data from the filesystem still requires closing** the `DirectoryStream` or `Stream<Path>`; returning a list is no excuse for skipping `close()`.

Example:

~~~java
List<String> names = new ArrayList<>();
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        names.add(entry.getFileName().toString());
    }
}
Collections.sort(names);
~~~

This is an illustrative snippet, requiring Java Collections and NIO imports. After closing, `names` is data in RAM that is safe to use as a list structure; however, the filesystem can keep changing, so the list no longer reflects real-time state.

## 20. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Opening `DirectoryStream` and forgetting to close it | Leaks directory handles/file descriptors | `try-with-resources` |
| Creating a `Path` and thinking the directory is open | Confuses a path with a resource | Only `newDirectoryStream` opens iteration |
| Iterating after leaving the `try` block | The stream is already closed | Process inside the block or return a data copy |
| Calling `iterator()` twice | `DirectoryStream` supports at most one iterator | Open a new stream or store results |
| Assuming results are sorted | Provider does not promise ordering | Collect and sort if needed |
| Assuming it recurses automatically | Direct entries only | Manage sublevels yourself or use `walkFileTree` |
| Recursing deeply with unclosed parent/child streams | Can open too many handles | Nested try or an appropriate traversal API |
| Using default `isDirectory` to recurse into every entry | May follow symbolic links and hit cycles | `NOFOLLOW_LINKS` with safe traversal design |
| Using glob `*.txt` and assuming only regular files match | A directory named `a.txt` can also match | Add `Files.isRegularFile` |
| Thinking glob is Java regex | Pattern matches incorrectly | Distinguish glob syntax from regex syntax |
| Catching only `IOException` around the loop | Misses unchecked iterator errors | Handle `DirectoryIteratorException` |
| Catching `Exception` and returning the collected list | Hides failure, produces an incomplete result | Propagate error or return explicit partial status |
| Using `Files.list` without closing | `Stream<Path>` holds an iteration resource | `try-with-resources` |
| Trusting that a seen entry still exists later | TOCTOU and concurrent filesystem changes | Catch errors on the actual operation |
| Calling `normalize` and considering it safe against symlinks | Normalize does not resolve the real filesystem | Control permissions, links, root, and races |
| Using `DirectoryStream` to track all changes | It is a listing tool, not an event watcher | See `WatchService` |

## 21. Practice Exercises

**Exercise 1 — Counting direct children.** Create a temporary directory containing two files and one subdirectory, with another file inside the subdirectory. If you iterate the root with `DirectoryStream`, how many entries are counted?

**Answer:** three direct entries (two files and the subdirectory); the deeper file is not counted.

**Exercise 2 — Glob and entry types.** A directory contains a file `notes.txt` and a **directory** `backup.txt`. What can `newDirectoryStream(dir, "*.txt")` return?

**Answer:** it can return both, because the glob checks **entry names**. To include only regular files, add `Files.isRegularFile` with the desired symbolic link policy.

**Exercise 3 — Why must `try-with-resources` be used?** If the iteration loop fails at the 10th entry, what happens to the handle if the code only calls `close()` manually at the end of the success path?

**Answer:** the stream risks never being closed. `try-with-resources` calls `close()` when exiting the block even if an exception occurs.

**Exercise 4 — Open error vs. iteration error?** When `Files.newDirectoryStream(dir)` fails to open due to missing permissions, what exception might occur? What about when a filter throws `IOException` while fetching elements?

**Answer:** open errors are usually `IOException` or an appropriate subclass like `AccessDeniedException`. Filter/iteration errors can be wrapped in `DirectoryIteratorException`, where `getCause()` gives the original `IOException`.

**Exercise 5 — Ordering.** Why should the output of `for (Path entry : entries)` not be used directly to build a report table that must always be sorted by name?

**Answer:** `DirectoryStream` does not guarantee ordering. If a stable order is needed, collect the data and sort with a clearly defined comparator.

**Exercise 6 — Closing responsibility.** A method receives a `DirectoryStream<Path>` opened by the caller and only counts a few entries. Who should close it?

**Answer:** whoever owns it per the contract. By default, the caller opens and retains ownership so the caller closes it; a method borrowing the stream should not close it without an explicit agreement.

**Exercise 7 — Recursion.** Why can calling `visit(entry)` when `Files.isDirectory(entry)` returns true be dangerous?

**Answer:** it may follow symbolic links outside the tree or create cycles; deep recursion increases stack/handle usage. You need a link policy, depth limit, and proper error handling, or `walkFileTree`.

### Extended Practice

1. Add `"report-3.txt"` to `DirectoryStreamFilterDemo` and ensure the output stays sorted regardless of the order returned by the provider.
2. Try replacing the glob `"*.txt"` with `"*.{txt,md}"` and create a `README.md` file to observe the result.
3. Write a `listNames(Path dir)` method using `try-with-resources` that returns a sorted `List<String>` and lets I/O errors propagate rather than returning a partial list.
4. Write a two-level traversal method using nested `try-with-resources`, verifying that child streams close before deleting directories.
5. Create a `Filter<Path>` that can throw `IOException`, catch `DirectoryIteratorException`, and print the cause's message. Do not rely on random OS errors.
6. Compare `Files.list(dir).count()` with counting via `DirectoryStream` on an unchanging directory, remembering to close both sources.
7. Design a policy for symbolic links: distinguish when you want to follow a link versus when you must skip it, and test on a filesystem that supports links.

## 22. Summary

- **`Files.newDirectoryStream(dir)`** opens a mechanism to iterate **direct entries** of a directory, returning a `DirectoryStream<Path>`.
- **`DirectoryStream` is a `Closeable` resource** that can hold a directory handle. **Always close it with `try-with-resources`** in the code that owns the stream; never let GC decide when to close it.
- **A stream supports at most one iterator**, has no guaranteed ordering, and does not guarantee a consistent snapshot when the directory changes.
- **Globs** such as `"*.txt"` filter entry names; **`Filter<Path>`** handles custom conditions, including metadata when needed.
- **Open/close errors** are typically `IOException`; **iteration errors** may be `DirectoryIteratorException` containing an `IOException` cause.
- **Recursion requires managing multiple handles** and symbolic links carefully; for deep trees or complex structures, `Files.walkFileTree` is usually more suitable.
- **`Files.list` and `Files.walk` must also be closed** because they return a `Stream<Path>` tied to filesystem resources.
- **A listed path is neither a lock nor a permanent guarantee of existence**; accessing its contents later still requires handling exceptions and concurrent modifications.

### Official API Documentation (Java SE 17)

- [DirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html)
- [DirectoryStream.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.Filter.html)
- [DirectoryIteratorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryIteratorException.html)
- [Files.newDirectoryStream and Files.list](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor))
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
- [LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
