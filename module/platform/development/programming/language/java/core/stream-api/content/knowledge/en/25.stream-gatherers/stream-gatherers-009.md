# Handling Ordering, Infinite Sources, and Short-Circuiting with Gatherers

## 1. Problem: a transformation does more than take one element and return one element

In the **JAVA_STREAM_API** module, pipelines using `filter`, `map`, `reduce`, and `collect` solve many declarative data-processing requirements. However, some transformations must **remember state**, **emit more or fewer elements than received**, or **decide to stop processing the source as soon as a condition is met**:

- Group consecutive measurements into 3-element windows.
- Compute a running total after each transaction, instead of returning only a final sum.
- Take events up to **and including** an end-marker event.
- Read a potentially infinite stream, taking only the first 5 results without exhausting the source.
- Concurrently map expensive elements while still returning results in encounter order.

Starting from **Java 24**, the `Gatherer` interface and `Stream.gather(...)` method are standard APIs. Built-in transformations in `Gatherers` include `windowFixed`, `windowSliding`, `scan`, `fold`, and `mapConcurrent`. A custom gatherer can also control when to request **short-circuiting**.

In this lesson from the **Stream Gatherer** chapter, we focus on **three axes of correctness**:

1. **Ordering**: distinguishing encounter order, worker thread execution order, and final output order.
2. **Infinite sources**: determining whether a transformation produces results incrementally or must wait for the source to end.
3. **Short-circuiting**: understanding the two signals `Integrator.integrate(...)` returning `false` and `Downstream.push(...)` returning `false`; coordinating with `limit`, `findFirst`, and other terminal operations.

After this lesson, learners can design stateful sequential custom gatherers, explain why a pipeline can hang forever even with `limit(1)`, test results without relying on timing/thread scheduling, and manage I/O source lifecycles properly.

### 1.1. Three-tier diagram

```text
Source                           Gatherer                        Downstream
┌─────────────────┐             ┌────────────────────────┐      ┌─────────────────────┐
│ Stream<T>       │  input T    │ initializer()          │  R   │ filter/map/limit   │
│ ordered?        ├────────────►│ integrator()           ├─────►│ findFirst/toList   │
│ finite/infinite?│             │ state A                │      │                     │
│ resource-backed?│             │ combiner()/finisher()  │      │ accept more?        │
└─────────────────┘             └────────────────────────┘      └─────────────────────┘
                                           │                            │
                                           │  false: stop intake        │
                                           ◄────────────────────────────┘
                                               push() == false
```

A gatherer can **emit nothing** for an input, emit **one**, or emit **many**. Correctness depends on both **emission conditions** and **stopping conditions**.

## 2. JDK version and running the examples

| Version | Status of Stream Gatherers | Notes |
| --- | --- | --- |
| Java 8–21 | No `Gatherer` in standard API | Use existing Stream operations or write custom logic |
| JDK 22 | Stream Gatherers in **first preview** | Requires `--enable-preview`, API may change |
| JDK 23 | **Second preview** | Still requires `--enable-preview` |
| **JDK 24 and later** | **Official API** | No preview flag needed for `Gatherer` |

All **complete code** and tests in this lesson target **JDK 24+**. Do not copy Java 24 code verbatim to compile with `--release 22` or `--release 23` expecting 100% compatibility with preview APIs: read the exact Javadoc of the release you use.

Example on a machine with JDK 24:

```bash
javac --release 24 GathererOrderAndStopDemo.java
java GathererOrderAndStopDemo
```

Do not add `--enable-preview` for JDK 24 examples. For a project constrained to JDK 17 or JDK 21, choose an alternative approach and do not invoke an API missing from the target runtime.

Official reference documentation:

- [`Gatherer` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- [`Gatherer.Integrator` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html)
- [`Gatherer.Downstream` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [`Gatherers` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html)
- [`Stream.gather` — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer))

## 3. Core contract of `Gatherer<T,A,R>`

A gatherer has three type parameters:

- `T`: type of source elements the gatherer receives.
- `A`: type of intermediate accumulated state, which may be mutable.
- `R`: type of result elements pushed downstream.

Key components:

| Component | Function | What to check |
| --- | --- | --- |
| `initializer()` | Creates new state `A` if needed | Never accidentally share state across runs |
| `integrator()` | Receives each `T`, updates `A`, calls downstream to emit `R` | Handle stop signals and ordering properly |
| `combiner()` | Merges states when parallel evaluation is possible | Provide only if correctness under partition/merge is proven |
| `finisher()` | Runs final step and may emit final results | Does it wait for EOF? Does it check if downstream is rejecting? |
| `andThen(...)` | Composes gatherers | Stop signals must propagate validly through the chain |

Integrator signature:

```java
@FunctionalInterface
interface Integrator<A, T, R> {
    boolean integrate(
        A state,
        T element,
        Gatherer.Downstream<? super R> downstream
    );
}
```

Meaning of the return value:

- `true`: the gatherer **can continue receiving** source elements if the pipeline still demands them.
- `false`: the gatherer requests **stopping further input** to it; no more inputs remain to integrate.

This stop signal is **pipeline control**, not a boolean filter predicate for the current element. Returning `false` emits no element on its own; to include the final element in results, call `downstream.push(element)` at the right moment.

### 3.1. Do not share state between two pipelines

Lifecycle mistake:

```java
// Counterexample: counter captured outside gatherer and shared across runs.
// AtomicInteger global = new AtomicInteger();
// Gatherer<Integer, ?, Integer> g = Gatherer.ofSequential(
//     (ignored, n, downstream) ->
//         global.incrementAndGet() <= 5 && downstream.push(n)
// );
```

Even though `AtomicInteger` is safe for concurrent increments, shared state makes separate stream runs **interfere with each other**. For a stateful gatherer, place state in `initializer()` so every evaluation gets its own state.

### 3.2. Do not retain state or downstream to emit later

Per the `Gatherer` contract, do not retain, leak, or share references to state or `Downstream` beyond the scope of the invocation currently running. Never stash `downstream` in a static field and call `push` from an asynchronous callback seconds later: that is neither a reactive stream model nor contract-safe.

## 4. Encounter order: source order differs from execution order

**Encounter order** is the order of elements defined by the source and intermediate operations. For example, `List`, arrays, and `IntStream.range` have encounter order. Some sources such as `HashSet` do not promise order, and `BaseStream.unordered()` can drop the requirement to maintain encounter order.

Ordered example:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> windows = List.of(1, 2, 3, 4, 5, 6, 7)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7]]
```

Windows consist of **consecutive elements in encounter order**, not values automatically sorted ascending. If the source is `List.of(7, 1, 5, 4)`, windows of size 2 will be `[7,1]` and `[5,4]`.

### 4.1. `parallel()` does not mean ordered results get scrambled

`parallel()` only expresses an intent for parallel evaluation. For a pipeline with encounter order and order-preserving operations, `toList()` must still follow encounter order. However, **mapper invocations across workers may occur in a different order**.

```java
import java.util.stream.IntStream;

List<Integer> ordered = IntStream.range(1, 10)
    .boxed()
    .parallel()
    .gather(Gatherers.mapConcurrent(3, n -> n * 10))
    .toList();

