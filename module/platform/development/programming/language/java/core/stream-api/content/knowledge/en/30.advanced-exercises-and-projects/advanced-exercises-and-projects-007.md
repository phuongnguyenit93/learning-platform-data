# Building a Sales Report with Correctness and Ordering Tests

> **Chapter:** Advanced Exercises and Projects  
> **Module:** `JAVA_STREAM_API` — declarative data processing with the Java Stream API using lazy pipelines, `filter`, `map`, `reduce`, `collect`; applying grouping, custom collectors, `Spliterator`, parallel processing, and understanding limits around state, resources, and performance.

A sales report may look simple at first glance: total revenue, order count, units sold, and best-selling items. Yet a correct implementation must also answer: **are cancelled orders counted, can money suffer rounding errors, how are matching SKUs merged, and when revenues tie, what decides ranking order?**

This hands-on project walks from business requirements, data modeling, and pipeline design to **a standalone runnable test suite in Java 17+**. The focus is not writing the shortest possible Stream, but turning rules into explainable, reproducible aggregations and tests.

After completing it, you will be able to:

1. Write pipelines that filter valid orders and calculate revenue using `BigDecimal`, never `double`, for money.
2. Use `Collectors.toMap` with a merge function and `groupingBy` with a downstream collector to build per-SKU and per-category reports.
3. Distinguish **source encounter order**, **Map iteration order**, and **business ranking order**.
4. Test outputs against duplicate SKUs, cancelled orders, empty inputs, decimal amounts, ties, and reversed source order.
5. Verify equivalence between sequential and parallel Streams without relying on lambda execution order.

## 1. Specification: What to Aggregate, and in What Order?

The source is a list of **sales lines**. One receipt can contain multiple lines; one SKU can appear across multiple receipts.

Each line has:

| Field | Example | Meaning |
| --- | --- | --- |
| `receiptId` | `R-01` | Receipt identifier, used to count distinct receipts. |
| `sku` | `PEN` | Product identifier for aggregating revenue and units. |
| `category` | `STATIONERY` | Category used for grouped revenue reporting. |
| `quantity` | `2` | Line quantity; must be positive in this problem. |
| `unitPrice` | `12.50` | Unit price as `BigDecimal`, non-negative. |
| `status` | `PAID` | Receipt status: `PAID` or `CANCELLED`. |

Outputs include:

- **Paid receipt count:** number of distinct `receiptId` values, not line count.
- **Paid line count:** number of elements remaining after `filter`.
- **Units sold:** sum of `quantity` across `PAID` lines.
- **Total revenue:** sum of `quantity * unitPrice` across `PAID` lines.
- **Revenue by category:** `Map<String, BigDecimal>`, iterated in alphabetical key order.
- **SKU ranking:** revenue **descending**; if two SKUs tie on revenue, break ties by SKU code **ascending**. Each entry also holds total units.
- **SKUs by first appearance:** first occurrence only across `PAID` lines, preserving the `List` source's encounter order.

Explicit rules from the start:

1. `CANCELLED` lines contribute to **no** metrics whatsoever.
2. Monetary values use exact decimal arithmetic; never round on intermediate additions. If the system needs taxes, discounts, or refunds, specify and model them separately.
3. One SKU represents one product; this exercise assumes SKUs map consistently to categories in the input data.
4. `receiptId`, `sku`, `category`, `unitPrice`, and `status` must not be `null`; `quantity > 0`, `unitPrice >= 0`.
5. Every list is ordered **by an explicit rule**, never by whatever order a `HashMap` happens to yield.

## 2. Sample Data and Expected Results

| Receipt | SKU | Category | Quantity | Unit Price | Status | Computed Amount |
| --- | --- | --- | ---: | ---: | --- | ---: |
| R-01 | PEN | STATIONERY | 2 | 12.50 | PAID | 25.00 |
| R-01 | BOOK | BOOKS | 1 | 80.00 | PAID | 80.00 |
| R-02 | PEN | STATIONERY | 3 | 12.50 | PAID | 37.50 |
| R-03 | BAG | ACCESSORY | 1 | 62.50 | PAID | 62.50 |
| R-04 | BAG | ACCESSORY | 9 | 62.50 | CANCELLED | **Excluded** |

