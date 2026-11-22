# Reading the `Collector<T, A, R>` Type and Accumulation State Type

## 1. Why does `collect` need a separate state type?

In **JAVA_STREAM_API**, operations like `filter`, `map`, and `flatMap` describe how to select or transform pipeline elements; the terminal operation `collect` turns many elements into a structured result. That result can be a list, set, grouped map, statistics, or a domain object.

For instance, suppose we want total amount by region from a `Stream<Order>`:

```java
Map<String, Long> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

Here, the input element is `Order`, while the result is `Map<String, Long>`. During execution, the collector may need a storage area to track groups and temporary sums. **That storage type does not have to match the element type or the final result type.**

This is why the `Collector` interface has **three type parameters**:

```java
Collector<T, A, R>
```

- **`T` (input)**: the element type the collector receives from the stream.
- **`A` (accumulation)**: the *mutable accumulation state* type used during collection.
- **`R` (result)**: the result type returned by the terminal operation.

Goals after this lesson:

1. Read `Collector<T, A, R>` and `Stream.collect` signatures accurately.
2. Understand the five components: `supplier`, `accumulator`, `combiner`, `finisher`, and `characteristics`.
3. Distinguish **`A` as internal state** from **`R` as public result**.
4. Read the types of `Collectors.toList`, `groupingBy`, `mapping`, and downstream collectors.
5. Build a custom collector with an immutable result and valid merging.
6. Analyze correctness conditions when the stream is split for parallel processing, as well as limits on resources, state, and performance.

The complete examples in this lesson use **Java 17+**, due to `record` and `Stream.toList()`. Most of the `Collector` mechanism has existed since Java 8; check the API `Since` section if your project uses an older JDK.

## 2. Decoding the `Collector<T, A, R>` signature

The interface is declared in `java.util.stream`:

```java
public interface Collector<T, A, R> {
    Supplier<A> supplier();
    BiConsumer<A, T> accumulator();
    BinaryOperator<A> combiner();
    Function<A, R> finisher();
    Set<Characteristics> characteristics();
}
```

The signature above is simplified for learning, yet accurately reflects the roles of the methods. The functional interfaces `Supplier`, `BiConsumer`, `BinaryOperator`, and `Function` belong to `java.util.function`.

| Symbol | Where is it used? | How to read it? |
| --- | --- | --- |
| `T` | `BiConsumer<A,T>` | Each input element, e.g., `Order` |
| `A` | `Supplier<A>`, `BiConsumer<A,T>`, `BinaryOperator<A>` | State that the collector creates, updates, and merges |
| `R` | `Function<A,R>` | Final data handed to the caller |
| `Supplier<A>` | `supplier()` | Creates a new, initially empty accumulation state |
| `BiConsumer<A,T>` | `accumulator()` | Incorporates one `T` into state `A` |
| `BinaryOperator<A>` | `combiner()` | Merges two `A` states into one `A` |
| `Function<A,R>` | `finisher()` | Transforms final state `A` into result `R` |

A collector can use a mutable object to accumulate and then return an immutable object:

```text
                  supplier()
                      │
                      ▼
               A: empty state
                      │
           accumulator(A, T)
                      │
                  many times
                      ▼
               A: full state
                      │
              combiner(A, A)
          (when merging parts)
                      │
                      ▼
                 finisher(A)
                      │
                      ▼
                  R: result
