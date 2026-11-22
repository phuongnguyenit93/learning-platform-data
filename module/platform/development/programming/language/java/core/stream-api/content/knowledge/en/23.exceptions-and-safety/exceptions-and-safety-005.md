# Avoiding Exception Swallowing and Preserving Root Causes

In the Java Stream API, a `filter`, `map`, `reduce`, or `collect` pipeline can read thousands of elements before hitting invalid data, an I/O failure, or a business error. If the handler merely catches and ignores it, logs an incomplete message, or returns a default value to continue, the system may **report success even when results are missing or wrong**. Worse, creating a new exception without passing the original cause strips maintainers of the stack trace showing where the failure actually originated.

This lesson belongs to the **Exceptions and Safety** chapter of the `JAVA_STREAM_API` module. We focus on **not swallowing errors**, **preserving cause chains via `cause`**, retaining cleanup errors via **suppressed exceptions**, placing `try/catch` at the right lazy execution boundary, and choosing explicitly between **fail-fast** and **errors modeled as data**. Examples connect to I/O sources, custom Collectors, parallel pipelines, resource management, and state/performance constraints.

> Main examples use Java 8 or later. Top-level illustrative statements belong inside `main`, a method, or JShell; utility classes can live in separate files. Snippets marked **WRONG** exist only to identify anti-patterns and must not be placed in production code.

## 1. What Is “Exception Swallowing” Really?

*Exception swallowing* is catching an error and **erasing the failure signal**, leaving the caller unaware that the operation did not complete as intended.

A very dangerous example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList("10", "bad", "30");

List<Integer> values = raw.stream()
        .map(text -> {
            try {
                return Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                return 0; // WRONG: bad data is turned into a valid 0.
            }
        })
        .collect(Collectors.toList());

System.out.println(values); // [10, 0, 30]
```

If business logic sums the values, the total is 40 and looks completely valid. Nothing indicates `"bad"` was coerced into 0; you cannot even distinguish a genuine 0 from an error-induced 0.

Other forms of the same problem:

- `catch (Exception ignored) {}`: silently discarding the error.
- `catch (...) { return null; }`: hiding failure inside an ambiguous value.
- `catch (...) { return Collections.emptyList(); }`: making an error look like an empty dataset with zero records.
- `catch (...) { log(...); }` then **returning success anyway** when the contract forbids it.
- `catch (...) { throw new RuntimeException("failed"); }`: still throws, yet **drops the original cause** and stack trace.
- Catching every error—including programming bugs—and treating them as a single invalid record.

**Not every case of skipping a record is wrong.** If business rules specify that blank lines are skipped, filtering them out is valid. The problem is **skipping without a contract, without tracking counts, or without classifying errors**.

## 2. Three Decisions That Must Be Separated

When an operation can fail, ask three questions:

1. **What kind of error is this?** Bad input data, duplicate Map key, file read failure, task interruption, or a bug?
2. **Does this layer have authority to handle it?** Can it recover, translate into a domain result, retry validly, or must it propagate?
3. **What evidence must be preserved?** Error type, `cause`, record position, safe source metadata, `suppressed exceptions`, and completion status.

| Scenario | Typical appropriate policy | What not to do |
| --- | --- | --- |
| A CSV row has a non-numeric value where per-row errors are allowed | `ParseOutcome` carrying error, rejected counter | Return 0 without marking |
| Required source file cannot be opened | Throw/propagate `IOException` with context | Return an empty list and report success |
| I/O error while reading inside a lambda | `UncheckedIOException` wrapping original `IOException` | Throw `new RuntimeException("read failed")` alone |
| Unexpected duplicate key in `toMap` | Fail-fast or apply a defined merge rule | Use `(a,b) -> a` to mask the error without checking semantics |
| No element matches filter | `Optional.empty()` or valid empty result | Turn a normal absence into an infrastructure failure |
| Retryable transient failure | Bounded retry with fresh source and idempotent side effects | Re-invoke terminal on the same Stream |
| Thread interrupted while waiting on I/O | Restore interrupt or handle at authorized layer | Catch `InterruptedException` and ignore |

**Rule:** error handling counts as success only when that layer can **guarantee the post-handling result obeys the contract**. Otherwise, propagate the error with its cause.

## 3. Distinguishing Message, Stack Trace, Cause, and Suppressed

A Java `Throwable` carries several pieces of information:

| Component | Accessor | Meaning |
| --- | --- | --- |
| Exception type | `ex.getClass()` | Error classification |
| Message | `ex.getMessage()` | Short description, may lack context |
| Stack trace | `ex.getStackTrace()` / log Throwable | Call sites and execution path |
| Cause | `ex.getCause()` | Underlying error that led to the current error |
| Suppressed | `ex.getSuppressed()` | Additional errors, typically during resource cleanup |

Example of proper wrapping:

```java
import java.io.IOException;
import java.io.UncheckedIOException;

IOException original =
        new IOException("disk read failure");

UncheckedIOException wrapped =
        new UncheckedIOException("Cannot import orders", original);

System.out.println(wrapped.getCause() == original); // true
System.out.println(wrapped.getMessage());
// Cannot import orders
```

The business layer knows **order import failed**, while diagnostics can still inspect **the original IOException**.

Avoid doing this:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot import orders"); // WRONG
}
```

Pass `ex` to the constructor:

```java
catch (IOException ex) {
    throw new IllegalStateException(
            "Cannot import orders", ex);
}
```

`new IllegalStateException(message, ex)` preserves the original Throwable in `getCause()`. That matters far more than copying `ex.getMessage()` into a plain string.

## 4. When to Rethrow As-Is vs. When to Wrap?

**Propagate the original exception** when its type and context are already clear enough:

```java
try {
    processRecords();
} catch (IllegalArgumentException ex) {
    // Example: recording a metric at a boundary layer.
    metrics.recordInvalidRequest();
    throw ex; // Preserve the original object and stack trace.
}
```

This is an illustration assuming application-defined `processRecords` and `metrics`. If metric recording has side effects or lacks thread safety, manage it separately; recording a metric does not turn an error into success.

**Wrap** when you genuinely need to **cross an abstraction boundary**: a low-level source I/O failure expressed as a business-layer report loading failure.

```java
public final class ReportLoadException
        extends RuntimeException {

    public ReportLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Usage:

```java
try {
    return loadReportFromSource(path);
} catch (java.io.UncheckedIOException ex) {
    throw new ReportLoadException(
            "Report load failed for source " + sourceId,
            ex);
}
```

This snippet uses `loadReportFromSource` and `sourceId` as application components rather than standard APIs. The cause chain becomes:

```text
ReportLoadException: Report load failed for source ...
  caused by UncheckedIOException: cannot read ...
    caused by IOException: disk read failure
```

**Do not wrap repeatedly just to add the same “failed” phrase**. A deeply nested chain with duplicate messages makes logs harder to read. Add context only at meaningful abstraction boundaries, preserving `cause` whenever wrapping.

## 5. Lazy Evaluation: Catch Errors Around Terminal Execution

Streams are lazy: calling pipeline-building methods does not guarantee lambdas have run.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> raw = Arrays.asList("1", "bad", "3");

Stream<Integer> pipeline = raw.stream()
        .map(Integer::parseInt); // Has not parsed elements yet.

try {
    List<Integer> parsed =
            pipeline.collect(Collectors.toList());
    System.out.println(parsed);
} catch (NumberFormatException ex) {
    System.err.println("Invalid integer: " + ex.getMessage());
}
```

Wrong boundary:

```java
Stream<Integer> pipeline;

try {
    pipeline = raw.stream().map(Integer::parseInt);
} catch (NumberFormatException ex) {
    // Does not catch parse errors occurring later when terminal runs.
    throw new IllegalStateException("Parse failed", ex);
}

// Error can surface here:
pipeline.collect(Collectors.toList());
```

A subtle note: even with a terminal operation, **not every intermediate callback is guaranteed to execute**. `count()` can use `SIZED` to compute count while skipping `map` if the transformation does not change element count.

```java
long count = raw.stream()
        .map(Integer::parseInt) // Might not execute!
        .count();

System.out.println(count); // Might be 3.
```

Never use `peek`, `map` plus `count`, or early short-circuiting to force validation of **all** lines. If full validation is mandatory, build a terminal that collects validation outcomes or a traversal guaranteed to evaluate every value requiring inspection.

## 6. Checked Exceptions in map: Wrap with the Right Type and Keep Cause

Functional interfaces like `Function<T,R>` do not declare `throws IOException`. Therefore, this snippet does not compile:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

// WRONG: Files.size throws checked IOException.
List<Long> sizes = paths.stream()
        .map(Files::size)
        .collect(java.util.stream.Collectors.toList());
```

`paths` is assumed here to be `List<Path>`. If the policy is **fail-fast**, catch `IOException` in the lambda and wrap it in `UncheckedIOException`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

static List<Long> fileSizes(List<Path> paths) {
    return paths.stream()
            .map(path -> {
                try {
                    return Files.size(path);
                } catch (IOException ex) {
                    throw new UncheckedIOException(
                            "Cannot read size of " + path, ex);
                }
            })
            .collect(Collectors.toList());
}
```

At the call boundary:

```java
try {
    List<Long> sizes = fileSizes(paths);
    System.out.println(sizes);
} catch (UncheckedIOException ex) {
    IOException root = ex.getCause();

    // In application: log exception/cause at the error-handling layer.
    System.err.println("File operation failed: "
            + root.getClass().getSimpleName());
    throw ex; // Do not report false success.
}
```

`UncheckedIOException` accepts only `IOException` as its cause. It is not an arbitrary wrapper for any `RuntimeException` or validation error. Picking the right exception type clarifies the failure instead of collapsing everything into `RuntimeException("failed")`.

Another option, if your API **is permitted to declare checked exceptions**, is keeping I/O in a `throws IOException` method or a loop rather than forcing everything into a Stream. Pipeline syntax never outweighs a clear error contract.

## 7. Do Not Return null, 0, or an Empty List for Infrastructure Errors

Consider a file-reading helper:

```java
// WRONG: returns an empty List if the file cannot be read.
static List<String> unsafeRead(Path path) {
    try {
        return java.nio.file.Files.readAllLines(path);
    } catch (java.io.IOException ex) {
        return java.util.Collections.emptyList();
    }
}
```

The caller cannot distinguish:

- File exists and genuinely has zero lines;
- File does not exist;
- System lacks read permission;
- Storage device encountered an error.

A clearer contract:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

