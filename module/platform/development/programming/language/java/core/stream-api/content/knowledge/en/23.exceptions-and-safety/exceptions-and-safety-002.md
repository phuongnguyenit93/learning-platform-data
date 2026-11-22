# Handling Checked Exceptions in Stream Lambdas

## 1. The Problem: Code That Compiles in a Loop May Not Compile in a Stream

In **JAVA_STREAM_API**, we use lazy pipelines with `filter`, `map`, `reduce`, and `collect` to process data declaratively. However, many real-world operations such as reading files, calling legacy Java APIs, running JDBC queries, or parsing data with exception-checking APIs can throw **checked exceptions**. When migrating a loop to a Stream, adding `throws IOException` to the enclosing method **does not automatically make a lambda inside `map` accept IOException**.

Consider an example:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class CheckedExceptionProblem {

    static List<String> loadFiles(List<Path> paths)
        throws IOException {

        // DOES NOT COMPILE:
        // return paths.stream()
        //     .map(Files::readString)
        //     .toList();

        throw new UnsupportedOperationException(
            "The example above illustrates a compile error"
        );
    }
}
~~~

`Files.readString(Path)` declares `throws IOException`. Meanwhile, `Stream.map` expects a `Function<? super T, ? extends R>`, and `Function.apply` **does not declare any checked exceptions**. Java rejects passing a method that throws an unhandled checked exception into this position.

This lesson belongs to the **Exceptions and Safety** chapter, focusing on handling errors thrown inside Stream lambdas accurately and transparently. After this lesson, you will be able to:

- Distinguish **checked**, **unchecked exceptions**, and compiler error messages.
- Choose among **handling in place**, **wrapping into an unchecked exception**, **representing errors as data**, and **reverting to a loop**.
- Write `IOFunction`/`IOPredicate` adapters with explicit policies that never swallow errors.
- Preserve `cause` and failing record context when translating exceptions.
- Understand when exceptions surface due to **lazy evaluation** and the effect of short-circuiting.
- Close resources properly with `Files.lines` and distinguish source-opening errors from consumption errors.
- Handle parallel streams, unobserved errors, already-executed side effects, and interruption.
- Design test examples in Java 17+ to verify success paths, failure paths, and that data does not silently vanish.

**Scope:** Examples use Java 17+, and the core ideas apply to Java 8 by adjusting compatible syntax. This lesson covers the Java Stream API; it does not assume `onErrorContinue` or error-handling operators from external reactive libraries.

## 2. Why Don't Function, Predicate, and Consumer Declare throws?

The standard functional interfaces in `java.util.function` conceptually look like this:

~~~java
@FunctionalInterface
interface Function<T, R> {
    R apply(T value);
}

@FunctionalInterface
interface Predicate<T> {
    boolean test(T value);
}

@FunctionalInterface
interface Consumer<T> {
    void accept(T value);
}
~~~

These are **abbreviated versions for explanation**; the actual APIs also have default/static methods. The key point is that these abstract methods **do not have `throws IOException` or `throws SQLException`**.

| Pipeline position | Typical functional interface | Can body throw checked exceptions directly? |
| --- | --- | --- |
| `map(mapper)` | `Function<T,R>` | No, unless the exception is handled |
| `filter(predicate)` | `Predicate<T>` | No |
| `forEach(action)` | `Consumer<T>` | No |
| `flatMap(mapper)` | `Function<T,Stream<R>>` | No |
| `sorted(comparator)` | `Comparator<T>` | No |
| `collect(collector)` | accumulator/combiner/finisher callbacks | Does not allow checked exceptions directly |
| `reduce(accumulator)` | `BinaryOperator<T>` | No |
| Normal loop method with `throws IOException` | No functional interface blocking it | Yes, if the method declares or handles it properly |

### Checked vs. Unchecked Exceptions

- **Checked exceptions:** most subclasses of `Exception` that are not `RuntimeException`, such as `IOException`, `SQLException`, and `ParseException`. The compiler requires catching them or declaring `throws` wherever they can be thrown.
- **Unchecked exceptions:** `RuntimeException` and its subclasses such as `IllegalArgumentException`, `NumberFormatException`, `UncheckedIOException`; as well as `Error`. Java does not require declaring `throws`.
- **Errors:** such as `OutOfMemoryError`; should not be caught in a generic adapter and treated as ordinary data errors.

Even when an enclosing method declares `throws IOException`, a lambda acting as `Function.apply` still cannot let `IOException` escape directly under the target type's contract:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

// WRONG: declaring throws on the enclosing method is not enough.
static List<String> invalid(List<Path> paths) throws IOException {
    // return paths.stream().map(Files::readString).toList();
    throw new UnsupportedOperationException("Illustration");
}
~~~

**Rule:** Java checks checked exceptions against the **target type of the lambda/method reference**, not merely the enclosing method's declaration.

## 3. Before Writing try/catch: Define the Error-Handling Policy

There is no single “lambda trick” right for every domain. Pick the failure policy first:

| Policy | Meaning | Suitable scenario | Risk if misused |
| --- | --- | --- | --- |
| **Fail-fast** | Stop processing and report error | Every file is mandatory; financial data | Partial results/side effects may have already occurred |
| **Fallback** | Use a default/backup value | Missing optional config, replaceable cache content | Easily masks failures if fallback lacks valid meaning |
| **Skip + record** | Drop bad record while reporting fully | Best-effort import, dirty data processing | Skipping without recording causes silent data loss |
| **Error as data** | Return `Success/Failure` per record | Need to aggregate all errors and display to users | Requires extra result types and classification step |
| **Handle outside Stream** | Use a loop or dedicated API | Controlling transactions, retry, cleanup, break | More verbose, yet sometimes clearer and more accurate |

For example, given a list of mandatory document paths, failing to read one file may need to fail the whole batch. But for importing 1,000 rows, the requirement might be to **collect every bad row**, still produce a report of valid rows, and **commit only when approved by the business team**.

Every solution in this lesson must answer three questions:

1. **Can errors be lost?**
2. **Can successful data still be used correctly?**
3. **Does stopping or continuing match the transaction and business contract?**

## 4. Approach 1 — try/catch Directly Inside the Lambda

The most direct way is to catch the checked exception where it occurs and turn it into either a **meaningful valid result** or an **unchecked exception**.

### 4.1. Fail-Fast: Wrapping IOException into UncheckedIOException

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class LocalCatchDemo {

    static List<String> readAll(List<Path> paths) {
        return paths.stream()
            .map(path -> {
                try {
                    return Files.readString(path);
                } catch (IOException ex) {
                    throw new UncheckedIOException(
                        "Unable to read file: " + path, ex
                    );
                }
            })
            .toList();
    }
}
~~~

Here:

- `try/catch` resolves the checked exception inside the lambda.
- `UncheckedIOException` is a `RuntimeException` subclass dedicated to `IOException`.
- The message adds the **file path**, helping trace the failing record.
- The original exception is preserved in `ex.getCause()`, instead of being replaced by a plain message string.
- When an `IOException` occurs during pipeline evaluation, the terminal operation can terminate with an unchecked exception.

### 4.2. Explicit Fallback: Only When Allowed

If a missing optional configuration file can accept a default value, you may return a fallback:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String readOptionalConfiguration(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        // Only valid if every IOException is allowed by
        // business rules to be handled with a fallback.
        return "mode=DEFAULT";
    }
}
~~~

**Caution:** `IOException` does not only mean “file does not exist.” It can also mean permission errors, disk corruption, or failed reads. If you only want a fallback when the file **does not exist**, catch the more specific exception:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

static String readConfigOrDefault(Path path) throws IOException {
    try {
        return Files.readString(path);
    } catch (NoSuchFileException missing) {
        return "mode=DEFAULT";
    }
}
~~~

This method still declares `throws IOException` for other I/O errors. If used inside `map`, we **still need** an adapter or corresponding catch for the remaining possible `IOException`s.

### 4.3. Why Avoid `catch (Exception) { return null; }`?

This pattern can turn a file read error into a `null` element without downstream knowing why; then `filter(Objects::nonNull)` erases every trace of the error. It can also swallow unexpected `RuntimeException`s such as programming bugs.

If you want to skip failing rows, represent errors in an **observable** way: return a `Failure` type, record them in a result list, or report errors at the calling layer. Never use `null`/empty string as a blanket replacement for all errors.

## 5. Approach 2 — Writing a Reusable IOFunction Adapter

When multiple pipelines perform I/O, repeating `try/catch` in every `map` hurts readability. You can define a functional interface that **allows throwing IOException**, then adapt it to a standard `Function`.

