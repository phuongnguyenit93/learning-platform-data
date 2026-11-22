# Distinguishing Immutable Reduction and Mutable Container Reduction

In a **Java Stream API** pipeline, after `filter` and `map` steps, we often need to combine multiple elements into a single result: total revenue, order count, a summary string, a normalized list, or a grouped statistics table. A **reduction** operation transforms a sequence of elements into an aggregated result.

Java has two important approaches:

- **Non-mutating reduction**, typically using `reduce`. Each step computes a new accumulated value from the previous value and the current element, such as adding two numbers to produce a new number.
- **Mutable reduction**, typically using `collect`. Each element is placed into a **result container** such as an `ArrayList`, `HashMap`, or statistics object; the container is updated in place and can then be merged with another container.

Both approaches belong to the declarative data processing model of the **JAVA_STREAM_API** module, but their API contracts and behavior in a **parallel Stream** differ significantly. This lesson belongs to the **Collect Mechanism and Collector** chapter, providing the foundation to learn `groupingBy`, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers while still recognizing limitations regarding state, memory, and performance.

After this lesson, you will be able to explain why summing typically uses `reduce` or `sum`, why creating a `List` should use `collect`, how `supplier` / `accumulator` / `combiner` work, and why **you must not use a mutable list as the identity to simulate `collect` with `reduce`**.

## 1. One problem, two result types

Suppose a sales system has four orders. We want to:

1. Compute the **total amount of paid orders**: the result is a `long` value.
2. Collect the **list of IDs of paid orders**: the result is a `List<String>`.

Complete example using **Java 17 or later** due to `record` and `Stream.toList()`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class TwoReductionStyles {
    record Order(String id, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", 120_000L, true),
            new Order("DH02",  80_000L, false),
            new Order("DH03", 150_000L, true),
            new Order("DH04",  50_000L, true)
        );

        long paidTotal = orders.stream()
            .filter(Order::paid)
            .map(Order::amountVnd)
            .reduce(0L, Long::sum);

        List<String> paidIds = orders.stream()
            .filter(Order::paid)
            .map(Order::id)
            .collect(Collectors.toList());

        System.out.println(paidTotal); // 320000
        System.out.println(paidIds);   // [DH01, DH03, DH04]
    }
}
~~~

Both pipelines start from a `List<Order>` and use lazy intermediate steps. The difference lies in **how the result is built**:

- `reduce(0L, Long::sum)` combines numbers into a new `long` after each step. There is no collection-like accumulator object that needs to be modified in place.
- `collect(Collectors.toList())` gathers the strings into one or more list-shaped containers and returns the result. Adding an element to a list is a **mutable** operation, but it is performed inside the collector mechanism.

The summation could be replaced with `mapToLong(Order::amountVnd).sum()`, which is usually more concise and avoids boxing. Here `reduce` is written explicitly to clearly show the underlying principle.

> **Immutable reduction does not mean all source elements are immutable.** It describes an accumulation approach that **does not mutate the previous result object itself**. The value returned after each step can be a number, string, or a new immutable object. Conversely, a collector can produce a final result that does not allow modification even though the **temporary container** during collection remains mutable.

## 2. Visualizing the two data flows

~~~mermaid
flowchart TD
    S["Source: 120000, 150000, 50000"] --> R["reduce(0, Long::sum)"]
    R --> R1["0 + 120000 = 120000"]
    R1 --> R2["120000 + 150000 = 270000"]
    R2 --> R3["270000 + 50000 = 320000"]
    R3 --> V["Final value: 320000"]
    T["Source: DH01, DH03, DH04"] --> C["collect(toList())"]
    C --> C1["Create list []"]
    C1 --> C2["add(DH01), add(DH03), add(DH04)"]
    C2 --> L["Result list"]
~~~

The diagram above illustrates the **sequential** order for ease of understanding. When executing in parallel, the framework may split data into multiple branches and then combine results in a different structure; the code must still produce a **valid result** according to each method's contract.

