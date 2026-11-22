# Converting Between Object Streams and Primitive Streams

In the Java Stream API, pipeline elements can be **objects** (`Stream<T>`) or **primitive values** of three specialized types: `IntStream`, `LongStream`, and `DoubleStream`. Switching to the right Stream type expresses calculations clearly, leverages built-in arithmetic operations, and avoids unnecessary boxing. When the output requires objects, convert back with `mapToObj` or `boxed`.

This lesson belongs to the **Filtering and Transforming Elements** chapter of the **JAVA_STREAM_API** module. This topic directly connects `filter`, `map`, `reduce`, and `collect` with lazy pipelines, while laying the foundation for applying `groupingBy`, custom collectors, `Spliterator`, and semantically correct parallel processing. The focus is choosing the **element type at each stage**, understanding the limits of boxing, `null`, numeric casting, and performance.

## 1. Distinguishing `Stream<T>` and the Three Primitive Streams

Java has the following common Stream types:

| Type | Elements | Example sources | Signature operations |
| --- | --- | --- | --- |
| `Stream<T>` | Object references of type `T`, e.g., `String`, `Order`, `Integer` | `orders.stream()`, `Stream.of("A", "B")` | `map`, `filter`, `collect(Collectors.groupingBy(...))` |
| `IntStream` | `int` | `IntStream.range(0, 10)`, `Arrays.stream(int[])` | `sum`, `average`, `summaryStatistics`, `mapToObj` |
| `LongStream` | `long` | `LongStream.of(1L, 2L)` | `sum`, `average`, `mapToObj` |
| `DoubleStream` | `double` | `DoubleStream.of(0.5, 1.5)` | `sum`, `average`, `mapToObj` |

The three Primitive Streams are not `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>` under different names. They are specialized interfaces operating directly on `int`, `long`, and `double`, offering arithmetic methods like `sum()` that `Stream<T>` does not provide directly.

For example, with `Stream<Integer>`, you cannot call `sum()` directly:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

Stream<Integer> objectNumbers = Stream.of(10, 20, 30);
IntStream primitiveNumbers = IntStream.of(10, 20, 30);

// objectNumbers.sum(); // Does not compile: Stream<Integer> has no sum().
int total = primitiveNumbers.sum(); // 60
```

`Stream.of(10, 20, 30)` creates a `Stream<Integer>` because the primitive values are boxed into `Integer`. `IntStream.of(10, 20, 30)` creates an `IntStream` source directly. Note that each Stream can only be **consumed once** by a terminal operation; the example above calls `sum()` once on `primitiveNumbers`.

### Conversion Diagram

```text
Stream<T>   -- mapToInt(ToIntFunction<T>) ------> IntStream
            -- mapToLong(ToLongFunction<T>) ----> LongStream
            -- mapToDouble(ToDoubleFunction<T>) -> DoubleStream

IntStream   -- mapToObj(IntFunction<R>) -------> Stream<R>
            -- boxed() ------------------------> Stream<Integer>

LongStream  -- mapToObj(LongFunction<R>) ------> Stream<R>
            -- boxed() ------------------------> Stream<Long>

DoubleStream -- mapToObj(DoubleFunction<R>) ---> Stream<R>
             -- boxed() -----------------------> Stream<Double>
```

Crucially: `mapToInt` on `Stream<T>` does not cast the entire object to `int`; it takes **a function that extracts or computes an `int`** from each object.

## 2. From `Stream<T>` to `IntStream`, `LongStream`, `DoubleStream`

When an object stream contains numeric information, choose the method based on the **primitive type of the result**.

| Method on `Stream<T>` | Accepted functional interface | Abstract method | Result |
| --- | --- | --- | --- |
| `mapToInt` | `ToIntFunction<? super T>` | `int applyAsInt(T value)` | `IntStream` |
| `mapToLong` | `ToLongFunction<? super T>` | `long applyAsLong(T value)` | `LongStream` |
| `mapToDouble` | `ToDoubleFunction<? super T>` | `double applyAsDouble(T value)` | `DoubleStream` |

### 2.1. `mapToInt`: Extracting `int` Values

Suppose we have a list of product names and want the **total number of UTF-16 characters** across non-blank names:

```java
import java.util.List;

