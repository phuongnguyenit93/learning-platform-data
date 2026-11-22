# putFirst, putLast, and Sequenced Views of Map

## 1. An Ordered Map Needs Both Lookup and Positioning

Suppose an application stores tasks by ID. Each ID has an associated status or metric, and the UI displays them in processing order. When pinning a task to the front, we want to change the position of **the entire key-value mapping**, rather than maintaining a separate list of keys and trying to keep it synchronized with the map.

Since Java 21, `SequencedMap<K,V>` represents a map with a well-defined encounter order of mappings. `putFirst(k, v)` and `putLast(k, v)` allow inserting or updating a mapping while explicitly placing it at the front or back when supported by the implementation. Three sequenced views allow inspecting the same data as keys, values, or entries.

The ordered unit of a map is the **mapping**. This differs from a regular collection, where the unit is a single element. `SequencedMap` extends `Map`, not `SequencedCollection`. [Java 21: SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

This lesson uses `LinkedHashMap` as a mutable backing source to verify positioning and views. We will also examine sorted sources, unmodifiable wrappers, `null` values, and access-order maps. The main examples require **Java 21 or later**; these Java 21 APIs are not part of the Java 17 standard library target.

## 2. putFirst and putLast Do Two Things at Once

The two core signatures are:

~~~java
V putFirst(K key, V value);
V putLast(K key, V value);
~~~

These are signature shapes for reading the contract, not a standalone runnable Java class.

If the operation completes normally:

- the mapping for `key` has `value`;
- it is placed first with `putFirst` or last with `putLast`;
- the return value is **the previous value associated with the key**, or `null` if there was no previous mapping.

These are optional operations. Do not assume that every object declared as `SequencedMap` supports positioning.

### 2.1. Absent Key: Adding a Mapping at a Boundary

With a mutable `LinkedHashMap`:

~~~text
initial                        {A=10, B=20, C=30}

putFirst(Z, 0)
return value                   null
after                          {Z=0, A=10, B=20, C=30}

putLast(D, 40)
return value                   null
after                          {Z=0, A=10, B=20, C=30, D=40}
~~~

The size increases when adding an absent key. Values do not need to be distinct from existing values; a map only enforces uniqueness on its keys.

### 2.2. Existing Key: Updating the Value and Moving Position

Starting again from `{A=10, B=20, C=30}`:

~~~text
putFirst(B, 200)                returns 20
map after                       {B=200, A=10, C=30}

putLast(A, 100)                 returns 10
map after                       {B=200, C=30, A=100}
~~~

The number of mappings remains 3. There are not two `B` keys or two `A` keys as a result of changing positions. Other mappings preserve their relative order when one mapping is moved in this way.

Do not treat `putFirst` as “only pin to the front.” It also replaces the value with the argument you pass. If you accidentally pass a stale value read earlier, you can overwrite a newer task state.

### 2.3. A Key Already at the Boundary Can Still Have Its Value Updated

If the map is currently `{B=200, A=10}`, calling `putFirst("B", 201)` keeps `B` at the front but changes its value to `201`, returning `200`.

Therefore, checking that the order did not change is not enough to conclude the operation did nothing. Keep three observations separate: whether a key was added, whether the value changed, and whether the order changed.

### 2.4. How Does Regular put Differ?

In a default insertion-order `LinkedHashMap`, `put` with an existing key updates the value while preserving its position. `putFirst`/`putLast` express explicit positioning intent. The class also has an access-order mode with different rules, which is covered separately at the end of this lesson. [Java 21: LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

| Intent on an insertion-ordered linked map | Method |
| --- | --- |
| Insert if absent; if present, update and keep position | `put(k, v)` |
| Insert or update, placing the mapping first | `putFirst(k, v)` |
| Insert or update, placing the mapping last | `putLast(k, v)` |

Do not use `remove(k)` followed by `put(k, v)` as an unconditional substitute. That sequence creates a gap between the two calls where the mapping does not exist and does not clearly express the same intent. Nor does it become transactional under multiple threads.

## 3. A null Return Value Does Not Prove the Key Was Previously Absent

`LinkedHashMap` permits `null` values and one `null` key. `HashMap`, its underlying superclass, has the same policy allowing these values. Do not generalize that policy to every `SequencedMap`. [Java 21: HashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

For example:

~~~java
map.putLast("pending", null);
Integer previous = map.putFirst("pending", 7);
~~~

This Java 21 snippet assumes `map` is a `LinkedHashMap<String,Integer>`. `previous` is `null` even though the key `pending` was already present.

To distinguish “key absent” from “key mapped to `null`”, you can check `containsKey` beforehand in a context where you maintain consistent access. However, `containsKey` followed by `putFirst` is two separate calls; it does not provide an atomic transaction across multiple threads.

Also distinguish these cases:

- `putFirst` returning `null` refers to the **previous value**;
- `firstEntry()` returning `null` indicates the map is **empty**;
- an existing entry with `getValue() == null` is still a mapping.

These uses of `null` occur at different levels. Do not use a single condition to stand in for all three meanings.

## 4. Three Sequenced Views of the Same Map

Suppose the map currently is:

~~~text
map:        {A=10, B=20, C=20}
keys:       [A, B, C]
values:     [10, 20, 20]
entries:    [A=10, B=20, C=20]
~~~

The three methods and their return types:

| Method | Return type | Element unit |
| --- | --- | --- |
| `sequencedKeySet()` | `SequencedSet<K>` | Key |
| `sequencedValues()` | `SequencedCollection<V>` | Value |
| `sequencedEntrySet()` | `SequencedSet<Map.Entry<K,V>>` | Key-value pair |

Keys are unique; the entry for each mapping is also unique. Values can be duplicated, so the value view is `SequencedCollection` rather than `SequencedSet`.

`SequencedSet` combines the set contract with encounter order; set equality is still based on membership, not position. [Java 21: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html).

### 4.1. Not Three Copies

On `LinkedHashMap`, these views are backed by the source data. When the map changes, subsequent queries on the views see the new state; when a supported removal operation is performed through a view, the corresponding mapping is also removed from the map.

You can obtain the views once:

~~~java
java.util.SequencedSet<String> keys = map.sequencedKeySet();
java.util.SequencedCollection<Integer> values = map.sequencedValues();
java.util.SequencedSet<java.util.Map.Entry<String, Integer>> entries =
        map.sequencedEntrySet();
~~~

This snippet assumes `map` is a `SequencedMap<String,Integer>`. After `map.putFirst("Z", 0)` on a supporting source, you do not need to call the three methods again to get new view objects just to observe that mapping.

However, **live views do not mean old iterators remain valid**. If you create an iterator and then alter the order or number of mappings, you must obey the source's iteration rules; do not treat the fact that views reflect updates as a license to continue using an old iterator arbitrarily.

### 4.2. Legacy Views Still Follow the Map's Order

`keySet()`, `values()`, and `entrySet()` on a `SequencedMap` still reflect the encounter order of mappings. The key difference is that their legacy return types do not directly expose the sequenced API.

Thus, this is a change in **expressiveness and operations available through the type**, not a claim that legacy views of linked maps previously iterated in random order.

For example, when you need the last key, `sequencedKeySet().getLast()` expresses the intent more directly than obtaining a `Set<K>` and walking to the end yourself.

## 5. What Do Reading and Removing Through Views Do?

### 5.1. Removing a Key Through a View Removes the Mapping

If the source is `{A=10, B=20, C=30}`:

~~~text
keys.removeFirst()             returns A
map after                      {B=20, C=30}
~~~

It does not merely remove a label from a display list. The value `10` along with the mapping for key `A` is no longer in the map.

When you only need to hide a key in the UI while keeping the source data intact, build a separate display sequence or a suitable filtered result. Do not use a view's remove operation as a “remove from screen” action if the source still needs to retain the mapping.

### 5.2. Removing a Value Through a View Also Removes the Entire Mapping

`values.removeLast()` removes the value of the last mapping and deletes that mapping from the map. For `{A=10, B=20, C=30}`, it returns `30` and removes key `C`.

If values are duplicated, a removal by value cannot be interpreted as identifying a specific key. In the program, the `LinkedHashMap` view has `[5, 20, 20]`; `remove(20)` removes one matching mapping, not all mappings with `20`. The example verifies that this implementation picks the first match in the current iteration direction. If your business logic requires removing a specific key, remove by key; do not rely on a duplicate value to guess the key.

The `Collection.remove(Object)` contract is to remove a single matching element if present, not to remove all occurrences. [Java 21: Collection.remove](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

### 5.3. Removing an Entry Returns Both Key and Value

`entries.removeFirst()` on a view that supports removal gives you the entry of the removed first mapping. This can be a clearer choice than removing a value when you need to know which ID was dropped.

However, do not assume that every entry obtained this way is a mutable object permanently connected to the map. Entry lifecycle and `setValue` support are separate questions, explained in the next section.

### 5.4. Empty State Differs from the Map's Boundary Entry API

`SequencedCollection.getFirst()` and `getLast()` throw `NoSuchElementException` when the collection is empty. The removing methods additionally require that the source supports removal. [Java 21: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html).

Consequently, on an empty map:

~~~text
map.firstEntry()                    null
map.sequencedKeySet().getFirst()    NoSuchElementException
~~~

The two calls do not share the same missing-data convention even though both concern the first boundary. Choose according to the return type and error policy your method needs.

## 6. Why Views Are Not a Shortcut for Adding or Moving Mappings

On `LinkedHashMap` views:

- `keys.addFirst(k)` and `keys.addLast(k)` are not supported;
- `values.addFirst(v)` and `values.addLast(v)` are not supported;
- `entries.addFirst(entry)` and `entries.addLast(entry)` are also not supported.

This still applies even when the key already exists. Do not treat the key view like an independent `LinkedHashSet` and expect it to reposition a mapping.

A lone key does not carry the value needed to form a mapping. A lone value does not identify a key. Even an entry, which has both parts, does not turn a view into an arbitrary map insertion/positioning API. The map source owns the ability to add or position mappings via `putFirst` and `putLast` when supported.

The OpenJDK 21 source code of `LinkedHashMap` directly shows that boundary add operations on the views are rejected, whereas boundary remove operations delegate to removing the underlying mapping. This serves as evidence for the implementation used in the example. [OpenJDK 21: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java).

The key takeaway is that **permitted operations cannot be inferred solely from the return type name**. `SequencedSet` and `SequencedCollection` define optional operations; the backing source of the view decides which ones are supported.

## 7. An Entry Can Be a Snapshot or a Live Element Connected to the Map

A common mistake is seeing the type `Map.Entry<K,V>` and assuming that calling `setValue` will always mutate the map.

Distinguish three ways of obtaining an entry:

| How obtained | What you can rely on |
| --- | --- |
| `map.firstEntry()`, `lastEntry()`, `pollFirstEntry()`, `pollLastEntry()` | The entry is a snapshot of the mapping at call time; does not support mutating the source via `setValue` |
| An entry obtained while iterating the entry view | Connection to the source is guaranteed during iteration; `setValue` can update the value if the source supports it |
| `map.sequencedEntrySet().getFirst()` | The `SequencedMap` interface does not universally specify whether that entry is connected/mutable or not |

### 7.1. firstEntry Is Not a Handle for Mutating a Mapping

For example, with source `{E=5, D=20}`:

~~~java
java.util.Map.Entry<String, Integer> before = map.firstEntry();
map.putFirst("E", 50);
~~~

The `before` entry still describes `E=5`; the current mapping in the map is `E=50`. Calling `before.setValue(999)` is not a way to update the map and is rejected on this snapshot entry.

An entry snapshot copies the pair of key/value references, rather than automatically deep-copying all internal state of the objects. The example uses immutable strings and integers to keep the outcome clear.

### 7.2. Updating Through an Entry During Iteration

With a supporting source, you can use:

~~~java
for (java.util.Map.Entry<String, Integer> entry
        : map.sequencedEntrySet()) {
    if (entry.getKey().equals("D")) {
        entry.setValue(21);
    }
}
~~~

This snippet is for a mutable `LinkedHashMap` in a single-threaded example. It updates the **value** through the iteration entry, without calling `putFirst` to alter the order during that loop.

The `Map.Entry` contract ties the connection to the map to how the entry was obtained and the lifetime of the iteration. Do not hold onto an entry iterator long-term, mutate the map through another path, and still treat that entry as a valid handle. If you need an independent entry, copy it according to an appropriate policy; `Map.Entry.copyOf` does not accept `null` keys or values. [Java 21: Map.Entry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.Entry.html).

### 7.3. Do Not Generalize from One Test of getFirst().setValue()

One implementation may return a connected entry when you call `sequencedEntrySet().getFirst()`; another may return a snapshot or reject mutation. To write code that relies only on the general interface, do not turn an observation about one class into a guarantee for all maps.

If the intent is to update a key, the direct map API is usually clearer. If the intent is to iterate and update each entry's value on a supporting source, use the iteration contract. Choose the operation path based on intent rather than trying whichever method happens to work.

## 8. reversed Flips the Map and All Related Views

With a source:

~~~text
original map:     {A=1, B=2, C=3}
reversed map:     {C=3, B=2, A=1}
reversed keys:    [C, B, A]
reversed values:  [3, 2, 1]
~~~

`map.reversed()` is a reversed-order view. The key, value, and entry views of the reversed map also follow that reversed order.

On a `LinkedHashMap` that supports positioning:

- `map.reversed().putFirst(k, v)` places the mapping at the front of the reversed view, which corresponds to the end of the source;
- `map.reversed().putLast(k, v)` places it at the end of the reversed view, which corresponds to the front of the source.

Example:

~~~text
source before                     {A=1, B=2, C=3}
reversed.putFirst(B, 20)
source after                      {A=1, C=3, B=20}
reversed view after               {B=20, C=3, A=1}
~~~

The returned previous value still belongs to the updated key; reversing does not change which key the call targets.

With `LinkedHashMap`, mutations through the reversed map and its views propagate to the source, and source mutations are visible through the views. The general interface leaves certain visibility details of changes to implementations, so distinguish concrete class contracts from what is common to all `SequencedMap` implementations.

If you only need to output a report in reverse order, iterate the reversed view. There is no need to move every mapping in the source to invert the entire dataset and then invert it back.

## 9. Not Every Ordered Map Supports putFirst/putLast

### 9.1. SortedMap and TreeMap

`SortedMap` positions mappings by key comparison. Therefore, `putFirst` and `putLast` reject explicit positioning with `UnsupportedOperationException`. This remains true even if the key happens to already belong at that boundary. [Java 21: SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html#putFirst(K,V)).

`TreeMap` uses the keys' natural ordering or a `Comparator`, not value ordering, and it does not switch to insertion order when referenced as a `SequencedMap`. [Java 21: TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

To insert or update in a sorted map, use `put` and let the source determine the position. If a product requirement calls for arbitrarily pinning an item, revisit the ordering model; do not catch the exception and pretend the position was updated.

### 9.2. Unmodifiable Maps and Their Views

`Collections.unmodifiableSequencedMap(source)` returns a read-only view with the same sequenced expressiveness. It blocks modifications through the map and through its collection views. [Java 21: Collections.unmodifiableSequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableSequencedMap(java.util.SequencedMap)).

Blocking modifications through the view does not turn the source into an immutable snapshot. If another part of the code calls `source.putLast`, the read-only view can observe the source's new order per the wrapper's contract.

To keep the structure isolated, you can create `new LinkedHashMap<>(source)` first and then wrap the copy. This preserves the encounter order copied into the linked map; it does not deep-copy the key or value objects.

Do not substitute `Map.copyOf` merely because its name contains “copy” and assume it still provides the `SequencedMap` contract or your desired display order. Choose the tool based on both mutability and ordering requirements.

## 10. Complete Program

Save the code below into **`SequencedMapViewsDemo.java`**. The views are obtained before multiple updates to demonstrate that they are not copies. The program uses single-threaded sources; do not hold iterators across positioning operations.

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.SequencedCollection;
import java.util.SequencedMap;
import java.util.SequencedSet;
import java.util.TreeMap;

public class SequencedMapViewsDemo {
    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | NoSuchElementException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        SequencedMap<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 10);
        map.put("B", 20);
        map.put("C", 20);
        SequencedSet<String> keys = map.sequencedKeySet();
        SequencedCollection<Integer> values = map.sequencedValues();
        SequencedSet<Map.Entry<String, Integer>> entries = map.sequencedEntrySet();

        Integer previous = map.putFirst("B", 200);
        System.out.println("putFirst existing: previous=" + previous + ", map=" + map);
        previous = map.putLast("A", 100);
        System.out.println("putLast existing: previous=" + previous + ", map=" + map);
        previous = map.putFirst("Z", 0);
        System.out.println("putFirst new: previous=" + previous + ", map=" + map);
        System.out.println("live keys: " + keys);
        System.out.println("live values: " + values);
        System.out.println("live entries: " + entries);

        System.out.println("key view removeFirst: " + keys.removeFirst());
        System.out.println("after key removal: " + map);
        System.out.println("value view removeLast: " + values.removeLast());
        System.out.println("after value removal: " + map);
        System.out.println("entry view removeFirst: " + entries.removeFirst());
        System.out.println("after entry removal: " + map);

        map.putLast("D", 20);
        map.putFirst("E", 5);
        System.out.println("duplicate values: " + values);
        boolean removed = values.remove(Integer.valueOf(20));
        System.out.println("remove one matching value: " + removed + ", map=" + map);
        System.out.println("same key view now: " + keys);

        Map.Entry<String, Integer> snapshot = map.firstEntry();
        map.putFirst("E", 50);
        System.out.println("snapshot and current: " + snapshot + " / " + map.firstEntry());
        System.out.println("snapshot setValue: " + failure(() -> snapshot.setValue(999)));
        for (Map.Entry<String, Integer> entry : entries) {
            if (entry.getKey().equals("D")) {
                entry.setValue(21);
            }
        }
        System.out.println("iterator entry update: " + map);

        SequencedMap<String, Integer> backwards = map.reversed();
        previous = backwards.putFirst("E", 500);
        System.out.println("reverse putFirst: previous=" + previous + ", base=" + map);
        System.out.println("reverse map: " + backwards);
        backwards.putLast("X", 9);
        System.out.println("reverse putLast new, base: " + map);
        System.out.println("reverse keys: " + backwards.sequencedKeySet());

        System.out.println("key addFirst: " + failure(() -> keys.addFirst("D")));
        System.out.println("value addLast: " + failure(() -> values.addLast(30)));
        System.out.println("entry addFirst: "
                + failure(() -> entries.addFirst(Map.entry("Y", 1))));

        SequencedMap<String, Integer> empty = new LinkedHashMap<>();
        System.out.println("empty map firstEntry: " + empty.firstEntry());
        System.out.println("empty key view getFirst: "
                + failure(() -> empty.sequencedKeySet().getFirst()));

        SequencedMap<String, Integer> nullable = new LinkedHashMap<>();
        nullable.putLast("nullValue", null);
        boolean existed = nullable.containsKey("nullValue");
        previous = nullable.putFirst("nullValue", 7);
        System.out.println("previous null: existed=" + existed + ", previous=" + previous);
        nullable.putLast(null, 9);
        System.out.println("null key: " + nullable);

        SequencedMap<Integer, String> sorted = new TreeMap<>();
        sorted.put(2, "two");
        sorted.put(1, "one");
        System.out.println("sorted putFirst existing: "
                + failure(() -> sorted.putFirst(1, "ONE")));
        System.out.println("sorted remains: " + sorted);

        SequencedMap<String, Integer> readOnly =
                Collections.unmodifiableSequencedMap(map);
        LinkedHashMap<String, Integer> saved = new LinkedHashMap<>(map);
        System.out.println("read-only putFirst: "
                + failure(() -> readOnly.putFirst("D", 2)));
        System.out.println("read-only view removeFirst: "
                + failure(() -> readOnly.sequencedValues().removeFirst()));
        map.putLast("F", 6);
        System.out.println("read-only sees source keys: " + readOnly.sequencedKeySet());
        System.out.println("saved copy keys: " + saved.sequencedKeySet());
        System.out.println("map equals reverse: " + map.equals(map.reversed()));

        LinkedHashMap<String, Integer> access =
                new LinkedHashMap<>(16, 0.75f, true);
        access.put("A", 1);
        access.put("B", 2);
        access.put("C", 3);
        access.get("A");
        System.out.println("access after get A: " + access.sequencedKeySet());
        access.putFirst("C", 30);
        System.out.println("access explicit first C: " + access.sequencedKeySet());
        System.out.println("access firstEntry: " + access.firstEntry());
        System.out.println("access after firstEntry: " + access.sequencedKeySet());
        access.get("C");
        System.out.println("access after get C: " + access.sequencedKeySet());
    }
}
~~~

Compile with JDK 21 or later and run on Java 21 or later:

~~~shell
javac --release 21 -encoding UTF-8 SequencedMapViewsDemo.java
java SequencedMapViewsDemo
~~~

No `--enable-preview` is required. The example was compiled with release level 21 and ran successfully on OpenJDK 24.0.2.

Exact stdout:

~~~text
putFirst existing: previous=20, map={B=200, A=10, C=20}
putLast existing: previous=10, map={B=200, C=20, A=100}
putFirst new: previous=null, map={Z=0, B=200, C=20, A=100}
live keys: [Z, B, C, A]
live values: [0, 200, 20, 100]
live entries: [Z=0, B=200, C=20, A=100]
key view removeFirst: Z
after key removal: {B=200, C=20, A=100}
value view removeLast: 100
after value removal: {B=200, C=20}
entry view removeFirst: B=200
after entry removal: {C=20}
duplicate values: [5, 20, 20]
remove one matching value: true, map={E=5, D=20}
same key view now: [E, D]
snapshot and current: E=5 / E=50
snapshot setValue: UnsupportedOperationException
iterator entry update: {E=50, D=21}
reverse putFirst: previous=50, base={D=21, E=500}
reverse map: {E=500, D=21}
reverse putLast new, base: {X=9, D=21, E=500}
reverse keys: [E, D, X]
key addFirst: UnsupportedOperationException
value addLast: UnsupportedOperationException
entry addFirst: UnsupportedOperationException
empty map firstEntry: null
empty key view getFirst: NoSuchElementException
previous null: existed=true, previous=null
null key: {nullValue=7, null=9}
sorted putFirst existing: UnsupportedOperationException
sorted remains: {1=one, 2=two}
read-only putFirst: UnsupportedOperationException
read-only view removeFirst: UnsupportedOperationException
read-only sees source keys: [X, D, E, F]
saved copy keys: [X, D, E]
map equals reverse: true
access after get A: [B, C, A]
access explicit first C: [C, B, A]
access firstEntry: C=30
access after firstEntry: [C, B, A]
access after get C: [B, A, C]
~~~

### 10.1. Updating and Positioning

The first three lines distinguish two existing keys from a new key. The previous values of `B` and `A` are returned; `Z` is newly inserted with result `null`.

All three previously obtained views reflect the updated map. They read the same sequence of mappings, but project different element types.

### 10.2. Removing Through Views and Duplicate Values

Removing the first key removes `Z` from the map; removing the last value removes the mapping for `A`; removing the first entry then removes the mapping for `B`. Changes are not confined to a separate “list” held by each view.

After adding `E` and `D`, the value `20` appears twice. Calling `remove(20)` on the value view of this source removes only one matching mapping; the subsequent map line shows that key `C` is gone while `D` remains.

### 10.3. Snapshot Entries and Iterator Entries

`snapshot` still holds `E=5` after the map has updated to `E=50`, and rejects `setValue`. The entry loop afterwards changes `D` to `21` directly through the entry obtained during iteration on the supporting source.

Do not use the outcomes of these two approaches to conclude that every `Map.Entry` has the same mutability permissions.

### 10.4. Reversed View, Restricted Sources, and Copies

`backwards.putFirst("E", 500)` moves `E` to the end of the source. `backwards.putLast("X", 9)` places the new key at the front of the source.

Add operations on the views are rejected. The sorted map also rejects positioning. The read-only wrapper blocks both `putFirst` and removing through the value view, yet sees key `F` added through the source. The `saved` copy preserves the structure from before that addition.

## 11. Be Careful with LinkedHashMap Access-Order

`LinkedHashMap` uses insertion order by default. The constructor with a final argument of `true` creates access-order mode: access operations defined by the class can move a mapping to the end of the source.

Example at the end of the program:

~~~text
initially after put calls        [A, B, C]
get(A)                           [B, C, A]
putFirst(C, 30)                  [C, B, A]
firstEntry()                     still [C, B, A]
get(C)                           [B, A, C]
~~~

`putFirst` is explicit positioning, not to be understood as a normal access that automatically pushes the item to the end. However, a subsequent `get` can still change the position according to the access-order policy.

Therefore, a sequence like “move C to the front, then read its value with get(C) to print it” can both inspect C and move C away from the front. When you only need to display the mappings of an access-order source, consider iterating entries instead of iterating keys and calling `get` for each key.

This is also why first and last cannot be defined simply by insertion time for every `LinkedHashMap`. You must know the mode the map was constructed with and which events change the order.

## 12. Choosing How to Apply and Test

### 12.1. Need Both Key and Value: Prefer Iterating Entries

A report that needs key-value pairs should read entries directly:

~~~java
for (var entry : report.reversed().sequencedEntrySet()) {
    System.out.println(entry.getKey() + " = " + entry.getValue());
}
~~~

This is a Java 21 snippet, assuming `report` is a suitable source and is not concurrently modified during iteration. It clearly shows the report output direction and avoids an extra lookup per key.

### 12.2. Moving Position While Preserving Value Requires Its Own Contract

`putFirst` requires you to pass a value. If you want “move an existing key only and keep its current value,” design a helper with clear policies for missing keys, `null` values, and concurrent modifications.

With an access-order source, `get` itself can change the order before the positioning operation. With a multi-threaded source, reading and then writing the old value can overwrite another update. Do not advertise a simple read-then-write helper as an atomic move operation.

### 12.3. Test Both Contents and Order

`Map.equals` checks for the same mappings, not iteration order. A map and its reversed view can be equal. [Java 21: Map.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

Therefore, positioning tests should include at least two independent checks:

- each key maps to the right value;
- the list of keys or entries in the intended direction has the right order.

Do not use `equals` against an expected map as the sole proof that `putFirst` placed an item at the right position. Nor should you use `size` to detect every change: updating and moving an existing key usually leaves the mapping count unchanged.

### 12.4. Concurrency, Iterators, and Performance

Linked maps are not thread-safe by themselves. Value updates, positioning, and removals through views must obey the source's access policy. Avoid holding an iterator and invoking operations that can change the order through another path.

If you need a multi-step operation—such as checking pinning permission, reading the value, moving position, and recording history—as a single consistent unit, a locking or coordination mechanism must cover the entire sequence. Fail-fast behavior only helps detect some errors; it does not replace locks or transactions.

Performance comes from the hash/linked or tree implementation, not from the `SequencedMap` name. Using the common interface expresses the contract; it does not promise that every operation on every source has the same complexity.

## 13. Common Pitfalls

| Pitfall | Consequence | How to handle |
| --- | --- | --- |
| Treating `putFirst` as only changing order | Accidentally overwrites the value | Account for both updating and positioning |
| Seeing a `null` previous value and concluding the key is new | Wrong when the key already mapped to `null` | Distinguish presence per the source's contract |
| Removing from a view just to hide a row | The source mapping is deleted | Build separate display data if needed |
| Adding or moving keys through a view | `UnsupportedOperationException` | Use the map API that supports the operation |
| Assuming every entry is mutable | Errors or implementation dependence | Distinguish snapshots, iterator entries, and other sources |
| Treating the reversed view as a copy | Mutations change the source at the opposite end | Choose view vs. copy based on ownership |
| Calling `TreeMap.putFirst` when the key is already the smallest | Still rejected | Use `put` per comparison rules |
| Iterating keys then calling `get` on access-order | Order can change during iteration | Iterate entries or design an appropriate snapshot |
| Using only `Map.equals` to test pinning | Misses ordering bugs | Compare the sequence separately |
| Treating an unmodifiable wrapper as a fixed snapshot | Unexpected changes through the source | Define lifecycle and copying strategy |

## 14. Practice with Answers

### Exercise 1 — Updating Both Boundaries

An insertion-order `LinkedHashMap` holds `{A=1, B=2, C=3}`. Call `putFirst("B", 20)` then `putLast("A", 10)`. What are the two return values and the final map?

**Answer:** returns `2` then `1`. Final map is `{B=20, C=3, A=10}`, and size remains 3. Each call updates the value while positioning the mapping.

### Exercise 2 — Previous null

A map has key `K` mapped to `null`. `putLast("K", 9)` returns `null`. Can you conclude this was a new key insertion?

**Answer:** no. The result is the previous value, which can be `null` from an existing mapping. If you need to distinguish, check presence under a consistent access protocol; do not treat `containsKey` followed by an update as an automatic transaction across multiple threads.

### Exercise 3 — Removing the Last Value

The map is `{P=5, Q=5, R=8}`. What does `sequencedValues().removeLast()` on a mutable view return, and how does it affect the source?

**Answer:** returns `8` and removes the entire mapping for `R`, leaving the source as `{P=5, Q=5}`. It does not merely modify a value collection detached from the map. If you need to know which key was removed as well, look at the appropriate boundary entry API.

### Exercise 4 — Does the Key View Have Enough Permissions?

Given `SequencedSet<String> keys = map.sequencedKeySet()` from a `LinkedHashMap`. Why is `keys.addFirst("Q")` not a way to pin an existing key to the front?

**Answer:** the view does not support this add/positioning operation, even for an existing key. You must operate on the map through an API with the appropriate contract and manage the associated value. The `SequencedSet` type does not mean all optional mutating operations are supported.

### Exercise 5 — Two Ways of Obtaining an Entry

`before = map.firstEntry()` when the first entry is `A=1`. Later the map changes `A` to `10`. Should you call `before.setValue(100)` to mutate the map further?

**Answer:** no. That entry is a snapshot that does not allow updating the source via `setValue`. It continues to describe the value at the time it was taken. To update the mapping, use the appropriate map API; if using an entry during iteration, obey the permissions and lifecycle of the entry iterator on a supporting source.

### Exercise 6 — Positioning Through the Reversed View

Source `{A=1, B=2, C=3}`. Call `map.reversed().putLast("B", 200)` on a mutable linked map. What are the source and the reversed view afterwards?

**Answer:** the end of the reversed view is the front of the source, so the source becomes `{B=200, A=1, C=3}`; the reversed view is `{C=3, A=1, B=200}`. The returned previous value is `2`.

### Exercise 7 — Access-Order Map

An access-order map has keys in sequence `[A, B, C]`. Call `putFirst("B", 20)` then `get("B")`. Can you promise `B` is still at the front after this snippet?

**Answer:** no. The positioning call produces `[B, A, C]`, but the subsequent `get` counts as an access that moves `B` to the end of the source, resulting in `[A, C, B]`. When inspecting or outputting data, know which read operations also affect the order.

### Exercise 8 — Read-Only, Copying, and Testing Order

An API returns `Collections.unmodifiableSequencedMap(source)`. Later the source inserts a key at the front. Is the returned result guaranteed to stay unchanged, and is an `equals` test enough to verify order?

**Answer:** the wrapper is a view, not an independent snapshot. To preserve the structure at a point in time, make a copy that preserves the ordering policy and wrap it if appropriate; you still need to decide on deep copying if keys or values are mutable. `Map.equals` ignores order, so you must check the key or entry sequence separately.

When extending the program yourself, try a new key, a key already at the target boundary, two mappings with the same value, and an empty source. For each call, record three things: the return value, the mapping contents, and the iteration order. This verification habit helps clearly separate positioning, updating, and view effects.
