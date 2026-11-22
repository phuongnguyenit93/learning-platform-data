# Aggregating Orders by Customer and Time Period

> **Chapter:** Practical Data Processing Patterns  
> **Module:** `JAVA_STREAM_API` — declarative data processing with lazy pipelines, `filter`, `map`, `reduce`, and `collect`; practicing grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while understanding state, resource, and performance limits.

Sales reports rarely ask only **"what is total revenue?"**; they ask **"which customers purchased this quarter, how many orders did each have per month, and what was each customer's total spend?"**. To answer accurately, a program must handle status filtering, time-window boundaries, time-zone conversion, multi-dimensional grouping, and exact monetary summation simultaneously.

This hands-on lesson guides you through building a self-contained report on **Java 17+**. The source is a list of orders containing `customerId`, timestamp as an `Instant`, status, and payment amount. The output includes breakdowns **by customer and month**, **customer totals**, and a **period grand total**. The program includes tests for date boundaries, cancelled orders, empty sources, reversed input order, and parallel execution.

## 1. Define the Business Contract Before Writing Streams

Suppose the report has these conditions:

1. Count only orders with status `PAID`; `CANCELLED` orders contribute neither revenue nor order count.
2. Each `Order` object represents **one distinct order**; `id` values are assumed unique. If the source contains multiple events for the same order, deduplicate or compute final state using separate rules.
3. `recordedAt` is an `Instant` (an absolute point in time). Reporting day and month are determined **in the business time zone**.
4. The reporting interval is **half-open**: `[startInclusive, endExclusive)`. Include the exact start instant and **exclude** the start instant of the next period.
5. Sum revenue using `BigDecimal`; do not use `double` to represent money.
6. Sort output by **customer ID ascending**, then **month ascending**, so it never depends on `HashMap` iteration order.

For example, suppose you need a report from **2026-01-01 through 2026-03-31** in `Asia/Ho_Chi_Minh`. Instead of expressing the end as `03/31 23:59:59` (which can miss fractional milliseconds/nanoseconds), use:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant start = LocalDate.of(2026, 1, 1)
        .atStartOfDay(zone)
        .toInstant();
Instant end = LocalDate.of(2026, 4, 1)
        .atStartOfDay(zone)
        .toInstant();

// Inclusive: start <= recordedAt < end.
```

The absolute UTC times of those two boundaries are `2025-12-31T17:00:00Z` and `2026-03-31T17:00:00Z`. Using `LocalDate.atStartOfDay(zone)` handles time zones whose offset changes by date; never assume every day in every time zone is always 24 hours long.

## 2. Data Model and Grouping Key Design

The data model uses these types:

```java
enum Status { PAID, CANCELLED }

record Order(
        String id,
        String customerId,
        Instant recordedAt,
        BigDecimal amount,
        Status status
) {}

record CustomerMonth(String customerId, YearMonth month) {}
record Stats(long orderCount, BigDecimal revenue) {}
```

These types are declared in full, with input validation, in the program in section 5.

**Why use `CustomerMonth` instead of a concatenated string like `"C-A_2026-01"`?**

- A record key has explicit structure: `customerId` and `YearMonth` are distinct fields.
- `equals`/`hashCode` are generated from each field's value, ideal for `groupingBy`.
- No need to invent a delimiter or handle IDs containing `_`.
- A clear comparator by customer then month is straightforward to write.

When grouping:

```java
CustomerMonth key = new CustomerMonth(
        order.customerId(),
        YearMonth.from(order.recordedAt().atZone(zone))
);
```

**The month must be determined after converting to `zone`.** An order recorded at `2026-01-31T17:00:00Z` is **00:00 on 2026-02-01** in Vietnam, so it belongs to **February** in the local report, not January.

## 3. Staged Processing Pipeline

We split the problem into three main stages:

```text
List<Order>
    |
    v
filter(status == PAID)
    |
filter(start <= recordedAt < end)
    |
    v
List<Order> eligible
    |
    +---- groupingBy(CustomerMonth, reducing(Stats)) ----> Map<CustomerMonth, Stats>
    |                                                       |
    |                                                       v
    |                                               Totals by customer+month
    |                                                       |
    |                                                       v
    |                                        toMap(customerId, Stats::plus)
    |                                                       |
    |                                                       v
    |                                               Totals by customer
    |                                                       |
    |                                                       v
    +----------------------------------------------- reduce(Stats::plus)
                                                            |
                                                            v
                                                    Period grand total
