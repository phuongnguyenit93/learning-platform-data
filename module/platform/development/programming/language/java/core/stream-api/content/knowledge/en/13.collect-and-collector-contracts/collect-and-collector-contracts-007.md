# Creating Custom Collectors with `Collector.of`

> **Chapter:** Collect Mechanism and Collector  
> **Module:** `JAVA_STREAM_API` — declarative data processing in Java Stream API via lazy pipelines, `filter`, `map`, `reduce`, and `collect`; exploring grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers while recognizing limits around state, resources, and performance.

In real data processing, the desired result is not always a `List`, `Map`, or simple numeric sum. For example, an order report may need to **count orders**, **sum amounts**, **find min and max values**, and **compute a rounded average** in a single pass. We can design an intermediate accumulation object and use `Collector.of(...)` to clearly describe how to create, update, merge, and convert that object into the final result.

After this lesson, you will be able to:

- Explain the roles of `supplier`, `accumulator`, `combiner`, and `finisher` in `Collector.of`.
- Create collectors that return the accumulation container itself or produce a result of a different type.
- Ensure collector correctness for both sequential and parallel pipelines.
- Choose the right `Characteristics` and avoid bugs from shared state, faulty merging, or unclear empty-stream handling.

## 1. When is `Collector.of` needed?

Built-in collectors handle common problems well:

| Goal | Built-in API |
| --- | --- |
| Collect into a list | `Collectors.toList()`, `Stream.toList()` (Java 16+) |
| Count elements | `Collectors.counting()`, `Stream.count()` |
| Compute primitive numeric statistics | `Collectors.summarizingInt(...)`, `summarizingLong(...)`, `summarizingDouble(...)` |
| Group elements | `Collectors.groupingBy(...)` |
| Join strings | `Collectors.joining(...)` |
| Combine results of two collectors | `Collectors.teeing(...)` (Java 12+) |

If these APIs already express the requirement completely, prefer them. `Collector.of` is useful when **the accumulation object and result have a custom structure**, such as multi-metric statistics over `BigDecimal`, building specialized indices, collecting with a finishing step, or needing control over how intermediate results are merged.

`collect` is a **terminal operation**: it triggers traversal of the pipeline's source. `Collector.of` is only a **factory method creating a Collector**; calling `Collector.of` does not traverse data yet. Traversal happens when that collector is used in `stream.collect(collector)`.

## 2. Type parameters and the two overloads of `Collector.of`

A `Collector<T, A, R>` has three type parameters:

- `T`: the Stream's input element type.
- `A`: the **intermediate accumulation state** type, typically a mutable object.
- `R`: the **final result** type after collection.

Two key forms of the `Collector.of` factory method:

```java
// A is also the final result type (no separate finisher needed):
static <T, R> Collector<T, R, R> of(
        Supplier<R> supplier,
        BiConsumer<R, T> accumulator,
        BinaryOperator<R> combiner,
        Collector.Characteristics... characteristics);

// Intermediate state A is converted into result R:
static <T, A, R> Collector<T, A, R> of(
        Supplier<A> supplier,
        BiConsumer<A, T> accumulator,
        BinaryOperator<A> combiner,
        Function<A, R> finisher,
        Collector.Characteristics... characteristics);
```

The signatures above are shown to explain the types; compiling requires the interfaces in `java.util.function` and `Collector` in `java.util.stream`. The `characteristics` parameter group is varargs, so it can be omitted when no extra characteristics need to be declared.

| Component | Functional interface | Responsibility |
| --- | --- | --- |
| `supplier` | `Supplier<A>` | Creates **a new, independent accumulation container**. |
| `accumulator` | `BiConsumer<A, T>` | Incorporates one element `T` into accumulation container `A`. |
| `combiner` | `BinaryOperator<A>` | Merges **two accumulation containers** into one valid `A`. |
| `finisher` | `Function<A, R>` | Converts state `A` into result `R`. |
| `characteristics` | Constants in `Collector.Characteristics` | Declares properties so Stream can pick an appropriate collection strategy. |

Visualizing the process:

```text
  Stream<T>                    when splitting source for
  element T                    multi-branch processing
      │                          ┌────────────┐
      ▼                          │ supplier A │──┐
 supplier() → A                  └────────────┘  │
      │                          ┌────────────┐  ├─► combiner(A, A) → A
 accumulator(A, T) ...           │ supplier A │──┘           │
      │                          └────────────┘              │
      └───────────── A ───────────────────────────────────────┘
                             │
                             ▼
                         finisher(A)
                             │
                             ▼
                         Result R
```

`combiner` is part of the collector contract even if you only call sequential `stream()`. When running in parallel, the implementation typically creates multiple separate `A` states, accumulates partially, and merges them via `combiner`. Thus, a collector must be designed properly for **both splitting and merging**.

## 3. Small example: collecting into a list with the finisher-less overload

To see the first three components clearly, let's write a collector simulating adding elements to an `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> result = List.of("Java", "Stream", "API").stream()
        .collect(Collector.of(
                () -> new ArrayList<String>(),  // supplier
                ArrayList::add,                  // accumulator
                (left, right) -> {               // combiner
                    left.addAll(right);
                    return left;
                }
        ));

System.out.println(result); // [Java, Stream, API]
```

In this example:

1. `supplier` creates a **new list** whenever an accumulation container is needed.
2. `accumulator` appends each element to the list currently being accumulated.
3. `combiner` appends the elements of the right list into the left list, then **returns the merged list**.

The three-function overload produces a result of the same type as the accumulation container (`A = R`) and the collector has the `IDENTITY_FINISH` characteristic. It **does not automatically make the list immutable**: `result` is a modifiable `ArrayList`. If you only need to collect a list, using a built-in collector is usually more concise and maintainable.

## 4. Complete example: computing a revenue report with `Collector.of`

Requirement: across **paid** orders, compute order count, total amount, minimum amount, maximum amount, and average amount rounded to two decimal places. Use `BigDecimal` to avoid floating-point errors when summing money; the average uses `HALF_UP` rounding.

The program below runs standalone on Java 17+. Save as `CustomCollectorDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Collector;

public class CustomCollectorDemo {
    record Order(String id, boolean paid, BigDecimal amount) {}

    // Final result: immutable, explicitly representing metrics
    // that do not exist when the input set is empty.
    record SalesReport(
            long count,
            BigDecimal total,
            Optional<BigDecimal> min,
            Optional<BigDecimal> max,
            Optional<BigDecimal> average
    ) {}

    // Intermediate state: each supplier creates a separate object.
    static final class Accumulator {
        private long count;
        private BigDecimal total = BigDecimal.ZERO;
        private BigDecimal min;
        private BigDecimal max;

        void add(Order order) {
            Objects.requireNonNull(order, "order");
            BigDecimal amount = Objects.requireNonNull(
                    order.amount(), "amount");

            count++;
            total = total.add(amount);

            if (min == null || amount.compareTo(min) < 0) {
                min = amount;
            }
            if (max == null || amount.compareTo(max) > 0) {
                max = amount;
            }
        }

        Accumulator combine(Accumulator other) {
            count += other.count;
            total = total.add(other.total);

            if (other.min != null
                    && (min == null || other.min.compareTo(min) < 0)) {
                min = other.min;
            }
            if (other.max != null
                    && (max == null || other.max.compareTo(max) > 0)) {
                max = other.max;
            }

            return this;
        }

        SalesReport finish() {
            Optional<BigDecimal> average = count == 0
                    ? Optional.empty()
                    : Optional.of(total.divide(
                            BigDecimal.valueOf(count),
                            2,
                            RoundingMode.HALF_UP));

            return new SalesReport(
                    count,
                    total,
                    Optional.ofNullable(min),
                    Optional.ofNullable(max),
                    average);
        }
    }

