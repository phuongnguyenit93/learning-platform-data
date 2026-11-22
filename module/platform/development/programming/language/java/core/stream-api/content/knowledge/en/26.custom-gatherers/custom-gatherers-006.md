# Designing Gatherers with a Combiner for Parallel Processing

In the **Java Stream API**, `map`, `filter`, `flatMap`, `reduce`, and `collect` solve many declarative data-processing problems. However, some transformations require **private state**, may emit zero, one, or multiple elements, and may emit results when the source finishes. **Stream Gatherers** provide the `Stream.gather(...)` extension point to describe such intermediate operations.

When you want a custom Gatherer to work effectively on a **parallel stream**, the hardest part is usually designing the **`combiner`**. This function does not merely "merge two objects": it must produce a state equivalent to the state obtained if all elements were processed according to the right semantics, regardless of how many partitions the framework splits the source into.

This lesson belongs to the **Building Custom Gatherers** chapter of the `JAVA_STREAM_API` module. We will build a Gatherer with all four components `initializer`, `integrator`, `combiner`, and `finisher`; analyze the associativity laws; test sequential/parallel equivalence; and recognize algorithms **that cannot be parallelized with a simple combiner alone**.

## 1. Java Version and Scope of the API

`Gatherer<T, A, R>`, `Gatherers`, and `Stream.gather(...)` are official APIs starting in **Java 24**. They previously appeared as **preview** features in Java 22 and Java 23; code in this lesson uses the standard API of **Java 24 and later**, requiring no preview flags when compiling with JDK 24.

```java
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;
```

In projects running only Java 17 or 21, you cannot copy `gather` examples directly and expect them to compile. In those cases, use `map`, `flatMap`, `collect`, a custom collector, or upgrade the JDK per the project roadmap.

A Gatherer is an **intermediate operation**: `stream.gather(gatherer)` returns a new stream, and actual processing is still triggered by a terminal operation such as `toList()`, `count()`, `findFirst()`, or `collect()`.

## 2. How Do the Four Components Cooperate?

The generic types of `Gatherer<T, A, R>` mean:

| Symbol | Role | Lesson Example |
| --- | --- | --- |
| `T` | Type of elements entering the Gatherer. | `Integer` |
| `A` | Private accumulated state type, may be mutable. | `State` holding count, sum, min, max |
| `R` | Type of elements emitted by the Gatherer downstream. | Immutable `Summary` |

A full Gatherer uses four functions:

| Component | Conceptual Signature / Meaning | Responsibility |
| --- | --- | --- |
| `initializer` | `Supplier<A>` | Creates a **new state** for each accumulation chunk as needed. |
| `integrator` | `(A, T, Downstream<R>) -> boolean` | Processes one input, updates state, and may `push` outputs. |
| `combiner` | `BinaryOperator<A>` | Merges two partial states into one equivalent state. |
| `finisher` | `(A, Downstream<R>) -> void` | Performs the final step after the source finishes, may emit results. |

On Java 24, the appropriate factory is:

```java
Gatherer.of(initializer, integrator, combiner, finisher);
```

Conceptual diagram with a split source:

```text
                       Splittable Stream<T>
                                |
                     +----------+----------+
                     |                     |
                   Part 1                Part 2
                     |                     |
               initializer()           initializer()
                     |                     |
               State A1                State A2
                     |                     |
            integrator() many times  integrator() many times
                     |                     |
                     +--------+------------+
                              |
                     combiner(A1, A2)
                              |
                        Combined State
                              |
                         finisher()
                              |
                     Downstream.push(R)
```

The number of parts, split points, execution order, and number of `combiner` invocations are framework decisions. **Never** write logic assuming the source is definitely split into two parts or that `combiner` is definitely called.

## 3. How Does Having a Combiner Differ from `ofSequential`?

A **stateful** Gatherer without a suitable combiner should use `Gatherer.ofSequential(...)`. If a Gatherer's `combiner()` is `Gatherer.defaultCombiner()`, that Gatherer **is executed sequentially only**, even when upstream is marked `parallel()`.

