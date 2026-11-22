# Choosing Rules to Keep the First Record, Last Record, or Merge Values

> **Chapter:** Collecting to Maps  
> **Module:** JAVA_STREAM_API  
> **Goal:** Choose the right duplicate-key handling rule when collecting a Stream into a Map with `Collectors.toMap`: keeping the first-seen record, keeping the last-seen record, or merging data from multiple records; distinguish between source order and business order.

In **JAVA_STREAM_API**, intermediate operations such as `filter` and `map` form declarative data-processing pipelines. When the result needs key-based access, we often end the pipeline with `collect(Collectors.toMap(...))`. A problem arises when **multiple elements produce the same key**: an ordinary `Map<K,V>` holds only one value per key, so which value should be chosen?

For example, suppose a system receives multiple update records for the same product:

| Event ID | Product Code | Quantity | Business Timestamp |
| --- | --- | ---: | ---: |
| E01 | A | 4 | 100 |
| E02 | B | 3 | 101 |
| E03 | A | 2 | 105 |
| E04 | A | 6 | 103 |
| E05 | B | 7 | 98 |

If one value must be stored per product, there are at least four valid rules depending on the problem:

- **Keep first seen:** for A pick E01; for B pick E02.
- **Keep last seen:** for A pick E04; for B pick E05.
- **Merge quantities:** for A compute `4 + 2 + 6 = 12`; for B compute `3 + 7 = 10`.
- **Keep record with latest timestamp:** for A pick E03 (105); for B pick E02 (101).

The **last record in the Stream is not necessarily the newest record in business time**. That is the single most important distinction when designing a duplicate-key handling function.

This lesson connects directly to `collect`, the `Collector` contract, grouping, parallel processing, and `Spliterator` ordering in the Java Stream API module. These principles of state, associativity, and merge cost are also useful when building custom collectors and advanced Stream operations such as Stream Gatherers.

The main examples use Java 17+ with `record` and `List.of`. `Collectors.toMap` and its merge-function overloads have been available since Java 8.

## 1. Why Does toMap Encounter Key Collisions?

`Collectors.toMap` transforms elements of a `Stream<T>` into key–value pairs:

```text
Stream<T>
   │
   ├── keyMapper(T) ───────► K
   │
   └── valueMapper(T) ─────► V
                              │
                              ▼
                         Map<K, V>
```

Suppose we have products with category names:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Product(String sku, String category, long price) {}

List<Product> products = List.of(
    new Product("P01", "Books", 100_000),
    new Product("P02", "Books", 150_000),
    new Product("P03", "Devices", 200_000)
);
```

If we choose SKU as the key, every value is unique:

```java
Map<String, Product> bySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        product -> product
    ));

// bySku contains 3 entries because each sku appears only once.
```

If we choose `category` as the key:

```java
Map<String, Product> byCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        product -> product
    )); // IllegalStateException: duplicate key "Books".
```

**The two-argument overload of `toMap` does not automatically pick the first or last record.** When elements map to a duplicate key according to the Map's equality rules, the collector throws `IllegalStateException` by default. This helps detect data errors if the domain genuinely requires unique keys.

One valid solution is to **specify a merge function**. Other solutions are redesigning the key or using `groupingBy` when every record must be retained.

## 2. Reading the Collectors.toMap Overloads Correctly

`Collectors` provides three core overloads:

```java
// 1) No rule declared for duplicate keys:
toMap(keyMapper, valueMapper);

// 2) Includes a merge rule when keys collide:
toMap(keyMapper, valueMapper, mergeFunction);

// 3) Includes both a merge rule and the Map type to create:
toMap(keyMapper, valueMapper, mergeFunction, mapFactory);
```

Generic type shapes (simplified for readability):

```java
<T, K, U> Collector<T, ?, Map<K, U>> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
);

<T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
);
```

| Parameter | Purpose | Example |
| --- | --- | --- |
| `keyMapper` | Extracts key `K` from an element `T` | `Product::category` |
| `valueMapper` | Extracts value `U` from an element `T` | `Product::price` |
| `mergeFunction` | Receives two `U` values for the same key and returns one combined value | `(oldValue, newValue) -> oldValue` |
| `mapFactory` | Creates the Map instance to collect into | `LinkedHashMap::new`, `TreeMap::new` |

`mergeFunction` has type `BinaryOperator<U>`: it accepts two values **of the same type `U`** and returns one value of type `U`. It does not directly receive key `K` or the original element `T`, unless `valueMapper` retains the input object itself as the value.

Example:

```java
Map<String, Long> maxPriceByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category, // K = String
        Product::price,    // U = Long (boxed from long)
        Long::max          // BinaryOperator<Long>
    ));

// "Books" -> 150000; "Devices" -> 200000.
```

If we want to merge based on other attributes of `Product` (such as update date or priority), we can use `Function.identity()` as `valueMapper` to keep the whole object.

## 3. Keeping the First Record: (first, next) -> first

In a Stream **with a defined encounter order**, the rule for keeping the first-appearing record is commonly written as:

```java
Map<String, Product> firstByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        product -> product,
        (first, next) -> first
    ));
