# Computing Averages and Statistics with `averaging` and `summarizing`

## 1. The problem: need a single number or a full set of statistics?

In the **JAVA_STREAM_API** module, a declarative pipeline typically uses `filter`, `map`, and `flatMap` to select or transform data, then uses `collect` to aggregate. Two collector groups are especially useful when processing numeric data:

- **`averagingInt`, `averagingLong`, `averagingDouble`**: compute the **arithmetic mean**, returning a `Double` value.
- **`summarizingInt`, `summarizingLong`, `summarizingDouble`**: produce **a statistics object** containing count, sum, minimum, maximum, and average.

For example, given four paid orders, operations may need:

1. The average item quantity per order.
2. The average revenue per order.
3. Simultaneously knowing the order count, minimum revenue, maximum revenue, and total revenue.
4. Similar statistics **by region** using `groupingBy`.

`averaging` is suitable when only **one average number** is needed. `summarizing` is suitable when **multiple metrics are needed at once**, typically in a single pipeline traversal.

Lesson objectives:

- Read the signatures and result types of the six collectors.
- Distinguish `Collector<T, ?, Double>` from `Collector<T, ?, IntSummaryStatistics>` (and the other variants).
- Compose statistics collectors as the **downstream** of `groupingBy`, `filtering`, and `collectingAndThen`.
- Define the contract for **empty sources**, valid `0` values, and average division.
- Control risks of **overflow**, **`double` precision error**, `NaN`, `null` sources, and parallel processing.
- Write tests verifying business outcomes without relying on lambda invocation order.

The full examples in this lesson use **JDK 17 or later** for `record` and `Stream.toList()`. The `averaging*` and `summarizing*` collectors have existed since Java 8; newer APIs will be noted where they appear.

## 2. Reading the signatures of the six collectors

`Collectors` provides the following factory methods (annotations omitted to focus on generics):

```java
<T> Collector<T, ?, Double> averagingInt(
    ToIntFunction<? super T> mapper
)

<T> Collector<T, ?, Double> averagingLong(
    ToLongFunction<? super T> mapper
)

<T> Collector<T, ?, Double> averagingDouble(
    ToDoubleFunction<? super T> mapper
)

<T> Collector<T, ?, IntSummaryStatistics> summarizingInt(
    ToIntFunction<? super T> mapper
)

<T> Collector<T, ?, LongSummaryStatistics> summarizingLong(
    ToLongFunction<? super T> mapper
)

<T> Collector<T, ?, DoubleSummaryStatistics> summarizingDouble(
    ToDoubleFunction<? super T> mapper
)
```

Here:

- `T` is the **element type of the source stream**, such as `Order`.
- `mapper` extracts a primitive `int`, `long`, or `double` value from each `T`.
- `?` represents the **intermediate accumulation state type `A`** hidden by the collector from the caller; it does not mean the collector is stateless.
- The third type parameter, **`R`**, is the result of `collect`: `Double` or a `*SummaryStatistics`.

| Collector | Mapper takes `T` and returns | Result type `R` | Purpose |
| --- | --- | --- | --- |
| `averagingInt` | `int` | `Double` | Average of integers |
| `averagingLong` | `long` | `Double` | Average of long integers |
| `averagingDouble` | `double` | `Double` | Average of floating-point numbers |
| `summarizingInt` | `int` | `IntSummaryStatistics` | Count, sum, min, max, average |
| `summarizingLong` | `long` | `LongSummaryStatistics` | Count, sum, min, max, average |
| `summarizingDouble` | `double` | `DoubleSummaryStatistics` | Count, sum, min, max, average |

Example of reading types from the outside in:

```java
// Assume orders is List<Order>, and Order.amountVnd() returns long.
Double averageAmount = orders.stream()
    .collect(Collectors.averagingLong(Order::amountVnd));

LongSummaryStatistics amountStats = orders.stream()
    .collect(Collectors.summarizingLong(Order::amountVnd));
```

The input is still `Stream<Order>`, **not `LongStream`**. The collector uses `ToLongFunction<Order>` to extract the primitive amount from each order.

**Distinction:** `Stream.collect(Collector)` is a terminal operation. Once called, the stream is consumed; to compute another result from `List<Order>`, create a new stream with `orders.stream()`. If you want multiple metrics in **one pipeline**, `summarizing` often helps avoid traversing the source repeatedly.

## 3. `averagingInt`, `averagingLong`, and `averagingDouble`

### 3.1. `averagingInt`: integer input, `Double` output

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> quantities = List.of(1, 2, 3, 4);

double average = quantities.stream()
    .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(average); // 2.5
```

The collector accumulates integer values and returns the **average as a `Double`**. It is not `int / int` integer division, so the result `2.5` is not truncated to `2`.

If the source is a `Stream<Order>`, there is no need to box quantities into `Integer` before computing:

```java
double averageQuantity = orders.stream()
    .collect(Collectors.averagingInt(Order::quantity));
```

### 3.2. `averagingLong`: average of `long` values

```java
import java.util.List;
import java.util.stream.Collectors;

List<Long> amounts = List.of(100L, 200L, 300L);

