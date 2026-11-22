# Managing Private State Per Processing Partition

In the Java Stream API, `filter` and `map` are typically described using stateless functions. However, some problems require remembering data across elements: counting encountered records, computing a running total, grouping consecutive elements into a group, or producing a report only when the source finishes. **Stream Gatherers** provide a mechanism to build stateful intermediate operations instead of pushing counters or a shared `ArrayList` outside the pipeline.

This topic has a common point of confusion: **a Gatherer's state is not necessarily a single object for the entire Stream**. For a parallelizable Gatherer, the system may split the source into multiple **processing partitions** (*partitions*), create an independent state for each partition, and then **combine the states**. The number of partitions, executing threads, and timing of combination are implementation details that a program should never assume to be fixed.

The lesson **"Managing Private State Per Processing Partition"** belongs to the **Building Custom Gatherers** chapter of the **JAVA_STREAM_API** module. We will connect these concepts to lazy pipelines, `reduce`, `collect`, `Spliterator`, and parallel Streams, while clarifying constraints around state, order, resources, early termination, and correctness.

> **JDK Milestone:** `java.util.stream.Gatherer`, `Gatherers`, and `Stream.gather` are standard APIs starting in **Java 24**. Java 22 and 23 provided preview versions, but the code examples below target **JDK 24+**, without depending on preview flags. Verify both the build JDK and deployment runtime.

## 1. Learning Objectives

After completing this lesson, you should be able to:

1. Explain the generic type `Gatherer<T, A, R>` and the role of state `A`.
2. Distinguish between **partition-local state**, **pipeline-wide state**, and **external shared variables**.
3. Know when to use `Gatherer.ofSequential(...)` and when to use `Gatherer.of(...)` with a `combiner`.
4. Design an `initializer` that creates a **new state object**, rather than returning a shared mutable object.
5. Write an `integrator` that can update state and emit results via `Downstream.push`.
6. Write a `combiner` that preserves data when two partitions are merged, without relying on a fixed execution schedule.
7. Use a `finisher` to emit final results while respecting downstream's stop requests.
8. Test state independence across runs and equivalent results between sequential and parallel execution.

## 2. What Is a Gatherer in a Stream Pipeline?

A Gatherer transforms `Stream<T>` into `Stream<R>`. Unlike regular `map`, which produces only one value per element, a Gatherer can produce **zero, one, or more outputs**, maintain state, and emit final results at completion.

~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> windows = List.of(1, 2, 3, 4, 5)
    .stream()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows);
// [[1, 2], [3, 4], [5]]
~~~

`Gatherers.windowFixed(2)` is a built-in Gatherer that groups elements into windows of at most two elements. It maintains state to hold elements waiting to form a window. This lesson goes further: **managing state yourself** for a Gatherer and deciding how to handle it when the source is split.

The basic components of a custom Gatherer are:

~~~text
Source Stream<T>
      |
      v
Gatherer<T, A, R>
  initializer: creates A
  integrator: (A, T, Downstream<R>) -> boolean
  combiner:   (A, A) -> A
  finisher:   (A, Downstream<R>) -> void
      |
      v
Stream<R> -> filter/map/limit/collect/...
~~~

This is an **intermediate operation**, not a terminal collector. After `gather(...)`, the pipeline can continue with `filter`, `limit`, `map`, or `collect`.

## 3. The Three Type Parameters T, A, and R

The generic interface has the form:

~~~java
Gatherer<T, A, R>
~~~

| Parameter | Role | Example |
|---|---|---|
| `T` | Input element type | `Integer`, `Payment`, `String` |
| `A` | **Intermediate state** type, may be mutable | `CounterState`, `HashMap<String, Long>` |
| `R` | Element type emitted downstream | `Summary`, `Run<String>`, `List<Integer>` |

For example, a Gatherer that receives integers, stores count/sum in `CounterState`, and then emits a `Summary` has the type:

~~~java
Gatherer<Integer, CounterState, Summary>
~~~

`A` is **not** the partition count, thread name, or default "final result". It is simply the state type used by the Gatherer's functions. A parallel execution may create **multiple distinct `A` instances**.

For some factory methods, the type `A` can be hidden with a wildcard:

~~~java
Gatherer<Integer, ?, Summary> gatherer = ...;
~~~

Hiding the state type in the public API is good practice when callers of the Gatherer only need to know **inputs and outputs**, without depending on the internal container structure.

## 4. What Is a Processing Partition?

Imagine a source with eight elements:

~~~text
Source: [2, 4, 3, 1, 5, 8, 6, 7]
~~~

When running in parallel, the system *may* split the source into multiple partitions:

~~~text
                [2, 4, 3, 1, 5, 8, 6, 7]
                     /           \
              [2, 4, 3, 1]     [5, 8, 6, 7]
                  |                 |
             State A1           State A2
           count=4,sum=10     count=4,sum=26
                  \                /
                   combiner(A1, A2)
                         |
                   count=8,sum=36
                         |
                      finisher
                         |
                    Summary(8,36)
~~~

**Important:** this diagram is only one *possible* split. Java does not guarantee exactly two partitions, a split down the middle, each partition bound to a fixed thread, or that `combiner` is called exactly once.

A partition is an **accumulation unit** managed by the framework. It is not a "data page", "database transaction", or "business group" unless the algorithm and source explicitly define it as such.

### 4.1. Private State Differs from ThreadLocal

| State | Meaning | Should it be used as `A`? |
|---|---|---|
| Object from `initializer.get()` | State of one Gatherer partition | **Yes**, this is the standard model |
| External instance field holding shared state | Multiple runs may mutate the same object concurrently | **No**, if that state is used as the Gatherer's mutable container |
| Mutable `static` variable | Persists across calls and potentially across threads | Unsuitable for holding partition accumulation state |
| `ThreadLocal` | Bound to a thread, not a logical partition | Does not replace `initializer` |
| Current value `T` being processed | One input element | Not synonymous with accumulated state `A` |

Partitions may be processed and merged by different threads. Never assume "one thread = one Gatherer state".

## 5. The Four-Function Contract of a Gatherer

Java 24 describes a Gatherer through four components:

| Component | Conceptual Signature | Responsibility |
|---|---|---|
| `initializer()` | `Supplier<A>` | Creates the initial state for a partition |
| `integrator()` | `Integrator<A, T, R>` | Receives each element, updates state, and may emit output |
| `combiner()` | `BinaryOperator<A>` | Combines states from processed partitions |
| `finisher()` | `BiConsumer<A, Downstream<? super R>>` | May emit output after the source has been processed |

For a **stateless** Gatherer, the default `initializer` can indicate that no container is needed. For a **sequential** Gatherer, the default combiner serves as a marker that this operation **is not evaluated via parallel partitioning**.

### 5.1. Conceptual Lifecycle

~~~mermaid
flowchart TD
    A["Stream Source"] --> B{"Gatherer allows parallelism?"}
    B -->|No| C["One logical accumulation flow"]
    B -->|Yes| D["Independent partitions"]
    C --> E["initializer → integrator*"]
    D --> F["Separate initializer → integrator*"]
    F --> G["combiner merges state"]
    E --> H["finisher (if any)"]
    G --> H
    H --> I["Downstream output"]
~~~

The `*` here means the integrator is called multiple times depending on the amount of data to process. This is a conceptual diagram, not a description of exact thread counts or call counts.

### 5.2. State Ownership Boundaries

According to the Gatherer contract:

- State passed into `integrator` must be a state previously created by `initializer` or `combiner`.
- Under parallel evaluation, partitions are processed independently; `combiner` only merges after the corresponding accumulations have completed.
- Once a state has been handed to `combiner` or `finisher`, the framework does not pass that exact state into `integrator` again.
- Functions must not **retain or expose references** to state or `Downstream` for another thread to use after the function call returns.
- When the integrator returns `false`, accumulation does not continue in the same way; this is an early-termination request, not a "skip element" return value.

This allows a **locally mutable** state without locking around every field, provided it is not published externally or used in violation of the contract.

## 6. Choosing ofSequential or of with a combiner?

Java 24 provides factory methods to avoid having to write an entire class implementing `Gatherer`.

### Stateful Gatherer, Sequential Processing Only

~~~java
Gatherer.ofSequential(
    initializer,
    integrator,
    finisher
)
~~~

You can omit `finisher` if there is no work to do at the end.

### Stateful and Parallelizable Gatherer

~~~java
Gatherer.of(
    initializer,
    integrator,
    combiner,
    finisher
)
~~~

**Key difference:** `combiner` is not an "optional parameter to run faster". It is a **semantic contract** proving that local states can be merged without altering the expected result.

If the problem's state depends on overall **consecutive order** and you do not know how to merge partition boundaries correctly, **do not write a fake combiner**. Choose `ofSequential` first to preserve correctness.

### 6.1. A parallel Stream Can Still Contain a Sequential Gatherer

~~~java
List<Integer> source = List.of(1, 2, 3, 4, 5);

List<Integer> output = source.parallelStream()
    .gather(mySequentialGatherer)
    .toList();
~~~

This snippet illustrates an existing Gatherer variable named `mySequentialGatherer`. If the Gatherer has `defaultCombiner()` (for instance, created via `ofSequential`), **evaluation of that Gatherer** is not partitioned/parallelized by contract.

Do not infer that every remaining step in the pipeline always runs on one thread, or that `parallelStream()` is "permanently converted" into a different Stream type. Distinguish **pipeline mode** from **the parallelizability of a specific Gatherer**.

## 7. Example 1: Grouping Consecutive Runs Using Sequential State

Problem: the source has many consecutively repeated status codes that need to be compressed into **value + consecutive occurrence count** (*run-length encoding*).

~~~text
Input:  [A, A, B, B, B, A, C, C]
Output: [Run(A,2), Run(B,3), Run(A,1), Run(C,2)]
~~~

This is an ideal example for understanding state:

- `previous`: value of the current consecutive group.
- `count`: number of elements seen in that group.
- `present`: whether the first element has been received yet.

State must be **newly created for each evaluation**, never placed in a shared global list or variable.

### 7.1. Complete Java 24+ Program

