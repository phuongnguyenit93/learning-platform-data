# Identifying Resource-Backed Streams and Closing Their Lifecycle Properly in Java 17

The Stream API processes data in pipelines: filtering, mapping, sorting, grouping, or computing results. However, not every stream is merely an in-memory sequence of elements. Some streams hold **external resources** such as files, directories, readers, or data sources with their own lifecycle. If they are not closed promptly, an application can hold file handles, directory handles, or connections longer than necessary.

In Java 17, the common `BaseStream` contract provides `close()` and `onClose(...)`. APIs such as `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` return streams backed by I/O resources; the caller must ensure the stream is closed. The most common approach is **try-with-resources**.

This lesson focuses on identifying resource-backed streams, understanding when a terminal operation finishes while resources remain open, closing via the proper owner, handling errors, and designing APIs that do not leak streams.

## 1. Not Every Stream Holds Resources

Both of the following examples return `Stream<String>`, yet their lifecycles differ:

~~~java
Stream<String> inMemory =
        List.of("An", "Bình", "Chi").stream();

Stream<String> fromFile = Files.lines(Path.of("names.txt"));
~~~

The first stream reads from an in-memory collection. It does not open a file or I/O connection. The second stream reads file contents and holds a file resource while the pipeline is active.

| Stream source | Has external resource to close? | How to handle |
| --- | --- | --- |
| `collection.stream()` | Typically no | No need for try-with-resources just to close the stream |
| `Arrays.stream(array)` | No | No need to close |
| `Stream.of(...)` | No | No need to close |
| `IntStream.range(...)` | No | No need to close |
| `Files.lines(path)` | Yes, reader/file | Close the stream |
| `Files.list(path)` | Yes, directory stream | Close the stream |
| `Files.walk(path)` | Yes, directory traversal | Close the stream |
| `Files.find(path, ...)` | Yes, directory traversal | Close the stream |
| `BufferedReader.lines()` | Reader used as source | Close the `BufferedReader` owning the reader |
| Stream from external API | Depends on API contract | Read documentation and close the proper resource owner |

The key point is that **the return type `Stream<T>` does not indicate whether a stream holds resources**. You must check the stream-creating API and its ownership contract.

## 2. Why Does a Terminal Operation Not Close the Stream Automatically?

A stream pipeline typically has two groups of operations:

- **Intermediate operations:** `filter`, `map`, `sorted`, `distinct`, `limit`, etc., create the next pipeline stage and are usually executed lazily.
- **Terminal operations:** `forEach`, `count`, `collect`, `toList`, `findFirst`, `anyMatch`, etc., trigger processing and consume the stream.

A common misconception is that after `count()` or `forEach()`, the stream automatically closes its resources. That is **incorrect**. A terminal operation consumes the pipeline; it does not replace calling `close()`.

~~~java
Stream<String> lines = Files.lines(Path.of("names.txt"));

long count = lines.count(); // Reads all data.
                                // The file stream still needs to be closed.
~~~

Even short-circuiting operations such as `findFirst()` or `anyMatch()` do not guarantee closing the stream:

~~~java
Stream<String> lines = Files.lines(Path.of("large.txt"));

Optional<String> first = lines.findFirst();
// Reads only what is needed; the resource still needs to be closed.
~~~

This is why resource-backed streams must be placed inside a lifecycle-management construct rather than relying on terminal operations to clean up.

## 3. Using try-with-resources with Files.lines

`Files.lines(Path)` returns a `Stream<String>` read lazily from a file. This stream holds a file-reading resource and **must be closed** after processing.

Example:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class ReadLinesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("names.txt");

        try (Stream<String> lines =
                     Files.lines(path, StandardCharsets.UTF_8)) {
            lines.filter(line -> !line.isBlank())
                    .map(String::strip)
                    .forEach(System.out::println);
        }
    }
}
~~~

When exiting the `try` block, even if the pipeline throws an exception, Java invokes `close()` on the stream. The close action of a stream from `Files.lines` closes the underlying reader and file resource.

Using an explicit charset such as `StandardCharsets.UTF_8` keeps file reading consistent across environments.

### 3.1. Collect Results Before Closing the File

