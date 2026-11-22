# Bounding Side Effects and Partial Completion

The Java Stream API encourages describing **data transformations** rather than manually orchestrating every loop. Operations such as `filter`, `map`, `flatMap`, `reduce`, and `collect` compose cleanly, evaluate lazily, and can run in parallel when appropriate. Yet that very flexibility makes **side effects**—database writes, HTTP calls, mutating external variables, logging, or file writes—dangerous if treated as guaranteed to execute once per element.

In particular, **Stream is not a transaction manager**. If an element triggers an exception midway through processing, changes already written to external systems **do not automatically roll back**. With parallel streams, other tasks may still be running when one failure is observed. The absence of a final return value **does not mean** prior side effects never happened.

This lesson belongs to the **Exceptions and Safety** chapter of the **JAVA_STREAM_API** module. Its goal is to bound side effects properly, understand how early termination and errors leave pipelines partially completed, distinguish valid mutable reduction from unsafe shared mutable state, and design verifiable commit boundaries. These concepts connect to grouping, custom collectors, `Spliterator`, parallel execution, I/O resources, and modern pipelines using Stream Gatherers.

## 1. Three Concepts That Must Not Be Equated

| Concept | Meaning | Example |
|---|---|---|
| **Side effect** | An observable effect beyond a function's return value | `writer.write`, `db.insert`, mutating an external `List`, incrementing a counter |
| **Partial completion** | Some steps already took effect while the overall task did not finish as expected | Wrote 2 lines successfully, then parsing line 3 threw an error |
| **Atomicity** | An operation publishes as a single success/failure unit under a designed protocol | Committing a transaction or publishing a staged file |

A pipeline can **return the right value** while still causing unintended side effects. Conversely, a pipeline that **throws an exception** may have already written partial output to a file or database.

### 1.1. Partial Completion Example

Suppose orders are `O1, O2, O3, O4` in sequence:

```text
O1 -> API call succeeds        [side effect already occurred]
O2 -> API call succeeds        [side effect already occurred]
O3 -> API call throws          [pipeline fails]
O4 -> not processed yet        [under specific sequential traversal]

collect/forEach fails
         |
         +-- DOES NOT automatically call API to undo O1 and O2
         +-- DOES NOT return "processed all four orders"
```

If you retry **the entire pipeline** without deduplication, O1 and O2 may be sent **twice**. The flaw lies not in `forEach` alone, but in coupling data traversal with **external actions lacking commit/retry boundaries**.

## 2. Behavioral Parameter Contracts in Streams

For a pipeline to optimize, split, and run correctly, functions passed to most Stream operations must be:

- **Non-interfering**: never modify the data source being traversed by the Stream, except where explicitly permitted by API docs.
- **Stateless**: element processing does not depend on state that may mutate during pipeline execution, especially state modified by other invocations.
- **Compliant with operation contracts**: e.g., reduction accumulator/combiner must be associative; comparators must be consistent; predicates must not mutate the source.

A *pure function* makes satisfying these conditions easy:

```java
// Value mapping; does not mutate external variables or source orders.
Stream<Long> amounts = orders.stream()
        .map(order -> order.getAmountCents() * 2L);
```

Here `orders` is a valid source and `getAmountCents()` returns `long`. This snippet only illustrates mapping shape; if multiplication risks overflow, use `Math.multiplyExact` or a larger numeric type.

By contrast:

```java
List<String> audit = new ArrayList<>();

Stream<String> ids = orders.stream()
        .map(order -> {
            audit.add(order.getId()); // Side effect outside the pipeline.
            return order.getId();
        });
```

When `ids` is constructed, the pipeline **has not necessarily run**, because `map` is a lazy intermediate operation. If the terminal operation does not need to call the mapper for every element, `audit` misses orders. If switched to parallel, the shared `ArrayList` can also be mutated concurrently by multiple workers.

### 2.1. Side Effects Are Not Forbidden Everywhere

Side effects are necessary when an application **persists or emits output**—sending notifications, writing files, saving to databases. What matters is:

1. Place side effects at **managed boundaries**, rather than hiding them in `map`/`filter` for convenience.
2. Explicitly define **ordering**, **success criteria**, **commit scope**, and **retry handling**.
3. Never depend on invocation counts or which thread runs a callback when the API makes no such commitment.
4. Separate **data preparation** from **external action execution** whenever possible.

Avoid the extreme claim that apps should have zero side effects; instead distinguish **pure transformation logic** from **controlled mandatory I/O**.

## 3. Why peek and map Are Not Reliable Audit Mechanisms

`peek` is useful for observation/debugging, not for guaranteeing a business action runs exactly once per record.

```java
List<String> values = Arrays.asList("A", "B", "C");

long count = values.stream()
        .peek(value -> System.out.println("Saw " + value))
        .count();

System.out.println(count); // 3
```

In some execution paths, `count()` can deduce source size without iterating element by element. The Stream specification allows eliding intermediate callbacks when doing so does not change **the API-guaranteed result**. Thus, never assert that three `Saw ...` lines will always print.

The same issue applies to side effects inside `map`:

```java
AtomicInteger processed = new AtomicInteger();

long result = values.stream()
        .map(value -> {
            processed.incrementAndGet();
            return value.toLowerCase();
        })
        .count();

// Never assert processed.get() always equals result.
```

`AtomicInteger` makes increments **thread-safe** if callbacks run concurrently; it **does not force the runtime to run the mapper** on every element and does not turn a side effect into a complete audit.

### 3.1. Fix by Expressing Results Directly

If the goal is **counting**:

```java
long count = values.stream().count();
```

If the goal is **counting records by category**:

```java
Map<String, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));
```

If the goal is writing **mandatory audit events**, organize a write step with an explicit **commit/idempotency contract**. Never rely on `peek` to decide whether a transaction was recorded.

## 4. Short-Circuiting: A Terminal Operation May Intentionally Stop Early

Operations like `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch`, and pipelines with `limit` can stop without consuming the whole source:

```java
boolean hasError = messages.stream()
        .anyMatch(message -> message.startsWith("ERROR"));
```

Once an error is found, `anyMatch` need not inspect remaining messages to return `true`. If the predicate both checks and increments an external counter, the predicate call count **does not reliably reflect total messages**.

### 4.1. Two Different Requirements

| Requirement | Suitable operation | Traverses the whole source? |
|---|---|---|
| Is there **at least one** error? | `anyMatch(isError)` | Can stop at first error |
| What is the **first** error in order? | `filter(isError).findFirst()` | Can stop early |
| **How many** errors exist? | `filter(isError).count()` | Normally evaluates elements needed to count |
| Get **up to K** first errors | `filter(isError).limit(K).collect(toList())` | Can stop after K errors |
| Write **all** errors to a file | Properly designed terminal action/collector | Must process all if full completion is required |

Do not pick `findFirst` just for speed when the requirement is **ensuring every record is acted upon**.

### 4.2. Where limit Is Placed Is Also a Business Decision

```java
// Up to the first 10 valid orders.
orders.stream()
        .filter(Order::isValid)
        .limit(10);

// Inspect only the first 10 source orders, then drop invalid ones.
orders.stream()
        .limit(10)
        .filter(Order::isValid);
```

These two pipelines **are not equivalent** if the data contains invalid orders. If `filter` performed database writes, both the number of writes and which records were affected would differ—another reason to keep side effects out of transformation steps.

### 4.3. Do Not Count Lambda Invocations to Infer Outcomes

With `parallelStream()`, both how many elements are visited before stopping and callback order can vary across runs. Some already-started tasks may finish even after a stop condition is met. Rely only on **API-contracted return values**—never use auxiliary counter variables to claim exactly K elements were processed.

## 5. Exceptions Do Not Roll Back Executed Side Effects

`Stream` does not wrap every lambda in a transaction. Example:

```java
List<String> sent = new ArrayList<>();

try {
    Stream.of("O1", "O2", "O3", "O4")
            .forEachOrdered(id -> {
                if ("O3".equals(id)) {
                    throw new IllegalStateException("Sending O3 failed");
                }
                sent.add(id);
            });
} catch (IllegalStateException failure) {
    System.out.println(failure.getMessage());
}

System.out.println(sent); // [O1, O2] in this sequential example.
```

`O1` and `O2` were already added to `sent`. If `sent.add` represents a real send call, those sends may have already happened and are not undone when `O3` throws. `forEachOrdered` enforces action sequence by encounter order; it **provides no rollback**.

### 5.1. Post-Failure State Is Not a Single Value

| Question | General guarantee? |
|---|---|
| Do external changes made before an error vanish automatically? | **No** |
| Will the pipeline return a complete `collect` result after an exception? | **No**, when the error propagates and the terminal does not finish |
| Can you tell how many elements took effect from the exception alone? | **No** |
| Is every callback guaranteed to run exactly once per element? | **No**, across all operation combinations/optimizations |
| Does Stream perform compensation or retries for external APIs? | **No** |
| Does closing an I/O source Stream undo data already written to a target? | **No** |

Therefore, applications need **a dedicated progress/commit contract** when correctness depends on processing all elements without duplicates.

### 5.2. Exceptions in map/filter/reduce/collect

A parsing mapper can throw `NumberFormatException`; a predicate can throw on `null`; an accumulator can throw `ArithmeticException` when `Math.addExact` detects overflow. When the error propagates to the caller, the terminal operation returns no normal result.

Yet two kinds of state must be separated:

1. **Intermediate state managed by Stream/Collector**: normally never exposed to callers when collection fails; you need not assume it is returned or reusable.
2. **Side effects pushed outward by lambdas**: file writes, network calls, shared object mutations. These changes may already exist even when the terminal returns no value.

Hence, “no List/Map result returned” does not mean “no records were sent.”

## 6. Parallel Streams Make Partial Completion Harder to Predict

In a parallel stream, elements can be processed across multiple workers. An error in one branch does not create an “instant global barrier” for side effects already executing in other branches.

