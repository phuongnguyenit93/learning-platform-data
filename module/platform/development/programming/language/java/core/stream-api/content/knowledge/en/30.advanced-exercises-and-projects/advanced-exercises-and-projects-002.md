# Writing a Custom Collector to Aggregate Multiple Metrics

In real-world projects, a single pass over data often has to produce **several related metrics**: total orders, paid orders, total revenue, min/max values, average, and order counts by region. Writing six or seven separate `stream()` pipelines might still work on a small `List`, but it is unsuitable when the source is very large, single-use, or tied to I/O. A **custom `Collector`** can hold enough intermediate state, update every metric as each element arrives, and build one report object at the end.

This is an advanced hands-on exercise in the **Advanced Exercises and Projects** chapter of the **JAVA_STREAM_API** module. We combine knowledge of lazy pipelines, `filter`, `map`, `reduce`, `collect`, grouping, the Collector contract, `Spliterator`, and parallel processing. Beyond writing standalone runnable Java 8 code, the exercise asks you to reason about **correctness**, **empty data**, **numeric overflow**, **shared state**, **resources**, and **performance**; advanced transformation techniques such as Stream Gatherers are not required to solve this problem.

## 1. Project Problem: Multi-KPI Order Report

Suppose an application receives orders with four attributes:

- `id`: order ID.
- `region`: region code, e.g. `BAC`, `NAM`, or `TRUNG`.
- `amountCents`: monetary amount in the smallest currency unit, of type `long` and non-negative.
- `paid`: payment status, of type `boolean`.

Given the data:

| Order | Region | Amount (cents) | Paid? |
|---|---|---:|---|
| O1 | BAC | 10,000 | Yes |
| O2 | NAM | 5,000 | No |
| O3 | BAC | 30,000 | Yes |
| O4 | NAM | 20,000 | Yes |
| O5 | BAC | 0 | Yes |
| O6 | TRUNG | 4,000 | No |

Required report:

| Metric | Expected Result |
|---|---|
| Total orders | `6` |
| Paid orders | `4` |
| Unpaid orders | `2` |
| Total paid amount | `60_000L` |
| Minimum paid order amount | `0L` |
| Maximum paid order amount | `30_000L` |
| Average paid order amount | `15_000.0` |
| Order count by region | `{BAC=3, NAM=2, TRUNG=1}` |

Business rules to clarify **before** writing the Collector:

1. Order count by region includes **all** orders, even unpaid ones.
2. Total, min, max, and average amounts consider only **paid orders**.
3. If there are **no paid orders**, total amount is 0, but **min/max/average do not exist**, rather than all being 0.
4. A `null` order or `null` region is treated as invalid data; the example will fail fast rather than silently discarding it.
5. To guard against `long` overflow, use `Math.addExact`. Overflowing throws an exception instead of producing a wrong sum.

Defining these rules clearly is just as important as Stream syntax: a fast pipeline that aggregates the wrong set of records is still an unacceptable implementation.

## 2. Why Do We Need a Multi-Metric Collector?

### 2.1. The Simple Approach Traverses the Source Multiple Times

With an in-memory list, you could write:

```java
long orderCount = orders.stream().count();

long paidCount = orders.stream()
        .filter(Order::isPaid)
        .count();

long paidTotal = orders.stream()
        .filter(Order::isPaid)
        .mapToLong(Order::getAmountCents)
        .sum();
```

The snippet assumes an `Order` type and an `orders` source. Each `stream()` call creates a new pipeline to compute **one quantity**. On a re-traversable `List`, this is sometimes very readable and a reasonable choice. However, if you also compute min, max, average, and other statistics, the number of scans multiplies.

More importantly, you cannot invoke two terminal operations on **the same `Stream` instance**:

```java
Stream<Order> source = orders.stream();

long count = source.count();

// WRONG: Stream has already been consumed.
// long paidCount = source.filter(Order::isPaid).count();
```

For a single-use I/O source, recreating the Stream may require reopening files, re-reading data, or may not even be feasible. A multi-metric Collector completes all measurements in **one collection pass**.

### 2.2. Four Design Requirements

Our custom Collector must have:

1. **Sufficient intermediate state** to update all KPIs and merge two partial results.
2. **A function to add one order** into the state without mutating the source data.
3. **A function to combine two states** so it works properly even with parallel streams.
4. **A finisher function** that produces an immutable report without letting the caller mutate internal state.

A key point is **not computing the average on every accumulation step**. Keep only `sum` and `count`, then compute `sum / count` at the final step, because individual averages of two groups are insufficient to compute the combined average when group sizes differ.

## 3. Collector<T, A, R> Type and Its Components

`java.util.stream.Collector<T, A, R>` has three type parameters:

| Symbol | Meaning | In This Project |
|---|---|---|
| `T` | Source element type | `Order` |
| `A` | Mutable accumulation state type | `MetricsAccumulator` |
| `R` | Final result type | `Report` |

A complete Collector has five concepts:

| Component | Responsibility | Implementation Plan |
|---|---|---|
| `supplier` | Create an empty state | `MetricsAccumulator::new` |
| `accumulator` | Accept one `Order`, update state | `MetricsAccumulator::add` |
| `combiner` | Merge two branch results | `MetricsAccumulator::combine` |
| `finisher` | Produce the final report | `MetricsAccumulator::finish` |
| `characteristics` | Declare Collector properties | Do not declare unguaranteed characteristics |

To create the Collector in Java 8:

```java
Collector<Order, MetricsAccumulator, Report> collector =
        Collector.of(
                MetricsAccumulator::new,
                MetricsAccumulator::add,
                MetricsAccumulator::combine,
                MetricsAccumulator::finish);
```

This is the pattern that will be fully defined in section 5. Since `A = MetricsAccumulator` differs from `R = Report`, **do not declare `IDENTITY_FINISH`**. Since the container is ordinary mutable state, **do not declare `CONCURRENT`**. Because numeric results and count Maps do not depend on encounter order, this collection *could* be designed as unordered, yet the example does not need to declare `UNORDERED` to be correct and easy to verify.

## 4. Intermediate State Model

### 4.1. What Data to Store?

`MetricsAccumulator` needs these fields:

```text
orderCount        : long
paidCount         : long
paidCents         : long
minPaidCents      : long (initially Long.MAX_VALUE)
maxPaidCents      : long (initially Long.MIN_VALUE)
regionCounts      : Map<String, Long>
```

**There is no need to store individual orders.** The accumulator only increments counters, adds amounts, updates min/max, and increments per-region counts. Memory grows mainly with the **number of distinct regions**, not linearly with total orders.

### 4.2. State Invariants

After accumulating a valid set of orders:

- `orderCount >= 0` and `paidCount >= 0`.
- `0 <= paidCount <= orderCount`.
- `paidCents` is the sum of `amountCents` of paid orders, within non-overflowing `long` range.
- If `paidCount > 0`, `minPaidCents` and `maxPaidCents` are the true extrema of paid orders.
- If `paidCount == 0`, `Long.MAX_VALUE` or `Long.MIN_VALUE` must never be exposed as real extrema.
- The sum of all values in `regionCounts` equals `orderCount`, assuming counts do not overflow.

These invariants verify a Collector more thoroughly than merely seeing that it "runs".

### 4.3. Why Use Optional for min, max, and average?

For an empty source, or a source with orders where none are paid:

```text
paidCount = 0
paidCents = 0
minPaid   = absent
maxPaid   = absent
average   = absent
```

`OptionalLong` and `OptionalDouble` represent the missing-value state cleanly. Returning `0` from `minPaid` would be semantically wrong when no measurements exist; however, if there is **one paid order with amount 0**, a min of `OptionalLong[0]` is a valid result.

## 5. Complete Java 8 Program: Single collect for Multiple KPIs

