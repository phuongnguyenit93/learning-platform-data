# Closing Sources on Early Termination or Pipeline Exceptions

## Objectives

When using the **Java Stream API** to process data declaratively, we typically chain `filter`, `map`, `reduce`, and `collect` into a pipeline and trigger execution with a terminal operation. For sources backed by files or directories, *lazy evaluation* brings an extra responsibility: **closing I/O resources whether the pipeline completes normally, stops early, or throws an exception**.

After this lesson, you can:

- Explain why `findFirst()`, `anyMatch()`, or `limit(...)` do not automatically close an open file.
- Scope `try-with-resources` properly so the source closes even on `return` or exceptions.
- Distinguish exceptions when opening the source from exceptions raised while the stream reads data lazily.
- Identify the actual resource that must be closed, even when a stream is created from a `BufferedReader`.
- Design methods that return results safely without leaking resources or returning an already-closed stream.

## 1. Finishing a Pipeline Differs from Closing a Resource

A Stream consists of a **data source**, intermediate operations, and a terminal operation. Most intermediate operations only describe how to process elements; data is pulled from the source when the terminal operation runs.

With `List.stream()` or `Stream.of(...)`, there is normally no OS resource to release. However, APIs like `Files.lines(...)`, `Files.list(...)`, or `Files.walk(...)` can hold files, directory streams, or OS handles open. Java Stream implements `AutoCloseable` so callers can explicitly close such sources.

```text
Open I/O source
    |
    v
Stream (may hold file descriptor / directory handle)
    |
    +--> filter / map / ... (lazy processing)
    |
    +--> terminal operation
             |
             +--> read all data
             +--> stop early (short-circuit)
             +--> throw exception
                         |
                         v
             No automatic close step here
                         |
                         v
             Close source with try-with-resources
```

A terminal operation **consumes** the pipeline; it does not implicitly call `Stream.close()`. Even when the end of the file has been reached, do not assume the resource has been closed. Therefore, manage the lifecycle of I/O sources explicitly.

| Stream source | Resource to manage | How to manage |
| --- | --- | --- |
| `Stream.of(...)`, `list.stream()` | Typically no I/O handle | No `try-with-resources` needed solely to close this source |
| `Files.lines(path)` | Open file for lazy reading | Close `Stream<String>` |
| `Files.list(dir)` | Directory-listing resource | Close `Stream<Path>` |
| `Files.walk(dir)`, `Files.find(...)` | Directory-tree traversal resource | Close `Stream<Path>` |
| `reader.lines()` from `BufferedReader` | `BufferedReader` itself owns the reading source | Close `BufferedReader`; do not rely solely on `Stream.close()` |

Practical rule: **whenever a source opens a resource, identify clearly who owns it and who closes it**. For a stream returned by an I/O API, read the API contract and usually wrap that stream in `try-with-resources`.

## 2. Early Termination Still Requires Closing the Source

Operations like `findFirst()`, `findAny()`, `anyMatch()`, `allMatch()`, and `noneMatch()` can stop after reading only part of the data. `limit(n)` and `takeWhile(...)` are *intermediate operations* that can cause downstream consumption to finish early. Whether early stopping actually occurs also depends on other pipeline stages; for example, `sorted()` typically needs to inspect the entire input before returning results.

Suppose we need to find the first line containing an error code in a large log file:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public class LogSearch {
    public static Optional<String> firstError(Path logFile) throws IOException {
        try (Stream<String> lines = Files.lines(logFile, StandardCharsets.UTF_8)) {
            return lines
                    .map(String::trim)
                    .filter(line -> line.contains("ERROR"))
                    .findFirst();
        }
    }
}
```

What happens?

1. `Files.lines(...)` opens the reading source and returns a closeable stream.
2. `map` and `filter` do not read the file yet; `findFirst()` triggers the pipeline.
3. Upon seeing the first error line, `findFirst()` can stop without reading the remainder.
4. When exiting the `try` block, Java calls `close()`, even when `return` appears inside.
5. The `Optional<String>` holds the already-fetched data, so it remains usable after the file closes.

**Counter-example – leaving the source open after early stopping:**

```java
// Avoid: terminal operations do not automatically close a Files.lines stream.
Optional<String> result = Files.lines(logFile, StandardCharsets.UTF_8)
        .filter(line -> line.contains("ERROR"))
        .findFirst();
