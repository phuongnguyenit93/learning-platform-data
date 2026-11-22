# `Collectors.toUnmodifiableMap()` and `null` Data Requirements in Java

## 1. When Do You Need an Unmodifiable Map?

In the Stream API, `collect` is a terminal operation (*terminal operation*) that transforms Stream elements into an aggregated result. A common need is to create a `Map<K,V>`, where each element provides a key and a value. If the resulting Map **must not allow adding, removing, or modifying key-value mappings**, Java provides a dedicated collector:

~~~java
Collectors.toUnmodifiableMap(keyMapper, valueMapper)
~~~

For example, given a list of items:

~~~java
record Item(String code, String name, int price) {}

List<Item> items = List.of(
        new Item("P01", "Book", 120),
        new Item("P02", "Pen", 15));

Map<String, Item> byCode = items.stream()
        .collect(Collectors.toUnmodifiableMap(
                Item::code,
                Function.identity()));

System.out.println(byCode.get("P01").name()); // Book
~~~

In this example:

- `Item::code` turns each `Item` into a `String` key.
- `Function.identity()` keeps the `Item` itself as the Map value.
- `toUnmodifiableMap` collects the key/value pairs and returns an **unmodifiable Map**.
- If `keyMapper` or `valueMapper` returns `null`, the collector rejects it and throws `NullPointerException`.
- If two elements produce the same key, the **two-argument** overload throws `IllegalStateException`; the three-argument overload lets you provide a way to resolve conflicts.

The key takeaway of this lesson: **“Unmodifiable Map” and “not accepting null” are two distinct properties.** They coexist in `toUnmodifiableMap`, but you should not infer that *every* unmodifiable Map structure has the exact same null constraints.

## 2. API and Java Versions

`Collectors.toUnmodifiableMap` was added in **Java 10** and is available in Java 17+. There are two main overloads:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);

static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction);
~~~

Explanation of the type parameters:

| Symbol | Meaning | Example |
| --- | --- | --- |
| `T` | Type of each source element | `Item` |
| `K` | Type of keys in the Map | `String` |
| `U` | Type of values in the Map | `Integer` or `Item` |
| `keyMapper` | Converts `T` to `K` | `Item::code` |
| `valueMapper` | Converts `T` to `U` | `Item::price` or `Function.identity()` |
| `mergeFunction` | Merges two `U` values when keys collide | `Integer::sum` |

Example with a numeric result:

~~~java
Map<String, Integer> prices = items.stream()
        .collect(Collectors.toUnmodifiableMap(
                Item::code,
                Item::price));

System.out.println(prices.get("P02")); // 15
~~~

`Stream<Item>` becomes `Map<String,Integer>`. `collect` performs the collection step, while `toUnmodifiableMap(...)` is a **factory that creates a Collector**; calling the factory does not traverse the Stream by itself.

**Do not confuse `Collectors.toUnmodifiableMap` with `Map.of`:** `Map.of` builds a Map from arguments supplied directly, rather than collecting elements from a Stream.

## 3. Null Constraints: Disallowing Null Keys and Null Values

By API contract, the result of `Collectors.toUnmodifiableMap` **cannot contain a `null` key or `null` value**. If either mapping function produces `null` for a collected element, the collection throws **`NullPointerException`**.

### 3.1. When `keyMapper` returns null

~~~java
record Row(String key, Integer value) {}

List<Row> rows = List.of(
        new Row("A", 10),
        new Row(null, 20));

Map<String, Integer> result = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value)); // NullPointerException.
~~~

`List.of` here is still valid because **the two Row elements themselves are non-null**. A `key` field *inside* a Row can be null. When `Row::key` is applied to the second Row, it returns null, causing the collector to fail.

### 3.2. When `valueMapper` returns null

~~~java
List<Row> rows = List.of(
        new Row("A", 10),
        new Row("B", null));

Map<String, Integer> result = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value)); // NullPointerException.
~~~

The key `"B"` is valid, but the `null` value is not. Do not assume the Map will store `"B" -> null` or silently skip that element.

### 3.3. When the Stream element itself is null

This is a different case from **a mapper returning null**:

~~~java
List<Row> rows = java.util.Arrays.asList(
        new Row("A", 10),
        null);

// rows.stream().collect(Collectors.toUnmodifiableMap(
//         Row::key, Row::value));
~~~

