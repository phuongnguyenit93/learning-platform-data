# Determining Ownership and Closing Responsibility for Streams Returned by APIs

An API returning `Stream<T>` looks very convenient: the caller can chain `filter`, `map`, `limit`, `findFirst`, or `collect` without loading all data into memory. However, when the Stream reads from **a file, directory, or open I/O source**, returning a Stream also raises a critical design question: **who owns the resource and who must call `close()`?**

This lesson belongs to the **I/O Sources and Resource Management** chapter of the **JAVA_STREAM_API** module. We will distinguish in-memory Streams from resource-backed Streams, design Stream-returning API contracts, identify premature-closing or resource-leak bugs, use `try-with-resources` and `onClose`, and handle lazy pipelines, early termination, exceptions, and parallelism. These principles connect to `filter`, `map`, `reduce`, `collect`, `Spliterator`, and advanced Stream operations; however, the core of this lesson is **resource lifecycle**, not transformation syntax.

## 1. Two Lifecycles to Distinguish: The Stream and the Underlying Resource

`Stream<T>` represents a sequence of element-processing operations. A Stream can be created from:

- `List.stream()`, `Arrays.stream(...)`, or `Stream.of(...)`: normally do not hold external files or connections.
- `Files.lines(path)`: reads lines from an open file while traversing data.
- `Files.list(path)`, `Files.walk(path)`, or `Files.find(...)`: traverses file-system entries with I/O resources that must be released.
- A custom API using a `BufferedReader`, database, socket, or other resource as the data source.

All Streams have a `close()` method because `BaseStream` extends `AutoCloseable`. However, **not every Stream needs to be closed in practice**. Streams backed only by ordinary collections have no I/O resources to release; conversely, Streams returned by `Files.lines` or `Files.walk` must be closed properly.

| Source | Has external resource to close? | Typical handling |
| --- | --- | --- |
| `List.of(...).stream()` | No, in normal cases | Can call a terminal operation without `try-with-resources` |
| `IntStream.range(...)` | No | No closing needed for I/O |
| `Stream.of(...)` | No | No closing needed for I/O |
| `Files.lines(path)` | Yes, file-reading resource | `try (Stream<String> lines = ...) { ... }` |
| `Files.list(path)` | Yes, directory-listing resource | Close Stream when done |
| `Files.walk(path)` / `Files.find(...)` | Yes, directory-tree traversal resource | Close Stream when done |
| `BufferedReader.lines()` | Resource belongs to the supplied `BufferedReader` | Close `BufferedReader` per ownership contract; do not assume closing the Stream closes the reader |
| Stream from application API | Depends on implementation | **API contract must state clearly** who closes and what closing releases |

### Two Frequently Confused Concepts

1. **Consume**: invoking a terminal operation such as `count()`, `toList()`, or `findFirst()`. Afterward, you cannot reuse the same Stream for another terminal operation.
2. **Close**: requesting Stream closure, running registered close handlers, and releasing pipeline-associated resources per the source contract.

The two actions **are not synonymous**. Having a terminal operation run to completion **does not automatically guarantee the I/O source is closed**. Conversely, closing a Stream while the caller still needs to traverse it is premature closing.

## 2. Basic Ownership Rule: Whoever Holds Ownership Must Close

For APIs returning a Stream, there are two valid models, provided they are explicitly defined:

| API design | Resource owner during processing | Closing responsibility |
| --- | --- | --- |
| API opens a file and **returns a live Stream** | Transfers Stream ownership to the caller | **Caller** closes the returned Stream |
| API opens a file, runs a terminal operation, returns only `List`/`long`/domain result | **API** retains ownership throughout the operation | **API** closes the resource before returning |
| Caller creates a Stream and **passes it into** a borrowing helper method | Caller remains owner, unless ownership transfer is agreed | Caller closes if the Stream holds resources |
| API returns a Stream built on a resource managed by **another party** | Depends on the source object's contract | Do not close or transfer ownership unless agreed |

There is no technical rule stating "whoever creates a Stream must always close it." Rather: **whoever creates a resource must ensure a clear ownership contract**; they can either close it themselves or explicitly transfer closing responsibility to the caller when returning the Stream. This handoff must be visible in documentation, because the `Stream<T>` type alone does not tell the caller an open file is attached.

