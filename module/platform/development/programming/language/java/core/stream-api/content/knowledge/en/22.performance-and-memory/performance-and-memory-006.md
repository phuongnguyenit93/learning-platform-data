# Choosing `flatMap` or `mapMulti` Based on Data and Measurement

In the **Performance and Memory** chapter of **Java Stream API**, after mastering lazy pipelines, `filter`, `map`, `reduce`, `collect`, and `Spliterator` usage, a practical question arises: **when one input element can produce zero, one, or multiple output elements, should you use `flatMap` or `mapMulti`?**

Both methods express a **one-to-many transformation**. The main difference lies in how the mapper supplies results:

- `flatMap` requires the mapper to return **a child Stream** for each input element; the Stream API flattens those child Streams.
- `mapMulti` passes **an output Consumer** to the mapper; the mapper calls `accept` zero, one, or more times to emit elements.

`mapMulti` can cut boilerplate for creating tiny child Streams and can sometimes offer performance benefits. However, **there is no universal rule that `mapMulti` is always faster or uses less memory than `flatMap`**. The Javadoc allows `mapMulti`'s default implementation to use an intermediate buffer and `flatMap`; actual efficiency depends on the JDK, data, emitted element counts, transformations, and terminal operation.

This lesson covers each API's contract, typical use cases, equivalent Java examples, short-circuit and I/O resource risks, JMH benchmarks, and a **decision matrix grounded in semantics first, measurements second**.

> **Versions:** `Stream.flatMap` and its primitive variants have existed since Java 8. `Stream.mapMulti`, `mapMultiToInt`, `mapMultiToLong`, and `mapMultiToDouble` were added in **Java 16**. Complete examples use Java 17+; `record` and `Stream.toList()` require Java 16+. If you must support Java 8 or Java 11, do not call `mapMulti` directly.

## 1. Recognizing a one-to-many problem properly

Suppose you have a list of orders, each containing a list of line items:

~~~text
Order #10: [PEN x2, BOOK x0]
Order #11: []
Order #12: [PAD x3, PEN x1]
~~~

Requirement: generate a list of `"orderId:sku"` codes only for lines with quantity **greater than 0**.

~~~text
10:PEN
12:PAD
12:PEN
~~~

Here each order can emit:

| Input | Output element count | Reason |
| --- | ---: | --- |
| Order 10 | 1 | One item has quantity > 0 |
| Order 11 | 0 | No line items |
| Order 12 | 2 | Two items have quantity > 0 |

A plain `map` always turns **one element into exactly one result**, unless that result wraps a collection or uses an optional representation. `flatMap` and `mapMulti` fit when you need to **flatten** sub-results into a single stream.

Before comparing performance, define the **output contract**:

1. Which elements are kept?
2. How many outputs can each input emit?
3. Must encounter order be preserved?
4. Can results be `null`?
5. Is the child source already a Stream or data to iterate?
6. Might downstream short-circuit?
7. Are there resources to close?

If the answers change, the right method may change too.

## 2. `flatMap`: each input returns a child Stream

General signature of `flatMap`:

~~~java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
~~~

The mapper takes one element of type `T` and returns a `Stream<? extends R>` holding child results. The Stream API feeds the child Stream's elements into the main pipeline.

Java 17 example:

~~~java
List<String> codes = orders.stream()
        .flatMap(order -> order.items().stream()
                .filter(item -> item.quantity() > 0)
                .map(item -> order.id() + ":" + item.sku()))
        .toList();
~~~

You can read it left to right:

1. Traverse an `Order`.
2. Open a child Stream via `order.items().stream()`.
3. Filter items with `quantity > 0`.
4. Format each item into `"orderId:sku"`.
5. `flatMap` flattens those child Streams into `Stream<String>`.
6. `toList()` collects the final result.

### Advantages of `flatMap`

- Readable when **the child source already provides a Stream** or sub-processing is naturally expressed as a pipeline.
- Reuses Stream operations like `filter`, `map`, `limit`, `takeWhile`, `distinct`, and others per child source.
- Explicitly models transformation into a **child Stream**, helpful when the child source is lazy or has many elements.
- Carries the contract of closing child Streams returned by the mapper after their contents enter the pipeline.

### Costs to consider

When many inputs each produce an empty or single-element child Stream, writing `Stream.empty()`/`Stream.of(...)` can allocate intermediate objects or incur child Stream setup work. On some JDKs, the JIT can optimize away part or most of this cost; **never deduce actual allocation counts purely from method call counts in source code**.

When inputs already hold a child `Stream`, Stream creation cost may be **inherent to the source** rather than added by `flatMap`.

## 3. `mapMulti`: mapper emits results through a Consumer

Signature of `Stream.mapMulti`:

~~~java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper);
~~~

Inside the mapper:

- The first parameter is the input element `T`.
- The second parameter is a `Consumer<R>` supplied by the Stream API.
- Call `downstream.accept(value)` to emit one `R` result into the flattened stream.
- Do not call `accept` if the input produces no results.
- Call `accept` multiple times if the input produces multiple results.

For the same order problem:

~~~java
List<String> codes = orders.stream()
        .<String>mapMulti((order, emit) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    emit.accept(order.id() + ":" + item.sku());
                }
            }
        })
        .toList();
~~~

There is no `Stream.empty()` or `Stream.of(...)` creation per order. The mapper iterates the child list with a loop and **pushes values**.

The `.<String>mapMulti(...)` syntax explicitly specifies the output type. In some contexts, especially with lambdas and unclear target types, generic type inference may widen the type to `Object`. The `<String>` type witness helps both compiler and reader understand the intent.

### `mapMulti` is not push with a cancellation signal

The Consumer in `mapMulti` has the method:

~~~java
void accept(R value);
~~~

It **does not return a boolean**, so the mapper lacks a signal like `Gatherer.Downstream.push(...)` to learn that downstream has stopped accepting more elements. This is an important difference if one input can generate millions of elements or downstream calls `limit(1)`.

`mapMulti` is designed to emit results through the Consumer **synchronously within the mapper invocation**; do not retain the Consumer to call after the mapper returns, and do not pass the Consumer to self-managed asynchronous tasks.

## 4. Complete example: two pipelines producing identical results

Place the following code in `FlatMapOrMapMultiDemo.java`:

~~~java
import java.util.List;

public class FlatMapOrMapMultiDemo {

    record Item(String sku, int quantity) {}
    record Order(int id, List<Item> items) {}

    static List<String> usingFlatMap(List<Order> orders) {
        return orders.stream()
                .flatMap(order -> order.items().stream()
                        .filter(item -> item.quantity() > 0)
                        .map(item -> order.id() + ":" + item.sku()))
                .toList();
    }

    static List<String> usingMapMulti(List<Order> orders) {
        return orders.stream()
                .<String>mapMulti((order, emit) -> {
                    for (Item item : order.items()) {
                        if (item.quantity() > 0) {
                            emit.accept(
                                    order.id() + ":" + item.sku());
                        }
                    }
                })
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order(10, List.of(
                        new Item("PEN", 2),
                        new Item("BOOK", 0)
                )),
                new Order(11, List.of()),
                new Order(12, List.of(
                        new Item("PAD", 3),
                        new Item("PEN", 1)
                ))
        );

        List<String> flat = usingFlatMap(orders);
        List<String> multi = usingMapMulti(orders);

        System.out.println(flat);
        System.out.println(multi);
        System.out.println(flat.equals(multi));
    }
}
~~~

Output:

~~~text
[10:PEN, 12:PAD, 12:PEN]
[10:PEN, 12:PAD, 12:PEN]
true
~~~

Run on JDK 17+:

~~~bash
javac --release 17 FlatMapOrMapMultiDemo.java
java FlatMapOrMapMultiDemo
~~~

The example intentionally uses a `List` with encounter order, does not mutate inputs during processing, and the mapper only creates result strings. Thus, **both contents and ordering** of the two lists can be compared directly.

If `orders` comes from an unordered collection or uses `unordered()`, do not expect the list to match the example's exact order. Choosing a flattening method does not replace the source's ordering contract.

## 5. One input producing 0, 1, a few, or very many outputs

The number of child results per input element, known as **fan-out**, is a key performance variable.

| Common fan-out | Example | Initial suggestion |
| --- | --- | --- |
| **0 or 1** | Optional value, parse success/failure, nullable field | `mapMulti` is worth trying if creating many tiny `Stream.empty`/`Stream.of`; `filter` + `map` can also be simpler |
| **0 to a few elements** | Order with a few lines, event emitting a few tags | Compare `flatMap` and `mapMulti` on real data |
| **Already a child Stream** | API returning `Stream<Line>`, lazy child source | `flatMap` is usually natural and preserves laziness |
| **Many elements per input** | One record expanding into hundreds of thousands of elements | Examine buffering, `limit`, memory; do not assume `mapMulti` wins |
| **Resource-holding child source** | Path opening a file, query returning an I/O Stream | Prefer an approach expressing clear resource ownership/closing |
| **Stateful splitting, active short-circuiting** | Windowing, batching, multi-stage stop conditions | Consider right-contract tools like iterators, Spliterators, or Gatherers depending on JDK, rather than forcing everything into `mapMulti` |

The cleanest and fastest pattern can shift when fan-out moves from `0` to `1` or `100`. A benchmark testing only “each element emits one value” is insufficient to judge flattening long lists.

## 6. The 0-or-1 result case: `null`, `Optional`, and parsers

For example, a shipment may or may not have a tracking code:

~~~java
record Shipment(String id, String trackingCode) {}
~~~

### Using `flatMap`