```java
List<String> sent =
        Collections.synchronizedList(new ArrayList<>());

try {
    Stream.of("O1", "O2", "O3", "O4", "O5", "O6")
            .parallel()
            .forEach(id -> {
                if ("O3".equals(id)) {
                    throw new IllegalStateException("O3 failed");
                }
                sent.add(id);
            });
} catch (IllegalStateException failure) {
    System.out.println("Failed: " + failure.getMessage());
}

// Illustrative print only; DO NOT assert a fixed set or order.
System.out.println(sent);
```

`Collections.synchronizedList` protects individual List operations from data races, yet **does not make** a multi-step business workflow atomic. The IDs in `sent` can depend on execution scheduling; never assert that only `O1` and `O2` were sent.

### 6.1. Thread-Safe Differs from Transactional

| Property | Question |
|---|---|
| **Thread-safe** | Under concurrent calls from multiple threads, does the data structure avoid races/corruption? |
| **Atomic operation** | Does a single update occur atomically under its contract? |
| **Transaction** | Is a group of actions committed/rolled back as one unit? |
| **Idempotency** | Does repeating the same request cause additional effects? |
| **Exactly-once effect** | Does the external system guarantee the business effect happens once? |

A `ConcurrentHashMap` or `AtomicInteger` prevents races on that specific structure. It **does not** turn `chargeCard(); sendEmail(); updateReport()` into a transaction and cannot resolve retries after network timeouts where it is unknown whether the request succeeded.

### 6.2. forEach and forEachOrdered

`forEach` on a parallel Stream makes no ordering promise. `forEachOrdered` respects encounter order when the source is ordered, with actions ordered accordingly; however, actions do not necessarily run on the same thread.

**Key takeaway:** even `parallel().forEachOrdered(...)` **does not undo** prior actions when a later action throws. It preserves ordering semantics, **not** the integrity of a sequence of external operations.

## 7. Valid Mutable Reduction vs. Shared Mutable State

Java Stream permits mutable state **inside a collector** to accumulate data:

```java
List<String> ids = orders.parallelStream()
        .map(Order::getId)
        .collect(Collectors.toList());
```

`Collectors.toList()` does not declare `CONCURRENT`, yet still works properly on parallel streams. The framework can allocate per-branch containers and merge them afterward. Never assume that because `ArrayList` is not thread-safe, `collect(toList())` on a parallel Stream is broken.

Conversely:

```java
List<String> shared = new ArrayList<>();

orders.parallelStream()
        .map(Order::getId)
        .forEach(shared::add); // WRONG: multiple workers mutate one shared ArrayList.
```

In the second snippet, the application creates shared mutable state outside the pipeline and mutates it via actions. The bug is a race and missing combination contract; adding `synchronizedList` avoids races on `add` yet **does not** create the ordering or transactional guarantees business logic needs.

### 7.1. Use Collectors to Aggregate Metrics, Not forEach Updating a Shared Map

```java
Map<String, Long> countByRegion = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));
```

When you only need totals per region, `groupingBy(..., counting())` expresses the requirement far better than having workers call `sharedMap.merge(...)`. When writing a custom Collector, ensure `supplier`, `accumulator`, `combiner`, and `finisher` obey **identity – associativity – equivalence** and never declare `CONCURRENT` for un-thread-safe state.

### 7.2. Collectors Do Not Automatically Guarantee External Commits

A collector running `accumulator -> database.insert(row)` still causes external side effects and can partially complete on failure. Even if the collector obeys reduction contracts, **each callback is not a pipeline-wide commit boundary**. Avoid database writes inside accumulators/combiners unless retry, idempotency, and rollback rules are designed.

## 8. Separating Pure Transformations from Side-Effect Boundaries

An architecture that is usually easier to test:

```text
Source
  |
  v
parse / validate / map / filter     [pure computation]
  |
  v
prepare commands or results         [no external effects yet]
  |
  v
controlled commit                   [I/O, transaction, publish]
  |
  v
record status and handle retries
```

### 8.1. Prepare First, Commit Later

When data fits comfortably in memory:

```java
List<String> commands = orders.stream()
        .map(order -> {
            if (!order.isValid()) {
                throw new IllegalArgumentException(
                        "Invalid order: " + order.getId());
            }
            return order.getId() + "\t" + order.getAmountCents();
        })
        .collect(Collectors.toList());

// Execute only after preparation succeeds completely.
externalGateway.sendBatch(commands);
```

`externalGateway` is an assumed application interface. **Advantage:** if `map` throws during preparation, `sendBatch` is never called. **Limitation:** `sendBatch` itself can still partially write and fail; only transactions or the gateway's batch/idempotency protocol govern atomicity.

Furthermore, `collect(toList())` retains all `commands`; unsuitable for huge sources. In those cases, use **staging to a temporary file/DB, bounded batching, and an appropriate commit mechanism**.

### 8.2. Processing All Elements While Recording Errors

Never catch all errors with `try/catch` and return `null` to drop them silently:

```java
// Dangerous if records vanish without statistics:
orders.stream()
        .map(order -> {
            try {
                return transform(order);
            } catch (RuntimeException failure) {
                return null;
            }
        })
        .filter(Objects::nonNull);
```

