# Avoiding Multiple Source Traversals and Designing Single-Pass Aggregation

In the **Java Stream API**, a report often needs multiple metrics at once: record count, total amount, min/max values, count of transactions matching a condition, and per-group statistics. The easiest code to write is sometimes opening a separate stream for each metric. However, if the source is large, has a CPU-heavy normalization step, or can only be read **once** such as a file or I/O stream, that approach can repeat unnecessary work or be impossible.

This lesson belongs to the **Performance and Memory** chapter of the **JAVA_STREAM_API** module. We will distinguish “re-traversing data” from “reusing an already-consumed `Stream`”, design **a single terminal operation aggregating multiple metrics**, recognize when `summarizingLong`, `teeing`, `groupingBy`, or `Collector.of` is appropriate, and weigh precision, memory, lazy evaluation, parallelization, and performance measurement.

> **Practical rule:** If metrics share a source and data scope, consider computing them in **one logical collection pass**. However, never sacrifice correctness or clarity solely to reduce `stream()` calls; compare on a real workload.

## 1. Understanding “multiple source traversals” properly

With a `List<Long>`, the following runs validly because **each `stream()` creates a new Stream**:

```java
import java.util.List;

List<Long> values = List.of(10L, 20L, 30L, 40L);

long count = values.stream().count();
long sum = values.stream().mapToLong(Long::longValue).sum();
long above20 = values.stream().filter(n -> n > 20).count();

System.out.println(count);   // 4
System.out.println(sum);     // 100
System.out.println(above20); // 2
```

Here there are three separate terminal operations. On a repeatable source, this is **not an API error**, yet `map`, `filter`, data reading, or expensive computations may be repeated. Moreover, results across passes might **no longer reflect the same data snapshot** if the collection is modified between calculations.

Conversely, the following is **wrong** because it tries to reuse **the same Stream object**:

```java
import java.util.stream.Stream;

Stream<Integer> numbers = Stream.of(1, 2, 3);
long count = numbers.count();

// Wrong: Stream has already been consumed by a terminal operation.
// int sum = numbers.mapToInt(Integer::intValue).sum();
// Typically throws IllegalStateException.
```

Two scenarios to distinguish:

| Scenario | Valid? | Cost/consequence |
| --- | --- | --- |
| Calling `list.stream()` multiple times | Yes, if the source supports re-traversal | May re-process the same data and transformation steps. |
| Calling multiple terminal operations on the **same Stream** | No | A Stream can only be operated on once; may throw `IllegalStateException`. |
| Re-reading `Files.lines(path)` by **reopening the file** | Possible, when a new source can be opened and closed properly | Repeated I/O and parsing; file contents may have changed. |
| Calling `collect` once with multiple downstream collectors | Yes | One logical source pipeline, though each downstream still performs its own work. |

### “Single pass” does not mean every lambda is guaranteed to run exactly once

Streams can optimize traversal, e.g., `count()` on a `SIZED` source may not execute every `peek`. Short-circuiting operations like `findFirst` can stop early. Therefore, “single pass” in this lesson means **designing one pipeline and one terminal operation to compute metrics from the same element stream**, not guaranteeing callback schedules, thread counts, or low-level memory touches.

## 2. State the real problem before choosing an API

Suppose we have validated transactions, each with:

- `team`: responsible team, non-`null`.
- `amount`: integer amount in the **smallest currency unit** (e.g., cents), non-negative.
- `paid`: whether paid or not.
- `late`: whether processed late or not.

We want a report showing:

| Metric | Calculation scope |
| --- | --- |
| Total transaction count | **All** transactions. |
| Paid transaction count | Only transactions with `paid == true`. |
| Total paid amount | Only paid transactions. |
| Min/max paid amount | Only paid transactions; empty if no data. |
| Late paid transaction count | Transactions that are both `paid` and `late`. |
| All metrics above per team | Every team appearing in the source. |

Key point: metrics **do not necessarily share the same predicate**. If we filter `paid` upfront, we can no longer compute **total transaction count**, and a team with only unpaid transactions vanishes from the report.