The code below can be saved as `MultiMetricCollectorDemo.java` and run on JDK 8 or later. It uses monetary amounts in the smallest unit and accepts only non-negative values. Accumulation functions guard against overflow with `Math.addExact`.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalLong;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class MultiMetricCollectorDemo {

    static final class Order {
        private final String id;
        private final String region;
        private final long amountCents;
        private final boolean paid;

        Order(String id, String region, long amountCents, boolean paid) {
            this.id = Objects.requireNonNull(id, "id");
            this.region = Objects.requireNonNull(region, "region");
            if (amountCents < 0) {
                throw new IllegalArgumentException(
                        "amountCents must not be negative");
            }
            this.amountCents = amountCents;
            this.paid = paid;
        }

        String getId() { return id; }
        String getRegion() { return region; }
        long getAmountCents() { return amountCents; }
        boolean isPaid() { return paid; }
    }

    // A: Intermediate state, mutated only during collection.
    static final class MetricsAccumulator {
        private long orderCount;
        private long paidCount;
        private long paidCents;
        private long minPaidCents = Long.MAX_VALUE;
        private long maxPaidCents = Long.MIN_VALUE;
        private final Map<String, Long> regionCounts = new HashMap<>();

        // Accumulator: accepts one order.
        void add(Order order) {
            Objects.requireNonNull(order, "order");

            orderCount = Math.addExact(orderCount, 1L);
            regionCounts.merge(order.getRegion(), 1L, Math::addExact);

            if (order.isPaid()) {
                paidCount = Math.addExact(paidCount, 1L);
                paidCents = Math.addExact(
                        paidCents, order.getAmountCents());
                minPaidCents = Math.min(
                        minPaidCents, order.getAmountCents());
                maxPaidCents = Math.max(
                        maxPaidCents, order.getAmountCents());
            }
        }

        // Combiner: merges all metrics from the right branch into the left branch.
        MetricsAccumulator combine(MetricsAccumulator right) {
            orderCount = Math.addExact(orderCount, right.orderCount);
            paidCount = Math.addExact(paidCount, right.paidCount);
            paidCents = Math.addExact(paidCents, right.paidCents);

            if (right.paidCount > 0) {
                minPaidCents = Math.min(
                        minPaidCents, right.minPaidCents);
                maxPaidCents = Math.max(
                        maxPaidCents, right.maxPaidCents);
            }

            right.regionCounts.forEach((region, count) ->
                    regionCounts.merge(
                            region, count, Math::addExact));
            return this;
        }

        // Finisher: takes a result snapshot that forbids mutating the internal Map.
        Report finish() {
            OptionalLong min = paidCount == 0
                    ? OptionalLong.empty()
                    : OptionalLong.of(minPaidCents);
            OptionalLong max = paidCount == 0
                    ? OptionalLong.empty()
                    : OptionalLong.of(maxPaidCents);
            OptionalDouble avg = paidCount == 0
                    ? OptionalDouble.empty()
                    : OptionalDouble.of(
                            (double) paidCents / paidCount);

            Map<String, Long> snapshot = Collections.unmodifiableMap(
                    new TreeMap<>(regionCounts));

            return new Report(
                    orderCount, paidCount, paidCents,
                    min, max, avg, snapshot);
        }
    }

    // R: Immutable report DTO after collection completes.
    static final class Report {
        final long orderCount;
        final long paidCount;
        final long paidCents;
        final OptionalLong minPaid;
        final OptionalLong maxPaid;
        final OptionalDouble averagePaid;
        final Map<String, Long> regionCounts;

        Report(long orderCount, long paidCount, long paidCents,
                OptionalLong minPaid, OptionalLong maxPaid,
                OptionalDouble averagePaid,
                Map<String, Long> regionCounts) {
            this.orderCount = orderCount;
            this.paidCount = paidCount;
            this.paidCents = paidCents;
            this.minPaid = minPaid;
            this.maxPaid = maxPaid;
            this.averagePaid = averagePaid;
            this.regionCounts = regionCounts;
        }

        long unpaidCount() {
            return orderCount - paidCount;
        }
    }

    static Collector<Order, MetricsAccumulator, Report>
            metricsCollector() {
        return Collector.of(
                MetricsAccumulator::new,
                MetricsAccumulator::add,
                MetricsAccumulator::combine,
                MetricsAccumulator::finish);
    }

    // Explicit comparison helper to verify parallel results.
    static boolean sameReport(Report a, Report b) {
        return a.orderCount == b.orderCount
                && a.paidCount == b.paidCount
                && a.paidCents == b.paidCents
                && a.minPaid.equals(b.minPaid)
                && a.maxPaid.equals(b.maxPaid)
                && a.averagePaid.equals(b.averagePaid)
                && a.regionCounts.equals(b.regionCounts);
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("O1", "BAC",   10_000L, true),
                new Order("O2", "NAM",    5_000L, false),
                new Order("O3", "BAC",   30_000L, true),
                new Order("O4", "NAM",   20_000L, true),
                new Order("O5", "BAC",        0L, true),
                new Order("O6", "TRUNG",  4_000L, false)
        );

        // Both execution modes must produce equivalent KPIs.
        Report sequential = orders.stream()
                .collect(metricsCollector());
        Report parallel = orders.parallelStream()
                .collect(metricsCollector());

        System.out.println(sequential.orderCount);    // 6
        System.out.println(sequential.paidCount);     // 4
        System.out.println(sequential.unpaidCount()); // 2
        System.out.println(sequential.paidCents);     // 60000
        System.out.println(sequential.minPaid.orElse(-1)); // 0
        System.out.println(sequential.maxPaid.orElse(-1)); // 30000
        System.out.println(
                sequential.averagePaid.orElse(-1));  // 15000.0
        System.out.println(sequential.regionCounts);
        // {BAC=3, NAM=2, TRUNG=1}

        System.out.println(sameReport(sequential, parallel)); // true

        // Completely empty source: no extrema/average.
        Report empty = Collections.<Order>emptyList()
                .stream()
                .collect(metricsCollector());
        System.out.println(empty.orderCount); // 0
        System.out.println(empty.paidCents); // 0
        System.out.println(empty.averagePaid.isPresent()); // false
        System.out.println(empty.minPaid.isPresent()); // false
        System.out.println(empty.regionCounts.isEmpty()); // true

        // Orders exist, but none are paid.
        Report noPaid = Arrays.asList(
                new Order("X1", "BAC", 100L, false))
                .stream()
                .collect(metricsCollector());
        System.out.println(noPaid.orderCount); // 1
        System.out.println(noPaid.paidCount);  // 0
        System.out.println(noPaid.averagePaid.isPresent()); // false
        System.out.println(noPaid.regionCounts.get("BAC")); // 1

        // Custom Collector can serve as a downstream collector for grouping.
        Map<String, Report> reportsByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion, metricsCollector()));
        System.out.println(
                reportsByRegion.get("BAC").paidCount); // 3
        System.out.println(
                reportsByRegion.get("NAM").paidCents); // 20000
    }
}
```

**Key results:** sequential and parallel reports match, both counting six orders and four paid orders, with a total of 60,000 and average of 15,000. With an empty source, `paidCents == 0` while both `averagePaid` and `minPaid` are empty. With a source containing only unpaid orders, order count and per-region counts are still tracked, while paid monetary statistics do not exist.

The example uses a small dataset to test **correctness**, not as a benchmark claiming parallel streams are faster. There is no need to add `CONCURRENT` just because the collection can run on a parallel stream: the framework manages independent accumulators and then invokes the combiner.

## 6. Explaining Each Collector Component

### 6.1. Supplier: Truly Empty State

`MetricsAccumulator::new` creates a fresh object with zeroed counters and an empty `regionCounts`. `Long.MAX_VALUE` and `Long.MIN_VALUE` are purely internal *sentinels* for updating min/max; they **must never be exposed in the report** if no paid order has been seen.

The supplier must never grab a previously used `MetricsAccumulator` from a static field and hand it out to all branches. Doing so can cause two workers to mutate the same state, causing races and violating the collection contract.

### 6.2. Accumulator: Updating Every KPI per Element

For unpaid order `O2`:

```text
orderCount   + 1
regionCounts["NAM"] + 1
paidCount    unchanged
paidCents    unchanged
min/max      unchanged
```

For paid order `O3`, in addition to the first two metrics, the accumulator also does:

```text
paidCount + 1
paidCents + 30000
minPaidCents = min(minPaidCents, 30000)
maxPaidCents = max(maxPaidCents, 30000)
```

Do not use `forEach` to update a shared external `Report` object outside the pipeline. Mutating intermediate state is the Collector's responsibility, with clear ownership and combination boundaries.

### 6.3. Combiner: Do Not Merge Only the Total Amount

When merging two states, **all** metrics must be merged:

| Field | How to Merge |
|---|---|
| `orderCount` | Add counts from left and right branches |
| `paidCount` | Add paid counts |
| `paidCents` | Add paid totals |
| `minPaidCents` | Take min across branches that have at least one paid order |
| `maxPaidCents` | Take max across branches that have at least one paid order |
| `regionCounts` | Merge Maps and sum counts for matching keys |

If you forget to combine `regionCounts`, the program may appear "correct" sequentially yet lose groups or counts in parallel. If you merge averages directly, results can be wrong when partitions differ in size.

**Why can we mutate the left state and return it?** In non-concurrent mutable reduction, the framework manages each container's lifecycle according to the Collector contract. The combiner is permitted to reuse the left branch state as the merged result, as long as no illegal sharing occurs and the result stays valid.

### 6.4. Finisher: Turning Temporary State into Meaningful Output

The finisher computes the average only after sum and count are complete, and converts min/max sentinels into `OptionalLong`. It also creates a **`TreeMap` copy** wrapped with `Collections.unmodifiableMap`:

```java
Map<String, Long> snapshot = Collections.unmodifiableMap(
        new TreeMap<>(regionCounts));
