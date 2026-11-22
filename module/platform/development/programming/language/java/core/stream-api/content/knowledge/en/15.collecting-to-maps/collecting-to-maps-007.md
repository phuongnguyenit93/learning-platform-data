# Creating an Unmodifiable Map with `toUnmodifiableMap`

In the **Java Stream API**, we can use a lazy pipeline of `filter`, `map`, and other intermediate operations to prepare data, then use `collect` to produce a result. When the result is a key-based lookup table, `Collectors.toMap` is a familiar choice. However, if the lookup table is finalized and **adding, removing, or replacing mappings must be forbidden**, `Collectors.toUnmodifiableMap` (Java 10+) expresses that requirement directly.

This lesson belongs to the **Collecting to Maps** chapter: learn how to build an unmodifiable `Map<K,V>`, handle duplicate keys, forbid `null` values, distinguish unmodifiability from deep immutability, and choose solutions when ordering or parallel processing is needed.

## 1. What Does `toUnmodifiableMap` Do?

`Collectors.toUnmodifiableMap` is a **collector factory**, not an intermediate operation. It is passed to the terminal operation `Stream.collect(...)`; collecting triggers stream traversal and produces a `Map` that forbids structural modifications through the returned map's API.

Simple example from a list of words:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> lengths = Stream.of("Java", "Stream", "API")
    .collect(Collectors.toUnmodifiableMap(
        word -> word,
        String::length
    ));

System.out.println(lengths.get("Java"));   // 4
System.out.println(lengths.get("Stream")); // 6
System.out.println(lengths.size());        // 3

// Invalid for this map:
// lengths.put("New", 3);  // UnsupportedOperationException
```

Here, `word -> word` is the **key** mapper, and `String::length` is the **value** mapper. Key/value pairs are produced when the stream is collected. Once obtained, you can still call `get`, `containsKey`, `entrySet`, `size`, and normal read operations.

### Two important overloads

| Call | Meaning | On duplicate keys |
| --- | --- | --- |
| `toUnmodifiableMap(keyMapper, valueMapper)` | Creates a map when each element produces a unique key | Throws `IllegalStateException` |
| `toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` | Creates a map and defines how to merge values with the same key | Invokes `mergeFunction` to resolve collisions |

Both overloads have been in `java.util.stream.Collectors` since **Java 10**. The mappers belong to `java.util.function.Function`; the merge function is a `BinaryOperator<U>`, accepting two values of type `U` and returning one value of the same type.

At the type level, think of them as:

```java
<T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper
);

<T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
);
```

Do not rely on a specific implementation class (such as `HashMap` or `LinkedHashMap`): the contract returns an **unmodifiable `Map`**, without promising storage structure or iteration order.

## 2. Duplicate Keys: Understand the Exception Before Implementing

Keys in a `Map` must be unique under `equals`/`hashCode`. A source with distinct elements can still produce **the same key** after `keyMapper`.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Both Java and JUnit produce the key "J".
Map<String, Integer> broken = Stream.of("Java", "JUnit")
    .collect(Collectors.toUnmodifiableMap(
        word -> word.substring(0, 1),
        String::length
    ));

// IllegalStateException because key "J" appears twice.
```

This is a **collector contract** error, not a phenomenon that happens only in parallel execution. Even when two elements produce the same key **and the same value**, the two-argument overload still rejects duplicate keys.

If duplicate keys are valid in the problem domain, you must specify the merge policy explicitly:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> totalLengthByInitial =
    Stream.of("Java", "JUnit", "Stream")
        .collect(Collectors.toUnmodifiableMap(
            word -> word.substring(0, 1),
            String::length,
            Integer::sum
        ));

System.out.println(totalLengthByInitial.get("J")); // 9 = 4 + 5
System.out.println(totalLengthByInitial.get("S")); // 6
```

`Integer::sum` is a `BinaryOperator<Integer>`: two lengths sharing a key are summed into one value. A "sum" policy does not fit every dataset; depending on the goal, you may pick the maximum, minimum, or combine contents by another rule.

### Example picking the maximum value per key

```java
import java.util.Comparator;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Character, String> longestByInitial =
    Stream.of("An", "Anh", "Binh", "Bao")
        .collect(Collectors.toUnmodifiableMap(
            word -> word.charAt(0),
            word -> word,
            BinaryOperator.maxBy(
                Comparator.comparingInt(String::length)
            )
        ));

