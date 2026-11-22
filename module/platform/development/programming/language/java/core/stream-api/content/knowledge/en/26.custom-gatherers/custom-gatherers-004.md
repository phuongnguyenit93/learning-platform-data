# Distinguishing Regular Integrator and Integrator.ofGreedy

In the Java Stream API, `Gatherer` lets programmers define a custom **intermediate operation** that can receive elements from upstream, maintain state, and emit results downstream. At the center of this mechanism is **`Gatherer.Integrator<A, T, R>`**: a function accepting state `A`, input element `T`, and output sink `Gatherer.Downstream<R>`.

When creating an Integrator, Java provides two factories that are easily confused:

- **`Gatherer.Integrator.of(...)`:** creates a regular Integrator. The Integrator is allowed to **decide on its own to stop receiving more data**, for example when reaching a threshold or seeing a marker.
- **`Gatherer.Integrator.ofGreedy(...)`:** creates an Integrator marked as **`Greedy`**. It promises **never to initiate early termination itself**; if it returns `false`, the sole reason is that downstream does not want any more results.

This difference does not lie in how many elements are emitted. A Greedy Integrator can still **filter out, transform, or emit multiple results** for a single input element. The difference lies in **the authority to end input consumption from upstream** and the Stream's optimization opportunities.

This lesson belongs to the **Building Custom Gatherers** chapter in the **JAVA_STREAM_API** module. The content builds upon lazy pipelines, `filter`, `map`, `reduce`, `collect`, `Spliterator`, state, parallel processing, and resources; the direct goal is to apply the `of` and `ofGreedy` contracts correctly before considering performance.

> **Version:** `Stream.gather`, `Gatherer.Integrator`, and `Integrator.ofGreedy` are official APIs starting in **Java 24** (JEP 485). They were in preview in Java 22 and 23. The examples below are written for **JDK 24 and later** and do not run directly on Java 17/21.

## 1. Position of Integrator in a Gatherer

In a typical pipeline:

```text
Source Stream<T>
      |
      | filter(...) / map(...)           (optional)
      v
  gather(gatherer)
      |
      |  initializer -> creates state A
      |  integrator  -> receives T, updates A, may push R
      |  combiner    -> merges states if splitting is supported
      |  finisher    -> may emit more R at end of source
      v
Stream<R>
      |
      | limit(...) / findFirst() / toList() / collect(...)
      v
Terminal result
```

`Gatherer<T, A, R>` has three types:

| Type | Role | Example |
| --- | --- | --- |
| `T` | Input element | `Integer` |
| `A` | Internal state, may be mutable | `long[]` holding a running sum |
| `R` | Element emitted downstream | `Long` |

Different components of a Gatherer:

| Component | Job |
| --- | --- |
| `initializer()` | Allocates fresh state when needed |
| `integrator()` | Receives each input, updates state, and emits any number of outputs |
| `combiner()` | Combines states if the Gatherer supports parallel processing |
| `finisher()` | Performs end-of-source work, may emit additional outputs |

An `Integrator` is **not** a `Collector`. A Collector usually produces a result in the terminal operation `collect`, whereas a Gatherer is an intermediate stage that can emit multiple results before the entire source ends.

## 2. The Integrator Interface and the Boolean Value

In Java 24, the conceptual signature is:

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

The three parameters and return value mean:

| Component | Meaning |
| --- | --- |
| `state` | The Gatherer state provided by the framework |
| `element` | The current input element |
| `downstream` | The channel for emitting `R` to the next stage |
| `return true` | The Integrator wants to keep being fed elements |
| `return false` | The Integrator wants to **stop receiving further elements** |

Key point: `boolean` does **not** represent "whether this element was selected". An Integrator can **emit zero elements** and still return `true`, or emit one element and return `false` to stop at a boundary.

```text
integrate(state, element, downstream)
        |
        +-- process element / update state
        +-- may call downstream.push(result) multiple times
        |
        +-- true: want more input
        +-- false: request end of input integration
```

For a **regular Integrator**, `false` can come from the Integrator's **own decision** or from a downstream signal. For a **Greedy Integrator**, `false` can only be **the forwarding of downstream's rejection signal**.

## 3. Downstream.push and Downstream.isRejecting

Two methods directly tied to the Integrator contract:

```java
boolean downstream.push(R result);
boolean downstream.isRejecting();
```

- `push(result)` sends one output element to the next stage, **if that stage still accepts it**.
- `push` returns `true` if downstream can keep accepting more, `false` if downstream has rejected.
- After `push` returns `false`, subsequent `push` calls on the same downstream will also be rejected per contract.
- `isRejecting()` is a **best-effort** check of whether downstream is known to be rejecting. Returning `false` is not a permanent guarantee that a future `push` will be accepted.

Example of a valid response:

```java
// One element in -> one element out.
return downstream.push(transformed);
```

When downstream has a terminal operation like `limit(3).toList()`, a `push` call may signal that it wants no more. At that point, the Integrator should honor the signal to avoid wasted work.

A common mistake is:

```java
downstream.push(transformed);
return true; // Ignores the notice that downstream may have rejected.
```

