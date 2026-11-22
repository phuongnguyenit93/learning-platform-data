# Creating Sequential Gatherers with Gatherer.ofSequential

In the Java Stream API, `filter`, `map`, and `flatMap` solve many independent element-transformation problems. However, some tasks require **remembering state across elements**: computing a running total, assigning sequence numbers, grouping consecutive items, emitting a report when data ends, or stopping upon a condition. Instead of placing mutable variables outside the pipeline and using `peek` or `forEach`, starting in **Java 24** you can build a custom *Stream Gatherer* using `Gatherer.ofSequential`.

`Gatherer.ofSequential` is suitable when the algorithm must run its integration step (*integration*) sequentially, with **private state per pipeline execution**. A Gatherer does not only map each `T` to a single `R`: for each input element, it can **emit zero, one, or multiple outputs**, and can emit additional data during the completion step. It is an extension tool for pipelines involving sequential processing that are awkward to express with `map` or `filter` alone.

This lesson belongs to the **Building Custom Gatherers** chapter of the **JAVA_STREAM_API** module. We will learn how to design initializer, integrator, downstream, and finisher; check early-termination contracts; understand limitations with parallel sources; and write self-contained Java 24 examples. The topic connects to lazy pipelines, `reduce`, `collect`, grouping, `Spliterator`, state, and performance, with the main focus on **building semantically sound sequential Gatherers**.

## 1. JDK Version and Purpose of Gatherer

The core types live in the package:

```java
import java.util.stream.Gatherer;
import java.util.stream.Stream;
```

The intermediate method on Stream has the form:

```java
Stream<R> output = input.gather(gatherer);
```

Stream Gatherers were introduced to Java in earlier preview releases and **became an official API in JDK 24**. Thus, the examples in this lesson use **JDK 24 or later**; they cannot compile directly on JDK 8, 11, 17, or 21. In environments using preview versions, preview-flag rules differ and these JDK 24 examples should not be treated as backward-compatible code.

Simple example of pipeline shape:

```java
List<String> output = Stream.of("A", "B", "C")
        .gather(myGatherer)
        .toList();
```

Here `myGatherer` is an already-defined Gatherer. `gather(...)` remains an **intermediate operation**: it constructs the pipeline without necessarily traversing the source yet. `toList()` is the terminal operation that triggers processing.

### 1.1. When Is a Gatherer Needed Instead of Built-in APIs?

| Problem | Typically Suitable Tool |
|---|---|
| Filter each element independently | `filter` |
| Transform each element into one value | `map` |
| Each element expands into a sub-Stream | `flatMap` |
| Sum/count/aggregate into one final result | `reduce`, `collect` |
| Group by key regardless of consecutive positions | `groupingBy` |
| Compute **running total after each element** | Stateful Gatherer or dedicated algorithm |
| Split a sequence into **consecutive batches** and emit each batch | Gatherer, or built-in `Gatherers.windowFixed` if suitable |
| Emit a summary record at completion | Gatherer with finisher |
| Coordinate a novel transformation with state and custom emission rules | Custom Gatherer |

Do not choose a Gatherer just for new syntax: if `filter`, `map`, `limit`, or a built-in collector expresses the problem clearly, prefer the simpler tool.

## 2. The Gatherer<T, A, R> Model

The generic interface is `Gatherer<T, A, R>`:

- **`T`**: input element type.
- **`A`**: intermediate state type of the Gatherer; may be a mutable object or `Void` if no state is needed.
- **`R`**: output element type received by downstream.

Conceptual model:

```text
Stream<T>
    |
    v
initializer -> new state A
    |
    +----> integrator(A, T, downstream)
                 |
          update state
                 |
          push(0..n elements R)
                 |
       continue integrating?
                 |
            [loop over T]
                 |
       finisher(A, downstream)
                 |
           push remainder
                 |
              Stream<R>
```

Components to understand:

| Component | Responsibility | Characteristic in `ofSequential` |
|---|---|---|
| **Initializer** | Initializes `A` for the integration pass | Can supply `Supplier<A>` or use the stateless overload |
| **Integrator** | Receives state, element `T`, and downstream; may emit `R` | Executed under the sequential integration model |
| **Downstream** | Receives `R` elements from `push` | May reject further outputs when the pipeline stops early |
| **Finisher** | Finalizes state and may emit more `R` | Optional; useful for flushing an incomplete final group |
| **Combiner** | Combines two states in parallel integration | `ofSequential` does not require you to write a parallel merge |

A distinctive feature of a Gatherer is that **`integrator` returns a `boolean`** indicating whether it should keep receiving input elements. This differs from `Consumer<T>` in `forEach`, which returns no stop signal.

## 3. Commonly Used ofSequential Overloads

Three common practical variants:

### 3.1. No State and No Finisher

```java
Gatherer<T, Void, R> gatherer =
        Gatherer.ofSequential(integrator);
```

When no state needs to be retained, `A` is `Void` and the integrator can ignore the state parameter. Useful for simple mapping/filtering experiments with the API, though `map`/`filter` are usually more concise.

### 3.2. Stateful, No Finisher Needed

```java
Gatherer<T, A, R> gatherer =
        Gatherer.ofSequential(
                initializer,
                integrator);
```

This is the choice for running totals or sequential numbering: each element is integrated, output is emitted immediately, and no leftover data remains to flush when the source ends.

### 3.3. Stateful with Finisher

```java
Gatherer<T, A, R> gatherer =
        Gatherer.ofSequential(
                initializer,
                integrator,
                finisher);
```

Use this when accumulating an **incomplete block** and you only know to emit that block once input ends. A finisher does not replace a terminal operation: it is the completion stage of the Gatherer inside the pipeline.

**Syntax reading note:** `initializer` is typically a `Supplier<A>`; `integrator` is `Gatherer.Integrator<A,T,R>`; `finisher` accepts `(state, downstream)` and performs remaining emission commands. Complete examples in sections 5 and 6 show how types are inferred from the `Gatherer<T,A,R>` declaration.

## 4. Downstream.push and Early Termination Signals

Inside the integrator, `downstream.push(value)` attempts to emit an output element and returns a `boolean`:

- `true`: downstream can still accept output; the integrator may continue.
- `false`: downstream has rejected further output; the integrator should propagate the stop signal when appropriate.

For example, a Gatherer transforming positive numbers `n` into `n * 2` can be written:

```java
import java.util.stream.Gatherer;

Gatherer<Integer, Void, Integer> doublePositive =
        Gatherer.ofSequential((state, value, downstream) -> {
            if (value <= 0) {
                return true; // Skip this input element, keep reading.
            }
            return downstream.push(value * 2);
        });
```

This snippet **holds no state** and only emits doubled positive numbers. Sample input:

```java
List<Integer> values = Stream.of(-1, 2, 0, 3)
        .gather(doublePositive)
        .toList();

System.out.println(values); // [4, 6]
```

When downstream rejects due to `limit` or another short-circuiting operation, returning the result of `push` stops the Gatherer from integrating unnecessarily. Do not unconditionally return `true` after `push` reports no more output wanted, as that can cause the source to keep being traversed even after enough results have been collected.

### 4.1. false Does Not Mean "Skip Element"

This is a critical distinction:

```java
if (!isValid(value)) {
    return true;   // Do not push, yet allow inspecting subsequent elements.
}
```

Returning `false` tells the Gatherer **to stop integrating more input elements**; it does not simply mean "filter out the current element". If filtering logic returns `false` to skip a value, the pipeline terminates prematurely by mistake.

### 4.2. Do Not Assume Short-Circuiting Sees a Full Cycle

If downstream finishes early, such as with `limit(2)`, integration may not see all source elements. Therefore, **a Gatherer's state only reflects the data actually integrated**, not necessarily the entire original dataset. Do not use a finisher or internal counter inside a Gatherer to claim all elements were processed when a terminal operation can short-circuit.

## 5. Complete Java 24 Example: Running Total

Suppose a payment system needs to print **the cumulative processed amount after each transaction**. `reduce` or `sum` produces only one final result, whereas we need one output for **each** transaction, depending on the sum of preceding transactions.

We design the Gatherer:

- Accepts `Long` as the transaction amount; negative values can represent adjustments/refunds in the example.
- `RunningState` has `count` and `sumCents`.
- On each integration, add the amount and increment count, then emit `RunningTotal(index, sumCents)`.
- Guard against `long` overflow with `Math.addExact`.
- No finisher is needed since a corresponding result is emitted after each element.

Save the following as `SequentialGathererDemo.java` and run with **JDK 24+**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class SequentialGathererDemo {

    static final class RunningState {
        long count;
        long sumCents;
    }

    static final class RunningTotal {
        final long index;
        final long totalCents;

        RunningTotal(long index, long totalCents) {
            this.index = index;
            this.totalCents = totalCents;
        }

        @Override
        public String toString() {
            return "#" + index + "=" + totalCents;
        }
    }

    static Gatherer<Long, RunningState, RunningTotal>
            runningTotals() {
        return Gatherer.ofSequential(
                RunningState::new, // initializer
                (state, amount, downstream) -> {
                    state.count = Math.addExact(state.count, 1L);
                    state.sumCents = Math.addExact(
                            state.sumCents, amount);

                    // Return push's boolean to propagate stop signals.
                    return downstream.push(new RunningTotal(
                            state.count, state.sumCents));
                });
    }

    public static void main(String[] args) {
        List<Long> transactions = Arrays.asList(
                5_000L, 3_000L, -2_000L, 7_000L);

        List<RunningTotal> totals = transactions.stream()
                .gather(runningTotals())
                .toList();

        System.out.println(totals);
        // [#1=5000, #2=8000, #3=6000, #4=13000]

        // Each collect runs integration with its own private state.
        List<RunningTotal> again = transactions.stream()
                .gather(runningTotals())
                .toList();
        System.out.println(again);
        // [#1=5000, #2=8000, #3=6000, #4=13000]

        // Empty source: no state is pushed.
        List<RunningTotal> empty = Stream.<Long>empty()
                .gather(runningTotals())
                .toList();
        System.out.println(empty); // []

        // Preserves List order in sequential processing.
        transactions.stream()
                .gather(runningTotals())
                .forEachOrdered(System.out::println);
        // #1=5000
        // #2=8000
        // #3=6000
        // #4=13000
    }
}
```

### 5.1. Execution Walkthrough

| Transaction | `state.count` after | `state.sumCents` after | Output |
|---:|---:|---:|---|
| `5000` | 1 | 5000 | `#1=5000` |
| `3000` | 2 | 8000 | `#2=8000` |
| `-2000` | 3 | 6000 | `#3=6000` |
| `7000` | 4 | 13000 | `#4=13000` |

A running total differs from a final sum in that it **emits multiple results**, each being a snapshot of state after an integration step. If you only need `13000`, `mapToLong(...).sum()` is simpler.

### 5.2. Why Must the Initializer Create a New State?

`RunningState::new` allocates a new `RunningState` for every Gatherer invocation needing its own state. Never create a `static RunningState shared` for all pipelines to share; doing so causes the second run to continue the first run's count and can cause data races under parallel execution.

### 5.3. Why Not Hold RunningState in the Result?

`RunningTotal` holds **two captured `long` values**, not a reference to the mutable `RunningState` object. If you pushed the state object itself downstream and kept mutating it, every output element could point to the same changing state, preventing the result list from reflecting accurate cumulative checkpoints.

## 6. Complete Java 24 Example: Splitting Elements into Fixed Batches

A message-batching application needs to split a list into consecutive chunks, each containing at most `batchSize` elements. When a chunk fills up, the integrator emits a `List<String>`. If the source ends with a partial chunk remaining, the **finisher** must emit the final chunk.

Example with 5 elements, batch size 2:

```text
Input:   A B C D E
Batch 1: [A, B]
Batch 2: [C, D]
Batch 3: [E]    <- emitted by finisher
```

