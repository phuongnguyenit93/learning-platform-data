# Processing Remaining Data with finisher

## 1. When the Source Ends Yet the Gatherer State Still Holds Data

In the **JAVA_STREAM_API** module, pipelines of `filter`, `map`, `reduce`, and `collect` enable declarative data processing. However, not every transformation can be solved from a single input element alone. Some operations must **accumulate multiple elements**, such as batching, waiting for a delimiter, or grouping consecutive identical values.

**Stream Gatherer** allows writing a stateful intermediate operation. While receiving inputs, the `integrator` updates state and emits results when conditions are met. When the source ends, state may still hold an **unemitted tail**. The `finisher` resolves precisely that tail.

~~~text
Source:      [A, B, C, D, E, F, G]
Batch size = 3

Integrator:
  [A, B, C]  → emits batch 1
  [D, E, F]  → emits batch 2
  [G]        → still waiting, fewer than 3

Finisher:
  [G]        → emits final batch

Result: [[A, B, C], [D, E, F], [G]]
~~~

If the completion step is omitted, `G` could be lost. Conversely, if the buffer is always emitted upon completion without checking for emptiness, it can produce a **spurious empty batch** when the element count is divisible by the batch size.

The topic **"Processing Remaining Data with finisher"** belongs to the **Building Custom Gatherers** chapter. This lesson explains the mechanism, how to emit leftovers, respecting downstream on early stop, bugs related to mutable state, and limitations under parallel execution.

**Version Requirement:** Stream Gatherers were standardized in **Java 24** (JEP 485), following preview phases in Java 22 and 23. Examples using `Gatherer` and `Stream.gather(...)` in this lesson require **Java 24+**; they do not compile directly on Java 17 or 21. The `public class` examples below can be saved in files matching their class names and run standalone, except short snippets explicitly noted as using components from prior examples.

### Scenarios Requiring a finisher

| Processing Pattern | When does integrator emit? | What does finisher handle? |
| --- | --- | --- |
| Fixed-size batching | When `k` elements are reached | Final batch with fewer than `k` elements |
| Splitting sections by blank line | When encountering a delimiter | Final section without a trailing delimiter |
| Compressing consecutive identical elements | When the value changes | The final consecutive run |
| Aggregation emitted only at end of source | Does not emit while reading | Converts state into final summary result |
| BEGIN/END pair parser | When encountering END | Reports error or handles unclosed record |

The common thread is that **the finisher does not invent new source data**: it only processes what remains in state according to the policy defined by the Gatherer's author.

## 2. Lifecycle and Roles of the Four Components

A `Gatherer<T, A, R>` has these type parameters:

- `T`: input element.
- `A`: accumulated state (*state*) managed by the Gatherer.
- `R`: output element pushed to the subsequent stage.

The four main components:

1. **Initializer** creates an appropriate state for an evaluation pass.
2. **Integrator** receives each element `T`, updates state, and may call `downstream.push(R)`.
3. **Combiner** merges states when the Gatherer supports parallel evaluation.
4. **Finisher** finalizes state and may emit additional `R` elements after no more inputs remain.

~~~text
                      Stream<T>
                          │
                          ▼
                   initializer()
                  creates state A
                          │
                          ▼
                  integrator(A,T)
                    │        │
            updates A   push(R) when ready
                    │        │
                    └────┬───┘
                         │
              input consumption phase ends
                         │
                         ▼
                finisher(A, downstream)
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
     no tail in state          tail remains in state
     emit nothing more         push(R) if accepted
            └────────────┬────────────┘
                         ▼
                Downstream pipeline
                         ▼
                Terminal operation
~~~

This is a **logical model** for a sequential Gatherer when the pipeline is consumed normally. Do not treat callback invocation counts or log ordering as a contract for short-circuiting terminals or optimized runtimes.

### finisher Differs from integrator

`integrator` returns `boolean`: it can decide whether to **continue receiving more inputs** or not. `finisher` is a `BiConsumer` callback, **returns no Boolean**, and cannot be used to read more source data. It can offer 0, 1, or more final results downstream.

### finisher Differs from Collector.finisher

| Property | `Collector.finisher()` | `Gatherer.finisher()` |
| --- | --- | --- |
| Position | Terminal `collect` | Intermediate `gather` |
| Input | Accumulated state | State and Downstream |
| Output | Function transforming `A → R` | Calls `push` 0, 1, or more times |
| Can emit onward in pipeline? | No, produces terminal result | Yes, sends output to subsequent stages |
| Short-circuit interaction | Has no Gatherer Downstream | Must respect downstream rejecting further elements |

If the goal is solely a final sum or a final List, you should generally consider `reduce` or `collect` before building a custom Gatherer.

## 3. Contract of finisher and Downstream