| Criterion | Reduction with `reduce` | Reduction with `collect` |
|---|---|---|
| Idea | Combine elements into a new accumulated value | Put elements into a mutable result container |
| Commonly used for | Sum, product, min/max, immutable results | `List`, `Set`, `Map`, grouping, complex statistics |
| Accumulation operation | Function returns a new value | Function updates a container |
| Result on empty Stream | Identity if present; `Optional.empty()` if no identity | Empty container/value created by supplier and finisher |
| Branch merging | Combination operation must be **associative** | Combiner merges the **containers** |
| Side effects in accumulator | Should not have any | Mutates its **own container** according to the contract |
| Representative APIs | `reduce`, `mapToLong(...).sum()` | `collect`, `Collectors.toList()`, `groupingBy` |

## 3. reduce: accumulating without mutating a container

`Stream<T>` has three common `reduce` overloads:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)

T reduce(T identity, BinaryOperator<T> accumulator)

<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
)
~~~

All of them are **terminal operations**: they trigger the pipeline to produce a result and consume the Stream. What `reduce` overloads share is that the accumulator describes a **value-combining operation**, not an action that mutates a shared container.

### 3.1. With identity: empty result returns identity

~~~java
import java.util.List;

List<Integer> values = List.of(3, 5, 7);

int total = values.stream()
    .reduce(0, (left, right) -> left + right);

int emptyTotal = List.<Integer>of().stream()
    .reduce(0, Integer::sum);

System.out.println(total);      // 15
System.out.println(emptyTotal); // 0
~~~

`0` is the **identity** (neutral element) of addition: `0 + x = x` and `x + 0 = x`. `Integer::sum` is shorthand for the function adding two numbers.

For multiplication, the identity is typically `1`:

~~~java
int product = List.of(2, 3, 4).stream()
    .reduce(1, (a, b) -> a * b);

System.out.println(product); // 24
~~~

If the wrong identity is chosen, the result is mathematically wrong right away. For example, `reduce(10, Integer::sum)` adds 10 extra to the actual sum; identity 10 is invalid for addition.

### 3.2. Without identity: Optional result

~~~java
import java.util.Optional;

Optional<Integer> max = List.of(4, 9, 2).stream()
    .reduce(Integer::max);

Optional<Integer> empty = List.<Integer>of().stream()
    .reduce(Integer::max);

System.out.println(max.orElse(-1));   // 9
System.out.println(empty.isPresent()); // false
~~~

When there are no elements, no valid maximum value can be derived from the data, so this overload returns `Optional.empty()`. Do not pick `reduce(0, Integer::max)` out of habit if the source might contain only negative numbers: the result can be wrong. When the intent is finding the maximum/minimum value, `max`/`min` also express the right semantics and return Optional.

### 3.3. Three parameters: transforming the accumulated result type

The three-parameter overload allows input elements of type `T` to be accumulated into a result of a different type `U`:

~~~java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi");

int totalCharacters = names.stream().reduce(
    0,
    (total, name) -> total + name.length(),
    Integer::sum
);

System.out.println(totalCharacters); // 9
~~~

In this example:

- `identity = 0`: initial length of the result.
- `accumulator`: takes an `Integer` total and a `String`, then **returns a new total**.
- `combiner`: adds two branch totals together, required when combining partial results during parallel execution.

Note that `"An"` has 2 characters, `"Bình"` has 4 characters, and `"Chi"` has 3 characters; the total is **9**. Although this is a valid example, when you only want to count characters, the pipeline `names.stream().mapToInt(String::length).sum()` is usually shorter and avoids boxing.

## 4. The reduce contract: identity, associativity, and state

For the framework to safely partition elements and combine results, the reduction operation must obey important conditions.

### 4.1. Identity must be neutral

For a combining operation `op`, identity `e` must satisfy `op(e, x) = x` and `op(x, e) = x` for all applicable values. For the three-parameter overload, `combiner(identity, u)` must equal `u` for any valid accumulated result.

For example, string concatenation has the empty string `""` as its identity. However, using string concatenation with `reduce` for large outputs can incur many string allocations because `String` is immutable; when building long strings, `Collectors.joining` is usually more suitable.

### 4.2. The combining operation must be associative

Associativity means:

~~~text
(a op b) op c = a op (b op c)
~~~

Integer addition within Java's numeric range is commonly used as an example. Subtraction is **not** associative:

~~~java
int sequential = List.of(10, 3, 2).stream()
    .reduce(0, (left, right) -> left - right);

