# Reducing Boxing and Unboxing with Primitive Streams

> **Chapter:** Performance and Memory  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, `collect`; practice grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while recognizing limits regarding state, resources, and performance.

The Java Stream API makes pipeline data processing straightforward, but not every pipeline carries the same cost. When computing millions of numeric values, repeatedly converting `int` to `Integer`, `long` to `Long`, and then back to primitive types can create extra objects, increase memory pressure, and make the program do more work than necessary.

Java provides three Stream types dedicated to primitive numbers — `IntStream`, `LongStream`, `DoubleStream` — to explicitly represent **numeric data** and support operations like `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()` without representing every value via a wrapper inside `Stream<T>`.

This lesson explains how to identify boxing/unboxing, choose the right Stream type, handle conversions at the object–primitive boundary, and evaluate memory benefits in a verifiable way. Standalone examples use **Java 17+**.

## 1. Where do boxing and unboxing actually happen?

In Java:

- **Boxing:** converting a primitive value into its corresponding wrapper object, such as `int → Integer`, `long → Long`, `double → Double`.
- **Unboxing:** extracting the primitive value from a wrapper, such as `Integer → int`.
- **Autoboxing/unboxing:** the compiler inserts conversion operations when the context requires it, typically via methods like `Integer.valueOf(...)` and `Integer.intValue()`.

Example:

```java
int primitive = 42;
Integer boxed = primitive;    // autoboxing
int again = boxed;            // unboxing

Integer explicit = Integer.valueOf(42);
int explicitValue = explicit.intValue();
```

Both forms express the same type conversion, though the JVM may optimize or reuse certain wrapper objects. **Do not assume every autoboxing operation definitely allocates a new object**: wrapper caches, JIT, escape analysis, and other optimizations can reduce actual allocations.

The problem arises when an arithmetic computation unnecessarily passes through object types:

```java
import java.util.List;

List<Integer> values = List.of(2, 3, 5);

Integer boxedTotal = values.stream()       // Stream<Integer>
        .map(n -> n * n)                    // unbox to multiply, may box result
        .reduce(0, Integer::sum);           // combine on Integers

System.out.println(boxedTotal);            // 38
```

Here `Stream<Integer>` carries values as **wrapper types**. The lambda `n -> n * n` must perform multiplication on `int`, and `map` returns `Stream<Integer>` again. With `reduce(0, Integer::sum)`, the inputs and result of `BinaryOperator<Integer>` also sit at the object boundary.

We can express the same calculation using a primitive numeric pipeline:

```java
int primitiveTotal = values.stream()
        .mapToInt(Integer::intValue)  // Stream<Integer> -> IntStream
        .map(n -> n * n)              // int -> int
        .sum();                       // terminal operation -> int

System.out.println(primitiveTotal); // 38
```

**Key difference to remember:** `List<Integer>` already holds wrappers, so reading the elements still involves unboxing. The benefit is that **the arithmetic stages after `mapToInt`** can continue working with `int` without creating a `Stream<Integer>` at each step.

## 2. The three primitive streams and their operations

| Stream Type | Element | Example Source | Typical Aggregation |
| --- | --- | --- | --- |
| `IntStream` | `int` | `IntStream.range(0, 10)`, `Arrays.stream(int[])` | `sum()` returns `int`, `average()` returns `OptionalDouble`. |
| `LongStream` | `long` | `LongStream.of(...)`, `Stream<T>.mapToLong(...)` | `sum()` returns `long`; suitable for sums larger than `int`. |
| `DoubleStream` | `double` | `DoubleStream.of(...)`, `Stream<T>.mapToDouble(...)` | `sum()`, `average()`, `summaryStatistics()` on `double`. |
| `Stream<Integer>` | `Integer` | `List<Integer>.stream()`, `IntStream.boxed()` | `reduce(...)` or collector; numbers pass through wrappers. |
| `Stream<Long>` | `Long` | `List<Long>.stream()`, `LongStream.boxed()` | `reduce(...)` or collector; numbers pass through wrappers. |

