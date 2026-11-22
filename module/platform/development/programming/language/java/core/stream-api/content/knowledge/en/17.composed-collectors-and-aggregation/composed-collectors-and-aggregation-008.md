# Finishing Results with collectingAndThen

> **Chapter:** Composed Collectors and Aggregation  
> **Module:** JAVA_STREAM_API  
> **Focus:** Use `Collectors.collectingAndThen` to apply a **finishing transformation** onto the value produced by an inner collector. This technique is especially useful when combining `groupingBy`, `partitioningBy`, `mapping`, `filtering`, `maxBy`, `summarizingInt`, and custom collectors.

## Learning objectives

After this lesson, you can:

1. Accurately explain the signature `collectingAndThen(downstream, finisher)` and the type parameters `T`, `A`, `R`, `RR`.
2. Distinguish **per-element** transformation in `map`/`mapping` from **post-collection result** transformation in `collectingAndThen`.
3. Create structurally unmodifiable results with `List.copyOf`/`Map.copyOf`, while understanding the difference between shallow and deep immutability.
4. Extract values from `Optional` returned by `maxBy`/`minBy` and handle empty data cases.
5. Finish **each group** or **the entire Map** when composing multi-level collectors.
6. Return statistics DTOs/records from `IntSummaryStatistics` or aggregated values instead of exposing mutable state.
7. Identify the impact on `IDENTITY_FINISH`, associativity of downstream collectors, parallel execution, and runtime cost.
8. Write checks for empty sources, empty groups, null data, unmodifiability, and sequential/parallel consistency.

Examples use **Java 17+**. `collectingAndThen` and `groupingBy` have existed since Java 8; `Collectors.filtering`/`flatMapping` since Java 9; `Collectors.teeing` since Java 12; `List.copyOf` since Java 10; and `Stream.toList()` and `record` since Java 16.

## 1. Why do we need a finishing step after collect?

In the Java Stream API, we commonly write a declarative pipeline:

~~~text
Data source
   │
   ├─ filter(...)       filter elements
   ├─ map(...)          transform elements
   │
   └─ collect(...)      aggregate all data
          │
          ├─ supplier    create container
          ├─ accumulator add each element to container
          ├─ combiner    merge intermediate containers
          └─ finisher    return final result
~~~

Many standard collectors produce a result that **does not yet match the type or constraints you want to publish**. For example:

- Collecting into a mutable `ArrayList`, when the API wants to return an unmodifiable `List`.
- `maxBy` returns `Optional<T>`, when business rules want `T` directly or an error when no element exists.
- `summarizingInt` returns a mutable `IntSummaryStatistics`, when the API wants an immutable `record`.
- `groupingBy` returns `Map<K, List<T>>`, when each group's list must be normalized, sorted, or structurally frozen.

We can post-process the result after `collect` returns:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> mutable = List.of(" an ", " bình ", " chi ").stream()
        .map(String::strip)
        .collect(Collectors.toList());

List<String> immutable = List.copyOf(mutable);
System.out.println(immutable); // [an, bình, chi]
~~~

Or bundle the final step directly into the collector:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> immutable = List.of(" an ", " bình ", " chi ").stream()
        .map(String::strip)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(immutable); // [an, bình, chi]
~~~

Both snippets solve the example. The value of `collectingAndThen` becomes much clearer when the finishing step is **nested inside another collector**, such as transforming only each group's list inside `groupingBy`.

## 2. API contract and flow of data types

Conceptual API signature:

~~~java
public static <T, A, R, RR> Collector<T, A, RR> collectingAndThen(
        Collector<T, A, R> downstream,
        Function<R, RR> finisher
);
~~~

Meaning of each type parameter:

| Symbol | Role | Example |
|---|---|---|
| `T` | Input element of the Stream | `Order` |
| `A` | Internal accumulation state inside downstream | `ArrayList<Order>` |
| `R` | Result produced by the downstream collector | `List<Order>` |
| `RR` | Result **after finisher completes** | Unmodifiable `List<Order>`, `Summary`, `String`... |

We can illustrate the flow:

~~~text
Stream<T>
   |
   v
downstream: Collector<T, A, R>
   |   supplier / accumulator / combiner
   v
  A (state after merging is complete)
   |
   | downstream.finisher()
   v
  R
   |
   | finisher.apply(R)
   v
  RR
~~~

`collectingAndThen` does not replace the downstream's accumulation logic: it delegates to the downstream's components and then **chains an extra finisher** to convert `R` into `RR`.

Key points to remember:

- This is a **factory method creating a Collector**, not a new Stream intermediate operation.
- The `finisher` lambda operates on **the downstream's result**; it is not invoked per input element.
- For a single `collect` producing one overall result, the outer finisher is applied to the reduced result. When this collector is a downstream of `groupingBy`, the finisher is applied to the result **of each created group**.
- `collectingAndThen` returns a collector **without the `IDENTITY_FINISH` characteristic**; other valid characteristics are inherited from the downstream.
- `finisher` must accept any valid output state of the downstream, including empty output if the source or group can be empty.

### 2.1. Do not confuse finisher with map

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> values = List.of(1, 2, 3);

List<Integer> doubled = values.stream()
        .map(n -> n * 2)
        .collect(Collectors.toList());

int count = values.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::size
        ));

System.out.println(doubled); // [2, 4, 6]
System.out.println(count);   // 3
~~~

