# Creating Sliding Windows with `Gatherers.windowSliding`

## 1. Objectives and context

In the **`JAVA_STREAM_API`** module, learners are already familiar with declarative data-processing pipelines using `filter`, `map`, `flatMap`, `reduce`, and `collect`. However, many problems require processing **relationships between consecutive elements**: the average of the three most recent values, comparing changes between two measurement samples, recognizing three consecutive words, or detecting anomalous signals in a time series.

Regular `map` operations receive only one element at a time. You could write a manual loop or a stateful collector, but **Stream Gatherers** provide a more direct way to express stateful intermediate operations. One built-in gatherer is **`Gatherers.windowSliding(windowSize)`**, used to create **overlapping sliding windows**.

In the **Stream Gatherer** chapter, this lesson focuses on how to read, write, and test sliding-window pipelines, while distinguishing business requirements from parallelizability, memory cost, and resource lifecycles.

After finishing this lesson, you will be able to:

1. Explain the meaning of sliding windows and how they differ from fixed batching.
2. Use `Stream.gather(Gatherers.windowSliding(k))` in **Java 24+**.
3. Accurately predict results for an empty source, a source shorter than the window, `k = 1`, and `k > 1`.
4. Compute moving averages, deltas, n-grams, and pattern detection using `map`, `filter`, and `anyMatch`.
5. Recognize that windows are **unmodifiable** lists, without automatically making mutable elements immutable.
6. Verify window size, ordering, overlap, and correctness on boundary data.
7. Understand limitations regarding window size, source elements, infinite streams, parallel processing, and I/O sources.

## 2. JDK version requirements

Stream Gatherers went through the following stages:

| Version | Status | Notes |
| --- | --- | --- |
| Java 8–21 | No standard Stream Gatherers API | Use loops, stateful data structures, or other algorithms. |
| Java 22 | First preview (JEP 461) | Must enable preview when compiling/running; do not treat the API as stable. |
| Java 23 | Second preview (JEP 473) | Still requires enabling preview; details may differ from the previous preview. |
| **Java 24 and later** | **Official (JEP 485)** | `Stream.gather` and `java.util.stream.Gatherers` are available without `--enable-preview`. |

All code snippets with `Gatherers.windowSliding` in this lesson, unless noted otherwise, use **Java 24+**.

Save the file as `SlidingWindowDemo.java` and use JDK 24:

```text
javac SlidingWindowDemo.java
java SlidingWindowDemo
```

If multiple JDKs are installed, check `java -version` and `javac -version` to confirm both compiler and runtime support the API. A project configured with `--release 17` or `--release 21` **cannot** call the Java 24 API, even when running the compiler from a newer JDK.

**Do not confuse Java 16 with Java 24:** `Stream.toList()` and `mapMulti` have existed since Java 16, whereas `Stream.gather` and the built-in gatherers were standardized in Java 24.

## 3. The sliding window concept

Suppose we have data in encounter order:

```text
[10, 20, 30, 40, 50]
```

With window size `k = 3`:

```text
Source:        10   20   30   40   50
Window 1:     [10   20   30]
Window 2:          [20   30   40]
Window 3:               [30   40   50]
```

Output:

```text
[
  [10, 20, 30],
  [20, 30, 40],
  [30, 40, 50]
]
```

Each subsequent window:

- Drops **the earliest element** of the previous window.
- Keeps the remaining `k - 1` elements.
- Adds **the next element** from the source.

Therefore, **the step size of the built-in gatherer is 1 element**. Do not mistake `windowSize = 3` for jumping forward three elements each time.

### 3.1. Overlap

Two adjacent full-sized windows of size `k` **share `k - 1` elements**:

```text
[10, 20, 30]
     [20, 30, 40]
       └─────┘
       Shared: 20, 30
```

In the example, a value like `30` appears in three windows. This is **correct for the sliding-window problem**, not a duplicate-data bug in Stream.

### 3.2. Window size and window count

Let:

- `n` be the finite number of source elements.
- `k` be `windowSize`, required `k >= 1`.

Number of windows produced:

\[
W(n,k)=
\begin{cases}
0, & n=0\\
1, & 0<n<k\\
n-k+1, & n\ge k
\end{cases}
\]

Scenarios:

| Source | `k` | Window result | Window count |
| --- | ---: | --- | ---: |
| `[]` | 3 | `[]` | 0 |
| `[1]` | 3 | `[[1]]` | 1 |
| `[1,2]` | 3 | `[[1,2]]` | 1 |
| `[1,2,3]` | 3 | `[[1,2,3]]` | 1 |
| `[1,2,3,4]` | 3 | `[[1,2,3],[2,3,4]]` | 2 |
| `[1,2,3]` | 1 | `[[1],[2],[3]]` | 3 |

**Special point:** if `0 < n < k`, the API emits **exactly one short window** containing all available elements, instead of emitting 0 windows. If `n >= k`, it emits only full windows of size `k`, **without emitting extra short trailing windows**.

This is an important distinction when computing statistics: a short window may not meet the minimum sample count requirement. When the business logic only accepts full-length windows, filter by `window.size() == k`.

## 4. First example: `gather` then `toList`

Core call:

```java
Stream<T> source = ...;

Stream<List<T>> windows =
    source.gather(Gatherers.windowSliding(k));
```

`Gatherers.windowSliding(k)` is a `Gatherer<T, ?, List<T>>`. When applied with `gather`, each element of the **output stream** is a **`List<T>` containing one window**.

