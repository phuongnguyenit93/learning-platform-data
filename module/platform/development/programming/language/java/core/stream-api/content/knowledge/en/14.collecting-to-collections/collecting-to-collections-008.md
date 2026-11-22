# Comparing Result Mutability, Ordering, and Null Policies

## 1. Same Pipeline, Different Contracts on the Output Collection

In the **Collecting into Collections** chapter of **JAVA_STREAM_API**, after `filter`, `map`, or `flatMap` steps, we often want to materialize data into a `List`, `Set`, or `Map` for further use. Choosing a terminal operation does not only determine the **data type**, but also affects three contracts that matter directly to your program:

1. **Mutability:** Does the Collection allow `add`, `remove`, `set`, or `put` after collection?
2. **Ordering:** Does the Collection preserve the Stream's encounter order, insertion order, sorted order, or guarantee no iteration order?
3. **`null` policy:** Does the Collection or collector accept `null` elements, `null` keys, `null` values, or throw an exception?

For example, two statements can produce lists that look alike yet have different contracts for downstream code:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> immutableResult = List.of("An", "Binh")
    .stream()
    .toList();

List<String> unspecifiedResult = List.of("An", "Binh")
    .stream()
    .collect(Collectors.toList());
~~~

The first list from `Stream.toList()` is **unmodifiable** by specification. With `Collectors.toList()`, the API **does not guarantee** the implementation class, mutability, serializability, or thread-safety. Many current JDKs return a mutable `ArrayList`, but writing code that relies on that trait depends on an implementation detail.

~~~text
                 Stream<T> after filter / map / ...
                               │
                 Choose how to materialize data
                               │
           ┌───────────────────┼────────────────────┐
           ▼                   ▼                    ▼
          List                Set                  Map
         (List)              (Set)                (Map)
           │                   │                    │
       - Keep dups?        - Deduplicate        - Duplicate keys?
       - Order?            - Order?             - Key order?
       - Modifiable?       - Modifiable?        - Modifiable?
       - Allow null?       - Allow null?        - Null key/value?
~~~

**Core principle:** Choose a collector based on **the contract that must be guaranteed**, not because a particular JDK happens to return an `ArrayList` or `HashMap`.

The examples use **Java 17+**. `Stream.toList()` was introduced in Java 16; `Collectors.toUnmodifiableList/Set/Map` and `List.copyOf/Set.copyOf/Map.copyOf` have been available since Java 10. Core collectors such as `toList`, `toSet`, `toMap`, and `toCollection` have existed since Java 8.

## 2. Quick Comparison Table of Common Collection Methods

The table below describes **what code is allowed to rely on**, as opposed to common implementation details:

| Collection method | Modifying Collection after creation | Result iteration order | `null` policy |
| --- | --- | --- | --- |
| `stream.toList()` | **No**: list is unmodifiable | Preserves encounter order if Stream is ordered | Can contain `null` elements |
| `collect(Collectors.toList())` | **Not guaranteed** | Follows encounter order if Stream is ordered | No explicit guarantee in collector spec; common JDKs retain `null` |
| `collect(Collectors.toUnmodifiableList())` | **No** | Preserves encounter order if Stream is ordered | **Forbids `null`**; throws `NullPointerException` |
| `collect(Collectors.toCollection(ArrayList::new))` | **Yes**: concrete `ArrayList` | Preserves encounter order if Stream is ordered | `ArrayList` allows `null` |
| `collect(Collectors.toSet())` | **Not guaranteed** | **Not guaranteed** iteration order | No explicit guarantee on `null`; avoid relying on implementation details |
| `collect(Collectors.toUnmodifiableSet())` | **No** | **Not guaranteed** iteration order | **Forbids `null`**; throws `NullPointerException` |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | **Yes**: `LinkedHashSet` | Insertion order; for ordered sources, first-appearance order of each value | Allows one `null` element |
| `collect(Collectors.toCollection(TreeSet::new))` | **Yes**: `TreeSet` | Natural comparison order (or comparator provided by supplier) | Naturally ordered `TreeSet` does not accept `null` |

For `Map`, distinguish between keys and values. `toMap` guarantees neither Map type, mutability, nor ordering; `toUnmodifiableMap` yields an unmodifiable Map and forbids `null` keys or values. If you want an ordered and mutable `LinkedHashMap`, pass a supplier to the four-argument overload of `Collectors.toMap`.

