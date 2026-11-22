# Choosing the Map Type and Downstream Collector for groupingBy

## 1. Grouping Is More Than Choosing a Key

In **JAVA_STREAM_API**, we often start with a declarative pipeline: obtain data, `filter` valid records, `map` to the required form, and use `collect` to produce the result. When you want to gather elements sharing a common attribute, `Collectors.groupingBy` is the natural choice.

For example, from a list of orders, we want to know:

- **Which orders** belong to each region?
- **How many orders** are in each region?
- What is the **total revenue** of each region?
- Which **distinct product SKUs** does each region have?
- When displaying a report, should the **groups follow appearance order, alphabetical order, or no specific order**?

All of these questions can share the same grouping function, but the **Map type** and **downstream collector** determine the shape and contract of the result.

~~~text
                      Stream<Order>
                             │
                             ▼
                  groupingBy(classifier)
                             │
          ┌──────────────────┴──────────────────┐
          ▼                                     ▼
    Choose Map to hold groups             Choose downstream
    ─ HashMap (*)                         ─ toList() (*)
    ─ LinkedHashMap                       ─ counting()
    ─ TreeMap                             ─ summingLong()
    ─ EnumMap                             ─ mapping(..., toSet())
                                          ─ nested groupingBy(...)
          └──────────────────┬──────────────────┘
                             ▼
                       Map<K, D>
             group key K → group result D

(*) Description of common types, not a default guarantee
    on the concrete implementation class of Collectors.groupingBy.
~~~

This lesson belongs to the **Grouping and Partitioning** chapter. We will explore the three overloads of `groupingBy`, how to control the ordering and mutability of the Map, how to choose a downstream collector to return a `List`, `Set`, count, or statistics, along with considerations for `null`, resources, and parallel streams.

Examples use **Java 17+**. APIs such as `Collectors.mapping`, `groupingBy`, `counting`, and `summingLong` have been available since Java 8; `filtering` and `flatMapping` since Java 9; and `teeing` since Java 12.

## 2. Three Overloads of Collectors.groupingBy

General form of the API:

~~~java
// 1. Group by key, collecting each group into a List<T>.
<T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
    Function<? super T, ? extends K> classifier
);

// 2. Group by key, customizing how each group is accumulated.
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
);

// 3. Customize both the output Map and how each group is accumulated.
<T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
);
~~~

Reading each parameter:

| Component | Role | Example |
| --- | --- | --- |
| `classifier` | Computes the group key `K` from an input element. | `Order::region` |
| `mapFactory` | Creates the Map storing groups; specifies the Map implementation. | `LinkedHashMap::new` |
| `downstream` | Reduces elements **within each group** into a result `D`. | `Collectors.counting()` |
| `Map<K, D>` | Each key `K` maps to a group result of type `D`. | `Map<String, Long>` |

For the overload accepting only `classifier`, the default downstream semantically corresponds to `toList()`, so each key maps to a `List<T>`. The API **does not guarantee** the exact Map/List implementation class, mutability, serializability, or thread-safety of the default collections.

The three-parameter overload is the clearest choice when two requirements must be controlled independently: **how the Map stores the keys** and **what kind of result each key's value should be**.

## 3. Baseline Example: Grouping Orders by Region

First, use an immutable `record` to represent an order line and perform simple grouping operations. This example runs standalone on Java 17+.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupingBasics {
    record Order(
        String id,
        String region,
        String sku,
        int quantity,
        long unitPrice
    ) {
        long lineTotal() {
            return Math.multiplyExact(quantity, unitPrice);
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O1", "Nam", "BOOK", 2, 50_000L),
            new Order("O2", "Bắc", "PEN", 3, 10_000L),
            new Order("O3", "Nam", "PEN", 1, 10_000L),
            new Order("O4", "Trung", "BOOK", 1, 50_000L)
        );

        Map<String, List<Order>> grouped = orders.stream()
            .collect(Collectors.groupingBy(Order::region));

        System.out.println(grouped.get("Nam").size());  // 2
        System.out.println(grouped.get("Bắc").size());   // 1
        System.out.println(grouped.get("Trung").size()); // 1
    }
}
~~~

Here:

- `Order::region` is the classifier: each `Order` produces a group key such as `"Nam"` or `"Bắc"`.
- `groupingBy(Order::region)` returns `Map<String, List<Order>>`.
- `grouped.get("Nam")` contains two orders, `O1` and `O3`.
- You should not infer the iteration order of **Map keys** from a single print output.

We will use this `Order` structure as context in the short code snippets in later sections. When running an individual example in another class, declare the corresponding `record Order` and `orders` list.

## 4. Choosing a Map: Default, LinkedHashMap, TreeMap, and EnumMap

### 4.1. Default Map: when there is no specific key-ordering requirement

~~~java
Map<String, List<Order>> byRegion = orders.stream()
    .collect(Collectors.groupingBy(Order::region));
~~~

In common Java implementations, the result is typically stored in a `HashMap`, but the `groupingBy` specification does not guarantee a concrete Map class. Do not write code that depends on:

- The Map always being a `HashMap`.
- The Map always supporting `put` or `remove`.
- Keys always appearing in input order.
- The Map always being thread-safe.

If the business requirement is only key-based lookup and does not depend on iteration order, declaring the type as `Map<K,D>` is sufficient.

### 4.2. LinkedHashMap: first-appearance order of groups

When you need to display groups in the order they were **first encountered** in an ordered sequential pipeline, use `LinkedHashMap`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> inFirstSeenOrder = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.toList()
    ));

System.out.println(inFirstSeenOrder.keySet());
// [Nam, Bắc, Trung]
~~~

`LinkedHashMap` iterates over keys in insertion order. Because the `List` source has encounter order and this pipeline is sequential, the key `"Nam"` is inserted first, followed by `"Bắc"` and `"Trung"`. Subsequent encounters of `"Nam"` only update the existing group without moving it to the end.

This is the appropriate choice for reports that need to follow the order in which groups appear in the input data. If the source is `unordered()` or elements come from a source without encounter order, key ordering according to the original source order is no longer guaranteed.

### 4.3. TreeMap: sorted key order

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, List<Order>> sortedByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.toList()
    ));

System.out.println(sortedByRegion.keySet());
// [Bắc, Nam, Trung] according to String.compareTo.
~~~

`TreeMap` sorts keys by their natural order or by a comparator provided when creating the Map. It is suitable when the requirement specifies **alphabetical order, code order, or an explicit priority rule**.

If a custom comparator is needed:

~~~java
import java.util.Comparator;
import java.util.TreeMap;

Map<String, List<Order>> reverseOrder = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        () -> new TreeMap<>(Comparator.reverseOrder()),
        Collectors.toList()
    ));
~~~

Choose a comparator consistent with the definition of **whether two keys belong to the same group**. A `TreeMap` treats two keys as equivalent if the comparator returns `0`. If the comparator merges two keys that are not equal under `equals`, the number of groups may be smaller than expected.

### 4.4. EnumMap: keys are a finite enum

For statuses with a finite domain of values, `EnumMap` clearly expresses the key domain and orders keys by enum constant declaration order:

~~~java
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupingByStatus {
    enum Status { NEW, PAID, CANCELLED }

    record Invoice(String code, Status status) {}

    public static void main(String[] args) {
        List<Invoice> invoices = List.of(
            new Invoice("A", Status.PAID),
            new Invoice("B", Status.NEW),
            new Invoice("C", Status.PAID)
        );

        Map<Status, Long> counts = invoices.stream()
            .collect(Collectors.groupingBy(
                Invoice::status,
                () -> new EnumMap<>(Status.class),
                Collectors.counting()
            ));

        System.out.println(counts);
        // {NEW=1, PAID=2}
    }
}
~~~

`EnumMap` does not automatically create keys that have not appeared: the `CANCELLED` group is absent from the Map because no invoice has that status. To produce a report containing **all statuses including 0**, you must deliberately add the empty statuses after grouping or initialize an appropriate result structure.

### Map Selection Table

| Requirement | Typical mapFactory | Key iteration order |
| --- | --- | --- |
| Group lookup, order does not matter | Omit factory | Not guaranteed |
| Preserve first-seen group order | `LinkedHashMap::new` | Insertion order |
| Sort by key/comparator | `TreeMap::new` or supplier with comparator | Comparison order |
| Keys are an enum | `() -> new EnumMap<>(MyEnum.class)` | Enum declaration order |
| Keys need concurrent lookup in result | Consider `groupingByConcurrent` | Order not guaranteed |