From the four `PAID` lines we derive:

```text
Paid receipts:   3 (R-01, R-02, R-03)
Counted lines:   4
Units sold:      7 = 2 + 1 + 3 + 1
Total revenue:   205.00 = 25.00 + 80.00 + 37.50 + 62.50

By category:
  ACCESSORY  = 62.50
  BOOKS      = 80.00
  STATIONERY = 62.50

By SKU:
  BOOK: 1 unit, revenue 80.00
  BAG:  1 unit, revenue 62.50
  PEN:  5 units, revenue 62.50
```

**Why does BAG rank ahead of PEN?** Both tie at revenue `62.50`; by the tie-breaker rule, `"BAG"` precedes `"PEN"` in ascending string order. **Why is `firstSeenSkus` `[PEN, BOOK, BAG]`?** That is a separate requirement: it reflects the order in which SKUs first appear in the filtered `List` source, **not** revenue order.

## 3. Pipeline Design: One Source, Multiple Quantities

We split the problem into small, well-typed steps:

```text
List<SaleLine> (source with encounter order)
             |
             v
   filter(status == PAID)
             |
             v
       List<SaleLine> paid
             |
             ├── receiptId -> distinct -> count
             ├── quantity  -> mapToLong -> reduce(addExact)
             ├── amount    -> BigDecimal::add -> total revenue
             ├── category  -> groupingBy -> reducing -> Map by category
             ├── sku       -> toMap(merge) -> per-SKU totals
             |                           └── sorted(revenue DESC, sku ASC)
             └── sku       -> distinct -> first-seen SKUs
```

`filter`, `map`, `mapToLong`, `distinct`, and `sorted` are intermediate operations; `count`, `reduce`, `collect`, and `toList` are terminal operations. A `Stream` cannot be reused after a terminal operation, so each metric must open **a new Stream from `paid`**, or combine them into a custom collector in an advanced version.

In this lesson, we deliberately materialize the `paid` list once so isolating valid data is easy to inspect and test. For massive datasets, retaining an intermediate list carries a memory cost; section 9 examines alternatives.

## 4. Complete Java 17+ Program