Complete Java 24+ example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class SlidingWindowDemo {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(
                10, 20, 30, 40, 50)
            .gather(Gatherers.windowSliding(3))
            .toList();

        windows.forEach(System.out::println);
    }
}
```

Output:

```text
[10, 20, 30]
[20, 30, 40]
[30, 40, 50]
```

Pipeline breakdown:

1. `Stream.of(...)` provides a source with encounter order.
2. `Gatherers.windowSliding(3)` creates a gatherer of size three.
3. `gather(...)` emits windows in encounter order.
4. `toList()` consumes the windows, producing `List<List<Integer>>`.

Both `gather` and subsequent intermediate transformations can combine with `filter`, `map`, `limit`, and terminal operations. `toList` is not a mandatory part of `windowSliding`; it is simply a way to clearly observe the windows.

### 4.1. Placing `map` after `gather`

`gather` changes the type from `Stream<Integer>` to `Stream<List<Integer>>`. Therefore, a subsequent `map` receives **a window list**, no longer individual source numbers:

```java
List<Integer> sums = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream()
        .mapToInt(Integer::intValue)
        .sum())
    .toList();

System.out.println(sums); // [6, 9, 12]
```

The sums correspond respectively to `[1,2,3]`, `[2,3,4]`, and `[3,4,5]`.

### 4.2. Placing `map` before `gather`

```java
List<List<Integer>> squares = Stream.of(1, 2, 3, 4)
    .map(n -> n * n)
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(squares);
// [[1, 4], [4, 9], [9, 16]]
```

These are **windows over transformed values**. If transforming each element is an independent step, placing it before the gatherer can be more suitable than repeating the transformation on the same element across multiple windows.

## 5. Input precondition: `windowSize`

The API requires `windowSize >= 1`.

```java
import java.util.stream.Gatherers;

var gatherer = Gatherers.windowSliding(3); // Valid.

// Gatherers.windowSliding(0);  // IllegalArgumentException.
// Gatherers.windowSliding(-2); // IllegalArgumentException.
```

`windowSize = 1` is valid: each element becomes a single-element window.

```java
List<List<String>> windows = Stream.of("A", "B", "C")
    .gather(Gatherers.windowSliding(1))
    .toList();

System.out.println(windows); // [[A], [B], [C]]
```

If accepting window size from a user, an application API should also check a **reasonable upper bound**, not just positivity:

```java
static int validateWindowSize(int size) {
    if (size < 1 || size > 10_000) {
        throw new IllegalArgumentException(
            "windowSize must be in [1, 10000]");
    }
    return size;
}
```

The limit 10,000 is an **application policy example**, not a mandatory JDK limit. A reasonable bound depends on records, memory, resources, and processing time.

### 5.1. Empty source and insufficient-sample source

```java
System.out.println(
    Stream.<Integer>empty()
        .gather(Gatherers.windowSliding(3))
        .toList()
); // []

System.out.println(
    Stream.of(5, 10)
        .gather(Gatherers.windowSliding(3))
        .toList()
); // [[5, 10]]
```

If the application computes a moving average only when at least three samples exist, do not take the average of `[5,10]` and present it as a three-sample average. There are two options:

- Return the short window along with the actual sample count.
- Filter out windows with fewer than `k` elements.

```java
int k = 3;

List<List<Integer>> full = Stream.of(5, 10)
    .gather(Gatherers.windowSliding(k))
    .filter(window -> window.size() == k)
    .toList();

System.out.println(full); // []
```

On a source with `n >= k`, all emitted windows already have full size; this filter mainly expresses **the business requirement** when the source is too short.

## 6. Windows are unmodifiable `List`s

Per the `Gatherers.windowSliding` contract, **each window is an unmodifiable list**. Its contents cannot be modified via `add`, `remove`, or `set`:

```java
List<Integer> window = Stream.of(1, 2, 3)
    .gather(Gatherers.windowSliding(2))
    .findFirst()
    .orElseThrow();

System.out.println(window); // [1, 2]

try {
    window.add(99);
} catch (UnsupportedOperationException expected) {
    System.out.println("Window is unmodifiable");
}
```

No specific implementation class or serializability is guaranteed for these lists. Do not cast to `ArrayList` or rely on the class name printed by the JVM.

### 6.1. If you genuinely need a modifiable copy

```java
import java.util.ArrayList;

List<List<Integer>> mutableWindows = Stream.of(1, 2, 3, 4)
    .gather(Gatherers.windowSliding(2))
    .map(ArrayList::new)
    .toList();

mutableWindows.get(0).add(99);
System.out.println(mutableWindows.get(0)); // [1, 2, 99]
```

Note: **the outer `toList()` also returns an unmodifiable list**. In the example, you can mutate **the inner `ArrayList`s**, but you cannot call `mutableWindows.add(...)`. If you also need to mutate the outer list, collect with `collect(Collectors.toCollection(ArrayList::new))`.

### 6.2. Unmodifiable does not mean deep immutable

If windows contain objects with mutable fields, mutating **the referenced object** will still be visible through the window:

```java
class Box {
    int value;
    Box(int value) { this.value = value; }
}

Box a = new Box(1);
Box b = new Box(2);

List<Box> window = Stream.of(a, b)
    .gather(Gatherers.windowSliding(2))
    .findFirst()
    .orElseThrow();

a.value = 42;
System.out.println(window.get(0).value); // 42
```

An unmodifiable window is **structurally immutable as a list**; it does not automatically deep-copy elements. For accounting, measurement, or audit data, consider immutable element types or deep snapshots per system policy.

## 7. Comparing `windowSliding` with `windowFixed`

Java 24 has two built-in window gatherers:

| Criterion | `windowSliding(k)` | `windowFixed(k)` |
| --- | --- | --- |
| Partitioning style | Overlapping windows, step size 1 | Consecutive non-overlapping groups |
| Window size | `k` if enough data | `k`, final window may be shorter |
| Source shorter than `k`, non-empty | **One short window** | **One short window** |
| Empty source | No windows | No windows |
| Example `[1..7], k=3` | `[1,2,3]`, `[2,3,4]`, `[3,4,5]`, `[4,5,6]`, `[5,6,7]` | `[1,2,3]`, `[4,5,6]`, `[7]` |
| Purpose | Observing variation across adjacent points | Processing data in independent batches |

Comparison program:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class CompareWindows {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 7)
            .boxed()
            .toList();

        System.out.println(source.stream()
            .gather(Gatherers.windowSliding(3))
            .toList());
        // [[1, 2, 3], [2, 3, 4], [3, 4, 5],
        //  [4, 5, 6], [5, 6, 7]]

        System.out.println(source.stream()
            .gather(Gatherers.windowFixed(3))
            .toList());
        // [[1, 2, 3], [4, 5, 6], [7]]
    }
}
```