```

**Point to remember:** `A` is the **accumulator** type, not "data array", "element type after `map`", or "return type of `collect`". It can be `ArrayList<T>`, `HashMap<K,V>`, an object holding multiple counters, or another internal type. Callers generally **do not need to know what `A` specifically is**.

## 3. Reading `Stream.collect(Collector)` from outside in

The overload taking a collector on `Stream<T>` has the signature:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

Take `Stream<Order>` as an example:

- `T = Order` is determined by the stream.
- `Collector<? super T, A, R>` is allowed to accept `Order` elements (or a compatible supertype).
- `A` specifies the internal accumulation state.
- `R` is **the return type of `collect` itself**.

A practical reading:

```java
Stream<Order> source = orders.stream();
Map<String, Long> result = source.collect(
    Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    )
);
```

On the `result` line, the compiler infers `R = Map<String, Long>`. Type `A` does not appear in the result variable; it is inferred from the passed-in collector.

Do not confuse `collect` with `map`: `map` is an **intermediate operation**, returning a new stream and executing lazily. `collect` is a **terminal operation**, consuming the pipeline to return an `R`. To get two results from the same collection, open two new streams; you cannot call a terminal operation a second time on a consumed stream.

Reference documentation:

- [`Collector<T,A,R>` — Java 21 Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html)
- [`Stream.collect` — Java 21 Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector))
- [`Collectors` — collector factories](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [Package `java.util.stream` — reduction and parallelism](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)

## 4. Lifecycle of state `A`

### 4.1. `supplier` creates the accumulator

`Supplier<A>` returns a fresh `A` in its initial state. Usually this is an empty container, for example:

```java
Supplier<ArrayList<String>> supplier = ArrayList::new;
ArrayList<String> left = supplier.get();
ArrayList<String> right = supplier.get();
```

`left` and `right` are **two independent states**; during parallel processing, the library can create many states and merge them. A supplier should never return the same global mutable `ArrayList` across every call.

### 4.2. `accumulator` puts an element into `A`

`BiConsumer<A,T>` receives state `A` and element `T`; its return type is `void`. When accumulating a list:

```java
BiConsumer<ArrayList<String>, String> accumulator =
    ArrayList::add;

accumulator.accept(left, "Java");
accumulator.accept(left, "Stream");
// left = ["Java", "Stream"]
```

Standard collectors are designed around **mutable reduction**: the accumulator updates the managed container, avoiding recreating the entire container for each element. Even though the state is mutable, preceding `filter`/`map` steps must still be non-interfering with the source and stateless.

### 4.3. `combiner` merges states

`BinaryOperator<A>` takes **two `A`s** and returns **one `A`** representing the merged result:

```java
BinaryOperator<ArrayList<String>> combiner = (a, b) -> {
    a.addAll(b);
    return a;
};

ArrayList<String> combined = combiner.apply(left, right);
```

Merging must not drop data; associativity and compatibility with the accumulator are crucial when the pipeline splits into multiple branches. A collector can be executed with multiple `A` instances even when the programmer sees only one `collect` call.

### 4.4. `finisher` produces `R`

A collector can maintain an `ArrayList<T>` during processing and then return an unmodifiable copy:

```java
Function<ArrayList<String>, List<String>> finisher = List::copyOf;

List<String> result = finisher.apply(combined);
```

In this example:

```text
T = String
A = ArrayList<String>
R = List<String>
```

`List.copyOf` disallows `null` elements. This is a data-contract decision, not a default property of every collector. Even if `A` and `R` are the same type, the finisher can still perform real work such as copying; only when the finisher **is truly the identity operation by contract** can the `IDENTITY_FINISH` characteristic be attached.

### 4.5. `characteristics` describes the collector's guarantees

Characteristics belong to `Collector.Characteristics` and affect how the Stream framework may perform collection. The three key values are `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH`; they will be analyzed in section 10.

## 5. Why does `A` often appear as `?`?

Built-in collectors usually **hide the accumulation type** in their public signatures. For example:

```java
// Simplified factory method signatures:
<T> Collector<T, ?, List<T>> toList()

<T> Collector<T, ?, Set<T>> toSet()

<T> Collector<T, ?, Long> counting()
```

The `?` symbol in the second position does not mean the collector "needs no state". It means **the caller does not know and does not need to depend on the actual `A` type**. During execution, the library can still create an accumulator, update it, merge it, and finish it.

Example:

```java
List<String> names = Stream.of("An", "Bình", "Chi")
    .collect(Collectors.toList());
```

We know `T = String` and `R = List<String>`. You should not infer from the signature that `A` is definitely `ArrayList<String>`, or that the result is a mutable `ArrayList`. The Javadoc of `Collectors.toList()` makes **no guarantees** on the collection type, mutability, serializability, or thread-safety of the returned list.

Comparison:

| Collection method | Contract |
| --- | --- |
| `stream.toList()` (JDK 16+) | Unmodifiable list; no guarantee on implementation class |
| `stream.collect(Collectors.toList())` | No guarantee on mutability or implementation class |
| `stream.collect(Collectors.toUnmodifiableList())` (JDK 10+) | Unmodifiable list; rejects `null` elements |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Creates a new `ArrayList` via the specified supplier |

Choose the method based on the desired contract, rather than guessing the internal type `A`.

## 6. Complete example: custom collector `Order → RevenueAccumulator → Summary`

Suppose an application needs **order count** and **total revenue** in a single collection pass. The public result will be an immutable `record Summary`; the intermediate state uses a mutable object to accumulate.

Diagram:

```text
T = Order
    ├── Order("HN", 120_000)
    ├── Order("HCM", 80_000)
    └── Order("HN", 100_000)
             │
             ▼
