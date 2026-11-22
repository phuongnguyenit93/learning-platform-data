# Reviewing Projects for API Contracts, Maintainability, and Resources

A project built with the **Java Stream API** can produce right outputs on sample data yet still hide severe bugs: reusing an exhausted Stream, failing to close a file source, mutating a shared `ArrayList` in parallel, mishandling empty inputs, or altering element order unintentionally. These bugs often surface only under large datasets, exceptions, multithreaded execution, or future maintenance by someone else.

Therefore, finishing a Stream project is more than writing a `filter -> map -> collect` pipeline. It requires an **evidence-based review process** along three axes:

1. **API contracts:** what preconditions, guarantees, and limits does each operation have?
2. **Maintainability:** can readers clearly understand business intent, data types, and responsibility boundaries?
3. **Resources and operations:** are Streams, files, memory, CPU, and parallel tasks managed properly?

This advanced lesson belongs to the **Advanced Exercises and Projects** chapter of the **JAVA_STREAM_API** module. We use a payment-reporting project as a running example—from business requirements, code under review, and an improved implementation to a test plan. The issues examined connect directly to lazy pipelines, `filter`, `map`, `reduce`, `collect`, grouping, custom collectors, `Spliterator`, parallel Streams, and advanced transformations such as Stream Gatherers.

**Target outcome:** after this lesson, you can organize a code review, classify findings by risk level, propose verifiable fixes, and establish acceptance criteria before shipping a Stream feature.

## 1. How Does Project Review Differ from Re-Reading Code?

A review does not merely ask "does the code run?", it must answer at least four questions:

- **Business correctness:** for example, is the reported amount calculated strictly from eligible transactions?
- **Java contract compliance:** does the code make false assumptions about encounter order, `Optional`, empty sources, side effects, or reduction associativity?
- **Safety when data and environment shift:** will a malformed file, huge source, early termination request, or multiple threads corrupt results?
- **Ease of future change:** are parsing, aggregation, error handling, resource ownership, and presentation tangled inside one hard-to-test expression?

Distinguish **findings** from **impressions**. A valuable review comment describes:

~~~text
Symptom / risk
    ↓
Relevant code snippet or API contract
    ↓
Minimal input data to reproduce
    ↓
Proposed fix
    ↓
Confirming test
~~~

Good example:

> The pipeline calls `count()` and then `collect()` on the same Stream variable. A Stream can only be consumed once; the second call can throw `IllegalStateException`. Create a new source if the data can be re-traversed, or use a combined collector in a single terminal operation. Add a test computing both count and total amount on a single-use source.

Insufficient example:

> "This part looks a bit hard to read, maybe optimize it."

Reviews should prioritize **correctness** and **safety** before debating formatting preferences.

## 2. Project Problem: Payment Report from a Text File

Suppose the application must read lines from a UTF-8 text file. To keep focus on the Stream API, we choose a simple illustrative format using `|` as the delimiter:

~~~text
id|region|category|amountVnd|status
~~~

**Note:** the line above is a **schema description**, not an actual header line inside the file processed by the program later. Every data line must have exactly five fields; field values must not contain `|`. This is **not a general-purpose CSV parser** supporting quoting and escaping.

Sample data:

~~~text
TX01|North|Books|120000|PAID
TX02|South|Pens|50000|PENDING
TX03|North|Books|80000|PAID
TX04|South|Books|200000|PAID
TX05|North|Pens|35000|PAID
TX06|South|Books|25000|PENDING
~~~

Business requirements:

1. Only transactions with `status = PAID` count toward revenue.
2. `amountVnd` is a non-negative `long` integer; invalid lines must fail with informative errors rather than silently turning into 0.
3. The report includes **paid transaction count**, **total paid amount**, and **total amount by region**.
4. Do not rely on `Map` key iteration order.
5. Close the file-reading stream on completion or error.
6. Prevent callers from mutating the aggregated report Map.
7. Do not enable parallel execution by default: verify correctness and benchmark first.

Expected results:

| Metric | Value |
|---|---:|
| `PAID` transactions | 4 |
| Total revenue | 435,000 VND |
| `North` revenue | 235,000 VND |
| `South` revenue | 200,000 VND |
| `PENDING` transactions counted | 0 |

These requirements form the **output contract** for evaluating the code. If source data changes, tests must pinpoint which assumption no longer holds.

## 3. Java Stream API Contract Checklist

Before editing code, use a short checklist to spot risks affecting correctness.

| Topic | What to Verify | Common Mistake |
|---|---|---|
| Stream lifecycle | One Stream supports one terminal pipeline; I/O sources are closed | Calling `count()` and `collect()` on the same Stream |
| Lazy evaluation | Intermediate callbacks run only when the pipeline demands elements | Relying on `peek` for mandatory writes |
| Non-interference | Callbacks do not structurally modify the traversed source | `filter` or `map` removing elements from the source List |
| Stateless behavior | Callbacks do not depend on shared mutable state across elements | Using an external counter to assign IDs under `parallel()` |
| Ordering | Require encounter order only when business rules need it | Assuming `findAny` always picks the first or `toSet` is ordered |
| Empty data | `Optional`, identities, and collectors have explicit rules | Calling `get()` on an empty Optional |
| Equality | `distinct` uses `equals`/`hashCode`; `TreeSet` uses comparator | Dropping records when comparator checks only price |
| Reduction | Identity, associativity, and compatibility of combiner | Using subtraction or a mutable container inside `reduce` |
| Collector | Supplier creates fresh containers; combiner loses no data | Sharing one `ArrayList` in parallel |
| Resources | Streams from `Files.lines` are closed with `try-with-resources` | Terminal operation finishes yet file stays open |
| Numeric types | Control overflow and precision | Summing `long` past representational bounds |
| Parallelism | Source splits well; pipeline and collector obey contracts | Turning on `parallel()` assuming it is always faster |