System.out.println(ordered);
// [10, 20, 30, 40, 50, 60, 70, 80, 90]
```

`Gatherers.mapConcurrent` uses **virtual threads**, bounds concurrent tasks by `maxConcurrency`, and **preserves the stream's result order** per Javadoc. This does not mean mappers execute sequentially from 1 → 9. Tasks can finish at different times. If the input is already unordered, do not impose an order the source does not have.

### 4.2. `forEach` and `forEachOrdered`

```java
List<Integer> input = List.of(1, 2, 3, 4);

input.parallelStream()
    .gather(Gatherers.mapConcurrent(2, n -> n * 2))
    .forEach(System.out::println);
// Print line order is not guaranteed.

input.parallelStream()
    .gather(Gatherers.mapConcurrent(2, n -> n * 2))
    .forEachOrdered(System.out::println);
// 2, 4, 6, 8 in encounter order.
```

`forEachOrdered` preserves order at the terminal stage, though with coordination cost. Do not use log order or thread names to assert final data ordering.

### 4.3. When calling `unordered()`

```java
var result = IntStream.range(1, 7)
    .boxed()
    .unordered()
    .gather(Gatherers.windowFixed(2))
    .toList();
```

The pipeline above **must not be tested assuming groups are always `[1,2]`, `[3,4]`, `[5,6]`** under an ordered source contract. `unordered()` drops that constraint. If the business rule requires "three consecutive events", keep an ordered source and do not blindly call `unordered()` as an optimization.

**Rule:** if a transformation relies on **preceding/following elements**, define "before/after" with a reliable data ordering. Thread completion timing cannot substitute for encounter order.

## 5. `Gatherers.windowFixed`: fixed batching and ordering

`Gatherers.windowFixed(windowSize)` groups consecutive elements into **non-overlapping** windows:

```java
List<List<Integer>> result = List.of(10, 20, 30, 40, 50, 60, 70)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(result);
// [[10, 20, 30], [40, 50, 60], [70]]
```

Characteristics:

- `windowSize` must be **greater than 0**, otherwise `IllegalArgumentException` is thrown.
- Each window consists of consecutive elements in encounter order.
- When a finite source has a remainder smaller than `windowSize`, **the final window can be smaller than requested**.
- An empty source creates no windows.
- Returned window `List`s are **unmodifiable**; do not rely on a specific implementation class or serialization.
- A huge window size can consume significant memory even when the source stream is small.

### 5.1. Fixed windows on an infinite source

```java
import java.util.stream.Stream;

List<List<Long>> firstTwo = Stream.iterate(1L, n -> n + 1L)
    .gather(Gatherers.windowFixed(3))
    .limit(2)
    .toList();

System.out.println(firstTwo);
// [[1, 2, 3], [4, 5, 6]]
```

The `Stream.iterate(1L, n -> n + 1L)` source **has no natural endpoint**. The pipeline above still completes because:

1. The gatherer emits a window once three elements accumulate.
2. `limit(2)` needs two windows and then stops accepting results.
3. The stop signal propagates through the pipeline without waiting for the infinite source to end.

**Never assert that the framework calls the source generator exactly 6 times in every mode or implementation.** Pipelines may perform buffering, lookahead, or start work before downstream stops. What can be verified per contract is **the contents of the two windows** and that the computation has a termination path.

### 5.2. Source smaller than one window

```java
List<List<Integer>> partial = Stream.of(1, 2)
    .gather(Gatherers.windowFixed(5))
    .toList();

System.out.println(partial); // [[1, 2]]
```

Here, the gatherer's `finisher`/completion stage emits the incomplete final window once the finite source **has ended**. With an infinite source that never reaches window size and never ends, there is no natural way to "end and emit the remaining window".

## 6. `Gatherers.windowSliding`: overlapping windows

`windowSliding(size)` maintains a sliding window: the first element of the old window is dropped, and the new element is appended.

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Window `List`s are **unmodifiable**. For a source with fewer elements than `size`, Javadoc specifies **one window containing all elements** if the source is non-empty:

```java
System.out.println(Stream.of(5, 9)
    .gather(Gatherers.windowSliding(4))
    .toList());
// [[5, 9]]
```

An empty source gives an empty list of windows. `windowSize < 1` is invalid.

### 6.1. Infinite sources need output limits

```java
List<List<Integer>> firstThree = Stream.iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(3)
    .toList();

System.out.println(firstThree);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Once enough data arrives for the first window, the gatherer emits another window for each subsequent element received. A trailing `limit(3)` supplies a stopping condition with a finite result.

### 6.2. Window size determines output latency

With a window size of 1,000,000, `findFirst()` **will not necessarily return immediately**, because the gatherer must accumulate enough data for one complete window or wait for a finite source to finish to emit the trailing partial window. If an infinite source keeps producing data, it can eventually fill, though latency and memory depend on source speed and window size.

**Do not** treat `limit(1)` or `findFirst()` as a guarantee of "read one source element and return a result". They cap **output elements**, not automatically **how many input elements the gatherer must consume**.

## 7. `scan` and `fold`: two accumulations with different completion behavior

`Gatherers.scan(initial, scanner)` emits a result **after every input**. `Gatherers.fold(initial, folder)` emits only **one final accumulated result** when collection finishes normally.

### 7.1. `scan`: incremental output

```java
List<Long> prefixSums = Stream.of(2L, 3L, 5L)
    .gather(Gatherers.scan(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .toList();

System.out.println(prefixSums); // [2, 5, 10]
```

The `0L` is only the initial state; it is **not emitted as a separate result element**. After the first input `2`, the result is `2`.

### 7.2. `scan` on an infinite source

```java
List<Long> runningTotals = Stream.iterate(1L, n -> n + 1L)
    .gather(Gatherers.scan(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .limit(5)
    .toList();

System.out.println(runningTotals);
// [1, 3, 6, 10, 15]
```

Each input yields one prefix sum. A trailing `limit(5)` can take five results without waiting for EOF on the infinite source.

### 7.3. `fold`: waits for the source to end

```java
List<Long> oneTotal = Stream.of(2L, 3L, 5L)
    .gather(Gatherers.fold(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .toList();

System.out.println(oneTotal); // [10]
```

With an infinite source, the code below **has no natural termination path**:

```java
// DO NOT RUN in demos or unit tests:
// Stream.iterate(1L, n -> n + 1L)
//     .gather(Gatherers.fold(() -> 0L, Long::sum))
//     .limit(1)
//     .toList();
```

`limit(1)` asks for one **fold result**, yet fold normally does not emit a result until all input has been consumed. The infinite source never ends, so fold has no result for downstream to receive. This is a classic example showing **downstream short-circuiting does not guarantee termination if an earlier stage emits nothing**.

If the requirement is "sum of the first 100 numbers", place `limit` **before `fold`**:

```java
List<Long> first100Total = Stream.iterate(1L, n -> n + 1L)
    .limit(100)
    .gather(Gatherers.fold(
        () -> 0L,
        (sum, next) -> Math.addExact(sum, next)
    ))
    .toList();

System.out.println(first100Total); // [5050]
```

**Where `limit` is placed is a semantic choice**, not just an optimization:

```text
Infinite source → limit(100) → fold → one final sum       (has termination path)
Infinite source → fold → limit(1)   → waits forever       (no EOF)
Infinite source → scan → limit(100) → 100 running totals  (has termination path)
```

## 8. Two stop signals that must be understood separately

### 8.1. `Integrator.integrate` returns `false`