```

Benefit of copying: `Report` does not hold a direct reference to the accumulator's mutable Map. `TreeMap` also provides ascending key order for presentation; **this is a result-design choice**, not a prerequisite for parallel collection.

Because the finisher performs an actual conversion from `MetricsAccumulator` to `Report`, do not declare `Collector.Characteristics.IDENTITY_FINISH`.

## 7. Proving Identity, Associativity, and Equivalence Contracts

A custom Collector must produce correct results under every valid way the framework splits and combines data.

### 7.1. Identity

Let `E` be a fresh accumulator from the supplier. It has zero counters, an empty Map, and no extrema yet. For any valid state `A`:

```text
combine(A, E) is equivalent to A
```

In code, adding counts and amounts with 0 leaves the result unchanged; an empty Map adds no keys; and because `E.paidCount == 0`, min/max are untouched.

The symmetric case `combine(E, A)` also yields the same semantics: totals/counts are copied via addition, min/max take values from `A` if `A` has paid orders, and count Maps are merged.

### 7.2. Associativity

Suppose `A`, `B`, and `C` are accumulated states for three independent partitions. We require:

```text
combine(combine(A, B), C)  ≈  combine(A, combine(B, C))
```

Counts and totals use `long` addition, min/max use extremum selection, and the Map sums per-key counts. For **valid non-overflowing data**, regrouping does not alter any metric. Every addition is checked with `Math.addExact` so it fails explicitly if results exceed `long` range.

**Note on averages:** we never combine branch averages. For example:

```text
Branch A: [10]         sum=10, count=1, average=10
Branch B: [20, 30]     sum=50, count=2, average=25