A = RevenueAccumulator
    count = 3
    totalVnd = 300_000
             │  finisher
             ▼
R = Summary(count=3, totalVnd=300_000)
```

Complete code running on **JDK 17+**:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collector;

public class RevenueCollectorDemo {

    public record Order(String region, long amountVnd) {
        public Order {
            Objects.requireNonNull(region, "region");
            if (region.isBlank() || amountVnd < 0) {
                throw new IllegalArgumentException("Invalid Order");
            }
        }
    }

    public record Summary(long count, long totalVnd) {}

    // A: internal state; callers do not need to know this class.
    private static final class RevenueAccumulator {
        long count;
        long totalVnd;

        void add(Order order) {
            count = Math.addExact(count, 1L);
            totalVnd = Math.addExact(totalVnd, order.amountVnd());
        }

        RevenueAccumulator merge(RevenueAccumulator other) {
            count = Math.addExact(count, other.count);
            totalVnd = Math.addExact(totalVnd, other.totalVnd);
            return this;
        }

        Summary finish() {
            return new Summary(count, totalVnd);
        }
    }

    public static Collector<Order, ?, Summary> revenueCollector() {
        return Collector.of(
            RevenueAccumulator::new,  // Supplier<A>
            RevenueAccumulator::add,  // BiConsumer<A, Order>
            RevenueAccumulator::merge, // BinaryOperator<A>
            RevenueAccumulator::finish // Function<A, Summary>
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("HN", 120_000L),
            new Order("HCM", 80_000L),
            new Order("HN", 100_000L)
        );

        Summary sequential = orders.stream()
            .collect(revenueCollector());
        Summary parallel = orders.parallelStream()
            .collect(revenueCollector());

        System.out.println(sequential);
        // Summary[count=3, totalVnd=300000]
        System.out.println(parallel.equals(sequential)); // true

        Summary empty = List.<Order>of().stream()
            .collect(revenueCollector());
        System.out.println(empty);
        // Summary[count=0, totalVnd=0]
    }
}
```

### 6.1. Tracking `T`, `A`, `R` accurately

| Component | Type in example | Role |
| --- | --- | --- |
| Source element | `Order` | `T` |
| `RevenueAccumulator::new` | `Supplier<RevenueAccumulator>` | Creates empty `A` |
| `RevenueAccumulator::add` | `BiConsumer<RevenueAccumulator,Order>` | Updates `A` with `T` |
| `RevenueAccumulator::merge` | `BinaryOperator<RevenueAccumulator>` | Merges two `A`s |
| `RevenueAccumulator::finish` | `Function<RevenueAccumulator,Summary>` | Converts `A` to `R` |
| Final result | `Summary` | `R` |

The `revenueCollector()` method has public return type `Collector<Order, ?, Summary>`. The `?` **hides the `RevenueAccumulator` class as an implementation detail**, while the `collect(revenueCollector())` call is still type-checked by the compiler and returns `Summary`.

### 6.2. Why does mutable state here still work with `parallelStream`?

In the collector above, each `RevenueAccumulator` state is created fresh by the supplier and managed by the Stream framework. The collector **does not declare `CONCURRENT`**, so the framework will not accumulate concurrently from multiple threads onto **the same container `A`**. Separate containers can be processed concurrently, then merged by the combiner.

That differs from declaring a shared mutable variable and mutating it inside `map` or `forEach`. Collector splitting/merging is part of the `collect` protocol.

`Math.addExact` helps detect `long` overflow; since the example only accepts non-negative amounts, every partial sum never exceeds the true source total, and if the true total fits within `long`, no valid partial addition overflows. With sources that can contain negative numbers or rounding rules, associativity and order-independence of the result must be examined further.

### 6.3. Why not attach `IDENTITY_FINISH`?

`RevenueAccumulator` and `Summary` are **two different types**; `finish()` also constructs a record. Attaching `IDENTITY_FINISH` would misstate the contract, potentially allowing the framework to skip the finisher and cause an invalid result type. The collector above passes no characteristics, so the finisher must be invoked to create `Summary`.

