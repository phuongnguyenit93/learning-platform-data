# Collector's supplier, accumulator, combiner, and finisher Components

> **Chapter:** Collect Mechanism and Collector  
> **Module:** JAVA_STREAM_API  
> **Goal:** Understand the role, types, and contracts of the four components in `Collector<T, A, R>`; build a correct collector for sequential and parallel pipelines; know when to use built-in collectors.

In **JAVA_STREAM_API**, we use lazy pipelines with `filter`, `map`, and intermediate operations to describe how elements are transformed. When we need to put processed elements into a list, map, statistical report, or custom structure, a common terminal operation is **`collect(...)`**.

A `Collector` describes how to **accumulate multiple elements into a result**. It accomplishes this with four components: **`supplier`** creates an accumulation container; **`accumulator`** inserts an element into it; **`combiner`** merges accumulation containers; **`finisher`** transforms the accumulated state into the final result. These components are especially important when a Stream executes in parallel and Java can partition the data into multiple chunks.

This lesson focuses on the **contract among the four components**. After mastering this model, using `Collectors.groupingBy`, `mapping`, `reducing`, custom collectors, `Spliterator`, and Stream Gatherers will be easier to reason about. At the same time, learners gain a basis for identifying bugs related to mutable state, ordering, resources, and performance.

The examples run on **Java 17+**; `Collector` and `Collector.of` themselves have been available since Java 8. Some examples use `record` (Java 16+) and `Stream.toList()` (Java 16+).

## 1. Where does Collector sit in a pipeline?

Consider a sales data source:

```java
record Sale(String category, long amount) {}

List<Sale> sales = List.of(
    new Sale("Sách", 120_000),
    new Sale("Thiết bị", 200_000),
    new Sale("Sách", 80_000)
);
```

To compute the total amount of valid transactions by category:

```java
Map<String, Long> revenue = sales.stream()
    .filter(sale -> sale.amount() > 0)
    .collect(Collectors.groupingBy(
        Sale::category,
        Collectors.summingLong(Sale::amount)
    ));
```

`filter` is an **intermediate** operation: it describes a condition. `collect` is a **terminal** operation: it triggers pipeline evaluation and returns a `Map<String, Long>`. In the example, `groupingBy` and `summingLong` are factory methods that create Collectors; they hide the accumulation details so we only need to state the business intent.

When designing a Collector ourselves, we must make the internal process explicit:

```text
                  Stream<Sale>
                       │
                       ▼
                collect(collector)
                       │
                  supplier()
                       ▼
               A: accumulation area
                       │
           accumulator(A, Sale)
                  many times
                       ▼
               A: accumulated
                       │
              [if work is split]
                       │
            combiner(A1, A2)
                       ▼
                A: combined
                       │
                  finisher(A)
                       ▼
                  R: result
```

Here **`A` does not have to be the same as `R`**. For example, `A` can be a mutable object holding a counter and a sum, while `R` is a read-only record containing the final statistics.

The diagram is a logical model, **not a guarantee about the number of calls or order of function invocations**. Java may use one accumulation container or many depending on the source, collector, and execution mode. A collector with special characteristics may also accumulate concurrently into the same container.

## 2. Generic type Collector<T, A, R>

The `java.util.stream.Collector` interface has three type parameters:

| Parameter | Meaning | Example |
| --- | --- | --- |
| `T` | Type of **each input element** from the Stream | `Sale` |
| `A` | **Intermediate accumulation type** | `SalesAccumulator` |
| `R` | **Return result type** after collect | `SalesSummary` |

The key methods of the interface have the following concise signatures:

```java
Supplier<A> supplier();

BiConsumer<A, T> accumulator();

BinaryOperator<A> combiner();

Function<A, R> finisher();

Set<Collector.Characteristics> characteristics();
```

The first four components contribute directly to data gathering. The fifth method publishes the **characteristics** that the framework is permitted to rely on, such as `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT`.

For example, an explicit declaration:

```java
Collector<String, StringJoiner, String> joining = Collector.of(
    () -> new StringJoiner(", "),
    StringJoiner::add,
    StringJoiner::merge,
    StringJoiner::toString
);
```

- `T = String`: the input elements.
- `A = StringJoiner`: where strings are accumulated.
- `R = String`: the result after calling `toString()`.

The snippet requires importing `java.util.StringJoiner` and `java.util.stream.Collector`. In many situations, we only need to store the variable as type `Collector<T, ?, R>` because there is no need to expose the intermediate state type `A` to callers.

## 3. Supplier: creating a new accumulation container

**Supplier** is a function that takes no parameters and returns an object of type `A`:

```java
Supplier<A> supplier();
```

Its job is to provide an **appropriate initial state** for each accumulation container that the `collect` process needs to create.

Easy-to-understand example:

```java
Supplier<ArrayList<String>> supplier = ArrayList::new;

ArrayList<String> first = supplier.get();
ArrayList<String> second = supplier.get();

System.out.println(first == second); // false
```

Each call creates a new list. For a Collector, the supplier must not return the same mutable list stored in a global variable across every use.

### 3.1. Why must the supplier create independent state?

When running in parallel, the framework may split a source into multiple parts. Each part can use its own accumulator, then merge them:

```text
Source part 1                   Source part 2
    │                               │
supplier()                      supplier()
    │                               │
    ▼                               ▼
  empty A1                        empty A2
    │                               │
accumulate                       accumulate
    │                               │
    ▼                               ▼
 A1 with data                    A2 with data
    └────────── combiner ───────────┘
                    │
                    ▼
                 total A
```

If the supplier repeatedly returns **the same mutable object**, data can be overwritten/duplicated, violate ownership boundaries, or cause race conditions. This is a contract bug, even if a small sequential test has not exposed the issue yet.

**Wrong:**

```java
List<String> shared = new ArrayList<>();

Collector<String, List<String>, List<String>> broken = Collector.of(
    () -> shared, // All accumulation areas share the same list.
    List::add,
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
```

**Correct:**

```java
Collector<String, List<String>, List<String>> collector = Collector.of(
    ArrayList::new, // Each call creates a new list.
    List::add,
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
```

The example uses `java.util.List`, `java.util.ArrayList`, and `java.util.stream.Collector`. When designing a normal collector, treat the accumulation container as a resource **belonging to a single `collect` execution**, without keeping it in an external shared variable.

### 3.2. Empty state must act as an identity element

The value created by the supplier must be compatible with the combiner. If `a` is an accumulated state, merging an empty state into it must be equivalent to `a`:

```text
combine(a, supplier())  ≈  a
```

Examples:

- Total amount: new state has `sum = 0`.
- Element count: new state has `count = 0`.
- List: new state is an empty list.
- Joined string: new state is an empty `StringJoiner`.

The `≈` symbol means **equivalent according to the Collector result**, not necessarily the same object reference.

## 4. Accumulator: putting each element into the state

**Accumulator** is a `BiConsumer<A, T>`:

```java
BiConsumer<A, T> accumulator();
```

It accepts two parameters: an accumulation container `A` and an input element `T`, then updates that accumulation container.

Example of summing and counting:

```java
static final class MutableStats {
    long count;
    long total;
}

BiConsumer<MutableStats, Long> addAmount = (stats, amount) -> {
    stats.count++;
    stats.total += amount;
};
```

When applied:

```java
MutableStats stats = new MutableStats();
addAmount.accept(stats, 100L);
addAmount.accept(stats, 200L);

// stats.count = 2
// stats.total = 300
```

This snippet assumes the declarations sit inside a Java class; `MutableStats` and `addAmount` illustrate the roles of `A` and `T`.

### 4.1. Accumulator typically updates A, rather than returning A

Unlike `reduce`, which uses a value-returning combining function, `Collector.accumulator()` returns a `BiConsumer`, whose `accept` method has return type `void`. Thus mutable collectors typically **mutate the contents of object `A`**.

```java
BiConsumer<List<String>, String> append =
    (list, item) -> list.add(item);
```

The lambda above is valid even though `List.add` returns `boolean`, because it is a statement expression and the return value is ignored in a `void` context.

Do not do this:

```java
List<String> outside = new ArrayList<>();

BiConsumer<List<String>, String> wrong =
    (current, item) -> outside.add(item);
```

This function ignores the `current` parameter and writes to external state. When the framework creates multiple accumulators, the data will not be in the containers needed for `combiner` to merge.

### 4.2. An element must be counted exactly once in accumulation logic

For a counter and sum, each valid element typically contributes:

```java
void add(Sale sale) {
    count++;
    total += sale.amount();
}
```

The example assumes this is a method of an accumulator class with `count` and `total` fields, using the `Sale` type introduced in section 1.

If the input needs invalid data filtered out, you can filter before `collect`:

```java
SalesSummary summary = sales.stream()
    .filter(sale -> sale.amount() > 0)
    .collect(summaryCollector);
```

`summaryCollector` will be declared in the complete example. Clear filtering conditions in the pipeline let the accumulator focus strictly on accumulation. In a custom collector, skipping elements can also be a valid rule, but it must be documented clearly and remain consistent with merging.

### 4.3. Keep the accumulation container in a valid state

Define the **invariants** for `A`. For example: `count >= 0`; `total` is the sum of amounts of the elements seen so far; no element is kept twice unless business logic requires it.

For integers, `long` can overflow. Use `Math.addExact` or a larger numeric type if business rules forbid overflow; however, understand that parallel computation may merge parts in different orders. When you need to guarantee exact results for all data even if intermediate sums exceed limits, use a sufficiently wide representation such as `BigInteger`.

