# Conditions for Applying Concurrent Collection with CONCURRENT and UNORDERED

When using the Java Stream API, calling `parallelStream()` or `parallel()` **does not mean** every element will be written concurrently into the same `List` or `Map`. How results are gathered depends on the **Collector's contract** and the **Stream's ordering requirements**. Specifically, the two characteristics `Collector.Characteristics.CONCURRENT` and `Collector.Characteristics.UNORDERED` determine when the execution engine **is permitted** to choose a strategy where multiple threads accumulate into a single container.

This lesson belongs to the **Concurrent Collection** chapter of the `JAVA_STREAM_API` module. We will analyze the exact conditions for concurrent reduction to occur, distinguish a concurrent collector from a parallel stream and concurrent data structures, use `toConcurrentMap`/`groupingByConcurrent`, build safe custom Collectors, and identify bugs involving shared state, lost ordering, and performance impacts. The examples build on lazy pipelines, `filter`, `map`, `reduce`, `collect`, `Spliterator`, and the limits of parallel execution.

The core APIs have been available since **Java 8**. The examples use `Arrays.asList` or `IntStream` to avoid Java 9+ dependencies.

## 1. From Regular Collect to Concurrent Reduction

A `Collector<T, A, R>` defines:

- `T`: the input element type;
- `A`: the intermediate accumulation type;
- `R`: the final result type.

The five components of a Collector:

| Component | Role |
| --- | --- |
| `supplier()` | Creates a new, initially empty accumulator `A` |
| `accumulator()` | Incorporates an element `T` into an accumulator `A` |
| `combiner()` | Merges two accumulators `A` when there are multiple branches |
| `finisher()` | Transforms `A` into `R` if needed |
| `characteristics()` | Allows the execution engine to rely on guarantees regarding concurrency, ordering, and finishing |

When processing in parallel, Java can use **multiple separate containers**:

```text
               Stream<T>
                   |
         split into multiple parts
            /             \
           v               v
     supplier()       supplier()
         A1               A2
          |                |
    accumulator      accumulator
          |                |
          +---- combiner --+
                   |
                finisher
                   |
                  R
```

This strategy **does not require** each container `A1` and `A2` to tolerate concurrent updates from multiple threads at the same time, as long as branches do not concurrently modify the same container and the combiner obeys the contract.

Another strategy is **shared accumulation into a single container**:

```text
                 Stream<T>
                     |
           multiple parallel tasks
            /       |       \
           v        v        v
      accumulator accumulator accumulator
            \       |       /
             \      v      /
                 shared A
                    |
                 finisher
                    |
                    R
```

When the same `A` receives concurrent accumulator calls, the collector itself must **actually be safe for concurrent updates**. Simply calling `parallel()` or using a `ConcurrentHashMap` as the result is not enough to infer that the entire pipeline is processed under this strategy.

## 2. Exact Meaning of CONCURRENT and UNORDERED

`Collector.Characteristics` has three flags:

| Characteristic | Guarantee | Does Not Mean |
| --- | --- | --- |
| `CONCURRENT` | The accumulator **can** be called concurrently from multiple threads with **the same object A** | Does not automatically make the Stream parallel; does not automatically add locks or synchronization |
| `UNORDERED` | The collection **does not guarantee preserving the encounter order** of input elements | Not a data shuffle operation; does not mean the accumulator is thread-safe |
| `IDENTITY_FINISH` | The accumulator `A` can be used directly as the result `R`, skipping the finisher conversion | Unrelated to concurrency or immutability |

The two characteristics under discussion are **two independent guarantees**.

**`CONCURRENT` answers:** “Is it safe by contract for multiple threads to call the accumulator on a single container?”

**`UNORDERED` answers:** “Does the result need to reflect encounter order?”

