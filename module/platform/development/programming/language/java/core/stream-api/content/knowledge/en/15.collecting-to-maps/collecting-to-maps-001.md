# Converting a Stream to a Map with Collectors.toMap

In the **Collecting to Maps** chapter of the **Java Stream API**, many problems require turning a sequence of objects into a key-based lookup structure: product code → product, employee ID → name, customer ID → total revenue. `Collectors.toMap` is the collector used to create a `Map<K, V>` from the elements of a Stream by specifying a **key** and a **value** for each element.

The first design point to decide is **whether keys are unique**. If multiple elements produce the same key, the simple `toMap` version throws an exception; in that case, you must choose a conflict-handling policy or switch to a multi-value grouping collector such as `groupingBy`. Other aspects are equally important: the desired `Map` type, ordering rules, `null` handling, safety in parallel execution, and the cost of keeping data in memory.

This lesson builds from basic examples to handling duplicate keys, aggregating data, and designing collectors according to business contracts.

## 1. The Problem: Fast Key-Based Lookup

Suppose the input data is a `List<Product>`. Each product has a unique `sku` code; the system frequently needs to look up the selling price by code.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ProductIndexDemo {

    record Product(String sku, String name, BigDecimal price) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("PEN", "Pen", new BigDecimal("12000")),
                new Product("BOOK", "Book", new BigDecimal("50000")),
                new Product("BAG", "Bag", new BigDecimal("95000"))
        );

        Map<String, BigDecimal> priceBySku = products.stream()
                .collect(Collectors.toMap(
                        Product::sku,
                        Product::price
                ));

        System.out.println(priceBySku.get("BOOK"));       // 50000
        System.out.println(priceBySku.containsKey("PEN")); // true
        System.out.println(priceBySku.size());             // 3
    }
}
~~~

In this pipeline:

1. `products.stream()` creates a Stream of `Product`.
2. `Product::sku` is the **key mapper**: each product produces a key of type `String`.
3. `Product::price` is the **value mapper**: each product produces a value of type `BigDecimal`.
4. `collect(Collectors.toMap(...))` is the **terminal operation**: it triggers the pipeline, accumulates key–value pairs, and returns a `Map<String, BigDecimal>`.

After collecting, you can use `get(key)`, `containsKey(key)`, and regular `Map` methods. However, the `Map` is not an automatic copy of the entire source object: in the example, it only stores the code and the price.

> **Implicit precondition of the two-argument overload:** Each key must appear at most once in the mapped result. `toMap` does not automatically pick the first or last value when keys collide.

## 2. Understanding the Roles of keyMapper and valueMapper

The general signature of the basic overload is:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper)
~~~

Here:

| Component | Meaning | In the example |
| --- | --- | --- |
| `T` | Stream element type | `Product` |
| `K` | Map key type | `String` |
| `U` | Map value type | `BigDecimal` |
| `keyMapper` | Function mapping `T -> K` | `Product::sku` |
| `valueMapper` | Function mapping `T -> U` | `Product::price` |
| Result | Collector creating `Map<K, U>` | `Map<String, BigDecimal>` |

The two mapping functions **do not have to return fields of the input element** (they can return the input element itself). For example, indexing the whole object by code:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

// products has type List<Product>.
Map<String, Product> bySku = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Function.identity()
        ));

Product book = bySku.get("BOOK");
~~~

`Function.identity()` returns the input element itself, so the Map value is `Product`. This approach is suitable when you need to look up the entire object by key. However, the Map still holds references to the original `Product` instances; it does not automatically deep-copy data fields.

Keys can also be another type, such as integers:

~~~java
record Worker(int id, String name) {}

Map<Integer, String> nameById = workers.stream()
        .collect(Collectors.toMap(
                Worker::id,
                Worker::name
        ));
~~~

The snippet assumes `workers` is a collection of `Worker`. This form is easy to read when each ID is unique and values are non-`null`.

