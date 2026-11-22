# Closing Sources with try-with-resources

In the **I/O Sources and Resource Management** chapter of the **Java Stream API**, declarative pipelines can draw data from a `List`, an array, a number generator, or directly from files and directories. The same `filter`, `map`, `reduce`, and `collect` style applies across many sources, yet **resource management responsibility depends on how the Stream was created**.

With I/O sources such as `Files.lines`, `Files.list`, or `Files.walk`, a Stream may keep a file or directory open during traversal. Running a terminal operation does not mean the source has been closed. The safe rule is to **place resource-owning Streams inside `try-with-resources` and run the entire pipeline within that scope**. Even when the pipeline stops early, encounters an error, or returns a value, Java still calls `close()` upon exiting the `try` block.

This lesson explains the Stream closing contract, which sources need closing, how resource ownership is passed between methods, exception handling, and common pitfalls. These principles remain critical when adding `parallel()`, using a Spliterator, or extending pipelines with Stream Gatherers: a pipeline that computes the right data can still leak resources if the I/O lifecycle is uncontrolled.

## 1. Why Does a Stream Need to Be Closed?

A Stream is a **description of element-processing steps**, not necessarily a copy of data already residing in memory.

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Minh", "An");

Stream<String> fromList = names.stream();
Stream<String> fromValues = Stream.of("A", "B", "C");
~~~

The two Streams above use already-available data. Normally, they **do not own** files, sockets, or OS resources that need releasing after traversal. In such cases, a `try-with-resources` block is usually unnecessary.

Conversely:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path file = Path.of("logs/app.log");

Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8);
~~~

`Files.lines` creates a Stream that reads file lines on demand as the pipeline requests them. This source has an I/O resource that must be closed. If a program lets the Stream live too long or forgets to close it, the file may stay open, causing the application to exhaust file descriptors/handles or blocking certain file operations on the OS.

**Do not assume every Stream requires closing in the same mandatory way.** However, for any source documented as backed by I/O resources, follow the closing instructions of the factory method that created it.

## 2. The AutoCloseable Contract and try-with-resources

`Stream<T>` extends `BaseStream`, and `BaseStream` extends `AutoCloseable`. Therefore, a variable of type `Stream<String>` can be declared in `try-with-resources`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path file = Path.of("logs/app.log");

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    long warnings = lines
            .filter(line -> line.startsWith("WARN"))
            .count();

    System.out.println("Warning line count: " + warnings);
} // Java automatically calls lines.close() here.
~~~

Sequence:

1. `Files.lines(...)` opens the I/O source and returns a Stream.
2. The Stream is declared as a **resource** in the `try` parentheses.
3. Intermediate operations like `filter` form the pipeline; `count` is the terminal operation.
4. When the `try` block finishes, Java calls `lines.close()`, whether traversal succeeded or threw an exception.
5. The resource owned by the Stream is released according to the source contract.

Resource declaration syntax works since Java 7; the Stream API and `Files.lines` arrived in Java 8. `Path.of` appeared in Java 11; on Java 8 you can use `Paths.get("logs/app.log")`.

> **Core rule:** Keep **opening the source, using the Stream, and closing the source** inside the same clear resource-ownership scope.

## 3. Terminal Operations Do Not Replace close()

The most important distinction is between **ending a pipeline** and **closing a resource**.

| Action | Meaning | Guarantees closing I/O source? |
| --- | --- | --- |
| `filter`, `map`, `limit` | Builds intermediate operations, usually lazy | No |
| `count`, `collect`, `toList`, `reduce` | Executes and completes the pipeline | No |
| `findFirst`, `anyMatch` | Short-circuiting terminal operations | No |
| `Stream.close()` | Closes the Stream and runs registered close handlers | Performs the closing action defined by the source |
| Exiting `try-with-resources` | Java automatically calls `close()` on the resource | Yes, even on exception or `return` paths |

The following code **risks leaking resources**, even though `count()` has returned:

~~~java
// Do not use this pattern with Files.lines sources.
Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8);

