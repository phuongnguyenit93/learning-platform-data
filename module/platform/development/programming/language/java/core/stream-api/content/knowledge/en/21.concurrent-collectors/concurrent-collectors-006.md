# Designing Safe Accumulation State for Concurrent Collectors

In the Java Stream API, `collect()` transforms elements passing through a pipeline into an aggregated result. When using `parallelStream()`, multiple threads can process elements simultaneously. If the collector (`Collector`) allows those threads to update **a single accumulation state** together, that state must be designed so that no data is lost, no structure is corrupted, and results remain correct even when execution order changes.

This lesson belongs to the **Concurrent Collection** chapter of `JAVA_STREAM_API`. The focus is on designing a safe shared accumulator, understanding the `Collector` contract, implementing a key-counting collector, and knowing when to use built-in collectors such as `groupingByConcurrent()` and `toConcurrentMap()`.

## 1. Where Does Accumulation State Live in a Collector?

At the type level, `Collector<T, A, R>` has three type parameters:

- `T`: the input element type from the stream.
- `A`: the mutable **intermediate accumulation state** type.
- `R`: the final result type returned after `collect()`.

Five components form the collector contract:

| Component | Role | What Must Be Guaranteed |
| --- | --- | --- |
| `supplier` | Creates a new state `A` | Each new state is independent and validly initialized |
| `accumulator` | Folds an element `T` into `A` | Updates accurately; safe when threads share `A` if `CONCURRENT` is declared |
| `combiner` | Merges two states `A` | No lost or duplicated data; merge operation is associative |
| `finisher` | Converts `A` into `R` | Result reflects all accumulated data |
| `characteristics` | Declares collector capabilities | Must describe actual behavior accurately, never declared merely for speed |

There are two parallel execution modes to distinguish:

1. **Multiple separate states:** tasks accumulate into independent containers, then `combiner` is called. A `HashMap` can be used inside each task as long as it is not shared across threads.
2. **Shared state:** multiple tasks call `accumulator` on a single container together. This case requires both the data structure and each update operation to be thread-safe.

Declaring `Collector.Characteristics.CONCURRENT` means the collector **permits** `accumulator` to be called concurrently on the same container. It does not mean every `collect()` call will share a container: the collection mechanism depends on collector characteristics, stream ordering, and the implementation.

### Three Easily Confused Characteristics

| Characteristic | Meaning | Example |
| --- | --- | --- |
| `CONCURRENT` | Accumulator supports multiple threads updating the same container | `ConcurrentHashMap` combined with `LongAdder` |
| `UNORDERED` | Result does not depend on element encounter order | Counting events by type |
| `IDENTITY_FINISH` | Result `R` is the container `A` itself, needing no conversion | Directly returning an accumulation map of the exact type |

For a stream with encounter order, a `CONCURRENT` collector can typically only perform shared accumulation if the collector is `UNORDERED` **or** the stream has been marked unordered (for example via `unordered()`). Adding `UNORDERED` must come from problem semantics: ordered string concatenation or picking the “first element” cannot arbitrarily discard order.

## 2. Invariants Required for a Shared State

A safe state must satisfy **all** of the following requirements simultaneously:

1. **The container structure supports concurrency.** Use `ConcurrentHashMap` instead of `HashMap` when multiple threads write to the same map.
2. **Inner values are also protected.** `ConcurrentHashMap<K, V>` only protects map operations; it does not make an `ArrayList` or arbitrary mutable `V` object thread-safe.
3. **Updating a logical unit is not split into check-then-write.** Avoid `get()` → compute value → `put()` because threads can read the same old value and overwrite each other. Choose `merge()`, `compute()`, `computeIfAbsent()`, or atomic counters as needed.
4. **Correctness does not depend on execution schedule.** The merge operation in `combiner` must be associative; for an `UNORDERED` collector, the result must also be independent of input permutations.
5. **Do not touch state outside the pipeline.** Classification functions should be pure (side-effect-free), source data must not be modified while the stream runs, and map keys must have stable `equals()/hashCode()`.
6. **Do not publish partial results.** If a consistent result is required, read the final snapshot only after `collect()` has finished. Reading multiple counters while threads are still updating does not produce an atomic snapshot of the whole map.

