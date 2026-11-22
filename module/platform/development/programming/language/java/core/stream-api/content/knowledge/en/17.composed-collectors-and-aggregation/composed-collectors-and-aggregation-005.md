# Flattening Collector Input with flatMapping

In the Java Stream API, an input element often contains **multiple child values**: an order has multiple tags, an article has multiple keywords, an invoice has multiple line items. When you need to aggregate those child values **by the parent element's group**, `Collectors.flatMapping` lets you turn each parent element into a child `Stream` and pass **each child element** to a downstream collector. This is a way to compose multi-level collectors without manually creating intermediate lists.

This lesson belongs to the **Composed Collectors and Aggregation** chapter of the **JAVA_STREAM_API** module. The goal is to understand `flatMapping` accurately, distinguish it from `Stream.flatMap`, practice `groupingBy` with downstream collectors, and handle constraints around ordering, null data, state, resources, and parallel execution. This knowledge connects to declarative lazy pipelines, `filter`, `map`, `reduce`, and `collect`; it also prepares you for custom collectors, `Spliterator`, and advanced transformations such as Stream Gatherers.

## 1. Problem: a parent element has multiple child elements

Suppose we have these orders:

| Order ID | Region | Order tags |
|---|---|---|
| D01 | Bắc | gấp, dễ vỡ |
| D02 | Bắc | gấp, quà tặng |
| D03 | Nam | *(no tags)* |
| D04 | Trung | *(tag list not provided)* |
| D05 | Nam | ưu tiên |

Requirement: for **each region**, build the set of tags appearing in orders of that region. The expected result in terms of content is:

```text
Bắc   -> {gấp, dễ vỡ, quà tặng}
Nam   -> {ưu tiên}
Trung -> {}
```

We need two distinct processing levels:

1. **Group orders** by the order's region.
2. **Flatten the tags** of orders within each group and collect the tags into a set.

`Collectors.groupingBy` handles the first level. `Collectors.flatMapping` handles the second level, while `Collectors.toSet` determines the final result shape of each group:

```java
Map<String, Set<String>> tagsByRegion = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        order -> order.getTags().stream(),
                        Collectors.toSet())));
```

This is the **conceptual pattern** for data with a non-null tag list. In practice, if `getTags()` can return `null`, you must handle that before calling `stream()`. A complete, null-safe example is in section 4.

## 2. Signature and mechanism of Collectors.flatMapping

`Collectors.flatMapping` was added in **Java 9** in `java.util.stream.Collectors`. General signature:

```java
static <T, U, A, R> Collector<T, ?, R> flatMapping(
        Function<? super T, ? extends Stream<? extends U>> mapper,
        Collector<? super U, A, R> downstream)
```

| Parameter/type | Meaning |
|---|---|
| `T` | Parent element type entering the collector |
| `U` | Child element type emitted by the mapper |
| `A` | Accumulation state type of the downstream collector |
| `R` | Final result type of the downstream collector |
| `mapper` | Takes one `T` and returns a `Stream` of **0, 1, or many** `U` elements |
| `downstream` | Receives each `U` element and collects into `R` |

Conceptually, you can read the processing flow as:

```text
          Stream<Order>
                |
          groupingBy(region)
                |
   +------------+-------------+
   |            |             |
 "Bắc"        "Nam"         "Trung"
   |            |             |
flatMapping   flatMapping    flatMapping
   |            |             |
 [gấp, ...]  [ưu tiên]        []
   |            |             |
  toSet        toSet         toSet
   |            |             |
{gấp, ...}  {ưu tiên}         {}
```

**Important:** `flatMapping` is not an intermediate operation called directly on a `Stream`. It is **a Collector** composed with another collector. The mapper function here returns a `Stream<U>`, not a single `U`.

### 2.1. Cases of 0, 1, and many elements

For an order with three tags, the mapper can produce a Stream of three tags; the downstream receives all three. If the tag list is empty, the mapper produces an empty Stream and the downstream **receives zero elements** from that order. If an order has one tag, the downstream receives one element.

A mapper emitting **zero child elements** does not mean the **parent order itself disappears from grouping**. This is a crucial difference from flattening the input **before** grouping.

### 2.2. Lifecycle characteristics of child Streams

By the contract of `Collectors.flatMapping`, **each Stream returned by the mapper is closed after its elements have been fed into the downstream collector**. If the mapper returns a **null Stream**, the implementation treats it as an empty Stream.