~~~java
List<String> codes = shipments.stream()
        .flatMap(shipment ->
                java.util.stream.Stream.ofNullable(
                        shipment.trackingCode()))
        .toList();
~~~

`Stream.ofNullable` was added in Java 9. When `trackingCode == null`, it returns an empty Stream; otherwise, a single-element Stream.

### Using `mapMulti`

~~~java
List<String> codes = shipments.stream()
        .<String>mapMulti((shipment, emit) -> {
            String tracking = shipment.trackingCode();
            if (tracking != null) {
                emit.accept(tracking);
            }
        })
        .toList();
~~~

Both pipelines produce the same output if the requirement is to **drop null values**. Still, you need not restrict yourself to just those two:

~~~java
List<String> codes = shipments.stream()
        .map(Shipment::trackingCode)
        .filter(java.util.Objects::nonNull)
        .toList();
~~~

The `map` + `filter` form can be shorter and clearer for a 1–1 transform followed by null removal; still benchmark if performance differences matter.

### How does `Optional` differ from `null`?

If inputs hold `Optional<T>`, Java 9+ supports:

~~~java
List<String> codes = optionalCodes.stream()
        .flatMap(java.util.Optional::stream)
        .toList();
~~~

With `mapMulti`:

~~~java
List<String> codes = optionalCodes.stream()
        .<String>mapMulti((opt, emit) ->
                opt.ifPresent(emit))
        .toList();
~~~

Both emit **0 or 1** value per Optional. The `emit` argument is only valid during the mapper call, so do not retain a reference for later use.

**Business note:** Dropping nulls or empty Optionals reduces element count. If the system must keep positional correspondence with every record, do not drop elements and assume the output list still matches input count/alignment.

## 7. When `flatMap` is preferred because a child Stream already exists

Suppose a domain interface already returns a child Stream:

~~~java
interface EventSource {
    java.util.stream.Stream<Event> events();
}
~~~

If you need to concatenate the sources:

~~~java
Stream<Event> all = sources.stream()
        .flatMap(EventSource::events);
~~~

`flatMap` directly expresses “each source supplies an event Stream”. It also leverages Stream's contract for child Streams: per the API, **each Stream returned by the mapper is closed after its contents have been placed into the pipeline**.

Rewriting with `mapMulti` can force eager iteration of the child Stream:

~~~java
Stream<Event> all = sources.stream()
        .<Event>mapMulti((source, emit) -> {
            try (Stream<Event> events = source.events()) {
                events.forEach(emit);
            }
        });
~~~

This snippet must use `try-with-resources` to close the child Stream. It also eagerly traverses all child elements **inside the mapper callback**, so you cannot assume the same short-circuiting behavior as `flatMap`. Writing such eager iteration is usually **counterproductive** when the source API already returns a lazy Stream.

**Rule:** If the child source is itself a Stream or holds resources, `flatMap` is the clearer starting choice. Only switch to `mapMulti` if you verify equivalent semantics, lifecycle handling, and measurable gain.

## 8. Special care for I/O resource lifecycles

