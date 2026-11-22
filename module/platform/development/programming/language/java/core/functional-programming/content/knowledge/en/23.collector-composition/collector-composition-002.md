# `summarizingInt()`, `summarizingLong()`, and `summarizingDouble()` in Java Stream

When processing data with Java Stream, many scenarios require knowing the element count, sum, minimum value, maximum value, and average of a numeric property **at the same time**. Instead of running five separate terminal operations, `Collectors.summarizingInt()`, `Collectors.summarizingLong()`, and `Collectors.summarizingDouble()` perform **a single collection pass** into the corresponding summary statistics object.

All three collectors accept a **numeric extractor function** (*numeric extractor*) from each element `T`, but differ in the numeric type and result type:

| Collector | Extractor function | Result object type |
| --- | --- | --- |
| `Collectors.summarizingInt(extractor)` | `ToIntFunction<? super T>`, returns `int` | `IntSummaryStatistics` |
| `Collectors.summarizingLong(extractor)` | `ToLongFunction<? super T>`, returns `long` | `LongSummaryStatistics` |
| `Collectors.summarizingDouble(extractor)` | `ToDoubleFunction<? super T>`, returns `double` | `DoubleSummaryStatistics` |

The summary statistics classes are in `java.util`; the collectors are in `java.util.stream.Collectors`. They can be used starting from Java 8; examples in this article prefer **Java 17+**.

**Key point to remember:** `summarizingInt/Long/Double` are **Collector factory methods**; `stream.collect(...)` itself is the **terminal operation** that executes the aggregation. The result is not a `Map` or a single average number, but an object containing multiple metrics.

## 1. Meaning and How to Read the Results

Each summary statistics object provides the following methods:

| Method | Meaning | Return type for Int | Return type for Long | Return type for Double |
| --- | --- | --- | --- | --- |
| `getCount()` | Number of collected values | `long` | `long` | `long` |
| `getSum()` | Sum of values | `long` | `long` | `double` |
| `getMin()` | Minimum value | `int` | `long` | `double` |
| `getMax()` | Maximum value | `int` | `long` | `double` |
| `getAverage()` | Arithmetic mean | `double` | `double` | `double` |

Several important points:

- With `IntSummaryStatistics`, **`getSum()` returns `long`**, not `int`. This allows storing the sum of many `int` values that exceeds the `int` limit; however, if the sum exceeds the `long` limit, it can still overflow.
- `LongSummaryStatistics.getSum()` returns `long`: it does not automatically switch to `BigInteger`, so it can overflow when the sum exceeds the limit.
- `DoubleSummaryStatistics` uses `double` floating-point numbers, which have rounding errors; it is not suitable for guaranteeing exact monetary calculations.
- `getAverage()` returns `double` even for the two integer collectors. Do not assume the result is integer division or an `OptionalDouble`.
- `getCount()` counts the number of **values that actually pass through the collector after filtering/mapping steps**, not the original size of the collection before the pipeline.

Intuitive formula for a non-empty set of `n` numeric elements:

~~~text
count   = n
sum     = sum of values
min     = minimum value
max     = maximum value
average = sum / n  (represented as double, subject to rounding)
~~~

That is the conceptual model. For `double`, the JDK may use compensated summation and compute the average in a way that improves numerical stability; you should not assume binary floating-point addition is completely exact.

## 2. Standalone Runnable Example: Same Source, Three Summary Types

