# `toSet()`, `toUnmodifiableList()` and `toUnmodifiableSet()` in Java Stream

When processing a Stream, we often need to **collect elements** into a `List` or `Set`. Three collectors in `java.util.stream.Collectors` are:

- `Collectors.toSet()` — collects into a `Set` to remove duplicate elements; **does not guarantee** the implementation type, iteration order, or mutability of the result.
- `Collectors.toUnmodifiableList()` — collects into a **structurally unmodifiable** `List`, preserves duplicate elements, and preserves *encounter order* when the stream is ordered; **does not allow null**.
- `Collectors.toUnmodifiableSet()` — collects into a **structurally unmodifiable** `Set`, removes duplicate elements, **does not guarantee order**, and **does not allow null**.

They are all **collectors** passed into the **terminal operation** `Stream.collect(...)`. Do not confuse them with `Stream.toList()`, which is a direct terminal method, or with a mutable `Set`.

Example:

~~~java
List<String> words = List.of("pear", "apple", "pear", "banana");

Set<String> a = words.stream().collect(Collectors.toSet());
List<String> b = words.stream().collect(Collectors.toUnmodifiableList());
Set<String> c = words.stream().collect(Collectors.toUnmodifiableSet());
~~~

The snippet requires `import java.util.List;`, `import java.util.Set;`, and `import java.util.stream.Collectors;`, placed inside a method. The result `b` keeps four elements in the exact input order; the two Sets contain three distinct values. However, **do not rely on the output of printing a Set directly to assert order**.

## 1. Context: collector, terminal, and the difference between List and Set

A Stream pipeline typically consists of a source → intermediate operations → terminal operation:

~~~text
List<String> source
       |
       v
source.stream().filter(...).map(...)
       |
       v
collect(Collectors.toUnmodifiableList())  <-- terminal
       |
       v
Unmodifiable List<String> result
~~~

`Collectors.toSet()` **does not** consume a Stream by itself; it returns a `Collector` object describing how to collect. The call `stream.collect(collector)` is the terminal operation that triggers pipeline execution and returns the result.

A few directly relevant differences:

| Criterion | `List<E>` | `Set<E>` |
| --- | --- | --- |
| Duplicate elements by `equals` | Allowed | Not allowed |
| Position and order | Index-ordered | Depends on implementation; `Set` in general makes no guarantee |
| Lookup | `get(index)` | `contains(value)`, no `get(index)` |
| Multiple equal objects | Can coexist | Only one equivalent element is kept |
| Mutability | Depends on object/implementation | Depends on object/implementation |

**List or Set** describes the storage and deduplication contract; **modifiable or unmodifiable** describes the result mutation contract. These two questions are independent: a List can be unmodifiable, a Set can be modifiable — but `Collectors.toSet()` specifically **does not guarantee** that the result is modifiable.

### Encounter order

*Encounter order* is the element order determined by the source and pipeline. `List.stream()` has an encounter order matching the list; `HashSet.stream()` has no such order guarantee.

Collectors for List preserve encounter order on ordered streams according to the appropriate contract. Conversely, `Collectors.toSet()` and `Collectors.toUnmodifiableSet()` are **unordered collectors**, so the iteration order of the resulting Set is not guaranteed to match the input order.

## 2. `Collectors.toSet()` — deduplicates without promising mutability

Usage:

~~~java
Set<String> unique = Stream.of("A", "B", "A")
        .collect(Collectors.toSet());
~~~

The resulting set has two distinct values `A` and `B`. `Set` determines duplication using `equals`. For custom types, design `equals` and `hashCode` consistently so they work with common hash-based structures.

The API contract **does not guarantee**:

1. A specific Set type (`HashSet`, `LinkedHashSet`, `TreeSet`, ...).
2. Iteration order of the result.
3. Mutability of the result.
4. *Serializability* or thread-safety.
5. Whether `null` elements are allowed in every implementation.

On many current JDKs, you may observe that the returned Set supports calling `add(...)`, but **you should not write programs that depend on that implementation detail**. If you want a mutable Set, choose a collector that explicitly specifies the Set type created:

~~~java
Set<String> mutable = words.stream()
        .collect(Collectors.toCollection(HashSet::new));
mutable.add("melon");
~~~

This is an illustrative snippet with `words` and imports `Set`, `HashSet`, `Collectors`; `toCollection(HashSet::new)` creates a `HashSet` using the specified supplier. If you need to preserve encounter order (with an ordered stream), use `LinkedHashSet`:

~~~java
LinkedHashSet<String> insertionOrdered = words.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

`LinkedHashSet` typically iterates in insertion order; this is the explicit choice when iteration in first-appearance order is required, not a property of `toSet()`.

### Type inference

~~~java
Set<Integer> ids = Stream.of(2, 1, 2, 3)
        .collect(Collectors.toSet());
~~~

The collector method infers the type `Integer`. Because `Set` has no index, `ids.get(0)` is invalid. If you need the "first element", you must define an order (or a criterion) before selecting; do not infer "first" from a Set that makes no order guarantee.

## 3. `Collectors.toUnmodifiableList()` — preserves order, preserves duplicates, and forbids modification

Since **Java 10**, `Collectors.toUnmodifiableList()` returns a collector that creates a structurally unmodifiable `List`:

~~~java
List<String> result = Stream.of("A", "B", "A")
        .collect(Collectors.toUnmodifiableList());
// [A, B, A]
~~~

Characteristics:

- **Preserves duplicate elements:** both `"A"` elements remain present.
- **Preserves encounter order:** for an ordered stream, the result follows the encounter order from the pipeline.
- **Unmodifiable:** mutation operations such as `add`, `remove`, or `set` throw `UnsupportedOperationException`.
- **Does not allow null elements:** if the stream provides `null` to the collector, the collect operation throws `NullPointerException`.
- Do not assume the List implementation type, serializability, or other properties not promised by the API.

Example illustrating behavior:

~~~java
List<String> fixed = List.of("a", "b").stream()
        .collect(Collectors.toUnmodifiableList());

// fixed.add("c");  // Compiles, but throws UnsupportedOperationException.
// fixed.set(0, "x"); // Same.
~~~

Unmodifiable is a constraint **on the returned collection**, not a protection for every object referenced inside it. If an element is a mutable object, the element's fields can still be modified; see the section on shallow immutability.

`toUnmodifiableList()` is not an automatic "sort". If you want a specific order, place `sorted(...)` in the pipeline **before** `collect`.

## 4. `Collectors.toUnmodifiableSet()` — unmodifiable and no duplicates

Also since **Java 10**, `Collectors.toUnmodifiableSet()` collects values into a structurally unmodifiable Set:

~~~java
Set<String> codes = Stream.of("A", "B", "A")
        .collect(Collectors.toUnmodifiableSet());
// Contains A and B, iteration order is not guaranteed.
~~~

Key contract:

- Duplicate elements according to `equals` are removed, as in a Set.
- The returned Set is **unmodifiable**; calling `add`, `remove`, etc. throws `UnsupportedOperationException`.
- **`null` is rejected** with `NullPointerException`.
- **Unordered** collector: no guarantee of iterating in encounter order.
- When multiple distinct objects are considered equal by `equals`, an **arbitrary** representative among those equivalent objects may be kept. Do not rely on keeping the "first object".
- Does not use a comparator to determine duplicates: `toUnmodifiableSet()` relies on Set equality rules, not the result of `sorted(comparator)`.

For example, if you need to "take one record per ID" preferring the latest record, `toUnmodifiableSet` **does not know that policy**. Design the representative selection step using `toMap` with an appropriate merge function, and then create the required collection.

### Unmodifiable Set vs. deep immutable

~~~java
List<StringBuilder> builders = Stream.of(new StringBuilder("A"))
        .collect(Collectors.toUnmodifiableList());
builders.get(0).append("B"); // The StringBuilder object is still mutable.
~~~

