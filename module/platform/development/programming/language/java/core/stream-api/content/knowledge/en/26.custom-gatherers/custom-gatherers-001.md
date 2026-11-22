# Contracts of initializer, integrator, combiner, and finisher

**Stream Gatherer** is an extension mechanism for the Java Stream API pipeline that creates an intermediate operation capable of maintaining state, transforming one element into multiple results, grouping multiple elements into one result, or stopping processing before the source ends. The key difference compared to `map` or `filter` is that Gatherer allows programmers to describe a custom transformation through **four functions with tightly coordinated contracts**: `initializer`, `integrator`, `combiner`, and `finisher`.

This lesson belongs to the **Building Custom Gatherers** chapter of the `JAVA_STREAM_API` module. We will understand the role of each function, the state lifecycle, how to emit elements via `Downstream`, how to handle early termination, the conditions for parallel splitting, cases where you should not write a `combiner`, as well as how to test a Gatherer with empty data, boundary states, and I/O sources. This topic builds upon knowledge of lazy pipelines, `filter`, `map`, `reduce`, `collect`, `Spliterator`, and Stream Gatherers.

> **JDK Version:** `java.util.stream.Gatherer`, `java.util.stream.Gatherers`, and `Stream.gather(...)` are official APIs starting from **Java 24** (JEP 485). They previously appeared as preview features in Java 22 and 23. Code in this lesson uses **Java 24 and later** APIs and does not run as-is on Java 8–21. Gatherers no longer require `--enable-preview` when using Java 24.

## 1. A Gatherer Is Not a Collector

A `Collector` is an argument to the terminal operation `collect(...)` and produces a single final aggregated result. A `Gatherer` is passed to `Stream.gather(...)`, which is an **intermediate operation**: its output continues flowing through `filter`, `map`, `limit`, `collect`, `toList`, or other operations.

```text
Source Stream<T>
      |
   filter / map
      |
   gather(Gatherer<T, A, R>)
      |       |
      |       +-- initializer: creates A
      |       +-- integrator : receives T, updates A, may push R
      |       +-- combiner   : merges two As when parallelism is allowed
      |       +-- finisher   : processes final A, may push R
      |
    Stream<R>
      |
   filter / map / limit / ...
      |
    toList / collect / reduce      <-- terminal
      |
     Result
```

Example of creating fixed windows using a built-in Gatherer:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> totals = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(Gatherers.<Integer>windowFixed(3))
        .map(window -> window.stream()
                .mapToInt(Integer::intValue)
                .sum())
        .toList();

System.out.println(totals); // [6, 15, 7]
```

`windowFixed(3)` transforms elements into lists of at most three elements; the downstream `map` converts each list into its sum. A Gatherer is **not required** to wait for the entire source to emit results: it can emit a window as soon as that window is complete.

The four components of a Gatherer allow us to build a custom transformation following that exact principle.

## 2. The Three Types T, A, R and the Four Contracts

General interface:

```java
public interface Gatherer<T, A, R> {
    // Methods are explained in the following sections.
}
```

Three type parameters:

| Type | Meaning | Example when creating windows |
| --- | --- | --- |
| `T` | Input element | `Integer` |
| `A` | Private intermediate state of the Gatherer | Buffer holding numbers not yet forming a full window |
| `R` | Element emitted downstream after `gather` | `List<Integer>` |

Contracts of the four functions:

| Function | Core Functional Type | Responsibility |
| --- | --- | --- |
| `initializer()` | `Supplier<A>` | Provides the initial state for a run/processing branch |
| `integrator()` | `Gatherer.Integrator<A,T,R>` | Receives a new element, may mutate state, and emits results |
| `combiner()` | `BinaryOperator<A>` | Merges two accumulated states when the Gatherer allows parallel execution |
| `finisher()` | `BiConsumer<A, Downstream<? super R>>` | Performs the final step after accumulation, typically emitting remaining data |

The sequential processing framework can be conceptualized as:

```text
A state = initializer.get()

for each element T from upstream:
    keepGoing = integrator.integrate(state, T, downstream)
    if keepGoing == false:
        stop receiving further elements

finisher.accept(state, downstream)
```

This is a **conceptual model**, not a program where you manually invoke all four functions. Java has the right to optimize: it may skip calling the default initializer of a stateless Gatherer, skip calling the default finisher, and split the source then merge states if the combiner allows it.

Do not confuse `A` objects with `R` results: internal state does not have to be exposed, and a Gatherer can emit **0, 1, or more** `R`s for each `T`.

## 3. initializer: Starting from a Valid State

`initializer()` returns a `Supplier<A>`. This Supplier creates the state for one accumulation pass; in parallel processing, it may be called multiple times to provide states for different partitions.

Example window state:

```java
import java.util.ArrayList;
import java.util.List;

