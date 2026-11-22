# Composing Gatherers with andThen

> **Chapter:** Stream Gatherer  
> **Module:** JAVA_STREAM_API  
> **Focus:** Understand and use `Gatherer.andThen(...)` to compose multiple custom Stream transformations into a reusable Gatherer. This lesson connects lazy pipelines, `filter`/`map`, collectors, Spliterator, and parallel processing; paying special attention to input/output types, composition order, state, `finisher`, short-circuiting, and performance.

## Learning objectives

After this lesson, you will be able to:

1. Explain the purpose of `Gatherer`, `Stream.gather(...)`, and the `Gatherer.andThen(...)` method.
2. Read generic signatures accurately, understanding the type flow `T → R → RR` and the private role of state `A`.
3. Demonstrate by example that `stream.gather(a.andThen(b))` is **semantically** equivalent to `stream.gather(a).gather(b)`.
4. Distinguish **sequential composition** (*composition*) from concatenating results (*concat*), zipping two branches (*zip*), and terminal collectors.
5. Build pipelines from standard Gatherers: `windowFixed`, `windowSliding`, `scan`, `fold`, and `mapConcurrent`.
6. Write simple Gatherers using `Gatherer.of(...)` or `Gatherer.ofSequential(...)` and compose them with standard Gatherers.
7. Explain how a Gatherer can emit 0, 1, or many elements, emit final results in `finisher`, and signal stop when downstream accepts no more.
8. Handle empty sources, incomplete final windows, data ordering, null errors, and memory limits.
9. Understand why composing Gatherers **does not automatically produce a valid combiner**, does not guarantee speedup in parallel, and does not replace resource management.
10. Test chains using an independent reference pipeline, boundary data, and ordering/result invariants.

**Version requirement:** Main examples use **Java 24 or later**, where Stream Gatherers became a standard API under **JEP 485**. Gatherers were previously introduced as a *preview* in **JDK 22 (JEP 461)** and **JDK 23 (JEP 473)**. Java 24 code in this lesson does not need `--enable-preview` just to use `Gatherer`. Java 8, 11, 17, and 21 **do not** include `Stream.gather`/`Gatherer.andThen` as standard APIs.

This is a self-contained knowledge lesson of the `JAVA_STREAM_API` module, not a guide to enabling previews on older JDKs. All examples importing `java.util.stream.Gatherer` or `Gatherers` target the Java 24+ API.

---

## 1. Why does Stream need Gatherer and andThen composition?

Traditional Streams provide `filter`, `map`, `flatMap`, `distinct`, `sorted`, `reduce`, and `collect`. They handle many problems, yet some intermediate transformations are awkward to express concisely:

- **Window packaging:** emit a `List` every three elements.
- **Running totals:** emit the sum seen so far after each element.
- **Private state retention:** emit a record when it differs from the one immediately before it.
- **Emit-on-completion only:** fold the entire sequence into a single element.
- **Bounded concurrent work:** execute a mapper with a concurrency cap.

`Gatherer<T,A,R>` allows defining such intermediate transformations. When two steps must run back-to-back, `andThen` chains them into **one new Gatherer**:

~~~text
Stream<T>
    |
    v
Gatherer A: T -> R
    |
    | R elements emitted by A
    v
Gatherer B: R -> RR
    |
    v
Stream<RR>
    |
    v
terminal operation: toList / count / findFirst / collect...
~~~

Workflow example:

~~~text
Order counts:         [10, 20, 30, 40, 50]
                              |
                    windowFixed(2)
                              |
                       [[10,20],
                        [30,40],
                        [50]]
                              |
                     map each window
                              |
                        [30, 70, 50]
                              |
                      scan running sum
                              |
                        [30,100,150]
~~~

Here `windowFixed` changes "one element" from `Integer` to `List<Integer>`. The next Gatherer can sum each list, and another Gatherer can compute the running total.

**Core point:** `andThen` connects **the output of the previous step** to **the input of the next step**. It does not concatenate two independent result lists, does not run two branches side by side, and does not replace a terminal operation.

---

## 2. API map: Gatherer, Gatherers, and Stream.gather

Related components in `java.util.stream`:

| API | Role | Usage level |
|---|---|---|
| `Gatherer<T,A,R>` | Contract of a potentially stateful intermediate transformation | Defining or referencing a Gatherer |
| `Gatherer.andThen(that)` | Feeds the output of the current Gatherer into the next Gatherer | **Lesson focus** |
| `Stream.gather(gatherer)` | Attaches a Gatherer to a Stream pipeline | When executing a pipeline |
| `Gatherers.windowFixed(n)` | Splits source into consecutive groups of size n | Standard Gatherer |
| `Gatherers.windowSliding(n)` | Emits sliding windows | Standard Gatherer |
| `Gatherers.scan(initial, scanner)` | Emits accumulated value after each input | Standard Gatherer |
| `Gatherers.fold(initial, folder)` | Emits one aggregated value upon completion | Standard Gatherer |
| `Gatherers.mapConcurrent(k, mapper)` | Transforms each element with bounded concurrency | Standard Gatherer |
| `Gatherer.of(...)` | Creates a Gatherer that may have a combiner | Custom Gatherer |
| `Gatherer.ofSequential(...)` | Creates a Gatherer with sequential processing semantics | Custom Gatherer |

Distinguish the names:

- `Gatherer` (singular): the **interface** of an intermediate operation.
- `Gatherers` (plural): utility class providing **built-in Gatherers**.
- `Collector`: collects at the **end** of a pipeline; `Gatherer` transforms **in the middle** of a pipeline.
- `Gatherer.andThen`: composes **two Gatherers**, not `Consumer.andThen` or `Function.andThen`.

### 2.1. Full structure of a Gatherer

A Gatherer can define:

1. `initializer()` — creates private state `A`.
2. `integrator()` — receives element `T`, updates state, and may emit `R` elements.
3. `combiner()` — merges intermediate states when gathering supports parallelism.
4. `finisher()` — performs final actions when integration finishes, potentially emitting extra elements.

~~~text
                     +------------------------+
Input T ------------>| integrator(state, T)   |
                     |       |                |
                     |       +---- push(R) ---+----> Downstream
                     +------------------------+
                               |
                       state A mutates
                               |
                      after completion
                               |
                               v
                       finisher(state)
                               |
                          push(R) if needed
~~~

**Not every Gatherer uses all four parts.** A simple stateless Gatherer may only need `integrator`. A windowing or running-total Gatherer needs state; a `fold`-style Gatherer may wait until `finisher` to emit its result.

---

## 3. Exact signature of andThen

Conceptual signature in Java 24:

~~~java
default <RR> Gatherer<T, ?, RR> andThen(
        Gatherer<? super R, ?, ? extends RR> that
);
~~~

Suppose the initial Gatherer has type:

~~~java
Gatherer<T, A, R> first;
~~~

then `that` must accept the `R` elements emitted by `first`. The result is a new Gatherer:

~~~java
Gatherer<T, ?, RR> combined = first.andThen(that);
~~~

Type-reading table:

| Symbol | Meaning | Example |
|---|---|---|
| `T` | Input of **the entire chain** | `Integer` |
| `A` | Private state of the first Gatherer | E.g. state used to collect windows |
| `R` | Output of the first step, **input of the next step** | `List<Integer>` |
| `RR` | Output of **the entire chain** | `Integer` |
| `?` | Internal state details hidden from the chain's API | Combined state of the two Gatherers |

### 3.1. Why `? super R` and `? extends RR`?

- `? super R`: the second Gatherer can accept `R` itself or an appropriate **supertype**.
- `? extends RR`: the second Gatherer can emit `RR` or a **subtype** usable as `RR`.

