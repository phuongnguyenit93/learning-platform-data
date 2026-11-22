# `int[]`, `long[]`, `double[]` and Specialized Streams in Java

## 1. Numeric Arrays Are Data Sources, Streams Are Processing Pipelines

Java has three primitive array types commonly used for numeric aggregation: `int[]`, `long[]`, and `double[]`. Arrays store elements by **index** and allow element mutation; a stream represents **a single traversal pass and chain of operations** over a data source. Creating a stream does not automatically copy the entire array.

```java
int[] counts = {3, 1, 4, 1, 5};
long[] bytes = {3_000_000_000L, 4_000_000_000L};
double[] temperatures = {19.5, 20.0, 21.5};
```

Each primitive element has a width of 32 bits (`int`), 64 bits (`long`), or 64-bit binary floating point (`double`). Arrays have `length` and support access via `counts[0]`. Streams do not automatically provide indices, are **single-use**, and only execute their intermediate pipeline when a terminal operation such as `sum()`, `average()`, or `toArray()` is invoked.

**The focus of this lesson** is choosing the right array source, array slice, and type-conversion point. The next lesson dives deeper into primitive streams versus `Stream<Integer/Long/Double>`, boxing, and collectors.

## 2. Creating the Right Stream from the Three Array Types

| Input array | Factory | Stream type | Traversed elements |
| --- | --- | --- | --- |
| `int[]` | `Arrays.stream(array)` | `IntStream` | each `int` value |
| `long[]` | `Arrays.stream(array)` | `LongStream` | each `long` value |
| `double[]` | `Arrays.stream(array)` | `DoubleStream` | each `double` value |

```java
int intSum = java.util.Arrays.stream(new int[] {1, 2, 3}).sum(); // 6
long longSum = java.util.Arrays.stream(new long[] {3_000_000_000L, 4_000_000_000L}).sum(); // 7000000000
double doubleMean = java.util.Arrays.stream(new double[] {2.0, 4.0})
        .average().orElseThrow(); // 3.0
```

**The `Stream.of(array)` trap**: for a primitive array, `Stream.of(new int[] {1, 2, 3})` has type `Stream<int[]>` and **a single element which is the entire array**. `Arrays.stream(new int[] {1, 2, 3})` has type `IntStream` with **three numeric elements**. `Arrays.asList(intArray)` also keeps the primitive array as a single list element instead of creating three `Integer` objects.

### A Contiguous Slice of an Array

`Arrays.stream(array, fromInclusive, toExclusive)` reads only the index range `[fromInclusive, toExclusive)`. For `int[] a = {10,20,30,40,50}`, `Arrays.stream(a,1,4).sum()` equals `20+30+40 = 90`. `fromInclusive > toExclusive` throws `IllegalArgumentException`; out-of-bounds indices can throw `ArrayIndexOutOfBoundsException`. All three array types have slice overloads.

## 3. When Calculations Need Indices

`Arrays.stream(array)` gives the **value** of each element; it does not automatically provide the position in the array. If you need to select positions, process two arrays in parallel by index, or look up metadata at a position, generate an index sequence with `IntStream.range(0, array.length)`.

```java
int[] scores = {7, 9, 4, 10};
int[] highIndices = java.util.stream.IntStream.range(0, scores.length)
        .filter(i -> scores[i] >= 9)
        .toArray(); // {1, 3}
```

`range(start, end)` excludes the upper bound. If processing two arrays `prices[]` and `quantities[]`, you must check that their lengths match before using the same index. When inputs are not guaranteed to have the same number of elements, do not skip the check and expect the stream to infer the relationship between the two arrays.

```java
int[] prices = {100, 200, 300};
int[] quantities = {2, 3, 1};
if (prices.length != quantities.length) {
    throw new IllegalArgumentException("Array lengths differ");
}
long revenue = java.util.stream.IntStream.range(0, prices.length)
        .mapToLong(i -> (long) prices[i] * quantities[i])
        .sum(); // 1100
```

The `(long) prices[i]` cast is placed **before the multiplication** so the multiplication runs in `long`. If you write `(long) (prices[i] * quantities[i])`, the `int` multiplication may already overflow before being cast. Of course, the sum of multiple products must also fit in `long` if using `.sum()` that way.

## 4. Type Conversion Before Operations Can Lose Data

Passing an `int[]` through `Arrays.stream(...).sum()` produces an `int` sum, which can overflow. When the mathematical sum of an `int[]` may exceed the `int` range, widen each element to `long` **before adding**:

```java
int[] values = {2_000_000_000, 2_000_000_000};
int wrapped = java.util.Arrays.stream(values).sum(); // -294967296
long widened = java.util.Arrays.stream(values).asLongStream().sum(); // 4000000000
```

For a realistic `int[]` array (both length and elements within Java limits), the mathematical sum still fits in `long`; however, the sum of a `long[]` or an unbounded stream / aggregation across many batches can exceed `long`. When an integer sum exceeding `long` is needed, use `BigInteger`. The lesson on **sums that can overflow for integers** distinguishes step-by-step overflow detection from final sum bound checks in detail.