If you need to return a list of what was read, run the terminal operation inside the resource-management block:

~~~java
static List<String> readAllLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.toList();
    }
}
~~~

`toList()` has existed since Java 16 and returns an unmodifiable list. After building the list, the stream is closed upon exiting the `try` block.

If a mutable list is needed, use an appropriate collector:

~~~java
static List<String> readMutableLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.collect(Collectors.toCollection(ArrayList::new));
    }
}
~~~

Returning a materialized collection keeps the API from shifting file-closing responsibility onto callers.

### 3.2. Handling IOException When Opening and UncheckedIOException When Reading

`Files.lines` may throw `IOException` when opening the file. Reading contents happens lazily during pipeline execution; if an I/O error occurs while reading, it may be wrapped in an `UncheckedIOException`.

~~~java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (IOException ex) {
    System.err.println("Cannot open or close file: " + ex.getMessage());
} catch (UncheckedIOException ex) {
    System.err.println("Error reading contents: " + ex.getMessage());
}
~~~

In real applications, handle exceptions at a layer with sufficient context to decide whether to retry, report the error, or abort processing. Never catch and ignore every exception, as doing so can mask data-reading failures.

## 4. Other Files Streams That Also Need Closing

`Files.lines` is not the only method that opens resources. Several other methods in `java.nio.file.Files` also return resource-backed streams.

### 4.1. Files.list: Listing One Directory Level

~~~java
try (Stream<Path> entries = Files.list(Path.of("data"))) {
    entries.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.list` returns a stream of direct entries in the directory. It does not recurse into subdirectories. The stream keeps the directory stream open until closed.

### 4.2. Files.walk: Traversing a Directory Tree

~~~java
try (Stream<Path> paths = Files.walk(Path.of("data"))) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.walk` traverses the directory tree depth-first. It may open multiple directories during traversal, so the stream must be closed to release resources.

If only one level is needed, use `Files.list`. If recursion is needed, use `Files.walk` and limit depth when appropriate:

~~~java
try (Stream<Path> paths = Files.walk(Path.of("data"), 2)) {
    paths.forEach(System.out::println);
}
~~~

The parameter `2` is the maximum depth from the starting directory according to the `Files.walk` contract.

### 4.3. Files.find: Traversing and Filtering by Attributes

~~~java
import java.nio.file.attribute.BasicFileAttributes;

try (Stream<Path> matches = Files.find(
        Path.of("data"),
        5,
        (path, attributes) ->
                attributes.isRegularFile()
                        && path.getFileName().toString().endsWith(".csv"))) {
    matches.forEach(System.out::println);
}
~~~

`Files.find` passes both the path and `BasicFileAttributes` to the predicate. It also returns a stream that must be closed after use.

### 4.4. Summary Table

| API | Scope | Resource to close |
| --- | --- | --- |
| `Files.lines(path)` | Lines in a file | Reader/file stream |
| `Files.list(directory)` | Direct entries of a directory | Directory stream |
| `Files.walk(start)` | Directory tree | Directory streams opened during traversal |
| `Files.find(start, depth, matcher)` | Directory tree with attribute predicate | Directory streams opened during traversal |

Do not skip try-with-resources merely because a terminal operation finished or only a single result was sought.

## 5. BufferedReader.lines(): Closing the Reader That Owns the Source

`BufferedReader.lines()` also returns a `Stream<String>`, but understand resource ownership clearly: `BufferedReader` is the object owning the reader/file.

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines()
            .filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

The try block manages `BufferedReader` and ensures `reader.close()` is called after the pipeline finishes. `BufferedReader.lines()` reads lazily from that reader; do not use the reader elsewhere concurrently while the stream's terminal operation is running.

Do not assume that closing an arbitrary stream created from `BufferedReader.lines()` will automatically close the reader. The `BufferedReader.lines()` API creates a stream to read from the reader; resource management responsibility still belongs to `BufferedReader`. Therefore, the clear pattern is keeping the reader in try-with-resources as shown.

### 5.1. Difference from Files.lines

| API | Stream reads from | What needs closing? |
| --- | --- | --- |
| `Files.lines(path)` | Reader created internally by the API | Close the returned stream |
| `reader.lines()` | `BufferedReader` created externally | Close the `BufferedReader` |

A practical guideline is using `Files.lines` directly when only a stream is needed. Use `BufferedReader` when other reader operations are needed, or when you want explicit application-level management of the reader.

## 6. Scanner and Other Readers with Their Own Lifecycles

`Scanner` has a `tokens()` method that creates a stream of tokens. `Scanner` is often created from a file, input stream, or reader; close scanners owned by the application.

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.Scanner;

try (Scanner scanner = new Scanner(Path.of("numbers.txt"), "UTF-8")) {
    scanner.tokens()
            .filter(token -> !token.isBlank())
            .forEach(System.out::println);
}
~~~

Closing a scanner closes the underlying source it manages, so exercise caution when a scanner wraps `System.in` or a shared stream. If the application does not own that underlying source, do not arbitrarily close it through a wrapper.

General principle: **close resources where they are owned or where ownership is explicitly transferred**. A stream view does not automatically tell you who owns the underlying file, socket, or reader.

## 7. Stream.close() and onClose(...)

`BaseStream` defines:

- `close()`: closes the stream and runs registered close handlers.
- `onClose(Runnable closeHandler)`: returns an equivalent stream with an additional action registered to run when the stream is closed.

Example with a custom stream:

~~~java
Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("Stream closed"));