## 5. Choosing a Downstream Collector: List, Set, Count, and Sum

The downstream collector determines the Map's **value** type, not its key type. The same classifier `Order::region` can produce many different reports.

### 5.1. Default: List<Order>

~~~java
Map<String, List<Order>> ordersByRegion = orders.stream()
    .collect(Collectors.groupingBy(Order::region));
~~~

Use this when you need to retain the records in each group for further processing. If the source has encounter order and the downstream collector is `toList()`, elements in each group are accumulated in encounter order; however, the **key order of the Map** still depends on the Map.

If you need to guarantee each List is **mutable**, use an explicit supplier:

~~~java
import java.util.ArrayList;

Map<String, ArrayList<Order>> editableGroups = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.toCollection(ArrayList::new)
    ));

editableGroups.get("Nam").add(
    new Order("O5", "Nam", "PAD", 1, 20_000L)
);
~~~

Do not rely on `Collectors.toList()` happening to return a mutable `ArrayList` on the current JDK: the contract does not guarantee the collection's concrete type or mutability.

### 5.2. Counting: Map<K, Long>

~~~java
Map<String, Long> orderCounts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(orderCounts.get("Nam")); // 2
System.out.println(orderCounts.get("Bắc"));  // 1
~~~

`counting()` counts **elements in the group**, not the sum of `quantity`. If you want to calculate the number of units sold, use `summingInt(Order::quantity)` or `summingLong(...)`.

### 5.3. Summing: revenue by region

~~~java
Map<String, Long> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::lineTotal)
    ));

System.out.println(revenueByRegion.get("Nam")); // 110000
System.out.println(revenueByRegion.get("Bắc"));  // 30000
System.out.println(revenueByRegion.get("Trung")); // 50000
~~~

`summingLong` returns a `Long` value for each group. If the sum may exceed the `long` range, both the multiplication `quantity * unitPrice` and the summation require an overflow policy. The example uses `Math.multiplyExact` to detect multiplication overflow; the `summingLong` collector does not automatically detect addition overflow.

### 5.4. Mapping: storing only the needed attribute

~~~java
import java.util.Set;

Map<String, Set<String>> skusByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::sku,
            Collectors.toSet()
        )
    ));

System.out.println(skusByRegion.get("Nam"));
// Contains BOOK and PEN, print order not guaranteed.
~~~

`mapping` transforms each `Order` into `sku` **inside each group**, and then `toSet` removes duplicate SKUs. This is an important difference from calling `stream.map(Order::sku)` **before grouping**: doing so loses the `region` field needed to compute the key.

If you need to preserve the first-appearance order of SKUs within each group, choose `LinkedHashSet`:

~~~java
import java.util.LinkedHashSet;

Map<String, LinkedHashSet<String>> orderedSkus = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::sku,
            Collectors.toCollection(LinkedHashSet::new)
        )
    ));
~~~

`toSet()` does not guarantee order or mutability of the returned Set; `toCollection(LinkedHashSet::new)` explicitly selects both the structure and mutability.

## 6. Choosing a Downstream Collector to Build Sub-Maps and Multi-Level Structures

### 6.1. Two-level grouping

Problem: each region has multiple SKUs; we want the count of order lines per SKU within each region.

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Map<String, Long>> countsByRegionAndSku =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.groupingBy(
            Order::sku,
            TreeMap::new,
            Collectors.counting()
        )
    ));

System.out.println(countsByRegionAndSku);
// {Bắc={PEN=1}, Nam={BOOK=1, PEN=1}, Trung={BOOK=1}}
~~~

Here:

- The outer `TreeMap` sorts **region** keys.
- The inner `TreeMap` sorts **SKU** keys.
- `counting()` counts orders for each `(region, SKU)` pair.

If you want product unit quantities instead of line counts, replace the innermost downstream collector with `summingInt(Order::quantity)`. The result type is then `Map<String, Map<String, Integer>>`.

### 6.2. Each group holds a Map from SKU to total quantity

An SKU may appear multiple times within the same region. `Collectors.toMap` with a merge function allows merging duplicate SKUs:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Map<String, Integer>> unitsByRegionAndSku =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.toMap(
            Order::sku,
            Order::quantity,
            Integer::sum
        )
    ));

