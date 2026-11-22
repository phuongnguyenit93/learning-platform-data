# Closing the Stream Returned From `Files.list`, `Files.walk`, and `Files.find` in Java

## 1. Why Must Directory-Traversal Streams Be Closed?

In Java NIO.2, **`Files.list(Path)`**, **`Files.walk(Path, ...)`**, and **`Files.find(Path, ...)`** return a **`Stream<Path>`** to traverse directory contents or directory trees. They leverage *lazy traversal*: the program does not have to load the entire list of paths into memory before filtering, counting, or finding the first match.

However, a Stream here **is not merely an in-memory computation pipeline**. It can hold references to an **open directory**, directory traversal iterators, and OS resources. In particular, `walk` and `find` may hold **one or more open directories** while descending through the tree.

**Most important rule:**

> **A `Stream<Path>` obtained from `Files.list`, `Files.walk`, or `Files.find` must be closed via `close()` when finished; prefer `try-with-resources`.** Calling terminal operations such as `forEach()`, `count()`, `findFirst()`, or `toList()` **does not replace closing the Stream**.

~~~text
Files.list(dir) / Files.walk(root) / Files.find(root, ...)
             |
             v
Stream<Path> bound to directory traversal resources
             |
             | filter / map / limit / sorted ...
             v
Terminal operation: forEach / count / findFirst / toList
             |
             | Result computed, yet NOT automatically closed
             v
Exit try-with-resources
             |
             v
Stream.close() -> releases associated directory resources
~~~

If you forget to close it—especially in long-running services or when processing thousands of directories—the application can hold more directory handles/file descriptors than necessary. Depending on the OS and provider, consequences include resource exhaustion, errors opening files/directories, or obstacles when modifying/deleting directories.

Note: **not every Stream in Java has to be closed**. For example, `List.of(1, 2, 3).stream()` processes only in-memory data. For the three `Files` APIs above, **the API contract specifies that open resources must be released**, so closing is not optional.

## 2. Distinguishing `list`, `walk`, and `find`

| API | Traversal Scope | Return Value | Key Differences | Lifecycle |
| --- | --- | --- | --- | --- |
| `Files.list(dir)` | Direct entries in `dir`, **not recursive** | `Stream<Path>` | Excludes `dir` itself; does not descend into subdirectories | **Must close** |
| `Files.walk(start)` | Recursive from `start`; default max depth up to `int` limit | `Stream<Path>` | Includes `start` itself; depth-first traversal | **Must close** |
| `Files.walk(start, maxDepth)` | Tree traversal with bounded depth | `Stream<Path>` | `maxDepth=0` includes only `start`; depth 1 includes direct children | **Must close** |
| `Files.find(start, maxDepth, matcher)` | Tree traversal returning only paths matching the filter | `Stream<Path>` | `matcher` receives both `Path` and `BasicFileAttributes` | **Must close** |

The method names reflect **search scope and intent**, not different cleanup mechanics. All three require closing the resource afterward.

**`Files.list` is not `java.io.File.list()`**. The two APIs belong to different classes:

- `Files.list(Path)`: returns a `Stream<Path>` **tied to an open directory**, so it must be closed.
- `File.list()`: returns a `String[]` array or `null` under its own contract; it is not a Stream and has no returned Stream lifecycle.

Likewise, do not confuse `Files.find` with an ordinary `stream.filter`. `Files.find` **traverses the directory tree itself** and supplies metadata to the matcher; `filter` is only an intermediate operation on an already-created Stream.

## 3. Default Pattern: `try-with-resources`

To list a directory:

~~~java
// Code snippet inside a method having Path directory and handling IOException.
try (Stream<Path> paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
~~~

To traverse a directory tree:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

To search files by attributes:

~~~java
try (Stream<Path> paths = Files.find(
        root,
        4,
        (path, attrs) -> attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".txt"))) {
    paths.forEach(System.out::println);
}
~~~

These are **illustrative code snippets**, assuming `Path`, `Files`, and `Stream` are imported and `IOException` is handled.

How it works:

1. Java calls `Files.list/walk/find` and receives a Stream bound to the source.
2. Intermediate operations `filter`, `map`, etc. configure the pipeline.
3. The terminal operation consumes elements on demand.
4. Whether the body finishes normally, executes `return`, or throws an exception, **`try-with-resources` attempts to close the Stream**.