### Pipeline sketch

```text
Stream<Sale>
    |
    +--> classifier: Sale::team
              |
              +--> downstream:
                       total transaction count
                       paid transactions: count / sum / min / max
                       paid & late transactions: count
              |
              +--> immutable per-team result
    |
    +--> Map<String, TeamReport>
```

To start, use standard collectors whenever they express the requirement; write a custom collector only when logic genuinely demands more control.

## 3. Simple case: `summaryStatistics` instead of multiple terminal operations

If you only need `count`, `sum`, `min`, `max`, and `average` for a numeric field, the Stream API already includes a summary operation:

```java
import java.util.IntSummaryStatistics;
import java.util.List;

List<Integer> values = List.of(10, 20, 30, 40);

IntSummaryStatistics stats = values.stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 100
System.out.println(stats.getMin());     // 10
System.out.println(stats.getMax());     // 40
System.out.println(stats.getAverage()); // 25.0
```

This is a **single terminal operation** `summaryStatistics()` on `IntStream`. On `Stream<T>`, the matching collector lets you compose inside `groupingBy`:

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;

List<Long> amounts = List.of(10L, 20L, 30L, 40L);

LongSummaryStatistics stats = amounts.stream()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(stats.getSum());   // 100
System.out.println(stats.getCount()); // 4
```

| Source type | Statistics operation | Result |
| --- | --- | --- |
| `IntStream` | `summaryStatistics()` | `IntSummaryStatistics` |
| `LongStream` | `summaryStatistics()` | `LongSummaryStatistics` |
| `DoubleStream` | `summaryStatistics()` | `DoubleSummaryStatistics` |
| `Stream<T>` | `collect(summarizingInt/Long/Double(mapper))` | Corresponding statistics type |

**Limitations:** `LongSummaryStatistics` is a **mutable** object. Both `sum` and `getAverage()` have numeric type limits; `long` sums can overflow, and average returns `double` rather than exact decimal currency.

On an empty source, `getCount() == 0`, `getSum() == 0`, `getAverage() == 0.0`, while `getMin() == Long.MAX_VALUE` and `getMax() == Long.MIN_VALUE`. Those two extrema are only **initial sentinel values**, not observed data. Reports should represent **missing min/max** explicitly.

## 4. `Collectors.teeing`: two aggregations on the same pipeline

`Collectors.teeing` (Java 12+) takes two downstream collectors and a result merger function:

```java
Collectors.teeing(downstreamA, downstreamB, merger)
```

Every element entering the `teeing` collector is fed to **both downstreams**. At the end, `merger` combines the two results. It is useful when you need **two different kinds of aggregation** without reopening the source.

```java
import java.util.List;
import java.util.stream.Collectors;

record CountAndSum(long count, long sum) {}

CountAndSum report = List.of(10L, 20L, 30L).stream()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Long::longValue),
        CountAndSum::new
    ));

System.out.println(report); // CountAndSum[count=3, sum=60]
```

This example shows the syntax; for a single numeric field, `summarizingLong` already gives count and sum in one statistics object. `teeing` shines when the two branches have **different semantics**, such as total count alongside statistics for a subset.

### Two branches with different filter conditions

```java
import java.util.List;
import java.util.stream.Collectors;

record NumberReport(long all, long even) {}

NumberReport report = List.of(1, 2, 3, 4, 5, 6).stream()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.filtering(
            n -> n % 2 == 0,
            Collectors.counting()
        ),
        NumberReport::new
    ));

