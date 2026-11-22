# Testing Output Counts, Laziness, Early Termination, and State Merging

> **Chapter:** Building Custom Gatherers  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, `collect`; practice grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while recognizing constraints around state, resources, and performance.

When writing a custom `Gatherer`, getting it to run on a few elements **does not prove it is correct**. A Gatherer can emit **zero, one, or multiple elements** per input element; may wait until the end of the source to emit results; may request early termination itself; and if it supports parallel execution, it must merge states from multiple branches according to contract. These behaviors require distinct test cases.

This lesson focuses on **how to design and test custom Gatherers**, not merely how to write lambdas. Examples use the `java.util.stream.Gatherer` and `Stream.gather(...)` APIs, which are official features starting in **Java 24**. On Java 22/23, Stream Gatherers are in preview and require the corresponding preview configuration; code in this lesson targets **JDK 24 and later** and does not run on JDK 17.

After this lesson, you will be able to:

1. Verify a Gatherer's output count on empty sources, multi-element sources, partial batches, and downstream output limits.
2. Verify that pipelines execute only when a terminal operation runs, without relying on side effects in `peek` as a business contract.
3. Distinguish **integrator-driven termination** from **downstream-rejection termination**; propagate `false` signals properly.
4. Test `initializer`, `integrator`, `combiner`, and `finisher` of a stateful Gatherer; compare sequential and parallel runs.
5. Catch bugs where `combiner` drops data, state is shared, or merging is non-associative.

## 1. Review of the `Gatherer<T, A, R>` Contract

A Gatherer is an **intermediate operation** transforming `Stream<T>` into `Stream<R>`; there is not necessarily a 1:1 ratio between input and output elements. For stateful Gatherers, `A` is the internal state type.

| Component | Conceptual Type | Testing Meaning |
| --- | --- | --- |
| `initializer` | `Supplier<A>` | Each state must be freshly created, never leaking across runs or branches. |
| `integrator` | `Integrator<A, T, R>` | Receives elements, may `push` 0..n results, returns `true` to continue or `false` to stop. |
| `combiner` | `BinaryOperator<A>` | Merges two states from partitions; must satisfy identity and associativity. |
| `finisher` | `BiConsumer<A, Downstream<? super R>>` | Optionally emits final results after accumulation; may produce output even on an empty source. |

Two methods related to early termination:

```java
boolean accepted = downstream.push(result);
boolean rejecting = downstream.isRejecting();
```

- `push(result)` returns `false` if downstream wants no more results. Once it has returned `false`, subsequent `push` calls will not be accepted.
- `isRejecting()` is only a **best-effort** check signal: never rely on it as an absolute guarantee that downstream will accept more.
- `Integrator.integrate(...)` returns `false` to signal **no more inputs needed**. After that, do not expect the integrator to be called further.
- `Gatherer.Integrator.Greedy` is an integrator kind that **never initiates early termination itself**; it may only reflect a stop request from downstream. Never mark an integrator as greedy if it proactively returns `false` upon reaching a count.

Overview diagram:

```text
Source T ──► integrator(state, T, downstream)
                    │
                    ├── no push           → 0 results
                    ├── push once         → 1 result
                    ├── push many times   → multiple results
                    └── return false      → stop receiving source elements
                              │
                              ▼
               combiner (if split) + finisher
                              │
                              ▼
                         Stream<R>
```

Note that `Gatherer.ofSequential(...)` creates a Gatherer with sequential processing semantics for the gather stage itself. `Gatherer.of(initializer, integrator, combiner, finisher)` allows this stage to partition and merge state when needed. Never assume every parallel pipeline **must** invoke the combiner or invoke it a fixed number of times.

## 2. Test Matrix to Prepare Before Writing Code

| Criterion | Test Case | Expectation to Assert |
| --- | --- | --- |
| Output count | 0 source elements | 0 or the number of outputs **explicitly designed** by the finisher, not assumed by default. |
| Output count | Gatherer duplicating 3 elements | Exactly 6 elements with exact content. |
| Batch | 5 elements, batch size 2 | Two full batches and one final batch of 1 element. |
| Laziness | Build pipeline without a terminal operation | Source is not traversed yet. |
| Integrator stop | `takeFirst(3)` on long/infinite source | Exactly 3 results; terminates without processing the entire source. |
| Downstream stop | `duplicate().limit(3)` | Exactly 3 results; integrator stops pushing once rejected. |
| State merging | Split data into multiple segments | Combined total matches single-pass calculation. |
| Identity | Merge with empty state | Result is unchanged. |
| Associativity | `(A + B) + C` and `A + (B + C)` | Results are equivalent. |
| Parallel | Same data, sequential vs parallel | Business results match. |
| Order | `List` source with encounter order | Preserves order if part of the Gatherer's contract. |