This snippet is not a good way to express an Integrator that always respects downstream. When downstream wants no more, continuing to compute or push new results is wasteful and may consume resources needlessly. With a Greedy Integrator, you **must accurately reflect** downstream's rejection status.

## 4. Regular Integrator: Allowed to Decide Early Termination

Business example: from an event stream, record every event **up to and including** the `"STOP"` marker, then stop reading subsequent events.

```java
import java.util.List;
import java.util.stream.Gatherer;

public class UntilMarkerDemo {

    static Gatherer<String, Void, String> untilMarker(String marker) {
        Gatherer.Integrator<Void, String, String> step =
            Gatherer.Integrator.of(
                (unused, value, downstream) -> {
                    boolean wantsMore = downstream.push(value);

                    // Stop because of marker, even if downstream never rejected.
                    return wantsMore && !value.equals(marker);
                }
            );

        return Gatherer.ofSequential(step);
    }

    public static void main(String[] args) {
        List<String> result = List.of(
                "START", "READY", "STOP", "AFTER", "LATER"
            ).stream()
            .gather(untilMarker("STOP"))
            .toList();

        System.out.println(result); // [START, READY, STOP]
    }
}
```

Notice the line:

```java
return wantsMore && !value.equals(marker);
```

Two distinct causes can make this Integrator return `false`:

1. **Downstream returns `false`** from `push`: downstream wants no more.
2. **Business condition hits the marker**: the Integrator **decides on its own** to stop, even though downstream still wants more.

It is precisely this second cause that makes this Integrator **ineligible to be declared Greedy**.

### 4.1. Early Stopping Does Not Mean Dropping the Current Element

The Integrator above **pushes the marker first**, and only then returns `false`. Thus `"STOP"` is included in the result, while elements after the marker are not received.

If the rule is **exclude the marker**, you can check beforehand:

```java
Gatherer.Integrator<Void, String, String> step =
    Gatherer.Integrator.of((unused, value, downstream) -> {
        if (value.equals("STOP")) {
            return false;  // Do not push the marker.
        }

        return downstream.push(value);
    });
```

These two versions implement two different business contracts.

### 4.2. When Is a Regular Integrator Appropriate?

- Stopping after receiving `k` results, even if downstream has not placed `limit(k)`.
- Stopping when encountering a protocol termination marker.
- Stopping when a metric reaches a threshold and no more input needs to be read.
- Stopping when a parser determines the valid header section has ended.
- Any short-circuit rule **originating from the Gatherer's own logic**.

You can write a regular Integrator that **never** stops on its own. It is still correct; it simply has not declared the Greedy property to the framework.

## 5. What Does `Integrator.ofGreedy` Actually Promise?

`Gatherer.Integrator.Greedy<A, T, R>` is a **subinterface** of `Gatherer.Integrator<A, T, R>`. The factory:

```java
Gatherer.Integrator.ofGreedy(greedyIntegrator)
```

returns an object of type `Gatherer.Integrator.Greedy<A, T, R>`.

The core condition is:

> **A Greedy Integrator never initiates short-circuiting itself. It may stop accepting more data only when downstream has signaled rejection.**

Therefore, the following return patterns fit Greedy:

```java
// Emitted one result: propagate downstream's signal.
return downstream.push(result);

// Emitted nothing, downstream has not rejected.
return true;

// Emitted multiple results: stop if downstream rejects.
for (R result : results) {
    if (!downstream.push(result)) {
        return false;
    }
}
return true;
```

Conversely, the following form **violates** the Greedy promise:

```java
// Invalid for ofGreedy: self-stops due to a business rule.
return downstream.push(result) && !conditionForStop;
```

Here `conditionForStop` can cause the Integrator to return `false` **even when `push` just returned `true`**. In that case, termination originates from the Integrator's own decision — the exact thing Greedy promises never to do.

### 5.1. Greedy Does Not Mean "Emit Every Element"

Greedy describes **willingness to keep receiving from upstream**, not a requirement to retain every element.

Example of a Greedy Integrator that emits only even numbers:

```java
import java.util.stream.Gatherer;

Gatherer.Integrator.Greedy<Void, Integer, Integer> evenStep =
    Gatherer.Integrator.ofGreedy(
        (unused, number, downstream) -> {
            if (number % 2 == 0) {
                return downstream.push(number);
            }

            return true; // Skip odd element, keep receiving next element.
        }
    );

Gatherer<Integer, Void, Integer> onlyEven = Gatherer.of(evenStep);
```

`onlyEven` behaves similarly to `filter(n -> n % 2 == 0)`. The Integrator does not push odd numbers, yet **does not** stop the Stream when it sees an odd number.

In production code, prefer `filter` if it already expresses the intent clearly; the example above clarifies **Greedy semantics**, rather than encouraging replacing every standard operation with a custom Gatherer.

## 6. Contract Comparison: `of` vs `ofGreedy`

