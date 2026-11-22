# Keeping equals, hashCode, Views, and Default Methods Consistent

## 1. A Data Structure Has Multiple Paths into the Same State

Suppose you write a list that only accepts non-negative numbers. `add(-1)` is blocked. However, a caller can still invoke `listIterator().set(-1)`, `subList(...).set(...)`, or `replaceAll(...)`. If an update path bypasses validation, the invariant "every element is non-negative" no longer holds.

With maps, the issue is even easier to obscure: you validate inside `put`, yet a returned `Map.Entry` object may allow calling `setValue` directly. Certain default methods rely on this exact path.

Beyond that, the structure must also interoperate with other implementations of the same interface. A custom `List` containing the same elements in the same order must satisfy the equality and hash code relationships expected by `ArrayList` or `LinkedList`. You cannot simply compare two instances of the same concrete class and conclude that the contract is satisfied.

This article focuses on four interconnected concerns:

1. **`equals`:** Which two states are considered equal?
2. **`hashCode`:** Do equal states produce compatible hash codes?
3. **Views:** Which objects read and mutate the same backing data?
4. **Default and inherited methods:** Through which underlying operations do built-in algorithms update data?

An **invariant** is a condition you want to maintain after every supported operation—for instance, no duplicate elements, non-negative values, or preventing mutation through a read-only interface. Maintaining consistency means every observation and update path respects the same contract, including paths whose code you did not explicitly write in your subclass.

The mental model to use:

```text
Direct calls ───────────────────┐
Iterator / ListIterator ────────┤
Views ──────────────────────────┼─→ actual update operation
Default / inherited methods ────┘       ↓
                              shared data and invariants
                                        ↓
                          equals / hashCode / observation
```

The goal is to trace these paths, not to mechanically override every method. Three programs will sequentially verify equality contracts, a list with views, and a map with validated update entry points.

## 2. equals and hashCode Must Match the Interface Semantics

### 2.1. The Base Contract of Object

According to [Object.equals and Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), equality must be reflexive, symmetric, transitive, and consistent while relevant data remains unchanged; any non-`null` object must return `false` when compared against `null`.

The resulting requirement for hash codes is:

```text
a.equals(b) == true  ⇒  a.hashCode() == b.hashCode()
```

The converse is not required to hold. Two distinct objects may share the same hash code. If you treat equal `hashCode` values as proof that `equals` is `true`, you turn a valid hash collision into a comparison bug.

You do not need to reimplement both methods in every class. However, whenever you customize the `equals` rule, you must maintain a matching `hashCode` rule. If a base class already provides the exact collection contract you need, keeping that implementation is usually less risky than rewriting it yourself.

### 2.2. Holding Elements Does Not Automatically Mean Using the Same Equality Rule

| API Type | Content Equality Condition | Required Compatible Hash Code |
| --- | --- | --- |
| `List` | The other object is also a `List`, has the same length, and each pair at the same index is equal | Accumulated in order starting from 1, multiplying by 31 at each step and adding the element's hash code. |
| `Set` | The other object is also a `Set` containing the same elements, regardless of order | Sum of the hash codes of its elements. |
| `Map` | The other object is also a `Map` containing the same key–value mappings | Sum of the hash codes of the entries in `entrySet`. |
| `Map.Entry` | The other object is also an `Entry` with equal keys and equal values | Key hash code XOR value hash code. |
| `Collection` other than `List`/`Set` | No general content-comparison rule is automatically imposed | Keep the `Object` contract or a properly designed custom contract. |

In element formulas, `null` contributes 0. Hash code calculations using `int` may overflow according to Java integer arithmetic; do not alter the standard formula merely because the sum exceeds a large positive value.