System.out.println(sequential); // -15 (on this sequential pipeline)
~~~

The sequential result may look reasonable according to a custom formula, but it is **not a safe reduction to split into branches and merge in arbitrary order**. When running in parallel, the grouping order may differ and change the result.

With `double`, addition is approximate due to floating-point rounding; changing how additions are grouped can produce numerical differences. If monetary data requires precision, consider integer currency units with overflow handling, or `BigDecimal` with defined rounding rules.

### 4.3. Accumulator must be non-interfering and stateless

A proper `reduce` should not have side effects on the source or shared containers:

~~~java
int sum = List.of(2, 4, 6).parallelStream()
    .reduce(0, Integer::sum);

System.out.println(sum); // 12
~~~

The framework may create local results for each branch and merge them. Therefore, let the accumulation **return a result from its arguments** instead of mutating external variables; do not use `reduce` for mandatory logging, database updates, or writing to a shared list.

### 4.4. Compatibility in the three-parameter overload

With the `reduce(identity, accumulator, combiner)` overload, the accumulator and combiner must also be **compatible**. Semantically, accumulating `t` into `u` and then merging with `v` must yield the same result as accumulating `t` after `u` and `v` have been merged (or more specifically, per the identity/combiner relationship):

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

The equality above expresses the compatibility law for the relevant values; it ensures splitting the sequence into branches does not change the result. If the accumulator and combiner perform semantically different operations, a parallel pipeline can fail even if sequential execution appears to work.

## 5. Why not use reduce with a mutable ArrayList?

A very common mistake is trying to collect a Stream into a list using `reduce`:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

// Do not do this: mutates identity and returns the same object!
List<String> broken = words.parallelStream().reduce(
    new ArrayList<String>(),
    (list, word) -> {
        list.add(word);
        return list;
    },
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
~~~

**This is not a valid use of `reduce` under the semantics of non-mutating reduction.** The accumulator mutates `list` itself and returns the same reference; the `identity` object may be shared or reused across branches, and the combiner may merge duplicate references. The result risks duplicates, wrong ordering, race conditions, or runtime errors. Do not use this code in an application or expect it to always fail the same way.

Even when running sequentially and "appearing to work", this style creates misconceptions about the `reduce` contract and easily breaks when switched to a parallel Stream.

**The right way:** use `collect`, because this API is designed to **create separate containers, accumulate into containers, and merge containers**:

~~~java
List<String> words = List.of("Java", "Stream", "API");

List<String> safe = words.parallelStream()
    .collect(java.util.stream.Collectors.toList());

System.out.println(safe); // [Java, Stream, API]
~~~

Since the source is a `List` with an encounter order and the `toList` collector preserves order according to the ordered collection contract, the output list has the same sequence of values. Still, the `Collectors.toList()` API does not guarantee the implementation class, mutability, serializability, or thread-safety of the **returned list**.

## 6. collect: reduction using mutable containers

`Stream<T>` has two forms of `collect`:

~~~java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)

<R, A> R collect(Collector<? super T, A, R> collector)
~~~

The first form passes the three functions directly. The second form encapsulates the rules into a reusable `Collector`.

### 6.1. Practicing the three-parameter form

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

ArrayList<String> result = words.parallelStream().collect(
    ArrayList::new, // supplier: creates a new container
    ArrayList::add, // accumulator: adds each element to the container
    ArrayList::addAll // combiner: merges another container into this container
);

System.out.println(result); // [Java, Stream, API]
~~~

Each function does exactly one job:

| Component | Functional type | Role |
|---|---|---|
| `supplier` | `Supplier<R>` | Creates a **new container** when needed |
| `accumulator` | `BiConsumer<R, T>` | Updates a container with one element |
| `combiner` | `BiConsumer<R, R>` | Merges two compatible containers |

For example, if the Stream is split into two branches:

~~~text
Branch 1:
  supplier() -> []
  add("Java") -> ["Java"]
  add("Stream") -> ["Java", "Stream"]

Branch 2:
  supplier() -> []
  add("API") -> ["API"]

Combine:
  left.addAll(right) -> ["Java", "Stream", "API"]
~~~

This is an illustrative model; the number of branches, when the supplier is called, and how merging happens are decided by the framework. Do not write code that depends on the supplier being called exactly twice or the combiner running on a specific thread.