If business rules require **continuing past bad data**, model parse outcomes explicitly:

```text
ParseResult
  - Success(value)
  - Failure(recordId, errorCode)
```

Then collect or write valid outcomes and failed records (*dead-letter*) **separately** alongside total counts. Never treat a pipeline's ability to continue as permission to drop data unreported.

## 9. Complete Java 8 Program: Identifying Side Effects and Verifying Outcomes

The following example uses a small order list to demonstrate:

1. A terminal action that throws **does not erase prior effects**.
2. Collecting data via **pure transformations** lets you validate output before publishing.
3. Parallel `collect` safely aggregates without mutating an external shared Map.
4. Tests should verify **values guaranteed by the API**, never asserting `peek` or parallel execution schedules.

Save as `StreamSideEffectSafetyDemo.java` and run on **JDK 8 or later**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class StreamSideEffectSafetyDemo {

    static final class Order {
        private final String id;
        private final String region;
        private final long amountCents;

        Order(String id, String region, long amountCents) {
            this.id = Objects.requireNonNull(id, "id");
            this.region = Objects.requireNonNull(region, "region");
            this.amountCents = amountCents;
        }

        String getId() { return id; }
        String getRegion() { return region; }
        long getAmountCents() { return amountCents; }
        boolean isValid() { return amountCents >= 0; }
    }

    static String prepare(Order order) {
        if (!order.isValid()) {
            throw new IllegalArgumentException(
                    "Negative amount on order " + order.getId());
        }
        return order.getId() + "=" + order.getAmountCents();
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("O1", "BAC", 100L),
                new Order("O2", "NAM", 200L),
                new Order("O3", "BAC", -1L),
                new Order("O4", "NAM", 300L)
        );

        // 1) Simulate side effects in a sequential terminal operation.
        List<String> externallySent = new ArrayList<>();
        try {
            orders.stream().forEachOrdered(order -> {
                if (!order.isValid()) {
                    throw new IllegalStateException(
                            "Failed to send " + order.getId());
                }
                externallySent.add(order.getId());
            });
            throw new AssertionError("Should have failed on O3");
        } catch (IllegalStateException expected) {
            System.out.println(expected.getMessage());
        }

        System.out.println(externallySent); // [O1, O2]
        check(externallySent.equals(
                Arrays.asList("O1", "O2")),
                "Side effects before the error still persist");

        // 2) Pure preparation: on failure, no List is returned.
        List<String> commands = null;
        try {
            commands = orders.stream()
                    .map(StreamSideEffectSafetyDemo::prepare)
                    .collect(Collectors.toList());
            throw new AssertionError("Should have rejected order O3");
        } catch (IllegalArgumentException expected) {
            System.out.println(expected.getMessage());
        }
        check(commands == null,
                "Never publish a new List when validation fails");

        // 3) Once input data is fixed, everything can be collected.
        List<Order> validOrders = Arrays.asList(
                new Order("O1", "BAC", 100L),
                new Order("O2", "NAM", 200L),
                new Order("O3", "BAC", 250L),
                new Order("O4", "NAM", 300L)
        );

        List<String> prepared = validOrders.stream()
                .map(StreamSideEffectSafetyDemo::prepare)
                .collect(Collectors.toList());

        check(prepared.equals(Arrays.asList(
                "O1=100", "O2=200", "O3=250", "O4=300")),
                "Prepared all four commands");
        System.out.println(prepared);

        // 4) Mutable reduction managed by Stream/Collector.
        Map<String, Long> grouped = validOrders.parallelStream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.counting()));
        check(grouped.get("BAC") == 2L
                && grouped.get("NAM") == 2L,
                "Parallel groupingBy produced exact counts");

        // 5) Collector List result without mutating
        // any shared ArrayList across threads.
        List<String> ids = validOrders.parallelStream()
                .map(Order::getId)
                .collect(Collectors.toList());
        check(ids.equals(Arrays.asList(
                "O1", "O2", "O3", "O4")),
                "toList preserves encounter order of source List");

        // 6) When only a metric is needed, do not hide a counter in peek.
        long paidLikeCount = validOrders.stream()
                .filter(order -> order.getAmountCents() > 0)
                .count();
        check(paidLikeCount == 4L, "Direct count");

        System.out.println("PASS: semantic checks");
    }
}
```

### 9.1. What Is Tested vs. What Is Not?

The program deliberately uses sequential `forEachOrdered` when simulating the `O3` failure, so in this run `externallySent` contains `[O1, O2]`. This tests **the behavior of this specific code**, not a general proof that every failing parallel `forEach` sends only the first two orders.

In the preparation step, `commands` is assigned only after `collect` returns normally. When `prepare` throws, `commands` stays `null`; however, **there is no general guarantee that programs putting side effects inside `map` leave zero external effects**. The benefit comes from `prepare` being pure and never calling external systems.

### 9.2. Testing with Parallel Streams

When checking parallel `groupingBy` output, the program compares **values by key** rather than `HashMap` iteration order. Similarly, `collect(toList())` on an encounter-ordered List preserves element order per contract, without implying mappers ran sequentially on one thread.

## 10. Complete Java 8 Program: Write to a Temp File and Publish on Success

For large exports, building an entire `List` in RAM before writing may consume too much memory. A safer design for **a new output file**:

1. Open the source via `Files.lines` inside `try-with-resources`.
2. Write each normalized line to a **temporary file in the target directory**.
3. If parsing or writing fails, **close resources and delete the temp file**, never publishing the final file.
4. Only after preparation succeeds completely, **move the temp file to the final name** using `ATOMIC_MOVE` if the filesystem supports it.

This approach **reduces exposing incomplete output**, though it is not a multi-resource transaction and does not automatically solve power loss, disk corruption, or concurrent writers across systems. The example publishes only to **a target file that does not yet exist**, without implementing an overwrite protocol.

Save as `StreamStagedFileDemo.java`; it generates its own sample files so it runs standalone on **JDK 8 or later**:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class StreamStagedFileDemo {

    // Sample data format: id;amountCents (no header).
    static String normalize(String line) {
        String[] columns = line.split(";", -1);
        if (columns.length != 2
                || columns[0].trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "Invalid format: " + line);
        }
        long cents = Long.parseLong(columns[1].trim());
        if (cents < 0) {
            throw new IllegalArgumentException(
                    "Negative amount: " + line);
        }
        return columns[0].trim() + "\t" + cents;
    }

    // Only for a new target file that does not yet exist.
    static void exportToNewFile(Path input, Path target)
            throws IOException {
        Path absoluteTarget = target.toAbsolutePath();
        Path parent = absoluteTarget.getParent();

        if (Files.exists(absoluteTarget)) {
            throw new IllegalArgumentException(
                    "Target file must not already exist");
        }

        Path staging = Files.createTempFile(
                parent, "stream-stage-", ".tmp");
        boolean published = false;

        try {
            try (Stream<String> lines =
                         Files.lines(input, StandardCharsets.UTF_8);
                 BufferedWriter writer =
                         Files.newBufferedWriter(
                                 staging, StandardCharsets.UTF_8)) {

                lines.map(StreamStagedFileDemo::normalize)
                        .forEachOrdered(value -> {
                            try {
                                writer.write(value);
                                writer.newLine();
                            } catch (IOException cause) {
                                throw new UncheckedIOException(cause);
                            }
                        });
            }

            // If unsupported, let the error propagate to the caller:
            // DO NOT silently fall back to a non-atomic move.
            Files.move(staging, absoluteTarget,
                    StandardCopyOption.ATOMIC_MOVE);
            published = true;
        } finally {
            if (!published) {
                Files.deleteIfExists(staging);
            }
        }
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory =
                Files.createTempDirectory("stream-safety-");
        Path valid = directory.resolve("valid.txt");
        Path invalid = directory.resolve("invalid.txt");
        Path published = directory.resolve("published.txt");
        Path rejected = directory.resolve("rejected.txt");

        try {
            Files.write(valid,
                    Arrays.asList("O1;100", "O2;200", "O3;300"),
                    StandardCharsets.UTF_8);
            Files.write(invalid,
                    Arrays.asList("O1;100", "O2;200", "O3;BAD"),
                    StandardCharsets.UTF_8);

            exportToNewFile(valid, published);
            List<String> exported = Files.readAllLines(
                    published, StandardCharsets.UTF_8);
            check(exported.equals(Arrays.asList(
                    "O1\t100", "O2\t200", "O3\t300")),
                    "Valid file must contain all data");
            System.out.println(exported);

            try {
                exportToNewFile(invalid, rejected);
                throw new AssertionError("Should throw parse error");
            } catch (NumberFormatException expected) {
                check(!Files.exists(rejected),
                        "Must not publish invalid output file");
                System.out.println(
                        "Rejected invalid file; no rejected.txt created");
            }
        } catch (AtomicMoveNotSupportedException unsupported) {
            System.out.println(
                    "Filesystem does not support ATOMIC_MOVE; "
                    + "file not published under this mechanism");
        } finally {
            Files.deleteIfExists(valid);
            Files.deleteIfExists(invalid);
            Files.deleteIfExists(published);
            Files.deleteIfExists(rejected);
            Files.deleteIfExists(directory);
        }
    }
}
```

