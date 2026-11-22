# `Collector.of()` and Building a Simple Collector in Java

## 1. When do you need to write a custom collector?

Stream terminal operations such as `toList()`, `count()`, `reduce(...)`, and `collect(...)` turn a sequence of elements into a usable result. With `collect(...)`, Java already provides many built-in collectors:

```java
List<String> names = values.stream().collect(Collectors.toList());
Set<String> unique = values.stream().collect(Collectors.toSet());
Map<String, Long> counts = values.stream().collect(
        Collectors.groupingBy(String::toLowerCase, Collectors.counting()));
```

The snippet above is an illustration where `values` is a `List<String>` and the required types have been imported. Most common needs should use standard collectors. However, if you need a **custom result type**—for example, aggregating order information into an immutable summary containing line count, total quantity, and revenue, or building a specially formatted string—`Collector.of(...)` lets you specify how accumulation works.

After completing this lesson, you will:

- Understand the types `T`, `A`, `R` in `Collector<T,A,R>`.
- Distinguish the four components `supplier`, `accumulator`, `combiner`, `finisher` and how they work together.
- Use the two forms of `Collector.of(...)`: without an explicit finisher and with a finisher.
- Build a simple collector from `StringJoiner`, and then a collector that aggregates data into an immutable record in Java 17.
- Write a correct combiner that works for both sequential and parallel Streams.
- Understand the `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` characteristics, and avoid declaring them incorrectly.
- Test the results for an empty Stream, a single element, multiple elements, a parallel source, and grouping by key.

## 2. How is `collect` different from `Collector`?

`stream.collect(collector)` is a **terminal operation**. It executes the pipeline and uses a collector to produce the result.

`Collector` is a **description of the accumulation process**, not a list already holding data, and not a place where the program should manually retain state across multiple runs. A `Collector` can be reused across different `collect` calls if its functions are designed properly (especially having the supplier create a new container). A Stream that has already been consumed cannot be reused.

Conceptual example:

```text
Stream<T> has elements t1, t2, t3, ...
       │
       ▼
collector.supplier()       → new container A
       │
       ▼
collector.accumulator()    → add each T into A
       │
       ├── parallel processing may create multiple A's
       │                         │
       │                         ▼
       └──── collector.combiner() merges two A's into A
                                 │
                                 ▼
                      collector.finisher()
                                 │
                                 ▼
                           result R
```

This diagram illustrates the API contract; it does **not** guarantee that Java must invoke the functions in that exact order or number of times for every Stream. A collector with an identity finisher can skip the final transformation step; a parallel Stream can create and merge multiple containers; and the collector's characteristics affect how execution proceeds.

## 3. The three data types `T`, `A`, `R`

Declaration:

```java
public interface Collector<T, A, R> {
    // supplier, accumulator, combiner, finisher, characteristics...
}
```

| Parameter | Role | Statistics example |
| --- | --- | --- |
| `T` | Type of the **input elements** of the Stream | `Order` |
| `A` | Type of the **intermediate accumulation container** | `MutableStats` |
| `R` | Type of the **final result** returned by `collect` | `Report` |

`T`, `A`, and `R` **do not have to be the same**.

For example, `Stream<Order>` is collected into a `Report` using an intermediate `MutableStats` object:

```text
T = Order
A = MutableStats
R = Report
```

There are also cases where `A = R`, such as collecting a Stream of strings into a `List<String>`; because the intermediate container is already the result, the finisher can be the identity function.

A very important distinction: **a collector's accumulator does not return a new container**; it usually **mutates the provided container `A`**. Meanwhile, the combiner must **return a container `A`** representing the merged result.

## 4. The four core components of `Collector.of(...)`

Full form:

```java
Collector.of(
        supplier,
        accumulator,
        combiner,
        finisher,
        characteristics...);
```

### 4.1. `supplier: Supplier<A>`

`supplier.get()` must create a **new empty result container** for an accumulation pass:

```java
ArrayList<String>::new
```

or:

```java
() -> new MutableStats()
```

Why does "new" matter? In a parallel Stream, multiple branches can accumulate into different containers. Returning **the same shared object** from the supplier causes overwritten state, duplicate counting bugs, and race conditions. Even in a sequential Stream, a reused collector must not carry data from one run into the next.

