# Distinguishing I/O streams from `java.util.stream.Stream` in Java

In Java, the word **stream** appears in two different API groups. An **I/O stream** is a channel for reading/writing data across a device, file, socket, or memory; **`java.util.stream.Stream<T>`** is a pipeline for processing elements in a declarative style. They can be combined, but they do not directly replace each other. This article is placed in the **I/O Overview** section and focuses on how to choose, use, and manage both kinds of streams.

## 1. Two meanings of “stream”

**I/O stream — data flowing through a read/write channel**

- `java.io.InputStream` reads **bytes**; `java.io.OutputStream` writes **bytes**.
- `java.io.Reader` reads **characters**; `java.io.Writer` writes **characters**. When converting between bytes and characters, you must specify an encoding such as UTF-8.
- The source/destination can be a file (`FileInputStream`), memory (`ByteArrayInputStream`), a network connection, or another wrapped I/O stream (`BufferedInputStream`, `InputStreamReader`).
- Operations such as `read()`, `write()`, and `flush()` directly perform or request I/O actions. Reading advances sequentially from the current position; end-of-stream is typically indicated by `-1`. Many operations can block the execution thread and throw `IOException`.
- Most I/O resources need to be closed with `close()` in a timely manner. `try-with-resources` ensures closing even when an exception occurs.

**Stream API — a sequence of element transformations/consumption**

- `java.util.stream.Stream<T>` represents a pipeline over **objects of type `T`**, such as `Stream<String>`; `IntStream`, `LongStream`, and `DoubleStream` are specialized for primitive types.
- The source can be `Collection.stream()`, `Arrays.stream()`, `Stream.of()`, an element generator, or a data-reading API such as `Files.lines()`.
- Intermediate operations such as `filter`, `map`, and `distinct` build the pipeline; terminal operations such as `toList`, `count`, `reduce`, and `forEach` trigger data consumption.
- Pipelines are typically **lazy**: defining intermediate operations does not immediately process elements. A stream is single-use; you cannot re-run the same pipeline after a terminal operation.
- The Stream API can process sequentially or in parallel, but parallelism does **not** automatically make I/O faster.

> Distinguish the fully qualified names when explaining or importing: `java.io.InputStream` / `java.io.OutputStream` belong to I/O; `java.util.stream.Stream` belongs to the Stream API. `Reader`/`Writer` are also I/O even though their names do not contain “Stream”.

## 2. Direct comparison table

| Criterion | I/O stream (`InputStream`, `OutputStream`, `Reader`, `Writer`) | `java.util.stream.Stream<T>` |
|---|---|---|
| Question it answers | **Where** is data read from/written to, and **how**? | **How** are elements filtered, transformed, and aggregated? |
| Primary unit | Bytes or characters | Object elements (`T`) or primitive streams |
| Processing direction | Reading/writing through a specific source or destination | A flow of elements running from a source through a pipeline to a result |
| Characteristic API | `read`, `write`, `flush`, `close` | `filter`, `map`, `sorted`, `collect`, `toList`, `count` |
| Execution timing | Read/write operations happen when the method is called; can block | Intermediate operations are usually lazy; a terminal operation triggers execution |
| Exceptions | Typically uses `IOException` (checked) | Standard operations do not declare `IOException`; I/O-backed sources may throw `UncheckedIOException` during traversal |
| Resources | File descriptors, sockets, buffers, etc. may need closing | Streams from collections usually hold no external resources; file-backed streams may need closing |
| Reuse | Reading advances the position; some types support `mark/reset` or reopening the source | Cannot be reused after a terminal operation; a new Stream must be created |
| Parallel | I/O streams themselves do not provide a `parallel()` pipeline | Has `parallel()`, but correctness, ordering, overhead, and data source must be considered |
| Result | Bytes/characters read, or the side effect of writing to a destination | An aggregated value, collection, or element depending on the terminal operation |

Both can be **incremental** in many cases, but “lazy” in the Stream API refers to **when transformations execute**; it does not mean only the Stream API saves memory or supports reading piece by piece.

## 3. Example 1 — same word “stream”, two different jobs

File `StreamKindsDemo.java` (Java 17+):

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