WRONG: (10 + 25) / 2 = 17.5
RIGHT: (10 + 50) / (1 + 2) = 20
```

Thus, intermediate state must retain full `sum` and `count` until the finisher step.

### 7.3. Equivalence

Different accumulation strategies must produce equivalent `Report` objects across **every KPI**, not just total revenue. For example, if two reports have the same `paidCents` but different `regionCounts`, they are **not equivalent** under the project requirements.

`sameReport` in the example compares every metric and the resulting Map. On small datasets with integer inputs, comparing `OptionalDouble` is reasonable; in systems averaging many floating-point values, bit-for-bit equality should not always be demanded because summation order can affect rounding error.

### 7.4. Why Not Declare CONCURRENT?

`MetricsAccumulator` uses `HashMap` and mutates several `long` fields directly. If multiple workers call `add` simultaneously on **one** accumulator, that code is not thread-safe.

However, when calling `orders.parallelStream().collect(metricsCollector())`, the Collector **does not carry the `CONCURRENT` characteristic**. The framework allocates **separate containers per branch** and combines them; it does not require every field or Map inside the accumulator to support concurrent updates on the same instance.

`UNORDERED` should only be declared if results do not depend on encounter order. The example's metrics are order-independent, yet omitting that characteristic still keeps the collector correct; withholding `CONCURRENT` remains the essential decision.

## 8. Handling Empty Sources and Non-Existent Metrics

There are two distinct cases:

| Case | `orderCount` | `paidCount` | `paidCents` | `averagePaid` | `regionCounts` |
|---|---:|---:|---:|---|---|
| No orders at all | 0 | 0 | 0 | `OptionalDouble.empty()` | Empty Map |
| One unpaid order in BAC | 1 | 0 | 0 | `OptionalDouble.empty()` | `{BAC=1}` |
| One paid order of amount 0 | 1 | 1 | 0 | `OptionalDouble[0.0]` | By region |
| Two paid orders of 100 and 300 | 2 | 2 | 400 | `OptionalDouble[200.0]` | By region |

A dashboard may want to display `—` when there is no average, or intentionally call `orElse(0.0)`. Even so, **presentation policy should not erase "no data" information** in the statistics layer if reports must distinguish it from an actual average of 0.

For groups, `groupingBy` only creates keys for groups with at least one parent element. If there are no orders in region `TAY`, `reportsByRegion` will not automatically insert a `TAY` key with an empty `Report`; the reporting layer must backfill absent groups if business logic requires them.

## 9. Extending the Project: Variants and Data Policies

### 9.1. Adding Unpaid Order Count

There is no need for a separate mutable field if:

```java
long unpaidCount = report.orderCount - report.paidCount;
```

Since `paidCount` is a subset of `orderCount`, we can compute this metric in `Report.unpaidCount()`. Avoid storing derived metrics if they could become inconsistent during updates or combining.

### 9.2. Payment Rate

If you want the ratio of paid orders:

```java
OptionalDouble paidRate = report.orderCount == 0
        ? OptionalDouble.empty()
        : OptionalDouble.of(
                (double) report.paidCount / report.orderCount);
```

When the source is empty, the rate is undefined. Computing the rate inside the finisher or in a `Report` method avoids directly merging unweighted ratios.

### 9.3. Adding Paid Total by Region

You can add:

```java
Map<String, Long> paidCentsByRegion = new HashMap<>();
```

In the accumulator, for paid orders only:

```java
paidCentsByRegion.merge(
        order.getRegion(),
        order.getAmountCents(),
        Math::addExact);