Simple conventions to prefer:

- API returning a **live Stream**: documentation explicitly states "caller must close returned Stream", e.g., with `try-with-resources`.
- API returning a **computed result**: the method owns and closes the resource internally.
- API accepting a **borrowed Stream from the caller**: does not close the input Stream unless the contract states ownership is transferred.

## 3. API Returning a Stream Created by `Files.lines`: Transferring Responsibility to the Caller

Consider a method returning non-blank lines with leading/trailing whitespace stripped. The API wants to stay lazy: without reading the whole file into a list.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class TextLineApi {
    private TextLineApi() {}

    /**
     * Opens a file-reading source and returns a live Stream.
     *
     * The caller owns the returned Stream and MUST close it with
     * try-with-resources, even when only using findFirst()/limit().
     *
     * @throws IOException if the source cannot be opened.
     */
    public static Stream<String> readNonBlankLines(Path path)
            throws IOException {
        return Files.lines(path, StandardCharsets.UTF_8)
            .map(String::strip)
            .filter(line -> !line.isEmpty());
    }
}
```

Correct caller:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class ReadNonBlankExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes.txt");

        try (Stream<String> lines = TextLineApi.readNonBlankLines(path)) {
            List<String> results = lines
                .limit(10)
                .toList();

            System.out.println(results);
        } // close() is called even when the pipeline stops early.
    }
}
```

In the example above, `TextLineApi` opens the file source and **transfers ownership of the returned Stream** to the caller. When the returned Stream is closed (after the intermediate operations `map` and `filter`), the pipeline's close handlers run, closing the file-reading resource managed by `Files.lines`.

Key point: `map`, `filter`, and `limit` do not turn a file-backed Stream into a file-independent Stream. They only build a processing pipeline over **the same open source**.

### 3.1. Why Must This Be Explicitly Declared in API Documentation?

The signature:

```java
Stream<String> readNonBlankLines(Path path) throws IOException;
```

does not express ownership at the type-system level. If a caller sees only a method returning `Stream<String>`, they might assume `count()` releases the source automatically.

API documentation should state at a minimum:

1. **Who closes**: the caller must close the returned Stream.
2. **When to close**: after completing the terminal operation or when no longer needed, including early termination and errors.
3. **Resource source**: the Stream traverses a file/directory and holds resources during its lifetime.
4. **Consumption state**: the Stream is single-use and cannot be reused after a terminal operation.
5. **Exceptions**: open errors may be `IOException`; read errors during traversal may appear as `UncheckedIOException`.
6. **Consistency**: file data may change between Stream creation and traversal; do not promise a snapshot if the API does not guarantee one.

A method name containing `open` (such as `openLines`) can hint at a resource, but **it cannot substitute for an explicit closing contract**.

## 4. Serious Bug: Returning a Stream from Inside `try-with-resources`

The following snippet has a **broken resource lifecycle**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static Stream<String> brokenApi(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank());
    } // lines is closed BEFORE the caller runs a terminal operation!
}
```

`return` happens inside the `try` block, yet exiting the block still closes `lines`. The returned pipeline has not been consumed because `filter` is a lazy intermediate operation. When the caller attempts `toList()`, `count()`, or `findFirst()`, the Stream is already closed and no longer valid to use.

**Fix A — return an open Stream and transfer ownership:**

```java
public static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path).filter(s -> !s.isBlank());
}

// Caller:
try (Stream<String> lines = openLines(path)) {
    long count = lines.count();
    System.out.println(count);
}
```

**Fix B — API manages the resource itself and returns a materialized result:**

```java
import java.util.List;

public static List<String> loadLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank()).toList();
    }
}

// Caller receives List<String>, holding no file resource.
List<String> values = loadLines(path);
```

Both approaches are valid; choose based on the goal: if you want lazy traversal without retaining all data, return a live Stream and document closing responsibility; if you want the API to encapsulate the resource and return a standalone result, process inside and close before returning.

## 5. Terminal Operations, Lazy Processing, and Early Stopping Do Not Auto-Close

A `Files.lines` source opens a file-reading resource. Operations like `filter`, `map`, `skip`, and `limit` build intermediate steps; only a terminal operation triggers element processing.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path file = Path.of("events.log");

try (Stream<String> stream = Files.lines(file)) {
    boolean hasError = stream
        .filter(line -> !line.isBlank())
        .anyMatch(line -> line.contains("ERROR"));

    System.out.println(hasError);
}
```

