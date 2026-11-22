# Flattening with flatMapToInt, flatMapToLong, and flatMapToDouble

## 1. When is flattening numeric data needed?

In the Java Stream API, available data is commonly processed through a lazy pipeline consisting of operations such as `filter`, `map`, `reduce`, and `collect`. A frequent scenario is that **each input element contains multiple numbers**, whereas the required output is a single continuous sequence of numbers to sum, find extrema, or compute statistics.

For example, each delivery batch contains an array of item quantities:

```text
Stream<int[]>                        IntStream
  [2, 3]  ─────────────────────────► 2, 3
  [4]     ── flatMapToInt(...) ────► 4
  []      ─────────────────────────► (no elements)

Result after flattening: 2, 3, 4
```

The three methods **`flatMapToInt`, `flatMapToLong`, and `flatMapToDouble`** convert a `Stream<T>` into the corresponding primitive numeric stream:

- `flatMapToInt` produces an `IntStream` containing `int` values.
- `flatMapToLong` produces a `LongStream` containing `long` values.
- `flatMapToDouble` produces a `DoubleStream` containing `double` values.

Unlike one-to-one mapping, each input element is allowed to produce **zero, one, or many** output elements. The sub-streams are concatenated into a single primitive stream.

This lesson belongs to the **Primitive Streams** chapter and focuses on how to pick the right method, how to structure mappers, data safety, collecting results, and performance limits of flattening.

After studying this lesson, you will be able to write pipelines to:

1. Flatten lists of integer arrays, lists of `long` IDs, or sets of `double` measurement samples.
2. Combine `filter`, `flatMapToX`, and terminal operations `sum`, `average`, `summaryStatistics`, and `toArray`.
3. Distinguish `mapToX` from `flatMapToX`, and `Stream.flatMapToX` from `IntStream.flatMap`/`LongStream.flatMap`/`DoubleStream.flatMap`.
4. Handle empty sub-collections, `null`, parsing errors, infinite Streams, and mutable data.
5. Evaluate sub-stream creation overhead, boxing, parallel processing, and numeric precision.

Complete examples use **Java 17+**. The three `flatMapToX` operations have existed since Java 8; examples using `List.of` require Java 9+, and `record` and `Stream.toList()` require Java 16+.

## 2. Contract of the three methods

On `Stream<T>`, Java provides:

```java
IntStream flatMapToInt(
        Function<? super T, ? extends IntStream> mapper);

LongStream flatMapToLong(
        Function<? super T, ? extends LongStream> mapper);

DoubleStream flatMapToDouble(
        Function<? super T, ? extends DoubleStream> mapper);
```

The signatures above illustrate methods specific to `Stream<T>`. The `mapper` takes **one element `T`** and returns **a primitive Stream**, rather than returning a number directly.

| Method on `Stream<T>` | Mapper returns | Operation result | Common source examples |
| --- | --- | --- | --- |
| `flatMapToInt(...)` | `IntStream` | `IntStream` | `int[]`, list of product quantities |
| `flatMapToLong(...)` | `LongStream` | `LongStream` | `long[]`, list of durations or large IDs |
| `flatMapToDouble(...)` | `DoubleStream` | `DoubleStream` | `double[]`, series of measurements |

Logically, the process proceeds as follows:

1. The pipeline pulls an element from the outer Stream.
2. `mapper` creates a sub-stream of the matching primitive type.
3. Values from the sub-stream are fed into the flattened result.
4. The pipeline continues with the next element of the outer Stream as needed.

These are **lazy intermediate operations**. Writing `source.stream().flatMapToInt(...)` only constructs the pipeline; a terminal operation triggers traversal.

By the API contract, **the sub-stream returned by the mapper is closed after its contents have been placed into the result Stream**. A mapper returning `null` is treated as returning an empty Stream, though it is better to return `IntStream.empty()`, `LongStream.empty()`, or `DoubleStream.empty()` explicitly to clarify intent.

Mapper functions must be **non-interfering** and **stateless** (not depending on mutable state modified while processing other elements).

## 3. flatMapToInt: concatenating multiple int sequences

Suppose each group has its own order counts:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<int[]> orderCounts = List.of(
        new int[] {2, 3},
        new int[] {4},
        new int[] {}
);

