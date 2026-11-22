# Building Histograms and Value Bucketing

In practical data processing, a raw list of numbers rarely gives a clear big-picture view. Given thousands of API response times, exam scores, order sizes, or sensor readings, instead of inspecting individual numbers we want to know **how many elements fall into each interval**. That is the idea behind **histograms** (frequency distributions) and **bucketing/binning**.

This lesson belongs to the **Practical Data Processing Patterns** chapter of the `JAVA_STREAM_API` module. We will design boundary-accurate buckets, choose between `groupingBy`/`counting` and primitive accumulators, handle negative values, out-of-range points, variable-width intervals, special `double` values, and empty buckets, while weighing performance, memory, parallelism, and I/O sources. Pipelines rely on declarative `filter`, `map`, and `collect`; for multi-metric summaries we also compare against `reduce` and `summaryStatistics`.

> Main Java examples use APIs available since **Java 8**. Each snippet is self-contained or uses variables/helpers introduced earlier. Choosing bucket bounds and invalid-value policies is a **business decision**, not a Java Stream API default.

## 1. How Does a Histogram Differ from a List or Plain Grouping?

Suppose we have exam scores:

```text
0, 9, 10, 18, 20, 45, 57, 60, 76, 88, 99, 100, -5, 120
```

Calling `average()` yields one mean value without showing where scores cluster. Calling `distinct()` reveals unique scores without frequencies per band. A histogram answers a different question:

> In each band 0–9, 10–19, ..., 90–100, **how many valid scores** fall inside?

Example frequency table:

| Score Band | Count |
| --- | ---: |
| 0–9 | 2 |
| 10–19 | 2 |
| 20–29 | 1 |
| 30–39 | 0 |
| 40–49 | 1 |
| 50–59 | 1 |
| 60–69 | 1 |
| 70–79 | 1 |
| 80–89 | 1 |
| 90–100 | 2 |

The total number of scores within `0..100` is **12**. Values `-5` and `120` lie outside the domain and require an explicit policy: discard, count separately, or treat as data errors. Never silently fold them into a valid bucket if the report must isolate measurement errors.

A histogram consists of three parts:

1. **Bucketing rule:** maps each value to a bucket key.
2. **Counter:** increments by 1 for the corresponding bucket.
3. **Presentation:** bucket labels, counts, relative frequencies, or charts.

Bucketing is the **key-assignment** step; the histogram is the resulting **count aggregation per key**. If you later need sums, averages, or min/max per bucket, you can keep the exact same bucketing rule and swap the downstream collector.

## 2. Define Boundaries Before Writing Code

The cleanest convention uses **left-closed, right-open** intervals:

```text
[0, 10)    contains 0, 1, ..., 9
[10, 20)   contains 10, 11, ..., 19
[20, 30)   contains 20, 21, ..., 29
...
[90, 100)  contains 90, ..., 99
```

With this convention, a boundary value such as `10` belongs to **only one** bucket and is never double-counted. Formula for non-negative integers starting at 0:

```java
int width = 10;
int bucketIndex = value / width;
```

However, our sample data allows score **100** and wants exactly **10 buckets**. Computing `100 / 10` yields index 10, outside indices `0..9`.

Two valid options with different semantics:

| Policy | Valid Domain | How Score 100 Is Represented |
| --- | --- | --- |
| **Ten uniform width-10 intervals** | `[0,100)` | 100 falls into an out-of-range bucket or an 11th bucket |
| **Ten score bands, last band includes 100** | `[0,100]` | Final band is `90–100`, wider by one integer than earlier bands |

This lesson's score example uses the **second policy** and explicitly documents the final band's exception. Under that policy, do not describe all buckets as equal-width integer intervals.

On real data, document every decision: whether lower/upper bounds are inclusive, where underflow/overflow points are counted, and whether zero-count buckets must appear in reports.

## 3. Histograms with groupingBy and counting

When values are in an `int[]`, `Arrays.stream` creates an `IntStream`, which `boxed()` turns into `Stream<Integer>` for `Collectors.groupingBy`:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

int[] scores = {
        0, 9, 10, 18, 20, 45, 57,
        60, 76, 88, 99, 100, -5, 120
};

Map<Integer, Long> countsByBucket = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .boxed()
        .collect(Collectors.groupingBy(
                score -> Math.min(score / 10, 9),
                TreeMap::new,
                Collectors.counting()
        ));

