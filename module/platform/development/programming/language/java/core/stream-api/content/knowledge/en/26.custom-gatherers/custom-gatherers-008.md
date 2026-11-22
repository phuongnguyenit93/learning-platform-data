# Building a Consecutive-Element Grouping Operator by Key

## 1. Problem: Grouping Consecutive Segments, Not Globally

In the **Java Stream API**, `filter` and `map` are suited for per-element processing; `groupingBy` groups elements with the same key across the **entire** stream. However, many log and event-stream problems require grouping **consecutive elements sharing the same key**, while **preserving boundaries when the key changes**.

For example, a system receives events in sequence:

```text
Input (in order):
A1  A2  A3  B1  B2  A4  C1  C2
│        │  │    │  │   │    │
└── A ───┘  └ B ─┘  A4  └ C ─┘

Desired result:
Run(A, [A1, A2, A3])
Run(B, [B1, B2])
Run(A, [A4])
Run(C, [C1, C2])
```

The two segments with key `A` **must not be merged into one**, because a `B` segment lies in between. This is *run-length grouping*, *group adjacent by key*, or *group consecutive elements by key*. It arises when needing to:

- Group consecutive identical states in an event stream.
- Merge log records having the same priority level over a contiguous interval.
- Build consecutive activity bursts for a device.
- Count state transitions or summarize each segment of a data stream.
- Convert records already sorted by key into chunks for downstream processing.

This lesson belongs to the **Building Custom Gatherers** chapter of the `JAVA_STREAM_API` module. We will build an operator to use like this:

```java
List<Run<String, Event>> runs = events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .toList();
```

Here `groupConsecutiveBy` is a **function we write ourselves**, returning a `Gatherer`. It is not a built-in method on `Gatherers` in the standard library.

**Java Version:** Stream Gatherers became an official feature in **Java 24** (JEP 485); they were previously in preview in Java 22 and Java 23. This lesson and the complete program use **JDK 24+** and do not require `--enable-preview` when compiling on JDK 24 or later. On Java 17/21, `Stream.gather` is not yet an available standard API.

## 2. Distinguishing groupingBy and Consecutive Grouping

Given elements with keys:

```text
A, A, B, A, B, B
```

The two requirements produce different results:

| Requirement | Interpretation | Result |
| --- | --- | --- |
| Global grouping | All elements with the same key belong to the same group | `A → [A,A,A]`; `B → [B,B,B]` |
| Consecutive grouping | When the key changes, the current group ends | `[A,A]`, `[B]`, `[A]`, `[B,B]` |

`Collectors.groupingBy(classifier)` is a terminal collector returning `Map<K, List<T>>`. It cannot retain **how many times a key appeared in separate segments** if it only stores one entry per key.

Conversely, the consecutive-grouping operator produces a **Stream of groups**. This enables chaining operations:

```java
events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .filter(run -> run.items().size() >= 2)
        .map(run -> run.key() + "=" + run.items().size())
        .forEachOrdered(System.out::println);
```

The output of `gather` remains a Stream and can continue with `map`, `filter`, `limit`, or `collect`. Each group is emitted as soon as it is known to have ended, or when the source finishes.

### Why Can't distinct or windowFixed Replace It?

`distinct` removes duplicate elements via `equals` rather than grouping elements into segments. `Gatherers.windowFixed(n)` forms fixed windows of count `n`, not based on where **keys change**. `groupingBy` merges across the entire source. Hence, consecutive grouping is a practical example for a **stateful Gatherer**.

## 3. Gatherer Architecture in Java 24

`java.util.stream.Gatherer<T, A, R>` is a protocol for an intermediate operation that can accumulate state and emit zero, one, or multiple output elements for input elements. Meaning of the three type parameters:

| Type Parameter | Meaning in This Lesson |
| --- | --- |
| `T` | One input element, e.g., `Event`. |
| `A` | Internal accumulated state, e.g., current key and list of records in the segment. |
| `R` | One output element, e.g., `Run<String, Event>`. |

Components of a Gatherer:

1. **Initializer:** creates a fresh state `A` for an evaluation pass.
2. **Integrator:** receives `(state, element, downstream)`, updates state, and may emit new elements via `downstream.push(...)`.
3. **Combiner:** defines how to merge states of parallel split segments if the Gatherer supports parallel processing at this stage.
4. **Finisher:** invoked when no more input remains to consume; can emit final results still held in state.

For consecutive grouping, boundaries depend on **element order**, so we intentionally use a **sequential Gatherer**:

```java
Gatherer.ofSequential(
        initializer,
        integrator,
        finisher
)
```

The conceptual signature used is:

```java
static <T, A, R> Gatherer<T, A, R> ofSequential(
        Supplier<A> initializer,
        Gatherer.Integrator<A, T, R> integrator,
        BiConsumer<A, Gatherer.Downstream<? super R>> finisher
)
```

A Gatherer built with `ofSequential` does not supply a combiner capable of merging state at arbitrary boundaries. This is **the right choice first**: splitting a stream in parallel can slice a group in half, and a naive merge yields wrong results.

### Downstream.push and Stop Signals

Inside the integrator, `downstream.push(output)` passes a completed group to the next stage. Its `boolean` return value indicates whether downstream **still accepts more output**. When it returns `false`, the integrator must **stop requesting further inputs** by returning `false`.

This signal matters if the downstream pipeline uses `limit(n)` or another short-circuiting terminal operation. Never ignore the return value of `push` and keep processing the source needlessly.

## 4. Minimum State to Store

A consecutive-grouping operator needs to know:

- **Has a group started?** `active`, to distinguish the no-element-yet state from when the actual current key is `null`.
- **Current key:** `key`, compared against the incoming element's key.
- **Elements of the current group:** `items`, the list currently accumulating.

```text
Before receiving input:
active=false, key=(none), items=[]

Receive A1:
active=true, key=A, items=[A1]

Receive A2:
key still A, items=[A1,A2]

Receive B1:
emit Run(A,[A1,A2])
switch to key=B, items=[B1]

End of source:
emit Run(B,[B1])
```

**Invariant** to uphold: whenever `active=true`, `items` contains **the exact elements of the currently open segment**, in encounter order, and all share `key` under the chosen equality rule.

Do not use `key == null` to mean "no group yet", because the classifier may validly return `null`. Instead, `active` represents that state separately.

### Why Must a Copy Be Taken Before Emitting?

If you emit `items` directly and then call `items.clear()` to begin a new group, **the just-emitted group can become empty too**, because downstream still holds a reference to the same List.

Wrong:

```java
downstream.push(new Run<>(state.key, state.items));
state.items.clear(); // Can wipe out data of the emitted Run.
```

Right: create a **snapshot** of the group before emitting:

```java
List<T> snapshot = Collections.unmodifiableList(
        new ArrayList<>(state.items)
);
downstream.push(new Run<>(state.key, snapshot));
```

`Collections.unmodifiableList` prevents mutating **list structure** through the result, while `new ArrayList<>(...)` breaks sharing with the reused buffer. This is still a **shallow copy**: mutable element objects must be handled separately if deep immutability is required.

## 5. Integrator Algorithm: Three Cases

For each new element `element`, compute:

```java
K nextKey = classifier.apply(element);
```

Then consider three cases:

| State | Action | Emit a group immediately? |
| --- | --- | --- |
| No group open (`!active`) | Open a new group with `nextKey` and `element` | No |
| `Objects.equals(key, nextKey)` | Append element to the open group | No |
| Different key | Emit snapshot of old group, then open a new group | Yes |

Pseudocode:

```text
integrate(state, element, downstream):
    nextKey = classifier(element)
    if no group open:
        open group(nextKey, element)
        return true

    if old key equals nextKey:
        append element
        return true

    emit snapshot of old group
    if downstream accepts no more:
        mark group closed
        return false

    open new group(nextKey, element)
    return true
```

Looking at the condition, **there is no need to buffer the entire source**. During processing, the Gatherer holds only **one open group**. Previous groups have already been emitted and can immediately flow through the rest of the pipeline.

At the same time, there is a trade-off: to know a group has ended, the Gatherer must **read the first element of the next group**. Thus, when downstream only asks for `limit(1)` group, upstream may have had to process the first element of the second group in order to emit the first group.