A Stream created from `Files.lines(path)` holds an I/O resource that must be closed. When reading multiple files, `flatMap` can express opening each file:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static long countErrorLines(List<Path> paths) {
    return paths.stream()
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
~~~

Here the outer Stream is `paths.stream()` from an in-memory list. `flatMap` manages closing the child Streams returned by `Files.lines` under its contract. If the **outer** Stream also owns a resource, wrap that outer Stream in `try-with-resources` as well.

With `mapMulti`, the mapper author is responsible for closing the file:

~~~java
static long countErrorLinesMulti(List<Path> paths) {
    return paths.stream()
            .<String>mapMulti((path, emit) -> {
                try (Stream<String> lines =
                        Files.lines(path, StandardCharsets.UTF_8)) {

                    lines.forEach(emit);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
~~~

This closes the child source **in the right scope**, yet it is not automatically a better design: the callback may end up reading an entire child file even when downstream only wants a few elements. When processing very large files or potentially short-circuiting, `flatMap` is usually better suited to expressing a lazy child stream.

**Strictly avoid** opening `Files.lines` inside the callback and calling `forEach(emit)` without closing the Stream. Terminal operations do not automatically call `close` on an arbitrary I/O Stream.

## 9. `mapMulti` does not guarantee eliminating all buffering

A common thought:

> “`mapMulti` creates no child Streams, so it definitely allocates no buffers and always uses `O(1)` memory.”

That conclusion is **not guaranteed by the API**.

According to the API Note on `Stream.mapMulti`, a default implementation can work as follows:

1. Create an **internal buffer** for elements emitted by the mapper.
2. Call the mapper with a Consumer that appends into the buffer.
3. After the mapper returns, create a Stream from the buffer.
4. Use `flatMap` to feed the results into the pipeline.

Specific JDK implementations may optimize differently, and the JIT may alter actual object allocations. However, **code calling `mapMulti` must not depend on a “never buffers” guarantee**.

Consequences:

- With **small fan-out**, `mapMulti` can help avoid many tiny child Streams, depending on the JDK.
- With **very large fan-out from one input**, there is a risk of holding many intermediate results depending on implementation; measure heap and allocations.
- If downstream short-circuits, never assume the mapper will stop mid-loop as soon as enough results are produced.
- For large or infinite output from a single input, `mapMulti` is not a guaranteed element-by-element streaming/backpressure mechanism.

Therefore, alongside runtime, measure **allocation rate, GC, and peak memory** before deciding for large-data workloads.

## 10. Short-circuiting: `limit` and `findFirst` can differ in cost

An important scenario is when downstream only needs the first result:

~~~java
List<Integer> first = rows.stream()
        .flatMap(row -> row.values().stream())
        .limit(1)
        .toList();
~~~

With `flatMap`, the child Stream is a lazy source. Downstream consumption can stop after pulling enough elements, depending on contracts and execution.

The equivalent using `mapMulti`:

~~~java
List<Integer> first = rows.stream()
        .<Integer>mapMulti((row, emit) -> {
            for (Integer value : row.values()) {
                emit.accept(value);
            }
        })
        .limit(1)
        .toList();
~~~

The mapper receives a `Consumer<Integer>` that **cannot signal** that downstream has enough. If `row.values()` has millions of elements, you cannot write:

~~~java
if (!emit.accept(value)) {
    break;
}
~~~

because `Consumer.accept` returns `void`. An implementation may buffer all values emitted by the mapper for **one** input before downstream continues processing.

Key points to remember:

- Two pipelines can yield the **same result** yet differ significantly in how many child elements are created/traversed.
- Do not put side effects inside the mapper and assume `limit(1)` causes the mapper to touch exactly one child element.
- If emitting results is expensive or child sources are huge, try `flatMap` with a lazy child Stream first.
- If using `mapMulti` because you intentionally process an entire short group, callback and memory overhead may still fit well.

### Why not use `Gatherer` to replace every `mapMulti`?

`Gatherer.Downstream.push` (standard API since Java 24) has a `boolean` signal indicating whether downstream still wants more; `mapMulti`'s Consumer **lacks** this protocol. Gatherers fit problems needing complex short-circuiting/stateful windows, yet require a newer JDK and are unnecessary for simple flattening.

Do not change architecture or JDK versions just for a small microbenchmark; pick the API by **result contract and lifecycle**, then measure.

## 11. `mapMultiToInt`, `mapMultiToLong`, `mapMultiToDouble`: avoiding unnecessary boxing

When output is primitive numbers, compare the corresponding API pairs:

| Output | `flatMap` | `mapMulti` |
| --- | --- | --- |
| `Stream<R>` | `flatMap(...)` | `mapMulti(...)` |
| `IntStream` | `flatMapToInt(...)` | `mapMultiToInt(...)` |
| `LongStream` | `flatMapToLong(...)` | `mapMultiToLong(...)` |
| `DoubleStream` | `flatMapToDouble(...)` | `mapMultiToDouble(...)` |

Example summing quantities of valid lines:

~~~java
long totalUnitsFlat = orders.stream()
        .flatMapToInt(order -> order.items().stream()
                .filter(item -> item.quantity() > 0)
                .mapToInt(Item::quantity))
        .asLongStream()
        .sum();

long totalUnitsMulti = orders.stream()
        .mapMultiToInt((order, emit) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    emit.accept(item.quantity());
                }
            }
        })
        .asLongStream()
        .sum();
~~~

Both computations give the same sum when quantities are non-negative and totals stay within `long`. `asLongStream().sum()` accumulates in `long` instead of `IntStream.sum()`'s `int`, reducing overflow risk on large datasets (though not eliminating `long` overflow).

The fair comparison is **`flatMapToInt` vs. `mapMultiToInt`**. Comparing repeatedly boxed `Stream<Integer>` against `mapMultiToInt` skews benchmarks because it changes **two factors at once**: flattening style and boxing. When benchmarking, keep output pipeline types equivalent.

### Type inference in `mapMulti`

When the output type is not clearly inferred:

~~~java
List<String> result = orders.stream()
        .<String>mapMulti((order, emit) -> {
            for (Item item : order.items()) {
                emit.accept(item.sku());
            }
        })
        .toList();
~~~

The `<String>` type witness avoids cases where the compiler infers `Object` and fails assignment to `List<String>`. If the output is primitive numbers, the `mapMultiToInt/Long/Double` overloads fix the Stream type upfront, avoiding many type-inference and boxing issues.

## 12. Correctness before optimization: invariants to preserve

Replacing `flatMap` with `mapMulti` must preserve **semantics**:

1. **Output element count:** each input emits the exact required number of values.
2. **Values:** outputs are transformed/filtered under identical conditions.
3. **Order:** when the source has encounter order, values are emitted in the exact order required.
4. **Nulls:** null elements are kept or dropped under the exact same rules, never guessed.
5. **Exceptions:** parse and I/O errors are not turned into silently incomplete output.
6. **Resource lifecycle:** child Streams or readers must be closed.
7. **Parallelism:** mappers do not interfere with the source or share mutable state outside contracts.
8. **Short-circuiting:** do not rely on mapper invocation count/side effects as a business result.
9. **Output type:** `Stream<R>` and primitive streams use appropriate value ranges.

### Invariants for the order example

For each `Order`, let:

~~~text
valid(order) = items with quantity > 0
~~~

Then:

~~~text
flatten(orders).size()
    == total count of valid(item) across all orders

flatten(orders) preserves order and item order if source is ordered
every output string uses exact order.id and item.sku
~~~

Verification example:

~~~java
List<String> expected = usingFlatMap(orders);
List<String> actual = usingMapMulti(orders);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "flatMap/mapMulti mismatch\n"
            + "expected=" + expected
            + "\nactual=" + actual
    );
}
~~~