System.out.println(unitsByRegionAndSku.get("Nam"));
// {BOOK=2, PEN=1}; key order of the inner Map is not guaranteed.
~~~

If you do not pass a merge function to `toMap` and two orders have the same SKU, the collector can throw `IllegalStateException` due to duplicate keys. This differs from `groupingBy`, which is **designed to gather multiple elements sharing the same key**.

### 6.3. Result is a single summary statistic per group

When the requirement is min/max/sum/average values, prefer a downstream collector that computes them directly:

~~~java
import java.util.IntSummaryStatistics;

Map<String, IntSummaryStatistics> quantityStats = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summarizingInt(Order::quantity)
    ));

System.out.println(quantityStats.get("Nam").getCount()); // 2
System.out.println(quantityStats.get("Nam").getSum());   // 3
System.out.println(quantityStats.get("Nam").getMin());   // 1
System.out.println(quantityStats.get("Nam").getMax());   // 2
~~~

`IntSummaryStatistics` is an aggregation type with mutating operations; do not treat it as a deeply immutable value object. If you need to return it from an unmodifiable API, convert it into an immutable record or separate numeric values before publishing.

## 7. filtering and flatMapping Work *Inside* Groups

Two downstream collectors added in Java 9 help avoid writing manual loops or temporary Maps. They differ from placing `filter`/`flatMap` before `groupingBy`.

### 7.1. Downstream filtering preserves the group even when no elements match

Suppose all orders in the `"Trung"` region have a quantity below 2. We need to report all regions that appeared, but only list orders with `quantity >= 2`.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> largeOrdersByRegion =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            order -> order.quantity() >= 2,
            Collectors.toList()
        )
    ));

System.out.println(largeOrdersByRegion.get("Nam").size()); // 1
System.out.println(largeOrdersByRegion.get("Bắc").size()); // 1
System.out.println(largeOrdersByRegion.get("Trung"));      // []
~~~

`groupingBy` creates the region key first, and then `filtering` decides whether to put the `Order` into the downstream List. Therefore, the `"Trung"` region still has a key with an empty List.

Contrast this with `filter` **before** `groupingBy`:

~~~java
Map<String, List<Order>> onlyRegionsWithLargeOrders = orders.stream()
    .filter(order -> order.quantity() >= 2)
    .collect(Collectors.groupingBy(Order::region));

System.out.println(onlyRegionsWithLargeOrders.containsKey("Trung")); // false
~~~

**Choose by business requirement:** if the report must include every region that appeared (even regions with no qualifying orders), use downstream `filtering`; if you only need regions with at least one qualifying order, use upstream `filter`.

### 7.2. Downstream flatMapping emits multiple values per group

A support ticket can have multiple tags. We want the set of tags for each handling team:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class GroupTicketTags {
    record Ticket(String team, List<String> tags) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
            new Ticket("Core", List.of("java", "api")),
            new Ticket("Data", List.of("sql")),
            new Ticket("Core", List.of("api", "stream")),
            new Ticket("Data", List.of())
        );

        Map<String, Set<String>> tagsByTeam = tickets.stream()
            .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.flatMapping(
                    ticket -> ticket.tags().stream(),
                    Collectors.toSet()
                )
            ));

        System.out.println(tagsByTeam.get("Core"));
        // Contains java, api, stream; order is not guaranteed.
    }
}
~~~

`flatMapping` turns each element in the group into a sub-Stream and sends that Stream's elements to the next collector. If the sub-Stream requires closing resources, closing is managed by `flatMapping` per contract; nevertheless, external resources outside the pipeline must still be managed properly.

If a team only has empty tag lists, that team still gets a group and the result is an empty Set. Placing `flatMap` before grouping would lose the classifier information if the tags no longer carry the team name.

## 8. Downstream Collectors Combining Multiple Aggregations: collectingAndThen and teeing

### 8.1. collectingAndThen to finalize each group's result

With `Collectors.collectingAndThen(downstream, finisher)`, we let a downstream collector finish accumulating and then apply a final transformation step.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> readonlyLists = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.collectingAndThen(
            Collectors.toList(),
            List::copyOf
        )
    ));
~~~

The inner Lists are unmodifiable. The **outer Map** still follows the general `groupingBy` contract and does not automatically become an unmodifiable Map. Additionally, `List.copyOf` does not accept `null` elements.