A checklist works only when each item is backed by **test evidence, API reasoning, or reproducible examples**, not mere checkmarks.

## 4. Axis One: Stream Lifecycle and Source Ownership

A `Stream` is a **single-use** pipeline description. Terminal operations like `sum()`, `count()`, `findFirst()`, `reduce()`, or `collect()` end the pipeline. You cannot run a second terminal operation on the same Stream instance.

~~~java
java.util.stream.Stream<String> names =
    java.util.stream.Stream.of("An", "Bình", "Chi");

long count = names.count(); // 3

// Invalid: Stream has already been consumed.
// java.util.List<String> list = names.toList();
~~~

**Fix depends on the source:**

- For a re-traversable `List`, open two independent Streams if goals and cost permit.
- To compute multiple metrics in one pass, use `Collectors.teeing` (Java 12+) or an appropriate collector.
- For file-backed sources, never reuse the same Stream after a terminal operation; decide explicitly who closes it.

### 4.1. Terminal Operations Do Not Close I/O Streams Automatically

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("payments.txt");

try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
    System.out.println(count);
}
~~~

`try-with-resources` guarantees `close()` runs when leaving `try`, even if an exception occurs. `count()` only executes the terminal operation; it **does not promise to close the file**.

In a method **returning a Stream to its caller**, make **closing ownership** explicit. If you create an I/O source inside a method and return an already-closed Stream, the caller cannot consume it. If you return an open Stream, the caller must know to close it:

~~~java
static Stream<String> openLines(Path path)
        throws java.io.IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

// Caller owns the closing responsibility:
try (Stream<String> lines = openLines(path)) {
    // Process within this scope.
}
~~~

An alternative design is **not returning a Stream**, instead accepting `Path` in a business method and completing all work inside `try-with-resources`. That usually limits how long the file stays open and prevents resource leaks.

### 4.2. onClose Does Not Replace close

`onClose(Runnable)` only **registers a handler**. The handler runs when the Stream is closed, **not** when the terminal operation finishes.

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)
        .onClose(() -> System.out.println("Source closed"))) {
    System.out.println(lines.findFirst().orElse("Empty"));
}
~~~

You do not need `onClose` just to call `close` again on the Stream itself; it is useful when extra cleanup is needed. If multiple close handlers throw exceptions, subsequent ones may be attached as *suppressed exceptions*; inspect `Throwable.getSuppressed()` when diagnosing.

## 5. Axis One: Laziness and Side Effects

Intermediate operations like `filter` and `map` are *lazy*. They build an execution plan without traversing data when declared.

~~~java
java.util.stream.Stream<Integer> pipeline =
    java.util.stream.Stream.of(1, 2, 3)
        .filter(n -> n > 1)
        .map(n -> n * 10);

// No terminal operation yet.
// Calling toList() triggers demand for results.
java.util.List<Integer> result = pipeline.toList();
System.out.println(result); // [20, 30]
~~~

Because Java can optimize execution paths based on the source and terminal operation, **never treat intermediate callback invocation counts as guaranteed business events**.

### 5.1. Bug: Putting Mandatory Actions Inside peek

~~~java
// Never place mandatory state-update logic inside peek.
long count = java.util.stream.IntStream.range(0, 100)
    .peek(n -> auditLog(n))
    .count();
~~~

This snippet assumes an `auditLog(int)` method. With a `SIZED` source and suitable pipeline, `count()` can use the source size without visiting every element, so `auditLog` is not guaranteed to execute 100 times.

**Fix:** extract business logging into a step with an explicit contract instead of relying on `peek`. If updating state is core business logic, design transactions, error handling, retries, and ordering explicitly rather than hiding them inside a pure computation pipeline.

### 5.2. Non-Interference and Statelessness

Risky example:

~~~java
java.util.List<Integer> source =
    new java.util.ArrayList<>(java.util.List.of(1, 2, 3, 4));

// Wrong: structurally mutates the source while the Stream traverses it.
// source.stream()
//     .filter(n -> {
//         if (n == 2) source.remove(Integer.valueOf(3));
//         return n % 2 == 0;
//     })
//     .toList();
~~~

Mutating the source inside a callback can throw `ConcurrentModificationException` or yield unpredictable results. On parallel Streams, external mutable variables also introduce race conditions.

Write callbacks based purely on **their arguments** without modifying the source:

~~~java
java.util.List<Integer> even = source.stream()
    .filter(n -> n % 2 == 0)
    .toList();

System.out.println(even); // [2, 4]
~~~

## 6. Axis One: Ordering and Element Selection Criteria

Sources like `List` typically have an **encounter order**. Some terminal operations guarantee honoring that order when present; others do not.

| Operation | What to Remember |
|---|---|
| `findFirst()` | Returns the first element in encounter order if the Stream is ordered |
| `findAny()` | Returns any matching element; do not rely on it to pick the first |
| `forEach()` on parallel Stream | Makes no guarantee about action execution order |
| `forEachOrdered()` | Preserves encounter order, though may increase coordination cost |
| `sorted()` | Sorts by comparator, preserving duplicates |
| `distinct()` | Deduplicates via `equals`/`hashCode`; keeps first occurrence on ordered Streams |
| `Collectors.toSet()` | Guarantees neither Set implementation nor iteration order |
| `Collectors.groupingBy(...)` | Guarantees no default Map key order |

Example:

~~~java
java.util.List<Integer> values = java.util.List.of(9, 3, 9, 5);

