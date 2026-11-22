# Avoiding Unnecessary Boxing in Numeric Computations with Java Stream

When computing sums, averages, maximum values, or statistics over a sequence of numbers, the choice of Stream type affects processing overhead. `Stream<Integer>`, `Stream<Long>`, and `Stream<Double>` hold **references to wrapper objects**; whereas `IntStream`, `LongStream`, and `DoubleStream` specialize in processing the corresponding **primitive values**. Passing through unnecessary wrappers can cause boxing/unboxing, increasing memory usage, allocation volume, and garbage collector pressure.

The goal of this lesson is to identify **when wrapper types are actually needed**, when to use primitive streams to keep numeric operations in primitive form, and how to avoid premature or incorrect optimizations that alter the meaning of the data.

Core example:

~~~java
List<Integer> values = List.of(2, 3, 5);

// Easily creates boxed intermediates when the source/target type requires Integer:
int boxed = values.stream()
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

// Numeric operations stay on IntStream after unboxing the source elements:
int primitive = values.stream()
        .mapToInt(Integer::intValue)
        .map(n -> n * 2)
        .sum();
~~~

Both produce a sum of `20`. The `List<Integer>` source still holds `Integer` instances, so unboxing cannot be completely eliminated when reading from the list. However, the second pipeline avoids continuing to use `Integer` for **the intermediate arithmetic steps**, and uses the `sum()` terminal operation directly.

The snippet above requires `import java.util.List;` and must be placed inside a method. The compiler/JVM can optimize away some temporary objects via the JIT, so one should not claim that every `map` operation necessarily allocates a new `Integer`. It is important to understand the difference in **API types and potential overhead**, and then measure performance if optimization is the goal.

## 1. What are boxing and unboxing?

Java has primitive types `int`, `long`, `double` and the corresponding wrapper classes `Integer`, `Long`, `Double`. **Boxing** converts a primitive value into a wrapper reference; **unboxing** extracts the primitive value from a wrapper:

~~~java
int primitiveValue = 42;
Integer boxedValue = primitiveValue; // Autoboxing: Integer.valueOf(42)
int restored = boxedValue;           // Unboxing: boxedValue.intValue()
~~~

Autoboxing is useful when an API requires objects, such as generic collections. However, when iterating over large volumes of numeric data, creating/retaining wrappers in unnecessary steps can consume extra resources.

Example:

~~~java
Stream<Integer> boxedStream = Stream.of(1, 2, 3);
IntStream intStream = IntStream.of(1, 2, 3);
~~~

`Stream<Integer>` passes `Integer` through the pipeline; `IntStream` represents data as `int`. In the `Stream.of(1, 2, 3)` call, the `int` literals are boxed to match the Stream's `Integer` type. `IntStream.of(...)` has overloads that accept `int` values and provides specialized operators.

**Overhead does not live at every syntactic boundary in the source code.** In practice, it also depends on the JDK, escape analysis, JIT, data size, and the JVM's ability to eliminate allocations. However, choosing primitive types helps the API express the true nature of numeric operations and avoids the need for boxing across multiple stages.

## 2. The three primitive stream families

| Stream Family | Element Type | Common Operations |
| --- | --- | --- |
| `IntStream` | `int` | `map(IntUnaryOperator)`, `sum()`, `average()`, `summaryStatistics()` |
| `LongStream` | `long` | `map(LongUnaryOperator)`, `sum()`, `max()`, `average()` |
| `DoubleStream` | `double` | `map(DoubleUnaryOperator)`, `sum()`, `average()`, `summaryStatistics()` |

All these classes reside in `java.util.stream`. They are **primitive specializations** of the Stream API, not `Stream<int>` or `Stream<double>`: Java generics do not allow primitive types as type arguments.

Basic sources:

~~~java
IntStream oneToFive = IntStream.rangeClosed(1, 5);
LongStream identifiers = LongStream.of(10L, 20L, 30L);
DoubleStream prices = DoubleStream.of(1.5, 2.25, 3.75);
~~~

The illustrative snippet requires importing the three classes `IntStream`, `LongStream`, `DoubleStream`; streams are single-use. After a terminal operation such as `sum()`, they are consumed.

From a primitive array:

~~~java
int[] items = {2, 4, 6};
int total = Arrays.stream(items).sum(); // 12
~~~

