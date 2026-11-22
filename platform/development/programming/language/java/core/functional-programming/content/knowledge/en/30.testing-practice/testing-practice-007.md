# Practicing Grouping Data and Generating Reports with `Collector` in Java Streams

In real-world applications, data rarely needs just a single total. We often have to **filter by business conditions, group across multiple levels, compute metrics, produce reports in a deterministic order**, and then test results at each level. Java Streams provide built-in `Collector` implementations such as `groupingBy`, `counting`, `summingLong`, `filtering`, `mapping`, and `teeing` to organize that work without mutating a shared `Map` inside `forEach`.

This lab uses **Java 17+** and designs an order revenue report by **region** and **category**, moving from requirements → sample data → `record` design → pipeline → results → testing → extension exercises. It pays special attention to distinguishing a **non-existent** group from a group with a **count of 0**, preserving report output order, and keeping I/O out of computation lambdas.

## 1. Context and Business Requirements

A sales system has records with:

- Order ID `id`.
- Region `region` (e.g., `North`, `South`, `Central`).
- Product category `category` (`Books`, `Toys`).
- Order value in **cents** `revenueCents`, of type `long`.
- Status `paid`: `true` if paid; `false` if unpaid.

Report rules:

1. **Sum revenue only for paid orders.** Unpaid orders must not be included in total revenue.
2. **Detailed report** structured as `Map<region, Map<category, Stats>>`. At the leaf, `Stats` contains `count` and `revenueCents`.
3. Provide **totals by region**, **totals by category**, and an **overall total** for reconciliation.
4. **Sort report keys** in natural order using `TreeMap`; do not rely on the incidental order of `HashMap`.
5. Provide a separate metric for **the number of paid orders per region appearing in the original data**, even for regions that only have unpaid orders. This is an opportunity to use downstream `Collectors.filtering()`.
6. Validate order data and reconcile totals across levels without relying on side effects in `peek` or `forEach`.

The first goal is **semantic correctness and testability**. If data is large enough to require pagination or a database, the query and storage strategy may need to change; this example illustrates reporting on an in-memory list.

## 2. Sample Input Data

Data used throughout the lab:

| ID | Region | Category | Revenue (cent) | Paid |
| --- | --- | --- | ---: | --- |
| S01 | North | Books | 1200 | Yes |
| S02 | South | Toys | 3500 | Yes |
| S03 | North | Books | 800 | Yes |
| S04 | North | Toys | 7000 | No |
| S05 | South | Books | 1500 | Yes |
| S06 | North | Toys | 2500 | Yes |
| S07 | South | Toys | 500 | Yes |
| S08 | Central | Books | 1800 | Yes |
| S09 | Central | Toys | 900 | No |
| S10 | South | Books | 0 | Yes |
| S11 | West | Toys | 1200 | No |

Only **8 orders are paid**: `S01`, `S02`, `S03`, `S05`, `S06`, `S07`, `S08`, `S10`. Paid revenue:

```text
North:   Books 1200 + 800; Toys 2500             = 4500
South:   Books 1500 + 0; Toys 3500 + 500         = 5500
Central: Books 1800                               = 1800
West:    no paid orders                           = 0
Overall: 4500 + 5500 + 1800                      = 11800
```

`S10` has revenue 0 but is **still a paid order**, so it is counted in `count`. Conversely, `S11` in `West` is unpaid so it does not appear in the paid-only revenue report, yet `West` can appear in the count metric that preserves groups from the original data.

## 3. Designing Data Types and Needed Collectors

We use two `record` types:

```java
record Sale(
        String id,
        String region,
        String category,
        long revenueCents,
        boolean paid
) {}

record Stats(long count, long revenueCents) {}
```

These are illustrative types, not a standalone runnable program. In the complete program, `Sale` includes field validation.

The collector for `Stats` combines two aggregations using `teeing` (Java 12+):

```java
static Collector<Sale, ?, Stats> statsCollector() {
    return Collectors.teeing(
            Collectors.counting(),
            Collectors.summingLong(Sale::revenueCents),
            Stats::new
    );
}
```

Explanation:

- `counting()` produces `Long`, counting each source element.
- `summingLong(Sale::revenueCents)` produces `Long`, summing element revenues.
- `Stats::new` receives the two `Long` results, auto-unboxes them to `long`, and constructs a `Stats` with both fields.
- The type `Collector<Sale, ?, Stats>` has `?` because **the accumulation container type `A` is an implementation detail** of the collector; callers only need to know the input is `Sale` and the result is `Stats`.

