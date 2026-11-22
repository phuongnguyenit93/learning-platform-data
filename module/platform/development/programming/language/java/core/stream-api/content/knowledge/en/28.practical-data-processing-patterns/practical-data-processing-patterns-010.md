# Computing Windowed Metrics with Gatherers

In many data-analysis problems, a metric does not depend on a single record alone, but on **a group of consecutive records**: average temperature of the last three readings, total transactions per batch of 100 records, spread between two consecutive observations, or error rate per event batch. These are **window-based metrics** problems.

The Java Stream API provides `Gatherer` and factory methods `Gatherers.windowFixed` and `Gatherers.windowSliding` to construct windows directly inside a pipeline. After the `gather` step, each window is a `List<T>`, from which you can apply `map`, `reduce`, `collect`, or statistical operations to produce the required metric.

This lesson belongs to the **Practical Data Processing Patterns** chapter of the **JAVA_STREAM_API** module. The focus is on understanding window types, pairing each window with aggregations, handling empty or undersized inputs, trading off **count-based** windows against **time-based** windows, and respecting limits on ordering, state, performance, and parallel processing.

> **Version requirement:** Stream Gatherers were standardized in **Java 24**. Examples using `Stream.gather(...)` and `java.util.stream.Gatherers` in this lesson require JDK 24 or later. On JDK 22/23, this API was in preview with separate preview flags; **Java 17 does not include `Stream.gather`**.

## 1. What Is a Data Window?

A window is a slice of consecutive elements from a Stream with **encounter order**. After partitioning into windows, instead of computing one aggregate across all elements, we compute **one result per window**.

Example measurement sequence:

```text
Data:             10  20  30  40  50
Width-3 windows: [10  20  30]       → average 20
                     [20  30  40]   → average 30
                         [30  40  50] → average 40
```

Windows reveal local trends rather than yielding only:

```java
double overallAverage = java.util.stream.Stream
    .of(10, 20, 30, 40, 50)
    .mapToInt(Integer::intValue)
    .average()
    .orElseThrow();

System.out.println(overallAverage); // 30.0
```

An **overall mean of 30** hides the upward progression across each group of three readings. A moving average `[20, 30, 40]` shows how the data evolves.

### Two Fundamental Window Types

| Window Type | Characteristics | Example with `[10, 20, 30, 40, 50]`, size 3 |
| --- | --- | --- |
| **Fixed, non-overlapping** (*fixed / tumbling*) | Collects three items then starts a new group | `[10,20,30]`, `[40,50]` |
| **Sliding, overlapping** (*sliding*) | Each new full window drops the oldest item and adds the next | `[10,20,30]`, `[20,30,40]`, `[30,40,50]` |

Both types partition by **element count**, not by seconds or minutes. We contrast this with time-based windows later.

## 2. The Gatherer APIs You Need

Since Java 24, `java.util.stream.Gatherers` provides two primary factories:

```java
public static <TR> Gatherer<TR, ?, List<TR>> windowFixed(
    int windowSize
);

public static <TR> Gatherer<TR, ?, List<TR>> windowSliding(
    int windowSize
);
```

To apply a gatherer, call `Stream.gather(...)`:

```java
<R> Stream<R> gather(Gatherer<? super T, ?, R> gatherer)
```

Example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows); // [[1, 2, 3], [4, 5]]
```

Data types flow through the pipeline as:

```text
Stream<Integer>
    |
    | gather(Gatherers.windowFixed(3))
    v
Stream<List<Integer>>
    |
    | map(window -> metric)
    v
Stream<Metric>
    |
    | toList()
    v
List<Metric>
```

`gather` is an **intermediate operation**; it does not execute the pipeline by itself. A terminal operation such as `toList()`, `collect(...)`, `forEach(...)`, or `count()` triggers execution under Stream semantics.

### 2.1. Windows Require a Valid Size

`windowSize` must be at least `1`. Passing `0` or a negative number causes the factory to throw `IllegalArgumentException`.

```java
Gatherers.windowFixed(1);   // Valid.
Gatherers.windowSliding(5); // Valid.

// Gatherers.windowFixed(0);   // IllegalArgumentException.
// Gatherers.windowSliding(-2); // IllegalArgumentException.
```

For configuration-driven inputs, validate window size at the API boundary and enforce a sensible upper limit for memory safety.

### 2.2. Emitted Windows Are Unmodifiable Lists

Each window emitted by these two built-in gatherers is a `List` **that does not support mutating methods**:

```java
List<Integer> first = Stream.of(1, 2, 3)
    .gather(Gatherers.windowFixed(2))
    .findFirst()
    .orElseThrow();

System.out.println(first); // [1, 2]

// first.add(99); // UnsupportedOperationException.
```

Do not depend on the concrete List implementation class. If you genuinely need to modify a window, copy it into a new list such as `new ArrayList<>(window)` rather than mutating `window` directly.

## 3. `windowFixed`: Metrics per Non-Overlapping Batch

`Gatherers.windowFixed(k)` forms groups in encounter order, each containing up to `k` elements. When a finite Stream ends, the **final group may have fewer than `k` elements**.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> batches = Stream
    .of(4, 6, 8, 10, 12, 14, 16, 18)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(batches);
// [[4, 6, 8], [10, 12, 14], [16, 18]]
```

For `N` elements and `k > 0`, the number of fixed windows on a finite ordered source is:

\[
W_{\mathrm{fixed}}=\left\lceil \frac{N}{k} \right\rceil.
\]

If `N = 0`, the window count is 0. With `N = 8` and `k = 3`, we get 3 batches.

### 3.1. Summing per Three-Element Batch

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> batchTotals = List.of(100L, 200L, 300L, 400L, 500L)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .map(window -> window.stream()
        .mapToLong(Long::longValue)
        .sum())
    .toList();

System.out.println(batchTotals); // [600, 900]
```

The first batch sums to `600`; the second batch has only two elements yet is still emitted, summing to `900`.

**Define an explicit policy for undersized trailing batches:**

- **Accept a shorter final batch:** compute over available elements.
- **Accept only full batches:** filter by `window.size() == k`.
- **Withhold metrics until enough data arrives:** design an incomplete-sample result state or carry items over to the next run.

Example keeping only full three-element batches:

```java
List<Long> fullBatchTotals = List.of(100L, 200L, 300L, 400L, 500L)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .filter(window -> window.size() == 3)
    .map(window -> window.stream()
        .mapToLong(Long::longValue)
        .sum())
    .toList();

System.out.println(fullBatchTotals); // [600]
```

### 3.2. Counting Failure Rate per Batch

Suppose records carry a success or failure flag:

```java
record Job(String id, boolean failed) {}
record ErrorRate(long failed, long total, double ratio) {}

List<Job> jobs = List.of(
    new Job("J-1", false),
    new Job("J-2", true),
    new Job("J-3", false),
    new Job("J-4", true),
    new Job("J-5", true)
);

List<ErrorRate> rates = jobs.stream()
    .gather(Gatherers.windowFixed(3))
    .map(window -> {
        long failed = window.stream()
            .filter(Job::failed)
            .count();

        return new ErrorRate(
            failed,
            window.size(),
            (double) failed / window.size()
        );
    })
    .toList();

System.out.println(rates);
// [ErrorRate[failed=1, total=3, ratio=0.3333333333333333],
//  ErrorRate[failed=2, total=2, ratio=1.0]]
```

Every window emitted by `windowFixed` is non-empty, so `window.size()` here is never 0. Still, an empty input Stream produces **zero windows**; overall summary metrics for a completely empty source must be defined at the reporting layer.

## 4. `windowSliding`: Sliding Metrics Across Consecutive Elements

`Gatherers.windowSliding(k)` emits overlapping windows: each new full window drops the oldest element and appends the next element.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream
    .of(10, 20, 30, 40, 50)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[10, 20, 30], [20, 30, 40], [30, 40, 50]]
```

For `N >= k`, the number of sliding windows is:

\[
W_{\mathrm{sliding}}=N-k+1.
\]

When `0 < N < k`, the standard API emits **one short window containing the whole source**. If `N = 0`, zero windows are emitted. Thus the complete formula for a finite source is:

\[
W_{\mathrm{sliding}}=
\begin{cases}
0 & N=0,\\
1 & 0<N<k,\\
N-k+1 & N\ge k.
\end{cases}
\]

### 4.1. Computing a Three-Sample Moving Average

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Double> movingAverages =
    List.of(10, 20, 30, 40, 50)
        .stream()
        .gather(Gatherers.windowSliding(3))
        .map(window -> window.stream()
            .mapToInt(Integer::intValue)
            .average()
            .orElseThrow())
        .toList();

System.out.println(movingAverages); // [20.0, 30.0, 40.0]
```

This is a *simple moving average* (**SMA**) over the **three most recent elements**. Each output value represents a window whose last item is that window's latest observation.

For an ordered sequence `x1, x2, ..., xN` and `k <= N`, the mean at position `i >= k` is:

\[
\mathrm{SMA}_i=\frac{1}{k}\sum_{j=i-k+1}^{i}x_j.
\]

For instance, `x3=30`, `x4=40`, `x5=50` with `k=3` gives `SMA5=(30+40+50)/3=40`.

### 4.2. Handle Sources Shorter Than the Window Size Explicitly

```java
List<List<Integer>> shortWindows = List.of(10, 20)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(shortWindows); // [[10, 20]]
```

Never assume `windowSliding(3)` **always** returns three-element lists. On a two-element source, it still emits **one two-element window**.

If the metric strictly requires three samples:

```java
List<Double> fullOnly = List.of(10, 20)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .filter(window -> window.size() == 3)
    .map(window -> window.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow())
    .toList();