At the API level, `Gatherer.finisher()` provides a callback with type meaning:

~~~java
// Conceptual signature, not a standalone class.
BiConsumer<A, Gatherer.Downstream<? super R>> finisher;
~~~

`Downstream` provides two essential operations:

| Operation | Meaning |
| --- | --- |
| `downstream.push(value)` | Offers an element to emit; `boolean` return indicates whether more are still accepted |
| `downstream.isRejecting()` | Indicates whether downstream is currently rejecting new elements |

Finisher pattern for a buffer:

~~~java
// Methods hasPending()/snapshot() are defined by the problem's state.
(state, downstream) -> {
    if (state.hasPending() && !downstream.isRejecting()) {
        downstream.push(state.snapshot());
    }
}
~~~

If the finisher may emit **multiple** final values, break out of the loop when downstream rejects:

~~~java
// Pseudocode where R and state.pendingValues() are application-defined.
(state, downstream) -> {
    for (R value : state.pendingValues()) {
        if (downstream.isRejecting() || !downstream.push(value)) {
            break;
        }
    }
}
~~~

`finisher` has no authority to force a terminal operation to accept all outputs. For instance, `limit(1)` only wants one output element: if downstream has already rejected, the tail held in state must not arbitrarily appear in the result.

## 4. Complete Problem: Fixed Batching and Flushing the Tail

We write a Gatherer accepting `Stream<T>` and producing `Stream<List<T>>`. Each batch holds at most `batchSize` elements. Full batches emit inside the integrator; an incomplete final batch emits inside the finisher.

### 4.1. State Invariants

1. Buffer holds only **elements read but not yet emitted**.
2. After emitting a full batch, the buffer must return to empty.
3. Output must be an **independent copy**, not sharing the mutable `ArrayList` itself.
4. Finisher emits only when the buffer is **non-empty** and downstream still accepts.
5. Each input appears **exactly once** in the result when the pipeline is consumed to completion.

### 4.2. Java 24+: Complete Program

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public class FixedBatchesDemo {

    static <T> Gatherer<T, ?, List<T>> batches(int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be > 0");
        }

        return Gatherer.<T, ArrayList<T>, List<T>>ofSequential(
            // initializer: create a fresh buffer per execution
            () -> new ArrayList<>(batchSize),

            // integrator: accumulate and emit batch when full
            (buffer, element, downstream) -> {
                Objects.requireNonNull(element, "element");
                buffer.add(element);

                if (buffer.size() == batchSize) {
                    List<T> ready = List.copyOf(buffer);
                    buffer.clear();
                    return downstream.push(ready);
                }

                return true;
            },

            // finisher: emit only the remaining items in buffer
            (buffer, downstream) -> {
                if (!buffer.isEmpty() && !downstream.isRejecting()) {
                    downstream.push(List.copyOf(buffer));
                }
            }
        );
    }

    public static void main(String[] args) {
        List<List<Integer>> result = List.of(
            1, 2, 3, 4, 5, 6, 7, 8
        ).stream()
            .gather(batches(3))
            .toList();

        System.out.println(result);
        // [[1, 2, 3], [4, 5, 6], [7, 8]]
    }
}
~~~

Meaning of the generic arguments `Gatherer<T, ArrayList<T>, List<T>>`:

- `T`: one source element.
- `ArrayList<T>`: mutable state for accumulation.
- `List<T>`: one output element of the Gatherer (one batch).

`Gatherer.ofSequential` fits because this logic processes batch boundaries in encounter order without defining how to merge parallel buffers.

### 4.3. Why Return downstream.push from the integrator?

Once a full batch is ready, the integrator calls `downstream.push(ready)`. If the result is `false`, downstream wants no more elements; the integrator also returns `false` to stop receiving inputs. If the batch is not full yet, the integrator returns `true` because it still needs to read further.

Finisher returns no Boolean. It simply checks whether state has a tail and whether downstream still accepts.

### 4.4. Result Table by Size

| Source | Batch size | Expected Result |
| --- | ---: | --- |
| `[]` | 3 | `[]` |
| `[1]` | 3 | `[[1]]` |
| `[1,2]` | 3 | `[[1,2]]` |
| `[1,2,3]` | 3 | `[[1,2,3]]` |
| `[1,2,3,4]` | 3 | `[[1,2,3],[4]]` |
| `[1,2,3,4,5,6]` | 3 | `[[1,2,3],[4,5,6]]` |
| `[1,2,3,4,5,6,7]` | 3 | `[[1,2,3],[4,5,6],[7]]` |

If a source has `N` elements, batch size `k > 0`, and the pipeline is consumed completely: the integrator emits `floor(N/k)` full batches, and the finisher emits **one** batch if `N % k != 0`. Batch count equals `ceil(N/k)` when `N > 0`, and 0 when the source is empty.

