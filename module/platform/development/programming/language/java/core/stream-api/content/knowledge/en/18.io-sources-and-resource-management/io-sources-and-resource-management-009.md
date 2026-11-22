# Avoiding Open Resource Leaks When Returning Streams or Combining Multiple Sources

The Stream API enables declarative data processing with lazy pipelines such as `filter`, `map`, `reduce`, and `collect`. However, **not every Stream lives solely in memory**. A `Stream<String>` created from `Files.lines(path)` or a `Stream<Path>` created from `Files.list(directory)` can hold a *file descriptor*, read channel, or directory handle. Calling a terminal operation without closing the Stream can leave the associated resource open. This bug is especially elusive when a method **returns an open Stream** or combines multiple I/O sources with `Stream.concat`.

This lesson belongs to the **I/O Sources and Resource Management** chapter of the **JAVA_STREAM_API** module. The goal is to distinguish data lifecycles from resource lifecycles, determine who owns closing responsibility, apply `try-with-resources` for both single pipelines and multiple sources, and choose patterns suited for performance, parallelism, and resource limits. Examples use Java 8 and later unless noted otherwise.

## 1. Distinguishing In-Memory Streams from Resource-Backed Streams

Both lines below return `Stream<String>`, yet they do not carry the same resource-management responsibilities:

```java
// In-memory source: no file handle is created by this statement.
Stream<String> names = Arrays.asList("An", "Bình").stream();

// File source: must close the Stream after use.
Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8);
```

Common I/O source methods:

| Source API | Created Stream object | Why closing is needed |
|---|---|---|
| `Files.lines(Path, Charset)` | `Stream<String>` of lines | Closes the file opened for reading |
| `Files.list(Path)` | `Stream<Path>` of direct directory entries | Releases directory-listing resources |
| `Files.walk(Path, ...)` | `Stream<Path>` across directory tree | Releases directory-tree traversal resources |
| `Files.find(Path, int, BiPredicate<...>, ...)` | `Stream<Path>` matching file search | Releases directory-tree traversal resources |
| `Collection.stream()` | Stream from a collection | The call itself does not open a file or directory |
| `Stream.of(...)`, `IntStream.range(...)` | Stream from in-memory values/ranges | Typically has no I/O resources to release |

For I/O-backed Streams, **close via `close()`**, typically using `try-with-resources`. That does not rule out in-memory Streams having `onClose` handlers or custom managed resources attached; read the contract of **the Stream-creating source** rather than guessing from `Stream<T>` alone.

### 1.1. Lazy Does Not Mean Deferred Resource Opening

`Files.lines(path)` sets up a file-backed Stream when the method is called. Intermediate operations such as `filter` and `map` normally run only at consumption time, yet **the I/O source may already be open before any terminal operation**:

```java
Stream<String> lines = Files.lines(path);
Stream<String> selected = lines.filter(line -> line.startsWith("ERROR"));
// count()/findFirst()/collect() not called yet, but the file may already be open.
```

Therefore, deferring pipeline consumption without proper closing still risks holding resources open. Laziness in element processing does not automatically manage file lifecycles.

## 2. Fundamental Rule: Open and Close in the Same Scope

The safe default is `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrors(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

The snippet above illustrates **a single method** (the final `}` closes the method); place imports at the top of the file when used in a complete class. `try-with-resources` guarantees `lines.close()` runs when leaving the block, even if the terminal operation throws an exception.

Lifecycle:

```text
try (open Files.lines source)
        |
        v
    filter/map/...       <- pipeline executes when terminal runs
        |
        v
    count/findFirst/...
        |
        v
close() from try-with-resources
        |
        v
file handle is released
```

### 2.1. Terminal Operations Do Not Imply Closing

`count()`, `findFirst()`, `forEach()`, or `collect()` **finish consuming the pipeline**, yet **do not guarantee closing a resource-backed Stream**:

```java
// AVOID: does not close the Stream returned by Files.lines.
long count = Files.lines(path).filter(s -> !s.isEmpty()).count();

