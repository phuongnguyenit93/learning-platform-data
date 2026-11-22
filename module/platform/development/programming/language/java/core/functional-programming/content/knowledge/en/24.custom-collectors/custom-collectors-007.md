# `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` in Custom Java Collectors

In the Java Stream API, `Collector<T, A, R>` describes how to **collect elements of type `T`** into an **intermediate container of type `A`**, and then produce a **result of type `R`**. When building a custom collector, in addition to the `supplier`, `accumulator`, `combiner`, and `finisher` functions, Java also allows declaring the **characteristics** of the collector:

- `Collector.Characteristics.IDENTITY_FINISH`
- `Collector.Characteristics.UNORDERED`
- `Collector.Characteristics.CONCURRENT`

These are **behavioral guarantees**, not decorative labels or performance switches. The Stream framework can rely on them to decide how to collect data, especially when `parallelStream()` is used. Declaring them incorrectly can cause out-of-order results, lost elements, race conditions, or returning an object of the wrong type.

Example of the desired result:

~~~java
List<String> words = List.of("beta", "alpha", "beta", "gamma");
List<String> keptOrder = words.parallelStream()
        .collect(Collectors.toList()); // [beta, alpha, beta, gamma]
~~~

Here `toList()` can gather data from multiple parallel branches while still producing a result in the encounter order of the source `List`. That does **not** mean a shared `ArrayList` was safely written to by multiple threads. When `CONCURRENT` is not declared, the framework can create separate intermediate containers and then use `combiner` to merge them.

## 1. Collector architecture: five related elements

Consider the general declaration:

~~~java
Collector<T, A, R> collector = ...;
R result = stream.collect(collector);
~~~

The main components:

| Component | Conceptual Type | Responsibility |
| --- | --- | --- |
| `supplier()` | `Supplier<A>` | Allocates a new container `A` |
| `accumulator()` | `BiConsumer<A, T>` | Incorporates an element `T` into container `A` |
| `combiner()` | `BinaryOperator<A>` | Merges two containers `A` into one container `A` |
| `finisher()` | `Function<A, R>` | Transforms intermediate container `A` into result `R` |
| `characteristics()` | `Set<Characteristics>` | Declares the characteristics that the collector actually guarantees |

In a sequential pipeline, there may only be a single container and sequential calls to the accumulator. With a parallel pipeline, the framework can create multiple containers, accumulate independently, and then merge using the combiner, or it can use a concurrent reduction strategy when conditions allow.

Illustrative model:

~~~text
Stream<T>
   |
   +--> supplier() --> A1 --accumulate(T)--> A1'
   |
   +--> supplier() --> A2 --accumulate(T)--> A2'
                                 |
                                 v
                          combiner(A1', A2')
                                 |
                                 v
                           A (container)
                                 |
                          finisher(A)
                                 |
                                 v
                            R (result)
~~~

This diagram is **not** a mandatory sequence for every run: a concurrent collector can receive elements from multiple threads on the same container; the order and number of `supplier`/`combiner` calls also cannot be inferred solely from the number of input elements. You need to understand the **contract**, rather than depending on a specific execution pattern.

The three characteristics are exact enum constants in `java.util.stream.Collector.Characteristics`. There is no `ORDERED` characteristic: if a collector does not declare `UNORDERED`, that allows the framework to preserve encounter order requirements appropriate for the collector.

## 2. `IDENTITY_FINISH`: the result is the accumulation container itself

`IDENTITY_FINISH` indicates that the **finishing step can be omitted**: the intermediate container `A` can be treated directly as the result `R`. By contract, this requires that the transformation from container to result is the identity function and that the container type is directly compatible with the result type.

Example collecting into an `ArrayList`:

~~~java
Collector<String, ?, List<String>> listCollector = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

This illustrative snippet requires importing `Collector`, `ArrayList`, and `List`. `supplier` creates a list, `accumulator` adds each element, and `combiner` concatenates two lists and returns the left list. There is no final result transformation: `A` is the accumulation list and `R` is also a list.

**Important:** the `Collector.of(supplier, accumulator, combiner)` overload **implicitly declares `IDENTITY_FINISH`**. When using the three-parameter overload, `finisher` is inherently the identity function, so there is no need to specify this flag explicitly.