**Two warnings when reading the table:** (1) "Not guaranteed to be modifiable" is different from "unmodifiable"; (2) for `Set`, the order *printed during a test run* does not establish an API ordering guarantee.

## 3. Mutability: toList, toUnmodifiableList, and toCollection

### 3.1. `Stream.toList()` Returns an Unmodifiable List

~~~java
import java.util.List;
import java.util.stream.Stream;

public class StreamToListDemo {
    public static void main(String[] args) {
        List<String> names = Stream.of("An", "Binh", "Chi")
            .toList();

        System.out.println(names); // [An, Binh, Chi]

        // names.add("Dung");      // UnsupportedOperationException
        // names.remove("An");     // UnsupportedOperationException
        // names.set(0, "Other");  // UnsupportedOperationException
    }
}
~~~

By contract, calls to list-mutating methods throw `UnsupportedOperationException`. `Stream.toList()` does not guarantee implementation type, `Serializable`, or object identity; the result may be *value-based*, so avoid synchronizing on the list's monitor or using `==` to compare two results.

"Unmodifiable" applies to the **Collection structure**, and does not prevent modifying the state of **mutable elements** inside it; an example appears in section 10.

### 3.2. `Collectors.toList()` Has No Mutability Guarantee

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> collected = Stream.of("An", "Binh")
    .collect(Collectors.toList());

// Do not write business code requiring collected.add("Chi") to succeed.
// The Collectors.toList() specification does not promise that.
~~~

On a current JDK, calling `add` often succeeds because the collector uses an `ArrayList`. That outcome is not an API contract. If the requirement is a **modifiable list**, choose `toCollection` with an explicit supplier.

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> names = Stream.of("An", "Binh")
    .collect(Collectors.toCollection(ArrayList::new));

names.add("Chi");
names.remove("An");
names.set(0, "Binh new");

System.out.println(names); // [Binh new, Chi]
~~~

`toCollection(ArrayList::new)` makes both the container type and mutability explicit. Pass a different supplier if another data structure is required, such as `LinkedList::new` or `LinkedHashSet::new`.

### 3.3. `Collectors.toUnmodifiableList()` Also Forbids Modification

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Binh")
    .collect(Collectors.toUnmodifiableList());

// names.add("Chi"); // UnsupportedOperationException
~~~

When the result does not need modification and elements are known to contain no `null`, both `Stream.toList()` and `Collectors.toUnmodifiableList()` are suitable choices. However, they **differ in null policy**, and `Stream.toList()` is usually more concise when no special collector is needed.

### 3.4. Why Can You Not Judge Solely by the List Return Type?

The `List<E>` interface includes **optional** mutating methods. A variable of type `List<String>` might point to a mutable `ArrayList` or an unmodifiable list. The compiler cannot infer from the `List` type alone that `add` will succeed. The contract must come from how the list is created and from API documentation.

## 4. List Null Policy: Differences That Easily Cause Runtime Errors

`null` can appear when legacy APIs return absent values, when mapping incomplete data, or when a `map` callback returns `null`.

### 4.1. `Stream.toList()` Can Contain null

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("A", null, "B")
    .toList();

System.out.println(values); // [A, null, B]
System.out.println(values.get(1) == null); // true
~~~

The list remains **unmodifiable**, even though it contains a `null` element. "Unmodifiable" and "null-free" are **two independent properties**.

### 4.2. `Collectors.toUnmodifiableList()` Forbids null

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Throws NullPointerException during terminal collect:
List<String> invalid = Stream.of("A", null, "B")
    .collect(Collectors.toUnmodifiableList());
~~~

This collector throws `NullPointerException` if any element is `null`. This is contractual behavior, differing from `Stream.toList()`.

If the requirement is to **drop null elements and return an unmodifiable list**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> cleaned = Stream.of("A", null, "B")
    .filter(Objects::nonNull)
    .collect(Collectors.toUnmodifiableList());

System.out.println(cleaned); // [A, B]
~~~

Or you can use `filter(Objects::nonNull).toList()` if the output policy does not require the `toUnmodifiableList` collector.

### 4.3. `List.of` and `List.copyOf` Forbid null

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> withNull = Stream.of("A", null).toList();

// List.copyOf(withNull); // NullPointerException.
// List.of("A", null);    // NullPointerException.
~~~

Therefore, if you choose an unmodifiable conversion via `List.copyOf`, handle `null` **before** converting.