| Criterion | `Integrator.of(...)` | `Integrator.ofGreedy(...)` |
| --- | --- | --- |
| Produced type | `Integrator<A,T,R>` | `Integrator.Greedy<A,T,R>` |
| Can self-stop due to business condition? | **Yes** | **No** |
| Can return `false` when downstream rejects? | Yes | Yes, and this is the only valid cause |
| Can emit zero outputs for an input? | Yes | Yes |
| Can emit multiple outputs for an input? | Yes | Yes |
| Can hold mutable internal state? | Yes, if contract-compliant | Yes, if contract-compliant |
| Means automatic parallel execution? | No | No |
| Must framework inspect `false` as a self-stop request? | Yes | May **skip inspecting** the return value |
| Can assist optimization? | Depends on design | **Greedy metadata** opens extra optimization opportunities |
| Suitable when | There is or may be an Integrator-driven termination boundary | Definitely never proactively cuts off the stream |

**Key optimization insight:** The Java 24 specification allows a Stream implementation to **skip checking the boolean returned by a Greedy Integrator**, because the Integrator promised never to self-short-circuit. Downstream has its own mechanism to express no longer accepting results.

Thus, mislabeling an Integrator as Greedy **does not just make documentation inaccurate**: it can cause a compliant implementation to ignore the `false` signal that business logic relied on. Subsequent outputs might then contain data past the point where it was supposed to stop.

### 6.1. `ofGreedy` Does Not Alter the Lambda's Logic

Both `of` and `ofGreedy` accept a lambda with the same three-parameter signature returning boolean. The difference is **the Integrator type** and **the promise communicated to the framework**, not a new filtering or looping algorithm.

An Integrator that happens to behave greedily can be implemented with `of` and still be correct. Only once you are certain the Greedy contract holds should you use `ofGreedy` to give the framework optimization opportunities.

## 7. Side-by-Side Example: Same Mapping, Two Integrator Kinds

The same squaring operation (within a small, non-overflowing range):

```java
import java.util.stream.Gatherer;

// Regular Integrator: valid, does not self-stop.
Gatherer.Integrator<Void, Integer, Integer> ordinary =
    Gatherer.Integrator.of(
        (unused, n, downstream) -> downstream.push(n * n)
    );

// Greedy Integrator: also does not self-stop, informs the framework.
Gatherer.Integrator.Greedy<Void, Integer, Integer> greedy =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) -> downstream.push(n * n)
    );

Gatherer<Integer, Void, Integer> g1 = Gatherer.of(ordinary);
Gatherer<Integer, Void, Integer> g2 = Gatherer.of(greedy);
```

Usage:

```java
import java.util.List;

List<Integer> input = List.of(1, 2, 3, 4);

System.out.println(input.stream().gather(g1).toList());
// [1, 4, 9, 16]

System.out.println(input.stream().gather(g2).toList());
// [1, 4, 9, 16]
```

The outputs are identical. `g2` provides **additional contract metadata** that a `Stream.gather` implementation may optimize. **There is no guarantee `g2` runs faster** across every dataset or every JDK.

If state management or multi-output emission is not needed, standard `map(n -> n * n)` is the simplest choice.

## 8. Using Greedy as a Filter: Skipping an Element Is Not Stopping the Stream

A frequent mistake when writing a filter using Gatherer is confusing "do not select this element" with "do not want the next element".

**Wrong**:

```java
// Wrong: odd numbers make integrate return false -> stops the rest of the source.
Gatherer.Integrator<Void, Integer, Integer> wrongFilter =
    Gatherer.Integrator.of(
        (unused, n, downstream) ->
            n % 2 == 0 && downstream.push(n)
    );
```

With `[2, 3, 4, 6]`, upon hitting `3`, the Integrator returns `false`. It **does not continue** to `4` and `6`. That is a **take-until-failure** gatherer, not a filter.

**Right**:

```java
Gatherer.Integrator.Greedy<Void, Integer, Integer> correctFilter =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) ->
            n % 2 == 0 ? downstream.push(n) : true
    );
```

When `n` is odd, no `push` occurs so it returns `true` to continue. When `n` is even, the result of `push` is propagated back up.

This example underscores: **`return false` always means stop receiving input**, never "filter out one element" in an `Integrator`.

## 9. Greedy Emitting Multiple Results from One Element

Greedy can also operate in *flat-map* style: one input element produces 0, 1, or multiple output elements.

For example, each input is a group of strings, and each string in the group needs to be emitted:

```java
import java.util.List;
import java.util.stream.Gatherer;

Gatherer.Integrator.Greedy<Void, List<String>, String> flattenStep =
    Gatherer.Integrator.ofGreedy(
        (unused, group, downstream) -> {
            for (String item : group) {
                if (!downstream.push(item)) {
                    return false; // Solely due to downstream rejection.
                }
            }

            return true; // Group may be empty; still await next group.
        }
    );

Gatherer<List<String>, Void, String> flatten = Gatherer.of(flattenStep);

List<String> words = List.of(
        List.of("A", "B"),
        List.of(),
        List.of("C", "D")
    ).stream()
    .gather(flatten)
    .toList();

System.out.println(words); // [A, B, C, D]
```

Notice how this is written:

```java
for (String item : group) {
    if (!downstream.push(item)) {
        return false;
    }
}
return true;
```