Create the file `SummaryCollectorsDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.LongSummaryStatistics;
import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class SummaryCollectorsDemo {
    record Sale(String region, int units, long revenueCents,
                double weight) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", 3, 1200L, 1.5),
                new Sale("South", 5, 1800L, 2.25),
                new Sale("North", 2, 600L, 1.25)
        );

        IntSummaryStatistics units = sales.stream()
                .collect(Collectors.summarizingInt(Sale::units));

        LongSummaryStatistics revenue = sales.stream()
                .collect(Collectors.summarizingLong(Sale::revenueCents));

        DoubleSummaryStatistics weights = sales.stream()
                .collect(Collectors.summarizingDouble(Sale::weight));

        System.out.printf(Locale.ROOT,
                "units count=%d sum=%d min=%d max=%d avg=%.2f%n",
                units.getCount(), units.getSum(), units.getMin(),
                units.getMax(), units.getAverage());

        System.out.printf(Locale.ROOT,
                "cents count=%d sum=%d min=%d max=%d avg=%.2f%n",
                revenue.getCount(), revenue.getSum(), revenue.getMin(),
                revenue.getMax(), revenue.getAverage());

        System.out.printf(Locale.ROOT,
                "weight count=%d sum=%.1f min=%.2f max=%.2f avg=%.2f%n",
                weights.getCount(), weights.getSum(), weights.getMin(),
                weights.getMax(), weights.getAverage());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 SummaryCollectorsDemo.java
java SummaryCollectorsDemo
~~~

Stdout:

~~~text
units count=3 sum=10 min=2 max=5 avg=3.33
cents count=3 sum=3600 min=600 max=1800 avg=1200.00
weight count=3 sum=5.0 min=1.25 max=2.25 avg=1.67
~~~

Step-by-step explanation:

1. `sales.stream()` has type `Stream<Sale>`.
2. `Sale::units` is an extractor `Sale -> int`; `summarizingInt` produces `IntSummaryStatistics`.
3. `Sale::revenueCents` returns `long`; `summarizingLong` produces `LongSummaryStatistics`.
4. `Sale::weight` returns `double`; `summarizingDouble` produces `DoubleSummaryStatistics`.
5. The resulting count is 3 because there are three `Sale` items; total units is `3 + 5 + 2 = 10`; total cents is `1200 + 1800 + 600 = 3600`; total weight is `1.5 + 2.25 + 1.25 = 5.0`.
6. `printf(Locale.ROOT, ...)` fixes the decimal separator as a dot, using the `%.2f` format so stdout has a consistent number of decimal places, avoiding dependence on the default locale.

In the example there are **three independent collect operations**, because we want three different types of statistics. If you only need one group of metrics, a single collect is enough. For a source that can only be traversed once, you can consider `Collectors.teeing` or another composite collector instead of re-consuming the same `Stream`.

## 3. Differences Between 32-bit Integer, 64-bit Integer, and Double

The three collectors are not three interchangeable names for the same result. Choose based on the type and value range to be processed:

- Use **`summarizingInt`** for quantities, ages, scores, or properties that are `int`; the sum result has type `long`.
- Use **`summarizingLong`** for long counters, numeric timestamps, or monetary amounts represented in minor units with type `long`; the sum result still has type `long`.
- Use **`summarizingDouble`** for floating-point measurements, weights, temperatures, or metrics that tolerate `double` precision error; the result may contain `NaN` or infinite values if the input contains those values.

Example with large `int` values:

~~~java
// Illustrative snippet inside a method:
IntSummaryStatistics stats =
        java.util.stream.Stream.of(Integer.MAX_VALUE, Integer.MAX_VALUE)
                .collect(java.util.stream.Collectors.summarizingInt(
                        Integer::intValue));

System.out.println(stats.getSum()); // 4294967294
~~~

If you use `IntStream.sum()`, the sum of `int` elements has type `int` and can overflow when exceeding the limit. `IntSummaryStatistics.getSum()` uses `long`, so it can store the sum `4294967294` in the example above. This does **not** mean it supports arbitrarily large numbers: beyond the `Long.MAX_VALUE` threshold there is still a risk of overflow.

On `LongSummaryStatistics`, addition uses `long` integer arithmetic; it does not automatically detect every overflow case. For financial or accounting data that requires overflow detection, consider checked arithmetic strategies, `BigDecimal`/`BigInteger`, or another business-appropriate model rather than relying on summary statistics.

## 4. When the Stream Is Empty: The Result Is Not an `Optional`

This is an easy point to confuse with terminal operations such as `average()`, `min()`, and `max()` on primitive streams. The `summarizing...` collectors **still produce a valid summary statistics object**, even when there are no elements.

| Value when source is empty | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| --- | --- | --- | --- |
| `getCount()` | `0` | `0` | `0` |
| `getSum()` | `0` (long) | `0` (long) | `0.0` |
| `getMin()` | `Integer.MAX_VALUE` | `Long.MAX_VALUE` | `Double.POSITIVE_INFINITY` |
| `getMax()` | `Integer.MIN_VALUE` | `Long.MIN_VALUE` | `Double.NEGATIVE_INFINITY` |
| `getAverage()` | `0.0` | `0.0` | `0.0` |

The min/max values in the empty case are **sentinels used as initial values for aggregation**, not evidence that the data actually contains those min/max values. To present min/max or average as a meaningful statistic, check `getCount() > 0` first. Do not use `getMin() == Integer.MAX_VALUE` to infer emptiness, because that value could also genuinely appear in the data.

File `EmptySummaryDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.LongSummaryStatistics;
import java.util.DoubleSummaryStatistics;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class EmptySummaryDemo {
    public static void main(String[] args) {
        IntSummaryStatistics ints = Stream.<Integer>empty()
                .collect(Collectors.summarizingInt(Integer::intValue));
        LongSummaryStatistics longs = Stream.<Long>empty()
                .collect(Collectors.summarizingLong(Long::longValue));
        DoubleSummaryStatistics doubles = Stream.<Double>empty()
                .collect(Collectors.summarizingDouble(Double::doubleValue));

        System.out.println("int count=" + ints.getCount()
                + ", sum=" + ints.getSum()
                + ", min=" + ints.getMin()
                + ", max=" + ints.getMax()
                + ", avg=" + ints.getAverage());

        System.out.println("long count=" + longs.getCount()
                + ", sum=" + longs.getSum()
                + ", min=" + longs.getMin()
                + ", max=" + longs.getMax()
                + ", avg=" + longs.getAverage());

        System.out.println("double count=" + doubles.getCount()
                + ", sum=" + doubles.getSum()
                + ", min=" + doubles.getMin()
                + ", max=" + doubles.getMax()
                + ", avg=" + doubles.getAverage());
    }
}
~~~