## 5. Combiner: merging two accumulated states

**Combiner** is a `BinaryOperator<A>`:

```java
BinaryOperator<A> combiner();
```

It receives two populated states `A` and returns **an accumulated state equivalent to having processed all elements of both parts**.

Example with a list:

```java
BinaryOperator<List<String>> mergeLists = (left, right) -> {
    left.addAll(right);
    return left;
};
```

Note: `Collector`'s combiner **must return `A`**, unlike the `BiConsumer<R, R>` combiner in the three-argument `Stream.collect` overload.

### 5.1. Why is a combiner needed even when usually running sequentially?

The framework may not need to call the combiner during a sequential collect run. However, for a Collector to work properly when partitioned, the combiner must be present and valid.

Suppose a source of four numbers is split:

```text
Left branch            Right branch
[10, 20]               [30, 40]
   │                       │
   ▼                       ▼
A1: sum=30             A2: sum=70
   └──────── combine ───────┘
              │
              ▼
        A: sum=100
              │
              ▼
        finisher → 100
```

Combiner for statistics:

```java
static final class MutableStats {
    long count;
    long total;

    MutableStats merge(MutableStats other) {
        this.count += other.count;
        this.total += other.total;
        return this;
    }
}
```

If `other.total` or `other.count` is omitted, parallel results will lose data even though sequential examples may still pass.

### 5.2. Truly merge, don't just return one branch

**Wrong:**

```java
(left, right) -> left // Loses the data in right.
```

**Correct:**

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

The correct form is for an accumulator of type `List<T>`. For multi-field statistics, **every field contributing to the result** must be merged.

Once a container has been passed to the combiner or finisher, Collector rules restrict continuing to reuse that container. Do not save an accumulator reference externally and mutate it after collect finishes.

### 5.3. Associativity and ordering

The Collector contract requires the merge operation to satisfy **associativity of results**:

```text
combine(combine(A, B), C)
              ≈
combine(A, combine(B, C))
```

Both sides must produce equivalent results after `finisher` is applied, because the framework may choose different merge trees.

For integer sums within representable bounds, addition satisfies the condition. For ordered lists, list concatenation is also associative **as long as left-branch then right-branch order is preserved**.

Not just any operation is valid. For example, taking the **unweighted average of two averages** fails when the two parts have different element counts:

```text
Branch A: [10, 20]  → average = 15, count = 2
Branch B: [90]      → average = 90, count = 1

Wrong:   (15 + 90) / 2 = 52.5
Correct: (10 + 20 + 90) / 3 = 40
```

For averaging problems, the accumulator should store **`sum` and `count`**; the combiner adds the two sums and two counts; only the finisher divides. This example shows how the design of type `A` determines correctness.

**Note:** `double` addition has rounding errors and is not strictly bitwise associative. Thus floating-point results can differ slightly when addition order changes, especially in parallel runs. Do not use exact equality between two `double` results as a general standard.

## 6. Finisher: converting A into R

**Finisher** is a `Function<A, R>`:

```java
Function<A, R> finisher();
```

It takes the completed accumulated state and produces **the result the caller needs**.

Example where state holds two fields and the result is a record:

```java
record Summary(long count, long total) {}

static final class MutableStats {
    long count;
    long total;
}

Function<MutableStats, Summary> finish =
    stats -> new Summary(stats.count, stats.total);
```

Here `A = MutableStats` is a mutable type, while `R = Summary` is a record with final fields. The caller receives a simple result record instead of a mutable accumulation container.

### 6.1. Finisher can leave A unchanged

Sometimes the final result is the accumulation container itself:

```java
Collector<String, ArrayList<String>, ArrayList<String>> toArrayList =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

The three-component overload of `Collector.of` creates a collector with an **identity finisher**: `A` and `R` are the same type, and the final result is the accumulation container itself.

This differs from returning an unmodifiable list:

```java
Collector<String, ArrayList<String>, List<String>> toImmutableList =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        List::copyOf
    );
```

In the second example, `A = ArrayList<String>`, `R = List<String>`, and the finisher creates an unmodifiable list using `List.copyOf`. That method does not accept `null` elements, so sources containing `null` will need a separate handling policy.

### 6.2. Do not use finisher for mandatory side effects

When a Collector has `IDENTITY_FINISH`, the framework is allowed to skip calling the finisher function. The number of times or timing of internal step evaluations must also not be used to trigger business actions beyond creating the result.

Avoid relying on the finisher to send notifications, write payment logs, or mutate an external service. If business logic requires an action after collection, perform it **after the `collect` call** based on the received result.

### 6.3. Finisher for aggregated reports

For example, the accumulator stores `sum` and `count`, while the result also needs the average:

```java
record AverageReport(long count, long total, double average) {}