Create the file `SequentialRunsDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class SequentialRunsDemo {

    record Run<T>(T value, long count) {}

    static <T> Gatherer<T, ?, Run<T>> consecutiveRuns() {

        class State {
            boolean present;
            T previous;
            long count;
        }

        return Gatherer.<T, State, Run<T>>ofSequential(
            State::new,
            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    if (!state.present) {
                        state.present = true;
                        state.previous = value;
                        state.count = 1L;
                        return true;
                    }

                    if (Objects.equals(state.previous, value)) {
                        state.count = Math.addExact(state.count, 1L);
                        return true;
                    }

                    // Encountered a different value: complete the old group.
                    if (!downstream.push(
                            new Run<>(state.previous, state.count))) {
                        return false;
                    }

                    // Start the next group.
                    state.previous = value;
                    state.count = 1L;
                    return true;
                }
            ),
            (state, downstream) -> {
                // Only emit the last group if downstream still accepts data.
                if (state.present && !downstream.isRejecting()) {
                    downstream.push(
                        new Run<>(state.previous, state.count)
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Run<String>> result = Stream.of(
                "A", "A", "B", "B", "B", "A", "C", "C"
            )
            .gather(consecutiveRuns())
            .toList();

        System.out.println(result);
        // [Run[value=A, count=2], Run[value=B, count=3],
        //  Run[value=A, count=1], Run[value=C, count=2]]

        List<Run<String>> empty = Stream.<String>empty()
            .gather(consecutiveRuns())
            .toList();

        System.out.println(empty); // []
    }
}
~~~

### 7.2. Reading State Transitions

| Input element | `previous` before | `count` before | Action | Output at that moment |
|---|---|---:|---|---|
| A | None | 0 | Start group A | None |
| A | A | 1 | Increment count | None |
| B | A | 2 | Emit Run(A,2), start B | Run(A,2) |
| B | B | 1 | Increment count | None |
| B | B | 2 | Increment count | None |
| A | B | 3 | Emit Run(B,3), start A | Run(B,3) |
| C | A | 1 | Emit Run(A,1), start C | Run(A,1) |
| C | C | 1 | Increment count | None |
| End | C | 2 | `finisher` emits final group | Run(C,2) |

Without `finisher`, the final group would not be emitted because **there is no next element** to trigger closing the previous group.

### 7.3. Why Is the present Variable Needed?

A source can validly contain `null` if the source contract permits it. In that case, `previous == null` is **not enough** to distinguish "no element yet" from "current group value is null".

`present` acts as a logical sentinel; `Objects.equals(a, b)` safely compares two nullable values. Depending on business rules, you could also filter out nulls beforehand, but that is **a different data policy**.

### 7.4. Why Use ofSequential?

Imagine the source `[A, A, A, A]` being split:

~~~text
Partition 1: [A, A]  → Run(A,2)
Partition 2: [A, A]  → Run(A,2)

Desired global result: Run(A,4)
~~~

If each partition **emits Run(A,2) right before combining**, a `combiner` that only merges final counts cannot "retract" two results already pushed downstream. To parallelize correctly, you must design a way to **retain boundary data** and defer/adjust output, instead of attaching a simple count-summing combiner.

Because the problem depends on **adjacent elements**, `ofSequential` is the clear and semantically sound choice for the first version.

## 8. Greedy Integrator and Early Termination

In the example above, we used:

~~~java
Gatherer.Integrator.ofGreedy((state, element, downstream) -> {
    // ...
    return true;
})
~~~

`Integrator.Greedy` indicates that the integrator **does not proactively short-circuit**: it processes all incoming elements passed to it, except when downstream no longer wants additional elements.

If you are unsure whether an algorithm is greedy, do not mark it greedy just hoping for optimization. An integrator that needs to stop upon meeting a business condition must use the appropriate `Integrator` contract and return `false` when it wants to stop further accumulation.

### 8.1. What Does Downstream.push Returning boolean Mean?

~~~java
boolean wantsMore = downstream.push(result);
~~~

- `true`: downstream still accepts output.
- `false`: downstream already knows it does not need more; subsequent `push` calls will no longer be accepted.

A practical example is when a later stage in the pipeline uses `limit(2)`. After receiving two results, downstream may reject further results. Therefore, the integrator in section 7 **returns `false` if `push` returns `false`**, instead of continuing to compute and emit uselessly.

`downstream.isRejecting()` is a **best-effort** check to know whether downstream has stopped accepting. If it returns `true`, you should stop emitting output. If it returns `false`, there is no guarantee downstream will accept every subsequent `push`; always check the return value of `push` when emitting a sequence of outputs.

### 8.2. Do Not Use Side Effects to Measure Processed Element Count

~~~java
List<Run<String>> firstTwo = Stream.of(
        "A", "A", "B", "B", "C", "C"
    )
    .gather(consecutiveRuns())
    .limit(2)
    .toList();
~~~

The result is the first two runs in encounter order. However, **do not test the number of integrator calls, thread count, or initializer calls using a counter variable outside the pipeline**, because the system may short-circuit or use a different execution strategy to satisfy the contract.

## 9. Why Isn't a Combiner Simply Adding Two Numbers?

For an algorithm with local state, `combiner` must answer:

> If the left partition was processed independently and the right partition was as well, how do we merge **the full meaning of the two state results** to obtain the same output as continuous traversal?

Some algorithms are easy to combine:

- Counting elements: add the two counts.
- Summing: add the two sums (requires an overflow policy).
- Finding the maximum: take the max of two present values.
- Counting by key: sum counts for matching keys from two Maps.

Some algorithms are harder to combine:

- Counting transitions **between consecutive elements**: requires knowing values at the right/left boundaries.
- Sliding windows: requires retaining enough prefix/suffix to reconstruct windows spanning across partition boundaries.
- Global sequential numbering: each partition does not yet know the offset of preceding parts.
- Emitting running totals at each element: values already emitted in the right partition would need the left partition's total added as an offset.

If you have not proven a valid merge across all possible partitionings, **do not declare the Gatherer as parallelizable**.

## 10. Example 2: Statistics with Partition-Private State

Problem: receive **non-negative** integers and produce exactly **one final statistics record** containing:

- `count`: number of elements.
- `sum`: sum of values.
- `evenCount`: number of even elements.

Because all three metrics can be combined via addition, this is a suitable example for writing `Gatherer.of(initializer, integrator, combiner, finisher)`.

### 10.1. Complete Java 24+ Program

Save as `PartitionStateDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class PartitionStateDemo {

    record Summary(long count, long sum, long evenCount) {}

    static Gatherer<Integer, ?, Summary> summarizeNonnegative() {

        class State {
            long count;
            long sum;
            long evenCount;
        }

        return Gatherer.<Integer, State, Summary>of(
            // Each partition is given an independent state.
            State::new,

            // Accumulate from each element; do not emit output yet.
            Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    Objects.requireNonNull(element, "element");
                    if (element < 0) {
                        throw new IllegalArgumentException(
                            "Only non-negative numbers are accepted");
                    }

                    state.count = Math.addExact(state.count, 1L);
                    state.sum = Math.addExact(
                        state.sum, element.longValue());

                    if ((element & 1) == 0) {
                        state.evenCount = Math.addExact(
                            state.evenCount, 1L);
                    }
                    return true;
                }
            ),

            // Merge two independently processed states.
            (left, right) -> {
                left.count = Math.addExact(left.count, right.count);
                left.sum = Math.addExact(left.sum, right.sum);
                left.evenCount =
                    Math.addExact(left.evenCount, right.evenCount);
                return left;
            },

            // After merging completes, emit exactly one Summary.
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(
                        new Summary(
                            state.count, state.sum, state.evenCount)
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 3, 1, 5, 8);

        List<Summary> sequential = source.stream()
            .gather(summarizeNonnegative())
            .toList();

        List<Summary> parallel = source.parallelStream()
            .gather(summarizeNonnegative())
            .toList();

        System.out.println(sequential);
        // [Summary[count=6, sum=23, evenCount=3]]

        System.out.println(parallel);
        // [Summary[count=6, sum=23, evenCount=3]]

        if (!sequential.equals(parallel)) {
            throw new AssertionError(
                "Sequential and parallel results differ");
        }
    }
}
~~~

