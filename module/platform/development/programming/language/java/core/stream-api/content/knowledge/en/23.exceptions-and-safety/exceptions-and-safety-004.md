# Choosing to Fail Fast or Collect Errors Alongside Results

## 1. Should a Pipeline Stop Immediately on Error or Continue?

In the **JAVA_STREAM_API** module, pipelines built with `filter`, `map`, `reduce`, and `collect` process data declaratively across lazy stages. When an input element is invalid, there are at least two distinct strategies:

- **Fail-fast (stop on error):** reject the invalid element and fail the entire operation rather than returning a success report from incomplete data.
- **Error accumulation (collect errors alongside results):** transform each element into either a **valid value or a structured error**, then gather both valid values and errors into a single report.

Neither strategy is right for every situation. When working with financial figures that require strict reconciliation, dropping a single row can corrupt the report severely. When building a 10,000-row import tool where users want to fix multiple errors in one pass, stopping on the first bad row creates a poor experience.

Minimal CSV-like order file example:

```text
1  O-101,1200,HN
2  O-102,500,HCM
3  malformed-line
4
5  O-103,-5,HN
6  O-104,700,DN
7  O-105,100,HN
```

Convention: each line has three fields `orderId,amountCents,region`; blank lines are counted separately and skipped; IDs follow `O-` plus three digits; amounts are non-negative; region codes are 2–3 uppercase letters.

For this dataset:

| Metric | Value |
| --- | ---: |
| Total physical lines | 7 |
| Valid lines | 4 |
| Blank lines | 1 |
| Malformed/invalid lines | 2 |
| Total amount of four valid orders | 2,500 cents |
| First error line | 3 — wrong field count |
| Remaining error line | 5 — negative amount |

If you choose fail-fast, the result is an **error at line 3**, with no successful `BatchReport`. If you choose error accumulation, the result can contain four valid `Order`s, two `RowIssue`s, and counters. However, **a technically successful report does not automatically mean the data may be published or persisted**.

### Learning Objectives

After this lesson in the **Exceptions and Safety** chapter, you will be able to:

1. Distinguish predictable data errors from I/O errors, programming bugs, and external service failures.
2. Choose among fail-fast, collect-all, skip-with-count, and bounded hybrid policies.
3. Write a pure parser returning `Accepted`, `Blank`, or `Rejected`, without using `null` to hide errors.
4. Preserve accurate line numbers and design a self-verifying `BatchReport` type.
5. Write a collector that accumulates **valid values, counters, and error samples** concurrently without mutating external state outside the pipeline.
6. Understand fail-fast behavior on sequential vs. parallel streams and short-circuiting.
7. Prevent calling services or writing to databases before acceptance has been decided.
8. Test empty sources, multiple errors, sample limits, ordering, and edge cases on Java 17.

## 2. Define the Error-Classification Contract Before Writing Code

A data-processing pipeline cannot simply say “skip if there is an error.” You must define **error categories**, **severity**, **continuation rules**, and **output artifacts**.

### 2.1. Classification by Origin

| Category | Example | Handle like a normal bad row? |
| --- | --- | --- |
| **Schema error** | Missing column, bad region code, negative amount | Yes, if policy permits |
| **Spec-valid blank line** | Empty line between records | Not an error; count separately |
| **Cross-record rule error** | Two orders with same ID, total exceeds cap | Needs batch-level validation, per-row parser is insufficient |
| **I/O error** | Cannot open file, connection lost mid-read | **Do not** silently convert into a bad row |
| **Programming bug** | `NullPointerException` from bug, broken invariant | Do not catch broadly and treat as missing data |
| **External service error** | Timeout saving order, database rejection | Outside `ParseOutcome`; needs separate workflow/result |
| **Resource error** | Out of memory, task cancellation | Should not be ignored to report success |

Catching `RuntimeException` or `Exception` everywhere and converting it into an `INVALID_ROW` state is dangerous: programming bugs can be disguised as “a few bad rows.”

### 2.2. Three States per Line

```text
                  Physical line N
                         │
                         ▼
                  parse(N, raw)
                         │
              ┌──────────┼───────────┐
              ▼          ▼           ▼
           Accepted     Blank       Rejected
           Order        number      RowIssue
              │          │           │
          valid++      blank++     invalid++
          keep Order                 policy?
```

For a normally completed read pass, the invariant is:

\[
\text{totalLines}=\text{validLines}+\text{blankLines}+\text{invalidLines}.
\]

This is a stronger check than merely inspecting `orders.size()`: it prevents invalid rows from quietly vanishing through `filter`.

### 2.3. A Bad Row May Have Multiple Causes

A row like `O-ABC,-2,?` has multiple errors. There are two policies:

- **First error per row:** the parser validates in sequence and returns the first error code. This lesson uses this approach; it is predictable and streamlined.
- **All field errors in one row:** the parser accumulates a `List<FieldIssue>` for a line and returns a `Rejected` carrying multiple details; suitable for form-editing UIs.

Never casually describe a parser as “collecting all errors” if each row only keeps **the first error**. This lesson collects multiple **invalid rows** across the dataset, without claiming to gather every field error within a single row.

## 3. Policy Matrix for Halting vs. Continuing

| Policy | When an invalid row is found | Final outcome if data errors exist | Best suited when |
| --- | --- | --- | --- |
| **FAIL_FAST** | Throws error, stops sequential pipeline at first encountered failure | Returns no successful result | Strict data enforcement |
| **COLLECT_ALL** | Records one issue per bad row, continues | Report contains both valid records and all issues | Small/medium import tools needing multi-error fixes |
| **SKIP_WITH_COUNT** | Increments counter, keeps no details | Report has `invalidLines` while `issues` is empty | Best-effort telemetry, minimal storage |
| **COLLECT_BOUNDED** | Increments counter and keeps at most `k` samples | Report has exact error total and at most `k` issues | Large files where RAM must be bounded |
| **THRESHOLD** | Collects errors, then applies an allowed threshold | Technical report may be marked “do not publish” | SLA / quality-gate data ingestion |

These choices **do not replace I/O error policies**: in any mode, failing to read a file must never be interpreted as an “empty source.” A partial report caused by a read failure must use a distinct result type with bytes/lines read recorded explicitly.

### 3.1. Quick Selection Rules

Ask:

1. **Would one dropped row corrupt business meaning?** If so, prefer fail-fast or collect errors and **block persistence**.
2. **Do users need to see multiple errors at once?** If so, accumulate errors.
3. **Can the file be very large?** If so, keep full counters with bounded error samples, or stream errors to a dedicated controlled store.
4. **Are you charging payments / sending emails / writing to DB?** If so, never perform side effects in a mapper before the quality gate completes.
5. **Does policy require “all errors” or “some sample errors”?** If sampling, label it accurately.

### 3.2. Stopping Publication Differs from Stopping Parsing

An import tool can **read the entire file** to return all errors, yet **write zero orders** when `invalidLines > 0`. This is the *validate all, commit none* policy:

```text
File → Parse all rows → BatchReport
                         │
                    invalidLines > 0 ?
                      /          \
                    Yes           No
                    │              │
             Return errors     Allow DB
             (no DB write)      write
```

This differs from “drop bad rows, write valid rows.” Both can be built atop the same `BatchReport`, yet the **commit** decision must be an explicit business step.

## 4. Why `filter(Objects::nonNull)` Is Not Error Handling

Anti-pattern:

```java
List<Order> valid = rawLines.stream()
    .map(line -> parseOrNull(line))
    .filter(java.util.Objects::nonNull)
    .toList();
```

If `parseOrNull` returns null for bad rows, the result only holds surviving records. It does not tell you:

- How many rows were dropped.
- The physical position of bad rows.
- The error category.
- Whether source I/O failed before reading finished.
- Whether this data is allowed to be persisted or previewed only.

**`Optional<Order>` is also insufficient** when the domain must distinguish blank lines, schema errors, and transient failures. `Optional.empty()` only expresses “no value”; using an explicit stateful type preserves audit information.

```java
sealed interface ParseOutcome
    permits Accepted, Blank, Rejected {}

record Accepted(long lineNumber, Order value)
    implements ParseOutcome {}

record Blank(long lineNumber) implements ParseOutcome {}

record Rejected(RowIssue issue) implements ParseOutcome {}
```

Here, the records are immutable for the chosen components: `Order` should be an immutable value object; `RowIssue` holds line number and error code. You do not need to return the entire raw line if a line may contain tokens or sensitive data.

## 5. Choosing Fail-Fast When Complete Valid Data Is Required

A pure parser can return `Rejected`; a fail-fast wrapper turns that case into a **domain exception**:

```java
List<Order> accepted = java.util.stream.IntStream
    .range(0, lines.size())
    .mapToObj(i -> parse(i + 1L, lines.get(i)))
    .map(outcome -> {
        if (outcome instanceof Rejected bad) {
            throw new InvalidRowException(bad.issue());
        }
        return outcome;
    })
    .filter(Accepted.class::isInstance)
    .map(Accepted.class::cast)
    .map(Accepted::value)
    .toList();
```

This illustration uses `parse`, `lines`, and the `ParseOutcome` types defined in the complete program in section 9.

With a **sequential stream with encounter order**, evaluation stops at the first `Rejected` in traversal order: here, **line 3**. No `accepted` list is returned normally; values prior to the error stay internal to the pipeline.

### 5.1. “Fail-Fast” Is Not Rollback

If a write call is placed inside a mapper before `Rejected`:

```java
// WRONG for all-or-nothing requirements:
// lines.stream()
//     .map(parseAndSaveToDatabase)
//     .toList();
```

then an exception at line 3 **does not undo** lines 1 and 2 already written. Fail-fast only describes **halting evaluation on error**, not cross-system transactions.

### 5.2. With Parallel Streams, the “First Error” Is Not Necessarily the Lowest Line Number

`parallel()` can evaluate different segments concurrently. An error on line 50 may be observed before an error on line 3; work in other segments may already have begun before the pipeline stops.

If the error message **must report the error with the lowest line number**, clearer options are:

- Use a **sequential** pipeline on an encounter-ordered source.
- Or collect errors and **sort by line number**, picking the first error in data order.

Never use `parallelStream().findAny()` to claim you found “the first failing line” in a file.

### 5.3. A Pure Parser Error Differs from a Source Read Error

`InvalidRowException` means **a line that was read** is invalid. `IOException` on opening a file and `UncheckedIOException` during traversal must retain distinct meanings. If a reader only read two lines before an I/O failure, you cannot return `BatchReport(totalLines=2, invalidLines=0)` and claim the file is completely valid.

## 6. Collecting Errors Alongside Results: Losing Zero Lines

Instead of throwing when seeing `Rejected`, we can route all `ParseOutcome`s into **two logical streams of data**: valid values and issues.

```text
Fully read List<String>
          │
      stream/index
          │
       parse()
          │
    ┌─────┴───────────────────────┐
    ▼                             ▼
 Accepted                     Blank / Rejected
    │                             │
 List<Order>                 blankCount / invalidCount
                                  │
                         List<RowIssue> (bounded)
    └──────────┬──────────────────┘
               ▼
           BatchReport
```

The result contains **all valid records** and details of what could not become an `Order`:

```java
record BatchReport(
    long totalLines,
    long validLines,
    long blankLines,
    long invalidLines,
    List<Order> orders,
    List<RowIssue> issueSamples
) {}
```

Note: `issueSamples` holds at most `sampleLimit` errors. If the true requirement is **all errors**, set a sufficiently high limit or design a dedicated error store; never label a truncated list as “all errors.”

### 6.1. Key Report Invariants

If all input is read without unexpected exceptions:

\[
\begin{aligned}
  \text{totalLines} &= \text{validLines}+\text{blankLines}+\text{invalidLines},\\
  |\text{orders}| &= \text{validLines},\\
  |\text{issueSamples}| &\leq \min(\text{invalidLines},\text{sampleLimit}).
\end{aligned}
\]

When `sampleLimit = 0`, only counters are kept, with no error details stored. When `sampleLimit` is greater than or equal to total errors, the list contains all issues under the parser's one-issue-per-row policy.

### 6.2. Line Numbers Must Come from the Source, Not Mapper Side Effects

When the source is `List<String>`, use:

```java
java.util.stream.IntStream.range(0, lines.size())
    .mapToObj(i -> parse(i + 1L, lines.get(i)));
```

Line numbers derive from **the source index**, independent of lambda execution order. Avoid:

```java
// Error-prone with parallel streams and control semantics:
// AtomicLong counter = new AtomicLong();
// lines.parallelStream()
//     .map(line -> parse(counter.incrementAndGet(), line));
```

`AtomicLong` ensures atomic increments, yet **does not align line numbers with source positions** when multiple threads process out of order. For lazily read I/O sources, use an ordered line-numbering source/iterator or a properly designed `Spliterator`; never put that responsibility into a mapper with shared mutable state.

## 7. Collecting Both Outcomes in One Pass: A Custom Collector

A naive approach runs twice:

```java
// parse runs twice, and a consumed stream cannot be reused:
// var valid = outcomes.stream().filter(...).toList();
// var invalid = outcomes.stream().filter(...).toList();
```

If `outcomes` is an already-materialized `List`, two passes may be acceptable. However, if the source is a one-shot I/O stream or the parser is expensive, **a single collector** gathering both values and errors is cleaner.

A `Collector<ParseOutcome, Accumulator, BatchReport>` has four parts:

| Part | Role |
| --- | --- |
| `supplier` | Creates an isolated `Accumulator` for a partition |
| `accumulator` | Accepts each `Accepted`/`Blank`/`Rejected` and updates counters/lists |
| `combiner` | Merges two accumulators when the pipeline needs to |
| `finisher` | Returns `BatchReport` with collection snapshots |

Illustrative code:

```java
.collect(java.util.stream.Collector.of(
    () -> new Accumulator(sampleLimit),
    Accumulator::add,
    Accumulator::combine,
    Accumulator::finish
));
```

Mutable state **lives inside the collector**, not in static variables or an `ArrayList` outside the pipeline. The collector **does not declare `CONCURRENT`**, so the framework preserves per-container ownership during parallel evaluation.

### 7.1. Combiner and Error Sample Ordering

If you want to keep **the first N issues in encounter order** from an ordered stream, the combiner must:

1. Keep the left partial result before the right partial result.
2. Append right-side issues while the list is still below the limit.
3. Never order by thread completion time.

With `sampleLimit = 2`, if the left segment has an error at line 3 and the right segment has errors at lines 5 and 9, merging in encounter order retains **3 and 5**. Taking up to the limit from each segment and appending yields the exact overall prefix if the combiner respects order and associativity.

