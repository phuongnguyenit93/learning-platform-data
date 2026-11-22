# Distinguishing Gatherer from map, mapMulti, and Collector

When designing a Java Stream pipeline, four tools that are often placed side by side are `map`, `mapMulti`, **Stream Gatherer**, and **Collector**. They all participate in transforming or aggregating data, yet **they do not do the same thing**. Choosing the wrong tool can make code unnecessarily complex, lose elements, break ordering, share state unsafely, or return a result shape that does not fit the requirement.

Key points to keep in mind from the start:

- **`map`**: each input element produces **one output element** via a mapping function.
- **`mapMulti`**: each input element can emit **0, 1, or many output elements** through a consumer; typically used when there is no need to maintain state across input elements.
- **`gather` with `Gatherer`**: an extensible intermediate operation; it can emit 0..n elements, **hold private state**, decide when to stop integrating, and perform a finalization step.
- **`collect` with `Collector`**: a terminal operation to **accumulate inputs into a single final result**, such as a `List`, `Map`, summary metrics, or a DTO.

This lesson belongs to the **Stream Gatherer** chapter of the **JAVA_STREAM_API** module, where learners have already encountered lazy pipelines, `filter`, `map`, `reduce`, and `collect`, as well as grouping, custom collectors, `Spliterator`, and parallel processing. We will distinguish these tools by **result shape, state usage, laziness, ordering, short-circuiting, and parallel contract**, then implement a complete Java 24 example and practice exercises.

## 1. JDK availability and pipeline position of each API

| API | Available since JDK | Role | Result shape |
|---|---:|---|---|
| `Stream.map(Function)` | Java 8 | *Intermediate operation* | `Stream<R>` |
| `Stream.mapMulti(BiConsumer)` | Java 16 | *Intermediate operation* | `Stream<R>` |
| `Stream.gather(Gatherer)` | Java 24 official | *Intermediate operation* | `Stream<R>` |
| `Stream.collect(Collector)` | Java 8 | *Terminal operation* | `R`, usually not a Stream |

Stream Gatherers appeared as a **preview** in Java 22 and Java 23, then became an official feature in **Java 24**. The examples using `Gatherer` in this lesson target **JDK 24 and later**. You cannot copy them verbatim into a Java 8, 11, 17, or 21 project and expect them to compile.

### 1.1. Intermediate operations vs. terminal operations

`map`, `mapMulti`, and `gather` all return **a new Stream** so additional steps can be chained:

```java
List<String> result = source
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .toList();
```

Here, `map` and `filter` describe the pipeline. `toList()` is the **terminal operation** that triggers execution and returns a list.

Conversely:

```java
Map<String, Long> counts = source
        .collect(Collectors.groupingBy(
                s -> s.substring(0, 1),
                Collectors.counting()));
```

`collect` terminates the pipeline and returns a `Map`. If you want to continue using Stream operations on its entries, you must create a **new** Stream from `counts.entrySet()`, rather than chaining `.filter(...)` directly onto the `Map`.

### 1.2. A short decision table

| Business question | Tool to consider first |
|---|---|
| "Convert `Order` to order ID?" | `map` |
| "An order has multiple lines; emit each line?" | `flatMap` or `mapMulti` |
| "Need a sequence number or cumulative total after **each line**?" | Stateful `Gatherer` |
| "Split consecutive lines into windows?" | `Gatherers.windowFixed` or a custom Gatherer |
| "Stop the Gatherer based on an internal rule?" | `Gatherer.Integrator` with a `boolean` signal |
| "Need the **final** total revenue by SKU?" | `collect(groupingBy(...))` or `toMap` |
| "Need count, min, max, and average of a numeric field?" | `summarizingInt`/`summarizingLong` |
| "Need a multi-metric report when the pipeline finishes?" | Custom `Collector` or `Collectors.teeing` |

**No single tool is always better than the others.** The right choice is the simplest tool that expresses **the right number of outputs, the right emission timing, and the right state to retain**.

## 2. map: one element to one element

Core signature:

```java
<R> Stream<R> map(
        Function<? super T, ? extends R> mapper);
```

For each element `T` actually processed by the pipeline, the mapper returns **one `R` value**. That value may be a complex object, a collection, or even `null`; `map` **does not automatically remove nulls** or flatten collections.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> words = Arrays.asList(" java ", "stream", " api ");

List<String> cleaned = words.stream()
        .map(String::trim)
        .collect(Collectors.toList());

System.out.println(cleaned); // [java, stream, api]
```

Each input string produces **one string** in the result. If an order has a list of item lines:

```java
Stream<List<OrderLine>> nested = orders.stream()
        .map(Order::getLines);
