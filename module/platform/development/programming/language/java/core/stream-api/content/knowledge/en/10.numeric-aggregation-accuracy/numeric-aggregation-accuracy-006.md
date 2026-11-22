# Choosing `summaryStatistics` Over Multiple Source Passes

In the **Java Stream API**, we often need multiple metrics over the same dataset: **count, sum, minimum, maximum, and average**. Writing five separate pipelines to call `count()`, `sum()`, `min()`, `max()`, and `average()` may force the program to read or process the source multiple times. `IntSummaryStatistics`, `LongSummaryStatistics`, and `DoubleSummaryStatistics` aggregate all five metrics in **a single terminal operation**.

This topic belongs to **Numeric Aggregation Accuracy**: choosing `summaryStatistics()` avoids re-traversing the source, yet you still must understand numeric type ranges, empty data, floating-point rounding error, parallel execution properties, and stream lifecycle.

## 1. When Does Traversing the Source Multiple Times Become a Problem?

Suppose you have a list of scores `[12, 18, 24, 30]` and need to display statistics. A natural first thought is creating a new stream for each metric:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> scores = Arrays.asList(12, 18, 24, 30);

long count = scores.stream().mapToInt(Integer::intValue).count();
int minimum = scores.stream().mapToInt(Integer::intValue)
    .min().orElseThrow(IllegalStateException::new);
int maximum = scores.stream().mapToInt(Integer::intValue)
    .max().orElseThrow(IllegalStateException::new);
long sum = scores.stream().mapToLong(Integer::longValue).sum();
double average = scores.stream().mapToInt(Integer::intValue)
    .average().orElseThrow(IllegalStateException::new);

System.out.println(count);   // 4
System.out.println(minimum); // 12
System.out.println(maximum); // 30
System.out.println(sum);     // 84
System.out.println(average); // 21.0
```

Each call to `scores.stream()` creates a **new pipeline**. Operations like `min`, `max`, `sum`, and `average` typically need to inspect all relevant data. On large sources or with expensive `filter`/`map` steps, repeating passes wastes time and resources. Certain special cases, such as `count` on a sized source, may be optimized without invoking every mapper; do not assume every lambda always runs once per pipeline.

You cannot store a `Stream` and invoke multiple terminal operations on the same object:

```java
import java.util.stream.IntStream;

IntStream numbers = IntStream.of(12, 18, 24, 30);
long count = numbers.count();

// Invalid: the stream has already been consumed.
// int sum = numbers.sum(); // IllegalStateException
```

With a `List` source, you can create a new stream each time; with single-use sources such as I/O streams, network streams, or consuming iterators, doing so may be impossible or yield inconsistent data across reads.

## 2. `summaryStatistics()`: Five Metrics in One Pipeline

A cleaner approach is converting data to a primitive stream and calling one terminal operation:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;

List<Integer> scores = Arrays.asList(12, 18, 24, 30);

IntSummaryStatistics stats = scores.stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 84
System.out.println(stats.getMin());     // 12
System.out.println(stats.getMax());     // 30
System.out.println(stats.getAverage()); // 21.0
```

`summaryStatistics()` is a **terminal operation**: traversing the source and updating statistical state happen in one pipeline. It is not a short-circuiting operation, because computing exact min/max/sum under contract requires inspecting every remaining finite input element.

Visualizing the accumulation process:

```text
Source -> lazy filter/map -> IntStream -> summaryStatistics()
                                          |
                                          +-- count
                                          +-- sum
                                          +-- min
                                          +-- max
                                          +-- average = sum / count (when count > 0)
```

Each element is fed into the accumulator needed for the metrics; once the terminal operation returns, you read properties from **one result object** without re-traversing the source.

### Choosing the Right Type for the Data

| Primitive stream | Terminal operation | Result object | Readable values |
| --- | --- | --- | --- |
| `IntStream` | `summaryStatistics()` | `IntSummaryStatistics` | `getCount()`, `getSum()`, `getMin()`, `getMax()`, `getAverage()` |
| `LongStream` | `summaryStatistics()` | `LongSummaryStatistics` | Same getters, with `long` for sum/min/max |
| `DoubleStream` | `summaryStatistics()` | `DoubleSummaryStatistics` | Same getters, with `double` for sum/min/max/average |

These types live in `java.util` and have existed since Java 8. `getCount()` always returns `long`; `getAverage()` returns `double`. For `IntSummaryStatistics`, `getSum()` returns `long`, whereas `getMin()` and `getMax()` return `int`. For `LongSummaryStatistics`, sum, min, and max are `long`; for `DoubleSummaryStatistics`, they are `double`.