## 7. Two overloads of `Collector.of`

`Collector.of` has two key factory forms:

**Identity finish form:**

```java
static <T, R> Collector<T, R, R> of(
    Supplier<R> supplier,
    BiConsumer<R, T> accumulator,
    BinaryOperator<R> combiner,
    Collector.Characteristics... characteristics
)
```

In this form, **`A = R`**, and the result is the accumulation container itself under the identity-finish contract. The factory adds `IDENTITY_FINISH` for this form.

**Form with separate finisher:**

```java
static <T, A, R> Collector<T, A, R> of(
    Supplier<A> supplier,
    BiConsumer<A, T> accumulator,
    BinaryOperator<A> combiner,
    Function<A, R> finisher,
    Collector.Characteristics... characteristics
)
```

In the second form, `A` and `R` can differ; a finisher function must be provided. This is the overload used in the revenue statistics example.

Example creating a modifiable list with the first overload:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Stream;

Collector<String, ArrayList<String>, ArrayList<String>> mutableListCollector =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );

ArrayList<String> names = Stream.of("An", "Bình")
    .collect(mutableListCollector);
names.add("Chi"); // Valid.
```

Example creating an immutable list with the finisher overload:

```java
Collector<String, ArrayList<String>, List<String>> immutableListCollector =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        List::copyOf
    );

List<String> immutableNames = Stream.of("An", "Bình")
    .collect(immutableListCollector);
// immutableNames.add("Chi"); // UnsupportedOperationException.
```

In the second example `A = ArrayList<String>`, `R = List<String>`. Although both hold strings, the accumulation container is kept distinct from the final result so callers cannot continue modifying it through mutable list methods.

For business logic needing only an unmodifiable list, APIs such as `Stream.toList()` or `Collectors.toUnmodifiableList()` are usually simpler. Writing a custom collector makes sense when you need a specialized accumulation or result type that standard collectors do not express well.

## 8. Reading nested collectors in `groupingBy`

To understand generics of `groupingBy` with a downstream collector, look at the simplified signature:

```java
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)
```

Reading the types:

- `T`: input element of the **entire** pipeline.
- `K`: group key type produced by `classifier`.
- `A`: accumulation state **of the downstream collector**.
- `D`: result produced by the downstream collector **for each group**.
- `Map<K,D>`: overall result type of the grouping collector.
- `?` in `Collector<T, ?, Map<K,D>>`: the accumulator type **of the grouping collector itself** is hidden; it does not necessarily equal the downstream's `A`.

Example:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<RevenueCollectorDemo.Order> orders = List.of(
    new RevenueCollectorDemo.Order("HN", 120_000L),
    new RevenueCollectorDemo.Order("HCM", 80_000L),
    new RevenueCollectorDemo.Order("HN", 100_000L)
);

Map<String, Long> totals = orders.stream()
    .collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region,
        Collectors.summingLong(
            RevenueCollectorDemo.Order::amountVnd
        )
    ));

System.out.println(totals.get("HN"));  // 220000
System.out.println(totals.get("HCM")); // 80000
```

We deduce `T = Order`, `K = String`, `D = Long`, so the return type is `Map<String,Long>`. There is no need to guess what type the collector used to hold temporary sums. Internally, grouping may manage a map of **unfinished downstream states**, then finish each group to produce `Map<K,D>`.

If you need a `Map<String, List<Order>>` result, omitting the downstream collector works too:

```java
Map<String, List<RevenueCollectorDemo.Order>> byRegion = orders.stream()
    .collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region
    ));
```

### 8.1. Combining custom collector with grouping

The `revenueCollector()` collector in section 6 outputs `Summary`, so it can be reused directly as a downstream collector:

```java
Map<String, RevenueCollectorDemo.Summary> summaryByRegion =
    orders.stream().collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region,
        RevenueCollectorDemo.revenueCollector()
    ));

System.out.println(summaryByRegion.get("HN"));
// Summary[count=2, totalVnd=220000]
```

This example clearly illustrates **two layers of accumulation**: the outer collector groups by `K = String`; the inner collector accumulates `Order`s into a `Summary` for each group. The downstream's `A` type never needs to leak outside.

