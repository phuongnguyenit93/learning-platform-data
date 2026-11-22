# Collecting Primitive Streams with Three-Argument collect

In the Java Stream API, `IntStream`, `LongStream`, and `DoubleStream` allow processing primitive values without converting each one into `Integer`, `Long`, or `Double`. Built-in terminal operations such as `sum()`, `average()`, and `summaryStatistics()` cover many statistical needs. However, when you want to **accumulate values into a custom result object**—such as multi-bucket counters, business statistics structures, lists, or formatted strings—you can use the **three-argument `collect` method**.

This lesson belongs to the **Primitive Streams** chapter of the `JAVA_STREAM_API` module. It is a form of *mutable reduction* in a lazy pipeline: the accumulator updates a result container, while the combiner merges partial results from separate processing segments, which is especially important for parallel streams. We will learn how to design the three functions `supplier`, `accumulator`, and `combiner` according to contract, distinguish this from `Collectors` on `Stream<T>`, and recognize limits regarding state, overflow, resources, and performance.

## 1. Why do primitive Streams have their own collect?

Java has three primary primitive Stream types:

| Stream Type | Element | Accumulator function used in `collect` |
| --- | --- | --- |
| `IntStream` | `int` | `ObjIntConsumer<R>` |
| `LongStream` | `long` | `ObjLongConsumer<R>` |
| `DoubleStream` | `double` | `ObjDoubleConsumer<R>` |

General signature of `IntStream.collect`:

```java
<R> R collect(
        Supplier<R> supplier,
        ObjIntConsumer<R> accumulator,
        BiConsumer<R, R> combiner
)
```

For `LongStream` and `DoubleStream`, `ObjIntConsumer<R>` is replaced by `ObjLongConsumer<R>` and `ObjDoubleConsumer<R>`, respectively. All three methods have been available since **Java 8**.

The three components have independent responsibilities:

1. **`supplier`**: creates **a new, empty result object** of type `R`, such as `new ArrayList<>()`, `new long[10]`, or `new Stats()`.
2. **`accumulator`**: receives **the current `R` object and a primitive value**, then updates the object. It returns `void`, e.g., `(list, n) -> list.add(n)`.
3. **`combiner`**: receives **two independently accumulated result objects** and merges the second result **into the first object**. It also returns `void`, e.g., `(left, right) -> left.addAll(right)`.

```text
IntStream: 3, 5, 7, 9
             │
             ▼
   collect(supplier, accumulator, combiner)
             │
     ┌───────┴────────┐
     ▼                ▼
 supplier()        supplier()
  Stats A            Stats B
     │                │
  add(3), add(5)  add(7), add(9)
     │                │
     └── combine(A, B)┘
             │
             ▼
      Aggregated Stats
```

The diagram illustrates one **possible** way data may be partitioned during parallel execution; Java does not guarantee always creating exactly two accumulators or splitting data this way. During sequential execution, `combiner` may never be called.

**Key distinction:** `IntStream` does not have a `collect(Collector)` overload like `Stream<T>`. The syntax `IntStream.range(0, 5).collect(Collectors.toList())` **will not compile**. If you want to use `Collectors.toList()` or `Collectors.groupingBy()`, convert to `Stream<Integer>` via `boxed()`, or use `mapToObj(...)` if mapping to another object type is needed.

## 2. First example: collecting int values into List<Integer>

The easiest example to understand collects all integers into an `ArrayList<Integer>`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.rangeClosed(1, 5)
        .collect(
                () -> new ArrayList<Integer>(),
                (list, n) -> list.add(n),
                (left, right) -> left.addAll(right)
        );

System.out.println(numbers); // [1, 2, 3, 4, 5]
```

Matching each line against the contract:

- `() -> new ArrayList<Integer>()` creates a separate list for accumulation.
- `(list, n) -> list.add(n)` adds an `int` to the list, **boxing** it into `Integer` since `List<Integer>` stores objects.
- `(left, right) -> left.addAll(right)` merges two lists; no list needs to be returned because `BiConsumer` returns `void`.

Using method references is shorter, while lambdas make the two arguments of `accumulator` and `combiner` explicit. You can pick a concrete type like `ArrayList<Integer>` as the target if you want to avoid generic type inference ambiguity.

If the goal is merely keeping all primitive `int` values, `toArray()` expresses intent more directly and avoids boxing:

```java
int[] primitiveValues = IntStream.rangeClosed(1, 5).toArray();
System.out.println(java.util.Arrays.toString(primitiveValues));
// [1, 2, 3, 4, 5]
```

Do not use `collect` just because you can; start from the result you want to represent. `List<Integer>` requires objects; `int[]` and numeric terminal operations can save memory and boxing overhead in many cases.

## 3. What contract must the three parameters satisfy for parallel processing?

`collect` is *mutable reduction*. It allows creating multiple local containers, feeding elements into each container, and merging them into a combined result. For results to remain correct when the number and partitioning of branches vary, the three functions must satisfy the following properties.

### 3.1. Supplier creates a new object on every call

Right:

```java
() -> new ArrayList<Integer>()
```

Wrong:

```java
List<Integer> shared = new ArrayList<>();