~~~bash
javac --release 17 EmptySummaryDemo.java
java EmptySummaryDemo
~~~

Stdout:

~~~text
int count=0, sum=0, min=2147483647, max=-2147483648, avg=0.0
long count=0, sum=0, min=9223372036854775807, max=-9223372036854775808, avg=0.0
double count=0, sum=0.0, min=Infinity, max=-Infinity, avg=0.0
~~~

Here, **an empty source does not produce `Optional.empty()`**. If business logic requires displaying "no data" instead of an average of 0, check the count:

~~~java
// Illustrative snippet inside a method that has IntSummaryStatistics stats.
String averageText = stats.getCount() == 0
        ? "No data" : Double.toString(stats.getAverage());
~~~

A summary statistics object with `getCount() == 1` actually has one observed value; in that case both its min and max equal that value, and the average corresponds to that value converted to double.

## 5. Using `summarizingInt` as a Downstream Collector of `groupingBy`

A very useful application is **per-group statistics** rather than across the entire stream. `Collectors.groupingBy(classifier, downstream)` produces a `Map<K,D>`; `downstream` can be any of the three summary collectors.

Example: summarizing sales units by region, resulting in `Map<String,IntSummaryStatistics>`:

~~~text
Stream<Purchase>
    .collect(groupingBy(Purchase::region,
                        summarizingInt(Purchase::units)))
                   ↓
Map<String, IntSummaryStatistics>
~~~

