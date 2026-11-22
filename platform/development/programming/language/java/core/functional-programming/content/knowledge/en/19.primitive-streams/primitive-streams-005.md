# `boxed()`, `mapToObj()`, and Conversions Between Primitive Streams in Java

## 1. Why Does Java Have Primitive Streams?

The Java Stream API has the generic type `Stream<T>` for processing objects, but `int`, `long`, and `double` are **primitive types** (*primitive*), not objects that can be used directly as generic type arguments. Therefore, the JDK provides three specialized streams:

- `IntStream`: a stream of `int` values.
- `LongStream`: a stream of `long` values.
- `DoubleStream`: a stream of `double` values.

These streams reside in `java.util.stream`, have primitive-specific operations such as `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()`, and can reduce boxing/unboxing overhead in large numeric processing pipelines.

Example:

```java
import java.util.stream.IntStream;

int total = IntStream.rangeClosed(1, 5).sum();
System.out.println(total); // 15
```

`IntStream.rangeClosed(1,5)` generates the numbers 1, 2, 3, 4, 5. The `sum()` terminal operation returns an `int`, without needing to create an `Integer` for each element in the logical representation of the pipeline.

When data must be used by an API that works with objects (`List<Integer>`, `Collectors.groupingBy`, `Map`, `Stream<String>`...) or when each number needs to be transformed into a new object, we must choose the appropriate conversion. Three main questions:

1. **`boxed()`:** Keep the same numeric value but convert to a **wrapper object**?
2. **`mapToObj()`:** Use each primitive value to create an **object of any type**?
3. **`mapToInt`/`mapToLong`/`mapToDouble`, `asLongStream`/`asDoubleStream`:** How to convert the **stream kind** or **numeric type**?

## 2. `boxed()`: From Primitive Stream to Wrapper `Stream`

The signatures can be pictured as follows:

```java
// IntStream:
Stream<Integer> boxed();

// LongStream:
Stream<Long> boxed();

// DoubleStream:
Stream<Double> boxed();
```

The three `boxed()` methods are **parameterless** methods on each primitive stream. They produce the object stream corresponding to the wrapper of the primitive element:

| Input | Call | Result Type |
| --- | --- | --- |
| `IntStream` | `.boxed()` | `Stream<Integer>` |
| `LongStream` | `.boxed()` | `Stream<Long>` |
| `DoubleStream` | `.boxed()` | `Stream<Double>` |

Example:

```java
List<Integer> numbers = IntStream.rangeClosed(1, 4)
        .boxed()
        .toList();

System.out.println(numbers); // [1, 2, 3, 4]
```

`import java.util.List;` and `import java.util.stream.IntStream;` are needed when placed inside a method. Each `int` from `IntStream` is converted into a wrapper `Integer` value to be provided through `Stream<Integer>`. Having objects does not mean you can rely on `==` identity of individual wrappers: when working with numbers, compare values using numeric operators or `equals` as appropriate for the type.

### Why Not Just Use `Stream<int>`?

`Stream<int>` is **invalid** because a Java generic type argument must be a reference type. If you need an object stream, use `Stream<Integer>` or call `boxed()` on `IntStream`.

### `boxed()` Does Not Create a List Immediately

`boxed()` is an **intermediate operation** that returns a new stream, not a `List<Integer>`. A terminal operation is required when concrete data is needed:

```java
Stream<Integer> boxed = IntStream.of(10, 20).boxed();
List<Integer> result = boxed.toList(); // [10, 20]
```

Like any stream, the `boxed` object cannot be reused after it has been consumed. `Stream.toList()` (Java 16+) returns a `List` that **does not support modification methods** such as `add`/`remove`. If you want a mutable list:

```java
List<Integer> mutable = new java.util.ArrayList<>(
        IntStream.of(10, 20).boxed().toList()
);
mutable.add(30);
System.out.println(mutable); // [10, 20, 30]
```

Choose `boxed()` when you **only need to convert `int → Integer`**, `long → Long`, or `double → Double` for compatibility with APIs that use reference types, rather than transforming the content into a new model.

