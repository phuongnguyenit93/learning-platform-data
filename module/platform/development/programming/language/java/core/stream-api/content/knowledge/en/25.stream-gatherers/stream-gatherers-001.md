# The Role of gather and Gatherer Supported in the JDK

Java Stream API provides familiar operations such as `filter`, `map`, `flatMap`, `distinct`, `sorted`, `reduce`, and `collect`. They solve many declarative data-processing problems. However, some problems require **looking at multiple consecutive elements**, **maintaining state across elements**, or **emitting a different number of results than the number of inputs**: computing a moving average, batching events, checking event patterns, or emitting multiple results from a single record. These are the situations where **Stream Gatherers** expand the expressive power of a pipeline.

Starting from **Java 24**, `Stream.gather(...)` and the interfaces in `java.util.stream.Gatherer` became an official API. A `Gatherer` describes *how an intermediate stage receives, processes, and emits elements*, while `gather(...)` is the operation on `Stream` used to **attach a Gatherer to a pipeline**.

This lesson belongs to the **Stream Gatherer** chapter of the **JAVA_STREAM_API** module. Its goal is to understand the role of `gather` and `Gatherer`, know how to choose them over `filter`, `map`, `flatMap`, `reduce`, and `collect`, master the built-in Gatherers, learn how to write simple Gatherers, and understand JDK requirements as well as limitations around laziness, short-circuiting, ordering, parallel processing, resources, and performance. The main examples use **JDK 24+**.

## 1. Opening problem: average of the three most recent measurements

Suppose a system receives a sequence of temperatures in chronological order:

```text
20, 22, 21, 25, 27
```

The average of the entire sequence is:

```java
import java.util.List;

List<Integer> temperatures = List.of(20, 22, 21, 25, 27);

double overallAverage = temperatures.stream()
    .mapToInt(Integer::intValue)
    .average()
    .orElseThrow();

System.out.println(overallAverage); // 23.0
```

However, the user wants **the average of each group of three consecutive measurements**:

```text
[20, 22, 21] -> 21.0
[22, 21, 25] -> 22.666...
[21, 25, 27] -> 24.333...
```

Starting in Java 24, this can be written directly:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Double> movingAverages = temperatures.stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow())
    .toList();

System.out.println(movingAverages);
// [21.0, 22.666666666666668, 24.333333333333332]
```

Here, `windowSliding(3)` creates **a window of three consecutive elements** for each position with enough samples; `map` computes the average of **each window**. The `gather` operation allows the pipeline to transition from:

```text
Stream<Integer>
      |
      | gather(Gatherers.windowSliding(3))
      v
Stream<List<Integer>>
      |
      | map(compute average)
      v
Stream<Double>
      |
      | toList()
      v
List<Double>
```

This is the general role of a Gatherer: **transforming the way elements flow through the pipeline itself**, rather than only computing on each individual element.

## 2. Distinguishing `gather` from `Gatherer` and `Gatherers`

The three names look similar, but they serve different roles:

| Component | Kind | Role |
| --- | --- | --- |
| `Stream.gather(...)` | Method on `Stream<T>` | Attaches a Gatherer to create a **new intermediate stage** |
| `Gatherer<T, A, R>` | Interface describing processing rules | Accepts `T`, may hold state `A`, emits `R` |
| `Gatherers` | Utility class containing factories | Provides built-in Gatherers such as `windowFixed`, `windowSliding`, `scan`, `fold`, `mapConcurrent` |

Example:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<String, ?, List<String>> batchByTwo =
    Gatherers.windowFixed(2);

List<List<String>> batches = Stream.of("A", "B", "C")
    .gather(batchByTwo)
    .toList();

System.out.println(batches); // [[A, B], [C]]
```

The method `Gatherers.windowFixed(2)` **creates a Gatherer object**; the method `Stream.gather(batchByTwo)` **uses that object** in the pipeline.

**Way to remember:** `Gatherer` is the *rule*, `Gatherers` is the *set of built-in rules*, and `gather` is the *point where the rule is applied to a Stream*.

### 2.1. `gather` is an intermediate operation

`gather` returns a new Stream, so it can be chained further:

```java
List<Integer> sums = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(2))
    .map(window -> window.stream().mapToInt(Integer::intValue).sum())
    .filter(sum -> sum >= 5)
    .toList();

System.out.println(sums); // [7, 5]
```

The windows are `[1,2]`, `[3,4]`, `[5]` with sums `3`, `7`, and `5`. The filter after `gather` checks **the sum of each window**, not each individual input number.

`gather` **is not a terminal operation**. Only when a terminal operation such as `toList`, `collect`, `reduce`, or `findFirst` is invoked is the pipeline consumed.

## 3. JDK milestones: when can Stream Gatherers be used?

Stream Gatherers went through three stages:

| JDK Version | Status | JEP | Requirement |
| --- | --- | --- | --- |
| Java 8–21 | No standard Stream Gatherers | — | Cannot call `Stream.gather` directly |
| **Java 22** | First preview | [JEP 461](https://openjdk.org/jeps/461) | Enable preview when compiling and running |
| **Java 23** | Second preview | [JEP 473](https://openjdk.org/jeps/473) | Still requires enabling preview |
| **Java 24** | Official API | [JEP 485](https://openjdk.org/jeps/485) | No preview needed just to use Gatherer |
| Java 25 and later include this API | API is standardized | Starting from JEP 485 | Use a toolchain/runtime matching the target version |

A program using a standard Gatherer on JDK 24:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererAvailabilityDemo {
    public static void main(String[] args) {
        List<List<Integer>> result = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowFixed(2))
            .toList();

        System.out.println(result); // [[1, 2], [3, 4], [5]]
    }
}
```

Compile and run with **JDK 24**:

```bash
javac --release 24 GathererAvailabilityDemo.java
java GathererAvailabilityDemo
```

If testing the same basic example on **JDK 22**:

```bash
javac --enable-preview --release 22 GathererAvailabilityDemo.java
java --enable-preview GathererAvailabilityDemo
```

On **JDK 23**:

```bash
javac --enable-preview --release 23 GathererAvailabilityDemo.java
java --enable-preview GathererAvailabilityDemo
```

Do not use JDK 21 with `--enable-preview` expecting `Gatherers` to be available: Java 21 does not provide this API yet. `--release 21` on a newer compiler also does not allow using the Java 24 API when targeting Java 21.

### 3.1. Compatibility notes

- Examples in this article follow the **official Java 24 API**, which does not mean custom code written for the 22/23 previews will migrate without edits.
- Preview features are tied to the JDK version being used; you should recompile on the target JDK.
- If the application needs to run on Java 17/21, you must choose another approach or isolate the parts requiring a newer JDK.
- Java 24 is the version with the official Gatherer API, but **the minimum Java version of a product** is determined by deployment requirements and support policies.

## 4. Why do we need Gatherer when `map` and `flatMap` already exist?

Many requirements should continue using traditional Stream operations. Gatherer does not aim to replace them.

| Problem | Preferred API | Why |
| --- | --- | --- |
| Keep only paid transactions | `filter(Order::paid)` | Each element is evaluated independently |
| Convert names to uppercase | `map(String::toUpperCase)` | One input produces one output |
| Flatten each sublist into elements | `flatMap(List::stream)` | Combines multiple sub-streams |
| Compute a single final sum | `mapToLong(...).sum()` or `reduce` | No need to emit intermediate sequences of results |
| Group by key at the end of a pipeline | `collect(groupingBy(...))` | The final result is a Map/report |
| Group every 100 consecutive elements into a batch | `gather(windowFixed(100))` | Needs a stateful stage to form batches |
| Moving average of the three most recent elements | `gather(windowSliding(3))` then `map` | Needs overlapping windows |
| Emit cumulative sum after **each** element | `gather(scan(...))` | Needs multiple cumulative results, not just one final sum |
| Custom stateful intermediate transformation | Custom `Gatherer` | Needs control over data and state beyond built-in operations |

The `flatMap` operation can also emit multiple outputs from a single element, so **an output count different from the input count** alone is not enough to mandate using a Gatherer. The strength of Gatherer is **its programming model for stateful intermediate operations and flexible emission/short-circuiting rules**.

### 4.1. Gatherer does not replace `Collector`

`Collectors.groupingBy` groups elements by key and produces **a single final Map**:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("North", 100L),
    new Sale("South", 200L),
    new Sale("North", 300L)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(totals.get("North")); // 400
```

A Gatherer produces **intermediate values** that can subsequently be filtered, transformed, or collected. For example, receiving groups of consecutive transactions, and then summing each batch:

```java
List<Long> batchTotals = sales.stream()
    .gather(Gatherers.windowFixed(2))
    .map(batch -> batch.stream()
        .mapToLong(Sale::amountVnd)
        .sum())
    .toList();

System.out.println(batchTotals); // [300, 300]
```

The two problems have different meanings:

- `groupingBy`: all transactions with the same `region` are grouped under one key, even if they appear far apart.
- `windowFixed`: **adjacent** transactions in encounter order are grouped by count, not by key.

## 5. Components of a Gatherer

General form:

```java
Gatherer<T, A, R>
```

Where:

- **`T`**: the input element type of the stage.
- **`A`**: the internal state type (*intermediate state*); this can be an object, an array, or `Void` if no state is needed.
- **`R`**: the element type emitted downstream.

Four components make up the processing lifecycle:

| Component | Responsibility | Question the developer needs to answer |
| --- | --- | --- |
| `initializer` | Creates state `A` | What information is stored initially? |
| `integrator` | Receives a `T`, updates `A`, may emit `R`s | How does each element affect the result? |
| `combiner` | Combines states when work is split | Can two branches be merged correctly? |
| `finisher` | Finalizes when processing ends, may emit remaining output | Is there any remaining result to push at the end of the source? |

Model:

```text
        Stream<T>
            |
            v
   +---------------------+
   | initializer()       | -> state A
   +---------------------+
            |
            v
   +---------------------+
   | integrator(state,   | -> push R, push R, ...
   |            T, out)  |
   +---------------------+
            |
            | at end of source or processing
            v
   +---------------------+
   | finisher(state,out) | -> may push more R
   +---------------------+
            |
            v
        Stream<R>

   combiner(left,right): for designs capable of combining state
```

**Not every Gatherer requires writing all four components manually.** The factories in `Gatherers` already provide complete logic for many common patterns. The `Gatherer.of(...)` and `Gatherer.ofSequential(...)` factories also provide overloads for cases that do not need state or a custom finisher.

### 5.1. A Gatherer can receive one element and emit 0, 1, or many elements

Unlike `map`, which always maps one element to one output, an Integrator can:

- Receive an element and **emit nothing yet**, because more data is needed.
- Emit **one** new result after each element, such as a running sum.
- Emit **multiple** results because a single element contains multiple sub-items.
- Stop accepting further data according to a valid condition.

This is an important point when building windowing, protocol, or event-stream analysis logic.

## 6. `Gatherers.windowFixed`: splitting a source into fixed batches

`windowFixed(k)` creates **non-overlapping** windows, each with at most `k` elements. The final window may have fewer than `k` elements.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7]]
```

This is a reasonable choice to:

- Compute the amount for each batch of consecutive transactions.
- Process data in batches bounded by `k` elements.
- Emit chunks of input for a subsequent transformation step.
- Produce statistics for each group of adjacent observations up to a fixed maximum length.

### 6.1. An incomplete final group still appears

```java
List<List<String>> batches = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(batches); // [[A, B], [C, D], [E]]
```

If the business rule only processes batches with **a full two elements**:

```java
List<List<String>> fullBatches = Stream.of("A", "B", "C", "D", "E")
    .gather(Gatherers.windowFixed(2))
    .filter(batch -> batch.size() == 2)
    .toList();

