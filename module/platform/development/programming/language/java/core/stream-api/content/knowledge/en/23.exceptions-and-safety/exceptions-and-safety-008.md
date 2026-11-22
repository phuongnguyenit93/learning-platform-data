# Identifying Unsafe Operations in Parallel Processing

The Java Stream API lets you turn a sequential pipeline into a parallel-capable pipeline using `parallel()` or `parallelStream()`. Concise syntax does not mean every transformation is **safe under concurrent execution**. A lambda writing to a shared `ArrayList` can lose data; a non-associative `reduce` can yield a different result from sequential execution; an operation touching files, connections, or transactions can run on an unintended thread. Even when results are right, task-splitting, synchronization, or ordering overhead can make a parallel Stream slower.

This lesson belongs to the **Exceptions and Safety** chapter of the **JAVA_STREAM_API** module. Its goal is to **spot** unsafe operations from pipeline structure, explain why they are unsafe, fix them using `filter`, `map`, `reduce`, `collect`, an appropriate collector, or a clear sequential alternative, and test result invariants. It also connects to `Spliterator`, collector accumulator state, Stream Gatherers, exceptions, resources, and performance.

Core examples use **Java 17+**. Sections involving `Stream.gather` and custom Gatherers require **Java 24+**, where Stream Gatherers became a standard API.

> **Foundational Rule:** Parallelizing does not turn broken code into correct code, and thread-safe does not automatically mean business-correct. Establish correctness of the operation **before** measuring performance gains.

## 1. What Does a Parallel Stream Actually Change?

`parallelStream()` creates a Stream configured for parallel execution; `parallel()` switches a pipeline to parallel mode. When executing a terminal operation, the framework **may** split the source into chunks and process them across multiple tasks.

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5);

long sequential = values.stream()
    .filter(n -> n % 2 == 0)
    .mapToLong(n -> (long) n * n)
    .sum();

long parallel = values.parallelStream()
    .filter(n -> n % 2 == 0)
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(sequential); // 20
System.out.println(parallel);   // 20
```

Here both pipelines compute the sum of squares of even numbers. `filter` and `mapToLong` need not mutate external data; integer addition on these small chosen values is guaranteed not to overflow. Thus, both execution modes can be compared against the same business outcome.

What must **never be assumed** when switching to parallel:

- The invocation order of **lambdas**, `peek`, or `forEach` matches sequential order.
- Each element is always processed on a specific thread.
- Tasks can share an external mutable variable without synchronization.
- Stateful aggregations automatically split/merge properly.
- `findAny`, `limit` on unordered sources, or side-effecting operations follow the same execution progression.
- `parallel()` definitely uses more CPUs in a beneficial way.

### 1.1. Distinguishing Result Order from Execution Order

A `List` source has **encounter order**. A parallel pipeline can still preserve **result order** when required by operations like `toList()` on an ordered Stream:

```java
List<Integer> doubled = values.parallelStream()
    .map(n -> n * 2)
    .toList();

System.out.println(doubled); // [2, 4, 6, 8, 10]
```

This **does not mean** `map` calls ran in `1 → 2 → 3 → 4 → 5` order or on the same thread. The framework can evaluate partitions at different times and assemble results in encounter order.

## 2. Three Criteria for Identifying Safe Operations

A behavioral parameter such as `Predicate`, `Function`, `Consumer`, or an accumulator in Stream should be examined along **three axes**:

| Axis | Question | Red flag |
| --- | --- | --- |
| **Non-interference** | Does the lambda mutate the source being traversed? | `source.add(...)` or `source.remove(...)` inside `filter` |
| **Stateless behavior** | Does the outcome depend on mutable state changing outside the lambda? | Shared counters, flags, lists, or current positions |
| **Aggregation contract** | Are identity, accumulator, and combiner compatible and associative? | Using subtraction in reduction; using a shared mutable container as identity |

Parallelism also requires inspecting **thread safety** of any stateful dependency: mutable formatters, caches, repositories, transaction contexts, custom loggers, and objects called by lambdas.

### 2.1. Two Layers of “Correctness” to Separate

- **Data correctness:** outputs match filter criteria, counts, and required ordering without losing elements.
- **Coordination/resource correctness:** no data races, no illegal source mutation, no leaked files, no using transaction contexts on the wrong thread, and no unintended lingering side effects.

A program can throw zero exceptions and still fail both layers.

## 3. Red Flag #1: Updating a Shared `ArrayList` Inside `forEach`

This is a classic bug:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

IntStream.range(0, 100_000)
    .parallel()
    .forEach(shared::add); // DANGEROUS.
```

`ArrayList.add` mutates the backing array and size field without synchronization across concurrent writers. You can encounter lost elements, corrupted slots, wrong values, or exceptions; there is **no guarantee** the bug manifests on every run.

Fix:

```java
List<Integer> result = IntStream.range(0, 100_000)
    .parallel()
    .boxed()
    .toList();

System.out.println(result.size()); // 100000
```

When using terminal `toList()`, the framework manages result assembly and preserves the encounter order of ordered sources.

### 3.1. Why `Collections.synchronizedList` Is Not a General Solution

You could write:

```java
List<Integer> synchronizedResult =
    java.util.Collections.synchronizedList(new ArrayList<>());

IntStream.range(0, 100_000)
    .parallel()
    .forEach(synchronizedResult::add);
```

Individual `add` calls are protected per the wrapper's contract. However:

- Insertion order is **not** guaranteed to match encounter order.
- Contending on one shared lock can hurt parallel speedups.
- Multi-step operations like “check-then-add” still lack atomicity.
- Unless side effects are genuinely required, `collect` or `toList` expresses intent much better.

**Rule:** Whenever you see `parallel().forEach(collection::add)` or `parallel().peek(collection::add)`, inspect it immediately; never just slap on `synchronized` and call every requirement solved.

## 4. Red Flag #2: Shared Mutable Counters

Incorrect example:

```java
int[] counter = {0};

long count = IntStream.range(0, 100_000)
    .parallel()
    .filter(n -> {
        if (n % 2 == 0) {
            counter[0]++; // Data race.
            return true;
        }
        return false;
    })
    .count();
```

`counter[0]++` is a read-increment-write sequence, not an atomic update. Multiple threads can read the same value and overwrite each other's updates.

This also puts **side effects inside a predicate**, coupling behavior to how the framework invokes predicates; some pipelines can elide callbacks when terminal semantics remain unchanged.