### 6.2. Why doesn't ArrayList need self-synchronization here?

In the standard collection pattern, the framework can partition the data and use **independent containers** for the work chunks, then combine the containers. Thus the accumulator can update its own `ArrayList`, even though `ArrayList` is not thread-safe.

This **does not mean** every way of sharing an `ArrayList` across threads is safe. If the supplier always returns **the same object** instead of creating a new one, such as returning a list variable declared outside the pipeline, independence is broken and results may be wrong. Similarly, introducing side effects on state outside the collector can cause race conditions.

### 6.3. Wanting to keep a specific collection type

If the result must be an `ArrayList` and you need a modifiable list, you can use:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> editable = words.stream()
    .collect(Collectors.toCollection(ArrayList::new));

editable.add("Collector");
System.out.println(editable); // [Java, Stream, API, Collector]
~~~

When you only need a `List` and have no specific requirement on mutability, `Collectors.toList()` is easy to read. `Stream.toList()` (Java 16+) returns an **unmodifiable** list, which differs from specifying a mutable container for the collection process.

## 7. Collector: the contract of the collection process

`Collector<T, A, R>` describes how to transform elements of type `T` into a result `R` via an **intermediate container** of type `A`.

The five key components of a Collector are:

1. **`supplier()`:** creates a new container `A`.
2. **`accumulator()`:** adds an element `T` into `A`.
3. **`combiner()`:** merges two containers `A`.
4. **`finisher()`:** converts container `A` into the final result `R`.
5. **`characteristics()`:** describes characteristics such as `IDENTITY_FINISH`, `UNORDERED`, or `CONCURRENT`.

~~~mermaid
flowchart TD
    S["Stream<T>"] --> L["Left branch"]
    S --> R["Right branch"]
    L --> A1["supplier -> A1"]
    R --> A2["supplier -> A2"]
    A1 --> B1["accumulator(A1, T)"]
    A2 --> B2["accumulator(A2, T)"]
    B1 --> C["combiner(A1, A2)"]
    B2 --> C
    C --> F["finisher(A) -> R"]
~~~

`A` and `R` **can be the same type or different types**. For example:

- `Collectors.toList()` uses a list container and returns a list.
- A report-computing collector can use `MutableStats` to accumulate during processing, then return an immutable `Stats` upon completion.

This separation between the **mutable intermediate** and the **final result** makes `Collector` more flexible than simply returning a container.

### 7.1. Collector characteristics to understand properly

| Characteristic | Meaning |
|---|---|
| `IDENTITY_FINISH` | The finisher is the identity function, essentially the accumulator type can be used as the result; the framework may skip a separate finisher step |
| `UNORDERED` | The collection result does not commit to preserving encounter order |
| `CONCURRENT` | The collector allows multiple threads to call the accumulator **concurrently on the same result container** per contract |

**`CONCURRENT` does not mean every collector running in parallel shares a single container.** Non-concurrent collectors can still execute in parallel using independent containers and the combiner. Conversely, if you declare `CONCURRENT` on a collector whose accumulator is not safe when updating the same container, the result may be corrupted.

`UNORDERED` and Stream encounter order are two concepts to consider together. You should not declare `UNORDERED` on a collector if the business logic requires the output order to follow the source order.

## 8. Custom collector example: mutable container, immutable result

Suppose we need statistics on order count and total amount; we want to **accumulate efficiently** into a mutable temporary object, then return an **immutable** final report. This is the clearest example showing that **mutable reduction does not require producing a mutable final result**.

Complete example for **Java 17+**:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class CustomStatsCollectorDemo {
    record Order(String id, long amountVnd, boolean paid) {}
    record Stats(long count, long totalVnd) {}

    static final class StatsAccumulator {
        private long count;
        private long totalVnd;

        void add(Order order) {
            count++;
            totalVnd += order.amountVnd();
        }

        StatsAccumulator merge(StatsAccumulator other) {
            count += other.count;
            totalVnd += other.totalVnd;
            return this;
        }

        Stats finish() {
            return new Stats(count, totalVnd);
        }
    }

    static Collector<Order, StatsAccumulator, Stats> statsCollector() {
        return Collector.of(
            StatsAccumulator::new,   // supplier
            StatsAccumulator::add,   // accumulator
            StatsAccumulator::merge, // combiner
            StatsAccumulator::finish // finisher
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", 120_000L, true),
            new Order("DH02",  80_000L, false),
            new Order("DH03", 150_000L, true)
        );

        Stats result = orders.parallelStream()
            .filter(Order::paid)
            .collect(statsCollector());

        System.out.println(result.count());    // 2
        System.out.println(result.totalVnd()); // 270000
    }
}
~~~

