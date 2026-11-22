# Keeping I/O and Side Effects at Controllable Boundaries

In functional programming with Java, an important principle is to **push I/O operations and side effects to the boundaries of the program**, while the business-rule processing in the middle receives input data and returns clear results. This principle is especially useful when handling **exceptions**: code that reads files, makes network calls, or writes to a database can fail due to the environment, whereas pure computations can be tested with given data.

The goal is not to eliminate all side effects. Applications still need to read, write, send notifications, store data, and write logs. The goal is to **know where they happen, what they depend on, and at which boundary errors are handled**.

## 1. Identifying Side Effects and Boundaries

A function has an *observable side effect* when it modifies or depends on state outside its return value, for example:

- Reading/writing files, sockets, HTTP, databases, queues, or the console.
- Writing logs, sending emails, emitting events, or updating a shared cache.
- Modifying an object/collection that callers can still observe; mutating global variables or shared fields.
- Fetching the current time with `Instant.now()`, generating random values, or reading environment variables. These are **hidden inputs**, causing the same arguments to yield different results.

Conversely, a pure processing function receives all inputs via parameters, returns its result through the return value, and produces no observable side effects. For example:

```java
static long total(int quantity, long unitPrice) {
    if (quantity <= 0 || unitPrice < 0) {
        throw new IllegalArgumentException("Giá trị không hợp lệ");
    }
    return Math.multiplyExact((long) quantity, unitPrice);
}
```

This is an **illustrative snippet placed inside a class**. With the same `quantity` and `unitPrice`, the result or exception always has the same cause. Throwing `IllegalArgumentException` identifies an input error and does not itself cause I/O. Java does not force every exception to be a side effect; what matters here is **predictability, no hidden environment dependencies, and no mutation of external state**.

> Distinction: updating a local variable inside a function is not necessarily an observable side effect, as long as that state does not leak outside. By contrast, `list.sort(...)` on a list passed in by the caller mutates observable data.

## 2. The "Functional Core – Imperative Shell" Model

A processing flow should generally follow this direction:

```text
Input boundary (I/O)     Data processing core          Output boundary (I/O)
Read file / HTTP  --->   Parse -> Validate -> Compute  --->  Write file / DB / HTTP
   IOException             Clear data error                     IOException
```

The **input boundary** converts external system data into Java arguments, such as `List<String>`, `Order`, or `byte[]`. The **processing core** performs transformations by creating new values. The **output boundary** receives the completed result and is responsible for executing effects on the outside world.

From this come three rules:

1. Do not hide file reading, network calls, or logging inside `map`, `filter`, or `reduce` just because they can be written with lambdas.
2. The processing core does not need to know where the file is located, which logger is used, or which HTTP client is initialized. Pass in already-read data, or provide I/O sources/sinks via interfaces at the orchestration layer.
3. Catch, translate, and report errors where the **processing context** is understood: data errors may come from the core; `IOException` is raised by read/write adapters; the decision to retry, stop, or return an error to the user lives at the boundary layer.

The processing core can use `Stream`, `for` loops, `Optional`, or records; using functional syntax does not automatically make code pure.

## 3. Complete Java 17+ Example: Separating Reading, Computation, and Writing

Problem: a source provides each line in the form `code,quantity`. The program validates the input, multiplies the quantity by a fixed unit price of `100`, and outputs `code,amount`. The same processing core can run with fake in-memory data or real files.

