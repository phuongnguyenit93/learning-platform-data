# Computing `sum`, `average`, `min`, `max`, and `summaryStatistics`

> **Chapter:** Primitive Streams  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, `collect`; extending to grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while understanding limits on state, resources, and performance.

In revenue reports, exam scores, temperatures, or inventory counts, common requirements are **summing**, **averaging**, finding the **minimum**, finding the **maximum**, and computing **multiple statistics at once**. Java provides dedicated *terminal operations* on `IntStream`, `LongStream`, and `DoubleStream`. They express intent clearly and operate directly on primitive types, reducing boxing/unboxing demand compared to `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>`.

Lesson objectives:

1. Choose the right operation and understand the return types of `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()`.
2. Retrieve results safely when a stream has no elements.
3. Compute multiple statistics in a single traversal.
4. Recognize floating-point rounding error, integer overflow risk, and limits when processing large or parallel datasets.

## 1. Three primitive stream types and how to create sources

Unlike `Stream<T>`, which holds object references, primitive streams operate directly on one of three types—`int`, `long`, or `double`:

| Stream Type | Element Data | Source Example | Typical Use Cases |
| --- | --- | --- | --- |
| `IntStream` | `int` | `IntStream.of(2, 4, 6)` | Scores, quantities, indices. |
| `LongStream` | `long` | `LongStream.of(100L, 200L)` | Counts or sums exceeding `int` range, milliseconds. |
| `DoubleStream` | `double` | `DoubleStream.of(1.5, 2.5)` | Measurements, floating-point values tolerating rounding error. |

There are several ways to go from existing data to a primitive stream:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

IntStream fromArray = Arrays.stream(new int[] {5, 10, 15});
IntStream fromList = List.of(5, 10, 15).stream()
        .mapToInt(Integer::intValue);
LongStream orderIds = LongStream.of(1001L, 1002L, 1003L);
DoubleStream temperatures = DoubleStream.of(28.5, 29.0, 30.25);
```

When data is in object form, `mapToInt`, `mapToLong`, and `mapToDouble` extract numeric keys:

```java
record Product(String name, int quantity, long revenueCents) {}

List<Product> products = List.of(
        new Product("A", 3, 125_000L),
        new Product("B", 7, 250_000L)
);

int totalQuantity = products.stream()
        .mapToInt(Product::quantity)
        .sum(); // 10

long totalRevenueCents = products.stream()
        .mapToLong(Product::revenueCents)
        .sum(); // 375000
```

The declarations above are standalone syntax illustrations. In snippets that reuse `Product`, `products`, or other variables, place them in the same scope when running. Section 3 provides a complete Java program.

**Lifecycle rule:** invoking a terminal operation consumes the Stream. Do not call `sum()` and then `average()` on **the same** `IntStream` instance; create a new Stream from a re-traversable source or use `summaryStatistics()` when multiple metrics are needed in one pass.

## 2. Aggregation APIs and return types

| Terminal operation | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| `sum()` | `int` | `long` | `double` |
| `average()` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |
| `min()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `max()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `summaryStatistics()` | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |

All are **terminal operations**. Until a terminal operation is present, intermediate steps such as `filter` or `mapToInt` generally have not traversed the source yet. Once `sum` or `summaryStatistics` is called, the pipeline is traversed to produce the result.

### Summing with `sum()`

```java
int sum = java.util.stream.IntStream.of(5, 10, 15).sum();
// 30

long longSum = java.util.stream.LongStream.of(3_000_000_000L, 4_000_000_000L)
        .sum();
// 7000000000

double doubleSum = java.util.stream.DoubleStream.of(1.5, 2.0, 3.5)
        .sum();
// 7.0
```

`sum()` returns the numeric type directly. For an empty source, `sum()` returns **0** (or `0.0`) because 0 is the additive identity.

### Averaging with `average()`

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble avg = IntStream.of(7, 8, 10).average();
System.out.println(avg.orElseThrow()); // 8.333333333333334
```

`average()` returns `OptionalDouble` **for all three primitive stream types**. The result can have a fractional part even when the source is `IntStream` or `LongStream`. On an empty source, there is no arithmetic mean, so the result is `OptionalDouble.empty()`, not 0.

### Finding minimum and maximum

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt minimum = IntStream.of(9, 2, 7, 4).min();
OptionalInt maximum = IntStream.of(9, 2, 7, 4).max();