System.out.println(fullBatches); // [[A, B], [C, D]]
```

Do not assume on your own that the final group is discarded. This is a **business policy** that must be written as an explicit condition if required.

## 7. `Gatherers.windowSliding`: overlapping windows

`windowSliding(k)` creates windows of `k` consecutive elements and shifts the starting point forward by **one element** after each full window.

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Compare with `windowFixed(3)` on the same source:

```java
System.out.println(Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .toList());
// [[1, 2, 3], [4, 5]]
```

### 7.1. Comparing boundary cases

With window size `k = 3`:

| Input | `windowFixed(3)` | `windowSliding(3)` |
| --- | --- | --- |
| `[]` | `[]` | `[]` |
| `[1]` | `[[1]]` | `[[1]]` |
| `[1,2]` | `[[1,2]]` | `[[1,2]]` |
| `[1,2,3]` | `[[1,2,3]]` | `[[1,2,3]]` |
| `[1,2,3,4]` | `[[1,2,3],[4]]` | `[[1,2,3],[2,3,4]]` |

For `windowSliding(k)`, if the source is **non-empty but has fewer than `k` elements**, it emits **one short window** containing the entire source. If the source has at least `k` elements, every sliding window emitted has a full `k` elements.

With `N >= k`, the number of sliding windows equals `N-k+1`. With fixed windows on a finite source, the number of windows equals `ceil(N/k)` when `N > 0`.

### 7.2. Element windows are not the same as time windows

`windowSliding(3)` means **three consecutive elements**, not three seconds or three minutes. If events have unevenly spaced timestamps, achieving actual time-based windows requires a different design that clearly defines:

- Event time versus processing time.
- The start/end boundaries of the time interval.
- Late-arriving events and timestamp ordering.
- The policy for time intervals with no records.

Standard Gatherers only see **element order** and size `k`; they do not infer business time rules.

## 8. `Gatherers.scan` and `Gatherers.fold`: accumulated state and final result

These two built-in Gatherers clarify **the difference between emitting results step by step and emitting only a final result**.

### 8.1. `scan` emits a running total after each element

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> runningTotals = List.of(10L, 20L, 30L, 40L)
    .stream()
    .gather(Gatherers.scan(
        () -> 0L,
        Long::sum
    ))
    .toList();

System.out.println(runningTotals); // [10, 30, 60, 100]
```

The output contains the accumulated value **after each element is received**. A running total is not a sliding-window sum: with a running sum, old elements are **not removed from the total**.

### 8.2. `fold` emits a single value after aggregating

```java
String text = Stream.of("Java", " ", "Stream")
    .gather(Gatherers.fold(
        () -> "",
        String::concat
    ))
    .findFirst()
    .orElseThrow();

System.out.println(text); // Java Stream
```

`fold` uses accumulated state to produce **one result at the end**, unlike `scan`, which can emit multiple intermediate values.

When only a single final arithmetic sum is needed, `reduce` or `sum` is usually simpler than `gather(fold(...))`:

```java
long total = List.of(10L, 20L, 30L, 40L)
    .stream()
    .mapToLong(Long::longValue)
    .sum();

System.out.println(total); // 100
```

**Selection rule:** use `scan` when you need accumulated states step by step; `fold` when you want a single value after traversing the source; `reduce`/`sum` when the final aggregation is simple and a suitable terminal operation already exists.

## 9. `Gatherers.mapConcurrent`: bounded concurrent mapping

`Gatherers.mapConcurrent(maxConcurrency, mapper)` allows a mapping stage to **perform multiple tasks concurrently** using virtual threads, up to the maximum limit specified by `maxConcurrency`. This Gatherer **preserves result order** according to the Stream's encounter order.

An example that can run on JDK 24+:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Integer> sizes = List.of("A", "Java", "Gatherers")
    .stream()
    .gather(Gatherers.mapConcurrent(
        3,
        String::length
    ))
    .toList();

System.out.println(sizes); // [1, 4, 9]
```

Operations like `String::length` are very cheap, so the example only illustrates syntax. `mapConcurrent` is typically more worth considering for independent tasks with wait time, such as calling services whose contracts permit concurrency, **provided** concurrency limits and I/O management are properly designed.

### 9.1. `mapConcurrent` differs from `parallelStream`

| Criterion | `Gatherers.mapConcurrent` | `parallelStream().map(...)` |
| --- | --- | --- |
| Goal | Limit the number of mapper operations executing concurrently | Split Stream processing across parallel tasks |
| Notable model | Virtual threads for mapper work | Stream's parallel processing mechanism |
| API-level concurrency limit setting | `maxConcurrency` | No equivalent parameter directly on `parallel()` |
| Output order | Preserves encounter order when present | `toList` also preserves encounter order when the Stream is ordered |
| Guaranteed to run faster | **No** | **No** |

Neither automatically makes a mapper that uses shared mutable state thread-safe. Preserving **result order** does not mean the internal computations execute sequentially.

Do not set `maxConcurrency` too high just to increase throughput. I/O sources, connection limits, CPU load, memory, and upstream/downstream requirements all affect effectiveness.

## 10. Writing a minimal custom Gatherer: one input to one output

To understand the role of `Gatherer`, let's start with a stateless example: squaring integers.

```java
import java.util.List;
import java.util.stream.Gatherer;

public class SquareGathererDemo {

    static Gatherer<Integer, Void, Integer> squares() {
        Gatherer.Integrator.Greedy<Void, Integer, Integer> integrator =
            Gatherer.Integrator.ofGreedy(
                (unused, number, downstream) ->
                    downstream.push(Math.multiplyExact(number, number))
            );

        return Gatherer.of(integrator);
    }

    public static void main(String[] args) {
        List<Integer> result = List.of(1, 2, 3, 4)
            .stream()
            .gather(squares())
            .toList();

        System.out.println(result); // [1, 4, 9, 16]
    }
}
```

This is a custom Gatherer with `T = Integer`, `A = Void`, and `R = Integer`. There is no separate state object. The Integrator receives a number, computes its square, and calls `downstream.push`.

`Integrator.ofGreedy` is used because the Integrator **does not initiate short-circuiting on its own**: it only reflects the downstream's decision via the return value of `push`.

For this simple problem, it is still better to use:

```java
List<Integer> result = List.of(1, 2, 3, 4)
    .stream()
    .map(n -> Math.multiplyExact(n, n))
    .toList();