### 10.1. What the Example Actually Protects

When reading `invalid.txt`, the first two lines may already be written to **the staging file**, then line three throws `NumberFormatException`. The `try-with-resources` block closes the reader/writer, and `finally` deletes the staging file. Callers **never observe `rejected.txt` as a successful output**.

If the filesystem does not support `ATOMIC_MOVE`, the code **fails loudly** instead of silently falling back to a non-atomic copy/move. Atomic file renaming applies only within the scope and guarantees of the filesystem; it **does not** automatically mean data is durably synced to storage in every case.

### 10.2. Limitations and Scenarios Outside Demo Scope

- `Files.exists` followed by `Files.move` does not fully eliminate races when **multiple processes target the same output name**. Publishing over existing files or overwriting requires proper concurrency protocols.
- If deleting the staging file fails, cleanup errors must also be observed; in production, record both primary and cleanup errors.
- For multiple output files, a single rename cannot create **an atomic transaction across all files**.
- If writing files and sending emails/updating databases in the same pipeline, moving a file does not roll back side effects in other systems.
- `Files.lines` can still materialize one huge line; use bounded readers/parsers if a hard memory cap is needed.
- The demo uses a simple `id;amountCents` format, not a CSV parser with quoting/escaping.

**Memory:** the staging approach writes line by line without holding a `List` of all records. Memory goes mainly to the active line, I/O buffers, and pipeline state; **the staging file size on disk** still grows with output data. Monitor disk space, quotas, and disk-full errors.

