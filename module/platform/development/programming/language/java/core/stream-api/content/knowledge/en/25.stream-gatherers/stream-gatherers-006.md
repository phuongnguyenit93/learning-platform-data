# Folding Data with Gatherers.fold

## 1. Problem: folding the whole stream into one result while staying inside the pipeline

In the **Java Stream API**, a pipeline typically starts from `Collection.stream()`, applies `filter`, `map`, and ends with `reduce` or `collect`. Those terminal operations produce a result, yet also **consume the Stream**: you cannot chain another intermediate operation onto a Stream that has already terminated.

Starting from **Java 24**, the **Stream Gatherers** API adds a way to express an accumulation as an **intermediate operation**:

```java
Stream<Integer> resultStream = Stream.of(2, 3, 4)
        .gather(Gatherers.fold(
                () -> 0,
                Integer::sum
        ));

System.out.println(resultStream.toList()); // [9]
```

`Gatherers.fold` takes an initial value and a function that merges each new element into the result being built. It traverses elements, updates the accumulated state, and **emits exactly one aggregated value when the input ends**, provided processing completes normally and downstream accepts the result.

```text
Source Stream:      2       3       4
                     \      |      /
                        Gatherers.fold
                  initial = 0
                  0 + 2 = 2
                  2 + 3 = 5
                  5 + 4 = 9
                          |
                        [9]
                          |
                map / filter / findFirst / toList
```

The result `[9]` is **a Stream containing one element**, not an integer returned directly from `gather`. Therefore, you can continue with `map`, `filter`, or other Gatherers before the terminal operation.

This lesson belongs to the **Stream Gatherer** chapter of the `JAVA_STREAM_API` module. Alongside `fold`, the module covers lazy pipelines, `reduce`/`collect`, parallel processing, and stateful Gatherers; this lesson focuses on **ordered folding of the entire input**.

**Objectives:** after this lesson, you will be able to:

1. Read the signature and contract of `Gatherers.fold` accurately.
2. Distinguish `initial`, `folder`, single output, and empty-stream handling.
3. Compare `fold` with `reduce`, `collect`, and `Gatherers.scan`.
4. Write order-dependent folds such as counting state transitions.
5. Choose immutable or mutable accumulators with a safe lifecycle.
6. Combine `fold` with other steps, handling finite sources, short-circuiting, I/O, and parallel limits.

## 2. Java version and API location

**Stream Gatherers were finalized as an official API in JDK 24** (JEP 485). `Stream.gather` and `java.util.stream.Gatherers.fold` are not available as standard APIs in JDK 17/21. Gatherers appeared in preview in earlier JDKs; the examples in this lesson use **JDK 24+** and do not require `--enable-preview`.

Main imports:

```java
import java.util.stream.Stream;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
```

`Stream.gather(...)` accepts a `Gatherer` and returns **a new Stream**. `Gatherers` is the class providing commonly used Gatherers, including `fold`, `scan`, `windowFixed`, `windowSliding`, and `mapConcurrent`.

Example from a `List`:

```java
List<Integer> values = List.of(3, 5, 7);

int total = values.stream()
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(total); // 15
```

`findFirst` here is the terminal operation reading the **one final result** that `fold` emits. If the business logic only needs a sum of numbers, `mapToInt(Integer::intValue).sum()` or `reduce` is usually shorter and simpler. What makes `fold` distinctive is that **the accumulated result keeps flowing through a Stream pipeline before terminating**.

## 3. Signature and contract of Gatherers.fold

Official signature:

```java
public static <T, R> Gatherer<T, ?, R> fold(
        Supplier<R> initial,
        BiFunction<? super R, ? super T, ? extends R> folder
);
```

Meaning of components:

| Component | Type | Role |
| --- | --- | --- |
| `T` | Input type | Each element drawn from the source Stream. |
| `R` | Accumulator and output type | Aggregated state built up so far. |
| `initial` | `Supplier<R>` | Provides the initial accumulated value for the evaluation pass. |
| `folder` | Conceptually `BiFunction<R, T, R>` | Receives current accumulated result and a new element, returns next accumulated result. |
| Result of `fold` | `Gatherer<T, ?, R>` | Passed to `Stream.gather(...)`, producing `Stream<R>`. |

`fold` is an **ordered, reduction-like gatherer**: it performs accumulation sequentially when the source has encounter order, suitable for folds without an easily defined combiner or that are inherently order-dependent.

If no error occurs during processing, `fold` **emits only one output element**. More importantly, when the input is empty, the emitted result is **the value supplied by `initial`**.

```java
List<Integer> oneResult = Stream.of(1, 2, 3)
        .gather(Gatherers.fold(() -> 10, Integer::sum))
        .toList();

List<Integer> emptySourceResult = Stream.<Integer>empty()
        .gather(Gatherers.fold(() -> 10, Integer::sum))
        .toList();

System.out.println(oneResult);         // [16]
System.out.println(emptySourceResult);  // [10]
```