Requires `java.util.Arrays`. `Arrays.stream(int[])` creates an `IntStream`, whereas `Arrays.stream(Integer[])` creates a `Stream<Integer>`. If a system performs arithmetic on arrays, keeping `int[]` or `long[]` can avoid the cost of representing each element as a wrapper as in `Integer[]`.

## 3. `mapToInt()`, `mapToLong()`, and `mapToDouble()`

When the source is a `Stream<T>` (for example, a list of domain objects), use a direct numeric extractor function to convert to a primitive stream.

Suppose we have:

~~~java
record Sale(String sku, int quantity, long cents, double rating) {}
~~~

Conversion functions:

~~~java
IntStream quantities = sales.stream().mapToInt(Sale::quantity);
LongStream amounts = sales.stream().mapToLong(Sale::cents);
DoubleStream ratings = sales.stream().mapToDouble(Sale::rating);
~~~

These are **illustrative snippets**, placed inside a method with `List<Sale> sales` and appropriate imports. The method reference `Sale::quantity` is type-compatible with `ToIntFunction<Sale>`; `Sale::cents` with `ToLongFunction<Sale>`; `Sale::rating` with `ToDoubleFunction<Sale>`. These functional interfaces return a primitive instead of a wrapper.

From a wrapper list `List<Integer>`:

~~~java
int sum = values.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

The `Integer::intValue` step unboxes the source elements. After that step, `filter`, `map`, and `sum` operations on `IntStream` work with `int`.

### Distinguishing `map` and `mapToInt`

~~~java
// map takes Function<Sale, Integer> and returns Stream<Integer>:
Stream<Integer> valuesBoxed = sales.stream().map(Sale::quantity);

// mapToInt takes ToIntFunction<Sale> and returns IntStream:
IntStream valuesPrimitive = sales.stream().mapToInt(Sale::quantity);
~~~

The first path requires representing the pipeline's numeric values as wrappers; the second feeds primitive values through the specialized `IntStream`. If the final goal is a sum, average, min/max, or statistics, the second path is usually simpler and more appropriate.

### Extractors for wider types

If `quantity` is an `int` but the sum risks exceeding the `int` range, use `mapToLong` to widen **before** summing:

~~~java
long total = sales.stream()
        .mapToLong(s -> (long) s.quantity())
        .sum();
~~~

This protects against `int` overflow occurring during addition (provided the result fits within the `long` range). Do **not** use `mapToInt(...).sum()` and then cast to `long`: the addition has already overflowed in `int` before the cast.

## 4. Specialized terminal operations for numeric computations

Primitive streams have numeric terminal operations, so you do not need to manually assemble `reduce` for simple aggregations:

| Operation | Example | Result Type |
| --- | --- | --- |
| `int` sum | `IntStream.of(1, 2, 3).sum()` | `int` equal to `6` |
| `long` sum | `LongStream.of(1L, 2L).sum()` | `long` equal to `3` |
| `double` sum | `DoubleStream.of(1.5, 2.0).sum()` | `double` equal to `3.5` |
| Element count | `IntStream.of(1, 2).count()` | `long` equal to `2` |
| Average | `IntStream.of(2, 4).average()` | `OptionalDouble` containing `3.0` |
| Minimum/maximum | `IntStream.of(2, 4).max()` | `OptionalInt` containing `4` |
| Statistics | `IntStream.of(2, 4).summaryStatistics()` | `IntSummaryStatistics` |

`OptionalInt`, `OptionalLong`, and `OptionalDouble` are optional containers specialized for primitives. They allow representing the **absence of a value** without wrapping numbers in `Optional<Integer>`, `Optional<Long>`, or `Optional<Double>`. For example, `IntStream.empty().max()` returns `OptionalInt.empty()`; `IntStream.empty().average()` returns `OptionalDouble.empty()`.

~~~java
OptionalInt maybeMax = IntStream.of(5, 8, 3).max();
int maxOrDefault = maybeMax.orElse(0); // 8

double meanOrZero = IntStream.of(5, 8, 3)
        .average()
        .orElse(0.0); // 5.333333...
~~~

The snippet requires importing `OptionalInt` and `IntStream`. Each `IntStream.of(...)` call creates a new stream, because a stream is consumed after a terminal operation.

### `summaryStatistics()` gathers multiple results in a single pass

`IntStream.summaryStatistics()` provides `count`, `sum`, `min`, `max`, and `average`. When multiple statistics are needed on the same data, it avoids creating separate pipelines to compute each figure.

~~~java
IntSummaryStatistics stats = sales.stream()
        .mapToInt(Sale::quantity)
        .summaryStatistics();