// PREFER: closes even on errors.
try (Stream<String> lines = Files.lines(path)) {
    long safeCount = lines.filter(s -> !s.isEmpty()).count();
    System.out.println(safeCount);
}
```

In particular, **short-circuiting** terminal operations like `findFirst()` can stop after a few lines, while the file still must be closed:

```java
Optional<String> firstError;
try (Stream<String> lines = Files.lines(path)) {
    firstError = lines
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}
// By here the file is closed; firstError is a value detached from the source.
```

Short-circuit searching and resource release are **two separate responsibilities**.

### 2.2. onClose Is a Handler, Not an Auto-Close Mechanism

`Stream.onClose(Runnable)` registers an action to run **when the Stream is closed**. It does not make traversing the Stream call `close()` automatically:

```java
try (Stream<String> lines = Files.lines(path)
        .onClose(() -> System.out.println("Stream closed"))) {
    lines.limit(1).forEach(System.out::println);
}
// After leaving try: the onClose handler is invoked.
```

Do not use `onClose` as a replacement for `try-with-resources`. When a Stream has multiple handlers and an error occurs during closing, Java still attempts to run handlers per the close contract; additional errors may be recorded as *suppressed exceptions*. Avoid putting irreversible business actions inside handlers.

## 3. Mistake Number One: Returning a Stream Out of a Closed try Block

The following example is **unsafe**:

```java
// WRONG: returns a Stream object already closed by try-with-resources.
public static Stream<String> readLinesBroken(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank());
    }
}
```

The illustration uses `String.isBlank()`, which requires Java 11+. The resource-management bug **does not depend on** the filtering method: leaving `try` closes `lines`, so the caller receives a pipeline that is no longer valid to traverse. Attempting to consume it can throw `IllegalStateException` such as "stream has already been operated upon or closed".

To stay Java 8 compatible, the same mistake can be shown with `line -> !line.trim().isEmpty()`. Do **not** fix this by removing `try` and silently returning an open Stream: that merely shifts the leak risk onto the caller.

### 3.1. Returning an Open Stream: Only with Explicit Ownership Transfer

If you truly need an API returning a Stream so the caller can build its own pipeline, adopt the **caller owns stream** contract:

```java
/**
 * Opens a line-reading Stream. The caller MUST close the returned Stream.
 * Each call opens a separate I/O source.
 */
public static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

// Caller:
try (Stream<String> lines = openLines(path)) {
    lines
            .filter(line -> !line.trim().isEmpty())
            .forEach(System.out::println);
}
```

The key is that **nobody can "forget" ownership**:

- The Stream-creating method must state the closing obligation clearly in its API name, Javadoc, or contract.
- The caller must wrap **the entire consumption** in `try-with-resources`.
- Never store an open Stream in a long-lived field, cache it, or pass it across layers where none of those layers clearly owns closing it.
- Never return a Stream hoping the *garbage collector* or a terminal operation will close the file in time.

This is an acceptable option when an application API genuinely aims for **streaming**, though it is usually harder to use safely than an API returning computed data or accepting a callback.

## 4. Three Safe API Patterns for Returning Results from a Method

### 4.1. Pattern A: Finish Processing and Return Resource-Detached Results

When the data size fits comfortably in memory:

```java
public static List<String> loadErrors(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .collect(Collectors.toList());
    }
}
```

The caller receives a `List<String>` independent of any file handle. In return, the program allocates memory for all retained lines in the List. If the file is huge or contains many error lines, consider streaming aggregation/statistics instead of loading everything.

### 4.2. Pattern B: Accept a Processing Function and Execute Inside the Open-File Scope

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;
import java.util.stream.Stream;

public static <R> R withLines(
        Path path, Function<Stream<String>, R> operation)
        throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return operation.apply(lines);
    }
}

// Usage:
long count = withLines(path, lines ->
        lines.filter(line -> line.startsWith("ERROR")).count());
```