```

The purpose of the example is to get familiar with the API, **not** to suggest replacing every `map` with a Gatherer. When the code does not need to maintain state or emit multiple results under custom rules, standard operations are usually clearer.

## 11. Stateful custom Gatherer: emitting a running sum

Even though `scan` already exists, we can learn how a custom Gatherer stores state across element receptions.

The following example uses a `long[]` array to hold the sum. The array is newly created for the accumulation scope and is not shared as a global variable.

```java
import java.util.List;
import java.util.stream.Gatherer;

public class RunningSumGathererDemo {

    static Gatherer<Integer, long[], Long> runningSum() {
        return Gatherer.ofSequential(
            () -> new long[] {0L},
            (state, number, downstream) -> {
                state[0] = Math.addExact(state[0], number.longValue());
                return downstream.push(state[0]);
            }
        );
    }

    public static void main(String[] args) {
        List<Long> result = List.of(3, 5, -2, 9)
            .stream()
            .gather(runningSum())
            .toList();

        System.out.println(result); // [3, 8, 6, 15]
    }
}
```

Components of the Gatherer:

1. **Initializer:** `() -> new long[] {0L}` creates the initial state.
2. **Integrator:** receives each number, adds it to the sum, and emits the new sum.
3. **Combiner:** not declared; `ofSequential` is used when there is no valid way to combine parallel state.
4. **Finisher:** no special work is needed, so it does not need to be defined manually.

`Math.addExact` throws `ArithmeticException` if the `long` sum overflows. It **does not** turn addition into arbitrary-precision integer arithmetic; if sums larger than 64 bits are required, a type like `BigInteger` is needed.

### 11.1. Why choose `ofSequential`?

The running-sum result is order-dependent: to emit the correct state at the third element, the Gatherer needs to know the sum of the preceding elements. You cannot arbitrarily merge the states of two branches with `Long::sum` and assume **the entire sequence of prefix sums** remains correct.

`ofSequential` is the clear choice when no valid combiner exists. It does not mean every stage in the pipeline runs on only a single Java thread, nor does it eliminate the need to check for shared state elsewhere.

### 11.2. A Stream can only be consumed once

```java
var pending = List.of(3, 5, -2, 9)
    .stream()
    .gather(runningSum());

System.out.println(pending.toList()); // [3, 8, 6, 15]

// pending.count(); // Invalid: the Stream has already been consumed.
```

A Gatherer can be used for **new pipelines** according to its contract, but it does not turn the same already-consumed Stream into a reusable source.

## 12. Custom Gatherers and short-circuiting

Besides state and output, a Gatherer can **stop receiving from upstream on its own** when encountering a business milestone.

Example keeping all strings until `"END"` is encountered, **including the marker**:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class UntilEndGathererDemo {

    static Gatherer<String, Void, String> untilEnd() {
        Gatherer.Integrator<Void, String, String> integrator =
            Gatherer.Integrator.of(
                (unused, value, downstream) -> {
                    boolean wantsMore = downstream.push(value);
                    return wantsMore && !"END".equals(value);
                }
            );

        return Gatherer.ofSequential(integrator);
    }

    public static void main(String[] args) {
        List<String> result = List.of(
                "START", "RUN", "END", "AFTER"
            ).stream()
            .gather(untilEnd())
            .toList();

        System.out.println(result); // [START, RUN, END]
    }
}
```

For a regular Integrator:

- Returning `true`: ready to receive more elements.
- Returning `false`: requests stopping intake from upstream.
- Can return `false` on its own due to hitting a marker, even when downstream still wants more.

### 12.1. `ofGreedy` does not mean always having to emit an element

`Gatherer.Integrator.ofGreedy` creates an Integrator that **does not initiate short-circuiting itself**. It may skip elements or emit multiple results, but **must not** return `false` on its own due to a business condition while downstream is still accepting.

Example filtering even numbers while continuing past odd numbers:

```java
Gatherer.Integrator.Greedy<Void, Integer, Integer> even =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) ->
            n % 2 == 0 ? downstream.push(n) : true
    );
```

Example **violating the contract** if labeled Greedy:

```java
Gatherer.Integrator.Greedy<Void, String, String> bad =
    Gatherer.Integrator.ofGreedy(
        (unused, value, downstream) ->
            downstream.push(value) && !"END".equals(value)
    );
```

Because `false` can occur due to the marker, a valid Stream implementation may **ignore the return value of a Greedy Integrator** and fail to stop where the code expects.

**Rule:** use a regular Integrator when **the Gatherer itself decides to stop**; only use `ofGreedy` when there is no self-stopping path.

## 13. Output emission mechanism: `Downstream.push` and `isRejecting`

The Integrator communicates with the next stage through `Gatherer.Downstream<R>`.

```java
boolean accepted = downstream.push(result);
boolean rejecting = downstream.isRejecting();
```

`push(result)` returns `false` if downstream does not want to receive more output. A terminal operation such as `limit(3).toList()` can cause downstream to reject after receiving three elements. `isRejecting()` is a *best-effort* check of rejection status, and does not guarantee future `push` calls will definitely be accepted if it returns `false` at the time of checking.

For a Gatherer that can emit multiple results for one input, you should respond to the signal:

```java
import java.util.List;
import java.util.stream.Gatherer;

Gatherer.Integrator.Greedy<Void, List<String>, String> flatten =
    Gatherer.Integrator.ofGreedy(
        (unused, batch, downstream) -> {
            for (String item : batch) {
                if (!downstream.push(item)) {
                    return false; // Only propagate downstream rejection.
                }
            }
            return true;
        }
    );
```