### 8.2. `mapping`, `filtering`, and `collectingAndThen`

Other factories also accept a downstream collector:

```java
// Simplified meaning:
Collectors.mapping(mapper, downstream)
Collectors.filtering(predicate, downstream) // JDK 9+
Collectors.collectingAndThen(downstream, finisher)
```

For example, needing a list of **amounts** per region instead of full order lists:

```java
Map<String, List<Long>> amountsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        RevenueCollectorDemo.Order::region,
        Collectors.mapping(
            RevenueCollectorDemo.Order::amountVnd,
            Collectors.toList()
        )
    ));
```

`mapping` changes the data fed into the downstream: the outer collector still receives `Order`, while the downstream now receives `Long`. This is a spot where it is very easy to confuse the outer collector's `T` with the element type after the inner mapper.

**Boundary to remember:** `Collectors.filtering` differs from `Stream.filter` when placed inside `groupingBy`. Filtering before grouping can eliminate a group completely; downstream filtering can keep the group key with an empty accumulated result if the group had elements but none passed the downstream predicate.

## 9. Difference between the two `Stream.collect` overloads

Besides the overload taking a `Collector`, `Stream<T>` also has a three-parameter form:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)
```

Example collecting into an `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

ArrayList<String> names = Stream.of("An", "Bình", "Chi")
    .collect(
        ArrayList::new,
        ArrayList::add,
        ArrayList::addAll
    );

System.out.println(names); // [An, Bình, Chi]
```

With this overload, **container type `R` is already the result**; there is no separate type parameter `A` or finisher. The combiner has type `BiConsumer<R,R>` and returns `void`, unlike `BinaryOperator<A>` on the `Collector` interface which returns an `A`.

Comparison:

| Part | `collect(Collector)` | `collect(supplier, accumulator, combiner)` |
| --- | --- | --- |
| Input type | `T` | `T` |
| Accumulation type | `A` | `R` |
| Result type | `R` | `R` |
| Combiner | `BinaryOperator<A>` returns `A` | `BiConsumer<R,R>` returns `void` |
| Finisher | Can have `Function<A,R>` | No separate finisher |
| Characteristics | Can be declared via collector | No characteristics parameter |
| When to use | Standard collectors, custom collectors, aggregated results | Direct mutable reduction when container is the result |

Primitive streams such as `IntStream` have an overload `collect(supplier, ObjIntConsumer, combiner)` suited to primitive data. They do not provide a `collect(Collector<T,A,R>)` overload like `Stream<T>`; when you need to use `Collectors` with wrappers, you can convert via `boxed()` or create objects with `mapToObj`.

## 10. Three collector characteristics

`Collector.Characteristics` provides characteristics so the Stream framework knows which optimizations are **valid**. Do not attach characteristics just to chase speedups.

| Characteristic | Commitment | Common misconception |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher can be skipped; `A` can be used directly as `R` | Not just because `A` and `R` have the same type name |
| `UNORDERED` | Result does not depend on encounter order | Does not mean source elements are already sorted |
| `CONCURRENT` | Accumulator can be called from multiple threads on **the same `A` container** | Cannot be attached to plain mutable `ArrayList`/`HashMap` without a safety mechanism |

### 10.1. `IDENTITY_FINISH`

For example, a collector creating an `ArrayList<String>` and returning that exact accumulated list can have `IDENTITY_FINISH`. With `RevenueAccumulator → Summary`, the finisher creates a new record, so it does **not** have this characteristic.

By contract, if `IDENTITY_FINISH` is declared, the framework may perform a cast `A → R` without calling the finisher; declaring it wrongly can cause a `ClassCastException` or wrong results. `Collector.of(supplier, accumulator, combiner)` supplies this characteristic automatically.

### 10.2. `UNORDERED`

For instance, a set of unique elements may not care about encounter order, so a `toSet`-style collector is unordered. Conversely, a collector building a list in source order should not declare `UNORDERED` if element positions are part of the guaranteed result.

`UNORDERED` speaks to **equivalence of collector results**, not whether the source itself is unordered; a `Map` result still does not automatically guarantee key order.

### 10.3. `CONCURRENT`

A concurrent collector allows multiple threads to update **the same state** per its contract. The accumulation mechanism must be genuinely thread-safe. For example, `Collectors.toConcurrentMap` or `groupingByConcurrent` have specific contracts that must be read carefully.

Even when a collector has `CONCURRENT`, accumulating together into one container also depends on whether the stream has an encounter order and whether the collector has `UNORDERED`. In parallel environments, the framework may still use multiple states and merge them appropriately. Do not rely on how many times supplier/combiner are called to judge correctness.

## 11. Collector correctness laws

The laws are described in the `Collector` Javadoc, and are especially critical in parallel processing.

### 11.1. Identity

Given an accumulated state `a`, merging with a fresh empty container from the supplier must be **equivalent** to the initial state:

```text
combiner(a, supplier()) ≈ a
```

"Equivalent" does not necessarily mean the same object reference; what must hold is that the result has the same meaning per the collector contract.

For example, when aggregating revenue: an empty state has count and total equal to 0. Merging with an empty state does not change either value.

### 11.2. Associativity

Splitting input into multiple parts and merging in different ways must yield **equivalent results**:

```text
accumulate(all elements sequentially)
    ≈ combine(accumulate(left), accumulate(right))