The `try (Stream<Path> paths = ...)` syntax works because `Stream` extends `BaseStream`, which implements `AutoCloseable` and provides `close()`.

**Key reminder:** if you call the `Files` API to create a Stream **outside** a `try` block and an error occurs before entering a managing `finally`/`try`, the resource risks never being closed. Place the Stream-opening call directly in the `try-with-resources` resource header.

## 4. Lazy Traversal Does Not Mean No Open Resources

A common misconception is “the Stream is lazy, so nothing needs closing until the first element is actually read.” In reality, returning the Stream can already initialize directory-traversal state and hold resource references; **the API requires closing even if zero elements are consumed**.

~~~java
// WRONG: creating a Stream and discarding it without closing.
Files.list(directory);
~~~

Even with no terminal operation at all, the returned Stream is not closed on time. Similarly, configuring `filter` or `limit` and then abandoning the pipeline does not close the underlying source.

A program might write:

~~~java
Stream<Path> stream = Files.walk(root);
Stream<Path> filtered = stream.filter(Files::isRegularFile);
// Terminal operation has not run yet.
~~~

This is not complete cleanup code: the program must ensure **the final pipeline or source is closed within the same lifecycle**. Putting TWR around the directly built pipeline is usually clearer:

~~~java
try (Stream<Path> paths = Files.walk(root)
        .filter(Files::isRegularFile)) {
    paths.forEach(System.out::println);
}
~~~

Closing a pipeline backed by `Files.walk` releases the resources carried by the pipeline rather than leaving directory handles waiting for GC. **Never reuse a Stream a second time** after calling a terminal operation on it.

## 5. Java 17+ Program Comparing All Three APIs