`map` runs **per element**, whereas `List::size` receives **the already-collected list**. If the goal is merely counting elements, `stream.count()` or `Collectors.counting()` is shorter and avoids holding the entire list; this example mainly highlights where the finisher runs.

## 3. Foundational example: turning a result list into an unmodifiable snapshot

Suppose an application receives a list of names, normalizes them, and wants to publish a read-only result:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of(" An ", " Bình ", " Chi ");

List<String> result = names.stream()
        .map(String::strip)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(result); // [An, Bình, Chi]

// result.add("Dũng"); // Throws UnsupportedOperationException at runtime.
~~~

`Collectors.toList()` does not guarantee whether the resulting list is mutable or unmodifiable, nor its exact implementation class. `List.copyOf` creates a **structurally** unmodifiable List by contract and **rejects null elements**.

With data that may contain null, the finishing step can throw `NullPointerException`; you must establish a policy to validate or filter out nulls beforehand rather than assuming this collector handles missing values automatically.

### 3.1. Comparison with Collectors.toUnmodifiableList and Stream.toList

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of("a", "b", "c");

List<String> a = source.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

List<String> b = source.stream()
        .collect(Collectors.toUnmodifiableList());

List<String> c = source.stream()
        .toList();
~~~

All three results in the example forbid adding, removing, or replacing elements through the List API. However:

| Form | Version | When appropriate |
|---|---|---|
| `collectingAndThen(toList(), List::copyOf)` | Java 10+ | Need custom finishing structure, or as a downstream in multi-level collectors |
| `Collectors.toUnmodifiableList()` | Java 10+ | Simply want to collect into an unmodifiable list; rejects nulls |
| `Stream.toList()` | Java 16+ | Simple terminal operation creating an unmodifiable list; cannot replace a downstream `Collector` when nesting |

For tasks needing only a structurally unmodifiable list, `toUnmodifiableList` or `Stream.toList` is usually shorter. `collectingAndThen` shines when you need **a finishing step not directly expressed by standard collectors**, or **a finished list inside each group**.

### 3.2. Structural immutability is not deep immutability

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

final class Note {
    String title;
    Note(String title) { this.title = title; }
}

Note original = new Note("Draft");

List<Note> notes = List.of(original).stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

original.title = "Edited";

System.out.println(notes.get(0).title); // Edited
~~~

`List.copyOf` does not deep-copy each `Note`; it holds references to the objects. If you need an immutable snapshot of **inner data as well**, convert mutable objects to immutable DTOs/`record`s before collecting or perform appropriate defensive copying.

## 4. Sorting or normalizing results in the finisher

A finisher can produce a different output type, sort a list, or express a post-processing step that runs only after the downstream finishes.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

List<String> values = List.of("chi", "an", "binh");

List<String> sorted = values.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> {
                    ArrayList<String> copy = new ArrayList<>(list);
                    copy.sort(Comparator.naturalOrder());
                    return List.copyOf(copy);
                }
        ));

System.out.println(sorted); // [an, binh, chi]
~~~

Here:

1. `toList()` collects the elements.
2. The finisher receives the resulting list.
3. Creates a copy to make data ownership explicit.
4. Sorts the copy.
5. Returns an unmodifiable list.

**There is a shorter way for a global sort:**

~~~java
List<String> sorted = values.stream()
        .sorted()
        .toList();
~~~

Using `collectingAndThen` is more worthwhile when sorting **each group's list separately** or when the finisher performs custom normalization.

### 4.1. Do not require the finisher to mutate the downstream result in place

~~~java
list -> {
    list.sort(Comparator.naturalOrder()); // Works if list is mutable.
    return List.copyOf(list);
}
~~~

The pattern above works if you know for certain that the downstream creates a mutable list; however, writing a finisher **that does not depend on mutability** of the result is more reusable. For example, use `list.stream().sorted().toList()` on Java 16+.

A finisher with side effects on a collection shared outside the pipeline is usually unnecessary. Prefer returning **a new value** and keeping finishing logic explicit.

## 5. Optional from maxBy/minBy: defining a policy for missing data

`Collectors.maxBy(comparator)` returns `Optional<T>` because a data group can be empty. `collectingAndThen` lets you decide the final result type directly:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

record Product(String code, int price) {}

List<Product> products = List.of(
        new Product("PEN", 15),
        new Product("BOOK", 45),
        new Product("BAG", 120)
);

Product mostExpensive = products.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(Comparator.comparingInt(Product::price)),
                optional -> optional.orElseThrow(
                        () -> new IllegalStateException("Empty list")
                )
        ));

System.out.println(mostExpensive.code()); // BAG
~~~

Here:

- Downstream `maxBy` produces `Optional<Product>`.
- The finisher turns `Optional<Product>` into `Product` or throws the specified error.
- `optional.orElseThrow()` is only appropriate if the output contract **requires an element to exist**.

For a plain Stream, `products.stream().max(comparator)` can be clearer. Combining with `collectingAndThen` proves its worth when placed **inside `groupingBy`** to obtain the single best representative for each group.

### 5.1. You can keep Optional instead of forcing a value

~~~java
import java.util.Optional;

Optional<Product> max = products.stream()
        .collect(Collectors.maxBy(
                Comparator.comparingInt(Product::price)
        ));
~~~

