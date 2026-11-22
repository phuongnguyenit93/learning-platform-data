# Unmodifiable Collectors Since Java 10

## 1. Why Does the Java Stream API Need Unmodifiable Collectors?

In **JAVA_STREAM_API**, we commonly use `filter`, `map`, `flatMap`, `reduce`, and `collect` to transform source data into results. Many `collect` results are `List`, `Set`, or `Map`. A problem arises when a method exposes results for other parts of the program to use:

```java
List<String> names = users.stream()
    .map(User::name)
    .collect(Collectors.toList());
```

This snippet obtains a list, but **the contract of `Collectors.toList()` does not guarantee whether the list is mutable or not**. Relying on `names.add(...)` as a business condition depends on uncommitted behavior. Conversely, if you want to prevent callers from modifying the report's structure, relying solely on the `List` type is insufficient.

Starting in **Java 10**, the `java.util.stream.Collectors` class provides these factories:

- `Collectors.toUnmodifiableList()`;
- `Collectors.toUnmodifiableSet()`;
- `Collectors.toUnmodifiableMap(keyMapper, valueMapper)`;
- `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)`.

These collectors produce **collections that disallow mutating operations**. They are especially suitable when a pipeline's output is a **structural snapshot** sent to an API layer, reporting screen, or another business process.

### Learning Objectives

After this lesson in the **JDK Compatibility** chapter, you will be able to:

1. Identify the minimum JDK version providing the `toUnmodifiable*` collectors.
2. Read the generic signatures of `Collector<T,A,R>` and the `List`, `Set`, and `Map` result types.
3. Distinguish **structurally unmodifiable** results from deep immutability of elements.
4. Properly handle `null` elements, `null` keys/values, and duplicate keys.
5. Distinguish `Collectors.toList()`, `Stream.toList()`, `List.copyOf()`, and `Collections.unmodifiableList(...)`.
6. Combine unmodifiable collectors with `groupingBy`, `mapping`, and `filtering`.
7. Write equivalent solutions for projects that must remain on Java 8 or Java 9.
8. Test the `UnsupportedOperationException` contract and avoid relying on uncommitted ordering.

In this lesson, the integrated demonstration program runs on **JDK 17+** because it uses `record`. `Collectors.toUnmodifiable*` itself only requires **Java 10+**; upgrading to Java 17 is not required to use it.

## 2. Timeline: Do Not Confuse Versions of Similarly Named APIs

| API | Version Introduced | Main Purpose |
| --- | --- | --- |
| `Stream.collect(...)`, `Collectors.toList()`, `toSet()`, `toMap()` | Java 8 | Collects results; **does not promise** immutable results |
| `Collections.unmodifiableList/Set/Map(...)` | Pre-Java 8 | Creates an **unmodifiable wrapper view** |
| `List.of(...)`, `Set.of(...)`, `Map.of(...)` | Java 9 | Creates unmodifiable collections from values |
| `Collectors.toUnmodifiableList/Set/Map` | **Java 10** | Collects directly from a `Stream` into an unmodifiable collection |
| `List.copyOf(...)`, `Set.copyOf(...)`, `Map.copyOf(...)` | **Java 10** | Creates an unmodifiable copy from an existing collection/map |
| `Collectors.teeing(...)` | Java 12 | Combines two downstream collectors; does not imply immutability |
| `Stream.toList()` | **Java 16** | Convenient terminal operation returning an unmodifiable list |

Commonly confused points:

- `Collectors.toList()` **was not upgraded to an immutable contract** after Java 10.
- `Stream.toList()` did **not** exist in Java 10; it was added in **Java 16**.
- `List.of` appeared in **Java 9**, while `List.copyOf` appeared in **Java 10**.
- `Collections.unmodifiableList` is an older API, yet **a wrapper view is not the same as an independent snapshot**.
- The three unmodifiable collectors from Java 10 live in `Collectors`, **not** in `Spliterator`'s `IMMUTABLE` characteristic.

