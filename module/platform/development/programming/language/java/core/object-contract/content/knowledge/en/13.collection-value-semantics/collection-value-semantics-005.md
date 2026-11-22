# Equality Can Apply Across Implementation Classes Sharing the Same Contract

## 1. Same Interface, Different Implementation Classes: Can `equals()` Return `true`?

In Java, `ArrayList` and `LinkedList` are two different classes, yet both implement the `List` interface. When two lists contain **equal elements at the same positions**, they are considered equal under the `List.equals(Object)` contract, even though their implementation types and internal data structures differ.

```java
List<String> a = new ArrayList<>(List.of("java", "core"));
List<String> b = new LinkedList<>(List.of("java", "core"));

System.out.println(a.equals(b)); // true
System.out.println(b.equals(a)); // true
```

This is an illustrative fragment; it requires importing `java.util.List`, `ArrayList`, and `LinkedList`. A complete runnable example appears in a later section.

**Key point:** equality of standard collections is typically defined by the **contract of the abstract interface** (`List`, `Set`, `Map`) rather than requiring `a.getClass() == b.getClass()`. We can compare two different implementation classes when they adhere to an equality relation with unified semantics.

However, do not generalize this statement into "every `Collection` compares by contents": **`Collection` does not impose a universal `equals()` algorithm on all collection types**. Cross-class compatibility depends on the specific contract of the type being compared and proper implementation of that contract.

## 2. Why Can Different Classes Still Be Equal?

`Object.equals(Object)` only specifies the properties of an equivalence relation (reflexive, symmetric, transitive, consistent, and non-equal to `null`). A class decides its own criteria for logical identity as long as it obeys these properties.

For collections, many criteria are standardized at the interface level:

| Type | Contract Equality Condition | Cross-Implementation Examples That Can Be Equal |
| --- | --- | --- |
| `List` | Other object is a `List`, same size, each corresponding position has equal elements | `ArrayList` and `LinkedList` |
| `Set` | Other object is a `Set`, same size, contains equivalent elements under element semantics | `HashSet` and `LinkedHashSet` or `TreeSet` with matching ordering |
| `Map` | Other object is a `Map`, same set of key → value mappings; independent of iteration order | `HashMap`, `LinkedHashMap`, and `TreeMap` with compatible key comparison |

When classes of the same type obey these criteria, internal algorithms, storage ordering, complexity, and synchronization capabilities can differ while `equals()` still returns the right result.

For example, `ArrayList` stores elements in a dynamic array while `LinkedList` is a linked list. Those differences do not appear in the definition of `List.equals`; what is compared is the **positional sequence of values**.

## 3. Comparing Two `List` Instances of Different Implementations

For two `List` instances, the equality condition is **same size and equal elements at each corresponding position**. Thus, `ArrayList` and `LinkedList` can be equal in both directions:

```java
List<String> array = new ArrayList<>(List.of("A", "B"));
List<String> linked = new LinkedList<>(List.of("A", "B"));
System.out.println(array.equals(linked)); // true
System.out.println(linked.equals(array)); // true
```

This is an illustrative snippet requiring imports from `java.util`. Swapping the two positions in `linked` makes the list differ in value; changing the implementation class while keeping ordered contents does not. Two equal lists must have the same hash under the `List` formula, regardless of internal storage details. The dedicated `List.equals()` lesson analyzes duplicate positions, `null`, and elements with custom `equals`.

## 4. Comparing Two `Set` Instances of Different Implementations

`HashSet` and `LinkedHashSet` can be equal despite different insertion orders; `Set.equals()` requires both sides to be a `Set`, have the same size, and contain the same elements under a compatible membership relation:

```java
Set<String> hash = new HashSet<>(List.of("A", "B"));
Set<String> linked = new LinkedHashSet<>(List.of("B", "A"));
System.out.println(hash.equals(linked)); // true
System.out.println(linked.equals(hash)); // true
```

This example requires `java.util` imports. Both have the same hash under the sum-of-element-hashes contract. `TreeSet` can also participate in cross-implementation comparisons when its `Comparator`/natural ordering detects duplicates consistently with `equals`; if the comparator treats two strings that differ under `equals` as the same, symmetry can break (see Section 7). The `Set.equals()` lesson covered membership principles and iteration order in detail.