System.out.println(fullOnly); // []
```

**Business rules must state explicitly:** should initial metrics use available samples (*warm-up average*) or be emitted only once `k` samples exist (*full-window average*)?

## 5. Boundary-Case Comparison Table for Both Gatherers

Assume `k = 3`:

| Source | `windowFixed(3)` | `windowSliding(3)` |
| --- | --- | --- |
| `[]` | `[]` | `[]` |
| `[1]` | `[[1]]` | `[[1]]` |
| `[1,2]` | `[[1,2]]` | `[[1,2]]` |
| `[1,2,3]` | `[[1,2,3]]` | `[[1,2,3]]` |
| `[1,2,3,4]` | `[[1,2,3],[4]]` | `[[1,2,3],[2,3,4]]` |
| `[1,2,3,4,5,6]` | `[[1,2,3],[4,5,6]]` | `[[1,2,3],[2,3,4],[3,4,5],[4,5,6]]` |

**Key distinction:** `windowFixed` can emit a **short trailing window** even when the source is longer than `k`. `windowSliding` emits a short window only when the **entire source has fewer than `k` elements**. Whenever the source has at least `k` elements, every emitted sliding window is full.

Both preserve source encounter order within each window. On ordered sources, these two gatherers **must not be confused with key-based grouping** like `Collectors.groupingBy`.

## 6. Which Metrics Can Be Computed Over a Window?

After `gather`, each downstream element is a `List<T>`. You can aggregate it with standard operations:

| Metric | Suggested Calculation | Meaning |
| --- | --- | --- |
| Sample count | `window.size()` | How many observations participate |
| Sum | `window.stream().mapToLong(...).sum()` | Total volume, quantity, or revenue |
| Average | `window.stream().mapToDouble(...).average()` | Typical level in the window |
| Min / Max | `min()` / `max()` | Local extremes |
| Error rate | `count(failed) / window.size()` | Share of failing records in the batch |
| Distinct values | `distinct().count()` | Diversity within the group |
| Range / spread | `max - min` | Width of observed values |
| Start-to-end delta | `last - first` | Change across the endpoints of the window |

Example computing sum, min, max, and average for each window:

```java
import java.util.IntSummaryStatistics;

record WindowStats(long count, long sum, int min, int max, double average) {}

List<WindowStats> stats = List.of(4, 8, 6, 12, 10)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        IntSummaryStatistics s = window.stream()
            .mapToInt(Integer::intValue)
            .summaryStatistics();

        return new WindowStats(
            s.getCount(), s.getSum(),
            s.getMin(), s.getMax(), s.getAverage()
        );
    })
    .toList();

System.out.println(stats);
// [WindowStats[count=3, sum=18, min=4, max=8, average=6.0],
//  WindowStats[count=3, sum=26, min=6, max=12, average=8.666666666666666],
//  WindowStats[count=3, sum=28, min=6, max=12, average=9.333333333333334]]
```

Here `IntSummaryStatistics.getSum()` returns `long`. Still, `long` has limits; if exact integer totals can exceed 64 bits, use `BigInteger`. For floating-point inputs, averages remain subject to binary rounding error.

### 6.1. Endpoint Metrics Require Meaningful Ordering

```java
record Change(int start, int end, int delta) {}

List<Change> changes = List.of(100, 105, 98, 120)
    .stream()
    .gather(Gatherers.windowSliding(2))
    .map(window -> {
        int start = window.get(0);
        int end = window.get(window.size() - 1);
        return new Change(start, end, end - start);
    })
    .toList();

System.out.println(changes);
// [Change[start=100, end=105, delta=5],
//  Change[start=105, end=98, delta=-7],
//  Change[start=98, end=120, delta=22]]
```

Here `windowSliding(2)` computes deltas between **two consecutive observations** without a mutable `previous` variable outside the pipeline.

## 7. Practical Example: Sliding Sensor Metrics

Suppose a sensor emits temperature readings, each with a timestamp and value. We need a report over the last three readings: window end timestamp, sample count, average, minimum, and maximum.

For the metrics to be meaningful, the source must be in **event order**. This example assumes the list is already sorted by ascending timestamp.

```java
import java.time.Instant;
import java.util.List;
import java.util.stream.Gatherers;

record Reading(Instant at, double temperature) {}

record TemperatureMetric(
    Instant windowEnd,
    int samples,
    double average,
    double minimum,
    double maximum
) {}

List<Reading> readings = List.of(
    new Reading(Instant.parse("2026-01-01T10:00:00Z"), 20.0),
    new Reading(Instant.parse("2026-01-01T10:01:00Z"), 21.0),
    new Reading(Instant.parse("2026-01-01T10:02:00Z"), 22.0),
    new Reading(Instant.parse("2026-01-01T10:03:00Z"), 25.0),
    new Reading(Instant.parse("2026-01-01T10:04:00Z"), 24.0)
);

List<TemperatureMetric> metrics = readings.stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        var summary = window.stream()
            .mapToDouble(Reading::temperature)
            .summaryStatistics();

        return new TemperatureMetric(
            window.get(window.size() - 1).at(),
            window.size(),
            summary.getAverage(),
            summary.getMin(),
            summary.getMax()
        );
    })
    .toList();

metrics.forEach(System.out::println);
```

This yields three metrics:

| Window | Window End | Average | Min | Max |
| --- | --- | ---: | ---: | ---: |
| `[20,21,22]` | 10:02 UTC | 21.0 | 20.0 | 22.0 |
| `[21,22,25]` | 10:03 UTC | 22.666… | 21.0 | 25.0 |
| `[22,25,24]` | 10:04 UTC | 23.666… | 22.0 | 25.0 |

When inputs are short, `windowSliding(3)` can emit a short window, and `summary.getAverage()` computes over the elements present. If three samples are mandatory, add:

```java
.filter(window -> window.size() == 3)
```

right after `gather`.

### 7.1. Reading Trends and Raising Alerts

You can filter right after computing metrics:

```java
List<TemperatureMetric> hotWindows = readings.stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        var summary = window.stream()
            .mapToDouble(Reading::temperature)
            .summaryStatistics();

        return new TemperatureMetric(
            window.get(window.size() - 1).at(),
            window.size(),
            summary.getAverage(),
            summary.getMin(),
            summary.getMax()
        );
    })
    .filter(metric -> metric.average() > 23.0)
    .toList();

