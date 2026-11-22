# IntStream, LongStream, DoubleStream, and Reducing Boxing in Java Numeric Aggregation

## 1. The Problem: Does Numeric Aggregation Need Integer, Long, or Double Objects?

The Java Stream API lets you process datasets using transformations like `filter` and `map`, and aggregations like `sum`, `average`, `min`, and `max`. When elements are *primitive* values `int`, `long`, or `double`, Java provides three specialized stream types:

- `IntStream` processes `int` elements.
- `LongStream` processes `long` elements.
- `DoubleStream` processes `double` elements.

All three live in the `java.util.stream` package. Unlike `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>`, their elements are passed through specialized operations as primitive values. Therefore, they **can reduce boxing/unboxing and intermediate object allocations** when computing sums, averages, or extrema.

**Boxing** converts a primitive into a wrapper, such as `int → Integer`. **Unboxing** extracts the primitive from a wrapper, such as `Integer → int`. Java can perform both conversions automatically, but they are still operations with cost and can create objects or trigger `NullPointerException` when unboxing a `null` value.

An example with the same summation goal:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = List.of(10, 20, 30);

// Already have List<Integer>: convert once to IntStream for primitive calculation.
int sumFromList = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 60

// Create data as primitives right from the source.
int sumFromPrimitive = IntStream.of(10, 20, 30).sum(); // 60
~~~

Both produce 60. The optimal choice depends on the data source: if data is already held in a `List<Integer>`, unboxing at the boundary is necessary; if data can be created and kept as primitives from the start, `IntStream` avoids creating wrappers just to compute a sum.

## 2. Distinguishing Stream<T> from the Three Primitive Streams

| Aspect | `Stream<Integer>` (similar for Long/Double) | `IntStream` | `LongStream` | `DoubleStream` |
|---|---|---|---|---|
| Element type | `Integer` object | `int` | `long` | `double` |
| Has `sum()`? | No | Yes, returns `int` | Yes, returns `long` | Yes, returns `double` |
| Has `average()`? | No | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |
| `min()`, `max()` | `Optional<T>` with comparator/natural order | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `summaryStatistics()` | No direct equivalent method | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| `toArray()` | `T[]` with proper constructor; no-arg returns `Object[]` | `int[]` | `long[]` | `double[]` |
| `boxed()` | Not needed because already an object stream | `Stream<Integer>` | `Stream<Long>` | `Stream<Double>` |
| `map(...)` | Transforms object → object | `int → int` | `long → long` | `double → double` |

`Stream<T>` is an abstraction for reference objects; it does not provide `sum()` because an arbitrary `T` is not necessarily a number, nor is there a default sum result type. Meanwhile, primitive streams know the element type ahead of time and therefore provide specialized arithmetic operations.

One thing to note: `IntStream` cannot contain `null`. This eliminates null errors from the primitive elements themselves, though if the source is a `Stream<Integer>` containing `null`, `mapToInt(Integer::intValue)` can still throw `NullPointerException` when unboxing.

Primitive streams are only specialized for `int`, `long`, and `double`. There is no `ByteStream`, `ShortStream`, `CharStream`, or `FloatStream` in the standard Stream API. Values of `byte`, `short`, and `char` can be widened into `IntStream` when appropriate; `float` is typically handled via `DoubleStream` when floating-point operations are needed.

## 3. Ways to Create Primitive Streams

### 3.1. From Values and Primitive Arrays

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

IntStream ints = IntStream.of(2, 4, 6);
LongStream longs = LongStream.of(1_000_000_000L, 2_000_000_000L);
DoubleStream doubles = DoubleStream.of(1.5, 2.5, 3.5);

int[] readings = {4, 6, 8};
int total = Arrays.stream(readings).sum(); // 18
~~~

`Arrays.stream(int[])` returns an `IntStream`. Similarly, `Arrays.stream(long[])` returns a `LongStream` and `Arrays.stream(double[])` returns a `DoubleStream`. This is the natural path when data already resides in a primitive array.

An easy mistake with `Stream.of(array)`:

~~~java
int[] readings = {4, 6, 8};

long a = Arrays.stream(readings).count(); // 3
long b = java.util.stream.Stream.of(readings).count(); // 1
~~~

`Stream.of(readings)` in this example is a stream containing **one `int[]` array object**, not three integers. To traverse the numeric elements, use `Arrays.stream(readings)` or `IntStream.of(readings)`.

### 3.2. Generating Contiguous Sequences with range and rangeClosed

~~~java
IntStream.range(1, 5);         // 1, 2, 3, 4
IntStream.rangeClosed(1, 5);   // 1, 2, 3, 4, 5
LongStream.range(10L, 13L);   // 10, 11, 12
LongStream.rangeClosed(10L, 13L); // 10, 11, 12, 13
~~~

`range(startInclusive, endExclusive)` includes the start and excludes the end; `rangeClosed(startInclusive, endInclusive)` includes both ends. Both families of methods exist on `IntStream` and `LongStream`; `DoubleStream` **does not have** `range`/`rangeClosed`.

`range` is very useful for array indices, counting loops, and contiguous range data, though be mindful of boundary correctness before replacing ordinary loops.

### 3.3. From an Object Stream via mapToInt, mapToLong, mapToDouble

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> texts = List.of("7", "10", "13");

int sum = texts.stream()
        .mapToInt(Integer::parseInt)
        .sum(); // 30

long totalLengths = Stream.of("Java", "Stream")
        .mapToLong(s -> s.length())
        .sum(); // 10

double average = Stream.of("1.5", "2.5", "3.5")
        .mapToDouble(Double::parseDouble)
        .average()
        .orElseThrow(); // 2.5
~~~

`mapToInt`/`mapToLong`/`mapToDouble` are the conversion boundary from an object stream to a primitive stream. After conversion, filtering, mapping, and numeric aggregation can proceed without repeatedly converting each element to a wrapper.

## 4. Numeric Aggregations: sum, average, min, max, count

Example:

~~~java
int sum = IntStream.of(2, 4, 6).sum(); // 12
double average = IntStream.of(2, 4, 6).average().orElseThrow(); // 4.0
int minimum = IntStream.of(2, 4, 6).min().orElseThrow(); // 2
int maximum = IntStream.of(2, 4, 6).max().orElseThrow(); // 6
long count = IntStream.of(2, 4, 6).count(); // 3
~~~

`count()` returns `long`, not `int`. `average()` on all three primitive streams returns `OptionalDouble`, because the average of integers can be fractional: for example, the average of `1` and `2` is `1.5`.

`min()`/`max()` return `OptionalInt`, `OptionalLong`, or `OptionalDouble` respectively; they do not return a primitive directly because the stream may be empty.

### 4.1. Handling Empty Streams Properly

~~~java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

int sum = IntStream.empty().sum();       // 0
long count = IntStream.empty().count();  // 0
OptionalDouble avg = IntStream.empty().average(); // OptionalDouble.empty()
~~~

For `min()`, `max()`, and `average()`, choose how to handle empty streams according to business requirements:

~~~java
double fallback = IntStream.empty().average().orElse(0.0); // 0.0

// Only use when the dataset is required to be non-empty.
// double required = IntStream.empty().average().orElseThrow();
~~~

`orElse(0.0)` is an application-specific decision: mathematically, the average of an empty set is not 0. If 0 could be misinterpreted as a valid measurement, it is better to keep `OptionalDouble` or report an error explicitly.

### 4.2. summaryStatistics: Aggregating Multiple Metrics in One Pass

Instead of creating separate streams for `count`, `sum`, `min`, `max`, and `average`, you can obtain a single statistics object:

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.of(2, 4, 6).summaryStatistics();

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 12
System.out.println(stats.getMin());     // 2
System.out.println(stats.getMax());     // 6
System.out.println(stats.getAverage()); // 4.0
~~~

Similarly:

- `LongStream.summaryStatistics()` returns `LongSummaryStatistics`.
- `DoubleStream.summaryStatistics()` returns `DoubleSummaryStatistics`.