List<String> productNames = List.of("Bút", "Sách", "Máy tính");

int totalUtf16Units = productNames.stream()
    .filter(name -> !name.isBlank())
    .mapToInt(String::length)
    .sum();

System.out.println(totalUtf16Units); // 3 + 4 + 8 = 15
```

Stages:

1. `stream()` produces `Stream<String>`.
2. `filter` retains non-blank names, still `Stream<String>`.
3. `mapToInt(String::length)` converts each name to an `int`, producing `IntStream`.
4. `sum()` is the terminal operation summing the integers.

`String.length()` counts **UTF-16 code units**. If business rules require counting Unicode code points instead of UTF-16 code units, use `name.codePointCount(0, name.length())`; do not loosely refer to both quantities as "display character count".

### 2.2. `mapToLong`: Aggregating `long` Fields

Many applications represent money as integers in the smallest currency unit to avoid binary floating-point errors. For example, order values stored as `long` (VND):

```java
record Order(String id, long amountVnd, boolean paid) {}

List<Order> orders = List.of(
    new Order("O-01", 1_500_000L, true),
    new Order("O-02",   800_000L, false),
    new Order("O-03", 2_300_000L, true)
);

long paidRevenue = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountVnd)
    .sum();

System.out.println(paidRevenue); // 3800000
```

In this example, `Order::amountVnd` matches `ToLongFunction<Order>`. Use `mapToLong` because the field is `long`; using `mapToInt(order -> (int) order.amountVnd())` risks data loss when values exceed the `int` range.

`long` also has limits: `sum()` can **overflow** when the sum exceeds `Long.MAX_VALUE` or falls below `Long.MIN_VALUE`. If the business domain requires magnitudes beyond `long`, consider `BigInteger` or `BigDecimal` according to the monetary model, with an appropriate aggregation on `Stream<T>`.

### 2.3. `mapToDouble`: Computing Floating-Point Averages or Statistics

```java
record Reading(String sensor, double temperatureC) {}

List<Reading> readings = List.of(
    new Reading("S-01", 22.0),
    new Reading("S-02", 24.5),
    new Reading("S-03", 26.0)
);

double averageC = readings.stream()
    .mapToDouble(Reading::temperatureC)
    .average()
    .orElseThrow();

System.out.println(averageC); // 24.166666666666668
```

`average()` returns `OptionalDouble` because the stream may be empty. Only call `orElseThrow()` when the data is guaranteed non-empty; for arbitrary inputs, handle the missing-data case:

```java
double averageOrZero = readings.stream()
    .mapToDouble(Reading::temperatureC)
    .average()
    .orElse(0.0);
```

A default value of `0.0` can carry misleading business semantics ("no sensor readings" does not mean "temperature is 0"). In many cases it is better to keep `OptionalDouble` to represent absent data.

### 2.4. Using Primitive Streams for Numeric Statistics

After converting types, you can use:

```java
import java.util.IntSummaryStatistics;

List<Integer> scores = List.of(7, 9, 8, 10);

IntSummaryStatistics stats = scores.stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 34
System.out.println(stats.getMin());     // 7
System.out.println(stats.getMax());     // 10
System.out.println(stats.getAverage()); // 8.5
```

`summaryStatistics()` reports count, sum, min, max, and average in a **single pipeline traversal**. With `IntStream` and `LongStream`, `sum()` and total statistics can still experience integer overflow. With `DoubleStream`, results also follow floating-point rules, including `NaN` and infinities.

## 3. From Primitive Streams Back to Object Streams

When you need to turn primitive numbers into **arbitrary objects**, use `mapToObj`. When you only need the **corresponding wrapper type**, use `boxed`.

### 3.1. `mapToObj`: Creating Objects by Business Rules

This method takes a function converting a primitive value into an object:

| Source | Method | Accepted function | Result type |
| --- | --- | --- | --- |
| `IntStream` | `mapToObj(IntFunction<R>)` | `int` | `Stream<R>` |
| `LongStream` | `mapToObj(LongFunction<R>)` | `long` | `Stream<R>` |
| `DoubleStream` | `mapToObj(DoubleFunction<R>)` | `double` | `Stream<R>` |

Example generating seat IDs from indices:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> seatIds = IntStream.rangeClosed(1, 4)
    .mapToObj(i -> "A-" + i)
    .toList();

System.out.println(seatIds); // [A-1, A-2, A-3, A-4]
```