A collector can be `CONCURRENT` without being `UNORDERED` if it is genuinely capable of concurrent accumulation while still having ordering requirements. However, that **does not by itself allow** collecting into a single shared container from an ordered parallel stream, because ordering constraints still have to be preserved. Conversely, a collector with `UNORDERED` but not `CONCURRENT` allows dropping ordering requirements, **not** allowing multiple threads to freely modify the same `ArrayList`.

`IDENTITY_FINISH` is a separate topic: if the finisher must actually convert `A` into a different type `R`, such as `LongAdder` into `Long`, `IDENTITY_FINISH` must not be declared.

## 3. Conditions Permitting Concurrent Accumulation into a Single A

For the terminal operation `stream.collect(collector)`, the necessary condition for the execution engine to choose the **concurrent reduction with a shared container** strategy is:

1. The Stream is executing in **parallel**.
2. The Collector declares **`CONCURRENT`**.
3. **At least one** of the following is true:
   - The Stream has no encounter order requirement (`unordered`); **or**
   - The Collector declares **`UNORDERED`**.

Written as a logical expression:

```text
shared-container concurrent reduction is permitted when:

stream.isParallel()
    && collector has CONCURRENT
    && (!stream has encounter order || collector has UNORDERED)
```

Note that this is a **permitting condition**, not a guarantee about thread count, work splitting, number of supplier calls, or that the framework must actually choose the shared strategy on every run.

### Decision Table

| Stream | Collector Characteristics | Can Accumulate Concurrently into the Same A? | Explanation |
| --- | --- | --- | --- |
| Sequential | `CONCURRENT + UNORDERED` | Not needed | The pipeline does not execute parallel branches |
| Parallel, ordered | No `CONCURRENT` | **No** | No guarantee that a shared accumulator is safe |
| Parallel, ordered | Only `UNORDERED` | **No** | Dropping order does not create thread-safety |
| Parallel, ordered | Only `CONCURRENT` | **Not via the shared strategy** | The collector still requires preserving order |
| Parallel, ordered | `CONCURRENT + UNORDERED` | **Possible** | The collector allows both shared updates and dropping order requirements |
| Parallel, unordered | Only `CONCURRENT` | **Possible** | The source/pipeline does not require preserving order |
| Parallel, unordered | `CONCURRENT + UNORDERED` | **Possible** | Both conditions are satisfied |
| Parallel, any order | Only `IDENTITY_FINISH` | **No** | Identity finisher does not guarantee a safe accumulator |

If a Collector does **not** have `CONCURRENT`, it can still **be used with a parallel stream**. Java can create multiple independent accumulators and call `combiner` to merge the results. What is restricted is multiple concurrent tasks writing to **the exact same** container when the collector has not declared support for it.

## 4. Stream Encounter Order Differs from Collector UNORDERED

*Encounter order* is the logical order defined by the source and intermediate operations. `List.stream()` normally has an encounter order matching list positions. Some sources such as `HashSet` provide no stable encounter order guarantee.

A Collector's `UNORDERED` **differs from** the `BaseStream.unordered()` operation:

- `stream.unordered()` changes the ordering contract of the downstream pipeline.
- `collector.characteristics().contains(UNORDERED)` states that the collection itself does not need to preserve encounter order.

Example with an ordered list:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> input = Arrays.asList("A", "B", "A", "C");

List<String> result = input.parallelStream()
        .collect(Collectors.toList());

System.out.println(result); // [A, B, A, C]
```

`Collectors.toList()` is not a concurrent collector; it can still run with a parallel stream by accumulating and combining parts according to the contract. When the source has an encounter order, the `toList` result preserves the order of input elements.

Conversely:

```java
import java.util.Set;

Set<String> unique = input.parallelStream()
        .collect(Collectors.toSet());

