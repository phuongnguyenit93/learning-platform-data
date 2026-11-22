# mapToInt(), mapToLong(), and mapToDouble() in Java Streams

## Objectives

In the Java Stream API, the three methods **`mapToInt()`, `mapToLong()`, and `mapToDouble()`** are used to convert each element of a **`Stream<T>`** into a corresponding primitive numeric value. The result is no longer a `Stream<Integer>`, `Stream<Long>`, or `Stream<Double>`, but rather an **`IntStream`, `LongStream`, and `DoubleStream`**, respectively. These primitive streams provide aggregation operations such as `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()`, while avoiding boxing/unboxing of individual elements during appropriate primitive numeric processing stages.

After this lesson, you will be able to:

- Read the signatures, mapper inputs, and resulting Stream types of the three methods accurately.
- Distinguish `map()` returning `Stream<R>` from `mapToInt/Long/Double()` returning a primitive stream.
- Combine a mapper with a lambda or method reference; understand the target types `ToIntFunction`, `ToLongFunction`, and `ToDoubleFunction`.
- Compute sums, averages, extrema, statistics, and handle empty Streams via `OptionalInt`, `OptionalLong`, and `OptionalDouble`.
- Convert back to an object Stream using `boxed()` or `mapToObj()` when needed.
- Distinguish primitive types, numeric type conversions, overflow, `double` precision errors, and boxing overhead.
- Test Java 17 programs and avoid common pitfalls when transforming numeric data.

## 1. Why Do Primitive Streams Exist?

Suppose we have a list of strings and want to calculate the total length:

```java
List<String> words = List.of("Java", "Go", "API");
```

One approach using `map`:

```java
int sum = words.stream()
        .map(String::length)
        .mapToInt(Integer::intValue)
        .sum();
```

`String.length()` returns a primitive `int`, but `Stream.map` creates a `Stream<Integer>`, causing the numbers to be boxed into `Integer` before being converted back to `int`. A usually more concise and targeted approach:

```java
int sum = words.stream()
        .mapToInt(String::length)
        .sum(); // 9
```

`Stream<String>` is transformed into an `IntStream` right after `mapToInt`. Then `sum()` returns a primitive `int`. There is no need to create an `Integer` for each mapper result just to add the numbers.

The three primitive stream types are:

| Type | Element | Example Results |
| --- | --- | --- |
| `IntStream` | `int` | String length, counts, indices |
| `LongStream` | `long` | Numeric timestamps, large counts, monetary values converted to minor units |
| `DoubleStream` | `double` | Weights, ratios, real measurements |

**Note:** these types are meant for **processing primitive numeric values**; they do not automatically replace domain models. Monetary values with rounding rules usually require `BigDecimal` or integer minor units; using `double` can introduce representation errors.

Small snippets in this document may require importing `java.util.List`, `java.util.stream.*`, and the corresponding data model classes; the complete program in a later section includes all imports.

## 2. Signatures of the Three Methods and Lambda Target Types

On `Stream<T>`, the equivalent APIs are:

```java
IntStream mapToInt(ToIntFunction<? super T> mapper);
LongStream mapToLong(ToLongFunction<? super T> mapper);
DoubleStream mapToDouble(ToDoubleFunction<? super T> mapper);
```

These are **simplified API declarations** for learning, not code to add to your application. The mapper must not be `null`. The three functional interfaces belong to `java.util.function` and have the following function descriptors:

| Mapper | Functional Method | Descriptor | Result |
| --- | --- | --- | --- |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | `(T) -> int` | `IntStream` |
| `ToLongFunction<T>` | `long applyAsLong(T value)` | `(T) -> long` | `LongStream` |
| `ToDoubleFunction<T>` | `double applyAsDouble(T value)` | `(T) -> double` | `DoubleStream` |

If the source is `Stream<Order>`, `mapToInt(Order::units)` requires a function that takes an `Order` and returns an `int`. The method reference `Order::units` is valid when the `Order` record has an `int units()` accessor.

Example of reading a mapper:

```java
IntStream lengths = Stream.of("Java", "Go")
        .mapToInt(text -> text.length());
```

