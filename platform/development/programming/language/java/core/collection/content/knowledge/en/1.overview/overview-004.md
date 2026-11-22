# Why Does Map Belong to the Framework Without Extending Collection?

**`Map` belongs to the Java Collections Framework because it is part of Java's API system for organizing and processing data. It does not extend `Collection` because the contract of a key–value mapping differs from the contract of a group of elements.**

Two relationships should be kept separate:

- **Belonging to the framework:** participating in the same system of interfaces, implementation classes, algorithms, and conventions.
- **Extending an interface:** a type committing to fulfill the full contract of its parent interface.

There is no rule stating that every component in the Java Collections Framework must sit under the `Collection` interface. The `Map` branch exists alongside the `Collection` branch and connects to it through views such as `keySet()`, `values()`, and `entrySet()`.

## 1. Where Do the Two Data Models Differ?

### 1.1. Collection Views Data as Elements

With `Collection<E>`, the unit of processing is an element of type `E`.

Example of a group of product codes:

```text
["pen", "book", "bag"]
```

The natural questions are:

- How many elements are in this group?
- Does it contain the element `"book"`?
- Can an element be added or removed?
- How do we iterate over the elements?

Subinterfaces add specific semantics. `List` has positions and list ordering; `Set` represents a collection with no duplicate elements; `Queue` serves processing according to a queuing policy.

### 1.2. Map Views Data as Key–Value Relationships

With `Map<K, V>`, the domain unit is a **mapping** from a key of type `K` to a value of type `V`.

Example of inventory quantities:

```text
"pen"  -> 10
"book" -> 3
"bag"  -> 3
```

The natural questions shift to:

- What is the quantity corresponding to the code `"pen"`?
- Does the code `"book"` already have a mapping?
- How do we update the quantity for a code?
- Which key's mapping should be removed?

In a map, each key has at most one current value. Different keys can map to equal values. In the example above, two values of `3` do not violate the map contract.

A value can also be an object containing multiple elements, such as `Map<String, List<String>>`. Even then, each key still maps to **one List object**, without changing the contract of `Map`.