In this example:

- `Order` is the source element `T`.
- `StatsAccumulator` is the intermediate container `A`: the two fields `count` and `totalVnd` are mutated via `add`/`merge`.
- `Stats` is the result `R` as a record, with primitive fields and **no setters**.
- `finish()` creates a new result value from the accumulated state.
- `Collector.of(...)` does **not** declare `CONCURRENT` or `UNORDERED`. Accumulation containers are handled under the standard collector contract; it can be used in a parallel Stream thanks to the split-and-merge mechanism.

No shared mutable object is passed from outside into the pipeline. `StatsAccumulator` is only created via `supplier` and merged via `combiner`. This design fits the requirements for parallel execution **by contract**, as long as the accumulator, combiner, and finisher continue to obey their respective laws.

> **Arithmetic limits:** A `long` total amount can overflow if the data is extremely large. The example uses small numbers to focus on the collector mechanism; real applications need rules for currency units, overflow, and precision, potentially using `BigDecimal` or another appropriate representation.

## 9. Comparison with reduce returning an immutable result

If the aggregated result is very small, we **can** use a new immutable value at each step:

~~~java
import java.util.List;

record Stats(long count, long totalVnd) {}
record Order(String id, long amountVnd, boolean paid) {}

List<Order> orders = List.of(
    new Order("DH01", 100L, true),
    new Order("DH02", 200L, false),
    new Order("DH03", 300L, true)
);

Stats stats = orders.stream()
    .filter(Order::paid)
    .reduce(
        new Stats(0, 0),
        (current, order) -> new Stats(
            current.count() + 1,
            current.totalVnd() + order.amountVnd()
        ),
        (left, right) -> new Stats(
            left.count() + right.count(),
            left.totalVnd() + right.totalVnd()
        )
    );

System.out.println(stats); // Stats[count=2, totalVnd=400]
~~~

This snippet uses the `Stats` and `Order` records, so it requires Java 16+. With this `reduce`:

- `Stats` at each step is a **new object**, with no mutable fields to modify.
- Identity `new Stats(0, 0)` is not mutated during accumulation.
- The accumulator and combiner create a new `Stats` by adding the components.
- The merge operation obeys the identity and associativity laws within integer arithmetic bounds.

This style is functionally clear, but **can allocate many intermediate objects** when processing very large datasets. The collector in section 8 updates one mutable object per branch, which can save allocations. Actual performance evaluation should rely on benchmarks and data volume, not merely whether the code uses `reduce` or `collect`.

### Conceptual boundary

A `reduce` operation **can return a complex object**; the core requirement is that the accumulator does not mutate the previous result state. A `collect` operation **can return an immutable value** through its finisher. Therefore, classify by the **accumulation mechanism**, not solely by the type of the final result.

## 10. Common standard collectors

Java provides `java.util.stream.Collectors` to reduce the need to write custom collectors for common cases.

| Goal | Collector | Illustrative result |
|---|---|---|
| Collect elements into a `List` | `Collectors.toList()` | A list |
| Collect into a `Set` | `Collectors.toSet()` | Set of unique values |
| Specify collection type | `Collectors.toCollection(ArrayList::new)` | Mutable `ArrayList` |
| Join strings | `Collectors.joining(", ")` | A `String` |
| Group by key | `Collectors.groupingBy(Order::category)` | `Map<key, List<Order>>` |
| Partition by predicate | `Collectors.partitioningBy(Order::paid)` | `Map<Boolean, List<Order>>` |
| Count elements | `Collectors.counting()` | `Long` |
| Sum numeric values | `Collectors.summingLong(Order::amountVnd)` | `Long` |
| Compute multiple statistics | `Collectors.summarizingLong(Order::amountVnd)` | `LongSummaryStatistics` |
| Collect unmodifiable list (Java 10+) | `Collectors.toUnmodifiableList()` | Unmodifiable `List` |