`teeing` aggregates multiple metrics in **a single collection pass** with coordinated downstream collectors. Another option is a custom `Collector.of` maintaining a `(sum, count)` pair; using standard collectors keeps the lab concise and less error-prone.

### Target data structure tree

```text
Map<String, Map<String, Stats>>
              |
              +-- Central
              |      +-- Books -> Stats(1, 1800)
              |
              +-- North
              |      +-- Books -> Stats(2, 2000)
              |      +-- Toys  -> Stats(1, 2500)
              |
              +-- South
                     +-- Books -> Stats(2, 1500)
                     +-- Toys  -> Stats(2, 4000)
```

Because the revenue report only considers `paid` orders, the `West` key **is not created** in this tree. `TreeMap` guarantees keys are ordered naturally; the presentation above follows that order.

## 4. Complete Java 17+ Solution

Save the following code to **`SalesReportDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class SalesReportDemo {
    record Sale(
            String id,
            String region,
            String category,
            long revenueCents,
            boolean paid
    ) {
        Sale {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            Objects.requireNonNull(category, "category");
            if (id.isBlank() || region.isBlank() || category.isBlank()
                    || revenueCents < 0) {
                throw new IllegalArgumentException("Invalid Sale");
            }
        }
    }

    record Stats(long count, long revenueCents) {}

    static Collector<Sale, ?, Stats> statsCollector() {
        return Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Sale::revenueCents),
                Stats::new
        );
    }

    // Detailed report: region -> category -> stats.
    static Map<String, Map<String, Stats>> byRegionAndCategory(
            List<Sale> sales
    ) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Sale::category,
                                TreeMap::new,
                                statsCollector()
                        )
                ));
    }

    // Total by region, paid orders only.
    static Map<String, Stats> byRegion(List<Sale> sales) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        statsCollector()
                ));
    }

    // Total by category, paid orders only.
    static Map<String, Stats> byCategory(List<Sale> sales) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        statsCollector()
                ));
    }

    // Overall total of paid orders.
    static Stats overall(List<Sale> sales) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(statsCollector());
    }

    // Keep keys for regions that only have unpaid orders.
    static Map<String, Long> paidCountIncludingEmptyGroups(
            List<Sale> sales
    ) {
        return sales.stream().collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.counting()
                )
        ));
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("S01", "North", "Books", 1200, true),
                new Sale("S02", "South", "Toys", 3500, true),
                new Sale("S03", "North", "Books", 800, true),
                new Sale("S04", "North", "Toys", 7000, false),
                new Sale("S05", "South", "Books", 1500, true),
                new Sale("S06", "North", "Toys", 2500, true),
                new Sale("S07", "South", "Toys", 500, true),
                new Sale("S08", "Central", "Books", 1800, true),
                new Sale("S09", "Central", "Toys", 900, false),
                new Sale("S10", "South", "Books", 0, true),
                new Sale("S11", "West", "Toys", 1200, false)
        );

        Map<String, Map<String, Stats>> detail =
                byRegionAndCategory(sales);
        Map<String, Stats> regions = byRegion(sales);
        Map<String, Stats> categories = byCategory(sales);
        Stats total = overall(sales);
        Map<String, Long> paidCounts =
                paidCountIncludingEmptyGroups(sales);

        // Cross-check results including empty cases.
        check(total.equals(new Stats(8, 11800)),
                "Wrong overall total");
        check(detail.get("North").get("Books")
                        .equals(new Stats(2, 2000)),
                "Wrong North/Books group");
        check(!detail.containsKey("West"),
                "West must not be in revenue report");
        check(paidCounts.get("West") == 0L,
                "West must have paid count 0");
        check(overall(List.of()).equals(new Stats(0, 0)),
                "Empty source must yield total 0");
        check(byRegionAndCategory(List.of()).isEmpty(),
                "Empty source has no groups");
        check(regions.values().stream()
                        .mapToLong(Stats::revenueCents).sum()
                        == total.revenueCents(),
                "Regional totals do not match");

        System.out.println("DETAIL:");
        detail.forEach((region, byCategory) ->
                byCategory.forEach((category, stats) ->
                        System.out.println(region + "/" + category
                                + " = " + stats.count()
                                + " orders, " + stats.revenueCents()
                                + " cents")
                )
        );

        System.out.println("BY REGION:");
        regions.forEach((region, stats) ->
                System.out.println(region + " = " + stats.count()
                        + " orders, " + stats.revenueCents() + " cents")
        );

        System.out.println("BY CATEGORY:");
        categories.forEach((category, stats) ->
                System.out.println(category + " = " + stats.count()
                        + " orders, " + stats.revenueCents() + " cents")
        );

        System.out.println("TOTAL = " + total.count()
                + " orders, " + total.revenueCents() + " cents");
        System.out.println("PAID COUNTS = " + paidCounts);
        System.out.println("CHECKS = PASS");
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac -encoding UTF-8 SalesReportDemo.java
java SalesReportDemo
```