The compiler knows `text` has type `String` from `Stream<String>` and the target `ToIntFunction<? super String>`. The result is an `IntStream`, not a `List<Integer>` or `Stream<Integer>`.

You can write the type explicitly:

```java
IntStream lengths = Stream.of("Java", "Go")
        .mapToInt((String text) -> text.length());
```

or use a method reference:

```java
IntStream lengths = Stream.of("Java", "Go")
        .mapToInt(String::length);
```

These three snippets are **three independent options** (do not declare the same `lengths` variable in the same scope). If the lambda's return value matches the descriptor, choose the shortest, clearest form.

## 3. mapToInt(): Converting Objects to int

`mapToInt` is well-suited when an object already has an `int` property:

```java
record Product(String name, int quantity) {}

List<Product> products = List.of(
        new Product("Book", 2),
        new Product("Pen", 5)
);

int totalQuantity = products.stream()
        .mapToInt(Product::quantity)
        .sum(); // 7
```

In this illustration, the accessor `Product::quantity` returns a primitive `int`. After `mapToInt`, you can continue using methods specialized for `IntStream`:

```java
IntStream counts = products.stream()
        .mapToInt(Product::quantity);

int total = counts.sum();
```

Do not call `counts.average()` on the same variable after `sum()` because a **Stream is single-use**. You need to create a new Stream or use `summaryStatistics()` to obtain multiple metrics in a single terminal operation.

### 3.1. When a String Source Needs to Be Parsed into Numbers

```java
List<String> raw = List.of("10", "20", "30");

int total = raw.stream()
        .mapToInt(Integer::parseInt)
        .sum(); // 60
```

`Integer.parseInt` returns an `int`. If there is an element `"abc"`, running the mapper will throw `NumberFormatException`; `mapToInt` **does not automatically skip invalid strings**.

For user-supplied data, you should define a clear policy: reject the entire input, record errors, or parse each element into a result representing success/failure. Do not silently catch all errors and return `0` if `0` could have a valid business meaning.

### 3.2. Sum, Average, and Maximum Value

```java
int sum = products.stream().mapToInt(Product::quantity).sum();

OptionalDouble average = products.stream()
        .mapToInt(Product::quantity)
        .average();

OptionalInt max = products.stream()
        .mapToInt(Product::quantity)
        .max();
```

`average()` returns **`OptionalDouble`**, not `double` directly, because the source might be empty; `max()` returns **`OptionalInt`**. With the source `[2, 5]`, the average is `3.5` and the maximum is `5`. If the source is empty, the corresponding Optionals are empty.

`sum()` returns `0` when the IntStream is empty. You need to distinguish between "no data" and "data exists with a sum of 0" if the business requirement needs to know the element count.

## 4. mapToLong(): Converting Objects to long

`mapToLong` is commonly used for a `long` field or calculations that may exceed the `int` range:

```java
record Item(long priceCents, int units) {}

List<Item> items = List.of(
        new Item(1_250, 2),
        new Item(2_500, 3)
);

long revenue = items.stream()
        .mapToLong(item -> item.priceCents() * item.units())
        .sum(); // 10000
```

In the multiplication above, `item.priceCents()` is `long` and `units()` is `int`; Java widens `int` to `long` to perform `long` multiplication. The correct result for the sample data is `1_250*2 + 2_500*3 = 10_000`.

If both initial operands are `int`, **you must cast to long before multiplying** if the result can be large:

```java
int price = 1_500_000_000;
int quantity = 3;

// Incorrect intent for large numbers: int multiplication overflows before assigning to long.
long wrong = price * quantity;

// Correct for the int range, result is long.
long correct = (long) price * quantity; // 4500000000
```

Even though `mapToLong` expects the mapper to return a `long`, if the body already performed an `int * int` multiplication that overflowed, converting the overflowed result to `long` afterward will not recover the true value. You must widen the type **before** the multiplication.

`LongStream.sum()` can also overflow if the sum exceeds the `long` range; Java does not automatically throw an exception with regular `+`. When overflow detection is required, you can use checked operations like `Math.addExact`/`Math.multiplyExact` in an appropriate aggregation design, or use `BigInteger` if a larger range is needed.

