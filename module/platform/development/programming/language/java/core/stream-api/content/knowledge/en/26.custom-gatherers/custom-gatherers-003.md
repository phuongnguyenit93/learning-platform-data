# Emitting Results via Downstream.push and Handling Rejection Signals

In the **Building Custom Gatherers** chapter of the **Java Stream API**, `Gatherer` extends the declarative data-processing model beyond the familiar `filter`, `map`, `flatMap`, `reduce`, and `collect` operations. A gatherer can emit **zero, one, or multiple result elements** per input element, maintain state across incoming elements, and proactively terminate source consumption.

The core focus of this lesson is **`Gatherer.Downstream.push(result)`**. When a gatherer wants to pass a result to the next stage of the pipeline, it calls `push` and receives a `boolean` signal indicating whether downstream **still wants to receive more elements**. This signal must be handled properly, especially when downstream contains `limit`, `findFirst`, `takeWhile`, or another gatherer that can stop early.

If rejection signals are ignored, the gatherer may continue producing useless results or consuming input unnecessarily. If `false` is misunderstood as "the element just pushed was rejected", the program may try to re-emit elements, produce duplicate outputs, or violate the termination contract. This lesson builds from small examples to gatherers emitting multiple elements, packaging buffers, handling `finisher`, and choosing the right integrator.

> **JDK Requirement:** Stream Gatherers are an official API starting in **Java 24** (JEP 485); they previously appeared as preview features in Java 22 and 23. Complete examples in this lesson target **JDK 24+**, and are not present in standard Java 8, 11, 17, or 21. Running examples on JDK 24+ does not require enabling preview.

## 1. Position of Downstream in a Gatherer

A pipeline might look like this:

~~~java
List<Integer> result = Stream.of(1, 2, 3)
        .gather(myGatherer())
        .limit(3)
        .toList();
~~~

If `myGatherer()` emits two results per input element, the final result may be capped at three elements. The gatherer needs to know when **the next stage no longer needs additional results**.

Data flow diagram:

~~~text
Source Stream<T>
      |
      v
  Gatherer<T, A, R>
      |
      +-- initializer(): creates state A (if needed)
      |
      +-- integrator(state, T, downstream)
      |        |
      |        +---- downstream.push(R)
      |                    |
      |                    v
      |               Next stage
      |           (limit / map / collect ...)
      |                    |
      |               boolean
      |              /       \
      |            true      false
      |        accept more   no more wanted
      |
      +-- finisher(state, downstream) (if any)
~~~

Four components make up the general contract of `Gatherer<T, A, R>`:

| Component | Function | Must you write it yourself? |
| --- | --- | --- |
| `initializer` | Creates accumulation state `A` | No, a stateless gatherer can use convenience factories |
| `integrator` | Processes one element `T`; optionally pushes results `R` | Yes, it is the core processing logic |
| `combiner` | Merges states during parallel execution | No; sequential gatherers need not support merging |
| `finisher` | Processes remaining data when the source ends | No; only used when final emissions or state cleanup are needed |

`Downstream<? super R>` is an object representing **the next stage in the pipeline**, not an application-created `List` or `Consumer`. A gatherer can call `push` multiple times during a single integrator invocation, or not at all.

## 2. The Exact Contract of Downstream.push

In Java 24, the `Gatherer.Downstream<T>` interface has two related operations:

~~~java
boolean push(T element);

default boolean isRejecting();
~~~

Meaning of `push(element)`:

- The gatherer **offers `element`** to downstream.
- If the result is `true`, downstream **can still accept more** results.
- If the result is `false`, downstream **does not want any more results**; subsequent `push` calls on the same downstream will continue returning `false`.
- **Do not infer that the element just passed was dropped** solely because `push` returned `false`. Downstream may have accepted that element, and that exact element may have been the final one satisfying a limit.
- Once `false` has been received, the gatherer should **stop creating/pushing more elements**, while propagating the stop signal upstream if there is nothing further to consume.

For example, with `limit(3)`: downstream may accept the third element and then return `false` because three elements have now been reached. If the gatherer assumes the third element was not sent and tries to send it again, it is misinterpreting the signal.

