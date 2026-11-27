# Transforming One Element into Many Elements with mapMulti in Java 17

> **Topic:** Java 17
> **Chapter:** Collections and Streams

## 1. The Problem

An input element sometimes needs to produce zero, one, or multiple output elements: an order has multiple line items, a sentence has multiple words, an Optional may be empty, or a record may emit multiple events.

The Stream API provides these operations:

| Operation | Meaning |
|---|---|
| `map` | One element into exactly one element |
| `filter` | Keep or discard an element |
| `flatMap` | One element into a child Stream, then flatten |
| `mapMulti` | Emit zero, one, or multiple elements via a consumer |

`mapMulti` was added in Java 16 and is a stable API in Java 17. It is useful when the transformation logic can be written naturally using loops or conditionals.

## 2. How Does mapMulti Work?

For an object Stream, the method signature in Java 17 is:

```java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper)
```

Where:

- `T` is the element type of the source Stream.
- `R` is the element type of the resulting Stream.
- `mapper` is invoked for each source element.
- The second parameter of the mapper is a `Consumer<R>` used to emit output elements.
- `consumer.accept(value)` can be called zero times, once, or multiple times.

The mapper **pushes results directly** through the consumer. The mapper does not return a child Stream as in `flatMap`.

### 2.1. Example: One String Produces Characters

```java
import java.util.List;

public class MapMultiIntro {
    public static void main(String[] args) {
        List<String> words = List.of("cat", "dog");

        List<Character> characters = words.stream()
                .<Character>mapMulti((word, output) -> {
                    for (char ch : word.toCharArray()) {
                        output.accept(ch);
                    }
                })
                .toList();

        System.out.println(characters);
    }
}
```

The result is `[c, a, t, d, o, g]`. For each string, the mapper emits each character in order. `<Character>` is a **type witness** explicitly specifying the resulting Stream's type `R`. When a lambda only calls `accept` or emits no value, writing it explicitly makes the code clearer and avoids type inference errors.

### 2.2. Emitting Zero Elements

If the mapper does not call the consumer, the source element produces no result elements:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> evenNumbers = numbers.stream()
        .<Integer>mapMulti((number, output) -> {
            if (number % 2 == 0) {
                output.accept(number);
            }
        })
        .toList();

System.out.println(evenNumbers); // [2, 4]
```

If you only want to filter and keep the original values as is, `filter` expresses the intent better:

```java
List<Integer> evenNumbers = numbers.stream()
        .filter(number -> number % 2 == 0)
        .toList();
```

### 2.3. Emitting Multiple Elements

```java
List<Integer> values = List.of(2, 3, 1);

List<Integer> expanded = values.stream()
        .<Integer>mapMulti((value, output) -> {
            for (int i = 0; i < value; i++) {
                output.accept(value);
            }
        })
        .toList();

System.out.println(expanded); // [2, 2, 3, 3, 3, 1]
```

The number of `accept` calls depends on the input value. Each number `n` produces `n` copies of itself.

## 3. Comparing mapMulti with flatMap

`flatMap` is a familiar operation for turning each element into a child Stream and flattening those child Streams into a single Stream.

### 3.1. Same Problem Written with flatMap

Suppose each sentence needs to be split into words:

```java
import java.util.Arrays;
import java.util.List;

List<String> sentences = List.of(
        "Java Stream",
        "mapMulti example");

List<String> words = sentences.stream()
        .flatMap(sentence -> Arrays.stream(sentence.split(" ")))
        .toList();

System.out.println(words);
```

Output:

```text
[Java, Stream, mapMulti, example]
```

Each source element is mapped to a `Stream<String>`. `flatMap` feeds the elements of those child Streams into a single result Stream.

### 3.2. Writing the Same Logic with mapMulti

```java
import java.util.List;

List<String> sentences = List.of(
        "Java Stream",
        "mapMulti example");

List<String> words = sentences.stream()
        .<String>mapMulti((sentence, output) -> {
            for (String word : sentence.split(" ")) {
                output.accept(word);
            }
        })
        .toList();