```java
// Conceptual, with State and integrator already defined:
Gatherer.ofSequential(State::new, integrator, finisher);

// Permits splitting and merging state when combiner is valid:
Gatherer.of(State::new, integrator, combiner, finisher);
```

The word **permits** is vital: supplying a combiner does not guarantee the runtime **will** execute in parallel, nor does it guarantee it is **faster**. The framework may choose a different execution plan depending on source, terminal operation, and Gatherer characteristics.

Conversely, for a **stateless** Gatherer, Java has `Gatherer.of(integrator)` which creates a parallelizable Gatherer without manually supplying state or a combiner:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> doubled =
    Gatherer.<Integer, Integer>of(
        (ignored, value, downstream) ->
            downstream.push(value * 2)
    );

List<Integer> result = Stream.of(1, 2, 3, 4)
    .parallel()
    .gather(doubled)
    .toList();

System.out.println(result); // [2, 4, 6, 8]
```

This is purely for **API demonstration**; simple one-to-one transformations should use `map(value -> value * 2)` instead of writing a custom Gatherer.

## 4. The Most Important Law: State Must Be Mergeable

Suppose the source is split into three segments `P`, `Q`, `R`. Let `S(P)` be the state obtained by accumulating segment `P`, and `C(a, b)` be the combiner.

The desired condition is:

\[
C(S(P), S(Q)) \equiv S(P \mathbin{+\!+} Q)
\]

Here `++` denotes concatenating two source segments in order if the input has encounter order. For three segments, the combiner must satisfy semantic **associativity**:

\[
C(C(a,b),c) \equiv C(a,C(b,c))
\]

If `e` is the empty state produced by the initializer, an identity element is required:

\[
C(e,a) \equiv a, \quad C(a,e) \equiv a
\]

The symbol `≡` refers to **observable results**, not requiring objects to have the same reference. For example, a combiner may mutate `left` and return `left`, provided it only mutates appropriate private state and preserves semantics.

**Associativity is not commutativity.** String concatenation `"A" + "B"` is associative, yet `"AB"` differs from `"BA"`. When output must preserve source order, the combiner must preserve the merge order of segments; never swap `left` and `right` arbitrarily. With unordered sources, clarify whether results are permitted to differ in order.

## 5. Sample Project: Parallel Statistics Gatherer Emitting One Report

Problem: input is a stream of `Integer`; output is **one `Summary`** containing count, sum, minimum, and maximum values. We do not emit results after each element. Each data partition accumulates into its own `State`; states are merged; finally, `finisher` emits the report.

This is a pedagogical example illustrating **a Gatherer's combiner**. If you only want integer statistics in a real application, `IntStream.summaryStatistics()` or `Collectors.summarizingInt(...)` is usually simpler.

### Complete Program (Java 24+)

```java
import java.util.List;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.stream.Gatherer;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public final class ParallelSummaryGatherer {
    private ParallelSummaryGatherer() {}

    // Output holds only immutable values.
    public record Summary(
        long count,
        long sum,
        OptionalInt minimum,
        OptionalInt maximum
    ) {}

    // Internal accumulation state per data partition.
    private static final class State {
        private long count = 0L;
        private long sum = 0L;
        private int minimum = Integer.MAX_VALUE;
        private int maximum = Integer.MIN_VALUE;

        void add(Integer boxedValue) {
            int value = Objects.requireNonNull(
                boxedValue, "Gatherer does not accept null"
            );

            count = Math.addExact(count, 1L);
            sum = Math.addExact(sum, (long) value);
            minimum = Math.min(minimum, value);
            maximum = Math.max(maximum, value);
        }

        State combine(State right) {
            // Empty state must act as identity.
            if (right.count == 0L) {
                return this;
            }
            if (this.count == 0L) {
                this.count = right.count;
                this.sum = right.sum;
                this.minimum = right.minimum;
                this.maximum = right.maximum;
                return this;
            }

            this.count = Math.addExact(this.count, right.count);
            this.sum = Math.addExact(this.sum, right.sum);
            this.minimum = Math.min(this.minimum, right.minimum);
            this.maximum = Math.max(this.maximum, right.maximum);
            return this;
        }

        Summary snapshot() {
            return new Summary(
                count,
                sum,
                count == 0L
                    ? OptionalInt.empty()
                    : OptionalInt.of(minimum),
                count == 0L
                    ? OptionalInt.empty()
                    : OptionalInt.of(maximum)
            );
        }
    }

    public static Gatherer<Integer, ?, Summary> summaryGatherer() {
        return Gatherer.<Integer, State, Summary>of(
            State::new,

            // Integrator: accumulate only; do not emit results yet.
            Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    state.add(element);
                    return true;
                }
            ),

            // Combiner: merge two independent States.
            (left, right) -> left.combine(right),

            // Finisher: emit exactly one final report.
            (state, downstream) ->
                downstream.push(state.snapshot())
        );
    }

    public static void main(String[] args) {
        List<Summary> sequential = IntStream
            .rangeClosed(1, 1_000)
            .boxed()
            .gather(summaryGatherer())
            .toList();

        List<Summary> parallel = IntStream
            .rangeClosed(1, 1_000)
            .boxed()
            .parallel()
            .gather(summaryGatherer())
            .toList();

        if (!sequential.equals(parallel)) {
            throw new AssertionError("Results are not equivalent");
        }
        if (parallel.size() != 1) {
            throw new AssertionError("Must have one report");
        }

        Summary report = parallel.get(0);
        System.out.println(report.count());                 // 1000
        System.out.println(report.sum());                   // 500500
        System.out.println(report.minimum().orElseThrow()); // 1
        System.out.println(report.maximum().orElseThrow()); // 1000

        List<Summary> empty = Stream.<Integer>empty()
            .gather(summaryGatherer())
            .toList();

        System.out.println(empty.get(0).count());           // 0
        System.out.println(empty.get(0).minimum().isEmpty()); // true
    }
}
```

Save as `ParallelSummaryGatherer.java`, compile and run with **JDK 24 or newer**:

```text
javac ParallelSummaryGatherer.java
java ParallelSummaryGatherer
```

This is practice code provided for learners to run; the lesson **does not present benchmark figures** and does not treat a single passing run as exhaustive testing of all partitionings.

## 6. Analyzing Each Component of the Program

### `initializer`: Fresh State per Partition

```java
State::new
```

When the framework splits the source, it may invoke the initializer multiple times to create independent `State`s. **Never** create a `State shared = new State()` outside and supply `() -> shared`: doing so causes multiple accumulations to share count/sum/min/max, breaking safe partitioning.

In the example, `State` is intentionally mutable, yet never exposed outside. **There is no need to synchronize every `State.add`** if the framework uses them per the Gatherer contract: each partition accumulates separately, and combining starts after accumulation of the relevant partitions finishes.

### `integrator`: Updating the Current Data Partition

```java
Gatherer.Integrator.ofGreedy(
    (state, value, downstream) -> {
        state.add(value);
        return true;
    }
)
```

`Integrator.ofGreedy` signals that the integrator does not self-short-circuit input consumption. It must still respect downstream if it emits elements and downstream wants no more. In the example, the integrator **does not `push` anything yet**, so it always returns `true`, leaving emission to `finisher`.

`Downstream.push(r)` returns a `boolean` indicating whether downstream still wants elements. When writing a Gatherer that emits multiple elements inside the integrator, inspect the return value and stop pushing once downstream rejects.

### `combiner`: Merging Two Partial Results

```java
(left, right) -> left.combine(right)
```

`left` and `right` are two states returned by the initializer or combiner, not two input `Integer` elements. `combine` in the example:

- Adds `count` and `sum`.
- Takes min of the two mins and max of the two maxes.
- Handles empty state as identity.
- Returns the merged state.

For values within permitted arithmetic bounds, the result does not depend on parenthesization of merges. `Math.addExact` proactively throws `ArithmeticException` when the sum exceeds `long`, avoiding silent overflow; for huge data, `BigInteger` or another arithmetic policy may be needed.

One subtle point: once a state has been passed to **combiner or finisher**, the framework will not hand that same state back to the integrator. This allows the combiner to merge and transfer state ownership, yet **does not** permit keeping a state reference to mutate later on another thread.

### `finisher`: One Report, Not One Report per Partition

```java
(state, downstream) -> downstream.push(state.snapshot())
```

Because `integrator` only accumulates and `combiner` merges states, the finisher emits **one final Summary**. The `Summary` record holds only primitives and `OptionalInt`, so it holds no reference to the mutable `State`.

Do not think the finisher runs once for **each partition** and magically merges emitted reports. For a Gatherer with a combiner, merging **state** is the necessary step before emitting the final result.

## 7. Self-Testing Combiner Laws

Do not merely run `parallel()` once and see the right answer. Test the state-merging function itself with hand-verifiable cases.

Example source `[2, 4, 6, 8]`:

| Partitioning | Individual States | Final Merge |
| --- | --- | --- |
| `[2, 4]`, `[6, 8]` | `(2,6,2,4)`, `(2,14,6,8)` | `(4,20,2,8)` |
| `[2]`, `[4,6,8]` | `(1,2,2,2)`, `(3,18,4,8)` | `(4,20,2,8)` |
| `[]`, `[2,4,6,8]` | Empty state and `(4,20,2,8)` | `(4,20,2,8)` |

The tuples mean `(count, sum, min, max)`. With non-overflowing data:

```text
combine(combine(A, B), C)
          ==