Right way to count:

```java
long evenCount = IntStream.range(0, 100_000)
    .parallel()
    .filter(n -> n % 2 == 0)
    .count();

System.out.println(evenCount); // 50000
```

### 4.1. `AtomicInteger` Fixes the Race, Not the Flawed Design

```java
java.util.concurrent.atomic.AtomicInteger counter =
    new java.util.concurrent.atomic.AtomicInteger();

IntStream.range(0, 100_000)
    .parallel()
    .forEach(n -> counter.incrementAndGet());

System.out.println(counter.get()); // 100000 if full traversal succeeds
```

`AtomicInteger` makes increments atomic, yet:

- It does not enforce element execution order.
- It does not turn multi-step mutations across other objects into transactions.
- Workers may all contend on one variable.
- If the pipeline short-circuits or optimizes away callbacks, call count need not equal source count.
- For **counting elements**, `count()` is usually cleaner and right.

`LongAdder` can suit concurrent counters in specialized designs, yet calling `sum()` while threads are still updating does not give an atomic snapshot of all updates. Do not use `LongAdder` to “patch” a count that belongs in a terminal operation.

## 5. Red Flag #3: `peek` with Mandatory Side Effects

`peek` is commonly used for debugging:

```java
List<Integer> result = List.of(1, 2, 3, 4)
    .parallelStream()
    .peek(n -> System.out.println("saw " + n))
    .map(n -> n * 2)
    .toList();
```

Logs may interleave out of List order. That does not mean the result is wrong.

Far more dangerous is using `peek` for business writes:

```java
orders.parallelStream()
    .peek(order -> repository.markProcessed(order.id()))
    .count(); // DO NOT use peek to guarantee side effects.
```

By the Stream contract, side effects in behavioral parameters are **not guaranteed to run** across all optimizations; specifically, `count()` on sized sources may skip traversing intermediate stages. Thus, rows marked in the repository may not match expectations.

**Sound design:** use Stream to compute the list of IDs/records to update; then run an explicit write step with controlled retry, transaction, and idempotency contracts. When updating is the main task, an explicit sequential loop is sometimes more reliable and easier to operate.

### 5.1. Patterns Warranting Code Review

- `peek(System.out::println)`: fine for temporary observation, never assert call counts.
- `peek(cache::put)`: risk of races and skipped callbacks.
- `peek(metrics::increment)`: callback invocation count is not a business KPI.
- `map(x -> { save(x); return x; })`: `map` is turned into side-effecting I/O; execution contracts must be explicit.

## 6. Red Flag #4: Mutating the Source Collection During Traversal

Dangerous in both sequential and parallel modes, especially parallel:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.parallelStream()
    .filter(n -> {
        if (n % 2 == 0) {
            source.remove(n); // Mutating the source while traversing.
        }
        return true;
    })
    .toList();
```

`ArrayList` is not designed for structural modification concurrent with standard Spliterator traversal. The code can throw `ConcurrentModificationException`, miss elements, or yield unexpected results. **Fail-fast detection is best-effort, not a guarantee of catching every race.**

Instead, create a new collection:

```java
List<Integer> odd = source.parallelStream()
    .filter(n -> n % 2 != 0)
    .toList();

System.out.println(odd); // [1, 3]
```

If business logic must mutate `source` itself, do it in a controlled step **after traversal finishes**, or use a collection method on a single thread when parallel Stream is unnecessary.

### 6.1. `Spliterator.CONCURRENT` Does Not Permit Arbitrary Side Effects

Some concurrent sources expose Spliterators supporting concurrent source edits per **their own contract**. `Spliterator.CONCURRENT` does not mean:

- Lambdas mutating a separate `ArrayList` are safe.
- Encounter order is preserved as the source mutates.
- The source gives a fixed snapshot.
- Every downstream collector becomes concurrent.

Inspect exact `ORDERED`, `SIZED`, `CONCURRENT`, and `IMMUTABLE` characteristics and source behavior rather than guessing from the word “parallel.”

## 7. Red Flag #5: Depending on Lambda Invocation Order

Stateful code example:

```java
java.util.concurrent.atomic.AtomicInteger index =
    new java.util.concurrent.atomic.AtomicInteger();

List<String> labels = List.of("A", "B", "C", "D")
    .parallelStream()
    .map(s -> index.getAndIncrement() + ":" + s)
    .toList();
```

`AtomicInteger` gives each increment a distinct number, yet **does not tie that number to source position**. Output may be `["2:A", "0:B", "3:C", "1:D"]` or another numbering, even though the outer list remains ordered A, B, C, D.

To number elements **by their position in a List**:

```java
List<String> items = List.of("A", "B", "C", "D");

List<String> indexed = IntStream.range(0, items.size())
    .parallel()
    .mapToObj(i -> i + ":" + items.get(i))
    .toList();

System.out.println(indexed); // [0:A, 1:B, 2:C, 3:D]
```

Precondition: `items` stays stable during traversal and supports indexed access efficiently; for `ArrayList` or `List.of`, this is direct. Do not repeatedly index into a huge `LinkedList` expecting good performance.

### 7.1. `forEach` vs. `forEachOrdered`

```java
List.of(1, 2, 3, 4)
    .parallelStream()
    .forEach(System.out::println); // Print order is not guaranteed.

List.of(1, 2, 3, 4)
    .parallelStream()
    .forEachOrdered(System.out::println); // Follows encounter order.
```

`forEachOrdered` processes elements in encounter order on ordered sources; this can require coordination and negate parallel speedups at the terminal stage.

**Never assume `forEachOrdered` makes arbitrary mutable shared state safe** more broadly: data can still be accessed concurrently elsewhere, and upstream `map`/`peek` side effects can still run on other threads.

## 8. Red Flag #6: Using a Non-Associative `reduce`

Parallel reduction splits the source into chunks, computes partial results, and merges them. Therefore the operation needs a **proper identity** and **associativity** across the target domain.

Subtraction is a classic non-associative example:

```text
(10 - 4) - 2 = 4
10 - (4 - 2) = 8
```

The snippet below is an unsafe design:

```java
int result = List.of(10, 4, 2)
    .parallelStream()
    .reduce(0, (a, b) -> a - b);

// Do not expect a fixed value or sequential equivalence.
```

`0` is not a two-sided identity for subtraction, and subtraction is not associative. Happening to match on one run proves nothing.

Use an operation obeying the contract, such as non-overflowing integer addition:

```java
int total = List.of(10, 4, 2)
    .parallelStream()
    .reduce(0, Integer::sum);