It propagates downstream's rejection signal immediately when it happens. Do not keep iterating over thousands of elements in `group` once downstream has signaled it wants no more.

When you only need to flatten a Stream of collections, `flatMap(List::stream)` is built-in and usually shorter; a custom Gatherer is valuable when stateful rules or complex emission logic are also required.

## 10. Greedy Still Honors Early Termination from Downstream

Distinguish **Integrator-initiated stopping** from **terminal/downstream-initiated stopping**.

Example with an infinite source:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

Gatherer.Integrator.Greedy<Void, Integer, Integer> squareStep =
    Gatherer.Integrator.ofGreedy(
        (unused, value, downstream) -> downstream.push(value * value)
    );

List<Integer> firstThree = Stream.iterate(1, n -> n + 1)
    .gather(Gatherer.of(squareStep))
    .limit(3)
    .toList();

System.out.println(firstThree); // [1, 4, 9]
```

`squareStep` has no stop rule of its own: if downstream needs more, it is willing to keep accepting inputs. However, `limit(3)` wants no more after three output elements, so the pipeline can terminate.

**Never say that Greedy "always consumes the entire source regardless of downstream".** With an infinite source, that statement immediately contradicts this example. Greedy only states that **the Integrator itself imposes no termination boundary independent of downstream**.

### 10.1. What Happens When Downstream Wants No More?

Suppose a Greedy Integrator emits multiple elements and `limit(2)` follows:

```java
List<String> firstTwo = List.of(
        List.of("A", "B", "C"),
        List.of("D")
    ).stream()
    .gather(flatten)
    .limit(2)
    .toList();

System.out.println(firstTwo); // [A, B]
```

When `push` reports rejection, the loop inside `flattenStep` returns `false` immediately. Propagating this boolean **does not violate Greedy**, because it merely reflects downstream's decision.

Do not use side-effect counters in mappers, `peek`, or `integrate` as a definitive way to verify how many elements were traversed: Streams are allowed to optimize stages when public semantics do not change.

## 11. How Dangerous Is Violating the `ofGreedy` Contract?

Look at an **intentionally broken** snippet:

```java
// DO NOT USE.
Gatherer.Integrator.Greedy<Void, String, String> bad =
    Gatherer.Integrator.ofGreedy(
        (unused, value, downstream) -> {
            boolean accepted = downstream.push(value);

            // Wrong: false can come from STOP even while downstream still accepts.
            return accepted && !"STOP".equals(value);
        }
    );
```

The programmer wanted to cut off at `"STOP"`, yet declared it `Greedy`. The specification allows a Stream implementation to **ignore the boolean of a Greedy Integrator**. Therefore, this code is **not guaranteed** to stop at the marker.

Fix:

```java
Gatherer.Integrator<Void, String, String> correct =
    Gatherer.Integrator.of(
        (unused, value, downstream) ->
            downstream.push(value) && !"STOP".equals(value)
    );
```

Or consider `takeWhile` if the source has encounter order and the business rule matches taking a prefix (excluding the first non-matching element). If you must **keep the marker**, a custom Integrator like the one above is a direct way to express it.

### 11.1. Similar Violation Patterns

| Broken pattern | Why it violates the contract |
| --- | --- |
| `ofGreedy(... -> count < limit)` | Self-stops when limit is reached, not due to downstream |
| `ofGreedy(... -> !isEndMarker(element))` | Self-stops on marker |
| `ofGreedy(... -> !businessRuleFailed)` | Self-stops on business failure |
| `ofGreedy(... -> downstream.push(x) && count < limit)` | Can return `false` due to count even when `push` returned `true` |
| `ofGreedy(... -> false)` | Always self-stops immediately even when downstream hasn't rejected |

**Review rule:** Every branch capable of `return false` in a Greedy Integrator must trace back to a **`downstream.push(...)` call that returned `false`**. If any `false` branch comes from a counter, business condition, or exception converted to boolean, use a regular Integrator or change the design.

## 12. Greedy and State: Running Total Example

Greedy **does not mean stateless**. An Integrator can maintain private state and still always accept more elements as long as downstream accepts them.

Example of running total after each element:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class RunningTotalDemo {

    static Gatherer<Integer, long[], Long> runningTotal() {
        Gatherer.Integrator.Greedy<long[], Integer, Long> step =
            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    state[0] = Math.addExact(state[0], (long) value);
                    return downstream.push(state[0]);
                }
            );

        return Gatherer.ofSequential(
            () -> new long[] {0L},
            step
        );
    }

    public static void main(String[] args) {
        List<Long> totals = List.of(3, 5, 7)
            .stream()
            .gather(runningTotal())
            .toList();

        System.out.println(totals); // [3, 8, 15]
    }
}
```

Key characteristics:

- `initializer` allocates a **fresh** state array for each managed execution pass.
- `integrate` updates the sum and emits the new value via `push`.
- `Math.addExact` throws `ArithmeticException` if the sum exceeds `long` range; Greedy is unrelated to overflow detection.
- `ofSequential` is chosen because a running total depends on order and the example **defines no combiner**.
- `ofGreedy` is chosen because the integrator **has no self-stop condition**; it only returns the signal from `push`.

