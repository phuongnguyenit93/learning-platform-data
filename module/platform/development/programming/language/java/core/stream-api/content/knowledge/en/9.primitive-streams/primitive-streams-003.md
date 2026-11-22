# Mapping with `mapToInt`, `mapToLong`, and `mapToDouble`

In the **Java Stream API**, `Stream<T>` processes elements as objects, whereas `IntStream`, `LongStream`, and `DoubleStream` are specialized to handle the three primitive types `int`, `long`, and `double`. When the initial data consists of objects yet the desired calculations are numeric, `mapToInt`, `mapToLong`, and `mapToDouble` bridge the two worlds.

This is part of building **lazy pipelines**: using intermediate operations to describe how to extract numeric values, and then using terminal operations such as `sum`, `average`, `min`, `max`, or `summaryStatistics` to compute results. Choosing the right stream type clarifies intent, reduces boxing/unboxing demand, and explicitly manages value ranges and precision error.

## 1. Three methods to convert from `Stream<T>` to a primitive stream

| Method called on `Stream<T>` | Input function | Returned stream type | Common scenarios |
| --- | --- | --- | --- |
| `mapToInt(ToIntFunction<? super T>)` | `T → int` | `IntStream` | String lengths, ages, small counts. |
| `mapToLong(ToLongFunction<? super T>)` | `T → long` | `LongStream` | Large quantities, epoch timestamps, sums exceeding `int` range. |
| `mapToDouble(ToDoubleFunction<? super T>)` | `T → double` | `DoubleStream` | Measurements, ratios, floating-point calculation results. |

The three functional interfaces `ToIntFunction`, `ToLongFunction`, and `ToDoubleFunction` live in `java.util.function`. Each takes an object `T` and returns the corresponding primitive type directly, not `Integer`, `Long`, or `Double`.

Shortest example:

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("Java", "Stream", "API");

int totalCharacters = words.stream()
    .mapToInt(String::length)
    .sum();

System.out.println(totalCharacters); // 13 = 4 + 6 + 3
```

`String::length` satisfies `ToIntFunction<String>` because it takes a `String` and returns `int`. After the `mapToInt` step, the pipeline type is **`IntStream`**, so `sum()` or `average()` can be called directly.

### How does it differ from regular `map`?

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import java.util.stream.IntStream;

List<String> words = Arrays.asList("Java", "Stream", "API");

Stream<Integer> boxedLengths = words.stream()
    .map(String::length);

IntStream primitiveLengths = words.stream()
    .mapToInt(String::length);

int total = primitiveLengths.sum(); // 13
int boxedTotal = boxedLengths.mapToInt(Integer::intValue).sum(); // 13
```

`map(String::length)` creates a `Stream<Integer>`: the `int` value from `length()` is **boxed** into an `Integer` object. In contrast, `mapToInt(String::length)` yields an `IntStream` and avoids that intermediate object layer. The final result in the example is the same, yet the APIs available in subsequent steps differ.

You cannot call `sum()` directly on `Stream<Integer>`, because `Stream<T>` has no terminal `sum` method. You could use `reduce(0, Integer::sum)` on `Stream<Integer>`, though a primitive stream is usually preferred when the goal is purely numeric aggregation.

## 2. `mapToInt`: counting, measuring length, and integer statistics

`mapToInt` fits when computed values lie within the `int` range (from `-2_147_483_648` to `2_147_483_647`) and subsequent operations accept 32-bit integers.

Example taking string lengths, keeping only words at least four characters long, and computing the average:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalDouble;

List<String> words = Arrays.asList("Java", "API", "Stream", "Code");

OptionalDouble averageLength = words.stream()
    .mapToInt(String::length)
    .filter(length -> length >= 4)
    .average();

System.out.println(averageLength.orElse(0.0)); // 14 / 3 = 4.666...

IntSummaryStatistics stats = words.stream()
    .mapToInt(String::length)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 17