Create file **DirectoryStreamsDemo.java**, saved with UTF-8 encoding:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class DirectoryStreamsDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("directory-streams-");
        Path nested = root.resolve("nested");
        Path alpha = root.resolve("alpha.txt");
        Path beta = nested.resolve("beta.txt");

        try {
            Files.createDirectory(nested);
            Files.writeString(alpha, "alpha", StandardCharsets.UTF_8);
            Files.writeString(beta, "beta", StandardCharsets.UTF_8);

            try (Stream<Path> entries = Files.list(root)) {
                List<String> names = entries
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("list=" + names);
            }

            try (Stream<Path> tree = Files.walk(root, 2)) {
                List<String> names = tree
                        .map(p -> p.equals(root)
                                ? "."
                                : root.relativize(p).toString()
                                      .replace('\\', '/'))
                        .sorted()
                        .toList();
                System.out.println("walk=" + names);
            }

            try (Stream<Path> matches = Files.find(
                    root, 2,
                    (p, attrs) -> attrs.isRegularFile()
                            && p.getFileName().toString()
                                    .endsWith(".txt"))) {
                List<String> names = matches
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("find=" + names);
            }
        } finally {
            Files.deleteIfExists(beta);
            Files.deleteIfExists(alpha);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 DirectoryStreamsDemo.java
java DirectoryStreamsDemo
~~~

Expected stdout:

~~~text
list=[alpha.txt, nested]
walk=[., alpha.txt, nested, nested/beta.txt]
find=[alpha.txt, beta.txt]
~~~

**Detailed explanation:**

- The demo directory contains `alpha.txt` at root and `nested/beta.txt` under a subdirectory.
- `Files.list(root)` returns only **the two entries directly inside root**: `alpha.txt` and `nested`. It **does not** continue down to `beta.txt` and does not return `root` itself.
- `Files.walk(root, 2)` returns `root` (depth 0), the two direct entries (depth 1), and `nested/beta.txt` (depth 2). The `"."` string is a representation intentionally chosen by the example for root itself.
- `Files.find(root, 2, matcher)` traverses with the same depth limit of 2, yet **emits into the Stream** only entries with `attrs.isRegularFile()` and names ending in `.txt`.
- `sorted()` stabilizes stdout across operating systems, because **directory enumeration order is not guaranteed**. `replace('\\', '/')` normalizes only **the relative display strings in the example**, not the actual `Path` objects.
- All three Streams are placed individually inside **`try-with-resources`**. Each source closes before moving on to the next operation.
- The `finally` block deletes the temporary files/directories owned by the program; this is **secondary demo cleanup**, not a substitute for closing Streams.

The program assumes the environment allows creating temporary files and directories; if permissions, disk space, or I/O fail, the method throws `IOException` instead of printing the expected stdout.

## 6. Depth in `Files.walk` and `Files.find`

Both `walk` and `find` take a **`maxDepth`** parameter:

~~~text
root/                   depth 0
root/a.txt              depth 1
root/sub/               depth 1
root/sub/b.txt          depth 2
root/sub/inner/         depth 2
root/sub/inner/c.txt    depth 3
~~~

- `maxDepth=0`: evaluates only `root` itself.
- `maxDepth=1`: evaluates `root` and direct entries.
- `maxDepth=2`: adds entries at depth 2.
- Negative `maxDepth`: throws `IllegalArgumentException`.
- `Files.walk(root)` without a limit argument is specified as equivalent to `Integer.MAX_VALUE` depth.

**A depth limit does not replace `close()`**. Walking just one level or visiting only a few elements still uses a Stream that can hold directory resources open.

`Files.walk` traverses **depth-first**, emitting the starting entry before child entries. For each directory, entries inside appear as encountered during traversal. However, **sibling order is not guaranteed alphabetically**. If deterministic ordering is needed, apply `sorted()` or an appropriate comparator, keeping in mind that sorting may retain many elements in memory.

**`Files.walk` includes `start` itself even when `start` is a regular file**. When `start` is a valid regular file, the Stream contains just that path; do not assume `walk` returns only files *inside* a directory.

## 7. `Files.find`: Matcher Receives `Path` and `BasicFileAttributes`

Typical syntax:

~~~java
try (Stream<Path> results = Files.find(
        root,
        5,
        (path, attrs) -> attrs.isRegularFile()
                && attrs.size() > 0
                && path.getFileName().toString().endsWith(".json"))) {
    results.forEach(System.out::println);
}
~~~

`BiPredicate<Path, BasicFileAttributes>` receives:

- **`path`**: the path of the entry currently being evaluated.
- **`attrs`**: basic metadata already retrieved for that entry, including `isRegularFile()`, `isDirectory()`, `size()`, modification time, etc.

Compared with `Files.walk(root).filter(p -> ...)` where **every filter step calls `Files.readAttributes(p, ...)` again**, `Files.find` avoids redundant attribute lookups because the API already fetches entry attributes during traversal.

Distinguish clearly:

- **`Files.find` emits only paths accepted by the matcher**. It still must traverse portions of the tree to discover eligible items; returning `false` from the matcher for a directory **does not automatically prune that entire branch**.
- If you want to **actively skip a subtree** when encountering a specific directory, `Files.walkFileTree` with `FileVisitor` and `SKIP_SUBTREE` is usually more suitable.
- Because the matcher is called repeatedly, avoid unnecessary side effects. If the matcher performs its own I/O logic and throws an unchecked exception, the application must still handle it.

**Do not treat metadata as an immutable snapshot:** files can change after attributes are read. Applications requiring strong consistency still need locking/snapshot policies or identity-based file opening.

## 8. Short-Circuiting Does Not Release Directory Handles Automatically

One of the most common mistakes:

~~~java
// WRONG: findFirst returns a result without automatically closing the source.
Path first = Files.list(directory)
        .findFirst()
        .orElse(null);
~~~

Similarly:

~~~java
// WRONG: limit(3) bounds elements, does not close the Stream.
Files.walk(root)
        .limit(3)
        .forEach(System.out::println);
~~~

Or:

~~~java
// WRONG: count traverses results, does not automatically close the Stream.
long amount = Files.find(root, 3, matcher).count();
~~~

In the final snippet, `matcher` is an appropriate `BiPredicate` defined by the program.

Fix them as:

~~~java
try (Stream<Path> entries = Files.list(directory)) {
    Path first = entries.findFirst().orElse(null);
    // Process first while the resource is open.
}
~~~

~~~java
try (Stream<Path> tree = Files.walk(root)) {
    tree.limit(3).forEach(System.out::println);
}
~~~

~~~java
try (Stream<Path> matches = Files.find(
        root, 3, (p, a) -> a.isRegularFile())) {
    long amount = matches.count();
    System.out.println(amount);
}
~~~

`findFirst()`, `anyMatch()`, and `limit()` can stop consuming elements early. `count()` generally traverses items to count them, while `toList()` collects elements. Yet **whether reading zero elements, a few elements, or running to completion, the obligation to close the Stream remains unchanged**.

**TWR on the source stream closes the resource at the end of the block**, even when a terminal operation terminated early.

## 9. Runnable Example: Terminal Operation Finishes Yet Stream Is Not Closed

Create file **ShortCircuitCloseDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

public class ShortCircuitCloseDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("stream-close-");
        Path file = root.resolve("one.txt");

        try {
            Files.writeString(file, "data", StandardCharsets.UTF_8);

            AtomicBoolean closeHandlerCalled = new AtomicBoolean();

            try (Stream<Path> entries = Files.list(root)
                    .onClose(() -> closeHandlerCalled.set(true))) {

                boolean found = entries.anyMatch(path ->
                        path.getFileName().toString().equals("one.txt"));

                System.out.println("found=" + found);
                System.out.println("closedInsideTry="
                        + closeHandlerCalled.get());
            }

            System.out.println("closedAfterTry="
                    + closeHandlerCalled.get());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Run with Java 17+:

~~~bash
javac -encoding UTF-8 ShortCircuitCloseDemo.java
java ShortCircuitCloseDemo
~~~

Stdout:

~~~text
found=true
closedInsideTry=false
closedAfterTry=true
~~~

Explanation:

1. `Files.list(root)` creates a Stream from a directory containing `one.txt`.
2. `onClose(...)` registers a **handler that runs when the Stream closes**, simply flipping a flag in this demo.
3. `anyMatch(...)` finds the file and can stop early. After the terminal operation returns, the flag is still **false**: the terminal operation did not invoke `close()`.
4. Upon exiting `try-with-resources`, `close()` is called and the handler runs, turning the flag **true**.
5. This demo observes when **the close handler** runs, rather than directly measuring an OS file descriptor. Having `Files.list`'s Stream close its directory resource is part of `Files`'s contract.

From this we can deduce: **it is not only partially read Streams that need closing; a Stream that has completed a terminal operation must still be closed**.

## 10. Open-Time I/O Errors Differ From Traversal-Time Errors

These methods declare `throws IOException` when **initializing the source** fails, for example:

~~~java
Stream<Path> entries = Files.list(directory);
~~~

If `directory` does not exist, is not a directory, or cannot be opened, that call can throw `IOException` or a specific subclass like `NoSuchFileException` or `NotDirectoryException` when supported by the provider.

However, because the Stream is traversed **lazily**, I/O can occur **after `Files.list/walk/find` has already returned**. When an I/O error occurs while continuing to read directories, the Java SE 17 documentation states that it is **wrapped in `UncheckedIOException`** and thrown by the terminal/intermediate traversal operation that triggered the access.

~~~text
Calling Files.list/walk/find:
    failure on open        -> IOException (checked)

Consuming Stream<Path>:
    failure on traversal   -> UncheckedIOException
                              cause is the original IOException
~~~

Diagnostic pattern:

~~~java
// Code snippet: import java.io.IOException, java.io.UncheckedIOException
// and Path, Files, Stream classes.
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
} catch (java.io.UncheckedIOException traversalFailure) {
    System.err.println("Traverse failed: "
            + traversalFailure.getCause());
} catch (IOException openingFailure) {
    System.err.println("Open failed: " + openingFailure);
}
~~~

Several notes:

- `UncheckedIOException.getCause()` retrieves the underlying `IOException` for logging/diagnostics.
- If the program **cannot recover**, usually propagate the error after adding context; never treat a truncated traversal result as success.
- Exceptions from **user lambdas** (e.g., parsing, network calls, or runtime exceptions in a matcher) are a separate category; not every pipeline failure comes from the `Files` API.
- When both the `try` body and cleanup throw exceptions, TWR's **primary/suppressed exception** mechanism must be respected; never swallow the initial error.
- `Files.list` and `Files.walk` are **weakly consistent**: they do not freeze the directory/tree during traversal. If entries are added, deleted, or renamed during scanning, results may or may not reflect those changes, and I/O errors can also arise.

Do not call `Files.exists(root)` beforehand and then assume `Files.walk` will always succeed. Checking and using happen at two different times; resources can vanish or permissions change. Handle errors at the actual operation.

## 11. Returning a Stream From a Method: Who Owns Closing Responsibility?

For a service method, there are two clear design options.

### Option A — Process Inside the Method and Return a Completed Result

~~~java
// Code snippet, with appropriate imports.
static long countDirectEntries(Path dir) throws IOException {
    try (Stream<Path> paths = Files.list(dir)) {
        return paths.count();
    }
}
~~~

Advantage: the method **owns and closes** the Stream itself. The caller receives a `long` and does not have to manage directory handles. This is usually easier to use and less prone to leaks.

### Option B — Return a Live Stream and Transfer Close Responsibility to the Caller

~~~java
static Stream<Path> openTextFiles(Path root)
        throws IOException {
    return Files.walk(root)
            .filter(p -> Files.isRegularFile(p)
                    && p.getFileName().toString().endsWith(".txt"));
}
~~~

The caller must close it:

~~~java
try (Stream<Path> textFiles = openTextFiles(root)) {
    textFiles.forEach(System.out::println);
}
~~~

Option B fits when an API intentionally returns lazy results. However, **ownership has transferred to the caller**; the method name and API contract should state clearly that the returned Stream holds directory resources that must be closed.

**Wrong pattern:**

~~~java
// WRONG: closes the source inside the method before the caller consumes it.
static Stream<Path> broken(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile);
    }
}
~~~