**Common mistake:** using `windowFixed` to compute a moving average, which causes non-overlapping segments and skips many adjacent combinations of elements.

## 8. General formulas for window count and coverage

When a finite source has `n >= k >= 1`, full windows start successively at indices:

```text
0, 1, 2, ..., n - k
```

The `i`-th window in 0-based indexing covers the index range:

```text
[i, i + 1, ..., i + k - 1]
```

Number of full windows:

```text
n - k + 1
```

When `n = 0`, there are no windows; when `0 < n < k`, there is one short window. This formula is very useful for writing **tests across many values of k**, especially k = 1, k = n, and k > n.

Example `n = 5` and `k = 3`:

```text
Window 0: elements 0, 1, 2
Window 1: elements 1, 2, 3
Window 2: elements 2, 3, 4
Total: 5 - 3 + 1 = 3 windows.
```

If a downstream pipeline takes only two windows via `limit(2)`, the result is still **the first two windows in encounter order**, not the first two elements of the source.

## 9. Practical problem 1: computing a moving average

Given a sequence of measurements:

```text
[10, 12, 14, 16, 18, 20]
```

With `k = 3`:

```text
[10,12,14] -> 12.0
[12,14,16] -> 14.0
[14,16,18] -> 16.0
[16,18,20] -> 18.0
```

Java 24+ example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class MovingAverage {
    public static void main(String[] args) {
        int windowSize = 3;

        List<Double> averages = Stream.of(
                10, 12, 14, 16, 18, 20)
            .gather(Gatherers.windowSliding(windowSize))
            .filter(window -> window.size() == windowSize)
            .map(window -> window.stream()
                .mapToDouble(Integer::doubleValue)
                .average()
                .orElseThrow())
            .toList();

        System.out.println(averages);
        // [12.0, 14.0, 16.0, 18.0]
    }
}
```

Here:

1. `gather` creates adjacent windows.
2. `filter` ensures there are always three samples when computing.
3. `mapToDouble` avoids creating extra boxed `Double`s during aggregation.
4. `average` is a terminal operation **on each window's stream**, returning `OptionalDouble`.
5. `orElseThrow` is safe because every retained window has at least three elements.

This approach is simple and readable, though each window iterates over `k` elements to sum them. With large `n` and large `k`, total work can be roughly **O(n × k)** instead of O(n). When strict optimization is required, you can use a controlled stateful **rolling sum** algorithm; do not assume using windows is automatically the fastest approach.

### 9.1. Is a short window averaged?

```java
List<Double> averages = Stream.of(10, 20)
    .gather(Gatherers.windowSliding(3))
    .map(w -> w.stream()
        .mapToDouble(Integer::doubleValue)
        .average()
        .orElseThrow())
    .toList();

System.out.println(averages); // [15.0]
```

This is the average **of the two available samples**, not a three-sample moving average. If the system only publishes results when three samples exist, add `filter(w -> w.size() == 3)` to return an empty list for this source.

### 9.2. Floating-point error and value ranges

`DoubleStream.average()` returns a floating-point value; when handling monetary data, floating-point precision may not meet requirements. Consider `BigDecimal` and explicit rounding rules. Converting large integers to `double` can lose precision for integers exceeding the exact representation range.

For long sequences, computing the average independently per window can be suitable for learning and testing; high-performance requirements should be measured on real workloads and compared against an incremental sum-updating algorithm.


## 10. Practical problem 2: difference between two consecutive samples

A window of size 2 is a natural way to compare the current element with the element immediately preceding it.

Source:

```text
[100, 105, 103, 110]
```

Pairs and differences:

```text
[100,105] -> +5
[105,103] -> -2
[103,110] -> +7
```

Example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class ConsecutiveDeltas {
    public static void main(String[] args) {
        List<Integer> delta = Stream.of(100, 105, 103, 110)
            .gather(Gatherers.windowSliding(2))
            .filter(window -> window.size() == 2)
            .map(window -> window.get(1) - window.get(0))
            .toList();

        System.out.println(delta); // [5, -2, 7]
    }
}
```

The subtraction `window.get(1) - window.get(0)` represents the change from **the previous element to the next element**. If there is only one sample, the gatherer may produce a window `[100]`; `filter(window -> window.size() == 2)` prevents `IndexOutOfBoundsException`.

### 10.1. Detecting sudden spikes

```java
boolean hasJump = Stream.of(100, 105, 103, 140)
    .gather(Gatherers.windowSliding(2))
    .filter(window -> window.size() == 2)
    .anyMatch(window ->
        window.get(1) - window.get(0) > 20);

System.out.println(hasJump); // true
```

`anyMatch` is a short-circuiting terminal operation: it can finish as soon as a matching pair is detected. When attaching I/O or side effects to a pipeline, never assume all source elements have been traversed or callbacks were invoked an exact number of times.

### 10.2. Returning both positions and deltas

`gather` creates windows, **not automatic window-start indices**. You can index the input beforehand:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

record Sample(int index, int value) {}

record Change(int fromIndex, int toIndex, int delta) {}

List<Change> changes = IntStream.range(0, 4)
    .mapToObj(i -> new Sample(
        i, new int[] {100, 105, 103, 110}[i]))
    .gather(Gatherers.windowSliding(2))
    .filter(window -> window.size() == 2)
    .map(window -> new Change(
        window.get(0).index(),
        window.get(1).index(),
        window.get(1).value() - window.get(0).value()))
    .toList();