Official Javadoc references: [`Collectors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html), [`Stream.toList()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#toList()), [`List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html), [`Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

## 3. Generic Signatures and the Meaning of "Unmodifiable"

The main signatures have the form:

```java
static <T> Collector<T, ?, List<T>> toUnmodifiableList()

static <T> Collector<T, ?, Set<T>> toUnmodifiableSet()

static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper
)

static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
)
```

In `Collector<T,A,R>`:

- `T` is the source stream element type.
- `A` is the internal accumulation state, represented with wildcard `?` because it is not part of the public contract.
- `R` is the resulting collection: `List<T>`, `Set<T>`, or `Map<K,U>` respectively.

"Unmodifiable" here means **disallowing collection mutation via add, remove, or replace element/entry operations**. Attempting an unsupported mutation throws `UnsupportedOperationException`.

Example:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> labels = Stream.of("A", "B", "C")
    .collect(Collectors.toUnmodifiableList());

System.out.println(labels); // [A, B, C]
// labels.add("D");          // UnsupportedOperationException
// labels.set(0, "Z");       // UnsupportedOperationException
// labels.remove("B");       // UnsupportedOperationException
```

**Two important limitations:**

1. An unmodifiable **collection structure** does not mean the elements `T` inside are always immutable.
2. Do not rely on implementation class names or cast the result to `ArrayList`, `HashSet`, or `HashMap`: the API only promises the respective interface.

## 4. `Collectors.toUnmodifiableList()`

### 4.1. Preserves Encounter Order When the Source Is Ordered

`toUnmodifiableList()` collects elements into an unmodifiable list, following **encounter order** if the pipeline has one:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> result = Stream.of(8, 3, 8, 1)
    .filter(n -> n > 1)
    .collect(Collectors.toUnmodifiableList());

System.out.println(result); // [8, 3, 8]
```

The list **retains duplicate elements**, just like an ordinary `List`. The collector does not automatically deduplicate or sort:

- `filter` decides which elements are kept.
- `sorted` (if called) decides the new order.
- `distinct` (if called) removes duplicates by `equals`.
- `toUnmodifiableList()` collects the final result and **forbids modifying the list**.

Example:

```java
List<String> names = Stream.of("Chi", "An", "An", "Bình")
    .distinct()
    .sorted()
    .collect(Collectors.toUnmodifiableList());

System.out.println(names); // [An, Bình, Chi]
```

### 4.2. Rejects `null`

`Collectors.toUnmodifiableList()` **rejects `null` elements**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> nullable = Arrays.asList("A", null, "B");

// Throws NullPointerException when the terminal operation executes:
// nullable.stream().collect(Collectors.toUnmodifiableList());
```

If the data domain permits dropping missing elements, filter explicitly:

```java
List<String> nonNull = nullable.stream()
    .filter(java.util.Objects::nonNull)
    .collect(Collectors.toUnmodifiableList());
// [A, B]
```

If `null` indicates corrupted data, filtering will **hide the error signal**. In that case, validate and throw an exception with a clear message, or return a separate error report rather than silently skipping it.

### 4.3. Empty Sources and Copies

`Stream.<String>empty().collect(Collectors.toUnmodifiableList())` returns an empty unmodifiable list. You can store it, pass it across APIs, and iterate over it multiple times as a normal result. However, do not require that **each collection creates a distinct object** or that it has a specific concrete class: the JDK may reuse immutable instances when appropriate.

```java
List<String> empty = Stream.<String>empty()
    .collect(Collectors.toUnmodifiableList());

System.out.println(empty.isEmpty()); // true
```

## 5. `Collectors.toUnmodifiableSet()`

`toUnmodifiableSet()` collects elements into an unmodifiable `Set`.

```java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Set<String> regions = Stream.of("HN", "HCM", "HN", "DN")
    .collect(Collectors.toUnmodifiableSet());

System.out.println(regions.size()); // 3
System.out.println(regions.contains("HN")); // true
// regions.add("HP"); // UnsupportedOperationException
```

### 5.1. Duplicate Elements Are Removed by `equals`

If multiple elements are considered equal by `equals`, the `Set` keeps one representative. For equal objects that are distinct instances, **do not rely on which instance is retained**:

```java
record Tag(String code) {}

Tag first = new Tag("VIP");
Tag second = new Tag("VIP");

Set<Tag> tags = Stream.of(first, second)
    .collect(Collectors.toUnmodifiableSet());

System.out.println(tags.size()); // 1
// Do not assert tags.iterator().next() == first.
```

This differs from "keep the first record" in a report requiring a specific order. If you want to pick a representative by timestamp priority, define merging/sorting with business criteria rather than relying on `Set`.

### 5.2. No Guaranteed Iteration Order

`toUnmodifiableSet()` is an **unordered** collector. Iteration order of the `Set` may differ from the source order and may vary across implementations or runs. Proper test:

```java
Set<String> expected = Set.of("HN", "HCM", "DN");
assertEquals(expected, regions); // JUnit: compares Set values
```

Contract-violating test:

```java
// Do not use this test:
// assertEquals(List.of("HN", "HCM", "DN"),
//     new ArrayList<>(regions));
```

If business logic requires **ordering**, keep a `List` (e.g., `distinct` then `toUnmodifiableList`), or use a chosen structure with ordering rules and wrap an appropriate snapshot.

### 5.3. `null` and Empty Sets

`Collectors.toUnmodifiableSet()` rejects `null` elements. An empty source produces an empty unmodifiable `Set`. Avoid testing with `Set.of("HN", null)` to construct test data, because `Set.of` itself throws `NullPointerException` before the pipeline runs; to test the collector, use `ArrayList` or `Arrays.asList` with a null element.

## 6. `Collectors.toUnmodifiableMap()`: Keys, Values, and Collisions

With `Stream<Order>`, a common need is looking up by `id`:

```java
Map<String, Order> byId = orders.stream()
    .collect(Collectors.toUnmodifiableMap(
        Order::id,
        java.util.function.Function.identity()
    ));
```

The signature takes two mappers:

- `keyMapper` produces `K`.
- `valueMapper` produces `U`.
- Result is an unmodifiable `Map<K,U>`.

### 6.1. Two-Parameter Overload: Duplicate Keys Are Errors

When two elements produce the same key by `equals`, `toUnmodifiableMap(keyMapper, valueMapper)` throws `IllegalStateException`.

```java
record Product(String sku, int price) {}

List<Product> products = List.of(
    new Product("P-01", 100),
    new Product("P-01", 200)
);

// Throws IllegalStateException due to duplicate key P-01:
// products.stream().collect(Collectors.toUnmodifiableMap(
//     Product::sku, Product::price
// ));
```

This works well for models where **keys must be unique**. Do not silently overwrite with the last element if duplicate SKUs signal invalid input data.

### 6.2. Three-Parameter Overload: Deciding How to Merge Values

If duplicate keys are valid, use the overload with `mergeFunction`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("HN", 100L),
    new Sale("HCM", 50L),
    new Sale("HN", 80L)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.toUnmodifiableMap(
        Sale::region,
        Sale::amountVnd,
        (a, b) -> Math.addExact(a, b)
    ));

System.out.println(totals.get("HN")); // 180
System.out.println(totals.get("HCM")); // 50
```

Here, `Long` is inferred from the mapper returning `long` via autoboxing. `Math.addExact` detects `long` overflow instead of silently wrapping around. For inputs with **non-negative** amounts, exact addition within the non-overflowing domain is compatible with how the pipeline partitions and merges sub-results.

When values are mutable objects and the merge function mutates an existing object, carefully check the **no shared state** and side-effect contract. Ideally, use a value type or an accumulator with clear business meaning.

### 6.3. `null` Is Disallowed

Neither **keys** nor **values** returned by the mappers may be `null`:

```java
import java.util.ArrayList;
import java.util.List;

record Row(String key, String value) {}

List<Row> rows = new ArrayList<>();
rows.add(new Row("a", "x"));
rows.add(new Row(null, "y"));

// Throws NullPointerException:
// rows.stream().collect(Collectors.toUnmodifiableMap(
//     Row::key, Row::value
// ));
```

`null` values are also rejected. This is an important difference from some mutable map implementations that allow null; **do not extrapolate null policy from a familiar map type**.

Choose one of three strategies: **reject**, **skip the record if business logic allows**, or **normalize to a valid sentinel value type**. Do not arbitrarily convert a missing key into `"UNKNOWN"` if there is any risk of colliding with a valid code.

### 6.4. `toUnmodifiableMap` Has No `mapFactory`

`Collectors.toUnmodifiableMap` has no overload to choose `LinkedHashMap::new` or `TreeMap::new`. Therefore, **key iteration order is not guaranteed** in the final map.

```java
Map<String, Long> byRegion = sales.stream()
    .collect(Collectors.toUnmodifiableMap(
        Sale::region, Sale::amountVnd, Long::sum
    ));

// Do not assert:
// new ArrayList<>(byRegion.keySet()) == [HN, HCM]
```

If key order is part of the contract, see section 13/14 on collecting into a `LinkedHashMap`/`TreeMap`, then creating a copy and wrapping an unmodifiable view.

## 7. Choosing the Right Collector for the Goal

| Input and Requirement | Appropriate Collector | Result |
| --- | --- | --- |
| Keep all elements including duplicates; preserve encounter order | `toUnmodifiableList()` | `List<T>` |
| Obtain distinct values, no order required | `toUnmodifiableSet()` | `Set<T>` |
| Map unique keys to values, duplicates must error | `toUnmodifiableMap(key, value)` | `Map<K,U>` |
| Map potentially duplicate keys, explicit merge needed | `toUnmodifiableMap(key, value, merge)` | `Map<K,U>` |
| Want a map with specific key iteration order | `toMap(..., mapFactory)` then snapshot/wrap view | Map of chosen type |
| Want caller to be able to add/remove results | `toCollection(ArrayList::new)` or mutable map of right type | Mutable collection |
| Want deep immutability of every record | Unmodifiable collection **and** immutable elements | Guaranteed at both layers |

**First decision question:** should the report be treated as a fixed snapshot or a container that continues to be updated? If updates are needed, do not pick an unmodifiable collector only to copy it back immediately without reason.

## 8. Complete Java 17 Example: Building a Read-Only Report

The following sales model uses an immutable `Order` record. The program demonstrates using `List`, `Set`, and `Map` collected with Java 10 collectors.

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public final class UnmodifiableCollectorsDemo {

    private UnmodifiableCollectorsDemo() {}

    public record Order(
        String id,
        String region,
        long amountVnd,
        boolean paid
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank() || amountVnd < 0L) {
                throw new IllegalArgumentException("Invalid Order");
            }
        }
    }

    public record Report(
        List<Order> paidOrders,
        Set<String> regions,
        Map<String, Order> ordersById,
        Map<String, Long> paidTotalsByRegion
    ) {}

    public static List<Order> sample() {
        return List.of(
            new Order("O-1", "HN", 120_000L, true),
            new Order("O-2", "HCM", 80_000L, true),
            new Order("O-3", "HN", 40_000L, false),
            new Order("O-4", "DN", 50_000L, true),
            new Order("O-5", "HCM", 20_000L, true)
        );
    }

    public static Report buildReport(List<Order> source) {
        Objects.requireNonNull(source, "source");

        List<Order> paid = source.stream()
            .filter(Order::paid)
            .collect(Collectors.toUnmodifiableList());

        Set<String> regions = source.stream()
            .map(Order::region)
            .collect(Collectors.toUnmodifiableSet());

        Map<String, Order> byId = source.stream()
            .collect(Collectors.toUnmodifiableMap(
                Order::id,
                java.util.function.Function.identity()
            ));

        Map<String, Long> paidTotals = source.stream()
            .filter(Order::paid)
            .collect(Collectors.toUnmodifiableMap(
                Order::region,
                Order::amountVnd,
                (a, b) -> Math.addExact(a, b)
            ));

        return new Report(paid, regions, byId, paidTotals);
    }

    public static void main(String[] args) {
        Report report = buildReport(sample());

        System.out.println(report.paidOrders().stream()
            .map(Order::id).toList());
        // [O-1, O-2, O-4, O-5]

        System.out.println(report.regions().size()); // 3
        System.out.println(report.ordersById().get("O-3").amountVnd());
        // 40000

        System.out.println(report.paidTotalsByRegion().get("HCM"));
        // 100000
        System.out.println(report.paidTotalsByRegion().get("HN"));
        // 120000

        // None of the four collections allow direct mutation:
        // report.paidOrders().add(...);
        // report.regions().add("HP");
        // report.ordersById().put("O-6", ...);
        // report.paidTotalsByRegion().clear();
    }
}
```

### 8.1. Result Analysis

- `paidOrders` preserves encounter order from the source `List<Order>`; it contains only the four orders with `paid == true`.
- `regions` has three regions `HN`, `HCM`, `DN`, but **does not guarantee iteration order**.
- `ordersById` indexes all five orders by unique `id`; duplicate IDs **throw an error** rather than silently overwriting.
- `paidTotalsByRegion` sums only paid orders, with `HCM = 100_000`, `HN = 120_000`, `DN = 50_000`. Map entry print order has no guarantee.
- `Report` is a record, and the collections inside are all unmodifiable results; the `Order` items are also records containing strings and primitives, so in this model there is no mutable state inside elements.

### 8.2. Single Pass or Multiple Passes?

`buildReport` traverses the source `List` four times, suitable for a small, clear example. However, **a consumed `Stream` cannot be reused**:

```java
// Wrong:
// Stream<Order> stream = source.stream();
// var list = stream.collect(Collectors.toUnmodifiableList());
// var set = stream.map(Order::region)
//     .collect(Collectors.toUnmodifiableSet());
```

When the source is very large or single-pass only, design a combined collector or appropriate `teeing` and `groupingBy` downstreams. Read-only results alone do not solve the cost of multiple traversals.

## 9. Unmodifiable Collections Differ from Deep Immutability

Consider a **mutable** object type:

```java
final class MutableUser {
    private String name;