### 4.1. Counting vs. Summing

`IntStream.sum()` returns `int`, whereas `LongStream.sum()` returns `long`. `Stream.count()` returns `long` because it counts the number of elements (not the sum of values). Do not confuse them:

```java
long numberOfItems = items.stream().count(); // 2

long totalCents = items.stream()
        .mapToLong(Item::priceCents)
        .sum(); // 3750
```

`count()` does not need `mapToLong` because it counts elements, whereas `sum()` adds the mapped numeric values.

## 5. mapToDouble(): Converting Objects to double

`mapToDouble` is used for measurements, ratios, or calculations returning `double`:

```java
record Measure(String id, double weightKg) {}

List<Measure> measures = List.of(
        new Measure("A", 1.25),
        new Measure("B", 2.00)
);

double totalWeight = measures.stream()
        .mapToDouble(Measure::weightKg)
        .sum(); // 3.25
```

`DoubleStream` has `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()`. The average of an empty Stream is `OptionalDouble.empty()`:

```java
OptionalDouble average = measures.stream()
        .mapToDouble(Measure::weightKg)
        .average();

double value = average.orElse(0.0);
```

Only use `orElse(0.0)` if the business logic genuinely wants to treat missing data as `0.0`. For reports or statistical metrics, missing data may need to be distinguished from a measurement of zero.

### 5.1. Floating-Point Precision

`double` represents binary values according to the floating-point standard; many common decimal numbers cannot be represented with absolute precision. For example, adding `0.1 + 0.2` does not have the same bit representation as `0.3` in many direct comparisons.

`DoubleStream.sum()` may use techniques to reduce summation error, but it **does not guarantee mathematically exact results**, especially with very large/small values, `NaN`, infinity, or different evaluation orders in parallel pipelines. You should not use `==` to check approximate aggregated results when an acceptable tolerance is required.

For currency, consider:

- Integer minor units like `long cents` when the currency unit and calculation range are suitable.
- `BigDecimal` when exact decimal numbers, rounding, and explicit financial rules are required.
- `double` for measurements, scientific calculations, or statistics with acceptable error tolerances.

Do not choose `mapToDouble` just because revenue contains a decimal point in the UI. **The numeric type is a correctness decision**, not just a performance one.

## 6. map() vs. mapToInt(), mapToLong(), and mapToDouble()

| Mapping Method | Mapper | Resulting Stream | Terminal Example |
| --- | --- | --- | --- |
| `map(f)` | `Function<T,R>` | `Stream<R>` | `toList()`, `collect()` |
| `mapToInt(f)` | `ToIntFunction<T>` | `IntStream` | `sum()` returns `int` |
| `mapToLong(f)` | `ToLongFunction<T>` | `LongStream` | `sum()` returns `long` |
| `mapToDouble(f)` | `ToDoubleFunction<T>` | `DoubleStream` | `average()` returns `OptionalDouble` |

Mapping with `map` is appropriate when you need to keep the results as objects, records, or types like `BigDecimal`:

```java
List<String> uppercase = words.stream()
        .map(String::toUpperCase)
        .toList();
```

Whereas for numbers to aggregate:

```java
int characters = words.stream()
        .mapToInt(String::length)
        .sum();
```

If you use `map(String::length)`, the result is a `Stream<Integer>` and lacks a direct `sum()` like `IntStream`. You could add `reduce(0, Integer::sum)` or convert to a primitive stream, but choosing `mapToInt` is usually clearer for summing `int` values.

### 6.1. Boxing Overhead and Limits of Performance Reasoning

A `Stream<Integer>` works with `Integer` wrappers; `IntStream` works with primitive `int`. Primitive streams can reduce boxing/unboxing in numeric computation stages, but **they do not automatically guarantee every program will be faster**. Performance depends on mapper cost, data size, JVM/JIT, source structure, caching, and terminal operations.

If the mapper mainly calls a database or HTTP endpoint, I/O cost will dominate, and boxing micro-optimizations may be negligible. Measure with an appropriate benchmark if performance optimization is a critical requirement.

