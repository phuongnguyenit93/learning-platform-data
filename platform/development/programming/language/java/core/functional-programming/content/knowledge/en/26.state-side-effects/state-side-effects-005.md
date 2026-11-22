# Using `collect()` Instead of External Accumulators in Java Stream

In functional programming with Java Stream, a common mistake is creating a `List`, `Map`, counter, or `StringBuilder` **outside the pipeline**, and then using `forEach()`, `map()`, or `peek()` to update them. That code may appear to work when executed sequentially, but it becomes hard to test, state-dependent, and prone to **race conditions** when switching to `parallelStream()`.

`collect()` is a terminal operation used to **gather elements into a result** under a clear contract. Instead of letting lambdas arbitrarily mutate an external variable, we delegate creating, updating, and merging result containers to Stream's collection mechanism.

Lesson goals: identify external accumulators, convert them into appropriate `collect()` calls, understand sequential/parallel collection, and choose between `collect()`, `reduce()`, and specialized aggregation APIs.

## 1. What Is an External Accumulator?

An *external accumulator* is state declared outside the pipeline that gets mutated by a callback inside the pipeline:

```java
List<String> result = new ArrayList<>();

names.stream()
        .filter(name -> !name.isBlank())
        .forEach(name -> result.add(name.trim()));
```

This is an **illustrative snippet requiring the imports** `java.util.List`, `java.util.ArrayList`, and a variable `names` of type `List<String>`; it is not a standalone program.

With a sequential stream, the list may contain the expected names. However:

- The result is a side effect on `result`, not a value returned by the pipeline.
- Transformation logic and state management logic are mixed together.
- Anyone else holding a reference to `result` can observe or modify it during processing.
- Changing `stream()` to `parallelStream()` allows multiple callbacks to call `ArrayList.add` concurrently: **not safe for concurrent writes**.

If the problem only requires a result list, write it in a data-oriented way:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::trim)
        .toList();
```

Here, `filter()` and `map()` do not mutate external state; the terminal `toList()` gathers the results into a list. Note that `Stream.toList()` since Java 16 returns an **unmodifiable** list.

If you want to use `collect()`:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::trim)
        .collect(Collectors.toList());
```

This snippet requires `import java.util.stream.Collectors;`. `Collectors.toList()` does not guarantee a specific list type, mutability, or thread-safety. If a mutable `ArrayList` is needed, use `Collectors.toCollection(ArrayList::new)`.

## 2. `collect()` Moves State Inside the Stream Mechanism

For `Stream<T>`, two common API forms are:

```java
<R,A> R collect(Collector<? super T,A,R> collector)

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R,? super T> accumulator,
        BiConsumer<R,R> combiner
)
```

These are **abbreviated API signatures**, not a standalone Java class.

The form accepting a `Collector` is the most common:

```java
Map<String, Long> counts = names.stream()
        .collect(Collectors.groupingBy(
                String::trim,
                Collectors.counting()
        ));
```

The pipeline describes: group by the trimmed string, then count each group. There is no need to create a `HashMap` beforehand and update it manually.

The three-argument form provides three specific behaviors:

1. **`supplier`** creates a new result container.
2. **`accumulator`** adds an input element into that container.
3. **`combiner`** merges two intermediate containers when needed.

Example:

```java
List<String> labels = names.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
```

This is a snippet inside a method, requiring `java.util.List`, `java.util.ArrayList`. Each container created by the supplier is a new `ArrayList`; `List::add` updates the container managed by Stream, not a shared list created externally beforehand; `List::addAll` merges intermediate lists.

**Important:** The `combiner` in the `collect(supplier, accumulator, combiner)` form has type **`BiConsumer<R,R>` returning `void`**, unlike `BinaryOperator<A>` **returning `A`** in a custom `Collector.of(...)`.

## 3. Complete Runnable Java 17+ Example

Save as file `CollectInsteadOfSideEffectsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class CollectInsteadOfSideEffectsDemo {
    record Order(String region, String code, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("HN", "A", 2),
                new Order("HCM", "B", 4),
                new Order("HN", "C", 3)
        );

        List<String> labels = orders.parallelStream()
                .map(order -> order.code() + "=" + order.quantity())
                .collect(
                        ArrayList::new,
                        List::add,
                        List::addAll
                );

        Map<String, Integer> totalsByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::region,
                        TreeMap::new,
                        Collectors.summingInt(Order::quantity)
                ));

        int totalQuantity = orders.parallelStream()
                .mapToInt(Order::quantity)
                .sum();

        List<Integer> largeQuantities = orders.stream()
                .filter(order -> order.quantity() >= 3)
                .map(Order::quantity)
                .toList();

        String codes = orders.stream()
                .map(Order::code)
                .collect(Collectors.joining(","));

        System.out.println("labels = " + labels);
        System.out.println("totalsByRegion = " + totalsByRegion);
        System.out.println("totalQuantity = " + totalQuantity);
        System.out.println("largeQuantities = " + largeQuantities);
        System.out.println("codes = " + codes);
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac -encoding UTF-8 CollectInsteadOfSideEffectsDemo.java
java CollectInsteadOfSideEffectsDemo
```

Exact stdout:

```text
labels = [A=2, B=4, C=3]
totalsByRegion = {HCM=4, HN=5}
totalQuantity = 9
largeQuantities = [4, 3]
codes = A,B,C
```

**Why is this output deterministic?**

- The `List` source has an encounter order; `map` does not change logical order. `collect(ArrayList::new, List::add, List::addAll)` on an ordered stream preserves the result order `A=2, B=4, C=3`, even though processing may happen in parallel.
- `groupingBy(..., TreeMap::new, summingInt(...))` sums quantities by region and asks `TreeMap` to sort keys: `HCM` before `HN`. The total for HN is `2 + 3 = 5`.
- `mapToInt(...).sum()` is the appropriate primitive reduction for summing; no external `AtomicInteger` is needed.
- `toList()` gathers the results of `filter`/`map` into a list in source order.
- `joining(",")` concatenates strings directly, avoiding manual management of an external `StringBuilder`.

The example uses standard collectors and aggregation operations designed by Java to fit the Stream mechanism. There is no need to manually synchronize a shared collection.

## 4. Why `parallelStream().forEach(list::add)` Is Not `collect()`

A **poorly designed** example:

```java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(output::add);
```

This is an illustrative snippet placed inside a method, requiring `java.util.List`, `java.util.ArrayList`, and `java.util.stream.IntStream`. `ArrayList` does not support concurrent writes from multiple threads without synchronization; the result may lose elements, have indeterminate order, or even fail during updates. **Do not run this code to obtain reliable data.**

The correct version, without shared variables:

```java
List<Integer> output = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
```

Or, if a specific mutable `ArrayList` is needed:

```java
List<Integer> output = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
```

Both options use an ordered `IntStream.range`, so the resulting list contains numbers from `0` to `9_999` in encounter order. The `toList` version is unmodifiable; the `toCollection(ArrayList::new)` version returns a mutable `ArrayList`.

### Do `Collections.synchronizedList(...)` or `AtomicInteger` Solve Everything?

No. A synchronized list can make the `add` operation safe from races when multiple threads update it, but:

- The order of `forEach` invocations on a parallel stream is **not guaranteed** to follow encounter order.
- The logic still depends on external side effects, making reuse or testing difficult.
- Synchronization can become a contention point when data is large.

Similarly, `AtomicInteger` makes incrementing a shared counter atomic, but using it inside `map` or `peek` does not turn the pipeline into a meaningful aggregation; intermediate callbacks can be optimized away or short-circuited depending on the terminal operation.

If the goal is counting elements, use `count()`; if the goal is summing integers, use `mapToInt(...).sum()`; if the goal is multiple statistics, choose the corresponding downstream collector.

## 5. Thinking in "Each Branch Has Its Own Container" During Parallel Collection

A valid collector lets Java organize accumulation like this:

```text
Ordered source:   A  B  C  D
                   \ /   \ /
                 group 1 group 2
                    |       |
              supplier() supplier()
                    |       |
                 add A,B  add C,D
                    \       /
                     combiner
                        |
                  [A, B, C, D]
```

