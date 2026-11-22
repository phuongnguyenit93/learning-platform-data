# IntStream, LongStream, and DoubleStream in Java

In the Java Stream API, `Stream<T>` is a pipeline for processing objects. However, primitive numeric data appears very frequently: `int`, `long`, and `double`. To work with these values without boxing each element into `Integer`, `Long`, or `Double`, Java provides three **primitive streams** in the `java.util.stream` package:

- **`IntStream`**: a stream of `int` values.
- **`LongStream`**: a stream of `long` values.
- **`DoubleStream`**: a stream of `double` values.

These three types share many operations similar to object streams: `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`, `skip`, `forEach`, and `reduce`. They also have very convenient terminal operations for arithmetic such as `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()`.

An important benefit is **avoiding unnecessary boxing/unboxing** and directly expressing numeric computation intent. However, primitive streams do not automatically guarantee overflow-free addition, error-free floating-point numbers, or that parallel mode is always faster.

After this lesson, you can:
1. Choose the right `IntStream`, `LongStream`, or `DoubleStream` and create sources from arrays, numeric ranges, or individual values.
2. Transform, filter, sum, find min/max, compute averages, and gather statistics on numeric data.
3. Convert between `Stream<T>` and primitive streams, understanding `boxed()`, `mapToInt`, `mapToLong`, and `mapToDouble`.
4. Handle potentially absent results with `OptionalInt`, `OptionalLong`, and `OptionalDouble`.
5. Recognize pitfalls regarding `range`, `rangeClosed`, boxing, integer overflow, floating-point precision, and terminal operations.

The complete runnable programs below are written for **JDK 17 and above**; each file includes `javac`/`java` commands and deterministic stdout.

## 1. How do primitive streams differ from Stream<T>?

| Criterion | `Stream<Integer>` | `IntStream` |
| --- | --- | --- |
| Element type | `Integer` object | Primitive `int` value |
| Filter function | `Predicate<Integer>` | `IntPredicate` |
| Same-type mapping function | `Function<Integer,Integer>` | `IntUnaryOperator` |
| Summing | Typically uses `mapToInt(...).sum()` or `reduce` | Built-in `sum()` |
| Average | Needs conversion to a primitive stream or separate calculation | Has `average()` returning `OptionalDouble` |
| Converting to object stream | Already an object stream | Uses `boxed()` |
| With large numeric data | May incur boxing/unboxing | Often helps avoid wrapper overhead |

`LongStream` and `DoubleStream` apply the same idea to `long` and `double`. They implement `BaseStream`, but they are not `Stream<Long>` or `Stream<Double>` and cannot be substituted directly for each other.

Example:

```java
IntStream primitive = IntStream.of(1, 2, 3);
Stream<Integer> objects = IntStream.of(1, 2, 3).boxed();
```

This is an illustrative snippet requiring `import java.util.stream.IntStream;` and `import java.util.stream.Stream;`. `boxed()` converts each `int` into an `Integer` to place into an object stream. If you only need `sum`, no boxing is needed.

**Type note:** `int` and `Integer` are different. Although autoboxing makes code convenient, the generic type parameter of `Stream<T>` does not accept primitive `int` as a type argument: you cannot write `Stream<int>`.

## 2. Creating an IntStream

Common factories and sources:

```java
IntStream a = IntStream.of(2, 4, 6);
IntStream b = IntStream.empty();
IntStream c = IntStream.range(1, 5);       // 1, 2, 3, 4
IntStream d = IntStream.rangeClosed(1, 5); // 1, 2, 3, 4, 5
int[] source = {7, 8, 9};
IntStream e = java.util.Arrays.stream(source);
```

This is an **illustrative snippet**, placed inside a method with `import java.util.stream.IntStream`. Each variable is **a separate Stream** that can be consumed once. The two methods `range` and `rangeClosed` have an easily confused difference:

- `IntStream.range(startInclusive, endExclusive)`: includes the left bound, **excludes** the right bound.
- `IntStream.rangeClosed(startInclusive, endInclusive)`: includes **both bounds** if the range has elements.

For example, `range(5,5)` is empty, while `rangeClosed(5,5)` has exactly one element, 5. When the left bound is greater than the right bound, both return an empty Stream and do not automatically produce a descending sequence.

You can also create a Stream from data generation:

```java
IntStream odds = IntStream.iterate(1, n -> n + 2).limit(4);
IntStream fixed = IntStream.generate(() -> 7).limit(3);
```

`iterate(seed, next)` produces a sequence by rule; `generate(supplier)` pulls values from a supplier. Both sources can be **infinite** if no termination condition is set; `limit` ensures the example only takes a few elements. Since Java 9, there is also `iterate(seed, hasNext, next)` to stop according to a predicate:

```java
int[] values = IntStream.iterate(1, n -> n <= 5, n -> n + 2)
        .toArray(); // [1, 3, 5]
```

In this pipeline, `hasNext` is checked to decide whether to emit the next element. Do not add `sorted()` or operations requiring all data to an infinite source without an appropriate bound.

## 3. Creating LongStream and DoubleStream

`LongStream` is suitable for operations on `long` and large numeric ranges:

```java
LongStream ids = LongStream.of(10L, 20L, 30L);
LongStream sequence = LongStream.rangeClosed(1L, 4L);
long[] source = {100L, 200L};
LongStream fromArray = java.util.Arrays.stream(source);
```

This is a snippet with `import java.util.stream.LongStream;`. `LongStream.range` and `rangeClosed` work similarly to the `IntStream` versions, but over the `long` domain.

`DoubleStream` is used for floating-point numbers:

```java
DoubleStream prices = DoubleStream.of(1.5, 2.5, 4.0);
double[] weights = {0.5, 1.0, 1.5};
DoubleStream fromArray = java.util.Arrays.stream(weights);
DoubleStream repeated = DoubleStream.generate(() -> 0.5).limit(3);
```

This is an illustrative snippet with `import java.util.stream.DoubleStream;`; the `fromArray` variable names are used in **two independent examples**. `DoubleStream` **does not have** `range` or `rangeClosed` methods like `IntStream`/`LongStream`. If you need an evenly spaced sequence of floating-point numbers, you can generate integer indices and convert them:

```java
double[] steps = IntStream.rangeClosed(0, 3)
        .mapToDouble(i -> i * 0.5)
        .toArray(); // [0.0, 0.5, 1.0, 1.5]
```

With a decimal step that cannot be represented exactly in binary, `double` results may have rounding errors; the example uses 0.5 to get exact results.

## 4. Core processing operations

The primitive streams provide a nearly corresponding set of operations:

| Purpose | IntStream | LongStream | DoubleStream |
| --- | --- | --- | --- |
| Filtering | `filter(IntPredicate)` | `filter(LongPredicate)` | `filter(DoublePredicate)` |
| Same-type transformation | `map(IntUnaryOperator)` | `map(LongUnaryOperator)` | `map(DoubleUnaryOperator)` |
| Converting to object stream | `mapToObj(IntFunction<R>)` | `mapToObj(LongFunction<R>)` | `mapToObj(DoubleFunction<R>)` |
| Summing | `sum(): int` | `sum(): long` | `sum(): double` |
| Minimum value | `min(): OptionalInt` | `min(): OptionalLong` | `min(): OptionalDouble` |
| Maximum value | `max(): OptionalInt` | `max(): OptionalLong` | `max(): OptionalDouble` |
| Average | `average(): OptionalDouble` | `average(): OptionalDouble` | `average(): OptionalDouble` |
| Element count | `count(): long` | `count(): long` | `count(): long` |
| Creating an array | `toArray(): int[]` | `toArray(): long[]` | `toArray(): double[]` |

For example, `IntStream.rangeClosed(1, 6).filter(n -> n % 2 == 0).sum()` returns **12**, because the retained elements are 2, 4, 6. `LongStream.of(5L, 9L).max()` returns an `OptionalLong` with value 9. `DoubleStream.of(1.0, 3.0).average()` returns an `OptionalDouble` with value 2.0.

Operations like `filter`, `map`, `sorted`, and `distinct` are **intermediate operations**: they create a new pipeline and are generally lazy. Operations like `sum`, `average`, `count`, `toArray`, and `reduce` are **terminal operations**: they trigger processing and consume the Stream.

Because a primitive stream is not a `Stream<T>`, you also cannot call `toList()` directly on `IntStream`, `LongStream`, or `DoubleStream` in Java 17. When you need a `List<Integer>`, `List<Long>`, or `List<Double>`, use `boxed().toList()`.

## 5. Java 17 Program: IntStream from source to statistics

Save as **`IntStreamBasicsDemo.java`**:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.IntStream;