System.out.println(report); // NumberReport[all=6, even=3]
```

`Collectors.filtering` (Java 9+) forwards only matching elements to its inner downstream. Thus the `all` branch receives **every element**, while `even` counts only even numbers. Moving `.filter(n -> n % 2 == 0)` **before `collect`** drops odd elements from both branches so `all` is no longer the total input count.

**Remember:** `teeing` maintains **two accumulator states**, not one magical free state. It avoids repeating the source and upstream transforms, yet each downstream still performs its own work.

## 5. Grouping and aggregating in one pass

`groupingBy(classifier, downstream)` combines **grouping** with **per-group statistics** in a single terminal operation. You do not need separate `filter` passes per team to compute count, sum, min, and max repeatedly.

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

record Entry(String team, long amount) {}

List<Entry> entries = List.of(
    new Entry("API", 100L),
    new Entry("UI",  300L),
    new Entry("API", 200L)
);

Map<String, LongSummaryStatistics> byTeam = entries.stream()
    .collect(Collectors.groupingBy(
        Entry::team,
        Collectors.summarizingLong(Entry::amount)
    ));

System.out.println(byTeam.get("API").getCount()); // 2
System.out.println(byTeam.get("API").getSum());   // 300
System.out.println(byTeam.get("UI").getMax());    // 300
```

Each element is routed by the classifier to **one group**, and that group's downstream updates its statistics. Accumulated memory scales with **group count and retained summary state**, rather than retaining all elements per group like `groupingBy(team, toList())`.

However, `groupingBy` creates keys only for groups **that appeared**. If the system must also display teams with zero transactions, supplement from the team catalog with empty values per report rules instead of assuming the map has every key.

## 6. Complete example: multi-metric team report in one terminal operation

The following example uses **Java 17+** for `record`, `teeing`, `filtering`, and `Map.copyOf`. Inputs are assumed validated with non-null `team` and non-negative `amount`; production code needs an explicit policy for invalid records.

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.OptionalLong;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class OnePassTeamReport {
    record Sale(
        String team,
        String id,
        long amount,
        boolean paid,
        boolean late
    ) {}

    record TeamReport(
        long allCount,
        long paidCount,
        long paidAmount,
        OptionalLong minimumPaid,
        OptionalLong maximumPaid,
        long latePaidCount
    ) {}

    static Map<String, TeamReport> summarize(List<Sale> sales) {
        Collector<Sale, ?, LongSummaryStatistics> paidStats =
            Collectors.filtering(
                Sale::paid,
                Collectors.summarizingLong(Sale::amount)
            );

        Collector<Sale, ?, Long> latePaidCount =
            Collectors.filtering(
                sale -> sale.paid() && sale.late(),
                Collectors.counting()
            );

        Collector<Sale, ?, TeamReport> byTeamCollector =
            Collectors.teeing(
                Collectors.counting(),
                Collectors.teeing(
                    paidStats,
                    latePaidCount,
                    (stats, lateCount) -> new TeamReport(
                        0L, // Replaced with allCount in outer merger.
                        stats.getCount(),
                        stats.getSum(),
                        stats.getCount() == 0L
                            ? OptionalLong.empty()
                            : OptionalLong.of(stats.getMin()),
                        stats.getCount() == 0L
                            ? OptionalLong.empty()
                            : OptionalLong.of(stats.getMax()),
                        lateCount
                    )
                ),
                (allCount, partial) -> new TeamReport(
                    allCount,
                    partial.paidCount(),
                    partial.paidAmount(),
                    partial.minimumPaid(),
                    partial.maximumPaid(),
                    partial.latePaidCount()
                )
            );

        return sales.stream()
            .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(Sale::team, byTeamCollector),
                Map::copyOf
            ));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("API", "A-1", 1200L, true,  false),
            new Sale("API", "A-2",  800L, true,  true),
            new Sale("API", "A-3",  500L, false, true),
            new Sale("UI",  "U-1", 2000L, true,  true),
            new Sale("UI",  "U-2",  700L, false, false),
            new Sale("OPS", "O-1",  300L, false, true)
        );

        Map<String, TeamReport> report = summarize(sales);

        TeamReport api = report.get("API");
        System.out.println(api.allCount());            // 3
        System.out.println(api.paidCount());           // 2
        System.out.println(api.paidAmount());          // 2000
        System.out.println(api.minimumPaid().orElseThrow()); // 800
        System.out.println(api.maximumPaid().orElseThrow()); // 1200
        System.out.println(api.latePaidCount());       // 1

        TeamReport ops = report.get("OPS");
        System.out.println(ops.allCount());            // 1
        System.out.println(ops.paidCount());           // 0
        System.out.println(ops.minimumPaid().isEmpty()); // true
    }
}
```

Processing flow:

1. **The source creates only one Stream**: `sales.stream()`.
2. `groupingBy(Sale::team, ...)` partitions elements into groups by `team`.
3. The `counting()` branch counts **all** transactions in the team.
4. The `filtering(Sale::paid, summarizingLong(...))` branch computes statistics only for paid transactions.
5. The `filtering(sale -> sale.paid() && sale.late(), counting())` branch counts paid and late transactions.
6. The `teeing` mergers assemble an immutable `TeamReport`.
7. `collectingAndThen(..., Map::copyOf)` seals the output map as unmodifiable.

**Note on expression:** Nesting two `teeing` collectors works correctly, yet can get verbose. As requirements add more metrics or complex business rules, a `Collector.of` with a dedicated accumulator is often easier to read and control in cost.

**Empty cases:** `OPS` still appears because it has a transaction, though none are `paid`; hence `paidCount == 0` and min/max use `OptionalLong.empty()`. If `sales` is completely empty, the output map is empty too.

**Immutability:** `Map.copyOf` makes the map unmodifiable; `TeamReport` holds only primitives and `OptionalLong`, so no mutable accumulator leaks. Do not assume `Map.copyOf` preserves key iteration order.

## 7. When multiple metrics depend on each other: `Collector.of`

For many metrics, a custom collector can accumulate directly into **one state object** instead of two or three separate `teeing` branches. `Collector.of` fits when you want explicit supplier, accumulator, combiner, and finisher logic.

Java 17+ example reusing `Sale` and `TeamReport` from the previous section. The following are **additional members** placed inside `OnePassTeamReport`:

```java
static final class Accumulator {
    long allCount;
    long paidCount;
    long paidAmount;
    long latePaidCount;
    long minPaid = Long.MAX_VALUE;
    long maxPaid = Long.MIN_VALUE;