For example, a Gatherer emitting `Integer` can be chained into a Gatherer accepting `Number`, because every `Integer` is a `Number`.

~~~java
import java.util.stream.Gatherer;

Gatherer<Integer, ?, Integer> increment =
        Gatherer.<Integer, Integer>of(
                (ignored, n, downstream) ->
                        downstream.push(n + 1)
        );

Gatherer<Number, ?, String> formatNumber =
        Gatherer.<Number, String>of(
                (ignored, n, downstream) ->
                        downstream.push("n=" + n)
        );

Gatherer<Integer, ?, String> chain =
        increment.andThen(formatNumber);
~~~

The chain accepts `Integer` and emits `String`. The state types of the individual Gatherers do not need to be exposed in the `chain` variable.

### 3.2. Mismatched composition fails to compile

~~~java
Gatherer<Integer, ?, Integer> numbers = ...;
Gatherer<String, ?, String> trimTexts = ...;

// DOES NOT compile: the next step requires String,
// while the previous step only emits Integer.
// numbers.andThen(trimTexts);
~~~

To connect properly, an `Integer → String` step is needed, or the previous Gatherer's output type must change. Do not cast arbitrarily to mask a mismatched design.

### 3.3. Passing null is an error

~~~java
// Throws NullPointerException:
// chain.andThen(null);
~~~

A `null` Gatherer is not a valid "empty step". If an optional stage is absent, build the chain conditionally in application code, or use a well-defined pass-through Gatherer.

---

## 4. Fundamental law: two gather calls equal andThen

The Javadoc of `Gatherer.andThen` guarantees that the result is semantically equivalent to chaining two consecutive gather operations.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> scan =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, String> asText =
        Gatherer.<Integer, String>of(
                (ignored, sum, downstream) ->
                        downstream.push("sum=" + sum)
        );

List<String> composed = Stream.of(1, 2, 3, 4)
        .gather(scan.andThen(asText))
        .toList();

List<String> separate = Stream.of(1, 2, 3, 4)
        .gather(scan)
        .gather(asText)
        .toList();

System.out.println(composed);
// [sum=1, sum=3, sum=6, sum=10]

System.out.println(composed.equals(separate)); // true
~~~

~~~text
Approach 1: gather(scan.andThen(asText))
              Integer --> Integer --> String

Approach 2: gather(scan).gather(asText)
              Integer --> Integer --> String
~~~

**Semantic equivalence** does not mean the framework must allocate the same number of objects, use the same thread scheduling, or invoke user functions in a schedule observable via side effects. The comparison target is **contracted output**, not debug-print order from parallel lambdas.

### 4.1. andThen creates a Gatherer, it does not execute immediately

~~~java
Gatherer<Integer, ?, String> reusable =
        scan.andThen(asText); // No source yet, no elements emitted yet.

List<String> result = Stream.of(5, 6)
        .gather(reusable)
        .toList();             // Terminal operation consumes source.
~~~

In a lazy pipeline, declaring a `Gatherer` or calling `andThen` **does not evaluate** Stream elements on its own. `toList()`, `collect()`, `count()`, `findFirst()`, or another terminal operation triggers execution.

### 4.2. Do not reuse a Stream that has already been consumed

~~~java
// Wrong pattern:
// Stream<Integer> source = Stream.of(1, 2, 3);
// source.gather(scan).toList();
// source.gather(scan.andThen(asText)).toList();
~~~

Create **two new Streams from the same re-traversable source** or use a `Supplier<Stream<T>>` to compare. You can reuse a **Gatherer definition that holds no invalid external state**; standard Gatherer state is created per run, not stored inside the `Gatherer` variable.

---

## 5. Foundational example: windowFixed then sum each window

`Gatherers.windowFixed(n)` takes `Stream<T>` and emits `Stream<List<T>>`. We chain it with a Gatherer that takes `List<Integer>`, computes its sum, and emits `Integer`.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, List<Integer>> windows =
        Gatherers.windowFixed(3);

Gatherer<List<Integer>, ?, Integer> sumWindow =
        Gatherer.<List<Integer>, Integer>of(
                (ignored, window, downstream) ->
                        downstream.push(
                                window.stream()
                                      .mapToInt(Integer::intValue)
                                      .sum()
                        )
        );

Gatherer<Integer, ?, Integer> windowSums =
        windows.andThen(sumWindow);

List<Integer> result = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(windowSums)
        .toList();

System.out.println(result); // [6, 15, 7]
~~~

Trace:

~~~text
Input Integer:        1 2 3 4 5 6 7
                         |
                  windowFixed(3)
                         |
Output List<Integer>: [1,2,3] [4,5,6] [7]
                         |
                     sumWindow
                         |
Output Integer:         6      15     7
~~~

The final window may have **fewer than n elements**. `windowFixed(3)` does not discard `[7]`. `sumWindow` must compute properly even for lists smaller than the nominal size.

### 5.1. Compared with consecutive gather calls

~~~java
List<Integer> sameResult = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(windows)
        .gather(sumWindow)
        .toList();

System.out.println(result.equals(sameResult)); // true
~~~

Both express the same logic; `andThen` is advantageous when you want to name and reuse the **"batch by 3 then sum"** transformation.

### 5.2. When is andThen unnecessary?

~~~java
List<Integer> alsoValid = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(Gatherers.windowFixed(3))
        .map(window -> window.stream()
                             .mapToInt(Integer::intValue)
                             .sum())
        .toList();
~~~

A plain `map` is enough when the subsequent stage only performs a **one-to-one** transformation and does not need to be packaged as a standalone Gatherer. `andThen` does not replace `map` everywhere; it is a tool for **composing Gatherers** that may handle diverse state and output counts.

---

## 6. Advanced example: window sums followed by running total

There are three stages:

1. `windowFixed(2)`: `Integer → List<Integer>`.
2. `sumWindow`: `List<Integer> → Integer`.
3. `scan`: `Integer → Integer`, emitting the running total after each window.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, List<Integer>> window2 =
        Gatherers.windowFixed(2);

Gatherer<List<Integer>, ?, Integer> sumEach =
        Gatherer.<List<Integer>, Integer>of(
                (ignored, xs, downstream) ->
                        downstream.push(
                                xs.stream()
                                  .mapToInt(Integer::intValue)
                                  .sum()
                        )
        );

Gatherer<Integer, ?, Integer> running =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, Integer> pipeline =
        window2.andThen(sumEach).andThen(running);

List<Integer> totals = Stream.of(1, 2, 3, 4, 5)
        .gather(pipeline)
        .toList();

System.out.println(totals); // [3, 10, 15]
~~~

Because:

~~~text
Input:             [1, 2, 3, 4, 5]
windowFixed(2):    [[1,2], [3,4], [5]]
sumEach:           [3, 7, 5]
scan(sum):         [3, 10, 15]
~~~

With `scan`, the value returned by `initial` is the **starting state**, not emitted as a leading element. Thus the output has three numbers matching the three windows, not four numbers starting at `0`.

### 6.1. Equivalent to three separate gather calls

~~~java
List<Integer> separateStages = Stream.of(1, 2, 3, 4, 5)
        .gather(window2)
        .gather(sumEach)
        .gather(running)
        .toList();

System.out.println(totals.equals(separateStages)); // true
~~~

### 6.2. Turning into a reusable utility