**Distinguish an empty source from an empty result Stream.** After `fold` completes on an empty source, it still emits the initial value. This is a very important difference from `Stream.reduce(BinaryOperator)` without an identity, which returns `Optional.empty()` on an empty source.

Both `initial` and `folder` parameters must be non-`null`; passing `null` for either throws `NullPointerException` per the API contract.

## 4. Data flow inside a fold operation

Take the number sequence `[4, 2, 3]` and the folder `(sum, value) -> sum + value`.

| Step | Prior value | Incoming element | Folder returns | Emitted downstream yet? |
| --- | ---: | ---: | ---: | --- |
| Init | — | — | `0` from `initial` | Not yet |
| 1 | 0 | 4 | 4 | Not yet |
| 2 | 4 | 2 | 6 | Not yet |
| 3 | 6 | 3 | 9 | Not yet |
| End | 9 | Source exhausted | 9 | **Emits `9`** |

```java
List<Integer> output = Stream.of(4, 2, 3)
        .gather(Gatherers.fold(
                () -> 0,
                (sum, value) -> sum + value
        ))
        .toList();

System.out.println(output); // [9]
```

Key characteristics:

- `folder` runs element by element **when the terminal operation begins consuming the pipeline**.
- `folder` does not emit an element downstream after every addition; it updates internal state.
- The final accumulated value is emitted once there are no more input elements to process.
- A `fold` can aggregate a large source into **one** value without keeping a List holding the entire source, depending on the structure of `R`.

`Gatherers.fold` **is not `map`**: `map` typically turns each input element into one output; `fold` is **many-to-one** and must reach the end of the source to determine the final value.

## 5. initial is a Supplier, not a global accumulator

The first parameter is `Supplier<R>`, not an `R` object passed directly:

```java
Gatherer<Integer, ?, Integer> foldSum =
        Gatherers.fold(() -> 0, Integer::sum);
```

This design lets the Gatherer obtain an initial state tailored to **each evaluation pass**. `Supplier` is especially important when the accumulator is a mutable object such as `StringBuilder`, `StringJoiner`, or a multi-field class.

### Right: creating fresh state

```java
Gatherer<String, ?, StringJoiner> joinerGatherer =
        Gatherers.fold(
                () -> new StringJoiner(" | "),
                (joiner, word) -> joiner.add(word)
        );
```

Each time state is created, the supplier returns a **fresh** `StringJoiner`. `StringJoiner.add` updates the object and returns itself; thus the folder matches `BiFunction<R,T,R>`.

### Wrong: returning the same shared mutable state

```java
StringJoiner shared = new StringJoiner(" | ");

Gatherer<String, ?, StringJoiner> unsafe =
        Gatherers.fold(
                () -> shared,       // Does not create a new object.
                (acc, word) -> acc.add(word)
        );
```

`shared` may retain data from a previous evaluation or be modified by another part of the application. The pattern above creates an unnecessary **shared-state point**, making results depend on object usage history.

**Rule:** if using a mutable accumulator, have `initial` create a new instance; if using an immutable accumulator, you may return an immutable starting value.

Do not attach business side effects to `initial` assuming the supplier is always invoked a fixed number of times. Treat it as a state-creation mechanism, not a place to send notifications or write data.

## 6. Simple examples: sum, product, and joining strings

### Sum of numbers

```java
int total = Stream.of(1, 2, 3, 4)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(total); // 10
```

### Product of numbers

```java
long product = Stream.of(2L, 3L, 4L)
        .gather(Gatherers.fold(() -> 1L, (a, b) -> a * b))
        .findFirst()
        .orElseThrow();

System.out.println(product); // 24
```

Here `0` is the additive identity and `1` is the multiplicative identity. Setting an unsuitable `initial` changes the result:

```java
int withInitialTen = Stream.of(1, 2, 3)
        .gather(Gatherers.fold(() -> 10, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(withInitialTen); // 16, not 6
```

### Joining tokens in order

```java
import java.util.StringJoiner;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

String joined = Stream.of("alice", "bob", "charlie")
        .gather(Gatherers.<String, StringJoiner>fold(
                () -> new StringJoiner(" -> "),
                (builder, token) -> builder.add(token)
        ))
        .map(StringJoiner::toString)
        .findFirst()
        .orElseThrow();

System.out.println(joined); // alice -> bob -> charlie
```

This string-joining example shows an **ordered fold**: changing element order changes the result. If you only need to join strings, `Collectors.joining(" -> ")` in a terminal operation is usually shorter; use `fold` when you want to insert a fold **between** Stream processing steps.

## 7. Comparing fold, reduce, collect, and scan

All of these methods can involve accumulation, yet their **pipeline position** and **output count** differ:

| Tool | Kind of operation? | Output on `[2,3,4]` starting sum at 0 | When appropriate? |
| --- | --- | --- | --- |
| `reduce(0, Integer::sum)` | Terminal | Value `9` | Only need a single reduced value and the operation fits the reduction contract. |
| `collect(...)` | Terminal | E.g. a Collection or summary object | Need mutable reduction, grouping, or built-in collectors. |
| `gather(Gatherers.fold(...))` | Intermediate | A Stream containing `[9]` | Need ordered accumulation while still chaining the pipeline. |
| `gather(Gatherers.scan(...))` | Intermediate | Stream `[2,5,9]` | Need **every intermediate accumulated value**. |

### reduce

```java
int reduced = Stream.of(2, 3, 4)
        .reduce(0, Integer::sum);

System.out.println(reduced); // 9
```

`reduce` ends the Stream and returns the result directly. On a parallel Stream, identity, accumulator, and combiner must satisfy the reduction contract; non-associative operations can yield unexpected results when data is split.

### fold

```java
List<Integer> folded = Stream.of(2, 3, 4)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .map(sum -> sum * 10)
        .toList();

System.out.println(folded); // [90]
```

`fold` **keeps the result inside the Stream world**: you can continue with `map`, combine with another Gatherer, or pass it to an API that only accepts a Stream. If no further chained steps are needed, `reduce` is usually easier to read.

### scan

```java
List<Integer> scanned = Stream.of(2, 3, 4)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(scanned); // [2, 5, 9]
```

`scan` emits a value after **each** update, thus producing three results for three elements. `fold` does not emit `2` or `5` downstream; it emits only the final `9`.

With an empty source, the difference is even clearer:

```java
System.out.println(
        Stream.<Integer>empty()
                .gather(Gatherers.fold(() -> 0, Integer::sum))
                .toList()
); // [0]

System.out.println(
        Stream.<Integer>empty()
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList()
); // []

System.out.println(
        Stream.<Integer>empty()
                .reduce(Integer::sum)
); // Optional.empty
```

### collect

```java
long count = Stream.of("A", "B", "C")
        .collect(Collectors.counting());

System.out.println(count); // 3
```

`collect` is a terminal operation. If you want frequencies by key or a multi-group structure, collectors such as `groupingBy`, `toMap`, and `summarizingLong` are usually more suitable than building a custom fold.

## 8. Order-dependent fold: counting state transitions

One strength of `fold` is processing data **in sequence** and carrying state from the previous element to the next. Problem: count how many times a device's state changes in a sequence:

```text
NEW, NEW, RUNNING, RUNNING, DONE, RUNNING
         |               |      |
         +--- change --->+- chg +- change

Transition count = 3
Final state = RUNNING
```

To count transitions, we must remember **the immediately preceding state**. A simple `sum` or `count` over each element independently cannot understand adjacent pairs.

Define an immutable accumulator:

```java
record TransitionState(
        boolean started,
        String last,
        long changes
) {}
```

The `started` flag distinguishes the initial "no element seen yet" state from an uninitialized `last`. This is safer than using `last == null` as an initialization sentinel if business data allows null keys.

Apply `fold`:

```java
List<String> statuses = List.of(
        "NEW", "NEW", "RUNNING", "RUNNING", "DONE", "RUNNING"
);

TransitionState transitions = statuses.stream()
        .gather(Gatherers.<String, TransitionState>fold(
                () -> new TransitionState(false, null, 0),
                (state, current) -> {
                    if (!state.started()) {
                        return new TransitionState(true, current, 0);
                    }

                    long nextChanges = state.changes()
                            + (Objects.equals(state.last(), current) ? 0 : 1);
                    return new TransitionState(
                            true, current, nextChanges
                    );
                }
        ))
        .findFirst()
        .orElseThrow();

System.out.println(transitions.changes()); // 3
System.out.println(transitions.last());    // RUNNING
```

Each step returns a **new** `TransitionState` without mutating a global state. This is easy to reason about for a small state. Allocating a record on each step has a cost; if data is massive and profiling shows it is expensive, consider a mutable accumulator **created fresh per evaluation**.

### Why not use parallel reduction with subtraction or pair comparison?

A computation depending on **the immediately preceding element** generally cannot combine two partial results with simple addition without carrying boundary information. `fold` processes sequentially, allowing direct logic. If you want a parallelizable reduction, you must design an accumulator containing **first/last elements and transition count** so a combiner can merge boundaries correctly.

## 9. Aggregating multiple business metrics in one pass

Another usage pattern for `fold` is producing **a summary object** instead of just a single number:

```java
record Invoice(String id, long amountCents, boolean paid) {}

record SalesSummary(
        long paidCount,
        long paidAmountCents,
        long unpaidCount
) {}
```

For each `Invoice`, the accumulator creates a new `SalesSummary`:

```java
List<Invoice> invoices = List.of(
        new Invoice("I01", 1_200, true),
        new Invoice("I02", 700, false),
        new Invoice("I03", 400, true),
        new Invoice("I04", 300, false)
);

SalesSummary summary = invoices.stream()
        .gather(Gatherers.<Invoice, SalesSummary>fold(
                () -> new SalesSummary(0, 0, 0),
                (state, invoice) -> {
                    if (invoice.paid()) {
                        return new SalesSummary(
                                state.paidCount() + 1,
                                Math.addExact(
                                        state.paidAmountCents(),
                                        invoice.amountCents()
                                ),
                                state.unpaidCount()
                        );
                    }
                    return new SalesSummary(
                            state.paidCount(),
                            state.paidAmountCents(),
                            state.unpaidCount() + 1
                    );
                }
        ))
        .findFirst()
        .orElseThrow();

System.out.println(summary);
// SalesSummary[paidCount=2, paidAmountCents=1600, unpaidCount=2]
```

`Math.addExact` detects overflow when adding `long` monetary amounts; counters may also need overflow guards on massive datasets. The example treats amounts in **minor units** (cents) and assumes inputs are already validated.

Using a record ensures **the output accumulator is shallowly immutable**: all fields are primitives. When data contains mutable Lists/Maps inside, a record does not automatically make all components deeply immutable.

If only total amount is needed, `mapToLong(Invoice::amountCents).sum()` (or overflow-checked addition) is more concise. `fold` makes more sense when **multiple state fields interact**, or when the result must continue through subsequent Stream steps.

## 10. Mutable accumulator: when to use and what to avoid?

A `folder` may **mutate an accumulator object and return it**:

```java
String joined = Stream.of("A", "B", "C")
        .gather(Gatherers.<String, StringJoiner>fold(
                () -> new StringJoiner(","),
                (joiner, part) -> joiner.add(part)
        ))
        .map(StringJoiner::toString)
        .findFirst()
        .orElseThrow();

System.out.println(joined); // A,B,C
```

This is an accumulator with **internal** state scoped to a single evaluation, not a `StringJoiner` mutated across multiple pipelines. For long strings, this usually avoids many intermediate `String` objects compared to:

```java
String result = Stream.of("A", "B", "C")
        .gather(Gatherers.fold(
                () -> "",
                (text, part) -> text.isEmpty() ? part : text + "," + part
        ))
        .findFirst()
        .orElseThrow();
```

Step-by-step String concatenation can allocate many copies, causing overhead to grow significantly for long sequences. Still, when the task is purely joining strings, `Collectors.joining(",")` remains the simpler standard option.

### Risk when publishing a mutable accumulator

`fold` emits the final `R` value itself. If `R` is a mutable `ArrayList`, `StringBuilder`, or `Map` exposed directly outside, callers can mutate it. If an unmodifiable result is required, convert the state to an immutable value **before publishing**:

```java
List<String> snapshot = Stream.of("A", "B", "C")
        .gather(Gatherers.<String, ArrayList<String>>fold(
                ArrayList::new,
                (list, item) -> {
                    list.add(item);
                    return list;
                }
        ))
        .map(List::copyOf)
        .findFirst()
        .orElseThrow();

System.out.println(snapshot); // [A, B, C]
// snapshot.add("D"); // UnsupportedOperationException
```

`List.copyOf` creates a structurally unmodifiable List and **rejects null elements**. It is a shallow copy: if elements are mutable objects, they can still be altered elsewhere.

**Do not choose fold to collect a List if you just want a List of all elements.** `Stream.toList()` or `Collectors.toCollection(ArrayList::new)` is clearer and has the opportunity to leverage parallel characteristics of standard collection.

## 11. Combining fold with other Stream operations

Because `fold` is an **intermediate Gatherer**, it can compose with `filter`, `map`, `windowFixed`, and post-processing steps. Distinguish **operations before fold** from **operations after fold**.

### Filtering before folding

```java
List<Integer> totals = Stream.of(1, 2, 3, 4, 5, 6)
        .filter(n -> n % 2 == 0)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(totals); // [12] from 2 + 4 + 6
```

`filter` runs on **the original elements**, then fold combines the remaining elements.

### Filtering after folding

```java
List<Integer> acceptedTotal = Stream.of(1, 2, 3)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .filter(sum -> sum >= 10)
        .toList();

System.out.println(acceptedTotal); // []
```

Here `filter` sees only **a single sum** of `6`, rather than filtering individual source elements. If the condition is "sum at least 10", placing it after fold is right; if the condition is "only add numbers at least 10", filter beforehand.

### Folding after windowing

`Gatherers.windowFixed` creates consecutive windows, and then `fold` can accumulate a metric over **the stream of windows**:

```java
List<Integer> totalWindowSizes = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(Gatherers.windowFixed(3))
        .gather(Gatherers.<List<Integer>, Integer>fold(
                () -> 0,
                (count, window) -> count + window.size()
        ))
        .toList();

System.out.println(totalWindowSizes); // [6]
```

The input to fold here is no longer `Integer` but `List<Integer>`. Read the data type carefully at **every step boundary** in the pipeline.

### scan then fold

```java
List<Integer> sumOfPrefixes = Stream.of(1, 2, 3)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(sumOfPrefixes); // [10] = 1 + 3 + 6
```

This is **the sum of the prefix sums**, not the initial sum `1 + 2 + 3 = 6`. When chaining multiple Gatherers, each stage receives **the output of the previous stage**, so type compatibility alone does not guarantee business correctness.

## 12. Short-circuiting, infinite sources, and pipeline effects

`Gatherers.fold` only knows the final result after **consuming all assigned input**. Therefore:

```java
int total = Stream.of(1, 2, 3, 4)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(total); // 10
```

Even though the terminal operation is `findFirst()`, it **cannot obtain the fold result after the first element**. The very first output of fold is the result emitted when accumulation finishes.

### limit before fold: capping the number of input elements

```java
List<Integer> limitedInput = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(limitedInput); // [15]
```

`limit(5)` sits **before** fold, so the Gatherer sees only the first 5 elements. This is one way to turn an infinite source into a finite portion that can be folded.

### limit after fold: capping output, not accumulated data

```java
List<Integer> limitedOutput = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .limit(1)
        .toList();

System.out.println(limitedOutput); // [15]
```

`limit(1)` applies only to **the output Stream after fold**, which already has at most one element. It does not truncate the input to one element.

**Infinite-source warning:** if the source never ends, a standard `fold` **cannot emit a final total**, because there is never an "end of input" point. Pipelines like the following must not be used if you actually expect a result:

```java
// Do not run without a stopping condition:
// Stream.iterate(1L, n -> n + 1)
//         .gather(Gatherers.fold(() -> 0L, Long::sum))
//         .findFirst();
```

For infinite or real-time data, choose **`scan` for step-by-step accumulated results**, or split data into finite windows and aggregate per window. Do not wait for a "final" result from a source that has no endpoint.

## 13. Source ordering and parallel processing

The API documentation describes `fold` as an **ordered** and **reduction-like** operation, suited when folding depends on sequence order or lacks a clear combiner.

### With encounter order

```java
String text = List.of("A", "B", "C")
        .parallelStream()
        .gather(Gatherers.fold(
                () -> "",
                (acc, part) -> acc + part
        ))
        .findFirst()
        .orElseThrow();

System.out.println(text); // ABC
```

The `List` source has encounter order; even though upstream may run in parallel, the fold step must respect **ordered accumulation semantics**. `fold` is not a mechanism to turn an inherently sequential fold into an efficiently parallel one.

### Without encounter order

```java
Set<String> set = new HashSet<>(List.of("A", "B", "C"));

String text = set.stream()
        .gather(Gatherers.fold(
                () -> "",
                (acc, part) -> acc + part
        ))
        .findFirst()
        .orElseThrow();

// Cannot assert the result is "ABC".
```

`HashSet` does not guarantee encounter order, so string concatenation has no stable business order. If order matters, use an ordered source or `sorted()` with a suitable comparator **before fold**:

```java
String sortedText = set.stream()
        .sorted()
        .gather(Gatherers.fold(() -> "", (acc, part) -> acc + part))
        .findFirst()
        .orElseThrow();

System.out.println(sortedText); // ABC
```

### Does fold have a combiner?

`Gatherers.fold` does not provide a combiner to split and merge accumulation across multiple source partitions like a standard parallel reduction. When a Gatherer has no combiner, **that gather stage does not execute in parallel via state splitting/merging**; other parts of the pipeline may have their own execution strategies. Do not assume adding `parallel()` makes `fold` itself faster.

If the computation is an **associative** sum, count, or extremum, `reduce`, primitive `sum`, or standard collectors may fit parallel Streams better. If the computation depends on the immediately preceding state, sequential `fold` usually expresses it more accurately than a hastily written combiner.

## 14. Non-interference, arithmetic errors, and null

### Do not modify the source inside folder

`folder` should compute the next state from the accumulated value and the current element without modifying the collection being traversed:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// WRONG: interferes with the source itself while the Stream is traversing.
// source.stream().gather(Gatherers.fold(
//         () -> 0,
//         (acc, item) -> {
//             source.add(item);
//             return acc + item;
//         }
// )).toList();
```

The operation above can corrupt the source structure or throw `ConcurrentModificationException`. Separate data processing from source updates, or prepare a stable snapshot before computing.

### Overflow

`Integer::sum` and `Long::sum` do not report overflow in a way you can rely on for financial business logic. When overflow detection is required:

```java
long safeSum = Stream.of(1_000_000L, 2_000_000L)
        .gather(Gatherers.fold(() -> 0L, Math::addExact))
        .findFirst()
        .orElseThrow();