    MutableUser(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String next) {
        this.name = next;
    }
}

MutableUser user = new MutableUser("An");
List<MutableUser> users = Stream.of(user)
    .collect(Collectors.toUnmodifiableList());

// users.add(new MutableUser("Bình")); // UnsupportedOperationException
user.rename("Chi");                    // Valid: element is still mutable.
System.out.println(users.get(0).name()); // Chi
```

Unmodifiable collectors protect **collection membership**, not immutability of the referenced objects. Consequences:

1. Elements cannot be added/removed/reordered through that list.
2. If a mutable element is modified elsewhere, the value observed in the list can change.
3. If an element is used as a **map/set key**, mutating fields involved in `equals/hashCode` can break lookup or correctness.
4. If a map's values are mutable `List`s, an unmodifiable `Map` does **not** make those lists immutable.

For deep immutability, design immutable value objects (`record` with immutable components, defensive copies for nested collections), or copy data into immutable DTOs before collecting.

### 9.1. There Is No "Freeze Entire Object Graph" Operation

`toUnmodifiableList`, `toUnmodifiableSet`, and `toUnmodifiableMap` are not deep-copy utilities. They do not copy each `Order`, do not clone an object graph, and do not make all mutable fields final.

Specifically, the record:

```java
record Group(String name, List<String> members) {}
```

has a `members` field that is final by reference, yet if it receives a mutable `ArrayList` from the caller, the list's contents can still change. For structural immutability:

```java
record SafeGroup(String name, List<String> members) {
    SafeGroup {
        members = List.copyOf(members); // Java 10+, rejects null.
    }
}
```

However, if elements inside the list are also mutable, `List.copyOf` still **does not deep-copy** those elements.

## 10. Unmodifiable Views vs. Independent Snapshots: A Huge Difference

`Collections.unmodifiableList(existing)` returns a **view** that disallows mutation via the wrapper, yet **reflects changes to the original collection**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

ArrayList<String> mutable = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(mutable);

mutable.add("C");
System.out.println(view); // [A, B, C]
// view.add("D");          // UnsupportedOperationException
```

When you need a **structural snapshot** no longer modifiable by other callers:

```java
List<String> snapshot = Collections.unmodifiableList(
    new ArrayList<>(mutable)
);

mutable.add("D");
System.out.println(snapshot); // [A, B, C]
```