// WRONG: every supplier invocation returns the exact same object.
() -> shared
```

If the supplier returns the same container, parallel branches can write to the same thread-unsafe object; even without a race, merging an object's contents with itself can duplicate elements. `supplier` must create an **independent container** on every invocation.

### 3.2. Accumulator mutates the container it receives

Right:

```java
(list, n) -> list.add(n)
```

Wrong when expecting to replace the result:

```java
// WRONG: reassigning the local parameter does not change the collect result.
(list, n) -> list = new ArrayList<Integer>()
```

`accumulator` is an `ObjIntConsumer<R>` and does not return `R`. Therefore, it must **mutate the state of the container object** according to `R`'s contract. Do not use an external counter outside the Stream to “hold the result” instead of the provided container.

### 3.3. Combiner merges data into the first object

Right:

```java
(left, right) -> left.addAll(right)
```

Wrong:

```java
// WRONG: reassigning local variable left; data is not merged.
(left, right) -> left = right
```

`combiner` must merge **both partial results** and preserve mathematical properties. It must not assume there is only one container or that it is always called a fixed number of times.

### 3.4. Identity and associativity

You can think of the empty container produced by `supplier` as the **identity** element. Merging with an empty container must not alter the meaning of the result. Merging three branches as `(A + B) + C` or `A + (B + C)` must produce semantically equivalent business results.

For lists combined by concatenation, the operator is **sequence concatenation**, which is associative and preserves order within each branch. For sum statistics, the merge operator must add **sum to sum** and **count to count**. Never average averages while ignoring element counts in each branch.

Furthermore, how two results are merged must be compatible with how the accumulator adds individual elements. If merging yields a different result from adding all elements sequentially into a single container, the design can break when `parallel()` is enabled.

## 4. Practical example: computing count, sum, and average in one pass

Suppose we need to count transactions, sum values, and compute the average. We can design a self-accumulating `Stats` container:

```java
import java.util.stream.IntStream;

final class Stats {
    long count;
    long sum;

    void add(int value) {
        count++;
        sum += value;
    }

    void combine(Stats other) {
        count += other.count;
        sum += other.sum;
    }

    double average() {
        return count == 0 ? Double.NaN : (double) sum / count;
    }
}

Stats stats = IntStream.of(3, 5, 7, 9)
        .collect(Stats::new, Stats::add, Stats::combine);

System.out.println(stats.count);     // 4
System.out.println(stats.sum);       // 24
System.out.println(stats.average()); // 6.0
```

Meaning of each parameter:

| Parameter | On the `Stats` container |
| --- | --- |
| `supplier` | `Stats::new` initializes `count = 0`, `sum = 0` |
| `accumulator` | `Stats::add` takes an `int`, increments `count`, and adds to `sum` |
| `combiner` | `Stats::combine` adds two counts and two sums |
| Terminal result | The merged `Stats` instance can be queried for the average |

`sum` uses `long` rather than `int` to expand the additive domain; however, **`long` can still overflow** if the total is huge. If exact precision beyond 64 bits is required, consider `BigInteger` or overflow checks as needed.

More importantly, **do not compute the average of each branch and then take the arithmetic mean of the branch averages**. For example, branches `[10, 20]` and `[100]` have averages 15 and 100, respectively. Combining them wrongly as `(15 + 100) / 2 = 57.5`; the true average of the three values is `130 / 3 ≈ 43.33`. A `(sum, count)` container merges properly first, and only then computes the final average.

### When should you use summaryStatistics()?

If you only need basic statistics for `int`, Java already provides `IntSummaryStatistics`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics s = IntStream.of(3, 5, 7, 9)
        .summaryStatistics();

System.out.println(s.getCount());   // 4
System.out.println(s.getSum());     // 24
System.out.println(s.getAverage()); // 6.0
System.out.println(s.getMin());     // 3
System.out.println(s.getMax());     // 9
```