The callback pattern keeps **opening and closing in one place**, while still letting the caller decide how to compute over the Stream. The contract must specify that `operation` **consumes and finishes using the Stream right inside the callback**; it must not return the Stream itself, an iterator, or another lazy object still tied to the closed source.

If processing must return an asynchronous result like a `CompletableFuture` depending on the Stream, design a different lifecycle so the resource stays valid until work completes. Never assume a callback returning a Future has finished reading.

### 4.3. Pattern C: Transfer Ownership Explicitly

`openLines(path)` from section 3 fits when the caller needs multi-step lazy processing, provided it is documented and closing points are controlled. When only a count, collection, or statistical summary is needed, **Pattern A or B is usually less risky**.

| API style | Who closes? | Advantages | Risks / trade-offs |
|---|---|---|---|
| Return `List` / `Map` / metrics | Source method | Easy to use, hides handles | Can consume high RAM when materializing lots of data |
| `withLines(path, operation)` | Source method | Supports streaming, clear ownership | Callback must not let lazy objects escape |
| `openLines(path)` returns Stream | Caller | Allows external pipeline composition | Easy to leak if caller forgets to close |
| Return `Supplier<Stream<T>>` | Caller of each `get()` | Can defer when I/O opens | Each invocation must create and close its own Stream; does not reduce closing responsibility |

`Supplier<Stream<T>>` only expresses "how to open anew" and does not make a Stream self-closing. If you choose it, document the `try (Stream<T> s = supplier.get()) { ... }` usage pattern.

## 5. Combining Two Sources: Stream.concat Does Not Decide Lifecycles for You

`Stream.concat(first, second)` creates a **lazy concatenation** Stream: elements of `first` followed by elements of `second` (when both have encounter order). By the Java contract, **when the concatenated Stream is closed, the close handlers of both input Streams are also invoked**.

However, `concat` **does not auto-close just because `count()`, `findFirst()`, or `forEach()` finished**. And if you already called `Files.lines` to open both inputs, the second file may be open **even when processing stops inside the first file**.

### 5.1. Wrong Pattern: Open Two Sources, Concat, and Forget to Close

```java
// WRONG: both source Streams can retain file handles after the terminal operation.
long total = Stream.concat(
        Files.lines(firstPath),
        Files.lines(secondPath))
        .filter(line -> line.startsWith("ERROR"))
        .count();
```

Beyond leaking by not closing, there is a subtle bug: if opening `firstPath` succeeds but opening `secondPath` **throws `IOException`**, the first already-opened Stream may never be closed because `Stream.concat(...)` never finished constructing a result to manage.

### 5.2. Correct Pattern: Declare Both Sources in the Same try-with-resources