## 11. Retries, Idempotency, and Transactions in External Systems

### 11.1. Distinguishing Pre-Commit vs. Post-Commit Failures

| Case | What is known | Retry decision |
|---|---|---|
| Validation fails before calling API | No side effect called yet | Fix data and re-run |
| API explicitly returns error before taking effect | Per specific API contract | Retry per API policy |
| Timeout after sending network request | **Uncertain** whether server committed | Need idempotency key / status query |
| One batch committed, later batch failed | Earlier batch took effect | Scoped retry avoiding duplicates |
| Parallel Stream throws an error | Other actions may have run | Do not rely on encounter order to guess success scope |

**You cannot achieve “exactly once” for an external side effect merely by switching `map` to `forEach` or adding `synchronized`.** Guarantees depend on external protocols, commit state tracking, transactions, and retry strategies.

### 11.2. Business Idempotency Keys

Example invoice creation request:

```text
operation = "CREATE_INVOICE"
orderId   = "O123"
key       = "CREATE_INVOICE:O123"
```

The application passes the key to a gateway that **genuinely supports idempotency**. When resending the exact same request with the same key, the gateway per its contract returns the previous outcome instead of creating a duplicate invoice.

Accompanying conditions:

- Keys must stay stable across retries of **the same business operation**.
- Never reuse a key for **two different operations**.
- If payload changes while keeping the same key, the gateway must enforce a conflict policy.
- Idempotency retention windows and retry windows must align properly.

This is a **system-level design**, not a built-in feature of the Java Stream API.

### 11.3. Transactions and Outbox

When data must be stored in a database, you can:

1. Parse/validate records first.
2. Open a transaction in the persistence layer.
3. Write changes for **one chosen unit of work**.
4. Commit on success or roll back if the database and transaction type support it.

When you need to **both update a database and publish a message**, the *transactional outbox* pattern writes business changes and an outbox row in **the same database transaction**. Another worker publishes messages from the outbox with retry/deduplication. This avoids committing the DB while losing the message, though consumers still require idempotency since redeliveries can occur.

Never claim a single Stream writing to two systems creates a distributed transaction.

## 12. Progress Tracking and Recovery After Partial Completion

For large files, you cannot always keep all records in RAM and commit once. When processing in batches, define an explicit **checkpoint unit**:

```text
Batch 1: prepare -> commit -> checkpoint 1
Batch 2: prepare -> commit -> checkpoint 2
Batch 3: prepare -> error
Restart: resume after checkpoint 2
```

A checkpoint is valuable only when it is **accurately coupled to committed results**. Writing the checkpoint before writing results risks **losing** records on crash between steps. Writing results before checkpointing risks **duplicating** effects on retry after crash between steps. Use a shared-system transaction or idempotent/dedupe mechanisms to close that gap.

### 12.1. Choosing Durable Progress Keys

- Database sources: monotonic keys/cursors are often safer than offset pagination.
- Message brokers: offsets, partitions, and broker offset-commit contracts.
- Files: byte offsets or line numbers are safe only when the source **does not change** and has a file version/checksum identifier.
- Paginated APIs: store cursor tokens together with query identity and data version when supported.

An `AtomicLong processed` variable in a JVM is only a **runtime counter**, not a durable checkpoint if the process crashes or external effects remain unconfirmed.

### 12.2. Bounded Batches Still Require Cross-Batch Failure Handling

Processing `K` lines per batch bounds memory to `K` rather than `n`. However, **atomicity usually applies only at each batch boundary**, not across the whole file unless storage supports massive transactions.

With asynchronous batch dispatch, bound **both batch size and in-flight batch count**. Unbounded queues allow total memory to grow without limit even when each batch is small, and failures can leave many batches in uncertain states.

## 13. I/O Resources: Closing a Resource Is Not Rollback