Examples with `Order::category` require `Order` to have a `category` field; here they are **API selection patterns**, while the complete examples in this lesson use `Order` according to the model declared in each snippet.

### 10.1. String joining: same result, different mechanism

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> tags = List.of("java", "stream", "collector");

String byReduce = tags.stream()
    .reduce("", (left, right) ->
        left.isEmpty() ? right : left + ", " + right
    );

String byCollect = tags.stream()
    .collect(Collectors.joining(", "));

System.out.println(byReduce);  // java, stream, collector
System.out.println(byCollect); // java, stream, collector
~~~

Both can produce the same string on this sequential pipeline. However, the accumulator in `byReduce` is peculiar in that **it is not compatible with arbitrary merging unless formatting/identity rules are carefully designed**; the example demonstrates convenience but is not a recommended formula for all parallel environments.

`Collectors.joining(", ")` directly expresses the intent and typically handles concatenations more efficiently via a builder-style container. When you need a string with a delimiter, prefix, or suffix, prefer `joining`. If you want to know whether a `reduce` algorithm is valid in parallel execution, explicitly verify identity, associativity, and branch-merging rules.

### 10.2. Unmodifiable list and mutable reduction

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> ids = List.of("A", "B", "C");

List<String> immutableResult = ids.stream()
    .collect(Collectors.toUnmodifiableList());

// immutableResult.add("D"); // Throws UnsupportedOperationException.
~~~

`toUnmodifiableList()` has been available since Java 10 and **does not accept `null` elements**. Even though the result is unmodifiable, the collector can still use a mutable container during the intermediate stage. Immutability **of the result** does not imply the pipeline used `reduce`.

`Stream.toList()` (Java 16+) also returns an unmodifiable List, but has a different null policy from `Collectors.toUnmodifiableList()`; you must choose according to the API contract your application needs.

### 10.3. Grouping and per-group aggregation

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String category, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("Sách", 100L),
    new Sale("Bút",   30L),
    new Sale("Sách",  50L)
);

Map<String, Long> revenueByCategory = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::category,
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(revenueByCategory.get("Sách")); // 150
System.out.println(revenueByCategory.get("Bút"));  // 30
~~~

`groupingBy` acts as the outer collector, while `summingLong` is the downstream collector for each group. It illustrates **collector composition**: grouping and summing by key in a single terminal operation. Do not assume the iteration order of keys in the `Map` returned by `groupingBy` unless you specify an appropriate Map type.

## 11. Parallel Stream: correctness before performance

Reduction is designed to combine results from multiple branches, but is only correct when the functions obey the contract.

~~~mermaid
flowchart TD
    S["Source: 1,2,3,4"] --> A["Branch A: 1,2"]
    S --> B["Branch B: 3,4"]
    A --> RA["reduce -> 3"]
    B --> RB["reduce -> 7"]
    RA --> RC["combiner: 3 + 7 = 10"]
    RB --> RC
    RC --> OUT["Result: 10"]
~~~

With mutable reduction, each branch can have its own **separate container**:

~~~text
Branch A: supplier() -> [] -> add(1), add(2) -> [1, 2]
Branch B: supplier() -> [] -> add(3), add(4) -> [3, 4]
Combiner: [1, 2] + [3, 4] -> [1, 2, 3, 4]
~~~

The two strategies do not conflict: `reduce` combines **values**, while `collect` combines **containers**.

### 11.1. Why is the same ArrayList unsafe with forEach?

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> output = new ArrayList<>();

// Dangerous: multiple threads may add to the same ArrayList.
List.of(1, 2, 3, 4).parallelStream()
    .forEach(output::add);
~~~

`ArrayList` is not thread-safe; concurrent updates can lose elements, corrupt state, or produce unpredictable results. Using a `synchronizedList` just to fix this bug may still fail to meet ordering and performance requirements.

**Replace with a collector**:

~~~java
List<Integer> output = List.of(1, 2, 3, 4)
    .parallelStream()
    .collect(java.util.stream.Collectors.toList());
~~~

`collect` organizes creation, accumulation, and merging of results according to the contract. Remember that **ordering** is handled by encounter order and collector characteristics, not by the order in which threads finish.