```

Exact integer addition, counting, and properly designed group merging can satisfy this requirement. Subtraction is usually **not associative**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Do not use subtraction as a combiner if the result must be invariant under splitting/merging. For floating-point `double`, addition suffers rounding error and can differ across groupings; when exact math or strictly reproducible results are required, define an appropriate arithmetic strategy.

### 11.3. Combiner must be consistent with accumulator

If the accumulator inserts elements into a list in order, the combiner must merge two segments in the corresponding order (unless the collector declares and truly enforces `UNORDERED`).

A counter-example:

```java
// Semantically wrong: combiner discards the right container.
(left, right) -> left
```

When a sequential pipeline creates a single container, the bug may not appear. During parallel execution, data from other branches is lost. Therefore, **a passing sequential test does not prove a collector is correct**.

### 11.4. Container and ownership constraints

A proper collector must not leak mutable accumulation references for other parts of the program to modify while running. Once a container has been passed to the combiner, further use of that container must follow the collector protocol constraints and how the framework manages it.

`Supplier<A>` typically creates an independent container; `accumulator` and `combiner` must operate solely on collector state, avoiding global variables or mutating the source being traversed. A collector without `CONCURRENT` can still be valid in parallel execution thanks to container partitioning, **without requiring each `A` to be thread-safe itself**.

## 12. Important anti-patterns

### 12.1. Using `reduce` to mutate a mutable list

`reduce` serves associative value merging and should not use a mutable accumulator like this:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

// Avoid: the same identity List may be shared in parallel reduction.
List<String> wrong = Stream.of("A", "B", "C").reduce(
    new ArrayList<>(),
    (list, value) -> {
        list.add(value);
        return list;
    },
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);

// Right: use collect for mutable accumulation.
List<String> right = Stream.of("A", "B", "C")
    .collect(java.util.stream.Collectors.toList());
```

This is a failure to distinguish **immutable reduction** (`reduce`) from **mutable reduction** (`collect`). With `reduce`, the identity must be a neutral value and the accumulator/combiner must be compatible, not relying on a mutable object that might be shared.

### 12.2. Supplier returns the same shared container

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> shared = new ArrayList<>();