static List<String> readRequiredFile(Path path)
        throws IOException {
    return Files.readAllLines(path, StandardCharsets.UTF_8);
}
```

Another option, when a higher-layer API must not declare checked exceptions, is wrapping the cause with `UncheckedIOException` or a domain exception. **Never turn an unreadable file into “no data”** unless the contract explicitly specifies it, such as treating a missing optional file as default configuration.

Also distinguish an **allowed fallback** from an **error-hiding fallback**. For instance, an optional configuration may use defaults **only when the file is absent**, not when an existing file is corrupted or unreadable.

## 8. Files.lines: Opening Errors Differ from Lazy Read Errors

`Files.lines` can throw `IOException` when opening the source, while read errors during iteration can surface as `UncheckedIOException`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countWarnings(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(s -> s.startsWith("WARN:"))
                .count();
    }
}
```

At the call site:

```java
import java.io.UncheckedIOException;

try {
    long count = countWarnings(path);
    System.out.println("Warnings: " + count);
} catch (UncheckedIOException ex) {
    // Error may occur during lazy iteration.
    throw new IllegalStateException(
            "Failed while reading log content", ex);
} catch (java.io.IOException ex) {
    // Checked error may occur when opening the source.
    throw new IllegalStateException(
            "Failed to open log source", ex);
}
```

In practice, `filter` or downstream steps can also throw a RuntimeException. **Do not catch every RuntimeException broadly and label it an I/O error**.

### Sources Must Be Closed Even on Error

`try-with-resources` still calls `close` when the body throws an exception. Terminals like `collect`, `count`, `findFirst`, or `forEach` **do not automatically close** a Stream from `Files.lines`.

`BufferedReader.lines()` has different ownership: if you created the `BufferedReader`, close that Reader directly. Do not assume closing the Stream returned from a Reader automatically closes the Reader.

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    long count = reader.lines()
            .filter(s -> !s.isEmpty())
            .count();
    System.out.println(count);
}
```

If returning a lazy Stream to a caller, transfer closing responsibility explicitly. **Never** open a Reader inside `try`, return `reader.lines()`, and let the caller consume it after the Reader has already closed.

## 9. Do Not Use catch(Exception) to Mask Programming Bugs

The following snippet almost guarantees operational headaches:

```java
// WRONG: every error is replaced with a default value.
static int parseOrZero(String text) {
    try {
        return Integer.parseInt(text);
    } catch (Exception ex) {
        return 0;
    }
}
```

It lumps together `NumberFormatException`, null cases, and other failures, then claims success.

If an **invalid input value** is an error that must halt, catch specifically and add context:

```java
static int parseRequiredScore(String text, int lineNumber) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid score at line " + lineNumber, ex);
    }
}
```

This function does not swallow the exception: the caller receives an `IllegalArgumentException` with a business message and the original `NumberFormatException` in `getCause()`.

If a score may be legitimately absent, define an explicit policy such as `OptionalInt.empty()` **only** for permitted absence. Never use `Optional.empty` in place of unrecoverable system failures.

### Do Not catch(Throwable) to “Ensure It Always Runs”

`Throwable` includes `Error` types such as `OutOfMemoryError` and `StackOverflowError`. These are generally **not skippable bad data**.

```java
// WRONG:
// try {
//     ...
// } catch (Throwable ignored) {
//     return Collections.emptyList();
// }
```

Catch only error types for which the current layer has a valid handling policy. Errors outside that scope should propagate to the lifecycle/task management layer.

## 10. When Interrupted, Do Not Swallow InterruptedException

Some blocking tasks inside a pipeline can throw `InterruptedException`. Stream functional interfaces do not declare this checked exception, so it cannot simply be ignored.

```java
import java.util.concurrent.TimeUnit;
import java.util.List;
import java.util.stream.Collectors;

List<String> results = tasks.stream()
        .map(task -> {
            try {
                TimeUnit.MILLISECONDS.sleep(10L);
                return task;
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while processing task " + task,
                        ex);
            }
        })
        .collect(Collectors.toList());
```

`tasks` is an assumed `List<String>` in the application. The snippet only shows how to preserve `cause` and **restore the interrupt flag** when a functional interface forbids throwing checked exceptions directly. In real background tasks, the coordinating layer may need a dedicated cancellation mechanism.

Avoid doing this:

```java
catch (InterruptedException ignored) {
    return task; // WRONG: pretends processing completed.
}
```

Especially with parallel streams, halting a pipeline does not mean all of your blocking tasks are automatically interrupted. Do not use `parallel()` as a cancellation or timeout mechanism for I/O sources without explicit design.

## 11. Choose Fail-Fast or Record Errors as Data?

Sometimes a dataset has a few corrupted records and the application is permitted to process the rest. **Not throwing an exception for every bad record** can be the right policy—provided converting errors into data is **intentional and auditable**.

We define a Java 8 `ParseOutcome` type to retain the line number, valid value, or failure `cause`.

```java
public final class ParseOutcome {
    private final int line;
    private final Integer value;
    private final RuntimeException error;

    private ParseOutcome(
            int line, Integer value, RuntimeException error) {
        this.line = line;
        this.value = value;
        this.error = error;
    }