Converting large `long` integers to `double` also carries risk: `double` only preserves every consecutive integer up to `2^53`. Do not pass large ID/count data through `DoubleStream` just to call `average()` when unit-level precision is required.

## 5. Terminal Operations and the Meaning of Empty Data

| Terminal operation | `IntStream` | When empty |
| --- | --- | --- |
| `sum()` | `int` | `0` |
| `count()` | `long` | `0` |
| `average()` | `OptionalDouble` | `OptionalDouble.empty()` |
| `min()` / `max()` | `OptionalInt` | `OptionalInt.empty()` |
| `summaryStatistics()` | `IntSummaryStatistics` | `getCount()==0`, extrema are sentinels |
| `toArray()` | `int[]` | empty array |

For `LongStream` and `DoubleStream`, the corresponding operations return the appropriate `long`/`double` or `OptionalLong`/`OptionalDouble`. `sum()` of an empty sequence equals 0 by reduction convention; **the average or extremum of an empty sequence has no numeric value**. Therefore `average().orElse(0.0)` should only be used if the domain explicitly defines 0 as the default.

`summaryStatistics()` provides count/sum/min/max/average in **a single stream consumption pass**, which is useful when the source is not easy to traverse multiple times. Note that `IntSummaryStatistics.getSum()` returns `long`; with `LongSummaryStatistics` the sum field remains `long`. When `getCount() == 0`, do not interpret `getMin()` or `getMax()` as actual measurements. These boundaries are covered thoroughly in the lessons on average, min/max, and SummaryStatistics.

## 6. Standalone Example on Java 17+

Create `NumericArraysDemo.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class NumericArraysDemo {
    public static void main(String[] args) {
        int[] counts = {3, 1, 4, 1, 5};
        long[] distances = {3_000_000_000L, 4_000_000_000L};
        double[] temperatures = {19.5, 20.0, 21.5};

        System.out.println("array sum=" + Arrays.stream(counts).sum());
        System.out.println("long sum=" + Arrays.stream(distances).sum());
        System.out.println("double mean="
                + Arrays.stream(temperatures).average().orElseThrow());
        System.out.println("array as one=" + Stream.of(counts).count());
        System.out.println("primitive elements=" + Arrays.stream(counts).count());

        int[] indices = IntStream.range(0, counts.length)
                .filter(i -> counts[i] >= 4)
                .toArray();
        System.out.println("high indices=" + Arrays.toString(indices));

        int[] big = {2_000_000_000, 2_000_000_000};
        System.out.println("wrapped sum=" + Arrays.stream(big).sum());
        System.out.println("widened sum=" + Arrays.stream(big).asLongStream().sum());

        IntSummaryStatistics stats = Arrays.stream(counts).summaryStatistics();
        System.out.println("stats=" + stats.getCount() + "/"
                + stats.getSum() + "/" + stats.getMin() + "/"
                + stats.getMax() + "/" + stats.getAverage());
        OptionalDouble empty = Arrays.stream(new int[0]).average();
        System.out.println("empty average present=" + empty.isPresent());
    }
}
```

```bash
javac --release 17 NumericArraysDemo.java
java NumericArraysDemo
```

```text
array sum=14
long sum=7000000000
double mean=20.333333333333332
array as one=1
primitive elements=5
high indices=[2, 4]
wrapped sum=-294967296
widened sum=4000000000
stats=5/14/1/5/2.8
empty average present=false
```

To verify a result, split the question into **which array is the source**, **whether the pipeline processes values or indices**, **the computation type at each operation**, and **the empty-source case**. `DoubleStream.average()` may round according to binary64; do not confuse printed output digits with decimal exactness.

## 7. Choosing a Traversal Approach by Problem

- **Arrays and loops:** convenient when you need to modify elements in place, access indices, or manage state in explicit order.
- **Primitive streams:** convenient when you need a filter/transform/aggregate chain without boxing every element.
- **Index-based `IntStream.range`:** convenient when you need positions or correlation across multiple arrays; you must validate sizes and avoid mutating the source from lambdas.
- **`summaryStatistics()`:** convenient when you need multiple statistics in a single consumption pass; you must check the sample count and arithmetic bounds.

In parallel pipelines, do not mutate shared arrays or accumulator variables and do not expect `parallel()` to speed up small arrays automatically. For `double` sums, grouping can change the lowest bits; when decimal exactness is required, use an appropriate data type and rounding policy.

## 8. Self-Check Questions

1. Why do `Stream.of(new int[] {1,2,3}).count()` and `Arrays.stream(new int[] {1,2,3}).count()` differ?
2. How do you obtain the indices of even elements without confusing indices with values?
3. In a total revenue calculation `price * quantity`, where must the cast be placed so the multiplication executes in `long`?
4. Why does `long total = Arrays.stream(intArray).sum()` fail to fix an `int` sum that has already overflowed?
5. When `average()` is empty, what factor should decide between keeping an Optional, throwing an error, or displaying zero?
6. When you need min/max/count on a source traversed only once, which API should you use and what condition must you guard against?

**Remember:** The array type determines the primitive stream type; using a stream is just a single pass over the source. For numeric aggregation problems, correctness requires **explicitly choosing the source, indices, computation type, and empty-source policy** before optimizing the pipeline.