System.out.println(total); // 16
```

### 8.1. Identity Must Be Neutral Under the Contract

Example:

```java
int wrong = List.of(1, 2, 3)
    .parallelStream()
    .reduce(10, Integer::sum); // 10 is not an identity.
```

In parallel execution, the identity may be used for each partial accumulator; never treat `10` as a “value added once” and expect `16`.

To add 10 to the **final sum**, place it outside the reduction:

```java
int correct = 10 + List.of(1, 2, 3)
    .parallelStream()
    .reduce(0, Integer::sum);

System.out.println(correct); // 16
```

### 8.2. Associativity Does Not Mean Commutativity

String concatenation is mathematically associative:

```text
("A" + "B") + "C" = "A" + ("B" + "C")
```

yet not commutative:

```text
"A" + "B" != "B" + "A"
```

On ordered Streams, the framework respects encounter order for compliant reductions; on unordered Streams, do not expect order-sensitive aggregations to produce the same sequence in a fixed business order.

## 9. Red Flag #7: Using a Mutable Container as `reduce` Identity

Very common mistake:

```java
List<Integer> result = IntStream.range(0, 1000)
    .boxed()
    .parallel()
    .reduce(
        new ArrayList<>(),
        (list, n) -> {
            list.add(n);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    ); // DANGEROUS.
```

Problems:

- `reduce` is designed for **immutable value accumulation** whose identity/accumulator/combiner satisfy compatibility and associativity laws.
- A single mutable `ArrayList` identity fails the expectation of an independent identity per branch.
- The accumulator mutates the object passed as identity; under parallel runs this causes shared state, races, duplicated elements, or wrong results.
- Combiner `addAll` also mutates the object, breaking identity and associativity reasoning.

Right approach for **mutable reduction**:

```java
List<Integer> result = IntStream.range(0, 1000)
    .boxed()
    .parallel()
    .collect(
        ArrayList::new,
        ArrayList::add,
        ArrayList::addAll
    );

System.out.println(result.size()); // 1000
```

Three-argument `collect` has a `supplier` creating **separate containers** for accumulation, `accumulator` adding one element, and `combiner` merging containers.

Or even simpler:

```java
List<Integer> result = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .toList();
```

**Distinction:** `ArrayList::add` being a mutable operation **does not make `collect` wrong**, because the collector manages container partitioning properly. What is wrong is trying to express **mutable reduction** through a `reduce` overload lacking that contract.

## 10. Three Risk Categories When Using a Parallel `Collector`

A collector has core roles:

```text
supplier      -> creates accumulation container
accumulator   -> adds an element into a container
combiner      -> merges two containers
finisher      -> produces the final result
characteristics -> describes special guarantees
```

Inspect not only the accumulator code, but also **how multiple containers are merged**.

| Component | Red flag | Check question |
| --- | --- | --- |
| Supplier | Returns the same static object | Does each accumulation branch get independent state? |
| Accumulator | Writes to external variables, shared mutable state | Does it update only the provided container? |
| Combiner | Drops data or merges in wrong order | Does the merged result match processing the whole source? |
| Finisher | Returns an internal mutable object externally and keeps mutating it | Is the result immutable per contract? |
| Characteristics | Declares `CONCURRENT` when accumulator is not thread-safe | Does it genuinely support concurrent calls? |

### 10.1. `Collectors.toList()` Still Works with Parallel Streams

```java
List<String> ids = orders.parallelStream()
    .map(Order::id)
    .collect(java.util.stream.Collectors.toList());
```

You do not need to replace `Collectors.toList()` with a shared `synchronizedList`. A collector without the `CONCURRENT` characteristic can still run properly on a parallel Stream because the framework uses **independent** accumulation containers and then calls the combiner.

**Parallel collection does not mean every thread writes to a single `ArrayList`.**

### 10.2. `CONCURRENT` Is a Promise, Not a “Speed Booster”

If you write a custom collector and attach `Collector.Characteristics.CONCURRENT`, you declare that the accumulator can be called **concurrently on the same result container** safely under its contract.

Never declare `CONCURRENT` on a collector writing to a plain `HashMap` or `ArrayList` without matching concurrency protection.

`Collector.Characteristics.UNORDERED` states the result is not bound by encounter order; `IDENTITY_FINISH` is valid only when the accumulation type matches the result type and finisher is a true identity. Never treat characteristics as “performance hints” unless their contracts actually hold.

## 11. `groupingBy` and `groupingByConcurrent`: Choose by Data Requirements

Example grouping paid orders by region:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

Map<String, Long> counts = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

ConcurrentMap<String, Long> concurrentCounts = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.counting()
    ));

System.out.println(counts.equals(concurrentCounts)); // true
```

Both options can produce Maps with equal counts, yet their contracts differ:

- `groupingBy` performs grouping suitable for both sequential and parallel; in parallel, the combiner may merge Maps across branches.
- `groupingByConcurrent` creates a **concurrent/unordered collector**, appropriate when **encounter order of values within each group is not required**.
- `ConcurrentMap` is thread-safe at the Map-operation level, yet **does not make mutable objects stored inside thread-safe after collection**.
- With “hot” keys (many elements sharing one key), contention can hurt performance. Never assume `groupingByConcurrent` is always faster.

### 11.1. Do Not Test Group List Ordering Under Concurrent Grouping

```java
ConcurrentMap<String, List<Order>> byRegion =
    orders.parallelStream()
        .collect(Collectors.groupingByConcurrent(Order::region));
```

Each group's list is not guaranteed to reflect encounter order like a sequentially built list. If order by timestamp is a business requirement, sort explicitly afterward or use an order-preserving design.

**Safety during collection** and **safety when multiple threads mutate result lists after collection** are two separate stages. Never mutate the `List<Order>` values in `byRegion` concurrently without dedicated protection.

## 12. `toMap`: Duplicate Keys, Merge Functions, and Merging

`Collectors.toMap` is often used in parallel pipelines, yet data may contain duplicate keys.

```java
// Multiple Orders share the same region.
// Without a merge function, toMap can throw IllegalStateException.
Map<String, Long> unsafe = orders.parallelStream()
    .collect(Collectors.toMap(
        Order::region,
        Order::amountVnd
    ));
```

This is not only a parallel issue: duplicate keys also fail the sequential version.

To sum totals by region:

```java
Map<String, Long> totals = orders.parallelStream()
    .collect(Collectors.toMap(
        Order::region,
        Order::amountVnd,
        Long::sum
    ));
```

If a merge function depends on order or has side effects, check whether merging remains valid when the source splits. For monetary values, watch out for `long` overflow; for fractional currencies use `BigDecimal` with explicit scale and rounding rules.

### 12.1. Mutable Keys Are Also Dangerous

If a key object changes its `equals`/`hashCode` during or after Map construction, the Map may fail to look up keys as expected. Use immutable keys such as `String` or appropriate immutable records; never let workers mutate fields used as keys while grouping/`toMap` runs.

## 13. Red Flag #8: Tasks Depending on `ThreadLocal` and Transaction Context

`ThreadLocal` stores a value per **executing thread**, not per “business request” or “Stream run.”

Architecturally dangerous example:

```java
static final ThreadLocal<String> TENANT = new ThreadLocal<>();

TENANT.set("tenant-A");

orders.parallelStream()
    .forEach(order -> {
        // Never assume TENANT.get() on a worker thread
        // equals "tenant-A".
        processForTenant(TENANT.get(), order);
    });

TENANT.remove();
```

On other workers, `TENANT.get()` may miss the caller thread's value or carry stale context if lifecycle cleanup was flawed. This is a serious risk when tenant IDs, user context, tracing, transactions, or authorization info are passed implicitly through thread-local storage.

**Preferred solution:** pass immutable context explicitly as parameters:

```java
String tenant = "tenant-A";

List<Result> results = orders.parallelStream()
    .map(order -> processForTenant(tenant, order))
    .toList();
```

Here `tenant` is an immutable captured value, not mutable thread-bound state. You must still verify `processForTenant` is genuinely thread-safe and does not rely on thread-bound transactions lower down.

### 13.1. Should You Create a `ThreadLocal` per Task?

`ThreadLocal` is not a “private state container per element”: a thread can handle multiple elements and is reused in pools. In pool-backed code, manage lifecycle, cleanup, and context correctness. For Stream accumulation, prefer **state managed by Collector/Gatherer** or a clear sequential loop.

## 14. Red Flag #9: Non-Thread-Safe Helper Objects

Collections and counters are not the only stateful things. Some utility objects are mutable too:

```java
// Never share a mutable SimpleDateFormat across multiple workers.
java.text.SimpleDateFormat sharedFormatter =
    new java.text.SimpleDateFormat("yyyy-MM-dd");

List<java.util.Date> legacyDates = List.of(
    new java.util.Date(0L),
    new java.util.Date(86_400_000L)
);

List<String> dates = legacyDates.parallelStream()
    .map(sharedFormatter::format)
    .toList();
```

`SimpleDateFormat` is not designed for concurrent use by multiple threads without synchronization. Concurrent parsing/formatting can corrupt outputs or throw exceptions.

For `java.time` timestamps, `DateTimeFormatter` is immutable and thread-safe by contract:

```java
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

DateTimeFormatter formatter = DateTimeFormatter
    .ofPattern("uuuu-MM-dd")
    .withZone(ZoneOffset.UTC);

List<java.time.Instant> timestamps = List.of(
    java.time.Instant.parse("2026-01-01T10:00:00Z"),
    java.time.Instant.parse("2026-01-02T10:00:00Z")
);

List<String> dates = timestamps.parallelStream()
    .map(formatter::format)
    .toList();
```

The first example uses `java.util.Date` with a legacy mutable formatter; the second uses `List<Instant>` with `java.time`'s immutable formatter. A safe formatter alone does not automatically make other objects touched by the pipeline safe.

### 14.1. Stateful Connections and Sessions

Objects such as JDBC `Connection`, transaction-bound sessions, mutable parsers, or writers usually have **their own concurrency contracts**. Never capture and share one connection/session across `parallel().forEach(...)` just because Java allows capturing the variable in a lambda.

For external I/O, decide per-task resource allocation, concurrency bounds, timeouts, retries, and idempotency. Many cases fit executors/structured concurrency plus a separate aggregation step far better than parallel Streams.

## 15. Red Flag #10: Mistaking `double` Rounding for Bit-Exact Equality

Binary floating-point addition is not strictly associative due to rounding:

```text
(a + b) + c may differ from a + (b + c)
```

Illustrative example:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

When a parallel reduction groups and sums values differently, order-induced differences can appear. `DoubleStream.sum()` may use compensated summation and specific reduction strategies, so do not require it to match a naive sequential loop bit-for-bit in every case.

If the domain requires:

- **Floating-point statistics:** define acceptable error bounds and test within a tolerance.
- **Currency with decimals:** use `BigDecimal` with agreed scale and rounding.
- **Huge exact integer sums:** use `BigInteger` or overflow checks.

**Thread safety does not eliminate rounding error.** A bit-level mismatch does not automatically prove a data race; distinguish mathematical properties from concurrency bugs.

### 15.1. Integer Overflow Must Also Be Checked

`IntStream.sum()` returns `int` and can overflow. `LongStream.sum()` can also overflow `long`. `Math.addExact` detects overflow per addition; parallel splitting can affect whether/where an overflow triggers if intermediate sums differ. If an unbounded exact integer sum is required, use `BigInteger`.

## 16. Red Flag #11: Relying on `findAny` or Unordered Ops to Pick the “First” Record

`findFirst()` and `findAny()` share the `Optional<T>` return type yet differ in guarantees:

```java
List<String> ids = List.of("A", "B", "C", "D");

String first = ids.parallelStream()
    .findFirst()
    .orElseThrow(); // A on an ordered List source.

String any = ids.parallelStream()
    .findAny()
    .orElseThrow(); // Could be A, B, C, or D.
```

`findAny` is allowed to return any element to favor parallel execution. Never use it when business rules require “the earliest order chronologically.”

Operations like `limit`, `skip`, `takeWhile`, and `dropWhile` depend heavily on encounter order. Specifically:

- On ordered Streams, `takeWhile(p)` takes **the longest prefix** matching `p`.
- `dropWhile(p)` drops that prefix and keeps the remainder.
- On unordered Streams, the while operations may take/drop any matching subset per contract, losing a clear business cut point.
- `unordered()` relaxes ordering constraints; **it is not a shuffle operation**.

Never add `unordered()` just for speed when correctness depends on “the first element,” “the first N records,” or “the latest window.”

## 17. Red Flag #12: Ignoring Stateful Operation Overhead in Parallel Streams

The following operations often require memory or cross-worker coordination:

| Operation | Why parallel can be expensive | What to check |
| --- | --- | --- |
| `sorted()` | Sorting and merging ordered output | Is full-source sorting truly needed? |
| `distinct()` | Tracking previously seen values | Is encounter order required? |
| `limit(n)` / `skip(n)` | Selecting/skipping prefix in order | Does the source split efficiently? |
| `takeWhile` / `dropWhile` | Finding prefix cutoff point | Is the Stream ordered? |
| `groupingBy` | Merging Maps from branches | Does key skew cause huge merges? |
| `flatMap` with uneven sub-streams | Output count per branch varies | Is there load imbalance? |

Example:

```java
List<Integer> firstTen = IntStream.range(0, 1_000_000)
    .parallel()
    .boxed()
    .sorted()
    .limit(10)
    .toList();
```

Since `IntStream.range` already has encounter order and ascending values, `sorted()` here is usually redundant for **semantics**. A simpler pipeline:

```java
List<Integer> firstTen = IntStream.range(0, 1_000_000)
    .limit(10)
    .boxed()
    .toList();
```

No claim that the second is “always faster” in every environment; the point is **eliminating unnecessary stages before trying parallel optimization**.

### 17.1. `parallel()` Must Not Change Logical Output

When an operation is valid and obeys its contracts, logical output should agree between sequential and parallel runs. Significant data discrepancies point to side effects, non-compliant reductions, source interference, or unwarranted ordering assumptions.

## 18. Red Flag #13: Treating a Worker Exception as an Instant Global Halt

A mapper can throw an exception:

```java
List<Integer> processed = values.parallelStream()
    .map(n -> {
        if (n == 0) {
            throw new IllegalArgumentException("zero is forbidden");
        }
        return 100 / n;
    })
    .toList();
```

On a parallel Stream, multiple partitions may already be scheduled or mid-execution when one task fails. **There is no guarantee all other tasks stop instantaneously** or that prior side effects roll back.

Risks when lambdas perform I/O:

- Some records were already sent/written before another task threw.
- Retrying the entire pipeline may repeat those operations.
- Exceptions may propagate through parallel machinery; never rely on error discovery order or observing one specific failing element.
- Calling `findFirst`/`anyMatch`/`limit` may stop result collection early, yet is not a “transaction rollback switch.”

### 18.1. Distinguishing Recoverable Data Errors from Fatal Failures

When individual records can fail independently, a clean design **models success/failure outcomes** instead of hiding errors and skipping:

```java
public class ParseResultsDemo {
    record ParseResult(String raw, Integer value, String error) {
        boolean ok() { return error == null; }
    }

    static ParseResult parseNumber(String raw) {
        try {
            return new ParseResult(raw, Integer.parseInt(raw), null);
        } catch (NumberFormatException e) {
            return new ParseResult(raw, null, "invalid integer");
        }
    }

    public static void main(String[] args) {
        List<ParseResult> results = List.of("10", "oops", "20")
            .parallelStream()
            .map(ParseResultsDemo::parseNumber)
            .toList();

        results.forEach(System.out::println);
    }
}
```

This self-contained example yields one outcome per input, including error cases. Results pinpoint which records failed without mutating any shared collection.

Never lump exceptions like `OutOfMemoryError`, permission errors, or system failures into “invalid input”; error policy must separate continuable data errors from fatal failures that should halt.

### 18.2. Checked Exceptions and Stream Lambdas

Standard `Function`/`Predicate` interfaces do not declare arbitrary checked exceptions, so I/O code often wraps or maps errors:

```java
.map(path -> {
    try {
        return java.nio.file.Files.size(path);
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
})
```

`UncheckedIOException` preserves the original `IOException` cause, yet does not solve retries, rollbacks, or resource closing automatically. For pipelines with many tasks, evaluate whether parallel I/O actually fits resource limits.

## 19. Red Flag #14: Side Effects Without an Exactly-Once Contract

Example:

```java
orders.parallelStream()
    .forEach(order -> paymentGateway.charge(order));
```

Even if the API gateway supports concurrent calls from multiple threads, charging has **external effects**. If one part fails, **parallel Stream provides no global transaction** to undo charges that already succeeded.

If an operator retries the batch after failure, duplicate charges can happen without idempotency keys. That is a business-architecture issue, not just Java thread safety.

For tasks with unavoidable side effects, design explicitly:

1. Determine the work set with a pure-data pipeline.
2. Validate input data, permissions, and business preconditions.
3. Use idempotency keys/transactions/outbox or a reliable protocol matching the target system.
4. Bound concurrency and track per-task outcomes.
5. Define clear compensation, retry, and error-classification policies.

**No `parallel`, `synchronized`, or `AtomicInteger` keyword automatically guarantees exactly-once external calls.**

## 20. Red Flag #15: Forgetting I/O Resource Lifecycles

A `Stream` returned by `Files.lines(path)` holds an open resource that needs closing:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileStreamSafetyDemo {
    static long countErrors(Path path) throws java.io.IOException {
        try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> line.contains("ERROR"))
                .count();
        }
    }
}
```

`try-with-resources` guarantees releasing the resource when the method exits or throws.

If you add `parallel()`:

```java
try (Stream<String> lines = Files.lines(path)) {
    long errors = lines.parallel()
        .filter(line -> line.contains("ERROR"))
        .count();
    System.out.println(errors);
}
```

you still must keep `try-with-resources`. `count()` or early termination **does not automatically call `close()`** on I/O-backed Streams. Moreover, source splitting and file-decoding costs can prevent parallel execution from improving speed.

### 20.1. Do Not Share an Unsafe Writer Across Workers

```java
// Carefully review the writer's contract and write coordination.
lines.parallel()
    .forEach(line -> writer.write(line + System.lineSeparator()));
