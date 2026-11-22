# Designing Success or Failure Outcomes for Each Element

> **Chapter:** Exceptions and Safety  
> **Module:** `JAVA_STREAM_API` — declarative data processing with the Java Stream API using lazy pipelines, `filter`, `map`, `reduce`, and `collect`; practicing grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while recognizing constraints around state, resources, and performance.

A pipeline processing thousands of data lines frequently encounters both **valid records** and **invalid records**. For instance, when importing order data, a line might have a non-integer quantity, a negative unit price, or a missing product SKU. If the lambda in `map` throws an unhandled exception, the terminal operation can abort with an error before we obtain a full report. Yet if you simply catch the exception and return `null` or skip the broken line, bad data disappears without a trace.

A useful design is: **each input element produces a strongly typed outcome: success or failure**. Afterward, we can collect both groups, continue aggregating the valid items, and report errors line by line. This is the *result as data* model: expected data errors are represented as values, while programming bugs or system failures continue to be handled via appropriate exception mechanisms.

This article uses **Java 17+**, with `sealed interface`, `record`, `Stream.map`, `filter`, `toList`, and `BigDecimal`. The standalone example includes tests covering valid data, multiple error kinds, empty sources, `null`, ordering, and parallel execution.

## 1. The Problem: One Broken Line Can Break the Whole Batch

Suppose an import file has each line in a simple format:

```text
SKU,quantity,unitPrice
```

Within this example's scope, data lines have **no header line**, consist of exactly three columns, and contain no commas inside a field. This is a small format for learning error handling, **not a standard CSV parser** (real CSV involves quotes, escapes, and additional rules).

Sample source:

| Line | Text | Expected outcome |
| ---: | --- | --- |
| 1 | `PEN,2,12.50` | Success; line total `25.00`. |
| 2 | `NOTE,0,9.99` | Failure: quantity must be positive. |
| 3 | `BOOK,1,80.00` | Success; line total `80.00`. |
| 4 | `PEN,abc,1.20` | Failure: quantity is not an integer. |
| 5 | `BAG,3,-10.00` | Failure: unit price is negative. |
| 6 | `BAD` | Failure: fewer than three columns. |
| 7 | `,5,4.00` | Failure: product SKU is empty. |
| 8 | `RULER,3,2.00` | Success; line total `6.00`. |

Expected business summary:

```text
Total input:     8 lines
Succeeded:       3 lines (1, 3, 8)
Failed:          5 lines (2, 4, 5, 6, 7)
Valid revenue:   111.00
```

Total revenue sums only valid lines: `25.00 + 80.00 + 6.00 = 111.00`. Invalid lines **are not lost**; they go into the error branch for data correction or display to the uploader.

### Three Approaches and Their Consequences

| Design | On a bad line | Limitation |
| --- | --- | --- |
| `map(Integer::parseInt)` letting exceptions escape | Terminal operation fails if exception is unhandled. | Hard to produce a complete report for all lines. |
| `try/catch` returning `null` / `Optional.empty()` | Pipeline can continue. | Keeping only valid values usually loses error cause and position. |
| `map(line -> parse(line))` returning `Success` or `Failure` | Every line gets an explicit outcome; processing continues. | Must design result types and explicit error-reporting policy. |

The third model fits when errors are **expected at the per-line level** and the requirement is to *collect errors rather than halt the entire batch*. It **does not mean every exception in the program should be turned into data**.

## 2. Distinguishing Expected Data Errors from Unexpected Failures

Before writing `Result`, define the **responsibility boundary**.

### Expected Errors Returnable Per Element

- Missing columns or malformed structure in an input line.
- Quantity that is not an integer, or is less than or equal to 0.
- Unit price string that cannot be parsed into a decimal number.
- Empty or invalid product SKU under business rules.
- Any explicit business condition that is not satisfied.

These situations should produce an error object with an **error code, location, and safe description**, allowing remaining lines to continue processing.

### Errors That Should Not Be Swallowed in a Broad `catch (Exception)`