System.out.println(unique.size());     // 3
System.out.println(unique.contains("A")); // true
```

`Collectors.toSet()` is an **unordered collector**, which **does not mean concurrent collector**. The result set guarantees no specific iteration order; lacking an ordering requirement does not automatically make the accumulator safe for multiple threads to modify together.

Nor should `unordered()` be treated as a random shuffle: it removes the encounter order constraint without forcing elements to be shuffled.

## 5. Inspect Characteristics Instead of Guessing

You can directly observe the characteristics declared by a Collector:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, Set<String>> toSet = Collectors.toSet();

System.out.println(
        toSet.characteristics().contains(
                Collector.Characteristics.UNORDERED
        )
); // true

System.out.println(
        toSet.characteristics().contains(
                Collector.Characteristics.CONCURRENT
        )
); // false

Collector<String, ?, Map<String, String>> toMap =
        Collectors.toMap(s -> s, s -> s);

System.out.println(
        toMap.characteristics().contains(
                Collector.Characteristics.CONCURRENT
        )
); // false
```

`characteristics()` reports the **declared contract**; it does not verify whether custom code is actually thread-safe. If a Collector author marks flags incorrectly, the framework may rely on that declaration to execute in an unsafe manner.

Do not rely solely on data type names. A Collector returning a `ConcurrentMap` is a clue worth inspecting, but to know whether it is a concurrent collector you must still read the **Collector contract** and check its own characteristics.

## 6. toConcurrentMap: A Suitable Case for Concurrent Accumulation

`Collectors.toConcurrentMap` creates a `ConcurrentMap<K,U>` and is a **concurrent, unordered collector**. When keys collide, an appropriate merge function must be specified.

Example counting events by code:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> events = Arrays.asList(
        "WARN", "INFO", "WARN", "ERROR", "INFO", "WARN"
);

ConcurrentMap<String, Long> counts = events.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Function.identity(),
                code -> 1L,
                Long::sum
        ));

System.out.println(counts.get("WARN"));  // 3
System.out.println(counts.get("INFO"));  // 2
System.out.println(counts.get("ERROR")); // 1
```

In the pipeline above:

1. The `List` source has an encounter order.
2. `parallelStream()` allows execution across multiple branches.
3. `toConcurrentMap` has both `CONCURRENT` and `UNORDERED`, so the framework **is permitted** to accumulate into a shared ConcurrentMap.
4. `Long::sum` merges values when the same key appears.
5. The result does not require a specific key iteration order.

This is an appropriate example because the result of **counting by code** does not depend on which code is processed first.

**Watch out for duplicate keys:** the overload taking only `keyMapper` and `valueMapper` will throw `IllegalStateException` upon encountering duplicate keys. Whether to sum, pick the max, overwrite by rule, or throw an error depends on business logic—you must choose the right merge function.

### Avoid Using “Keep First Value” for Unordered Data

```java
// NOT reliable if you need the "first-arriving" event by source order.
ConcurrentMap<String, Event> firstByKey = eventsStream
        .parallel()
        .collect(Collectors.toConcurrentMap(
                Event::key,
                Function.identity(),
                (a, b) -> a
        ));
```

This is a **sketch snippet**; `Event` and `eventsStream` represent application types and Streams. Because `toConcurrentMap` is an unordered collector, `a` in the merge function is not guaranteed to be the first element appearing in encounter order. If the business requires the latest record, use a comparator on `timestamp` with a stable secondary key to select it, rather than merge position.

## 7. groupingByConcurrent: Grouping Without Ordering Requirements

`Collectors.groupingByConcurrent` is a concurrent, unordered collector that groups elements using a classifier.

Counting words by their initial letter:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

List<String> words = Arrays.asList(
        "java", "junit", "spring", "sql", "stream"
);

ConcurrentMap<Character, Long> byInitial =
        words.parallelStream()
             .collect(Collectors.groupingByConcurrent(
                     word -> word.charAt(0),
                     Collectors.counting()
             ));

System.out.println(byInitial.get('j')); // 2
System.out.println(byInitial.get('s')); // 3
```

There is no need to preserve word order when the goal is counting, so the unordered characteristic fits well.