## 3. Four toMap Forms to Remember

`Collectors` has four key map-related forms to keep in mind for `toMap`:

~~~java
// 1. Keys must be unique.
toMap(keyMapper, valueMapper)

// 2. Custom handling when two elements produce the same key.
toMap(keyMapper, valueMapper, mergeFunction)

// 3. Handle duplicate keys and choose how to create the result Map.
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

The three lines above are the three common **call forms** (overloads); in practice `Collectors.toMap` has **three overloads**, according to the Java 8+ signatures. Each subsequent overload adds an explicit policy.

| Overload | When to use | Requirement to watch |
| --- | --- | --- |
| `toMap(k, v)` | Keys are already unique by contract | Duplicate keys throw `IllegalStateException`. |
| `toMap(k, v, merge)` | Keys may collide; need to merge/pick a value | The merge function must express the business rule accurately. |
| `toMap(k, v, merge, factory)` | Also need a specific Map type | The factory creates a new Map, e.g. `LinkedHashMap::new` or `TreeMap::new`. |

By default, the `toMap` specification **makes no guarantees** about the type, mutability, serializability, or thread-safety of the returned Map. Do not design logic that depends on a current JDK version returning a `HashMap`.

> **Note:** `Collectors.toUnmodifiableMap` and `Collectors.toConcurrentMap` are **separate collector factories**, not additional overloads of `Collectors.toMap`. They have their own contracts regarding unmodifiability or concurrent collection.

## 4. Duplicate Keys: The Most Important Error When Using toMap

A business-valid dataset can still contain multiple lines sharing the same product code:

~~~java
import java.util.List;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> lines = List.of(
        new Item("PEN", 2),
        new Item("BOOK", 1),
        new Item("PEN", 3)
);

var quantityBySku = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity
        )); // IllegalStateException because PEN appears twice.
~~~

Both `PEN` lines produce the key `"PEN"`. The two-argument overload **does not automatically overwrite** the old value with the new one; it rejects duplicate keys.

The message usually looks like `Duplicate key ...`, though the exact wording of the error string may vary by JDK version. What matters is the duplicate-key condition, which is determined by how the Map compares keys, typically based on `equals` and `hashCode`.

Even when **two values are equal**, a duplicate key still violates this overload's contract:

~~~java
List<Item> same = List.of(
        new Item("PEN", 2),
        new Item("PEN", 2)
);

// Still reports duplicate key; does not auto-merge just because both quantities are 2.
same.stream().collect(Collectors.toMap(Item::sku, Item::quantity));
~~~

If keys are supposed to be unique yet the data contains duplicates, the exception can be a necessary signal to detect invalid data. Do not rush to add a merge function just to "make the program run" if the business domain requires unique keys.

## 5. Using mergeFunction to Decide the Value on Duplicate Keys

The three-argument overload accepts an additional `BinaryOperator<U>`:

~~~java
toMap(keyMapper, valueMapper, mergeFunction)
~~~

When a key already has a value, the collector invokes the merge function with the **accumulated value** and the **incoming value**:

~~~text
merge(oldValue, incomingValue) -> mergedValue
~~~

### 5.1. Summing quantities for duplicate product codes

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> lines = List.of(
        new Item("PEN", 2),
        new Item("BOOK", 1),
        new Item("PEN", 3)
);

Map<String, Integer> quantityBySku = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));

System.out.println(quantityBySku.get("PEN"));  // 5
System.out.println(quantityBySku.get("BOOK")); // 1
~~~

`Integer::sum` merges `2` and `3` into `5`. This rule is associative under Java integer addition semantics, making it suitable when intermediate results are combined in a parallel stream. With real-world data, consider `int` overflow; if the sum may exceed the limit, use `long` or an appropriate numeric type.

### 5.2. Picking the first or last value in an ordered stream

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Event(String id, String status) {}

List<Event> events = List.of(
        new Event("E-1", "NEW"),
        new Event("E-1", "CHECKED"),
        new Event("E-2", "NEW")
);