static final class WindowState<T> {
    final List<T> pending = new ArrayList<>();
    boolean stopped;
}
```

Supplier:

```java
WindowState<Integer> initialState = new WindowState<>();
```

In a Gatherer, you should pass `WindowState::new` rather than a pre-created object. The critical condition is that **every time the Supplier is called, it must return an independent state**, not the same shared `ArrayList` or Map.

Wrong:

```java
WindowState<Integer> shared = new WindowState<>();

// WRONG: Supplier always returns the same mutable instance.
java.util.function.Supplier<WindowState<Integer>> unsafe =
        () -> shared;
```

Right:

```java
java.util.function.Supplier<WindowState<Integer>> safe =
        WindowState::new;
```

A good initial state needs to define an **identity** for merging: 0 for a sum, empty for a list, 0 for a counter. If you need to distinguish between "no element received yet" and "first key value is null", use a separate `initialized`/`active` flag instead of using `null` as a sentinel for not started.

**Do not store the state of a run in a static variable or a shared object across Stream executions.** A Gatherer is designed as a reusable descriptor; each execution needs its own state according to its contract.

## 4. integrator: Receiving One Element, Possibly Emitting Multiple Results

`integrator()` returns a `Gatherer.Integrator<A,T,R>`. Its central method has the form:

```java
boolean integrate(
        A state,
        T element,
        Gatherer.Downstream<? super R> downstream
);
```

One integration step can:

1. Read/update state `A` based on element `T`.
2. Emit nothing (for example, waiting until three elements fill a window).
3. Emit one or more `R`s via `downstream.push(...)`.
4. Return `true` to continue receiving elements, or `false` to **stop receiving further elements from upstream**.

Example that only transforms each number into a string label (demonstrating a stateless Gatherer):

```java
import java.util.function.Function;
import java.util.Objects;
import java.util.stream.Gatherer;

static <T, R> Gatherer<T, ?, R> project(
        Function<? super T, ? extends R> mapper) {

    Objects.requireNonNull(mapper, "mapper");

    return Gatherer.of(
            (unusedState, element, downstream) ->
                    downstream.push(mapper.apply(element))
    );
}
```

Usage:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> labels = Stream.of(1, 2, 3)
        .gather(project(n -> "n=" + n))
        .toList();

System.out.println(labels); // [n=1, n=2, n=3]
```

This code is conceptually equivalent to `map`; in real applications, prefer `map` because it is shorter. The learning point is that **not every Gatherer needs state**.

For stateless Gatherers created with `Gatherer.of(integrator)`, the JDK uses appropriate default initializer and combiner. Do not create a useless state object if nothing needs to be remembered between elements.

## 5. Downstream.push and the Early Termination Signal

`Gatherer.Downstream<R>` represents the next step in the pipeline. Two methods to know:

- `boolean push(R value)`: emits a result to the next step. Returns `true` if downstream can still accept more, `false` otherwise.
- `boolean isRejecting()`: a best-effort check of whether downstream has already rejected further elements. `false` **does not guarantee** that the next `push` will succeed; this is a *best effort* signal.

Example where `limit(2)` as a step after the Gatherer stops after two results:

```java
List<String> firstTwo = Stream.of(10, 20, 30, 40)
        .gather(project(n -> "value:" + n))
        .limit(2)
        .toList();

System.out.println(firstTwo); // [value:10, value:20]
```

The integrator function in `project` returns **the exact return value of `push`**; when downstream wants no more results, the Gatherer can stop receiving source elements. Once `push` has returned `false`, subsequent `push` calls on the same downstream will continue to be rejected per contract.

### Stopping from Inside the Gatherer

A Gatherer can also decide on its own to emit at most `n` elements:

```java
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, T> firstAtMost(int maxElements) {
    if (maxElements < 0) {
        throw new IllegalArgumentException(
                "maxElements must not be negative"
        );
    }

    class State {
        int emitted;
    }

    return Gatherer.<T, State, T>ofSequential(
            State::new,
            (state, element, downstream) -> {
                if (state.emitted >= maxElements) {
                    return false;
                }

                state.emitted++;
                boolean wantsMore = downstream.push(element);

                return wantsMore && state.emitted < maxElements;
            }
    );
}
```

Example:

```java
System.out.println(
        Stream.of("A", "B", "C", "D")
                .gather(firstAtMost(2))
                .toList()
); // [A, B]
```

Returning `false` means **stop integrating input**, not "the current element has an error". When `maxElements == 0`, the Gatherer emits no elements; if you only need a standard limit, `Stream.limit(maxElements)` is built-in and should be preferred.

**Important:** early termination of a Stream does not automatically close `Files.lines`, sockets, or Readers. Ownership of upstream resources must still be handled separately with `try-with-resources` or an equivalent resource-closing contract.

## 6. finisher: Processing Remaining State After the Last Element

`finisher()` has the signature:

```java
BiConsumer<A, Gatherer.Downstream<? super R>> finisher()
```