A method reference call such as `Row::key` on a null source element can throw `NullPointerException` **right inside the mapper**. The outcome is still a failure, but the direct cause is being unable to invoke a method on a null source object, rather than a key/value pair being checked by the collector.

When null elements may appear in the source, clarify the policy: filter them out, reject invalid data, or replace them with normalized data according to business rules.

### 3.4. Null in a Map does not mean “key not found”

In some other Maps, `get(key) == null` can mean *key is absent* **or** *key exists with a null value*. For a Map created by `toUnmodifiableMap`, values cannot be null, so if `map.get("missing")` returns null, that key is not in the Map.

However, use `containsKey` when what you want to check is **key presence**, instead of relying on value comparisons as you might for more general Map APIs.

## 4. Strategy 1: Filter Out Invalid Data Before Collecting

If business requirements allow **skipping** records missing a key or value, filter them explicitly:

~~~java
List<Row> raw = List.of(
        new Row("A", 10),
        new Row(null, 20),
        new Row("B", null),
        new Row("C", 30));

Map<String, Integer> clean = raw.stream()
        .filter(row -> row.key() != null && row.value() != null)
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));

System.out.println(clean.size());     // 2
System.out.println(clean.get("A"));   // 10
System.out.println(clean.get("C"));   // 30
~~~

The filter condition is part of your **data policy**, not an automatic behavior of `toUnmodifiableMap`. When filtering, records with missing data will no longer appear in the result. If the problem requires reporting errors or auditing missing data, silently skipping them is usually inappropriate.

If there are also null source elements:

~~~java
List<Row> raw = java.util.Arrays.asList(
        new Row("A", 10), null, new Row("B", 20));

Map<String, Integer> clean = raw.stream()
        .filter(java.util.Objects::nonNull)
        .filter(row -> row.key() != null && row.value() != null)
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));
~~~

Filter out null `Row` objects first, before calling `row.key()` and `row.value()`. Placing `Objects::nonNull` in the **right position** is necessary to avoid errors in the mapper.

## 5. Strategy 2: Normalize or Require Mandatory Data

Many systems **cannot drop** records simply because information is missing. In that case, you can choose one of two approaches:

1. **Normalize** to a valid value accepted by business rules.
2. **Reject** invalid records with an exception that has a clear message.

Example: a missing value is defined as 0.

~~~java
Map<String, Integer> quantities = raw.stream()
        .filter(row -> row.key() != null)
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                row -> row.value() == null ? 0 : row.value()));
~~~

This snippet still requires **non-null keys**. Setting a missing quantity to 0 is only correct if that is a business rule; do not do it mechanically.

If the `code` field must be present, check it early:

~~~java
Map<String, Integer> quantities = raw.stream()
        .collect(Collectors.toUnmodifiableMap(
                row -> java.util.Objects.requireNonNull(
                        row.key(), "code must not be null"),
                row -> java.util.Objects.requireNonNull(
                        row.value(), "quantity must not be null")));
~~~

With non-null source elements and unique keys, a missing field will be reported as `NullPointerException` with a deterministic message produced by `requireNonNull`. In an application that handles business validation errors, you can also use dedicated validation to return a complete list of errors, rather than letting the first error abort the entire process.

**Do not use a shared placeholder for all null keys if it can create duplicate keys.** For example, replacing every missing key with `"UNKNOWN"` causes multiple records to share the same key, and the two-argument overload will throw `IllegalStateException` instead. Key normalization must preserve uniqueness or be paired with a duplicate-handling strategy.

## 6. Strategy 3: Represent “Absent Value” with a Non-Null Value

When you want to **keep the key** while recording that the value is not yet present, you can choose a non-null representation such as `Optional<U>` as the value:

~~~java
List<Row> raw = List.of(
        new Row("A", null),
        new Row("B", 20));

Map<String, Optional<Integer>> values = raw.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                row -> Optional.ofNullable(row.value())));

System.out.println(values.get("A").isEmpty()); // true
System.out.println(values.get("B").orElse(-1)); // 20
~~~

Here `valueMapper` returns an **`Optional<Integer>` that is always non-null**, so the collector accepts it. The Optional's content may be `empty`, but **the Optional object itself is not null**.

