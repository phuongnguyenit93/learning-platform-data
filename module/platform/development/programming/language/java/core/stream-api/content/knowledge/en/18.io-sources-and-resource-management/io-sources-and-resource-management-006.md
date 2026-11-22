# Execution Order of `onClose` and `suppressed` Exceptions

In the Java Stream API, a pipeline can process data coming from a file, a directory, or a source that requires resource cleanup. When a stream is closed, the cleanup handlers registered via `onClose(...)` are invoked in a deterministic order. If multiple cleanup handlers throw exceptions, Java preserves those errors using **suppressed exceptions** so no information about resource closing is lost.

This lesson belongs to the **I/O Sources and Resource Management** chapter of `JAVA_STREAM_API`. The goal is to understand when `onClose` runs, the execution order of handlers, which exception gets thrown outward, and why `try-with-resources` can produce multiple layers of `suppressed` exceptions.

## 1. `onClose` Is Tied to Closing the Stream, Not Terminal Operations

`BaseStream.onClose(Runnable closeHandler)` registers an action to be executed when the stream is **closed**. Each call to `onClose` returns an equivalent stream with an additional close handler, so a common style is to chain `onClose` calls when creating the stream.

Distinguish these events:

| Event | What happens? |
| --- | --- |
| `count()`, `collect()`, `forEach()`, `findFirst()`... | The terminal operation triggers or completes pipeline processing; **it does not automatically call `close()`**. |
| `stream.close()` | Closes the stream and triggers all registered close handlers. |
| Exiting a `try-with-resources` block | Java automatically calls `close()` on declared resources, even if processing fails. |

Short example:

```java
import java.util.stream.Stream;

public class CloseLifecycleDemo {
    public static void main(String[] args) {
        Stream<String> stream = Stream.of("A", "B")
                .onClose(() -> System.out.println("stream closed"));

        System.out.println(stream.count()); // 2
        System.out.println("count executed");
        stream.close();
    }
}
```

Output:

```text
2
count executed
stream closed
```

Notice that the line `stream closed` appears only after `close()`. When working with `Files.lines(...)`, `Files.walk(...)`, or similar I/O sources, do not simply invoke a terminal operation and abandon the stream: those sources must be closed to release their corresponding resources. With a purely in-memory stream such as `Stream.of(...)`, the example above only demonstrates lifecycle behavior; there is no file to release.

## 2. Execution Order of Close Handlers

By the contract of `BaseStream.onClose`, **close handlers run in the order they were registered**. If the first handler throws an exception, Java still attempts to run all remaining handlers.

For example, when registering `H1`, `H2`, `H3`, `H4` in sequence:

```text
Register: H1 -> H2 -> H3 -> H4
close():  H1 -> H2 -> H3 -> H4
                  |     |
              error A  error B
```

If `H2` throws error A and `H3` throws error B, `H4` **still runs**. Error A becomes the primary exception of the `close()` call; error B is stored in A's list of `suppressed` exceptions.

Run the following complete program:

```java
import java.util.stream.Stream;

public class OnCloseOrderDemo {
    public static void main(String[] args) {
        try (Stream<String> stream = Stream.of("A", "B")
                .onClose(() -> System.out.println("close-1"))
                .onClose(() -> {
                    System.out.println("close-2");
                    throw new IllegalStateException("error-2");
                })
                .onClose(() -> {
                    System.out.println("close-3");
                    throw new IllegalArgumentException("error-3");
                })
                .onClose(() -> System.out.println("close-4"))) {

            System.out.println(stream.count());
        } catch (RuntimeException error) {
            System.out.println("primary=" + error.getMessage());
            for (Throwable suppressed : error.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Output:

```text
2
close-1
close-2
close-3
close-4
primary=error-2
suppressed=error-3
```

Three rules follow from this output:

1. `close-1` through `close-4` execute in registration order.
2. Failure in `close-2` does not prevent `close-3` and `close-4` from running.
3. The first exception thrown by a handler is the exception thrown outward by `close()`; later exceptions appear in `getSuppressed()` of that first exception.

When only one handler fails, `getSuppressed()` may be an empty array; when multiple handlers fail, this array contains the additional errors. Special case: if a later handler rethrows **the exact same `Throwable` instance** that is already the primary exception, Java does not attach that object as suppressed to itself.

## 3. How Does `suppressed` Differ from `cause`?

`Throwable` has two mechanisms expressing different relationships:

| API | Meaning | Common situations |
| --- | --- | --- |
| `getCause()` | The exception that caused or was wrapped by the current exception. | `new UncheckedIOException(ioException)` or `new IllegalStateException("...", cause)`. |
| `getSuppressed()` | Secondary exceptions recorded while keeping one primary exception in front. | Multiple close handlers failing together; `close()` failing when the `try` body also failed. |

For cleanup errors, `suppressed` is very useful: the program can preserve the primary exception as the error signal to handle, while still providing information about other resources that failed to close. You should not infer that a suppressed exception is the `cause` of the primary exception; they are two independent relationships.

When analyzing incidents, inspect both the main exception and `getSuppressed()`. Some loggers or standard stack trace printouts display `Suppressed: ...` branches, but the most direct and explicit programmatic way is iterating over `Throwable#getSuppressed()` as in the example above.

## 4. Two Levels of `suppressed` in `try-with-resources`

`try-with-resources` has its own precedence rule. If **the `try` body already threw an exception**, and then `close()` also fails, the exception from the `try` body remains the primary exception; the exception thrown by `close()` is attached to it as `suppressed`.