double average = amounts.stream()
    .collect(Collectors.averagingLong(Long::longValue));

System.out.println(average); // 200.0
```

The mapper's input type is `long`, yet the result type is still `Double`, **not `Long`**. If the data represents integer monetary amounts in the smallest currency unit and business rules allow zero rounding error, do not treat `Double` as an exact currency representation.

### 3.3. `averagingDouble`: average of floating-point values

```java
import java.util.List;
import java.util.stream.Collectors;

record Measurement(double kilograms) {}

List<Measurement> samples = List.of(
    new Measurement(1.5),
    new Measurement(2.0),
    new Measurement(3.5)
);

double meanWeight = samples.stream()
    .collect(Collectors.averagingDouble(Measurement::kilograms));

System.out.println(meanWeight); // 2.3333333333333335
```

`double` is a binary floating-point number. Many decimal values cannot be represented exactly; sums and averages can suffer rounding error. For `Double.NaN` and infinite values, the result also requires an explicit data policy.

### 3.4. What do all three return on an empty stream?

`Collectors.averagingInt`, `averagingLong`, and `averagingDouble` **return `0.0`** when there are no input elements:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> empty = List.of();

Double average = empty.stream()
    .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(average); // 0.0
```

This is **the collector's contract**, not an assertion that “a sample with value 0 was observed”. If business logic must distinguish between **no samples** and **an actual average of 0**, preserve `count` as well or return a type such as `OptionalDouble`. Section 8 shows how.

## 4. `summarizing`: one collector gathering multiple metrics

The three `*SummaryStatistics` classes provide five key getters:

| Getter | Return type on `IntSummaryStatistics` | Meaning |
| --- | --- | --- |
| `getCount()` | `long` | Number of elements included in the statistics |
| `getSum()` | `long` | Sum of the `int` values |
| `getMin()` | `int` | Minimum value |
| `getMax()` | `int` | Maximum value |
| `getAverage()` | `double` | Arithmetic mean |

With `LongSummaryStatistics`, `getSum()`, `getMin()`, and `getMax()` return `long`; with `DoubleSummaryStatistics`, they return `double`. All three have `getCount()` returning `long` and `getAverage()` returning `double`.

Example:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> values = List.of(3, 5, 8, 4);

IntSummaryStatistics stats = values.stream()
    .collect(Collectors.summarizingInt(Integer::intValue));

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 20
System.out.println(stats.getMin());     // 3
System.out.println(stats.getMax());     // 8
System.out.println(stats.getAverage()); // 5.0
```

A single `collect` produces all five metrics. If the source is a single-use stream (for example, lines from a file), this approach is usually preferable to running five separate terminal operations—which would require recreating the source or buffering all data.

### 4.1. `IntSummaryStatistics` has a `long` sum

`IntSummaryStatistics` uses `long` for `getSum()` even though individual values are `int`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics s = IntStream.of(
    Integer.MAX_VALUE, Integer.MAX_VALUE
).summaryStatistics();

System.out.println(s.getSum()); // 4294967294
```

The sum above exceeds the `int` limit yet still fits in `long`. However, **`long` also has a limit**: for huge counts or additions that must never overflow, you must design arithmetic checks or larger data types.

### 4.2. Summary statistics classes are mutable objects

`IntSummaryStatistics`, `LongSummaryStatistics`, and `DoubleSummaryStatistics` provide `accept(...)` and `combine(...)` to mutate state:

```java
import java.util.LongSummaryStatistics;

LongSummaryStatistics left = new LongSummaryStatistics();
left.accept(100L);
left.accept(200L);

LongSummaryStatistics right = new LongSummaryStatistics();
right.accept(300L);

left.combine(right);
System.out.println(left.getCount()); // 3
System.out.println(left.getSum());   // 600
```

Therefore, the object returned by `summarizing*` is a **mutable snapshot**, not an immutable value object. Avoid sharing the same reference with other parts of the system that might mutate it unintentionally. If an immutable result is required, convert the needed getters into a `record` or DTO in a finishing step.

## 5. Contract table for empty sources

Averaging and summarizing have different default values. The `min`/`max` values of empty statistics are especially error-prone if passed directly into reports.

| Collector / result | Count | Sum | Min | Max | Average |
| --- | ---: | ---: | --- | --- | ---: |
| `averagingInt/Long/Double` on empty | — | — | — | — | `0.0` |
| Empty `IntSummaryStatistics` | 0 | 0 (`long`) | `Integer.MAX_VALUE` | `Integer.MIN_VALUE` | `0.0` |
| Empty `LongSummaryStatistics` | 0 | 0 (`long`) | `Long.MAX_VALUE` | `Long.MIN_VALUE` | `0.0` |
| Empty `DoubleSummaryStatistics` | 0 | 0.0 | `Double.POSITIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | `0.0` |

Example:

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;

LongSummaryStatistics emptyStats = List.<Long>of().stream()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(emptyStats.getCount());   // 0
System.out.println(emptyStats.getSum());     // 0
System.out.println(emptyStats.getMin() == Long.MAX_VALUE); // true
System.out.println(emptyStats.getMax() == Long.MIN_VALUE); // true
System.out.println(emptyStats.getAverage()); // 0.0
```