## 3. `mapToObj()`: From Primitive to an Arbitrary Object

`mapToObj` takes a function mapping **one primitive value → an object of type `U`**. Corresponding signatures:

```java
// IntStream:
<U> Stream<U> mapToObj(IntFunction<? extends U> mapper);

// LongStream:
<U> Stream<U> mapToObj(LongFunction<? extends U> mapper);

// DoubleStream:
<U> Stream<U> mapToObj(DoubleFunction<? extends U> mapper);
```

While `boxed()` only produces the wrapper with the same numeric value, `mapToObj` can create a `String`, `record`, DTO, or other object.

Example:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "Item-" + n)
        .toList();

System.out.println(labels); // [Item-1, Item-2, Item-3]
```

Pipeline shape:

```text
IntStream            --mapToObj(n -> "Item-" + n)--> Stream<String>
1, 2, 3                                             "Item-1", "Item-2", "Item-3"
```

If you want an object that holds multiple pieces of information:

```java
record Score(String id, int points) {}

List<Score> scores = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> new Score("S" + n, n * 10))
        .toList();

// [Score[id=S1, points=10], Score[id=S2, points=20],
//  Score[id=S3, points=30]]
```

`record` is officially supported since Java 16. This is an **illustrative** snippet to be placed inside an appropriate class; a complete Java 17 program appears in a later section.

### Two Ways Equivalent in Content, Not in Expressiveness

For each `int`, an `Integer` can be created in both ways:

```java
Stream<Integer> a = IntStream.of(1, 2).boxed();
Stream<Integer> b = IntStream.of(1, 2).mapToObj(Integer::valueOf);
```

Both produce a stream of wrapper objects with contents 1, 2. However, `boxed()` **explicitly states the boxing intent** and is more concise. `mapToObj` is suitable when mapping to another type such as `String`, `Score`, or `BigDecimal`.

There is no need to write `.boxed().map(n -> "Item-" + n)` when it can be expressed directly with `.mapToObj(n -> "Item-" + n)`: the direct version avoids an intermediate wrapper step in the API model. Actual performance still depends on the JVM and workload; to claim one is faster or slower requires benchmarking.

## 4. Converting Back: `Stream<T>` to `IntStream`, `LongStream`, `DoubleStream`

On an object stream, there are three important methods:

```java
IntStream mapToInt(ToIntFunction<? super T> mapper);
LongStream mapToLong(ToLongFunction<? super T> mapper);
DoubleStream mapToDouble(ToDoubleFunction<? super T> mapper);
```

The mapper takes an object `T` and produces a specific primitive value. For example, converting `Stream<String>` to `IntStream`:

```java
int total = Stream.of("12", "8", "5")
        .mapToInt(Integer::parseInt)
        .sum();

System.out.println(total); // 25
```

Here:

- `Stream.of(...)` has type `Stream<String>`.
- `Integer.parseInt(String)` returns `int`, matching `ToIntFunction<String>`.
- `mapToInt` returns `IntStream`.
- `sum()` is a terminal operation of `IntStream`, returning `int`.

Converting wrapper to primitive:

```java
List<Integer> values = List.of(2, 4, 6);

double mean = values.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow();

System.out.println(mean); // 4.0
```

`average()` on `IntStream` returns `OptionalDouble` because an empty stream has no average. With the data in the example, the average is 4.0; if the source is empty and `orElseThrow()` is called, a `NoSuchElementException` is thrown. Do not call `getAsDouble()` unchecked on `OptionalDouble.empty()`.

### Converting Possibly Null Data Must Be Handled Before Unboxing

`Stream<Integer>` can contain `null` references if created from a source that allows nulls (unlike `List.of`). Calling `Integer::intValue` on null throws a `NullPointerException`:

```java
List<Integer> values = new java.util.ArrayList<>();
values.add(2);
values.add(null);
values.add(5);

// Runtime ERROR: calling intValue() on null.
// int total = values.stream().mapToInt(Integer::intValue).sum();

