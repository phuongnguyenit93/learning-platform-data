# Building Group Reports with Multi-Level Collectors

## 1. Practice Problem and Goals

In **JAVA_STREAM_API**, `filter`, `map`, `reduce`, and `collect` let you turn a collection of records into a report without managing nested loops manually. When aggregating across **two or more dimensions**, such as sales region and sales channel, you can nest collectors instead of assembling Maps by hand.

This exercise belongs to the **Beginner and Intermediate Exercises** chapter and presents a self-contained sales-reporting scenario that can be implemented and tested independently:

> From a list of orders, generate a report by **region → sales channel**, where each group reports the paid order count, total amount, minimum, maximum, and average. You must distinguish a group with zero paid orders from a group that does not exist in the data.

By the end of this lesson, you will be able to:

1. Identify two grouping keys and sketch the `Map<K1, Map<K2, D>>` return type before writing code.
2. Use nested `Collectors.groupingBy` to count or sum per group.
3. Combine `counting`, `summingLong`, `summarizingLong`, `mapping`, `filtering`, and `collectingAndThen`.
4. Choose `LinkedHashMap` for first-encounter region order and `TreeMap` for sorted channel keys.
5. Handle empty sources, groups emptied by filtering, zero amounts, and invalid inputs accurately.
6. Write a Java 17 program and JUnit 5 unit tests verifying **both content and required ordering**.
7. Recognize limits involving `long` addition, mutable collections, shared state, and parallel execution.

**Scope:** This is a guided lesson with requirements, examples, a reference solution, and extension exercises. No database, server, or external framework beyond the JDK is needed to run the core program.

## 2. Designing the Data Model and Expected Output

### 2.1. What Fields Does Each Order Have?

Minimal model:

```java
record Sale(
    String id,
    String region,
    String channel,
    long amountVnd,
    boolean paid
) {}
```

Meaning:

| Field | Type | Role |
| --- | --- | --- |
| `id` | `String` | Order identifier |
| `region` | `String` | Level-1 grouping key, e.g., `HN`, `HCM`, `DN` |
| `channel` | `String` | Level-2 grouping key, e.g., `WEB` or `STORE` |
| `amountVnd` | `long` | Integer amount in VND |
| `paid` | `boolean` | Whether the order has been paid |

In the complete program, `Sale`'s constructor validates `id`, `region`, `channel`, and amount so invalid data never enters the collector.

### 2.2. Input Dataset

| ID | Region | Channel | Amount (VND) | Paid? |
| --- | --- | --- | ---: | --- |
| O1 | HN | WEB | 120.000 | Yes |
| O2 | HN | STORE | 40.000 | Yes |
| O3 | HCM | WEB | 70.000 | Yes |
| O4 | HN | WEB | 30.000 | No |
| O5 | HCM | STORE | 50.000 | Yes |
| O6 | DN | WEB | 90.000 | No |
| O7 | DN | STORE | 20.000 | Yes |
| O8 | HCM | WEB | 10.000 | Yes |

Total orders in the source: **8**. There are **6 paid orders**, with total paid revenue equal to **310.000 VND**.

### 2.3. Reference Result Table for Verification

| Region | Channel | All Orders | Paid Orders | Paid Total (VND) | Paid Average (VND) |
| --- | --- | ---: | ---: | ---: | ---: |
| HN | STORE | 1 | 1 | 40.000 | 40.000 |
| HN | WEB | 2 | 1 | 120.000 | 120.000 |
| HCM | STORE | 1 | 1 | 50.000 | 50.000 |
| HCM | WEB | 2 | 2 | 80.000 | 40.000 |
| DN | STORE | 1 | 1 | 20.000 | 20.000 |
| DN | WEB | 1 | 0 | 0 | **No samples** |

**Two ordering requirements:**

- Regions follow first-appearance order in the source list: **HN → HCM → DN**.
- Channels within each region follow ascending name order: **STORE → WEB**.

The table uses those orders explicitly—not because every Java `Map` is ordered. In the solution, we select specific Map implementations to enforce them.

## 3. Step 1 — Translate the Problem into Result Types

Before writing lambdas, determine the types to collect:

```text
List<Sale>
    │
    └── Stream<Sale>
            │
            └── groupingBy(region)
                    │
                    ├── HN  ── groupingBy(channel) ── STORE, WEB
                    ├── HCM ── groupingBy(channel) ── STORE, WEB
                    └── DN  ── groupingBy(channel) ── STORE, WEB
                                                        │
                                                        └── downstream statistic
```

Three progressive result shapes will be built:

```java
// A. Count all orders, without filtering by paid.
Map<String, Map<String, Long>>

// B. Total amount of paid orders.
Map<String, Map<String, Long>>

// C. Detailed report for every group appearing in the source.
Map<String, Map<String, Cell>>
```

`Cell` is a record holding sample count, total amount, min/max, and average of **paid orders**.