```

In the example, the `"Books"` group keeps P01 because P01 appears before P02 in the source list.

You can use `Function.identity()` to return the original element:

```java
import java.util.function.Function;

Map<String, Product> firstByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        Function.identity(),
        (first, next) -> first
    ));
```

### 3.1. "First" according to what order?

In the example above, `products` is an ordered `List` and `products.stream()` preserves *encounter order*. If the data comes from a `HashSet`, a Stream with `unordered()` called on it, or a source that declares no order, **there is no basis for determining which record is business-first**.

Compare:

```java
List<String> names = List.of("Alice", "Bob", "Carol");

// With a List and a sequential Stream, the encounter order is Alice, Bob, Carol.
String first = names.stream().findFirst().orElseThrow();
```

With an unordered Stream, the notion of "first" lacks the stable guarantee of a List. To pick the first record by creation time, **put the timestamp into the comparison rule** rather than implicitly depending on input order.

### 3.2. When should you keep the first record?

This rule fits when:

- The input list is already sorted by **highest priority first**.
- You need to preserve the first value ingested in an ordered event stream.
- The specification states "for each key, take the first occurrence in the input data".

If the goal is to pick the record with the **earliest timestamp**, use a `Comparator` directly as shown in Section 6; that also remains explicit when source order is not guaranteed.

### 3.3. Do not misunderstand first as a global variable keeping one item total

In the collector, `(first, next) -> first` specifies **how to resolve two values competing for the same key**. It does not create a global variable and does not mean the entire Stream keeps only one element. Each key has its own collision history.

Therefore:

```text
[A: E01, B: E02, A: E03, A: E04, B: E05]
                     │
                 keep first
                     ▼
                 A → E01
                 B → E02
```

## 4. Keeping the Last Record: (oldValue, newValue) -> newValue

To choose the value seen later in source order:

```java
Map<String, Product> lastByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        Function.identity(),
        (oldValue, newValue) -> newValue
    ));
```

In the `"Books"` group, P02 replaces P01. This rule is commonly called **last wins**.

Numeric example:

```java
record Reading(String sensorId, int value) {}

List<Reading> readings = List.of(
    new Reading("S1", 10),
    new Reading("S2", 20),
    new Reading("S1", 15),
    new Reading("S1", 18)
);

Map<String, Integer> latestInSequence = readings.stream()
    .collect(Collectors.toMap(
        Reading::sensorId,
        Reading::value,
        (oldValue, newValue) -> newValue
    ));

// "S1" -> 18; "S2" -> 20.
```

### 4.1. "Last" does not mean "newest"

Suppose data arrives late:

```text
Events appearing in the list:
E01 (timestamp 100)
E03 (timestamp 105)
E04 (timestamp 103)

last wins by encounter order = E04
newest by timestamp         = E03
```

If data arrives from queues, paginated APIs, or services replaying old records, appearance order can differ from chronological order. **Last wins is only correct for "overwrite with the later-arriving element"**, not by default for "the most recently updated value".

### 4.2. Does last wins change the order of keys in the Map?

Replacing the value of a key does not necessarily move that key to the end of Map traversal order. For example, with `LinkedHashMap` storing insertion order by default:

```java
Map<String, Reading> map = readings.stream()
    .collect(Collectors.toMap(
        Reading::sensorId,
        Function.identity(),
        (oldValue, newValue) -> newValue,
        LinkedHashMap::new
    ));
```

Here key `S1` appears first, so its position is recorded upon first insertion. Subsequent overwrites of `S1`'s **value** do not make it the most recently inserted key. `LinkedHashMap` in insertion-order mode does not move a key's position just because an existing value is updated.

If keys need to be ordered by last update time, choose a data structure or sorting rule specifically designed for that requirement.

## 5. Merging Values: sum, max, min, and Business Rules

Keeping the first or last value are two special cases: on collision, one value is kept intact and the other is discarded. However, many problems require **accumulation**.

### 5.1. Summing quantities by key

```java
record Item(String sku, long quantity) {}

List<Item> items = List.of(
    new Item("A", 4),
    new Item("B", 3),
    new Item("A", 2),
    new Item("A", 6),
    new Item("B", 7)
);

Map<String, Long> totalQuantity = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::sum
    ));

// "A" -> 12; "B" -> 10.
```

At each key collision, `Long::sum` combines the existing value with the incoming value. At the end, each key holds a total.

You could write an equivalent lambda:

```java
(left, right) -> left + right
```

However, `Long::sum` more clearly expresses the intent of adding two `long` numbers.

### 5.2. Selecting the maximum or minimum value

```java
Map<String, Long> maxQuantity = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::max
    ));

// A -> 6; B -> 7.
```

`Long::min` works similarly for taking the minimum value. This merge is independent of appearance position and is typically suitable when input order carries no business meaning.

### 5.3. When fields must be combined instead of adding a single number

Suppose each record holds revenue and order count:

```java
record Totals(long revenue, long orders) {}

