# Testing Resource Closure on Early Exit or Exceptions

> **Chapter:** Debugging and Testing Pipelines  
> **Module:** `JAVA_STREAM_API` — learning declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, and `collect`; practicing grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers while recognizing state, resource, and performance limits.

A Java Stream pipeline can return the exact right result yet still **leak resources**. For example, a program reads the first few lines from a file with `Files.lines(...).limit(5)`, or finds a match with `findFirst()`, and forgets to close the Stream. The fact that data processing has finished **does not mean** the underlying file handle, directory stream, or I/O resource was released.

An even trickier situation arises when a lambda in `map`, `filter`, or a terminal operation throws an exception. Cleanup code placed after the terminal operation may never run. This lesson teaches how to establish **resource ownership** properly using `try-with-resources`, write tests observing `onClose`, test exceptions both during processing and during closing, and avoid confusing Stream short-circuiting with resource closure.

The examples run on **Java 17+**, requiring no external libraries beyond the JDK. Assertions throw `AssertionError` explicitly so tests run without enabling `-ea`.

## 1. Three Distinct Events: Consuming, Stopping, and Closing

In the Java Stream API, distinguish these events:

| Event | Example | Automatically calls `close()`? |
| --- | --- | --- |
| **Terminal operation finishes normally** | `toList()`, `count()`, `sum()` | **No**. |
| **Terminal operation short-circuits** | `findFirst()`, `anyMatch(...)`, `limit(3).toList()` | **No**. |
| **Terminal operation throws an exception** | `map(...)` throws `IllegalArgumentException` during `toList()` | **No guaranteed close**; requires a resource-management mechanism. |
| **`close()` is called explicitly** | `stream.close()` | **Yes**, invokes registered close handlers. |
| **Exiting a `try-with-resources` block** | `try (Stream<T> s = ...) { ... }` | **Yes**, even on `return` or exception. |

`Stream` extends `BaseStream`, which implements `AutoCloseable`. Therefore, a Stream can be declared inside `try-with-resources`. However, **calling a terminal operation does not automatically close a Stream**. After a terminal operation, a Stream is consumed and cannot be reused, yet *consumed* is not the same state as *closed*.

A lifecycle diagram:

```text
Create Stream from an I/O source
        |
        v
Build intermediate stages (filter/map/limit...)
        |
        v
Terminal operation
        |
        +---- finishes entire source -----------+
        |                                       |
        +---- stops early (findFirst/limit...)--+----> Not necessarily closed
        |                                       |
        +---- throws an exception --------------+
                                                |
                             Exit try-with-resources / call close()
                                                |
                                                v
                                    Close pipeline and close handlers
```

Most Streams backed by collections or arrays hold no I/O resources to release and normally do not need closing. Conversely, Streams backed by files, directory walkers, or application-opened sources must obey **the closing contract** of that source. Never assume any arbitrary API's Stream manages handles automatically.

## 2. Safe Patterns with `Files.lines` and `Files.walk`

For example, reading at most the first five lines of a file:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path path = Path.of("orders.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> firstFive = lines.limit(5).toList();
    System.out.println(firstFive);
} catch (IOException openFailure) {
    System.err.println("Không mở được file: " + openFailure.getMessage());
}
```

`Files.lines` returns a Stream backed by a file resource that **must be closed** after use. `limit(5)` tells the terminal operation to request only a prefix of the source, **without replacing** Stream closure. `try-with-resources` invokes `close()` when exiting the block, even if the file has more than five lines.

`Files.lines` can throw `IOException` when opening the file; I/O errors occurring **during traversal** can also be wrapped in `UncheckedIOException`. The `catch (IOException)` above demonstrates handling open failures, not every runtime read failure. Applications must define error handling for both cases and never swallow exceptions.

Another example is walking a directory and taking at most three file paths:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path root = Path.of("data");

try (Stream<Path> paths = Files.walk(root)) {
    List<Path> firstFiles = paths
            .filter(Files::isRegularFile)
            .limit(3)
            .toList();
    System.out.println(firstFiles);
} catch (IOException openFailure) {
    System.err.println("Không thể bắt đầu duyệt: " + openFailure);
}
```