System.out.println(stats.getMin());     // 3
System.out.println(stats.getMax());     // 6
System.out.println(stats.getAverage()); // 4.25
```

`average()` returns `OptionalDouble` because the stream may be empty; `min()` and `max()` on `IntStream` return `OptionalInt`. With `summaryStatistics()`, the fields `count`, `sum`, `min`, `max`, and `average` are provided in a single object. On an empty stream, `getCount()` is 0; the other statistical values should be interpreted according to the class contract and business rules, rather than treating an empty set's min/max as an actual observation.

### Reading numbers from strings

In input data, numbers are often stored as text. `mapToInt` can be combined directly with `Integer::parseInt`:

```java
import java.util.Arrays;

int[] numbers = Arrays.asList("10", "20", "30").stream()
    .mapToInt(Integer::parseInt)
    .toArray();

System.out.println(Arrays.toString(numbers)); // [10, 20, 30]
```

Here, `parseInt` can throw `NumberFormatException` if the text is invalid or out of `int` range. `mapToInt` **does not** validate data automatically nor skip malformed strings on its own.

## 3. `mapToLong`: reducing `int` overflow risk during aggregation

Individual element values may fit in `int`, yet their **sum** can exceed `int`. In that case, convert to `LongStream` *before performing addition*:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> views = Arrays.asList(1_500_000_000, 1_500_000_000);

long totalViews = views.stream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(totalViews); // 3000000000
```

If replaced with `mapToInt(Integer::intValue).sum()`, the sum uses `int` and overflows. `mapToLong` avoids 32-bit overflow, **yet `long` still has a limit**: `LongStream.sum()` can also overflow when the total exceeds the 64-bit range.

What matters is not only the stream type, but also **when the type conversion happens**:

```java
import java.util.stream.IntStream;

long correct = IntStream.of(50_000, 60_000)
    .mapToLong(n -> (long) n * n)
    .sum();

long wrong = IntStream.of(50_000, 60_000)
    .mapToLong(n -> n * n) // Multiplies using int first, may already overflow!
    .sum();

System.out.println(correct); // 6100000000
System.out.println(wrong);   // Not 6100000000
```

In `(long) n * n`, multiplication uses `long`. In `n * n`, multiplication happens in `int` and only afterward widens the already-overflowed result to `long`.

A practical scenario is summing revenue in the **smallest currency unit** (such as cents or VND) to avoid using floating-point numbers in monetary calculations:

```java
import java.util.Arrays;
import java.util.List;

final class OrderLine {
    final int quantity;
    final long unitPriceInMinorUnit;

    OrderLine(int quantity, long unitPriceInMinorUnit) {
        this.quantity = quantity;
        this.unitPriceInMinorUnit = unitPriceInMinorUnit;
    }
}

List<OrderLine> lines = Arrays.asList(
    new OrderLine(2, 15_000L),
    new OrderLine(3, 20_000L)
);

long totalMinorUnits = lines.stream()
    .mapToLong(line -> Math.multiplyExact(
        line.unitPriceInMinorUnit, (long) line.quantity
    ))
    .sum();

System.out.println(totalMinorUnits); // 90000
```

`Math.multiplyExact` throws `ArithmeticException` if **an individual multiplication** overflows `long`. It does not guard the total from `LongStream.sum()`; if the total can also exceed `long`, a checked addition mechanism like `Math.addExact` (with a valid reduction contract) or `BigInteger` / `BigDecimal` is needed depending on the problem. When decimal monetary calculations are required, data type choices should stem from currency units, rounding rules, and numeric bounds.

## 4. `mapToDouble`: handling floating-point numbers and measurements

`mapToDouble` returns a `DoubleStream` to compute over `double`. It suits measurements, fractional scores, probabilities, or approximate calculations:

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.List;

List<String> measurements = Arrays.asList("1.25", "2.50", "3.75");

double total = measurements.stream()
    .mapToDouble(Double::parseDouble)
    .sum();