System.out.println(values.stream().findFirst().orElse(-1)); // 9
System.out.println(values.stream().min(Integer::compareTo).orElse(-1)); // 3
System.out.println(values.stream().distinct().toList()); // [9, 3, 5]
~~~

**Review must clarify business intent first:** "first" differs from "minimum", and "arbitrary representative" differs from "earliest ingested record". To get deterministic outputs on ties, define an explicit **tie-breaker**.

### 6.1. Do Not Infer Ordering from One Map Printout

~~~java
java.util.Map<String, Long> amountByRegion = sales.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        Sale::region,
        java.util.stream.Collectors.summingLong(Sale::amountVnd)
    ));
~~~

This snippet illustrates a hypothetical `Sale` type and declared `sales` source. `groupingBy` makes no promise on key order in the returned Map. If a report must display ascending keys, specify `TreeMap::new` via the `groupingBy(classifier, mapFactory, downstream)` overload or sort when rendering.

## 7. Axis One: Data Types, Nulls, and Equality Contracts

A collector or terminal operation cannot guess your project's definition of "valid record" or "duplicate record".

### 7.1. Distinguish Element Equality from Business Key Duplication

`Stream.distinct()` relies on element `equals`/`hashCode`. Given a record:

~~~java
record Payment(String id, String region, long amountVnd) {}

java.util.List<Payment> rows = java.util.List.of(
    new Payment("TX01", "North", 100L),
    new Payment("TX01", "North", 200L)
);
~~~

These two records are **unequal under `equals`** because `amountVnd` differs, despite sharing ID `TX01`. Hence `rows.stream().distinct()` does **not** enforce "at most one transaction per ID".

If business rules demand unique IDs, you must decide:

- **Reject** inputs with duplicate IDs?
- **Keep the first** record?
- **Keep the latest** record by timestamp?
- **Merge** rows under a verified rule?

Each choice needs its own algorithm and tests. Calling `distinct()` does not substitute for a business decision.

### 7.2. Comparator Does Not Always Equal `equals`

When collecting into a `TreeSet`, two elements with `compare(a, b) == 0` are treated as duplicates under set ordering. If the comparator compares only amounts, two transactions with different IDs yet equal amounts could silently lose a record.

For reports that must keep all transactions, `sorted(comparator).toList()` fits better when the goal is purely sorting. When unique keys are needed, define the comparator or Map structure to match the exact key policy.

### 7.3. Handling Nulls at Input Boundaries

- `Optional.of(null)` throws `NullPointerException`, while `Optional.ofNullable(null)` returns an empty Optional.
- `findFirst` or `findAny` cannot return an Optional holding null; selecting a null element can fail.
- `Collectors.groupingBy` in standard Java rejects null classifier results.
- `Collectors.toUnmodifiableList()` and `List.copyOf(...)` reject null elements.

For pipelines reading external data, **validate and normalize** early instead of letting nulls travel deep into collectors and failing late.

## 8. Axis One: reduce and collect Need Valid Contracts

A `reduce` operation requires a valid identity and an **associative** combining function, especially when running in parallel.

~~~java
long sum = java.util.stream.LongStream.of(10L, 20L, 30L)
    .reduce(0L, Long::sum);

System.out.println(sum); // 60
~~~

`0L` is the additive identity. Subtraction is non-associative, so never write `reduce(0, (a, b) -> a - b)` and expect consistent results under parallel execution.

### 8.1. Mistake: Mutating a Container Inside reduce

~~~java
java.util.List<String> names = java.util.List.of("An", "Bình");

// Violates value-reduction contract, especially in parallel.
// java.util.List<String> result = names.parallelStream().reduce(
//     new java.util.ArrayList<String>(),
//     (list, name) -> { list.add(name); return list; },
//     (left, right) -> { left.addAll(right); return left; }
// );
~~~

`reduce` must not be used this way to mutate a mutable identity that may be shared or reused across branches. When collecting elements into a list, use `collect`:

~~~java
java.util.List<String> result = names.parallelStream()
    .collect(java.util.stream.Collectors.toList());
~~~

Containers and combiners are managed by the collector under contract. This differs from updating a shared `ArrayList` via `parallelStream().forEach(shared::add)`, which is unsafe.

### 8.2. Custom Collectors Need Valid supplier, accumulator, and combiner

When reviewing `Collector.of(...)`, ask:

1. Does the supplier return a brand-new container on every call?
2. Does the accumulator mutate **only the provided container** without touching external state?
3. Does the combiner merge all data from both containers without dropping or double-counting?
4. Does the finisher return the expected type without leaking a mutable container when immutability is required?
5. Are `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH` flags actually true?

**Never declare `CONCURRENT` just because `parallel()` is used.** An ordinary collector can already run in parallel using separate containers and a combiner. Allowing multiple threads to mutate **the same container** requires genuinely concurrent data structures and accumulator logic.

### 8.3. Arithmetic Pitfalls in Reports

`Collectors.summingLong(...)` and `LongSummaryStatistics` use ordinary `long` arithmetic, which can **overflow**. Switching from `int` to `long` does not grant infinite precision.

If policy requires **failing on overflow**:

~~~java
java.util.stream.Collector<Payment, ?, Long> exactTotal =
    java.util.stream.Collectors.reducing(
        0L,
        Payment::amountVnd,
        Math::addExact
    );
~~~

This snippet assumes a `Payment` type with an `amountVnd()` accessor. `Math.addExact` throws `ArithmeticException` on overflow so processing halts instead of returning a corrupted total.

If real totals may exceed `long` by design, represent them with `BigInteger` or `BigDecimal` and explicit arithmetic rules.

## 9. Axis Two: Separating Responsibilities for Maintainable Code

