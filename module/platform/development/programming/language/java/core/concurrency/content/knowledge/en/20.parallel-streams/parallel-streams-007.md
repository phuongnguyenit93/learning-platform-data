# Concurrent Collectors vs. Sequential Collectors in Java Parallel Streams

## Objectives and Scope

In the Java Stream API, `parallelStream()` determines the capability for parallel processing, while `Collector` defines **how to transform multiple elements into a single result**. These two concepts are independent: a non-concurrent collector can still be validly used in a parallel stream.

After this lesson, you will be able to:

1. Distinguish between a **non-concurrent collector** and a **concurrent collector** when running parallel reduction.
2. Explain the three characteristics `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH`, along with the conditions that allow multiple workers to write into a single result container.
3. Choose between `groupingBy` and `groupingByConcurrent`, `toMap` and `toConcurrentMap`; understand the impact on encounter order, thread safety, and contention.
4. Design custom collectors with the proper contract, verify output, and avoid overusing parallelization.
5. Evaluate performance using data and proper measurements rather than relying on API names.

The content belongs entirely to **Java SE concurrency, Stream, and Collector**, and runs on Java 17 and above.

## 1. Parallel Stream and Concurrent Collector Are Two Different Decisions

Example:

~~~java
// Illustration: requires importing java.util.List and java.util.stream.Collectors.
List<String> words = List.of("ant", "ape", "bee");

List<String> uppercase = words.parallelStream()
        .map(String::toUpperCase)
        .collect(Collectors.toList());
~~~

`parallelStream()` enables processing data partitions in parallel. `Collectors.toList()` is a **non-concurrent** collector, yet the call is still valid. With an input list that has an encounter order, the result has the order `[ANT, APE, BEE]`, even though `map` may execute on different workers.

**Non-concurrent** does not mean "runs only sequentially." It means the collector's accumulator **does not guarantee** safety when multiple threads write to **a single** container simultaneously. The framework can create independent accumulation containers so that workers process separately and then use the combiner to merge the results.

~~~text
Parallel source
     |
     +--> Worker A --> Accumulator A (private container A)
     |                                     \
     +--> Worker B --> Accumulator B --------> combiner --> result
     |                                     /
     +--> Worker C --> Accumulator C ------/
~~~

This is a conceptual model; the number of workers, number of containers, and how splitting/merging are done depend on the implementation. Because containers are not shared for concurrent writes, non-concurrent collectors can use `ArrayList`/`HashMap` internally. The fact that an internal collector uses a non-thread-safe structure **does not make** `parallelStream().collect(Collectors.groupingBy(...))` automatically suffer from a data race.

On the other hand, a sequential stream can still use a concurrent collector. In that case, there are not multiple workers accumulating concurrently, so the concurrent capability provides no specific benefit.

## 2. Collector Contract: supplier, accumulator, combiner, finisher

A `Collector<T,A,R>` describes how to accumulate inputs of type `T` into an intermediate container `A` and then produce a result `R`:

| Component | Role |
| --- | --- |
| `supplier()` | Creates a new accumulation container. |
| `accumulator()` | Incorporates an element `T` into container `A`. |
| `combiner()` | Merges two containers `A` in a way that preserves reduction semantics. |
| `finisher()` | Transforms container `A` into result `R`. |
| `characteristics()` | Declares guarantees so the runtime can optimize the collection operation. |

A collector must satisfy rules such as compatibility between accumulator and combiner, associativity of the merge operation, and independence from how the data is split. For a sum operation: the result must be the same whether grouped as `(a+b)+c` or `a+(b+c)`. If the merge function has external side effects or depends on thread scheduling, parallel results can easily be wrong.

### Three Characteristics to Distinguish

- **`CONCURRENT`:** the accumulator can be called **concurrently with the same result container** and still remain correct. This requires the container and update operations to genuinely support concurrency.
- **`UNORDERED`:** the collector does not guarantee preserving the encounter order of elements. It **does not mean** the collector is automatically thread-safe.
- **`IDENTITY_FINISH`:** the finisher is the identity function; the accumulation container representation can be used directly as the result. It must not be declared when the finisher transforms the type or structure.