If business rules allow an empty source, returning `Optional<Product>` is usually more honest than throwing an error or picking a fake “default” product. `collectingAndThen` does not force you to unwrap `Optional`; it simply provides a hook to do so **when requirements call for it**.

## 6. groupingBy + collectingAndThen: finishing each group

Suppose orders have a category. You want to return `Map<String, List<Order>>` such that **each category's list** is structurally unmodifiable.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String id, String category, long amount) {}

List<Order> orders = List.of(
        new Order("O-01", "BOOK", 100),
        new Order("O-02", "PEN", 30),
        new Order("O-03", "BOOK", 200),
        new Order("O-04", "PEN", 70)
);

Map<String, List<Order>> byCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf
                )
        ));

System.out.println(byCategory.get("BOOK").size()); // 2
// byCategory.get("BOOK").add(...); // UnsupportedOperationException.
~~~

Looking at the structure:

~~~text
orders.stream()
   |
   v
groupingBy(Order::category,
     collectingAndThen(
         toList(),       -- builds list for each key
         List::copyOf    -- finishes each list
     )
   )
   |
   v
{
  "BOOK": immutableList[O-01, O-03],
  "PEN" : immutableList[O-02, O-04]
}
~~~

**Important boundary:** `List.copyOf` is called for **each collected group value**, not for each `Order`. It also **does not automatically make the outermost Map unmodifiable**. Callers could still insert a new key into a mutable Map if the supplied Map supports it; the `groupingBy` API guarantees no specific Map mutability contract.

### 6.1. Sorting each group before publishing

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> byAmountDesc = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        list -> list.stream()
                                .sorted(
                                        Comparator
                                                .comparingLong(Order::amount)
                                                .reversed()
                                                .thenComparing(Order::id)
                                )
                                .toList()
                )
        ));

System.out.println(byAmountDesc.get("BOOK")
        .stream().map(Order::id).toList()); // [O-03, O-01]
~~~

For records with equal `amount`, `thenComparing(Order::id)` defines a deterministic order by order ID. `Stream.toList()` in the finisher returns a structurally unmodifiable list.

Note that this approach must retain all elements of a group before sorting; if you only need the highest-value order in each group, use `maxBy` instead of buffering the whole list.

## 7. Two layers of collectingAndThen: protecting both Map keys and group lists

If an API wants to publish **both the Map and every inner List** as structurally unmodifiable, you can finish at two levels:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> immutableIndex = orders.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(
                        Order::category,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf
                        )
                ),
                Map::copyOf
        ));

// immutableIndex.put("OTHER", List.of()); // UnsupportedOperationException.
// immutableIndex.get("BOOK").add(...);     // UnsupportedOperationException.
~~~

Reading from inside out:

1. Each order is classified by `category`.
2. Downstream `toList` builds a list for each category.
3. The **inner** `List.copyOf` finisher protects the structure of each list.
4. `groupingBy` builds `Map<String, List<Order>>`.
5. The **outer** `Map.copyOf` finisher protects the structure of the Map.

~~~text
Stream<Order>
   |
   v
groupingBy(category)
   ├─ BOOK -> toList() -> List.copyOf(...)
   └─ PEN  -> toList() -> List.copyOf(...)
   |
   v
Map<String, List<Order>>
   |
   v
Map.copyOf(...)
   |
   v
Unmodifiable Map + unmodifiable value Lists
~~~

`Map.copyOf` does not deep-copy `Order` elements. In the example, `Order` is a record containing only `String` and `long`, so the fields used are stable; with mutable value objects, you must design a separate deep snapshot.

**Key difference:** placing `collectingAndThen` **only outside** `groupingBy` and calling `Map.copyOf` will **not** make the inner lists unmodifiable. That is why we must distinguish “finishing each group” from “finishing the entire result”.

## 8. groupingBy + maxBy + collectingAndThen: one representative per group

Requirement: get the **largest order in each category**, returning `Order` directly instead of `Optional<Order>` in the Map.

~~~java
import java.util.Comparator;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Order> largestByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.maxBy(
                                Comparator.comparingLong(Order::amount)
                                        .thenComparing(Order::id)
                        ),
                        optional -> optional.orElseThrow(
                                () -> new IllegalStateException("Empty group")
                        )
                )
        ));

System.out.println(largestByCategory.get("BOOK").id()); // O-03
System.out.println(largestByCategory.get("PEN").id());  // O-04
~~~

With standard `groupingBy`, every key in the Map is created from at least one source element, so `maxBy` for that group has a value if the source is valid and does not drop elements. Still, the finisher should have an explicit policy for `Optional.empty()` so the collector can be understood and tested independently.

When the **entire Stream is empty**, `groupingBy` returns an empty Map; it **does not** invent a dummy key and call that group's finisher. Do not confuse this with `partitioningBy`, which populates both Boolean keys.

### 8.1. When priority order must be explicit

When multiple orders have the same amount, a comparator looking only at `amount` can pick any tied element without expressing a business tie-breaker. Use `thenComparing(Order::id)` when ID is an appropriate tie-breaker, or state an explicit conflict rule.

If monetary values can exceed `long` limits, choose appropriate data types and comparators; a finisher cannot repair an aggregate that already overflowed in earlier steps.

## 9. mapping and collectingAndThen: convert type then finish a group