**Design rule:** treat `getMin()` and `getMax()` as actual measurements **only when `getCount() > 0`**. When count is 0, the displayed result should be “no data”, `OptionalLong.empty()`, or an equivalent state—not the sentinels in the table above.

On primitive streams, `IntStream.average()`, `LongStream.average()`, and `DoubleStream.average()` return `OptionalDouble`; on an empty source, they return `OptionalDouble.empty()`. This is an important difference from `Collectors.averaging*`, which returns `0.0`.

## 6. Complete business example: statistics for paid orders

The example below uses an `Order` record with region, item quantity, order amount (in VND), weight, and payment status.

Business requirements:

1. Aggregate only paid orders.
2. Compute **average item quantity** using `averagingInt`.
3. Compute **average order amount** using `averagingLong`.
4. Compute **average weight** using `averagingDouble`.
5. Collect **count / sum / min / max / average** of order amounts using `summarizingLong`.
6. Group amounts by region, counting only paid orders.

Complete code, compiling on **JDK 17+**:

```java
import java.util.DoubleSummaryStatistics;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class OrderAggregationDemo {

    public record Order(
        String id,
        String region,
        int quantity,
        long amountVnd,
        double weightKg,
        boolean paid
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank()
                    || quantity < 0 || amountVnd < 0
                    || !Double.isFinite(weightKg) || weightKg < 0) {
                throw new IllegalArgumentException("Invalid order");
            }
        }
    }

    public static List<Order> sample() {
        return List.of(
            new Order("O-1", "HN", 2, 120_000L, 1.5,  true),
            new Order("O-2", "HCM", 1, 80_000L, 2.0, true),
            new Order("O-3", "HN", 3, 60_000L, 0.75, true),
            new Order("O-4", "DN", 2, 40_000L, 1.25, false),
            new Order("O-5", "HCM", 4, 160_000L, 4.5, true)
        );
    }

    public static double averagePaidQuantity(List<Order> source) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.averagingInt(Order::quantity));
    }

    public static double averagePaidAmount(List<Order> source) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.averagingLong(Order::amountVnd));
    }

    public static double averagePaidWeight(List<Order> source) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.averagingDouble(Order::weightKg));
    }

    public static LongSummaryStatistics paidAmountStats(
        List<Order> source
    ) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.summarizingLong(Order::amountVnd));
    }

    public static DoubleSummaryStatistics paidWeightStats(
        List<Order> source
    ) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.summarizingDouble(Order::weightKg));
    }

    public static Map<String, LongSummaryStatistics> paidByRegion(
        List<Order> source
    ) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                LinkedHashMap::new,
                Collectors.summarizingLong(Order::amountVnd)
            ));
    }

    public static void main(String[] args) {
        List<Order> orders = sample();

        System.out.println(averagePaidQuantity(orders)); // 2.5
        System.out.println(averagePaidAmount(orders));   // 105000.0
        System.out.println(averagePaidWeight(orders));   // 2.1875

        LongSummaryStatistics amount = paidAmountStats(orders);
        System.out.println(amount.getCount());   // 4
        System.out.println(amount.getSum());     // 420000
        System.out.println(amount.getMin());     // 60000
        System.out.println(amount.getMax());     // 160000
        System.out.println(amount.getAverage()); // 105000.0

        DoubleSummaryStatistics weight = paidWeightStats(orders);
        System.out.println(weight.getSum());     // 8.75
        System.out.println(weight.getAverage()); // 2.1875

        Map<String, LongSummaryStatistics> regions = paidByRegion(orders);
        System.out.println(regions.get("HN").getAverage());  // 90000.0
        System.out.println(regions.get("HCM").getAverage()); // 120000.0
        System.out.println(regions.containsKey("DN"));      // false
    }
}
```

Reading the types in grouping:

```text
Stream<Order>
    │ filter(Order::paid)
    ▼
Stream<Order>
    │ groupingBy(Order::region, ..., summarizingLong(Order::amountVnd))
    ▼
Map<String, LongSummaryStatistics>
```

`LinkedHashMap::new` in the example only determines the **Map implementation and key insertion order** on a sequential `List` source with encounter order. The statistics object for each region is created by the downstream collector. The `Map` is not immutable by default, and the `LongSummaryStatistics` values inside are also mutable.

## 7. `groupingBy` with downstream `averaging` / `summarizing`

### 7.1. Separate average for each group

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Double> averageAmountByRegion =
    OrderAggregationDemo.sample().stream()
        .filter(OrderAggregationDemo.Order::paid)
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.averagingLong(
                OrderAggregationDemo.Order::amountVnd
            )
        ));