Choose the state representation based on the aggregation operation:

| Problem | Suitable State | Reason |
| --- | --- | --- |
| Count elements by key | `ConcurrentHashMap<K, LongAdder>` | `increment()` is safe; `LongAdder` often reduces contention when many threads increment together |
| Accumulate numbers by key | `ConcurrentHashMap<K, LongAdder>` or `merge()` | No lost additions under contention |
| Store unique values per key | Concurrent map + `ConcurrentHashMap.newKeySet()` | Both the map and value sets can be updated concurrently |
| Store lists per key | Built-in `groupingByConcurrent()`, or synchronize lists separately | `ArrayList.add()` is unsafe if called concurrently directly |
| Pick min/max by key | `ConcurrentMap.merge()` with min/max selection | Merge is associative and order-independent |

`LongAdder` is suited for high-write-frequency aggregations. `sum()` is **not** an atomic snapshot while concurrent updates are still occurring; in the collector below, we only take `sum()` for the final result after all updates have completed.

## 3. Building a Custom Collector to Count Events Concurrently by Type

Suppose a system needs to count `login`, `payment`, and `logout` events from a log list. Each event is processed independently; appearance order does not affect the result. We choose:

- `T = Event`: a single event.
- `A = ConcurrentHashMap<String, LongAdder>`: a map holding concurrently updatable counters.
- `R = Map<String, Long>`: a read-only summary of the results.

Complete example, running on **JDK 17+**:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;

public class ConcurrentCollectorExample {

    record Event(String type) {}

    static Collector<Event, ?, Map<String, Long>> countingByType() {
        return Collector
            .<Event, ConcurrentHashMap<String, LongAdder>, Map<String, Long>>of(
                ConcurrentHashMap::new,

                // accumulator: permitted to be called concurrently on the same map
                (counts, event) -> {
                    String key = Objects.requireNonNull(event.type(), "event.type");
                    counts.computeIfAbsent(key, ignored -> new LongAdder())
                          .increment();
                },

                // combiner: still required to merge independent containers
                (left, right) -> {
                    right.forEach((key, counter) ->
                        left.computeIfAbsent(key, ignored -> new LongAdder())
                            .add(counter.sum())
                    );
                    return left;
                },

                // finisher: creates the result snapshot after collection completes
                counts -> {
                    Map<String, Long> snapshot = new HashMap<>();
                    counts.forEach(
                        (key, counter) -> snapshot.put(key, counter.sum())
                    );
                    return Map.copyOf(snapshot);
                },

                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
            );
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("login"),
            new Event("payment"),
            new Event("payment"),
            new Event("logout"),
            new Event("login"),
            new Event("payment")
        );

        Map<String, Long> result =
            events.parallelStream().collect(countingByType());

        Map<String, Long> expected =
            Map.of("login", 2L, "payment", 3L, "logout", 1L);

        if (!result.equals(expected)) {
            throw new AssertionError("Wrong counts: " + result);
        }