### 10.2. Why Can the Combiner Mutate left?

`left` and `right` are **two local states** handed to the combiner by the framework after partitions have finished accumulating. In the example, the combiner transfers totals from `right` into `left` and returns `left`.

This is valid because they are not used as two concurrent containers after merging; the framework only uses the **combined state** per contract. However, you must not place `left` into a `static` field, store a reference to `right` elsewhere, or return them through the Stream for external code to keep mutating.

### 10.3. Why Not Emit a Summary per Partition?

In the example, the integrator **only accumulates**, while the finisher calls `push` for the Summary. When running in parallel, local states can be completely merged before emitting **a single final result**.

If the integrator pushed a `Summary` per element or per partition and the combiner tried to sum at the end, the already-emitted results would no longer reflect statistics for the **entire source**. A state `combiner` **cannot retroactively modify data already emitted** downstream.

### 10.4. Why Use Math.addExact?

With inputs already validated as **non-negative**, accumulation is easier to reason about and `Math.addExact` throws `ArithmeticException` if `long` overflows. This implements a **fail-loudly instead of silent overflow** policy.

Keeping inputs non-negative also avoids cases where intermediate sums of mixed-sign data might overflow under one grouping but not under another. In systems with arbitrary data requiring exact sums independent of splitting, consider `BigInteger` or an explicitly designed arithmetic policy.

### 10.5. Key Takeaway from the Example

We **do not manually split the List**, call `new Thread`, or write synchronization around every state field. The Stream framework manages partitions; the Gatherer provides **how to create state**, **how to update each state**, **how to merge states**, and **how to emit results**.

However, `parallelStream()` does not guarantee the program will actually create more than one state: the system may choose an execution strategy suited to the workload. Tests must rely on **outputs**, not on the number of times the supplier is invoked.

## 11. State Invariants Help Prove Correctness

In the `PartitionStateDemo` example, for each partition that processed a set of elements `P`, we define:

~~~text
state.count     = number of elements in P
state.sum       = sum of values in P
state.evenCount = number of even elements in P
~~~

A fresh state from the initializer represents the empty set:

~~~text
count = 0, sum = 0, evenCount = 0
~~~

After the integrator processes each non-negative element `x`, all three invariants still hold:

~~~text
count'     = count + 1
sum'       = sum + x
evenCount' = evenCount + (x is even ? 1 : 0)
~~~

When two disjoint partitions `P1` and `P2` are merged:

~~~text
count(P1 ∪ P2)     = count(P1) + count(P2)
sum(P1 ∪ P2)       = sum(P1) + sum(P2)
evenCount(P1 ∪ P2) = evenCount(P1) + evenCount(P2)
~~~

Because addition of these triples **is associative** over valid values, different groupings and merge trees yield the same final result, provided there is no overflow and no unintended mutation of data.

This is the real justification for calling `of(...)` with a combiner, rather than because "this function looks like it can run in parallel".

## 12. Example 3: Per-Partition Private Map State

Another problem: count occurrences of each keyword. A `HashMap` is a natural state per partition; the combiner merges counts for matching keys.

### 12.1. Complete Java 24+ Program

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Gatherer;

public class PartitionFrequencyDemo {

    static Gatherer<String, ?, Map<String, Long>> frequencies() {
        return Gatherer
            .<String, HashMap<String, Long>, Map<String, Long>>of(
                HashMap::new,

                Gatherer.Integrator.ofGreedy(
                    (counts, word, downstream) -> {
                        if (word == null || word.isBlank()) {
                            throw new IllegalArgumentException(
                                "Invalid keyword");
                        }

                        counts.merge(
                            word, 1L,
                            (a, b) -> Math.addExact(a, b)
                        );
                        return true;
                    }
                ),

                (left, right) -> {
                    right.forEach((word, amount) ->
                        left.merge(
                            word, amount,
                            (a, b) -> Math.addExact(a, b)
                        )
                    );
                    return left;
                },

                (counts, downstream) -> {
                    if (!downstream.isRejecting()) {
                        // Copy to avoid exposing the mutable accumulation Map.
                        downstream.push(Map.copyOf(counts));
                    }
                }
            );
    }

    public static void main(String[] args) {
        List<String> words = List.of(
            "java", "stream", "java", "api", "stream", "java"
        );

        List<Map<String, Long>> reports = words.parallelStream()
            .gather(frequencies())
            .toList();

        System.out.println(reports.size()); // 1

        Map<String, Long> expected = Map.of(
            "java", 3L,
            "stream", 2L,
            "api", 1L
        );

        if (!reports.get(0).equals(expected)) {
            throw new AssertionError("Incorrect count result");
        }

        System.out.println(reports.get(0).get("java")); // 3
    }
}
~~~

### 12.2. Three Technical Decisions to Note

**First is the `HashMap::new` supplier.** Every initial state must be a **new** Map, not a Map from a static variable or an object pre-created outside.

**Second is merging by key.** `left.putAll(right)` is **wrong** if a key appears in both partitions because it overwrites `left`'s count. `Map.merge` with addition preserves the true total occurrence count.

**Third is snapshotting in the finisher.** `Map.copyOf(counts)` creates an unmodifiable result Map, preventing callers from holding a reference to the mutable `HashMap` used for accumulation.

`Map.copyOf` does not guarantee key iteration order. If the output must be sorted by keyword name, choose an appropriate result structure or sort at the display step; never rely on `HashMap` having a stable order.

### 12.3. When Should You Not Write a Word-Counting Gatherer Yourself?

If you only need **a single final frequency report**, a shorter approach is usually a terminal collector:

~~~java
Map<String, Long> counts = words.parallelStream()
    .collect(java.util.stream.Collectors.groupingBy(
        word -> word,
        java.util.stream.Collectors.counting()
    ));
~~~

Both can satisfy the same simple requirement. A Gatherer is worthwhile when you need **an intermediate operation that can be further composed** or specialized custom behavior, not because every aggregation needs to be converted into a Gatherer.

**Goal-driven design:** if you do not need `Stream.gather(...)`, do not add complexity just to showcase a new API.

## 13. Why Must a State Not Be Shared Across Multiple Partitions?

Here is a **wrong** example:

~~~java
class CounterState {
    long count;
}

CounterState shared = new CounterState();

// Wrong: every initializer call returns the exact same object.
// Do not use:
// Gatherer.of(
//     () -> shared,
//     (state, value, downstream) -> { state.count++; return true; },
//     (left, right) -> left,
//     (state, downstream) -> downstream.push(state.count)
// );
~~~

If two partitions both receive `shared`, they update `count` concurrently. This creates a **race condition** and breaks the independent-accumulation contract. Furthermore, the combiner may receive two references **to the same object**, causing merging/addition to double-count.

Fix it with a supplier that actually creates a new instance:

~~~java
CounterState::new
~~~

And keep state scoped to what the framework passes to callbacks:

~~~java
(state, value, downstream) -> {
    state.count++;
    return true;
}
~~~

Adding `synchronized` around `state.count++` **is not a valid fix for a shared initializer**, because the state design itself is no longer independent and the combiner still does not know partition boundaries. Fix the **state ownership contract**, rather than masking a race with a lock.

## 14. Combiner Must Merge Properly and Not Assume Merge Order

A valid combiner must match the semantics of the data being merged.

For example, with counts:

~~~java
(left, right) -> {
    left.count += right.count;
    return left;
}
~~~

Mathematically, count addition is associative. However, for concatenation or order-dependent merging, carefully check **encounter order** and the merge order permitted by the algorithm.

### 14.1. Do Not Use Subtraction as an Accumulation Combiner

~~~java
// Wrong for merging sums:
(left, right) -> {
    left.sum -= right.sum;
    return left;
}
~~~

Subtraction is not associative: `(a - b) - c` can differ from `a - (b - c)`. Splitting the source differently can change the result.

### 14.2. Do Not Discard One Partition's Data

~~~java
// Wrong if both partitions hold data that must be kept:
(left, right) -> left
~~~

If `right` holds accumulated elements, returning `left` without merging **loses data**. It is only valid for special-purpose algorithms whose contract proves the right state is unneeded.

### 14.3. Empty Partitions Must Also Be Valid

A fresh state from the initializer must represent **no elements received yet**. When merged with an empty state, the result must be observationally equivalent to the non-empty state:

~~~text
combine(empty, A) ≡ A
combine(A, empty) ≡ A
~~~

The `≡` symbol means equivalent in business result, not requiring the same object reference.

### 14.4. Do Not Depend on Combiner Being Called Exactly Once

With three partitions `A`, `B`, and `C`, merging may proceed according to different tree shapes. If the algorithm only works for one fixed grouping, it **does not satisfy parallelization requirements**.

When order-dependent results are needed, you must prove the merge preserves order and boundary information properly. Never use an external counter to assign "first partition, second partition...".

## 15. Hard Problem: Running Sums Across Partition Boundaries

Suppose we want to produce running sums:

~~~text
Input:  [1, 2, 3, 4]
Output: [1, 3, 6, 10]
~~~

If the source is split into:

~~~text
Left segment:  [1, 2] → [1, 3], state.sum = 3
Right segment: [3, 4] → [3, 7], state.sum = 7
~~~

The correct result for the right segment across the full source must be `[6, 10]`, because every value needs **offset 3** from the left segment added. If the right branch already called `push` with `[3,7]`, a combiner that merely adds `3+7` at the end **cannot retroactively fix already-emitted elements**.

This is why you should not write a "parallel scan" by attaching a sum combiner while ignoring output semantics.

If you have not implemented a true parallel scan strategy (such as computing per-block sums, computing offsets, and applying them to block results), use a sequential Gatherer or an appropriate built-in:

~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<Integer> prefixSums = List.of(1, 2, 3, 4)
    .stream()
    .gather(Gatherers.scan(
        () -> 0,
        Integer::sum
    ))
    .toList();

System.out.println(prefixSums); // [1, 3, 6, 10]
~~~

`Gatherers.scan` is a standard option for ordered prefix accumulation. The example uses small numbers so overflow is not considered; for large data, choose `long` and appropriate arithmetic rules.

## 16. Partition State Differs from Business Windows

A common design mistake is wanting "a batch every 100 records" and treating **each parallel partition** as a 100-record batch.

This is wrong because:

- The framework may split the source into partitions of varying sizes.
- A partition may contain fewer or more than 100 elements.
- A short-circuiting operation may cause some parts never to be traversed.
- Splitting depends on the `Spliterator`, source characteristics, and scheduling.

If the business requirement needs **windows of size 100 in encounter order**, use an algorithm that defines **window boundaries from the data and order**, such as:

~~~java
List<List<Integer>> batches = java.util.stream.IntStream
    .range(0, 7)
    .boxed()
    .gather(java.util.stream.Gatherers.windowFixed(3))
    .toList();

System.out.println(batches);
// [[0, 1, 2], [3, 4, 5], [6]]
~~~

Here, window size `3` is a business rule, **not** the number of elements that happen to land in an internal partition.

## 17. Do Not Use ThreadLocal to Simulate Gatherer State

The following pattern often stems from assuming "each thread needs a counter":

~~~java
ThreadLocal<long[]> counter =
    ThreadLocal.withInitial(() -> new long[1]);
~~~

Even if each thread has its own array, it is still **not identical to a processing partition**:

1. One thread may execute multiple tasks/partitions.
2. A partition's state may be handed off to combining phases.
3. `ThreadLocal` does not provide a proper combiner for accumulated values.
4. In long-lived thread pools, forgetting to clear state can retain data/resources for too long.

Only use `ThreadLocal` for requirements with **genuinely thread-bound semantics**, not as a replacement for a Gatherer's `initializer`. For Stream problems, state should be created, passed, and merged by the framework according to the Gatherer contract.

## 18. Avoid Leaking Mutable State Downstream

Suppose state holds a list:

~~~java
class State {
    final java.util.ArrayList<String> values =
        new java.util.ArrayList<>();
}
~~~

The finisher below can **leak the list owned by state**:

~~~java
// Not recommended if callers need an independent, unmodifiable result:
// (state, downstream) -> downstream.push(state.values);
~~~

A safer variant:

~~~java
(state, downstream) -> {
    if (!downstream.isRejecting()) {
        downstream.push(List.copyOf(state.values));
    }
}
~~~

`List.copyOf` creates an unmodifiable list and **does not accept null elements**. If state may contain nulls, choose a copying approach consistent with your null policy, such as a new `ArrayList` wrapped as unmodifiable.

The key point is **never passing live internal state out for external code to keep mutating**. A snapshot prevents user-visible results from changing due to later internal processing, while making data ownership clear.

## 19. Memory and Resource Management When State Is Large

Partition state makes many algorithms easy to express, but it is **not free**.

| State design | Cost/Risk | Recommendation |
|---|---|---|
| A few counters/sums | Lightweight, easy to merge | Suitable for aggregation problems |
| `HashMap` by key | Memory grows with each partition's key count | Bound cardinality and merge properly |
| `ArrayList` storing all elements | Memory can approach source size multiplied across intermediate containers | Only store when truly necessary |
| Window buffer | Must compute window bounds and handle remainder | Use a window algorithm with clear invariants |
| State holding I/O resources | Hard to manage closing timing and exceptions | Separate responsibilities and define lifecycle |

### 19.1. Many Partitions Can Create Many Containers

With a parallel Gatherer, the framework may allocate many states before merging them. If each state pre-allocates a huge array or opens a connection, total resource consumption can surge even when the source element count is modest.

Prefer **small states**, allocate on demand when appropriate, and avoid assuming there is only a single initializer call.

### 19.2. Finisher Does Not Replace All Resource Management

`finisher` is the Gatherer's completion hook; if the source is `Files.lines(...)`, **closing the source** remains the responsibility of whoever owns the Stream:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("events.txt");

try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    // lines.gather(...).collect(...)
}
~~~

Terminal operations do not automatically close `Files.lines`. Do not expect a Gatherer's `finisher` to replace `try-with-resources` for a file source.

### 19.3. Do Not Store Downstream to Emit Results Later

A Gatherer **must not retain a `Downstream` reference** to call later from another thread or an asynchronous callback after the `integrator`/`finisher` invocation has returned.

Example of a flawed design:

~~~java
// Lifetime violation:
// savedDownstream = downstream;
// executor.submit(() -> savedDownstream.push(value));
~~~

If you want to integrate asynchronous processing, design a model with dedicated dataflow and lifecycle management. A Gatherer's `Downstream` is not a message channel that can be retained arbitrarily.

## 20. Checking Empty Data, Nulls, Overflow, and Early Termination

### 20.1. Empty Source

Define result semantics clearly:

- A run-compressing Gatherer (`consecutiveRuns`) returns **no runs**.
- A final statistics Gatherer (`summarizeNonnegative`) may emit **one Summary(0,0,0)**.
- A final frequency Gatherer may emit **one empty Map**.

These are three **different** policies, all potentially reasonable. The Gatherer author must choose the result semantics matching business requirements and test against an empty source.

### 20.2. Nulls

A `Stream` may contain nulls in some cases, yet callbacks may not handle them. For example, `consecutiveRuns` uses `Objects.equals` to group nulls safely, whereas `summarizeNonnegative` explicitly rejects nulls because there is no valid numeric value.

If results are copied via `List.copyOf` or `Map.copyOf`, remember those APIs **reject null elements/keys/values**. Do not let your null policy surface only as an obscure exception in the finisher.

### 20.3. Overflow

Even though `long` is larger than `int`, a `count` or `sum` can still overflow. `Math.addExact` is an option that **fails on overflow**, appropriate when the goal is to detect out-of-range data. For precision beyond `long`, consider `BigInteger`.

In parallel execution, grouping order may change, so you must also consider **associativity of the operation and overflow policy**. If using `double`, addition order can introduce rounding differences even though mathematical addition is associative.

### 20.4. Short-Circuiting

If downstream uses `limit(1)` or `findFirst()`, some source elements may not need to be processed. `Downstream.push` returns `false` when downstream wants no more elements; `isRejecting()` is only a helper check.

Do not write tests asserting that the integrator is always invoked exactly as many times as the source element count in every pipeline; under short-circuiting, that assumption no longer holds.

## 21. Evaluating Parallelism and Order Correctness

Simply having a combiner does not mean a Gatherer always runs faster.

Deciding factors:

1. **Does the source split well?** Does `Spliterator.trySplit` produce independent, balanced, non-overlapping splits?
2. **Is the per-element cost high enough?** Simple numeric addition can be cheaper than parallel overhead.
3. **Is the combiner expensive?** Merging two large `HashMap`s incurs heavy hashing and allocation work.
4. **Is encounter order required?** Algorithms depending on adjacency or running totals may not allow arbitrary merging.
5. **Is the state heavy?** A large number of partitions can multiply intermediate memory usage.
6. **Is there short-circuiting?** Early stopping can affect total work and which branch results are kept.

`Gatherer.of(...)` with a valid combiner **permits** parallelization; it does not force the runtime to split the source. Conversely, `ofSequential(...)` explicitly states that the algorithm requires sequential accumulation to preserve semantics.

**Rule of thumb:** verify **equivalent sequential and parallel results** first, and only then measure timing with a proper tool like JMH. Do not use `System.out.println` inside an integrator to benchmark performance, as shared console I/O skews results.

## 22. Comparing Gatherer with Collector and Spliterator

| Component | Primary Role | Relation to Partition State |
|---|---|---|
| `Spliterator` | Supplies and splits the source | Determines how input data can be partitioned |
| `Gatherer` | Stateful **intermediate** transformation | Has initializer/integrator/combiner/finisher, emits 0..n outputs |
| `Collector` | **Terminal reduction** into one result | Has supplier/accumulator/combiner/finisher, accumulates into final result |
| `reduce` | Value reduction via associative combination | Usually not intended for mutating a shared mutable identity |
| `map`/`filter` | Element transformation/filtering | Typically requires no state from prior elements |

### 22.1. When Only a Final Report Is Needed, Collector Is Usually Clearer

Example counting by keyword:

~~~java
Map<String, Long> counts = words.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        word -> word,
        java.util.stream.Collectors.counting()
    ));
~~~