Map<String, String> keepFirst = events.stream()
        .collect(Collectors.toMap(
                Event::id,
                Event::status,
                (first, next) -> first
        ));

Map<String, String> keepLast = events.stream()
        .collect(Collectors.toMap(
                Event::id,
                Event::status,
                (first, next) -> next
        ));

System.out.println(keepFirst.get("E-1")); // NEW
System.out.println(keepLast.get("E-1"));  // CHECKED
~~~

In the **sequential example from an ordered List**, the two functions above illustrate picking the first or last occurrence. For data **without an encounter order**, the notions of "first" and "last" are not stably defined; do not use that approach when the business logic requires the latest record by time.

If you want the record with the most recent time, **compare using the actual timestamp**:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.stream.Collectors;

record StatusEvent(String id, Instant occurredAt, String status) {}

Map<String, StatusEvent> latest = statusEvents.stream()
        .collect(Collectors.toMap(
                StatusEvent::id,
                event -> event,
                (a, b) -> a.occurredAt().isAfter(b.occurredAt()) ? a : b
        ));
~~~

The snippet above assumes `statusEvents` is a collection of `StatusEvent` with valid timestamps. If two timestamps are equal, the example picks `b`; in a real system, add a deterministic tie-breaker such as a sequence number or event ID so the result does not depend on combination order.

### 5.3. Picking the maximum or summing monetary amounts

When values have type `BigDecimal`, you can merge using exact addition:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> amountBySku = sales.stream()
        .collect(Collectors.toMap(
                Sale::sku,
                sale -> sale.unitPrice()
                        .multiply(BigDecimal.valueOf(sale.quantity())),
                BigDecimal::add
        ));
~~~

Here `sales` is a collection of `Sale` with `sku()`, `quantity()`, and `unitPrice()`. This aggregates monetary amounts by product code: each element maps to an amount, then amounts with the same key are merged.

If monetary rounding is required, define the **rounding point according to business rules**. Do not insert `setScale` into the merge function after every addition if the goal is exact summation followed by a single rounding step, because intermediate rounding can make the result depend on combination order.

## 6. Engineering Rules for mergeFunction

A merge function does more than prevent an exception; it defines the **data semantics when multiple elements share a key**.

- **Match the business domain:** summing quantities, taking the highest price, taking the latest record by timestamp, or rejecting duplicates are completely different policies.
- **Avoid side effects:** do not mutate an external counter, list, or Map inside the merge function; splitting and combining in the pipeline can differ between sequential and parallel execution.
- **Prefer associative operations:** addition and taking min/max under a deterministic ordering are usually preferable to operations that depend on a prior running total. This keeps results stable when the Collector combines intermediate Maps.
- **Know the `Map.merge` contract:** if the merge function returns `null`, the mapping for that key may be removed. Do not return `null` as a "skip" value if the goal is to retain the key.
- **Do not equate order with correctness:** `(a, b) -> a` can mean "keep the first element" on an ordered source; it does not solve "latest record by time" if the source arrives out of order.

Example showing how returning `null` can lose a key:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Tag(String key, String value) {}

Map<String, String> result = List.of(
        new Tag("A", "one"),
        new Tag("A", "two")
).stream().collect(Collectors.toMap(
        Tag::key,
        Tag::value,
        (oldValue, newValue) -> null
));

System.out.println(result.containsKey("A")); // false
~~~

The policy "remove the key on duplicate" is rarely appropriate for business indexing. If you want to exclude invalid data, it is usually better to validate beforehand, intentionally exclude elements with `filter`, or throw an explicit exception.

## 7. Specifying the Map Type with mapFactory

The four-argument overload lets you choose the Map implementation:

~~~java
toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

`mapFactory` is a `Supplier<M>` that creates a new Map for accumulation. It is useful when the caller needs ordering rules, a specific Map type, or key semantics different from the default.