int safeTotal = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(safeTotal); // 7
```

Only skip nulls if business rules allow it. If null represents corrupted data or missing required data, validate and report an error instead of silently ignoring it.

## 5. Direct Conversions Between Primitive Stream Types

The three primitive streams have specialized type-conversion operations. Common diagram:

```text
IntStream  --asLongStream()----> LongStream
IntStream  --asDoubleStream()--> DoubleStream
LongStream --asDoubleStream()--> DoubleStream

IntStream  --mapToLong(IntToLongFunction)--> LongStream
IntStream  --mapToDouble(IntToDoubleFunction)--> DoubleStream
LongStream --mapToInt(LongToIntFunction)--> IntStream
LongStream --mapToDouble(LongToDoubleFunction)--> DoubleStream
DoubleStream --mapToInt(DoubleToIntFunction)--> IntStream
DoubleStream --mapToLong(DoubleToLongFunction)--> LongStream
```

### `asLongStream()`: Widening `int` to `long`

```java
long sum = IntStream.rangeClosed(1, 4)
        .asLongStream()
        .sum();

System.out.println(sum); // 10
```

`asLongStream()` converts each `int` to `long` via primitive widening conversion. Every `int` value is represented exactly by `long`; this is also useful when a sum exceeds the `int` range, **but `long` addition can still overflow** if the sum is too large.

### `asDoubleStream()`: Widening to `double`

```java
double average = IntStream.of(2, 4, 6)
        .asDoubleStream()
        .average()
        .orElseThrow();

System.out.println(average); // 4.0
```

All `int` values are represented exactly as `double`, because `double` has enough integer precision for the 32-bit range. However, **`LongStream.asDoubleStream()` does not guarantee that every `long` value is preserved exactly**, because `double` only has 53 bits of significand precision.

### `mapToLong`/`mapToDouble` for Custom Transformations

```java
long squares = IntStream.of(2, 3, 4)
        .mapToLong(n -> (long) n * n)
        .sum();

System.out.println(squares); // 29
```

Unlike `asLongStream()` which only changes the type, `mapToLong(...)` can both change the type and transform the value. Casting `(long) n` **before multiplying** avoids intermediate multiplication in the `int` range when `n` is large enough.

## 6. Narrowing Types: Make Data Loss Explicit

There is no `LongStream.asIntStream()` because `long → int` is a **narrowing conversion** that can lose values. Instead, `LongStream.mapToInt(LongToIntFunction)` forces you to state the transformation explicitly.

Example:

```java
List<Integer> small = LongStream.of(10L, 20L)
        .mapToInt(Math::toIntExact)
        .boxed()
        .toList();

System.out.println(small); // [10, 20]
```

`Math.toIntExact(long)` throws `ArithmeticException` if the value is outside the `int` range. This is a good choice when the business requirement is **no information loss**.

Conversely:

```java
int narrowed = (int) 3_000_000_000L;
System.out.println(narrowed); // -1294967296
```

The primitive cast `(int)` can produce a result that has lost its high bits. Using `mapToInt(n -> (int) n)` without checking can lead to silently wrong numbers. For `double → int/long`, Java has floating-point-to-integer conversion rules (in which the fractional part is truncated toward 0; NaN/out-of-range cases have their own rules). If the business logic requires rounding, apply an explicit rounding policy and range check before converting.

### Precision in `long → double`

Verifiable illustrative example:

```java
long original = 9_007_199_254_740_993L; // 2^53 + 1
double converted = (double) original;
long roundTrip = (long) converted;