record PartialReport(String category, Totals totals) {}

List<PartialReport> parts = List.of(
    new PartialReport("Books", new Totals(100, 2)),
    new PartialReport("Devices", new Totals(250, 1)),
    new PartialReport("Books", new Totals(300, 3))
);

Map<String, Totals> summary = parts.stream()
    .collect(Collectors.toMap(
        PartialReport::category,
        PartialReport::totals,
        (left, right) -> new Totals(
            left.revenue() + right.revenue(),
            left.orders() + right.orders()
        )
    ));

// "Books" -> Totals(revenue=400, orders=5).
```

The merge function produces a new value without mutating old objects. This is a clean way to prevent shared-state bugs under parallel processing. With real data, guard against `long` overflow if totals may exceed the representable range.

### 5.4. Merging lists or using groupingBy?

If you want to keep **every record** in each group, `groupingBy` is usually much more natural:

```java
Map<String, List<Item>> itemsBySku = items.stream()
    .collect(Collectors.groupingBy(Item::sku));

// "A" has 3 Items; "B" has 2 Items.
```

You could write `toMap` with a `valueMapper` that creates a single-element list and then merges lists. But managing a mutable container per key, preserving order, and combining in parallel is needlessly complicated when `groupingBy` already models the problem directly.

Conversely, if only the total quantity is needed, `toMap(..., Long::sum)` is concise and clear. Another alternative is:

```java
Map<String, Long> totals = items.stream()
    .collect(Collectors.groupingBy(
        Item::sku,
        Collectors.summingLong(Item::quantity)
    ));
```

Both approaches express "sum by key"; choose the API based on downstream collector composition, Map type, code clarity, and desired output.

## 6. Keeping a Record by Time or Priority: Using a Comparator

When keys collide and you need the **chronologically latest** record, compare an attribute of the object itself. Using the data from the opening section:

```java
record Event(String id, String product, long quantity, long occurredAt) {}
```

Keep the `Event` itself as the Map value:

```java
Comparator<Event> byTimestampThenId = Comparator
    .comparingLong(Event::occurredAt)
    .thenComparing(Event::id);

Map<String, Event> newestByProduct = events.stream()
    .collect(Collectors.toMap(
        Event::product,
        Function.identity(),
        BinaryOperator.maxBy(byTimestampThenId)
    ));
```

The variable `events` is a `List<Event>` fully declared in the standalone program in Section 9.

`BinaryOperator.maxBy(...)` returns the greater value according to the Comparator. The primary key `occurredAt` determines the latest record; `id` breaks ties consistently when two events share the same timestamp.

### 6.1. Why is a tie-breaker needed?

If you only compare timestamps, two events at the same instant can be treated as equivalent by the Comparator. Which element is kept can then depend on how ties are handled.

```java
Comparator<Event> byTimestamp =
    Comparator.comparingLong(Event::occurredAt);
```

For systems requiring reproducible results, add a **unique and stable** final tie-breaker key:

```java
Comparator<Event> byTimestampThenId = Comparator
    .comparingLong(Event::occurredAt)
    .thenComparing(Event::id);
```

This works only if `id` satisfies the uniqueness requirement of the data. If event IDs are not unique, define an additional rule.

### 6.2. Using minBy for the oldest record

```java
Map<String, Event> oldestByProduct = events.stream()
    .collect(Collectors.toMap(
        Event::product,
        Function.identity(),
        BinaryOperator.minBy(byTimestampThenId)
    ));
```

`minBy` selects the element with the smallest comparison key. When the Comparator means "ascending timestamp then ID", it picks the oldest record by time; on equal timestamps, it picks the smaller ID.

### 6.3. An alternative: sort first, then last wins

If you want to literally express "traverse in ascending timestamp order, then take the last":

```java
Map<String, Event> newestSorted = events.stream()
    .sorted(byTimestampThenId)
    .collect(Collectors.toMap(
        Event::product,
        Function.identity(),
        (first, second) -> second
    ));
```

This can yield the same result as `maxBy` on data with an appropriate total order. However, `sorted` must sort the entire source, typically costing `O(n log n)` time and extra memory; `maxBy` in the merge function does not require sorting everything just to select one representative per key.

If you do not need a sorted list, **comparing directly in the merge function** is usually clearer and involves less work.

### 6.4. Do not use first/last to replace version update rules

In distributed systems, a record may arrive late, be reprocessed, or be delivered twice. If the business selects by `version`, compare versions explicitly:

```java
record VersionedValue(String key, long version, String payload) {}

Comparator<VersionedValue> byVersion =
    Comparator.comparingLong(VersionedValue::version)
        .thenComparing(VersionedValue::payload);

Map<String, VersionedValue> chosen = updates.stream()
    .collect(Collectors.toMap(
        VersionedValue::key,
        Function.identity(),
        BinaryOperator.maxBy(byVersion)
    ));