```java
public static long countErrorsInTwoFiles(
        Path firstPath, Path secondPath) throws IOException {
    try (Stream<String> first =
                 Files.lines(firstPath, StandardCharsets.UTF_8);
         Stream<String> second =
                 Files.lines(secondPath, StandardCharsets.UTF_8);
         Stream<String> combined = Stream.concat(first, second)) {

        return combined
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

Benefits:

- If opening the second file fails, `try-with-resources` closes the first file that opened successfully.
- Upon completion or exception, resources are closed **in reverse declaration order**.
- Closing `combined` closes its inputs; afterward `try-with-resources` also closes `second` and `first`. `Stream.close()` does not re-run close handlers already executed in an earlier close, so this layered protection is safe and clarifies ownership when opening fails.
- If you only need to open two sources and process them in the same scope, you can keep `first` and `second` in `try` without declaring `combined` as a separate resource; both still must be closed.

**Do not rely on Stream closing order as business-logic order.** Closing resources is cleanup work, not a guarantee of execution order for `filter` or `map`.

### 5.3. Short-Circuiting Still Must Close Both

```java
public static Optional<String> firstErrorFromTwoFiles(
        Path firstPath, Path secondPath) throws IOException {
    try (Stream<String> first = Files.lines(firstPath);
         Stream<String> second = Files.lines(secondPath);
         Stream<String> combined = Stream.concat(first, second)) {

        return combined
                .filter(line -> line.startsWith("ERROR"))
                .findFirst();
    }
}
```

If the first error element is inside the first file, `findFirst` can terminate early without reading the second file's contents. **The second file may still have been opened** because `Files.lines(secondPath)` was called when setting up the pipeline. `try-with-resources` releases both regardless of which file was read.

## 6. Complete Java 8 Example: Create Two Temp Files, Concat Sources, and Clean Up

The program below creates two temporary files for self-verifying sample data, counts lines starting with `ERROR`, finds the first error line, and deletes the temporary files in `finally` blocks. The example uses only Java 8+ with no external libraries.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Optional;
import java.util.stream.Stream;

public class MultiFileResourceDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;

    static long countErrors(Path a, Path b) throws IOException {
        try (Stream<String> first = Files.lines(a, UTF8);
             Stream<String> second = Files.lines(b, UTF8);
             Stream<String> joined = Stream.concat(first, second)) {

            return joined
                    .filter(line -> line.startsWith("ERROR"))
                    .count();
        }
    }

    static Optional<String> firstError(Path a, Path b)
            throws IOException {
        try (Stream<String> first = Files.lines(a, UTF8);
             Stream<String> second = Files.lines(b, UTF8);
             Stream<String> joined = Stream.concat(first, second)) {

            return joined
                    .filter(line -> line.startsWith("ERROR"))
                    .findFirst();
        }
    }

    public static void main(String[] args) throws IOException {
        Path a = Files.createTempFile("stream-logs-a-", ".txt");
        try {
            Path b = Files.createTempFile("stream-logs-b-", ".txt");
            try {
                Files.write(a,
                        Arrays.asList("INFO begin", "ERROR first"),
                        UTF8);
                Files.write(b,
                        Arrays.asList("ERROR second", "INFO end"),
                        UTF8);

                System.out.println(countErrors(a, b)); // 2
                System.out.println(
                        firstError(a, b).orElse("(none)"));
                // ERROR first
            } finally {
                Files.deleteIfExists(b);
            }
        } finally {
            Files.deleteIfExists(a);
        }
    }
}
```

Points to note:

1. `Files.lines` opens a **new source** each time `countErrors` or `firstError` is called. A consumed Stream cannot be reused.
2. `Stream.concat` preserves the order file A then B when both Streams are ordered. Thus `findFirst` picks `ERROR first`.
3. Both input sources and the concatenated Stream are managed in `try-with-resources`; early stopping never skips closing.
4. Both temporary files are deleted in separate `finally` blocks, even if writing or reading fails after file creation.
5. If a read operation fails during traversal, the runtime can throw `UncheckedIOException`; `try-with-resources` still closes resources during stack unwinding. Errors can be propagated rather than treated as empty results.

**Note:** creating *temporary files* in the example serves to prepare self-contained test data; in real applications, paths typically come from configuration or parameters. Do not open/write temporary files just to use `Stream.concat` when data is already in memory.

## 7. Combining Many Files: Avoid Opening All at Once

For two files, `Stream.concat` is simple. With hundreds or thousands of files, "open all `Files.lines` and concat them" can **keep too many file descriptors open**, including sources whose turn to be read has not arrived.