This combines with the `onClose` rule to form a nested structure:

```text
Error from try body: body-error            <-- primary exception thrown out of try
  Suppressed: close-error-1                <-- thrown by close()
    Suppressed: close-error-2              <-- next onClose handler
```

Compilable, standalone example:

```java
import java.util.stream.Stream;

public class NestedSuppressedDemo {
    public static void main(String[] args) {
        try (Stream<String> stream = Stream.of("A")
                .onClose(() -> {
                    throw new IllegalStateException("close-error-1");
                })
                .onClose(() -> {
                    throw new IllegalArgumentException("close-error-2");
                })) {

            stream.findFirst();
            throw new UnsupportedOperationException("body-error");
        } catch (RuntimeException error) {
            System.out.println("primary=" + error.getMessage());

            for (Throwable closeError : error.getSuppressed()) {
                System.out.println("  suppressed=" + closeError.getMessage());
                for (Throwable laterCloseError : closeError.getSuppressed()) {
                    System.out.println("    nested=" + laterCloseError.getMessage());
                }
            }
        }
    }
}
```

Output:

```text
primary=body-error
  suppressed=close-error-1
    nested=close-error-2
```

Two independent steps occur here:

1. During `close()`, the first handler throws `close-error-1`; the second handler still runs and throws `close-error-2`. `close-error-2` is attached to `close-error-1`.
2. Because the `try` body threw `body-error`, `try-with-resources` keeps `body-error` as the primary error, and attaches the **entire** `close-error-1` exception (along with its nested exception) to `body-error`.

Consequently, outer `error.getSuppressed()` **does not necessarily contain every close error at the same flat level**. To see everything, inspect the suppressed exceptions of each child exception as well. If the `try` body had not failed, `close-error-1` would become the primary exception thrown out of the block.

## 5. Distinguishing Closing Order of *Multiple Resources* vs. `onClose` Order

Do not mix up two rules:

- Within **a single stream**, close handlers run in **registration order**.
- With **multiple resources declared in a single `try-with-resources`**, Java closes resources in **reverse declaration order**.

Example:

```java
import java.util.stream.Stream;

public class MultipleResourcesDemo {
    public static void main(String[] args) {
        try (Stream<String> first = Stream.<String>empty()
                    .onClose(() -> System.out.println("first/H1"))
                    .onClose(() -> System.out.println("first/H2"));
             Stream<String> second = Stream.<String>empty()
                    .onClose(() -> System.out.println("second/H1"))
                    .onClose(() -> System.out.println("second/H2"))) {
            // No terminal operation needed to demonstrate close order.
        }
    }
}
```

Output:

```text
second/H1
second/H2
first/H1
first/H2
```

`second` is closed before `first`; within each stream, `H1` runs before `H2`. When multiple resources throw exceptions, `try-with-resources` still preserves information about failed closes via suppressed exceptions; which exception becomes primary depends on whether the `try` body failed and the resource closing order.

## 6. Application with a File-Reading Stream

A practical example is reading a file line by line. `Files.lines(...)` creates a stream whose underlying source must be closed. You can register an extra handler to record when usage of the source finishes:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class ReadLinesDemo {
    public static long countNonEmptyLines(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)
                .onClose(() -> System.out.println("Finished using stream"))) {
            return lines.filter(line -> !line.isBlank()).count();
        }
    }
}
```

This example uses `String.isBlank()` (Java 11 and later). `try-with-resources` ensures `close()` is called both when processing succeeds and when the pipeline raises an error. Note that `onClose` does not replace the I/O resource-closing mechanism of `Files.lines`; what is required is closing the opened stream itself, while additional handlers are used to attach appropriate cleanup or observation actions.

If closing the file and an additional `onClose` operation both fail, examine the entire exception chain and `suppressed` entries instead of reading only the outermost error message.

## 7. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `collect()` or `forEach()` automatically closes the stream. | Handlers do not run; the I/O source may stay open. | Use `try-with-resources` for streams owning closeable resources. |
| Thinking a throwing handler stops subsequent handlers. | Wrong predictions about cleanup flow and logs. | Remember all handlers are attempted; inspect primary and suppressed errors. |
| Printing only `error.getMessage()`. | Loses track of errors from other close handlers. | Log stack traces and check `getSuppressed()` during investigation. |
| Checking only top-level `error.getSuppressed()`. | Misses `onClose` errors nested under a close exception suppressed by a body error. | Traverse suppressed exceptions of child exceptions when needed. |
| Confusing `getCause()` with `getSuppressed()`. | Misinterprets root cause vs. cleanup failures. | Treat them as two distinct exception relationships. |
| Registering handlers with complex, error-prone side effects. | Increases risk of secondary failures during closing. | Keep handlers focused on concise cleanup with clear resource ownership. |

To test your understanding, consider a stream with three handlers: `A` succeeds, `B` throws `IllegalStateException`, and `C` throws `IllegalArgumentException`. When `close()` is called, all three are still invoked; the exception from `B` is thrown, while the exception from `C` is in `B.getSuppressed()`. If the `try-with-resources` body had previously thrown another exception, the body exception becomes the outermost error and the error from `B` sits in its suppressed list.

**Key takeaway:** terminal operations end processing, while `close()` triggers cleanup; `onClose` handlers run in registration order and do not skip subsequent handlers when one fails; `try-with-resources` preserves body errors and resource-closing errors across layers of suppressed exceptions.