System.out.println(countsByBucket.get(0)); // 2
System.out.println(countsByBucket.get(1)); // 2
System.out.println(countsByBucket.get(9)); // 2
System.out.println(countsByBucket.get(3)); // null
```

Pipeline breakdown:

- `filter` retains only scores in `0..100`.
- `boxed()` converts `IntStream` to `Stream<Integer>`, because `groupingBy` collects object Streams.
- The bucketing function `Math.min(score / 10, 9)` produces keys `0..9`, folding 100 into bucket 9.
- `Collectors.counting()` counts elements per bucket.
- `TreeMap::new` ensures numeric bucket keys iterate in ascending order.

**Warning:** `groupingBy` creates keys only for buckets actually observed. Because no score fell in 30–39, the Map **has no key 3**; `get(3)` returns `null`, not `0L`.

To print all 10 buckets:

```java
for (int i = 0; i < 10; i++) {
    int lower = i * 10;
    String label = (i == 9)
            ? "90-100"
            : lower + "-" + (lower + 9);

    long count = countsByBucket.getOrDefault(i, 0L);
    System.out.println(label + ": " + count);
}
```

`getOrDefault` supplies a fallback value; it **does not insert** missing keys into the Map. If a reporting API requires all 10 keys present, construct a new report Map or populate missing keys explicitly.

### Why Not Two-Argument toMap?

When two scores land in the same bucket, `Collectors.toMap(keyMapper, valueMapper)` hits a **duplicate key** and throws `IllegalStateException`. You can pass `Long::sum` as a merge function, though `groupingBy(..., counting())` expresses "count by group" more directly:

```java
Map<Integer, Long> alternative = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .boxed()
        .collect(Collectors.toMap(
                score -> Math.min(score / 10, 9),
                score -> 1L,
                Long::sum
        ));
```

Both produce bucket frequencies; Map type, ordering, and mutability may differ unless a factory is specified.

## 4. Primitive Histograms via Three-Argument IntStream.collect

When bucket counts are **small and fixed**, there is no need to box every `int` or allocate key objects. `IntStream` supports a three-argument `collect` accepting **supplier**, **accumulator**, and **combiner**.

To count the 10 score bands while also tracking out-of-range items, allocate:

- Indices `0..9`: the 10 score bands;
- Index `10`: scores below 0;
- Index `11`: scores above 100.

```java
import java.util.Arrays;

int[] scores = {
        0, 9, 10, 18, 20, 45, 57,
        60, 76, 88, 99, 100, -5, 120
};