System.out.println(changes);
// [Change[fromIndex=0, toIndex=1, delta=5],
//  Change[fromIndex=1, toIndex=2, delta=-2],
//  Change[fromIndex=2, toIndex=3, delta=7]]
```

This illustrative snippet belongs inside an appropriate **Java 24+** class or source file; `record` has existed since Java 16. For reusability and to avoid allocating the array repeatedly, production code should declare the source once and index into it.

A simpler version when you only need to know which segments changed is storing the windows or delta values without necessarily creating a new record per pair.

## 11. Practical problem 3: generating n-grams in text processing

An **n-gram** is a sequence of `n` adjacent tokens. Given the words:

```text
["learn", "java", "stream", "api"]
```

Bigrams (`n = 2`) are:

```text
["learn java", "java stream", "stream api"]
```

Trigrams (`n = 3`):

```text
["learn java stream", "java stream api"]
```

Using `windowSliding`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class NgramDemo {
    public static void main(String[] args) {
        List<String> tokens = List.of(
            "learn", "java", "stream", "api"
        );

        List<String> bigrams = tokens.stream()
            .gather(Gatherers.windowSliding(2))
            .map(window -> String.join(" ", window))
            .toList();

        List<String> trigrams = tokens.stream()
            .gather(Gatherers.windowSliding(3))
            .map(window -> String.join(" ", window))
            .toList();

        System.out.println(bigrams);
        System.out.println(trigrams);
    }
}
```

Output:

```text
[learn java, java stream, stream api]
[learn java stream, java stream api]
```

### 11.1. Fewer tokens than the n-gram size

```java
List<String> shortInput = List.of("learn", "java");

System.out.println(
    shortInput.stream()
        .gather(Gatherers.windowSliding(3))
        .map(window -> String.join(" ", window))
        .toList()
); // [learn java]
```

The result here contains **one string representing the short window**, not a valid three-token trigram.

When the business logic only accepts complete n-grams:

```java
int n = 3;

List<String> valid = shortInput.stream()
    .gather(Gatherers.windowSliding(n))
    .filter(window -> window.size() == n)
    .map(window -> String.join(" ", window))
    .toList();

System.out.println(valid); // []
```

### 11.2. Counting n-gram frequencies

```java
import java.util.Map;
import java.util.stream.Collectors;

List<String> tokens = List.of(
    "java", "stream", "api", "java", "stream", "api"
);

Map<String, Long> counts = tokens.stream()
    .gather(Gatherers.windowSliding(2))
    .map(window -> String.join(" ", window))
    .collect(Collectors.groupingBy(
        text -> text,
        Collectors.counting()
    ));

System.out.println(counts.get("java stream")); // 2
```

`groupingBy` aggregates the emitted n-grams. `windowSliding` only produces windows; it **is not a collector**.

The iteration order of entries in the resulting `Map` is not guaranteed to follow token order unless you pick an appropriate map type and follow the collector contract. If a report sorted by count or keyword is needed, sort explicitly in the next step.

## 12. Practical problem 4: detecting windows matching a condition

Suppose temperature readings (°C) in chronological order have been normalized, and an alert is required when **three consecutive samples are all greater than 38**.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class TemperatureAlert {
    public static void main(String[] args) {
        List<Double> readings = List.of(
            37.5, 38.2, 39.1, 39.3, 37.8
        );

        boolean alert = readings.stream()
            .gather(Gatherers.windowSliding(3))
            .filter(window -> window.size() == 3)
            .anyMatch(window -> window.stream()
                .allMatch(value -> value > 38.0));

        System.out.println(alert); // true
    }
}
```

The window `[38.2,39.1,39.3]` satisfies the condition. Filtering for a full three samples before `anyMatch` avoids treating an incomplete sequence as three consecutive samples.

When samples have uneven real-world timestamps, a window of three **elements** does not mean three minutes or three seconds. `windowSliding(3)` counts **element count**, not elapsed time intervals.

### 12.1. Distinguishing count-based windows from time-based windows

| Type | Example requirement | Does `windowSliding` handle it directly? |
| --- | --- | --- |
| Count-based | Three most recent values | Yes, use `windowSliding(3)`. |
| Adjacent pairs | Difference between previous and next sample | Yes, use `windowSliding(2)`. |
| Time-based | All samples within the last 5 minutes | **Not automatically**; requires checking timestamps and boundary rules. |
| Strided steps | Window of length 5, advancing by 2 each time | **Not directly**; the built-in gatherer slides one element at a time. |
| Session-based | Group until the gap between events exceeds a threshold | Requires custom state/business logic. |

If samples carry timestamps, sort by timestamp **and a tie-breaker key when timestamps collide** before using count-based windows. However, `sorted` may buffer the input data, incurring high cost or proving unsuitable for general infinite streams.

## 13. Operation order determines window meaning

Windows are formed on **the stream of elements at the exact position where the gatherer appears in the pipeline**. Reordering operations can make adjacent source data become **non-adjacent** in the output, or vice versa.

### 13.1. Filtering before windowing

```java
List<List<Integer>> result = Stream.of(1, 2, 3, 4, 5)
    .filter(n -> n % 2 == 1)
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(result);
// [[1, 3], [3, 5]]
```

Because `filter` removes even numbers first, `1` and `3` are considered adjacent **in the filtered stream**, even though they were not adjacent in the original source.

### 13.2. Windowing before filtering

```java
List<List<Integer>> result = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(2))
    .filter(window -> window.get(0) % 2 == 1)
    .toList();

System.out.println(result);
// [[1, 2], [3, 4]]
```

These are adjacent pairs of the **original data**, then only pairs starting with an odd element are kept. The two pipelines are **not equivalent**.

Selection rule:

- If you want windows over **already selected elements**: `filter(...).gather(...)`.
- If you want to preserve adjacency **in the original sequence** and then evaluate windows: `gather(...).filter(...)`.

### 13.3. Sorting before `gather`

```java
List<List<Integer>> byValue = Stream.of(9, 1, 7, 2)
    .sorted()
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(byValue);
// [[1, 2], [2, 7], [7, 9]]
```

The pipeline forms windows in **ascending value order**, not the original occurrence order `9,1,7,2`. For time-series events, if the source is already chronologically ordered, sorting by measured value destroys the temporal relationship.

### 13.4. `limit` before and after gatherer

```java
List<List<Integer>> firstFourSource = Stream.of(
        1, 2, 3, 4, 5, 6)
    .limit(4)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(firstFourSource);