Save the code below to `SalesReportProject.java`. It includes **sample data, report builder, output printer, and automated self-tests**. No external libraries beyond the JDK are needed; `main` runs the tests directly.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class SalesReportProject {

    enum Status {
        PAID, CANCELLED
    }

    record SaleLine(
            String receiptId,
            String sku,
            String category,
            int quantity,
            BigDecimal unitPrice,
            Status status
    ) {
        SaleLine {
            Objects.requireNonNull(receiptId, "receiptId");
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(category, "category");
            Objects.requireNonNull(unitPrice, "unitPrice");
            Objects.requireNonNull(status, "status");

            if (receiptId.isBlank() || sku.isBlank() || category.isBlank()) {
                throw new IllegalArgumentException("Codes and categories must not be blank");
            }
            if (quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Invalid quantity/unit price");
            }
        }

        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record ProductTotal(String sku, long units, BigDecimal revenue) {}

    record SalesReport(
            long paidReceipts,
            long paidLines,
            long soldUnits,
            BigDecimal totalRevenue,
            Map<String, BigDecimal> revenueByCategory,
            List<ProductTotal> rankedProducts,
            List<String> firstSeenSkus
    ) {
        SalesReport {
            // Prevent external mutation after returning the result.
            // TreeMap copy guarantees ascending key order.
            revenueByCategory = Collections.unmodifiableMap(
                    new TreeMap<>(revenueByCategory));
            rankedProducts = List.copyOf(rankedProducts);
            firstSeenSkus = List.copyOf(firstSeenSkus);
        }
    }

    static Stream<SaleLine> view(List<SaleLine> rows, boolean parallel) {
        return parallel ? rows.parallelStream() : rows.stream();
    }

    static SalesReport buildReport(List<SaleLine> source, boolean parallel) {
        Objects.requireNonNull(source, "source");

        // A list preserving encounter order from the source List.
        List<SaleLine> paid = view(source, parallel)
                .map(line -> Objects.requireNonNull(line, "sale line"))
                .filter(line -> line.status() == Status.PAID)
                .toList();

        // Two lines on the same receipt count as one receipt.
        long paidReceipts = view(paid, parallel)
                .map(SaleLine::receiptId)
                .distinct()
                .count();

        long soldUnits = view(paid, parallel)
                .mapToLong(SaleLine::quantity)
                .reduce(0L, Math::addExact);

        // Sum money accurately with BigDecimal, never double.
        BigDecimal totalRevenue = view(paid, parallel)
                .map(SaleLine::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        // One sum per category; TreeMap sorts keys.
        Map<String, BigDecimal> revenueByCategory = view(paid, parallel)
                .collect(Collectors.groupingBy(
                        SaleLine::category,
                        TreeMap::new,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                SaleLine::amount,
                                BigDecimal::add)
                ));

        // Merge matching SKUs using an associative merge function.
        Map<String, ProductTotal> bySku = view(paid, parallel)
                .collect(Collectors.toMap(
                        SaleLine::sku,
                        line -> new ProductTotal(
                                line.sku(), line.quantity(), line.amount()),
                        (left, right) -> new ProductTotal(
                                left.sku(),
                                Math.addExact(left.units(), right.units()),
                                left.revenue().add(right.revenue()))
                ));

        // Deterministic ranking: revenue descending, SKU ascending.
        Comparator<ProductTotal> rankingOrder =
                Comparator.<ProductTotal, BigDecimal>comparing(
                        ProductTotal::revenue,
                        Comparator.reverseOrder())
                        .thenComparing(ProductTotal::sku);

        List<ProductTotal> rankedProducts = bySku.values().stream()
                .sorted(rankingOrder)
                .toList();

        // First-appearance order, DIFFERENT from ranking order.
        List<String> firstSeenSkus = view(paid, parallel)
                .map(SaleLine::sku)
                .distinct()
                .toList();

        return new SalesReport(
                paidReceipts,
                paid.size(),
                soldUnits,
                totalRevenue,
                revenueByCategory,
                rankedProducts,
                firstSeenSkus);
    }

    static List<SaleLine> sample() {
        return List.of(
                new SaleLine("R-01", "PEN", "STATIONERY", 2,
                        new BigDecimal("12.50"), Status.PAID),
                new SaleLine("R-01", "BOOK", "BOOKS", 1,
                        new BigDecimal("80.00"), Status.PAID),
                new SaleLine("R-02", "PEN", "STATIONERY", 3,
                        new BigDecimal("12.50"), Status.PAID),
                new SaleLine("R-03", "BAG", "ACCESSORY", 1,
                        new BigDecimal("62.50"), Status.PAID),
                new SaleLine("R-04", "BAG", "ACCESSORY", 9,
                        new BigDecimal("62.50"), Status.CANCELLED)
        );
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void checkMoney(
            String name, BigDecimal actual, String expected) {
        check(actual.compareTo(new BigDecimal(expected)) == 0,
                name + ": expected " + expected + ", actual " + actual);
    }

    static List<String> rankedSkus(SalesReport report) {
        return report.rankedProducts().stream()
                .map(ProductTotal::sku)
                .toList();
    }

    static void selfTest() {
        List<SaleLine> data = sample();
        SalesReport sequential = buildReport(data, false);

        // Correctness: only three PAID receipts and four valid lines.
        check(sequential.paidReceipts() == 3, "Receipt count");
        check(sequential.paidLines() == 4, "Line count");
        check(sequential.soldUnits() == 7, "Unit count");
        checkMoney("Total revenue", sequential.totalRevenue(), "205.00");
        checkMoney("BOOKS",
                sequential.revenueByCategory().get("BOOKS"), "80.00");
        checkMoney("STATIONERY",
                sequential.revenueByCategory().get("STATIONERY"), "62.50");
        checkMoney("ACCESSORY",
                sequential.revenueByCategory().get("ACCESSORY"), "62.50");

        // Report order: ranked with tie-breaker.
        check(rankedSkus(sequential).equals(
                List.of("BOOK", "BAG", "PEN")), "Ranking");
        check(sequential.firstSeenSkus().equals(
                List.of("PEN", "BOOK", "BAG")), "Encounter order");
        check(new ArrayList<>(sequential.revenueByCategory().keySet())
                .equals(List.of("ACCESSORY", "BOOKS", "STATIONERY")),
                "Category key order");
        check(sequential.rankedProducts().get(2).units() == 5,
                "Aggregated PEN units");

        // Same source: parallel processing must not alter the result.
        SalesReport parallel = buildReport(data, true);
        check(sequential.equals(parallel), "Parallel != sequential");

        // Reversed encounter order: totals stay invariant,
        // while first-seen SKU order may change.
        List<SaleLine> reversed = new ArrayList<>(data);
        Collections.reverse(reversed);
        SalesReport changedOrder = buildReport(reversed, true);
        checkMoney("Total after reversing source",
                changedOrder.totalRevenue(), "205.00");
        check(changedOrder.rankedProducts().equals(
                sequential.rankedProducts()), "Ranking changed on reversed source");
        check(changedOrder.revenueByCategory().equals(
                sequential.revenueByCategory()), "Group changed on reversed source");
        check(changedOrder.firstSeenSkus().equals(
                List.of("BAG", "PEN", "BOOK")), "SKU order after reversing");

        // Empty source and cancelled-only source.
        SalesReport empty = buildReport(List.of(), false);
        check(empty.paidReceipts() == 0, "Empty receipts");
        check(empty.paidLines() == 0, "Empty lines");
        check(empty.soldUnits() == 0, "Empty units");
        checkMoney("Empty revenue", empty.totalRevenue(), "0");
        check(empty.revenueByCategory().isEmpty(), "Empty categories");
        check(empty.rankedProducts().isEmpty(), "Empty ranking");
        check(empty.firstSeenSkus().isEmpty(), "Empty appearance");
        check(buildReport(List.of(data.get(4)), true).equals(empty),
                "Cancelled-only report");

        // Decimal money: do not sum using double.
        List<SaleLine> cents = List.of(
                new SaleLine("R-A", "A", "SMALL", 1,
                        new BigDecimal("0.10"), Status.PAID),
                new SaleLine("R-B", "A", "SMALL", 1,
                        new BigDecimal("0.20"), Status.PAID)
        );
        checkMoney("Decimal amount",
                buildReport(cents, true).totalRevenue(), "0.30");

        // Returned result lists must not allow mutation.
        boolean rejected = false;
        try {
            sequential.firstSeenSkus().add("X");
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        check(rejected, "Result list must be unmodifiable");
    }

    public static void main(String[] args) {
        SalesReport report = buildReport(sample(), false);
        System.out.println("PAID receipts: " + report.paidReceipts());
        System.out.println("PAID lines: " + report.paidLines());
        System.out.println("Units sold: " + report.soldUnits());
        System.out.println("Total revenue: " + report.totalRevenue());
        System.out.println("By category: " + report.revenueByCategory());
        System.out.println("SKU ranking: " + rankedSkus(report));
        System.out.println("First-seen SKUs: " + report.firstSeenSkus());

        // Always run checks; do not depend on Java's -ea flag.
        selfTest();
        System.out.println("TEST PASS");
    }
}
```

Run with Java 17+ in the folder where you saved the file if you want to practice:

```text
javac SalesReportProject.java
java SalesReportProject
```

Expected output:

```text
PAID receipts: 3
PAID lines: 4
Units sold: 7
Total revenue: 205.00
By category: {ACCESSORY=62.50, BOOKS=80.00, STATIONERY=62.50}
SKU ranking: [BOOK, BAG, PEN]
First-seen SKUs: [PEN, BOOK, BAG]
TEST PASS
```

The output above is derived from the sample data; more important than matching console strings is **verifying values and ordering field by field** inside `selfTest()`.

## 5. Why Use `BigDecimal` and `Math.addExact`?

### Money Should Not Be Summed with `double`

Decimal values like `0.1` or `0.2` cannot always be represented exactly in binary floating point. When handling money, write:

```java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
BigDecimal total = a.add(b);

System.out.println(total); // 0.30
```

Never write `new BigDecimal(0.1)` if you expect the exact decimal `0.1`; constructing from a `String` or an integer minor unit is far more reliable.

In the example, `SaleLine.amount()` multiplies a positive integer by a `BigDecimal`. When reducing many lines:

```java
BigDecimal totalRevenue = paid.stream()
        .map(SaleLine::amount)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`BigDecimal.ZERO` is the additive identity. `BigDecimal::add` yields exact arithmetic results, and addition is associative **by numeric value**, making it safe for combining parallel branches. However, do not assume every rounding scheme is associative: rounding after **each** addition can produce different totals depending on how the source is split.

### Why Does `checkMoney` Use `compareTo`?

`BigDecimal.equals` also checks **scale**:

```java
new BigDecimal("2.0").equals(new BigDecimal("2.00"));    // false
new BigDecimal("2.0").compareTo(new BigDecimal("2.00")); // 0
```

For reports comparing **numerical monetary values**, `compareTo(...) == 0` is usually appropriate. If business rules demand an exact two-decimal scale, check scale **additionally** and apply formatting/rounding rules at the defined boundary.

### Quantities Can Overflow

`IntStream.sum()` returns `int`, which can overflow on large totals. This lesson uses:

```java
long units = paid.stream()
        .mapToLong(SaleLine::quantity)
        .reduce(0L, Math::addExact);
```

`Math.addExact` throws `ArithmeticException` if the sum exceeds `long` bounds, making overflow explicit instead of wrapping silently. This addition remains valid in parallel reduction when input bounds and business rules permit. For totals exceeding `long`, design with a larger numeric type rather than ignoring overflow.

## 6. Two Kinds of Ordering Commonly Confused

### First-Appearance Order (*Encounter Order*)

With a `List` source, a Stream has a default encounter order. Writing:

```java
List<String> firstSeen = paid.stream()
        .map(SaleLine::sku)
        .distinct()
        .toList();
```

returns distinct SKUs in **first-appearance order** within the ordered source. On the sample data, the result is `[PEN, BOOK, BAG]`. On an ordered Stream, `distinct` retains the first occurrence among equal elements; on an unordered source, never expect a "first" rule.

If you reorder input lines, this list can change even while **total revenue stays identical**. Therefore, never test it by sorting arbitrarily and expecting it to remain unchanged.

### Ranking Order (*Business Ranking*)

```java
Comparator<ProductTotal> rankingOrder =
        Comparator.<ProductTotal, BigDecimal>comparing(
                ProductTotal::revenue,
                Comparator.reverseOrder())
                .thenComparing(ProductTotal::sku);
```

This Comparator applies two criteria:

1. Revenue **descending** via `Comparator.reverseOrder()`.
2. When two revenues are numerically equal, SKU **ascending** via `thenComparing`.

`BigDecimal.compareTo` compares revenues inside the comparator, so `62.5` and `62.50` compare equal. Never rely on iteration order of `Map.values()` without calling `sorted`.

**Do not confuse** this with appending `comparator.reversed()` at the end: reversing the entire comparator reverses the secondary criterion too, making tied SKUs sort descending. The pattern above reverses only revenue, keeping SKU ascending.

### Map Key Order

Using `TreeMap::new` for category stats enforces ascending key order; copying via `new TreeMap<>(...)` wrapped in `Collections.unmodifiableMap(...)` inside the record preserves that order on publication.

The default `HashMap` of some collectors **does not guarantee** iteration order. Two Maps can satisfy `Map.equals` despite different iteration orders; if order is required, assert `keySet()` ordering against the published rule.

## 7. What Should Be Tested to Make Reports Trustworthy?

Do not merely check that the program prints a few lines. A report can have **right totals but wrong order**, or **right order while accidentally counting cancelled orders**. Every business rule should become an independent test.

| Test Group | Scenario | Expected Verification |
| --- | --- | --- |
| Filtering | A `CANCELLED` line with large quantity | Contributes nothing to receipts, units, or revenue. |
| Counting | Two lines sharing the same `receiptId` | One receipt, yet two valid sale lines. |
| SKU merge | `PEN` appears twice | 5 units, revenue 62.50. |
| Category grouping | `PEN` and `BOOK` in different categories | Accurate total per category. |
| Summation | All `PAID` lines | 205.00, no overflow or `double` drift. |
| Ties | `BAG` and `PEN` with equal revenue | `BAG` precedes `PEN` by SKU. |
| Input order | List presents PEN, BOOK, BAG | `firstSeenSkus` preserves that order. |
| Source permutation | Reversing the line list | Totals and ranking stay unchanged; `firstSeenSkus` reflects new encounter order. |
| Parallel | `parallel = true` on same source | Entire report equals sequential report. |
| Empty | Empty list or `CANCELLED`-only | Zero counts, zero revenue, empty Maps/Lists. |
| Decimals | 0.10 and 0.20 | Sum equals 0.30 numerically. |
| Output immutability | Attempting to add a SKU to published list | Rejected with `UnsupportedOperationException`. |

In `selfTest()`, `check(boolean, message)` throws `AssertionError` on failure. Unlike Java's `assert` statement, this check **does not depend on the `-ea` flag** at runtime. It suits standalone self-study in one file; in a production project with an automated suite, put corresponding cases into dedicated tests with JUnit or the project's test framework.

### Permutation Testing Is a Strong Verification Technique

Because addition and per-SKU merging are order-independent, we expect:

```text
report(source).totalRevenue == report(reverse(source)).totalRevenue
report(source).rankedProducts == report(reverse(source)).rankedProducts
```

However:

```text
report(source).firstSeenSkus
    may DIFFER from report(reverse(source)).firstSeenSkus
```

This acts as a **permutation invariance test** for order-independent quantities, while proving that appearance order is **genuinely** handled according to source semantics. If a test forces `firstSeenSkus` to stay identical after reversing the source, the test itself is wrong.

## 8. Sequential, Parallel, and Correctness Contracts

`parallelStream()` can split the source and combine results across partitions. This exercise uses associative combining operations:

- Units: `Math.addExact` while sums stay within `long` range.
- Money: `BigDecimal::add`, with no intermediate rounding.
- Per-SKU merge: summing units and revenue, with a fixed SKU per key.
- Ranking: sorting with an explicit comparator after merging.
- First-seen SKUs: preserving `List` encounter order via `distinct`.

Never use an external `ArrayList` and append via `parallelStream().forEach(shared::add)`: it creates data races and loses ordering guarantees. Stream collectors manage private accumulators and merges properly.

```java
// Avoid:
// List<SaleLine> shared = new ArrayList<>();
// source.parallelStream().forEach(shared::add);

// Prefer:
List<SaleLine> paid = source.parallelStream()
        .filter(s -> s.status() == Status.PAID)
        .toList();
```

On an ordered `List` source, `Stream.toList()` preserves element order in the result even though elements may be processed by different threads. **Lambda invocation order** is not necessarily the order in the resulting List.

### Should You Use `parallel = true` in Production?

Do not decide based solely on identical test results. Parallel execution adds overhead for splitting, scheduling, and merging intermediate Maps. On small inputs, `parallelStream()` can be **slower** than sequential execution. If work is CPU-bound, stateless, and data is large enough, benchmark in a realistic environment; if each line makes blocking JDBC/HTTP calls, design dedicated I/O orchestration and resource bounds instead of defaulting to the common pool.

Functional tests answer **"is it right?"**; benchmarks and system monitoring answer **"is it faster?"**. Never draw conclusions from a single execution time.

## 9. Design Limitations and Extension Directions

### 9.1. Materializing the `paid` List

The current solution stores an intermediate list and traverses it multiple times to compute metrics. That is convenient for teaching and moderate datasets, yet uses memory proportional to `PAID` line count. For massive datasets, use a **custom collector** accumulating multiple metrics in one pass, combine `groupingBy`/downstream collectors as needed, or aggregate in the database.

Note that a custom collector does not automatically guarantee tiny memory: if it still retains a Map per SKU or category, memory still scales with **distinct key count**.

### 9.2. Dirty Data, Category Mismatches per SKU, and Exceptions

The `SaleLine` record validates **one line**, not dataset-wide consistency. If the same SKU carries two different `category` values, per-SKU aggregation still works while per-category reporting reflects **inconsistent** source data. In real systems, validate `SKU -> category` consistency at ingestion or prior to reporting.

Other rules to settle before extending:

- Are refunds/returns represented as negative lines or a separate status?
- Is `PAID` count tracked at receipt level or line level? This lesson assumes per-line status reflects receipt status.
- Are taxes, discounts, and shipping fees allocated per SKU or shown only in receipt totals?
- Are time zones, reporting periods, exchange rates, and rounding rules applied daily or per transaction?

These questions have no single technical answer; they must come from business requirements before choosing `filter`, `map`, or collectors.

### 9.3. Stability and Ordering

When a report asks for "first sold timestamp", you cannot rely solely on **list index** if rows can arrive out of chronological order. Add a `soldAt` field or event sequence number and sort via a comparator with a **tie-breaker** for identical timestamps.

Likewise, when ranking by multiple criteria, define a total order sufficient so results never depend on Map iteration order or parallel merge order.

### 9.4. Stream Sources and Resource Management

If the source is a Stream backed directly by a file or database cursor, `collect` consumes it yet **does not replace closing the resource**. For closeable sources, use `try-with-resources` per the corresponding API. A Stream cannot be reused after a terminal operation; never reuse the same Stream object to compute multiple reports.

## 10. Project Extension Exercises

**Exercise 1 — Top N.** Write a method returning the top three SKUs by revenue. On ties, keep ascending SKU order.

```java
List<ProductTotal> topThree = report.rankedProducts().stream()
        .limit(3)
        .toList();
```

`report` is the `SalesReport` returned by `buildReport`. Since the list is already sorted by the business comparator, `limit(3)` needs no re-sorting.

**Exercise 2 — Revenue Share Percentage.** Compute the revenue share of `BOOKS` out of total revenue using `BigDecimal.divide(scale, roundingMode)` and rounding at the presentation step. If total revenue is 0, define an explicit policy instead of dividing by 0.

**Exercise 3 — Detecting Inconsistent Data.** Add a validation check that throws an error if the same SKU appears under multiple categories. Never silently merge two distinct categories just because SKU strings match.

**Exercise 4 — Chronological Ordering.** Add `soldAt` and `lineId` fields. Build the SKU list ordered by first sale event, sorting by ascending timestamp and `lineId` as tie-breaker. Compare against using raw encounter order directly.

**Exercise 5 — Independent Cross-Check.** Build a small dataset and compute total revenue with a plain loop to cross-check the Stream result. On large randomized datasets, test permutation invariance and inject non-contributing data (such as cancelled orders) to catch regressions.

**Exercise 6 — Streaming Aggregation.** Discuss how to handle millions of sales lines. If moving to a custom collector, specify `supplier`, `accumulator`, `combiner`, and `finisher`, ensuring merges stay accurate under `parallelStream()`.

## Key Takeaways

- An accurate sales report starts with the **business contract**: which statuses count, how "receipts" differ from "lines", and how money and quantities sum.
- `filter` selects valid records; `map`/`reduce` compute totals; `toMap` with a merge function aggregates SKUs; `groupingBy` with a downstream collector aggregates category revenue.
- Use **`BigDecimal`** for money, `Math.addExact` to catch integer overflow, and avoid rounding mid-aggregation.
- **Encounter order**, **Map key order**, and **business ranking** are three distinct concepts: preserve first appearance with `distinct`, use `TreeMap` for keys, and use a tie-breaking comparator for ranking.
- Tests must cover cancelled orders, duplicate keys, empty sources, ties, reversed order, decimals, and sequential/parallel equivalence; **functional correctness alone does not prove good performance**.