```

The statement above may return the right result, yet it does not guarantee timely release of the file resource. If called repeatedly, the application can accumulate file descriptors/handles, fail to open files, or run into trouble renaming or deleting files on certain operating systems.

The same pattern applies when finding the first matching file in a directory tree:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public static Optional<Path> firstJavaFile(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .findFirst();
    }
}
```

When `findFirst()` stops early, tree traversal is left incomplete; closing the stream is essential to release the resources held by `Files.walk`. Do not assume returning `Optional<Path>` releases them.

## 3. Exceptions in the Pipeline Must Also Close the Source

Exceptions can originate from several places:

- **When opening the source:** `Files.lines(path)` or `Files.walk(path)` can throw `IOException`.
- **During lazy reading:** I/O errors occurring while the terminal operation consumes data are typically wrapped in `UncheckedIOException`.
- **In processing logic:** functions passed to `map`, `filter`, `forEach`, or collectors can throw runtime exceptions, such as `IllegalArgumentException`.
- **When closing:** resource-release operations or close handlers can also throw exceptions.

`try-with-resources` ensures `close()` is invoked upon exiting the block, even if a pipeline stage throws an exception:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countValidRecords(Path input) throws IOException {
    try (Stream<String> lines = Files.lines(input, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .map(line -> {
                    if (line.equals("INVALID")) {
                        throw new IllegalArgumentException("Invalid record");
                    }
                    return line;
                })
                .count();
    } // Stream closes even if count() throws IllegalArgumentException.
}
```

Important point: `catch` **is not a prerequisite for closing the resource**. `try-with-resources` closes automatically on exiting `try`. Add `catch` only when you need to translate, log, or handle exceptions at the appropriate layer.

For instance, to distinguish file-open errors from deferred read errors:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.count();
    } catch (UncheckedIOException ex) {
        // I/O error occurred while the stream was being consumed.
        throw ex.getCause();
    }
    // IOException when opening the source is already a checked exception,
    // declared via throws IOException in the method signature.
}
```

In practice, how specific APIs and operations read data can differ; do not assume all I/O errors in a pipeline surface as checked `IOException`. When comprehensive handling is needed, watch for `UncheckedIOException` during terminal operation execution as well.

### What If Both Processing and Closing Fail?

Suppose `map` throws an exception, and then `close()` also throws an exception while releasing the resource. With `try-with-resources`, the initial exception from the `try` body remains the primary exception; the close exception is typically recorded in the *suppressed exceptions* list, accessible via `getSuppressed()`. This preserves the original cause of failure.

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(line -> process(line));
} catch (RuntimeException ex) {
    System.err.println("Primary error: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Error closing resource: " + suppressed);
    }
    throw ex;
}
```

In this example, `process` is an application-provided processing function. If you catch and ignore exceptions, the program can mask business errors or I/O failures. Log sufficient context and let the appropriate layer decide recovery.

## 4. Closing the Right Resource-Owning Object

The object that needs closing is not always the `Stream` object.

### `Files.lines()`: the stream manages closing the source

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank()).forEach(System.out::println);
}
```

In this case, closing the stream from `Files.lines` matches the API contract.