~~~java
static Gatherer<Integer, ?, Integer>
runningWindowSums(int windowSize) {
    Gatherer<Integer, ?, List<Integer>> windows =
            Gatherers.windowFixed(windowSize);

    Gatherer<List<Integer>, ?, Integer> sumWindow =
            Gatherer.<List<Integer>, Integer>of(
                    (ignored, xs, downstream) ->
                            downstream.push(
                                    xs.stream()
                                      .mapToInt(Integer::intValue)
                                      .sum()
                            )
            );

    Gatherer<Integer, ?, Integer> running =
            Gatherers.scan(() -> 0, Integer::sum);

    return windows.andThen(sumWindow).andThen(running);
}
~~~

Place the method in a Java class. We can use:

~~~java
List<Integer> a = Stream.of(1, 2, 3, 4, 5)
        .gather(runningWindowSums(2))
        .toList();

List<Integer> b = Stream.of(10, 20, 30)
        .gather(runningWindowSums(2))
        .toList();

System.out.println(a); // [3, 10, 15]
System.out.println(b); // [30, 60]
~~~

The function creates a **fresh Gatherer per window configuration**. It does not hold an external `int` sum shared across evaluation streams.

**Precision note:** The example uses `int` for simplicity. For data where sums can overflow `int`, choose `long`/`BigInteger` as appropriate rather than expecting `andThen` to fix overflow.

---

## 7. Composition order matters: andThen is not commutative

In general:

~~~text
A.andThen(B) != B.andThen(A)
~~~

Many Gatherer pairs cannot even be swapped due to **type mismatch**. Even for Gatherers with matching types, the two orders can produce different results.

### 7.1. Example: scan then fold

`scan` emits **each running total**; `fold` reduces all those totals into a single final result.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> running =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, Integer> foldSum =
        Gatherers.fold(() -> 0, Integer::sum);

List<Integer> scanThenFold = Stream.of(1, 2, 3, 4)
        .gather(running.andThen(foldSum))
        .toList();

System.out.println(scanThenFold); // [20]
~~~

Explanation:

~~~text
Input:     [1, 2, 3, 4]
scan:      [1, 3, 6, 10]
fold:      [1 + 3 + 6 + 10]
Output:    [20]
~~~

### 7.2. Example: fold then scan

~~~java
List<Integer> foldThenScan = Stream.of(1, 2, 3, 4)
        .gather(foldSum.andThen(running))
        .toList();

System.out.println(foldThenScan); // [10]
~~~

Explanation:

~~~text
Input:     [1, 2, 3, 4]
fold:      [10]     (one element emitted at end of source)
scan:      [10]     (processes only one element)
Output:    [10]
~~~

The two pipelines have **the same start/end types** yet **different outputs**. This is the simplest counterexample to the false assumption that `andThen` is commutative.

### 7.3. Associativity at the result level

For three Gatherers `A: T→U`, `B: U→V`, `C: V→W`, the two expressions below share the same transformation flow per contract:

~~~java
Gatherer<T, ?, W> leftGrouped =
        A.andThen(B).andThen(C);

Gatherer<T, ?, W> rightGrouped =
        A.andThen(B.andThen(C));
~~~

This is **type-illustrative code**, not standalone compilable Java since variables `A`/`B`/`C` and type parameters `T`/`U`/`V`/`W` must be declared. The point is that both parenthesizations pass data in the order `A → B → C`.

Do **not** infer that both forms have the same allocation cost, same threads, or same lambda invocation counts observed via side effects. Equivalence is evaluated on **contracted output behavior**.

---

## 8. windowSliding and post-processing over a sequence of windows

`Gatherers.windowSliding(n)` creates sliding windows. With n = 3 and input 1..5:

~~~text
[1,2,3]
  [2,3,4]
    [3,4,5]
~~~

We can compose a Gatherer that averages each window:

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, List<Integer>> sliding =
        Gatherers.windowSliding(3);

Gatherer<List<Integer>, ?, Double> averageWindow =
        Gatherer.<List<Integer>, Double>of(
                (ignored, window, downstream) ->
                        downstream.push(
                                window.stream()
                                      .mapToInt(Integer::intValue)
                                      .average()
                                      .orElseThrow()
                        )
        );

List<Double> averages = Stream.of(1, 2, 3, 4, 5)
        .gather(sliding.andThen(averageWindow))
        .toList();

System.out.println(averages); // [2.0, 3.0, 4.0]
~~~

`average().orElseThrow()` is safe **in this example** because emitted sliding windows contain at least one element when `windowSize >= 1`. If you write a Gatherer that can emit empty lists, pick an explicit empty-handling policy.

### 8.1. Source shorter than window size

If the input has fewer elements than `windowSliding(3)`, the Gatherer emits **one window containing all available elements**.

~~~java
List<List<Integer>> windows = Stream.of(1, 2)
        .gather(Gatherers.windowSliding(3))
        .toList();

System.out.println(windows); // [[1, 2]]
~~~

With an empty source, there are no windows. With `windowFixed`, the final window can also be shorter than n. Never write downstream assuming every list has exactly n elements without checking the specific window contract.

### 8.2. Cost

Sliding windows have many **overlapping** elements; the total number of element appearances across windows can far exceed the input size. Chaining another Gatherer that computes statistics per window may repeat calculations.

If deep optimization is required, consider a dedicated stateful sliding-statistics algorithm. `andThen` helps express **pipeline structure**; it does not automatically turn an O(n·windowSize) algorithm into O(n).

---

## 9. Finisher: elements emitted at the end still flow through the next Gatherer

Some Gatherers emit output only inside `finisher` after upstream finishes. `Gatherers.fold` is an important example.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> foldSum =
        Gatherers.fold(() -> 0, Integer::sum);

Gatherer<Integer, ?, String> format =
        Gatherer.<Integer, String>of(
                (ignored, n, downstream) ->
                        downstream.push("TOTAL=" + n)
        );

List<String> result = Stream.of(3, 5, 7)
        .gather(foldSum.andThen(format))
        .toList();

System.out.println(result); // [TOTAL=15]
~~~

~~~text
Stream.of(3,5,7)
   |
   v
foldSum:
  integrator receives 3,5,7;
  does not emit intermediate sums;
  finisher emits 15
   |
   v
format:
  integrator receives 15
  and emits "TOTAL=15"
   |
   v
["TOTAL=15"]
~~~

Because `fold`'s output is emitted **at the end of the source**, the downstream Gatherer still receives and processes it. Composition does not mean "skipping the previous step's finisher".

### 9.1. Empty source case

Per the `Gatherers.fold` contract, when there is no input and processing finishes normally, it emits **the initial value**.

~~~java
List<Integer> foldedEmpty = Stream.<Integer>empty()
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(foldedEmpty); // [0]
~~~

Conversely, `windowFixed(3)` on an empty Stream emits no windows:

~~~java
List<List<Integer>> emptyWindows = Stream.<Integer>empty()
        .gather(Gatherers.windowFixed(3))
        .toList();

System.out.println(emptyWindows); // []
~~~

When composing the two steps:

~~~java
Gatherer<Integer, ?, List<Integer>> windows =
        Gatherers.windowFixed(3);

Gatherer<List<Integer>, ?, Integer> countWindows =
        Gatherers.fold(() -> 0,
                (count, window) -> count + 1);

List<Integer> counts = Stream.<Integer>empty()
        .gather(windows.andThen(countWindows))
        .toList();

System.out.println(counts); // [0]
~~~

**Common pitfall:** "Gatherer A emitted no output" does not mean "the whole chain has no output", because Gatherer B can emit a value in its `finisher` even when receiving no input.

### 9.2. Finisher vs. terminal Collector.finisher

- `Gatherer.finisher` can **emit additional elements downstream**, remaining part of the Stream transformation.
- `Collector.finisher` converts collection state `A` into the **terminal result** `R` of `collect`.
- `Gatherer.andThen` composes **potentially stateful intermediate operations**; `Collectors.collectingAndThen` finalizes a **collector result**. The two APIs are not interchangeable.