System.out.println(safeSum); // 3000000
```

If the `long` range is exceeded, `Math.addExact` throws `ArithmeticException`. For decimal currency or calculations requiring high precision, consider `BigDecimal` and explicit rounding rules.

### Null

The `initial` and `folder` function arguments must not be null. For **null input elements**, the folder must have a specific policy; a method reference like `Integer::sum` cannot handle null.

```java
List<Integer> nullable = Arrays.asList(1, null, 3);

int nonNullSum = nullable.stream()
        .filter(Objects::nonNull)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(nonNullSum); // 4
```

For a **null accumulated result**, downstream operations like `findFirst` cannot wrap null into an `Optional` and may throw `NullPointerException`. Design a non-null result state, or use `Optional`/a value object to represent missing data.

### Exceptions inside folder

If `initial`, `folder`, or a downstream step throws an exception, the terminal operation may fail; `fold` does not automatically roll back side effects already executed inside the function. Therefore, avoid sending emails, writing records, or charging payments inside folder just to piggyback on the traversal.

## 15. Complete Java 24+ example: order summary and state transitions

The following example uses `fold` to compute an immutable report object and an **order-dependent** fold. The program uses Java 24+ and requires no external libraries.

Save as `FoldGathererDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FoldGathererDemo {
    record Invoice(String id, long amountCents, boolean paid) {
        Invoice {
            Objects.requireNonNull(id, "id");
            if (amountCents < 0) {
                throw new IllegalArgumentException("amountCents < 0");
            }
        }
    }

    record SalesSummary(
            long paidCount,
            long paidAmountCents,
            long unpaidCount
    ) {}

    record TransitionState(
            boolean started,
            String last,
            long changes
    ) {}

    static SalesSummary summarize(List<Invoice> invoices) {
        return invoices.stream()
                .gather(Gatherers.<Invoice, SalesSummary>fold(
                        () -> new SalesSummary(0L, 0L, 0L),
                        (state, invoice) -> {
                            if (invoice.paid()) {
                                return new SalesSummary(
                                        Math.addExact(state.paidCount(), 1L),
                                        Math.addExact(
                                                state.paidAmountCents(),
                                                invoice.amountCents()
                                        ),
                                        state.unpaidCount()
                                );
                            }
                            return new SalesSummary(
                                    state.paidCount(),
                                    state.paidAmountCents(),
                                    Math.addExact(state.unpaidCount(), 1L)
                            );
                        }
                ))
                .findFirst()
                .orElseThrow();
    }

    static TransitionState countTransitions(List<String> statuses) {
        return statuses.stream()
                .gather(Gatherers.<String, TransitionState>fold(
                        () -> new TransitionState(false, null, 0L),
                        (state, current) -> {
                            Objects.requireNonNull(current, "current");
                            if (!state.started()) {
                                return new TransitionState(
                                        true, current, 0L
                                );
                            }
                            boolean changed = !Objects.equals(
                                    state.last(), current
                            );
                            return new TransitionState(
                                    true,
                                    current,
                                    Math.addExact(
                                            state.changes(),
                                            changed ? 1L : 0L
                                    )
                            );
                        }
                ))
                .findFirst()
                .orElseThrow();
    }

    public static void main(String[] args) {
        List<Invoice> invoices = List.of(
                new Invoice("I01", 1_200L, true),
                new Invoice("I02", 700L, false),
                new Invoice("I03", 400L, true),
                new Invoice("I04", 300L, false)
        );

        SalesSummary summary = summarize(invoices);
        SalesSummary emptySummary = summarize(List.of());

        List<String> statuses = List.of(
                "NEW", "NEW",
                "RUNNING", "RUNNING",
                "DONE", "RUNNING"
        );
        TransitionState transitions = countTransitions(statuses);
        TransitionState emptyTransitions = countTransitions(List.of());

        List<Integer> folded = Stream.of(2, 3, 4)
                .gather(Gatherers.fold(() -> 0, Integer::sum))
                .toList();

        List<Integer> scanned = Stream.of(2, 3, 4)
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();

        String joined = statuses.stream()
                .gather(Gatherers.<String, StringJoiner>fold(
                        () -> new StringJoiner(" -> "),
                        (builder, item) -> builder.add(item)
                ))
                .map(StringJoiner::toString)
                .findFirst()
                .orElseThrow();

        if (!summary.equals(new SalesSummary(2, 1_600L, 2))) {
            throw new AssertionError("Wrong order summary");
        }
        if (!emptySummary.equals(new SalesSummary(0, 0, 0))) {
            throw new AssertionError("Empty-source fold did not return initial");
        }
        if (!transitions.equals(
                new TransitionState(true, "RUNNING", 3))) {
            throw new AssertionError("Wrong transition count");
        }
        if (!emptyTransitions.equals(
                new TransitionState(false, null, 0))) {
            throw new AssertionError("Wrong state on empty source");
        }
        if (!folded.equals(List.of(9))
                || !scanned.equals(List.of(2, 5, 9))) {
            throw new AssertionError("Wrong fold/scan semantics");
        }

        System.out.println("Summary: " + summary);
        // Summary: SalesSummary[paidCount=2, paidAmountCents=1600,
        //                       unpaidCount=2]
        System.out.println("Transitions: " + transitions);
        // Transitions: TransitionState[started=true, last=RUNNING,
        //                              changes=3]
        System.out.println("Fold: " + folded); // [9]
        System.out.println("Scan: " + scanned); // [2, 5, 9]
        System.out.println("Trace: " + joined);
        System.out.println("PASS");
    }
}
```

Compile and run:

```text
javac FoldGathererDemo.java
java FoldGathererDemo
```

### What the example demonstrates

1. **Proper initialization:** `SalesSummary` and `TransitionState` have clear starting values.
2. **Empty source:** `fold` still returns one `initial` result, so `orElseThrow` does not fail.
3. **Stateful folder without external writes:** each step produces a new summary record.
4. **Order matters:** `countTransitions` checks the immediately preceding state, unlike global state counting.
5. **Single output vs. multiple outputs:** `folded` is `[9]`, while `scanned` is `[2,5,9]`.
6. **Private mutable accumulator:** `StringJoiner` is created by the supplier and converted to `String` before returning.
7. **Deterministic checks:** `if` + `throw` checks detect mismatches without relying on the JVM's `-ea` flag.

Do not run Gradle or a Content QA loop during the authoring step. When deploying for real, compile with **JDK 24+**, add project tests, and verify specific data-handling requirements.

## 16. Practice exercises and reference solutions

### Exercise 1 — Folding a sum and empty-source case

**Data:** `[5, 10, 20]`. Fold into a single sum with `Gatherers.fold`, then test with `Stream.empty()`. Results should be `[35]` and `[0]`.

```java
List<Integer> sums = Stream.of(5, 10, 20)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