System.out.println(hotWindows.size()); // 1
```

Here the alert condition inspects the **window average**, not individual readings. Placing `filter(reading -> reading.temperature() > 23)` **before** `gather` removes source records, altering the windows themselves and changing the metric's meaning.

## 8. Count-Based Windows Differ from Time-Based Windows

A common business mistake is assuming `windowSliding(3)` means "the last three minutes". In reality, it means **the last three records**.

Consider this data:

```text
10:00 → 20°C
10:01 → 21°C
10:10 → 22°C
10:11 → 25°C
```

`windowSliding(3)` forms the window `[10:00, 10:01, 10:10]`, even though the first and third observations are **10 minutes** apart. It never inspects timestamps or expires stale elements by time.

| Window Basis | Defined By | Example |
| --- | --- | --- |
| Element count | Record count in encounter order | Last three transactions |
| Processing time | Wall clock when the server receives/processes records | Requests per minute as received |
| Event time | Timestamp carried by the event | Temperature over 5 minutes by reading time |

If you need a 5-minute event-time window, the application must specify:

- Is data **sorted by timestamp** yet?
- Are time intervals **[start, end)** or another boundary rule?
- How are late arrivals or duplicate timestamps handled?
- Does the window slide every minute, every second, or per event?
- Are watermarks, late-data handling, or durable state required?

`windowFixed` and `windowSliding` **do not provide** event-time semantics automatically. Complex real-time event windows may require a custom `Gatherer`, timestamped state management, or a dedicated stream-processing engine.

### 8.1. Source Ordering Determines Metric Correctness

If inputs are not yet sorted by time, add a sort stage or dedicated ordering logic:

```java
import java.util.Comparator;

List<TemperatureMetric> sortedMetrics = readings.stream()
    .sorted(Comparator.comparing(Reading::at))
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        var summary = window.stream()
            .mapToDouble(Reading::temperature)
            .summaryStatistics();

        return new TemperatureMetric(
            window.get(window.size() - 1).at(),
            window.size(),
            summary.getAverage(),
            summary.getMin(),
            summary.getMax()
        );
    })
    .toList();
```

`sorted` on a finite dataset costs time and memory. Never try to sort an unbounded infinite Stream expecting immediate online output.

## 9. Per-Device Metrics: Combining `groupingBy` and Gatherers

When records arrive from multiple devices, never slide windows directly across a **mixed-device stream**: a single window would mix temperatures from different sensors.

A simple approach for finite data is grouping by device first, then computing windows independently per device list.

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Gatherers;

record DeviceReading(String deviceId, Instant at, double value) {}
record DeviceMetric(Instant endAt, double movingAverage) {}

List<DeviceReading> input = List.of(
    new DeviceReading("A", Instant.parse("2026-01-01T10:00:00Z"), 10.0),
    new DeviceReading("B", Instant.parse("2026-01-01T10:00:00Z"), 90.0),
    new DeviceReading("A", Instant.parse("2026-01-01T10:01:00Z"), 20.0),
    new DeviceReading("B", Instant.parse("2026-01-01T10:01:00Z"), 80.0),
    new DeviceReading("A", Instant.parse("2026-01-01T10:02:00Z"), 30.0)
);

Map<String, List<DeviceMetric>> byDevice = input.stream()
    .collect(Collectors.groupingBy(DeviceReading::deviceId))
    .entrySet().stream()
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        entry -> entry.getValue().stream()
            .sorted(Comparator.comparing(DeviceReading::at))
            .gather(Gatherers.windowSliding(3))
            .map(window -> new DeviceMetric(
                window.get(window.size() - 1).at(),
                window.stream()
                    .mapToDouble(DeviceReading::value)
                    .average()
                    .orElseThrow()
            ))
            .toList()
    ));

System.out.println(byDevice.get("A"));
// [DeviceMetric[endAt=2026-01-01T10:02:00Z, movingAverage=20.0]]

System.out.println(byDevice.get("B"));
// [DeviceMetric[endAt=2026-01-01T10:01:00Z, movingAverage=85.0]]
```

Device `A` has three samples, producing one full window. Device `B` has only two samples, so `windowSliding(3)` emits **one short window** averaging `85.0`. If the product only displays metrics with three samples, add `filter(window -> window.size() == 3)` to each group's pipeline.

**Trade-off:** `groupingBy` materializes all groups' data before windowing, so memory scales with input size. For massive datasets, already-partitioned device streams, or continuous online processing, choose another architecture to avoid retaining full history.

## 10. Financial Metrics: Exact Totals and Rounding Rules

For money, never switch to `double` merely because `mapToDouble` offers a convenient `.average()`. Use `BigDecimal` when values are decimal and business rules require explicit rounding.

Example batch total and average:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.stream.Gatherers;

record Sale(String id, BigDecimal amount) {}
record RevenueMetric(int count, BigDecimal total, BigDecimal average) {}

List<Sale> sales = List.of(
    new Sale("S1", new BigDecimal("10.10")),
    new Sale("S2", new BigDecimal("20.20")),
    new Sale("S3", new BigDecimal("30.30")),
    new Sale("S4", new BigDecimal("40.40"))
);