Suppose an API needs an index `Map<String, List<String>>` of **order IDs** per category instead of keeping full `Order` objects.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<String>> idsByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.mapping(
                                Order::id,
                                Collectors.toList()
                        ),
                        List::copyOf
                )
        ));

System.out.println(idsByCategory.get("BOOK")); // [O-01, O-03]
~~~

Processing flow:

~~~text
Order -> group(category)
            |
            v
        mapping(Order::id)
            |
            v
         toList()
            |
            v
        List.copyOf()
            |
            v
       List<String> per group
~~~

`mapping` transforms **elements entering the downstream**; `collectingAndThen` finishes the **downstream result**. Composing them is a common pattern in multi-level collectors.

### 9.1. Sorting IDs within each group

~~~java
Map<String, List<String>> sortedIds = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.mapping(Order::id, Collectors.toList()),
                        ids -> ids.stream().sorted().toList()
                )
        ));

System.out.println(sortedIds.get("BOOK")); // [O-01, O-03]
~~~

With `List<String>`, `String::compareTo` defines natural order. If you want to sort by `Order`'s `amount` and keep only the ID, sort `Order` before mapping to `String`, or choose a more suitable downstream; once amount information is discarded, the finisher cannot naturally recover it.

## 10. filtering/flatMapping in downstream: never confuse empty groups with missing keys

`Collectors.filtering` (Java 9+) filters **downstream elements**, differing from `stream.filter` before `groupingBy` in that a group can still exist even if all its elements are rejected by the downstream.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Ticket(String id, String team, boolean resolved) {}

List<Ticket> tickets = List.of(
        new Ticket("T-01", "CORE", false),
        new Ticket("T-02", "CORE", true),
        new Ticket("T-03", "UI", true)
);

Map<String, List<String>> unresolvedIds = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.collectingAndThen(
                        Collectors.filtering(
                                ticket -> !ticket.resolved(),
                                Collectors.mapping(
                                        Ticket::id,
                                        Collectors.toList()
                                )
                        ),
                        List::copyOf
                )
        ));

System.out.println(unresolvedIds.get("CORE")); // [T-01]
System.out.println(unresolvedIds.get("UI"));   // []
~~~

The `"UI"` group **is in the Map** because a UI team ticket reached `groupingBy`; downstream `filtering` merely excluded values from that group's list.

If filtered **before** grouping:

~~~java
Map<String, List<String>> onlyUnresolvedGroups = tickets.stream()
        .filter(ticket -> !ticket.resolved())
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.mapping(Ticket::id, Collectors.toList())
        ));

System.out.println(onlyUnresolvedGroups.containsKey("UI")); // false
~~~

Those are **two different data contracts**. When finishing results with `List.copyOf`, an empty list is still a valid result when business rules allow empty groups.

### 10.1. flatMapping + collectingAndThen

When each order contains multiple product codes, `flatMapping` (Java 9+) lets you emit multiple values into each group's downstream.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Basket(String owner, List<String> productCodes) {}

List<Basket> baskets = List.of(
        new Basket("An", List.of("PEN", "BOOK")),
        new Basket("An", List.of("BAG")),
        new Basket("Bình", List.of("BOOK"))
);

Map<String, List<String>> codesByOwner = baskets.stream()
        .collect(Collectors.groupingBy(
                Basket::owner,
                Collectors.collectingAndThen(
                        Collectors.flatMapping(
                                basket -> basket.productCodes().stream(),
                                Collectors.toList()
                        ),
                        List::copyOf
                )
        ));

System.out.println(codesByOwner.get("An")); // [PEN, BOOK, BAG]
~~~

`flatMapping` closes each child Stream returned by the mapper per contract. The `List.copyOf` finisher runs only on the collected list; it **does not** participate in reading child sources or managing resources of individual child Streams.

If the code list can contain null, `List.copyOf` will reject the result; choose a null policy right at input or element transformation time.

## 11. partitioningBy + collectingAndThen: finishing both Boolean branches

`partitioningBy` produces results under two keys `true` and `false`. Example splitting resolved vs. unresolved tickets:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Ticket>> partitioned = tickets.stream()
        .collect(Collectors.partitioningBy(
                Ticket::resolved,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf
                )
        ));

System.out.println(partitioned.get(true).size());  // 2
System.out.println(partitioned.get(false).size()); // 1
~~~

Characteristics:

- `true` represents the `resolved` group.
- `false` represents the unresolved group.
- The downstream collector is finished **separately for each branch**.
- Unlike `groupingBy`, the result of `partitioningBy` contains **both Boolean keys**, even when one branch has no elements.

### 11.1. When the Stream is empty

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Ticket>> emptyPartitions =
        List.<Ticket>of().stream()
                .collect(Collectors.partitioningBy(
                        Ticket::resolved,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf
                        )
                ));

System.out.println(emptyPartitions.get(true));  // []
System.out.println(emptyPartitions.get(false)); // []
~~~

This explains why the downstream's finisher **must handle an empty list** when used inside `partitioningBy`. Never write `list.get(0)` in a finisher without handling the empty case.

## 12. Turning IntSummaryStatistics into a result record

`Collectors.summarizingInt` collects count, sum, min/max values, and average into a mutable `IntSummaryStatistics`. If you want to expose an immutable statistics object matching a business interface, `collectingAndThen` helps convert the type.

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.Collectors;

