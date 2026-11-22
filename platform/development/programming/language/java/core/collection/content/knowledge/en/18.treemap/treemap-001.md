# TreeMap, SortedMap, NavigableMap, and Key Ordering

A regular map answers the question "which value does this key map to?". Many problems also need to know the first key, the key closest to a threshold, or all keys within a range. For example, a configuration table with effective timestamps needs to find the latest configuration that is no later than the timestamp under consideration.

`TreeMap` solves this class of problems by keeping keys according to a comparison rule. `SortedMap` and `NavigableMap` are two interfaces describing order-related capabilities; they are not two separate modes that have to be turned on in TreeMap.

This lesson uses Java 17. The goal is to understand the relationship between the three names, read the meaning of key ordering accurately, choose neighborhood and range queries, and distinguish between a shared-data view and an independent copy.

## 1. From Map to NavigableMap

The interface hierarchy in Java 17 can be read as a chain:

~~~text
Map<K, V>
    ↑
SortedMap<K, V>
    ↑
NavigableMap<K, V>
    ↑ implemented by
TreeMap<K, V>
~~~

The arrows represent that the type below has the capabilities of the type above. `TreeMap` is a concrete class, while the first three names are interfaces.

| Type | What it adds or represents |
|---|---|
| Map | Key–value mappings |
| SortedMap | Total ordering on keys, first/last keys, and ranges |
| NavigableMap | Neighbor key lookup, range bound control, reverse order, and polling/removing both ends |
| TreeMap | A NavigableMap implementation based on a red–black tree |