- `NullPointerException` from programming bugs or an unexpected internal invariant violation.
- `OutOfMemoryError`, severe resource exhaustion, or system errors unrecoverable by dropping one line.
- Connection failures to a shared service, file permission errors, or misconfigurations preventing **every line** from being processed.
- Task cancellation, thread interruption, timeouts, or other lifecycle concerns that must reach the orchestrating layer.

For I/O-backed work, distinguish **per-request service errors** (sometimes representable as a `Failure` per contract) from **infrastructure failures** requiring retries, batch abortion, or job-level alerts. When catching `InterruptedException` in interruptible APIs, normally restore the interrupt flag via `Thread.currentThread().interrupt()` and propagate cancellation per application policy instead of silently converting it into a normal data error.

**Rule:** convert to `Failure` only errors defined in that operation's contract; never use `catch (Throwable)` to force a pipeline to keep running.

## 3. Modeling Outcomes with `sealed interface` and `record`

In Java 17, `sealed interface` restricts valid implementations. We use two variants:

```java
sealed interface RowOutcome permits Success, Failure {
    int lineNo();
}

record Success(int lineNo, Order order) implements RowOutcome {}

record Failure(
        int lineNo,
        ErrorCode code,
        String message
) implements RowOutcome {}
```

For each input element, the outcome is either **`Success` or `Failure`**, never an ambiguous value like `null`. `lineNo` appears on both variants, linking each result back to its original position.

`ErrorCode` is an enum with stable constants:

```java
enum ErrorCode {
    EMPTY_RECORD,
    WRONG_COLUMN_COUNT,
    EMPTY_SKU,
    INVALID_QUANTITY,
    NON_POSITIVE_QUANTITY,
    INVALID_PRICE,
    NEGATIVE_PRICE
}
```

Separating `code` from `message` helps:

- Test against **error codes**, avoiding brittle assertions on message wording.
- Aggregate error statistics, such as how many lines had an invalid quantity.
- Localize or reword messages without breaking logic.
- Avoid storing sensitive raw input verbatim inside messages.

This design is a **domain-specific result** for an import problem. In a reusable library, you could build a generic `Result<T, E>`, whereas in a Stream learning example, two concrete `record`s keep the presentation clearer.

### When to Choose `Optional`?

`Optional<T>` expresses **presence or absence of a value**, yet by itself gives no reason why it is absent. If business logic only asks “was a product found?”, `Optional<Product>` fits. If it needs “line 4 failed because quantity was `abc`”, a structured error type is much more useful.

```text
Optional<Order>:
  present → Order exists
  empty   → no Order, no error code

RowOutcome:
  Success → Order and line number
  Failure → line number, error code, message
```

You do not have to treat both models as mutually exclusive: a `Success` can still hold an `Optional` field if **that specific field** is genuinely optional in the domain.

## 4. Designing a Pure Parse Function: One Input, One Outcome

The `parseLine(lineNo, raw)` function is responsible for:

1. Checking for a blank or `null` line.
2. Checking for exactly three columns.
3. Reading and validating `sku`.
4. Parsing `quantity`, returning the corresponding failure if invalid or non-positive.
5. Parsing `unitPrice` with `BigDecimal`, returning a failure if invalid or negative.
6. Creating `Success` only when all conditions pass.

Diagram:

```text
Input(lineNo, raw)
          │
          ▼
      parseLine
          │
          ├── missing/bad columns ─► Failure(lineNo, code, message)
          ├── bad SKU             ─► Failure(lineNo, code, message)
          ├── bad quantity        ─► Failure(lineNo, code, message)
          ├── bad unit price      ─► Failure(lineNo, code, message)
          │
          └── valid ───────────────► Success(lineNo, Order)
```

With this design, the parse function **does not log, mutate the source list, or update external counters**. Everything needed is in its parameters and return value. Calling it from `map` in a sequential or parallel Stream does not depend on shared mutable state.

### Why Not Let `NumberFormatException` Escape?

`Integer.parseInt("abc")` and `new BigDecimal("x")` can throw `NumberFormatException`. In an import workflow, this is an **expected data error**. We catch that exact exception at the specific conversion site and return `INVALID_QUANTITY` or `INVALID_PRICE`.