| Result of `push(value)` | Interpretation | Typical Action |
| --- | --- | --- |
| `true` | Can still pass **more** results | Continue logic if more outputs or inputs remain |
| `false` | Downstream needs no more results | Stop emitting further, signal upstream not to continue |
| `false` on the first push | Downstream needs no more after this one | Do not assume the first value was lost |
| Continuing to call after `false` | Subsequent calls also return `false` | Avoid as it only creates wasted work |

A subtle point: `push` is not a protocol meaning "confirmed written to database" or "the sent element definitely exists in a list". It is a **signal of downstream demand**. If the next stage is a filter, the element may be inspected and then filtered out; if it is `limit`, the element just inspected may be the last one.

## 3. The Integrator's Boolean Differs from Push's Boolean

The integrator has the contract:

~~~java
boolean integrate(
        A state,
        T element,
        Gatherer.Downstream<? super R> downstream);
~~~

The boolean that the **integrator returns to the runtime** means:

- `true`: the integrator still wants to receive the **next input element**.
- `false`: the integrator wants to **stop receiving further input elements**; the gather operation can terminate early.

The two signals are often related, yet not identical:

~~~text
downstream.push(output) -> false
       |
       v
Integrator should return false
       |
       v
Runtime stops supplying new inputs to the gatherer
~~~

However, an integrator can also **proactively return false** due to its own business condition, even before downstream rejects. For example, a gatherer stops on its own after hitting a marker or emitting `N` elements.

Case where no element is emitted:

~~~java
if (!shouldEmit(element)) {
    return true; // Skip an output, yet keep receiving next input.
}
~~~

Case where one element is emitted and there is no custom stop policy:

~~~java
return downstream.push(transform(element));
~~~

This directly forwards downstream's demand signal upstream. **Do not automatically `return false` merely because no result was emitted**: doing so stops the whole source instead of filtering a single element.

## 4. Small Example: Emitting One Value and Forwarding the Signal

A stateless gatherer can be created with `Gatherer.ofSequential`:

~~~java
import java.util.stream.Gatherer;

static Gatherer<Integer, Void, Integer> plusOne() {
    return Gatherer.<Integer, Integer>ofSequential(
            Gatherer.Integrator.of(
                    (unused, value, downstream) ->
                            downstream.push(value + 1)
            )
    );
}
~~~

Type meanings:

- Input `T = Integer`.
- No business state needed, so state type `A = Void`.
- Output `R = Integer`.
- `ofSequential` selects sequential evaluation suitable for this demonstration.
- `Integrator.of(...)` creates an integrator capable of propagating stop signals.

Usage:

~~~java
List<Integer> values = Stream.of(1, 2, 3)
        .gather(plusOne())
        .toList();

// [2, 3, 4]
~~~

If downstream limits output:

~~~java
List<Integer> values = Stream.of(1, 2, 3)
        .gather(plusOne())
        .limit(1)
        .toList();

// [2]
~~~

After `2` is pushed downstream and `limit(1)` has enough results, `push` may return `false`; the integrator returns `false` back to the runtime to stop fetching from the source. Do not add side effects inside `plusOne` and assert that every element of the source Stream was definitely processed.

## 5. Emitting Multiple Results: Check After Every push

For example, each integer generates two results: the number itself and ten times the number.

~~~java
static Gatherer<Integer, Void, Integer> expand() {
    return Gatherer.<Integer, Integer>ofSequential(
            Gatherer.Integrator.of(
                    (unused, value, downstream) -> {
                        if (!downstream.push(value)) {
                            return false;
                        }
                        return downstream.push(value * 10);
                    }
            )
    );
}
~~~

With source `[1, 2, 3]`:

~~~java
List<Integer> expanded = Stream.of(1, 2, 3)
        .gather(expand())
        .toList();

System.out.println(expanded);
// [1, 10, 2, 20, 3, 30]
~~~

When adding `limit(3)`:

~~~java
List<Integer> firstThree = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(3)
        .toList();

System.out.println(firstThree);
// [1, 10, 2]
~~~

Logical sequence in sequential execution:

~~~text
Input 1:
  push(1)   -> downstream still wants more
  push(10)  -> downstream still wants more

Input 2:
  push(2)   -> downstream has 3 results; may return false
  DO NOT push(20)
  NO NEED to fetch input 3
~~~

**Do not write**:

~~~java
// Violates rejection protocol: keeps pushing after being rejected.
downstream.push(value);
downstream.push(value * 10);
return true;
~~~