A regular `Stream<T>` **does not have** a `sum()` terminal operation. Primitive streams provide dedicated arithmetic operations and directly return primitive numeric types when appropriate.

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

int intSum = IntStream.of(2, 3, 5).sum();
long longSum = LongStream.of(2L, 3L, 5L).sum();
double doubleSum = DoubleStream.of(2.0, 3.0, 5.0).sum();

System.out.println(intSum);    // 10
System.out.println(longSum);   // 10
System.out.println(doubleSum); // 10.0
```

### `map` and `mapToInt` are not the same

For a `Stream<Order>` or `Stream<Product>`, you choose the method according to the **output type**:

```java
Stream<Product> products = ...;

// Object -> object:
Stream<String> names = products.map(Product::name);

// Object -> primitive int:
IntStream quantities = products.mapToInt(Product::quantity);

// Object -> primitive long:
LongStream cents = products.mapToLong(Product::priceCents);
```

This is a signature illustration, not a standalone runnable snippet: `Product` must be an application-defined type, and each `products` variable may only be used for one terminal operation in a pipeline. In the complete program in section 5, we create a **new Stream from the list** for each calculation.

Primitive streams also have ways to convert numeric types:

```java
IntStream ints = IntStream.of(1, 2, 3);
LongStream longs = ints.asLongStream(); // int -> long, no wrapper needed
System.out.println(longs.sum());       // 6
```

`IntStream.asLongStream()`, `IntStream.asDoubleStream()`, `IntStream.mapToLong(...)`, and `LongStream.mapToDouble(...)` help keep computation in the primitive domain when numeric type conversion is needed.

## 3. Creating primitive sources properly

When initial data is already an `int[]` array, avoid creating an intermediate object layer just to open a Stream:

```java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.Stream;

int[] scores = {2, 5, 9};

IntStream fromArray = Arrays.stream(scores);
IntStream fromOf = IntStream.of(scores);

System.out.println(fromArray.sum()); // 16
System.out.println(fromOf.count());  // 3

// DIFFERENT: Stream.of(scores) has one element of type int[].
long arrayObjects = Stream.of(scores).count();
System.out.println(arrayObjects);   // 1
```

Because `Stream.of(scores)` treats **the entire `int[]` array as a single object**, the result is a `Stream<int[]>` with one element, not an `IntStream` with three numbers. This is a common pitfall when switching from object-based APIs to primitive arrays.

Two ways to generate integer ranges:

```java
IntStream.range(1, 5)       // 1, 2, 3, 4: upper bound excluded
IntStream.rangeClosed(1, 5) // 1, 2, 3, 4, 5: upper bound included
```

If data is generated algorithmically and does not need to pre-exist as a `List<Integer>`, starting from `IntStream.range(...)` can avoid the boxing step of building a number list.

### Be careful with `Stream.of(1, 2, 3)`

```java
long boxedCount = Stream.of(1, 2, 3).count();  // Stream<Integer>
long primitiveCount = IntStream.of(1, 2, 3).count();

System.out.println(boxedCount);     // 3
System.out.println(primitiveCount); // 3
```

Both sources have the same count, but **different pipeline types**. `Stream.of(1, 2, 3)` represents elements as `Integer`; `IntStream.of(1, 2, 3)` keeps `int` across subsequent operations.

## 4. Converting at boundaries: `mapToInt`, `mapToLong`, `boxed`, `mapToObj`

An effective way to reduce boxing is usually not “avoid objects at all costs”, but **only convert to objects when truly needed**.

| Source | Method | Result | When to use |
| --- | --- | --- | --- |
| `Stream<Integer>` | `mapToInt(Integer::intValue)` | `IntStream` | After reading a list of wrappers, numeric calculation is needed. |
| `Stream<Order>` | `mapToLong(Order::amountCents)` | `LongStream` | Each order maps to a primitive monetary amount. |
| `IntStream` | `asLongStream()` | `LongStream` | Sum may exceed the `int` range. |
| `IntStream` | `boxed()` | `Stream<Integer>` | External API or collector requires `Integer`. |
| `IntStream` | `mapToObj(n -> "ID-" + n)` | `Stream<String>` | Need to create objects/strings for display. |
| `LongStream` | `boxed()` | `Stream<Long>` | Need a list or Map with `Long` values. |
| `DoubleStream` | `boxed()` | `Stream<Double>` | Need to pass into an API expecting wrappers. |

Example from integer data to labels:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(id -> "ID-" + id)
        .toList();

System.out.println(labels); // [ID-1, ID-2, ID-3]
```