## 6. Finisher: Do Not Forget the Final Group

Suppose input is `[A,A,B]`. Upon seeing `B`, the integrator emits group `A`. After `B`, however, no more elements arrive to trigger a "key change", so group `B` must be emitted in the **finisher**.

```java
(state, downstream) -> {
    if (state.active && !downstream.isRejecting()) {
        downstream.push(new Run<>(
                state.key,
                Collections.unmodifiableList(
                        new ArrayList<>(state.items)
                )
        ));
    }
}
```

**Empty source** case: `active=false`, so finisher emits no spurious group. With a single element: finisher emits one group containing that element. If the source ends right after a key switch, finisher emits the newly opened group.

`downstream.isRejecting()` avoids trying to emit more when downstream no longer wants output. Furthermore, if the integrator already stopped after `push` returned `false`, we **close the group in state** to prevent the finisher from emitting redundantly.

**Do not treat the finisher as another "pass" over inputs:** it solely finalizes data already accumulated and not yet emitted. It should never read more source items or revisit processed elements.

## 7. Complete Java 24+ Program: groupConsecutiveBy

The following program defines a reusable Gatherer, decoupled from any specific event class. `Run<K,T>` represents one consecutive segment: a key and the list of elements in that segment.

Save as `ConsecutiveKeyGathererDemo.java`, compile and run with **JDK 24+**.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Gatherer;

public class ConsecutiveKeyGathererDemo {
    record Event(String id, String type, int value) {}
    record Run<K, T>(K key, List<T> items) {}

    static <T, K> Gatherer<T, ?, Run<K, T>> groupConsecutiveBy(
            Function<? super T, ? extends K> classifier) {
        Objects.requireNonNull(classifier, "classifier");

        class State {
            boolean active;
            K key;
            final ArrayList<T> items = new ArrayList<>();
        }

        return Gatherer.ofSequential(
                State::new,

                (state, element, downstream) -> {
                    K nextKey = classifier.apply(element);

                    // Start the first group.
                    if (!state.active) {
                        state.active = true;
                        state.key = nextKey;
                        state.items.add(element);
                        return true;
                    }

                    // Still inside a consecutive segment.
                    if (Objects.equals(state.key, nextKey)) {
                        state.items.add(element);
                        return true;
                    }

                    // Key changed: emit snapshot of the previous segment.
                    Run<K, T> completed = new Run<>(
                            state.key,
                            Collections.unmodifiableList(
                                    new ArrayList<>(state.items)
                            )
                    );

                    if (!downstream.push(completed)) {
                        // Downstream accepts no more; do not open a new group.
                        state.active = false;
                        state.items.clear();
                        return false;
                    }

                    // Start a new segment from the current element.
                    state.key = nextKey;
                    state.items.clear();
                    state.items.add(element);
                    return true;
                },

                (state, downstream) -> {
                    // Flush the final segment when the source ends.
                    if (state.active && !downstream.isRejecting()) {
                        downstream.push(new Run<>(
                                state.key,
                                Collections.unmodifiableList(
                                        new ArrayList<>(state.items)
                                )
                        ));
                    }
                }
        );
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event("A1", "A", 10),
                new Event("A2", "A", 20),
                new Event("A3", "A", 30),
                new Event("B1", "B", 40),
                new Event("B2", "B", 50),
                new Event("A4", "A", 60),
                new Event("C1", "C", 70),
                new Event("C2", "C", 80)
        );

        List<Run<String, Event>> runs = events.stream()
                .gather(groupConsecutiveBy(Event::type))
                .toList();

        for (Run<String, Event> run : runs) {
            List<String> ids = run.items().stream()
                    .map(Event::id)
                    .toList();
            System.out.println(run.key() + " -> " + ids);
        }

        // A -> [A1, A2, A3]
        // B -> [B1, B2]
        // A -> [A4]
        // C -> [C1, C2]