```java
try {
    int quantity = Integer.parseInt(rawQuantity);
    // Use quantity after successful parse.
} catch (NumberFormatException invalid) {
    return new Failure(
            lineNo,
            ErrorCode.INVALID_QUANTITY,
            "Quantity must be an integer");
}
```

There is no need for `catch (RuntimeException)` around **the entire pipeline**: doing so risks hiding programming bugs, and a broad `catch` cannot identify which line failed without preserving input metadata.

## 5. Complete Java 17+ Program

Save the following program to `PerElementOutcomeDemo.java`. It includes immutable models, a per-line parser, a report containing both successes and failures, and self-running test cases in `main`.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

public class PerElementOutcomeDemo {

    enum ErrorCode {
        EMPTY_RECORD,
        WRONG_COLUMN_COUNT,
        EMPTY_SKU,
        INVALID_QUANTITY,
        NON_POSITIVE_QUANTITY,
        INVALID_PRICE,
        NEGATIVE_PRICE
    }

    record Order(String sku, int quantity, BigDecimal unitPrice) {
        Order {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("SKU cannot be blank");
            }
            if (quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "Quantity and unit price must be valid");
            }
        }

        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    sealed interface RowOutcome permits Success, Failure {
        int lineNo();
    }

    record Success(int lineNo, Order order) implements RowOutcome {
        Success {
            if (lineNo <= 0) {
                throw new IllegalArgumentException("Line number must be positive");
            }
            Objects.requireNonNull(order, "order");
        }
    }

    record Failure(
            int lineNo,
            ErrorCode code,
            String message
    ) implements RowOutcome {
        Failure {
            if (lineNo <= 0) {
                throw new IllegalArgumentException("Line number must be positive");
            }
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
        }
    }

    record BatchReport(
            List<RowOutcome> outcomes,
            List<Success> successes,
            List<Failure> failures,
            BigDecimal revenue
    ) {
        BatchReport {
            // Expose unmodifiable copies; never retain mutable Lists
            // that callers could mutate after building the report.
            outcomes = List.copyOf(outcomes);
            successes = List.copyOf(successes);
            failures = List.copyOf(failures);
            Objects.requireNonNull(revenue, "revenue");
        }
    }

    static RowOutcome parseLine(int lineNo, String raw) {
        if (lineNo <= 0) {
            throw new IllegalArgumentException("lineNo must be positive");
        }
        if (raw == null || raw.isBlank()) {
            return new Failure(
                    lineNo,
                    ErrorCode.EMPTY_RECORD,
                    "Input line is blank");
        }

        // -1 keeps trailing empty columns to detect missing fields.
        String[] fields = raw.split(",", -1);
        if (fields.length != 3) {
            return new Failure(
                    lineNo,
                    ErrorCode.WRONG_COLUMN_COUNT,
                    "Each line must have exactly 3 columns");
        }

        String sku = fields[0].strip();
        if (sku.isEmpty()) {
            return new Failure(
                    lineNo,
                    ErrorCode.EMPTY_SKU,
                    "Product SKU cannot be empty");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(fields[1].strip());
        } catch (NumberFormatException invalid) {
            return new Failure(
                    lineNo,
                    ErrorCode.INVALID_QUANTITY,
                    "Quantity must be an integer");
        }
        if (quantity <= 0) {
            return new Failure(
                    lineNo,
                    ErrorCode.NON_POSITIVE_QUANTITY,
                    "Quantity must be greater than 0");
        }

        final BigDecimal unitPrice;
        try {
            unitPrice = new BigDecimal(fields[2].strip());
        } catch (NumberFormatException invalid) {
            return new Failure(
                    lineNo,
                    ErrorCode.INVALID_PRICE,
                    "Unit price must be a valid decimal number");
        }
        if (unitPrice.signum() < 0) {
            return new Failure(
                    lineNo,
                    ErrorCode.NEGATIVE_PRICE,
                    "Unit price cannot be negative");
        }

        return new Success(
                lineNo,
                new Order(sku, quantity, unitPrice));
    }

    static BatchReport analyze(List<String> source, boolean parallel) {
        Objects.requireNonNull(source, "source");

        // Index i determines lineNo independently of threads.
        IntStream indices = IntStream.range(0, source.size());
        if (parallel) {
            indices = indices.parallel();
        }

        List<RowOutcome> outcomes = indices
                .mapToObj(i -> parseLine(i + 1, source.get(i)))
                .toList();

        // toList() preserves encounter order of IntStream.range.
        // From a materialized List, each stream() call creates a fresh Stream.
        List<Success> successes = outcomes.stream()
                .filter(Success.class::isInstance)
                .map(Success.class::cast)
                .toList();

        List<Failure> failures = outcomes.stream()
                .filter(Failure.class::isInstance)
                .map(Failure.class::cast)
                .toList();

        BigDecimal revenue = successes.stream()
                .map(item -> item.order().amount())
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new BatchReport(
                outcomes, successes, failures, revenue);
    }

    static List<String> sample() {
        return List.of(
                "PEN,2,12.50",
                "NOTE,0,9.99",
                "BOOK,1,80.00",
                "PEN,abc,1.20",
                "BAG,3,-10.00",
                "BAD",
                ",5,4.00",
                "RULER,3,2.00"
        );
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void checkMoney(
            BigDecimal actual, String expected, String message) {
        check(actual.compareTo(new BigDecimal(expected)) == 0,
                message + ": actual=" + actual
                        + ", expected=" + expected);
    }

    static void selfTest() {
        List<String> source = sample();
        BatchReport sequential = analyze(source, false);

        check(sequential.outcomes().size() == source.size(),
                "Lost some input lines");
        check(sequential.successes().size() == 3, "Success count");
        check(sequential.failures().size() == 5, "Failure count");
        check(sequential.successes().size()
                + sequential.failures().size() == source.size(),
                "A line did not produce exactly one outcome");
        checkMoney(sequential.revenue(), "111.00", "Total revenue");

        check(sequential.successes().stream()
                .map(Success::lineNo)
                .toList().equals(List.of(1, 3, 8)),
                "Success line numbers");
        check(sequential.failures().stream()
                .map(Failure::lineNo)
                .toList().equals(List.of(2, 4, 5, 6, 7)),
                "Failure line numbers");
        check(sequential.failures().stream()
                .map(Failure::code)
                .toList().equals(List.of(
                        ErrorCode.NON_POSITIVE_QUANTITY,
                        ErrorCode.INVALID_QUANTITY,
                        ErrorCode.NEGATIVE_PRICE,
                        ErrorCode.WRONG_COLUMN_COUNT,
                        ErrorCode.EMPTY_SKU)),
                "Error code classification");

        // Given the same data, both modes must match.
        BatchReport parallel = analyze(source, true);
        check(sequential.equals(parallel),
                "Parallel result differs from sequential");

        // Empty source yields no Success/Failure, revenue is 0.
        BatchReport empty = analyze(List.of(), true);
        check(empty.outcomes().isEmpty(), "Empty source outcomes");
        check(empty.successes().isEmpty(), "Empty source successes");
        check(empty.failures().isEmpty(), "Empty source failures");
        checkMoney(empty.revenue(), "0", "Empty source revenue");

        // One bad line produces Failure instead of losing data.
        BatchReport invalidOnly =
                analyze(List.of("A,0,1.00"), false);
        check(invalidOnly.successes().isEmpty(), "Invalid line slipped through");
        check(invalidOnly.failures().size() == 1, "Missing failure for bad line");
        checkMoney(invalidOnly.revenue(), "0", "Revenue when all fail");

        // Decimals must sum accurately with BigDecimal.
        BatchReport decimals = analyze(
                List.of("A,1,0.10", "B,1,0.20"), false);
        checkMoney(decimals.revenue(), "0.30", "Decimal addition");

        // null on a line is a data error if the contract allows it.
        RowOutcome missing = parseLine(42, null);
        check(missing instanceof Failure, "Failed to catch null");
        check(((Failure) missing).code() == ErrorCode.EMPTY_RECORD,
                "Wrong error code for null line");
        check(missing.lineNo() == 42, "Lost line number for null line");

        // Rebuild with a loop to verify mapToObj ordering.
        List<RowOutcome> expectedOrder = new ArrayList<>();
        for (int i = 0; i < source.size(); i++) {
            expectedOrder.add(parseLine(i + 1, source.get(i)));
        }
        check(sequential.outcomes().equals(expectedOrder),
                "Outcome order differs from input");

        // Lists exposed by the report cannot be mutated.
        boolean rejectedMutation = false;
        try {
            sequential.failures().clear();
        } catch (UnsupportedOperationException expected) {
            rejectedMutation = true;
        }
        check(rejectedMutation, "Failure list must be unmodifiable");
    }

    public static void main(String[] args) {
        BatchReport report = analyze(sample(), false);
        System.out.println("Input: " + report.outcomes().size());
        System.out.println("Success: " + report.successes().size());
        System.out.println("Failure: " + report.failures().size());
        System.out.println("Revenue: " + report.revenue());

        report.failures().forEach(error ->
                System.out.println("line=" + error.lineNo()
                        + ", code=" + error.code()));

        selfTest();
        System.out.println("ALL ROW OUTCOME TESTS PASS");
    }
}
```

Run on JDK 17 or later:

```text
javac PerElementOutcomeDemo.java
java PerElementOutcomeDemo
```

Expected output:

```text
Input: 8
Success: 3
Failure: 5
Revenue: 111.00
line=2, code=NON_POSITIVE_QUANTITY
line=4, code=INVALID_QUANTITY
line=5, code=NEGATIVE_PRICE
line=6, code=WRONG_COLUMN_COUNT
line=7, code=EMPTY_SKU
ALL ROW OUTCOME TESTS PASS
```

The `check(...)` helpers throw `AssertionError` on failure without relying on `-ea`. The example is provided for learners to compile and run; during authoring of this Markdown file, the code has not been executed.

## 6. Why Keep Both `Success` and `Failure`?

If you only write:

```java
List<Order> accepted = input.stream()
        .map(PerElementOutcomeDemo::parseWithoutLineNumber)
        .flatMap(Optional::stream)
        .toList();
