# SummaryStatistics and Collecting Multiple Measurements in Java

## 1. Goal: One Data Pass, Many Statistics

In a real system, the same set of measurements often needs to answer multiple questions: **how many** values were received, what is the **sum**, what are the **min/max**, and what is the **average**? When there are multiple measured attributes (response latency, byte count, temperature), we also want to aggregate all of them in a single pass and, when needed, split statistics by group.

Java provides three basic statistics accumulator classes in the `java.util` package:

- `IntSummaryStatistics`: accepts `int` values.
- `LongSummaryStatistics`: accepts `long` values.
- `DoubleSummaryStatistics`: accepts `double` values.

All three provide **count, sum, min, max, and average**; they support `accept(...)` to ingest another value and `combine(...)` to merge two statistics accumulators. They do not automatically compute variance, median, percentiles, or distinct-value counts.

This lesson covers two usage levels: (1) obtaining multiple statistical metrics for **a single sequence of numbers**, and (2) simultaneously collecting multiple measurement fields of **a sequence of records**, even when some values must be excluded from one metric.

## 2. Choosing the Right Type and Understanding the Results

| Input | Accumulator | Quick creation from stream | `getSum()` type |
| --- | --- | --- | --- |
| `int` | `IntSummaryStatistics` | `IntStream.summaryStatistics()` | `long` |
| `long` | `LongSummaryStatistics` | `LongStream.summaryStatistics()` | `long` |
| `double` | `DoubleSummaryStatistics` | `DoubleStream.summaryStatistics()` | `double` |

The getters all share analogous meanings:

| Getter | Meaning |
| --- | --- |
| `getCount()` | Number of elements fed into the accumulator, type `long` |
| `getSum()` | Sum of elements received |
| `getMin()` | Minimum element received |
| `getMax()` | Maximum element received |
| `getAverage()` | Arithmetic mean, type `double` |

Minimal example:

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats =
        IntStream.of(12, 8, 20, 10).summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 50
System.out.println(stats.getMin());     // 8
System.out.println(stats.getMax());     // 20
System.out.println(stats.getAverage()); // 12.5
~~~

This is a **snippet usable in `jshell` or inside a Java method**; a standalone program with a full class and `main` appears later.

You do not need to traverse a stream five times to call `count`, `sum`, `min`, `max`, and `average`: just call `summaryStatistics()` once, then read the getters on **the same finalized result**. A Java `Stream` cannot be reused after a terminal operation.

For `Stream<T>` containing objects, use the collectors from `java.util.stream.Collectors`:

~~~java
// Assuming Stream<Order> orders and Order has a units() method.
IntSummaryStatistics stats = orders.collect(
        java.util.stream.Collectors.summarizingInt(Order::units)
);
~~~

Here `Order` is a hypothetical application type, not a standard Java class or standalone runnable example. The corresponding collectors are `summarizingInt`, `summarizingLong`, and `summarizingDouble`.

## 3. How the Accumulator Works

An `IntSummaryStatistics` object starts in an empty state; each call to `accept(int)` updates count, sum, min, and max. The average is derived from sum and count when its getter is called. Consequently, extra memory usage **does not grow with sample count**: there is no need to store every value to compute these five statistics.

~~~java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = new IntSummaryStatistics();
stats.accept(5);
stats.accept(15);
stats.accept(-5);

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 15
System.out.println(stats.getMin());     // -5
System.out.println(stats.getMax());     // 15
System.out.println(stats.getAverage()); // 5.0
~~~

After accepting more values, the getters reflect the **new state**. Therefore, clearly distinguish:

- **Accumulator**: a mutable object that can continue receiving data.
- **Snapshot**: numbers copied into a reporting DTO/record for publication to consumers.

If your application needs an immutable report, do not hand a mutable statistics object still being updated elsewhere and assume it is a snapshot.

### Merging Collected Parts

~~~java
IntSummaryStatistics first = new IntSummaryStatistics();
first.accept(2);
first.accept(4);

IntSummaryStatistics second = new IntSummaryStatistics();
second.accept(6);
second.accept(8);

first.combine(second);
System.out.println(first.getCount());   // 4
System.out.println(first.getSum());     // 20
System.out.println(first.getAverage()); // 5.0
~~~