A custom gatherer can decide "stop milestone reached, accept no more source elements". This is **active short-circuiting initiated by the gatherer**.

For example, taking values up to **and including** the first number greater than or equal to 5:

```java
// [1, 2, 3, 4, 5], then requests stopping the source.
Stream.iterate(1, n -> n + 1)
    .gather(takeUntilInclusive(n -> n >= 5))
    .toList();
```

`takeUntilInclusive` is implemented in full in section 11.

### 8.2. `Downstream.push(value)` returns `false`

`downstream.push(value)` forwards the value to the next stage and returns:

- `true` when downstream can still accept more.
- `false` when downstream **will accept no more elements**. Subsequent `push` calls on the same downstream will also return `false`.

An integrator wishing to support short-circuiting should **observe and propagate** that signal, for instance:

```java
boolean wantsMore = downstream.push(element);
return wantsMore;
```

Once downstream has received the single result needed by `findFirst` or the `N` elements needed by `limit(N)`, continuing to call `push` does wasted work and can make logic harder to reason about.

### 8.3. `Downstream.isRejecting()` is a helper signal, not an absolute prediction

`downstream.isRejecting()` returns `true` if downstream is **already known** to want no more; this is a **best-effort** check. Returning `false` **does not guarantee** that the next `push` will definitely be accepted.

Therefore:

- Before doing an expensive operation to construct an output, you may check `isRejecting()`.
- Still check **the return value from `push`** when actually emitting data.
- Never use `isRejecting()` as a pause/resume mechanism or asynchronous backpressure.

### 8.4. Stop control flow diagram

```text
                  integrator(state, input, downstream)
                                │
                     Any element to emit?
                         /             \
                        No            Yes
                         │              │
              Stop input?          downstream.push(output)
                   /     \              │
                 Yes     No        true / false
                 │        │          │     │
              return    return     may     stop emitting,
              false     true    accept more return false
```

The `integrator == false` signal can also happen **without emitting output**, such as when detecting an error condition or a stop marker that should not enter the results.

## 9. `Integrator.ofGreedy` is not for active short-circuiting

`Gatherer.Integrator.Greedy` indicates an integrator that **never initiates stopping the source itself**; it only reflects downstream's unwillingness to accept more. Therefore, the JDK may optimize by skipping the boolean check on a greedy integrator in certain scenarios.

Valid usage example:

```java
Gatherer<Integer, ?, Integer> doubleValues =
    Gatherer.ofSequential(
        Gatherer.Integrator.ofGreedy(
            (ignored, n, downstream) -> downstream.push(n * 2)
        )
    );

List<Integer> result = Stream.of(1, 2, 3)
    .gather(doubleValues)
    .toList();
// [2, 4, 6]
```

Because the integrator simply transforms the element and returns `push`, it needs no stop milestone of its own. However, if you want to **stop accepting input when encountering 5 even while downstream is still ready**, you must use a **regular Integrator** (`ofSequential` with a regular lambda or `Integrator.of(...)`), **not `ofGreedy`** returning `false` for a custom condition.

**Contract violation:**

```java
// Counterexample: greedy yet actively returns false when n == 5.
// Gatherer.Integrator.ofGreedy(
//     (state, n, downstream) -> n != 5 && downstream.push(n)
// )
```

In an implementation that optimizes away checking the greedy boolean return value, the counterexample's stop rule may fail to execute as intended.

## 10. Downstream short-circuiting does not mean upstream is called exactly once

Given a pipeline:

```java
var first = Stream.iterate(0, n -> n + 1)
    .gather(Gatherers.scan(
        () -> 0L,
        (sum, next) -> sum + next
    ))
    .findFirst();
```

The result can be obtained as soon as the gatherer first emits a value, yet **you should not write specifications requiring mapper, supplier, finisher, or upstream to be called an exact number of times**. The Stream API is permitted to use buffering, speculative work, or optimizations, especially in parallel execution.

### 10.1. Do not place business side effects in mapper expecting "runs only N times"

```java
// Do not do:
// Stream.generate(() -> paymentApi.chargeCard())
//     .gather(Gatherers.mapConcurrent(8, this::validate))
//     .limit(1)
//     .findFirst();
```

When the gatherer or upstream has concurrency, multiple tasks may already have started before downstream decides to stop. `Gatherers.mapConcurrent` only **attempts to cancel** unfinished work on a best-effort basis; it does not guarantee that all external side effects not yet completed will be retracted.

For payments, database writes, or notifications, separate irreversible operations from a pipeline with speculative work, or design **idempotency**, transactions, and retry/cancellation policies at the application layer.

### 10.2. Different kinds of "stopped"

| Mechanism | Who emits the signal? | Effect |
| --- | --- | --- |
| `integrate(...) == false` | Gatherer | Stops receiving input per gatherer contract |
| `downstream.push(...) == false` | Downstream | Wants to receive no more output |
| `limit(N)` | Subsequent intermediate stage | Needs at most `N` output elements |
| `findFirst` | Terminal operation | Needs only the first element in encounter order |
| `anyMatch` / `noneMatch` | Terminal operation | Stops as soon as the result is determined |
| `takeWhile` | Intermediate stage | Stops when predicate ceases to hold on an ordered stream |
| `Stream.close()` | Owner/caller | Releases resources, **not** a terminal computation replacing `collect` |

**Remember:** stopping computation, stopping data emission, and closing resources are three distinct responsibilities.

## 11. Custom Gatherer: taking up to and including a marker element

`Stream.takeWhile(predicate)` (Java 9+) takes elements **while the condition remains true** and **does not emit the first element that fails the predicate** on an ordered stream. Meanwhile, some problems require **keeping the closing marker**:

```text
Input:  [10, 20, 30, -1, 40, 50, ...]
Target: [10, 20, 30, -1]
                      ^
                keep marker element
```

This is a case where a Gatherer fits better than `takeWhile(n -> n != -1)`, because `takeWhile` would only return `[10,20,30]`.

### 11.1. Algorithm idea

For each element:

1. Call `downstream.push(element)` **first** so the current element (including the marker) is emitted.
2. Check whether the predicate indicates this is a stop element.
3. Return `false` if downstream rejects **or** the predicate signals the stop milestone was reached.
4. Return `true` otherwise.

Because the gatherer needs to actively stop on the predicate, **do not use `Integrator.ofGreedy`**.

```java
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, T> takeUntilInclusive(
    Predicate<? super T> stopWhen
) {
    Objects.requireNonNull(stopWhen, "stopWhen");
    return Gatherer.<T, T>ofSequential(
        (unusedState, element, downstream) -> {
            boolean wantsMore = downstream.push(element);
            return wantsMore && !stopWhen.test(element);
        }
    );
}
```

Here, the `ofSequential(Integrator<Void,T,R>)` overload needs no state because the stopping condition depends only on **the current element** and the predicate. `Void` is the default state type of this overload; `unusedState` is unused.

### 11.2. Finite and infinite sources

```java
List<Integer> finite = Stream.of(10, 20, 30, -1, 40)
    .gather(takeUntilInclusive(n -> n == -1))
    .toList();

System.out.println(finite); // [10, 20, 30, -1]

List<Integer> infinite = Stream.iterate(1, n -> n + 1)
    .gather(takeUntilInclusive(n -> n >= 5))
    .toList();

System.out.println(infinite); // [1, 2, 3, 4, 5]
```