```

this snippet is only a **sketch**: `parseWithoutLineNumber` is not defined in the complete program. It illustrates a common design that converts a record into `Optional<Order>` and uses `flatMap(Optional::stream)` to drop records without a value.

That design can fit requirements that **discard ineligible elements**. However, for data imports needing error reporting, it loses information: how many lines were dropped, where were they, and why did they fail?

With `RowOutcome`, both branches are preserved:

```text
                   List<RowOutcome>
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    List<Success>                 List<Failure>
          │                             │
     Order / amount               lineNo / code
          │                             │
          ▼                             ▼
    Valid revenue                 Import error report
```

An important invariant to test is:

```text
successCount + failureCount == inputCount
```

This holds in the example because **each line is processed once and yields exactly one `RowOutcome`**. If business rules allow *intentionally skipping* certain lines (such as headers or comments), model a `Skipped` state or filter them out before counting, rather than letting tests mask missing elements.

### What About `Collectors.partitioningBy`?

You can partition `RowOutcome` by type:

```java
import java.util.Map;
import java.util.List;
import java.util.stream.Collectors;

Map<Boolean, List<RowOutcome>> groups = report.outcomes().stream()
        .collect(Collectors.partitioningBy(
                item -> item instanceof Success));

List<RowOutcome> successBranch = groups.get(true);
List<RowOutcome> failureBranch = groups.get(false);
```

This is a convenient grouping when there are only two outcome types; `report` is the `BatchReport` variable from the program in section 5. Elements in both branches still have the common declared type `RowOutcome`, so checking or casting is needed to access fields exclusive to `Success` or `Failure`. In the complete example, `filter(Success.class::isInstance)` paired with `map(Success.class::cast)` directly yields concretely typed lists.

## 7. Ordering and Error Lines: Never Use Thread Order as Line Number

A practical question: if we use `parallelStream()`, will `lineNo` still be correct?

In the example, `lineNo` is assigned from **the source list index**:

```java
IntStream indices = IntStream.range(0, source.size());
if (parallel) {
    indices = indices.parallel();
}
List<RowOutcome> outcomes = indices
        .mapToObj(i -> parseLine(i + 1, source.get(i)))
        .toList();