Both **`ofSequential`** and **`ofGreedy`** appear in this example, yet answer **two separate questions**:

| Question | Choice |
| --- | --- |
| Can state be split and merged to run in parallel correctly? | `ofSequential` or design `of` with a valid combiner |
| Does the Integrator initiate short-circuiting itself? | `Integrator.of` or `Integrator.ofGreedy` |

If you only need a standard running total, `Gatherers.scan(() -> 0L, Long::sum)` already implements the same idea and should usually be preferred.

## 13. Greedy and finisher: Not Emitting Inside Integrator Is Still Valid

Some Gatherers **accumulate the entire source and only emit one result** in the finisher. Their Integrator may never call `downstream.push`.

Example counting input elements and emitting the result at completion:

```java
import java.util.List;
import java.util.stream.Gatherer;

public class CountAtEndDemo {
    static final class State {
        long count;
    }

    static Gatherer<String, State, Long> countAtEnd() {
        Gatherer.Integrator.Greedy<State, String, Long> step =
            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    state.count = Math.addExact(state.count, 1L);
                    return true; // No push, no reason to self-stop.
                }
            );

        return Gatherer.ofSequential(
            State::new,
            step,
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(state.count);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Long> result = List.of("A", "B", "C")
            .stream()
            .gather(countAtEnd())
            .toList();

        System.out.println(result); // [3]
    }
}
```

`Integrator.ofGreedy` fits here even though it **emits nothing at each step**. It keeps receiving inputs and updating state; at the end of the source, `finisher` emits the total count.

### 13.1. Why Must the finisher Also Care About Downstream?

`finisher` may be invoked when downstream is no longer accepting data, depending on how the pipeline terminates. When emitting multiple results in the finisher, check `downstream.isRejecting()` if helpful and especially check the boolean from each `downstream.push(...)` to stop emitting upon rejection.

`isRejecting()` is a best-effort signal, so you must still use `push` per contract; never store `Downstream` in a global variable or retain a reference after the callback invocation ends.

### 13.2. If You Only Need to Count, Do Not Write a Gatherer

The example above illustrates state and finisher. In real problems, calling:

```java
long count = List.of("A", "B", "C")
    .stream()
    .count();

System.out.println(count); // 3
```

is concise, clear, and lets the Stream optimize itself. A Gatherer is useful when an **intermediate** transformation has custom semantics that built-in `filter`, `map`, `reduce`, or `collect` cannot express.

## 14. A Regular Integrator Can "Behave Greedily" and Still Be Correct

Example:

```java
Gatherer.Integrator<Void, Integer, Integer> normal =
    Gatherer.Integrator.of(
        (unused, n, downstream) -> downstream.push(n + 1)
    );
```

`normal` **does not self-stop**. It remains a regular Integrator because it was created via `of`, yet its behavior satisfies the Greedy promise.

Once you have verified with certainty that the Integrator never self-short-circuits, you can write:

```java
Gatherer.Integrator.Greedy<Void, Integer, Integer> greedy =
    Gatherer.Integrator.ofGreedy(
        (unused, n, downstream) -> downstream.push(n + 1)
    );
```

Both are valid and yield the same results on matching data. The difference is that `greedy` turns **the non-self-stopping property** into type information that implementations can rely on.

**Practical strategy:** When unsure whether all exit branches of an Integrator obey the Greedy contract, **start with `Integrator.of`**. Only switch to `ofGreedy` after auditing all return paths and writing appropriate tests.

## 15. Greedy Does Not Mean Parallel, and `ofSequential` Does Not Mean Non-Greedy

These are two independent axes:

```text
                            CAN IT SELF-SHORT-CIRCUIT?
                                   |
                          Yes                No
                           |                  |
          Valid           Integrator.of      Integrator.ofGreedy
          combiner        + Gatherer.of      + Gatherer.of
                           |
          Sequential      Integrator.of      Integrator.ofGreedy
          (no             + ofSequential     + ofSequential
          combiner)
```

Read the diagram via two questions:

1. **Integrator property**: can it stop receiving data on its own? If yes, do not declare Greedy.
2. **State splittability**: is there a valid combiner or is it sequential-only? This depends on how the **Gatherer** is constructed, not on the name `ofGreedy`.

`Gatherer.of(integrator)` produces a **stateless parallelizable Gatherer** per contract. `Gatherer.ofSequential(initializer, integrator)` creates a **sequential Gatherer** when no valid state-splitting/merging mechanism exists.

If code uses a `long[]` as a running sum, do not switch `ofSequential` to a parallel factory just because the Integrator was marked Greedy. Order-dependent windows or running sums need a valid combiner algorithm, not merely an optimization marker.

### 15.1. `Spliterator.CONCURRENT` and Greedy Also Differ

- `Spliterator.CONCURRENT` describes a **source that can be concurrently modified** under the source contract.
- `Collector.Characteristics.CONCURRENT` describes an accumulator permitting concurrent updates under the collector contract.
- `Gatherer.Integrator.Greedy` describes **never initiating short-circuiting itself**.

None of these three characteristics automatically implies the other two.

## 16. Short-Circuiting from Upstream and Downstream