If you explicitly want both an **insertion-ordered Map and unmodifiable Lists**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> result = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.toUnmodifiableList()
    ));
~~~

The result has a `LinkedHashMap` structure and each List is unmodifiable; the Map itself is still a mutable LinkedHashMap. To publish a structurally unmodifiable result at both levels, you can wrap a copy of the Map:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;

Map<String, List<Order>> immutableStructure =
    Collections.unmodifiableMap(new LinkedHashMap<>(result));
~~~

The `Order` instances are immutable records for the fields stored in the example, so the sample data is close to an immutable snapshot. With mutable child objects, wrapping the Map and Lists **does not automatically make the object graph deeply immutable**.

### 8.2. teeing to compute two metrics in a single pass

Since Java 12, `Collectors.teeing` lets two downstream collectors process the same stream and merges their results with a function.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupCountAndRevenue {
    record Order(String region, int quantity, long unitPrice) {
        long total() {
            return Math.multiplyExact(quantity, unitPrice);
        }
    }

    record Summary(long orderCount, long revenue) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("Nam", 2, 50_000L),
            new Order("Bắc", 3, 10_000L),
            new Order("Nam", 1, 10_000L)
        );

        Map<String, Summary> reports = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingLong(Order::total),
                    Summary::new
                )
            ));

        System.out.println(reports.get("Nam"));
        // Summary[orderCount=2, revenue=110000]
    }
}
~~~

In this example, the group key is `String`, and the downstream collector returns an immutable `Summary` with two metrics. You do not have to build a `List<Order>` for each group and iterate over it again to count and sum. However, all integer arithmetic must still remain within `long` limits, and `teeing` does not make operations with side effects safe.

## 9. Mutability, Ordering, and Null Behavior of Grouped Results

### 9.1. The two levels (Map and Collection) have separate contracts

Even if you choose `LinkedHashMap`, the downstream result can be a List, Set, or number; the mutability and ordering of **each level** are independent.

| Configuration | Outer Map | Value per group |
| --- | --- | --- |
| `groupingBy(key)` | Map type and mutability not guaranteed | `List<T>`; mutability not guaranteed |
| `groupingBy(key, LinkedHashMap::new, toList())` | LinkedHashMap in insertion order | List in encounter order (if any), mutability not guaranteed |
| `groupingBy(key, TreeMap::new, toSet())` | TreeMap by comparator | Deduplicated Set, order not guaranteed |
| `groupingBy(key, LinkedHashMap::new, toCollection(LinkedHashSet::new))` | LinkedHashMap in insertion order | LinkedHashSet in insertion order |
| `groupingBy(key, counting())` | Map type not guaranteed | Long representing count |
| `groupingBy(key, toUnmodifiableList())` | Map mutability not guaranteed | Unmodifiable List, forbids null elements |

A concrete example:

~~~java
Map<String, List<Order>> grouped = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.toUnmodifiableList()
    ));

// grouped.put("Tây", List.of());  // Map is mutable.
// grouped.get("Nam").add(...);  // Throws UnsupportedOperationException.
~~~

### 9.2. Classifier returning null: define policy before grouping

In standard Java implementations, `groupingBy` requires the group key returned by the classifier to be **non-null**; if the classifier returns null, collection will throw `NullPointerException`.

~~~java
record Customer(String name, String region) {}

List<Customer> customers = List.of(
    new Customer("An", "Nam"),
    new Customer("Bình", null)
);

// Do not rely on groupingBy creating a group with a null key.
// customers.stream().collect(groupingBy(Customer::region));
~~~

If "unknown region" is a valid business group, convert it into an explicit key:

~~~java
Map<String, List<Customer>> grouped = customers.stream()
    .collect(Collectors.groupingBy(
        customer -> customer.region() == null
            ? "CHUA_XAC_DINH"
            : customer.region()
    ));

System.out.println(grouped.get("CHUA_XAC_DINH").size()); // 1
~~~

Avoid collisions if `"CHUA_XAC_DINH"` can also be a valid data value. You can use a dedicated enum or a stateful key type instead of a sentinel string when exact distinction is needed.

### 9.3. Null in downstream collectors