### Complete Java 17+ Program

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class IOFunctionAdapter {

    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> uncheckedIO(
        IOFunction<T, R> function
    ) {
        Objects.requireNonNull(function, "function");

        return value -> {
            try {
                return function.apply(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static List<String> readAll(List<Path> paths) {
        return paths.stream()
            .map(uncheckedIO((Path path) -> Files.readString(path)))
            .toList();
    }
}
~~~

Key points:

- `IOFunction.apply` declares `throws IOException`, allowing `Files.readString(path)` inside.
- `uncheckedIO` produces a valid `Function<T,R>` for Stream.
- The adapter preserves `IOException` as the cause rather than using a “sneaky throw” trick to spoof exception types.
- `Objects.requireNonNull(function)` catches programming errors right when creating the adapter.

### Preserving Failing File Context in the Adapter

A generic adapter does not know the path or record name. If the error message needs context, attach it in the calling lambda:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

static List<String> load(List<Path> paths) {
    return paths.stream()
        .map(IOFunctionAdapter.uncheckedIO((Path path) -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new IOException(
                    "Read failed: " + path, ex
                );
            }
        }))
        .toList();
}
~~~

In this example, the new `IOException` carries the path context while keeping the original cause; the adapter then wraps it in `UncheckedIOException` to fit `Function`.

**Do not confuse this:** An adapter only **translates the error-reporting mechanism**; it does not decide whether the error should trigger retry, skip, rollback, or user display. Policy at outer layers must remain explicit.

## 6. Approach 3 — Adapters for Predicate or Consumer with Checked Exceptions

`filter` needs `Predicate<T>`; `forEach` needs `Consumer<T>`. Since these interfaces also lack checked `throws`, the adapter pattern is similar.

### 6.1. IOPredicate with Files.size

`Files.size(path)` can throw `IOException`. If you want to filter files larger than 0 bytes:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Predicate;

public class IOPredicateDemo {

    @FunctionalInterface
    interface IOPredicate<T> {
        boolean test(T value) throws IOException;
    }

    static <T> Predicate<T> uncheckedIO(IOPredicate<T> predicate) {
        return value -> {
            try {
                return predicate.test(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static List<Path> nonEmptyFiles(List<Path> paths) {
        return paths.stream()
            .filter(uncheckedIO(path -> Files.size(path) > 0L))
            .toList();
    }
}
~~~

**Domain note:** Filtering by `Files.size` and reading the file later can hit a *time-of-check to time-of-use* (TOCTOU) race if the file changes between steps. Do not treat a pre-check on size as a guarantee that the subsequent read will succeed.

### 6.2. IOConsumer for Operations with Side Effects

An `IOConsumer<T>` can also be wrapped. However, for operations that write files or send requests, using `forEach` with side effects requires careful review:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Consumer;

@FunctionalInterface
interface IOConsumer<T> {
    void accept(T value) throws IOException;
}

static <T> Consumer<T> uncheckedIOConsumer(IOConsumer<T> action) {
    return value -> {
        try {
            action.accept(value);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    };
}
~~~

The code above is a **snippet** defining an interface and helper, not a standalone program. It translates exceptions, yet **does not make side effects atomic**. If `forEach` wrote 4 files and the 5th failed, the first 4 files may already exist. With `parallelStream().forEach(...)`, execution order cannot rely on encounter order at all.

If you need **all-or-nothing transactions**, use an appropriate transaction/staging/commit mechanism or a sequential loop with explicit rollback; never expect throwing an exception to undo already-executed side effects.

## 7. Approach 4 — Restoring Checked Exceptions at the API Boundary

Sometimes a public API must declare `throws IOException` instead of exposing `UncheckedIOException`. We can still use Stream internally and **restore the checked exception at the outer layer**.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class CheckedBoundaryDemo {

    static List<String> readAll(List<Path> paths)
        throws IOException {

        try {
            return paths.stream()
                .map(IOFunctionAdapter.uncheckedIO(
                    (Path path) -> Files.readString(path)
                ))
                .toList();

        } catch (UncheckedIOException ex) {
            throw ex.getCause();
        }
    }
}
~~~

`UncheckedIOException.getCause()` returns the original `IOException`, so callers can use `catch (IOException e)` per the method's contract. If you need to keep the path, use an adapter that adds context as shown in section 5.

This is **controlled translation at a boundary**. Do not write `throw (IOException) ex.getCause()` on a generic `RuntimeException` unless you are certain of the cause type; use a strongly typed wrapper to avoid a secondary `ClassCastException`.

### When Should You Choose a throws Boundary?

- Your library API has a checked exception contract and callers need to handle by exception type.
- The business layer already has a retry or fallback strategy for `IOException`.
- You want to keep `IOException` as an explicit part of the public API.

If the pipeline involves multiple exception types such as `IOException` and `SQLException`, design a domain error hierarchy or separate the operations instead of forcing every error into a semantically wrong `IOException`.

## 8. Approach 5 — A Normal Method Handles I/O, Stream Only Performs Pure Transformations

Wrapping checked exceptions inside lambdas is not always the best option. Sometimes the clearest design is **performing I/O at the outer boundary** and using Stream to process the data already in memory.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReadThenTransform {

    static List<String> cleanedLines(Path path)
        throws IOException {

        // I/O at API boundary, can throw IOException.
        String text = Files.readString(path);

        // Stream processes data already loaded into memory.
        return text.lines()
            .map(String::strip)
            .filter(line -> !line.isEmpty())
            .toList();
    }
}
~~~

This avoids writing an adapter because `String.lines()` no longer performs file I/O. However, it **loads the entire file into memory**, which is unsuitable for very large files. When streaming I/O is needed, `Files.lines` with proper resource management is an alternative covered below.

**Design lesson:** Separate “fetching fallible data” from “pure data transformation” whenever doing so makes errors easier to observe, code easier to test, and memory cost acceptable.

## 9. Lazy Evaluation: Checked Exceptions Can Surface at the Terminal

`map` is a **lazy** intermediate operation. The file-reading callback does not execute merely because the pipeline was defined:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class LazyFailureDemo {

    static Stream<String> buildPipeline(List<Path> paths) {
        return paths.stream().map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                    "Error reading " + path, ex
                );
            }
        });
    }

    static List<String> execute(List<Path> paths) {
        Stream<String> pipeline = buildPipeline(paths);
        // No file is read just because the pipeline was created.
        return pipeline.toList(); // I/O error may surface here.
    }
}
~~~

### try/catch Must Wrap the Terminal Operation

~~~java
try {
    List<String> result = LazyFailureDemo.execute(paths);
    // Only use result when the terminal completes successfully.
} catch (UncheckedIOException ex) {
    System.err.println("I/O error: " + ex.getCause());
}
~~~

The snippet above assumes a `paths` variable is declared; its purpose is to show where exception handling belongs.

If you build a pipeline inside a `try` block but execute the terminal **after leaving that block**, the mapper's exception happens later and is not caught where the pipeline was constructed.

### Short-Circuiting Changes Which Elements Are Evaluated

~~~java
import java.util.List;

List<String> first = names.stream()
    .map(name -> potentiallyFailingTransform(name))
    .limit(1)
    .toList();
~~~

This snippet assumes an application-defined `potentiallyFailingTransform`. `limit(1)` only needs one output element, so later elements may **never have their mapper called**. Similarly, `findFirst`, `findAny`, `anyMatch`, and `noneMatch` can terminate early.

**Consequence:** Do not rely on `map` with side effects expecting it to “check every file and throw every error” if the terminal can short-circuit. For full reporting, design a step that processes the entire source and records each item's outcome as data.


## 10. Approach 6 — Representing Errors as Data with Success and Failure

When the requirement is to **collect all failing records** instead of stopping at the first error, fail-fast is insufficient. You can use a result type with two variants, `Success` and `Failure`; each Stream element produces **exactly one status-bearing outcome**.

### Complete Self-Contained Java 17+ Example

~~~java
import java.io.IOException;
import java.util.List;

public class ReadOutcomeDemo {

    sealed interface Outcome permits Success, Failure {}

    record Success(String sourceId, String content)
        implements Outcome {}

    record Failure(String sourceId, IOException error)
        implements Outcome {}

    record Report(
        List<Success> successes,
        List<Failure> failures
    ) {}

    // Simulates a read source that can throw IOException.
    static String load(String sourceId) throws IOException {
        if (sourceId.startsWith("bad")) {
            throw new IOException("Cannot read " + sourceId);
        }
        return "DATA:" + sourceId;
    }

    static Outcome read(String sourceId) {
        try {
            return new Success(sourceId, load(sourceId));
        } catch (IOException ex) {
            return new Failure(sourceId, ex);
        }
    }

    static Report scan(List<String> sourceIds) {
        // Perform the read operation only once per source.
        List<Outcome> results = sourceIds.stream()
            .map(ReadOutcomeDemo::read)
            .toList();

        List<Success> good = results.stream()
            .filter(Success.class::isInstance)
            .map(Success.class::cast)
            .toList();

        List<Failure> bad = results.stream()
            .filter(Failure.class::isInstance)
            .map(Failure.class::cast)
            .toList();

        return new Report(good, bad);
    }

    public static void main(String[] args) {
        Report report = scan(List.of(
            "doc-1", "bad-2", "doc-3", "bad-4"
        ));

        System.out.println(report.successes().size()); // 2
        System.out.println(report.failures().size());  // 2

        report.failures().forEach(f ->
            System.out.println(
                f.sourceId() + ": " + f.error().getMessage()
            )
        );
    }
}
~~~

**Why is this approach useful?**

- The lambda in `map` never lets a checked exception escape; `read` catches `IOException` and returns a value object.
- No shared mutable `List<Exception>` is mutated via side effects.
- Error and success records are split **after materializing once** into `List<Outcome>`, avoiding running I/O twice.
- `Failure` retains the source ID and exception, fitting per-row reporting needs.
- `toList()` preserves the input order from the `List` in this example, though the `IOException` object inside is not deeply immutable.

In real applications, replace `load(sourceId)` with `Files.readString(path)` or your project's I/O API. To represent multiple error kinds, you can use `record Failure(SourceId id, ErrorCode code, String message, Throwable cause)` or a richer sealed hierarchy.

### Do Not Turn Every Bug into a Data Error

This example catches only `IOException`. If `sourceId == null` causes a `NullPointerException` in `startsWith`, that is an input contract violation and should be checked separately. Do not use `catch (Exception)` to treat all errors, including programming bugs, as an “unreadable” record.

### Fail-Fast or Collect All Errors?

| Goal | Strategy |
| --- | --- |
| If one file is corrupted, the whole batch must fail | Wrap error and fail-fast, or validate all before committing |
| Need to report every broken file for user remediation | `Outcome` per source, no short-circuiting |
| Partial success is acceptable | Return both success and failure lists, explicitly exposing partial status |
| Fallback allowed for only one error kind | Catch the specific exception type |
| Need all-or-nothing write guarantees | Combine input validation with transactions, not just Stream |

**Note:** Successfully reading/validating a batch of records does not mean a transaction succeeded. Commit, rollback, and idempotency must be designed separately.

## 11. Files.lines: Distinguishing Opening Errors from Consumption Errors

`Files.lines(path)` returns a Stream **backed by a file resource**, not a pure in-memory collection. There are at least three stages to mind:

1. **Opening the source:** `Files.lines(path)` can throw checked `IOException`.
2. **Lazy reading:** I/O errors while the terminal consumes lines can surface as `UncheckedIOException`.
3. **Closing the source:** `try-with-resources` is needed to close the Stream even when errors occur.

### Correct Resource Management Example

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FilesLinesDemo {

    static List<String> nonBlank(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(
                path, StandardCharsets.UTF_8)) {

            return lines
                .map(String::strip)
                .filter(s -> !s.isEmpty())
                .toList();
        }
    }
}
~~~

`throws IOException` on the method handles the checked error when **opening the file**. Reading errors during the terminal can rise as `UncheckedIOException`. If the API must expose only checked `IOException`, you can convert back at the boundary:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

// Method snippet using the imports above.
static List<String> readLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        try {
            return lines.toList();
        } catch (UncheckedIOException ex) {
            throw ex.getCause();
        }
    }
}
~~~

