# BufferedReader.lines() and Reader Closing Ownership in Java

`BufferedReader.lines()` turns a `BufferedReader` into a `Stream<String>` so you can process lines of text using the Stream API. The syntax is very convenient for filtering, transforming, counting, and searching lines:

~~~java
long count = reader.lines()
        .filter(line -> !line.isBlank())
        .count();
~~~

However, you must distinguish **stream consumption** from **I/O resource ownership**. The stream created by `BufferedReader.lines()` reads data from the same `BufferedReader`, yet **closing the stream does not automatically close the reader**. If the reader reads a file or socket, the reader's owner must still close the reader when finished. This differs from `Files.lines(path, charset)`: the stream returned by `Files.lines` is bound to a file resource and must be closed to release that resource.

## 1. Objectives

After this lesson, you will be able to:

- Explain how `BufferedReader.lines()` produces a **lazy** `Stream<String>` and when actual I/O happens.
- Distinguish an empty line `""`, a whitespace-only line, and `readLine()`'s `null`; understand that line terminators are no longer present in stream elements.
- Place `try-with-resources` around the right object that owns the resource, even when the stream short-circuits with `findFirst()` or `limit()`.
- Prove with a runnable program that `stream.close()` does not automatically call `BufferedReader.close()`.
- Distinguish `BufferedReader.lines()` from `Files.lines()` regarding resource-closing ownership.
- Handle `UncheckedIOException` raised during lazy reading, avoid returning a stream tied to an already closed reader, and avoid using the reader concurrently with a stream terminal operation.
- Know when to use `readLine()`, `lines()`, or reading `char[]` blocks.

## 2. Source, Stream, and Resource: Three Roles to Keep Separate

Consider the relationship:

~~~text
File / socket / StringReader
          |
          v
     BufferedReader   <-- object managing the underlying Reader
          |
          | .lines()
          v
     Stream<String>   <-- pipeline processing the lines
          |
          | filter / map / limit / count / forEach / ...
          v
        Result
~~~

- `BufferedReader` is a buffered `Reader`; it implements `Closeable`/`AutoCloseable` itself, and `close()` closes the underlying reader.
- `BufferedReader.lines()` returns a `Stream<String>` **backed by that reader**; the stream itself does not carry ownership to close the reader under this contract.
- `Stream` supports `close()`, primarily to run **close handlers** attached to the stream (if any). Do not infer that calling `close()` on every stream closes the data source the pipeline reads from.
- Resource-closing responsibility stems from how **the resource is opened and handed over**. Whoever opens the reader is normally responsible for closing it, unless an API contract explicitly states transfer of ownership.

A file can remain open if you only close the `Stream<String>` and forget to close the `BufferedReader`. Conversely, closing `BufferedReader` too early prevents an unconsumed stream from reading properly.

### Essential Contract of `BufferedReader.lines()`

- Creates a stream of lines matching the results of sequential `readLine()` calls.
- Each `String` element **does not contain** line-termination characters.
- Data is read **lazily**: only when a terminal operation executes does the pipeline request lines.
- If an `IOException` occurs from the reader while the pipeline is reading, the exception is wrapped in an `UncheckedIOException` to fit the Stream API.
- You should not perform other operations on the same reader while a stream terminal operation is running; the terminal operation's result is not guaranteed in that case.
- After a terminal operation, do not assume the reader is at any particular position for further reading via another API.
- Calling `close()` on the returned stream does not automatically call `close()` on the reader.

Remember the difference between `lines()` and `readLine()`: `readLine()` returns `null` at EOF; in the Stream API, EOF simply means the stream **runs out of elements** and does not emit a trailing `null` element.

## 3. Lazy Evaluation: Building a Pipeline Does Not Mean Reading the File Yet

Example:

~~~java
Stream<String> pipeline = reader.lines()
        .map(String::trim)
        .filter(line -> !line.isEmpty());
~~~

At declaration time, `map` and `filter` are **intermediate operations**; they have not traversed the file and have not produced a data list yet. A terminal operation such as `forEach`, `count`, `toList`, `findFirst`, or `anyMatch` triggers fetching and processing from the source.

~~~java
List<String> values = pipeline.toList(); // terminal operation (Java 16+)
~~~