### 7.1. LinkedHashMap preserves insertion order

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> lines = List.of(
        new Item("PEN", 2),
        new Item("BOOK", 1),
        new Item("PEN", 3),
        new Item("BAG", 4)
);

Map<String, Integer> quantities = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum,
                LinkedHashMap::new
        ));

System.out.println(quantities);
// {PEN=5, BOOK=1, BAG=4}
~~~

`LinkedHashMap` preserves key insertion order by default. In this sequential example, `PEN` appears first, then `BOOK`, then `BAG`. When `PEN` appears again, merging updates its value without inserting a new key, so the key order remains unchanged.

**Do not rely on the default Map print order** when using overloads without a supplier. The `toMap` contract does not guarantee the Map type or key iteration order.

### 7.2. TreeMap sorts keys

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Integer> sortedQuantities = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum,
                TreeMap::new
        ));

System.out.println(sortedQuantities);
// {BAG=4, BOOK=1, PEN=5}
~~~

`TreeMap` is ordered by key. For `String` in the example, natural ordering applies. If keys lack a natural ordering or require custom sorting rules, construct the `TreeMap` with an explicit comparator.

One point to consider: in `TreeMap`, **key uniqueness depends on the comparator**. If the comparator treats two distinct keys as equal (comparison result is 0), the Map treats them as the same key slot, even though their `String.equals` may return false.

~~~java
import java.util.TreeMap;

Map<String, Integer> caseInsensitive = lines.stream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)
        ));
~~~

The Map type and comparator are a critical part of the data model. Do not replace `HashMap` with `TreeMap` without considering the impact on key identity.

### 7.3. The factory must create a new Map

Avoid returning a mutable Map **shared across multiple invocations** from the supplier. In parallel processing, the collector may request multiple independent accumulation containers; the factory should create a fresh empty Map each time.

~~~java
// Correct: supplier creates a new Map when called.
LinkedHashMap::new
~~~

That is the role of `Supplier<M>` in the overload—not a pre-existing Map parameter to write data into directly.

## 8. Distinguishing toMap from groupingBy

Multiple elements sharing a key can have two very different meanings:

1. **One resulting value per key:** multiple values must be merged into one, such as total quantity or total amount. Use `toMap` with a merge function.
2. **A collection of values per key:** all elements must be kept, such as a list of orders per customer. Use `groupingBy`.

Example with the same source:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String customerId, String orderId, int quantity) {}

List<Order> orders = List.of(
        new Order("C-01", "O-1", 2),
        new Order("C-02", "O-2", 1),
        new Order("C-01", "O-3", 4)
);

// One total per customer.
Map<String, Integer> totalUnits = orders.stream()
        .collect(Collectors.toMap(
                Order::customerId,
                Order::quantity,
                Integer::sum
        ));

// List of all orders per customer.
Map<String, List<Order>> ordersByCustomer = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));

System.out.println(totalUnits.get("C-01"));          // 6
System.out.println(ordersByCustomer.get("C-01").size()); // 2
~~~

If you try `toMap(Order::customerId, order -> order)`, customer key `C-01` will collide and throw an error. If you pick `(first, second) -> first` to avoid the error, the system **drops an order**. When the requirement is to keep all orders, `groupingBy` expresses the true intent.

In addition, you can combine `groupingBy` with a downstream collector to both group and sum:

~~~java
Map<String, Integer> totals = orders.stream()
        .collect(Collectors.groupingBy(
                Order::customerId,
                Collectors.summingInt(Order::quantity)
        ));
~~~

For composite collectors like `groupingBy`, downstream collectors allow computing averages, counting, transforming elements, collecting lists, or performing custom reductions. Choosing between `toMap` and `groupingBy` should be based on the **output shape** and key semantics, not merely line count.

## 9. Normalizing Keys Before Collecting

A system may treat codes `"pen"`, `"PEN"`, and `" Pen "` as the same product. In that case, keys must be normalized according to a published rule:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String sku, int quantity) {}