The following code runs standalone on JDK 24+:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class SequentialBatchGathererDemo {

    static Gatherer<String, List<String>, List<String>>
            batchesOf(int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize must be greater than 0");
        }

        return Gatherer.ofSequential(
                ArrayList::new,
                (state, value, downstream) -> {
                    Objects.requireNonNull(value, "value");
                    state.add(value);

                    if (state.size() == batchSize) {
                        // Independent snapshot: do not push mutable state out.
                        List<String> batch =
                                Collections.unmodifiableList(
                                        new ArrayList<>(state));
                        state.clear();
                        return downstream.push(batch);
                    }
                    return true; // Batch not full yet, keep accepting input.
                },
                (state, downstream) -> {
                    if (!state.isEmpty()) {
                        downstream.push(Collections.unmodifiableList(
                                new ArrayList<>(state)));
                    }
                });
    }

    public static void main(String[] args) {
        List<List<String>> groups = Stream.of("A", "B", "C", "D", "E")
                .gather(batchesOf(2))
                .toList();

        System.out.println(groups);
        // [[A, B], [C, D], [E]]

        List<List<String>> exact = Stream.of("A", "B", "C", "D")
                .gather(batchesOf(2))
                .toList();
        System.out.println(exact); // [[A, B], [C, D]]

        List<List<String>> none = Stream.<String>empty()
                .gather(batchesOf(2))
                .toList();
        System.out.println(none); // []

        try {
            batchesOf(0);
            throw new AssertionError("Must reject batchSize=0");
        } catch (IllegalArgumentException expected) {
            System.out.println("Rejected batchSize=0");
        }
    }
}
```

### 6.1. Role of the Three Components

**Initializer:** creates a separate empty list for the integration pass. **Integrator:** adds an element to the list; when full, snapshots the list, clears the buffer to start a new batch, and `push`es the batch downstream. **Finisher:** emits the final batch if elements remain in the buffer.

Emitted batches are wrapped as unmodifiable and copied from state. If you merely did `downstream.push(state)` then `state.clear()`, results across batches could reference a single List mutated after pushing, causing hard-to-spot bugs.

### 6.2. Why Use ofSequential Here?

The notion of "first batch consists of the first two elements of the sequence", "next batch consists of the next two elements" depends on **consecutive positions and input order**. When splitting a source into independent branches, an arbitrary combiner cannot simply concatenate two batch lists and always preserve accurate batch boundaries.

`Gatherer.ofSequential` describes a sequential integration mechanism **without having to design a parallel state-merging operation**. If you only need fixed-size chunking via built-in APIs, Java 24 also provides `Gatherers.windowFixed(batchSize)`; prefer standard APIs when they fit, and use custom gatherers to learn how to add custom business rules.

### 6.3. Finisher and Short-Circuiting

The finisher can be invoked when the source finishes or the Gatherer stage completes. If downstream **no longer accepts output**, calling `push` further produces no accepted elements. Do not design the finisher as a mandatory side-effect step to "guarantee all batches are sent" if the terminal operation can short-circuit, such as `limit(1)`. To guarantee all data is emitted, design the whole pipeline and terminal operation to match the requirement.

## 7. Example of Early Termination by the Integrator Itself

Besides being asked to stop by downstream, a Gatherer can also **proactively stop** upon a condition. For example, emit only the first three positive numbers, skipping non-positive ones:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

class Counter {
    int emitted;
}

Gatherer<Integer, Counter, Integer> firstThreePositive =
        Gatherer.ofSequential(
                Counter::new,
                (state, value, downstream) -> {
                    if (value <= 0) {
                        return true; // Skip, yet continue.
                    }

                    state.emitted++;
                    boolean accepted = downstream.push(value);
                    return accepted && state.emitted < 3;
                });

List<Integer> result = Stream.of(-2, 4, 0, 5, 6, 7)
        .gather(firstThreePositive)
        .toList();

System.out.println(result); // [4, 5, 6]
```

This snippet illustrates inside a class/method where `Counter` and variables are defined; it is not a standalone program like sections 5 and 6. Once the third positive number is emitted, the integrator returns `false` to signal not to integrate further elements.

**Do not confuse:** `false` in the integrator's return value is a **stop signal**, not a predicate return value like `filter`. If you want to skip an element while still searching for subsequent elements, return `true` after not pushing that element.