The statistics classes provide sum, count, extrema, and average. For empty streams, summary-statistics extrema and average use API default values; you must **check `getCount()`** before treating the result as a meaningful extremum or average.

`summaryStatistics()` is also a **terminal operation**: it consumes the stream. You cannot subsequently call `sum()` on the same stream instance.

## 5. Transforming Primitives Then Aggregating: filter, map, reduce

Primitive streams have intermediate operations `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`, `skip`, and others taking primitive-accepting functions:

~~~java
int totalEvenSquares = IntStream.rangeClosed(1, 5)
        .filter(n -> n % 2 == 0) // 2, 4
        .map(n -> n * n)         // 4, 16
        .sum();                  // 20
~~~

In this chain, `filter` and `map` operate on `int` via specialized functional interfaces `IntPredicate` and `IntUnaryOperator`. Data does not need to become `Integer` between operations.

Some key callback types:

| Primitive stream | `filter` takes | `map` takes | `forEach` takes |
|---|---|---|---|
| `IntStream` | `IntPredicate` | `IntUnaryOperator` | `IntConsumer` |
| `LongStream` | `LongPredicate` | `LongUnaryOperator` | `LongConsumer` |
| `DoubleStream` | `DoublePredicate` | `DoubleUnaryOperator` | `DoubleConsumer` |

### 5.1. reduce with Custom Combining Operations

~~~java
int product = IntStream.rangeClosed(1, 4)
        .reduce(1, (a, b) -> a * b); // 24

int biggest = IntStream.of(4, 9, 2)
        .reduce(Integer::max)
        .orElseThrow(); // 9
~~~

`reduce(identity, operator)` returns a primitive (yielding the identity value if the stream is empty). `reduce(operator)` without an identity returns an `OptionalInt`/`OptionalLong`/`OptionalDouble`. Use an **associative** combining operation and matching identity so it remains correct even when the stream runs in parallel. For example, addition with identity 0, multiplication with identity 1; do not use subtraction as a general reduction if you need stable results under parallel partitioning.

When you only need a sum, prefer `sum()` over `reduce(0, Integer::sum)` because the code expresses intent more clearly.

### 5.2. You Do Not Always Need a Custom reduce

`sum`, `average`, and `summaryStatistics` already cover common aggregations. If you need to collect into a specialized structure without boxing every element, `IntStream` provides an overload `collect(supplier, accumulator, combiner)` whose accumulator is `ObjIntConsumer<R>`:

~~~java
String joined = IntStream.of(2, 3, 5)
        .collect(
            StringBuilder::new,
            (builder, value) -> builder.append(value),
            (left, right) -> left.append(right)
        )
        .toString(); // "235"
~~~

The accumulator receives a primitive `int`. For parallel tasks, the supplier must create a separate container per branch and the combiner must merge properly, without relying on a shared external container. Simple string joining may not need a custom collector; this example illustrates the specialized mechanism.

## 6. Converting Back and Forth: boxed(), mapToObj(), mapToInt()

When downstream APIs require objects, **box only at the boundary where it is actually necessary**.

### 6.1. Primitive Stream → Wrapper Stream via boxed()

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> ids = IntStream.of(3, 1, 3, 2)
        .distinct()
        .sorted()
        .boxed()
        .toList(); // [1, 2, 3]
~~~

`boxed()` converts:

| Input | Result |
|---|---|
| `IntStream.boxed()` | `Stream<Integer>` |
| `LongStream.boxed()` | `Stream<Long>` |
| `DoubleStream.boxed()` | `Stream<Double>` |

`toList()` in the example is a terminal operation on `Stream<Integer>` (available since Java 16); `IntStream` has no `toList()` method to create a `List<Integer>` directly. The `boxed()` step is necessary when the required output type is a list of wrappers.

You should only convert to wrappers when objects are actually required, such as calling an API that accepts `List<Integer>`. If you are only computing a sum, `IntStream.of(...).sum()` is concise and avoids that boxing boundary.

### 6.2. Primitive → Other Object Types via mapToObj()