The supplier must be able to create a neutral (identity) container: when no elements have been added yet, the result after the finisher must be the **correct result for an empty Stream**.

### 4.2. `accumulator: BiConsumer<A,T>`

This function takes a container `A` and an element `T`, then **folds the element's contribution into the container**:

```java
(list, word) -> list.add(word)
```

Because `BiConsumer` returns `void`, you do not write `return list` as you would in a `BinaryOperator`. In a mutable collector, the accumulator usually modifies `A` in place. For statistics data:

```java
(stats, order) -> stats.add(order)
```

The accumulator must follow the non-interference contract: do not add or remove elements on the Stream source being traversed. Avoid unrelated side effects or updating a shared variable outside the container.

### 4.3. `combiner: BinaryOperator<A>`

When there are two intermediate results, the combiner must merge them into one suitable result:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

The combiner **returns `A`**, not `void`. You may mutate the left container and return it, provided you do not keep a reusable reference to the right container and the merge preserves the correct result.

For statistics, the combiner adds the line count, unit count, and revenue from the `right` container into `left`. If it forgets a field, a sequential collect may still produce the right answer, whereas parallel collection will be **wrong** because one branch's values are dropped.

The merge must be associative with respect to the result semantics; if the result needs to preserve element order, you must not arbitrarily swap `left` and `right`. Do not assume the combiner is called only once.

### 4.4. `finisher: Function<A,R>`

The finisher transforms the accumulated container into the **final result**. For example:

```java
stats -> new Report(stats.rows, stats.units, stats.revenue)
```

When `A` is a mutable object used for accumulation, but the API wants to return an immutable `record`, this is the key step to **avoid exposing internal mutable state**.

If `A` and `R` are the same type and the container itself is the result, you can use the `Collector.of(supplier, accumulator, combiner, characteristics...)` overload without a finisher. This form has the `IDENTITY_FINISH` characteristic: the intermediate container is used directly as the result.

## 5. Two `Collector.of` overloads to distinguish

### Without passing a finisher — `A` is also `R`

```java
static <T, R> Collector<T, R, R> of(
        Supplier<R> supplier,
        BiConsumer<R, T> accumulator,
        BinaryOperator<R> combiner,
        Collector.Characteristics... characteristics);
```

Example:

```java
Collector<String, List<String>, List<String>> copyCollector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

Here:

- The supplier creates an empty `ArrayList<String>`.
- The accumulator adds a `String` to the List.
- The combiner concatenates intermediate Lists and returns the left List.
- The result is the accumulated List itself, so there is no separate final transformation function.

With the three-function `Collector.of` above, the collector has the `IDENTITY_FINISH` characteristic by contract. The resulting list is **modifiable** because we used `ArrayList`; by contrast, `Stream.toList()` since Java 16 returns an unmodifiable List. Do not treat these two approaches as having the same mutability contract.

### Passing a finisher — `A` can differ from `R`

```java
static <T, A, R> Collector<T, A, R> of(
        Supplier<A> supplier,
        BiConsumer<A, T> accumulator,
        BinaryOperator<A> combiner,
        Function<A, R> finisher,
        Collector.Characteristics... characteristics);