// Wrong: every supplier call returns the exact same shared object.
Collector<String, List<String>, List<String>> unsafe = Collector.of(
    () -> shared,
    List::add,
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
```

This collector risks mixing data across different runs, concurrently updating the same list, or merging a list with itself. The supplier must create a fresh accumulation container per contract, e.g., `ArrayList::new`.

### 12.3. Attaching `CONCURRENT` to an unsafe accumulator

A regular `ArrayList` does not support multiple threads calling `add` concurrently on the same instance. Adding `Collector.Characteristics.CONCURRENT` does not make it thread-safe. Use an appropriate accumulation mechanism, or let the framework partition state and merge **without** declaring concurrent.

### 12.4. Forgetting empty sources, `null`, and invalid data

`supplier()` must provide a state that allows collecting an empty source. In `RevenueCollectorDemo`, the result is `Summary(0,0)`; in normal `groupingBy`, it is an empty `Map`.

For `null` elements, collectors do not share one universal policy: `ArrayList` can hold `null`, `List.copyOf` and `Collectors.toUnmodifiableList` reject `null`, while a `groupingBy` classifier returning a `null` key throws an error per the implementation contract. Decide up front whether to **reject, skip, or substitute** missing data. Do not silently turn data errors into empty results that underreport metrics.

### 12.5. Attaching `UNORDERED` when the result needs ordering

If the result is a list representing event history, order may be business-critical information. Attaching `UNORDERED` removes an important constraint and can allow the framework to produce results differing from requirements. Only declare it when different element encounter orders yield equivalent results.

## 13. Testing a collector: empty source, splitting/merging, and parallel

The JUnit 5 tests below use the `RevenueCollectorDemo` class from section 6. They verify result correctness without depending on supplier/combiner call counts:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class RevenueCollectorDemoTest {

    @Test
    void collectsCountAndSum() {
        List<RevenueCollectorDemo.Order> orders = List.of(
            new RevenueCollectorDemo.Order("HN", 120_000L),
            new RevenueCollectorDemo.Order("HCM", 80_000L),
            new RevenueCollectorDemo.Order("HN", 100_000L)
        );

        RevenueCollectorDemo.Summary actual = orders.stream()
            .collect(RevenueCollectorDemo.revenueCollector());

        assertEquals(
            new RevenueCollectorDemo.Summary(3L, 300_000L),
            actual
        );
    }

    @Test
    void emptyStreamReturnsNeutralSummary() {
        RevenueCollectorDemo.Summary actual =
            List.<RevenueCollectorDemo.Order>of().stream()
                .collect(RevenueCollectorDemo.revenueCollector());

        assertEquals(
            new RevenueCollectorDemo.Summary(0L, 0L),
            actual
        );
    }

    @Test
    void sequentialAndParallelResultsMatch() {
        List<RevenueCollectorDemo.Order> orders =
            java.util.stream.IntStream.range(0, 10_000)
                .mapToObj(i -> new RevenueCollectorDemo.Order(
                    i % 2 == 0 ? "HN" : "HCM", i
                ))
                .toList();

        RevenueCollectorDemo.Summary sequential = orders.stream()
            .collect(RevenueCollectorDemo.revenueCollector());
        RevenueCollectorDemo.Summary parallel = orders.parallelStream()
            .collect(RevenueCollectorDemo.revenueCollector());

        assertEquals(sequential, parallel);
        assertEquals(10_000L, parallel.count());
        assertEquals(49_995_000L, parallel.totalVnd());
    }

    @Test
    void reportsOverflowInsteadOfWrappingAround() {
        List<RevenueCollectorDemo.Order> orders = List.of(
            new RevenueCollectorDemo.Order("HN", Long.MAX_VALUE),
            new RevenueCollectorDemo.Order("HN", 1L)
        );

        assertThrows(ArithmeticException.class, () ->
            orders.stream().collect(
                RevenueCollectorDemo.revenueCollector()
            )
        );
    }

    @Test
    void rejectsInvalidOrder() {
        assertThrows(IllegalArgumentException.class, () ->
            new RevenueCollectorDemo.Order("HN", -1L)
        );
    }
}
```

Additionally test **merging laws** when writing complex collectors: split a list into several segments, accumulate separately and merge under different grouping trees, then compare the final results. For ordered collectors, preserve expected order; for `UNORDERED` collectors, compare as sets or order-independent values.

## 14. Performance, resources, and choosing the right collector

A Collector does not automatically make every pipeline faster. The following choices significantly impact performance:

**Size of `A`.** A collector building a full list must hold many elements in memory. A collector holding only count and sum has small state, usually preferable when only statistics are needed. When data volume is massive, consider pushing aggregation down to the source system (e.g., database) if appropriate for the problem and data model.

**Finisher cost.** `List.copyOf` creates or selects an unmodifiable list representation, which may take extra time and memory. A finisher converting temporary maps into DTOs also adds work. In return, the final result has a clear contract and lower risk of accidental mutation.

**Ordering and parallelism.** Collectors that must preserve order sometimes have to coordinate/merge results in source order. `groupingByConcurrent` can be useful when business logic permits unordered accumulation, though it does not automatically guarantee sublist order. Measure on real data before switching to `parallel()`.

**Side effects.** Avoid I/O calls, business-significant logging, or network access from accumulator/combiner. A single collection may create multiple states and call the combiner differently across JVM versions or parallel configurations; external side effects may be duplicated or run out of expected order.

**Streams backed by resources.** `Files.lines(path)` and I/O-related streams must be closed with `try-with-resources`, even when the terminal operation is `collect`. Example:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> readNonBlankLines(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines
            .map(String::strip)
            .filter(s -> !s.isEmpty())
            .toList();
    }
}
```

If the data stream could be too large, keeping everything in memory via `toList()` should also be reconsidered; a leaner statistics collector might be used instead. Closing the I/O source and managing result memory are **two independent concerns**.

**When to use standard collectors?** With `toList`, `toSet`, `joining`, `counting`, `summingLong`, `groupingBy`, `partitioningBy`, `mapping`, `filtering`, or `collectingAndThen`, prefer the standard API if it expresses the business logic accurately. Only use `Collector.of` when you need a custom state `A` and aggregation logic.

## 15. Applied exercises

### Exercise 1 — Identify `T`, `A`, and `R`

Given three collectors:

```java
Collectors.toList()
Collectors.counting()
Collectors.groupingBy(Order::region,
    Collectors.summingLong(Order::amountVnd))