        if (runs.size() != 4
                || !runs.get(0).key().equals("A")
                || runs.get(0).items().size() != 3
                || !runs.get(1).key().equals("B")
                || runs.get(1).items().size() != 2
                || !runs.get(2).key().equals("A")
                || runs.get(2).items().size() != 1
                || !runs.get(3).key().equals("C")
                || runs.get(3).items().size() != 2) {
            throw new AssertionError("Incorrect consecutive groups");
        }

        List<Run<String, Event>> firstTwo = events.stream()
                .gather(groupConsecutiveBy(Event::type))
                .limit(2)
                .toList();

        if (firstTwo.size() != 2
                || !firstTwo.get(0).key().equals("A")
                || !firstTwo.get(1).key().equals("B")) {
            throw new AssertionError("Incorrect early termination");
        }

        System.out.println("PASS");
    }
}
```

If the environment uses JDK 24 or newer:

```text
javac ConsecutiveKeyGathererDemo.java
java ConsecutiveKeyGathererDemo
```

No external libraries are needed. The code uses `Stream.gather` and `java.util.stream.Gatherer`, which are official in Java 24. The lesson **does not run compilation at STEP 4**; when applying in practice, use the right JDK version and test against the project's build.

## 8. Why Is This Implementation Correct?

Review the trace:

```text
Receive A1: state=A/[A1], not emitted
Receive A2: state=A/[A1,A2], not emitted
Receive A3: state=A/[A1,A2,A3], not emitted
Receive B1: emit A/[A1,A2,A3], state=B/[B1]
Receive B2: state=B/[B1,B2], not emitted
Receive A4: emit B/[B1,B2], state=A/[A4]
Receive C1: emit A/[A4], state=C/[C1]
Receive C2: state=C/[C1,C2], not emitted
Source ends: finisher emits C/[C1,C2]
```

Properties to verify:

1. **Completeness:** every element is placed into exactly one group, unless downstream stops early.
2. **Non-overlapping:** when the key changes, the old group finishes emitting before the new group is formed.
3. **Maximality:** no key boundary exists within a group; two adjacent groups cannot have equal keys given a consistent classifier.
4. **Order preservation:** elements inside a group preserve the input Stream's encounter order; groups are emitted in exact sequence.
5. **No retroactive merging:** key `A` appearing after segment `B` creates a new group `A`.
6. **Final closure:** finisher emits the last group even with no subsequent element.
7. **No shared buffer:** each output holds its own snapshot, unaffected by `clear()` on later groups.
8. **Early stop:** if downstream rejects, the integrator returns `false` and does not try to open new groups.

### Why Return true in Branches That Emit Nothing?

An integrator returning `true` means **able to keep receiving inputs**, not "an output was emitted". While a group is accumulating and not yet closed, emitting nothing is normal. A Gatherer can emit 0 or more elements per input element.

### Why Not Use state.key == nextKey?

For `String` keys, `new String("A")` and `"A"` can be two distinct object references with equal values. `Objects.equals(state.key, nextKey)` uses `equals`, while also supporting `null` keys if application policy permits.

## 9. Handling Downstream Early Stop and limit

Example:

```java
List<Run<String, Event>> firstTwo = events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .limit(2)
        .toList();
```

In the sample data, the first two groups are `A` and `B`. To emit group `B`, the Gatherer must receive element `A4` (the start of the third group). At that moment downstream can report no more wanted via `push`, causing the integrator to return `false`.

This is a property of **boundary-dependent operators**: a group only surely ends upon seeing a different key or knowing the source has ended.

```text
Receive A1,A2,A3: no complete group yet
Receive B1:       emit Run(A)
Receive B2:       Run(B) not emitted yet
Receive A4:       emit Run(B); limit(2) has enough results
                   -> downstream rejects more
                   -> integrator stops