List<Integer> emptySums = Stream.<Integer>empty()
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(sums);      // [35]
System.out.println(emptySums); // [0]
```

### Exercise 2 — Count and sum statistics in one accumulator

**Data:** `[3, 7, 10]`. Create a record with `count` and `sum`, then use fold.

```java
record CountSum(long count, long sum) {}

CountSum data = Stream.of(3, 7, 10)
        .gather(Gatherers.<Integer, CountSum>fold(
                () -> new CountSum(0, 0),
                (state, n) -> new CountSum(
                        state.count() + 1,
                        state.sum() + n
                )
        ))
        .findFirst()
        .orElseThrow();

System.out.println(data); // CountSum[count=3, sum=20]
```

**Extension:** when `count==0`, the average cannot be defined as `sum/count`. Return `OptionalDouble.empty()` or an explicit "no data" representation.

### Exercise 3 — Distinguishing fold and scan

**Task:** with `[4, 1, 5]`, predict the output of the two pipelines below:

```java
List<Integer> a = Stream.of(4, 1, 5)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

List<Integer> b = Stream.of(4, 1, 5)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();
```

**Answer:** `a = [10]`, `b = [4, 5, 10]`. `fold` emits one final sum; `scan` emits prefix sums.

### Exercise 4 — Counting consecutive value changes

**Data:** `[A, A, B, A, A, C]`. Count how many times the value changes, not the number of distinct values.

```java
List<String> values = List.of("A", "A", "B", "A", "A", "C");

TransitionState s = countTransitions(values);

System.out.println(s.changes()); // 3
System.out.println(s.last());    // C
```

**Explanation:** there are three changes `A → B`, `B → A`, `A → C`. Using `distinct().count()` yields only three distinct values, which is a **different** metric from transition count. If historical order must be preserved, do not call `unordered()` or sort before folding.

### Exercise 5 — Bounding the source before folding

**Task:** create an infinite Stream of natural numbers, summing only **the first 10 elements**. Why must `limit(10)` come before `gather(fold(...))`?

```java
long tenNumbers = Stream.iterate(1L, n -> n + 1)
        .limit(10)
        .gather(Gatherers.fold(() -> 0L, Math::addExact))
        .findFirst()
        .orElseThrow();

System.out.println(tenNumbers); // 55
```

`limit(10)` makes **the source of fold finite**. Placing `limit(1)` after fold only caps the Gatherer's output count; it does not help it find the end of an infinite source.

### Exercise 6 — Mutable fold: shared-state bug

**Task:** explain why `() -> sharedList` (with `sharedList` created externally) is not a good supplier for `fold`. Fix it to return an unmodifiable List snapshot.

```java
List<String> safe = Stream.of("X", "Y", "Z")
        .gather(Gatherers.<String, ArrayList<String>>fold(
                ArrayList::new,
                (acc, value) -> {
                    acc.add(value);
                    return acc;
                }
        ))
        .map(List::copyOf)
        .findFirst()
        .orElseThrow();