System.out.println(longestByInitial.get('A')); // Anh
System.out.println(longestByInitial.get('B')); // Binh
```

In this example, `maxBy` compares length only; if two names have equal length, the comparator treats them as tied. When you **need a unique, deterministic result** even on ties, add a secondary criterion such as alphabetical string comparison.

### When you want to keep *all* values per key

If the requirement is to store a list of items for each group, `toUnmodifiableMap` with a merge picking **one** value does not reflect the business domain. In that case, `groupingBy` is typically used:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Character, List<String>> byInitial = Stream.of(
        "An", "Anh", "Binh", "Bao"
    )
    .collect(Collectors.groupingBy(word -> word.charAt(0)));

System.out.println(byInitial.get('A')); // [An, Anh]
```

`groupingBy` here merely illustrates the semantic difference: **the default result is not guaranteed to be an unmodifiable map or list**. If you still need an unmodifiable result at every level, design an appropriate finishing step, avoiding confusing "cannot modify the outer map" with "cannot modify the inner list".

## 3. Null Is Rejected

`toUnmodifiableMap` **does not allow `null` keys or values**. If `keyMapper` or `valueMapper` returns `null`, collection throws `NullPointerException`.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// WRONG example: valueMapper returns null.
Map<String, String> invalid = Stream.of("A", "B")
    .collect(Collectors.toUnmodifiableMap(
        key -> key,
        key -> key.equals("B") ? null : "active"
    ));

// NullPointerException
```

If the source data contains `null` elements, that can also cause a mapper to throw `NullPointerException` before the collector builds the map. Handling must follow business requirements: **filter**, **substitute a meaningful value**, or **report an error**.

```java
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

Map<String, Integer> lengths = Arrays.asList("Java", null, "API")
    .stream()
    .filter(Objects::nonNull)
    .collect(Collectors.toUnmodifiableMap(
        word -> word,
        String::length
    ));

System.out.println(lengths.size()); // 2
```

Do not automatically turn every missing value into an empty string or 0 if those values have real meaning in the system. For financial data, input errors or missing identifiers usually need to be recorded and handled transparently.

## 4. Unmodifiability Differs from Deep Immutability

"Unmodifiable Map" means callers **cannot modify mappings through the returned `Map` object**. It does not mean the entire object graph is deep-copied or that objects used as keys/values become immutable.

### Which operations are blocked?

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Integer, String> names = Stream.of("An", "Binh")
    .collect(Collectors.toUnmodifiableMap(
        String::length, word -> word
    ));

// Invalid:
// names.put(3, "New");
// names.remove(2);
// names.clear();
// names.replace(2, "Other");
```

Structural map-modifying operations are blocked by contract; mutating methods can throw `UnsupportedOperationException`. For default methods like `compute`, `merge`, or `replaceAll`, do not use them to update this map. Do not rely on whether an operation changes data before throwing: the API promises the result is **unmodifiable**.

### Mutable values inside can still change

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> roles = new ArrayList<>(Arrays.asList("READ"));

Map<String, List<String>> permissions = Stream.of("user")
    .collect(Collectors.toUnmodifiableMap(
        key -> key,
        key -> roles
    ));

// permissions.put("admin", roles); // Disallowed
permissions.get("user").add("WRITE"); // Allowed: mutates the mutable List itself

System.out.println(permissions.get("user")); // [READ, WRITE]
```

Thus, the `Map` itself cannot have key/value pairs added or replaced, yet **the internal state of the `roles` object** can still change. This is a map that is unmodifiable at the mapping level, **not** a deeply immutable snapshot.

If you want the value lists to also be unmodifiable through their API, you can make a copy:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> roles = new ArrayList<>(Arrays.asList("READ"));
Map<String, List<String>> permissions = Stream.of("user")
    .collect(Collectors.toUnmodifiableMap(
        key -> key,
        key -> List.copyOf(roles)
    ));

roles.add("WRITE");
System.out.println(permissions.get("user")); // [READ]
```