long total = lines.count();

// Missing lines.close(): the resource lifecycle has not been handled properly.
~~~

Replace with:

~~~java
long total;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    total = lines.count();
}
~~~

Once a terminal operation finishes, **the Stream object cannot be reused**, even if `close()` has not yet been called. Conversely, after `close()` is called, the Stream is also no longer permitted to run a new pipeline even if no terminal operation has run.

These are two different states, yet neither allows further use of the same Stream instance.

## 4. Early Stopping Still Requires Closing the Source

Terminal operations such as `findFirst`, `findAny`, and `anyMatch` can stop once enough evidence is found. `limit` can also cause upstream stages to supply only part of the data.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

Path file = Path.of("logs/app.log");

Optional<String> firstError;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    firstError = lines
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}

firstError.ifPresent(System.out::println);
~~~

If the first error line appears near the top of the file, the Stream may not need to read the rest. Even when only one line is read, **the source must still be closed** when exiting the `try` block.

Similarly:

~~~java
boolean containsCritical;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    containsCritical = lines.anyMatch(
            line -> line.contains("CRITICAL")
    );
}
~~~

If `CRITICAL` is found, `anyMatch` can return early. If not found, it continues traversing until the source is exhausted. In both cases, `try-with-resources` handles closing.

**Do not rely on "having read the whole file" as an auto-close signal:** even a full traversal does not replace `close()` under the I/O Stream contract.

## 5. I/O Stream Factories That Commonly Need try-with-resources

Sources from `java.nio.file.Files` are especially important:

| Factory | Data provided | Resource risk | How to use |
| --- | --- | --- | --- |
| `Files.lines(path)`, `Files.lines(path, charset)` | Text lines from a file | Keeps file-reading source open during traversal | `try (Stream<String> s = Files.lines(...))` |
| `Files.list(dir)` | Direct entries inside a directory | Holds resources tied to directory listing | `try (Stream<Path> s = Files.list(dir))` |
| `Files.walk(root)`, `Files.walk(root, depth)` | Paths from directory tree traversal | May hold resources for tree traversal | `try (Stream<Path> s = Files.walk(root))` |
| `Files.find(root, depth, matcher)` | Paths matching search criteria | Holds resources for file-system access | `try (Stream<Path> s = Files.find(...))` |

`Files.list` provides only **direct** entries in a directory. `Files.walk` can descend into subdirectories within the chosen depth. Those are functional differences in the source, whereas **the Stream closing requirement** is the same.

Example listing regular files in a directory:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<Path> listRegularFiles(Path directory) throws IOException {
    try (Stream<Path> entries = Files.list(directory)) {
        return entries
                .filter(Files::isRegularFile)
                .collect(Collectors.toList());
    }
}
~~~

The `Path` list is materialized **inside** the `try` block; after the block exits, the list remains usable. `Path` instances merely represent paths and do not require keeping the directory Stream open to access the collected items.

For deep traversal:

~~~java
static long countJavaFiles(Path projectRoot) throws IOException {
    try (Stream<Path> paths = Files.walk(projectRoot)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .count();
    }
}
~~~

Directory tree traversal can hit permission or I/O errors; handle errors as required by your business logic and avoid assuming the file system stays static during traversal.

## 6. BufferedReader.lines: Who Owns the Resource?

`BufferedReader.lines()` also creates a `Stream<String>`, but **the direct resource to manage is `BufferedReader`**. Do not assume calling `close()` on the Stream returned by `reader.lines()` will close `reader`.

Clear approach:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countNonEmptyLines(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

        return reader.lines()
                .filter(line -> !line.isEmpty())
                .count();
    }
}
~~~

`try-with-resources` closes `reader` upon exiting the block. The Stream from `reader.lines()` is traversed while the reader is open, avoiding any use-after-close along the normal path.

If you want to manage both the Stream and the reader explicitly, declare multiple resources:

~~~java
import java.util.stream.Stream;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8);
     Stream<String> lines = reader.lines()) {

    long total = lines.count();
    System.out.println(total);
}
~~~

Resources are closed in **reverse declaration order**: `lines.close()` first, then `reader.close()`. Java still attempts to close remaining resources if one close operation fails.

The important point when using wrappers like `BufferedReader`, `Scanner`, or a custom Stream is: **whichever object truly owns the underlying resource must have an explicit closing mechanism**. Do not infer a wrapper's lifetime solely from the fact that it returns a Stream.

## 7. Do Not Return an Already-Closed Stream

This mistake happens easily when splitting code into helper methods.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// Wrong: returns a pipeline depending on an already-closed Stream.
static Stream<String> badRead(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank());
    }
}
~~~

`filter` is a *lazy* intermediate operation. At the moment of `return`, no terminal operation has needed to read data yet. However, before the method returns the Stream object to the caller, the `try` block finishes and `lines.close()` is called. The caller receives a pipeline that can no longer be used.

This example uses `String.isBlank()` (Java 11+); on Java 8 it can be replaced with `!line.trim().isEmpty()`.

There are two proper designs depending on who owns the source.

### Approach A: Read and Collect Results Before Returning

When an API needs to return a finite list, execute the pipeline **inside** the resource scope:

~~~java
import java.util.List;
import java.util.stream.Collectors;

static List<String> readNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> !line.isBlank())
                .collect(Collectors.toList());
    }
}
~~~

The `try` block runs the terminal operation first, producing a `List<String>` independent of the source's lifetime. Afterward the Stream closes and the method returns the list.

In exchange, this keeps all results in memory; it is unsuitable for unbounded data or very large files if the application does not need to store everything.

### Approach B: Return an Open Stream and Clearly Assign Closing Responsibility to the Caller

If the API needs to process lines lazily one by one, the method can return an **unclosed** Stream:

~~~java
/**
 * Returns a Stream that reads the file on demand.
 * The caller must close the Stream using try-with-resources.
 */
static Stream<String> openNonBlankLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> !line.isBlank());
}
~~~

The caller must take ownership of closing:

~~~java
try (Stream<String> lines = openNonBlankLines(path)) {
    lines.limit(100).forEach(System.out::println);
}
~~~

This avoids holding all results in memory, but the API contract **must state clearly who closes the Stream**. Never let callers mistake it for a collection Stream where `close()` can be skipped.

> **Ownership transfer principle:** A method either **owns the Stream and closes it before returning computed data**, or **returns an open Stream and requires the caller to take closing responsibility**. Never return a lazy pipeline from a block that has already closed its source.

## 8. Handling Exceptions When Opening, Reading, and Closing Streams

I/O paths can fail at multiple stages:

1. **Opening the source:** `Files.lines(...)`, `Files.list(...)`, or `Files.walk(...)` can throw `IOException` upon initialization.
2. **Traversing the source:** deferred I/O operations can fail when the terminal operation requests elements. Several factories wrap checked errors into `UncheckedIOException` during traversal.
3. **Closing the source:** resource release or close handlers can raise errors.

