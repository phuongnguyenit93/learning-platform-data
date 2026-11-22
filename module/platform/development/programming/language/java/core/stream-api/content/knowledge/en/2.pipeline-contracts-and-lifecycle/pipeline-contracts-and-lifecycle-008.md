# Consumption Lifecycle, Closing Streams, and Designing Stream-Providing Functions

In the Java Stream API, a `Stream` represents a **data-processing pipeline**, rather than a dataset that can be traversed again arbitrarily. Each pipeline is designed to execute **once**. If the source holds resources such as a file or directory, the program must also manage **when to close the resource**. These two responsibilities are related yet distinct: **consuming a Stream** is not the same as **closing a Stream**.

This lesson belongs to the **Pipeline Contracts and Lifecycle** chapter, focusing on how to use Streams safely in declarative processing: knowing when a pipeline is finished, identifying who owns the resource, and designing APIs that return Streams so callers know what they must do. These principles still apply when a pipeline combines `filter`, `map`, `reduce`, `collect`, runs in parallel, or has short-circuiting operations.

## 1. A pipeline has a single-use lifecycle

A typical pipeline consists of a **source**, **zero or more intermediate operations**, and a **terminal operation**:

```text
Source → filter(...)  →  map(...)     →  limit(...)   →  collect(...)
         intermediate    intermediate    intermediate    terminal
```

- **Source** creates a Stream from an array, collection, number sequence, file, or custom source.
- **Intermediate operations** such as `filter`, `map`, `sorted`, and `limit` are usually *lazy*: they declare how to process, without beginning element traversal immediately when attached to the pipeline.
- **Terminal operations** such as `count`, `findFirst`, `forEach`, `reduce`, or `collect` trigger processing if needed and end the right to use that pipeline. Some short-circuiting operations may stop before traversing the entire source.
- **Closing a Stream** via `close()` or `try-with-resources` marks the Stream as closed and runs registered cleanup tasks (if any). Closing by itself does not execute the whole pipeline.

Situations to distinguish:

| Moment | Can the same Stream be used again? | What to remember |
| --- | --- | --- |
| Newly created, no operations attached | Can continue building **one** pipeline | A Stream is used for only one processing chain |
| `filter`/`map` attached | Use the resulting Stream to continue building | Do not split multiple branches from the same source Stream |
| Terminal operation already called | **No** | To compute a second time, create a new Stream |
| `iterator()` or `spliterator()` already called | **Do not** reuse the pipeline | This retrieves a traversal object and also binds the pipeline for consumption |
| `close()` already called | **No** | Do not continue traversing or attaching new operations |

Incorrect reuse example:

```java
import java.util.stream.Stream;

Stream<String> names = Stream.of("An", "Binh", "Chi");
long total = names.count();       // Single allowed use: 3
long again = names.count();       // Usually throws IllegalStateException
```

Java may detect this and throw `IllegalStateException: stream has already been operated upon or closed`. However, the API contract requires **never reusing a Stream**; do not depend on every implementation detecting every misuse case.

To perform multiple independent analyses on the same collection, call `stream()` for each one:

```java
import java.util.List;

List<String> names = List.of("An", "Binh", "Chi");

long total = names.stream().count();
long longNames = names.stream()
        .filter(name -> name.length() >= 4)
        .count();
```

`names` is a collection that remains intact after each computation; the two `names.stream()` calls create **two separate pipelines**. Conversely, if data is read from a single-pass source, creating a new pipeline may require reopening the source or designing a dedicated buffer.

## 2. Consuming and closing are two separate events

`Stream` extends `BaseStream`, which implements `AutoCloseable`, so it works with `try-with-resources`. Yet **a terminal operation does not automatically call `close()`**. This is the most important distinction when a Stream is associated with external resources.

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

AtomicBoolean closed = new AtomicBoolean(false);
Stream<Integer> numbers = Stream.of(1, 2, 3)
        .onClose(() -> closed.set(true));

System.out.println(numbers.count());   // 3
System.out.println(closed.get());      // false: count() does not close the Stream