try (stream) {
    stream.forEach(System.out::println);
}
~~~

Output:

~~~text
A
B
Stream closed
~~~

`onClose` is useful when building abstractions that must run cleanup when the caller closes the stream. However, registering a handler **does not make the handler run automatically when the terminal operation finishes**; `close()` or try-with-resources must still be used.

### 7.1. Close Handlers Do Not Replace Resource Ownership

Example:

~~~java
Stream<String> lines = Files.lines(path)
        .onClose(() -> audit("closed"));
~~~

When the stream is closed, the audit handler runs alongside closing the source stream. But if close is never called, the handler does not run either. Therefore, the stream must still be managed in try-with-resources.

### 7.2. Closing Multiple Times

`close()` is intended to close the pipeline; avoid calling it from multiple places or having unclear shared closing responsibility. Establish a single owner responsible for closing. When multiple components register cleanup, `onClose` attaches cleanup actions to the stream's lifecycle; ordering and exceptions across close handlers follow the `BaseStream` API contract.

## 8. What Does try-with-resources Guarantee?

The construct:

~~~java
try (Stream<String> stream = Files.lines(path)) {
    stream.filter(...).forEach(...);
}
~~~

guarantees `close()` is invoked upon exiting the block, whether:

- The pipeline completes normally.
- A predicate or mapper throws a runtime exception.
- A terminal operation throws an exception.
- A `return` statement or exception exits the block early.

This is the standard way to manage resources in Java. There is no need to write manual `finally` blocks to call close in normal scenarios.

### 8.1. Multiple Resources

Multiple resources can be declared in the same try statement:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8);
     Stream<String> lines = reader.lines()) {

    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

Resources are closed in reverse order of their declaration. In the example, the stream is closed first, then the reader is closed. Since `BufferedReader.lines()` does not transfer reader ownership to the stream, managing the reader in the same block remains essential.

### 8.2. Suppressed Exceptions

If the try body throws an exception and closing a resource also fails, Java preserves the exception from the try body as the primary exception; errors during closing are attached as suppressed exceptions. This prevents masking the original failure when cleanup also fails.

You can inspect suppressed exceptions via `getSuppressed()` when diagnosing issues. Normally, letting try-with-resources manage this process is sufficient.

## 9. Short-Circuiting and Early-Terminating Pipelines

Terminal operations such as `findFirst`, `findAny`, `anyMatch`, `allMatch`, and `noneMatch` can stop a pipeline before reading all data.

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Optional<String> firstError = lines
            .filter(line -> line.contains("ERROR"))
            .findFirst();

    firstError.ifPresent(System.out::println);
}
~~~

Once the first error line is found, the stream can stop reading early. Still, the file must be closed when exiting the try block.

Similarly, `limit(10)` is an intermediate operation; it caps the number of processed elements but does not close the stream itself:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.limit(10).forEach(System.out::println);
}
~~~