`List.copyOf` (since Java 10) rejects `null` elements and creates an unmodifiable list containing the elements at copy time. **Elements inside the list remain references**; if they themselves are mutable, a deep-copy strategy or immutable value types are needed.

### Mutable keys are even more dangerous

`Map` keys must keep stable `equals`/`hashCode` while inside the map. If you use an object with a field participating in `hashCode` and mutate that field after collecting, lookups may fail to work as expected. `toUnmodifiableMap` **does not automatically make keys immutable**. Prefer `String`, `Integer`, enums, or immutable key types with clear equality semantics.

## 5. Differences Among `toMap`, `toUnmodifiableMap`, `Map.copyOf`, and Unmodifiable Views

Several map-creating APIs look similar but have different contracts:

| API | Purpose | Can output be modified via returned Map? | Scenario |
| --- | --- | --- | --- |
| `Collectors.toMap(k, v)` | Collects into a map; no concrete implementation class promised | No unmodifiability guarantee | Need a map for further processing; behavior follows `toMap` contract. |
| `Collectors.toMap(k, v, merge)` | Handles duplicate keys during collection | No unmodifiability guarantee | Need a merge policy and further map operations. |
| `Collectors.toUnmodifiableMap(k, v)` | Collects directly into an unmodifiable map | **No** | Keys expected to be unique. |
| `Collectors.toUnmodifiableMap(k, v, merge)` | Collects into an unmodifiable map with duplicate-key merging | **No** | Need to merge values before finalizing the result. |
| `Map.copyOf(existing)` | Creates an unmodifiable map from an existing map | **No** | Already have a map and want a snapshot of mappings at creation time. |
| `Collections.unmodifiableMap(existing)` | Creates an unmodifiable **view** of an existing map | **Not through the view** | Need to protect an API surface, though the backing map may still change. |

Example distinguishing a **view** from a **mapping snapshot**:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> source = new HashMap<>();
source.put("A", 1);

Map<String, Integer> view = Collections.unmodifiableMap(source);
Map<String, Integer> snapshot = Map.copyOf(source);

source.put("B", 2);

System.out.println(view.containsKey("B"));     // true
System.out.println(snapshot.containsKey("B")); // false
```

`Collections.unmodifiableMap(source)` reflects changes to the **backing map** if another reference still mutates it. `Map.copyOf(source)` does not reflect mapping edits made after creation, though it remains a **shallow snapshot** with respect to key/value objects. `toUnmodifiableMap` produces the result directly from the pipeline without requiring callers to build a mutable map and wrap it in a separate step.

Note: `Collectors.toMap` does not promise the implementation class or mutability of the returned map; therefore do not use it as a guarantee of `HashMap` or mutability across all implementations. If you need to specify the container type, `toMap` has an overload accepting `mapFactory`.

## 6. Iteration Order: Do Not Infer from Source Order

`toUnmodifiableMap` **does not guarantee entry iteration order**. Even if the source is a `List` with encounter order or the pipeline called `sorted()`, the print order of `keySet()`, `values()`, or `entrySet()` on the resulting map is not a contract you may rely on.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> result = Stream.of("A", "B", "C")
    .collect(Collectors.toUnmodifiableMap(
        s -> s,
        String::length
    ));

// Only check the mapping, not entrySet() print order.
System.out.println(result.get("B")); // 1
```

If the requirement is an *insertion-ordered Map* and consumers must not modify it, you can use `LinkedHashMap` with the four-argument `toMap` overload, then create an unmodifiable view **over a private new map**:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> orderedView = Stream.of("A", "B", "C")
    .collect(Collectors.collectingAndThen(
        Collectors.toMap(
            Function.identity(),
            String::length,
            (left, right) -> left,
            LinkedHashMap::new
        ),
        Collections::unmodifiableMap
    ));

