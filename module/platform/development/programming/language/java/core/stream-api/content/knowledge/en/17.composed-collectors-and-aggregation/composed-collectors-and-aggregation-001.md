# Counting and Summing per Group with counting and summing

A common problem in the Java Stream API is: **how many orders does each region have and what is the total revenue?** If you only call `count()` or `sum()` on the entire Stream, you get a single number for all the data. To get **one result per group**, combine `Collectors.groupingBy(...)` with a *downstream collector* such as `Collectors.counting()` or `Collectors.summingLong(...)`.

This lesson belongs to the **Composed Collectors and Aggregation** chapter of the **JAVA_STREAM_API** module. We will practice counting, summing, two-level grouping, combining multiple metrics, and handling groups without data. The examples also explain the relationship with lazy pipelines (`filter`, `map`, `collect`), collector contracts, numeric types, parallel processing, and performance. The focus is not on calling as many APIs as possible, but on **correctly distinguishing the grouped elements, the grouping keys, and the aggregation within each group**.

## 1. Two-level thinking: grouping and aggregation

Consider a list of orders with three main pieces of information: region, product category, and amount.

```java
import java.util.List;

record Order(
    String id,
    String region,
    String category,
    long amountVnd,
    boolean paid
) {}

List<Order> orders = List.of(
    new Order("O-01", "Bắc",   "Sách", 120_000L, true),
    new Order("O-02", "Nam",   "Bút",   30_000L, true),
    new Order("O-03", "Bắc",   "Sách",  80_000L, false),
    new Order("O-04", "Bắc",   "Bút",   50_000L, true),
    new Order("O-05", "Nam",   "Sách", 100_000L, true),
    new Order("O-06", "Trung", "Bút",   40_000L, true),
    new Order("O-07", "Tây",   "Sách",  75_000L, false)
);
```

The dataset has **7 orders**, of which **5 orders are paid**. The two unpaid orders are `O-03` and `O-07`.

If the requirement is “count the number of orders by region”, we need to create four groups: Bắc, Nam, Trung, Tây, and then count each group. You can visualize this as:

```text
                  orders.stream()
                         |
             groupingBy(Order::region)
                         |
          +--------------+---------------+-----------+
          |              |               |           |
         Bắc            Nam            Trung        Tây
      3 orders       2 orders        1 order     1 order
          |              |               |           |
      counting()     counting()      counting()  counting()
          |              |               |           |
          3L             2L              1L          1L
                         |
                  Map<String, Long>
```

Two semantically independent tasks:

1. The **classifier** of `groupingBy` determines the **key** each element belongs to.
2. The **downstream collector** determines the **value** accumulated for each key.

If you replace `counting()` with `summingLong(Order::amountVnd)`, the group keys remain the same, but each group's value changes from **order count** to **total amount**.

## 2. `Collectors.counting()`: counting elements of each group

`Collectors.counting()` is a collector used to count the number of elements passed into it. The result type is `Long`.

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> countByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(countByRegion.get("Bắc"));   // 3
System.out.println(countByRegion.get("Nam"));   // 2
System.out.println(countByRegion.get("Trung")); // 1
System.out.println(countByRegion.get("Tây"));   // 1
```

Here:

- `orders.stream()` creates a `Stream<Order>`.
- `Order::region` is a `Function<Order, String>` that selects the group key.
- `Collectors.counting()` counts the number of elements in **each group**.
- `groupingBy` creates a collector whose result is `Map<String, Long>`.
- `collect(...)` is the terminal operation that triggers Stream processing.

### 2.1. Difference between `stream.count()` and `Collectors.counting()`

```java
long totalOrders = orders.stream().count(); // 7