The second example **does not put `limit` afterward**. It still terminates because the Gatherer itself returns `false` after pushing element 5. This is **active short-circuiting** from the integrator, distinct from downstream `limit(5)`.

### 11.3. What if the stop milestone never appears?

If a finite source has no marker, the Gatherer above emits all data and finishes when the source ends. If an infinite source never satisfies `stopWhen` and downstream does not stop either, the pipeline **never completes**:

```java
// DO NOT RUN: infinite source always emits 1L, predicate is always false.
// Stream.iterate(1L, n -> n)
//     .gather(takeUntilInclusive(n -> n < 0L))
//     .toList();
```

In real systems, include **a safeguard limit** (element count, deadline, resource limit) if the marker might be missing. However, adding `limit` without specifying where data is truncated turns a complete report into a partial report; document the contract explicitly.

### 11.4. Be careful if the predicate has side effects

The example calls `downstream.push(element)` before evaluating `stopWhen.test(element)`. If downstream already rejected the next element, the `&&` expression does not invoke the predicate. Therefore, **never place mandatory actions** inside the predicate (writing invoices, incrementing audit counters, calling external APIs). Predicates should be pure and non-interfering.

## 12. Stateful custom Gatherer: taking at most N elements

`Stream.limit(N)` already solves this problem in most situations. Let's implement an equivalent Gatherer for **N > 0** to understand how to manage **per-run private state** and coordinate both kinds of stop signals.

```java
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, T> firstN(int max) {
    if (max <= 0) {
        throw new IllegalArgumentException("max must be greater than 0");
    }

    class Counter {
        int emitted;
    }

    return Gatherer.<T, Counter, T>ofSequential(
        Counter::new,
        (state, element, downstream) -> {
            if (state.emitted >= max) {
                return false;
            }

            state.emitted++;
            boolean wantsMore = downstream.push(element);
            return wantsMore && state.emitted < max;
        }
    );
}
```

**Analysis:**

- `Counter::new` creates fresh state; there is no shared external counter variable.
- Each element is emitted once; `emitted` increments before checking the limit.
- When `max` is reached, the integrator returns `false` **immediately after emitting the N-th element**, without waiting to receive one more input to discover it.
- When downstream returns `false`, the integrator also returns `false` even before reaching `max`.
- For `max == 0`, the example intentionally rejects the input to avoid pretending no elements were read; use **`Stream.limit(0)`** if the goal is an empty result directly at the source.

Usage:

```java
List<Integer> firstFour = Stream.iterate(1, n -> n + 1)
    .gather(firstN(4))
    .toList();

System.out.println(firstFour); // [1, 2, 3, 4]
```

### 12.1. Why does `ofSequential` fit better than a DIY combiner?

`firstN` depends on **element order** and the count already emitted in the prefix. If the source is split into two halves, you cannot simply take each half's counter and add them while guaranteeing "the exact first N elements" and stopping at the desired point.

`Gatherer.ofSequential` provides **a default combiner requiring the gatherer to be evaluated sequentially**. This avoids writing a bogus combiner that seems to work on small data yet breaks under parallel execution.

### 12.2. Parallel execution must still yield the right result

```java
List<Integer> result = java.util.stream.IntStream.rangeClosed(1, 10)
    .boxed()
    .parallel()
    .gather(firstN(4))
    .toList();
// Result must obey firstN semantics on an ordered source.
```

Do not infer from calling `parallel()` that stateful accumulation must run across multiple branches simultaneously. A Gatherer without a suitable combiner is evaluated **sequentially at the gather stage itself**. Other parts of the pipeline may have their own execution strategies; never write tests asserting thread counts or evaluation timing.

## 13. Complete Java 24 program: three stopping styles and two source types

The following program is independent of the isolated snippets above. Save it in `GathererOrderAndStopDemo.java` and run on **JDK 24+**.

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public final class GathererOrderAndStopDemo {

    private GathererOrderAndStopDemo() {}

    public static <T> Gatherer<T, ?, T> takeUntilInclusive(
        Predicate<? super T> stopWhen
    ) {
        Objects.requireNonNull(stopWhen, "stopWhen");
        return Gatherer.<T, T>ofSequential(
            (state, element, downstream) -> {
                boolean wantsMore = downstream.push(element);
                return wantsMore && !stopWhen.test(element);
            }
        );
    }

    public static <T> Gatherer<T, ?, T> firstN(int max) {
        if (max <= 0) {
            throw new IllegalArgumentException(
                "max must be greater than 0"
            );
        }

        class Counter {
            int emitted;
        }

        return Gatherer.<T, Counter, T>ofSequential(
            Counter::new,
            (state, element, downstream) -> {
                if (state.emitted >= max) {
                    return false;
                }

                state.emitted++;
                boolean wantsMore = downstream.push(element);
                return wantsMore && state.emitted < max;
            }
        );
    }

    public static List<List<Integer>> firstTwoFixedWindows() {
        return Stream.iterate(1, n -> n + 1)
            .gather(Gatherers.windowFixed(3))
            .limit(2)
            .toList();
    }

    public static List<List<Integer>> firstTwoSlidingWindows() {
        return Stream.iterate(1, n -> n + 1)
            .gather(Gatherers.windowSliding(3))
            .limit(2)
            .toList();
    }

    public static List<Long> firstFiveRunningTotals() {
        return Stream.iterate(1L, n -> n + 1L)
            .gather(Gatherers.scan(
                () -> 0L,
                (sum, next) -> Math.addExact(sum, next)
            ))
            .limit(5)
            .toList();
    }

    public static List<Long> foldFirstFive() {
        return Stream.iterate(1L, n -> n + 1L)
            .limit(5) // Important: cap INPUT before fold.
            .gather(Gatherers.fold(
                () -> 0L,
                (sum, next) -> Math.addExact(sum, next)
            ))
            .toList();
    }

    public static List<Integer> untilFiveInclusive() {
        return Stream.iterate(1, n -> n + 1)
            .gather(takeUntilInclusive(n -> n >= 5))
            .toList();
    }

    public static List<Integer> firstThree() {
        return Stream.iterate(1, n -> n + 1)
            .gather(firstN(3))
            .toList();
    }

    public static List<Integer> concurrentOrdered() {
        return Stream.of(5, 1, 4, 2, 3)
            .gather(Gatherers.mapConcurrent(3, n -> n * 10))
            .toList();
    }

    public static void main(String[] args) {
        System.out.println(firstTwoFixedWindows());
        // [[1, 2, 3], [4, 5, 6]]

        System.out.println(firstTwoSlidingWindows());
        // [[1, 2, 3], [2, 3, 4]]

        System.out.println(firstFiveRunningTotals());
        // [1, 3, 6, 10, 15]

        System.out.println(foldFirstFive());
        // [15]

        System.out.println(untilFiveInclusive());
        // [1, 2, 3, 4, 5]

        System.out.println(firstThree());
        // [1, 2, 3]

        System.out.println(concurrentOrdered());
        // [50, 10, 40, 20, 30]
    }
}
```

Key takeaway: the program uses **infinite sources**, yet **has no terminal operation waiting for an infinite source to finish on its own**. Each pipeline either uses an incrementally emitting gatherer combined with `limit`, returns `false` on its own to stop the source, or caps the source to finite size **before `fold`**.

### 13.1. How to compile

```bash
javac --release 24 GathererOrderAndStopDemo.java
java GathererOrderAndStopDemo
```

These commands require a compiler supporting `--release 24`; do not use `--release 17` because Java 17 lacks `Stream.gather`. With Java 24, Gatherers are an official API.

### 13.2. Why does the example use `Stream.iterate` instead of `Stream.generate`?

`Stream.iterate(seed, next)` has encounter order, useful when testing "the first N values" or consecutive windows. `Stream.generate(supplier)` is specified as an **unordered** source, even though when run sequentially the supplier is still called to generate values. When results carry positional meaning in order, use a source and operations with explicit encounter order.

## 14. A custom Gatherer needing `finisher`: handling the trailing window

`Gatherers.windowFixed` already implements the behavior of a final window shorter than the requested size. However, to clearly understand the role of `finisher`, we can build a batching gatherer ourselves.

**Requirements:**

- Emit a `List<T>` whenever `size` elements are collected.
- When finite input ends with a remainder, emit **one final batch**.
- Stop emitting if downstream is already rejecting.
- Do not retain a mutable reference to the internal buffer in emitted results.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, List<T>> batches(int size) {
    if (size < 1) {
        throw new IllegalArgumentException(
            "size must be greater than 0"
        );
    }

    class State {
        final ArrayList<T> pending = new ArrayList<>(size);
    }

    return Gatherer.<T, State, List<T>>ofSequential(
        State::new,
        (state, element, downstream) -> {
            Objects.requireNonNull(element, "element");
            state.pending.add(element);

            if (state.pending.size() == size) {
                List<T> batch = List.copyOf(state.pending);
                state.pending.clear();
                return downstream.push(batch);
            }

            return !downstream.isRejecting();
        },
        (state, downstream) -> {
            if (!state.pending.isEmpty() &&
                    !downstream.isRejecting()) {
                downstream.push(List.copyOf(state.pending));
            }
        }
    );
}
```