## 3. From Object Data to Numeric Statistics

Business data usually resides in objects: orders, transactions, exams, or sensors. Use `mapToInt`, `mapToLong`, or `mapToDouble` to extract the right numeric field, then collect statistics.

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;

public class OrderSummary {
    static final class Order {
        final String id;
        final boolean paid;
        final long amountInMinorUnits;

        Order(String id, boolean paid, long amountInMinorUnits) {
            this.id = id;
            this.paid = paid;
            this.amountInMinorUnits = amountInMinorUnits;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
            new Order("A", true, 15000L),
            new Order("B", false, 7000L),
            new Order("C", true, 25000L),
            new Order("D", true, 10000L)
        );

        LongSummaryStatistics paidStats = orders.stream()
            .filter(order -> order.paid)
            .mapToLong(order -> order.amountInMinorUnits)
            .summaryStatistics();

        System.out.println(paidStats.getCount());   // 3
        System.out.println(paidStats.getSum());     // 50000
        System.out.println(paidStats.getMin());     // 10000
        System.out.println(paidStats.getMax());     // 25000
        System.out.println(paidStats.getAverage()); // 16666.666...
    }
}
```

In this example, only paid orders enter the statistics. `filter` and `mapToLong` are lazy intermediate steps; `summaryStatistics` triggers them. Logically each element passes through the pipeline once, rather than writing multiple pipelines repeating the `order.paid` condition and amount extraction.

Storing money in the smallest integer unit is a useful design choice when avoiding `double` decimal representation. However, the **average** from `getAverage()` is still a `double` and may need its own rounding rule when converted to a payable amount.

## 4. Precision of `IntSummaryStatistics`: The Sum Is `long`

An easily overlooked benefit is that `IntSummaryStatistics.getSum()` returns **`long`**, even though the input values are `int`. By contrast, `IntStream.sum()` returns `int` and can overflow if the sum exceeds the 32-bit range.

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;

int[] largeValues = {1_500_000_000, 1_500_000_000};

int intSum = Arrays.stream(largeValues).sum();
IntSummaryStatistics stats = Arrays.stream(largeValues)
    .summaryStatistics();
long summarySum = stats.getSum();

System.out.println(intSum);      // -1294967296 (int overflow)
System.out.println(summarySum);  // 3000000000
System.out.println(stats.getAverage()); // 1500000000.0
```

`IntSummaryStatistics` accumulates `int` values into a `long` sum, preventing `int` overflow in many practical tasks. **That does not mean the sum can never overflow**: with an enormous number of elements or a sum exceeding `Long.MAX_VALUE`/`Long.MIN_VALUE`, `long` also has limits.

If you only want a `long` sum and do not need min/max/count/average, `intStream.asLongStream().sum()` or `mapToLong(...).sum()` usually expresses intent more directly. There is no need to build a full statistics object for a single metric.

### `LongSummaryStatistics` Still Has Limits

```java
import java.util.LongSummaryStatistics;
import java.util.stream.LongStream;

LongSummaryStatistics stats = LongStream.of(Long.MAX_VALUE, 1L)
    .summaryStatistics();

System.out.println(stats.getCount()); // 2
System.out.println(stats.getSum());   // Long.MIN_VALUE due to long overflow
```

`LongSummaryStatistics` uses a `long` sum; it **does not automatically detect or throw on overflow** like `Math.addExact`. When overflow must be detected and only a sum is needed, you can use `LongStream.reduce(0L, Math::addExact)` to throw `ArithmeticException` if addition overflows:

```java
import java.util.stream.LongStream;

long safeTotal = LongStream.of(10L, 20L, 30L)
    .reduce(0L, Math::addExact);

System.out.println(safeTotal); // 60
```

If a sum legitimately exceeds the `long` range under business rules, consider `BigInteger` or `BigDecimal` via `Stream<T>`. Those object types carry different overhead and calculation contracts, yet satisfy precision requirements beyond primitive ranges.

## 5. Empty Data: Always Check `getCount()`

Unlike `min()`, `max()`, or `average()` on primitive streams, which return `OptionalInt`, `OptionalLong`, or `OptionalDouble`, `summaryStatistics()` **always returns a statistics object**, even when there are no elements.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics empty = IntStream.empty().summaryStatistics();