System.out.println(minimum.orElseThrow()); // 2
System.out.println(maximum.orElseThrow()); // 9
```

On primitive streams, `min()` and `max()` **do not require a `Comparator`** because they use the numeric ordering of the primitive type. If you need to find the **object** with the largest property value, use `Stream<T>.max(Comparator.comparingInt(...))` to retain the object instead of `mapToInt(...).max()`, which returns only the number.

## 3. Complete Java 17+ program: score statistics

The example below demonstrates all five operations on an `int[]` source. Save the contents into `PrimitiveStatisticsDemo.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class PrimitiveStatisticsDemo {
    public static void main(String[] args) {
        int[] scores = {12, 18, 24, 30, 36};

        // Each Arrays.stream(scores) call creates a new Stream.
        int sum = Arrays.stream(scores).sum();
        OptionalDouble average = Arrays.stream(scores).average();
        OptionalInt min = Arrays.stream(scores).min();
        OptionalInt max = Arrays.stream(scores).max();

        System.out.println("sum = " + sum);
        System.out.println("average = " + average.orElseThrow());
        System.out.println("min = " + min.orElseThrow());
        System.out.println("max = " + max.orElseThrow());

        // One pass for count, sum, min, max, average.
        IntSummaryStatistics stats = Arrays.stream(scores)
                .summaryStatistics();

        System.out.println("count = " + stats.getCount());
        System.out.println("stats.sum = " + stats.getSum());
        System.out.println("stats.average = " + stats.getAverage());
        System.out.println("stats.min = " + stats.getMin());
        System.out.println("stats.max = " + stats.getMax());
    }
}
```

Output:

```text
sum = 120
average = 24.0
min = 12
max = 36
count = 5
stats.sum = 120
stats.average = 24.0
stats.min = 12
stats.max = 36
```

Notice the **data type difference**: `IntStream.sum()` returns `int`, while `IntSummaryStatistics.getSum()` returns `long`. This becomes crucial when the sum of elements can exceed the 32-bit range.

## 4. `summaryStatistics()`: multiple metrics in one pass

If you need sum, average, minimum, and maximum together, calling four independent terminal operations on a reusable source results in four traversals (in the general case). `summaryStatistics()` returns an accumulator object holding **count, sum, min, max, and average** while traversing the source once:

```text
Data source
    │
    ▼
 filter / mapToInt     ← intermediate steps if any
    │
    ▼
 summaryStatistics()   ← terminal operation
    │
    ├── count
    ├── sum
    ├── min
    ├── max
    └── average
```

The three statistics classes have corresponding methods:

| Class | `getCount()` | `getSum()` | `getMin()` / `getMax()` | `getAverage()` |
| --- | --- | --- | --- | --- |
| `IntSummaryStatistics` | `long` | `long` | `int` | `double` |
| `LongSummaryStatistics` | `long` | `long` | `long` | `double` |
| `DoubleSummaryStatistics` | `long` | `double` | `double` | `double` |

Example with large numbers:

```java
import java.util.LongSummaryStatistics;
import java.util.stream.LongStream;

LongSummaryStatistics stats = LongStream
        .of(1_000_000_000L, 2_000_000_000L, 3_000_000_000L)
        .summaryStatistics();

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 6000000000
System.out.println(stats.getMin());     // 1000000000
System.out.println(stats.getMax());     // 3000000000
System.out.println(stats.getAverage()); // 2.0E9
```

With `DoubleStream`, there is `DoubleSummaryStatistics` and corresponding getters:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics temperatures = DoubleStream
        .of(28.5, 30.0, 29.5)
        .summaryStatistics();

System.out.println(temperatures.getCount());   // 3
System.out.println(temperatures.getSum());     // 88.0
System.out.println(temperatures.getMin());     // 28.5
System.out.println(temperatures.getMax());     // 30.0
System.out.println(temperatures.getAverage()); // 29.333333333333332
```

The `average` value on `double` is a binary approximation of `88 / 3`; never compare floating-point averages using `==` when exact precision is required.

### `summaryStatistics` is not an element collection

The statistics object stores only summary metrics and **does not retain the original elements**. If you want statistics per group (e.g., per department or product category), group using `collect(groupingBy(...))` with appropriate downstream collectors. That is a different problem from summarizing a single primitive sequence.

## 5. Empty streams: distinguishing “no data” from zero

Behavior on an **empty source** is crucial whenever a `filter` step eliminates all elements.

| Operation | On `IntStream.empty()` |
| --- | --- |
| `sum()` | `0` |
| `average()` | `OptionalDouble.empty()` |
| `min()` | `OptionalInt.empty()` |
| `max()` | `OptionalInt.empty()` |
| `summaryStatistics().getCount()` | `0` |
| `summaryStatistics().getSum()` | `0L` |
| `summaryStatistics().getMin()` | `Integer.MAX_VALUE` |
| `summaryStatistics().getMax()` | `Integer.MIN_VALUE` |
| `summaryStatistics().getAverage()` | `0.0` |