System.out.println(averageAmountByRegion.get("HN"));  // 90000.0
System.out.println(averageAmountByRegion.get("HCM")); // 120000.0
```

Here:

- The **outer** collector groups `Order` instances by `region`.
- The **inner** collector receives the `Order` elements belonging to each region, extracts `amountVnd`, and computes the average.
- The downstream type is `Collector<Order, ?, Double>`.
- The outer result is `Map<String, Double>`.

There is no need to manually build `Map<String,List<Order>>` and then loop over each list to compute the average. Using a downstream collector expresses **multi-level** aggregation directly within a single `collect`.

### 7.2. Getting the full statistics object per group

```java
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, LongSummaryStatistics> statsByRegion =
    OrderAggregationDemo.sample().stream()
        .filter(OrderAggregationDemo.Order::paid)
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.summarizingLong(
                OrderAggregationDemo.Order::amountVnd
            )
        ));

LongSummaryStatistics hn = statsByRegion.get("HN");
System.out.println(hn.getCount());   // 2
System.out.println(hn.getSum());     // 180000
System.out.println(hn.getMin());     // 60000
System.out.println(hn.getMax());     // 120000
System.out.println(hn.getAverage()); // 90000.0
```

Fundamentally, each group has its own statistics state. You must not take the **average of regional averages** to derive the overall order average, unless all regions have the same sample count.

For example, HN has two orders and HCM has two orders, so the average of the two means `90_000` and `120_000` happens to equal the overall average `105_000`. But if one region has one order and another has ten orders, taking the simple average of the two means will be wrong.

Formula to use when combining groups with different sample counts:

\[
\overline{x}
= \frac{\sum_{g} n_g \cdot \overline{x}_g}{\sum_{g} n_g}
= \frac{\sum_{g} \mathrm{sum}_g}{\sum_{g} n_g}
\]

Where `n_g` is the sample count of group `g`. `summarizing` retains both `count` and `sum`, making it suitable for expressing this problem.

## 8. `filter` before grouping vs. `Collectors.filtering` inside groups

Both filtering approaches can produce **differences in the key set**, even though the statistics on remaining groups are identical.

### 8.1. `Stream.filter` before `groupingBy`

```java
var filteredBeforeGrouping = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .collect(Collectors.groupingBy(
        OrderAggregationDemo.Order::region,
        Collectors.summarizingLong(
            OrderAggregationDemo.Order::amountVnd
        )
    ));

System.out.println(filteredBeforeGrouping.containsKey("DN")); // false
```

Region DN only has unpaid orders. When filtering before grouping, **no DN elements remain** to create a group.

### 8.2. `Collectors.filtering` as a downstream

`Collectors.filtering` has been available since **JDK 9**:

```java
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, LongSummaryStatistics> withEmptyGroups =
    OrderAggregationDemo.sample().stream()
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.filtering(
                OrderAggregationDemo.Order::paid,
                Collectors.summarizingLong(
                    OrderAggregationDemo.Order::amountVnd
                )
            )
        ));

System.out.println(withEmptyGroups.containsKey("DN")); // true
System.out.println(withEmptyGroups.get("DN").getCount()); // 0
System.out.println(withEmptyGroups.get("DN").getSum());   // 0
```

The outer collector still sees the DN order and creates the **DN group key**; the downstream `filtering` rejects that element before computing statistics, producing a result with `count == 0`. Thus:

- **Filter before grouping:** only keys of filtered elements exist.
- **Filter in downstream:** keys from the unfiltered source can still exist, with empty statistics.

If all orders in a region are filtered out by the downstream, `getAverage() == 0.0` is merely the return value of a statistics object with no samples; it must **not** be reported as a true average revenue of 0.

## 9. Preserving the “no samples” state with `collectingAndThen`

If an API needs to distinguish “average is 0” from “no data”, `Collectors.averaging*` does not carry enough information on its own. You can use `summarizing*` and then transform `count == 0` into an optional result.

`Collectors.collectingAndThen` takes a downstream collector and a finisher to transform the downstream result into the desired public type:

```java
import java.util.OptionalDouble;
import java.util.stream.Collector;
import java.util.stream.Collectors;

static <T> Collector<T, ?, OptionalDouble> optionalAverageLong(
    java.util.function.ToLongFunction<? super T> mapper
) {
    return Collectors.collectingAndThen(
        Collectors.summarizingLong(mapper),
        stats -> stats.getCount() == 0
            ? OptionalDouble.empty()
            : OptionalDouble.of(stats.getAverage())
    );
}
```

Usage example with `Order`:

```java
import java.util.OptionalDouble;

OptionalDouble average = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .collect(optionalAverageLong(
        OrderAggregationDemo.Order::amountVnd
    ));

System.out.println(average.orElseThrow()); // 105000.0

OptionalDouble missing = java.util.stream.Stream
    .<OrderAggregationDemo.Order>empty()
    .collect(optionalAverageLong(
        OrderAggregationDemo.Order::amountVnd
    ));

System.out.println(missing.isEmpty()); // true
```

This is an example of a **composed collector**:

```text
Order
  └─ summarizingLong(amountVnd) ──> LongSummaryStatistics
                                    └─ collectingAndThen
                                       ├─ count == 0: OptionalDouble.empty()
                                       └─ count > 0: OptionalDouble.of(avg)
```

**Note:** `OptionalDouble` solves **sample presence/absence** but does not turn `double` into an exact monetary type. If revenue must preserve absolute decimal accuracy under financial rules, see section 11.

If the input is already a primitive stream, `LongStream.average()` returns `OptionalDouble` directly:

```java
OptionalDouble direct = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .mapToLong(OrderAggregationDemo.Order::amountVnd)
    .average();