**Deterministic** stdout (because `TreeMap` sorts keys and the program does not print from parallel callbacks):

```text
DETAIL:
Central/Books = 1 orders, 1800 cents
North/Books = 2 orders, 2000 cents
North/Toys = 1 orders, 2500 cents
South/Books = 2 orders, 1500 cents
South/Toys = 2 orders, 4000 cents
BY REGION:
Central = 1 orders, 1800 cents
North = 3 orders, 4500 cents
South = 4 orders, 5500 cents
BY CATEGORY:
Books = 5 orders, 5300 cents
Toys = 3 orders, 6500 cents
TOTAL = 8 orders, 11800 cents
PAID COUNTS = {Central=1, North=3, South=4, West=0}
CHECKS = PASS
```

The main report uses paid records; `S04`, `S09`, and `S11` are not added to revenue. Order `S10` has value 0 yet still increments `count` of the `South/Books` group. Because `Stats` is a `record`, value-based `equals()` allows checking `Stats(8, 11800)` directly.

## 5. Explaining the Most Important Pipeline

The most important part is:

```java
return sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        statsCollector()
                )
        ));
```

This is a snippet from `byRegionAndCategory` in the class above.

Reading from outside in:

1. `filter(Sale::paid)`: lets only paid elements enter the collector.
2. `groupingBy(Sale::region, TreeMap::new, ...)`: partitions elements by region. `TreeMap::new` controls outer key ordering.
3. Downstream `groupingBy(Sale::category, TreeMap::new, statsCollector())`: within **each region**, groups by category and uses a `TreeMap` for inner keys.
4. `statsCollector()`: for orders with the **same region and category**, counts orders and sums cents.
5. The result has type `Map<String, Map<String, Stats>>`; not a `List` or flat map.

For example, `North/Books` receives `S01` and `S03`, so the count is 2 and total revenue is `1200 + 800 = 2000`. `North/Toys` only receives `S06` because `S04` is unpaid, so it has 1 order and 2500 cents.

### Why not use the default `HashMap` to print stdout?

`Collectors.groupingBy(classifier, downstream)` **does not guarantee** a specific `Map` implementation or key iteration order. Printing the default map directly and documenting a fixed stdout order could mislead readers.

The example uses the **three-argument** overload:

```java
Collectors.groupingBy(classifier, TreeMap::new, downstream)
```

As a result, `region` and `category` are traversed in `String` natural order. Sorting keys does not mean the program sorted the `Sale` records or removed duplicates.

## 6. `filter()` Before Grouping vs. `Collectors.filtering()` Inside Grouping

This is the most common source of confusion.

**Filtering before grouping:**

```java
Map<String, Long> result = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.counting()
        ));
```

With the sample source, key `West` **does not exist** because all `West` sales were removed at the `filter` step.

**Grouping first and filtering in downstream:**

```java
Map<String, Long> result = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.counting()
                )
        ));
```

The `West` group is created because input data exists for `West`. Downstream then counts only paid elements, so `West` gets `0`. Both snippets sit inside a method with `sales` and imports `java.util.Map`, `java.util.stream.Collectors`; they are not standalone programs.

| Approach | Region with only unpaid orders | When to use |
| --- | --- | --- |
| `stream.filter(paid).collect(groupingBy(region, counting()))` | **No key** | Report includes only regions with qualifying orders |
| `stream.collect(groupingBy(region, filtering(paid, counting())))` | **Key present with count 0** | Report includes every region seen, explicitly showing 0 paid orders |

