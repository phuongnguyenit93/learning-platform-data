# Characteristics: IDENTITY_FINISH, UNORDERED, and CONCURRENT

When calling `stream.collect(collector)`, programmers usually see results like a `List`, `Map`, or aggregated summary. Internally, the Java Stream API needs to know **whether it can create multiple accumulators and merge them**, **whether it must preserve element encounter order**, and **whether threads are allowed to accumulate into the same container**. The three characteristics of `Collector.Characteristics` — `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` — express those commitments.

This lesson belongs to the **Collect Mechanism and Collector** chapter of the `JAVA_STREAM_API` module. The goal is to properly understand the contract of the three characteristics, how they interact with lazy pipelines, `filter`, `map`, `collect`, and `parallel()`, how to build custom Collectors without falsely declaring capabilities, and when to use standard collectors like `toList`, `groupingBy`, and `groupingByConcurrent`. These decisions directly affect shared state, result ordering, correctness, and performance costs.

> The core APIs presented here have been available since Java 8. The code examples use `Arrays.asList` and `Collectors` so they can apply even to projects still on Java 8.

## 1. Collector as a data reduction contract

A `Collector<T, A, R>` describes how to aggregate data:

- `T`: the input element type of the Stream.
- `A`: the **intermediate accumulation type**.
- `R`: the **final result type** upon completion.

For example, when counting words, `T` can be `String`, `A` is a mutable counter, and `R` is `Long`.

A Collector has five components:

| Component | Responsibility |
| --- | --- |
| `supplier()` | Creates a new accumulator `A` |
| `accumulator()` | Adds one element `T` to accumulator `A` |
| `combiner()` | Merges two accumulators `A` into one `A` |
| `finisher()` | Converts `A` into result `R` |
| `characteristics()` | Declares properties that the runtime is permitted to rely on |

Logical illustration:

```text
                Stream<T>
                    |
         filter / map / flatMap
                    |
             collect(collector)
                    |
          +---------+---------+
          |                   |
      supplier()          supplier()
          |                   |
     A branch 1          A branch 2
          |                   |
     accumulator         accumulator
          |                   |
          +------ combiner ---+
                    |
                merged A
                    |
                 finisher
                    |
                 final R
```

The diagram has two branches to explain `combiner`, not as a promise that Java always splits threads that way. A Collector can run sequentially or in parallel; depending on characteristics, Java may also accumulate concurrently into **the same container** instead of using multiple separate containers.

`collect` is a **terminal operation**: calling it triggers the lazy pipeline and consumes the Stream. It does not automatically close an I/O source that requires `close()`, such as a Stream returned by `Files.lines`; resource closing responsibility must still be handled separately.

## 2. Summary table of the three Characteristics

In Java, the characteristic set is represented by the `Collector.Characteristics` enum.

| Characteristic | Collector's commitment | What you must **not** infer |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher is equivalent to the identity function: the accumulated result can be used directly as the final result | Does not mean the container is immutable, nor does it mean thread-safe |
| `UNORDERED` | Aggregation does not commit to preserving the encounter order of input elements | Does not mean data is randomly shuffled; does not automatically create concurrency |
| `CONCURRENT` | Accumulator can be called concurrently from multiple threads on **the same** container | Does not mean the source automatically becomes parallel; not synonymous with `UNORDERED` |

The three characteristics are **not mutually exclusive**. A collector can have several characteristics at once, or declare none. Each characteristic must be justified by the actual design of `supplier`, `accumulator`, `combiner`, and `finisher`; it is not an "optimization toggle" you can pick arbitrarily.

## 3. IDENTITY_FINISH: the accumulator is also the final result

`IDENTITY_FINISH` means the `finisher` function effectively performs no conversion: after accumulation, Java can use the type `A` object itself as the result `R`. By contract, converting `A` to `R` must be valid, even if the implementation skips calling `finisher()` and casts directly.

Example creating a Collector that collects `String`s into an `ArrayList<String>`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.stream.Collector;

Collector<String, ArrayList<String>, ArrayList<String>> listCollector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );

ArrayList<String> values = Arrays.asList("A", "B", "C")
        .stream()
        .collect(listCollector);