```

Choose between this and a composed collector based on your goal: a primitive terminal operation is suitable for **a single statistic of the whole stream**; a composed collector is suitable when composing with `groupingBy` or a custom finishing step.

## 10. Turning mutable statistics into an immutable result

`*SummaryStatistics` classes allow mutation after collection. To return an immutable report, you can use a `record` and `collectingAndThen`.

```java
import java.util.OptionalLong;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record AmountReport(
    long count,
    long totalVnd,
    OptionalLong minVnd,
    OptionalLong maxVnd,
    java.util.OptionalDouble averageVnd
) {}

static <T> Collector<T, ?, AmountReport> amountReport(
    java.util.function.ToLongFunction<? super T> mapper
) {
    return Collectors.collectingAndThen(
        Collectors.summarizingLong(mapper),
        stats -> {
            boolean any = stats.getCount() > 0;
            return new AmountReport(
                stats.getCount(),
                stats.getSum(),
                any ? OptionalLong.of(stats.getMin()) : OptionalLong.empty(),
                any ? OptionalLong.of(stats.getMax()) : OptionalLong.empty(),
                any ? java.util.OptionalDouble.of(stats.getAverage())
                    : java.util.OptionalDouble.empty()
            );
        }
    );
}
```

`AmountReport` has immutable value fields, so callers cannot subsequently invoke `accept` or `combine` to alter published statistics.

Note that a record only guarantees that its **field references** are final; if a field points to a mutable collection, the record is not necessarily deeply immutable. The example above uses primitives and Optionals, so it does not have that issue.

Usage:

```java
AmountReport report = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .collect(amountReport(
        OrderAggregationDemo.Order::amountVnd
    ));

System.out.println(report.count()); // 4
System.out.println(report.totalVnd()); // 420000
System.out.println(report.minVnd().orElseThrow()); // 60000
System.out.println(report.averageVnd().orElseThrow()); // 105000.0
```

If a group has no samples, `AmountReport` expresses this via `count == 0` and empty Optionals, instead of leaking `Long.MAX_VALUE` or `Long.MIN_VALUE` into JSON or report tables.

## 11. Floating-point error, overflow, and correctness of averages

### 11.1. Integers can also overflow when summed

`summarizingInt` stores the sum as `long`, whereas `summarizingLong` stores the sum as `long` and **can overflow**. `summingLong`/`averagingLong` also provide no guarantee of throwing an error automatically when addition exceeds the `long` range.

```java
import java.util.List;
import java.util.stream.Collectors;

List<Long> huge = List.of(Long.MAX_VALUE, 1L);

long wrapped = huge.stream()
    .collect(Collectors.summarizingLong(Long::longValue))
    .getSum();

// The long value has overflowed its range; do not use for financial statistics.
```

If absolute accuracy is required, do not compute large monetary amounts using an accumulator with an unchecked `long` sum. Use `BigInteger` or `BigDecimal` with an explicit rounding policy.

Example of summing integer VND amounts using `BigInteger` with downstream `reducing`:

```java
import java.math.BigInteger;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigInteger> exactByRegion =
    OrderAggregationDemo.sample().stream()
        .filter(OrderAggregationDemo.Order::paid)
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.reducing(
                BigInteger.ZERO,
                order -> BigInteger.valueOf(order.amountVnd()),
                BigInteger::add
            )
        ));

System.out.println(exactByRegion.get("HN")); // 180000
```

For **monetary averages**, division may not have a finite decimal representation. Therefore, specify `scale` and `RoundingMode` instead of immediately converting to `double`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

BigInteger sum = BigInteger.valueOf(10L);
long count = 3L;

BigDecimal exactRoundedAverage =
    new BigDecimal(sum).divide(
        BigDecimal.valueOf(count),
        2,
        RoundingMode.HALF_UP
    );

System.out.println(exactRoundedAverage); // 3.33
```

Use this pattern only when business rules allow two decimal places and `HALF_UP` rounding. With real data, ensure `sum` and `count` come from the exact same set of records; running two pipelines over a mutable source can yield inconsistent results.

### 11.2. `double` is not bit-exact associative

With `double`, addition does not guarantee:

```text
(a + b) + c == a + (b + c)
```

due to rounding error. A parallel collection may combine partial sums in a different order, changing the last digits of `average` or `sum`. The Javadoc also notes that input order and addition order can affect the precision of `averagingDouble` and `summarizingDouble`.

Example illustrating loss of precision:

```java
double a = 1.0e16;
double b = 1.0;
double c = -1.0e16;

System.out.println((a + b) + c); // 0.0
System.out.println(a + (b + c)); // 0.0 in this case

// Consider a different grouping:
System.out.println((a + c) + b); // 1.0
```

Do not write unit tests requiring the floating-point result of a parallel collector to be **bit-for-bit identical** to the sequential result without a contract guaranteeing it. Use an appropriate tolerance delta, or a more accurate/stable summation algorithm when required by the domain.