Do not intentionally return `null` to represent missing data; using `Stream.empty()` explicitly is clearer and avoids masking bugs inside the mapper. Remember also that closing the **child Stream** does not automatically close all resources of the **outer source Stream**. For I/O sources such as `Files.lines`, manage the source lifecycle with `try-with-resources`.

## 3. Why place flatMapping inside groupingBy?

Two pipelines that look similar can yield **different Map key sets**.

### 3.1. Flatten first, then groupingBy

```java
Map<String, List<String>> byRegion = orders.stream()
        .flatMap(order -> order.getTags().stream()
                .map(tag -> new AbstractMap.SimpleEntry<>(
                        order.getRegion(), tag)))
        .collect(Collectors.groupingBy(
                Map.Entry::getKey,
                Collectors.mapping(
                        Map.Entry::getValue,
                        Collectors.toList())));
```

This illustration also assumes `getTags()` is non-null; the standalone runnable example in section 4 provides a null-safe version.

Here, `flatMap` is an intermediate operation **before** `groupingBy`. An order with no tags emits no `(region, tag)` pair. If all orders in a region have no tags, that region key **may not exist in the resulting Map**.

### 3.2. groupingBy first, flatMapping in downstream

```java
Map<String, List<String>> byRegion = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        order -> order.getTags().stream(),
                        Collectors.toList())));
```

`groupingBy` receives the **parent order** and creates a group for its region. The `flatMapping` collector only alters **the elements passed to the downstream**, not whether an order belongs to a group.

For a region that has orders with no tags, the region key still exists and its value can be an **empty list**. However, a region **with no orders at all in the source** will not have a key created automatically by `groupingBy`.

| Source data | `stream.flatMap(...).collect(groupingBy(...))` | `stream.collect(groupingBy(..., flatMapping(...)))` |
|---|---|---|
| Has orders with tags | Group exists | Group exists |
| Has orders, but tag list is empty | No group contributed by that order | Group exists; downstream is empty if other orders also lack tags |
| Has orders, and null tag list is turned into empty Stream | No elements for grouping | Preserves parent order's group |
| No orders for that region | No group | No group |

**Deciding whether to flatten before or after grouping is a business decision:** should groups with no child values be omitted, or must they be kept to report “orders exist, but have no tags yet”?

## 4. Complete Java 9 example: order tags by region

The example below runs standalone on **Java 9 or later**. It normalizes tags, removes nulls and blank strings, and produces both the **set of distinct tags** and **tag occurrence counts** per region.

```java
import java.util.AbstractMap;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FlatMappingCollectorDemo {
    static final class Order {
        private final String id;
        private final String region;
        private final List<String> tags;

        Order(String id, String region, List<String> tags) {
            this.id = id;
            this.region = region;
            this.tags = tags;
        }

        String getId() {
            return id;
        }

        String getRegion() {
            return region;
        }

        List<String> getTags() {
            return tags;
        }
    }

    // Creates a new child Stream per order without mutating the source list.
    static Stream<String> normalizedTags(Order order) {
        List<String> tags = order.getTags();
        if (tags == null) {
            return Stream.empty();
        }
        return tags.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(tag -> !tag.isEmpty());
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("D01", "Bắc",
                        Arrays.asList(" gấp ", "dễ vỡ", null)),
                new Order("D02", "Bắc",
                        Arrays.asList("gấp", "quà tặng")),
                new Order("D03", "Nam", Collections.emptyList()),
                new Order("D04", "Trung", null),
                new Order("D05", "Nam",
                        Arrays.asList("ưu tiên", "  "))
        );

        // 1) Group parent orders, flatten tags in the downstream.
        Map<String, Set<String>> uniqueTagsByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.flatMapping(
                                FlatMappingCollectorDemo::normalizedTags,
                                Collectors.toSet())));

        System.out.println(uniqueTagsByRegion.get("Bắc").size()); // 3
        System.out.println(uniqueTagsByRegion.get("Nam").size()); // 1
        System.out.println(uniqueTagsByRegion.containsKey("Trung")); // true
        System.out.println(uniqueTagsByRegion.get("Trung").isEmpty()); // true

        // 2) Count tag OCCURRENCES, including repeated tags.
        Map<String, Long> tagCountByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.flatMapping(
                                FlatMappingCollectorDemo::normalizedTags,
                                Collectors.counting())));

        System.out.println(tagCountByRegion.get("Bắc"));   // 4
        System.out.println(tagCountByRegion.get("Nam"));   // 1
        System.out.println(tagCountByRegion.get("Trung")); // 0

        // 3) Flatten before grouping: groups without tags disappear.
        Map<String, List<String>> flatFirst = orders.stream()
                .flatMap(order -> normalizedTags(order)
                        .map(tag -> new AbstractMap.SimpleEntry<>(
                                order.getRegion(), tag)))
                .collect(Collectors.groupingBy(
                        Map.Entry::getKey,
                        Collectors.mapping(
                                Map.Entry::getValue,
                                Collectors.toList())));

        System.out.println(flatFirst.containsKey("Trung")); // false

        // 4) For a group with no orders at all, there is still no key.
        System.out.println(uniqueTagsByRegion.containsKey("Tây")); // false
    }
}
```