~~~java
List<String> labels = IntStream.of(2, 3, 5)
        .mapToObj(n -> "id-" + n)
        .toList(); // [id-2, id-3, id-5]
~~~

`mapToObj` differs from `boxed`: it maps primitives to **any object type**. Similarly, `LongStream` and `DoubleStream` also have `mapToObj`. Creating `String` objects is intentional business logic, not unnecessary integer boxing.

### 6.3. Wrapper Stream → Primitive via mapToInt(), mapToLong(), mapToDouble()

~~~java
List<Integer> values = List.of(5, 10, 15);

int total = values.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 30
~~~

At this boundary, Java needs to unbox each `Integer` into an `int`. The benefit is that the rest of the pipeline can continue working with primitives. If the list contains `null`, `Integer::intValue` throws `NullPointerException`; handle nullable sources explicitly, such as filtering first with `filter(java.util.Objects::nonNull)` if the business logic allows skipping missing data.

`IntStream` also has `mapToLong` and `mapToDouble` to switch primitive types; `LongStream` has `mapToInt` and `mapToDouble`; `DoubleStream` has `mapToInt` and `mapToLong`. *Narrowing* conversions from `long`/`double` down to `int` can lose information, so do not treat them as always safe.

### 6.4. asLongStream(), asDoubleStream()

~~~java
long safeForThisSum = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum(); // 2147483648

double mean = IntStream.of(1, 2)
        .asDoubleStream()
        .average()
        .orElseThrow(); // 1.5
~~~

`asLongStream()` on `IntStream` is a *widening* conversion that preserves `int` values exactly. `IntStream.asDoubleStream()` also preserves every `int` value exactly (since `double` represents all 32-bit integers exactly). However, `LongStream.asDoubleStream()` **can lose precision** for `long` values larger than `double`'s exact integer threshold (around `2^53`). Do not use that conversion for calculations requiring unit-level precision on large integers.

## 7. Complete Java 17+ Program and Verified Output

Create `PrimitiveStreamsDemo.java`:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamsDemo {
    public static void main(String[] args) {
        int[] readings = {2, 4, 6, 8};
        System.out.println("array sum=" + Arrays.stream(readings).sum());
        System.out.println("range=" + IntStream.range(1, 5).sum());
        System.out.println("rangeClosed=" + LongStream.rangeClosed(1, 5).sum());

        IntSummaryStatistics stats =
                IntStream.of(2, 4, 6).summaryStatistics();
        System.out.println("stats count=" + stats.getCount()
                + ", sum=" + stats.getSum()
                + ", avg=" + stats.getAverage());

        System.out.println("max=" +
                IntStream.of(8, 2, 5).max().orElseThrow());
        System.out.println("empty average present=" +
                IntStream.empty().average().isPresent());

        List<Integer> ids = IntStream.of(3, 1, 3, 2)
                .distinct().sorted().boxed().toList();
        System.out.println("boxed ids=" + ids);

        List<String> labels = IntStream.of(2, 3, 5)
                .mapToObj(i -> "id-" + i).toList();
        System.out.println("labels=" + labels);

        System.out.println("parsed sum=" +
                Stream.of("7", "10", "13")
                        .mapToInt(Integer::parseInt).sum());

        System.out.println("long sum=" +
                IntStream.of(Integer.MAX_VALUE, 1)
                        .asLongStream().sum());
        System.out.println("int sum=" +
                IntStream.of(Integer.MAX_VALUE, 1).sum());

        System.out.println("double total=" +
                DoubleStream.of(1.5, 2.5, 3.5).sum());
        System.out.println("double avg=" +
                DoubleStream.of(1.5, 2.5, 3.5)
                        .average().orElseThrow());

        String joined = IntStream.of(2, 3, 5)
                .collect(
                        StringBuilder::new,
                        (builder, value) -> builder.append(value),
                        (left, right) -> left.append(right))
                .toString();
        System.out.println("collected=" + joined);
    }
}
~~~

Compile and run:

~~~bash
javac PrimitiveStreamsDemo.java
java PrimitiveStreamsDemo
~~~

Stdout output:

~~~text
array sum=20
range=10
rangeClosed=15
stats count=3, sum=12, avg=4.0
max=8
empty average present=false
boxed ids=[1, 2, 3]
labels=[id-2, id-3, id-5]
parsed sum=30
long sum=2147483648
int sum=-2147483648
double total=7.5
double avg=2.5
collected=235
~~~

The program illustrates important boundaries. `Arrays.stream(int[])` and `IntStream.range` create primitive streams; `summaryStatistics` aggregates metrics in one consumption pass; `boxed()` appears only where `List<Integer>` is needed; `mapToObj` creates `String` objects when required. The two lines `long sum` and `int sum` intentionally demonstrate `int` overflow in a default aggregation.

## 8. Controlling Overflow During Integer Aggregation

Using primitive streams **does not automatically guarantee the sum stays within the result type**.

~~~java
int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
// -2147483648 due to int overflow

long widenedFirst = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648
~~~

`IntStream.sum()` returns `int`, so it can overflow according to Java integer rules; `LongStream.sum()` can also overflow with sufficiently large `long` data. `asLongStream()` does not always solve every problem: it only widens the limit from 32 bits to 64 bits.

Crucially, **widen before performing operations that can overflow**, rather than casting afterward:

~~~java
long wrong = IntStream.of(50_000, 60_000)
        .map(n -> n * n)        // multiplication in int: already overflowed
        .asLongStream()
        .sum();

long correct = IntStream.of(50_000, 60_000)
        .mapToLong(n -> (long) n * n)
        .sum(); // 6100000000
~~~

The `(long) n` cast is placed **before the multiplication** so the multiplication runs in `long`. For data that can exceed even the `long` range, design the aggregation using `BigInteger` or handle bounds as required.

When you need to **detect** overflow instead of letting values wrap, you can use `Math.addExact`:

~~~java
int exact = IntStream.of(1, 2, 3)
        .reduce(0, Math::addExact); // 6

// IntStream.of(Integer.MAX_VALUE, 1)
//          .reduce(0, Math::addExact);
// Throws ArithmeticException when addition exceeds the int range.
~~~

For a parallel pipeline, reductions must satisfy associativity; exact addition via `Math.addExact` can throw an exception during combining if a step exceeds the limit. Decide clearly whether you want an `int` result, a `long` result, arbitrary-precision integers, or an error on overflow.

## 9. DoubleStream Has Its Own Speed and Floating-Point Characteristics

`DoubleStream` fits measurement data or real numbers where IEEE 754 approximate precision is acceptable:

~~~java
double sum = DoubleStream.of(1.5, 2.5, 3.5).sum(); // 7.5
double average = DoubleStream.of(1.5, 2.5, 3.5)
        .average().orElseThrow(); // 2.5
~~~

However, `double` **cannot represent every decimal fraction exactly**, such as `0.1`. `DoubleStream.sum()` uses compensated summation to reduce error compared to naive addition in many situations, but **does not guarantee** exact decimal results like a `BigDecimal` calculation.

Illustrative example:

~~~java
double a = 0.1;
double b = 0.2;
System.out.println(a + b == 0.3); // false under regular double addition
~~~

Do not use this example to claim that a specific `DoubleStream.sum()` sequence always produces the exact same decimal string as direct addition: the summation algorithm may differ. The takeaway is to choose the numeric type suited to your precision requirements.

When handling monetary amounts or quantities with exact decimal rules, `BigDecimal` is usually the better choice; in that case an object pipeline may be the right design decision, and reducing boxing is less important than ensuring arithmetic correctness.

Other differences to know:

- `DoubleStream` can contain `NaN`, `Infinity`, and `-Infinity`; how these values propagate through aggregation must be defined by the application.
- `DoubleStream.min()`/`max()` return `OptionalDouble`. Do not use the result when empty without checking.
- `double` loses the ability to represent every integer larger than `2^53` exactly. Avoid converting large `long` counts to `double` just to use `average()` if business logic requires exact unit precision.
- In floating-point addition, combining order can affect the low-order digits of the result. Running in parallel can change evaluation order, so floating-point comparisons often require an error tolerance rather than `==` when the domain allows.

