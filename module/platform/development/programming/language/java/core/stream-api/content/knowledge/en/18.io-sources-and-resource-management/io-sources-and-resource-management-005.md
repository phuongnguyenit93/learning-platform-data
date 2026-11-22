# Registering Close Handlers with `onClose` in Java Stream API

When processing data with the Java Stream API, a pipeline typically consists of **data source -> intermediate operations -> terminal operation**. However, completing a terminal operation such as `count()`, `collect()`, or `forEach()` **does not mean the stream is closed**. This is especially important when the data source holds system resources, such as a file read via `Files.lines()`.

`onClose(Runnable)` lets you register an action to be executed **when the stream is closed**. Combining `onClose` with `try-with-resources` makes resource release, logging, and cleanup explicit, even when processing encounters an exception.

## 1. What Does `onClose` Do in the Stream Lifecycle?

`Stream<T>` inherits this method from `BaseStream<T, S>`:

~~~java
S onClose(Runnable closeHandler);
~~~

This method returns an equivalent stream with an additional **close handler**. It is not a terminal operation; calling `onClose` does not traverse elements, does not close the source, and does not immediately run the handler.

A pipeline has two distinct milestones to distinguish:

1. **Pipeline execution:** the terminal operation pulls data from the source and processes the required elements.
2. **Pipeline closing:** calling `close()` (directly or via `try-with-resources`), which triggers the registered handlers.

~~~text
Source stream ── filter/map/... ── count()/collect()/...  [data processing]
      │
      └── onClose(handler A) ── onClose(handler B)
                    │                  │
                    └──── close() ─────┘                  [cleanup]
~~~

Not every stream needs to be closed: with in-memory data sources such as `Stream.of(...)` or `list.stream()`, there are usually no external resources to release. Conversely, a stream reading data from a file may own I/O resources that must be closed on time. `onClose` is an extension point of the closing step; **it does not replace calling `close()`**.

## 2. Basic Example: Handler Runs Only on Close

~~~java
import java.util.stream.Stream;

public class OnCloseDemo {
    public static void main(String[] args) {
        try (Stream<String> names = Stream.of("An", "Binh", "Chi")
                .filter(name -> name.length() >= 3)
                .onClose(() -> System.out.println("Stream closed"))) {

            long count = names.count();
            System.out.println("Valid name count: " + count);
            System.out.println("Executed terminal operation");
        }
    }
}
~~~

Output:

~~~text
Valid name count: 2
Executed terminal operation
Stream closed
~~~

The handler is called after leaving the `try` block because `try-with-resources` automatically invokes `close()` on `names`. If you omit `try-with-resources` and do not call `close()`, calling `count()` still finishes computing, but does not automatically trigger the handler.

Register `onClose` **before** the terminal operation. A stream cannot be reused after a terminal operation has run; attempting to build a new pipeline on an already-consumed stream can throw `IllegalStateException`.

## 3. Important Case: Reading a File with `Files.lines()`

`Files.lines(Path, Charset)` creates a stream of text lines. Data is read as the pipeline demands it, and this stream holds an I/O resource during use. The safe approach is to declare the stream in `try-with-resources`.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

public class CountErrorLines {
    public static void main(String[] args) throws IOException {
        Path logFile = Paths.get("application.log");

        try (Stream<String> errorLines = Files.lines(logFile, StandardCharsets.UTF_8)
                .filter(line -> line.contains("ERROR"))
                .onClose(() -> System.out.println("Closed log-reading stream"))) {

            long errorCount = errorLines.count();
            System.out.println("ERROR line count: " + errorCount);
        }
    }
}
~~~

In this example:

- `Files.lines(...)` opens the I/O source and installs the mechanism to close the source when the stream closes.
- `filter(...)` selects lines containing `ERROR` without loading the entire file into a list.
- `onClose(...)` adds an action recording the close step; it is not where reading or filtering takes place.
- When leaving `try` (even if an exception occurs), `close()` is called; both the closing mechanism of `Files.lines` and the additional handler are executed.

Opening the file can throw `IOException`. I/O errors occurring while the stream is being traversed can appear as `UncheckedIOException`; handle them according to your application's error policy. `onClose` does not catch or ignore these errors.

**Ownership rule:** the component that creates a resource-backed stream must ensure someone is responsible for closing it. If a method returns the stream to a caller, explicitly specify that the caller must use `try-with-resources`.

## 4. Attaching `onClose` to Close Self-Managed Resources

Not every data source attaches a closing action automatically. For instance, `BufferedReader.lines()` creates a stream from a reader, but closing that stream does not automatically guarantee the reader is closed. You can link their lifecycles using `onClose`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class ReaderStreams {
    public static Stream<String> openLines(Path path) throws IOException {
        BufferedReader reader =
                Files.newBufferedReader(path, StandardCharsets.UTF_8);

        return reader.lines().onClose(() -> {
            try {
                reader.close();
            } catch (IOException ex) {
                throw new UncheckedIOException("Cannot close reader", ex);
            }
        });
    }

    public static long countNonBlankLines(Path path) throws IOException {
        try (Stream<String> lines = openLines(path)) {
            return lines.filter(line -> !line.trim().isEmpty()).count();
        }
    }
}
~~~