```

The result is still `Stream<List<OrderLine>>`: one output element is **the entire sublist**. `map` is not responsible for concatenating those lists into a single Stream of order lines.

### 2.1. When not to write a stateful map

An incorrect pattern is keeping a shared counter outside the mapper:

```java
int[] counter = {0};

List<String> numbered = words.parallelStream()
        .map(word -> (++counter[0]) + ":" + word)
        .collect(Collectors.toList());
// WRONG: mutable array is shared across workers.
```

This bug has two layers:

1. `map` is designed for **non-interfering** and normally **stateless** functions; an external counter turns the mapping into an order-dependent, stateful operation.
2. When the Stream runs in parallel, updating `counter[0]` causes a **data race**; sequence numbers can be duplicated, lost, or fail to match encounter order.

If you only need **positional numbering for a List**, you can use `IntStream.range(0, list.size())`. If you need a general stateful transformation across a sequence of elements, a **sequential Gatherer** expresses the intent much more clearly.

## 3. mapMulti: emitting multiple elements without creating sub-streams

`Stream.mapMulti` was introduced in **Java 16**. General signature:

```java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper);
```

The mapper receives:

- An input element of type `T`.
- A `Consumer<R>` (named `emit` in the example) to emit output values.

The mapper may call `emit.accept(...)` **zero times, once, or many times**:

```java
List<Integer> values = List.of(1, 2, 3);

List<Integer> output = values.stream()
        .<Integer>mapMulti((n, emit) -> {
            if (n % 2 != 0) {
                emit.accept(n);
                emit.accept(n * 10);
            }
        })
        .toList();

System.out.println(output); // [1, 10, 3, 30]
```

The number `2` emits no elements; each odd number emits two results. This is something `map` cannot do directly because `map` maps each input element to **one value**.

### 3.1. Comparison with flatMap

`flatMap` since Java 8 can solve the same problem by returning a **sub-stream**:

```java
List<Integer> output = List.of(1, 2, 3).stream()
        .flatMap(n -> n % 2 == 0
                ? Stream.<Integer>empty()
                : Stream.of(n, n * 10))
        .toList();
// [1, 10, 3, 30]
```

In `mapMulti`, the mapper emits directly through `emit.accept`; in `flatMap`, the mapper returns `Stream<R>`. `mapMulti` can avoid creating a sub-stream for every element, which is especially useful when each input produces only a few child elements. However, **you must not assume `mapMulti` is always faster**; measure the actual cost.

### 3.2. Limitations of mapMulti

`mapMulti` is well-suited when processing **each element independently** and emitting 0..n values. It does not natively provide:

- An `initializer` to create state for the entire transformation pass.
- A `finisher` to push remaining buffered data when the source ends.
- An `Integrator` returning a signal to stop integration according to the transformation's rules.
- A `combiner` to describe how to merge state when parallel integration is allowed.

One could try storing state outside the callback, but doing so makes the program depend on ordering/scheduling and easily violates Stream's statelessness requirements. When the problem genuinely **links consecutive elements**, `Gatherer` is the choice with the clearer contract.

## 4. Gatherer: an intermediate transformation capable of holding state

The `Gatherer<T, A, R>` interface describes:

- **`T`**: input element type.
- **`A`**: accumulated state type, typically mutable across steps.
- **`R`**: output element type emitted to the downstream pipeline.

At a conceptual level:

```text
Stream<T>
    |
    v
 Gatherer initializer ---> state A
    |
    v
 integrator(A, T, downstream)
    |      |
    |      +-- may push 0..n R elements
    |      +-- may return true / false to continue / stop
    |
    v
 finisher(A, downstream)  [if needed]
    |
    v
Stream<R> ---> subsequent map/filter/limit/collect/...
```

Unlike `Collector`, a Gatherer stays **in the middle of the pipeline**. For example:

```java
List<RunningTotal> totals = transactions.stream()
        .gather(runningTotals())
        .filter(total -> total.amountCents() > 0)
        .toList();
```

This snippet assumes the `RunningTotal` type and the `runningTotals()` Gatherer are already defined; the complete self-contained runnable code is in section 7.

### 4.1. Key parts

| Part | Meaning | How does it differ from `mapMulti`? |
|---|---|---|
| `initializer` | Creates state `A` for the integration process | `mapMulti` does not have this parameter |
| `integrator` | Receives state, source element, and downstream | Can rely on state across elements |
| `downstream.push(R)` | Emits an element to the next pipeline stage | Returns `boolean`, indicating whether output is still accepted |
| `integrator` returning `boolean` | Indicates whether to continue integrating inputs | Has its own stopping protocol |
| `finisher` | Uses final state to emit more if needed | `mapMulti` has no finalization step |
| `combiner` | Strategy for merging state in parallel-capable Gatherers | Not every Gatherer needs or has a combiner |

Not every Gatherer is required to have state or a finisher. For stateless transformations, overloads without state exist, though when `map` or `mapMulti` is sufficient, adding a Gatherer usually makes the code harder to read.

### 4.2. Gatherer creation variants

Example of a **stateful sequential** Gatherer:

```java
Gatherer<T, State, R> gatherer = Gatherer.ofSequential(
        State::new,
        (state, value, downstream) -> {
            // Update state.
            // May call downstream.push(output).
            return true;
        });