List<RevenueMetric> metrics = sales.stream()
    .gather(Gatherers.windowFixed(3))
    .map(window -> {
        BigDecimal total = window.stream()
            .map(Sale::amount)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new RevenueMetric(
            window.size(),
            total,
            total.divide(
                BigDecimal.valueOf(window.size()),
                2,
                RoundingMode.HALF_UP
            )
        );
    })
    .toList();

System.out.println(metrics);
// [RevenueMetric[count=3, total=60.60, average=20.20],
//  RevenueMetric[count=1, total=40.40, average=40.40]]
```

Note: `windowFixed` emits a final window with just one amount. That may be right for batch sales totals, or wrong if a "settlement cycle" must always comprise three transactions.

Validate input values before computing. `BigDecimal` ensures exact decimal addition, yet does not replace checking negative amounts, cancelled transactions, duplicate timestamps, or currency units.

## 11. Custom Gatherers: State and Window Finalization

The two built-in factories work well when you only need a **list of elements per window** to compute a metric. However, for a sliding window with large `k`, allocating a new list and re-iterating all `k` items to sum them repeats work.

An advanced option is writing a custom `Gatherer` with internal state: keep up to `k` elements in a `Deque` alongside a running sum. On each new element, evict the oldest if size reached `k`, then update the sum. This is *incremental sliding aggregation*.

### 11.1. Four Components of a Custom Gatherer

`Gatherer<T, A, R>` has three type parameters:

- `T`: input element type, e.g., `Long`.
- `A`: internal state type, e.g., `RunningState`.
- `R`: output element type, e.g., `Long` window sum.

A gatherer can define:

| Component | Purpose |
| --- | --- |
| **Initializer** | Creates isolated state for the run |
| **Integrator** | Consumes a new element, updates state, optionally pushes zero or more results downstream |
| **Combiner** | Merges two states when supporting parallel execution |
| **Finisher** | Emits final outputs at end-of-stream if needed, e.g., a short trailing window |

Unlike `Collector`, a `Gatherer` is an **intermediate operation** able to emit multiple outputs as inputs flow through, rather than producing only one final result object.

### 11.2. Custom Gatherer Example: Rolling Sum

The complete Java 24+ program below implements `rollingSum(k)` matching `windowSliding(k)`'s element-count semantics:

- Once `k` samples are seen, emit the running sum after each new element.
- If the source is non-empty yet **shorter than `k`**, the finisher emits one sum of all received samples.
- If the source is empty, emit nothing.

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.stream.Gatherer;

public class RollingSumGathererDemo {

    static final class RunningState {
        final int width;
        final Deque<Long> values = new ArrayDeque<>();
        long sum = 0L;

        RunningState(int width) {
            this.width = width;
        }

        void accept(long value) {
            if (values.size() == width) {
                sum = Math.subtractExact(sum, values.removeFirst());
            }

            values.addLast(value);
            sum = Math.addExact(sum, value);
        }
    }

    static Gatherer<Long, RunningState, Long> rollingSum(int width) {
        if (width < 1) {
            throw new IllegalArgumentException("width must be >= 1");
        }

        return Gatherer.ofSequential(
            () -> new RunningState(width),

            // Integrator: accept each element and push when window is full.
            (state, value, downstream) -> {
                state.accept(value);

                if (state.values.size() == width) {
                    return downstream.push(state.sum);
                }

                return !downstream.isRejecting();
            },

            // Finisher: emit one short window if the entire source had < width items.
            (state, downstream) -> {
                if (!state.values.isEmpty()
                        && state.values.size() < width
                        && !downstream.isRejecting()) {
                    downstream.push(state.sum);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Long> numbers = List.of(10L, 20L, 30L, 40L, 50L);

        System.out.println(numbers.stream()
            .gather(rollingSum(3))
            .toList()); // [60, 90, 120]

        System.out.println(List.of(10L, 20L).stream()
            .gather(rollingSum(3))
            .toList()); // [30]

        System.out.println(List.<Long>of().stream()
            .gather(rollingSum(3))
            .toList()); // []
    }
}
```

### Why Use `Gatherer.ofSequential`?

A rolling sum is **order-dependent**: to emit the next window accurately, state needs the last `k - 1` elements from the prior segment. Simply adding two parallel partition sums cannot reconstruct windows **straddling partition boundaries**.

`Gatherer.ofSequential` declares that this gatherer runs sequentially without supplying an invalid parallel combiner. Even if the source stream calls `parallel()`, do not assume a stateful sliding window automatically splits across parallel workers.

### Crucial Notes on Correctness and Precision

- `Math.addExact` and `Math.subtractExact` **catch `long` overflow with exceptions** instead of widening range automatically. If monetary sums can exceed `long` or intermediate sums risk overflow, use `BigInteger` or a higher-precision accumulator.
- Each `sum` update takes constant arithmetic work per element, while the `Deque` still holds up to `k` elements.
- Computation runs over **input order**; windows carry no timestamps unless state tracks them.
- When downstream short-circuits, `downstream.push(...)` returns `false`; the integrator must respect that signal.
- State belongs strictly to the executing gatherer run; never share a global `Deque` across Streams.

This example is pedagogical. In production, test varied input lengths, negative numbers, overflow, early termination, reordering, and malformed sources.

## 12. How `gather`, `scan`, `reduce`, and `collect` Differ

These APIs can all appear in metrics pipelines, each serving a distinct role:

| Tool | Primary Output | Best When |
| --- | --- | --- |
| `filter` / `map` | Selects or transforms each element | Per-element independent rules |
| `Gatherers.windowFixed(k)` | `Stream<List<T>>` non-overlapping groups | Batch metrics of size `k` |
| `Gatherers.windowSliding(k)` | `Stream<List<T>>` overlapping groups | Metrics over the last `k` observations |
| `Gatherers.scan(...)` | Running accumulated value per element | Cumulative totals from start, without evicting old items |
| `reduce(...)` | Single final aggregated value | One global sum/reduction across the whole source |
| `collect(...)` | Single final container or summary object | Grouping, overall reports, Maps |
| Custom `Gatherer` | Output stream driven by intermediate state | Custom windowing/alert logic not built in |

### 12.1. Running Totals Are Not Sliding-Window Sums

`Gatherers.scan` computes a cumulative value from the start of the Stream:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> runningTotals = List.of(10L, 20L, 30L, 40L)
    .stream()
    .gather(Gatherers.scan(
        () -> 0L,
        Long::sum
    ))
    .toList();

System.out.println(runningTotals); // [10, 30, 60, 100]
```

Whereas a width-3 sliding window sum gives:

```java
List<Long> rollingTotals = List.of(10L, 20L, 30L, 40L)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream()
        .mapToLong(Long::longValue)
        .sum())
    .toList();

System.out.println(rollingTotals); // [60, 90]
```

`scan` **never evicts old elements**. `windowSliding` maintains only the latest window span. They agree only in special cases and are not interchangeable.

### 12.2. Keyed `collect` Is Not a Consecutive Window

`Collectors.groupingBy(DeviceReading::deviceId)` groups **all records with the same key**, even if separated by many elements. Sliding windows group **consecutive elements in encounter order**. You can combine both, provided you define which groups must be isolated before building windows.

## 13. Laziness, Short-Circuiting, and Finite vs. Infinite Sources

`gather` is an intermediate operation that runs only when downstream pulls elements:

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Stream<List<Integer>> pending = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3)); // Windows are not collected yet.

System.out.println(pending.findFirst().orElseThrow());
// [1, 2, 3]
```

With `findFirst()`, the pipeline can stop right after emitting one full window. Never rely on side effects inside `peek`, `map`, or an integrator assuming every source element was visited.

### 13.1. Infinite Streams and Count-Based Windows

On an ordered infinite source, `windowSliding(3)` emits a window after every element once three samples arrive:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> firstWindows = Stream.iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(3)
    .toList();

