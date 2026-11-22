# sum(), average(), min(), max(), and summaryStatistics() on Java primitive streams

## 1. Lesson objectives

Java has three **primitive stream** types specialized for primitive numeric data:

- **IntStream** processes `int`.
- **LongStream** processes `long`.
- **DoubleStream** processes `double`.

In the functional programming module, these streams are typically created using `IntStream.of(...)`, `LongStream.range(...)`, `DoubleStream.of(...)`, or converted from `Stream<T>` via `mapToInt`, `mapToLong`, and `mapToDouble`. They avoid having to box each numeric value into **Integer/Long/Double** in the corresponding processing steps.

Important group of methods for **data aggregation**:

| Terminal operation | Purpose | Basic result |
| --- | --- | --- |
| **sum()** | Sums the elements | `int`, `long`, or `double` corresponding to the stream type |
| **average()** | Arithmetic mean | `OptionalDouble` |
| **min()** | Minimum value | `OptionalInt`, `OptionalLong`, `OptionalDouble` |
| **max()** | Maximum value | `OptionalInt`, `OptionalLong`, `OptionalDouble` |
| **summaryStatistics()** | Combines count, sum, min, max, average | `IntSummaryStatistics`, `LongSummaryStatistics`, or `DoubleSummaryStatistics` |

All of them are **terminal operations**: once one of these methods consumes a stream, that stream cannot be reused. This affects how code is written when sum, average, min, and max are needed at the same time.

Example:

~~~java
int total = IntStream.of(2, 4, 6).sum();           // 12
OptionalDouble average = IntStream.of(2, 4, 6).average();
OptionalInt minimum = IntStream.of(2, 4, 6).min();
OptionalInt maximum = IntStream.of(2, 4, 6).max();
~~~

These are illustrative snippets requiring imports for `java.util.stream.IntStream`, `java.util.OptionalDouble`, and `java.util.OptionalInt`. They create **four separate new streams**, without reusing an already-consumed stream.

**Key mindset:** Choose a method based on the result you need to compute and the meaning of empty data; if you need multiple metrics at once, `summaryStatistics()` is usually cleaner than traversing the source repeatedly.

## 2. How are primitive streams created?

### 2.1. Creating directly from values

~~~java
IntStream integers = IntStream.of(3, 6, 9);
LongStream longs = LongStream.of(100L, 200L, 300L);
DoubleStream decimals = DoubleStream.of(1.5, 2.0, 4.5);
~~~

This is an illustrative snippet requiring imports for the three corresponding interfaces from `java.util.stream`. The variables are single-use streams; there is no terminal operation yet, so there is no aggregated result yet.

### 2.2. Generating number sequences with range and rangeClosed

~~~java
IntStream firstFive = IntStream.range(1, 6);       // 1, 2, 3, 4, 5
LongStream inclusive = LongStream.rangeClosed(1, 5); // 1, 2, 3, 4, 5
~~~

- **range(start, endExclusive)** does not include endExclusive.
- **rangeClosed(start, endInclusive)** includes endInclusive if the range is valid.

Using `range(1,6).sum()` gives the sum 1+2+3+4+5 = 15. For a very large sequence, consider numeric limits, performance, and overflow risk before specifying the data type.

### 2.3. Converting from an object stream

For example, a product record:

~~~java
record Item(String name, int quantity, long priceCents) {}
~~~

If you have `List<Item> items`:

~~~java
int totalQuantity = items.stream()
        .mapToInt(Item::quantity)
        .sum();

long totalPrices = items.stream()
        .mapToLong(Item::priceCents)
        .sum();
~~~

This is an illustrative snippet, assuming `items` already exists and the values fit the model. **mapToInt** and **mapToLong** create primitive streams to use aggregation methods, instead of `map(Item::quantity)` creating a Stream<Integer> and then having to reduce/collect.

If the `Integer quantity` or `Long priceCents` property can be **null**, unboxing in `mapToInt`/`mapToLong` can throw a NullPointerException. In that case, you need null checks and a missing-data policy before converting to primitive.

## 3. sum(): returning a number directly and behavior with empty streams

**sum()** returns a primitive value:

~~~java
int intSum = IntStream.of(1, 2, 3).sum();           // 6
long longSum = LongStream.of(10L, 20L, 30L).sum(); // 60
double doubleSum = DoubleStream.of(1.5, 2.5).sum();// 4.0
~~~

This is an illustrative snippet requiring primitive stream imports.

Unlike min/max/average, `sum()` does **not** return an Optional. For an **empty stream**, `sum()` returns **0** of the corresponding type:

~~~java
int noneInt = IntStream.empty().sum();       // 0
long noneLong = LongStream.empty().sum();    // 0L
double noneDouble = DoubleStream.empty().sum(); // 0.0
~~~

**Why is the value 0?** In addition, 0 is the **identity element**. Summing zero elements can be defined as 0, so the API returns a number directly.

Note the distinction:

- **No elements** → `sum()` returns 0.
- **Elements exist but their sum is 0** → `sum()` also returns 0.

If business logic needs to distinguish between these two cases, using only `sum()` is **not enough**. You can use `summaryStatistics()` and check `getCount()`, or design a return result with "no data" semantics.

### 3.1. Overflow with IntStream.sum

`IntStream.sum()` returns an **int**, which can overflow according to int addition. For example:

~~~java
int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
// Result according to int addition: Integer.MIN_VALUE.
~~~

This is an illustrative snippet. Using a primitive stream does not automatically check for overflow. For values that might exceed the int range, you can **widen to long before summing**:

~~~java
long safeIntTotal = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();  // 2147483648L
~~~

Note that long also has a limit, and `LongStream.sum()` can also overflow if it exceeds the long range. For numbers larger than long, consider **BigInteger**; for currency/decimal precision, consider **BigDecimal** or an appropriate minor-units model.

### 3.2. DoubleStream.sum and floating-point precision error

`DoubleStream.sum()` returns a **double**. Floating-point addition is **not strictly associative** due to rounding under IEEE 754 representation; the result can vary slightly when changing grouping, addition order, or parallelization. Calculations can also encounter **NaN**, infinity, or loss of precision when magnitudes differ significantly.

Example:

~~~java
double sum = DoubleStream.of(0.1, 0.2).sum();
~~~

This is an illustrative snippet. Do not force the result under the assumption that "every decimal addition is exact"; `0.1` and `0.2` cannot be represented exactly in binary double.

**Do not use DoubleStream.sum for accounting problems requiring exact decimal numbers** without an error-handling policy. Use BigDecimal with input data and rounding rules matching business requirements.

## 4. average(): always returns OptionalDouble

The arithmetic mean equals **sum / number of elements**. For an empty stream, there is no element count to serve as the denominator, so there is no valid average value.

Therefore:

~~~java
OptionalDouble a = IntStream.of(2, 4, 6).average();
OptionalDouble b = LongStream.of(10L, 20L).average();
OptionalDouble c = DoubleStream.of(1.0, 2.0).average();
~~~

All return **OptionalDouble** (not OptionalInt, OptionalLong, or a direct double). This is an illustrative snippet with the corresponding imports.

- `a.orElse(-1)` gives **4.0**.
- `b.orElse(-1)` gives **15.0**.
- `c.orElse(-1)` gives **1.5**.
- `IntStream.empty().average().isEmpty()` gives **true**.

Why doesn't IntStream return an int? The average of int values can be fractional. For example, 1 and 2 have an average of **1.5**, so using `OptionalDouble` is appropriate.

If business logic requires at least one value, define how absence is handled:

~~~java
double average = scores.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow(() -> new IllegalStateException("No scores"));
~~~

This is an illustrative snippet, assuming scores is a List<Integer> containing no nulls. **orElseThrow** turns absence into an intentional exception. If empty is a valid scenario, `orElse(0.0)` or returning OptionalDouble to the caller may be more appropriate, but it should be made clear that **0.0 when empty is a business fallback**, not the mathematical average of an empty set.

### 4.1. Difference between average and integer sum

With `IntStream`, `average()` computes the average without the author having to perform **int/int** division (which causes integer division). Avoid:

~~~java
int sum = 5;
int count = 2;
double wrong = sum / count; // 2.0, because integer division happens first.
~~~

This is an illustrative snippet; `sum / count` produces int 2, which is then converted to double 2.0. If computing manually, cast to double before dividing:

~~~java
double correct = (double) sum / count; // 2.5
~~~

**average()** expresses intent more clearly, though you still need to handle the empty stream case via OptionalDouble.

### 4.2. Precision error of average on large data

`IntStream.average()` or `LongStream.average()` returns a double: large long values may not be represented accurately down to every least significant unit in double. `DoubleStream.average()` is also subject to floating-point limits, especially when there are very large, very small, or infinite values. If you need an average accurate to a specified decimal place, you may need BigDecimal or a specialized algorithm with a rounding policy.

## 5. min() and max(): Optional per primitive type

Minimum/maximum values **do not exist for an empty stream** without defining an out-of-band sentinel value, so these methods return Optional:

| Stream | min() | max() |
| --- | --- | --- |
| **IntStream** | **OptionalInt** | **OptionalInt** |
| **LongStream** | **OptionalLong** | **OptionalLong** |
| **DoubleStream** | **OptionalDouble** | **OptionalDouble** |

Example:

~~~java
OptionalInt smallest = IntStream.of(9, 3, 7).min();  // contains 3
OptionalLong greatest = LongStream.of(4L, 10L).max(); // contains 10
OptionalDouble maxDouble = DoubleStream.of(1.5, 3.2).max(); // contains 3.2
~~~

This is an illustrative snippet requiring imports for primitive Optionals and primitive streams.

### 5.1. When the stream is empty

~~~java
OptionalInt emptyMin = IntStream.empty().min();
OptionalLong emptyMax = LongStream.empty().max();
OptionalDouble emptyAvg = DoubleStream.empty().average();
~~~

All three Optionals are **empty**. `isPresent()` returns false; `isEmpty()` returns true (the isEmpty method has been available on primitive Optionals since Java 11).

If you call **getAsInt()**, **getAsLong()**, or **getAsDouble()** on an empty Optional, Java throws **NoSuchElementException**. Therefore, use `orElse`, `orElseGet` (if the specific API supports it), `orElseThrow`, or check presence as needed.

Example:

~~~java
int min = IntStream.of(5, 7).min().orElse(-1); // 5
int fallback = IntStream.empty().min().orElse(-1); // -1
~~~

**Be careful with sentinels:** if -1 can also appear in the data, it cannot distinguish "no elements". It is better to keep OptionalInt if the caller needs to know about absence.

### 5.2. Negative numbers and choosing the wrong identity

Do not substitute arbitrarily:

~~~java
int wrongMax = IntStream.of(-7, -3, -9)
        .reduce(0, Integer::max); // 0 (wrong meaning for data max)
~~~

Here 0 **is not an identity for max over the entire int domain**, because max(0, x) is not equal to x when x is negative. If you use **max()**, the correct result is -3, while also getting OptionalInt to handle an empty stream.

**Good approach:** `IntStream.of(-7,-3,-9).max().orElseThrow()` returns -3. Similarly, `min()` avoids inventing a sentinel that does not fit the data domain.

### 5.3. DoubleStream.min/max and NaN

For double floating-point numbers, **NaN** (Not a Number) has special rules. `DoubleStream.min()` and `max()` follow `Math.min`/`Math.max` semantics: if any element is **NaN**, the result of the corresponding reduction is **NaN**. When **-0.0** and **+0.0** are present, min/max comparison also distinguishes the sign of zero according to the rules of these methods.

Do not use `filter(Double::isFinite)` mechanically: dropping NaN/infinity alters the data. Determine whether NaN is invalid data that should be reported, a value to exclude by policy, or part of a computation domain with specific meaning.

## 6. Complete Java 17 example: the five basic aggregations

Create file **PrimitiveAggregatesDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

public class PrimitiveAggregatesDemo {
    public static void main(String[] args) {
        int[] values = {8, 3, 5, 4};

        int sum = IntStream.of(values).sum();
        OptionalDouble average = IntStream.of(values).average();
        OptionalInt min = IntStream.of(values).min();
        OptionalInt max = IntStream.of(values).max();
        IntSummaryStatistics stats =
                IntStream.of(values).summaryStatistics();

        System.out.println("sum=" + sum);
        System.out.println("average=" + average.orElse(-1));
        System.out.println("min=" + min.orElse(-1));
        System.out.println("max=" + max.orElse(-1));

        System.out.println("count=" + stats.getCount());
        System.out.println("stats sum=" + stats.getSum());
        System.out.println("stats min=" + stats.getMin());
        System.out.println("stats max=" + stats.getMax());
        System.out.println("stats average=" + stats.getAverage());

        System.out.println("empty sum=" + IntStream.empty().sum());
        System.out.println("empty average present="
                + IntStream.empty().average().isPresent());
        System.out.println("empty min present="
                + IntStream.empty().min().isPresent());
    }
}
~~~

Compile/run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 PrimitiveAggregatesDemo.java
java PrimitiveAggregatesDemo
~~~

Stdout:

~~~text
sum=20
average=5.0
min=3
max=8
count=4
stats sum=20
stats min=3
stats max=8
stats average=5.0
empty sum=0
empty average present=false
empty min present=false
~~~

**Result explanation:**