`return false` here **does not** violate Greedy because it only happens when downstream `push` returns `false`. Do not continue iterating through the remaining elements in a batch if downstream is already rejecting.

If you only need to flatten lists, `flatMap(List::stream)` is a more concise choice. The example illustrates the **output coordination mechanism** of a Gatherer.

## 14. `finisher` is used to emit remaining results

Not every Gatherer emits data immediately inside the Integrator. There are cases where it is necessary to **hold state and then emit a result at the end of the source**.

Example counting received elements and then emitting the count upon finishing:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class FinishCountGathererDemo {
    static final class State {
        long count;
    }

    static Gatherer<String, State, Long> countAtEnd() {
        return Gatherer.ofSequential(
            State::new,
            (state, value, downstream) -> {
                state.count = Math.addExact(state.count, 1L);
                return true; // Nothing emitted yet, still wants more.
            },
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(state.count);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Long> output = List.of("A", "B", "C")
            .stream()
            .gather(countAtEnd())
            .toList();

        System.out.println(output); // [3]
    }
}
```

This example shows:

- The Integrator can **emit no results** throughout the process of receiving input.
- `finisher` can emit a final element.
- When downstream is rejecting, you should not continue emitting unnecessary data.

In production code, simple counting should use `Stream.count()`. A custom Gatherer is better suited when there are multi-step stateful processing rules or final data needs to be emitted as an intermediate stage.

## 15. Laziness: `gather` does not run immediately when creating the pipeline

A Stream pipeline is constructed first and executes when the terminal operation starts.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Stream<List<Integer>> pending = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3));

// toList(), findFirst(), or any other terminal operation has not been called yet.

List<Integer> firstWindow = pending.findFirst().orElseThrow();

System.out.println(firstWindow); // [1, 2, 3]
```

`findFirst` can stop after the Gatherer stage emits enough data for it. A Gatherer capable of emitting results before the source ends is often well-suited for **incremental** processing needs, though that does **not** mean every Gatherer can produce output immediately.

For example, `fold` needs to accumulate until the end of the source before producing its final result.

### 15.1. Avoid side effects that depend on callback invocation counts

`map`, `filter`, `peek`, and integrator are functions in the pipeline. You should not rely on side effects to count exactly "how many times the framework called a lambda" in every situation:

- Terminal operations can short-circuit.
- Streams can optimize steps when result semantics are preserved.
- Parallel processing can change the order and splitting of work.
- A Gatherer can emit 0, 1, or many outputs for each input.

Express statistics using the results of `count`, `sum`, `reduce`, `collect`, or a contract-compliant Gatherer, instead of turning `peek` into a place for mandatory business data writes.

## 16. Infinite Streams and short-circuiting

An infinite source can still be used if there is a clear termination condition downstream.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> firstThreeWindows = Stream
    .iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(3)
    .toList();

System.out.println(firstThreeWindows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

`limit(3)` limits **three output windows**, not three source elements. To produce three full windows of width three, the pipeline needs at least five input elements.

With infinite sources, avoid terminal operations or Gatherers that **require the entire source to finish before emitting results**, such as a `fold` operation on a source that never ends.

### 16.1. Short-circuiting and resources are two separate concerns

If the source is a Stream backed by a file or connection, a `limit` or self-stopping Gatherer **does not automatically release resources**. You must properly close the source according to the API contract, usually with `try-with-resources`.

## 17. Encounter order: windows depend on element ordering

`windowFixed` and `windowSliding` rely on **the encounter order of elements**. With a source that has an encounter order such as `List.stream()` or `IntStream.range(...).boxed()`, you can accurately predict the windows in that order.

```java
import java.util.List;
import java.util.stream.Gatherers;

List<List<String>> windows = List.of("A", "B", "C", "D")
    .stream()
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(windows);
// [[A, B], [B, C], [C, D]]
```

If the source is a `HashSet` or the pipeline is switched to `unordered()`, you should not infer a fixed business order. Even though all values appear, **how they are grouped into windows** may not represent "the two most recent records by time".

For timestamped data, you must clearly establish:

- Is the source already sorted by event time?
- If timestamps collide, what is the tie-breaking criterion?
- Does calling `sorted` before `gather` change the original meaning?
- Are time-based windows needed instead of record-count windows?

An object having a timestamp field **does not automatically make a Stream ordered by timestamp**.

## 18. Parallel processing: Gatherer does not guarantee speedup on its own

Some Gatherers carry order-dependent state. When running in parallel, the system must know whether it can:

1. Split elements into branches.
2. Process the state of each branch.
3. Merge results **without losing, duplicating, or misordering elements**.

`combiner` is part of the contract that supports merging state when splitting is possible. However, not every problem has a simple combiner.

For example, the running sum in section 11 needs to know **the sum of the entire preceding portion** when emitting values in the later portion. Merging two local sums by addition is not enough to adjust all intermediate values of the later branch. Therefore, that example uses `ofSequential`.

```java
List<Long> output = List.of(1, 2, 3, 4, 5)
    .parallelStream()
    .gather(RunningSumGathererDemo.runningSum())
    .toList();

System.out.println(output); // [1, 3, 6, 10, 15]
```

Even though the source is a parallel Stream, a sequential Gatherer can restrict parallel execution at that stage. You should not conclude that calling `parallelStream()` always speeds things up.

### 18.1. Using mutable state in the proper scope

Pattern to avoid:

```java
import java.util.ArrayList;
import java.util.List;

List<Long> shared = new ArrayList<>();

List.of(1, 2, 3, 4).parallelStream()
    .map(Integer::longValue)
    .forEach(shared::add); // Unsafe when multiple tasks write to ArrayList.
```

Recommended pattern:

```java
List<Long> result = List.of(1, 2, 3, 4)
    .parallelStream()
    .map(Integer::longValue)
    .toList();
```

A stateful custom Gatherer needs to store state inside the accumulator managed by the framework, avoiding shared static mutable variables across multiple Streams. A properly designed Gatherer can use internal mutable state while still not permitting arbitrary writes to the source data.

### 18.2. `Integrator.ofGreedy` is not synonymous with `Gatherer.ofSequential`

The two choices address two different questions:

| Question | Related API |
| --- | --- |
| Does the Integrator **initiate short-circuiting itself**? | `Integrator.of` and `Integrator.ofGreedy` |
| Does the Gatherer have a **valid combiner** to split/merge state? | `Gatherer.of`, `ofSequential`, and overloads with a combiner |

A **Greedy Integrator with sequential state** is completely valid. Marking an Integrator as Greedy does not automatically make the algorithm parallel-safe.

## 19. Primitive Streams and Gatherers

`gather(...)` is a method of object **`Stream<T>`**. Primitive specializations such as `IntStream`, `LongStream`, and `DoubleStream` **do not have an equivalent `gather` method directly** in the Java 24 API.

When you need to apply a Gatherer to `int` data:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 5)
    .boxed()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

`boxed()` creates a `Stream<Integer>`, on which `gather` can be used. When processing millions of integers, boxing and `List<Integer>` windows can create additional memory allocation pressure. If you only need the sum of all integers, consider `IntStream.sum`, `LongStream.sum`, or `summaryStatistics` before using a Gatherer.

## 20. I/O and responsibility for closing Streams

`gather` is an intermediate stage; applying it **does not automatically close** `Files.lines`, `Files.walk`, or other I/O sources.

Example counting error lines per batch of 100 **non-blank** lines:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class LogBatchDemo {
    public static List<Long> countErrorsPerBatch(Path path)
            throws IOException {
        try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> !line.isBlank())
                .gather(Gatherers.windowFixed(100))
                .map(batch -> batch.stream()
                    .filter(line -> line.contains("ERROR"))
                    .count())
                .toList();
        }
    }
}
```

Here:

- `Files.lines` holds the file-reading resource for the Stream's lifecycle.
- `try-with-resources` closes the source, even if an error occurs.
- `filter` **before** `gather` means each batch has 100 non-blank lines, **not** necessarily 100 original lines.
- `windowFixed(100)` emits a final batch of fewer than 100 lines if remaining elements exist.
- `toList()` materializes the list of error counts for all batches.

If you want to batch by **100 original lines and then count error lines**, you must reverse the order:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<Long> counts = lines
        .gather(Gatherers.windowFixed(100))
        .map(batch -> batch.stream()
            .filter(line -> line.contains("ERROR"))
            .count())
        .toList();

    System.out.println(counts);
}
```

