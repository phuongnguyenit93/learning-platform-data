# The IntStream, LongStream, and DoubleStream Model

> **Chapter:** Primitive Streams  
> **Module:** JAVA_STREAM_API  
> **Objective:** Understand the model of the three specialized Streams for primitive numeric data, know how to create sources, build pipelines, convert types, aggregate results, and choose the appropriate API considering precision, resources, and performance.

In Java, `Stream<T>` is commonly used to process data declaratively: create a source, chain intermediate operations such as `filter` and `map`, and then execute a terminal operation such as `reduce` or `collect`. However, when each element is simply an `int`, `long`, or `double` number, placing numbers into `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>` can incur **boxing/unboxing**: converting between primitive types and wrapper objects.

The Java Stream API provides three specialized interfaces:

- **`IntStream`:** processes `int` values.
- **`LongStream`:** processes `long` values.
- **`DoubleStream`:** processes `double` values.

These interfaces make it possible to express arithmetic, filtering, mapping, and statistical calculations without needing to wrap every element in a wrapper object just to move through the pipeline. In the **JAVA_STREAM_API** module, this model connects directly to lazy pipelines, `filter`, `map`, `reduce`, `collect`, grouping, custom collectors, `Spliterator`, parallel processing, and limits regarding state, resources, and performance. Advanced topics such as Stream Gatherers still rely on a proper awareness of element types and how to convert to `Stream<T>` when an API requires it.

The examples use Java 17+ for `List.of(...)`, records, and `Stream.toList()`. The primitive streams themselves and most of the methods presented have been available since Java 8; some overloads such as `iterate(seed, predicate, next)` have been available since Java 9.

## 1. Where do the three primitive stream types sit in the Stream hierarchy?

A simplified diagram:

```text
                     BaseStream<T, S>
                     /      |      \
                    /       |       \
              Stream<T>  IntStream  LongStream  DoubleStream
                  |         |          |           |
           object elements int        long        double
                  |         |          |           |
               map(...)    sum()      sum()       sum()
               collect()   average()  average()   average()
                           toArray()  toArray()   toArray()
```

The diagram illustrates API relationships and does not depict the full inheritance tree. Type-wise, `IntStream`, `LongStream`, and `DoubleStream` are specialized interfaces extending `BaseStream`; they are **not** subtypes of `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>`.

| Feature | `Stream<T>` | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- | --- |
| Element form | Object `T` | `int` | `long` | `double` |
| Example value | `Integer.valueOf(5)` | `5` | `5L` | `5.0` |
| `map` | `Function<T,R>` | `IntUnaryOperator` | `LongUnaryOperator` | `DoubleUnaryOperator` |
| `filter` | `Predicate<T>` | `IntPredicate` | `LongPredicate` | `DoublePredicate` |
| Direct sum | No general `sum()` | `sum(): int` | `sum(): long` | `sum(): double` |
| Average calculation | Custom logic/collector | `average(): OptionalDouble` | `average(): OptionalDouble` | `average(): OptionalDouble` |
| Collect to array | `Object[]` or `T[]` via generator | `int[]` | `long[]` | `double[]` |
| Convert to object stream | Already an object stream | `boxed()` → `Stream<Integer>` | `boxed()` → `Stream<Long>` | `boxed()` → `Stream<Double>` |

### 1.1. Why not use Stream<Integer> in all cases?

`Integer` is a wrapper object, whereas `int` is a primitive value. For example:

```java
Stream<Integer> objectNumbers = Stream.of(1, 2, 3);
IntStream primitiveNumbers = IntStream.of(1, 2, 3);
```

Both sources represent the same numeric values, but their processing paths differ:

```text
Stream<Integer>
  Integer ──unbox──► int ──compute──► int ──box──► Integer
       (may occur across related transformation operations)

IntStream
    int ────────────► int ────────────► int
```

One should not conclude that every operation on `Stream<Integer>` allocates a new object: the JVM and JIT have their own optimizations, and speed depends on actual data. However, primitive streams **clearly express numeric processing intent** and avoid requiring wrappers at the interface of specialized operations.

### 1.2. There is no standard FloatStream, ByteStream, or ShortStream

In `java.util.stream`, the three standard primitive stream interfaces are `IntStream`, `LongStream`, and `DoubleStream`. Java does not have corresponding `FloatStream`, `ByteStream`, or `ShortStream` in this API.

When computations with `byte`, `short`, or `char` are needed, `IntStream` can be used after appropriately converting/widening the values; for `float`, `DoubleStream` can be used if converting to `double` fits the problem. Do not treat this conversion as a guarantee of exact decimal representation.

## 2. The pipeline structure remains unchanged

Whether using `Stream<T>` or a primitive stream, a pipeline still has three parts:

```text
SOURCE                       INTERMEDIATE                  TERMINAL
IntStream.range(1, 8)  →  filter(n -> n % 2 == 0)  →  sum()
                          map(n -> n * n)
```

Example:

```java
import java.util.stream.IntStream;

class FirstIntStream {
    public static void main(String[] args) {
        int sumOfSquares = IntStream.range(1, 8)
            .filter(n -> n % 2 == 0) // 2, 4, 6
            .map(n -> n * n)         // 4, 16, 36
            .sum();                  // 56

        System.out.println(sumOfSquares);
    }
}
```

`filter` and `map` only describe transformations; when `sum()` is called, the pipeline is evaluated. The principles of **lazy evaluation** and **a Stream is consumed only once** still apply.