Here creating `String` **is a business requirement**, not useless boxing. If you also want to sum the IDs, compute the sum **before `mapToObj`**, or create a separate pipeline for numeric calculation.

```java
List<Integer> numbers = IntStream.rangeClosed(1, 3)
        .boxed()
        .toList();

System.out.println(numbers); // [1, 2, 3]
```

`boxed()` is necessary if the target API requires `List<Integer>`; the result of `Stream.toList()` is an unmodifiable list. However, after `boxed()`, subsequent steps return to the `Stream<Integer>` world.

## 5. Complete example: summing sale line amounts with `LongStream`

A store records sale lines with SKU, quantity, unit price in **cents** (the smallest monetary unit, using `long`), and paid status. Requirement: include only **paid lines with quantity 2 or greater**, then sum the line amounts of eligible lines.

| SKU | Quantity | Unit price (cents) | Paid? | Included? | Line amount |
| --- | ---: | ---: | --- | --- | ---: |
| PEN | 3 | 1,299 | Yes | Yes | 3,897 |
| NOTE | 2 | 2,500 | Yes | Yes | 5,000 |
| BAG | 1 | 9,900 | No | No | — |
| CLIP | 5 | 199 | Yes | Yes | 995 |
| PEN | 1 | 1,299 | Yes | No | — |

**Expected total:** `3_897 + 5_000 + 995 = 9_892L`.