**Comparing one implementation against another does not prove either is right.** Pair it with a loop-based oracle so you catch cases where both pipelines share the same business bug.

## 13. A simple oracle to check fan-out and encounter order

An imperative loop, independent of both APIs under comparison:

~~~java
static List<String> reference(List<Order> orders) {
    List<String> result = new java.util.ArrayList<>();

    for (Order order : orders) {
        for (Item item : order.items()) {
            if (item.quantity() > 0) {
                result.add(
                        order.id() + ":" + item.sku());
            }
        }
    }

    return result;
}
~~~

You can check:

~~~java
List<String> expected = reference(orders);

if (!expected.equals(usingFlatMap(orders))
        || !expected.equals(usingMapMulti(orders))) {
    throw new AssertionError("Incorrect flatten result");
}
~~~

Your test suite should cover these cases:

| Test case | What matters |
| --- | --- |
| Empty order list | Empty result |
| Order with no items | Emits nothing |
| Order with only quantity = 0 items | Emits nothing |
| Order with one valid item | Emits one element |
| Order with multiple items | Emits multiple elements in order |
| Multiple orders sharing the same SKU | Does not deduplicate without `distinct` |
| Empty or null SKU | Follows defined input validation policy |
| Negative quantity | Filtered out if condition is `quantity > 0` |
| Increasing fan-out | Compare correctness, runtime, and allocations |
| Short-circuiting with `limit(1)` | Same result, while checking execution cost separately |
| Switching to parallel | Compare results per contract, not mapper scheduling |

Do not test only an order with a single item: that is the exact case that makes all styles look equivalent in both semantics and performance.

## 14. Parallelization and stateless mappers

Both `flatMap` and `mapMulti` are Stream **intermediate operations**. Their mappers must avoid modifying the source and avoid depending on shared mutable state.

**Unsafe pattern:**

~~~java
List<String> shared = new java.util.ArrayList<>();

orders.parallelStream()
        .forEach(order -> {
            for (Item item : order.items()) {
                shared.add(item.sku());
            }
        });
~~~

`ArrayList` is unsafe when multiple tasks write concurrently. Swapping to `synchronizedList` can prevent some race conditions, yet still fails to preserve encounter order while adding contention.

**Safer pattern:**

~~~java
List<String> result = orders.parallelStream()
        .<String>mapMulti((order, emit) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    emit.accept(item.sku());
                }
            }
        })
        .toList();
~~~

Each mapper only reads `order.items()` and emits values into the Stream API-provided Consumer. With an ordered `List` and terminal `toList()`, output preserves encounter order by contract. However, there is **no** guarantee the mapper runs sequentially or on any specific thread.

Never keep the `emit` Consumer outside the callback to call from another thread, and never put side effects in the mapper expecting them to run once under short-circuiting.

### Parallel does not automatically mean faster

When per-element work is just a tiny loop and an addition, `Spliterator` splitting, task scheduling, and result merging overhead can outweigh parallel gains. When benchmarking `flatMap` and `mapMulti`, default to comparing **sequential vs. sequential**, then run a separate benchmark for **parallel vs. parallel**, rather than mixing two axes of change in one comparison.

## 15. Designing a fair benchmark

To decide based on measurements, control independent variables.

### 15.1. Variables to hold constant

- **Identical input data:** record count, sub-list sizes, emitted element counts, and ordering.
- **Identical filtering/mapping:** each record produces the exact same numbers in both pipelines.
- **Identical output type:** compare `flatMapToInt` with `mapMultiToInt`, or `flatMap` with `mapMulti`.
- **Identical terminal operation:** e.g., both compute `asLongStream().sum()`.
- **Identical parallelism:** do not compare sequential `flatMap` against parallel `mapMulti`.
- **Identical JIT/GC conditions:** warm up, run multiple iterations and multiple forks as needed.
- **Exclude input generation from timing** unless intentionally measuring it.
- **Prevent dead-code elimination:** benchmark outputs must be consumed by the harness or a Blackhole.