### 7.2. When Should You Avoid a Collector That Retains Every Result?

If there are millions of valid rows, `List<Order>` uses memory proportional to element count. Even with a bounded error list, the report may grow too large. In that case:

- Collect **counters + aggregates** without keeping every `Order` if only statistics are needed.
- Or process in chunks, writing to staging with checkpoints.
- If every error must be inspected, stream errors into a store with retention/access controls instead of buffering everything in RAM.

Never silently allocate an unbounded `List` that risks exceeding memory limits just to keep a pipeline short.

## 8. Designing an API for Error-Bearing Reports

The complete example exposes two methods:

```java
static List<Order> validateFailFast(List<String> lines);

static BatchReport collectIssues(
    List<String> lines,
    int sampleLimit
);
```

**`validateFailFast`** returns the list of validated records only if the entire source satisfies the policy. Upon encountering `Rejected`, it throws `InvalidRowException` carrying `RowIssue`. Blank lines are valid per specification and **do not create an Order**.

**`collectIssues`** does not throw for **expected data errors**. It can still throw on programming bugs or invalid inputs (such as `lines == null`), or overflow detected by `Math.addExact`. It returns:

```text
BatchReport
  totalLines:    7
  validLines:    4
  blankLines:    1
  invalidLines:  2
  orders:        [O-101, O-102, O-104, O-105]
  issueSamples:  [line 3 FIELD_COUNT, line 5 NEGATIVE_AMOUNT]
```

Here, `issueSamples` is not a full audit when `sampleLimit` is smaller than total errors. **The `invalidLines` counter is the true error count**, while the issue list provides diagnostic samples.

### 8.1. Do Not Return Partial Objects on Fail-Fast

Some code allocates `List<Order> values` outside the stream, appends in `map`/`forEach`, and then hits an error:

```java
// Anti-pattern: caller could observe a List holding only a prefix of valid rows.
// List<Order> values = new ArrayList<>();
// lines.stream().map(OrderBatchValidation::parse)
//     .forEach(o -> values.add(...));
```

In this lesson's fail-fast method, intermediate results are **internal** and never exposed if an exception occurs. This prevents returning an incomplete list labeled as “valid orders.”

### 8.2. Do Not Treat a Technical Report as Implicit Permission to Persist

A `BatchReport` can contain valid data even when `invalidLines > 0`, yet the caller must decide:

```java
BatchReport report = collectIssues(lines, 20);

if (report.invalidLines() != 0L) {
    // Return validation report to user; do not write to database yet.
} else {
    // Passed per-row validation; may still need checks for
    // duplicate IDs, credit limits, authorization, and transactions.
}
```

## 9. Complete Java 17 Program: `OrderBatchValidation`

The following code can be saved as `OrderBatchValidation.java` and run standalone on Java 17+. It has no database, framework, or external service dependencies.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collector;
import java.util.stream.IntStream;

public final class OrderBatchValidation {

    private OrderBatchValidation() {}

    public enum ErrorCode {
        FIELD_COUNT,
        INVALID_ID,
        INVALID_AMOUNT,
        NEGATIVE_AMOUNT,
        INVALID_REGION
    }