Instead, obtain a Stream of paths and `flatMap` each path to a Stream of lines:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrorsInDirectory(Path directory)
        throws IOException {
    try (Stream<Path> paths = Files.list(directory)) {
        return paths
                .filter(path -> path.getFileName()
                        .toString().endsWith(".log"))
                .filter(Files::isRegularFile)
                .flatMap(path -> {
                    try {
                        return Files.lines(path, StandardCharsets.UTF_8);
                    } catch (IOException e) {
                        throw new UncheckedIOException(
                                "Cannot open file: " + path, e);
                    }
                })
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

In this **sequential** pipeline:

- `Files.list(directory)` is the outermost I/O source and is closed via `try-with-resources`.
- `flatMap` opens a line Stream for each path only when its turn arrives. By the `Stream.flatMap` contract, child Streams produced by the mapper are closed after their contents are placed into the result stream.
- There is no need to accumulate all file contents into a `List` just to count error lines.
- `IOException` when **opening a file** inside the lambda must be converted into an unchecked exception like `UncheckedIOException`, because `Function<T, Stream<R>>` does not declare `throws IOException`.
- Read errors occurring **while traversing** `Files.lines` can also surface as `UncheckedIOException`. Do not swallow errors and treat an unreadable file as empty unless that is an explicit, documented business policy.

**Do not casually add `parallel()`** to the example above if your goal is limiting simultaneously open files. A parallel pipeline can invoke the mapper on many paths at once, increasing the number of concurrently open file streams and causing I/O contention. If parallelism is truly needed, cap concurrency, benchmark performance, and control handle counts under realistic load.

### 7.1. Processing Order of Files.list Is Not Guaranteed

`Files.list(directory)` makes no guarantee about entry ordering. If you want to combine files by name and then pick the **first error line**, define an ordering rule explicitly, for example:

```java
try (Stream<Path> paths = Files.list(directory)) {
    Optional<String> firstError = paths
            .filter(path -> path.getFileName().toString().endsWith(".log"))
            .filter(Files::isRegularFile)
            .sorted()
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            })
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}
```

`sorted()` applies the natural ordering of `Path`, which is the provider's path ordering; if business rules need custom ordering, pass an appropriate `Comparator<Path>`. Sorting carries time and memory cost proportional to the number of paths. `findFirst` on a sorted source means "first according to the chosen file order", not "earliest error chronologically" unless filenames and contents reflect that.

### 7.2. Do Not Concatenate Thousands of Streams with Deeply Nested concat Calls

A very deep chain of `Stream.concat(Stream.concat(...), ...)` creates a deep concat tree, adding overhead and, in extreme cases, risking `StackOverflowError` during traversal or closing. For many sources, the "Stream of paths -> `flatMap` to line Streams" pattern or a bounded sequential reader design manages resources much more cleanly.

## 8. Related Sources with Different Closing Contracts

### 8.1. BufferedReader.lines Does Not Govern BufferedReader Ownership

If you open a `BufferedReader` yourself, close the **reader** with `try-with-resources`. Never assume that merely calling `close()` on a Stream obtained from `reader.lines()` closes all reader resources the way `Files.lines` does:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static long countNonEmpty(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.trim().isEmpty())
                .count();
    }
}
```

Here, the I/O resource owner is `BufferedReader`. The Stream is used while the reader is open; exiting `try` closes the reader. Read exceptions raised while traversing the Stream can be wrapped in `UncheckedIOException`.

### 8.2. Files.walk and Files.find Also Require try-with-resources

`Files.walk` and `Files.find` can hold directory-traversal resources. Example:

```java
public static long countJavaFiles(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .count();
    }
}
```

This snippet does not limit depth or file count on its own. On large directory trees, consider depth limits, symbolic-link handling, and access permissions. Traversal can throw errors while running, not only at the `Files.walk` call.

### 8.3. Files.readAllLines Is Not Ideal for Every File

`Files.readAllLines(path)` reads the entire content into a list and does not return a Stream holding the file open for the caller. That can simplify resource lifecycles for small files, at the cost of **memory proportional to data size**. For large files, prefer streaming inside `try-with-resources` and aggregating incrementally instead of loading everything.

## 9. Exceptions During Processing and Closing

Resources can fail at three different stages:

| Stage | Example | How to handle |
|---|---|---|
| **Opening source** | `Files.lines(path)` throws `IOException` | Let `try-with-resources` close earlier sources that opened successfully |
| **Reading in pipeline** | I/O failure after several lines, possibly `UncheckedIOException` | Do not ignore errors accidentally; resources still must close |
| **Closing source** | Close handler or resource release fails | Log/propagate error properly; preserve primary error details |

Example handling and translating errors at an application boundary:

```java
public static long countOrReport(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> line.startsWith("ERROR")).count();
    } catch (UncheckedIOException e) {
        // Can occur when reading during terminal operation traversal.
        throw e.getCause();
    }
}
```

Corresponding imports are `java.io.IOException`, `java.io.UncheckedIOException`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.util.stream.Stream`. Exception handling must match the method contract; do not return `0` or `Optional.empty()` when reading fails unless business rules intentionally treat I/O failures as missing data.