With early rejection downstream, the final output might still look "right" because subsequent `push` calls are ignored, yet the gatherer performed unnecessary work and kept pulling input for no reason. If generating outputs involves I/O or heavy computation, this cost is significant.

Use this pattern:

~~~java
if (!downstream.push(firstOutput)) {
    return false;
}

return downstream.push(secondOutput);
~~~

If there are `N` outputs in a loop, check the result of **every** `push` and exit immediately upon encountering `false`.

## 6. Complete Runnable Java 24+ Example: Multi-Emit, Downstream Stop, and Proactive Stop

The program `DownstreamPushDemo.java` below demonstrates both possibilities: downstream rejecting via `limit` and a gatherer stopping on its own after emitting a configured count.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class DownstreamPushDemo {

    static Gatherer<Integer, Void, Integer> expand() {
        return Gatherer.<Integer, Integer>ofSequential(
                Gatherer.Integrator.of(
                        (unused, number, downstream) -> {
                            if (!downstream.push(number)) {
                                return false;
                            }
                            return downstream.push(number * 10);
                        }
                )
        );
    }

    static final class Counter {
        int emitted;
    }

    static Gatherer<Integer, Counter, Integer> takeAtMost(int max) {
        if (max < 0) {
            throw new IllegalArgumentException(
                    "max must be non-negative");
        }

        return Gatherer.<Integer, Counter, Integer>ofSequential(
                Counter::new,
                Gatherer.Integrator.of(
                        (state, number, downstream) -> {
                            if (state.emitted >= max) {
                                return false;
                            }

                            state.emitted++;
                            boolean wantsMore = downstream.push(number);

                            // Stop if the Gatherer itself reaches the limit
                            // OR downstream needs no more data.
                            return wantsMore && state.emitted < max;
                        }
                )
        );
    }

    public static void main(String[] args) {
        List<Integer> all = Stream.of(1, 2, 3)
                .gather(expand())
                .toList();

        List<Integer> limitedDownstream = Stream.of(1, 2, 3)
                .gather(expand())
                .limit(3)
                .toList();

        List<Integer> limitedGatherer = Stream.of(1, 2, 3, 4)
                .gather(takeAtMost(2))
                .toList();

        System.out.println(all);
        System.out.println(limitedDownstream);
        System.out.println(limitedGatherer);
    }
}
~~~

Output:

~~~text
[1, 10, 2, 20, 3, 30]
[1, 10, 2]
[1, 2]
~~~

Run on JDK 24+:

~~~bash
javac --release 24 DownstreamPushDemo.java
java DownstreamPushDemo
~~~

Distinguish the two scenarios in the code:

- `limitedDownstream`: `expand` **does not know** the three-result limit itself. It knows to stop when `push` returns `false` due to `limit(3)` downstream.
- `limitedGatherer`: `takeAtMost(2)` **proactively stops** after emitting two elements, even if downstream is still ready for more.

**Note on `max == 0`:** the `takeAtMost(0)` gatherer emits nothing, yet the runtime may need to pass one input element into the integrator for it to realize it must return `false`. If the requirement is **zero consumption of any upstream element** when the limit is 0, use `stream.limit(0)` or branch before starting the pipeline; do not claim this gatherer example has the zero-consumption property.

## 7. Filtering Elements: Not Pushing Does Not Mean Stopping

A gatherer can decide to emit nothing for an input, similar to `filter`. When skipping an element without a reason to stop, the integrator must return `true`.

~~~java
static Gatherer<Integer, Void, Integer> evenOnly() {
    return Gatherer.<Integer, Integer>ofSequential(
            Gatherer.Integrator.of(
                    (unused, number, downstream) -> {
                        if (number % 2 != 0) {
                            return true;
                        }
                        return downstream.push(number);
                    }
            )
    );
}
~~~

Usage:

~~~java
List<Integer> evens = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(evenOnly())
        .toList();

System.out.println(evens); // [2, 4, 6]
~~~

If you wrote `return false` for the first odd number, the pipeline could stop immediately upon seeing `1` and never reach `2`, `4`, or `6`.