`Files.walk` likewise holds open resources during traversal; stopping via `limit` does not release those resources. As with `Files.lines`, errors raised during traversal can be `UncheckedIOException`.

**Note:** When using `BufferedReader.lines()`, treat `BufferedReader` as the managed resource and close the reader with `try-with-resources`. Never infer from the method name `lines()` that every source shares the exact same closing policy.

## 3. `onClose`: A Tool for Testing the Close Path

For an in-memory Stream, you can register an `onClose` callback to observe whether `close()` is actually invoked:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger closeCount = new AtomicInteger();

try (Stream<Integer> numbers = Stream.of(1, 2, 3)
        .onClose(closeCount::incrementAndGet)) {
    int first = numbers.findFirst().orElseThrow();
    System.out.println(first);         // 1
    System.out.println(closeCount.get()); // 0: still inside try
}

System.out.println(closeCount.get());  // 1: close has been called
```

This tests **the close-handler invocation path**, not a direct proof that the OS closed a specific file descriptor. `onClose` is ideal for verifying ownership and control flow. To verify actual OS-level resource release, pair it with integration tests for that resource type.

### Why use `AtomicInteger`?

In sequential tests a simple counter might suffice, yet `AtomicInteger` stays safe if exercises expand to multi-threaded scenarios. Even so, **a thread-safe counter does not determine when closing occurs**; `try-with-resources` or `close()` is the behavior being tested.

`onClose` registers a handler that runs **when the pipeline closes**, not a per-element callback, and not `peek`. Never use it to count processed rows.

## 4. Testing Early Exit: `findFirst`, `anyMatch`, `limit`

All three examples require closing the Stream when the source holds resources:

```java
try (Stream<String> lines = Files.lines(path)) {
    String firstError = lines
            .filter(line -> line.startsWith("ERROR:"))
            .findFirst()
            .orElse("(không có lỗi)");
    System.out.println(firstError);
}
```

```java
try (Stream<String> lines = Files.lines(path)) {
    boolean hasError = lines.anyMatch(line -> line.startsWith("ERROR:"));
    System.out.println(hasError);
}
```

```java
try (Stream<String> lines = Files.lines(path)) {
    List<String> preview = lines.limit(10).toList();
    System.out.println(preview);
}
```

In all three examples, `path` is a `Path` pointing to a real file. `findFirst` and `anyMatch` can stop as soon as the condition is met; `limit` can stop after collecting enough elements. **None of them calls `close()` automatically in place of `try-with-resources`.**

Do not write tests assuming lambdas in `filter` or `peek` run exactly N times in **every** pipeline, especially with short-circuiting or parallel execution. What stays stable to assert here is: **correct business output and close handler execution upon leaving scope**.

### Using infinite sources safely under bounds

```java
AtomicInteger closed = new AtomicInteger();

try (Stream<Integer> values = Stream.iterate(1, n -> n + 1)
        .onClose(closed::incrementAndGet)
        .limit(4)) {
    System.out.println(values.toList()); // [1, 2, 3, 4]
}

System.out.println(closed.get()); // 1
```

`Stream.iterate` here can produce an infinite stream, yet `limit(4)` ensures the terminal operation requests only the first four values. If someone accidentally omits `limit` and calls `toList()`, processing may never terminate, so the `close` at block exit is never reached either. In automated short-circuit tests, configure a **test-runner timeout** to avoid hanging the suite on logic bugs.

## 5. Mid-Pipeline Exceptions: Cleanup Must Still Happen

The snippet below is **unsafe** when the Stream is backed by a file or closeable resource:

```java
Stream<String> lines = Files.lines(path);
List<Integer> numbers = lines
        .map(Integer::parseInt)
        .toList();