Save the entire file as `SideEffectBoundaryDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class SideEffectBoundaryDemo {

    @FunctionalInterface
    interface Source {
        List<String> read() throws IOException;
    }

    @FunctionalInterface
    interface Sink {
        void write(List<String> rows) throws IOException;
    }

    record Order(String code, int quantity) {}

    // Core: validate and parse one line without reading files or printing logs.
    static Order parse(String raw) {
        String[] parts = raw.split(",", -1);
        if (parts.length != 2 || parts[0].isBlank()) {
            throw new IllegalArgumentException("Sai cấu trúc: " + raw);
        }

        int quantity;
        try {
            quantity = Integer.parseInt(parts[1].trim());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Sai số lượng: " + raw, e);
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương: " + raw);
        }
        return new Order(parts[0].trim(), quantity);
    }

    // Core: produce a new value without mutating Order or external systems.
    static String calculate(Order order) {
        long amount = order.quantity() * 100L;
        return order.code() + "," + amount;
    }

    static List<String> transform(List<String> rawLines) {
        return rawLines.stream()
                .map(SideEffectBoundaryDemo::parse)
                .map(SideEffectBoundaryDemo::calculate)
                .toList();
    }

    // Orchestration shell: read once, compute, and only then write once.
    static void run(Source source, Sink sink) throws IOException {
        List<String> input = source.read();
        List<String> output = transform(input);
        sink.write(output);
    }

    public static void main(String[] args) {
        if (args.length != 0 && args.length != 2) {
            System.err.println(
                    "Cách dùng: java SideEffectBoundaryDemo [input.csv output.csv]"
            );
            return;
        }

        try {
            if (args.length == 0) {
                // In-memory adapter: no real file needed to test the core.
                run(
                        () -> List.of("A01,2", "B02,3"),
                        lines -> lines.forEach(System.out::println)
                );
                return;
            }

            Path input = Path.of(args[0]);
            Path output = Path.of(args[1]);

            // Real adapter: I/O is placed at two explicit points.
            run(
                    () -> Files.readAllLines(input, StandardCharsets.UTF_8),
                    lines -> {
                        Files.write(output, lines, StandardCharsets.UTF_8);
                    }
            );
            System.out.println("Đã ghi " + output.getFileName());

        } catch (IOException | IllegalArgumentException e) {
            // The program boundary decides how to report errors externally.
            System.err.println("Không xử lý được: " + e.getMessage());
        }
    }
}
```

Compile and run (JDK 17 or higher):

```bash
javac -encoding UTF-8 SideEffectBoundaryDemo.java
java SideEffectBoundaryDemo
```

Exact stdout output when no arguments are passed:

```text
A01,200
B02,300
```

To use real I/O, create a UTF-8 `input.csv` file with the contents:

```text
A01,2
B02,3
```

Then run:

```bash
java SideEffectBoundaryDemo input.csv output.csv
```

When reading and writing succeed, the console displays `Đã ghi output.csv`; the `output.csv` file contains two lines `A01,200` and `B02,300`. If the path or permissions are invalid, the adapter may throw `IOException` and the `catch` block in `main` reports the error to stderr. The exact message from the operating system may vary.

**Why does this example place the boundary in the right spot?**

- `Source.read()` is the only place that receives data from the environment. `Sink.write(...)` is the place that performs external actions, such as printing or writing a file.
- `parse`, `calculate`, and `transform` do not perform I/O. We can pass `List.of("A01,2")` to `transform` and verify the result without needing files or HTTP mocks.
- `Order` is a `record`, which helps express a clear data value; the result of `calculate` is a new string without mutating the input object.
- `run` receives two behaviors through dedicated interfaces. The interfaces **allow `throws IOException`**, so file read/write lambdas are valid without burying `try/catch` inside every stream element.
- `transform` finishes before `sink.write` is called. If the second line has a syntax error, writing **is not called in that run**. This is an orchestration-order guarantee, not an automatic transaction for `Files.write`.

`Stream.toList()` (Java 16+) produces an unmodifiable result list. In the example, the sink only needs to read the lines for output, so a mutable list is unnecessary.

## 4. Which Boundaries Should Exceptions Cross?

There are two error groups worth distinguishing:

| Error Source | Examples | Where Typically Handled |
| --- | --- | --- |
| Data/business rules | Line does not match `code,quantity`, non-positive quantity | Detected by parse/validate functions; orchestration layer or API boundary decides whether to report an error, skip the line per policy, or request re-entry |
| Environment/I/O | File does not exist, connection lost, out of disk space, write permission error | Adapter throws a context-appropriate error; boundary layer decides whether to retry, respond, abort the operation, or log the incident |

`IOException` is a **checked exception**: a method that may throw it must declare `throws` or handle it. Meanwhile, `IllegalArgumentException` is an **unchecked exception** (`RuntimeException`). Choosing the exception type depends on the API contract, not on a rule that every I/O error must be swallowed on the spot.

In the example, `parse` wraps `NumberFormatException` into `IllegalArgumentException` with the **original cause** `e`. This tells the caller that the error belongs to the input data structure while preserving the cause for diagnostics. `main` catches only at the point capable of presenting an appropriate message to the runner.

