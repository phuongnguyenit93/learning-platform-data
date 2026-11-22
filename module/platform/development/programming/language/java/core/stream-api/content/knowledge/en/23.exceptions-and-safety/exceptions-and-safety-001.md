# Exception Propagation from Source, Mapping Functions, and Terminal Operations

The Java Stream API lets you describe data processing with a pipeline of `filter`, `map`, `reduce`, and `collect`. But when data is invalid, an I/O source fails, or a Collector cannot complete, **where do exceptions arise and how are they propagated?** This is a critical question in both business logic and testing.

A core characteristic of Stream is **lazy evaluation**: most intermediate operations do not traverse data immediately when declared. Exceptions from `map` or `filter` therefore typically appear only when a terminal operation actually requests elements to be computed. With resource-backed sources like `Files.lines`, you must also distinguish **source-opening** errors from **iteration-reading** errors, and remember that finishing processing does not automatically close the source.

This lesson belongs to the **Exceptions and Safety** chapter of the `JAVA_STREAM_API` module. We will analyze three error layers in turn — **source**, **transformations**, and **terminal operations** — and then build fail-fast or per-record error-collecting strategies, preserve causes, manage `try-with-resources`, test parallel pipelines, and avoid dangerous assumptions that every element is processed.

> **Environment:** The main Stream examples use the **Java 8 or later** API. Each code block may represent a snippet in `main`, JShell, or a standalone method as described; classes/helpers can be placed separately. Examples that intentionally throw exceptions are clearly marked. Choosing whether to skip data, record errors, or halt the entire pipeline is a **business policy**, not a behavior automatically decided by the Java Stream API.

## 1. Exceptions Can Occur at Three Different Layers

A typical pipeline:

```text
Stream<T> Source
   |
   |  [1] source creation and reading
   |      - IOException when opening file
   |      - UncheckedIOException when iterating lines
   |      - IllegalStateException from custom source
   v
filter / map / flatMap / peek
   |
   |  [2] functions in the pipeline
   |      - NumberFormatException on parse
   |      - NullPointerException on null access
   |      - IllegalArgumentException on validation
   v
collect / reduce / count / forEach / findFirst
   |
   |  [3] terminal operations and Collector
   |      - IllegalStateException due to duplicate toMap key
   |      - ArithmeticException from overflow-checked addition
   |      - exceptions from accumulator/combiner/finisher
   v
Result or exception
```

| Layer | Typical timing | Example | Handling approach |
| --- | --- | --- | --- |
| Source creation | When calling source factory | `Files.lines(path)` cannot open file | Catch or declare `IOException` at I/O boundary |
| Lazy source iteration | When terminal pulls elements | Read error from `Files.lines` after a few lines | Handle `UncheckedIOException`, ensure source is closed |
| Intermediate operation | When element actually passes through function | `Integer.parseInt("abc")` in `map` | Fail-fast or convert error into a value |
| Terminal operation | During collection/reduction | `toMap` hits duplicate key; `reduce` throws | Choose right merge policy/collector, do not hide errors |
| Resource cleanup | When calling `Stream.close()` or exiting `try` | Close handler throws exception | Track primary exception and suppressed exceptions |

**Rule:** identify **where the error originates** and **where the error is observed**. These two places do not necessarily coincide. With Stream, the call that builds the pipeline usually only assembles the stages; an error inside a lambda may surface later at the terminal call.

## 2. Lazy Evaluation: Writing map Does Not Mean map Has Run

The following snippet **has not parsed any string** at the moment `map` is called:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> raw = Arrays.asList("10", "20", "not-a-number");

Stream<Integer> numbers = raw.stream()
        .map(Integer::parseInt); // has not iterated elements yet

// Error usually surfaces at the terminal operation:
List<Integer> parsed = numbers.collect(Collectors.toList());
// NumberFormatException: For input string "not-a-number"
```

`Integer::parseInt` can throw `NumberFormatException`, a `RuntimeException`. In this pipeline, collecting into a list requires all results, so it eventually encounters the invalid element.

A common mistake is placing `try/catch` around **only the Stream construction block**:

```java
Stream<Integer> pending;

try {
    pending = raw.stream().map(Integer::parseInt);
} catch (NumberFormatException ex) {
    // Does not catch parse errors thrown later during collect.
    throw new IllegalStateException("Cannot parse input", ex);
}

pending.collect(Collectors.toList()); // error surfaces here
```

To catch errors at the processing boundary, wrap `try/catch` around the **terminal operation**:

```java
try {
    List<Integer> parsed = raw.stream()
            .map(Integer::parseInt)
            .collect(Collectors.toList());
    System.out.println(parsed);
} catch (NumberFormatException ex) {
    System.err.println("Invalid integer: " + ex.getMessage());
}
```

Not every intermediate lambda is guaranteed to be invoked. For example, some pipelines whose source has a known size and whose terminal is `count()` can be optimized to **skip executing `map`**:

```java
long count = raw.stream()
        .map(Integer::parseInt) // may not run
        .count();

System.out.println(count); // May be 3, without necessarily throwing a parse error
```

**Do not use `count()` with a `map` just to “force validation”** if the mapped values are not needed by the Stream result. If you must validate all data, design a terminal operation that consumes the transformed values or a dedicated error-aggregation operation.

## 3. Source Exceptions: Opening the Source Differs from Reading the Source

With a file source:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
```