numbers.close();
System.out.println(closed.get());      // true: close() runs onClose
```

`onClose` registers an action to run **when closing the Stream**, not when reaching the terminal operation. Multiple handlers can be registered; they run in registration order, and Java still attempts to run remaining handlers if one throws an exception. Calling `close()` multiple times does not mean handlers run multiple times.

A helpful mental diagram:

```text
Create Stream ──► Build pipeline ──► Terminal operation ──► Consumed
      │                  │                   │                  │
      └──────────────────┴───────────────────┴──────────────────┘
                                close()
                                   │
                                   ▼
                           Closed / cleaned up
```

You can close a Stream **before** calling a terminal operation or **after** the terminal operation has finished. Closing early renders the pipeline unusable; closing afterward releases resources. With pure Streams from collections or arrays, there is normally no resource requiring closure; with I/O sources, closing is a real responsibility.

Also remember: `findFirst()`, `anyMatch()`, `limit()`, and short-circuiting operations may not traverse the entire source. Stopping traversal early **does not** release an opened file or directory. Likewise, a pipeline throwing an exception mid-way still needs to be closed.

## 3. Closing resource-holding Streams with try-with-resources

Methods such as `Files.lines(...)`, `Files.list(...)`, `Files.walk(...)`, and `Files.find(...)` return Streams tied to I/O resources. Those resources must be closed when no longer needed. The standard pattern is opening and processing within the same `try-with-resources` block.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countWarnings(Path logFile) throws IOException {
    try (Stream<String> lines =
                 Files.lines(logFile, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains("WARN"))
                .count();
    }
}
```

Here:

1. `Files.lines(...)` opens a file-reading source and returns a Stream that reads lines on demand.
2. `filter(...)` describes the condition; `count()` triggers processing.
3. Upon exiting the `try` block, even when an exception occurs, Java calls `lines.close()` to release the source's resources.

Using short-circuiting operations also requires closing:

```java
public static boolean hasFailure(Path logFile) throws IOException {
    try (Stream<String> lines = Files.lines(logFile)) {
        return lines.anyMatch(line -> line.contains("ERROR"));
    }
}
```

If `ERROR` is found on the first line, `anyMatch` can stop immediately, yet the Stream still closes at the end of the `try` block.

**I/O exceptions can happen at two points.** When opening `Files.lines`, an error may be reported via `IOException`; during lazy traversal, file-reading errors may be wrapped in `UncheckedIOException`. `try-with-resources` still runs the close operation when exiting the block. If both processing and closing throw exceptions, `try-with-resources` preserves the primary exception and records the close exception as a *suppressed exception*.

### The case of BufferedReader.lines()

Calling `close()` on just any Stream does not automatically close the external source. With `BufferedReader.lines()`, you must manage the **`BufferedReader` itself**:

```java
public static long countNonEmptyLines(Path file) throws IOException {
    try (var reader =
                 Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.isBlank())
                .count();
    }
}
```

General rule: check the close contract of **the source creating the Stream**. A Stream from `Files.lines` has built-in file closing; a Stream produced from an object that already owns a resource (such as `BufferedReader` or a database query cursor) may require closing the owner object separately or attaching a cleanup action via `onClose`.

## 4. Designing Stream-providing functions: who is responsible for closing?

When writing an API, the key decision is: **does the method finish processing data internally, or return the pipeline outside for the caller to process?** How you write it determines the resource's lifetime.

| API design | Who closes the resource? | Appropriate when |
| --- | --- | --- |
| `long countWarnings(Path)`, `List<T> load(Path)` | The implementing method | Simple interface, returning computed results |
| `Stream<String> openLines(Path)` | **The caller** | Caller needs to choose `filter`/`map`/`collect` themselves |
| `<R> R withLines(Path, Function<Stream<String>, R>)` | The implementing method | Want customizable processing while bounding the Stream's lifetime |
| `Supplier<Stream<T>>` or Stream factory | Each consumer must manage the created Stream | Need a **new pipeline** for each use |