Notice that forms A and B share the same **Java type** but carry **different statistical meanings**; name variables and methods so readers never confuse "order count" with "money". In the complete code, we use `LinkedHashMap<String, TreeMap<String, ...>>` to make both outer and inner Map types explicit.

## 4. Step 2 — Two-Level Grouping and Record Counting

Basic pattern:

```java
Collectors.groupingBy(
    Sale::region,                  // Level-1 group.
    LinkedHashMap::new,            // Outer map factory.
    Collectors.groupingBy(
        Sale::channel,             // Level-2 group.
        TreeMap::new,              // Inner map factory.
        Collectors.counting()      // Value per level-2 group.
    )
)
```

Applying this to `sales.stream().collect(...)` yields:

```java
LinkedHashMap<String, TreeMap<String, Long>> counts =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::channel,
            TreeMap::new,
            Collectors.counting()
        )
    ));
```

**Reading from the inside out:**

1. `Collectors.counting()` receives the `Sale` items for one region/channel pair and produces a `Long`.
2. `groupingBy(Sale::channel, TreeMap::new, counting())` produces a `TreeMap<String,Long>` per region.
3. `groupingBy(Sale::region, LinkedHashMap::new, ...)` produces a `LinkedHashMap<String,TreeMap<String,Long>>`.
4. `collect` consumes `Stream<Sale>` and returns the completed nested Map.

Expected count output:

```text
HN:
    STORE -> 1
    WEB   -> 2
HCM:
    STORE -> 1
    WEB   -> 2
DN:
    STORE -> 1
    WEB   -> 1
```

**Self-check:** the sum of counts across all cells must equal `8`; `HN/WEB` has 2 orders including the unpaid order O4. If we only want paid counts, we need a filtering rule in the next step.

## 5. Step 3 — Filtering Before Grouping to Sum Paid Revenue

If the report only needs groups that have **at least one paid order**, filtering before grouping is natural:

```java
LinkedHashMap<String, TreeMap<String, Long>> paidTotals =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                Sale::channel,
                TreeMap::new,
                Collectors.summingLong(Sale::amountVnd)
            )
        ));
```

On the sample data:

```text
HN:
    STORE -> 40000
    WEB   -> 120000
HCM:
    STORE -> 50000
    WEB   -> 80000
DN:
    STORE -> 20000
    // No WEB key.
```

Explaining `DN/WEB`: O6 is in region DN, channel WEB, and is unpaid. `filter(Sale::paid)` drops O6 **before** either grouping stage sees it, so the map contains no `DN/WEB` cell. When you must display every group present in the source, this approach is insufficient.

**Do not confuse:** "missing key" differs from "present key with total 0". In transactional reporting, both states may need distinct representation.

## 6. Step 4 — Preserving Group Cells While Filtering Statistics via `Collectors.filtering`

`Collectors.filtering` (Java 9+) is a **downstream collector**. Placing it **inside grouping** retains groups seen by the outer collectors even when zero elements pass the downstream predicate.

```java
LinkedHashMap<String, TreeMap<String, Long>> paidTotalsKeepingCells =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::channel,
            TreeMap::new,
            Collectors.filtering(
                Sale::paid,
                Collectors.summingLong(Sale::amountVnd)
            )
        )
    ));
```

Now:

```text
HN:  STORE -> 40000, WEB -> 120000
HCM: STORE -> 50000, WEB -> 80000
DN:  STORE -> 20000, WEB -> 0
```

Why does `DN/WEB` remain? Both region and channel collectors see O6 and **create the DN/WEB group**. Downstream `filtering(Sale::paid, ...)` drops O6, and `summingLong` over an empty subset returns `0L`.

However, `0` alone is **not enough** to tell whether the group had any paid samples. A valid order with an amount of `0` also produces a sum of `0`. The next step uses `summarizingLong` to keep both `count` and `sum`.

## 7. Step 5 — Collecting Full `count`, `sum`, `min`, `max`, and `average`

Instead of running five separate pipelines or building five separate maps, use `Collectors.summarizingLong` to produce a `LongSummaryStatistics` per cell.

```java
LinkedHashMap<String, TreeMap<String, LongSummaryStatistics>> stats =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::channel,
            TreeMap::new,
            Collectors.filtering(
                Sale::paid,
                Collectors.summarizingLong(Sale::amountVnd)
            )
        )
    ));
```

Example:

```java
LongSummaryStatistics hcmWeb = stats.get("HCM").get("WEB");

System.out.println(hcmWeb.getCount());   // 2
System.out.println(hcmWeb.getSum());     // 80000
System.out.println(hcmWeb.getMin());     // 10000
System.out.println(hcmWeb.getMax());     // 70000
System.out.println(hcmWeb.getAverage()); // 40000.0
```

### 7.1. Empty Subsets and Sentinel Values

For the `DN/WEB` cell, `LongSummaryStatistics` reports:

```java
LongSummaryStatistics dnWeb = stats.get("DN").get("WEB");

System.out.println(dnWeb.getCount()); // 0
System.out.println(dnWeb.getSum());   // 0
System.out.println(dnWeb.getMin());   // Long.MAX_VALUE
System.out.println(dnWeb.getMax());   // Long.MIN_VALUE
System.out.println(dnWeb.getAverage()); // 0.0
```

**Never** treat `Long.MAX_VALUE` as a real minimum or `Long.MIN_VALUE` as a real maximum for an empty group. Nor does `getAverage() == 0.0` mean an observed average of 0.

Display rule:

- `count > 0`: min/max/average are real group statistics.
- `count == 0`: min/max/average should display as **"No data"** or an empty optional type.

### 7.2. `LongSummaryStatistics` Is a Mutable Object

`LongSummaryStatistics` exposes `accept(...)` and `combine(...)`. Callers could mutate the stats after collection; therefore, **do not** treat `Map<String,Map<String,LongSummaryStatistics>>` as an immutable report. To publish stable results, convert to a DTO/record holding only the needed values.

## 8. Step 6 — Finalizing Each Cell with `collectingAndThen`

Define the result type:

```java
record Cell(
    long paidCount,
    long totalVnd,
    OptionalLong minVnd,
    OptionalLong maxVnd,
    OptionalDouble averageVnd
) {}
```

`OptionalLong` and `OptionalDouble` represent **presence or absence of statistics**. When `paidCount == 0`, the min, max, and average fields are empty.

Composed collector diagram:

```text
Sale
  │
  └── groupingBy(region, LinkedHashMap)
          │
          └── groupingBy(channel, TreeMap)
                  │
                  └── filtering(paid)
                          │
                          └── summarizingLong(amountVnd)
                                  │
                                  └── collectingAndThen(finisher)
                                         │
                                         ▼
                                        Cell
```

The finisher transforms `LongSummaryStatistics` into `Cell`:

```java
Collectors.collectingAndThen(
    Collectors.summarizingLong(Sale::amountVnd),
    s -> new Cell(
        s.getCount(),
        s.getSum(),
        s.getCount() > 0
            ? OptionalLong.of(s.getMin()) : OptionalLong.empty(),
        s.getCount() > 0
            ? OptionalLong.of(s.getMax()) : OptionalLong.empty(),
        s.getCount() > 0
            ? OptionalDouble.of(s.getAverage()) : OptionalDouble.empty()
    )
)
```

Wrapped inside `Collectors.filtering`, every cell holds a complete `Cell`. This is **multi-level collection**: outer collectors group the data, inner collector filters samples, summary collector accumulates numbers, and the finisher turns mutable state into a clean value type.

## 9. Complete Reference Solution (Java 17+)