Writing a custom `Stats` makes sense when business logic needs **extra fields or custom rules**, such as counting rejected transactions, storing a histogram, tracking days with positive revenue, or classifying by thresholds. To obtain just those five basic metrics above, `summaryStatistics()` is shorter and easier to maintain.

## 5. Grouping numbers into buckets: a histogram using long[]

This is an example where three-argument `collect` truly shines on primitive Streams. Suppose exam scores are in the range **0–100** and we want to count them across ten score buckets: 0–9, 10–19, ..., 90–100.

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] scores = {5, 12, 12, 27, 98, 100, -1, 105};

long[] histogram = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .parallel()
        .collect(
                () -> new long[10],
                (counts, score) -> {
                    int index = Math.min(score / 10, 9);
                    counts[index]++;
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(histogram));
// [1, 2, 1, 0, 0, 0, 0, 0, 0, 2]
```

Explanation:

- `supplier` allocates a **fresh counter array** initialized to zeros for each branch.
- `accumulator` determines the bucket and increments that slot. A score of 100 goes into the last bucket thanks to `Math.min`.
- `combiner` adds each slot of the right array into the left array.
- `filter` discards out-of-range values before bucketing. Dropping out-of-range scores is **this example's business rule**, not a default behavior of `collect`.

The number of buckets is small and fixed, so memory per container is `O(10)`. In parallel mode, multiple containers can exist simultaneously; creating too many branches still has overhead. The `long[]` array avoids allocating an `Integer` key on every update as a `Map<Integer,Long>` grouping would, at the trade-off of requiring known, fixed buckets upfront.

When buckets are **not** known in advance, or when grouping by complex object keys is needed, using `boxed()` or `mapToObj(...)` with `Collectors.groupingBy(...)` may be more appropriate. Do not force every problem into an array solely to avoid boxing.

## 6. Building a string result with StringJoiner

`collect` can accumulate into objects other than Lists or arrays. For example, building a comma-separated string of integers:

```java
import java.util.StringJoiner;
import java.util.stream.IntStream;

StringJoiner joined = IntStream.rangeClosed(1, 5)
        .collect(
                () -> new StringJoiner(", ", "[", "]"),
                (out, n) -> out.add(Integer.toString(n)),
                (left, right) -> left.merge(right)
        );

System.out.println(joined.toString()); // [1, 2, 3, 4, 5]
```

`StringJoiner::merge` also works as a combiner. Unlike concatenating immutable `String` values repeatedly, `StringJoiner` is a mutable object. This property fits mutable reduction. In the sequential example with encounter order, the result preserves order 1 to 5.

When `parallel` is enabled, preserving encounter order still requires the Stream to have an encounter order and the combiner to merge branches in order. Do not use `unordered()` or assume accumulator call order is the final order. If building an enormous string, consider the memory of the resulting string; primitive Streams do not eliminate text-creation costs.

## 7. Applying to LongStream and DoubleStream

The same three-argument model appears on both `LongStream` and `DoubleStream`. Example using built-in statistics objects for mutable reduction:

```java
import java.util.LongSummaryStatistics;
import java.util.stream.LongStream;

LongSummaryStatistics longStats = LongStream.of(
        10_000_000_000L,
        20_000_000_000L
).collect(
        LongSummaryStatistics::new,
        LongSummaryStatistics::accept,
        LongSummaryStatistics::combine
);

System.out.println(longStats.getCount()); // 2
System.out.println(longStats.getSum());   // 30000000000
```

With `DoubleStream`:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics doubleStats = DoubleStream.of(1.5, 2.5, 3.0)
        .collect(
                DoubleSummaryStatistics::new,
                DoubleSummaryStatistics::accept,
                DoubleSummaryStatistics::combine
        );

System.out.println(doubleStats.getCount());   // 3
System.out.println(doubleStats.getAverage()); // near 2.3333333333333335
```

Note on floating-point numbers: `double` uses finite floating-point representation. Addition is not strictly mathematically associative when rounding occurs, so sum/average results **can differ slightly** when partitioning or execution order changes, especially with very large and very small values mixed together. Even `DoubleStream.sum()` has floating-point precision limits; if business rules require exact currency in minor units or exact decimals, consider `long` minor units or `BigDecimal` with an explicit rounding policy.

Do not treat `DoubleStream.collect` as a guarantee of bit-for-bit identical results between sequential and parallel runs. The accumulator must merge cleanly, while numeric precision must be designed according to requirements.

## 8. Comparing three-argument collect with other APIs

| Need | Suitable API | Notes |
| --- | --- | --- |
| Sum `int`, `long`, or `double` | `sum()` | Concise; watch overflow and error per numeric type |
| Average of `IntStream` | `average()` | Returns `OptionalDouble` since Stream may be empty |
| Min/max | `min()` / `max()` | Returns primitive Optional type |
| Count/sum/min/max/average | `summaryStatistics()` | Built-in summary accumulator |
| Keep all elements as primitives | `toArray()` | Produces `int[]`, `long[]`, or `double[]` |
| Turn each `int` into an object then use Collector | `mapToObj(...).collect(Collectors...)` | Returns `Stream<R>` to use Collectors |
| Collect numbers into `List<Integer>` | `boxed().collect(Collectors.toList())` or 3-arg `collect(...)` | Boxing is unavoidable when creating a wrapper List |
| Fixed histogram or multiple custom metrics | `collect(supplier, accumulator, combiner)` | Full control over mutable container and merge operation |
| Grouping by flexible keys, complex downstream collectors | `boxed().collect(Collectors.groupingBy(...))` | Expressive, though incurs boxing |

Example with `Collectors` requiring type conversion:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 5)
        .boxed()
        .collect(Collectors.toList());

