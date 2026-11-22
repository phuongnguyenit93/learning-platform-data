# `min`, `max`, and Specialized `Optional` Types When Aggregating Numbers in Java

## 1. Goal and Problem

When aggregating numeric data in Java, two common requirements are finding the **minimum (`min`)** and **maximum (`max`)** values. Examples include the lowest daily temperature, highest request latency, highest score, or smallest order quantity.

The difficulty arises when **the data source is empty**. A sequence with no elements has no defined minimum or maximum value. The Java Stream API represents this with `OptionalInt`, `OptionalLong`, `OptionalDouble`, or `Optional<T>`; the caller must decide how to handle missing data.

```java
OptionalInt minimum = IntStream.of(8, 3, 12).min();
OptionalInt maximum = IntStream.of(8, 3, 12).max();
// minimum holds 3; maximum holds 12
```

After this lesson, you will be able to choose the right `min`/`max` overload, understand why the API returns `Optional`, handle empty sequences safely, distinguish primitive streams from object streams, evaluate `NaN`/`-0.0` cases, and apply `summaryStatistics()` when multiple aggregations are needed over the same source.

## 2. `min` and `max` on the Three Primitive Stream Types

Java has three specialized stream interfaces for primitive numbers:

| Stream type | Methods | Result | Value type |
| --- | --- | --- | --- |
| `IntStream` | `min()`, `max()` | `OptionalInt` | `int` |
| `LongStream` | `min()`, `max()` | `OptionalLong` | `long` |
| `DoubleStream` | `min()`, `max()` | `OptionalDouble` | `double` |
| `Stream<T>` | `min(Comparator)`, `max(Comparator)` | `Optional<T>` | Object |

The `min()`/`max()` methods on primitive streams are **terminal operations**: they consume the stream to compute the result. There is no overload taking a `Comparator` on `IntStream`, `LongStream`, or `DoubleStream`; primitive numeric types use their natural numeric order. On `Stream<T>`, you must pass a `Comparator` defining the ordering.

Example:

```java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.OptionalDouble;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

OptionalInt smallestInt = IntStream.of(6, -2, 9).min();
OptionalLong largestLong = LongStream.of(2L, 5_000_000_000L).max();
OptionalDouble smallestDouble = DoubleStream.of(3.5, 1.25).min();

System.out.println(smallestInt.orElseThrow());  // -2
System.out.println(largestLong.orElseThrow());   // 5000000000
System.out.println(smallestDouble.orElseThrow()); // 1.25
```

This is an **embedded snippet**: place these statements inside a method together with the listed `import`s. A standalone runnable program is in Section 8.

These functions find extrema by **element value**. If you want to find *the element with the highest score* while keeping its ID, label, or other fields, use `Stream<T>.max(comparator)` instead of converting every object into just an `int`.

### 2.1. Why Is the Result an `Optional`?

Because no valid extremum can be assigned to an empty stream:

```java
OptionalInt none = IntStream.empty().max();

System.out.println(none.isPresent()); // false
System.out.println(none.isEmpty());   // true
```

`OptionalInt.empty()` is not the number `0`. Returning `0`, `Integer.MIN_VALUE`, or `null` as a default would change the meaning of the problem whenever that value could legitimately appear in the data.

The `min`/`max` methods on primitive streams are equivalent to a **reduction without an identity** using minimum/maximum selection, such as `reduce(Integer::min)` on `IntStream`. Because there is no universal identity that distinguishes an empty sequence, the natural result is `OptionalInt`.

### 2.2. Data Type Ranges and Conversions

- `IntStream` holds `int`, from `Integer.MIN_VALUE` to `Integer.MAX_VALUE`. It does not automatically widen inputs to `long`.
- `LongStream` holds `long`, suitable for numbers beyond `int` bounds.
- `DoubleStream` holds `double`, so it is subject to IEEE 754 floating-point specifics such as `NaN`, infinities, and `-0.0`.
- `Stream<Integer>`, `Stream<Long>`, `Stream<Double>` are **object streams**, which may require boxing/unboxing when converting types and use `Optional<T>` instead of `OptionalInt`/`OptionalLong`/`OptionalDouble`.

Example with a `List<Integer>`:

```java
List<Integer> numbers = List.of(7, 2, 11);
OptionalInt min = numbers.stream()
        .mapToInt(Integer::intValue)
        .min();
```

The statement above requires `import java.util.List; import java.util.OptionalInt;`. `List.of(...)` contains no `null`, so converting to primitives is safe. For another `List<Integer>` that contains `null` elements, unboxing throws `NullPointerException`; you must establish an explicit policy to filter or reject `null`.

## 3. Methods of `OptionalInt`, `OptionalLong`, and `OptionalDouble`

The three specialized classes hold the state of **having or not having a primitive value**, avoiding boxing into `Integer`, `Long`, or `Double` just to represent "possibly absent".

| Need | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| --- | --- | --- | --- |
| Check presence | `isPresent()` / `isEmpty()` | `isPresent()` / `isEmpty()` | `isPresent()` / `isEmpty()` |
| Get value when guaranteed present | `getAsInt()` | `getAsLong()` | `getAsDouble()` |
| Get value if present, else fallback | `orElse(int)` | `orElse(long)` | `orElse(double)` |
| Compute fallback when absent | `orElseGet(IntSupplier)` | `orElseGet(LongSupplier)` | `orElseGet(DoubleSupplier)` |
| Throw if absent | `orElseThrow()` | `orElseThrow()` | `orElseThrow()` |
| Run action if present | `ifPresent(IntConsumer)` | `ifPresent(LongConsumer)` | `ifPresent(DoubleConsumer)` |
| Two branches present/absent | `ifPresentOrElse(...)` | `ifPresentOrElse(...)` | `ifPresentOrElse(...)` |
| Convert to 0- or 1-element stream | `stream()` | `stream()` | `stream()` |

In Java 17, `isEmpty()`, `stream()`, `ifPresentOrElse()`, and `orElseThrow()` are all available. Primitive Optional types **do not provide all the transformation methods** of `Optional<T>`; for example, you cannot write `optionalInt.map(x -> ...)` directly as you can with `Optional<Integer>`.

### 3.1. When to Use `orElse`, `orElseGet`, and `orElseThrow`?

```java
OptionalInt optional = IntStream.of(4, 9, 2).max();

int mustExist = optional.orElseThrow(); // 9
int fallback = optional.orElse(-1);     // 9 because Optional has a value

OptionalInt missing = IntStream.empty().min();
int defaultValue = missing.orElse(0);   // 0 by caller POLICY
```

`orElse(0)` is only appropriate if business logic defines **no elements = 0**. That is not the mathematical definition of min/max on an empty set. For instance, when measuring temperature, `0°C` is a valid measurement, so using `0` to mean "no measurement" is dangerous.

If data is required to be non-empty, express that with an exception:

```java
int peak = IntStream.of(4, 9, 2)
        .max()
        .orElseThrow(() ->
                new IllegalStateException("No data to compute maximum"));
```

This is an embedded snippet. `orElseGet(() -> expensiveFallback())` evaluates the fallback only when the Optional is empty; whereas the argument passed to `orElse(expensiveFallback())` is evaluated before calling `orElse`, even when a value is already present. A primitive fallback must return the exact type `int`, `long`, or `double`.

When missing data is a normal state, **preserve the Optional** at the API boundary so the calling layer can decide. When missing data violates the contract, use `orElseThrow` with an informative message.

### 3.2. Do Not Call `getAs...()` Without Validation

```java
OptionalLong empty = LongStream.empty().min();
// empty.getAsLong() -> NoSuchElementException
```

`getAsInt`, `getAsLong`, and `getAsDouble` should only be used after `isPresent()` or when another domain invariant guarantees the Optional cannot be empty. If you intend to throw an error when data is missing, `orElseThrow()` communicates that intent more clearly.

### 3.3. Handling with `ifPresent`, `ifPresentOrElse`, and `stream`

```java
OptionalInt maybe = IntStream.of(2, 8, 5).max();

maybe.ifPresent(value -> System.out.println("max=" + value));

maybe.ifPresentOrElse(
        value -> System.out.println("Value present: " + value),
        () -> System.out.println("Empty data"));

int[] result = maybe.stream().map(x -> x * 2).toArray();
// result is an array containing only 16
```