public class StreamKindsDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "abc".getBytes(StandardCharsets.UTF_8);

        // I/O: read bytes from a source.
        try (InputStream input = new ByteArrayInputStream(data)) {
            System.out.println((char) input.read());
            System.out.println(
                    new String(input.readAllBytes(), StandardCharsets.UTF_8));
        }

        // Stream API: process elements of a List.
        List<String> chosen = List.of("An", "Binh", "Chi").stream()
                .filter(name -> name.length() >= 3)
                .map(String::toUpperCase)
                .toList();
        System.out.println(chosen);
    }
}
```

Run:

```bash
javac --release 17 StreamKindsDemo.java
java StreamKindsDemo
```

Output:

```text
a
bc
[BINH, CHI]
```

In the first part, `read()` retrieves the first byte (`'a'`); `readAllBytes()` retrieves the **remaining bytes** (`"bc"`), without automatically rewinding to the beginning. `ByteArrayInputStream` is an I/O stream that reads from memory, so “I/O” does not mean every read accesses disk or network.

In the second part, `List.stream()` creates a `Stream<String>`, `filter` keeps names at least three characters long, `map` converts them to uppercase, and `toList()` produces the result. The pipeline does not read bytes from a device; it processes objects already in the `List`. The list returned by `Stream.toList()` is **structurally unmodifiable** (unmodifiable), since Java 16.

## 4. Lazy pipelines and single-use consumption

Example `LazyPipelineDemo.java` (Java 17+):

```java
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        Stream<String> pipeline = Stream.of("a", "bb", "ccc")
                .map(value -> {
                    System.out.println("map:" + value);
                    return value.toUpperCase();
                })
                .filter(value -> value.length() >= 2);

        System.out.println("Built pipeline");
        System.out.println(pipeline.toList());
    }
}
```

```bash
javac --release 17 LazyPipelineDemo.java
java LazyPipelineDemo
```

```text
Built pipeline
map:a
map:bb
map:ccc
[BB, CCC]
```

`map` and `filter` only construct the pipeline; calling `toList()` causes elements to pass through the pipeline. Operation order can differ if you change how the pipeline is constructed, apply optimizations, or run in parallel. The print statement inside `map` here is only to illustrate execution timing; in real programs, avoid relying on side effects of intermediate operations.

**Common misconception:** `Stream<T>` is not a “container” that can be traversed repeatedly:

```java
Stream<String> oneShot = Stream.of("A", "B");
long count = oneShot.count();       // Valid
// oneShot.toList();                // IllegalStateException: stream has already been used
```

The snippet above is **illustrative**, not a standalone program. After `count()`, if you need further computation, create a new stream from the source. Similarly, `parallel()` only changes how the pipeline executes; it does not turn an I/O stream into the Stream API and does not allow reusing a consumed stream.

## 5. When the two APIs combine: reading a file and filtering lines

A file typically stores **bytes**. `Files.lines(path, charset)` produces a `Stream<String>`: the I/O side reads and decodes the data, while the Stream API provides `filter`/`count`. This is a **bridge** between the two concepts.

File `FileLinesDemo.java` (Java 17+; creates and cleans up a temporary file automatically):

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-stream-demo-", ".txt");
        try {
            Files.writeString(file, "Java\nI/O\nStream\n",
                    StandardCharsets.UTF_8);

            // Stream API reads lines from an I/O source: must close the Stream.
            try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
                long count = lines.filter(line -> line.length() >= 4).count();
                System.out.println("Long lines: " + count);
            }

            // I/O Reader: reads lines sequentially directly.
            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("First: " + reader.readLine());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 FileLinesDemo.java
java FileLinesDemo
```

```text
Long lines: 2
First: Java
```

Explanation:

1. `Files.writeString` writes UTF-8 text; the `\n` sequence in the Java string creates a newline.
2. `Files.lines` creates a `Stream<String>` that reads lines on demand when the terminal operation runs. `filter` keeps `"Java"` and `"Stream"`; `count` prints `2`.
3. `try-with-resources` closes the stream from `Files.lines`, ensuring the associated file resource is released even if the pipeline fails. A terminal operation such as `count()` does **not** mean the stream is automatically closed.
4. `Files.newBufferedReader` returns a `BufferedReader`; `readLine()` directly reads the first line. The Reader is also closed via `try-with-resources`.
5. The `finally` block deletes the temporary file after both the stream and the reader are closed. If cleanup fails, `deleteIfExists` can throw `IOException`.