System.out.println(orderedView.keySet()); // [A, B, C]
```

In this example, `LinkedHashMap` iterates in insertion order and the stream has an encounter order. Because the backing map is freshly created inside the collector and never exposed externally, callers only receive an unmodifiable view. If later code exposes the backing map reference or mutable values inside, revisit the desired immutability contract.

Do not use `Map.copyOf(orderedMap)` if **preserving iteration order** is required: `Map.copyOf` makes no promise to preserve insertion order.

## 7. Parallel Execution and Merge Functions

`toUnmodifiableMap` works on parallel streams. The framework can collect partial results and merge them into the final map; do not assume mapper execution order or the number of merge-function calls is fixed.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Integer, Integer> sumByRemainder = IntStream.rangeClosed(1, 1000)
    .parallel()
    .boxed()
    .collect(Collectors.toUnmodifiableMap(
        n -> n % 10,
        n -> n,
        Integer::sum
    ));

System.out.println(sumByRemainder.size()); // 10
System.out.println(
    sumByRemainder.values().stream().mapToInt(Integer::intValue).sum()
); // 500500
```

Each element is placed into a group based on its remainder; `Integer::sum` combines values sharing a key. The sum in this example fits within `int` range, so addition does not overflow.

Principles to maintain when using the merge-function overload:

1. **Choose a merge rule based on business logic**, such as summing quantities, picking the record with the greater timestamp, or detecting conflicts. Do not write `(a, b) -> a` merely to suppress an exception if the domain has not defined which side to keep.
2. **Prefer associative merge operations**: parallel branches may combine in varying groupings. Non-overflowing integer addition is associative; subtraction is unsuitable.
3. **Avoid shared state and side effects** in mappers and mergers. Do not write into an external `HashMap` from multiple threads and expect the collector to make that map thread-safe.
4. **Do not assume iteration order of the result map**. If order is needed, choose another design per Section 6.
5. **Evaluate performance via measurement**. Merging maps across branches and building the final map has overhead; `parallel()` is not guaranteed to be faster than sequential execution.

In particular, using a non-associative merger or making decisions based on external state can cause results to depend on how the stream is split and merged. Use pure functions and define clear rules when two records share a key.

## 8. Real-World Example: Building a Read-Only Lookup Price Catalog

Suppose an application receives a list of products, each with a `sku` code and price in the smallest integer currency unit. After validating data, the application needs a `sku -> price` map for lookups, and must prevent other code from modifying the price table.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class PriceCatalog {
    static final class Product {
        final String sku;
        final long priceInMinorUnits;

        Product(String sku, long priceInMinorUnits) {
            this.sku = sku;
            this.priceInMinorUnits = priceInMinorUnits;
        }
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
            new Product("BOOK-01", 25000L),
            new Product("PEN-02", 8000L),
            new Product("BAG-03", 90000L)
        );

        Map<String, Long> priceBySku = products.stream()
            .collect(Collectors.toUnmodifiableMap(
                product -> product.sku,
                product -> product.priceInMinorUnits
            ));

        System.out.println(priceBySku.get("PEN-02")); // 8000
        // priceBySku.put("PEN-02", 0L); // UnsupportedOperationException
    }
}
```

In this design, `String` and `Long` are immutable value types, so both the **map surface** and the lookup values avoid the mutable-object trap from Section 4. If two products share a `sku`, the pipeline fails instead of silently picking a price: this is appropriate when SKUs are expected to be unique.

If the application allows multiple updates for the same SKU, define the policy before switching to the merge overload. For example: pick the latest update **by real timestamp**, rather than arbitrarily picking the last element seen in a pipeline that may execute in parallel.

## 9. Common Errors

| Error | Consequence | Resolution |
| --- | --- | --- |
| Duplicate keys exist yet two-argument overload is called | Throws `IllegalStateException`. | Ensure unique keys or use the three-argument overload with a business-accurate merger. |
| `keyMapper` or `valueMapper` returns `null` | Throws `NullPointerException`. | Validate, filter, or choose an explicit replacement policy. |
| Calling `put`, `remove`, `clear` on the result map | Modification rejected. | Choose `toMap`/a mutable map when updates are genuinely required. |
| Thinking `toUnmodifiableMap` deep-copies objects | Mutable `List` or bean inside a value can still change state. | Use immutable types or copy data at the element level. |
| Writing tests relying on `entrySet()` order | Result map order is not guaranteed. | Compare mappings; use `LinkedHashMap` if insertion order is needed. |
| Merger produces results depending on thread order or shared variables | Parallel results become unpredictable. | Use pure, associative functions and a deterministic merge policy. |
| Using mutable keys whose `hashCode` changes | Lookups can fail or keys become unfindable. | Choose immutable key types. |
| Collecting an entire infinite stream into a map | Never finishes; may exhaust resources. | Limit the source or use a finite aggregation. |

## 10. Empty Data, Infinite Streams, and Pipeline Lifecycle

For an empty stream, `toUnmodifiableMap` produces an **empty unmodifiable map**:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Integer> empty = Stream.<String>empty()
    .collect(Collectors.toUnmodifiableMap(
        text -> text,
        String::length
    ));

System.out.println(empty.isEmpty()); // true
```