---

## 10. Writing a stateless custom Gatherer and composing it

We want to normalize strings, discard blank strings, and then group the remaining strings into pairs.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<String, ?, String> nonBlankTrimmed =
        Gatherer.<String, String>of(
                (ignored, text, downstream) -> {
                    if (downstream.isRejecting()) {
                        return false;
                    }

                    String trimmed = text.trim();
                    if (trimmed.isEmpty()) {
                        return true; // Emit no element.
                    }

                    return downstream.push(trimmed);
                }
        );

Gatherer<String, ?, List<String>> pairs =
        nonBlankTrimmed.andThen(
                Gatherers.windowFixed(2)
        );

List<List<String>> result = Stream
        .of(" An ", " ", "Binh", "", " Chi ")
        .gather(pairs)
        .toList();

System.out.println(result); // [[An, Binh], [Chi]]
~~~

Contract:

- One input `String` can produce **0 or 1** output from `nonBlankTrimmed`.
- `windowFixed(2)` sees only **the Strings actually emitted**; blank strings disappeared before grouping.
- If you use `windowFixed(2).andThen(...)` with a list-processing step, you are grouping **the raw data first**; that is a different workflow.

### 10.1. When to use regular filter + map?

The same problem can be written:

~~~java
List<List<String>> alsoValid = Stream
        .of(" An ", " ", "Binh", "", " Chi ")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .gather(Gatherers.windowFixed(2))
        .toList();
~~~

`map` and `filter` are usually clearer if you do not need to package the transformation into a reusable Gatherer. Only write custom Gatherers when you have specific requirements around emission count, state, short-circuiting, finisher, or composition components.

---

## 11. Custom stateful-style Gatherer: stop after a milestone while keeping it

Requirement: given an integer Stream with encounter order, take elements from the start **until the first number >= threshold**, inclusive of the number reaching the threshold.

A Gatherer like this can stop the source early:

~~~java
import java.util.stream.Gatherer;

static Gatherer<Integer, ?, Integer>
takeUntilInclusive(int threshold) {
    return Gatherer.<Integer, Integer>ofSequential(
            (ignored, value, downstream) -> {
                // Emit element if downstream still accepts.
                boolean wantsMore = downstream.push(value);

                // Stop after the first element >= threshold.
                return wantsMore && value < threshold;
            }
    );
}
~~~

Even without storing separate state, `ofSequential` is chosen to emphasize **prefix semantics in input order**. Do not advertise a combiner that splits data without being able to determine the global first milestone.

### 11.1. Composing with scan

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> stopAtThree =
        takeUntilInclusive(3);

Gatherer<Integer, ?, Integer> running =
        Gatherers.scan(() -> 0, Integer::sum);

List<Integer> result = Stream.of(1, 2, 3, 4, 5)
        .gather(stopAtThree.andThen(running))
        .toList();

System.out.println(result); // [1, 3, 6]
~~~

After emitting `3`, the first Gatherer returns `false` so it receives no more inputs. `running` only sees `[1,2,3]`.

### 11.2. Swapping order can change the stopping point

~~~java
List<Integer> other = Stream.of(1, 2, 3, 4, 5)
        .gather(running.andThen(stopAtThree))
        .toList();

System.out.println(other); // [1, 3]
~~~

Because `running` emits `[1,3,6,10,15]`, the Gatherer stops at **running total 3** (the second element), yielding `[1,3]`. This is another example showing `andThen` **is order-sensitive**.

### 11.3. Do not swallow the signal from downstream.push

~~~java
// Unsafe if downstream stops early:
// (ignored, value, downstream) -> {
//     downstream.push(value);
//     return true; // Tries to tell upstream to continue.
// }
~~~

`downstream.push(value)` returns a `boolean` indicating whether downstream still wants more. If it returns `false`, stop emitting downstream. `downstream.isRejecting()` can assist with an early check, though it is *best-effort*; never use it to replace handling the return value of `push`.

The `takeUntilInclusive` example returns `wantsMore && ...`, respecting both the Gatherer's own stopping condition and a stop request from a subsequent terminal operation.

---

## 12. Custom finisher: emitting result after the source ends

Example of a Gatherer that tracks the count of received elements and emits `"count=N"` only when upstream ends.

~~~java
import java.util.stream.Gatherer;

static Gatherer<Integer, ?, String> countAsText() {
    class CountState {
        long count;
    }

    return Gatherer.<Integer, CountState, String>ofSequential(
            CountState::new,
            (state, item, downstream) -> {
                state.count++;
                return true;
            },
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push("count=" + state.count);
                }
            }
    );
}
~~~

In this code:

- `initializer` creates a `CountState` for each appropriate evaluation.
- `integrator` increments count without **emitting any output**.
- `finisher` emits one String upon completion.
- Never save state or the `downstream` object into a static field for later use.

### 12.1. Composing custom finisher with another Gatherer

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

Gatherer<String, ?, Integer> textLength =
        Gatherer.<String, Integer>of(
                (ignored, text, downstream) ->
                        downstream.push(text.length())
        );

List<Integer> result = Stream.of(3, 7, 11)
        .gather(countAsText().andThen(textLength))
        .toList();

System.out.println(result); // [7]
~~~

`"count=3"` has length `7`. The output of the previous step's finisher is forwarded through the next step's integrator, even though the previous step emitted nothing while reading each element.

### 12.2. Short-circuiting and finisher

Do not assume every Gatherer's finisher will always emit every value successfully:

- Terminal `limit`/`findFirst` may cause downstream **to stop accepting more**.
- If an integrator stops early, processing remaining input may be skipped.
- If downstream is already rejecting, finisher should not try to push extra elements at all costs.
- Never place mandatory side effects such as committing transactions, sending emails, or closing file handles solely inside a finisher assuming every error/cancellation path will invoke it once.

For resources, use `try-with-resources` and dedicated application cleanup mechanisms.

---

## 13. How does composition affect the state of two Gatherers?

Suppose:

~~~text
A: windowFixed(3)     state A collects numbers into windows
B: scan(sum)          state B holds running sum
C: fold(...)          state C holds one final aggregated value
~~~

When composing `A.andThen(B).andThen(C)`, each stage retains its **own state semantics**. B's state is not A's state; B's running sum is computed from **the outputs emitted by A**, not directly from every input T.

Diagram:

~~~text
Stream<T>
  |
  v
A.initializer / A.integrator / A.finisher
  |          |
  |          +-- may emit in finisher
  v
R
  |
  v
B.initializer / B.integrator / B.finisher
  |
  v
RR
  |
  v
C.initializer / C.integrator / C.finisher
  |
  v
Final Output
~~~

`andThen` returns a Gatherer **encapsulating the composition**. Internal state types are hidden with the wildcard `?`, because callers do not need to know what the two Gatherers store internally.

### 13.1. Do not leak mutable state outside the pipeline

~~~java
// Do not:
// List<Integer> shared = new ArrayList<>();
// Gatherer<Integer, ?, Integer> g = Gatherer.of(
//     (unused, n, downstream) -> {
//         shared.add(n);       // Same list shared across evaluations.
//         return downstream.push(n);
//     }
// );
~~~

State used to track progress must belong to **the evaluation pass** (via initializer or appropriate state mechanism), not a mutable variable shared across multiple pipelines.

**API constraint:** A custom Gatherer must not retain references to the passed-in state or `Gatherer.Downstream` beyond the lifetime of the function invocation receiving them, and must not hand them off to another thread for arbitrary use.

---

## 14. Parallel streams: andThen does not automatically parallelize Gatherers