System.out.println(safe); // [X, Y, Z]
```

`ArrayList::new` allocates a dedicated buffer per evaluation pass, while `List.copyOf` creates an unmodifiable snapshot before publishing. If you only needed this List, you could replace everything with `Stream.of("X", "Y", "Z").toList()`; the exercise is meant to practice the contract of `initial` and `folder`.

## 17. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Stream.gather` fails to compile on JDK 17/21 | Gatherers are not a standard API in those versions | Use JDK 24+ or a compatible `reduce`/`collect` solution. |
| Expecting fold to directly return an `R` | `gather` is an intermediate operation returning `Stream<R>` | Consume with `findFirst`, `toList`, or a suitable terminal operation. |
| Expecting to see every prefix sum | Confusing `fold` with `scan` | Use `Gatherers.scan` when per-element results are needed. |
| Empty source produces one element | `fold` emits the `initial` value on an empty source | Define starting value and distinguish from `reduce(BinaryOperator)`. |
| `findFirst` after fold does not stop at first element | Fold does not emit until the source ends | Limit input with `limit`/`takeWhile` **before** fold. |
| Fold on an infinite source produces no output | There is never an endpoint to emit the sum | Use `scan` or finite segmentation/windows. |
| Results carry over from a previous run | `initial` returns a shared mutable accumulator | Create a new instance via the supplier. |
| Results have wrong order | Unordered source or `unordered()` called before fold | Establish encounter order and business-appropriate comparator. |
| Adding `parallel()` does not make fold faster | Fold has no combiner to split/merge state | Use parallel reduction/collector when the operation permits. |
| Integer overflow when adding many values | `Integer::sum`/`Long::sum` exceeds range | Use `Math.addExact` or an appropriate numeric type. |
| `NullPointerException` with `findFirst` | Fold result is null or folder does not handle null elements | Use a non-null accumulator and explicit null-handling policy. |
| Side effects in folder cause corrupted data | Mutating source/external variables during computation | Keep folder focused on input and internal state without source interference. |
| Mutable result gets mutated after return | Publishing the mutable accumulator itself | Convert to an immutable record or appropriate snapshot. |
| Using fold to solve complex grouping problems | Missing out on dedicated collectors | Consider `groupingBy`, `toMap`, `summarizingLong`. |

## 18. Checklist for choosing and implementing Gatherers.fold

1. **JDK:** does the environment have Java 24+ and support official `Gatherers.fold`?
2. **Problem:** is a single final aggregate needed rather than a list of all intermediate values?
3. **Pipeline:** is there value in keeping the fold as an intermediate operation before another terminal step?
4. **Starting value:** does `initial` accurately represent the state for an empty source?
5. **Merge function:** does `folder` accept the right `R` and `T` types and return the right `R`?
6. **State:** if mutable, does the supplier create a fresh instance rather than sharing a global?
7. **Immutability:** is a snapshot/deep copy needed before publishing the result?
8. **Ordering:** does the fold depend on encounter order? Is the source already in business order?
9. **Parallelism:** have you avoided expecting `fold` to have its own parallel combiner?
10. **Short-circuiting:** are `limit`/`takeWhile` placed **before fold** if bounding the source?
11. **Infinite sources:** is there a termination condition, or was `scan`/windowing chosen instead?
12. **Null:** do source, output value, and folder have an explicit null policy?
13. **Arithmetic:** have overflow, precision loss, and rounding rules been reviewed?
14. **I/O:** is a Stream backed by a file/connection closed via `try-with-resources`?
15. **Testing:** have empty source, single element, multiple elements, different orders, and result immutability been tested?

## Remember

**`Gatherers.fold(initial, folder)`** is a Gatherer that accumulates data **in order** and emits **one aggregated value when input ends**. `initial` provides the starting state, and `folder` receives the accumulated value and a new element, returning the next accumulated value. Even when the source is empty, fold still emits the value from `initial`.

`fold` is an **intermediate operation** so its result remains `Stream<R>`, unlike terminal `reduce`/`collect`. It also differs from `scan`, which emits **every intermediate accumulated value**. `fold` fits when folding is order-dependent, such as counting state transitions, though it is not a tool that automatically speeds up parallel processing.

Design the supplier to create properly scoped state, keep folder non-interfering with the source, avoid unintentionally publishing mutable accumulators, establish encounter order, and ensure the input has an endpoint. For simple sums/counts/grouping needing only a final result, prefer `sum`, `reduce`, or `collect` when they express it more directly.

### API Documentation

- [Oracle JDK 24 — Gatherers.fold](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html)
- [Oracle JDK 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