Here `new ArrayList<>(mutable)` detaches the container, and `unmodifiableList` protects the detached container. Without copying, another piece of code holding a reference to `mutable` can still alter the view.

Comparison:

| Creation Approach | Mutable via Result? | Result Changes When Original Changes? | Minimum JDK |
| --- | --- | --- | --- |
| `Collections.unmodifiableList(mutable)` | No | **Yes**, because it is a view | Pre-Java 8 |
| `Collections.unmodifiableList(new ArrayList<>(mutable))` | No | No, for structural membership | Pre-Java 8 |
| `List.copyOf(mutable)` | No | No, for structural membership | Java 10 |
| `mutable.stream().collect(toUnmodifiableList())` | No | No, for structural membership | Java 10 |

In every row, **mutable elements inside** can still change; the table refers only to the **container**.

## 11. `List.copyOf`, `Set.copyOf`, and `Map.copyOf` Since Java 10

The three `copyOf` methods create **unmodifiable collections** from an existing collection/map. They differ from `Collectors.toUnmodifiable*` in their **starting point**:

- `Collectors.toUnmodifiableList()` receives elements emitted by a **stream**.
- `List.copyOf(collection)` receives an existing **collection**.
- `Set.copyOf(collection)` receives an existing **collection** and builds a set of elements.
- `Map.copyOf(map)` receives an existing **map**.

Example:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

ArrayList<String> source = new ArrayList<>(List.of("HN", "HCM"));
List<String> immutableList = List.copyOf(source);

source.add("DN");
System.out.println(immutableList); // [HN, HCM]

Set<String> immutableSet = Set.copyOf(source);
System.out.println(immutableSet.size()); // 3

Map<String, Integer> mutableMap = new HashMap<>();
mutableMap.put("HN", 1);
Map<String, Integer> immutableMap = Map.copyOf(mutableMap);

mutableMap.put("HN", 5);
System.out.println(immutableMap.get("HN")); // 1
```

### 11.1. Policies You Must Know

| Factory | Accepts `null`? | Keeps Duplicates? | Preserves Order? |
| --- | --- | --- | --- |
| `List.copyOf(collection)` | No | Yes | Preserves iteration order of source collection |
| `Set.copyOf(collection)` | No | No; may retain any representative among equal elements | No iteration order guarantee |
| `Map.copyOf(map)` | No for null keys/values | Input map already has unique keys | No key iteration order guarantee |

If the passed-in collection is already of a suitable unmodifiable form, the implementation may **avoid allocating a new container**. Do not write tests like `copy != original` or assume `copyOf` always allocates; what matters is the content and mutability contract, not instance identity.

### 11.2. `copyOf` Is Not a Deep-Copy Promise

For example, `List.copyOf(List<MutableUser>)` copies the list structure, while the `MutableUser` instances inside remain the same objects. The same principle applies to `toUnmodifiable*`.

### 11.3. Do Not Use `Map.copyOf` If You Need to Preserve Key Order

`Map.copyOf(linkedHashMap)` creates an unmodifiable map but **does not guarantee preserving insertion order**. To preserve `LinkedHashMap` iteration order, use a **`LinkedHashMap` copy** wrapped with `Collections.unmodifiableMap`. For `TreeMap`, wrap a `TreeMap` copy with `Collections.unmodifiableSortedMap`.

## 12. Comparing `Collectors.toList()`, `Stream.toList()`, and Java 10 Collectors

Three expressions look very similar yet have **different contracts**:

```java
List<String> a = source.stream()
    .collect(Collectors.toList());                // Java 8+

List<String> b = source.stream()
    .collect(Collectors.toUnmodifiableList());    // Java 10+

List<String> c = source.stream()
    .toList();                                    // Java 16+
```

| Criterion | `Collectors.toList()` | `Collectors.toUnmodifiableList()` | `Stream.toList()` |
| --- | --- | --- | --- |
| Version introduced | Java 8 | **Java 10** | Java 16 |
| Is the result mutable? | **No guarantee** | No | No |
| Encounter order | Yes, if source is ordered | Yes, if source is ordered | Yes, if source is ordered |
| Accepts `null` elements? | No null-rejection constraint like immutable collectors | **No**, throws `NullPointerException` | May contain null; on JDK 17 preserves null |
| Implementation type guarantee | No | No | No |
| Usable directly as a downstream collector? | Yes | Yes | **No**, because it is a terminal method on `Stream` |
| Convenient when only a final list is needed | Yes | Yes | Yes, concise since Java 16 |

### 12.1. Important Example About `null`

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> values = Arrays.asList("A", null, "B");

List<String> fromStreamToList = values.stream().toList();
System.out.println(fromStreamToList.size()); // 3 (JDK 17)
System.out.println(fromStreamToList.get(1) == null); // true

// Throws NullPointerException:
// values.stream().collect(Collectors.toUnmodifiableList());
```

Do not mechanically switch `collect(Collectors.toList())` to `collect(Collectors.toUnmodifiableList())` if the pipeline ever contained valid `null`s. **The data policy has changed.** Nor should you switch `Stream.toList()` to `toUnmodifiableList()` assuming the two methods behave identically in all cases.

### 12.2. What If You Must Guarantee a Mutable List?

Use a collector with a factory creating a concrete collection:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

ArrayList<String> mutable = source.stream()
    .collect(Collectors.toCollection(ArrayList::new));

mutable.add("New"); // Allowed.
```

`toCollection(ArrayList::new)` expresses **explicit intent for a new mutable `ArrayList`**. Do not rely on the incidental implementation of `Collectors.toList()` in a particular JDK.

### 12.3. Why Is There No `toUnmodifiableList` on Primitive Streams?

`IntStream`/`LongStream`/`DoubleStream` have specialized terminal operations like `sum`, `average`, and `toArray`, but do not have the `collect(Collector<T,A,R>)` overload like `Stream<T>`. To use `Collectors.toUnmodifiableList` for integers, you can write:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Collectors;

List<Integer> squares = IntStream.rangeClosed(1, 4)
    .map(n -> n * n)
    .boxed()
    .collect(Collectors.toUnmodifiableList());

System.out.println(squares); // [1, 4, 9, 16]
```

`boxed()` converts `int` values to `Integer`. That introduces boxing work; if you only need an `int[]` or a sum, stay on the primitive stream rather than collecting wrappers into a list.

## 13. Unmodifiable Collectors Inside `groupingBy` and `mapping`

Java 10 collectors can serve as **downstream** collectors inside others. For example, grouping order IDs by region:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<String>> idsByRegion =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.groupingBy(
            UnmodifiableCollectorsDemo.Order::region,
            Collectors.mapping(
                UnmodifiableCollectorsDemo.Order::id,
                Collectors.toUnmodifiableList()
            )
        ));