```

Key design decisions:

- `filter` keeps only `PAID` orders within the exact time interval.
- `groupingBy` keys by **customer + local month**.
- The downstream `reducing` produces a `Stats` holding both **order count** and **revenue**, avoiding two separate grouping/summing passes.
- `Stats::plus` combines intermediate statistics; it needs an identity element and associativity to work correctly when a Stream splits across parallel branches.
- `TreeMap` is chosen to iterate results in deterministic order; this ordering is a report requirement, not an accidental side effect of a `HashMap`.

## 4. Sample Data and Expected Results

Timestamps in the table below are shown in **Vietnam local time (UTC+07:00)** to make boundaries clear:

| Order | Customer | Local Date & Time | Status | Amount | Included? |
| --- | --- | --- | --- | ---: | --- |
| O-01 | C-A | 01/01/2026 00:00:00 | PAID | 100.10 | Yes, start boundary |
| O-02 | C-A | 15/01/2026 17:00:00 | PAID | 200.20 | Yes |
| O-03 | C-B | 31/01/2026 23:59:59 | PAID | 40.00 | Yes, month 1 |
| O-04 | C-A | 01/02/2026 00:00:00 | PAID | 70.00 | Yes, month 2 |
| O-05 | C-B | 10/02/2026 09:00:00 | PAID | 10.50 | Yes |
| O-06 | C-A | 25/02/2026 19:00:00 | PAID | 90.20 | Yes |
| O-07 | C-B | 31/03/2026 23:59:59 | PAID | 30.00 | Yes |
| O-08 | C-A | 01/04/2026 00:00:00 | PAID | 300.00 | No, exact end boundary |
| O-09 | C-B | 05/02/2026 12:00:00 | CANCELLED | 999.00 | No, cancelled order |
| O-10 | C-C | 12/02/2026 10:00:00 | PAID | 0.30 | Yes |
| O-11 | C-B | 31/12/2025 23:59:59 | PAID | 600.00 | No, before start boundary |

From this, the expected results are:

| Customer | Month | Orders | Revenue |
| --- | --- | ---: | ---: |
| C-A | 2026-01 | 2 | 300.30 |
| C-A | 2026-02 | 2 | 160.20 |
| C-B | 2026-01 | 1 | 40.00 |
| C-B | 2026-02 | 1 | 10.50 |
| C-B | 2026-03 | 1 | 30.00 |
| C-C | 2026-02 | 1 | 0.30 |
| **Grand Total** | **01–03/2026** | **8** | **541.30** |

Per-customer totals are: **C-A = 460.50 (4 orders)**; **C-B = 80.50 (3 orders)**; **C-C = 0.30 (1 order)**. These numbers serve to write checks independent of the aggregation implementation.

## 5. Self-Contained Java 17+ Program with Tests

Save the following code to `CustomerPeriodReportDemo.java`. The program uses only standard JDK 17 APIs; `main` both prints the report and runs automated self-checks.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CustomerPeriodReportDemo {

    enum Status { PAID, CANCELLED }

    record Order(
            String id,
            String customerId,
            Instant recordedAt,
            BigDecimal amount,
            Status status
    ) {
        Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(recordedAt, "recordedAt");
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(status, "status");
            if (id.isBlank() || customerId.isBlank()) {
                throw new IllegalArgumentException("ID must not be blank");
            }
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("Negative amounts are not yet supported");
            }
        }
    }

    record CustomerMonth(String customerId, YearMonth month) {}

    record Stats(long orderCount, BigDecimal revenue) {
        static Stats zero() {
            return new Stats(0L, BigDecimal.ZERO);
        }

        Stats plus(Stats other) {
            return new Stats(
                    Math.addExact(orderCount, other.orderCount),
                    revenue.add(other.revenue));
        }
    }

    private static final Comparator<CustomerMonth> CUSTOMER_MONTH_ORDER =
            Comparator.comparing(CustomerMonth::customerId)
                    .thenComparing(CustomerMonth::month);

    record Report(
            Map<CustomerMonth, Stats> monthly,
            Map<String, Stats> byCustomer,
            Stats grandTotal
    ) {
        Report {
            // Unmodifiable maps with deterministic iteration order.
            TreeMap<CustomerMonth, Stats> months =
                    new TreeMap<>(CUSTOMER_MONTH_ORDER);
            months.putAll(monthly);
            monthly = Collections.unmodifiableMap(months);
            byCustomer = Collections.unmodifiableMap(
                    new TreeMap<>(byCustomer));
            Objects.requireNonNull(grandTotal, "grandTotal");
        }
    }

    static Stream<Order> streamOf(List<Order> source, boolean parallel) {
        return parallel ? source.parallelStream() : source.stream();
    }

    static Report build(
            List<Order> source,
            LocalDate fromInclusive,
            LocalDate toExclusive,
            ZoneId zone,
            boolean parallel
    ) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(fromInclusive, "fromInclusive");
        Objects.requireNonNull(toExclusive, "toExclusive");
        Objects.requireNonNull(zone, "zone");
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException(
                    "Date range must satisfy from < to");
        }

        Instant start = fromInclusive.atStartOfDay(zone).toInstant();
        Instant end = toExclusive.atStartOfDay(zone).toInstant();

        // Accept only PAID orders within [start, end).
        List<Order> eligible = streamOf(source, parallel)
                .map(o -> Objects.requireNonNull(o, "order"))
                .filter(o -> o.status() == Status.PAID)
                .filter(o -> !o.recordedAt().isBefore(start))
                .filter(o -> o.recordedAt().isBefore(end))
                .toList();

        // Composite key (customer, month) is computed in the business zone.
        Map<CustomerMonth, Stats> monthly = streamOf(eligible, parallel)
                .collect(Collectors.groupingBy(
                        o -> new CustomerMonth(
                                o.customerId(),
                                YearMonth.from(o.recordedAt().atZone(zone))),
                        () -> new TreeMap<>(CUSTOMER_MONTH_ORDER),
                        Collectors.reducing(
                                Stats.zero(),
                                o -> new Stats(1L, o.amount()),
                                Stats::plus)
                ));

        // Customer totals sum monthly groups, avoiding re-scanning the source.
        Map<String, Stats> byCustomer = monthly.entrySet().stream()
                .collect(Collectors.toMap(
                        entry -> entry.getKey().customerId(),
                        Map.Entry::getValue,
                        Stats::plus,
                        TreeMap::new
                ));

        Stats grandTotal = byCustomer.values().stream()
                .reduce(Stats.zero(), Stats::plus);

        return new Report(monthly, byCustomer, grandTotal);
    }

    static List<Order> sample() {
        return List.of(
                new Order("O-01", "C-A",
                        Instant.parse("2025-12-31T17:00:00Z"),
                        new BigDecimal("100.10"), Status.PAID),
                new Order("O-02", "C-A",
                        Instant.parse("2026-01-15T10:00:00Z"),
                        new BigDecimal("200.20"), Status.PAID),
                new Order("O-03", "C-B",
                        Instant.parse("2026-01-31T16:59:59Z"),
                        new BigDecimal("40.00"), Status.PAID),
                new Order("O-04", "C-A",
                        Instant.parse("2026-01-31T17:00:00Z"),
                        new BigDecimal("70.00"), Status.PAID),
                new Order("O-05", "C-B",
                        Instant.parse("2026-02-10T02:00:00Z"),
                        new BigDecimal("10.50"), Status.PAID),
                new Order("O-06", "C-A",
                        Instant.parse("2026-02-25T12:00:00Z"),
                        new BigDecimal("90.20"), Status.PAID),
                new Order("O-07", "C-B",
                        Instant.parse("2026-03-31T16:59:59Z"),
                        new BigDecimal("30.00"), Status.PAID),
                new Order("O-08", "C-A",
                        Instant.parse("2026-03-31T17:00:00Z"),
                        new BigDecimal("300.00"), Status.PAID),
                new Order("O-09", "C-B",
                        Instant.parse("2026-02-05T05:00:00Z"),
                        new BigDecimal("999.00"), Status.CANCELLED),
                new Order("O-10", "C-C",
                        Instant.parse("2026-02-12T03:00:00Z"),
                        new BigDecimal("0.30"), Status.PAID),
                new Order("O-11", "C-B",
                        Instant.parse("2025-12-31T16:59:59Z"),
                        new BigDecimal("600.00"), Status.PAID)
        );
    }

    static void check(boolean ok, String reason) {
        if (!ok) {
            throw new AssertionError(reason);
        }
    }

    static void checkMoney(String name, BigDecimal actual, String expected) {
        check(actual != null
                        && actual.compareTo(new BigDecimal(expected)) == 0,
                "Wrong amount for " + name + ": " + actual);
    }

    static Stats at(Report report, String id, int year, int month) {
        return report.monthly().get(
                new CustomerMonth(id, YearMonth.of(year, month)));
    }

    static void selfTest() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate from = LocalDate.of(2026, 1, 1);
        LocalDate end = LocalDate.of(2026, 4, 1);
        List<Order> data = sample();

        Report sequential = build(data, from, end, zone, false);
        check(sequential.monthly().size() == 6, "Customer/month group count");
        check(sequential.byCustomer().size() == 3, "Customer count");
        check(sequential.grandTotal().orderCount() == 8, "Period order count");
        checkMoney("Grand total", sequential.grandTotal().revenue(), "541.30");

        check(at(sequential, "C-A", 2026, 1).orderCount() == 2,
                "C-A month 1");
        checkMoney("C-A month 1",
                at(sequential, "C-A", 2026, 1).revenue(), "300.30");
        checkMoney("C-A month 2",
                at(sequential, "C-A", 2026, 2).revenue(), "160.20");
        checkMoney("C-B month 1",
                at(sequential, "C-B", 2026, 1).revenue(), "40.00");
        checkMoney("C-B month 2",
                at(sequential, "C-B", 2026, 2).revenue(), "10.50");
        checkMoney("C-B month 3",
                at(sequential, "C-B", 2026, 3).revenue(), "30.00");
        checkMoney("C-C month 2",
                at(sequential, "C-C", 2026, 2).revenue(), "0.30");

        check(sequential.byCustomer().get("C-A").orderCount() == 4,
                "C-A should have 4 orders");
        checkMoney("C-A", sequential.byCustomer().get("C-A").revenue(),
                "460.50");
        checkMoney("C-B", sequential.byCustomer().get("C-B").revenue(),
                "80.50");

        // Comparator defines order, not relying on HashMap.
        List<CustomerMonth> expectedKeys = List.of(
                new CustomerMonth("C-A", YearMonth.of(2026, 1)),
                new CustomerMonth("C-A", YearMonth.of(2026, 2)),
                new CustomerMonth("C-B", YearMonth.of(2026, 1)),
                new CustomerMonth("C-B", YearMonth.of(2026, 2)),
                new CustomerMonth("C-B", YearMonth.of(2026, 3)),
                new CustomerMonth("C-C", YearMonth.of(2026, 2))
        );
        check(new ArrayList<>(sequential.monthly().keySet())
                .equals(expectedKeys), "Group ordering");

        // Same data: parallel and sequential must yield equivalent reports.
        Report parallel = build(data, from, end, zone, true);
        check(sequential.equals(parallel), "Parallel result mismatch");

        // Reversed input order: sums and groups must not change.
        List<Order> reversed = new ArrayList<>(data);
        Collections.reverse(reversed);
        check(sequential.equals(build(reversed, from, end, zone, true)),
                "Result changed when input was reversed");

        // Empty source and source with only excluded orders.
        Report empty = build(List.of(), from, end, zone, false);
        check(empty.monthly().isEmpty(), "Empty groups");
        check(empty.byCustomer().isEmpty(), "Empty customers");
        check(empty.grandTotal().orderCount() == 0, "Empty order count");
        checkMoney("Empty revenue", empty.grandTotal().revenue(), "0");
        check(build(List.of(data.get(7), data.get(8), data.get(10)),
                from, end, zone, false).equals(empty),
                "Out-of-range or cancelled orders were still counted");

        // Order O-04 is on 02/01 in Vietnam time, not in January's group.
        checkMoney("Month 2 boundary",
                at(sequential, "C-A", 2026, 2).revenue(), "160.20");

        // External edits must not mutate the report results.
        boolean rejected = false;
        try {
            sequential.byCustomer().put("C-Z", Stats.zero());
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        check(rejected, "Report Map must be unmodifiable");
    }

    public static void main(String[] args) {
        Report report = build(
                sample(),
                LocalDate.of(2026, 1, 1),
                LocalDate.of(2026, 4, 1),
                ZoneId.of("Asia/Ho_Chi_Minh"),
                false);

        report.monthly().forEach((key, stats) ->
                System.out.println(key.customerId() + " | "
                        + key.month() + ": " + stats.orderCount()
                        + " orders / " + stats.revenue()));
        report.byCustomer().forEach((id, stats) ->
                System.out.println("Customer " + id + ": "
                        + stats.orderCount() + " orders / " + stats.revenue()));
        System.out.println("Grand total: "
                + report.grandTotal().orderCount() + " orders / "
                + report.grandTotal().revenue());

        // Checks do not depend on the java -ea flag.
        selfTest();
        System.out.println("TEST PASS");
    }
}
```