    void add(Sale sale) {
        allCount++;
        if (sale.paid()) {
            paidCount++;
            paidAmount += sale.amount();
            minPaid = Math.min(minPaid, sale.amount());
            maxPaid = Math.max(maxPaid, sale.amount());
            if (sale.late()) {
                latePaidCount++;
            }
        }
    }

    Accumulator combine(Accumulator other) {
        allCount += other.allCount;
        paidCount += other.paidCount;
        paidAmount += other.paidAmount;
        latePaidCount += other.latePaidCount;
        minPaid = Math.min(minPaid, other.minPaid);
        maxPaid = Math.max(maxPaid, other.maxPaid);
        return this;
    }

    TeamReport finish() {
        return new TeamReport(
            allCount, paidCount, paidAmount,
            paidCount == 0L
                ? OptionalLong.empty() : OptionalLong.of(minPaid),
            paidCount == 0L
                ? OptionalLong.empty() : OptionalLong.of(maxPaid),
            latePaidCount
        );
    }
}

static Collector<Sale, Accumulator, TeamReport> metrics() {
    return Collector.of(
        Accumulator::new,
        Accumulator::add,
        Accumulator::combine,
        Accumulator::finish
    );
}
```

Replace the downstream `byTeamCollector` in the previous example with `metrics()`:

```java
Map<String, TeamReport> report = sales.stream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingBy(Sale::team, metrics()),
        Map::copyOf
    ));