    static Collector<Order, ?, SalesReport> salesCollector() {
        return Collector.of(
                Accumulator::new,
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("D-01", true, new BigDecimal("120.00")),
                new Order("D-02", false, new BigDecimal("500.00")),
                new Order("D-03", true, new BigDecimal("80.00")),
                new Order("D-04", true, new BigDecimal("200.00"))
        );

        SalesReport report = orders.stream()
                .filter(Order::paid)
                .collect(salesCollector());

        System.out.println("Order count: " + report.count());
        System.out.println("Total amount: " + report.total());
        System.out.println("Min: " + report.min().orElseThrow());
        System.out.println("Max: " + report.max().orElseThrow());
        System.out.println("Average: " + report.average().orElseThrow());

        SalesReport parallelReport = orders.parallelStream()
                .filter(Order::paid)
                .collect(salesCollector());
        System.out.println("Parallel matches sequential: "
                + report.equals(parallelReport));

        SalesReport emptyReport = orders.stream()
                .filter(o -> false)
                .collect(salesCollector());
        System.out.println("Empty: " + emptyReport.count()
                + " / " + emptyReport.average());
    }
}
```

Output:

```text
Order count: 3
Total amount: 400.00
Min: 80.00
Max: 200.00
Average: 133.33
Parallel matches sequential: true
Empty: 0 / Optional.empty
```

### Why separate `Accumulator` and `SalesReport`?

- `Accumulator` has state that mutates per element; thus each `add` only needs to update a few fields and each `combine` only merges two sets of statistics.
- `SalesReport` is an immutable record, never exposing a mutable accumulation container. `finisher` rounds **once when creating the report**, rather than rounding after every addition; this preserves associativity for total amount.
- `Optional<BigDecimal>` explicitly indicates `min`, `max`, and `average` are **absent** when there are no orders. `count = 0` and `total = 0` are valid results for an empty set.
- Order `D-02` is excluded because it was filtered out by `filter(Order::paid)` before the terminal operation.

In the example, every `amount` is non-null; if source data permits missing amounts, define a policy to **filter beforehand** or throw an error. `Objects.requireNonNull` surfaces data bugs explicitly instead of silently treating missing amounts as 0.

## 5. Correctness contracts: identity and associativity

Writing a collector that works sequentially is not enough. Java Stream can split the source into chunks, accumulate separately, and merge in various ways. The collector must satisfy the **identity and associativity contracts**.

### Identity: an empty accumulation container must be neutral

The container created by `supplier.get()` must represent **zero elements collected yet**. For `Accumulator` in the example:

```text
count = 0
total = 0
min = none yet
max = none yet
```

Merging an accumulated state `a` with a fresh empty state must produce a result equivalent to the original `a`:

```text
combine(a, empty)  ≈  a
```

`combine` in the example only adds `0` to count/total and ignores empty `min/max`, so it satisfies that requirement. This is **equivalence in result**, not necessarily the exact same object by `==`.

### Associativity: splitting and merging must not alter the result

If the source has three segments `X`, `Y`, `Z`, merging `(X + Y) + Z` and `X + (Y + Z)` must produce **equivalent results**:

```text
combine(combine(Ax, Ay), Az)
             ≈
combine(Ax, combine(Ay, Az))
```

When each state holds `count`, `total`, `min`, and `max`, adding counts, adding `BigDecimal`s, and picking min/max are proper merge operations. Because `BigDecimal` sums exact values during accumulation and only rounds `average` in `finisher`, merging does not depend on where the source was split in this example.

**Pitfall to avoid:** if you compute the average of two branches and then average those two averages, the result is wrong when branches have different element counts:

```text
Branch A: [10, 20]     → average = 15, count = 2
Branch B: [100]        → average = 100, count = 1

Wrong:   (15 + 100) / 2 = 57.5
Correct: (10 + 20 + 100) / 3 ≈ 43.33
```

Instead of storing a rounded average and merging it, **store `sum` and `count`**, and only compute `sum / count` inside `finisher`.

### Do not drop the right branch's state

```java
// WRONG: combiner drops the right branch's result.
(left, right) -> left