For example, `Collectors.toSet()` may be unordered, yet **not concurrent**. `Collectors.groupingByConcurrent(...)` is both concurrent **and** unordered. Meanwhile, `Collectors.toList()` is not concurrent and generally must respect encounter order when collecting an ordered stream.

**Conditions for a stream to use concurrent reduction:**

1. The stream must be **parallel**;
2. The collector must have the **`CONCURRENT`** characteristic;
3. **Either** the stream is unordered, **or** the collector has `UNORDERED`.

When these conditions hold, the implementation **may** allow multiple workers to accumulate into **the same** container, reducing the need to create/merge multiple separate containers. The API does not require the implementation to always perform this optimization. If the collector does not have `CONCURRENT`, adding `stream.unordered()` **does not** make the accumulator thread-safe.

~~~text
Parallel source
    |           |           |
  worker A    worker B    worker C
    |           |           |
    +-----------+-----------+
                |
         Shared container
         concurrent updates
                |
              result
~~~

Concurrent reduction helps reduce **combiner** overhead, but it can increase contention on shared updates; therefore, **concurrent is not guaranteed to be faster**.

## 3. Encounter Order: Does Input Order Matter?

**Encounter order** is the order in which elements are encountered from an ordered source, such as `List.of("ant", "ape", "bee")`. Do not confuse the order in which workers execute with the result order guaranteed by the API.

With ordered data, `groupingBy(key)` uses a non-concurrent collector and preserves ordered collection semantics within each group's list. Conversely, `groupingByConcurrent(key)` **does not guarantee** that the list under a key maintains encounter order. It may contain the same elements, but they may appear in a different sequence.

- If the result is used for **frequency statistics or order-independent grouping**, an unordered collector is usually suitable.
- If elements within a group must follow **event order**, you must choose a collector that preserves encounter order or explicitly sort by timestamp/sequence after grouping.
- With `.unordered()`, you declare that encounter order constraints can be relaxed at appropriate steps; the runtime has the right to optimize, though that does not mean every result will be randomly shuffled.
- `ConcurrentMap` does not guarantee key iteration order. Do not rely on the printed order of `ConcurrentHashMap` as a data contract.

Only replace `groupingBy` with `groupingByConcurrent` after confirming that losing order **does not alter business requirements**.

## 4. Java 17+ Example: groupingBy and groupingByConcurrent