System.out.println(original == roundTrip); // false
```

The number `2^53 + 1` is not represented exactly in standard binary `double`. Therefore `LongStream.asDoubleStream()` can lose precision for large integers even though the compiler allows the conversion. Do not use this conversion path for large integer IDs/monetary amounts if exactness must be preserved. For currency, prefer `BigDecimal` or an integer type with an explicit unit, along with a defined rounding policy.

## 7. Complete Java 17 Program: Converting and Aggregating Data

The example below processes scores, `long` values, and numeric strings. The goal is to verify exact return types, boxing, converting to objects, returning to primitives, and detecting loss during narrowing.

Create the file **`PrimitiveStreamConversionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamConversionDemo {
    record Score(String id, int points) {}

    public static void main(String[] args) {
        // 1. boxed(): IntStream -> Stream<Integer> -> List<Integer>.
        List<Integer> boxedNumbers = IntStream.rangeClosed(1, 4)
                .boxed()
                .toList();
        System.out.println("Boxed: " + boxedNumbers);

        // 2. mapToObj(): IntStream -> Stream<String>.
        List<String> labels = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> "Item-" + n)
                .toList();
        System.out.println("Labels: " + labels);

        // 3. mapToObj(): create a new record instead of just boxing.
        List<Score> scores = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> new Score("S" + n, n * 10))
                .toList();
        System.out.println("Scores: " + scores);

        // 4. Object Stream -> IntStream to aggregate numbers.
        int parsedSum = Stream.of("7", "11", "2")
                .mapToInt(Integer::parseInt)
                .sum();
        System.out.println("Parsed sum: " + parsedSum);

        // 5. boxed() allows using a collector on Stream<Integer>.
        Map<String, List<Integer>> groups = IntStream.rangeClosed(1, 6)
                .boxed()
                .collect(Collectors.groupingBy(
                        n -> n % 2 == 0 ? "even" : "odd",
                        TreeMap::new,
                        Collectors.toList()
                ));
        System.out.println("Grouped: " + groups);

        // 6. IntStream -> LongStream via primitive widening.
        long longSum = IntStream.rangeClosed(1, 4)
                .asLongStream()
                .sum();
        System.out.println("Long sum: " + longSum);

        // 7. IntStream -> DoubleStream, then compute the average.
        double mean = IntStream.of(2, 4, 6)
                .asDoubleStream()
                .average()
                .orElseThrow();
        System.out.println("Mean: " + mean);

        // 8. LongStream -> Stream<String> using mapToObj().
        List<String> longLabels = LongStream.of(10L, 20L)
                .mapToObj(n -> "L" + n)
                .toList();
        System.out.println("Long labels: " + longLabels);

        // 9. DoubleStream -> Stream<Double> using boxed().
        List<Double> decimals = DoubleStream.of(1.5, 2.5)
                .boxed()
                .toList();
        System.out.println("Decimals: " + decimals);

        // 10. LongStream -> IntStream: convert within valid range.
        List<Integer> checked = LongStream.of(10L, 20L)
                .mapToInt(Math::toIntExact)
                .boxed()
                .toList();
        System.out.println("Checked narrowing: " + checked);

        // 11. Detect a long value that does not fit in int.
        try {
            LongStream.of(3_000_000_000L)
                    .mapToInt(Math::toIntExact)
                    .sum();
        } catch (ArithmeticException ex) {
            System.out.println("Narrowing rejected: ArithmeticException");
        }

        // 12. Wrapper data that may contain null must be checked.
        List<Integer> possiblyNull = new ArrayList<>();
        possiblyNull.add(2);
        possiblyNull.add(null);
        possiblyNull.add(5);
        int validSum = possiblyNull.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("Null-safe sum: " + validSum);

        // 13. Map a record to a primitive using a numeric field.
        int scoreSum = scores.stream()
                .mapToInt(Score::points)
                .sum();
        System.out.println("Score sum: " + scoreSum);

        // 14. Long -> double can lose precision.
        long large = 9_007_199_254_740_993L;
        long roundTrip = (long) ((double) large);
        System.out.println("Precise round trip: " + (large == roundTrip));

        // 15. Empty stream: no average value.
        System.out.println("Empty average: "
                + IntStream.empty().average().isEmpty());
    }
}
```

Compile and run:

```bash
javac --release 17 PrimitiveStreamConversionDemo.java
java PrimitiveStreamConversionDemo
```

**Deterministic stdout:**

```text
Boxed: [1, 2, 3, 4]
Labels: [Item-1, Item-2, Item-3]
Scores: [Score[id=S1, points=10], Score[id=S2, points=20], Score[id=S3, points=30]]
Parsed sum: 20
Grouped: {even=[2, 4, 6], odd=[1, 3, 5]}
Long sum: 10
Mean: 4.0
Long labels: [L10, L20]
Decimals: [1.5, 2.5]
Checked narrowing: [10, 20]
Narrowing rejected: ArithmeticException
Null-safe sum: 7
Score sum: 60
Precise round trip: false
Empty average: true
```

### Reading the Results by Type

1. `boxedNumbers` has type `List<Integer>`, contents `[1,2,3,4]`. `boxed()` does not change the numbers; it only creates a wrapper object stream.
2. `labels` has type `List<String>`, contents `Item-1`, `Item-2`, `Item-3`. `mapToObj` applied the rule to transform into another object.
3. `scores` has type `List<Score>`; `record` automatically provides `toString()` formatted with the type name and components. `Score("S1",10)` is printed as `Score[id=S1, points=10]`.
4. `parsedSum` equals `7+11+2=20`. `mapToInt(Integer::parseInt)` creates an `IntStream` to use `sum()`.
5. `groups` creates a `Stream<Integer>` via `boxed()` and then `Collectors.groupingBy` with `TreeMap::new`, so the displayed key order is deterministic: `even` before `odd`. Group values preserve encounter order: `even=[2,4,6]`, `odd=[1,3,5]`.
6. `asLongStream` preserves the exact values `1..4` and the sum is `10`. `asDoubleStream` produces `2.0`, `4.0`, `6.0`, so the average is `4.0`.
7. `LongStream.mapToObj` creates labels from `long`. `DoubleStream.boxed` returns `Double` wrappers.
8. `Math.toIntExact` succeeds for `10L`, `20L` but throws `ArithmeticException` for `3_000_000_000L`, instead of silently converting to an inaccurate number.
9. `Objects::nonNull` filters out null references before unboxing. If null has a specific business meaning, it must be represented and handled rather than skipped.
10. `scores.stream().mapToInt(Score::points).sum()` returns `10+20+30=60`.
11. The `long` value exceeds `double`'s exact integer representation capability, so the round trip returns `false`. `IntStream.empty().average()` returns `OptionalDouble.empty()` and `isEmpty()` is `true`.

The entire program uses ordered sources and appropriate terminal operations; the output does not depend on parallel stream execution order or wrapper object identity.

## 8. When to Use `boxed` Before a Collector?

Many collectors such as `Collectors.groupingBy` or `Collectors.toMap` work with **`Stream<T>`** and do not accept `IntStream` directly. When you need to group numbers by key:

```java
Map<String, List<Integer>> grouped = IntStream.rangeClosed(1, 6)
        .boxed()
        .collect(Collectors.groupingBy(
                n -> n % 2 == 0 ? "even" : "odd",
                TreeMap::new,
                Collectors.toList()
        ));