A Gatherer's `finisher` **differs** from a Collector's finisher:

- A Collector finisher transforms `A` into a single **final result `R`**.
- A Gatherer finisher can **emit additional elements** via `downstream.push(...)`, such as the final group or an incomplete window.

For example, grouping elements into batches of three: when reading `1,2,3,4,5`, the integrator emits `[1,2,3]`; at the end of the source, the finisher emits `[4,5]`.

Without a finisher, the batch `[4,5]` would be lost because there is no sixth element to trigger emitting it.

**Two safety rules:**

1. Once you have pushed a `List` downstream, do not subsequently `clear()` or mutate that List. Emit an **independent snapshot**.
2. If downstream has already stopped, the finisher must not emit unsolicited extra results. Check your internal stop flag and/or `downstream.isRejecting()`, keeping in mind that `isRejecting` is a best-effort check.

## 7. Complete Exercise: Sequential Batching Gatherer

We build `fixedBatches(size)` to demonstrate **initializer + integrator + finisher**. It depends on encounter order, so we use `Gatherer.ofSequential(...)` and **do not write a fake combiner**.

### 7.1. Complete Gatherer Code

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;

public final class BatchGatherers {
    private BatchGatherers() {}

    private static final class BatchState<T> {
        final List<T> pending = new ArrayList<>();
        boolean stopped;
    }

    public static <T> Gatherer<T, ?, List<T>> fixedBatches(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException(
                    "size must be positive"
            );
        }

        return Gatherer.<T, BatchState<T>, List<T>>ofSequential(
                BatchState::new,            // initializer

                (state, element, downstream) -> { // integrator
                    state.pending.add(element);

                    if (state.pending.size() < size) {
                        return true;
                    }

                    // Emit a copy, do not emit the still-mutating buffer.
                    List<T> complete =
                            new ArrayList<>(state.pending);
                    state.pending.clear();

                    boolean accepted = downstream.push(complete);
                    if (!accepted) {
                        state.stopped = true;
                    }
                    return accepted;
                },

                (state, downstream) -> {     // finisher
                    if (!state.stopped
                            && !state.pending.isEmpty()
                            && !downstream.isRejecting()) {
                        downstream.push(
                                new ArrayList<>(state.pending));
                    }
                }
        );
    }
}
```

### 7.2. Using It in a Pipeline

```java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> batches = Stream.of(
        1, 2, 3, 4, 5, 6, 7, 8
).gather(BatchGatherers.fixedBatches(3))
 .toList();

System.out.println(batches);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Timeline of `pending`:

```text
Receive 1: pending = [1]         => not emitted yet
Receive 2: pending = [1,2]       => not emitted yet
Receive 3: pending = [1,2,3]     => push [1,2,3], clear
Receive 4: pending = [4]         => not emitted yet
Receive 5: pending = [4,5]       => not emitted yet
Receive 6: pending = [4,5,6]     => push [4,5,6], clear
Receive 7: pending = [7]         => not emitted yet
Receive 8: pending = [7,8]       => not emitted yet
End:       finisher              => push [7,8]
```

With an empty source, `pending` is empty and the finisher emits nothing. With a source having exactly full-sized batches, the finisher does not emit an empty batch.

### 7.3. Early Termination and Snapshot Handling

```java
List<List<Integer>> onlyOne = Stream.of(
        1, 2, 3, 4, 5, 6, 7
).gather(BatchGatherers.fixedBatches(3))
 .limit(1)
 .toList();

System.out.println(onlyOne); // [[1, 2, 3]]
```

Once `limit(1)` has received the first batch, `push` may return `false`. `stopped` prevents the finisher from emitting the remainder.

If you replace `new ArrayList<>(state.pending)` with `state.pending` and then call `clear()`, previously emitted batches could turn into empty lists or change as subsequent elements arrive. **Never let mutable internal state escape downstream and then continue mutating it**.

For large batches, the buffer holds at most `size` elements; copying on emission incurs memory and allocation overhead. If you only need the count or sum of each batch, store summary statistics instead of all elements.

### 7.4. When Should You Not Write It Yourself?

Java 24 includes `Gatherers.windowFixed(size)`, which solves the exact problem of splitting into fixed batches. `fixedBatches` is an example for **learning the contracts**, not a recommendation to rewrite standard APIs in every project.

## 8. combiner: Merging Two States, Not Arbitrary Emission

`combiner()` returns a `BinaryOperator<A>`:

```java
A combine(A left, A right);
```

When a Gatherer is allowed to run in parallel, the framework may:

1. Split the source into partitions.
2. Provide a separate state for each partition using the initializer.
3. Call the integrator on elements of that partition.
4. Wait for accumulation of the partitions to finish, then call the combiner to merge the states.
5. Call the finisher on the final merged state.

Diagram:

```text
              Stream<T> (parallel)
                 /         \
               T...        T...
                |            |
          initializer    initializer
                |            |
           state A1       state A2
                |            |
          integrator     integrator
                |            |
                +-- combiner-+
                      |
                 merged A
                      |
                   finisher
                      |
                Stream<R>
```

**Core contract of the combiner:**

- Do not lose or double-count elements.
- Merge states according to the semantics of the transformation.
- Have an **identity element** consistent with the initializer.
- Remain correct under **different groupings**: merging `(A+B)+C` must produce an equivalent result to `A+(B+C)` when the Gatherer supports parallel execution.
- Do not assume a fixed number of calls, partition sizes, or thread count.
- Do not continue mutating states already handed over to the combiner/finisher in ways that violate lifecycle contracts.
- Do not arbitrarily emit results downstream from the combiner, because the combiner only receives **two states** and has no `Downstream`.

**The combiner function does not have to allocate a new state:** it may merge `right` into `left` and return `left`, as long as partition independence and state usage rules are preserved. Do not concurrently access the same state from outside the Gatherer.

## 9. Four-Function Exercise: Summing Integers to Emit a Single Total

We create a Gatherer that receives `Integer` elements and emits **a single `Long` total** at the end. This problem can be solved more easily with `mapToLong(...).sum()`, but it shows how a Gatherer **with a proper combiner** works.

### 9.1. Gatherer.of Implementation

```java
import java.util.stream.Gatherer;

public final class SumGatherers {
    private SumGatherers() {}

    private static final class SumState {
        long total;
    }

    public static Gatherer<Integer, ?, Long> oneTotal() {
        return Gatherer.<Integer, SumState, Long>of(
                SumState::new, // initializer: initial total 0

                Gatherer.Integrator.ofGreedy(
                        (state, value, downstream) -> {
                            state.total += value.longValue();
                            return true;
                        }
                ),

                (left, right) -> { // combiner: merge two totals
                    left.total += right.total;
                    return left;
                },

                (state, downstream) -> { // finisher
                    if (!downstream.isRejecting()) {
                        downstream.push(state.total);
                    }
                }
        );
    }
}
```

Analysis of the four contracts:

- **Initializer:** `new SumState()` has `total == 0`, which is the identity of addition.
- **Integrator:** each `Integer` is added to the total. It emits no output before completion.
- **Combiner:** two partial totals are added into a new total without dropping data from the right branch.
- **Finisher:** at completion, emits the final total as a single `Long` element.

`Integrator.ofGreedy(...)` is used because this integrator **always returns `true`** and never initiates early termination itself. It also **does not call `push` during the accumulation phase**, so it does not ignore any signal from downstream.

### 9.2. Identical Semantics Across Multiple Partitions

```java
import java.util.List;
import java.util.stream.IntStream;

List<Long> sequential = IntStream.rangeClosed(1, 100)
        .boxed()
        .gather(SumGatherers.oneTotal())
        .toList();

List<Long> parallel = IntStream.rangeClosed(1, 100)
        .boxed()
        .parallel()
        .gather(SumGatherers.oneTotal())
        .toList();

System.out.println(sequential); // [5050]
System.out.println(parallel);   // [5050]
```

Groups may be split into sums `1+...+50` and `51+...+100`, and then the combiner adds the two totals. Integer addition within this example's range preserves semantics across different groupings.

**Do not use this example to claim a custom Gatherer is faster than `sum()`.** It boxes `int` into `Integer`, allocates state, and uses downstream to emit the result; specialized `IntStream.sum()` is usually cleaner and better optimized.

Over large ranges, `long` addition can also overflow; choose arithmetic suitable for the requirement. And because Gatherer is an intermediate operation, the final result still requires a terminal `toList()` (or another terminal method).

### 9.3. Why Not Just Return left and Discard right?

Wrong:

```java
// WRONG if data has already been accumulated in both branches.
(left, right) -> left
```

With a parallel Stream, this drops the total of a partition. A sequential run may still "look right" if the combiner is never invoked; therefore, **sequential testing is insufficient** for a Gatherer declared as parallel-capable.

## 10. Not Every Stateful Gatherer Can Be Split

Try turning `fixedBatches(3)` from section 7 into a parallel Gatherer by merging two `pending` lists:

```text
Input sequence: 1 2 3 4 5 6 7

Left branch:  [1 2 3 4]      emits [1 2 3], keeps [4]
Right branch: [5 6 7]        emits [5 6 7]

Correct result across the whole sequence:
  [1 2 3] [4 5 6] [7]

Wrong result if merely concatenating outputs of two branches:
  [1 2 3] [5 6 7] [4]      (wrong order/boundaries)
```

Groups or windows can **span across partition boundaries**. You cannot simply write `left.pending.addAll(right.pending)` if elements on both sides have already been emitted as results earlier.

Problems whose states are typically hard to merge:

- Grouping **consecutive** elements with the same key;
- Sliding windows that overlap across two partitions;
- Emitting state changes relative to the previous element;
- Stopping after observing a specific number of results;
- Accumulation strongly dependent on encounter order.

For these problems, start with `Gatherer.ofSequential(...)`. Only write a combiner when you can clearly prove how to preserve **prefixes, suffixes, and boundaries**, as well as how to handle early termination across partitions.

**The Stream's `parallel()` flag does not automatically fix a broken combiner.** It only allows the framework to choose a parallel strategy when the Gatherer provides a suitable combiner.

## 11. ofSequential, of, and Default Functions

Java 24 provides important factories:

| How to create a Gatherer | Characteristics | Use case |
| --- | --- | --- |
| `Gatherer.ofSequential(initializer, integrator, finisher)` | Stateful, no parallel combiner provided | Batches/windows/adjacent groups |
| `Gatherer.ofSequential(initializer, integrator)` | Stateful, no special finisher needed | All outputs emitted while integrator runs |
| `Gatherer.ofSequential(integrator)` | Stateless, sequential | Custom logic needing no state |
| `Gatherer.of(initializer, integrator, combiner, finisher)` | Stateful, allows parallel via combiner | Mergeable aggregations |
| `Gatherer.of(integrator)` | Stateless, parallel-capable | Independent per-element transformation |

Three default functions to distinguish:

- `Gatherer.defaultInitializer()`: marks the Gatherer as **stateless**; the framework may skip calling the initializer.
- `Gatherer.defaultCombiner()`: marks the Gatherer as **sequential-only**. It is not a general-purpose state-merging combiner.
- `Gatherer.defaultFinisher()`: marks **no end-of-stream work**; the framework may skip calling the finisher.

Do not replace `defaultCombiner()` with a seemingly harmless lambda just to "enable parallelism". If the lambda does not describe a valid merge operation, the algorithm will still be wrong when split across branches. `ofSequential` is the explicit way to signal that no valid state-merging operation exists.

### How Integrator.Greedy Differs from a Regular Integrator

`Gatherer.Integrator.ofGreedy(...)` creates an integrator declaring that it **never initiates short-circuiting itself**. Under the Java 24 contract, a Greedy integrator must be prepared to consume the entire input; it **may propagate** downstream's refusal to accept more elements. The framework is permitted to skip inspecting the return value of a Greedy integrator, since rejection state is already represented on downstream.

Therefore:

```java
// VALID: the integrator itself never requests to stop.
class CounterState {
    long total;
}

Gatherer.Integrator<CounterState, Integer, Long> greedy =
        Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    state.total += element.longValue();
                    return true;
                }
        );
```

A Greedy integrator may also forward the result of `push` without imposing its own limit:

```java
// VALID: false only reflects that downstream rejected further output.
Gatherer.Integrator<Void, Integer, Integer> forwardingGreedy =
        Gatherer.Integrator.ofGreedy(
                (unused, element, downstream) ->
                        downstream.push(element)
        );
```

Conversely, the snippet below **violates the Greedy contract**, because it decides on its own to stop after seeing a certain number of elements, even when downstream is still ready:

```java
class CutoffState {
    int seen;
}

// WRONG: self-short-circuits on the 5th element instead of only forwarding downstream.
Gatherer.Integrator<CutoffState, Integer, Integer> wrongGreedy =
        Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    state.seen++;
                    if (state.seen == 5) {
                        return false;
                    }
                    return downstream.push(element);
                }
        );
```

If you want to stop on a threshold yourself, use a regular `Gatherer.Integrator` or an integrator lambda directly in `ofSequential`; **do not** mark that algorithm as `ofGreedy`.

## 12. State Lifecycle and the Rule Against Retaining References

This is an easily overlooked part of the Gatherer contract. According to the API, an implementation **must not retain or pass to another thread references to state or Downstream beyond the scope of the invocation in which those objects were passed**.

Do:

- Keep state properly within Gatherer functions; Supplier creates a new state whenever requested by the framework.
- Emit **independent result values** via `push`.
- Once a state has been handed to the combiner or finisher, do not continue manipulating it in the integrator.
- Do not store `downstream` in a static field, background task, or deferred callback to call `push` at an arbitrary time.
- Do not use a gather operation's state as a global container that can be concurrently mutated from outside.

Do not:

```java
// CONCEPTUALLY WRONG: retaining downstream for use after the callback finishes.
// static Gatherer.Downstream<String> savedDownstream;
//
// (state, element, downstream) -> {
//     savedDownstream = downstream;
//     return true;
// };
```

Doing so can violate lifecycle and thread-safety guarantees. If asynchronous processing is needed, design the pipeline around an explicitly supported mechanism rather than using `Downstream` as an arbitrary callback channel.

### Is Mutable Output Allowed?