System.out.println(empty.getCount());   // 0
System.out.println(empty.getSum());     // 0
System.out.println(empty.getAverage()); // 0.0
System.out.println(empty.getMin());     // Integer.MAX_VALUE
System.out.println(empty.getMax());     // Integer.MIN_VALUE
```

Before receiving any element, min/max hold **special initial sentinel values** rather than an actual observation. Contract of statistics objects when empty:

| Type | `getMin()` when empty | `getMax()` when empty | `getSum()` | `getAverage()` |
| --- | --- | --- | --- | --- |
| `IntSummaryStatistics` | `Integer.MAX_VALUE` | `Integer.MIN_VALUE` | `0L` | `0.0` |
| `LongSummaryStatistics` | `Long.MAX_VALUE` | `Long.MIN_VALUE` | `0L` | `0.0` |
| `DoubleSummaryStatistics` | `Double.POSITIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | `0.0` | `0.0` |

Therefore, never return `getMin()` from an empty group to users as “the smallest value”. Check `getCount() == 0` before reading min, max, or interpreting average:

```java
if (empty.getCount() == 0) {
    System.out.println("No valid data available for statistics");
} else {
    System.out.println("Minimum: " + empty.getMin());
}
```

In monitoring problems, distinguishing **“average equal to 0”** from **“no samples to compute an average”** is critical. The `0.0` returned on empty data is an API convention, not proof that a zero measurement was observed.

## 6. `DoubleSummaryStatistics`: Understand Precision Errors Before Use

For measurements or probabilities, `DoubleSummaryStatistics` provides the same five metrics:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics measurements = DoubleStream.of(2.5, 3.0, 4.5)
    .summaryStatistics();

System.out.println(measurements.getCount());   // 3
System.out.println(measurements.getSum());     // 10.0
System.out.println(measurements.getMin());     // 2.5
System.out.println(measurements.getMax());     // 4.5
System.out.println(measurements.getAverage()); // approximately 3.3333333333333335
```

`double` is binary floating-point. Many decimal numbers such as `0.1` or `0.2` are not represented exactly in this type. When summing many numbers, rounding error depends on data and addition order. The JDK implementation may use *compensated summation*, yet **you must not treat `getSum()` or `getAverage()` as exact decimal arithmetic**.

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics stats = DoubleStream.of(0.1, 0.2, 0.3)
    .summaryStatistics();

double expected = 0.6;
double tolerance = 1e-12;
System.out.println(Math.abs(stats.getSum() - expected) < tolerance);
// true for the data and threshold in this example
```

The threshold `1e-12` is only illustrative. In real tests, choose an absolute or relative tolerance appropriate to the data's scale and units. If monetary statistics require exact decimal results, use smallest-unit integers or `BigDecimal` with explicit rounding rules.

### `NaN`, Infinity, and Anomalous Values

`DoubleSummaryStatistics` does not automatically discard non-finite values. If the input contains `NaN`, the sum and min/max/average values can become `NaN`; having both `+Infinity` and `-Infinity` also makes the sum undefined:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics stats = DoubleStream
    .of(1.0, Double.NaN, 2.0)
    .summaryStatistics();

System.out.println(Double.isNaN(stats.getSum())); // true
System.out.println(Double.isNaN(stats.getMin())); // true
```

When business rules accept only finite numbers, place an explicit filter before collecting statistics:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics finiteStats = DoubleStream
    .of(1.0, Double.NaN, Double.POSITIVE_INFINITY, 2.0)
    .filter(x -> !Double.isNaN(x) && !Double.isInfinite(x))
    .summaryStatistics();

System.out.println(finiteStats.getCount());   // 2
System.out.println(finiteStats.getAverage()); // 1.5
```

Filtering non-finite values is appropriate only if data-handling rules permit it; in sensor-fault alerting systems, you may need to **record** anomalous samples instead of silently ignoring them.

## 7. `Collectors.summarizingInt/Long/Double` When Grouping Data

`summaryStatistics()` lives on primitive streams. If you are working with `Stream<T>` and want statistics on a numeric field of each element, use these collectors:

| Collector | Mapper accepted | Result |
| --- | --- | --- |
| `Collectors.summarizingInt(mapper)` | `ToIntFunction<? super T>` | `IntSummaryStatistics` |
| `Collectors.summarizingLong(mapper)` | `ToLongFunction<? super T>` | `LongSummaryStatistics` |
| `Collectors.summarizingDouble(mapper)` | `ToDoubleFunction<? super T>` | `DoubleSummaryStatistics` |

