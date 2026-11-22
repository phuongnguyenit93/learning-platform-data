# Non-interference: Do Not Interfere with the Source Being Processed

## Lesson objectives

In the Java Stream API, we describe how to process data through a **pipeline**: a data source, intermediate operations such as `filter` and `map`, and then a terminal operation such as `toList`, `collect`, or `reduce`. Most intermediate operations are executed **lazily**: creating a pipeline does not mean the data has already been traversed.

An essential contract for a pipeline to operate correctly is **non-interference**: behavior passed into a Stream must not modify **the data source that the Stream is traversing** during processing. This is the foundation allowing declarative operations to be optimized, executed in different orders, or run in parallel.

After this lesson, you will be able to:

- Recognize when a lambda, another thread, or a helper method is interfering with the Stream source.
- Distinguish non-interference from *statelessness* and *side effect* issues.
- Choose ways to filter, transform, group, or update data without modifying the source while the pipeline is running.
- Understand the impact of laziness, concurrent-capable sources, and `parallelStream()` on this contract.

## 1. What is non-interference?

Consider a simple pipeline:

```java
List<String> names = new ArrayList<>(List.of("An", "Bình", "Chi"));

List<String> selected = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toList(); // JDK 16+

System.out.println(selected); // [BÌNH, CHI]
```

Here:

1. **The source** is `names`, a mutable `ArrayList`.
2. **Intermediate operations** `filter` and `map` only read each element to decide whether to retain it and produce a new value.
3. **The terminal operation** `toList` triggers traversal and collects results into another list.

While `toList()` is processing, no operation adds, removes, or alters the contents of `names`. This pipeline obeys non-interference.

```text
ArrayList names ── stream() ── filter() ── map() ── toList()
  (source)                read-only per element      (new result)
```

**Core point:** do not interfere with **the source currently being traversed**. Having a Stream or `Collector` create and update its **own result container** does not violate this principle.

For ordinary sources not designed for concurrent mutation, the non-interference contract applies to behavioral functions supplied to the Stream (predicate, mapper, comparator, consumer, accumulator...) as well as to code running outside the pipeline while the source is being traversed. The exception requiring separate consideration is a source whose traversal mechanism supports concurrent modification, explained in section 6.

## 2. Violation example: mutating the list itself inside `filter`

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> evens = numbers.stream()
        .filter(n -> {
            if (n == 2) {
                numbers.add(99); // INVALID: mutating the source currently being traversed
            }
            return n % 2 == 0;
        })
        .toList();
```

When running the terminal operation `toList()`, the `filter` lambda adds an element to `numbers` itself. `ArrayList` usually detects structural modification during traversal and may throw `ConcurrentModificationException`. However, **do not treat the presence or absence of an exception as the criterion for correctness**:

- Another source might not detect the modification.
- A value-replacement operation like `list.set(index, value)` might not increment the structural modification counter, yet still causes the result to depend on read timing.
- With a parallel pipeline, mutation can cause skipped elements, duplicate elements, or unpredictable results; exact behavior depends on the source and traversal mechanism.

Similarly, the following also interfere with the source if executed while the pipeline is traversing `numbers`:

```java
numbers.removeIf(n -> n < 0);
numbers.clear();
numbers.set(0, 100);
```

The calls above are **not always wrong**. They simply must not be executed *concurrently with traversing that very source*, unless the source is specifically designed to permit it. For example, calling `removeIf` **before** creating/running the Stream or **after** the terminal operation completes is normal usage.

### Fix: compute results first, update the source afterward

If you want to extract even numbers for processing and remove them from the original list, split it into two phases:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// Phase 1: read-only on source; create separate result.
List<Integer> evens = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();

// Phase 2: terminal operation has finished, now modify the source.
numbers.removeIf(n -> n % 2 == 0);

System.out.println(evens);   // [2, 4]
System.out.println(numbers); // [1, 3]
```

If the goal is **only** to remove elements, calling `numbers.removeIf(...)` directly is clear and needs no Stream. If the goal is to transform or extract data, use `filter`/`map`/`collect` to produce a new output.