The exact specifications are found in [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html), and [Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

A list is not equal to a set just because both print `[A, B]`. Order and multiplicity belong to list semantics, whereas a set contains no duplicate elements and does not use order to determine equality.

If your custom class implements `List`, do not restrict `equals` with a "must be the exact same concrete class as mine" check. Doing so can cause your class to reject equality with a standard list while the standard list accepts equality with yours. Symmetry breaks even though the underlying data is identical.

For an ordinary value type that does not implement these collection interfaces, choosing which class hierarchy is eligible for equality is an independent design decision. Here, the public interface contract already mandates interoperability across implementations.

### 2.3. Cross-Implementation Verification Program

`Words` is a small read-only list backed by a cloned array that inherits equality and hash code behavior from `AbstractList`. The program also tests sets, maps, and map entries across different concrete classes.

Save as `EqualityContractsDemo.java`:

```java
import java.util.AbstractList;
import java.util.AbstractMap;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

public class EqualityContractsDemo {
    public static void main(String[] args) {
        List<String> custom = new Words("A", "B");
        List<String> standard = Arrays.asList("A", "B");
        System.out.println("list equality both ways = "
                + (custom.equals(standard) && standard.equals(custom)));
        System.out.println("list hash agrees = "
                + (custom.hashCode() == standard.hashCode()));
        System.out.println("reordered list equals = " + custom.equals(List.of("B", "A")));

        Set<String> firstSet = new LinkedHashSet<>(List.of("A", "B"));
        Set<String> secondSet = new HashSet<>(List.of("B", "A"));
        System.out.println("set equality = " + firstSet.equals(secondSet));
        System.out.println("set hash agrees = "
                + (firstSet.hashCode() == secondSet.hashCode()));
        System.out.println("list equals set = " + custom.equals(firstSet));

        Map<String, Integer> firstMap = new HashMap<>(Map.of("A", 1, "B", 2));
        Map<String, Integer> secondMap = new TreeMap<>(Map.of("B", 2, "A", 1));
        System.out.println("map equality = " + firstMap.equals(secondMap));
        System.out.println("map hash agrees = "
                + (firstMap.hashCode() == secondMap.hashCode()));

        Map.Entry<String, Integer> entry = Map.entry("A", 3);
        Map.Entry<String, Integer> copied =
                new AbstractMap.SimpleImmutableEntry<>("A", 3);
        System.out.println("entry equality both ways = "
                + (entry.equals(copied) && copied.equals(entry)));
        int requiredHash = Objects.hashCode(entry.getKey())
                ^ Objects.hashCode(entry.getValue());
        System.out.println("entry XOR hash agrees = " + (entry.hashCode() == requiredHash));
        System.out.println("Objects.hash pair agrees = "
                + (entry.hashCode() == Objects.hash("A", 3)));

        CollisionKey one = new CollisionKey(1);
        CollisionKey two = new CollisionKey(2);
        System.out.println("collision has same hash = " + (one.hashCode() == two.hashCode()));
        System.out.println("collision keys equal = " + one.equals(two));
        System.out.println("collision set size = " + Set.of(one, two).size());
    }

    private static final class Words extends AbstractList<String> {
        private final String[] data;

        private Words(String... words) {
            data = words.clone();
        }

        @Override
        public String get(int index) {
            Objects.checkIndex(index, data.length);
            return data[index];
        }

        @Override
        public int size() {
            return data.length;
        }
    }

    private record CollisionKey(int value) {
        @Override
        public int hashCode() {
            return 0;
        }
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all EqualityContractsDemo.java
java EqualityContractsDemo
```

Output:

```text
list equality both ways = true
list hash agrees = true
reordered list equals = false
set equality = true
set hash agrees = true
list equals set = false
map equality = true
map hash agrees = true
entry equality both ways = true
entry XOR hash agrees = true
Objects.hash pair agrees = false
collision has same hash = true
collision keys equal = false
collision set size = 2
```

### 2.4. What Each Group of Results Proves

For lists, comparison in both directions returns `true` and the hash codes match. When the order is reversed, equality becomes `false`. `Words` does not define a separate `equals` implementation that breaks interoperability.

For sets and maps, differing construction orders do not alter equality. Do not rely on the iteration order of `HashMap` or `HashSet` when printing output; the program prints only deterministic boolean and integer evaluations.

For `Map.Entry`, the XOR formula is verified directly. `Objects.hash("A", 3)` is not a drop-in replacement for `Entry.hashCode()`: it computes a combined hash code differently. The concrete example yields different values; never assume two formulas are equivalent simply because both take a key and a value.

`CollisionKey` intentionally returns a hash code of 0 for every value. Two keys with different values remain unequal and are both retained in the set. This illustrates a high-collision hash function that still satisfies the "equal objects must have equal hash codes" rule. It can degrade performance in hash-based structures, but it is not a valid reason to treat two distinct objects as identical.

### 2.5. Mutable State Changes Comparison Results

A collection's hash code can change whenever its elements, order, or mappings change. Therefore, do not compute a hash code once and cache it permanently while the underlying data remains mutable. Even a structural modification counter is insufficient: replacing a value via `set` may keep the size unchanged while still altering a list's hash code.

Similarly, keys in a map or elements in a set must be handled with care if fields participating in `equals` remain mutable. The [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) and [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) contracts leave behavior unspecified if such a mutation alters equality while the object is stored. Avoid claiming that "after mutation, `contains` is guaranteed to return `false`"; that over-specifies behavior for a state that has already violated the contract.

If an identifying value must change, a clean approach is to remove the object under its old state first, construct or update the new value appropriately, and reinsert it according to your domain policy. Using immutable value keys helps minimize this hazard.

For sorted structures, you must also consider the relationship `compare(a, b) == 0`. If this relationship is inconsistent with `equals`, the structure may treat two elements as duplicates under comparison while the objects themselves report being unequal. [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) explains how this affects `Set` and `Map` contracts. Do not add case-insensitivity or key normalization in only a handful of methods and assume all lookups, removals, equality checks, and hash codes will automatically stay consistent.


## 3. Views Share Data, Not Just Types

### 3.1. Three Relationships to Distinguish

| Returned Object | Tracks Structural/Content Changes in Backing Store? | Allows Mutation Through This Object? |
| --- | --- | --- |
| Mutable view such as `subList` | Coupled to the backing list within the scope of its usage contract | Yes, if supported by the backing list and the corresponding operation. |
| Unmodifiable view such as `Collections.unmodifiableList` | Read queries delegating to the backing list observe valid changes made to the backing list | Disallows mutation through the view itself. |
| Structural copy such as `List.copyOf` | Does not reflect subsequent structural changes to the source collection | Disallows mutation of the returned list. |

"Unmodifiable" describes the capability of an access path. It does not mean the backing data cannot change through another reference. Likewise, a "copy" does not automatically mean a deep copy of every element object.

[Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) and [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) are two distinct APIs that must be read separately. `List.copyOf` rejects `null` elements; it is not an unconditional substitute for a defensive copy whose policy permits `null`.

If you implement a method documented as returning a view but actually return a disconnected copy, callers will have wrong expectations about updates. Conversely, returning the raw backing store when a copy was promised allows unintended mutations to leak back into the original structure.

### 3.2. A Policy Must Hold Across Every List Mutation Path

For a non-negative list, trace the update paths:

```text
addAll(...)               → adds each element → add(index, value)
ListIterator.add(value)   → add(index, value)
ListIterator.set(value)   → set(index, value)
subList(...).set(...)     → set at the corresponding index in the backing list
List.replaceAll(...)      → ListIterator.set(...) in the default implementation
List.sort(...)            → writes sorted results back via the iterator in the default implementation
removeIf(...)             → Iterator.remove() in the default implementation
```

This is the call map for a list built on a skeletal abstract class that does not override those algorithms. Other concrete classes may override them, so whenever you optimize or write a wrapper class, you must inspect the actual implementation.

Be precise with Java terminology:

- `Collection.removeIf`, `List.replaceAll`, and `List.sort` are `default` methods declared on interfaces.
- A method like `addAll` inherited from an abstract class is a concrete method on a superclass; it does not become an interface `default` method merely because you did not write it yourself.

Both categories can call back into operations on your class. Consequently, invariant checks must cover both default interface methods and inherited superclass methods.

### 3.3. Program: Non-Negative List, Views, and Built-In Algorithms

`NonNegativeList` accepts non-`null` `Integer` values greater than or equal to 0. It maintains its own private storage, validates inside `add(int, Integer)` and `set(int, Integer)`, supports removal, and records structural modifications for the inherited machinery.

Save as `ViewsAndDefaultsDemo.java`:

```java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.RandomAccess;

public class ViewsAndDefaultsDemo {
    public static void main(String[] args) {
        NonNegativeList list = new NonNegativeList();
        list.addAll(List.of(1, 2, 3, 4));
        List<Integer> readOnlyView = Collections.unmodifiableList(list);
        List<Integer> snapshot = List.copyOf(list);
        List<Integer> middle = list.subList(1, 3);

        middle.set(0, 20);
        list.replaceAll(value -> value * 2);
        System.out.println("after view set and replaceAll = " + list);
        middle.clear();
        System.out.println("after subList clear = " + list);
        System.out.println("read-only view = " + readOnlyView);
        System.out.println("snapshot = " + snapshot);

        list.removeIf(value -> value > 5);
        list.addAll(List.of(5, 3));
        list.sort(Comparator.reverseOrder());
        System.out.println("after removeIf and sort = " + list);
        expect("negative replaceAll", IllegalArgumentException.class,
                () -> list.replaceAll(value -> -value));
        ListIterator<Integer> cursor = list.listIterator();
        cursor.next();
        expect("negative iterator set", IllegalArgumentException.class,
                () -> cursor.set(-1));
        expect("read-only add", UnsupportedOperationException.class,
                () -> readOnlyView.add(6));
        System.out.println("after rejected changes = " + list);
        System.out.println("updated read-only view = " + readOnlyView);
    }

    private static final class NonNegativeList
            extends AbstractList<Integer> implements RandomAccess {
        private final List<Integer> data = new ArrayList<>();

        @Override
        public Integer get(int index) {
            return data.get(index);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public Integer set(int index, Integer value) {
            Objects.checkIndex(index, data.size());
            check(value);
            return data.set(index, value);
        }

        @Override
        public void add(int index, Integer value) {
            if (index < 0 || index > data.size()) {
                throw new IndexOutOfBoundsException("index: " + index);
            }
            check(value);
            data.add(index, value);
            modCount++;
        }

        @Override
        public Integer remove(int index) {
            Integer previous = data.remove(index);
            modCount++;
            return previous;
        }

        private static void check(Integer value) {
            Objects.requireNonNull(value, "value");
            if (value < 0) {
                throw new IllegalArgumentException("nonnegative value required");
            }
        }
    }

    private static void expect(String label, Class<? extends RuntimeException> type,
                               Runnable action) {
        try {
            action.run();
            throw new AssertionError("operation unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ViewsAndDefaultsDemo.java
java ViewsAndDefaultsDemo
```

Output:

```text
after view set and replaceAll = [2, 40, 6, 8]
after subList clear = [2, 8]
read-only view = [2, 8]
snapshot = [1, 2, 3, 4]
after removeIf and sort = [5, 3, 2]
negative replaceAll -> IllegalArgumentException
negative iterator set -> IllegalArgumentException
read-only add -> UnsupportedOperationException
after rejected changes = [5, 3, 2]
updated read-only view = [5, 3, 2]
```

### 3.4. Which Updates Passed Through Validation?

`middle` initially spans indices 1 and 2 of the list. `middle.set(0, 20)` updates the backing list to `[1, 20, 3, 4]`. `replaceAll(value -> value * 2)` invokes the underlying replacement operations and yields `[2, 40, 6, 8]`.

Next, `middle.clear()` removes that range, leaving `[2, 8]`. The read-only view observes this exact state, whereas `snapshot` retains `[1, 2, 3, 4]`. No copying behavior is inferred from variable names; the difference comes strictly from the APIs used to construct each object.

Subsequently, `removeIf` removes 8, and the list receives 5 and 3. `sort` reorders the elements to `[5, 3, 2]`. In this example, the values remain valid, so writing them back via `set` preserves the invariant.

Both attempts to write negative values fail:

- `replaceAll` produces a negative result on the very first element, which `set` rejects.
- `ListIterator.set(-1)` likewise passes through the validated `set` method.

Crucially, neither caller needs to know about a custom application-specific validation method. Because they route through the same fundamental operation, they enforce the exact same policy. Meanwhile, the read-only view rejects its own `add` call while continuing to reflect valid modifications performed on the backing list.

In this class, `set` does not change the list's size and does not increment `modCount`; successful additions and removals increment it once. This design matches an illustrative implementation relying on inherited iterators. Do not assume that every other `List` implementation—especially one that overrides `sort` or its iterators—must track modifications in the exact same way.

### 3.5. subList Is an Index Range, Not an Identity-Bound Group of Elements

A list view maps indices and ranges onto the backing store. It does not promise to "follow the exact same two initial element instances" when you replace contents or reorder positions.

After a structural modification to the backing list outside the view, do not continue using the old `subList` as though it automatically resynchronizes itself. [List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)) specifies undefined semantics when the backing list is structurally modified other than via the returned sublist. An implementation may throw `ConcurrentModificationException` to detect this, but the exception is not a protocol for refreshing the range.