```

Example of a **sequential Gatherer with a finisher**:

```java
Gatherer<T, State, R> gatherer = Gatherer.ofSequential(
        State::new,
        (state, value, downstream) -> {
            // Accumulate, may emit output.
            return true;
        },
        (state, downstream) -> {
            // Emit remaining data upon completion if needed.
        });
```

These are signature templates, not runnable programs since `T`, `State`, `R`, and the integration rules have not been defined yet. Use them when designing a concrete Gatherer, rather than attaching shared mutable state outside the Stream.

### 4.3. push(false) and return false do not mean "filter out"

With an integrator:

```java
(state, value, downstream) -> {
    if (!isValid(value)) {
        return true; // Skip element, continue processing remaining inputs.
    }
    return downstream.push(transform(value));
}
```

- Not calling `push` means **emitting no output for this element**.
- Returning `true` means **continuing integration** if downstream still demands elements.
- Returning `false` means **the Gatherer wants to stop integrating inputs**.
- `downstream.push(...)` returns `false` when downstream rejects further output; propagate the stop signal when appropriate.

Do not use `return false` merely to skip an invalid element. Doing so drops all valid elements that follow it.

## 5. Collector: focused on a single final result

`Collector<T, A, R>` describes a *mutable reduction* from `T` elements through state `A` into **a final result `R`**.

```java
Map<String, Long> revenueBySku = lines.stream()
        .collect(Collectors.groupingBy(
                LineView::sku,
                Collectors.summingLong(LineView::amountCents)));
```

`collect` consumes the pipeline and returns `Map<String, Long>`. It **does not emit an intermediate Stream of results after each `LineView`** for downstream Stream operations to filter by cumulative total.

### 5.1. Five components of a Collector

| Component | Function |
|---|---|
| `supplier` | Creates a new accumulator container |
| `accumulator` | Updates the container upon receiving an element |
| `combiner` | Merges two containers, especially when the framework splits work |
| `finisher` | Transforms the container into the final result |
| `characteristics` | Describes `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` |

Gatherers also have initializer/integrator/finisher, yet **you should not mechanically equate similarly named pairs**:

- `Collector.accumulator` receives elements to build one reduced result; it has no downstream to `push` individual output elements to.
- `Gatherer.integrator` can emit **multiple outputs right during traversal**, can short-circuit, and those outputs continue flowing through subsequent intermediate operations.
- `Collector.finisher` produces the final `R` result of terminal `collect`; `Gatherer.finisher` can **emit additional Stream elements**.
- A Gatherer created with `ofSequential` does not need a combiner for parallel integration; a valid Collector must have a `combiner` by contract even if the application currently runs mostly sequentially.

### 5.2. Where do Gatherer.fold and Collector look similar?

Some standard Gatherers, such as `Gatherers.fold`, can reduce multiple elements into a single value and emit that value into the Stream. In terms of **data produced**, it can look close to a reduction/collector; in terms of **pipeline position**, it remains an intermediate operation:

```java
// Conceptual sketch:
source.gather(foldingGatherer)
      .map(this::formatSummary)
      .toList();