## 3. Laziness determines when the source must be kept stable

Calling `stream()` and intermediate operations usually only **describes the pipeline**. They have not yet begun traversing the entire source; the terminal operation is what triggers processing.

```java
List<String> names = new ArrayList<>(List.of("An", "Bình"));

Stream<String> pipeline = names.stream()
        .filter(name -> name.length() >= 3);

names.add("Chi"); // Before terminal operation: valid for this ArrayList source.

List<String> result = pipeline.toList();
System.out.println(result); // [Bình, Chi]
```

This example uses the *late-binding* property of the iterator/spliterator from `ArrayList`: it does not lock down the set of elements to traverse right when the pipeline is created. Many Stream sources behave this way, yet **not every source guarantees the same binding time**. Do not assume every Stream reflects all modifications made prior to the terminal operation.

Distinguish these points in time:

| Point in time | With a typical `ArrayList` source |
| --- | --- |
| Before creating the pipeline | Elements can be added, removed, or modified normally. |
| After building the pipeline but before starting the terminal operation | Can be modified; a late-binding source like `ArrayList` lets the pipeline see the changes. |
| While the terminal operation is traversing the source | Do not modify the source; this is the zone where non-interference must be obeyed. |
| After the terminal operation completes | The source can be updated. The already-used Stream cannot run a terminal operation again. |

Because traversal normally happens inside the terminal operation, **do not** call source-mutating methods from `filter`, `map`, `peek`, `forEach`, from a comparator passed to `sorted`, or from an accumulator of `reduce`. Another thread modifying the source during that same interval causes the same problem.

A terminal operation may short-circuit (`findFirst`, `anyMatch`, `limit` combined with a terminal operation), or the system may skip some steps via optimization. Therefore, never rely on the number of times a lambda is invoked to perform a mandatory sequence of updates.

## 4. Distinguishing non-interference, statelessness, and side effects

These three concepts are related yet address different questions:

| Concept | Question to check | Example |
| --- | --- | --- |
| **Non-interference** | Does the function modify **the source being traversed**? | `source.add(...)` inside `filter` is a violation. |
| **Stateless** | Does the processing result for this element depend on state that changes while processing other elements? | Using a shared counter inside `map` is typically *stateful*. |
| **Side effect** | Does the function do anything other than producing/testing an output value? | Logging, incrementing a counter, emitting an event are side effects. |

The following example **does not modify the source list** yet still uses shared state, making it unsuitable for the *stateless* requirement of many Stream operations:

```java
List<String> names = List.of("An", "Bình", "Chi");
AtomicInteger sequence = new AtomicInteger();

List<String> labels = names.parallelStream()
        .map(name -> sequence.incrementAndGet() + ": " + name)
        .toList();
```

`AtomicInteger` makes the increment atomic, yet **does not guarantee** which person receives which sequence number when elements are processed in parallel. Positional numbering problems should use an indexed loop or `IntStream.range` over data with stable indices, rather than depending on mapper execution timing.

Another mistake is writing into a shared result list:

```java
List<Integer> source = List.of(1, 2, 3, 4);
List<Integer> output = new ArrayList<>();

source.parallelStream()
        .map(n -> n * 2)
        .forEach(output::add); // INVALID: multiple threads concurrently mutating ArrayList output.
```

Here `output` is **not the source**, so the direct flaw is side effects and unsafe concurrent access, even though `source` is not interfered with. The proper way is to let the Stream manage accumulation:

```java
List<Integer> output = source.parallelStream()
        .map(n -> n * 2)
        .toList(); // [2, 4, 6, 8], preserves encounter order of an ordered source.
```

`peek` is also not the place for business update operations: it can be helpful for observing during debugging, yet invocation of the `peek` lambda is not guaranteed for every element in every pipeline. When verifiable results are needed, use `map` to produce new values, `filter` to select elements, and `collect` to accumulate.

### What about mutating properties of objects inside the source?