Save as `PrimitiveStreamBoxingDemo.java`. The Java 17+ program below includes the wrapper-style pipeline, the `LongStream` pipeline, and self-tests, **without needing external libraries beyond the JDK**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamBoxingDemo {

    record SaleLine(
            String sku,
            int quantity,
            long unitPriceCents,
            boolean paid
    ) {
        SaleLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("Empty SKU");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("Invalid sale line");
            }
        }

        long amountCents() {
            return Math.multiplyExact((long) quantity, unitPriceCents);
        }
    }

    static List<SaleLine> sample() {
        return List.of(
                new SaleLine("PEN", 3, 1_299L, true),
                new SaleLine("NOTE", 2, 2_500L, true),
                new SaleLine("BAG", 1, 9_900L, false),
                new SaleLine("CLIP", 5, 199L, true),
                new SaleLine("PEN", 1, 1_299L, true)
        );
    }

    static boolean eligible(SaleLine line) {
        return line.paid() && line.quantity() >= 2;
    }

    // Object pipeline: map returns Stream<Long>.
    static long boxedTotal(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .map(SaleLine::amountCents)
                .reduce(0L, Long::sum);
    }

    // Primitive pipeline: mapToLong returns LongStream.
    static long primitiveTotal(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .mapToLong(SaleLine::amountCents)
                .sum();
    }

    // When business logic requires detecting long sum overflow.
    static long checkedTotal(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .mapToLong(SaleLine::amountCents)
                .reduce(0L, Math::addExact);
    }

    static List<String> eligibleSkus(List<SaleLine> lines) {
        return lines.stream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .map(SaleLine::sku) // String is needed here, so map is right.
                .toList();
    }

    static int doubledPositiveStock(int[] changes) {
        return Arrays.stream(changes)
                .filter(delta -> delta > 0)
                .map(delta -> Math.multiplyExact(delta, 2))
                .sum();
    }

    static void check(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    static void selfTest() {
        List<SaleLine> data = sample();

        check(boxedTotal(data) == 9_892L, "Boxed total");
        check(primitiveTotal(data) == 9_892L, "Primitive total");
        check(checkedTotal(data) == 9_892L, "Checked total");
        check(boxedTotal(data) == primitiveTotal(data),
                "Two pipelines produced different results");
        check(eligibleSkus(data).equals(
                List.of("PEN", "NOTE", "CLIP")), "Wrong SKU order");

        // No eligible lines: both pipelines sum to 0.
        check(boxedTotal(List.of()) == 0L, "Empty source");
        check(primitiveTotal(List.of(
                new SaleLine("X", 1, 100L, true),
                new SaleLine("Y", 5, 100L, false)
        )) == 0L, "All elements filtered out");

        // Two ways to create an IntStream from an int[] array.
        int[] values = {2, 5, 9};
        check(Arrays.stream(values).sum() == 16, "Array IntStream");
        check(IntStream.of(values).count() == 3, "IntStream.of array");
        check(Stream.of(values).count() == 1,
                "Stream.of(int[]) has only one int[] element");
        check(IntStream.of(values).boxed().toList()
                .equals(List.of(2, 5, 9)), "Boxed list");

        // Arithmetic operations on IntStream.
        check(doubledPositiveStock(new int[] {4, -2, 6, 3}) == 26,
                "Doubled positive stock");
        check(IntStream.rangeClosed(1, 5).sum() == 15,
                "rangeClosed");
        check(IntStream.range(1, 5).sum() == 10, "range");

        // Optional results for average/extrema.
        OptionalDouble average = IntStream.of(values).average();
        check(average.isPresent(), "Missing average");
        check(Math.abs(average.orElseThrow() - 16.0 / 3.0) < 1e-12,
                "Wrong average");
        check(IntStream.empty().average().isEmpty(),
                "Empty average must be OptionalDouble.empty");

        OptionalInt minimum = IntStream.of(values).min();
        check(minimum.orElse(-1) == 2, "Wrong min");
        check(IntStream.empty().min().isEmpty(),
                "Empty min must be OptionalInt.empty");

        IntSummaryStatistics stats =
                IntStream.of(values).summaryStatistics();
        check(stats.getCount() == 3, "Count in stats");
        check(stats.getSum() == 16, "Sum in stats");
        check(stats.getMin() == 2, "Min in stats");
        check(stats.getMax() == 9, "Max in stats");

        // Wrapper data may contain null: filter BEFORE unboxing.
        List<Integer> nullable = Arrays.asList(4, null, 6);
        int filtered = nullable.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        check(filtered == 10, "Data containing null");

        // If sum may exceed int, widen to long before summing.
        long safe = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .sum();
        check(safe == 2_147_483_648L, "Long sum");

        boolean overflowDetected = false;
        try {
            LongStream.of(Long.MAX_VALUE, 1L)
                    .reduce(0L, Math::addExact);
        } catch (ArithmeticException expected) {
            overflowDetected = true;
        }
        check(overflowDetected, "Must detect long overflow");

        // Pure pipeline: arithmetic result unchanged in parallel.
        long parallelTotal = data.parallelStream()
                .filter(PrimitiveStreamBoxingDemo::eligible)
                .mapToLong(SaleLine::amountCents)
                .sum();
        check(parallelTotal == 9_892L, "Wrong parallel total");

        // Reversing data keeps sum unchanged, but changes encounter order.
        List<SaleLine> reversed = new ArrayList<>(data);
        java.util.Collections.reverse(reversed);
        check(primitiveTotal(reversed) == 9_892L,
                "Sum changed when reversing source");
        check(eligibleSkus(reversed).equals(
                List.of("CLIP", "NOTE", "PEN")),
                "SKU order after reversing source");
    }

    public static void main(String[] args) {
        List<SaleLine> data = sample();
        System.out.println("Boxed total: " + boxedTotal(data));
        System.out.println("Primitive total: " + primitiveTotal(data));
        System.out.println("Checked total: " + checkedTotal(data));
        System.out.println("Eligible SKUs: " + eligibleSkus(data));
        System.out.println("Positive restock x2: "
                + doubledPositiveStock(new int[] {4, -2, 6, 3}));
        System.out.println("Int array sum: "
                + Arrays.stream(new int[] {2, 5, 9}).sum());

        // Self-test without requiring the -ea flag.
        selfTest();
        System.out.println("ALL PRIMITIVE STREAM TESTS PASS");
    }
}
```

Compile and run when practicing:

```text
javac PrimitiveStreamBoxingDemo.java
java PrimitiveStreamBoxingDemo
```

Expected output:

```text
Boxed total: 9892
Primitive total: 9892
Checked total: 9892
Eligible SKUs: [PEN, NOTE, CLIP]
Positive restock x2: 26
Int array sum: 16
ALL PRIMITIVE STREAM TESTS PASS
```

The two methods `boxedTotal` and `primitiveTotal` use **the same dataset, the same filter condition, the same multiplication, and the same addition**. The goal is to demonstrate value equivalence, not to make a quantitative claim about which method is faster. To confirm performance gains, benchmark in a realistic environment.

## 6. Places where boxing can return inside a pipeline

Even when starting with a primitive stream, a program can switch back to wrappers if an operation requiring objects is applied:

```java
import java.util.Map;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<String, List<Integer>> grouped = IntStream.of(2, 3, 4, 5)
        .boxed()
        .collect(Collectors.groupingBy(
                n -> n % 2 == 0 ? "EVEN" : "ODD"));