System.out.println(values); // [1, 2, 3, 4, 5]
```

If each number must become a specific object, `mapToObj` avoids boxing and then mapping to an object:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "item-" + n)
        .collect(Collectors.toList());

System.out.println(labels); // [item-1, item-2, item-3]
```

`Collector`s built with `Collector.of(...)` have their own parameters, can declare *characteristics*, and support downstream collecting. However, the three-argument overload on `IntStream` **does not accept a `Collector`**, and its combiner has type `BiConsumer<R,R>` instead of the `BinaryOperator<R>` commonly seen in `Collector.of`. Do not copy a combiner containing `return left` verbatim here when writing lambdas.

## 9. Critical mistakes when enabling parallel()

Parallel streams expose broken combiner designs that sequential pipelines may hide.

### Wrong: holding an external mutable container

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

// WRONG: side effects on shared from multiple branches.
IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add);
```

`ArrayList` is not protected for concurrent writes, so it can drop elements, throw exceptions, or end up in a corrupted state. Use `collect` with a supplier creating fresh containers and a proper combiner:

```java
List<Integer> safe = IntStream.range(0, 10_000)
        .parallel()
        .collect(
                () -> new ArrayList<Integer>(),
                (part, n) -> part.add(n),
                (left, right) -> left.addAll(right)
        );
```

Each branch updates its own container, and the combiner merges results. Do not use `Collections.synchronizedList` to mask a supplier returning a shared object; creating and merging properly is the real fix.

### Wrong: combiner discards the right-hand data

```java
// WRONG: combiner performs no merging at all.
IntStream.rangeClosed(1, 100)
        .parallel()
        .collect(
                () -> new long[1],
                (acc, n) -> acc[0] += n,
                (left, right) -> {}
        );
```

Sequential execution may appear to give the expected result because the combiner is never invoked, yet parallel execution can lose sums from sub-branches. Fix with `(left, right) -> left[0] += right[0]`.

### Wrong: non-associative computation

Operations such as repeated subtraction or repeated division are unsuitable for arbitrary combiners:

```java
// Semantically wrong example if trying to perform sequential subtraction:
// You cannot assume combining branch results with subtraction
// equals traversing all values in order.
```

For computing averages, quantiles, variances, ratios, or rates, store **sufficient statistics** in the container (such as `sum`, `count`, and other components), and derive the metric at the final step. If an operation has no contract-compliant merge rule, do not force parallel execution with an ad-hoc combiner.

### Overhead and source size

Even a valid combiner does not guarantee parallel execution is faster. Parallelism adds work-splitting, container-allocation, branch-merging, and CPU/memory contention costs. For a few dozen elements, a loop or sequential Stream is usually simpler; for large datasets with heavy per-element work, parallel can pay off. Measure on the real JDK and data rather than guessing from CPU core count.

## 10. Lifecycle contract: terminal collect still does not close I/O sources

`collect` is a terminal operation. Once invoked, the pipeline is consumed and cannot be reused; **however, the terminal operation does not automatically call `close()` on I/O sources**. If a primitive pipeline originates from `Files.lines`, close the file Stream at the resource-owning scope.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static Stats summarizeNumbers(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .mapToInt(Integer::parseInt)
                .collect(Stats::new, Stats::add, Stats::combine);
    }
}
```