```

An important detail is never assuming `limit(2)` means **reading only two source elements**. Here the limit applies to **output group count**, not input event count.

Furthermore, other callbacks in a pipeline may have processed some elements depending on execution strategy. Hence, do not place mandatory side effects, such as sending emails or charging money, inside the classifier assuming it runs a predictable number of times.

### Stop Condition from the Integrator

`Integrator.integrate` returns `false` to signal it wants no further input. In our implementation, this occurs when `downstream.push(completed)` returns `false`. When that happens:

- Do not open a group for the element that triggered the key change.
- Set `state.active=false` and clear the buffer to prevent re-emission in the finisher.
- Never reuse state for another Stream consumption.

If the classifier or downstream throws an exception, the exception propagates out to the terminal operation. Do not treat the finisher as an automatic error-recovery or side-effect rollback mechanism.

## 10. Empty Source, Single Element, Nulls, and Key Types

### Empty Source

```java
List<Run<String, Event>> noRuns =
        java.util.stream.Stream.<Event>empty()
                .gather(groupConsecutiveBy(Event::type))
                .toList();

System.out.println(noRuns.isEmpty()); // true
```

Initializer creates state with `active=false`, integrator is never called, and finisher emits nothing.

### Single Element

```java
List<Run<String, Event>> oneRun =
        java.util.stream.Stream.of(new Event("E1", "A", 10))
                .gather(groupConsecutiveBy(Event::type))
                .toList();

System.out.println(oneRun.size());            // 1
System.out.println(oneRun.get(0).items().size()); // 1
```

The single group is emitted in the finisher.

### Null Keys

`Objects.equals` allows two `null` keys to be treated as equal:

```java
record Label(String text) {}

List<Label> labels = java.util.Arrays.asList(
        new Label(null), new Label(null),
        new Label("X"), new Label(null)
);

List<Run<String, Label>> groups = labels.stream()
        .gather(groupConsecutiveBy(Label::text))
        .toList();

System.out.println(groups.size());  // 3
System.out.println(groups.get(0).key()); // null
System.out.println(groups.get(0).items().size()); // 2
```

In the Gatherer factory, `Objects.requireNonNull(classifier)` only checks that **the classifier function is non-null**, not that **returned key values** must be non-null. If your product forbids null keys, validate inputs or map them to a sentinel value with clear semantics.

### Null Elements

A snapshot list from `Collections.unmodifiableList(new ArrayList<>(...))` can contain null elements, yet a classifier like `Event::type` throws `NullPointerException` upon receiving `element=null`. If the source contains nulls, define a policy:

```java
List<Run<String, Event>> safe =
        possiblyNullEvents.stream()
                .filter(Objects::nonNull)
                .gather(groupConsecutiveBy(Event::type))
                .toList();
```

This snippet illustrates with a `possiblyNullEvents` variable prepared at the call site. **Filtering out null elements** can cause two segments of the same key previously separated by a null element to become adjacent. If null must act as a **boundary**, do not filter it out; instead define a key/element explicitly representing that boundary.

## 11. Encounter Order Is an Essential Condition

A **consecutive** grouping operator directly depends on encounter order. With `List.stream()`, element order follows the List, so boundaries are uniquely defined.

```java
List<String> keys = List.of("A", "A", "B", "A");

List<Run<String, String>> runs = keys.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .toList();

// Run(A,[A,A]), Run(B,[B]), Run(A,[A])
```

However, if the source is a `HashSet`, traversal order **is not guaranteed**, so "consecutive" segments carry no stable business meaning:

```java
Set<String> unorderedSource =
        new java.util.HashSet<>(List.of("A", "B", "C"));

// Do not treat consecutive grouping results from this source
// as historical segments with fixed order.
```

If data has a `sequence`, `timestamp`, or index field, **establish order before grouping**:

```java
List<Event> ordered = events.stream()
        .sorted(Comparator.comparing(Event::id))
        .toList();

List<Run<String, Event>> sortedRuns = ordered.stream()
        .gather(groupConsecutiveBy(Event::type))
        .toList();
```

Note: the comparator by `id` here is only a technical illustration. In real logs, choose **timestamp, sequence, and tie-breakers** with accurate semantics; sorting data by the grouping key itself would **change the requirement** by collapsing separate segments into one large group.

### Do Not Call unordered() When Historical Segments Are Needed

`unordered()` drops the encounter-order constraint. It does not mean "shuffle" randomly, yet allows operations to stop preserving source order. For sequential consecutive grouping, dropping order makes **the output definition unstable**.

## 12. Why Not Write a Parallel Combiner Yet?

The difficulty lies at boundaries between split segments. For example:

```text
Input: A A A A B B C

