# Managing Child Stream Lifecycles in `flatMap` and `mapMulti`

## 1. The Problem: A Single Pipeline Can Own Multiple Resources

One of the strengths of **JAVA_STREAM_API** is declarative data processing: from a source, we chain `filter`, `map`, `flatMap`, `reduce`, and `collect` into a lazy pipeline. With in-memory lists, closing streams rarely attracts attention. However, when data comes from files, directories, sockets, or sources backed by system resources, **a stream is no longer just a sequence of values**.

Consider the requirement: find non-empty lines across multiple text files in a directory.

```text
Files.list(directory)   -> Stream<Path>         (source stream, holds directory resource)
       │
       ├── file-a.txt  -> Files.lines(a)        (child stream, holds file A resource)
       ├── file-b.txt  -> Files.lines(b)        (child stream, holds file B resource)
       └── file-c.txt  -> Files.lines(c)        (child stream, holds file C resource)
                                    │
                                    ▼
                              Stream<String>
                                    │
                         filter / limit / collect
```

We must answer **two distinct questions**:

1. **Who closes the source stream** created by `Files.list`?
2. **Who closes each child stream** created when opening the files?

When using `flatMap`, the API contract includes a mechanism to close child streams returned by the mapper. When using `mapMulti`, the mapper **does not return a child stream**; instead, it actively pushes each value through a `Consumer`. If the mapper opens a stream or another resource, **the mapper itself must arrange to close that resource**.

After this lesson, you can:

- Distinguish streams holding no resources from streams backed by I/O resources.
- Identify ownership and lifecycles of the source stream, child streams, and final results.
- Use `try-with-resources`, `BaseStream.close`, and `onClose` in the right places.
- Design `flatMap` with `Files.lines` and `mapMulti` with explicit resource lifecycles.
- Handle file open/read/close failures, including `IOException` and `UncheckedIOException`.
- Understand the effects of `limit`, `findFirst`, infinite sources, and parallel processing.
- Test both **return values** and **resource closing**, not just output data.

Examples use **JDK 17 or later** (`mapMulti` was added in JDK 16 and `Stream.toList()` in JDK 16). `flatMap` and `BaseStream.close` have existed since JDK 8.

## 2. Not Every `Stream` Needs to Be Closed

`Stream` extends `BaseStream`, and `BaseStream` extends `AutoCloseable`. Therefore, a stream has a `close()` method and can be used with `try-with-resources`. Still, **whether closing is needed depends on the source that created the stream**.

| Source | Has external resource to manage? | Typical usage |
| --- | --- | --- |
| `List.stream()`, `Set.stream()` | Usually no | No `try-with-resources` needed |
| `Stream.of(...)`, `IntStream.range(...)` | No, if only creating in-memory values | No need to close just because it is a Stream |
| `Files.lines(path)` | Yes: file-reading resource | Close stream or transfer closing responsibility per contract |
| `Files.list(directory)` | Yes: directory-listing resource | `try-with-resources` |
| `Files.walk(directory)`, `Files.find(...)` | Yes: file-tree traversal resource | `try-with-resources` |
| `BufferedReader.lines()` | Underlying reader still must be closed | Close **`BufferedReader`**; do not assume closing the stream closes the reader |
| Custom application stream with `onClose` | Depends on handlers and related resources | Clarify ownership with callers |

**Rule:** when calling an API that returns a stream, read the Javadoc of **the source-creating API**, not just the general Javadoc of `Stream`. A terminal operation such as `count()` or `toList()` **does not automatically call `close()` on the source stream**.

Correct example:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
```

`count()` consumes the pipeline; upon exiting the `try` block, `lines.close()` is invoked even if there are no lines or the terminal operation throws an error.

Conversely:

```java
// No try-with-resources needed for typical in-memory sources:
long count = java.util.List.of("Java", "Stream")
    .stream()
    .filter(s -> s.length() > 4)
    .count();
```

## 3. Understanding `close()` and `onClose()` Before Nesting Streams

### 3.1. `close()` Is Not a Terminal Operation

In the Java Stream API:

- `collect`, `count`, `findFirst`, and `forEach` are **terminal operations**: they trigger/consume the pipeline.
- `close()` is the action that **releases resources** and triggers registered close handlers.
- Finishing a terminal operation **does not mean** the stream is closed automatically.
- A closed stream cannot continue being processed as a new pipeline; to run again, open a new source.

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger closed = new AtomicInteger();
Stream<String> source = Stream.of("A", "B")
    .onClose(closed::incrementAndGet);

long count = source.count();
System.out.println(count);        // 2
System.out.println(closed.get()); // 0: count() does not auto-close.

source.close();
System.out.println(closed.get()); // 1
```