The demonstration program stops using `middle` right after clearing the range through it. Subsequent structural modifications happen on the main list and are observed only through the full-list read-only view, never through the stale `subList`.

### 3.6. Making the Container Unmodifiable Does Not Make Contained Objects Immutable

In the example above, the elements are `Integer` instances, which expose no mutator methods on their numeric value. If elements are mutable objects, however, a view that blocks adding or removing elements will still hand references to those mutable objects back to callers.

The same principle applies to a collection of `Map.Entry` objects that support `setValue`. Wrapping an entry set with `Collections.unmodifiableSet` alone does not make the entries inside it immutable. An entry can still write through to the underlying map as long as it retains its live connection to the backing store.

When you need a read-only map, using [Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)) properly enforces the read-only policy across the map's views as well. If you write a custom wrapper, you must guard both the container and any write-through capability on returned objects.

Furthermore, do not assume every `Collection` wrapper delegates content-based equality. `Collections.unmodifiableCollection` uses `Object.equals` and `Object.hashCode`, whereas the specialized wrappers for `List` and `Set` preserve their respective interface semantics. Choose the wrapper API that matches your required semantics and read its contract rather than relying on a blanket assumption for all wrappers.


## 4. Map: put Is Not the Only Update Entry Point

### 4.1. Three Views Must Describe the Same Map