Map<String, Long> perRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));
```

`stream.count()` returns **one** `long` value for all remaining elements in the pipeline. `Collectors.counting()` is **a collector**, which can be placed as the downstream of `groupingBy` to return a count **separately for each group**.

| Requirement | Appropriate approach | Result type |
| --- | --- | --- |
| Count all orders | `orders.stream().count()` | `long` |
| Count orders by region | `groupingBy(Order::region, counting())` | `Map<String, Long>` |
| Count paid orders by region | `filter(Order::paid)` then `groupingBy(..., counting())` | `Map<String, Long>` |
| Count orders belonging to one region only | `filter(...).count()` | `long` |

Choose `count()` when no grouping key is needed. Choose `counting()` when the count is **the value of a collection operation**.

### 2.2. The result is `Long`, not `Integer`

`Collectors.counting()` returns `Long`, so the proper declaration is:

```java
Map<String, Long> counts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));
```

Do not declare `Map<String, Integer>` and do not cast the result by assumption. `Long` is a 64-bit integer type; for typical datasets, it is suitable for counting large numbers of records. Even so, every finite integer type has limits, and using `Long` does not make large data sources free in terms of time or memory.

## 3. `summingInt`, `summingLong`, and `summingDouble`

Whereas `counting()` counts **how many** elements there are, the `summingX` collectors compute the sum of **a numeric property** extracted from each element.

| Downstream collector | Extractor function | Result type | Typical use case |
| --- | --- | --- | --- |
| `Collectors.summingInt(...)` | `ToIntFunction<T>` | `Integer` | Sum of `int` quantities |
| `Collectors.summingLong(...)` | `ToLongFunction<T>` | `Long` | Sum of `long` values, e.g., currency in integer units |
| `Collectors.summingDouble(...)` | `ToDoubleFunction<T>` | `Double` | Sum of `double` measurements |

These three collectors take a function that **maps an element to a number**. For an `Order` object, `Order::amountVnd` is an appropriate `ToLongFunction<Order>`.

```java
Map<String, Long> amountByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));

System.out.println(amountByRegion.get("Bắc"));   // 250000
System.out.println(amountByRegion.get("Nam"));   // 130000
System.out.println(amountByRegion.get("Trung")); // 40000
System.out.println(amountByRegion.get("Tây"));   // 75000
```

This is the **sum of all orders**, including unpaid orders. If the requirement is paid revenue, you must filter by `paid` before summing or apply an intentional downstream filter.

### 3.1. `summingInt` for item quantities

```java
record CartLine(String category, int quantity) {}

List<CartLine> lines = List.of(
    new CartLine("Sách", 2),
    new CartLine("Bút", 5),
    new CartLine("Sách", 3)
);

Map<String, Integer> quantityByCategory = lines.stream()
    .collect(Collectors.groupingBy(
        CartLine::category,
        Collectors.summingInt(CartLine::quantity)
    ));

System.out.println(quantityByCategory.get("Sách")); // 5
System.out.println(quantityByCategory.get("Bút"));  // 5
```

The result is `Map<String, Integer>` because `summingInt` returns `Integer`.

### 3.2. `summingLong` for integer monetary totals

```java
Map<String, Long> paidRevenueByRegion = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));

System.out.println(paidRevenueByRegion.get("Bắc"));   // 170000
System.out.println(paidRevenueByRegion.get("Nam"));   // 130000
System.out.println(paidRevenueByRegion.get("Trung")); // 40000
System.out.println(paidRevenueByRegion.containsKey("Tây")); // false
```

Because the `"Tây"` region **has no paid orders**, it **has no key** in the resulting Map when filtering before grouping. This is an important distinction between “no group” and “a group with a total of 0”.

### 3.3. `summingDouble` for floating-point data

```java
record SensorReading(String device, double value) {}

List<SensorReading> readings = List.of(
    new SensorReading("S1", 1.25),
    new SensorReading("S1", 2.50),
    new SensorReading("S2", 3.00)
);

Map<String, Double> totalByDevice = readings.stream()
    .collect(Collectors.groupingBy(
        SensorReading::device,
        Collectors.summingDouble(SensorReading::value)
    ));

System.out.println(totalByDevice.get("S1")); // 3.75
System.out.println(totalByDevice.get("S2")); // 3.0
```

`double` uses binary floating-point numbers. For numbers that cannot be represented exactly in binary, the addition order and how partial sums are combined during parallel execution can affect the last digits of the result. Do not use `summingDouble` for currency that requires absolute decimal precision without an appropriate rounding model.

## 4. Filter before or after grouping?

`filter` in the pipeline and `Collectors.filtering` in the downstream are both useful, but **they do not produce the same set of keys**.

### 4.1. Filtering the whole source before `groupingBy`

```java
Map<String, Long> paidCounts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(paidCounts.get("Bắc"));  // 2
System.out.println(paidCounts.get("Nam"));  // 2
System.out.println(paidCounts.get("Trung")); // 1
System.out.println(paidCounts.containsKey("Tây")); // false
```

Only paid orders reach `groupingBy`. The `"Tây"` region has no grouped elements, so it **does not appear**.

### 4.2. Filtering inside each group with `Collectors.filtering`

Since Java 9, `Collectors.filtering(predicate, downstream)` allows applying a filter **during downstream collection**:

```java
Map<String, Long> paidCountsIncludingZero = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            Order::paid,
            Collectors.counting()
        )
    ));