```

Distinguish **two layers**:

- `idsByRegion` is the **outer map** created by `groupingBy`. The default contract does **not** guarantee the outer map is unmodifiable.
- Each `List<String>` created by `toUnmodifiableList()` is an **unmodifiable list**.

Therefore:

```java
// Inner group contract disallows mutation:
// idsByRegion.get("HN").add("O-9"); // UnsupportedOperationException.

// Do not conclude the outer map is also immutable:
// idsByRegion.clear(); // May be supported, depending on map type.
```

### 13.1. Making the Outer Map Unmodifiable Too

With **Java 10+**, wrap the outer collector using `collectingAndThen`:

```java
Map<String, List<String>> immutableGroups =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.collectingAndThen(
            Collectors.groupingBy(
                UnmodifiableCollectorsDemo.Order::region,
                Collectors.mapping(
                    UnmodifiableCollectorsDemo.Order::id,
                    Collectors.toUnmodifiableList()
                )
            ),
            Map::copyOf
        ));

// immutableGroups.put("HP", List.of()); // UnsupportedOperationException
// immutableGroups.get("HN").add("X");    // UnsupportedOperationException
```

`Map.copyOf` creates an unmodifiable outer map; the map values are already unmodifiable lists. Since the IDs are immutable strings, this is a result safe to publish as a two-layer structural snapshot.

**Note:** `Map.copyOf` does not guarantee key iteration order. If regions must follow appearance order, see the option in the next section.

### 13.2. Combining `filtering` for Empty Groups

With JDK 10, `Collectors.filtering` (available since JDK 9) can be placed inside `groupingBy`:

```java
Map<String, List<String>> paidIdsByRegion =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.groupingBy(
            UnmodifiableCollectorsDemo.Order::region,
            Collectors.filtering(
                UnmodifiableCollectorsDemo.Order::paid,
                Collectors.mapping(
                    UnmodifiableCollectorsDemo.Order::id,
                    Collectors.toUnmodifiableList()
                )
            )
        ));
```

If a region has only unpaid orders, that group still exists with an **empty unmodifiable list**. By contrast, `stream.filter(Order::paid)` **before** `groupingBy` can drop that region key entirely. Unmodifiable collectors do not change the semantics of filter placement.

### 13.3. Grouping into an Unmodifiable `Set`

```java
Map<String, Set<String>> uniqueIdsByRegion =
    UnmodifiableCollectorsDemo.sample().stream()
        .collect(Collectors.groupingBy(
            UnmodifiableCollectorsDemo.Order::region,
            Collectors.mapping(
                UnmodifiableCollectorsDemo.Order::id,
                Collectors.toUnmodifiableSet()
            )
        ));
```

The result deduplicates IDs by `equals` within each group. However, if duplicate IDs are **corrupted data**, `toUnmodifiableSet` can mask the issue because it deduplicates automatically; pick a collector and duplicate-checking policy accordingly.

## 14. Need Deterministic Key Order? Separate Data Collection from Freezing

`toUnmodifiableMap` has no `mapFactory` and does not guarantee insertion order. If a report must show regions in first-encounter order, use `toMap` with `LinkedHashMap::new`, then copy/wrap:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

LinkedHashMap<String, Long> orderedMutable =
    UnmodifiableCollectorsDemo.sample().stream()
        .filter(UnmodifiableCollectorsDemo.Order::paid)
        .collect(Collectors.toMap(
            UnmodifiableCollectorsDemo.Order::region,
            UnmodifiableCollectorsDemo.Order::amountVnd,
            (a, b) -> Math.addExact(a, b),
            LinkedHashMap::new
        ));

Map<String, Long> orderedSnapshot =
    Collections.unmodifiableMap(
        new LinkedHashMap<>(orderedMutable)
    );

System.out.println(List.copyOf(orderedSnapshot.keySet()));
// [HN, HCM, DN]
```

With an ordered sequential stream from a `List`, `LinkedHashMap` preserves first-key insertion order. The **copy** detaches the map from `orderedMutable`, and the wrapper disallows mutating the snapshot map through the published result.

Do not replace the snapshot step with `Map.copyOf(orderedMutable)` if you need an **ordering contract**; it does not guarantee the iteration order of the original map.

### 14.1. Need Keys Sorted Ascending or by Comparator?

`TreeMap` sorts by key:

```java
import java.util.Collections;
import java.util.SortedMap;
import java.util.TreeMap;

TreeMap<String, Long> sorted = new TreeMap<>(orderedMutable);
SortedMap<String, Long> immutableSorted =
    Collections.unmodifiableSortedMap(new TreeMap<>(sorted));

System.out.println(List.copyOf(immutableSorted.keySet()));
// [DN, HCM, HN]
```

For a custom comparator, note that `TreeMap` uses comparison results to determine **key equivalence**. A comparator returning 0 for two distinct keys can cause them to merge into one entry; this is a matter of **key semantics**, not merely sorting.

### 14.2. Sorting by Value: Use a Result List

If you want the highest-revenue region first, `TreeMap` does **not** sort by value. You can build:

```java
List<Map.Entry<String, Long>> ranking =
    orderedSnapshot.entrySet().stream()
        .sorted(
            Map.Entry.<String, Long>comparingByValue()
                .reversed()
                .thenComparing(Map.Entry.comparingByKey())
        )
        .toList(); // Java 16+: unmodifiable list.
```

This entry list is ordered by **descending revenue**, breaking ties by **ascending region name**. `Map.Entry` from the snapshot map cannot mutate via the map; if you want complete separation from views or external schemas, map to a `record RegionTotal(String region, long total)`.

## 15. Migrating Java 8/9 Projects to Java 10 Safely

### 15.1. Projects Still Using `--release 8`

You cannot call `Collectors.toUnmodifiableList()` directly when compiling targeting **Java 8**, even if the development machine runs JDK 17 or newer:

```bash
javac --release 8 LegacyCollectors.java
```

If `LegacyCollectors.java` contains a call to `toUnmodifiableList()`, compilation fails because the API does not exist in Java 8. This cannot be solved by merely changing the source syntax flag while claiming the application is Java 8-compatible.

An approach with a **structurally unmodifiable contract** using APIs already present in Java 8:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LegacyCollectors {
    public static List<String> labels() {
        return Stream.of("A", "B")
            .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                values -> Collections.unmodifiableList(
                    new ArrayList<>(values)
                )
            ));
    }
}
```

This code **does not use `List.of`, `record`, or `Stream.toList`**, so it is compatible with Java 8 syntax and APIs. The two steps of creating a mutable list and a wrapper copy achieve the same goal of **disallowing structural modification of the output**, but **do not automatically reject null elements** like the Java 10 collector. To match the null policy as well, validate or apply `Objects.requireNonNull` before/after collecting.

### 15.2. Equivalents for `Set` and `Map` on Java 8

A `Set` can be frozen after collecting with `LinkedHashSet`, if you want deterministic insertion-order iteration, or another suitable set type:

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Set<String> immutableSet = Stream.of("HN", "HCM", "HN")
    .collect(Collectors.collectingAndThen(
        Collectors.toCollection(LinkedHashSet::new),
        set -> Collections.unmodifiableSet(
            new LinkedHashSet<>(set)
        )
    ));
```