record Stats(
        long count,
        long total,
        OptionalInt min,
        OptionalInt max,
        OptionalDouble average
) {}

List<Integer> scores = List.of(5, 10, 8, 7);

Stats stats = scores.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.summarizingInt(Integer::intValue),
                s -> new Stats(
                        s.getCount(),
                        s.getSum(),
                        s.getCount() == 0
                                ? OptionalInt.empty()
                                : OptionalInt.of(s.getMin()),
                        s.getCount() == 0
                                ? OptionalInt.empty()
                                : OptionalInt.of(s.getMax()),
                        s.getCount() == 0
                                ? OptionalDouble.empty()
                                : OptionalDouble.of(s.getAverage())
                )
        ));

System.out.println(stats.count());               // 4
System.out.println(stats.total());               // 30
System.out.println(stats.average().orElseThrow()); // 7.5
~~~

Points to distinguish:

- The downstream computes statistics via its own accumulation and combining operations.
- The finisher **does not** recompute over the whole list; it simply reads post-collection metrics.
- On an empty source, `getMin()`/`getMax()` of `IntSummaryStatistics` hold primitive sentinel values; the example above converts them to `OptionalInt.empty()` instead of publishing nonexistent min/max values.
- `getAverage()` uses `double`; if business rules require an exact decimal average, use a suitable sum/count and rounding algorithm instead of merely wrapping `IntSummaryStatistics`.
- `summarizingInt`'s sum uses `long`, which **can still overflow** for datasets exceeding the `long` range. A finisher cannot fix an already-incorrect sum.

### 12.1. Statistics by group

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Stats> statsByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.summarizingInt(
                                order -> Math.toIntExact(order.amount())
                        ),
                        s -> new Stats(
                                s.getCount(),
                                s.getSum(),
                                s.getCount() == 0
                                        ? OptionalInt.empty()
                                        : OptionalInt.of(s.getMin()),
                                s.getCount() == 0
                                        ? OptionalInt.empty()
                                        : OptionalInt.of(s.getMax()),
                                s.getCount() == 0
                                        ? OptionalDouble.empty()
                                        : OptionalDouble.of(s.getAverage())
                        )
                )
        ));
~~~

Here `Order.amount()` in the example is `long` and converted via `Math.toIntExact`; if data can exceed `int` range, the conversion will throw `ArithmeticException`. This is **only** an illustration connecting to `summarizingInt`; in a real system, choose `summarizingLong(Order::amount)` or a `BigInteger` accumulator to better fit the data domain.

Never silently cast `(int) order.amount()` when values risk overflowing `int`.

## 13. Using collectingAndThen to validate constraints on the final result

Not every finisher converts to an unmodifiable collection. It can also perform **validation** on the aggregated result.

For example, a batch of sales **must contain at least one sale** and the total cents must be non-negative:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record Sale(long cents) {}
record SaleSummary(long count, BigInteger total) {}

Collector<Sale, ?, SaleSummary> validatedSummary =
        Collectors.collectingAndThen(
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.mapping(
                                sale -> BigInteger.valueOf(sale.cents()),
                                Collectors.reducing(
                                        BigInteger.ZERO,
                                        BigInteger::add
                                )
                        ),
                        SaleSummary::new
                ),
                summary -> {
                    if (summary.count() == 0) {
                        throw new IllegalStateException("Empty batch");
                    }
                    if (summary.total().signum() < 0) {
                        throw new IllegalStateException("Negative total amount");
                    }
                    return summary;
                }
        );

List<Sale> sales = List.of(new Sale(100), new Sale(-20));
SaleSummary result = sales.parallelStream().collect(validatedSummary);

System.out.println(result); // SaleSummary[count=2, total=80]
~~~

`Collectors.teeing` (Java 12+) feeds **two downstream collectors** over the same element stream: one branch counts, one sums `BigInteger`; then the merger creates `SaleSummary`. `collectingAndThen` then **validates the complete summary**.

Even though `teeing` means “splitting into two branches”, it does not mean each branch necessarily runs on two separate threads; it describes collection structure, not a guaranteed physical execution plan.

**When is collectingAndThen unnecessary?** If validation and output normalization already fit cleanly inside `teeing`'s merger or a custom collector's finisher, an extra wrapper may be unnecessary. Pick whichever makes the contract clearest.

## 14. A finisher cannot fix a broken accumulation

A Collector that is valid under parallel execution still requires:

- `supplier` creates a proper empty state.
- `accumulator` adds elements per contract.
- `combiner` merges two states preserving **identity** and **associativity**.
- `finisher` converts the completed state into the final result per contract.

`collectingAndThen` only replaces/chains the last step. It **cannot turn a broken combiner into a valid one**.

~~~text
Partition A -> accumulator(A) ---\
                                   combiner() -> combined state
Partition B -> accumulator(B) ---/                  |
                                                    v
                                      downstream.finisher()
                                                    |
                                                    v
                                       extra finisher from
                                        collectingAndThen
                                                    |
                                                    v
                                          published result
~~~

Classic bug example: each partition computes an average, and the combiner takes the average of the two averages without accounting for partition sizes. No matter how nicely the finisher formats the result afterward, it will still be wrong if the two partitions had different element counts.

Right way: keep `sum` and `count` in the state, let the combiner add both fields, and only divide in the final finisher according to the chosen arithmetic rule.