Do not lump everything into one generic test. Checking only `count()` can miss **wrong order with right count**; checking only small sequential inputs can miss **a combiner dropping data**.

## 3. Testing Output Counts: One Input Can Produce Multiple Results

The smallest example is a Gatherer that **emits each element twice**. Since no state is needed, we use the overload without an initializer:

```java
import java.util.stream.Gatherer;

static Gatherer<Integer, ?, Integer> duplicateEach() {
    return Gatherer.<Integer, Integer>ofSequential(
            (ignored, value, downstream) -> {
                if (!downstream.push(value)) {
                    return false;
                }
                return downstream.push(value);
            }
    );
}
```

`duplicateEach()` is an **intermediate operation**, not regular `map`: `map` emits exactly one output per input, whereas this Gatherer emits up to two.

```java
List<Integer> doubled = Stream.of(2, 4, 6)
        .gather(duplicateEach())
        .toList();

System.out.println(doubled); // [2, 2, 4, 4, 6, 6]
```

If the source is empty, the result is empty. If downstream stops after 3 outputs, the result is `[2, 2, 4]`: there is no requirement to emit the complete pair for `4` **after downstream rejects**.

**Common mistake:** calling `downstream.push(value)` twice and always doing `return true`. When the first `push` returns `false`, the second call is wasted work and the Gatherer fails to propagate the stop signal upstream.

## 4. Testing the Final Batch: `finisher` Can Change Output Count

A common pattern is grouping every `size` elements into a `List<T>`. If an incomplete group remains when the source ends, `finisher` must flush it. This is a **sequential** example to avoid complex requirements around merging batch positions across parallel branches.

```java
static Gatherer<Integer, ?, List<Integer>> fixedBatches(int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }
    return Gatherer.<Integer, List<Integer>, List<Integer>>ofSequential(
            ArrayList::new,
            (buffer, value, downstream) -> {
                buffer.add(value);
                if (buffer.size() == size) {
                    List<Integer> batch = List.copyOf(buffer);
                    buffer.clear();
                    return downstream.push(batch);
                }
                return true;
            },
            (buffer, downstream) -> {
                if (!buffer.isEmpty() && !downstream.isRejecting()) {
                    downstream.push(List.copyOf(buffer));
                }
            }
    );
}
```

Result:

```java
List<List<Integer>> batches = Stream.of(1, 2, 3, 4, 5)
        .gather(fixedBatches(2))
        .toList();
// [[1, 2], [3, 4], [5]]
```

Here:

- Input has 5 elements, output has only **3 elements**, each output element being a `List<Integer>`.
- `integrator` emits a batch as soon as 2 elements accumulate.
- `finisher` emits the final batch only if data remains and downstream is not known to be rejecting.
- With an empty source, the result is an empty list because `buffer` is empty; unlike a full-period summary Gatherer that may intentionally emit **one empty summary object**.
- `List.copyOf(buffer)` isolates emitted batches from the reused mutable buffer. Pushing `buffer` directly and then calling `clear()` would unexpectedly mutate already-returned batches.

Do not only assert `batches.size() == 3`: inspect every batch as well, because bugs like `[1,2], [2,3], [4]` also produce three batches yet with wrong contents.

## 5. Testing Laziness: Distinguish Pipeline Creation from Pipeline Execution

A Gatherer is an intermediate operation, so **constructing the pipeline does not pull elements from the source**. Test code can use a counter solely to observe how many times an intermediate step was evaluated:

```java
AtomicInteger visited = new AtomicInteger();

Stream<Integer> pipeline = IntStream.rangeClosed(1, 4)
        .boxed()
        .map(n -> {
            visited.incrementAndGet(); // Used solely for measurement in test
            return n;
        })
        .gather(duplicateEach());

check(visited.get() == 0, "Pipeline ran too early");
List<Integer> result = pipeline.toList();
check(result.equals(List.of(1, 1, 2, 2, 3, 3, 4, 4)),
        "Output content");
check(visited.get() == 4, "Source was not fully processed");
```