For maps, you can collect into a `LinkedHashMap` and then create a wrapper copy:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> immutableMap = Stream.of("HN", "HCM", "HN")
    .collect(Collectors.collectingAndThen(
        Collectors.toMap(
            value -> value,
            value -> 1,
            Integer::sum,
            LinkedHashMap::new
        ),
        map -> Collections.unmodifiableMap(
            new LinkedHashMap<>(map)
        )
    ));
```

These recipes provide **structurally unmodifiable snapshots**, yet do not make elements immutable and do not automatically match `toUnmodifiable*`'s null policy. When migration requires **matching the exact contract**, write tests for `null`, duplicates, ordering, and mutability, rather than just comparing plain outputs.

### 15.3. Target System Is Java 9

Java 9 has `List.of`, `Set.of`, `Map.of`, and `Stream.ofNullable`, but **does not yet have `Collectors.toUnmodifiable*`** or `List.copyOf`. Do not confuse having unmodifiable literal factories with having unmodifiable collectors.

If the project is permitted to upgrade both **runtime and compile target** to Java 10, the new collectors can be used. When still required to run on Java 8/9, keep the legacy-compatible approach and verify on the target environment.

### 15.4. Behavior Changes Must Be Treated as API Changes

Suppose legacy code has:

```java
List<Customer> result = stream.collect(Collectors.toList());
result.sort(comparator);
```

If you replace the collector with `toUnmodifiableList()`, the `sort` call will fail. Depending on business logic:

1. If you want a **sorted and unmodifiable** result: place `sorted(comparator)` **before** `collect(toUnmodifiableList())`.
2. If the caller needs to modify the list: use `toCollection(ArrayList::new)`.
3. If the original should stay unmodifiable while the caller gets a working copy: the caller can use `new ArrayList<>(immutableResult)`.

Upgrading the JDK is not enough to conclude every collection **should** become unmodifiable; that is a contract choice.

## 16. JUnit 5 Testing: Immutability, Nulls, Duplicates, and Ordering

The tests below reference the `UnmodifiableCollectorsDemo` program in section 8. Assume JUnit Jupiter is in the project and JDK 17+ is used.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class UnmodifiableCollectorsDemoTest {

    @Test
    void listPreservesEncounterOrderAndDuplicates() {
        List<Integer> actual = Stream.of(3, 1, 3, 2)
            .collect(Collectors.toUnmodifiableList());
        assertEquals(List.of(3, 1, 3, 2), actual);
        assertThrows(UnsupportedOperationException.class, () ->
            actual.add(99)
        );
        assertThrows(UnsupportedOperationException.class, () ->
            actual.set(0, 99)
        );
    }

    @Test
    void setRemovesDuplicatesWithoutOrderPromise() {
        Set<String> actual = Stream.of("HN", "DN", "HN")
            .collect(Collectors.toUnmodifiableSet());

        assertEquals(Set.of("HN", "DN"), actual);
        assertThrows(UnsupportedOperationException.class, () ->
            actual.add("HP")
        );
        // Do not assert iteration order on actual.
    }

    @Test
    void uniqueKeyMapCannotBeMutated() {
        var report = UnmodifiableCollectorsDemo.buildReport(
            UnmodifiableCollectorsDemo.sample()
        );

        assertEquals(5, report.ordersById().size());
        assertEquals(100_000L, report.paidTotalsByRegion().get("HCM"));

        assertThrows(UnsupportedOperationException.class, () ->
            report.ordersById().clear()
        );
        assertThrows(UnsupportedOperationException.class, () ->
            report.paidTotalsByRegion().put("HP", 10L)
        );
    }

    @Test
    void toUnmodifiableListAndSetRejectNull() {
        List<String> nullable = Arrays.asList("A", null, "B");

        assertThrows(NullPointerException.class, () ->
            nullable.stream().collect(
                Collectors.toUnmodifiableList()
            )
        );
        assertThrows(NullPointerException.class, () ->
            nullable.stream().collect(
                Collectors.toUnmodifiableSet()
            )
        );
    }

    @Test
    void unmodifiableMapRejectsNullKeyAndNullValue() {
        record Row(String key, String value) {}

        List<Row> nullKey = List.of(new Row(null, "x"));
        List<Row> nullValue = List.of(new Row("a", null));

        assertThrows(NullPointerException.class, () ->
            nullKey.stream().collect(
                Collectors.toUnmodifiableMap(Row::key, Row::value)
            )
        );
        assertThrows(NullPointerException.class, () ->
            nullValue.stream().collect(
                Collectors.toUnmodifiableMap(Row::key, Row::value)
            )
        );
    }

    @Test
    void duplicateMapKeyFailsWithoutMergeFunction() {
        record Row(String key, int value) {}
        List<Row> rows = List.of(
            new Row("A", 1),
            new Row("A", 2)
        );

        assertThrows(IllegalStateException.class, () ->
            rows.stream().collect(
                Collectors.toUnmodifiableMap(
                    Row::key, Row::value
                )
            )
        );
    }

    @Test
    void duplicateMapKeyCanBeMergedExplicitly() {
        record Row(String key, long value) {}
        List<Row> rows = List.of(
            new Row("A", 1L),
            new Row("A", 2L),
            new Row("B", 4L)
        );

        Map<String, Long> actual = rows.stream()
            .collect(Collectors.toUnmodifiableMap(
                Row::key, Row::value, Math::addExact
            ));

        assertEquals(Map.of("A", 3L, "B", 4L), actual);
    }

    @Test
    void collectedSnapshotDoesNotTrackSourceStructure() {
        ArrayList<String> source = new ArrayList<>(
            List.of("A", "B")
        );

        List<String> immutable = source.stream()
            .collect(Collectors.toUnmodifiableList());

        source.add("C");
        assertEquals(List.of("A", "B"), immutable);
    }

    @Test
    void unmodifiableCollectionDoesNotFreezeMutableElements() {
        StringBuilder mutable = new StringBuilder("A");
        List<StringBuilder> result = Stream.of(mutable)
            .collect(Collectors.toUnmodifiableList());

        mutable.append("B");
        assertEquals("AB", result.get(0).toString());
        assertThrows(UnsupportedOperationException.class, () ->
            result.remove(0)
        );
    }

    @Test
    void streamToListAndCollectorDifferOnNullInJdk17() {
        List<String> nullable = Arrays.asList("A", null);

        List<String> result = nullable.stream().toList();
        assertEquals(2, result.size());
        assertTrue(result.get(1) == null);
        assertThrows(UnsupportedOperationException.class, () ->
            result.add("B")
        );
    }

    @Test
    void emptySourceReturnsEmptyUnmodifiableResults() {
        List<String> values = Stream.<String>empty()
            .collect(Collectors.toUnmodifiableList());
        Set<String> unique = Stream.<String>empty()
            .collect(Collectors.toUnmodifiableSet());
        Map<String, String> mappings = Stream.<String>empty()
            .collect(Collectors.toUnmodifiableMap(
                value -> value,
                value -> value
            ));

        assertTrue(values.isEmpty());
        assertTrue(unique.isEmpty());
        assertTrue(mappings.isEmpty());

        assertThrows(UnsupportedOperationException.class, () ->
            values.add("A")
        );
    }
}
```