## 5. Comparing Two `Map` Instances of Different Implementations

`HashMap` and `LinkedHashMap` are equal when they share the same **key → value** mappings, even if insertion or iteration orders differ:

```java
Map<String, Integer> hash = new HashMap<>();
hash.put("A", 1);
hash.put("B", 2);
Map<String, Integer> linked = new LinkedHashMap<>();
linked.put("B", 2);
linked.put("A", 1);
System.out.println(hash.equals(linked)); // true
```

This is a fragment with appropriate `java.util` imports. If the value for the same key differs, or if a value has a different type rejected by `equals` (e.g., `Integer(1)` and `Long(1)`), the two maps differ. Equal maps must have the same hash, due to having the same sum of entry hashes. `TreeMap` is only cross-implementation compatible when the key comparator does not skew equality semantics; Section 7 and the `Map.equals()` lesson present the exact boundaries.

## 6. Java 17 Program Demonstrating These Cases

Save the following code as `CollectionContractEqualityDemo.java`. The program includes `List`, `Set`, and `Map` cases, a `Collection` that does not use general content comparison, and a `TreeSet` comparator example that is intentionally inconsistent with `equals()`.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionContractEqualityDemo {
    public static void main(String[] args) {
        List<String> array = new ArrayList<>(List.of("java", "core"));
        List<String> linked = new LinkedList<>(List.of("java", "core"));
        List<String> swapped = new LinkedList<>(List.of("core", "java"));

        System.out.println("list cross implementation: "
                + array.equals(linked));
        System.out.println("list symmetric: " + linked.equals(array));
        System.out.println("list order matters: "
                + array.equals(swapped));
        System.out.println("list same hash: "
                + (array.hashCode() == linked.hashCode()));

        Set<String> hashSet = new HashSet<>(List.of("java", "core"));
        Set<String> linkedSet = new LinkedHashSet<>(
                List.of("core", "java"));
        Set<String> treeSet = new TreeSet<>(
                List.of("java", "core"));

        System.out.println("set cross implementation: "
                + hashSet.equals(treeSet));
        System.out.println("set symmetric: " + treeSet.equals(hashSet));
        System.out.println("set order ignored: "
                + hashSet.equals(linkedSet));
        System.out.println("set same hash: "
                + (hashSet.hashCode() == treeSet.hashCode()));

        Map<String, Integer> hashMap = new HashMap<>();
        hashMap.put("alice", 1);
        hashMap.put("bob", 2);

        Map<String, Integer> linkedMap = new LinkedHashMap<>();
        linkedMap.put("bob", 2);
        linkedMap.put("alice", 1);
        Map<String, Integer> treeMap = new TreeMap<>(linkedMap);

        System.out.println("map cross implementation: "
                + hashMap.equals(linkedMap));
        System.out.println("map symmetric: "
                + linkedMap.equals(hashMap));
        System.out.println("map TreeMap cross: "
                + hashMap.equals(treeMap));
        System.out.println("map same hash: "
                + (hashMap.hashCode() == linkedMap.hashCode()));

        Collection<String> deque = new ArrayDeque<>(
                List.of("java", "core"));
        System.out.println("list vs deque: " + array.equals(deque));
        System.out.println("deque vs list: " + deque.equals(array));
        System.out.println("Objects.equals(list, linked): "
                + Objects.equals(array, linked));

        // INTENTIONALLY WRONG REGARDING COMPARATOR COMPATIBILITY WITH equals().
        Set<String> insensitive = new TreeSet<>(
                String.CASE_INSENSITIVE_ORDER);
        insensitive.add("java");
        Set<String> sensitive = new HashSet<>();
        sensitive.add("JAVA");

        System.out.println("bad comparator tree to hash: "
                + insensitive.equals(sensitive));
        System.out.println("bad comparator hash to tree: "
                + sensitive.equals(insensitive));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CollectionContractEqualityDemo.java
java CollectionContractEqualityDemo
```

Stdout output:

```text
list cross implementation: true
list symmetric: true
list order matters: false
list same hash: true
set cross implementation: true
set symmetric: true
set order ignored: true
set same hash: true
map cross implementation: true
map symmetric: true
map TreeMap cross: true
map same hash: true
list vs deque: false
deque vs list: false
Objects.equals(list, linked): true
bad comparator tree to hash: true
bad comparator hash to tree: false
```

### Reading the Key Points in the Output

- `ArrayList` and `LinkedList` with the same two strings in exact order → equal **in both directions**, same hash. Reversing order in the list → not equal.
- `HashSet`, `LinkedHashSet`, and `TreeSet` using the natural ordering of `String` represent the exact same set of strings → equal regardless of storage and iteration order.
- `HashMap`, `LinkedHashMap`, and `TreeMap` have the same two string → integer mappings → equal, same hash, despite different insertion/iteration orders.
- `ArrayDeque` is a `Collection`, but does not implement `List.equals`; for two distinct objects in the example, `deque.equals(array)` remains identity comparison and returns `false`. `array.equals(deque)` is also `false` because `deque` is not a `List`.
- `Objects.equals(array, linked)` calls `array.equals(linked)`, so it is still `true`; it only provides null protection and does not change the content contract.

The two "bad comparator" lines intentionally produce opposite results to expose a case that breaks the contract; **do not use a comparator inconsistent with `equals()` in a set or map that the program needs to compare with other implementations**.

## 7. When Can Cross-Class Equality Within the Same Interface Run Into Problems?

### a. Comparator Inconsistent with `equals()`

`TreeSet` can use `String.CASE_INSENSITIVE_ORDER` to treat `"java"` and `"JAVA"` as equivalent in the tree structure. Meanwhile, `HashSet` relies on `String.equals()`, which is case-sensitive.

In the program:

- `insensitive` contains only `"java"`, and can match `"JAVA"` using the case-insensitive comparator.
- `sensitive` contains only `"JAVA"`, and does not treat `"java"` as the same string under `String.equals`.
- `insensitive.equals(sensitive)` can return `true` because `containsAll` checking relies on the `TreeSet` comparator.
- `sensitive.equals(insensitive)` returns `false` because `HashSet.contains("java")` cannot find the exact matching string.

This is an **inconsistency in element identity criteria**, leading to a violation of expected symmetry when comparing between sets. It is not a bug in `String.equals()`. Under the `SortedSet` contract, the ordering should be **consistent with equals** if the sorted set is to properly implement the `Set` contract; otherwise it is a comparator-based structure with different set-membership semantics, and its limits must be understood.

`TreeMap` has the analogous issue where a comparator can treat two keys as equal (`compare(k1,k2) == 0`) even though `k1.equals(k2)` is `false`. Therefore, `Map.equals` compatibility between `TreeMap` and `HashMap` also depends on the key equality policy. The standard example in Section 6 uses `String` natural ordering, which is consistent with `String.equals`.

### b. A Custom Implementation Fails to Follow the Contract

An interface does not automatically force every implementation to write `equals()` and `hashCode()` properly. If you build a custom `List` class whose `equals()` only checks `getClass()`, that class may fail the `List.equals()` contract and break symmetry with `ArrayList` or `LinkedList`.

Therefore, when writing a custom collection, read the interface contract and test **both directions** when comparing against standard implementations, rather than relying on a single call's result. Ensure hash values are consistent with the equality relation.

### c. Inner Elements Have Abnormal `equals()`

Lists, sets, and maps rely on the equality relation of **elements, keys, and values**. If an element class uses a non-transitive epsilon, depends on mutable state, compares superclasses/subclasses asymmetrically, or produces hashes violating the contract, collections using that object can also exhibit unexpected behavior.

For example, `HashSet` cannot "fix" a pair of elements with a broken `equals()`. Before comparing collections, ensure each involved value type has a valid equality relation and corresponding hash.

### d. Two Collection Types Are Fundamentally Different

A `List` is ordered and can contain duplicate elements; a `Set` does not allow duplicate elements under its equality relation. Even if they appear under `Collection` references or contain the same strings, **no contract requires `List.equals(Set)` to return `true`**. In fact, standard classes define them as unequal.

`Queue` or `Deque` likewise do not inherently perform content comparison like `List`. For instance, `ArrayDeque` inherits object-identity `equals()`. Seeing two collections print the same elements or share the same iteration order is not enough to conclude they are equal.

## 8. Value, Mutation, and Use Inside Other Collections

### Why Must the Equality Relation Be Stable?

A `List` containing elements with mutable state can change its `equals()` and `hashCode()` results when an element is modified. A `Set` or `Map` containing a key whose hash-participating field changes after insertion may no longer locate the key by its current value as expected.

For objects used as **`HashSet` elements or `HashMap` keys**, prefer immutable classes or immutable keys. Even though the set/map holds the object by reference, modifying values involved in `equals()`/`hashCode()` after storage can break `contains`/`get`/`remove`.

### Caution When Using a Collection as a Map Key or Element of Another Set

If a `List` is used as a `HashMap` key, adding, removing, or sorting elements in the list changes `List.hashCode()`. The map may fail to find the key in the old bucket. An unmodifiable list via `List.copyOf` or `List.of` may work when the elements are also stable, yet structural list unmodifiability alone **does not guarantee deep immutability** of the objects inside the list.

`Set.hashCode()` also depends on element hash codes; `Map.hashCode()` depends on entry hash codes. When using a set or map as a key or element of another hash structure, ensure that the contents defining its identity are not mutated during its storage lifetime.

## 9. Contract Testing When Comparing Across Implementations

A minimal test suite should include:

1. **Within the same type:** `ArrayList` ↔ `LinkedList` with the same elements/order, `HashSet` ↔ `TreeSet` with a valid comparator, `HashMap` ↔ `LinkedHashMap` with the same mappings.
2. **Both directions:** test both `a.equals(b)` and `b.equals(a)` to catch symmetry bugs.
3. **Transitivity:** if `a`, `b`, `c` use three implementations yet represent the same value under the contract, `a.equals(b) && b.equals(c)` must imply `a.equals(c)`.
4. **Hash:** when two objects are equal, their hashes must match, even though unequal objects are not required to have distinct hashes.
5. **Intentional counterexamples:** list with swapped order; set missing one element; map with same key but different value; comparator inconsistent with equals; element mutating state.
6. **Null and special implementations:** `HashMap` and `HashSet` normally allow `null`; `Map.of`/`Set.of` forbid `null`. When creating test data, choose initialization compatible with the collection itself.

Sample snippet (fragment assuming two non-null objects `a`, `b` sharing the same equality contract):

```java
if (a.equals(b) != b.equals(a)) {
    throw new AssertionError("equals() is not symmetric");
}
if (a.equals(b) && a.hashCode() != b.hashCode()) {
    throw new AssertionError("equal objects have different hashes");
}
```

The two checks above test symmetry and hash alignment on **one chosen pair**. They do not prove every value is correct; they must be combined with boundary tests, triples, and analysis of the equality definition.

## 10. Self-Check Questions

**Q1.** What does `new ArrayList<>(List.of("A", "B")).equals(new LinkedList<>(List.of("A", "B")))` return?  
**Answer:** `true`, because both obey the `List.equals` contract by element order without requiring the same implementation class.

**Q2.** What does `new HashSet<>(List.of("A", "B")).equals(new LinkedHashSet<>(List.of("B", "A")))` return?  
**Answer:** `true`; sets ignore insertion order and iteration order.

**Q3.** Are a `HashMap` and a `LinkedHashMap` with the same entries inserted in reverse order equal?  
**Answer:** Yes, if keys and values follow proper `equals()` semantics; `Map.equals` is based on mappings, ignoring entry order.

**Q4.** Why are an `ArrayDeque` and an `ArrayList` both containing `"A", "B"` usually not equal?  
**Answer:** `ArrayDeque` does not promise `List.equals`; `Collection` itself does not impose universal content comparison across all implementations.

**Q5.** Can a `TreeSet` and a `HashSet` containing "the same letters" always be considered equal?  
**Answer:** No. If the `TreeSet` comparator defines equivalence differently from the element's `equals()`, symmetry in cross-implementation comparisons can even be lost.

## Takeaway

**Value-based equality can cross implementation class boundaries when classes follow the same semantic contract.** `ArrayList` and `LinkedList` compare by element position; standard `Set` implementations compare by element set; standard `Map` implementations compare by mapping set. The essential requirement is that the algorithm and the element/key identity policy align. `Collection` in general has no single content-based `equals()` rule across all types, and non-compliant comparators or elements can break symmetry, transitivity, and collection behavior.