combine(A, combine(B, C))
```

**Note on mutation in tests:** `State.combine` in the example mutates the left object. Never reuse the **exact same State** to test both parenthesizations on it; the second test would observe a state already mutated by the first. Create independent state instances for each evaluation path and compare the final `Summary`.

A stronger test suite should check:

- Zero elements.
- One element.
- Many even/odd, negative, and positive numbers.
- `Integer.MIN_VALUE` and `Integer.MAX_VALUE`.
- Various split strategies, including empty segments.
- Sequential vs parallel results across varying source sizes.
- Sources with duplicate data, ensuring no lost or double-counted elements.

If the operation uses `double`, associativity **is no longer bit-exact** due to rounding rules. In that case, tests need explicit error tolerances and business rules; never assume sequential and parallel `double` sums match bit-for-bit.

## 8. Why Does Early Emission Make the Combiner Much Harder?

A Gatherer can emit results in the **integrator**, without waiting for the finisher. However, when outputs of a later partition **depend on the state of an earlier partition**, merging final states usually **cannot fix already-emitted results**.

For example, a **prefix sum** of `[1, 2, 3, 4]` must emit:

```text
Input:      1   2   3   4
Prefix:     1   3   6  10
```

Suppose the framework splits into `[1,2]` and `[3,4]`. If each part starts at sum `0` and emits immediately:

```text
Part 1 emits: [1, 3]
Part 2 emits: [3, 7]    <-- wrong: needs [6, 10]
```

Even if the combiner later adds the two partial sums (`3 + 7 = 10`), it **cannot retroactively fix `3,7` already emitted** from the second branch. Parallelizing a prefix scan requires a multi-phase algorithm: compute per-part sums, compute offsets for later parts, and adjust output values **before emitting them**. That is a different problem from merely supplying `(left, right) -> left.sum += right.sum`.

Java already provides `Gatherers.scan(...)` for ordered prefix scans, and `Gatherers.fold(...)` for order-dependent reductions. These two Gatherers express tasks that typically **require sequential evaluation** per contract, rather than bolting on a fake combiner to force parallel execution.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> prefixes = Stream.of(1, 2, 3, 4)
    .gather(Gatherers.scan(() -> 0, Integer::sum))
    .toList();

System.out.println(prefixes); // [1, 3, 6, 10]
```