In this example, `toList()` needs the results produced by the Gatherer, so all four inputs must pass through `map`. However, **do not generalize** that every `map` or `peek` is always invoked once per element in all pipelines: Java Streams may optimize away intermediate operations that cannot affect the terminal result.

**Rule:** an external counter is an **observation tool in a specific test**, not a business design. In production code, avoid putting database writes, business counters, or notifications inside `peek` assuming the pipeline will always execute them.

## 6. Testing Self-Initiated Early Termination by the Gatherer

A `takeFirst(maximum)`-style Gatherer maintains state counting emitted elements. Once the count is reached, the integrator returns `false`.

```java
static Gatherer<Integer, ?, Integer> takeFirst(int maximum) {
    if (maximum < 0) {
        throw new IllegalArgumentException("negative maximum");
    }
    return Gatherer.<Integer, int[], Integer>ofSequential(
            () -> new int[1],
            (state, value, downstream) -> {
                if (state[0] >= maximum) {
                    return false;
                }
                state[0]++;
                return downstream.push(value) && state[0] < maximum;
            }
    );
}
```

Test:

```java
List<Integer> firstThree = Stream.iterate(1, n -> n + 1)
        .gather(takeFirst(3))
        .toList();
// [1, 2, 3]
```

A `Stream.iterate` source can be infinite. If the Gatherer fails to stop on time, the `toList()` terminal operation will never finish. In a large automated test suite, add a **test-case timeout** so that a broken short-circuit does not hang the suite forever.

Do not use `Gatherer.Integrator.ofGreedy(...)` for `takeFirst`: this integrator **proactively** stops accepting source elements based on count, so it violates the *greedy* contract.

### What Does `maximum == 0` Mean?

`takeFirst(0)` produces an **empty output**. With the sample implementation, it may receive one input element so the integrator sees it must stop and returns `false`; therefore, do not advertise this check as guaranteeing **zero source elements pulled**. If business rules require never touching the source when the limit is 0, apply `limit(0)` upfront or handle it on the caller side.

## 7. Testing Downstream Termination: `push` and `limit`

Unlike `takeFirst`, here **downstream** is the side deciding enough data has arrived:

```java
List<Integer> limited = Stream.iterate(1, n -> n + 1)
        .gather(duplicateEach())
        .limit(3)
        .toList();

System.out.println(limited); // [1, 1, 2]
```

After `limit(3)`, downstream needs no more elements. The Gatherer must stop sending more as soon as `push` reports `false`, rather than trying to duplicate subsequent elements.

Both termination directions need independent tests:

| Stop Source | Example Code | Primary Signal |
| --- | --- | --- |
| Integrator proactively stops | `gather(takeFirst(3))` | `integrate` returns `false` upon reaching limit. |
| Downstream rejects | `gather(duplicateEach()).limit(3)` | `downstream.push(...)` returns `false`, integrator propagates it. |

For parallel or buffered pipelines, **do not test by assuming upstream accesses strictly 3 elements**. Stages may prefetch or process extra elements depending on implementation details. Test **outputs and termination**; only rely on exact visit counts when the contract or source design actually guarantees them.

## 8. Merging State: Testing Identity and Associativity

A statistics-collecting Gatherer can use `A = CountState`, where `count` and `sum` update as elements arrive. Instead of emitting on every accumulation, `finisher` emits **one** `Summary` upon completion.

```java
record Summary(long count, long sum) {}

static final class CountState {
    long count;
    long sum;

    void add(long n) {
        count = Math.addExact(count, 1);
        sum = Math.addExact(sum, n);
    }

    CountState merge(CountState right) {
        count = Math.addExact(count, right.count);
        sum = Math.addExact(sum, right.sum);
        return this;
    }

    Summary snapshot() {
        return new Summary(count, sum);
    }
}
```

With the four-component Gatherer:

```java
static Gatherer<Long, ?, Summary> countAndSum() {
    return Gatherer.<Long, CountState, Summary>of(
            CountState::new,
            Gatherer.Integrator.ofGreedy((state, value, downstream) -> {
                state.add(value);
                return true; // Never self-stops before source ends
            }),
            CountState::merge,
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(state.snapshot());
                }
            }
    );
}
```

Differences from `duplicateEach`:

- `initializer` creates a **separate state** per partition.
- `integrator` only updates state, **emitting nothing during traversal**.
- `combiner` merges count and sum of two states. A merged `CountState` must remain valid for further merging.
- `finisher` emits one `Summary` after accumulation; even on an empty source, if the finisher runs and downstream accepts, output is `Summary(0, 0)`.