`getMin()` and `getMax()` on an empty statistics object are **initial sentinel values**, not real extrema. Likewise, `getAverage() == 0.0` does not prove there was a 0 in the data.

```java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.IntStream;

IntSummaryStatistics emptyStats = IntStream.empty()
        .summaryStatistics();

if (emptyStats.getCount() == 0) {
    System.out.println("No data to compute extrema or average");
} else {
    System.out.println("Min: " + emptyStats.getMin());
    System.out.println("Average: " + emptyStats.getAverage());
}

OptionalDouble average = IntStream.empty().average();
System.out.println(average.isPresent()); // false
```

For an empty `LongSummaryStatistics`, `getMin()` is `Long.MAX_VALUE` and `getMax()` is `Long.MIN_VALUE`. For an empty `DoubleSummaryStatistics`, `getMin()` is `Double.POSITIVE_INFINITY` and `getMax()` is `Double.NEGATIVE_INFINITY`. In all three cases, **check `getCount() > 0`** before interpreting min/max/average.

### Using `Optional` when a result may be absent

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble maybeAverage = IntStream.of().average();

// Let the caller know there is no average:
if (maybeAverage.isPresent()) {
    System.out.println(maybeAverage.getAsDouble());
} else {
    System.out.println("No scores yet");
}

// Use default 0 only when business rules explicitly specify so:
double averageForDashboard = maybeAverage.orElse(0.0);
```

Do not call `getAsInt()` or `getAsDouble()` when the corresponding Optional may be empty without checking first: these methods can throw `NoSuchElementException`. When data is required to exist, `orElseThrow()` can be used.

## 6. Integer overflow: `sum()` can be wrong even when every element is valid

Java `int` addition has the domain `[-2^{31}, 2^{31}-1]`. If the sum exceeds this range, the integer **overflows** without `IntStream.sum()` throwing an exception.

```java
import java.util.stream.IntStream;

int wrong = IntStream.of(2_000_000_000, 2_000_000_000).sum();
System.out.println(wrong); // -294967296 (int overflow)

long correct = IntStream.of(2_000_000_000, 2_000_000_000)
        .asLongStream()
        .sum();
System.out.println(correct); // 4000000000

long fromStats = IntStream.of(2_000_000_000, 2_000_000_000)
        .summaryStatistics()
        .getSum();
System.out.println(fromStats); // 4000000000
```

`asLongStream()` switches addition to `long`. `IntSummaryStatistics` also accumulates the sum in `long`, even though `IntStream.sum()` returns `int`. However, `long` still has a limit: `LongStream.sum()` and `LongSummaryStatistics.getSum()` can also overflow when the total exceeds the `long` range.

When you need to **detect** overflow rather than merely widening the numeric domain, `Math.addExact` can be used for sequential or parallel reduction with checked addition:

```java
long exact = java.util.stream.LongStream
        .of(9_000_000_000L, 8_000_000_000L)
        .reduce(0L, Math::addExact);
// 17000000000
```

This example fits within `long` and throws no error. If the sum exceeds `long`, `Math.addExact` throws `ArithmeticException`. For arbitrarily large integers, values can be converted to `BigInteger` and reduced over `Stream<BigInteger>`, at the cost of no longer being a primitive stream.

## 7. `double` error, NaN, infinity, and signed zero

Unlike integers, `double` uses binary floating-point representation. Many decimals cannot be represented exactly, so `sum()` and `average()` can be **approximations**:

```java
double total = java.util.stream.DoubleStream.of(0.1, 0.2).sum();
System.out.println(total); // typically prints 0.30000000000000004
```

`DoubleStream.sum()` implementations may use *compensated summation* to reduce error in some cases. However, addition order can vary by execution strategy and results are **not guaranteed to be strictly exact**. Likewise, `DoubleSummaryStatistics` is not a tool for unit-exact monetary calculations.

When calculating money with exact rounding rules, store amounts in the smallest currency unit as integers if overflow cannot occur, or use `BigDecimal`:

```java
import java.math.BigDecimal;
import java.util.List;

BigDecimal totalMoney = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20")
).stream().reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(totalMoney); // 0.30
```

This is a `Stream<BigDecimal>`, not a `DoubleStream`, because data type and precision requirements dictate the proper solution.

### Special values

`DoubleStream` has several rules to know:

- If the stream contains `Double.NaN`, `min()` and `max()` yield a result containing `NaN` per their operation contracts.
- For `+0.0` and `-0.0`, `min()` treats `-0.0` as smaller than `+0.0`; `max()` treats `+0.0` as greater than `-0.0`.
- Adding opposite infinities or `NaN` can make `sum` evaluate to `NaN`. Ordering and summation strategy on `double` affect precision of finite results.

```java
import java.util.stream.DoubleStream;