**Result explanation:**

- The **Bắc** region has four valid tag occurrences: `gấp`, `dễ vỡ`, `gấp`, `quà tặng`. `toSet` deduplicates `gấp`, leaving **three distinct tags**; `counting` still counts **four occurrences**.
- The **Nam** region has one valid tag `ưu tiên`, because order D03 has no tags and the whitespace-only string in D05 is filtered out.
- The **Trung** region has one order D04 whose tag list is null. `normalizedTags` returns `Stream.empty()`, so downstream `toSet` returns an empty set and `counting` returns `0L`. **The `"Trung"` key still exists** when using `groupingBy(..., flatMapping(...))`.
- The **Tây** region has no orders, so no group is created for it.
- `toSet` and default `groupingBy` Maps **do not guarantee iteration order**; the example checks content using `get`, `containsKey`, and `size`.

This is an example of using `flatMapping` in line with business semantics: **grouping by the parent element**, while allowing each parent element to contribute **0 or more child elements**.

## 5. Combining flatMapping with other downstream collectors

`flatMapping` is not limited to `toSet`. It forwards `U` elements to **any suitable downstream collector**:

| Downstream | Per-group result | Case where group has parent but no children |
|---|---|---|
| `Collectors.toList()` | List of child elements, may contain duplicates | Empty list |
| `Collectors.toSet()` | Set of distinct child elements | Empty set |
| `Collectors.counting()` | Count of child element occurrences | `0L` |
| `Collectors.summingInt(String::length)` | Total character count of tags | `0` |
| `Collectors.joining(", ")` | Joined string of tags | Empty string `""` |
| `Collectors.mapping(..., toList())` | Further transformation after flattening | Empty list |
| `Collectors.filtering(..., toSet())` (Java 9+) | Filter child elements before adding to set | Empty set |

### 5.1. Keeping duplicates with toList

```java
Map<String, List<String>> allTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.toList())));

System.out.println(allTags.get("Bắc"));
// [gấp, dễ vỡ, gấp, quà tặng]
```

If the source Stream is a `List` with encounter order, the collector preserves that order for elements in the resulting `List`; however, **Map key iteration order** from `groupingBy` is a separate matter and is not guaranteed stable by default.

### 5.2. Counting distinct items with collectingAndThen

`Collectors.counting()` counts **occurrences**, whereas sometimes you need the **number of distinct tags**:

```java
Map<String, Integer> uniqueCount = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.collectingAndThen(
                                Collectors.toSet(),
                                Set::size))));

System.out.println(uniqueCount.get("Bắc"));   // 3
System.out.println(uniqueCount.get("Trung")); // 0
```

Here, `toSet()` accumulates distinct tags; `collectingAndThen` calls the `Set::size` finisher to convert the set into a count. This is an example of a **multi-level composed collector**: `groupingBy → flatMapping → collectingAndThen → toSet`.

### 5.3. Transforming or further filtering child elements

`Collectors.mapping` converts **each element** into a new element; `Collectors.flatMapping` converts **each element** into a Stream that can hold multiple elements. They can be nested:

```java
Map<String, Set<String>> upperCaseTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.mapping(
                                String::toUpperCase,
                                Collectors.toSet()))));
```

With the `filtering` collector from Java 9, you can retain only tags of length at least four characters:

```java
Map<String, List<String>> longTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.filtering(
                                tag -> tag.length() >= 4,
                                Collectors.toList()))));

System.out.println(longTags.get("Bắc"));
// [dễ vỡ, quà tặng]; "gấp" has three characters so it is excluded.
System.out.println(longTags.get("Trung")); // []
```

In the snippets of this section, `orders` and `FlatMappingCollectorDemo.normalizedTags` come from the complete example in section 4. Dropping child elements with downstream `filtering` still preserves the group already created for the parent element.

## 6. Comparing mapping, flatMapping, filtering, and flatMap

Similar method names are easy to confuse:

| Form | Operating level | Transformation shape | Effect on groups |
|---|---|---|---|
| `stream.map(f)` | Stream intermediate operation | Each `T` → one `U`, even if `U` can be null | Can change data before grouping |
| `stream.flatMap(f)` | Stream intermediate operation | Each `T` → 0..n `U` elements | If used before grouping, parents with 0 children may not create a group |
| `Collectors.mapping(f, downstream)` | Downstream collector | Each `T` → one `U`, then accumulated | Group is formed from parent if placed inside `groupingBy` |
| `Collectors.flatMapping(f, downstream)` | Downstream collector (Java 9+) | Each `T` → 0..n `U` elements, then accumulated | Group is formed from parent, even if mapper emits 0 elements |
| `Collectors.filtering(p, downstream)` | Downstream collector (Java 9+) | Each `T` → kept or dropped before downstream | Group is formed from parent, even if all elements are filtered out downstream |

**Quick rule of thumb:** If the task is simply to produce a combined Stream of children for all elements, `Stream.flatMap` is natural. If the task is to **aggregate multiple child values inside each parent group**, `Collectors.flatMapping` usually expresses this better and can preserve groups with zero child values.

### 6.1. Do not confuse flatMapping with single-value mapping

```java
// With mapping/summing, each Order contributes only one integer:
Map<String, Integer> totalTagLists = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.summingInt(order ->
                        order.getTags() == null ? 0 : 1)));
// This is the number of orders with non-null tag lists, NOT the number of tags.

// With flatMapping + counting, each Order contributes all valid tags:
Map<String, Long> totalTags = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.counting())));
```

Verify the **counting unit**: counting orders, counting tag lists, counting tag occurrences, and counting distinct tags are four different computations.

## 7. Handling null and empty child Streams

Three levels of null can arise in a nested pipeline:

1. **The parent order is null**: `Order::getRegion` or `Order::getTags` will fail; filter out null orders first or handle explicitly.
2. **An order's tag list is null**: cannot call `tags.stream()`; return `Stream.empty()` or use a null-safe API.
3. **An element inside the tag list is null**: `tags.stream()` still emits null; the downstream may receive it unless filtered.

```java
Map<String, Set<String>> byRegion = orders.stream()
        .filter(Objects::nonNull) // Protects Order itself.
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        order -> Stream.ofNullable(order.getTags())
                                .flatMap(List::stream)
                                .filter(Objects::nonNull),
                        Collectors.toSet())));
```

`Stream.ofNullable` was also introduced in **Java 9**: if the tag list is null, it creates an empty Stream; if non-null, it contains that single list so `flatMap(List::stream)` expands its elements. The final `filter(Objects::nonNull)` only drops **null tag elements**, not a null list.

In this example, `region` is assumed non-null. If `getRegion()` returns null, `groupingBy` can throw `NullPointerException` because the classifier does not accept null keys; decide on a policy to filter orders or map missing regions to a group label.

### 7.1. What if flatMapping's mapper returns null?

The contract of `Collectors.flatMapping` treats a **null Stream returned by the mapper** as an empty Stream. However, this is a Collector-level fallback, not a promise that calling `order.getTags().stream()` on a null list will be safe. That expression throws an exception **before the mapper ever returns a Stream**.

Write:

```java
order -> order.getTags() == null
        ? Stream.<String>empty()
        : order.getTags().stream()
```

or use `Stream.ofNullable(...)` as shown above so the intent to skip missing data is explicit.

## 8. Ordering, laziness, and resource lifecycle

`flatMapping` is a Collector used in the `collect` terminal operation. The upstream pipeline such as `filter` and `map` still operates under Stream laziness; the mapping function inside `flatMapping` is applied when data is actually collected.

### 8.1. Downstream choice determines order preservation