`IntStream.rangeClosed(1, 4)` emits four values: 1, 2, 3, and 4. `mapToObj` creates `Stream<String>`, so `toList()` returns `List<String>`.

Example with domain objects:

```java
record Tier(int level, String label) {}

List<Tier> tiers = IntStream.rangeClosed(1, 3)
    .mapToObj(level -> new Tier(level, "Bậc " + level))
    .toList();

System.out.println(tiers);
// [Tier[level=1, label=Bậc 1], Tier[level=2, label=Bậc 2],
//  Tier[level=3, label=Bậc 3]]
```

You do not need `boxed()` before `mapToObj` in the case above: `mapToObj` receives `int` directly and constructs the exact target objects.

### 3.2. `boxed()`: Creating a Wrapper Stream

`boxed()` converts each primitive value into its corresponding wrapper object:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> ids = IntStream.rangeClosed(1, 5)
    .boxed()
    .toList();

System.out.println(ids); // [1, 2, 3, 4, 5]
```

Correspondingly:

- `IntStream.boxed()` returns `Stream<Integer>`.
- `LongStream.boxed()` returns `Stream<Long>`.
- `DoubleStream.boxed()` returns `Stream<Double>`.

If you want to produce `Stream<Integer>`, `boxed()` is shorter and expresses intent more clearly than `mapToObj(Integer::valueOf)`. Conversely, to produce `Stream<String>` or `Stream<OrderView>`, use `mapToObj`.

**Memory note:** `boxed()` can cause boxing of values; calling `toList()` also retains all results in a list. Use these two steps when the API or output genuinely requires `List<Integer>`, rather than boxing just to compute a sum.

### 3.3. When an Object Stream Collector Is Needed

General collectors like `groupingBy` are APIs on `Stream<T>`. When you want to group integers by parity, you can convert `IntStream` to `Stream<Integer>`:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<String, Long> countsByParity = IntStream.rangeClosed(1, 10)
    .boxed()
    .collect(Collectors.groupingBy(
        number -> number % 2 == 0 ? "Chẵn" : "Lẻ",
        Collectors.counting()
    ));

System.out.println(countsByParity.get("Chẵn")); // 5
System.out.println(countsByParity.get("Lẻ"));   // 5
```

`boxed()` is appropriate because `groupingBy` expects `Integer` objects. Nevertheless, if the task only needs to count even numbers, `IntStream.rangeClosed(1, 10).filter(n -> n % 2 == 0).count()` is more direct and avoids boxing.

### 3.4. A Round-Trip Conversion Chain

```java
List<String> labels = List.of("Mật ong", "Sữa", "Bánh")
    .stream()                       // Stream<String>
    .mapToInt(String::length)       // IntStream
    .filter(length -> length >= 4) // IntStream
    .mapToObj(length -> length + " UTF-16 units") // Stream<String>
    .toList();                      // List<String>

System.out.println(labels);
// [7 UTF-16 units, 4 UTF-16 units]
```

In this example, after `mapToInt` we **no longer retain the original product name**, only its length. If you need both the name and its length, map directly to an object holding both fields from the original `Stream<String>`:

```java
record NameLength(String name, int utf16Units) {}

List<NameLength> details = List.of("Mật ong", "Sữa", "Bánh")
    .stream()
    .map(name -> new NameLength(name, name.length()))
    .toList();
```