These snippets are embedded examples using `OptionalInt` and `IntStream`. `stream()` is useful when you want to continue processing 0 or 1 value in a primitive pipeline without manually checking the empty branch.

## 4. `Stream<T>.min/max` and Comparators (`Comparator`)

For an object stream, the library does not know the ordering rules for every type; the API requires a comparator:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

record Reading(String id, int score) {}

List<Reading> readings = List.of(
        new Reading("sensor-A", 4),
        new Reading("sensor-B", 9),
        new Reading("sensor-C", 3));

Comparator<Reading> byScore =
        Comparator.comparingInt(Reading::score);

Optional<Reading> smallest = readings.stream().min(byScore);
Optional<Reading> largest = readings.stream().max(byScore);

System.out.println(smallest.orElseThrow().id()); // sensor-C
System.out.println(largest.orElseThrow().id());  // sensor-B
```

This is an **embedded snippet** illustrating a Java 17 `record`. If placing the record in the same `.java` file as another demo class, ensure naming rules and `public` class count rules are respected.

`Comparator.comparingInt` reads `int` via `ToIntFunction`, avoiding unnecessary boxing just to compare. For `long`/`double` fields, there are `comparingLong`/`comparingDouble`. `Stream<Integer>` can use `Comparator.naturalOrder()` to get `Optional<Integer>`; `mapToInt(Integer::intValue).min()` is more suitable if you want `OptionalInt`.

### 4.1. When Multiple Elements Tie at the Extremum

Suppose two orders both have score `9`. `max(byScore)` may pick either of them; **do not rely on which specific element is picked when the comparator considers them equal**, especially under parallel processing or after source order changes.

If business logic requires a deterministic element, specify a secondary criterion:

```java
Comparator<Reading> ranking = Comparator
        .comparingInt(Reading::score)
        .thenComparing(Reading::id);

Reading selected = readings.stream().max(ranking).orElseThrow();
```

With this comparator, when scores tie, `max` picks the lexicographically larger ID. If you want to prefer the smaller ID on a score tie, redefine the secondary criterion—for example `thenComparing(Reading::id, Comparator.reverseOrder())` when taking `max`. This is a domain decision, not a Stream API default.

A comparator must be consistent, transitive, and independent of state mutated while the stream runs. Otherwise, aggregation results become unpredictable.

### 4.2. `Collectors.minBy/maxBy`

When already inside `collect` or grouping data:

```java
import java.util.Comparator;
import java.util.Optional;
import java.util.stream.Collectors;

Optional<Integer> min = List.of(6, 3, 9)
        .stream()
        .collect(Collectors.minBy(Comparator.naturalOrder()));
```

`Collectors.minBy` returns `Optional<T>` like `Stream.min(comparator)`; it is useful when combined with other collectors such as `groupingBy`. If you only want the extremum of the whole stream, calling `.min(comparator)` or `.max(comparator)` directly is usually simpler.

## 5. Empty Data and Business Semantics

A source may be empty because there are no records at all, because a filter removed every element, or because input data was invalid/inaccessible. These cases can all produce the same `Optional.empty()` result, yet have **different business causes**.

```java
OptionalInt expensivePeak = IntStream.of(10, 20, 30)
        .filter(x -> x > 100)
        .max(); // OptionalInt.empty()
```

Before choosing a fallback, answer:

- **Is having no data a normal state?** Return `OptionalInt`/`OptionalLong`/`OptionalDouble` to the caller.
- **Is data required to exist?** Throw a clear exception, e.g., via `orElseThrow`.
- **Is there a defined default unit?** You may use `orElse(fallback)`; document clearly that the fallback is a domain policy.
- **Need JSON/REST?** Design an explicit "no value" representation in the DTO/API. Do not assume every JSON library serializes primitive Optionals the same way; convert to a well-defined DTO/protocol type when exporting data.

Do not replace an empty Optional with an extreme sentinel like `Integer.MAX_VALUE` or `Integer.MIN_VALUE` without an explicit existence flag, because those extreme values are valid integers in the `int` domain.

## 6. Special Cases with `DoubleStream.min/max`

`double` differs from integers because it has special values and ordering:

### 6.1. `NaN`

If **any element** in a `DoubleStream` is `Double.NaN`, then by the Java 17 contract, `min()`/`max()` returns an `OptionalDouble` **containing `NaN`**, even when all other elements are finite.

```java
double result = DoubleStream.of(3.0, Double.NaN, -5.0)
        .max()
        .orElseThrow();