## 5. Do Not Emit the Mutable Buffer Itself

Common mistake:

~~~java
// WRONG: illustrated inside integrator.
if (buffer.size() == batchSize) {
    downstream.push(buffer); // Leaks the state object itself.
    buffer.clear();          // Wipes the content just emitted.
    return true;
}
~~~

If downstream retains a reference to `buffer`, previously emitted batches can be wiped clean or altered as `buffer` receives new data. Multiple batches might even point to **the exact same object**.

Right way when nulls are disallowed:

~~~java
List<T> ready = List.copyOf(buffer);
buffer.clear();
return downstream.push(ready);
~~~

`List.copyOf` builds an unmodifiable list structure. Calling `buffer.clear()` does not affect the already-emitted copy.

If business logic **permits null elements**, `List.copyOf` is unsuitable because it throws `NullPointerException`. You can copy structurally and wrap as unmodifiable:

~~~java
List<T> ready = java.util.Collections.unmodifiableList(
    new java.util.ArrayList<>(buffer)
);
buffer.clear();
return downstream.push(ready);
~~~

`Collections.unmodifiableList(new ArrayList<>(buffer))` creates an unmodifiable view over **a copy**, not over the original buffer. Still, if `T` is a mutable object, internal state of elements can still mutate: this is not a **deep immutable snapshot**.

**Rule:** Never call `Collections.unmodifiableList(buffer)` and then keep mutating `buffer`, because that wrapper still reflects changes to the backing list.

## 6. Empty Source, Zero Remainder, and Early Downstream Stop

### 6.1. Empty Source

~~~java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> result = Stream.<Integer>empty()
    .gather(FixedBatchesDemo.batches(3))
    .toList();

System.out.println(result); // []
~~~

Because there are no elements to emit, the finisher must check `buffer.isEmpty()` to avoid emitting a bogus `[]`.

### 6.2. Exact Multiple of Batch Size

~~~java
List<List<Integer>> result = List.of(1, 2, 3, 4, 5, 6)
    .stream()
    .gather(FixedBatchesDemo.batches(3))
    .toList();

System.out.println(result); // [[1, 2, 3], [4, 5, 6]]
~~~

If the finisher **always** called `downstream.push(List.copyOf(buffer))` without checking emptiness, the result could append an extra `[]` at the end. That is a business bug if each batch represents a real processing request.

### 6.3. Short-Circuiting with limit

~~~java
List<List<Integer>> first = List.of(
    1, 2, 3, 4, 5, 6, 7
).stream()
    .gather(FixedBatchesDemo.batches(3))
    .limit(1)
    .toList();

System.out.println(first); // [[1, 2, 3]]
~~~

`limit(1)` does not request subsequent batches. If downstream rejects further elements, the integrator should stop and the finisher must not try to push the remainder. Never write tests requiring the integrator to run on **all source elements** merely because a `finisher` exists.

### 6.4. Do Not Use Callbacks as an Audit Mechanism

How many times `integrator`, `finisher`, or a pipeline lambda is called can be affected by short-circuiting and optimizations. If a system needs mandatory business logging, transactions, or outbound requests, design a dedicated orchestration mechanism. `finisher` does not replace a guaranteed exactly-once transaction hook.

## 7. Grouping by Delimiter: Handling a Final Section Without a Closing Marker

Another example is splitting text lines into groups; a blank line closes the current group. A file may end right after a content line instead of a blank line.

~~~text
Input lines:
alpha
beta

gamma
delta
EOF

Integrator:
  sees blank line → emits [alpha, beta]
  retains [gamma, delta] at end of source

Finisher:
  emits [gamma, delta]

Result:
[[alpha, beta], [gamma, delta]]
~~~

### 7.1. Java 24+ Program

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public class DelimitedSectionsDemo {

    static Gatherer<String, ?, List<String>> sections() {
        return Gatherer.<String, ArrayList<String>, List<String>>
            ofSequential(
                ArrayList::new,

                (buffer, line, downstream) -> {
                    Objects.requireNonNull(line, "line");

                    if (line.isBlank()) {
                        if (buffer.isEmpty()) {
                            // Ignore consecutive delimiters.
                            return true;
                        }

                        List<String> ready = List.copyOf(buffer);
                        buffer.clear();
                        return downstream.push(ready);
                    }

                    buffer.add(line);
                    return true;
                },

                (buffer, downstream) -> {
                    if (!buffer.isEmpty() && !downstream.isRejecting()) {
                        downstream.push(List.copyOf(buffer));
                    }
                }
            );
    }

    public static void main(String[] args) {
        List<String> lines = List.of(
            "alpha", "beta", "", "gamma", "delta"
        );

        List<List<String>> groups = lines.stream()
            .gather(sections())
            .toList();

        System.out.println(groups);
        // [[alpha, beta], [gamma, delta]]
    }
}
~~~