The `BufferedReader.lines()` method also returns a `Stream<String>`, but you still have to manage **the `BufferedReader` that created that stream**. Do not assume that closing only the Stream returned by `reader.lines()` closes the reader. For example, when you open the reader yourself:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long total = reader.lines().filter(s -> !s.isBlank()).count();
    System.out.println(total);
}
```

This snippet is an **illustrative pattern**: `path` must be a valid `Path`, and the caller must handle/declare `IOException`. The reader remains open while the terminal operation runs. `Files.lines` and `BufferedReader.lines` do not require loading the entire file into memory; however, stateful transformations such as `sorted` or terminal operations such as `toList` can still collect many elements in memory.

## 6. Choosing the API for practical requirements

**Need to copy, read/write raw data, transmit over a socket, or handle binary formats:** use `InputStream`/`OutputStream`, or `Files.copy` when appropriate. When working with bytes, you cannot apply `filter` or `map` directly on an `InputStream`; if you need a pipeline, you must convert it into a meaningful element source and consider the overhead.

**Need to read/write text:** use `Reader`/`Writer` and explicitly specify a `Charset` when converting between bytes ↔ characters. For example, `Files.newBufferedReader(path, UTF_8)` to read line by line, and `Files.newBufferedWriter` to write strings. Do not cast an arbitrary byte to `char` and expect valid Unicode; Example 1 only did that because the byte `'a'` is ASCII.

**Need to filter/transform/aggregate existing data:** choose `Stream<T>` from a `Collection`/array/element generator. For simple operations, a traditional loop can be easier to understand and have less overhead.

**Need to read a text file and process line by line:** `Files.lines(path, UTF_8)` combines I/O and the Stream API; close the stream in `try-with-resources`. If you need direct control over reading, character stream handling, or alternating line reads in a stateful workflow, `BufferedReader.readLine()` is the direct choice.

**Small or large files?** `Files.readAllLines` reads all lines into a `List<String>`; convenient when the data fits in memory. `Files.lines` supports incremental pipeline processing, often reducing memory usage for streaming filters/aggregations, but does not automatically solve all memory issues (for example, `sorted().toList()` still retains significant data).

## 7. Common mistakes

1. **Calling the wrong method:** `InputStream` does not have `map`/`filter`; `Stream<String>` does not have `read()`/`write()` like an I/O stream. The two APIs serve different purposes and data types.
2. **Ignoring encoding:** reading bytes and converting directly to text using the default charset can corrupt Vietnamese text. For text data, specify `StandardCharsets.UTF_8` on both sides when needed.
3. **Forgetting to close I/O sources:** using `Files.lines` and only calling `count()`/`toList()`, then forgetting `close()`. Keep `try-with-resources` around streams tied to files. For readers you open yourself, close the reader.
4. **Assuming every Stream must be closed:** `Stream.of(...)` and `list.stream()` do not normally hold OS resources. Although `Stream` extends `AutoCloseable`, the need to close depends on the **source**; `try-with-resources` is still valid, though usually unnecessary for in-memory streams.
5. **Assuming `readAllBytes()` is always best:** it stores all remaining bytes in a single array; for large data, consider chunked processing, `transferTo`, or direct streaming APIs.
6. **Reusing a Stream after a terminal operation:** if you want to run `count` and `toList` independently, create two new streams, or collect the data first if memory limits permit.
7. **Assuming the Stream API is always faster:** building a pipeline has overhead; `parallel()` can reduce performance or cause contention on I/O sources. Measure performance with real data before optimizing.
8. **Misunderstanding exception boundaries:** I/O methods like `Files.lines`/`readLine` typically declare `IOException`; read errors while traversing a file-backed stream can surface at runtime as `UncheckedIOException`. Handle them at the proper I/O boundary; do not swallow errors.
9. **Misusing side effects and ordering:** `forEach` on a parallel stream does not guarantee encounter order; if order matters, consider `forEachOrdered` or sequential processing. Use `map`/`filter` primarily for pure transformation functions and predicates.

## 8. Key takeaways checklist

- Are you **transferring/reading/writing bytes or characters**? Think of `java.io` and `java.nio.file`.
- Are you **processing a sequence of elements**? Think of `java.util.stream`.
- Are you reading from a file via `Files.lines`? **Both** appear together: I/O supplies the elements, and the Stream API processes them.
- Is there an open file/socket/reader? Determine **who owns and who closes** the resource.
- Was a terminal operation executed? The pipeline has been consumed; to run again, create a new Stream.

**Conclusion:** “stream” in I/O refers to **a flow of data passing through a read/write endpoint**; “stream” in the Stream API refers to **a pipeline for processing elements**. When combining them, choose the API based on data form, manage exceptions, and close resources at the proper boundary.

### References (Java SE 17)

- [`java.io.InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [`Reader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html)
- [`java.util.stream.Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [`Files.lines` and `Files` utilities](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`BufferedReader.lines`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