An `R` may be a `List<T>`, but **you should not emit the mutating state list itself as a result if you will keep modifying it**. Emitting a snapshot ensures downstream results are not altered by subsequent integrator calls.

If copying lists is expensive, revisit the requirements: perhaps you can emit a `count`, `sum`, or a small immutable DTO instead of keeping the whole group.

## 13. Early Termination Behavior with a Combiner

Early termination is a subtle interaction between the integrator, downstream, and parallel partitions.

When `integrate` returns `false`, the framework interprets it as **no more elements need to be fed into that integrator**. Under parallel evaluation, states from partitions **after** a partition that short-circuited may not be allowed to contribute to the emitted results.

Therefore, the following cases need careful verification:

1. **Integrator stops by input element count**: with an ordered source and branching, how are the "first n elements" determined?
2. **Downstream uses `limit`**: `push` may return `false` right during integration.
3. **Finisher has remaining data**: is it certain downstream still accepts more?
4. **Does the combiner preserve the required order?** If not, taking the "first" or "last" will be wrong.

For example, `fixedBatches` has a `stopped` flag and uses `isRejecting` to avoid emitting the final batch when downstream has already rejected. That is one way to coordinate state with the request to stop receiving further data.

Do not assume that `finisher` is always used to "rescue" every element remaining in state after downstream has stopped. When downstream rejects, emitting more only causes output to be dropped or violates the semantics the application expects.

## 14. Composition: Chaining Multiple Gatherers and Stream Operations

A Gatherer can be chained with another Gatherer using `andThen(...)`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> values = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(
                Gatherers.<Integer>windowFixed(3)
                        .andThen(
                                Gatherer.<List<Integer>, Integer>of(
                                        (unused, window, downstream) ->
                                                downstream.push(
                                                        window.stream()
                                                                .mapToInt(
                                                                        Integer::intValue)
                                                                .sum()
                                                )
                                )
                        )
        )
        .toList();

System.out.println(values); // [6, 15]
```

Here we place the windowing Gatherer before a Gatherer that sums each window. Equivalent result:

```java
List<Integer> direct = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(Gatherers.<Integer>windowFixed(3))
        .map(window -> window.stream()
                .mapToInt(Integer::intValue)
                .sum())
        .toList();
```

The `andThen` pattern is useful when you want to **encapsulate** multiple transformation steps into a single reusable Gatherer. However, when you only need standard `map` or `filter`, there is no need to turn every step into a custom Gatherer.

**Watch the data types:** `andThen` composes on the output element type `R` of the preceding Gatherer and the input type `T` of the following Gatherer; it does not merge the two states `A`. Checking input/output types helps catch mismatched compositions at compile time.

## 15. Performance, Memory, and When to Fall Back to Standard APIs

Writing a Gatherer does not automatically guarantee higher performance than standard Stream operations.

| Approach | Advantages | Limitations |
| --- | --- | --- |
| `map`, `filter`, `flatMap` | Clear intent, idiomatic, easy to optimize | Cannot directly express every stateful transformation |
| `collect`/`reduce` | Produces final aggregated result | Does not itself create an intermediate operation emitting multiple outputs |
| `Gatherers.windowFixed` | Built-in fixed windows | Cannot customize all boundary logic |
| `Gatherers.windowSliding` | Built-in sliding windows | Follows JDK-defined windowing policy |
| `Gatherers.scan` | Built-in prefix accumulation | Does not replace every stateful algorithm |
| `Gatherer.ofSequential` | Easy to preserve encounter order for adjacent algorithms | May limit parallelism at the gather stage |
| `Gatherer.of` with combiner | Can leverage partitions | Must prove the merge operation is safe and efficient |

Memory considerations:

- The state of `fixedBatches(k)` holds at most about `k` elements; the `toList()` output holds all emitted batches as well.
- The state of `oneTotal()` is `O(1)` per branch, though there is state creation and merging overhead.
- Using `distinct`/`sorted` or nesting large windows before or after a Gatherer can force the pipeline to buffer substantial data.
- If you need small summary statistics, avoid emitting large lists only to sum them downstream if you can design a direct accumulation instead.

Parallelism can only help if the source's Spliterator is splittable, the integrator work is heavy enough, the combiner is cheaper than the work split, and the transformation does not depend on order in a way that causes high coordination overhead.

## 16. Resource Management When Upstream Is I/O

A Gatherer does not change the responsibility for closing the Stream source:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<List<String>> readBatches(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> !line.isEmpty())
                .gather(BatchGatherers.fixedBatches(100))
                .toList();
    }
}
```

`Files.lines` opens a resource; `gather` is intermediate and `toList` is terminal. **Neither operation replaces `close`**. `try-with-resources` closes the Stream whether the source is empty, downstream stops early, or an error occurs while reading.

For very large files, `toList()` after a Gatherer still retains all emitted data in memory. If the goal is only to count lines per batch or compute statistics, emit compact results or use a memory-appropriate terminal operation.