### 11.2. Collector.CONCURRENT differs from Stream.parallel()

- `parallel()` or `parallelStream()` describes **how the pipeline may execute**.
- `Collector.Characteristics.CONCURRENT` describes whether **the collector's accumulator allows multiple threads to update the same container**.

A collector can support parallel processing **without declaring `CONCURRENT`**, because the system uses multiple independent containers. When building a concurrent collector yourself, you must design both the container and accumulator accordingly and consider `UNORDERED`/encounter order.

You should not declare `CONCURRENT` or `UNORDERED` merely in hopes of a speedup when the corresponding properties are not satisfied.

### 11.3. Splitting and merging overhead

Parallelism can be effective when data is large enough, the source splits easily (`Spliterator` with suitable characteristics), and the accumulator/combiner do enough work to offset coordination overhead. For very small pipelines, creating branches and merging containers can be **costlier than running sequentially**.

Measure on real data: timing, allocations, element count, contention potential, and ordering requirements all affect the outcome. There is no rule that `collect` or `reduce` is always faster than the other.

## 12. Additional contracts: source, laziness, state, and null

### 12.1. Do not modify the source data being traversed

`filter`, `map`, and functions in the pipeline should be **non-interfering**, meaning they do not modify the data source itself during traversal. For instance, in a pipeline reading a `List<Order>`, do not add/remove orders inside an accumulator or lambda.

With `collect`, **updating the target container created by the supplier** is expected behavior; it is different from modifying the source or mutating a shared object outside that container.

### 12.2. Laziness and single-use lifecycle

`reduce` and `collect` are both terminal operations, so they trigger lazy intermediate operations. After calling a terminal operation, you cannot reuse the same Stream:

~~~java
var stream = List.of(1, 2, 3).stream();

int sum = stream.reduce(0, Integer::sum);

// stream.collect(Collectors.toList()); // Invalid: already consumed.
List<Integer> copy = List.of(1, 2, 3).stream()
    .collect(java.util.stream.Collectors.toList());
~~~

If the source is an I/O file such as `Files.lines(...)`, you must close the Stream with `try-with-resources`. The result of `collect` does not replace the responsibility of managing the source resource.

### 12.3. Nulls and empty-result rules

`Collectors.toUnmodifiableList()` and `Stream.toList()` have different null policies; do not assume every collector accepts null. With `Collectors.toMap`, duplicate keys can cause an `IllegalStateException` unless a merge function is provided, and null policies must be checked for each specific collector.

For an empty source:

~~~java
int zero = List.<Integer>of().stream()
    .reduce(0, Integer::sum);

List<Integer> emptyList = List.<Integer>of().stream()
    .collect(java.util.stream.Collectors.toList());

System.out.println(zero);              // 0
System.out.println(emptyList.isEmpty()); // true
~~~

`reduce(identity, ...)` returns the identity; a collector typically returns an empty result created from the supplier and finisher. Without an identity, `reduce(accumulator)` returns `Optional.empty()`. These differences matter when distinguishing "a value of 0" from "no records".

## 13. Common mistakes and how to fix them

| Mistake | Why it is wrong or risky | How to fix |
|---|---|---|
| `reduce(new ArrayList<>(), ... add ...)` | Mutates identity, violating non-mutating reduction; prone to break in parallel | `collect(Collectors.toList())` or `collect(ArrayList::new, List::add, List::addAll)` |
| `parallelStream().forEach(sharedList::add)` | Unsafe writes to shared state | Collect using a contract-compliant collector |
| Supplier returns the same existing List | Branches do not have independent containers | Supplier must create a **new container** when called |
| Combiner ignores right-branch data | Parallel result loses data | Merge both containers completely and return a valid container |
| `reduce(10, Integer::sum)` to compute a sum | Wrong identity for addition | Use 0 |
| `reduce(0, Integer::min)` to find min of positive numbers | 0 intrudes and produces the wrong minimum | Use `min` or `reduce(Integer::min)` |
| `reduce` accumulator uses subtraction | Not associative | Design an associative combining operation |
| Declaring `CONCURRENT` collector on ArrayList | Container is not safe for concurrent updates | Remove the characteristic or use a contract-compliant concurrent container/accumulator |
| Assuming `Collectors.toList()` is always a mutable `ArrayList` | API does not guarantee specific type/mutability | Use `toCollection(ArrayList::new)` when needed |
| Using `toArray` or `collect(toList)` on an infinite source | Cannot complete or exhausts resources | Place an appropriate limit before the terminal operation |
| Reusing a Stream after `collect` | Stream is already consumed | Create a new Stream from a reusable source |