There are **two distinct failure points**:

1. **Source creation:** `Files.lines(...)` can throw `IOException` immediately when opening the file, for example if it does not exist or lacks permissions.
2. **Source consumption:** reading the file happens lazily. If I/O fails during iteration, the Stream from `Files.lines` can throw `UncheckedIOException` from the terminal operation.

`UncheckedIOException` is a `RuntimeException` wrapping an `IOException`. When you need the wrapped I/O cause, use `getCause()`:

```java
import java.io.UncheckedIOException;

try {
    countLines(path);
} catch (UncheckedIOException ex) {
    System.err.println("Read failed: "
            + ex.getCause().getMessage());
} catch (IOException ex) {
    System.err.println("Open/close failed: "
            + ex.getMessage());
}
```

`countLines` is declared `throws IOException` to represent checked errors at the source layer. Runtime exceptions like `UncheckedIOException` can still propagate without being declared in the signature.

**Note:** `Stream.count()` has optimizations based on source size when applicable; do not write test code that depends on every line definitely being materialized in all cases. To inspect content, use a pipeline that needs to read/parse that data.

### Custom Sources Can Also Throw During Iteration

If an `Iterator`, `Spliterator`, or element-emitting supplier throws a `RuntimeException`, the error can emerge when the terminal pulls the corresponding element:

```java
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

Iterator<String> source = new Iterator<String>() {
    private int index;

    @Override
    public boolean hasNext() {
        if (index == 2) {
            throw new IllegalStateException("Source read failed");
        }
        return index < 4;
    }

    @Override
    public String next() {
        return "event-" + index++;
    }
};

Spliterator<String> spliterator =
        Spliterators.spliteratorUnknownSize(
                source, Spliterator.ORDERED);

try {
    StreamSupport.stream(spliterator, false)
            .collect(Collectors.toList());
} catch (IllegalStateException ex) {
    System.err.println(ex.getMessage()); // Source read failed
}
```

An outer `try/catch` around the terminal can catch the error, but **cannot recover a partially consumed Iterator**. To retry, you must create a **new source** with an explicit retry policy and data consistency guarantees.

## 4. Exceptions from map, filter, flatMap, and Callbacks

Functions in a Stream are typically represented by `Function`, `Predicate`, `Consumer`, or primitive functional interfaces. If a callback throws a `RuntimeException` or `Error`, it generally propagates out of pipeline execution; Stream does not automatically turn a failing element into `Optional.empty()` or log it for you.

### map: Parse or Type-Conversion Errors

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList("7", "x", "12")
        .stream()
        .map(Integer::parseInt)
        .collect(Collectors.toList());
// NumberFormatException at "x"
```

The snippet above is a **fail-fast example**. The output list is not returned normally if parsing throws an exception. Do not assume Java will return `[7]` as a complete result and skip the invalid element.

### filter: Predicate Can Also Throw Exceptions

```java
import java.util.Arrays;

boolean hasHighValue = Arrays.asList("10", "bad", "50")
        .stream()
        .anyMatch(text -> Integer.parseInt(text) > 40);
```

With the sequential version and this order, the predicate encounters `"bad"` before reaching `"50"`, so it throws `NumberFormatException`. If `"50"` came first, `anyMatch` could return `true` without evaluating subsequent elements.

### flatMap: Errors from Nested Sources

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> records = Arrays.asList("a,b", "c,d", "e,f");

List<String> tokens = records.stream()
        .flatMap(line -> Stream.of(line.split(",")))
        .collect(Collectors.toList());
```

This snippet is valid for three non-null strings. But if `line` is `null`, `line.split(...)` throws `NullPointerException` when the mapper runs. With nested file sources, `flatMap` may pull elements from a sub-stream and hit an error while iterating that sub-stream. By the `flatMap` contract, **each returned sub-stream is closed after its contents are placed into the pipeline**; however, that does not replace closing the outer source stream if it holds resources.

### Functions with Side Effects: Exceptions Do Not Roll Back Side Effects

```java
import java.util.Arrays;
import java.util.List;

List<String> values = Arrays.asList("A", "B", "C");

values.stream().forEach(value -> {
    if ("B".equals(value)) {
        throw new IllegalArgumentException("B is not allowed");
    }
    System.out.println("Processed: " + value);
});
```

`"Processed: A"` may already have been printed before the error occurs. If instead of logging you write to a database, send an email, or call an API, actions already performed **are not automatically rolled back** when the Stream throws an exception. You need transaction/idempotency design at the business layer if all-or-nothing semantics are required.

## 5. Checked Exceptions Do Not Pass Through Function Directly

`Function<T,R>.apply` does not declare `throws IOException`. Therefore the following lambda **fails to compile**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

// WRONG: Files.size(...) throws checked IOException.
List<Long> sizes = paths.stream()
        .map(path -> Files.size(path))
        .collect(java.util.stream.Collectors.toList());