int[] allCounts = orderCounts.stream()
        .flatMapToInt(group -> Arrays.stream(group))
        .toArray();

System.out.println(Arrays.toString(allCounts)); // [2, 3, 4]
```

In the example, the source has type `Stream<int[]>`. `Arrays.stream(int[])` creates an `IntStream` for each array; `flatMapToInt` concatenates the sub-streams into a single `IntStream`. Empty arrays emit no elements.

A method reference can be used:

```java
int total = orderCounts.stream()
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 9
```

`sum()` is a terminal operation on `IntStream`. If only the sum is needed, there is no need to call `toArray()` and hold all results in memory.

### One input element can produce 0, 1, or many numbers

The mapper can decide the number of output elements conditionally:

```java
record Group(boolean enabled, int[] numbers) {}

List<Group> groups = List.of(
        new Group(true, new int[] {1, 2}),
        new Group(false, new int[] {100}),
        new Group(true, new int[] {7})
);

int[] enabledNumbers = groups.stream()
        .flatMapToInt(group -> group.enabled()
                ? Arrays.stream(group.numbers())
                : IntStream.empty())
        .toArray();

System.out.println(Arrays.toString(enabledNumbers)); // [1, 2, 7]
```

The condition can be placed outside the mapper if it is a property of the source element:

```java
int[] sameResult = groups.stream()
        .filter(Group::enabled)
        .flatMapToInt(group -> Arrays.stream(group.numbers()))
        .toArray();
```

In this case, placing `filter` before `flatMapToInt` clearly shows that **entire groups** are excluded first, and only selected groups are flattened.

## 4. flatMapToLong: handling long sequences

`long` fits integer values beyond the `int` range, such as numeric identifiers or large millisecond counts. For example, batches containing event IDs:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.LongStream;

record EventBatch(String name, long[] ids) {}

List<EventBatch> batches = List.of(
        new EventBatch("A", new long[] {2_147_483_648L, 3_000_000_000L}),
        new EventBatch("B", new long[] {}),
        new EventBatch("C", new long[] {4_000_000_000L})
);

long[] eventIds = batches.stream()
        .flatMapToLong(batch -> Arrays.stream(batch.ids()))
        .toArray();

System.out.println(Arrays.toString(eventIds));
// [2147483648, 3000000000, 4000000000]
```

The numbers above exceed `int` limits yet remain within `long`. The `L` suffix in Java literals clarifies the data type.

Total duration in milliseconds can also be summed:

```java
List<long[]> durationsBySession = List.of(
        new long[] {1_200L, 800L},
        new long[] {3_000L}
);

long totalMillis = durationsBySession.stream()
        .flatMapToLong(Arrays::stream)
        .sum();

System.out.println(totalMillis); // 5000
```

**Watch numeric range:** `LongStream.sum()` can still overflow `long` when the total exceeds `Long.MAX_VALUE` or falls below `Long.MIN_VALUE`. Choosing `flatMapToLong` does not create arbitrary-precision integers; for huge totals, consider `BigInteger` and an appropriate reduction strategy.

## 5. flatMapToDouble: flattening measurement samples

For floating-point numbers, `DoubleStream` can compute averages, sums, extrema, and statistics:

```java
import java.util.Arrays;
import java.util.List;
import java.util.DoubleSummaryStatistics;

record SensorBatch(String sensorId, double[] readings) {}

List<SensorBatch> readingsBySensor = List.of(
        new SensorBatch("S1", new double[] {1.5, 2.5}),
        new SensorBatch("S2", new double[] {}),
        new SensorBatch("S3", new double[] {3.0})
);

DoubleSummaryStatistics statistics = readingsBySensor.stream()
        .flatMapToDouble(batch -> Arrays.stream(batch.readings()))
        .summaryStatistics();

System.out.println(statistics.getCount());   // 3
System.out.println(statistics.getSum());     // 7.0
System.out.println(statistics.getAverage()); // approximately 2.3333333333333335
```

`summaryStatistics()` performs a single pass to collect count, sum, min, max, and average. A simpler alternative:

```java
double average = readingsBySensor.stream()
        .flatMapToDouble(batch -> Arrays.stream(batch.readings()))
        .average()
        .orElse(Double.NaN);
```

`average()` returns `OptionalDouble` because there may be no samples after flattening. In this example, `Double.NaN` is chosen to **indicate no average value** rather than silently returning 0; an application may choose a different handling strategy.

### NaN, Infinity, and floating-point precision

`DoubleStream` does not automatically discard `NaN` or infinite values. For measurement data requiring finite statistics, filter explicitly:

```java
double[] readings = {2.5, Double.NaN, 4.0, Double.POSITIVE_INFINITY};

double finiteAverage = Arrays.stream(readings)
        .filter(Double::isFinite)
        .average()
        .orElse(Double.NaN);

System.out.println(finiteAverage); // 3.25
```

`double` operations have representation error and addition is not strictly associative; in parallel processing, combination order can change a few trailing decimal digits. For **currency** or exact decimal requirements, use `BigDecimal` with an appropriate collection model instead of `DoubleStream`.

## 6. Comparing mapToInt, flatMapToInt, and flatMap

This is the most important distinction when reading method signatures:

| Method on `Stream<T>` | Each `T` produces | Result type | When to use |
| --- | --- | --- | --- |
| `mapToInt(ToIntFunction<T>)` | **Exactly one** `int` | `IntStream` | Computing string length, extracting one quantity per order. |
| `flatMapToInt(Function<T, IntStream>)` | **0 to many** `int` | `IntStream` | Each group contains multiple integers to flatten. |
| `map(Function<T, R>)` | **Exactly one** `R` value | `Stream<R>` | Transforming one object into another object. |
| `flatMap(Function<T, Stream<R>>)` | **0 to many** `R` | `Stream<R>` | Flattening object data, e.g., names from multiple groups. |

Signatures in the table are abbreviated for comparison and do not show full generic wildcards.

Consider a source with two arrays:

```java
List<int[]> blocks = List.of(
        new int[] {3, 5},
        new int[] {7}
);

int[] lengths = blocks.stream()
        .mapToInt(block -> block.length)
        .toArray();
// [2, 1]: each array produces exactly one length

int[] values = blocks.stream()
        .flatMapToInt(Arrays::stream)
        .toArray();
// [3, 5, 7]: each array emits the numbers inside it
```

A common mistake is using `map` when the mapper returns a sub-stream:

```java
Stream<IntStream> nested = blocks.stream()
        .map(Arrays::stream);

// nested contains two IntStreams, not a flattened int stream.
```

To obtain integers directly, use `flatMapToInt`. If the source data is `List<Integer>` lists instead of arrays, you can write:

```java
List<List<Integer>> nestedLists = List.of(
        List.of(3, 5),
        List.of(),
        List.of(7)
);

int[] flattened = nestedLists.stream()
        .flatMapToInt(list -> list.stream()
                .mapToInt(Integer::intValue))
        .toArray();

System.out.println(Arrays.toString(flattened)); // [3, 5, 7]
```

In the latter example, `List<Integer>` already stores numbers as boxed objects. `flatMapToInt` lets the output pipeline work with `int`, yet **does not eliminate the boxing overhead already present in the input structure**. For large numeric datasets that are particularly performance-sensitive, `int[]` or primitive stream structures may be more appropriate.

Correspondingly for `long` and `double`, one-to-one mappings are `mapToLong` and `mapToDouble`; flattening operations are `flatMapToLong` and `flatMapToDouble`.

## 7. Do not confuse with flatMap on primitive streams

The `flatMapToX` family **exists only on object-typed `Stream<T>`**. If you already have an `IntStream`, you use `IntStream.flatMap`:

```java
int[] values = IntStream.of(1, 3)
        .flatMap(n -> IntStream.rangeClosed(1, n))
        .toArray();

System.out.println(Arrays.toString(values)); // [1, 1, 2, 3]
```

Similarly:

- `LongStream.flatMap(LongFunction<? extends LongStream>)` flattens a `LongStream` into a `LongStream`.
- `DoubleStream.flatMap(DoubleFunction<? extends DoubleStream>)` flattens a `DoubleStream` into a `DoubleStream`.