`try-with-resources` still closes the Stream when an exception occurs. A method that **directly returns a Files.lines Stream** must clearly document that the caller owns closing it; you cannot rely on GC.

### Mistake: Creating a Stream in try-with-resources and Returning It

~~~java
// Wrong: returns a Stream already closed before the caller consumes it.
// static Stream<String> broken(Path path) throws IOException {
//     try (Stream<String> lines = Files.lines(path)) {
//         return lines;
//     }
// }
~~~

A Stream is only valid within the lifetime of its underlying resource. If you need to return a Stream to a caller, ownership must be designed explicitly; otherwise, execute the terminal inside `try-with-resources` and return the collected data.

## 12. SQLException, ParseException, and Other Business Exceptions

`UncheckedIOException` is designed for `IOException`; do not shoehorn `SQLException` into it. For other checked exceptions, create a **domain-meaningful runtime exception** or model errors as data.

~~~java
import java.sql.SQLException;
import java.util.function.Function;

public class SQLAdapter {

    @FunctionalInterface
    interface SQLFunction<T, R> {
        R apply(T value) throws SQLException;
    }

    static class DataAccessFailure extends RuntimeException {
        DataAccessFailure(String message, SQLException cause) {
            super(message, cause);
        }
    }

    static <T, R> Function<T, R> uncheckedSQL(
        SQLFunction<T, R> function
    ) {
        return value -> {
            try {
                return function.apply(value);
            } catch (SQLException ex) {
                throw new DataAccessFailure(
                    "Database query failed", ex
                );
            }
        };
    }
}
~~~