```

This example illustrates a compilation error; `paths` is assumed to be `List<Path>`. The compiler does not allow ignoring the checked exception from `Files.size` inside `Function`.

There are three policy choices:

1. **Wrap into an unchecked exception preserving the cause**, such as `UncheckedIOException`, when fail-fast is needed.
2. **Convert the outcome into an error-carrying value** (Result/Outcome) to retain both valid data and errors.
3. **Move the I/O operation outside the pipeline** or use an explicit loop if complex checked-exception handling is required.

You should not use a generic “sneaky throw” to bypass exception checking just to keep Stream syntax concise; it can make API contracts harder to read and operate.

## 6. Proper Fail-Fast: UncheckedIOException Preserving Cause

Example converting each path into file size:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

static List<Long> readSizes(List<Path> paths) {
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
    List<Long> sizes = readSizes(paths);
    System.out.println(sizes);
} catch (UncheckedIOException ex) {
    IOException cause = ex.getCause();
    System.err.println("I/O error: " + cause.getMessage());
}
```

Why choose `UncheckedIOException` instead of `new RuntimeException(ex)`?

- The exception type **clearly states this is an I/O error**.
- `getCause()` has return type `IOException`.
- The stack trace preserves the cause chain from the original operation.

`UncheckedIOException` does not turn the error into “handled successfully.” It only lets the error travel through a callback that does not declare checked exceptions, so the outer layer can decide whether to report the error, retry, or return a failed status.

**Do not catch `Exception` too broadly inside a mapper** and turn every error into `0`. I/O errors, parse errors, programming bugs, and business contract violations may require different policies.

## 7. Handling a Failing Element: Fail-Fast, Skip, or Keep Errors?

There is no single right choice for every system.

| Policy | Representation | Advantages | Risks |
| --- | --- | --- | --- |
| **Fail-fast** | Throw exception on invalid element | Never hides corrupted data | Halts entire result, side effects may remain |
| **Intentional skip** | Drop invalid element after validation | Continues processing good data | Data loss if error count is not tracked/recorded |
| **Keep errors as data** | `ParseResult` or `Either` type | Reports both successes and failures | Requires defining result type and handling it explicitly |
| **Fallback** | Meaningful business default value | Continuous output when errors are tolerable | Can mask serious discrepancies |
| **Retry** | Re-create operation/source per policy | Useful for certain transient errors | May repeat side effects or hit same permanent error |

For financial/business figures, silently dropping an erroneous row can corrupt reports. For telemetry, the system may choose to continue while recording the count of bad rows to monitor data quality.

### Only Skip Data According to Explicitly Defined Rules

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList(" 10 ", "", " -3 ", null, "25");

List<Integer> parsed = raw.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .map(Integer::parseInt)
        .collect(Collectors.toList());

System.out.println(parsed); // [10, -3, 25]
```

This pipeline only handles **null/blank strings**, because they are filtered out before parsing. If a string is `"abc"`, `Integer.parseInt` still throws `NumberFormatException`. Do not describe this pipeline as “automatically skipping all bad records.”

A safer approach is using `Result` to distinguish actual parse errors while retaining original record information.

## 8. The Result Pattern: Turning Parse Errors into Collectible Values

Java 8 example, without requiring `record` or external libraries:

```java
public final class ParseResult {
    private final String raw;
    private final Integer value;
    private final String error;

    private ParseResult(String raw, Integer value, String error) {
        this.raw = raw;
        this.value = value;
        this.error = error;
    }

    public static ParseResult from(String raw) {
        if (raw == null) {
            return new ParseResult(null, null, "Missing value");
        }

        String normalized = raw.trim();
        if (normalized.isEmpty()) {
            return new ParseResult(raw, null, "Blank value");
        }

        try {
            return new ParseResult(
                    raw, Integer.parseInt(normalized), null);
        } catch (NumberFormatException ex) {
            return new ParseResult(
                    raw, null, "Not an integer: " + normalized);
        }
    }

    public boolean isValid() {
        return error == null;
    }

    public int value() {
        if (!isValid()) {
            throw new IllegalStateException(
                    "Cannot read value from failed ParseResult");
        }
        return value;
    }

    public String error() {
        return error;
    }

    public String raw() {
        return raw;
    }
}
```

Each element is represented as **a success or failure outcome**, preventing one predictable data error from breaking the entire Stream:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<ParseResult> results = Arrays.asList(
        "10", "bad", "-3", "", null
).stream()
 .map(ParseResult::from)
 .collect(Collectors.toList());

Map<Boolean, Long> byValidity = results.stream()
        .collect(Collectors.partitioningBy(
                ParseResult::isValid,
                Collectors.counting()));

System.out.println(byValidity.get(true));  // 2
System.out.println(byValidity.get(false)); // 3
```

Extracting the successful values:

```java
List<Integer> accepted = results.stream()
        .filter(ParseResult::isValid)
        .map(ParseResult::value)
        .collect(Collectors.toList());

System.out.println(accepted); // [10, -3]
```

Extracting error details:

```java
List<String> errors = results.stream()
        .filter(r -> !r.isValid())
        .map(r -> "raw=" + r.raw() + ", error=" + r.error())
        .collect(Collectors.toList());

System.out.println(errors.size()); // 3
```

**Benefit:** you can reconcile `total = accepted + rejected`. Expected errors such as blank strings or non-numeric values become reportable data.

**Limitation:** this pattern does not mean you should catch `OutOfMemoryError`, `StackOverflowError`, or every `RuntimeException` and treat them as per-record data errors. For unrecoverable infrastructure or programming errors, fail-fast can be safer.

## 9. Single-Pass Processing of Valid Data and Errors Without Storing All Results

`results.stream().collect(toList())` in the previous section keeps every `ParseResult` in memory. For large sources, you can build compact statistics in a single collection pass:

```java
import java.util.List;

final class ImportSummary {
    private long accepted;
    private long rejected;
    private long sum;

    void add(ParseResult result) {
        if (result.isValid()) {
            accepted++;
            sum += result.value();
        } else {
            rejected++;
        }
    }

    void merge(ImportSummary other) {
        accepted += other.accepted;
        rejected += other.rejected;
        sum += other.sum;
    }

    long accepted() { return accepted; }
    long rejected() { return rejected; }
    long sum() { return sum; }
}
```

Usage:

```java
import java.util.Arrays;

ImportSummary summary = Arrays.asList(
        "10", "bad", "-3", "", null
).stream()
 .map(ParseResult::from)
 .collect(
         ImportSummary::new,
         ImportSummary::add,
         ImportSummary::merge
 );

System.out.println(summary.accepted()); // 2
System.out.println(summary.rejected()); // 3
System.out.println(summary.sum());      // 7
```

The `ImportSummary::new` supplier creates a separate accumulator when the framework needs multiple branches. `merge` combines all three fields completely without dropping data. This design does not store individual error `String`s; if you need to audit each bad record, store them separately with a bounded limit, write them to a resource-managed destination, or return a capped list of errors.

Do not write from `ImportSummary.add` into a shared external `ArrayList` without synchronization. With a parallel stream, having a fresh accumulator per branch is required for mutable reduction under this pattern to work correctly. `long` can still overflow on extremely large datasets; if the domain requires absolute precision, checked arithmetic is needed.

## 10. Exceptions from Terminal Operations

Many developers only look at `map` or `filter` when hunting for bugs, yet terminal operations can also actively throw exceptions:

| Terminal | Error scenario | Notes |
| --- | --- | --- |
| `collect(toMap(...))` | Duplicate key without merge function | `IllegalStateException` |
| `collect(groupingBy(...))` | Classifier produces null key | `NullPointerException` with standard collector |
| `reduce(...)` | Operator throws, e.g., `Math.addExact` overflow | Exception from accumulator/combiner |
| `forEach(...)` | Consumer throws | Side effects before the error do not roll back |
| `findFirst()` | Selected element is null | May throw `NullPointerException` |
| `Optional.get()` after terminal | Empty `Optional` | `NoSuchElementException` from `get` |
| `collect(customCollector)` | Bug in supplier/accumulator/combiner/finisher | Exception depends on Collector code |
| `count()` | Does not require all intermediate steps to run | Do not rely on `count` for validation side effects |

### Example: toMap Encountering Duplicate Keys

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> byLength = Arrays.asList("cat", "dog")
        .stream()
        .collect(Collectors.toMap(
                String::length,
                s -> s
        ));
// IllegalStateException: both strings produce key 3.
```

The error here is not data parsing, but **failing to define how duplicate keys are resolved**. If the goal is to keep all strings by length, use `groupingBy`:

```java
import java.util.List;

Map<Integer, List<String>> grouped = Arrays.asList("cat", "dog")
        .stream()
        .collect(Collectors.groupingBy(String::length));

System.out.println(grouped.get(3)); // [cat, dog]
```

If business logic wants to select one element according to a rule, use `toMap(keyMapper, valueMapper, mergeFunction)`, keeping the merge function valid and order-independent if results must remain stable under parallel execution.

### Example: reduce with an Operator That Throws

```java
import java.util.Arrays;

int sum = Arrays.asList(Integer.MAX_VALUE, 1)
        .stream()
        .reduce(0, Math::addExact);
// ArithmeticException: integer overflow
```

`Math.addExact` is useful when overflow must be detected instead of allowing wrap-around. However, in parallel reduction, combining sub-parts may produce different intermediate sums. If the final mathematical sum fits in range while an intermediate grouping overflows, whether an exception is thrown can depend on partitioning. Define the arithmetic contract and pick the appropriate type/algorithm before comparing sequential and parallel execution.

### An Empty Optional Is Not an Error When Modeled Properly

```java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> firstEven = Arrays.asList(1, 3, 5)
        .stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(firstEven.isPresent()); // false
```

Do not call `firstEven.get()` when it is empty. Choose `orElse`, `orElseGet`, or `orElseThrow` with a clear business message depending on the problem.

## 11. Controlling Order and Short-Circuiting When Errors Occur

A short-circuiting terminal operation may **never reach an invalid element**:

```java
import java.util.Arrays;

boolean found = Arrays.asList("100", "bad", "10")
        .stream()
        .anyMatch(s -> Integer.parseInt(s) >= 100);

System.out.println(found); // true
```

Here the first number `100` is enough to return `true`; `"bad"` later in the list does not need to be parsed in sequential execution.

Similarly:

```java
int first = Arrays.asList("7", "invalid")
        .stream()
        .map(Integer::parseInt)
        .findFirst()
        .orElseThrow(IllegalStateException::new);

System.out.println(first); // 7
```

Not encountering an error in a terminal operation **does not prove** that all records are valid.

### Parallel Streams May Process Elements Out of Temporal Order

On a `parallelStream()`, the framework can evaluate elements across multiple branches before knowing the terminal already has enough results. You cannot assert “because there is `limit(1)`, other elements definitely had their mapper skipped.” The correctness of a parallel pipeline must not rely on side effects or throwing an exception at a specific point in time.

If the requirement is to **validate every record and fail if any record is invalid**, design a collection/reduction operation that inspects the entire dataset, rather than using `findAny`, `anyMatch`, or `limit` as a mechanism to guarantee all elements were checked.

### peek Should Not Be Used to Verify Exception Throwing

```java
long length = Arrays.asList("A", "B", "C")
        .stream()
        .peek(s -> {
            if ("B".equals(s)) {
                throw new IllegalStateException("B detected");
            }
        })
        .count();