```java
IntStream numbers = IntStream.of(1, 2, 3);

int sum = numbers.sum(); // 6
// long count = numbers.count(); // Wrong: Stream has already been consumed.
```

To compute multiple results, create a new Stream from a re-traversable source or produce an aggregated result in a single pass if the API supports it.

## 3. Where can IntStream, LongStream, and DoubleStream be created from?

### 3.1. From direct values: of and empty

```java
IntStream a = IntStream.of(10, 20, 30);
LongStream b = LongStream.of(1L, 2L, 3L);
DoubleStream c = DoubleStream.of(1.5, 2.0, 3.25);

int[] values = a.toArray();       // [10, 20, 30]
long totalLong = b.sum();         // 6
double totalDouble = c.sum();     // 6.75

long emptyCount = IntStream.empty().count(); // 0
```

The `of` methods have overloads taking a single value or an array of the same primitive type. There is no need to pass wrappers into them.

### 3.2. From primitive arrays

`Arrays.stream` provides overloads for `int[]`, `long[]`, and `double[]`:

```java
import java.util.Arrays;

int max = Arrays.stream(new int[] {3, 10, 7})
    .max()
    .orElseThrow(); // 10

long count = Arrays.stream(new long[] {100L, 200L})
    .count(); // 2

double average = Arrays.stream(new double[] {1.0, 3.0})
    .average()
    .orElseThrow(); // 2.0
```

If the target is already an `int[]`, `Arrays.stream(data)` usually expresses intent more clearly than wrapping it into `Stream<Integer>`.

**Distinguishing `int[]` from `Integer[]`:** `Arrays.stream(new Integer[] {1, 2})` returns `Stream<Integer>` because it is an object array; `Arrays.stream(new int[] {1, 2})` returns `IntStream`.

### 3.3. Generating integer ranges: range and rangeClosed

`IntStream` and `LongStream` have two factory methods for consecutive sequences:

| Method | Generated values | Note |
| --- | --- | --- |
| `IntStream.range(2, 6)` | `2, 3, 4, 5` | End bound is **exclusive**. |
| `IntStream.rangeClosed(2, 6)` | `2, 3, 4, 5, 6` | End bound is **inclusive**. |
| `LongStream.range(2L, 6L)` | `2, 3, 4, 5` as `long` | End bound is exclusive. |
| `LongStream.rangeClosed(2L, 6L)` | `2, 3, 4, 5, 6` as `long` | End bound is inclusive. |

Example of generating array indices:

```java
String[] names = {"An", "Binh", "Chi"};

List<String> labels = IntStream.range(0, names.length)
    .mapToObj(index -> index + ": " + names[index])
    .toList();

// [0: An, 1: Binh, 2: Chi]
```

If `startInclusive >= endExclusive`, `range` produces no elements; if `startInclusive > endInclusive`, `rangeClosed` also produces no elements.

`DoubleStream` does not have standard `range` or `rangeClosed`. Generating a `double` sequence by repeatedly adding a floating-point step can accumulate rounding errors; if a sequence at fixed intervals is needed, consider generating indices with `IntStream` and then mapping:

```java
double[] values = IntStream.rangeClosed(0, 4)
    .mapToDouble(index -> index * 0.25)
    .toArray(); // [0.0, 0.25, 0.5, 0.75, 1.0]
```

### 3.4. From a generation rule: iterate and generate

`iterate` typically expresses a sequence where each subsequent element depends on the previous one:

```java
int[] powersOfTwo = IntStream.iterate(1, n -> n * 2)
    .limit(5)
    .toArray(); // [1, 2, 4, 8, 16]
```

Since Java 9, there is an overload with a stopping condition:

```java
long[] multiples = LongStream.iterate(
        2L,
        n -> n <= 10L,
        n -> n + 2L
    )
    .toArray(); // [2, 4, 6, 8, 10]
```

`generate` accepts a supplier and invokes it whenever the next value is needed:

```java
double[] fixedValues = DoubleStream.generate(() -> 1.25)
    .limit(3)
    .toArray(); // [1.25, 1.25, 1.25]
```

`iterate` or `generate` sources have no natural termination point when using the infinite overload. With terminal operations that must read the entire source—such as `sum`, `toArray`, or global `sorted`—ensure the pipeline has an appropriate termination mechanism.

### 3.5. From Collections, text, or other APIs

When starting with an object collection, convert to a primitive stream using `mapToInt`, `mapToLong`, or `mapToDouble`:

```java
List<String> numbers = List.of("5", "12", "8");

int total = numbers.stream()
    .mapToInt(Integer::parseInt)
    .sum(); // 25
```

From `String`, two special methods exist:

```java
IntStream utf16Units = "Java".chars();
IntStream codePoints = "Java".codePoints();
```

`chars()` returns UTF-16 code units as `int`, while `codePoints()` returns Unicode code points. For characters outside the BMP, a single code point may be represented by two UTF-16 code units; the two Streams can differ in element count.

When reading data from a file with `Files.lines(path)`, lines can be converted into numbers:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

class ReadScores {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("scores.txt"); // Each line is a valid integer.