Create the file `GroupedSummaryDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupedSummaryDemo {
    record Purchase(String region, int units) {}

    public static void main(String[] args) {
        List<Purchase> purchases = List.of(
                new Purchase("North", 2),
                new Purchase("South", 4),
                new Purchase("North", 6)
        );

        Map<String, IntSummaryStatistics> perRegion = purchases.stream()
                .collect(Collectors.groupingBy(
                        Purchase::region,
                        TreeMap::new,
                        Collectors.summarizingInt(Purchase::units)));

        perRegion.forEach((region, summary) ->
                System.out.println(region
                        + ": count=" + summary.getCount()
                        + ", sum=" + summary.getSum()
                        + ", avg=" + summary.getAverage()));
    }
}
~~~

~~~bash
javac --release 17 GroupedSummaryDemo.java
java GroupedSummaryDemo
~~~

Stdout:

~~~text
North: count=2, sum=8, avg=4.0
South: count=1, sum=4, avg=4.0
~~~

`TreeMap::new` sorts keys in natural order, so the order of the two lines `North` and `South` is predictable. The default `groupingBy` overload does not guarantee a specific Map type or iteration order.

Important: if the source is empty, **the resulting Map from `groupingBy` is empty**; the collector does not pre-create groups that did not appear. If a group exists and the downstream receives elements of that group, `IntSummaryStatistics` contains the metrics for that group. If you also need groups with no records, you must add them according to your data contract in a separate step.

You can also swap `summarizingInt(Purchase::units)` for `summarizingLong(Purchase::longValue)` or `summarizingDouble(Purchase::measurement)` when the domain model has an appropriate getter. The value type in the Map will change accordingly.

## 6. Converting the Statistics Object into a Business Value

An output API does not always need all five fields. If you only want the **average per group**, you can use `Collectors.collectingAndThen` to transform `IntSummaryStatistics` into `Double`:

~~~java
// Illustrative snippet inside a method that has List<Purchase> purchases.
Map<String, Double> averageByRegion = purchases.stream()
        .collect(Collectors.groupingBy(
                Purchase::region,
                java.util.TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.summarizingInt(Purchase::units),
                        IntSummaryStatistics::getAverage)));
~~~

Type structure:

~~~text
summarizingInt(Purchase::units)
       → IntSummaryStatistics
collectingAndThen(..., IntSummaryStatistics::getAverage)
       → Double
groupingBy(Purchase::region, ...)
       → Map<String, Double>
~~~

If you only need the average without count/min/max, `Collectors.averagingInt(Purchase::units)` is the dedicated collector, which is usually clearer in intent and produces `Double` directly. If you need the full set of statistics, `summarizingInt` avoids having to recompute each metric individually.

To build reports that need to display nullable min/max values, consider converting the statistics object into an immutable DTO after `collect`, while explicitly representing `count == 0` instead of exposing the sentinel min/max values as real data.

## 7. Comparison with `averagingInt`, `summingInt`, and Primitive `summaryStatistics()`

These APIs are closely related but differ in return type:

| API | Result type | Suitable when |
| --- | --- | --- |
| `collect(summarizingInt(T::value))` | `IntSummaryStatistics` | Need count, sum, min, max, average at once; used as `groupingBy` downstream. |
| `collect(summarizingLong(T::value))` | `LongSummaryStatistics` | Need the summary statistics of a `long` key. |
| `collect(summarizingDouble(T::value))` | `DoubleSummaryStatistics` | Need the summary statistics of a `double` key. |
| `collect(averagingInt(T::value))` | `Double` | Only need the average. |
| `collect(summingInt(T::value))` | `Integer` | Only need an `int` sum (can overflow). |
| `stream.mapToInt(T::value).summaryStatistics()` | `IntSummaryStatistics` | Already working with an `IntStream`. |
| `stream.mapToLong(T::value).summaryStatistics()` | `LongSummaryStatistics` | Already working with a `LongStream`. |
| `stream.mapToDouble(T::value).summaryStatistics()` | `DoubleSummaryStatistics` | Already working with a `DoubleStream`. |

Example:

~~~java
// Illustrative snippet in a context with List<Sale> sales.
IntSummaryStatistics a = sales.stream()
        .collect(Collectors.summarizingInt(Sale::units));

IntSummaryStatistics b = sales.stream()
        .mapToInt(Sale::units)
        .summaryStatistics();
~~~

Both expressions aggregate `units`, but via two different paths:

- `summarizingInt` is a **collector** for `Stream<Sale>`; convenient when passed into `groupingBy`, `mapping`, and the collector composition system.
- `mapToInt(...).summaryStatistics()` converts to an `IntStream` and then calls the **dedicated terminal operation**.

Do not confuse `IntStream.average()` returning `OptionalDouble` with `IntSummaryStatistics.getAverage()` returning `double`. On an empty stream, `OptionalDouble.empty()` is different from `0.0`; therefore, when using the summary object, you must check the count if requirements do not allow implicitly treating empty as an average of 0.

## 8. The Extractor Must Have the Right Type and Handle Null Explicitly

The three `summarizing...` methods accept primitive extractors:

~~~java
// Functional interface method signatures for reference:
int applyAsInt(T element);
long applyAsLong(T element);
double applyAsDouble(T element);
~~~

If a getter returns a boxed `Integer`, `Long`, or `Double` wrapper, Java can **auto-unbox** it to match the extractor. That means **a getter returning null can throw `NullPointerException`**, even though the object holding the field itself exists.

Example:

~~~java
// Illustrative snippet: Product.stock() returns a nullable Integer.
products.stream()
        .collect(Collectors.summarizingInt(Product::stock));
~~~

If a `Product` has a null stock, unboxing can fail. There are three different policies:

1. **Reject missing data**: validate/throw an exception when stock is null.
2. **Skip missing records**: `.filter(p -> p.stock() != null)` before collect. In that case `getCount()` counts **records with stock**, not all products.
3. **Treat missing value as 0**: `p -> p.stock() == null ? 0 : p.stock()`. In that case count still includes missing records, while sum/average are affected by the assumed 0s.

Do not choose a policy merely to avoid an NPE; it must come from business semantics. **Skipping null** is different from **replacing null with 0**, especially when computing the average.

For **null source elements**, a method reference like `Product::stock` is also unsafe. `List.of(...)` does not accept null elements, but `Arrays.asList(...)` or certain streams can still contain them. When possible, define the null policy right at the source rather than letting the getter fail mid-pipeline.

### Full example: skipping missing values vs. replacing with 0 gives different results

File `NullableValueSummaryDemo.java`:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

public class NullableValueSummaryDemo {
    record Item(String code, Integer stock) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 4),
                new Item("B", null),
                new Item("C", 2));

        IntSummaryStatistics skipMissing = items.stream()
                .filter(item -> item.stock() != null)
                .collect(Collectors.summarizingInt(Item::stock));

        IntSummaryStatistics missingAsZero = items.stream()
                .collect(Collectors.summarizingInt(
                        item -> item.stock() == null ? 0 : item.stock()));

        System.out.println("skip count=" + skipMissing.getCount()
                + ", sum=" + skipMissing.getSum()
                + ", avg=" + skipMissing.getAverage());

        System.out.println("zero count=" + missingAsZero.getCount()
                + ", sum=" + missingAsZero.getSum()
                + ", avg=" + missingAsZero.getAverage());
    }
}
~~~

~~~bash
javac --release 17 NullableValueSummaryDemo.java
java NullableValueSummaryDemo
~~~

Stdout:

~~~text
skip count=2, sum=6, avg=3.0
zero count=3, sum=6, avg=2.0
~~~

Both approaches have sum 6, but count and average differ. Therefore, in reports, you should clearly state whether **the denominator of the average** includes missing records or not.

## 9. Characteristics of `DoubleSummaryStatistics`: Precision and Special Values

`double` numbers cannot represent all decimal numbers exactly. For example, `0.1 + 0.2` is usually not exactly equal to `0.3` in double comparison. When collecting floating-point numbers:

- **Sum/average may be rounded**. The JDK uses compensated summation in `DoubleSummaryStatistics` to reduce some error, but it does not turn double into exact decimal arithmetic.
- **Combination order can affect the final result**; a parallel pipeline may split and merge in a different order. Do not impose a "bit-for-bit always identical" requirement for double sums across all execution modes.
- If **`Double.NaN`** is present, `getMin()` and `getMax()` become `NaN`, and the sum/average statistics can also become `NaN`.
- If the sum includes both **`Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY`**, addition can yield `NaN`.
- `-0.0` and `+0.0` follow Java floating-point min/max comparison rules; do not assume they behave identically in every operation.
- **Financial precision:** for money requiring exact sums, use integer minor units when there is no overflow risk, or `BigDecimal` with an appropriate collector/aggregation solution.

If measurement data may contain `NaN` or infinity, explicitly decide whether to **discard, fail on, or allow** those values before `summarizingDouble`. A summary collector does not invent business rules for anomalous measurements.

In addition, **the average here is an unweighted arithmetic mean**. If you want an average weighted by mass, duration, or frequency, you must simultaneously compute `sum(value * weight)` and `sum(weight)` and divide when the total weight is valid; `summarizingDouble(value)` alone does not compute a weighted average.

## 10. Using the Statistics Object and Mutability

`IntSummaryStatistics`, `LongSummaryStatistics`, and `DoubleSummaryStatistics` are **mutable objects**, with methods such as `accept(value)` and `combine(other)`. `Collectors.summarizing...` uses an accumulation/combination mechanism to produce the final result; however, once `stats` is received, a developer can still mutate its state by calling `accept` or `combine`.

Illustrative snippet:

~~~java
IntSummaryStatistics stats = new IntSummaryStatistics();
stats.accept(4);
stats.accept(6);
System.out.println(stats.getSum()); // 10
~~~

Therefore:

- Do not directly return a mutable summary object through an API that requires immutability if callers might modify the metrics.
- If you need to store a fixed snapshot, extract `count`, `sum`, `min`, `max`, and `average` into a record/DTO and clearly define how the empty case is represented.
- Do not share a single statistics object across multiple threads calling `accept` directly without synchronization. Collectors in a parallel pipeline use their own appropriate accumulation/combination mechanism; that does not make an arbitrary summary instance thread-safe.
- Do not use an extractor with side effects or one that reads mutable state changing while the stream is processing; the resulting count/sum/min/max may not reflect a consistent snapshot.

A statistics object returned from a collector can be queried multiple times via its getters without re-running the stream, as long as nothing continues to mutate it.

## 11. Performance, Parallel Streams, and Composite Collectors

The main benefit of summary collectors is **a single accumulation pass** for multiple metrics. Computing count, sum, min, max, and average in the same accumulator is usually more efficient and clearer than running five separate stream pipelines over a source with high read cost.

However:

1. **The extractor can be expensive** (conversions, extracting values from objects). Keep it pure, short, and avoid database/network queries per element whenever possible.
2. **Streaming data still has overhead**; for very small datasets, a simple loop may also be appropriate. There is no guarantee that streams are faster than every other approach.
3. **Parallel streams** may create multiple statistics containers and then `combine` them, so do not rely on the order in which the extractor is called. For double, combination order can affect rounding error.
4. **Do not create multiple streams on the same consumed instance**: if you need statistics for different properties, you must use a new stream from the collection or a collector that aggregates multiple results in one pass.
5. The summary classes operate on primitive values, helping avoid unnecessary boxing during aggregation if the extractor returns a primitive directly.

If an application needs **both** sales volume statistics and total revenue in **a single pass**, Java 12+ provides `Collectors.teeing` to combine two collectors and a finisher function. For groups, `groupingBy(classifier, summarizingInt(...))` is a clear composition and usually the first choice.

## 12. Avoiding Type Mismatches When Combining `map`, `filter`, and Downstream Collectors

Example:

~~~java
// Suppose sales: List<Sale>.
sales.stream()
        .filter(sale -> sale.units() > 0)
        .collect(Collectors.summarizingInt(Sale::units));
~~~

After `filter`, the element type is still `Sale`, so `Sale::units` is valid. However, if you add `.map(Sale::region)` before collect, the stream becomes `Stream<String>`; `Sale::units` **no longer has the right type**.

Another valid usage:

~~~java
// Only want to summarize region name lengths (Stream<String>):
sales.stream()
        .map(Sale::region)
        .collect(Collectors.summarizingInt(String::length));
~~~

At this point `getCount()` counts the number of region strings passing through the pipeline; `getMin()` and `getMax()` are **string lengths**, no longer sales units. When reading a pipeline, always identify the type `T` at the point where the collector is called and what is actually being extracted.

In `groupingBy`, `downstream` receives the elements **after the stream's intermediate operations**, not the Map key returned by the classifier. For example, `groupingBy(Sale::region, summarizingInt(Sale::units))` still feeds each `Sale` into the summary for its corresponding region.

## 13. Common Mistakes

1. **Thinking `summarizingInt` returns only an `int` sum.** In fact it returns `IntSummaryStatistics`; the sum is obtained via `getSum()`, which has type `long`.
2. **Confusing an empty-source result with `Optional.empty()`.** A summary collector returns a statistics object with count 0, sum 0, average 0.0, and sentinel min/max.
3. **Displaying empty-source sentinel min/max as real values.** Always check `getCount() > 0` before reporting min/max as meaningful.
4. **Assuming average is always an integer.** `getAverage()` returns `double`; for example, a sum of 10 over 3 elements gives 3.333...
5. **Not distinguishing `summarizingLong` from `summarizingInt`.** Long accepts `long` and sums into `long`; Int accepts `int` and also stores the sum in `long`.
6. **Assuming a `long` sum never overflows.** `long` is still finite; use a big-number solution or overflow checks when the data domain requires it.
7. **Using `summarizingDouble` to sum money requiring exact precision.** Double has rounding errors; use `BigDecimal` or appropriate minor units.
8. **Not handling `NaN`/infinity.** They affect the meaning of min, max, sum, and average in floating-point statistics.
9. **Using an extractor that returns a nullable wrapper without checking.** Auto-unboxing `null` throws `NullPointerException`.
10. **Filtering out null values while still expecting count to equal the original record count.** Count only counts elements passed into the collector.
11. **Using `groupingBy` and expecting groups with no records to appear.** The Map does not automatically create keys for absent groups.
12. **Relying on the default Map's iteration order.** If you want deterministic key ordering, choose `TreeMap::new` or another contract-compliant rule.
13. **Using the same stream for multiple collect calls.** A terminal operation consumes the stream; create a new stream from the source if needed.
14. **Sharing a mutable statistics object across threads and calling `accept` directly.** It is not thread-safe by default.
15. **Using `summarizingDouble` to compute a weighted average.** This is an ordinary unweighted arithmetic mean.
16. **Believing parallel execution is always faster.** Source, size, combination cost, and numeric type determine actual performance.

## 14. Pre-Application Checklist

- Do you need **all five metrics** or only a specific one such as `sum`/`average`?
- Is the input data type `int`, `long`, or `double`? Is there a risk of overflow or precision error?
- Does the extractor return the right primitive and handle `null` wrappers safely?
- Can the source be empty? If empty, do you check `getCount()` before displaying min/max/average?
- Do you need statistics for **the entire source** or per group with `groupingBy`?
- Can the dataset contain `NaN`, infinity, negative values, or anomalous measurements?
- If running in parallel, is the extractor stateless, non-interfering with the source, and free of side effects?
- Do you need to convert the mutable statistics object into an immutable DTO before sharing it externally?
- Have `filter/map` transformations before the collector changed the type or number of elements being summarized?
- Do tests cover empty data, single element, multiple elements, null values, boundary values, and hard-to-represent floating-point numbers?

**Remember:** `Collectors.summarizingInt/Long/Double(extractor)` lets a `Stream<T>` produce an object containing **count, sum, min, max, and average** based on the numeric values extracted by the extractor. Use `groupingBy(..., summarizing...)` for per-group statistics; check `count == 0` so sentinels on empty sources are not misinterpreted, and choose the right numeric type to avoid overflow or unintended precision errors.