The diagram is only a conceptual model: Java may split into a different number of groups and execute callbacks on different threads.

Correctness requires:

- **Supplier** provides a suitable initial container; for mutable collections, each call must create an independent container, never returning the same shared instance.
- **Accumulator** updates the provided container; it must not modify the stream source or another shared state.
- **Combiner** merges all relevant data from two containers without losing or duplicating elements.
- **Identity and associativity**: merging with an empty container does not change the result; changing how groups are split/merged does not change the observable result under the ordering contract.

It is not that `ArrayList` suddenly becomes thread-safe when used with `collect`. The difference is that Stream can **manage separate containers per branch** for a collector without the `CONCURRENT` characteristic, and then merge them. For example, `Collectors.toList()` works with parallel streams without requiring a single `ArrayList` shared across all threads.

## 6. Use Standard Collectors Before Writing a Custom Collector

Most common problems already have built-in collectors:

| Needed Result | Solution |
| --- | --- |
| List of elements | `toList()` or `collect(Collectors.toList())` |
| Mutable `ArrayList` | `collect(Collectors.toCollection(ArrayList::new))` |
| Set of distinct elements | `collect(Collectors.toSet())` |
| Naturally ordered set | `collect(Collectors.toCollection(TreeSet::new))` |
| String joined with delimiter | `collect(Collectors.joining(","))` |
| Group by property | `collect(Collectors.groupingBy(keyFn))` |
| Group and count | `collect(Collectors.groupingBy(keyFn, Collectors.counting()))` |
| Group then sum | `collect(Collectors.groupingBy(keyFn, Collectors.summingInt(valueFn)))` |
| Partition into two `true/false` branches | `collect(Collectors.partitioningBy(predicate))` |
| Statistics count/sum/min/max/average | `collect(Collectors.summarizingInt(valueFn))` |

`Collectors.toSet()` does not guarantee the set type or iteration order. `Collectors.toList()` makes no general promise about list mutability. When a specific structure is needed, choose `toCollection(factory)` or the `groupingBy(classifier, mapFactory, downstream)` overload.

**Watch out for duplicate key errors:** The two-argument `Collectors.toMap(keyFn, valueFn)` typically throws `IllegalStateException` if duplicate keys are produced. If the data has multiple records with the same key, use `groupingBy` or provide an explicit merge function to `toMap`.

## 7. When Should You Write `Collector.of(...)`?

If you need to accumulate multiple fields and produce a dedicated result, a custom collector can be appropriate. For example, gathering **record count** and **total item quantity** in a single pass:

```java
import java.util.List;
import java.util.stream.Collector;

public class CustomCollectExample {
    record Order(int quantity) {}
    record Summary(long count, long total) {}

    static final class Acc {
        long count;
        long total;

        void add(Order order) {
            count++;
            total += order.quantity();
        }

        Acc merge(Acc other) {
            count += other.count;
            total += other.total;
            return this;
        }

        Summary finish() {
            return new Summary(count, total);
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(new Order(2), new Order(3));

        Collector<Order, Acc, Summary> collector = Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish
        );

        Summary summary = orders.parallelStream().collect(collector);
        System.out.println(summary);
    }
}
```

Save as file `CustomCollectExample.java`, run:

```bash
javac CustomCollectExample.java
java CustomCollectExample
```

Stdout:

```text
Summary[count=2, total=5]
```

Here, the mutable `Acc` is **strictly internal state owned by the collector**. Outside the pipeline, callers only receive `Summary`, a value record, not a partially updated accumulator.

`Acc::merge` merges both fields completely so the result does not depend on how branches are split. If the supplier started with `count=1`, or the combiner added an extra number not from the data, parallel execution could overcount. If `Acc` is not thread-safe, do **not** declare `Collector.Characteristics.CONCURRENT`.

A custom collector is not the first choice for simple `sum()`, `count()`, or `joining()` operations; standard APIs are usually shorter and less risky.

## 8. Distinguishing `collect()` and `reduce()`

Both terminal operations aggregate data, but they serve different accumulation styles:

| Criterion | `reduce()` | `collect()` |
| --- | --- | --- |
| Nature | **Reduces values** using a combining operation | **Collects into a container** and optionally transforms into a final result |
| Accumulation state | Usually should be immutable and replaced with a new value | Can be a mutable container inside the collector |
| Identity | Identity value of the combining operation | Empty container state created by the supplier |
| Parallel | Requires an associative operation and proper identity | Requires supplier, accumulator, and combiner satisfying the contract |
| Example | `reduce(0, Integer::sum)` | `collect(Collectors.toList())` |

Do not use `reduce` with a mutable `ArrayList` or `StringBuilder` **as a shared identity** and mutate it inside the accumulator; this easily violates the reduce contract when running in parallel. Instead, use `collect()` with a supplier that creates a new container.

For specialized operations, prefer the shortest API:

```java
long count = orders.stream().count();
int total = orders.stream().mapToInt(Order::quantity).sum();
```

This is a snippet inside a class with record `Order` and variable `orders` as in the full example. There is no need to use `collect` just to count or sum.

## 9. `map`/`peek` Are Not Places for Mandatory Accumulation Logic

A common anti-pattern:

```java
AtomicInteger counter = new AtomicInteger();

long count = Stream.of("A", "B", "C")
        .peek(x -> counter.incrementAndGet())
        .count();
```

This is a **poorly designed** illustrative snippet requiring `java.util.concurrent.atomic.AtomicInteger` and `java.util.stream.Stream`. On sources with a known size, the implementation can compute `count()` **without calling `peek` for every element**; therefore, `counter` must not be treated as a reliable pipeline counter. An atomic variable does not guarantee that callbacks will run.

Similarly, using `map(x -> { externalList.add(x); return x; })` to record side effects is error-prone when the pipeline is short-circuited by `limit`, `findFirst`, `anyMatch`, or optimized. Correct results must be derived from a **well-defined terminal operation**.

If you genuinely need to write a file, make an HTTP call, or send a notification, place that action at an intentionally orchestrated boundary with an error/retry policy, rather than trying to replace `collect` with hidden I/O inside `peek`.

## 10. Correctness with Encounter Order and Parallelism

- `parallelStream()` does not automatically discard the encounter order of a `List`. If the collector preserves order, the result list can still follow source order, even though callbacks execute concurrently.
- `parallelStream().forEach(action)` **does not guarantee** that `action` is called in encounter order. Using it to append to an external list violates both thread-safety and ordering requirements.
- `forEachOrdered(action)` can enforce running actions in encounter order, but if you only need **a result list**, `collect` or `toList` expresses intent more clearly and is easier to test.
- `Collectors.groupingByConcurrent(...)` has concurrent/unordered characteristics; do not assume it preserves element order within each group. Only use it when encounter order is not required or when processing is designed accordingly.
- `Collector.Characteristics.CONCURRENT` should only be declared when the accumulator can genuinely be invoked concurrently on the same container and remain correct. A collector that works with parallel streams **does not necessarily** have this characteristic.

Do not automatically switch every pipeline to parallel expecting it to be faster. For small datasets, lightweight work, or collectors requiring strict order coordination, splitting/merging overhead can outweigh the benefits. Choose the right approach first, then measure performance with real data.

## 11. Testing Behavior Instead of Checking Side-Effect State Variables

An easily testable pipeline is one that **returns a result**:

```java
List<Integer> actual = List.of(1, 2, 3, 4).stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();

if (!actual.equals(List.of(20, 40))) {
    throw new AssertionError(actual);
}
```

This is an illustrative snippet inside a method with `import java.util.List;`. There is no need to mock an external `ArrayList` or inspect side effects triggered in `peek`.

When writing a custom collector, you should test:

1. **Empty stream:** `supplier` creates the proper initial state and finisher returns the contract-compliant result for an empty source.
2. **Single element:** accumulator does not duplicate data.
3. **Merging an empty container:** `combiner(a, supplier.get())` yields a result equivalent to `a`.
4. **Group splitting:** gathering `[a,b]` and `[c,d]` and merging produces the same result as sequentially collecting the whole list.
5. **Associativity:** different ways of grouping and combining yield equivalent results (for ordered collectors, order must also match).
6. **Parallel vs sequential:** compare results across multiple datasets; do not run just once and conclude it is correct.
7. **Independence:** supplier creates a new container each time; no unintended sharing of mutable instances.