- `toList` preserves elements in encounter order if ordering is required by the source and collector.
- `toSet` removes duplicates and **does not guarantee iteration order**.
- `toCollection(LinkedHashSet::new)` can be used when you need a set without duplicates **that preserves insertion order**.
- `toCollection(TreeSet::new)` sorts by natural order or the set's comparator, not necessarily encounter order.

Example preserving tag appearance order while deduplicating:

```java
Map<String, java.util.LinkedHashSet<String>> orderedTags =
        orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.flatMapping(
                                FlatMappingCollectorDemo::normalizedTags,
                                Collectors.toCollection(
                                        java.util.LinkedHashSet::new))));

System.out.println(orderedTags.get("Bắc"));
// [gấp, dễ vỡ, quà tặng]
```

This is the element order **inside the Set value** of the `"Bắc"` region; the Map produced by `groupingBy` still does not iterate keys in region order by default.

### 8.2. Child Streams are closed; I/O sources need separate management

If the mapper creates a resource-backed Stream, `flatMapping` closes the child Stream after forwarding its elements to the downstream. However, consider the cost of opening/closing a resource **for every parent element**: an I/O source per order can be very expensive and easily exhaust resource limits if poorly designed.

When the outer Stream is created from a closeable resource, wrap that source itself:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Path path = java.nio.file.Paths.get("data.txt"); // File must exist.