A pipeline can have limits at multiple positions:

```java
Stream.of(1, 2, 3, 4, 5)
    .takeWhile(n -> n < 4)
    .gather(greedyGatherer)
    .limit(2)
    .toList();
```

Separate the three termination sources:

- **Upstream `takeWhile`** may stop supplying inputs when the predicate becomes false.
- **Greedy Integrator** does not request to stop itself; it processes the elements supplied to it.
- **Downstream `limit(2)`** may stop wanting outputs after receiving two elements.

Therefore, the statement "Greedy receives the whole source" only holds when the source actually continues supplying elements and downstream still accepts them; it does **not** mean traversing the entire physical source in every pipeline.

### 16.1. Why Still Propagate the Signal from `push`?

Suppose the Gatherer's output is expensive to compute. If `push` returns `false` after the terminal operation has enough data, continuing to compute remaining results only causes waste. In a Greedy Integrator, returning the value of `push` clearly honors downstream:

```java
return downstream.push(expensiveResult);
```

A Stream implementation may ignore the boolean from a Greedy Integrator, yet downstream itself still manages rejection state. Hence **do not exploit this fact to ignore the `push` signal** and perform extra work with side effects.

## 17. Typical Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `ofGreedy` for a gatherer stopping at a marker | Violates non-self-stopping promise; boolean may be ignored | Use `Integrator.of` |
| Using `ofGreedy` and returning `false` on an invalid element to skip it | May terminate or exhibit unguaranteed behavior | Do not push and return `true` when only filtering |
| Using `of` and returning `false` for a filtered-out element | Stops the entire stream instead of skipping one element | Do not push, return `true` |
| Always doing `return true` after `downstream.push(...)` | Fails to reflect downstream rejection | Return `push` or break the loop when `push` returns `false` |
| Assuming `ofGreedy` means always pushing exactly one element | Misunderstands filtering, flattening, and finishers | Remember Greedy is the **no self-stopping** contract |
| Assuming `ofGreedy` means faster execution in all cases | Optimization is not guaranteed | Benchmark with representative workloads |
| Assuming Greedy is automatically thread-safe | May have unsafe shared state | Manage initializer/combiner and confinement separately |
| Assuming `ofSequential` cannot use Greedy | Misses the chance to express the contract | They are two independent axes |
| Marking Greedy when `return count < limit` exists | False due to internal condition | Switch to a regular Integrator |
| Failing to check `push` when emitting multiple results | Wasted work after downstream rejects | Exit the loop if `push` returns `false` |
| Saving `state` or `downstream` in a static field for later use | Violates lifecycle contract, risks data races | Use references only within valid callback scope |
| Using `peek`/side effects to count Integrator invocations | Pipeline may short-circuit or optimize | Test public outputs |
| Using `gather` on JDK 17/21 | API does not exist | Use JDK 24+ or a compatible algorithm |
| Returning I/O resources without a close handler/ownership contract | Leaks files, cursors, or connections | Use `try-with-resources` and proper source APIs |
| Using `int`/`long` addition assuming Greedy prevents overflow | Results may wrap/overflow | Use `Math.addExact` or `BigInteger` per requirements |

## 18. Complete Java 24 Example: Both Kinds of Integrators