There is no single pipeline order that fits every business requirement; choose the order according to **the definition of a data batch**.

## 21. A complete Java 24 example: from input data to report

The following program combines `filter`, `gather`, `map`, and `toList` on an ordered dataset. It produces two reports: **totals for each batch of two paid orders** and **sliding totals of three consecutive paid orders**.

```java
import java.util.List;
import java.util.stream.Gatherers;

public class GathererOrderReportDemo {

    record Order(String id, long amountVnd, boolean paid) {}

    record BatchMetric(
        List<String> orderIds,
        int count,
        long totalVnd
    ) {}

    static BatchMetric toMetric(List<Order> window) {
        List<String> ids = window.stream()
            .map(Order::id)
            .toList();

        long total = window.stream()
            .mapToLong(Order::amountVnd)
            .sum();

        return new BatchMetric(ids, window.size(), total);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", 100_000L, true),
            new Order("O-02",  50_000L, false),
            new Order("O-03", 200_000L, true),
            new Order("O-04",  80_000L, true),
            new Order("O-05", 120_000L, true),
            new Order("O-06",  90_000L, false),
            new Order("O-07", 300_000L, true)
        );

        List<BatchMetric> fixedBatches = orders.stream()
            .filter(Order::paid)
            .gather(Gatherers.windowFixed(2))
            .map(GathererOrderReportDemo::toMetric)
            .toList();

        List<BatchMetric> movingBatches = orders.stream()
            .filter(Order::paid)
            .gather(Gatherers.windowSliding(3))
            .map(GathererOrderReportDemo::toMetric)
            .toList();

        System.out.println("FIXED");
        fixedBatches.forEach(System.out::println);

        System.out.println("SLIDING");
        movingBatches.forEach(System.out::println);
    }
}
```

Output:

```text
FIXED
BatchMetric[orderIds=[O-01, O-03], count=2, totalVnd=300000]
BatchMetric[orderIds=[O-04, O-05], count=2, totalVnd=200000]
BatchMetric[orderIds=[O-07], count=1, totalVnd=300000]

SLIDING
BatchMetric[orderIds=[O-01, O-03, O-04], count=3, totalVnd=380000]
BatchMetric[orderIds=[O-03, O-04, O-05], count=3, totalVnd=400000]
BatchMetric[orderIds=[O-04, O-05, O-07], count=3, totalVnd=500000]
```

### 21.1. Why are the results meaningful in business terms?

- **`filter(Order::paid)`** excludes the two unpaid orders.
- **`windowFixed(2)`** groups the remaining orders into batches of two; the last batch has only one order.
- **`windowSliding(3)`** computes three overlapping windows in the order of paid orders.
- **`map(toMetric)`** converts each window into a domain object, with the order count and total amount.
- **`toList()`** is the terminal operation that produces the final report.

If calculations must follow **actual payment timestamps**, the `orders` source must be ordered accordingly. A `List` preserving insertion order is not automatically the business chronological order.

### 21.2. Arithmetic limits

`long` can still overflow if the total amount is too large. For integer totals exceeding the 64-bit range, use `BigInteger`. For decimal currency, use `BigDecimal` according to rounding policies and currency units. Gatherers do not change the limits of numeric types.

## 22. Testing Gatherers and pipelines properly

Small tests should verify **public results** and input boundaries, rather than relying on internal implementation classes or callback invocation counts.