The merge operation must satisfy:

```text
identity:      merge(a, empty)           ~ a
associativity: merge(merge(a,b), c)     ~ merge(a, merge(b,c))
```

`~` means **equivalent in result**, not requiring both expressions to return the same object reference. In this `count` and `sum` problem, empty state `(0, 0)` is the identity element; addition over valid `long` ranges is associative. `Math.addExact` throws on overflow so arithmetic errors are never hidden.

### Testing the Combiner Directly

Do not merely run `parallelStream()` on three elements and hope the combiner gets called. The framework may choose few or zero splits. Invoke `merge` **directly** on independent states:

```java
static CountState stateOf(long... values) {
    CountState state = new CountState();
    for (long value : values) {
        state.add(value);
    }
    return state;
}

Summary leftGrouped = stateOf(1, 2)
        .merge(stateOf(3))
        .merge(stateOf(4, 5))
        .snapshot();

Summary rightGrouped = stateOf(1, 2)
        .merge(stateOf(3).merge(stateOf(4, 5)))
        .snapshot();

check(leftGrouped.equals(rightGrouped), "State merge depends on splitting");
check(leftGrouped.equals(new Summary(5, 15)), "Incorrect state merge");
check(stateOf(1, 2).merge(new CountState())
        .snapshot().equals(new Summary(2, 3)), "Incorrect identity");
```

This test catches bugs like forgetting to add `right.count` or `right.sum` even when sequential runs show no issue.

### Testing on Sequential and Parallel Streams

```java
List<Summary> sequential = LongStream.rangeClosed(1, 100)
        .boxed()
        .gather(countAndSum())
        .toList();

List<Summary> parallel = LongStream.rangeClosed(1, 100)
        .parallel()
        .boxed()
        .gather(countAndSum())
        .toList();

check(sequential.equals(List.of(new Summary(100, 5050))),
        "Incorrect sequential sum");
check(parallel.equals(sequential), "Parallel sum differs from sequential");
```

This tests **outputs**, not thread counts, execution order, or combiner invocation counts. Since only one `Summary` is emitted in the finisher after branches are merged, outputs are governed by accumulation and merge contracts.

### Gatherers That CANNOT Simply Merge State

For order-dependent operations like taking "first 3 elements", "consecutive 2-element batches", or "moving averages", you cannot simply have `combiner` concatenate two arbitrary `List`s and expect parallel execution to be right.

For instance, a batch at a branch boundary may need to combine the left branch's remainder with the right branch's head. Unless order, positions, remainders, and associativity are strictly managed, **use `Gatherer.ofSequential`**. Only switch to `Gatherer.of` with a combiner once you have proven the merge is equivalent to processing the whole source in encounter order.

## 9. Complete Self-Check Java 24+ Program