```java
orders.stream()
        .peek(order -> order.setStatus("PROCESSED"))
        .toList();
```

Even without calling `orders.add/remove`, the example above still carries a side effect on objects belonging to the source. If those properties affect predicates, comparators, `equals/hashCode`, or are being read by another thread, results can become inconsistent. Moreover, `peek` is not guaranteed to execute as an update step. The safe approach is to create new records/DTOs using `map`, or perform object updates in a controlled **separate phase** after computation finishes.

## 5. `collect` mutates data, so why is it still valid?

Non-interference does not forbid **all** mutation. It forbids modifying **the source while the Stream is processing that source**. Having a `Collector` construct a new `List`, `Map`, or result structure is a valid accumulation mechanism.

```java
List<String> words = List.of("java", "stream", "map", "reduce", "filter");

Map<Integer, List<String>> byLength = words.stream()
        .collect(Collectors.groupingBy(String::length));

System.out.println(byLength);
// Example: {3=[map], 4=[java], 6=[stream, reduce, filter]}
```

In the example above, `groupingBy` creates and updates a result `Map`; `words` is not modified. With parallel Streams, the framework uses the Collector's accumulation and combining mechanisms according to contract, avoiding manually writing `forEach` and unsafely mutating a shared `HashMap`.

Choose the right result form:

- `stream.toList()` (JDK 16+) returns an **unmodifiable** `List`; do not call `add`/`remove` on it.
- `collect(Collectors.toList())` makes no guarantee about implementation type or mutability of the returned list.
- `collect(Collectors.toCollection(ArrayList::new))` is appropriate when **a mutable result list is needed**.

Example:

```java
List<String> editable = words.stream()
        .filter(word -> word.length() >= 5)
        .collect(Collectors.toCollection(ArrayList::new));

editable.add("pipeline"); // Modifies the new result, does not affect words.
```

Also distinguish **intermediate operations with internal state** (`distinct`, `sorted`, `limit`) from **lambdas depending on external state**. Library operations are designed to manage their own state; they do not permit predicates/mappers to arbitrarily mutate the source.

## 6. Sources supporting concurrent modification: understanding the exception properly

Some sources are designed to allow modification during traversal. For example, `ConcurrentHashMap` has a `Spliterator` supporting the `CONCURRENT` characteristic and *weakly consistent* traversal: concurrent modification does not necessarily cause `ConcurrentModificationException`, though recently added/removed elements may be observed or missed depending on timing.

```java
ConcurrentHashMap<String, Integer> live = new ConcurrentHashMap<>();
live.put("A", 10);
live.put("B", 20);

// If another thread modifies live during traversal:
long matching = live.keySet().parallelStream()
        .filter(key -> key.startsWith("A"))
        .count();
```

Here, the source's support for concurrent traversal solves **traversal safety**, yet **does not provide an atomic data snapshot** and does not guarantee a fixed result when source contents change. You must choose semantics matching the business logic:

- Accepting a potentially changing view of data: use a collection with a concurrent traversal contract and accept timing-dependent results.
- Needing a stable dataset for computation: create a copy, an immutable dataset, or lock/version the data per system design before processing.
- Needing consistency at **a single point in time**: merely copying a collection currently being updated is not enough to guarantee an atomic snapshot; there must be synchronization or a snapshot mechanism provided by the system.

Note that calling `parallelStream()` on an `ArrayList` **does not turn** `ArrayList` into a safe source for concurrent modification. Similarly, wrapping a list with `Collections.synchronizedList(...)` does not automatically turn every pipeline over it into a snapshotted traversal.

## 7. Complete business example: aggregating orders then updating the list