Function<MutableStats, AverageReport> finish = stats ->
    new AverageReport(
        stats.count,
        stats.total,
        stats.count == 0 ? 0.0 : (double) stats.total / stats.count
    );
```

The value `0.0` when `count == 0` is **this example's default rule**, not the mathematical average of an empty set. If the application needs to distinguish an empty set, it can return `OptionalDouble` or a report type that explicitly represents the no-data state.

## 7. Writing a Collector with Collector.of

`Collector.of` provides factory methods for both scenarios:

```java
// A is also R, identity finisher:
Collector.of(supplier, accumulator, combiner, characteristics...);

// A and R can differ:
Collector.of(supplier, accumulator, combiner,
             finisher, characteristics...);
```

Example joining strings using `StringJoiner`:

```java
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

class JoiningCollectorExample {
    public static void main(String[] args) {
        Collector<String, StringJoiner, String> joining = Collector.of(
            () -> new StringJoiner(", "),
            StringJoiner::add,
            StringJoiner::merge,
            StringJoiner::toString
        );

        String text = Stream.of("An", "Bình", "Chi")
            .collect(joining);

        System.out.println(text); // An, Bình, Chi
    }
}
```

Analysis:

| Component | Expression | Meaning |
| --- | --- | --- |
| Supplier | `() -> new StringJoiner(", ")` | Creates an accumulation container with a delimiter. |
| Accumulator | `StringJoiner::add` | Adds a string to the current container. |
| Combiner | `StringJoiner::merge` | Joins the contents of two accumulation containers. |
| Finisher | `StringJoiner::toString` | Produces the `String` result. |

In real projects, `Collectors.joining(", ")` is built in and usually the better choice. Writing the collector manually here illustrates the internal contract.

### 7.1. When should you use Collector.of?

`Collector.of` is useful when:

- You need a custom result containing multiple statistics.
- You need to merge data according to business rules that cannot be conveniently expressed with standard collectors.
- You need explicit control over accumulation state, merging, final result, or immutability policy.
- You need to reuse the accumulation logic across multiple pipelines or as a downstream collector for `groupingBy`.

If `Collectors.toList`, `toCollection`, `joining`, `groupingBy`, `summingLong`, or `summarizingInt` already meet the requirements, prefer them to reduce code maintenance.

## 8. Complete example: revenue report Collector

Problem: each transaction has a category and an amount. We need the total number of transactions and total revenue; then reuse the same Collector to aggregate statistics per category.

We design:

- `T = Sale`: input data.
- `A = Metrics`: mutable container with `count` and `total`.
- `R = SalesReport`: field-immutable record containing only the result.

Save the example below into `CollectorContractDemo.java` and run on Java 17+:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class CollectorContractDemo {
    record Sale(String category, long amount) {}
    record SalesReport(long count, long total) {}

    static final class Metrics {
        private long count;
        private long total;

        // ACCUMULATOR: accumulates a single Sale element.
        void add(Sale sale) {
            count = Math.addExact(count, 1L);
            total = Math.addExact(total, sale.amount());
        }

        // COMBINER: merges data from another accumulation container.
        Metrics merge(Metrics other) {
            count = Math.addExact(count, other.count);
            total = Math.addExact(total, other.total);
            return this;
        }

        // FINISHER: converts intermediate state into the result.
        SalesReport finish() {
            return new SalesReport(count, total);
        }
    }

    static Collector<Sale, Metrics, SalesReport> reportCollector() {
        return Collector.of(
            Metrics::new,     // SUPPLIER
            Metrics::add,     // ACCUMULATOR
            Metrics::merge,   // COMBINER
            Metrics::finish   // FINISHER
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("Sách", 120_000),
            new Sale("Thiết bị", 200_000),
            new Sale("Sách", 80_000),
            new Sale("Thiết bị", 150_000)
        );

        Collector<Sale, Metrics, SalesReport> collector =
            reportCollector();

        SalesReport total = sales.stream()
            .collect(collector);

        SalesReport totalParallel = sales.parallelStream()
            .collect(collector);

        Map<String, SalesReport> byCategory = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                collector
            ));

        System.out.println(total);
        // SalesReport[count=4, total=550000]

        System.out.println(totalParallel);
        // SalesReport[count=4, total=550000]

        System.out.println(byCategory);
        // {Sách=SalesReport[count=2, total=200000],
        //  Thiết bị=SalesReport[count=2, total=350000]}
    }
}
```

**Why is this structure mechanically sound?**

1. `Metrics::new` creates an independent state with `count=0` and `total=0`.
2. `Metrics::add` records one `Sale` into the exact state passed to it.
3. `Metrics::merge` merges two states by summing `count` and `total`, then returns the merged state.
4. `Metrics::finish` creates `SalesReport`, sparing the caller from working with a mutable accumulation container.
5. The same **Collector** object can be reused across `collect` calls because each run obtains fresh accumulation containers from the supplier; do not reuse a **Stream** after a terminal operation.