```

`boxed()` is a reasonable choice because the content being collected is still `Integer`. However, when you only want **sum, min, max, average, count**, primitive streams already have specialized terminal operations:

```java
int sum = IntStream.rangeClosed(1, 100).sum();
long count = IntStream.rangeClosed(1, 100).count();
int max = IntStream.rangeClosed(1, 100).max().orElseThrow();
```

There is no need for `boxed()` just to call `collect(Collectors.summingInt(...))` if `sum()` already solves the problem properly. `boxed` can introduce extra boxing overhead compared to keeping a continuous primitive pipeline.

### Primitive `collect` Exists, but Differs from Object `Collector`

Primitive streams also have their own `collect` overload, for example `IntStream.collect(Supplier<R>, ObjIntConsumer<R>, BiConsumer<R,R>)`. It does not directly accept a `Collector<T,A,R>` like `Stream<T>.collect(Collector)`. Therefore, to use `Collectors.groupingBy` on integer elements, `boxed()` is the clear path.

## 9. Reference Table of Important Conversion Types

| Source | Method | Target | When to Use |
| --- | --- | --- | --- |
| `IntStream` | `boxed()` | `Stream<Integer>` | Using generic collectors/APIs requiring objects |
| `LongStream` | `boxed()` | `Stream<Long>` | Getting `Long` wrappers |
| `DoubleStream` | `boxed()` | `Stream<Double>` | Getting `Double` wrappers |
| `IntStream` | `mapToObj(IntFunction<U>)` | `Stream<U>` | Creating String/record/DTO |
| `LongStream` | `mapToObj(LongFunction<U>)` | `Stream<U>` | Creating objects from `long` |
| `DoubleStream` | `mapToObj(DoubleFunction<U>)` | `Stream<U>` | Creating objects from `double` |
| `Stream<T>` | `mapToInt(ToIntFunction<T>)` | `IntStream` | Parsing or extracting `int` |
| `Stream<T>` | `mapToLong(ToLongFunction<T>)` | `LongStream` | Extracting `long` |
| `Stream<T>` | `mapToDouble(ToDoubleFunction<T>)` | `DoubleStream` | Extracting `double` |
| `IntStream` | `asLongStream()` | `LongStream` | Widening `int → long` |
| `IntStream` | `asDoubleStream()` | `DoubleStream` | Widening `int → double` |
| `LongStream` | `asDoubleStream()` | `DoubleStream` | Widening `long → double`, may lose precision |
| `LongStream` | `mapToInt(LongToIntFunction)` | `IntStream` | Narrowing with a checking policy |
| `DoubleStream` | `mapToInt(DoubleToIntFunction)` | `IntStream` | Applying explicit `double → int` rules |
| `DoubleStream` | `mapToLong(DoubleToLongFunction)` | `LongStream` | Applying explicit `double → long` rules |
| `IntStream` | `mapToLong(IntToLongFunction)` | `LongStream` | Converting type and transforming |
| `IntStream` | `mapToDouble(IntToDoubleFunction)` | `DoubleStream` | Converting type and transforming |

In Java, the generics `ToIntFunction<? super T>`/`ToLongFunction<? super T>`/`ToDoubleFunction<? super T>` accept an input object and return a primitive. Other specialized interface names may need to be imported from `java.util.function`; `java.util.stream` is the package containing Stream.

## 10. Primitive Types and Numeric Operations: Avoiding Misconceptions

### `sum()` Does Not Automatically Prevent Overflow

`IntStream.sum()` returns `int`; addition can overflow if the result exceeds the `int` range. For example, summing a million large values can be inaccurate even without boxing.

If the sum may exceed `int`, widen to `long` before aggregating:

```java
long total = IntStream.of(1_500_000_000, 1_500_000_000)
        .asLongStream()
        .sum();