This adapter only **changes how errors are reported**; it does not make JDBC thread-safe. Never run `parallelStream()` over a shared `Connection` or `ResultSet` without concurrency-safety guarantees. Retries, connection pooling, transactions, and timeouts must be handled in the data-access layer.

For `ParseException` or custom domain exceptions, pick a proper wrapper and preserve `cause`. Avoid `throw new RuntimeException("Error occurred")` which drops the root cause and record ID.

## 13. InterruptedException Must Not Be Swallowed Arbitrarily

Some blocking APIs can throw `InterruptedException`. This is usually a task-cancellation or interruption signal. If caught inside a lambda where `Function` cannot declare checked exceptions, **restore the interrupt flag** before throwing an appropriate unchecked error, unless your API can surface the checked exception transparently.

~~~java
import java.util.List;
import java.util.Locale;

public class InterruptDemo {

    static String transform(String input) {
        try {
            Thread.sleep(10L);
            return input.toUpperCase(Locale.ROOT);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Task was interrupted", ex
            );
        }
    }

    public static void main(String[] args) {
        List<String> values = List.of("a", "b")
            .stream()
            .map(InterruptDemo::transform)
            .toList();

        System.out.println(values); // [A, B] if not interrupted.
    }
}
~~~

When `InterruptedException` is thrown, the thread's interrupt flag is typically cleared. Calling `Thread.currentThread().interrupt()` lets coordinating layers observe the interruption signal.

**Do not:**

~~~java
// Wrong: pretends processing succeeded when cancellation was requested.
// catch (InterruptedException ignored) { return ""; }
~~~

For complex async/cancellation workflows, Stream is not a replacement for executors/task frameworks. Never catch `Error` or `Throwable` just to keep a pipeline running.

## 14. Parallel Streams: There Is No Guaranteed Error Order

With `parallelStream`, multiple branches may read data concurrently. When one branch throws, the terminal can fail, yet there is **no guarantee of reporting all errors** or always reporting the error at the earliest List index.

~~~java
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

static List<String> readParallel(List<Path> paths) {
    try {
        return paths.parallelStream()
            .map(IOFunctionAdapter.uncheckedIO(
                (Path path) -> Files.readString(path)
            ))
            .toList();

    } catch (UncheckedIOException ex) {
        // Do not assume this is the first failing file in the List.
        throw ex;
    }
}
~~~

This snippet uses the adapter from section 5. Do not build business logic on assumptions about the first exception, the order of causes, or the list of suppressed exceptions. Some branches may have already completed side effects before the failure is observed.

### Do Not Collect Errors into a Shared ArrayList in Parallel

~~~java
// Anti-pattern: external mutable state modified by multiple threads.
// List<Exception> errors = new ArrayList<>();
// paths.parallelStream().map(path -> {
//     try { return read(path); }
//     catch (IOException ex) {
//         errors.add(ex); // Unsafe.
//         return "";
//     }
// }).toList();
~~~