The example assumes the file contains valid integer lines or blank lines. If a malformed line is encountered, `Integer.parseInt` throws `NumberFormatException` and `try-with-resources` still closes the file Stream. Read errors during lazy pipeline traversal may surface as `UncheckedIOException`. In real programs, state the policy for malformed lines: skip intentionally, log/record, or abort processing.

The resource resides in the **outer source Stream** created by `Files.lines`; converting to `IntStream` via `mapToInt` does not make the file release itself when `collect` finishes. Never return a closed Stream outside the `try` block for the caller to traverse later.

## 11. Combined example: exam result statistics

Requirement: from a sequence of scores that may include out-of-range values outside `0..100`, compute **valid count**, **passing count (>= 50)**, and **total valid score** in a single pass.

```java
import java.util.Arrays;

final class ExamStats {
    long valid;
    long passed;
    long totalScore;

    void accept(int score) {
        valid++;
        if (score >= 50) {
            passed++;
        }
        totalScore += score;
    }

    void combine(ExamStats other) {
        valid += other.valid;
        passed += other.passed;
        totalScore += other.totalScore;
    }

    double average() {
        return valid == 0 ? Double.NaN : (double) totalScore / valid;
    }
}

int[] input = {92, 40, 76, 51, -1, 105, 0};

ExamStats result = Arrays.stream(input)
        .filter(score -> score >= 0 && score <= 100)
        .collect(ExamStats::new, ExamStats::accept, ExamStats::combine);

System.out.println(result.valid);      // 5
System.out.println(result.passed);     // 3
System.out.println(result.totalScore); // 259
System.out.println(result.average());  // 51.8
```

The `filter` step expresses the rule to drop out-of-range scores before feeding the statistics container. The accumulator processes **one `int` score at a time**; the combiner sums each component independently while preserving units. Changing `Arrays.stream(input)` to `Arrays.stream(input).parallel()` requires no change to the statistics formula because `ExamStats::combine` satisfies this merge rule (within non-overflow bounds).

If you need to distinguish “invalid data” from “skipped” for an audit report, do not silently drop them via `filter`. Instead, use an accumulator with an `invalid` field and handle every score directly for complete accounting.

## 12. Self-check

1. Why does `IntStream.collect(Collectors.toList())` fail to compile? **Because** `IntStream.collect` requires **three functions**: `supplier`, `ObjIntConsumer`, and `BiConsumer`; the overload taking `Collector` belongs to `Stream<T>`.
2. In a List accumulator, can `supplier` return the exact same `ArrayList` on every call? **No**, each call must return an independent container.
3. Why is the combiner `(left, right) -> {}` dangerous? **Because** results from the right-hand branch are lost whenever the pipeline performs parallel merging.
4. If you only need an `int[]`, should you pick `collect` or `toArray()`? **`toArray()`** is usually more direct and avoids boxing.
5. Do you need to write a combiner yourself for `IntSummaryStatistics`? **No** when calling `summaryStatistics()`; you can pass `IntSummaryStatistics::combine` if explicitly invoking three-argument `collect`.
6. When computing an average in parallel, why is storing `sum` and `count` better than averaging two branch `average` values? **Because** branches can have different element counts.
7. Has `collect` running on `Files.lines` closed the file? **No**; close the source Stream via `try-with-resources`.
8. Why does a `long` field inside an accumulator still need data-range checks? **Because** `long` addition can still overflow if the total exceeds its limit.
9. Does `DoubleStream.collect` guarantee bit-for-bit identical sum results between sequential and parallel runs? **No**; floating-point addition is affected by ordering and grouping.

**Practical rule:** Use `collect(supplier, accumulator, combiner)` when a primitive Stream needs to construct **a custom mutable result**. The supplier creates a fresh state, the accumulator adds one value, and the combiner properly merges two states; all three functions must be consistent to work correctly in both sequential and parallel modes. When `sum()`, `toArray()`, or `summaryStatistics()` already meets the need, prefer the specialized API for simplicity and fewer bugs.