```

`updates` represents a Stream or List of updates. This Comparator merely illustrates prioritizing by version and breaking ties with payload; if data shares the same version with different contents, a real system needs an **explicit conflict policy**, potentially rejecting the data rather than picking arbitrarily by string order.

## 7. Associativity of mergeFunction and Parallel Processing

A Collector can be executed via `parallelStream()`. The framework may then create multiple local Maps, process separate chunks of data, and **combine the Maps** using the merge function.

```text
                  Ordered source
                [A1, B1, A2, A3, B2]
                         │
                     split work
                ┌────────┴────────┐
                ▼                 ▼
           Local Map 1        Local Map 2
            A → ...             A → ...
            B → ...             B → ...
                └──── merge ───────┘
                        │
                        ▼
                    Result Map
```

For splitting and merging to remain valid, **the merge function must be associative** and obey the collector contract.

### 7.1. Associative merge operations

| Merge function | Formula | Result associativity |
| --- | --- | --- |
| Keep first | `(a, b) -> a` | Yes: always keeps the left value of an order-preserving merge sequence. |
| Keep last | `(a, b) -> b` | Yes: always keeps the right value of an order-preserving merge sequence. |
| Integer addition | `Long::sum` | Yes under Java integer modular arithmetic; business logic must watch for overflow. |
| Maximum | `Long::max` | Yes. |
| Minimum | `Long::min` | Yes. |
| Max by stable Comparator | `BinaryOperator.maxBy(comparator)` | Yes when the comparison relation is valid and ties are handled consistently. |
| Subtraction | `(a, b) -> a - b` | **No**. |
| Unweighted average of two averages | `(a, b) -> (a + b) / 2` | **No** in the general case. |

Counterexample:

```text
(20 - 7) - 3 = 10
20 - (7 - 3) = 16
```

Changing how elements are grouped yields different results. Therefore, do not choose subtraction as a merge function for aggregations that must remain valid under splitting and merging.

### 7.2. first/last with encounter order and parallel execution

With an ordered `List` source, standard `Collectors.toMap` is a **non-concurrent** collector and is not marked `UNORDERED`. When run in parallel, it must preserve semantics equivalent to sequential collection with respect to element encounter order; first-wins or last-wins merge functions are associative in a way that satisfies this requirement.

However, do not infer that:

- You can predict the **wall-clock order** in which lambdas execute across threads.
- Every source has an encounter order.
- The resulting `Map` automatically shares the source's iteration order.
- The first/last rule expresses "chronologically earliest/latest" if dates have not been compared.

If you need "latest by timestamp", use a Comparator as in Section 6. If you need first/last by input data, ensure the source has an explicit encounter order.

### 7.3. toConcurrentMap requires special care

`Collectors.toConcurrentMap` creates a concurrent collector, which is typically unordered. Example:

```java
ConcurrentMap<String, Long> totals = items.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Item::sku,
        Item::quantity,
        Long::sum
    ));
```

For summing by key, it does not matter which element is "first". But if you replace `Long::sum` with `(first, next) -> first` or `(first, next) -> next`, the winning value can depend on concurrent scheduling; **do not use those rules to pick a first/last record by source order** with an unordered collector.

This snippet requires `import java.util.concurrent.ConcurrentMap;`. Do not assume `toConcurrentMap` is automatically faster; key contention, element count, and source characteristics still govern performance.

### 7.4. Avoid side effects in the merge function

**Do not write:**

```java
List<String> audit = new ArrayList<>();

Map<String, Long> totals = items.parallelStream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        (a, b) -> {
            audit.add("Duplicate key found"); // Unsafe, external side effect.
            return a + b;
        }
    ));
```

`ArrayList` is not thread-safe under concurrent updates; furthermore, the number of merge calls depends on how chunks are split and combined, making it unsuitable for counting business collisions or producing formal audits.

If you need per-key statistics, gather extra data with `groupingBy` and `counting`, or a properly contracted stateful collector. Business logging should be a separate, explicitly orchestrated step after the result is ready.

## 8. Choosing a Map: HashMap, LinkedHashMap, or TreeMap?

The three-argument overload of `toMap` does not guarantee a concrete Map class or iteration order for the returned Map. If the application depends on how keys are iterated, specify `mapFactory`:

```java
Map<String, Item> firstWithInsertionOrder = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Function.identity(),
        (first, next) -> first,
        LinkedHashMap::new
    ));
```

### 8.1. Differences among maps

| Map | Characteristic | When appropriate |
| --- | --- | --- |
| `HashMap` | No iteration order guaranteed. | Key-based lookup needed, no display order required. |
| `LinkedHashMap` | Preserves key insertion order by default. | Need to display keys in first-appearance order. |
| `TreeMap` | Iterates keys by Comparator or natural order. | Need keys sorted for display or processing. |
| `ConcurrentHashMap` | Supports concurrent operations under its own contract. | Need concurrent updates/lookups with properly designed merge semantics. |

To sort product codes by key name:

```java
Map<String, Long> sortedKeys = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::sum,
        TreeMap::new
    ));