| Behavior inside integrator | Typically correct return value |
| --- | --- |
| Skip current element yet still want to read more | `true` |
| Push an element; downstream still accepts more | `true` from `push` |
| Push an element; downstream rejects more | `false` from `push` |
| Gatherer's own termination condition reached | `false` |
| No output yet and termination condition not reached | `true` |

**Design rule:** Ask "do I still need the **next source element**?" to choose the integrator's boolean. Ask "does the next stage still want the **next output**?" to interpret `push`'s boolean.

## 8. Distinguishing Integrator.of and Integrator.ofGreedy

Java provides:

~~~java
Gatherer.Integrator.of(integrator)

Gatherer.Integrator.ofGreedy(greedyIntegrator)
~~~

`Integrator.of` allows the integrator to **initiate short-circuiting itself** by returning `false`, even when downstream has not rejected.

`Integrator.ofGreedy` describes an integrator that **never stops reading the source on its own**. It may return `false` to **propagate downstream's rejection**, but must not stop on its own due to a private business condition. This information helps the implementation optimize the pipeline accordingly.

Example of an integrator that filters blank values yet still traverses to the end of the source (unless downstream asks to stop):

~~~java
static Gatherer<String, Void, String> nonBlank() {
    return Gatherer.<String, String>ofSequential(
            Gatherer.Integrator.ofGreedy(
                    (unused, text, downstream) -> {
                        if (text.isBlank()) {
                            return true;
                        }
                        return downstream.push(text);
                    }
            )
    );
}
~~~

Because this example uses Java 24+, `String.isBlank()` (Java 11+) is available.

Do not use `ofGreedy` for the `takeAtMost` gatherer in section 6. That gatherer **can return false because its own limit is reached**, even when downstream is still willing to receive, so it does not satisfy the "greedy" promise.

Note: "greedy" does not mean **must emit at least one result per input**. A greedy integrator can filter elements out, accumulate in a buffer, or emit multiple elements; it simply does not initiate stopping input consumption on its own.

## 9. isRejecting: When It Is Needed and Guarantee Limits

Besides `push`, downstream has the method:

~~~java
boolean isRejecting();
~~~

It indicates whether downstream **is known to be rejecting** further elements. This is a **best-effort** mechanism:

- When `isRejecting()` returns `true`, downstream is already known to need no more data.
- When it returns `false`, **you must not infer with certainty** that downstream will accept every subsequent `push`. The interface allows default implementations to always return `false`.
- During normal processing, the return value of `push` is the direct source of truth to check.
- Once `push` has returned `false`, later `push` calls on the same downstream also return `false`; avoid redundant calls.

`isRejecting` is especially useful in the **finisher**, because the finisher may be called after accumulation ends when downstream no longer wants additional output.

Example:

~~~java
(state, downstream) -> {
    if (!state.pending.isEmpty() && !downstream.isRejecting()) {
        downstream.push(List.copyOf(state.pending));
    }
}
~~~

This code checks upfront to avoid leftover emission work **when downstream is already known** to be rejecting. However, `isRejecting()` returning `false` is still only a best-effort signal; if emitting multiple outputs in the finisher, check the `push` result after each emission.

**Do not use `isRejecting` as a replacement for checking `push`**, or use it like a synchronization lock across threads. It is a pipeline demand notification mechanism, not a thread coordination API.

## 10. Finisher Emitting Remaining Items: Check Downstream Before Pushing

Stateful gatherers often accumulate part of the data before emitting results. For example, grouping every **two** numbers into a list; when the source ends with an odd number left over, the finisher emits the final group.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class BatchGathererDemo {

    static Gatherer<Integer, ArrayList<Integer>, List<Integer>>
    batchesOf(int size) {

        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }

        return Gatherer.<Integer, ArrayList<Integer>, List<Integer>>
                ofSequential(
                    ArrayList::new,
                    Gatherer.Integrator.of(
                            (buffer, value, downstream) -> {
                                buffer.add(value);

                                if (buffer.size() < size) {
                                    return true;
                                }

                                // Copy before clearing so the mutable
                                // buffer does not leak externally.
                                List<Integer> batch = List.copyOf(buffer);
                                buffer.clear();

                                return downstream.push(batch);
                            }
                    ),
                    (buffer, downstream) -> {
                        // A partial group smaller than size may remain.
                        // Avoid emitting if downstream is known to reject.
                        if (!buffer.isEmpty() &&
                                !downstream.isRejecting()) {
                            downstream.push(List.copyOf(buffer));
                        }
                    }
                );
    }

    public static void main(String[] args) {
        List<List<Integer>> all = Stream.of(1, 2, 3, 4, 5)
                .gather(batchesOf(2))
                .toList();

        List<List<Integer>> onlyOne = Stream.of(1, 2, 3, 4, 5)
                .gather(batchesOf(2))
                .limit(1)
                .toList();

        System.out.println(all);     // [[1, 2], [3, 4], [5]]
        System.out.println(onlyOne); // [[1, 2]]
    }
}
~~~