// [[1, 2, 3], [2, 3, 4]]
```

`limit(4)` caps the source to four elements before forming windows.

```java
List<List<Integer>> firstTwoWindows = Stream.of(
        1, 2, 3, 4, 5, 6)
    .gather(Gatherers.windowSliding(3))
    .limit(2)
    .toList();

System.out.println(firstTwoWindows);
// [[1, 2, 3], [2, 3, 4]]
```

The two examples happen to produce the same output on this dataset, yet **their meanings differ**. If `limit(4)` before gather is changed to `limit(3)`, only one full window remains. If `limit(2)` after gather is changed to `limit(3)`, three windows are returned.

Do not conclude that `limit(2)` after gather guarantees the source is only read for four elements: the runtime may perform buffering or maintain intermediate state; the important contract is **the number of resulting windows**.

## 14. Sliding windows on infinite streams

An application may process a continuously generated stream of values. `Stream.iterate` creates a potentially infinite source:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(4)
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6]]
```

`limit(4)` **after the gatherer** gives the terminal operation a finite result. Removing both `limit` and any source termination condition makes `toList` attempt to collect infinitely many windows, which cannot finish in finite memory.

### 14.1. Enough elements are needed before the first window appears

With `windowSize = 3`, the gatherer must receive three elements before emitting the first full window. If a finite source ends before then, it emits a single short window when the source completes.

Therefore:

- With a source that never emits `k` elements **and never terminates**, you cannot assume a window will arrive promptly.
- With a finite source having fewer than `k` elements, when traversal ends, there is one short window.
- `findFirst` on a gatherer pipeline may need to read enough data to form the first window.

This is the difference between **latency to obtain the first window** and **cost of collecting all results**.

### 14.2. Do not create infinite sliding windows and sort them all

```java
// NOT RECOMMENDED for an infinite source:
// Stream.iterate(1, n -> n + 1)
//     .gather(Gatherers.windowSliding(3))
//     .sorted(comparator)
//     .limit(1)
//     .toList();
```

`sorted` is a stateful operation that may need to see all data before emitting a value. Placing `limit` afterward does not turn an infinite problem into a finite one. Whenever sorting is required, explicitly bound input size and resources.

## 15. When data has groups, avoid windows crossing group boundaries

Suppose a system has two sensor devices, each with its own time series:

```text
Device A: [10, 11, 12]
Device B: [50, 51, 52]
```

If concatenated into `[10,11,12,50,51,52]` and passed to `windowSliding(3)`, windows `[11,12,50]` and `[12,50,51]` will **mix readings from two devices**.

A correct approach is to apply the gatherer **separately within each group**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Gatherers;

Map<String, List<Integer>> readings = new LinkedHashMap<>();
readings.put("A", List.of(10, 11, 12));
readings.put("B", List.of(50, 51, 52));

readings.forEach((device, values) -> {
    List<List<Integer>> windows = values.stream()
        .gather(Gatherers.windowSliding(3))
        .toList();

    System.out.println(device + ": " + windows);
});
```

Output:

```text
A: [[10, 11, 12]]
B: [[50, 51, 52]]
```

The example uses `LinkedHashMap` so the printing order of groups is easy to verify. With `HashMap`, device iteration order is not guaranteed. If data carries separate timestamps, sort elements **inside each group** according to business order before windowing.

In a larger pipeline, you might use `Collectors.groupingBy` first and then process the groups, while remaining aware of the cost of **holding every group's list in memory**. A Gatherer only sees the source stream; it does not automatically infer device, user, or session boundaries.

### 15.1. When the dataset changes during traversal

Functions in a Stream should be **non-interfering**: do not modify the source collection while traversal is underway. If other threads might update a sensor list, use a snapshot, synchronization, or a source supporting concurrency per contract.

`windowSliding` needs to maintain adjacency in encounter order, so mutating the source during traversal can leave windows without stable data meaning. The gatherer itself does not create an immutable snapshot of the whole system.


## 16. Parallelization: correct results do not mean faster execution

You can place `parallel()` on an ordered source:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 6)
    .boxed()
    .parallel()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6]]
```

Although the input can be processed in parallel mode, sliding windows depend on **boundaries between adjacent elements**. Splitting the source into independent segments must handle overlapping elements at boundaries; not every gatherer has a combiner that merges state in parallel efficiently.

What is required is **logically correct results in encounter order** of an ordered source. There is no guarantee that:

- Each window is built by a separate thread.
- Each source segment can be processed completely independently without coordination.
- More CPU cores always make `windowSliding` faster.
- `parallel()` is implemented with the exact same strategy on every JDK.

For a stateful window gatherer, parallel execution can incur **coordination and ordering overhead**, so a sequential pipeline is sometimes faster. Do not infer performance from the word `parallel()`.

### 16.1. Comparing sequential and parallel semantics

```java
List<Integer> source = IntStream.range(0, 100)
    .boxed()
    .toList();

List<List<Integer>> sequential = source.stream()
    .gather(Gatherers.windowSliding(5))
    .toList();

List<List<Integer>> parallel = source.parallelStream()
    .gather(Gatherers.windowSliding(5))
    .toList();

System.out.println(sequential.equals(parallel)); // true
```

Checking with `List.equals` compares **all contents and window ordering**. Do not test using thread IDs, log order, or completion timing of individual callbacks.

### 16.2. `unordered()` loses stable adjacency semantics

```java
List<List<Integer>> windows = IntStream.rangeClosed(1, 6)
    .parallel()
    .unordered()
    .boxed()
    .gather(Gatherers.windowSliding(3))
    .toList();
```