TWR runs `close()` **before returning the result to the caller**. The returned Stream is tied to a closed pipeline, so it cannot be used as a valid traversal source.

`Stream.onClose(...)` can be used for custom cleanup when building APIs, provided you understand *which resource is owned*. For `Files.list/walk/find`, closing the returned Stream properly is sufficient; do not invent dummy close handlers just to duplicate existing behavior.

## 12. Single-Use Streams and Intermediate Pipelines

A Stream can be used for only **one consuming pipeline**. After:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    long n = paths.count();
    // paths.findFirst(); // Invalid: Stream has already been consumed.
}
~~~

Do not call `findFirst()`, `forEach()`, or another terminal operation on the same Stream. Subsequent operations throw `IllegalStateException` because the stream has already been operated upon or closed.

If two different statistics are needed, design **a single collector** aggregating both in one pass, or **open a new Stream** for the second pass; each Stream must have its own TWR.

When using a derived pipeline:

~~~java
try (Stream<Path> result = Files.walk(root)
        .filter(Files::isRegularFile)
        .limit(10)) {
    result.forEach(System.out::println);
}
~~~

Closing the derived pipeline also closes resources associated with the pipeline's traversal source. There is no need to keep three separate Stream variables and try to close each multiple times.

**Do not equate laziness with low memory in every case.** `sorted()` and `toList()` can still retain many `Path` objects in memory; operations like `count()` or `anyMatch()` typically keep minimal state. For huge directories, process each `Path` incrementally rather than collecting everything first.