        System.out.println(result); // Key display order is not fixed
    }
}
```

### Why Is Every Step Safe?

**`supplier`:** `ConcurrentHashMap::new` creates the initial container. When the stream implementation chooses to use multiple containers, each supplier call still creates an independent map.

**`accumulator`:** `computeIfAbsent()` safely initializes the counter for a key when multiple threads see a new key simultaneously. Afterward, `LongAdder.increment()` performs a safe increment. The concurrent map protects key structure; `LongAdder` protects the mutable inner value.

**`combiner`:** for each key in the right map, we add its sum to the corresponding counter on the left. `right` is unmodified; `left` is returned. The invariant to preserve is:

```text
count(merge(left, right), key) = count(left, key) + count(right, key)
```

Addition is associative and commutative, so how tasks are split does not alter the counts. Even though a shared-map collection path rarely needs the combiner, **you must not omit it or write a dummy combiner**: the collector contract still requires it to work properly.

**`finisher`:** after the terminal operation finishes, converts `LongAdder` instances into `Long` and returns `Map.copyOf()`. Callers cannot mutate the result via `put()` or `remove()`, and cannot access the intermediate accumulation map.

**`characteristics`:** `CONCURRENT` is valid because both the container and update operations support concurrency; `UNORDERED` is valid because counts do not depend on order. We do **not** declare `IDENTITY_FINISH` because `A` and `R` have different types, and the finisher must build a snapshot.

> Note: `ConcurrentHashMap` does not allow `null` keys or values. In the example, `Objects.requireNonNull()` proactively reports an error if an event has no type. When using mutable objects as keys, strictly avoid changing fields participating in `equals()`/`hashCode()` after inserting the key into the map.

## 4. When Should Built-In Collectors Be Used?

Before writing a custom collector, check whether the library already provides an equivalent aggregation. For counting by type, the two approaches below are much more concise:

```java
// Option 1: Group concurrently then count each group
Map<String, Long> counts1 = events.parallelStream()
    .collect(java.util.stream.Collectors.groupingByConcurrent(
        Event::type,
        java.util.stream.Collectors.counting()
    ));

// Option 2: Map each event directly to 1 and sum on duplicate keys
Map<String, Long> counts2 = events.parallelStream()
    .collect(java.util.stream.Collectors.toConcurrentMap(
        Event::type,
        event -> 1L,
        Long::sum
    ));
```

Both produce the same counts in the example. `groupingByConcurrent()` fits when grouping is needed and downstream collectors can be swapped, such as `counting()`, `mapping()`, or `summarizingLong()`. `toConcurrentMap()` fits when each element yields a key/value pair and there is a clear merge function.

The merge function `Long::sum` is associative and commutative. Conversely, a merge like “keep the string seen first” can yield different results when threads run on different schedules; it should not be used if preserving order is required.

**Distinguish collector safety from result safety.** Default `groupingByConcurrent(classifier)` can create `ConcurrentMap<K, List<T>>`. The collector safely manages the grouping process, yet the `List<T>` values inside the map are not guaranteed to be thread-safe for concurrent mutations **after** `collect()` returns.

### Choosing `groupingBy()` or `groupingByConcurrent()`

`groupingBy()` can run in a parallel stream by using separate maps and combining them, returning a `Map` by default. `groupingByConcurrent()` is a concurrent collector, does not guarantee element order within each group, and returns a `ConcurrentMap`. Therefore:

- Choose `groupingBy()` if you need to preserve encounter order when placing elements into each group's list.
- Consider `groupingByConcurrent()` if order can be ignored and groups are large enough to benefit from concurrent accumulation.
- Choose a custom collector when you need state, accumulation logic, or a result type that built-in collectors cannot express cleanly.

You cannot conclude the concurrent version is always faster solely from the API name. Small element counts, too few keys causing heavy contention, or task coordination overhead can make sequential `stream()` run faster.

## 5. Common Mistakes

### Mistake 1: Sharing a HashMap Inside a Parallel forEach

```java
Map<String, Long> counts = new HashMap<>();

// WRONG: multiple threads concurrently read/write an unsynchronized HashMap
events.parallelStream().forEach(event ->
    counts.merge(event.type(), 1L, Long::sum)
);
```

`HashMap.merge()` has no concurrency safety contract. Results may lose counts or corrupt map structure. Fix with `collect(Collectors.toConcurrentMap(...))` or a safe collector as in section 3.

### Mistake 2: Concurrent Map, Non-Concurrent Values

```java
var groups =
    new ConcurrentHashMap<String, java.util.List<Event>>();