```

With this approach, there is no need to create a child Stream for each sentence. The mapper iterates over the array returned by `split` and emits each word.

### 3.3. Comparing Mindsets

| Aspect | `flatMap` | `mapMulti` |
|---|---|---|
| Mapper returns | A Stream for each element | Returns no Stream; pushes results via a consumer |
| Representation | Each source element produces a child source | Each source element executes a procedure that emits results |
| Well suited for | Logic that already has APIs returning a Stream | Loops, conditionals, possibly emitting few elements |
| Zero output | Return `Stream.empty()` | Do not call the consumer |
| One output | Return `Stream.of(value)` | Call `accept(value)` once |
| Many outputs | Return a Stream containing multiple values | Call `accept` multiple times |
| Child Stream resources | `flatMap` manages closing child Streams after consumption | No need to create child Streams in the mapper |
| Performance | May incur child Stream creation and orchestration overhead | May reduce child Stream allocation overhead in some cases |

**Do not conclude that `mapMulti` is always faster than `flatMap`.** The API is designed to support pushing results directly, which can reduce allocations in certain workloads. However, performance depends on the implementation, output counts, mapper logic, and pipeline. Benchmark on representative data if performance is a key criterion.

### 3.4. When to Prefer flatMap

If a processing method naturally returns a Stream already, `flatMap` is usually clearer:

```java
Stream<String> readWords(Path path) {
    // Illustrative example: an API returning Stream<String>.
    return Stream.of("Java", "Stream");
}

List<String> allWords = paths.stream()
        .flatMap(this::readWords)
        .toList();
```

`flatMap` also has a rule to close child Streams once their contents have been fed into the pipeline. If child Streams manage resources, such as file-reading Streams, this rule is crucial.

`mapMulti` is not a replacement for `flatMap`'s resource management mechanism. If a mapper opens a file or other resource, you must manage it yourself with `try-with-resources` and emit values while the resource remains open.

## 4. Practical Examples with Collections and Streams

### 4.1. One Order Produces Multiple Line Items

Model:

```java
import java.util.List;

record OrderLine(String productCode, int quantity) { }
record Order(String orderId, List<OrderLine> lines) { }
```

Each `Order` has multiple `OrderLine` items. To get a list of all line items across multiple orders:

```java
List<Order> orders = List.of(
        new Order("ORD-1", List.of(
                new OrderLine("P-01", 2),
                new OrderLine("P-02", 1))),
        new Order("ORD-2", List.of(
                new OrderLine("P-03", 4))));

List<OrderLine> allLines = orders.stream()
        .<OrderLine>mapMulti((order, output) -> {
            for (OrderLine line : order.lines()) {
                output.accept(line);
            }
        })
        .toList();

System.out.println(allLines);
```

Output:

```text
[OrderLine[productCode=P-01, quantity=2],
 OrderLine[productCode=P-02, quantity=1],
 OrderLine[productCode=P-03, quantity=4]]
```

This is a case where one source element (`Order`) produces multiple result elements (`OrderLine`).

If the model already exposes `order.lines()` returning `List<OrderLine>`, the `flatMap` approach is also very natural:

```java
List<OrderLine> allLines = orders.stream()
        .flatMap(order -> order.lines().stream())
        .toList();
```

Choose based on style and mapper requirements. `flatMap` is concise when a child collection/Stream already exists; `mapMulti` is convenient when you need to filter, check, or transform inside a loop before emitting results.

### 4.2. An Optional Value Produces Zero or One Output

An `Optional` may contain a value or be empty. You can turn a Stream of Optionals into a Stream of present values:

```java
import java.util.List;
import java.util.Optional;

List<Optional<String>> inputs = List.of(
        Optional.of("Java"),
        Optional.empty(),
        Optional.of("Stream"));

List<String> values = inputs.stream()
        .<String>mapMulti((optional, output) ->
                optional.ifPresent(output))
        .toList();

System.out.println(values); // [Java, Stream]
```

Each Optional can emit one string or nothing. In this simple case, you can also use:

```java
List<String> values = inputs.stream()
        .flatMap(Optional::stream)
        .toList();
```

`Optional.stream()` has been an API since Java 9 and remains stable in Java 17. If you only need to discard empty Optionals, `flatMap(Optional::stream)` is very readable.

### 4.3. One Record Can Produce Multiple Events

Suppose an inventory change produces notifications for thresholds being monitored:

```java
import java.util.List;

record StockChange(String product, int before, int after) { }
record StockEvent(String product, String type, int quantity) { }