However, a commonly misunderstood point: `Collectors.counting()` (downstream) is not a concurrent collector. That **does not make `groupingByConcurrent` incorrect**. The outer collector is responsible for coordinating safe updates to downstream accumulators; you must not take downstream containers out afterward to let multiple threads mutate them without protection.

### Lists Within Each Group Guarantee No Ordering

```java
ConcurrentMap<Character, List<String>> grouped =
        words.parallelStream()
             .collect(Collectors.groupingByConcurrent(
                     word -> word.charAt(0)
             ));

System.out.println(grouped.get('j').size()); // 2
```

We know group `'j'` contains two elements `"java"` and `"junit"`, but **we must not assert the order of those two elements**. `groupingByConcurrent` is an unordered collector, even when the source is an ordered `List`.

Moreover, `ConcurrentMap<K,List<V>>` **does not make each `List<V>` itself automatically thread-safe** for continued mutation from threads after collect. Correctness during collection is the Collector implementation's responsibility; thread safety of subsequent operations is a separate concern.

If the UI or report needs per-group ordering, use an appropriate collector to preserve order, or sort each list by an **explicit key** after collection.

## 8. Building a Safe Custom Concurrent Collector Using LongAdder

`LongAdder` supports multiple threads concurrently updating a count/sum. It is a good choice for illustrating a Collector with both `CONCURRENT` and `UNORDERED`.

```java
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;
import java.util.stream.IntStream;

Collector<Integer, LongAdder, Long> sumCollector =
        Collector.of(
                LongAdder::new,
                (adder, n) -> adder.add(n),
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
```

Contract analysis:

- `supplier` creates a new `LongAdder` container, initially summing to 0.
- `accumulator` calls `LongAdder.add`; multiple threads can update the **same** object.
- `combiner` merges the sum from `right` into `left`; still must be valid for execution paths that do not use a shared container.
- `finisher` returns a `long` from `LongAdder.sum`, boxed into `Long`.
- `CONCURRENT` is valid because the accumulator accepts concurrent updates.
- `UNORDERED` is valid because summing integers here does not require element encounter order.
- **No** `IDENTITY_FINISH` because `A = LongAdder`, `R = Long`.

`LongAdder.sum()` is not a linearized snapshot while threads are **still writing**. In a valid collect operation, the finisher is applied after the accumulation phase completes, so this usage is appropriate.

For very large integer sums, even `long` can overflow. If the business requires overflow detection, exact precision, or special ordering, a different arithmetic design is needed. And if you only need an `int` or `long` sum, `mapToLong(...).sum()` is usually simpler than a custom Collector.

### Why Must the Combiner Still Be Correct?

There are situations where the pipeline does not use the shared-container strategy. A Collector must still satisfy the identity/associativity contracts of `combiner`, regardless of whether a specific run invokes it.

Wrong:

```java
// WRONG: containers must be merged, cannot discard data from the right branch.
(left, right) -> left
```

The snippet above merely illustrates a `combiner` lambda. If used in a Collector with multiple intermediate containers, results from the right branch will be lost.

Right with `LongAdder`:

```java
(left, right) -> {
    left.add(right.sum());
    return left;
}
```

The merge operation must be compatible with how the accumulator added elements to each container, not merely “look reasonable” when run sequentially.

## 9. Anti-pattern: Attaching CONCURRENT to ArrayList

`ArrayList` does not natively support multiple threads concurrently calling `add` on a single instance. Therefore, do not create the Collector below and declare `CONCURRENT`:

```java
import java.util.ArrayList;
import java.util.stream.Collector;

// WRONG EXAMPLE: DO NOT use in applications.
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

If Java selects the shared accumulation strategy, `ArrayList.add` can run concurrently from multiple tasks, leading to lost elements, corrupted state, or hard-to-reproduce errors.

Do not treat a single test run with the right output as proof of thread safety. Race conditions may only surface under heavy load or different scheduling.

The right approach when you only need a List:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> safe = IntStream.range(0, 1000)
        .boxed()
        .parallel()
        .collect(Collectors.toList());

System.out.println(safe.size()); // 1000
```