```

Many mutable writers are unsuitable for concurrent calls without synchronization; and even with a lock, line order may be scrambled. If output must be **ordered**, processing data first and writing sequentially is often simpler.

## 21. Red Flag #16: Deadlocks, Blocking, and Resource Starvation

Not everything that can run in a parallel Stream should run there. Watch out for:

- Waiting on a lock that another worker needs to finish.
- Blocking indefinitely on `Future.get()`/`join()` within a task dependency graph.
- Running long network I/O without connection limits.
- Nesting parallel pipelines heavily.
- Pairing a small database pool with high parallel task fan-out.
- Mixing thread-bound transaction contexts with worker pools.

A classic danger is each element submitting a new task to the same bounded executor and **waiting** for its result while all executor workers are already busy waiting. That is a *thread starvation deadlock*, common across concurrency models beyond the Stream API.

**Countermeasures:** measure blocking, cap concurrency, avoid cyclic dependencies, set timeouts/cancellation, and consider structured task management or application-controlled executors. Never use `parallelStream()` as a blanket substitute for bounded I/O orchestration.

## 22. Custom `Spliterator` and Broken Source Splitting

Parallel Streams rely heavily on `Spliterator.trySplit()` to divide work. A custom Spliterator violating its contract can cause:

- **Dropped elements** across branches.
- **Duplicate elements** when two branches cover overlapping ranges.
- Wrong order despite declaring `ORDERED`.
- Wrong size despite declaring `SIZED`/`SUBSIZED`.
- Data races when child Spliterators mutate a shared source cursor.

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<Integer> s = List.of(1, 2, 3).spliterator();

System.out.println(s.hasCharacteristics(Spliterator.ORDERED)); // true
System.out.println(s.estimateSize());                         // 3
```