Ungrouped example:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<String> words = Arrays.asList("Java", "Stream", "API");

IntSummaryStatistics lengths = words.stream()
    .collect(Collectors.summarizingInt(String::length));

System.out.println(lengths.getCount()); // 3
System.out.println(lengths.getSum());   // 13
```

In output, this matches `words.stream().mapToInt(String::length).summaryStatistics()`. `Collectors.summarizingInt` is especially convenient when nested **inside another collector**, such as `groupingBy`.

### One Logical Pass for Per-Group Statistics

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SummaryByTeam {
    static final class Task {
        final String team;
        final int minutes;

        Task(String team, int minutes) {
            this.team = team;
            this.minutes = minutes;
        }
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
            new Task("API", 30),
            new Task("UI", 45),
            new Task("API", 15),
            new Task("UI", 20),
            new Task("API", 25)
        );

        Map<String, IntSummaryStatistics> byTeam = tasks.stream()
            .collect(Collectors.groupingBy(
                task -> task.team,
                Collectors.summarizingInt(task -> task.minutes)
            ));

        IntSummaryStatistics api = byTeam.get("API");
        System.out.println(api.getCount());   // 3
        System.out.println(api.getSum());     // 70
        System.out.println(api.getMin());     // 15
        System.out.println(api.getMax());     // 30
        System.out.println(api.getAverage()); // 23.333...
    }
}
```

`groupingBy` classifies elements by key, while `summarizingInt` accumulates statistics for each group. This is far better than filtering the entire list **five times per group**. The resulting map contains only keys that actually appeared; calling `byTeam.get("OTHER")` can return `null`, so check whether a group exists before reading its statistics.

To aggregate a single value per group (such as total minutes only), `Collectors.summingInt`/`summingLong` also works well. There is no need to pick `summarizingInt` if count, min, max, and average are unused.

## 8. File Sources, Single-Pass Sources, and Resource Lifecycle

With a stream from `Files.lines`, reading data multiple times means reopening and rescanning the file. If the file is large, that costs I/O; if the file is being updated, separate reads may reflect different snapshots of data.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LongSummaryStatistics;
import java.util.stream.Stream;

public class FileStatistics {
    public static LongSummaryStatistics read(Path path)
            throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.map(String::trim)
                .filter(line -> !line.isEmpty())
                .mapToLong(Long::parseLong)
                .summaryStatistics();
        }
    }
}
```

This pipeline reads each valid line once to update all five metrics, rather than opening five independent file streams. `try-with-resources` closes the stream and its I/O resources upon completion, even if an error occurs while parsing a line.

`summaryStatistics` is a **terminal operation**, yet by itself it **does not replace `close()`**. Collection-backed streams normally do not need closing; I/O-backed streams must have resources managed properly. `Long::parseLong` can throw `NumberFormatException` on invalid lines, so specify malformed-data handling before using it in production.

### Unbounded Sources Must Have a Bound

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics firstHundred = IntStream.iterate(1, n -> n + 1)
    .limit(100)
    .summaryStatistics();

System.out.println(firstHundred.getCount()); // 100
System.out.println(firstHundred.getSum());   // 5050
```

`summaryStatistics` cannot return a complete result if the source generates elements forever without a limit or stopping condition. Use `limit`, a finite source, or `takeWhile` when semantically appropriate to ensure the pipeline can terminate.

## 9. Parallelism: Merging Statistics Under Contract

`IntSummaryStatistics`, `LongSummaryStatistics`, and `DoubleSummaryStatistics` can accumulate via `accept(value)` and merge via `combine(other)`. Calling `parallel().summaryStatistics()` allows the stream machinery to split the source, compute partial statistics, and merge them. You do not manually create a statistics object shared across threads.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.rangeClosed(1, 100_000)
    .parallel()
    .summaryStatistics();

System.out.println(stats.getCount());   // 100000
System.out.println(stats.getSum());     // 5000050000
System.out.println(stats.getMin());     // 1
System.out.println(stats.getMax());     // 100000
System.out.println(stats.getAverage()); // 50000.5
```

For the `int` values in this example, the `long` sum does not overflow, so results match between sequential and parallel runs. Parallelism carries splitting and merging overhead, so it is not guaranteed to be faster.

**Do not** do the following:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

// WRONG example: the same mutable object is updated from multiple threads.
IntSummaryStatistics shared = new IntSummaryStatistics();
IntStream.rangeClosed(1, 100_000)
    .parallel()
    .forEach(shared::accept);

// shared may produce wrong results due to concurrent update races.
```