`TreeMap` guarantees `O(log n)` time cost for `containsKey`, `get`, `put`, and `remove`. This lesson does not go into tree-balancing algorithms; what matters for the API is that the data is already ordered to support threshold and range queries. [Java 17: TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

### 1.1. SortedMap is not yet NavigableMap as a variable type

A TreeMap object can be referenced through multiple types:

~~~java
TreeMap<Integer, String> tree = new TreeMap<>();
Map<Integer, String> general = tree;
SortedMap<Integer, String> sorted = tree;
NavigableMap<Integer, String> navigable = tree;
~~~

These are illustrative declarations, not a standalone program.

All four variables point to the same object. Iterating over `general.entrySet()` still follows the order maintained by TreeMap. Changing the reference type does not turn the object into a HashMap and does not erase its ordering.

However, which methods can be called at compile time depends on the declared type:

- `general` has the methods of Map.
- `sorted` adds `firstKey`, `lastKey`, and the range methods of SortedMap.
- `navigable` adds `floorEntry`, `ceilingKey`, `descendingMap`, and other navigation methods.

If a method needs navigation capabilities, it should express that requirement with an appropriate `NavigableMap` parameter. It should not accept a Map and blindly cast it under the assumption that callers always pass a TreeMap.

### 1.2. Why is more than one interface needed?

A function that only counts mappings does not need to require a specific tree class. A function that needs neighboring keys requires a stronger contract than Map. Interfaces help state clearly what the function needs from the data.

For example, a feature that looks up a configuration version at a point in time may need `floorEntry`. Declaring the parameter as NavigableMap makes that capability explicit in the signature, rather than hiding a TreeMap assumption inside the body.

## 2. Which rule does TreeMap use to order keys?

### 2.1. Natural ordering

If no comparator is passed, TreeMap uses the natural ordering of keys via `Comparable.compareTo`. Keys must be mutually comparable.

For `Integer`, the usual order is numerical order. Inserting `40, 10, 30, 20` still yields the iteration order `10, 20, 30, 40`.

For `String`, the rule is defined by `String.compareTo`. You should not assume it matches Vietnamese alphabetical sorting rules for an application's locale needs. The comparison rule must be chosen according to the data and business domain. [Java 17: Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)

### 2.2. Custom Comparator

A comparison object can be provided when creating the map:

~~~java
NavigableMap<Integer, String> decreasing =
        new TreeMap<>(Comparator.reverseOrder());
~~~

Then the map's order is reversed. "Smallest key", "before", and "after" in navigation methods must all be interpreted according to this comparator, not automatically as ascending numerical order.

`comparator()` returns the comparator currently in use, or null if natural ordering is used. A null result here does not mean the map is unordered.

`Comparator` must establish a consistent comparison relation, such as transitivity. When comparing integers, do not write `a - b` to get the sign because overflow can break the relation. Use `Integer.compare(a, b)` or appropriate comparator factory methods. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

### 2.3. Ordered by key, not by value

Suppose a map has the pairs:

~~~text
40 -> forty
10 -> ten
30 -> thirty
20 -> twenty
~~~

Iterating over entrySet in ascending key order yields `10=ten, 20=twenty, 30=thirty, 40=forty`. Iterating over values yields `ten, twenty, thirty, forty` because values follow the mappings of their corresponding keys. That does not mean the value strings are sorted alphabetically.

The order is not insertion order either. If first-seen order is needed, that is a different requirement. TreeMap maintains a comparison rule; it does not record insertion history to use as iteration order.

`SortedMap` defines the key ordering reflected when iterating over the `keySet`, `entrySet`, and `values` views. [Java 17: SortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html)

## 3. Comparing equal to 0 affects key identity as well

A Comparator does not merely decorate how data is printed. TreeMap uses comparison to identify keys in its structure.

### 3.1. Two different strings can occupy the same slot

With a case-insensitive comparator, `"java"` and `"JAVA"` compare as 0. Adding those two keys in sequence can produce a single mapping where the later value replaces the earlier value, rather than two mappings.

In the code below:

~~~java
TreeMap<String, Integer> folded =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
folded.put("java", 1);
folded.put("JAVA", 2);
~~~

The result has one mapping, and looking up `"JaVa"` returns 2. The example only asserts the mapping count and the looked-up value; do not rely on which key representative is retained to explain business identity.

This is often misunderstood as "data lost by the tree". In fact, the comparison rule stated that the two keys belong to the same comparison position.

### 3.2. Consistency with equals

To adhere to the equals-based Map contract, a sorted map's ordering should be consistent with equals: comparing equal to 0 corresponds to being equal according to equals.

A case-insensitive comparator for String does not have that consistency, because `"java".equals("JAVA")` is false. The example intentionally exposes this difference, not to recommend using that comparator for every identifier catalog. [Java 17: relation between comparison and equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

If the domain is genuinely case-insensitive, you can design an appropriately normalized key representation. If two records with the same score or display name must both be kept, an additional tie-breaking criterion is required instead of accidentally merging them.

Partial illustrative example with a record key:

~~~java
record RankKey(int score, long id) {}

Comparator<RankKey> byScoreThenId =
        Comparator.comparingInt(RankKey::score)
                  .thenComparingLong(RankKey::id);

NavigableMap<RankKey, String> ranking =
        new TreeMap<>(byScoreThenId);
~~~

Two keys with different ids but the same score still compare non-zero thanks to the secondary criterion. For this record, equals also checks those two components.

### 3.3. Keep compared components stable

If a key is already in the tree and a field used for comparison is mutated, that object's ordering relation with other keys may no longer match the position where it was placed. Do not assume the map will automatically detect this and reposition the key.

Immutable keys make data organization clearer. When information affecting ordering must change, design an operation that removes the old key and inserts a new key in a controlled state, rather than mutating the object currently serving as a key in place.

## 4. SortedMap: both ends and three range types

### 4.1. First and last keys

`firstKey()` returns the first key according to the map's order, and `lastKey()` returns the last key. On a natural-order map containing `10, 20, 30, 40`, the results are 10 and 40.

On a descending map of the same numbers, first is 40 and last is 10. "First" is the start of the map's order, not necessarily the smallest number in ascending numerical reading.

If the map is empty, these two methods throw `NoSuchElementException`. When you want a possibly absent result without using exceptions, NavigableMap provides methods that return entries at both ends.

### 4.2. Default ranges of SortedMap

According to the current ordering, the methods are:

| Method | Key condition k |
|---|---|
| subMap(a, b) | a ≤ k < b |
| headMap(b) | k < b |
| tailMap(a) | k ≥ a |

The ≤ and < symbols in the table denote the relation under the comparator or natural ordering currently in use.

With keys `10, 20, 30, 40` in ascending numerical order:

~~~text
subMap(20, 40) -> 20, 30
headMap(30)    -> 10, 20
tailMap(30)    -> 30, 40
~~~

The default subMap range includes the lower bound and excludes the upper bound. This notation is commonly called a half-open interval `[a, b)`.

Bounds do not have to be existing keys. With the same data, `subMap(15, 35)` selects 20 and 30. Bounds are used for range comparison, not as a requirement that two boundary mappings must be found.

### 4.3. Choosing ranges by business requirements

Half-open intervals allow adjacent regions to be joined without duplicating boundaries: `[a, b)` followed by `[b, c)`. For example, a single-day report can use the start of the current day and the start of the next day instead of computing an "end-of-day timestamp" with an assumed precision.

This is why you should design the range before calling the method. When the domain requires including both endpoints, use the NavigableMap overload with boolean parameters rather than accidentally dropping the upper bound by misremembering the default.

## 5. NavigableMap: finding neighboring keys

### 5.1. Four relations to distinguish

Given target x and the map's order:

| Group | Selected key |
|---|---|
| lowerKey(x), lowerEntry(x) | Greatest key strictly less than x |
| floorKey(x), floorEntry(x) | Greatest key less than or equal to x |
| ceilingKey(x), ceilingEntry(x) | Least key greater than or equal to x |
| higherKey(x), higherEntry(x) | Least key strictly greater than x |

You can remember them by separating two questions: are you looking before or after, and is an exact match with the target accepted?

With keys `10, 20, 30, 40` in numerical order:

| Target | lower | floor | ceiling | higher |
|---|---:|---:|---:|---:|
| 20 | 10 | 20 | 20 | 30 |
| 25 | 20 | 20 | 30 | 30 |
| 5 | None | None | 10 | 10 |
| 45 | 40 | 40 | None | None |

The methods return null when no matching result exists. The `Key` variants return the key; the `Entry` variants return both key and value. [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html)

### 5.2. Effective-from configuration example

Suppose the keys are effective start timestamps:

~~~text
10 -> config A
20 -> config B
30 -> config C
~~~

To know the configuration at timestamp 25, use floorEntry(25), which returns the mapping at 20. Using lowerEntry(25) also gives 20 in this example, but at exact timestamp 20, lowerEntry would return the entry at 10, which violates the requirement.

That is why you must test exact boundary cases too, not just pick a target between two keys. When data can be absent at the start of the timeline, you also need to define what happens when floorEntry returns null: is there no valid configuration, or should a default configuration be used?

### 5.3. Order neighbors are not nearest by distance

Lower, floor, ceiling, and higher describe order relations. They do not automatically return "the value with the smallest arithmetic distance".

For example, with keys 10 and 100, finding the key closest to 90 requires comparing distances after fetching the relevant candidates. Calling floorKey(90) alone only gives the lower candidate 10, not the "nearest" key by distance.

With timestamps, addresses, or versions, the business relation may not be numerical distance. Name what the application actually needs.

### 5.4. When values or keys can be null

A non-null result entry can hold a null value. Therefore, do not check `entry.getValue() == null` to conclude that nothing was found.

If a comparator permits null keys, key-returning methods can be ambiguous between "the resulting key is null" and "no result". The entry-returning form lets you distinguish them via the entry object itself.

You must check the null rules of the implementation; do not infer from an interface that every map allows null.

## 6. Both ends: peeking and polling are different operations

NavigableMap provides the methods:

| Method | Effect |
|---|---|
| firstEntry() | Views the first mapping without removing it |
| lastEntry() | Views the last mapping without removing it |
| pollFirstEntry() | Retrieves and removes the first mapping |
| pollLastEntry() | Retrieves and removes the last mapping |

An empty map returns null for all of the above methods. The name `poll` is a reminder that the operation mutates the map when a result exists.

For example, using pollFirstEntry to "peek at the smallest key" during logging will accidentally remove it from the data. If you only want to observe, choose firstEntry or firstKey depending on how you want an empty map handled.

### 6.1. Entries from TreeMap navigation queries

The entries returned by TreeMap navigation methods such as firstEntry, floorEntry, or pollFirstEntry are snapshots of the mapping at the time of creation. They do not support setValue to write back to the map. To modify an existing mapping, perform the appropriate map operation.

Do not overgeneralize this statement to "every Map.Entry in Java is immutable". Entries obtained while iterating over entrySet have their own contract; a pair returned from a navigation query and an entry from an iteration view should not be treated as having the same relationship to the map.

A snapshot pair does not mean deep-copying the value object either. The example uses String so that comparing old and new values is unambiguous.

## 7. Inclusive and exclusive bounds in NavigableMap

Additional overloads allow choosing each bound individually:

~~~java
NavigableMap<Integer, String> middle =
        map.subMap(20, true, 40, false);

NavigableMap<Integer, String> upTo30 =
        map.headMap(30, true);

NavigableMap<Integer, String> after30 =
        map.tailMap(30, false);
~~~

This is an illustrative snippet using an existing map variable, not a standalone program.

Results on data 10, 20, 30, 40:

~~~text
subMap(20, true, 40, false) -> 20, 30
headMap(30, true)          -> 10, 20, 30
tailMap(30, false)         -> 40
~~~

`true` means include that bound if a key compares equal to it; `false` means exclude it.

If both bounds are equal, the flags still matter. A range inclusive on both ends can contain a key equal to the bound if that key exists; a range excluding at least one end cannot contain it. The default `subMap(a, a)` is an empty range.

If the start bound comes after the end bound in the map's order, the range request is invalid. Do not assume "start less than end" always means ascending numerical comparison; the reverse-order section will illustrate this.

## 8. Ranges are shared-data views

### 8.1. No automatic copy is created

`subMap`, `headMap`, and `tailMap` on TreeMap return a `view` into the data. Valid changes through the view are reflected in the original map; changes to the original map within the range are also visible through the view.

Example:

~~~text
original map: 10, 20, 30, 40
view [20,40): 20, 30

add 35 via view:
original map: 10, 20, 30, 35, 40
view:         20, 30, 35

remove 20 via view:
original map: 10, 30, 35, 40
view:         30, 35
~~~

You can think of a view as a "key-restricted window" into the same data, not a newly detached table.

### 8.2. Out-of-range writes are rejected

For the view `[20,40)`, putting key 40 or 45 through the view throws `IllegalArgumentException`. Even if 40 already exists in the original map, it is still outside the view's range because the upper bound is excluded.

A view's bounds do not forbid the original map from having keys outside the range; they restrict which keys the view represents and allows inserting through the view. A `get` for an out-of-range key does not turn into a write and should not be interpreted as a request to widen the view.

Nested views continue to be constrained by existing bounds. Do not use a view to expand beyond its parent view's window. [Java 17: contract of TreeMap key ranges](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

### 8.3. Clearing a view differs from clearing the whole map

`view.clear()` removes the mappings within the view's range from the underlying data. It does not merely empty a separate display, nor does it remove keys outside the range.

This is useful for deleting a range, but it must be treated as an operation that mutates the original data. Naming variables to reflect the range helps prevent mistakes, such as `expiredByTime` instead of a generic name like `temp`.

### 8.4. When an independent copy is needed

You can construct a new TreeMap from an existing SortedMap or NavigableMap:

~~~java
NavigableMap<Integer, String> window =
        source.subMap(20, true, 40, false);

TreeMap<Integer, String> copy = new TreeMap<>(window);
~~~

The copy has an independent structure; later modifications to the view do not automatically add or remove mappings in copy. Key and value references are still reused, so there is no automatic deep copy.

If the source is being modified concurrently, the copying step still requires an appropriate concurrency policy. Creating a new object does not make reading the source in an unprotected state valid.

## 9. Reverse order changes the meaning of navigation too

### 9.1. DescendingMap is a view

`descendingMap()` returns a view with the reverse order of the current map. It shares the same data, so removing a key through the reversed map also removes the mapping from the original map.

When the original has order 10, 20, 30, 40, the reversed map iterates 40, 30, 20, 10.

Methods still operate according to the view's own order:

~~~text
in ascending order:
lowerKey(20)  -> 10
higherKey(20) -> 30

in descending order:
lowerKey(20)  -> 30
higherKey(20) -> 10
~~~

Key 30 comes before 20 in descending order, while 10 comes after. This is not a bug in lower or higher; the ordering relation in use has changed.

### 9.2. Range bounds also follow descending order

On a descending view, `subMap(40, true, 20, false)` selects 40 and 30. The pair of bounds looks "from larger number to smaller number", yet it follows the comparator's direction.

Conversely, taking the habit of passing 20 then 40 from an ascending map and applying it to a descending view can produce an invalid range. Read the actual sequence order before interpreting fromKey and toKey.

`descendingKeySet` and `navigableKeySet` provide corresponding key views. They are not places where you can add a new key without a map value; supported removals affect the underlying mapping according to the view contract.

## 10. Choosing a constructor is also choosing an ordering

Two copy constructors have a notable difference:

| Argument selected by compile-time type | New TreeMap uses |
|---|---|
| Map | Natural ordering of keys |
| SortedMap | Ordering of the source SortedMap |

For example, suppose a source TreeMap is descending. If passed via a variable of type SortedMap, the constructor preserves the descending rule. If passed via a variable of type Map, the constructor taking Map uses natural ordering.

There is no rule that "runtime always inspects the source object as a TreeMap and re-selects the overload". Overload resolution is based on the compile-time type of the expression.

When you want more explicit control, you can create the map with the desired comparator and then call putAll. The order is determined by the target's comparator; putAll does not replace it with the source's comparator.

This detail explains why two copies of the same mappings can iterate in different orders. It also reminds us that interface types affect not only which methods can be called, but also which constructor overload is chosen. [Java 17: TreeMap constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

## 11. Nulls, key types, and known limits

A TreeMap using natural ordering does not accept null keys. A custom comparator can allow null if the comparator itself defines how to compare it, such as `Comparator.nullsFirst(...)`.

The program uses a null-allowing comparator and prints the order `[null, A, B]`. That does not mean every TreeMap accepts null.

Null values are a separate question from null keys. A mapping with a null value can still exist; use containsKey or the appropriate entry method when you need to distinguish it from a missing mapping.

Keys must be mutually comparable under the map's rule. Generics help check types at compile time, but they do not guarantee every comparison rule is valid. Do not use raw types to arbitrarily mix incomparable key types.

TreeMap is not synchronized either. Iterators have best-effort modification detection; that mechanism does not replace a concurrency access policy. The ordering discussions here assume operations are organized within a valid map state.

## 12. Complete Java program

Save the following code to `SortedNavigationDemo.java`. Each scenario group uses suitable data so that an earlier poll or removal does not distort understanding of a later section.

The program verifies key ordering, the difference between lower and floor, view versus copy, navigation entries, reverse ordering, comparators returning 0, and the two constructor overloads.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NoSuchElementException;
import java.util.SortedMap;
import java.util.TreeMap;

public class SortedNavigationDemo {
    private static TreeMap<Integer, String> sample() {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(40, "forty");
        map.put(10, "ten");
        map.put(30, "thirty");
        map.put(20, "twenty");
        return map;
    }

    private static <K, V> List<K> keys(Map<K, V> map) {
        return new ArrayList<>(map.keySet());
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected result");
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> tree = sample();
        Map<Integer, String> asMap = tree;
        SortedMap<Integer, String> sorted = tree;
        NavigableMap<Integer, String> navigable = tree;

        require(keys(asMap).equals(List.of(10, 20, 30, 40)));
        System.out.println("order/keys=" + keys(asMap));
        System.out.println("order/values=" + new ArrayList<>(tree.values()));
        System.out.println("sorted/first=" + sorted.firstKey()
                + ", last=" + sorted.lastKey());
        System.out.println("sorted/[20,40)=" + sorted.subMap(20, 40));
        System.out.println("near/25: lower=" + navigable.lowerKey(25)
                + ", floor=" + navigable.floorKey(25)
                + ", ceiling=" + navigable.ceilingKey(25)
                + ", higher=" + navigable.higherKey(25));
        System.out.println("near/20: lower=" + navigable.lowerKey(20)
                + ", floor=" + navigable.floorKey(20)
                + ", ceiling=" + navigable.ceilingKey(20)
                + ", higher=" + navigable.higherKey(20));

        NavigableMap<Integer, String> range =
                tree.subMap(20, true, 40, false);
        TreeMap<Integer, String> independent = new TreeMap<>(range);
        range.put(35, "thirty-five");
        range.remove(20);
        require(keys(tree).equals(List.of(10, 30, 35, 40)));
        require(keys(independent).equals(List.of(20, 30)));
        boolean outsideRejected = false;
        try {
            range.put(40, "not-allowed");
        } catch (IllegalArgumentException exception) {
            outsideRejected = true;
        }
        require(outsideRejected);
        System.out.println("view/range=" + range);
        System.out.println("view/parent=" + tree);
        System.out.println("view/copy=" + independent);
        System.out.println("view/outsideRejected=" + outsideRejected);

        TreeMap<Integer, String> snapshotMap = sample();
        Map.Entry<Integer, String> first = snapshotMap.firstEntry();
        snapshotMap.put(10, "TEN");
        require(first.getValue().equals("ten"));
        boolean snapshotImmutable = false;
        try {
            first.setValue("changed");
        } catch (UnsupportedOperationException exception) {
            snapshotImmutable = true;
        }
        require(snapshotImmutable);
        System.out.println("entry/snapshot=" + first
                + ", current=" + snapshotMap.get(10)
                + ", setValueRejected=" + snapshotImmutable);

        TreeMap<Integer, String> drained = sample();
        Map.Entry<Integer, String> smallest = drained.pollFirstEntry();
        Map.Entry<Integer, String> largest = drained.pollLastEntry();
        require(keys(drained).equals(List.of(20, 30)));
        System.out.println("poll/first=" + smallest + ", last=" + largest);
        System.out.println("poll/remaining=" + drained);

        TreeMap<Integer, String> empty = new TreeMap<>();
        boolean firstKeyThrows = false;
        try {
            empty.firstKey();
        } catch (NoSuchElementException exception) {
            firstKeyThrows = true;
        }
        require(firstKeyThrows && empty.firstEntry() == null);
        System.out.println("empty/firstEntry=" + empty.firstEntry()
                + ", firstKeyThrows=" + firstKeyThrows);

        TreeMap<Integer, String> ascending = sample();
        NavigableMap<Integer, String> descending = ascending.descendingMap();
        require(keys(descending).equals(List.of(40, 30, 20, 10)));
        System.out.println("descending/keys=" + keys(descending));
        System.out.println("descending/at20: lower=" + descending.lowerKey(20)
                + ", higher=" + descending.higherKey(20));
        System.out.println("descending/[40,20)="
                + descending.subMap(40, true, 20, false));
        descending.remove(20);
        require(!ascending.containsKey(20));
        System.out.println("descending/parentAfterRemove=" + keys(ascending));

        TreeMap<String, Integer> folded =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        folded.put("java", 1);
        folded.put("JAVA", 2);
        require(folded.size() == 1 && folded.get("JaVa") == 2);
        System.out.println("compareZero/size=" + folded.size()
                + ", value=" + folded.get("JaVa"));

        TreeMap<Integer, String> reverseSource =
                new TreeMap<>(Comparator.reverseOrder());
        reverseSource.putAll(sample());
        SortedMap<Integer, String> sortedSource = reverseSource;
        Map<Integer, String> mapSource = reverseSource;
        TreeMap<Integer, String> copySorted = new TreeMap<>(sortedSource);
        TreeMap<Integer, String> copyMap = new TreeMap<>(mapSource);
        require(keys(copySorted).equals(List.of(40, 30, 20, 10)));
        require(keys(copyMap).equals(List.of(10, 20, 30, 40)));
        System.out.println("constructor/SortedMap=" + keys(copySorted));
        System.out.println("constructor/Map=" + keys(copyMap));

        NavigableMap<String, Integer> nullable =
                new TreeMap<>(Comparator.nullsFirst(
                        Comparator.<String>naturalOrder()));
        nullable.put("B", 2);
        nullable.put(null, 0);
        nullable.put("A", 1);
        require(keys(nullable).toString().equals("[null, A, B]"));
        System.out.println("nullKeys/order=" + keys(nullable));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 SortedNavigationDemo.java
java SortedNavigationDemo
~~~

Stdout from the verification run:

~~~text
order/keys=[10, 20, 30, 40]
order/values=[ten, twenty, thirty, forty]
sorted/first=10, last=40
sorted/[20,40)={20=twenty, 30=thirty}
near/25: lower=20, floor=20, ceiling=30, higher=30
near/20: lower=10, floor=20, ceiling=20, higher=30
view/range={30=thirty, 35=thirty-five}
view/parent={10=ten, 30=thirty, 35=thirty-five, 40=forty}
view/copy={20=twenty, 30=thirty}
view/outsideRejected=true
entry/snapshot=10=ten, current=TEN, setValueRejected=true
poll/first=10=ten, last=40=forty
poll/remaining={20=twenty, 30=thirty}
empty/firstEntry=null, firstKeyThrows=true
descending/keys=[40, 30, 20, 10]
descending/at20: lower=30, higher=10
descending/[40,20)={40=forty, 30=thirty}
descending/parentAfterRemove=[10, 30, 40]
compareZero/size=1, value=2
constructor/SortedMap=[40, 30, 20, 10]
constructor/Map=[10, 20, 30, 40]
nullKeys/order=[null, A, B]
~~~

The code was compiled with `--release 17` and ran successfully. The release option sets the API level and target bytecode compatibility; it does not assert that the executing JVM is specifically JDK 17.

### 12.1. The order and sorted lines

Data was inserted as 40, 10, 30, 20, yet keys are printed as 10, 20, 30, 40. The values follow those mappings, not a separate value sort.

Three interface variables reference the same tree. The output shows that viewing the object through Map does not lose TreeMap's iteration order, while the SortedMap type allows calling firstKey and subMap.

### 12.2. Two intentionally chosen near targets

Target 25 lies between two keys, so lower and floor both give 20, and ceiling and higher both give 30. If you only test this target, it is easy to mistake the pairs of methods for synonyms.

Target 20 matches an existing key exactly, making the difference clear: lower is 10, floor is 20, ceiling is 20, and higher is 30. A boundary test must include an exact-match case.

### 12.3. The view mutates, while copy keeps copied data

Copy was created before the view added 35 and removed 20. Therefore, copy still contains 20 and 30, while the original map reflects both view operations.

Putting key 40 is rejected because 40 is the excluded upper bound. That key's existence in the original map does not grant the view permission to modify it.

### 12.4. Snapshot entries and data-removing polls

FirstEntry retains the pair 10=ten after the map has been updated to 10=TEN. Calling setValue on that entry is rejected. The example uses String to avoid ambiguity with mutating the internals of a mutable value object.

PollFirstEntry and pollLastEntry return 10=ten and 40=forty, leaving 20 and 30 in the map. On an empty map, firstEntry returns null, whereas firstKey throws NoSuchElementException.

### 12.5. Reversing order and overload selection

The reversed map iterates 40, 30, 20, 10; lower and higher at target 20 are interpreted in this direction. Removing 20 through the reversed view removes 20 from the original map.

The two constructor lines use the same descending source data but different compile-time argument types. One preserves descending order; the one passed as Map uses natural ordering. This is the result of overload resolution, not data being randomly shuffled.

## 13. Common mistakes and how to spot them

| Misconception | How to check properly |
|---|---|
| TreeMap sorts by value | Identify which keys the comparator applies to |
| TreeMap preserves insertion order | Try inserting in reverse order and reading keySet |
| comparator() returning null means unsorted | Null represents natural ordering |
| lower and floor are the same | Test with a target equal to an existing key |
| ceiling is the nearest element by distance | It is the candidate on the ≥ side according to the order |
| Default subMap includes both bounds | The two-argument form is lower-inclusive, upper-exclusive |
| subMap is a copy for safe trial edits | It is a view; valid edits go into the original map |
| Out-of-range keys can be put because the original has them | View bounds still restrict insertions through the view |
| descending only changes printing | It reverses navigation relations and range bounds too |
| firstEntry and pollFirstEntry are both read-only | Poll removes the mapping from the map |
| Every entry supports setValue | Entries from navigation queries have their own contract |
| Comparing equal to 0 only affects display | It affects whether TreeMap treats keys as the same position |
| A copy always keeps the source comparator | Check which constructor is chosen by the argument type |

## 14. Practice and solutions

### Exercise 1. Distinguishing interface type and object

A Map variable references a TreeMap with keys 30, 10, 20. Is iterating over keySet still ordered? Why can't floorKey be called directly through the Map variable?

**Solution:** The object is still a TreeMap, so it keeps the order 10, 20, 30 according to the active rule. Map does not declare floorKey, so the variable's type does not allow calling that method. If a function needs navigation, express the requirement with an appropriate NavigableMap type.

### Exercise 2. Testing exact boundaries

With keys 10, 20, 30, compute lowerKey(20), floorKey(20), ceilingKey(20), and higherKey(20). Why is testing only target 25 insufficient?

**Solution:** The results are 10, 20, 20, 30. Target 25 gives lower equal to floor and ceiling equal to higher, so it does not reveal the difference in accepting an exact match.

### Exercise 3. Selecting an effective configuration

Start timestamps are 100, 200, 300. At timestamp 200, which timestamp's configuration is needed and which method should be used? What if querying 50?

**Solution:** Use floorEntry(200), which returns the mapping at 200. LowerEntry(200) returns timestamp 100, which is wrong for the requirement. At 50 there is no timestamp ≤ 50, so the result is null; the application must define a policy for missing configuration or use a default.

### Exercise 4. Ranges and underlying data

A map has 10, 20, 30, 40. Create subMap(20, 40), then call clear on the view. Which keys remain in the original? Can put(40, value) be called through the view?

**Solution:** The view represents 20 and 30; clear removes those two mappings from the original, leaving 10 and 40. Key 40 is outside the view because the upper bound is excluded, so putting through the view is rejected with IllegalArgumentException.

### Exercise 5. Reverse order

An ascending original map has 10, 20, 30, 40. On descendingMap, what are lowerKey(20) and higherKey(20)? What does subMap(40, true, 20, false) contain?

**Solution:** Lower is 30 and higher is 10 in descending order. The range starts at 40 inclusive and ends at 20 exclusive, so it contains 40 and 30.

### Exercise 6. Comparator accidentally merging keys

A key is a pair of score and id, but the comparator only checks score. Are two records with the same score and different ids guaranteed to be kept as two mappings? How should this be fixed if both must be kept?

**Solution:** No. The comparator returns 0 when scores are equal, so TreeMap treats them as the same key position. You can add id as a secondary criterion while also designing a compatible equals relation and keeping keys stable.

### Exercise 7. Peeking and polling

A logging task needs to print the first mapping without modifying the map, and the map may be empty. Choose firstEntry or pollFirstEntry? Can setValue be called on the navigation result to update the original?

**Solution:** Choose firstEntry and handle null when empty. PollFirstEntry would remove the mapping if present. Entries from TreeMap navigation queries do not support setValue write-back; to modify, use the appropriate map operation.

### Exercise 8. Copying and comparators

The source is a descending TreeMap. A SortedMap variable and a Map variable both point to the source. Do two `new TreeMap` calls with those two variables always have the same order?

**Solution:** No. The constructor taking SortedMap preserves the source's order; the constructor taking Map uses natural ordering. The overload is selected by the expression's compile-time type. To make intent explicit, create the target with a specific comparator and then copy the mappings.

## 15. How to read a query before running it

Before writing floor, subMap, or descendingMap, answer four questions: which order is in use, is an exact match accepted, is the result a view or a pair/copy, and does the operation mutate data?

When these four questions are clear, the chain Map → SortedMap → NavigableMap becomes easy-to-use capability tiers: mapping, ordering, then order-based navigation. TreeMap provides an implementation to connect those capabilities to real problems.