public class IntStreamBasicsDemo {
    public static void main(String[] args) {
        int[] numbers = {2, 3, 4, 5, 6};

        int[] evenSquares = Arrays.stream(numbers)
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .toArray();

        int total = Arrays.stream(numbers).sum();
        double average = Arrays.stream(numbers)
                .average()
                .orElse(-1.0);

        List<Integer> exclusive = IntStream.range(1, 5)
                .boxed()
                .toList();

        List<Integer> inclusive = IntStream.rangeClosed(1, 5)
                .boxed()
                .toList();

        int[] odds = IntStream.iterate(1, n -> n + 2)
                .limit(4)
                .toArray();

        IntSummaryStatistics stats = Arrays.stream(numbers)
                .summaryStatistics();

        System.out.println("evenSquares=" + Arrays.toString(evenSquares));
        System.out.println("sum=" + total);
        System.out.println("average=" + average);
        System.out.println("range=" + exclusive);
        System.out.println("rangeClosed=" + inclusive);
        System.out.println("odds=" + Arrays.toString(odds));
        System.out.println("stats=" + stats.getCount() + "/"
                + stats.getMin() + "/" + stats.getMax());
    }
}
```

Command to run with JDK 17+:

```bash
javac -encoding UTF-8 IntStreamBasicsDemo.java
java IntStreamBasicsDemo
```

**Exact stdout:**

```text
evenSquares=[4, 16, 36]
sum=20
average=4.0
range=[1, 2, 3, 4]
rangeClosed=[1, 2, 3, 4, 5]
odds=[1, 3, 5, 7]
stats=5/2/6
```

Explanation:
1. The `numbers` array contains 2, 3, 4, 5, 6. Filtering even numbers yields 2, 4, 6, which are squared to 4, 16, 36.
2. `sum()` returns the total 20; `average()` returns an `OptionalDouble` containing 4.0. Here `orElse(-1.0)` is just a fallback policy for the case with no elements.
3. `range(1,5)` excludes 5; `rangeClosed(1,5)` includes 5. `boxed()` turns the `int` stream into `Stream<Integer>`.
4. `iterate(...).limit(4)` takes only the first four odd numbers, avoiding an infinite pipeline.
5. `summaryStatistics()` collects `count`, `sum`, `min`, `max`, and `average` statistics in a single terminal operation. The example only prints three metrics to keep stdout concise, though the other getters remain available.

## 6. LongStream: handling long and reducing int overflow risk

`LongStream` has factories and terminal operations similar to IntStream, but works with the `long` type. It is often appropriate when values, multiplications, or sums may exceed the `int` range.

```java
long sum = LongStream.of(2_000_000_000L, 2_000_000_000L)
        .sum(); // 4_000_000_000L