lines.close(); // Skipped if parseInt throws an exception!
```

A line `"abc"` causes `Integer.parseInt` to throw `NumberFormatException`; the trailing `lines.close()` never executes.

Fix with `try-with-resources`:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<Integer> numbers = lines
            .map(Integer::parseInt)
            .toList();
    System.out.println(numbers);
}
```

If parsing throws an exception and unwinds out of the block, Java still invokes `lines.close()`. The `parseInt` exception propagates outward unless caught at an appropriate application layer.

Avoid manual `finally` blocks when `try-with-resources` expresses ownership cleanly. With multiple resources and close-time exceptions, `try-with-resources` also handles **suppressed exceptions** according to Java's rules.

## 6. When Closing Throws Too: Suppressed Exceptions

Two independent places can fail:

1. **Try body:** `map`/terminal operation throws `IllegalArgumentException`, `UncheckedIOException`, etc.
2. **Resource closing:** a close handler or `close()` throws a `RuntimeException`.

Inside `try-with-resources`, if **the try body already threw an exception**, that exception stays the **primary exception**; any exception thrown during closing is attached to `primary.getSuppressed()` instead of replacing the original processing failure.

```java
import java.util.stream.Stream;

try (Stream<Integer> values = Stream.of(1, 2)
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {
    values.map(n -> {
        if (n == 2) {
            throw new IllegalArgumentException("bad input");
        }
        return n;
    }).toList();
} catch (IllegalArgumentException processingFailure) {
    System.out.println(processingFailure.getMessage()); // bad input
    System.out.println(processingFailure.getSuppressed().length); // 1
    System.out.println(processingFailure.getSuppressed()[0].getMessage());
    // close failed
}
```

Here `close()` was not skipped: it ran and threw; Java preserves the processing error as the **primary cause** while keeping the close failure for diagnostics. In production systems, logging and monitoring should inspect `getSuppressed()` too, especially when both failures occur together.

### Multiple `onClose` handlers

`BaseStream.onClose(...)` allows registering multiple handlers. Handlers run **in registration order**; if one throws, remaining handlers are still executed. The first thrown exception becomes the exception thrown by `close()`, with subsequent exceptions attached as suppressed.

```java
List<String> events = new ArrayList<>();

try (Stream<Integer> values = Stream.of(1)
        .onClose(() -> {
            events.add("first");
            throw new IllegalStateException("first close failed");
        })
        .onClose(() -> {
            events.add("second");
            throw new IllegalArgumentException("second close failed");
        })) {
    values.findFirst();
} catch (IllegalStateException closeFailure) {
    System.out.println(events); // [first, second]
    System.out.println(closeFailure.getSuppressed().length); // 1
}
```

In the complete program in Section 8, these cases are verified via assertions rather than just printed.

## 7. Closing Pipelines and Managing Resource Ownership

When chaining stages on a Stream:

```java
Stream<String> source = Files.lines(path);
Stream<Integer> lengths = source
        .filter(line -> !line.isBlank())
        .map(String::length);
```

`source` and `lengths` belong to **the same pipeline**. Closing any Stream in the pipeline invokes the pipeline's close handlers. Thus, you can wrap the final Stream you consume in `try-with-resources`:

```java
try (Stream<Integer> lengths = Files.lines(path)
        .filter(line -> !line.isBlank())
        .map(String::length)) {
    System.out.println(lengths.limit(3).toList());
}
```

Ownership must be unambiguous: who creates the I/O Stream, who is responsible for closing it, and does the method return a Stream or a materialized list? A method that closes the Stream and returns `List<T>` is usually much simpler to use safely. If a method **returns an open Stream**, document clearly that the caller owns closing it and never close it before the caller consumes it.

### Building a custom Stream from a closeable source

If an application builds a Stream via `StreamSupport.stream(spliterator, ...)` over a resource, that Stream **does not automatically know how to close** your custom resource. Attach `onClose` or manage the source inside its own `try-with-resources` scope.

```java
// Pattern illustration, not standalone runnable code:
// Stream<Record> records = StreamSupport.stream(source.spliterator(), false)
//         .onClose(source::close);
// try (records) {
//     return records.limit(100).toList();
// }
```