`toList` is a non-concurrent Collector; the framework can use multiple independent containers and merge them safely under its contract. The result does not require the caller to share an `ArrayList` being mutated by multiple threads.

If you want to write your own list Collector, **do not declare `CONCURRENT`** unless the accumulator and the entire container genuinely support shared updates. Merely wrapping a Map with `ConcurrentHashMap` while the inner values are still `ArrayList` does not prove updates to those lists are safe either.

## 10. UNORDERED Cannot Fix a Broken Merge Function

The two characteristics only grant certain optimization permissions. They **do not cure** a merge function that lacks associativity or relies on side effects.

Semantically wrong example using subtraction as merge:

```java
// WRONG if expecting an invariant result when branch splitting changes.
Collectors.toConcurrentMap(
        item -> item.key(),
        item -> item.value(),
        (a, b) -> a - b
)
```

This is a sketch with `item` of an application-defined type. Subtraction is not associative:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Parallel collect may combine partial results in different ways. For operations such as counting or summing integers within a non-overflowing range, `Long::sum` is an appropriate merge function. If you need to choose a preferred object, use a stable rule like `BinaryOperator.maxBy(comparator)`, with tie-breaking clearly defined.

### Associativity Differs from Commutativity

`(a, b) -> a` (keep left operand) and `(a, b) -> b` (keep right operand) can be considered associative in grouping, but **not commutative**: changing input order changes the result. With a concurrent, unordered collector, they should not be used to implement “first/last arriving record by encounter order”.

If an operation does not care about order, verify that from business requirements rather than inferring it merely because the data is stored in a Map.

## 11. Collector CONCURRENT Differs from ConcurrentMap and Spliterator.CONCURRENT

The word “concurrent” appears at three different layers:

| Layer | Indicator | Meaning |
| --- | --- | --- |
| **Source** | `Spliterator.CONCURRENT` | The source is designed to tolerate a form of concurrent structural modification per contract |
| **Collector** | `Collector.Characteristics.CONCURRENT` | The accumulator can be called concurrently on the same accumulator container |
| **Result structure** | `ConcurrentHashMap`, `ConcurrentMap` | Certain Map operations carry concurrency guarantees per the class/map contract |

They are **not interchangeable**. A source with `Spliterator.CONCURRENT` does not require the collector to be concurrent. A `ConcurrentMap` can be created from sequential code. A custom Collector declaring `CONCURRENT` will not automatically make input elements or objects inside the Map thread-safe.

Similarly, the `Collector.Characteristics.IDENTITY_FINISH` characteristic only states that `A` can be used directly as `R`. It does not prove the accumulator is thread-safe.

### An Unordered Stream Is Not Necessarily a Concurrent Source

`stream.unordered()` can drop the encounter order constraint, but it does not turn an `ArrayList` being mutated by multiple threads into a safe source. If `map`, `filter`, or classifier operations modify an external structure without synchronization, the risk still exists even if the collector at the end is concurrent.

## 12. Strategy for Using parallel + unordered Intentionally

If **the result genuinely does not need ordering**, we can express that in the pipeline or Collector.

Word counting example:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "a", "b", "a", "c", "b"
).parallelStream()
 .unordered()
 .collect(Collectors.toConcurrentMap(
         Function.identity(),
         x -> 1L,
         Long::sum
 ));

System.out.println(counts.get("a")); // 2
```

`unordered()` in this example is **not required** to permit the shared strategy, because `toConcurrentMap` already has `UNORDERED`. Adding it simply clarifies that the downstream pipeline does not demand encounter order. Do not add `unordered()` to every pipeline out of habit: it can change the semantics of `findFirst`, `limit`, `skip`, or operations that pick the “first” element.

If a collector only declares `CONCURRENT` (without `UNORDERED`), having the pipeline drop encounter order can enable the shared accumulation path. However, that is only valid if **the business logic truly allows reordering**, including at intermediate operations before collect.

### When Ordered Results Are Needed

If preserving the order of a `List` is required:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> ordered = Arrays.asList("C", "A", "B")
        .parallelStream()
        .collect(Collectors.toList());

System.out.println(ordered); // [C, A, B]
```