### 7.2. Edge Cases

| Source | Result per Example's Policy |
| --- | --- |
| `[]` | `[]` |
| `[""]` | `[]` |
| `["A"]` | `[["A"]]` |
| `["A",""]` | `[["A"]]` |
| `["A","","","B"]` | `[["A"],["B"]]` |

The example **drops empty sections**. If the system needs to preserve empty sections between two delimiters, the integrator needs a different contract. The finisher only handles **the open section at termination**, rather than replacing the entire boundary-detection logic.

### 7.3. Memory Risks

If a long source has no blank lines, the buffer accumulates the entire section. The finisher cannot reduce RAM usage **prior to termination**. With real-world data, you may need to cap line count or byte size, and raise an error or flush partial groups according to business rules.


## 8. Run-Length Encoding: Emitting the Final Unclosed Run

Another problem requiring a finisher is **run-length encoding**: grouping **consecutive** equal elements into `(value, count)` pairs.

~~~text
Source: A, A, B, B, B, A

Integrator:
  On first B → emits Run(A, 2)
  On final A → emits Run(B, 3)
  At EOF, Run(A, 1) remains unemitted

Finisher:
  emits Run(A, 1)

Output:
[Run(A, 2), Run(B, 3), Run(A, 1)]
~~~

### 8.1. Complete Java 24+ Code

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public class RunLengthDemo {

    record Run<T>(T value, long count) {}

    static final class State<T> {
        boolean hasValue;
        T currentValue;
        long count;
    }

    static <T> Gatherer<T, ?, Run<T>> runs() {
        return Gatherer.<T, State<T>, Run<T>>ofSequential(
            () -> new State<T>(),

            (state, element, downstream) -> {
                if (!state.hasValue) {
                    state.hasValue = true;
                    state.currentValue = element;
                    state.count = 1L;
                    return true;
                }

                if (Objects.equals(state.currentValue, element)) {
                    state.count = Math.addExact(state.count, 1L);
                    return true;
                }

                Run<T> finished = new Run<>(
                    state.currentValue, state.count
                );

                state.currentValue = element;
                state.count = 1L;
                return downstream.push(finished);
            },

            (state, downstream) -> {
                if (state.hasValue && !downstream.isRejecting()) {
                    downstream.push(new Run<>(
                        state.currentValue, state.count
                    ));
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Run<String>> encoded = List.of(
            "A", "A", "B", "B", "B", "A"
        ).stream()
            .gather(RunLengthDemo.<String>runs())
            .toList();

        System.out.println(encoded);
        // [Run[value=A, count=2],
        //  Run[value=B, count=3],
        //  Run[value=A, count=1]]
    }
}
~~~

### 8.2. Why Is hasValue Needed?

`currentValue` may equal `null` if the source permits nulls. If you used `currentValue == null` to detect "no data yet", the program would confuse it with a genuine run of consecutive null elements.

The `hasValue` flag separates two states: **no element seen yet** and **seen an element whose value is null**. `Objects.equals` safely compares two nulls, and the `Run<T>` record does not forbid null.

~~~java
import java.util.Arrays;
import java.util.List;

List<RunLengthDemo.Run<String>> encoded =
    Arrays.<String>asList(null, null, "A", null)
        .stream()
        .gather(RunLengthDemo.<String>runs())
        .toList();

System.out.println(encoded);
// [Run[value=null, count=2],
//  Run[value=A, count=1],
//  Run[value=null, count=1]]
~~~

`List.of` does not allow nulls, so the example uses `Arrays.asList`.

### 8.3. Why Not Replace It with groupingBy?

With source `["A", "A", "B", "A"]`:

- Run-length: `[Run(A,2), Run(B,1), Run(A,1)]`.
- `groupingBy(identity(), counting())`: `A→3`, `B→1`.

Run-length preserves **consecutive boundaries in encounter order**, whereas `groupingBy` merges all elements with the same key across the entire source. For simple frequency counting, `groupingBy` is more concise.

## 9. Emitting Only in the finisher: A Final Summary at End of Source

A finisher does not have to emit only the **remainder** of a batch. A Gatherer can emit nothing inside the integrator and then emit **one final summary** from state.

The example below chooses the policy: **an empty source still emits `Summary(count=0,sum=0)`**.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class FinalSummaryDemo {

    record Summary(long count, long sum) {}

    static final class State {
        long count;
        long sum;
    }

    static Gatherer<Integer, ?, Summary> summarize() {
        return Gatherer.<Integer, State, Summary>ofSequential(
            State::new,

            (state, number, downstream) -> {
                if (number == null) {
                    throw new IllegalArgumentException(
                        "Null elements are not accepted"
                    );
                }
                state.count = Math.addExact(state.count, 1L);
                state.sum = Math.addExact(
                    state.sum, number.longValue()
                );

                // Accumulate only, emit nothing yet.
                return true;
            },

            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(
                        new Summary(state.count, state.sum)
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        System.out.println(
            List.of(2, 3, 5).stream()
                .gather(summarize())
                .toList()
        ); // [Summary[count=3, sum=10]]

        System.out.println(
            Stream.<Integer>empty()
                .gather(summarize())
                .toList()
        ); // [Summary[count=0, sum=0]]
    }
}
~~~

**Points to note:**

- `State` holds only `count` and `sum` fields, without storing every element.
- `Math.addExact` detects `long` overflow.
- Finisher emits an immutable value object.
- If "no measurements" differs from "actual sum is 0", adjust the finisher to **skip emitting** when `state.count == 0` or use a result type explicitly modeling missing data.

### Gatherer or collect?

If you only need one final end-of-source summary, terminal `collect` or `reduce` is usually a better fit:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;

IntSummaryStatistics stats = List.of(2, 3, 5)
    .stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 10
~~~

The summary Gatherer example here illustrates **that the finisher can be the sole output-emitting step**, not that you should always replace terminal collectors with custom Gatherers.

## 10. A Finisher Can Push Multiple Final Values

`Gatherer.finisher()` is a `BiConsumer` callback, so it is not limited to a single output element. A state may hold multiple notifications or data chunks to emit at completion.

~~~java
// Pseudocode: state.pendingValues() returns an application-defined Iterable<R>.
(state, downstream) -> {
    for (R value : state.pendingValues()) {
        if (downstream.isRejecting()) {
            break;
        }
        if (!downstream.push(value)) {
            break;
        }
    }
}
~~~

This is only an illustrative pattern; `pendingValues()` is not a Gatherer API method. Always check the return value of `push` because a terminal operation may stop early. Never use `pending.forEach(downstream::push)` which silently ignores rejection signals.

A finisher emitting multiple values must also control:

- Is the number of final outputs bounded by a reasonable limit?
- Does state hold only **unemitted** elements rather than accidentally re-including already-emitted ones?
- Are emitted outputs safe immutable/snapshot structures?
- If downstream rejects after a few values, does the logic stop immediately?

Never write a finisher that emits an infinite sequence or relies on a loop without a termination criterion.

## 11. Policies for the Tail: Keep, Drop, Pad, or Error

Not every domain wants to emit an undersized final batch. Given input `[1,2,3,4]` and batch size 3:

| Policy | Result | Finisher Behavior |
| --- | --- | --- |
| Keep short batch | `[[1,2,3],[4]]` | `push([4])` |
| Drop remainder | `[[1,2,3]]` | Emit nothing |
| Pad | `[[1,2,3],[4,0,0]]` | Pad with 0s then emit |
| Require full batches | Throw error | Detect non-empty buffer |

In transaction processing, dropping the remainder can cause severe data loss. In some signal-processing domains, discarding a partial trailing window is the standard convention.

A finisher can reject an incomplete batch:

~~~java
// Snippet for a List state, not a standalone program.
(buffer, downstream) -> {
    if (!buffer.isEmpty()) {
        throw new IllegalStateException(
            "Final batch is missing elements: " + buffer.size()
        );
    }
}
~~~

A parser with `BEGIN/END` markers can adopt a similar policy: if EOF arrives while a record has not seen `END`, the finisher throws an error instead of auto-closing the record.

### Null Policy Must Be Consistent Across Both Branches

If the integrator uses a null-accepting container to emit full batches while the finisher uses `List.copyOf(buffer)`, a final batch containing null will throw an inconsistent NPE. Either disallow nulls upfront on arrival or use the same null-supporting snapshot mechanism in both integrator and finisher.

## 12. Parallelism: finisher Does Not Replace combiner

Examples in this lesson use `Gatherer.ofSequential(...)` because the logic depends on order and data boundaries. With run-length encoding, splitting a source can slice right through a run:

~~~text
Ordered source: [A, A, A, B, B]

Split into:
Left:  [A, A]
Right: [A, B, B]

If each branch flushes its tail and concatenates naively:
  Run(A,2), Run(A,1), Run(B,2)

Correct result:
  Run(A,3), Run(B,2)
~~~

To design a Gatherer that genuinely supports parallel state merging, you must solve:

1. Which boundary metadata of each segment must state retain?
2. Is the state-merging combiner **associative**?
3. How are two runs or batches straddling a split boundary merged?
4. Is encounter order preserved when the algorithm requires it?
5. How is the tail emitted **after full merging**, without flushing prematurely?

`ofSequential` provides no combiner for parallel state merging. Calling `parallelStream().gather(sequentialGatherer)` does not magically synthesize a valid state merge either. Never assume `parallel()` brings a speedup; benchmark on representative data after verifying correctness.

**Rule:** Until a valid state combine is proven, prefer sequential Gatherers. When parallelism is desired, design a Gatherer with a valid combiner and test across multiple split layouts.


## 13. Finisher Is Not finally or close

The name `finisher` easily makes learners think of `finally` or `AutoCloseable.close()`. Yet the two sets of responsibilities are completely separate:

- **`Gatherer.finisher()`:** finalizes **data inside state**, possibly emitting remaining results.
- **`Stream.close()`, `onClose()`, try-with-resources:** releases external resources such as files, readers, sockets, or connections.

Never depend on a finisher as a "guaranteed run-once" callback to close resources, execute payments, or commit a transaction. Short-circuiting, exceptions, and pipeline execution strategies can alter execution paths; resource closing must be managed separately.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FileSectionsDemo {
    static List<List<String>> readSections(Path file)
        throws IOException {

        try (Stream<String> lines = Files.lines(file)) {
            return lines
                .gather(DelimitedSectionsDemo.sections())
                .toList();
        }
    }
}
~~~

Here:

1. `Files.lines(file)` creates a Stream backed by a file resource.
2. `gather(sections())` groups lines into sections; finisher emits the last section when EOF arrives without a trailing blank line.
3. `try-with-resources` guarantees closing the Stream/file per API contract, even if an exception occurs during traversal.

If a Gatherer allocates external resources itself, explicitly design **who owns, who closes, and error recovery**. Finisher is only an output-transformation step, not a replacement resource-management mechanism.

## 14. Testing to Prove the Tail Is Neither Lost nor Duplicated

For encounter-ordered batching with a **keep-remainder** policy, you can verify these invariants:

~~~text
N = number of input elements, k = batch size > 0

Total elements across all batches = N
Batch count:
  N = 0: 0
  N > 0: ceil(N / k)

Each batch has 1 to k elements.
Concatenating batches in order == exact source list.
~~~

This tests **outputs**, not how many times `integrator` or `finisher` was invoked.

### 14.1. Dependency-Free Test Program

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

public class BatchFinisherChecks {

    static void check(int count, int batchSize) {
        List<Integer> source = IntStream.range(0, count)
            .boxed()
            .toList();

        List<List<Integer>> actual = source.stream()
            .gather(FixedBatchesDemo.batches(batchSize))
            .toList();

        int expectedNumberOfBatches = count == 0
            ? 0
            : (count - 1) / batchSize + 1;

        if (actual.size() != expectedNumberOfBatches) {
            throw new AssertionError(
                "Wrong batch count, N=" + count + ", k=" + batchSize
            );
        }

        ArrayList<Integer> flattened = new ArrayList<>();

        for (List<Integer> batch : actual) {
            if (batch.isEmpty() || batch.size() > batchSize) {
                throw new AssertionError(
                    "Empty batch or exceeds limit"
                );
            }
            flattened.addAll(batch);
        }

        if (!flattened.equals(source)) {
            throw new AssertionError(
                "Missing, duplicated, or reordered elements"
            );
        }
    }

    public static void main(String[] args) {
        for (int k : new int[] {1, 2, 3, 5, 8}) {
            for (int n = 0; n <= 30; n++) {
                check(n, k);
            }
        }
        System.out.println("PASS");
    }
}
~~~

These cases cover:

- Empty source.
- Source shorter than batch size.
- Source fitting one or multiple full batches exactly.
- Source with remainder of 1 to `k-1` elements.
- Batch size of 1.
- Multiple source sizes to catch boundary bugs.

### 14.2. Testing Early Downstream Stop

~~~java
import java.util.List;

List<List<Integer>> result = List.of(
    1, 2, 3, 4, 5, 6, 7
).stream()
    .gather(FixedBatchesDemo.batches(3))
    .limit(1)
    .toList();

if (!result.equals(List.of(List.of(1, 2, 3)))) {
    throw new AssertionError("limit(1) received wrong batch");
}
~~~

This test does not require the entire source to be traversed. `limit(1)` only cares about one output, and the Gatherer must respect that.

### 14.3. Testing the Final Run

~~~java
import java.util.List;

List<RunLengthDemo.Run<String>> actual = List.of(
    "A", "A", "B", "B", "B", "A"
).stream()
    .gather(RunLengthDemo.<String>runs())
    .toList();

List<RunLengthDemo.Run<String>> expected = List.of(
    new RunLengthDemo.Run<>("A", 2),
    new RunLengthDemo.Run<>("B", 3),
    new RunLengthDemo.Run<>("A", 1)
);

if (!actual.equals(expected)) {
    throw new AssertionError("Wrong final run");
}
~~~

Because `Run` is a record, `equals` compares fields by value; this test catches **forgetting to emit the final run** and **emitting an already-completed run twice**.

### 14.4. Testing Errors and Nulls

In addition to happy paths, test error policies:

- `batchSize <= 0` must be rejected.
- Invalid `null` in batches must be caught per rules.
- `Math.addExact` in summary may throw on overflow.
- Consecutive delimiters and leading/trailing delimiters produce the right group count.
- Run-length with nulls creates valid runs if a null-supporting policy was chosen.

Never infer that a test on a few elements proves correctness for all sources; testing aims to cover **meaningful boundaries**.

## 15. Performance and Built-in APIs Instead of Custom Gatherers

### 15.1. State Memory

| Algorithm | Typical State | Limit to Watch |
| --- | --- | --- |
| Batch of size `k` | Buffer of at most `k` elements | Copy allocation upon emission |
| Run-length | Current value + counter | Counter overflow checks |
| Group by delimiter | Buffer since previous delimiter | Can grow large if delimiters are rare |
| End-of-source summary | A few counter/sum fields | May emit nothing until EOF |
| Parser with open record | Syntax state + unclosed data | Needs bounds and EOF policy |

`finisher` cannot reduce RAM **before completion** if the integrator accumulates unboundedly. On an infinite Stream, a Gatherer that only emits in the finisher may **never deliver output**, because there is no EOF to trigger emission.

### 15.2. Snapshots Cost Work Yet Are Necessary

`List.copyOf(buffer)` or `new ArrayList<>(buffer)` uses memory and copy work. This is the cost of guarding against **mutable reference leaks**. Never replace it with `push(buffer)` followed by `clear` just to save one allocation when downstream needs to retain the data.

### 15.3. If Only Fixed Windows Are Needed, Check Gatherers.windowFixed

Java 24 provides built-in Gatherers. When the task is purely splitting into fixed-size windows, `Gatherers.windowFixed(int)` is the option to consider before writing your own:

~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> result = List.of(
    1, 2, 3, 4, 5, 6, 7
).stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(result);
// [[1, 2, 3], [4, 5, 6], [7]]
~~~

Write a custom Gatherer when specialized rules are needed: final batch must be padded or throw an error; each batch carries metadata; byte-size limits; multi-marker protocols; or emitting a final event with business status.

For problems needing only a `sum` or `count`, prefer standard terminals. Do not build a new Gatherer just because the API makes it possible.

## 16. Ten Common Mistakes When Writing a finisher

### Mistake 1 — Forgetting to Flush the Final Buffer

The integrator emits only full batches. Without finisher logic, trailing elements fewer than batch size are dropped.

**Fix:** check whether state holds data and emit the tail per policy.

### Mistake 2 — Emitting a Spurious Empty Batch

Finisher calls `push(List.copyOf(buffer))` even when `buffer` is empty.

**Fix:** only emit when `!buffer.isEmpty()`.

### Mistake 3 — Exposing the Mutable Buffer Itself

`downstream.push(buffer)` followed by `buffer.clear()` alters emitted output after the fact.

**Fix:** take an independent snapshot before clearing.

### Mistake 4 — Failing to Clear Emitted State

After a full batch, failing to clear the buffer causes the finisher to re-emit old data.

**Fix:** state must hold only **unemitted** elements.

### Mistake 5 — Using One Shared Buffer Across Multiple Pipelines

~~~java
// Do not do this: initializer always returns the same mutable object.
// ArrayList<String> shared = new ArrayList<>();
// Gatherer.ofSequential(() -> shared, integrator, finisher);
~~~

**Fix:** initializer creates a fresh state per evaluation.

### Mistake 6 — Ignoring Downstream Rejection

`push` returns false yet the integrator keeps reading and pushing data. Finisher does not check `isRejecting()`.

**Fix:** return false from the integrator, and stop emitting when downstream rejects.

### Mistake 7 — Inconsistent Null Policy

Full batches use a container accepting nulls, whereas the final batch uses `List.copyOf` and throws NPE.

**Fix:** validate or convert nulls consistently across both branches.

### Mistake 8 — Treating finisher as a File-Closing / Notification Hook

Finisher is a data-finalization step, not a guaranteed side-effect protocol.

**Fix:** handle resources and business actions with dedicated mechanisms.

### Mistake 9 — Adding parallel Without a Valid Combiner

The algorithm depends on consecutive boundaries yet is expected to auto-split and merge.

**Fix:** use `ofSequential` or design an associative combiner and test across multiple splits.

### Mistake 10 — Waiting for EOF on an Infinite Source

If emission occurs solely inside the finisher, a non-terminating source will never produce final output.

**Fix:** emit incrementally in the integrator or add appropriate limits/termination conditions.

## 17. Checklist Before Delivering a Custom Gatherer

| Question | Required Answer |
| --- | --- |
| What are input `T` and output `R`? | Types and meaning of each element |
| What does state `A` hold? | Only unemitted items or final statistics |
| Why is a finisher needed? | Which outputs aren't ready to emit inside the integrator |
| Does an empty state emit? | Explicit rule for empty sources |
| How is a partial final batch handled? | Keep, drop, pad, or error |
| Are nulls accepted? | Unified validation and snapshot policy |
| Must outputs be immutable? | Copy state before push; consider mutable elements |
| Can downstream stop early? | Respect `push` and `isRejecting()` |
| Could the source be infinite? | Termination condition must not rely solely on EOF |
| Is parallelism required? | Valid combiner, partition boundary tests |
| Are there external resources to close? | Separate try-with-resources / close |
| Does a built-in operation exist? | Consider `Gatherers.windowFixed`, `collect`, `reduce` |
| What do tests verify? | No drops/duplicates, empty, remainder, short-circuit |

## 18. Review Questions and Extension Exercises

1. **How does finisher differ from integrator?** Integrator processes each input; finisher finalizes state and may emit remaining items.
2. **What two arguments does finisher receive?** Accumulated state and `Gatherer.Downstream`.
3. **Does finisher directly return a single result like Collector.finisher?** No; it calls `push` and can emit multiple elements.
4. **With 8 elements and batch size 3, how many batches are output?** Three batches of sizes 3, 3, 2 if keeping the tail.
5. **With 6 elements and batch size 3, should an empty batch be appended?** No.
6. **If the source is empty, should a batcher emit `[]`?** Not under the keep-real-batches policy in this lesson.
7. **Why snapshot before clearing?** To prevent downstream from holding references to mutable state.
8. **Does `List.copyOf` accept nulls?** No.
9. **What should the integrator do when `push` returns false?** Return false to request stopping input.
10. **Why does finisher check `isRejecting()`?** To avoid pushing more items into an already-rejecting downstream.
11. **When does run-length encoding need a finisher?** To emit the final run when no subsequent value arrives to trigger emission.
12. **Why is the `hasValue` flag needed if elements can be null?** To distinguish no data yet from having seen null.
13. **What happens when delimiter grouping hits EOF without a closing marker?** Finisher can emit the final group or throw an error per contract.
14. **Does `ofSequential` need a combiner?** No; it is for sequential Gatherers.
15. **Can a parallel gatherer independently flush edge segments?** No if groups can span boundaries; states must be merged properly.
16. **Does finisher replace closing a Stream from `Files.lines`?** No; `try-with-resources` is still required.
17. **What other APIs should be considered for a single-value summary?** `reduce`, `collect`, or `summaryStatistics`.
18. **How do you verify batches neither lose nor duplicate elements?** Flatten all batches in order and compare to the ordered input.
19. **Why not use finisher as a mandatory email-sending command?** It is a data-transformation hook, not a transaction/side-effect contract.
20. **What if the source is infinite and the Gatherer only emits in finisher?** Final output may never appear.

### Extension A — Batch with Metadata

Modify the batcher to emit `record Batch<T>(long index, List<T> items, boolean complete)`. Full-sized batches have `complete = true`; a partial final batch has `complete = false`. Test empty sources and exact multiples.

### Extension B — Parser with BEGIN/END

Write a Gatherer receiving `BEGIN`, body lines, and `END`. If EOF arrives while a record is still open, the finisher throws an exception clearly reporting the position. Test two consecutive `BEGIN`s.

### Extension C — Compressing Nulls

Pass `Arrays.asList(null, null, "A", null)` into `RunLengthDemo`. Verify the output contains three runs corresponding to `null×2`, `A×1`, `null×1`.

### Extension D — Distinguishing Limits Before and After Gatherer

Compare `source.stream().limit(5).gather(batches(4))` with `source.stream().gather(batches(4)).limit(1)`. One pipeline limits **input count**, while the other limits **output batch count**, so they are not equivalent.

### Extension E — Bounding the Buffer

In `DelimitedSectionsDemo`, add a limit of 1,000 lines per group. If exceeded before seeing a delimiter, define an error or partial-group emission policy to avoid unbounded state retention.

**Remember:** `Gatherer.finisher()` handles state **remaining when the source or accumulation phase ends**. For batching, delimiters, and run-length encoding, it ensures the final batch/group/run is not lost. Keep state containing only unemitted items, emit independent snapshots, avoid spurious empty groups, respect early downstream termination, and enforce a consistent null policy. Finisher does not replace resource management, nor does it solve infinite sources or parallel state merging on its own; use built-in Gatherers and standard collectors whenever they already fit.