```

`IntStream.range` has an encounter order. `toList()` preserves that order when the source and pipeline preserve order, even when `mapToObj` executes across different workers. Because `lineNo` comes from `i + 1`, line numbers also do not depend on scheduling order.

**Do not do this:**

```java
// Avoid: shared mutable counter during parallel execution.
// int[] counter = {0};
// source.parallelStream()
//       .map(raw -> parseLine(++counter[0], raw))
//       .toList();
```

The code above has a race condition and can assign wrong line numbers. Even if `AtomicInteger` were used to avoid races, numbers would be assigned by **when callbacks execute**, not necessarily by **source line position**. A thread-safe counter does not turn parallel scheduling into encounter order.

### What If the Source Is a Sequential File?

With an ordered file source, you can attach `lineNo` while reading and construct immutable `InputLine(lineNo, raw)` objects before parallel processing. Do not assign indices after `unordered()` or after transformations that break the stable link to the original position.

The example program uses `List<String>` to avoid I/O in the exercise. In real applications, use `try-with-resources` when reading files and handle file-reading errors **separately** from per-line parsing errors.

## 8. Per-Element Errors vs. Halting the Pipeline: A Deliberate Choice

You do not always want to collect all errors. There are at least three strategies:

| Strategy | Handling approach | Best suited when |
| --- | --- | --- |
| **Fail-fast** | Throw an exception and abort the terminal operation on an unhandled error. | Every element must be valid before continuing, or the error signals a severe violation. |
| **Collect all errors** | Each element returns `Success`/`Failure`, continuing to process remaining lines. | Batch imports, form validation, auditing, or bad-data workflows needing aggregated error reports. |
| **Skip with metrics** | Drop selected elements per policy while recording counts/reasons. | Streams with skippable records where drop rates and causes still need observability. |

With **fail-fast**, if a lambda throws in a parallel stream, other tasks may already have started or be running. Never assume that when the terminal throws, external side effects have been rolled back. This is a key reason to keep pipeline steps **pure and non-mutating on external state**.

With **collect-all**, a `Failure` recording bad data **does not mean** the batch is safe to push to production. Applications can work in two phases:

1. Parse and collect all errors for display.
2. Commit data or trigger external commands only when error rates satisfy policy or the entire batch is approved.

Thus, the per-element outcome model is an **information-gathering tool**, while the decision to accept the batch stays in the business layer.

## 9. Avoid Turning Errors into `null` or Contextless Exceptions

A common anti-pattern:

```java
List<Order> orders = rawLines.stream()
        .map(raw -> {
            try {
                return parseOrderOrThrow(raw);
            } catch (Exception ignored) {
                return null;
            }
        })
        .filter(Objects::nonNull)
        .toList();