### 14.1. Round after merging, not inside every merge

For currency or decimals, if business rules require **summing exact decimals and rounding once at the end**, you can use a downstream with `BigDecimal::add` (without `MathContext`) and then apply `setScale` in the finisher.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.stream.Collectors;

List<BigDecimal> amounts = List.of(
        new BigDecimal("1.235"),
        new BigDecimal("2.235"),
        new BigDecimal("3.235")
);

BigDecimal roundedTotal = amounts.parallelStream()
        .collect(Collectors.collectingAndThen(
                Collectors.reducing(
                        BigDecimal.ZERO,
                        BigDecimal::add
                ),
                total -> total.setScale(2, RoundingMode.HALF_UP)
        ));

System.out.println(roundedTotal); // 6.71
~~~

Since `1.235 + 2.235 + 3.235 = 6.705`, rounding `HALF_UP` to two decimal places yields `6.71`. If business rules require **rounding each transaction before summing**, the result can differ; establish the rule before choosing the collector.

The finisher is the natural place for *final rounding*, yet it must never be used to mask overflow that already occurred in the accumulator or precision loss from misusing `double`.

## 15. Characteristics: why is IDENTITY_FINISH removed?

The `Collector.Characteristics.IDENTITY_FINISH` contract permits the framework to skip the finisher step when converting the accumulation state to the final result is considered an identity in both type and behavior. `collectingAndThen` adds a real finishing step and therefore **removes `IDENTITY_FINISH`**.

~~~java
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, List<String>> ordinary =
        Collectors.toList();

Collector<String, ?, List<String>> finished =
        Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        );

System.out.println(
        ordinary.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH
        )
);

System.out.println(
        finished.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH
        )
); // false
~~~

The first print may be `true` for `Collectors.toList()` under typical configurations, yet the key check for `collectingAndThen` is that **the result no longer has `IDENTITY_FINISH`**. Never manually attach that flag to a collector that genuinely needs to run `List.copyOf`, statistics normalization, or validation: the framework could skip the final step your application relies on.

Other characteristics such as `CONCURRENT` and `UNORDERED` (when present on the downstream and still valid) are inherited. Still, the fact that **a collector permits** concurrent accumulation does not mean the finisher runs per element or that every run uses a single thread schedule.

### 15.1. Can it be used on parallelStream?

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> parallelGroups = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf
                )
        ));
~~~

With standard downstream collectors that honor the contract, Stream can create separate containers and merge them before finishing each group. The finisher sees the **already-merged** result, not a single isolated partition.

However:

- Ensure key-extracting lambdas, transformations, and custom collectors are **non-interfering/stateless** per contract.
- Do not take parallel speedups for granted; small groups and few elements can run slower due to merging overhead.
- If sorting groups inside the finisher, sorting cost can be significant.
- Compare sequential and parallel results against the **data contract**, not `HashMap` iteration order when order is not guaranteed.

## 16. Ordering, null, and immutability: three easily misunderstood limits

### 16.1. collectingAndThen does not sort automatically

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = List.of(3, 1, 2);

List<Integer> result = source.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(result); // [3, 1, 2]
~~~

`List.copyOf` does not reorder elements; it preserves the iteration order of the passed-in list. If you need `[1, 2, 3]`, sort beforehand or inside the finisher. With a downstream collector that does not guarantee order, `collectingAndThen` creates no new guarantee.

### 16.2. collectingAndThen does not filter out null automatically

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> source = new ArrayList<>(
        Arrays.asList("A", null, "B")
);

// Throws NullPointerException when the List.copyOf finisher encounters null:
// List<String> result = source.stream()
//         .collect(Collectors.collectingAndThen(
//                 Collectors.toList(), List::copyOf
//         ));
~~~

If business rules allow dropping null values, filter beforehand:

~~~java
import java.util.Objects;

List<String> cleaned = source.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));

System.out.println(cleaned); // [A, B]
~~~

If null is a data error, raise an error instead of silently dropping elements. `collectingAndThen` does not impose a null policy on behalf of business logic.

### 16.3. Protecting the outer Map does not protect inner lists

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> outerOnly = orders.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(Order::category),
                Map::copyOf
        ));
~~~

The resulting Map is structurally unmodifiable, yet **the List in each group can still be mutable**. To protect both layers, use two `collectingAndThen` layers as in section 7.

### 16.4. Collections.unmodifiableList is a view; List.copyOf is a structural snapshot

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> original = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(original);
List<String> copy = List.copyOf(original);

original.add("B");

System.out.println(view); // [A, B]
System.out.println(copy); // [A]
~~~

`unmodifiableList` blocks changes **through the view**, yet the view's contents can still change if the underlying list is modified elsewhere. `List.copyOf` produces a result whose structure does not change over time due to edits to `original`. Both can still reference **mutable elements**.

## 17. When should you not use collectingAndThen?

Not every final step needs a wrapped finisher. The table below helps make clear choices:

| Goal | Usually preferred | When collectingAndThen helps |
|---|---|---|
| Create an unmodifiable List from a Stream | `Stream.toList()` (Java 16+) or `toUnmodifiableList` | When placed inside `groupingBy` downstream or adding final logic |
| Create an unmodifiable Set | `toUnmodifiableSet` | When extra validation, conversion, or logic is needed |
| Get max/min of a Stream | `stream.max/min` | When you want a Map of key → max/min value without Optional |
| Only count elements | `count()` or `Collectors.counting()` | When turning count into a DTO/label at the group level |
| Flatten or transform elements | `flatMap`/`map` or `flatMapping`/`mapping` | When post-processing the **entire** collected list is also needed |
| Group and keep regular Lists | `groupingBy(classifier)` | When group lists must be sorted/frozen |
| Exact sum | `reduce` or appropriate numeric collector | When **one final** validation/rounding step is needed |
| Partition by Boolean | `partitioningBy` | When each branch needs custom normalization |
| Build a DTO from two metrics | `teeing` with merger | When post-merger validation/normalization is an independent step |

`collectingAndThen` can be a poor choice when the finisher has to iterate or copy a huge collection while the problem actually only needs a single simple number. For `count`, collecting a list and calling `size` raises memory cost from O(1) for a counter to O(n) for a list.

## 18. Performance and resource lifecycle

Notes when using composed collectors:

- **Memory allocation:** `toList` followed by `List.copyOf` may copy arrays/references depending on JDK and downstream implementation. Never assume `collectingAndThen` is “free”.
- **Finisher frequency:** a finisher after global collection differs from a finisher per **each group**. With hundreds of thousands of groups, per-group finishing cost can be substantial.
- **No replacement for algorithms:** if you only need min/max, do not collect a whole list and `sort` just to pick one element. `maxBy` is better suited.
- **Short-circuiting:** `collect` is a terminal operation that generally must process all required elements; `collectingAndThen` does not add early termination like `findFirst` or `anyMatch`.
- **I/O sources:** if the source is `Files.lines`, manage the Stream lifecycle with `try-with-resources`. The finisher does not automatically close I/O sources.
- **Precision:** if the downstream already miscalculated due to overflow or per-combiner rounding, reformatting or rounding again in the finisher cannot restore the right result.

Example using `Files.lines` to collect non-empty lines into a list snapshot:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Path path = Path.of("application.log");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> snapshot = lines
            .filter(line -> !line.isBlank())
            .collect(Collectors.collectingAndThen(
                    Collectors.toList(),
                    List::copyOf
            ));

    System.out.println("Line count: " + snapshot.size());
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Cannot read file: " + ex.getMessage());
}
~~~

`try-with-resources` manages closing the file source; `List.copyOf` only finishes the in-memory result and is not responsible for the lifecycle of `Files.lines`. For huge files, holding every line in memory may be inappropriate; choose a more compact aggregating downstream instead.

## 19. Testing collectingAndThen against its contract

When designing a test suite, establish an **oracle** or specific expected results and test across these dimensions:

| Case | What to verify |
|---|---|
| Empty Stream | Does the finisher handle an empty downstream result? |
| Single element | Final type and value are right; no spurious data added |
| Multiple groups | Finisher applies separately to each group |
| Group with zero elements after downstream filtering | Is an empty list valid or should it fail? |
| Empty `partitioningBy` | Both `true` and `false` are still finished |
| Null data | Filtered/rejected as required; `List.copyOf`/`Map.copyOf` reject null |
| Outer Map protection | `put` fails if the Map was frozen |
| Inner List protection | `add` fails if group lists were frozen |
| Mutable values inside List | Do not confuse structural immutability with deep copy |
| Sequential vs. parallel | Compare results per contract, not unguaranteed `Map` iteration order |
| Custom collector | Supplier/accumulator/combiner still preserve identity and associativity |
| Arithmetic correctness | No overflow, rounding happens at the right point |

### 19.1. Small test program: protecting both levels

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class CollectingAndThenCheck {
    record Order(String id, String category) {}

    static Map<String, List<Order>> index(List<Order> orders) {
        return orders.stream()
                .collect(Collectors.collectingAndThen(
                        Collectors.groupingBy(
                                Order::category,
                                Collectors.collectingAndThen(
                                        Collectors.toList(),
                                        List::copyOf
                                )
                        ),
                        Map::copyOf
                ));
    }

    public static void main(String[] args) {
        List<Order> data = List.of(
                new Order("A", "BOOK"),
                new Order("B", "PEN"),
                new Order("C", "BOOK")
        );

        Map<String, List<Order>> sequential = index(data);
        Map<String, List<Order>> parallel = data.parallelStream()
                .collect(Collectors.collectingAndThen(
                        Collectors.groupingBy(
                                Order::category,
                                Collectors.collectingAndThen(
                                        Collectors.toList(),
                                        List::copyOf
                                )
                        ),
                        Map::copyOf
                ));

        if (!sequential.equals(parallel)) {
            throw new AssertionError("Parallel differs from sequential");
        }
        if (sequential.get("BOOK").size() != 2) {
            throw new AssertionError("Wrong BOOK count");
        }

        try {
            sequential.put("OTHER", List.of());
            throw new AssertionError("Map is still mutable");
        } catch (UnsupportedOperationException expected) {
            // PASS: Map is unmodifiable.
        }

        try {
            sequential.get("BOOK").add(new Order("D", "BOOK"));
            throw new AssertionError("Group list is still mutable");
        } catch (UnsupportedOperationException expected) {
            // PASS: Group list is unmodifiable.
        }

        Map<String, List<Order>> empty = index(List.of());
        if (!empty.isEmpty()) {
            throw new AssertionError("Empty source must yield empty Map");
        }

        System.out.println("PASS");
    }
}
~~~