## 8. Gatherer.ofSequential and Parallel Streams

The name "Sequential" refers to **the Gatherer's integration rule**: elements cannot be arbitrarily split, integrated into state across branches, and merged like a Gatherer with a valid parallel combiner.

Example:

```java
List<Long> input = List.of(5L, 3L, -2L, 7L);

List<SequentialGathererDemo.RunningTotal> totals = input
        .parallelStream()
        .gather(SequentialGathererDemo.runningTotals())
        .toList();
```

With an **encounter-ordered** List source, running-total semantics must consider elements in logical source order. `ofSequential` cannot magically turn a running-total algorithm into parallel addition. The framework must honor the Gatherer's constraints rather than inventing a non-existent state combiner.

Do not infer that **every step in the pipeline** is forced to run on a single thread merely because `ofSequential` is present. Other stages may execute according to Stream's strategy, yet **the speedup potential of the sequential stateful stage is limited**. In particular, thread names or lambda invocation schedules are not part of the application contract.

### 8.1. Why Not Supply an Arbitrary Parallel Combiner?

Suppose branch A processes `[5, 3]` and produces running totals `[5, 8]`; branch B processes `[-2, 7]` and produces `[-2, 5]`. To merge into `[5, 8, 6, 13]`, every result in branch B must be adjusted by branch A's sum.

Merely calling `left.addAll(right)` fails the semantics. Designing a true parallel integration Gatherer may require complex state and merging logic, or a dedicated parallel scan algorithm. For this problem, `ofSequential` preserves correctness without fabricating a broken combiner.

### 8.2. Source Order Still Matters

If the source comes from a collection **without encounter order**, "first element" or "sum after the third element" may not have consistent business meaning across runs. `ofSequential` does not sort data automatically. If chronological order or transaction-ID order is required, you must:

- Choose a source with the appropriate encounter order.
- Or sort explicitly with `sorted(comparator)` before `gather`, using a comparator expressing the business order.
- Avoid `unordered()` when results depend on position or running accumulation.

Sequential integration **does not replace defining input order**.

## 9. Comparing ofSequential with Collector and Other Operations

| Characteristic | `map` / `filter` | `reduce` / `collect` | `Gatherer.ofSequential` |
|---|---|---|---|
| Can maintain local state across elements? | Should not rely on external mutable state | Has accumulation state to form final result | Has private state `A` across integration steps |
| Number of outputs | 0 or 1 output per element depending on op | Usually one final result | 0, 1, or more outputs per step, plus optional completion emissions |
| Early termination support | `limit`, `takeWhile`, etc. | Some terminal operations short-circuit | Integrator can return `false`; downstream can reject |
| Parallel state combining? | Not a dedicated stateful model | Has a contract-compliant combiner | No parallel combiner required in `ofSequential` |
| Suitable use cases | Independent mapping/filtering | Final summary aggregation | Running totals, batching, stateful transformations |

### 9.1. Do Not Replace reduce with a Gatherer When Only a Final Sum Is Needed

```java
long total = Stream.of(5L, 3L, -2L, 7L)
        .mapToLong(Long::longValue)
        .sum();
System.out.println(total); // 13
```

Writing a running-total Gatherer and then calling `reduce((a, b) -> b)` to grab the final sum is an obscure detour. Use a Gatherer when you need **intermediate results** or element-coordination rules with no direct built-in API.

### 9.2. When Computing by Key Rather Than Position

If you only want total revenue per product code, `groupingBy(..., summingLong(...))` or `toMap(..., Long::sum)` expresses it more clearly than a sequential Gatherer iterating and mutating a `HashMap`. Gatherer excels at processing **across consecutive element sequences**, such as emitting a report whenever an end marker appears.

### 9.3. Built-in Gatherers API

Java 24 ships standard gatherers such as `Gatherers.windowFixed`, `windowSliding`, `scan`, and `fold`. Before writing your own, check whether they match your problem. For example, a running total can be expressed with `Gatherers.scan`; building it yourself via `ofSequential` still has educational value when attaching counters, overflow checks, or multi-field output objects.

## 10. State Constraints and Data Safety