**Core lesson:** when a transformation emits multiple elements depending on history, you must prove **the outputs** of each partition still match sequential execution, not just that the final states can be merged.

## 9. Associative Yet Non-Commutative: Order Is Also a Contract

A combiner merging list or string states might use concatenation:

```text
combine("AB", "CD") = "ABCD"
```

Concatenation is associative:

```text
("AB" + "CD") + "EF" = "AB" + ("CD" + "EF")
```

but not commutative:

```text
"AB" + "CD" != "CD" + "AB"
```

If a Gatherer relies on source order to build strings or lists, the combiner must preserve **the order of segments**. Never use a `HashSet` and expect encounter order to be preserved. If input comes from a source without encounter order or after calling `unordered()`, define clearly which outputs are considered valid.

With `windowFixed(3)`, source splitting creates another issue: a window may start in the left part and end in the right part. A correct combiner must **preserve or reconstruct elements at the boundary**, rather than merely concatenating two emitted window lists and dropping leftovers. Without a sound boundary-merging design, use `Gatherers.windowFixed(3)` instead of writing a custom parallel Gatherer.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows); // [[1, 2, 3], [4, 5, 6], [7]]
```

## 10. Common Broken Combiners

| Flawed Design | Consequence | Fix |
| --- | --- | --- |
| `(left, right) -> left` | Drops the entire right branch's state. | Merge full information from both branches. |
| `(left, right) -> right` | Drops the entire left branch. | Design the combine operation per business semantics. |
| `(left, right) -> new State()` | Loses accumulated data. | Return a state truly combining both branches. |
| Taking **average of two averages** | Wrong when sample counts differ across branches. | Merge `sum` and `count`, then divide at the end. |
| Merging min/max without handling empty state | May emit `MAX_VALUE`/`MIN_VALUE` sentinels as real data. | Design empty identity and `Optional` at finalization. |
| Sharing one `State` from initializer | Races, double-counting, or merging an object into itself. | `State::new` creates a separate instance per partition. |
| Combiner has external side effects, e.g. writing to a global `List` | Correctness depends on call schedule, hard to test. | Only merge the Gatherer's two states. |
| `left + right` on non-associative ops, like subtraction | Result can depend on partition boundaries. | Choose a state representation with a valid associative merge or use sequential. |
| Merging state after integrator emitted history-dependent prefixes | Partial outputs are already wrong and unfixable. | Design boundary/offset adjustment algorithm or use sequential `scan`. |
| Retaining a `Downstream` reference to `push` after callback returns | Violates API-defined lifecycle. | Only use downstream within valid integrator/finisher calls. |

### Example of the Average-of-Averages Bug

```text
Group A: [10]         -> mean = 10, count = 1
Group B: [20,30,40]   -> mean = 30, count = 3