## 10. flatMapToInt and Processing Multiple Primitive Arrays

Input data may consist of multiple `int[]` arrays inside a `Stream<int[]>`. You do not need to box every element to concatenate them:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

int total = Stream.of(
        new int[] {1, 2},
        new int[] {3, 4, 5}
    )
    .flatMapToInt(Arrays::stream)
    .sum(); // 15
~~~

`flatMapToInt` takes each `int[]`, creates the corresponding `IntStream`, and flattens the primitive elements. Similarly, `flatMapToLong` and `flatMapToDouble` apply when the mapping result is a `LongStream` or `DoubleStream`.

If the source is already an `IntStream` and each value must produce multiple `int` values, `IntStream.flatMap` itself takes a function returning an `IntStream`:

~~~java
int sum = IntStream.of(1, 2, 3)
        .flatMap(n -> IntStream.of(n, n * 10))
        .sum(); // 66
~~~

This is a useful pattern for flattening numeric data before aggregation without building an intermediate `List<Integer>`.

## 11. Parallel Streams: Can Be Faster, But Not by Default

Primitive streams support `parallel()`:

~~~java
long sum = IntStream.rangeClosed(1, 1_000_000)
        .asLongStream()
        .parallel()
        .sum(); // 500000500000
~~~

This calculation is valid because the `long` sum in the example does not overflow, and integer addition is associative, making it suitable for data partitioning. However, `parallel()` **is not automatically faster**; for small inputs or very lightweight per-element work, the overhead of splitting, scheduling, and combining can outweigh the benefit.

Do not replace a small sequential pipeline with a parallel one just because it uses primitives. Also, do not write into a shared accumulator variable inside `forEach`:

~~~java
// Unsafe when running in parallel due to unsynchronized shared variable updates:
int[] total = {0};
IntStream.rangeClosed(1, 100).parallel()
        .forEach(n -> total[0] += n);
~~~

The result of the example above can be wrong due to a data race. Use `sum()`, `reduce()`, or a collector with proper supplier/accumulator/combiner. With `forEach` on a parallel stream, execution order is not guaranteed; `forEachOrdered` preserves encounter order when needed, though it can reduce parallel speedup.

Primitive streams, like `Stream<T>`, are normally **consumed only once**. After a terminal operation (`sum`, `toArray`, `count`, `collect`, ...), to compute another metric you need to create a new stream or gather multiple statistics in one pass with `summaryStatistics`.

## 12. How to Reduce Boxing Properly, and When to Benchmark

Compare two pipelines with the same goal:

~~~java
// Can create wrapper values across multiple steps.
int totalA = IntStream.rangeClosed(1, 1000)
        .boxed()
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

// Keeps primitives throughout.
int totalB = IntStream.rangeClosed(1, 1000)
        .map(n -> n * 2)
        .sum();
~~~

Both return `1001000`. The second pipeline expresses the computation intent more clearly and avoids converting elements to `Integer` before `map`/`reduce`. However, do not assume a fixed speedup ratio: the JVM has JIT optimizations, wrapper caching in some cases, escape analysis, and other optimization effects depending on the workload.

Practical rules:

1. **Start from a primitive source when possible:** `int[]`, `long[]`, `double[]`, `IntStream.range`.
2. **Stay primitive through arithmetic processing:** `filter`, `map`, `sum`, `average`, `summaryStatistics`.
3. **Convert when needed:** use `mapToInt` for object input data; use `boxed` when the output must be wrappers/lists; use `mapToObj` when you need a domain object.
4. **Never sacrifice correctness:** choose `long` or `BigInteger` when `int` can overflow; choose `BigDecimal` when exact decimal arithmetic is needed.
5. **Measure in the right environment:** for performance-critical systems, use a profiler and reliable microbenchmarking (commonly JMH) on realistic data and sizes; avoid drawing conclusions from a single small run or measuring with `System.currentTimeMillis()`.