Save the code below as `SalesGroupReport.java`, then compile and run on JDK 17 or later. This is a **standalone reference implementation**, independent of the earlier code snippets.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalLong;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public final class SalesGroupReport {

    private SalesGroupReport() {}

    public record Sale(
        String id,
        String region,
        String channel,
        long amountVnd,
        boolean paid
    ) {
        public Sale {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            Objects.requireNonNull(channel, "channel");
            if (id.isBlank() || region.isBlank() || channel.isBlank()) {
                throw new IllegalArgumentException("Codes/IDs must not be blank");
            }
            if (amountVnd < 0L) {
                throw new IllegalArgumentException("amountVnd must be >= 0");
            }
        }
    }

    public record Cell(
        long paidCount,
        long totalVnd,
        OptionalLong minVnd,
        OptionalLong maxVnd,
        OptionalDouble averageVnd
    ) {}

    public static List<Sale> sample() {
        return List.of(
            new Sale("O1", "HN", "WEB",   120_000L, true),
            new Sale("O2", "HN", "STORE",  40_000L, true),
            new Sale("O3", "HCM", "WEB",   70_000L, true),
            new Sale("O4", "HN", "WEB",    30_000L, false),
            new Sale("O5", "HCM", "STORE", 50_000L, true),
            new Sale("O6", "DN", "WEB",    90_000L, false),
            new Sale("O7", "DN", "STORE",  20_000L, true),
            new Sale("O8", "HCM", "WEB",   10_000L, true)
        );
    }

    // Step 2: count all orders by region then channel.
    public static LinkedHashMap<String, TreeMap<String, Long>>
    countAll(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream().collect(Collectors.groupingBy(
            Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                Sale::channel,
                TreeMap::new,
                Collectors.counting()
            )
        ));
    }

    // Step 3: create groups only for paid orders.
    public static LinkedHashMap<String, TreeMap<String, Long>>
    paidTotalsFilteringBeforeGrouping(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream()
            .filter(Sale::paid)
            .collect(Collectors.groupingBy(
                Sale::region,
                LinkedHashMap::new,
                Collectors.groupingBy(
                    Sale::channel,
                    TreeMap::new,
                    Collectors.summingLong(Sale::amountVnd)
                )
            ));
    }

    // Downstream for each cell: filter paid, summarize, and build Cell.
    private static Collector<Sale, ?, Cell> paidCellCollector() {
        return Collectors.filtering(
            Sale::paid,
            Collectors.collectingAndThen(
                Collectors.summarizingLong(Sale::amountVnd),
                stats -> {
                    boolean hasSamples = stats.getCount() > 0L;
                    return new Cell(
                        stats.getCount(),
                        stats.getSum(),
                        hasSamples
                            ? OptionalLong.of(stats.getMin())
                            : OptionalLong.empty(),
                        hasSamples
                            ? OptionalLong.of(stats.getMax())
                            : OptionalLong.empty(),
                        hasSamples
                            ? OptionalDouble.of(stats.getAverage())
                            : OptionalDouble.empty()
                    );
                }
            )
        );
    }

    // Step 6: create cells for every region/channel pair present in source.
    public static LinkedHashMap<String, TreeMap<String, Cell>>
    reportKeepingExistingGroups(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream().collect(Collectors.groupingBy(
            Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                Sale::channel,
                TreeMap::new,
                paidCellCollector()
            )
        ));
    }

    public static long overallPaidCount(
        LinkedHashMap<String, TreeMap<String, Cell>> report
    ) {
        return report.values().stream()
            .flatMap(inner -> inner.values().stream())
            .mapToLong(Cell::paidCount)
            .sum();
    }

    public static long overallPaidAmount(
        LinkedHashMap<String, TreeMap<String, Cell>> report
    ) {
        return report.values().stream()
            .flatMap(inner -> inner.values().stream())
            .mapToLong(Cell::totalVnd)
            .sum();
    }

    public static void main(String[] args) {
        List<Sale> source = sample();
        var allCounts = countAll(source);
        var paidTotals = paidTotalsFilteringBeforeGrouping(source);
        var report = reportKeepingExistingGroups(source);

        System.out.println(List.copyOf(report.keySet()));
        // [HN, HCM, DN]

        System.out.println(List.copyOf(report.get("HN").keySet()));
        // [STORE, WEB]

        System.out.println(allCounts.get("HN").get("WEB")); // 2
        System.out.println(paidTotals.get("HCM").get("WEB")); // 80000
        System.out.println(paidTotals.get("DN").containsKey("WEB"));
        // false, because filtering ran before grouping.

        System.out.println(report.get("HCM").get("WEB"));
        // Cell[paidCount=2, totalVnd=80000, minVnd=OptionalLong[10000],
        //      maxVnd=OptionalLong[70000], averageVnd=OptionalDouble[40000.0]]

        Cell noPaid = report.get("DN").get("WEB");
        System.out.println(noPaid.paidCount()); // 0
        System.out.println(noPaid.totalVnd());  // 0
        System.out.println(noPaid.averageVnd().isEmpty()); // true

        System.out.println(overallPaidCount(report));  // 6
        System.out.println(overallPaidAmount(report)); // 310000
    }
}
```

### 9.1. Why Extract `paidCellCollector` into a Separate Method?

If every lambda is nested inside one long `groupingBy` expression, deep parentheses and generics make the code hard to read. The method:

```java
private static Collector<Sale, ?, Cell> paidCellCollector()
```

exposes the clean input `Sale` and output `Cell` contract while **hiding the intermediate accumulator type `A`**. Separating it also lets you unit test the cell aggregation logic without constructing the full two-level map.

### 9.2. Collector Lifecycle in the Solution

| Layer | Input | Output | Responsibility |
| --- | --- | --- | --- |
| Initial Stream | `Sale` | `Stream<Sale>` | Supplies records in `List` order |
| Outer grouping | `Sale` | `LinkedHashMap<String,...>` | Groups by `region` |
| Inner grouping | `Sale` | `TreeMap<String,Cell>` | Groups by `channel` |
| Downstream filtering | `Sale` | Downstream result | Passes only `paid == true` orders to stats |
| Downstream summarizing | `Sale` | `LongSummaryStatistics` | Accumulates count/sum/min/max/average |
| Finisher | `LongSummaryStatistics` | `Cell` | Converts empty-group sentinels to empty Optionals |

Crucially, this **retains every key pair that appeared in the data**, rather than pre-populating every theoretical region × channel combination. If the source contains only `HN/WEB`, the collector will not invent `HN/STORE`. To guarantee all configured combinations appear, pre-seed a skeleton frame from the valid key catalog and merge data into it.

## 10. Design Choices That Alter the Report

### 10.1. Outer and Inner Map Ordering

`LinkedHashMap::new` preserves **first-key insertion order** in a sequential pipeline with encounter order; on this dataset, regions are `HN, HCM, DN`. `TreeMap::new` sorts channels in natural `String` order; here `STORE, WEB`.

When ordering is unnecessary, `groupingBy(classifier, downstream)` is shorter, though it gives no Map type or key-order guarantee. To sort regions too, use `TreeMap::new` on the outer grouping. To keep channel first-appearance order, use `LinkedHashMap::new` on the inner grouping.

**Never test ordering with `Map.equals` alone:** two maps can be `equals` because they share identical key–value mappings even when their `keySet()` iteration orders differ. Assert on a `List` copied from `keySet()` whenever order is a requirement.

### 10.2. Empty Source vs. Emptied After Filtering

`List.<Sale>of()` yields an **empty** outer map, not a map of regions initialized to zero. A source with only unpaid orders still populates groups/cells in `reportKeepingExistingGroups`, with every `Cell` having `paidCount == 0` and empty Optionals.

Those are three distinct states:

| State | Representation |
| --- | --- |
| No source records | Empty Map |
| Records in region/channel, but zero paid orders | Cell exists with `paidCount == 0` |
| Paid orders exist whose amounts sum to 0 | Cell exists with `paidCount > 0` and `totalVnd == 0` |

### 10.3. `null` and Grouping Keys

`Collectors.groupingBy` does not allow classifiers to return `null` keys in standard JDK implementations; likewise, natural-order `TreeMap` rejects null string keys. The reference code rejects `region == null` or `channel == null` directly in `Sale`'s constructor.

If the source can contain **`null` `Sale` elements**, method references `Sale::region` and `Sale::channel` throw `NullPointerException`. Validate the source or apply `filter(Objects::nonNull)` **only if** dropping invalid rows is permitted by business rules. Avoid silently under-reporting revenue due to missing data.

### 10.4. `long` Overflow

`Collectors.summingLong` and `LongSummaryStatistics` do not detect `long` overflow. When amounts can exceed `Long.MAX_VALUE`, sums can silently wrap. For strict financial accuracy, consider `BigInteger` or `BigDecimal` with an exact collector. Example summing integer VND by region with `BigInteger`:

```java
import java.math.BigInteger;