Suppose we need to compute the total value of paid orders per customer, then remove processed orders from the pending list. The two tasks can run sequentially, each with a clear responsibility:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NonInterferenceDemo {
    record Order(String customer, int amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> pending = new ArrayList<>(List.of(
                new Order("An", 100, true),
                new Order("Bình", 80, false),
                new Order("An", 50, true),
                new Order("Chi", 40, true)
        ));

        // Step 1: read-only on pending, aggregate into a separate Map.
        Map<String, Integer> paidTotalByCustomer = pending.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                        Order::customer,
                        Collectors.summingInt(Order::amount)
                ));

        System.out.println(paidTotalByCustomer);
        // {An=150, Chi=40} (key order is not guaranteed)

        // Step 2: update pending after the terminal operation has finished.
        pending.removeIf(Order::paid);

        System.out.println(pending);
        // [Order[customer=Bình, amount=80, paid=false]]
    }
}
```

Points to observe:

1. `filter` only inspects order status; it does not alter `pending`.
2. `groupingBy` and `summingInt` accumulate into a result `Map` managed by the Collector.
3. `removeIf` updates the source **after** `collect` has completed.
4. When wanting to process the source with a parallel stream, this phase separation still keeps the pipeline from depending on source mutation during traversal. If another thread also updates `pending` concurrently, a separate synchronization strategy is still required.

Examples using `record` and `Stream.toList` in this lesson require Java 16 or later. Examples using `List.of` require Java 9 or later; on Java 8 you can use `Arrays.asList` to create initial data and `collect(Collectors.toList())` when needing to build a list from a Stream.

## 8. Error signs and how to inspect

When reviewing a pipeline, follow this order:

1. **Identify the actual source.** Where are `source.stream()`, `map.keySet().stream()`, `Files.lines(path)`, or a custom `Spliterator` drawing data from? With views like `map.keySet()`, modifying `map` also modifies the source.
2. **Find all write paths to the source.** Check `add`, `remove`, `clear`, `set`, mutations to stateful elements, helper method calls, and code running on other threads. Do not look only at the body of `filter`.
3. **Determine the timing of writes.** Does the mutation happen before, during, or after the terminal operation? Lazy intermediate operations make execution timing differ from the line creating the pipeline.
4. **Check shared state.** Even without mutating the source, a lambda might still use an external counter, list, or map; when running in parallel, that is a separate risk.
5. **Check the source contract.** If relying on concurrent modification, does the collection/Spliterator commit to supporting it? Is a consistent snapshot required?

Some symptoms to trace:

| Symptom | What to review |
| --- | --- |
| `ConcurrentModificationException` | Is the source collection structurally modified while the pipeline traverses? |
| No error reported, yet erratic results | Is there `set`, object mutation, another thread, or a weakly consistent concurrent source? |
| Correct sequentially, wrong in `parallel` | Is there shared mutable state or dependence on lambda call order? |
| `peek` does not run for every element | Is there a pipeline optimization or a short-circuiting terminal operation? |
| Returned result is unmodifiable | Was `Stream.toList()` used instead of intentionally creating a mutable collection? |

## 9. Self-practice

The following snippet tries to collect all numbers greater than 10 and remove them from the source at the same time:

```java
List<Integer> values = new ArrayList<>(List.of(4, 12, 7, 18, 3));

List<Integer> large = values.stream()
        .filter(n -> {
            if (n > 10) {
                values.remove(n);
            }
            return n > 10;
        })
        .toList();
```

**Question:** What is the violation? How can we still obtain `large = [12, 18]` and keep `values = [4, 7, 3]`?

**Suggested answer:**

```java
List<Integer> large = values.stream()
        .filter(n -> n > 10)
        .toList();

values.removeIf(n -> n > 10);
```

Elements have finished being filtered before the source list is modified. There is no need to rely on implicit processing order or exceptions to achieve the result.

## Key takeaway

**Non-interference is a contract about the data source:** while a Stream is traversing an ordinary source, behavioral functions and external code must not modify that source. Mutation of the result container managed by a Collector is a separate matter; a lambda that does not modify the source can still be wrong due to shared state or side effects. Keep `filter`/`map` read-only, use `collect` to build results, and move source mutation into a clear phase outside the pipeline. For concurrent sources, read the source's consistency contract carefully before relying on updates during traversal.