System.out.println(total); // 3000000000
```

`IntStream.of(...).sum()` returns `int`, which cannot hold the result `3,000,000,000` in the `int` range. `asLongStream()` widens each element before adding, so it is sufficient in this example.

Although `long` is larger, it still has limits. When numbers may exceed `long` limits, consider `BigInteger` or `BigDecimal` with an appropriate precision definition.

### `average()` on an Empty Stream Does Not Return 0

`IntStream.empty().average()` returns `OptionalDouble.empty()`, not "an average value of 0". The average of a set with no elements is **undefined** under standard calculation; use `orElse(default)` if the business logic truly wants to assign a default.

### `DoubleStream` Has Floating-Point Characteristics

Operations on `double` can encounter `NaN`, positive/negative infinity, and rounding errors. `DoubleStream.boxed()` does not make the data more accurate; it only converts `double` to the `Double` wrapper. For currency or auditing, decide on the numeric type before choosing a stream.

### Wrappers `Integer`, `Long`, `Double` Are Not Primitives

`Stream<Integer>` holds reference objects and can contain `null` if the source allows it. `IntStream` cannot have `null` elements: every element is already an `int`. If you need to represent "there might be no number", use appropriate models such as `OptionalInt` for **a single optional result**, rather than secretly encoding null with a valid value like `0`.

## 11. Single-Use Streams and Laziness

The methods `boxed`, `mapToObj`, `mapToInt`, and `asLongStream` are **intermediate operations**. They do not immediately traverse the entire source; instead, they construct a lazy pipeline that is evaluated when a terminal operation such as `sum()`, `toList()`, or `collect(...)` runs.

```java
IntStream numbers = IntStream.of(1, 2, 3);
Stream<Integer> objects = numbers.boxed();