### 11.3. `NaN`, infinity, and invalid measurements

`DoubleSummaryStatistics` has special rules for `NaN` and infinity. If any sample is `NaN`, sum/average calculations can become `NaN`; min/max results are also affected per the class contract. With both `+Infinity` and `-Infinity`, addition yields `NaN`.

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics stats = DoubleStream.of(
    1.0, Double.NaN, 2.0
).summaryStatistics();

System.out.println(Double.isNaN(stats.getAverage())); // true
```

If a report only allows finite numbers, validate at the **data boundary** using `Double.isFinite(value)`. You can use `filter` to drop invalid samples if permitted by business rules; when an invalid sample indicates a device or input error, **throwing an error or recording a separate error** is usually better than silently ignoring it.

### 11.4. Ratios and weighted averages

`averagingInt`/`averagingLong`/`averagingDouble` compute an **unweighted arithmetic mean**: each stream element contributes one sample. If you want the average revenue **per item**, taking the average of each order's total value is incorrect when item quantities differ across orders.

With `quantity` as item count and `amountVnd` as the order's total amount:

\[
\text{Average value/item}
= \frac{\sum \text{amountVnd}}{\sum \text{quantity}}
\]

Samples with different quantities must carry different weights. Use an accumulation that tracks both numerator and denominator (for example, a custom collector, `teeing`, or an appropriate statistical model) and handle the case where the denominator is 0. Do not try to force a weighted average problem into `averagingLong(Order::amountVnd)`.

## 12. Choosing between collectors and primitive stream terminal operations

If you only need **one metric for the whole stream**, primitive streams are sometimes more concise and avoid boxing:

```java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;

var source = OrderAggregationDemo.sample();

OptionalDouble avg = source.stream()
    .filter(OrderAggregationDemo.Order::paid)
    .mapToInt(OrderAggregationDemo.Order::quantity)
    .average();

IntSummaryStatistics stats = source.stream()
    .filter(OrderAggregationDemo.Order::paid)
    .mapToInt(OrderAggregationDemo.Order::quantity)
    .summaryStatistics();
```

Comparison:

| Problem | Natural API |
| --- | --- |
| Single average on `Stream<Order>` | `collect(averagingInt/Long/Double(mapper))` |
| Single summary statistics on `Stream<Order>` | `collect(summarizingInt/Long/Double(mapper))` |
| Average of an entire `IntStream` | `IntStream.average()` → `OptionalDouble` |
| Summary statistics of an entire `LongStream` | `LongStream.summaryStatistics()` |
| Average per key of `Stream<Order>` | `groupingBy(key, averaging*)` |
| Summary statistics per key | `groupingBy(key, summarizing*)` |
| Average that distinguishes empty sources inside grouping | `collectingAndThen(summarizing*, finisher)` as downstream |

`IntStream`, `LongStream`, and `DoubleStream` have specialized terminal operations, but **do not** support `collect(Collector<T,A,R>)` like object streams. If you need `Collectors.groupingBy` for primitive data, you can convert to an object stream via `boxed()` or `mapToObj(...)`, or design an appropriate primitive aggregation.

## 13. Laziness, side effects, and parallel processing performance

Collectors run only when `collect` consumes the pipeline. Preceding `filter` and `map` remain lazy intermediate operations.

```java
import java.util.stream.Collectors;
import java.util.stream.IntStream;

double averageEven = IntStream.rangeClosed(1, 10)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(averageEven); // 6.0
```

This example is semantically correct, though if only the average is needed, `IntStream.filter(...).average()` is more direct and avoids boxing to `Integer`.

### 13.1. Do not put side effects inside the mapper

Avoid using a `ToIntFunction` mapper as a mechanism to increment an external counter:

```java
// Anti-pattern:
java.util.concurrent.atomic.AtomicInteger observed =
    new java.util.concurrent.atomic.AtomicInteger();

double wrongDesign = OrderAggregationDemo.sample().stream()
    .collect(Collectors.averagingInt(order -> {
        observed.incrementAndGet();
        return order.quantity();
    }));

// observed should not be part of the business contract.
```

Stream mappers should be **non-interfering** and **stateless**. `AtomicInteger` only solves concurrent updates to the counter variable; it does not turn side effects in a mapper into good design. To know the sample count, use `summarizingInt(...).getCount()` instead of writing side effects.

### 13.2. Parallel streams are not automatically faster

`groupingBy` with downstream `summarizing*` can run on a parallel stream: the framework can create multiple statistics states and merge them. However:

- Splitting and merging overhead increases, especially with few records or many small groups.
- The collector is not necessarily `CONCURRENT`; the standard mechanism is for each branch to accumulate into its own state and then combine.
- `double` arithmetic can yield differences due to merge order.
- If output order is required, check encounter order and collector characteristics; standard grouped maps do not guarantee key iteration order.
- Do not share the same mutable `IntSummaryStatistics` across multiple threads calling `accept` directly without proper synchronization.

Measure with representative datasets before adding `parallel()`. On small datasets, sequential code is usually simpler.

### 13.3. Resources and memory

`summarizing` keeps relatively compact state (a few variables for sum, count, and extrema), without holding every element like `toList()`. However, `groupingBy` creates a statistics object **for each key**, so a large number of keys still increases memory usage.

If the source is `Files.lines(path)` or a stream holding I/O resources, close it with `try-with-resources`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.IntSummaryStatistics;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static IntSummaryStatistics lineLengthStats(Path path)
    throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.collect(
            Collectors.summarizingInt(String::length)
        );
    }
}
```