List<Item> input = List.of(
        new Item("pen", 2),
        new Item(" PEN ", 3),
        new Item("book", 1)
);

Map<String, Integer> quantityByCanonicalSku = input.stream()
        .collect(Collectors.toMap(
                item -> item.sku().trim().toUpperCase(Locale.ROOT),
                Item::quantity,
                Integer::sum
        ));

System.out.println(quantityByCanonicalSku.get("PEN")); // 5
~~~

`Locale.ROOT` expresses the intent to normalize codes using rules independent of the user's display locale. However, `trim` and `toUpperCase` are not valid policies for **all** identifier types; case-sensitive codes or complex Unicode identifiers may require dedicated normalization.

After normalization, **keys that were initially distinct may become duplicates**. Therefore, the merge function must be designed properly even if the raw source data had no duplicate keys under raw string comparison.

Do not convert `null` into the string `"null"` or an empty string as a key if doing so could merge independent records. When a key is required to exist, validate and reject records with missing codes.

## 10. Handling null in keyMapper and valueMapper

Map-producing collectors are **not a null-normalization mechanism**.

With `Collectors.toMap`, do not rely on the default Map implementation supporting `null` keys. The specification does not guarantee the Map type; different collection strategies or Map types may handle `null` keys differently. For `null` values, standard implementations reject them and can throw `NullPointerException`.

The safest policy is to **validate that both keys and values are appropriate before collecting**. For example:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

record User(String id, String email) {}

List<User> users = List.of(
        new User("U-1", "lan@example.com"),
        new User("U-2", null),
        new User("U-3", "minh@example.com")
);

// Illustrative rule: only index users with both an ID and an email.
Map<String, String> emailById = users.stream()
        .filter(user -> user.id() != null && user.email() != null)
        .collect(Collectors.toMap(
                User::id,
                User::email
        ));
~~~

`List.of` disallows `null` **List elements**, but `User` records inside the list can still have a `null` `email` field; the example is therefore valid.

In situations where users without an email must be kept, filtering out the user may be inappropriate. In that case, choose an explicit model, such as `Map<String, User>` (retaining the whole object with a missing email field), `Optional<String>` at the domain layer, or a separate validation error list. **Do not silently drop data** just to avoid an exception.

`Collectors.toUnmodifiableMap` (Java 10+) is stricter: it rejects `null` in both keys and values and forbids modifying the resulting Map.

## 11. When to Use toUnmodifiableMap?

If the goal is to return an **unmodifiable Map** with non-`null` keys and values, you can use:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Product> bySku = products.stream()
        .collect(Collectors.toUnmodifiableMap(
                Product::sku,
                product -> product
        ));
~~~

In this example's source code, `Product` is the record type declared earlier and `products` contains unique keys. Calling `bySku.put(...)` or `remove(...)` will throw `UnsupportedOperationException`.

This collector has an overload with a merge function if duplicate keys need to be handled:

~~~java
Map<String, Integer> quantities = lines.stream()
        .collect(Collectors.toUnmodifiableMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));
~~~

**Unmodifiability** only prevents structural modifications to the Map. If a value is a mutable object, its properties can still be modified through another reference; the Map does not automatically deep-copy values.

Another option is to collect a Map and then use `Map.copyOf(...)` (Java 10+) if the `null` contract is satisfied and an unmodifiable copy is needed. `Map.copyOf` does not guarantee preserving the iteration order of the source Map; if both ordering and unmodifiable structure are required, you must design an explicit contract and decide whether to use a view or a snapshot.

In particular, do not assume `Collectors.toMap` always creates a mutable Map just because a given JDK version allows calling `put` on the result. If Map mutability is a strict requirement, supply a `mapFactory` that creates a specific mutable Map such as `LinkedHashMap::new`.

## 12. Result Ordering, Parallel Streams, and Concurrent Collectors