In this example, the data has non-negative amounts and the result fits within `long`. `Math.addExact` detects overflow at each addition step. With very large positive and negative numbers, different merge orders may differ in detecting intermediate overflow; if you need order-independent mathematical summation for arbitrary `long` numbers, use a `BigInteger` accumulator or a sufficiently wide representation.

### 8.1. Tracing two branches of the example

If the framework splits the four transactions into two parts:

```text
Part 1:
  Sách 120000
  Thiết bị 200000
  → Metrics(count=2, total=320000)

Part 2:
  Sách 80000
  Thiết bị 150000
  → Metrics(count=2, total=230000)

combiner:
  count = 2 + 2 = 4
  total = 320000 + 230000 = 550000

finisher:
  SalesReport(count=4, total=550000)
```

This is **one possible partitioning**, not a rule that the Stream must create exactly two branches or call the combiner exactly once.

### 8.2. Using the collector as downstream of groupingBy

`Collectors.groupingBy(Sale::category, TreeMap::new, collector)` uses classifier `Sale::category` to pick the group, then applies our collector to each group.

The benefit is separating two concerns:

- **Which group?** Decided by `groupingBy`.
- **How does each group accumulate?** Decided by our `collector`.

Thus a well-written custom collector composes easily with standard collectors, instead of having to rebuild all grouping, map, and counter logic manually.

## 9. Correctness contract: identity, associativity, and equivalence

A Collector cannot be considered correct merely because it returns the right result for a small sequential Stream. Java allows **splitting the source**, accumulating partially, and **merging along different trees**. Therefore the components must obey the contract.

### 9.1. Identity constraint

An empty accumulation container created by `supplier` must not change the result when merged:

```text
a = a valid state after accumulation
empty = supplier.get()

finisher(combiner(a, empty)) ≈ finisher(a)
```

If a collector concatenates lists in order, `combiner(a, empty)` must preserve the exact element sequence in `a`.

Wrong example:

```java
// Wrong: supplier initializes count=1, which can overcount when work is split.
Supplier<MutableStats> wrongSupplier = () -> {
    MutableStats stats = new MutableStats();
    stats.count = 1;
    return stats;
};
```

### 9.2. Associativity constraint

The result must be equivalent regardless of how data chunks are grouped, provided any ordering guarantees required by the collector are respected:

```text
finisher(combine(combine(A, B), C))
                  ≈
finisher(combine(A, combine(B, C)))
```

For counts and sums, merging partial results via addition is valid within the appropriate representation range. For ordered sequences, the combiner must concatenate data in the right direction; swapping to `right + left` in one branch produces a wrong result even though it still "included all elements".

### 9.3. Sequential and parallel results must be equivalent

For the same input, the results from:

```java
R sequential = data.stream().collect(collector);
R parallel = data.parallelStream().collect(collector);
```

must be equivalent per the Collector contract, assuming the data, accumulation functions, and operations satisfy the required conditions. This snippet is **general notation**; in a real program you must declare `data`, `collector`, and type `R`.

If the collector has `UNORDERED`, equivalence allows element encounter order not to matter. If the collector requires preserving order, the combiner and result must respect that order.

### 9.4. Do not let logic depend on invocation counts

The framework does not guarantee that:

- `supplier` is called only once.
- `accumulator` runs on only one thread.
- `combiner` is always called or called an expected number of times.
- An element is processed in chronological order matching input order when the pipeline runs in parallel.

Design a Collector based on **result semantics**, not on logging or counting internal function invocations.

## 10. The three Characteristics and their exact meanings

`Collector.Characteristics` is an enum describing guarantees that the framework can exploit:

| Characteristic | Meaning | Pitfall to avoid |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher is the identity function: type `A` can be used directly as `R`. | Do not declare if finisher makes a copy, transforms, or returns a different type. |
| `UNORDERED` | The Collector result does not depend on preserving the source's *encounter order*. | Do not declare for lists where element order matters. |
| `CONCURRENT` | Accumulator can be called concurrently on the same accumulation container while remaining correct. | Do not declare for `ArrayList` or unsynchronized mutable `long` counters. |

These characteristics **are contracts**, not "speedup" switches.

### 10.1. IDENTITY_FINISH

With the `Collector.of(supplier, accumulator, combiner)` overload, an identity finisher is provided implicitly. In the `Metrics → SalesReport` example, the finisher converts from a mutable class to a record, so `IDENTITY_FINISH` is **not** declared.

Even when `A` and `R` have the same declared type, you must not declare `IDENTITY_FINISH` if the finisher performs actual work, such as creating an unmodifiable copy.

### 10.2. UNORDERED does not mean elements are randomly shuffled