Try running it on JDK 17+:

```text
javac CustomerPeriodReportDemo.java
java CustomerPeriodReportDemo
```

Expected output (abbreviated):

```text
C-A | 2026-01: 2 orders / 300.30
C-A | 2026-02: 2 orders / 160.20
C-B | 2026-01: 1 orders / 40.00
C-B | 2026-02: 1 orders / 10.50
C-B | 2026-03: 1 orders / 30.00
C-C | 2026-02: 1 orders / 0.30
Customer C-A: 4 orders / 460.50
Customer C-B: 3 orders / 80.50
Customer C-C: 1 orders / 0.30
Grand total: 8 orders / 541.30
TEST PASS
```

The results above are computed from the sample data; test code is provided for learners to run themselves. Documentation **does not imply** the program was compiled or automatically verified as part of authoring this article.

## 6. Why Pair `groupingBy` with `reducing`?

The core of the solution is:

```java
Map<CustomerMonth, Stats> monthly = eligible.stream()
        .collect(Collectors.groupingBy(
                o -> new CustomerMonth(
                        o.customerId(),
                        YearMonth.from(o.recordedAt().atZone(zone))),
                () -> new TreeMap<>(CUSTOMER_MONTH_ORDER),
                Collectors.reducing(
                        Stats.zero(),
                        o -> new Stats(1L, o.amount()),
                        Stats::plus)
        ));
```