### 4.4. Is `Collectors.toList()` Safe to Rely On with null?

Many current JDKs accumulate `Collectors.toList()` into an `ArrayList` and accept `null`. However, the collector specification promises neither a List implementation nor a specific null policy the way `Collectors.toUnmodifiableList()` explicitly states it. When data can contain `null` as a business requirement, make the policy explicit: `toCollection(ArrayList::new)` if you want to hold `null` in a mutable `ArrayList`, `Stream.toList()` if you need an unmodifiable List that can contain `null`, or filter/transform `null` before using a collector that forbids `null`.

## 5. Encounter Order: Source Order vs. Collection Iteration Order

**Encounter order** is the order a Stream must respect if the source and pipeline are ordered. For instance, `List.stream()` has the List's element order; `HashSet.stream()` does not promise an encounter order.

### 5.1. Lists from Ordered Streams Preserve Encounter Order

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("Chi", "An", "Binh");

List<String> a = names.stream().toList();

List<String> b = names.stream()
    .collect(Collectors.toList());

List<String> c = names.stream()
    .collect(Collectors.toUnmodifiableList());

System.out.println(a); // [Chi, An, Binh]
System.out.println(b); // [Chi, An, Binh]
System.out.println(c); // [Chi, An, Binh]
~~~

`toList()` preserves encounter order if present. `Collectors.toList()` and `toUnmodifiableList()` are ordered collectors; with ordered sources, they also accumulate in encounter order, even when the terminal runs on a parallel stream.

### 5.2. `parallel()` Does Not Automatically Erase Encounter Order

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 5)
    .parallel()
    .boxed()
    .toList();

System.out.println(values); // [1, 2, 3, 4, 5]
~~~

The pipeline may process elements across different worker threads, but the result of the terminal `toList()` must preserve encounter order when the source is ordered.

Conversely, `forEach` on a parallel stream does not guarantee **action execution** order. Never build a result list via `parallelStream().forEach(shared::add)` on a shared `ArrayList`: that behavior is both non-thread-safe and defeats the Stream API's proper collection mechanism.

### 5.3. `unordered()` Allows Dropping the Constraint

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 5)
    .parallel()
    .unordered()
    .boxed()
    .toList();

// May still be [1, 2, 3, 4, 5], but that order is no longer promised.
~~~

`unordered()` is not a random shuffle; it removes the encounter-order constraint. When you need a list always in a fixed order, use an ordered source or `sorted(...)` with a comparator that adequately distinguishes elements.

### 5.4. Do Not Treat a Single Printed Order as a Contract

A `HashSet` or `HashMap` may produce the same iteration order across several runs, yet that order is not guaranteed. In tests, compare using the appropriate structure: if order matters, use `List`/`LinkedHashSet`/`LinkedHashMap` or a sorted collection; otherwise, compare as a set of elements.

## 6. Collecting into Set: Deduplication, Ordering, and null

`Set` removes duplicate elements according to the equality rule of the corresponding Set type. When moving from a Stream to a Set, you change the **duplicate-retention policy** and may also change result iteration order.

### 6.1. `Collectors.toSet()` Guarantees Neither Order Nor Mutability

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> source = List.of("B", "A", "B", "C");

Set<String> unique = source.stream()
    .collect(Collectors.toSet());

System.out.println(unique.size()); // 3
System.out.println(unique.containsAll(List.of("A", "B", "C"))); // true
~~~

Do not write tests expecting `unique.toString().equals("[B, A, C]")` or `unique.add("D")` to work: `toSet()` guarantees neither iteration order, concrete Set type, nor mutability.

### 6.2. `toUnmodifiableSet()` Is Unmodifiable and Forbids null

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Set<String> unique = Stream.of("B", "A", "B", "C")
    .collect(Collectors.toUnmodifiableSet());

System.out.println(unique.size()); // 3

// unique.add("D"); // UnsupportedOperationException
// Stream.of("A", null).collect(Collectors.toUnmodifiableSet());
//                              ^ NullPointerException
~~~

When multiple elements are **equal** under `equals`, the collector may keep **any representative** from that group; do not rely on always keeping the first-appearing object. Iteration order of the returned Set is also not guaranteed.

### 6.3. `LinkedHashSet` for an Insertion-Ordered Set

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.stream.Collectors;

LinkedHashSet<String> uniqueInOrder = List.of("B", "A", "B", "C")
    .stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(uniqueInOrder); // [B, A, C]