        try (Stream<String> lines = Files.lines(path)) {
            int total = lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .mapToInt(Integer::parseInt)
                .sum();

            System.out.println(total);
        }
    }
}
```

`Files.lines` must be closed via `try-with-resources`. Converting to `IntStream` **does not automatically release the underlying resources** of the file-reading Stream; the lifecycle of the source must be managed.

## 4. Specialized intermediate operations

The three primitive streams provide many operations similar to `Stream<T>`, but accept specialized functional interfaces:

| Operation | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| Filter elements | `filter(IntPredicate)` | `filter(LongPredicate)` | `filter(DoublePredicate)` |
| Same-type mapping | `map(IntUnaryOperator)` | `map(LongUnaryOperator)` | `map(DoubleUnaryOperator)` |
| Flatten sub-streams | `flatMap(IntFunction<? extends IntStream>)` | `flatMap(LongFunction<? extends LongStream>)` | `flatMap(DoubleFunction<? extends DoubleStream>)` |
| Remove duplicates | `distinct()` | `distinct()` | `distinct()` |
| Sort ascending | `sorted()` | `sorted()` | `sorted()` |
| Limit/skip | `limit`, `skip` | `limit`, `skip` | `limit`, `skip` |
| Observe elements | `peek(IntConsumer)` | `peek(LongConsumer)` | `peek(DoubleConsumer)` |

### 4.1. filter and map preserve the primitive type

```java
int[] results = IntStream.of(-3, 2, 5, 6, 2)
    .filter(n -> n > 0)
    .map(n -> n * n)
    .distinct()
    .sorted()
    .toArray();

// [4, 25, 36]
```

After each `filter`, `map`, `distinct`, and `sorted` on an `IntStream`, the return type remains `IntStream`. The same applies to `LongStream` and `DoubleStream` when using same-type overloads.

`sorted()` on a primitive stream uses the natural order of the numeric type. Unlike `Stream<T>.sorted(comparator)`, primitive streams **do not have a `sorted(Comparator)` overload**. If a custom comparison rule is needed, you can call `boxed()` and then `sorted(comparator)`:

```java
List<Integer> descending = IntStream.of(3, 1, 2)
    .boxed()
    .sorted(Comparator.reverseOrder())
    .toList(); // [3, 2, 1]
```

The example requires `import java.util.Comparator;`. Switching to an object stream introduces wrappers; take that into account if the processing path handles a very large volume of data.

### 4.2. flatMap on primitive streams

`flatMap` allows each input value to produce 0, 1, or more values of the same primitive type:

```java
int[] repeated = IntStream.of(1, 3)
    .flatMap(n -> IntStream.rangeClosed(1, n))
    .toArray();

// [1, 1, 2, 3]
```

Input `1` produces `1`, and `3` produces `1,2,3`. Sub-streams created by the mapper are closed by `flatMap` after their contents are placed into the result, per the API contract.

### 4.3. lazy evaluation and short-circuiting

`filter`, `map`, `peek`, and intermediate operations remain **lazy**:

```java
IntStream pipeline = IntStream.rangeClosed(1, 10)
    .filter(n -> {
        System.out.println("Checking: " + n);
        return n % 2 == 0;
    });

System.out.println("Pipeline declared");
int first = pipeline.findFirst().orElseThrow(); // 2
```

For a sequential Stream, `findFirst()` only needs to inspect up to `2`; the pipeline does not need to scan all ten elements. Therefore, do not place mandatory state-updating logic inside `peek` or intermediate lambdas.

Operations such as `sorted` and `distinct` are stateful; they can incur memory overhead or affect short-circuiting capability, especially in parallel processing.

## 5. Converting between primitive streams and Stream<T>

This is an important skill because many APIs require objects, whereas numeric computations fit primitive types.

### 5.1. mapToInt, mapToLong, and mapToDouble

From `Stream<T>`, these methods take a numeric extraction function:

```java
record Product(String name, int quantity, long unitPrice, double rating) {}

List<Product> products = List.of(
    new Product("Book", 2, 75_000L, 4.5),
    new Product("Pen", 5, 12_000L, 4.0)
);

int totalQuantity = products.stream()
    .mapToInt(Product::quantity)
    .sum(); // 7

long totalRevenue = products.stream()
    .mapToLong(p -> p.unitPrice() * p.quantity())
    .sum(); // 210000

double averageRating = products.stream()
    .mapToDouble(Product::rating)
    .average()
    .orElse(0.0); // 4.25
```

`mapToInt` accepts `ToIntFunction<Product>`; `mapToLong` accepts `ToLongFunction<Product>`; `mapToDouble` accepts `ToDoubleFunction<Product>`.

The `long` revenue calculation above assumes that the multiplication and sum do not exceed `Long.MAX_VALUE`. For business logic requiring overflow control, add arithmetic checks or choose a suitable numeric type.

### 5.2. boxed: returning to a wrapper stream

`boxed()` converts primitive values into their corresponding wrappers:

```java
List<Integer> ids = IntStream.rangeClosed(1, 4)
    .boxed()
    .toList(); // [1, 2, 3, 4]

List<Long> times = LongStream.of(10L, 20L)
    .boxed()
    .toList(); // [10, 20]

List<Double> temperatures = DoubleStream.of(20.5, 22.0)
    .boxed()
    .toList(); // [20.5, 22.0]
```

`boxed()` is useful when:

- `List<Integer>`, `List<Long>`, or `List<Double>` is needed.
- `Collectors.groupingBy`, `Collectors.toMap`, or a collector only available on `Stream<T>` is needed.
- Passing a custom `Comparator` to `sorted(comparator)` is needed.
- An API only accepts `Stream<T>` or an object collection.

Not every pipeline should call `boxed()` right from the start: keep numeric processing in `IntStream`/`LongStream`/`DoubleStream` for as long as it is beneficial, and convert only when objects are actually needed.

### 5.3. mapToObj: creating objects from numeric values

If the result is an object other than the wrapper of the number itself, use `mapToObj`:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(n -> "Item " + n)
    .toList();

// [Item 1, Item 2, Item 3]
```