A long Stream expression is not automatically "clean code". Mixing **input parsing**, **business rules**, **aggregation**, **display formatting**, and **logging** inside one chain of lambdas makes it hard for maintainers to tell which change affects which output.

Review-friendly designs usually separate stages:

~~~mermaid
flowchart LR
    A["Source: Files.lines / List"] --> B["parseLine: text → Payment"]
    B --> C["Select valid and PAID records"]
    C --> D["summarize: collect → Report"]
    D --> E["Display / API response"]
~~~

In small projects, you do not need many class layers or frameworks. The goal is separating **independently changeable policies** into clearly named functions.

### 9.1. Choose Names That Express Business Intent

Compare:

~~~java
// Hard to read in isolation during review:
.filter(x -> x.paid())
.map(x -> x.amountVnd())

// Clearer intent:
.filter(Payment::paid)
.mapToLong(Payment::amountVnd)
~~~

Names like `paid` and `amountVnd` let reviewers recognize conditions and units immediately. For multi-branch logic, extract helper methods such as `parseLine`, `isBillable`, or `summarizePayments` rather than stuffing everything into one lambda.

### 9.2. Separate Computation from I/O

A method accepting `Stream<String>` can focus purely on **turning data into a report**, while the caller owns the Stream and underlying resource:

~~~java
static Report summarize(Stream<String> lines) {
    // Parse and aggregate; do not close the caller's source.
}
~~~

This makes unit testing with `List.of(...).stream()` trivial without creating real files. An outer `main` or service method uses `try-with-resources` when opening `Files.lines`.

**Ownership contracts must be explicit:** whoever opens an I/O Stream ensures it is closed, or documents transferring closing responsibility to the caller. Never let a Stream float across layers with no clear owner.

## 10. Axis Two: Choose APIs by Fit, Not Brevity

| Need | Option to Consider | What Reviewers Check |
|---|---|---|
| Sum one primitive field | `mapToLong(...).sum()` | Overflow and units |
| Find first element | `findFirst()` | Does encounter order exist? |
| Find any element | `findAny()` | Is order truly irrelevant? |
| Min/max | `min(comparator)`, `max(comparator)` | Tie-breakers, empty Optional |
| Build a list | `collect(toList())` or `toList()` | Needs mutability? Target Java version? |
| Count, sum, min, max together | `summarizingLong(...)` | Empty-source and overflow policies covered? |
| Group by key | `groupingBy(...)` | Null keys, Map order, key cardinality |
| Multi-level grouping | `groupingBy(..., groupingBy(...))` | Does Map nesting hurt readability? |
| Merge two results | `teeing(...)` (Java 12+) | Merger receives final results, not elements |
| Sorted unique set | `toCollection(TreeSet::new)` | Could comparator drop distinct records? |
| Immutable collection | `Collectors.toUnmodifiableList()` or `Stream.toList()` | Null-handling and API differences |
| Custom source | `Spliterator` and `StreamSupport` | Splitting, ordering, sizing, and lifecycle |

Writing fewer lines does not guarantee easier maintenance. Four levels of nested `groupingBy` may be shorter than a named report class, yet much harder to understand and inspect for nulls. Weigh **clarity and testability** alongside code length.

### 10.1. Distinguish Mutability and Identity

- `Stream.toList()` (Java 16+) returns an unmodifiable list.
- `Collectors.toList()` **makes no guarantees** on concrete class, mutability, or thread-safety of the returned list.
- `Collectors.toCollection(ArrayList::new)` returns the exact requested mutable collection type.
- `List.copyOf(...)` returns an unmodifiable list and rejects null elements.

If results must be immutable, state it in the API and return type; never assume a `record` holding a `List` automatically makes that List unmodifiable.

## 11. Axis Three: Resources, Errors, and Data Limits

### 11.1. Memory and Terminal Operation Kind

A Stream may read elements lazily, yet a terminal operation can still **load the entire dataset into memory**.

~~~java
// Can hold all lines of the file in memory.
java.util.List<String> allLines;
try (java.util.stream.Stream<String> lines =
         java.nio.file.Files.lines(path)) {
    allLines = lines.toList();
}
~~~

If you only need counts or sums over a handful of keys, `counting`/`summingLong`/`groupingBy` with summary downstreams avoid storing every line in a List. Still, `groupingBy` retains state per key; if unique keys approach record count, the resulting Map can grow very large.

### 11.2. Unbounded Sources and Short-Circuiting

`Stream.generate(...)` or `Stream.iterate(...)` can produce infinite streams. `collect(toList())` or `sorted()` on an unbounded source cannot finish without an appropriate limit.

~~~java
java.util.List<Integer> firstFive = java.util.stream.Stream
    .iterate(1, n -> n + 1)
    .limit(5)
    .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
~~~

Operation order matters: `sorted().limit(5)` may try to sort the entire source before emitting, which fails on infinite sources.

### 11.3. Blocking I/O Limits and Mid-Pipeline Errors

With `Files.lines`, file-open errors throw `IOException`; read errors mid-traversal can surface as `UncheckedIOException`. Never catch a broad `RuntimeException` and turn every failure into an empty report. Doing so hides data loss behind a normal-looking dashboard.

In financial reporting, **contextual fail-fast** is usually preferable to silently skipping invalid lines, unless product specs explicitly require reporting both valid and rejected data.

### 11.4. Data Scale and Operational Limits

Review should ask:

- Could a huge file exhaust the heap?
- Could the parser allocate excessive temporary strings or objects?
- Can group key count grow unboundedly?
- Should there be caps on file size, line count, or malformed input count?
- Do mid-pipeline errors close resources and leave the system in a clean state?
- Do error logs accidentally expose full user payloads or sensitive data?