uniqueInOrder.add("D"); // Modifiable.
~~~

With an encounter-ordered source, the first appearance of each value determines its insertion order into `LinkedHashSet`. However, if the source was `unordered()`, this collection only preserves the **actual received/insertion order**; it cannot reconstruct a discarded original order.

`LinkedHashSet` allows one `null` element, so it can be used if business policy requires "retaining one null value" in the result set.

### 6.4. `TreeSet` Establishes Order via Comparator

~~~java
import java.util.TreeSet;
import java.util.List;
import java.util.stream.Collectors;

TreeSet<Integer> sortedUnique = List.of(5, 2, 5, 1, 3)
    .stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(sortedUnique); // [1, 2, 3, 5]
~~~

`TreeSet` is modifiable and iterates in comparison order. It drops elements when the comparator considers them equivalent (`compare(a,b) == 0`), even if `equals` between the two elements differs; therefore, ensure the comparator aligns with the business equality rule. A `TreeSet` using natural ordering does not allow `null`.

If you only need an unmodifiable ordered List, you can use `distinct().sorted().toList()`, without necessarily creating a `TreeSet`.

## 7. Collecting into Map: Three Contracts That Must Be Clear

`Map<K,V>` adds two issues: **duplicate keys** and **`null` in keys/values**. A collector can define a duplicate-key policy, while the returned Map has ordering or mutability contracts different from List or Set.

### 7.1. Default `toMap` Rejects Duplicate Keys

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record User(int id, String name) {}

List<User> users = List.of(
    new User(1, "An"),
    new User(2, "Binh")
);

Map<Integer, String> byId = users.stream()
    .collect(Collectors.toMap(User::id, User::name));

System.out.println(byId.get(1)); // An
~~~

If two elements share the same `id`, the two-argument overload of `toMap` throws `IllegalStateException`. You must define a merge policy or choose truly unique keys; never assume "the last value overwrites automatically".

~~~java
List<User> duplicated = List.of(
    new User(1, "An"),
    new User(1, "An updated")
);

// Pick the entry appearing later in encounter order:
Map<Integer, String> lastWins = duplicated.stream()
    .collect(Collectors.toMap(
        User::id,
        User::name,
        (oldValue, newValue) -> newValue
    ));
~~~

With an encounter-ordered parallel stream, the collector may merge branches yet must still adhere to the semantics of an ordered collector; even so, when "latest" means **business timestamp**, compare timestamps or versions explicitly rather than assuming stream order reflects the newest record.

### 7.2. `toMap` Does Not Promise a Modifiable or Ordered Map

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> orderedById = users.stream()
    .collect(Collectors.toMap(
        User::id,
        User::name,
        (left, right) -> left,
        LinkedHashMap::new
    ));

System.out.println(orderedById); // {1=An, 2=Binh}
orderedById.put(3, "Chi"); // Modifiable.
~~~

The four-argument overload lets you pick a concrete Map. `LinkedHashMap` uses insertion order; with an ordered source, insertion order reflects the first appearance of each key in the pipeline. If you want a Map **ordered by key**, choose `TreeMap::new` with a comparable key type or a supplier with an appropriate comparator.

### 7.3. `toUnmodifiableMap` Creates an Unmodifiable Map

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> immutableById = users.stream()
    .collect(Collectors.toUnmodifiableMap(
        User::id,
        User::name
    ));

// immutableById.put(3, "Chi"); // UnsupportedOperationException
~~~

`toUnmodifiableMap` forbids `null` in **both keys and values**. It also throws `IllegalStateException` on duplicate keys in the two-argument overload; a three-argument overload accepts a merge function to resolve duplicate keys. Do not rely on the iteration order of the Map returned by this collector.

### 7.4. Null Keys and Values in Map: Handle Before the Terminal Operation

Do not design pipelines that depend on whether `Collectors.toMap` accepts `null` keys or `null` values in a specific JDK version. The API offers no general guarantee of a Map supporting both; some combinations throw `NullPointerException` during collection.

A clear approach is filtering out incomplete data before building the Map:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

record Entry(String key, String value) {}

List<Entry> raw = List.of(
    new Entry("A", "Alpha"),
    new Entry(null, "No key"),
    new Entry("B", null)
);

Map<String, String> safe = raw.stream()
    .filter(entry -> entry.key() != null && entry.value() != null)
    .collect(Collectors.toUnmodifiableMap(
        Entry::key,
        Entry::value
    ));