long count = stats.getCount();
long sum = stats.getSum();
int min = stats.getMin();
int max = stats.getMax();
double average = stats.getAverage();
~~~

This snippet belongs inside a method with `sales`; it requires `java.util.IntSummaryStatistics`. An important detail: **`IntSummaryStatistics.getSum()` has return type `long`**, whereas `IntStream.sum()` has return type `int`. Do not confuse the two methods when evaluating overflow limits.

For an empty stream, `IntSummaryStatistics` has count/sum equal to 0 and average equal to 0.0; min is `Integer.MAX_VALUE` and max is `Integer.MIN_VALUE` when there are no elements. Therefore, before using min/max as a meaningful result, you should check `count > 0`.

## 5. Avoid boxed `reduce` when a primitive terminal exists

One way that works with `Stream<Integer>`:

~~~java
int sumBoxed = sales.stream()
        .map(Sale::quantity)
        .reduce(0, Integer::sum);
~~~

`map` creates a `Stream<Integer>`; the `reduce` reduction uses an operator on the wrapper type, introducing potential boxing/unboxing in the processing chain. When the goal is simply an `int` sum, prefer:

~~~java
int sumPrimitive = sales.stream()
        .mapToInt(Sale::quantity)
        .sum();
~~~

The second approach is concise, states the intent clearly, and avoids an intermediate `Stream<Integer>` pipeline. If a different exact result bundle is needed (for example, simultaneously computing a sum, a verification list, and a count), an appropriate collector or accumulator structure can be used, but consider associativity, immutability, and parallelism requirements.

`IntStream.reduce(identity, op)` remains useful when the combining operation is not addition and no specialized terminal exists:

~~~java
int product = IntStream.of(2, 3, 4)
        .reduce(1, (a, b) -> a * b);
// 24
~~~

`IntBinaryOperator` takes two `int` values and returns an `int`. When running in parallel, the reduction function must be **associative** and the identity must be neutral with respect to the combining operation. Multiplication can overflow integers; use another data type if business logic requires no overflow.

### Reducing across multiple numeric types in the same pipeline

Some operations can be done with `mapToLong` or `asLongStream` if addition exceeds `int`:

~~~java
long safeWideSum = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648
~~~

Conversely:

~~~java
int overflow = IntStream.of(Integer.MAX_VALUE, 1).sum();
// -2147483648 due to two's complement int overflow in Java
~~~

The example result shows why widening **before** aggregating matters. However, `long` also has limits; when exceeding `Long.MAX_VALUE` or when arbitrary-precision integers are needed, use `BigInteger` and its appropriate operations, accepting its object nature.

## 6. Converting between object Streams and primitive streams

Java provides several explicit conversion points:

| From | To | Method |
| --- | --- | --- |
| `Stream<T>` | `IntStream` | `mapToInt(ToIntFunction<? super T>)` |
| `Stream<T>` | `LongStream` | `mapToLong(ToLongFunction<? super T>)` |
| `Stream<T>` | `DoubleStream` | `mapToDouble(ToDoubleFunction<? super T>)` |
| `IntStream` | `Stream<Integer>` | `boxed()` |
| `LongStream` | `Stream<Long>` | `boxed()` |
| `DoubleStream` | `Stream<Double>` | `boxed()` |
| `IntStream` | `Stream<R>` | `mapToObj(IntFunction<? extends R>)` |
| `IntStream` | `LongStream` | `asLongStream()` |
| `IntStream` | `DoubleStream` | `asDoubleStream()` |
| `LongStream` | `DoubleStream` | `asDoubleStream()` |

Do not convert back and forth out of habit: switching primitive → object → primitive can negate the advantage of avoiding wrappers in intermediate operations.

### When `boxed()` is necessary

~~~java
List<Integer> values = IntStream.rangeClosed(1, 4)
        .boxed()
        .toList();
// [1, 2, 3, 4]
~~~

`List<Integer>` requires `Integer` objects because generics do not accept `int`. Boxing at **the boundary where storing in a List is required** is reasonable, not a bug. The issue is only boxing **earlier than necessary** when most of the work is still numeric.

If the result is a primitive array, no boxing is needed:

~~~java
int[] squares = IntStream.rangeClosed(1, 4)
        .map(n -> n * n)
        .toArray();
// [1, 4, 9, 16]
~~~

### When `mapToObj` is the right choice

If the target is object data such as strings, records, or DTOs, switch to `Stream<R>`:

~~~java
List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "S" + n)
        .toList();
// [S1, S2, S3]
~~~

This is an **intentional data-type transformation**, not redundant boxing. `mapToObj` accepts an `IntFunction<R>`, whereas `boxed()` only wraps primitive values into their corresponding wrapper type.

### `flatMapToInt` instead of creating an intermediate `Stream<Integer>`

With a `Stream<List<Integer>>`, you can flatten into a primitive stream:

~~~java
List<List<Integer>> groups = List.of(
        List.of(1, 2),
        List.of(3, 4)
);
int sum = groups.stream()
        .flatMapToInt(group -> group.stream().mapToInt(Integer::intValue))
        .sum();
// 10
~~~

The source lists contain wrappers, so unboxing is still required at the boundary. However, after `flatMapToInt`, the aggregation operations use `IntStream`. If the input data is stored in `int[]` arrays, you can use `flatMapToInt(Arrays::stream)` on `Stream<int[]>` to avoid wrappers from the start.

## 7. Complete Java 17+ program

Place the following code in a file named **`PrimitiveStreamDemo.java`**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalInt;
import java.util.stream.IntStream;

public class PrimitiveStreamDemo {
    record Sale(String sku, int quantity, long cents, double rating) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2, 1_500L, 4.0),
                new Sale("B", 3, 2_600L, 4.5),
                new Sale("C", 1, 900L, 3.5),
                new Sale("D", 4, 1_000L, 5.0)
        );

        int quantity = sales.stream().mapToInt(Sale::quantity).sum();
        long cents = sales.stream().mapToLong(Sale::cents).sum();
        double averageRating = sales.stream().mapToDouble(Sale::rating).average().orElse(0.0);
        IntSummaryStatistics stats = sales.stream()
                .mapToInt(Sale::quantity).summaryStatistics();

        int boxedSum = sales.stream().map(Sale::quantity)
                .reduce(0, Integer::sum);
        int flatQuantity = List.of(List.of(1, 2), List.of(3, 4)).stream()
                .flatMapToInt(group -> group.stream().mapToInt(Integer::intValue))
                .sum();

        OptionalInt maximum = sales.stream().mapToInt(Sale::quantity).max();
        List<String> labels = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> "S" + n).toList();
        List<Integer> boxed = IntStream.rangeClosed(1, 4).boxed().toList();
        long squares = IntStream.rangeClosed(1, 4).mapToLong(n -> (long) n * n).sum();
        long safeWideSum = IntStream.of(Integer.MAX_VALUE, 1).asLongStream().sum();

        System.out.println("quantity=" + quantity);
        System.out.println("cents=" + cents);
        System.out.println("averageRating=" + averageRating);
        System.out.println("statistics=" + stats.getCount() + "/" + stats.getMin()
                + "/" + stats.getMax() + "/" + stats.getSum());
        System.out.println("boxedSum=" + boxedSum);
        System.out.println("flatQuantity=" + flatQuantity);
        System.out.println("maximum=" + maximum.orElse(-1));
        System.out.println("labels=" + labels);
        System.out.println("boxed=" + boxed);
        System.out.println("squares=" + squares);
        System.out.println("safeWideSum=" + safeWideSum);
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac PrimitiveStreamDemo.java
java PrimitiveStreamDemo
~~~

**Exact stdout:**

~~~text
quantity=10
cents=6000
averageRating=4.25
statistics=4/1/4/10
boxedSum=10
flatQuantity=10
maximum=4
labels=[S1, S2, S3]
boxed=[1, 2, 3, 4]
squares=30
safeWideSum=2147483648
~~~

Explanation:

1. `mapToInt(Sale::quantity).sum()` sums the quantities 2 + 3 + 1 + 4 = 10 without creating an intermediate `Stream<Integer>`.
2. `mapToLong(Sale::cents).sum()` sums the monetary values in cents, resulting in `6000`; floating point is not used for money calculations.
3. `mapToDouble(Sale::rating).average()` yields an average of `4.25`; `orElse(0.0)` is only used if there are no elements.
4. `summaryStatistics()` aggregates the four quantities: count 4, min 1, max 4, sum 10.
5. `boxedSum` produces the same result but uses `Stream<Integer>` and boxed `reduce`; `flatQuantity` flattens the number groups and then sums using `IntStream`.
6. `maximum` is an `OptionalInt`; `labels` converts to strings via `mapToObj`; `boxed` creates a `List<Integer>` when the output actually requires wrappers.
7. `squares` computes 1² + 2² + 3² + 4² = 30. `safeWideSum` widens `int` to `long` before adding to obtain 2,147,483,648 without `int` overflow.