```

This is a **sketch illustrating a design to avoid**; `parseOrderOrThrow` is not part of the sample program. There are three issues:

1. `catch (Exception)` is overly broad and can turn programming bugs or system failures into silently dropped records.
2. `null` carries no error code, position, or information to fix the data.
3. After `filter(Objects::nonNull)`, you do not know how many lines failed or why.

If you genuinely want to drop invalid data per contract, still **record the reason** before discarding or build an error-counting report. Never mutate an external `ArrayList<Failure> errors` via `errors.add(...)` inside `parallelStream().map(...)` without proper synchronization and ordering guarantees: shared mutable state causes races and non-reproducible output.

A cleaner approach is **having `map` return values and `collect`ing them**, as in the `BatchReport` example. Materializing `List<RowOutcome>` also provides a stable source to compute multiple metrics without reusing a consumed Stream.

## 10. What Information Should Structured Error Outcomes Store?

For systems with audit requirements, useful fields typically include:

| Field | Role | Safety note |
| --- | --- | --- |
| `lineNo` / `recordId` | Identifies record location. | Attached at source, not from parallel callback order. |
| `code` | Stable machine-readable error code. | Do not use full exception text as the code. |
| `message` | Helpful message for users to fix input. | Omit raw secrets or stack traces. |
| `field` (optional) | Identifies the failing field, e.g., `quantity`. | Normalize field names for aggregation. |
| `severity` (optional) | Distinguishes warnings from blocking errors. | Batch acceptance rules must define these clearly. |
| `sourceId` (optional) | Distinguishes file, batch, or input source. | Never put tokens, passwords, or credentials in IDs. |

In real applications, you may need to report **multiple errors on a single line**, not just the first one. A `Failure` can then hold an immutable `List<ValidationIssue>`. The parser must specify clearly whether it **returns the first error** or **collects all independently verifiable errors**.

The example program in section 5 intentionally returns **the first error** in validation order so output stays predictable. That does not imply only one error exists on a line.

### Protecting Sensitive Data

Do not attach the entire `raw` string to every `Failure` or log by default. An input line may contain customer names, emails, identifiers, addresses, or tokens. Consider masking values, keeping structured error codes, and defining retention lifecycles for stored error data.

When reporting errors to monitoring systems, avoid placing detailed user-data messages in high-cardinality **metrics labels**. Use stable error codes for metric dimensions and store detailed context in an appropriately secured channel.

## 11. Edge Cases to Test

| Test case | Input | Expected verification |
| --- | --- | --- |
| Valid line | `PEN,2,12.50` | `Success`, amount `25.00`. |
| Zero quantity | `NOTE,0,9.99` | `NON_POSITIVE_QUANTITY`. |
| Non-numeric quantity | `PEN,abc,1.20` | `INVALID_QUANTITY`. |
| Negative unit price | `BAG,3,-10.00` | `NEGATIVE_PRICE`. |
| Non-numeric unit price | `PEN,1,x` | `INVALID_PRICE`. |
| Missing columns | `BAD` | `WRONG_COLUMN_COUNT`. |
| Empty SKU | `,5,4.00` | `EMPTY_SKU`. |
| `null` or whitespace-only line | `null`, `"  "` | `EMPTY_RECORD`. |
| Empty source | `List.of()` | No `Success` or `Failure`; revenue is 0. |
| All lines invalid | `["A,0,1.00"]` | `0` successes, `1` failure, revenue `0`. |
| Decimal amounts | `0.10` and `0.20` | Numeric sum `0.30`. |
| Repeated SKU in source | Two valid `PEN` lines | Two `Success` items; do not auto-`distinct()` if domain counts per line. |
| Parallel mode | Same source, `parallel=true` | Same outcomes, `lineNo`, and totals as sequential. |
| Ordering | `List` source with encounter order | `outcomes` and each branch preserve source line order. |
| Mutating report | `report.failures().clear()` | Throws `UnsupportedOperationException`. |

**Every line produces exactly one outcome** is a strong invariant of this model. Tests should compare result lists in exact order, not merely assert counts. In particular, include failing cases that **actually exercise the error branches**; if sample inputs are all valid, a parser catching the wrong exception can still pass tests.

## 12. Memory Cost, Performance, and Large Datasets

The example retains three lists: `outcomes`, `successes`, and `failures`. They hold references to created outcomes and keep access and testing clear; in exchange, memory grows with input line count.

For very large datasets you can:

- Use a **custom collector** maintaining both groups and totals consistently; pay attention to `supplier`, `accumulator`, `combiner`, and associativity in parallel runs.
- Process data in **bounded batches**, writing results to storage and reporting errors per batch.
- Aggregate error counts by **error code**, rather than retaining millions of message strings if only totals are needed.
- Stop or pause reading the source when an error threshold is exceeded, while defining policy clearly and never claiming the entire file was checked if reading stopped early.

When reading from files, database cursors, or networks, a `Stream` may bind to closeable resources. Close the source per its API contract, typically with `try-with-resources`; the `Result` pattern itself does not handle resource cleanup.

### Parallel Processing Is Not Automatically Better

If each element only performs `split`, `Integer.parseInt`, and small `BigDecimal` creation, `parallelStream()` scheduling overhead can outweigh gains. If the parser performs blocking HTTP or database calls, use bounded I/O orchestration rather than defaulting to the common pool.

`BatchReport` in the example is built from immutable values, with no shared mutable `ArrayList` updated inside parallel lambdas. This is a **favorable condition for correctness**, not a promise of speedup. Measure with representative data and proper tooling before optimizing.

## 13. Extended Exercises

**Exercise 1 — Add non-numeric unit price check.** Given `"PEN,2,abc"`, call `parseLine(9, ...)`. Verify the result is a `Failure` with `lineNo = 9` and `code == INVALID_PRICE`, without throwing `NumberFormatException`.

**Exercise 2 — Count errors by code.** From `report.failures()`, build a `Map<ErrorCode, Long>` counting occurrences of each error code:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<ErrorCode, Long> errorCounts = report.failures().stream()
        .collect(Collectors.groupingBy(
                Failure::code,
                Collectors.counting()));
```