An example using an array:

```java
String[] names = {"An", "Binh", "Chi"};

List<String> indexed = IntStream.range(0, names.length)
    .mapToObj(i -> (i + 1) + ". " + names[i])
    .toList();

// [1. An, 2. Binh, 3. Chi]
```

`mapToObj` returns `Stream<R>`; subsequent operations use the object stream API.

### 5.4. Converting between primitive stream types

Operations table:

| Source | Operation | Output |
| --- | --- | --- |
| `IntStream` | `asLongStream()` | `LongStream` (widening `int → long`). |
| `IntStream` | `asDoubleStream()` | `DoubleStream` (widening `int → double`). |
| `LongStream` | `asDoubleStream()` | `DoubleStream` (`long → double`, may lose precision). |
| `IntStream` | `mapToLong(IntToLongFunction)` | `LongStream`. |
| `IntStream` | `mapToDouble(IntToDoubleFunction)` | `DoubleStream`. |
| `LongStream` | `mapToInt(LongToIntFunction)` | `IntStream`. |
| `DoubleStream` | `mapToInt(DoubleToIntFunction)` | `IntStream`. |
| `DoubleStream` | `mapToLong(DoubleToLongFunction)` | `LongStream`. |

Example:

```java
long total = IntStream.of(100, 200, 300)
    .asLongStream()
    .sum(); // 600

double adjusted = LongStream.of(1L, 2L, 3L)
    .mapToDouble(n -> n * 1.5)
    .sum(); // 9.0
```

There is no `asIntStream()` method on `LongStream` or `DoubleStream`. You must choose a narrowing conversion using `mapToInt` and accept or control the casting rules.

For instance, `(int) someLong` can truncate high bits without raising an error; `Math.toIntExact(someLong)` throws `ArithmeticException` if it exceeds the `int` range:

```java
int[] exact = LongStream.of(10L, 20L)
    .mapToInt(Math::toIntExact)
    .toArray(); // [10, 20]
```

## 6. Specialized terminal operations for arithmetic

Primitive streams come with terminal operations that the general `Stream<T>` lacks:

| Operation | IntStream | LongStream | DoubleStream |
| --- | --- | --- | --- |
| `sum()` | `int` | `long` | `double` |
| `average()` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |
| `min()` / `max()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `count()` | `long` | `long` | `long` |
| `summaryStatistics()` | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| `reduce(identity, op)` | `int` | `long` | `double` |
| `reduce(op)` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `toArray()` | `int[]` | `long[]` | `double[]` |
| `anyMatch/allMatch/noneMatch` | `boolean` | `boolean` | `boolean` |
| `findFirst/findAny` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |

### 6.1. sum, count, min, and max

```java
int sum = IntStream.of(3, 6, 9).sum();      // 18
long count = LongStream.of(3L, 6L).count(); // 2

int min = IntStream.of(7, 2, 5)
    .min()
    .orElseThrow(); // 2

double max = DoubleStream.of(1.5, 3.5, 2.0)
    .max()
    .orElseThrow(); // 3.5
```

`count()` returns `long` even when the elements belong to an `IntStream`. This illustrates the difference between **the type of each element** and **the type of the aggregated result**.

### 6.2. average returns OptionalDouble

`average()` may have no result on an empty Stream, so Java returns `OptionalDouble`:

```java
OptionalDouble avg = IntStream.of(10, 20, 30).average();

if (avg.isPresent()) {
    System.out.println(avg.getAsDouble()); // 20.0
}
```

You can use `orElse(...)` if the application has a default policy:

```java
double averageOrZero = IntStream.empty()
    .average()
    .orElse(0.0);
```

`0.0` in the example is an **application choice**, not the mathematical average of an empty set. When an empty result carries business meaning, keep `OptionalDouble` so the caller decides how to handle it.

### 6.3. summaryStatistics: multiple statistics in a single pass

`summaryStatistics()` computes count, sum, minimum, maximum, and average over the same Stream:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

class ScoresStatistics {
    public static void main(String[] args) {
        IntSummaryStatistics stats = IntStream.of(6, 8, 10, 8)
            .summaryStatistics();

        System.out.println(stats.getCount());   // 4
        System.out.println(stats.getSum());     // 32 (long)
        System.out.println(stats.getMin());     // 6
        System.out.println(stats.getMax());     // 10
        System.out.println(stats.getAverage()); // 8.0
    }
}
```

Similarly:

```java
LongSummaryStatistics longStats =
    LongStream.of(10L, 20L, 30L).summaryStatistics();

DoubleSummaryStatistics doubleStats =
    DoubleStream.of(1.5, 2.5, 3.0).summaryStatistics();
```

Both `LongSummaryStatistics` and `DoubleSummaryStatistics` reside in `java.util`. If the program needs multiple metrics simultaneously, a single `summaryStatistics()` call is usually clearer than creating new Streams to call `sum`, `min`, `max`, and `average` individually.

### 6.4. reduce and associativity

`reduce` uses a combining function to collapse elements into a single value:

```java
int product = IntStream.of(2, 3, 4)
    .reduce(1, (left, right) -> left * right); // 24

long sum = LongStream.of(10L, 20L, 30L)
    .reduce(0L, Long::sum); // 60
```