**Data policy:** the example explicitly rejects `null` elements via `Objects.requireNonNull`; `List.copyOf` also rejects null. If the source has valid nulls, design another representation instead of pretending nulls cannot occur.

### 14.1. Testing on finite sources

```java
System.out.println(Stream.of("A", "B", "C", "D", "E")
    .gather(batches(2))
    .toList());
// [[A, B], [C, D], [E]]

System.out.println(Stream.<String>empty()
    .gather(batches(2))
    .toList());
// []
```

For the final batch `[E]`, the completion stage after EOF emits the remainder; there is no need to call `push` on every input.

### 14.2. Caution on infinite sources

An infinite source **has no EOF** to trigger "emit the trailing remainder batch", though the gatherer can continuously emit **full batches**:

```java
List<List<Integer>> firstTwo = Stream.iterate(1, n -> n + 1)
    .gather(batches(2))
    .limit(2)
    .toList();

System.out.println(firstTwo);
// [[1, 2], [3, 4]]
```

If `size` is very large and downstream only needs one batch, the gatherer still has to accumulate `size` inputs before emitting. If the source produces items slowly, `findFirst` does not make the batch appear earlier than the accumulation requirement allows.

### 14.3. Why copy the buffer when emitting?

If you call `downstream.push(state.pending)` and then `state.pending.clear()`, previously emitted lists will **lose their data** because they share the same mutable reference. `List.copyOf(state.pending)` creates a structurally unmodifiable snapshot for each batch.

With mutable element objects, the objects inside the list can still change; `List.copyOf` is not a deep copy. With parallel pipelines, `ofSequential` keeps stateful logic ordered without needing an incorrect combiner.

## 15. `andThen` and multiple Gatherers in one pipeline

`Gatherer.andThen(other)` creates a composite gatherer: the `R` output of the first gatherer becomes the input of the next. An alternative syntax is calling `Stream.gather(...)` multiple times.

Example: split fixed windows and then scan **window sizes**:

```java
List<Integer> runningCounts = Stream.of(1, 2, 3, 4, 5, 6, 7)
    .gather(Gatherers.windowFixed(3))
    .map(List::size)
    .gather(Gatherers.scan(
        () -> 0,
        Integer::sum
    ))
    .toList();

System.out.println(runningCounts); // [3, 6, 7]
```

In this pipeline:

1. `windowFixed(3)` emits `[1,2,3]`, `[4,5,6]`, `[7]`.
2. `map(List::size)` emits `3`, `3`, `1`.
3. `scan` accumulates into `3`, `6`, `7`.

Do not confuse `limit(2)` before and after `windowFixed`:

```java
// Limit input count: 2 elements -> one short window.
Stream.of(1, 2, 3, 4, 5)
    .limit(2)
    .gather(Gatherers.windowFixed(3))
    .toList(); // [[1, 2]]

// Limit OUTPUT count: 2 windows -> may contain up to 6 inputs.
Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .limit(2)
    .toList(); // [[1, 2, 3], [4, 5]]
```

The JDK may optimize a gatherer chain, yet **must not** alter the contracted semantics. Do not write programs that depend on a particular gatherer stage running on a specific thread or being invoked an exact number of times unless guaranteed by the API.

## 16. Parallelism, combiners, and limits of source splitting

### 16.1. Without a combiner, a stateful gatherer is usually sequential

For a gatherer with prefix-dependent state, such as `scan` or `takeUntilInclusive`, splitting input into multiple regions and merging state at the end **is not trivial**. `ofSequential` offers a safe choice: the gatherer **is evaluated sequentially**, even when the outer stream has parallel mode enabled.

Do not conclude `ofSequential` turns **the entire pipeline** into a single thread across every stage. What matters is that the framework does not arbitrarily split the gatherer's state and attempt to call a nonexistent combiner.

### 16.2. If providing your own combiner, you must prove associativity

With `Gatherer.of(initializer, integrator, combiner, finisher)`, the framework may:

1. Split the source into partitions.
2. Create an independent state per partition.
3. Accumulate each partition.
4. Merge results via the appropriate combiner.
5. Run the finisher.

If the computation has a rule **"stop at the first marker in encounter order"**, simply adding counters across partitions is insufficient. The combiner must understand **marker position**, which prefix an input slice belongs to, and which data must be discarded; that is much harder than simple addition.

**Anti-pattern:**

```java
// Wrong idea:
// State has seen ArrayList<T> and stopped flag.
// combiner = (left, right) -> {
//     left.seen.addAll(right.seen);
//     return left;
// };
// Does not handle stopped flag, prefix order, or marker position.
```

The result may look right on small sources or when unsplit, then fail on a parallel stream. If you cannot prove associativity and correctness under encounter order, **never add a combiner just to "enable parallelism"**.

### 16.3. `mapConcurrent` differs from regular parallel streams

`Gatherers.mapConcurrent(maxConcurrency, mapper)` uses **virtual threads** to execute the mapper concurrently with a bound. The API preserves result ordering. For mappers doing blocking I/O or independent tasks that can run concurrently, it is worth evaluating.

```java
List<String> values = Stream.of("a", "bb", "ccc", "dddd")
    .gather(Gatherers.mapConcurrent(
        2,
        String::toUpperCase
    ))
    .toList();

System.out.println(values); // [A, BB, CCC, DDDD]
```