If the result is only a sum or count and does not depend on order, a collector **may** declare `UNORDERED` if its components actually satisfy the contract.

For example, with a `List<String>` result that must be displayed in input order, you should not declare `UNORDERED`: a list containing all elements in a swapped order is not necessarily business-equivalent.

`UNORDERED` also differs from the `Stream.unordered()` method: one declares a characteristic **of the collector**, while the other drops the encounter-order requirement **of the stream**.

### 10.3. CONCURRENT requires a thread-safe accumulator

`CONCURRENT` allows multiple threads to call the accumulator with **the same result container**. When a concurrent collector lacks `UNORDERED`, concurrent accumulation into the same container is only applied under contract if the Stream itself is also unordered.

An example standard collector is `Collectors.groupingByConcurrent(...)`, which is concurrent and unordered. When working with maps, using `ConcurrentHashMap` does not automatically make logic updating mutable values inside it safe. You must examine the entire update path of the accumulator.

**Important:** omitting `CONCURRENT` **does not mean** your Collector cannot be used with `parallelStream()`. The framework can still create multiple independent containers and merge them with the combiner. The `Metrics` Collector in section 8 uses that exact mechanism.

## 11. Collector.of vs. three-argument Stream.collect

Java has two ways to express accumulation logic directly, with **different** signatures.

### 11.1. Stream.collect takes three functions

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
);
```

Example:

```java
List<String> result = Stream.of("An", "Bình", "Chi")
    .collect(
        ArrayList::new,
        List::add,
        List::addAll
    );
```

Here the combiner is a **`BiConsumer<R,R>` returning `void`**, used to mutate the result container.

### 11.2. Collector.of takes a combiner returning A

```java
Collector<String, ArrayList<String>, ArrayList<String>> toList =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );

ArrayList<String> result = Stream.of("An", "Bình", "Chi")
    .collect(toList);
```

Here the combiner is a **`BinaryOperator<A>`**, which must return the merged container. `Collector.of` can also accept a **finisher** and **characteristics**, making it suitable for packaging into a reusable component and downstream composition.

### 11.3. Primitive streams also have their own collect

`IntStream.collect` has the form:

```java
<R> R collect(
    Supplier<R> supplier,
    ObjIntConsumer<R> accumulator,
    BiConsumer<R, R> combiner
);
```

`LongStream` and `DoubleStream` have variants with `ObjLongConsumer` and `ObjDoubleConsumer`. These APIs handle primitive numbers without wrappers. If you need to use a standard `Collector<T,A,R>` with an `IntStream`, you can convert to `Stream<Integer>` via `boxed()`, though that incurs boxing at the API boundary.

## 12. How do standard Collectors embody these components?

When using built-in collectors, we are still using the four-component model.

| Collector | Conceptual accumulation state | Result | Hint |
| --- | --- | --- | --- |
| `Collectors.toCollection(ArrayList::new)` | Mutable list | An `ArrayList` | When a specific collection type is needed. |
| `Collectors.toList()` | A list accumulation structure | `List<T>` | Makes no specific guarantee on concrete type or mutability. |
| `Collectors.joining(", ")` | String accumulation builder | `String` | Avoids writing a string-joining combiner manually. |
| `Collectors.summingLong(...)` | Numeric sum state | `Long` | `long`-typed sum. |
| `Collectors.summarizingLong(...)` | count/sum/min/max statistics | `LongSummaryStatistics` | Multiple metrics in one pass. |
| `Collectors.groupingBy(...)` | Grouping structure and accumulator per group | `Map<K,D>` | Can compose with a downstream collector. |
| `Collectors.toMap(...)` | Map of keys and values | `Map<K,V>` | Needs a duplicate-key policy when collisions can occur. |
| `Collectors.collectingAndThen(downstream, finisher)` | Downstream's state | Output of the new finisher | Transforms an existing collector's result. |

The table presents the **conceptual accumulation approach**, without asserting the exact internal type `A` of each standard collector; implementations may vary across JDK versions.

### 12.1. collectingAndThen: adding a finisher

Example creating an unmodifiable list:

```java
List<String> immutable = Stream.of("An", "Bình")
    .collect(Collectors.collectingAndThen(
        Collectors.toList(),
        List::copyOf
    ));
```

`Collectors.toList()` accumulates the elements, while `List::copyOf` converts the result into an unmodifiable list. In practice, if you just need an unmodifiable list, `Stream.toList()` (Java 16+) or `Collectors.toUnmodifiableList()` (Java 10+) can also work, noting differences in `null` handling.

Because this added finisher performs real work, you must not assume the resulting new collector has `IDENTITY_FINISH`.

### 12.2. teeing: aggregating two results then finishing

Since Java 12, `Collectors.teeing` can run two collectors and then merge their results:

```java
record Summary(long count, long amount) {}