    public static ParseOutcome parse(int line, String raw) {
        if (raw == null) {
            return new ParseOutcome(
                    line, null,
                    new IllegalArgumentException("Missing value"));
        }

        String normalized = raw.trim();
        if (normalized.isEmpty()) {
            return new ParseOutcome(
                    line, null,
                    new IllegalArgumentException("Blank value"));
        }

        try {
            return new ParseOutcome(
                    line, Integer.parseInt(normalized), null);
        } catch (NumberFormatException ex) {
            return new ParseOutcome(line, null, ex);
        }
    }

    public boolean isSuccess() {
        return error == null;
    }

    public int line() {
        return line;
    }

    public int value() {
        if (!isSuccess()) {
            throw new IllegalStateException(
                    "No parsed value at line " + line, error);
        }
        return value;
    }

    public RuntimeException error() {
        return error;
    }
}
```

Here parse errors **retain the original `NumberFormatException` object** in `ParseOutcome.error()`. It is neither turned into 0 nor stripped of its root cause.

For blank and null lines, the application explicitly creates an `IllegalArgumentException` describing the invalid case. Depending on requirements, you can also store an error code/type instead of keeping Throwable instances across millions of objects if memory cost matters.

### Using ParseOutcome in a Pipeline

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<String> raw = Arrays.asList(
        "10", "bad", "-3", "", null
);

List<ParseOutcome> outcomes =
        IntStream.range(0, raw.size())
                .mapToObj(i ->
                        ParseOutcome.parse(i + 1, raw.get(i)))
                .collect(Collectors.toList());

long success = outcomes.stream()
        .filter(ParseOutcome::isSuccess)
        .count();

long failure = outcomes.stream()
        .filter(o -> !o.isSuccess())
        .count();

System.out.println(success); // 2
System.out.println(failure); // 3
```

Error reporting still accesses line numbers and causes:

```java
for (ParseOutcome outcome : outcomes) {
    if (!outcome.isSuccess()) {
        System.err.println(
                "Line " + outcome.line()
                + " failed: "
                + outcome.error().getClass().getSimpleName());
    }
}
```

In production operations, do not log raw content if it contains sensitive data. To avoid writing millions of error lines, bound the number of detailed errors stored/logged while always tracking the total error count.

**This is not “swallowing errors.”** Errors are part of the output data model, classified, counted, and used to decide whether import is partially successful or failed. Callers must inspect `failure` instead of looking only at successful items.

## 12. Collecting Statistics Without Keeping Every Exception in Memory

If you only need accepted count, failure count, and total score, use three-argument `collect` with a small accumulator:

```java
public final class ImportStats {
    private long accepted;
    private long rejected;
    private long sum;

    public void add(ParseOutcome outcome) {
        if (outcome.isSuccess()) {
            accepted++;
            sum += outcome.value();
        } else {
            rejected++;
        }
    }

    public void merge(ImportStats other) {
        accepted += other.accepted;
        rejected += other.rejected;
        sum += other.sum;
    }

    public long accepted() { return accepted; }
    public long rejected() { return rejected; }
    public long sum() { return sum; }
}
```

Usage:

```java
ImportStats stats = IntStream.range(0, raw.size())
        .mapToObj(i -> ParseOutcome.parse(i + 1, raw.get(i)))
        .collect(
                ImportStats::new,
                ImportStats::add,
                ImportStats::merge);

System.out.println(stats.accepted()); // 2
System.out.println(stats.rejected()); // 3
System.out.println(stats.sum());      // 7
```

Key points:

- The `ImportStats::new` supplier creates a fresh accumulator per branch when the framework needs it.
- The accumulator increments exactly one of `accepted`/`rejected`.
- The `merge` combiner adds all fields; it never drops the right branch's data.
- For a fixed source, `accepted + rejected == raw.size()`.
- This pattern keeps `O(1)` statistics relative to record count, without retaining every `Throwable` for inspection.

If both statistics and sample errors are needed, design an accumulator with a **bounded sample error list** while keeping total error counts separate. Never accumulate exceptions unboundedly in long-running ingestion systems. `long` arithmetic still has limits; choose numeric types and overflow detection based on scale.

## 13. Terminal Operations Can Also Throw Errors

Not every exception comes from `map`. A `collect`, `reduce`, or `forEach` terminal can fail due to the operation's own contract.

### toMap on Duplicate Keys

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> byLength =
        Arrays.asList("cat", "dog")
                .stream()
                .collect(Collectors.toMap(
                        String::length,
                        s -> s));
// IllegalStateException: duplicate key 3.
```

**Do not** patch this error with an arbitrary merge function `(oldValue, newValue) -> oldValue` if the domain needs both records. Use `groupingBy` instead:

```java
import java.util.List;

Map<Integer, List<String>> grouped =
        Arrays.asList("cat", "dog")
                .stream()
                .collect(Collectors.groupingBy(String::length));

System.out.println(grouped.get(3)); // [cat, dog]
```

If business rules keep one record per key (e.g., latest by timestamp), define the merge function using **data properties and tie-breakers** rather than parallel branch order.

### reduce Can Throw ArithmeticException

```java
import java.util.Arrays;

int sum = Arrays.asList(Integer.MAX_VALUE, 1)
        .stream()
        .reduce(0, Math::addExact);