var exactTotals = SalesGroupReport.sample().stream()
    .filter(SalesGroupReport.Sale::paid)
    .collect(Collectors.groupingBy(
        SalesGroupReport.Sale::region,
        Collectors.reducing(
            BigInteger.ZERO,
            sale -> BigInteger.valueOf(sale.amountVnd()),
            BigInteger::add
        )
    ));
```

In the main example, amounts fit comfortably in `long`; this lesson focuses on **multi-level collectors**, not a full accounting engine.

### 10.5. Result Immutability

`Cell` is a record containing `long` and Optional fields, so its properties cannot be mutated directly. However, the returned `LinkedHashMap` and `TreeMap` instances remain mutable: callers can invoke `put` or `remove`.

If an API must publish an unmodifiable snapshot while **still preserving order**, copy the outer map into a new `LinkedHashMap`, copy inner maps into new `TreeMap`s, and wrap them with `Collections.unmodifiableMap` or `Collections.unmodifiableSortedMap`. Wrapping a view without copying does not prevent callers holding the backing map from mutating it. `Map.copyOf` does not guarantee preserving the source's key traversal order.

## 11. Extension 1: Adding a List of Order IDs per Cell with `mapping`

When a report must inspect which orders belong to each group, `Collectors.mapping` converts each `Sale` to its `id` **downstream** without changing the grouping keys.

```java
LinkedHashMap<String, TreeMap<String, List<String>>> paidIds =
    SalesGroupReport.sample().stream()
        .collect(Collectors.groupingBy(
            SalesGroupReport.Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                SalesGroupReport.Sale::channel,
                TreeMap::new,
                Collectors.filtering(
                    SalesGroupReport.Sale::paid,
                    Collectors.mapping(
                        SalesGroupReport.Sale::id,
                        Collectors.toList()
                    )
                )
            )
        ));

System.out.println(paidIds.get("HCM").get("WEB")); // [O3, O8]
System.out.println(paidIds.get("DN").get("WEB"));  // []
```

Notice the difference between:

- `stream.map(Sale::id)` **before grouping**: the stream elements become `String`, so `Sale::region` and `Sale::channel` are no longer available.
- `Collectors.mapping(Sale::id, toList())` **after determining both keys**: the outer collectors still receive `Sale`, while the inner downstream keeps only IDs.

### 11.1. Intermediate Variation: Returning Deduplicated IDs

Replace `Collectors.toList()` with `Collectors.toSet()` if business rules require dropping duplicate IDs. Note that `toSet()` **does not guarantee order**. For distinct IDs sorted ascending, use `Collectors.toCollection(TreeSet::new)` or chain `collectingAndThen` to convert the Set into a sorted list.

Depending on the domain, two orders sharing the same `id` may be a **data error**; do not silently deduplicate if the report needs to flag errors.

## 12. Extension 2: `teeing` for Two Independent Metrics

`Collectors.teeing` was introduced in **Java 12**. It feeds every element to **two downstream collectors** and combines their results via a merger function.

Example reporting paid count and paid total per region:

```java
import java.util.Map;
import java.util.stream.Collectors;