(10 + 30) / 2 = 20         // WRONG
(10 + 20 + 30 + 40) / 4 = 25 // RIGHT
```

A proper `State` for averages stores `sum` and `count`, the combiner sums each field, and the finisher computes `sum / count`. If special decimal precision is required, select the numeric type and rounding policy before implementing.

## 11. Mutable State Does Not Mean It Must Be Thread-Safe

In a Gatherer with a valid combiner, the framework may create multiple states via initializer, process **independent partitions**, and then merge them. Thus a `State` with plain `long`/`int` fields or an internal `ArrayList` can be used safely **within its private state scope** without needing `AtomicLong` or locks.

However, here is what you **must not do**:

- Keep a shared `State` in a static field for all integrators to update together.
- Return mutable state directly in results where other code could mutate it before the stream finishes.
- Capture a `State` or `Downstream` reference and retain it for use on another thread after the callback ends.
- Spawn an async task inside the integrator and let that task keep mutating state after the integrator returns.
- Equate `parallel()` with "one thread per element", or predict how many times the framework calls initializer/combiner.

**Do not use a globally synchronized state to dodge designing a combiner.** That can erase parallel gains, alter semantics, and destroy partition independence.

## 12. Testing Techniques Independent of Runtime Split Schedules

There is no basis for writing a test asserting that on 1,000 inputs the runtime always calls `combiner` 3 times or always uses 4 workers. A good test suite focuses on **result invariants**:

1. Run sequentially on the same data to get the expected `Summary`.
2. Run in parallel multiple times and compare **values**, not callback schedules or threads.
3. Test on ordered array/`ArrayList` sources and unordered sources if semantics permit.
4. Check empty state, single element, negative numbers, boundary values, and duplicates.
5. Directly test identity/associativity laws on **fresh** states, never reusing states already mutated by a combiner.
6. Test short-circuiting downstream like `limit` or `findFirst` per the Gatherer's actual **output contract**; do not infer every element must have passed through the integrator.
7. If the combiner performs a non-commutative merge, explicitly test **order preservation**.

In our statistics example, `Math.addExact` intentionally fails on `long` overflow. That is better than returning a silent wrong total, though it means inputs whose **intermediate** sum overflows cannot be processed successfully. To support any integer input over a wider range, replace `sum` with a non-overflowing type like `BigInteger` and design the combiner accordingly.

**Separate correctness tests from benchmarks:** matching sequential/parallel outputs only verifies tested input cases; it does not prove the parallel version is faster.

## 13. With a Combiner in Place, Why Can It Still Be Slow?

Scalability depends on several factors:

| Factor | Possible Consequence |
| --- | --- |
| Small source, cheap integrator | Split/merge and state-creation overhead exceeds gains. |
| Hard-to-split Spliterator or ineffective `trySplit()` | Fails to utilize multiple workers. |
| Combiner must concatenate/copy large containers | Merge cost grows with data size, potentially making parallel slower. |
| Finisher builds a huge output | Post-merge work becomes a sequential bottleneck. |
| Integrator holds heavy state | Memory and cache pressure grows with partition count. |
| Ordered source and order-dependent algorithm | Must maintain boundary order, raising coordination cost. |
| Mapper or accumulation performs blocking I/O | Workers block waiting for I/O; parallel stream is not a connection scheduler. |
| Multiple concurrent requests sharing resources | CPU, memory, and pool contention causes latency jitter. |

For example, the count/sum/min/max statistics Gatherer merges only a few fields, so **combiner cost is small**. But if the real task writes files, concatenates a million strings, or retains every element for post-processing, merge costs can be completely different.

When benchmarking, compare **sequential stream**, **parallel stream with Gatherer**, and a **standard collector/reduction** approach for the same requirement. Use JMH with warm-up, multiple iterations/forks, and pre-built inputs outside the measured section; observe throughput, time/op, and allocations. Never claim an assumed speedup without real measurements.

## 14. Gatherer with Combiner or Regular Collector?

Not every aggregation problem warrants writing a new Gatherer:

| Need | Typically Suitable API | Why |
| --- | --- | --- |
| Compute sum, count, min, max for numeric streams | `IntStream.summaryStatistics()` | Built-in, readable, no manual state/combiner management. |
| Aggregate a `Stream<T>` into one value | `reduce` or `collect` | Terminal reduction expresses the single-output goal directly. |
| Collect elements into `Map<K,V>` or groups | `toMap`, `groupingBy`, `groupingByConcurrent` | Standard collectors already handle accumulation and combining. |
| Stateless one-to-one transformation | `map` | Simpler than `Gatherer.of`. |
| Simple one-to-many transformation | `flatMap` or `mapMulti` | No need to manage a combiner for a stateful algorithm. |
| Ordered prefix scan | `Gatherers.scan` | History-dependent, cannot be merged via simple final-state sum. |
| Fixed windowing | `Gatherers.windowFixed` | Handles window boundaries per contract. |
| Novel stateful transformation with merge rules | **Custom Gatherer with combiner** | Controls intermediate output and parallelizability. |

In the statistics example, Gatherer is a way **to learn the Stream extension mechanism**; typical production code may only need:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics summary =
    IntStream.rangeClosed(1, 1_000).parallel().summaryStatistics();

System.out.println(summary.getSum()); // 500500
```

