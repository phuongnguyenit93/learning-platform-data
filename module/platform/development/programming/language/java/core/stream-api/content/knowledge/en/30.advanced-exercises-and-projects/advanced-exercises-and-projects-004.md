# Writing Gatherers for Consecutive Groups and Data Windows

In many event-sequence processing problems, the result depends not on individual elements alone, but on **adjacent elements**: a streak of consecutive states, an active session, a run of identical items, or a window of the most recent measurements. `filter` and `map` handle per-element logic very well; `groupingBy` collects all elements by key; yet neither directly expresses the rule "group **adjacent** elements and emit an intermediate result to continue the pipeline".

**Stream Gatherers** provide a mechanism for stateful intermediate operations that can emit **0, 1, or many** output elements. This lesson belongs to the **Advanced Exercises and Projects** chapter of the `JAVA_STREAM_API` module: we will write custom Gatherers for **consecutive groups** and **data windows**, compare them against `Gatherers.windowFixed` and `Gatherers.windowSliding`, build an event-monitoring problem, test edge cases, and evaluate performance, resources, ordering, and parallel execution.

> **Version requirement:** `java.util.stream.Gatherer`, `Gatherers`, and `Stream.gather(...)` were finalized in **Java 24 (JEP 485)**. Java 22 and 23 had preview versions with potentially different contracts/syntax; **Java 8–21 do not include this standard API**. The main code targets Java 24 or later without the `--enable-preview` flag on Java 24. If your system cannot upgrade its JDK yet, use a loop or a suitable stateful collection instead of copying the Gatherer code verbatim.

## 1. Defining Requirements Before Writing a Gatherer

Suppose we have a sequence of states over time:

```text
A, A, A, B, B, A, C, C
```

There are several very different ways to group them:

| Need | Desired Output | Suitable Tool |
| --- | --- | --- |
| Group all elements with the same key regardless of position | A -> [A,A,A,A], B -> [B,B], C -> [C,C] | `Collectors.groupingBy` |
| Group **consecutive runs** with the same key | [A,A,A], [B,B], [A], [C,C] | Gatherer tracking current group state |
| Split into fixed non-overlapping blocks | [A,A,A], [B,B,A], [C,C] | `Gatherers.windowFixed(3)` |
| Create sliding windows of size 3 | [A,A,A], [A,A,B], [A,B,B], ... | `Gatherers.windowSliding(3)` |
| Create sliding windows **only when all 3 elements are present** | Length-3 slices, no underfilled windows emitted | Custom Gatherer with explicit emission rules |

The notion of **consecutive groups** requires a meaningful encounter order. If the source is an unordered set or events are not sorted by time, "consecutive" reflects an accidental traversal order rather than necessarily business order.

**Core design question:** When is a result emitted? When a different key appears, when `k` elements are counted, or when the source ends? That answer dictates how `integrator` and `finisher` are written.

## 2. Where Does a Gatherer Sit in the Pipeline?

`gather(...)` is an **intermediate operation**, not a terminal operation:

```text
Stream<T> source
      |
  filter/map
      |
  gather(custom Gatherer<T, A, R>)
      |             ├─ initializer: creates state A
      |             ├─ integrator: receives T, updates A, may push R
      |             ├─ combiner: merges A if parallel is supported
      |             └─ finisher: emits remaining result on completion
      |
  map/filter/flatMap
      |
  collect / toList / reduce / count      <- terminal
      |
  Result
```

Type parameter concepts:

- `T`: Gatherer input type;
- `A`: internal accumulation state type;
- `R`: output element type emitted by the Gatherer downstream.

For example, `Gatherer<String, ?, List<String>>` accepts individual strings and emits individual **groups of strings**, rather than returning one final `Map`.

A Gatherer has components analogous to a collector, though with different roles:

| Component | Responsibility |
| --- | --- |
| `initializer` | Creates state `A` for the accumulation process |
| `integrator` | Accepts one element `T` and decides whether to update state, emit `R`, or stop |
| `combiner` | Coordinates branch states when the Gatherer's contract permits it |
| `finisher` | Handles leftover state when upstream completes |
| `Downstream.push(R)` | Passes one element `R` to the next stage |

Notably, `integrator` returns a `boolean`: `true` if it can still accept elements, `false` if no further elements are needed. `Downstream.push(value)` also returns a `boolean` indicating whether downstream still wants more data.