For sources that may be processed in parallel, the `reduce` operator must satisfy *associativity*, and the identity must be appropriate. Subtraction `(a, b) -> a - b` is not associative, so the result can change when elements are grouped differently.

With floating-point numbers, **`double` arithmetic does not strictly obey mathematical associativity in all cases** due to rounding. Use `sum()` and `summaryStatistics()` where appropriate rather than writing a custom floating-point addition reduction and expecting identical results across every evaluation order.

## 7. How does collect on primitive streams differ from collect(Collector)?

`Stream<T>` has the common overload:

```java
<R, A> R collect(Collector<? super T, A, R> collector);
```

Primitive streams have their own `collect` method taking **three parameters**:

```java
// Simplified signature shape on IntStream:
<R> R collect(
    Supplier<R> supplier,
    ObjIntConsumer<R> accumulator,
    BiConsumer<R, R> combiner
);
```

For `LongStream` and `DoubleStream`, the accumulator is `ObjLongConsumer<R>` and `ObjDoubleConsumer<R>`, respectively.

Example building a StringBuilder from an IntStream:

```java
import java.util.stream.IntStream;

StringBuilder builder = IntStream.rangeClosed(1, 4)
    .collect(
        StringBuilder::new,
        (text, number) -> {
            if (text.length() > 0) text.append(", ");
            text.append(number);
        },
        (left, right) -> {
            if (left.length() > 0 && right.length() > 0) {
                left.append(", ");
            }
            left.append(right);
        }
    );

System.out.println(builder.toString()); // 1, 2, 3, 4
```

`supplier` creates the accumulation container, `accumulator` updates it with each primitive value, and `combiner` merges partial results when the framework requires it, such as in parallel execution. The combiner must be semantically compatible with the accumulator and initial value.

When wanting to use `Collectors.groupingBy`, switch to an object stream:

```java
Map<String, Long> counts = IntStream.of(1, 2, 3, 4, 5, 6)
    .boxed()
    .collect(Collectors.groupingBy(
        n -> n % 2 == 0 ? "even" : "odd",
        Collectors.counting()
    ));

// {even=3, odd=3} (key order in the Map is not guaranteed)
```

The example requires importing `java.util.Map` and `java.util.stream.Collectors`. This connects to the grouping and custom collectors sections of the JAVA_STREAM_API module: many standard collectors operate on objects, while primitive streams optimize numeric calculations.

## 8. Complete example: order line statistics

Consider order lines having an `int` quantity, an integer `long` unit price, and a `double` rating score. The goal is to count total quantity, compute revenue, get average rating, and group revenue by product category.

Standalone runnable example on Java 17+; save as `PrimitiveStreamDemo.java`:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class PrimitiveStreamDemo {
    record OrderLine(
        String category,
        int quantity,
        long unitPrice,
        double rating
    ) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("Books", 2, 120_000L, 4.5),
            new OrderLine("Books", 1, 80_000L, 4.0),
            new OrderLine("Equipment", 3, 150_000L, 5.0),
            new OrderLine("Equipment", 0, 200_000L, 4.0)
        );

        // Stream<OrderLine> -> IntStream -> IntSummaryStatistics.
        IntSummaryStatistics quantityStats = lines.stream()
            .mapToInt(OrderLine::quantity)
            .summaryStatistics();

        // Stream<OrderLine> -> LongStream -> long.
        long totalRevenue = lines.stream()
            .mapToLong(line ->
                Math.multiplyExact(
                    (long) line.quantity(),
                    line.unitPrice()
                )
            )
            .sum();

        // Stream<OrderLine> -> DoubleStream -> OptionalDouble.
        OptionalDouble averageRating = lines.stream()
            .filter(line -> line.quantity() > 0)
            .mapToDouble(OrderLine::rating)
            .average();

        // When grouping is needed, use a Collector on Stream<OrderLine>.
        Map<String, Long> revenueByCategory = lines.stream()
            .collect(Collectors.groupingBy(
                OrderLine::category,
                TreeMap::new,
                Collectors.summingLong(line ->
                    Math.multiplyExact(
                        (long) line.quantity(),
                        line.unitPrice()
                    )
                )
            ));

        System.out.println(quantityStats.getSum());         // 6
        System.out.println(totalRevenue);                   // 770000
        System.out.println(averageRating.orElse(0.0));      // 4.5
        System.out.println(revenueByCategory);
        // {Books=320000, Equipment=450000}
    }
}
```

Structural breakdown:

| Goal | Processing path | Reason for choice |
| --- | --- | --- |
| Total quantity and related statistics | `mapToInt(OrderLine::quantity).summaryStatistics()` | Keeps `int` data and obtains a `long` sum along with min/max/count/average. |
| Total revenue | `mapToLong(...).sum()` | Monetary amount as integer `long` to avoid floating-point errors for whole currency values. |
| Average rating score | `mapToDouble(OrderLine::rating).average()` | Result has type `OptionalDouble` because the filtered set may be empty. |
| Revenue by category | `collect(groupingBy(..., summingLong(...)))` | Uses a collector to build `Map<String,Long>` from business objects. |

Total revenue `770000` does not exceed the `long` range in the example. `Math.multiplyExact` detects overflow on **each individual multiplication**, but `LongStream.sum()` and the addition inside `Collectors.summingLong` can still overflow if the sum exceeds `long` range. For business cases requiring guaranteed overflow protection, choose a checked addition strategy (such as `Math.addExact` in an appropriate reduction) or a larger numeric type.

The rating `4.5` here is the average of the three **order lines with positive quantity**, not an average weighted by product units. If a weighted average is required, multiply each rating by its weight and divide by the total weight.

## 9. IntStream and LongStream: integer overflow

Primitive streams do not automatically change the value domain of a numeric type. `IntStream.sum()` returns `int` and can overflow when the sum exceeds the limit:

```java
int overflow = IntStream.of(Integer.MAX_VALUE, 1)
    .sum();