System.out.println(values); // [A, B, C]
System.out.println(listCollector.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // true
```

In the `Collector.of(supplier, accumulator, combiner, characteristics...)` overload without a separate finisher function, `IDENTITY_FINISH` is declared automatically. Here `A` and `R` are both `ArrayList<String>`, so the container can be returned directly after combining.

Point to remember: this list is still **mutable** and not implicitly safe for multiple threads adding elements simultaneously. `IDENTITY_FINISH` only speaks about the finishing step, providing no extra guarantees on thread-safety or specific collection type.

### No IDENTITY_FINISH when result type conversion is needed

Wanting to join text into a `String` from a `StringJoiner` container:

```java
import java.util.Arrays;
import java.util.StringJoiner;
import java.util.stream.Collector;

Collector<String, StringJoiner, String> joining =
        Collector.of(
                () -> new StringJoiner(", "),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString
        );

String text = Arrays.asList("Java", "Stream", "API")
        .stream()
        .collect(joining);

System.out.println(text); // Java, Stream, API
System.out.println(joining.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // false
```

`A` is `StringJoiner` while `R` is `String`. If `IDENTITY_FINISH` were wrongly declared for this collector, the runtime would be allowed to skip `StringJoiner::toString` and treat the container itself as the result. That is a **contract violation**, which can lead to wrong results or cast errors.

You also must not declare `IDENTITY_FINISH` if the final step needs to copy the container, make the result immutable, normalize data, or compute a metric from the accumulator.

### collectingAndThen changes the meaning of the finishing step

`Collectors.collectingAndThen(downstream, finisher)` adds a transformation **after** the downstream finishes. For example, creating an unmodifiable list from the result:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, List<String>> readonly =
        Collectors.collectingAndThen(
                Collectors.toList(),
                Collections::unmodifiableList
        );

List<String> result = Arrays.asList("A", "B")
        .stream()
        .collect(readonly);

System.out.println(result); // [A, B]
System.out.println(readonly.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // false
```

Because there is a new finisher, the `IDENTITY_FINISH` characteristic is no longer retained. `Collections.unmodifiableList` creates an **unmodifiable view** over the underlying list; it does not copy the data itself. When an immutable copy with different semantics is needed, design an appropriate finisher and still do **not** declare `IDENTITY_FINISH`.

**An important note:** `Collectors.toList()` does not guarantee that the result is an `ArrayList`, mutable, or thread-safe. Do not rely on the current JDK implementation class to infer a stable contract across all versions.

## 4. UNORDERED: encounter order is not required

*Encounter order* is the element traversal order determined by the source and intermediate operations. For instance, `List.stream()` is ordered by list position, whereas a source like `HashSet` does not commit to a fixed encounter order.

`UNORDERED` states that **the Collector does not require preserving encounter order in the result**. This is a characteristic **of the collection operation**, distinct from `stream.unordered()` which is an intermediate operation on the pipeline.

Example comparing a list and a set:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> source = Arrays.asList("B", "A", "B", "C");

List<String> asList = source.stream()
        .collect(Collectors.toList());

Set<String> asSet = source.stream()
        .collect(Collectors.toSet());

System.out.println(asList); // [B, A, B, C]
System.out.println(asSet.size());  // 3
System.out.println(asSet.contains("A")); // true
```

`Collectors.toList()` collects elements in encounter order when the source is ordered. `Collectors.toSet()` is specified as an **unordered collector**: what matters is which distinct elements are present in the set, not the iteration order of the `Set`.

Do not assume `asSet` always prints as `[A, B, C]` or any specific order: the Set implementation and iteration order are not guaranteed by `toSet()`.

### UNORDERED does not mean shuffling data

`UNORDERED` is not a requirement to randomize order. Java **is allowed** to execute in an order-preserving manner in some cases, but callers **must not depend on it**. Nor does it deduplicate automatically: deduplication is the decision of a specific Collector, like `toSet()`.

Similarly, `stream.unordered()` merely drops the pipeline's ordering constraint; it does not create a `shuffle` operation. If business logic requires "the first three orders chronologically", using an unordered source or unordered collector will not preserve the meaning of "first".

### Result sorting order is a separate concern

A collection may apply an **intrinsic ordering** without needing to preserve the source's encounter order. For example:

```java
import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

Set<Integer> sortedValues = Arrays.asList(9, 2, 9, 4)
        .stream()
        .collect(Collectors.toCollection(TreeSet::new));

System.out.println(sortedValues); // [2, 4, 9]
```

This order is sorted by `TreeSet` according to comparison rules, not the encounter order `9, 2, 9, 4`. The `UNORDERED` characteristic speaks to whether the collector must preserve encounter order; it does not mean the result structure cannot have its own ordering.

## 5. CONCURRENT: multiple threads can accumulate into the same A

`CONCURRENT` is a stronger commitment than "sometimes running with `parallelStream()`". It permits the runtime to call `accumulator` concurrently from multiple threads **on the exact same accumulator object `A`**.

Therefore, the container and update behavior **must withstand concurrent calls**. A regular `ArrayList` does not satisfy this contract on its own, even though its `combiner` can validly merge two independent lists.

However, we must distinguish two collection strategies:

```text
Strategy A: multiple independent containers
  supplier -> A1 --\
                    +-- combiner -> final A
  supplier -> A2 --/

Strategy B: a single shared container
  thread 1 -- accumulator --\
  thread 2 -- accumulator ---+--> shared A
  thread 3 -- accumulator --/
          (A must be safe for concurrent updates)
```

A Stream running in parallel is **not forced** to use strategy B; Java can choose how to split, combine, and optimize based on characteristics. Conversely, having `CONCURRENT` also **does not automatically turn** a sequential `stream()` into a `parallelStream()`.

### Standard collector: groupingByConcurrent

`Collectors.groupingByConcurrent` is a suitable choice when you want to group into a `ConcurrentMap` without requiring encounter order within groups:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

List<String> names = Arrays.asList(
        "java", "junit", "spring", "sql", "streams"
);

ConcurrentMap<Character, Long> counts = names.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                text -> text.charAt(0),
                Collectors.counting()
        ));

System.out.println(counts.get('j')); // 2
System.out.println(counts.get('s')); // 3
```

The result is a `ConcurrentMap`, but key iteration order **is not guaranteed**. `groupingByConcurrent` is a **concurrent and unordered** collector. The fact that a downstream collector like `counting()` does not itself declare `CONCURRENT` does not mean you should arbitrarily share downstream containers: the implementation of `groupingByConcurrent` is responsible for coordinating updates according to its contract.

If you want to group into lists preserving element encounter order, `groupingByConcurrent(..., toList())` **does not guarantee the element order of lists inside each group**. Furthermore, returning a `ConcurrentMap` does not make mutable values inside the map (like `ArrayList`) automatically safe for concurrent modification **after** collection. You must distinguish safety during collection from safety when external threads access/modify the result.

### Comparing groupingBy and groupingByConcurrent

| Collector | Typical result | Key commitment |
| --- | --- | --- |
| `groupingBy(classifier)` | `Map<K,List<T>>` | Not a concurrent collector; may need to merge maps in parallel runs |
| `groupingByConcurrent(classifier)` | `ConcurrentMap<K,List<T>>` | Concurrent, unordered; **does not** preserve per-group element encounter order |
| `groupingBy(classifier, downstream)` | `Map<K,D>` | Follows the contracts of downstream and outer collector |
| `groupingByConcurrent(classifier, downstream)` | `ConcurrentMap<K,D>` | Outer collector is concurrent and unordered; downstream updates can be coordinated safely during collection |

You should not claim that `groupingByConcurrent` is **always faster** than `groupingBy`. Key contention cost, number of distinct groups, source size, downstream collector, and partitioning characteristics determine actual benchmark results.

## 6. When is Java allowed to collect concurrently into one container?

Three factors must be examined together:

1. Is the Stream running **parallel** or **sequential**?
2. Does the Collector have the `CONCURRENT` characteristic?
3. Does the Stream have an encounter order to preserve, and does the Collector have `UNORDERED`?

The practical condition under which the framework **is permitted** to use a single-shared-container strategy in parallel collect is: Collector is `CONCURRENT` **and** (Stream has no encounter order **or** Collector is `UNORDERED`). Meeting this condition does not mean the framework is forced to choose this path in every case.

| Stream | Collector | Can accumulate concurrently into one container by contract? | Reason |
| --- | --- | --- | --- |
| Sequential | `CONCURRENT + UNORDERED` | No concurrency needed | Only one thread executes the pipeline |
| Parallel, with encounter order | Only `CONCURRENT` | Must not use shared strategy if it breaks encounter order | Collector has not waived ordering requirement |
| Parallel, with encounter order | `CONCURRENT + UNORDERED` | **Yes** | Collector permits dropping ordering constraint |
| Parallel, no encounter order | Only `CONCURRENT` | **Yes** | No encounter-order preservation requirement remains |
| Parallel, any source | Only `UNORDERED` | Not enough to share one container | Accumulator has not declared concurrent safety |
| Parallel, any source | Only `IDENTITY_FINISH` | Not enough to share one container | Finisher characteristic says nothing about concurrency |

Short mnemonic: **`CONCURRENT` answers "is shared updating safe?"; `UNORDERED` answers "may ordering requirements be dropped?"**. Both conditions may be needed together to achieve the shared-container concurrent collection path on an ordered Stream.

Do not confuse this with `Collectors.toConcurrentMap`: Collector variants designed to build a `ConcurrentMap` are typically concurrent and unordered, yet still require an appropriate merge function for duplicate keys. A custom collector returning a `ConcurrentHashMap` **does not automatically** gain the `CONCURRENT` characteristic without a properly designed accumulator and explicit declaration.

## 7. Building a Collector with CONCURRENT + UNORDERED

Example summing integers from a `Stream<Integer>` using `LongAdder`, a counter supporting concurrent updates. This illustrates how to define characteristics on a custom collector; if you only need an integer sum, `mapToLong(...).sum()` is usually simpler.

```java
import java.util.stream.Collector;
import java.util.stream.IntStream;
import java.util.concurrent.atomic.LongAdder;

Collector<Integer, LongAdder, Long> sumCollector =
        Collector.of(
                LongAdder::new,
                (adder, number) -> adder.add(number),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );

long total = IntStream.rangeClosed(1, 100_000)
        .boxed()
        .parallel()
        .collect(sumCollector);

System.out.println(total); // 5000050000
System.out.println(sumCollector.characteristics()
        .contains(Collector.Characteristics.IDENTITY_FINISH)); // false
```

Analysis:

- `supplier` creates a new `LongAdder`. Each counter starts with an initial state of 0.
- `accumulator` adds an `Integer` to the sum and is safe when multiple threads update the same `LongAdder`.
- `combiner` merges the right container's sum into the left container. It must still be correct even if a particular execution path never calls it.
- `finisher` uses `LongAdder::sum` to convert `A = LongAdder` into `R = Long`.
- `CONCURRENT` is valid because the accumulator can run on the same counter.
- `UNORDERED` is valid because summation here does not depend on element encounter order.
- There is **no** `IDENTITY_FINISH` because `LongAdder` cannot be used directly as a `Long`.

For the range `1..100_000`, the sum fits within `long`. If the sum could overflow `long`, or if the sum uses floating-point numbers with rounding error, review the data type and equivalence contract. Using `LongAdder` does not automatically guarantee correctness for every arithmetic problem.

### Risk of using ArrayList while declaring CONCURRENT

Do not do what is shown below:

```java
import java.util.ArrayList;
import java.util.stream.Collector;

// WRONG EXAMPLE: ArrayList::add is not safe when multiple threads add concurrently.
Collector<Integer, ArrayList<Integer>, ArrayList<Integer>> unsafe =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );
```

When the framework uses shared accumulation, two threads can mutate the same `ArrayList` simultaneously, causing lost elements or invalid state. `CONCURRENT` does not create locks or synchronize automatically. If you want to collect a list in encounter order, remove the two wrongly declared characteristics and use `Collectors.toList()` or a contract-compliant collector.

You should not try pre-sizing `ArrayList` or using `Collections.synchronizedList` as a mechanical "patch". Even though synchronization might make some updates safe, you still must verify ordering, performance, identity, combiner, and exactly what result is guaranteed.

## 8. How do IDENTITY_FINISH, UNORDERED, and CONCURRENT interact?

The three characteristics are semantically orthogonal: a collector may hold any **valid** combination, provided the underlying functions truly satisfy the contract.

| Combination | Example meaning | Notes |
| --- | --- | --- |
| No characteristics declared | Accumulates into `StringJoiner` then converts to `String`, order required | Uses real finisher; no concurrency assumed |
| `IDENTITY_FINISH` | Merges directly into `ArrayList` and returns the container | Not thread-safe |
| `UNORDERED` | Collects a set without caring about encounter order | Only drops ordering constraint |
| `CONCURRENT` | Container supports shared updates, but Collector still cares about order when encounter order exists | Does not grant permission to ignore order |
| `CONCURRENT + UNORDERED` | Counting/summing using a thread-safe structure regardless of order | Can leverage shared accumulation on ordered parallel Streams |
| `IDENTITY_FINISH + CONCURRENT + UNORDERED` | Directly returns a concurrent container, no conversion finisher needed | Must still prove combiner and accumulator correctness |

Use the output of `collector.characteristics()` to **inspect what was declared**, not as an automatic test proving code is thread-safe.

```java
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, Set<String>> toSet = Collectors.toSet();

boolean unordered = toSet.characteristics()
        .contains(Collector.Characteristics.UNORDERED);

System.out.println(unordered); // true
```

In real programs, a returned collector may carry characteristics depending on the overload and downstream collector; if a design decision depends on a characteristic, read the API contract of that specific collector rather than guessing from the method name.

## 9. Proper understanding of Collector contracts and performance optimization

Characteristics are only helpful when the Collector's five functions obey foundational rules:

### 9.1. Identity and associative merging

`supplier` must create a genuinely "empty" container. `combiner(a, supplier.get())` must produce a result equivalent to `a`. When merging three containers `a, b, c`, parenthesization must yield business-equivalent results. This is the prerequisite for a Stream to reduce across multiple branches.

### 9.2. Accumulator and combiner must be compatible

Incorporating a value `t` directly into `a` must be equivalent to merging `a` with a fresh container holding only `t`:

```text
accumulate(a, t)
  is equivalent to
combine(a, accumulate(supplier(), t))
```

This is a mental check, not a literal Java expression you can call directly: `accumulator` typically returns `void`, so the diagram uses the concept of before/after states.

### 9.3. Avoid side effects outside the Collector

Do not mutate the source `List` from `filter`, increment a shared counter in `map`, or write to an external `HashMap` while a parallel pipeline runs. `Collector` characteristics **do not protect** side effects in pipeline stages preceding the Collector.

### 9.4. Costs are not just about thread count

`CONCURRENT` can avoid the cost of creating multiple containers and combining, yet may introduce contention on a single structure. `UNORDERED` can allow more flexible strategies, but if business logic requires ordered results, that trade-off is invalid. `IDENTITY_FINISH` can skip a final conversion, yet the benefit is minor if most time is spent on I/O, hashing, DB queries, or sorting.

An optimization is only meaningful when it **still preserves the data contract**. Benchmark with real input sizes, key distributions, duplicate ratios, collector types, `Spliterator` characteristics, and target JDK.

## 10. Comprehensive example: choosing the right collector for event reporting

Suppose events have category codes like `"INFO"`, `"WARN"`, and `"ERROR"`. Two different requirements lead to two different collection approaches.

### Requirement A: preserve event lines in order

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> events = Arrays.asList(
        "INFO: started",
        "WARN: slow",
        "INFO: resumed",
        "ERROR: failed"
);

List<String> visible = events.parallelStream()
        .filter(line -> line.startsWith("INFO"))
        .collect(Collectors.toList());

System.out.println(visible);
// [INFO: started, INFO: resumed]
```

Because we want to display in the list's encounter order, do **not** declare `UNORDERED` on a custom list collector. `parallelStream()` does not inherently lose encounter order for `collect(toList())`.

### Requirement B: count events per category only

```java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = events.parallelStream()
        .map(line -> line.substring(0, line.indexOf(':')))
        .collect(Collectors.groupingByConcurrent(
                category -> category,
                Collectors.counting()
        ));

System.out.println(counts.get("INFO"));  // 2
System.out.println(counts.get("WARN"));  // 1
System.out.println(counts.get("ERROR")); // 1
```

Here, event order does not affect the count per category. `groupingByConcurrent` fits aggregations that do not require encounter order; still, there is no guarantee it is faster for small datasets. The `map` step in the example assumes every line has a `:` character; on real data, handle malformed input before slicing strings.

If you need to **count by category while preserving event order within each category**, do not use `groupingByConcurrent(..., toList())` and assume the lists will retain encounter order. Use an order-preserving collector, or design explicit keys/sorting for display in a subsequent step.

## 11. Common mistakes

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Declaring `IDENTITY_FINISH` when `A` is `StringBuilder` and `R` is `String` | The type-converting finisher may be skipped | Remove `IDENTITY_FINISH`, keep the real finisher |
| Inferring `IDENTITY_FINISH` means an immutable result | State may still be mutable | Determine immutability via result type and finisher |
| Inferring `UNORDERED` means automatic shuffling | It is merely waiving an ordering guarantee | Do not rely on incidental order when not guaranteed |
| Declaring `UNORDERED` for a Collector that needs encounter order | Results may change order in parallel | Remove `UNORDERED` or revise business requirements |
| Declaring `CONCURRENT` for `ArrayList::add` | Same container is unsafely mutated by multiple threads | Choose the right collector or an appropriate concurrent container |
| Assuming `parallel()` guarantees shared-container accumulation | Java may create multiple containers and merge | Write a correct combiner in every case |
| Assuming `CONCURRENT` requires `UNORDERED` | They are two distinct commitments | Include `UNORDERED` only when business logic permits |
| Assuming `ConcurrentMap<K,List<V>>` makes Lists safe to mutate at any time | Map's thread-safety does not extend to mutable values | Manage List lifecycle and synchronization separately |
| Assuming downstream `counting()` must be concurrent for `groupingByConcurrent` to work | The outer collector can coordinate downstream updates | Use standard APIs per contract instead of mutating shared data |
| Calling `collect` and thinking an I/O Stream is closed | Terminal operations do not automatically call `close` | `try-with-resources` where the source is owned |
| Testing only sequential results and then declaring `CONCURRENT` | Bugs may appear only in parallel | Verify combiner, test in parallel, review thread-safety and contract |

## 12. Self-check questions

1. Which step does `IDENTITY_FINISH` describe? **Finisher**: `A` can be used directly as `R`, without needing a meaningful type conversion.
2. Does `IDENTITY_FINISH` guarantee a thread-safe container? **No**; this characteristic says nothing about concurrency.
3. Does `UNORDERED` mean Java must randomly scramble results? **No**; it simply does not commit to encounter order.
4. Does `CONCURRENT` mean the accumulator may be called on the same `A` from multiple threads? **Yes**, so updates to `A` must be thread-safe.
5. When a parallel Stream has an encounter order, can a `CONCURRENT` collector without `UNORDERED` freely accumulate into a single shared container? **No**, as doing so violates the ordering constraint; a strategy respecting encounter order is required.
6. Can an `UNORDERED` collector without `CONCURRENT` share one `ArrayList` for multiple threads to add freely? **No**, because there is no guarantee of safe concurrent updates.
7. Why doesn't `StringJoiner::toString` go with `IDENTITY_FINISH` when `R` is `String`? **Because** `A` and `R` are different types; the finisher must perform an actual conversion.
8. Does `groupingByConcurrent` guarantee value ordering within each group? **No**, it is an unordered collector.
9. If `Collector.of` takes only supplier, accumulator, and combiner, which finishing characteristic is declared? **IDENTITY_FINISH**.
10. Should you choose `CONCURRENT + UNORDERED` to get the **first** five records chronologically? **No**, because the "first" requirement demands preserving order and explicit selection rules.

**Practical principle:** Declaring Collector characteristics is a **correctness commitment**, not a trick to run faster. `IDENTITY_FINISH` is valid only when the accumulator is also the result; `UNORDERED` is valid only when business logic does not need encounter order; `CONCURRENT` is valid only when the accumulator can genuinely update the same container from multiple threads. Choose built-in Collectors when they satisfy requirements, write custom Collectors when needed, and optimize for parallelism only after proving contract compliance.