DoubleSummaryStatistics summary = measurements.stream()
    .mapToDouble(Double::parseDouble)
    .summaryStatistics();

System.out.println(total);                // 7.5
System.out.println(summary.getCount());   // 3
System.out.println(summary.getAverage()); // 2.5
```

Like `mapToInt`, `Double::parseDouble` can throw an exception if input data is invalid. `Double.parseDouble` can also accept special values such as `NaN` and `Infinity`; simulations or statistics typically need a policy to control them.

### Precision note for `double`

`double` is a binary floating-point number with finite precision. The result of `0.1 + 0.2` does not necessarily represent the exact decimal value `0.3`. `DoubleStream.sum()` does not turn floating-point numbers into exact decimals.

```java
import java.util.stream.DoubleStream;

double result = DoubleStream.of(0.1, 0.2).sum();
System.out.println(result == 0.3); // Do not use == to test floating-point algorithms
System.out.println(Math.abs(result - 0.3) < 1e-12); // true
```

This example illustrates comparing using an **error tolerance**. An appropriate tolerance must be chosen based on data scale, operation characteristics, and application requirements. Do not assume `1e-12` fits every problem.

Be careful when converting from `long` to `double`: every `int` value can be represented exactly as a `double`, yet `long` values whose magnitude exceeds the 53-bit significand limit can **lose integer precision**.

```java
import java.util.stream.LongStream;

long original = 9_007_199_254_740_993L; // 2^53 + 1
double asDouble = LongStream.of(original)
    .mapToDouble(value -> value)
    .findFirst()
    .orElseThrow(IllegalStateException::new);

System.out.println((long) asDouble == original); // false
```

Therefore, do not convert `long` values holding identifiers, large counts, or exact monetary amounts into `double` merely to use `average` without considering precision loss. If absolute decimal precision is needed, `BigDecimal` with `Stream<BigDecimal>` can be used, accepting object overhead and explicit rounding rules.

## 5. Further conversions between the three primitive streams

After the first mapping step, you are working with a **primitive stream**, and the subsequent conversion methods are not identical to those on `Stream<T>`:

| Current source | Conversion method | Result |
| --- | --- | --- |
| `IntStream` | `mapToLong(IntToLongFunction)` | `LongStream` |
| `IntStream` | `mapToDouble(IntToDoubleFunction)` | `DoubleStream` |
| `LongStream` | `mapToInt(LongToIntFunction)` | `IntStream` |
| `LongStream` | `mapToDouble(LongToDoubleFunction)` | `DoubleStream` |
| `DoubleStream` | `mapToInt(DoubleToIntFunction)` | `IntStream` |
| `DoubleStream` | `mapToLong(DoubleToLongFunction)` | `LongStream` |
| `IntStream`, `LongStream`, `DoubleStream` | `mapToObj(...)` | `Stream<R>` |
| `IntStream`, `LongStream`, `DoubleStream` | `boxed()` | `Stream<Integer>`, `Stream<Long>`, `Stream<Double>` |

For widening conversions **with no transformation logic**, `IntStream.asLongStream()`, `IntStream.asDoubleStream()`, and `LongStream.asDoubleStream()` express intent more clearly than `mapToLong(n -> n)` or `mapToDouble(n -> n)`.

```java
import java.util.stream.IntStream;

long sumAsLong = IntStream.rangeClosed(1, 100_000)
    .asLongStream()
    .sum();

double mean = IntStream.rangeClosed(1, 5)
    .asDoubleStream()
    .average()
    .orElseThrow(IllegalStateException::new);