Summary result = sales.stream()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::amount),
        Summary::new
    ));
```

The example uses `Sale` declared earlier in the lesson. `teeing` holds the results of two statistics branches and applies the merger function at the end. This is a way to use built-in tools to avoid manually writing an accumulator and combiner when the requirement fits.

## 13. Collector and reduce: similarities and differences

`reduce` and `collect` are both terminal operations for aggregating a Stream, but their models differ:

- `reduce` represents combining values via an associative operator, usually aiming for an immutable value or a calculation.
- `collect` typically uses a **mutable accumulation container**, with a dedicated supplier and accumulator; suitable for building collections, maps, or complex statistical structures.

Computing a sum:

```java
long total = sales.stream()
    .mapToLong(Sale::amount)
    .sum();
```

Multi-field statistics:

```java
SalesReport report = sales.stream()
    .collect(reportCollector);
```

Do not use a shared mutable list as the **identity** for `reduce` and append elements directly into that identity. When the Stream is split, multiple branches can reference the same object and break the logic. If the goal is mutable accumulation, use `collect` with a supplier creating new containers.

Risky example:

```java
// Avoid this reduce pattern with a mutable identity:
// List<String> sharedIdentity = new ArrayList<>();
// List<String> result = words.parallelStream().reduce(
//     sharedIdentity,
//     (list, word) -> { list.add(word); return list; },
//     (left, right) -> { left.addAll(right); return left; }
// );
```

`words` in the example is an assumed `Stream<String>` source; the snippet is commented out to illustrate what not to do.

## 14. Correctness first, optimization second: performance and resources

A correct Collector can still consume significant memory or CPU. Complexity depends on state `A`, accumulation method, merge strategy, and result size.

### 14.1. Accumulator memory

- A list holding all elements needs memory proportional to the element count.
- Counters and sums typically need only a fixed amount of state.
- `groupingBy` may require a map with many keys and an accumulator for each group.
- A Collector that creates a copy in its finisher may temporarily hold both the intermediate container and final result.

Choose `A` just big enough to serve `R`. If you only need the total amount, there is no need to store every transaction in a list only to sum them in the finisher.

### 14.2. Combiner cost in parallel streams

With a large source that splits well via `Spliterator` and suitable accumulation work, parallelism can speed things up. However, if the combiner must concatenate huge lists or copy entire maps repeatedly, merging can add significant overhead.

Do not turn on `CONCURRENT` to bypass the combiner when the accumulator is not thread-safe. Nor should you assume `parallelStream` is always faster. Decisions should be based on measurements with realistic data volume, group counts, and collector shape.

### 14.3. I/O resources are not closed automatically by collect

If the source is `Files.lines(path)`, you must close the Stream:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class CollectLinesExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.txt");

        try (Stream<String> lines = Files.lines(path)) {
            List<String> nonBlank = lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .collect(Collectors.toList());

            System.out.println(nonBlank.size());
        }
    }
}
```

The example assumes `data.txt` exists. The `collect` terminal operation does not automatically close the I/O source; `try-with-resources` manages that resource lifecycle.

## 15. Common Collector design mistakes

| Mistake | Why is it dangerous? | How to fix |
| --- | --- | --- |
| Supplier returns a shared list | Accumulations are not independent, risking duplicate data or races. | Create a new container in every supplier call. |
| Accumulator writes to an external variable instead of parameter `A` | Combiner cannot see the proper data from each branch. | Only update the accumulation container passed in. |
| Combiner always returns `left` without merging `right` | Loses data from split partitions. | Merge all fields and return a valid state. |
| Combiner takes an unweighted average of two averages | Result depends on how work was split. | Keep `sum` and `count`, computing the average only in the finisher. |
| Supplier initializes count to 1 | No valid empty identity state. | Start with count=0 and an appropriate identity. |
| Combiner reverses order in an ordered collector | Parallel results can differ from sequential. | Preserve order when concatenating partial results. |
| Declaring `IDENTITY_FINISH` when finisher converts types | Framework may skip the finisher and return the wrong type. | Only declare when it is truly an identity function. |
| Declaring `CONCURRENT` for `ArrayList` or unsynchronized counters | Multiple threads writing to the same container is unsafe. | Use a non-concurrent collector or implement proper concurrent state. |
| Declaring `UNORDERED` even though list order matters | Ordering guarantees can be lost. | Do not declare characteristics not satisfied by the data/logic. |
| Relying on `println` in accumulator/combiner for business decisions | Invocations can happen in different orders and counts. | Perform business actions after collect. |
| Collecting every element into a list only to compute a sum at the end | Unnecessary memory usage. | Keep a `sum` accumulator, or use `summingLong` / `mapToLong(...).sum()`. |
| Processing an I/O source without closing the Stream | Resource leak. | `try-with-resources`. |

## 16. Self-check