Use a custom Gatherer when built-in operations cannot express the semantics, or when that design clearly improves composability with other `gather` steps in a pipeline.

## 15. Practice Exercises

**Exercise 1 — Prove the combiner yourself.** Write a `State` with `count` and `sum`, and test merging states from `[1,2]`, `[3]`, `[4,5]` under both parenthesizations. Show both yield `(count=5,sum=15)` and an empty state leaves the result unchanged.

**Exercise 2 — Test boundary data.** Run `summaryGatherer()` with an empty stream, one element, `Integer.MIN_VALUE`, and `Integer.MAX_VALUE`. Why must `OptionalInt` be used for min/max of an empty group instead of exposing `Integer.MAX_VALUE` as a real measurement?

**Exercise 3 — Average metric.** Extend `Summary` with an average. Compute `sum/count` only inside the finisher after the combiner has merged sum and count. Explain why the average of two averages is wrong when two partitions have different sample counts.

**Exercise 4 — Analyze a flawed design.** A Gatherer uses `() -> sharedState` for initializer and `(left,right) -> left` for combiner. Point out at least two independent bugs, and explain why changing `sharedState` to an object using `AtomicLong` does not fix all of them.

**Exercise 5 — Prefix scan.** For `[1,2,3,4]`, split into two parts and compute local prefixes. Show the offset the second part needs to add to produce `[1,3,6,10]`. Why is a combiner that merges final sums without touching already-emitted values insufficient?