This approach changes the API model from `Map<String,Integer>` to `Map<String,Optional<Integer>>`; it should only be used if the domain genuinely needs to distinguish “key exists but value is missing” from “key does not exist”.

Note that `values.get("missing")` still returns `null` because **the key does not exist**. Therefore, distinguish between:

- `values.containsKey("A") == true`, and `values.get("A") == Optional.empty()`.
- `values.containsKey("missing") == false`, and `values.get("missing") == null`.

Do not call `isEmpty()` on the result of `get` for a key whose presence has not been verified.

## 7. Duplicate Keys: A Separate Error, Not a Null Error

The two-parameter overload:

~~~java
Collectors.toUnmodifiableMap(keyMapper, valueMapper)
~~~

**does not automatically pick the first or last record** when multiple elements produce the same key. It throws **`IllegalStateException`** upon encountering a duplicate key.

~~~java
List<Row> rows = List.of(
        new Row("A", 2),
        new Row("A", 5));

// Throws IllegalStateException:
Map<String, Integer> totals = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));
~~~

To handle duplicate keys, use the three-parameter overload:

~~~java
Map<String, Integer> totals = rows.stream()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value,
                Integer::sum));

System.out.println(totals.get("A")); // 7
~~~

`Integer::sum` is a `BinaryOperator<Integer>` for merging two values. Addition is associative and order-independent for this integer example (assuming no overflow with small data). This is an appropriate strategy when records sharing a key need their quantities summed.

**Important note:** having a `mergeFunction` does not make null keys or null values valid. The mapper functions still must not return null. Do not use `mergeFunction` to “fix null inputs” instead of validating before the collection step.

### 7.1. Choosing the first or last record on duplicate keys

You can supply:

~~~java
(left, right) -> left    // Keep the value from the left argument.
(left, right) -> right   // Keep the value from the right argument.
~~~

However, you should not assume `left` is always the “chronologically earliest record” in all parallel cases, when there is no encounter order, or when the source changes. If the preferred record is determined by timestamp or priority, design the merge with an **explicit comparison rule** instead of relying on callback processing order:

~~~java
record Event(String key, int priority) {}

Map<String, Event> chosen = events.stream()
        .collect(Collectors.toUnmodifiableMap(
                Event::key,
                Function.identity(),
                (a, b) -> a.priority() >= b.priority() ? a : b));
~~~

In this illustrative example, `events` is assumed to be declared as `List<Event>`. To get a deterministic result when two records have the same `priority`, you can add a tie-breaker on an appropriate identifier field if business rules require it.

### 7.2. Do not use a merge returning null as a way to store null values

`mergeFunction` should not be treated as a channel for storing null values in the resulting Map. For collectors based on `Map.merge` semantics, a null merge result can lead to **removing the mapping** for the key rather than storing the key with a null value. Design your merge function to return a **valid non-null value** according to business policy; if you need to record missing data, use an appropriate result type such as `Optional` or another domain structure.

## 8. The Resulting Map Is Unmodifiable, but Not “Deep Immutable”

For a Map returned by `toUnmodifiableMap`, structural modification operations must be rejected:

~~~java
Map<String, Integer> prices = Stream.of(
        new Row("A", 10),
        new Row("B", 20))
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value));

// prices.put("C", 30); // Throws UnsupportedOperationException.
// prices.remove("A"); // Throws UnsupportedOperationException.
// prices.clear();     // Throws UnsupportedOperationException.
~~~

Do not assume the Map will be an instance of `HashMap`, `LinkedHashMap`, or any specific implementation. The API does not require a fixed iteration order of keys or entries; **do not write tests that rely on `map.toString()` with a specific element order**. Instead, check `get(key)`, `containsKey(key)`, and `size()`.

### 8.1. Mutable value objects can still change

~~~java
record Box(String id, List<String> tags) {}

List<String> tags = new ArrayList<>(List.of("new"));
Box box = new Box("B01", tags);

Map<String, Box> boxes = Stream.of(box)
        .collect(Collectors.toUnmodifiableMap(
                Box::id,
                Function.identity()));

tags.add("sale");

System.out.println(boxes.get("B01").tags()); // [new, sale]
~~~

`boxes` does not allow adding, removing, or updating mappings, but the `Box` value holds a reference to a mutable `List<String>`. Changes to `tags` are still visible through the object referenced by the Map.