`maxConcurrency` must be greater than or equal to 1. Do **not** conclude that exactly `maxConcurrency` tasks run at every instant, or that this optimization is always faster than `map`; coordination overhead, source traits, downstream contention, and I/O latency all matter.

### 16.4. Task cancellation is best-effort

When downstream no longer wants more, `mapConcurrent` **attempts to cancel** in-flight tasks, yet cannot guarantee every already-started mapper stops immediately or avoids side effects. Therefore, never use it as a transactional rollback mechanism.

## 17. Infinite sources: completion-feasibility table

| Pipeline on an infinite source | Has a completion path? | Why |
| --- | --- | --- |
| `scan(...).limit(5).toList()` | Yes | `scan` emits step-by-step, `limit` caps output |
| `windowFixed(3).limit(2).toList()` | Yes | Emits one result per three inputs, then stops at two outputs |
| `windowSliding(3).limit(2).toList()` | Yes | Emits sliding windows once enough data arrives |
| `takeUntilInclusive(n >= 5).toList()` | Yes for source ascending from 1 | Integrator itself returns `false` at marker |
| `firstN(5).toList()` | Yes | Integrator self-stops after N outputs |
| `limit(5).fold(...).toList()` | Yes | Source is already finite **before** fold |
| `fold(...).limit(1).toList()` | No natural completion path | Fold waits for EOF to emit |
| `filter(n -> false).limit(1).toList()` | No natural completion path | No element passes the filter |
| `takeUntilInclusive(n < 0).toList()` with forever-positive inputs | No | Stopping predicate is never true |
| `windowFixed(1_000_000).findFirst()` | Yes if source keeps supplying enough inputs | Needs enough data for one window; may be very slow/memory-heavy |

### 17.1. Four liveness check questions

Before placing a gatherer after `Stream.iterate` or `Stream.generate`, ask yourself:

1. Does the gatherer **emit output before EOF**?
2. Does downstream have a **stopping condition** such as `limit` or `findFirst`?
3. Does the gatherer **stop the source itself** via `integrate == false`?
4. If no output arrives for a long time, what deadline, cancellation, or data bound does the program need?

If questions 1, 2, and 3 provide no completion mechanism, the pipeline will likely **run indefinitely**. Do not run an infinite pipeline without a cancellation mechanism in automated tests.

## 18. Resource lifecycles when a Gatherer sits mid-pipeline

A Gatherer does not mean an I/O source will be closed automatically when the terminal operation completes. For example, `Files.lines` opens a file-reading resource, so the caller must use `try-with-resources`.

### 18.1. Taking the first two windows from a large file

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

static List<List<String>> firstTwoBatches(Path path)
    throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .gather(Gatherers.windowFixed(3))
            .limit(2)
            .toList();
    }
}
```

Characteristics:

- `Files.lines` returns a **lazily reading** stream, avoiding loading the whole file with `readAllLines`.
- `windowFixed(3)` groups lines in file order.
- `limit(2)` needs at most two output windows, avoiding reading an entire huge file.
- `toList()` completing **does not automatically close** the `lines` stream.
- `try-with-resources` closes the source stream both on normal reads and when a stage throws an exception.

**Never assert that exactly six physical reads occur on every implementation:** buffering, read-ahead, and character decoding may cause the I/O layer to read ahead before the pipeline needs all lines.

### 18.2. `findFirst` is not `close`

```java
try (Stream<String> lines = Files.lines(path)) {
    var first = lines
        .gather(Gatherers.windowFixed(10))
        .findFirst();
    // first: Optional<List<String>>
}
```

`findFirst` can short-circuit after receiving the first window; however, **closing the file descriptor** happens on exiting `try`, not as a guaranteed side effect of `findFirst`.

### 18.3. When a Gatherer opens resources itself

If a custom Gatherer opens a file, sub-stream, or connection in `initializer`/`integrator`, you must specify:

- Who is the **owner**?
- Is there a closing mechanism on short-circuit or exception?
- Can multiple states be created in parallel?
- Is `finisher` actually invoked on every path where resources must be freed?

Do not put the entire resource-cleanup responsibility in `finisher` and implicitly treat it like a `finally` replacing `try-with-resources`. Resource-backed sources should be closed in an explicit owning scope outside the pipeline, or via a testable close handler/owner.

### 18.4. Short-circuiting does not mean canceling background work

When using `mapConcurrent` with I/O-waiting mappers, downstream may already have enough results and request stopping. The gatherer attempts to cancel running work on a **best-effort** basis, yet response time depends on the I/O API, interruptibility, and tasks already launched.

System design must not rely on "we called `limit(1)` so only one HTTP request was sent". If exactly-once guarantees are needed, that is a **protocol and idempotency** issue, not an automatic side effect of the gatherer.

## 19. JUnit 5 testing: ordering, infinite sources, and short-circuiting

The tests below use `GathererOrderAndStopDemo` from section 13 on **JDK 24+**. Run them with the project's JUnit Jupiter setup. The example uses `@Timeout` on pipelines starting from infinite sources; this is a **test guardrail**, not a production task-cancellation API.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class GathererOrderAndStopDemoTest {

    @Test
    void fixedWindowPreservesOrderAndLastPartialWindow() {
        List<List<Integer>> actual = Stream.of(
            7, 2, 9, 1, 4, 8, 5
        )
            .gather(Gatherers.windowFixed(3))
            .toList();

        assertEquals(
            List.of(
                List.of(7, 2, 9),
                List.of(1, 4, 8),
                List.of(5)
            ),
            actual
        );
    }

    @Test
    void slidingWindowsOverlapByAllButOneElement() {
        List<List<Integer>> actual = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowSliding(3))
            .toList();

        assertEquals(
            List.of(
                List.of(1, 2, 3),
                List.of(2, 3, 4),
                List.of(3, 4, 5)
            ),
            actual
        );
    }

    @Test
    void shortFiniteSourceProducesOnePartialSlidingWindow() {
        var actual = Stream.of(10, 20)
            .gather(Gatherers.windowSliding(5))
            .toList();
        assertEquals(List.of(List.of(10, 20)), actual);
    }

    @Test
    void emptySourceProducesNoWindow() {
        assertTrue(Stream.<Integer>empty()
            .gather(Gatherers.windowFixed(3))
            .toList().isEmpty());

        assertTrue(Stream.<Integer>empty()
            .gather(Gatherers.windowSliding(3))
            .toList().isEmpty());
    }

    @Test
    void fixedWindowsAreUnmodifiable() {
        var windows = Stream.of("a", "b", "c")
            .gather(Gatherers.windowFixed(2))
            .toList();

        assertThrows(UnsupportedOperationException.class, () ->
            windows.get(0).add("x")
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void infiniteSourceTerminatesWithOutputLimit() {
        assertEquals(
            List.of(List.of(1, 2, 3), List.of(4, 5, 6)),
            GathererOrderAndStopDemo.firstTwoFixedWindows()
        );

        assertEquals(
            List.of(List.of(1, 2, 3), List.of(2, 3, 4)),
            GathererOrderAndStopDemo.firstTwoSlidingWindows()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void scanProducesPrefixSumsWithoutWaitingForEof() {
        assertEquals(
            List.of(1L, 3L, 6L, 10L, 15L),
            GathererOrderAndStopDemo.firstFiveRunningTotals()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void foldCompletesWhenInputIsBoundedFirst() {
        assertEquals(
            List.of(15L),
            GathererOrderAndStopDemo.foldFirstFive()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void customGathererStopsAtMarkerInclusively() {
        assertEquals(
            List.of(1, 2, 3, 4, 5),
            GathererOrderAndStopDemo.untilFiveInclusive()
        );
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void customStatefulGathererStopsAfterN() {
        assertEquals(
            List.of(1, 2, 3),
            GathererOrderAndStopDemo.firstThree()
        );
    }

    @Test
    void downstreamCanStopBeforeGathererPredicate() {
        var result = Stream.iterate(1, n -> n + 1)
            .gather(GathererOrderAndStopDemo
                .takeUntilInclusive(n -> n >= 20))
            .limit(3)
            .toList();

        assertEquals(List.of(1, 2, 3), result);
    }

    @Test
    void missingMarkerInFiniteStreamEmitsEverything() {
        var result = Stream.of(1, 2, 3)
            .gather(GathererOrderAndStopDemo
                .takeUntilInclusive(n -> n > 10))
            .toList();

        assertEquals(List.of(1, 2, 3), result);
    }

    @Test
    void firstNRejectsNonPositiveSize() {
        assertThrows(IllegalArgumentException.class, () ->
            GathererOrderAndStopDemo.firstN(0)
        );
        assertThrows(IllegalArgumentException.class, () ->
            GathererOrderAndStopDemo.firstN(-1)
        );
    }

    @Test
    void windowsRejectNonPositiveSize() {
        assertThrows(IllegalArgumentException.class, () ->
            Gatherers.windowFixed(0)
        );
        assertThrows(IllegalArgumentException.class, () ->
            Gatherers.windowSliding(-1)
        );
    }

    @Test
    void concurrentMapPreservesEncounterOrderOfResult() {
        assertEquals(
            List.of(50, 10, 40, 20, 30),
            GathererOrderAndStopDemo.concurrentOrdered()
        );
    }

    @Test
    void customGathererDoesNotLeakStateBetweenRuns() {
        var gatherer = GathererOrderAndStopDemo
            .<Integer>firstN(2);

        assertEquals(
            List.of(1, 2),
            Stream.of(1, 2, 3).gather(gatherer).toList()
        );
        assertEquals(
            List.of(10, 20),
            Stream.of(10, 20, 30).gather(gatherer).toList()
        );
    }
}
```