You cannot call `flatMapToInt` on an `IntStream` because that method is not part of its API. You can convert between primitive types using appropriate methods, such as `IntStream.asLongStream()`, `IntStream.asDoubleStream()`, `LongStream.mapToDouble(...)`, or `IntStream.boxed()` when returning to an object Stream is genuinely needed.

## 8. Combining filter, flatMapToX, and aggregate operations

The position of `filter` determines whether to **filter groups first** or **filter numbers after flattening**.

Suppose we only want quantities from active groups, and within each group only keep positive quantities:

```java
record InventoryGroup(boolean active, int[] quantities) {}

List<InventoryGroup> inventory = List.of(
        new InventoryGroup(true, new int[] {3, 0, -1, 5}),
        new InventoryGroup(false, new int[] {100}),
        new InventoryGroup(true, new int[] {2})
);

int[] acceptedQuantities = inventory.stream()
        .filter(InventoryGroup::active)             // Filter by group
        .flatMapToInt(group -> Arrays.stream(group.quantities()))
        .filter(quantity -> quantity > 0)           // Filter individual numbers
        .toArray();

System.out.println(Arrays.toString(acceptedQuantities)); // [3, 5, 2]
```

Semantically:

1. `filter` on `Stream<InventoryGroup>` can discard entire inactive groups without creating sub-streams for them.
2. `flatMapToInt` concatenates the `quantities` arrays of the remaining groups.
3. `filter` on `IntStream` keeps only positive numbers.

After flattening, commonly used terminal operations include:

| Terminal operation | Return type | Purpose |
| --- | --- | --- |
| `sum()` | matching `int`/`long`/`double` | Sums all values. |
| `average()` | `OptionalDouble` | Average, possibly empty. |
| `count()` | `long` | Counts numbers after flattening. |
| `min()`, `max()` | `OptionalInt`/`OptionalLong`/`OptionalDouble` | Extrema. |
| `summaryStatistics()` | `IntSummaryStatistics`/`LongSummaryStatistics`/`DoubleSummaryStatistics` | Computes multiple metrics in one pass. |
| `toArray()` | `int[]`, `long[]`, or `double[]` | Stores all results when actually needed. |

A Stream already consumed by a terminal operation cannot be reused. If both `sum` and `max` are needed on the same dataset, call `summaryStatistics()` once or build a **new pipeline from the source**.

## 9. Mapping from raw strings to multiple numbers

Not every source already contains primitive arrays. For instance, each CSV row contains a group of numbers:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> rows = List.of("12, 8", "", "5, 9, 10");

int[] numbers = rows.stream()
        .flatMapToInt(row -> {
            if (row.isBlank()) {
                return IntStream.empty();
            }
            return Arrays.stream(row.split(","))
                    .map(String::trim)
                    .mapToInt(Integer::parseInt);
        })
        .toArray();

System.out.println(Arrays.toString(numbers)); // [12, 8, 5, 9, 10]
```

This is a multi-layer pipeline: `Stream<String>` of rows → `Stream<String>` of tokens in each row → `IntStream` after parsing → one flattened `IntStream`.

**Limitation of the example:** `Integer.parseInt` throws `NumberFormatException` if a token is invalid or out of `int` range. `flatMapToInt` does not skip bad tokens automatically.

If the requirement is to **skip unparseable tokens**, the policy can be expressed as a helper method:

```java
static IntStream parseIfValid(String token) {
    try {
        return IntStream.of(Integer.parseInt(token.trim()));
    } catch (NumberFormatException exception) {
        return IntStream.empty();
    }
}

// Example placed inside the same class containing parseIfValid:
int[] accepted = List.of("3", "abc", "7").stream()
        .flatMapToInt(MyClass::parseIfValid)
        .toArray();

// [3, 7]
```

In the illustration, replace `MyClass` with the name of the class containing `parseIfValid`. Skipping bad data is only appropriate when business rules permit it; if auditing is needed, retain the invalid tokens and reasons in a separate reporting structure.

For `long` numbers, use `Long.parseLong` to build a `LongStream`; for `double`, use `Double.parseDouble` and explicitly decide whether `NaN` or infinity is accepted.

## 10. Null sources, empty Streams, and missing-data rules

Primitive streams cannot hold `null` references, yet an **object source** can still contain `null` elements or `null` array fields.

```java
record Packet(int[] values) {}