`combine` updates the **receiving object** (`first`) with data from the other object. It is useful in pipelines that split data into parts, especially parallel streams. Do not assume these classes are thread-safe for multiple threads concurrently calling `accept` on **the same instance**.

For ordinary integer aggregation, the order of combining parts does not change the mathematical meaning if there is no overflow. For `double` floating-point numbers, addition order can change the lowest bits of sum and average.

## 4. Empty State and How to Avoid Misleading Results

If no values have been accepted, the getters still return numbers rather than `Optional`:

| Class | `count` | `sum` | `min` | `max` | `average` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `IntSummaryStatistics` | `0` | `0` | `Integer.MAX_VALUE` | `Integer.MIN_VALUE` | `0.0` |
| `LongSummaryStatistics` | `0` | `0` | `Long.MAX_VALUE` | `Long.MIN_VALUE` | `0.0` |
| `DoubleSummaryStatistics` | `0` | `0.0` | `Double.POSITIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | `0.0` |

Example:

~~~java
IntSummaryStatistics empty = new IntSummaryStatistics();
System.out.println(empty.getCount()); // 0
System.out.println(empty.getMin());   // 2147483647
System.out.println(empty.getMax());   // -2147483648
~~~

`getAverage() == 0.0` **does not mean** the dataset's true average is 0 when `count == 0`. Likewise, `getMin()` or `getMax()` on an empty statistics object is a sentinel value, **not an actual measurement**.

When producing reports, always check `getCount() > 0` before presenting min, max, and average. An API might return `null`, omit fields, or use a `hasData` flag for empty statistics; whichever choice you make must be defined clearly.

## 5. Gathering Multiple Measurements from One Record

Suppose each telemetry record has four fields:

- `region`: where the sample originated.
- `latencyMs`: non-negative latency as an `int`.
- `bytes`: non-negative data volume as a `long`.
- `temperatureC`: temperature as a `double`; the system uses non-finite values (`NaN`, `±Infinity`) to mark invalid temperature samples.

The report requires total row count, latency (count/min/max/average), total bytes, valid temperature (count/average), and invalid temperature sample count. **Each metric's count can differ from the row count** because metrics have separate filtering policies.

You could call `stream()` multiple times on the same `List` and build separate reports, but for single-read sources (streaming files, event streams), large datasets, or consistent policy enforcement, a shared accumulator is more convenient.

### Complete Java 17+ Program

Save the following as `MultiMeasureSummaryDemo.java`:

~~~java
import java.util.DoubleSummaryStatistics;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class MultiMeasureSummaryDemo {

    record Reading(String region, int latencyMs, long bytes,
                   double temperatureC) {}

    static final class Metrics {
        long rows;
        long invalidTemperatures;

        final IntSummaryStatistics latency = new IntSummaryStatistics();
        final LongSummaryStatistics bytes = new LongSummaryStatistics();
        final DoubleSummaryStatistics temperature =
                new DoubleSummaryStatistics();

        void accept(Reading reading) {
            if (reading.latencyMs() < 0 || reading.bytes() < 0) {
                throw new IllegalArgumentException(
                        "latencyMs and bytes must be non-negative");
            }

            rows++;
            latency.accept(reading.latencyMs());
            bytes.accept(reading.bytes());

            if (Double.isFinite(reading.temperatureC())) {
                temperature.accept(reading.temperatureC());
            } else {
                invalidTemperatures++;
            }
        }

        Metrics merge(Metrics other) {
            rows += other.rows;
            invalidTemperatures += other.invalidTemperatures;
            latency.combine(other.latency);
            bytes.combine(other.bytes);
            temperature.combine(other.temperature);
            return this;
        }
    }

    static Collector<Reading, Metrics, Metrics> metricsCollector() {
        return Collector.of(Metrics::new, Metrics::accept, Metrics::merge);
    }

    static void print(String label, Metrics m) {
        System.out.printf(
                Locale.ROOT,
                "%s: rows=%d, latency(count=%d,min=%d,max=%d,avg=%.1f), "
                        + "bytes=%d, temp(count=%d,avg=%.1f), invalid=%d%n",
                label,
                m.rows,
                m.latency.getCount(),
                m.latency.getMin(),
                m.latency.getMax(),
                m.latency.getAverage(),
                m.bytes.getSum(),
                m.temperature.getCount(),
                m.temperature.getAverage(),
                m.invalidTemperatures
        );
    }

    public static void main(String[] args) {
        IntSummaryStatistics simple =
                IntStream.of(2, 4, 6).summaryStatistics();

        System.out.printf(
                Locale.ROOT,
                "simple: count=%d sum=%d min=%d max=%d avg=%.1f%n",
                simple.getCount(),
                simple.getSum(),
                simple.getMin(),
                simple.getMax(),
                simple.getAverage()
        );

        List<Reading> readings = List.of(
                new Reading("North", 10, 100L, 21.5),
                new Reading("North", 20, 300L, 22.5),
                new Reading("South", 30, 200L, Double.NaN),
                new Reading("South", 40, 400L, 19.0)
        );

        Metrics all = readings.stream().collect(metricsCollector());
        print("all", all);

        Map<String, Metrics> byRegion = readings.stream().collect(
                Collectors.groupingBy(
                        Reading::region,
                        TreeMap::new,
                        metricsCollector()
                )
        );

        byRegion.forEach(MultiMeasureSummaryDemo::print);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac MultiMeasureSummaryDemo.java
java MultiMeasureSummaryDemo
~~~

Stdout output:

~~~text
simple: count=3 sum=12 min=2 max=6 avg=4.0
all: rows=4, latency(count=4,min=10,max=40,avg=25.0), bytes=1000, temp(count=3,avg=21.0), invalid=1
North: rows=2, latency(count=2,min=10,max=20,avg=15.0), bytes=400, temp(count=2,avg=22.0), invalid=0
South: rows=2, latency(count=2,min=30,max=40,avg=35.0), bytes=600, temp(count=1,avg=19.0), invalid=1
~~~

### Reading the Collector Structure

`Collector.of` is given three components:

1. **Supplier `Metrics::new`**: creates a new accumulator.
2. **Accumulator `Metrics::accept`**: updates all assigned measurements for one sample; each sample passes through the shared accumulator once.
3. **Combiner `Metrics::merge`**: merges partial accumulators, essential when the collector is used with parallel streams.

After `collect`, `all` is the aggregate result for the whole dataset. `groupingBy(Reading::region, TreeMap::new, metricsCollector())` creates **one accumulator per region**, routes each record into its matching group, and uses `TreeMap` to print groups in deterministic key order in the example. With k groups, accumulated memory depends on the number of groups k (aside from the input source), instead of building a list of every record in each group.

Because `South` has one `NaN` temperature, total rows equal 4 while valid temperature samples equal 3. `latency` and `bytes` still count all four rows. **Never use `rows` as the denominator for temperature** when invalid temperature samples have been excluded.

The `rows` and `invalidTemperatures` fields in the example are also `long` counters. For very large data streams, have an overflow detection policy or partition aggregation sessions; `rows++` does not protect against overflow by itself.

## 6. When You Only Need to Aggregate One Field by Group

If you only care about latency, there is no need to write a custom collector:

~~~java
Map<String, IntSummaryStatistics> latencyByRegion =
        readings.stream().collect(
                Collectors.groupingBy(
                        Reading::region,
                        Collectors.summarizingInt(Reading::latencyMs)
                )
        );
~~~

**This is an excerpt inside `main` of the program above**, since `readings` and `Reading` are already defined there.

Correspondingly, `Collectors.summarizingLong(Reading::bytes)` returns `LongSummaryStatistics`; `Collectors.summarizingDouble(Reading::temperatureC)` returns `DoubleSummaryStatistics` (though you must actively handle `NaN` if present in the data).

An example using `Collectors.filtering` (Java 9+) to drop non-finite temperature samples **while still keeping groups**, even a group with no valid temperatures:

~~~java
Map<String, DoubleSummaryStatistics> temperatureByRegion =
        readings.stream().collect(
                Collectors.groupingBy(
                        Reading::region,
                        Collectors.filtering(
                                reading -> Double.isFinite(
                                        reading.temperatureC()),
                                Collectors.summarizingDouble(
                                        Reading::temperatureC)
                        )
                )
        );
~~~

Distinguish `stream().filter(...).collect(groupingBy(...))` from `groupingBy(..., filtering(...))`: the first can **drop an entire group** that has no rows left after filtering; the second keeps the group with an empty downstream accumulator. Which behavior is right depends on the report semantics.

If you want to combine two different collectors in one pass in Java 12+, `Collectors.teeing` can coordinate two downstream collectors and a merger function. When three or more measurements with distinct acceptance criteria are needed, a custom collector like `Metrics` is usually clearer.

## 7. Aggregating Multiple Measurements Correctly in Parallel

When using `parallelStream()` or `stream().parallel()`, the framework can create multiple independent accumulators and call the combiner to merge them. For a custom collector, three requirements must hold:

- **Correct accumulator per sample**: each `accept` properly updates the metrics and filtering rules for that sample.
- **Semantically correct combine**: `merge` adds counters, calls `combine` on each statistics object, and returns the merged state.
- **Order-independent** if you want semantically stable results in parallel; `double` calculations can still differ in the lowest digits due to addition order.

Example with the declared collector:

~~~java
Metrics parallel = readings.parallelStream()
        .collect(metricsCollector());
~~~

This is an excerpt in the same `main` scope as the complete example. `Collector.of` above **does not** declare `CONCURRENT`: the framework can process across separate accumulators and merge them, rather than having multiple threads mutate one `Metrics`. Still, you must never share one `Metrics` instance and call `accept` concurrently from multiple threads outside the collector mechanism without synchronization.

Do not blindly add `Collector.Characteristics.CONCURRENT` to this mutable collector. With `groupingByConcurrent`, container rules, associativity, and thread safety of downstream accumulators must be carefully examined; you cannot assume from using a parallel stream that every statistics object is thread-safe.

A custom accumulator with non-commutative or order-dependent operations (such as concatenating strings in arrival order) will require a stricter combiner design. Even though real-number addition is mathematically associative, **finite floating-point addition is not strictly associative**; small differences between execution plans can appear.

## 8. Precision, Overflow, and Anomalous Data

### `IntSummaryStatistics` Uses `long` for the Sum

~~~java
IntSummaryStatistics stats = java.util.stream.IntStream
        .of(Integer.MAX_VALUE, Integer.MAX_VALUE)
        .summaryStatistics();

System.out.println(stats.getSum()); // 4294967294
~~~

The sum is not capped at `int` in this case because `IntSummaryStatistics.getSum()` returns `long`. However, with extremely high counts or sums exceeding `Long.MAX_VALUE`/`Long.MIN_VALUE`, `long` can still overflow.

`LongSummaryStatistics` also returns a `long` sum and **does not** automatically widen to `BigInteger`. If the problem requires exact sums beyond `long` bounds, design a dedicated `BigInteger` accumulator. When decimal sums must be exact, use `BigDecimal` with an appropriate accumulator rather than converting values to `double` just to use `DoubleSummaryStatistics`.

### `DoubleSummaryStatistics` and Floating-Point Error

`DoubleSummaryStatistics` computes sum and average from `double` values. It uses compensated summation to reduce accumulated error, yet remains subject to binary64 limits; acceptance/combination order can affect the lowest digits. If financial data requires exactness down to the smallest unit, this is not a substitute for `BigDecimal`.

If the measurement sequence contains `NaN`, `DoubleSummaryStatistics` can return `NaN` for min, max, sum, and average. `+Infinity` and `-Infinity` can produce infinite or `NaN` results (for example, when mixing infinities of opposite signs). Filter out non-finite values only when **the system contract permits dropping samples**; in other applications, invalid values should trigger an error or be recorded as a separate error metric.

Example of careful filtering:

~~~java
DoubleSummaryStatistics validTemperature =
        java.util.stream.DoubleStream.of(
                21.5, Double.NaN, Double.POSITIVE_INFINITY, 22.5
        )
        .filter(Double::isFinite)
        .summaryStatistics();

System.out.println(validTemperature.getCount());   // 2
System.out.println(validTemperature.getAverage()); // 22.0
~~~

Note clearly that `getCount() == 2` here is the **filtered** element count, not the raw initial event count (4).

### Do Not Compute One Metric Using Another Metric's Denominator

If a source has optional fields or field-specific filtering rules—for example 100 records where only 72 have finite temperature values—the temperature average must use **72 temperature samples**. The total record count of 100 is a separate metric.

For analyses also needing percentiles or medians, `SummaryStatistics` is insufficient. Exact medians/percentiles generally require retaining distribution information or specialized data structures; variance and standard deviation also require a dedicated accumulator (such as a mergeable online algorithm). Do not infer these quantities solely from count/sum/min/max/average.

## 9. API Design and Testing for Statistical Reports

Distinguish the **collection state** from the **finalized report**. A DTO might return:

~~~json
{
  "region": "North",
  "rows": 2,
  "latency": {
    "count": 2,
    "minMs": 10,
    "maxMs": 20,
    "averageMs": 15.0
  },
  "bytes": {
    "count": 2,
    "sum": 400
  },
  "temperature": {
    "validCount": 2,
    "averageC": 22.0,
    "invalidCount": 0
  }
}
~~~

Populate `min`, `max`, and `average` only when `count > 0`, or standardize `null` representation for empty statistics. If JSON is consumed by JavaScript clients, note that `long` sums can exceed `Number`'s safe integer limit; for especially large byte totals requiring exact preservation, consider transmitting them as decimal strings with a clear schema.

### Recommended Test Suite

1. **Empty stream:** count = 0, do not interpret sentinel min/max as measurements.
2. **Single sample:** min = max = value; average matches; sum is correct.
3. **Negative and positive values:** min/max remain accurate.
4. **Multiple fields with missing/invalid values:** each field tracks its own count; row total remains accurate.
5. **Combining two accumulators:** merging partial stats via `combine` matches statistics of the combined dataset, within floating-point precision limits.
6. **A group entirely invalid in one field:** the group still exists and reports valid count = 0 if downstream policy retains groups.
7. **Large data and type boundaries:** test large `int` values, `long` values near limits, and non-finite `double` values.

Manual verification model for the main example: there are 4 records, `latency` values are 10, 20, 30, 40 so the sum is 100 and average is 25; bytes are 100 + 300 + 200 + 400 = 1000. Three valid temperatures 21.5, 22.5, 19.0 sum to 63.0 with average 21.0; the fourth temperature sample is counted in `invalidTemperatures` and excluded from the sum.

## 10. Common Mistakes and How to Avoid Them

- **Traversing a stream multiple times:** `IntStream.sum()` followed by `IntStream.average()` on the same instance will fail. Call `summaryStatistics()` once or recreate the stream from a repeatable source.
- **Treating empty-statistics min/max as real values:** always check count first.
- **Mixing row count with valid-sample count:** track the sample count used for each metric and the rejected-sample count.
- **Believing `DoubleSummaryStatistics` is completely exact:** it operates on `double`, which can incur rounding error, `NaN`, infinity, and addition-order sensitivity.
- **Believing `LongSummaryStatistics.getSum()` cannot overflow:** the sum is still `long`.
- **Sharing one mutable instance across threads:** use a collector with proper supplier/combiner contracts, or synchronize explicitly in an appropriate concurrent architecture.
- **Filtering and forgetting dropped data:** if skipping `NaN`, add a counter for invalid/error samples.
- **Confusing descriptive summaries with distribution metrics:** `SummaryStatistics` only supports its built-in getters and cannot accurately derive medians or percentiles from them.

### Self-Check Questions

1. For `IntStream.of(4, 8, 12).summaryStatistics()`, what do the five getters return?
2. A group has 5 records, but only 3 have finite temperatures. What should `getCount()` of `DoubleSummaryStatistics` be after filtering?
3. Can you call `getMin()` on an empty statistics object? If so, why should it not be published as a measured result?
4. How can you summarize latency by `region` without writing a custom accumulator?
5. Why should you not convert all values to `double` and use `DoubleSummaryStatistics` when you need an exact `BigDecimal` sum?
6. When switching to `parallelStream()`, which part of a custom collector must be accurate so no samples are lost?

**Answers:** (1) count = 3, sum = 24, min = 4, max = 12, average = 8.0. (2) count = 3. (3) Yes, but it returns a type-specific sentinel; check count = 0. (4) `Collectors.groupingBy(..., Collectors.summarizingInt(...))`. (5) `double` does not preserve all decimal fractions exactly. (6) Supplier, accumulator, and especially combiner must cover all statistics fields and counters.

Key takeaway: `SummaryStatistics` lets you **collect count/sum/min/max/average in a single pass**, while collecting **multiple measurement fields per record** can be built with a composite collector. For trustworthy reports, always specify how each metric filters data, handles empty data, respects numeric bounds, and combines partial results.