// Whereas collect ends the pipeline:
Summary summary = source.collect(summaryCollector);
```

The two lines represent two independent approaches, each needing a fresh Stream source; `foldingGatherer`, `Summary`, and `summaryCollector` are placeholder types/values. Choose `collect` when the business requirement only needs the final result; choose Gatherer when the result needs to **continue flowing through Stream steps** or requires a complex integration/emission protocol.

## 6. Full comparison table of the four tools

| Criterion | `map` | `mapMulti` | `Gatherer` | `Collector` |
|---|---|---|---|---|
| Step in pipeline | Intermediate | Intermediate | Intermediate | Terminal |
| Outputs per input element | Exactly one value | 0..n values | 0..n values, state-dependent | Accumulates, does not emit an intermediate Stream |
| Call return type | `Stream<R>` | `Stream<R>` | `Stream<R>` | `R` |
| Local state living across inputs | Not a provided model | Not a provided model | Can have private `A` | Has accumulator state `A` |
| Finalization step to emit extra elements | No | No | Optional | Finisher returns a single final result |
| Dedicated integration stop signal | No | No | Yes, `boolean` from integrator | Not part of collector protocol |
| Can chain `filter/map/limit` directly afterward | Yes | Yes | Yes | No, because the Stream has ended |
| In parallel | Function normally must be stateless/non-interfering | Callback normally must be stateless/non-interfering | Depends on Gatherer design and combiner | Depends on supplier/accumulator/combiner contract |
| When to prefer | Simple 1:1 transformation | Emitting 0..n from an independent input | Stateful transformations, windows, emit-on-finish, rule-based stopping | Final aggregation, grouping, reports |

**Be careful with the phrase "0..n":** it does not mean a pipeline will always emit every expected element if `limit`, `findFirst`, or another short-circuiting terminal operation follows. Streams can stop early; Gatherers also have their own stopping protocol. Test against **the output contract** rather than using lambda invocation counts as a business metric.

## 7. Complete Java 24 example: map, mapMulti, Gatherer, and Collector on the same data

Problem: given a list of orders, each containing multiple detail lines. We need:

1. **`map`** to extract each order's ID.
2. **`mapMulti`** to emit detail lines paired with the order ID, omitting orders with no items.
3. **`Gatherer`** to emit **cumulative revenue after each line**, along with a line sequence number.
4. **`Collector`** to produce a final report with line count, total units, and total revenue.
5. Use `groupingBy` to compute revenue by SKU.

Save the entire code below as `GathererComparisonDemo.java`. The example uses `record`s and `Stream.toList()`, matching the **JDK 24+** requirement of `Gatherer`.

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Gatherer;

public class GathererComparisonDemo {

    record Item(String sku, int quantity, long unitPriceCents) {
        Item {
            if (sku == null || sku.isEmpty()) {
                throw new IllegalArgumentException("Invalid sku");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("Invalid quantity/unitPrice");
            }
        }
    }

    record Order(String id, List<Item> items) {
        Order {
            if (id == null || items == null) {
                throw new IllegalArgumentException("Invalid Order");
            }
            items = List.copyOf(items);
        }
    }

    record LineView(
            String orderId,
            String sku,
            long quantity,
            long amountCents) {}

    record RunningTotal(
            long lineNumber,
            long amountCents) {}

    record Report(
            long lineCount,
            long units,
            long revenueCents) {}

    // A: dedicated state for the Gatherer.
    static final class RunningState {
        long lineNumber;
        long amountCents;
    }

    // Stateful intermediate Gatherer; emits one snapshot per line.
    static Gatherer<LineView, RunningState, RunningTotal>
            runningTotals() {
        return Gatherer.ofSequential(
                RunningState::new,
                (state, line, downstream) -> {
                    state.lineNumber = Math.addExact(
                            state.lineNumber, 1L);
                    state.amountCents = Math.addExact(
                            state.amountCents, line.amountCents());
                    return downstream.push(new RunningTotal(
                            state.lineNumber, state.amountCents));
                });
    }

    // Terminal Collector; returns a single Report.
    static Collector<LineView, long[], Report>
            reportCollector() {
        return Collector.of(
                () -> new long[3],
                (state, line) -> {
                    state[0] = Math.addExact(state[0], 1L);
                    state[1] = Math.addExact(
                            state[1], line.quantity());
                    state[2] = Math.addExact(
                            state[2], line.amountCents());
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] = Math.addExact(left[i], right[i]);
                    }
                    return left;
                },
                state -> new Report(
                        state[0], state[1], state[2]));
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("D01", List.of(
                        new Item("P01", 2, 100L),
                        new Item("P02", 1, 50L))),
                new Order("D02", List.of(
                        new Item("P01", 3, 100L))),
                new Order("D03", List.of())
        );

        // 1) map: each order produces exactly one order ID.
        List<String> orderIds = orders.stream()
                .map(Order::id)
                .toList();
        System.out.println(orderIds);
        // [D01, D02, D03]

        // 2) mapMulti: each order emits 0..n LineViews.
        List<LineView> lines = orders.stream()
                .<LineView>mapMulti((order, emit) -> {
                    for (Item item : order.items()) {
                        long amount = Math.multiplyExact(
                                (long) item.quantity(),
                                item.unitPriceCents());
                        emit.accept(new LineView(
                                order.id(), item.sku(),
                                item.quantity(), amount));
                    }
                })
                .toList();

        System.out.println(lines.size()); // 3
        // D01 emits 2 lines; D02 emits 1 line; D03 emits 0 lines.

        // 3) Gatherer: emits total revenue after each line.
        List<RunningTotal> running = lines.stream()
                .gather(runningTotals())
                .toList();

        System.out.println(running);
        // [RunningTotal[lineNumber=1, amountCents=200],
        //  RunningTotal[lineNumber=2, amountCents=250],
        //  RunningTotal[lineNumber=3, amountCents=550]]

        // 4) Collector: returns only a single final result.
        Report report = lines.stream()
                .collect(reportCollector());

        System.out.println(report);
        // Report[lineCount=3, units=6, revenueCents=550]

        // 5) A built-in Collector to group by SKU.
        Map<String, Long> revenueBySku = lines.stream()
                .collect(Collectors.groupingBy(
                        LineView::sku,
                        TreeMap::new,
                        Collectors.summingLong(
                                LineView::amountCents)));

        System.out.println(revenueBySku);
        // {P01=500, P02=50}

        // 6) Gatherer is an intermediate operation, so further filtering is possible.
        List<RunningTotal> overTwoHundred = lines.stream()
                .gather(runningTotals())
                .filter(total -> total.amountCents() > 200)
                .toList();

        System.out.println(overTwoHundred);
        // [RunningTotal[lineNumber=2, amountCents=250],
        //  RunningTotal[lineNumber=3, amountCents=550]]
    }
}
```