### Approach A: Complete the pipeline and return the result

```java
import java.util.List;

public static List<String> loadWarnings(Path file) throws IOException {
    try (Stream<String> lines =
                 Files.lines(file, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains("WARN"))
                .toList();
    }
}
```

Data is materialized into a `List` before closing the file; the caller receives a result independent of the Stream's lifecycle. `Stream.toList()` exists since **Java 16**; on Java 8–15 you can use `collect(Collectors.toList())` (differences in list mutability guarantees should be considered when choosing).

Advantage: low risk of resource leaks, easy-to-use API. In return, results are held in memory; for large files, returning aggregated results (`count`, statistics `Map`, ...) instead of all lines may be preferable.

### Approach B: Return the Stream and transfer responsibility to the caller

```java
/**
 * Opens a Stream reading lines containing WARN.
 * The caller MUST close the returned Stream using try-with-resources.
 */
public static Stream<String> openWarnings(Path file) throws IOException {
    return Files.lines(file, StandardCharsets.UTF_8)
            .filter(line -> line.contains("WARN"));
}

// Caller side:
try (Stream<String> warnings = openWarnings(logFile)) {
    warnings.limit(10).forEach(System.out::println);
}
```

The `openWarnings` method opens the file without closing immediately, since the caller has not finished using the pipeline. Having `filter` create an intermediate Stream preserves the close handler of the pipeline containing the source. The caller closes the returned Stream to release resources.

**Never return an already-closed Stream from inside `try-with-resources`:**

```java
// WRONG: as soon as it returns, the try block ends and the Stream is closed.
public static Stream<String> brokenOpen(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines.filter(line -> !line.isBlank());
    }
}
```

Because the pipeline is lazy, the caller only starts traversing after the method returns, by which time the source has already been closed. Errors typically surface when the caller runs a terminal operation. The fix is using Approach A (returning computed results) or Approach B (returning an open Stream and clearly documenting the close obligation).

When a public API returns a resource-holding `Stream`, documentation should clearly state: **the caller needs to close it**, when the source is opened, exceptions that may arise during traversal, and whether the Stream can only be read once. The type `Stream<T>` alone does not tell callers whether it holds resources.

### Approach C: Accept a callback, keeping resource ownership inside the method

```java
import java.util.function.Function;

public static <R> R withLines(
        Path file,
        Function<? super Stream<String>, ? extends R> operation
) throws IOException {
    try (Stream<String> lines =
                 Files.lines(file, StandardCharsets.UTF_8)) {
        return operation.apply(lines);
    }
}

// User customizes the pipeline yet finishes processing within a safe scope:
long errors = withLines(
        logFile,
        lines -> lines.filter(line -> line.contains("ERROR")).count()
);
```

This design fits when you want flexibility while still guaranteeing resource closure before the method returns. The callback contract must require **consuming the Stream completely inside the callback**; do not return the Stream itself, an `Iterator`, a `Spliterator`, or a lambda capturing the Stream for later use, because by then the source is already closed. Java generics do not automatically forbid callbacks from returning such objects, so document the contract clearly and consider stricter APIs when needed.

### Approach D: Factory creating a new Stream for each traversal

Sometimes multiple queries need to run over the same data. Provide **a way to create a new Stream**, not a single Stream to use over and over.

```java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<String> events = List.of("INFO start", "WARN slow", "ERROR failed");
Supplier<Stream<String>> newStream = events::stream;

long warnings = newStream.get()
        .filter(s -> s.startsWith("WARN"))
        .count();

long errors = newStream.get()
        .filter(s -> s.startsWith("ERROR"))
        .count();
```

Conversely, `Supplier<Stream<String>> wrong = () -> existingStream;` only returns **the same Stream**, failing to solve the reuse error.

With file sources, opening anew may throw `IOException` (a checked exception). `Supplier.get()` declares no checked exceptions, so a specialized interface can be designed:

```java
@FunctionalInterface
interface IOStreamOpener<T> {
    Stream<T> open() throws IOException;
}

IOStreamOpener<String> opener =
        () -> Files.lines(logFile, StandardCharsets.UTF_8);

try (Stream<String> first = opener.open()) {
    System.out.println(first.count());
}
try (Stream<String> second = opener.open()) {
    System.out.println(second.findFirst().orElse("(empty)"));
}
```

**Each open is a separate Stream and a separate resource-management cycle.** Providing a factory does not promise that file contents remain immutable between two reads; results may change when the source changes.

## 5. Common real-world mistakes

| Usage pattern | Problem | How to handle |
| --- | --- | --- |
| `stream.count(); stream.findFirst();` | Reusing a consumed pipeline | Create a new Stream from the source |
| `Stream<String> s = Files.lines(path); s.findFirst();` without closing | Short-circuiting still leaves the resource open | Wrap the Stream in `try-with-resources` |
| `return stream.filter(...)` inside `try (stream)` | Caller receives a closed Stream | Return processed results or transfer close ownership to the caller |
| Returning `BufferedReader.lines()` after closing the reader | Pipeline reading from the reader is no longer usable | Keep the reader alive during processing or define an appropriate resource-owning API |
| `Supplier` always returns the same `Stream` variable | Fails to create a new pipeline | Have the factory **create** a Stream each time it is called |
| Relying on GC to close a file-reading Stream | No guarantee on when resources are released | Close explicitly, preferring `try-with-resources` |
| Using `peek` to clean up resources manually | `peek` may not run for every element; some operations have optimizations | Use `close` / `onClose` and resource-management blocks |

With `parallel()`, these rules still hold: a parallel Stream is also consumed only once, and terminal operations do not guarantee closing resources automatically. Do not share a single Stream instance across multiple threads operating concurrently.

## 6. Complete example: aggregating log levels from a large file

Suppose a file has lines formatted as `INFO started`, `WARN delayed`, `ERROR failed`. The requirement is to count lines by log level without loading the entire content into memory.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class LogStatistics {
    private LogStatistics() {}

    public static Map<String, Long> countByLevel(Path file)
            throws IOException {
        try (Stream<String> lines =
                     Files.lines(file, StandardCharsets.UTF_8)) {
            return lines
                    .map(String::strip)
                    .filter(line -> !line.isEmpty())
                    .map(line -> line.split("\\s+", 2)[0])
                    .collect(Collectors.groupingBy(
                            Function.identity(),
                            Collectors.counting()
                    ));
        }
    }
}
```

The pipeline traverses the source on demand; `collect` is the terminal operation; the result retains only counters for the log levels that appeared. When the method returns `Map<String, Long>`, the Stream has already been closed. The log-level extraction pattern here assumes the first token is the log-level name; more complex real-world log formats require an appropriate parser.

Through this example, three independent questions can be checked: **Who creates the pipeline?** The `countByLevel` method. **When is the pipeline consumed?** Inside `collect`. **Who closes the I/O source?** That same method, via `try-with-resources`.

## 7. Self-check questions

1. Does `count()` succeeding on `Files.lines(...)` guarantee the file has been closed? **No**; the Stream must be closed.
2. If `findFirst()` only takes one element, can `close()` be skipped? **No**, if the Stream owns a resource.
3. After calling `close()` with no terminal operation yet, can `collect()` be called? **No**; the Stream is already closed.
4. If a method returns a `Stream<T>` from a file, who must use `try-with-resources`? **The caller**, if the API transfers ownership and has documented the contract.
5. To process a collection three times, should you keep one `Stream` or call `collection.stream()` three times? **Create three independent Streams**.
6. Is returning a `List<T>` from inside `try-with-resources` safer than returning a `Stream<T>`? **Yes**, if the data has been fully materialized before closing and memory capacity is suitable.

**Rule of thumb:** Treat a Stream as a single-use processing session. Design method boundaries so the lifetime of both the Stream and source resources is clear: if processed inside the method, close inside the method; if returning a resource-holding Stream outside, explicitly state the caller's closing responsibility.