**Exercise 6 — Order.** Imagine a Gatherer joining names with commas in source order. Which combiner is associative, and why can `combine(right,left)` break the result? What changes when the source has no encounter order?

**Exercise 7 — Design a benchmark.** On JDK 24+, compare `summaryGatherer()`, `IntStream.summaryStatistics()`, and a `for` loop across multiple data sizes, verifying equivalent outputs. Record real measurements and explain the overhead of state, combiner, boxing/unboxing, and source splitting before drawing conclusions.

## 16. Checklist Before Choosing a Parallel Gatherer

- [ ] Confirmed JDK supports `Stream.gather` and `Gatherer.of` (Java 24+ for standard API).
- [ ] Problem genuinely needs a Gatherer transformation rather than just `map`, `collect`, or `reduce`.
- [ ] Initializer creates a **new state** for each accumulation partition.
- [ ] Integrator updates only the passed-in state without mutating the source or global state.
- [ ] Combiner preserves **complete information** from both states, with identity and semantic associativity.
- [ ] Encounter order has been accounted for if output is non-commutative.
- [ ] Does not emit partial outputs too early if later adjustments from earlier parts are needed.
- [ ] Finisher creates proper output without leaking mutable state.
- [ ] Does not retain state or `Downstream` outside callback invocation lifetime.
- [ ] Tested on empty data, boundary values, and multiple split layouts.
- [ ] Compared sequential/parallel by **values**, independent of thread count or combiner call count.
- [ ] Evaluated arithmetic limits, memory, Spliterator, performance, and termination conditions.

**Remember:** A Gatherer with a combiner is **not** simply a sequential Gatherer with a state-merging lambda tacked on. To parallelize properly, the initializer must supply independent states, the integrator must not leak or share state, the combiner must preserve **semantics across all split/merge trees**, and the finisher must emit output only when the needed data is complete. If output depends on history or partition boundaries without a valid correction algorithm, choose a sequential Gatherer or redesign the transformation instead of forcing `parallel()`.

**Official API Docs:** [Gatherer (Java 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html), [Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html), [Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html), and [Stream.gather](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer)).