### 10.1. Do Not Share State Across Multiple Pipelines

Wrong in principle:

```java
// Avoid a static mutable variable shared across all gather runs:
// static final RunningState SHARED = new RunningState();
// Gatherer.ofSequential(() -> SHARED, integrator);
```

An initializer returning the same object causes:

- A later invocation to continue from the previous invocation's total.
- Two active pipelines to interfere with each other.
- Potential data races if accessed from multiple threads.

Create fresh state via a constructor or clear supplier, and treat a Gatherer as a **processing specification**, not a shared business state holder.

### 10.2. Do Not Mutate the Source During Traversal

The integrator should operate only on the received element and private state, without removing/adding elements in the source `List` during traversal. Stream's *non-interference* rule still applies; being a stateful Gatherer does not permit mutating source data.

### 10.3. Emit Snapshots Instead of Mutable References

For list or summary outputs, if internal state can continue changing, copy it or construct a new result object:

```java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<>(state));
downstream.push(snapshot);
```

Pushing the mutable `state` itself and calling `clear()` on the next step can cause every element in the output List to reflect the same mutated contents.

### 10.4. Handle nulls Intentionally

If `null` is invalid data, use `Objects.requireNonNull(value)` inside the integrator or `filter(Objects::nonNull)` before the Gatherer; if `null` represents a valid delimiter, model that rule explicitly.

Do not rely on `toList()` or `collect` to strip nulls implicitly. A transformation may emit nulls if unguarded, and downstream stages or subsequent operations may react differently.

### 10.5. Arithmetic Safety

Running totals with `long` can overflow. The example uses `Math.addExact` to throw `ArithmeticException` when the sum exceeds `long` range. For precision-sensitive monetary values, consider smallest currency units, `BigDecimal`, or `BigInteger` as required; never assume `double` is exact.

## 11. Memory Cost, Short-Circuiting, and I/O Sources

A sequential Gatherer **is not forced to store the entire input**. For example, the running total only keeps two `long`s, having `O(1)` state space. The batching example holds at most `batchSize` elements, having `O(batchSize)` state space; if downstream `toList()` retains every batch, output memory still scales with retained elements.

| Design | Gathering State Memory | Emission Capability |
|---|---|---|
| Running total | `O(1)` | Emits one result per element |
| Sequential numbering | `O(1)` | Emits one result per element |
| Fixed batching of size `k` | `O(k)` | Emits a list every `k` elements plus final batch |
| Accumulating everything to emit once | `O(n)` | Can emit in finisher, memory-heavy |

### 11.1. Lazy Does Not Mean Stateless

Calling `stream.gather(gatherer)` does not traverse elements yet; when the terminal operation runs, initializer/integrator engage on demand. However, once consumption begins, the Gatherer can hold state across many elements until completion. If multiple pipelines share an external state variable, laziness also makes mutation timing unpredictable.

### 11.2. Short-Circuiting and Partial Source Reading

`limit`, `findFirst`, `anyMatch`, and other short-circuiting terminal operations can stop the pipeline before all inputs are integrated. Hence, do not use integrator or finisher call counts as proof that "all source data was processed". When designing a Gatherer that emits in the finisher, verify its interaction with a rejecting downstream.

### 11.3. I/O-Backed Streams Still Need Closing

`Gatherer.ofSequential` does not close a source opened via `Files.lines` on your behalf:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