Create the file `GroupingCollectorsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class GroupingCollectorsDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "ant", "ape", "bear", "bee", "cat", "cow", "dog", "duck");

        Map<Character, List<String>> grouped = words.parallelStream()
                .collect(Collectors.groupingBy(s -> s.charAt(0)));

        ConcurrentMap<Character, List<String>> groupedConcurrent =
                words.parallelStream()
                     .collect(Collectors.groupingByConcurrent(s -> s.charAt(0)));

        System.out.println("groupingBy a: " + grouped.get('a'));

        List<String> a = new ArrayList<>(groupedConcurrent.get('a'));
        Collections.sort(a);
        System.out.println("groupingByConcurrent a sorted: " + a);

        boolean sameMembers = grouped.keySet().equals(groupedConcurrent.keySet())
                && grouped.keySet().stream().allMatch(key -> {
                    List<String> left = new ArrayList<>(grouped.get(key));
                    List<String> right = new ArrayList<>(groupedConcurrent.get(key));
                    Collections.sort(left);
                    Collections.sort(right);
                    return left.equals(right);
                });
        System.out.println("Same members: " + sameMembers);

        ConcurrentMap<Character, Long> counts = words.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        s -> s.charAt(0), Collectors.counting()));
        System.out.println("Counts: " + new TreeMap<>(counts));
    }
}
~~~

Run:

~~~bash
javac --release 17 GroupingCollectorsDemo.java
java GroupingCollectorsDemo
~~~

Exact output:

~~~text
groupingBy a: [ant, ape]
groupingByConcurrent a sorted: [ant, ape]
Same members: true
Counts: {a=2, b=2, c=2, d=2}
~~~

Analysis:

1. `grouped` is a `Map<Character,List<String>>` created by a **non-concurrent** collector. The stream processes in parallel, but does not use a shared `HashMap` arbitrarily modified by multiple threads.
2. `groupedConcurrent` is a `ConcurrentMap<Character,List<String>>`. The collector has concurrent and unordered characteristics, so the element order in the list for group `a` **is not part of the contract**.
3. Creating a copy `ArrayList` and calling `sort` is a way to stabilize the order for **display/comparison**; it does not mean the collector preserved the order.
4. `sameMembers` checks that both sides have the same keys and the same members per key **after normalizing order**.
5. `Collectors.counting()` is a downstream collector to aggregate the element count per group; `TreeMap` only normalizes key order when printing.

### Common Misconception About Downstream Collectors

`groupingByConcurrent(classifier, Collectors.counting())` is **valid**, even though `counting()` itself does not advertise `CONCURRENT`. The outer collector must safely coordinate downstream accumulation for each key. However, this may require per-key synchronization or coordination and can reduce benefits if millions of elements hit a few "hot" keys.

Meanwhile, the `groupingByConcurrent(classifier)` form returns `ConcurrentMap<K,List<T>>` but **does not guarantee that the resulting lists are thread-safe for external code to continue calling `add()` from multiple threads**. The safety of the collection process managed by the collector is not equivalent to thread safety for all operations on the objects after collection finishes.

## 5. Comparing Commonly Used Collectors

| Collector | Has `CONCURRENT`? | Ordering | Purpose |
| --- | --- | --- | --- |
| `toList()` | No | Respects encounter order for ordered streams | Need a list in source order |
| `toSet()` | No | Does not guarantee encounter order | Deduplicate elements |
| `groupingBy(key)` | No | Preserves encounter order semantics within groups for ordered streams | Group by key, uses combiner |
| `groupingByConcurrent(key)` | Yes, unordered | Does not guarantee element order within groups | Parallel grouping when order is not needed |
| `toMap(key, value, merge)` | No | Does not guarantee Map iteration order | Merge values by key |
| `toConcurrentMap(key, value, merge)` | Yes, unordered | Does not guarantee key/merge order by encounter order | Collect into a ConcurrentMap |
| `counting()` | No | Count value is independent of order | Count elements or use as downstream |

**Distinction from the returned collection type:** a `ConcurrentMap` is a data structure that supports concurrent updates, whereas `Collector.CONCURRENT` describes **the accumulator contract during the reduce phase**. Looking only at the return type is not enough to infer the collection strategy, and a thread-safe map does not guarantee that the value objects inside the map are thread-safe.

### Duplicate Keys with `toMap`/`toConcurrentMap`

When the mapper produces duplicate keys, the `toConcurrentMap(keyMapper,valueMapper)` overload without a merge function will throw an exception due to duplicate keys. You can use the three-argument overload:

~~~java
// Illustration: values is a Stream or Collection of Item with a category() method.
ConcurrentMap<String, Integer> frequencies = values.parallelStream()
        .collect(Collectors.toConcurrentMap(
                item -> item.category(),
                item -> 1,
                Integer::sum));
~~~

The merge function `Integer::sum` is suitable for counting frequencies because it is associative and order-insensitive.

Conversely, the merge function `(oldValue, newValue) -> newValue` **does not** guarantee selecting the *last element by encounter order* in a concurrent unordered collector. If the goal is "the record with the latest timestamp," use a comparator on the timestamp with a clear tie-breaking rule. Non-associative merge operations such as subtraction also do not have stable parallel semantics when regrouping.

## 6. Java 17+ Example: Writing a Custom Concurrent Collector with the Right Contract

A simple example uses `LongAdder`, an adder that supports concurrent updates from multiple threads, to collect a sum. Create the file `ConcurrentCollectorDemo.java`:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ConcurrentCollectorDemo {
    public static void main(String[] args) {
        Collector<Integer, ?, Long> concurrentSum = Collector.of(
                LongAdder::new,
                (adder, value) -> adder.add(value),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED);

        long sum = IntStream.rangeClosed(1, 1000)
                .boxed()
                .parallel()
                .collect(concurrentSum);
        System.out.println("Sum = " + sum);

        ConcurrentMap<String, Integer> frequency =
                IntStream.rangeClosed(1, 10)
                        .parallel()
                        .boxed()
                        .collect(Collectors.toConcurrentMap(
                                n -> n % 2 == 0 ? "even" : "odd",
                                n -> 1,
                                Integer::sum));
        System.out.println("Even count = " + frequency.get("even"));
        System.out.println("Odd count = " + frequency.get("odd"));
        System.out.println("Collector concurrent = " +
                concurrentSum.characteristics()
                        .contains(Collector.Characteristics.CONCURRENT));
    }
}
~~~

Run:

~~~bash
javac --release 17 ConcurrentCollectorDemo.java
java ConcurrentCollectorDemo
~~~

Output:

~~~text
Sum = 500500
Even count = 5
Odd count = 5
Collector concurrent = true
~~~

Why is this collector correct?

- `supplier` uses `LongAdder::new`: creates a container suitable for concurrent updates.
- `accumulator` uses `adder.add(value)`: multiple workers can safely add into the same container.
- `combiner` adds the sum of the right container into the left container. A concurrent collector still **needs** a valid combiner in its contract even though the runtime may choose to use a single container.
- `finisher` uses `LongAdder::sum` to return `Long`. `IDENTITY_FINISH` is not declared because `A` is `LongAdder`, while `R` is `Long`.
- Addition is an order-independent operation, so `UNORDERED` is appropriate. `LongAdder.sum()` is not an atomic snapshot if concurrent updates are still occurring; here the finisher runs after the collection phase has completed.
- `toConcurrentMap` uses `Integer::sum` to merge 10 elements into two keys: `even` and `odd`.

This example demonstrates **contract correctness**, not a claim that `LongAdder` is faster than a standard `IntStream.sum()`. For summing numbers, `mapToLong(...).sum()` is usually concise and easy to understand; use a custom collector only when you need a specific accumulation structure and contract.

## 7. Dangerous Pitfalls with Concurrent Collectors

### Pitfall 1: Advertising CONCURRENT While Using an Unsafe ArrayList

~~~java
// BROKEN SNIPPET (illustration only, do not use in applications):
Collector<String, List<String>, List<String>> broken = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.CONCURRENT,
        Collector.Characteristics.UNORDERED);
~~~

This broken snippet requires `java.util.ArrayList`, `java.util.List`, and `java.util.stream.Collector`; it is not a standalone program. `ArrayList.add()` is **not safe** when multiple threads update the same list. Falsely declaring `CONCURRENT` can cause lost elements, incorrect size, or corrupted state. A test that occasionally runs "correctly" does not prove the code is safe: execution interleaving changes across runs.

The fix depends on requirements: remove `CONCURRENT` to use the private-container + combiner model, or use a genuinely concurrent container and accumulator, such as `ConcurrentLinkedQueue` if order does not matter. Evaluate overhead and correctness before attaching optimization flags.

### Pitfall 2: Side Effects Outside the Collector

~~~java
// BROKEN SNIPPET: shared is an unsynchronized shared ArrayList.
words.parallelStream()
     .peek(shared::add)
     .collect(Collectors.toList());
~~~

This is illustrative code with undeclared `shared` and `words`. Even though the standard `toList()` handles its own work properly, `peek(shared::add)` still has a data race because it writes to a list **outside the collector**. Do not use side effects in `map`, `filter`, or `peek` to collect results; express the transformation and use an appropriate collector.

### Pitfall 3: Misunderstanding Ordering

`groupingByConcurrent` can produce lists with the right members but in a different order from the source. Do not use `list.get(0)` to infer "the first event" if ordering is required and not guaranteed by the collector. Instead, store a timestamp/sequence and select using a deterministic rule.

### Pitfall 4: Hot Key Contention

If 90% of the data belongs to a single key, multiple workers may concurrently update the data region for that key. Synchronization/contended-update overhead can easily outweigh the benefit of skipping the combiner. Try partitioning and then merging aggregates, or using a non-concurrent collector, after measuring on the real workload.

### Pitfall 5: Too Many Tiny Tasks

Parallel streams have overhead for splitting work, ForkJoin scheduling, object allocation, and merging results. If processing each element is too lightweight, a sequential stream can be faster. A concurrent collector also does not replace designing an appropriate task granularity.

## 8. When Can a Concurrent Collector Be More Useful?

| Workload Characteristic | Expected Impact |
| --- | --- |
| Many elements, many keys, even distribution | Updates have a chance to spread out; reduces merging separate maps. |
| Very few keys, concentrated frequency | High contention; concurrent may provide no benefit. |
| Stable ordering required within each group | An unordered collector may violate the requirement. |
| Downstream counting or simple reduce | Worth trying both options and measuring actual throughput. |
| Downstream builds large lists/sets | Allocation, memory, and per-key synchronization may dominate. |
| Very small dataset | Parallelism overhead is usually not worth it. |
| Hard-to-split source, uneven processing | Bottlenecks in the Spliterator/task partitioning remain even if you change the collector. |

A "concurrent" collector **allows** concurrent reduction; it does not guarantee **always using** a shared container, and even less does it guarantee being faster than a non-concurrent collector. With grouping, `groupingBy` can incur overhead from merging multiple maps; `groupingByConcurrent` can incur overhead from write contention on the map and certain keys. Results depend on the data and goals.

## 9. Reliable Benchmarking Methodology

To decide for a real application:

1. **Verify correctness first:** confirm that the input element count equals the total element count across groups, key counts, and summary values; if unordered, normalize order when comparing.
2. **Compare on the same workload:** test `stream().collect(groupingBy(...))`, `parallelStream().collect(groupingBy(...))`, and `parallelStream().collect(groupingByConcurrent(...))`. Do not compare two approaches that differ only in input order or data types.
3. **Test different distributions:** few hot keys vs. many even keys; small vs. large datasets; `counting` vs. collecting into a `List`.
4. **Use JMH** when micro-benchmark conclusions are needed: warm-up, multiple iterations, JVM forks; do not rely on a single `System.nanoTime()` run.
5. **Measure the right factors:** throughput, latency, CPU utilization, allocation, GC, contention, and combiner cost; CPU quota/cores/JDK details matter significantly.
6. **Check system-wide effects:** parallel streams typically use the common `ForkJoinPool`; a standalone benchmark may differ from an application running many concurrent tasks.
7. **Choose the simpler approach when fast enough:** correctness, contract ordering, and maintainability matter more than a tiny, unstable gain.

Practice exercise: generate 100,000 numbers from `0` to `99_999`, group by key `n % k` with `k = 2`, `100`, and `10_000`. Compare the correctness of `groupingBy` and `groupingByConcurrent`, then benchmark them. Observe the case with few hot keys and the case with many keys, and do not assume a concurrent collector is always optimal.

## 10. Collector Selection Checklist

- **Need to preserve order in a List?** Prefer a collector that respects encounter order or post-process using a real ordering criterion.
- **Need grouping without ordering?** Try `groupingByConcurrent` and benchmark against `groupingBy`.
- **Need per-key aggregation with duplicates?** Choose `toConcurrentMap` with an associative merge function that has clear semantics.
- **Writing a custom collector?** Check supplier/accumulator/combiner/finisher, independence from data splitting, and only declare `CONCURRENT` when the accumulator is truly safe on a shared container.
- **Using a non-concurrent downstream?** Do not assume the outer collector is wrong; instead, understand the synchronization/contended-key behavior of the overall collector.
- **Got a faster result?** Verify correctness, inputs, warm-up, key distribution, CPU, and GC before drawing conclusions.

Key takeaway: **a parallel stream can run in parallel with a non-concurrent collector thanks to private containers and a combiner. A concurrent collector only enables concurrent accumulation on the same container when thread-safety and ordering contracts allow it. The right choice depends on data semantics and real measurements.**

### Official Java References

- [Java 21 Stream package: parallelism, ordering, and concurrent reduction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)
- [Java 21 Collector API: Characteristics and contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html)
- [Java 21 Collectors API: groupingBy, groupingByConcurrent, toConcurrentMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [JMH: Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/)