Standard sources like `List.of` already ship proper Spliterators. Avoid writing a custom Spliterator if a built-in source already models your data accurately.

### 22.1. Source `CONCURRENT` Differs from Collector `CONCURRENT`

| Characteristic | Applies to | Meaning |
| --- | --- | --- |
| `Spliterator.CONCURRENT` | Traversed source | Source supports concurrent modification per contract |
| `Collector.Characteristics.CONCURRENT` | Collector | Accumulator accepts concurrent calls on the same container |
| `Gatherer.Integrator.Greedy` (Java 24+) | Integrator | Does not initiate short-circuiting itself |

Never infer one characteristic from another; each has its own contract.

## 23. Stream Gatherers and Parallel Safety (Java 24+)

`Stream.gather(...)` extends Stream with custom intermediate operations. A `Gatherer<T,A,R>` can hold state and emit multiple outputs. Consequently, it can introduce parallel hazards if its **combiner** is inadequate.

Illustrative principle:

```java
// Java 24+, stateful sequential gatherer form.
static java.util.stream.Gatherer<Integer, long[], Long> runningTotal() {
    return java.util.stream.Gatherer.ofSequential(
        () -> new long[] {0L},
        (state, value, downstream) -> {
            state[0] = Math.addExact(state[0], value.longValue());
            return downstream.push(state[0]);
        }
    );
}
```