System.out.println(grouped.get("EVEN")); // [2, 4]
```

`Collectors.groupingBy` accepts `Stream<T>`, not `IntStream` directly as a `Stream<Integer>`; calling `boxed()` is a **necessary boundary** if you want to use that collector. Map keys and lists are also objects, so you cannot promise “zero boxing” across the entire problem.

### Do not box and immediately unbox again

The following often creates an unnecessary round-trip conversion:

```java
int total = IntStream.rangeClosed(1, 1_000)
        .boxed()
        .mapToInt(Integer::intValue)
        .sum();
```

In this example, you can write:

```java
int total = IntStream.rangeClosed(1, 1_000).sum();
```

Look at **the type of each stage**, not just the syntax. Some generic helper functions accepting `Stream<Integer>` can force a pipeline to box earlier than needed; consider providing an overload taking `IntStream` or a primitive computation function when it is a hot path and the API allows it.

### Boxing does not happen only at `boxed()`

Operations that produce objects, such as `mapToObj(n -> new Event(n))`, still create `Event` objects when business logic requires them. That is different from pointlessly boxing `int` into `Integer`. Avoid optimizing by “creating zero objects” when the output genuinely must be a record, string, or Map.

Some stateful operations like `distinct()` and `sorted()` may need intermediate storage; internal optimization details depend on the JDK. **Primitive streams do not guarantee zero allocation across the whole pipeline**.

## 7. Memory: primitive arrays, wrappers, and materializing results

Compare three data forms:

```java
int[] primitiveArray = {1, 2, 3};
List<Integer> boxedList = List.of(1, 2, 3);
int[] processed = IntStream.of(1, 2, 3)
        .map(n -> n * 2)
        .toArray();
```

Regarding storage models:

- `int[]` stores `int` values directly inside the array.
- `List<Integer>` stores **references to `Integer` wrappers**. Wrapper objects may be reused/cached, so you cannot deduce from element count that exactly that many objects were newly allocated.
- `IntStream.toArray()` returns `int[]`, whereas `IntStream.boxed().toList()` returns `List<Integer>`. The two results can use different amounts of memory because their data shapes differ.

For an arithmetic pipeline that does not need to keep all outputs, `sum()`, `count()`, or `summaryStatistics()` can avoid building a full result list. Still, a `sorted()` or stateful operation may need intermediate storage even when using a primitive stream.

Do not make fixed claims like “each `Integer` costs X bytes” across all JVMs: object size depends on compressed references, alignment, runtime/version, and optimizations. When memory is a real concern, measure **allocation rate, GC, and heap usage** with appropriate tools rather than inferring solely from type signatures.

## 8. Avoiding numeric overflow and understanding `sum()`

Switching to `IntStream` does not widen `int` addition:

```java
int overflow = IntStream.of(Integer.MAX_VALUE, 1).sum();
System.out.println(overflow); // -2147483648, int overflow