System.out.println(objects.toList()); // [1, 2, 3]

// Error: the stream source has already been used in a pipeline/consumed.
// System.out.println(numbers.sum());
```

If you need to compute two different results, create two sources:

```java
List<Integer> list = IntStream.of(1, 2, 3).boxed().toList();
int sum = IntStream.of(1, 2, 3).sum();
```

Avoid putting important side effects into a mapper under the assumption that it always runs once for every element. Short-circuiting terminal operations, arbitrary sources, optimizations, and parallel pipelines can affect execution. Chaining conversions across multiple streams does not make them execute independently without a terminal operation.

## 12. Primitive Mapping Differs from Object Mapping

On `IntStream`, the `map` method does **not** return `Stream<R>`; it takes `IntUnaryOperator` and returns `IntStream`:

```java
IntStream doubled = IntStream.rangeClosed(1, 3)
        .map(n -> n * 2);

System.out.println(doubled.boxed().toList()); // [2, 4, 6]
```

On `Stream<Integer>`, `map` takes `Function<Integer,R>` and can return `Stream<R>`:

```java
Stream<String> labels = IntStream.rangeClosed(1, 3)
        .boxed()
        .map(n -> "n=" + n);
```

Direct `mapToObj` approach:

```java
Stream<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "n=" + n);
```

Within the same local scope, you cannot declare two variables with the same name `labels` consecutively; the snippets above are **two alternative approaches**, not meant to be combined in the same method. The goal is to recognize the **stream type at each step**:

- `IntStream.map(IntUnaryOperator)`: `int → int`.
- `IntStream.mapToObj(IntFunction<R>)`: `int → object R`.
- `Stream<T>.map(Function<T,R>)`: `object T → object R`.
- `Stream<T>.mapToInt(ToIntFunction<T>)`: `object T → int`.

The variants on `LongStream` and `DoubleStream` follow the same principle, but the primitive conversion interface names change according to the input/output types.

## 13. Generics, Ordering, and Parallelism

When the source has an encounter order, the conversions `boxed`/`mapToObj`/`mapToInt` do not implicitly erase the encounter order. Example:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
        .parallel()
        .mapToObj(n -> "N" + n)
        .toList();

System.out.println(labels); // [N1, N2, N3]
```

`IntStream.rangeClosed` is ordered, and `toList()` preserves the encounter order, even when the pipeline may process elements in parallel. However, do not assume the lambda `n -> "N" + n` executes sequentially on a single thread. Avoid updating an external `ArrayList` from `parallel().forEach(...)`: an unprotected mutable collection can suffer from data races.

For primitive streams, terminal operations `sum`/`average`/`count` are usually more convenient than manually using `forEach` to accumulate. For numeric operations that require strict associativity (especially floating-point), evaluate stability and result contracts before parallelizing.

## 14. Common Mistakes

| Mistake | Cause | Correct Approach |
| --- | --- | --- |
| `Stream<int>` | Generics do not accept primitives | `IntStream` or `Stream<Integer>` |
| Thinking `boxed()` returns `List<Integer>` | It returns `Stream<Integer>` | Add terminal `toList()`/`collect` |
| `IntStream.map(n -> "N"+n)` | `IntStream.map` requires `int → int` | `mapToObj(n -> "N"+n)` |
| `IntStream.boxed().sum()` | `Stream<Integer>` has no `sum()` | `IntStream.sum()` or `mapToInt(...).sum()` |
| `Stream<String>.mapToInt(...)` with a mapper returning `String` | Mapper must return `int` | `Integer::parseInt` or extract a number |
| Thinking `mapToObj` always boxes | It allows converting to any object | Use `boxed()` if only wrappers are needed |
| Ignoring `null` before `Integer::intValue` | Unboxing causes NPE | Validate or `filter(Objects::nonNull)` intentionally |
| Using `(int) longValue` without checking | Can lose data when narrowing | `Math.toIntExact` or validation |
| Thinking `long → double` is always exact | Large integers can exceed 53-bit precision | Keep `long`/`BigInteger` if exactness is needed |
| Using `IntStream.sum()` for sums outside `int` range | Overflow can silently be wrong | `asLongStream().sum()` if `long` suffices |
| Calling `average().getAsDouble()` on an empty stream | No average result exists | `orElse`/`orElseThrow` and a clear policy |
| Reusing a stream after `boxed().toList()` | Streams are single-use | Recreate the source |
| Switching to `parallel` and manually adding to an external `List` | Unsafe shared mutable state | Collect using a terminal collector/`toList` |