Here the pipeline has **dropped the encounter-order requirement**. You should not assume windows reflect `[1,2,3,4,5,6]` in business order. One run happening to return the expected result does not constitute an API guarantee.

For time-series data, transaction sequences, logs, or positionally meaningful records, **preserve source order** or sort by an explicit key before windowing.

## 17. Memory, complexity, and resources

Sliding windows have high overlap: when `n >= k`, there are `n - k + 1` windows and each window logically holds `k` element references.

If **all windows** are collected into a `List<List<T>>`, the number of element slots represented across windows scales as:

```text
k * (n - k + 1)
```

For example, `n = 100_000` and `k = 1_000`: there are about 99,001 windows, totaling nearly 99 million element positions across windows. You **should not** treat each window as free independent data.

JDK implementations may use different storage or memory-sharing strategies, so do not infer from this formula that actual allocations always equal that exact object count. Business-wise, however, **retaining all windows** creates high memory pressure compared to **computing a statistic and discarding the window**.

### 17.1. Do not collect windows if you only need statistics

Instead of:

```java
List<List<Integer>> windows = source.stream()
    .gather(Gatherers.windowSliding(100))
    .toList();

// Then compute statistics in another loop.
```

You can process directly:

```java
List<Double> averages = source.stream()
    .gather(Gatherers.windowSliding(100))
    .filter(window -> window.size() == 100)
    .map(window -> window.stream()
        .mapToDouble(Integer::doubleValue)
        .average()
        .orElseThrow())
    .toList();
```

The second pipeline keeps only **the output averages**, not the entire list of windows in the result. However, recomputing the average of each window still loops through up to 100 elements; when genuine optimization is needed, you can compute a **rolling sum** with properly managed state.

### 17.2. Very large window size on a short source

The API documentation notes that for efficiency, windows **may be allocated eagerly or ahead of demand**. Thus requesting `windowSliding(1_000_000)` on a stream with only a few elements still **risks large memory consumption** during evaluation.

Set an upper limit for `windowSize` based on system configuration and actual record size. Do not treat a downstream `limit(1)` as a guarantee that total memory usage stays small.

### 17.3. Sources backed by I/O must be closed

If data comes from `Files.lines`, `Files.walk`, or another I/O resource, the `toList` terminal operation itself **does not replace closing the source**. Java 24+ example:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