Here `source` represents an object with appropriate `spliterator()` and `close()` methods. Plain `Stream`s over `List` or arrays do not need synthetic close handlers just to compute numbers.

### What if `close()` is called twice?

`BaseStream.close()` is **idempotent**: once a Stream is closed, subsequent calls have no further effect. This helps prevent duplicate cleanup, though it is not an excuse to scatter multiple `close()` calls across the codebase.

```java
AtomicInteger closeCount = new AtomicInteger();
Stream<Integer> values = Stream.of(1)
        .onClose(closeCount::incrementAndGet);

values.close();
values.close();
System.out.println(closeCount.get()); // 1
```

Always establish **one clear owner** and one management scope rather than having multiple layers arbitrarily close the same Stream.

## 8. Self-Contained Java 17+ Program: Testing Closure Across All Branches

Save the following program as `StreamResourceClosureTests.java`. To keep the test suite runnable **without creating external files**, we use `Stream.onClose` and an `AtomicInteger` counter as our observation point. These tests verify the `close()` invocation path; Section 9 then outlines integration tests over real I/O sources.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamResourceClosureTests {

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static Stream<Integer> tracked(AtomicInteger closeCount) {
        return Stream.of(1, 2, 3, 4)
                .onClose(closeCount::incrementAndGet);
    }

    static void testFindFirstCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = tracked(closed)) {
            Optional<Integer> first = values
                    .filter(n -> n >= 3)
                    .findFirst();
            check(first.equals(Optional.of(3)), "findFirst sai");
            check(closed.get() == 0,
                    "Terminal operation không tự đóng Stream");
        }

        check(closed.get() == 1, "findFirst không được đóng khi rời try");
    }

    static void testLimitCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = tracked(closed).limit(2)) {
            check(values.toList().equals(List.of(1, 2)),
                    "Sai kết quả limit");
            check(closed.get() == 0,
                    "limit/toList không tự đóng");
        }

        check(closed.get() == 1, "Không đóng sau limit");
    }

    static void testAnyMatchCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = tracked(closed)) {
            check(values.anyMatch(n -> n == 2), "anyMatch sai");
        }

        check(closed.get() == 1, "Không đóng sau anyMatch");
    }

    static void testInfiniteSourceWithLimit() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = Stream
                .iterate(1, n -> n + 1)
                .onClose(closed::incrementAndGet)
                .limit(4)) {
            check(values.toList().equals(List.of(1, 2, 3, 4)),
                    "Nguồn vô hạn không dừng ở 4 phần tử");
        }

        check(closed.get() == 1, "Không đóng nguồn vô hạn có limit");
    }

    static void testTerminalDoesNotAutoClose() {
        AtomicInteger closed = new AtomicInteger();
        Stream<Integer> values = tracked(closed);

        check(values.toList().equals(List.of(1, 2, 3, 4)),
                "toList sai");
        check(closed.get() == 0,
                "toList không được tự gọi onClose");

        values.close();
        check(closed.get() == 1, "close không gọi handler");
        values.close(); // Idempotent.
        check(closed.get() == 1, "Handler chạy hai lần");
    }

    static Optional<Integer> returnEarly(AtomicInteger closed) {
        try (Stream<Integer> values = tracked(closed)) {
            return values.filter(n -> n > 2).findFirst();
        }
    }

    static void testReturnStillCloses() {
        AtomicInteger closed = new AtomicInteger();
        Optional<Integer> found = returnEarly(closed);

        check(found.equals(Optional.of(3)), "Giá trị trả sai");
        check(closed.get() == 1,
                "return không được bỏ qua try-with-resources");
    }

    static void testProcessingExceptionStillCloses() {
        AtomicInteger closed = new AtomicInteger();
        boolean caught = false;

        try (Stream<Integer> values = tracked(closed)
                .map(n -> {
                    if (n == 2) {
                        throw new IllegalArgumentException("invalid row");
                    }
                    return n * 2;
                })) {
            values.toList();
        } catch (IllegalArgumentException expected) {
            caught = "invalid row".equals(expected.getMessage());
        }

        check(caught, "Thiếu ngoại lệ xử lý");
        check(closed.get() == 1,
                "Ngoại lệ trong map làm mất close");
    }

    static void testPrimaryAndSuppressed() {
        AtomicInteger closed = new AtomicInteger();
        boolean caught = false;

        try (Stream<Integer> values = Stream.of(1, 2)
                .onClose(() -> {
                    closed.incrementAndGet();
                    throw new IllegalStateException("cleanup failed");
                })) {
            values.map(n -> {
                if (n == 2) {
                    throw new IllegalArgumentException("bad input");
                }
                return n;
            }).toList();
        } catch (IllegalArgumentException main) {
            caught = "bad input".equals(main.getMessage());
            Throwable[] suppressed = main.getSuppressed();
            check(suppressed.length == 1,
                    "Phải giữ ngoại lệ đóng dưới dạng suppressed");
            check(suppressed[0] instanceof IllegalStateException,
                    "Sai kiểu ngoại lệ đóng");
            check("cleanup failed".equals(suppressed[0].getMessage()),
                    "Sai nguyên nhân đóng");
        }

        check(caught, "Ngoại lệ xử lý không còn là lỗi chính");
        check(closed.get() == 1, "Close handler không chạy");
    }

    static void testMultipleCloseHandlers() {
        List<String> events = new ArrayList<>();
        boolean caught = false;

        try (Stream<Integer> values = Stream.of(1)
                .onClose(() -> {
                    events.add("first");
                    throw new IllegalStateException("close first");
                })
                .onClose(() -> {
                    events.add("second");
                    throw new IllegalArgumentException("close second");
                })) {
            check(values.findFirst().equals(Optional.of(1)),
                    "findFirst sai");
        } catch (IllegalStateException first) {
            caught = "close first".equals(first.getMessage());
            Throwable[] suppressed = first.getSuppressed();
            check(suppressed.length == 1,
                    "Handler lỗi thứ hai phải suppressed");
            check(suppressed[0] instanceof IllegalArgumentException,
                    "Sai ngoại lệ handler thứ hai");
            check("close second".equals(suppressed[0].getMessage()),
                    "Sai thông điệp handler thứ hai");
        }

        check(caught, "Không nhận ngoại lệ close đầu tiên");
        check(events.equals(List.of("first", "second")),
                "Không chạy đủ close handlers theo thứ tự đăng ký");
    }

    static void testParallelEarlyExitCloses() {
        AtomicInteger closed = new AtomicInteger();

        try (Stream<Integer> values = IntStream.range(0, 1_000)
                .parallel()
                .boxed()
                .onClose(closed::incrementAndGet)) {
            check(values.anyMatch(n -> n >= 500),
                    "Không tìm thấy phần tử thỏa điều kiện");
        }

        // Do not count anyMatch callback invocations: parallel execution
        // may evaluate extra elements before short-circuiting completes.
        check(closed.get() == 1,
                "Pipeline song song không được đóng khi rời scope");
    }

    public static void main(String[] args) {
        testFindFirstCloses();
        testLimitCloses();
        testAnyMatchCloses();
        testInfiniteSourceWithLimit();
        testTerminalDoesNotAutoClose();
        testReturnStillCloses();
        testProcessingExceptionStillCloses();
        testPrimaryAndSuppressed();
        testMultipleCloseHandlers();
        testParallelEarlyExitCloses();

        System.out.println("ALL STREAM CLOSE TESTS PASS");
    }
}
```

Run on JDK 17+:

```text
javac StreamResourceClosureTests.java
java StreamResourceClosureTests
```

Expected output when all checks pass:

```text
ALL STREAM CLOSE TESTS PASS
```

This is a self-test program provided in the lesson. Authoring this lesson **does not imply** the program was compiled or executed in the workspace.

## 9. Integration Testing with Real Resources

The `onClose` tests in Section 8 verify **the close invocation path**, yet do not prove the OS released a specific resource or that an external library obeyed its close contract. For `Files.lines` and `Files.walk`, add dedicated integration tests:

1. Create a test file inside a test-owned temporary directory; write several valid lines and one line that triggers a parse failure.
2. Open the Stream with `Files.lines` inside `try-with-resources`, testing `findFirst`, `limit`, and mid-`map` exceptions in turn.
3. After each scope, verify you can perform subsequent file operations appropriate to the platform under test.
4. Also test errors raised mid-read if you can simulate an I/O source that throws on read.
5. Clean up test resources in `finally` or `try-with-resources` so failed tests don't leave stray temp files behind.

**Do not treat file deletion as a universal file-closure check across all operating systems.** On some OSes, a file can be unlinked even while handles remain open; on others, behavior differs. To verify contracts reliably, combine fake/mock resources counting close calls with platform-appropriate integration tests.

A JUnit integration test sketch (outline only; **not standalone runnable code** since it requires the test framework and fixture):

```java
// @TempDir Path tempDir; // JUnit 5
// Path sample = tempDir.resolve("sample.txt");
// Files.writeString(sample, "1\n2\ninvalid\n");
//
// try (Stream<String> lines = Files.lines(sample)) {
//     assertEquals(List.of(1, 2),
//             lines.limit(2).map(Integer::parseInt).toList());
// }
//
// assertThrows(NumberFormatException.class, () -> {
//     try (Stream<String> lines = Files.lines(sample)) {
//         lines.map(Integer::parseInt).toList();
//     }
// });
```

In integration tests, observe when resources close via a dedicated wrapper or library cleanup hooks rather than guessing from thread counts or OS file-locking timing.

## 10. Required Test Matrix for Early Exit and Exceptions

| Case | Terminal / scenario | When does `onClose` run? | What to verify |
| --- | --- | --- | --- |
| Normal, full read | `toList()`, `count()` | When `close()` is called or exiting `try`. | Does not auto-close on terminal completion. |
| Find first match | `findFirst()` | On exiting `try`. | Exact result; closed exactly once. |
| Short-circuit match | `anyMatch(...)` | On exiting `try`. | Independent of how many elements were evaluated. |
| Bounded output | `limit(n).toList()` | On exiting `try`. | Does not read infinitely; still closes pipeline. |
| Early return from method | `return` inside `try` block | Before method returns. | Close handler still runs. |
| Lambda throws exception | `map(...).toList()` fails | On unwinding out of `try`. | Still closes and preserves processing error. |
| Failure only on close | Handler throws | Inside `close()`. | Close failure is not swallowed. |
| Failure in processing **and** close | Both throw | During cleanup on `try` exit. | Close failure is `suppressed` on primary error. |
| Multiple close handlers | First handler throws | As `close()` calls all handlers. | Registration order; later error is suppressed. |
| Repeated `close()` calls | `close(); close()` | Handler runs only the first time. | Idempotency. |
| Parallel early exit | `parallel().anyMatch(...)` | On exiting `try`. | Never count callbacks or assume thread order. |

If a test checks only that `findFirst()` returns the right element **without checking `close()`**, that test fails to test resource ownership. Likewise, if a test checks only that an exception was thrown without verifying closure, resource leaks slip right through.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `toList()`/`sum()` closes every Stream | I/O handles can remain open. | Use `try-with-resources` for closeable sources. |
| Stopping via `findFirst()` and discarding Stream | Terminal stops early while resource stays open. | Wrap the entire pipeline in `try`. |
| Calling `close()` after `map(...).toList()` | Exceptions in lambdas skip the close statement. | Let `try-with-resources` perform cleanup. |
| Using `onClose` as a per-element callback | Miscounts and misunderstands lifecycle. | Use `onClose` strictly to manage/observe closure. |
| Swallowing everything in `catch (Exception)` | Hides critical processing and close errors. | Handle at proper layer and inspect suppressed exceptions. |
| Catching one close exception and assuming later handlers skip | Misses multi-handler close contract. | Verify ordering and suppressed exceptions per API. |
| Asserting exact `peek` counts on `parallel().findAny()` | Test depends on optimizations and scheduling. | Assert output, termination, and close events. |
| Returning an open `Stream` without naming an owner | Caller forgets to close or reads after owner closes. | Document close ownership or return materialized results. |
| Creating a Stream from a custom resource `Spliterator` without a close hook | Stream doesn't know what resource needs cleanup. | Attach `onClose(resource::close)` or manage resource separately. |
| Using file deletion as a universal close test across OSes | Test behavior varies across operating systems. | Combine mock/fake close checks with OS-aware integration tests. |
| Using an infinite source and forgetting `limit` | Terminal never finishes to exit scope. | Define short-circuiting and set test timeouts. |

## 12. Self-Practice Exercises

**Exercise 1 — Does a terminal auto-close?** Predict `counter` after `findFirst()` and after `close()`:

```java
AtomicInteger counter = new AtomicInteger();
Stream<Integer> s = Stream.of(10, 20)
        .onClose(counter::incrementAndGet);