`Collectors.toUnmodifiableList()` and `toUnmodifiableSet()` forbid `null` elements. `Collectors.toList()` does not guarantee mutability or implementation class, so if null handling policy is an important requirement, handle it explicitly before collecting: filter out, map to a replacement value, or intentionally fail.

~~~java
Map<String, List<String>> cleanSkus = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            order -> order.sku() == null
                ? "UNKNOWN"
                : order.sku(),
            Collectors.toUnmodifiableList()
        )
    ));
~~~

In the sample `Order` data, SKUs all have values; this snippet illustrates the policy when another system might supply null SKUs.

## 10. groupingBy and partitioningBy: Differences in Key Domain

`Collectors.partitioningBy(predicate)` splits elements into two Boolean groups, `true` and `false`. It is suitable when the problem truly has **two sides of a condition**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Order>> partitions = orders.stream()
    .collect(Collectors.partitioningBy(
        order -> order.quantity() >= 2
    ));
~~~

Differences to remember:

| Criterion | `groupingBy` | `partitioningBy` |
| --- | --- | --- |
| Key | Classifier function returning `K` | Predicate returning Boolean |
| Number of groups | Only keys that appear in the source | Always has both keys `true` and `false` |
| Empty source | Empty Map | Map with both keys and empty downstream results |
| Can choose Map supplier? | Yes, in the three-parameter overload | No `mapFactory` parameter |
| Can choose downstream? | Yes | Yes, via `partitioningBy(predicate, downstream)` |

Example counting both sides:

~~~java
Map<Boolean, Long> counts = orders.stream()
    .collect(Collectors.partitioningBy(
        order -> order.quantity() >= 2,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 2
System.out.println(counts.get(false)); // 2
~~~

With `groupingBy(order -> order.quantity() >= 2)`, one side can be completely absent from the Map if the source only contains data for the other side; `partitioningBy` preserves both keys. This is a difference that often affects reports and UIs.

## 11. groupingBy and groupingByConcurrent in Parallel Execution

### 11.1. groupingBy on a parallel stream

~~~java
Map<String, Long> counts = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));
~~~

`groupingBy` can be used on a parallel stream, but according to the API documentation it is **not a concurrent collector**. During the combine phase, the implementation may need to merge intermediate Maps, causing overhead when there are many keys or large datasets.

With an ordered source and an ordered downstream such as `toList()`, `groupingBy` helps preserve per-group element order semantics; the order in which the output Map iterates over **keys** still requires an appropriate `mapFactory`.

### 11.2. groupingByConcurrent when order is not needed

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> concurrentCounts =
    orders.parallelStream().collect(
        Collectors.groupingByConcurrent(
            Order::region,
            Collectors.counting()
        )
    );
~~~

`groupingByConcurrent` is a concurrent, unordered collector; the result is a `ConcurrentMap<K,D>`. It allows an implementation suited to accumulating groups in parallel, but **does not guarantee encounter order** of elements within each group or key iteration order.

If you need to choose a specific `ConcurrentMap` type, use the three-parameter overload with an appropriate supplier:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> counts =
    orders.parallelStream().collect(
        Collectors.groupingByConcurrent(
            Order::region,
            ConcurrentHashMap::new,
            Collectors.counting()
        )
    );
~~~

You cannot pass `LinkedHashMap::new` as the supplier for this overload: it requires a `ConcurrentMap`. The fact that the output Map itself is concurrent **does not mean** downstream values such as `List` can be arbitrarily mutated concurrently after collection finishes.

### 11.3. Choosing by goal and measuring performance

| Goal | Usually reasonable choice |
| --- | --- |
| Small report or straightforward logic needing source order | `groupingBy` on a sequential stream |
| Need parallel work while preserving ordered group semantics | `groupingBy` on a parallel stream, test and measure |
| Many elements, many groups, order does not matter | Consider `groupingByConcurrent` |
| Need a Map with sorted keys | `groupingBy(..., TreeMap::new, ...)` |
| Only need two true/false groups | `partitioningBy` |

Do not assume concurrent is always faster: source size, number of groups, skew across groups, classifier and downstream cost, contention, and CPU count all affect performance. Do not use lambdas that mutate external state to "speed up" grouping; keep the classifier stateless and non-interfering with the source.

## 12. Completing a Business Report: Ordered Map and Summary Statistics