Conversely, for a collector with a `StringJoiner` container that wants a `String` result:

~~~java
Collector<String, StringJoiner, String> joining = Collector.of(
        () -> new StringJoiner("|"),
        StringJoiner::add,
        StringJoiner::merge,
        StringJoiner::toString
);
~~~

`A` is `StringJoiner`, `R` is `String`. `finisher` must convert `StringJoiner` to `String`; `IDENTITY_FINISH` **must not** be attached. If declared incorrectly, the framework is allowed to skip the finisher and use the intermediate container as the result; this can lead to a wrong result type or a `ClassCastException` at the consumer.

### The contract is not just having the same generic type

Even if `A` and `R` have the same declared type, if the finisher actually **transforms** the container (for example, creating an unmodifiable copy, normalizing content, or encoding the result), it is **not an identity finisher**.

~~~java
Collector<String, List<String>, List<String>> snapshot = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        List::copyOf
);
~~~

This is an illustrative snippet requiring `Collector`, `ArrayList`, and `List`. `List.copyOf` creates an unmodifiable result and rejects `null` elements; it is not the identity function on a mutable `ArrayList`. Therefore, do not declare `IDENTITY_FINISH`. Do not rely on the `List<String>` result type to conclude that the finisher is an identity function.

## 3. `UNORDERED`: the result does not depend on encounter order

`UNORDERED` means the collector **does not guarantee preserving the encounter order** of input elements. When a collector has this characteristic, the framework can take advantage of not having to preserve source order to organize execution.

Typical cases:

- Collecting into a `Set` when only **distinct values** matter, not the order of appearance.
- Computing statistics with appropriate associativity/commutativity and no logic that selects elements based on "first seen".
- Collecting into a map keyed by value, if the meaning of the result does not depend on the order in which elements were inserted.

`UNORDERED` **does not require the source to be unordered**. A `List` source with a clear encounter order can still be processed by an unordered collector; in that case, the collector declares that it has no requirement to maintain that order in its result.

~~~java
Set<String> unique = List.of("B", "A", "B")
        .parallelStream()
        .collect(Collectors.toSet());
~~~

`Collectors.toSet()` has the unordered characteristic: the result set contains `A` and `B`, but **the iteration/printing order of the Set is not guaranteed**. `UNORDERED` does not mean "the result is automatically sorted"; even a container with its own structure like a Set requires checking the contract of each collector and collection.

### When you should not declare `UNORDERED`

If the result is a `List` whose business logic needs to preserve the order of appearance:

~~~java
List<String> ordered = List.of("B", "A", "B").parallelStream()
        .collect(Collectors.toList());
// [B, A, B]
~~~

Do not arbitrarily add `UNORDERED` to a similar collector if the result must preserve the original order. When a collector requires the "first element", "insertion order", or formatting text in source order, order is **part of the semantics**.

In particular, string joining with a delimiter (such as `beta|alpha|beta|gamma`) usually depends on order; if `UNORDERED` is attached, the result may differ from what is required.

### "No order guarantee" is different from "random order"

`UNORDERED` does not force the framework to intentionally shuffle elements, and a single run may happen to produce a result matching the input. A mistake is **writing tests that rely on this coincidence**. If you need a stable presentation of a `Set`, sort it at output time:

~~~java
List<String> display = unique.stream().sorted().toList();
~~~

This is a newly sorted List, not evidence that an unordered collector preserves order.

## 4. `CONCURRENT`: the accumulator can run concurrently on the same container

`CONCURRENT` declares that the collector is designed so that `accumulator` can be called by multiple threads **concurrently on the same result container**. This flag is about **thread-safe concurrent accumulation capability**, not merely whether a Stream runs in parallel.

Example of a collector using a Set created from `ConcurrentHashMap.newKeySet()`:

~~~java
Collector<String, ?, Set<String>> concurrentUnique = Collector.of(
        () -> ConcurrentHashMap.<String>newKeySet(),
        Set::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.UNORDERED,
        Collector.Characteristics.CONCURRENT
);
~~~

This illustrative snippet requires `java.util.Set`, `java.util.concurrent.ConcurrentHashMap`, and `java.util.stream.Collector`. `newKeySet()` is a Set that supports concurrent updates; `add` can be called from multiple threads on the same container. `combiner` must still have a correct merging contract and must not be omitted when a Stream implementation chooses to collect using separate containers.