## 14. Practice exercise: reducing and collecting orders

Given a list of payments, perform the following:

1. Compute the total amount of payments with `successful = true` using `reduce`.
2. Collect the IDs of successful payments into a `List<String>` using `collect`.
3. Create a map of **successful payment counts per customer** using a standard collector.
4. Write how to collect the IDs using the three-parameter overload of `collect`.
5. Explain what happens when the list is empty.

**Reference solution (Java 17+):**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ReductionPractice {
    record Payment(String id, String customer, long amount, boolean successful) {}

    public static void main(String[] args) {
        List<Payment> payments = List.of(
            new Payment("P01", "An",   120L, true),
            new Payment("P02", "Bình", 200L, false),
            new Payment("P03", "An",    80L, true),
            new Payment("P04", "Chi",   50L, true)
        );

        long total = payments.stream()
            .filter(Payment::successful)
            .map(Payment::amount)
            .reduce(0L, Long::sum);

        List<String> ids = payments.stream()
            .filter(Payment::successful)
            .map(Payment::id)
            .collect(Collectors.toList());

        Map<String, Long> countByCustomer = payments.stream()
            .filter(Payment::successful)
            .collect(Collectors.groupingBy(
                Payment::customer,
                Collectors.counting()
            ));

        ArrayList<String> idsWithThreeArgs = payments.stream()
            .filter(Payment::successful)
            .map(Payment::id)
            .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
            );

        System.out.println(total);                    // 250
        System.out.println(ids);                      // [P01, P03, P04]
        System.out.println(countByCustomer.get("An")); // 2
        System.out.println(ids.equals(idsWithThreeArgs)); // true
    }
}
~~~

**When the input is empty:** `reduce(0L, Long::sum)` returns `0L`; `collect(toList())` returns an empty list; `groupingBy` returns an empty Map; `collect(ArrayList::new, ...)` returns an empty ArrayList. An empty result is a **valid rule of the APIs**, though the business system still needs to decide whether "no payments" should be treated as a value of 0 or a state reported separately.

**Self-check questions:**

1. Why is summing numbers with `reduce` considered a non-mutating reduction? — The accumulator produces a **new numeric value**, without mutating an accumulation container.
2. Why does `collect` allow `ArrayList::add` even when using a parallel Stream? — The normal collector mechanism uses **independent containers** and then merges them; it does not use a shared external list.
3. Can `Supplier` return the same shared `ArrayList` on every call? — **No**, because that breaks container independence.
4. If a Collector has a finisher returning `List.copyOf(container)`, is it still a mutable reduction? — **Yes**, because the intermediate state is still updated mutably.
5. How do the two `reduce` overloads differ on an empty Stream? — With identity it returns the identity; without identity it returns `Optional.empty()`.
6. Is `CONCURRENT` synonymous with `parallelStream()`? — **No**; one is a collector characteristic, and the other is a pipeline execution mode.
7. If the source is infinite, does `collect(toList())` stop on its own? — **No**, unless there is an appropriate limiting step or condition beforehand.

## 15. Takeaways for choosing the right tool

**Use `reduce`** when the result can be built by combining **values** via an operation with a proper identity and associativity, such as a sum, product, or immutable record. **Use `collect`** when you need to build a **container** like a `List`, `Map`, `Set`, or stateful statistics object, which can then use a finisher to produce the final result per contract.

Both are terminal operations and can participate in declarative, lazy pipelines before completion. When dealing with large datasets or parallel processing, it is crucial to obey the contracts on **state**, **associativity**, **independent containers**, **ordering**, **resources**, and **result merging overhead**.

Understanding the boundary between **non-mutating reduction** and **mutable reduction** helps you choose the right API, write safe custom collectors, and understand how the Java Stream API scales to grouping, concurrent processing, `Spliterator`, and Stream Gatherers.