static List<List<String>> adjacentLines(Path file)
        throws IOException {

    try (Stream<String> lines = Files.lines(
            file, StandardCharsets.UTF_8)) {

        return lines
            .gather(Gatherers.windowSliding(2))
            .toList();
    }
}
```

`try-with-resources` closes `lines` when done or when an error occurs. The result consists of lists holding the already-read strings, independent of keeping the I/O stream open.

Do not read an entire huge file and hold every pair of lines if you only need to check a condition on them. Choose a suitable terminal operation or reduce to a smaller result while the stream is open.

### 17.4. Mutating the source during traversal

If another thread alters the structure of a source such as an `ArrayList` while the stream is traversing it, results are not guaranteed. `windowSliding` does not snapshot the entire collection before reading.

For reproducible reporting, use a stable source or a dataset snapshot per session. If elements are mutable objects, decide whether deep copying is needed; an unmodifiable window list does not automatically protect the state of those objects.

## 18. Complete verification program (Java 24+)

To verify semantics, we create a **reference algorithm** using `List.subList` on a finite source, then compare it against `windowSliding` across many values of `n` and `k`.

This method avoids checking just a couple of sample sequences and jumping to conclusions. It tests:

- Empty source.
- Source with fewer elements than window size.
- `k = 1`, `k = n`, `k > n`.
- Window count and contents of each window.
- Equivalence between sequential and parallel streams.
- Rejection of invalid window sizes.
- Unmodifiability of returned windows.
- Duplicate data preserved the exact number of times.

Create `SlidingWindowCheck.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class SlidingWindowCheck {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static <T> List<List<T>> expected(
            List<T> source, int k) {

        if (k < 1) {
            throw new IllegalArgumentException("k must be >= 1");
        }

        List<List<T>> result = new ArrayList<>();

        if (source.isEmpty()) {
            return result;
        }

        if (source.size() < k) {
            result.add(new ArrayList<>(source));
            return result;
        }

        for (int i = 0; i <= source.size() - k; i++) {
            result.add(new ArrayList<>(
                source.subList(i, i + k)));
        }

        return result;
    }

    static <T> void verify(List<T> source, int k) {
        List<List<T>> reference = expected(source, k);

        List<List<T>> sequential = source.stream()
            .gather(Gatherers.windowSliding(k))
            .toList();

        List<List<T>> parallel = source.parallelStream()
            .gather(Gatherers.windowSliding(k))
            .toList();

        check(sequential.equals(reference),
            "Mismatch with reference: source=" + source + ", k=" + k);

        check(parallel.equals(reference),
            "Mismatch in parallel: source=" + source + ", k=" + k);

        int n = source.size();
        int expectedCount = n == 0 ? 0
            : n < k ? 1
            : n - k + 1;

        check(sequential.size() == expectedCount,
            "Incorrect window count");

        for (List<T> window : sequential) {
            check(!window.isEmpty(), "Unexpected empty window");
            check(window.size() <= k, "Exceeded size k");
        }
    }

    public static void main(String[] args) {
        for (int n = 0; n <= 10; n++) {
            List<Integer> source = IntStream.range(0, n)
                .boxed()
                .toList();

            for (int k = 1; k <= 12; k++) {
                verify(source, k);
            }
        }

        verify(Arrays.asList(1, 1, 2, 2, 1, 1), 3);
        verify(Arrays.asList(7, 7), 5);

        boolean rejectedZero = false;
        try {
            Gatherers.windowSliding(0);
        } catch (IllegalArgumentException expected) {
            rejectedZero = true;
        }
        check(rejectedZero, "Must reject windowSize=0");

        boolean rejectedNegative = false;
        try {
            Gatherers.windowSliding(-1);
        } catch (IllegalArgumentException expected) {
            rejectedNegative = true;
        }
        check(rejectedNegative,
            "Must reject negative windowSize");

        List<Integer> first = List.of(1, 2, 3).stream()
            .gather(Gatherers.windowSliding(2))
            .findFirst()
            .orElseThrow();

        boolean rejectedModification = false;
        try {
            first.add(99);
        } catch (UnsupportedOperationException expected) {
            rejectedModification = true;
        }
        check(rejectedModification,
            "Window must be unmodifiable");

        System.out.println("PASS: windowSliding");
    }
}
```

Expected output when all checks pass:

```text
PASS: windowSliding
```

This program is a **semantic verification template**, not a performance benchmark or proof that the system handles every scale. In particular, testing on sources with duplicate values prevents bugs from comparing only as a `Set` and ignoring occurrence counts.

### 18.1. Why is an independent reference algorithm needed?

If both production code and test code call `windowSliding`, both could share the same misunderstanding of a boundary case without detecting it. The `expected` function above uses:

- An index loop.
- `subList(i, i + k)`.
- Separate conditions for an empty source and a source shorter than the window.

Thanks to a different implementation, it helps verify exact positions, lengths, and window counts against the defined rules. For larger inputs, *property-based testing* can be added, though you should not generate millions of windows just to test with `toList`.

## 19. Common errors and misconceptions

| Misconception / error | Consequence | Fix |
| --- | --- | --- |
| Thinking `windowSliding(3)` takes three elements then jumps three elements | Produces the wrong window type | Each window slides by **one element** and overlaps `k - 1`. |
| Using `windowFixed` to compute a moving average | Non-overlapping segments | Use `windowSliding` when all consecutive segments are needed. |
| Assuming a source shorter than `k` has no windows | Misses one short window | Check `0 < n < k`. |
| Assuming short trailing windows are always emitted at the end | Miscounts windows | When `n >= k`, only windows of **full k** are emitted. |
| Accessing `window.get(k - 1)` on a short source | `IndexOutOfBoundsException` | Filter `window.size() == k` when full samples are required. |
| Calling `windowSliding(0)` | `IllegalArgumentException` | Require `k >= 1` and a suitable upper bound. |
| Calling `window.add` or `window.set` | `UnsupportedOperationException` | Use `new ArrayList<>(window)` if mutation is truly needed. |
| Thinking an unmodifiable list makes all elements immutable | Mutable data still changes | Use immutable elements or deep snapshots. |
| Sorting by value before temporal analysis | Loses temporal adjacency | Sort by timestamp/tie-breaker or keep ordered source. |
| Calling `filter` before gather while wanting adjacent pairs of the original source | Non-adjacent elements get paired | Place gather before window filter when needed. |
| Merging two devices' data and gathering in one pass | Windows mix groups | Gather separately for each sequence/group. |
| Treating k elements as k minutes | Wrong under uneven sampling | Use a time-window algorithm when needed. |
| Collecting all windows of huge data into RAM | High memory pressure | Compute statistics in the pipeline without keeping every list. |
| Huge `windowSize` on a tiny stream | May allocate excessively | Enforce bounds according to source and resources. |
| Assuming `parallel()` speeds things up | Coordination and state overhead | Measure performance, do not infer from thread count. |
| Using `unordered()` on business-ordered data | Pairs/windows lose stable meaning | Maintain encounter order or sort. |
| Using `toList` on an unbounded infinite source | Does not finish, consumes unbounded resources | `limit` results or bound the input. |
| Source is `Files.lines` left unclosed | I/O resource leak | Use `try-with-resources`. |
| Code fails to compile on JDK 21 | Stream Gatherers are not in JDK 21 | Use JDK 24+ or an older-compatible solution. |

## 20. Practice exercises

### Exercise 1 — Computing windows manually

Given source `[2,4,6,8,10]` and `k = 3`. List all windows and the window count. Compare against `windowFixed(3)`.

### Exercise 2 — Boundary cases

Predict the result of `windowSliding(4)` on `[]`, `[1]`, `[1,2,3]`, `[1,2,3,4]`, and `[1,2,3,4,5]`.

### Exercise 3 — Sum of each window

Use `windowSliding(2)` on `[3,5,7,9]` and transform into a list of sums of consecutive pairs.

### Exercise 4 — Difference between adjacent samples

Use `windowSliding(2)` to compute differences from `[100,98,103,99]`, defined as the next value minus the previous value. If the source has only one element, what is the valid list of differences?

### Exercise 5 — Text n-grams

From `["java","stream","api","java","stream"]`, generate bigrams and count the frequency of each bigram using `groupingBy` and `counting`.

### Exercise 6 — Operation order

Given `[1,2,3,4,5]`. Compare `filter(n -> n % 2 == 1).gather(windowSliding(2))` with `gather(windowSliding(2)).filter(window -> window.get(0) % 2 == 1)`.

### Exercise 7 — Source shorter than k

An alerting system may only fire a signal if **three consecutive samples** exceed 50. If the source only has `[60,70]`, will `windowSliding(3)` produce a result? How do you prevent a false alert?

### Exercise 8 — Resource limits

A system has 100,000 samples and `k = 1,000`. Why should you not blindly collect all windows into `List<List<T>>` if only the average values are needed? Give an additional reason why an upper bound on `k` is needed.

### Exercise 9 — Choosing window type

Business requirement A needs every 100 records grouped into a non-overlapping batch for file export; business requirement B needs to analyze the 100 most recent records after each new record. Which gatherer fits each need?

### Exercise 10 — Preserving order

Why is `source.parallelStream().unordered().gather(Gatherers.windowSliding(3))` unsuitable when the source consists of chronological events? What additional criterion is needed if two events share the same timestamp?

## 21. Reference solutions

**Exercise 1.** The sliding windows are `[2,4,6]`, `[4,6,8]`, `[6,8,10]`, totaling `5 - 3 + 1 = 3`. `windowFixed(3)` produces `[2,4,6]` and `[8,10]`; the last batch is short because fewer than three elements remain.

**Exercise 2.** Results respectively: `[]`; `[[1]]`; `[[1,2,3]]`; `[[1,2,3,4]]`; `[[1,2,3,4],[2,3,4,5]]`. An empty source has no windows; a source shorter than k has one short window.

**Exercise 3.**

```java
List<Integer> sums = Stream.of(3, 5, 7, 9)
    .gather(Gatherers.windowSliding(2))
    .map(w -> w.get(0) + w.get(1))
    .toList();