long[] histogram = Arrays.stream(scores)
        .collect(
                () -> new long[12],
                (counts, score) -> {
                    if (score < 0) {
                        counts[10]++;
                    } else if (score > 100) {
                        counts[11]++;
                    } else {
                        counts[Math.min(score / 10, 9)]++;
                    }
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(histogram));
// [2, 2, 1, 0, 1, 1, 1, 1, 1, 2, 1, 1]
```

Here `long[]` is a **mutable accumulator**, and `long` stores counts. The three arguments must obey this contract:

| Parameter | In Example | Why Needed |
| --- | --- | --- |
| Supplier | `() -> new long[12]` | Allocates a **fresh** zeroed array each time invoked |
| Accumulator | Classifies one `int` and increments one slot | Routes each element into exactly one bucket |
| Combiner | Adds each right-array slot into left array | Merges partition results in parallel execution |

Never allocate a `long[]` outside and return that same instance from the Supplier. In parallel runs, each branch needs its own state per `IntStream.collect`'s contract; sharing one array causes **data races** and wrong counts.

Using the same Collector on a parallel source:

```java
long[] parallelHistogram = Arrays.stream(scores)
        .parallel()
        .collect(
                () -> new long[12],
                (counts, score) -> {
                    int index = score < 0 ? 10
                            : score > 100 ? 11
                            : Math.min(score / 10, 9);
                    counts[index]++;
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.equals(histogram, parallelHistogram));
// true
```

Because each slot adds independently, merging does not depend on partition tree shape (assuming no `long` overflow). Still, parallel is **not automatically faster**. With 14 numbers and 12 slots, splitting and merging arrays costs more than sequential counting.

### When to Choose an Array Over a Map?

| Scenario | `long[]` Array | `Map<K,Long>` |
| --- | --- | --- |
| Fixed, small bucket count | Usually sensible | Works, with more object allocations |
| Contiguously numbered buckets | Direct index access | Requires key encoding |
| Sparse or unbounded bucket count | Wastes memory | Usually more flexible |
| String labels or structured keys | Needs index ↔ label mapping | Keys express labels directly |
| Parallel execution | Per-branch array then merge | Combiner merges Maps |
| Multiple metrics per bucket | Needs custom container/DTO | Supports rich downstream collectors |

Do not pick arrays purely for "optimization": if bucket names or bounds change dynamically via config, Map/DTO designs can be much easier to maintain.

## 5. Total Counts, Valid Counts, and Percentages

A reporting histogram must clearly define its **denominator**. From the array above:

```java
long validCount = 0L;
for (int i = 0; i < 10; i++) {
    validCount += histogram[i];
}

long belowRange = histogram[10];
long aboveRange = histogram[11];
long totalInput = validCount + belowRange + aboveRange;

System.out.println(validCount); // 12
System.out.println(belowRange); // 1
System.out.println(aboveRange); // 1
System.out.println(totalInput); // 14
```

To report each band's share **of valid scores**:

```java
for (int i = 0; i < 10; i++) {
    double percent = validCount == 0L
            ? Double.NaN
            : 100.0 * histogram[i] / validCount;
    System.out.printf("bucket %d: %.2f%%%n", i, percent);
}
```

Returning `Double.NaN` when the denominator is 0 is a **representation choice**: "undefined due to zero valid scores". If the UI wants `"N/A"` or `OptionalDouble.empty()`, design the result type accordingly. Avoid showing 0% as though computed from real observations.

Note also that displayed percentages may sum to 99.99% or 100.01% due to **per-bucket rounding**. Preserve raw integer counts as ground truth; percentages are strictly derived presentation.

You could write `LongStream.of(histogram).limit(10).sum()` to sum valid slots, though a clear loop like above is often simplest in report formatting.

## 6. Negative Values: Use Math.floorDiv, Not Plain /

When buckets start at 0 and data includes negative numbers, integer division in Java **truncates toward 0**, not toward negative infinity. Thus `value / 10` mis-buckets negative values.

```java
System.out.println(-1 / 10);                 // 0  (wrong bucket for [-10, 0))
System.out.println(Math.floorDiv(-1, 10));   // -1
System.out.println(Math.floorDiv(-10, 10));  // -1
System.out.println(Math.floorDiv(-11, 10));  // -2
```

For width-10 intervals anchored at 0:

```text
bucket -3 = [-30, -20)
bucket -2 = [-20, -10)
bucket -1 = [-10,   0)
bucket  0 = [  0,  10)
bucket  1 = [ 10,  20)
bucket  2 = [ 20,  30)
```

Test data:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

int[] changes = {
        -21, -20, -11, -10, -1, 0, 9, 10, 19, 20
};

Map<Integer, Long> frequency = Arrays.stream(changes)
        .boxed()
        .collect(Collectors.groupingBy(
                value -> Math.floorDiv(value, 10),
                TreeMap::new,
                Collectors.counting()
        ));

System.out.println(frequency);
// {-3=1, -2=2, -1=2, 0=2, 1=2, 2=1}
```

For each `bucket` key, compute interval labels in `long` to avoid overflow when multiplying key by width:

```java
for (Map.Entry<Integer, Long> entry : frequency.entrySet()) {
    long lower = (long) entry.getKey() * 10L;
    long upper = lower + 10L;

    System.out.printf(
            "[%d, %d): %d%n",
            lower, upper, entry.getValue()
    );
}
```

**Note:** for integer data with a non-zero origin, use the offset `value - origin`. If both operands can lie near opposite ends of `int`, `int` subtraction overflows. Promote subtraction to `long` before dividing:

```java
static long uniformBucket(int value, int origin, int width) {
    if (width <= 0) {
        throw new IllegalArgumentException("width must be positive");
    }

    long offset = (long) value - origin;
    return Math.floorDiv(offset, (long) width);
}
```

This handles intervals with any origin, including negative `value` or negative `origin`, free from `int` truncation toward zero.

## 7. Variable-Width Intervals

Not all histograms divide into equal widths. Consider bucketing API response latencies:

```text
[0, 100)      very fast response
[100, 300)    fast response
[300, 1000)   slow response
[1000, 5000)  very slow response
out of range  measurement error or separate alert
```

Represent boundaries as a strictly increasing array:

```java
int[] edges = {0, 100, 300, 1000, 5000};
```

Rule: a value equal to a left edge **belongs to the bucket starting at that edge**, while a value equal to the final upper edge (`5000`) lies **outside all buckets**.

### Finding Buckets with binarySearch

Given strictly increasing, distinct boundaries:

```java
import java.util.Arrays;

static int findBucket(int value, int[] edges) {
    // Assumes edges are validated: at least 2 elements,
    // strictly increasing, and immutable during processing.
    int pos = Arrays.binarySearch(edges, value);

    if (pos >= 0) {
        // Matches a left boundary, except the final upper bound.
        return pos == edges.length - 1 ? -1 : pos;
    }

    // Negative binarySearch result encodes the insertion point.
    int insertionPoint = -pos - 1;
    int index = insertionPoint - 1;

    return index >= 0 && index < edges.length - 1
            ? index
            : -1;
}

static void validateEdges(int[] edges) {
    if (edges == null || edges.length < 2) {
        throw new IllegalArgumentException(
                "At least two edges required"
        );
    }

    for (int i = 1; i < edges.length; i++) {
        if (edges[i] <= edges[i - 1]) {
            throw new IllegalArgumentException(
                    "Edges must be strictly increasing"
            );
        }
    }
}
```

`Arrays.binarySearch` returns the index if an exact edge matches, or a negative value encoding the **insertion point** otherwise. For `k` buckets with `k + 1` edges, each lookup takes roughly `O(log k)`.

**Important:** call `validateEdges(edges)` **once before building the pipeline**, rather than re-validating the config on every element. Keep `edges` unmodified while the Stream executes; mutating it mid-run makes bucket assignment inconsistent.

### Collecting into a Count Array

```java
import java.util.Arrays;

int[] edges = {0, 10, 25, 50, 100};
int[] values = {0, 9, 10, 24, 25, 49, 50, 99, -1, 100};

validateEdges(edges);

long[] counts = Arrays.stream(values)
        .collect(
                () -> new long[edges.length - 1],
                (acc, value) -> {
                    int index = findBucket(value, edges);
                    if (index >= 0) {
                        acc[index]++;
                    }
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(counts));
// [2, 2, 2, 2]
```

This example's policy **excludes out-of-range values**. Elements `-1` and `100` are not counted in the four buckets. If reconciliation counts are needed, reserve two extra slots for underflow/overflow as in section 4, or return a report object tracking both valid and invalid counts.

### Warning When Comparing Variable-Width Intervals

A wider bucket can hold more items simply because **it is wider**. To compare density along a continuous axis, consider **frequency density** rather than raw bar height alone:

```text
group relative frequency  = count / validCount
density in an interval    = count / (validCount * interval width)
```

Thus, across `[0, 10)` and `[10, 100)`, having 20 elements in both does not mean equal density. Density is a distinct statistical measure, and charts must represent interval widths accurately so viewers are not misled.

## 8. Double Data: NaN, Infinity, and Boundary Precision

With `DoubleStream`, bucketing must also check **special values**:

- `Double.NaN` has no standard position on the number line.
- `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` lie outside finite ranges.
- Floating-point numbers have representation error; dividing by widths like `0.1` can land right on boundaries unexpectedly.
- `-0.0` and `0.0` need consistent handling if your domain distinguishes them.

Example source:

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

double[] samples = {
        0.4, 1.0, 2.2, 2.9,
        3.1, -0.1,
        Double.NaN,
        Double.POSITIVE_INFINITY
};

long[] buckets = DoubleStream.of(samples)
        .filter(Double::isFinite)
        .filter(value -> value >= 0.0 && value < 3.0)
        .collect(
                () -> new long[3],
                (counts, value) -> {
                    int index = (int) Math.floor(value);
                    counts[index]++;
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(buckets));
// [1, 1, 2]
```

The buckets here are `[0, 1)`, `[1, 2)`, and `[2, 3)`. Four samples are valid, and four are excluded (two out of range, one NaN, one infinity). When measurement errors matter, track rejected categories rather than silently filtering them away.

**About `DoubleStream.collect`:** it takes three arguments like `IntStream.collect`, with an accumulator of type `ObjDoubleConsumer<R>`. You cannot pass `Collectors.groupingBy(...)` directly to `DoubleStream.collect`; to use standard object Collectors, convert via `boxed()` or `mapToObj(...)`.

### Exact Decimal Bucketing

For currency, `0.1` and `0.01` cannot be represented exactly in binary `double`. When bucket boundaries must be exact:

- Store values as `long` minor units (cents, milliunits, etc.) and bucket on integers; or
- Use `BigDecimal` and `compareTo` against explicit boundary values.

Never use `(int) value` casting as a universal substitute for `Math.floor`, because floating-point-to-`int` casts truncate toward 0 and saturate on range limits.

## 9. Empty Buckets Should Be Surfaced Explicitly

With `groupingBy(..., counting())`, the Map holds only observed keys. If a report must always list every frequency band, construct the ordered Map from configuration rather than inferring it from the collected Map:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Long> report = new LinkedHashMap<>();

for (int i = 0; i < 10; i++) {
    int lower = i * 10;
    String label = i == 9
            ? "90-100"
            : lower + "-" + (lower + 9);

    report.put(label, countsByBucket.getOrDefault(i, 0L));
}

System.out.println(report.get("30-39")); // 0
System.out.println(report.containsKey("30-39")); // true
```

This creates **a new report Map** containing every bucket label, including zero-count bands. `LinkedHashMap` preserves insertion order so the table prints 0–9, 10–19, ..., 90–100 instead of relying on `HashMap` iteration order.

Do not confuse `getOrDefault(i, 0L)` with the original Map actually containing that key; it only returns a fallback. Filling empty buckets is the responsibility of the reporting layer or configuration builder.

If the application must distinguish **"bucket not observed yet"** from **"bucket observed with count 0"**, store additional source or window state. A plain `0` alone cannot tell those cases apart.

## 10. Histograms vs. partitioningBy and summaryStatistics

Aggregation APIs yield different result shapes:

| Goal | Suitable Approach | Characteristics |
| --- | --- | --- |
| Need only min, max, count, sum, average | `IntStream.summaryStatistics()` | Creates no buckets |
| Split into two groups by predicate | `Collectors.partitioningBy(predicate)` | Always contains keys `true` and `false` |
| Multiple intervals or categories | `groupingBy(classifier, counting())` | Flexible bucket count |
| Fixed, contiguously indexed intervals | `IntStream.collect` with `long[]` | Avoids boxing every element |
| Need original elements inside each bucket | `groupingBy(classifier)` | Retains `List<T>`, using more memory |
| Need multiple metrics per bucket | `groupingBy(classifier, downstream)` or custom container | Pick downstream matching required metrics |

For example, if you only care about **pass vs. fail** at threshold 50:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Long> passFail = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .boxed()
        .collect(Collectors.partitioningBy(
                score -> score >= 50,
                Collectors.counting()
        ));

System.out.println(passFail.get(true));  // 6
System.out.println(passFail.get(false)); // 6
```

`partitioningBy` always populates both Boolean keys even if one branch is empty. Yet when 10 score bands are needed, it cannot replace multi-bucket classification.

To compute summary statistics on valid scores without building a histogram:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .summaryStatistics();

System.out.println(stats.getCount()); // 12
System.out.println(stats.getMin());   // 0
System.out.println(stats.getMax());   // 100
```

You can combine both a histogram and summary statistics in one report, though two separate terminal operations **cannot reuse the same Stream instance**. On arrays, open two fresh streams; on I/O files or single-pass sources, design a single combined accumulator to read once.

## 11. Missing Data, Outliers, and Ingestion Policies

An `IntStream` never contains `null`, yet a wrapper `List<Integer>` can. For example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

List<Integer> rawScores = Arrays.asList(10, null, 20, 30);

IntStream validValues = rawScores.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue);
```

This expression actively **drops missing values**. If you need to count missing records, do not use this pipeline alone and treat the post-filter count as total input.

A clean report model might track:

```text
totalRows
missingCount
invalidBelowCount
invalidAboveCount
validCount
bins[0..k-1]
```

When collecting from a nullable `List<Integer>`, use `Stream<Integer>.collect` with a custom container to classify `null` and valid numbers in one pass. This is **mutable reduction**: the supplier creates a fresh container, the accumulator updates fields, and the combiner merges containers in parallel runs.

For floating-point inputs, also separate `NaN` and `Infinity`. When values exceed configured bounds, decide whether to **skip, raise an error, record underflow/overflow buckets, or clamp**. Clamping every outlier into the first/last bucket produces plausible-looking charts that hide measurement errors.

For very large counts, `long` has bounds. For sums inside buckets, `int`/`long` can overflow too. Choose numeric types and overflow checks to match data scale.

## 12. Practical Event-Stream Histogram Pattern

Suppose a monitoring service tracks API request latencies (in milliseconds) across defined service-level bands:

```text
[0, 100)      very fast
[100, 300)    normal
[300, 1000)   slow
[1000, 5000)  very slow
out of range  measurement error or values needing investigation
```

To represent results cleanly, build a complete processor:

```java
import java.util.Arrays;

final class LatencyHistogram {
    private static final int[] EDGES = {0, 100, 300, 1000, 5000};

    static long[] summarize(int[] latencyMillis) {
        int[] edges = EDGES; // immutable configuration during processing

        long[] result = Arrays.stream(latencyMillis)
                .collect(
                        () -> new long[edges.length + 1],
                        (counts, value) -> {
                            int index = findBucket(value, edges);

                            if (index >= 0) {
                                counts[index]++;
                            } else if (value < edges[0]) {
                                counts[edges.length - 1]++;
                            } else {
                                counts[edges.length]++;
                            }
                        },
                        (left, right) -> {
                            for (int i = 0; i < left.length; i++) {
                                left[i] += right[i];
                            }
                        }
                );

        return result;
    }

    private static int findBucket(int value, int[] edges) {
        int pos = Arrays.binarySearch(edges, value);
        if (pos >= 0) {
            return pos == edges.length - 1 ? -1 : pos;
        }

        int insertionPoint = -pos - 1;
        int index = insertionPoint - 1;
        return index >= 0 && index < edges.length - 1
                ? index
                : -1;
    }
}
```

Example:

```java
int[] latencies = {20, 90, 100, 250, 299, 300, 999, 1000, 6000, -3};

long[] report = LatencyHistogram.summarize(latencies);

System.out.println(Arrays.toString(report));
// [2, 3, 2, 1, 1, 1]
```

The result array has four slots for valid intervals, one slot for underflow, and one slot for overflow. Out-of-range indices are `edges.length - 1` and `edges.length`, kept separate from valid intervals.

With boundaries `{0, 100, 300, 1000, 5000}`, there are **4 intervals**, so total array length is `4 + 2 = 6`. Sizing as `new long[edges.length + 1]` matches because `edges.length = 5`.

Classification trace:

- 20 and 90 → `[0, 100)`: 2.
- 100, 250, and 299 → `[100, 300)`: 3.
- 300 and 999 → `[300, 1000)`: 2.
- 1000 → `[1000, 5000)`: 1.
- 6000 → above range: 1.
- -3 → below range: 1.

**Implementation note:** the class includes a `findBucket` matching section 7 so the example stands alone. `EDGES` is a pre-known, strictly increasing config array that **must not be mutated** during processing. If boundaries come from a file, copy them, run `validateEdges` once, and treat them as immutable throughout aggregation.

## 13. Parallelism and Performance Considerations

In histograms, per-element work is usually lightweight: compute bucket key and increment counter. Several approaches exist with trade-offs:

| Approach | Strengths | Costs or Limits |
| --- | --- | --- |
| Sequential `IntStream` + `long[]` | Few objects, simple, single array | Single-threaded |
| `IntStream.parallel().collect(...)` with private arrays | Splits work, combiner sums arrays | Allocates arrays and adds `O(k)` per merge |
| `Stream<Integer>.collect(groupingBy(..., counting()))` | Flexible dynamic buckets and downstreams | Boxing plus Map/Long allocations |
| `groupingByConcurrent(..., counting())` | Good when encounter order is unneeded and keys are dynamic | Contention when many values hit the same key |
| Mutating `sharedCounts[index]++` inside `parallel().forEach(...)` | Looks short | **Unsafe**: non-atomic increment |

Example **never to use** in parallel:

```java
long[] sharedCounts = new long[10];

// WRONG: multiple threads may update the same slot without synchronization.
Arrays.stream(scores)
        .parallel()
        .filter(s -> s >= 0 && s <= 100)
        .forEach(s -> sharedCounts[Math.min(s / 10, 9)]++);
```

Each `x++` is a read–increment–write sequence, not an atomic operation; counts will be lost.

Replace it with `IntStream.collect` supplying private arrays and a slot-wise combiner as in section 4. If concurrent shared counters are genuinely needed, `AtomicLongArray` or specialized concurrent counters work, though synchronization overhead does not always beat thread-local/branch-local arrays.

**A note on order:** pure frequency histograms usually do not need encounter order because counting is commutative. However, if a bucket also retains **the first three samples** or an ordered sequence, the output is no longer purely a histogram and requires order-preserving rules.

Memory sizing also matters:

- A `k`-bucket count array uses `O(k)` state per accumulator.
- A counting Map stores only observed buckets, typically `O(actual keys)`.
- Default `groupingBy(...)` stores full element lists per bucket, potentially consuming `O(n)` memory.
- For rolling time-window histograms, you must decide how to expire old values rather than incrementing forever.

Run benchmarks on your target JDK and realistic workloads only after correctness across all boundaries is verified.

## 14. I/O Sources and Streaming Histograms Without Loading Everything

For a file containing **one integer per line** representing latency, you can build the histogram while streaming instead of loading the entire file into a List:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long[] readHistogram(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .mapToInt(Integer::parseInt)
                .collect(
                        () -> new long[12],
                        (counts, value) -> {
                            int index = value < 0 ? 10
                                    : value > 100 ? 11
                                    : Math.min(value / 10, 9);
                            counts[index]++;
                        },
                        (left, right) -> {
                            for (int i = 0; i < left.length; i++) {
                                left[i] += right[i];
                            }
                        }
                );
    }
}
```

This assumes every non-empty line is a valid `int`; text or out-of-range numbers cause `Integer.parseInt` to throw `NumberFormatException`. Production systems need an explicit policy to count, skip, or abort on malformed lines.

Crucially, `Files.lines` returns a Stream **holding an OS resource**, so close it with `try-with-resources`. Terminal `collect` **does not close the file**; even on empty files, parse failures, or short-circuiting downstream, the resource must still be released.

Lazy I/O errors during traversal may surface as `UncheckedIOException`. Distinguish them from data-format errors, and never catch everything to return an all-zero histogram that hides a corrupted file.

## 15. Practice Exercises and Test Criteria

### Exercise A: Score Histogram with Two Outlier Slots

Write a method accepting `int[]` and returning `long[12]` per section 4's contract. Use:

```java
int[] sample = {0, 9, 10, 99, 100, -1, 101};
```

Expected result:

```text
bucket 0 (0-9)      = 2
bucket 1 (10-19)    = 1
bucket 9 (90-100)   = 2
underflow           = 1
overflow            = 1
all other buckets   = 0
total elements      = 7
```

Acceptance criteria: bucket counts plus both outlier slots sum exactly to the source length; sequential and parallel pipelines produce identical arrays.

### Exercise B: Negative Intervals and Boundaries

Use `Math.floorDiv` with width 10:

```java
int[] samples = {-11, -10, -1, 0, 9, 10};
```

Result:

```text
[-20,-10) -> 1
[-10,  0) -> 2
[  0, 10) -> 2
[ 10, 20) -> 1
```

Explain why `-1 / 10` cannot replace `Math.floorDiv(-1, 10)`.

### Exercise C: Variable-Width Intervals

With `edges = {0, 10, 25, 50, 100}`, verify:

```text
findBucket(-1)   = -1
findBucket(0)    = 0
findBucket(9)    = 0
findBucket(10)   = 1
findBucket(24)   = 1
findBucket(25)   = 2
findBucket(49)   = 2
findBucket(50)   = 3
findBucket(99)   = 3
findBucket(100)  = -1
```

Test duplicate or decreasing boundaries and verify `validateEdges` rejects the configuration.

### Exercise D: Multi-Band Latency Histogram

Extend `LatencyHistogram` to return an object holding `total`, `accepted`, `underflow`, `overflow`, and `bins`. Generate labels from `edges`, track below/above-range counts, and print a table including zero-count buckets. In real production reports, define what happens if boundary config changes between two runs.

## 16. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `value / width` on negatives | `-1` lands in bucket 0 | Use `Math.floorDiv` |
| Leaving upper bound undefined | Miscounts `100` or adds an extra bucket | Pick `[min, max)` or explicit final-bucket rule |
| Folding outliers into end buckets silently | Masks invalid data | Track separate underflow/overflow or fail |
| Expecting `groupingBy` to emit empty keys | Zero-count buckets are absent | Populate from config or use arrays |
| Two-arg `toMap` when multiple values share a bucket | `IllegalStateException` on duplicate key | Use `groupingBy(counting)` or a merge function |
| Treating `Map.get(missingKey)` null as 0 carelessly | Risks `NullPointerException` or ambiguity | Use `getOrDefault` or explicit empty entries |
| Dividing by total input while labeling "of valid scores" | Percentages contradict definition | Define denominator and label clearly |
| `counts[index]++` inside `parallel().forEach` | Data race, lost increments | Private accumulators via `collect` |
| Supplier returning the same mutable array | Contention or self-merging corruption | Allocate a fresh array per supplier call |
| Skipping `Double.NaN` or Infinity checks | Undefined bucketing behavior | Filter/check `Double.isFinite` |
| Casting `double` to `int` to "floor" | Wrong for negatives, risks range truncation | Use `Math.floor` and validate range |
| Building bins from unsorted boundaries | Binary search returns wrong buckets | Call `validateEdges` before pipeline |
| Mutating edges array mid-pipeline | Same-range values land in different buckets | Keep config immutable during run |
| Default `groupingBy` storing lists when only counts needed | Unnecessary `O(n)` memory | Use `counting` downstream or `long[]` |
| Adding `parallel()` just because data is numeric | Overhead can exceed speedup | Benchmark after proving correctness |
| Reading `Files.lines` without closing | Leaks OS file handles | Use `try-with-resources` |

## 17. Self-Check Questions

1. What question does a histogram answer? **The count or share of elements falling into each value interval**.
2. Does `[10, 20)` include 20? **No**, though it includes 10.
3. In a 10-band 0–100 policy, why does 100 need special handling? **Because `100 / 10 = 10`, outside indices `0..9`**.
4. Why can `groupingBy(counting())` omit a bucket key? **Because no element produced that key**.
5. When is `boxed()` needed? **When converting `IntStream` to `Stream<Integer>` for object collectors like `groupingBy`**.
6. Why does `IntStream.collect` take three functions? **To create a mutable container, accumulate each `int`, and combine two containers**.
7. What do the last two slots of `long[12]` represent in the example? **Scores below 0 and scores above 100**.
8. Why is `Math.floorDiv(-1, 10)` right while `-1 / 10` is wrong? **It floors to `-1`, matching `[-10, 0)`**.
9. What is the label for bucket index `-2` with origin `0` and step `10`? **`[-20, -10)`**.
10. With an edges array, which bucket gets a value equal to a left edge? **The bucket starting at that edge**, except the final upper bound which is out of range.
11. Why validate the edges array before the pipeline? **Because `binarySearch` requires ascending order and validating per element is wasteful**.
12. Should `Double.NaN` go into bucket 0? **No**; define a separate missing/invalid policy.
13. When bucket widths differ, what error does comparing raw counts cause? **Wider intervals appear taller even when density is lower**.
14. Can `partitioningBy` replace `groupingBy` for 10 buckets? **No**; it only splits into `true`/`false`.
15. If you only need counts per bucket, why avoid default `groupingBy` to Lists? **It buffers all elements in memory needlessly**.
16. Is updating one shared `long[]` in `parallel().forEach` safe? **No**; array-slot increments are non-atomic.
17. When the source is `Files.lines`, does `collect` close the file? **No**; use `try-with-resources`.

**Guiding rule:** Correct histograms begin with **defining intervals and boundaries**, then choosing between `groupingBy(..., counting())` and `IntStream.collect` with a count array. Explicitly define empty buckets, boundary points, negative values, outliers, missing data, and percentage denominators. When optimizing, keep accumulators/combiners contract-compliant, configuration immutable, I/O streams closed, and use parallelism only when benchmarks on real data prove a benefit.