```

This example keeps the result Map's keys in natural `String` order. It **does not mean** the Map values are sorted in ascending order.

### 8.2. TreeMap may define "duplicate key" differently from HashMap

With `HashMap`, two `String` keys are considered equal when `equals` is `true`. With `TreeMap`, the Comparator's comparison rule can treat two keys as occupying the same slot if `compare(a,b) == 0`.

```java
TreeMap<String, Long> map = new TreeMap<>(
    String.CASE_INSENSITIVE_ORDER
);

map.merge("SKU-a", 10L, Long::sum);
map.merge("sku-A", 20L, Long::sum);

System.out.println(map.size()); // 1
```

Note: a Map using a comparator inconsistent with `equals` may not obey the general Map contract in the way everyone expects. When key matching is **case-insensitive**, it is often clearer to normalize `keyMapper` upfront:

```java
Map<String, Long> normalized = items.stream()
    .collect(Collectors.toMap(
        item -> item.sku().trim().toLowerCase(Locale.ROOT),
        Item::quantity,
        Long::sum
    ));
```

This snippet requires `import java.util.Locale;`. Code normalization must follow business rules; in some systems uppercase and lowercase produce distinct codes.

### 8.3. Preserving Map order does not replace keeping the first record

`LinkedHashMap` preserves **the order of keys**, whereas the merge function determines **the value for each key**. Design these two independently:

```java
// Keep keys in first-seen order, but keep the last-seen value.
Map<String, Item> map = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Function.identity(),
        (first, next) -> next,
        LinkedHashMap::new
    ));
```

If you need to paginate results in descending order of quantity, sort entries by quantity after collection or design a suitable query flow; using `LinkedHashMap` does not sort by value.

## 9. Complete Java Example: Comparing Four Policies

The following example uses the same source to compare **first wins**, **last wins**, **sum**, and **newest by timestamp**. Save to `MapMergePoliciesDemo.java`, run on Java 17+:

```java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class MapMergePoliciesDemo {
    record Event(
        String id,
        String product,
        long quantity,
        long occurredAt
    ) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("E01", "A", 4, 100),
            new Event("E02", "B", 3, 101),
            new Event("E03", "A", 2, 105),
            new Event("E04", "A", 6, 103),
            new Event("E05", "B", 7, 98)
        );

        Map<String, Event> first = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Function.identity(),
                (kept, incoming) -> kept,
                LinkedHashMap::new
            ));

        Map<String, Event> last = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Function.identity(),
                (kept, incoming) -> incoming,
                LinkedHashMap::new
            ));

        Map<String, Long> sum = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Event::quantity,
                Long::sum,
                LinkedHashMap::new
            ));

        Comparator<Event> byTimeThenId = Comparator
            .comparingLong(Event::occurredAt)
            .thenComparing(Event::id);

        Map<String, Event> newest = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Function.identity(),
                BinaryOperator.maxBy(byTimeThenId),
                LinkedHashMap::new
            ));

        System.out.println("First A: " + first.get("A").id());
        System.out.println("Last A: " + last.get("A").id());
        System.out.println("Sum A: " + sum.get("A"));
        System.out.println("Newest A: " + newest.get("A").id());

        System.out.println("First B: " + first.get("B").id());
        System.out.println("Last B: " + last.get("B").id());
        System.out.println("Sum B: " + sum.get("B"));
        System.out.println("Newest B: " + newest.get("B").id());
    }
}
```

Output:

```text
First A: E01
Last A: E04
Sum A: 12
Newest A: E03
First B: E02
Last B: E05
Sum B: 10
Newest B: E02
```

### 9.1. Why use four independent Streams?

Each call to `events.stream()` creates a fresh Stream from the traversable `List`. A Stream that has terminated with `collect` **cannot be reused**.

All four collections read the same data while applying different conflict rules. We do not need to mutate `events` or copy the source just to change the aggregation policy.

### 9.2. Comparing results per key

| Key | Keep first | Keep last | Total quantity | Latest by timestamp |
| --- | --- | --- | ---: | --- |
| A | E01 | E04 | 12 | E03 |
| B | E02 | E05 | 10 | E02 |

The table shows that **last wins and newest are not equivalent** when data arrives out of chronological order. Choosing the wrong rule can produce an incorrect current state for a business entity.

### 9.3. What if an unordered source is used?

With a source lacking encounter order, the results of keeping first or keeping last can vary across runs or execution strategies. Meanwhile, summation like `Long::sum` and picking the maximum via a Comparator with a consistent tie-breaker remain meaningful regardless of source order (within the arithmetic bounds of the type).

If reproducible results are required on any source, define a **comparison rule with an appropriate total order**, or sort the source by a business key before applying first/last.

## 10. Nulls, Duplicate Keys, Merge Returning Null, and Data Errors

### 10.1. valueMapper should not return null

The `Collectors.toMap` overloads rely on Map value creation and merging mechanisms. **Null mapped values are not safely supported**; in common JDK implementations, a `null` value triggers a `NullPointerException`.

```java
record User(String id, String email) {}