This is an illustrative example, **not a substitute for a full domain test suite**. In practice, you also need to test null keys/values, required ordering, mutable objects, large data volumes, and downstream collectors with complex aggregations. Equal sequential and parallel outputs **are not enough** if both share a buggy accumulator; cross-check small datasets against hand-computed answers and statistical invariants.

### 19.2. Do not use side effects to count finisher invocations

~~~java
// Avoid business logic like:
// AtomicInteger calls = new AtomicInteger();
// collectingAndThen(toList(), list -> {
//     calls.incrementAndGet(); // Depends on the pipeline structure using the collector
//     return List.copyOf(list);
// });
~~~

In nested collectors, the number of finishing calls depends on how many downstream results are created (such as group count). Logging/metrics can help diagnostics, yet you should never turn finisher call counts into business data or rely on them for external synchronization.

## 20. Self-check exercises (with answers)

### Exercise 1. What does the finisher receive?

**Prompt:** With `collectingAndThen(toList(), List::copyOf)` on `Stream<String>`, is `List::copyOf` called for each String or for the list?

**Answer:** It receives **the list collected by the downstream**, not individual Strings. `toList` performs accumulation; `List.copyOf` finishes the List result.

### Exercise 2. Outer Map and group lists

**Prompt:** Does `collectingAndThen(groupingBy(Order::category), Map::copyOf)` guarantee that the list in each group is unmodifiable?

**Answer:** No. It protects the outer Map structure, but does not automatically protect group lists. You need `collectingAndThen(toList(), List::copyOf)` as the inner downstream of `groupingBy`.

### Exercise 3. maxBy and Optional

**Prompt:** Why does `maxBy` return `Optional<Order>`? When should you use an `orElseThrow` finisher?

**Answer:** The source can be empty and have no maximum element. `orElseThrow` is only appropriate when a result is **mandatory**, such as an existing group that by business rules cannot be empty; if an empty source is a normal state, keep `Optional` or represent missing data explicitly.

### Exercise 4. groupingBy and filtering

**Prompt:** A `UI` group has tickets, all already resolved. Why does `groupingBy(Ticket::team, filtering(notResolved, collectingAndThen(toList(), List::copyOf)))` still contain the `UI` key?

**Answer:** `groupingBy` creates the key when processing the UI ticket, while downstream `filtering` excludes elements from the list **of the already-created key**. The `UI` group result is an empty list, not an absent key.

### Exercise 5. Empty partitioningBy

**Prompt:** Collecting an empty Stream with `partitioningBy(predicate, collectingAndThen(toList(), List::copyOf))` yields which keys?

**Answer:** Both `true` and `false`, each mapped to an unmodifiable empty list. The finisher in this branch must handle an empty list.

### Exercise 6. Where does rounding belong?

**Prompt:** `BigDecimal` values are allowed to be summed exactly and rounded once at the very end. Is a finisher appropriate?

**Answer:** Yes. Use downstream `reducing(BigDecimal.ZERO, BigDecimal::add)` with no intermediate rounding, followed by finisher `total -> total.setScale(2, RoundingMode.HALF_UP)`. If business rules require rounding each transaction individually, do that before combining.

### Exercise 7. IDENTITY_FINISH

**Prompt:** Does a `toList` collector wrapped with `collectingAndThen(toList(), List::copyOf)` still have `IDENTITY_FINISH`?

**Answer:** No. `List.copyOf` is a meaningful finisher, so the resulting collector strips the `IDENTITY_FINISH` characteristic. If the framework skipped the final step, structural unmodifiability would not be guaranteed.

### Exercise 8. Shallow immutability

**Prompt:** A list created with `List.copyOf` holds mutable `Note` objects. Does modifying `Note.title` through another reference affect the element inside the list?

**Answer:** Yes, it can. `List.copyOf` does not deep-copy values. The list forbids adding/removing elements, yet still holds references to mutable `Note` instances. Use an immutable DTO model or deep defensive copies if you need a truly stable data snapshot.

### Exercise 9. Can a finisher fix a wrong combiner?

**Prompt:** A downstream collector for computing an average merges two partitions by taking the unweighted average of the two averages. Can `collectingAndThen` be added to make it right?

**Answer:** No. Once partition element counts are lost, the finisher cannot recover enough data. Fix the accumulator and combiner to retain/sum `sum` and `count`; only divide in the final finisher.

### Exercise 10. Picking the most concise API

**Prompt:** You only need an unmodifiable List from a Stream on Java 17, with no grouping or other post-processing. Do you have to use `collectingAndThen`?

**Answer:** No. `stream.toList()` is usually cleaner. `collectingAndThen` is useful when the finishing step must be nested inside a downstream collector or transform the result into another type/contract.

---

**Key takeaway:** `Collectors.collectingAndThen(downstream, finisher)` is the way to **chain a finishing step onto a collector's result**, without transforming individual elements. Place it **inside** `groupingBy` to finish **each group**, place it **outside** to finish **the entire Map**, or nest both when multi-level protection is required. The finishing step can freeze structure, sort, unwrap `Optional`, build statistics DTOs, or validate results. It cannot fix a broken accumulator/combiner, does not create a deep copy automatically, and does not replace proper handling of nulls, resources, precision, or performance in the Java Stream API.