1. In `Collector<Sale, Metrics, SalesReport>`, what do types `T`, `A`, and `R` represent respectively?
2. How must `supplier` create state so a collector works properly across multiple accumulation containers?
3. Why does `accumulator` use `BiConsumer<A,T>`, whereas `combiner` uses `BinaryOperator<A>`?
4. If `combiner(a,b)` returns `a` without merging `b`, when does the bug usually surface?
5. Why shouldn't you compute an unweighted average of averages when combining data from multiple branches?
6. When can `finisher` be the identity function? Which characteristic describes this?
7. Can a collector without `CONCURRENT` be used with `parallelStream()`? Why?
8. How do the three-component `Collector.of` and three-argument `Stream.collect` differ in their combiner types?
9. Why does `Collectors.collectingAndThen` typically not have `IDENTITY_FINISH`?
10. Can a Collector automatically close a `Files.lines` source after `collect`?

**Quick check:** (1) element, accumulation state, result; (2) fresh independent state acting as identity; (3) accumulator mutates container, combiner returns the merged container; (4) when data is split, typically in parallel execution; (5) branches can have different element counts; (6) when `A=R` and no transformation is needed, `IDENTITY_FINISH`; (7) yes, the framework uses separate containers and merges them; (8) `BinaryOperator<A>` returning `A` vs. `BiConsumer<R,R>` returning `void`; (9) there is an actual additional finisher; (10) no, file lifecycle must be managed explicitly.

## 17. Practice exercises

**Exercise 1 — Count and sum.** Write `Collector<Integer, ?, Summary>` with `Summary(long count, long sum)`. Use an accumulator class holding count and sum, implementing the four components with `Collector.of`; test with the list `[1, 2, 3, 4]`.

**Exercise 2 — String joining.** Use `StringJoiner` to create a collector joining words with `" | "`. Run on both sequential and parallel Streams, comparing results when the source is an ordered `List`.

**Exercise 3 — Broken combiner.** Replace the counting collector's combiner with `(left, right) -> left`. Explain why the sequential case may give the right answer while parallel may lose elements.

**Exercise 4 — Computing average.** Build an accumulator storing `long count` and `long sum`, with a finisher returning a record containing `OptionalDouble` or a type representing an empty source. Why must both metrics be kept until the end?

**Exercise 5 — Immutable list.** Write a collector using `ArrayList` as `A` and `List.copyOf` as the finisher. Try adding an element to `R` after collect and explain whether the `IDENTITY_FINISH` characteristic is appropriate.

**Exercise 6 — Downstream grouping.** Reuse the collector from Exercise 1 as the downstream of `Collectors.groupingBy` to compute count and sum by even/odd label.

**Exercise 7 — Reviewing characteristics.** With an accumulator of `HashMap<String, Long>` and a combiner merging each key, analyze whether `CONCURRENT` can be declared. What conditions are needed for multiple threads to safely update the same map?

Implementation hint for Exercise 1:

```java
record Summary(long count, long sum) {}

static final class Acc {
    long count;
    long sum;

    void add(int n) {
        count++;
        sum += n;
    }

    Acc merge(Acc right) {
        count += right.count;
        sum += right.sum;
        return this;
    }

    Summary finish() {
        return new Summary(count, sum);
    }
}

Collector<Integer, Acc, Summary> collector = Collector.of(
    Acc::new,
    Acc::add,
    Acc::merge,
    Acc::finish
);
```

The snippet above needs the `record` and `class` declarations placed inside an appropriate Java class; the `collector` variable can live inside a method. For large datasets, consider `long` overflow and error-handling rules.

## 18. Core takeaways

- **`Collector<T,A,R>`** describes how to turn many elements of type `T` into a result `R` through an intermediate state `A`.
- **`supplier`** creates a new accumulation container whose initial state serves as the identity; **`accumulator`** adds each element into that container.
- **`combiner`** merges two accumulation containers and must preserve all contributions from every branch; merging must be **associative with respect to the result**.
- **`finisher`** converts state `A` into result `R`; when `A` itself is `R` and no conversion is needed, the collector may have `IDENTITY_FINISH`.
- **`UNORDERED` and `CONCURRENT`** are genuine guarantees about semantics and thread-safety, not speedup tricks.
- **`Collector.of` and the three-argument overload of `Stream.collect`** use combiners with different signatures; do not swap them directly while ignoring return-type differences.
- **A correct collector must behave equivalently when splitting and merging data**. Do not rely on internal function call counts, do not use a mutable variable outside the pipeline as a shared accumulator, and do not declare characteristics without justification.
- Prefer **built-in `Collectors`** when they meet requirements; write custom collectors when custom state or results are needed. Optimizing memory, parallel execution, and resource management must follow source contracts, `Spliterator`, and actual collection operations in **JAVA_STREAM_API**.