If the goal is solely the final Map, prefer a collector. A word-counting Gatherer like in section 12 has educational value for demonstrating **partition state and combiners**, though it is not necessarily the most concise choice in production code.

### 22.2. When Emitting Intermediate Pipeline Results, Gatherer Shines

Example compressing consecutive runs:

~~~java
List<Run<String>> longRuns = words.stream()
    .gather(consecutiveRuns())
    .filter(run -> run.count() >= 2)
    .toList();
~~~

Here the Gatherer's output flows directly into `filter`. A standard terminal collector cannot directly replace this intermediate step without restructuring the pipeline.

## 23. Common Mistakes When Managing Partition-Level State

| Mistake | Consequence | Fix |
|---|---|---|
| `initializer` returns a shared mutable object | Race conditions, wrong merges, state leaks across runs | Return a new state from `State::new` |
| Using `ThreadLocal` instead of partition state | Confuses threads with partitions, hard to merge | Let the framework manage state via initializer |
| `combiner` returns `left` without merging `right` | Data loss | Merge completely before returning |
| `combiner` uses a non-associative operation | Results may change under different splits | Prove associativity or use sequential |
| Using `of(...)` for a step-by-step prefix scan | Cannot adjust already-emitted outputs in the right partition | Use `ofSequential` or a proper parallel scan algorithm |
| Treating a partition as a "100-element batch" | Batch size depends on runtime splitting | Use explicit business windows |
| `finisher` returns a mutable container directly | Callers may mutate or observe internal state | Return a copy/snapshot with clear policy |
| Saving `Downstream` to emit from another thread | Violates API lifetime | Use downstream only within the corresponding callback |
| Ignoring `push` returning `false` | Wasted work or violation of stop request | Propagate stop signal appropriately |
| Allocating huge state in every initializer | Memory spikes when many partitions are created | Keep state small, allocate controllably |
| Assuming combiner runs exactly once | Breaks when runtime splits/merges differently | Design correctly for all valid split trees |
| Assuming `parallel()` is always faster | High split/merge overhead | Measure with representative benchmarks |
| Using `static long count` for statistics | Results bleed across evaluations | Keep count in state and merge via combiner |
| Not handling empty sources | Finisher may emit semantically wrong output | Clearly define zero-output vs empty result |
| Not specifying null/overflow handling | Wrong reports or late errors | Validate inputs and choose arithmetic policy |

## 24. Practice 1: Verify Results Across Multiple Runs

**Requirement:** use `summarizeNonnegative()` from section 10 to verify that each Stream evaluation has its own state and partitions do not share state across two calls.

Place the following snippet in `main` of `PartitionStateDemo`:

~~~java
List<Integer> first = List.of(2, 4, 6);
List<Integer> second = List.of(1, 3);

List<Summary> firstReport = first.parallelStream()
    .gather(summarizeNonnegative())
    .toList();

List<Summary> secondReport = second.parallelStream()
    .gather(summarizeNonnegative())
    .toList();

System.out.println(firstReport);
// [Summary[count=3, sum=12, evenCount=3]]

System.out.println(secondReport);
// [Summary[count=2, sum=4, evenCount=0]]
~~~

If state were stored in a static variable and reused, the second report could inherit counts/sums from the first run. With a contract-compliant `State::new`, each evaluation gets an independent container.

**Do not write tests checking how many times the initializer was called using a global variable.** Partition count is an execution detail; what needs testing is the business result.

## 25. Practice 2: Write a Gatherer That Finds the Maximum Value

**Prompt:** create a Gatherer accepting non-null `Integer` elements and emitting **one maximum value** when the source finishes; if the source is empty, emit no output. Allow parallel execution via private state and a contract-compliant combiner.