**Easily overlooked point:** the `Collector.of(supplier, accumulator, combiner, characteristics...)` overload is still an overload without a separate finisher, so **`IDENTITY_FINISH` is added implicitly**. For this collector, the actual set of characteristics includes `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT`.

### Actual conditions for concurrent reduction

Even when a Stream is parallel and the collector has `CONCURRENT`, the framework is only **permitted** to use a single shared container for concurrent accumulation when **the Stream is unordered or the collector has `UNORDERED`**. You can read the general logic as:

~~~text
parallel
  AND collector.CONCURRENT
  AND (stream.unordered OR collector.UNORDERED)
  -> Can choose concurrent reduction on the same container
~~~

Do not interpret this condition as a guarantee that the framework **must** use multiple threads or is guaranteed to speed things up. It is an enabling condition for an execution strategy. If a collector has `CONCURRENT` but not `UNORDERED` and the source is still ordered, the framework must not arbitrarily break encounter order; it may use separate accumulators and then combine them to preserve the requirement.

Conversely, a **collector without `CONCURRENT` can still be used in `parallelStream()`**: the framework accumulates into multiple separate containers and then uses the combiner. Do not attach `CONCURRENT` just because callers might use a parallel stream.

### Flags do not replace thread-safe data structures

This is a **wrong** example:

~~~java
// Do not execute this example; ArrayList::add is not safe
// when multiple threads update the same ArrayList.
// Collector<String, ?, List<String>> wrong = Collector.of(
//         ArrayList::new,
//         List::add,
//         (a, b) -> { a.addAll(b); return a; },
//         Collector.Characteristics.CONCURRENT,
//         Collector.Characteristics.UNORDERED
// );
~~~

Declaring `CONCURRENT` can cause the framework to call `ArrayList.add` concurrently on the same list, causing races, lost elements, or structural corruption. `UNORDERED` does not fix thread-safety bugs either. If using a regular `ArrayList`, **do not** declare `CONCURRENT`; the framework can split containers for parallel branches on its own.

A valid concurrent collector must also ensure that **all mutable state touched by the accumulator** is appropriately protected, including counters, auxiliary maps, or contained objects. Merely using `ConcurrentHashMap` on the outside does not automatically make all value objects in the map thread-safe.

## 5. Relationships between the three characteristics

The characteristics are **conceptually independent**, but their combinations affect the collection strategy:

| `IDENTITY_FINISH` | `UNORDERED` | `CONCURRENT` | Design Meaning |
| --- | --- | --- | --- |
| Yes | No | No | The container itself is the result; may need to preserve encounter order |
| No | No | No | Finisher produces a different type/value; may need to preserve encounter order |
| Yes | Yes | No | The container is the result; no order guarantee; uses combiner when parallel |
| Yes | Yes | Yes | The container is the result; no order guarantee; can accumulate concurrently on the same container |
| No | Yes | Yes | Has an actual finisher and a thread-safe accumulator; finisher runs after the accumulation phase |
| Yes | No | Yes | Thread-safe accumulator, but the collector still guarantees ordered semantics when the source is ordered |

This table **does not mean every combination is automatically valid**: you must consider the data, accumulation rules, combining laws, and order guarantees. Additionally, `IDENTITY_FINISH` has nothing to do with whether a collector can be used in a parallel stream; it only determines whether the finisher can be skipped.

Important: `CONCURRENT` and `UNORDERED` are **not synonyms**. A collector can be unordered without supporting concurrent updates; a concurrent collector can still have ordering constraints that must be respected.

### Short table of counterexamples

| False Inference | Reality |
| --- | --- |
| "Having `IDENTITY_FINISH` means the result is immutable" | No: the returned container can be a mutable list |
| "Having `UNORDERED` means the result is sorted" | No: order is not guaranteed |
| "Having `CONCURRENT` means every method on the result is thread-safe" | Only guarantees the accumulator can be used concurrently; does not automatically protect all post-processing operations |
| "Parallel streams require `CONCURRENT`" | No: can accumulate into independent containers and combine |
| "`CONCURRENT` makes it faster" | No speed guarantee; you must measure |
| "Flags are just optimization hints; declaring them wrong is harmless" | Wrong: the framework can trust the flags and return corrupted/wrong-type results |