This snippet is inside a method with imports `Stream`, `Collectors`, `List`. You **cannot replace** elements in the list, but the referenced object can still be modified. For a Set, mutating an element's key in a way that changes `equals/hashCode` can also break lookup consistency. Use immutable elements if you need a stable result set.

## 5. Direct comparison table of the three collectors

| Property | `toSet()` | `toUnmodifiableList()` | `toUnmodifiableSet()` |
| --- | --- | --- | --- |
| Result | `Set<T>` | `List<T>` | `Set<T>` |
| Duplicates | Deduplicates | Preserves duplicates | Deduplicates |
| Result order | Not guaranteed | Follows encounter order if present | Not guaranteed |
| Modifiable result? | **No guarantee** | **No** | **No** |
| `null` in data | **Do not rely on null support** | **Rejected** | **Rejected** |
| Minimum Java | Java 8 | Java 10 | Java 10 |
| Unordered collector? | Yes | No, in the sense of a collector for ordered lists | Yes |
| Use when | Want a Set and need no extra guarantees | Want a read-only List, keeping duplicates and order | Want a read-only Set, without duplicates |

"Read-only"/"unmodifiable" in the table means **does not support modifying the collection**. It **does not claim** that elements are immutable or thread-safe in all cases.

`Collectors.toSet()` is worth using when you only need a Set and have no strict requirements on order/mutability. If the API requirement is "return data without letting callers modify the collection", prefer the appropriate unmodifiable collector. If you need guaranteed mutability or a deterministic iteration order, choose `toCollection(...)` with a specific implementation type.

## 6. Complete Java 17+ example and output verification