## 13. Symbolic Links, Loops, and the `FOLLOW_LINKS` Option

By default, `Files.walk` and `Files.find` **do not automatically follow symbolic links to subdirectories** recursively like ordinary directories. To follow symlinks, specify `FileVisitOption.FOLLOW_LINKS`:

~~~java
try (Stream<Path> paths = Files.walk(
        root, 10, java.nio.file.FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
~~~

However:

- Following links can lead traversal outside what the application initially assumed was `root`.
- A symlink can point back to an ancestor directory, creating a **cycle**. The file-tree traversal API includes cycle detection and can throw errors like `FileSystemLoopException` as an I/O error during traversal.
- The filesystem can change during traversal, so results and attributes are not an immutable snapshot.
- Choosing whether to follow links must be driven by business and safety requirements—do not turn on `FOLLOW_LINKS` just to “find more files.”

**Do not use `normalize()` or a single `isDirectory()` check to assume traversal is immune to symbolic links or races.** For untrusted paths, enforce appropriate filesystem security policies.

## 14. Why Does `filter` Not Automatically Prune Tree Branches?

The snippet:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p -> !p.getFileName().toString()
                    .equals("node_modules"))
         .forEach(System.out::println);
}
~~~

only means: **omit paths named `node_modules` from the output**. It **does not guarantee skipping descent inside the `node_modules` directory**. `Files.walk` can still traverse its children to feed elements into `filter`.

If you truly need to **prune a subtree**, use a visitor:

~~~java
// Code snippet: import Files, Path, FileVisitResult,
// SimpleFileVisitor, BasicFileAttributes, and IOException.
Files.walkFileTree(root,
        new java.nio.file.SimpleFileVisitor<Path>() {
    @Override
    public java.nio.file.FileVisitResult preVisitDirectory(
            Path dir,
            java.nio.file.attribute.BasicFileAttributes attrs) {
        if (dir.getFileName() != null
                && dir.getFileName().toString()
                        .equals("node_modules")) {
            return java.nio.file.FileVisitResult.SKIP_SUBTREE;
        }
        return java.nio.file.FileVisitResult.CONTINUE;
    }
});
~~~

This is a **code snippet**, not a standalone runnable class. `Files.walkFileTree` uses visitor callbacks to control traversal (including `SKIP_SUBTREE`) instead of returning a `Stream<Path>` that must be closed; the visitor must still handle `IOException` and failure callbacks per contract.

For tree-traversal tasks requiring **recursive deletion, branch skipping, per-branch error classification, or structured state tracking**, `walkFileTree` is usually a better fit than `walk(...).filter(...)`.

## 15. `Files.newDirectoryStream` and `DirectoryStream` Must Also Be Closed

Alongside the Stream API, Java offers:

~~~java
try (java.nio.file.DirectoryStream<Path> entries =
        Files.newDirectoryStream(directory)) {
    for (Path p : entries) {
        System.out.println(p);
    }
}
~~~

`DirectoryStream<Path>` is a **different API** from `Stream<Path>`, yet it also opens a directory and must be closed after iteration. It supports an iterator and can accept a glob filter when opened:

~~~java
try (java.nio.file.DirectoryStream<Path> textEntries =
        Files.newDirectoryStream(directory, "*.txt")) {
    for (Path p : textEntries) {
        System.out.println(p.getFileName());
    }
}
~~~

`DirectoryStream` has its own error and lifecycle rules; do not confuse `iterator.hasNext()` with a Java Stream terminal operation. Using `for-each` **does not automatically close** a `DirectoryStream`; TWR in the snippet is what closes it.

If you specifically need the **`Stream<Path>`** API, `list`/`walk`/`find` are the natural choice. If you want iterator control and filename filtering for a single directory, `newDirectoryStream` is also well worth considering.

## 16. Choosing the Right Tool for the Goal

| Need | Usually Best API | Resource Management |
| --- | --- | --- |
| Immediately list entries of one directory | `Files.list(dir)` | TWR on Stream |
| Count direct entries | `Files.list(dir).count()` in TWR | Close even after `count` finishes |
| Traverse an entire tree | `Files.walk(root)` | TWR on Stream |
| Traverse a tree up to a fixed depth | `Files.walk(root, maxDepth)` | TWR on Stream |
| Find entries by metadata | `Files.find(root, depth, predicate)` | TWR on Stream |
| Stop early after a few paths | `limit(n)`, `findFirst()` in pipeline | **Still close** despite short-circuiting |
| Skip an entire subtree | `Files.walkFileTree` + `SKIP_SUBTREE` | Control callbacks and traversal errors |
| Iterate one directory with `for-each` | `Files.newDirectoryStream(dir)` | TWR on `DirectoryStream` |
| Need results after closing source | Compute/collect inside TWR | Return `List`/`Map`/value, not a closed Stream |
| Need to return lazy results externally | Return live Stream with ownership contract | **Caller must close** |

If a directory changes continuously, result handling must accept **weakly consistent** state or add snapshot/synchronization policies. **Closing manages resource lifecycles; it does not turn traversal into a snapshot or transaction.**

## 17. Common Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Calling `Files.list(dir).forEach(...)` and discarding Stream | Fails to close directory resource promptly | Wrap Stream in TWR |
| Calling `Files.walk(root).count()` without closing | Terminal operation does not close automatically | Wrap `count` in TWR |
| Calling `Files.find(...).findFirst()` without closing | Short-circuiting still holds source open | Close Stream after retrieving result |
| Assuming `Files.list` recurses | Misses files under subdirectories | Use `walk` or `find` |
| Assuming `Files.walk` excludes `root` itself | Off-by-one counts or wrong element handling | Remember `root` is the first element visited |
| Filtering out a directory and expecting its subtree skipped | Still descends into that branch | Use `walkFileTree` + `SKIP_SUBTREE` |
| Catching only `IOException` on `Files.walk` | Misses consumption-time `UncheckedIOException` | Handle both phases |
| Returning a Stream from an exited `try-with-resources` | Caller receives an already-closed Stream | Return materialized result or transfer ownership |
| Calling `count()` then `findFirst()` on the same Stream | Stream is already consumed | Open a new Stream or aggregate in one pass |
| Assuming listing order is stable | Order depends on provider and directory | Sort when needed; consider RAM |
| Enabling `FOLLOW_LINKS` casually | Can escape tree or hit loops | Define link policy and depth limits |
| Using `sorted().toList()` on a huge tree | Holds many `Path`s in memory | Process streaming or with controlled traversal |
| Not closing `DirectoryStream` after `for-each` | Finishing loop does not close it | TWR around `DirectoryStream` |
| Modifying/deleting while relying on an open traversal Stream | Can cause inconsistencies or I/O errors | Design separate operations and handle errors |
| Skipping cleanup when a terminal operation throws | Stream retains open resources | Wrap entire pipeline in TWR |