Do not confuse `0` with `null`: `map.get("West")` is `0L` when the key is present, but `null` when the key is absent.

## 7. Keeping Money Data Types and Controlling Precision

The example uses `long revenueCents`, not `double`, to store money. Summing integer cents avoids binary floating-point representation errors, but **`long` still has limits**.

`Collectors.summingLong(Sale::revenueCents)` uses `long` addition; it **does not detect overflow by default**. With real data that could exceed limits, strategies are needed such as:

- Bounding input values and total sizes per business contract.
- Using checked addition `Math.addExact` in an appropriate custom collector.
- Using `BigDecimal` when representing multiple currencies, decimals, and defined rounding policies.

Do not implicitly treat `revenueCents=0` as “unpaid”; `paid` is a separate business field. Example `S10` illustrates that a paid order can have 0 revenue.

If an **average value** is needed, state clearly “average per paid order”, especially when zero-value orders exist. `Collectors.averagingLong(Sale::revenueCents)` returns `Double` and has floating-point precision limits; do not use it arbitrarily to determine exact cent amounts payable.

## 8. More Report Types Using Downstream Collectors

### 8.1. Listing only paid order IDs in each region

```java
Map<String, List<String>> paidIdsByRegion = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.mapping(
                        Sale::id,
                        Collectors.toList()
                )
        ));
```

This is a snippet inside `SalesReportDemo` or a method with `sales`; it requires importing `Map`, `List`, `TreeMap`, and `Collectors`.

`mapping(Sale::id, toList())` keeps one attribute without retaining entire `Sale` objects in the result list. If you only need the count, do not collect IDs just to take `.size()`; `counting()` is more appropriate.

### 8.2. Partitioning paid/unpaid

```java
Map<Boolean, Long> paidVsUnpaid = sales.stream()
        .collect(Collectors.partitioningBy(
                Sale::paid,
                Collectors.counting()
        ));
// false = 3, true = 8
```

`partitioningBy` splits groups by the two Boolean keys `true` and `false`; it differs from `groupingBy` in that both branches are always represented, even if one branch is empty.

### 8.3. Using `summarizingLong()` instead of `teeing()`

```java
Map<String, java.util.LongSummaryStatistics> summary =
        sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::region,
                        Collectors.summarizingLong(
                                Sale::revenueCents
                        )
                ));
```

Each `LongSummaryStatistics` provides `getCount()`, `getSum()`, `getMin()`, `getMax()`, and `getAverage()`. If the report also needs min/max/average, it can be more convenient than a two-field `Stats`.

Note that `LongSummaryStatistics.getSum()` also has `long` range limits; statistics themselves do not replace overflow-control and arithmetic-precision policies.

## 9. Transforming Result Maps into Text Reports

`byRegionAndCategory`, `byRegion`, `byCategory`, and `overall` only compute data. Printing happens at the end of `main`:

```java
detail.forEach((region, groups) ->
        groups.forEach((category, stats) ->
                System.out.println(
                        region + "/" + category + " = "
                        + stats.count() + " orders, "
                        + stats.revenueCents() + " cents"
                )
        )
);
```

Because inputs are `TreeMap` instances, traversal for printing has deterministic order. However, if you want to **return the report as a `String`** instead of printing to console, you can use a `render` function:

```java
static String render(Map<String, Map<String, Stats>> detail) {
    StringBuilder out = new StringBuilder();

    detail.forEach((region, categories) ->
            categories.forEach((category, stats) ->
                    out.append(region).append("/")
                            .append(category).append(": ")
                            .append(stats.count()).append(", ")
                            .append(stats.revenueCents())
                            .append("\n")
            )
    );

    return out.toString();
}
```

This is an **illustrative method** added to `SalesReportDemo`, not independently runnable. `StringBuilder` is a **local variable of `render`**, not shared with a parallel stream; the function only builds a new string and does not write files or console. Therefore tests can compare the rendered string directly. For more complex number and currency formatting rules, specify locale/currency/rounding explicitly.

To output a file or HTTP response, build the `String` first and perform I/O at the application boundary. Do not put `Files.writeString` inside `map`, `peek`, or a `groupingBy` classifier.

## 10. Testing and Reconciling Reports

Beyond checking “runs without error”, the lab should verify business conditions:

| Condition | Expected value |
| --- | --- |
| Total paid orders | 8 |
| Total paid revenue | 11800 |
| `North/Books` | `Stats(2,2000)` |
| `South/Toys` | `Stats(2,4000)` |
| Total North revenue | 4500 |
| Total South revenue | 5500 |
| Total Central revenue | 1800 |
| West revenue group | Does not exist |
| West paid count in all-region report | 0 |
| Sum of all regions | Equals overall total |
| Sum of all categories | Equals overall total |
| Empty source | Total `Stats(0,0)`, group maps empty |

The complete program already includes several checks in `main`. You can add an independent check for categories:

```java
long sumByCategory = categories.values().stream()
        .mapToLong(Stats::revenueCents)
        .sum();

check(sumByCategory == total.revenueCents(),
        "Category totals do not match");
```

This snippet runs inside `main`, using the already-declared `categories`, `total`, and `check`.

### Testing the unpaid-only case

```java
List<Sale> unpaidOnly = List.of(
        new Sale("U01", "West", "Books", 900, false)
);

check(byRegionAndCategory(unpaidOnly).isEmpty(),
        "No paid groups");
check(overall(unpaidOnly).equals(new Stats(0, 0)),
        "Paid total must be 0");
check(paidCountIncludingEmptyGroups(unpaidOnly)
                .get("West") == 0L,
        "West must be kept with count 0");
```

This snippet runs inside `main` or a test method of `SalesReportDemo`, not a separate file. It verifies the difference between **groups dropped before collecting** and **groups kept with downstream count 0**.

### What should be checked if switching to a parallel stream?

If you want to replace `sales.stream()` with `sales.parallelStream()`, verify that totals/groups still have the same values. The standard collectors used here are designed to combine branches per contract, and `TreeMap` presents keys in clear order after collection.

However:

- Do not assume thread count or execution timing order of `classifier` and `downstream` functions.
- Do not add side effects to `map`/`filter`/classifier or manually mutate a shared `HashMap`.
- Do not assume `Collectors.groupingByConcurrent` always preserves encounter order; concurrency and ordering needs must be evaluated separately.
- For small datasets, parallelism overhead can outweigh benefits. Benchmark only when the real problem is sufficiently complex.

## 11. Common Mistakes in Grouping and Reporting

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Grouping all orders and summing revenue while forgetting `paid` | Revenue includes unpaid orders | `filter(Sale::paid)` before grouping or downstream `filtering` per requirement |
| Counting records with positive revenue | Drops paid orders with value 0 | Count by `paid` status, not `revenueCents > 0` |
| Using `groupingBy(region)` when two levels are needed | Leaves are just `List<Sale>` | Nest `groupingBy(category, downstream)` |
| Mistaking `counting()` return type for `Integer` | Generic type mismatch | Use `Long` |
| Mistaking `teeing` for a Java 8 collector | Fails to compile on older JDKs | Use Java 12+ or an equivalent custom collector |
| Using `HashMap` then documenting fixed stdout order | Iteration order is not guaranteed | `TreeMap::new` at levels needing sorting |
| Accessing `map.get(a).get(b)` when outer key is missing | `NullPointerException` | Check key or use `getOrDefault` |
| Expecting every category in every region | Groups with no data are not auto-created | Represent zero-groups per report policy |
| Using `Collectors.toMap` with duplicate keys | Can throw `IllegalStateException` | Use `groupingBy` or an explicit merge function |
| Classifier returns `null` | `groupingBy` typically throws `NullPointerException` | Validate or normalize keys |
| Computing revenue with `double` assuming cent precision | Risk of monetary rounding error | Use integer cents or `BigDecimal` with policy |
| Forgetting `long` range limits | Sums can overflow | Validate/monitor or use checked addition |
| Updating a shared `Map` in `parallelStream().forEach` | Races and wrong totals | Use `collect(groupingBy(...))` |
| Using `peek` for mandatory business counting/logging | Intermediate callback lacks aggregation execution guarantees | Use terminal operations and clear I/O boundaries |

## 12. Extension Exercises

After running the program successfully, modify or add each requirement below, **writing the expected result before running the program**.

### Exercise A — unpaid orders report

Add `byRegionUnpaid` returning `Map<String, Stats>` containing only `paid == false` orders. With the sample data:

```text
Central = Stats[count=1, revenueCents=900]
North   = Stats[count=1, revenueCents=7000]
West    = Stats[count=1, revenueCents=1200]
```

Note this is **total recorded value on unpaid orders**, not collected revenue. Do not confuse its label with the paid revenue report.

**Hint:** change the predicate to `filter(sale -> !sale.paid())` and use `groupingBy(Sale::region, TreeMap::new, statsCollector())`.

### Exercise B — average revenue per paid order

Add `averageRevenueCents` by region using `Collectors.averagingLong(Sale::revenueCents)` or by dividing `revenueCents / count` from `Stats`. With the sample data:

```text
Central: 1800.0
North:   1500.0
South:   1375.0
```

When rounding cents in financial domains, a defined rounding rule is required; `Double` is suitable only for statistical illustration. Region `West` has no paid orders so **do not arbitrarily assign average 0** unless the reporting policy explicitly specifies it.

### Exercise C — top category indicator

Find the category with the highest paid total revenue. With the sample data, `Toys = 6500` cents and `Books = 5300` cents, so `Toys` is first.

**Hint:** use `byCategory(sales).entrySet().stream().max(Comparator.comparingLong(e -> e.getValue().revenueCents()))`. `max` returns `Optional` because the source may be empty. If multiple categories tie, define a tie-breaking rule before writing tests.

### Exercise D — building a CSV report

Create a pure `renderCsv(detail)` function returning the string:

```text
region,category,count,revenueCents
Central,Books,1,1800
North,Books,2,2000
North,Toys,1,2500
South,Books,2,1500
South,Toys,2,4000
```

Only after obtaining the string, use `Files.writeString` in an outer layer. If `region` or `category` values may contain commas, quotes, or newlines, standard CSV escaping is required; this basic example intentionally uses simple values.

### Exercise E — testing report equivalence

Write a test function computing the same report with `stream()` and `parallelStream()`, then compare the two maps with `.equals()`. Also test an empty source, unpaid-only orders, a 0-revenue order, and invalid input cases. **Do not compare callback order** in parallel runs: what to verify is the final result per the collector contract.

## 13. Self-Assessment Questions

**1.** Why does `groupingBy(region, groupingBy(category, teeing(...)))` return a nested `Map`?

Because the outer `groupingBy` receives a downstream collector whose result is `Map<category, Stats>`; therefore the value of `Map<region,...>` is an inner map.

**2.** Why does `S10` with `revenueCents=0` still increment `count`?

Because the rule checks only `paid` status, not positive revenue. `counting()` counts every element reaching downstream.

**3.** Why is `West` absent from `byRegionAndCategory` yet present in `paidCountIncludingEmptyGroups`?

Because the first filters out all unpaid orders **before** grouping; the second creates groups from the original data and applies `filtering` **inside downstream**, so `West` keeps its key with count 0.

**4.** Why choose `TreeMap::new` at both levels if you want to print the report in key order?

To get deterministic traversal order for `region` and `category`. Default `groupingBy` does not promise map iteration order.

**5.** What problem does `Collectors.teeing` solve?

It feeds the same elements to two downstream collectors and combines both results into a desired type, here `Stats(count, revenueCents)`.

**6.** If you only need the number of records in a group, should you collect a full list and call `.size()`?

No. Use `counting()` to avoid allocating a list just to count.

**7.** Should you use `parallelStream().forEach(sharedMap::put)` instead of grouping?

No. Concurrent writes to an external map can race; moreover, one key can have multiple records and `put` overwrites without merging. Use `collect(groupingBy(...))`.

## Key Takeaways

- **Multi-dimensional reports**: `groupingBy(key1, mapFactory, groupingBy(key2, mapFactory, downstream))`.
- **Multiple metrics on the same group**: `teeing(counting(), summingLong(...), Stats::new)` or a corresponding summary collector.
- **Right business condition**: place `filter` before grouping to drop non-qualifying groups completely; use downstream `filtering` to retain keys of seen groups.
- **Display ordering**: specify `TreeMap` or an explicit sorting strategy; do not rely on `HashMap`.
- **Reconciliation tests**: totals by region, category, and overall must be consistent; also test missing groups, 0-count groups, and empty sources.
- **Keep pipelines pure**: compute data with collectors, perform I/O only after results are produced. Choose appropriate money types, handle invalid data, and guard against overflow.