System.out.println(paidCountsIncludingZero.get("Bắc")); // 2
System.out.println(paidCountsIncludingZero.get("Nam")); // 2
System.out.println(paidCountsIncludingZero.get("Trung")); // 1
System.out.println(paidCountsIncludingZero.get("Tây")); // 0
```

All **regions present in the source** have groups created by `groupingBy`; the downstream `filtering` does not count unpaid orders, so the `"Tây"` group gets the result `0L`.

The total amount behaves similarly:

```java
Map<String, Long> revenueIncludingZero = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            Order::paid,
            Collectors.summingLong(Order::amountVnd)
        )
    ));

System.out.println(revenueIncludingZero.get("Tây")); // 0
```

**Note:** If a region is completely absent from the source (for example, `"Đông"`), even `Collectors.filtering` will not create that key automatically. If a report must display every valid region, you need a standard catalog of regions and populate missing keys according to business rules.

### 4.3. Rules for choosing how to filter

| Requirement | Where to place `filter`? | Group with only non-matching elements |
| --- | --- | --- |
| Show only regions with paid orders | Before `groupingBy` | No key |
| Show every region that had orders, even with 0 paid revenue | Inside downstream `Collectors.filtering` | Has key with value 0 |
| Show even regions that have never had orders | Add key catalog from outside the data | Must create key explicitly |

Where you place the filter is a decision about **report semantics**, not just a different way of writing code.

## 5. Multi-level grouping: `groupingBy` nested in `groupingBy`

When a requirement has two dimensions, such as “by region then by product category”, place one `groupingBy` inside the downstream of the outer `groupingBy`.

### 5.1. Counting orders by region and product category

```java
Map<String, Map<String, Long>> countsByRegionAndCategory =
    orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
            Order::region,
            Collectors.groupingBy(
                Order::category,
                Collectors.counting()
            )
        ));

System.out.println(countsByRegionAndCategory.get("Bắc").get("Sách")); // 1
System.out.println(countsByRegionAndCategory.get("Bắc").get("Bút"));  // 1
System.out.println(countsByRegionAndCategory.get("Nam").get("Sách")); // 1
System.out.println(countsByRegionAndCategory.get("Trung").get("Bút")); // 1
```

The result type is `Map<String, Map<String, Long>>`:

- Outer Map key: `region`.
- Inner Map key: `category`.
- Innermost value: count of paid orders for the intersecting cell.

Diagram:

```text
Stream<Order> (paid orders only)
    |
    +-- groupingBy(region)
           |
           +-- Bắc
           |    +-- groupingBy(category)
           |           +-- Sách → counting() → 1L
           |           +-- Bút  → counting() → 1L
           |
           +-- Nam
           |    +-- Sách → 1L
           |    +-- Bút  → 1L
           |
           +-- Trung
                +-- Bút  → 1L
```

The nested Map structure only contains keys that actually appear after the filter step. Therefore, `countsByRegionAndCategory.get("Trung").get("Sách")` returns `null`, not automatically `0L`.

### 5.2. Summing at two levels

Simply change the collector at the final level to `summingLong`:

```java
Map<String, Map<String, Long>> revenueByRegionAndCategory =
    orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
            Order::region,
            Collectors.groupingBy(
                Order::category,
                Collectors.summingLong(Order::amountVnd)
            )
        ));

System.out.println(revenueByRegionAndCategory.get("Bắc").get("Sách")); // 120000
System.out.println(revenueByRegionAndCategory.get("Bắc").get("Bút"));  // 50000
System.out.println(revenueByRegionAndCategory.get("Nam").get("Sách")); // 100000
System.out.println(revenueByRegionAndCategory.get("Nam").get("Bút"));  // 30000
```

Although both expressions have the same outer and inner Map shape, **the meaning of the final value differs**. Name your variables, report types, and API documentation so that `count` is never confused with `amount`.

### 5.3. Order of grouping dimensions matters

`groupingBy(region, groupingBy(category, ...))` creates the outer Map by region. Swapping the order to `groupingBy(category, groupingBy(region, ...))` creates the outer Map by product category. The two reports have the same aggregated cells logically, but **their structure and access pattern differ**. Choose the outer dimension based on the primary access pattern of the business logic.

## 6. Counting and summing in a single collection pass

If you want **both order count and total amount** for each region, you could use two separate pipelines, but that may traverse the source twice:

```java
Map<String, Long> counts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region, Collectors.counting()
    ));