**How to read the tests:** do not compare implementation class names or result object identity, because the JDK does not guarantee those. For an ordered `List`, compare the entire list. For `Set` and `Map`, compare the set of elements or key-value pairs without enforcing iteration order.

### 16.1. Additional Test Cases Recommended in Real Projects

- Input elements whose `equals/hashCode` rely on mutable fields.
- Two equal objects with different references in `toUnmodifiableSet`.
- `toUnmodifiableMap` with identifiers differing in case; decide whether to normalize keys.
- Merge functions with side effects or non-associative operations; check correctness on parallel streams.
- `long` values near limits and `Math.addExact` errors.
- Nested `groupingBy`: mutable outer map, unmodifiable inner lists; after `Map.copyOf`, both layers are unmodifiable.
- Ordered snapshots via `Collections.unmodifiableMap(new LinkedHashMap<>(...))`.
- Sources filtered down to empty, initially empty, or containing null elements from external data.

## 17. Parallel Streams, Encounter Order, and What Must Not Be Inferred

Unmodifiable collectors are **not the same** as `CONCURRENT` collectors. They can be used in a parallel stream because the Stream framework creates and merges accumulation states according to contract; there is no need to mutate a shared `ArrayList` from multiple threads:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Collectors;

List<Integer> values = IntStream.range(0, 100_000)
    .boxed().parallel()
    .collect(Collectors.toUnmodifiableList());

System.out.println(values.size());  // 100000
System.out.println(values.get(0)); // 0, because the source has encounter order
```

If the pipeline is ordered, `toUnmodifiableList` must preserve encounter order in its contents; **the order in which workers call the mapper** may differ. Do not use logs from `peek`, thread timestamps, or shared variables in mappers to infer result positions.

### 17.1. `Set` and `Map` Do Not Guarantee Order Even When the Source Is a `List`

`toUnmodifiableSet` is an unordered collector, and `toUnmodifiableMap` does not guarantee key order. Even when starting from an ordered `List`, these two results carry no promise of "preserving source order".

If an **ordered** report of key-value pairs is required, choose a collector with a `mapFactory` and an appropriate snapshot, or build a `sorted` `List<record>`.

### 17.2. Do Not Mutate a Mutable Source Underneath the Pipeline

`parallelStream()` does not permit arbitrarily mutating the source collection during traversal. `toUnmodifiableList` at the end makes the result unmodifiable, but **does not protect the source collection from concurrent modification**.

Similarly, if `map` returns a mutable object modified concurrently by multiple threads, an unmodifiable final list does not fix races inside each object.

### 17.3. `groupingByConcurrent` with an Unmodifiable Downstream

You can use:

```java
var groups = UnmodifiableCollectorsDemo.sample()
    .parallelStream()
    .collect(Collectors.groupingByConcurrent(
        UnmodifiableCollectorsDemo.Order::region,
        Collectors.mapping(
            UnmodifiableCollectorsDemo.Order::id,
            Collectors.toUnmodifiableList()
        )
    ));