For an empty file, `getCount() == 0`. If file access fails, do not arbitrarily turn the failure into empty statistics and treat it as “no data”; an I/O error and an empty source are two different states.

## 14. Common mistakes

| Mistake | Why is it dangerous? | How to handle |
| --- | --- | --- |
| Assuming `averaging*` on empty returns `OptionalDouble.empty()` | The collector actually returns `0.0` | Use `summarizing*` + count or primitive `average()` |
| Reading `getMin/getMax` when `count == 0` as real numbers | The values are sentinels | Check `getCount() > 0` |
| Using group averages to derive overall average without sample counts | Groups may have different weights | Add sums and sample counts |
| Using `summarizingLong` for monetary totals that can exceed `long` | The sum can overflow | `BigInteger`/`BigDecimal` or arithmetic overflow checks |
| Comparing `double` with exact equality in every test | Rounding error depends on data and combine order | Tolerance delta or exact arithmetic |
| Keeping `NaN`/Infinity without a contract | Can corrupt sum, min, max, and average | Validate data or classify errors |
| Calling `average` when a weighted average is needed | Each element is counted as an equal sample | Design numerator and denominator accumulation |
| Replacing `Stream.filter` with downstream `filtering` unthinkingly | Changes the grouping key set | Choose based on whether empty groups should exist |
| Returning raw `SummaryStatistics` assuming immutability | Callers can call `accept/combine` | Build an immutable DTO/record |
| Running multiple terminal operations on the same stream | Streams are single-use | Create a new stream or use an aggregate collector |
| Assuming `parallel` is always faster | Adds merge overhead and floating-point differences | Benchmark and keep mappers pure |

## 15. JUnit 5 tests