A Gatherer can only be evaluated in parallel if its model and **combiner** allow it. `Gatherer.ofSequential(...)` describes only a **sequential** Gatherer; it may appear in a `parallel()` pipeline, yet that does not mean it is split and merged safely in parallel.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

Gatherer<Integer, ?, Integer> scan =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, Integer> fold =
        Gatherers.fold(() -> 0, Integer::sum);

List<Integer> result = IntStream.rangeClosed(1, 4)
        .boxed()
        .parallel()
        .gather(scan.andThen(fold))
        .toList();

System.out.println(result); // [20]
~~~

The result must still adhere to the composed transformation contract, yet **do not infer** that both stages actually run across multiple threads. Order-dependent computations like prefix scan/fold can limit parallelizability.

### 14.1. Conditions for a valid combiner

If writing a custom Gatherer with a combiner, you must ensure:

1. **Each partition initializes its own state**, without mutating an unsafe shared object.
2. **Combiner merges two states according to the exact transformation semantics**, being associative when multi-level splitting/merging is needed.
3. Results do not depend on a specific partitioning schedule if the API permits evaluating in different ways.
4. **Encounter-order semantics** are still preserved at steps requiring order guarantees.
5. Early stopping and canceling surplus work never lead to wrong outputs.

You cannot take a numeric-addition combiner from one Gatherer and apply it to a windowing Gatherer without proving that **window boundaries between two partitions** are handled correctly.

### 14.2. What if one stage can only run sequentially?

A chain consisting of one sequential Gatherer and one parallel-capable Gatherer must still preserve **the semantics of the entire chain**. The sequential step can create a bottleneck; having one stage with a combiner does not automatically parallelize the other stages.

`andThen` is a **semantic composition**, not a promise that the entire pipeline is implemented as an optimal parallel algorithm.

### 14.3. What does mapConcurrent mean?

`Gatherers.mapConcurrent(maxConcurrency, mapper)` can execute the mapper with a configured **maximum concurrency** using virtual threads while preserving output order from the source. It differs from turning on `parallelStream()` for the whole pipeline.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<String, ?, String> enrich =
        Gatherers.mapConcurrent(
                3,
                (String code) -> "enriched:" + code
        );

Gatherer<String, ?, List<String>> batch =
        Gatherers.windowFixed(2);

List<List<String>> output = Stream.of("A", "B", "C")
        .gather(enrich.andThen(batch))
        .toList();

System.out.println(output);
// [[enriched:A, enriched:B], [enriched:C]]
~~~

The example mapper just concatenates strings for easy verification; in practice `mapConcurrent` suits independent waiting work such as I/O calls, and concurrency must be bounded according to resources. Do not invoke the mapper on shared mutable data without thread control.

---

## 15. andThen is not collect, collectingAndThen, or Function.andThen

Four constructs with "Then" or composition models are easy to confuse:

| API | Where does it live? | Output |
|---|---|---|
| `Function.andThen` | Composes two one-to-one transformation functions | A new function |
| `Consumer.andThen` | Composes two `void` actions | A new consumer |
| `Collector`/`Collectors.collectingAndThen` | Finalizes collected result at terminal stage | Final `R` result of `collect` |
| `Gatherer.andThen` | Composes **two potentially stateful intermediate operations** | A new Gatherer |

### 15.1. Function.andThen has no multi-output or finisher mechanism

~~~java
import java.util.function.Function;

Function<Integer, Integer> plusOne = n -> n + 1;
Function<Integer, String> toText = n -> "n=" + n;

Function<Integer, String> f = plusOne.andThen(toText);

System.out.println(f.apply(4)); // n=5
~~~

Traditional functions do not have `integrator`, `downstream.push`, `finisher`, or combiner like Gatherer. Use `Function.andThen` when only a pure 1→1 transformation chain is needed.

### 15.2. collectingAndThen runs after collection completes

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> list = Stream.of(1, 2, 3)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));
~~~

This is a **terminal operation**. `List::copyOf` is applied to **the entire collected result**; it does not receive individual elements like an intermediate Gatherer.

### 15.3. Gatherer.andThen keeps the pipeline going

~~~java
long howMany = Stream.of(1, 2, 3, 4)
        .gather(
                Gatherers.<Integer>windowFixed(2)
                        .andThen(
                                Gatherer.<List<Integer>, Integer>of(
                                        (ignored, window, downstream) ->
                                                downstream.push(window.size())
                                )
                        )
        )
        .filter(size -> size >= 2)
        .count();

System.out.println(howMany); // 2
~~~

After `gather`, the Stream can continue through `filter`, `map`, `sorted`, `collect`, or another terminal operation. `andThen` does not terminate the Stream.

---

## 16. Combining Gatherers and regular Stream operations

Not every stage needs to be a Gatherer.

~~~java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> result = Stream.of(-1, 1, 2, 3, 4, 5)
        .filter(n -> n > 0)
        .gather(Gatherers.windowFixed(2))
        .map(window -> window.stream()
                             .mapToInt(Integer::intValue)
                             .sum())
        .filter(sum -> sum > 3)
        .toList();

System.out.println(result); // [7, 5]
~~~

After `filter(n > 0)`, the input is `[1,2,3,4,5]`. The windows are: `[1,2]`, `[3,4]`, `[5]`. Sums: `3,7,5`. After `sum > 3`: `[7,5]`.

If a later step is reused across multiple pipelines, you can move it into its own Gatherer and use `andThen`. If you only need a simple `map` in one place, a mixed pipeline is usually easier to read.

### 16.1. Only move filter before window when business semantics allow

~~~text
Input: [A, X, B, C]
X: invalid record
windowFixed(2) before filter: [[A,X], [B,C]]
filter before windowFixed(2): [[A,B], [C]]
~~~

These are two different grouping workflows. When using `andThen` to package a chain, document clearly **when filtering happens** relative to **when windowing happens**.

### 16.2. Do not overuse custom Gatherers

A transformation `x -> x * 2` should usually be written `map(x -> x * 2)`. Deduplication by `equals` usually uses `distinct`. Gatherers are useful when you need state or emission rules that built-in operations cannot express cleanly, or when packaging **a multi-stage Gatherer combination**.

---

## 17. Reusing chains and configuration concepts

A practical way to organize code:

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;

static Gatherer<Integer, ?, Integer>
windowAveragesRoundedDown(int size) {

    Gatherer<Integer, ?, List<Integer>> windows =
            Gatherers.windowFixed(size);

    Gatherer<List<Integer>, ?, Integer> averageFloor =
            Gatherer.<List<Integer>, Integer>of(
                    (ignored, xs, downstream) -> {
                        long sum = xs.stream()
                                .mapToLong(Integer::longValue)
                                .sum();

                        int average = Math.toIntExact(
                                Math.floorDiv(sum, xs.size())
                        );

                        return downstream.push(average);
                    }
            );

    return windows.andThen(averageFloor);
}
~~~

Creating a chain from a configuration parameter `size` gives the problem a name and makes it independently testable. `Gatherers.windowFixed` rejects `size < 1`; never silently coerce it to size=1 unless the business logic requires it.

**Arithmetic limits:** The example uses `long` for sum and `Math.toIntExact` to detect results overflowing `int`. For huge totals that can exceed `long`, upgrade to `BigInteger` if business logic requires exact sums.

### 17.1. Do not use application-level mutable counters

~~~java
// Do not:
// AtomicInteger running = new AtomicInteger();
// Gatherer<Integer, ?, Integer> g = Gatherer.of(
//       (unused, n, downstream) ->
//               downstream.push(running.addAndGet(n))
// );
~~~