    public record Order(
        String id,
        long amountCents,
        String region
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (!id.matches("O-[0-9]{3}")) {
                throw new IllegalArgumentException("Invalid ID");
            }
            if (amountCents < 0L) {
                throw new IllegalArgumentException("Negative amount");
            }
            if (!region.matches("[A-Z]{2,3}")) {
                throw new IllegalArgumentException("Invalid region code");
            }
        }
    }

    public record RowIssue(long lineNumber, ErrorCode code) {
        public RowIssue {
            if (lineNumber < 1L) {
                throw new IllegalArgumentException("lineNumber must be >= 1");
            }
            Objects.requireNonNull(code, "code");
        }
    }

    public sealed interface ParseOutcome
        permits Accepted, Blank, Rejected {}

    public record Accepted(long lineNumber, Order order)
        implements ParseOutcome {}

    public record Blank(long lineNumber)
        implements ParseOutcome {}

    public record Rejected(RowIssue issue)
        implements ParseOutcome {}

    public static final class InvalidRowException
            extends RuntimeException {
        private final RowIssue issue;

        public InvalidRowException(RowIssue issue) {
            super("Line " + issue.lineNumber() +
                  " invalid: " + issue.code());
            this.issue = issue;
        }

        public RowIssue issue() {
            return issue;
        }
    }

    public record BatchReport(
        long totalLines,
        long validLines,
        long blankLines,
        long invalidLines,
        List<Order> orders,
        List<RowIssue> issueSamples
    ) {
        public BatchReport {
            // Take defensive collection snapshots so collector state stays private.
            orders = List.copyOf(orders);
            issueSamples = List.copyOf(issueSamples);
        }

        public boolean hasDataErrors() {
            return invalidLines > 0L;
        }

        public long acceptedTotalCents() {
            return orders.stream()
                .mapToLong(Order::amountCents)
                .reduce(0L, Math::addExact);
        }
    }

    // Pure function: same (lineNumber, raw) produces same outcome or input error.
    public static ParseOutcome parse(long lineNumber, String raw) {
        if (lineNumber < 1L) {
            throw new IllegalArgumentException(
                "lineNumber must be >= 1"
            );
        }
        Objects.requireNonNull(raw, "raw");

        if (raw.isBlank()) {
            return new Blank(lineNumber);
        }

        // -1 keeps trailing empty fields, preventing missed missing-value errors.
        String[] fields = raw.split(",", -1);
        if (fields.length != 3) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.FIELD_COUNT)
            );
        }

        String id = fields[0].strip();
        String amountText = fields[1].strip();
        String region = fields[2].strip();

        if (!id.matches("O-[0-9]{3}")) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.INVALID_ID)
            );
        }

        long amount;
        try {
            amount = Long.parseLong(amountText);
        } catch (NumberFormatException ex) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.INVALID_AMOUNT)
            );
        }

        if (amount < 0L) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.NEGATIVE_AMOUNT)
            );
        }

        if (!region.matches("[A-Z]{2,3}")) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.INVALID_REGION)
            );
        }

        return new Accepted(
            lineNumber,
            new Order(id, amount, region)
        );
    }

    // FAIL_FAST: use sequential stream only to report errors in line order.
    public static List<Order> validateFailFast(List<String> lines) {
        Objects.requireNonNull(lines, "lines");

        return IntStream.range(0, lines.size())
            .mapToObj(i -> parse(i + 1L, lines.get(i)))
            .map(outcome -> {
                if (outcome instanceof Rejected rejected) {
                    throw new InvalidRowException(rejected.issue());
                }
                return outcome;
            })
            .filter(Accepted.class::isInstance)
            .map(Accepted.class::cast)
            .map(Accepted::order)
            .toList();
    }

    private static final class Accumulator {
        final int sampleLimit;
        long totalLines;
        long validLines;
        long blankLines;
        long invalidLines;
        final List<Order> orders = new ArrayList<>();
        final List<RowIssue> issues = new ArrayList<>();

        Accumulator(int sampleLimit) {
            this.sampleLimit = sampleLimit;
        }

        void add(ParseOutcome outcome) {
            totalLines = Math.addExact(totalLines, 1L);

            if (outcome instanceof Accepted accepted) {
                validLines = Math.addExact(validLines, 1L);
                orders.add(accepted.order());
            } else if (outcome instanceof Blank) {
                blankLines = Math.addExact(blankLines, 1L);
            } else if (outcome instanceof Rejected rejected) {
                invalidLines = Math.addExact(invalidLines, 1L);
                if (issues.size() < sampleLimit) {
                    issues.add(rejected.issue());
                }
            } else {
                throw new IllegalStateException("Unknown outcome");
            }
        }

        Accumulator combine(Accumulator right) {
            totalLines = Math.addExact(totalLines, right.totalLines);
            validLines = Math.addExact(validLines, right.validLines);
            blankLines = Math.addExact(blankLines, right.blankLines);
            invalidLines = Math.addExact(invalidLines, right.invalidLines);

            // For ordered sources, append parts in encounter order.
            orders.addAll(right.orders);
            for (RowIssue issue : right.issues) {
                if (issues.size() >= sampleLimit) {
                    break;
                }
                issues.add(issue);
            }
            return this;
        }

        BatchReport finish() {
            return new BatchReport(
                totalLines,
                validLines,
                blankLines,
                invalidLines,
                orders,
                issues
            );
        }
    }

    // COLLECT_BOUNDED: full counters, bounded stored issue samples.
    public static BatchReport collectIssues(
        List<String> lines,
        int sampleLimit
    ) {
        Objects.requireNonNull(lines, "lines");
        if (sampleLimit < 0) {
            throw new IllegalArgumentException(
                "sampleLimit must be >= 0"
            );
        }

        return IntStream.range(0, lines.size())
            .mapToObj(i -> parse(i + 1L, lines.get(i)))
            .collect(Collector.of(
                () -> new Accumulator(sampleLimit),
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
            ));
    }

    public static List<String> sample() {
        return List.of(
            "O-101,1200,HN",
            "O-102,500,HCM",
            "malformed-line",
            "",
            "O-103,-5,HN",
            "O-104,700,DN",
            "O-105,100,HN"
        );
    }

    public static void main(String[] args) {
        List<String> input = sample();

        try {
            validateFailFast(input);
        } catch (InvalidRowException ex) {
            System.out.println(ex.getMessage());
            // Line 3 invalid: FIELD_COUNT
        }

        BatchReport report = collectIssues(input, 2);
        System.out.println(report.totalLines());       // 7
        System.out.println(report.validLines());       // 4
        System.out.println(report.blankLines());       // 1
        System.out.println(report.invalidLines());     // 2
        System.out.println(report.acceptedTotalCents());// 2500
        System.out.println(report.issueSamples());
        // [RowIssue[lineNumber=3, code=FIELD_COUNT],
        //  RowIssue[lineNumber=5, code=NEGATIVE_AMOUNT]]
    }
}
```

Compile and run:

```bash
javac --release 17 OrderBatchValidation.java
java OrderBatchValidation
```

### 9.1. Separation of Responsibilities Across Components

| Component | Responsibility | Business side effects? |
| --- | --- | --- |
| `parse` | Validate one line and return an outcome | No |
| `validateFailFast` | Build valid list or throw first error | No |
| `Accumulator.add` | Count outcome types and store internal data | No, mutates only internal state |
| `Accumulator.combine` | Merge two states per collector contract | No, mutates only internal state |
| `Accumulator.finish` | Produce report with unmodifiable collections | No |
| `BatchReport.acceptedTotalCents` | Sum amounts from parsed Orders | No, may throw on overflow |
| `main` | Print illustrative results | Console output only, no external transactions |

**Arithmetic note:** `long` has limits. `Math.addExact` ensures total amount additions and non-negative counters fail loudly if they exceed range. If the domain allows totals exceeding `Long.MAX_VALUE`, use `BigInteger`, rather than turning overflow into a bad-row issue.

### 9.2. Why Is `List.copyOf` Inside the `BatchReport` Record?

`Accumulator` maintains mutable `ArrayList`s to append items during collection. Returning those lists directly would let callers mutate reported data. `List.copyOf` creates **unmodifiable structural snapshots**.

In this example, `Order` and `RowIssue` are records holding only strings, numbers, and enums, so they have no mutable fields. In another domain, `List.copyOf` still **does not deep-copy** mutable elements.

### 9.3. Null Input Is Not Treated as a Malformed Row

`parse(1L, null)` intentionally throws `NullPointerException` because the `String raw` signature requires non-null input. This distinguishes:

- **A readable text line failing schema validation** → `Rejected`.
- **Caller passing data violating API preconditions** → contract violation.

If a system receives a source where null elements are legitimately possible, update the schema/policy and test explicitly; do not broadly catch `NullPointerException` and return `INVALID_AMOUNT`.

## 10. Analyzing Differences When Running the Program

### 10.1. With `validateFailFast(sample())`

Sequential execution evaluates lines in physical order:

```text
Line 1: Accepted(O-101)
Line 2: Accepted(O-102)
Line 3: Rejected(FIELD_COUNT)
          │
          └── InvalidRowException, no List<Order> returned
```

Lines 4–7 do not need to be parsed. If the only job is validation, early termination avoids extra work. Yet if the goal is **returning all issues to fix at once**, this is not the right choice.

### 10.2. With `collectIssues(sample(), 2)`

All seven lines are parsed:

```text
Line 1: Accepted → valid=1, Order O-101
Line 2: Accepted → valid=2, Order O-102
Line 3: Rejected → invalid=1, sample [FIELD_COUNT @3]
Line 4: Blank    → blank=1
Line 5: Rejected → invalid=2, sample [FIELD_COUNT @3, NEGATIVE_AMOUNT @5]
Line 6: Accepted → valid=3, Order O-104
Line 7: Accepted → valid=4, Order O-105

total=7, valid=4, blank=1, invalid=2
```

The Order list preserves encounter order. `sampleLimit=2` suffices to hold both issues. Reducing it to `1` keeps `invalidLines` at **2**, while `issueSamples` holds only the error from line 3.

### 10.3. With `collectIssues(sample(), 0)`

The result still produces:

```text
validLines=4
blankLines=1
invalidLines=2
issueSamples=[]
```

This is the **SKIP_WITH_COUNT** configuration for data errors: no issues are stored, yet the existence of two rejected rows is never hidden. Note that `orders` still holds four valid records, so **this is not an O(1)-memory streaming pipeline**.

### 10.4. With an Empty File or List

`List.<String>of()` produces a report with all counters at 0, `orders=[]`, and `issueSamples=[]`. Meanwhile, a missing or unreadable file **must not** be turned into an empty report: that is a data-source error.

## 11. Error-Collection Policies Do Not Replace Batch-Level Validation

A per-line parser only sees three fields of **one** line. It cannot catch all rules involving **multiple records**.

### 11.1. Duplicate IDs Across Two Lines

Both lines below are valid individually:

```text
O-101,1200,HN
O-101,500,HCM
```

Yet if `orderId` must be unique within a batch, you need a global check **after** obtaining the valid Order list. You can use a local `Set` in a validation helper:

```java
static List<String> duplicateIds(List<OrderBatchValidation.Order> orders) {
    java.util.Set<String> seen = new java.util.HashSet<>();
    java.util.Set<String> duplicates = new java.util.TreeSet<>();
    for (OrderBatchValidation.Order order : orders) {
        if (!seen.add(order.id())) {
            duplicates.add(order.id());
        }
    }
    return List.copyOf(duplicates);
}
```

This is **an additional check**; it does not automatically add duplicate errors to the main example's `BatchReport.issueSamples`. If you want exact **line numbers** reported at the batch level, retain `lineNumber` alongside `Order` in `Accepted` or an equivalent structure until validation finishes.

### 11.2. Totals, Batch Limits, and Cross-Field Constraints

Other errors only appear after aggregating multiple lines:

- Record count exceeding the permitted import limit.
- A customer's cumulative amount exceeding their credit limit.
- Two individually valid fields being incompatible in combination.
- `long` sum overflowing even though each order fits within range.

Do not turn a **total-sum overflow** error into “invalid row N” unless a rule identifies which row is responsible. Report it at the **batch** level or use a larger accumulator such as `BigInteger`.

### 11.3. Two-Tier Reporting

A serious system can return:

```text
ImportValidation
   ├── rowIssues: [RowIssue(...), ...]
   ├── batchIssues: [DUPLICATE_ID, TOTAL_TOO_LARGE, ...]
   ├── acceptedRows: [...]
   └── decision: ACCEPT / REJECT / PREVIEW_ONLY