```

This snippet requires `import java.util.stream.LongStream;`. If replaced with `IntStream.of(2_000_000_000, 2_000_000_000).sum()`, the `int` addition will overflow according to Java integer rules and **will not** produce 4 billion.

### Java 17 Program: LongStream and reduction

Save as **`LongStreamDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class LongStreamDemo {
    public static void main(String[] args) {
        long[] squares = LongStream.rangeClosed(1L, 4L)
                .map(value -> value * value)
                .toArray();

        long bigSum = LongStream.of(2_000_000_000L, 2_000_000_000L)
                .sum();

        long exactIntPromoted = IntStream.of(
                        2_000_000_000,
                        2_000_000_000)
                .asLongStream()
                .sum();

        long product = LongStream.rangeClosed(1L, 4L)
                .reduce(1L, (left, right) -> left * right);

        List<Long> boxed = LongStream.of(10L, 20L, 30L)
                .boxed()
                .toList();

        System.out.println("squares=" + Arrays.toString(squares));
        System.out.println("bigSum=" + bigSum);
        System.out.println("promotedSum=" + exactIntPromoted);
        System.out.println("product=" + product);
        System.out.println("boxed=" + boxed);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 LongStreamDemo.java
java LongStreamDemo
```

**Exact stdout:**

```text
squares=[1, 4, 9, 16]
bigSum=4000000000
promotedSum=4000000000
product=24
boxed=[10, 20, 30]
```

`asLongStream()` converts each `int` to `long` **before summing**, so the example yields a sum of 4 billion. This is an important difference from summing as `int` and casting the result afterward: once overflow has occurred, casting later does not recover the true value.

`reduce(1L, (a,b) -> a*b)` uses the identity element 1 and multiplication. In this small example the result is `1×2×3×4 = 24`. On large data, `long` multiplication can still overflow; using `long` **does not mean** avoiding all overflow cases.

## 7. DoubleStream: double calculations and averages

`DoubleStream` serves operations on `double`. The terminal operations `sum`, `average`, and `summaryStatistics` are very useful for measurement data.

### Java 17 Program: DoubleStream statistics

Create the file **`DoubleStreamStatsDemo.java`**:

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

public class DoubleStreamStatsDemo {
    public static void main(String[] args) {
        double[] measurements = {2.0, 4.0, 6.0};

        DoubleSummaryStatistics stats = Arrays.stream(measurements)
                .summaryStatistics();

        double[] halves = Arrays.stream(measurements)
                .map(value -> value / 2.0)
                .toArray();

        double greaterThanThree = Arrays.stream(measurements)
                .filter(value -> value > 3.0)
                .sum();

        double mean = DoubleStream.of(1.0, 2.0, 3.0)
                .average()
                .orElse(-1.0);

        System.out.println("halves=" + Arrays.toString(halves));
        System.out.println("filteredSum=" + greaterThanThree);
        System.out.println("count=" + stats.getCount());
        System.out.println("sum=" + stats.getSum());
        System.out.println("min=" + stats.getMin());
        System.out.println("max=" + stats.getMax());
        System.out.println("average=" + stats.getAverage());
        System.out.println("mean=" + mean);
    }
}
```

Run:

```bash
javac -encoding UTF-8 DoubleStreamStatsDemo.java
java DoubleStreamStatsDemo
```

**Exact stdout:**

```text
halves=[1.0, 2.0, 3.0]
filteredSum=10.0
count=3
sum=12.0
min=2.0
max=6.0
average=4.0
mean=2.0
```

All three operations—`sum`, `average`, and `summaryStatistics`—are terminal operations; they cannot be called consecutively on the **same** already-consumed Stream. In the example above, each operation creates a new source from the original array/values.

### Note on floating-point numbers

`double` is a binary floating-point type and does not represent every decimal number exactly. Therefore, cumulative addition can introduce rounding errors. With parallel data, additions may be grouped in a different order; do not require every computation path to produce bit-identical results.

If a problem requires precision on a monetary scale (for example, two decimal places), consider `BigDecimal` or an appropriate integer unit. `DoubleStream` is well suited for many measurement, statistical, and scientific calculations, but it does not automatically solve business rounding policies.

## 8. Converting between object streams and primitive streams

This is a crucial point because most business APIs start from `List<T>`, not primitive arrays.

| Source | Conversion | Result type |
| --- | --- | --- |
| `Stream<String>` | `.mapToInt(String::length)` | `IntStream` |
| `Stream<String>` | `.mapToLong(Long::parseLong)` | `LongStream` |
| `Stream<String>` | `.mapToDouble(Double::parseDouble)` | `DoubleStream` |
| `IntStream` | `.boxed()` | `Stream<Integer>` |
| `LongStream` | `.boxed()` | `Stream<Long>` |
| `DoubleStream` | `.boxed()` | `Stream<Double>` |
| `IntStream` | `.asLongStream()` | `LongStream` |
| `IntStream` | `.asDoubleStream()` | `DoubleStream` |
| `LongStream` | `.asDoubleStream()` | `DoubleStream` |
| `IntStream` | `.mapToObj(n -> "ID-" + n)` | `Stream<String>` |

Here, `Long::parseLong` takes a `String` and returns a primitive `long`; if an input string is malformed, the call can throw `NumberFormatException`. Primitive streams only help describe and process data; they do not automatically turn parse errors into valid values.

Conversions are **not completely information-preserving**:
- `IntStream.asLongStream()` converts `int` to `long` without losing values.
- `IntStream.asDoubleStream()` preserves every `int` value exactly because `double` has enough precision for the `int` range.
- `LongStream.asDoubleStream()` **can lose precision** for large `long` values (especially beyond 2^53), because `double` cannot represent every 64-bit integer exactly.
- Converting from `double` to `int` or `long` via a cast or `mapToInt`/`mapToLong` requires considering fractional parts, NaN, infinity, and Java's numeric conversion rules.

## 9. Java 17 Program: mapToInt, boxed, asLongStream, mapToObj

Save as **`PrimitiveStreamConversionsDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamConversionsDemo {
    public static void main(String[] args) {
        List<String> words = List.of("Java", "Stream", "API");

        int letters = words.stream()
                .mapToInt(String::length)
                .sum();

        List<Integer> lengths = words.stream()
                .mapToInt(String::length)
                .boxed()
                .toList();

        List<String> labels = IntStream.rangeClosed(1, 3)
                .mapToObj(number -> "ID-" + number)
                .toList();

        long fromString = Stream.of("10", "20", "30")
                .mapToLong(Long::parseLong)
                .sum();

        long promotedSum = IntStream.rangeClosed(1, 3)
                .asLongStream()
                .sum();

        double mean = LongStream.of(2L, 4L, 6L)
                .asDoubleStream()
                .average()
                .orElse(-1.0);

        System.out.println("letters=" + letters);
        System.out.println("lengths=" + lengths);
        System.out.println("labels=" + labels);
        System.out.println("parsedSum=" + fromString);
        System.out.println("promotedSum=" + promotedSum);
        System.out.println("mean=" + mean);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 PrimitiveStreamConversionsDemo.java
java PrimitiveStreamConversionsDemo
```

**Exact stdout:**

```text
letters=13
lengths=[4, 6, 3]
labels=[ID-1, ID-2, ID-3]
parsedSum=60
promotedSum=6
mean=4.0
```

The example shows that `mapToInt` returns an `int` stream that has `sum()`; `boxed()` turns a numeric stream into an object Stream to use `toList()`; `mapToObj` creates arbitrary objects from primitives, not necessarily wrappers. With `LongStream.asDoubleStream()`, the small numbers 2, 4, 6 are represented exactly and yield an average of 4.0.

## 10. OptionalInt, OptionalLong, and OptionalDouble

Because `min`, `max`, `findFirst`, `findAny`, or `average` may have no result when a Stream is empty, the API cannot always return a primitive directly. It uses specialized containers:

- `OptionalInt`: has `getAsInt()`, `orElse(int)`, `isPresent()`, `isEmpty()`.
- `OptionalLong`: has `getAsLong()`, `orElse(long)`, `isPresent()`, `isEmpty()`.
- `OptionalDouble`: has `getAsDouble()`, `orElse(double)`, `isPresent()`, `isEmpty()`.

Example:

```java
OptionalInt firstEven = IntStream.of(3, 4, 5)
        .filter(n -> n % 2 == 0)
        .findFirst(); // contains 4

OptionalLong missingLong = LongStream.empty().max(); // empty
OptionalDouble emptyAverage = DoubleStream.empty().average(); // empty
```

This is an illustrative snippet requiring imports from `java.util` and `java.util.stream`. Do not call `getAsInt()`, `getAsLong()`, or `getAsDouble()` **blindly** when a value is not guaranteed to be present: those methods throw `NoSuchElementException` when the specialized Optional is empty. Use `orElse`, `ifPresent`, `orElseThrow`, or check state appropriately.

### Empty Stream cases

| Terminal operation | Result for an empty primitive Stream |
| --- | --- |
| `sum()` | `0`, `0L`, or `0.0` depending on type |
| `count()` | `0L` |
| `average()` | `OptionalDouble.empty()` |
| `min()`, `max()` | Empty specialized Optional |
| `findFirst()`, `findAny()` | Empty specialized Optional |
| `reduce(identity, op)` | `identity` |
| `reduce(op)` | Empty specialized Optional |
| `summaryStatistics()` | Statistics object with `count == 0`, min/max getters having the class's own sentinel values |

**Do not treat `sum() == 0` as proof that a stream has no elements.** A stream with opposite numbers can also sum to 0. When you need to know whether elements exist, use `count`, `findAny`, or an appropriate result design.

### Java 17 Program: fallbacks on specialized Optionals

Save as **`PrimitiveOptionalDemo.java`**:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveOptionalDemo {
    public static void main(String[] args) {
        OptionalInt firstOdd = IntStream.of(2, 4, 5)
                .filter(n -> n % 2 != 0)
                .findFirst();

        OptionalLong maxMissing = LongStream.empty().max();
        OptionalDouble avgMissing = DoubleStream.empty().average();

        System.out.println("firstOdd=" + firstOdd.orElse(-1));
        System.out.println("maxMissing=" + maxMissing.orElse(-1L));
        System.out.println("avgMissing=" + avgMissing.orElse(-1.0));
        System.out.println("sumEmpty=" + IntStream.empty().sum());
        System.out.println("countEmpty=" + LongStream.empty().count());
        System.out.println("minPresent=" + IntStream.of(9, 3, 7)
                .min().isPresent());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

**Exact stdout:**

```text
firstOdd=5
maxMissing=-1
avgMissing=-1.0
sumEmpty=0
countEmpty=0
minPresent=true
```

In the example, `firstOdd` contains 5, while `maxMissing` and `avgMissing` are empty. The fallbacks `-1`, `-1L`, `-1.0` are only **illustrative conventions**; real applications should choose a fallback that cannot be confused with valid data, or use exceptions/stateful result types if exact distinction is needed.

## 11. reduce and parallel on primitive streams

Primitive streams support `reduce`, for example:

```java
int sum = IntStream.rangeClosed(1, 5)
        .reduce(0, Integer::sum); // 15

long product = LongStream.rangeClosed(1L, 4L)
        .reduce(1L, (a, b) -> a * b); // 24
```

Each snippet is placed inside a method. With an appropriate identity and operator, `reduce` combines elements into a single result. `sum()` usually expresses addition intent more clearly than `reduce(0, Integer::sum)`.

You can choose `parallel()`:

```java
long sum = LongStream.rangeClosed(1L, 1_000L)
        .parallel()
        .sum(); // 500500L
```

**Not every reduce operation is suitable for parallel execution.** The combining operator should be **associative** with a proper identity, and must not depend on shared mutable state. For example, subtraction is not associative, so `reduce(0, (a,b) -> a-b)` can return different results between sequential and parallel runs.

With `double`, rounded results may differ when split and combined across multiple threads. Parallel streams also carry overhead: small datasets or simple operations like summing a few hundred numbers can be slower than sequential execution. Measure on real workloads instead of assuming adding `parallel()` is always beneficial.

## 12. Integer overflow and floating-point precision

### 12.1. IntStream.sum() returns int

Example:

```java
int wrong = IntStream.of(2_000_000_000, 2_000_000_000).sum();
// Java int overflows, result is -294967296

long correct = IntStream.of(2_000_000_000, 2_000_000_000)
        .asLongStream()
        .sum(); // 4000000000L
```

Both lines are valid snippets inside a method. `asLongStream()` widens the type **before the addition**, so the example produces the correct sum in the `long` range. Do not compute the `int` sum first and cast to `long` afterward hoping to fix overflow.

### 12.2. LongStream still has limits

`long` has a larger value range than `int` but is not infinite; `long` addition or multiplication can still overflow. If a problem requires integers beyond the `long` range, you can use `BigInteger` in an object stream or an appropriate algorithm.

### 12.3. DoubleStream is not exact decimal arithmetic

For example, `0.1 + 0.2` may not compare equal to `0.3` when using `double`. `DoubleStream.sum()` and `average()` support computing sums/averages but still follow IEEE 754 floating-point behavior. If approximate comparison is needed, define an appropriate error tolerance; if exact currency amounts following decimal rules are required, consider `BigDecimal` instead of `DoubleStream`.

Do not treat `DoubleStream.of(0.1, 0.2).sum() == 0.3` as a good test across all JDKs and computation orders; what should be tested is **accuracy within a business tolerance**, not an assertion about bit representation.

### 12.4. Precision when converting long to double

`LongStream.asDoubleStream()` is convenient for averages but can lose integer precision when `long` values are very large. `double` cannot represent every integer outside the 53-bit significand precision range. If you must never lose a single unit on large ID numbers, **do not convert IDs to double just to process them faster**.

## 13. Common mistakes

1. **Writing `Stream<int>`:** a generic type parameter must be a reference type; choose `IntStream`.
2. **Calling `IntStream.toList()`:** primitive streams do not have this method in Java 17; use `boxed().toList()`.
3. **Confusing `range` and `rangeClosed`:** one excludes the end, the other includes the end.
4. **Assuming `DoubleStream.range` exists:** it does not; generate indices from IntStream and then `mapToDouble`.
5. **Calling a terminal operation twice on the same Stream:** a Stream can generally only be consumed once.
6. **Using IntStream's `sum()` for sums that can exceed int:** the sum can overflow; widen to LongStream first.
7. **Assuming LongStream never overflows:** `long` also has a finite range.
8. **Calling `getAsInt()` or `getAsDouble()` on an empty Optional:** throws `NoSuchElementException`.
9. **Assuming average on an empty Stream returns 0.0:** it returns `OptionalDouble.empty()`.
10. **Confusing `boxed()` with `mapToObj`:** `boxed()` creates primitive wrappers; `mapToObj` lets you create objects of any type.
11. **Using `map` instead of `mapToInt` from `Stream<String>`:** `map(String::length)` returns an object stream of Integer, not an IntStream.
12. **Assuming DoubleStream is for exact currency:** binary floating-point numbers have rounding errors.
13. **Creating an infinite `generate` and calling `sum` without a bound:** the pipeline may never terminate.
14. **Switching to `parallel()` with a non-associative combiner:** the result can be wrong or unexpected.
15. **Assuming no boxing always means faster:** performance also depends on workload, JIT, allocation, actual boxing, and algorithm; benchmark it.
16. **Using a primitive stream to represent null:** primitive elements cannot be null; if the source has nullable wrappers, define a filtering/mapping policy before unboxing.
17. **Using asDoubleStream for large long integers that require exactness:** the conversion can lose information.

## 14. Quick selection by need

| Problem | Suitable API | Key point |
| --- | --- | --- |
| Generate integers from 0 to n-1 | `IntStream.range(0,n)` | End exclusive |
| Generate integers from 1 to n | `IntStream.rangeClosed(1,n)` | End inclusive |
| Sum int values guaranteed not to overflow | `IntStream.sum()` | Returns int |
| Sum many ints that may exceed int range | `IntStream.asLongStream().sum()` | Widen before summing |
| Process long IDs | `LongStream` | Avoid narrowing to int |
| Statistics for double measurements | `DoubleStream.summaryStatistics()` | Count, sum, min, max, avg |
| Sum string lengths | `words.stream().mapToInt(String::length).sum()` | Convert object stream to primitive |
| Return a list of integers | `IntStream.boxed().toList()` | Return to object stream |
| Represent potentially missing min/max results | `OptionalInt`/`OptionalLong`/`OptionalDouble` | Do not unwrap when empty |
| Convert int into descriptive strings | `IntStream.mapToObj(...)` | Create an object per number |

## 15. Self-check questions

**Question 1.** What do `IntStream.range(1,5).sum()` and `IntStream.rangeClosed(1,5).sum()` return?

**Answer:** `range` returns the sum 1+2+3+4 = **10**; `rangeClosed` adds 5 to return **15**.

**Question 2.** Why does `IntStream.of(1,2,3).toList()` not compile on Java 17?

**Answer:** `IntStream` does not have `toList()`. Use `boxed().toList()` to get `List<Integer>`, or `toArray()` to get `int[]`.

**Question 3.** What does `List.of("A","BB","CCC").stream().mapToInt(String::length).sum()` return?

**Answer:** 1 + 2 + 3 = **6**.

**Question 4.** What does `DoubleStream.empty().average()` return?

**Answer:** `OptionalDouble.empty()`, not a `double` 0.0.

**Question 5.** Can `LongStream.asDoubleStream()` be used to preserve every long larger than 2^53 exactly?

**No.** Precision can be lost because `double` cannot represent all large integers.

**Question 6.** Does `IntStream.of(2_000_000_000, 2_000_000_000).sum()` give 4,000,000,000?

**No.** `int` overflows. Convert to `asLongStream()` **before** summing to get 4,000,000,000 as a long.

**Question 7.** When should you use `boxed()`, and when should you use `mapToObj()`?

**Answer:** `boxed()` when you need a Stream of wrappers (`Integer`, `Long`, `Double`); `mapToObj()` when you want to turn primitives into any object type, such as a `"ID-"` string plus the number.

**Question 8.** Why is `IntStream.generate(() -> 1).sum()` a dangerous pipeline?

Because the generator source is infinite and `sum()` needs to consume all data; without a limit, the computation does not terminate normally.

**Takeaway:** Use **`IntStream` for int**, **`LongStream` for long**, and **`DoubleStream` for double** to compute with primitive types. Knowing how to create sources, convert via `mapToX`/`boxed`, handle `OptionalX`, and control overflow/precision errors matters more than just replacing `Stream<T>` with a new name.