List<Packet> packets = java.util.Arrays.asList(
        new Packet(new int[] {1, 2}),
        new Packet(null),
        null,
        new Packet(new int[] {})
);

int[] valid = packets.stream()
        .filter(java.util.Objects::nonNull)
        .flatMapToInt(packet -> packet.values() == null
                ? IntStream.empty()
                : Arrays.stream(packet.values()))
        .toArray();

System.out.println(Arrays.toString(valid)); // [1, 2]
```

Here there are two decisions:

- `filter(Objects::nonNull)` drops **null Packet elements** from the source.
- `IntStream.empty()` represents a **valid Packet with no number array**.

If the mapper returns `null`, `flatMapToInt` treats it as an empty Stream per the contract; using `empty()` explicitly remains clearer and avoids ambiguous code.

For the output primitive stream, `filter(Objects::nonNull)` is not needed after `flatMapToInt` because `int` cannot be `null`. Nor should missing data arbitrarily be turned into `0` unless that is genuinely the business rule.

## 11. Laziness, resources, and sub-stream lifecycle

`flatMapToInt`, `flatMapToLong`, and `flatMapToDouble` are all lazy: they do not need to pre-build a list holding all flattened values. Traversal is driven by the terminal operation.

```java
Stream<int[]> pipeline = Stream.of(
        new int[] {1, 2},
        new int[] {3}
);

IntStream flattened = pipeline.flatMapToInt(values -> {
    System.out.println("Creating sub IntStream");
    return Arrays.stream(values);
});

// No terminal operation yet, so flattening has not started.
int[] result = flattened.toArray(); // Triggers processing.
```

The strength of a lazy pipeline is processing values on demand without storing the entire result. Terminal operations such as `findFirst` and `limit` allow **short-circuiting** in many pipelines:

```java
int[] firstThree = Stream.of(
                new int[] {4, 5},
                new int[] {6, 7, 8}
        )
        .flatMapToInt(Arrays::stream)
        .limit(3)
        .toArray();

System.out.println(Arrays.toString(firstThree)); // [4, 5, 6]
```

However, **do not rely on how many times the mapper is called, the call order, or side effects**. Pipeline optimizations, source characteristics, and parallel processing can affect how much work runs before stopping. Be especially cautious with an infinite sub-stream or a blocking input source: do not assume every terminal operation completes immediately.

### Who is responsible for closing Streams?

`flatMapToX` closes **the sub-streams returned by the mapper** after consuming them per the contract. However, if the **outer Stream** is created from a closeable resource (such as `Files.lines`), you must still manage the outer resource with `try-with-resources`:

```java
// Illustrative example: lines is a Stream<String> backed by a file.
// try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
//     long count = lines.flatMapToInt(MyClass::parseLineToInts).count();
// }
```

Automatic closing of sub-streams does not replace managing sources, I/O streams, or connections from outer layers. Avoid reusing a single sub-stream across multiple input elements: a Stream should only be consumed once.

## 12. Shared state, parallelism, and performance

### Mappers must be non-interfering and stateless

An incorrect pattern is modifying the source collection itself inside the mapper:

```java
List<int[]> source = new java.util.ArrayList<>();
source.add(new int[] {1, 2});
source.add(new int[] {3});

// WRONG: modifying source while source.stream() is traversing it.
int[] invalid = source.stream()
        .flatMapToInt(group -> {
            source.add(new int[] {99});
            return Arrays.stream(group);
        })
        .toArray();
```

This example violates **non-interference**; it can lead to `ConcurrentModificationException` or unreliable behavior. Similarly, a mapper relying on a shared counter violates the stateless contract and is unpredictable when run in parallel.

If the source needs to be updated, finish the terminal operation first and perform updates in a separate phase.

### When is parallel appropriate?

`parallelStream()` can distribute work across threads, yet it is not always faster:

```java
long total = durationsBySession.parallelStream()
        .flatMapToLong(Arrays::stream)
        .sum();