### 12.1. Default Maps have no guaranteed order

Even when the source is an ordered `List`, the default `toMap(k, v)` overload **does not guarantee Map iteration order**. If you need output in key-appearance order, use `LinkedHashMap::new` with a sequential pipeline that has an encounter order. If you need keys sorted, use `TreeMap::new` with an appropriate comparator.

For Maps with the same set of keys and values, the order of `Map.toString()` is not a valid way to verify correctness of the default overload. Access entries via `get` or compare Maps according to the mapping contract.

### 12.2. Parallel streams do not make an ordinary Map concurrent

~~~java
Map<String, Integer> quantities = lines.parallelStream()
        .collect(Collectors.toMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));
~~~

With a standard Collector, the library can create **multiple intermediate Maps** and merge them. This differs from multiple threads mutating an arbitrary external `HashMap`. Do not replace the collector with:

~~~java
// Wrong: writing to a shared HashMap from parallel tasks.
Map<String, Integer> shared = new java.util.HashMap<>();

lines.parallelStream().forEach(item ->
        shared.put(item.sku(), item.quantity())
);
~~~

This approach introduces race-condition risks, overwrites duplicate keys, and fails to merge quantities by rule. Use the appropriate Collector instead.

### 12.3. toConcurrentMap has a different contract

When you genuinely need a `ConcurrentMap` and the pipeline can collect independently of encounter order, Java provides `Collectors.toConcurrentMap`:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Integer> concurrentTotals = lines.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Item::sku,
                Item::quantity,
                Integer::sum
        ));
~~~

`toConcurrentMap` has a collector supporting concurrent accumulation and is unordered; the resulting Map's iteration order is not the input list's order. When keys collide, the merge function must have stable semantics across different combination patterns.

Do not assume `toConcurrentMap` is faster than `toMap`: performance depends on source size, number of distinct keys, key contention, mapping cost, and runtime environment characteristics. Measure performance before optimizing.

### 12.4. Associativity limits of merging

When a pipeline runs in parallel, the order in which duplicate values are combined may differ from sequential execution. Therefore, prefer associative merge operations for aggregated values, such as summing quantities, adding exact `BigDecimal` values, or taking min/max under a consistent order.

Sequential subtraction, rounding after **each** addition, or relying on the update sequence of a shared variable can change results depending on execution scheduling. If the problem requires the "latest event", comparing by timestamp key and a deterministic tie-breaker is usually better than keeping the "last processed record".

## 13. Complete Real-World Example: Total Revenue by Product Code

An application needs total revenue per product code from order lines. Each line has a code, quantity, and unit price; multiple lines can share the same code. Requirement: preserve the **first-appearance** order of each code in the input data and calculate monetary amounts with exact `BigDecimal` arithmetic before formatting.

~~~java
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SalesBySkuDemo {

    record Sale(String sku, long quantity, BigDecimal unitPrice) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("PEN", 2, new BigDecimal("12.50")),
                new Sale("BOOK", 1, new BigDecimal("30.00")),
                new Sale("PEN", 1, new BigDecimal("10.00"))
        );

        Map<String, BigDecimal> revenueBySku = sales.stream()
                .collect(Collectors.toMap(
                        Sale::sku,
                        sale -> sale.unitPrice().multiply(
                                BigDecimal.valueOf(sale.quantity())),
                        BigDecimal::add,
                        LinkedHashMap::new
                ));

        System.out.println(revenueBySku);
        // {PEN=35.00, BOOK=30.00}

        System.out.println(revenueBySku.get("PEN"));  // 35.00
        System.out.println(revenueBySku.get("BOOK")); // 30.00
    }
}
~~~

Calculation:

~~~text
PEN:  2 x 12.50 + 1 x 10.00 = 35.00
BOOK: 1 x 30.00               = 30.00
~~~

What the pipeline does:

1. `Sale::sku` creates the key for each line.
2. The value mapper computes the line amount and produces a `BigDecimal` value.
3. `BigDecimal::add` merges amounts with the same key **without intermediate rounding**.
4. `LinkedHashMap::new` requests a Map preserving insertion order, so under sequential processing the codes appear in order `PEN`, `BOOK`.

If business rules specify rounding amounts at the invoice, tax, or line level, apply the exact rule at the **designated boundary**. The example intentionally avoids applying a rounding policy on its own because the input values are already exact and the task is solely to sum by product code.

## 14. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `IllegalStateException: Duplicate key ...` | Two elements produce the same key in `toMap(k, v)` | If duplicates are errors, validate the source; if valid, add a business-appropriate merge function. |
| Missing data rows after using `(old, next) -> old` | Chose to keep one value when all values were actually needed | Use `groupingBy` when each key must hold a list of multiple values. |
| `NullPointerException` when collecting Map | Key/value mapper produces missing or null values incompatible with collector/result Map | Validate and apply an explicit null policy before collecting. |
| Map iteration order differs from input List | `toMap` does not guarantee Map order by default | Choose `LinkedHashMap::new` or `TreeMap::new` to match requirements. |
| Results vary on unordered sources when "keeping last" | Rule depends on an unguaranteed order | Pick the value using a timestamp and a deterministic tie-breaker. |
| Duplicate records not merged after code normalization | Keys were not normalized consistently | Use a canonical key and a meaningful merge function. |
| Sums fluctuate under parallel execution | Non-associative merge or reliance on side effects | Use an associative merge, avoid shared state, and avoid arbitrary intermediate rounding. |
| Casting the result Map fails | Assumed the default overload always returns a specific class | Program to the `Map` interface or supply a `mapFactory`. |
| Expected an unmodifiable Map yet `put` works | Use `toUnmodifiableMap` / `Map.copyOf` | Clearly specify mutable vs. unmodifiable in the API contract. |
| High memory growth | The Map retains all distinct key–value pairs and referenced objects | Reduce fields, aggregate directly, process in batches, or use a database where appropriate. |

## 15. Performance, Lifecycle, and Pipeline Limits

`collect(Collectors.toMap(...))` is a **terminal operation**. Preceding `filter`, `map`, and `flatMap` steps generally execute only when the terminal operation begins processing. After collecting the Map, you must not reuse the **same Stream instance** for another terminal operation.

A Map typically holds one entry per distinct key; if the Stream contains millions of keys, memory still grows with the number of entries. `toMap` is not a constant-memory aggregation for unbounded numbers of keys.

An infinite source that continuously introduces new keys cannot be collected into a finite Map with `collect(toMap)` without a stopping condition. Use `limit(n)` or an appropriate finite source when a fully materialized result is needed. For data read from files or I/O sources, manage lifecycle and resource closing separately; `collect` does not replace `try-with-resources`.

Optimization notes:

- If key-based lookups are needed repeatedly, a Map can save work compared to repeatedly filtering a list; efficiency also depends on the Map type and entry count.
- If you only need to check whether a code exists, `anyMatch` can short-circuit and avoid building an entire Map.
- If multiple values per key are needed, `groupingBy` avoids manually writing list-merging logic inside `toMap`.
- Do not switch a Stream to parallel just because there are many elements; with too little data or heavy contention on duplicate keys, overhead can be significant.
- Avoid mutable keys: modifying fields involved in `equals`/`hashCode` of a key after inserting it into a hash-based Map can make the entry impossible to look up.
- When choosing `TreeMap`, consider sorting and comparator costs; choose the structure based on requirements rather than merely shorter syntax.

These techniques also connect to custom collectors, `Spliterator`, and Stream API parallel processing: key contracts and data-combination semantics must remain intact even when the source is split or traversed differently.

## 16. Self-Check Exercises

### Exercise 1 — Predicting duplicate-key failure

~~~java
record Product(String sku, int price) {}

List<Product> products = List.of(
        new Product("A", 10),
        new Product("A", 10)
);