Map<String, Long> sums = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

With a stable `List` source, two passes are often easy to read. However, when you need **one consistent report**, you can combine two downstream collectors using `Collectors.teeing` (Java 12+).

### 6.1. `teeing` with `counting` and `summingLong`

```java
import java.util.Map;
import java.util.stream.Collectors;

record RegionStats(long orderCount, long totalVnd) {}

Map<String, RegionStats> statsByRegion = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.summingLong(Order::amountVnd),
            RegionStats::new
        )
    ));

System.out.println(statsByRegion.get("Bắc"));   // RegionStats[orderCount=2, totalVnd=170000]
System.out.println(statsByRegion.get("Nam"));   // RegionStats[orderCount=2, totalVnd=130000]
System.out.println(statsByRegion.get("Trung")); // RegionStats[orderCount=1, totalVnd=40000]
```

Both downstream collectors receive **the same elements of each group**, and then `teeing` combines the two results into a `RegionStats`:

```text
                 Each Order group
                       |
         +-------------+--------------+
         |                            |
       counting()               summingLong(amount)
         |                            |
     Long count                  Long total
         +-------------+--------------+
                       |
                 RegionStats::new
                       |
                   RegionStats
```

This is **collector composition**, not manually splitting a Stream into two branches for reuse. It also avoids introducing a mutable counter outside a lambda. When the result needs more statistics, you can use `summarizingLong` or a custom collector instead of nesting `teeing` too deeply to the point of hurting readability.

### 6.2. When you only need statistics on a single numeric field

`Collectors.summarizingLong` returns a `LongSummaryStatistics` containing `count`, `sum`, `min`, `max`, and `average`:

```java
import java.util.LongSummaryStatistics;

Map<String, LongSummaryStatistics> summaryByRegion =
    orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
            Order::region,
            Collectors.summarizingLong(Order::amountVnd)
        ));

LongSummaryStatistics north = summaryByRegion.get("Bắc");

System.out.println(north.getCount());   // 2
System.out.println(north.getSum());     // 170000
System.out.println(north.getMin());     // 50000
System.out.println(north.getMax());     // 120000
System.out.println(north.getAverage()); // 85000.0
```

If the requirement is to both count and sum **the same numeric value**, `summarizingLong` is a concise choice. If counting and summing have **different conditions**, use `teeing` with appropriate `filtering` downstreams, or define a custom aggregate collector.

## 7. Distinguishing element counts, key counts, and group counts

`counting()` counts the number of **elements** arriving at each downstream, not the number of Map keys.

```java
Map<String, Long> byRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

int numberOfRegions = byRegion.size();  // 4
long allOrders = orders.stream().count(); // 7
long northernOrders = byRegion.get("Bắc"); // 3
```

These three results answer three different questions:

| Value | Question | Result |
| --- | --- | ---: |
| `byRegion.size()` | How many distinct region keys are there? | 4 |
| `orders.stream().count()` | How many orders in total? | 7 |
| `byRegion.get("Bắc")` | How many orders does region Bắc have? | 3 |

If you want to count the number of **distinct SKUs in each region**, you need to change the downstream semantics:

```java
record Item(String region, String sku) {}

List<Item> items = List.of(
    new Item("Bắc", "P-01"),
    new Item("Bắc", "P-01"),
    new Item("Bắc", "P-02"),
    new Item("Nam", "P-01")
);

Map<String, Long> distinctSkuByRegion = items.stream()
    .collect(Collectors.groupingBy(
        Item::region,
        Collectors.mapping(
            Item::sku,
            Collectors.collectingAndThen(
                Collectors.toSet(),
                set -> (long) set.size()
            )
        )
    ));

System.out.println(distinctSkuByRegion.get("Bắc")); // 2
System.out.println(distinctSkuByRegion.get("Nam")); // 1
```

Here `counting()` is not used directly, because it would count both occurrences of `P-01`. We map elements to SKU, collect into a set of unique values, and then count the set's size. This is an example of **composed collectors**; choose the counting rule according to the exact business unit.

## 8. Empty streams, missing groups, and zero values

Empty cases must be distinguished at three levels:

1. **The entire Stream is empty:** there are no elements to create keys.
2. **A group does not appear:** the Map does not contain that key.
3. **A group has source elements, but downstream `filtering` rejects all of them:** the group can still exist with a count or sum of 0.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Order> noOrders = List.of();