```

Here each element in a group passes through **one accumulator** to update all metrics. That cuts nested `teeing` complexity, though it **increases verification responsibility** for the collector author.

### Combiner correctness laws

`Collector.of` needs more than just an accumulator. In parallel execution, Stream can create **multiple independent Accumulators** and merge them via combiner. Merging must satisfy **associativity** with the empty state as **identity**:

```text
combine(combine(A, B), C)  ≡  combine(A, combine(B, C))
combine(empty, A)         ≡  A
combine(A, empty)         ≡  A
```

Merging `count`, `sum`, `min`, and `max` as shown works when values stay within `long` range without external interference. However, `long` can **overflow silently**, so if exact sums beyond `long` are required, enforce bounds or use `BigInteger`/`BigDecimal`.

**Do not** declare `Collector.Characteristics.CONCURRENT` for this `Accumulator`: its `long` fields are updated without synchronization and do not support concurrent `add` calls on **one** accumulator. Normal collectors still work on parallel streams by allocating per-branch accumulators and merging properly. Also do not declare `IDENTITY_FINISH`, since the mutable state is transformed into `TeamReport`.

### When not to write a custom collector

If you only need min/max/count/sum/average of one field, built-in `summarizingLong` is **simpler and less error-prone**. If adding just one conditional metric, `teeing` is usually easier to understand. Only invest in writing and testing a custom collector when requirements are complex enough or measurements show tangible benefits.

## 8. Single-read sources: `Files.lines`

For file data, each reopen/reread costs I/O and risks observing **different file contents**. Suppose a file contains **one integer amount per line**, already validated against source format.

```text
100
200
300
400
```

Multiple metrics can be computed in one terminal operation:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LongSummaryStatistics;
import java.util.stream.Stream;

public class FileStatistics {
    static LongSummaryStatistics readOnce(Path path)
            throws IOException {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> !line.isBlank()) // Java 11+
                .mapToLong(Long::parseLong)
                .summaryStatistics();
        }
    }
}
```

For the sample content, count = 4, sum = 1,000, min = 100, max = 400, average = 250.0. `Files.lines` is a stream backed by an I/O resource, so use **`try-with-resources`**. Terminal operations **do not replace `close()`**.

This is **fail-fast** error handling for bad data: `Long.parseLong` throws `NumberFormatException` on malformed lines. If business rules require continuing past invalid lines, model a `Valid/Rejected` result type and collect rejected records in the same pass, instead of adding a `filter` that hides errors.

**Do not use `Files.lines` as a general-purpose CSV parser**: quoted commas, embedded newlines, and complex encodings need a proper parser. A file can also change while being read; a single-pass pipeline **does not automatically create an atomic snapshot** of the file.

## 9. Separating “one source pass” from “one computation”

These designs have distinct traits:

| Design | Logical passes over source | Notable state/memory |
| --- | --- | --- |
| `list.stream().filter(...).count()` and `list.stream().mapToLong(...).sum()` | Two independent pipelines | May repeat filtering/mapping and traversal. |
| `list.stream().collect(summarizingLong(...))` | One pipeline | One `LongSummaryStatistics`. |
| `collect(teeing(counting(), filtering(...), merger))` | One pipeline | Two downstream state objects. |
| `collect(groupingBy(key, summarizingLong(...)))` | One pipeline | Map and statistics object per key. |
| `collect(groupingBy(key, toList()))`, then summarizing each list | One source pipeline **plus extra pass over group lists** | Retains all elements inside lists. |
| `sorted().collect(...)` | One declarative pipeline | May need to buffer/sort all data before emitting results. |
| `distinct().collect(...)` | One declarative pipeline | Needs state to track seen elements. |

Thus, **one terminal operation does not guarantee `O(1)` memory**, nor does it guarantee no internal buffering. `sorted`, `distinct`, `groupingBy(..., toList())`, and element-retaining collectors can still consume substantial memory despite reading the source once.

If data is stored in an intermediate collection for testing or reprocessing, that can also be an **intentional choice**. The goal is not eliminating every pass, but avoiding **expensive, unnecessary** repetition.

## 10. Memory mindset: summary state or storing all data?

When input has `n` elements and `g` distinct groups:

| Result to retain | Typical state magnitude |
| --- | --- |
| Whole-source count, sum, min, max | `O(1)` for a fixed metric count. |
| Per-group count/sum/min/max | `O(g)` when each group keeps only a few numbers. |
| All records per group `groupingBy(..., toList())` | `O(n + g)` references/containers, plus original data objects. |
| Filter then `toList()` | `O(k)` for `k` retained elements; can approach `O(n)`. |
| `sorted()` | May require `O(n)` buffer depending on source/implementation. |
| `distinct()` | May retain state proportional to distinct value count. |

`O(...)` expressions describe growth trends, not exact byte promises. Object headers, boxing, map resizing, parallel partitions, and GC cause actual memory usage to vary.

A grouped `HashMap` can still be huge if key count **approaches element count**. Thus switching from `toList` to `summarizingLong` cuts memory when group count is small, yet does not solve very high cardinality. When data exceeds RAM, consider **batching, off-heap/external state, or distributed processing**, not just adding `.parallel()`.

## 11. When both valid and invalid records are needed

If a pipeline includes parsing/validation, “single pass” can use an intermediate **success-or-failure** result type:

```text
Source -> parseAndValidate -> Result<T>
                               |
                               +-- Valid<T>
                               |
                               +-- Invalid(reason)
                                     |
                            teeing(validCollector,
                                   errorCollector,
                                   Report::new)
```

The benefit is **each row is parsed once**, while `teeing` keeps both valid report data and rejection reasons. By contrast, using:

```text
source.stream().filter(this::isValid).map(this::parse).collect(...)
source.stream().filter(this::isInvalid).map(this::explain).collect(...)
```

may repeat validation/parsing and is impossible on single-use sources. Even so, **you do not need to materialize all `Result<T>` values**: feed them straight into appropriate downstream collectors.

If business rules require storing every rejected record for reconciliation, error-list memory still scales with error count. Single-pass reading **does not eliminate real storage needs**: batching, writing errors to a quarantine sink, or bounded storage may be needed.

## 12. Lazy evaluation, short-circuiting, and side effects

Intermediate operations like `map`, `filter`, and many transforms are **lazy**: only a terminal operation triggers on-demand processing. Never use `peek` or `map` to count how many elements were actually visited:

```java
import java.util.List;

long count = List.of(1, 2, 3)
    .stream()
    .peek(System.out::println)
    .count();

System.out.println(count); // 3
// No guarantee peek prints all three elements.
```

With a sized source, `count()` can optimize without running stages that cannot affect the count. `findFirst`, `findAny`, `anyMatch`, and `limit` can **short-circuit**, skipping the rest of the source.

Therefore:

- Never put DB writes, email sends, or business counter updates inside `peek`.
- Never expect `map` to run once per element if the terminal operation can elide work.
- Never modify the source inside `filter` or `forEach` while the pipeline runs (*non-interference*).
- Never use an external `ArrayList` with `parallel().forEach(list::add)` instead of `collect`.

**Single-pass aggregation** is business-correct only if collectors and mappers avoid out-of-contract side effects.

## 13. Parallel streams can help, but are not free

With `parallelStream()`, a regular collector can create independent accumulators and **merge** them via its combiner. Addition, min, and max merge accurately when identity, associativity, and numeric range hold.

```java
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;
import java.util.stream.LongStream;

LongSummaryStatistics stats = LongStream.rangeClosed(1, 100_000)
    .parallel()
    .boxed()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(stats.getCount()); // 100000
System.out.println(stats.getSum());   // 5000050000
```

This snippet is arithmetically valid, yet `.parallel()` should not be slapped onto every range. In fact, `LongStream.rangeClosed(...).summaryStatistics()` avoids boxing and is cleaner. When mappers are cheap or sources small, splitting, scheduling, and merging overhead can exceed useful work.

**Never share a single accumulator** in a custom collector: the supplier must create fresh state, and the combiner must merge properly. Never declare `CONCURRENT` unless the accumulator safely supports concurrent writes from multiple threads to the same state. If metrics depend on encounter order, re-examine combining logic and any `UNORDERED` choice.

For `double` sums, merge order can introduce rounding differences; a “slightly different result in the last few bits” does not necessarily indicate a bug. Use acceptable tolerances and business rules when verifying correctness.