### 7.1. Result analysis

| Step | Input element count | Output count | Core behavior |
|---|---:|---:|---|
| `orders.stream().map(Order::id)` | 3 orders | 3 order IDs | **1:1**, still keeps D03 |
| `orders.stream().mapMulti(...)` | 3 orders | 3 detail lines | **0..n**, D03 produces no lines |
| `lines.stream().gather(runningTotals())` | 3 lines | 3 snapshots | Line 1: 200; line 2: 250; line 3: 550 |
| `lines.stream().collect(reportCollector())` | 3 lines | One `Report` | 3 lines, 6 units, 550 cents |
| `groupingBy(..., summingLong(...))` | 3 lines | One `Map` | P01: 500, P02: 50 |

To achieve **cumulative revenue**, the Gatherer must know the total amount from **previous** lines. `mapMulti` can emit the detail lines of each order, but you must not use an external `sum` variable outside the callback to fake cross-element state. In the Collector, we only need the final report, so there is no need to build a list of snapshots and take the last element.

### 7.2. Why use Math.multiplyExact and Math.addExact?

`quantity × unitPriceCents` can exceed the `long` range if the numbers are large. The example guards multiplication with `Math.multiplyExact`; both the Gatherer and Collector use `Math.addExact` to detect sum overflow. If arithmetic exceeds the `long` range, the program throws `ArithmeticException` instead of silently producing a wrong report.

For real-world monetary problems, you must also define currency units, discount policies, refunds, and currency conversions. The example intentionally uses integer cents to avoid `double` precision errors; it does not imply all monetary data can be safely represented with `long`.

### 7.3. Why create a new Stream for each operation?

A `Stream` object can only be consumed once. `orders` and `lines` are `List`s that can be traversed again, so we call a fresh `stream()` for each check. You must not call `collect` and then reuse `map` on the already-consumed Stream.

## 8. Gatherer with finisher example: collapsing consecutive elements

Some problems not only require state after each line, but also need to **emit held data when the input ends**. For example, suppose we want to compress a sequence of elements into "runs" of consecutive identical values:

```text
Input:  A, A, B, B, B, A
Output: A:2, B:3, A:1
```

If you only use `groupingBy` to count by key, the result is `{A=3, B=3}` and **cannot represent two separate runs of A**. If you use regular `mapMulti`, each element is not provided state to remember the current run. A stateful sequential Gatherer with a finisher expresses the problem accurately.

### 8.1. Java 24 code

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class ConsecutiveRunsDemo {

    static final class RunState {
        String current;
        long count;
    }

    static Gatherer<String, RunState, String> consecutiveRuns() {
        return Gatherer.ofSequential(
                RunState::new,
                (state, value, downstream) -> {
                    if (state.current == null) {
                        state.current = value;
                        state.count = 1L;
                        return true;
                    }

                    if (state.current.equals(value)) {
                        state.count++;
                        return true;
                    }

                    String completed =
                            state.current + ":" + state.count;
                    state.current = value;
                    state.count = 1L;

                    return downstream.push(completed);
                },
                (state, downstream) -> {
                    if (state.current != null) {
                        downstream.push(
                                state.current + ":" + state.count);
                    }
                });
    }

    public static void main(String[] args) {
        List<String> runs = Stream.of(
                        "A", "A", "B", "B", "B", "A")
                .gather(consecutiveRuns())
                .toList();

        System.out.println(runs); // [A:2, B:3, A:1]

        System.out.println(
                Stream.<String>empty()
                        .gather(consecutiveRuns())
                        .toList()); // []
    }
}
```

**Explanation:** the integrator holds `current` and `count`. When a new value arrives, it **emits the completed run**, then starts a new run. The last run has no "next value" to trigger emission; therefore, `finisher` pushes the final run downstream. The program assumes input elements are **non-null**, so `null` is used as a sentinel meaning "no active run yet". If `null` is valid data, a separate state flag is needed.

### 8.2. Why must encounter order be preserved?

The result `A:2, B:3, A:1` describes **consecutive occurrences**. If the source has no encounter order, run boundaries have no stable meaning. Use an ordered `List` or sort by a business key before calling `gather`.

### 8.3. Why not use Collector to collapse runs?

You could write a custom Collector with complex state and combiner to process segments, but you would have to solve merging **the last run of the left branch with the first run of the right branch**. A sequential Gatherer is more suitable when the requirement is to **emit each run in order** for the downstream pipeline to process further.

This is also a case where `Gatherers.windowFixed` is not a full substitute: fixed windows split by **size**, whereas this problem splits by **value-change boundaries**.

## 9. Ordering, parallel processing, and state

You cannot choose a tool merely by saying "it should run faster on a parallel stream".

### 9.1. map and mapMulti

`map` and `mapMulti` express **non-interfering**, typically **stateless** transformations well. With a parallel stream, lambdas can be invoked by multiple workers in a schedule that differs from encounter order. If the source is an ordered `List` and results are collected with `toList()`, Stream must still satisfy the appropriate output ordering contract; however, **the execution order of side effects inside lambdas is not guaranteed**.

### 9.2. Gatherer.ofSequential

A Gatherer created with `Gatherer.ofSequential` **does not provide a combiner for arbitrary parallel state integration**. That fits transformations where each step's result depends on state from the previous step.

```java
List<Long> ordered = List.of(5L, 3L, -2L, 7L);