static List<StockEvent> events(List<StockChange> changes) {
    return changes.stream()
            .<StockEvent>mapMulti((change, output) -> {
                if (change.after() == 0) {
                    output.accept(new StockEvent(
                            change.product(), "OUT_OF_STOCK", 0));
                }

                if (change.before() > 10 && change.after() <= 10) {
                    output.accept(new StockEvent(
                            change.product(), "LOW_STOCK", change.after()));
                }

                if (change.after() > change.before()) {
                    output.accept(new StockEvent(
                            change.product(), "RESTOCKED", change.after()));
                }
            })
            .toList();
}
```

A `StockChange` can emit zero events, one event, or multiple events. The mapper directly expresses the business rules and event emission order.

The order of `accept` calls within a single mapper invocation is the order in which that record's events enter the result. If event order has business meaning, keep the emission order explicit and avoid nondeterministic shared state.

### 4.4. Expanding a Data Row into Multiple Values Conditionally

```java
record Product(String code, int stock, boolean active) { }

List<Product> products = List.of(
        new Product("A", 5, true),
        new Product("B", 0, true),
        new Product("C", 10, false));

List<String> availableCodes = products.stream()
        .<String>mapMulti((product, output) -> {
            if (product.active() && product.stock() > 0) {
                output.accept(product.code());
                if (product.stock() >= 10) {
                    output.accept(product.code() + "-BULK");
                }
            }
        })
        .toList();
```

The result is `[A, C-BULK]`. A product may produce no result, one code, or both a regular code and a bulk code. If you only want to return an eligible product code once, `filter` followed by `map` is easier to understand.

## 5. Using mapMulti with Primitive Streams

Java provides specialized Streams for primitive types:

- `IntStream`
- `LongStream`
- `DoubleStream`

These APIs avoid unnecessary boxing/unboxing in numeric pipelines.

### 5.1. IntStream.mapMulti

`IntStream` has a `mapMulti` method taking `IntStream.IntMapMultiConsumer`, whose output parameter is an `IntConsumer`.

For example, each integer `n` emits numbers from `1` to `n`:

```java
import java.util.stream.IntStream;

int[] values = IntStream.of(2, 3, 1)
        .mapMulti((number, output) -> {
            for (int i = 1; i <= number; i++) {
                output.accept(i);
            }
        })
        .toArray();

System.out.println(java.util.Arrays.toString(values));
```

Output:

```text
[1, 2, 1, 2, 3, 1]
```

The input is an `IntStream`, and the output remains an `IntStream`. Values are emitted through `IntConsumer`, so there is no need to box each number into an `Integer` and unbox it again.

### 5.2. From Stream<String> to IntStream with mapMultiToInt

When the source Stream is an object Stream but the results are integers, use `mapMultiToInt`:

```java
import java.util.List;

int[] codePoints = List.of("Java", "17").stream()
        .mapMultiToInt((text, output) ->
                text.codePoints().forEach(output))
        .toArray();
```

`String.codePoints()` returns an `IntStream` containing Unicode code points. The consumer of `mapMultiToInt` accepts `int`, so it can be passed directly to `forEach`.

Do not confuse `String.chars()` with `String.codePoints()`:

- `chars()` emits UTF-16 code unit values.
- `codePoints()` emits Unicode code points, which may span surrogate pairs.

If the goal is processing Unicode characters at the code point level, `codePoints()` is usually more appropriate.

### 5.3. mapMultiToLong and mapMultiToDouble

From an object Stream, you can emit `long` or `double` values:

```java
import java.util.List;

record Measurement(String sensor, double[] samples) { }

List<Measurement> measurements = List.of(
        new Measurement("S1", new double[] { 10.5, 11.0 }),
        new Measurement("S2", new double[] { 8.0, 9.5 }));

double[] allSamples = measurements.stream()
        .mapMultiToDouble((measurement, output) -> {
            for (double sample : measurement.samples()) {
                output.accept(sample);
            }
        })
        .toArray();
