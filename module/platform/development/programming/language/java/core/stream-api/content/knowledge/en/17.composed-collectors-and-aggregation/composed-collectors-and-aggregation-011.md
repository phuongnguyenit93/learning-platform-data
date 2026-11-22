# Building Multi-Metric Reports and Immutable Aggregated Results

In the **Java Stream API**, a report often needs more than a single total. For instance, from a list of orders we may want **order count, total amount, min/max values, average, and late-order count** per group. If each metric is computed in a separate pipeline, filtering, grouping, and data traversal can be repeated multiple times. **Composed collectors** let us express grouping and multi-metric aggregation within a single `collect` terminal operation.

Reports also need another contract: once computation finishes, other parts of the program **must not accidentally mutate** the published numbers. Therefore, this lesson combines two ideas:

1. **Aggregating multiple metrics in the same collection pass**, using `summarizingLong`, `groupingBy`, `filtering`, `teeing`, or a custom collector.
2. **Finalizing results into immutable values** using immutable data types, `collectingAndThen`, `Map.copyOf`, and `List.copyOf` where appropriate.

We will separate *mutable accumulation state inside the collector* from *immutable report data returned outside*. This is an important design principle for the Java Stream API when working with declarative data processing, statistics, and parallel pipelines.

## 1. Define the report shape and data contract upfront

Suppose the input consists of orders with attributes: owning team, order ID, amount in the smallest integer currency unit, payment status, and late-delivery status.

We want a report of **paid orders only** by team:

| Team | Orders | Total amount | Minimum | Maximum | Average | Late orders |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| API | 2 | 2.000 | 800 | 1.200 | 1.000 | 1 |
| UI | 1 | 2.000 | 2.000 | 2.000 | 2.000 | 1 |

Several decisions must be made **before writing code**:

- Is the eligibility condition placed **before grouping** or applied only to one metric inside the group?
- When there is no data, should a group **be absent** or still appear with empty values?
- Should amounts use `long`, `BigDecimal`, or `double`? Can overflow occur, or are there rounding rules?
- Is the report **read-only**, or do callers still need to edit groups and metrics?
- Must **team ordering** be preserved for display?

Examples throughout use `long` for integer monetary amounts. Small sample datasets do not overflow `long`; real systems still must guard amount and total bounds.

## 2. Avoid computing each metric in an independent pipeline

This is valid on a `List` that can create multiple streams, yet it is usually poor design for multi-metric reports:

```java
import java.util.Arrays;
import java.util.List;

List<Long> amounts = Arrays.asList(1200L, 800L, 2000L);

long count = amounts.stream().count();
long sum = amounts.stream().mapToLong(Long::longValue).sum();
long min = amounts.stream().mapToLong(Long::longValue)
    .min().orElseThrow(IllegalStateException::new);
long max = amounts.stream().mapToLong(Long::longValue)
    .max().orElseThrow(IllegalStateException::new);
double average = amounts.stream().mapToLong(Long::longValue)
    .average().orElseThrow(IllegalStateException::new);
```

Each `amounts.stream()` creates **a different stream instance**, and terminal operations over typical sources traverse or process the relevant data. In real pipelines, filtering, mapping, decoding records, or reading I/O sources can cost far more than the additions themselves.

You **cannot** reuse the same `Stream` after a terminal operation:

```java
import java.util.stream.LongStream;

LongStream values = LongStream.of(1200L, 800L, 2000L);
long sum = values.sum();

// Wrong: the same stream has already been consumed.
// long count = values.count(); // IllegalStateException
```

If the source can only be consumed once, such as a file stream or an iterator-backed stream, reading multiple times may not even be possible. The solution is designing a collector for aggregations that need to run **in a single logical collection pass**.

## 3. `summarizingInt`, `summarizingLong`, `summarizingDouble`: built-in multi-metrics

These three collectors compute **count, sum, min, max, and average** for a numeric field of each element:

| Collector | Mapper | Result type |
| --- | --- | --- |
| `Collectors.summarizingInt(...)` | `ToIntFunction<T>` | `IntSummaryStatistics` |
| `Collectors.summarizingLong(...)` | `ToLongFunction<T>` | `LongSummaryStatistics` |
| `Collectors.summarizingDouble(...)` | `ToDoubleFunction<T>` | `DoubleSummaryStatistics` |

Example:

```java
import java.util.Arrays;
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;

LongSummaryStatistics stats = Arrays.asList(1200L, 800L, 2000L)
    .stream()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 4000
System.out.println(stats.getMin());     // 800
System.out.println(stats.getMax());     // 2000
System.out.println(stats.getAverage()); // 1333.333...
```

`summarizingLong` is a **collector** for `Stream<T>`; it is not the same as the terminal operation `LongStream.summaryStatistics()`, even though both produce the same statistics type. The collector form is especially useful inside `groupingBy` or `partitioningBy`.

Note: `LongSummaryStatistics` is **mutable**; `accept` and `combine` can mutate the object. Thus, returning `Map<String, LongSummaryStatistics>` directly does not yet produce an immutable report.

## 4. Grouping then summarizing: `groupingBy` with a downstream collector

`Collectors.groupingBy(classifier, downstream)` builds a map keyed by `classifier`; each group uses `downstream` to compute its result:

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

List<String> data = Arrays.asList("API:1200", "UI:2000", "API:800");

Map<String, LongSummaryStatistics> byTeam = data.stream()
    .collect(Collectors.groupingBy(
        line -> line.substring(0, line.indexOf(':')),
        Collectors.summarizingLong(line ->
            Long.parseLong(line.substring(line.indexOf(':') + 1))
        )
    ));

System.out.println(byTeam.get("API").getCount()); // 2
System.out.println(byTeam.get("API").getSum());   // 2000
System.out.println(byTeam.get("UI").getMax());    // 2000
```

As each element is visited, the classifier determines the group and the downstream updates the corresponding statistics. Logically, the source goes through a single terminal operation, rather than calling `filter` five times for each team.

However, this result has **two mutable layers**: the map itself can be mutated in common implementations, and each `LongSummaryStatistics` is definitely mutable. To finalize the report, convert the statistics objects into immutable value types and protect the containing map.

## 5. `collectingAndThen`: finalizing results after accumulation

`Collectors.collectingAndThen(downstream, finisher)` wraps a collector with a **final finishing step**. The downstream is free to use a mutable container for efficient accumulation; `finisher` converts the completed result into the desired output type.

```text
Stream<T>
   |
   +--> groupingBy(key, downstream)
             |
             +--> summarizingLong(...)    // mutable accumulation
                         |
                         +--> finisher     // build immutable DTO
             |
             +--> outer map finisher       // Map.copyOf(...)
   |
   +--> Map<K, ImmutableReport>
```

A simple report type can be a `record` (Java 16+):

```java
import java.util.LongSummaryStatistics;

record BasicMetrics(
    long count,
    long total,
    long minimum,
    long maximum,
    double average
) {
    static BasicMetrics from(LongSummaryStatistics source) {
        return new BasicMetrics(
            source.getCount(),
            source.getSum(),
            source.getMin(),
            source.getMax(),
            source.getAverage()
        );
    }
}
```

A `record` has no setters for its components; with only primitive components, `BasicMetrics` is an immutable value by design in this example. Converting via `from` also avoids exposing the mutable `LongSummaryStatistics`.

**Beware of empty groups:** `LongSummaryStatistics.getMin()` when `count == 0` returns `Long.MAX_VALUE`, and `getMax()` returns `Long.MIN_VALUE`. Those two values are **not** measured data. `BasicMetrics` fits **groups that appeared and contain at least one element**. If designing a general report that may be empty, represent min/max with `OptionalLong`, mark a no-data state, or read them only after checking count.

### Finalizing each group and the outer map

Assuming `BasicMetrics` is defined as above:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BasicMetrics> report = Arrays.asList(
        "API:1200", "UI:2000", "API:800"
    ).stream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingBy(
            line -> line.substring(0, line.indexOf(':')),
            Collectors.collectingAndThen(
                Collectors.summarizingLong(line ->
                    Long.parseLong(line.substring(line.indexOf(':') + 1))
                ),
                BasicMetrics::from
            )
        ),
        Map::copyOf
    ));

System.out.println(report.get("API").total()); // 2000
// report.put("OTHER", new BasicMetrics(...)); // Not allowed
```

`Map.copyOf` (Java 10+) creates an **unmodifiable** map from the input map. Combined with `BasicMetrics` containing only primitives, we obtain immutability at both the map level and the statistics value level. For components that are `List`, `Map`, arrays, or mutable beans, using `record` alone is **not enough** for deep immutability.

## 6. `teeing`: combining two independent aggregations into one result