List<RunningTotal> totals = ordered.parallelStream()
        .gather(runningTotals())
        .toList();
```

When the source has encounter order, the required cumulative totals are `5, 8, 6, 13` in that order. `ofSequential` does not turn the cumulative total problem into an arbitrarily splittable reduction; requesting a parallel stream does not automatically bring benefits to a sequential stateful stage. Do not rely on specific thread names or lambda call order as a contract.

### 9.3. Non-CONCURRENT Collectors still work on parallel streams

`Collectors.toList()` or `Collectors.groupingBy(...)` can execute properly on a parallel stream without their accumulators receiving concurrent writes on **the same container**. The framework can create separate state for branches and invoke `combiner` to merge them.

`Collectors.groupingByConcurrent(...)` or `toConcurrentMap(...)` have different properties regarding accumulation strategy and ordering; do not switch to a concurrent collector just because the name sounds appealing. If the result depends on head/tail order, changing the collector can **change semantics**.

### 9.4. Mutable state and ownership

| Tool | Where should state be kept? | What to avoid? |
|---|---|---|
| `map` | No state needed across elements | Shared counter variable outside the lambda |
| `mapMulti` | Local state within one invocation to emit independent elements | Shared Map or List mutated concurrently by callbacks |
| `Gatherer.ofSequential` | Fresh state from `initializer` | A `static` object shared across multiple pipelines |
| `Collector` | Container from `supplier`, managed by the framework | Supplier always returning one shared container; broken combiner |

In a Gatherer, if you must emit a collection stored in state, **take a copy** before calling `push`. If you `push(state.list)` and then `clear()`, previously emitted outputs can be mutated because they share a reference to the same mutable List.

## 10. Performance, memory, and short-circuiting

### 10.1. Memory footprint of each approach

- `map` can process one element at a time without holding the entire input; memory depends on the pipeline and terminal operation.
- `mapMulti` can avoid creating a sub-stream for every source element; if all outputs are pushed into `toList()`, result memory still grows with the number of retained elements.
- A cumulative Gatherer only needs two counters, i.e., **`O(1)`** state; a window Gatherer of size `k` may need an **`O(k)`** buffer.
- A summing/counting Collector may hold only **`O(1)`** state; `groupingBy` holds state proportional to the number of groups, while `toList` holds all output elements.

Using a Gatherer does not always mean saving memory. A Gatherer that emits large Lists and then calls `collect(toList())` may still need to retain most of the data.

### 10.2. Short-circuiting

A pipeline like:

```java
List<RunningTotal> firstTwo = transactions.stream()
        .gather(runningTotals())
        .limit(2)
        .toList();
```

can stop after downstream receives two results. A Gatherer should respect the `downstream.push(...)` signal and not assume all source transactions have been integrated. `collect` itself is not an intermediate transformation to incrementally emit snapshots to subsequent Stream steps.

With `mapMulti`, if a callback emits multiple elements in one call, do not assume a short-circuiting terminal operation will always prevent **every** remaining `emit.accept` immediately. Avoid side effects in callbacks; short-circuiting is a contract on output results, not a guarantee of callback invocation counts.

### 10.3. I/O sources still must be closed

A Stream from `Files.lines` can hold resources:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<String> processed = lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .toList();
}
```