There is no one-size-fits-all limit: resource bounds must match the runtime environment and product requirements.

## 12. Reference Program: Read, Validate, and Aggregate in One Pipeline

This is a compact yet **self-contained** implementation prioritizing contract compliance and maintainability. It uses **Java 17+** for `record`, `switch` expressions, and `List.of`; `Collectors.teeing` arrived in Java 12.

Save the code in `ProjectStreamReviewDemo.java`. Pass no arguments to run the sample data; pass a file path to read a real UTF-8 file.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ProjectStreamReviewDemo {

    record Payment(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    record Report(
        long paidCount,
        long paidTotalVnd,
        Map<String, Long> paidRevenueByRegion
    ) {}

    private static List<String> sampleRows() {
        return List.of(
            "TX01|North|Books|120000|PAID",
            "TX02|South|Pens|50000|PENDING",
            "TX03|North|Books|80000|PAID",
            "TX04|South|Books|200000|PAID",
            "TX05|North|Pens|35000|PAID",
            "TX06|South|Books|25000|PENDING"
        );
    }

    static Payment parseLine(String line) {
        if (line == null) {
            throw new IllegalArgumentException("Data line is null");
        }

        String[] fields = line.split("\\|", -1);
        if (fields.length != 5) {
            throw new IllegalArgumentException(
                "Expected exactly 5 fields: " + line
            );
        }

        String id = fields[0].trim();
        String region = fields[1].trim();
        String category = fields[2].trim();
        String amountText = fields[3].trim();
        String status = fields[4].trim();

        if (id.isEmpty() || region.isEmpty() || category.isEmpty()) {
            throw new IllegalArgumentException(
                "Missing id, region, or category: " + line
            );
        }

        long amount;
        try {
            amount = Long.parseLong(amountText);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "Invalid amount in line: " + line, ex
            );
        }

        if (amount < 0L) {
            throw new IllegalArgumentException(
                "Amount must not be negative: " + line
            );
        }

        boolean paid = switch (status) {
            case "PAID" -> true;
            case "PENDING" -> false;
            default -> throw new IllegalArgumentException(
                "Invalid status: " + status
            );
        };

        return new Payment(id, region, category, amount, paid);
    }

    // Does not close the Stream itself: caller owns source lifecycle.
    static Report summarize(Stream<String> lines) {
        return lines
            .map(ProjectStreamReviewDemo::parseLine)
            .filter(Payment::paid)
            .collect(Collectors.teeing(
                Collectors.summarizingLong(Payment::amountVnd),
                Collectors.groupingBy(
                    Payment::region,
                    Collectors.summingLong(Payment::amountVnd)
                ),
                (stats, byRegion) -> new Report(
                    stats.getCount(),
                    stats.getSum(),
                    Map.copyOf(byRegion)
                )
            ));
    }

    public static void main(String[] args) throws IOException {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                "Usage: java ProjectStreamReviewDemo [file]"
            );
        }

        Stream<String> source = args.length == 0
            ? sampleRows().stream()
            : Files.lines(Path.of(args[0]), StandardCharsets.UTF_8);

        Report report;

        // With Files.lines, this closes the source even if parsing fails.
        try (Stream<String> lines = source) {
            report = summarize(lines);
        }

        System.out.println("paidCount=" + report.paidCount());
        System.out.println("paidTotalVnd=" + report.paidTotalVnd());
        System.out.println(
            "North=" + report.paidRevenueByRegion().get("North")
        );
        System.out.println(
            "South=" + report.paidRevenueByRegion().get("South")
        );
    }
}
~~~

Output when run with no arguments:

~~~text
paidCount=4
paidTotalVnd=435000
North=235000
South=200000
~~~

### 12.1. Why Is This Design Easier to Review?

**Single source, single terminal operation.** `summarize` accepts a Stream and uses `teeing` to compute overall stats and per-region revenue together. Two terminal operations are never called on one Stream.

**Independent parser.** `parseLine` validates syntax and field values. Unit tests can exercise bad inputs directly without creating files.

**Explicit business policy.** `filter(Payment::paid)` states clearly that only paid transactions count.

**Unmodifiable report Map.** `Map.copyOf(byRegion)` produces an unmodifiable Map; `String` keys and `Long` values are immutable. It promises no key order, and the code relies on none.

**Outer-layer file ownership.** `main` uses `try-with-resources`; `summarize` never arbitrarily closes the caller's Stream. When parsing or collecting fails, the `try` block still closes the source.

**No shared mutable state.** `teeing` and `groupingBy` manage containers per collector contract; no external `ArrayList`/`HashMap` is mutated by lambdas.

### 12.2. Known Limits, Explicitly Acknowledged

This example **does not claim to be a complete financial system**:

- The `|` format does not support escaping or delimiters inside fields. If real input is CSV, use a compliant CSV parser.
- There is no **duplicate transaction ID** check. If IDs are business-unique, dedicated detection and handling rules are needed.
- `summingLong` and `LongSummaryStatistics` can **overflow `long`** on massive sums.
- Every new region name becomes a Map key, so high-cardinality inputs can consume substantial memory.
- Parse exceptions currently embed the entire input line; with personal or sensitive data, replace raw lines with safe diagnostic fields.
- Parallelism is intentionally **disabled** because of I/O backing and because parallel correctness/performance have not been benchmarked.

Recognizing boundaries is part of a thorough review: avoid turning unproven assumptions into implicit API promises.

## 13. Testing: From "Sample Passes" to Contract Verification

Tests should cover **sample outputs, empty sources, invalid inputs, boundary cases, and resource lifecycle**.

### 13.1. Minimal Dependency-Free Test Suite