Do not think of `push` as appending directly to a final `List`. It merely emits an element to the next stage; downstream may still have `filter`, `limit`, `map`, or another Gatherer.

## 3. ofSequential and Why Choose a Sequential Gatherer

For problems relying on **boundaries between the previous and next element**, the simplest approach is `Gatherer.ofSequential(...)`.

Conceptual form:

```java
Gatherer.ofSequential(
        initializer,
        integrator,
        finisher
);
```

Where:

- `initializer` supplies a fresh state;
- `integrator` processes each element according to adjacency logic;
- `finisher` emits the final buffered remainder.

Not every Gatherer needs a finisher; if every result is already emitted as elements arrive, use the `ofSequential(initializer, integrator)` overload.

`ofSequential` fits because state such as "current group" or "window of prior elements" depends on order. If you write a `combiner` enabling parallel splitting, you must properly resolve **groups spanning the boundary between two branches**, rather than merely concatenating two output lists. Never slap together an arbitrary list-concatenating combiner and assume the problem is correctly parallelized.

Calling `parallel()` upstream **does not** guarantee a sequential Gatherer will run faster. Stages before the Gatherer may behave differently, while order-dependent transformations must still preserve their contract.

## 4. Exercise 1: Grouping Consecutive Elements by Key

### Requirements and Example

From the sequence:

```text
A, A, B, B, B, A, C, C
```

Produce the groups:

```text
[A, A]
[B, B, B]
[A]
[C, C]
```

The third `A` **must not merge** with the first `A` group because three `B` elements sit between them. This is how it differs from `groupingBy`.

State rules:

1. No active group yet -> open a group with the first element's key.
2. New key matches the current group's key -> append the element.
3. New key differs from the current key -> **emit a copy of the old group**, then start a new group.
4. Source ends -> **emit the final group** inside the finisher.
5. If downstream wants no more elements -> stop and emit no leftover data.

### Complete Implementation

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Gatherer;

public final class RunGatherers {
    private RunGatherers() {}

    private static final class RunState<T, K> {
        boolean active;
        boolean cancelled;
        K currentKey;
        final List<T> current = new ArrayList<>();
    }

    public static <T, K> Gatherer<T, ?, List<T>> consecutiveBy(
            Function<? super T, ? extends K> classifier) {

        Objects.requireNonNull(classifier, "classifier");

        return Gatherer.ofSequential(
                () -> new RunState<T, K>(),

                (state, element, downstream) -> {
                    K key = classifier.apply(element);

                    // First element of the group.
                    if (!state.active) {
                        state.active = true;
                        state.currentKey = key;
                        state.current.add(element);
                        return true;
                    }

                    // Same key as the current group.
                    if (Objects.equals(state.currentKey, key)) {
                        state.current.add(element);
                        return true;
                    }

                    // Key changed: emit a copy of the completed group.
                    List<T> completed =
                            new ArrayList<>(state.current);

                    if (!downstream.push(completed)) {
                        state.cancelled = true;
                        state.current.clear();
                        return false;
                    }

                    state.current.clear();
                    state.currentKey = key;
                    state.current.add(element);
                    return true;
                },

                (state, downstream) -> {
                    // The final group has no key-changing element to trigger push.
                    if (!state.cancelled
                            && state.active
                            && !state.current.isEmpty()) {
                        downstream.push(
                                new ArrayList<>(state.current)
                        );
                    }
                }
        );
    }
}
```

**Usage:**

```java
import java.util.List;
import java.util.stream.Stream;

List<List<String>> runs = Stream.of(
        "A", "A", "B", "B", "B", "A", "C", "C"
).gather(RunGatherers.consecutiveBy(s -> s))
 .toList();

System.out.println(runs);
// [[A, A], [B, B, B], [A], [C, C]]
```

In the class above, `RunState<T, K>` is **internal Gatherer data**, not a public result. `current` holds only one incomplete group. `currentKey` stores the current group's key; `active` distinguishes "not started yet" from "currently in a group with a null key".

### Why Must We Use Objects.equals?

If the classifier can return `null`, writing `currentKey.equals(key)` throws `NullPointerException`. In the example, `Objects.equals(currentKey, key)` treats two null keys as the same key and avoids confusing that with an unstarted state thanks to `active`.

This differs from `Collectors.groupingBy`: the classifier of `groupingBy` is disallowed from returning `null` by contract. A custom Gatherer can choose its own null-key policy, as long as handling logic and downstream types remain consistent.

If **the input element itself** may be null, generic code can still store that element inside `ArrayList`; the classifier must handle null safely. Never assume every `Function<T,K>` supports null inputs.

## 5. Crossing Boundaries: How Integrator and Finisher Coordinate

Consider the sequence `A, A, B`:

```text
Read A:
    active = true, currentKey = A, current = [A]
    not emitted yet