A synchronized collection alone does not satisfy a contract of **completeness, ordering, transactions, and error observability**. If all outcomes are needed, produce an `Outcome` per input and collect with a non-short-circuiting terminal.

### Parallel I/O Does Not Automatically Mean Faster

Parallel Stream does not provide quotas, rate limiting, retries, circuit breakers, or connection limits. For external requests, higher concurrency can overload services or hit rate limits. Use a controlled orchestration layer when handling large volumes of I/O tasks.


## 15. Exceptions Do Not Roll Back Already-Executed Side Effects

A pipeline may read/transform many records and then write externally:

~~~java
// Pseudocode illustrating side effects.
// records.stream()
//     .map(this::validate)
//     .forEach(repository::save);
~~~

If the fifth record fails, the first four **may already be saved**. An exception stops further evaluation, yet **does not undo** previously written transactions or files. With `parallelStream`, some records appearing later in encounter order may also have already been processed.

**Safer alternatives:**

1. **Validate first, commit later:** collect all valid values and only write when no blocking errors exist.
2. **Transaction/staging:** write to a staging area or transaction, committing only when everything succeeds.
3. **Best-effort with reporting:** each input yields `Success/Failure`, without pretending everything succeeded.
4. **Idempotent retry:** use request IDs/deduplication keys when business rules permit retries.
5. **Coordinated loop:** easier to reason about order, breakpoints, stopping, and compensation steps.

Whether using a loop or Stream, rollback and idempotency must be designed **at the system level**, not expected as a property of `forEach`.

### Do Not Rely on Logging Inside peek for Auditing

`peek` is an intermediate operation meant for observation/debugging, not a guaranteed audit mechanism. Stream has lazy evaluation, short-circuiting, and terminal optimizations; callbacks are not guaranteed to execute for every input.

In particular, on a Stream with a known size, `count()` **may compute its result without running the mapper** if the mapper does not change element count:

~~~java
import java.util.List;

public class CountOptimizationWarning {
    public static void main(String[] args) {
        long count = List.of("A", "B").stream()
            .map(value -> {
                // Do not use mapper as a mandatory audit step.
                System.out.println("Processed " + value);
                return value.toLowerCase(java.util.Locale.ROOT);
            })
            .count();

        System.out.println(count); // 2
        // No guarantee both "Processed ..." lines will print.
    }
}
~~~

This also means never using `map` with side effects/exceptions followed by `count()` to “prove every file was read.” To validate all data, use a terminal that truly needs the transformed results and model errors as observable values.

## 16. When Is a Loop Clearer Than a Stream?

You do not need to force every I/O operation with checked exceptions into a pipeline. When the requirement is to stop immediately on the first unreadable file and keep `throws IOException` on the public API, a loop can be the clearest choice.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class PlainLoopAlternative {

    static List<String> readRequiredFiles(List<Path> paths)
        throws IOException {

        List<String> texts = new ArrayList<>();

        for (Path path : paths) {
            texts.add(Files.readString(path));
        }

        return List.copyOf(texts);
    }
}
~~~

Advantages of a loop:

- Checked exceptions pass directly through `throws IOException`.
- Line numbers or paths can be attached to exceptions right at the failure site.
- Bounded retries, `break`, `continue`, and cleanup are often easier to follow.
- No adapter is needed when there is only a single I/O flow.
- When transaction state, ordering, and rollback decisions matter, explicit statements can be easier to audit.

**This does not mean loops are always better.** With already-loaded data and pure transformations, Streams are often shorter and easier to compose. Choose the construct that makes the **error policy clearest**, rather than forcing a functional style.

## 17. Testing Adapters with Simulated I/O Sources

You do not need real files to test an adapter that converts `IOException` to `UncheckedIOException`. Use a simulated function with a failing input to verify:

- The success path preserves expected data.
- The error path throws the right wrapper.
- The original `IOException` is retained as the cause.
- Tests do not swallow failures by catching the wrong exception.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;

public class IOAdapterChecks {

    static String fakeRead(String id) throws IOException {
        if ("bad".equals(id)) {
            throw new IOException("cannot read bad");
        }
        return id.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<String> success = List.of("ok", "fine")
            .stream()
            .map(IOFunctionAdapter.uncheckedIO(
                (String id) -> fakeRead(id)
            ))
            .toList();

        if (!success.equals(List.of("OK", "FINE"))) {
            throw new AssertionError("Wrong success path");
        }

        try {
            List.of("ok", "bad")
                .stream()
                .map(IOFunctionAdapter.uncheckedIO(
                    (String id) -> fakeRead(id)
                ))
                .toList();

            throw new AssertionError("Should have thrown");

        } catch (UncheckedIOException ex) {
            IOException cause = ex.getCause();

            if (!"cannot read bad".equals(cause.getMessage())) {
                throw new AssertionError("Lost cause", ex);
            }
        }

        System.out.println("PASS");
    }
}
~~~

`IOFunctionAdapter` is the complete class from section 5. Both classes can be placed in the same package and compiled together. The test uses `throw new AssertionError` instead of Java `assert` because `assert` is typically disabled unless the JVM runs with `-ea`.

### Testing the Error-as-Data Path

~~~java
import java.util.List;