This snippet uses the types, variables, and comparator defined in the program in section 5.

Meaningful components:

| Component | Role |
| --- | --- |
| `o -> new CustomerMonth(...)` | Classifies across **two dimensions**: customer and month. |
| `() -> new TreeMap<>(CUSTOMER_MONTH_ORDER)` | Selects a Map whose keys are ordered by the business comparator. |
| `Stats.zero()` | Identity state: `0` orders, `BigDecimal.ZERO` revenue. |
| `o -> new Stats(1L, o.amount())` | Maps a single order to single-order stats. |
| `Stats::plus` | Combines two stats by summing order counts and revenues. |

`reducing(identity, mapper, op)` is a **downstream collector**: each group receives the elements belonging to that group and reduces them into a single `Stats`.

### Why Not Use `summingDouble` for Money?

`Collectors.summingDouble(Order::amount)` does not fit here because `amount` is a `BigDecimal`, and converting to `double` can introduce precision errors. For money, keep an exact type or a well-defined integer minor-unit model.

### Why Does `Stats::plus` Work Well with Parallelism?

Combining operates on **immutable records**:

```java
Stats left = new Stats(2, new BigDecimal("100.10"));
Stats right = new Stats(1, new BigDecimal("20.20"));
Stats total = left.plus(right);
// 3 orders, 120.30
```