**An unmodifiable Map does not deep-copy its input elements.** If end-to-end immutability is needed, you must build suitable values, such as records with immutable components or defensive copies of collections:

~~~java
record SafeBox(String id, List<String> tags) {
    SafeBox {
        tags = List.copyOf(tags);
    }
}
~~~

`List.copyOf` rejects null elements and creates/returns an unmodifiable List; for mutable child objects, layered copying is still required if deep immutability is demanded.

## 9. Comparison with Similarly Named Map APIs

| API | Purpose | Key characteristics to remember |
| --- | --- | --- |
| `Collectors.toUnmodifiableMap(k,v)` | Collects a Stream into an unmodifiable Map | Disallows null keys/values; duplicate keys throw an error |
| `Collectors.toUnmodifiableMap(k,v,merge)` | Collects into an unmodifiable Map, handling duplicate keys | Disallows null keys/values; merge must follow an appropriate policy |
| `Collectors.toMap(k,v)` | Collects a Stream into a Map | Does not guarantee a specific Map implementation, mutability, or null behavior by contract |
| `Collectors.toMap(k,v,merge)` | Collects a Stream, merging duplicate keys | Need to understand the merge policy and output Map |
| `Map.of(k,v,...)` | Directly creates an unmodifiable Map from key/value pairs | Disallows null and duplicate keys |
| `Map.ofEntries(entries...)` | Directly creates an unmodifiable Map from entries | Disallows null and duplicate keys |
| `Map.copyOf(existing)` | Creates an unmodifiable Map containing the mappings of an existing Map | Disallows null keys/values; does not guarantee deep copy |
| `Collections.unmodifiableMap(existing)` | Creates an unmodifiable **view** over an existing Map | Changes made through the original Map may be visible in the view |

**Be careful with `Collectors.toMap`:** do not use it under the assumption that “`toMap` definitely accepts null”. Across overloads, implementations, and JDK versions, null-related behavior has its own constraints and is not a guaranteed contract to substitute for `toUnmodifiableMap`. If you need to handle null, it is best to encode an explicit policy in the pipeline and choose a result structure with a suitable contract.

Example distinguishing `Collections.unmodifiableMap`:

~~~java
Map<String, Integer> mutable = new HashMap<>();
mutable.put("A", 1);

Map<String, Integer> view =
        Collections.unmodifiableMap(mutable);
mutable.put("B", 2);

System.out.println(view.containsKey("B")); // true
~~~

`view` does not allow modifications through itself, but the **mutable source Map** can still be updated via the `mutable` variable and the view reflects those changes. With `toUnmodifiableMap`, the output Map is not just a direct wrapper over a source collection; it is the collected result from the Stream's key/value pairs. However, mutable value objects can still share references as shown in Section 8.

## 10. Parallel Streams, Ordering, and Merge Correctness

`Collectors.toUnmodifiableMap` can be used in either sequential or parallel pipelines:

~~~java
Map<String, Integer> totals = Stream.of(
        new Row("A", 2),
        new Row("B", 3),
        new Row("A", 5))
        .parallel()
        .collect(Collectors.toUnmodifiableMap(
                Row::key,
                Row::value,
                Integer::sum));

System.out.println(totals.get("A")); // 7
System.out.println(totals.get("B")); // 3
~~~

During parallel reduction, partial results may be combined according to varying execution schedules. Therefore, the merge should be **stateless, non-interfering**, and appropriately **associative** if you want deterministic results regardless of how the source is split and combined.

For example, `Integer::sum` on small values satisfies this requirement. A merge like `(a,b) -> a - b` is not associative and can produce different results when partitioning changes; it should not be used for parallel aggregation unless specific conditions have been carefully designed.

Avoid doing this:

~~~java
// Avoid mutating shared external state from the merger:
AtomicInteger calls = new AtomicInteger();
// (a, b) -> { calls.incrementAndGet(); return a + b; }
~~~

Counting merge invocations via side effects is not a reliable basis for inferring which record took precedence, because splitting/combining and callback execution order are not a stable contract for that purpose.

## 11. Complete Java 17+ Example, Standalone Compile and Run