record CountAndAmount(long count, long amountVnd) {}

Map<String, CountAndAmount> byRegion =
    SalesGroupReport.sample().stream()
        .filter(SalesGroupReport.Sale::paid)
        .collect(Collectors.groupingBy(
            SalesGroupReport.Sale::region,
            Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(
                    SalesGroupReport.Sale::amountVnd
                ),
                CountAndAmount::new
            )
        ));

System.out.println(byRegion.get("HN"));
// CountAndAmount[count=2, amountVnd=160000]
```

`teeing` shines when two metrics accumulate differently yet combine into one result object. However, if you need `count + sum + min + max + average` of **the same numeric field**, `summarizingLong` is usually simpler.

### 12.1. Why Should You Never Average Group Averages?

HN has 2 paid orders, HCM has 3, and DN has 1. The overall system-wide average revenue per paid order must be:

\[
\mathrm{averageAll}
= \frac{160000 + 130000 + 20000}{2 + 3 + 1}
= \frac{310000}{6}
\approx 51666.67 \text{ VND}
\]

**Never** take the unweighted mean of the three regional averages when group sizes differ:

```text
HN:  160000 / 2 = 80000
HCM: 130000 / 3 ≈ 43333.33
DN:   20000 / 1 = 20000
```

The average of those three numbers does not equal the average across all 6 orders. To combine group statistics, combine **sums** and **sample counts**, or run a single collector over the entire source.

## 13. Testing with JUnit 5

The following unit tests reference `SalesGroupReport` from Section 9. Place them in an appropriate package and add JUnit Jupiter to your project setup.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SalesGroupReportTest {

    @Test
    void countsEverySourceRowExactlyOnce() {
        var counts = SalesGroupReport.countAll(
            SalesGroupReport.sample()
        );

        long total = counts.values().stream()
            .flatMap(inner -> inner.values().stream())
            .mapToLong(Long::longValue)
            .sum();

        assertEquals(8L, total);
        assertEquals(Long.valueOf(2L), counts.get("HN").get("WEB"));
        assertEquals(Long.valueOf(1L), counts.get("DN").get("STORE"));
    }

    @Test
    void preservesSpecifiedRegionAndChannelOrder() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );

        assertEquals(List.of("HN", "HCM", "DN"),
            new ArrayList<>(report.keySet()));
        assertEquals(List.of("STORE", "WEB"),
            new ArrayList<>(report.get("HN").keySet()));
    }

    @Test
    void filteringBeforeGroupingRemovesUnpaidOnlyCell() {
        var filtered =
            SalesGroupReport.paidTotalsFilteringBeforeGrouping(
                SalesGroupReport.sample()
            );

        assertFalse(filtered.get("DN").containsKey("WEB"));
        assertEquals(Long.valueOf(80_000L),
            filtered.get("HCM").get("WEB"));
    }

    @Test
    void downstreamFilteringKeepsCellWithoutPaidSamples() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );
        var cell = report.get("DN").get("WEB");

        assertEquals(0L, cell.paidCount());
        assertEquals(0L, cell.totalVnd());
        assertTrue(cell.minVnd().isEmpty());
        assertTrue(cell.maxVnd().isEmpty());
        assertTrue(cell.averageVnd().isEmpty());
    }

    @Test
    void reportsValuesForGroupWithTwoPaidSales() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );
        var hcmWeb = report.get("HCM").get("WEB");

        assertEquals(2L, hcmWeb.paidCount());
        assertEquals(80_000L, hcmWeb.totalVnd());
        assertEquals(10_000L, hcmWeb.minVnd().orElseThrow());
        assertEquals(70_000L, hcmWeb.maxVnd().orElseThrow());
        assertEquals(40_000.0,
            hcmWeb.averageVnd().orElseThrow(), 1e-9);
    }

    @Test
    void overallCountsAndAmountsMatchControlTotals() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );

        assertEquals(6L, SalesGroupReport.overallPaidCount(report));
        assertEquals(310_000L,
            SalesGroupReport.overallPaidAmount(report));
    }

    @Test
    void emptySourceReturnsEmptyOuterMap() {
        var empty = List.<SalesGroupReport.Sale>of();

        assertTrue(SalesGroupReport.countAll(empty).isEmpty());
        assertTrue(SalesGroupReport.reportKeepingExistingGroups(
            empty
        ).isEmpty());
    }

    @Test
    void zeroAmountIsDifferentFromNoSamples() {
        var source = List.of(
            new SalesGroupReport.Sale(
                "Z1", "HN", "WEB", 0L, true
            ),
            new SalesGroupReport.Sale(
                "Z2", "DN", "STORE", 10L, false
            )
        );

        var report = SalesGroupReport.reportKeepingExistingGroups(
            source
        );

        assertEquals(1L, report.get("HN").get("WEB").paidCount());
        assertEquals(0L, report.get("HN").get("WEB").totalVnd());
        assertTrue(report.get("HN").get("WEB")
            .averageVnd().isPresent());
        assertTrue(report.get("DN").get("STORE")
            .averageVnd().isEmpty());
    }

    @Test
    void invalidInputFailsExplicitly() {
        assertThrows(NullPointerException.class, () ->
            SalesGroupReport.reportKeepingExistingGroups(null)
        );
        assertThrows(NullPointerException.class, () ->
            new SalesGroupReport.Sale(
                "X", null, "WEB", 10L, true
            )
        );
        assertThrows(IllegalArgumentException.class, () ->
            new SalesGroupReport.Sale(
                "Y", "HN", "WEB", -1L, true
            )
        );
    }
}
```