```

Valid integer arithmetic values can be aggregated across branches, yet data size, sub-stream creation overhead, and source splitting determine performance. With many tiny groups, mapper and coordination overhead can outweigh the computation itself.

If the outer Stream has an encounter order and each sub-stream is also ordered, the flattened result preserves the logical order of groups in operations that respect order, such as `toArray()`. **Mapper execution order** across threads is not guaranteed. With `double` addition, changing evaluation order can slightly alter results due to floating-point rounding.

### Boxing, sub-streams, and mapMultiToX

Using primitive streams avoids boxed values **in the resulting pipeline**. It does not convert a `List<Integer>` into a primitive array for free.

For one-to-one mapping, use `mapToInt` rather than writing `flatMapToInt(x -> IntStream.of(...))` just to emit a single number, as the latter allocates a sub-stream.

When each element emits few numbers and creating many sub-streams becomes a bottleneck, Java 16+ also offers `mapMultiToInt`, `mapMultiToLong`, and `mapMultiToDouble`. These methods push values directly to a consumer:

```java
List<int[]> groups = List.of(
        new int[] {2, 3},
        new int[] {},
        new int[] {4}
);

int[] flattened = groups.stream()
        .mapMultiToInt((group, consumer) -> {
            for (int value : group) {
                consumer.accept(value);
            }
        })
        .toArray();

System.out.println(Arrays.toString(flattened)); // [2, 3, 4]
```

`mapMultiToX` is worth considering when emitting 0 to many values without creating sub-streams; prioritize clarity first, and then benchmark on realistic data volumes.

## 13. Complete example: shipment batch statistics

Problem: each batch has a list of item counts (`int[]`), leg distances in meters (`long[]`), and weight samples (`double[]`). Only count accepted batches, then produce three independent statistics.

Runnable example on Java 17+:

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

public class PrimitiveFlatMapDemo {
    record Batch(
            String id,
            boolean accepted,
            int[] itemCounts,
            long[] distancesMeters,
            double[] weightsKg
    ) {}

    public static void main(String[] args) {
        List<Batch> batches = List.of(
                new Batch("B01", true,
                        new int[] {2, 3},
                        new long[] {1_200L, 800L},
                        new double[] {1.0, 2.0}),
                new Batch("B02", false,
                        new int[] {100},
                        new long[] {99_999L},
                        new double[] {99.0}),
                new Batch("B03", true,
                        new int[] {4},
                        new long[] {3_000L},
                        new double[] {3.0}),
                new Batch("B04", true,
                        new int[] {},
                        new long[] {},
                        new double[] {})
        );

        int totalItems = batches.stream()
                .filter(Batch::accepted)
                .flatMapToInt(batch -> Arrays.stream(batch.itemCounts()))
                .sum();

        long totalDistance = batches.stream()
                .filter(Batch::accepted)
                .flatMapToLong(batch -> Arrays.stream(batch.distancesMeters()))
                .sum();

        DoubleSummaryStatistics weightStats = batches.stream()
                .filter(Batch::accepted)
                .flatMapToDouble(batch -> Arrays.stream(batch.weightsKg()))
                .summaryStatistics();

        System.out.println("Total items: " + totalItems);         // 9
        System.out.println("Total distance (m): " + totalDistance); // 5000
        System.out.println("Weight sample count: " + weightStats.getCount()); // 3
        System.out.println("Average weight (kg): " + weightStats.getAverage()); // 2.0
    }
}
```

Rationale for this structure:

1. `filter(Batch::accepted)` completely excludes batch `B02` before flattening.
2. `flatMapToInt` concatenates the item count arrays, and `sum` computes a total of `9`.
3. `flatMapToLong` concatenates the `long` distances, and `sum` produces `5000` meters.
4. `flatMapToDouble` concatenates the weight samples, and `summaryStatistics` aggregates three samples with an average of `2.0` kg.
5. Batch `B04` contains three empty arrays and emits no numbers; the program handles it normally.
6. Each metric creates a **new pipeline from the source list**, rather than trying to reuse a Stream already consumed by a terminal operation.

In a real application, if three statistics are needed in a single pass over the data, a custom collector/accumulator or a clearly structured and controlled loop can be built. The independent pipelines here prioritize readability and clearly demonstrate each `flatMapToX`.