Read A:
    current = [A, A]
    not emitted yet

Read B:
    emit snapshot [A, A]
    currentKey = B, current = [B]

Source ended:
    finisher emits snapshot [B]
```

If you forget the finisher, the final group is lost. If you push `state.current` directly and then call `clear()`, downstream may hold a reference to **the exact same cleared List**, corrupting earlier results.

Therefore, each emission uses `new ArrayList<>(state.current)`. That creates a **snapshot decoupled from the mutable buffer**; we never modify it after emitting.

### Downstream May Stop Early

For example, wanting only the first group:

```java
List<List<String>> firstRun = Stream.of(
        "A", "A", "B", "B", "C"
).gather(RunGatherers.consecutiveBy(s -> s))
 .limit(1)
 .toList();

System.out.println(firstRun); // [[A, A]]
```

When the Gatherer sees `B`, it emits `[A, A]`. `limit(1)` has received its one output, so `downstream.push(...)` can return `false`: the Gatherer must stop and not emit group `B` in the finisher.

That is why the implementation sets `state.cancelled = true` and returns `false`. Never unconditionally ignore the return value of `push`. **Early termination downstream does not automatically close an I/O source**; if upstream is `Files.lines`, you still need `try-with-resources`.

## 6. Edge Cases for Consecutive Grouping

| Source | Output |
| --- | --- |
| Empty | `[]` |
| `[A]` | `[[A]]` |
| `[A,A,A]` | `[[A,A,A]]` |
| `[A,B,A]` | `[[A],[B],[A]]` |
| `[A,A,B]` | `[[A,A],[B]]` |
| `[A,B,B]` | `[[A],[B,B]]` |
| `[null,null,A,null]` with identity classifier | `[[null,null],[A],[null]]` |

With an empty source, `active` stays `false`; the finisher emits no groups. For the final key with no trailing key-change element, the finisher flushes the group.

A group can be very long—even as long as the entire source. An implementation returning `List<T>` must hold every element of that group in memory; **there is no `O(1)` memory guarantee with respect to group length**. If you only need counts or sums per run, store a compact summary state instead of all elements.

## 7. Memory-Efficient Variant: Emitting Per-Group Statistics

Log data can contain millions of consecutive events of the same type. If you only want the **key and count** of each streak, there is no need to retain all events.

Suppose we have a result `record`:

```java
record RunCount<K>(K key, long count) {}
```

State needs only `key`, `count`, `active`, and `cancelled`. Implementation idea:

```java
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Gatherer;

static <T, K> Gatherer<T, ?, RunCount<K>> countRuns(
        Function<? super T, ? extends K> classifier) {

    class State {
        K key;
        long count;
        boolean active;
        boolean cancelled;
    }

    return Gatherer.ofSequential(
            State::new,
            (state, element, downstream) -> {
                K key = classifier.apply(element);

                if (!state.active) {
                    state.active = true;
                    state.key = key;
                    state.count = 1;
                    return true;
                }

                if (Objects.equals(state.key, key)) {
                    state.count++;
                    return true;
                }

                if (!downstream.push(
                        new RunCount<>(state.key, state.count))) {
                    state.cancelled = true;
                    return false;
                }

                state.key = key;
                state.count = 1;
                return true;
            },
            (state, downstream) -> {
                if (state.active && !state.cancelled) {
                    downstream.push(
                            new RunCount<>(state.key, state.count));
                }
            }
    );
}
```

Result:

```java
List<RunCount<String>> counts = Stream.of(
        "A", "A", "B", "A", "A", "A"
).gather(countRuns(s -> s)).toList();

System.out.println(counts);
// [RunCount[key=A, count=2], RunCount[key=B, count=1],
//  RunCount[key=A, count=3]]
```

Internal state memory for this variant is `O(1)` per run, excluding the output list built by terminal `toList()`. With a `long` counter, still watch for overflow if a single run could exceed `Long.MAX_VALUE`.

> **Design point:** If you need all elements in the group, use a Gatherer emitting `List<T>`. If you only need an aggregate, emit a **compact statistics DTO**. Choosing the output shape largely determines memory cost.

## 8. Exercise 2: Fixed Windows and Sliding Windows

A *window* is a group of neighboring elements in an ordered sequence. There are two basic kinds.

### Non-Overlapping Fixed Windows

With size `3`:

```text
Source:  1 2 3 4 5 6 7 8