Public method example:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countErrors(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
~~~

`throws IOException` covers checked errors when opening the source. If reading data during the terminal operation raises `UncheckedIOException`, the caller may need to handle that runtime exception separately. Do not swallow all errors and return 0, because that makes a broken file indistinguishable from a valid file with zero error lines.

An example of handling at the call site:

~~~java
try {
    long errors = countErrors(path);
    System.out.println("Errors: " + errors);
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Cannot read file: " + path);
    // Log/propagate error per application policy.
}
~~~

Do not catch every `RuntimeException` and blame it on I/O: a `NullPointerException` or bug inside a mapper/predicate is a different defect requiring separate investigation.

### Suppressed Exceptions on Close

If the `try` body already threw an exception and `close()` also throws an exception, Java retains the body exception as the **primary cause**, while the close exception is **attached** via `getSuppressed()`. This prevents losing track of the first failure.

~~~java
try (Stream<String> stream = Stream.of("A")
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {

    throw new IllegalArgumentException("processing failed");
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage()); // processing failed
    System.out.println(ex.getSuppressed().length); // 1
}
~~~

This illustrates the exception mechanism, not a recommendation to intentionally throw errors in close handlers. Using `try-with-resources` closes resources and preserves error details more accurately than manual `try/finally` blocks that overwrite earlier errors.

## 9. onClose: Attaching Cleanup Actions to the Stream Lifecycle

`BaseStream.onClose(Runnable closeHandler)` registers a task to run when `close()` is invoked on the Stream. Example:

~~~java
import java.util.stream.Stream;

try (Stream<String> words = Stream.of("Java", "Stream")
        .onClose(() -> System.out.println("Stream closed"))) {

    System.out.println(words.count()); // 2
} // Also prints "Stream closed"
~~~

Two key points:

- `count()` is a terminal operation; **it does not invoke close handlers itself**.
- The close handler runs when `try-with-resources` calls `close()` upon exiting the block.

`onClose` is useful when building a custom Stream with its own resource to clean up, or when recording close events for diagnostics. Close handlers execute in registration order. If one handler throws an exception, remaining handlers are still invoked; later exceptions may become suppressed exceptions.

**Do not abuse `onClose` to mutate business state** such as "order processed successfully." A Stream can close due to an exception or early pipeline termination, so "closed" does not mean "processed completely and successfully."

### Resources with Checked Exceptions in close()

`onClose` takes a `Runnable`, so a handler cannot directly declare throwing `IOException`. If you wrap an I/O resource in a Stream yourself, design error conversion and reporting clearly, such as using `UncheckedIOException` when appropriate. In simple cases, prefer source APIs that already manage closing like `Files.lines` and place the original resource directly in `try-with-resources`.

## 10. flatMap and Multiple Child Sources: Distinguishing Outer vs. Inner Streams

When using `flatMap`, each element of the outer Stream can produce a child Stream:

~~~java
outer.flatMap(item -> openChildStream(item))
~~~

By the `flatMap` contract, a child Stream returned by the mapper is **closed after its contents are placed into the pipeline**. This helps when each source element maps to a file to read.

However, do not infer that managing child Streams **replaces** the obligation to close the outer Stream or standalone I/O resources owned by the program.

Example concatenating the contents of two text files:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readAllFrom(List<Path> files) {
    return files.stream()
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .collect(Collectors.toList());
}
~~~

In this example, the outer Stream is `files.stream()` from a collection; the child Streams come from `Files.lines`. `flatMap` manages closing each child Stream per its contract during processing. If opening a file fails, the lambda converts `IOException` to `UncheckedIOException` to propagate the failure out of the pipeline.

For complex I/O tasks, many large files, or potentially blocking sources, you may prefer an explicit loop with `try-with-resources` per file for clearer control over errors, cancellation, and resource limits. Favor **clear resource lifecycles** over forcing a nested pipeline onto every scenario.

## 11. Closing the Source and Materialized Results Are Separate Things

When calling `collect` or `toList` inside a `try` scope, the finite result resides in memory. Closing the Stream afterward **does not erase** the created `List`.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> firstThreeLines(Path file) throws IOException {
    try (Stream<String> lines =
                 Files.lines(file, StandardCharsets.UTF_8)) {

        return lines.limit(3).collect(Collectors.toList());
    }
}
~~~

The method above returns the list of the first three lines after closing the source because `collect` finished inside the block. On the other hand, if you return an iterator, spliterator, or Stream created directly from an I/O source and traverse it only after the source closes, the caller will encounter an invalid state.

Since Java 16 you can use `lines.limit(3).toList()`, noting that `Stream.toList()` returns an unmodifiable list, whereas `Collectors.toList()` makes no specification guarantee about implementation type or mutability.

One more point: a Stream can contain **references to mutable objects**. Closing the source does not make those objects immutable or deep-copy them.

## 12. Single-Use Streams and No Reuse After close()

Logical lifecycle:

~~~text
OPEN SOURCE
   |
CREATE STREAM
   |
filter/map/flatMap/...  (usually lazy)
   |
terminal operation     (count, collect, findFirst, ...)
   |
CLOSE STREAM           (try-with-resources)
   |
DO NOT REUSE
~~~

You cannot invoke a second terminal operation on the same finished Stream:

~~~java
try (Stream<String> lines =
             Files.lines(file, StandardCharsets.UTF_8)) {

    long count = lines.count();
    // lines.findFirst(); // Wrong: Stream has already been used.
}
~~~

If two independent computations are needed, you can:

- Compute **multiple results in a single pass** using an appropriate collector.
- Collect a finite dataset into a List, then create multiple new Streams from the List if memory suffices.
- **Open a new I/O Stream** in another `try-with-resources` block if the source remains available and re-readable.

Example opening the file twice:

~~~java
long total;
long warnings;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    total = lines.count();
}

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    warnings = lines.filter(s -> s.startsWith("WARN")).count();
}
~~~