The program below brings together all introduced Gatherers and tests in one file. Save as `GathererVerificationDemo.java`; requires **JDK 24+**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Gatherer;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class GathererVerificationDemo {

    record Summary(long count, long sum) {}

    static final class CountState {
        long count;
        long sum;

        void add(long n) {
            count = Math.addExact(count, 1);
            sum = Math.addExact(sum, n);
        }

        CountState merge(CountState other) {
            count = Math.addExact(count, other.count);
            sum = Math.addExact(sum, other.sum);
            return this;
        }

        Summary snapshot() {
            return new Summary(count, sum);
        }
    }

    static Gatherer<Integer, ?, Integer> duplicateEach() {
        return Gatherer.<Integer, Integer>ofSequential(
                (ignored, value, downstream) -> {
                    if (!downstream.push(value)) {
                        return false;
                    }
                    return downstream.push(value);
                }
        );
    }

    static Gatherer<Integer, ?, List<Integer>> fixedBatches(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }
        return Gatherer.<Integer, List<Integer>, List<Integer>>ofSequential(
                ArrayList::new,
                (buffer, value, downstream) -> {
                    buffer.add(value);
                    if (buffer.size() == size) {
                        List<Integer> batch = List.copyOf(buffer);
                        buffer.clear();
                        return downstream.push(batch);
                    }
                    return true;
                },
                (buffer, downstream) -> {
                    if (!buffer.isEmpty() && !downstream.isRejecting()) {
                        downstream.push(List.copyOf(buffer));
                    }
                }
        );
    }

    static Gatherer<Integer, ?, Integer> takeFirst(int maximum) {
        if (maximum < 0) {
            throw new IllegalArgumentException("negative maximum");
        }
        return Gatherer.<Integer, int[], Integer>ofSequential(
                () -> new int[1],
                (state, value, downstream) -> {
                    if (state[0] >= maximum) {
                        return false;
                    }
                    state[0]++;
                    return downstream.push(value) && state[0] < maximum;
                }
        );
    }

    static Gatherer<Long, ?, Summary> countAndSum() {
        return Gatherer.<Long, CountState, Summary>of(
                CountState::new,
                Gatherer.Integrator.ofGreedy(
                        (state, value, downstream) -> {
                            state.add(value);
                            return true;
                        }),
                CountState::merge,
                (state, downstream) -> {
                    if (!downstream.isRejecting()) {
                        downstream.push(state.snapshot());
                    }
                }
        );
    }

    static CountState stateOf(long... values) {
        CountState state = new CountState();
        for (long value : values) {
            state.add(value);
        }
        return state;
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static void testOutputCounts() {
        check(Stream.<Integer>empty().gather(duplicateEach())
                .toList().isEmpty(), "Empty source");
        check(Stream.of(2, 4, 6).gather(duplicateEach())
                .toList().equals(List.of(2, 2, 4, 4, 6, 6)),
                "Duplication count/content");

        List<List<Integer>> batches = Stream.of(1, 2, 3, 4, 5)
                .gather(fixedBatches(2))
                .toList();
        check(batches.equals(List.of(
                List.of(1, 2), List.of(3, 4), List.of(5))),
                "Final batch");
        check(Stream.<Integer>empty()
                .gather(fixedBatches(2)).toList().isEmpty(),
                "Empty source batches");
    }

    static void testLaziness() {
        AtomicInteger visited = new AtomicInteger();
        Stream<Integer> pipeline = IntStream.rangeClosed(1, 4)
                .boxed()
                .map(n -> {
                    visited.incrementAndGet(); // Measured in test
                    return n;
                })
                .gather(duplicateEach());

        check(visited.get() == 0, "Traversed before terminal");
        check(pipeline.toList().equals(
                List.of(1, 1, 2, 2, 3, 3, 4, 4)),
                "Lazy pipeline result");
        check(visited.get() == 4, "Wrong number of elements traversed");
    }

    static void testShortCircuit() {
        check(Stream.iterate(1, n -> n + 1)
                .gather(takeFirst(3))
                .toList().equals(List.of(1, 2, 3)),
                "Integrator did not stop early");
        check(Stream.of(1, 2, 3)
                .gather(takeFirst(0)).toList().isEmpty(),
                "Take 0 elements");
        check(Stream.iterate(1, n -> n + 1)
                .gather(duplicateEach())
                .limit(3)
                .toList().equals(List.of(1, 1, 2)),
                "Did not honor downstream limit");
    }

    static void testStateCombiner() {
        Summary left = stateOf(1, 2)
                .merge(stateOf(3))
                .merge(stateOf(4, 5))
                .snapshot();
        Summary right = stateOf(1, 2)
                .merge(stateOf(3).merge(stateOf(4, 5)))
                .snapshot();

        check(left.equals(right), "Combiner is not associative");
        check(left.equals(new Summary(5, 15)), "Combiner dropped data");
        check(stateOf(1, 2).merge(new CountState())
                .snapshot().equals(new Summary(2, 3)),
                "Incorrect identity element");

        List<Summary> sequential = LongStream.rangeClosed(1, 100)
                .boxed().gather(countAndSum()).toList();
        List<Summary> parallel = LongStream.rangeClosed(1, 100)
                .parallel().boxed().gather(countAndSum()).toList();

        check(sequential.equals(List.of(new Summary(100, 5050))),
                "Sequential sum");
        check(parallel.equals(sequential),
                "Parallel sum differs from sequential");
        check(Stream.<Long>empty().gather(countAndSum()).toList()
                .equals(List.of(new Summary(0, 0))),
                "Finisher with empty source");
    }

    public static void main(String[] args) {
        testOutputCounts();
        testLaziness();
        testShortCircuit();
        testStateCombiner();
        System.out.println("ALL GATHERER TESTS PASS");
    }
}
```

On JDK 24+ this can be compiled and run directly:

```text
javac GathererVerificationDemo.java
java GathererVerificationDemo
```

Expected output when all checks pass:

```text
ALL GATHERER TESTS PASS
```

In the program, `check` throws `AssertionError` on failure so it does not depend on the `-ea` flag of `java`. This section provides **test code for learners**, without claiming the program was compiled/executed during authoring.

## 10. Common Mistakes When Testing Gatherers

| Mistake | Why It Is Dangerous | Testing / Fixing Approach |
| --- | --- | --- |
| Assuming each input emits exactly one output | Gatherer can duplicate, filter, batch, or emit from finisher | Check both counts and contents with sample data and empty sources. |
| Calling `push` again after downstream returned `false` | Wastes work, breaks short-circuit intent | Return `false` immediately and test with `limit`. |
| Using `Integrator.Greedy` for a gatherer stopping after N elements | Violates contract; runtime may ignore stop signal | Use regular integrator when proactively short-circuiting. |
| Forgetting to emit partial batch in finisher | Loses trailing elements | Test input sizes 0, 1, exact multiples, and multiple + 1. |
| Pushing mutable buffer then calling `clear()` | Previously emitted results get mutated | Emit an independent copy; inspect batch lists. |
| Inferring from `count()` that `peek` always runs | Some operations allow eliding stages that do not affect outcome | Verify laziness via results, never use side effects as contract. |
| Only running `parallel()` without testing combiner | Small sources may not split into branches | Directly test identity/associativity and compare sequential/parallel. |
| Letting multiple branches share mutable state | Races, lost data, flaky outputs | `initializer` creates independent state; merge only via combiner. |
| Using subtraction or average of averages as combiner | Yields different results under different splits | Merge sufficient statistics, such as `sum` and `count`. |
| Asserting a fixed callback count during parallel runs | Scheduling/splitting are implementation details | Test outputs and invariants, never force call schedules. |
| Testing infinite sources without a timeout | A broken early stop can hang the suite | Set a timeout in the test runner; include finite cases for diagnosis. |

## 11. Extension Exercises

**Exercise 1 — Testing 0, 1, N Outputs.** Write a Gatherer dropping negative numbers (`0` outputs for negative), keeping non-negative (`1` output), and then change it to duplicate positive numbers (`2` outputs). Given `[-2, 0, 3]`, determine outputs by hand and verify with `toList()`.

Hint: in the integrator, you can skip calling `push` when filtering out an element; however, if you emit nothing and still want the next element, return `true`.

**Exercise 2 — Boundary Batches.** For `fixedBatches(3)`, test sources with `0`, `1`, `3`, `4`, `6` elements. Predict batch counts and elements in each batch. Why is checking `count()` alone insufficient?

**Exercise 3 — Early Termination.** Replace `takeFirst(N)` with `takeUntilInclusive(predicate)`: emit up to and including the first element matching the predicate, then stop. For `[1, 3, 5, 6, 8]` and an even-number predicate, output must be `[1, 3, 5, 6]`.

```java
static Gatherer<Integer, ?, Integer> takeUntilEven() {
    return Gatherer.<Integer, Integer>ofSequential(
            (ignored, n, downstream) ->
                    downstream.push(n) && n % 2 != 0
    );
}
```

**Exercise 4 — Broken State Merging.** Try replacing `CountState::merge` with one that only keeps `left`. Predict why sequential execution can still pass while parallel execution can fail; write a **direct** test to guarantee catching the bug even when the framework does not split the source.

**Exercise 5 — Testing Empty Sources.** Compare `Stream.empty().gather(duplicateEach())` with `Stream.empty().gather(countAndSum())`: why is the first empty while the second can contain `Summary(0, 0)`? Hint: `finisher` decides whether to emit an aggregate value for an empty source.

**Exercise 6 — Parallelizability.** Design a Gatherer computing `min`, `max`, `count` of integers. Specify state for an empty group, identity merging, and associativity, then test with 1,000 numbers in both sequential and parallel modes.

## 12. Takeaways

- Gatherers are not restricted to a 1:1 ratio: test **empty input, 0/1/many outputs per element, and the finisher**.
- `gather` is an intermediate operation: pipelines remain lazy until a terminal operation. Never turn `peek` or observable side effects into a business correctness requirement.
- `Integrator.integrate` returns `false` to stop receiving more elements; `Downstream.push` returns `false` when downstream wants no more. **Always propagate stop signals** and avoid pushing after rejection.
- A Gatherer with a combiner must use independent state and a merge satisfying **identity/associativity**; test the merge directly before comparing sequential/parallel results.
- Never write tests depending on thread count, combiner call count, or fixed prefetch amounts; test **values, order, output counts, and completion** on representative data.

**API References:** [Gatherer (JDK 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html), [Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html), and [Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html).