System.out.println(DoubleStream.of(-0.0, +0.0)
        .min().orElseThrow()); // -0.0
System.out.println(DoubleStream.of(-0.0, +0.0)
        .max().orElseThrow()); // 0.0

System.out.println(Double.isNaN(
        DoubleStream.of(2.0, Double.NaN).max().orElseThrow()));
// true
```

If an application accepts only finite values, **define a filtering policy** before computing statistics:

```java
double[] measurements = {1.2, Double.NaN, 2.4, Double.POSITIVE_INFINITY};

java.util.DoubleSummaryStatistics finiteStats = java.util.Arrays
        .stream(measurements)
        .filter(Double::isFinite)
        .summaryStatistics();

System.out.println(finiteStats.getCount()); // 2
System.out.println(finiteStats.getSum());   // approximately 3.6
```

Removing `NaN` or `Infinity` changes the reported dataset, so apply it only when business rules treat them as invalid data.

## 8. Practical example: inventory statistics after filtering

Suppose a system needs statistics on **stock quantities of active products**. Combine `filter` (intermediate, lazy) with `mapToInt` (converting to `IntStream`) and `summaryStatistics()`:

```java
import java.util.IntSummaryStatistics;
import java.util.List;

public class InventoryStatisticsDemo {
    record Item(String sku, boolean active, int stock) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A-01", true, 12),
                new Item("A-02", false, 99),
                new Item("B-03", true, 8),
                new Item("B-04", true, 20)
        );

        IntSummaryStatistics stats = items.stream()
                .filter(Item::active)
                .mapToInt(Item::stock)
                .summaryStatistics();

        System.out.println("Item count: " + stats.getCount());
        System.out.println("Total stock: " + stats.getSum());
        System.out.println("Min: " + stats.getMin());
        System.out.println("Max: " + stats.getMax());
        System.out.println("Average: " + stats.getAverage());
    }
}
```

Output:

```text
Item count: 3
Total stock: 40
Min: 8
Max: 20
Average: 13.333333333333334
```

Key points to note:

- `filter(Item::active)` drops inactive items **before** statistics are computed.
- `mapToInt(Item::stock)` extracts only stock counts; from this point on, `Item` objects are no longer in the stream.
- `stats.getCount()` counts **retained items**, not total product units.
- If you need to find **which item has the highest stock**, use `items.stream().filter(Item::active).max(Comparator.comparingInt(Item::stock))`; the result is `Optional<Item>`.
- If all items are inactive, the statistics result has `getCount() == 0`, and `getMin()`/`getMax()` should not be presented as real extrema.

## 9. Performance, data sources, and parallel processing

### One pass for multiple metrics

For aggregations over a finite source without precomputed results, typical cost is **O(n)** to traverse n elements. `summaryStatistics()` combines multiple accumulators in one pass, reducing source reads when `count`, `sum`, `min`, `max`, and `average` are all needed at once.

Do not assume `summaryStatistics()` is always faster than every alternative: if only the sum is needed, direct `sum()` is simpler and avoids computing extra unneeded metrics. Measure with representative data when performance truly matters.

### Streams cannot be reused

```java
import java.util.stream.IntStream;

IntStream stream = IntStream.of(1, 2, 3);
int total = stream.sum(); // 6

// Invalid: the same stream has already been consumed.
// double avg = stream.average().orElseThrow();
```

Create a new Stream from a re-traversable `List` or array, or use `summaryStatistics()` if data should only be read once. For resource-backed sources like files or I/O connections, respect resource lifecycles, close streams properly, and avoid reading multiple times arbitrarily.

### Unbounded sources and short-circuiting

`sum`, `average`, `min`, `max`, and `summaryStatistics` all must **inspect all data** of a finite source to return an overall result. They generally do not terminate if an unbounded source is not bounded:

```java
import java.util.stream.IntStream;

// Clear stopping point:
int total = IntStream.iterate(1, n -> n + 1)
        .limit(5)
        .sum();
System.out.println(total); // 15

// Must not run unbounded on an infinite source:
// IntStream.iterate(1, n -> n + 1).sum();
```

`limit` before the terminal operation establishes a finite bound. On an unbounded source capable of generating huge numbers, also consider overflow as in section 6.

### Parallelism and result stability

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.rangeClosed(1, 1_000_000)
        .parallel()
        .summaryStatistics();

System.out.println(stats.getCount()); // 1000000
System.out.println(stats.getSum());   // 500000500000
```