Work split:
  Left:  A A A
  Right: A B B C

Local groups:
  Left:  [A,A,A]
  Right: [A], [B,B], [C]

Naive merge:
  [A,A,A], [A], [B,B], [C]   <- WRONG

Correct merge:
  [A,A,A,A], [B,B], [C]
```

To support a true parallel combiner, each partition's state must retain enough information about **its first group**, **its last group**, and complete middle groups. When merging two parts, you must check whether the left's last group shares a key with the right's first group and fuse them while preserving order. That is no longer a simple `List.addAll`.

`Gatherer.ofSequential` avoids this by **not supplying a combiner to split/merge Gatherer state**. If the pipeline starts from `parallelStream()`, do not assume this Gatherer stage is automatically parallelized effectively; ordering constraints can negate parallel gains.

**Lesson priority:** write a correct sequential Gatherer with boundary tests; only design a combiner when truly needed and after mathematically modeling how two segments merge, including head/tail, empty groups, and *associativity*.

## 13. Statefulness, Non-Interference, and Memory Safety

A Gatherer having internal state **is not equivalent to a pipeline violating stateless/non-interference rules**. The difference is:

- The Gatherer uses **state created specifically for the evaluation pass by its initializer**, per API contract.
- The classifier should be a function that **does not mutate the source**, nor write to shared lists or Maps.
- Never keep accumulated state in a global or `static` variable reused across multiple Stream invocations.
- Downstream must receive an **isolated snapshot** if state will continue being mutated.

Flawed design example:

```java
static List<Event> sharedBuffer = new ArrayList<>();

// WRONG: using sharedBuffer as the buffer for all evaluations
// can cause leftover data and race conditions.
```

Better: create the buffer inside a fresh `State` object initialized by `State::new`.

Another limitation: `Run` elements are only **reference-copied**, not automatically deep-copied. If `Event` holds mutable fields such as `List<String>` or an object with setters, elements can still be mutated externally. For DTOs needing deep immutability, map or copy elements into immutable values before grouping.

### Memory Usage

With `n` elements and longest segment of length `m`:

- The Gatherer's accumulation buffer holds at most about `m` element references at a time.
- Snapshotting a segment copies that segment's references; total references copied across all segments is `n` if the full source is consumed.
- The Gatherer itself does not retain previously emitted segments. If you call `toList()` after `gather`, **the final result** still stores all groups and their elements, growing overall memory proportional to `n`.
- If a segment is very long or the source never changes keys, the first output is delayed and the buffer can grow very large.

On a truly infinite stream where the key never changes, this Gatherer **cannot emit a complete group**. In that case you need another segment-closing rule, such as maximum element count, timeout, or time window.

## 14. Aggregating Statistics for Each Segment

Since `gather` returns a Stream of `Run`s, we can continue building reports:

```java
record RunSummary(
        String type, long count, long totalValue) {}

List<RunSummary> summaries = events.stream()
        .gather(groupConsecutiveBy(Event::type))
        .map(run -> new RunSummary(
                run.key(),
                run.items().size(),
                run.items().stream()
                        .mapToLong(Event::value)
                        .sum()
        ))
        .toList();