## 7. Complete Java 17 Example: From Order Data to Three Primitive Streams

Create the file **`PrimitiveMappingDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.OptionalDouble;
import java.util.stream.IntStream;

public class PrimitiveMappingDemo {
    record Order(String code, int units, long unitPriceCents, double weightKg) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("A", 2, 1_250, 1.25),
            new Order("B", 3, 2_500, 2.00),
            new Order("C", 1, 750, 0.75)
        );

        int units = orders.stream().mapToInt(Order::units).sum();
        long priceSum = orders.stream()
                .mapToLong(Order::unitPriceCents).sum();
        long revenue = orders.stream()
                .mapToLong(o -> o.unitPriceCents() * o.units()).sum();
        double weight = orders.stream()
                .mapToDouble(Order::weightKg).sum();
        OptionalDouble averageWeight = orders.stream()
                .mapToDouble(Order::weightKg).average();

        IntSummaryStatistics statistics = orders.stream()
                .mapToInt(Order::units).summaryStatistics();
        List<Integer> lengths = List.of("Java", "Go", "")
                .stream().mapToInt(String::length).boxed().toList();

        long billions = IntStream.rangeClosed(1, 3)
                .mapToLong(n -> n * 1_000_000_000L).sum();
        double halves = IntStream.rangeClosed(1, 3)
                .mapToDouble(n -> n / 2.0).sum();

        System.out.println("Units: " + units);
        System.out.println("Price sum cents: " + priceSum);
        System.out.println("Revenue cents: " + revenue);
        System.out.printf(Locale.ROOT, "Weight total kg: %.2f%n", weight);
        System.out.printf(Locale.ROOT, "Weight average kg: %.2f%n",
                averageWeight.orElse(0));
        System.out.println("Units stats: count=" + statistics.getCount()
                + ", min=" + statistics.getMin()
                + ", max=" + statistics.getMax()
                + ", sum=" + statistics.getSum());
        System.out.println("Lengths boxed: " + lengths);
        System.out.println("Billions: " + billions);
        System.out.printf(Locale.ROOT, "Halves: %.1f%n", halves);
        System.out.println("Empty average: "
                + java.util.stream.DoubleStream.empty().average().isEmpty());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac PrimitiveMappingDemo.java
java PrimitiveMappingDemo
```

**Exact stdout:**

```text
Units: 6
Price sum cents: 4500
Revenue cents: 10750
Weight total kg: 4.00
Weight average kg: 1.33
Units stats: count=3, min=1, max=3, sum=6
Lengths boxed: [4, 2, 0]
Billions: 6000000000
Halves: 3.0
Empty average: true
```

### 7.1. Explanation of Each Result

1. The orders have `units` equal to `2, 3, 1`, so `mapToInt(Order::units).sum()` returns `6`.
2. The sum of unit prices from the `unitPriceCents` field is `1250 + 2500 + 750 = 4500`, stored as a `long`. This is **not revenue**, because each order has a different quantity.
3. Actual revenue in cents is `1250*2 + 2500*3 + 750*1 = 10750`; the lambda `mapToLong(o -> o.unitPriceCents() * o.units())` produces one `long` value per line item.
4. The sample weights sum to `1.25 + 2.00 + 0.75 = 4.00` and the average is `4.00 / 3 ≈ 1.33` formatted to two decimal places using `Locale.ROOT`.
5. `IntSummaryStatistics` collects in a single pass: `count=3`, `min=1`, `max=3`, `sum=6`. This avoids trying to run multiple terminal operations on the same already-consumed Stream.
6. `mapToInt(String::length)` produces the primitive numbers `4, 2, 0`; `boxed()` converts to `Stream<Integer>`, and `toList()` collects them into `[4, 2, 0]`.
7. `IntStream.rangeClosed(1,3)` generates `1,2,3`. `mapToLong(n -> n * 1_000_000_000L)` performs `long` multiplication, so the sum is `6_000_000_000`, which exceeds the `int` range but is valid in `long`.
8. `mapToDouble(n -> n / 2.0)` yields `0.5,1.0,1.5`, so the sum is `3.0`.
9. `DoubleStream.empty().average()` returns `OptionalDouble.empty()`, so `isEmpty()` is `true`.