**Important note on `@Timeout`:** timeouts in tests help detect hangs, yet a task stuck in I/O or a non-interruptible loop may require stronger isolation/cancellation mechanisms in the test environment. Do not run a `fold` pipeline on an infinite source to "prove it hangs"; explaining from API semantics and testing the version bounded **before fold** is enough.

### 19.1. Testing order vs. testing invocation counts

The tests above compare the result list against **expected data**. They do not require supplier/mapper to be called an exact number of times N; the API allows buffering, delayed cancellation, or speculative work, especially with `mapConcurrent`.

### 19.2. Testing state isolation across runs

The `customGathererDoesNotLeakStateBetweenRuns` test is especially important: it reuses **the same Gatherer instance** on two fresh streams. If the code kept an external counter instead of creating state via initializer, the second run might emit 0 elements or fewer than expected.

### 19.3. Tests must not depend on thread completion order

If you replace the `mapConcurrent` example with a mapper using random `Thread.sleep`, do **not** assert "start/end" log order. Verify the final list order on an ordered source; if real concurrency verification is needed, use a dedicated test/benchmark avoiding dependence on clocks and scheduling.

## 20. Property-based checks: replacing isolated examples with invariants

Beyond a few fixed examples, you can verify `windowFixed`/`windowSliding` across all small source lengths and multiple window sizes.

### 20.1. Invariants of `windowFixed`

For a source of `n >= 0` elements and window `size > 0`:

- Window count equals `n / size` plus 1 if `n % size != 0`.
- Every window except the last has length `size`.
- The last window has length in `[1, size]` if the source is non-empty.
- Flattening the windows in order must recover **the exact original list**, with no missing or duplicated elements.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

for (int n = 0; n <= 40; n++) {
    List<Integer> source = IntStream.range(0, n)
        .boxed().toList();

    for (int size = 1; size <= 8; size++) {
        List<List<Integer>> windows = source.stream()
            .gather(Gatherers.windowFixed(size))
            .toList();

        int expectedCount =
            n / size + (n % size == 0 ? 0 : 1);

        if (windows.size() != expectedCount) {
            throw new AssertionError("Incorrect window count");
        }

        List<Integer> flattened = windows.stream()
            .flatMap(List::stream)
            .toList();
        if (!source.equals(flattened)) {
            throw new AssertionError("Missing/duplicate element");
        }
    }
}
```

For `windowFixed`, the **flatten** check is particularly effective because windows do not overlap and preserve encounter order. It catches missing/duplicated element bugs that checking total window count alone might miss.

### 20.2. Invariants of `windowSliding`

For `n > 0`:

- If `n < size`: there is one window containing the entire source.
- If `n >= size`: there are `n - size + 1` windows.
- For every two consecutive full windows, **the trailing `size - 1` elements of the previous window equal the leading `size - 1` elements of the next window**.
- If `n == 0`: there are no windows.

Example check on a sequence:

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

for (int i = 1; i < windows.size(); i++) {
    List<Integer> prev = windows.get(i - 1);
    List<Integer> curr = windows.get(i);

    if (!prev.subList(1, 3).equals(curr.subList(0, 2))) {
        throw new AssertionError("Incorrect sliding window");
    }
}
```

### 20.3. Invariants of custom `takeUntilInclusive`

On a finite ordered source:

1. If a marker exists, the result is **the prefix ending at the first marker**.
2. If no marker exists, the result equals the entire source.
3. No element after the marker appears in the result.
4. Elements before and at the marker preserve their order and occurrence counts.

For sources allowing duplicate values, do **not** compare only as a `Set`; `Set` discards frequency information. Use `List.equals` to verify prefixes in the ordered case.

## 21. Common anti-patterns

| Mistake | Why is it wrong? | Fix |
| --- | --- | --- |
| Using `fold(...).limit(1)` on an infinite source | Fold waits for source completion to emit a result | Cap input **before fold**, or use `scan` |
| Thinking `limit(2)` after `windowFixed(3)` means reading two inputs | Limit counts **output** windows | Determine how many inputs are needed per output |
| Attaching `unordered()` to a source needing event order | Encounter order is no longer guaranteed | Keep ordered source or define another order |
| Thinking `parallel()` runs `ofSequential` state in parallel | A Gatherer using the default combiner must evaluate sequentially | Only write a combiner when correctness is proven |
| Returning `false` from `Integrator.ofGreedy` to self-stop | Greedy promises never to initiate short-circuiting itself | Use a regular integrator |
| Ignoring `downstream.push(...) == false` | Downstream already rejected further output | Propagate the stop signal appropriately |
| Trusting `isRejecting() == false` means `push` will surely succeed | It is a best-effort check | Always check the return value of `push` |
| Using a mutable counter outside initializer | Multiple runs can share state | Create fresh state inside `initializer` |
| Calling `push` with an `ArrayList` then `clear` | Emitted results get mutated via the shared reference | Create a `List.copyOf` snapshot |
| Retaining `Downstream` for async callbacks | Violates reference lifetime | Emit synchronously inside integrator/finisher |
| Using `mapConcurrent` for non-idempotent side effects | Tasks may start before downstream stops | Isolate transactions/design idempotency |
| Requiring mapper to run exactly N times with `limit` | Buffering, speculative work, optimizations | Test results and resource boundaries |
| Forgetting `Files.lines` closing after `findFirst` | Terminal operations do not auto-close resources | Use `try-with-resources` |
| Using huge windows without memory planning | Gatherer must buffer data | Bound size, measure peak memory |
| Running a test asserting "infinite pipeline must hang" | Can hang the test suite | Prove by reasoning and test bounded variants |
| Compiling `Stream.gather` with `--release 17` | API does not exist | Use JDK 24+ or a fallback solution |