```

In the combiner, iterate over the right branch's Map and `merge(region, amount, Math::addExact)` into the left Map. In the finisher, create an immutable snapshot for the result. Adding any new metric Map **requires updating both accumulator and combiner completely**; modifying only the accumulator risks wrong results on parallel streams.

### 9.4. Negative Amounts, Refunds, and Currency Conversion

The original example rejects `amountCents < 0`. If an application supports refunds, it is not just a matter of flipping a check: you need explicit rules for negative sums, extrema, paid counts, and how adjustment transactions are identified.

If there are **multiple currencies**, never sum all `amountCents` directly into a single total. Group by currency, convert using an approved exchange rate, or define a unified accounting unit before aggregating.

### 9.5. Multiple Quantiles or Top-N

Median, percentiles, top-N, and exact distinct counts may require more complex state. For instance, to compute an exact median, a collector may have to retain far more data than just `(sum, count, min, max)`. Do not assume all KPIs share the same memory complexity: some metrics compute online in constant state, while others require storing many elements.

## 10. Precision Issues and Invalid Data

### 10.1. Integer Overflow

`long` does not have an infinite range. Using `Math.addExact` detects when a sum or count exceeds `Long.MAX_VALUE`. When that happens, the collector throws `ArithmeticException` instead of silently returning a wrapped negative number.

For large monetary volumes or calculations exceeding `long` bounds, you can design an accumulator using `BigInteger` or `BigDecimal`. Each choice carries different performance costs and rounding policies.

### 10.2. Average as double vs. Exact Decimal Currency

`(double) paidCents / paidCount` represents a binary floating-point number and may introduce rounding. It is fine for many display statistics, though not always suitable for financial rules requiring exact rounding under a fixed policy.

Example switching to `BigDecimal` in the finisher:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Optional;

Optional<BigDecimal> exactAverage = paidCount == 0
        ? Optional.empty()
        : Optional.of(BigDecimal.valueOf(paidCents)
                .divide(BigDecimal.valueOf(paidCount),
                        2, RoundingMode.HALF_UP));
```

This snippet illustrates code inside `MetricsAccumulator`, where `paidCents` and `paidCount` are in scope. The `scale = 2` and `HALF_UP` rule must be chosen according to business requirements; if statistics are in cents, the result is also in cents and does not automatically convert to dollars/VND.

### 10.3. Nulls and Corrupted Elements

Do not assume null elements are automatically removed by the Stream. On datasets containing null, `MetricsAccumulator.add` currently uses `Objects.requireNonNull(order)` to **reject explicitly**; it does not silently skip bad records.

If business logic requires dropping null records before reporting:

```java
Report result = orders.stream()
        .filter(Objects::nonNull)
        .collect(metricsCollector());
```

This makes counts reflect **valid orders after filtering**, not total raw input records. If you need an **invalid record count**, model it inside the accumulator or in a separate validation pass with its own statistics. Never silently filter records while reporting "total records received".

## 11. Reading from an I/O Source While Still Closing Resources

One advantage of a multi-metric collector is computing multiple KPIs **while streaming through a file**, without holding every order in memory. However, a collector **does not automatically close** an I/O-backed Stream.

Conceptual example:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    Report report = lines
            .map(line -> parseOrder(line)) // Parser function provided by the app.
            .collect(metricsCollector());
}
```

This snippet illustrates usage inside a class where `parseOrder(String)` and `path` are already defined; it is not a standalone program. `Files.lines` must sit inside `try-with-resources` even after calling the terminal operation `collect`. If parsing fails or file reading throws an exception, the source is still closed upon exiting `try`.

For large sources, consider:

- Can the parser analyze each line independently, or does it need state from previous lines?
- How many region keys does the accumulator retain? If key count is huge, `regionCounts` can consume significant memory.
- Are there file descriptor or other resource limits? `parallel()` does not replace resource management.
- Does the result require ordering? The current collector only computes statistics and does not need to preserve order.

## 12. When to Use Built-In Collectors Instead of Writing Your Own?

A custom Collector fits best when you need **multiple quantities under consistent data rules**, a single pass, and a cohesive report object. However, do not write one when built-in APIs already express the requirement cleanly.

| Problem | Usually Simpler Tool |
|---|---|
| Only summing amounts | `mapToLong(...).sum()` or `Collectors.summingLong(...)` |
| Only counting orders | `count()` or `Collectors.counting()` |
| Need count/sum/min/max/average of **one numeric field** | `summarizingLong(...)` |
| Counting orders by region | `groupingBy(..., counting())` |
| Total amount by region | `groupingBy(..., summingLong(...))` |
| Combining **two** independent collectors | `Collectors.teeing(...)` since Java 12 |
| Multiple metrics, one consistent DTO, custom state | `Collector.of(...)` |

### 12.1. Comparison with summarizingLong

`Collectors.summarizingLong` produces `LongSummaryStatistics`, computing count, sum, min, max, and average of **one numeric field**:

```java
java.util.LongSummaryStatistics stats = orders.stream()
        .filter(Order::isPaid)
        .collect(Collectors.summarizingLong(
                Order::getAmountCents));