This snippet uses types and variables from the main program; the map includes only error codes **that actually appeared**, without creating zero-count entries automatically.

**Exercise 3 — Return multiple issues per line.** Change `Failure(code, message)` to `Failure(List<ValidationIssue>)` so an empty SKU and a negative price can be reported together. Analyze which checks are independent and which require a prior parse step to succeed first.

**Exercise 4 — Batch fail-fast policy.** After producing `BatchReport`, allow the persistence step only when `failures.isEmpty()`. If any error exists, return the full report while **performing no data-writing side effects**.

**Exercise 5 — Preserving order after parallel processing.** Reverse the sample data and run `analyze(reversed, true)`. Verify that the new `lineNo` values correspond to positions **in the reversed source**, not the pre-reversal indices. To preserve original file line numbers across reordering, create `InputLine(originalLineNo, raw)` **before permuting**.

**Exercise 6 — Distinguishing system errors from data errors.** Suppose the parser looks up a product catalog from an external service. Classify `SKU_NOT_FOUND`, `HTTP_TIMEOUT`, `AUTH_FAILED`, and `SERVICE_UNAVAILABLE`: which can be treated as a per-record failure, and which require retries or aborting the batch? Explain why `catch (Exception)` mapping everything to `INVALID_RECORD` loses critical information.