You can place this method **inside** `ProjectStreamReviewDemo` and invoke it from `main` for self-testing. It demonstrates pure-Java verification without fully replacing JUnit or a CI suite.

~~~java
static void verifyContract() {
    Report expected = summarize(Stream.of(
        "TX01|North|Books|120000|PAID",
        "TX02|South|Pens|50000|PENDING",
        "TX03|North|Books|80000|PAID"
    ));

    if (expected.paidCount() != 2L
            || expected.paidTotalVnd() != 200_000L
            || !Long.valueOf(200_000L).equals(
                expected.paidRevenueByRegion().get("North")
            )) {
        throw new AssertionError("Incorrect aggregation result");
    }

    Report empty = summarize(Stream.empty());
    if (empty.paidCount() != 0L
            || empty.paidTotalVnd() != 0L
            || !empty.paidRevenueByRegion().isEmpty()) {
        throw new AssertionError("Incorrect empty source handling");
    }

    boolean rejectedNegative = false;
    try {
        parseLine("TX09|North|Books|-1|PAID");
    } catch (IllegalArgumentException ex) {
        rejectedNegative = true;
    }

    if (!rejectedNegative) {
        throw new AssertionError("Negative amount was not rejected");
    }

    boolean immutableMap = false;
    try {
        empty.paidRevenueByRegion().put("Other", 1L);
    } catch (UnsupportedOperationException ex) {
        immutableMap = true;
    }

    if (!immutableMap) {
        throw new AssertionError("Result Map must be unmodifiable");
    }
}
~~~

**Do not rely solely on Java's `assert` keyword** unless runtime flags are controlled: `assert` statements are disabled by default without `-ea`. Throwing `AssertionError` directly ensures the checks always execute.

### 13.2. Test Case Matrix

| Case | Input | Expected Outcome |
|---|---|---|
| Empty stream | No lines | Count 0, total 0, empty Map |
| Single PAID transaction | One valid line | Count 1, revenue equals amount |
| All PENDING | Several valid unpaid lines | Count 0, total 0, empty Map |
| Negative number | `-1` | Rejected with contextual exception |
| Non-numeric amount | `abc` | Rejected, preserving parse cause |
| Missing field | Only 4 fields | Rejected |
| Extra field | 6 fields | Rejected |
| Unknown status | `DONE` | Rejected |
| Blank region key | `region = ""` | Rejected |
| Two regions | North and South | Both keys in Map, accurate per-key sums |
| Duplicate transaction IDs | Two lines with identical ID | **Undefined** in example; requires business policy |
| Total exceeding `long` | Valid huge numbers | Define requirement: fail or switch numeric type |
| Mid-stream I/O error | File stream fails | Propagate error and close resource |
| Multithreaded run | Parallel if permitted | Equivalent result and race-free |

A reviewer must never mark **PASS** for cases marked "undefined" or "requires business policy" before a decision is made. Those are **open questions**, not bugs to resolve by guessing.

## 14. Exercise: Reviewing Buggy Code

Read the snippet below and find as many issues as possible. This is **deliberately flawed code**, not recommended usage:

~~~java
// Example for code review; do not use in production.
static List<String> broken(Path path) throws IOException {
    Stream<String> lines = Files.lines(path);

    long count = lines.count();

    List<String> result = new ArrayList<>();
    lines.parallel()
        .filter(line -> !line.isEmpty())
        .forEach(result::add);

    System.out.println("rows=" + count);
    return result;
}
~~~

This snippet assumes imports for `Path`, `Files`, `IOException`, `Stream`, `List`, and `ArrayList`.

### 14.1. Findings Expected in Review

| Issue | Severity | Explanation |
|---|---|---|
| Reusing `lines` after `count()` | Blocker | Stream already terminated; second pipeline is illegal |
| Missing `try-with-resources` | Blocker | Leaks file descriptor/handle |
| `parallel().forEach(result::add)` | Blocker | Shared `ArrayList` is not thread-safe |
| `Files.lines(path)` omits charset | Depends on data spec | Explicitly specify charset per file contract |
| Checking `!line.isEmpty()` | Worth reviewing | Whitespace-only strings count as non-empty |
| Printing directly inside processing method | Maintainability | Mixes logging/console output into logic |
| Unspecified mutable return list | API design | Caller may mutate list unless contract forbids it |
| Running parallel on an I/O source | Performance | No evidence source splits well or gains speed |

### 14.2. Simple Sequential Fix with Clear Ownership

~~~java
static List<String> readNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> !line.trim().isEmpty())
            .toList();
    }
}
~~~

This uses Java 16+ `Stream.toList()`. It returns an **unmodifiable** list, releases the file resource via `try-with-resources`, and uses no shared mutable state. If the dataset is huge, returning an entire `List` remains an API-design concern; this fix addresses bugs within the scope of **reading all non-blank lines into a list**.

There is no automatic reason to add `parallel()`: file reading and list collection must be measured and checked against ordering and resource constraints before switching modes.

## 15. Reviewing Custom Sources and Parallel Processing

If a project includes a custom `Spliterator`, apply a dedicated checklist.

### 15.1. `trySplit` and `estimateSize` Contracts

| Component | Review Question |
|---|---|
| `tryAdvance(action)` | Emits exactly one element when returning `true`, and `false` when exhausted? |
| `trySplit()` | Are the two partitions **disjoint** with no dropped elements? |
| `ORDERED` | Is the returned Spliterator genuinely a **prefix** of the remaining range? |
| `estimateSize()` | Does it reflect **remaining** elements after traversal/splitting? |
| `SIZED` | Is the count exact per source contract? |
| `SUBSIZED` | Do all child Spliterators continue reporting exact sizes? |
| `IMMUTABLE` | Is the source truly guaranteed free from structural changes during traversal? |
| `CONCURRENT` | Does the source support concurrent modifications per contract? |
| `SORTED` / `DISTINCT` | Does the data genuinely uphold these guarantees? |
| Lifecycle | Is the same mutable Spliterator never accessed concurrently across threads? |