This is an ordered running total. Splitting the source into two segments means running totals in the second segment **depend on the total of the first segment**. Simply summing the two final states cannot reconstruct every prefix sum accurately.

Hence `ofSequential` is the right choice when no combiner satisfies the required contract.

### 23.1. Greedy and Parallel Are Two Separate Questions

`Gatherer.Integrator.ofGreedy(...)` only states that the integrator **does not itself stop accepting upstream elements**; it may still return `false` once downstream rejects further elements.

Greedy **does not mean** thread-safe, does not supply a combiner, and does not make shared mutable state safe. A gatherer can be **greedy yet sequential**.

**Especially dangerous:** declaring Greedy on an Integrator that actually stops itself at a marker. Stream implementations are permitted to ignore a Greedy Integrator's boolean return value, which can keep a program running past its intended stop condition.

### 23.2. `mapConcurrent` and Virtual Threads

`Gatherers.mapConcurrent(maxConcurrency, mapper)` provides concurrency-bounded mapping using virtual threads. It differs from `parallelStream().map(...)` in execution model and concurrency bounds; mappers still must be right regarding data, thread safety, exceptions, and resources.

Never assume virtual threads automatically make mutable connections or transaction-bound contexts safe to share.

## 24. Testing Correctness: Compare Outcomes, Not Logs

For parallel pipelines, do not rely on `peek` log sequences to verify ordering or invocation counts. Instead, assert **output invariants** over predictable inputs.

### 24.1. Essential Invariants

- `filter` never creates extra elements.
- `map` preserves logical element count in a 1:1 transformation.
- `flatMap` changes element count according to sub-results.
- `distinct` never increases element count.
- `toList()` on an ordered Stream preserves result encounter order.
- Group totals match keys and values regardless of `groupingBy` vs. an appropriate concurrent variant.
- No duplicate/stray/lost elements outside business rules.
- After a terminal operation, the Stream cannot be reused.
- On external failures, retries never cause contract-violating side effects.

### 24.2. Testing Across Diverse Inputs

| Input | Likely exposed bug |
| --- | --- |
| Empty source | Bad identity, `Optional.get` on missing value |
| Single element | Initialization and boundary issues |
| Many duplicate elements | `distinct`, `toMap` merge, mutable keys |
| All items sharing one grouping key | Contention, hot-key handling |
| Negative/large values | Overflow, sign errors, non-associativity |
| Unordered source | Bad assumptions about `findAny`, `limit`, windows |
| Very large size | Scheduling, memory, Spliterator splitting |
| File/I/O reads | Exceptions, resource closing, and retries |
| Repeated runs/forks | Scheduling-sensitive race conditions |

**Warning:** Passing a test 1,000 times without hitting a race **does not prove zero races exist**. Contract analysis and proper concurrency testing/profiling tools remain essential.

## 25. Complete Java 17 Program: Choosing Safe Parallel Execution