Map<String, Long> emptyCounts = noOrders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(emptyCounts.isEmpty()); // true
System.out.println(emptyCounts.get("Bắc")); // null
```

`counting()` alone on an empty collection yields `0L`, but `groupingBy` **does not invoke the downstream to create results for keys that never had any element**. Therefore, an empty Map differs from a Map containing `"Bắc" -> 0L`.

### 8.1. Reading results with a default value

```java
long northCount = emptyCounts.getOrDefault("Bắc", 0L);
System.out.println(northCount); // 0
```

`getOrDefault` helps display 0 when a key is absent, but it **does not add the key to the Map**. If “no data yet” and “a group with a total of 0” are two distinct states in the business logic, do not use a default `0L` to erase the difference.

### 8.2. Initializing valid groups from a business catalog

If the UI must always display five regions, including `"Đông"` which has no orders yet:

```java
import java.util.LinkedHashMap;

List<String> regions = List.of("Bắc", "Trung", "Nam", "Tây", "Đông");

Map<String, Long> paidCounts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

Map<String, Long> complete = new LinkedHashMap<>();
for (String region : regions) {
    complete.put(region, paidCounts.getOrDefault(region, 0L));
}

System.out.println(complete);
// {Bắc=2, Trung=1, Nam=2, Tây=0, Đông=0}
```

The catalog completion step happens **after collection**. It gives exact control over which groups must exist and their display order; changing the collector alone cannot infer regions absent from the source.

## 9. Map types, key order, and multi-level grouping

`Collectors.groupingBy(classifier, downstream)` **does not guarantee** a specific Map type or key iteration order. When ordering is required, you can choose the three-parameter overload with `mapFactory`:

```java
import java.util.LinkedHashMap;
import java.util.TreeMap;

LinkedHashMap<String, Long> byFirstSeenRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.counting()
    ));

TreeMap<String, Long> bySortedRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.summingLong(Order::amountVnd)
    ));
```

With a `List` source and a **sequential** pipeline like in the example, `LinkedHashMap` iterates keys in insertion order (Bắc, Nam, Trung, Tây). `TreeMap` iterates according to `String`'s natural comparison order; this order does not necessarily match Vietnamese collation rules.

The outer Map of a two-level grouped report can be a `TreeMap` and the inner Map a `LinkedHashMap`:

```java
Map<String, Map<String, Long>> report =
    orders.stream()
        .collect(Collectors.groupingBy(
            Order::region,
            TreeMap::new,
            Collectors.groupingBy(
                Order::category,
                LinkedHashMap::new,
                Collectors.counting()
            )
        ));
```

Choose the order and Map type according to **how the result is used**, not merely for code aesthetics.

## 10. `partitioningBy` when keys have only two states

If the goal is to group by a true/false condition, such as whether an order is paid or not, `Collectors.partitioningBy` is a specialized choice.

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Long> countByPayment = orders.stream()
    .collect(Collectors.partitioningBy(
        Order::paid,
        Collectors.counting()
    ));

System.out.println(countByPayment.get(true));  // 5
System.out.println(countByPayment.get(false)); // 2
```

`partitioningBy` returns a Map containing **both `true` and `false` keys**, even when one side has no elements. Downstream `counting()` with no elements on one side returns `0L`.

```java
Map<Boolean, Long> emptyPartition = List.<Order>of()
    .stream()
    .collect(Collectors.partitioningBy(
        Order::paid,
        Collectors.counting()
    ));

System.out.println(emptyPartition.get(true));  // 0
System.out.println(emptyPartition.get(false)); // 0
```

This differs from `groupingBy(Order::paid, counting())` on an empty Stream: `groupingBy` returns an empty Map. If there are only two boolean states and both results must always be present, `partitioningBy` expresses the intent clearly.

## 11. Arithmetic precision in group aggregation

Collectors do not perform overflow checks on behalf of the application. This condition is especially important for large-volume and monetary reports.

### 11.1. `summingInt` can overflow `int`

```java
record Stock(String warehouse, int units) {}

List<Stock> stocks = List.of(
    new Stock("K1", 1_500_000_000),
    new Stock("K1", 1_500_000_000)
);

Map<String, Integer> wrongTotals = stocks.stream()
    .collect(Collectors.groupingBy(
        Stock::warehouse,
        Collectors.summingInt(Stock::units)
    ));

Map<String, Long> longTotals = stocks.stream()
    .collect(Collectors.groupingBy(
        Stock::warehouse,
        Collectors.summingLong(stock -> (long) stock.units())
    ));

System.out.println(wrongTotals.get("K1")); // -1294967296
System.out.println(longTotals.get("K1"));  // 3000000000
```