## 14. Performance measurement: is one pass actually faster?

Reducing source traversals usually pays off when pipelines have **parsing, complex filtering, CPU-heavy mapping, or I/O**. Yet if the source is a small array and the JVM optimizes very simple loops well, `teeing` or a custom collector can have more overhead than multiple plain pipelines.

Measure with a reproducible experiment:

1. **Variant A — multiple passes**: open a fresh stream per metric on the same immutable list.
2. **Variant B — single `summarizingLong`**: when the five built-in metrics suffice.
3. **Variant C — single `teeing` or custom collector**: when two or a group of metrics have different predicates.
4. Keep **the same dataset, same filter/parse rules, and same business output**. Verify correctness before comparing times.
5. Test small, medium, and large datasets; try few vs. many groups and uniform vs. skewed key distributions.
6. Use **JMH** with warmup, multiple measurements/forks, result consumption, and record JDK, CPU, cores, heap, and GC.

Table template **awaiting real measured numbers**:

| Workload | Multiple streams (ms/op) | One-pass collectors (ms/op) | Allocation (B/op) | Notes |
| --- | --- | --- | --- | --- |
| 1,000 records, light mapper | Measure in practice | Measure in practice | Measure in practice | Overhead may dominate. |
| 1,000,000 records, light mapper | Measure in practice | Measure in practice | Measure in practice | Check memory bandwidth and JVM optimization. |
| 1,000,000 records, heavy parsing | Measure in practice | Measure in practice | Measure in practice | Watch repeated parsing cost. |
| 100,000 records, 10 groups | Measure in practice | Measure in practice | Measure in practice | Per-group memory is relatively small. |
| 100,000 records, 100,000 groups | Measure in practice | Measure in practice | Measure in practice | Map and group count may dominate. |

Never fill in made-up numbers and call them benchmark results. When comparing, distinguish **time/op** (lower is better) from **throughput** (higher is better), and inspect variance across runs.

One option can win a microbenchmark yet run slower under concurrent requests competing for CPU/pools. If the source involves I/O, CPU-only benchmarks cannot predict connection pools, timeouts, or real load behavior.

## 15. Common mistakes

| Practice | Why it is problematic | Fix |
| --- | --- | --- |
| Calling multiple terminal operations on the **same Stream** | A consumed Stream cannot be reused. | Create a new Stream from a repeatable source, or combine metrics in one terminal operation. |
| Reopening a file for each count/sum/min/max | Repeats I/O and parsing; file may change between reads. | `Files.lines` + `summaryStatistics` or multi-metric collector, closed properly. |
| Using `groupingBy(key, toList())` just to compute count/sum | Retains all elements and iterates lists again. | `groupingBy(key, counting/summarizingLong)`. |
| Filtering `paid` before reporting `allCount` | Drops unpaid transactions from the total metric. | Use `teeing` and downstream `filtering` per scope. |
| Treating `getMin()` of an empty statistics object as real data | Returns sentinel, not an observation. | Check count; expose `OptionalLong`. |
| Using `BigDecimal` unnecessarily for counts, or `double` for exact money | Adds needless cost or rounding bugs. | Match numeric type to domain range and precision rules. |
| Believing “one pass = `O(1)` memory” | Stateful operations and `toList` still buffer. | Check state size, group cardinality, and retained results. |
| Calling `parallel()` to fix multiple traversals | Parallel does not automatically merge distinct pipelines. | Design proper aggregation first, then benchmark parallelism. |
| Using a mutable identity in `reduce` to collect into a list/map | Violates reduction contract and breaks under parallelism. | Use `collect` with proper supplier/accumulator/combiner. |
| Marking a custom collector `CONCURRENT` carelessly | Concurrent updates to shared state cause races. | Declare only true characteristics, or keep separate accumulators. |
| Timing with a single `System.nanoTime()` | Skewed by JIT, GC, scheduling, and load. | Use JMH and verify equivalent results. |

## 16. Practice exercises