If upstream is `BufferedReader.lines()`, the caller-owned Reader must be closed in the proper lifecycle scope. Do not return a lazy Stream from a Reader that was already closed inside a `try` block.

## 17. Minimal Test Suite for Custom Gatherers

A useful test suite should verify **outputs**, **state contracts**, **early termination**, and **parallelism** when a combiner is present.

### 17.1. Sequential Batching: Empty Source, Full Batch, Partial Batch

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

static void checkEquals(Object expected, Object actual) {
    if (!Objects.equals(expected, actual)) {
        throw new AssertionError(
                "Expected " + expected + ", actual " + actual
        );
    }
}

checkEquals(
        List.of(),
        Stream.<Integer>empty()
                .gather(BatchGatherers.fixedBatches(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3), List.of(4, 5)),
        Stream.of(1, 2, 3, 4, 5)
                .gather(BatchGatherers.fixedBatches(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3)),
        Stream.of(1, 2, 3)
                .gather(BatchGatherers.fixedBatches(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3)),
        Stream.of(1, 2, 3, 4, 5)
                .gather(BatchGatherers.fixedBatches(3))
                .limit(1)
                .toList()
);
```

Verify snapshotting: the first emitted batch must not change after later batches appear. Also verify that `size <= 0` throws `IllegalArgumentException` and a single-element source still produces the final batch per policy.

### 17.2. Sum with Combiner: Sequential and Parallel

```java
import java.util.List;
import java.util.stream.IntStream;

List<Long> a = IntStream.rangeClosed(1, 1000)
        .boxed()
        .gather(SumGatherers.oneTotal())
        .toList();

List<Long> b = IntStream.rangeClosed(1, 1000)
        .boxed()
        .parallel()
        .gather(SumGatherers.oneTotal())
        .toList();