The code uses `record` (available in Java 17), `Stream.toList()`, and standard primitive streams. There is no random data or network access; the results can be verified independently.

## 8. summaryStatistics(): Getting Multiple Metrics in One Pass

If you need `count`, `min`, `max`, `sum`, and `average` of the same numeric Stream, use `summaryStatistics()`:

```java
IntSummaryStatistics stats = products.stream()
        .mapToInt(Product::quantity)
        .summaryStatistics();

System.out.println(stats.getCount());
System.out.println(stats.getMin());
System.out.println(stats.getMax());
System.out.println(stats.getSum());
System.out.println(stats.getAverage());
```

The snippet above illustrates this with `products` and `Product` defined in context. Besides `IntSummaryStatistics`, there are also `LongSummaryStatistics` and `DoubleSummaryStatistics`.

Benefits:

- You can obtain multiple metrics in **one terminal operation** instead of recreating the Stream for each statistic.
- The getters have clear return types: `getCount()` returns `long`, `getAverage()` returns `double`; `getSum()` returns the sum type appropriate for the statistics class.
- It does not conflate the input data's numeric type with the types of all statistical metrics.

**Empty Stream note:** `summaryStatistics()` still returns a statistics object; `getCount()` is `0`. The `getMin/getMax` getters have special initial values depending on the statistics type, so when reporting extrema, check `getCount() > 0`. With `average()` called directly on a primitive stream, the empty state is explicitly reflected by `OptionalDouble.empty()`.

## 9. Distinguishing mapTo* on Stream<T> from Conversions Between Primitive Streams

The three methods we are studying belong to `Stream<T>` and take a mapper from an object `T` to a primitive number. However, when you **already have a primitive stream**, there are other type conversions available as well.

### 9.1. From IntStream to LongStream or DoubleStream

```java
long sum = IntStream.of(1, 2, 3)
        .mapToLong(n -> n * 1_000_000_000L)
        .sum(); // 6000000000
```

`IntStream.mapToLong` takes an `IntToLongFunction` with descriptor `(int) -> long`, **not `ToLongFunction<T>`** as on `Stream<T>`. They share the name `mapToLong`, but the target mapper and input source differ.

```java
double total = IntStream.of(1, 2, 3)
        .mapToDouble(n -> n / 2.0)
        .sum(); // 3.0
```

`IntStream.mapToDouble` takes an `IntToDoubleFunction`. If you write `n / 2` instead of `n / 2.0`, the math is performed as **integer division** before converting to `double`; the result will be different. Pay attention to the operand types in the body, not just the final return type.

### 9.2. Other Conversion Paths

- `IntStream.asLongStream()` converts `int` elements to `long` via widening.
- `IntStream.asDoubleStream()` converts `int` elements to `double`.
- `LongStream.asDoubleStream()` converts `long` elements to `double`; very large `long` values may lose precision when represented as `double`.
- `IntStream.boxed()`, `LongStream.boxed()`, and `DoubleStream.boxed()` turn primitive elements into wrappers to produce `Stream<Integer/Long/Double>`.

Example:

```java
List<Long> longs = IntStream.rangeClosed(1, 3)
        .asLongStream()
        .boxed()
        .toList(); // [1, 2, 3]
```

When you only need to **widen the numeric type while keeping the same values**, `asLongStream` usually expresses intent more clearly than writing `mapToLong(n -> n)`. When you need to **transform using a formula**, use the corresponding mapper.

## 10. boxed() and mapToObj(): Returning to Object Results

A primitive stream does not have all the methods of `Stream<T>` in the same form; when you need to collect into an object collection or construct a record from a numeric value, you can convert back to an object stream.

### 10.1. boxed()

```java
List<Integer> lengths = Stream.of("A", "Java")
        .mapToInt(String::length)
        .boxed()
        .toList(); // [1, 4]
```

`boxed()` turns each `int` into an `Integer`. Then `toList()` creates a `List<Integer>`. This is the right choice when the required output is genuinely a list of wrappers; however, if you only need to compute `sum`, stay on the primitive stream.