```

This avoids mixing “which row failed schema validation” and “did the batch violate business rules” into one confusing exception.

## 12. Short-Circuiting, Parallel Sources, and Determinism

### 12.1. Laziness Enables Early Stop, Not Exhaustive Inspection

On a sequential source:

```java
boolean hasError = lines.stream()
    .map(raw -> parseOneWithoutLineNumber(raw))
    .anyMatch(outcome -> outcome instanceof Rejected);
```

This is a **sketch** using a helper `parseOneWithoutLineNumber`, not a method from the complete class in section 9. `anyMatch` can stop at the first error that makes the result `true`. It answers “**is there at least one error?**”, not **how many errors**, **all errors**, or valid values beyond it.

If the goal is “show all errors to fix,” `anyMatch` cannot satisfy it even when returning `true` is accurate.

### 12.2. Parallel Execution Does Not Mean Stopping Cleanly at One Line

`parallelStream` and pipelines may have multiple elements mid-evaluation when an error is discovered. Intermediate calls may already have started before one branch throws an exception.

Consequences:

- **Do not place irreversible side effects** like payments inside `map` of a fail-fast pipeline.
- Do not use a shared counter in `peek` to claim exactly N elements ran before an error.
- Do not depend on the temporal order in which exceptions surface on a parallel stream.

With properly contracted counters and collectors, parallel streams can accelerate **pure** parsing when performance benefits exist. However, if error samples must follow **line number order**, preserve encounter order or sort by `lineNumber` afterward. When reports do not require ordering, logic can be simpler while still ensuring no data is lost.

### 12.3. Why Doesn't the Collector Declare `CONCURRENT`?

In the sample program, `Accumulator` uses mutable `ArrayList`s. Misdeclaring `CONCURRENT` would let multiple threads call `add` on **the same container**, causing races.

A default **non-concurrent** collector lets the Stream framework allocate thread-local containers and merge them via `combine`, even when the source is evaluated in parallel. There is no need to force `Collections.synchronizedList` or `AtomicLong` onto every field just because a pipeline uses `parallel()`.

### 12.4. Do Not Confuse “Result Order” with “Side-Effect Order”

An ordered stream can return `List<Order>` in encounter order while partition mappers execute at arbitrary times. Thus, ordered final output **does not prove** HTTP requests inside a mapper executed in that order.

For sensitive imports, parse/validate purely first, then invoke external services through a separate coordinator if needed.

## 13. I/O Sources: Data Line Errors Are Not File Read Errors

`Files.lines(path, charset)` reads lazily, suitable for logs/CSVs, with its own resource lifecycle:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static OrderBatchValidation.BatchReport analyzeSmallFile(Path file)
        throws IOException {
    List<String> lines;
    try (Stream<String> stream =
             Files.lines(file, StandardCharsets.UTF_8)) {
        lines = stream.toList();
    }
    return OrderBatchValidation.collectIssues(lines, 100);
}
```

The snippet above targets **small/medium files** to reuse this lesson's parser:

1. `Files.lines` opens the I/O resource.
2. `toList()` consumes the stream yet **does not close** it automatically.
3. `try-with-resources` closes the stream even on exception.
4. Once reading completes and the file closes, `collectIssues` classifies every line in memory.

### 13.1. When a File Cannot Be Opened

`Files.lines` can throw `IOException` while opening the file. This is a **source error**, not a bad CSV line. Never return an empty `BatchReport` with `invalidLines=0` and report the file as valid.

### 13.2. When an I/O Error Occurs Mid-Iteration

A read error occurring **after the stream opened** can be wrapped in `UncheckedIOException`. In this example, the error propagates out of `toList()`, and `try-with-resources` still closes the source.

**Do not catch all `UncheckedIOException`s to fabricate a `RowIssue(INVALID_AMOUNT)`**; on a read failure, you do not even know what the unread line contained.

### 13.3. Very Large Files: Do Not Materialize Everything Just for Line Numbers

`Files.lines(...).toList()` loads all lines into RAM; unsuitable for files with hundreds of millions of records. Alternatives:

- Use `BufferedReader.readLine()` in a sequential loop with an explicit line counter.
- Build a `Stream<NumberedLine>` source from a reader/iterator, avoiding incrementing line numbers inside shared-state mappers.
- Collect **counts and statistics** without retaining every `Order`.
- Process chunks with staging and checkpoints, explicitly tracking partial-progress boundaries.

**Never assume** that feeding lines into a stream makes the pipeline automatically manage I/O backpressure, stored error bounds, or memory. Those policies must be engineered explicitly.

### 13.4. Schema Errors, Encoding Errors, and CSV Lines Containing Commas

This lesson's parser uses `String.split(",", -1)`, **not a full standard CSV parser**. If data contains commas inside quoted strings, escapes, embedded newlines, or a BOM, use a proper grammar/parser.

If a line has three fields yet contains malformed character encoding, the failure can occur at the **decoder layer** and cannot always be blamed on `INVALID_REGION`. Identify source, charset, and schema before choosing where to handle errors.

## 14. Data Quality Policies After Collection

Collecting errors is only useful if the caller **uses that information to make a decision**. Example:

```java
OrderBatchValidation.BatchReport report =
    OrderBatchValidation.collectIssues(lines, 20);

boolean publishable = !report.hasDataErrors();

if (!publishable) {
    // Return error report for fixing; never call repository.save yet.
} else {
    // Proceed to batch-level validation (duplicate IDs, limits...)
    // before authorizing data writes.
}
```

### 14.1. Error Thresholds Do Not Replace Critical Data Controls

For telemetry that does not require 100% completeness, up to 0.1% invalid non-blank lines might be tolerated. The rate is computed over **non-blank** lines:

\[
\text{invalidRate}
= \frac{\text{invalidLines}}{\text{validLines}+\text{invalidLines}}.
\]

If the denominator is 0, **do not automatically conclude** the error rate is 0% and the source is high quality; that case means **there is no data to evaluate**.

### 14.2. Technical Reports and Business Decisions Are Distinct Outcomes

An import system may need:

- `BatchReport`: line counts, valid records, error samples.
- `ValidationDecision`: writable, preview-only, or rejected.
- `WriteReport`: how many saved, how many remaining, any database/service errors.

Do not cram all success/failure dimensions into a single `boolean success`. Otherwise callers can easily mistake “parsed 90%” for “imported 100%.”

### 14.3. Error Limits and Warnings Must Go Together