Map<String, Integer> prices = products.stream()
        .collect(Collectors.toMap(
                Product::sku,
                Product::price
        ));
~~~

**Answer:** Throws `IllegalStateException` because the key `"A"` appears twice, even though both corresponding values are 10. If the source must be unique, fix the data; if duplicates are valid, define a merge function.

### Exercise 2 — Summing quantities by key

~~~java
record Line(String code, int count) {}

List<Line> lines = List.of(
        new Line("A", 2),
        new Line("B", 4),
        new Line("A", 3)
);
~~~

**Task:** Create a `Map<String, Integer>` summing quantities with the same code.

**Answer:**

~~~java
Map<String, Integer> total = lines.stream()
        .collect(Collectors.toMap(
                Line::code,
                Line::count,
                Integer::sum
        ));

System.out.println(total.get("A")); // 5
System.out.println(total.get("B")); // 4
~~~

### Exercise 3 — Choosing toMap or groupingBy

**Task:** Given a `Stream<Order>`, keep **all orders** grouped by `customerId`.

**Answer:** Use `Collectors.groupingBy(Order::customerId)` to obtain `Map<String, List<Order>>`. Using `toMap(Order::customerId, Function.identity())` will fail for customers with multiple orders; choosing to keep one order will lose the remaining orders.

### Exercise 4 — Key ordering

**Task:** From a `List` whose keys appear in the order `B`, `A`, `C`, return a Map preserving key insertion order.

**Answer:** Use a sequential pipeline and `Collectors.toMap(keyMapper, valueMapper, mergeFunction, LinkedHashMap::new)`. Do not rely on the key ordering of the default overload.

### Exercise 5 — Selecting the latest record

Two events share the same code, but are read in reverse chronological order. Should you use `(oldValue, newValue) -> newValue` to get the latest record?

**Answer:** No, if processing order is not guaranteed to match chronological order. You must compare a reliable timestamp or sequence number with a deterministic tie-breaker, then pick the greatest event by that criterion.

### Exercise 6 — Unmodifiable Map

~~~java
Map<String, String> result = Stream.of("a", "b")
        .collect(Collectors.toUnmodifiableMap(
                value -> value,
                value -> value.toUpperCase(java.util.Locale.ROOT)
        ));
~~~

**Question:** Can you call `result.put("c", "C")`? What happens if the Stream has two `"a"` elements?

**Answer:** `put` throws `UnsupportedOperationException`. If two elements both produce the key `"a"` and the overload without a merge function is used, the collector will throw `IllegalStateException` due to the duplicate key.

## 17. Key Takeaways

- `Collectors.toMap(keyMapper, valueMapper)` turns a Stream into a `Map<K, V>` when keys are unique.
- When keys can collide, use `toMap(keyMapper, valueMapper, mergeFunction)`, but **only after choosing a business-correct merge rule**.
- To specify a concrete Map type, use the overload with `mapFactory`: `LinkedHashMap::new` for insertion order or `TreeMap::new` for key order.
- Use `groupingBy` when **multiple values** per key must be kept; `toMap` fits when each key ultimately maps to **a single merged value**.
- Explicitly address duplicate keys, `null`, identifier normalization, traversal order, merge associativity, and memory limits before putting a pipeline into production.
- `Collectors.toUnmodifiableMap` creates an unmodifiable Map and rejects `null`; `toConcurrentMap` is for scenarios requiring a concurrent Collector.
- `collect` terminates the Stream; infinite sources need a stopping condition, and I/O sources must be properly closed according to their lifecycle.

**Main idea:** `Collectors.toMap` is the tool for indexing and aggregating data by key in the Java Stream API. To get correct results, answer three questions upfront: **which key identifies an entry**, **how to merge duplicate keys**, and **what Map type/ordering contract the result requires**. When those rules are clear, the pipeline becomes easy to read, easy to test, and safely extensible to data grouping or parallel processing.