public class OutcomeChecks {
    public static void main(String[] args) {
        ReadOutcomeDemo.Report report = ReadOutcomeDemo.scan(
            List.of("ok", "bad-1", "ok-2", "bad-2")
        );

        if (report.successes().size() != 2) {
            throw new AssertionError("Wrong success count");
        }
        if (report.failures().size() != 2) {
            throw new AssertionError("Missing error records");
        }
        if (!"bad-1".equals(
                report.failures().get(0).sourceId())) {
            throw new AssertionError("Wrong error order");
        }

        System.out.println("PASS");
    }
}
~~~

This test suite makes the contract explicit: on a sequential `List.stream()`, the report preserves the source's encounter order. It tests **observable outcomes**, not how many times `peek` or logging inside a lambda ran.

## 18. Debugging Workflow and Production Readiness Checklist

When debugging errors in Stream lambdas, follow these steps:

1. **Identify the exception type:** checked (`IOException`, `SQLException`) or unchecked (`NumberFormatException`, `IllegalArgumentException`)?
2. **Identify the target functional interface:** `Function`, `Predicate`, `Consumer`, `BinaryOperator`, or which Collector callback?
3. **Choose the policy:** fail-fast, fallback, error as data, partial success, or a loop API.
4. **Check where the error actually throws:** pipeline construction or terminal execution?
5. **Preserve context:** source ID, path, line position, operation being performed.
6. **Preserve cause:** do not just throw a message that drops the original stack/cause.
7. **Check resources:** who opens and who closes? Is `try-with-resources` used when reading `Files.lines`?
8. **Check side effects:** was any data committed before the failure?
9. **Check short-circuiting:** `findFirst`, `limit`, `anyMatch`, `count` can prevent some callbacks from running.
10. **Check parallelism:** is there shared mutable state, incomplete error reporting, non-deterministic ordering, or overloaded I/O?
11. **Test:** empty source, all successes, single error, multiple errors, causes, and transaction boundaries.

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `unreported exception IOException` in `map` | `Function.apply` lacks checked throws | Catch/adapter or restructure |
| Error thrown at `toList()` | Lazy mapper runs at terminal | Catch around terminal |
| Missing errors for some elements | Short-circuiting terminal or optimization | Do not use side effects as an oracle |
| Out of memory reading file | `Files.readString` loads entire data | Streaming / size limits |
| Unclosed file descriptors | Forgot to manage `Files.lines` | Try-with-resources |
| Lost failing file path | Wrapper lacks context | Put path/ID in message or Result |
| Not all errors observed | Fail-fast stops early | Error as data, non-short-circuit terminal |
| Corrupted error list in parallel | Shared mutable ArrayList | Remove side effects, collect `Outcome` |
| Records saved despite pipeline failure | No transaction/staging | Design separate commit/rollback |
| Cancellation ineffective | Swallowed `InterruptedException` | Restore interrupt flag, report error |
| SQL error labeled as I/O | Wrong wrapper type | Domain runtime exception with cause |

## 19. Antipatterns to Avoid

### 19.1. Catching Every Exception and Returning an Empty String

~~~java
// Avoid:
// catch (Exception ex) { return ""; }
~~~

An empty value can be **legitimate** data; you cannot distinguish an empty file from a failed read. Choose an explicit fallback or a `Failure` type.

### 19.2. Throwing RuntimeException While Dropping the Cause

~~~java
// Avoid:
// catch (IOException ex) {
//     throw new RuntimeException("File read error");
// }
~~~

Dropping the cause breaks the exception chain. Use `new UncheckedIOException("...", ex)` or a domain exception wrapping `ex`.

### 19.3. Using UncheckedIOException for Every Exception

`UncheckedIOException` is specifically for `IOException`. For `SQLException` and `ParseException`, use a domain-appropriate wrapper or structured error model.

### 19.4. Converting All Checked Exceptions to Unchecked and Forgetting API Boundaries

Silently changing a public API that previously declared `throws IOException` to unchecked can break callers expecting to handle that exception type. If the checked contract must stay, translate back at the boundary as in section 7.

### 19.5. Assuming try/catch Around Stream Construction Is Enough

Mappers execute lazily. If the terminal runs outside `try`, exceptions surface after the catch block. Verify the actual terminal location.

### 19.6. Assuming parallelStream Reports Every Error

There is no such guarantee. If all errors must be tallied, map each input to `Outcome`, avoid short-circuiting, control I/O, and test thoroughly.

### 19.7. Using a Shared Mutable List to Collect Errors

Callbacks running in parallel may mutate an un-synchronized List concurrently. Even with synchronization, `Outcome`-style return values are easier to reason about and free of side effects.

### 19.8. Assuming Exceptions Roll Back Files or Databases

They do not. Already-executed side effects must be handled via transactions, staging, or compensation depending on the domain.

### 19.9. Failing to Close Files.lines Sources

`Files.lines` must be closed. Never just run the terminal and rely on GC or expect Stream to close all attached resources automatically.

### 19.10. Hiding Interrupt Signals

Do not handle `InterruptedException` by returning a fallback and continuing normally. If you cannot rethrow the checked exception, usually restore the interrupt flag and throw an error preserving the cause.