long widened = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
System.out.println(widened); // 2147483648
```

If inputs are `int` quantities whose sum can grow large, `mapToLong` or `asLongStream` helps **widen the numeric range before summing**. If the sum exceeds even `long`, `LongStream.sum()` can still overflow; when error detection is required, use `reduce(0L, Math::addExact)` or a larger numeric type as appropriate.

### Watch out for multiplication before widening to `long`

```java
int quantity = 100_000;
int price = 100_000;

long wrong = quantity * price;        // Overflows in int before assignment.
long right = (long) quantity * price; // 10000000000.
```

`mapToLong(line -> line.quantity() * line.price())` **does not guarantee** overflow safety if both getters return `int`: the multiplication inside the lambda still runs as `int`. Cast **before multiplying**, or use `Math.multiplyExact` on the target type.

In the sample program, `amountCents()` uses `Math.multiplyExact((long) quantity, unitPriceCents)` to report an error if multiplication exceeds the `long` range.

## 9. `null`, empty results, and primitive `Optional` types

`IntStream`, `LongStream`, and `DoubleStream` **cannot hold null elements**. However, a `Stream<Integer>` or `List<Integer>` source may contain `null`, and unboxing null throws `NullPointerException`.

```java
import java.util.Arrays;
import java.util.Objects;

List<Integer> numbers = Arrays.asList(4, null, 6);

int total = numbers.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 10
```

If null represents invalid input, **filtering out** nulls can hide bad data; in that case, validate beforehand or fail with a clear error message. Java’s `List.of(...)` rejects null elements, whereas some collections and external sources permit them.

Aggregation operations with optional results:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalDouble average = IntStream.of(2, 5, 9).average();
OptionalInt minimum = IntStream.of(2, 5, 9).min();

System.out.println(average.orElse(0.0)); // 5.333333333333333
System.out.println(minimum.orElse(-1));  // 2

System.out.println(IntStream.empty().average().isEmpty()); // true
System.out.println(IntStream.empty().min().isEmpty());     // true
```

With an empty source:

- `sum()` returns **0** of the corresponding numeric type.
- `count()` returns `0L`.
- `average()` returns `OptionalDouble.empty()`.
- `min()` and `max()` return an empty `OptionalInt`, `OptionalLong`, or `OptionalDouble` depending on the Stream type.

Do not assume `min()` of an empty Stream is `0`: `0` here can only be a fallback chosen by the **caller** via `orElse(...)`, and may collide with a meaningful business value.

## 10. `summaryStatistics()`: multiple metrics in one pass

When you need count, sum, min, max, and average on the same primitive source, you can use `summaryStatistics()`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.of(2, 5, 9)
        .summaryStatistics();

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 16
System.out.println(stats.getMin());     // 2
System.out.println(stats.getMax());     // 9
System.out.println(stats.getAverage()); // 5.333333333333333
```

The strength here is not only limiting boxing: **a single terminal operation** can compute all metrics, instead of opening multiple Streams from a hard-to-traverse source or materializing intermediate data.

`IntSummaryStatistics` is a **single statistics object**, which does not mean each number had to be boxed into `Integer`. This illustrates using an object at the result boundary while processing the data itself as primitives.

### Limits to know

`IntSummaryStatistics` stores the sum as `long`; if the data range and element count are large enough, even `long` has a limit. With `DoubleSummaryStatistics`, `double` results follow floating-point rounding rules. For money, do not convert `BigDecimal` to `double` just to use `DoubleStream`.

## 11. `DoubleStream` is not the default choice for money

`DoubleStream` is suitable for measurements, statistics, or floating-point problems that **tolerate floating-point rounding error**:

```java
import java.util.stream.DoubleStream;

double averageTemperature = DoubleStream.of(28.5, 29.0, 30.5)
        .average()
        .orElseThrow();
System.out.println(averageTemperature); // 29.333333333333332 (approximate)
```

`DoubleStream.sum()` may use compensated summation and yield different rounding error from naive sequential addition. Due to floating-point properties, **do not write tests relying on bit-for-bit equality** across all orders or parallel strategies without defining an arithmetic contract. Define acceptable tolerance, rounding rules, and `NaN`/`Infinity` handling according to the domain.

For money requiring exact decimal arithmetic:

```java
import java.math.BigDecimal;
import java.util.List;