`summingInt` returns `Integer` and sums in the `int` domain. If the sum can exceed `int`, you must convert the type **before the addition**, not merely assign the resulting Map to a variable holding `Long`.

### 11.2. `summingLong` can also overflow

`Long.MAX_VALUE + 1L` does not fit in `long`. If the business logic needs an integer sum larger than the 64-bit limit, you can combine `groupingBy` with `Collectors.reducing` on `BigInteger`:

```java
import java.math.BigInteger;

record LargeTransfer(String group, long amount) {}

List<LargeTransfer> transfers = List.of(
    new LargeTransfer("A", Long.MAX_VALUE),
    new LargeTransfer("A", 1L)
);

Map<String, BigInteger> exactTotals = transfers.stream()
    .collect(Collectors.groupingBy(
        LargeTransfer::group,
        Collectors.reducing(
            BigInteger.ZERO,
            transfer -> BigInteger.valueOf(transfer.amount()),
            BigInteger::add
        )
    ));

System.out.println(exactTotals.get("A")); // 9223372036854775808
```

`BigInteger` computes the exact integer sum from the values present in the source. It does not fix bugs if an **earlier** multiplication or cast already overflowed. For decimal currency, consider `BigDecimal` and business rounding rules rather than switching to `double`.

### 11.3. `summingDouble` has floating-point limitations

`summingDouble` does not guarantee an exact decimal sum: results can vary due to binary rounding, operand magnitudes, and addition order. If the data contains `NaN` or infinity, a policy for handling abnormal measurements must be defined. For exact decimal monetary amounts, use `BigDecimal` when required by the business model.

### 11.4. The numeric type of the mapping expression also matters

With `record Line(String group, int quantity, int priceVnd)`, the following code can still overflow `int` **before `summingLong` receives the result**:

```java
// Risk of bug: int * int multiplication happens before widening to long.
Collectors.summingLong(line -> line.quantity() * line.priceVnd())
```

A more accurate approach when the product fits in the `long` range:

```java
Collectors.summingLong(
    line -> (long) line.quantity() * line.priceVnd()
)
```

If either the product or the sum can exceed the `long` range, use a larger type and check limits according to business rules.

## 12. Laziness, cost, and parallelism

`filter`, `map`, and intermediate operations are evaluated **lazily**. `collect` is the terminal operation that triggers traversal of the required elements.

```java
var selected = orders.stream()
    .filter(Order::paid); // Has not produced statistics yet.

Map<String, Long> counts = selected.collect(
    Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    )
);

// selected.count(); // Cannot reuse an already-consumed Stream.
```

### 12.1. Collection typically needs to read all data

Counting and summing per group is not a short-circuiting search: for a finite dataset, groups must receive all elements within the computation scope. The resulting Map has the storage cost of **one entry per group key**; with two-level grouping, there is also a Map for each outer group and entries in each sub-Map.

`groupingBy(..., counting())` does not store all elements into lists like the default `groupingBy(...)`; it only holds the state required for counting. Similarly, `summingLong` avoids storing all transactions in each group. This is an important benefit of choosing a downstream matching the required result.

### 12.2. `parallelStream` is not faster by default

```java
Map<String, Long> parallelTotals = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

Standard `groupingBy` **is not a concurrent collector**; when running in parallel, the framework may accumulate into separate Maps and then **combine** them. Combining many Maps can be costly if the number of keys is large.

If appropriate for order-independent business logic, you can consider:

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> concurrentTotals = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

`groupingByConcurrent` is a concurrent, unordered collector. The downstream `summingLong` does not need to change itself into a variable shared across threads; the framework is responsible for coordination to preserve correctness under the contract. Using `groupingByConcurrent` also **does not** guarantee it is always faster than `groupingBy`: data with few keys and very many elements sharing the same key can cause contention.

Parallelization does not fix integer overflow, does not resolve floating-point errors, and does not permit arbitrarily mutating an external `HashMap` from `forEach`.

### 12.3. Avoid mutable state outside the Collector

Example to avoid:

```java
// Unsafe, especially with parallelStream():
Map<String, Long> mutableTotals = new java.util.HashMap<>();