These are two different Streams and two separate file opens. In return, data could change between reads and I/O is performed twice; choose based on consistency requirements and cost.

## 13. Java 9+: Using Existing Resource Variables

Since Java 9, `try-with-resources` allows using a variable declared outside if it is `final` or *effectively final*:

~~~java
import java.util.stream.Stream;

Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8);

try (lines) {
    System.out.println(lines.findFirst().orElse("Empty file"));
}
~~~

After this block, the Stream is closed. In new code, declaring the resource directly inside the `try` parentheses usually makes **ownership easier to see**:

~~~java
try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    System.out.println(lines.findFirst().orElse("Empty file"));
}
~~~

Be especially careful when opening a resource **before** the `try` block: if another operation can throw an exception between opening and entering the `try` block, the program may skip closing. Best practice is to keep that gap nonexistent or declare directly in the resource specification.

## 14. Does Parallel Processing Change Closing Responsibility?

No. Example:

~~~java
long count;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    count = lines
            .parallel()
            .filter(line -> !line.isEmpty())
            .count();
}
~~~

`parallel()` only requests parallel execution mode for the pipeline; it **does not** cause the Stream to close automatically when the terminal operation finishes. The resource is still closed upon exiting `try-with-resources`.

For file data, parallelism can increase coordination, source-splitting, and I/O overhead. If mappers/predicates hold shared state, results also risk race conditions. Do not turn on `parallel()` merely hoping an I/O source will read faster. Evaluate Spliterator splittability, per-element processing cost, and benchmark with real sources.

Likewise, a custom gatherer or collector does not replace resource ownership: even when a pipeline processes fewer elements or stops early, **an open source still needs to be closed**.

## 15. Common Errors and Fixes Table

| Symptom | Cause | Solution |
| --- | --- | --- |
| Exhausting file handles when reading many files | Creating many `Files.lines` Streams without closing | Wrap the entire pipeline in `try-with-resources`. |
| `findFirst()` returned yet resource stays open | Short-circuiting terminal operation does not call `close()` | Close the Stream right after completion, ideally with `try-with-resources`. |
| Returning a Stream from a method but caller cannot traverse it | Stream closed before caller used it | Collect inside the block or transfer open Stream ownership to caller. |
| `BufferedReader.lines()` works but reader is never closed | Managing only the Stream, forgetting the underlying reader | Put `BufferedReader` in `try-with-resources`. |
| `try` block closes Stream before collector runs | Returning a lazy pipeline outside the resource scope | Run the terminal operation while the resource is open. |
| File traversal error not caught by `catch(IOException)` | Lazy I/O error raised as `UncheckedIOException` | Handle the exception types published by the source. |
| Close exception masks processing error | Closing manually and overwriting the prior error | Use `try-with-resources` and inspect `getSuppressed()` when needed. |
| Wrong results after reusing a Stream | A Stream supports only one pipeline | Create a new Stream from a re-readable source or design a single pass. |
| Infinite or huge source never completes | `collect` must process all emitted elements | Add a finite bound, process in batches, or change aggregation strategy. |
| Enabling `parallel()` spikes CPU/I/O | Coordination, splitting, and state overhead | Choose execution mode from benchmarks and lambda independence. |