`map`, `mapMulti`, `gather`, and `collect` **do not replace** `try-with-resources` for I/O sources. The snippet assumes `path` is declared and the enclosing method handles `IOException`. If a Gatherer uses sub-streams or its own resources, you must also understand the lifecycle of those resources.

### 10.4. Measure properly before optimizing

Do not conclude `mapMulti` is faster than `flatMap`, or `Gatherer` is faster than `Collector`, from an example with a few elements. Results depend on:

- Source size and average number of child elements per parent element.
- Intermediate object allocation overhead.
- Mutable state, combining operations, and ordering requirements.
- Splitting capability of the `Spliterator`.
- Cost of the terminal operation and amount of data retained.

If performance truly matters, use representative data, verify result equivalence first, warm up the JVM, measure multiple runs, and consider JMH. Choose the right algorithm before optimizing.

## 11. Common pitfalls and fixes

| Pitfall | Consequence | Fix |
|---|---|---|
| Using `map` on sublists expecting flattened lines | `Stream<List<T>>` instead of `Stream<T>` | Use `flatMap` or `mapMulti` |
| Using `mapMulti` with an external mutable counter | Data race or schedule-dependent results | Use an indexed source or stateful Gatherer |
| Using `mapMulti` when remaining state must be emitted at end | No finisher available | Use a Gatherer with a finisher |
| Returning `false` in integrator just to filter one input | Stops all further integration | Do not push and return `true` |
| Ignoring the return value of `downstream.push` | Consumes excess source or breaks stopping rules | Propagate the signal when appropriate |
| Gatherer initializer returning static state | Pipelines mix state, potential race | Create fresh state per integration pass |
| Emitting a mutable reference and mutating it afterward | Earlier outputs change contents | Emit a snapshot/new DTO |
| Calling `collect` then chaining `filter` directly on the result | `collect` already ended the Stream | Create a new Stream from the result if needed |
| Writing a cumulative Gatherer just to get a final sum | Unnecessarily complex code | Use `sum`/`reduce` or a Collector |
| Blindly switching `toMap` to `toConcurrentMap` for speed | May lose head/tail order | Clarify encounter order requirements and benchmark |
| Expecting `Gatherer` to run on JDK 21 | API not officially available yet | Upgrade to JDK 24+ or choose a compatible API |
| Relying on `HashMap.toString()` to check order | No key order guarantee | Compare contents or choose an ordered Map |
| Forgetting to close `Files.lines` after terminal operation | File handle leak | Use `try-with-resources` |

## 12. Practice exercises and solutions

### Exercise 1. Choosing map or mapMulti

Given `List<String> words = List.of("A", "B", "C")`. Which API should be used to transform each string into its length? What if each string should emit both the original string and its lowercase version?

**Answer:** Length is a **1:1** mapping, so use `map(String::length)`. Emitting two strings per element can use `mapMulti`:

```java
List<String> pairs = words.stream()
        .<String>mapMulti((word, emit) -> {
            emit.accept(word);
            emit.accept(word.toLowerCase());
        })
        .toList();
// [A, a, B, b, C, c]
```

### Exercise 2. Flattening sublists

Given `List<List<Integer>> nested = List.of(List.of(1, 2), List.of(), List.of(3))`. Use `mapMulti` to emit each number.

```java
List<Integer> flat = nested.stream()
        .<Integer>mapMulti((list, emit) -> {
            for (Integer value : list) {
                emit.accept(value);
            }
        })
        .toList();
// [1, 2, 3]
```

`flatMap(List::stream)` is also appropriate and can be shorter. No stateful Gatherer is needed for this problem.

### Exercise 3. Total sum or cumulative sum?

Input `[5, 3, -2]`. One dashboard only needs the final total; another dashboard needs `[5, 8, 6]` after each transaction. What should be used?

**Answer:** Final total uses `mapToLong(...).sum()` or `reduce`. Cumulative total uses a stateful Gatherer such as `runningTotals()` or the standard Gatherer `Gatherers.scan` when suitable.

### Exercise 4. Difference between Collector and Gatherer

Can `orders.stream().collect(groupingBy(...))` directly chain `.filter(...)` to filter **the created groups**?

**Answer:** No, `collect` returns a Map and terminates the Stream. You can create `map.entrySet().stream()` from the Map result. A Gatherer, on the other hand, is an intermediate operation and can directly chain `filter` onto the elements it emits.

### Exercise 5. Returning false in a Gatherer

A Gatherer receives `[-1, 2, 3]` and only wants to drop negative numbers. If it returns `false` when encountering `-1`, what happens?

**Answer:** The Gatherer stops integrating, so 2 and 3 are never processed. To **filter** negative numbers, do not call `push` and return `true`.

### Exercise 6. Why is a finisher needed?

A Gatherer groups consecutive values: `A,A,B,B,B,A`. If it only emits a group when encountering a different value, which group is lost without a finisher?