Particularly severe bug example:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    return this; // Wrong: both branches share one object and cursor.
}
~~~

A valid `trySplit` returns a Spliterator managing a **separate** partition of the untraversed source, while the original retains the remainder. For `ORDERED` sources, the returned split must be the prefix. Never verify correctness by checking `count()` alone, because `count()` may use `SIZED` without traversing elements.

### 15.2. When Does Parallel Help?

Evaluate three factors:

1. **Source size:** are there enough elements or tasks to split?
2. **Per-element cost:** is work heavy and independent enough to outweigh coordination overhead?
3. **Splitting quality:** does `Spliterator.trySplit()` produce balanced partitions cheaply?

Next, inspect costs of `sorted`, `distinct`, and `limit` on `ORDERED` sources; combiner cost; CPU/memory contention; and whether blocking I/O occurs.

If a pipeline uses `parallel()` yet contains side effects or a shared-state accumulator, **fix correctness first**—never benchmark to hunt for a "less buggy" configuration.

## 16. Meaningful Performance Measurement Methodology

Never benchmark two different algorithms and conclude parallel mode is faster. Compare **the same input, the same operation, and the same output**.

~~~java
import java.util.stream.IntStream;

public class ParallelReviewExample {
    static long work(int n) {
        long x = n + 1L;
        for (int i = 0; i < 100; i++) {
            x = x * 1_664_525L + 1_013_904_223L;
            x ^= x >>> 11;
        }
        return x & 1023L;
    }

    static long calculate(int count, boolean parallel) {
        IntStream source = IntStream.range(0, count);
        if (parallel) {
            source = source.parallel();
        }
        return source.mapToLong(ParallelReviewExample::work).sum();
    }

    public static void main(String[] args) {
        int count = 100_000;

        long sequential = calculate(count, false);
        long parallel = calculate(count, true);

        if (sequential != parallel) {
            throw new AssertionError("Results differ between modes");
        }

        System.out.println("Consistent result: " + sequential);
    }
}
~~~

This program checks **equivalence**, not speed. For trustworthy benchmarks:

- Use tools like **JMH** with warm-up and multiple iterations/forks.
- Ensure results are consumed so dead-code elimination does not remove unobservable work.
- Test representative input sizes and cost distributions.
- Control JDK, CPU, container quotas, background load, heap, and GC.
- Record throughput, latency, allocations, and impact on concurrent tasks.
- Never treat one `System.nanoTime()` reading as conclusive evidence.

**Never put console writes or HTTP calls inside callbacks to measure CPU power.** Shared I/O resources have completely different behavior and skew conclusions.

## 17. Java Version Policy and Upgrade Readiness

A codebase may be reviewed on a newer JDK while still deploying onto an organization's supported version. Reviews should note **target JDK version** and minimum required APIs.

| API / Syntax | Milestone to Note |
|---|---|
| `Stream`, `Collectors`, `Optional`, `Files.lines`, `Spliterator` | Java 8 |
| `List.of`, `Collectors.filtering`, `Optional.stream` | Java 9 |
| `List.copyOf`, `Collectors.toUnmodifiableList` | Java 10 |
| `Collectors.teeing` | Java 12 |
| `Stream.toList` | Java 16 |
| `record` (finalized) | Java 16 |
| Switch expressions (finalized) | Java 14 |
| Stream Gatherers (standard API) | Java 24 |

The reference program in section 12 targets **Java 17+**, matching the syntax and APIs it uses. If production must support Java 11, do not keep `teeing`, `record`, `Stream.toList`, or newer syntax without equivalent replacements.

If a project uses Stream Gatherers for stateful intermediate operations or windowing, the review must also check **integrator/finisher contracts, early termination, associativity**, and **target JDK support**. Never introduce a gatherer just to replace a plain `map` or `filter`.

## 18. Finding Severity Levels and Acceptance Criteria

Not every review comment carries the same urgency.

| Level | Examples | Action |
|---|---|---|
| **Blocker** | Data loss, wrong money totals, severe resource leak, race condition, Stream reuse crash | Must fix and add tests before approval |
| **Major** | Missing crucial input validation, unclear null/key policy, overload risk on expected scale | Requires fix and impact verification |
| **Minor** | Confusing variable names, minor duplication, suboptimal formatting or error messages | Fix by priority without obscuring blockers |
| **Question** | Unclear duplicate-ID policy, money overflow policy, bad-line policy, or ordering | Needs business decision; never guess |

To mark a finding resolved, look for:

1. **Concrete code change** eliminating the root cause.
2. **Before/after test** proving the bug is fixed or contract met.
3. **Documented API impact** if return type, order, mutability, or exceptions changed.
4. **Resource/performance evidence** if optimization was the goal.
5. **No new regressions** elsewhere, e.g. fixing a leak by accidentally returning a closed Stream.

Distinguish academic examples from production code reviews: a short Java snippet may validly illustrate `reduce` without covering observability, heap caps, PII redaction, or deployment rollout. Review against **the artifact's purpose**.

## 19. Pre-Completion Project Review Checklist