A stream can only be consumed **once**. After `toList()`, you cannot follow up with `pipeline.count()`; you must create a new source/pipeline if the data allows. Even when a terminal operation short-circuits, such as `findFirst()`, reusing the same stream is invalid.

### `limit()` and `findFirst()` Do Not Automatically Close the Reader

~~~java
Optional<String> first = reader.lines()
        .filter(line -> line.startsWith("ERR"))
        .findFirst();
~~~

`findFirst()` may stop before reaching the end of the file; that does not cause the reader resource to close automatically. `limit(10)` likewise only caps **the number of stream elements** the pipeline takes—it does not bound a line's length and does not close the file. The reader stays open until its owner closes it.

A reader may have already buffered more characters ahead than the stream delivered to the caller. Therefore, after a terminal operation, **do not rely on the reader's remaining position** to continue reading accurately from an assumed offset. If you must combine multiple reading styles under one protocol, manage them through a single consistent reading mechanism.

## 4. Proper Usage Pattern: Open Reader, Consume Stream, Then Close Reader

For UTF-8 text files, this is the preferred pattern:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LineCounter {
    private LineCounter() {}

    public static long countNonBlank(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            return reader.lines()
                    .filter(line -> !line.isBlank())
                    .count();
        }
    }
}
~~~

This is a **compilable utility class** without `main`. To use it, call `LineCounter.countNonBlank(path)` with an existing file. `String.isBlank()` was introduced in Java 11; the example works with Java 17+.

- `Files.newBufferedReader` creates a `BufferedReader` bound to the file and using an explicit charset.
- `try-with-resources` keeps the reader open throughout `count()`.
- When the `try` block exits (even due to an exception), `reader.close()` is invoked.
- It is not strictly necessary to separately wrap the temporary stream in `try-with-resources` in this example, because the stream from `reader.lines()` does not own closing the reader; **the reader is the resource to manage**.
- If an I/O error occurs while `count()` is traversing, note that the exception travels as an `UncheckedIOException`; `throws IOException` in the signature above mainly covers errors opening/closing the reader and does not automatically convert lazy read exceptions back to checked exceptions.

If an application wants the API to always report read errors as `IOException`, you can unwrap `UncheckedIOException`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CheckedLineCounter {
    private CheckedLineCounter() {}

    public static long countNonBlank(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            try {
                return reader.lines()
                        .filter(line -> !line.isBlank())
                        .count();
            } catch (UncheckedIOException exception) {
                throw exception.getCause();
            }
        }
    }
}
~~~

This second class also has no `main`; it demonstrates returning the I/O cause to a checked-exception contract. Do not catch all `RuntimeException`s and treat them all as I/O errors: processing errors inside `map/filter` could be programming or data bugs.

## 5. Runnable Java 17+ Example: Closing the Stream Still Leaves the Reader Open

The example tracks `close()` on the source itself to observe this behavior without depending on how the operating system holds file handles.