// CORRECT for a list accumulator:
(left, right) -> {
    left.addAll(right);
    return left;
}
```

A collector with a broken combiner can still sometimes give the "right" result sequentially, because the implementation may not need to merge branches. When run in parallel, data is easily lost or results become inconsistent.

## 6. `Collector.Characteristics` and their practical meaning

`Collector.of` allows declaring characteristics via `Collector.Characteristics`.

| Characteristic | Meaning | Condition to declare properly |
| --- | --- | --- |
| `IDENTITY_FINISH` | The accumulation container itself can be used as the result, needing no substantive conversion | `A` and `R` are compatible, and finisher is truly the identity. |
| `UNORDERED` | Result does not depend on source elements' encounter order | Business logic accepts equivalent results regardless of input order. |
| `CONCURRENT` | Allows multiple threads to call accumulator concurrently on **one** accumulation container | The container and all update operations must be safe under concurrent access. |

### `IDENTITY_FINISH`

The finisher-less overload of `Collector.of` uses the accumulation container as the result. In the list example in section 3, `A` is also `R`, so `IDENTITY_FINISH` is appropriate.

For the `Accumulator -> SalesReport` report, **do not declare `IDENTITY_FINISH`**: Stream must execute `Accumulator::finish` to construct the record and compute the average. Declaring it wrongly could let the implementation skip the finisher and trigger type errors when receiving the result.

### `UNORDERED`

The report contains only `count`, `sum`, `min`, `max`, and `average`, so with `BigDecimal` computed per the contract in the example, the result values **do not depend on encounter order**. You may declare `UNORDERED` if desired:

```java
Collector<Order, ?, SalesReport> unorderedSummary = Collector.of(
        Accumulator::new,
        Accumulator::add,
        Accumulator::combine,
        Accumulator::finish,
        Collector.Characteristics.UNORDERED
);
```

The snippet above uses `Order`, `Accumulator`, and `SalesReport` defined in `CustomCollectorDemo`; it must be placed where those types are in scope. `UNORDERED` **does not mean** Java must randomly scramble data. It simply states the collector's result does not depend on encounter order.

Do not mark `UNORDERED` on a collector when you need to guarantee a list in source order, ordered string joining, picking the first element, or any structure with ordering semantics.

### `CONCURRENT`

Do not confuse **a collector usable in `parallelStream()`** with **a collector having the `CONCURRENT` characteristic**. For a non-concurrent collector, Stream can allocate independent `Accumulator` instances for parallel branches and merge them with the combiner. Plain mutable fields in `Accumulator` from section 4 still fit that model.

If declaring `CONCURRENT`, `accumulator` must handle multiple threads updating **the exact same state A**. For example, `count++` is not atomic; updating `min` and `max` also needs proper coordination. Using a single `AtomicLong` just for count is not enough to guarantee the whole collector is correct if other fields still suffer contention/races.

For a collector declaring `CONCURRENT` without `UNORDERED`, Stream may only accumulate concurrently on a single container appropriately when the source has no encounter-order requirement. Do not add characteristics merely hoping for a speedup; prove the contract and benchmark performance.

## 7. Shared state, non-interference, and data sources

### Each `supplier` call must create new state

```java
// WRONG: sharing one single list for every supplier invocation.
List<String> shared = new java.util.ArrayList<>();
var badCollector = Collector.of(
        () -> shared,
        List<String>::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

If `supplier` returns the same object, branches can mutate the list simultaneously, and the combiner could even merge a list into itself, causing duplicated data or concurrency errors. `supplier` must create a **new, independent container**:

```java
// Better: each supplier call gets its own list.
() -> new java.util.ArrayList<String>()
```

In the order example, `Accumulator::new` provides that exact behavior. A `Collector` can be reused multiple times on different Streams as long as it holds no shared state mutated outside the collection lifecycle.

### Do not mutate data during collect

Collector callbacks should not modify the source collection, depend on external counters, or use side effects without a clear contract. With parallel Stream sources, callback invocation order does not necessarily match source order. Keep the data to be aggregated inside `A`, updated via `accumulator` and `combiner`.

For instance, instead of incrementing a `globalCount` variable inside a `filter` or `peek` lambda, increment `count` inside the accumulation state if that is a reported metric. This keeps processing sound across Stream branch splitting.

### One Stream has only one collection lifecycle

```java
// After collect, a Stream object is consumed.
// Stream<Order> source = orders.stream();
// SalesReport a = source.collect(salesCollector());
// SalesReport b = source.collect(salesCollector()); // Invalid.
```

To generate two reports from a `List` source, call `orders.stream()` anew for each report. If the source is tied to an I/O resource or single-read source, choosing a collector that aggregates multiple metrics in one pass avoids re-traversing and must follow resource-closing rules.

## 8. Comparison with other `collect` forms and `reduce`

There are two forms of calling `collect` that are easily confused:

```java
// 1) Takes a Collector<T, A, R>:
R result = stream.collect(collector);

// 2) Three-argument form: directly returns a result container R.
R result2 = stream.collect(supplier, accumulator, combiner);
```

These are illustrative signatures. In the three-argument form of **`Stream.collect`**, `combiner` has type **`BiConsumer<R,R>`** and merges by side effect; in `Collector.of`, `combiner` has type **`BinaryOperator<A>`** and must **return** the merged container. The `Collector.of` form also supports a separate `finisher` and declaring characteristics, making it convenient for reusable collectors.

Example using three-argument `Stream.collect` to gather a list:

```java
List<String> values = List.of("A", "B", "C").stream()
        .collect(
                java.util.ArrayList::new,
                java.util.List::add,
                java.util.List::addAll
        );
// [A, B, C]
```

If you only need to add an immutable value or perform reduction via a simple associative operator, `reduce` is usually clearer:

```java
long total = java.util.stream.LongStream.of(4, 5, 6).sum(); // 15
```

`Collector.of` fits **mutable reduction** with a dedicated accumulation container; there is no need to write a custom collector to replace a simple `sum()` or `Collectors.joining()`. When you only want to tweak the final result of an existing collector, `Collectors.collectingAndThen(...)` is also worth considering.

## 9. Common errors

| Error | Consequence | Fix |
| --- | --- | --- |
| `supplier` returns the same shared container | Branches mutate data together, risking duplicates/lost data | Create a new object on every supplier call. |
| `combiner` only returns `left`, ignoring `right` | Data loss when multiple branches exist | Merge completely and return the result container. |
| Merging two branch averages with a simple average | Wrong when branches differ in size | Merge `sum` and `count`, compute average in finisher. |
| Rounding money in `accumulator` before summing | Result depends on how source is split | Compute with `BigDecimal`, round at finishing step. |
| Declaring `IDENTITY_FINISH` though `A` differs from `R` | Finisher may be skipped, returning wrong type | Do not use this characteristic on collectors with a converting finisher. |
| Declaring `CONCURRENT` when container is not thread-safe | Data races, wrong statistics | Remove `CONCURRENT` or design contract-compliant concurrent accumulation. |
| Declaring `UNORDERED` for order-dependent results | Result order may change | Keep ordering characteristics when business logic requires it. |
| Using `null` for data without a rule | `NullPointerException` or wrong report | Filter, fail fast, or represent absence with Optional per policy. |
| Reusing the same Stream after `collect` | `IllegalStateException` | Create a new Stream from a reusable source. |

## 10. Self-check

**Question 1.** In `Collector<T,A,R>`, why can `A` and `R` be different?

**Answer:** `A` is the accumulation container that needs to be mutated during traversal; `R` is the final result created by `finisher`. For example, `Accumulator` holds mutable state while `SalesReport` is an immutable record.

**Question 2.** Why can a collector using `ArrayList` as its accumulation container still collect on `parallelStream()` even though `ArrayList` is not thread-safe?

**Answer:** As long as `CONCURRENT` is not declared and the supplier creates separate containers, Stream can accumulate into independent containers and use the combiner to merge them. Using `parallelStream()` does not mean the accumulator must run concurrently on a single container.

**Question 3.** Given branch A with two values `10, 20` and branch B with one value `100`, is merging via `(avgA + avgB)/2` correct?

**Answer:** No. The overall average is `(10 + 20 + 100)/3 ≈ 43.33`, different from `57.5`. You must merge sum and count first.

**Question 4.** Should a Collector building a `StringBuilder` and then calling `toString()` to return `String` declare `IDENTITY_FINISH`?

**Answer:** No. `A = StringBuilder`, `R = String`; the `finisher` step converts the result type.

**Question 5.** If the Stream is empty, what must `supplier` and `finisher` of the report in section 4 produce?

**Answer:** The empty state has `count = 0`, `total = 0`, and no `min/max` yet; `finisher` returns `SalesReport` with `Optional.empty()` for `min`, `max`, and `average`. Never invent fake extrema.

## Takeaways

- `Collector.of` expresses **create state → accumulate elements → merge states → finish result**.
- `supplier` must create a new container; `accumulator` updates per element; `combiner` merges completely; `finisher` converts `A` into `R`.
- **Identity** and **associativity** contracts keep results right regardless of branch splitting and merge order.
- `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` are commitments with execution consequences—declare them only when genuinely valid.
- For multi-metric business aggregations, prefer independent accumulation state, explicit empty-set handling, and rounding at the finishing step; use built-in collectors when they already express the requirement sufficiently.