Conversely, with an unbounded source such as `Stream.generate`, the terminal operation `collect` generally cannot finish without bounding the element count:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Integer, Integer> firstHundred = IntStream.range(0, 100)
    .boxed()
    .collect(Collectors.toUnmodifiableMap(
        n -> n,
        n -> n * n
    ));

System.out.println(firstHundred.size()); // 100
```

When an infinite sequence must be generated, bound it with `limit(n)` before `collect`, or use a finite source directly such as `IntStream.range` in the example. Do not rely on a small number of distinct keys to conclude a pipeline from an infinite source will stop: even if subsequent elements only update old keys, the collector still has to read the whole source to know the final result.

After `collect`, **the stream object is consumed** and cannot be used for another terminal operation on the same stream. If the source is backed by a resource like `Files.lines`, use `try-with-resources` to close the stream; returning a map from `collect` does not automatically close external resources.

## 11. Collector Selection Checklist

When converting data into a map, check:

1. **Does the map need modifications after creation?** If not, prefer `toUnmodifiableMap` to express the output data contract. If additions, deletions, or updates are required, choose a mutable map with an appropriate collector.
2. **Are keys unique?** If guaranteed unique, use the two-argument overload. If duplicates may occur, define a merger or switch to `groupingBy` when all elements in a group must be retained.
3. **Can any field be `null`?** `toUnmodifiableMap` rejects null keys and values; define a cleaning or error-reporting policy.
4. **Are values and keys mutable?** A map is unmodifiable at the mapping level; deep immutability requires controlling nested objects.
5. **Is iteration order required?** `toUnmodifiableMap` promises no order; pick `LinkedHashMap` and create an appropriate view if ordering is required.
6. **Will it run in parallel?** The merger should be associative, independent of shared state, and independent of thread scheduling.
7. **Is the source finite and resource-backed?** Limit data before collecting and properly close I/O sources according to their lifecycle.

### Practice Exercises

**Exercise 1 — Unique keys.** From `Stream.of("Java", "Stream", "API")`, build a `Map<String, Integer>` using `toUnmodifiableMap`. Try calling `put` and explain the exception. Confirm `get("Stream") == 6`.

**Exercise 2 — Duplicate keys.** From `Stream.of("Java", "JUnit", "Stream")`, map the key to the first character. Predict the failure with the two-argument overload. Rewrite using the three-argument overload and `Integer::sum`, then explain why `get("J") == 9`.

**Exercise 3 — Deep immutability.** Use a mutable `List<String>` as a value in an unmodifiable map and try `map.get(key).add(...)`. Replace the value with `List.copyOf` and explain the new level of protection achieved.

**Exercise 4 — Comparing view and snapshot.** Create a backing `HashMap`, derive `Collections.unmodifiableMap` and `Map.copyOf`, then add an entry to the backing map. Which map sees the new mapping? Why?

**Exercise 5 — Ordered result.** From a source with encounter order, create a `LinkedHashMap` via the four-argument `toMap` overload and wrap it with `Collections.unmodifiableMap`. Compare iteration order with `toUnmodifiableMap` and explain each type's ordering contract.

**Takeaway:** `Collectors.toUnmodifiableMap` locks down a lookup table so it cannot be modified **through the Map API**, supports duplicate-key merge policies via its three-argument overload, and rejects `null` keys/values. Unmodifiability does not mean deep copying or preserving insertion order. Choose the collector based on key, value, mutability, ordering, and parallel-processing requirements, and validate inputs before collecting.