// ArithmeticException: integer overflow
```

`Math.addExact` detects overflow instead of letting an `int` sum wrap around. Never catch `ArithmeticException` and return 0 when 0 is also a valid sum. Report out-of-range figures or widen to `long`/`BigInteger` per business contract.

In parallel reduction, intermediate sums may be grouped differently; overflow-checked addition may throw under one grouping and not another if an intermediate sum exceeds bounds while the final mathematical sum fits. If partition-independent behavior is required, pick an appropriate numeric model.

### Custom Collectors

A Collector's `supplier`, `accumulator`, `combiner`, and `finisher` can all throw runtime exceptions. When diagnosing failures, inspect **all four**, not just input mappers. A Collector being `CONCURRENT` or running on a parallel Stream **does not eliminate** business errors from those functions.

## 14. Preserving Original Exceptions When Attaching Record Position

A message like `"For input string: abc"` does not tell you which line failed. You can add context in a wrapper while keeping `cause`.

```java
public final class InputLineException
        extends RuntimeException {

    private final long lineNumber;

    public InputLineException(
            long lineNumber, String message, Throwable cause) {
        super(message, cause);
        this.lineNumber = lineNumber;
    }

    public long lineNumber() {
        return lineNumber;
    }
}
```

Example parsing an ordered List:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<String> raw = Arrays.asList("10", "abc", "30");

List<Integer> parsed = IntStream.range(0, raw.size())
        .mapToObj(i -> {
            String text = raw.get(i);
            try {
                return Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                throw new InputLineException(
                        i + 1,
                        "Invalid integer at line " + (i + 1),
                        ex);
            }
        })
        .collect(Collectors.toList());
```

Callers can still inspect:

```java
try {
    runImport();
} catch (InputLineException ex) {
    System.err.println("Bad line: " + ex.lineNumber());
    System.err.println("Root type: "
            + ex.getCause().getClass().getSimpleName());
}
```

`runImport` here is an application method containing the pipeline above. With an explicitly indexed `List` source, line numbers are stable. With `parallelStream` from a file, **never** increment a shared `int[]` or `AtomicInteger` inside `map` to fake encounter-order line numbers; attach indices in a sequential reading step with a clear contract or hold `(lineNumber, text)` records at the source.

### Minimizing Sensitive Data Exposure

Even an original `NumberFormatException` can embed raw input text in its message. **Preserving `cause` for diagnostics** does not mean dumping full stack traces into broadly accessible logs. Log access control, redaction, and keeping only required metadata are operational responsibilities.

## 15. onClose and Suppressed Exceptions: Never Lose Cleanup Errors

`try-with-resources` closes resources even when the terminal operation throws. If **both processing and closing fail**, Java keeps the processing exception as **primary** and attaches the close error to `getSuppressed()`.

Runnable example with an in-memory Stream:

```java
import java.util.stream.Stream;

try (Stream<String> lines = Stream.of("A")
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {

    lines.forEach(s -> {
        throw new IllegalArgumentException("parse failed");
    });

} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage()); // parse failed

    for (Throwable suppressed : ex.getSuppressed()) {
        System.out.println(suppressed.getMessage());
        // close failed
    }
}
```

Looking only at `getMessage()` on the primary exception without checking `getSuppressed()` can miss that resource cleanup also failed.

**Key distinctions:**

- `getCause()` expresses **error A caused error B**.
- `getSuppressed()` holds **additional errors** occurring while unwinding the same failure, typically during close.
- `onClose(...)` runs only when `close()` is called, **not automatically after every terminal operation**.
- If the `try` body succeeds and `close` fails, the close error becomes the primary exception thrown.
- Never write `finally { return defaultValue; }`, because `return` inside `finally` can suppress exceptions from `try`.

An important design rule is **logging the full Throwable (where security permits)** at the error-handling boundary, since standard formatters display causes and suppressed exceptions. Do not log only `ex.getMessage()` and drop the stack trace.

## 16. Do Not Log-and-Swallow, and Do Not Double-Log at Every Layer

There are two opposing anti-patterns:

```java
// WRONG: logs only, then returns false success.
try {
    importRequiredData();
} catch (RuntimeException ex) {
    logger.warning("Import failed: " + ex.getMessage());
}
return ImportStatus.SUCCESS;
```

and:

```java
// NOISY: every layer logs the same exception and rethrows.
catch (RuntimeException ex) {
    logger.log(java.util.logging.Level.SEVERE,
            "Import failed", ex);
    throw ex;
}
```

The second snippet **does not lose the error**, yet if every layer does this, a single failure emits multiple near-identical logs. Instead:

- At low layers: catch specifically if adding context, then `throw` with cause or propagate as-is.
- At the interface/job boundary: **log once** with stack trace and safe details, then translate into an appropriate error response or failure status.
- At the user interface: return an understandable message without exposing sensitive stack traces or causes.

Centralized logging example:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

static final Logger LOG =
        Logger.getLogger("import-service");

static void runImportJob() {
    try {
        executeImport();
    } catch (ReportLoadException ex) {
        LOG.log(Level.SEVERE, "Import job failed", ex);
        // Report failure to scheduler/caller per job contract.
        throw ex;
    }
}
```

`executeImport` is an assumed application method. `LOG.log(Level.SEVERE, message, ex)` retains the Throwable instead of only a message. Rethrowing here is appropriate if the scheduler needs to know the job failed; if a protocol uses an explicit error status, translate at that boundary.

## 17. Parallel Streams: Do Not Rely on the “First” Exception

A parallel pipeline can process multiple partitions of data concurrently:

```java
import java.util.stream.IntStream;