`anyMatch` can stop as soon as it sees an error; it does not mean every line was read. Still, **closing the Stream remains necessary** to release the resource held by `Files.lines`.

Similarly:

```java
try (Stream<String> stream = Files.lines(file)) {
    String first = stream
        .filter(line -> line.startsWith("WARN"))
        .findFirst()
        .orElse("no warnings");

    System.out.println(first);
}
```

With `findFirst`, do not assume the system reads to the end of the file before closing. Try-with-resources calls `close()` when exiting the block, even if the pipeline consumed only a small portion of the source.

### 5.1. Common Scenarios

| Pipeline | Can stop before reading all data? | Must close I/O-backed Stream? |
| --- | --- | --- |
| `filter(...).count()` | Usually must inspect data to count; optimizations may exist | **Yes** |
| `findFirst()` | Yes | **Yes** |
| `anyMatch(...)` | Yes | **Yes** |
| `limit(5).toList()` | Yes | **Yes** |
| `noneMatch(...)` | Yes | **Yes** |
| `toList()` | Usually collects all elements reaching the end of the pipeline | **Yes** |
| `reduce(...)` | Usually must consume all elements being reduced | **Yes** |

The rule does not depend on how many elements were processed: **a source with external resources must be closed when finished**, even when the source is empty or the terminal operation returns early.

## 6. Exceptions in the Pipeline: `try-with-resources` Still Closes the Source

Errors can surface **after the API returns the Stream**, because much of the reading and transformation work is deferred until the terminal operation. For example, a line with an invalid format:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long sumFile(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
            .filter(s -> !s.isBlank())
            .mapToLong(Long::parseLong)
            .sum();
    }
}
```

If there is a line `"abc"`, `Long.parseLong` throws `NumberFormatException` while consuming the pipeline. **Try-with-resources still calls `close()`**, and then the exception propagates outward per Java semantics.

When reading from `Files.lines` or `Files.walk`, distinguish:

- **When opening the Stream**: can raise a declared `IOException`.
- **When traversing the Stream**: I/O failures can be wrapped in `UncheckedIOException`.
- **Inside lambdas**: business-logic errors (such as `NumberFormatException`) can appear during the terminal operation.
- **When closing**: close handlers or the source may fail; try-with-resources manages *suppressed exceptions* when both processing and closing fail.

Do not close only on the success path. Nor should you call `close()` manually across multiple `return`/`catch` branches when `try-with-resources` already expresses the contract cleanly.

### 6.1. Prefer try-with-resources Over Manual Closing in `finally`

The manual form can be correct if handled carefully:

```java
Stream<String> lines = Files.lines(path);
try {
    return lines.count();
} finally {
    lines.close();
}
```

However, the recommended form is more concise and handles close exceptions better:

```java
try (Stream<String> lines = Files.lines(path)) {
    return lines.count();
}
```

## 7. API Owning the Resource Itself: Returning a Computed Result

Not every API should return a Stream. When the goal is just counting, finding one value, or producing a small list, the API can open and close the source itself.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public final class LogReportApi {
    private LogReportApi() {}

    public static long countErrors(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.filter(line -> line.contains("ERROR")).count();
        }
    }

    public static List<String> firstFiveErrors(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> line.contains("ERROR"))
                .limit(5)
                .toList();
        }
    }
}
```

Here:

- The API **retains ownership** from the `Files.lines` call until the `try` block exits.
- The caller receives `long` or `List<String>`, **not a Stream still holding a file**.
- `firstFiveErrors` can still stop early via `limit(5)`, while the source is always closed.
- `List` is a materialized result; if filtering many elements and returning the full list, consider memory usage.

### 7.1. A Self-Closing API Can Accept a Processing Function

When you want to give callers flexibility without **transferring closing responsibility**, another design is an API accepting a function to process the source.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;
import java.util.stream.Stream;

public final class SafeFileStreams {
    private SafeFileStreams() {}