```

Similarly, `mapMultiToLong` uses a `LongConsumer` to emit `long` values.

### 5.4. Variants on Primitive Streams

Main methods in Java 17:

| Source Stream | Method | Output consumer type | Result type |
|---|---|---|---|
| `Stream<T>` | `mapMulti` | `Consumer<R>` | `Stream<R>` |
| `Stream<T>` | `mapMultiToInt` | `IntConsumer` | `IntStream` |
| `Stream<T>` | `mapMultiToLong` | `LongConsumer` | `LongStream` |
| `Stream<T>` | `mapMultiToDouble` | `DoubleConsumer` | `DoubleStream` |
| `IntStream` | `mapMulti` | `IntConsumer` | `IntStream` |
| `IntStream` | `mapMultiToObj` | `Consumer<R>` | `Stream<R>` |
| `LongStream` | `mapMulti` | `LongConsumer` | `LongStream` |
| `LongStream` | `mapMultiToObj` | `Consumer<R>` | `Stream<R>` |
| `DoubleStream` | `mapMulti` | `DoubleConsumer` | `DoubleStream` |
| `DoubleStream` | `mapMultiToObj` | `Consumer<R>` | `Stream<R>` |

The specialized consumer interfaces are defined on the respective primitive stream types, such as `IntStream.IntMapMultiConsumer`.

## 6. Using mapMulti in Larger Pipelines

`mapMulti` is an **intermediate operation**: it does not consume the Stream immediately in place. Downstream operations determine when data is processed.

Example:

```java
List<String> result = orders.stream()
        .<OrderLine>mapMulti((order, output) -> {
            for (OrderLine line : order.lines()) {
                if (line.quantity() > 0) {
                    output.accept(line);
                }
            }
        })
        .filter(line -> line.productCode().startsWith("P-"))
        .map(line -> line.productCode() + ":" + line.quantity())
        .distinct()
        .sorted()
        .toList();
```

Pipeline:

```text
Stream<Order>
      |
      v
mapMulti: each order emits OrderLine items with quantity > 0
      |
      v
filter: keep only codes starting with P-
      |
      v
map: convert OrderLine to String
      |
      v
distinct
      |
      v
sorted
      |
      v
toList()
```

In this pipeline, `mapMulti` performs the data expansion; subsequent operations continue processing the resulting Stream. There is no need to collect into an intermediate list and call `stream()` again.

### 6.1. Results Follow the Encounter Order of Ordered Streams

For a Stream with an encounter order, `mapMulti` preserves the relative order of input elements and the order in which the mapper emits elements for each input. Example:

```java
List<Integer> values = List.of(1, 2, 3).stream()
        .<Integer>mapMulti((number, output) -> {
            output.accept(number);
            output.accept(number * 10);
        })
        .toList();

System.out.println(values); // [1, 10, 2, 20, 3, 30]
```

With unordered Streams, or when a pipeline explicitly drops encounter order, do not rely on an order the source does not guarantee. `forEach` on a parallel stream also does not guarantee display order; if you need to collect results in encounter order, use an appropriate terminal operation such as `toList()` or `forEachOrdered()` depending on the problem.

### 6.2. mapMulti Is Not a Terminal Operation

This snippet does not execute the pipeline yet:

```java
Stream<String> result = source
        .<String>mapMulti((value, output) -> output.accept(value));
```

Only when there is a terminal operation such as `toList()`, `count()`, `reduce()`, or `forEach()` is the Stream consumed:

```java
List<String> values = result.toList();
```

A Stream can only be consumed once. Do not reuse `result` for a second terminal operation.

## 7. Rules and Limitations to Understand

### 7.1. The Consumer May Only Be Used While the Mapper Is Running

The consumer passed to the mapper belongs to the pipeline. Call `accept` **during the mapper invocation itself**; do not store the consumer in a field or collection or use it after the mapper returns.

Do not retain the consumer to call asynchronously or after the mapper finishes. `mapMulti` is designed for the mapper to push data synchronously within the scope of its invocation; using the consumer outside that timeframe is outside supported usage.

### 7.2. Do Not Mutate the Stream Source Inside the Mapper

The mapper should be *non-interfering* with the data source. For example, if the Stream is backed by an `ArrayList`, do not add or remove elements from that same list inside the mapper:

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));

// Do not mutate values while its stream is being processed.
values.stream()
        .<Integer>mapMulti((value, output) -> {
            output.accept(value);
            // values.add(99); // Interfering with Stream source
        })
        .toList();
```

Modifying the source while the pipeline is traversing it can cause errors, unexpected results, or violate the Stream contract.

### 7.3. Avoid Side Effects Dependent on Mapper Invocation Count

Do not build business logic around side effect ordering or invocation counts:

```java
int[] counter = { 0 };

List<Integer> values = source.stream()
        .<Integer>mapMulti((value, output) -> {
            counter[0]++;
            output.accept(value);
        })
        .toList();
```

In a sequential example, the counter might look predictable. However, if switched to a parallel stream, the mapper can run concurrently across multiple elements; the `counter` array is not thread-safe and the result has a race condition.

Keep mappers stateless, non-interfering with the data source, and free of side effects. If statistics are needed, use an appropriate terminal reduction or collector.

### 7.4. Parallel Streams and Consumers