**Do not catch an exception and return a fake result just so the pipeline "keeps running":**

```java
// Avoid: a data-reading error is turned into an empty list.
try {
    return Files.readAllLines(path);
} catch (IOException e) {
    return List.of();
}
```

This is an illustrative snippet inside a method that has a `path` variable; it is not a standalone program. Here, an empty result does not distinguish "valid file with no lines" from "unable to read file." If business rules **genuinely specify** that a source error means no data, document that policy in the contract and test it explicitly; do not apply it as a default.

## 5. Why Not Put I/O Directly Inside `Stream.map()`?

It is easy to write a lambda like this:

```java
List<String> contents = paths.stream()
        .map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .toList();
```

This is an illustrative snippet requiring imports `java.io.IOException`, `java.io.UncheckedIOException`, `java.nio.file.Files`, and `java.util.List`; `paths` has type `List<Path>`. The code may be valid, but it brings consequences:

- `map` now depends on the file system and can fail outside data transformation; it is hard to test in isolation.
- In a stream, intermediate operations such as `map` are **lazy**. The file-reading call inside the lambda is only invoked when a terminal operation like `toList()` consumes elements.
- If the operation fails midway, some files may already have been read; using a parallel stream makes controlling order and side effects even more complex.
- Wrapping into `UncheckedIOException` is an exception-translation policy; **it does not make I/O pure**. If you must use this approach, translate intentionally in the adapter, preserve `cause`, and handle it at the appropriate boundary.

When an API requires `Function<T,R>`, `Predicate<T>`, or `Consumer<T>`, these standard interfaces do not declare checked exceptions. **Do not force every I/O operation into them**. You can read data before running the stream, define a custom interface with `throws IOException` as in the example, or choose an asynchronous API that supports success/failure states when the problem calls for it.

Similarly, calling `forEach(x -> repository.save(x))` can be useful at the orchestration layer if you genuinely want to issue a write per element, but clearly define error handling, retries, ordering, and the possibility of partial writes. The `forEach` syntax does not make write operations atomic.

## 6. Testing the Core and Testing the Boundary

With the design in the example, unit testing the core is very straightforward:

```java
List<String> actual = SideEffectBoundaryDemo.transform(
        List.of("X1,2", "Y2,1")
);
if (!actual.equals(List.of("X1,200", "Y2,100"))) {
    throw new AssertionError(actual);
}
```

This is an illustrative test snippet placed in Java code in the same package with `import java.util.List;`. `transform` needs no real environment.

To test `run`, you can replace the adapter with a fake sink that stores results in memory:

```java
List<String> saved = new java.util.ArrayList<>();
SideEffectBoundaryDemo.run(
        () -> List.of("X1,2"),
        rows -> saved.addAll(rows)
);
if (!saved.equals(List.of("X1,200"))) {
    throw new AssertionError(saved);
}
```

The second test snippet needs to be placed in a method with `throws IOException` or exception handling; use `java.util.List` and `java.io.IOException` as appropriate. This tests behavior at the boundary: `saved` is state **of the fake adapter**, not a side effect inside `transform`.

You should also test:

1. **Data error:** pass `"X1,abc"` to `transform`, verify `IllegalArgumentException`; ensure the sink is not called if transformation has not completed.
2. **Source error:** implement a fake `Source` that throws `IOException`; verify `run` propagates the error and the sink does not run.
3. **Sink error:** implement a fake `Sink` that throws `IOException`; verify the error reaches the caller. At this point the core may have finished computing, but the result has not been saved successfully.
4. **Real I/O:** integration test using temporary files and UTF-8 charset, verifying the data is written accurately and resources are managed properly.

These test cases focus on **contracts and error observability**, without requiring mocks for every pure computation function.

## 7. Resource Management and Data Consistency at the Boundary

Keeping I/O at the boundary also makes resource lifecycles visible:

```java
try (var reader = Files.newBufferedReader(input, StandardCharsets.UTF_8)) {
    // Read from reader and pass the read data to the processing core.
}
```

This is an illustrative snippet requiring imports `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`; the variable `input` is a `Path`. `try-with-resources` guarantees the resource is closed when exiting the block, even when an exception occurs. If both the operation in the block and closing throw errors, Java may record the close error as a *suppressed exception*; do not lose the cause when reporting.