Do not switch to a Primitive Stream if doing so discards information needed in a later step.

## 4. Converting Between the Three Primitive Streams

Besides converting with objects, Java supports converting among primitive numeric streams through several specialized methods.

### 4.1. Numeric Widening: `asLongStream` and `asDoubleStream`

`IntStream` has `asLongStream()` and `asDoubleStream()`; `LongStream` has `asDoubleStream()`.

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

long totalAsLong = IntStream.of(1, 2, 3)
    .asLongStream()
    .sum();

double totalAsDouble = LongStream.of(1L, 2L, 3L)
    .asDoubleStream()
    .sum();

System.out.println(totalAsLong);   // 6
System.out.println(totalAsDouble); // 6.0
```

These two methods fit when converting to a type with a different value domain. However, **widening to `double` does not guarantee exact preservation of every `long` value**: `double` has 53 bits of significand precision, so many large integers can no longer be represented exactly. For large monetary amounts or integer IDs, keep them as `long` or a numeric type with suitable precision.

### 4.2. `mapToLong`, `mapToDouble`, and Intentional Type Conversions

Primitive Streams also provide mapping methods between numeric types. For example:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

LongStream longValues = IntStream.of(1, 2, 3)
    .mapToLong(n -> n * 1_000_000L);

DoubleStream ratios = LongStream.of(1L, 2L, 3L)
    .mapToDouble(n -> n / 10.0);

IntStream rounded = DoubleStream.of(1.2, 2.6, 3.1)
    .mapToInt(value -> (int) Math.round(value));

System.out.println(longValues.sum());                   // 6000000
System.out.println(java.util.Arrays.toString(ratios.toArray())); // [0.1, 0.2, 0.3]
System.out.println(java.util.Arrays.toString(rounded.toArray())); // [1, 3, 3]
```

When narrowing from `long` to `int`, values can exceed bounds. If the requirement is **detecting overflow instead of truncating data**, use `Math.toIntExact`:

```java
import java.util.stream.LongStream;

int[] safeValues = LongStream.of(10L, 20L, 30L)
    .mapToInt(Math::toIntExact)
    .toArray();

System.out.println(java.util.Arrays.toString(safeValues)); // [10, 20, 30]

// If a value is outside the int range, Math.toIntExact throws ArithmeticException.
```

Converting from `double` to an integer type also depends on rounding rules and handling `NaN` and infinity. For example, `(int) 2.9` gives `2` (truncating toward 0), whereas `Math.round(2.9)` gives `3L` before casting to `int`. When values can fall outside the `int` range, validate bounds before converting.

### Quick Orientation Table

| Have | Want | Typical method |
| --- | --- | --- |
| `IntStream` | `LongStream` | `asLongStream()`, or `mapToLong(...)` to transform values |
| `IntStream` | `DoubleStream` | `asDoubleStream()`, or `mapToDouble(...)` |
| `LongStream` | `DoubleStream` | `asDoubleStream()`, or `mapToDouble(...)` |
| `LongStream` | `IntStream` | `mapToInt(...)`, consider `Math.toIntExact` |
| `DoubleStream` | `IntStream` / `LongStream` | `mapToInt(...)` / `mapToLong(...)` with explicit numeric conversion rules |
| Any Primitive Stream | Any `Stream<R>` | `mapToObj(...)` |
| Any Primitive Stream | Corresponding `Stream<Wrapper>` | `boxed()` |

## 5. Handling `null` During Unboxing

With a `Stream<Integer>` that may contain `null`, calling `Integer::intValue` causes `NullPointerException` when encountering a null element. Never assume every `List<Integer>` is free of `null`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<Integer> values = Arrays.asList(10, null, 20);