This is not an example of concurrent accumulation into a shared List, yet it **is still collection from a parallel Stream**. There is no need to sacrifice order if business requirements depend on it.

If you need a chronologically sorted list, describe the sort key and stability explicitly instead of just picking a concurrent collector and assuming elements will arrive in chronological order.

## 13. Complex Downstreams and Null Cases

### Grouping with a Non-Concurrent Downstream

`groupingByConcurrent(classifier, downstream)` supports downstream collectors such as `counting`, `mapping`, or `toList`. The outer collector is responsible for ensuring contract-compliant accumulation even when the downstream does not declare `CONCURRENT`. Do not use that to conclude that **every downstream container is inherently safe** when taken out and used outside the collection process.

When many elements share the same key, heavy contention can occur on the corresponding bucket; performance is strongly influenced by **key distribution**, not just CPU core count.

### Null Keys Are Not Solved by CONCURRENT

`groupingByConcurrent` does not accept a classifier returning `null`. `ConcurrentHashMap` also disallows null keys. If the source has missing keys, design a policy to **filter, replace with a non-colliding sentinel key, or represent using `Optional`** before grouping.

`toConcurrentMap` should also not receive key/value mappers that can return null. In particular, null values are not a safe “default value” for a `ConcurrentMap`. Normalize input data or model missing states explicitly.

### Keep All Groups or Only Observed Groups?

`groupingByConcurrent` can only create groups from elements that the classifier actually observes. It **does not auto-generate groups that never appeared**. If a report must display every category (including zero counts), supplement the domain key list after collection or design the source/report to include all expected keys.

## 14. When Can a Concurrent Collector Be Slower?

`CONCURRENT + UNORDERED` **does not guarantee** a speedup. They open an execution option, while actual effectiveness depends on the specific workload.

| Factor | Typical Impact |
| --- | --- |
| Source with few elements | Splitting and coordination overhead can exceed processing work |
| Many elements sharing one key | Updates contend on the same bucket/container |
| Many independent keys | Updates distribute better, but large Maps consume memory |
| Cheap accumulator processing | Synchronization/atomic operations can dominate total time |
| CPU-heavy, pure accumulator | Parallel can help if the source is splittable |
| Sequential I/O source | Reading the source may become the bottleneck |
| Mandatory encounter order | Certain concurrent optimizations are disallowed |
| Downstream holding large `List`s | Data size and memory grow with element count |
| Sorting/deduplicating before collect | Stateful operations can introduce buffering and coordination |
| Floating-point arithmetic | How additions are grouped can alter low-order rounding error |

For example, counting a few dozen elements with `parallelStream().collect(toConcurrentMap(...))` can be **slower** than `stream().collect(toMap(...))`, because creating tasks and updating a concurrent map are not free.

Measure performance on representative data: element count, unique key count, collision rate, key string length, classifier cost, downstream type, JDK, and actual thread count. Do not use a single un-warmed run as a firm conclusion.

If the goal is merely an integer sum, `IntStream.sum()` or `LongStream.sum()` is usually simpler and requires no custom Collector.

## 15. Verifying Correctness in Parallel Execution

Looking at one run's output is not enough to conclude a collector is safe. You should verify at least:

1. **Supplier:** does it create an accumulator with the right initial state, independent across multiple invocations?
2. **Accumulator:** is it safe if multiple threads operate on a single `A` concurrently? If not, do not declare `CONCURRENT`.
3. **Combiner:** does it merge all data from both branches, obeying identity and associativity?
4. **Finisher:** does it need to convert type `A → R`? If so, do not use `IDENTITY_FINISH`.
5. **Ordering:** do results require “first”, “last”, or stability by encounter order?
6. **Pipeline before collect:** are the classifier, `map`, and `filter` stateless, non-interfering, and free of writes to shared variables?
7. **Edge cases:** empty source, single element, many elements with the same key, null keys, oversized values.
8. **Repeated execution:** do statistical results remain invariant across multiple sequential and parallel runs?
9. **After collect:** will other consumers concurrently mutate mutable objects inside the Map?
10. **Resources:** has the owner closed sources holding files/Readers/sockets?

An example comparing sequential results with a concurrent collector:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> data = Arrays.asList(
        "A", "B", "A", "C", "B", "A"
);

Map<String, Long> sequential = data.stream()
        .collect(Collectors.toMap(
                Function.identity(),
                x -> 1L,
                Long::sum
        ));

ConcurrentMap<String, Long> concurrent = data.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Function.identity(),
                x -> 1L,
                Long::sum
        ));

System.out.println(sequential.equals(concurrent)); // true
```

Here, both Maps have the **same key–value contents**, with no ordering requirement. This is an illustrative check, **not a substitute** for proving thread safety or running tests under heavy load.

## 16. Stream Lifecycle and Resource-Holding Sources

`collect` is a terminal operation: it consumes the pipeline once but **does not automatically close** I/O sources. The `CONCURRENT`/`UNORDERED` characteristics do not change this rule.

Example aggregating log lines by severity level:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static ConcurrentMap<String, Long> countLevels(Path path)
        throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains(":"))
                .map(line -> line.substring(0, line.indexOf(':')))
                .collect(Collectors.toConcurrentMap(
                        level -> level,
                        level -> 1L,
                        Long::sum
                ));
    }
}
```

This example runs sequentially because `parallel()` is not called. The Collector is still concurrent and unordered **in capability**, which does not mean Java automatically creates parallel branches. Choosing `toConcurrentMap` just because you are reading a file brings no automatic benefit; for I/O sources, consider `Spliterator` characteristics and read overhead before deciding to parallelize.

The example assumes lines contain a `:` before the message payload and the key before the colon is valid. If real data has malformed lines or empty keys, establish a validation policy. When file reading encounters an error, the Stream may throw `UncheckedIOException` during consumption; `try-with-resources` still closes the source.

## 17. Checklist for Choosing the Right Collector

| Need | Recommended Choice | Why |
| --- | --- | --- |
| Preserve elements in source order | `Collectors.toList()` | Collects with ordered semantics, no shared container needed |
| Need a set of unique values | `Collectors.toSet()` | Unordered, but no concurrent guarantee |
| Collect a Map and merge by key, concurrent not required | `Collectors.toMap(...)` | Simple contract, still works with parallel |
| Collect a concurrent Map, encounter order irrelevant | `Collectors.toConcurrentMap(...)` | Concurrent + unordered |
| Group by key without needing per-group order | `Collectors.groupingByConcurrent(...)` | Concurrent + unordered |
| Group when element order within each group matters | `Collectors.groupingBy(...)` with appropriate downstream | Does not sacrifice encounter order |
| Only compute a sum or count | `sum()`, `count()` | Specialized terminal operations |
| Need a custom concurrent accumulator | `Collector.of(...)` with a genuinely supporting container | Prove the contract before declaring flags |
| Final result type differs from container type | Collector with a real finisher | Do not declare `IDENTITY_FINISH` |
| Only need to keep the “latest record” | Merge by timestamp + stable tie-breaker key | Do not rely on concurrent update order |

Before adding `parallel()`, ask: “If elements are processed in a different order, will the business requirement still hold?” If the answer is no, **do not use `UNORDERED` just to try to go faster**.

## 18. Common Mistakes