### 9.1. Close in the Proper Scope Even When findFirst or limit Stops Early

`limit`, `findFirst`, and `anyMatch` can stop the pipeline before reading the whole file. That saves processing, yet **does not replace closing**. `try-with-resources` provides an explicit boundary ensuring resource release even on early stop or exception.

## 10. API Design, Performance, and Parallel Processing

Keeping sources open can exhaust *file descriptors*, block file deletion/renaming on some operating systems, and cause unpredictable system load. For in-memory sources, `parallelStream()` can help when CPU work is substantial; for many small I/O files, parallelism is not automatically faster because of open/close overhead, hardware limits, and resource contention.

Key principles:

1. **Define the owner** right at the I/O source-creating API. If returning a Stream, the caller must close it; if external streaming is unnecessary, prefer returning computed results or accepting a callback.
2. **Keep open scopes short and explicit**. Execute pipelines inside `try-with-resources`, and do not store open Streams in singletons or caches.
3. **Do not eagerly open every source** when only data from a few files is needed. When file counts are large, prefer opening on demand and closing each child Stream.
4. **Do not call `parallel()` to fix an I/O bottleneck** without benchmarking. Multiple workers may open many files simultaneously, exceeding handle limits.
5. **Control result counts**. `collect(toList())` retains all filtered data and can pressure RAM even if files close properly; `count`, `sum`, or summarizing collectors can use far less memory.
6. **Distinguish file ordering from line ordering**. `Stream.concat` on two ordered sources expresses "file A then file B"; `Files.list` promises no business file order.
7. **Avoid uncontrolled side effects** inside `filter`, `map`, or close handlers. Stream steps can be optimized or run in parallel; I/O operations must be designed around published contracts.

## 11. Common Mistakes

| Practice | Problem | Solution |
|---|---|---|
| Returning `Files.lines(path)` without stating who closes | Callers easily forget, leaving files open | Document caller ownership or switch to callback/computed result |
| `return lines.filter(...)` inside `try (lines)` | Returned Stream is already closed | Consume inside scope or return an open Stream with explicit close ownership |
| `Files.lines(path).count()` without `try` | Terminal operation does not auto-close | Use `try-with-resources` |
| Direct `Stream.concat(Files.lines(a), Files.lines(b))` | Can leak if opening the second source fails | Declare each source in `try-with-resources` before concat |
| `findFirst` without closing | Short-circuiting does not imply close | Close both sources with `try-with-resources` |
| Opening thousands of files before concatenating | Exhausts file descriptors | Open on demand using Stream<Path> and `flatMap` |
| Unbounded parallel `flatMap` | Many files open simultaneously | Limit concurrency or process sequentially |
| Assuming `onClose` runs automatically after `count` | Handler may never be called | Call `close` or use `try-with-resources` |
| Reusing a Stream after a terminal operation | `IllegalStateException` | Create a new Stream source for the next pass |
| Listing `Files.list` and relying on arbitrary file order | `findFirst` result is unstable functionally | Use `sorted`/Comparator before reading |
| Using `Files.readAllLines` on very large files | Increases memory footprint | Aggregate via Stream inside a closing scope |
| Catching all `UncheckedIOException` and returning empty result | Hides I/O failures | Report errors or apply an explicit fallback policy |