s.findFirst();
int before = counter.get();
s.close();
int after = counter.get();
```

**Answer:** `before == 0`, `after == 1`. The terminal consumed the Stream without automatically invoking the close handler.

**Exercise 2 — Early stop.** If `Files.lines(path)` has 10,000 lines and `limit(1).toList()` returns one line, can you omit `try-with-resources`?

**Answer:** No. `limit` restricts consumption/output, not the obligation to close the file-backed Stream.

**Exercise 3 — Mid-pipeline exception.** Write a test ensuring `NumberFormatException` from `Integer.parseInt` does not prevent `onClose` from running when the Stream is inside `try-with-resources`. Put `"oops"` after a valid line and verify both the exception and the close count.

**Exercise 4 — Two exceptions.** Have the `try` body throw `IllegalArgumentException("body")` and `onClose` throw `IllegalStateException("close")`. Which is primary? Which appears in `getSuppressed()`?

**Answer:** `IllegalArgumentException("body")` is primary, and `IllegalStateException("close")` is attached as suppressed.

**Exercise 5 — Multiple handlers.** Register three `onClose` handlers; the first and third throw exceptions, while the second increments a counter. Verify all three run in registration order, and the third exception is suppressed on the first.

**Exercise 6 — `return` inside `try`.** Write a method returning `findFirst()` directly inside `try (Stream<T> s = ...)`. Why doesn't `return` bypass `close()`?

**Answer:** `try-with-resources` generates cleanup executed upon leaving scope, including exiting via `return`. Closing completes before the caller receives the return value.

**Exercise 7 — Custom resource.** An application-defined source provides `spliterator()` and `close()`. Design how to wire `StreamSupport.stream(...)` to resource closure. Analyze who owns closing if a method returns the open Stream to its caller.

**Exercise 8 — Parallel test.** Write a `parallelStream().anyMatch(...)` test on a large list with `onClose` attached. Why should you require only that `onClose` runs on close, without asserting `map` always processes the exact element count seen in one trial?

**Answer:** A parallel Stream may split work, speculatively evaluate extra elements, and stop once one branch finds a match. Callback counts are not a stable contract; `try-with-resources` guarantees closing at scope exit.

## 13. Key Takeaways

- **Terminal operations do not auto-close a Stream**, even after reading the entire source or stopping early with `findFirst`, `anyMatch`, or `limit`.
- Resource-backed sources like `Files.lines`/`Files.walk` require **`try-with-resources`**; `return` statements and mid-pipeline exceptions never bypass cleanup.
- `onClose` attaches/observes pipeline close actions; closing a Stream is idempotent. Testing `onClose` proves the close invocation path, not automatically that all OS handles were released.
- When both processing and closing fail, `try-with-resources` keeps the processing failure as **primary** and records close failures in **suppressed exceptions**; close handlers run in registration order.
- Test **normal completion, early exit, bounded infinite sources, exceptions, multiple handlers, and parallel runs**. Never require fixed callback counts or thread schedules that the API does not promise.