BigDecimal totalMoney = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20")
).stream().reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(totalMoney); // 0.30
```

`BigDecimal` is an object, and `Stream<BigDecimal>` is the right choice when precision matters more than reducing boxing. **Business correctness comes before optimizing wrapper counts**.

## 12. Performance measurement: verify instead of guessing

Ask a concrete question: “With an `int[]` of millions of elements, does an `IntStream` pipeline reduce allocations and execution time compared to `Stream<Integer>`?” Measure under the same **work** and same **conditions**:

1. Both versions must apply the same filter, mapping, and summation rules.
2. Control the cost of **building input data**. Comparing reading an `int[]` against freshly building a `List<Integer>` mixes in list construction cost; if measuring only the pipeline, prepare inputs beforehand.
3. Separate measurements for **throughput, latency, allocation rate, and GC**; do not measure just a single run’s duration.
4. Give the JVM warmup and avoid dead-code elimination; for Java microbenchmarks, prefer **JMH** with explicit result consumption.
5. Test different data sizes and operations: tiny pipelines can be dominated by setup overhead; CPU-heavy pipelines may be less sensitive to wrapper cost than lightweight ones.
6. Record the JDK, JVM, heap, CPU, parallelism, and run flags; results can change when environments change.

| Observation | What it may suggest | What it cannot prove alone |
| --- | --- | --- |
| Primitive pipeline allocates less | Wrappers or intermediate structures previously caused overhead. | Every primitive pipeline will be faster. |
| Both versions have similar runtime | The JVM optimizes boxing well, or another cost dominates. | Boxing is completely free in all cases. |
| `parallel()` is faster once | The source may be large enough or the machine multi-core. | Stable speedup under production load. |
| `DoubleStream` is faster than `BigDecimal` | Precision requirements differ. | You can swap monetary types without business impact. |

**Do not build a benchmark using a one-off `System.nanoTime()` call and treat it as proof.** A single run can be skewed by JIT, GC, caches, system load, or dead-code elimination.

## 13. Common pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `Stream<Integer>` for arithmetic and repeatedly `map`/`reduce` wrappers | Can increase boxing/unboxing and processing cost. | Switch to `IntStream` via `mapToInt` when output remains numeric. |
| Assuming `Stream.of(intArray)` is a Stream of numbers | Actually has one element of type `int[]`. | Use `Arrays.stream(intArray)` or `IntStream.of(intArray)`. |
| Calling `boxed()` then immediately `mapToInt(Integer::intValue)` | Unnecessary type round-trip. | Keep the pipeline primitive until the required API boundary. |
| Trying to use `Collectors.groupingBy` directly on `IntStream` | Collectors target `Stream<T>`, not primitive streams directly. | Use `boxed()` where grouping is needed or design a specialized aggregator. |
| Unboxing a `null` element | `NullPointerException`. | Define a null policy; filter or validate before `mapToInt`. |
| Using `IntStream.sum()` for sums exceeding `int` | Can silently overflow. | Widen with `asLongStream()` before summing, or use a larger type. |
| Multiplying two `int`s before casting to `long` | Overflows inside the expression even when assigned to `long`. | Cast before multiplication or use `Math.multiplyExact`. |
| Using `DoubleStream` for money to avoid boxing | Floating-point error, potential business bugs. | Prefer `BigDecimal` or integer smallest currency units. |
| Calling `getAsInt()` on `OptionalInt.empty()` | Throws `NoSuchElementException`. | Use `isPresent`, `orElse`, or `orElseThrow` as required. |
| Assuming primitive streams never allocate | Stateful buffers/arrays and result objects may still allocate. | Measure allocations; separate element type from execution strategy. |
| Using `parallelStream()` just to “avoid boxing” | Does not solve boxing and may add split/merge overhead. | Choose primitive types first, then evaluate parallelism separately. |
| Benchmarking two versions doing different work | Performance conclusions are meaningless. | Build functionally equivalent test cases and normalize input data. |

## 14. Self-practice exercises

**Exercise 1 — Converting from `Stream<Integer>` to `IntStream`.** Given `List.of(2, 3, 5)`, square the numbers and compute the sum without returning `Stream<Integer>` after squaring.

```java
int sumSquares = List.of(2, 3, 5).stream()
        .mapToInt(Integer::intValue)
        .map(n -> n * n)
        .sum();