With a five-element list, the integrator emits two full-sized groups `[1,2]`, `[3,4]`, and then the finisher emits `[5]`. The computation does not need to hold the entire source, only a buffer of at most `size` elements during accumulation.

With `limit(1)`, downstream only needs `[1,2]`. `push([1,2])` may return `false`; the integrator returns `false`, so the source does not need to be consumed further for the gatherer. If the finisher is invoked after a stopped pass, it must not attempt to emit unnecessary extra groups.

**Important technical detail:** `List.copyOf(buffer)` creates an unmodifiable output list; therefore the subsequent `buffer.clear()` does not alter already-emitted groups. This approach only accepts non-`null` elements; the example uses valid `Integer` values.

The implementation above prioritizes illustrating **the downstream protocol and buffer ownership**. If a system needs efficient parallel batching while preserving encounter-order boundaries, you must additionally design combiner semantics and state-merging rules — not merely replace `ofSequential` with `of`.

## 11. Do Not Retain a Downstream Reference for Later Calls

A `Gatherer.Downstream` object is only valid within **the scope of the callback invocation** supplied by the implementation. Never store it in a field for use on another thread, in an async callback, in a background task, or after `integrate`/`finisher` has returned.

**Wrong idea:**

~~~java
// Do not do this inside gatherer state:
state.savedDownstream = downstream;

// ... or pass downstream to another task and call push later.
~~~

Reasons:

1. The API does not grant long-lived ownership of downstream.
2. The runtime may change execution state and stop the pipeline after the callback ends.
3. Retaining downstream and accessing it from another thread breaks Gatherer's partitioning and combining assumptions.
4. Rejection signals may have changed; late emissions no longer have a valid contract.

If asynchronous processing is required, design dedicated queueing, cancellation, lifecycle, and coordination mechanisms tailored to the application. Never turn `Gatherer.Downstream` into an arbitrary multi-threaded async push API.

## 12. One Input Producing Multiple Outputs: Avoid Waste After Rejection

Suppose each event needs to produce multiple result strings:

~~~java
static Gatherer<String, Void, String> variants() {
    return Gatherer.<String, String>ofSequential(
            Gatherer.Integrator.of(
                    (unused, value, downstream) -> {
                        String normalized = value.trim();

                        if (!downstream.push(normalized)) {
                            return false;
                        }

                        String upper = normalized.toUpperCase(
                                java.util.Locale.ROOT);
                        return downstream.push(upper);
                    }
            )
    );
}
~~~

The optimization here is not only avoiding the second `push`. We also **avoid computing `upper` if downstream already had enough results after `normalized`**. When generating outputs is CPU-intensive, allocates many objects, or calls an expensive operation, this ordering matters.

If you do not know upfront how many results downstream needs, do not build a `List` of thousands of variants first before attempting to push. Generate each value lazily and check `push` immediately, provided that generation obeys the contract and does not depend on abandoned side effects.

Example pattern when each element has a collection of sub-results:

~~~java
for (String candidate : candidates) {
    if (!downstream.push(candidate)) {
        return false;
    }
}
return true;
~~~

For sub-sources from I/O or resource-backed `Stream`s, close those resources in the proper scope even when encountering `push == false` and returning early. `push` does not automatically close `Files.lines`, `Scanner`, or HTTP cursors opened in user code.

## 13. Distinguishing Rejection, Short-Circuiting, and Exceptions

The following scenarios are not the same:

| Scenario | Signal / Behavior | Interpretation |
| --- | --- | --- |
| Downstream has enough output | `push(...) == false` | No need to push more |
| Gatherer reaches its own threshold | `integrator returns false` | No need to pull next input |
| An input is filtered out | No push; `integrator returns true` | Continue processing other inputs |
| Mapper or integrator throws an exception | Pipeline fails | Report error and release resources per lifecycle |
| Finisher has data when downstream is rejecting | `isRejecting()` may be true | Do not try to emit excess values |
| Terminal completes normally | Result is produced | Does not imply I/O Streams auto-close |

A gatherer **must not treat downstream rejection as an error** and throw an exception just because `push` returns `false`. That is usually **normal termination** when the pipeline already has enough data.

Conversely, if a transformation function cannot process data due to a business error, never mask the error by doing `return false`: the caller would interpret the pipeline as having **completed normally**, potentially publishing incomplete results. Use explicit error reporting if it is a failure.

## 14. Behavior with limit(0), findFirst, takeWhile, and Chained Downstream

A custom gatherer cannot assume the terminal operation always traverses the entire source.

### `limit(0)`

~~~java
List<Integer> none = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(0)
        .toList();

// []
~~~

Downstream already knows it needs zero outputs. The runtime may optimize by never calling the integrator; never rely on the `integrate` callback always running at least once.

### `findFirst`

~~~java
int first = Stream.of(1, 2, 3)
        .gather(expand())
        .findFirst()
        .orElseThrow();

// 1
~~~

Once the first result satisfies the requirement, downstream needs no more. The gatherer should not generate a second output or read later inputs just to serve an already-completed terminal operation.

### `takeWhile`

~~~java
List<Integer> prefix = Stream.of(1, 2, 3, 4)
        .gather(expand())
        .takeWhile(n -> n < 15)
        .toList();

// [1, 10, 2]
~~~

The logical sequence after the gatherer is `[1,10,2,20,3,30,4,40]`. `takeWhile(n -> n < 15)` stops at `20`, keeping only `[1,10,2]`. The value `20` **is not in the result**, yet it was delivered to downstream to evaluate the predicate. This illustrates why `push` returning `false` **does not tell you whether the pushed element belongs in the final result** — that depends on downstream steps.

### Gatherer Chained into Another Gatherer

~~~java
List<Integer> result = Stream.of(1, 2, 3, 4)
        .gather(expand())
        .gather(takeAtMost(3))
        .toList();

// [1, 10, 2]
~~~

Stop signals can propagate across multiple layers: the `takeAtMost(3)` gatherer stops accepting after three results, preventing the upstream `expand` gatherer from generating more. Do not assume each gatherer operates independently with respect to consumption demand.

## 15. Parallelization and Rejection Signals: Do Not Promise What the API Doesn't

Examples in this lesson use `Gatherer.ofSequential` to demonstrate clear behavior on ordered sources. When the source calls `parallel()`, correctness also depends on the gatherer kind and state-combining contract.

- A gatherer with `defaultCombiner()` is evaluated under Gatherer's sequential mechanism, and **does not become effectively parallel** just because upstream called `parallel()`.
- To parallelize a stateful gatherer, design partition-independent `initializer` and a valid `combiner`, especially when output depends on encounter order.
- For short-circuiting gatherers, the runtime must manage partitions and outputs according to Stream/Gatherer contracts. **Do not assume callback counts, callback order, or side effects match a sequential loop**.
- `push == false` still means "downstream wants no more"; do not assume every upstream task in other partitions stops instantaneously.
- Lambdas calling `push` must finish within their invocation scope; do not save downstream to push from another thread.
- Avoid side effects requiring exactly-once or transactional execution inside an integrator; short-circuiting and parallelism make side-effect counts hard to predict.

In practice, start with a contract-correct sequential gatherer, measure, and only then consider parallel combiner designs. A gatherer returning the right `List` on 10 elements is not proof of parallel safety on millions of records.

## 16. I/O Resources and Early Cancellation

When upstream reads a file via `Files.lines`, early downstream rejection **does not close the source automatically**. Use `try-with-resources`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<Integer> firstNumbers(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {

        return lines.map(Integer::parseInt)
                .gather(expand())
                .limit(3)
                .toList();
    }
}
~~~

Here `expand()` is the method in the same class as the `DownstreamPushDemo` example. If placed in another class, qualify with the class name or pass the Gatherer in from outside.

`limit(3)` enables the pipeline to stop early, yet **`Files.lines` still needs to be closed** upon exiting the `try` block. If `Integer.parseInt` throws `NumberFormatException`, `try-with-resources` still calls `close()` before propagating the exception.