## 18. Self-Check Questions

**Question 1.** Do `Files.list`, `Files.walk`, and `Files.find` return purely in-memory data so they do not need closing?  
**Answer:** No. Their Streams can hold open directory resources. They must be closed after use, preferably with TWR.

**Question 2.** Does `Files.list(dir)` return files inside subdirectories of `dir`?  
**Answer:** No. It lists direct entries only; use `walk` or `find` if recursion is needed.

**Question 3.** Does `Files.walk(root, 0)` return any `Path`?  
**Answer:** Yes. It includes `root` itself if opening/accessing `start` succeeds; depth 0 examines only `start`.

**Question 4.** Why can `Files.find(root, 3, matcher)` be preferable to `Files.walk(root, 3).filter(...)` when inspecting lots of metadata?  
**Answer:** `find`'s matcher already receives `BasicFileAttributes`, avoiding redundant attribute lookups. It still has to walk the tree to find entries.

**Question 5.** If `findFirst()` or `limit(1)` consumes only one item, must the Stream still be closed?  
**Answer:** Yes. Stopping a terminal operation or pipeline early does not close the resource.

**Question 6.** How can open-time directory errors and traversal-time errors differ in exception type?  
**Answer:** Open errors may be checked `IOException`; I/O errors occurring during traversal after the API returned the Stream are wrapped in `UncheckedIOException`.

**Question 7.** Why should you not return a Stream from inside a `try-with-resources` block in a factory method?  
**Answer:** TWR closes the Stream before the caller receives it, leaving the returned pipeline unusable as a live source.

**Question 8.** Does `Files.walk(root).filter(p -> !name.equals("cache"))` automatically skip all contents of the `cache` directory?  
**Answer:** No. `filter` only removes items from output; use `walkFileTree` and `SKIP_SUBTREE` if you need to prune branches.

**Question 9.** If you need deterministic alphabetical order inside a directory, can you assume `Files.list` already sorts entries?  
**Answer:** No. Use `sorted()` or an appropriate comparator, and keep in mind the memory cost of buffering elements.

**Question 10.** If a Stream has already been fully consumed by `forEach`, is calling `close()` still necessary?  
**Answer:** Yes. Completing a terminal operation is distinct from closing the I/O source; `close()` releases resources per contract.

## 19. Java SE 17 Documentation

- [Files.list(Path)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#list(java.nio.file.Path)): direct directory listing and Stream closing requirement.
- [Files.walk(Path, int, FileVisitOption...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walk(java.nio.file.Path,int,java.nio.file.FileVisitOption...)): depth-first traversal, `maxDepth`, open directory resources.
- [Files.find(Path, int, BiPredicate, FileVisitOption...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#find(java.nio.file.Path,int,java.util.function.BiPredicate,java.nio.file.FileVisitOption...)): matcher with `BasicFileAttributes` and Stream lifecycle.
- [BaseStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html): `close()`, `onClose()`, and single-use nature.
- [Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor)): visitor for controlling traversal and pruning branches.
- [DirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html): directory-iteration iterator and close management.

**Summary:** **`list`** iterates one level, **`walk`** traverses a tree, and **`find`** traverses a tree while selecting paths via a metadata-aware predicate. All three return a `Stream<Path>` tied to open directories, so **managing their lifecycle with `try-with-resources` or an equivalent mechanism is mandatory**. Lazy traversal, completed terminal operations, short-circuiting, `count`, `toList`, or finding a match **none of them close the underlying resource automatically**.