Create the file **`UnmodifiableMapDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

public class UnmodifiableMapDemo {
    record Item(String code, Integer quantity) {}
    record Box(String code, List<String> tags) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 2),
                new Item("B", 4));

        Map<String, Item> byCode = items.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        Function.identity()));
        System.out.println("A.quantity=" + byCode.get("A").quantity());
        System.out.println("containsB=" + byCode.containsKey("B"));

        try {
            byCode.put("C", new Item("C", 1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=true");
        }

        List<Item> duplicated = List.of(
                new Item("A", 2),
                new Item("A", 5));

        try {
            duplicated.stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Item::code,
                            Item::quantity));
        } catch (IllegalStateException ex) {
            System.out.println("duplicateRejected=true");
        }

        Map<String, Integer> merged = duplicated.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        Item::quantity,
                        Integer::sum));
        System.out.println("mergedA=" + merged.get("A"));

        try {
            List.of(new Item(null, 1)).stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Item::code,
                            Item::quantity));
        } catch (NullPointerException ex) {
            System.out.println("nullKeyRejected=true");
        }

        try {
            List.of(new Item("X", null)).stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Item::code,
                            Item::quantity));
        } catch (NullPointerException ex) {
            System.out.println("nullValueRejected=true");
        }

        List<Item> incomplete = List.of(
                new Item(null, 10),
                new Item("X", null),
                new Item("Y", 5));

        Map<String, Integer> filtered = incomplete.stream()
                .filter(item ->
                        item.code() != null && item.quantity() != null)
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        Item::quantity));
        System.out.println("filteredSize=" + filtered.size());
        System.out.println("filteredY=" + filtered.get("Y"));

        Map<String, Optional<Integer>> withMissing = List.of(
                new Item("X", null),
                new Item("Y", 5))
                .stream()
                .collect(Collectors.toUnmodifiableMap(
                        Item::code,
                        item -> Optional.ofNullable(item.quantity())));
        System.out.println("X.isEmpty=" + withMissing.get("X").isEmpty());

        List<String> tags = new ArrayList<>(List.of("new"));
        Box box = new Box("B1", tags);
        Map<String, Box> boxes = List.of(box).stream()
                .collect(Collectors.toUnmodifiableMap(
                        Box::code,
                        Function.identity()));
        tags.add("sale");
        System.out.println("tagsCount=" + boxes.get("B1").tags().size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac UnmodifiableMapDemo.java
java UnmodifiableMapDemo
~~~

**Stdout output:**

~~~text
A.quantity=2
containsB=true
unmodifiable=true
duplicateRejected=true
mergedA=7
nullKeyRejected=true
nullValueRejected=true
filteredSize=1
filteredY=5
X.isEmpty=true
tagsCount=2
~~~

Explanation of the output groups:

1. `A.quantity=2` and `containsB=true`: the two Item elements are mapped into Map entries and accessed by key.
2. `unmodifiable=true`: `put` is not supported on the resulting Map.
3. `duplicateRejected=true`: the two-argument overload encounters two `"A"` keys and throws `IllegalStateException`.
4. `mergedA=7`: the three-argument overload uses `Integer::sum` to merge the two values 2 and 5.
5. `nullKeyRejected=true` and `nullValueRejected=true`: two separate collections demonstrate that null in either the key mapper or value mapper is rejected.
6. `filteredSize=1` and `filteredY=5`: the pipeline keeps only records that have both a key and a value.
7. `X.isEmpty=true`: the Map has key `"X"` with **the value `Optional.empty()`**, not null.
8. `tagsCount=2`: the Map is structurally unmodifiable, but it does not deep-copy the mutable List inside the value.

The program intentionally **does not print the entire Map**, because entry iteration order is not guaranteed. Error cases catch the exact exception types so that stdout stays stable and does not depend on JVM-generated error messages.

## 12. Notes on `null`, Errors, and API Design

### 12.1. Do not confuse the three error scenarios

| Symptom | Source scenario | Typical exception |
| --- | --- | --- |
| `keyMapper` returns null | `new Item(null, 1)` | `NullPointerException` |
| `valueMapper` returns null | `new Item("A", null)` | `NullPointerException` |
| Two elements have the same key | `new Item("A", 1)` and `new Item("A", 2)` | `IllegalStateException` if no merger is provided |
| The source element itself is null | Source contains `null` | Possible `NullPointerException` when invoking the mapper |
| Modifying the resulting Map | `put`, `remove`, `clear` on the output Map | `UnsupportedOperationException` |

Do not catch all `RuntimeException`s and ignore them. Each error has a different meaning and should be handled at the appropriate place: source validation, duplicate resolution policy, or rules for using the result.

### 12.2. An unmodifiable Map does not mean thread-safe at every layer

Not modifying the resulting structure makes sharing the Map safer, but the Map may contain mutable value objects managed by the application. If those values are modified concurrently, **thread-safety still depends on those objects themselves and how they are synchronized**. Do not take the name “unmodifiable” as a promise that the entire object graph is immutable or automatically thread-safe.

### 12.3. Null can be an important business signal

If `quantity == null` means “not yet inventoried”, whereas `quantity == 0` means “inventoried and out of stock”, replacing null with 0 will **lose data meaning**. Use a domain type with explicit states, `Optional`, or a result object describing missing data when needed. Normalization logic must be driven by business requirements, not merely to avoid `NullPointerException`.

### 12.4. A Map has only one value per key

Even when merging is allowed, a Map still stores **a single mapping** per key. If you need to keep all records sharing a key, consider `groupingBy` to produce `Map<K,List<T>>`, and then design the immutability of the Map and Lists according to your goals; do not confuse value merging in `toUnmodifiableMap` with grouping multiple values.

## 13. Self-Check Exercises

**Question 1.** Given `record R(String key, Integer value) {}`, an element `new R("A", null)` is collected with `toUnmodifiableMap(R::key, R::value)`. What is the result?

**Answer:** `NullPointerException`, because `valueMapper` returns null. The collector does not store `"A" -> null`.

**Question 2.** Given two elements with the same key `"A"` and values 3 and 4 respectively, what happens with the two-argument overload? What should you do if you want to sum the two values?

**Answer:** The two-argument overload throws `IllegalStateException` due to the duplicate key. Use `Collectors.toUnmodifiableMap(R::key, R::value, Integer::sum)` to get the value 7.

**Question 3.** Can you call `put` on the Map returned by `toUnmodifiableMap` to add an element?

**Answer:** No. Structural modification operations throw `UnsupportedOperationException`.

**Question 4.** If the Map contains a mutable `ArrayList` as a value, can the List be modified through another reference?

**Answer:** Yes. The unmodifiability of the Map does not automatically make its values immutable or create a deep copy. Defensive copying or immutable value design is required if that is a requirement.

**Question 5.** Why should you not default to `Collectors.toMap` as a way to store null?

**Answer:** Different overloads and implementations have their own constraints, so it cannot be treated as a promise to support null in all cases. It is better to explicitly define how to filter, normalize, or represent absent data and choose an appropriate API.

**Question 6.** When should you use `Optional<Integer>` as the value?

**Answer:** When you need to keep the key present in the Map even though a value may not yet exist, and the domain model genuinely needs to distinguish that state. `Optional.empty()` is a non-null object, which is compatible with the collector.

**Question 7.** Does using `Map.of("A", null)` solve the null constraint of `toUnmodifiableMap`?

**Answer:** No. `Map.of` also rejects null keys and null values.

**Question 8.** Can you rely on the iteration order of `map.entrySet()` from `toUnmodifiableMap` to produce deterministic stdout?

**Answer:** You should not. There is no contract guaranteeing a specific iteration order. Look up by key or sort the entries when ordered output is required.

## 14. Key Takeaways

`Collectors.toUnmodifiableMap` is used to **collect a Stream into an unmodifiable Map**, starting in Java 10. Rules to always remember:

- **Key and value mappers must not return `null`.** If they return null, collection throws `NullPointerException`.
- **Duplicate keys do not automatically keep the first or last entry.** The two-argument overload throws `IllegalStateException`; the three-argument overload uses the `mergeFunction` you provide.
- **Unmodifiable does not mean deep immutable.** The Map is structurally unmodifiable, but mutable values can still change state.
- **Do not assume Map iteration order.** Look up by key or sort when ordered display is needed.
- **Handle null according to business policy before `collect`:** filter, validate, normalize, or use a value type that represents absence.
- **Do not confuse it with `Collectors.toMap`, `Map.of`, or `Collections.unmodifiableMap`.** They have different contracts and purposes.

Choose `toUnmodifiableMap` when you want a collected key-value structure that cannot be modified and you have clear policies for null, duplicate keys, and value types.