In a parallel stream, mapper invocations for different source elements may run on different threads. Each invocation's consumer is used to emit results for that invocation; do not collect consumers into a shared variable.

Example:

```java
List<Integer> expanded = values.parallelStream()
        .<Integer>mapMulti((value, output) -> {
            output.accept(value);
            if (value % 2 == 0) {
                output.accept(value * 10);
            }
        })
        .toList();
```

The mapper does not mutate shared state and only emits values based on the current element. With an ordered source, `toList()` collects results in the Stream's encounter order, even though processing steps may run in parallel.

Do not share a mutable `ArrayList` to receive results inside the mapper. Let the Stream manage passing elements through the pipeline and use a terminal operation/collector to gather them.

### 7.5. Exceptions in the Mapper

If the mapper or a `consumer.accept` call throws an exception, pipeline execution terminates with that exception (or an exception thrown by a downstream operation). Do not silently swallow data errors:

```java
List<String> values = records.stream()
        .<String>mapMulti((record, output) -> {
            if (record == null) {
                throw new IllegalArgumentException("record must not be null");
            }
            output.accept(record.trim());
        })
        .toList();
```

If the domain wants to skip invalid data, express that explicitly by conditionally not emitting an element or via a dedicated error-collection channel.

## 8. Performance: When Can mapMulti Be Helpful?

A primary reason `mapMulti` was added is to reduce the cost of representing each intermediate result as a child Stream. Compare:

**flatMap approach:**

```java
List<String> tokens = lines.stream()
        .flatMap(line -> Arrays.stream(line.split(",")))
        .toList();
```

**mapMulti approach:**

```java
List<String> tokens = lines.stream()
        .<String>mapMulti((line, output) -> {
            for (String token : line.split(",")) {
                output.accept(token);
            }
        })
        .toList();
```

In the `flatMap` approach, each line creates a child Stream. In the `mapMulti` approach, the mapper emits tokens directly. When each input produces only a few outputs and emission is simple, the latter can avoid some child Stream objects and dispatch overhead.

However:

- `split()` still allocates a string array; `mapMulti` does not eliminate that cost.
- Very large output counts still require processing and storing the corresponding elements.
- An implementation may use internal buffers; the API specification does not guarantee every implementation uses the same allocation strategy.
- A complex mapper or heavy imperative logic can be harder to read than a `flatMap` expression.
- The JIT may optimize different pipelines differently; only benchmarking reveals behavior for a specific workload.

### 8.1. Benchmarking Properly

If you need to decide between `flatMap` and `mapMulti` for performance:

1. Use data representative of actual size and distribution.
2. Measure zero-, one-, and many-output cases.
3. Run warm-up and measure multiple iterations; do not draw conclusions from a single simple `System.nanoTime()` run.
4. Measure allocation/GC if the goal is reducing intermediate Stream objects.
5. Use JMH (Java Microbenchmark Harness) for microbenchmarks instead of hand-rolled timing loops.
6. Ensure both implementations produce the same output and perform the same work.

There is no universal element-count threshold where `mapMulti` always wins. Prioritize readability and optimize only when backed by measurements.

## 9. Common Mistakes When Using mapMulti

| Mistake/misconception | Consequence | Resolution |
|---|---|---|
| Thinking the mapper must return a value | Wrong signature or attempting to return results | Call `output.accept(value)` to emit elements |
| Not calling `accept` and expecting to keep the source element | Source element disappears from the result Stream | Call `accept` to re-emit it, or use `map` |
| Using `mapMulti` for simple one-to-one transformations | More verbose than `map` | Use `map` |
| Using `mapMulti` solely for filtering | Less readable intent than `filter` | Use `filter` |
| Returning a child Stream from the mapper | Confused with `flatMap` | Use `flatMap` if you already have a child Stream |
| Saving the consumer to call later | Using the consumer outside mapper execution | Emit synchronously inside the mapper |
| Sharing a mutable collection inside a parallel mapper | Race conditions or data corruption | Use pipeline/collectors, avoid side effects |
| Assuming `mapMulti` is always faster | Unmeasured optimization | Benchmark the real workload |
| Forgetting to specify output type when the compiler cannot infer it | Generic inference error | Use a type witness like `.<String>mapMulti(...)` |
| Using `Stream<Integer>` when results are just integers | May cause boxing | Consider `mapMultiToInt`/primitive streams |
| Ignoring emission order | Business order may become wrong | Emit in deterministic order; preserve encounter order when needed |
| Using `mapMulti` to open resources without closing them | File/socket/stream leaks | Manage resources with try-with-resources or an appropriate API |