summaries.forEach(System.out::println);
```

Output on sample data:

```text
RunSummary[type=A, count=3, totalValue=60]
RunSummary[type=B, count=2, totalValue=90]
RunSummary[type=A, count=1, totalValue=60]
RunSummary[type=C, count=2, totalValue=150]
```

Notably, there are **two** `RunSummary` entries with type `A`, because they are two separate segments in the event stream. Using `groupingBy(Event::type, summingLong(...))` would yield **one** `A` entry with sum `120`, losing information about returning to state `A`.

### Counting State Transitions

If the source is non-empty and every key change starts a new group, then:

```text
Number of key transitions = Number of consecutive groups - 1
```

In the example with 4 groups, there are 3 key transitions: `A→B`, `B→A`, `A→C`. If the source is empty, transition count is 0; in code you can write `Math.max(0, runs.size() - 1)`.

When only group counts or summary stats are needed, you can emit `RunSummary` directly instead of keeping the whole List of elements; that is an optimization direction for large datasets once you master the basic mechanism.

## 15. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Two separated segments with the same key get merged into one | Using global `groupingBy` | Use a stateful Gatherer and emit when key changes. |
| The last group is lost | Only emitting inside integrator upon seeing a new key | Add a finisher to flush the remaining open group. |
| Previous group result suddenly turns empty | Pushed buffer reference then called `clear()` | Create a snapshot before `push`. |
| Empty source emits one empty group | Finisher emits even when no group opened | Use an `active` flag and emit only when true. |
| Null key treated as uninitialized | Using `key == null` to detect empty state | Use a separate `boolean active`. |
| Two strings with equal content become two groups | Comparing keys with `==` | Use `Objects.equals` or a clearly defined equivalent comparator. |
| Elements no longer consumed yet integrator keeps running | Ignoring `downstream.push` returning `false` | Return `false` from integrator, avoid opening new groups. |
| Finisher emits redundantly after early stop | Did not close state when downstream rejected | Mark `active=false` before returning `false`. |
| Group mutates after result is emitted | Elements contain mutable objects mutated outside | Convert to immutable values / deep-copy if required by business rules. |
| Unstable group order | Unordered source or dropped order | Establish event encounter order before gathering. |
| Parallel run produces wrong groups at split boundaries | Combiner merely concatenates two group lists | Design a combiner merging adjacent boundary groups, or use `ofSequential`. |
| High memory usage when one key runs long | Buffer holds the entire unclosed segment | Add secondary split rules, emit summary stats, or bound input. |
| Code fails to compile on JDK 17/21 | `Stream.gather` is not a standard API in that version | Use JDK 24+ or an alternative sequential solution for that version. |

## 16. Practice Exercises and Solutions

### Exercise 1 — Count Consecutive Segments

Given sequence:

```java
List<String> values =
        List.of("X", "X", "Y", "X", "X", "Z", "Z", "Z");
```

**Prompt:** group consecutive elements and print group count, element count per group, and number of key transitions.

**Reference Solution:**

```java
List<Run<String, String>> runs = values.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .toList();

List<Integer> lengths = runs.stream()
        .map(run -> run.items().size())
        .toList();

System.out.println(lengths); // [2, 1, 2, 3]
System.out.println(runs.size()); // 4
System.out.println(Math.max(0, runs.size() - 1)); // 3
```

### Exercise 2 — Group Numbers by Parity

Given:

```java
List<Integer> numbers =
        List.of(2, 4, 7, 9, 12, 5, 3, 8);
```

**Prompt:** group each consecutive run sharing the same even/odd parity.

```java
List<Run<Boolean, Integer>> parityRuns = numbers.stream()
        .gather(groupConsecutiveBy(n -> n % 2 == 0))
        .toList();

parityRuns.forEach(run ->
        System.out.println(run.key() + " -> " + run.items()));

// true  -> [2, 4]
// false -> [7, 9]
// true  -> [12]
// false -> [5, 3]
// true  -> [8]
```

### Exercise 3 — Test Empty Source, Single Element, and Final Group

**Prompt:** create three test cases:

1. Empty source → 0 groups.
2. Single element `A` → one group containing `A`.
3. `[A, A, B]` → two groups; group `B` must be emitted by the finisher.

```java
List<Run<String, String>> empty =
        java.util.stream.Stream.<String>empty()
                .gather(groupConsecutiveBy(Function.identity()))
                .toList();

List<Run<String, String>> single =
        java.util.stream.Stream.of("A")
                .gather(groupConsecutiveBy(Function.identity()))
                .toList();

List<Run<String, String>> lastRun =
        java.util.stream.Stream.of("A", "A", "B")
                .gather(groupConsecutiveBy(Function.identity()))
                .toList();

System.out.println(empty.size()); // 0
System.out.println(single.get(0).items()); // [A]
System.out.println(lastRun.get(1).items()); // [B]
```

### Exercise 4 — Test Snapshots and Early Termination

**Prompt:** collect results from `[A,A,B,B,C]` and verify:

- Each group list retains its values after subsequent groups are processed.
- Elements cannot be added to the snapshot List.
- `limit(2)` emits only two complete groups.

```java
List<String> data = List.of("A", "A", "B", "B", "C");