// Inside a method where path and gatherer are already defined:
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> result = lines
            .gather(gatherer)
            .toList();
}
```

This snippet illustrates resource scoping; `path` and `gatherer` must be declared in actual code. `toList()` triggers processing but does not replace `try-with-resources`. If the integrator throws an exception, resource closing still executes upon leaving the `try` block.

## 12. Testing a Gatherer.ofSequential

Do not test only with an even-sized list. Build an **edge-case matrix** tailored to semantics:

| Test Case | Running Total | Batching |
|---|---|---|
| Empty source | Empty output list | Empty batch list |
| Single element | One total equal to that element | One batch containing one element |
| Count equal to batch size | N/A | Finisher emits no extra empty batch |
| Count not divisible by batch size | N/A | Final batch holds remaining elements |
| Negative numbers / 0 | Sums accurately per business contract | Still creates batches if valid |
| Null data | Filtered/errors per policy | Filtered/errors per policy |
| Sum exceeds `long` | Throws `ArithmeticException` | N/A |
| Two consecutive pipeline runs | No state carried over from prior run | Fresh batch buffer, no mixed elements |
| Ordered vs unordered source | Ensure business order first | Do not expect ordered batch boundaries on unordered sources |
| Short-circuiting terminal operation | Do not assert full source read | Do not assume all batches were emitted |

### 12.1. Minimal Test for Running Totals

In `SequentialGathererDemo` from section 5, you can add:

```java
List<RunningTotal> result = Stream.of(2L, -2L, 5L)
        .gather(runningTotals())
        .toList();

if (result.size() != 3
        || result.get(0).totalCents != 2L
        || result.get(1).totalCents != 0L
        || result.get(2).totalCents != 5L) {
    throw new AssertionError("Incorrect running total");
}
```

For automated testing, use JUnit to cover the cases in the table, especially empty sources and repeated Gatherer invocations. Correctness of a stateful algorithm is never confirmed by a single happy-path run.

## 13. Common Mistakes When Using ofSequential

| Mistake | Consequence | Fix |
|---|---|---|
| Returning `false` when only wanting to skip one element | Stops integrating remaining elements | Skip `push` yet return `true` |
| Always returning `true` after `downstream.push` rejects | May traverse source needlessly after output is sufficient | Propagate stop signal when appropriate |
| Initializer returns the same static object | State leaks across runs; potential races | Allocate a fresh state object |
| `push(state)` then mutating that state | Outputs may point to a mutated object | Emit a snapshot or new DTO |
| Forgetting finisher in a batching Gatherer | Drops incomplete final batch | Use the overload with finisher |
| Finisher emits an empty batch when data divides evenly | Extra empty batch | Check `!state.isEmpty()` |
| Assuming `ofSequential` sorts data automatically | Accumulates in wrong order | Ensure source encounter order |
| Expecting `parallel()` to speed up a sequential stateful stage | Speedup does not materialize as expected | Benchmark and pick a suitable algorithm |
| Using a Gatherer to replace `sum()` when only total is needed | Unnecessarily complex code | Use primitive `sum` / `reduce` |
| Calling `gather` on JDK 21 | Missing API error | Use JDK 24+ or a compatible strategy |
| Forgetting to close `Files.lines` | File handle leak | `try-with-resources` |
| Using an external counter in `peek` instead of Gatherer state | Side effects, races, may be elided by optimization | Keep local state inside the Gatherer |

## 14. Guided Practice Exercises and Answers

### Exercise 1. Number Each Element Sequentially

**Prompt:** Write a Gatherer taking `String` and emitting `"1:A"`, `"2:B"`, `"3:C"` from Stream `["A", "B", "C"]`. Do not use a counter variable outside the pipeline.

**Reference Solution:**

```java
class State {
    long index;
}

Gatherer<String, State, String> numbered = Gatherer.ofSequential(
        State::new,
        (state, value, downstream) -> {
            state.index++;
            return downstream.push(state.index + ":" + value);
        });

List<String> out = Stream.of("A", "B", "C")
        .gather(numbered)
        .toList();