Stream aggregations provide mechanisms to combine branch results when running in parallel. For `int`/`long`, overflow must still be considered. For `double`, changing addition order can cause fractional results to differ across execution strategies or runs. `parallel()` is not automatically faster either, because it incurs source splitting, task management, and result merging overhead.

**Practical rule:** choose `mapToInt`/`mapToLong`/`mapToDouble` matching the data type; enable parallelism only after performance measurement and ensure the pipeline has no lambdas relying on shared mutable state.

## 10. Common errors and fixes

| Error | Consequence | Fix |
| --- | --- | --- |
| Calling `average().getAsDouble()` on an empty Stream | `NoSuchElementException` | Check `isPresent()`, or use `orElse` if a default policy exists. |
| Treating `getMin() == Integer.MAX_VALUE` as a real value when empty | Incorrect extrema reported | Check `stats.getCount() > 0`. |
| Using `IntStream.sum()` for sums exceeding `int` | Integer overflow, wrong result | Switch to `asLongStream().sum()` or `IntSummaryStatistics.getSum()` if within `long`. |
| Using `LongStream.sum()` for sums exceeding `long` | Possible integer overflow | Use a `BigInteger` strategy / overflow check. |
| Using `double` for exact monetary calculations | Representation and rounding error | Use integer minor units with adequate range or `BigDecimal`. |
| Reusing one Stream for `sum` and `average` | `IllegalStateException` | Create a new Stream or use `summaryStatistics`. |
| Using `mapToInt` when getter returns nullable `Integer` | Auto-unboxing can throw `NullPointerException` | Filter `null` or define a business default value. |
| Using `max()` on a primitive stream when the original object is needed | Only numeric value remains, object lost | Use `Stream<T>.max(Comparator.comparingInt(...))`. |
| Running statistics on an unbounded infinite source | Never terminates | Limit the source or design finite partitions/windows. |
| Thinking `summaryStatistics()` groups automatically | Only aggregates the entire stream | Use appropriate collectors when multiple groups are needed. |

## 11. Self-practice

**Exercise 1 — Sum and average.** Given `int[] numbers = {3, 6, 9, 12}`, what are the sum and average?

```java
int total = java.util.Arrays.stream(numbers).sum(); // 30
double avg = java.util.Arrays.stream(numbers).average().orElseThrow(); // 7.5
```

**Exercise 2 — Filter before statistics.** Given `IntStream.of(-3, 2, 5, 8)`, consider only positive numbers. What are `min`, `max`, and `sum`?

**Answer:** The remaining elements are `2, 5, 8`; `min = 2`, `max = 8`, `sum = 15`. You can obtain them together with:

```java
var stats = java.util.stream.IntStream.of(-3, 2, 5, 8)
        .filter(n -> n > 0)
        .summaryStatistics();
```

**Exercise 3 — Empty data.** Do `IntStream.empty().sum()` and `IntStream.empty().average()` have the same meaning?

**Answer:** No. The sum of an empty set is `0` by the additive identity; the average is undefined and represented by `OptionalDouble.empty()`.

**Exercise 4 — Overflow.** Does `IntStream.of(2_000_000_000, 2_000_000_000).sum()` return `4_000_000_000`?

**Answer:** No, `int` cannot hold that value; use `.asLongStream().sum()` to get `4_000_000_000L`.

**Exercise 5 — Choosing the API.** If only exact total revenue in whole cents is needed, should you convert to `DoubleStream`?

**Answer:** Not necessarily. If values and sum fit in `long`, storing as `long` and using `mapToLong(...).sum()` is more appropriate. If there is overflow risk beyond `long` or complex decimal rules apply, consider `BigInteger`/`BigDecimal` with an explicit rounding policy.

## Takeaways

- `sum()` returns a number directly; `average()` returns `OptionalDouble`; `min()`/`max()` return primitive-specific Optional types.
- `summaryStatistics()` retrieves `count`, `sum`, `min`, `max`, and `average` **in a single traversal** and returns the statistics class matching `int`, `long`, or `double`.
- On statistics from an empty stream, **check `getCount() > 0`** before trusting min/max/average; getters hold initial sentinel values.
- `IntStream.sum()` can overflow `int`; `IntSummaryStatistics.getSum()` uses `long`. `DoubleStream` has floating-point error, so it does not replace exact monetary arithmetic.
- Choose the right primitive source, bound infinite sources, and weigh traversal cost and precision before selecting an aggregation approach or parallel execution.