Suppose a dashboard needs to display regions in alphabetical order. Each region needs order count, total units, and total revenue. You can use a custom downstream collector producing an immutable result object:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class SalesDashboard {
    record Order(String region, int quantity, long unitPrice) {
        long revenue() {
            return Math.multiplyExact(quantity, unitPrice);
        }
    }

    record Summary(long orders, long units, long revenue) {
        static Summary zero() {
            return new Summary(0L, 0L, 0L);
        }

        Summary add(Order order) {
            return new Summary(
                orders + 1,
                units + order.quantity(),
                revenue + order.revenue()
            );
        }

        Summary merge(Summary other) {
            return new Summary(
                orders + other.orders(),
                units + other.units(),
                revenue + other.revenue()
            );
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("Nam", 2, 50_000L),
            new Order("Bắc", 3, 10_000L),
            new Order("Nam", 1, 10_000L),
            new Order("Trung", 1, 50_000L)
        );

        Collector<Order, ?, Summary> summaryCollector =
            Collectors.reducing(
                Summary.zero(),
                order -> Summary.zero().add(order),
                Summary::merge
            );

        Map<String, Summary> report = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                TreeMap::new,
                summaryCollector
            ));

        System.out.println(report);
        // {Bắc=Summary[orders=1, units=3, revenue=30000],
        //  Nam=Summary[orders=2, units=3, revenue=110000],
        //  Trung=Summary[orders=1, units=1, revenue=50000]}
    }
}
~~~

`reducing(identity, mapper, op)` in the downstream collector converts each `Order` into a single-element summary and combines them using `Summary::merge`. `Summary` is an immutable record, `zero()` is the identity element, and `merge` is associative within non-overflowing ranges. This approach fits well when you want to return a single aggregate object. When a report only needs standard counts/sums, `counting()`, `summingLong()`, or `teeing()` is usually more concise.

With real monetary data, ensure all orders share the same currency unit, validate quantities/unit prices, and detect overflow or use an appropriate numeric type. `TreeMap` only solves **display key ordering**, not business validation.

## 13. Common Mistakes and Fixes

### Mistake 1: Assuming the default Map preserves insertion order

~~~java
Map<String, List<Order>> map = orders.stream()
    .collect(Collectors.groupingBy(Order::region));

// Do not rely on map.keySet() being in Nam, Bắc, Trung order.
~~~

If you need insertion order of groups from a sequential source with encounter order, choose `LinkedHashMap::new`. If you need alphabetical order, choose `TreeMap::new`.

### Mistake 2: Confusing order count with total quantity

~~~java
Map<String, Long> orderCount = orders.stream()
    .collect(Collectors.groupingBy(Order::region, Collectors.counting()));

Map<String, Integer> units = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingInt(Order::quantity)
    ));
~~~

For the `"Nam"` region in the sample dataset, `orderCount` is `2`, whereas `units` is `3`.

### Mistake 3: Using upstream filter when empty groups must be preserved

~~~java
// Creates groups only when at least one element matches:
orders.stream()
    .filter(order -> order.quantity() >= 2)
    .collect(Collectors.groupingBy(Order::region));

// Keeps every seen group; each group may have an empty list:
orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            order -> order.quantity() >= 2,
            Collectors.toList()
        )
    ));
~~~

The two pipelines are not equivalent when a group contains only elements that fail the condition.

### Mistake 4: Wanting a mutable List but only using the toList downstream

~~~java
// Specification does not guarantee List mutability:
Collectors.groupingBy(Order::region, Collectors.toList());

// More explicit if a mutable ArrayList is required:
Collectors.groupingBy(
    Order::region,
    Collectors.toCollection(java.util.ArrayList::new)
);
~~~

If an unmodifiable result is needed, consider `toUnmodifiableList()` and wrapping the outer Map after collection.

### Mistake 5: Unhandled null keys or null values

A null key from the classifier can cause `groupingBy` to throw NPE, while the `toUnmodifiableList` downstream also throws NPE on null elements. Define the policy—**filter**, **replace with an explicit state**, or **fail**—before selecting the collector.

### Mistake 6: Thinking parallel is always faster

~~~java
Map<String, Long> counts = orders.parallelStream()
    .collect(Collectors.groupingBy(Order::region, Collectors.counting()));
~~~