The identity `Stats.zero()` leaves values unchanged when added. Addition of counts and money is associative within the valid data domain, so even if `groupingBy` builds multiple intermediate Maps during parallel execution, the arithmetic result stays equivalent. `Math.addExact` fails if total orders exceed `long`; the example does not round money at intermediate steps.

## 7. Time Boundaries: Common Reporting Bugs

### Half-Open Interval `[start, end)`

Safe condition:

```java
boolean within = !order.recordedAt().isBefore(start)
        && order.recordedAt().isBefore(end);
```

For **01/01–04/01**, an order at exact `01/01 00:00` is included, while an order at exact `04/01 00:00` is excluded. When the next period starts on the following date, adjacent periods tile cleanly **without overlap or boundary gaps**.

Avoid writing `<= LocalDate.atTime(23,59,59)` for the end boundary when data has millisecond/nanosecond precision. Also avoid calling `Instant.now()` repeatedly inside predicates if reports must be repeatable and testable.

### Difference Between `Instant` and `LocalDate`

- `Instant` represents an absolute point in time, suited for storing and comparing events.
- `LocalDate` represents a **calendar date** without a time zone; it requires a `ZoneId` when converting to `Instant` boundaries.
- `YearMonth` represents a reporting month; choose the month only after converting `Instant` to the business time zone.