try (Stream<String> lines = Files.lines(path)) {
    List<String> nonEmpty = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .collect(Collectors.toList());
}
```

This snippet illustrates resource-management syntax; at runtime `data.txt` must exist in the working directory (or replace with an appropriate path). `collect` itself does not replace `try-with-resources` for an external file source.

### 8.3. Do not reuse a child Stream

A `Stream` can generally be consumed only once. The mapper should **create a new Stream on each invocation**, rather than returning the same `Stream` variable already used on a previous order. Returning a closed or already-consumed Stream can cause `IllegalStateException`.

A `List` can be traversed multiple times with new Streams, provided the list is not illegally modified during traversal. This differs from reusing the `Stream` object itself.

## 9. Performance and parallel processing

When using `groupingBy(..., flatMapping(...))` on a parallel stream, the framework can create intermediate accumulation containers per branch, feed child elements to the downstream, and then merge the containers. This requires the downstream collector to obey the **identity, associativity, and equivalence contracts** so results remain valid across partitions.

```java
Map<String, Set<String>> parallelResult = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.toSet())));
```

The snippet above does not share a mutable `HashSet` outside the pipeline. Containers managed by the collector are created and combined according to framework rules, so there is no need to use `Collections.synchronizedSet` just to write an ordinary collection operation.

For safety and verifiability:

- The mapper and downstream functions should be **non-interfering** and avoid mutable state shared across workers.
- Do not assume mapper invocation order or worker execution order when using `parallelStream()`; use order-independent result semantics when business rules permit.
- Parallel `groupingBy` may have to **merge many Maps**, incurring notable cost with many groups or skewed data distributions.
- `groupingByConcurrent` may fit when order does not matter and the downstream is compatible, though switching to a concurrent collector **does not guarantee faster speed**.
- With large numbers of child elements, `toList` may retain all data in memory, whereas `counting` or `summingInt` typically need only a small accumulation state per group.

Placing `flatMapping` inside the collector avoids manually materializing an intermediate list for grouping, yet each mapper invocation still pays the cost of creating and traversing a child Stream. Do not equate using Streams with automatic memory savings if the final downstream must still hold many elements.

## 10. When should you not use flatMapping?

Do not force every problem into `Collectors.flatMapping`:

| Problem | Better approach |
|---|---|
| Need to flatten a list of lists and return a new Stream | `Stream.flatMap` |
| Only map each parent to exactly one value and collect by group | `Collectors.mapping` |
| Only filter elements before downstream | `Collectors.filtering` or `Stream.filter` per group policy |
| Only need to count orders per region | `groupingBy(Order::getRegion, counting())` |
| Only need to sum a primitive field | `summingInt`/`summingLong` or primitive stream |
| Need a report grouped by parent, collecting children inside each group | `groupingBy(..., flatMapping(...))` |

If the business logic **does not want to keep empty groups**, sometimes `Stream.flatMap` before grouping is simpler. If the business logic **requires keeping empty groups**, downstream `flatMapping` expresses the intent more clearly.

## 11. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `NullPointerException` at `order.getTags().stream()` | Null child list | Return `Stream.empty()` or use `Stream.ofNullable` |
| `NullPointerException` when calling getter on `Order` | Null parent element | Filter `Objects::nonNull` before grouping |
| Groups without tags disappear from Map | Flattening before `groupingBy` | Place `flatMapping` as the downstream of `groupingBy` |
| Expecting `counting` to count orders | It actually counts elements **after** `flatMapping` | Identify the counting unit; place `counting` at the right layer |
| Distinct tag counts still include duplicates | Using `toList` | Use `toSet` or `toCollection(LinkedHashSet::new)` |
| Unstable tag order | `toSet` makes no ordering guarantee | Use an ordered collection or sort explicitly |
| Reused child Stream fails with `already operated upon or closed` | Mapper returned an old Stream | Create a fresh Stream for each parent element |
| Null tags inside a non-null list still pass through | Only checked that the child list is non-null | Filter child elements with `Objects::nonNull` |
| Parallel collector has unexpected side effects | Mapper mutates shared variable or source | Use pure functions; let the collector manage state |
| Using `flatMapping` on Java 8 | API did not exist in Java 8 | Upgrade to Java 9+ or use an alternative strategy |

## 12. Self-check exercises with answers

### Exercise 1. Determining tag occurrence count

Two orders in region A have tag lists `["x", "y"]` and `["x"]`. What is the result of `groupingBy(region, flatMapping(tagsStream, counting()))` for region A?

**Answer:** `3L`, because `counting` receives **three tag occurrences**, including the repeated `"x"` tag. With `toSet`, region A would have only two distinct tags.

### Exercise 2. Group without child values

Region B has one order with an empty tag list. Region C has no orders. What keys does the result of `groupingBy(Order::getRegion, flatMapping(..., toList()))` contain?

**Answer:** Region B **has a key** with an empty list. Region C **has no key** because there is no parent element to create the group.

### Exercise 3. Comparing two pipeline orders

Why can `orders.stream().flatMap(...).collect(groupingBy(...))` drop a group, whereas `orders.stream().collect(groupingBy(..., flatMapping(...)))` preserves it?

**Answer:** In the first approach, parent elements are replaced by child elements **before** grouping. Parents with 0 children emit no elements. In the second approach, `groupingBy` sees the parent first and creates the group, while flattening only affects the values inside the group.

### Exercise 4. Choosing the downstream

A region has tags `["gấp", "quà tặng", "gấp"]`. To keep all three occurrences in their original order, do you choose `toList` or `toSet`? To keep two distinct tags, what should you choose?

**Answer:** `toList` keeps all three occurrences when the input has encounter order. `toSet` keeps two distinct tags without guaranteeing order. If you need both uniqueness and insertion order, use `toCollection(LinkedHashSet::new)`.

### Exercise 5. Handling null at the right level

`order.getTags()` can be null, and inside a non-null list there can still be null elements. Is writing only `Stream.ofNullable(order.getTags())` sufficient?

**Answer:** Not sufficient. `ofNullable` produces a Stream of **one list** or an empty Stream. You must also flatten the list into tags with `flatMap(List::stream)`, and then filter out null tags with `filter(Objects::nonNull)`.

### Exercise 6. Counting tag characters per group

Compute the total length of valid tags for each region using `Collectors.flatMapping` and downstream `summingInt`.

```java
Map<String, Integer> charactersByRegion = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.flatMapping(
                        FlatMappingCollectorDemo::normalizedTags,
                        Collectors.summingInt(String::length))));
```

**Answer:** Each normalized tag contributes `length()` characters to its group's total. A group with orders but no valid tags receives `0`. This is the character count of **tag occurrences**, not the total length of distinct tags.

## 13. Key takeaway

`Collectors.flatMapping(mapper, downstream)` (Java 9+) is a **Collector adapter**: each parent element produces a Stream of **0 or more child elements**, and each child element is fed into the downstream. It is especially expressive when you need `groupingBy` on parent objects while aggregating child values, **preserving even groups that have parents with no children**. Clearly distinguish flattening **before grouping** via `Stream.flatMap` from flattening **inside grouping** via `Collectors.flatMapping`; pick the right downstream, handle nulls at each level, create fresh child Streams, and control ordering, resources, state, and parallelism overhead.