**Exercise 1 — Spot redundant passes.** Given a `List<Order>` where `count`, `sum`, `min`, and `max` are computed via four fresh streams, rewrite using one `summarizingLong(Order::amount)`. List the conditions making both versions equivalent.

**Exercise 2 — Distinguish reuse errors.** Explain why `list.stream().count()` followed by `list.stream().findFirst()` can be valid whereas `Stream<T> s = list.stream(); s.count(); s.findFirst();` is invalid.

**Exercise 3 — Two scopes.** Given `Sale(team, amount, paid, late)`, use `teeing` to collect `allCount` and `paidCount` in one terminal operation. Replace `filtering` with `Stream.filter` before `collect` and explain the wrong result.

**Exercise 4 — Multi-metric grouping.** Write `groupingBy(Sale::team, summarizingLong(Sale::amount))` and verify `API` has count = 2, sum = 300 for `API:100`, `API:200`, `UI:50`. If a team never appeared in the input, does the map contain its key?

**Exercise 5 — A group with zero matching elements.** Apply downstream `filtering(Sale::paid, summarizingLong(...))` to a team that has only unpaid sales. Why is count = 0 while min/max return sentinels? Convert them to `OptionalLong`.

**Exercise 6 — Custom collector.** Write an `Accumulator` holding count/sum/min/max; prove the combiner has an identity and associativity when numeric types do not overflow. Explain why the supplier must not return **a single shared accumulator instance**.

**Exercise 7 — Memory.** Compare `groupingBy(team, toList())` against `groupingBy(team, summarizingLong(...))` for 1,000,000 transactions across only 10 teams. What changes if there are 1,000,000 distinct teams?

**Exercise 8 — Single-pass file read.** Read a file of integers, skip blank lines, and compute `LongSummaryStatistics` inside `try-with-resources`. Try adding one malformed line and decide whether to fail the whole batch or record bad lines.

**Exercise 9 — Performance test.** Benchmark designs A/B/C with JMH using a light mapper and a heavy mapper. Draw conclusions only after outputs match, warmup/forks finish, and time/op, allocation, and environment are recorded.

## 17. Pre-optimization checklist

- [ ] Identify **all metrics** to compute and **the data scope** of each.
- [ ] Distinguish **reopening a source** from **reusing the same Stream** (invalid).
- [ ] Prefer `summaryStatistics`/`summarizingLong` when built-in arithmetic metrics suffice.
- [ ] Use `teeing` when you genuinely have two distinct downstream roles; consider a custom collector for many metrics.
- [ ] Group with aggregating downstreams instead of retaining every record only to summarize later.
- [ ] Place `filter` and `Collectors.filtering` at the right business scope.
- [ ] Handle empty groups, missing min/max values, and numeric overflow.
- [ ] Choose an appropriate accumulator state; never leak mutable objects if reports must be immutable.
- [ ] For custom collectors, ensure supplier creates fresh state, combiner merges cleanly, and never declare `CONCURRENT` unless thread-safe.
- [ ] Evaluate **group cardinality, buffering, and memory** instead of merely counting streams.
- [ ] Avoid side effects in `peek` or relying on lambda call counts.
- [ ] Close I/O sources with `try-with-resources`.
- [ ] Verify sequential correctness before trying parallelism.
- [ ] Measure performance with controlled benchmarks; never conclude from hypothetical numbers.

**Takeaway:** Avoiding multiple source traversals does not mean cramming every computation into one giant lambda. **Design aggregations around the exact data scope**, use built-in collectors when they fit, combine metrics with `teeing` or a dedicated accumulator when needed, and return clean reports. A single-terminal pipeline can still consume lots of memory, and a custom collector must still honor parallel contracts. Performance gains are trustworthy only when **results are correct, memory is controlled, and measurements reflect real workloads**.

**References:** [Stream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html), [Collectors — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Collectors.html), [LongSummaryStatistics — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/LongSummaryStatistics.html), [JMH — OpenJDK](https://github.com/openjdk/jmh).