### Reference Solution (Java 24+)

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class MaxGathererPractice {

    static Gatherer<Integer, ?, Integer> maxValue() {
        class State {
            boolean present;
            int maximum;
        }

        return Gatherer.<Integer, State, Integer>of(
            State::new,

            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    Objects.requireNonNull(value, "value");
                    if (!state.present) {
                        state.present = true;
                        state.maximum = value;
                    } else {
                        state.maximum = Math.max(
                            state.maximum, value
                        );
                    }
                    return true;
                }
            ),

            (left, right) -> {
                if (!right.present) {
                    return left;
                }
                if (!left.present) {
                    return right;
                }
                left.maximum = Math.max(
                    left.maximum, right.maximum
                );
                return left;
            },

            (state, downstream) -> {
                if (state.present && !downstream.isRejecting()) {
                    downstream.push(state.maximum);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(4, 9, 2, 7, 1);

        List<Integer> result = values.parallelStream()
            .gather(maxValue())
            .toList();

        System.out.println(result); // [9]

        List<Integer> empty = Stream.<Integer>empty()
            .gather(maxValue())
            .toList();

        System.out.println(empty); // []
    }
}
~~~

### Why Does the Combiner Handle Empty States First?

A fresh state from `initializer` has `present = false`. If you called `Math.max(left.maximum, right.maximum)` immediately, the default value `0` could corrupt the result when the source contains all negative numbers.

For example, `[-10, -4, -8]` must yield `-4`, not `0`. The `present` flag ensures:

- When one side is empty, pick the state of the side with data.
- When both have data, take the max of the two values.
- When both are empty, the result remains empty.
- No assumption is made that input values are non-negative.

This is an important **state invariant**: `maximum` is only meaningful when `present == true`.

## 26. Practice 3: Analyze a Broken Combiner

A developer writes an element-counting Gatherer with a `long[]` state of size 1:

~~~java
// Intentionally broken example:
Gatherer<Integer, ?, Long> counter = Gatherer.of(
    () -> new long[1],
    Gatherer.Integrator.ofGreedy(
        (state, value, downstream) -> {
            state[0]++;
            return true;
        }
    ),
    (left, right) -> left,
    (state, downstream) -> downstream.push(state[0])
);
~~~

### Questions

1. Does `initializer` create independent state?
2. Does `integrator` count within each state?
3. Does `combiner` preserve partition counts?
4. Why might a sequential pipeline produce the right answer while a parallel one produces the wrong answer?
5. Fix the combiner and explain the condition for addition to be valid.

### Solution

~~~java
(left, right) -> {
    left[0] = Math.addExact(left[0], right[0]);
    return left;
}
~~~

The example's `initializer` and `integrator` are on the right track. **The bug is in the combiner**: returning `left` drops `right`'s count. In a sequential run, the combiner may not be invoked so the bug stays hidden; when the source is split and states are merged, the bug becomes obvious.

To guard against `long` overflow, use `Math.addExact` in both accumulator and combiner if the business contract requires failing on out-of-range totals. You cannot test only on a small sequential Stream and conclude the combiner is always right.

## 27. Testing Should Be Contract-Based, Not Schedule-Based

A stateful Gatherer should be tested across at least these dimensions:

| Test Case | Meaning |
|---|---|
| Empty stream | Zero-output or empty aggregate per policy |
| Single element | Neither skipped nor double-counted |
| Multiple consecutively repeated elements | State maintained properly across inputs |
| Multiple groups with identical values across imaginary boundaries | Runs emitted accurately |
| Multiple consecutive evaluations | No state leakage across runs |
| Sequential and parallel | Equivalent results for Gatherers with valid combiners |
| All negative elements (max) | Does not use 0 as a bogus sentinel |
| Null values | Errors or handled per policy |
| Oversized sums | Reports overflow or uses appropriate numeric type |
| Downstream `limit`/`findFirst` | Callbacks do not push after downstream rejects |
| Ordered and unordered sources | Does not assume order on unordered sources |
| Map with keys appearing in both partitions | Combiner sums counts instead of overwriting |
| Large volume | Does not retain excessive state or leak resources |

For split correctness, **do not try to force the framework to create exactly two partitions** and call that complete testing. You can **unit-test the state-merge function directly** using contract-valid constructed states; compare results for `(A⊕B)⊕C` and `A⊕(B⊕C)`, including empty states.

Testing combiner logic directly catches bugs that a small real pipeline might never trigger.

## 28. Self-Check Questions

1. What does `Gatherer<T, A, R>` mean? — **Input T, state A, output R**.
2. Does a parallel Gatherer evaluation always have exactly one state? — **No**; there may be multiple local states that get merged.
3. What should `initializer` return when state is mutable? — **A new instance** on each invocation.
4. What does `integrator` receive? — **State, input element, Downstream**.
5. What does `combiner` receive? — **Two accumulated states**, producing a combined state.
6. What is `finisher` used for? — **Optionally emitting final outputs upon completion**.
7. What does `ofSequential` express? — **The Gatherer is not split/merged as a parallelizable Gatherer**.
8. Does `of` with a combiner automatically guarantee faster execution? — **No**, it only enables parallelization.
9. Why should `ThreadLocal` not replace partition state? — **Threads are not identical to partitions**.
10. What does `Downstream.push` returning `false` mean? — **Downstream no longer accepts further output**.
11. May `Integrator.Greedy` proactively stop arbitrarily? — **No**, it only reflects stop requests from downstream.
12. Why does simple run-length encoding use `ofSequential`? — **Groups can span across partition boundaries**.
13. Why can't a running scan simply add a sum-merging combiner? — **Already-emitted outputs in the right branch need the offset from the left branch**.
14. If `combiner` receives two Maps with shared keys, can it use `putAll`? — **No**, if counts must be summed.
15. When must state be copied in the finisher? — **When you must avoid exposing a mutable container or need a snapshot**.
16. Should `Downstream` be stored to push data from another thread after the callback? — **No**, that violates API lifetime.
17. Is the partition count a business batch rule? — **No**, it is decided by the framework.
18. Can a `Collector` replace a Gatherer to aggregate a final Map? — **Yes**, often more concisely and clearly.
19. From which JDK are standard Stream Gatherers available? — **Java 24**.
20. What is the single most important condition before allowing a parallel Gatherer? — **The combiner and emission strategy must preserve semantics across all valid splits**.

## 29. Stateful Gatherer Design Checklist

Before shipping a custom Gatherer in a project, ask yourself:

- [ ] Are **input/output contracts** clear, including empty sources?
- [ ] Does **State A** hold only what must be retained, without being artificially bound to threads?
- [ ] Does `initializer` create independent state when needed?
- [ ] Does `integrator` maintain invariants after each element?
- [ ] When emitting output, does it respect `Downstream.push` and short-circuiting?
- [ ] Is `finisher` truly needed? If so, does it check downstream rejection?
- [ ] Is the **combiner proven correct** without losing data?
- [ ] Have boundary items between partitions been considered, especially for order-dependent algorithms?
- [ ] Without a valid combiner, did you use `ofSequential`?
- [ ] Are State and Downstream **never saved, leaked, or used after callbacks**?
- [ ] Does the final result avoid leaking mutable Maps/Lists if the API disallows mutation?
- [ ] Are null, overflow, and exception policies clear?
- [ ] Are I/O sources managed with `try-with-resources` by the owner?
- [ ] Have you tested sequential, parallel, empty sources, and consecutive runs?
- [ ] Have you benchmarked before claiming parallel is faster?
- [ ] Do the build and runtime environments actually support **Java 24+**?

## 30. Conclusion

**Private state per processing partition** is the foundation for implementing stateful Gatherers that remain parallelizable. `initializer` creates independent state; `integrator` updates state from assigned elements; `combiner` merges processed states; `finisher` produces final output. A Gatherer can run in parallel **only when state merging and output emission preserve exact semantics**.

Keep these three design choices in mind:

1. If the operation depends on **global order** or adjacent elements, start with **`Gatherer.ofSequential`**.
2. If state can be merged with a **valid associative operation, a proper empty state**, and output is emitted at the right time, you can use **`Gatherer.of` with a combiner**.
3. If only **one final aggregated result** is needed, evaluate whether a standard `Collector` is simpler than a custom Gatherer.

Do not share mutable state across partitions, do not equate partitions with threads, do not leak `Downstream` outside callbacks, and do not use `parallel()` as a default optimization. Mastering these principles helps you build stateful Stream transformations that are **contract-compliant, testable, well-managed in resources, and scalable**.

### Java 24 API References

- [Java SE 24 — Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- [Java SE 24 — Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html)
- [Java SE 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [Oracle — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