System.out.println(safe); // {A=Alpha}
~~~

If null has business meaning (e.g., "value not yet recorded"), choose a data type that represents this state explicitly, such as a result record with a status field, rather than silently dropping records or relying on HashMap's null policy.

## 8. `groupingBy`, Map Ordering, and List Ordering Within Each Group

`groupingBy` is a common collector when each element is placed into a group by key. Because the returned Collection is typically a Map, you must consider both **key order** and **element order within each group**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String customer, int quantity) {}

List<Order> orders = List.of(
    new Order("An", 2),
    new Order("Binh", 1),
    new Order("An", 3)
);

Map<String, List<Order>> grouped = orders.stream()
    .collect(Collectors.groupingBy(Order::customer));
~~~

The default `Collectors.groupingBy` form **does not guarantee** the Map type, mutability, serializability, or thread-safety of the resulting Map. The downstream `Collectors.toList()` also does not guarantee mutable Lists. With an ordered source, group lists generally retain the encounter order of elements in the group per the downstream collector's semantics; however, if you need a specific List type or key iteration order, declare it explicitly.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> orderedGroups = orders.stream()
    .collect(Collectors.groupingBy(
        Order::customer,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));

// Keys in first-seen order: An, Binh.
// In group An, orders appear in order [2, 3].
~~~

`LinkedHashMap::new` guarantees key iteration in insertion order, and `toCollection(ArrayList::new)` creates mutable lists preserving the encounter order of elements within each group when the source is ordered. If an unmodifiable output is desired, apply an appropriate transformation for both the Map and the inner Lists; wrapping only the outer Map **does not** automatically make the inner Lists immutable.

**Null note:** standard `groupingBy` implementations do not allow the classifier to return a `null` key, typically throwing `NullPointerException`. Filter or replace null keys with a named placeholder group before grouping.

## 9. Mutable, Unmodifiable, and Immutable Are Three Concepts to Distinguish

- **Mutable Collection:** structural mutations like `add`, `remove`, `put` are supported by contract.
- **Unmodifiable Collection:** structural modifications cannot be performed through that Collection reference; however, elements stored inside may still be mutable.
- **Deep immutable:** the entire data graph observable through the Collection cannot change after creation. This is a stronger requirement that `toList()`, `toUnmodifiableList()`, and `List.copyOf()` **do not automatically guarantee**.

### 9.1. An Unmodifiable List Can Still Hold Mutable Objects

~~~java
import java.util.List;
import java.util.stream.Stream;

StringBuilder builder = new StringBuilder("A");

List<StringBuilder> result = Stream.of(builder).toList();

// result.add(new StringBuilder("B")); // UnsupportedOperationException
builder.append("!");

System.out.println(result.get(0)); // A!
~~~

The list itself has no elements added, removed, or replaced, yet an element's contents changed. If the application needs a truly immutable snapshot, convert data into immutable value objects or defensive copies before collecting.

~~~java
List<String> snapshot = Stream.of(builder)
    .map(StringBuilder::toString)
    .toList();

// snapshot contains "A!" at creation time.
builder.append("?");
System.out.println(snapshot); // [A!]
~~~

### 9.2. `Collections.unmodifiableList` Is a View; `List.copyOf` Creates a Contractual Copy

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

ArrayList<String> source = new ArrayList<>(List.of("A"));

List<String> view = Collections.unmodifiableList(source);
List<String> copy = List.copyOf(source);

source.add("B");

System.out.println(view); // [A, B] because view reflects the backing list.
System.out.println(copy); // [A] because copy is independent of changes to source.
~~~

`Collections.unmodifiableList(source)` blocks modifications **through the view**, but still reflects mutations to `source` via another reference. `List.copyOf(source)` returns an unmodifiable list independent of later changes to `source`; it does not deep-copy individual elements.

`List.copyOf`, `Set.copyOf`, and `Map.copyOf` all forbid `null` in the relevant positions. `Set.copyOf`/`Map.copyOf` do not promise iteration order like `LinkedHashSet`/`LinkedHashMap`.

### 9.3. `collectingAndThen` Is Useful When a Finishing Step Is Needed

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> immutableCopy = Stream.of("A", "B")
    .collect(Collectors.collectingAndThen(
        Collectors.toList(),
        List::copyOf
    ));
~~~