Do not use `limit` or `findFirst` as a substitute for closing. They control how much data is read, not resource lifecycle ownership.

## 10. Do Not Return an Already-Closed Stream

A common API design mistake is creating a stream inside try-with-resources and returning it:

~~~java
// Broken lifecycle:
static Stream<String> badRead(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank());
    }
}
~~~

As soon as the method exits, try-with-resources closes the stream. The caller receives an already-closed pipeline and cannot execute a terminal operation on it as expected.

There are two better design approaches.

### 10.1. Execute and Materialize Internally

~~~java
static List<String> readNames(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank())
                .map(String::strip)
                .toList();
    }
}
~~~

The method owns the file, processes the data, closes the stream, and returns an independent collection.

### 10.2. Return the Stream and Explicitly Transfer Closing Responsibility to the Caller

~~~java
static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path);
}
~~~

If you choose this design, the API contract must explicitly state that **the caller is responsible for closing the stream**. Usage:

~~~java
try (Stream<String> lines = openLines(path)) {
    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

Do not return a resource-backed stream from a public API without documenting ownership clearly. Callers can easily overlook that a terminal operation does not close the file.

## 11. flatMap and Child Streams

A special case is `flatMap`: when a mapper produces child streams, the Stream API guarantees each mapped stream is closed after its contents have been placed into the result stream.

Example reading multiple files:

~~~java
try (Stream<Path> files = Files.list(Path.of("logs"))) {
    long errorCount = files
            .filter(Files::isRegularFile)
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .filter(line -> line.contains("ERROR"))
            .count();

    System.out.println(errorCount);
}
~~~

In this pipeline:

- The outer stream from `Files.list` is closed by try-with-resources.
- Each child stream from `Files.lines` is closed by `flatMap` after its contents are consumed.
- If opening a child file fails, converting `IOException` to `UncheckedIOException` propagates it through the mapper.

This is a specific rule of `flatMap`; do not generalize it to "any child stream created anywhere closes automatically". If you create child streams in `map` and retain them as data, or store them in a collection, the caller must manage each stream's lifecycle per the source's contract.

When reading multiple files, also decide on the policy when one file fails to read: abort the whole pipeline, log the error and skip that file, or retry. Do not silently swallow I/O errors.

## 12. Do Not Use Parallel Streams to Bypass Resource Management

Resource-backed streams still need to be closed when processed in parallel:

~~~java
try (Stream<String> lines = Files.lines(path).parallel()) {
    long count = lines
            .filter(line -> line.contains("WARN"))
            .count();

    System.out.println(count);
}
~~~

`parallel()` changes how the pipeline executes; it does not eliminate the obligation to close the file. In addition, parallel execution can make action ordering nondeterministic and is not always faster, especially for I/O sources or small files.

Do not share a resource-backed stream to be consumed by multiple pipelines. A stream is for one pipeline and one terminal operation.

## 13. When Is a Stream Not Needed?

If you only need to read a small file completely into a list, `Files.readAllLines` can be simpler:

~~~java
List<String> lines =
        Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

This method manages opening and closing the file internally and returns the list of lines read. In exchange, the entire contents are loaded into memory.

If line-by-line processing with explicit control is needed, you can use `BufferedReader` and a loop:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        if (!line.isBlank()) {
            System.out.println(line);
        }
    }
}
~~~

Choose the API based on need:

| Need | Suggested API |
| --- | --- |
| Small file, need all lines in memory | `Files.readAllLines` |
| Lazy filter/map/reduce pipeline on a file | `Files.lines` inside try-with-resources |
| Sequential reading with step-by-step control | `BufferedReader` inside try-with-resources |
| List a single directory level | `Files.list` inside try-with-resources |
| Recursive traversal | `Files.walk` or `Files.find` inside try-with-resources |