### 10.2. mapToObj()

```java
List<String> labels = IntStream.of(1, 2, 3)
        .mapToObj(n -> "No." + n)
        .toList(); // [No.1, No.2, No.3]
```

`mapToObj` takes a mapper from a primitive to an object and returns `Stream<R>`. It does not merely box: you decide which object is created. Distinguish `IntStream.mapToObj` from `Stream<T>.map`; both produce an object Stream, but their input sources have different types.

### When Do You Need to Return to an Object Stream?

Use `boxed()` when you need wrappers to interact with generic APIs or collect into a list. Use `mapToObj()` when you want to create another object from a number (a string, record, or domain object). Do not bounce back and forth between primitive → wrapper → primitive multiple times without reason, as it lengthens the pipeline and can incur unnecessary overhead.

## 11. Lazy Evaluation and Stream Usage Constraints

`mapToInt`, `mapToLong`, and `mapToDouble` are **intermediate operations**. The mapper body usually executes only when a terminal operation requests elements.

```java
IntStream pipeline = Stream.of("A", "BB")
        .mapToInt(s -> {
            System.out.println("mapping " + s);
            return s.length();
        });

// Does not print "mapping A" or "mapping BB" when the pipeline is created.
int sum = pipeline.sum();
```

When `sum` runs in this sequential pipeline, the mapper processes the two elements to produce the sum. However, do not rely on side effects inside `mapToInt` as a once-per-element business mechanism for all pipelines: short-circuiting and Stream optimizations can change how many times the mapper is observed to run.

### Each Stream Can Only Be Consumed Once

```java
IntStream numbers = Stream.of("A", "BB")
        .mapToInt(String::length);

int sum = numbers.sum();

// Do not call numbers.average() afterward:
// the same Stream has already been consumed.
```

To compute both sum and average, recreate the Stream from a reusable source:

```java
int sum = words.stream().mapToInt(String::length).sum();
OptionalDouble avg = words.stream()
        .mapToInt(String::length)
        .average();
```

Or use `summaryStatistics` once. If the source comes from a file or I/O and cannot be recreated arbitrarily, design a single aggregation pass or use an intermediate collection according to memory needs and resource lifecycles.

## 12. Handling Nulls, Invalid Data, and Checked Exceptions

### 12.1. Null in an Object Source

A `Stream<T>` can contain `null` from certain sources. A mapper such as `String::length` or `s -> s.length()` will throw a `NullPointerException` if an element is null:

```java
// Illustrates a source containing null (not created with List.of because List.of forbids null).
List<String> names = new ArrayList<>();
names.add("Java");
names.add(null);

int total = names.stream()
        .mapToInt(String::length)
        .sum(); // May throw NullPointerException
```

If null should be skipped according to business rules:

```java
int total = names.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(String::length)
        .sum(); // 4
```

Do not filter out nulls indiscriminately if missing data is an error that must be reported. With `Integer` wrappers, unboxing null can also throw `NullPointerException`:

```java
// Illustration: numericValues is a List<Integer> that may contain null.
int total = numericValues.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

This snippet is not standalone because `numericValues` needs to be declared; it points out that a primitive stream cannot represent a primitive numeric element as `null`.

### 12.2. Parsing Failures

`Integer::parseInt` and `Long::parseLong` can throw `NumberFormatException`. You should not silently turn invalid strings into zero, especially when doing so can skew sum and average reports.

If you need to parse a batch of potentially invalid data, consider validating beforehand, recording errors per record, or splitting the result stream into success/failure branches using an appropriate data structure.

### 12.3. Checked Exceptions in a Mapper

`ToIntFunction.applyAsInt`, `ToLongFunction.applyAsLong`, and `ToDoubleFunction.applyAsDouble` do not declare checked exceptions. If the mapper calls an API that throws `IOException`, the lambda must catch/handle it according to your rules or separate the I/O from the pipeline; you cannot add `throws IOException` to the target type.

Do not arbitrarily wrap every exception as unchecked just to keep code short. Determine who owns error handling, retries, logging, and compensating actions.

## 13. Arithmetic Boundaries: Overflow, Precision, and Integer Division

### 13.1. Overflow Before the Mapper Returns long

`mapToLong` does not protect an addition or multiplication that already overflowed `int` inside the body:

```java
int price = 1_500_000_000;
int units = 3;