Use `Gatherers.scan(() -> 0, Integer::sum)` so each evaluation has compliant per-run state. Reusing a **safe Gatherer definition** differs from sharing a **mutable container carrying data from previous runs**.

---

## 18. Differences between windowFixed and windowSliding when composing

| Condition | `windowFixed(3)` | `windowSliding(3)` |
|---|---|---|
| Input `[1,2,3,4,5]` | `[[1,2,3],[4,5]]` | `[[1,2,3],[2,3,4],[3,4,5]]` |
| Elements per window | Last may have fewer than 3 | Usually 3 when source is long enough; source shorter than 3 emits one short window |
| Overlap | No | Yes |
| Common usage | Batching for sending/aggregating | Moving averages, adjacent comparisons |
| Composed with `scan` | Scan runs per **batch** | Scan runs per **sliding window** |

### 18.1. Counterexample: thinking both window types produce the same output count

~~~java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> fixed = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowFixed(3))
        .toList();

List<List<Integer>> sliding = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowSliding(3))
        .toList();

System.out.println(fixed);   // [[1, 2, 3], [4, 5]]
System.out.println(sliding); // [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
~~~

A subsequent Gatherer will see **2 List elements** in the fixed case and **3 List elements** in the sliding case. Choose the right window semantics before chaining with `fold` or `scan`.

---

## 19. Handling null, empty sources, and problematic data

### 19.1. Empty sources

| Chain | Result when no input and processing finishes normally |
|---|---|
| `windowFixed(3)` | Emits no windows |
| `windowSliding(3)` | Emits no windows |
| `scan(() -> 0, sum)` | Emits no running totals |
| `fold(() -> 0, sum)` | Emits initial value `0` |
| `windowFixed(3).andThen(fold(count))` | Can emit `0` because downstream fold receives zero windows |

This is why test suites must not apply a blanket rule "an empty Stream always returns an empty List" to **every Gatherer**. A Gatherer with a `finisher` can emit a value **even with zero inputs**.

### 19.2. Null

`Stream.of((String) null)` can produce a null element. However, `String::trim` on null throws `NullPointerException`.

~~~java
import java.util.Objects;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<String>> safe = Stream.of(" An ", null, " Binh ")
        .filter(Objects::nonNull)
        .map(String::trim)
        .gather(Gatherers.windowFixed(2))
        .toList();

System.out.println(safe); // [[An, Binh]]
~~~

Filter out nulls **before** entering a Gatherer if the Gatherer has not defined null handling. This also alters window sizes and boundaries compared to keeping a null slot, so align on the policy.

### 19.3. Exceptions in mapper and finisher

When a mapper/gatherer function throws an exception, the pipeline can terminate with an exception; side effects already executed in earlier parts have no automatic rollback mechanism.

With `mapConcurrent`, when a mapper fails, the exception may be propagated as a `RuntimeException` and remaining tasks may be canceled best-effort. Do not assume every started task completes or external operations are automatically undone.

---

## 20. Performance: composition may optimize, with no guarantees

Example:

~~~java
Stream<Integer> source = ...;

List<Integer> result = source
        .gather(g1.andThen(g2))
        .toList();
~~~

You cannot assert from syntax alone that this form always:

- Traverses the source fewer times than `gather(g1).gather(g2)`.
- Allocates fewer objects on every JDK.
- Runs better in parallel.
- Uses zero temporary memory.
- Cancels all work immediately when downstream stops.

`andThen` provides a **composition contract**, while the runtime may choose an implementation preserving semantics depending on JDK version, Gatherer characteristics, and pipeline shape.

### 20.1. Major cost sources

| Cost | When significant? |
|---|---|
| Holding state | `scan`, `fold`, custom Gatherers |
| Allocating windows | `windowFixed`/`windowSliding`, especially large windows |
| Recomputing on sliding windows | When each window is processed separately with a reduction |
| Parallel state merging | Gatherer with combiner; contract must be checked |
| Preserving encounter order | When stateful transformations are order-dependent |
| I/O concurrency | `mapConcurrent` uses many virtual threads while external resources remain bounded |
| Final result | `toList` can retain all output in memory |

### 20.2. Benchmarking properly

If performance is a requirement, use JMH or a measurement setup with warm-up and clear controls:

- Same data source and same result contract.
- Varying data sizes and window sizes.
- Comparing traditional pipelines, chained `gather`, and `andThen`.
- Measuring throughput, allocation, GC, latency, and peak memory.
- Separating real I/O cost from CPU transformations to locate bottlenecks.
- Never comparing two **semantically different** pipelines like `windowFixed` and `windowSliding` and concluding one is purely faster/slower.

---

## 21. Complete Java 24 program: testing andThen

This is a standalone example that can be placed in `GathererAndThenDemo.java` and compiled with JDK 24 or later.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererAndThenDemo {

    static Gatherer<Integer, ?, Integer> pairSums() {
        Gatherer<Integer, ?, List<Integer>> pairs =
                Gatherers.windowFixed(2);

        Gatherer<List<Integer>, ?, Integer> sumPair =
                Gatherer.<List<Integer>, Integer>of(
                        (ignored, pair, downstream) ->
                                downstream.push(
                                        pair.stream()
                                            .mapToInt(Integer::intValue)
                                            .sum()
                                )
                );

        return pairs.andThen(sumPair);
    }

    static Gatherer<Integer, ?, Integer> runningPairSums() {
        Gatherer<Integer, ?, Integer> pairSums = pairSums();
        Gatherer<Integer, ?, Integer> running =
                Gatherers.scan(() -> 0, Integer::sum);

        return pairSums.andThen(running);
    }

    static void checkEquals(
            String name, Object expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual
            );
        }
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(1, 2, 3, 4, 5);

        List<Integer> composed = input.stream()
                .gather(runningPairSums())
                .toList();

        List<Integer> separate = input.stream()
                .gather(Gatherers.windowFixed(2))
                .map(pair -> pair.stream()
                                 .mapToInt(Integer::intValue)
                                 .sum())
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();

        checkEquals("composed", List.of(3, 10, 15), composed);
        checkEquals("equivalence", separate, composed);

        // Empty source: windowFixed creates no windows.
        List<Integer> empty = Stream.<Integer>empty()
                .gather(runningPairSums())
                .toList();
        checkEquals("empty", List.of(), empty);

        // Incomplete final window.
        List<Integer> one = Stream.of(7)
                .gather(runningPairSums())
                .toList();
        checkEquals("one", List.of(7), one);

        // Both gather styles have identical semantics.
        Gatherer<Integer, ?, Integer> pairs = pairSums();
        Gatherer<Integer, ?, Integer> running =
                Gatherers.scan(() -> 0, Integer::sum);

        List<Integer> joined = input.stream()
                .gather(pairs.andThen(running))
                .toList();

        List<Integer> chained = input.stream()
                .gather(pairs)
                .gather(running)
                .toList();

        checkEquals("andThen vs gather-gather", chained, joined);

        // Reusing multiple times, always creating a new Stream.
        List<Integer> again = input.stream()
                .gather(runningPairSums())
                .toList();
        checkEquals("reusable definition", composed, again);

        System.out.println("AND_THEN_OK");
        System.out.println(composed);
    }
}
~~~

Expected output:

~~~text
AND_THEN_OK
[3, 10, 15]
~~~

### 21.1. Running with JDK 24+

~~~text
javac GathererAndThenDemo.java
java GathererAndThenDemo
~~~

If `javac` reports it cannot find `Gatherer` or `Stream.gather`, check the actual JDK version in use:

~~~text
java -version
javac -version
~~~

JDK 22/23 included **preview** versions of Stream Gatherers; this lesson targets the **final API on JDK 24+**, and copying the examples verbatim to older JDKs without checking compatibility is not recommended.