## 14. Common errors and how to check

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Cannot call `flatMapToInt` | Current source is `IntStream`, no longer `Stream<T>`. | Use `IntStream.flatMap` or check the pipeline type. |
| Lambda returns an `int` instead of `IntStream` | Confusing `flatMapToInt` with `mapToInt`. | Return an `IntStream` or switch to `mapToInt` for 1-to-1 mapping. |
| Result is `Stream<IntStream>` | Called `map(x -> IntStream...)`. | Use `flatMapToInt` to flatten. |
| `NumberFormatException` while parsing tokens | Not validating input before `parseInt`. | Define a policy to report errors or skip invalid tokens. |
| `NullPointerException` when calling `Arrays.stream` | An array/field in the source is `null`. | Check for null and return an empty primitive stream when appropriate. |
| Cannot call `toList()` on `IntStream` | Primitive streams do not have `Stream.toList()`. | Use `toArray()` or `boxed().toList()`. |
| Average result has no value | No numbers remained after flattening. | Handle `OptionalDouble` per business rules. |
| Wrong `int`/`long` sum on very large data | Integer type overflow. | Choose a numeric model with adequate range; check for overflow. |
| Small discrepancy in `double` sum or average | Floating-point precision limits and addition order. | Define acceptable tolerance, or use `BigDecimal` if needed. |
| Parallel pipeline is slower | Splitting/merging and sub-stream creation overhead. | Measure in practice; consider sequential or `mapMultiToX`. |
| Source data mutated unexpectedly | Mapper has side effects on source or shared objects. | Keep mapper stateless and read-only on the source. |

## 15. Practice exercises

Given the data:

```java
List<String> integerRows = List.of("1,2,3", "", "4,5");

List<long[]> sessions = List.of(
        new long[] {1_000L, 2_000L},
        new long[] {},
        new long[] {3_000L}
);

List<double[]> grades = List.of(
        new double[] {7.5, 8.0},
        new double[] {},
        new double[] {9.5}
);
```

**Tasks:**

1. Use `flatMapToInt` to read the numbers from `integerRows` and produce an `int[]` in exact order.
2. Use `flatMapToLong` to compute the total duration in `sessions`.
3. Use `flatMapToDouble` to compute the average grade in `grades`.
4. Explain why `mapToLong(session -> session.length)` does not replace `flatMapToLong(Arrays::stream)` in task 2.
5. If an entry in `grades` is an empty array, how does it affect the sample count and average?

**Reference solutions:**

```java
int[] allIntegers = integerRows.stream()
        .flatMapToInt(row -> row.isEmpty()
                ? IntStream.empty()
                : Arrays.stream(row.split(","))
                        .mapToInt(Integer::parseInt))
        .toArray();
// [1, 2, 3, 4, 5]

long totalTime = sessions.stream()
        .flatMapToLong(Arrays::stream)
        .sum();
// 6000

double gradeAverage = grades.stream()
        .flatMapToDouble(Arrays::stream)
        .average()
        .orElse(Double.NaN);
// (7.5 + 8.0 + 9.5) / 3 = 8.333333333333334 (approximately)
```

For task 4, `mapToLong(session -> session.length)` produces one number equal to the **array length** for each session, so the sum only reflects the element count; `flatMapToLong` emits the durations **inside the arrays** so they can be summed. For task 5, an empty array produces no samples; the denominator for the average remains the three values `7.5`, `8.0`, and `9.5`.

## Key Takeaways

`flatMapToInt`, `flatMapToLong`, and `flatMapToDouble` flatten primitive sub-streams produced from each element of a `Stream<T>`. Choose the method based on the output numeric type; each input can yield **0, 1, or many numbers**. Results can be used directly with `sum`, `average`, `summaryStatistics`, or `toArray` without re-boxing. `mapToX` is only suitable when each element yields exactly one number, whereas when the source is already a primitive stream, use the corresponding `flatMap`.

Make handling of empty or invalid data explicit, keep mappers stateless and non-interfering, manage I/O source lifecycles properly, and avoid reusing consumed Streams. For heavy workloads, weigh numeric precision, sub-stream creation cost, parallelization suitability, and `mapMultiToX` when evidence-based optimization is warranted.