```

Assume the source is `Stream<Order>`. Identify `T`, `R`, and explain why you should not guess `A` solely from the result type. Distinguish the downstream's `A` from the hidden `A` in the outer collector.

### Exercise 2 — Merging counting states

Design an element-counting collector where `T = String`, `A` is a mutable object holding `long count`, and `R = Long`. Write supplier, accumulator, combiner, and finisher. Test with an empty source and compare `stream()` against `parallelStream()`.

### Exercise 3 — Immutable result

Write `Collector<String, ArrayList<String>, List<String>>` whose finisher uses `List.copyOf`. Compare with the identity-finish overload of `Collector.of` and with `Collectors.toList()`. Predict what happens if the input contains `null`, then choose a handling policy.

### Exercise 4 — Downstream collector

Use `groupingBy` to create `Map<String, Summary>` by region from `RevenueCollectorDemo`. Identify `K = String`, `D = Summary`, and where `Collector<Order, ?, Summary>` is passed. Add a new region and verify the result.

### Exercise 5 — Finding a combiner bug

A collector has a supplier creating a new `ArrayList` and an accumulator adding elements, but its combiner returns `left` unchanged without merging `right`. Explain why sequential runs can "look right" while parallel runs can drop elements. Rewrite the combiner and test on a large list.

### Exercise 6 — Safe average with empty sources

Write a collector that tracks `count` and `sum` (with an appropriate numeric type), then returns a result type with an explicit empty state: `OptionalDouble.empty()` when there are no samples, and the average when samples exist. Compare this approach with `Collectors.averagingLong` when business logic must distinguish "no samples" from "average of 0".

### Exercise 7 — Which characteristics are valid?

For the `RevenueAccumulator → Summary` collector, evaluate whether `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` should be attached. Explain based on **actual contracts**, not a wish for speedup.

## 16. Reference cheat sheet for `Collector<T, A, R>`

| Question | Line of reasoning |
| --- | --- |
| What type are the stream elements? | That is `T` |
| What structure does the collector accumulate into? | That is `A` |
| What type must `collect` return? | That is `R` |
| Who creates the empty state? | `supplier()` |
| Who puts one element into the state? | `accumulator()` |
| Who merges states when the pipeline splits? | `combiner()` |
| Who converts the state into the public result? | `finisher()` |
| When can `A` and `R` be used identically? | When the contract truly satisfies `IDENTITY_FINISH` |
| Why does `Collector<T, ?, R>` have `?`? | The internal state type is hidden from callers |
| When does a collector work with parallel streams? | Supplier/accumulator/combiner obey identity, associativity, ownership, and characteristics laws |
| Are standard collectors concurrent by default? | Do not assume; check `characteristics()` and the contract |
| Need to group data by key and aggregate each group? | `groupingBy(classifier, downstream)` |
| Only need a sum, count, or list? | Prefer standard collectors or the corresponding terminal operation |

`Collector<T,A,R>` is the contract connecting **input elements** to **accumulation state** and **final result**. Reading these three types correctly helps you understand why `collect` can produce a `Map`, DTO, or report from a `Stream<Order>`, why many collectors hide `A` behind a wildcard, and why the combiner must be right when running in parallel. When you need a custom collector, clearly define state lifecycle, merging laws, empty-source handling, and result immutability before optimizing performance.