List<User> users = List.of(
    new User("U1", "an@example.com"),
    new User("U2", null)
);

// Do not do this when email may be null:
// Map<String, String> byId = users.stream()
//     .collect(Collectors.toMap(User::id, User::email));
```

You can filter out elements missing a value:

```java
Map<String, String> byId = users.stream()
    .filter(user -> user.email() != null)
    .collect(Collectors.toMap(
        User::id,
        User::email
    ));
```

However, filtering is a **data policy**, not the only approach: if a missing email is a valid state to retain, represent it with an appropriate value type or an object capturing presence/absence.

### 10.2. keyMapper must produce valid keys

Do not assume every Map type accepts `null` keys. For example, a `TreeMap` in natural order typically forbids null keys; other maps have different policies. The safest approach is to enforce input constraints:

```java
Map<String, Long> amounts = items.stream()
    .filter(item -> item.sku() != null)
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::sum
    ));
```

If invalid keys must be rejected rather than skipped, validate and throw a meaningful exception before the collect step.

### 10.3. What does mergeFunction returning null mean?

The `Map.merge` contract specifies that if the merge function returns `null` when a key already has a value, **the key entry may be removed from the Map**. This is a special behavior, not "storing a null value".

```java
Map<String, Long> map = new HashMap<>();

map.merge("A", 4L, Long::sum);
map.merge("A", 2L, (left, right) -> null);

System.out.println(map.containsKey("A")); // false
```

This snippet requires importing `java.util.HashMap`. Depending on the collector implementation and Map type, using a null-returning merge function in `toMap` can cause a key to vanish and then be recreated when a later element appears. This is a specialized behavior that must be designed and tested carefully; **do not use null to mean "keep the existing value"**. To keep the old value, return `left`.

### 10.4. Numeric overflow when summing

`Long::sum` uses Java `long` arithmetic and **does not throw an error on overflow**:

```java
long overflow = Long.sum(Long.MAX_VALUE, 1L);
// The result overflows under long arithmetic.
```

If the system must detect overflow, you can use:

```java
Map<String, Long> exact = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Math::addExact
    ));
```

`Math.addExact` throws `ArithmeticException` when an intermediate addition exceeds the limit. When very large positive and negative numbers are mixed, different merge orders can trigger or avoid intermediate overflow even when the final mathematical sum fits in range. If exact mathematical totals are required for all input combinations, consider `BigInteger` as the value type instead of `Long`.

## 11. Designing Record-Selection Rules for Business Requirements

Before choosing a merge function, answer three questions:

1. **Which key determines that two elements represent the same business entity?** Does the key need normalization?
2. **What should the final value represent?** A specific record, a total, a maximum value, or the full history?
3. **If two values collide, what determines the winner?** Encounter order, timestamp, version, priority level, or an aggregation?

Quick selection table:

| Requirement | Approach | Reminder |
| --- | --- | --- |
| Data guaranteed to have each key appear once | `toMap(keyMapper, valueMapper)` | Duplicate keys throw an exception, helping detect anomalous data. |
| Keep first element in an ordered source | `toMap(k, v, (first, next) -> first)` | Must understand encounter order. |
| Keep last element in an ordered source | `toMap(k, v, (first, next) -> next)` | Not synonymous with latest by timestamp. |
| Sum quantity/revenue by key | `toMap(k, v, Long::sum)` | Consider numeric overflow. |
| Get max/min value by key | `Long::max` / `Long::min` | Independent of source order. |
| Keep latest record by timestamp | `BinaryOperator.maxBy(comparator)` | Comparator needs a tie-breaker if timestamps can match. |
| Keep all records by key | `groupingBy(keyMapper)` | Produces grouped lists without losing history. |
| Collect complex statistics per key | `groupingBy(keyMapper, downstreamCollector)` | Fits collectors with multiple fields or states. |
| Traverse keys in first-seen order | `toMap(k, v, merge, LinkedHashMap::new)` | Key ordering is separate from the winning-value rule. |
| Need sorted keys | `toMap(k, v, merge, TreeMap::new)` | Map's Comparator affects key equivalence. |
| Need an unmodifiable map | `Map.copyOf(...)` or `toUnmodifiableMap(...)` | Watch `null`, duplicate keys, and iteration order. |

### 11.1. Do not hide business conflicts

If a system requires unique user IDs, writing `(first, second) -> first` can **mask data bugs**. When there is no legitimate rule to pick one value over another, letting `toMap` throw an exception or running an explicit validation step is safer.

If a full conflict report is needed, group first:

```java
Map<String, List<User>> byId = users.stream()
    .collect(Collectors.groupingBy(User::id));