long wrong = price * units;        // Overflows in int
long correct = (long) price * units;
```

For data that can exceed even `long`, use `BigInteger` or an overflow-checking mechanism as required. If you want to detect errors precisely when an individual operation exceeds the value range, use `Math.multiplyExact` and `Math.addExact` in the appropriate places.

### 13.2. int / int Is Still Integer Division

```java
double average = IntStream.of(1, 2, 3)
        .mapToDouble(n -> n / 2)
        .sum(); // 2.0, because 1/2=0, 2/2=1, 3/2=1
```

If the goal is floating-point division:

```java
double total = IntStream.of(1, 2, 3)
        .mapToDouble(n -> n / 2.0)
        .sum(); // 3.0
```

Simply switching to `mapToDouble` does not force all operations **inside** the body to use `double`. At least one operand must be a floating-point number before dividing.

### 13.3. Double Does Not Guarantee Decimal Exactness

For currency, using `double` and then formatting to two decimal places does not mean the value is stored accurately according to monetary rules. If you need to calculate discounted prices, taxes, or rounding per line item or at the end of a transaction, define the rules clearly and use an appropriate numeric type.

### 13.4. NaN and Infinity

`DoubleStream` can contain `Double.NaN` or `Double.POSITIVE_INFINITY` from a mapper. `sum`, `average`, `min`, and `max` have specific rules for these values; do not assume every result is always a finite number. When processing measurements, check inputs with `Double.isFinite(value)` if the data domain requires finite real numbers.

## 14. When Should You Use Each Method?

| Scenario | Suggested Method | Reason |
| --- | --- | --- |
| Counting total item quantities in records | `mapToInt(Order::units).sum()` | `int` property, simple summation |
| Calculating total revenue in minor units | `mapToLong(order -> ...)` | Result may exceed `int` |
| Calculating average weight | `mapToDouble(Measure::weightKg).average()` | Measurement data in `double` |
| Calculating string lengths | `mapToInt(String::length)` | Avoids boxing each length |
| Converting integers to larger units | `IntStream.mapToLong` | Evaluates formula with a `long` result |
| Converting int to double for real division | `IntStream.mapToDouble` | Uses floating-point numbers in the expression |
| Needing `List<Integer>` as the result | `mapToInt(...).boxed().toList()` | Converts to wrappers when actually needed |
| Needing domain objects or `BigDecimal` | `map(...)` | Result type is not a primitive number |
| Needing multiple statistics on the same data stream | `summaryStatistics()` | One terminal pass for multiple metrics |

Prioritize the result type that fits the **semantics and data range**, then choose a primitive stream when the calculation needs primitive numbers. Do not choose `mapToInt` for values that can exceed `int` just because the initial value is stored as an `int`; you may need to widen the type before calculating.

## 15. Common Mistakes

1. **Mistaking `mapToInt` for returning `Stream<Integer>`:** it returns `IntStream`; if you want an object stream, call `boxed()`.
2. **Writing `map(...).sum()`:** `Stream<Integer>` does not have a direct `sum()` like `IntStream`. Choose `mapToInt` or an appropriate `reduce` operation.
3. **Using the wrong mapper:** `mapToInt` requires a result usable as `int`; a mapper returning `String` does not match the target type.
4. **Assuming `mapToLong` fixes an already-overflowed `int` multiplication:** you must widen the type before the operation.
5. **Assuming `mapToDouble` turns `int/int` into floating-point division:** you must use a `double` operand, such as `2.0`.
6. **Calling `average().getAsDouble()` without checking for an empty source:** it can throw `NoSuchElementException`; use `isPresent`, `orElse`, or a missing-data policy.
7. **Forgetting nulls in an object Stream:** method references and unboxing can throw an NPE.
8. **Forgetting malformed input:** `parseInt` does not automatically skip invalid values; handle validation.
9. **Assuming sum is always exact and never overflows:** `int`/`long` have finite ranges, while `double` has precision errors.
10. **Using the same primitive stream for multiple terminal operations:** a Stream is single-use.
11. **Calling `boxed` too early:** it can cause unnecessary boxing; stay on primitives for numeric calculations.
12. **Using `double` for money just to compute averages:** choose the numeric type according to financial rules.
13. **Thinking `mapToInt` executes immediately:** it is an intermediate operation; the mapper usually runs only when a terminal operation requests elements.
14. **Abusing side effects in lambdas:** the number of mapper executions can be affected by short-circuiting and optimizations.

## 16. Practice Exercises

1. Given `List<String> words = List.of("Java","Go","API");`. Write a pipeline using `mapToInt` to get the total length. What is the result?
2. Given `record Item(String id,int count) {}` and a list of 3 Items with counts 2, 4, and 6. Use `mapToInt` to calculate the sum, average, and maximum.
3. Given a list of numeric strings `"100"`, `"200"`, `"300"`. Use `mapToLong(Long::parseLong)` to compute the sum; what happens if `"abc"` is present?
4. With two fields `int unitPrice` and `int quantity` that can be large, write a lambda for `mapToLong` so that the multiplication is performed as `long` from the start.
5. Suppose `record Sensor(double temperature) {}`. Compute the `OptionalDouble` average temperature using `mapToDouble`. Choose a policy for when the list is empty.
6. Write a pipeline from `Stream.of("A","BB","CCC")` through `mapToInt(String::length)` and then `boxed()` to get a `List<Integer>`.
7. Distinguish `IntStream.of(1,2,3).mapToDouble(n -> n/2).sum()` from `mapToDouble(n -> n/2.0).sum()`.
8. Why can `Stream<Integer>` contain `null` elements while `IntStream` has no primitive `null` value? Where can an NPE occur?
9. What type can `sum()` return after `IntStream.mapToLong`? Why does the same mapper method name on a primitive stream not mean the same functional interface as on `Stream<T>`?
10. A report needs the sum, min, max, and average quantity on the same data. Why might `summaryStatistics()` be more suitable than trying to reuse the same Stream for four terminal operations?

### Answer Key

1. `words.stream().mapToInt(String::length).sum()` returns `9`.
2. `summaryStatistics()` gives `sum=12`, `count=3`, `average=4.0`, `max=6`; or create a new Stream for each metric.
3. Sum is `600`; `"abc"` causes a `NumberFormatException` when the mapper runs.
4. `mapToLong(x -> (long) x.unitPrice() * x.quantity())` when the record has appropriate accessors; cast to `long` before multiplication.
5. `sensors.stream().mapToDouble(Sensor::temperature).average()`; when empty, it returns `OptionalDouble.empty()`, and the caller decides how to handle missing data.
6. `Stream.of("A","BB","CCC").mapToInt(String::length).boxed().toList()` returns `[1,2,3]`.
7. The integer-division version returns a sum of `2.0`; the floating-point-division version returns a sum of `3.0`.
8. `Integer` is an object that can be null; when `mapToInt(Integer::intValue)` dereferences or unboxes a null element, an NPE occurs.
9. It returns `long`; `IntStream.mapToLong` expects `IntToLongFunction`, whereas `Stream<T>.mapToLong` expects `ToLongFunction<? super T>`.
10. `summaryStatistics()` computes multiple statistics in a single terminal operation, whereas each Stream can only be consumed once.

## Conclusion

**`mapToInt()`, `mapToLong()`, and `mapToDouble()`** are the bridge from `Stream<T>` to the three **primitive stream** types. They allow you to transform objects into numbers according to specific function descriptors and then continue computing `sum`, `average`, `max`, `min`, or `summaryStatistics` without unnecessarily returning to wrappers.

When designing a pipeline, choose the numeric type based on data range and business requirements, control `null` and parse errors, remember to check Optionals when the source may be empty, widen types before operations that risk overflow, and separate approximate measurement data from financial calculations requiring exact precision. Understanding both the **result type** and the **semantics of operations inside the mapper** matters more than simply renaming `map` to `mapTo...`.