1. The four numbers **8,3,5,4** have sum **20** and average **20/4 = 5.0**.
2. Minimum value is **3**, maximum is **8**.
3. `IntSummaryStatistics` provides all four metrics plus **count=4** after a single stream pass performed by summaryStatistics.
4. `IntStream.empty().sum()` returns 0; `average()` and `min()` return empty Optionals.
5. The individual computations at the beginning use **new streams** created from `int[] values`; a Stream is never reused after a terminal operation.

**Note:** The example demonstrates aggregation on the same small array. In a pipeline with I/O, expensive filtering, or a single-pass source, creating four independent streams to compute four metrics may be infeasible or inefficient. `summaryStatistics()` avoids traversing the source repeatedly.

## 7. summaryStatistics(): a single pass for multiple metrics

The corresponding methods:

~~~java
IntSummaryStatistics ints = IntStream.of(1, 3, 5).summaryStatistics();
LongSummaryStatistics longs = LongStream.of(10, 20).summaryStatistics();
DoubleSummaryStatistics doubles = DoubleStream.of(1.0, 2.5).summaryStatistics();
~~~

This is an illustrative snippet requiring imports for **java.util.IntSummaryStatistics**, **LongSummaryStatistics**, **DoubleSummaryStatistics**, and the primitive streams.

Each statistics object provides these getters:

- **getCount()** → number of elements received, type **long**.
- **getSum()** → sum, type depends on the statistics class.
- **getMin()** → min, corresponding primitive type.
- **getMax()** → max, corresponding primitive type.
- **getAverage()** → average, type **double**.

| Getter | IntSummaryStatistics | LongSummaryStatistics | DoubleSummaryStatistics |
| --- | --- | --- | --- |
| getCount() | long | long | long |
| getSum() | **long** | long | double |
| getMin() | int | long | double |
| getMax() | int | long | double |
| getAverage() | double | double | double |

**Important pitfall:** `IntStream.sum()` returns **int**, whereas **IntSummaryStatistics.getSum() returns long**. Therefore, `IntSummaryStatistics` can hold a sum larger than the int range in cases where `IntStream.sum()` would overflow int. However, **long still has a limit**, and `LongSummaryStatistics.getSum()` can still overflow long.

### 7.1. Purpose of the statistics object

In an example processing exam scores:

~~~java
IntSummaryStatistics stats = scores.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();
~~~

This is an illustrative snippet assuming scores is a non-null List<Integer>. Instead of:

~~~java
long count = scores.size();
int sum = scores.stream().mapToInt(Integer::intValue).sum();
int min = scores.stream().mapToInt(Integer::intValue).min()
        .orElseThrow();
int max = scores.stream().mapToInt(Integer::intValue).max()
        .orElseThrow();
double average = scores.stream().mapToInt(Integer::intValue).average()
        .orElseThrow();
~~~

we can obtain all metrics from a single statistics result. The second snippet traverses the stream multiple times and uses `orElseThrow()`, so it does not handle an empty list with a fallback. Do not assume the two snippets have identical semantics in every way: `IntSummaryStatistics.getSum()` is long, and the min/max getters have special values when empty.

### 7.2. When the stream is empty, the statistics object still exists

Unlike `min()`/`average()`, `summaryStatistics()` returns a statistics object **even when the stream is empty**. Initial state of the objects:

| Statistics of an empty source | count | sum | min | max | average |
| --- | ---: | ---: | --- | --- | ---: |
| IntSummaryStatistics | 0 | 0L | Integer.MAX_VALUE | Integer.MIN_VALUE | 0.0 |
| LongSummaryStatistics | 0 | 0L | Long.MAX_VALUE | Long.MIN_VALUE | 0.0 |
| DoubleSummaryStatistics | 0 | 0.0 | Double.POSITIVE_INFINITY | Double.NEGATIVE_INFINITY | 0.0 |

**These are initial/sentinel values**, not "the true min/max of an empty set". Therefore, always **check getCount() > 0** before presenting min/max/average as statistical results of the dataset.

~~~java
IntSummaryStatistics stats = IntStream.empty().summaryStatistics();
if (stats.getCount() == 0L) {
    System.out.println("No data");
} else {
    System.out.println(stats.getMin());
}
~~~

This is an illustrative snippet, importing IntSummaryStatistics and IntStream. With empty input, the program prints **No data**.

**API distinction:**

- **`stream.min()`** returns an empty Optional when there are no elements.
- **`stream.summaryStatistics().getMin()`** returns a sentinel when there are no elements.
- **`stats.getCount()`** is how you check whether the min/max getters are meaningful on actual data.

### 7.3. DoubleSummaryStatistics and non-finite numbers