List<Run<String, String>> all = data.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .toList();

System.out.println(all.get(0).items()); // [A, A]
System.out.println(all.get(1).items()); // [B, B]
System.out.println(all.get(2).items()); // [C]

// all.get(0).items().add("X");
// UnsupportedOperationException

List<Run<String, String>> firstTwo = data.stream()
        .gather(groupConsecutiveBy(Function.identity()))
        .limit(2)
        .toList();

System.out.println(firstTwo.size()); // 2
```

### Exercise 5 — Sum Each Segment Without Merging Globally

**Prompt:** given event sequence `A(10), A(20), B(7), A(5)`, compute the sum for **each segment** in order.

```java
List<Event> input = List.of(
        new Event("E1", "A", 10),
        new Event("E2", "A", 20),
        new Event("E3", "B", 7),
        new Event("E4", "A", 5)
);

List<String> totals = input.stream()
        .gather(groupConsecutiveBy(Event::type))
        .map(run -> run.key() + ":" + run.items().stream()
                .mapToInt(Event::value)
                .sum())
        .toList();

System.out.println(totals); // [A:30, B:7, A:5]
```

### Exercise 6 — Analyze Special Cases

Answer:

1. If key `A` appears again after key `B`, why must a new `A` group be created?
2. If the classifier returns `null` for two consecutive elements, what does the `active` flag help with?
3. If `sorted(Comparator.comparing(Event::type))` is called before the Gatherer, do the results still represent consecutive segments **in the original history**?
4. Why is a combiner that only calls `addAll` on two group lists wrong when two segments share a key at the boundary?
5. If the source is an infinite Stream of all key `A` elements, can the Gatherer emit a first complete group?

**Answer Guidance:** (1) because boundary `B` separates them; (2) distinguishes "not started yet" from "actual key is null"; (3) no, order was altered; (4) the left's last group and right's first group must be merged if keys match; (5) no, unless an additional group-closing condition is designed.

## 17. Checklist Before Using in a Project

1. **Version:** using JDK 24+ for official `Stream.gather` and `Gatherer` APIs.
2. **Key contract:** is the classifier stateless, non-interfering, with clear equality semantics?
3. **Encounter order:** does the source have business order? Is `unordered()` called anywhere?
4. **Fresh state:** does initializer create an independent state for each evaluation pass?
5. **First group:** does the first element open a group without creating an empty group?
6. **Same key:** is each element appended exactly once to the buffer?
7. **Key change:** is the old group emitted before starting the new group?
8. **Snapshot:** is output isolated from the buffer that will be reused?
9. **Finisher:** is the final group emitted, while an empty source emits nothing?
10. **Early stop:** does the integrator check `push` returning false and stop cleanly?
11. **Nulls:** do null keys and null elements have an explicit policy?
12. **Parallel:** is it documented why `ofSequential` is used instead of writing a broken combiner?
13. **Resources:** for I/O sources, is the Stream closed with proper `try-with-resources`?
14. **Memory:** how big can the longest segment be? Are time/count limits needed?
15. **Tests:** tested empty source, single element, returning keys, multiple groups, limit, snapshots, and ordered/unordered inputs?

## Takeaways

The **consecutive grouping by key** operator differs fundamentally from `Collectors.groupingBy`: only elements **adjacent in encounter order** with equal keys belong to the same group. A single key can appear in multiple groups if interrupted by another key.

With **Java 24+**, `Gatherer.ofSequential` is the right starting point to build this operator yourself. **Initializer** creates the open-group state; **integrator** appends elements or emits the old group when the key changes; **finisher** emits the final group when the source ends. Always copy the buffer before `downstream.push`, obey downstream rejection signals, and keep the classifier non-interfering.

Only after boundaries, order, early termination, and state are verified should you consider memory optimizations or designing a parallel combiner. When segments can grow too long or an infinite stream never changes keys, add an explicit segment-closing condition instead of waiting for a boundary that will never arrive.