`collectingAndThen` runs a finisher after accumulation, allowing conversion of the List to a final type or format. With `List::copyOf`, the finisher will throw NPE if the result contains `null`.

There is no need to add such a wrapper if `Stream.toList()` or `Collectors.toUnmodifiableList()` already meets the requirement. When a **view** or a snapshot that may contain `null` is needed, define the policy explicitly rather than automatically using `copyOf`.

## 10. A Practical Problem: A Clean, Ordered List of Customer Codes

Input from a legacy system may contain whitespace, inconsistent casing, `null` values, and duplicate codes. Product requirements:

- Remove `null` and blank codes.
- Normalize and deduplicate.
- Sort for stable display.
- Return an unmodifiable result.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class CustomerCodes {
    public static void main(String[] args) {
        List<String> rawCodes = Arrays.asList(
            " b02 ", null, "A01", "a01 ", "", "C03", "B02"
        );

        List<String> codes = rawCodes.stream()
            .filter(Objects::nonNull)
            .map(String::strip)
            .filter(code -> !code.isEmpty())
            .map(code -> code.toUpperCase(Locale.ROOT))
            .distinct()
            .sorted()
            .toList();

        System.out.println(codes); // [A01, B02, C03]

        // codes.add("D04"); // UnsupportedOperationException
    }
}
~~~

Because the final data **contains no `null`**, `toList()` is a concise choice. `distinct()` is a stateful intermediate operation for deduplication; `sorted()` produces lexicographical order. For large sources, these two operations can consume significant memory; measure if performance matters.

If business logic needs to **preserve the first-appearance order of codes** instead of sorting, omit `sorted()` and use `distinct().toList()` on an ordered source. If a **modifiable** set of codes in appearance order is needed, use:

~~~java
import java.util.LinkedHashSet;
import java.util.stream.Collectors;

LinkedHashSet<String> editable = rawCodes.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .filter(code -> !code.isEmpty())
    .map(code -> code.toUpperCase(Locale.ROOT))
    .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

If the goal is merely checking whether a code is present, a `Set` is usually more suitable than a `List`. However, if the UI must display a specific order, choose the data structure that expresses that requirement.

## 11. Common Mistakes

### Mistake 1: Relying on the Mutability of Collectors.toList

~~~java
List<String> names = source.stream()
    .collect(Collectors.toList());

// names.add("X") may work on the current JDK,
// but is not guaranteed by the Collectors.toList() contract.
~~~

Use `Collectors.toCollection(ArrayList::new)` when the result must definitely be modifiable.

### Mistake 2: Assuming `toList()` and `toUnmodifiableList()` Are Always Equivalent

~~~java
List<String> a = Stream.of("X", null).toList(); // May contain null.

// This line throws NullPointerException:
// List<String> b = Stream.of("X", null)
//     .collect(Collectors.toUnmodifiableList());
~~~

Both are unmodifiable, but their `null` policies differ.

### Mistake 3: Assuming toSet Preserves Encounter Order

~~~java
Set<Integer> set = List.of(3, 1, 2, 1).stream()
    .collect(Collectors.toSet());

// Can only assert the set contains 1, 2, 3; do not rely on print order.
~~~

Use `toCollection(LinkedHashSet::new)` to keep first-appearance order, or `toCollection(TreeSet::new)` if comparison order is needed.

### Mistake 4: Assuming Parallel Streams Lose List Order

~~~java
List<Integer> values = List.of(3, 1, 2).parallelStream()
    .toList();

// values still has encounter order [3, 1, 2].
~~~

A parallel stream may split tasks, but it does not by default drop the terminal's ordering constraint. If you discard order with `unordered()`, behavior may differ.

### Mistake 5: Not Handling Duplicate Keys in toMap

~~~java
// With two Users sharing the same id:
// users.stream().collect(Collectors.toMap(User::id, User::name));
// May throw IllegalStateException due to duplicate key.
~~~

Ensure unique keys or pass a merge function, such as picking the record according to a defined timestamp rule.

### Mistake 6: Wrapping the Outer Map and Assuming Nested Data Is Immutable

~~~java
// Map<String, List<Order>> groups = ...
// Collections.unmodifiableMap(groups) only blocks map mutation
// through the wrapper; it does not make each List<Order> immutable.
~~~

If publishing an API that forbids clients from modifying nested structures, create immutable copies of each group and of the outer Map, and watch out for mutable child objects.

### Mistake 7: Comparing Collections with toString When Order Is Not Guaranteed