## 20. Decision Matrix by Requirement

| Requirement | Recommended approach |
| --- | --- |
| Read all required files; fail on first error | Catch `IOException` into `UncheckedIOException` and fail-fast |
| Public method must declare `throws IOException` | Unwrap back via `getCause()` at boundary |
| Many similar I/O mappers | `IOFunction` adapter |
| Filter data based on `Files.size` | `IOPredicate` adapter, avoid TOCTOU assumptions |
| Each record needs a success/failure status | `Success/Failure` or domain Result |
| Need to analyze all errors in a batch | Materialize `Outcome` across whole source, then partition |
| Fallback for missing file, report other errors | Catch specific `NoSuchFileException` |
| Read large files line by line | `Files.lines` + try-with-resources |
| All-or-nothing transactional writes | Transaction/staging outside Stream |
| `InterruptedException` present | Propagate if possible; if wrapping, restore interrupt |
| Concurrent I/O calls with quotas | Bounded orchestration layer, not just parallelStream |
| Adapter code more complex than core logic | Explicit loop with `throws` |

## 21. Self-Check Questions and Practice Exercises

1. **Why can't `Files::readString` be passed directly to `Stream.map`?** Because `Function.apply` does not declare `throws IOException`.
2. **Does adding `throws IOException` to the enclosing method fix the lambda error?** No, the target type still forbids checked exceptions from escaping.
3. **How does `IOException` differ from `UncheckedIOException`?** One is checked; the other is a RuntimeException holding `IOException` as its cause.
4. **Why include Path/ID in error messages?** To identify the failing source when a pipeline processes many records.
5. **Is `orElse("")` or returning an empty string on read errors always safe?** No, because it blurs the distinction between empty data and an error.
6. **What problem does `IOFunction` solve?** It lets a callback declare `throws IOException` and adapts it into a valid Function.
7. **Can `UncheckedIOException` be used for SQLException?** No; use a domain-appropriate wrapper.
8. **Where do lazy mapper errors surface?** When the terminal actually requests evaluating the mapper.
9. **Does `limit(1)` guarantee the mapper runs on every input?** No.
10. **Can `count()` skip running a mapper?** Yes, in pipelines with known size where the mapper does not change element count.
11. **Why use `Outcome` when all errors must be collected?** Because every input produces a success or failure result without aborting at the first error.
12. **Why avoid running I/O twice to build two reports?** It wastes resources and external data may change between passes.
13. **What must you watch out for with `Files.lines`?** Checked errors on open, unchecked errors on iteration, and Stream closing responsibility.
14. **Is returning a Stream from try-with-resources valid?** No, if the Stream is closed before the caller consumes it.
15. **Why not swallow `InterruptedException`?** Because it masks cancellation signals; restore the interrupt flag or propagate.
16. **Does parallel Stream report every IOException?** There is no guarantee of order or completeness.
17. **Does a synchronized List fix all error-collection risks?** No, side effects and completeness contracts remain problematic.
18. **Does an exception at the fifth record roll back previous records?** No.
19. **When is a loop preferable?** When checked exceptions, cleanup, retries, transactions, and ordering need to be explicit.
20. **Does an unchecked adapter replace a retry policy?** No, it only translates exceptions.
21. **What cases should be tested for an adapter?** Success, failure, cause and source context, and empty source.
22. **Does `NumberFormatException` require a checked-exception adapter?** No; it is an unchecked exception, though a policy for bad data is still required.

### Extension A — Reporting Both Errors and Successful Data

Modify `ReadOutcomeDemo` so each `Failure` includes `sourceId`, error category, and message. Add an empty-data check, distinguishing “read succeeded but file has no content” from “read failed.”

### Extension B — Catching Missing Files While Preserving Access Errors

Write `readConfigOrDefault(Path)` to fall back only for `NoSuchFileException`. If `AccessDeniedException` occurs, propagate the error or convert it into an appropriate `Failure`; do not use the same fallback for every IOException.

### Extension C — Testing Lazy Evaluation and Short-Circuiting

Create a `["ok","bad"]` source with `fakeRead`. Compare `limit(1).toList()` and `toList()`, then explain why a short-circuiting pipeline cannot serve as validation for every record.

### Extension D — Resource Management Across Multiple Files

Design a function reading each file with `try-with-resources`, returning an `Outcome` per path. Test unreadable files, line-reading errors, and ensure every source Stream is closed.

### Extension E — Processing Outcomes Before Committing

Build a batch import returning `List<Outcome>`, with no database-writing side effects inside the mapper. Perform commit only when there is no `Failure`, or according to a declared partial-success policy.

**Remember:** Checked exceptions are not directly compatible with Stream's `Function`, `Predicate`, or `Consumer`. Decide your error policy first: **fail-fast**, **conditional fallback**, **cause-preserving adapter**, **error as data**, or **explicit loop**. Always account for lazy evaluation, short-circuiting, resource closing, already-executed side effects, and non-deterministic failures in parallel streams. Writing a pipeline properly means not merely making code compile, but ensuring every significant failure can be observed and handled according to the business contract.