With DoubleSummaryStatistics, if there is a **NaN** element, min/max and sum/average can become NaN according to the arithmetic rules. If there is positive or negative infinity, addition and average can produce Infinity or NaN depending on the sequence.

Do not present every getSum/getAverage value of DoubleSummaryStatistics as exact currency; they still carry floating-point semantics. For non-finite data, define the policy up front: exclude, report an error, or accept according to the data domain.

## 8. Complete Java 17 example: score statistics on a dataset

Create file **SummaryStatisticsDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;

record Exam(String student, int score) {}

public class SummaryStatisticsDemo {
    public static void main(String[] args) {
        List<Exam> exams = List.of(
                new Exam("An", 75),
                new Exam("Bình", 92),
                new Exam("Chi", 83),
                new Exam("Dung", 90)
        );

        IntSummaryStatistics stats = exams.stream()
                .mapToInt(Exam::score)
                .summaryStatistics();

        System.out.println("Count: " + stats.getCount());
        System.out.println("Sum: " + stats.getSum());
        System.out.println("Min: " + stats.getMin());
        System.out.println("Max: " + stats.getMax());
        System.out.println("Average: " + stats.getAverage());

        List<Exam> empty = List.of();
        IntSummaryStatistics noScores = empty.stream()
                .mapToInt(Exam::score)
                .summaryStatistics();

        System.out.println("Has scores: "
                + (noScores.getCount() > 0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SummaryStatisticsDemo.java
java SummaryStatisticsDemo
~~~

Stdout:

~~~text
Count: 4
Sum: 340
Min: 75
Max: 92
Average: 85.0
Has scores: false
~~~

**Explanation:**

- Scores **75 + 92 + 83 + 90 = 340**, divided by 4 gives **85.0**.
- Min **75**, max **92**, count **4**.
- For an empty list, **summaryStatistics()** still returns an IntSummaryStatistics; count is 0 so **Has scores: false**.
- If a `List<Exam>` has a **null element**, `Exam::score` will cause an NPE; validate the source or filter with `Objects::nonNull` when policy allows skipping.
- If scores must be in the range 0..100, separate **validation** is needed. Statistics only aggregates numbers; it does not validate data against business rules.

### 8.1. How should a result with count = 0 be represented?

Instead of displaying `Min: 2147483647` or `Max: -2147483648` for an empty set, show a "no data yet" message. In an API, you can return a **record with count and Optionals** or translate the empty state into an appropriate business result. Do not confuse internal sentinels with measured values.

## 9. IntSummaryStatistics has getSum of type long: int-limit overflow example

Create file **IntSumWidthDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

public class IntSumWidthDemo {
    public static void main(String[] args) {
        int[] values = {Integer.MAX_VALUE, 1};

        int intSum = IntStream.of(values).sum();
        long statsSum = IntStream.of(values)
                .summaryStatistics().getSum();
        long widenedSum = IntStream.of(values)
                .asLongStream().sum();

        System.out.println("int sum: " + intSum);
        System.out.println("statistics sum: " + statsSum);
        System.out.println("long sum: " + widenedSum);
    }
}
~~~

Run:

~~~bash
javac IntSumWidthDemo.java
java IntSumWidthDemo
~~~

Stdout:

~~~text
int sum: -2147483648
statistics sum: 2147483648
long sum: 2147483648
~~~

**Why are the three lines different?**

1. **IntStream.sum** returns int, so `Integer.MAX_VALUE + 1` exceeds 32-bit signed and wraps around to `Integer.MIN_VALUE`.
2. **IntSummaryStatistics.getSum** has type long, so it holds 2147483648.
3. **IntStream.asLongStream().sum()** converts int elements to long before summing, also holding 2147483648.
4. This example only illustrates **numeric type width**. For values exceeding long, neither approach using long is safe enough.

**Do not assume `Math.addExact` is used internally** and expect the sum API to throw an exception on overflow. To control overflow, design checked addition—for example, reduce with `Math::addExact` for an appropriate domain—or use a sufficiently wide numeric type.

## 10. LongStream and DoubleStream: same API, different data domains

### 10.1. LongStream

~~~java
LongSummaryStatistics stats = LongStream.of(
        100_000_000_000L,
        200_000_000_000L,
        300_000_000_000L
).summaryStatistics();
~~~

This is an illustrative snippet requiring imports for LongSummaryStatistics and LongStream. `getCount()` = 3, `getSum()` = 600000000000L, `getMin()` = 100000000000L, `getMax()` = 300000000000L, `getAverage()` = 200000000000.0 in this value range.

**Note:** Both `LongStream.sum()` and `LongSummaryStatistics.getSum()` return **long**; they do not automatically promote to BigInteger. If the numbers exceed the allowable sum of long, overflow can occur.

### 10.2. DoubleStream

~~~java
DoubleSummaryStatistics stats = DoubleStream.of(
        1.5, 2.5, 4.0
).summaryStatistics();
~~~

This is an illustrative snippet requiring imports for DoubleSummaryStatistics and DoubleStream. Results for these values: count = 3, sum = 8.0, min = 1.5, max = 4.0, average is approximately 8.0/3 = 2.6666666666666665.

With double, **not every decimal value is represented exactly**. If the system requires exact equality down to the smallest currency unit, use an appropriate data type and rounding policy rather than simply switching to DoubleStream.

### 10.3. NaN and infinity

DoubleStream's min/max operations follow double comparison rules; sum and average can be heavily affected by NaN/infinity. To check the data:

~~~java
long invalid = DoubleStream.of(
        1.0, Double.NaN, Double.POSITIVE_INFINITY, 2.0)
        .filter(x -> !Double.isFinite(x))
        .count(); // 2
~~~

This is an illustrative snippet importing DoubleStream. **Double.isFinite(x)** returns false for NaN and infinity, so `invalid` = 2.

Choosing to filter out or report an error must be based on business meaning. Silently filtering out non-finite values and then computing an average can turn a corrupted dataset into a normal-looking statistic.

## 11. Can the same stream be used for sum and average?

**No.** A stream is consumed only once. The following snippet compiles but throws **IllegalStateException** at runtime:

~~~java
IntStream stream = IntStream.of(1, 2, 3);
int sum = stream.sum();
OptionalDouble average = stream.average(); // Stream has already been consumed.
~~~

This is an **intentionally failing snippet**, illustrating the stream-reuse error. After a terminal operation such as sum(), a stream cannot be consumed again.

There are three options:

1. **Create a new stream from a re-traversable source:** `IntStream.of(values).sum()` and `IntStream.of(values).average()`.
2. **Use `summaryStatistics()` once** if you need multiple metrics over the same dataset.
3. **Use `Supplier<IntStream>` to create a new stream** when multiple passes are needed and the source allows it, but do not assume I/O sources, network streams, cursors, or infinite streams support re-reading automatically.

Example of a recreating source:

~~~java
Supplier<IntStream> source = () -> IntStream.of(1, 2, 3);
int total = source.get().sum();
double mean = source.get().average().orElseThrow();
~~~

This is an illustrative snippet importing Supplier and IntStream. Two calls to `get()` return two separate new streams; with an immutable source giving consistent results, sum is 6 and average is 2.0. If the source reads data that changes over time, the two computations are not guaranteed to be based on the same dataset.

## 12. summaryStatistics and parallelism

Primitive streams can use **parallel()**, and `summaryStatistics()` supports combining partial statistics to produce the total result. Example:

~~~java
IntSummaryStatistics stats = IntStream.rangeClosed(1, 1000)
        .parallel()
        .summaryStatistics();
~~~

This is an illustrative snippet requiring imports for IntSummaryStatistics and IntStream. For data 1..1000, count is 1000, sum is 500500, min is 1, max is 1000, average is 500.5. The aggregation property allows splitting and combining multiple groups.

**Things to be careful about:**

- For **int/long**, the sum has domain limits; parallel does not fix overflow bugs.
- For **double**, changing the combination order can cause differences in some result bits.
- Do not use side effects in mapper/filter to count invocations when running in parallel.
- For small datasets, parallel has overhead and is not necessarily faster than sequential.
- Data-fetching operations must adhere to Stream's **non-interference** and **statelessness** contracts to produce reliable results.

**An advantage of summaryStatistics:** instead of running sum, average, min, and max on four independent streams and assembling them manually, a single terminal operation aggregates the metrics into one object. This is especially useful when the source is a complex filter/map pipeline.

## 13. Risks when aggregating business data

### 13.1. Monetary values and numeric types

For monetary systems, choose types according to **storage unit, value range, and rounding rules**. `int` risks overflow if quantities/unit prices are large. `long` has a wider range but is not infinite. `double` has binary representation error and is not inherently suitable for exact payments.

For example, `mapToLong(Order::amountInCents).sum()` can be valid if all data is represented in the smallest unit, the sum stays within long limits, and the business domain permits it. If many decimal places or extremely large sums are needed, use **BigDecimal** or **BigInteger** according to contract.

### 13.2. Missing or invalid data

`mapToInt(Employee::age)` invokes the accessor on Employee, so a null element can cause an NPE. If the accessor returns a **nullable Integer**, unboxing can also cause an NPE. `summaryStatistics()` has no mechanism to auto-correct missing data.

A pipeline can filter valid data:

~~~java
IntSummaryStatistics ages = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::age)
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .summaryStatistics();
~~~

This is an illustrative snippet, assuming `Employee.age()` returns Integer and importing Objects and IntSummaryStatistics. It **skips** null Employees or null ages. If those are required records that must report an error, do not silently filter: validate and report invalid results according to contract.

### 13.3. Taking the average of group averages

Suppose group A has 2 values with an average of 10; group B has 8 values with an average of 20. The average of the two averages is 15, whereas the overall average of the 10 values must be:

~~~text
(2 * 10 + 8 * 20) / (2 + 8) = 18
~~~

Therefore, when aggregating reports from multiple groups, keep **count and sum**, or combine the appropriate statistics, rather than just averaging `getAverage()` across groups.

`IntSummaryStatistics.combine(other)`, `LongSummaryStatistics.combine(other)`, and `DoubleSummaryStatistics.combine(other)` allow merging compatible statistics, but the caller must ensure no duplicate counting and no mixing of different domains/units. Statistics objects are **mutable accumulators** and should not be treated as immutable snapshots to share arbitrarily across threads.

## 14. Combining multiple sources with summaryStatistics

For already-grouped data, two statistics objects can be combined:

~~~java
IntSummaryStatistics groupA = IntStream.of(10, 20)
        .summaryStatistics();
IntSummaryStatistics groupB = IntStream.of(30, 40, 50)
        .summaryStatistics();

groupA.combine(groupB);

System.out.println(groupA.getCount());   // 5
System.out.println(groupA.getSum());     // 150
System.out.println(groupA.getAverage()); // 30.0
~~~

This is an illustrative snippet requiring imports for IntStream and IntSummaryStatistics. `combine` updates **groupA** in place by adding the statistics from **groupB**; it does not return a new object. `groupB` remains as its own group's statistics in the example.

**Do not write `IntSummaryStatistics combined = groupA.combine(groupB);`** because `combine` returns void. If you need to preserve the original groupA, create a separate accumulator and `combine` both sources into it, or compute directly on the merged stream.

When merging statistics in a parallel stream, the JDK also uses the corresponding partial-statistics combination mechanism. For double data, combination order can affect the final error; for large datasets with high variance, evaluate precision requirements.

## 15. Differences between summaryStatistics and Collectors.summarizing*

For an object `Stream<T>`, Java provides a group of collectors:

- **Collectors.summarizingInt(ToIntFunction<T>)**
- **Collectors.summarizingLong(ToLongFunction<T>)**
- **Collectors.summarizingDouble(ToDoubleFunction<T>)**

Example from `List<Order>`:

~~~java
IntSummaryStatistics stats = orders.stream()
        .collect(Collectors.summarizingInt(Order::quantity));
~~~

This is an illustrative snippet, assuming Order.quantity returns int, orders already exists, and Collectors and IntSummaryStatistics are imported. It yields a similar statistics result type to:

~~~java
IntSummaryStatistics stats = orders.stream()
        .mapToInt(Order::quantity)
        .summaryStatistics();
~~~

Both aggregate count/sum/min/max/average. The difference lies in the Stream type and how the API composes with collectors, such as inside `groupingBy(..., summarizingInt(...))` to compute statistics **by group**.

There is no mandatory rule to use a collector in all cases. With an existing primitive stream, direct `summaryStatistics()` is usually easier to read. When you need statistics for multiple groups by key, collectors can help reduce data-organization boilerplate.

## 16. Common mistakes

| Mistake or misconception | Consequence | Correct approach |
| --- | --- | --- |
| Thinking `average()` returns double | Wrong type, ignores empty case | Remember `OptionalDouble`, handle empty |
| Thinking `min/max` return a primitive directly | Fails to handle empty stream | Use OptionalInt/Long/Double |
| Calling `getAsInt()` on an empty OptionalInt | NoSuchElementException | Use orElse/check/isPresent/orElseThrow |
| Calling `sum()` then `average()` on the same stream | IllegalStateException | Create a new stream or use summaryStatistics |
| Thinking every `sum()` auto-promotes to long | IntStream.sum returns int, can overflow | Use asLongStream or statistics/getSum or another numeric type |
| Thinking IntSummaryStatistics.getSum returns int | Can break type contracts | IntSummaryStatistics.getSum is long |
| Reading min/max of summaryStatistics when count=0 | Receives sentinel, causes wrong reports | Check getCount() > 0 |
| Treating average 0.0 when empty as mathematical mean | Hides missing data | Handle count=0 or use OptionalDouble |
| Using double for exact currency | Floating-point precision error | Choose BigDecimal/minor units per domain |
| Averaging averages while forgetting weights | Wrong aggregated result | Merge count/sum or combine statistics |
| Null data entering mapToInt/mapToLong | NPE on dereference/unboxing | Validate null or handle per policy |
| Using parallel and expecting bit-identical double results | Addition order can differ | Define tolerance/choose appropriate algorithm |
| Using statistics count as total source count and assuming equality | filter may have dropped elements | Understand count is elements reaching the statistics step |

## 17. Practice exercises

### Exercise 1: Predict the results

Given `IntStream.of(4, 8, 12)`, compute by hand `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()`. State the return type of each API.

**Hint:** sum=24, average=8.0, min=4, max=12, count=3.

### Exercise 2: Check empty streams

Use `IntStream.empty()`, `LongStream.empty()`, `DoubleStream.empty()` and check `sum()`, `average()`, `min()`, `max()`, `summaryStatistics().getCount()`. Explain why min/max on statistics should not be used directly when count=0.

### Exercise 3: Observe overflow

Compute the sum of `Integer.MAX_VALUE` and `1` using `IntStream.sum()`, `asLongStream().sum()`, and `IntSummaryStatistics.getSum()`. Why do the results differ? In what situation can it still exceed long?

### Exercise 4: Transform from an object list

Given a List<Product> with property `long priceCents`, write a method using `mapToLong(Product::priceCents).summaryStatistics()`. Return a report of count, sum, min, max, average; handle an empty List without showing fake sentinels.

### Exercise 5: Weighted average

Group one has 3 scores with average 7; group two has 12 scores with average 9. Compute the overall average using count/sum instead of averaging the two numbers 7 and 9. Create two appropriate IntSummaryStatistics objects and use combine.

### Exercise 6: Floating-point and invalid data

Try `DoubleStream.of(0.1, 0.2, 0.3).sum()` and explain why you should not compare it directly with decimal values under an exact-equality mindset. Try adding NaN and Infinity, then define the input policy needed when reporting metrics.

### Exercise 7: Compute multiple metrics in a single pass

Suppose a Stream comes from an expensive filtering operation. Compare recreating the source four times to call sum/average/min/max with creating one IntSummaryStatistics in a single terminal operation. Describe a scenario where a source cannot be re-traversed, and why recreating the source might change the data.

## 18. Checklist before using aggregates on primitive streams

1. **Which numeric type matches the data domain?** int/long/double have different limits.
2. **Can it be empty?** For min/max/average use Optional; for statistics check count.
3. **Do you need multiple statistics on the same dataset?** Consider summaryStatistics to reduce passes.
4. **Are you reusing a consumed stream?** Each terminal operation closes that consumption pass.
5. **Is there an overflow risk?** Do not let sum fail silently.
6. **Is high decimal precision required?** Double has representation and rounding errors.
7. **Does the data contain null or invalid values?** Guard dereference/unboxing and validation.
8. **Is there filtering before statistics?** Count/sum/min/max only reflect elements passing through the pipeline.
9. **Is it parallelized?** Be careful with floating-point, side effects, and ordering.
10. **Do you need grouped results?** Consider Collectors.summarizingInt/Long/Double with groupingBy.
11. **Are you combining metrics from multiple groups?** Merge count/sum or combine properly; avoid unweighted averages of averages.
12. **Have you tested domain boundaries and empty sets?** These are the two most common sources of bugs in aggregate reports.

## 19. Takeaways

**sum()** returns a primitive number and returns 0 for an empty stream. **average()** returns OptionalDouble; **min()/max()** return OptionalInt/OptionalLong/OptionalDouble matching the stream type, all empty if there are no elements. **summaryStatistics()** returns a statistics object providing count, sum, min, max, and average in a single terminal operation.

For statistics on an empty set, **getCount()==0** is the reliable signal; min/max are **sentinels** rather than data values. **IntSummaryStatistics.getSum() is long**, unlike **IntStream.sum() which is int**; LongStream and DoubleStream also have arithmetic limits that must be understood.

Choose the right tool by asking: **"Do I need a single result or a full set of metrics, can the source be empty, and does the numeric type preserve accurate results within the business domain?"** Answering those three points will help you write primitive stream aggregations that are correct, clear, and easy to test.