int result = IntStream.range(0, 1000)
        .parallel()
        .map(n -> {
            if (n == 200 || n == 700) {
                throw new IllegalArgumentException(
                        "Bad value: " + n);
            }
            return n;
        })
        .sum();
```

In this situation:

1. There is no guarantee that the error for 200 is reported before 700.
2. Other tasks may have partially completed work; there is no automatic rollback.
3. Stack traces/causes may reflect the parallel execution layer; do not assert solely on messages.
4. There is no guarantee all errors across tasks are aggregated for the caller.
5. Catching outside the terminal handles the propagated error, yet does not undo prior side effects.

Do not write this test:

```java
// WRONG for the parallel pipeline above:
// assertEquals("Bad value: 200", exception.getMessage());
```

If the application must report **every** invalid record, convert expected errors into `ParseOutcome` or structured results and collect error counts. **Fail-fast** is a mechanism to halt on failure, not an exhaustive error-aggregation system.

### Thread-Safe Collectors Do Not Make Lambdas Harmless

`Collectors.groupingByConcurrent` and `toConcurrentMap` have their own concurrency guarantees. However, classifiers, value mappers, or merge functions can still throw exceptions. If they mutate external state, the collector being concurrent does **not** fix race conditions.

Do not use `parallel()` to “auto-retry” a failing mapper. Every Stream still permits only one terminal consumption per contract.

## 18. Short-Circuiting Does Not Validate All Elements

Operations like `findFirst`, `findAny`, `anyMatch`, `allMatch`, and `limit` may **avoid traversing the entire source**.

```java
import java.util.Arrays;

boolean found = Arrays.asList("100", "bad", "50")
        .stream()
        .anyMatch(s -> Integer.parseInt(s) >= 100);

System.out.println(found); // true, no need to parse "bad".
```

A pipeline containing `"bad"` that throws no error **does not prove** all data was validated.

```java
int first = Arrays.asList("7", "invalid")
        .stream()
        .map(Integer::parseInt)
        .findFirst()
        .orElseThrow(IllegalStateException::new);

System.out.println(first); // 7
```

If the requirement is “check every record before importing,” never use a short-circuiting terminal to prove validity. Choose an operation that collects all data requiring validation or a dedicated validation step. With parallel streams, do not assume mapper invocation count equals output element count when short-circuiting.

## 19. Proper Retry: Create a Fresh Source, Limit Attempts, Avoid Repeating Side Effects

Once consumed or failed during consumption, a Stream **cannot be reused**:

```java
import java.util.stream.Stream;

Stream<String> source = Stream.of("10", "20");
long first = source.count();

// WRONG: source is already consumed.
long second = source.count();
```

For **transient** file-reading errors, the example below shows retrying up to two attempts, opening a fresh source each time:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countWarningsWithOneRetry(Path path)
        throws IOException {

    IOException lastFailure = null;

    for (int attempt = 1; attempt <= 2; attempt++) {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                    .filter(s -> s.startsWith("WARN:"))
                    .count();

        } catch (UncheckedIOException ex) {
            lastFailure = ex.getCause();
        } catch (IOException ex) {
            lastFailure = ex;
        }
    }

    throw new IOException(
            "Cannot count warnings after two attempts",
            lastFailure);
}
```

This is an **illustrative pattern**, without delay/backoff, deadlines, or retryability classification. In production:

- Retry **only errors identified as transient**; a parse error is a data error, so retrying the exact same string will not help.
- Enforce **attempt and time bounds**, considering backoff.
- Ensure input across attempts is a consistent snapshot if consistent results are required.
- If the pipeline writes to databases or sends requests, establish **idempotency** or transactions before retrying.
- Preserve the final attempt's cause in the summary exception; record earlier attempts as diagnostics/suppressed where appropriate.

Never retry by calling a terminal again on an old `Stream` instance or reusing a closed Reader.

## 20. Unit Testing: Do Not Just Check “An Exception Was Thrown”

A good test verifies **exception type**, **cause chain**, **output state**, and **resource closing**, rather than merely checking that some exception occurred.

Example using **JUnit Jupiter** (an external test dependency beyond the JDK):

```java
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExceptionSafetyTest {

    @Test
    void parseFailureKeepsOriginalCause() {
        IllegalArgumentException ex =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> parseRequiredScore("abc", 7)
                );

        assertTrue(ex.getMessage().contains("line 7"));
        assertInstanceOf(NumberFormatException.class,
                ex.getCause());
    }

    @Test
    void dataErrorsAreCountedInsteadOfIgnored() {
        java.util.List<String> raw =
                Arrays.asList("10", "bad", "-3", "", null);

        ImportStats stats = java.util.stream.IntStream
                .range(0, raw.size())
                .mapToObj(i ->
                        ParseOutcome.parse(i + 1, raw.get(i)))
                .collect(
                        ImportStats::new,
                        ImportStats::add,
                        ImportStats::merge);

        assertEquals(2L, stats.accepted());
        assertEquals(3L, stats.rejected());
        assertEquals(7L, stats.sum());
    }
}
```

`parseRequiredScore`, `ParseOutcome`, and `ImportStats` were defined in earlier sections. `assertInstanceOf` is a helper in modern JUnit Jupiter versions; if your version lacks it, replace with:

```java
assertTrue(ex.getCause() instanceof NumberFormatException);
```