## 6. Complete Java 17+ example with three custom collectors

Save the file **`CollectorCharacteristicsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.StringJoiner;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collector;

public class CollectorCharacteristicsDemo {
    public static void main(String[] args) {
        List<String> words = List.of("beta", "alpha", "beta", "gamma");

        Collector<String, ?, List<String>> orderedList = Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );

        Collector<String, StringJoiner, String> joined = Collector.of(
                () -> new StringJoiner("|"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString
        );

        Collector<String, ?, Set<String>> concurrentUnique = Collector.of(
                () -> ConcurrentHashMap.<String>newKeySet(),
                Set::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.UNORDERED,
                Collector.Characteristics.CONCURRENT
        );

        System.out.println("ordered=" + words.parallelStream().collect(orderedList));
        System.out.println("joined=" + words.parallelStream().collect(joined));
        System.out.println("uniqueSorted=" + words.parallelStream()
                .collect(concurrentUnique).stream().sorted().toList());

        printFlags("orderedList", orderedList);
        printFlags("joined", joined);
        printFlags("concurrentUnique", concurrentUnique);
    }

    private static void printFlags(String name, Collector<?, ?, ?> collector) {
        Set<Collector.Characteristics> flags = collector.characteristics();
        System.out.println(name + ": identity="
                + flags.contains(Collector.Characteristics.IDENTITY_FINISH)
                + ", unordered=" + flags.contains(Collector.Characteristics.UNORDERED)
                + ", concurrent=" + flags.contains(Collector.Characteristics.CONCURRENT));
    }
}
~~~

Compile/run with **JDK 17** or higher:

~~~bash
javac CollectorCharacteristicsDemo.java
java CollectorCharacteristicsDemo
~~~

**Exact stdout:**

~~~text
ordered=[beta, alpha, beta, gamma]
joined=beta|alpha|beta|gamma
uniqueSorted=[alpha, beta, gamma]
orderedList: identity=true, unordered=false, concurrent=false
joined: identity=false, unordered=false, concurrent=false
concurrentUnique: identity=true, unordered=true, concurrent=true
~~~

Explanation:

1. `orderedList` uses an `ArrayList` container, accumulates with `List::add`, and its combiner concatenates lists. The three-parameter overload implicitly carries `IDENTITY_FINISH` but does not declare `UNORDERED` or `CONCURRENT`. A parallel Stream can still collect using independent containers and merge them, returning a list in encounter order.
2. `joined` accumulates into a `StringJoiner` and finishes with `StringJoiner::toString`. Because `A` and `R` are different, it **does not have `IDENTITY_FINISH`**. When the source is ordered, the joined string result is in the exact order.
3. `concurrentUnique` uses a Set container safe for concurrent updates, deduplicates, and does not require encounter order. `Collector.of` automatically adds `IDENTITY_FINISH`, while we explicitly declare `UNORDERED` and `CONCURRENT`.
4. `uniqueSorted` prints a **separately sorted List**, rather than relying on the unguaranteed iteration order of the concurrent Set.
5. The `printFlags` method checks each characteristic with `contains` instead of printing `Set<Characteristics>` directly, so the display order and accuracy of the stdout string do not depend on how the Set orders enum constants.

This example uses `parallelStream()` to illustrate that **non-concurrent collectors can still be used in parallel pipelines**; the output remains correct when the functions obey the contract. The code was compiled with `javac --release 17` and stdout was verified by actual execution.

## 7. Characteristics from built-in collectors

Not every collector from `Collectors` has the same set of characteristics. Before writing a custom collector, you can refer to the contracts of the corresponding built-in collectors:

- `Collectors.toList()` typically has `IDENTITY_FINISH` because the result container is the accumulation List, but it does **not** specify the exact List implementation or guarantee mutability in its public API contract. You should not use `toList()` to guarantee an `ArrayList`.
- `Collectors.toSet()` does not require preserving order and can use the unordered characteristic. `toSet()` itself is not a concurrent collector because of that.
- `Collectors.toUnmodifiableList()` has a transformation step to create an unmodifiable collection, so it must not be treated as an identity finisher.
- `Collectors.joining(delimiter)` needs to build the result string from the accumulator, so it is not an identity finish case like directly returning a `StringJoiner` container.
- `Collectors.toConcurrentMap(...)` or `Collectors.groupingByConcurrent(...)` provide concurrent/unordered collectors when appropriate for the use case; do not assume every collector with "Map" in its name is concurrent.

The specific set of characteristics can be observed via `collector.characteristics()`; **do not infer all flags solely from a collector's name**. More importantly, when declaring flags yourself, you must understand and satisfy the conditions that each flag represents.

## 8. Associativity, identity, and rules for the combiner

Collector characteristics do not replace the rules of a valid collection operation. A collector must satisfy:

- **Identity constraint:** merging an accumulated container with a new empty container must produce a result equivalent to the original container.
- **Associativity constraint:** splitting elements into multiple segments, accumulating independently, and combining in different groupings must produce an equivalent result with respect to what the collector promises.
- **Compatibility of supplier/accumulator/combiner/finisher:** containers are created, updated, merged, and finished with consistent semantics; no dropped elements, double counting, or wrong type conversions.

Example of an accumulator summing `int` numbers:

~~~java
Collector<Integer, long[], Long> sum = Collector.of(
        () -> new long[1],
        (a, n) -> a[0] += n,
        (left, right) -> {
            left[0] += right[0];
            return left;
        },
        a -> a[0]
);
~~~

This is an illustrative snippet requiring `Collector`. Container `A` is `long[]`, result `R` is `Long`; the finisher `a -> a[0]` is not the identity function. Do **not** attach `IDENTITY_FINISH`. Do **not** attach `CONCURRENT` because updating `a[0] += n` is not safe when multiple threads concurrently update the same array. However, the collector can still be used in a parallel stream when the framework creates separate containers and uses the combiner to merge them.

Note that the `long` result can still overflow if the sum exceeds `Long.MAX_VALUE`; with an `Integer` source, unboxing `n` from `Integer` can throw a `NullPointerException` if an element is null. These issues belong to the computation design and are not solved by characteristics.

### The combiner must not arbitrarily discard one side

Wrong code:

~~~java
// Wrong: discards the entire result of the right branch.
// (left, right) -> left
~~~

It may happen to produce the expected result in a sequential pipeline where the combiner is not called, but when running in parallel, the data from the right branch is lost. You must merge so that the result is equivalent to processing all input elements.

For string joining, the merge order also matters. If the result must preserve encounter order, the combiner needs to append left before right, not reverse them arbitrarily.

## 9. Concurrent collectors and thread-safety limits

A **concurrent** container does not automatically make the entire collector correct:

1. `supplier` must create an appropriate container; reusing a global container across multiple `collect` calls can mix data.
2. `accumulator` must be safe when called concurrently on **the same `A`**; any auxiliary state must also be protected.
3. `combiner` must still be correct when the framework chooses multiple containers; do not assume it will never be called just because `CONCURRENT` is present.
4. `finisher` should not assume it runs before accumulation completes, and must produce the right type `R`. If returning a mutable container and the caller continues using it across multiple threads, the thread-safety contract of the **result collection** must be considered separately.
5. `UNORDERED` should only be declared when the result does not depend on order; a thread-safe structure may still require ordering for business logic.

For example, an accumulator calling `ConcurrentHashMap.computeIfAbsent` and then mutating an `ArrayList` in the value is not automatically safe if threads concurrently add to that list. You must use a component container with synchronization, or design the accumulator around atomic/appropriate operations.

There is no guarantee that attaching `CONCURRENT` will make the operation **faster**. Contention overhead, memory, number of groups, and parallelization overhead can make the pipeline slower than sequential execution.

## 10. Subtle mistakes when declaring characteristics

### Wrong: attaching `IDENTITY_FINISH` to a finisher that transforms the result

~~~java
// Violates the contract if IDENTITY_FINISH is added:
// Collector<String, StringJoiner, String> c = Collector.of(
//         () -> new StringJoiner(","),
//         StringJoiner::add,
//         StringJoiner::merge,
//         StringJoiner::toString,
//         Collector.Characteristics.IDENTITY_FINISH
// );
~~~

If the framework skips the finisher and uses `StringJoiner` where a `String` is expected, the result is not the type the caller expects. Do not attach this flag to "save one finisher call".

### Wrong: attaching `CONCURRENT` to an accumulator using `ArrayList`

~~~java
// Violates thread safety if List::add is still used:
// Collector<String, ?, List<String>> c = Collector.of(
//         ArrayList::new,
//         List::add,
//         (a, b) -> { a.addAll(b); return a; },
//         Collector.Characteristics.CONCURRENT,
//         Collector.Characteristics.UNORDERED
// );
~~~

The collector may be used on a shared container in a parallel stream, causing races. Do not declare `CONCURRENT` if it is only correct when each thread has its own container.

### Wrong: attaching `UNORDERED` when the first element or output order is needed

If a collector is building a `List` in input order or a `String` joining elements in order, attaching `UNORDERED` allows the framework not to preserve an important business requirement.

### Wrong: assuming `CONCURRENT` means the accumulator always runs simultaneously

This flag does not guarantee thread count, parallelism, speed, or the choice of a single shared container in every run. It enables concurrent reduction **when the remaining conditions are met**.

### Wrong: thinking `IDENTITY_FINISH` means the result is immutable

A collector returning the mutable `ArrayList` itself is still an identity finish. `toUnmodifiableList()`, by contrast, has a separate finishing step to produce an unmodifiable result. *Identity* refers to the result conversion step, not immutability.

### Wrong: measuring performance via side effects in the accumulator

Incrementing an unsynchronized global variable to "count invocations" both breaks the correctness of a concurrent collector and can skew benchmarks. Use benchmarks with representative data, observe standard results, and use JMH/Java Flight Recorder when you need to evaluate real performance.

## 11. Verification checklist for custom collectors

When creating a custom collector, you should check step by step:

1. **Identify types `T, A, R`:** what are the input element, accumulation container, and expected return result?
2. **Prove identity:** `combiner(a, supplier.get())` must be equivalent to the accumulated `a`, in terms of the result.
3. **Prove associativity:** splitting the source into segments, collecting independently, and merging in various ways must yield equivalent results; pay attention to order for collections/lists or string joining.
4. **Examine the finisher:** is the result truly the container itself? Only declare `IDENTITY_FINISH` if the finisher can be omitted while still returning the right type and semantics.
5. **Examine encounter order:** do you need "first occurrence", "exact order", or ordered string joining? If so, do not attach `UNORDERED` arbitrarily.
6. **Examine concurrent updates on the same `A`:** is the accumulator safe when two threads call it simultaneously? If not, **do not** attach `CONCURRENT`.
7. **Test both `stream()` and `parallelStream()`:** compare values, without comparing the order of an unordered result; test empty input, single element, many duplicates, and large data.
8. **Measure if truly needed:** benchmark with warm-up and reasonable data, because parallelization overhead and contention can outweigh the benefits of a concurrent collector.

An important best practice: when a characteristic has not been proven, **do not declare it**. A safe, contract-compliant collector is worth more than unsubstantiated optimization flags.

## 12. Quick decision table

| Scenario | `IDENTITY_FINISH` | `UNORDERED` | `CONCURRENT` |
| --- | --- | --- | --- |
| Collect List with `ArrayList`, return the list itself, preserve order | Yes | No | No |
| Accumulate `StringJoiner`, return `String` in order | No | No | No |
| Collect distinct Set, order does not matter, non-thread-safe container | Yes if returning the Set itself | Yes | No |
| Collect Set with `ConcurrentHashMap.newKeySet()`, return the Set itself, order does not matter | Yes | Yes | Yes |
| Count with `long[]` then finisher returns `Long` | No | Possibly, if semantics do not depend on order | No |
| Collect List then finisher creates `List.copyOf(...)` | No | No if order is needed | No if accumulator is ArrayList |
| Collect Map by key with possible concurrent updates | Depends on finisher | Depends on semantics | Only if accumulator and internal state are truly thread-safe |

**In summary:** `IDENTITY_FINISH` allows treating the accumulation container as the result itself; `UNORDERED` allows dropping encounter order constraints; `CONCURRENT` allows the accumulator to receive concurrent updates on the same container when the framework selects a concurrent reduction strategy. The three flags are **contract declarations** that must be properly upheld by the supplier, accumulator, combiner, and finisher. Choosing fewer but accurate flags is always better than over-declaring and hoping the framework happens to run safely.