System.out.println(result); // NaN
```

Here `OptionalDouble` is **not empty**. `isPresent()` only indicates an element was aggregated, not that the value is a finite number.

If the domain rules specify discarding `NaN`, filter intentionally:

```java
OptionalDouble cleanMin = DoubleStream.of(3.0, Double.NaN, -5.0)
        .filter(d -> !Double.isNaN(d))
        .min();
// cleanMin holds -5.0
```

If infinities are also unacceptable, use `Double.isFinite(d)` to keep only finite values. However, filtering data is a **business rule**; for data expected to be valid, rejecting a record containing `NaN` may be more appropriate than silently ignoring it.

### 6.2. Two Zeros: `-0.0` and `+0.0`

Java distinguishes the sign of zero in `double`:

```java
System.out.println(DoubleStream.of(+0.0, -0.0).min().orElseThrow()); // -0.0
System.out.println(DoubleStream.of(+0.0, -0.0).max().orElseThrow()); // 0.0
```

`DoubleStream.min()` treats `-0.0` as less than `+0.0`; `max()` treats `+0.0` as greater than `-0.0`, consistent with `Double.compare`. If the sign of zero carries meaning for measurements or downstream math, do not strip the sign arbitrarily.

### 6.3. Infinity and Floating-Point Precision

`Double.POSITIVE_INFINITY`/`Double.NEGATIVE_INFINITY` can participate in min/max. The result remains `double` and reflects floating-point representation accuracy. Note that **min/max** aggregation itself does not introduce extra rounding like repeated addition does, though individual source values may already have been approximated beforehand.

If the domain involves currency/decimals requiring exact representation, consider `BigDecimal` in `Stream<BigDecimal>` with its natural comparator instead of automatically converting to `double`:

```java
Optional<BigDecimal> min = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"))
        .stream()
        .min(BigDecimal::compareTo);
```

This embedded snippet requires `import java.math.BigDecimal; import java.util.List; import java.util.Optional;`. Note that `BigDecimal.compareTo` compares by **numeric value**, whereas `BigDecimal.equals` also checks scale; extrema problems typically want numeric value comparison.

## 7. Computing min and max Together with `summaryStatistics()`

If you need min, max, count, sum, and average of the same source, you can gather all of them in **a single traversal**:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.of(7, -2, 13, 13, 0)
        .summaryStatistics();

System.out.println(stats.getCount()); // 5
System.out.println(stats.getMin());   // -2
System.out.println(stats.getMax());   // 13
System.out.println(stats.getSum());   // 31
System.out.println(stats.getAverage()); // 6.2
```

Java provides `IntSummaryStatistics`, `LongSummaryStatistics`, and `DoubleSummaryStatistics`. `summaryStatistics()` is useful when multiple metrics are needed and avoids trying to reuse an already consumed stream.

**Note on empty sources:** `IntSummaryStatistics` has `count == 0`; when no elements have been seen, `getMin()` returns `Integer.MAX_VALUE` and `getMax()` returns `Integer.MIN_VALUE`. These are **internal initial values**, not meaningful min/max for an empty set. For `LongSummaryStatistics`, the defaults are analogous in the `long` range. For `DoubleSummaryStatistics`, min and max of an empty source are `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY`, respectively.

Therefore, before using extrema:

```java
IntSummaryStatistics stats = IntStream.empty().summaryStatistics();
if (stats.getCount() == 0) {
    System.out.println("No data");
} else {
    System.out.println(stats.getMin());
}
```

`summaryStatistics()` also carries sum/average rules: `int` sums can fit in `long` (`getSum()`), `long` sums can still overflow, and `double` calculations can incur floating-point error. Choose tools based on aggregation requirements rather than treating statistics as an "infinitely exact" solution for every metric.

### Streams Are Single-Use

The following is **invalid** because a stream cannot be reused after a terminal operation:

```java
IntStream source = IntStream.of(3, 7, 2);
int min = source.min().orElseThrow();
// source.max(); // IllegalStateException: stream has already been consumed
```