`summarizingLong` provides five metrics out of the box. If the report needs **one more metric**, such as late order count, use `Collectors.teeing` (Java 12+):

```java
Collectors.teeing(downstream1, downstream2, merger)
```

Each input element is fed to both downstream collectors; when finished, `merger` receives **the two results** and produces one final result. That allows computing `summarizingLong` and filtered `counting` in **one logical pass**.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

record NumberReport(long count, long sum, long evenCount) {}

NumberReport report = Stream.of(2, 3, 4, 5)
    .collect(Collectors.teeing(
        Collectors.summarizingLong(Integer::longValue),
        Collectors.filtering(
            value -> value % 2 == 0,
            Collectors.counting()
        ),
        (stats, evens) -> new NumberReport(
            stats.getCount(), stats.getSum(), evens
        )
    ));

System.out.println(report); // NumberReport[count=4, sum=14, evenCount=2]
```

`Collectors.filtering` (Java 9+) is a downstream collector that **forwards only matching elements to the child collector**. In the example, `summarizingLong` runs on **all** numbers, while the `counting` branch sees only even numbers.

Do not confuse `Collectors.teeing` with running a stream twice. Although both downstreams process each element under the collector contract, **there is only one terminal `collect` on the source**. On the other hand, `teeing` still maintains **two state accumulators**; it is not free. For many complex metrics at high volume, a custom collector may be clearer or more efficient.

## 7. Complete example: immutable multi-metric report by team

The example below uses **Java 17+**, allowing `record`, `Collectors.filtering`, `Collectors.teeing`, and `Map.copyOf` together. Each group contains only **paid** orders; the late-order count is **the count of late orders among paid orders**, not all raw orders.

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ImmutableSalesReport {
    record Sale(
        String team,
        String orderId,
        long amountInMinorUnits,
        boolean paid,
        boolean late
    ) {}

    record TeamMetrics(
        long orderCount,
        long totalAmount,
        long minimumAmount,
        long maximumAmount,
        double averageAmount,
        long lateCount
    ) {}

    static Map<String, TeamMetrics> buildReport(List<Sale> orders) {
        Collector<Sale, ?, TeamMetrics> metricsCollector =
            Collectors.teeing(
                Collectors.summarizingLong(Sale::amountInMinorUnits),
                Collectors.filtering(
                    Sale::late,
                    Collectors.counting()
                ),
                (LongSummaryStatistics stats, Long lateCount) ->
                    new TeamMetrics(
                        stats.getCount(),
                        stats.getSum(),
                        stats.getMin(),
                        stats.getMax(),
                        stats.getAverage(),
                        lateCount
                    )
            );

        return orders.stream()
            .filter(Sale::paid)
            .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(Sale::team, metricsCollector),
                Map::copyOf
            ));
    }

    public static void main(String[] args) {
        List<Sale> orders = Arrays.asList(
            new Sale("API", "A-01", 1200L, true, false),
            new Sale("UI",  "U-01", 2000L, true, true),
            new Sale("API", "A-02",  800L, true, true),
            new Sale("UI",  "U-02",  500L, false, true),
            new Sale("API", "A-03",  900L, false, false)
        );

        Map<String, TeamMetrics> report = buildReport(orders);

        System.out.println(report.get("API"));
        // TeamMetrics[orderCount=2, totalAmount=2000,
        // minimumAmount=800, maximumAmount=1200,
        // averageAmount=1000.0, lateCount=1]

        System.out.println(report.get("UI").orderCount()); // 1
        System.out.println(report.get("UI").lateCount());  // 1

        // report.clear(); // UnsupportedOperationException
    }
}
```

Layer-by-layer explanation:

1. `filter(Sale::paid)` excludes unpaid orders **from all metrics**; therefore teams with only unpaid orders do not appear in the map.
2. `groupingBy(Sale::team, metricsCollector)` routes filtered elements into groups by team name.
3. `summarizingLong` accumulates `count/sum/min/max/average` for **each team**.
4. `filtering(Sale::late, counting())` counts late orders within **the same team**.
5. `teeing`'s merger constructs an immutable `TeamMetrics` from the two temporary results.
6. `collectingAndThen(..., Map::copyOf)` freezes the outer map as unmodifiable.

Notable point: `TeamMetrics` contains only primitives, so it introduces no mutable references into the result. The `LongSummaryStatistics` accumulators mutate **internally during collection**, yet never escape outside. Afterward, consumers see only the map and records.