---

## 22. Testing chains with an oracle and invariants

Cases that should be included:

| Case | Expectation |
|---|---|
| Empty source | Depends on chain: no windows, though `fold` may emit initial |
| Single element | `windowFixed` emits a short window; downstream handles it |
| Size divisible by n | No extra empty window created |
| Size not divisible by n | Final window holds remaining elements |
| Running `gather(A).gather(B)` | Result matches `gather(A.andThen(B))` per contract |
| Swapping `A/B` when types match | Do not assume equivalence; may differ |
| Type A output mismatches B input | Compile error; no fake casting |
| Downstream terminal `limit` | Respects stopping intake; do not rely on lambda call counts |
| Stateful Gatherer | No state leak between two evaluations |
| Gatherer with finisher | Output emitted at end still passes through next step |
| Parallel | Correct result per contract; do not require multi-thread execution |
| Null/exceptions | Input handling and cleanup follow policy |
| Invalid window size | `windowFixed`/`windowSliding` reject size < 1 |
| Results requiring exact arithmetic | Check overflow and rounding |
| I/O | File source is closed, not relying solely on finisher |

### 22.1. Building an oracle from a List and a loop

Example verifying `windowFixed(2)` then summing each pair, then running sum:

~~~java
import java.util.ArrayList;
import java.util.List;

static List<Integer> oracleRunningPairs(List<Integer> input) {
    List<Integer> result = new ArrayList<>();
    int total = 0;

    for (int i = 0; i < input.size(); i += 2) {
        int pairSum = input.get(i);

        if (i + 1 < input.size()) {
            pairSum += input.get(i + 1);
        }

        total += pairSum;
        result.add(total);
    }

    return result;
}
~~~

This method goes inside a Java class and suits sample data that does not overflow `int`. The oracle **does not call the Gatherer itself** under test, so it can catch structural bugs in the chain.

### 22.2. Testing multiple input sizes

~~~java
for (int size = 0; size <= 20; size++) {
    List<Integer> input = new java.util.ArrayList<>();

    for (int n = 1; n <= size; n++) {
        input.add(n);
    }

    List<Integer> expected = oracleRunningPairs(input);

    List<Integer> actual = input.stream()
            .gather(runningPairSums())
            .toList();

    if (!expected.equals(actual)) {
        throw new AssertionError(
                "size=" + size
                + ", expected=" + expected
                + ", actual=" + actual
        );
    }
}
~~~

Testing all sizes 0..20 covers both full and incomplete final windows; however, it does not prove all data values and splitting strategies. Add negative numbers, large numbers, null cases, and parallel checks as required.

### 22.3. Do not test by counting side-effect invocations

~~~java
// Do not use println counts inside an integrator as an oracle,
// because short-circuit/parallel/lazy optimizations can affect
// invocation schedules and observed ordering.
//
// Compare DATA RESULTS and contract invariants instead.
~~~

---

## 23. Common mistakes when composing Gatherers

| Mistake | Consequence | Fix |
|---|---|---|
| Confusing `andThen` with concatenating two streams | Wrong processing model | Understand A's output becomes B's input |
| Reversing `A.andThen(B)` order | May fail types or produce wrong results | Draw the `T → R → RR` diagram first |
| Forgetting terminal operation | Pipeline does not consume source | Call `toList`, `collect`, `findFirst`, etc. when needed |
| Reusing an already-consumed Stream | Stream lifecycle error | Create a new Stream |
| Assuming the last window always has n elements | Indexing/missing data error | Handle short lists |
| Thinking fold emits each value | Wrong output count | `fold` emits one result at completion; `scan` emits every step |
| Thinking an empty Stream always yields empty output | Wrong with `fold(initial)` | Check each stage's finisher |
| Ignoring `downstream.push` returning false | Does not respect stop request | Return false when downstream rejects |
| Saving `Downstream` or state for use outside the call | Violates Gatherer contract | Use only during invocation lifetime |
| Capturing shared mutable state inside lambda | State leak/race across evaluations | Create state via initializer |
| Thinking `andThen` automatically builds a parallel combiner | Wrong results or lost performance | Design a valid combiner or keep sequential |
| Guessing `CONCURRENT` characteristics | Confusing with Collector, violates contract | Distinguish Gatherer from Collector |
| Assuming `windowSliding` equals `windowFixed` | Different window counts and cost | Pick the right window type |
| Replacing `takeUntilInclusive` with `filter` | Loses first-milestone stopping semantics | Use a short-circuiting Gatherer |
| Not checking JDK version | Fails to compile on Java 17/21 | Use JDK 24+ for the final API |
| Benchmarking two semantically different pipelines as equivalent | Optimizing the wrong target | Compare against the same oracle/semantics first |

---

## 24. When to use andThen vs. consecutive gather calls?

Use `andThen` when:

- You have **two or more Gatherers** you want to name as one reusable operation.
- You want to expose a small API like `Gatherer<Input, ?, Output>` instead of asking callers to wire stages manually.
- You want to encapsulate configuration of window, scan, fold, or custom gatherers inside a helper.
- You need to test a composition as **a single business unit**.
- You want to clearly document intermediate type transitions.

Use `gather(A).gather(B)` when:

- Building a one-off pipeline in one place where separate steps are easier to read.
- You want to debug or insert `filter`/`map` operations between A and B.
- There is no need to package the combination as a reusable Gatherer object.

Use `map`/`filter`/`flatMap` when:

- The operation is a simple transformation already supported natively by Stream.
- No custom state, finisher, or short-circuiting mechanism is needed.

Use `collect` when:

- You want to **collect the final result** into a List/Map/Set, statistics, or DTO.
- There is no need to keep passing elements through a Stream after aggregation.

### 24.1. Chain design checklist

1. Name **each step's input and output**, e.g. `Integer → List<Integer> → Long`.
2. Verify generic types of `andThen` compile cleanly.
3. Determine whether each step emits **0, 1, or many** elements per input.
4. Identify whether any step **emits only in finisher**.
5. Determine what output an **empty source** produces.
6. Clarify encounter order, state, and short-circuiting conditions.
7. Control mutable state: never leak private state outside an invocation.
8. If using parallel, ensure a valid combiner or accept a sequential stage.
9. Do not let functions emit numbers overflowing arithmetic bounds without a policy.
10. Compare `gather(A.andThen(B))` and `gather(A).gather(B)` on the same data.
11. Use an independent oracle to catch cases where **both forms share the same business bug**.
12. Benchmark only after verifying results and resource constraints.

---

## 25. Foundational exercises (with answers)

### Exercise 1. What kind of object does andThen accept?

**Prompt:** Does `Gatherer.andThen(...)` take a `Collector`, a `Function`, or a `Gatherer`?

**Answer:** It takes another **`Gatherer`**. The signature has the form `Gatherer<T,?,RR> andThen(Gatherer<? super R,?,? extends RR> that)`. The previous step's output must be usable as the next step's input.

### Exercise 2. Two equivalent invocations

**Prompt:** Write the equivalent form of `stream.gather(a.andThen(b))`.

**Answer:** `stream.gather(a).gather(b)`. Equivalence applies to **output semantics** per contract, not thread counts, log invocations, or optimization details.

### Exercise 3. Intermediate data types

**Prompt:** `Gatherers.windowFixed(3)` accepts `Integer` numbers and emits what? What type should a subsequent Gatherer accept to compute window sums?

**Answer:** It emits `List<Integer>`. The next Gatherer takes `List<Integer>` as input and can emit `Integer` as the list sum.

### Exercise 4. Final window