```

A pipeline with a known source size and `count()` can be optimized without running `peek`. `peek` is suited for **temporary observation**, not for attaching mandatory validation or business writes.

## 12. Error Propagation in Parallel Execution: Do Not Rely on the “First Error”

When using `parallel()`, multiple tasks may process different portions of the data simultaneously. A `map` or `reduce` operation can throw an error in one task while other tasks are still running.

```java
import java.util.stream.IntStream;

int total = IntStream.range(0, 1000)
        .parallel()
        .map(n -> {
            if (n == 200 || n == 700) {
                throw new IllegalArgumentException(
                        "Invalid element: " + n);
            }
            return n;
        })
        .sum();
```

If the pipeline throws an exception:

- There is **no guarantee** that the failing element with the smaller index will be reported first.
- Do not use stack trace ordering or worker log order to infer encounter order.
- Other tasks may have already processed part of the data; do not rely on “all or nothing” side effects.
- Exceptions may pass through the parallel execution layer with a `cause` chain; preserve the full stack trace/causes for diagnostics rather than only logging `ex.getMessage()`.
- Do not expect all concurrent errors to be returned together in a single result set. Fail-fast is not an error-collecting mechanism.

Example of boundary handling:

```java
try {
    int total = IntStream.range(0, 1000)
            .parallel()
            .map(n -> {
                if (n == 200 || n == 700) {
                    throw new IllegalArgumentException(
                            "Invalid element: " + n);
                }
                return n;
            })
            .sum();

    System.out.println(total);
} catch (RuntimeException ex) {
    // Log the full exception/stack trace and any cause.
    ex.printStackTrace();
    throw ex; // rethrow intact for the caller to handle
}
```

Do not write a test hardcoding `ex.getMessage().equals("Invalid element: 200")` for this parallel pipeline. Assert the **category of failure** and correctness of the handling policy, or convert all expected errors into values before collecting if full reporting is required.

### Concurrent Collectors Do Not Eliminate Business Errors

`groupingByConcurrent` or `toConcurrentMap` accumulate safely according to their contract, yet classifiers, mappers, or merge functions can still throw exceptions. Enabling `CONCURRENT` does not make those functions exception-free. Likewise, a regular non-concurrent Collector can run correctly on a parallel stream using separate containers and a valid combiner.

## 13. Resource Lifecycle: Terminal Operations Do Not Auto-Close

`Stream` has `close()`, though many in-memory sources hold no resources. I/O sources such as `Files.lines` must be closed explicitly.

Correct pattern:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<Integer> readNumbers(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .map(Integer::parseInt)
                .collect(Collectors.toList());
    }
}
```

If a line contains `"abc"`:

1. `Files.lines` is opened in the resource declaration.
2. `map(Integer::parseInt)` throws `NumberFormatException` when iterating that line.
3. `try-with-resources` still calls `close()` on the opened Stream.
4. `NumberFormatException` can continue propagating to the caller.

Calling `collect(...)` does not automatically close the source. If you want to return a lazy Stream to a caller, you must **explicitly transfer ownership and closing responsibility** to the caller. Never return a Stream from inside a `try-with-resources` block that already closes the underlying Reader.

### Reader.lines and Reader Ownership

`BufferedReader.lines()` returns a Stream of lines, but closing that Stream **does not necessarily close the Reader** in the way you might expect. The explicit approach is to close the `BufferedReader` that owns the underlying resource:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countWarnings(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(s -> s.startsWith("WARN:"))
                .count();
    }
}
```

With custom sources created from a `Spliterator`, Java does not automatically know what socket, connection, or Reader you hold. Do not assume that successfully consuming the Spliterator means the resource has been released.

## 14. Errors in close and Suppressed Exceptions

When processing throws an error, cleanup may also fail. `try-with-resources` keeps the body's exception as the **primary exception**, and attaches resource-closing exceptions to `getSuppressed()`.

Example using `Stream.onClose` to illustrate:

```java
import java.util.stream.Stream;

try (Stream<String> source = Stream.of("A")
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {

    source.forEach(s -> {
        throw new IllegalArgumentException("processing failed");
    });

} catch (IllegalArgumentException primary) {
    System.out.println(primary.getMessage());
    // processing failed

    for (Throwable secondary : primary.getSuppressed()) {
        System.out.println(secondary.getMessage());
        // close failed
    }
}
```

The two exceptions play distinct roles:

- `IllegalArgumentException("processing failed")` is thrown from the terminal callback.
- `IllegalStateException("close failed")` is thrown when `try-with-resources` closes the Stream.
- The second exception is recorded in the **suppressed** list of the first exception, preserving the original failure context.

If the body **does not throw**, the exception from `close()` can become the error received by the caller. `onClose` can register multiple handlers; upon closing, handlers run in registration order and still attempt to run remaining handlers if one throws. Additional errors can be attached as suppressed exceptions per the contract.

**Do not write an empty catch around `close`** and pretend the pipeline succeeded. Cleanup errors can matter, especially when resources must flush/commit data. Likewise, when logging failures, retain primary, causes, and suppressed exceptions.

## 15. onClose Does Not Replace try-with-resources

`onClose` registers behavior that runs **when the Stream is closed**, not “when the terminal operation finishes”:

```java
import java.util.stream.Stream;

Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("closed"));