System.out.println(overflow); // -2147483648 (int overflow)
```

To convert each `int` to `long` before adding:

```java
long safeForThisInput = IntStream.of(Integer.MAX_VALUE, 1)
    .asLongStream()
    .sum();

System.out.println(safeForThisInput); // 2147483648
```

`LongStream.sum()` can also overflow `long`. Widening from `int` to `long` expands the value domain but does not eliminate all risks.

### 9.1. sum and summaryStatistics have different sum return types

`IntStream.sum()` returns `int`, whereas `IntSummaryStatistics.getSum()` returns `long`:

```java
long sum = IntStream.of(Integer.MAX_VALUE, 1)
    .summaryStatistics()
    .getSum(); // 2147483648
```

This is an important distinction when the sum can exceed `Integer.MAX_VALUE`. For problems needing only a `long` sum, `asLongStream().sum()` is usually simpler and expresses intent clearly.

### 9.2. Checking overflow before producing a result

If business rules mandate failing when the sum exceeds `long`:

```java
long exact = LongStream.of(10L, 20L, 30L)
    .reduce(0L, Math::addExact); // 60
```

`Math.addExact` throws `ArithmeticException` if an intermediate addition overflows. This checked addition is associative with respect to results within the representable domain, but for sums that may exceed the limit, the grouping order of additions in a parallel stream still affects **when or whether an intermediate overflow is detected**; choose a data processing policy and execution order accordingly.

If a sum exceeding `long` range is needed, consider `BigInteger`. If monetary data has decimal places and requires rounding by financial rules, consider storing the smallest unit as an integer or using `BigDecimal`; `DoubleStream` is not a tool that guarantees decimal monetary accuracy.

## 10. DoubleStream: rounding error, NaN, and infinity

`double` is an IEEE 754 binary floating-point number. Many decimal fractions cannot be represented exactly in binary:

```java
double result = DoubleStream.of(0.1, 0.2).sum();

System.out.println(result == 0.3); // Do not rely on this comparison.
```

In the example, the printed result of the comparison expression depends on representation and the summation algorithm; what to remember is **never use exact equality between two computed floating-point results as a general business rule**.

### 10.1. sum() and average() have finite precision

`DoubleStream.sum()` allows implementations to use compensated summation to improve accuracy, yet the API **does not guarantee a fixed summation order**; different groupings of additions or parallel execution can produce slightly different results due to rounding.

```java
double sum = DoubleStream.of(0.1, 0.2, 0.3).sum();
OptionalDouble average = DoubleStream.of(0.1, 0.2, 0.3)
    .average();
```

When comparing approximate computed results, choose an allowable error (*tolerance*) suited to the problem domain:

```java
double expected = 0.6;
double actual = DoubleStream.of(0.1, 0.2, 0.3).sum();

boolean closeEnough = Math.abs(actual - expected) < 1e-9;
```

The threshold `1e-9` is only an example. For numbers of widely varying magnitudes, consider relative error, absolute error, or specialized numerical algorithms.

### 10.2. NaN, Infinity, and negative zero

`DoubleStream` can contain:

- `Double.NaN`: *Not a Number* value.
- `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY`.
- `0.0` and `-0.0`: both equal zero in many operations, yet have different bit representations.

Example:

```java
double[] values = DoubleStream.of(
        1.0,
        Double.NaN,
        -0.0,
        0.0,
        Double.POSITIVE_INFINITY
    )
    .sorted()
    .toArray();
```

`DoubleStream.sorted()` uses the order defined by `Double.compare`: `-0.0` comes before `0.0`; `NaN` is considered greater than all numeric values under that ordering, including `POSITIVE_INFINITY`.

`DoubleStream.distinct()` identifies duplicates according to `Double.doubleToLongBits`; thus `NaN` is considered a duplicate of `NaN`, while `-0.0` and `0.0` are considered **distinct**:

```java
long count = DoubleStream.of(-0.0, 0.0, Double.NaN, Double.NaN)
    .distinct()
    .count(); // 3
```

`DoubleStream.sum()` and `average()` can return `NaN` when the source contains `NaN`. When processing measurement or statistical data, decide explicitly how to filter or record missing or non-finite values:

```java
double[] finite = DoubleStream.of(1.5, Double.NaN, 3.0,
                                 Double.POSITIVE_INFINITY)
    .filter(Double::isFinite)
    .toArray(); // [1.5, 3.0]
```

**Note:** filtering out `NaN` or infinite values can cause statistics to hide input errors. Define the data policy before filtering.

### 10.3. long → double can lose precision

`double` has 53 bits of significand precision, so it cannot represent **every** large `long` integer exactly.

```java
long value = 9_007_199_254_740_993L; // 2^53 + 1
double asDouble = LongStream.of(value)
    .asDoubleStream()
    .findFirst()
    .orElseThrow();