The following program is self-contained, runs on Java 17+, and uses **no** side effects inside pipelines. It compares sequential vs. parallel results and groups by region.

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class SafeParallelStreamDemo {

    record Order(String id, String region, long amountVnd, boolean paid) {}

    static List<Order> sample() {
        return List.of(
            new Order("O1", "Bac", 100_000L, true),
            new Order("O2", "Nam",  50_000L, false),
            new Order("O3", "Bac", 200_000L, true),
            new Order("O4", "Trung", 70_000L, true),
            new Order("O5", "Nam",  30_000L, true),
            new Order("O6", "Trung", 10_000L, false)
        );
    }

    static long totalPaidSequential(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();
    }

    static long totalPaidParallel(List<Order> orders) {
        return orders.parallelStream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();
    }

    static Map<String, Long> countsSequential(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }

    static Map<String, Long> countsParallel(List<Order> orders) {
        return orders.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }

    static ConcurrentMap<String, Long> countsConcurrent(
            List<Order> orders) {
        return orders.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingByConcurrent(
                Order::region,
                Collectors.counting()
            ));
    }

    public static void main(String[] args) {
        List<Order> orders = sample();

        long sequentialTotal = totalPaidSequential(orders);
        long parallelTotal = totalPaidParallel(orders);

        Map<String, Long> sequentialCounts = countsSequential(orders);
        Map<String, Long> parallelCounts = countsParallel(orders);
        ConcurrentMap<String, Long> concurrentCounts =
            countsConcurrent(orders);

        List<String> paidIds = orders.parallelStream()
            .filter(Order::paid)
            .map(Order::id)
            .toList();

        System.out.println("Total: " + parallelTotal);
        System.out.println("Paid IDs: " + paidIds);

        if (sequentialTotal != 400_000L) {
            throw new AssertionError("Unexpected sequential total");
        }
        if (parallelTotal != sequentialTotal) {
            throw new AssertionError("Parallel total mismatch");
        }
        if (!parallelCounts.equals(sequentialCounts)) {
            throw new AssertionError("Parallel grouping mismatch");
        }
        if (!concurrentCounts.equals(sequentialCounts)) {
            throw new AssertionError("Concurrent grouping mismatch");
        }
        if (!paidIds.equals(List.of("O1", "O3", "O4", "O5"))) {
            throw new AssertionError("Encounter-order mismatch");
        }

        System.out.println("All checks passed");
    }
}
```

Expected output:

```text
Total: 400000
Paid IDs: [O1, O3, O4, O5]
All checks passed
```

Map implementations may print keys in different orders if printed directly; the code asserts `Map.equals` so it never depends on key iteration order.

### 25.1. Why Is This Program Model-Safe?

- `Order` is an immutable record with immutable fields in this example.
- The `List.of` source is never mutated during traversal.
- `filter` and `mapToLong`/`map` have zero side effects.
- `sum` and `counting` are delegated to terminal operations/collectors.
- `groupingBy` and `groupingByConcurrent` follow their contracts.
- `forEach` is never used to mutate an external Map/List.
- `toList` on an ordered Stream preserves ID order.
- Outcomes are verified with explicit invariants.

**Limitation:** The example chooses small numbers to avoid `long` overflow. For real financial data, enforce range limits and currency rules. A correct parallel pipeline also does not guarantee beating the sequential version in speed.

## 26. JUnit 5 Tests and Property-Based Thinking

If the project uses JUnit 5, you can compare both execution modes across datasets:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ParallelStreamSafetyTest {

    @Test
    void sequentialAndParallelTotalsMatch() {
        List<SafeParallelStreamDemo.Order> data =
            SafeParallelStreamDemo.sample();

        assertEquals(
            SafeParallelStreamDemo.totalPaidSequential(data),
            SafeParallelStreamDemo.totalPaidParallel(data)
        );
    }

    @Test
    void emptyInputHasZeroTotalAndEmptyGroups() {
        List<SafeParallelStreamDemo.Order> empty = List.of();

        assertEquals(0L,
            SafeParallelStreamDemo.totalPaidParallel(empty));
        assertEquals(
            SafeParallelStreamDemo.countsSequential(empty),
            SafeParallelStreamDemo.countsParallel(empty)
        );
    }

    @Test
    void concurrentGroupingHasSameCounts() {
        var data = SafeParallelStreamDemo.sample();

        assertEquals(
            SafeParallelStreamDemo.countsSequential(data),
            SafeParallelStreamDemo.countsConcurrent(data)
        );
    }
}
```

With property-based tests, you can state:

> For any valid list of Orders whose total fits within `long`, the sequential and parallel sum pipelines return the exact same value.

However, tests are **not a mathematical proof** that every lambda is thread-safe. For custom collectors/Spliterators, also verify supplier, combiner, source characteristics, and shared references.

### 26.1. Do Not Use Log Output as a Test Oracle

`peek(System.out::println)` can interleave or be optimized out in some pipelines. Log counts and log ordering are unreliable test oracles. Assert **output data** and defined invariants instead.

## 27. Review Checklist: Which Red Flags Mean Stop Adding `parallel()`?

| Code smell | Risk | Preferred fix |
| --- | --- | --- |
| `parallel().forEach(list::add)` | Concurrent writes to `ArrayList` | `toList()` / `collect` |
| `parallel().peek(cache::put)` | Side effects/races/skipped callbacks | Separate controlled update step |
| `counter[0]++` inside lambda | Data race | `count()` or proper counter design |
| `AtomicInteger` used for indexing | Indices depend on execution schedule | `IntStream.range` with source index |
| `source.remove(...)` during traversal | Interference | Never mutate source inside pipeline |
| `reduce(0, (a,b)->a-b)` | Non-associative / wrong identity | Pick contract-compliant operation |
| `reduce(new ArrayList<>(), ...)` | Mutable identity in reduce | `collect` or `toList` |
| Collector supplier returns static object | Shared state across branches | Supplier creates fresh object |
| `CONCURRENT` collector with `HashMap` | Unsafe accumulator | Fix collector/characteristics |
| `groupingByConcurrent` when per-group order matters | Order not guaranteed | Use order-preserving design |
| `toMap` without merge on duplicate keys | Exception | Add valid merge function |
| Shared `SimpleDateFormat` | Mutable non-thread-safe | `DateTimeFormatter` |
| `ThreadLocal` holding business context | Context not propagated to workers | Pass parameters explicitly |
| `findAny` used to find “first” record | Order not guaranteed | `findFirst` on ordered source |
| `unordered().takeWhile(...)` expecting exact prefix | Wrong semantics | Keep encounter order |
| `sorted()/distinct()/limit()` on huge ordered parallel | State/sync overhead | Re-evaluate design, benchmark |
| Lambda writes DB/charges/mutates external state | No exactly-once/rollback | Separate I/O, idempotency, transactions |
| Unclosed `Files.lines` | Resource leak | `try-with-resources` |
| `parallel()` on source with custom Spliterator | Broken `trySplit` loses/duplicates items | Test source contract |
| Stateful `gather` with wrong combiner | Corrupted output sequence | `ofSequential`/valid combiner |
| `parallel()` on tiny workload | Overhead > work | Measure with JMH, consider sequential |

## 28. Practice Exercises

### Exercise 1: Finding and Fixing a Data Race