If a benchmark only times creating a `Stream` **without a terminal operation**, most of the pipeline never runs due to laziness. Such a measurement does not reflect actual `flatMap`/`mapMulti` cost.

### 15.2. Data profiles to test

| Parameter | Suggested values | Purpose |
| --- | --- | --- |
| Input count | 1,000; 100,000; larger if relevant | Inspect overhead vs. source size |
| Fan-out | 0; 1; 4; 16; 100+ | Distinguish empty/small/large cases |
| Fan-out skew | Uniform; mostly empty; a few huge records | Match real-world distributions |
| Data type | `int`, `long`, objects | Inspect boxing effects |
| Downstream | `sum`, `toList`, `limit(1)` | Compare aggregation vs. short-circuiting |
| Source | `ArrayList`, Iterator-backed, I/O Stream | Observe Spliterator and resource impact |
| Mode | Sequential; parallel separately | Do not conflate algorithm with concurrency |

**Important:** Never pick a fan-out configuration favorable to your preferred API and treat it as universal proof. Benchmark setups must mirror **production data distributions**.

## 16. JMH example: `flatMapToInt` vs. `mapMultiToInt`

**JMH** (*Java Microbenchmark Harness*) is the standard tool for JVM microbenchmarking. The example below shows how to structure a measurement; JMH is an external library outside the JDK, so configure dependencies and annotation processors in your project before running. This lesson **claims no speed results** without actually running the benchmark.

Note that the standalone benchmark below requires Java 17+ and JMH configured:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 4)
@Measurement(iterations = 6)
@Fork(2)
public class FlatMapMapMultiBenchmark {

    record Row(List<Integer> values) {}

    @State(Scope.Thread)
    public static class Data {
        @Param({"1000", "100000"})
        public int rows;

        @Param({"0", "1", "4", "16"})
        public int fanOut;

        List<Row> input;

        @Setup(Level.Trial)
        public void setup() {
            List<Row> rowsData = new ArrayList<>(rows);

            for (int i = 0; i < rows; i++) {
                List<Integer> values =
                        new ArrayList<>(fanOut);

                for (int j = 0; j < fanOut; j++) {
                    values.add((i + j) & 1023);
                }

                rowsData.add(new Row(List.copyOf(values)));
            }

            input = List.copyOf(rowsData);
        }
    }

    @Benchmark
    public long usingFlatMapToInt(Data data) {
        return data.input.stream()
                .flatMapToInt(row ->
                        row.values().stream()
                                .mapToInt(Integer::intValue))
                .asLongStream()
                .sum();
    }

    @Benchmark
    public long usingMapMultiToInt(Data data) {
        return data.input.stream()
                .mapMultiToInt((row, emit) -> {
                    for (int value : row.values()) {
                        emit.accept(value);
                    }
                })
                .asLongStream()
                .sum();
    }
}
~~~

Both benchmarks:

- Use the exact **same data** from `Data.input`.
- Emit the exact **same integer sequence** per `Row`.
- Create an `IntStream`, widen to `LongStream`, and sum to avoid `int` overflow on large datasets.
- Include the terminal operation `sum()`, so they do not merely time building an unexecuted pipeline.
- Exclude input generation from `@Benchmark` methods.
- Test multiple fan-out configurations with warmup, multiple measurements, and multiple forks.

When running JMH for real, also verify the **checksum value** of both variants in an independent test; fast timing means nothing if the two benchmarks compute different answers.

### Reading JMH results

An illustrative observation guide, **not real measured numbers**:

| Configuration | What to observe | Valid conclusion |
| --- | --- | --- |
| Fan-out = 0 | Cost of processing inputs that emit nothing | One approach may have less overhead on empty cases |
| Fan-out = 1 | Cost of tiny child Stream vs. Consumer | One approach may allocate fewer objects on a given JDK |
| Fan-out = 16 | Cost of iterating many child elements | Results can flip |
| Very large fan-out | Allocations, GC, memory peak, and cancellation | Do not look only at average time |
| `limit(1)` after flattening | Does child emission actually stop early? | Identical semantics do not mean identical cost |

Never invent speedup percentages before running measurements. Results that look great on a dev laptop may not repeat on a server with a different JDK, heap, CPU, or data profile.

### Measuring allocations and GC