System.out.println((long) asDouble == value); // false
```

The conversion `long → double` is a widening conversion in Java's type system, yet it does not guarantee preserving every large integer value. If data consists of IDs, very large timestamps, or exact integer monetary amounts, avoid using `DoubleStream` merely for calculation convenience.

## 11. OptionalInt, OptionalLong, and OptionalDouble

Operations such as `min`, `max`, `findFirst`, `findAny`, and `reduce` without an identity need to represent the **no element** case.

```java
OptionalInt smallest = IntStream.empty().min();
OptionalLong firstLong = LongStream.empty().findFirst();
OptionalDouble largest = DoubleStream.empty().max();

System.out.println(smallest.isPresent()); // false
System.out.println(firstLong.isEmpty());  // true (Java 11+)
System.out.println(largest.orElse(-1.0)); // -1.0
```

Comparison with `Optional<T>` used for object streams:

| Primitive stream | Optional type | Retrieve value when present |
| --- | --- | --- |
| `IntStream` | `OptionalInt` | `getAsInt()` |
| `LongStream` | `OptionalLong` | `getAsLong()` |
| `DoubleStream` | `OptionalDouble` | `getAsDouble()` |

Prefer `orElse`, `orElseGet` (where the API supports it), or `orElseThrow` when the data policy is clearly defined. Do not call `getAsInt()` on `OptionalInt.empty()` without checking, as it throws `NoSuchElementException`.

With an empty source, aggregate operations do not always return an Optional: `sum()` on `IntStream.empty()` is `0`, `count()` is `0L`, whereas `average()` is `OptionalDouble.empty()`. Distinguish the additive identity value from the non-existence of an average.

## 12. Sources, ordering, performance, and parallel streams

Primitive streams provide `sequential()`, `parallel()`, and `unordered()` like other Stream types. When a source has an encounter order, operations such as `findFirst` and `limit` respect that order.

```java
long total = LongStream.rangeClosed(1, 1_000_000)
    .parallel()
    .sum();
```

Calling `parallel()` requests parallel mode but **does not automatically guarantee faster execution**. Benefit depends on source size, per-element cost, `Spliterator` splitting capability, stateful operations, and result combination overhead.

### 12.1. Keep lambdas free of dependent state

Do not share a mutable counter across threads:

```java
// Do not do the following:
// int[] shared = {0};
// IntStream.range(0, 1000).parallel()
//     .forEach(n -> shared[0] += n);
```

This is a race condition and can yield wrong results. Use a specialized terminal operation:

```java
long total = IntStream.range(0, 1000)
    .parallel()
    .asLongStream()
    .sum(); // 499500
```

Lambdas in `filter`, `map`, and `reduce` should not cause side effects that modify the source or shared state. Every collector and accumulator function must obey the combinability contract when running in parallel.

### 12.2. Specialized Spliterators

Primitive streams use `Spliterator.OfInt`, `Spliterator.OfLong`, and `Spliterator.OfDouble` when traversing or splitting sources, thereby avoiding wrapping elements at the specialized consumer interface.

Example accessing a `Spliterator.OfInt`:

```java
import java.util.Spliterator;
import java.util.stream.IntStream;