## 10. Practice Exercises

### Exercise 1 — Split Sentences into Words

Given the list:

```java
List<String> sentences = List.of(
        "Java is useful",
        "Stream API",
        "mapMulti in Java 17");
```

Use `mapMulti` to create a `List<String>` containing all words in their order of appearance. Do not use `flatMap`.

**Suggested solution:**

```java
List<String> words = sentences.stream()
        .<String>mapMulti((sentence, output) -> {
            for (String word : sentence.split(" ")) {
                output.accept(word);
            }
        })
        .toList();
```

### Exercise 2 — Emit Only Prime Numbers

Given an integer Stream from 1 to 30. Use `mapMulti` to emit nothing for numbers less than 2, emit each prime number once, and emit nothing for composite numbers.

**Suggested solution:**

```java
static boolean isPrime(int n) {
    if (n < 2) return false;
    for (int divisor = 2; divisor * divisor <= n; divisor++) {
        if (n % divisor == 0) return false;
    }
    return true;
}

List<Integer> primes = java.util.stream.IntStream.rangeClosed(1, 30)
        .<Integer>mapMultiToObj((number, output) -> {
            if (isPrime(number)) {
                output.accept(number);
            }
        })
        .toList();
```

In this exercise, the source is an `IntStream`, so `mapMultiToObj` emits `Integer` objects into `Stream<Integer>`. To keep the result as an `IntStream`, use `IntStream.mapMulti`.

### Exercise 3 — Expand Orders into Line Items

Define:

```java
record Item(String sku, int quantity) { }
record Order(String id, List<Item> items) { }
```

Use `mapMulti` to emit only items with `quantity > 0` and produce the resulting `List<Item>`.

**Suggested solution:**

```java
List<Item> items = orders.stream()
        .<Item>mapMulti((order, output) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    output.accept(item);
                }
            }
        })
        .toList();
```

### Exercise 4 — Convert Optional to Stream

Given `List<Optional<Integer>>`. Use `mapMulti` to produce a list of present numbers, then rewrite it using `flatMap(Optional::stream)`. Compare the readability of both approaches.

**Hint:**

```java
List<Integer> first = optionals.stream()
        .<Integer>mapMulti((optional, output) ->
                optional.ifPresent(output))
        .toList();

List<Integer> second = optionals.stream()
        .flatMap(Optional::stream)
        .toList();
```

### Exercise 5 — Distinguish mapMulti and mapMultiToInt

From `List<String>`, emit the length of each string using `mapMultiToInt`. Then aggregate the result with `sum()`.

**Suggested solution:**

```java
int totalLength = words.stream()
        .mapMultiToInt((word, output) -> output.accept(word.length()))
        .sum();
```

### Exercise 6 — Emit Multiple Results Conditionally

For each integer `n`, emit `n` if even; emit `n` and `-n` if odd; emit nothing if `n == 0`. Determine the output order for source `[1, 2, 0, 3]`.

**Suggested solution:**

```java
List<Integer> result = List.of(1, 2, 0, 3).stream()
        .<Integer>mapMulti((n, output) -> {
            if (n == 0) {
                return;
            }
            output.accept(n);
            if (n % 2 != 0) {
                output.accept(-n);
            }
        })
        .toList();
```

Result: `[1, -1, 2, 3, -3]`.

## 11. Official Java 17 Documentation

- [Java SE 17 API — Stream.mapMulti](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#mapMulti(java.util.function.BiConsumer)): signature, description of mappers emitting zero or more elements, and API examples.
- [Java SE 17 API — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): `mapMulti`, `mapMultiToObj`, and `IntMapMultiConsumer`.
- [Java SE 17 API — LongStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html) and [DoubleStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html): variants for primitive streams.
- [Java SE 17 API — Optional.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html#stream()): converting an Optional to a Stream containing zero or one element.
- [Java SE 17 API — Stream.flatMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#flatMap(java.util.function.Function)): flattening rules and closing child Streams.

**Key takeaway:** `mapMulti` lets one source element emit zero, one, or multiple elements through a consumer. Use `map` for one-to-one transforms, `filter` for keep/discard, `flatMap` when the mapper naturally returns a child Stream, and `mapMulti` when you want to emit results directly with loops or conditionals. In Java 17, this API is stable and also includes variants for primitive streams.