| Area | Decision Question | Expected Evidence |
|---|---|---|
| Requirements | Input/output contract and missing-data rules defined? | Sample suite, edge cases |
| Source | Re-traversable or single-use? | Ownership design, single-use test |
| Resource closing | I/O sources wrapped in `try-with-resources`? | Tests on both success and failure paths |
| Lambdas | Free of side effects, interference, and shared state? | Code inspection and parallel tests if used |
| Ordering | Proper use of `findFirst`, `findAny`, `sorted`, `forEachOrdered`? | Output/order tests |
| Nulls | Policy for nulls and parse errors defined? | Null/blank/invalid tests |
| Grouping keys | Equality, duplicate-ID, and null-key rules set? | Duplicate and grouping tests |
| Reduction | Identity and associativity valid? | Empty-source and sequential/parallel tests |
| Collector | Supplier/accumulator/combiner/finisher obey contract? | Merge and immutability tests |
| Arithmetic | Protected against `int/long` overflow and `double` drift? | Large-number tests, precision policy |
| Scale | Caps on line count and group cardinality considered? | Large-data tests, heap measurement |
| Parallelism | Justified and benchmarked? | Benchmark, CPU/GC/latency data |
| Version | APIs/syntax compatible with target JDK? | Build/CI verification |
| Maintainability | Parsing, business rules, aggregation, and I/O separated? | Focused methods with unit tests |
| Security | Do error logs avoid exposing sensitive data? | Logging/redaction policy |
| Deployment | Rollback plan and post-release observability ready? | Monitoring, alerts, stop criteria |

You can use this table as a **pull-request review template**. Most importantly, never mark an item "checked" without tests or solid reasoning to back it up.

## 20. Capstone Exercise: Review and Propose a Patch

**Scenario:** a project has a feature aggregating orders from a file-reading Stream, and the team wants to speed it up by calling `parallel()` and collecting into a revenue Map. A reviewer flags four issues:

- The file source is not closed when parsing fails.
- `parallel().forEach(...)` updates an external Map without synchronization.
- Some lines share duplicate IDs, yet business specs have not decided whether to merge them.
- Output region ordering relies on `HashMap`'s accidental iteration order.

**Practice prompts:**

1. Classify each issue as blocker, major, or question and explain why.
2. Sketch a contract-compliant **sequential** pipeline before optimizing.
3. Write at least five tests covering empty source, invalid input, duplicate IDs, large input, and I/O errors.
4. Choose a Map structure and display ordering policy; justify your choice.
5. Identify conditions that would lead you to decide **against enabling parallel**.
6. Describe evidence strong enough to accept that a performance change preserves correctness.

### Suggested Solution Direction

**On severity:** resource leaks and race conditions are blockers; duplicate IDs are a **policy question** that becomes a blocker if it skews revenue; Map ordering is a fixable bug whenever output order is part of the contract.

**On the pipeline:** start with `Files.lines` inside `try-with-resources`, separate `parseLine`, `filter(Payment::paid)`, and `groupingBy(..., summingLong(...))` or `teeing` depending on report shape. Never mutate a shared Map inside a callback.

**On duplicate IDs:** do not arbitrarily pick "keep first" or "sum amounts" yourself. Request a business decision, then add a test enforcing that exact policy. `distinct()` does not solve this when record equality differs from ID equality.

**On ordering:** use `TreeMap` if keys must sort ascending by comparator, or sort at output time. If business logic mandates a custom region list order, use a comparator against that list rather than default `String.compareTo`.

**On benchmarking:** run identical representative datasets on the same JDK/environment, verify output equivalence before timing; use warm-up/forks, control machine load, measure latency/throughput/heap, and monitor edge-case failures. Never accept a single timing snapshot as proof.

### Self-Check Questions

1. Why is `Files.lines(...).count()` insufficient to guarantee file closing? — **Terminal operations do not call `close` automatically**.
2. Can two terminal operations be invoked on the same Stream? — **No**.
3. Is `peek` guaranteed to run for every element when calling `count()`? — **No**.
4. When should `teeing` be used? — **When combining two collectors over the same source in one terminal operation**.
5. Why is `parallelStream().forEach(sharedList::add)` dangerous? — **Shared non-thread-safe mutable state**.
6. Why might `Stream.distinct()` fail to remove duplicate IDs? — **It uses whole-element `equals`/`hashCode`, unaware of business keys**.
7. Does `groupingBy` guarantee Map key order? — **No**, unless a suitable map factory is supplied or keys are sorted on output.
8. Why can `reduce(0, Integer::min)` be wrong? — **0 is not an identity for `min` across arbitrary inputs**.
9. Does `Collectors.toList()` guarantee returning a mutable `ArrayList`? — **No**.
10. What does `Spliterator.SUBSIZED` state? — **Child Spliterators continue to report exact sizes under contract**.
11. Can a benchmark prove code is semantically right for business rules? — **No**, dedicated correctness tests are required.
12. What should you do if total revenue risks overflowing `long`? — **Define an overflow error policy or use a suitable numeric representation**.

## 21. Conclusion: Defining "Done" with Evidence

A well-reviewed Stream project is not the one with the shortest pipeline expression or the most `parallel()` calls. It is the project with **clear input/output contracts**, **defensible API choices**, **deliberate handling of empty data and errors**, **explicit resource ownership**, **no dangerous side effects**, and **verifiable tests after changes**.

Review in order: **business correctness -> API contracts -> resource safety -> maintainability -> performance measurement**. When applying parallelism or building custom `Spliterator`s/collectors, preserve invariants for splitting, sizing, identity, associativity, combiners, ordering, and state.

The most important skill is not memorizing every Stream method, but knowing **what questions to ask and what evidence to gather** before shipping a pipeline into a large project. That foundation enables working with `filter`, `map`, `reduce`, `collect`, grouping, custom collectors, `Spliterator`, parallel Streams, and Stream Gatherers accurately, resource-efficiently, and maintainably over time.