If an integrator opens a separate resource per input, do not wait for an `onClose` callback that may not be invoked as you expect. Manage each resource inside `try-with-resources` or design clear resource ownership. Downstream rejection is a mechanism to end **data demand**, not a file/transaction closing mechanism.

## 17. Common Mistakes and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Pipeline keeps processing inputs after `limit` is satisfied | Integrator ignores `push == false` and always does `return true` | Immediately return `false` when downstream rejects |
| Emits superfluous second value in one-to-many gatherer | Does not check result of the first `push` | Check after each `push`, use early return |
| `return false` for a filtered-out element | Confuses "do not emit" with "stop reading source" | Do not push and `return true` |
| Missing last element when `push` returns `false` | Misunderstands `push == false` as rejecting the pushed value itself | Do not re-emit; boolean is about accepting *more* |
| Finisher emits an extra batch after `limit` was met | Does not check downstream state | Use best-effort `isRejecting`, avoid emitting when known rejecting |
| `isRejecting() == false` yet `push` returns `false` | `isRejecting` is only best-effort | Rely on `push` return value to decide stopping |
| `ofGreedy` proactively stops on its own threshold | Violates greedy contract | Use `Integrator.of` for custom short-circuiting |
| Previously emitted result mutates when new batch forms | Pushed reference to mutable buffer then called `clear()` | Copy a snapshot before pushing |
| Another thread calls `push` after callback ended | Stored Downstream in state or async task | Use Downstream only within callback scope |
| I/O handle stays open after `findFirst` | Short-circuiting does not close sources | Use `try-with-resources` |
| Switching to parallel makes order/performance unpredictable | Missing combiner design and encounter-order handling | Start with `ofSequential`; design parallelism separately if needed |
| Reporting errors by doing `return false` | Confuses normal completion with business failure | Throw/record errors using proper application mechanisms |

## 18. Gatherer Testing Strategy

A good test suite must verify both **output values** and **stop-emitting/stop-consuming behavior**:

1. **Empty source:** emits no results when there is no input; finisher only emits if there is data to finalize.
2. **One input → one output:** `push` is forwarded properly.
3. **One input → multiple outputs:** preserves output order in sequential pipelines with encounter order.
4. **One input → zero outputs:** does not accidentally stop the entire source.
5. **`limit(0)`, `limit(1)`, `limit(k)`:** does not emit more than downstream requires.
6. **`findFirst`, `takeWhile`:** returns the exact first element/prefix without generating needless extra outputs after rejection.
7. **Self-stopping gatherer:** stops upon its own condition without waiting for downstream rejection.
8. **Finisher with buffer:** emits remainder when appropriate, does not emit extra when downstream already has enough.
9. **Failing inputs or I/O:** exceptions are not silently turned into fake success; sources are closed.
10. **State/parallel:** does not share mutable state or retain downstream beyond callback scope.

Examples of simple checks on JDK 24+:

~~~java
List<Integer> all = Stream.of(1, 2, 3)
        .gather(expand())
        .toList();

List<Integer> limited = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(3)
        .toList();

List<Integer> first = Stream.of(1, 2, 3)
        .gather(expand())
        .limit(1)
        .toList();

if (!all.equals(List.of(1, 10, 2, 20, 3, 30))
        || !limited.equals(List.of(1, 10, 2))
        || !first.equals(List.of(1))) {
    throw new AssertionError("Incorrect gatherer output");
}
~~~

These checks catch wrong outputs, yet **do not by themselves prove** the gatherer avoids wasted internal work. To inspect work done, use a counting mapper **strictly in test code**, or simulate downstream rejection per contract. Never turn observable side effects into part of production logic.

## 19. Practice Exercises

### Exercise 1 — Predict Output and Rejection Signal

~~~java
List<Integer> result = Stream.of(3, 4)
        .gather(expand())
        .limit(3)
        .toList();
~~~

**Answer:** `[3, 30, 4]`. Once three results have been received, downstream needs no more; `push(4)` may return `false`, so the gatherer does not need to call `push(40)`.

### Exercise 2 — Why Is Returning false for a Filtered Element Wrong?

~~~java
if (number % 2 != 0) {
    return false;
}
return downstream.push(number);
~~~