The key–value characteristics and the position of `Map` in the framework are described in the [Java 17 Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 2. Why Not Use Collection<Map.Entry<K, V>> as the Parent?

A key–value pair can be represented by `Map.Entry<K, V>`. From there, you can certainly create a collection holding those pairs. However, **holding data pairs** is not the same as **fulfilling the contract of a map**.

### 2.1. A Set of Pairs Does Not Guarantee Unique Keys

Consider two pairs:

```text
("pen", 10)
("pen", 12)
```

For two ordinary `Map.Entry` instances, having different values means these two pairs are not equal. Therefore, a `HashSet<Map.Entry<String, Integer>>` can hold both pairs at the same time.

For a map, calling in sequence:

```java
map.put("pen", 10);
map.put("pen", 12);
```

creates one current mapping for `"pen"` with value `12`, not two mappings with the same key.

The snippet above illustrates statements inside a method, where `map` is a mutable `Map<String, Integer>`.

The difference lies in the **rules for identifying and updating elements**, not in whether Java can store two values inside one object. Nor can it be explained simply by "`Collection` has one type parameter while `Map` has two", because `E` could easily be a pair type.

### 2.2. Core Operations Require Separate Contracts

| Need | Collection Contract | Map Contract |
| --- | --- | --- |
| Adding data | `add(E)` requests inserting an element into the group | `put(K, V)` creates or replaces the mapping for a key |
| Checking presence | `contains(Object)` asks about an element | `containsKey(Object)` and `containsValue(Object)` query two different sides |
| Key-based lookup | No equivalent general operation | `get(Object)` returns the value associated with a key |
| Removing data | `remove(Object)` removes a matching element | `remove(Object)` removes the mapping by key |
| Size | Number of elements | Number of key–value mappings |
| Iteration | Each element of type `E` | Must choose to iterate over keys, values, or entries |

Suppose a map had an `add(entry)` method—that name alone would not specify what happens when the key already exists: reject the new pair, keep both pairs, or replace the old value? `Map.put` has its own contract so callers know what behavior to expect.

Similarly, `contains(x)` on a map would need to define whether `x` is interpreted as a key, a value, or a complete pair. The `Map` API makes the intent explicit through separate methods.

### 2.3. Signature Conflicts Show This Is Not Just Changing the Inheritance Tree

One concrete difference in the existing API:

```java
// Illustrative signatures, not a standalone class or program:

// In Collection<E>:
boolean remove(Object element);

// In Map<K, V>:
V remove(Object key);
```

The two methods have the same name and the same parameter type list, yet one returns `boolean` and the other returns `V`.

With `Collection`, the result answers the question "did the group change as a result of removing the element?". With `Map`, the result is the previous value associated with the key, or `null` according to the method's contract.

You cannot simply add `extends Collection<...>` to the existing `Map` and keep both contracts intact: Java does not distinguish methods by return type alone, and `boolean` is incompatible with the reference type `V`.

This is a clear manifestation of the semantic difference between the two interfaces. The goal of API design is to provide a clear contract for each data model, rather than forcing two models into one interface just because both "contain multiple things".

You can compare the signatures in the [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)) and the [Map.remove API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#remove(java.lang.Object)).

## 3. Where Does Map Sit in the Framework?

The simplified diagram below shows the familiar interface branches in Java 17:

```text
Java Collections Framework
│
├── Element-group branch
│   └── Collection<E> extends Iterable<E>
│       ├── List<E>
│       ├── Set<E>
│       └── Queue<E>
│           └── Deque<E>
│
└── Mapping branch
    └── Map<K, V>
        └── SortedMap<K, V>
            └── NavigableMap<K, V>
```

This is a simplified grouping and inheritance diagram, not an exhaustive list of every interface in the framework.

Some implementation classes:

| Interface Used | Example Implementation Classes |
| --- | --- |
| `List<E>` | `ArrayList<E>`, `LinkedList<E>` |
| `Set<E>` | `HashSet<E>`, `LinkedHashSet<E>` |
| `Deque<E>` | `ArrayDeque<E>`, `LinkedList<E>` |
| `Map<K, V>` | `HashMap<K, V>`, `LinkedHashMap<K, V>` |
| `NavigableMap<K, V>` | `TreeMap<K, V>` |

Having `HashMap` implement `Map` places it in the mapping branch of the framework. It does not need and does not have an inheritance relationship with `Collection`.

The framework also provides utilities that support both branches. For example, the `Collections` class has `unmodifiableCollection` and `unmodifiableMap`. Thus, **Java Collections Framework**, the **`Collection` interface**, and the **`Collections` class** are three names at three different scopes.

See the overall structure in the [Java 17 Collections Framework Overview](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/doc-files/coll-overview.html).

## 4. Three Views Connecting Map to Collection

A map can be viewed from three perspectives without turning itself into a `Collection`:

| Method | Return Type | Data Exposed |
| --- | --- | --- |
| `keySet()` | `Set<K>` | Set of keys |
| `values()` | `Collection<V>` | Group of values |
| `entrySet()` | `Set<Map.Entry<K, V>>` | Set of key–value pairs |

### 4.1. Why Is keySet a Set?

Keys in a map do not repeat according to that map's key rules. A view of type `Set<K>` accurately reflects this property.

### 4.2. Why Is values Only a Collection?

Values can be duplicated. If `"book"` and `"bag"` both have a quantity of `3`, `values()` must reflect both occurrences.

If the result were a `Set<V>`, equal values could be collapsed, losing the information that they belong to different mappings.

### 4.3. Why Is entrySet a Set?

An entry holds the key and value of a single mapping. Because each key has at most one mapping, a map's entry set contains no duplicate pairs.

The reverse implication does not hold: an arbitrary `Set<Map.Entry<K, V>>` can still contain two pairs with the same key and different values. The map itself is responsible for enforcing key uniqueness; returning a `Set` does not replace the map's enforcement of that constraint.

### 4.4. A View Is an Object Backed by the Original Map

The returned collections are **views** backed by the original map. When the map's contents change, the views reflect those current contents; you do not need to call `keySet()` again just to see a newly added key.

In the other direction, certain supported modification operations on a view affect the map. For instance, removing a key via `keySet().remove(key)` also removes the corresponding mapping if the map and view support removal.

This does not mean a view can be modified arbitrarily:

- These three standard views do not support adding elements via `add` or `addAll`.
- Removing via `values()` removes the mapping corresponding to the removed value. If multiple mappings share the same value, `remove(value)` removes only one matching mapping; it should not be used in place of selecting a specific key.
- `Map.Entry.setValue` is an optional operation. An entry obtained from an unmodifiable map may reject it.
- Entries created by `Map.entry(k, v)` cannot be modified with `setValue`.

The behavior and limitations of entries are specified in the [Map.Entry API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

## 5. Complete Java Example

The following program demonstrates the difference between a set of pairs and a map, then verifies the three views.

Save to **MapFrameworkDemo.java**:

```java
import java.util.Collection;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class MapFrameworkDemo {
    public static void main(String[] args) {
        Set<Map.Entry<String, Integer>> pairs = new HashSet<>();
        pairs.add(Map.entry("pen", 10));
        pairs.add(Map.entry("pen", 12));

        Map<String, Integer> sameKey = new LinkedHashMap<>();
        sameKey.put("pen", 10);
        sameKey.put("pen", 12);

        System.out.println("Pair set size: " + pairs.size());
        System.out.println("Map size for same key: " + sameKey.size());
        System.out.println("Current pen value: " + sameKey.get("pen"));

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("pen", 10);
        stock.put("book", 3);
        stock.put("bag", 3);

        Set<String> keys = stock.keySet();
        Collection<Integer> values = stock.values();
        Set<Map.Entry<String, Integer>> entries = stock.entrySet();

        System.out.println("Initial map: " + stock);
        Integer old = stock.put("pen", 12);
        System.out.println("Previous pen value: " + old);
        System.out.println("After update: " + stock);
        System.out.println("Keys: " + keys);
        System.out.println("Values: " + values);
        System.out.println("Entries: " + entries);

        stock.put("eraser", 2);
        System.out.println("Keys after put: " + keys);

        values.remove(2);
        System.out.println("After values.remove: " + stock);

        keys.remove("book");
        System.out.println("After keys.remove: " + stock);

        Map.Entry<String, Integer> first = entries.iterator().next();
        first.setValue(15);
        System.out.println("After entry.setValue: " + stock);

        try {
            keys.add("ruler");
        } catch (UnsupportedOperationException ex) {
            System.out.println("keySet.add: " + ex.getClass().getSimpleName());
        }

        Map<String, Integer> copy = new LinkedHashMap<>(stock);
        stock.put("pen", 99);
        System.out.println("Map after later change: " + stock);
        System.out.println("Independent map copy: " + copy);
    }
}
```

Compile and run with a JDK that supports Java 17:

```shell
javac --release 17 -encoding UTF-8 MapFrameworkDemo.java
java MapFrameworkDemo
```

Stdout:

```text
Pair set size: 2
Map size for same key: 1
Current pen value: 12
Initial map: {pen=10, book=3, bag=3}
Previous pen value: 10
After update: {pen=12, book=3, bag=3}
Keys: [pen, book, bag]
Values: [12, 3, 3]
Entries: [pen=12, book=3, bag=3]
Keys after put: [pen, book, bag, eraser]
After values.remove: {pen=12, book=3, bag=3}
After keys.remove: {pen=12, bag=3}
After entry.setValue: {pen=15, bag=3}
keySet.add: UnsupportedOperationException
Map after later change: {pen=99, bag=3}
Independent map copy: {pen=15, bag=3}
```

### 5.1. Comparing the Results

**The first three lines** compare the two models:

- The `pairs` set retains two distinct entries: `("pen", 10)` and `("pen", 12)`.
- The `sameKey` map has only one `"pen"` key, with a current value of `12`.

**The update `stock.put("pen", 12)`** returns the previous value `10`. Because the key already existed, the map still has three mappings.

**The `values` view prints `[12, 3, 3]`**, preserving the fact that two different keys share the value `3`.

**After adding `"eraser"`**, the `keys` variable obtained earlier still sees the new key. This proves that a view is not an independent copy.

**Removing through a view** affects the map:

- `values.remove(2)` removes the mapping `"eraser" -> 2`. The value `2` was chosen because it appears only once in this dataset.
- `keys.remove("book")` removes the mapping for `"book"`.
- The first entry of the `LinkedHashMap` at this point is the entry for `"pen"`; `setValue(15)` updates the value in the map.

**`keySet.add` is rejected** with `UnsupportedOperationException`, showing that returning a `Set` does not guarantee all set operations are supported.

**The last two lines** distinguish a view from a structural copy: `new LinkedHashMap<>(stock)` creates a separate map containing the mappings at the time of copying. Updating the original map's mappings afterward does not update the mappings in the copied map.

The `LinkedHashMap` in the example is created with the default constructor, which preserves insertion order of keys. Updating the value of an existing key does not move that key's position. Do not rely on this stdout order as a guarantee for an arbitrary `HashMap`; see the [LinkedHashMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

## 6. Applying This When Writing APIs and Iterating Over Data

### 6.1. Choose the View Based on the Data Actually Needed

If a method only needs the values, you can pass `map.values()` to a `Collection<V>` parameter. If you need both keys and values, use `entrySet()`. If you need key-based lookup or updates, keep the parameter type as `Map<K, V>`.

The following snippet sits inside a method that has a `stock` variable:

```java
for (Map.Entry<String, Integer> entry : stock.entrySet()) {
    System.out.println(entry.getKey() + " has " + entry.getValue());
}

stock.forEach((key, value) ->
        System.out.println(key + " has " + value));
```

Both approaches process the mappings. `Map.forEach` accepts an action taking both key and value; the existence of this method does not make `Map` extend `Iterable`.

You cannot write a `for-each` loop directly over a variable whose type is `Map`:

```java
// Does not compile: Map is not Iterable.
// for (var item : stock) {
// }
```

Use `stock.entrySet()`, `stock.keySet()`, or `stock.values()` depending on your goal.

### 6.2. Do Not Cast to Force a Nonexistent Inheritance Relationship

This assignment is invalid:

```java
// Map<String, Integer> stock = new LinkedHashMap<>();
// Collection<?> data = stock; // Does not compile.
```

Instead of casting through `Object`, choose the right view. `stock.entrySet()` has type `Set<Map.Entry<String, Integer>>`, so it can be used as a `Collection<Map.Entry<String, Integer>>`.

Switching to a view selects a way of looking at the data; casting does not turn a map into an object that obeys the `Collection` contract.

### 6.3. Distinguish Structural Copying from Deep Copying

A copy created with `new LinkedHashMap<>(stock)` has its own mapping structure. However, it does not automatically clone the key and value objects.

In the example, `String` and `Integer` are immutable, so this distinction is easy to overlook. If a value is a mutable `List` and both maps hold a reference to that list, changes to the list's contents are visible from both maps.

If completely independent data is required, you must define a copying policy for each object type rather than assuming the map's copy constructor handles it.

## 7. Common Mistakes

| Misconception or Incorrect Operation | Problem | Appropriate Approach |
| --- | --- | --- |
| "If it doesn't extend Collection, it's not part of the JCF" | Confuses inheritance with framework scope | View Collection and Map as two branches |
| "A Map is just a Set of pairs" | A set of pairs can hold the same key with different values | Use Map to express key-based constraints |
| "values() is a Set because a map has no duplicate keys" | Unique keys do not make values unique | Keep the Collection type for the group of values |
| "Getting keySet and saving it takes a snapshot of the data" | The view remains backed by the original map | Create a copy when you need point-in-time data |
| "Since keySet returns a Set, keySet.add must work" | The add operation is not supported | Add mappings via Map.put |
| "Removing a value is how to remove a specific code" | Multiple keys can share the same value | Remove by key when intent is tied to a code |
| "Every entry supports setValue" | Some entries do not allow modification | Check the contract of the entry's source |
| "Every Map prints in insertion order" | Each implementation class has its own guarantees | Choose the class based on ordering requirements |

While iterating over views, you should also avoid arbitrarily adding to or structurally removing from the map through another path. Behavior depends on the map and iterator contracts; for ordinary maps, this can cause a `ConcurrentModificationException`. If you need to remove during iteration, choose a supported operation such as `Iterator.remove()` and follow its contract, rather than relying on a single test run not throwing an error.

## 8. Self-Check Exercises

1. Write two sentences distinguishing "`Map` belongs to the framework" from "`Map` extends `Collection`".
2. Given two pairs `("A", 1)` and `("A", 2)`, predict the size of a `HashSet<Map.Entry<String, Integer>>` and of a map updated sequentially with those two pairs.
3. Explain why `values()` does not have the return type `Set<V>`.
4. In the program, replace `keys.remove("book")` with `stock.remove("book")`. Does the `keys` view still contain that key afterward?
5. Create a `Map<String, List<String>>`, copy it using the `LinkedHashMap` constructor, and then modify the value list. Explain the difference between modifying a mapping and modifying the mapped object.
6. Compare the two `remove(Object)` signatures: why is it impossible to merge the existing contracts directly into an inheritance relationship just by changing the declaration?

The goal is to be able to explain the model choice and accurately predict view behavior, rather than merely memorizing the phrase "Map does not extend Collection".