## 16. Self-Check Exercises

### Exercise 1 — Identify Resources Needing Closing

~~~java
List<String> words = List.of("a", "b");

long x = words.stream().count();
long y = Files.lines(file).count();
~~~

**Question:** Which call needs redesigning to guarantee resource closing?

**Answer:** `Files.lines(file)`. It creates a Stream bound to an I/O source. Fix:

~~~java
long y;

try (Stream<String> lines = Files.lines(file)) {
    y = lines.count();
}
~~~

`words.stream()` from an in-memory list normally holds no I/O resources requiring closing.

### Exercise 2 — Does Short-Circuiting Free the File?

~~~java
Stream<String> lines = Files.lines(file);

boolean found = lines.anyMatch(s -> s.startsWith("ERROR"));
~~~

**Answer:** No. Although `anyMatch` stops early once a matching line is found, it does not close the Stream automatically. Use `try (Stream<String> lines = Files.lines(file)) { ... }` to guarantee closing.

### Exercise 3 — Why Is This Method Wrong?

~~~java
static Stream<String> read(Path file) throws IOException {
    try (Stream<String> stream = Files.lines(file)) {
        return stream.filter(s -> !s.isEmpty());
    }
}
~~~

**Answer:** `filter` is lazy; the method closes the Stream before the caller triggers a terminal operation. Either collect results into a `List` inside the block or return an open Stream and require the caller to use `try-with-resources`.

### Exercise 4 — Is a File Collected into a List Still Usable?

~~~java
List<String> cached;

try (Stream<String> lines = Files.lines(file)) {
    cached = lines.limit(10).collect(Collectors.toList());
}

System.out.println(cached.size());
~~~

**Answer:** Yes. The list was constructed before the source closed; the strings inside `cached` do not depend on the Stream to exist.

### Exercise 5 — I/O Error During Lazy Reading

**Question:** If `Files.lines` opens successfully but an error occurs while the terminal operation reads lines, does it always throw only a checked `IOException`?

**Answer:** No. Errors during lazy traversal can be wrapped into `UncheckedIOException`. Read the source contract and handle errors at the appropriate layer, while still using `try-with-resources` to close the source.

### Exercise 6 — Testing a Close Handler

~~~java
try (Stream<String> s = Stream.of("x")
        .onClose(() -> System.out.print("CLOSED"))) {

    s.findFirst();
}
~~~

**Question:** When is `CLOSED` printed?

**Answer:** Upon exiting the `try` block when Java calls `close()`. `findFirst()` by itself does not trigger the close handler.

## 17. Key Takeaways

- `Stream` implements `AutoCloseable` via `BaseStream`; closeable I/O resources are typically managed with `try-with-resources`.
- `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` are resource-backed Stream sources; enclose all processing within an explicit closing scope.
- Terminal operations such as `count`, `collect`, `findFirst`, and `anyMatch` **do not automatically close** the Stream.
- When using `BufferedReader.lines()`, manage the underlying **BufferedReader**; closing only the Stream does not guarantee closing the reader.
- Never return a closed lazy Stream; either return materialized data or transfer open Stream ownership to the caller.
- `try-with-resources` closes the resource on normal completion, `return`, or exception; close-time errors can be attached to the primary exception as suppressed.
- `onClose` can add close-time actions, but does not prove the pipeline finished or business processing succeeded.
- Early stopping, parallel execution, custom collectors, and Stream Gatherers do not remove the obligation to manage I/O sources.

**Main point:** With the Java Stream API, keep **when a pipeline finishes** separate from **when a resource is closed**. Any Stream reading from I/O must have a clear owner; `try-with-resources` is the default, verifiable way to ensure the source closes on time, even when processing stops early or encounters errors.