Here, `reader.lines()` supplies the lines; the close handler is responsible for calling `reader.close()`. Because `Runnable.run()` does not declare checked exceptions, the handler must handle `IOException` locally or wrap it in `UncheckedIOException` to report the failure to the caller. The caller of `openLines` still **must close the stream** for the handler to run.

If you simply need to read a file line by line, prefer `Files.lines(...)` to use the built-in resource management directly. Manually attaching `onClose` is appropriate when building a stream source from a resource actively managed by the application.

## 5. Multiple Close Handlers: Order and Exceptions

A pipeline can register multiple handlers, even at different intermediate steps:

~~~java
import java.util.stream.Stream;

public class MultipleCloseHandlers {
    public static void main(String[] args) {
        try (Stream<Integer> numbers = Stream.of(1, 2, 3)
                .onClose(() -> System.out.println("Close A"))
                .filter(number -> number > 1)
                .onClose(() -> System.out.println("Close B"))) {

            System.out.println("Element count: " + numbers.count());
        }
    }
}
~~~

Output:

~~~text
Element count: 2
Close A
Close B
~~~

Close handlers are executed **in the order they were registered**. If one handler throws an exception, the remaining handlers **are still called**. The first exception raised during closing is propagated to the caller; subsequent exceptions are attached to it as *suppressed exceptions*:

~~~java
import java.util.stream.Stream;

public class CloseExceptionDemo {
    public static void main(String[] args) {
        try (Stream<Integer> stream = Stream.of(1, 2)
                .onClose(() -> {
                    throw new IllegalStateException("Close error A");
                })
                .onClose(() -> {
                    System.out.println("Handler B still runs");
                    throw new IllegalArgumentException("Close error B");
                })) {

            System.out.println(stream.count());
        } catch (RuntimeException ex) {
            System.out.println("Primary exception: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("Suppressed exception: "
                        + suppressed.getMessage());
            }
        }
    }
}
~~~

In the example, handler B still runs even though handler A throws an exception. The exception from A is the primary exception of the close operation, while the exception from B is attached so no error information is lost.

There is another layer of exception handling when using `try-with-resources`: if **the body of the `try` block already threw an exception**, that exception takes precedence as the primary exception, and any exception thrown by `close()` is attached as suppressed. Therefore, when investigating errors, inspect `Throwable.getSuppressed()` as well.

## 6. Distinguishing Related Mechanisms

| Mechanism | When does it act? | Purpose |
|---|---|---|
| `onClose(handler)` | Registration only adds the handler; handler runs when the stream closes | Add cleanup logic, logging, or custom resource release |
| `close()` | When called directly or by `try-with-resources` | Close the pipeline and run close handlers |
| `try-with-resources` | Automatically calls `close()` when leaving the `try` scope | Ensure closing even when processing fails |
| `count()`, `collect()`, `forEach()` | When the terminal operation is called | Consume or process elements; does not automatically close the stream |
| `peek(action)` | When elements actually pass through that step during execution | Observe elements; not a close callback |

`onClose` is typically only needed when an extra action is required at close time. For I/O streams that already have built-in closing behavior like `Files.lines`, **`try-with-resources` is the essential step**; you do not have to add `onClose` just to call `close()` again.

## 7. Common Mistakes and How to Avoid Them

**Confusing pipeline completion with resource closing.** Calling `lines.count()` and dropping the `lines` variable does not guarantee immediate release of I/O resources. Wrap the entire stream usage in `try-with-resources`.

**Registering a handler without closing the stream.** `onClose` does not behave like a standalone `finally`. Without `close()`, the handler will not trigger merely because the pipeline finished or the object is no longer referenced.

**Closing the stream before returning it.** A method returning `Stream<T>` for the caller to process further must not close the stream before returning. Instead, transfer closing ownership to the caller and state the usage contract clearly.

**Using `onClose` to process individual elements.** A close handler is tied to the pipeline lifecycle, not invoked once per element. Per-element work belongs in `map`, `filter`, `forEach`, or corresponding operations.

**Ignoring cleanup errors.** If a resource-closing handler can throw `IOException`, handle or convert the exception deliberately. Avoid swallowing errors silently; check suppressed exceptions when multiple failures happen together.

## 8. Self-Practice Exercises

1. Create a stream with `Stream.of("a", "b")`, attach two `onClose` handlers that print `A` and `B` in order, then call `count()`. Observe the output before and after calling `close()` to verify when handlers execute.
2. Read a UTF-8 file via `Files.lines`, filter non-empty lines, and count them. Use `try-with-resources` and `onClose` to log when the stream closes. Try throwing an exception inside the `try` block and verify the handler still runs.
3. Register two handlers that each throw a different exception. Use `getSuppressed()` to verify that error information from both handlers is preserved.

**Key takeaway:** `onClose` defines *what to do on close*; `close()` performs *the closing action*; `try-with-resources` guarantees *closing happens at the right time*. Combining these three mechanisms properly keeps Java Stream I/O pipelines safe and maintainable.