**Self-evaluation:** when assertions on **total count**, **total amount**, **empty cells**, and **key ordering** all pass, the pipeline satisfies the core exercise contracts. Unit tests do not replace validating real data domains, but they catch wrong grouping keys, dropped records, or confusing `filter` with downstream `filtering`.

## 14. Common Mistakes When Writing Multi-Level Collectors

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Filtering `paid` before grouping when unpaid-only groups must stay | Group disappears from the map | Use downstream `filtering` |
| `groupingBy(Sale::region, toList())` then manually filtering/regrouping | Multiple passes and verbose code | Nest downstream `groupingBy` |
| Calling `map(Sale::id)` before grouping by `region` | Loses region/channel fields in stream | Use downstream `mapping` |
| Using `HashMap` and trusting display order | Order is not guaranteed | Choose `LinkedHashMap` or `TreeMap` explicitly |
| Reading min/max from empty statistics | Returns sentinel constants instead of real measurements | Check `count` and use Optionals |
| Treating a zero sum as zero orders | Confused with valid zero-amount orders | Store `count` as well |
| Using `Long::sum`/`summingLong` when totals may exceed `long` | Undetected arithmetic overflow | Use big numbers or overflow checks |
| Mutating source `List` inside mapper/collector | Violates non-interference | Keep mappers and classifiers pure |
| Returning `LongSummaryStatistics` and treating it as immutable | Callers can invoke `accept/combine` | Use `collectingAndThen` into a record |
| Collecting full `toList` when only numbers are needed | Unnecessary memory growth | Use downstream `counting`/`summarizingLong` |
| Using `groupingByConcurrent` while expecting insertion order | Concurrent grouping is unordered | Group sequentially or sort after collecting |
| Writing tests that only compare `Map.equals` | Misses key-ordering bugs | Compare `List.copyOf(map.keySet())` |

## 15. Parallel Processing and Resource-Backed Sources

### 15.1. Standard Collectors Still Work with Parallel Streams

`Collectors.groupingBy` is not a concurrent collector by default, yet it works safely on `parallelStream()`: the Stream framework accumulates thread-local containers and merges them with the combiner. Never share a `HashMap` or `ArrayList` across threads via `forEach`.

However, if the report **must preserve first-encounter order of regions**, the **sequential version over an ordered `List`** is the easiest to reason about and test. For large datasets, you can consider parallel grouping followed by **sorting results in an explicit order**, after measuring costs.

`Collectors.groupingByConcurrent` returns a `ConcurrentMap` and is an unordered collector; it is not a drop-in replacement when `LinkedHashMap` ordering is required. Even when inner results are lists, do not assume list order or thread-safe concurrent writes after `collect` finishes.

### 15.2. Do Not Confuse an Empty Source with an I/O Read Failure