```

This is great if you only need monetary statistics for paid orders. However, it does not simultaneously count **total orders**, **unpaid orders**, and **orders per region** in one result. Furthermore, `LongSummaryStatistics.getAverage()` returns 0 when count is 0; to distinguish missing data, you must check `getCount()`.

### 12.2. Comparison with teeing

Java 12 added `Collectors.teeing(downstream1, downstream2, merger)` to run **two** collectors on the same input and merge both final results into one:

```java
// Java 12+, illustrating just two quantities:
Map.Entry<Long, Long> totals = orders.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Order::getAmountCents),
                (count, sum) ->
                        new java.util.AbstractMap.SimpleImmutableEntry<>(
                                count, sum)));
```

This computes the count of **all** orders and total amount of **all** orders without filtering paid status. When multiple metrics need different sub-rules, you can nest `teeing`, though type complexity grows quickly. A custom Collector is usually clearer when you have a unified KPI model with multiple counters and Maps.

## 13. Testing by Manual Splitting and Combining

Do not test only sequential examples. A combiner bug may remain hidden until parallel execution runs. Simulate splitting the source into two branches:

```java
// Snippet running inside MultiMetricCollectorDemo from section 5.
MetricsAccumulator left = new MetricsAccumulator();
MetricsAccumulator right = new MetricsAccumulator();

left.add(new Order("A", "BAC", 100L, true));
right.add(new Order("B", "NAM", 200L, true));

Report merged = left.combine(right).finish();

MetricsAccumulator sequential = new MetricsAccumulator();
sequential.add(new Order("A", "BAC", 100L, true));
sequential.add(new Order("B", "NAM", 200L, true));
Report onePass = sequential.finish();