class PrimitiveSpliterator {
    public static void main(String[] args) {
        Spliterator.OfInt source = IntStream.range(1, 4)
            .spliterator();

        source.forEachRemaining((int n) -> System.out.println(n));
        // 1, 2, 3
    }
}
```

Do not obtain a `Spliterator` from a Stream, consume it, and then expect to call a terminal operation on the same Stream. Obtaining an iterator/spliterator consumes the Stream's source under the single-use lifecycle.

Characteristics such as `SIZED`, `SUBSIZED`, and `ORDERED` can support work splitting and optimizations. These characteristics belong to the actual source; they do not appear simply because the elements have a primitive type.

### 12.3. Boxing and benchmarking

Primitive streams are usually well suited when a pipeline only computes over numbers. However, performance is also affected by:

- Data size and source creation cost.
- Number of intermediate operations and JVM/JIT optimization capability.
- `boxed()` or `mapToObj` steps that require object creation/dispatch.
- Having to sort, deduplicate, group, or maintain order in parallel execution.
- Memory, garbage collection, and input data volume.

Do not write benchmarks based on a single runtime measurement. When making technical decisions based on performance, use a tool such as JMH and data representative of the application.

## 13. When to choose which Stream type?

| Input / goal | Reasonable choice | Notes |
| --- | --- | --- |
| `int[]` data, summing or filtering integers | `IntStream` | `Arrays.stream(int[])` or `IntStream.of(...)`. |
| Sequence of indices or consecutive integers | `IntStream.range/rangeClosed` | Be careful with exclusive/inclusive end bounds. |
| Large quantities, timestamps, or integer prices in `long` range | `LongStream` | Check for overflow during addition/multiplication. |
| Measurement data or approximate floating-point values | `DoubleStream` | Accept binary rounding error and choose a NaN policy. |
| List of objects, need to sum an `int` property | `stream().mapToInt(...).sum()` | Convert to primitive after extracting the property. |
| List of objects, need to sum a `long` property | `stream().mapToLong(...).sum()` | Well suited for integer statistics. |
| Need `List<Integer>` | `intStream.boxed().toList()` | Involves boxing to create wrappers. |
| Need display labels from indices | `intStream.mapToObj(...)` | Returns `Stream<R>`. |
| Need `Collectors.groupingBy` on primitive values | `intStream.boxed().collect(...)` | Standard collectors run on object streams. |
| Need custom descending numeric sort | `intStream.boxed().sorted(Comparator.reverseOrder())` | Primitive `sorted()` does not take a Comparator. |
| Exact decimal financial calculations | `BigDecimal` or integer representation in smallest unit | Avoid assuming `double` has exact precision. |

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `sum()` on `Stream<Integer>` | `Stream<T>` has no specialized `sum()` operation. | `mapToInt(Integer::intValue).sum()` or an `IntStream` source. |
| Thinking `IntStream` is `Stream<Integer>` | Incompatible with overloads requiring `Stream<T>`. | Use `boxed()` when a wrapper stream is needed. |
| Calling `collect(Collectors.toList())` directly on `IntStream` | Primitive `collect` has a three-argument signature and does not take a `Collector`. | `boxed().collect(Collectors.toList())` or `boxed().toList()`. |
| Using `IntStream.sum()` for sums that may exceed `int` | Overflow and wrong result. | `asLongStream().sum()` or an overflow-checking approach. |
| Computing money with `DoubleStream` and comparing for exact equality | Floating-point representation error. | Use integer smallest units or `BigDecimal` as required. |
| Casting large `long` to `double` assuming value is always preserved | Precision bits can be lost. | Keep `long` or choose an appropriate numeric type. |
| Calling `average().getAsDouble()` on an empty Stream | `NoSuchElementException`. | Handle `OptionalDouble` explicitly. |
| Calling `sorted(Comparator)` directly on `IntStream` | No overload accepts a Comparator. | `boxed().sorted(comparator)` or an appropriate algorithm. |
| Omitting `limit` when collecting an infinitely generated Stream | Terminal operation may never terminate. | Use an appropriate limit or stopping condition. |
| Using a shared mutable variable in `parallel().forEach` | Race condition. | Use `sum`, `reduce`, `summaryStatistics`, or `collect` appropriately. |
| Reusing a primitive Stream after a terminal operation | `IllegalStateException`. | Create a new Stream from a re-traversable source. |
| Failing to close a Stream reading from a file | I/O resource leak. | `try-with-resources` on the source Stream. |

## 15. Practice exercises

**Exercise 1 — Number sequence.** Use `IntStream.rangeClosed(1, 100)` to compute the sum of squares of numbers divisible by 3. Clearly explain the roles of the source, intermediate operations, and terminal operation.

**Exercise 2 — Single-pass statistics.** Given an `int[]` array containing 100 exam scores, use `summaryStatistics()` to obtain count, sum, min, max, and average. Compare the return types of `sum()` and `getSum()`.

**Exercise 3 — Type conversion.** Given a `List<String>` containing `"12", "5", "8"`, convert to an `IntStream` and compute the sum. Try a non-numeric string and decide how to handle `NumberFormatException`.

**Exercise 4 — Large sums.** Use `IntStream.of(Integer.MAX_VALUE, 1)`. Compare `sum()`, `asLongStream().sum()`, and `summaryStatistics().getSum()`. Explain why the results differ.

**Exercise 5 — Non-finite floats.** Use `DoubleStream.of(1.0, Double.NaN, 2.0, Double.POSITIVE_INFINITY)`. Compute the sum before and after `filter(Double::isFinite)`. State the data policy when removing invalid values.

**Exercise 6 — Grouping.** With `IntStream.rangeClosed(1, 20)`, build a `Map<String, Long>` counting even/odd numbers using `boxed().collect(Collectors.groupingBy(..., counting()))`.

**Exercise 7 — Monetary calculation.** With `OrderLine(quantity, unitPrice)`, compute a `long` total using `mapToLong`. Add inputs large enough to identify where overflow occurs and choose a checking strategy.

Hint for Exercise 1:

```java
int result = IntStream.rangeClosed(1, 100)
    .filter(n -> n % 3 == 0)
    .map(n -> n * n)
    .sum();
```

The sum of squares in this range fits within `int`; with a larger upper bound, you need to evaluate overflow risk at `n * n` even before the `sum()` step.

## 16. Core takeaways

- **`IntStream`, `LongStream`, and `DoubleStream`** are specialized primitive streams, not `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>`.
- **The pipeline model remains source → lazy intermediate → terminal.** The main difference lies in the element type and specialized arithmetic operations/functional interfaces.
- **`range` and `rangeClosed`** generate `int`/`long` sequences; `of`, `Arrays.stream`, `iterate`, and `generate` create other sources. Potentially infinite sources need a stopping condition.
- **`mapToInt` / `mapToLong` / `mapToDouble`** go from an object stream to a primitive stream; **`boxed`** returns to a wrapper stream; **`mapToObj`** creates an object stream from primitive values.
- **`sum`, `average`, `min`, `max`, `summaryStatistics`, and `reduce`** provide properly typed arithmetic results; `OptionalInt`, `OptionalLong`, and `OptionalDouble` represent potentially absent results.
- **`IntStream.sum()` can overflow `int`; `LongStream.sum()` can overflow `long`; `DoubleStream` is subject to floating-point error, NaN, and Infinity.** Choose data types according to business domain requirements.
- **Primitive `collect` takes supplier, accumulator, and combiner**, while standard collectors like `groupingBy` are typically used with `Stream<T>` or after `boxed()`.
- **Do not reuse a consumed Stream**, do not rely on side effects in intermediate lambdas, and always close I/O sources. Parallelism is only beneficial when the source, operations, and data volume are suitable.
- Knowledge of primitive streams forms the foundation for choosing how to extract data for grouping, custom collectors, `Spliterator`, parallel Streams, and advanced transformations in **JAVA_STREAM_API**.