// [1:A, 2:B, 3:C]
```

These declarations illustrate within a scope that imports `Gatherer`, `List`, and `Stream`.

### Exercise 2. Predict Running Total Output

**Prompt:** Input `[10, -3, 5, 0]`, what total values does the running-total Gatherer in section 5 emit?

**Answer:** `[10, 7, 12, 12]` in exact input order. If you only need the final total `12`, `mapToLong(...).sum()` is simpler.

### Exercise 3. Why Not Return false on Negative Numbers?

**Prompt:** A Gatherer emits only positive numbers from `[-1, 2, 3]`. If the negative-number branch does `return false`, what is the result?

**Answer:** The Gatherer stops immediately at `-1` without checking `2` or `3`, yielding an empty output. To **filter** out negatives, skip `push` and return `true`.

### Exercise 4. Batching When Element Count Is Not Divisible

**Prompt:** `batchesOf(3)` processes `["A", "B", "C", "D", "E"]`. What is the result?

**Answer:** `[[A, B, C], [D, E]]`. The second batch is emitted by the finisher; without a finisher, the last two elements would be lost.

### Exercise 5. Checking Shared State

**Prompt:** A Gatherer is created with `Gatherer.ofSequential(() -> SHARED_STATE, integrator)`, where `SHARED_STATE` is a mutable static field. Can two independent pipelines run safely?

**Answer:** Independence is not guaranteed. Both runs may use the same state and mix counts; if run concurrently, it can cause data races. Use `State::new` to allocate fresh state.

### Exercise 6. Emitting Snapshots

**Prompt:** In a batching Gatherer, the integrator writes `downstream.push(state); state.clear();`. Why can the resulting List be wrong?

**Answer:** `state` is the same mutable List; downstream may hold that reference. Calling `clear` after `push` wipes out the contents of the already-emitted batch. Create `new ArrayList<>(state)` before calling `clear`.

### Exercise 7. Stop After N Matching Elements

**Prompt:** Use a Gatherer to emit only the first two strings with length of at least three characters. What must happen after emitting the second string?

**Answer Guidance:** Use state to count **emitted strings**, skip short strings by returning `true`, and after emitting the second string return `false` (or combine `downstream.push`'s result with whether more emissions are allowed). Do not count skipped strings.

### Exercise 8. ofSequential and Unordered Sources

**Prompt:** Wanting to number transactions chronologically, should you use `HashSet.stream().gather(numbered)`?

**Answer:** No, unless business ordering is already established. `HashSet` does not guarantee encounter order, so numbering may be non-deterministic with respect to timestamps. Choose a sorted List or apply `sorted(Comparator.comparing(Transaction::getTime))` before the Gatherer.

### Exercise 9. Choosing the Simplest API

**Prompt:** You only need to group numbers into lists of size 4 on JDK 24. Must you write `ofSequential` yourself?

**Answer:** Not necessary. `Gatherers.windowFixed(4)` is the standard gatherer for fixed-size windowing. Writing `ofSequential` yourself is worthwhile for learning the API or when custom batch-emission rules are needed that standard APIs do not cover.

## 15. Checklist for Building Sequential Gatherers

Before putting a custom Gatherer into an application:

1. **Is the JDK level appropriate?** `Gatherer` and `Stream.gather` are directly available starting in Java 24+.
2. **Are `T`, `A`, `R` clearly defined?** Input element, state, and output element need not have the same type.
3. **Does the Initializer create fresh state?** Never share mutable state across runs.
4. **Does the Integrator handle 0/1/n outputs?** Distinguish skipping an element from stopping the pipeline.
5. **Is the boolean from `downstream.push` checked?** Do not keep consuming the source needlessly once downstream rejects.
6. **Is a finisher needed?** If buffered data remains at completion, ensure a way to flush it.
7. **Are snapshots of mutable state emitted?** Prevent output from mutating after being pushed.
8. **Does the source have the right business encounter order?** `ofSequential` does not sort automatically.
9. **Are empty, null, overflow, early-stop, and multi-run cases covered?** Test thoroughly.
10. **Is a custom Gatherer truly needed?** Prefer `map`, `filter`, `reduce`, `collect`, or standard `Gatherers` when simpler.
11. **Are performance/resource limits accounted for?** A sequential stateful step can limit speedups from parallel streams.
12. **Are there I/O sources needing closure?** `gather` and terminal operations do not replace `try-with-resources`.

**Conclusion:** `Gatherer.ofSequential` lets you implement **sequential stateful transformations** on Java Streams without having to design a parallel combiner. To write it correctly, clearly separate **the initializer creating fresh state**, **the integrator updating state and pushing outputs**, **the boolean deciding continue vs stop**, and **the finisher emitting leftovers when needed**. When you preserve source order, avoid shared mutable state, emit safe snapshots, and test empty/short-circuit cases, a custom Gatherer becomes a clean and expressive tool for advanced Java Stream pipelines.