**Answer:** The final group `A:1` is not emitted because there is no next element to close the group. The finisher emits the remainder at the end of the Stream.

### Exercise 7. Parallelism problem

A Gatherer numbers elements sequentially by input arrival; the source is a `HashSet` with no guaranteed encounter order. Does `ofSequential` automatically determine chronological order?

**Answer:** No. `ofSequential` specifies sequential integration, not automatic sorting. You need a source with an appropriate encounter order or `sorted(comparator)` by time and tie-breaking rules.

### Exercise 8. Checking shared state

A Gatherer has `initializer` `() -> SHARED`, where `SHARED` is a static mutable object. Why is this dangerous?

**Answer:** Multiple executions can share the same object, mixing counts and data. If pipelines run concurrently, there is also a risk of data race. Use `State::new` to create private state.

### Exercise 9. Testing empty sources

With an empty Stream, how many elements will `map` and `mapMulti` emit? Is a Gatherer with a finisher required to emit 0 elements?

**Answer:** `map` and `mapMulti` receive no input elements, so they emit no elements. **A Gatherer with a finisher** can be designed to emit a default value or a summary report upon completion, depending on its contract; for instance, `consecutiveRuns` emits nothing because there is no unfinished group. Do not assume every Gatherer handles empty sources identically to `map`.

### Exercise 10. Choosing a tool for reporting

There are 50,000 transaction lines, requiring line count, total amount, and total amount by SKU, **without** needing cumulative milestones. Should you write a Gatherer managing a `HashMap` manually and emitting only at the end?

**Answer:** No need. A built-in collector or a custom `Collector` is the natural choice to return a final report. A Gatherer is only worth considering if you need intermediate transformations, emitting results at milestones, or continuing the pipeline with multiple outputs.

## 13. Extended exercise: window statistics followed by filtering

**Prompt:** A sensor sends an ordered sequence of temperatures. We need to split them into windows of **three consecutive samples**, compute the average of each window, and keep only windows whose average exceeds a threshold.

Approach in Java 24:

```java
List<Double> hotWindows = temperatures.stream()
        .gather(java.util.stream.Gatherers.windowFixed(3))
        .map(window -> window.stream()
                .mapToDouble(Double::doubleValue)
                .average()
                .orElseThrow())
        .filter(avg -> avg > threshold)
        .toList();
```

This illustrative snippet assumes `List<Double> temperatures` and `double threshold` are already declared. Because `Gatherers.windowFixed` emits window Lists, `map` then maps **one window to one average**; finally `filter` removes windows that do not exceed the threshold. This problem shows **Gatherer does not replace map or filter**: they collaborate in the same pipeline.

If **sliding** windows are required instead of non-overlapping windows, consider `Gatherers.windowSliding` while checking the contract on window length and input ordering. If only the average of the entire sequence is needed, `mapToDouble(...).average()` is much simpler.

## 14. Checklist before choosing an API

1. **Does the requirement need one output or multiple outputs per input?** For a simple single output, prefer `map`.
2. **Can the outputs of one element be computed independently?** If yes, `mapMulti` or `flatMap` is usually enough.
3. **Is state needed across inputs?** If yes, consider Gatherer.
4. **Must remaining data be emitted when the source ends?** If yes, design a finisher or use a suitable standard Gatherer.
5. **Do you need one final result or a Stream of results for further processing?** Prefer `collect` for a final result; prefer `gather` for an intermediate Stream.
6. **What is the JDK version contract?** `map`/`collect` since Java 8; `mapMulti` since 16; `Gatherer` official since 24.
7. **Is there a business order?** Cumulative totals and consecutive runs require a defined encounter order.
8. **Is there shared mutable state?** Avoid side effects in `map`/`mapMulti`; create fresh state for Gatherer/Collector.
9. **Is short-circuiting required?** Distinguish "filtering one element" from "stopping the entire integration".
10. **Is parallel compatibility required?** Check combiner/collector contract or Gatherer sequentiality and ordering overhead.
11. **Are there nulls, empty inputs, overflowing amounts, or I/O to close?** Define policies before writing the pipeline.
12. **Can a simpler standard API be used?** `Collectors.summarizingLong`, `groupingBy`, `Gatherers.scan`, `windowFixed`, or `windowSliding` might solve the problem.

**Conclusion:** `map` solves **1:1**, `mapMulti` handles **0..n independent values from one input**, Gatherer extends capabilities with **stateful intermediate transformations, short-circuiting, and finisher**, and Collector **accumulates into a final result**. The core difference does not lie in all four taking lambdas, but in **output data flow, state lifecycle, and execution contract**. Choosing the right tool keeps JAVA_STREAM_API pipelines concise, accurate, and easy to reason about regarding ordering, performance, and resources when upgrading the JDK.