### `BufferedReader.lines()`: close the reader

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static boolean hasHeader(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .anyMatch(line -> line.startsWith("HEADER:"));
    }
}
```

Here, `BufferedReader` itself is the resource to close. Do not assume calling `close()` on the stream produced by `reader.lines()` closes the reader. Wrapping `BufferedReader` in `try-with-resources` keeps ownership and close timing explicit, even when `anyMatch()` finishes early.

### What If a Method Creates a Stream for the Caller?

The following snippet risks leaks because closing ownership is not clearly established:

```java
// Avoid unless the API contract requires the caller to close the stream.
static Stream<String> errorLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> line.contains("ERROR"));
}
```

If the method needs to return ready-to-use results, consume the data while the source is open and return an independent value:

```java
static java.util.List<String> loadErrors(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains("ERROR"))
                .toList();
    }
}
```

If you genuinely need to return a lazy stream for external processing, the API must explicitly state **the caller owns closing responsibility** and the caller must use `try-with-resources`:

```java
try (Stream<String> errors = errorLines(path)) {
    errors.limit(10).forEach(System.out::println);
}
```

Never create a stream inside a `try` block, close the resource, and return that stream for later consumption: the lazy pipeline would attempt to access a closed source. Choosing between returning a `List` or a `Stream` with an explicit close contract depends on memory, latency, and large-data requirements.

## 5. `onClose()` Is Useful, But Does Not Trigger Automatically

`BaseStream.onClose(Runnable)` registers an action that runs **when the stream is closed**. It is helpful for logging, counting closes, or cleaning up auxiliary resources in a pipeline you build. However, `findFirst()`, `count()`, or `forEach()` do not invoke this close handler automatically.

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

AtomicBoolean closed = new AtomicBoolean(false);

try (Stream<Integer> numbers = Stream.of(10, 20, 30)
        .onClose(() -> closed.set(true))) {
    boolean found = numbers.anyMatch(number -> number == 10);
    System.out.println(found); // true: stops after matching the first element
}

System.out.println(closed.get()); // true: because try-with-resources called close()
```

This is a callback test example, not a simulation of an actual file descriptor. With `Files.lines`, `onClose` should only add necessary behavior; you still must ensure the stream closes via proper lifecycle management. If multiple close handlers throw exceptions, Java runs all handlers and can preserve secondary exceptions as suppressed.

## 6. Common Design Mistakes

| Situation | Problem | Correct practice |
| --- | --- | --- |
| Calling `Files.lines(...).findFirst()` directly | Stops early while source may stay open | Wrap source stream in `try-with-resources` |
| Thinking `forEach()` or `collect()` auto-closes | Terminal operations do not guarantee resource release | Close source even when reading all data |
| Calling `stream.close()` after the processing line | If processing throws, `close()` is skipped | Use `try-with-resources` |
| Wrapping `reader.lines()` without closing reader | May miss the true resource owner | Wrap `BufferedReader` in `try-with-resources` |
| Returning a stream created inside an exited `try` block | Caller receives a stream backed by a closed source | Return materialized results or transfer closing ownership to caller |
| Only catching `IOException` when reading with `Files.lines` | Lazy read errors can be wrapped in `UncheckedIOException` | Account for wrapped exceptions too |
| Using `parallel()` thinking closing happens automatically | Parallelism does not alter resource management contracts | Close source after terminal operation; review I/O cost |

Using `parallelStream()` or `stream.parallel()` does not change lifecycle rules: if a source holds resources, it still must be closed. Benchmark before parallelizing I/O because synchronization, disk reading, and error-handling overhead can outweigh any gains.

## 7. Practical Code-Review Checklist

When reviewing a pipeline that reads files or directories, ask yourself:

1. **Where does the source come from?** `Files.lines`, `Files.walk`, `BufferedReader`, or just an in-memory collection?
2. **Who owns the resource?** Is it the stream returned by the API, an underlying reader, or another object?
3. **Where does the terminal operation run?** Are `findFirst` and other early-stopping operations inside the `try-with-resources` scope?
4. **What if the pipeline throws an exception?** Is the resource still closed? Are lazy read errors reported in the expected form?
5. **Does the return value still need the resource?** Collected `String`, `Optional<String>`, and `List<String>` can outlive `close`; a lazy stream needs an explicit lifecycle.

Complete example combining early finding, resource closing, and lazy read-error handling:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public final class AuditLog {
    private AuditLog() {}

    public static Optional<String> firstWarning(Path file) throws IOException {
        try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
            return lines
                    .map(String::trim)
                    .filter(line -> line.startsWith("WARN"))
                    .findFirst();
        } catch (UncheckedIOException ex) {
            throw ex.getCause(); // restore I/O read error to throws IOException contract
        }
    }
}
```

This method suits large log files because it typically reads only up to the first `WARN` line, while still closing the source if no line matches or an exception occurs. Returning `Optional<String>` spares the caller from managing a file-backed stream.

**Key takeaway:** In the Java Stream API, *short-circuiting* determines how early **reading data** can stop; `try-with-resources` determines **when resources are closed**. The two mechanisms serve independent purposes and normally must be used together whenever a pipeline works with I/O sources.