System.out.println(sameReport(merged, onePass)); // true
```

Continue testing merges with an empty state, three-branch merges under two different parenthesizations, branches with only unpaid orders, and branches with overlapping group keys. Manual tests catch bugs, though they **do not prove correctness** for every dataset; you must reason from the accumulator's mathematical contract.

### 13.1. Essential Test Case Matrix

| Test Case | What Must Hold |
|---|---|
| Completely empty source | Counts and totals are 0; extrema/average absent; Map empty |
| One paid order of amount 0 | Paid count = 1; min/max/average equal 0 |
| One unpaid order | Total orders = 1, paid = 0, region Map still increments |
| All orders in one region | Region count equals total orders |
| Orders across multiple regions | Sum of Map counts equals total orders |
| Reversed list order | KPIs and Map must be equivalent |
| Sequential vs. parallel runs | Equivalent results on valid data |
| Combining with empty state | Result unchanged |
| Combining three states in two parenthesizations | Equivalent results |
| Negative amount or null region | Rejected per example policy |
| Total amount exceeding `long` | Throws `ArithmeticException` instead of negative overflow |

For a project with automated tests, use JUnit and generate varied small combinations; for performance testing, measure separately and avoid treating "test passed" as proof that a parallel collector is always faster.

## 14. Common Mistakes When Writing Multi-Metric Collectors

| Mistake | Consequence | Fix |
|---|---|---|
| Computing average by averaging two accumulators | Wrong when branches have different sizes | Keep sum and count; divide in finisher |
| Combiner merges only sum, skipping Map or count | Lost data on parallel streams | Merge every state field |
| Supplier returns the same static object | Branches mutate shared container | Create fresh state on every supplier call |
| Marking `CONCURRENT` for mutable `HashMap` and `long` | Data race when workers update concurrently | Never declare `CONCURRENT` unless accumulator is thread-safe |
| Marking `IDENTITY_FINISH` when `A != R` | Framework may skip finisher | Omit that characteristic |
| Exposing sentinel min/max when count = 0 | Report displays fake extrema | Convert to empty Optional |
| Calling `toList` to keep all orders just to compute KPIs | Unnecessary memory usage | Accumulate metrics directly |
| Using `int` sum for large data | Numeric overflow | Use an appropriate type, `Math.addExact`, or BigInteger |
| Calling `getAsDouble()` on empty Optional | `NoSuchElementException` | Check `isPresent` or apply an explicit default policy |
| Using `parallelStream()` and assuming it is faster | Overhead, contention, costly splitting | Benchmark on real data |
| Reading files with `Files.lines` without closing | File descriptor leak | Use `try-with-resources` |
| Filtering bad records without reporting dropped count | KPIs misinterpret data scope | Define validation policy and quality metrics |

## 15. Guided Advanced Exercises and Solutions

### Exercise 1. Add Paid Order Rate

**Prompt:** Using existing fields, implement a `paidRate()` method returning `OptionalDouble`. If the source is empty, do not default to 0.

**Reference solution:**

```java
OptionalDouble paidRate() {
    return orderCount == 0
            ? OptionalDouble.empty()
            : OptionalDouble.of((double) paidCount / orderCount);
}
```

Place this method in `Report`. The accumulator needs no new field, because the rate is derived from two existing counters.

### Exercise 2. Add Paid Total Amount by Region

**Prompt:** Add `Map<String, Long> paidCentsByRegion` to the accumulator and update it across all phases.

**Guidance:** In `add`, add amount only if `order.isPaid()`. In `combine`, merge the entire Map from the right branch using `merge`. In `finish`, build an immutable snapshot. Remember to test a region that has only unpaid orders: depending on policy, it may be absent from the **paid amount** Map while still appearing in the **order count** Map.

### Exercise 3. Count Data Errors Instead of Throwing

**Prompt:** Replace the policy of rejecting `null` `Order` with reporting both `invalidCount` and `validCount`.

**Hint:** If the input Stream may contain null elements, move the null check into `add` instead of calling `Objects.requireNonNull` upfront. For a null order, increment `invalidCount` and `return`; for a valid order, update KPIs. `combine` must also sum `invalidCount`. Clearly define whether `orderCount` means valid orders or total records read, and keep that consistent across every step.

### Exercise 4. Build a Collector for Exam Scores

**Prompt:** Replace `Order` with `StudentResult(studentId, className, score)`. Compute submission count, total score, lowest score, highest score, average, and submission count per class.

**Solution guidance:** Use state containing `count`, `sum`, `min`, `max`, and `Map<className, count>`; write `add`, `combine`, and `finish` similarly. Decide how to handle invalid scores, missing data, and rounding rules before implementing.

### Exercise 5. Spot the Average-Combining Bug

Two branches have data: A = `[10]`, B = `[20, 30]`. A combiner merges average A and average B by taking the mean of the two averages.

**Answer:** The wrong result is `(10 + 25) / 2 = 17.5`, whereas the true average is `(10 + 20 + 30) / 3 = 20`. You must combine `(sum=10,count=1)` with `(sum=50,count=2)` and then divide `60/3`.

### Exercise 6. Checking Parallel Compatibility

**Prompt:** Is `Collector.Characteristics.CONCURRENT` required for `orders.parallelStream().collect(metricsCollector())` to work?

**Answer:** No. A standard Collector can run in parallel using separate containers and the combiner. Declaring `CONCURRENT` with an unsynchronized `HashMap`, mutable `long` fields, and unsynchronized updates would introduce data races.

### Exercise 7. Designing a Measurable Performance Requirement

**Prompt:** Define how to compare the custom collector against running multiple independent pipelines.

**Guidance:** Use the same dataset and KPI rules, verify correctness first, perform warm-up, measure multiple runs across representative sizes, distinguish in-memory data from I/O, and observe both memory allocation and CPU load. For serious Java benchmarks, use JMH. Never assume a custom collector is always faster: if data is very small or built-in stats suffice, the simplicity of `summarizingLong` may be worth more.

## 16. Project Completion Checklist

A multi-metric Collector can be considered well-designed when you can answer these questions:

1. **Are the data source and each KPI's scope clearly defined?** Count all records or only valid ones? Sum all orders or only paid ones?
2. **Does the intermediate state retain enough information?** Have sum, count, and data needed to derive all metrics been kept?
3. **Does the supplier create fresh, empty, independent state?**
4. **Does the accumulator process one element per published rules without external side effects?**
5. **Does the combiner merge every field and satisfy associativity?**
6. **Does the finisher return a result decoupled from the internal mutable Map and handle empty sources properly?**
7. **Has arithmetic been checked?** Any overflow, decimal precision loss, or division by zero?
8. **Have sequential, parallel, empty source, single-element, bad data, and duplicate group keys been tested?**
9. **Are the declared characteristics accurate?** In particular, never tag `CONCURRENT` or `IDENTITY_FINISH` carelessly.
10. **Is a custom Collector truly needed?** Would `counting`, `summingLong`, `summarizingLong`, `groupingBy`, or `teeing` already cover the requirement?

**Conclusion:** Writing a custom Collector to aggregate multiple metrics is not just calling `Collector.of`. The core problem is choosing a **mergeable state**, retaining enough information for every KPI, guaranteeing **identity – associativity – equivalence**, and decoupling the final result from mutable state. When designed well, the same Collector works on sequential Streams, parallel Streams, or as a downstream collector of `groupingBy`, eliminating redundant data passes while keeping precision and resources under control.