stream.forEach(System.out::println);
// No guarantee that "closed" is printed yet.

stream.close(); // close handler runs now
```

To guarantee the handler runs even when the terminal fails:

```java
try (Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("closed"))) {
    stream.forEach(System.out::println);
}
```

For files/Readers/network resources, wrap `try-with-resources` around the true resource owner, or around a Stream with proper close handlers. Do not rely on `forEach`, `findFirst`, `count`, `collect`, or `reduce` to close the source automatically.

### Resources with Lifecycles Outside Stream

If a database transaction or connection requires rollback/commit, closing the Stream is only one part of the resource protocol. A `RuntimeException` from a mapper does not guarantee the transaction rolls back automatically unless you manage the transaction in the calling layer. Always define ownership, commit/rollback ordering, and operation replay responsibilities clearly.

## 16. Retries Must Create a New Source and Control Idempotency

After a pipeline fails, the Stream **has been or may have been partially consumed**. Never retry by invoking a terminal operation again on the same Stream:

```java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<Integer> source = Arrays.asList(1, 2, 3).stream();

int first = source.mapToInt(Integer::intValue).sum();

// WRONG: cannot run another terminal on the same source.
int second = source.mapToInt(Integer::intValue).sum();
```

If you want to retry processing from reproducible data, use a **factory that creates a fresh Stream**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<String> values = Arrays.asList("10", "20", "30");
Supplier<Stream<String>> fresh = values::stream;

int attempt1 = fresh.get()
        .mapToInt(Integer::parseInt)
        .sum();

int attempt2 = fresh.get()
        .mapToInt(Integer::parseInt)
        .sum();

System.out.println(attempt1 == attempt2); // true
```

This example only illustrates creating a new source; **it is not a recommendation to retry every error**. A parse error on `"abc"` is a permanent data error—retrying with the same input will not help. For transient errors like I/O, define attempt limits, backoff intervals, timeouts, snapshot integrity, and whether external effects (database writes, API calls) are **idempotent**.

With `Files.lines`, each attempt must open and close a new Stream. Do not retain a partially read or closed Reader.

## 17. Null, Optional, and Exceptions Should Not Be Mixed

There are three distinct situations:

- **No valid value exists**: can be represented with `Optional.empty()`.
- **Invalid input value**: depending on business logic, return a failed `ParseResult` or throw `IllegalArgumentException`.
- **Infrastructure error while reading data**: preserve `IOException`/`UncheckedIOException` details and apply a separate recovery policy.

Example:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> firstLarge = Arrays.asList(1, 2, 3)
        .stream()
        .filter(n -> n > 100)
        .findFirst();

int fallback = firstLarge.orElse(-1);
System.out.println(fallback); // -1
```

`Optional.empty()` occurs here simply because **no number is greater than 100**, not because an I/O error happened. If a mapper before `findFirst` throws `NumberFormatException`, the error does not turn into an empty Optional.

### Avoid Returning null as an Error Signal When Possible

`map` can emit `null`, but many terminals/collectors reject null or treat it under different contracts. For example, `Collectors.toMap` does not accept null values in standard map accumulation; `findFirst` can throw `NullPointerException` if the selected element is null.

Instead of returning null whenever parsing fails and then calling `filter(Objects::nonNull)`, the `ParseResult` pattern preserves both **the cause** and **error counts**. If you truly choose to drop errors, document clearly that it is an allowed policy.

## 18. Error Messages, Logs, and Sensitive Data

Exception messages help diagnostics, yet can accidentally expose user data or file contents.

A good error message usually contains:

- The failing operation type: opening a file, reading a line, parsing, grouping, or finalizing.
- An appropriate source identifier or location (when allowed): stream name, line number, job ID.
- The original error preserved as `cause`, rather than merely formatted into a string.
- Action context: abort import, skip one record, or retry at the responsible layer.

Do not include full card numbers, passwords, access tokens, or sensitive data in exception messages. If an offending line must be logged, apply the system's truncation/masking rules and separate operational logs from data error reports.

### Attaching Line Numbers to Data Before Parsing

If you want to report errors with position without storing all elements in an external Map, you can pair the index with each read line:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<String> raw = Arrays.asList("10", "bad", "30");

List<String> report = IntStream.range(0, raw.size())
        .mapToObj(i -> {
            String text = raw.get(i);
            try {
                int value = Integer.parseInt(text);
                return "line=" + (i + 1) + ", value=" + value;
            } catch (NumberFormatException ex) {
                return "line=" + (i + 1) + ", invalid integer";
            }
        })
        .collect(Collectors.toList());

System.out.println(report);
// [line=1, value=10, line=2, invalid integer, line=3, value=30]
```

This example uses an ordered List with indexed access. For very large files, do not load all of `Files.lines` into a List just to get line numbers; design a `LineRecord` numbered in a single sequential read pass, or use an appropriate line-reading API. Do not increment a shared external `int[]` counter from multiple parallel threads.

## 19. Testing Exception Propagation