orders.parallelStream().forEach(order ->
    mutableTotals.merge(
        order.region(),
        order.amountVnd(),
        Long::sum
    )
);
```

This snippet updates a shared `HashMap` from multiple threads without proper synchronization. Use `groupingBy`/`groupingByConcurrent` with an appropriate downstream; the collector manages accumulation state, the combiner, and thread-safety requirements.

For sources tied to I/O resources, such as `Files.lines(path)`, close the Stream with `try-with-resources` even when the terminal operation is `collect`. Performance cost depends on element count, group count, mapper, Map structure, numeric types, and contention; measure with representative data, such as JMH, before optimizing.

## 13. Complete example: multi-level statistics and dual metrics

The following code runs on **Java 17+** (using `record`, `Collectors.filtering`, and `Collectors.teeing`). It aggregates several common reports over the same source list in one pass each; each report creates **a new Stream**, because a Stream cannot be reused after a terminal operation.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupedAggregationDemo {
    record Order(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    record RegionStats(long count, long totalVnd) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc",   "Sách", 120_000L, true),
            new Order("O-02", "Nam",   "Bút",   30_000L, true),
            new Order("O-03", "Bắc",   "Sách",  80_000L, false),
            new Order("O-04", "Bắc",   "Bút",   50_000L, true),
            new Order("O-05", "Nam",   "Sách", 100_000L, true),
            new Order("O-06", "Trung", "Bút",   40_000L, true),
            new Order("O-07", "Tây",   "Sách",  75_000L, false)
        );

        // 1. Count all orders by region.
        Map<String, Long> allCounts = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));

        // 2. Count paid orders, keeping regions that only have unpaid orders.
        Map<String, Long> paidCounts = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.filtering(
                    Order::paid,
                    Collectors.counting()
                )
            ));

        // 3. Total paid revenue by region.
        Map<String, Long> revenue = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));

        // 4. Count paid orders by both region and product category.
        Map<String, Map<String, Long>> byRegionAndCategory =
            orders.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                    Order::region,
                    Collectors.groupingBy(
                        Order::category,
                        Collectors.counting()
                    )
                ));

        // 5. One report per region: both order count and total amount.
        Map<String, RegionStats> combined = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingLong(Order::amountVnd),
                    RegionStats::new
                )
            ));

        System.out.println(allCounts.get("Bắc"));           // 3
        System.out.println(paidCounts.get("Tây"));          // 0
        System.out.println(revenue.get("Bắc"));             // 170000
        System.out.println(revenue.containsKey("Tây"));     // false
        System.out.println(
            byRegionAndCategory.get("Nam").get("Sách")
        );                                                  // 1
        System.out.println(combined.get("Bắc"));
        // RegionStats[count=2, totalVnd=170000]
    }
}
```

Analyzing the five results:

| Report | Return type | Tây group | Meaning |
| --- | --- | --- | --- |
| `allCounts` | `Map<String, Long>` | 1 | Counts all orders, regardless of payment |
| `paidCounts` | `Map<String, Long>` | 0 | Group exists, but no order satisfies the downstream condition |
| `revenue` | `Map<String, Long>` | No key | Stream filtered out all orders in Tây before grouping |
| `byRegionAndCategory` | `Map<String, Map<String, Long>>` | No key | Two-dimensional report containing only paid orders |
| `combined` | `Map<String, RegionStats>` | No key | A result containing both order count and total amount for each remaining group |

Do not rely on the print order of a `Map` unless you choose a `mapFactory` that guarantees ordering. The `get(...)` calls in the example inspect specific keys individually, so they do not require the Map to iterate in any particular order.