**Prompt:** What does `Stream.of(1,2,3,4,5).gather(Gatherers.windowFixed(2)).toList()` return?

**Answer:** `[[1,2],[3,4],[5]]`. The final window can be shorter than the requested size.

### Exercise 5. Scan after window sum

**Prompt:** Input `[1,2,3,4,5]`, `windowFixed(2)`, sum each window, then `scan(() -> 0, Integer::sum)`. Result?

**Answer:** Windows `[[1,2],[3,4],[5]]`, window sums `[3,7,5]`, scan emits `[3,10,15]`.

### Exercise 6. fold vs. scan

**Prompt:** `scan` and `fold` both start with initial 0 and add `[1,2,3]`. How do their results differ?

**Answer:** `scan` emits `[1,3,6]` after each input; `fold` emits one final value `[6]` when upstream completes.

### Exercise 7. Empty source

**Prompt:** What does `Stream.<Integer>empty().gather(Gatherers.fold(() -> 0, Integer::sum)).toList()` return?

**Answer:** `[0]`, because `fold` emits initial in its finisher even when there are no input elements. `windowFixed(3)` alone on an empty source returns `[]`.

### Exercise 8. Reversing order

**Prompt:** For `[1,2,3,4]`, are `scan(sum).andThen(fold(sum))` and `fold(sum).andThen(scan(sum))` equal?

**Answer:** No. The first emits `[20]` by summing the prefix sums 1+3+6+10. The second emits `[10]` because fold computes 10 and scan receives just that one number 10.

---

## 26. Intermediate exercises (with answers)

### Exercise 9. Write a Gatherer turning each window into its sum

**Prompt:** Write `Gatherer<List<Integer>, ?, Integer>` using `Gatherer.of` to turn a list of integers into one sum integer.

**Answer:**

~~~java
Gatherer<List<Integer>, ?, Integer> sumWindow =
        Gatherer.<List<Integer>, Integer>of(
                (ignored, xs, downstream) ->
                        downstream.push(
                                xs.stream().mapToInt(Integer::intValue).sum()
                        )
        );
~~~

This is a stateless Gatherer turning one List input into one Integer output. You can then chain `Gatherers.<Integer>windowFixed(2).andThen(sumWindow)`.

### Exercise 10. Blank strings affecting windows

**Prompt:** Source `["A", "", "B", "C"]`. What do you get if empty strings are removed before `windowFixed(2)`? What if grouped first and then empty strings are removed within each window?

**Answer:** Filtering first yields `[["A","B"],["C"]]`. Grouping first produces `[["A",""],["B","C"]]`, then removing blanks inside each window gives `[["A"],["B","C"]]`. Processing order alters group boundaries and cannot be swapped arbitrarily.

### Exercise 11. Stopping inclusive of milestone element

**Prompt:** Write a Gatherer accepting Integers, emitting numbers from the start and stopping right after the first number `>= 5`. What result does input `[1,3,6,2,8]` give?

**Answer:** `[1,3,6]`. The integrator must emit `6` and then return `false`; use `ofSequential` when handling encounter-order-dependent prefix boundaries. `filter(n -> n < 5)` would return `[1,3,2]`, differing from the requirement.

### Exercise 12. Why does downstream.push return boolean?

**Prompt:** If downstream has already received enough elements, is it proper for a Gatherer to keep emitting and always return true?

**Answer:** No. `push` returns false when downstream no longer wants more. The integrator must respect this signal and avoid emitting further elements. `isRejecting()` only assists with best-effort early checks.

### Exercise 13. Does andThen optimize parallel automatically?

**Prompt:** Given `A` using `ofSequential` and `B` with a valid combiner. Does `A.andThen(B)` guarantee both stages run in parallel?

**Answer:** No. Each Gatherer has its own processing contract; one sequential stage can constrain the entire chain. Parallelizing requires a valid split/merge mechanism, not just adding `parallel()` or `andThen`.

### Exercise 14. Finisher and final output

**Prompt:** Gatherer `A` emits nothing in its integrator, yet its finisher emits String `"count=4"`. Gatherer `B` turns a String into its length. What does `A.andThen(B)` return?

**Answer:** Emits one element `[7]`, because `"count=4"` has 7 characters. Output emitted in A's finisher still flows through Gatherer B.

### Exercise 15. Sliding and fixed

**Prompt:** For `[1,2,3,4,5]` and window size 3, how many lists does each window type emit?

**Answer:** `windowFixed(3)` emits two lists `[[1,2,3],[4,5]]`; `windowSliding(3)` emits three lists `[[1,2,3],[2,3,4],[3,4,5]]`.

### Exercise 16. Java 21 codebase

**Prompt:** A project runs on Java 21 and needs `stream.gather(g1.andThen(g2))`. Can Java 24 code be copied directly?

**Answer:** No. Stream Gatherers were only standardized in Java 24 after previews in 22/23; Java 21 does not have this API. If upgrading the JDK is impossible, express the logic using `map`/`flatMap`/`collect`/`Spliterator` or loops, per business requirements.

### Exercise 17. Checking equivalence

**Prompt:** Does merely comparing the outputs of `gather(a.andThen(b))` and `gather(a).gather(b)` prove the business requirement is met?

**Answer:** Not enough. Both could apply the same wrong comparator, wrong window size, or wrong formula. An independent oracle and boundary cases are also needed.

### Exercise 18. Mismatched data types

**Prompt:** Gatherer A emits `List<Integer>`, Gatherer B accepts `String`. Can `A.andThen(B)` be used?

**Answer:** Incompatible types cannot be chained directly. An intermediate `List<Integer> → String` Gatherer is needed, or A's output / B's input contract must change.

---

## 27. Final checklist

A chain `A.andThen(B)` is well-designed when:

- **Types match:** `output(A)` fits into `input(B)`.
- **Order is right:** A clearly runs before B, not swapped by guesswork.
- **Element counts match:** Accounted for A/B emitting 0, 1, or many elements.
- **Empty source works:** Behavior of each finisher is understood.
- **Final window works:** Not assuming every batch has full size.
- **Short-circuit works:** Respects signals from `downstream.push`.
- **State is safe:** Never retains state/`Downstream` outside valid calls or shares mutable objects.
- **Parallelism is safe:** Never attaches a broken combiner; never promises speedup with a sequential stage.
- **Resources are safe:** Closes I/O sources at the appropriate layer without relying on finisher as cleanup.
- **Results are verified:** Checked against an oracle and invariants, not just comparing two ways of writing the same chain.
- **Version is right:** Compiles and runs on JDK 24+ when using the standard Gatherer API.
- **Performance is measured:** Never claims `andThen` automatically fuses or saves memory.

### Reference documentation

- Official Java 24 Javadoc — [Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- Official Java 24 Javadoc — [Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html)
- Standardization specification — [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485)

---

## Summary

`Gatherer.andThen(...)` is the mechanism for **composing intermediate Stream transformations**: output `R` of the first Gatherer becomes the input of the second Gatherer, creating a new Gatherer of type `T → RR`. By contract, `stream.gather(a.andThen(b))` is semantically equivalent to `stream.gather(a).gather(b)`.

In practice, `andThen` is especially helpful for packaging workflows such as **windowing → summing per window → running total**, **filtering/normalizing → batching**, or **folding → formatting results**. You must understand **finishers emitting final elements**, **short-circuiting**, **per-run private state**, **intermediate types**, and **parallel processing limits** before turning a chain into a reusable library component.

**Remember:** `andThen` is an **ordered composition**, not a concatenation of two results or a speedup guarantee. To write correct Java Stream API code, define each Gatherer's input/output clearly, verify with an independent oracle, and run on a JDK supporting the final API (Java 24+).