With `sampleLimit=10`, if `invalidLines=1000`, a 10-item error list **does not show the other 990 errors**. The UI should display:

```text
Detected 1,000 invalid lines.
Showing the first 10 errors in line order.
Remaining errors are omitted from the sample list.
```

If users need to export **every single error**, provide a streaming/storage export with bounded limits and access controls; never raise `sampleLimit` to unbounded levels for huge files.

## 15. Adding Per-Line Detail Without Leaking Sensitive Data

`RowIssue` in the example carries only `lineNumber` and `ErrorCode`, enough to locate the line in the source. Some import tools also need the field name:

```java
record FieldIssue(
    long lineNumber,
    String fieldName,
    String code
) {}
```

Example:

```text
FieldIssue(5, "amountCents", "NEGATIVE_AMOUNT")
```

You do not necessarily need to return the verbatim `rawLine`, since a source line may contain emails, tokens, addresses, or payment info. If previews are allowed:

- Bound preview length and strip control characters.
- Mask/sanitize sensitive data.
- Configure retention and access permissions properly.
- Avoid exposing raw third-party exception messages in public APIs if they might leak secrets.

A `RowIssue` with a clear code and accurate line number lets UIs/CLIs show reliable feedback without exposing raw data wholesale.

## 16. JUnit 5 Tests: Results, Errors, and Limit Policies

The following tests use `OrderBatchValidation` from section 9, running on **JDK 17+** and JUnit Jupiter. They verify **content**, **line numbers**, **error codes**, and **sample-limit rules**, independent of scheduler timing or thread names.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderBatchValidationTest {

    @Test
    void failFastStopsAtFirstInvalidLine() {
        var ex = assertThrows(
            OrderBatchValidation.InvalidRowException.class,
            () -> OrderBatchValidation.validateFailFast(
                OrderBatchValidation.sample()
            )
        );

        assertEquals(3L, ex.issue().lineNumber());
        assertEquals(
            OrderBatchValidation.ErrorCode.FIELD_COUNT,
            ex.issue().code()
        );
    }

    @Test
    void failFastAllowsBlankLinesByPolicy() {
        var orders = OrderBatchValidation.validateFailFast(
            List.of(
                "O-101,1200,HN",
                "",
                "   ",
                "O-102,500,HCM"
            )
        );

        assertEquals(2, orders.size());
        assertEquals("O-101", orders.get(0).id());
        assertEquals("O-102", orders.get(1).id());
    }

    @Test
    void accumulatesValidRowsAndAllKnownIssueCodes() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(),
            10
        );

        assertEquals(7L, report.totalLines());
        assertEquals(4L, report.validLines());
        assertEquals(1L, report.blankLines());
        assertEquals(2L, report.invalidLines());
        assertEquals(4, report.orders().size());
        assertEquals(2_500L, report.acceptedTotalCents());
        assertTrue(report.hasDataErrors());

        assertEquals(
            report.totalLines(),
            report.validLines()
                + report.blankLines()
                + report.invalidLines()
        );

        assertEquals(
            new OrderBatchValidation.RowIssue(
                3L, OrderBatchValidation.ErrorCode.FIELD_COUNT
            ),
            report.issueSamples().get(0)
        );
        assertEquals(
            new OrderBatchValidation.RowIssue(
                5L, OrderBatchValidation.ErrorCode.NEGATIVE_AMOUNT
            ),
            report.issueSamples().get(1)
        );
    }

    @Test
    void limitingSamplesDoesNotLimitInvalidCount() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(),
            1
        );

        assertEquals(2L, report.invalidLines());
        assertEquals(1, report.issueSamples().size());
        assertEquals(3L, report.issueSamples().get(0).lineNumber());
        assertEquals(4L, report.validLines());
    }

    @Test
    void zeroSampleLimitGivesSkipWithCount() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(),
            0
        );

        assertTrue(report.issueSamples().isEmpty());
        assertEquals(2L, report.invalidLines());
        assertEquals(4, report.orders().size());
    }

    @Test
    void emptySourceHasNoRowsOrErrors() {
        var report = OrderBatchValidation.collectIssues(
            List.of(), 5
        );

        assertEquals(0L, report.totalLines());
        assertEquals(0L, report.validLines());
        assertEquals(0L, report.blankLines());
        assertEquals(0L, report.invalidLines());
        assertFalse(report.hasDataErrors());
        assertTrue(report.orders().isEmpty());
        assertTrue(report.issueSamples().isEmpty());
    }

    @Test
    void parsingDistinguishesBlankFromInvalid() {
        assertTrue(
            OrderBatchValidation.parse(1L, " \t ")
                instanceof OrderBatchValidation.Blank
        );
        assertTrue(
            OrderBatchValidation.parse(2L, "broken")
                instanceof OrderBatchValidation.Rejected
        );
        assertTrue(
            OrderBatchValidation.parse(3L, "O-101,0,HN")
                instanceof OrderBatchValidation.Accepted
        );
    }

    @Test
    void invalidAmountAndRegionGetSpecificCodes() {
        var amount = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(1L, "O-101,abc,HN");
        var region = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(2L, "O-101,100,?");
        var negative = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(3L, "O-101,-1,HN");

        assertEquals(
            OrderBatchValidation.ErrorCode.INVALID_AMOUNT,
            amount.issue().code()
        );
        assertEquals(
            OrderBatchValidation.ErrorCode.INVALID_REGION,
            region.issue().code()
        );
        assertEquals(
            OrderBatchValidation.ErrorCode.NEGATIVE_AMOUNT,
            negative.issue().code()
        );
    }

    @Test
    void oneRowGetsFirstFailureByValidationOrder() {
        var outcome = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(8L, "BAD,-1,?");

        assertEquals(
            OrderBatchValidation.ErrorCode.INVALID_ID,
            outcome.issue().code()
        );
        // Does not assert that the parser collected all 3 errors on the same line.
    }

    @Test
    void snapshotsCannotBeMutatedByCaller() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(), 10
        );

        assertThrows(UnsupportedOperationException.class, () ->
            report.orders().clear()
        );
        assertThrows(UnsupportedOperationException.class, () ->
            report.issueSamples().clear()
        );
    }

    @Test
    void repeatedRunsHaveIndependentResults() {
        var a = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(), 10
        );
        var b = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(), 10
        );

        assertEquals(a, b);
        assertEquals(2L, a.invalidLines());
        assertEquals(2L, b.invalidLines());
    }

    @Test
    void reportRejectsInvalidSampleLimit() {
        assertThrows(IllegalArgumentException.class, () ->
            OrderBatchValidation.collectIssues(
                OrderBatchValidation.sample(), -1
            )
        );
    }

    @Test
    void nullInputIsAContractErrorNotRowIssue() {
        assertThrows(NullPointerException.class, () ->
            OrderBatchValidation.collectIssues(null, 10)
        );
        assertThrows(NullPointerException.class, () ->
            OrderBatchValidation.parse(1L, null)
        );
        assertThrows(NullPointerException.class, () ->
            OrderBatchValidation.collectIssues(
                Arrays.asList("O-101,1,HN", null), 10
            )
        );
    }

    @Test
    void acceptedTotalDetectsOverflow() {
        var report = OrderBatchValidation.collectIssues(
            List.of(
                "O-101," + Long.MAX_VALUE + ",HN",
                "O-102,1,HN"
            ),
            10
        );

        assertEquals(2L, report.validLines());
        assertThrows(ArithmeticException.class, () ->
            report.acceptedTotalCents()
        );
    }
}
```

### 16.1. Tests Must Evaluate Meaning, Not Just Absence of Exceptions

A unit test asserting only that `collectIssues(...)` does not throw can miss serious bugs: wrong line counts undercounted, wrong line number on the first issue, or a truncated error list with no UI warning.

Assertions should check at least:

- Total-line-count invariant.
- Valid record count and total error count.
- Expected error code for each case.
- Issue order when display by line number is required.
- Sample limit vs. full counter accuracy.
- Immutability of returned collections.
- Distinction between an empty file/source and a source error.

### 16.2. Do Not Assert That Parallel Fail-Fast Always Returns the Lowest Line Number

A parallel pipeline may observe and throw an exception from another partition first. Unit tests checking **the first failing line by line number** should run sequentially or collect results and sort by `lineNumber`. Never make tests depend on scheduling and treat that as an API contract.

### 16.3. Additional Integration Tests

When moving the example to real files, test with a temporary directory:

- Valid empty file.
- Non-existent file: I/O error, not an empty report.
- File with wrong charset or complex quoted CSV lines.
- A simulated reader throwing `IOException` mid-stream.
- Very large file with small `sampleLimit` to verify bounded issue storage.
- Import skipping database writes when `invalidLines > 0` per quality gate.

These are tests **outside the illustrative JUnit code** if connecting to real I/O or repositories.

## 17. When to Use `partitioningBy`, `teeing`, or a Specialized Collector?

### 17.1. `partitioningBy` on a Materialized List of Outcomes

If you already have `List<ParseOutcome> outcomes`, you can split them quickly:

```java
Map<Boolean, List<OrderBatchValidation.ParseOutcome>> parts =
    outcomes.stream().collect(
        java.util.stream.Collectors.partitioningBy(
            outcome ->
                outcome instanceof OrderBatchValidation.Accepted
        )
    );