Window 1: [1 2 3]
Window 2:       [4 5 6]
Window 3:             [7 8]   <- final chunk shorter than 3
```

This partitions into contiguous batches; windows are **non-overlapping**.

### Overlapping Sliding Windows

With size `3`:

```text
Source:  1 2 3 4 5

Window 1: [1 2 3]
Window 2:   [2 3 4]
Window 3:     [3 4 5]
```

Each full window shifts by one element, so middle elements appear in multiple windows. Typical problems are moving averages, trend detection, or inspecting the last three events.

**Specify the underfilled-window policy explicitly:** fixed windows usually emit the final partial batch, while a statistical algorithm might want sliding windows **only when all `k` elements are present**. These requirements differ, so we will define the contract of each custom variant explicitly.

## 9. Built-In Factories in Java 24: Gatherers.windowFixed and windowSliding

Before building your own, inspect the two standard Gatherers:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> fixed = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
        .gather(Gatherers.windowFixed(3))
        .toList();

System.out.println(fixed);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

For sliding windows:

```java
List<List<Integer>> sliding = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowSliding(3))
        .toList();

System.out.println(sliding);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

These standard factories express the problem concisely and avoid rewriting state logic. They emit windows as lists; **do not mutate output lists** without a clear requirement and mutability contract.

Both factories require a **positive** window size; `0` or negative values are invalid configurations. For large window sizes, account for element retention memory and the number of window copies created.

**Note on inputs shorter than window size:** when applying standard `Gatherers.windowSliding`, verify its policy for underfilled windows under the JDK contract you are using. The custom `fullSliding` implementation below **deliberately suppresses** incomplete windows so threshold-checking algorithms maintain consistent statistical meaning.

## 10. Writing a Fixed Window That Emits the Final Batch

Goal: emit a window whenever `size` elements accumulate; when the source ends, emit the remainder if non-empty.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;

public final class FixedWindowGatherers {
    private FixedWindowGatherers() {}

    private static final class State<T> {
        final List<T> bucket = new ArrayList<>();
        boolean cancelled;
    }

    public static <T> Gatherer<T, ?, List<T>> fixed(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }

        return Gatherer.ofSequential(
                () -> new State<T>(),

                (state, element, downstream) -> {
                    state.bucket.add(element);

                    if (state.bucket.size() < size) {
                        return true;
                    }

                    List<T> completed =
                            new ArrayList<>(state.bucket);
                    state.bucket.clear();

                    boolean wantsMore = downstream.push(completed);
                    if (!wantsMore) {
                        state.cancelled = true;
                    }
                    return wantsMore;
                },

                (state, downstream) -> {
                    if (!state.cancelled
                            && !state.bucket.isEmpty()) {
                        downstream.push(
                                new ArrayList<>(state.bucket));
                    }
                }
        );
    }
}
```

Example:

```java
import java.util.List;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 8)
        .boxed()
        .gather(FixedWindowGatherers.fixed(3))
        .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Characteristics:

- The buffer holds at most `size` elements before emitting.
- Once full, the accumulator takes a **snapshot** and clears the buffer.
- `finisher` emits the final batch if elements remain.
- If downstream requested cancellation, `cancelled` stops `finisher` from emitting more.

For `n > 0` elements, the number of fixed windows is `ceil(n / size)`; for an empty source, no windows are emitted. Accumulating state uses `O(size)` memory, not counting emitted windows retained downstream.

## 11. Writing a Sliding Window That Emits Only Full Windows

Exact requirements for `fullSliding(size)`:

- While fewer than `size` elements have been seen -> **emit nothing**.
- Once `size` elements have arrived -> emit the first window.
- On each new element -> drop the oldest element, append the new element, emit the new window.
- **Do not emit underfilled windows** at the end of the source.
- If downstream rejects further data -> return `false` and stop.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public final class WindowGatherers {
    private WindowGatherers() {}

    private static final class WindowState<T> {
        final Deque<T> buffer = new ArrayDeque<>();
    }

    public static <T> Gatherer<T, ?, List<T>> fullSliding(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }

        return Gatherer.ofSequential(
                () -> new WindowState<T>(),

                (state, element, downstream) -> {
                    // ArrayDeque does not accept null elements.
                    state.buffer.addLast(
                            Objects.requireNonNull(element, "element")
                    );

                    if (state.buffer.size() > size) {
                        state.buffer.removeFirst();
                    }

                    if (state.buffer.size() == size) {
                        return downstream.push(
                                new ArrayList<>(state.buffer)
                        );
                    }

                    return true;
                }
        );
    }
}
```

Usage:

```java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
        .gather(WindowGatherers.fullSliding(3))
        .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

On every emission, `new ArrayList<>(state.buffer)` creates an independent copy so the next `removeFirst` cannot mutate a window already pushed downstream.

**Specific limitation:** `ArrayDeque` rejects null elements. The implementation above explicitly rejects nulls via `Objects.requireNonNull`; if your system needs a sequence with valid null values, pick a different buffer or represent missing data with an explicit wrapper type.

### Why Is No Finisher Needed?

Because the stated policy emits only **full windows**, there is no leftover remainder to flush on completion. Any buffer holding fewer than `size` elements at end-of-stream is not a valid window under this exercise's contract.

This is a key contrast with fixed windows in section 10: **whether a finisher exists depends on desired semantics**, not a mandatory template for every Gatherer.

## 12. Counting Formulas and Complexity

Suppose the source has `n` elements and window size `k > 0`.

| Algorithm | Output Element Count | State Memory | Result Creation Cost |
| --- | --- | --- | --- |
| `consecutiveBy` emitting `List<T>` | Number of consecutive-key runs | `O(max run length)` | Total elements copied ~ `O(n)` |
| `countRuns` emitting statistics | Number of consecutive-key runs | `O(1)` | `O(number of runs)` |
| Custom `fixed(k)` | `ceil(n/k)` if `n > 0`; 0 if empty | `O(k)` | Total elements copied `O(n)` |
| Custom `fullSliding(k)` | `max(0, n-k+1)` | `O(k)` | Up to `O(k * max(0,n-k+1))` due to copying each window |

A common mistake is seeing that window state holds only `k` elements and concluding the whole pipeline uses `O(k)` memory. If the terminal operation is `toList()`, every emitted window stays in memory; for sliding windows, the number of elements referenced in the output can reach roughly `k(n-k+1)`.

For instance, `100_000` measurements with window size `100` produce nearly `100_000` windows of `100` elements each. If you only need a **moving average**, emitting full `List<T>` objects and collecting them with `toList()` can be very memory-intensive; instead, `map` each window directly into a statistic, or write a Gatherer that maintains an `O(1)` rolling sum updated at each step.

If windows do not all need to be retained, use a streaming terminal operation or write to a sink with explicit I/O management rather than storing every result.

## 13. Mini Project: Detecting Spikes per Sensor Session

### Requirements

A stream of sensor events contains sensor IDs and measurement values. Data is ordered by time, yet readings for a given sensor can appear in **multiple non-adjacent sessions**.

```text
A:10, A:14, A:19, B:20, B:22, B:24, A:5
```

Goals:

1. Group **adjacent** events **with the same sensor ID** into sessions.
2. Within each session, form **full three-element** sliding windows.
3. Emit the sum of the three measurements for each window.
4. Never let a window cross a session boundary.
5. If a session has fewer than three readings, emit no result.

This combines two custom Gatherers without needing a global Map holding all readings by key.

### Data Model

```java
record Reading(String sensorId, long tick, int value) {}

record WindowSum(String sensorId, int sum) {}
```

`record` is standard syntax in Java 24. The example assumes input is already sorted by ascending `tick`; if not, establish and enforce ordering before grouping sessions.

### Practice Pipeline

```java
import java.util.List;

List<Reading> readings = List.of(
        new Reading("A", 1, 10),
        new Reading("A", 2, 14),
        new Reading("A", 3, 19),
        new Reading("B", 4, 20),
        new Reading("B", 5, 22),
        new Reading("B", 6, 24),
        new Reading("A", 7, 5)
);

List<WindowSum> result = readings.stream()
        .gather(RunGatherers.consecutiveBy(Reading::sensorId))
        .flatMap(run -> run.stream()
                .gather(WindowGatherers.fullSliding(3))
                .map(window -> new WindowSum(
                        window.get(0).sensorId(),
                        window.stream()
                                .mapToInt(Reading::value)
                                .sum()
                )))
        .toList();

System.out.println(result);
// [WindowSum[sensorId=A, sum=43],
//  WindowSum[sensorId=B, sum=66]]
```