System.out.println(sums); // [8, 12, 16]
```

**Exercise 4.** The differences are `[-2,5,-4]`. A single-element source produces one short window, yet has no **full two-element pair**. Filter `window.size() == 2` so the difference list is empty.

```java
List<Integer> deltas = Stream.of(100, 98, 103, 99)
    .gather(Gatherers.windowSliding(2))
    .filter(w -> w.size() == 2)
    .map(w -> w.get(1) - w.get(0))
    .toList();
```

**Exercise 5.**

```java
List<String> words = List.of(
    "java", "stream", "api", "java", "stream");

Map<String, Long> counts = words.stream()
    .gather(Gatherers.windowSliding(2))
    .map(w -> String.join(" ", w))
    .collect(java.util.stream.Collectors.groupingBy(
        text -> text,
        java.util.stream.Collectors.counting()));

System.out.println(counts.get("java stream")); // 2
```

The other bigrams are `stream api` and `api java`, each appearing once.

**Exercise 6.** Filtering odd numbers first creates source `[1,3,5]`, yielding `[[1,3],[3,5]]`. Gathering first creates pairs from the original sequence, then keeps pairs whose first element is odd: `[[1,2],[3,4]]`. Choose placement according to the business definition of "adjacent".

**Exercise 7.** `windowSliding(3)` produces **one short window `[60,70]`**. To require a full three samples, add `filter(w -> w.size() == 3)` before checking `allMatch(v -> v > 50)`.

**Exercise 8.** With 100,000 samples and k = 1,000, there are 99,001 full windows; total element positions represented across windows are roughly 99 million. Collecting all windows can consume a large amount of memory, whereas computing averages directly may retain only the aggregated numbers. The API allows windows to be allocated eagerly, so a very large `k` even on a small source carries memory risk.

**Exercise 9.** Requirement A uses `Gatherers.windowFixed(100)`, because non-overlapping batches are needed. Requirement B uses `Gatherers.windowSliding(100)`, because after each new sample a window shifted by one position is needed.

**Exercise 10.** Sliding windows rely on adjacency in encounter order; `unordered()` drops that constraint, leaving no consistent meaning of "before/after" samples. For events with identical timestamps, add a deterministic tie-breaker key such as a monotonically increasing ID or valid insertion order to establish a stable total order before gathering.

## 22. Checklist for using `windowSliding` in production systems

- [ ] JDK and toolchain support **Java 24+** if not using preview flags.
- [ ] `windowSize >= 1` and has an upper bound based on memory/resources.
- [ ] Clearly distinguish **windowSliding (slide by 1)** and **windowFixed (non-overlapping batches)**.
- [ ] Understand that an empty source produces **no windows**, and `0 < n < k` produces **one short window**.
- [ ] Explicit decision made if business logic only accepts windows of full `k`.
- [ ] Data encounter order is appropriate: timestamps, tie-breaker keys, source ordering.
- [ ] Do not drop encounter order with `unordered()` when adjacency is required.
- [ ] `filter` and `sorted` are placed in the right positions relative to `gather`.
- [ ] With multiple devices/sessions/users, do not allow windows to cross group boundaries.
- [ ] Do not mutate window lists; mutable objects inside have an explicit policy.
- [ ] Do not collect all `List<List<T>>` if only summary metrics are needed.
- [ ] Measured O(n × k) recomputation cost for statistics when `k` is large.
- [ ] For infinite sources, a stopping terminal operation or reasonable input limit is present.
- [ ] For file/I/O sources, `try-with-resources` and error handling are present.
- [ ] Do not expect `parallel()` to automatically make stateful windows faster.
- [ ] Tested k = 1, k = n, k > n, empty source, duplicate data, and ordering.
- [ ] Verified sequential/parallel results and used an independent reference algorithm.

## 23. Summary and references

`Gatherers.windowSliding(k)` concisely expresses the requirement "inspect `k` adjacent elements, shifting by one element for the next window":

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Core principles:

1. **Semantics:** windows overlap, sliding one element at a time. For a sufficiently long finite source, there are `n-k+1` windows.
2. **Boundary cases:** an empty source emits no windows; a non-empty source shorter than `k` emits **one short window**.
3. **Immutability:** each window is an unmodifiable list, which does not imply the element objects inside are also immutable.
4. **Pipeline:** `map`, `filter`, `reduce`, and `collect` can follow the gatherer; the placement of `filter`, `sorted`, and `limit` relative to the gatherer determines business semantics.
5. **Performance:** window size, output count, overlap, and statistic computation cost affect memory and speed; measure in practice.
6. **Resources and ordering:** preserve encounter order for sequential data, close I/O sources, and never assume parallelization is always beneficial.
7. **Versions:** Stream Gatherers are official starting in Java 24 (JEP 485); Java 22/23 only had preview releases.

Official reference sources:

- [Javadoc Java 24: Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html) — contract of `windowSliding`, `windowFixed`, size requirements, and result lists.
- [Oracle Java 24: Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html) — examples of using gatherers in pipelines.
- [OpenJDK JEP 485: Stream Gatherers](https://openjdk.org/jeps/485) — standardization progress of the feature.

Mastering `Gatherers.windowSliding` helps you turn many manual loops into readable, testable Java Stream API pipelines while properly controlling missing data, ordering, memory, and resources when bringing sliding-window processing into real-world applications.