    public static <R> R withLines(
            Path path,
            Function<? super Stream<String>, ? extends R> action
    ) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return action.apply(lines);
        }
    }
}
```

Caller usage:

```java
long count = SafeFileStreams.withLines(
    Path.of("events.log"),
    lines -> lines.filter(line -> line.contains("ERROR")).count()
);
```

The contract of `withLines`: the `action` function must **consume and complete its work right inside the call**, without returning a lazy Stream or an object dependent on that Stream. If `action` returns a Stream containing intermediate operations that has not yet been consumed, the source will close before the caller uses it. State this constraint clearly in JavaDoc and consider specialized APIs if stronger type-level guarantees are desired.

The callback design fits when callers want to customize `filter`, `map`, `reduce`, and `collect` without remembering to close resources. In return, the API needs to control synchronous execution scope clearly and prevent source references from escaping.

## 8. API Accepting a Caller's Stream: Consuming Does Not Mean Owning

Consider a method that simply aggregates lines and **receives** a Stream created elsewhere:

```java
import java.util.stream.Stream;

public static long countNonBlank(Stream<String> lines) {
    return lines.filter(s -> !s.isBlank()).count();
}
```

This method **consumes** the passed Stream, but that does not mean it is allowed to **close** a resource belonging to the caller. When the parameter type is simply `Stream<String>`, it could receive either an in-memory Stream or a file-reading Stream.

Recommended rule: a method **borrows** a Stream to consume it and **does not close** it; the caller retains closing responsibility when the source holds I/O resources.

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("events.log");

try (Stream<String> lines = Files.lines(path)) {
    long number = countNonBlank(lines);
    System.out.println(number);
}
```

If an API intends to **take over ownership** and close the input Stream itself, it must state that explicitly as an **ownership transfer**, for instance via the method name, API documentation, or a dedicated wrapper type. Never assume the caller will close while also silently closing inside a borrowing helper, especially when underlying resources may be shared.

### 8.1. Do Not Pass an Already-Used Stream

```java
Stream<String> values = Stream.of("A", "B");

long count = countNonBlank(values); // Stream has been consumed.

// values.findFirst(); // Invalid: a Stream cannot be used twice.
```

Even without closing, the terminal operation has consumed the Stream. This is the **single-use restriction**, separate from ownership and closing contracts.

## 9. Specifics of `BufferedReader.lines()`: Who Owns the Reader?

`BufferedReader.lines()` returns a `Stream<String>` reading from the `BufferedReader`. In this design, the **reader** object remains the managed resource. Do not assume that **closing the Stream returned by `reader.lines()` will automatically close the reader**.

Correct usage when the API owns the reader:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static long countComments(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
            .filter(line -> line.stripLeading().startsWith("#"))
            .count();
    }
}
```

The `try` block closes **`BufferedReader`**, which is the resource actually opened. `reader.lines()` merely represents traversing lines from that reader.

### 9.1. If You Must Return a Stream from a Reader, Attach Closing Responsibility

You can attach `onClose` so that when the caller closes the Stream, the reader closes too:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static Stream<String> openReaderLines(Path path) throws IOException {
    BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);

    return reader.lines().onClose(() -> {
        try {
            reader.close();
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    });
}

// Caller:
try (Stream<String> lines = openReaderLines(Path.of("events.log"))) {
    System.out.println(lines.findFirst());
}
```

`onClose` does not close the reader when declaring the pipeline; it only registers **an action for when the Stream is closed**. If the caller forgets to close, the reader still risks staying open. Since simple file sources already have `Files.lines` with a clear closing contract, prefer it over building a custom reader adapter unless you have a special requirement.

For more complex real-world adapters, ensure the reader is released if Stream creation or handler registration fails **before transferring ownership** to the caller, and handle close-time exceptions properly.

## 10. `onClose`: Close Handlers Differ from Terminal Operations

`onClose(Runnable)` registers an action to be called when the Stream closes. It is useful for attaching resource-release steps, marking a session, or recording close events.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger closed = new AtomicInteger();

try (Stream<String> words = Stream.of("A", "B")
        .onClose(() -> closed.incrementAndGet())) {
    List<String> result = words.toList();

    System.out.println(result);       // [A, B]
    System.out.println(closed.get());  // 0: have not left the try block yet.
}