Save to **`CollectorChoicesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorChoicesDemo {
    public static void main(String[] args) {
        List<String> source = List.of("pear", "apple", "pear", "banana");

        Set<String> regular = source.stream().collect(Collectors.toSet());
        List<String> immutableList =
                source.stream().collect(Collectors.toUnmodifiableList());
        Set<String> immutableSet =
                source.stream().collect(Collectors.toUnmodifiableSet());

        System.out.println("toSet(sorted for display)=" + regular.stream().sorted().toList());
        System.out.println("toUnmodifiableList=" + immutableList);
        System.out.println("toUnmodifiableSet(sorted for display)="
                + immutableSet.stream().sorted().toList());

        try {
            immutableList.add("melon");
        } catch (UnsupportedOperationException e) {
            System.out.println("listMutation=unsupported");
        }
        try {
            immutableSet.add("melon");
        } catch (UnsupportedOperationException e) {
            System.out.println("setMutation=unsupported");
        }

        List<String> nullable = Arrays.asList("a", null, "b");
        System.out.println("streamToListWithNull=" + nullable.stream().toList());
        try {
            nullable.stream().collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException e) {
            System.out.println("unmodifiableListNull=rejected");
        }
        try {
            nullable.stream().collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException e) {
            System.out.println("unmodifiableSetNull=rejected");
        }

        LinkedHashSet<String> insertionOrdered = source.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        ArrayList<String> mutableList = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        mutableList.add("melon");
        System.out.println("linkedHashSet=" + insertionOrdered);
        System.out.println("mutableList=" + mutableList);
    }
}
~~~

Compile and run commands (JDK 17 or later):

~~~bash
javac CollectorChoicesDemo.java
java CollectorChoicesDemo
~~~

**Exact stdout:**

~~~text
toSet(sorted for display)=[apple, banana, pear]
toUnmodifiableList=[pear, apple, pear, banana]
toUnmodifiableSet(sorted for display)=[apple, banana, pear]
listMutation=unsupported
setMutation=unsupported
streamToListWithNull=[a, null, b]
unmodifiableListNull=rejected
unmodifiableSetNull=rejected
linkedHashSet=[pear, apple, banana]
mutableList=[pear, apple, pear, banana, melon]
~~~

Analysis:

1. `toSet()` removes the duplicate `"pear"`; when printing, the code **explicitly sorts** using `regular.stream().sorted().toList()` so stdout is deterministic. It is not `toSet()` sorting on its own.
2. `toUnmodifiableList()` keeps both `"pear"` values and preserves the source List order.
3. `toUnmodifiableSet()` removes duplicates and forbids modification; the printed output is also sorted separately.
4. `add(...)` on the two unmodifiable collections triggers `UnsupportedOperationException`, which is caught and printed.
5. `nullable.stream().toList()` from Java 16+ can contain `null`. The two unmodifiable collectors here **do not accept null** and throw `NullPointerException`.
6. `toCollection(LinkedHashSet::new)` creates a Set with insertion order from the ordered source; `toCollection(ArrayList::new)` creates a list that is guaranteed to support adding elements.
7. The example **does not call `add(...)` on the result of `Collectors.toSet()`** because that is not guaranteed by the API contract.

The code runs on Java 17, error cases are caught with the exact exception types, and the output has been verified by actual compilation and execution.

## 7. Do not confuse with `Stream.toList()` and `Collectors.toList()`

Three APIs with similar names have different contracts:

~~~java
List<String> a = stream.toList();                              // Java 16+
List<String> b = stream.collect(Collectors.toList());          // Java 8+
List<String> c = stream.collect(Collectors.toUnmodifiableList()); // Java 10+
~~~

**Note:** these are three **alternative usages**, not to be called consecutively on the same consumed `stream` variable. Each terminal operation needs a fresh Stream from the source; the snippet is only for syntax comparison.

| API | Key contract |
| --- | --- |
| `Stream.toList()` | Returns an unmodifiable List; can still contain `null` elements |
| `Collectors.toList()` | Returns a List; **no guarantee** on implementation type, mutability, serializability, or thread-safety |
| `Collectors.toUnmodifiableList()` | Returns an unmodifiable List; **rejects null** |
| `Collectors.toCollection(ArrayList::new)` | Creates a specific `ArrayList` that supports adding/removing |

`Stream.toList()` and `Collectors.toUnmodifiableList()` both disallow modifying the List, but they have **different null policies**. Do not automatically replace one method with the other when the input may contain `null`.

When you need a modifiable return value, an explicit approach:

~~~java
ArrayList<String> editable = source.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

When you want an unmodifiable List and have verified that the data has no nulls, `Collectors.toUnmodifiableList()` is a great fit. There is no need to use `Collections.unmodifiableList(...)` to wrap an already unmodifiable List.

## 8. Null: decide on a data policy

The two unmodifiable collectors from Java 10 **reject `null` elements**. If the source contains `null`, the terminal call may throw `NullPointerException`:

~~~java
List<String> nullable = Arrays.asList("A", null, "B");

// Throws NullPointerException:
nullable.stream().collect(Collectors.toUnmodifiableList());
nullable.stream().collect(Collectors.toUnmodifiableSet());
~~~

This is an illustrative snippet; do not run it without exception handling. If the application has a rule to **discard missing values**:

~~~java
List<String> nonNull = nullable.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());
~~~

This snippet requires importing `java.util.Objects` and `List`. For Set:

~~~java
Set<String> nonNullUnique = nullable.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());
~~~

When `null` data means "input error" or "required field", you should not silently drop it with filter; validate and report the error according to business rules. Another option is `map(s -> s == null ? "<missing>" : s)` when the application has a replacement rule, making sure the marker does not collide with valid values.

**Do not infer in reverse** that `Collectors.toSet()` is a portable way to keep `null`. Some implementations accept null, but the API contract provides no guarantee of that; if the data requires storing null, choose a specific structure that supports it and test the data policy.

## 9. Unmodifiable collection: snapshot or view?

The two unmodifiable collectors **produce a collected result** from Stream elements. After collecting completes, you cannot call operations that structurally modify that List/Set itself. This differs from:

~~~java
List<String> backing = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(backing);
backing.add("C");
// view also sees "C" because it is a view wrapping the backing list.
~~~

This snippet requires importing `java.util.List`, `java.util.ArrayList`, `java.util.Collections`. `Collections.unmodifiableList(...)` creates an *unmodifiable view*; modifying the underlying collection through another reference is still visible through the view.

In contrast, `Collectors.toUnmodifiableList()` builds a collected result and provides no mechanism for the caller to later mutate that collection. However, **mutable element objects are still referenced**, without automatically deep-copying the entire data graph.

`List.copyOf(collection)` and `Set.copyOf(collection)` also create unmodifiable results from an existing collection, rejecting null. When the source is already an unmodifiable collection, the implementation may reuse the object instead of making a physical copy; do not rely on identity difference (`==`) to determine a "copy". `Set.copyOf` deduplicates and may keep any representative if elements are equal.

### Shallow immutability and thread safety

~~~java
List<StringBuilder> values = Stream.of(new StringBuilder("start"))
        .collect(Collectors.toUnmodifiableList());
values.get(0).append("-changed"); // Modifies the StringBuilder itself.
~~~

You cannot add/remove elements in `values`, but you can modify the contents of the `StringBuilder`. If an API returns sensitive datasets, use immutable values (such as `String` or records with appropriate immutable fields), or create defensive copies according to the specific contract.

Unmodifiable does not automatically make all operations on elements thread-safe. Do not share a mutable object across threads without proper synchronization just because it is inside an unmodifiable List.

## 10. Duplicate data, `equals`, and representative selection policy

For `Set`, two elements that are equivalent based on `equals` are treated as one entry. This differs from how `Comparator` evaluates order.

Example:

~~~java
record Product(String id, int version) {}

List<Product> products = List.of(
        new Product("A", 1),
        new Product("A", 2),
        new Product("A", 1)
);

Set<Product> items = products.stream()
        .collect(Collectors.toUnmodifiableSet());
// Set contains Product("A",1) and Product("A",2).
~~~

This is an illustrative snippet inside a class with a Java 17 record and imports `List`, `Set`, `Collectors`. By default, a record compares both `id` and `version`; therefore two Products with the same `id` but different `version` are **not duplicates** according to `equals`.

If the requirement is "one Product per id, preferring the highest version", using only a Set is not enough to express it:

~~~java
Map<String, Product> newestById = products.stream().collect(
        Collectors.toMap(
                Product::id,
                Function.identity(),
                BinaryOperator.maxBy(Comparator.comparingInt(Product::version))
        )
);
~~~

This snippet requires `Map`, `Collectors`, `Function`, `BinaryOperator`, `Comparator`, and the `products` variable from the example above. `toMap` with a merge function expresses the record selection policy; afterwards you can collect the values into a Set/List if needed. Note that iterating over `Map.values()` also does not guarantee order unless an appropriately ordered map is used.

**Key takeaway:** `toUnmodifiableSet` may keep any representative from equal elements, not necessarily the first one encountered. If the "first record" or "best record" matters, express the representative selection logic in an earlier step rather than expecting the collector to make your desired choice.

## 11. Parallelism, order, and cost

In a parallel stream, a collector is executed through partial accumulation steps followed by combining. `toSet()` and `toUnmodifiableSet()` are unordered collectors, so you cannot rely on insertion/iteration order of the result. `toUnmodifiableList()` preserves encounter order when the source is ordered, even when the pipeline runs in parallel.

Do not conclude that **unordered is always faster**, or that Set is always more efficient than List. Cost depends on:

- Number of elements, number of distinct values, and the cost of `equals/hashCode`.
- Storage/resizing cost of the underlying collection implementation.
- Coordination and combining cost of intermediate containers in a parallel stream.
- Requirements to maintain encounter order and the likelihood of hash collisions.

If you need to keep all elements and order, choose List. If you only need membership of unique values, choose Set. If you want a Set to display stably, **sort when outputting the result**:

~~~java
List<String> sortedValues = uniqueSet.stream()
        .sorted()
        .toList();
~~~

This is an illustrative snippet with an existing `Set<String> uniqueSet`. The code does not claim `uniqueSet` sorts itself; it simply creates a sorted List from the Set's contents. If you want a **Set with insertion order**, explicitly choose `LinkedHashSet`; if you want a Set ordered by a comparator, choose `TreeSet` and be aware that its duplicate policy is based on comparator `compare == 0`, which may differ from `equals`.

## 12. Common mistakes

### Thinking `toSet()` always returns a mutable `HashSet`

Wrong at the API contract level: there is no guarantee of Set type or mutability. When explicit mutability is needed: `Collectors.toCollection(HashSet::new)`. When insertion order is needed: `Collectors.toCollection(LinkedHashSet::new)`.

### Thinking `toUnmodifiableList()` automatically removes duplicates

It keeps duplicates because it is a List. If you want unique elements while still having a List in first-appearance order, add a deduplication step, for example:

~~~java
List<String> uniqueList = source.stream()
        .distinct()
        .collect(Collectors.toUnmodifiableList());
~~~

With an ordered List `source`, `distinct` keeps the first element by `equals`, and the resulting List preserves encounter order. This differs from `toUnmodifiableSet()`, which does not guarantee Set iteration order.

### Relying on the direct print order of a Set

~~~java
Set<String> result = source.stream().collect(Collectors.toUnmodifiableSet());
// Not guaranteed: System.out.println(result) prints in input order.
~~~

If order matters for reports/tests, use `result.stream().sorted().toList()` or choose a structure with deterministic order as required. Do not write tests comparing against the literal `Set.toString()` of an unordered Set.

### Confusing the null policy of collectors and `Stream.toList()`

`Stream.toList()` can contain `null`, whereas `Collectors.toUnmodifiableList()` and `toUnmodifiableSet()` reject null. If switching APIs for optimization or style, check the source data and output contract.

### Thinking unmodifiable means deep immutable

You cannot `add/remove/set` elements, but a `StringBuilder` or mutable object inside can still be modified. Design immutable elements or defensive copies if deeply immutable data is needed.

### Thinking Set deduplicates by comparator

`toSet()` and `toUnmodifiableSet()` do not accept a comparator; uniqueness depends on `equals`. `sorted(comparator)` only changes order, not the Set's equality rules.

### Assuming concurrent modification of source data is always safe

Stream pipelines are not designed for arbitrarily mutating the source during traversal. With parallel streams, do not use side-effect operations on external collections without synchronization. Collect results using an appropriate Collector and maintain non-interference.

### Reusing a Stream after collect

~~~java
Stream<String> once = source.stream();
List<String> list = once.collect(Collectors.toUnmodifiableList());
// Wrong: once has already been consumed.
// Set<String> set = once.collect(Collectors.toUnmodifiableSet());
~~~

To get two results, create two new Streams from the source or design a combined collection operation when there is a clear reason and contract.

## 13. Choosing a collector by business requirement

| Requirement | Appropriate expression |
| --- | --- |
| Only need a set of unique values, no order/mutability requirement | `collect(Collectors.toSet())` |
| Want an unmodifiable List, preserving order/duplicates, no null | `collect(Collectors.toUnmodifiableList())` |
| Want an unmodifiable Set, deduplicated, no null | `collect(Collectors.toUnmodifiableSet())` |
| Want an explicitly mutable List | `collect(Collectors.toCollection(ArrayList::new))` |
| Want an explicitly mutable Set | `collect(Collectors.toCollection(HashSet::new))` |
| Want a Set in encounter order from an ordered source | `collect(Collectors.toCollection(LinkedHashSet::new))` |
| Want an unmodifiable List directly and null may be present | `stream.toList()` (Java 16+) |
| Want a unique list preserving first-appearance order | `stream.distinct().collect(Collectors.toUnmodifiableList())` |
| Want to select a representative record by key | `toMap(key, value, merge)` with an explicit policy |

**In summary:** choosing a collector should be based on **the target structure (List/Set), duplicate policy, order, null handling, and mutability**. `Collectors.toSet()` does not promise mutability; `toUnmodifiableList()` preserves duplicates and encounter order but rejects null; `toUnmodifiableSet()` removes duplicates, is unmodifiable, does not guarantee order, and rejects null. When you have other requirements, use an explicit collector/collection instead of relying on incidental behavior of the running JDK.