If you group by `YearMonth.from(order.recordedAt().atZone(ZoneOffset.UTC))` when the report uses `Asia/Ho_Chi_Minh`, orders near boundaries can land in the **wrong month**.

### Time Zones and Daylight Saving Time

In zones with DST, the span from one local start-of-day to the next can be shorter or longer than 24 hours. Converting **both boundary dates in the same `ZoneId`** and comparing `Instant` values avoids the bug of adding a fixed `Duration.ofDays(1)` for every day.

If a system reports monthly, use `YearMonth.atDay(1)` and `plusMonths(1)` to construct month boundaries in the chosen time zone instead of assuming fixed lengths like 30 days.

## 8. Testing Correctness, Ordering, and Stability

A report can have the right grand total yet **wrong monthly grouping**. Therefore, test both summary totals and boundary cases.

| Test Group | Data | Assertion Needed |
| --- | --- | --- |
| Start boundary | O-01 at exact `01/01 00:00` local | Included in January stats. |
| End boundary | O-08 at exact `04/01 00:00` local | Excluded from Q1 report. |
| Before period | O-11 right before start instant | Excluded. |
| Month boundary | O-04 at exact `02/01 00:00` local | Belongs to February, not January. |
| Cancelled order | O-09 with very large amount | Excluded from all totals. |
| Multiple orders per customer/month | C-A months 1 and 2 | Exact order counts and revenues per month. |
| Multiple customers | C-A, C-B, C-C | Cleanly separated groups, no cross-contamination. |
| Empty source | `List.of()` | Empty maps, count 0, revenue 0. |
| Decimal money | O-10 with `0.30` | No precision loss from `double`. |
| Reversed input order | `Collections.reverse(...)` | Totals and groups remain identical. |
| Parallel stream | `parallel = true` | Result matches sequential run. |
| Report ordering | `TreeMap` and comparator | Customer ascending, month ascending. |

### Permutation-Invariance Test

When aggregation is order-independent, reversing the input is a helpful check:

```java
List<Order> reversed = new ArrayList<>(source);
Collections.reverse(reversed);

Report a = build(source, from, to, zone, false);
Report b = build(reversed, from, to, zone, true);
check(a.equals(b), "Report changed after reversing input");
```

This test relies on business semantics of **aggregating by key, not occurrence position**. If the report later adds a field like "first order" using encounter order, adjust the test: "first" must be defined by timestamp/ID or explicit source order.

### `Map.equals` Does Not Verify Ordering

`Map.equals` compares key–value mappings, **not key iteration order**. That is why `selfTest()` also builds `new ArrayList<>(monthly.keySet())` and compares it against the expected order. If ordering is part of the report contract, test it separately.

### `BigDecimal.equals` vs `compareTo`

`new BigDecimal("1.0").equals(new BigDecimal("1.00"))` returns `false` because scales differ; `compareTo(...) == 0` indicates two monetary values are **numerically equal**. `checkMoney` in this lesson uses `compareTo` so assertions do not depend on trailing fractional zeros. If business rules require always showing two decimal places, enforce scale rules or formatting at the report output boundary.

## 9. Performance, Reusability, and Source Limits

### Is Keeping the `eligible` List Necessary?

The example uses:

```java
List<Order> eligible = streamOf(source, parallel)
        .filter(o -> o.status() == Status.PAID)
        .filter(o -> !o.recordedAt().isBefore(start))
        .filter(o -> o.recordedAt().isBefore(end))
        .toList();
```

This intermediate list keeps testing and reuse of the filtered set clear. However, it consumes memory proportional to the number of eligible orders. For large sources, you can chain `filter` directly into `groupingBy` in a **single collect pass** to avoid materializing the list. Benchmark to see which suits your goals.

Note that here, rolling up from `monthly` to `byCustomer` and `grandTotal` does not re-scan the entire order list; it iterates only the **collected groups**.