### Things the example does not solve automatically

- **Zero paid orders:** `buildReport` returns an empty map. `report.get("API")` is then `null`; callers must check before calling accessors.
- **`null` team:** default `groupingBy` rejects classifiers returning `null`; a validation or normalization policy is needed.
- **Overflow:** `LongSummaryStatistics.getSum()` still uses `long` and can overflow. It is not an arbitrary-precision sum.
- **Average:** `getAverage()` returns `double`, not an exact decimal monetary figure under business rounding rules.
- **Map ordering:** `Map.copyOf` does not guarantee entry iteration order. Do not rely on map print order for team ordering.

## 8. Where to place the condition? `Stream.filter` vs. `Collectors.filtering`

Where you place `filter` can produce **different reports**.

### Filtering before `groupingBy`: non-qualifying groups vanish

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String team, boolean paid) {}

Map<String, Long> paidOnly = Arrays.asList(
        new Item("API", false),
        new Item("UI", true)
    ).stream()
    .filter(Item::paid)
    .collect(Collectors.groupingBy(
        Item::team,
        Collectors.counting()
    ));

System.out.println(paidOnly.containsKey("API")); // false
```

`API` is dropped completely before the classifier, so there is no `"API"` key in the map.

### `Collectors.filtering` as downstream: preserves groups that appeared

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String team, boolean paid) {}

Map<String, Long> paidPerExistingTeam = Arrays.asList(
        new Item("API", false),
        new Item("UI", true)
    ).stream()
    .collect(Collectors.groupingBy(
        Item::team,
        Collectors.filtering(
            Item::paid,
            Collectors.counting()
        )
    ));

System.out.println(paidPerExistingTeam.get("API")); // 0
System.out.println(paidPerExistingTeam.get("UI"));  // 1
```

`groupingBy` creates the `API` group from the encountered record, and then downstream `filtering` does not pass the unpaid record to `counting`. Thus the group appears with value `0`.

For management reports, this is an important semantic choice: **“no group”** and **“group exists with zero qualifying orders”** are not the same state.

## 9. Multi-level aggregation and freezing immutability down to lists

Multi-level reports often take the shape `Map<String, Map<Boolean, List<String>>>`: by team, then by completion status, then a list of task IDs. Wrapping only the outer map as unmodifiable **does not protect nested maps and lists**.

Java 17+ example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Task(String team, String id, boolean done) {}

List<Task> tasks = Arrays.asList(
    new Task("API", "T-01", true),
    new Task("API", "T-02", false),
    new Task("UI", "T-03", true)
);

Map<String, Map<Boolean, List<String>>> report = tasks.stream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingBy(
            Task::team,
            Collectors.collectingAndThen(
                Collectors.partitioningBy(
                    Task::done,
                    Collectors.mapping(
                        Task::id,
                        Collectors.collectingAndThen(
                            Collectors.toList(),
                            List::copyOf
                        )
                    )
                ),
                Map::copyOf
            )
        ),
        Map::copyOf
    ));

System.out.println(report.get("API").get(true));  // [T-01]
System.out.println(report.get("API").get(false)); // [T-02]
System.out.println(report.get("UI").get(false));  // []