System.out.println(sumAsLong); // 5000050000
System.out.println(mean);      // 3.0
```

Note that `asLongStream` only widens **each individual element** to `long`; it does not fix integer arithmetic results if you already computed and overflowed prior to the conversion step.

### Narrowing `long` or `double` to `int` requires intent

`mapToInt` methods also allow writing cast expressions. However, casting `long` to `int` can drop high bits; casting `double` to `int` truncates the fractional part, turns `NaN` into 0, and clamps out-of-range values to endpoint limits per Java rules.

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

int[] truncated = DoubleStream.of(2.9, -2.9, 5.0)
    .mapToInt(x -> (int) x)
    .toArray();

System.out.println(Arrays.toString(truncated)); // [2, -2, 5]
```

Casting `(int) x` **truncates the fractional part toward zero**, rather than rounding to the nearest integer. If business logic requires rounding, choose an explicit rule such as `Math.round` (which returns `long` for `double`), and handle boundary conditions and type overflow when converting further.

### Converting back to an object stream

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(n -> "item-" + n)
    .collect(java.util.stream.Collectors.toList());

List<Integer> boxed = IntStream.of(4, 5, 6)
    .boxed()
    .collect(java.util.stream.Collectors.toList());

System.out.println(labels); // [item-1, item-2, item-3]
System.out.println(boxed);  // [4, 5, 6]
```

`mapToObj` creates a new object according to a rule, while `boxed` simply wraps primitive numbers into their corresponding wrappers. Use `boxed` when the next API requires `Stream<Integer>` or a `Collector` accepting objects; avoid boxing if subsequent steps only compute over numbers.

## 6. One element to one number: `mapTo*` vs. `flatMapTo*`

`mapToInt`, `mapToLong`, and `mapToDouble` always map **one input element to one numeric value**. If one input element can produce **multiple** numbers (or none), use `flatMapToInt`, `flatMapToLong`, or `flatMapToDouble`.

```java
import java.util.Arrays;
import java.util.List;

List<int[]> batches = Arrays.asList(
    new int[] {2, 4},
    new int[] {7},
    new int[] {1, 3, 5}
);

int[] batchSizes = batches.stream()
    .mapToInt(batch -> batch.length)
    .toArray();

int[] allValues = batches.stream()
    .flatMapToInt(Arrays::stream)
    .toArray();

System.out.println(Arrays.toString(batchSizes)); // [2, 1, 3]
System.out.println(Arrays.toString(allValues));  // [2, 4, 7, 1, 3, 5]
```

`mapToInt(batch -> batch.length)` extracts **one size per array**. `flatMapToInt(Arrays::stream)` flattens the arrays into **a single sequence of numbers**. Choose the method by the output data shape, not solely by the desired primitive type.

## 7. Laziness, data filtering, and error handling

`mapTo*` is an **intermediate operation**: it specifies how to produce numbers without immediately executing the entire conversion. The pipeline begins traversing when a terminal operation is invoked.

```java
import java.util.Arrays;
import java.util.List;

List<String> raw = Arrays.asList(" 10 ", "", "20", "  ");

long total = raw.stream()
    .map(String::trim)
    .filter(text -> !text.isEmpty())
    .mapToLong(Long::parseLong)
    .sum();

System.out.println(total); // 30
```

The `filter` condition removes empty strings before `mapToLong`, yet it does not handle strings like `"N/A"` or numbers exceeding `long`. A serious input pipeline should define a policy for malformed data upfront: throw an error, record failed entries, or drop them with logging. Do not catch every `NumberFormatException` and substitute 0 if **0 is a meaningful business value**, as that silently skews statistical results.

### `null` values and unboxing

```java
import java.util.Arrays;
import java.util.Objects;

long total = Arrays.asList(10, null, 20).stream()
    .filter(Objects::nonNull)
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(total); // 30
```

If `Integer::intValue` or `Integer::longValue` is invoked on `null`, the lambda will throw `NullPointerException`. Primitive streams do not hold `null` elements; you must decide whether to drop, substitute, or reject missing values **before** converting types.

Short-circuiting terminal operations such as `findFirst`, `findAny`, `anyMatch`, or limiting with `limit` can cause only part of the source to be processed. Therefore, do not use a `mapTo*` lambda to perform side effects that must run for every element, such as updating a transaction ledger.

## 8. Parallelism and performance: conditional benefits

Primitive streams generally avoid boxing/unboxing and reduce temporary objects when data is numeric. That **does not guarantee** every primitive pipeline is faster: performance also depends on the source, mapping cost, data volume, allocation count, JVM optimizations, and parallel scheduler.

```java
import java.util.stream.IntStream;