int sumNonNull = values.stream()
    .filter(Objects::nonNull)
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(sumNonNull); // 30
```

Here, the `null` policy is **skip**. That is a business decision, not a mandatory rule. If `null` indicates corrupt data, you can proactively throw an exception or handle it in the input validation layer. If `null` genuinely means `0`, you can map it to `0`:

```java
int sumNullAsZero = values.stream()
    .mapToInt(value -> value == null ? 0 : value)
    .sum();
```

These approaches lead to different meanings when computing `count()`, `average()`, or sample statistics. For instance, "skip missing samples" differs from "treat missing samples as 0" when computing an average.

With `Stream<Long>` and `Stream<Double>`, you can use `Long::longValue` and `Double::doubleValue` respectively, with the same requirement to check for `null` before unboxing.

## 6. How Do `map`, `mapToX`, and `flatMapToX` Differ?

Not every transformation turns one input element into exactly one output element. Distinguish:

| Method | Receives input | Result per input | Stream type after operation |
| --- | --- | --- | --- |
| `map(Function<T, R>)` | `T` | One `R` | `Stream<R>` |
| `mapToInt(ToIntFunction<T>)` | `T` | One `int` | `IntStream` |
| `mapToLong(ToLongFunction<T>)` | `T` | One `long` | `LongStream` |
| `mapToDouble(ToDoubleFunction<T>)` | `T` | One `double` | `DoubleStream` |
| `flatMapToInt(Function<T, IntStream>)` | `T` | 0 to many `int` | `IntStream` |
| `flatMapToLong(Function<T, LongStream>)` | `T` | 0 to many `long` | `LongStream` |
| `flatMapToDouble(Function<T, DoubleStream>)` | `T` | 0 to many `double` | `DoubleStream` |

For example, each string contains **multiple Unicode code points**, so we use `flatMapToInt` instead of `mapToInt`:

```java
import java.util.List;

List<String> tokens = List.of("AB", "😀");

int[] codePoints = tokens.stream()
    .flatMapToInt(String::codePoints)
    .toArray();

System.out.println(java.util.Arrays.toString(codePoints));
// [65, 66, 128512]
```

`String::codePoints` returns an `IntStream` from each string; `flatMapToInt` merges the sub-streams into a flat `IntStream`. If you write `tokens.stream().map(String::codePoints)`, the result is `Stream<IntStream>`, i.e., a **Stream of sub-Stream objects**, not flattened. If you write `mapToInt(String::length)`, you only get each string's length, not the inner code points.

By `flatMapToInt`'s contract, sub-Streams are closed after their contents are fed into the result stream. Even so, with I/O sources or special resources, manage lifecycle and errors explicitly.

## 7. Complete Example: Revenue Report from an Order List

The following example uses **Java 17+**, as it uses `record` and `Stream.toList()`. It illustrates three scenarios: summing on a `LongStream`, generating output labels with `mapToObj`, and aggregating by key with a `Stream<Order>` collector.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ObjectPrimitiveStreamDemo {
    record Order(String id, String region, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc", 1_500_000L, true),
            new Order("O-02", "Nam",   700_000L, true),
            new Order("O-03", "Bắc", 2_000_000L, false),
            new Order("O-04", "Bắc",   300_000L, true)
        );

        // 1. Stream<Order> -> LongStream -> long.
        long paidRevenue = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();

        // 2. Stream<Order> -> LongStream -> Stream<String> -> List<String>.
        List<String> paidAmountLabels = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .mapToObj(amount -> "Đã thanh toán: " + amount + " VND")
            .toList();

        // 3. Keep Order to group by region and sum amountVnd.
        Map<String, Long> revenueByRegion = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));

        System.out.println(paidRevenue);
        System.out.println(paidAmountLabels);
        System.out.println(revenueByRegion.get("Bắc"));
        System.out.println(revenueByRegion.get("Nam"));
    }
}
```

Output:

```text
2500000
[Đã thanh toán: 1500000 VND, Đã thanh toán: 700000 VND, Đã thanh toán: 300000 VND]
1800000
700000
```

Analysis:

- In the summing step, only `amountVnd` is needed, so `mapToLong` is the direct expression.
- In the label-creation step, `mapToObj` converts each `long` value into a `String`. The `id` and `region` fields are no longer available after `mapToLong`.
- In the revenue-grouping step, `region` must stay paired with `amountVnd`; switching to `LongStream` from the start would lose the grouping key. `Collectors.summingLong` is the right choice on `Stream<Order>`.
- Each calculation starts with a fresh `orders.stream()`, since a Stream can only be consumed once.

Note that `Collectors.summingLong` also uses `long` addition and carries the same overflow risk as `LongStream.sum()` when data exceeds range.

## 8. Laziness, Stateful Data, and Parallel Processing

`mapToInt`, `mapToLong`, `mapToDouble`, `mapToObj`, `boxed`, and `flatMapToInt` are **intermediate operations**. They create a new pipeline and typically do not process elements right away; a terminal operation triggers traversal:

```java
List<String> names = List.of("A", "BBB", "CC");

var lengths = names.stream()
    .mapToInt(String::length); // Result calculation not requested yet.

int sum = lengths.sum();       // 1 + 3 + 2 = 6

// lengths.count();            // Wrong: Stream has already been consumed.
```

Inside mapping functions, avoid mutating the traversed source or updating shared state. Example that is unsafe in parallel execution:

```java
// Do not use; especially dangerous if parallelStream() is added.
long[] total = {0L};

orders.stream().mapToLong(order -> {
    total[0] += order.amountVnd(); // Side effect outside the pipeline.
    return order.amountVnd();
}).sum();

// Express directly according to the desired result:
long paidTotal = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountVnd)
    .sum();
```

In the first snippet, `total[0]` mutates external state and the addition could even be counted twice if both the variable and `sum()` are used. With parallel Streams, unsynchronized shared updates can cause race conditions and wrong results.

`parallelStream()` is not automatically faster than a sequential Stream. Splitting data, boxing during `boxed()` stages, merging results, ordering, and collector overhead all affect speed. For independent numeric computations on sufficiently large datasets, Primitive Streams can be a good candidate to **consider** parallelizing; verify with real measurements.

For stateful operations like `distinct`, `sorted`, grouping operations, or ordered data sources, memory and coordination overhead can increase. `Spliterator` affects how well a source splits for parallelism, though you rarely need to write a custom `Spliterator` just to convert between `Stream<T>` and Primitive Streams.

## 9. Performance: When Does Boxing Matter?

Wrappers like `Integer`, `Long`, and `Double` are **objects**, whereas `int`, `long`, and `double` are primitive values. Boxing/unboxing can introduce conversion and allocation overhead; actual optimization depends on the JVM and context.

Comparing two ways to sum:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

// Option A: reduce on Stream<Integer>.
int sumBoxed = numbers.stream()
    .reduce(0, Integer::sum);