## 14. Complete Example: Counting Errors Across Multiple Log Files

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class LogScanner {

    private LogScanner() {
    }

    public static long countErrors(Path directory) throws IOException {
        try (Stream<Path> files = Files.list(directory)) {
            return files
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName()
                            .toString().endsWith(".log"))
                    .flatMap(path -> readLines(path))
                    .filter(line -> line.contains("ERROR"))
                    .count();
        }
    }

    private static Stream<String> readLines(Path path) {
        try {
            return Files.lines(path, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Path.of("logs");
        System.out.println("Errors: " + countErrors(directory));
    }
}
~~~

In this example:

- `Files.list` creates the outer stream that must be closed.
- `Files.lines` creates a child stream for each file.
- `flatMap` consumes and closes each child stream per its contract.
- The outer stream is closed in try-with-resources.
- Opening a file can throw `IOException`, which is wrapped as `UncheckedIOException` to propagate through the mapper.

If you want to handle per-file failures independently and continue with remaining files, design an explicit error-handling branch instead of merely rethrowing a different exception. This example chooses the fail-fast policy where an error aborts the entire count.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| File remains locked after calling `count()` | Terminal operation does not close the stream automatically | Wrap the stream in try-with-resources |
| `findFirst()` finishes but the file stays open | Short-circuiting only stops reading | Close the stream after the terminal operation |
| Deleting/renaming a file fails on some OSes | File handle is still open | Ensure the resource-backed stream is closed |
| Method returns a stream, but caller fails when reading it | Stream was already closed when the method exited try | Return a collection or transfer closing ownership explicitly |
| Assuming every stream must be closed | Streams from collections/arrays generally hold no resources | Only manage close when the source or close handlers require it |
| `BufferedReader.lines()` leaks the reader | Owning reader was not closed | Put `BufferedReader` in try-with-resources |
| `Files.walk` does not release directories | Forgot to close the traversal stream | Use try-with-resources |
| I/O error surfaces in terminal operation as unchecked | Lazy reading causes errors during pipeline execution | Handle `UncheckedIOException` at an appropriate layer |
| Using parallel still keeps file handles open | `parallel()` does not manage resources | Close the stream as usual |
| Calling `onClose` alone does not run the handler | Handlers only run when close is invoked | Use try-with-resources or call close intentionally |
| Closing child streams in the wrong place | Misunderstanding source ownership | Read the API contract; note `flatMap`'s specific rule |

## 16. Practice Exercises

### Exercise 1 — Reading a File Safely

Write a method accepting a `Path` that uses `Files.lines` to count non-blank lines and return the count. Ensure the file stream is closed even if a predicate throws an error.

### Exercise 2 — Distinguishing Stream Sources

Create a stream from `List.of` and a stream from `Files.lines`. Explain which stream holds a file resource and why a terminal operation does not replace `close()`.

### Exercise 3 — Listing Directories

Use `Files.list` to print direct files in a directory. Then use `Files.walk` for recursive listing. Ensure both streams are closed.

### Exercise 4 — BufferedReader.lines

Create a `BufferedReader` via `Files.newBufferedReader` and call `lines()` to filter data. Manage the reader with try-with-resources and explain why the reader is the resource owner.

### Exercise 5 — Short-Circuiting

Use `Files.lines` to find the first line containing `ERROR` via `findFirst`. After finding it, ensure the resource is closed. Also test the case where no line matches.

### Exercise 6 — onClose

Create a stream with an `onClose` handler that logs a message. Run a terminal operation and observe that the handler has not run if close is not called; then add try-with-resources and observe cleanup.

### Exercise 7 — API Ownership

Write two methods: one returns a `List<String>` after reading and closing the file internally; the other returns a `Stream<String>` and documents clearly that the caller must close it. Compare the responsibilities of both sides.

## 17. Principles to Remember

- Identify the stream source before deciding whether closing is needed.
- `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` produce resource-backed streams; close them with try-with-resources.
- Terminal operations consume the pipeline but do not automatically guarantee resource release.
- `BufferedReader.lines()` reads from a reader; close the `BufferedReader` that owns the source.
- `onClose` registers cleanup, but cleanup only runs when the stream is closed.
- If a method returns a resource-backed stream, transfer closing responsibility to the caller explicitly.
- `flatMap` has a rule to close child streams after consumption; do not generalize that rule to all nested streams.
- Handle both errors when opening the source and errors occurring during lazy pipeline reading.

Proper stream lifecycle management helps Java 17 applications release file handles and related resources promptly, prevents leaks when pipelines terminate early or fail, and clarifies ownership between stream-producing APIs and stream consumers.