**Answer:** `false` from an integrator means **stop reading further inputs**, not "skip this element". With a source starting with `1`, the gatherer stops before `2`, `4`, and `6`. Use `return true` when skipping an element while still wanting to process the source.

### Exercise 3 — Does Downstream.push Returning false Mean the Pushed Value Was Lost?

**Answer:** No. For example, `limit(1)` may accept the exact value just pushed and then return `false` because it now has enough. Depending on downstream steps, the processed element may be kept or dropped by `filter`/`takeWhile`; the boolean only expresses **demand for further data**.

### Exercise 4 — Choose Integrator.of or ofGreedy?

A gatherer reads numbers until it encounters the first negative number, then stops on its own even if downstream still accepts more. Which should you use?

**Answer:** Use `Integrator.of`. It allows the integrator to return `false` itself due to its own termination condition. `ofGreedy` is only appropriate when the integrator does not initiate short-circuiting on its own.

### Exercise 5 — Why Must the Buffer Be Copied Before push?

~~~java
downstream.push(buffer);
buffer.clear();
~~~

**Answer:** If `buffer` is a mutable `ArrayList`, downstream may keep a reference to that exact object, and `clear()` turns the previously sent result into an empty list. Use `List.copyOf(buffer)` or a separate copy before clearing to avoid mutating emitted output.

### Exercise 6 — When to Use isRejecting?

A finisher holds one leftover element, yet downstream already satisfied `limit(1)`. Should it try to push the final element?

**Answer:** No. You can check `downstream.isRejecting()` to avoid pushing when downstream is already known to be rejecting. However, `isRejecting() == false` does not guarantee downstream still wants data; if emitting multiple elements, check the result of each `push`.

### Exercise 7 — JDK Compatibility

A project running on **Java 21** wants to use official `Stream.gather` without preview. Can it compile/run directly?

**Answer:** No. Gatherer is an official API starting in Java 24; earlier Java 22/23 only had preview versions for their respective releases. On Java 21, upgrade the JDK or implement another solution using existing Stream API/iterators/collectors.

### Exercise 8 — Checking I/O Ownership

~~~java
List<Integer> result = Files.lines(path)
        .map(Integer::parseInt)
        .gather(expand())
        .limit(1)
        .toList();
~~~

**Answer:** The source resource must be managed with `try-with-resources`. `limit(1)` stops early, yet does not automatically call `close()` on the file-reading Stream.

## 20. Takeaways

- `Gatherer.Downstream.push(value)` sends a result to the next stage and returns `true` if downstream **still wants more**, `false` if not.
- `push == false` **is not an assertion that the sent value was discarded**. It is a signal meaning *no more results needed*.
- When emitting multiple results from one input, **check after every `push`**; stop generating/emitting immediately upon rejection.
- The boolean from `integrator.integrate` asks **whether more inputs are needed**; it may return `false` due to downstream rejection or because the gatherer stops itself.
- If not pushing an element while still wanting to read the next input, `return true`, not `false`.
- `Integrator.ofGreedy` is for integrators that do not initiate short-circuiting themselves; it is still allowed to forward `false` from downstream rejection.
- `isRejecting()` is a best-effort signal, useful in the finisher; **the result of `push`** remains what must be checked during emission.
- Never retain a `Downstream` reference beyond callback scope; avoid shared state or schedule-dependent side effects.
- Early termination does not auto-release I/O sources: `try-with-resources` is still required.
- Examples use Stream Gatherers **officially on JDK 24+**, and cannot run as-is on Java 21 or lower.

**Main Takeaway:** `Downstream.push` is the **output demand coordination** mechanism between pipeline layers. A well-written gatherer not only emits results, but also **stops emitting when downstream has enough, propagates stop signals upstream, and distinguishes normal completion from errors**. Getting these principles right ensures multi-emit, batching, and short-circuiting gatherers behave predictably and avoid wasted work.

### API References

- [JDK 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): `push` and `isRejecting` contracts.
- [JDK 24 — Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): meaning of the boolean returned by an integrator.
- [JDK 24 — Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer, integrator, combiner, finisher, and state/downstream ownership.
- [Dev.java — The Gatherer API](https://dev.java/learn/api/streams/gatherers/): examples of early stopping and propagating rejection signals.