~~~java
// Do not compare printed strings of HashSet/HashMap to verify value sets.
// Compare Sets with equals, and Maps with equals when order is insignificant.
~~~

For Lists, `List.equals` considers order. For Sets and Maps, `equals` describes element/key-value membership, independent of iteration order.

## 12. Collector Selection Checklist

| Question | If the answer is yes | Suggested choice |
| --- | --- | --- |
| Need an **unmodifiable** List keeping encounter order? | Yes | `Stream.toList()` |
| Need an **unmodifiable** List and **drop null**? | Yes | `filter(Objects::nonNull).toList()` or `toUnmodifiableList()` after filtering |
| Need a modifiable `ArrayList`? | Yes | `toCollection(ArrayList::new)` |
| Need a Set without caring about iteration order? | Yes | `toSet()` or `toUnmodifiableSet()`, per mutability/null policy |
| Need a Set in first-appearance order? | Yes | `toCollection(LinkedHashSet::new)` |
| Need a Set in sorted order? | Yes | `toCollection(TreeSet::new)` with an appropriate comparator |
| Need a mutable Map in insertion order? | Yes | `toMap(..., merge, LinkedHashMap::new)` |
| Need an unmodifiable Map with no null? | Yes | `toUnmodifiableMap(...)` |
| Need grouping with deterministic key order? | Yes | `groupingBy(..., LinkedHashMap::new, downstream)` |
| Could data contain null or duplicate keys? | Yes | Filter, normalize, or model errors and merge policy before terminal |

**Note:** "Need an unmodifiable List and drop null" does not mandate `toUnmodifiableList()` if `filter(...).toList()` already expresses the intent accurately. Conversely, if you want to **detect null as an error**, you can use a null-forbidding collector to fail fast; the application should choose its policy explicitly rather than relying on incidental behavior.

## 13. Self-Check Questions

1. **Does `Stream.toList()` support `add` after collection?** No; mutating operations throw `UnsupportedOperationException`.
2. **Does `Collectors.toList()` guarantee returning a mutable `ArrayList`?** No; neither the List type nor mutability is guaranteed.
3. **What can `Stream.of("A", null).toList()` return?** An unmodifiable List containing `"A"` and `null`.
4. **What happens when `Collectors.toUnmodifiableList()` encounters null?** It throws `NullPointerException`.
5. **Why is `Collectors.toSet()` not used to guarantee display order?** The collector makes no guarantee about the returned Set's iteration order.
6. **If you need to preserve first-appearance order while removing duplicates, what should you use?** `Collectors.toCollection(LinkedHashSet::new)` or `distinct().toList()` if an unmodifiable List is desired.
7. **How does `TreeSet` differ from `LinkedHashSet`?** TreeSet uses comparison order; LinkedHashSet uses insertion order.
8. **What happens when two elements with the same key enter `toMap(keyMapper, valueMapper)`?** The collector throws `IllegalStateException` if no merge policy is supplied.
9. **To get a mutable Map preserving insertion order and resolving duplicates by a defined rule, what should you use?** The overload `toMap(key, value, merge, LinkedHashMap::new)`.
10. **Does `toUnmodifiableMap` allow null in keys or values?** No; both are forbidden.
11. **How does `List.copyOf` differ from `Collections.unmodifiableList(source)`?** The copy does not reflect later structural modifications to the source; the unmodifiable view reflects changes to the backing list.
12. **Is an unmodifiable List containing `StringBuilder` deeply immutable?** No; the contents of the `StringBuilder` can still be mutated.
13. **Does `parallelStream().toList()` preserve a List's encounter order?** Yes, provided the pipeline preserves encounter order.
14. **What should you do if a `groupingBy` classifier could return null?** Filter, normalize, or map it to a fallback key before grouping.
15. **When should you use `Collectors.toCollection`?** When you need exact control over the collection type, mutability, and properties like insertion or sorted order.

**Key takeaway:** Stream outputs should be evaluated by **mutability, ordering, and null policy** as three independent contracts. `Stream.toList()` and `Collectors.toUnmodifiableList()` are both unmodifiable yet have different null policies; `Collectors.toList()`/`toSet()` do not promise mutability; `toCollection` and `toMap` with a supplier let you select concrete structures. When business requirements are clear, choosing an explicit terminal operation reduces runtime errors and keeps pipelines maintainable, even when moving to parallel processing.