### 22.1. Testing built-in windows

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererContractDemo {
    public static void main(String[] args) {
        var fixed = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowFixed(3))
            .toList();

        var sliding = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var shortInput = Stream.of(1, 2)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var empty = Stream.<Integer>empty()
            .gather(Gatherers.windowFixed(3))
            .toList();

        if (!fixed.equals(List.of(
                List.of(1, 2, 3),
                List.of(4, 5)))) {
            throw new AssertionError("fixed mismatch");
        }

        if (!sliding.equals(List.of(
                List.of(1, 2, 3),
                List.of(2, 3, 4),
                List.of(3, 4, 5)))) {
            throw new AssertionError("sliding mismatch");
        }

        if (!shortInput.equals(List.of(List.of(1, 2)))) {
            throw new AssertionError("short-input mismatch");
        }

        if (!empty.isEmpty()) {
            throw new AssertionError("empty-input mismatch");
        }

        System.out.println("All checks passed");
    }
}
```

### 22.2. Testing custom Gatherers

For a custom Gatherer, you should check:

1. Empty, single-element, and multi-element sources.
2. Initial state and results across each element.
3. Emitting multiple outputs or emitting no outputs.
4. Behavior when downstream rejects.
5. Results when an integrator self-stops.
6. Exception cases in the integrator/finisher.
7. Ability to split and merge state if a combiner is present.
8. Ordered versus unordered inputs.
9. All constraints on I/O, resource closing, and numeric types.

If using `Integrator.ofGreedy`, in addition to testing you must review that **there is no `return false` path caused by an internal business condition**. That is a **contract**, not just a behavior observed on one machine.

## 23. Performance: when does a Gatherer bring benefits?

Gatherers can reduce the need to write hard-to-reuse multi-state loops, but **are not guaranteed to be faster** than sequential code, standard Stream operations, or a well-optimized loop.

Key factors:

| Factor | Impact |
| --- | --- |
| Window size `k` | State and memory grow with the number of elements that must be retained |
| Number of windows emitted | `windowSliding(k)` can emit nearly `N` windows when `N` is large |
| Metric computation cost | Each `window.stream().sum()` re-traverses elements in the window |
| Encounter order | Ordering constraints can limit splitting and merging |
| Custom Gatherer combiner | Without a valid merge strategy, it easily falls back to sequential execution |
| Boxing and allocation | `Stream<Integer>` and `List<Integer>` can allocate more than primitive streams |
| I/O and concurrent tasks | `mapConcurrent` is useful for some latency-bound tasks but has resource limits |

For example, if you only need **a sliding sum with a very large window `k`**, creating `List<T>` objects and recomputing the sum for each window may be more expensive than a custom Gatherer that keeps a running sum and drops the oldest element. However, a custom Gatherer must be carefully checked for:

- Overflow during addition and subtraction.
- Floating-point precision if using `double`.
- Incomplete windows.
- Sources without encounter order.
- Short-circuiting, exceptions, and state.
- Parallel execution capability.

**Optimize after correctness.** Use representative data and benchmarking tools such as JMH; do not draw conclusions from a single `System.nanoTime()` call.

## 24. Java 17/21 compatibility: what to do when you cannot upgrade the JDK yet?

Although Stream Gatherers became official in Java 24, many applications still set their minimum runtime to Java 17 or 21. In that case, `Stream.gather` from JDK 24 cannot be called directly.

There are three approaches:

- Use existing Stream operations (`filter`, `map`, `flatMap`, `reduce`, `collect`) if they sufficiently express the requirement.
- Use a loop, `Iterator`, or custom `Spliterator` to manage windows/state manually.
- Isolate the part requiring Java 24+ into a separate module/deployment artifact and clearly specify the required runtime.

Example replacing `windowFixed` with a loop over a finite `List` in Java 17:

```java
import java.util.ArrayList;
import java.util.List;