Given:

```java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 10000)
    .parallel()
    .forEach(output::add);
```

Explain why `output.size()` is not guaranteed to be 10000 by contract. Rewrite using `boxed().toList()` and verify output size and ordering.

### Exercise 2: Atomic Does Not Guarantee Order

Use `AtomicInteger` to index `List.of("A","B","C","D")` on a parallel Stream. Compare with `IntStream.range(0, list.size()).mapToObj(...)`. Why can the final output preserve encounter order while still containing wrong indices?

### Exercise 3: `reduce` Identity

Compare `reduce(10, Integer::sum)` and `10 + stream.reduce(0, Integer::sum)` under parallel execution. Why can't identity act as “a value added once”?

### Exercise 4: Non-Associative Operations

Find a list of `int`s where reduction using subtraction yields different answers depending on grouping. Explain why a single passing test run cannot prove subtraction is safe.

### Exercise 5: Mutable Reduction

Convert `reduce(new ArrayList<>(), ...)` into `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)`. Explain the difference between `reduce`'s identity and `collect`'s supplier.

### Exercise 6: Parallel Grouping

Generate 1,000 orders with repeated region keys. Compare `groupingBy(..., counting())` and `groupingByConcurrent(..., counting())` using Map equality rather than key print order. Then benchmark with JMH under uniform key distribution vs. all orders sharing a single key.

### Exercise 7: `ThreadLocal` and Authorization

An application stores tenant ID in a request thread's `ThreadLocal` and runs `parallelStream()`. Analyze what can happen on worker threads. Rewrite using an immutable tenant parameter and verify downstream APIs receive the right tenant.

### Exercise 8: Exceptions Mid-Batch I/O

A parallel pipeline calls an external service to update 100 orders. Record 20 fails; 15 updates already succeeded. Why is retrying the whole batch dangerous? Design the write step with idempotency keys and per-record outcomes.

### Exercise 9: Distinguishing Floating-Point Error from Races

Sum `double` values using a loop and a parallel reduction. If the results differ in the last digit, is that enough evidence to conclude a data race? Describe how to verify computations with tolerances and how to handle currency using `BigDecimal`.

### Exercise 10: `findAny` and Encounter Order

On an ordered `List`, compare `parallelStream().findAny()` with `parallelStream().findFirst()`. When business rules require the earliest record, what additional guarantee is needed about source ordering?

### Exercise 11: Side-Effecting Filter

A predicate uses `counter[0]++` to number elements and keep/drop based on index. Why is this broken in parallel processing? Design a fix using source indices or a sequential snapshot depending on requirements.

### Exercise 12: Resources

Write a function counting error lines from `Files.lines(path)` using `try-with-resources`. Try adding `parallel()`; analyze why resource ownership and `close` behavior do not change just by adding one keyword.

### Exercise 13: Custom Gatherer

On JDK 24+, write a Gatherer emitting sequential running totals with `ofSequential`. Explain why you cannot arbitrarily attach a combiner that sums two final states when output includes every prefix sum.

### Exercise 14: Designing a Fair Benchmark

Use JMH to compare sequential vs. parallel summing of squares of even numbers on `int[]`. Pick at least three sizes, verify equal totals, and measure GC allocations. Why can an operation that is faster at one million elements be slower at one thousand elements?

### Exercise 15: Real-System Review

Pick a pipeline that calls a repository or external service. Write a checklist covering thread safety, transactions, idempotency, concurrency limits, timeouts, retries, cancellation, monitoring, and rollback. Then decide whether to use parallel Stream or an explicit task orchestration mechanism.

## 29. Self-Check Questions

- Why does `parallelStream()` not guarantee lambdas run in encounter order?
- Can `toList()` on an ordered parallel Stream preserve output order even if `map` executes out of order?
- How does non-interference differ from stateless behavior?
- Why is `ArrayList.add` inside `parallel().forEach` dangerous?
- Which race does `AtomicInteger` fix, and which ordering requirement does it fail to fix?
- Why is `peek` not a reliable business recording mechanism?
- What can happen when mutating `source` during traversal?
- Why does `reduce` require a neutral identity and an associative operation?
- How does a mutable container in `reduce` differ from `collect`'s supplier?
- What does `Collector.Characteristics.CONCURRENT` mean?
- Does `groupingByConcurrent` guarantee the order of lists inside groups?
- When is `findAny` appropriate, and when is `findFirst` needed?
- Why doesn't `ThreadLocal` automatically propagate context to workers?
- Why is `DateTimeFormatter` usually better than a shared `SimpleDateFormat`?
- When a parallel task throws an exception, do prior side effects roll back automatically?
- Does `Files.lines` close automatically when `count()` is called?
- Why can `parallel()` degrade performance even when outputs are right?
- Why doesn't `Spliterator.CONCURRENT` guarantee a custom collector is safe?
- Why isn't `Gatherer.Integrator.ofGreedy` a thread-safety guarantee?
- Is a `double` result differing by a few bits enough to conclude a data race occurred?

## 30. References

- [Java SE 17 — `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): non-interference, stateless behaviors, side effects, `parallel`, `forEach`, and `forEachOrdered`.
- [Java SE 17 — `Collectors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `groupingBy`, `groupingByConcurrent`, `toMap`, and collector characteristics.
- [Java SE 17 — `Collector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html): supplier, accumulator, combiner, finisher, and identity/associativity constraints.
- [Java SE 17 — `Spliterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): `trySplit`, `ORDERED`, `SIZED`, `SUBSIZED`, and `CONCURRENT`.
- [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `lines` and resource management for I/O Streams.
- [Java SE 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic updates and limits of counter usage.
- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): thread-scoped values and lifecycle management.
- [Java SE 24 — `Gatherer`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): state, combiner, finisher, and safe Gatherer design.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): benchmarking tool for comparing sequential and parallel performance/GC.

**Key Takeaway:** When reading a parallel pipeline, look for **shared mutable state**, **side effects**, **source mutation during traversal**, **execution-order assumptions**, **non-compliant identity/combiners**, **non-thread-safe sources or resources**, and **expensive stateful operations**. Prefer pure data `map`/`filter`, contract-compliant `reduce`, and `collect` managing isolated containers; choose `groupingByConcurrent` only when unordered semantics fit. A pipeline is truly safe only when **results, state, exceptions, resources, and external side effects** are all handled properly—not merely when it runs without throwing errors.