The goal of primitive streams is not to "eliminate every object" in the JVM. The goal is to avoid unnecessary boxing/unboxing of **individual numeric elements** while providing a clear, verifiable numeric aggregation API.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `Stream.of(intArray)` to sum elements | Stream contains one array, not multiple numbers | `Arrays.stream(intArray).sum()` |
| Calling `sum()` directly on `Stream<Integer>` | No `sum()` method exists | `mapToInt(Integer::intValue).sum()` |
| Calling `toList()` on `IntStream` | No such API returning `List<Integer>` | `boxed().toList()` if a list is needed |
| Boxing early before a long calculation chain | Extra conversions and potential wrapper allocations | Stay primitive up to the object boundary |
| Unboxing `Integer` containing `null` | `NullPointerException` | Handle nulls per business logic before `mapToInt` |
| Assuming `IntStream.sum()` cannot overflow | Sum can wrap to a negative number | Widen early to long, or check with `Math.addExact` |
| Casting to long **after** int multiplication | Product already overflowed before cast | Cast `(long) n * n` directly inside `mapToLong` |
| Calling `max().getAsInt()` on an empty stream | `NoSuchElementException` | Check `isPresent` or `orElseThrow` per contract |
| Using `DoubleStream` for money needing decimal exactness | Floating-point rounding error | Use `BigDecimal` and explicit rounding rules |
| Expecting parallel to always be faster | High synchronization/partitioning overhead | Benchmark and parallelize only when worthwhile |
| Accumulating into a shared variable in parallel `forEach` | Data race, indeterminate results | Use `sum`, `reduce`, or a proper collector |
| Calling `sum()` then `average()` on the same stream | `IllegalStateException` because stream is consumed | Create a new stream or `summaryStatistics` |
| Converting very large `long` to `double` for sum/average | Can lose integer precision | Keep `long`/`BigInteger` or choose an appropriate exact technique |

## 14. Self-Check Exercises

**Exercise 1.** Write the sum of even numbers from 1 to 10 without boxing.

**Answer:**

~~~java
int sum = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .sum(); // 30
~~~

**Exercise 2.** Given the array `int[] data = {3, 6, 9}`, why does `Stream.of(data).count()` return 1 while `Arrays.stream(data).count()` returns 3?

**Answer:** `Stream.of(data)` treats the entire `int[]` as a single object element; `Arrays.stream(data)` creates an `IntStream` of three primitive elements.

**Exercise 3.** Which operation should be used for the sum `Integer.MAX_VALUE + 1` to avoid `int` overflow during this aggregation?

**Answer:** `IntStream.of(Integer.MAX_VALUE, 1).asLongStream().sum()` returns `2147483648`; do not use `IntStream.sum()` for that case.

**Exercise 4.** What type does `IntStream.of(1, 2, 3).average()` return? What happens if the stream is empty?

**Answer:** `OptionalDouble`, containing the average value `2.0` when elements exist. For an empty stream it is `OptionalDouble.empty()`; the caller decides on a fallback or error.

**Exercise 5.** After `IntStream.range(0, 4).sum()`, can you continue using the same stream to compute `max()`?

**Answer:** No, the stream is already closed after the terminal operation. Create a new stream, or if you need multiple metrics in one pass, use `summaryStatistics()`.

**Exercise 6.** When the output must be a `List<Integer>` ascending from 1 to 5, is boxing required?

**Answer:** Yes, because `List<Integer>` holds wrapper objects. For example, `IntStream.rangeClosed(1, 5).boxed().toList()`. What should be avoided is boxing earlier than the output requires.

**Exercise 7.** What is the result of `IntStream.of(50_000, 60_000).mapToLong(n -> (long)n * n).sum()`?

**Answer:** `6_100_000_000L`. Casting to long before multiplication keeps both squares and the sum exact within long limits.

---

**Remember:** `IntStream`, `LongStream`, and `DoubleStream` are specialized streams for numeric computation, providing `sum`, `average`, `summaryStatistics`, and many operations on primitive elements. **Stay primitive during computation, box only when an API genuinely needs objects**, and always check overflow, floating-point precision, empty-stream cases, and business requirements.