System.out.println(firstWindows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

`limit(3)` caps **output windows**, not input elements. To emit three width-3 windows, the gatherer must pull at least through the fifth source element.

Omitting `limit` and calling `toList()` on an infinite source has no natural termination and can exhaust resources indefinitely.

### 13.2. Never Compute via Side Effects in Lambdas

Wrong example:

```java
// Avoid: using a mutable List outside the Stream to collect windows.
List<List<Integer>> shared = new java.util.ArrayList<>();

Stream.iterate(1, n -> n + 1)
    .limit(100)
    .parallel()
    .gather(Gatherers.windowSliding(3))
    .forEach(shared::add);
```

An external `ArrayList` is unsafe for concurrent updates. Use `toList()` or an appropriate collector so the framework manages results safely.

## 14. Parallel Processing and Order Guarantees

Windows **depend on encounter order**. When a source is ordered, that order defines which elements are "adjacent".

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .parallel()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Do not assume `parallel()` helps automatically: overlapping windows must coordinate boundaries across splits. A sequential stateful gatherer restricts parallel speedup; even with a splittable gatherer, merging state and preserving order carry overhead.

### 14.1. Avoid `unordered()` When Order Carries Meaning

`unordered()` does not necessarily shuffle data, yet it **drops the encounter-order guarantee**. "The last three observations" has no deterministic meaning without an ordered input.

If the source is a `HashSet` or unordered pipeline, establish business ordering first. Merely having a timestamp field on an element does not automatically sort a Stream by timestamp.

### 14.2. Partition by Device Before Parallelizing

In multi-device workloads, you can process **independent device groups** in parallel at the group level while keeping windowing sequential **within each group**. That split is often far easier to reason about than parallelizing one overlapping window chain.

Still, materializing all groups upfront trades memory; never assume it fits infinite or continuously streaming sources.

## 15. Memory, Time, and Precision

### 15.1. Window Counts Can Be Huge

With `N` elements and sliding window `k` (for `N >= k`), there are `N - k + 1` windows. For one million elements and width 100:

\[
1\,000\,000-100+1=999\,901\text{ windows}.
\]

If `toList()` retains **every** window list, storage overhead can be massive. Each window holds up to `k` element references; allocating, copying, and retaining many windows costs both CPU and memory. Never retain full window history if the product only needs active alerts or a final metric.

**Design alternative:** consume metrics as they are emitted, or write a custom `Gatherer` updating incremental metrics without allocating a new list per window.

### 15.2. Unusually Large `windowSize` Still Has Upfront Cost

Built-in window gatherers may allocate buffers sized for `windowSize` early. Thus a huge configured `windowSize` can consume memory even on short input Streams.

Set configuration caps, validate `k > 0`, and test `N < k`, `N = k`, `N = k + 1`, and realistic datasets.

### 15.3. Metric Precision

- `IntStream.sum()` can overflow `int`; `LongStream.sum()` can overflow `long`.
- `mapToDouble(...).average()` uses binary floating point with rounding error.
- `BigDecimal` suits decimal money with explicit rounding; `BigInteger` suits huge integer sums.
- Windows can vary in size on short sources, so the **average denominator must be `window.size()`**, never assumed equal to `k`.
- With incremental sliding sums, subtracting old items and adding new ones must stay safe under overflow, negatives, and abnormal values.

### 15.4. Benchmark Before Optimizing

Measure runtime, memory, allocation rate, and emitted metrics using representative data. For performance-critical Java code, use JMH. Compare built-in windowing against custom Gatherers while ensuring **identical window semantics and rounding rules** before comparing speed.

## 16. I/O Sources and Lifecycle Management

Streams from `Files.lines(path)` or similar I/O resources must be closed. `gather`, `limit`, and terminal operations **do not replace `close()`**.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

// Place inside a method declaring throws IOException or handling exceptions.
Path file = Path.of("measurements.txt");

try (Stream<String> lines = Files.lines(file)) {
    List<Double> averages = lines
        .filter(line -> !line.isBlank())
        .map(Double::parseDouble)
        .gather(Gatherers.windowFixed(4))
        .map(window -> window.stream()
            .mapToDouble(Double::doubleValue)
            .average()
            .orElseThrow())
        .toList();

    System.out.println(averages);
}
```

If an invalid line appears, `Double.parseDouble` throws `NumberFormatException`. `try-with-resources` still closes the file handle when exiting the block.

**Ordering rule:** If you filter out bad records before `gather`, windows form over the **surviving elements**, shifting alignment relative to dropped readings. When business rules require preserving timestamps and flagging missing slots, model errors as explicit states rather than deleting them.

## 17. Complete Java 24 Example: Reporting Both Fixed and Sliding Metrics

The program below can be saved as `WindowMetricsDemo.java` and compiled on JDK 24+. It operates on immutable in-memory data, needing no file or I/O management.

```java
import java.time.Instant;
import java.util.List;
import java.util.stream.Gatherers;

public class WindowMetricsDemo {

    record Reading(Instant at, int value) {}

    record Metric(
        Instant endAt,
        int samples,
        long sum,
        double average,
        int min,
        int max
    ) {}

    static Metric metricOf(List<Reading> window) {
        var s = window.stream()
            .mapToInt(Reading::value)
            .summaryStatistics();

        return new Metric(
            window.get(window.size() - 1).at(),
            window.size(),
            s.getSum(),
            s.getAverage(),
            s.getMin(),
            s.getMax()
        );
    }

    public static void main(String[] args) {
        List<Reading> input = List.of(
            new Reading(Instant.parse("2026-01-01T00:00:00Z"), 10),
            new Reading(Instant.parse("2026-01-01T00:01:00Z"), 20),
            new Reading(Instant.parse("2026-01-01T00:02:00Z"), 30),
            new Reading(Instant.parse("2026-01-01T00:03:00Z"), 40),
            new Reading(Instant.parse("2026-01-01T00:04:00Z"), 50)
        );

        List<Metric> fixed = input.stream()
            .gather(Gatherers.windowFixed(3))
            .map(WindowMetricsDemo::metricOf)
            .toList();

        List<Metric> sliding = input.stream()
            .gather(Gatherers.windowSliding(3))
            .map(WindowMetricsDemo::metricOf)
            .toList();

        System.out.println("FIXED");
        fixed.forEach(System.out::println);

        System.out.println("SLIDING");
        sliding.forEach(System.out::println);
    }
}
```

Output:

```text
FIXED
Metric[endAt=2026-01-01T00:02:00Z, samples=3, sum=60, average=20.0, min=10, max=30]
Metric[endAt=2026-01-01T00:04:00Z, samples=2, sum=90, average=45.0, min=40, max=50]
SLIDING
Metric[endAt=2026-01-01T00:02:00Z, samples=3, sum=60, average=20.0, min=10, max=30]
Metric[endAt=2026-01-01T00:03:00Z, samples=3, sum=90, average=30.0, min=20, max=40]
Metric[endAt=2026-01-01T00:04:00Z, samples=3, sum=120, average=40.0, min=30, max=50]
```

**Analysis:** `windowFixed` emits two windows, with the last containing two samples. `windowSliding` emits three full windows. `metricOf` does not care how the windows were formed: it simply receives a list of elements forming a window and computes metrics. This **separates window creation from metric calculation**, keeping code clean and testable.

## 18. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Running `gather` examples on JDK 17 | No standard `Stream.gather`/`Gatherers` | Use JDK 24+ or a version-compatible alternative |
| Confusing `windowSliding(3)` with "last 3 minutes" | Widely separated records share one window | Distinguish count-based from time-based windows |
| Assuming `windowSliding(k)` always has k samples | Sources with `0 < N < k` emit one short window | Filter `window.size() == k` if required |
| Assuming `windowFixed(k)` drops trailing short windows | Report includes a shorter final batch | Accept or filter the trailing batch per policy |
| Windowing over mixed-device streams | Metrics blend readings from multiple devices | Group or partition by device first |
| Computing "latest" on an unordered source | Windows lack meaningful time order | Sort by timestamp or guarantee ordered input |
| Filtering before `gather` expecting original counts | Windows form after elements are removed | Clarify filter vs. window order |
| Calling `get(2)` on every width-3 window | Fails on short trailing/small windows | Check `size()` or use `get(size() - 1)` |
| Dividing mean by k even on short windows | Wrong average | Divide by actual element count |
| Mutating lists created by Gatherers | `UnsupportedOperationException` | Copy to a mutable list if needed |
| Calling `toList()` over all windows of huge sources | Sharp memory spike | Consume metrics incrementally or write a custom Gatherer |
| Adding `parallel()` assuming instant speedup | Window coordination overhead can dominate | Verify outputs and benchmark first |
| Using `reduce` over whole Stream for SMA | Gives one global total, no windows | Use `windowSliding` or a custom Gatherer |
| Replacing sliding windows with `Gatherers.scan` | Running total never evicts old items | Use `windowSliding` or rolling state |
| Opening I/O source and forgetting to close after `limit`/`gather` | Resource leak | Use `try-with-resources` |
| Calculating money with `double` expecting exactness | Binary rounding error | Use `BigDecimal` with explicit rounding rules |

## 19. Practice Exercises

### Exercise 1: Predicting Windows

Given `Stream.of(3, 6, 9, 12, 15, 18, 21)` and `k = 3`. Write out by hand the windows from `windowFixed` and `windowSliding`. Compute window counts with the formulas, then run a program to verify.

### Exercise 2: Moving Average

Given temperatures `[20, 21, 23, 24, 22, 25]`. Compute the 3-sample moving average using `Gatherers.windowSliding(3)` and `mapToInt(...).average()`. Note which element's timestamp each average corresponds to.

### Exercise 3: Undersized Windows

For `[10, 20]` and `k = 4`, predict the outputs of `windowFixed`, `windowSliding`, and both pipelines followed by `filter(w -> w.size() == 4)`. Why can automatically dropping short windows lose warm-up visibility?

### Exercise 4: Failure Rate per Batch

Create `record Job(String id, boolean failed)` and 10 jobs. Batch with `windowFixed(4)`; for each batch, compute failed count and failure rate. Raise an alert if failure rate exceeds 25%, noting how to handle a final batch of only two jobs.

### Exercise 5: Detecting Large Jumps Between Samples

Use `windowSliding(2)` to form measurement pairs. Map each pair to the absolute difference using a wide enough numeric type for `int` inputs, then filter pairs exceeding a threshold.

### Exercise 6: Per-Device Metrics

Given interleaved readings from sensors A and B. Produce a width-3 moving average report **per sensor**, preserving timestamp order. Compare with applying `windowSliding` before `groupingBy` and explain why that is wrong.

### Exercise 7: Count-Based vs. Time-Based Windows

Given records at 10:00, 10:01, 10:10, 10:11, and 10:12. Show how three consecutive records differ from a three-minute window. List the extra requirements needed to handle duplicate timestamps, late records, and open/closed time boundaries.

### Exercise 8: Custom Gatherer

Starting from `rollingSum(3)` in section 11, replace the sum with `BigInteger` to prevent `long` overflow. Test `[Long.MAX_VALUE, 1L, -1L]`; compare with `Math.addExact` and explain when to check only the final sum versus every intermediate sum.

### Exercise 9: Benchmarking and Memory

For one million observations and window width 100, estimate the sliding window count. Compare `gather(windowSliding).map(...).toList()` against a custom Gatherer emitting only sums without retaining window lists. Propose a fair JMH benchmark and boundary-case checks.

### Exercise 10: Infinite Streams

Create an unbounded `Stream.iterate(...)`, apply `windowSliding(5)` and `limit(3)`. Count the minimum source elements pulled to emit three full windows; explain why `limit` must not be removed when `toList()` is the terminal operation.

## 20. Knowledge Check

- How do `windowFixed` and `windowSliding` differ in overlap?
- Why can `windowFixed(3)` emit a trailing window with one or two elements?
- On a two-element source, what does `windowSliding(3)` return?
- For `N >= k`, what is the formula for the sliding window count?
- Is `Stream.gather` an intermediate or terminal operation?
- Why is `windowSliding(3)` not automatically a three-minute window?
- With multi-device data, why must windows be partitioned by device?
- Why can filtering before `gather` change a metric's meaning?
- When does `Gatherers.scan` apply, and why does it differ from a rolling sum?
- What are the roles of initializer, integrator, combiner, and finisher in a custom Gatherer?
- Why can an order-dependent rolling Gatherer not simply add two parallel branch sums?
- What memory risks arise when windows are huge and `toList()` keeps all of them?
- When should you choose `BigDecimal`, `BigInteger`, or `Math.addExact`?
- Why must `gather` over `Files.lines` still be wrapped in `try-with-resources`?

## 21. References

- [Java SE 24 — `Gatherers`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): contract and edge cases of `windowFixed`, `windowSliding`, and `scan`.
- [Java SE 24 — `Gatherer`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer, integrator, combiner, finisher, and `ofSequential`.
- [Java SE 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): usage patterns for built-in Gatherers.

**Key takeaway:** Gatherers transform a Stream into **ordered windows** for computing metrics over consecutive groups. Use `windowFixed(k)` for non-overlapping batches and `windowSliding(k)` for sliding metrics over the last `k` observations. Always define an **undersized-window** policy, distinguish **element counts from time intervals**, keep encounter order aligned with business semantics, and watch memory when window counts are huge. Write a custom `Gatherer` only when incremental state and finalization benefits justify the contract complexity.