// Option B: use specialized IntStream.
int sumPrimitive = numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(sumBoxed == sumPrimitive); // true
```

In Option A, `reduce` operates on `Integer`; Option B only has `Integer` at the source, then converts to `int` and computes with `IntStream`. Option B usually expresses numeric intent more clearly. However, you cannot conclude speed ratios from these two snippets alone: JIT optimizations, source size, and overall pipeline cost must be measured.

When comparing, you should:

1. Measure on representative data and realistic execution paths.
2. Use an appropriate benchmarking tool such as **JMH**, with warm-up.
3. Verify both calculations return identical results and follow the same overflow/`null` rules.
4. Check memory, boxing, and stability before changing code for performance.

Primitive Streams do not solve every performance issue: creating an output `List<Integer>` still stores objects; converting integers to `double` can lose precision; integer reductions can still overflow.

## 10. Common Mistakes

| Mistake | Consequence | Proper approach |
| --- | --- | --- |
| Calling `sum()` directly on `Stream<Integer>` | Does not compile | Convert via `mapToInt(Integer::intValue)` then `sum()`. |
| Calling `mapToInt` yet still trying `Stream<T>`-only operations like `groupingBy` | No `collect(Collector)` on `IntStream` | Keep objects or use `boxed()`/`mapToObj` if a general collector is truly needed. |
| Using `boxed().map(...)` when `mapToObj(...)` suffices | Unnecessary boxing | Use `mapToObj` to create result objects directly. |
| Narrowing `long` to `int` via silent cast | Large values can be truncated | Use `Math.toIntExact` when overflow detection is needed. |
| Treating `asDoubleStream` as lossless for all `long` values | Precision loss on large integers | Keep `long`/`BigInteger` or use appropriate-precision arithmetic. |
| Unboxing a `null` element | `NullPointerException` | Define `null`-handling rules before `mapToInt`/`mapToLong`. |
| Switching to a Primitive Stream too early | Loses context needed in later steps | Stay on `Stream<T>` while multiple object fields are still needed. |
| Using one Stream for multiple terminal operations | `IllegalStateException` | Create a fresh Stream from the source for each computation. |
| Using `parallel()` and mutating external variables/collections in `mapToX` | Race conditions, wrong results | Use proper reductions/aggregations and avoid shared state. |
| Assuming Primitive Streams are always faster than every loop | Speculative optimization | Measure on representative data and workloads. |

## 11. Practice Exercises

### Exercise 1: Student Scores

Given `List<Student>`, where each `Student` has `name` and `int score`. Filter students scoring at least 5, compute total score, average score, and highest score using `mapToInt`. Answer: when the list is empty, how do `average()` and `max()` behave differently from `sum()`?

### Exercise 2: Generating a List of Labels

Use `IntStream.rangeClosed(1, 12)` to create a `List<String>` containing `"Tháng 1"` through `"Tháng 12"`. Explain why `mapToObj` should be used and `boxed()` is unnecessary.

### Exercise 3: Grouping Numbers by Parity

Use `IntStream.rangeClosed(1, 20)` combined with `boxed()` and `Collectors.groupingBy` to produce `Map<Boolean, List<Integer>>`, where key `true` holds even numbers. Then count only even numbers using `IntStream.filter(...).count()` and compare output memory for the two goals.

### Exercise 4: Total Amount by Region

Given a list of orders with `region` and `amountVnd`. Produce a total revenue report across all orders using `mapToLong`, then build `Map<String, Long>` by region with `Collectors.groupingBy` and `Collectors.summingLong`. Explain why the second task must retain the order objects.

### Exercise 5: Safe Type Conversion

Given a `LongStream` containing `1L`, `2_147_483_647L`, and `2_147_483_648L`. Try `mapToInt(Math::toIntExact)` and explain on which element the exception occurs. Then try converting the same stream to `DoubleStream` and investigate the condition for preserving integer exactness.

### Exercise 6: Handling `null`

Given `List<Integer>` containing `[10, null, 20]`. Compare the average under two policies: **skip `null`** and **treat `null` as 0**. Explain why the results differ and pick the right policy according to data semantics.

## 12. Knowledge Self-Check

- How do `Stream<Integer>` and `IntStream` differ in element type and aggregation API?
- When should you use `mapToLong` instead of `mapToInt`?
- How does `mapToObj` differ from `boxed` in result type and intended use?
- Why is `Collectors.groupingBy` typically called on `Stream<T>` rather than directly on `IntStream`?
- What problem does `flatMapToInt` solve that `mapToInt` does not?
- What happens when unboxing an `Integer` that is `null`?
- Why can converting `long` to `double` lose precision even though it is a widening conversion?
- Why can switching to a Primitive Stream too early leave you without enough data to group by a key?

**Takeaway:** When you need **numeric calculations**, use `mapToInt`, `mapToLong`, or `mapToDouble` to convert `Stream<T>` to a Primitive Stream. When you need to **create result objects**, use `mapToObj`; when you need the **corresponding wrapper**, use `boxed`. Choosing the right moment to switch types keeps pipelines clear, preserves business data, and avoids bugs involving `null`, overflow, precision loss, and shared state.