This example uses `AtomicInteger` solely to **observe the lifecycle in a test**, not to encourage placing external state into business mappers.

### 3.2. `onClose` Registers a Cleanup Action

`BaseStream.onClose(Runnable)` returns a stream with an attached close handler. When the stream closes, handlers run in registration order. If multiple handlers throw exceptions, subsequent exceptions can be attached to the initial exception as *suppressed exceptions*.

```java
import java.util.stream.Stream;

try (Stream<String> s = Stream.of("A", "B")
        .onClose(() -> System.out.println("Closed"))) {
    System.out.println(s.findFirst().orElse("Empty"));
}
// A
// Closed
```

`onClose` does not turn `count` or `findFirst` into auto-closing operations; `try-with-resources` in the example is what calls `close`.

### 3.3. With `BufferedReader.lines()`, the Owner Is the Reader

`BufferedReader.lines()` provides a stream reading from the reader, but does not transfer reader-closing ownership to the stream by default. The safe practice is to close **the reader itself**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countNonBlank(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
            .filter(line -> !line.isBlank())
            .count();
    }
}
```

With `Files.lines(path)`, the stream created by `Files` itself is the resource to close. Do not equate the two APIs simply because both return `Stream<String>`.

## 4. `flatMap`: Child Streams Are Closed by Contract

Simplified signature:

```java
<R> Stream<R> flatMap(
    Function<? super T, ? extends Stream<? extends R>> mapper
)
```

For each element `T`, the mapper produces a `Stream<R>`. `flatMap` flattens the elements of those child streams into a single returned stream.

**Special lifecycle rule:** the Javadoc specifies that **each child stream produced by the mapper is closed after its contents have been placed into the resulting stream**. This enables:

```java
files.stream()
    .flatMap(path -> openLines(path))
    .filter(line -> !line.isBlank())
    .toList();
```

Here `openLines(path)` must return **an open stream**. Once the child stream's contents are processed inside `flatMap`, the framework takes responsibility for closing that child stream. `files.stream()` from `List<Path>` typically holds no resources, so `try-with-resources` is not needed for the outer stream in this example.

Ownership diagram:

```text
Caller
  │
  ├── owns source Stream<Path> when Files.list / Files.walk creates it
  │       └── closed via try-with-resources
  │
  └── flatMap
          ├── mapper returns Stream<String> for file A (open)
          │       └── flatMap manages close of stream A
          ├── mapper returns Stream<String> for file B (open)
          │       └── flatMap manages close of stream B
          └── ...