A dedicated test for `try-with-resources` and suppressed exceptions:

```java
import java.util.stream.Stream;

IllegalArgumentException ex;
try {
    try (Stream<String> source = Stream.of("x")
            .onClose(() -> {
                throw new IllegalStateException("close");
            })) {
        source.forEach(s -> {
            throw new IllegalArgumentException("body");
        });
    }
    throw new AssertionError("Expected processing failure");
} catch (IllegalArgumentException caught) {
    ex = caught;
}

if (ex.getSuppressed().length != 1
        || !"close".equals(
                ex.getSuppressed()[0].getMessage())) {
    throw new AssertionError("Suppressed close error missing");
}
```

**Testing note:** do not depend on exact JVM messages for `NumberFormatException` or exact wrapper types added by the parallel framework. Assert only **application-contract guarantees**. For I/O errors, use fixtures or controllable source components rather than trying to trigger flaky races.

## 21. Common Mistakes Found in Code Reviews

| Anti-pattern | Consequence | Alternative |
| --- | --- | --- |
| `catch (Exception ignored) {}` | Errors vanish | Handle properly or rethrow |
| Catching errors and returning `0`, `null`, empty List | Mixes errors with valid data | Proper `Result`/`Optional` or fail-fast |
| `new RuntimeException("failed")` | Drops original cause | `new RuntimeException("context", ex)` |
| Logging only `ex.getMessage()` | Loses stack trace, cause, and suppressed | Log full Throwable at trusted boundary |
| Logging then returning `SUCCESS` | Fabricates completion status | Report failure per contract |
| Logging and rethrowing at every layer | Duplicate noisy logs | Centralize logging, wrap when needed |
| Catching every `Throwable` | Swallows fatal errors | Catch handleable exceptions only |
| Swallowing `InterruptedException` | Loses cancellation/interrupt signal | Restore interrupt flag and propagate |
| Wrapping `IOException` with a string and no cause | Loses original I/O failure | `UncheckedIOException(message, ex)` |
| Catching around `map` construction | Misses lazy error at terminal | Catch around terminal or inside mapper |
| Using `map(...).count()` for validation | Mapper may be skipped | Collect real validation outcomes |
| Catching `toMap` duplicate keys and keeping an arbitrary one | Hides missing merge rule | `groupingBy` or proper merge policy |
| Swallowing `Math.addExact` overflow | Untrustworthy sum values | Widen numeric range or report error |
| Leaving `Files.lines` unclosed on exception | Resource leak | `try-with-resources` |
| Forgetting to check `getSuppressed()` | Misses close failures | Preserve and inspect suppressed errors |
| `return` from `finally` | Can mask exceptions from `try` | Let `try-with-resources` manage close |
| Retrying on a consumed Stream | `IllegalStateException` or partial data | Create a fresh source |
| Retrying non-idempotent side effects | Duplicate writes/sends | Transactions/idempotency |
| Asserting “first element error” in parallel | No scheduling guarantee | Test error contract without forcing order |
| Logging entire records with sensitive data | Security risk | Redaction and log access control |
| Turning every failure into `Optional.empty()` | Mixes absence with failure | Separate absence, validation, and system errors |

## 22. Layered Exception-Handling Workflow

```text
An operation fails
         |
         v
 What kind of error is it?
   /       |          \
 data     I/O       bug / other infra
   |       |               |
   v       v               v
Allowed   Is it         Never hide error
by        truly         with fallback
policy    retryable?
to skip?    |
  / \      / \
Yes  No  Yes  No
 |   |    |   |
 v   v    v   v
Count Throw Fresh Throw/wrap
in   with  source, keep cause
Res  cause bounded
        |     |
        +--+--+
           v
   Task/API Boundary
           |
  log once + safe context
           |
  explicit failure status
```

Choose deliberately where to **turn errors into data** and where to **translate errors into higher-layer exceptions**. Only when both form an explicit contract can a pipeline stay both readable and reliable.

## 23. Pre-Production Pipeline Checklist

1. Are there any empty `catch` blocks, catches returning 0/`null`/empty Lists, or log-and-succeed paths?
2. When wrapping exceptions, does the constructor pass the original `cause`?
3. Can errors in `map`/`filter` surface **when the terminal runs**, rather than where the pipeline is created?
4. Which terminals short-circuit or skip callbacks via optimization? Does validation depend on callback counts?
5. Are expected data errors, I/O errors, programming bugs, and task interruption signals separated?
6. When using `Result`, do accepted + rejected counts reconcile against total input elements?
7. When using custom Collectors, do supplier/accumulator/combiner/finisher propagate errors properly without improper shared state?
8. Does `try-with-resources` wrap the exact I/O resource that needs closing?
9. If both processing and closing fail, are primary and suppressed exceptions preserved?
10. Are full exceptions logged at an appropriate boundary without duplicate logging or leaking sensitive data?
11. If retrying, is there a fresh source, bounded attempts, transient-error classification, snapshot consistency, and idempotency?
12. If parallel, do you avoid assuming errors appear in encounter order or that all tasks roll back?
13. Do tests cover valid data, parse errors, nulls, empty sources, duplicate keys, overflow, and resource closing?
14. Are default values used **only** when business rules allow, rather than masking failures?

## 24. Practice Exercises

### Exercise A: Fixing Code That Swallows Errors

Given the pipeline:

```java
List<Integer> values = raw.stream()
        .map(s -> {
            try {
                return Integer.parseInt(s);
            } catch (Exception ignored) {
                return 0;
            }
        })
        .collect(Collectors.toList());
```

**Task:** rewrite it in two ways: (1) fail-fast using `IllegalArgumentException(message, cause)` with line context; (2) using `ParseOutcome` to count failed records accurately. Compare the results returned to the caller and auditability.

### Exercise B: Propagating the Cause of Files.size

Create a `List<Path>` containing two real files and one non-existent path. Inside `map`, wrap `IOException` with `UncheckedIOException`. In the caller, verify `getCause()` is `IOException` and do not return a “successful” total size if a required file cannot be read.

### Exercise C: Primary and Suppressed

Register `onClose` with a handler throwing `IllegalStateException("close")`. Inside `forEach`, throw `IllegalArgumentException("body")`. Verify the primary exception is the processing error and the suppressed list contains the close error. Also test when only closing fails.

### Exercise D: Reporting Bad Data

Given the source:

```text
"10", "bad", "-3", "", null
```

Expected output:

```text
accepted = 2
rejected = 3
sum = 7
```

Use `ParseOutcome` and `ImportStats`. Do not catch all `RuntimeException`s as if they were merely parse errors.

### Exercise E: Duplicate Keys and Overflow

Try `toMap(String::length, s -> s)` on `"cat"`/`"dog"`. Define an appropriate duplicate-key strategy instead of catching the error and keeping an arbitrary element. Next, try `reduce(0, Math::addExact)` with `Integer.MAX_VALUE` and `1`; design an error-reporting policy or widen the numeric range.

### Exercise F: Retries and One-Shot Sources

Use `Files.lines` with an immutable fixture. Design a factory opening a fresh Stream per attempt, closing every Stream, and bounding retries. Explain why calling a terminal a second time on the same failed Stream is invalid.

### Exercise G: Errors in Parallel

Configure two elements at different positions in `IntStream.range(...).parallel()` to throw `IllegalArgumentException`. Write a test that **does not** constrain which element reports first; then replace fail-fast with `ParseOutcome` to report all expected data errors.

## 25. Self-Check Questions

1. What is exception swallowing? **Catching an error and erasing the failure signal without a valid handling contract**.
2. Why is `catch (Exception ex) { return 0; }` dangerous? **It makes an error look like a valid numeric 0**.
3. When creating a new exception, how do you preserve the original error? **Use a constructor accepting `cause`, e.g., `new IllegalStateException(message, ex)`**.
4. How do `getCause()` and `getSuppressed()` differ? **Cause represents a causal chain; suppressed holds additional errors, typically during cleanup**.
5. When do errors in `map` usually appear? **When a terminal requests evaluating that element**.
6. Does `map(parse).count()` always invoke every mapper? **No**, Stream can optimize away the mapper.
7. Does `Function.apply` allow throwing `IOException` directly without catching/wrapping? **No**, it is a checked exception absent from `Function`'s signature.
8. Which type should wrap `IOException` inside a lambda to preserve I/O semantics? **`UncheckedIOException(message, cause)`**.
9. Can every `RuntimeException` be treated as a single-record error? **No**, some are bugs or infrastructure errors requiring fail-fast.
10. Why shouldn't you catch `Throwable` to return success? **It can swallow critical `Error`s**.
11. When catching `InterruptedException` where checked exceptions cannot be thrown, what must you mind? **Restore the interrupt flag and propagate an error with cause per caller contract**.
12. What does `ParseOutcome` enable? **Retaining data errors as structured results that can be counted and audited**.
13. Why avoid holding millions of Throwables in memory? **High memory/stack-trace cost; use statistics or bounded error samples**.
14. What can `toMap` without a merge function throw on duplicate keys? **`IllegalStateException`**.
15. What does `reduce(0, Math::addExact)` throw on `int` overflow? **`ArithmeticException`**.
16. In what forms can `Files.lines` throw when opening vs. iterating? **`IOException` and `UncheckedIOException`**.
17. Does `collect` automatically close a Stream from `Files.lines`? **No**.
18. When does `onClose` execute? **When the Stream is closed, not merely because a terminal finished**.
19. If both body and close fail in `try-with-resources`, which is usually primary? **The body error; the close error is suppressed**.
20. Does logging an error automatically mean it has been handled? **No**, result status must obey the contract.
21. Is retrying on a consumed Stream valid? **No**, a fresh source must be created.
22. What is required before retrying an operation with side effects? **Confirming the error is transient, bounding attempts, and ensuring idempotency/transactions**.
23. With two errors in a parallel stream, which must be reported first? **There is no source-order guarantee**.
24. Why limit raw data inside exception messages? **Causes/messages may expose sensitive data**.
25. What is the most important rule when writing `catch`? **Know whether you can validly handle the error or must propagate it with cause, never faking success**.

**Guiding Principle:** A safe Java Stream pipeline **never hides failures behind default values** and **never drops the original exception when crossing abstraction layers**. Catch the right error types at the right lazy/terminal boundaries, pass `cause` when wrapping, preserve `suppressed exceptions` during resource cleanup, use structured `Result` values when per-record handling is permitted by business rules, and avoid depending on error order under parallel execution. If a layer cannot guarantee the post-handling result obeys its contract, let the error propagate clearly to the responsible layer.