System.out.println(sumSquares); // 38
```

**Exercise 2 — Range bounds.** Predict `IntStream.range(1, 4).sum()` and `IntStream.rangeClosed(1, 4).sum()`.

**Answer:** `range(1, 4)` is `1 + 2 + 3 = 6`; `rangeClosed(1, 4)` is `1 + 2 + 3 + 4 = 10`.

**Exercise 3 — Primitive arrays.** Given `int[] data = {4, 6, 8}`, what do `Stream.of(data).count()` and `Arrays.stream(data).count()` return?

**Answer:** **1** and **3**, respectively. `Stream.of(data)` treats the whole array as one element; `Arrays.stream(data)` creates an `IntStream` traversing three numbers.

**Exercise 4 — Sum exceeding `int` range.** Compute `Integer.MAX_VALUE + 2` as a `long` without `int` overflow.

```java
long total = IntStream.of(Integer.MAX_VALUE, 2)
        .asLongStream()
        .sum();
System.out.println(total); // 2147483649
```

**Exercise 5 — Why `Integer` appears.** Why does `IntStream.range(1, 5).boxed().collect(Collectors.toList())` involve wrappers?

**Answer:** `boxed()` converts each `int` into an `Integer` to pass through `Stream<Integer>` and be stored in a `List<Integer>`. When an object list is genuinely required as output, that is a data-model cost rather than a programming bug.

**Exercise 6 — Empty average.** What does `IntStream.empty().average()` return? If business rules define no data as “no result”, what should you do?

**Answer:** It returns `OptionalDouble.empty()`. You can keep the `OptionalDouble` and display a message or handle an appropriate error; do not turn empty into `0.0` automatically if that could be mistaken for a zero average.

**Exercise 7 — Total revenue.** Rewrite `boxedTotal` in section 5 using `LongStream`, then replace `sum()` with overflow-detecting addition. Compare all three results on the sample data.

**Hint:** `mapToLong(SaleLine::amountCents).reduce(0L, Math::addExact)`. All three results on the sample data should be `9892`; if data exceeds numeric range, the checked version can throw `ArithmeticException`.

**Exercise 8 — Choosing the Stream type.** One pipeline takes temperature readings `double[]` and computes the average; another totals `BigDecimal` money with rounding rules. Which primitive stream do you choose?

**Answer:** Use `DoubleStream` for temperatures if floating-point approximation is acceptable; **do not choose `DoubleStream` for money** just to reduce boxing — keep `BigDecimal` and define rounding rules.

## 15. Key takeaways

- `Stream<Integer>`, `Stream<Long>`, and `Stream<Double>` carry wrapper types; `IntStream`, `LongStream`, and `DoubleStream` help numeric operations **avoid many unnecessary boxing/unboxing conversions**.
- When the source is a list of objects, use `mapToInt`/`mapToLong`/`mapToDouble` **at the boundary transitioning into numeric computation**; only call `boxed()` or `mapToObj()` when the output genuinely requires objects.
- For `int[]`, use `Arrays.stream(array)` or `IntStream.of(array)`, not `Stream.of(array)` which produces a single element holding the entire array.
- Primitive streams provide `sum`, `average`, `min`, `max`, and `summaryStatistics`, yet you still must handle **overflow, nulls in wrapper sources, and empty Optionals**.
- `int`/`long` do not replace `BigDecimal` in every monetary problem; `DoubleStream` has floating-point error. **Business correctness first, optimization second**.
- Primitive streams do not promise **zero allocation** or always being faster. Use value tests to verify equivalence, then benchmark and profile if performance truly matters.