checkEquals(List.of(500500L), a);
checkEquals(a, b);
```

Do not treat matching on a single run as sufficient proof that the combiner is correct. Add cases for empty data, a single element, repeated elements, negative values, and multiple parallel runs with varying source sizes. For bounded arithmetic ranges, watch for overflow conditions.

### 17.3. Testing Empty Data and Invalid Inputs

| Scenario | Expected Behavior |
| --- | --- |
| Empty source, batching Gatherer | Emits no empty batch |
| Single-element source, batch size 3 | Finisher emits a one-element batch |
| Batch size 0 or negative | Throws `IllegalArgumentException` before traversal |
| Downstream uses `limit(1)` | No results beyond the limit |
| Source contains null | Clear policy: allowed in `ArrayList` or explicitly rejected |
| Gatherer declares a parallel combiner | Results match sequential semantics |
| `Files.lines` source | Stream is closed after consumption |

An important note: `List.of(null)` is invalid; if you need to test null elements, you can use `Arrays.asList((String) null)` as the source.

## 18. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Supplier always returns the same mutable state | State leaks across partitions/runs | Allocate a new instance on each call |
| Using `null` as an uninitialized state marker | Ambiguous when null is a valid key | Use a separate `active` flag |
| Integrator mutates a variable outside the Stream | Data races, order dependence, and side effects | Keep state inside the Gatherer's `A` |
| Ignoring the return value of `downstream.push` | Fails to honor early termination requests | Use the `push` return value to decide whether to continue |
| Marking an integrator that self-stops on a threshold as `ofGreedy` | Framework may skip checking the return value | Only use Greedy if it does not **self**-short-circuit; forwarding downstream rejection is allowed |
| Missing finisher when buffered items remain | Final batch/group is lost | Emit remaining items per defined policy |
| Emitting state list then clearing or mutating it | Previously emitted output gets mutated | Emit an independent snapshot |
| Finisher emits data even after downstream rejected | Redundant emission or rejection | Track stop state and check `isRejecting` |
| Writing a combiner that only returns `left` | Loses data from the `right` branch | Properly merge both states |
| Enabling parallel for adjacent grouping without handling boundaries | Lost, duplicated, or mixed groups | Use `ofSequential` or prove the combiner |
| Assuming `defaultCombiner` merges states | Gatherer is evaluated sequentially only | Write a real combiner if parallelism is needed |
| Retaining a `Downstream` reference to push from another thread | Violates callback lifecycle contract | Use only within the invocation scope |
| Using a Gatherer for every `map`/`filter` operation | Unnecessary complexity | Prefer standard APIs |
| Collecting all windows in `toList` for large files | High memory usage despite lazy reading | Emit compact results or use an appropriate terminal |
| Assuming `gather`/`toList` closes I/O sources | Resource leak | Use `try-with-resources` |

## 19. Advanced Exercises

### Exercise A: Write a Gatherer That Emits Consecutive Character Runs

Source:

```text
A A B B B A C C
```

Expected output:

```text
(A,2), (B,3), (A,1), (C,2)
```

**Requirements:** initializer holds key/count and an `active` flag; integrator emits the previous group when the key changes; finisher emits the last group; use `Objects.equals` if keys may be null; do not write a combiner unless you have solved partition boundaries.

### Exercise B: Emit the Sum per Window Instead of a List

Replace `fixedBatches(k)` with a Gatherer holding `long sum` and `int count`. When `count == k`, emit a `Long` and reset state. At completion, specify whether a final partial batch smaller than `k` should be emitted.

**Criteria:** handle empty source, `k=1`, `k=3`, early termination, numeric ranges, and `long` overflow.

### Exercise C: Prove Combiner Correctness

For `oneTotal()`, simulate three states holding totals `10`, `20`, and `30` respectively. Compare:

```text
combine(combine(A, B), C) => 60
combine(A, combine(B, C)) => 60
```

Explain why an empty state (total 0) is the identity. Then try replacing the combiner with subtraction and show how the merge fails associativity.

### Exercise D: Threshold-Based Termination

Write a Gatherer that emits input elements until it encounters a value greater than a threshold, then stops. Clearly specify whether the element exceeding the threshold **is emitted or not**. Use the `push` return value to respect downstream `limit`.

**Criteria:** empty source, exceeding on the first element, never exceeding, and upstream holding closeable resources.

### Exercise E: Compare with Standard APIs

Try `Gatherers.windowFixed`, `Gatherers.windowSliding`, and `Gatherers.scan` to determine which problems **do not need** a custom Gatherer. Only write your own when boundary rules, outputs, or short-circuiting differ from built-in contracts.

## 20. Self-Check Questions

1. Is `Gatherer` an intermediate or terminal operation? **Intermediate**; `Stream.gather` allows chaining subsequent operations.
2. What are the three types `T`, `A`, `R`? **Input element, accumulated state, output emitted downstream**.
3. How must `initializer` create state? **Valid and independent on every call to the Supplier**.
4. Must `integrator` always emit exactly one output? **No**, it may emit 0, 1, or more.
5. What does `integrate` returning `false` mean? **Stop receiving further elements from upstream for that integration pass**.
6. What does `Downstream.push` returning `false` mean? **Downstream does not want to receive more elements**.
7. Does `Downstream.isRejecting()` returning `false` guarantee the next push will succeed? **No**, it is a best-effort check.
8. How does a Gatherer finisher differ from a Collector finisher? **A Gatherer finisher can push additional outputs; a Collector finisher converts state into the final result**.
9. When is a finisher most critical? **When unemitted groups or windows remain at the end of the source**.
10. Why must a buffer be snapshotted before emitting? **To prevent previously emitted output from being altered by subsequent accumulations**.
11. When is `combiner` called? **When the framework evaluates the Gatherer as parallel-capable and needs to merge states**.
12. Can the `right` branch be discarded in a combiner? **No**, doing so loses the result of a partition.
13. What does `defaultCombiner()` indicate? **The Gatherer is evaluated sequentially only**.
14. What does `defaultInitializer()` indicate? **The Gatherer is stateless; the framework may skip calling the initializer**.
15. What does `defaultFinisher()` indicate? **No end-of-stream work is needed; the framework may skip the finisher**.
16. When is `Integrator.ofGreedy` valid? **When the integrator does not itself initiate short-circuiting**; it may still propagate downstream's refusal of further output.
17. Why is consecutive grouping hard to parallelize? **Boundaries between partitions must be handled**.
18. Does `parallel()` automatically turn an `ofSequential` Gatherer into a valid state-splitting operation? **No**.
19. May `Downstream` be saved for use after the callback completes? **No**, because that violates the lifecycle contract.
20. Does `gather` automatically close `Files.lines`? **No**, the resource owner must close it with `try-with-resources`.
21. When you only need an integer sum, should you always use a custom Gatherer? **No**, `sum()` or `reduce()` is usually simpler.
22. From which Java version are standard Gatherers available? **Java 24**, following preview versions in Java 22 and 23.

## References

- [Java SE 24 — Gatherer API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): contracts of the four functions, factories, and state/parallel handling.
- [Java SE 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): `push` and `isRejecting`.
- [Java SE 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): guide to creating and using Gatherers.
- [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): milestone finalizing the API in Java 24.

**Application Principle:** The four functions `initializer`, `integrator`, `combiner`, and `finisher` are not four arbitrary callbacks, but **cooperating data-processing contracts**. Start with an independent initial state, integrate elements and emit output at the right time, respect downstream stop signals, only write a combiner when a valid merge is proven, and use the finisher for leftovers at the end of the source. For algorithms depending on adjacent elements, `ofSequential` is usually safer and clearer; for associative aggregations, `of` enables parallelism but still requires semantic testing. Finally, manage resources and memory independently of the fact that a Gatherer is lazy.