```

Then identify groups with more than one element for investigation. `groupingBy` does not automatically verify whether values within a group have identical content; that is the next business step.

### 11.2. Element encounter order is also data that must be established

For sources fetched from a database, do not assume record ordering if the query has no `ORDER BY` clause. With parallel processing or unordered sources, processing order can differ from expectations. If first/last truly means selecting by a timestamp or sequence number, express that field in a `Comparator`.

Similarly, if the current `HashMap` order "looks right" on test data, that is not a guaranteed contract. Explicitly choose `LinkedHashMap` or `TreeMap` when result traversal order must be guaranteed.

## 12. Performance, Memory, and Resources

### 12.1. Aggregation cost versus sorting

Collecting into a Map typically traverses input elements and resolves collisions by key. With a hash map under normal conditions, average cost can be near `O(n)`, plus hashing, key comparison, and merging overhead; actual performance also depends on key distribution and Map design.

If you sort all `n` elements just to pick the latest record for each key, you pay an extra sorting cost of roughly `O(n log n)`. Using a Comparator-based merge usually avoids sorting the entire source when only one representative per key is needed.

`TreeMap` incurs search-tree operation costs, typically `O(log k)` for `k` distinct keys. Choose the Map based on key-ordering needs and data volume.

### 12.2. Number of keys determines result memory

Keeping one value per key generally uses memory proportional to the number of distinct keys, whereas `groupingBy` retains lists of all elements and can require memory proportional to total record count. If only a sum or latest representative is needed, there is no need to retain every event.

Conversely, if the application needs auditing or history retrieval, keeping only last-wins loses earlier records. Clarify retention requirements before picking a collector.

### 12.3. Parallel is not faster by default

`parallelStream()` can split work via `Spliterator` and merge local Maps. With many keys and large datasets, benefits depend on source splittability, key distribution, merge cost, and hardware resources.

Factors that can make parallel execution inefficient:

- Each partition must create its own Map and then merge large numbers of keys.
- Elements cluster onto very few keys, causing heavy contention.
- The merge function performs expensive calculations or allocations.
- Encounter order or complex tie-breaking rules must be preserved.
- Data comes from blocking I/O, which is ill-suited for simple work splitting.

Only enable parallel mode after benchmarking on representative data and verifying that the merge function adheres to its contract.

### 12.4. Collecting does not automatically close I/O sources

Example reading a CSV file with two columns `sku,quantity` and collecting totals by SKU:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class MapFromFile {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("items.csv");

        try (Stream<String> lines = Files.lines(path)) {
            Map<String, Long> totals = lines
                .filter(line -> !line.isBlank())
                .map(line -> line.split(",", -1))
                .collect(Collectors.toMap(
                    columns -> columns[0].trim(),
                    columns -> Long.parseLong(columns[1].trim()),
                    Long::sum
                ));

            System.out.println(totals);
        }
    }
}
```

This snippet illustrates a simple headerless file where each line has exactly two columns and no embedded commas inside fields. Real CSV files require a proper parser and error handling. `Files.lines(path)` is backed by an I/O resource that must be closed via `try-with-resources`; `collect` does not invoke `close()` automatically.

## 13. Common Errors

| Error | Consequence | Fix |
| --- | --- | --- |
| Using `toMap(key, value)` when keys may collide | `IllegalStateException` on key collision. | Define a merge function or fix the key rule. |
| Using `(a,b)->a` without establishing source order | Kept value may not be the intended record. | Establish encounter order or select with a `Comparator`. |
| Using last wins to select the record with the latest timestamp | Late-arriving data can overwrite a newer record. | Use `BinaryOperator.maxBy` by timestamp and tie-breaker. |
| Merging with subtraction | Not associative; result varies under splitting/merging. | Use a merge operation valid for the business domain. |
| Using `Long::sum` without considering overflow | Sums can silently wrap past `long`. | Use `Math.addExact` or a sufficiently wide numeric type. |
| Writing a merge function with side effects on an external list | Broken in parallel; call count does not match business collisions. | Separate auditing from result collection. |
| Assuming the result `Map` preserves Stream order | Default overload does not guarantee Map order. | Use `LinkedHashMap::new` or `TreeMap::new` as appropriate. |
| Confusing `LinkedHashMap` value replacement with moving keys | Key order does not change on last update. | Build a timestamp-based ordering strategy if needed. |
| Using `toConcurrentMap` with first/last by source order | Unordered collector; result can depend on scheduling. | Use a collector suitable for ordered streams or a `Comparator` on a business key. |
| `valueMapper` returns `null` | May throw `NullPointerException`. | Validate, filter, or represent absent data explicitly. |
| `mergeFunction` returns null to "keep old value" | Key may be removed from the Map. | Return the old value itself if you want to keep it. |
| Collapsing all records into one representative when history is needed | Loses detailed data. | Use `groupingBy` to retain all records. |
| Using `HashMap` with mutable keys that get modified | May fail lookups under original `hashCode`/`equals`. | Use immutable, consistent keys. |
| Reading from a file without closing the resource | Resource leak. | Use `try-with-resources`. |

## 14. Self-Check Knowledge Questions