Create file **`LinesOwnershipDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import java.util.stream.Stream;

public class LinesOwnershipDemo {
    static final class TrackedReader extends StringReader {
        private boolean closed;

        TrackedReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            closed = true;
            super.close();
        }

        boolean isClosed() {
            return closed;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackedReader source = new TrackedReader("alpha\n\nbeta\n");

        try (BufferedReader reader = new BufferedReader(source)) {
            try (Stream<String> lines = reader.lines()) {
                List<String> values = lines
                        .filter(line -> !line.isEmpty())
                        .toList();
                System.out.println("values=" + values);
            }

            System.out.println("afterStreamClose=" + source.isClosed());
        }

        System.out.println("afterReaderClose=" + source.isClosed());
    }
}
~~~

Compile and run:

~~~bash
javac LinesOwnershipDemo.java
java LinesOwnershipDemo
~~~

**Exact stdout:**

~~~text
values=[alpha, beta]
afterStreamClose=false
afterReaderClose=true
~~~

Explanation:

1. `TrackedReader` records when its `close()` method is called.
2. `BufferedReader` wraps `TrackedReader` and `lines()` creates a pipeline processing `alpha`, the empty line, and `beta`.
3. `filter` removes empty lines; `toList()` consumes the stream. `Stream.toList()` was added in Java 16 and returns an unmodifiable list that does not support adding/removing elements.
4. Exiting `try (Stream<String> lines = ...)` runs `lines.close()`, yet the underlying source is still **not closed**, so it prints `false`.
5. Exiting `try (BufferedReader reader = ...)` invokes `reader.close()`, closing `TrackedReader`, so it prints `true`.

This does not depend on whether the source is a `StringReader` or a file. With files/sockets, the practical consequence of forgetting to close the reader can also be leaking file descriptors/sockets and associated buffers.

**Should you use both `try` blocks?** If the stream has no custom close handler, the stream's `try` is not required to release the file in this example; closing the reader is what matters. However, you may close both if you want to express lifecycle explicitly or if the stream has an `onClose` handler attached. Never assume closing the two layers is the same operation.

## 6. How `BufferedReader.lines()` Differs from `Files.lines()` in Closing Ownership

Even though both return `Stream<String>`, they have **different resource ownership contracts**.

| API | What You Receive | Object That Must Be Closed | Correct Structure Example |
| --- | --- | --- | --- |
| `BufferedReader.lines()` | Stream from an **existing** reader | `BufferedReader` created by its owner | `try (BufferedReader r = ...) { r.lines().count(); }` |
| `Files.lines(path, charset)` | Stream reading a file opened by the API | **The returned stream** | `try (Stream<String> s = Files.lines(path, UTF_8)) { s.count(); }` |
| `Stream.of(...)` | Stream over in-memory data | Usually no I/O resource to release | `Stream.of(...).count()` |

`Files.lines` opens a file resource for the stream; calling `close()` on the returned stream releases that operation's file resource. With `BufferedReader.lines()`, closing the stream **does not replace** `reader.close()`.

### Complete Example Comparing Both

Create file **`FileLinesDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("java-lines-", ".txt");

        try {
            Files.writeString(file, "red\r\n\r\nblue\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                long nonBlank = reader.lines()
                        .filter(line -> !line.isBlank())
                        .count();
                System.out.println("nonBlank=" + nonBlank);
            }

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long blank = lines
                        .filter(String::isBlank)
                        .count();
                System.out.println("blank=" + blank);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Run with Java 17+:

~~~bash
javac FileLinesDemo.java
java FileLinesDemo
~~~

Stdout:

~~~text
nonBlank=2
blank=1
~~~

The temp file contains `red`, a blank line, and `blue`. The first block **closes the reader** via `try-with-resources`. The second block **closes the stream returned by `Files.lines`** via `try-with-resources`. The `finally` block deletes the temp file after both reading resources are closed, even if processing fails.

Note: testing on a temp file does not prove "closing the stream from `BufferedReader.lines` is enough"; that case was verified using `TrackedReader` in the previous section.

## 7. Critical Bug: Returning a Stream from a Closed Reader

The following pattern often appears when trying to write a "convenience" method returning `Stream<String>`:

~~~java
// WRONG: lines are only read when the caller starts a terminal operation.
static java.util.stream.Stream<String> broken(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(
                         path, java.nio.charset.StandardCharsets.UTF_8)) {
        return reader.lines();
    } // Reader is already closed before the caller has a chance to traverse the stream.
}
~~~

`lines()` is lazy. When `broken` returns, the `try` block finishes so the reader is already closed. A caller invoking `count()` or `toList()` cannot consume the source properly and typically receives an `UncheckedIOException` from attempting to read from a closed stream.

There are two proper designs, depending on who owns the resource.

### Approach A: Process Everything While the Reader Is Still Open

If the method needs to return **results**, execute the terminal operation inside `try`:

~~~java
static java.util.List<String> loadNonBlank(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(
                         path, java.nio.charset.StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.isBlank())
                .toList();
    }
}
~~~

Only use this approach when the number of lines held in memory is **bounded and reasonable**. `toList()` materializes every line; for very large files, building a list can consume substantial RAM. If the task only needs counts, summary statistics, or writing results to another destination, streaming inside the `try` block is more appropriate.

### Approach B: Return a Stream with Explicit File Ownership

If an API intentionally hands a file-reading stream to the caller, use `Files.lines`:

~~~java
static java.util.stream.Stream<String> openLines(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.lines(
            path, java.nio.charset.StandardCharsets.UTF_8);
}
~~~

The caller must use:

~~~java
try (java.util.stream.Stream<String> lines = openLines(path)) {
    lines.filter(line -> !line.isBlank())
         .forEach(System.out::println);
}
~~~

These are **code snippets** (the method needs to be inside a class, with a `path` variable and `IOException` declared/handled at the caller). `Files.lines` creates a stream that closes the file resource when the stream is closed; the method documentation should clearly state that the caller **owns and must close** the stream, even when the terminal operation stops early or throws an exception.

Do not mechanically apply the trick "attach `onClose(reader::close)`" because `BufferedReader.close()` can throw checked `IOException` while `onClose` takes a `Runnable`. Wrapping exceptions and close contracts manually requires care; when the source is a file, `Files.lines` or closing the reader directly in the consuming scope is usually clearer.

## 8. How to Handle Lazy Reading Exceptions

`BufferedReader.readLine()` directly declares `throws IOException`. However, `Stream<String>` terminal operations do not declare checked `IOException`. Consequently, when the underlying read fails during stream traversal, Java wraps the cause in an `UncheckedIOException`.

The standalone example creates an intentionally failing source to demonstrate this. Create **`LinesIOExceptionDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.UncheckedIOException;
import java.util.Objects;

public class LinesIOExceptionDemo {
    static final class FailingReader extends Reader {
        @Override
        public int read(char[] buffer, int offset, int length)
                throws IOException {
            Objects.checkFromIndexSize(offset, length, buffer.length);
            if (length == 0) {
                return 0;
            }
            throw new IOException("simulated read failure");
        }

        @Override
        public void close() {
            // No real resource needs to be released in this demo.
        }
    }

    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new FailingReader())) {
            try {
                reader.lines().count();
            } catch (UncheckedIOException exception) {
                System.out.println("cause="
                        + exception.getCause().getMessage());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac LinesIOExceptionDemo.java
java LinesIOExceptionDemo
~~~

Stdout:

~~~text
cause=simulated read failure
~~~

The error occurs **inside `count()`**, i.e., when the stream actually needs to read lines. When closing the reader, `close()` can still throw its own `IOException`; `try-with-resources` handles closing while an exception is already active and can record the close exception as a *suppressed exception*. Translating `UncheckedIOException` back into `IOException` at an API boundary is a sensible choice if the application's contract requires consistent checked exceptions.

With `Files.lines`, an error **opening the file** may throw `IOException` at the `Files.lines(...)` call site, whereas an error **reading further during traversal** can also become an `UncheckedIOException`. Using `try-with-resources` remains vital whether the terminal operation completes normally or fails.

## 9. Reading Lines, Line Terminators, and Empty Lines

`BufferedReader.readLine()` (and hence `lines()`) splits lines on `\n` (LF), `\r` (CR), or the `\r\n` (CRLF) pair. Both **strip** the terminator from the returned string.

| Source character content | Stream elements |
| --- | --- |
| `"A\nB"` | `"A"` and `"B"` |
| `"A\r\nB\n"` | `"A"` and `"B"` |
| `"\n"` | One element `""` |
| `"A\n\nB"` | `"A"`, `""`, `"B"` |
| Empty string `""` | No elements |

True empty lines (`""`) still appear in the stream; `filter(String::isBlank)` keeps whitespace-only lines if your goal is to count them, while `filter(line -> !line.isBlank())` removes them. `String.isBlank()` matches strings containing only whitespace characters as defined by Java; it differs from `isEmpty()`, which only checks for length 0.

`lines()` is unsuitable if you need to preserve **exact terminators**, such as a file-copy tool that must preserve CRLF/LF at every position. In that case, use `BufferedReader.read(char[])` followed by `Writer.write(char[], off, count)` so terminators are not stripped, or use byte streams/`Files.copy` when exact bytes must be preserved.

In addition, `Stream<String>` operates in units of **lines**, not byte counts or Unicode code points. Charset belongs to the step converting file bytes into a `Reader`; always specify UTF-8 (or the protocol-mandated charset) explicitly rather than guessing the encoding.

## 10. Mind the Reader Position and Sharing Across Places

### Do Not Read Competingly from the Same Reader Inside a Terminal Operation

Avoid:

~~~java
// WRONG: directly interfering with the same reader inside a consuming pipeline.
reader.lines().forEach(line -> {
    try {
        System.out.println(reader.readLine());
    } catch (java.io.IOException exception) {
        throw new java.io.UncheckedIOException(exception);
    }
});
~~~

Here the pipeline and the callback both consume from one reader. Results are not guaranteed: lines may be lost, data skipped, or the reader left in an unpredictable state.

Do not concurrently hand one `BufferedReader` to two threads reading via `reader.lines()` and `reader.readLine()`. Even though some operations have internal synchronization, two consumers still compete over **a single stream position**. Designing one owner for the read loop that then dispatches decoded data to other components is safer and easier to control.

### Do Not Rely on Position After Finishing a Pipeline

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String first = reader.lines().findFirst().orElse(null);
    // Do not rely on the assumption that the next readLine() is the second line.
}
~~~

This snippet requires importing `BufferedReader`, `Files`, `Path`, and `StandardCharsets`, and handling `IOException`. The `BufferedReader.lines()` API does not guarantee a specific reader position after a terminal operation. If you genuinely need to read the first line and then continue sequentially from line two, write it with `readLine()` in a single reading loop or position-controlled parser instead of mixing the two models.

### Should You Use `parallel()`?

`reader.lines().parallel()` does not turn a single `Reader` source into multiple independent read sources. Splitting/reading behavior depends on implementation; file I/O has sequential costs, and callbacks with side effects may not preserve order with `forEach`. Usually you should read sequentially from one reader; if parallel CPU processing is needed, consider a queue/batch design or partitioning data with clear boundaries. Only parallelize once you have measured and controlled ordering, shared state, and resource lifecycles.

## 11. Stream Close Handlers Differ from Closing the Reader Source

A `Stream` lets you register `onClose(Runnable)`:

~~~java
try (java.util.stream.Stream<String> stream =
             java.util.stream.Stream.of("A", "B")
                     .onClose(() -> System.out.println("stream closed"))) {
    System.out.println(stream.count());
}
~~~

The snippet above can be placed inside a Java method; output:

~~~text
2
stream closed
~~~

`onClose` executes when **`stream.close()` is called** (here via `try-with-resources`), not automatically after the `count()` terminal operation. Therefore, an algorithm that calls `count()`/`findFirst()` and forgets to close can still skip resource-close handlers attached to the stream.

With `BufferedReader.lines()`, there is no default close handler that automatically closes the reader. If you design your own wrapper returning a stream with a reader-closing handler, clearly decide ownership and how to translate checked `IOException` from `Reader.close()` into an exception compatible with `Runnable`. When transferring closing ownership is not truly needed, the simplest approach remains keeping both stream consumption and closing `BufferedReader` in **the same scope**.

## 12. Using `Stream<String>` Saves Memory, but Infinite Safety Is Not Guaranteed

A pipeline like:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    long count = reader.lines().filter(s -> !s.isBlank()).count();
}
~~~

typically avoids holding the entire file in RAM; data is read sequentially and aggregated into a count. Even so:

- **A single individual line** can still be huge. `readLine()` must build a string for the entire line, so `lines()` imposes no line-length limit.
- `toList()`, `collect(...)`, or `sorted()` can accumulate much or all of the data. Streaming does not always imply constant memory.
- `limit(100)` only limits the number of **lines**, not how many characters each line has, and does not close the reader.
- `findFirst()`/`anyMatch()` can stop early, yet the `Reader` remains a resource that must be closed.
- For untrusted input or sockets, enforce record size limits, timeouts/cancellation policies, encoding handling, and explicit framing. `lines()` can block waiting for a line break or EOF if the peer keeps the connection open.

If you need to enforce a **byte/character limit per line while reading**, use a parser that reads character-by-character/chunk-by-chunk with bounded counting before accumulating, or a protocol with explicit length fields. Checking `line.length()` after `lines()` has already allocated an oversized string may be too late.

## 13. Common Mistakes and How to Fix Them

**Mistake 1 — Closing only the stream from `BufferedReader.lines()`.**  
Closing this stream does not close the underlying reader. Close `BufferedReader` in `try-with-resources` when the method owns it.

**Mistake 2 — Returning a lazy stream out of `try (BufferedReader...)`.**  
The reader closes immediately on return, before the caller has started reading. Run the terminal operation while still in the open scope, or return `Files.lines` with a contract that the caller closes the stream.

**Mistake 3 — Assuming a terminal operation automatically calls `close()`.**  
Completing `count()`, `findFirst()`, or `toList()` does not guarantee `stream.close()` was invoked. `onClose` handlers run only when the stream is closed; close the reader via proper scoping.

**Mistake 4 — Confusing `UncheckedIOException` with direct `IOException`.**  
Lazy read failures via `lines()` can throw `UncheckedIOException` at the terminal operation. Do not handle checked exceptions only when opening the file while ignoring this failure path.

**Mistake 5 — Mixing `readLine()` into the pipeline or relying on position after a terminal operation.**  
The reader shares one character source and one cursor; mixing operations produces undefined results. Pick one consistent traversal mechanism.

**Mistake 6 — Confusing `Files.lines()` and `BufferedReader.lines()` on closing ownership.**  
`Files.lines` hands over a stream that must be closed to close the file opened by the API itself; `BufferedReader.lines()` builds a stream over an existing reader whose caller/owner must still close the reader.

**Mistake 7 — Assuming a stream element retains line-ending characters.**  
`lines()` strips LF/CR/CRLF; it is unsuitable for tasks that must preserve separator characters or raw bytes.

**Mistake 8 — Calling `toList()` on unbounded files or treating `limit` as line-size protection.**  
`toList()` accumulates results; `limit` counts elements without checking each element's length. Enforce appropriate bounds at read time.

## 14. Pre-Production Project Checklist

- [ ] Is it clear **who opens** the `BufferedReader` and **who closes** it?
- [ ] Does `reader.lines()`'s terminal operation run while the reader is definitely still open?
- [ ] If an API returns `Files.lines`, does the caller use `try-with-resources` to close the stream itself?
- [ ] Are you avoiding using `stream.close()` as proof that the reader has closed?
- [ ] Have you accounted for `UncheckedIOException` if a read error occurs during pipeline execution?
- [ ] Are you avoiding mixing `lines()` traversal with direct reads on the same reader or assuming cursor position after the stream ends?
- [ ] If using `findFirst`/`limit`, is the reader still closed even when the pipeline consumes only a few lines?
- [ ] Is the charset explicitly specified, and are newlines and blank lines handled per requirements?
- [ ] If long lines or network data are possible, are protocol limits/timeouts enforced?
- [ ] Are you avoiding keeping all data in RAM unnecessarily?

### Self-Check Questions

**1.** Does calling `reader.lines().filter(...).count()` automatically close `reader`?  
**Answer:** No. Place the `BufferedReader` you own inside `try-with-resources`.

**2.** If you write `try (Stream<String> stream = reader.lines()) { ... }`, is `reader` closed after the `try` block?  
**Answer:** Not by `stream.close()`. The reader is closed only if there is a separate action/contract (for example, the reader's own closing scope).

**3.** For `Files.lines(path, UTF_8)`, which object must be closed?  
**Answer:** Close the `Stream<String>` returned by `Files.lines` using `try-with-resources` to release the associated file resource.

**4.** Why should you not return `reader.lines()` from a method where the reader is created inside `try-with-resources`?  
**Answer:** The stream is lazy; the reader closes before the caller invokes a terminal operation.

**5.** `reader.lines().findFirst()` reads the first line and stops. Can you be sure the next `reader.readLine()` returns the second line?  
**Answer:** No. There is no guarantee regarding reader position after a stream terminal operation.

**6.** How is an I/O error reported while a stream is running `count()`?  
**Answer:** Typically as an `UncheckedIOException` holding the original `IOException` in `getCause()`.

**Key takeaway:** `BufferedReader.lines()` is a way to **traverse lines** with the Stream API, whereas `BufferedReader` is what **manages the reading source**. Consume the stream while the reader is open and close the reader by its proper owner. With `Files.lines()`, the returned stream itself is the resource that must be closed.