This conforms to the contract, but can be slower than a sequential stream if the input is small or Map merging has high overhead. Measure with representative data and consider `groupingByConcurrent` if order does not matter.

### Mistake 7: Trying to update a shared Map from inside the classifier

~~~java
// Do not do this: the classifier should only compute the key purely,
// not write to an external Map on every element.
orders.parallelStream()
    .collect(Collectors.groupingBy(order -> {
        // sharedMap.put(...); // Dangerous side effect.
        return order.region();
    }));
~~~

Let the `Collector` accumulate the results rather than concurrently writing to a mutable structure outside the pipeline.

## 14. Quick Decision Guide

| Question | Option to consider |
| --- | --- |
| Need a list of records per key? | `groupingBy(classifier)` |
| Need record count per group? | `groupingBy(classifier, counting())` |
| Need total revenue per group? | `groupingBy(classifier, summingLong(...))` |
| Need only one field of each element? | `mapping(fieldMapper, downstream)` |
| Want to keep the group even if filtered count is 0? | `filtering(predicate, downstream)` |
| One element emits multiple values for its group? | `flatMapping(..., downstream)` |
| Need two metrics for a group? | `teeing(downstream1, downstream2, merger)` |
| Need two-level grouping? | `groupingBy(classifier1, groupingBy(classifier2, downstream))` |
| Need key appearance order from a sequential source? | `groupingBy(key, LinkedHashMap::new, downstream)` |
| Need keys sorted by a comparator? | `groupingBy(key, TreeMap::new, downstream)` |
| Keys are an enum? | `groupingBy(key, () -> new EnumMap<>(Type.class), downstream)` |
| Only have two true/false domains? | `partitioningBy(predicate, downstream)` |
| Can drop encounter order for parallel execution? | Consider `groupingByConcurrent` and benchmark |

## 15. Knowledge Self-Check

1. **What are the three parameters of the full `groupingBy` overload?** Classifier, mapFactory, and downstream collector.
2. **Why does `groupingBy(Order::region)` not mean Map keys will follow region appearance order?** Because the default collector does not guarantee the Map type or key iteration order.
3. **When should you choose `LinkedHashMap` vs. `TreeMap`?** LinkedHashMap for insertion order; TreeMap for comparison order.
4. **What value type does `groupingBy(region, counting())` return per key?** `Long`, representing the number of elements classified into the group.
5. **If you want total quantity, can you use `counting()`?** No, use `summingInt(Order::quantity)` or `summingLong(...)`.
6. **What does `mapping(Order::sku, toSet())` do?** Extracts the SKU within each group and builds a Set of distinct values.
7. **What is the difference between `filter(...)` before `groupingBy` and downstream `Collectors.filtering(...)`?** The former can eliminate the group key altogether; the latter keeps keys seen by the classifier with an empty downstream result.
8. **Can a group contain a sub-Map?** Yes, using an appropriate downstream `groupingBy` or `toMap`.
9. **Is a classifier returning null guaranteed to create a null group?** No; in current standard Java it throws `NullPointerException`.
10. **Does passing `TreeMap::new` as mapFactory sort each group's List?** No. It only sorts the keys; to sort group values, use an appropriate downstream collector or post-processing step.
11. **Does `groupingByConcurrent` guarantee encounter order of elements within a group?** No; the collector is unordered.
12. **How does `partitioningBy` differ from `groupingBy(booleanClassifier)` when the source has only one value?** `partitioningBy` still keeps both Boolean keys; `groupingBy` only contains the key that appeared.
13. **Does a Map containing unmodifiable Lists mean the outer Map is also unmodifiable?** No, the two levels have separate contracts.
14. **Why should you not increment a shared counter inside the classifier when running in parallel?** Because the lambda must be stateless and non-interfering; shared mutation can race and violate the contract.
15. **If you only need a count by key, do you need to create a List and call size?** No; use downstream `counting()` to compute it directly.

**Key takeaway:** `groupingBy` is a mechanism for **grouping and reducing each group**. `classifier` determines the key, `mapFactory` determines the Map structure and key iteration order, and `downstream` determines each group's result: List, Set, count, sum, nested Map, or a summary. Design all three parts according to business requirements, handle `null` and encounter order explicitly, and parallelize only after verifying that accumulation is correct and performance benefits are measured.