The following example can be saved as `GreedyVsOrdinaryDemo.java` and compiled with **JDK 24**. It shows both a regular Integrator that **self-stops** and a Greedy Integrator that **continues until downstream rejects**.

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class GreedyVsOrdinaryDemo {

    // Does not self-stop: each even number is transformed to its square.
    static Gatherer<Integer, Void, Integer> evenSquares() {
        Gatherer.Integrator.Greedy<Void, Integer, Integer> step =
            Gatherer.Integrator.ofGreedy(
                (unused, n, downstream) -> {
                    if (n % 2 != 0) {
                        return true;   // Skip odd numbers, do not stop.
                    }

                    return downstream.push(Math.multiplyExact(n, n));
                }
            );

        return Gatherer.of(step);
    }

    // Self-stops after marker, even if downstream still wants more.
    static Gatherer<String, Void, String> untilStop(String marker) {
        Gatherer.Integrator<Void, String, String> step =
            Gatherer.Integrator.of(
                (unused, text, downstream) -> {
                    boolean wantsMore = downstream.push(text);
                    return wantsMore && !text.equals(marker);
                }
            );

        return Gatherer.ofSequential(step);
    }

    // Stateful, yet does not self-stop.
    static Gatherer<Integer, long[], Long> runningTotals() {
        Gatherer.Integrator.Greedy<long[], Integer, Long> step =
            Gatherer.Integrator.ofGreedy(
                (state, n, downstream) -> {
                    state[0] = Math.addExact(state[0], (long) n);
                    return downstream.push(state[0]);
                }
            );

        return Gatherer.ofSequential(
            () -> new long[] {0L},
            step
        );
    }

    public static void main(String[] args) {
        System.out.println(
            List.of(1, 2, 3, 4, 5, 6).stream()
                .gather(evenSquares())
                .toList()
        ); // [4, 16, 36]

        System.out.println(
            List.of("A", "B", "STOP", "C").stream()
                .gather(untilStop("STOP"))
                .toList()
        ); // [A, B, STOP]

        System.out.println(
            List.of(3, 5, 7).stream()
                .gather(runningTotals())
                .toList()
        ); // [3, 8, 15]

        System.out.println(
            Stream.iterate(1, n -> n + 1)
                .gather(evenSquares())
                .limit(3)
                .toList()
        ); // [4, 16, 36]
    }
}
```

Compile and run:

```bash
javac --release 24 GreedyVsOrdinaryDemo.java
java GreedyVsOrdinaryDemo
```

Observations:

1. `evenSquares` is Greedy because **filtering out odd numbers does not stop it from receiving subsequent numbers**, and even numbers simply forward the signal from `push`.
2. `untilStop` is a regular Integrator because **the marker causes it to stop on its own**.
3. `runningTotals` is a **stateful** Greedy Integrator, using `ofSequential` so it does not require a combiner for running totals.
4. `Stream.iterate` is infinite, yet downstream `limit(3)` can stop the pipeline after three even squares.
5. Results are verified via the **output list**, not by relying on lambda invocation counts or execution threads.

## 19. Testing the Greedy Contract and Early Termination

For production code, test both **result correctness** and **termination rules** separately.

### 19.1. Small Data Tests

| Input | Gatherer | Expected Output |
| --- | --- | --- |
| `[]` | `evenSquares` | `[]` |
| `[1,3,5]` | `evenSquares` | `[]` |
| `[2,3,4]` | `evenSquares` | `[4,16]` |
| `["A","STOP","B"]` | `untilStop("STOP")` | `["A","STOP"]` |
| `["A","B"]` | `untilStop("STOP")` | `["A","B"]` |
| `[1,2,3]` | `runningTotals` | `[1,3,6]` |
| `[1,2,3,4]` then `limit(2)` | `evenSquares` | `[4,16]` |

Test cases to cover:

- Empty source and single-element source.
- Filter predicate matching none or matching all.
- Marker at the beginning, middle, end, or absent.
- Downstream `limit(0)`, `limit(1)`, `findFirst`.
- An Integrator emitting **multiple results** for a single input element.
- Exceptions thrown inside a mapper or when pushing data.
- Running on ordered sources; do not assume order if using `unordered()`.

### 19.2. Do Not Rely on "Broken Code Seems to Work"

A Greedy Integrator that violates the contract may **coincidentally** stop properly on one JVM version or one test case. That does not prove the code is valid, because another implementation **is allowed to ignore the boolean** of a Greedy Integrator.

Therefore, alongside output tests, always **audit every `return false` path** of an Integrator before calling `ofGreedy`. This is a contract review, not merely example testing.

### 19.3. Checking Parallel Correctness

If a Gatherer has a combiner enabling parallel execution, compare semantics between sequential and parallel pipelines on ordered data when the business logic requires encounter order.

Especially with large datasets and short-circuiting rules, verify that outputs from branches past the stopping point are not erroneously retained. Never place a global `HashMap` or `ArrayList` for workers to write into concurrently, and never abuse `AtomicInteger` to turn side effects into the main aggregation mechanism.

## 20. Performance and Optimization Potential

Greedy metadata can help a Stream implementation optimize how it schedules the gather stage. However:

- **There is no quantitative guarantee** that `ofGreedy` is faster than `of`.
- Actual optimization depends on downstream, source length, emitted result count, and other stages.
- If the Integrator performs heavy computation or reads I/O sources, that cost can dwarf savings from skipping a boolean check.
- Switching to `ofGreedy` does **not** automatically unlock parallelism for a Gatherer built with `ofSequential`.
- Greedy does not replace standard `filter`/`map`, which may be optimized even further for simple cases.

When performance measurement is truly needed, use representative data, warm-up/multiple runs, and a proper tool like JMH. Before comparing speed, ensure both versions **produce identical results and have the same termination contract**; never change `of` to `ofGreedy` on an Integrator that self-short-circuits.

### 20.1. Resource-Backed Sources Must Still Be Closed

When the source is `Files.lines(path)` or a Stream backed by a resource needing release, terminal operations like `toList()`, `findFirst()`, or early termination from an Integrator **do not replace `close()`**.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

// Place inside a method with throws IOException or error handling.
Path file = Path.of("events.txt");

try (Stream<String> lines = Files.lines(file)) {
    List<String> untilStop = lines
        .gather(GreedyVsOrdinaryDemo.untilStop("STOP"))
        .toList();

    System.out.println(untilStop);
}
```

`try-with-resources` closes the file source both when the Gatherer stops early and when a lambda throws an exception. If an API returns a live Stream, ownership and closing responsibility must be defined in the API contract.

## 21. Practice Exercises

### Exercise 1: Classify Integrators

Given four lambdas:

```java
// A
(unused, n, downstream) -> downstream.push(n)

// B
(unused, n, downstream) -> n >= 0 && downstream.push(n)

// C
(unused, n, downstream) -> n >= 0
    ? downstream.push(n)
    : true

// D
(unused, n, downstream) -> {
    if (n == 100) return false;
    return downstream.push(n);
}
```