## 22. Guided practice exercises

### Exercise 1 — Fixed windows on a finite log

Given `List<String> events = List.of("A", "B", "C", "D", "E", "F", "G")`. Use `windowFixed(3)` and verify:

- There are three windows.
- The last window contains only `G`.
- Flattening windows via `flatMap(List::stream)` recovers the exact source.
- Calling `add` on a result window fails.

### Exercise 2 — Sliding windows and ordering

Use `Stream.of(5, 1, 9, 3, 2)` and `windowSliding(3)`. Write out the exact three windows, verify that the last two elements of the previous window match the first two elements of the next window. Then try `unordered()` and explain why you cannot assert **window order** matches the original source once the encounter-order constraint is dropped.

### Exercise 3 — Running totals from an infinite source

Compute the first 10 triangular numbers using `scan(() -> 0L, Math::addExact)` and `limit(10)`. Verify the 10th element equals `55` and explain why `fold(...).limit(10)` cannot replace `scan` on an infinite source.

### Exercise 4 — Stopping at a marker, inclusive

With source `[10,20,30,-1,40,50]`, use `takeUntilInclusive(n -> n == -1)`. Compare against `takeWhile(n -> n != -1)`. Write tests covering marker present, marker absent, marker at first element, and empty source.

### Exercise 5 — Limiting input or output?

On `Stream.iterate(1, n -> n + 1)`:

1. `limit(5).gather(windowFixed(3)).toList()`.
2. `gather(windowFixed(3)).limit(5).toList()`.

Predict both results and explain why they are not equivalent in the number of source elements consumed. Do not put exact supplier call counts in test assertions.

### Exercise 6 — Shared-state bug

Write a "take 3 elements" gatherer where the counter is captured from outside. Reuse the same gatherer instance on two finite streams and observe the failure. Fix it using `Gatherer.ofSequential(Counter::new, integrator)`, and write a test proving runs are independent.

### Exercise 7 — Is `Integrator.Greedy` appropriate?

Can an integrator that emits double each number and **does not self-stop** the source use `ofGreedy`? What about an integrator that **stops when encountering 0**? Explain why the JDK is allowed to ignore the greedy return value in optimizations.

### Exercise 8 — I/O sources and short-circuiting

Read a large text file with `Files.lines`. Find the first two three-line windows, close the file properly, and explain how to verify the resource is closed in both success and failure cases. Do not treat `limit(2)` as a guarantee that the I/O layer reads only 6 physical lines.

### Exercise 9 — `mapConcurrent` and slow mappers

Given 30 request IDs calling a simulated time-consuming service. Use `mapConcurrent(4, mapper)` to compute values, verifying results **in encounter order**. Add a trailing `limit(3)` and analyze why some already-started tasks may still be running and why idempotency is needed if the mapper has side effects.

### Exercise 10 — Writing a batch gatherer with a finisher

Implement `batches(4)` following section 14. On a 10-element source, verify batch sizes are `4,4,2`. Use an infinite source and `limit(2)` to obtain two full 4-element batches. Prove already-emitted lists are unaffected when internal state is cleared for the next batch.

### Exercise 11 — Needing a real combiner

Propose a design for a gatherer capable of merging partitions for an **associative, order-independent** aggregation, and compare it with `takeUntilInclusive` which depends on **the first marker**. Only write a combiner if correctness can be proved across all valid splits and merge orders. If only a sum is needed, why is `mapToLong(...).sum()` or `Collectors.summingLong` usually simpler?

### Exercise 12 — Bounded liveness

Design an application reading potentially infinite events, finding an event matching a condition, and stopping. Require an explicit **event-count cap** or deadline, distinguishing:

- No matching event within the inspected window.
- Genuine end of source.
- Source canceled or unreadable.

Do not conflate all three scenarios into "empty result" and do not use an uncancelable infinite pipeline in tests.

## 23. Decision table and summary

| Problem | Approach | What to verify |
| --- | --- | --- |
| Group consecutive elements into fixed batches | `Gatherers.windowFixed(size)` | Ordering, short final batch, buffer size |
| Overlapping windows | `Gatherers.windowSliding(size)` | Overlap region, short source, window count |
| Running total/state after each input | `Gatherers.scan(initial, scanner)` | One output per input; overflow handling |
| Only one final sum on a finite source | `Gatherers.fold(initial, folder)` | Requires EOF to emit result |
| Infinite source + sum of first N inputs | `limit(N)` **before `fold`** | Caps input, not output |
| Infinite source + first N results from windows/scan | `gather(...).limit(N)` | Gatherer emits incrementally; reasonable buffer |
| Keep the stopping marker too | Custom `ofSequential` integrator returning `false` | Emit marker before stopping, clear order |
| Simply take at most N elements | `Stream.limit(N)` | Prefer built-in API, avoid needless gatherer |
| Downstream already has enough results | `push(...) == false` | Stop emitting, propagate signal properly |
| Downstream may already be rejecting | `isRejecting()` | Best effort, does not replace checking `push` |
| Integrator actively short-circuits | Regular integrator, **not** `ofGreedy` | Preserves stop signal |
| Stateful, order-dependent Gatherer | `Gatherer.ofSequential` | Fresh state per run, no fake combiner |
| Independent mappers runnable concurrently | `Gatherers.mapConcurrent(k, mapper)` | Output order and best-effort cancellation |
| Need sorting from an unordered source | `sorted` or explicit business order | Never rely on worker timing |
| Source is a file/I/O resource | `try-with-resources` around owner | Short-circuiting does not auto-close |
| Testing infinite sources | Pipeline with stop path and `@Timeout` | Never let tests hang |
| Running on JDK 17/21 | Use legacy Stream operations | No standard `Gatherer` API |
| Running on JDK 24+ | Official `Stream.gather` API | No `--enable-preview` needed |

### Conclusion

**Handling ordering, infinite sources, and short-circuiting with Gatherers** requires three distinct lines of reasoning. **Ordering** comes from source encounter order and transformation contracts, not thread completion order. **Infinite sources** can only produce finite results when there is an incremental emission mechanism and a genuine stopping condition; `scan` and windows can emit incrementally, whereas `fold` must wait for input completion. **Short-circuiting** can be initiated by the integrator or downstream, yet still requires managing resources through an explicit owner.

When writing custom gatherers, use initialized state **private to each evaluation**, respect `Downstream.push`, and never use `Integrator.ofGreedy` if the gatherer itself needs to actively short-circuit. Only add a combiner when correctness is proven across parallel partitions. Start with built-in APIs, test contents and liveness on controlled finite/infinite sources, and only then measure performance and consider Gatherers for production pipelines.