Because:

- The first `A` session has `10 + 14 + 19 = 43`.
- The `B` session has `20 + 22 + 24 = 66`.
- The trailing `A` session has only `5`, insufficient for a three-element window.

If you replaced `consecutiveBy` with `groupingBy(Reading::sensorId)`, both `A` sessions would merge into one group. That could form a window spanning a time/session gap and produce wrong business results.

### Scaling Up the Prompt

To turn this example into a realistic mini project, extend it step by step:

1. Records include `sessionId` or a rule starting a new session when the `tick` gap exceeds a threshold. Then a classifier by sensor ID alone is **insufficient**; Gatherer state must also check session-break conditions.
2. Replace the sum with `double average`, documenting floating-point rounding and rounding policy.
3. Emit alerts only when the three-reading average exceeds a threshold, without alerting repeatedly within the same session.
4. If data arrives over a network or file, define who owns and closes the source; the Gatherer does not manage I/O itself.
5. For massive datasets, avoid holding an entire session in a `List`; write a single per-session Gatherer using a ring-buffer window.

These upgrades are extension exercises; the baseline code above solves adjacent-key session grouping and full three-reading windows accurately.

## 14. Essential Behavioral Tests

Testing a Gatherer is not just matching output on a "happy path" sequence. Test boundary cases against the contract.

### Testing Consecutive Grouping

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

static void checkEquals(Object expected, Object actual) {
    if (!Objects.equals(expected, actual)) {
        throw new AssertionError(
                "Expected " + expected + ", got " + actual
        );
    }
}

checkEquals(
        List.of(),
        Stream.<String>empty()
                .gather(RunGatherers.consecutiveBy(s -> s))
                .toList()
);

checkEquals(
        List.of(List.of("A", "A", "A")),
        Stream.of("A", "A", "A")
                .gather(RunGatherers.consecutiveBy(s -> s))
                .toList()
);

checkEquals(
        List.of(List.of("A"), List.of("B"), List.of("A")),
        Stream.of("A", "B", "A")
                .gather(RunGatherers.consecutiveBy(s -> s))
                .toList()
);
```

With `null`, `List.of(null)` is **illegal** because `List.of` rejects nulls. When testing null keys, use `Arrays.asList(...)` to construct inputs and expected outputs:

```java
import java.util.Arrays;

List<List<String>> nullableRuns =
        Arrays.<String>asList(null, null, "A", null)
              .stream()
              .gather(RunGatherers.consecutiveBy(s -> s))
              .toList();

checkEquals(
        Arrays.asList(
                Arrays.asList(null, null),
                Arrays.asList("A"),
                Arrays.asList((String) null)
        ),
        nullableRuns
);
```

The goal is verifying that `active` and `Objects.equals` handle null keys cleanly without mistaking null for "no group yet".

### Testing fixed and fullSliding

```java
import java.util.List;
import java.util.stream.Stream;

checkEquals(
        List.of(),
        Stream.<Integer>empty()
                .gather(FixedWindowGatherers.fixed(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2)),
        Stream.of(1, 2)
                .gather(FixedWindowGatherers.fixed(3))
                .toList()
);

checkEquals(
        List.of(),
        Stream.of(1, 2)
                .gather(WindowGatherers.fullSliding(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3)),
        Stream.of(1, 2, 3)
                .gather(WindowGatherers.fullSliding(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3), List.of(2, 3, 4)),
        Stream.of(1, 2, 3, 4)
                .gather(WindowGatherers.fullSliding(3))
                .toList()
);
```

Because the two Gatherers have different requirements, their results on inputs shorter than three elements **intentionally differ**. Tests should assert this difference rather than forcing both APIs to share one policy.

### Testing Early Termination and Snapshots

```java
List<List<Integer>> onlyFirst =
        Stream.of(1, 2, 3, 4, 5)
              .gather(FixedWindowGatherers.fixed(2))
              .limit(1)
              .toList();

checkEquals(List.of(List.of(1, 2)), onlyFirst);

List<List<String>> separateSnapshots =
        Stream.of("X", "X", "Y", "Y")
              .gather(RunGatherers.consecutiveBy(s -> s))
              .toList();