When data comes from `Files.lines(path)` or another I/O stream, make sure resource closing is handled explicitly:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> wordCountsByInitial(Path path)
    throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
            .flatMap(line -> java.util.Arrays.stream(
                line.strip().split("\\s+")
            ))
            .filter(word -> !word.isEmpty())
            .collect(Collectors.groupingBy(
                word -> word.substring(0, 1),
                Collectors.counting()
            ));
    }
}
```

This is a **standalone illustration of resource management**, not a `Sale` grouping variant. `Files.lines` must be closed with `try-with-resources`; if the file cannot be read, the program must throw rather than pretending the dataset was empty.

### 15.3. Memory and Performance Cost

Multi-level maps hold entries proportional to the **number of key pairs actually observed**. With many regions/channels, allocating many `TreeMap` and statistics objects per cell consumes memory. On the other hand, `summarizingLong` stores only numeric accumulators per cell, which is much cheaper than retaining full `List<Sale>` details when individual rows are not needed.

Parallel execution only helps when per-record work is substantial and keys are well-distributed. If one region or channel dominates nearly all records, merge overhead and contention can dominate. Evaluate performance via warmed-up benchmarks on representative data; never draw conclusions from a single `System.nanoTime()` measurement.

## 16. Open-Ended Extension Exercises

After completing the main program, try these extensions. Each should specify a clear **output type**, **test data**, and **empty-case contract**.

### Exercise A — Adding a Third Dimension

Add a `String productType` field to `Sale`. Build a **region → channel → productType** report with downstream `counting()`. Predict the type:

```java
Map<String, Map<String, Map<String, Long>>>
```

Write unit tests covering at least two product types in a channel and one product type absent from the source. Are absent keys created automatically?

### Exercise B — Keeping Both Paid Order Count and Total Amount

Define `record BasicCell(long count, long totalVnd)`. Replace `summarizingLong` with `Collectors.teeing(counting(), summingLong(...), BasicCell::new)` after `filtering` to produce both values. Compare against the full `Cell` in the main example.

### Exercise C — Collecting Paid Order IDs per Group

Use `mapping(Sale::id, toList())` downstream of `filtering(Sale::paid, ...)`. Require each group's list to be sorted ascending by ID. Decide how to handle duplicate IDs—**keep both**, **deduplicate**, or **throw an error**—and prove your choice with tests.

### Exercise D — Top 2 Channels by Revenue per Region

From `Map<String,Map<String,Cell>>`, produce a new structure retaining at most the top two channels by `totalVnd` for each region. Break revenue ties by channel name ascending. Specify key order in the new map, or return a ranked `List` if that expresses the contract more cleanly.

### Exercise E — Weighted Average

Add an `int itemCount` field. If the requirement asks for "average revenue **per item**", why is `averagingLong(Sale::amountVnd)` insufficient? Accumulate **total amount** and **total item count** in the same collector, handling zero denominator and overflow.

### Exercise F — Immutable Snapshot

After building the report, expose an API returning maps that cannot be mutated at **either level**, without leaking references to the original mutable maps. Test that `put` throws at both outer and inner levels while key order remains intact.

### Exercise G — Invalid Records and Error Reporting

Design boundary validation to separate valid `Sale` records from rows with bad region codes or negative amounts. Decide whether to **fail fast and halt** or **return the report alongside an error list**; never silently drop records and present the report as complete.

## 17. Self-Assessment Criteria and Decision Table

Evaluate your solution with a short checklist:

- [ ] **8 records** are counted when counting all orders.
- [ ] Exactly **6 paid records** totaling **310.000 VND**.
- [ ] Outer grouping is by `region`; inner grouping is by `channel`.
- [ ] Region order is `HN, HCM, DN` and channel order is `STORE, WEB`.
- [ ] Pre-grouping filter version **omits the DN/WEB cell**.
- [ ] Downstream `filtering` version **retains the DN/WEB cell** with count and sum equal to 0.
- [ ] Cell `DN/WEB` does not display fake min/max/average values.
- [ ] All other cells match count, sum, min, max, and average in the reference table.
- [ ] Tests cover empty source, valid `0`-amount order, and invalid inputs.
- [ ] No shared mutable state, unguaranteed map iteration order, or unchecked overflow.

| Question | Collector / Approach |
| --- | --- |
| Two grouping keys? | `groupingBy(k1, ..., groupingBy(k2, ..., downstream))` |
| Count all records in each cell? | `counting()` |
| Sum a single `long` field? | `summingLong(mapper)` |
| Need count, sum, min, max, average? | `summarizingLong(mapper)` |
| Filter while retaining groups present in source? | `filtering(predicate, downstream)` |
| Transform objects into IDs per cell? | `mapping(idMapper, toList())` |
| Convert mutable stats into a clean DTO? | `collectingAndThen(downstream, finisher)` |
| Compute two independent aggregations on the same elements? | `teeing(leftCollector, rightCollector, merger)` |
| Preserve first-encounter region order? | `LinkedHashMap::new` with ordered sequential stream |
| Sort channel names? | `TreeMap::new` |
| Represent a group with zero samples? | `count == 0` and `OptionalLong`/`OptionalDouble.empty()` |
| Report huge monetary totals accurately? | BigInteger/BigDecimal or overflow-checked accumulator |

## 18. Summary

To **build group reports with multi-level collectors**, start from the **desired result type** rather than chaining lambdas at random. The outer `groupingBy` chooses the region key; the inner `groupingBy` chooses the channel; the downstream collector determines whether to **retain details, count, sum, or summarize**. The difference between `Stream.filter` and `Collectors.filtering` controls whether an empty group remains visible. `collectingAndThen` turns mutable statistical state into a value object that cleanly handles empty subsets.

In practice, a solid report does more than get numbers right on sample data: it defines **ordering rules, missing-data policies, empty-group representation, unit tests, and arithmetic/performance boundaries** clearly. That gives you a firm base for custom collectors, concurrent grouping, and large-scale data pipelines in the Java Stream API.