// report.clear();                     // Not allowed
// report.get("API").clear();          // Not allowed
// report.get("API").get(true).add("X"); // Not allowed
```

Each layer has a clear job:

- `mapping(Task::id, ...)` retains only task IDs in the list.
- `collectingAndThen(toList(), List::copyOf)` freezes **each list** after accumulation.
- `partitioningBy(Task::done, ...)` creates both Boolean keys for each team that appears.
- Inner `Map.copyOf` freezes each team's status map.
- Outer `Map.copyOf` freezes the teams map.

`List.copyOf`/`Map.copyOf` (Java 10+) reject invalid `null` elements or values; at the same time, this is still **shallow immutability**: if lists hold mutable objects rather than `String`, those objects themselves can still mutate state. For deeply nested reports, prefer immutable value types at the leaves.

There is no guarantee on iteration order for maps produced by `Map.copyOf`. If the UI must present teams in a fixed order, sort **at display time** or design an explicitly ordered map rather than expecting `Map.copyOf` to preserve insertion order.

## 10. When is a custom collector needed?

`teeing` combines **exactly two** downstream collectors in one step; combining three or more branches is possible by nesting `teeing`, yet generic expressions quickly become long and hard to read. A custom collector is the better option when:

- Multiple metrics can be updated together inside one small accumulator.
- Custom overflow detection, rounding, or special invalid-data handling is required.
- A dedicated immutable result must be constructed without exposing internal mutable containers.
- Deeply nesting collectors makes code harder to maintain than direct accumulation logic.

Conceptual pattern:

```text
Collector.of(
    Accumulator::new,          // supplier: creates a new accumulator
    Accumulator::add,          // accumulator: accepts one element
    Accumulator::combine,      // combiner: merges two independent accumulators
    Accumulator::toImmutable   // finisher: finalizes immutable DTO
)
```

Here, `Accumulator` is allowed to be mutable **within the private scope of the collector**. The supplier must return a fresh instance, the combiner must merge cleanly for any source split, and the finisher must avoid leaking mutable state externally. Do not replace this with `reduce(new ArrayList<>(), ...)` and mutate the identity: `reduce` has a different contract and provides no supplier to create isolated containers per accumulation partition.

**Do not declare `Collector.Characteristics.CONCURRENT`** unless the custom accumulator genuinely supports multiple threads safely updating the same container. Likewise, do not declare `IDENTITY_FINISH` when a finisher is still needed to convert a mutable accumulator into an immutable DTO.

## 11. Metric precision and behavior on empty data

Multi-metric reports can hide arithmetic bugs if you focus only on collector structure:

| Issue | Behavior to know | How to handle |
| --- | --- | --- |
| Sum of many `int`s | `summingInt` returns `int` and can overflow | Consider `summingLong` or `summarizingInt` (which has a `long` sum) where appropriate. |
| Very large `long` sum | `LongSummaryStatistics` and `summingLong` can still overflow | Validate bounds or use `BigInteger`/`BigDecimal` as needed. |
| Floating-point average | `getAverage()` returns `double` | Specify tolerance and rounding; never treat as exact decimal currency. |
| Group with no elements | `groupingBy` does not create unseen groups | Check `containsKey`/`get` before accessing DTOs. |
| Empty summary statistics | Min/max hold sentinel values, average defaults to `0.0` | Check `getCount()` or use `OptionalLong`/`OptionalDouble`. |
| `NaN` or infinity | Can render `double` statistics sum/average/extrema meaningless | Validate input data before aggregating. |
| `null` keys or values | `groupingBy` forbids classifier returning `null`; `Map.copyOf` rejects null | Validate, group missing values under an explicit rule, or fail fast. |
| Map ordering | `groupingBy` and `Map.copyOf` promise no iteration order | Sort separately on display or choose an ordered map implementation. |

For example: if statistics compute a system-wide report (without `groupingBy`) and the input is empty, min/max from `LongSummaryStatistics` are **not** real measurements. Rather than building `TeamMetrics` from an empty group with sentinels, represent missing data with `Optional` or a no-samples report state.

For currency, summing `long` minor units avoids many binary decimal representation errors; however, **monetary averages** still require a rounding policy for invoicing or unit conversion. When high precision is needed or sums can exceed `long`, `BigDecimal` may be more appropriate.

## 12. Parallelism, ordering, and resources

Collectors like `groupingBy`, `summarizingLong`, and `teeing` are designed so the Stream API can organize partitioned accumulation and combine results. When adding `parallel()`, watch out for:

1. **Behavioral functions must not depend on shared mutable state:** classifiers, predicates, mappers, and mergers should be data-pure. Do not update an external `HashMap` inside `map` or `filter`.
2. **Do not require a lambda execution order:** source encounter order and output map iteration order are separate concepts.
3. **Custom collector combiners must honor the contract:** never share one container across branches, and never drop or double-count elements.
4. **Floating-point error:** parallel `double` sums can differ in the last few bits due to addition order, even when business results agree within tolerance.
5. **Immutability does not automatically make nested values thread-safe:** an unmodifiable map can still hold references to mutable beans or collections.
6. **Performance is not better by default:** `teeing`, `groupingBy`, and `Map.copyOf` all carry accumulation, merging, and freezing costs. Measure on real data and workloads.

A report needing only `count`, `sum`, and extrema can usually run with memory proportional to **group count**, without retaining every record. Yet if the downstream is `toList`, memory still grows with **the number of stored elements**.

`collect` is a terminal operation; a `Stream` can be operated on only once. With sources such as `Files.lines`, close the stream with `try-with-resources`; `collect` does not automatically release all I/O resources. On infinite sources, collectors that aggregate the whole dataset generally cannot terminate without `limit` or a stopping condition.

## 13. Choosing collector composition by requirement

| Requirement | Design suggestion | Reason |
| --- | --- | --- |
| Count/sum/min/max/average of one field | `summarizingInt/Long/Double` | Five metrics in a single statistics object. |
| Five metrics per group | `groupingBy(key, summarizingLong(...))` | Accumulates per group in one pipeline. |
| Five metrics + one conditional metric | `teeing(summarizingLong(...), filtering(..., counting()), merger)` | Two downstreams, one result DTO. |
| Turn mutable statistics into a record | `collectingAndThen(summarizingLong(...), Metrics::from)` | Avoids exposing the mutable accumulator. |
| Freeze the group map as unmodifiable | `collectingAndThen(groupingBy(...), Map::copyOf)` | Prevents modifying mappings after finalizing. |
| Nested maps of unmodifiable lists | `mapping(..., collectingAndThen(toList(), List::copyOf))` and freeze each map | Protects multiple data layers. |
| Many interdependent metrics, complex logic | `Collector.of` with dedicated accumulator and immutable finisher | Full control over state and merging. |
| Need stable key order on display | Sort at presentation layer or use an ordered map | `Map.copyOf` preserves no insertion order guarantee. |

### Common mistakes

- Calling multiple terminal operations on **the same stream**: a consumed stream cannot be reused.
- Returning `LongSummaryStatistics` directly and calling it an “immutable report”: the object still has `accept` and `combine`.
- Wrapping the outer `Map` while leaving inner `List` or `Map` values mutable: callers can still mutate nested data.
- Using `Stream.filter` when groups with **0 valid results** must be retained: downstream `Collectors.filtering` has different semantics.
- Thinking `teeing` creates a single accumulator: it actually creates **two downstreams** and one merger.
- Using `long` sums without considering overflow, or `double` averages without an error policy.
- Assuming `groupingBy` results already include every business group: only groups that actually appear are created.
- Assuming `Map.copyOf` preserves ordering and deep-copies value objects.
- Marking a custom collector `CONCURRENT` or `IDENTITY_FINISH` before satisfying the corresponding contract.

## 14. Practice exercises

**Exercise 1 — Grouped report.** Given `List<String>` containing `["API:10", "UI:20", "API:30"]`, use `groupingBy` and `summarizingLong` to compute count, sum, min, max, and average per team. Verify team `API` has count = 2, sum = 40, average = 20.0.

**Exercise 2 — Finalizing results.** Create `record Metrics(long count, long sum)`. Use `collectingAndThen(summarizingLong(...), stats -> new Metrics(...))` for each group, then freeze the map with `Map.copyOf`. Try calling `put` on the result and explain why it is rejected.

**Exercise 3 — `teeing`.** On `Stream.of(1, 2, 3, 4, 5)`, simultaneously compute `summarizingInt` for all elements and count even numbers with `filtering(n -> n % 2 == 0, counting())`. Merge into a record; predict count = 5, sum = 15, even count = 2.

**Exercise 4 — Filter placement.** When team `API` has only `paid = false` orders, compare `stream.filter(paid).collect(groupingBy(team, counting()))` and `stream.collect(groupingBy(team, filtering(paid, counting())))`. Which approach lacks the `API` key, and which returns `API -> 0`?

**Exercise 5 — Multi-level immutability.** Build `Map<String, Map<Boolean, List<String>>>` by team and completion status, then use `List.copyOf` and `Map.copyOf` to freeze each layer. Verify you cannot `put` into the outer map, `put` into a sub-map, or `add` to a list, while explaining why a mutable bean inside a list still needs separate protection.

**Exercise 6 — Testing empty data.** Run the report on an empty list. Why does `groupingBy` return an empty map without creating `API` or `UI` teams? If business rules require displaying every team, propose how to add the team catalog and default values **after** aggregation or use a report structure with predefined teams.

**Key takeaway:** To build multi-metric reports, place `groupingBy` at the classification layer, `summarizing*` or `teeing` at the aggregation layer, and `collectingAndThen` at the finalization layer. A collector may use mutable state **during processing**, yet published values should be immutable DTOs and unmodifiable maps/lists to the exact depth required by business logic. Never overlook empty groups, numeric types, iteration order, or the difference between shallow and deep immutability.