`Files.lines` and I/O-backed Streams must be closed after finishing or on error:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long valid = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .count();
}
```

`try-with-resources` guarantees calling `close` on block exit, even when a pipeline step throws. However, **closing a reader does not erase written data**, **closing a writer does not make a file transactional**, and **closing an HTTP client does not undo requests the server already processed**.

### 13.1. One-Shot Streams and Source Lifecycles

- A Stream object can be consumed **only once**; never invoke a second terminal operation after consumption.
- Never return a Stream created inside a closed `try` block expecting the caller to keep reading.
- If an API returns an open Stream, document clearly **who closes it** and **when**.
- `onClose` registers close hooks, yet consuming with `collect` or `count` **does not auto-close every source Stream**.
- For I/O sources, iteration errors can be wrapped in `UncheckedIOException`; preserve the root cause while still releasing resources.

### 13.2. Side Effects in flatMap and Gatherers

`flatMap` opens sub-streams that may hold resources; the Stream API contracts to close sub-streams once flattened. Still, **any resource opened externally or managed manually** needs clear ownership.

With Java 24 Stream Gatherers, an integrator can maintain state and emit downstream per custom rules, yet a Gatherer is **not a transaction manager** either. Early termination, finishers, or parallel integration **do not roll back** external side effects. Never place payment charges or message sends inside an integrator assuming the entire pipeline will complete or self-compensate on error.

## 14. Testing True Semantics, Not Execution Schedules

A safe test suite separates:

| Test type | What to verify |
|---|---|
| **Pure transform** | Valid data, nulls, and bad data are handled per contract |
| **Short-circuit** | Return value is right; never assert `peek` call counts |
| **Sequential failure** | Side effects prior to error persist unless rollback was designed |
| **Parallel failure** | No races/corrupted state; never assert a fixed set of completed items |
| **Collector** | Sequential and parallel results match; combiner obeys contract |
| **File staging** | Parse failure creates no target file and cleans staging; do not assume `ATOMIC_MOVE` on every filesystem |
| **Retry/idempotency** | Resending with the same key causes no extra effect **per simulated gateway contract** |
| **Checkpoint** | Failures before/after commit do not lose or duplicate effects beyond policy |
| **I/O** | Streams, readers, and writers close on both success and failure |

### 14.1. Invariants Worth Asserting

For numeric reports, prefer checking:

```text
sum of group counts == valid record count
sum of group amounts == overall total amount
sequential result equals parallel result
no record rejected by validation policy appears
```

For data-export systems, add:

```text
target filename is never published when preparation fails
checkpoint advances only after appropriate commit
no duplicate dispatch on retry with same idempotency key
incomplete staging files are never exposed as final reports
```

These invariants align far better with business requirements than tests like “`peek` ran n times” or “thread A processed O1 before thread B.”

## 15. Common Misconceptions and Mistakes

| Claim or practice | Why it is unsafe | Replace with |
|---|---|---|
| “`peek` always runs once per element.” | Optimizations/short-circuiting can skip or stop callbacks | Use API-guaranteed Stream results |
| “Put `db.insert` in `map` to transform and save together.” | Hides side effects, muddies commit/retry | Separate transforms from contracted write steps |
| “When `forEach` throws, earlier records roll back.” | Stream has no transactions | Transactions/staging or compensation |
| “`forEachOrdered` rolls back because it preserves order.” | Only constrains action order | Design explicit commit boundaries |
| “`AtomicInteger` solves exactly-once.” | Only protects counter increments | Idempotency/transactions/checkpoints |
| “SynchronizedList means atomic results.” | Partial updates can happen before failure | Avoid shared state for atomic requirements |
| “`parallel()` finishes every element before throwing.” | Tasks may still be active; scheduling is non-deterministic | Never infer state from ordering |
| “`Collectors.toList()` is broken on parallel streams.” | Framework uses local containers and combiners | Use compliant collectors |
| “Writing a `CONCURRENT` HashMap collector is faster.” | `CONCURRENT` promises thread safety, not protection | Declare only when accumulator is genuinely thread-safe |
| “No `collect` result means nothing was sent.” | External side effects may still exist | Track commits/acks in target system |
| “Retrying the whole file after timeout is safe.” | Partial commits may have occurred | Idempotency keys or checkpoints |
| “try-with-resources undoes written files.” | Only closes resources | Staging + publish/transactions |
| “Writing temp file and moving is a multi-system transaction.” | Covers only one file on supported filesystems | Use system-appropriate transaction protocols |
| “Just catch errors and return null.” | Records can vanish untracked | Explicit success/failure `ParseResult` |
| “An auxiliary counter proves every callback ran.” | Laziness/short-circuit/elision and parallelism | Assert outputs/commit units directly |

## 16. Practice Exercises with Answers

### Exercise 1. Identifying Skipped Side Effects

**Prompt:** Why shouldn't you use `peek(audit::record)` before `count()` for mandatory auditing?

**Answer:** `peek` is an intermediate operation; `count()` may know the size without executing callbacks, or pipelines may short-circuit in other cases. A guaranteed count does not imply `peek`'s side effect ran n times. Place auditing at a write boundary with an explicit commit/idempotency contract.

### Exercise 2. forEachOrdered Throwing an Exception

**Prompt:** `Stream.of("A","B","C").forEachOrdered(...)` writes A, writes B, then throws on C. Do the written items disappear automatically?

**Answer:** No. `forEachOrdered` preserves action ordering by encounter order, yet never rolls back A and B. For output integrity, use an appropriate transaction or write to a staging file and publish only after completion.

### Exercise 3. Does anyMatch Inspect Everything?

**Prompt:** Does `List.of("ERROR","OK","OK").stream().anyMatch(s -> s.startsWith("ERROR"))` have to call the predicate on all three elements?

**Answer:** No; `anyMatch` can stop at the first matching element. `List.of` requires Java 9+, while `anyMatch`'s short-circuit semantics have existed since Java 8. Never use predicate call counts to measure “how many records were processed.”

### Exercise 4. Safe Counting on Parallel Streams

**Prompt:** With `parallelStream().forEach(o -> count[0]++)` on a `long[1]` array, is the count guaranteed accurate? Does `AtomicLong` solve the business semantics too?

**Answer:** The shared array suffers data races and lost updates. `AtomicLong` avoids increment races yet neither guarantees all callbacks run if the pipeline short-circuits/fails nor replaces transactions. When only a count is needed, use `count()` or `Collectors.counting()`.

### Exercise 5. Collect Outcome When Mapper Throws

**Prompt:** In `stream.map(parse).collect(toList())`, the parser fails on one element. Can the caller receive a complete result `List` from that terminal operation?

**Answer:** No, if the error propagates; `collect` returns no normal result. If the parser is pure, no external side effects need rollback. If the parser called APIs or sent business logs, effects before the failure may persist.

### Exercise 6. Retrying After HTTP Timeout

**Prompt:** A client calls `POST /invoice` and times out. Should it assume the server has not created the invoice and call again?

**Answer:** No. A timeout does not tell you whether the server committed. You need idempotency keys, status lookup by business key, or the server's retry protocol. The Stream API has no knowledge of external transaction state.

### Exercise 7. Writing Large Files Without Holding Everything

**Prompt:** You want to normalize 5 million lines and publish one report file; is `collect(toList())` required?

**Answer:** No. Read with `Files.lines`, stream-write into a staging file via `BufferedWriter`, close cleanly, then publish per file protocol. Memory need not hold all five million lines, though you must bound line length, monitor disk space, and handle errors before publishing.

### Exercise 8. Side Effects with a Gatherer

**Prompt:** A Java 24 Gatherer has an integrator sending an email per element. If downstream uses `limit(2)` or one element throws, can you claim all emails were sent exactly once?

**Answer:** No. A Gatherer can stop early based on downstream demand; errors do not roll back sent emails. Transformations should manage isolated state, while sending emails needs proper idempotency/commit protocols rather than tying correctness to integrator call counts.

### Exercise 9. Atomic Move and System Failures

**Prompt:** Can you call `Files.move(temp, target, ATOMIC_MOVE)` and claim both the file and database committed atomically?

**Answer:** No. Atomic move provides guarantees only within that single operation on supporting filesystems; it does not coordinate transactions with a database. If the system lacks atomic move support, fail explicitly or use another protocol—never silently treat a regular move as atomic.

### Exercise 10. Designing Checkpoints

**Prompt:** After successfully writing the second batch, the program crashes before saving the checkpoint. What can happen when restarting from the old checkpoint?

**Answer:** The second batch may be executed again. Use idempotent writes/deduplication or transactions committing progress state and data together where feasible. Writing the checkpoint before committing fails in the opposite direction: data can be lost.

## 17. Safety Checklist Before Deploying Streams

1. **Are all side effects identified?** File writes, database, HTTP, emails, counters, or mutating an external collection?
2. **Are mappers/predicates stateless and non-interfering?** Do they mutate the source or depend on shared variables?
3. **Does auditing depend on `peek`/`map` call counts?** If so, redesign it.
4. **Are there short-circuiting operations?** `limit`, `findFirst`, `findAny`, `anyMatch` can stop before traversing everything.
5. **Does the source have encounter order?** Must action order be preserved, or only aggregate results?
6. **If an element throws, what happens to prior effects?** Are commits, rollbacks, or compensations in place?
7. **Is a parallel stream used?** Have you avoided shared mutable state and assumptions about scheduling?
8. **Are Collectors compliant with their contracts?** Are supplier/accumulator/combiner and characteristics accurate?
9. **Are there external gateways?** Are idempotency keys, timeout policies, acknowledgements, and retry windows defined?
10. **Are batches/checkpoints used?** Can a crash between commit and checkpoint lose or duplicate data?
11. **Are files written?** Are source/target closing, staging, publishing, and error cleanup handled?
12. **What about invalid data?** Fail-fast or explicit error recording; are records being silently dropped?
13. **Are resources bounded?** Temporary memory, queued batches, line lengths, output sizes, and open file handles?
14. **Do tests verify mid-stream failures?** Never test only happy paths.
15. **Have you separated “correct output” from “committed side effects”?** Both concepts must be verified independently.

**Conclusion:** The Java Stream API is a tool for expressing transformations and aggregations, **not** a transaction manager or automatic exactly-once delivery system. Side effects hidden in `map`/`peek` risk being skipped, short-circuited, or run out of expected order; side effects in terminal actions can **partially complete** before an exception propagates; parallel streams make that scope even harder to predict. Rely on pure transformations, contract-compliant collectors, controlled write boundaries, properly closed resources, staging/transactions, and idempotency/checkpoints where needed. That way pipelines enjoy declarative clarity without sacrificing correctness or failure recovery.