Each `sales.stream()` call creates a new Stream over the same source list; a Stream that has been consumed after a terminal operation cannot be reused. With JDK 17, the example was compiled with `javac --release 17` and run to verify the exact stdout.

## 8. Commonly overlooked sources of boxing

### Collections containing wrappers from the start

`List<Integer>` always holds wrapper references; converting to `IntStream` does not change the underlying storage structure. If a system runs heavy numeric computations and controls the data format, `int[]`, `long[]`, or specialized primitive structures may be more suitable.

Even so, it is not necessary to convert every `List<Integer>` to an array: if object/generic APIs are needed, the data is small, or arithmetic is not a bottleneck, readability and compatibility may matter more than allocation optimization.

### `map` in an object Stream

~~~java
Stream<Integer> doubled = values.stream().map(n -> n * 2);
~~~

`doubled` has type `Stream<Integer>`; the pipeline must represent results as wrappers at the type level. Choose:

~~~java
IntStream doubledPrimitive = values.stream()
        .mapToInt(Integer::intValue)
        .map(n -> n * 2);
~~~

In this way, after conversion, the `map(IntUnaryOperator)` operator uses primitive types.

### Boxing in collectors

~~~java
List<Integer> result = IntStream.range(0, 1000)
        .boxed()
        .collect(Collectors.toList());
~~~

When the target needs `List<Integer>`, boxing is necessary. But if in the end only the sum is needed, do not build a list only to call `stream()` again:

~~~java
int total = IntStream.range(0, 1000).sum();
~~~

Both illustrative snippets belong inside a method; the collector snippet requires `java.util.stream.Collectors` and `List`.

### Unspecialized generic APIs

Generic interfaces such as `Function<T, R>`, `Predicate<T>`, and `Consumer<T>` work with reference-type arguments. When writing a numeric pipeline with primitive specialization, use the corresponding functional interfaces: `IntUnaryOperator`, `IntPredicate`, `IntConsumer`, `ToIntFunction<T>`, `IntToLongFunction`, etc. They represent parameters/return values in primitive form.

Example:

~~~java
IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .forEach(System.out::println);
~~~

`filter` takes an `IntPredicate`; `map` takes an `IntUnaryOperator`; `forEach` takes an `IntConsumer`. This snippet is an illustration run inside a method, not the main stdout example of the lesson.

## 9. Correctness precautions: overflow, floating point, null

### Overflow is not directly related to boxing

`IntStream.sum()` returns `int`; if the sum exceeds the `int` domain, the result overflows according to Java arithmetic. Use `asLongStream().sum()`, `mapToLong(...)`, or `LongStream` when the result requires `long`. However, `long` also has limits. For large monetary values requiring precision beyond the `long` range, `BigInteger` or `BigDecimal` can be used depending on the problem; objects here are a **requirement for value range/precision**, not redundant boxing.

### Floating-point numbers are not exact

`DoubleStream` processes `double` according to IEEE 754. Decimal numbers like `0.1` may not have an exact binary representation; sums or averages are prone to rounding errors. If calculating money, use integers in the smallest unit (cents) within a reasonable range or `BigDecimal`, rather than substituting `double` just to avoid boxing.

With `DoubleStream`, aggregations must also handle `NaN` and infinite values according to the Java contract. Floating-point addition order can change the result because addition is not strictly associative in computer arithmetic, especially in parallel streams.

### Null wrappers will fail when unboxed

~~~java
List<Integer> nullableValues = Arrays.asList(1, null, 3);
// May throw NullPointerException when encountering null:
// int sum = nullableValues.stream().mapToInt(Integer::intValue).sum();
~~~

`mapToInt(Integer::intValue)` requires non-null `Integer` elements. If the data policy is to ignore nulls, filter first:

~~~java
int sum = nullableValues.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
// 4
~~~

Requires `Arrays` and `Objects` from `java.util`. If null carries another business meaning (missing data, input error), do not silently discard it without stating a policy.

## 10. Parallel streams and real-world performance

Primitive streams help reduce the need for wrappers in numeric computations, but **they do not mean every primitive pipeline is fast**. Actual performance depends on:

- Input size, CPU cache, and how data is stored.
- Cost of extracting properties from source objects.
- Lambdas/JIT and the ability to eliminate temporary objects.
- Stateful operators like `sorted` or `distinct` and the requirement to preserve encounter order.
- Cost of splitting/merging work when using `parallel()`.
- Cost of terminal operations, collectors, and destination memory.

A very simple `IntStream.range(...).sum()` computation can be fast and low-allocation; however, one should not automatically infer it is always faster than a `for` loop. Streams are a useful abstraction; a direct primitive loop is sometimes best suited for extremely hot paths (*hot path*).

For parallel reduction, the operator must be suitable for merging branches; avoid mutating a shared accumulator in `forEach`. Instead of:

~~~java
// Do not do this with a parallel stream:
// int[] sum = {0};
// numbers.parallelStream().forEach(n -> sum[0] += n);
~~~

use a reduction:

~~~java
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

This is an illustrative snippet with `List<Integer> numbers`, usable when the sum range requires `long`. Sharing an unsynchronized single-element array causes a data race and can lose updates. Conversely, primitive `sum()` has a reduction contract suitable for parallel implementations.

To confirm performance gains, measure with **JMH** or a benchmark that includes warm-up and representative data, observing GC allocation rate, throughput, and latency. Do not just run `System.nanoTime()` once, as JIT optimizations, dead-code elimination, and system noise easily lead to false conclusions. Do not optimize boxing in a way that makes code hard to understand if measurements do not show significant benefit.

## 11. Common mistakes

**Using `Stream<Integer>` throughout just to compute a sum.** When possible, extract with `mapToInt` and use `sum`, `average`, or `summaryStatistics`.

**Calling `boxed()` too early.** If storing a `List<Integer>` is needed, boxing at the boundary is reasonable. If immediately afterwards you call `mapToInt(Integer::intValue)` to sum, check whether you can keep `IntStream` up to the numeric terminal.

**Assuming a primitive stream removes wrappers from a `List<Integer>` source.** Incorrect: wrappers already exist in the list; only the steps after conversion are specialized.

**Confusing `sum()` with methods returning `long`.** `IntStream.sum()` returns `int`, `LongStream.sum()` returns `long`. `IntSummaryStatistics.getSum()` is `long`; widen numbers before summing if needed.

**Using `double` for money just for speed.** Floating-point errors may be unacceptable for business logic. Choose types based on precision requirements, not solely on boxing.

**Ignoring nulls in `List<Integer>`.** Unboxing null throws `NullPointerException`. Explicitly decide whether to skip, report an error, or use a fallback value.

**Creating a custom mutable accumulator in a parallel stream.** Prone to data races or incorrect results. Use a terminal reduction with the proper contract.

**Expecting every wrapper to allocate at runtime.** The JIT can eliminate allocations in some situations; measure in practice rather than deducing fixed allocation bytes from source code.

**Reusing a primitive stream after a terminal operation.** `IntStream` is single-use just like `Stream<T>`. If multiple metrics need to be computed, use `summaryStatistics()` or create a new stream from an appropriate source.

## 12. Checklist for choosing types and operations

| Need | Preferred Approach |
| --- | --- |
| Sum of `int` quantities | `source.stream().mapToInt(Entity::quantity).sum()` |
| Sum of `long` values | `source.stream().mapToLong(Entity::amount).sum()` |
| Average of scores | `source.stream().mapToDouble(Entity::score).average()` |
| Min/max of integers | `source.stream().mapToInt(Entity::quantity).max()` |
| Multiple `int` statistics | `...mapToInt(...).summaryStatistics()` |
| Sum that may exceed `int` | `...mapToLong(...).sum()` or `IntStream.asLongStream().sum()` |
| From `int[]` | `Arrays.stream(intArray)` |
| Need `int[]` result | `IntStream...toArray()` |
| Need `List<Integer>` | `IntStream...boxed().toList()` |
| Need `List<String>` from numbers | `IntStream...mapToObj(...).toList()` |
| Flatten number groups from `Stream<List<Integer>>` | `flatMapToInt(group -> group.stream().mapToInt(Integer::intValue))` |
| Exact monetary decimals | `BigDecimal` or integers in the smallest unit, per business contract |

**Rule of thumb:** Choose **a primitive stream early when the pipeline mainly performs numeric operations**, keep primitive types throughout `filter`/`map`/`reduce`/`sum`, and only convert to wrappers or objects **when the destination actually requires them**. The goal is to reduce unnecessary boxing while preserving value ranges, null policies, precision, and business semantics.