## 15. Practice Exercises

1. Write `IntStream.rangeClosed(1,5).boxed().toList()` and state the type at each stage: `IntStream` → `Stream<Integer>` → `List<Integer>`.
2. From the numbers `1..5`, use `mapToObj(n -> "ID-" + n)` to get a list of strings. Why is `boxed()` not needed?
3. Use `Stream.of("10","20","30").mapToInt(Integer::parseInt).sum()`. **Result:** `60`. Identify the input type of the mapper and the result type.
4. Use `IntStream.of(1_500_000_000,1_500_000_000).asLongStream().sum()`. Why does the addition preserve `3,000,000,000` while `IntStream.sum()` does not guarantee it?
5. Group the numbers `1..8` into `even` and `odd` using `boxed().collect(groupingBy(...))`. State the reason for converting to an object stream with a general-purpose collector.
6. From `Stream<Score>`, use `mapToInt(Score::points)` to compute the total points. Compare this with `map(Score::points)` which has type `Stream<Integer>`.
7. Write `DoubleStream.of(1.5, 2.5).mapToObj(value -> "v=" + value).toList()`. The result is `[v=1.5, v=2.5]`.
8. Use `LongStream.of(10L, 3_000_000_000L).mapToInt(Math::toIntExact)` and a terminal operation to traverse it. Explain the exception on the second value.
9. From a `List<Integer>` containing a null element, test the execution path of `mapToInt(Integer::intValue)` and choose an appropriate null-handling policy.
10. Compute the average on `IntStream.empty()`. Why must `OptionalDouble.empty()` be handled instead of defaulting to `0`?
11. Compare `IntStream.map(n -> n * 2)` with `IntStream.mapToObj(n -> n * 2)`. Even though the numeric contents may be the same, how do the result types and boxing differ?
12. Test the `long` value `2^53+1` through `LongStream.asDoubleStream()` and convert back to `long`. Why cannot `double` be used to store every `long` exactly?
13. Use `IntStream.rangeClosed(1,3).parallel().mapToObj(...).toList()` and explain why the output element order remains deterministic even though the mapper execution order cannot be guaranteed.
14. Try designing a problem using exact monetary amounts: decide whether to store integers in minor units or use `BigDecimal`, and only box when entering collection/generic APIs.

## 16. Checklist Before Converting Stream Types

- Is the current input type `Stream<T>` or `IntStream`/`LongStream`/`DoubleStream`?
- Does the output need a **wrapper of the same value** (`boxed`) or a **new object** (`mapToObj`)?
- Can it stay primitive up to a terminal `sum`/`average` to avoid unnecessary boxing?
- Do you need to use a generic `Collector` or an API that accepts `Stream<T>`?
- When converting object → primitive, can the data be `null`? Does the mapper return the exact `int`/`long`/`double` type?
- When converting `long → int` or `long → double`, is there a risk of range or precision loss?
- For large sums, is the `int`/`long` result type sufficient, or is `BigInteger`/`BigDecimal` needed?
- Can the terminal operation return an empty `OptionalInt`/`OptionalLong`/`OptionalDouble`?
- Are you reusing an already-consumed stream or introducing side effects into a parallel mapper?
- Have you tested at least the cases of **empty, null in object source, boundary values, narrowing conversions, overflow, and ordered results**?

**Remember:** `boxed()` converts a primitive stream into a wrapper `Stream`; `mapToObj()` converts a primitive into any object; `mapToInt`/`mapToLong`/`mapToDouble` convert an object stream into a primitive stream; `asLongStream`/`asDoubleStream` are convenient widening conversions. Choose based on the **desired data type**, precision, and business contract, not merely because a method call chain looks shorter.