To get both min and max, create two new streams from a re-traversable source (e.g., `Arrays.stream(array)` each time) or use `summaryStatistics()` in a single pass. For a single-read I/O source, `summaryStatistics()` is usually the sensible approach for supported metrics.

## 8. Runnable Java 17+ Program

Save as **`MinMaxOptionalDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class MinMaxOptionalDemo {
    record Reading(String id, int score) {}

    public static void main(String[] args) {
        int[] scores = {7, -2, 13, 13, 0};

        OptionalInt smallest = Arrays.stream(scores).min();
        OptionalInt biggest = Arrays.stream(scores).max();
        OptionalInt empty = IntStream.empty().min();
        OptionalLong biggestLong =
                LongStream.of(5_000_000_000L, -4L, 9L).max();
        OptionalDouble smallestDouble =
                DoubleStream.of(2.5, -0.0, 7.75).min();

        List<Reading> readings = List.of(
                new Reading("A", 4),
                new Reading("B", 9),
                new Reading("C", 3));
        Comparator<Reading> ranking = Comparator
                .comparingInt(Reading::score)
                .thenComparing(Reading::id);

        Reading minReading = readings.stream()
                .min(ranking).orElseThrow();
        Reading maxReading = readings.stream()
                .max(ranking).orElseThrow();

        IntSummaryStatistics stats =
                Arrays.stream(scores).summaryStatistics();

        System.out.println("int min = " + smallest.orElseThrow());
        System.out.println("int max = " + biggest.orElseThrow());
        System.out.println("empty = " + empty.isEmpty());
        System.out.println("long max = " + biggestLong.orElseThrow());
        System.out.println("double min = " + smallestDouble.orElseThrow());
        System.out.println("reading min = " + minReading);
        System.out.println("reading max = " + maxReading);
        System.out.println("count = " + stats.getCount());
        System.out.println("stats min/max = "
                + stats.getMin() + "/" + stats.getMax());
        System.out.println("NaN max = "
                + DoubleStream.of(3.0, Double.NaN, -5.0)
                              .max().orElseThrow());
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac MinMaxOptionalDemo.java
java MinMaxOptionalDemo
```

Exact stdout:

```text
int min = -2
int max = 13
empty = true
long max = 5000000000
double min = -0.0
reading min = Reading[id=C, score=3]
reading max = Reading[id=B, score=9]
count = 5
stats min/max = -2/13
NaN max = NaN
```

**Explanation:** The numbers in `scores` yield min `-2` and max `13`; `IntStream.empty()` leads to an empty Optional. `LongStream` preserves `5_000_000_000` beyond `int` bounds. `DoubleStream` preserves the sign of `-0.0`. The comparator preserves the `Reading` record associated with the extreme score. `summaryStatistics` counts five elements and reports the same extrema. `NaN` in the source causes `DoubleStream.max()` to return `NaN` rather than `3.0`.

In this program, `orElseThrow()` on non-empty streams is valid because sample data is hardcoded. For potentially empty sources from an API or database, handle each Optional according to domain policy instead of calling `orElseThrow` everywhere by default.

## 9. Performance, Parallelism, and Comparison Order

To find min or max alone, a full pass normally has **O(n)** time complexity and does not need to sort the entire dataset. `stream().sorted().findFirst()` can find the lowest value, but it sorts everything and usually consumes more resources than `min(comparator)`.

With `IntStream`/`LongStream`/`DoubleStream`, avoid unnecessary boxing during reduction. When data is already a `List<Reading>`, converting to a primitive stream just to get a number and then mapping back to the object can introduce extra issues; use a comparator directly to retain metadata.

`min` and `max` can be used with parallel streams if the source, mapping, and comparator are safely designed:

```java
OptionalInt min = IntStream.rangeClosed(1, 1_000_000)
        .parallel()
        .min();
// Result has value 1, though whether parallel is faster must be measured.
```

If multiple objects are considered equal by the comparator, do not rely on a specific one being picked; add a tie-breaker criterion if a unique result is required by contract. Never let a comparator read/write shared mutable state or mutate values being compared mid-stream.

Do not run `min`/`max` over a source being concurrently modified without synchronization; correctness also depends on the collection/source guarantees. Under the Stream API, sources and lambdas must follow non-interference and avoid unsafe shared state.