Reading an entire file with `Files.readAllLines` suits small/medium data; for large files, streaming/iterating through `BufferedReader` helps control memory. Even when processing line by line as a stream, you still need to clearly define the resource open/close boundary and consider mid-stream error handling.

**The "compute first, write later" order helps reduce partial writes caused by transformation errors**, but it does not guarantee that the external system receives the change only once or all at once. For example:

- `Files.write` can fail mid-write, leaving an incomplete file. If you need to update a file in a "replace completely" manner, consider writing to a temporary file in the same directory and renaming with `Files.move` using `ATOMIC_MOVE` when the file system supports it; you still need to handle errors and clean up temporary files.
- Writing multiple DB records may require a transaction; wrapping `save` calls in a stream does not replace a transaction.
- An HTTP call can succeed on the server and fail when the client receives the response; blind retries risk creating duplicate operations. You need an idempotency policy or result identification.
- Placing error logs/metrics near the adapter or orchestration layer aids diagnostics without making every `parse` function aware of the observability system.

## 8. Passing Dependencies Instead of Accessing the Environment Directly

If a computation needs the "current time," do not hide a clock read inside the function:

```java
// Hidden input, unstable over time:
boolean expired(java.time.Instant deadline) {
    return java.time.Instant.now().isAfter(deadline);
}
```

Instead, the boundary layer reads the time once and passes it in:

```java
// The same two arguments always produce the same result:
static boolean expired(java.time.Instant deadline,
                       java.time.Instant now) {
    return now.isAfter(deadline);
}
```

Both illustrative snippets need to be placed in a Java class, importing `java.time.Instant` if not using the fully qualified name. The same applies to randomness, locale, configuration, or third-party data: when possible, turn them into **explicit input values** for the processing core. If multiple places need clock access, you can inject `Clock` at the adapter and obtain `Instant` at the orchestration point.

## 9. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `Files.readString` or `client.send` directly from a business-logic `map` | Function depends on the environment; checked exceptions are hard to manage | Have the adapter read first and pass data into `map`; or use a dedicated I/O interface |
| `catch (Exception e) { return null; }` at every layer | Cause is lost, `null` propagates deeply, hard to pinpoint errors | Handle only where a recovery policy exists; preserve `cause` when translating |
| Writing data immediately while validating each element | A malformed final line can appear after many initial lines were already written | Validate/transform before writing if all-or-nothing is required; when streaming is needed, define recovery |
| Logging, sending emails, or updating counters inside computation functions | Tests depend on external systems; re-calling the function causes duplicate effects | Return results/data events and let the boundary layer decide when to emit them |
| Catching `IOException` and turning it into `List.of()` | Read errors are interpreted as "no data" | Distinguish valid empty results from errors using exceptions or a result type |
| Assuming `forEach` or parallel streams are safe for all side effects | Race conditions, unclear ordering, partial writes | Orchestrate side effects in a controlled way; consider transactions and idempotency |
| Using manual `finally` and forgetting to close resources | File descriptor/connection leaks | Prefer `try-with-resources` at the resource ownership point |

A special case is `InterruptedException` when a waiting task is interrupted: if you catch it to translate into another exception in a worker thread, you normally need to call `Thread.currentThread().interrupt()` to restore the interrupt flag before propagating the stop policy; avoid swallowing task cancellation signals.

## 10. Self-Check Before Finishing a Processing Flow

Try answering these questions when looking at your code:

1. Which statements actually read/write externally, and are they located at a visible adapter layer or orchestration boundary?
2. Can the processing function be re-run with the same data and produce the same result, without files, clocks, networks, or DBs?
3. Are data errors and environment errors mixed into a fake value (`null`, empty string, empty list)?
4. If an error occurs midway, what external data might already have changed? Are transactions, temporary files, idempotent retries, or compensating mechanisms needed?
5. Who owns closing resources, writing logs, translating exceptions into API/CLI messages, and deciding on retries?

**Remember:** Put I/O and side effects at visible boundaries; keep parse/validate/compute on data values; let exceptions travel to where there is enough context to handle them. This approach makes Java code using lambdas/streams easier to read, easier to test, and easier to control for errors.