long sumOfSquares = IntStream.rangeClosed(1, 100_000)
    .parallel()
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(sumOfSquares); // 333338333350000
```

In this example, the mapping function depends only on its parameter `n`; each element can be computed independently. `long` addition combines elements deterministically **when the sum does not overflow**. However, `parallel()` has work-splitting and result-merging overhead; for small sources, sequential execution can be faster.

For correct and predictable results:

1. Keep mapping functions **non-interfering** and **stateless** whenever possible.
2. Do not mutate the source collection while the pipeline is traversing it.
3. Do not use `peek`, `mapToInt`, or `mapToDouble` to increment a shared counter and treat that as the primary result.
4. When using a custom `reduce`, choose an associative operation and an identity that satisfy the contract; subtraction is not a suitable example for parallel reduction.
5. With `DoubleStream`, accept that floating-point results can differ slightly depending on element ordering and combination strategy. When financial calculations require exact precision, consider another numeric model.

## 9. Choosing a method by intent

| Need | Suggested pipeline | Points to check |
| --- | --- | --- |
| Total length of strings | `stream.mapToInt(String::length).sum()` | Could the sum exceed `int`? |
| Total of very large view counts | `stream.mapToLong(Integer::longValue).sum()` | Was conversion to `long` done **before** addition? |
| Average of measured values | `stream.mapToDouble(...).average()` | Empty `OptionalDouble`, `NaN`, rounding error. |
| Min/max/count/sum/average stats | `mapToInt(...).summaryStatistics()` or matching type | Empty data and numeric type bounds. |
| Plain widening from `IntStream` to `LongStream` | `intStream.asLongStream()` | Did any prior calculation already overflow? |
| Generating label strings from numbers | `intStream.mapToObj(...)` | Need an object stream, not primitive. |
| Flattening multiple `int[]` arrays | `stream.flatMapToInt(Arrays::stream)` | One source element can yield multiple elements. |
| Collecting integers into `List<Integer>` | `intStream.boxed().collect(...)` | Accept boxing cost when an object collection is required. |

### Practice exercises

**Exercise 1.** Given `List<String> texts = Arrays.asList("A", "Java", "Stream")`, use `mapToInt` to get lengths, then compute sum and average. Predict the results **11** and **11 / 3.0**. Explain why `average` returns `OptionalDouble`.

**Exercise 2.** Given `List<Integer> quantities = Arrays.asList(2_000_000_000, 2_000_000_000)`, compute the sum using `mapToLong`, and compare with `mapToInt`. Why does converting to `long` *after* calling `IntStream.sum()` fail to fix the overflowed result?

**Exercise 3.** Given floating-point numbers `2.2`, `-2.2`, `5.9`, use `DoubleStream.mapToInt(x -> (int) x)` and print the array. Compare with using `Math.round` and explain why the two operations have different semantics.

**Exercise 4.** Given a `List<int[]>` containing `[1, 2]`, `[]`, `[3, 4, 5]`, use `mapToInt` to get the size of each array, then use `flatMapToInt` to collect all numbers into a single `IntStream`. Predict the result of each pipeline.

**Takeaway:** `mapToInt`, `mapToLong`, and `mapToDouble` convert input objects into primitive numeric elements for further processing with `IntStream`, `LongStream`, and `DoubleStream`. Choose the type according to **value range and subsequent operations**, handle missing or invalid data before converting, watch out for integer overflow and floating-point precision error, and only then consider performance optimization or parallel execution.