Statistics objects **have mutable state and are not designed for concurrent updates to a single shared instance**. Let `summaryStatistics()` or `Collectors.summarizing*` coordinate accumulation and combining. Upstream lambdas such as `mapToLong` or `filter` should also avoid mutating the source or depending on mutable external state.

With `double`, addition is not strictly associative due to rounding error. Merge order in a parallel pipeline can affect the trailing bits of `getSum()` and `getAverage()`. Therefore, do not use exact `==` comparisons for floating-point results when tolerance is appropriate; likewise, avoid parallel streams when a fixed floating-point evaluation order is required.

## 10. When to Choose `summaryStatistics`, and When Not To

| Requirement | Choice | Reason |
| --- | --- | --- |
| Need count, min, max, sum, average on the same data | `mapToInt/Long/Double(...).summaryStatistics()` | One pipeline produces all five metrics. |
| Need statistics per group | `groupingBy(..., Collectors.summarizingInt/Long/Double(...))` | Classifies and summarizes in the same collect operation. |
| Need only the sum | `sum()` or `Collectors.summing*` | No need to maintain min/max if unused. |
| Need only min or max | `min()` / `max()` | Expresses intent directly; returns `Optional*` when empty. |
| Need median, percentiles, standard deviation | Another algorithm or collector | `SummaryStatistics` classes do not provide those metrics. |
| Need a sum that never overflows `long` | `BigInteger` or checked addition | `LongSummaryStatistics` does not detect overflow. |
| Need exact decimal currency amounts | Smallest-unit integers or `BigDecimal` | `double` does not represent every decimal fraction exactly. |
| Unbounded source | Bound the source before aggregating | Cannot aggregate an entire infinite sequence. |

### Common Mistakes

1. **Reusing a stream:** calling `sum()` then `average()` on the same `IntStream` throws `IllegalStateException`; a single `summaryStatistics()` terminal operation satisfies multiple metrics at once.
2. **Not checking for empty data:** `getMin()`/`getMax()` can hold sentinel initial values; interpret them only when `getCount() > 0`.
3. **Assuming `getSum()` can never overflow:** `IntSummaryStatistics` sums into `long`, yet `LongSummaryStatistics` can still overflow `long`.
4. **Using `DoubleSummaryStatistics` for exact money:** results can suffer floating-point representation and addition errors.
5. **Sharing a statistics object across threads manually:** `IntSummaryStatistics.accept` on a shared instance is not thread-safe.
6. **Choosing `summaryStatistics` when only one number is needed:** specialized `sum`/`min`/`count` operations can express intent more clearly and avoid unnecessary state.
7. **Ignoring anomalous values:** `NaN`, `Infinity`, malformed text data, or `null` can corrupt statistics or throw exceptions.

## 11. Practice Exercises

**Exercise 1 — Single pass.** Given `List<Integer> scores = Arrays.asList(5, 15, 20, 40)`, use one pipeline with `mapToInt` and `summaryStatistics` to obtain count, sum, min, max, and average. Expected values are **4, 80, 5, 40, 20.0**.

**Exercise 2 — Checking overflow.** Create an `IntStream` containing two `1_500_000_000` values. Compare `sum()` with `summaryStatistics().getSum()`, explain why they differ, and explain why a `long` sum still has limits.

**Exercise 3 — Grouping data.** Given a list of tasks with team name and duration, use `groupingBy` with `summarizingInt` to compute per-team statistics. Handle the case where a team name is absent from the map without calling `null.getCount()`.

**Exercise 4 — Empty data.** Create `IntStream.empty().summaryStatistics()`, observe all five getters, and write logic that displays min/max/average only when samples exist. Explain why `0.0` from `getAverage()` when empty does not represent a measured average.

**Exercise 5 — Anomalous floating-point values.** Use `DoubleStream.of(1.0, Double.NaN, 3.0)` for statistics. Check `getSum()`, then add a filter for finite values and explain how the sample count changes.

**Key takeaway:** When you need **multiple statistics over the same source**, `summaryStatistics()` and the `summarizing*` collectors compute count, sum, min, max, and average in one pipeline, saving repeated traversals and transformations. Always check for empty data, `int`/`long` bounds, `double` rounding errors, and parallel pipeline safety before using the values in business decisions.