Depending on your JMH setup, use an appropriate profiler (such as JMH's GC/allocation profilers) to inspect:

- Bytes allocated per operation.
- GC count and cost.
- Mean time, variance, and worst-case behavior.
- Peak heap if fan-out produces many elements.
- Stability across multiple forks and datasets.

**Fewer allocations** do not always mean **lower runtime**, and faster average time does not always mean lower tail latency or higher system throughput.

## 17. Measure the whole pipeline, not just flattening

Sometimes the difference between `flatMap` and `mapMulti` is tiny relative to other steps:

~~~text
Data source -> parse JSON -> validate -> flatMap/mapMulti
            -> groupingBy -> write to database
~~~

If file reading, JSON parsing, or database writes dominate runtime, optimizing child Stream creation overhead may be negligible for end-to-end latency.

Separate **two measurement levels**:

1. **Microbenchmark:** isolate flattening to understand fan-out and allocation behavior.
2. **Integration benchmark:** measure end-to-end on realistic data including parsing, filtering, collectors, I/O, GC, and response time.

Measurements might show `mapMulti` winning in a microbenchmark while the real application pipeline shows no meaningful gain. In that case, keeping readable `flatMap` can be the better choice.

Conversely, if a pipeline processes tens of millions of elements with many 0/1-element child Streams and flattening consumes substantial CPU/allocations, consistent measurements can justify `mapMulti`.

## 18. Practical decision matrix

| Condition | What to try first | Reason |
| --- | --- | --- |
| Always 1 input to 1 output | `map` | Right model, simplest |
| Only filtering elements | `filter` | No one-to-many needed |
| Nullable values to drop | `map + filter`, `ofNullable + flatMap`, or `mapMulti` | Pick readable option, measure if hot |
| Already have `Optional` | `flatMap(Optional::stream)` or `mapMulti` | Both express 0/1 |
| Child is already a lazy `Stream` | `flatMap` | Preserves natural child Stream chaining |
| Child is a small collection, very many inputs | `mapMulti` is a candidate to try | Can avoid tiny child Streams; verify by measuring |
| One input emits very many elements | Try `flatMap` with lazy child Stream | Watch buffering, short-circuiting, and memory |
| Downstream often uses `limit`/`findFirst` | Try `flatMap` first and benchmark cancellation | `mapMulti` receives no stop signal via Consumer |
| Child source owns I/O | `flatMap` or explicit `try-with-resources` | Must control `close()` |
| Primitive output | Compare `flatMapToInt` with `mapMultiToInt` | Same types, avoids mismatched boxing comparison |
| Codebase targets Java 8/11 | `flatMap` | `mapMulti` is unavailable in target API |
| Encounter order must be kept | Either, if mapper emits in order | Never depend on thread execution order |
| Only aggregate needed, not full list | Appropriate terminal `sum`, `reduce`, `collect` | Avoid unnecessary `toList` |

**Priority order:**

- **Semantic correctness first.**
- **Simplicity and maintainability next.**
- **Performance by measurement last.**

There is no obligation to rewrite every `flatMap` to `mapMulti` when upgrading the JDK. Code that is correct, readable, and not a performance bottleneck can stay as is.

## 19. Common traps

| Trap | Consequence | Fix |
| --- | --- | --- |
| Assuming `mapMulti` is always “zero allocation” | Misjudges memory and GC | Check JDK, JIT, profiler, and data |
| Assuming `Consumer.accept` returns a stop signal | Invalid short-circuit logic | Understand `accept` returns `void`; consider `flatMap`/Gatherer as appropriate |
| Creating a child Stream inside `mapMulti` and draining it | Complex code, may lose laziness | Use `flatMap` if child source is already a Stream |
| Forgetting to `close` `Files.lines` | Resource leak | Use `try-with-resources` and/or `flatMap` properly |
| Benchmarking only 1-element fan-out | Does not represent real fan-out | Measure multiple distributions and sizes |
| Using `count()` and assuming all mappers ran | Optimizations may skip stages depending on source/pipeline | Benchmarks must execute transforms and verify correctness; `sum` is an option |
| Comparing boxed Stream against primitive Stream | False conclusions about flattening API | Compare identical types and identical work |
| Relying on execution order in `parallel()` | Flaky tests, broken side effects | Test only specified encounter order/results |
| Saving `emit` to call after callback returns | Violates Consumer scope | Call only inside the provided mapper |
| Putting side-effecting mappers in benchmarks | Hard to reason about and reproduce | Use pure functions and immutable fixtures |
| Huge `toList` output | Memory scales with total output | Use bounded aggregation/streaming writes if suitable |
| Seeing one fast benchmark and rewriting everything | Adds risk without system-wide gain | Profile bottlenecks, re-measure before/after on real pipeline |

## 20. Practice exercises

### Exercise 1 — Predict the output

~~~java
List<Integer> result = List.of(
        List.of(1, 2),
        List.<Integer>of(),
        List.of(3)
).stream().<Integer>mapMulti((list, emit) -> {
    for (Integer n : list) {
        emit.accept(n * 2);
    }
}).toList();
~~~

**Answer:** `[2, 4, 6]`. The empty sublist emits 0 elements; the others emit 2 and 1 elements respectively.

### Exercise 2 — Write the equivalent `flatMap`

Rewrite the `mapMulti` in Exercise 1 using `flatMap`.

**Hint/answer:**

~~~java
List<Integer> result = List.of(
        List.of(1, 2),
        List.<Integer>of(),
        List.of(3)
).stream()
        .flatMap(list -> list.stream().map(n -> n * 2))
        .toList();
~~~

With lists that have encounter order, both approaches yield the same elements and order.

### Exercise 3 — Choosing an API when the child source is already a Stream

A service returns a lazy `Stream<LogLine>` per day. Downstream only needs one matching line. Which API should you try first?

**Answer:** `flatMap` is usually more suitable because it flattens lazy child Streams and closes them under contract, favoring short-circuiting. Still use `try-with-resources` for any owned outer I/O source and measure actual cost.

### Exercise 4 — Why does `mapMulti` have no stop callback?

Can you write `if (!emit.accept(value)) break;`?

**Answer:** No. `emit` is a `Consumer<R>`, so `accept` returns `void`. `mapMulti` has no boolean downstream rejection signal; when a mapper can emit very many outputs, watch buffering and short-circuiting.

### Exercise 5 — One-to-one case

A pipeline uppercases `name` and always returns exactly one name. Should you use `flatMap` or `mapMulti`?

**Answer:** Use `map(String::toUpperCase)`. You do not need a one-to-many model, so do not add flattening cost or complexity.

### Exercise 6 — Checking memory

Why is `mapMulti` where a single input emits one million values not guaranteed to use `O(1)` memory?

**Answer:** The specification allows default implementations to accumulate a mapper's emissions in an internal buffer before creating a Stream for downstream. You must inspect the JDK implementation and allocation/peak heap measurements, especially when downstream uses `limit`.

### Exercise 7 — Making a fair benchmark

A benchmark compares `Stream<Integer>.flatMap(...)` against `Stream<T>.mapMultiToInt(...)` and concludes `mapMulti` is many times faster. What is unfair?

**Answer:** The two variants have different output types: one boxes objects while the other uses primitives. You must compare `flatMapToInt` with `mapMultiToInt`, keeping data, transformations, and terminal operation identical before drawing conclusions.

### Exercise 8 — Fan-out and element count

There are 100 orders, averaging four valid items per order, and all orders have complete data. How many outputs do `flatMap` and `mapMulti` produce?

**Answer:** By assumption, roughly 400 outputs if the average of four valid items holds across all 100 orders. Both APIs must produce the exact same element count for identical emission logic; a difference in output is a semantic bug, not a valid optimization.

### Exercise 9 — Parallelism and the consumer

Can you store `emit` in a list and use your own executor to invoke it after `mapMulti` finishes?

**Answer:** No. The supplied Consumer is valid only for the duration of the mapper call, not as an application-owned asynchronous push channel. Use a different design if concurrency like that is required.

### Exercise 10 — Deciding when benchmarks show no difference

If `flatMap` and `mapMulti` produce identical results and runtime/GC metrics show no meaningful difference on the real workload, which should you choose?

**Answer:** Choose the version that is easier to read, maintain, and matches the source's contract. If the child source is already a Stream, `flatMap` is usually clearer; if emitting a few conditional values, `mapMulti` can be more concise. Do not optimize based on an assumption unconfirmed by data.

## 21. Key takeaways

- `flatMap` requires the mapper to return a **child Stream**; `mapMulti` lets the mapper emit **0, 1, or more** elements via `Consumer.accept`.
- `mapMulti` and its primitive variants appeared in **Java 16**; `flatMap` dates from Java 8.
- With many inputs each producing very few outputs, `mapMulti` **can** reduce overhead, yet is **not guaranteed** to be faster than `flatMap`.
- The Javadoc permits `mapMulti` to be implemented via an **internal buffer and `flatMap`**; do not claim `O(1)` memory or zero allocation.
- `mapMulti`'s Consumer returns `void` and **does not propagate a stop signal** like `Gatherer.Downstream.push`. For long child sources or short-circuiting downstreams, consider lazy `flatMap` and measure in practice.
- When child sources are already Streams or own I/O resources, **ownership and closing** are decisive factors, not code brevity alone.
- Use `mapMultiToInt/Long/Double` and `flatMapToInt/Long/Double` to compare matching primitive types and avoid skew from boxing.
- Keep mappers stateless, non-interfering, and never retain the Consumer past the callback; parallel does not mean faster by default.
- **Verify equivalence with an oracle and edge cases**, then benchmark identical data, fan-out, terminal operation, and JVM using JMH or appropriate tooling.
- When differences are negligible in the real pipeline, **prefer clarity and maintainability**.

**Main point:** Choosing between `flatMap` and `mapMulti` is not a trick of swapping method names. Look at **the shape of the child data, how many outputs each input emits, and whether short-circuiting or resource closing is needed**, verify results first, and measure performance on a representative workload. An optimization worth keeping is one that is **both semantically correct and measurably beneficial**.