## 14. Common mistakes and fixes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Calling `stream.count()` expecting counts per key | Receives only the Stream-wide total | Place `counting()` as the downstream of `groupingBy` |
| Declaring `Map<K, Integer>` with `counting()` | Wrong return type | Use `Map<K, Long>` |
| Assuming `summingInt` works for all integer sums | Can overflow `int` | Use `summingLong` after widening the type, or a higher-precision integer type |
| Using `summingLong` while multiplication in mapper is still `int * int` | Intermediate value can overflow | Cast one operand before multiplying |
| Filtering before grouping and expecting a key with value 0 | Completely filtered-out groups do not appear | Use downstream `filtering` if you want to keep keys present in the source |
| Assuming downstream `filtering` will also create groups never present in the source | Cannot infer nonexistent keys | Explicitly populate from a business key catalog |
| Treating `get(key) == null` as a total of 0 without checking semantics | Confuses missing group with zero-valued group | Use `containsKey` or a result type expressing all states |
| Counting records with `counting()` when wanting distinct value counts | Counts duplicates | `mapping` to the unique key, `toSet`, then take size |
| Using two-level `groupingBy` but reading keys in the wrong order | Accesses the wrong report dimension | Clearly identify which dimension is the outer Map and which is the inner Map |
| Taking an unweighted average of two group averages for the overall average | Wrong when group sizes differ | Combine `sum` and `count` first, then divide |
| Assuming the returned Map preserves appearance order | Not guaranteed by the default overload | Use `LinkedHashMap::new`/`TreeMap::new` as needed |
| Summing decimal money with `summingDouble` and assuming exact precision | Floating-point precision errors | Use `BigDecimal` and appropriate rounding rules |
| Reusing the same Stream for multiple reports | Stream already consumed; throws exception | Create a new Stream or compose collectors intentionally |
| Mutating an external `HashMap` via `parallelStream().forEach(...)` | Race condition, corrupted data | Use a collector that honors the contract |
| Assuming `groupingByConcurrent` is always faster | Can cause key contention and increased overhead | Measure on actual data, group count, and key distribution |

## 15. Practice exercises

### Exercise 1: Count by product category

Using the `Order` list in section 1, use `groupingBy(Order::category, counting())` to count all orders by category. Compare with a pipeline that counts only paid orders and explain why the two reports have different meanings.

### Exercise 2: Paid revenue

Use `filter(Order::paid)`, `groupingBy(Order::region, summingLong(Order::amountVnd))` to compute revenue per region. Check the `"Tây"` region specifically and explain why this key does not appear.

### Exercise 3: Counting with zero values

Rewrite exercise 2's report using `groupingBy(Order::region, filtering(Order::paid, summingLong(...)))`. Compare `containsKey("Tây")`, `get("Tây")`, and `getOrDefault("Đông", 0L)`. What do these three checks tell you about data existence?

### Exercise 4: Two-level grouping

Create a `Map<String, Map<String, Long>>` counting paid orders by `category` first, then `region`. Compare the access pattern with `groupingBy(region, groupingBy(category, ...))`.

### Exercise 5: Counting and summing in one pass

Use `Collectors.teeing(counting(), summingLong(...), RegionStats::new)` to produce a `RegionStats` for each region. If you also need the maximum value, consider `summarizingLong` and explain when it is simpler than `teeing`.

### Exercise 6: Precision in aggregation

Given two warehouse records in the same group, each with `1_500_000_000` units, compare `summingInt` with `summingLong`; explain the cause of overflow and when the type conversion must happen. Then build a group whose total exceeds `Long.MAX_VALUE` using `BigInteger`.

### Exercise 7: Groups without data

Create a region catalog containing Bắc, Trung, Nam, Tây, and Đông. From a `Map` containing only regions with paid transactions, build a complete five-key report, setting `0L` when there are no figures. State when replacing missing data with 0 is appropriate and when the “no data yet” state must be preserved.

### Exercise 8: Evaluating parallelism

With a dataset containing many orders across only two regions, compare `groupingBy` and `groupingByConcurrent` under parallel execution. Explain the contention risk when there are few keys, the impact of the `combiner`, and why you should measure on a representative workload rather than choosing solely by API name.

## 16. Self-check questions

- How does `Collectors.counting()` differ from `Stream.count()`?
- In `groupingBy(classifier, downstream)`, which component determines the key and which determines the value?
- What types do `summingInt`, `summingLong`, and `summingDouble` return?
- Why can total revenue differ when placing `filter` before versus after grouping?
- When should you use `Collectors.filtering` to keep groups with a result of 0?
- How does `Map<K1, Map<K2, Long>>` represent two grouping dimensions?
- When is `teeing` more suitable than running two independent pipelines?
- In what situations can `summarizingLong` replace `counting` and `summingLong`?
- Why is an absent group different from a group with a sum of 0?
- How does `partitioningBy` on an empty source differ from `groupingBy`?
- Why does `summingLong` not solve every overflow and precision risk?
- Why must group count and key distribution be considered in parallel processing?

**Key takeaway:** To count or sum **per group**, place `Collectors.counting()` or `Collectors.summingInt/summingLong/summingDouble(...)` as the **downstream** of `groupingBy`. To add another reporting dimension, nest `groupingBy`; to compute multiple metrics in one result, consider `teeing` or `summarizingLong`. Always distinguish between **a group without a key**, **a group with a result of 0**, and **numeric values that can overflow or lose precision** before delivering reports to business logic.