**Exercise 7 — Currency rules.** Add a rule requiring unit prices to have at most two decimal places, or a currency unit. Distinguish **syntax errors** from **business constraint violations** and add dedicated error codes. Do not silently round `1.999` to `2.00` when the requirement is to reject excessive precision.

**Exercise 8 — Property-based tests.** Generate many valid and invalid lines and check invariants `outcomes.size() == input.size()`, `successes.size() + failures.size() == input.size()`, and `analyze(source, false).equals(analyze(source, true))` when there is no source interference. Do not use **unseeded** random data if tests must be reproducible.

## 14. Key Takeaways

- When individual data lines can fail yet the whole batch must still be processed, model **each element as `Success` or `Failure`** instead of dropping errors with `null` or catching exceptions too broadly.
- `sealed interface` and `record` in Java 17 allow strongly typed outcomes; keep **line number, error code, and safe message** for testing and remediation.
- Convert only **expected data errors** into `Failure` values. Programming bugs, thread interruption, and infrastructure failures need separate policies; never use `catch (Throwable)` to force a pipeline onward.
- Use pure `map` to produce `RowOutcome`, then separate successes and failures via `filter` and `map`; sum valid revenue with `BigDecimal`. Avoid mutating shared lists inside parallel lambdas.
- Test the invariant **one input → one outcome**, empty sources, all-error batches, error codes, decimal arithmetic, ordering, and sequential/parallel equivalence. **Collecting errors does not mean automatically accepting the batch**.