### A Stream Supports Only One Terminal Operation

After `collect(...)`, the Stream instance is consumed. Given a `List` `source`, calling `source.stream()` again opens a fresh Stream. For single-pass I/O sources, design collectors that accumulate all needed metrics in **one pass** and obey resource-closing rules.

### Parallel Execution Is Not Automatically Faster

`groupingBy` is not a concurrent collector: in parallel mode, the framework may collect into multiple intermediate Maps and merge them, which carries overhead. `groupingByConcurrent` can help when encounter order is not needed, but do not switch without understanding ordering requirements and downstream collector concurrency.

On small datasets, `parallelStream()` rarely yields clear gains. Measure speed and memory on real data; switching to parallel **does not replace** database access policies, timeouts, or backpressure when sources involve I/O.

### Handling Bad Data

Production systems must decide how to handle:

- **Duplicate order `id`s:** if an invoice appears multiple times in the source, this lesson counts **each record as an order**. To count unique invoices, check for duplicates and select valid records; do not simply call `distinct()` across whole objects if fields differ.
- **Refunds/returns:** this example has only `PAID` and `CANCELLED`. Negative amounts are rejected; design an explicit refund model if business rules require it.
- **Missing customer IDs:** the record validates against null and blank strings. Customer display names should be looked up from another contracted source rather than mixing identity aggregation with name resolution.
- **Multiple currencies:** never add USD, VND, and EUR together in the same `BigDecimal`. Group by currency or convert using governed exchange rates and periods.
- **Very long reporting spans:** group count grows with customers × months; `Map` memory depends on distinct key count, not just raw order count.

## 10. Extended Exercises

**Exercise 1 — Daily report.** Replace `YearMonth` with `LocalDate`:

```java
record CustomerDay(String customerId, LocalDate day) {}

CustomerDay key = new CustomerDay(
        order.customerId(),
        order.recordedAt().atZone(zone).toLocalDate()
);
```

Order by `customerId` then `day`; keep the half-open interval and monetary summation unchanged.

**Exercise 2 — Single-month report.** Write a function accepting `YearMonth month` and `ZoneId zone`; construct `from = month.atDay(1)` and `to = month.plusMonths(1).atDay(1)`, then call `build(...)`. Test with an order at exact 00:00 on the first day of the next month.

**Exercise 3 — Top customers.** From `byCustomer`, build a list of customers sorted by revenue descending, breaking ties by customer ID ascending:

```java
List<Map.Entry<String, Stats>> ranking =
        report.byCustomer().entrySet().stream()
                .sorted(Comparator
                        .<Map.Entry<String, Stats>, BigDecimal>comparing(
                                e -> e.getValue().revenue(),
                                Comparator.reverseOrder())
                        .thenComparing(Map.Entry::getKey))
                .toList();
```

Do not infer revenue ranking from Map iteration order.

**Exercise 4 — Consistency check.** For each customer, verify that summing monthly `Stats` equals `byCustomer.get(customerId)` in both order count and revenue. Add a dataset containing a customer with no eligible orders and decide whether that customer should appear in the report.

**Exercise 5 — Duplicate order data.** Add two records with the same `id` but different timestamps. Design a valid policy: reject, pick newest version, or treat as transaction history? Only then write a `toMap` pipeline with a merge function; never assume `distinct()` satisfies the business rule.

**Exercise 6 — Testing another time zone.** Run the same data with `ZoneId.of("UTC")`. Compare order `O-04` between January in UTC and February in Vietnam; explain why one instant can belong to two different reporting months while remaining the exact same `Instant`.

## 11. Key Takeaways

- Clarify **eligible statuses, customer keys, time zone, and the half-open interval `[start, end)`** before building the pipeline.
- Filter with `filter`, construct composite `(customerId, YearMonth)` keys, and pair `groupingBy` with downstream `reducing` to compute order counts and revenue per group.
- Use `BigDecimal` for money and associative combine operations with an identity element; avoid rounding between additions or relying on parallel branch ordering.
- Report iteration order must be **designed with comparators/`TreeMap`**, never inferred from `HashMap`. Test ordering explicitly rather than relying solely on `Map.equals`.
- Test **date/month boundary orders, cancelled orders, empty sources, reversed order, and parallel execution**; optimize only after business correctness is proven on representative data.