checkEquals(
        List.of(List.of("X", "X"), List.of("Y", "Y")),
        separateSnapshots
);
```

Verify that the first group does not turn empty when the second group is built. That catches the bug of emitting the same mutable `ArrayList` repeatedly.

## 15. Common Pitfalls When Writing Custom Gatherers

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Forgetting `finisher` in consecutive grouping | Final group is dropped | Emit remaining state when upstream finishes |
| Emitting raw buffer then calling `clear()` | Previously emitted groups/windows get mutated | Emit snapshot `new ArrayList<>(buffer)` |
| Ignoring `downstream.push(...)` return value | Keeps emitting after downstream stops | Return `false` and record cancellation if needed |
| Using `currentKey == key` for Strings/objects | Reference comparison instead of value equality | Use `Objects.equals` or proper business comparator |
| Calling `key.equals(...)` with nullable keys | `NullPointerException` | Use `Objects.equals` and an `active` flag |
| Using `groupingBy` instead of adjacent grouping | Merges non-adjacent segments with the same key | Use a boundary-aware stateful Gatherer |
| Sliding window fails to evict old elements | Buffer grows unboundedly, wrong window size | Remove head element when exceeding `k` |
| Using `ArrayDeque` while requiring null elements | `NullPointerException` | Choose an appropriate buffer or normalize inputs |
| Not validating `k > 0` | Nonsensical window emission behavior | Throw `IllegalArgumentException` |
| Assuming `windowFixed` and `windowSliding` are both non-overlapping | Misinterprets data semantics | Check slide step and emission points |
| Allowing windows to cross session boundaries | Semantically invalid statistics | Group sessions first, window within each session |
| Writing a combiner that concatenates adjacent ends without checking keys | Drops or mismerges groups at split boundaries | Use `ofSequential` or implement full boundary-merging logic |
| Enabling `parallel()` and assuming faster execution | Overhead may dominate; complex ordering | Measure on real data; never trade away correctness |
| Reading from `Files.lines` without closing source | Resource leak | Wrap in `try-with-resources` |
| Calling `toList()` on millions of long windows | Heavy memory growth retaining all outputs | Emit compact stats or stream outputs |

## 16. Ordering, I/O Sources, and Parallel Streams

Consecutive grouping requires a **meaningful encounter order**. On a time-ordered `List` of events, encounter order matches list position. With unordered sources or distributed multi-source data, never assume elements adjacent in the Stream are adjacent in business time.

If you use `sorted(Comparator.comparing(...))` to restore chronological order, remember `sorted` is stateful and may buffer extensively before emitting anything. When timestamps tie, define a deterministic tie-breaker such as a sequence number.

Never build a Gatherer whose combiner "just concatenates result lists" without handling **boundaries between left and right branches**: for example, if the left branch ends with `A` and the right branch starts with `A`, the left's tail group and the right's head group may need to merge. For a sliding window of size `k`, splitting also requires preserving up to `k - 1` boundary elements to form cross-boundary windows.

For those reasons, `ofSequential` is the right starting point for this exercise. If you later need a parallel-capable Gatherer, specify an associative combining operation that preserves ordering and semantics under every partition split.

### Resource Ownership Does Not Change Because of a Gatherer

Example processing streaks of matching error prefixes from a file:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<List<String>> consecutiveErrorLines(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> line.startsWith("ERROR:"))
                .gather(RunGatherers.consecutiveBy(
                        line -> line.substring(
                                0, Math.min(line.length(), 10))
                ))
                .toList();
    }
}
```

This example illustrates **resource lifecycle**, not a production log parser: taking the first ten characters as a key is purely an illustrative rule and unlikely to fit real log formats. Moreover, `filter` can make two `ERROR` lines separated by an `INFO` line become adjacent inside the pipeline; if the requirement is runs **consecutive in the original file**, move break logic into the Gatherer or keep boundary markers instead of filtering intermediate lines out.

`collect`, `toList`, `limit`, and `gather` **do not automatically close the Stream** returned by `Files.lines`. `try-with-resources` closes the source even when a terminal operation terminates early or throws an exception. If I/O fails during lazy traversal, it may surface as an `UncheckedIOException`.

## 17. From Exercise to Production Deployment

Before putting a custom Gatherer into an application, answer these questions:

1. **Does your JDK support the API?** Use Java 24+; do not assume the code runs on Java 8–21.
2. **What output is actually needed?** `List<T>`, a summary DTO, or an alert? Avoid retaining unneeded data.
3. **What defines group boundaries?** Key change, time interval, session ID, or a custom predicate?
4. **Is input ordering guaranteed?** If not, "consecutive" and "window" may lack stable meaning.
5. **How are windows shorter than `k` handled?** Emit partial, skip, or fail?
6. **Can inputs be null?** Clarify classifier, buffer, and result-type responsibilities.
7. **Is there a buffer size cap?** One huge run can create RAM pressure.
8. **Can downstream stop early?** When `push` returns `false`, integrator and finisher must coordinate not to over-emit.
9. **Is parallelism truly necessary?** Prove boundary state merging first.
10. **Does the source hold I/O?** Clarify ownership and close resources with `try-with-resources`.
11. **Have empty sources, single elements, repeated key flips, overlapping windows, and cancellation been tested?**
12. **Can a standard Gatherer replace a custom one?** When ordinary fixed or sliding windows suffice, `Gatherers.windowFixed`/`windowSliding` may be enough.

### Suggested Project Grading Rubric

| Criterion | Passing Standard |
| --- | --- |
| Correct consecutive runs | `A,A,B,A` yields three groups without merging the two `A` segments |
| Correct fixed windows | 8-element source with `k=3` yields chunks of size 3, 3, 2 |
| Correct full sliding windows | 5-element source with `k=3` yields 3 windows of size 3 |
| Snapshot isolation | Previously emitted outputs stay intact when buffer is reused |
| End-of-stream handling | Final group and final batch follow stated policy |
| Early termination | `limit(1)` produces no unexpected extra emissions |
| Boundary inputs | Empty source, `k <= 0`, and nulls handled explicitly |
| Resource management | I/O-backed Streams closed by their owning scope |
| Performance awareness | Evaluates memory and copying cost, not raw speed alone |
| API fit | Avoids complex custom Gatherers when standard APIs suffice |

## 18. Self-Check Questions

1. Is `gather` an intermediate or terminal operation? **Intermediate**; you can chain `map`, `filter`, `flatMap` afterward before a terminal operation.
2. Main difference between `groupingBy` and consecutive grouping? **`groupingBy` groups globally by key; consecutive grouping preserves adjacent runs in encounter order**.
3. Why does the last group need a finisher? **There is no subsequent key-changing element to trigger emitting the final group**.
4. Why copy the buffer before calling push? **To prevent downstream from seeing the same List cleared or mutated later**.
5. What should the integrator do when `Downstream.push` returns `false`? **Stop accepting more elements and avoid emitting leftover items unnecessarily**.
6. When does `ofSequential` fit? **When state depends on order and no boundary-combining operation has been proven correct**.
7. How many windows does `Gatherers.windowFixed(3)` emit on 8 elements? **Three**, of sizes 3, 3, and 2.
8. How many full windows does `Gatherers.windowSliding(3)` emit on five consecutive elements? **Three**, starting at positions 1, 2, and 3.
9. What does custom `fullSliding(3)` emit when the source has only two elements? **Nothing**, per its full-window-only contract.
10. Why does `ArrayDeque` in the example reject nulls? **That is a rule of `ArrayDeque`**, so the code validates inputs explicitly.
11. For `n` elements and full window size `k`, how many sliding windows are produced? **`max(0, n-k+1)`**.
12. Why is `consecutiveBy`'s memory not necessarily `O(1)`? **Because it buffers the entire active group; a group's length can grow up to n**.
13. Is concatenating two parallel branch outputs always right for consecutive groups? **No**, groups spanning the partition boundary must be handled.
14. If only per-streak counts are needed, what is the biggest improvement? **Store only key and counter, emitting a summary DTO instead of a List**.
15. When processing `Files.lines` through a Gatherer, does the terminal operation close the source automatically? **No**, `try-with-resources` is still required.

**Rule of thumb:** Writing Gatherers for consecutive groups and data windows starts with **defining boundaries, emission timing, and incomplete-tail policies**. Use `ofSequential` when results depend on adjacent elements, keep state minimal, emit independent snapshots, and respect downstream cancellation signals. Prefer `Gatherers.windowFixed`/`windowSliding` when standard contracts fit; build custom Gatherers only when business rules demand different behavior. Finally, verify correctness, I/O lifecycle, and memory costs before considering parallel optimization.