public class FixedWindowsLegacy {
    public static <T> List<List<T>> groupBySize(List<T> input, int size) {
        if (size < 1) {
            throw new IllegalArgumentException("size must be positive");
        }

        List<List<T>> result = new ArrayList<>();

        for (int start = 0; start < input.size();) {
            int end = start + Math.min(size, input.size() - start);
            result.add(List.copyOf(input.subList(start, end)));
            start = end;
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(groupBySize(
            List.of(1, 2, 3, 4, 5), 2
        )); // [[1, 2], [3, 4], [5]]
    }
}
```

This is an **equivalent solution in terms of results for finite lists without nulls**, not a full replica of a Gatherer. It materializes groups, is not a lazy intermediate operation, and does not share the same short-circuiting or parallel contracts.

When organizing a multi-JDK project, you must verify **the compiling JDK, `--release`, test-running JDK, CI environment, and actual runtime**. Enabling `--enable-preview` on Java 17/21 does not add the Java 24 Gatherers API.

## 25. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Thinking `Gatherer` and `Gatherers` are the same thing | Confusing interface with factory | Distinguish `Gatherer`, `Gatherers`, and `Stream.gather` |
| Calling `gather` on JDK 17/21 | API does not exist yet | Upgrade JDK or choose a compatible solution |
| Using JDK 22/23 without preview flags | Invalid compilation/execution | Enable preview in both compiler and runtime matching the JDK |
| Thinking `gather` is a terminal operation | Misunderstanding execution timing | Remember `gather` returns an intermediate Stream |
| Using Gatherer to replace simple `map` | Adds unnecessary complexity | Prefer built-in `map` or `filter` |
| Confusing `windowSliding(3)` with the last three minutes | Incorrect time-based results | Design explicit timestamp windows |
| Thinking `windowFixed` drops an incomplete final group | Losing or miscalculating the tail | Check group size according to requirements |
| Thinking `windowSliding(k)` always emits groups of full size k | Short sources still produce a short window | Handle the `0 < N < k` case |
| Placing `filter` before `gather` while assuming grouping on original data | Changes batch boundaries | Define pipeline order explicitly |
| Calling `IntStream.gather` directly | No such API exists | Convert with `boxed()` or use primitive algorithms |
| Using a global mutable `ArrayList` for parallel results | Data race or wrong order | Use `toList`/`collect` |
| Using `Integrator.ofGreedy` while self-stopping on a marker | Violates the Greedy contract | Use a regular Integrator |
| Ignoring `downstream.push` return value when emitting multiple elements | Continues working after rejection | Stop emitting when `push` returns `false` |
| Using `parallel()` assuming Gatherer automatically runs faster | Split/merge overhead may outweigh benefits | Benchmark and inspect the combiner |
| Forgetting to close `Files.lines` after `gather` | I/O resource leak | Use `try-with-resources` |
| Storing huge windows with `toList` | Sharp memory growth | Keep only needed metrics or use an incremental Gatherer |
| Computing money with `double` expecting exact precision | Binary floating-point rounding errors | Use `BigDecimal` with explicit rounding rules |

## 26. Practice exercises

### Exercise 1: Identifying the roles of the three API names

Explain the difference between `Stream.gather(...)`, `Gatherer<T,A,R>`, and `Gatherers`. In the expression `orders.stream().gather(Gatherers.windowFixed(10))`, which component creates the Gatherer and which component applies the Gatherer?

### Exercise 2: Comparing `filter` and Gatherer

Given `List.of(1, 2, 3, 4, 5)`. Use `filter` to get all even numbers. Then write a custom Gatherer with a Greedy Integrator that emits only even numbers. Explain why `filter` remains the recommended choice.

### Exercise 3: Two window types

For `[1,2,3,4,5,6,7]` and `k=3`, write out by hand the results of `windowFixed` and `windowSliding`, then run them with Java 24. Count the number of windows using the corresponding formulas.

### Exercise 4: Source shorter than the window

For `[1,2]` and `k=4`, predict the output of both window Gatherers. Write a pipeline that keeps only windows with `size() == 4` and explain why the result is empty.

### Exercise 5: Scan and reduce

For `[2,3,5]`, write a `scan` pipeline producing `[2,5,10]` and a `reduce`/`sum` pipeline producing `10`. How do the two results differ in **output count** and position in the pipeline?

### Exercise 6: Custom Integrator

Write a custom Gatherer that receives each `String` and emits its length. Use `Integrator.ofGreedy`. Then add the condition "stop if `STOP` is encountered" and explain why it must be changed to a regular Integrator.

### Exercise 7: Custom stateful Gatherer

Create a Gatherer that emits the running sum of `[3,5,-2,9]`. Where must the state be created? Why use `ofSequential` and not keep a shared static array?

### Exercise 8: Log report

Read a log file using `Files.lines`, group every 100 original lines with `windowFixed(100)`, and count the lines containing `ERROR` in each group. Compare with a pipeline that filters blank lines **before** grouping. Do both share the same batch definition?

### Exercise 9: Primitive Stream

From `IntStream.range(0, 100)`, use `boxed` then `windowFixed(10)`. Analyze the boxing and memory cost, then suggest a case where Gatherer should not be used.

### Exercise 10: Parallel semantics

Use `parallelStream` with `windowSliding(3)` on an ordered `List`. Compare the result with sequential execution. Why must ordering and the combiner be checked, and why does `parallel()` not guarantee higher speed?

### Exercise 11: Without JDK 24

Propose a way to create three-element batches in an application required to run on Java 17. Compare a loop over a `List` with using a standard Gatherer on Java 24 in terms of lazy processing capability and memory consumption.

### Exercise 12: Choosing an API

For the requirement "average of the 10 most recent measurements per device by timestamp", describe the pipeline or architecture before writing code. What questions should be asked about devices, timestamp ordering, late-arriving records, and cases with fewer than 10 samples?

## 27. Self-check questions

- Is `Stream.gather` an intermediate or terminal operation?
- What roles do `Gatherer`, `Gatherers`, and `gather` play?
- Why does `Gatherer<T,A,R>` have three type parameters?
- What do `initializer`, `integrator`, `combiner`, and `finisher` solve?
- Is an Integrator allowed to emit 0 or many elements when receiving one element?
- How does `windowFixed(k)` differ from `windowSliding(k)`?
- What happens with `windowSliding(3)` when the source has only two elements?
- How do `scan` and `fold` differ in emission timing and output count?
- When might `mapConcurrent` be more suitable than `parallelStream`?
- What does `Integrator.ofGreedy` commit to? When must a regular Integrator be used?
- Why does `ofSequential` relate to state-merging capability yet is not synonymous with Greedy?
- Why is there no direct `IntStream.gather` in Java 24?
- What role does encounter order play for windows?
- When does a Gatherer only make code more complex than `map`/`filter`?
- Why must `Files.lines` still be closed after `gather`?
- In which versions were Stream Gatherers in preview and final status?

## 28. References

Standard sources to look up API behavior and changes across versions:

1. [JEP 461 — Stream Gatherers (Preview)](https://openjdk.org/jeps/461): preview stage in Java 22.
2. [JEP 473 — Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473): second preview stage in Java 23.
3. [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): standardized starting in Java 24.
4. [Java SE 24 — `Stream`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html): the `gather` method and pipeline contract.
5. [Java SE 24 — `Gatherer`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer, integrator, combiner, and finisher.
6. [Java SE 24 — `Gatherers`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): `windowFixed`, `windowSliding`, `scan`, `fold`, and `mapConcurrent`.
7. [Java SE 24 — `Gatherer.Integrator`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): behavior of `integrate`, `of`, and `ofGreedy`.
8. [Oracle — Stream Gatherers Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): guide to applying Gatherers in pipelines.

**Remember:** **`Stream.gather(...)` is an intermediate operation**, **`Gatherer` is the contract describing how to process**, and **`Gatherers` provides the built-in Gatherers**. They extend the Stream API to allow windowing, stateful processing, and emitting multiple intermediate results, but **do not replace** `filter`, `map`, `flatMap`, `reduce`, or `collect` when those operations already fit. Gatherers were **preview in Java 22/23** and **official starting in Java 24**. When using them, always verify source ordering, stopping rules, parallelizability, numeric types, resource lifecycles, and memory cost.