## 10. Common Mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Calling `getAsInt()` on an empty stream result | `NoSuchElementException` | Use `orElse`, `orElseThrow`, `ifPresent`, or return Optional |
| Thinking `OptionalInt.empty()` equals `0` | Reports fake min/max, hides missing data | Keep absence state explicit |
| Using `Integer.MIN_VALUE` as max default without checking presence | Cannot distinguish empty from real extreme values | Return Optional or add a presence flag |
| Calling `.min()` then `.max()` on the same Stream | `IllegalStateException` | Create a new stream or use `summaryStatistics()` |
| Using `Stream<T>.min()` without a comparator | Does not compile | Pass a `Comparator` or convert to the proper primitive stream |
| Calling `getAsInt` on `Optional<Integer>` | Does not compile | For object Optional use `get`/`orElseThrow`; for primitive use `mapToInt` |
| Ignoring `NaN` in `DoubleStream` | Min/max becomes `NaN` despite other valid numbers | Define reject/filter policy per domain |
| Treating `-0.0` as identical to `+0.0` in every semantic | Unexpected display and extremum order | Check `Double.compare` rules and application contract |
| Comparator checking only score when a unique winner is needed | Records with tied scores are indistinguishable | Add secondary criteria via `thenComparing` |
| Using `summaryStatistics.getMin()` on empty set without checking count | Receives internal initial sentinel instead of true min | Check `getCount() > 0` |
| Using `sorted()` to get a single extremum | Unnecessary time/memory cost | Use terminal `min` or `max` |
| Passing `null` into `mapToInt(Integer::intValue)` | `NullPointerException` on unboxing | Validate, filter, or handle nulls intentionally |

## 11. Self-Check Exercises

1. Given `IntStream.of(-3, 0, 9, 9)`: what do `min` and `max` return? Why return `OptionalInt` instead of returning `int` directly?
2. After `.filter(x -> x > 100)` on the sequence above, what is the Optional from `max()`? When would you use `orElseThrow` instead of `orElse(0)`?
3. For `Reading(id, score)` with two elements sharing the same `score`, define a tie-breaker to take the highest score, and prefer the *smallest* ID on ties.
4. For `DoubleStream.of(2.0, Double.NaN, -10.0)`, what is `.min()`? Fix the pipeline to consider only finite values.
5. Why can `IntStream.empty().summaryStatistics().getMin()` not be treated as the dataset's minimum? Which property must you check?
6. A request needs `min`, `max`, and `count` on a source that can only be read once. Should you call three terminal operations on the same stream, or which approach should you choose?
7. Write a function taking `List<Integer>` and returning `OptionalInt` with the maximum value, rejecting `null`, without using `sorted()`.

**Hints:** (1) min `-3`, max `9`, because any source might be empty. (2) `OptionalInt.empty()`; use `orElseThrow` when missing data violates the contract. (3) `comparingInt(Reading::score).thenComparing(Reading::id, Comparator.reverseOrder())` then `.max(...)`. (4) `NaN`; use `.filter(Double::isFinite)` if domain rules require it. (5) `getCount() == 0` means no elements yet. (6) Single-pass `summaryStatistics()`. (7) use `stream().mapToInt(Integer::intValue).max()` after ensuring no nulls.

## 12. Key Takeaways

To obtain extrema on numeric data, prefer `IntStream.min/max`, `LongStream.min/max`, and `DoubleStream.min/max` matching the data type, receiving `OptionalInt`, `OptionalLong`, and `OptionalDouble`. For object data, use `Stream<T>.min/max(Comparator)` to preserve the full object. Define a clear **missing-data** policy, especially when a stream becomes empty after filtering; do not arbitrarily substitute 0.

If you need multiple metrics on the same stream, use `summaryStatistics()` and check `count` before reading min/max on empty sources. For `double`, define policies for `NaN`, infinity, and zero sign. When stable ordering is needed for tied records, define a comparator with secondary criteria.

Java SE 17 API documentation:
- [`IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html), [`LongStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html), [`DoubleStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html).
- [`OptionalInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html), [`OptionalLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalLong.html), [`OptionalDouble`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalDouble.html).
- [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [`IntSummaryStatistics`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IntSummaryStatistics.html).