System.out.println(closed.get());      // 1: close handler has run.
```

The `Stream.of` example needs no closing for I/O; `try-with-resources` is used here to **illustrate handler behavior**. In real applications, avoid abusing `onClose` to produce side effects in place of business logic.

When a handler throws an exception, Java still processes the other registered handlers per the close contract, and additional errors may be recorded as suppressed exceptions. Do not assume all close errors occur at Stream creation time.

### 10.1. Closing the Stream Returned After `map`/`filter`

```java
AtomicInteger closeCount = new AtomicInteger();

Stream<String> source = Stream.of(" a ", " b ")
    .onClose(closeCount::incrementAndGet);

try (Stream<String> transformed = source
        .map(String::strip)
        .filter(s -> !s.isEmpty())) {
    System.out.println(transformed.toList()); // [a, b]
}

System.out.println(closeCount.get()); // 1
```

In this pipeline, `transformed` and `source` belong to **the same pipeline**, not two independent sources. Closing the Stream returned at the end of the pipeline runs the handlers attached to the source.

Do not hold both `source` and `transformed` as two independent resources to consume separately. Once the pipeline finishes, the Stream cannot be reused.

## 11. Completing `flatMap` and Child Streams

`flatMap` can create a child Stream for each source element. By the Stream contract, each child Stream produced by the mapper is **closed after its contents have been placed into the pipeline**.

Example splitting each string into characters:

```java
import java.util.List;

List<String> tokens = List.of("AB", "CD");

List<String> chars = tokens.stream()
    .flatMap(text -> text.codePoints()
        .mapToObj(cp -> new String(Character.toChars(cp))))
    .toList();

System.out.println(chars); // [A, B, C, D]
```

However, `flatMap` closing child Streams **does not mean an outer I/O-backed source Stream is automatically closed after a terminal operation**. If the outer stream comes from `Files.lines`, the caller must still close the outer stream:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(Path.of("codes.txt"))) {
    long characterCount = lines
        .flatMapToInt(String::codePoints)
        .count();

    System.out.println(characterCount);
}
```

Cases where child Streams also own separate resources should be evaluated according to the child-Stream-creating API's contract; avoid building complex resource hierarchies without clearly defining where each source is created and closed.

## 12. Complete Java 17 Example: Stream-Returning API vs. Self-Closing API