```

The outer collector returns a **mutable `ConcurrentMap`**; each inner group is an **unmodifiable `List`** after the collector finishes. The outer collector contract includes `UNORDERED`, so do not assume the grouped lists preserve element encounter order.

Choose this when you want concurrent grouping without requiring inner list order, not merely to "go faster"; test and benchmark with realistic key distributions.

## 18. Performance, Resources, and Limits

### 18.1. Unmodifiable Does Not Mean Zero Allocation

A collector may still need temporary accumulation containers to hold elements, merge branches, and produce the final result. `toUnmodifiableList` makes no "zero-copy" or concrete-class promises. `List.copyOf` may reuse an already unmodifiable instance in some cases, but never write logic that depends on that optimization.

On large datasets, speed/memory differences among `Collectors.toList`, `toUnmodifiableList`, and `Stream.toList` should be evaluated using reliable benchmarks (such as JMH), not inferred from method names.

### 18.2. `List` Retains All Elements, `Set` Checks Duplicates, `Map` Needs Keys

| Collector | Data State Retained | Notable Cost |
| --- | --- | --- |
| `toUnmodifiableList` | All elements after pipeline | Memory proportional to element count |
| `toUnmodifiableSet` | Distinct values | `equals/hashCode` and storing value set |
| `toUnmodifiableMap` | Key-value mappings | Key mapping, duplicate-key check or merge |

If you only need **counts, sums, or statistics**, prefer `count()`, `sum()`, `counting()`, `summingLong()`, or `summarizingLong()` rather than materializing millions of elements into an immutable list.

### 18.3. Freezing the Result Alone Does Not Close I/O Sources

A source from `Files.lines` must be closed using `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> nonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines
            .map(String::strip)
            .filter(line -> !line.isEmpty())
            .collect(Collectors.toUnmodifiableList());
    }
}
```

`collect` is a terminal operation **but does not automatically close the source stream**. If a read error occurs during consumption, `try-with-resources` still ensures resource closing. An unmodifiable result only applies to the **final collection**, not the source's I/O lifecycle.

### 18.4. No Deep Immutability or Element Thread-Safety Guarantee

After safely publishing an unmodifiable result, multiple threads can read the **collection structure** without structural modification via the API. However, if mutable elements or values are still updated elsewhere, they can exhibit data races and visibility issues; immutable objects or proper synchronization and safe publication are required.

Do not treat `unmodifiable` as a replacement for `synchronized`, `ConcurrentHashMap`, or immutable data design.

## 19. Common Mistakes When Upgrading JDK Versions

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Using `Collectors.toUnmodifiableList` with `--release 8` | Fails to compile | Use older APIs or raise target to Java 10 |
| Calling `Stream.toList()` on Java 10 | Fails to compile | Use `collect(toUnmodifiableList())` |
| Assuming `Collectors.toList()` is always mutable | Depends on implementation | Use `toCollection(ArrayList::new)` |
| Assuming `Collectors.toList()` is always unmodifiable | Not guaranteed | Use `toUnmodifiableList` or `Stream.toList` |
| Switching collectors when data has `null` | `NullPointerException` | Define null policy |
| Using `toUnmodifiableMap(key,value)` when duplicate keys are valid | `IllegalStateException` | Add an appropriate merge function |
| Using merge to "pick a random value" | May hide corrupted data | Define priority or throw an error |
| Testing order of immutable `Set`/`Map` | Test expects uncommitted behavior | Compare contents, sort if needed |
| Using `Map.copyOf(LinkedHashMap)` and expecting insertion order | Not guaranteed | Snapshot/wrap `LinkedHashMap` |
| Wrapping `Collections.unmodifiableList(mutable)` then mutating `mutable` | View changes with original | Copy container before wrapping |
| Thinking an unmodifiable collection makes elements immutable | Inner values can still change | Defensive copy / value objects |
| Replacing `toList()` with `toUnmodifiableList()` without testing | Null/mutability differences | Write compatibility tests |
| Using new collectors and expecting the whole pipeline to be "side-effect free" | Source mappers may still mutate state | Keep pipeline stateless and non-interfering |
| Using `collect` with files and forgetting to close | Resource leak | `try-with-resources` |

## 20. Practice Exercises

### Exercise 1 — Choosing Collectors by Contract

Given a `Stream<String>` with values `["HN", "HCM", "HN", "DN"]`. Write three pipelines:

1. Preserve order and both `"HN"` occurrences in an unmodifiable `List`.
2. Obtain a `Set` of distinct regions, without relying on iteration order.
3. Build a map counting occurrences per region using three-argument `toUnmodifiableMap`.

Write tests for `UnsupportedOperationException` on all three results.

### Exercise 2 — Comparing Java 10 with Java 16

Create a `List<String>` containing a `null` element via `Arrays.asList("A", null)`. On JDK 17:

- Observe `stream().toList()`.
- Observe `stream().collect(Collectors.toUnmodifiableList())`.
- Explain why replacing one API with the other can alter error behavior.

Do not use `List.of("A", null)`, because the error will occur when constructing the source.

### Exercise 3 — Detecting Duplicate IDs Before Publishing Reports

Create two `Order` instances with the same `id`. Collect `Map<String,Order>` using `toUnmodifiableMap(Order::id, identity())` and verify `IllegalStateException`. Then consider another business rule: on duplicate ID, the newest record by `Instant` wins. Propose a merge function with **explicit priority ordering**, not depending on which element the mapper sees first.

### Exercise 4 — Snapshot Preserving Insertion Order

From `Stream<Sale>`, sum amounts by region using `toMap` with `LinkedHashMap::new`. Create an unmodifiable snapshot **preserving first-seen region order**, then mutate the original map and prove the snapshot does not change. Explain why `Map.copyOf` does not satisfy this ordering contract.

### Exercise 5 — Two-Layer Immutability

Use `groupingBy(Order::region, mapping(Order::id, toUnmodifiableList()))`. Prove the outer map is not guaranteed to be unmodifiable. Then add `collectingAndThen(..., Map::copyOf)`, and test that both the outer map and inner lists are unmodifiable.

### Exercise 6 — Java 8 Compatibility

Write a `LegacyReport` class using only Java 8 syntax that builds an unmodifiable list using `Collectors.collectingAndThen`, `ArrayList`, and `Collections.unmodifiableList`. Verify with `javac --release 8` when a supporting JDK is available. Add a `null`-rejection step to match Java 10 `toUnmodifiableList`'s policy.

### Exercise 7 — Deep Immutability

Create a `MutableUser` whose `name` can change, collect via `toUnmodifiableList`, and rename through the original reference. Explain why the list still reflects the new name. Replace with `record UserView(String name)` created via `map` before collecting, then try mutating the original object to prove the value snapshot is unaffected.

### Exercise 8 — Parallelism and Correctness

Generate 100,000 unique IDs, run `parallelStream().collect(toUnmodifiableList())`, and compare against the original sequence. Next collect `Set` and `Map` from the IDs; compare **contents**, without asserting iteration order. Explain why correctness does not mean parallel execution is guaranteed to be faster.

### Exercise 9 — Data from Files

Read lines from `Files.lines(path)`, remove blank lines, and collect into an unmodifiable `List`. Use `try-with-resources`, distinguish file read errors from empty files, and assess out-of-memory risk on very large files.

## 21. Final Decision Table

| What Do You Need? | Typically Suitable Solution |
| --- | --- |
| A list from a stream, unmodifiable and **rejecting null** | `Collectors.toUnmodifiableList()` (Java 10+) |
| A set of distinct values, unmodifiable | `Collectors.toUnmodifiableSet()` (Java 10+) |
| A unique-key map, duplicates must error | `Collectors.toUnmodifiableMap(key,value)` |
| A map allowing duplicate keys, merged by rule | `Collectors.toUnmodifiableMap(key,value,merge)` |
| An unmodifiable list from a stream on JDK 16+ | `Stream.toList()` |
| A list guaranteed to be mutable | `collect(toCollection(ArrayList::new))` |
| An unmodifiable copy from an existing collection | `List.copyOf` / `Set.copyOf` / `Map.copyOf` (Java 10+) |
| An unmodifiable **view** of an existing collection | `Collections.unmodifiableList/Set/Map` |
| Snapshot preserving map insertion order | `Collections.unmodifiableMap(new LinkedHashMap<>(source))` |
| Snapshot with ascending sorted keys | `Collections.unmodifiableSortedMap(new TreeMap<>(source))` |
| Immutability of both grouping map and inner lists | `collectingAndThen(groupingBy(..., mapping(..., toUnmodifiableList())), Map::copyOf)` |
| Inner elements are mutable | Map elements to immutable DTOs, defensive copy as needed |
| Running on Java 8/9 | `collectingAndThen` with container copy and `Collections.unmodifiable*`, extra null/duplicate tests |
| Need memory control instead of keeping all records | Use statistical collectors like `counting`/`summingLong` |

## 22. Summary

**`Collectors.toUnmodifiableList`, `toUnmodifiableSet`, and `toUnmodifiableMap` have existed since Java 10** to turn Java Stream API outputs into structurally unmodifiable collections. They have clear data policies: **they reject `null`**; `Set` deduplicates by `equals`; `Map` rejects duplicate keys unless a `mergeFunction` is supplied; only `List` promises to preserve encounter order when the source is ordered.

The distinctions between **snapshot** and **view**, between **unmodifiable collection** and **deep immutability**, and between **Java 10 collectors** and `Stream.toList()` from Java 16 directly impact JDK upgrades and API design. Define your data contract upfront—nulls, duplicates, ordering, mutability, and performance requirements—then choose the collector and write matching tests. That way, `filter`, `map`, `reduce`, and `collect` pipelines stay not only concise, but also produce results with stable semantics as applications evolve across JDK versions.