A test suite should cover both normal behavior and erroneous inputs, not just happy-path data.

| Test case | Expectation |
| --- | --- |
| Valid data | Terminal returns expected result |
| `map(Integer::parseInt)` hits invalid string | `NumberFormatException` propagates if fail-fast |
| `filter`/`anyMatch` stops before invalid element | Does not require inspecting every element |
| `toMap` hits duplicate key | Throws if no merge policy |
| File source cannot be opened | `IOException` on source creation |
| I/O error during lazy read | `UncheckedIOException` or appropriate source error |
| Mapper throws inside `try-with-resources` | Source is still closed |
| Mapper and close both throw | Primary keeps processing error; close error is suppressed |
| Parallel run with multiple bad elements | Do not assume which element fails first |
| Using `ParseResult` | Can count valid/invalid items; total record count preserved |
| Empty source | Appropriate result, no spurious errors |
| Retry | Fresh source; do not reuse old Stream |

### Example: Manually Testing Parse Error Propagation

```java
import java.util.Arrays;
import java.util.stream.Collectors;

boolean thrown = false;

try {
    Arrays.asList("1", "bad", "3")
            .stream()
            .map(Integer::parseInt)
            .collect(Collectors.toList());
} catch (NumberFormatException ex) {
    thrown = true;
}

if (!thrown) {
    throw new AssertionError("Expected NumberFormatException");
}
```

Note that this test uses terminal `collect(toList())` to force materializing elements after `map`. If replaced with `count()`, you cannot rely on every mapper invocation running.

### Example: Testing Retained Error Records

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Long> counts = Arrays.asList(
        "1", "bad", "3", null
).stream()
 .map(ParseResult::from)
 .collect(Collectors.partitioningBy(
         ParseResult::isValid,
         Collectors.counting()
 ));