A `Map` exposes three primary views:

| View | Visible Data | What Does Removing an Element Mean? |
| --- | --- | --- |
| `keySet()` | Keys | Removes the mapping for the corresponding key. |
| `values()` | Values (may contain duplicates) | Removes the mapping corresponding to the removed value occurrence. |
| `entrySet()` | Key–value pairs | Removes the mapping matching both the key and value of the entry. |

These are backed views, not arbitrary detached copies. When removal is supported, removing elements through them must write through to the map. Standard map views do not support addition via `add` or `addAll`; a standalone key or standalone value does not fully specify a key–value mapping to insert.

`values()` is not a `Set`: two distinct keys can map to the same value. Calling `values().remove(v)` does not remove every mapping with value `v`; if you want to filter out all entries matching a predicate, use an operation designed for that purpose, such as `removeIf`.

For `entrySet().contains` or `entrySet().remove`, you must not compare only the key while ignoring the value. An entry `A=10` is not equal to `A=20` even though they share the same key.

The authoritative contract is documented under [Map views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html). How a skeletal base class constructs them can be explored further in [AbstractMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

### 4.2. Trace the Algorithms Before Placing Validation Checks

For a subclass of `AbstractMap` relying on default interface methods, the critical execution paths include:

```text
putAll(...)                          → put(...) for each mapping
putIfAbsent / replace                → reads state, then calls put(...) when needed
compute / computeIfAbsent / merge    → computes result, then calls put/remove when needed
Map.replaceAll(...)                  → entrySet() → Entry.setValue(...)
keySet / values / entrySet removal   → removal path supported by the view
```

In this setup, `putAll` is an inherited method on `AbstractMap`, whereas `compute`, `merge`, and `replaceAll` are `default` methods on `Map`. Keep the two concepts distinct when reading code.

The easiest path to overlook is `replaceAll`: its default implementation is not required to call your `put` method for each computed result. Instead, it updates entries via `Entry.setValue`. If `entrySet` exposes raw entries directly from the backing store, validation inside `put` can be bypassed.

Therefore, a "map that only stores non-negative numbers" must guard at least two public write channels: `put` and `Entry.setValue`. Removal paths can remain supported because removing a mapping cannot introduce a negative number.

### 4.3. Program: A Map Validating Both put and Entries

`ScoreMap` below uses a `LinkedHashMap` internally so iteration order in the demonstration remains deterministic. It forbids `null` keys, `null` values, and negative values, while still permitting removals through its views.

The core mechanism lies in `checked`: every returned entry is wrapped so that `setValue` is validated while still faithfully implementing `Map.Entry`'s `equals` and `hashCode` contracts. The backing map is never exposed directly.

Save as `CheckedMapDemo.java`:

```java
import java.util.AbstractMap;
import java.util.AbstractSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Map.Entry;
import java.util.Objects;
import java.util.Set;

public class CheckedMapDemo {
    public static void main(String[] args) {
        ScoreMap<String> scores = new ScoreMap<>();
        scores.put("A", 10);
        scores.put("B", 20);
        System.out.println("initial = " + scores);
        Map<String, Integer> reference = Map.of("A", 10, "B", 20);
        System.out.println("map equality both ways = "
                + (scores.equals(reference) && reference.equals(scores)));
        System.out.println("map hash agrees = " + (scores.hashCode() == reference.hashCode()));
        expect("negative put", IllegalArgumentException.class, () -> scores.put("X", -1));
        expect("negative compute", IllegalArgumentException.class,
                () -> scores.compute("A", (key, value) -> -1));
        expect("negative replace", IllegalArgumentException.class,
                () -> scores.replace("A", -2));
        scores.compute("A", (key, value) -> value + 5);
        scores.merge("B", 3, Integer::sum);
        scores.putIfAbsent("C", 7);
        System.out.println("after compute merge putIfAbsent = " + scores);

        Iterator<Entry<String, Integer>> cursor = scores.entrySet().iterator();
        Entry<String, Integer> first = cursor.next();
        Entry<String, Integer> standard = Map.entry("A", 15);
        System.out.println("entry equality agrees = "
                + (first.equals(standard) && standard.equals(first)));
        System.out.println("entry hash agrees = " + (first.hashCode() == standard.hashCode()));
        expect("negative entry setValue", IllegalArgumentException.class,
                () -> first.setValue(-3));
        System.out.println("entry previous value = " + first.setValue(16));
        scores.replaceAll((key, value) -> value + 1);
        System.out.println("after replaceAll = " + scores);

        scores.values().removeIf(value -> value >= 20);
        scores.keySet().remove("C");
        System.out.println("after view removals = " + scores);
        expect("keySet add", UnsupportedOperationException.class,
                () -> scores.keySet().add("X"));
        scores.computeIfPresent("A", (key, value) -> null);
        System.out.println("after null compute result = " + scores);
        expect("null put", NullPointerException.class, () -> scores.put("N", null));

        Map<String, Integer> updates = new LinkedHashMap<>();
        updates.put("D", 4);
        updates.put("E", -1);
        expect("partly applied putAll", IllegalArgumentException.class,
                () -> scores.putAll(updates));
        System.out.println("after rejected putAll = " + scores);

        ScoreMap<String> partial = new ScoreMap<>();
        partial.put("A", 1);
        partial.put("B", 2);
        expect("partly applied replaceAll", IllegalArgumentException.class,
                () -> partial.replaceAll((key, value) -> key.equals("B") ? -1 : value + 10));
        System.out.println("after rejected replaceAll = " + partial);
    }

    private static final class ScoreMap<K> extends AbstractMap<K, Integer> {
        private final Map<K, Integer> data = new LinkedHashMap<>();
        private final Set<Entry<K, Integer>> entries = new AbstractSet<>() {
            @Override
            public int size() {
                return data.size();
            }

            @Override
            public Iterator<Entry<K, Integer>> iterator() {
                Iterator<Entry<K, Integer>> delegate = data.entrySet().iterator();
                return new Iterator<>() {
                    @Override
                    public boolean hasNext() {
                        return delegate.hasNext();
                    }

                    @Override
                    public Entry<K, Integer> next() {
                        return checked(delegate.next());
                    }

                    @Override
                    public void remove() {
                        delegate.remove();
                    }
                };
            }
        };

        @Override
        public Integer put(K key, Integer value) {
            Objects.requireNonNull(key, "key");
            check(value);
            return data.put(key, value);
        }

        @Override
        public Set<Entry<K, Integer>> entrySet() {
            return entries;
        }

        private Entry<K, Integer> checked(Entry<K, Integer> delegate) {
            return new Entry<>() {
                @Override
                public K getKey() {
                    return delegate.getKey();
                }

                @Override
                public Integer getValue() {
                    return delegate.getValue();
                }

                @Override
                public Integer setValue(Integer value) {
                    check(value);
                    return delegate.setValue(value);
                }

                @Override
                public boolean equals(Object other) {
                    return other instanceof Entry<?, ?> entry
                            && Objects.equals(getKey(), entry.getKey())
                            && Objects.equals(getValue(), entry.getValue());
                }

                @Override
                public int hashCode() {
                    return Objects.hashCode(getKey()) ^ Objects.hashCode(getValue());
                }

                @Override
                public String toString() {
                    return getKey() + "=" + getValue();
                }
            };
        }

        private static void check(Integer value) {
            Objects.requireNonNull(value, "value");
            if (value < 0) {
                throw new IllegalArgumentException("nonnegative value required");
            }
        }
    }

    private static void expect(String label, Class<? extends RuntimeException> type,
                               Runnable action) {
        try {
            action.run();
            throw new AssertionError("operation unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all CheckedMapDemo.java
java CheckedMapDemo
```

Output:

```text
initial = {A=10, B=20}
map equality both ways = true
map hash agrees = true
negative put -> IllegalArgumentException
negative compute -> IllegalArgumentException
negative replace -> IllegalArgumentException
after compute merge putIfAbsent = {A=15, B=23, C=7}
entry equality agrees = true
entry hash agrees = true
negative entry setValue -> IllegalArgumentException
entry previous value = 15
after replaceAll = {A=17, B=24, C=8}
after view removals = {A=17}
keySet add -> UnsupportedOperationException
after null compute result = {}
null put -> NullPointerException
partly applied putAll -> IllegalArgumentException
after rejected putAll = {D=4}
partly applied replaceAll -> IllegalArgumentException
after rejected replaceAll = {A=11, B=2}
```

### 4.4. Which Paths Do the Two Validation Points Cover?

At the start of the program, the custom map equals the reference map in both directions and produces the same hash code. This verifies true interoperability rather than merely formatting an output string that looks like a map.

Three attempts to write negative values via `put`, `compute`, and `replace` are all rejected. The latter two methods delegate to the validated `put` operation whenever they need to store a result. Valid computations then update A to 15, B to 23, and insert C with 7.

An entry for A is retrieved during iteration. It equals `Map.entry("A", 15)` in both directions and produces a matching hash code. Calling `setValue(-3)` fails, whereas `setValue(16)` succeeds and returns the previous value 15.

The subsequent `replaceAll` call iterates over the checked entries, updating the map to `{A=17, B=24, C=8}`. Had `entrySet` exposed raw backing entries without wrapping them, `replaceAll` would have been an open backdoor capable of inserting invalid values without ever calling `put`.

Removals through views demonstrate write-through back to the map: `values().removeIf(...)` removes mapping B, and `keySet().remove("C")` removes C. `keySet().add("X")` is rejected because a standalone key cannot synthesize a mapped value.

`computeIfPresent` returns `null` for A, causing A to be removed. That differs from `put("N", null)`, which attempts to store a forbidden `null` value and is rejected with `NullPointerException`.

### 4.5. Why Must the Entry Wrapper Preserve Both Read and Equality Contracts?

If an entry wrapper intercepts `setValue` but inherits `Object.equals` and `Object.hashCode`, `entrySet` no longer behaves properly as a set of mappings. Map equality and hash code calculations inherited from `AbstractMap` can break as a consequence.

`checked` uses the current key and value of the underlying entry to accomplish three things:

- Return the live data of the mapping currently being iterated.
- Compare keys and values according to the `Map.Entry` contract, even when compared against an entry of a different concrete class.
- Compute the required XOR hash code rather than relying on the wrapper object's identity.

The wrapper entry should not be treated as a permanent update handle. [Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html) restricts the validity of an entry obtained from an `entrySet` view to the progress of the iteration and leaves behavior unspecified if the backing map is modified outside supported entry operations. Do not retain an entry reference after removing its mapping and expect it to automatically rebind later.

If you need to keep an independent key–value snapshot, create an appropriate entry copy. `Map.Entry.copyOf` creates an independent unmodifiable entry following the same non-`null` policy as `Map.entry`. `AbstractMap.SimpleImmutableEntry` is another option whose element policy should be chosen deliberately. Note that both options only detach the key–value pairing; they do not deep-copy the key or value objects themselves.

### 4.6. Be Careful When Optimizing Entry-Returning Paths

In the example above, `entrySet` extends `AbstractSet` and provides only a wrapped iterator. Inherited methods that traverse via `iterator()` automatically receive checked entries.

If you later override `toArray`, `forEach`, or `spliterator` for performance by delegating directly to the backing collection, you can inadvertently leak unwrapped backing entries to callers. At that point, your validation policy is compromised again even though `iterator().next()` still looks safe.

Therefore, whenever a returned element object retains the ability to mutate backing data, audit every path that can emit that object—not just standard iteration. Keeping the `data` field `private` is not enough if objects with write-through privileges escape unwrapped.

The example class prioritizes clear call paths over lookup optimization. Several methods inherited from `AbstractMap` perform linear searches by iterating over `entrySet`. It serves as an illustration of contracts and input validation, not a fully optimized production map replacement for every workload.

## 5. Default Methods Do Not Add Every Guarantee You Might Want

### 5.1. null Has Multiple Meanings in Map

A map that permits `null` values must distinguish between "key is absent" and "key is present with a `null` value". Checking `get(k) == null` alone cannot separate these two states; `containsKey` may be required.

Different operations follow distinct rules regarding `null`:

| Operation | Role of null to Remember |
| --- | --- |
| `getOrDefault(k, d)` | If the key exists with a `null` value, the result is still `null`, not `d`. |
| `putIfAbsent` | A current value of `null` is treated as absent and eligible for assigning the new value. |
| `computeIfAbsent` | May compute when the current value is `null`; a `null` computation result creates no new mapping. |
| `computeIfPresent` | Computes only when a non-`null` value is currently mapped; a `null` result removes that mapping. |
| `compute` | May receive an old value of `null`; a `null` result leaves the key unmapped (removing it if present). |
| `merge` | The supplied value argument must be non-`null`; when no non-`null` value is currently mapped, it associates the supplied value directly without calling the remapping function. A `null` result from the remapping function removes the mapping. |
| `replaceAll` | A `null` result is treated as a value to assign, not a removal signal. Maps that forbid `null` values may reject it. |

For `computeIfAbsent` specifically, if a key is already mapped to `null` and the mapping function returns `null`, do not assume the existing `null`-valued entry is removed. Its "do not record a mapping" behavior differs from the explicit removal behavior of `compute` or `computeIfPresent`.

Because `ScoreMap` forbids `null` values, `get` returning `null` unambiguously indicates an absent mapping. However, when designing a general-purpose map that accepts `null` values, you must preserve this distinction across read, conditional replacement, and computation methods.

The authoritative reference is each individual method specification in [Java 17 Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html). Never apply a blanket rule like "`null` always means remove" across every API.

### 5.2. Preserving an Invariant Is Different from Rolling Back an Entire Bulk Operation

Near the end of the map program, two outputs can easily be misinterpreted:

- `putAll` inserts `D=4` first and then rejects `E=-1`. `D=4` remains in the map.
- `replaceAll` updates `A=1` to `A=11` first and then rejects the negative result for `B`. `A` stays `11` while `B` remains `2`.

Both final states preserve the non-negative value invariant. However, the bulk operations were only partially applied. Throwing an exception does not automatically roll back prior valid updates to their previous state.

In our demonstration, the partial update order is deterministic because `LinkedHashMap` backs the relevant structures. For collections that make no iteration-order guarantees, you must never promise which elements will have been modified before a failure occurs.

If your domain requirement is "all succeed together or nothing changes" (transactional atomicity), you need a different design involving a staging/validation phase and an atomic publication step. Simply adding a pre-validation loop over inputs does not solve concurrent modifications by multiple threads or remapping functions with external side effects.

Functions passed to `compute` or `merge` should compute their results without mutating the target map itself. A validation check inside a wrapper class cannot undo arbitrary external side effects triggered by a caller-supplied function.

### 5.3. Map Default Methods Are Not Automatically Atomic

A "read current state → compute → write" sequence may execute properly on a single thread while providing zero atomicity guarantees under concurrent multi-threaded access. The default method specifications on `Map` explicitly state that they do not promise synchronization or atomicity.

Do not rebrand a simple wrapper class as a concurrent map merely because it inherits `compute` or `putIfAbsent`. If concurrency guarantees are required, you must use or implement an appropriate concurrent contract (such as `ConcurrentMap`), enforce it consistently across all methods and views, and document it clearly.

All programs in this article run on a single thread. They verify update paths, equality contracts, and observable states; they are not proof of thread safety under concurrent access.

### 5.4. Unsupported Operations Are Also a Policy That Must Be Consistent

A read-only structure may reject mutating calls by throwing `UnsupportedOperationException`. Never use a no-op invocation—such as removing a non-existent element or adding an empty collection—to conclude that a structure supports mutation.

Conversely, when writing a read-only wrapper, do not merely block `put` or `add` while leaving newer default methods, iterators, or views able to write through. You must audit default interface methods and every object reachable from the wrapper.

Whenever your target Java version advances, review newly introduced interface methods and inherited operations. The core requirement remains constant: every path into the same underlying data must enforce the policy your class advertises.


## 6. How to Systematically Audit a Custom Implementation

### 6.1. Write Down the Contract Before Choosing Which Methods to Override

Before inspecting code, explicitly state what your class promises:

- Does it implement `Collection`, `List`, `Set`, or `Map`? Which equality contract applies?
- Are `null` elements, keys, or values permitted? What is the policy on duplicates, ordering, and comparison?
- Are additions, replacements, and removals supported, or only a subset?
- Which views are mutable? Do returned objects carry write-through capability?
- When a bulk operation fails mid-way, is partial application permitted?
- Are any concurrency guarantees genuinely provided?

You do not need to copy-paste domain validation logic into every single method. Identify the foundational operations through which other paths funnel, and then verify that no bypass routes exist. The list example placed validation in positional `add` and `set`; the map example placed validation in `put` and write-through entries.

If you subclass a concrete collection or delegate an optimized bulk method directly to a backing store, double-check: are you bypassing validation guards defined in the outer class? Code reuse must never accidentally alter your public contract.

### 6.2. Test by Contract Category, Not Just by Method Name

| Contract Category to Verify | High-Value Test Scenarios |
| --- | --- |
| Equality relationship | Same content compared against a standard implementation; test both directions; same collection interface but different concrete classes. |
| Hash code | Every pair confirmed equal produces identical hash codes; do not require unequal pairs to have distinct hash codes. |
| Data type semantics | Reordered lists must become unequal; sets ignore order and duplicates; maps compare key–value mappings rather than iteration order. |
| Direct mutation paths | Additions, replacements, removals, invalid inputs, and boundary values. |
| Iterator mutation paths | `Iterator.remove`, `ListIterator.add/set/remove` when supported. |
| View paths | `subList`, `keySet`, `values`, `entrySet`, and write-through `Map.Entry` instances. |
| Default / inherited algorithms | `removeIf`, `replaceAll`, `sort`, `putAll`, and conditional map computation/replacement methods. |
| Mid-operation failure | Inspect the exact updates applied prior to failure and verify that all invariants still hold. |
| Data escape paths | Iterators, `toArray`, `forEach`, streams: do any of them leak unwrapped objects that bypass validation? |

A test that only checks `custom.equals(custom)` verifies reflexivity, not cross-implementation interoperability. A test that only calls `put` will never catch a validation hole in `Entry.setValue`. A test that only supplies valid inputs never verifies your rejection policy.

When using randomized testing, use reproducible inputs or fixed seeds. For contract bugs like the ones covered here, however, small, targeted tests designed around specific execution paths typically provide much clearer evidence than firing thousands of random operations without knowing which call paths were actually exercised.

### 6.3. Compare Observable State After Every Step

For any supported operation, verify all four aspects:

1. The return value or exact exception type thrown.
2. The resulting contents, size, and consistency across views afterward.
3. That the class invariant still holds across every element or mapping.
4. Equality and hash code agreement when compared against an equivalent reference collection.

Do not stop at "an exception was thrown". For example, if `replaceAll` throws an exception on a negative value only *after* letting that negative value slip into storage, the invariant is broken despite the exception. Conversely, having updated entry A to a valid value before rejecting entry B is not a bug if the contract does not promise all-or-nothing rollback.

Likewise, never treat `toString()` output as the sole definition of equality. While helpful for inspecting small examples, string formatting order can vary across unordered collections, and two objects that format identically do not necessarily share the same API contract.

### 6.4. Separate Contract, Backing Implementation, and Runtime Evidence

Keep three layers of reasoning distinct:

- **Contract:** What the Java API specification and your class documentation promise to callers.
- **Implementation:** The specific algorithms in use, including base classes and overridden methods.
- **Evidence:** A concrete test run confirming specific deterministic scenarios.

In this article, Java 17 is the compile-time API and language level (`--release 17`). Default method call paths are cross-referenced against the Java 17 specification and OpenJDK 17u source code. The three demonstration programs provide runtime evidence for the printed scenarios.

Never extrapolate a single observation into an unstated guarantee—such as assuming every failure throws before mutating state, every map iterates in insertion order, or every method named `compute` is thread-safe and atomic.

## 7. Guided Exercises with Solutions

### Question 1. A Custom List That Only Equals Instances of Its Own Class

Suppose you implement `equals` in a custom `List` by requiring `other.getClass() == getClass()`. It contains `["A", "B"]`, and an `ArrayList` also contains `["A", "B"]`. What bug can occur?

**Solution:** Your custom list returns `false` when compared with the `ArrayList`, whereas `ArrayList.equals` returns `true` when comparing in the opposite direction. This violates symmetry and breaks the cross-implementation `List.equals` contract. Follow the standard list equality rule or inherit it from an appropriate skeletal base class; never restrict `List.equals` to a single concrete class.

**Practice:** Take `Words` from the first program and test it against a `LinkedList` as well as a list with the same elements in a different order. Verify equality in both directions and compare hash codes for all equal pairs.

### Question 2. Two Equal Entries with Different Hash Codes

Suppose an entry wrapper compares keys and values properly in `equals`, but its `hashCode` calls `Objects.hash(key, value)`. Why might testing two instances of your wrapper against each other miss this bug?

**Solution:** Two instances of the same wrapper sharing the same flawed formula will produce matching hash codes with each other, yet disagree with a standard `Map.Entry` representing the exact same mapping. You must use the `Map.Entry` XOR formula and cross-check against a standard entry implementation. A wrong entry hash code can also corrupt the hash code of `entrySet()` and the enclosing `Map`.

**Practice:** Test both non-`null` keys/values and `null` cases if your target entry type permits `null`. Be careful not to construct `null` test cases using factory methods like `Map.entry` that inherently reject `null` and confuse the resulting `NullPointerException` with a formula bug.

### Question 3. Blocking Negative Values in put While Returning Raw Backing Entries

A map wrapper overrides `put` to reject negative integers, but its `entrySet()` directly returns `data.entrySet()`. What are two ways a caller can bypass validation?

**Solution:** Call `setValue(-1)` directly on an entry obtained from `entrySet()`; or invoke the default `replaceAll` implementation with a function that produces a negative number, since `Map.replaceAll` updates values via `Entry.setValue`. You must either wrap returned entries to validate write-through updates or disallow write-through mutation altogether according to your published contract.

**Practice:** In a temporary copy of `ScoreMap`, replace the wrapped entry iterator with `data.entrySet().iterator()` and watch the non-negative invariant break. Then restore the wrapper and verify both entry equality/hash codes and update validation.

### Question 4. Is Wrapping entrySet with unmodifiableSet Enough to Make a Map Read-Only?

**Solution:** No. Preventing callers from adding or removing elements on the `Set` container does not prevent them from calling `setValue` on individual `Map.Entry` objects retrieved from that set. A truly read-only map view must block entry write-through (`setValue`), direct mutator methods on the map, and mutations across all collection views (`keySet`, `values`, `entrySet`). `Collections.unmodifiableMap` is the standard starting point when you need this policy for an existing map.

**Practice:** Distinguish between an unmodifiable container and unmodifiable elements. List every path through which callers can obtain entries from `entrySet()`—iterators, `toArray`, `forEach`, and streams—and verify which paths must wrap entries.

### Question 5. A Read-Only View Changes After the Backing List Mutates

You create `Collections.unmodifiableList(source)` and subsequently add an element to `source`. Does the unmodifiable view seeing the new element violate its read-only promise?

**Solution:** No. An unmodifiable view forbids mutation *through the view reference itself*, while continuing to read live state from its backing source. If you need an immutable snapshot unaffected by later structural edits to the source, make a copy with an appropriate contract. When using `List.copyOf`, remember that it rejects `null` elements and performs a shallow copy of element references.

**Practice:** Use two references as shown in `ViewsAndDefaultsDemo`: an unmodifiable view and a `List.copyOf` snapshot. Replace, add, and remove elements on the source list, predicting the state of both references before running the code.

### Question 6. null Returned from compute vs. null Returned from replaceAll

Suppose a map forbids storing `null` values. The remapping function passed to `computeIfPresent` returns `null`, and the function passed to `replaceAll` also returns `null`. Do these two `null` results mean the same thing?

**Solution:** No. In `computeIfPresent`, a `null` return value instructs the map to *remove* the existing mapping. In `replaceAll`, the function's return value is assigned to the entry via `setValue`; a map that forbids `null` values will reject it. Never generalize "this map forbids `null` values" into "every callback returning `null` must throw an exception".

**Practice:** Extend `CheckedMapDemo` with an explicit test for `replaceAll` returning `null` and inspect the map's state afterward. When testing bulk operations, take note of partial application on earlier entries.

### Question 7. If the Invariant Holds, Was the Operation Atomic?

In `CheckedMapDemo`, `replaceAll` updates `A` to `11` before failing on `B`, leaving all values in the map non-negative. Can you conclude that the operation rolled back or executed atomically?

**Solution:** No. While the non-negative invariant was preserved, the bulk update was partially applied. All-or-nothing rollback and concurrency atomicity are separate guarantees that do not arise automatically from per-element value validation. Under multi-threaded access, `Map`'s default methods likewise provide no built-in synchronization.

**Practice:** Write down the exact before and after states of the `partial` map in `CheckedMapDemo`. State precisely what was proven: no negative values entered the map, `A` changed from `1` to `11`, and `B` remained `2`—without claiming transactional rollback or thread safety.

## 8. Verification and References

All three programs in this article were compiled with `javac --release 17 -encoding UTF-8 -Xlint:all` and executed on OpenJDK 24.0.2; their actual outputs match the `text` blocks shown above. Note that `--release 17` pins the compile-time language and API level to Java 17; it does not mean the runtime JVM itself was version 17.

The examples never rely on the unspecified iteration order of `HashMap` or `HashSet` to print element sequences. The partial bulk-update map demonstration uses `LinkedHashMap` so that iteration order is deterministic. All executions are single-threaded.

Primary references:

- [Object — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `equals` and `hashCode` contracts.
- [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html), [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): collection semantics, views, and related default algorithms.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): map views, compute/merge operations, conditional replacements, `null` rules, and default non-atomicity caveats.
- [Map.Entry — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html): entry equality, XOR hash code formula, write-through semantics, and entry validity lifecycle.
- [Collections — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): unmodifiable wrapper implementations.
- [AbstractMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html): building a map implementation on top of `entrySet`.
- [OpenJDK 17u Map source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/Map.java) and [List source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/List.java): reference for the default method call paths discussed; concrete classes may override them.