// WRONG: multiple threads can call ArrayList.add() on the same list
events.parallelStream().forEach(event ->
    groups.computeIfAbsent(event.type(),
                           ignored -> new java.util.ArrayList<>())
          .add(event)
);
```

`computeIfAbsent()` only guarantees safe creation/lookup of the map value. It does not synchronize subsequent `add()` calls. You can use `groupingByConcurrent(Event::type)` for standard grouping tasks, or design a value container with appropriate synchronization.

### Mistake 3: Read-Then-Write Instead of Atomic Updates

```java
// WRONG if multiple threads operate on counts concurrently
Long oldValue = counts.get(key);
counts.put(key, oldValue == null ? 1L : oldValue + 1L);
```

Two threads may both observe an old value of `5` and both write `6` instead of `7`. With `ConcurrentMap<String, Long>`, use `counts.merge(key, 1L, Long::sum)`; with `ConcurrentHashMap<String, LongAdder>`, use `computeIfAbsent(...).increment()`.

### Mistake 4: Declaring CONCURRENT for an Unsafe Accumulator

`Collector.Characteristics.CONCURRENT` is a promise to the Stream engine, not a locking mechanism or a tool that automatically makes code thread-safe. If the accumulator modifies a shared `ArrayList`, `HashMap`, or plain `long` field without protection, adding this characteristic allows the collector to fail under parallel streams.

### Mistake 5: Confusing a Final Snapshot with Live Queries

`LongAdder.sum()` is suitable for obtaining the total after the pipeline finishes. If a dashboard needs a consistent snapshot at any point **while** multiple threads are still writing, simply reading `LongAdder` instances one by one is not enough. That problem requires a dedicated snapshot or synchronization protocol.

### Mistake 6: Broken Combiner Aggregation

If `combiner` merely returns the left map without merging the right map, results can be lost in multi-container execution mode. If the same counter is merged twice, results are doubled. Collector correctness must hold in both cases: sequential accumulation and multi-container accumulation followed by merging.

## 6. Verifying Correctness and Measuring Performance

A meaningful way to test is comparing against a reliable sequential result, repeating multiple times to increase the chance of hitting different schedules, and using a sufficiently large dataset:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

// Insert into main of ConcurrentCollectorExample to test with large load:
List<Event> many = IntStream.range(0, 100_000)
    .mapToObj(i -> new Event(i % 4 == 0 ? "payment" : "login"))
    .toList();

Map<String, Long> reference = many.stream()
    .collect(Collectors.groupingBy(Event::type, Collectors.counting()));

for (int attempt = 0; attempt < 100; attempt++) {
    Map<String, Long> actual =
        many.parallelStream().collect(countingByType());

    if (!actual.equals(reference)) {
        throw new AssertionError(
            "Mismatch at attempt " + attempt + ": " + actual
        );
    }
}
```

Also test empty streams, single-key (high contention), very many keys, `null` keys, and skewed data cases. Passing tests alone does not prove a collector is safe; combine them with verifying the invariants and contract in section 2.

When measuring performance, compare `stream()` against `parallelStream()` on **the same data size**, producing the same result, after JVM warm-up and across multiple runs. For decisive measurements, use JMH to control warm-up, forks, and result consumption. Do not perform I/O or blocking operations inside the accumulator of a CPU-bound parallel stream.

## 7. Practice Exercise

Suppose each `Event` also has a `userId`. Design a collector that returns the count of **distinct** users by `type`:

1. Choose state `ConcurrentHashMap<String, Set<String>>`, where each key's set is created with `ConcurrentHashMap.newKeySet()`.
2. Use `computeIfAbsent()` to create the set and `add()` to accumulate `userId` concurrently.
3. Write `combiner` by merging sets per key; in `finisher`, convert each set to its size and return an immutable result map.
4. Explain to yourself why the collector can declare `CONCURRENT` and `UNORDERED` but must not declare `IDENTITY_FINISH`.

Test with two threads concurrently sending multiple events for the same `userId`: the result per type must still count that user exactly **once**, regardless of occurrence count.

## 8. Remember

To design a correct concurrent collector, you must prove **both the container and its mutable inner values** can be updated safely, the merge operation satisfies the collector contract, and the declared characteristics match the semantics of the aggregation. Thread safety starts with choosing state `A` and its operations; `CONCURRENT` merely tells Stream that the collector has met that requirement.

For common tasks, prefer `groupingByConcurrent()` or `toConcurrentMap()`. Only implement your own when you need control over the accumulator, combiner, or finisher, and always compare sequential and parallel results before evaluating performance.