```

### 4.1. Do Not Close the Child Stream Before Returning It

Anti-pattern:

```java
// WRONG: returns an already-closed stream.
paths.stream()
    .flatMap(path -> {
        try (Stream<String> lines = Files.lines(path)) {
            return lines;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    })
    .toList();
```

When the lambda returns `lines`, the `try-with-resources` block has already exited and the stream is closed before `flatMap` uses it. Traversal may throw `IllegalStateException` because the stream is closed. **Do not wrap a stream being returned to `flatMap` in a `try-with-resources` block that finishes inside the mapper.**

### 4.2. Do Not Open Child Streams and Abandon Closing Ownership

Another anti-pattern:

```java
// Broken resource management: retaining child streams in a List.
List<Stream<String>> childStreams = paths.stream()
    .map(path -> openLines(path))
    .toList();

// Child streams are neither managed by flatMap nor closed.
```

`map` only creates a `Stream<Stream<String>>`; it has no contract to **close each child stream** like `flatMap` does. If an application truly needs to store child streams separately, it must define an owner and close every opened stream, even on exceptions. Usually it is much simpler to use `flatMap` or a properly scoped `try-with-resources` loop.

## 5. Complete Example: Processing Multiple Files with `flatMap`

Suppose we want to scan all regular files in a directory and count the total number of non-blank lines. There are **two resource layers**:

1. `Files.list(directory)` creates the source stream holding the directory-listing resource.
2. `Files.lines(file)` creates a child stream holding a file-reading resource.

Complete code, runnable on **JDK 17+**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class FileLinePipelines {

    private FileLinePipelines() {}

    static Stream<String> openLinesUnchecked(Path path) {
        try {
            // Transfer management of the open stream to the caller.
            return Files.lines(path, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException("Cannot open: " + path, ex);
        }
    }

    public static long countFlatMap(Path directory) throws IOException {
        // Caller owns the directory stream.
        try (Stream<Path> paths = Files.list(directory)) {
            return paths
                .filter(Files::isRegularFile)
                .flatMap(FileLinePipelines::openLinesUnchecked)
                // flatMap manages close of each Files.lines stream.
                .map(String::strip)
                .filter(line -> !line.isEmpty())
                .count();
        }
    }

    public static long countMapMulti(Path directory) throws IOException {
        try (Stream<Path> paths = Files.list(directory)) {
            return paths
                .filter(Files::isRegularFile)
                .<String>mapMulti((path, emit) -> {
                    // mapMulti does NOT close streams on the mapper's behalf.
                    try (Stream<String> lines = openLinesUnchecked(path)) {
                        lines.forEachOrdered(emit);
                    }
                })
                .map(String::strip)
                .filter(line -> !line.isEmpty())
                .count();
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Usage: java FileLinePipelines <directory>");
            return;
        }

        Path directory = Path.of(args[0]);
        System.out.println("flatMap = " + countFlatMap(directory));
        System.out.println("mapMulti = " + countMapMulti(directory));
    }
}
```

The two methods produce the **same semantic result** for unchanged file sources and identical reading policies: each non-blank line contributes one to the count. However, **resource lifecycles and early-stop capability inside files** differ.

In this example:

- `Files.list` can emit `Path` values in unspecified order. Because we are only counting, this does not affect the result.
- `Files.isRegularFile` checks only at call time; a file can still change, be deleted, or lose permissions before being opened.
- `openLinesUnchecked` is used because the lambda cannot declare `throws IOException`; it does not swallow errors.
- If reading a file fails while the terminal operation traverses, the exception may be `UncheckedIOException`; the directory stream is still closed upon exiting `try`.
- The example processes **direct files in the directory**, not recursively. To traverse a directory tree, you can use `Files.walk`, while still closing the source stream just like `Files.list`.
- The example imposes no file order to avoid sorting overhead when only a count is needed.

## 6. Why Does `mapMulti` Have Different Management Rules?

`Stream.mapMulti` was added in **JDK 16**, with signature:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Unlike `flatMap`:

- `flatMap` requires the mapper to **return a `Stream<R>`**.
- `mapMulti` gives the mapper a `Consumer<R>` with any chosen name (e.g., `emit`, `downstream`). The mapper calls `emit.accept(value)` **zero, one, or many times** to push values.
- The `mapMulti` mapper returns `void`, so **no child stream object is handed to the framework to close under the `flatMap` contract**.

In-memory example:

```java
import java.util.List;

List<List<String>> groups = List.of(
    List.of("Java", "Stream"),
    List.of(),
    List.of("API")
);

List<String> values = groups.stream()
    .<String>mapMulti((group, emit) -> group.forEach(emit))
    .toList();

System.out.println(values); // [Java, Stream, API]
```

With an in-memory `List`, there are no special I/O resources. However, when the mapper opens `Files.lines`, `BufferedReader`, or a custom resource, **the mapper must own and close it itself**.

### 6.1. Standard Pattern for `mapMulti` with I/O Sources

```java
paths.stream()
    .<String>mapMulti((path, emit) -> {
        try (Stream<String> lines = openLinesUnchecked(path)) {
            lines.forEachOrdered(emit);
        }
    })
    .toList();
```

Here `try-with-resources` is **correct** because the mapper emits all lines **right inside its own invocation**, rather than returning an open stream for deferred processing. Whether `forEachOrdered` finishes normally or throws an exception, `lines` is closed upon exiting `try`.

### 6.2. Do Not Retain `emit` for Use Outside the Mapper

The `Consumer<R>` passed into `mapMulti` is strictly for emitting results **within the mapper's execution scope**. Do not store the consumer in a global variable, invoke it from an asynchronous callback after the mapper has returned, or launch a background task that reuses it.

Misuse pattern:

```java
// Do not do this: retaining the Consumer provided by mapMulti to emit values later.
// savedConsumers.add(emit);
// asyncExecutor.submit(() -> emit.accept("late"));
```

If data comes from an asynchronous source, you need a dedicated async and backpressure model. `mapMulti` does not turn the Java Stream API into a reactive-streams API.

## 7. `flatMap` vs. `mapMulti`: When to Choose Which?

| Criterion | `flatMap` | `mapMulti` |
| --- | --- | --- |
| Mapper returns | `Stream<R>` | `void`; emits via `Consumer<R>` |
| One-to-many mapping | Expressed as a child stream | Expressed as calls to `emit.accept` |
| Child stream closed by framework? | Yes, per `flatMap` contract | No child stream returned |
| Opening a file inside mapper | Return open `Files.lines`; let `flatMap` close it | Use `try-with-resources` inside mapper |
| Downstream early stop | Can cooperate with child stream traversal | No early-stop signal passed directly into mapper's push loop |
| Representing large I/O sources | Natural when an API returns `Stream<R>` | Requires manual loop control and resource closing |
| Emitting few values / avoiding child streams | Can create many small streams | Can be more convenient |
| Guaranteed always faster? | No | No |
| Version introduced | Java 8 | JDK 16 |

**Performance note:** Javadoc notes that the default implementation of `mapMulti` may use a buffer and call `flatMap` internally. Therefore, claiming "`mapMulti` definitely performs zero allocations" or "`mapMulti` is always faster" is unfounded. Benchmark on your actual JDK, data source, and terminal operation.

## 8. `limit`, `findFirst`, and Early Stopping: An Important Difference

In a pipeline with a **short-circuiting** terminal operation or intermediate operation like `limit`, reading all data may not be necessary. Yet how elements are produced affects how much work can be saved.

### 8.1. `flatMap` Can Support Stopping Once Downstream Has Enough

```java
import java.util.List;

List<String> firstThree = paths.stream()
    .flatMap(FileLinePipelines::openLinesUnchecked)
    .limit(3)
    .toList();
```

In a sequential pipeline, `limit(3)` does not require reading all lines from every file: once three elements are obtained, the pipeline can stop. **Do not write tests asserting the exact number of mapper/reader invocations**, since traversal details and optimizations can vary across JDKs or parallel mode.

If `paths` actually comes from `Files.list`, the caller must still ensure **the directory stream** is closed via `try-with-resources`. Completing `limit` does not close the outer stream.

### 8.2. `mapMulti` May Consume an Entire Child Source Before the Limit Takes Effect

Example:

```java
import java.util.List;

List<String> firstThree = paths.stream()
    .<String>mapMulti((path, emit) -> {
        try (Stream<String> lines =
                 FileLinePipelines.openLinesUnchecked(path)) {
            lines.forEachOrdered(emit);
        }
    })
    .limit(3)
    .toList();
```

`lines.forEachOrdered(emit)` means the mapper actively iterates over lines of the open file. `mapMulti` gives the mapper no standard API to ask "has downstream already received three elements?". Therefore, **do not expect `limit(3)` to stop the `forEachOrdered` loop from reading further inside the current file**. For a huge file, that can waste substantial I/O.

Everything is still closed by `try-with-resources`, but **proper closing does not equate to economical reading**.

### 8.3. Source Ordering and "First" Results

`Files.list(directory)` does not guarantee path ordering. Thus, "the first three lines in the directory" is ambiguous without specifying file ordering.

If **ascending filename** order is needed, you can add:

```java
try (Stream<Path> paths = Files.list(directory)) {
    List<String> firstThree = paths
        .filter(Files::isRegularFile)
        .sorted(java.util.Comparator.comparing(
            path -> path.getFileName().toString()
        ))
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .limit(3)
        .toList();
}
```

`sorted` must be able to sort the paths, so it may need to buffer all paths before emitting any element. Weigh the cost if the directory is very large. Also distinguish filename order, timestamp order, and line order within each file.

### 8.4. Infinite Sources

If a `mapMulti` mapper runs a **never-ending loop** calling `emit.accept`, a downstream `limit` **is not guaranteed to save** the pipeline from getting stuck inside the mapper. In standard patterns, `flatMap` with a short-circuitable child stream is better suited for very long or potentially infinite sources, while still honoring the source's resource contract and ensuring the terminal operation can terminate.

## 9. Exceptions: Opening, Traversing, and Closing Are Three Distinct Moments

I/O APIs can fail at **multiple stages**:

1. **Opening the source:** `Files.list` or `Files.lines` can throw a checked `IOException`.
2. **Traversing the source:** an already-open stream can fail while reading; I/O errors during traversal may appear as `UncheckedIOException`.
3. **Closing the source:** resource release can fail; `try-with-resources` still handles exceptions and suppressed exceptions.

`Function`/`BiConsumer` signatures in the Stream API **do not declare `throws IOException`**, so this snippet will not compile:

```java
// Does not compile: Files.lines declares checked IOException.
// paths.stream().flatMap(path -> Files.lines(path)).count();
```

An adapter method can convert open errors into `UncheckedIOException`:

```java
static Stream<String> openLinesUnchecked(Path path) {
    try {
        return Files.lines(path, StandardCharsets.UTF_8);
    } catch (IOException ex) {
        throw new UncheckedIOException("Cannot open: " + path, ex);
    }
}
```

**Do not swallow I/O errors by returning `Stream.empty()`** when the business contract requires complete data. Doing so can cause reports to appear successful while silently omitting an entire file.

Distinguish two designs:

- **Fail fast:** if a file cannot be read, the aggregation fails with an exception preserving the cause.
- **Best effort:** the application accepts skipping unreadable files, but must **record the path, reason, and failed-file count** in an explicit result type. Deciding to skip errors belongs to the business layer, not as an implicit default of `flatMap` or `mapMulti`.

### 9.1. `try-with-resources` Protects Error Paths

```java
try (Stream<Path> files = Files.list(directory)) {
    return files
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .filter(line -> !line.isBlank())
        .count();
}
```

If reading one file throws an exception, the `try` block still closes the directory stream. Child streams are managed by `flatMap` per its contract; avoid attaching an extra external manual close mechanism to the same child stream in a way that creates ambiguous ownership.

### 9.2. When Opening Multiple Resources in One Mapper

Suppose a mapper must open **both a reader and another resource**, and only then create a stream. If opening the first resource succeeds but opening the second fails, the mapper must close the already-opened resource. Do not assume `flatMap` can clean up a resource that was never wrapped into the returned stream.

The pattern must be designed around ownership:

```java
// Idea: in mapMulti, close every resource right inside the lambda.
.<String>mapMulti((path, emit) -> {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        reader.lines().forEachOrdered(emit);
    } catch (IOException ex) {
        throw new UncheckedIOException("Cannot read: " + path, ex);
    }
})
```

The snippet above is **a continuation of a `Stream<Path>` pipeline**, not a standalone Java program. It closes `BufferedReader` rather than only closing `reader.lines()`; if a read error occurs later as an `UncheckedIOException`, the `try` block still closes the reader before the exception propagates outward.

## 10. Testing Child Stream Lifecycles with `onClose`

Testing that `toList` returns the right data is insufficient for I/O problems. A pipeline can return the right values while **leaking descriptors** or leaving the directory source unclosed.

To verify without creating real files, use `onClose` on simulated streams with test-only counters.

### 10.1. `flatMap` Closes Each Child Stream

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class StreamResourceLifecycleTest {

    @Test
    void flatMapClosesMappedStreams() {
        AtomicInteger childCloseCount = new AtomicInteger();

        List<String> result = List.of(1, 2, 3).stream()
            .flatMap(n -> Stream.of("N-" + n)
                .onClose(childCloseCount::incrementAndGet))
            .toList();

        assertEquals(List.of("N-1", "N-2", "N-3"), result);
        assertEquals(3, childCloseCount.get());
    }

    @Test
    void terminalOperationDoesNotCloseOuterSource() {
        AtomicInteger sourceClosed = new AtomicInteger();
        Stream<Integer> source = Stream.of(1, 2, 3)
            .onClose(sourceClosed::incrementAndGet);

        assertEquals(3L, source.count());
        assertEquals(0, sourceClosed.get());

        source.close();
        assertEquals(1, sourceClosed.get());
    }

    @Test
    void tryWithResourcesClosesOuterEvenAfterLimit() {
        AtomicInteger sourceClosed = new AtomicInteger();

        try (Stream<Integer> source = Stream.of(1, 2, 3)
                 .onClose(sourceClosed::incrementAndGet)) {
            assertEquals(
                List.of(1),
                source.limit(1).toList()
            );
        }

        assertEquals(1, sourceClosed.get());
    }

    @Test
    void mapMultiClosesResourcesOpenedByMapper() {
        AtomicInteger childCloseCount = new AtomicInteger();

        List<String> result = List.of(
            List.of("A", "B"),
            List.of("C")
        ).stream()
            .<String>mapMulti((items, emit) -> {
                try (Stream<String> child = items.stream()
                        .onClose(childCloseCount::incrementAndGet)) {
                    child.forEachOrdered(emit);
                }
            })
            .toList();

        assertEquals(List.of("A", "B", "C"), result);
        assertEquals(2, childCloseCount.get());
    }
}
```

These are **lifecycle tests**, not benchmarks. `AtomicInteger` observes close handlers after the pipeline finishes and does not participate in business output decisions. All test examples here use sequential, finite sources so expectations remain deterministic.

### 10.2. Testing When the Mapper Throws an Exception

With `mapMulti`, verify that resources still close even if emitting data fails:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class MapMultiFailureTest {

    @Test
    void closesChildIfMappingThrows() {
        AtomicInteger closed = new AtomicInteger();

        assertThrows(IllegalStateException.class, () ->
            List.of(1).stream()
                .<String>mapMulti((n, emit) -> {
                    try (Stream<String> child = Stream.of("A")
                            .onClose(closed::incrementAndGet)) {
                        child.forEachOrdered(emit);
                        throw new IllegalStateException("Test error");
                    }
                })
                .toList()
        );

        assertEquals(1, closed.get());
    }
}
```

When using real files, also add tests for empty files, missing files, locked files or insufficient permissions (OS-dependent), and read-time errors. **Never make tests depend on `Files.list` order**, because directory listing order is not guaranteed.

## 11. Design Bugs and Anti-Patterns to Avoid

### 11.1. Closing One Source While Forgetting the Other

```java
// Anti-pattern: Files.list is not placed inside try-with-resources.
// Files.list(directory)
//     .flatMap(FileLinePipelines::openLinesUnchecked)
//     .count();
```

`flatMap` is responsible for closing **child streams**, not for replacing closing **the outer `Files.list` source stream**. Place `Files.list` in the caller's `try-with-resources`.

### 11.2. Closing a Child Stream Too Early When Using `flatMap`

```java
// Returning a stream from inside try: the stream closes before use.
// .flatMap(path -> {
//     try (Stream<String> lines = openLinesUnchecked(path)) {
//         return lines;
//     }
// })
```

When you want the framework to close the child, return an **open** stream. When you want to close the resource **inside the mapper**, use `mapMulti`'s synchronous emission model or a direct processing loop.

### 11.3. Using `mapMulti` Without Closing Streams Opened Inside

```java
// Anti-pattern: creating an I/O stream inside the mapper without closing it.
// .<String>mapMulti((path, emit) -> {
//     Stream<String> lines = openLinesUnchecked(path);
//     lines.forEachOrdered(emit);
// })
```

Whether `forEachOrdered` finishes or throws, the code above never closes `lines`. Wrap every resource usage in `try-with-resources`.

### 11.4. Using `mapMulti` and Expecting Downstream `limit` to Prevent Reading the Whole File

A mapper like `lines.forEachOrdered(emit)` has no standard stop signal flowing from `limit` down into this loop. If taking just a few initial lines **without reading further** is important, `flatMap` is usually clearer for sources already modeled as `Stream<String>`.

### 11.5. Swallowing Every `IOException` as an Empty Stream

```java
// Dangerous anti-pattern for metric accuracy:
// .flatMap(path -> {
//     try { return Files.lines(path); }
//     catch (IOException ex) { return Stream.empty(); }
// })
```

An unreadable file is a source data error, not automatically equivalent to an empty file. If best-effort processing is acceptable, the report must expose the skipped-file count and reasons rather than silently marking data complete.

### 11.6. Opening Files Inside `peek` or a Mapper Purely for Side Effects

`peek` is meant for observation or conditional debugging, not mandatory I/O. The Stream API can optimize some pipelines, short-circuit, or run in parallel; do not rely on how many times `peek`/mappers run to ensure a file is processed or logged once. Business logic with side effects should be designed as tasks with explicit owners, success criteria, and error policies.

## 12. Parallel Processing: Resources Can Be Open Concurrently

`flatMap` or `mapMulti` can appear after `parallel()`:

```java
try (Stream<Path> paths = Files.list(directory)) {
    long result = paths.parallel()
        .filter(Files::isRegularFile)
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .filter(line -> !line.isBlank())
        .count();
}
```

At the API level, the pipeline may be valid, yet parallel I/O introduces practical concerns:

- Multiple mappers may **keep different file streams open simultaneously**, increasing descriptor and I/O resource counts.
- Large files, small files, local disks, and network filesystems behave very differently; parallel does not automatically speed things up.
- File-reading calls are blocking I/O; consider thread-pool configuration and actual system load.
- `Files.list` does not guarantee path ordering, and `forEach` on a parallel stream does not guarantee execution order.
- Mappers must not mutate the source collection or update unmanaged external mutable state. Count with `count`/collectors instead of mutating a shared `ArrayList` from `forEach`.
- A failure in one task can fail the pipeline and requires closing opened resources according to ownership; do not rely on exception ordering to deduce which file was processed last.

If you must bound the number of simultaneously open files or enforce strict processing order, a sequential pipeline may be more suitable. For complex I/O workloads, a dedicated concurrency coordinator may be needed instead of simply adding `parallel()`.

## 13. Performance and Memory: Choosing Tools Based on Source Shape

### 13.1. Creating a Child Stream vs. Pushing Directly

For purely in-memory data, `mapMulti` can be convenient when one element produces very few results:

```java
import java.util.List;

record Pair(String first, String second) {}

List<String> values = List.of(
    new Pair("A", "B"),
    new Pair("C", "D")
).stream()
    .<String>mapMulti((pair, emit) -> {
        emit.accept(pair.first());
        emit.accept(pair.second());
    })
    .toList();

System.out.println(values); // [A, B, C, D]
```

This avoids creating child streams at the mapper expression level. Still, the default implementation of `mapMulti` may buffer results; benchmark before claiming allocation wins.

### 13.2. For Large Files, Prefer Lazy Consumption

`Files.lines` creates a lazy line-reading stream. If only a small slice of data is needed, combining `flatMap` with `findFirst`, `limit`, or `takeWhile` can avoid scanning the entire file. With `mapMulti` calling `lines.forEachOrdered(emit)`, the mapper may scan the entire file to push values even when downstream needs far fewer.

Conversely, if business rules **require** processing every line of every file and emitting multiple object types per line, `mapMulti` can express 0-to-n logic cleanly, provided resources are closed in the right scope.

### 13.3. Holding All Lines in a `List` Can Consume High RAM

`toList()` materializes results. If you only need counts or aggregates, use `count`, `mapToLong`/`sum`, `reduce`, or summarizing collectors instead of holding all strings:

```java
try (Stream<Path> paths = Files.list(directory)) {
    long totalCharacters = paths
        .filter(Files::isRegularFile)
        .flatMap(FileLinePipelines::openLinesUnchecked)
        .mapToLong(String::length)
        .sum();
}
```

When using `Files.lines`, reducing result memory does not replace the responsibility to close files. Optimizing **state size**, **concurrent open files**, and **I/O read volume** are three distinct concerns.

## 14. Resource Ownership Review Checklist

Before putting a nested-stream pipeline into production, answer in order:

1. **Where does the source come from?** `List`, `Stream.of`, `Files.list`, `Files.walk`, `BufferedReader`, or a custom API?
2. **Are there resources that must be closed?** What does the Javadoc of the source-creating API say?
3. **Who is the owner?** The caller, `flatMap` for child streams, or the `mapMulti` mapper?
4. **When does the terminal operation stop?** Full traversal or `limit`/`findFirst`?
5. **Does early stopping close opened resources?** Are `try-with-resources` blocks in place on the source and appropriate mapper scopes?
6. **How are open, read, and close errors propagated?** Are errors being swallowed into empty data?
7. **Is the source ordered?** If taking the "first line", has file ordering been defined?
8. **Does the pipeline run in parallel?** Are concurrent open-file limits, ordering requirements, and benchmarks addressed?
9. **Must all results be retained?** Can an aggregating terminal operation replace `toList`?
10. **Are there lifecycle tests?** Not just value assertions; test closing and exception paths too.

## 15. Practice Exercises

### Exercise 1 — Properly Closing Two Resource Layers

Write a method taking `Path directory`, using `Files.list` and `flatMap` to read all text lines in regular files and count lines containing `"ERROR"`. Identify precisely:

- Which stream is closed by the caller with `try-with-resources`?
- Which streams are closed by `flatMap`?
- How is an `Files.lines` error converted to `UncheckedIOException`?

### Exercise 2 — Converting from `flatMap` to `mapMulti`

Rewrite Exercise 1 using `mapMulti`. You must place `Files.lines` inside `try-with-resources` right inside the mapper and emit lines only within that scope. Explain why you must not create the stream and leave it unclosed, or store `emit` to call asynchronously.

### Exercise 3 — Testing `close`

Use `Stream.of("A")` with `onClose` to create two child streams. Run `flatMap(...).toList()` and verify both close handlers executed. Run a separate experiment for the outer source stream with `onClose`, comparing terminal `count()` against closing in `try-with-resources`.

### Exercise 4 — Short-Circuiting

Given a file with one million lines where only the first three lines are needed, compare:

```java
paths.stream().flatMap(FileLinePipelines::openLinesUnchecked)
    .limit(3).toList();
```

with a `mapMulti` version that opens `Files.lines`, calls `lines.forEachOrdered(emit)`, and places `limit(3)` afterward. State the consequences for **I/O volume** and **resource lifecycle**. Do not claim exact read counts without measuring or testing the implementation.

### Exercise 5 — Data Errors

Suppose three files exist, but the second file is unreadable. Choose between contracts:

- Stop immediately and report an error including the path.
- Continue reading other files, while returning **the result and the list of failed files**.

Do not use `Stream.empty()` to silently report success. Describe how to avoid opening new resources unnecessarily and how to close sources after a failure.

### Exercise 6 — Reader Ownership

Write a pipeline using `BufferedReader.lines()` to count non-blank lines. Prove via `try-with-resources` that **the reader** is closed after the terminal operation completes or throws an error. Compare with `Files.lines(path)` regarding which object must be closed.

### Exercise 7 — Performance and Parallelism

A directory has 10,000 tiny files on a network filesystem. Design a benchmark plan comparing `stream()` and `parallel()` for the same line-counting task; explain how to monitor **concurrent open files**, CPU, I/O, memory, and elapsed time. Explain why merely switching to `parallel()` is not enough to prove correctness or speedup.

## 16. Decision Table

| Scenario | Appropriate approach |
| --- | --- |
| Traversing in-memory `List<List<T>>` | `flatMap(List::stream)` or `mapMulti` with no I/O resources |
| Mapper already produces a resource-holding `Stream<R>` | Return the open stream to `flatMap` so it closes per contract |
| Mapper opens a resource and **synchronously emits** values | `mapMulti` + `try-with-resources` inside the mapper |
| Source is `Files.list` or `Files.walk` | Caller closes the source stream via `try-with-resources` |
| Source is `BufferedReader.lines()` | Close the owning `BufferedReader` |
| Terminal operation is `count` or `toList` | Does **not** auto-close the source stream; close management still required |
| Using `limit`/`findFirst` with huge files | Consider `flatMap` to leverage child-stream short-circuiting |
| `mapMulti` calling `lines.forEachOrdered(emit)` | Do not assume downstream bounds how many lines the mapper reads |
| Opening a file throws checked `IOException` in a lambda | Wrap with cause into `UncheckedIOException` or handle with an explicit business API |
| Errors possible during traversal or closing | Use owner/`try-with-resources`; never swallow errors |
| Source does not guarantee order | Define ordering before speaking of "the first line" |
| Processing files in parallel | Control concurrent resource count, thread-safety, and benchmark |
| Only need count/sum | Use statistical terminal operations instead of `toList` over all data |

`flatMap` and `mapMulti` both express transforming **one input element into zero, one, or many output elements**, yet they do not share the same **resource ownership contract**. With `flatMap`, child streams are returned open so the framework manages closing them; with `mapMulti`, resources opened inside the mapper must be closed within the mapper scope, typically via `try-with-resources`. In both cases, resource-backed source streams such as `Files.list` remain the caller's responsibility. Attending to three independent concerns — **correct results, proper resource closing, and reading only as much data as needed** — makes Java Stream I/O pipelines safer and easier to optimize.