```

The `true` side is accepted; the `false` side contains **both Blank and Rejected**. Therefore, never conclude `parts.get(false).size()` is the error count. You still must separate Blank and Rejected afterward.

`partitioningBy` is concise for two states, yet this lesson has **three outcome types** and tracks counts/issues, making a custom collector clearer.

### 17.2. `teeing` When Two Independent Downstreams Suffice

`Collectors.teeing` (Java 12+) sends each element to two downstream collectors and combines their results. For example, from a validated stream of `Accepted` orders:

```java
record CountAndSum(long count, long sumCents) {}

CountAndSum stats = validOrders.stream().collect(
    java.util.stream.Collectors.teeing(
        java.util.stream.Collectors.counting(),
        java.util.stream.Collectors.summingLong(
            OrderBatchValidation.Order::amountCents
        ),
        CountAndSum::new
    )
);
```

This snippet uses a `validOrders` variable of type `List<OrderBatchValidation.Order>`. `teeing` fits when combining two aggregations, yet does not define three parse states, line numbers, or error sampling policies. `summingLong` does not detect overflow automatically; if overflow-checked arithmetic is needed, use an accumulator with `Math.addExact`.

### 17.3. Validation Libraries When Rules Multiply

When records have dozens of fields and require **collecting every error on the same row**, a validation library or `Validated<T>` model with `List<FieldIssue>` may express rules better than a chain of `if`s in a parser. Regardless of library, preserve the boundary:

```text
Predictable data errors     → validation issue
Infrastructure/runtime bugs → separate failure
Validated results           → eligible for side effects
```

Never let changing abstractions cause I/O failures or programming bugs to be swallowed as “empty data.”

## 18. Final Decision: Halt Immediately, Report All Errors, or Accept Partially?

Two systems can share **the exact same parser** yet make different decisions on receiving `BatchReport`.

### 18.1. Payments or Ledgers: Validate Everything, Block Writes on Error

Suppose a source contains financial transactions. One skipped entry can unbalance totals. An appropriate policy can be:

```text
Parse/validate all lines
     │
     ├─ Row issues exist?    → REJECT batch, do not call payment API.
     ├─ Batch issues exist?  → REJECT batch, do not write DB.
     └─ Zero errors?         → Build plan and execute under transaction policy.