| Mistake | Why It Is Wrong or Dangerous | How to Handle |
| --- | --- | --- |
| Thinking `parallelStream` automatically shares one container across all threads | Java can use multiple independent containers and a combiner | Understand both collection strategies |
| Adding only `UNORDERED` and letting multiple threads mutate `ArrayList` | Unordered does not guarantee thread-safety | Must have `CONCURRENT` **and** a contract-compliant accumulator |
| Declaring `CONCURRENT` for `ArrayList::add` | Can race and lose data | Remove the flag, use `toList` or an appropriate container |
| Thinking `CONCURRENT` implies `UNORDERED` | Two independent characteristics | Check ordering requirements separately |
| Thinking `CONCURRENT` always forces the collector to use one container | The framework is not forced to pick that strategy | Write a correct combiner |
| Using `groupingByConcurrent` and expecting group Lists to preserve encounter order | Unordered collector | Choose an order-preserving collector or sort afterward |
| Seeing `ConcurrentMap` and assuming all mutable values are safe | Map thread-safety does not propagate to value objects | Synchronize/freeze data according to the model |
| Using `(a,b) -> a` for “first arriving” in `toConcurrentMap` | Collision order does not reflect encounter order | Select by data attributes |
| Using a non-associative merge function | Result depends on branch splitting | Design a valid merge operation |
| Building a complex custom concurrent collector just for a sum | Extra code, boxing, overhead | `LongStream.sum()` |
| Choosing `IDENTITY_FINISH` when the result must change type | The finisher may be skipped | Remove the flag and keep the finisher |
| Enabling parallel for small or poorly splittable sources | High coordination cost | Measure before optimizing |
| Thinking `collect` automatically closes a file source | Terminal operations do not call `close` automatically | `try-with-resources` |

## 19. Self-Check Questions

1. Does `parallelStream()` force all threads to share a single accumulator? **No**. It can use multiple containers and a combiner.
2. What does a Collector's `CONCURRENT` guarantee? **The accumulator can be called concurrently on the same container `A`**.
3. Does `UNORDERED` mean Java must shuffle the data? **No**, it only drops the encounter order guarantee.
4. For an ordered parallel Stream, what condition permits accumulating into a single shared container? **The Collector has both `CONCURRENT` and `UNORDERED`**.
5. For an unordered parallel Stream, can a collector with only `CONCURRENT` (no `UNORDERED`) accumulate into a shared container? **Possible**, if the collector is genuinely safe per its contract.
6. Since `Collectors.toSet()` is unordered, does that mean it is concurrent? **No**.
7. Can `Collectors.toList()` be used with a parallel stream even though it is not concurrent? **Yes**; the framework can combine separate containers.
8. Why is `LongAdder` suitable for a custom concurrent accumulator? **It supports multiple threads updating the same counter**.
9. When `A` is `LongAdder` and `R` is `Long`, should `IDENTITY_FINISH` be used? **No**, the finisher needs to convert the result.
10. Does `groupingByConcurrent(..., toList())` guarantee preserving element encounter order in each group? **No**.
11. Does `ConcurrentMap<K,List<V>>` make the value Lists safe for concurrent updates by the caller? **No**.
12. If you need the latest event, why shouldn't you use merge `(a,b) -> b` on a concurrent collector? **Because merge order is not timestamp order**.
13. Is a Collector's `UNORDERED` different from `stream.unordered()`? **Yes**; one flag describes the collection operation, while the other removes the pipeline's ordering constraint.
14. When can a concurrent collector be slower? **When the source is small, the accumulator is cheap, lock contention is high, or coordination overhead is high**.
15. Does `collect` close `Files.lines` automatically? **No**; you must close the Stream with `try-with-resources`.

**Rule of thumb:** Only treat **concurrent collection into a shared container** as valid when the Stream runs in parallel, the Collector genuinely has `CONCURRENT`, and ordering requirements are satisfied by either an unordered Stream **or** an `UNORDERED` Collector. Flags are **correctness guarantees**, not speedup switches. Prefer standard collectors, keep accumulators/combiners contract-compliant, separate Map thread-safety from inner values, and only optimize with parallelism when semantics remain unchanged and real performance measurements support it.