The laws should be reasoned about in terms of the real data domain; some floating-point operations may differ due to rounding when additions are grouped differently.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `parallelStream().forEach(sharedList::add)` | Race condition and indeterminate order | `collect(toList())`, `toList()`, or `toCollection(...)` |
| Incrementing `AtomicInteger` in `peek` to count | Callback is not guaranteed to execute; relies on side effects | `count()` |
| Summing via an external `int[] sum` variable | Shared mutable state, unsafe in parallel | `mapToInt(...).sum()` or `reduce(0, Integer::sum)` |
| Manually updating a `HashMap` inside `forEach` | Race condition, wrong merge, or data loss | `groupingBy`, `toMap` with a merge function |
| Supplier returning the same shared `ArrayList` | Branches may concurrently modify the same container | `ArrayList::new` creating a new instance |
| Combiner forgetting data from the right branch | Parallel collect loses elements | Merge completely, in the right direction, preserving order if needed |
| Assuming `Collectors.toList()` always returns a mutable `ArrayList` | API does not promise type/mutability | `toCollection(ArrayList::new)` |
| Using `reduce` with a mutable `StringBuilder` identity | Violates the parallel reduction contract | `Collectors.joining()` or a proper custom collector |
| Using `forEachOrdered` just to build a result list | Unnecessary side effects and easily forced synchronization | `toList()` or `collect()` |
| Marking a collector `CONCURRENT` with non-thread-safe state | Race condition when concurrently updating one container | Declare only when the accumulator is designed to be concurrent |

## Knowledge Check

**Question 1.** Why is `parallelStream().forEach(result::add)` with an external `ArrayList` unsafe?

**Answer:** Threads can call `add` concurrently on the same `ArrayList`, while `ArrayList` is not synchronized for write operations; parallel `forEach` ordering is also not guaranteed.

**Question 2.** If you only need a result list in source order, should you choose `forEachOrdered(list::add)` or `toList()`?

**Answer:** Usually choose `toList()` when appropriate, or `collect(...)` when a specific container type is desired. They express the result directly instead of placing side effects inside a callback.

**Question 3.** In `collect(ArrayList::new, List::add, List::addAll)`, what does the combiner do?

**Answer:** It merges the data from the second container into the first container when accumulated parts need to be combined. It is a `BiConsumer` and does not return a container.

**Question 4.** Does using `Collectors.toList()` guarantee that the resulting list is a mutable `ArrayList`?

**Answer:** No. If you need an `ArrayList`, use `Collectors.toCollection(ArrayList::new)`.

**Question 5.** When the problem only needs a total quantity, should you write a custom `collect` or `mapToInt(...).sum()`?

**Answer:** Prefer `mapToInt(...).sum()` because it directly expresses a primitive aggregation and avoids managing collector state.

**Question 6.** Can a custom collector using a mutable `Acc` run in parallel without declaring `CONCURRENT`?

**Answer:** Yes. The framework can maintain separate containers per branch and then merge them. `CONCURRENT` is only used when the same container can be safely updated concurrently.

## Key Takeaways

- **Do not gather results using a mutable variable outside the pipeline** if `collect()`, `toList()`, or a specialized aggregation already expresses the problem cleanly.
- `collect()` creates and manages accumulation state **inside the Stream mechanism**, making code less dependent on external side effects and better suited for parallel processing.
- Use standard collectors for lists, sets, maps, grouping, joining, and statistics; use `Collector.of` when genuinely custom state is needed.
- Supplier must create an appropriate container; accumulator updates the container; combiner merges completely with proper order/semantics; identity/associativity/equivalence laws must hold.
- A **thread-safe external list** does not automatically make a parallel `forEach` ordered; an **atomic counter in `peek`** does not turn a callback into reliable counting.
- Distinguish **collecting results** from **I/O and business side effects**: process data with pipelines, and perform external effects at controlled boundaries.