The following example demonstrates **both contract styles** on a temporary file created by the program. `openRecords` transfers Stream ownership to the caller; `countRecords` closes internally and returns only a `long` result.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class StreamOwnershipDemo {

    /**
     * Caller owns the returned Stream and must close it.
     */
    public static Stream<String> openRecords(Path file) throws IOException {
        return Files.lines(file, StandardCharsets.UTF_8)
            .map(String::strip)
            .filter(line -> !line.isEmpty());
    }

    /**
     * This method owns and closes the file-backed Stream.
     */
    public static long countRecords(Path file) throws IOException {
        try (Stream<String> lines = openRecords(file)) {
            return lines.count();
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("stream-ownership-", ".txt");

        try {
            Files.write(
                file,
                List.of("  A ", "  ", "B  "),
                StandardCharsets.UTF_8
            );

            // Contract 1: Caller closes the returned Stream.
            try (Stream<String> records = openRecords(file)) {
                System.out.println(records.toList()); // [A, B]
            }

            // Contract 2: API closes internally, returns count.
            System.out.println(countRecords(file));   // 2
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

What this example demonstrates about design:

1. `openRecords` does **not** close the Stream before returning.
2. The caller always wraps the result of `openRecords` in `try-with-resources`.
3. `countRecords` consumes the Stream within its own scope and closes it itself.
4. `Files.write` and `Files.deleteIfExists` only serve to prepare demo data; real-world APIs should apply appropriate file permission and I/O error policies.
5. Once `openRecords` is consumed with `toList()`, the list is in-memory data and no longer depends on the closed file source.

If the application processes files that may be modified by another process, add consistency rules or data-pinning mechanisms; a resource-closing contract **does not automatically create a consistent snapshot**.

## 13. Designing APIs by Need: What Type Should You Return?

| Caller's need | Recommended design | Closing responsibility |
| --- | --- | --- |
| Traverse very many lines, pick custom `filter`/`map`, avoid holding everything | Return a lazy `Stream<T>` from an I/O source | Caller closes the Stream; must document contract |
| Only need a count or an aggregate | Return `long`, `int`, `BigInteger`, or a domain result | API opens, consumes, and closes internally |
| Need a list usable long after the file closes | Return a materialized `List<T>` | API closes before returning |
| Want processing flexibility without exposing ownership | Accept a synchronous processing callback inside open scope | API closes; callback must not let lazy data escape |
| Already have a caller-owned `BufferedReader` | Method accepts reader or borrowed Stream; does not close unless explicitly transferred | Reader owner closes |
| Need complex lifecycle control over multiple resources | Design a dedicated `AutoCloseable` wrapper with a closing contract | Per wrapper/API; do not rely solely on `Stream` type |

No single API shape fits every case. The trade-off is among **laziness and caller control**, **memory when materializing results**, and **clarity of resource lifecycles**.

### 13.1. A Minimal JavaDoc Template

```java
/**
 * Lazily reads records from the file.
 *
 * <p>The returned Stream owns an open file resource.
 * The caller must close it, preferably using try-with-resources.
 * Closing the returned Stream releases the underlying resource.
 * The Stream can be consumed only once.
 *
 * @throws IOException if the resource cannot be opened
 * @throws java.io.UncheckedIOException if an I/O failure occurs
 *         during traversal
 */
public static Stream<String> openRecords(Path path) throws IOException;
```

This template only illustrates **the documentation contract**, not a standalone compilable declaration without a method body. If the API adds constraints on encoding, connection lifetime, ordering, or thread-safety, document those specifically as well.

## 14. Parallel Processing and Resource Lifecycle

`parallel()` changes how the pipeline can process elements; **it does not transfer closing responsibility** to the JVM. If a Stream from `Files.lines` is processed in parallel, the caller still must close it:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(Path.of("events.log"))) {
    long errors = lines.parallel()
        .filter(line -> line.contains("ERROR"))
        .count();

    System.out.println(errors);
}
```

Do not assume parallel processing is faster for I/O. File access, decoding overhead, contention, and `Spliterator` splitting characteristics all affect performance. For many sources or resources that are not concurrency-safe, review the source's contract before switching to a parallel Stream.

### 14.1. Do Not Mutate or Close the Source Mid-Traversal

If another thread closes the Stream or underlying I/O resource while the pipeline is still active, results may fail or lack guarantees under the source contract. Avoid designs where multiple components believe they are owners entitled to close at any time.

In particular, if an API returns a Stream from a database or stateful connection, define a dedicated contract for concurrency, transactions, and connection lifetime. Do not infer from `Stream<T>` having `parallel()` that the underlying source supports concurrent access.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct practice |
| --- | --- | --- |
| API returns `Files.lines(...).filter(...)` without stating caller must close | API users easily forget the resource | Document ownership and show `try-with-resources` usage |
| API does `return stream` inside `try-with-resources` | Stream closes before the caller consumes it | Either return an open Stream, or consume inside `try` and return the result |
| Assuming `toList()`/`count()` automatically closes an I/O Stream | Resource can stay open | Use `try-with-resources` |
| Stopping early with `findFirst`/`anyMatch` and skipping `close()` | Resource is not released | Still close the source when leaving scope |
| Closing only on the success path | Leaks when mapper/terminal operation throws | Wrap the source in `try-with-resources` |
| Closing `Stream` from `reader.lines()` thinking the reader is closed | Reader remains open | Close `BufferedReader`, or attach a close handler when transferring ownership |
| Adding `onClose` thinking the close action runs automatically after terminal op | Handler never runs if Stream is not closed | Caller/API still must call `close()` per ownership |
| Method takes a borrowed Stream and closes it unasked | Breaks caller's lifecycle | Close only when contract specifies ownership transfer |
| Reusing the same Stream after `count()`/`toList()` | Stream already consumed | Create a new source if re-traversal is needed |
| Closing source then attempting to traverse pipeline built from it | Premature close, cannot traverse | Close **after** the pipeline's terminal operation completes |
| Using `Files.lines` then collecting all with `toList()` without considering RAM | May hold huge data in memory | Choose aggregated result or lazy Stream based on goal |
| Passing an I/O Stream to a callback API and letting a lazy Stream escape | Resource closes before pipeline is used | Return only completed results from callbacks |
| Enabling `parallel` thinking the framework handles closing | Ownership does not change | Close at the designated owner |
| Using `map`/`peek` to release source resources | Not guaranteed to run completely, especially with short-circuiting | Use `close`/`onClose`/`try-with-resources` |
| Multiple components closing a shared connection without a contract | Double-closing or breaking other tasks | Design clear owner/borrower lifecycles |

## 16. Practice Exercises

### Exercise 1: Identify Who Must Close

Classify six sources: `List.stream()`, `IntStream.range()`, `Files.lines()`, `Files.list()`, `BufferedReader.lines()`, and an API `openRecords(path)` returning a Stream with JavaDoc "caller must close". State **the actual resource** that needs closing and the responsible party.

### Exercise 2: Fix an API That Closes Too Early

Given:

```java
Stream<String> openBadly(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> s.length() > 5);
    }
}
```

Explain why `openBadly(path).count()` is invalid. Write two fixed versions: (a) returning a lazy Stream with JavaDoc transferring ownership, and (b) returning a `List<String>` collected inside `try-with-resources`.

### Exercise 3: Early Stop Still Closes the Source

Write an API finding the first line starting with `"ERROR"` in a file:

```java
Optional<String> firstError(Path path) throws IOException
```

Implement using `Files.lines`, `filter`, and `findFirst`. Point out where to place `try-with-resources` so the source always closes, even when the first line matches.

### Exercise 4: Design Two Ownership API Styles

Implement two methods:

```java
Stream<String> openNames(Path path) throws IOException;
long countNames(Path path) throws IOException;
```

One transfers closing responsibility to the caller, while the other closes internally. Write correct caller examples for both and describe what happens if the caller forgets to close the result of `openNames`.

### Exercise 5: Callback and Lazy Results

Given `withLines(path, Function<Stream<String>, R>)`, try a callback that returns `lines.filter(...)` without calling a terminal operation. Why can the resulting Stream not be traversed after `withLines` returns? Replace the callback with `lines.filter(...).count()` or `toList()` and explain the difference.

### Exercise 6: `onClose` and Processing Errors

Create a Stream from `Stream.of(...)` with an `onClose` that increments an `AtomicInteger`. Inside `try-with-resources`, invoke a terminal operation whose mapper throws `IllegalArgumentException` for an element. Check the counter after catching the exception to confirm the handler still ran when the Stream closed.

### Exercise 7: Managing `BufferedReader`

Write `countNonBlank(Path path)` using `Files.newBufferedReader` and `reader.lines()`. Use `try-with-resources` on the proper owner object. Then explain why `reader.lines().onClose(...)` may be needed if an API must return a Stream from a reader to the caller.

### Exercise 8: Choosing for Large Files

A log file has tens of millions of lines. Evaluate three APIs: (a) returning a full `List<String>`, (b) returning a lazy `Stream<String>` with caller closing responsibility, and (c) taking a callback returning summary metrics. Compare memory, flexibility, resource hold time, and the risk of the caller forgetting to close.

## 17. Self-Check Knowledge

- Why does consuming a `Stream` with `count()` not mean the I/O source has been closed?
- For an API returning a `Stream` from `Files.lines`, who must close it and why?
- What is wrong with `return stream.filter(...)` inside `try-with-resources`?
- Do `findFirst()`, `limit(5)`, and `anyMatch()` change the requirement to close the source?
- Does `onClose` execute immediately upon registration?
- Does closing the Stream returned by `BufferedReader.lines()` automatically close the reader?
- Should a method that merely **borrows** a Stream from the caller close it, and what contract must be documented if it wants ownership?
- When should an API return `List<T>` or `long` instead of a Stream?
- When a lambda throws after a file is opened, how does `try-with-resources` protect the resource?
- Why does `parallel()` neither replace the ownership contract nor guarantee faster I/O?
- When is a callback processing a Stream inside an open resource scope a useful design?
- What rule prevents confusing "consumed once" with "closed"?

**Key takeaway:** With Streams backed by files or I/O sources, **a terminal operation does not replace `close()`**. Either the API **closes internally after finishing computation** and returns an independent result, or it **returns a live Stream and explicitly transfers closing responsibility to the caller**. Use `try-with-resources` at the true owner; never return a Stream from a `try` block that has already closed, never skip closing after short-circuiting, and never assume `BufferedReader.lines()` or `onClose` releases resources without an appropriate close call.