The example below references `OrderAggregationDemo` from section 6. Place the test file in the appropriate package alongside the source code and declare JUnit Jupiter in the project.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class OrderAggregationDemoTest {

    @Test
    void averagingCollectorsCalculateMean() {
        var source = OrderAggregationDemo.sample();

        assertEquals(2.5,
            OrderAggregationDemo.averagePaidQuantity(source), 1e-12);
        assertEquals(105_000.0,
            OrderAggregationDemo.averagePaidAmount(source), 1e-12);
        assertEquals(2.1875,
            OrderAggregationDemo.averagePaidWeight(source), 1e-12);
    }

    @Test
    void summarizingLongReturnsAllMetrics() {
        LongSummaryStatistics stats =
            OrderAggregationDemo.paidAmountStats(
                OrderAggregationDemo.sample()
            );

        assertEquals(4L, stats.getCount());
        assertEquals(420_000L, stats.getSum());
        assertEquals(60_000L, stats.getMin());
        assertEquals(160_000L, stats.getMax());
        assertEquals(105_000.0, stats.getAverage(), 1e-12);
    }

    @Test
    void summarizingDoubleReturnsWeightMetrics() {
        DoubleSummaryStatistics stats =
            OrderAggregationDemo.paidWeightStats(
                OrderAggregationDemo.sample()
            );

        assertEquals(4L, stats.getCount());
        assertEquals(8.75, stats.getSum(), 1e-12);
        assertEquals(0.75, stats.getMin(), 1e-12);
        assertEquals(4.5, stats.getMax(), 1e-12);
        assertEquals(2.1875, stats.getAverage(), 1e-12);
    }

    @Test
    void averagingOnEmptyInputIsZero() {
        var empty = List.<OrderAggregationDemo.Order>of();

        assertEquals(0.0,
            OrderAggregationDemo.averagePaidAmount(empty), 0.0);

        LongSummaryStatistics stats =
            OrderAggregationDemo.paidAmountStats(empty);
        assertEquals(0L, stats.getCount());
        assertEquals(Long.MAX_VALUE, stats.getMin());
        assertEquals(Long.MIN_VALUE, stats.getMax());
    }

    @Test
    void groupingAfterFilterOmitsRegionWithoutPaidOrders() {
        Map<String, LongSummaryStatistics> map =
            OrderAggregationDemo.paidByRegion(
                OrderAggregationDemo.sample()
            );

        assertFalse(map.containsKey("DN"));
        assertEquals(2L, map.get("HN").getCount());
        assertEquals(180_000L, map.get("HN").getSum());
    }

    @Test
    void downstreamFilteringPreservesExistingRegionKey() {
        var map = OrderAggregationDemo.sample().stream()
            .collect(Collectors.groupingBy(
                OrderAggregationDemo.Order::region,
                Collectors.filtering(
                    OrderAggregationDemo.Order::paid,
                    Collectors.summarizingLong(
                        OrderAggregationDemo.Order::amountVnd
                    )
                )
            ));

        assertTrue(map.containsKey("DN"));
        assertEquals(0L, map.get("DN").getCount());
    }

    @Test
    void sequentialAndParallelIntegerSummariesAgree() {
        var data = OrderAggregationDemo.sample();

        LongSummaryStatistics sequential = data.stream()
            .collect(Collectors.summarizingLong(
                OrderAggregationDemo.Order::amountVnd
            ));
        LongSummaryStatistics parallel = data.parallelStream()
            .collect(Collectors.summarizingLong(
                OrderAggregationDemo.Order::amountVnd
            ));

        assertEquals(sequential.getCount(), parallel.getCount());
        assertEquals(sequential.getSum(), parallel.getSum());
        assertEquals(sequential.getMin(), parallel.getMin());
        assertEquals(sequential.getMax(), parallel.getMax());
    }
}
```

**Test matrix to add:** empty source, single-sample source, all samples equal to `0`, negative-only values (if the domain allows), equal min/max, values near numeric type bounds, missing group keys, mapper encountering `null`, `NaN` and infinity values, large parallel datasets, average precision, and weighted combination.

## 16. Practice exercises

### Exercise 1 — Comparing `averagingInt` and `summarizingInt`

Given `List<Integer> values = List.of(1, 3, 5, 7)`. Write two pipelines:

1. Obtain a single average using `Collectors.averagingInt`.
2. Obtain `IntSummaryStatistics` and print `count`, `sum`, `min`, `max`, and `average`.

Explain why both averages equal `4.0` while their result types differ.

### Exercise 2 — Empty source and `OptionalDouble`

Given `List<Integer> empty = List.of()`, contrast:

```java
empty.stream().collect(Collectors.averagingInt(Integer::intValue))
empty.stream().mapToInt(Integer::intValue).average()
```

Explain why the first result is `0.0` and the second result is `OptionalDouble.empty()`. Propose a return type for an API where `0` is also a valid average value.

### Exercise 3 — Statistics by group

Given a list of products with `category` and `price`, use `groupingBy(category, summarizingLong(price))` to return `Map<String,LongSummaryStatistics>`. Write tests for two groups with values and one group completely eliminated after `Stream.filter`.

### Exercise 4 — Difference between two filtering approaches

From `OrderAggregationDemo.sample()`, use `Stream.filter(Order::paid)` before grouping, then use downstream `Collectors.filtering(Order::paid, summarizingLong(...))`. Verify the difference in whether region DN has a key in the map.

### Exercise 5 — Weighted average

Define `record Item(int quantity, long totalVnd) {}`. With `[Item(1,100), Item(3,900)]`:

- The average of `totalVnd` **per record** is `(100+900)/2 = 500`.
- The average value **per item** is `(100+900)/(1+3) = 250`.

Design the correct accumulation for the second result and handle a source whose total `quantity == 0`. Do not use `averagingLong(Item::totalVnd)` for the “per item” question.

### Exercise 6 — Large monetary amounts

Given amounts `Long.MAX_VALUE` and `1`, explain why `summarizingLong` is unsuitable if the report requires an exact total. Write a version using `BigInteger` so the sum does not overflow; then use `BigDecimal.divide` with `RoundingMode` to present the average.

### Exercise 7 — Immutability and resources

Write a collector combining `summarizingInt(String::length)` and `collectingAndThen` into `record LengthReport(long count, long sum, OptionalInt min, OptionalInt max)`. For a file read with `Files.lines`, use `try-with-resources`. Distinguish the empty-file case from the missing-file case.

## 17. Decision table for collector aggregation

| Requirement | Choice |
| --- | --- |
| Need average of a property on an object stream | `averagingInt/Long/Double(mapper)` |
| Need count, sum, min, max, average in one pass | `summarizingInt/Long/Double(mapper)` |
| Need metrics per key | `groupingBy(key, summarizing*)` |
| Only need average per key | `groupingBy(key, averaging*)` |
| Need to keep group key even if elements fail downstream predicate | `groupingBy(key, filtering(predicate, summarizing*))` |
| Need to distinguish no samples from average equal to 0 | `getCount()` or `OptionalDouble` from finisher |
| Need to return an immutable DTO | `collectingAndThen(summarizing*, stats -> new Report(...))` |
| Need to compute average directly on a primitive stream | `IntStream/LongStream/DoubleStream.average()` |
| Need exact monetary sum exceeding `long` | `BigInteger`/`BigDecimal` and division/rounding rules |
| `NaN` or infinity exists in measurement data | Validate or establish a clear policy |
| Need a weighted average | Accumulate weighted sum and sum of weights |
| Want speedup via `parallel()` | Keep mapper pure, understand combiner, benchmark and allow float tolerance |

`averaging*` and `summarizing*` are two complementary collector families in the Java Stream API. **`averaging` produces a single mean**, while **`summarizing` preserves enough information about count, sum, and extrema** to produce more reliable reports. When combining them with `groupingBy`, `filtering`, and `collectingAndThen`, pay close attention to the difference between **no samples** and **samples equal to 0**, numeric domain limits, `double` precision, statistics mutability, and parallel merge overhead.