## 12. Self-Check Exercises

### Exercise 1. Stream Closed Too Early

```java
Stream<String> getLines(Path path) throws IOException {
    try (Stream<String> s = Files.lines(path)) {
        return s.filter(line -> line.startsWith("A"));
    }
}
```

**Question:** Why is this method wrong?

**Answer:** Before the caller receives the result, the `try-with-resources` block has closed `s`; the returned pipeline is no longer valid to traverse. Consume inside scope and return computed data, use a callback, or return an open source with a caller-must-close contract.

### Exercise 2. Does Early Stopping Replace Closing?

```java
Optional<String> value = Files.lines(path)
        .filter(line -> line.startsWith("ERROR"))
        .findFirst();
```

**Answer:** No. `findFirst` can stop early, yet it is not responsible for closing the file. Wrap the `Files.lines` source in `try-with-resources`.

### Exercise 3. Opening Two Files Before concat

If `Files.lines(a)` succeeds while `Files.lines(b)` throws `IOException` in `Stream.concat(Files.lines(a), Files.lines(b))`, what can happen?

**Answer:** File A is already open without a protective closing scope, creating a leak risk. Open A and B as consecutive resource declarations in the same `try-with-resources`; if B fails, Java closes A automatically.

### Exercise 4. Many Files and Handle Limits

Given a list of 10,000 log files, should you open all `Files.lines` and concat them, or take a Stream<Path> and `flatMap` to open each file as needed?

**Answer:** For sequential processing and limiting open files, open on demand with Stream<Path> and `flatMap`, while closing the outer Stream. Avoid enabling uncontrolled parallelism because it can increase simultaneously open sources.

### Exercise 5. Who Closes BufferedReader?

`BufferedReader reader = Files.newBufferedReader(path)` followed by `reader.lines().count()`. Can you rely on the terminal operation or only the Stream to close the reader?

**Answer:** No. Manage `BufferedReader` in `try-with-resources`; terminal operations have no contract to automatically close the reader.

### Exercise 6. Reading Two Sources, Returning One Result

Fix the following snippet to return the error line count while closing all sources:

```java
long total = Stream.concat(Files.lines(a), Files.lines(b))
        .filter(line -> line.startsWith("ERROR"))
        .count();
```

**Answer:**

```java
long total;
try (Stream<String> first = Files.lines(a);
     Stream<String> second = Files.lines(b);
     Stream<String> both = Stream.concat(first, second)) {
    total = both.filter(line -> line.startsWith("ERROR")).count();
}
```

If opening the second source fails, the first source still closes; if computation fails, both sources are released as well.

## 13. Checklist Before Returning or Combining I/O Streams

Before finalizing a method that processes files or directories, ask yourself:

1. **Which source is opening a file, read channel, reader, or directory handle?**
2. **Who owns closing?** Is there a `try-with-resources` block or an explicit caller-close contract?
3. **Is a Stream returned after its closing scope has ended?** Or conversely, returned open without anyone knowing to close it?
4. **If opening the second source fails, does the first source still close?**
5. **If the terminal operation stops early or throws an exception, does the source still close?**
6. **If the number of sources is huge, are all of them being opened too early?** Is concurrency bounded?
7. **If calling `findFirst` across multiple files, is file order explicitly defined?**
8. **If results must leave the method, can you return computed values instead of exposing a resource-backed Stream?**

**Key takeaway:** A `Stream` is an element-processing model; it **does not automatically replace I/O resource ownership**. When using `Files.lines`, `Files.list`, `Files.walk`, or `Files.find`, place opening and closing within one visible scope. With `Stream.concat`, protect each source as soon as it opens so later open failures are handled too. With many files, consider `flatMap` to open on demand rather than holding heaps of handles. Separating **data consumption**, **resource release**, and **error management** is the foundation for safe, accurate, and long-running Java Stream pipelines.