```

Example using `StringJoiner` as the container while returning `String`:

```java
Collector<String, StringJoiner, String> bracketed =
        Collector.of(
                () -> new StringJoiner(" | ", "[", "]"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);
```

`StringJoiner::merge` returns `StringJoiner`, matching the combiner requirement. Result:

```java
String text = Stream.of("red", "green", "blue")
        .collect(bracketed);
// "[red | green | blue]"
```

For an empty Stream, a `StringJoiner` with the prefix/suffix above returns `"[]"`; for ordered data, the result is built in element encounter order. **Do not** declare `UNORDERED` on this collector because the order of words affects the output.

## 6. Complete Java 17 example: building a statistics collector

Suppose each input element is an order line:

```text
Order(category, quantity, unitPrice)
```

Each `Order` entry is an immutable record representing the category, quantity, and unit price. We want to collect into a `Report`:

- `lines`: total number of order lines.
- `units`: total number of product units.
- `revenue`: total revenue, equal to the sum of `quantity × unitPrice`.

Collection architecture:

```text
Stream<Order>           [Order, Order, Order, ...]
     │
     ▼
Collector<Order, MutableStats, Report>
     │
     ├─ supplier:   MutableStats::new
     ├─ accumulator: MutableStats::accept
     ├─ combiner:   MutableStats::merge
     └─ finisher:   MutableStats::finish
     │
     ▼
Report(lines, units, revenue) — immutable
```

Unlike `reduce`, which returns a **new immutable object at every step**, a custom collector can accumulate into internal mutable state and only create the immutable record at the end. Intermediate containers must have an appropriate lifecycle and must not be freely shared across threads.

Create the file **`CustomCollectorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.StringJoiner;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CustomCollectorDemo {
    record Order(String category, int quantity, long unitPrice) {
        Order {
            Objects.requireNonNull(category, "category");
            if (quantity < 0 || unitPrice < 0) {
                throw new IllegalArgumentException(
                        "quantity and price must be nonnegative");
            }
        }
    }

    record Report(long lines, long units, long revenue) {}

    static final class MutableStats {
        private long lines;
        private long units;
        private long revenue;

        void accept(Order order) {
            lines = Math.addExact(lines, 1L);
            units = Math.addExact(units, order.quantity());
            long amount = Math.multiplyExact(
                    (long) order.quantity(), order.unitPrice());
            revenue = Math.addExact(revenue, amount);
        }

        MutableStats merge(MutableStats other) {
            lines = Math.addExact(lines, other.lines);
            units = Math.addExact(units, other.units);
            revenue = Math.addExact(revenue, other.revenue);
            return this;
        }

        Report finish() {
            return new Report(lines, units, revenue);
        }
    }

    static Collector<Order, MutableStats, Report> reportCollector() {
        return Collector.of(
                MutableStats::new,
                MutableStats::accept,
                MutableStats::merge,
                MutableStats::finish,
                Collector.Characteristics.UNORDERED);
    }

    static Collector<String, List<String>, List<String>>
            listCollector() {
        return Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
    }

    static Collector<String, StringJoiner, String>
            bracketCollector() {
        return Collector.of(
                () -> new StringJoiner(" | ", "[", "]"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);
    }

    static List<Order> sample() {
        return List.of(
                new Order("Books", 2, 100),
                new Order("Food", 3, 40),
                new Order("Books", 1, 150),
                new Order("Tech", 1, 250),
                new Order("Food", 2, 30));
    }

    static Map<String, Report> byCategory(List<Order> orders) {
        return orders.stream().collect(
                Collectors.groupingBy(
                        Order::category,
                        TreeMap::new,
                        reportCollector()));
    }

    static void expect(Object wanted, Object actual, String name) {
        if (!Objects.equals(wanted, actual)) {
            throw new AssertionError(
                    name + ": expected=" + wanted
                            + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Order> orders = sample();
        Report all = new Report(5, 9, 780);

        expect(all, orders.stream().collect(reportCollector()),
                "sequential report");
        expect(all, orders.parallelStream().collect(reportCollector()),
                "parallel report");
        expect(new Report(0, 0, 0),
                Stream.<Order>empty().collect(reportCollector()),
                "empty report");
        expect(new Report(1, 2, 200),
                orders.stream().limit(1).collect(reportCollector()),
                "single item");

        expect(Map.of(
                "Books", new Report(2, 3, 350),
                "Food", new Report(2, 5, 180),
                "Tech", new Report(1, 1, 250)),
                byCategory(orders), "downstream grouping");

        expect(List.of("red", "green", "blue"),
                Stream.of("red", "green", "blue")
                        .collect(listCollector()),
                "list collector");

        expect("[red | green | blue]",
                Stream.of("red", "green", "blue")
                        .collect(bracketCollector()),
                "joining");
        expect("[]", Stream.<String>empty()
                .collect(bracketCollector()), "empty joining");

        expect(true, listCollector().characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH),
                "identity finisher on list collector");
        expect(false, reportCollector().characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH),
                "report has real finisher");
        expect(true, reportCollector().characteristics().contains(
                Collector.Characteristics.UNORDERED),
                "report does not depend on order");
        expect(false, reportCollector().characteristics().contains(
                Collector.Characteristics.CONCURRENT),
                "mutable stats are not shared concurrently");

        expect(5, orders.size(), "source unchanged");
    }

    public static void main(String[] args) {
        runTests();

        List<Order> orders = sample();
        Report sequential = orders.stream().collect(reportCollector());
        Report parallel = orders.parallelStream()
                .collect(reportCollector());

        System.out.println("report=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + Stream.<Order>empty()
                .collect(reportCollector()));
        System.out.println("grouped=" + byCategory(orders));
        System.out.println("joined=" + Stream.of("red", "green", "blue")
                .collect(bracketCollector()));
        System.out.println("copy=" + Stream.of("red", "green", "blue")
                .collect(listCollector()));
        System.out.println("identityFinish="
                + listCollector().characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("summaryIdentityFinish="
                + reportCollector().characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("summaryUnordered="
                + reportCollector().characteristics().contains(
                        Collector.Characteristics.UNORDERED));
        System.out.println("summaryConcurrent="
                + reportCollector().characteristics().contains(
                        Collector.Characteristics.CONCURRENT));
        System.out.println("tests=PASS");
    }
}
```

Compile and run with **JDK 17 or newer**:

```bash
javac CustomCollectorDemo.java
java CustomCollectorDemo
```

Expected stdout:

```text
report=Report[lines=5, units=9, revenue=780]
parallel=Report[lines=5, units=9, revenue=780]
empty=Report[lines=0, units=0, revenue=0]
grouped={Books=Report[lines=2, units=3, revenue=350], Food=Report[lines=2, units=5, revenue=180], Tech=Report[lines=1, units=1, revenue=250]}
joined=[red | green | blue]
copy=[red, green, blue]
identityFinish=true
summaryIdentityFinish=false
summaryUnordered=true
summaryConcurrent=false
tests=PASS
```

### Result analysis

The five data lines have the following revenue:

| Category | Quantity | Unit price | Revenue |
| --- | ---: | ---: | ---: |
| Books | 2 | 100 | 200 |
| Food | 3 | 40 | 120 |
| Books | 1 | 150 | 150 |
| Tech | 1 | 250 | 250 |
| Food | 2 | 30 | 60 |
| **Total** | **9** | | **780** |

Thus `Report[lines=5, units=9, revenue=780]` is the correct result. When grouped by category, Books has two lines and revenue 350, Food has two lines and revenue 180, and Tech has one line and revenue 250.

`TreeMap::new` in `groupingBy` ensures the keys `Books`, `Food`, and `Tech` are traversed in alphabetical order, making the `grouped=...` output deterministic. Do not assume default `groupingBy` guarantees this key order.

`runTests()` checks the overall `Report`, per-category results, the empty case, a single line, the output of the other two collectors, declared characteristics, and that the input list is unmodified. The `expect` method throws `AssertionError` on failure; there is no need to enable the JVM `-ea` flag.

### Why can't the result record be mutated after being returned?

`MutableStats` exists only during `collect`; `MutableStats::finish` creates `new Report(...)`. Because `Report` is a record containing three `long` values, the caller cannot modify the fields of the result after completion. Real-world problems can be more complex if a record contains a `List`, `Map`, or mutable object; in that case you need to consider a **defensive copy** and should not conclude that all records are deeply immutable.

### Why is using `UNORDERED` valid here?

The metrics `lines`, `units`, and `revenue` are simply additions of independent contributions, so the result does not depend on element order (within the chosen arithmetic range without overflow errors). Therefore, the collector can declare `UNORDERED`.

By contrast, `bracketCollector()` joins strings in order and **does not declare `UNORDERED`**. Marking a string-joining collector as unordered while still expecting `[red | green | blue]` in input order would contradict the contract.

`UNORDERED` **does not mean** `CONCURRENT`. `MutableStats` is just an ordinary mutable object; the code **does not** allow multiple threads to call `accept` concurrently on the same instance. Nevertheless, `parallelStream` still works correctly because each branch accumulates into its own container, and the combiner merges them afterward.

## 7. Contract of `supplier`, `accumulator`, and `combiner`

A collector must have consistent semantics whether the source is empty, small, large, sequential, or parallel. You can think of the rules as follows.

### 7.1. Independence from how data is partitioned

Suppose the source consists of `[a,b,c,d]`; the aggregated result must be equivalent between:

```text
Way 1:
  supplier → add a → add b → add c → add d → finish

Way 2:
  supplier → add a → add b ┐
                            combiner → finish
  supplier → add c → add d ┘
```

The two intermediate containers do not have to be the same object. What must be preserved is an **equivalent final result** according to the business contract.

For statistics, the combiner adds each metric so both ways yield the same three totals. For an ordered List, the combiner `left.addAll(right)` preserves the order of the two partitions when the framework preserves encounter order.

### 7.2. Identity of the intermediate container

A new container from the supplier is a neutral state. Whether you call `combiner(empty, accumulated)` or `combiner(accumulated, empty)`, the result must be equivalent to `accumulated`.

A new `MutableStats` has all three fields equal to 0. When merged with an existing result, adding zeros does not change the values. A new empty `ArrayList` is also neutral with respect to `addAll`.

If the supplier starts with an extra value, such as `lines = 1`, parallel processing may **overcount by the number of intermediate containers**. If you want to add a fixed fee only once, do it **after** the reduction finishes—do not put that fee in every supplier container if it is not neutral.

### 7.3. Only return a valid container from the combiner

Correct example:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Wrong example:

```java
// Wrong: discards all data belonging to right.
(left, right) -> left
```

With a sequential Stream, a broken combiner might not be called and tests could still pass. With a parallel Stream or a downstream collector that must merge multiple containers, data from the right branch is lost. Therefore, **always test the combiner**, not just sequential cases.

### 7.4. Do not leak state that is still accumulating

Do not store `MutableStats` in a shared static variable or return a mutable object directly outside and continue mutating it during collection. Each invocation of the supplier needs a new container. If the finisher returns a mutable structure holding references to data regions that other code is also modifying, the application must have a clear ownership and copying contract.

## 8. `Collector.Characteristics`

`Collector.of(...)` can accept characteristics that describe the liberties the framework may take during execution:

| Characteristic | Meaning | When to declare |
| --- | --- | --- |
| `IDENTITY_FINISH` | The result can use the container `A` itself, needing no significant finisher conversion | When `A` is also `R` and the identity finisher is used |
| `UNORDERED` | The result is not constrained by encounter order | When element order does not change the meaning of the result |
| `CONCURRENT` | The accumulator can be called concurrently on **the same container** | Only when the structure and accumulation operation truly support safe concurrent access |

### `IDENTITY_FINISH`

With the overload taking only the three functions `supplier`, `accumulator`, and `combiner`, the `IDENTITY_FINISH` characteristic is added by contract. Do not add this characteristic to a collector that returns a different type from the container:

```java
// Correct: A=StringJoiner, R=String; finisher performs type conversion.
Collector<String, StringJoiner, String> c =
        Collector.of(
                () -> new StringJoiner(","),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);
```

The collector above **does not** have `IDENTITY_FINISH` because `StringJoiner` cannot stand in for `String`.

If you declare `IDENTITY_FINISH` incorrectly alongside a type-converting finisher, the API may skip the finisher; the result will no longer have the expected type or will cause a runtime error. Do not use characteristics as an arbitrary optimization trick.

### `UNORDERED`

A quantity sum by adding integers can be order-independent, whereas joining employee names into a string depends on order. A collector holding an ordered list normally **should not** declare `UNORDERED`.

When `UNORDERED` is present, the framework is allowed to drop the requirement to preserve encounter order of the data; it is a semantic guarantee of the collector, not a requirement that the Stream must run in parallel.

### `CONCURRENT`

`CONCURRENT` is a very strong commitment. For example, an `ArrayList` or a `MutableStats` with `long` fields is not thread-safe, so you **must not** attach `CONCURRENT` just because you want fast execution on `parallelStream()`.

If you use a shared accumulator without synchronization, updates like `lines++` or `revenue += amount` can lose data. To build a concurrent collector, you need a properly designed container, atomic operations, or genuine synchronization, while also considering ordering requirements and downstream characteristics.

A collector **without `CONCURRENT` can still** execute in parallel correctly using separate suppliers and a combiner. A collector **with `CONCURRENT`** is also not guaranteed to perform better; performance depends on the source, number of groups, contention, and how the framework executes it.

## 9. Using a custom collector as a downstream of `groupingBy`

Composability is a major advantage of collectors. You can pass `reportCollector()` into `groupingBy`:

```java
Map<String, Report> byCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                TreeMap::new,
                reportCollector()));
```

Here:

1. `groupingBy` determines the key from `Order::category`.
2. `reportCollector()` processes **only the Orders belonging to each key**.
3. Each Map key has a `Report` value, not a List.
4. `TreeMap` sorts the keys for output/iteration without changing the summation logic of each group.

You do not have to build `Map<String,List<Order>>` first and then loop over the Lists to create a Report. The downstream collector can compute totals during collection. For large datasets, this is often more sensible if you only need the metrics, because it avoids retaining every Order in the grouped result.

If business requirements also demand keeping all Orders alongside the statistics, you must deliberately choose a result type that includes them, or compose appropriate collectors. Do not alter requirements just to avoid storing more data.

### `null` keys and invalid data

`Collectors.groupingBy` does not allow the classifier to return a `null` key. `reportCollector()` **cannot** fix this on its own because the outer classifier determines the grouping.

If `Order.category()` can be null, you need a clear policy: fail with an error, normalize to a special key, or use a stateful key type. In the Java 17 program, the `Order` record constructor calls `Objects.requireNonNull`, so source data is valid by contract.

The `quantity` and `unitPrice` values are also validated to be non-negative. This is a choice of the example; if a business uses negative quantities for returns or negative revenue for adjustments, the contract must be adjusted accordingly.

## 10. `Collector.of` vs. `Stream.reduce`: differences in mutable reduction

A common trap is using `Stream.reduce` as if it were `Collector.of`:

```java
// Avoid: mutation on a shared identity ArrayList.
List<String> result = Stream.of("a", "b", "c")
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

This is a **broken design**, not a recommended collector: this style of reduction easily shares the mutable identity object across branches, corrupting data and violating the intent of `reduce`. `reduce` is meant for side-effect-free combining operations and value-based states per its contract.

For mutable accumulation, use `collect`:

```java
List<String> good = Stream.of("a", "b", "c")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll);
```

This is the **three-parameter overload of `Stream.collect`**, which takes a `supplier`, a `BiConsumer` accumulator, and a `BiConsumer` combiner. Note how it differs from `Collector.of`: **the combiner of `Stream.collect(supplier, accumulator, combiner)` returns `void`**, whereas the combiner of `Collector.of` must return `A`.

Compare the signatures:

```java
// Three-argument form of Stream.collect:
<R> R collect(Supplier<R> supplier,
              BiConsumer<R, ? super T> accumulator,
              BiConsumer<R, R> combiner);

// Collector.of form for creating a Collector:
<T, R> Collector<T, R, R> of(
        Supplier<R> supplier,
        BiConsumer<R, T> accumulator,
        BinaryOperator<R> combiner,
        Collector.Characteristics... characteristics);
```

That is why `ArrayList::addAll` fits the `BiConsumer` combiner of `collect` (its boolean return value is ignored in a void context), but cannot be used directly as the `BinaryOperator<List<String>>` of `Collector.of`, because a `BinaryOperator` must **return `List<String>`**. In `Collector.of`, write a lambda that calls `addAll` and then `return left`.

## 11. When should you prefer standard collectors over `Collector.of`?

Do not create a custom collector just to use an advanced API. Many problems already have shorter, easier-to-test solutions:

| Need | Built-in collector/operation | Notes |
| --- | --- | --- |
| Collect into a List | `toList()` / `Collectors.toList()` | Pay attention to the mutability of the result |
| Sum a property | `summingInt`, `summingLong`, `mapToLong(...).sum()` | Avoid writing custom state just for a single sum |
| Count | `counting()` / `stream.count()` | No need for a complex container |
| Min/max | `minBy`, `maxBy` | Use an explicit comparator; returns `Optional` |
| Group by property | `groupingBy` | Can be composed with a downstream collector |
| Join strings | `joining(delimiter, prefix, suffix)` | Often replaces the illustrative `StringJoiner` collector |
| Multiple numeric statistics | `summarizingInt/Long/Double` | Provides count, sum, min, max, average |
| Transform collector result | `collectingAndThen` | Avoids a custom collector if only a finisher is needed |
| Multiple independent aggregations | `teeing` (Java 12+) | Combines two collectors and a merger |

`CustomCollectorDemo` makes sense when the application needs **a single domain-specific Report** with three consistent fields, whether used directly or downstream. Even then, you can design standard collectors combined via `teeing`/`summarizing` if the results fit. Choose the approach with clear semantics, acceptable memory usage, and easy testability.

## 12. Common mistakes when building custom collectors

**Mistake 1 — supplier returns the same object:**

```java
List<String> shared = new ArrayList<>();
Collector<String, List<String>, List<String>> wrong =
        Collector.of(
                () -> shared,      // Wrong: does not create a new List.
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

This buggy snippet causes collection runs to share `shared`; when run in parallel, branches can mutate the same container or merge an object with itself. The supplier must create a **new container**.

**Mistake 2 — combiner drops the right-hand data:** writing `(left,right) -> left` when `right` contains data. Sequential tests may miss this, while parallel tests and tests combining two containers will expose the bug.

**Mistake 3 — confusing `BiConsumer` with `BinaryOperator`:** the accumulator does not return a result; the combiner of `Collector.of` must return the intermediate object.

**Mistake 4 — declaring `IDENTITY_FINISH` when the finisher converts types:** if `A=MutableStats` and `R=Report`, you must not claim the two types are identical.

**Mistake 5 — attaching `CONCURRENT` to a non-thread-safe container:** `ArrayList`, `HashMap`, or plain counter fields usually do not support multiple threads writing to the same instance. `parallelStream()` does not by itself justify `CONCURRENT`.

**Mistake 6 — attaching `UNORDERED` to an ordered result:** collectors that join strings or collect a List in encounter order must respect input order.

**Mistake 7 — finisher leaks mutable state:** returning a mutable List/Map to which external code still holds a reference makes state control unpredictable. Use a defensive copy or immutable structure when required by the contract.

**Mistake 8 — supplier does not create a neutral state:** if you initialize `lines=1` and split into multiple branches, each partial accumulation overcounts. Test empty, single-element, and parallel Streams.

**Mistake 9 — accumulation operation is not associative:** the combiner can alter results if it depends on grouping order or drops a field. Verify merging three containers under both groupings yourself.

**Mistake 10 — swallowing exceptions to return a seemingly valid result:** do not catch `Exception` and skip a bad row or return a default Report; handle input errors explicitly before the collector or report failure. In the demo, `Math.addExact`/`multiplyExact` throws `ArithmeticException` when exceeding `long` limits instead of silently overflowing.

**Mistake 11 — expecting the collector to be called in one exact callback order:** the number of calls to `supplier`, `accumulator`, `combiner`, and the timing of `finisher` depend on the execution strategy; verify the final result rather than turning callback logs into business logic.

**Mistake 12 — confusing immutability of the result with thread-safety of the state:** returning an immutable `Report` does not make `MutableStats` thread-safe. These two concerns are independent; the collector must be designed to satisfy its contract under parallel execution.

## 13. How to test a custom collector

Testing `stream.collect(...)` on three sequential elements is not enough. You should have test categories covering:

1. **Empty source:** the supplier creates a neutral state and the finisher returns the right result.
2. **Single element:** the accumulator updates all fields properly.
3. **Multiple elements:** the result is accurate, with no dropped or double-counted elements.
4. **Grouping by key:** the downstream collector is initialized and accumulated separately for each group.
5. **Parallel source:** the result matches sequential execution when the reduction satisfies the contract.
6. **Direct combiner test:** create two containers, accumulate two halves of the source, merge them, and compare against accumulating the whole.
7. **Identity:** merging an empty container with a populated container does not change the result.
8. **Associativity:** merging three containers as `(a+b)+c` and `a+(b+c)` yields the same observable result.
9. **Characteristics:** verify that only characteristics matching the actual semantics are declared.
10. **Overflow and invalid data:** the application has a clear response policy; the collector does not skew statistics.
11. **Ordering:** if the result depends on encounter order, test ordered input and verify the combiner preserves order.
12. **No source mutation:** the accumulator does not modify the List/Set/Map used as the Stream source.

Example of testing the combiner directly in the same `CustomCollectorDemo` class:

```java
MutableStats left = new MutableStats();
MutableStats right = new MutableStats();
left.accept(new Order("Books", 2, 100));
right.accept(new Order("Food", 3, 40));

Report merged = left.merge(right).finish();
// merged = Report[lines=2, units=5, revenue=320]
```

When testing, do not reuse `right` as if the combiner promised to leave every container untouched. The contract only cares about the proper result after merging. This snippet is an illustration placed in a class that already declares `MutableStats`, `Order`, and `Report`.

### Checking characteristics vs. behavior

A call to `reportCollector().characteristics()` confirms that the collector **declares** `UNORDERED` and does not declare `CONCURRENT`. This is only a test of metadata characteristics; it is not enough to prove the accumulator is safe or the merge is associative. You must inspect the logic and run tests with appropriate datasets and parallel partitions.

Do not rely on a single successful `parallelStream()` run to claim that every custom collector is thread-safe. The framework's parallelization depends on characteristics and splitting; your custom code must have a correct aggregation contract under every permitted grouping.

## 14. Practice exercises

1. Write a `Collector<String,StringJoiner,String>` using `Collector.of(...)` to join words with `" / "`, wrapped between `"{"` and `"}"`. Test the empty case and word ordering.
2. Change `listCollector()` into a collector that returns `List.copyOf(...)` via a finisher. Why must you not attach `IDENTITY_FINISH` to that collector? Verify that the returned List does not allow `add`.
3. Add `discount` to the `Order` record and update revenue after discount. Design the numeric type policy and rounding rules before writing the accumulator and combiner.
4. Write a statistics collector for `Stream<String>` returning `record TextStats(long items,long chars)`. Test an empty Stream, a parallel Stream, and grouping strings by their first letter.
5. Intentionally modify `MutableStats.merge` to forget adding `units`. Write a direct combiner test to catch the bug, even when sequential Stream tests still pass.
6. Intentionally modify the supplier to return a shared static `MutableStats`. Explain why this violates the collector contract, even if sequential runs sometimes print the right result.
7. Use the report collector as the downstream of `partitioningBy(o -> o.quantity() >= 2, reportCollector())`. Predict both `Report` values; an empty partition will yield `Report(0,0,0)`.
8. Compare a custom `Collector.of` for summing revenue with `Collectors.summingLong(o -> Math.multiplyExact((long)o.quantity(),o.unitPrice()))`. When only the sum is needed, which approach is simpler?
9. Design a collector that preserves **element encounter order** to return a simple CSV string. Explain why `UNORDERED` must not be declared; if CSV values contain commas, proper quoting/escaping rules are needed rather than plain string concatenation.
10. Only when you thoroughly understand thread safety, describe a container that can be used with `CONCURRENT`. Explain how concurrent updates, ordering capability, and merging are ensured.

## 15. Summary

`Collector.of()` is a tool for creating **custom collectors** by specifying their essential functions:

- `supplier` creates a new container `A` in a neutral state.
- `accumulator` folds each element `T` into `A` using a `BiConsumer`.
- `combiner` merges two containers `A` and **returns an `A`** via a `BinaryOperator`.
- `finisher` (if present) transforms container `A` into the result `R`.

The form without a finisher is suitable when **`A=R`**; the form with a finisher is appropriate when you need to convert from mutable state to another result, such as `MutableStats` to an immutable `Report`. The characteristics `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` must accurately reflect the contract, especially when the pipeline runs in parallel.