if (!Long.valueOf(2L).equals(counts.get(true))
        || !Long.valueOf(2L).equals(counts.get(false))) {
    throw new AssertionError("Incorrect accepted/rejected counts");
}
```

This verifies the **classification policy** rather than just computing a single numeric result. For unrecoverable errors like a corrupted file source, do not force them into regular per-record error items if continuing would produce untrustworthy output.

## 20. Pitfalls When “Handling All Exceptions” in a Pipeline

| Pattern or assumption | Problem | Better alternative |
| --- | --- | --- |
| Wrapping only `stream.map(...)` in `try/catch` | Lambda has not executed yet | Wrap the terminal or handle inside the lambda |
| Thinking `count()` forces every `map` to run | Optimizations may skip mapper | Use an operation that consumes results needing validation |
| Catching `Exception` and returning `0` everywhere | Masks source, bug, and data errors | Classify errors with explicit policies |
| Catching `IOException` directly in `Function` without handling | Won't compile unless caught/wrapped properly | `UncheckedIOException` or Result type |
| Throwing `new RuntimeException(ex.getMessage())` | Loses original cause/stack trace | Preserve cause in the new exception |
| Using null as “parse error” and filtering all out | Cannot audit dropped errors | `ParseResult` or error counters |
| Thinking `collect` auto-closes `Files.lines` | Resource leak | `try-with-resources` |
| Thinking `BufferedReader.lines().close()` always closes Reader | Unclear resource owner | Close the Reader directly |
| Thinking `onClose` runs when `forEach` finishes | Handler only runs on close | Call close or use `try-with-resources` |
| Swallowing close exceptions | Hides cleanup failures | Keep suppressed exceptions / full logs |
| Retrying on the same consumed Stream | Stream is single-use | New source factory |
| Retrying non-idempotent write/send operations | Can create duplicate side effects | Transaction/idempotency design |
| Expecting `limit(1)` to run mapper only once in parallel | Other branches may process ahead | Do not depend on callback invocation count |
| Expecting first source-order exception in parallel | Execution schedule is non-deterministic | Do not assert a specific element's error message |
| Dumping whole bad record into exceptions/logs | May leak sensitive data | Truncate, mask unnecessary info |
| Turning every `RuntimeException` into a data error | Programming bugs may be hidden | Catch only expected errors; fail-fast on others |
| Using side effects and expecting exception rollback | Effects before failure persist | Transactions or pure data processing |

## 21. Safety Design Checklist Before Production

1. **Where is the source?** In-memory array/List, one-shot Iterator, `Files.lines`, Reader, or network source?
2. **Does opening the source throw a checked exception?** Separate open errors from lazy iteration errors.
3. **Which lambdas can throw?** `map`, `filter`, `flatMap`, classifier, comparator, accumulator?
4. **What can the terminal throw?** `toMap` duplicate keys, `reduce` overflow, empty `Optional.get`?
5. **Which errors are data errors vs. infrastructure errors?** Never use one fallback for everything.
6. **Do you need fail-fast or per-record results?** If reporting errors is needed, design `Result` and summary counters.
7. **Are elements skipped?** If so, record counts and policy so reports are not skewed.
8. **Does logic depend on callback invocation count?** `count` and short-circuiting may skip operations.
9. **Is it running in parallel?** Do not rely on error ordering or side effects; verify Collector/combiner.
10. **Is there an I/O source?** Who owns it and who is responsible for closing it?
11. **What if both processing and close fail?** Are primary, cause, and suppressed exceptions preserved?
12. **What if retrying?** Is a fresh source created, with snapshot and idempotency ensured?
13. **Do error messages leak sensitive data?** Keep only information necessary for diagnosis.
14. **Do tests cover empty sources, invalid records, terminal exceptions, and resource closing?**

## 22. Practice Exercises

### Exercise A: Catching Errors at the Right Time

Create a `Stream<Integer>` from `["10","invalid","30"]` using `map(Integer::parseInt)`. Put `try/catch` around the **pipeline declaration** and observe why no error is caught. Move `try/catch` around `collect(toList())` and explain the difference.

### Exercise B: Wrapping Checked Exceptions with Preserved Cause

Use a `List<Path>` and `Files.size`. Write a mapper catching `IOException` and throwing `UncheckedIOException`; at the call site, check that `ex.getCause()` is the original I/O error. Test with a non-existent path.

### Exercise C: From Fail-Fast to Error Reporting

Read `["10", "abc", "", "-3", null]` into `ParseResult`. Report:

```text
accepted = 2
rejected = 3
sum = 7
```

Use `partitioningBy` or `ImportSummary`. Do not lose track of total input record count when handling parse errors.

### Exercise D: Exceptions from Terminals

Call `Collectors.toMap(String::length, s -> s)` on `["cat","dog"]`. Explain the `IllegalStateException` caused by duplicate keys. Switch to `groupingBy(String::length)` to retain both elements.

### Exercise E: Exceptions on Close

Create `Stream.of("A").onClose(...)` with a close handler that throws an exception; also throw inside `forEach`. Use `try-with-resources` and confirm the processing exception is primary while the close error is in `getSuppressed()`.

### Exercise F: Parallelism and Short-Circuiting

Use a source with multiple malformed strings. Compare `findFirst`, `anyMatch`, and `collect` in both modes. State clearly which terminals **might** skip inspecting every element, and why tests must not assert which failing element is reported first in parallel mode.

### Exercise G: File Sources and Resource Lifecycle

Write a function that reads a scores file, parses each line, and computes valid/error statistics. Use `Files.lines` inside `try-with-resources`. Test empty sources, malformed lines, missing files, and large datasets; distinguish opening `IOException` from iteration `UncheckedIOException`.

## 23. Self-Check Questions

1. Why don't errors in `map` usually appear at the line where the pipeline is created? **Because intermediate operations are usually lazy and run when the terminal requests elements**.
2. Is `NumberFormatException` a checked exception? **No, it is a `RuntimeException`**.
3. Does calling `map(Integer::parseInt).count()` guarantee parsing every element? **No**, optimizations can skip the mapper if it does not affect the count.
4. What can `Files.lines(path)` throw when opening the source? **`IOException`**.
5. When reading from `Files.lines` fails midway through iteration, what exception can be thrown? **`UncheckedIOException`**.
6. What type does `UncheckedIOException.getCause()` return? **`IOException`**.
7. Does `Function.apply` let a lambda throw `IOException` directly without handling it? **No**, checked exceptions are not declared in that signature.
8. When should `UncheckedIOException` be used? **When fail-fast is needed across a functional interface while preserving the I/O cause**.
9. When should a `ParseResult`-style type be used? **When expected data errors need to be reported rather than halting the entire run**.
10. Why shouldn't you catch `Exception` and return `0`? **It can hide serious errors and corrupt results**.
11. What happens when two-argument `Collectors.toMap` encounters duplicate keys? **It throws `IllegalStateException`**.
12. Does `Optional.empty()` mean the pipeline encountered an error? **No, it may simply indicate no matching result**.
13. Does `anyMatch` returning `true` prove all records are valid? **No, it can short-circuit early**.
14. With a parallel stream, which element's exception is guaranteed to appear first? **There is no source-order guarantee**.
15. If `forEach` called an external API and then threw an exception, is the external call automatically rolled back? **No**.
16. Does `collect` automatically close `Files.lines`? **No**, `try-with-resources` is required.
17. For `BufferedReader.lines()`, which resource should be closed? **Close the BufferedReader that owns the source**.
18. Does `onClose` run when the terminal finishes or when the Stream is closed? **When closed**.
19. If both processing and close fail in `try-with-resources`, which error is primary? **The processing error; the close error is recorded in suppressed exceptions**.
20. After a terminal operation fails, should you invoke a terminal again on the same Stream? **No**, a fresh Stream must be created to retry.
21. What must be considered when retrying I/O? **Attempt count, snapshot consistency, and idempotency of side effects**.
22. Why should `cause` and suppressed exceptions be preserved? **To avoid losing the root cause and cleanup errors**.
23. When processing many records and counting errors, what should be retained? **Total input count, valid count, error count, and classification policy**.
24. Why should both sequential and parallel execution be tested? **Parallel mode has different scheduling and merging, which can expose state/combiner bugs**.

**Guiding Principle:** Exceptions in the Java Stream API must be understood by **execution timing** rather than just the line of code where they are declared. Distinguish errors when opening a source from errors during lazy iteration, remember that callbacks can propagate errors from `map`/`filter` to terminals, and avoid expecting short-circuit or parallel execution to inspect a fixed set of elements. Choose fail-fast or error-carrying results according to business requirements, **preserve causes**, never swallow infrastructure errors, and always manage resource lifecycles with `try-with-resources`. A safe pipeline not only produces correct results when everything goes smoothly, but also reports errors accurately, remains diagnosable, and prevents data loss when failures occur.