```

Here, **collecting errors** helps users fix multiple issues at once, while **failing before writing** protects business data. These are two decisions at two boundaries, not contradictory.

### 18.2. Operational Logs: Skip-with-Count and Warn

For non-ledger logs, a small error rate may be acceptable while still reporting:

```text
valid=99.500
invalid=500
blank=20
issueSamples=10
quality=WARNING
```

The report represents **99,500 valid events**; it is not a complete description of every line. Never use the valid count to claim no lines were lost to file-reading failures.

### 18.3. Synchronous APIs: Return First Error or Multiple Errors?

A single-record import API might return the first error as:

```text
HTTP 400 / VALIDATION_ERROR
field=amountCents, code=NEGATIVE_AMOUNT
```

A batch import API might return multiple errors:

```text
validationStatus=REJECTED
totalLines=7
invalidLines=2
issues=[line 3 FIELD_COUNT, line 5 NEGATIVE_AMOUNT]
```

HTTP status codes, payloads, and maximum returned errors must follow the specific API contract. Never silently change a “first-error” endpoint into “return partial success” merely because you switched to a collector.

### 18.4. When Is Two-Pass Validation Needed?

If the system may write only after **an entire huge file** has been checked, one option is:

1. **Pass 1:** parse to count and detect errors, writing validation results to staging with no external service calls.
2. **Quality gate:** require zero errors and passing batch rules.
3. **Pass 2 / execution:** read from **an immutable validated snapshot/staging**, generate commands, and persist via a coordinator.

Never read a mutating file between passes and assume pass 1 validated pass 2's exact data. Use snapshots, checksums, versions, or appropriate source locking. If the source cannot be stabilized while requiring all-or-nothing guarantees, the design must address that risk before execution.

## 19. Common Anti-Patterns

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| `parseOrNull` then `filter(Objects::nonNull)` | Loses error counts and causes | Return explicit `ParseOutcome` |
| `catch (Exception) { return Optional.empty(); }` | Masks bugs, I/O, and service failures | Catch only expected data errors |
| `anyMatch(isInvalid)` claiming all errors collected | Short-circuiting skips remaining items | Use a collector when all issues are needed |
| Parallel fail-fast assuming lowest line number | Depends on execution order | Use sequential or sort collected issues |
| DB writes inside `map` before validation completes | Partial writes before hitting bad row | Prepare/validate first, write afterward |
| `peek(audit::save)` | Audit may not execute as expected | Write at explicit action boundary |
| Shared external `ArrayList` in `parallelStream` | Races and non-deterministic data | Collector owns local state with proper combiner |
| Declaring `CONCURRENT` on plain `ArrayList` collector | Multiple threads mutate same container | Do not declare incorrect characteristics |
| Capping at 10 issues then showing “10 errors found” | Hides true total error count | Use `invalidLines`, label “10 samples” |
| Catching `UncheckedIOException` as a schema row error | Hides incomplete file read | Report source error and partial state separately |
| Using `List.copyOf` thinking everything is deep-copied | Mutable elements can still change | Use value objects / defensive copies |
| Assuming total amount 0 means zero orders | Valid orders can have amount 0 | Track both count and sum |
| Checking duplicates in a single-row parser | Misses duplicates across rows | Batch-level validation |
| Collecting every `Order` and error of an unbounded file | Risk of out-of-memory | Chunking/staging, compact accumulators, bounded samples |
| Setting `sampleLimit` to 0 and claiming “no errors” | Confuses empty list with zero total errors | Check `invalidLines` |
| Testing only “no exception thrown” | Misses incorrect counts and policy bugs | Assert invariants, codes, and line numbers |

### 19.1. Why Name Policies Clearly?

`skipInvalidRecords`, `bestEffort`, and `tolerant` are misleading names unless they document:

- Are blank lines counted as errors?
- Are all errors kept or only samples?
- Are valid records allowed to persist when errors remain?
- Does it stop immediately on I/O errors?
- Are batch-level errors collected?

A well-designed API documents its **guarantee boundaries** instead of relying on a vague short name.

## 20. Practice Exercises

### Exercise 1 — Choosing Policies for Three Domains

Propose an error policy for:

1. Importing accounting journal entries that must balance.
2. Validating a CSV for users to edit before importing.
3. Aggregating operational logs with occasional bad lines that still need warnings.

Specify the returned report type, whether the repository may be called when `invalidLines > 0`, and why.

### Exercise 2 — Extending the Parser to Collect All Errors on One Line

Replace `Rejected(RowIssue)` with `Rejected(List<FieldIssue>)`. For `BAD,-1,?`, return at least three field issues for `id`, `amountCents`, and `region`. Keep the **`invalidLines` counter incrementing once per line**, not three times just because three field issues occurred.

### Exercise 3 — Line-Accurate Fail-Fast

Create a 100-line source with errors at line 10 and line 50. Using a sequential stream, prove `validateFailFast` reports line 10. Then experiment with a parallel version; explain why you should **never** write an assertion expecting the parallel version's exception to always be line 10.

### Exercise 4 — Limiting to 5 Error Samples

Generate 10,000 invalid lines and run `collectIssues(lines, 5)`. Test:

- `invalidLines == 10_000`.
- `issueSamples.size() == 5`.
- Line numbers of the five samples match source order.
- All other metrics remain accurate.

Explain why the memory concern for **`orders`** still exists if the file has millions of valid lines.

### Exercise 5 — Distinguishing Empty Source, Source Error, and Invalid Data

Write tests for three cases:

1. An empty yet readable file.
2. A non-existent file.
3. A readable file containing only invalid lines.

Do not let all three cases return an identical empty `BatchReport`.

### Exercise 6 — Batch-Level Duplicate IDs

Provide two valid lines with the same `orderId` and different regions. Add a post-parse duplicate check returning an appropriate `BatchIssue`. If line numbers of both records must be reported, update the intermediate structure to retain `Accepted.lineNumber`.

### Exercise 7 — Totals and Overflow

Create two valid lines: one with amount `Long.MAX_VALUE` and one with `1`. Verify `parse` accepts both, yet `acceptedTotalCents` throws `ArithmeticException`. Implement a `BigInteger` summation variant if a real system requires a larger range.

### Exercise 8 — Blocking Side Effects Before the Quality Gate

Create a fake repository tracking `save` calls. When `BatchReport.invalidLines > 0`, the coordinator **must not** call the repository. When the report is clean and passes batch validation, call the repository under an explicit policy. Test invocation counts and separate persistence errors from parser errors.

### Exercise 9 — Displaying Errors to Users

Design an API DTO containing:

```text
totalLines, validLines, blankLines, invalidLines,
issueSamples, samplesTruncated, validationDecision
```

When `invalidLines > issueSamples.size()`, require displaying “Showing N of M errors” instead of just “N errors found.”

### Exercise 10 — Using the Collector with an Unordered Source

Try using a `Set` or `unordered()` pipeline as the source. If the report needs “the first five issues,” define an **ordering criterion** (such as ascending `lineNumber`) before selecting samples. Explain why “first” is meaningless without reliable order.

### Exercise 11 — Two-Phase Validation for Large Files

Describe a two-phase validation and execution flow using staging:

- How do you guarantee data does not change between phases?
- If parsing fails, how is staging cleaned up?
- If the process crashes after validation but before execution, how do you resume?
- If execution wrote partially, what status is reported?

Never treat a single `collect` call as a distributed transaction.

### Exercise 12 — Comparing `partitioningBy` and a Custom Collector

Materialize `List<ParseOutcome>` first, then use `partitioningBy` to split accepted from the rest. Show why the remaining bucket contains **Blank + Rejected**. Compare memory cost of two passes against a single collector keeping only counters and error samples.

## 21. Design Checklist and Summary

Before shipping import or validation logic to production, verify:

- [ ] Data schema and blank-line handling are explicitly documented.
- [ ] Expected data errors have dedicated codes, without overly broad `catch (Exception)`.
- [ ] A clear choice was made between **FAIL_FAST** and **COLLECT/COUNT**.
- [ ] If collecting errors, it is explicit whether **all invalid rows** or **sample errors** are kept.
- [ ] Full `total/valid/blank/invalid` counters exist with a reconciling invariant.
- [ ] Line numbers come from source position, not parallel shared-state mappers.
- [ ] Cross-row rules such as duplicate IDs are handled.
- [ ] A quality gate sits before calling external services or writing to databases.
- [ ] I/O exceptions are never turned into bad rows or empty reports.
- [ ] Sources from `Files.lines` are closed with `try-with-resources`.
- [ ] Memory footprint of `orders`, `issues`, and file size has been evaluated.
- [ ] Logic never relies on parallel fail-fast returning the lowest line number.
- [ ] Collectors do not improperly share mutable state and have valid combiners.
- [ ] Raw lines or error messages do not leak sensitive data.
- [ ] Tests cover error cases, empty sources, truncated samples, and overflow.

| Question | Appropriate choice |
| --- | --- |
| Should one bad row abort processing immediately? | **Fail-fast** on an ordered sequential stream |
| Want users to fix multiple errors at once? | **Collect errors** and return a structured report |
| Large file needing bounded error memory? | **Count all + bounded issue samples** |
| Need every field error within a single row? | `Rejected(List<FieldIssue>)` |
| Have three states `Accepted/Blank/Rejected`? | Dedicated outcome type, not squeezed into `Optional.empty()` |
| Only need to know if any error exists? | Short-circuiting `anyMatch` may suffice, though it **cannot** list errors |
| Must preserve accurate line-number order? | Position-numbered source and ordered collector or final sort |
| Must avoid writing partial data? | Parse/validate and apply a **quality gate** before side effects |
| Need both technical stats and publish decision? | Separate `BatchReport` and `ValidationDecision` |
| Source is a very large file? | Reader/chunk/staging, not an unchecked `toList()` |
| File open/read error occurred? | Propagate I/O error, never fabricate an empty success report |

### Conclusion

**Choosing to fail fast or collect errors alongside results** is not simply switching from `throw` to `catch`. It is a decision about **the meaning of data**: when a result is considered complete, when it is preview-only, and when external side effects are permitted.

With **JAVA_STREAM_API**, keep parsers pure to map each element into a clear outcome; choose fail-fast when immediate rejection on a sequential source is required; use a collector with pipeline-owned state when gathering valid values, counters, and sample errors together. After collection, verify batch-level rules and make the persistence decision explicit. Done well, `filter`, `map`, `reduce`, and `collect` stay easy to test while never accidentally hiding errors or turning an incomplete report into false success.