Determine which lambdas can be declared with `ofGreedy` and why. Distinguish **filtering** from **self-stopping**.

### Exercise 2: Converting from `of` to `ofGreedy`

Write a regular Integrator that emits uppercase strings:

```java
Gatherer.Integrator<Void, String, String> upper =
    Gatherer.Integrator.of(
        (unused, s, downstream) ->
            downstream.push(s.toUpperCase())
    );
```

Convert it to `ofGreedy` and compare outputs when downstream is `limit(2).toList()`. Explain why equal outputs do not imply performance is guaranteed to be identical or faster.

### Exercise 3: Early Termination Marker

Write a Gatherer that emits log lines up to `"END"`, inclusive of the marker, then stops. Use `Integrator.of`. Why would using `ofGreedy` violate the contract?

### Exercise 4: Emitting Multiple Outputs

Create a Greedy Gatherer that splits a `List<String>` into individual strings. Place `limit(3)` after the Gatherer to verify stopping emission upon downstream rejection. Explain the role of the boolean returned by `push`.

### Exercise 5: Filtering Out Invalid Elements

Given `[2, -1, 4, -3, 6]`. Write a Greedy Integrator that emits only non-negative numbers; the result must be `[2,4,6]`. Try returning `false` on negative numbers and explain why it is no longer a valid filter.

### Exercise 6: Stateful Running Total

Create a `Gatherer<Integer, long[], Long>` using `ofSequential` and `ofGreedy` that emits the sum after each number. Test with `[1,2,3]`, an empty source, and negative numbers. If there is a risk of `long` overflow, how should handling be designed?

### Exercise 7: Finisher Emitting Only the Final Result

Create a Gatherer using `initializer` to hold a counter, `ofGreedy` to increment the counter **without pushing**, and `finisher` to emit the result. When should that Gatherer be replaced by `Stream.count()` or `Collectors.counting()`?

### Exercise 8: Subtle Contract Bug

Given:

```java
Gatherer.Integrator.ofGreedy(
    (state, item, downstream) -> {
        state.processed++;
        boolean more = downstream.push(item);
        return more && state.processed < 10;
    }
);
```

Explain why this snippet is invalid even though it may sometimes stop properly after 10 elements. Rewrite it using a regular Integrator or remove the internal limit so it only reflects downstream.

### Exercise 9: Ordering and Work Splitting

A Gatherer accumulates a prefix sum using `long[]` but has no exact combiner. Should it use `ofSequential`? Can its Integrator use `ofGreedy`? Why are the two answers independent?

### Exercise 10: Benchmarking Optimization

Design a benchmark comparing a regular Integrator that behaves greedily against an Integrator marked `Greedy` on the same data. List the variables that must be held constant: JDK, input, downstream, size, parallelism level, and output correctness.

## 22. Self-Check Questions

- What three arguments does `Gatherer.Integrator<A,T,R>` receive and what type does it return?
- Does `return false` inside `integrate` mean "skip the current element" or "stop receiving further inputs"?
- What distinguishes `Integrator.of` from `Integrator.ofGreedy`?
- Can Greedy be used to skip an element while continuing to process subsequent elements?
- Can Greedy emit multiple output elements for a single input element?
- Why is `ofGreedy` unsuitable for a "stop at marker" algorithm?
- Why is a Stream implementation allowed to ignore the boolean of a Greedy Integrator?
- What does `downstream.push` returning `false` mean?
- Is `isRejecting()` an absolute guarantee about all future `push` calls?
- Can a Greedy Integrator maintain internal state?
- What does `ofSequential` decide that `ofGreedy` does not decide?
- Why doesn't a source with `Spliterator.CONCURRENT` make an Integrator automatically thread-safe?
- When should `filter`, `map`, or `count` be used instead of a custom Gatherer?
- When the source is `Files.lines`, who is responsible for closing it after short-circuiting?
- Which test cases help detect a Gatherer that self-stops in violation of its contract?

## 23. Official References

- [Java SE 24 — Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): `integrate`, `of`, and `ofGreedy` signatures.
- [Java SE 24 — Gatherer.Integrator.Greedy](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.Greedy.html): promise not to self-short-circuit.
- [Java SE 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): `push` and `isRejecting`.
- [Java SE 24 — Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer/integrator/combiner/finisher contracts and Greedy optimization.
- [Oracle — Stream Gatherers Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): examples of Integrator, short-circuiting, finisher, and parallel execution.
- [Dev.java — The Gatherer API](https://dev.java/learn/api/streams/gatherers/): guide on Greedy Integrators and propagating downstream signals.
- [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): API finalization in Java 24.

**Remember:** `Integrator.of(...)` is for Integrators that **can self-stop receiving input**; `Integrator.ofGreedy(...)` is for when the Integrator **never initiates short-circuiting itself**, only reflecting downstream rejection. Greedy does **not** mean always emitting one element, is not automatically parallel or thread-safe, and does not guarantee a speedup. Declaring Greedy incorrectly can yield wrong results because the framework **is permitted to ignore** its boolean return value. Prioritize contract correctness and only use `ofGreedy` when every return path of the Integrator complies.