1. When two products share the same `category`, what does `Collectors.toMap(Product::category, Product::price)` do?
2. How do the three parameters `keyMapper`, `valueMapper`, and `mergeFunction` differ?
3. What do `(first, next) -> first` and `(first, next) -> next` produce on the list `[A1, B1, A2]`?
4. Why is the last record encountered in a Stream not necessarily the one with the latest timestamp?
5. When you need the largest value by `version`, should you use `BinaryOperator.maxBy` or last wins? Why?
6. With a source lacking encounter order, do first/last rules guarantee picking the same record across runs?
7. Why is `(a,b) -> a-b` unsuitable for merging data in parallel execution?
8. Is `toConcurrentMap` suitable for keeping the first-seen record in List order?
9. Does `LinkedHashMap::new` decide the winning value on duplicate keys, or only the Map type?
10. When should you use `groupingBy` instead of `toMap`?
11. What can a `mergeFunction` returning `null` do to a key?
12. Does `Long::sum` automatically detect `long` overflow?

**Answer hints:** (1) throws `IllegalStateException`; (2) creates the key, creates the value, and decides how to merge two values with the same key; (3) A1 versus A2, B1 stays as-is; (4) data can arrive out of chronological order; (5) `maxBy` with a Comparator and tie-breaker; (6) no; (7) subtraction is not associative; (8) unsuitable when source order must be guaranteed; (9) Map type and key iteration rule, not a replacement for the merge function; (10) when keeping multiple records or using downstream collectors; (11) may delete the key entry; (12) no.

## 15. Practice Exercises

**Exercise 1 — Keep first and last.** Given a `List<Event>` with duplicate `product` values, use two `Collectors.toMap` calls to get the first and last events in List order; explain why the results differ.

**Exercise 2 — Choose highest version.** Given `VersionedValue(String key, long version, String payload)`, use `BinaryOperator.maxBy(Comparator.comparingLong(...))` to keep the latest version. Add a tie-breaker when versions match.

**Exercise 3 — Group totals.** Given `Item(String sku, long quantity)`, collect a Map of total quantities using `Long::sum`, then rewrite using `groupingBy(..., summingLong(...))`; compare clarity and downstream extensibility.

**Exercise 4 — Detect conflicts.** Given a list of users with potentially duplicate IDs, use `groupingBy(User::id)` to find groups with more than one record. When should an error be thrown instead of keeping the first record?

**Exercise 5 — Control display order.** Use `LinkedHashMap::new` to preserve the order in which keys first appear in the list. Then create another Map with `TreeMap::new` to sort keys in natural order. Leave the merge function unchanged.

**Exercise 6 — Out-of-order chronological data.** Given three events for the same product with timestamps `100, 105, 103`, demonstrate that last wins picks `103` while `maxBy` on timestamp picks `105`.

**Exercise 7 — Parallel.** Run key-based summation on sequential and parallel Streams and verify the results. Try replacing the merge with subtraction and explain why the result is no longer reliable.

**Exercise 8 — Null errors.** Given a `User` with `email == null`, write safe handling before collecting a Map from ID to email; discuss when filtering out records is unacceptable.

Hint for Exercise 2:

```java
Comparator<VersionedValue> byVersionThenPayload = Comparator
    .comparingLong(VersionedValue::version)
    .thenComparing(VersionedValue::payload);

Map<String, VersionedValue> best = updates.stream()
    .collect(Collectors.toMap(
        VersionedValue::key,
        Function.identity(),
        BinaryOperator.maxBy(byVersionThenPayload)
    ));
```

The example assumes the objects and `updates` variable are already created, `payload` is non-null, and standard string comparison applies. If `payload` is not a business tie-breaker, pick another field or reject conflicting records with the same version.

## 16. Core Takeaways

- **`Collectors.toMap` throws an error by default on duplicate keys**; to pick a value, you must supply an appropriate `mergeFunction`.
- **`(first, next) -> first`** keeps the first-seen record; **`(first, next) -> next`** keeps the last-seen record when the source has an appropriate encounter order.
- **Keeping the last is not synonymous with the chronologically newest record**. If selection must follow timestamp, version, or priority, use `BinaryOperator.maxBy`/`minBy` with an explicit Comparator and valid tie-breaker.
- **Merging values** such as `Long::sum`, `Long::max`, or combining summary records must obey the merge contract, especially associativity under parallel execution.
- **`groupingBy` retains multiple values per key** and composes with downstream collectors; `toMap` fits when each key needs a single resulting value.
- **`mapFactory` determines the Map implementation**. `LinkedHashMap` preserves key insertion order and `TreeMap` sorts keys; these two choices are independent of the duplicate-key value selection policy.
- **Do not merge via external side effects, do not assume source order, do not misuse `toConcurrentMap` for first/last**, and manage `null`, overflow, immutable keys, and I/O resource lifecycles.
- Understanding Map merge rules is foundational for designing `collect`, custom collectors, grouping, and pipelines built on `Spliterator` or parallel processing in **JAVA_STREAM_API**.
