# TreeMap: descendingMap, navigableKeySet, and Reversed-Order Views

## 1. One Set of Mappings Can Be Viewed in Multiple Directions

Suppose a program stores document versions by sequence number: 10, 20, 30. You want to look up by number, view from oldest to newest on one screen, and view from newest to oldest on another screen. You do not necessarily need to create two maps and manually synchronize them whenever the data changes.

`TreeMap` already keeps keys in a defined order. A **view** lets you work with the same data through a different direction or range. The two main APIs in this lesson are:

- `descendingMap()`: a view of all mappings in reversed order.
- `navigableKeySet()`: a view of the keys, providing methods to find neighboring keys and work with both ends.

Two related APIs that connect these perspectives are `descendingKeySet()` on the map and `descendingSet()` on `NavigableSet`. They do not create an independent data store just because the return type is a map or set.

For a map using the natural order of integers:

```text
Original data:                 10=A, 20=B, 30=C
map key iteration:             10 → 20 → 30
map.descendingMap keys:        30 → 20 → 10
map.navigableKeySet:           10 → 20 → 30
map.descendingKeySet:          30 → 20 → 10
```

What needs to be understood is not just reversing the printed order. When operating through a reversed view, **first/last, before/after, neighboring keys, and range bounds must all be interpreted according to the view's order**. When removing through a modifiable view, the mapping in the original map is also removed.

The examples in this lesson use Java 17 or later, relying solely on the existing navigation APIs of `TreeMap` and `NavigableMap`.

## 2. Identifying the Right Return Types

| Call | Return Type | Visible Data | Order |
|---|---|---|---|
| `map.descendingMap()` | `NavigableMap<K,V>` | Both keys and values | Reversed relative to the receiving map |
| `map.navigableKeySet()` | `NavigableSet<K>` | Keys only | Same order as the map |
| `map.descendingKeySet()` | `NavigableSet<K>` | Keys only | Reversed relative to the map |
| `keys.descendingSet()` | `NavigableSet<K>` | Elements of the key set/view | Reversed relative to the receiving set |

`NavigableMap` extends the capabilities of an ordered map: beyond exact key lookup, it can also find the key or entry immediately before or after a threshold. `NavigableSet` performs similar operations on single elements, so on a key view, the result is a key rather than an entry.

`TreeMap`'s `keySet()` is still iterated in order. The useful difference of `navigableKeySet()` is that its return type exposes methods such as `lower`, `floor`, `ceiling`, `higher`, `pollFirst`, and `descendingSet`.

The following snippet is only an illustration inside a method, not a standalone Java file:

```java
TreeMap<Integer, String> map = new TreeMap<>();
NavigableMap<Integer, String> down = map.descendingMap();
NavigableSet<Integer> keys = map.navigableKeySet();
NavigableSet<Integer> downKeys = map.descendingKeySet();
```

Do not declare `TreeMap<Integer,String> down = map.descendingMap()`: the API returns `NavigableMap` and does not promise that the view is an independent `TreeMap` instance. Using the appropriately narrow interface accurately reflects the actual capabilities of the result.

## 3. "Descending" Means Reversing the Current Order

### 3.1. Not Fixed to Largest-to-Smallest Numbers

`TreeMap` can use natural ordering or a custom comparator. `descendingMap()` reverses **the current map's order**, rather than imposing a universal rule for all key types.

If the original map is in ascending numerical order, the reversed view goes from largest to smallest. However, if the original map was created with a descending numerical comparator, its reversed view goes from smallest to largest. For composite keys, the reversed order is also based on that key's comparator.

Therefore, in this lesson, statements like "the numerically largest key" and "the numerically smallest key" apply only when it is explicitly stated that the original map uses the natural order of integers. In the general case, speak in terms of first/last or before/after according to the comparator.

The [NavigableMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html) documentation describes the reversed view as having the reverse order of the original map. Reversing twice yields a view semantically equivalent to the original map; you do not need object identity `==` to define this property.

### 3.2. Reversing Does Not Change Mappings or Create New Key Groups

The view still contains the same key–value pairs. `get(key)` does not return a different value just because you are using the reversed direction. Groups of keys equivalent under comparison are not split into new keys either: reversing the order preserves comparison equality (comparison returning 0).

`down.put(key, value)` adds or updates a mapping in the original map. Its subsequent iteration position is determined by the key ordering, not by where the call was made or the fact that the map variable is named "down". You cannot insert key 25 at an arbitrary front of a natural-order `TreeMap` that already has 10, 20, 30; that key belongs between 20 and 30 in the original direction.

`down.values()` and `down.entrySet()` iterate according to the reversed view's key order. This is not sorting values `V` by a new comparator.

## 4. The Reversed View Is Bidirectionally Backed by the Original Map

### 4.1. Changes on One Path Are Visible on the Other

With a standard modifiable `TreeMap`, operations on `descendingMap()` affect the same underlying data:

| Operation | Effect on Original Map |
|---|---|
| `down.put(k, v)` | Adds or updates mapping for `k` |
| `down.remove(k)` | Removes mapping for `k` if present |
| `down.clear()` when `down` is a full-map reversed view | Removes all mappings from the original map |
| `down.pollFirstEntry()` | Removes the view's first entry, i.e., the original's last |
| `down.pollLastEntry()` | Removes the view's last entry, i.e., the original's first |

Conversely, adding or removing mappings through the original map is immediately reflected when observing the view. There is no separate "refresh view" operation to call after each `put`.

### 4.2. Inspecting Both Ends vs. Removing Them Are Different Operations

`firstKey()`/`lastKey()` only inspect the first/last key without removing the mapping. `firstEntry()`/`lastEntry()` inspect the full mapping at either end. Methods with `poll` both retrieve the result and remove the mapping.

In an original map with keys `[10, 20, 30]`, the reversed view is `[30, 20, 10]`. `down.firstKey()` is 30; `down.pollFirstEntry()` retrieves entry 30 and leaves the original map without key 30. If you only want to display the first item, use an inspection method to avoid unintended removal.

## 5. Program 1: Operating Across Both Directions

Save the complete program to `TreeMapDescendingViewDemo.java`. The original map uses the natural order of `Integer`.

```java
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapDescendingViewDemo {
    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        NavigableMap<Integer, String> down = map.descendingMap();
        System.out.println("original=" + map);
        System.out.println("descending=" + down);
        System.out.println("descendingEnds=" + down.firstKey() + "," + down.lastKey());
        down.put(25, "X");
        down.remove(10);
        map.put(5, "D");
        System.out.println("sharedOriginal=" + map);
        System.out.println("sharedDescending=" + down);
        System.out.println("lookup20=" + down.get(20));
        System.out.println("descendingPollFirst=" + down.pollFirstEntry());
        System.out.println("descendingPollLast=" + down.pollLastEntry());
        System.out.println("remainingOriginal=" + map);
        System.out.println("remainingDescending=" + down);
        System.out.println("twiceDescending=" + down.descendingMap().navigableKeySet());
        System.out.println("equalMappings=" + map.equals(down));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapDescendingViewDemo.java
java TreeMapDescendingViewDemo
```

Stdout:

```text
original={10=A, 20=B, 30=C}
descending={30=C, 20=B, 10=A}
descendingEnds=30,10
sharedOriginal={5=D, 20=B, 25=X, 30=C}
sharedDescending={30=C, 25=X, 20=B, 5=D}
lookup20=B
descendingPollFirst=30=C
descendingPollLast=5=D
remainingOriginal={20=B, 25=X}
remainingDescending={25=X, 20=B}
twiceDescending=[20, 25]
equalMappings=true
```

### 5.1. Insertion by Sorted Position, Not Insertion Time

Initially, the original map is `{10=A, 20=B, 30=C}`, and the view is `{30=C, 20=B, 10=A}`. Calling `down.put(25, "X")` inserts 25 into its appropriate position in the same tree. `down.remove(10)` removes 10 from the original map. Calling `map.put(5, "D")` adds 5 through the original map, and the view sees it as well.

As a result, the original map becomes `[5, 20, 25, 30]`, and the view becomes `[30, 25, 20, 5]`. `lookup20=B` confirms that key lookup does not alter value semantics.

### 5.2. Which End of the Original Map Does Poll on the Reversed View Take?

`descendingPollFirst=30=C` removes the largest key under the natural ordering in effect. Then `descendingPollLast=5=D` removes the smallest key. The original map is left with `[20, 25]`, and the view with `[25, 20]`.

`twiceDescending=[20, 25]` returns to the original direction. `equalMappings=true` does not mean both iteration orders are the same: map equality checks the mappings, not iteration order. When you need to verify order, inspect an ordered list of keys rather than relying solely on `Map.equals`.

## 6. Neighbor-Finding Methods Flip Meaning with Direction

### 6.1. Meaning of lower, floor, ceiling, higher

Navigation methods use the ordering of **the receiving object**:

| On Map | On Key View | Meaning in the Object's Order |
|---|---|---|
| `lowerKey(x)` | `lower(x)` | Nearest key strictly before `x` (excludes keys equivalent to `x`) |
| `floorKey(x)` | `floor(x)` | Nearest key before or equivalent to `x` |
| `ceilingKey(x)` | `ceiling(x)` | Nearest key after or equivalent to `x` |
| `higherKey(x)` | `higher(x)` | Nearest key strictly after `x` (excludes keys equivalent to `x`) |

"Nearest" here means nearest in order, not minimizing some arithmetic distance. For non-numeric keys, there is no need for a subtraction operation between two keys to compute distance.

With a natural-order original map containing `[10, 20, 30, 40]`, a query of 25 yields:

| Lookup | Ascending Original | Descending View |
|---|---|---|
| lower | 20 | 30 |
| floor | 20 | 30 |
| ceiling | 30 | 20 |
| higher | 30 | 20 |

In descending order, 30 comes before 25, while 20 comes after 25. Therefore, `down.lowerKey(25)` returns 30 even though 30 is numerically greater than 25.

### 6.2. Corresponding Method Pairs Between Original and Reversed Views

With `down = map.descendingMap()`, you can map them as follows:

```text
down.lowerKey(x)   ↔ map.higherKey(x)
down.floorKey(x)   ↔ map.ceilingKey(x)
down.ceilingKey(x) ↔ map.floorKey(x)
down.higherKey(x)  ↔ map.lowerKey(x)
```

The corresponding entry-returning methods flip in the exact same way. `floor` and `ceiling` still include keys equivalent to `x`; `lower` and `higher` still exclude equality. Inclusivity flags do not flip just because the direction flipped.

## 7. Program 2: Navigation and Range Bounds in Reversed Order

Save to `TreeMapDescendingNavigationDemo.java`. The queries cover an existing key, an intermediate value, and values outside the key set.

```java
import java.util.List;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapDescendingNavigationDemo {
    private static void show(String label, NavigableMap<Integer, String> map, int key) {
        System.out.println(label + "(" + key + "): lower=" + map.lowerKey(key)
                + ", floor=" + map.floorKey(key)
                + ", ceiling=" + map.ceilingKey(key)
                + ", higher=" + map.higherKey(key));
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        for (int key : List.of(10, 20, 30, 40)) {
            map.put(key, "v" + key);
        }
        NavigableMap<Integer, String> down = map.descendingMap();
        for (int query : List.of(25, 20, 5, 45)) {
            show("original", map, query);
            show("descending", down, query);
        }
        System.out.println("descendingRange="
                + down.subMap(40, true, 20, false).navigableKeySet());
        System.out.println("descendingHead=" + down.headMap(30, false).navigableKeySet());
        System.out.println("descendingTail=" + down.tailMap(30, true).navigableKeySet());
        try {
            down.subMap(10, true, 40, true);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("wrongBoundOrder=IllegalArgumentException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapDescendingNavigationDemo.java
java TreeMapDescendingNavigationDemo
```

Stdout:

```text
original(25): lower=20, floor=20, ceiling=30, higher=30
descending(25): lower=30, floor=30, ceiling=20, higher=20
original(20): lower=10, floor=20, ceiling=20, higher=30
descending(20): lower=30, floor=20, ceiling=20, higher=10
original(5): lower=null, floor=null, ceiling=10, higher=10
descending(5): lower=10, floor=10, ceiling=null, higher=null
original(45): lower=40, floor=40, ceiling=null, higher=null
descending(45): lower=null, floor=null, ceiling=40, higher=40
descendingRange=[40, 30]
descendingHead=[40]
descendingTail=[30, 20, 10]
wrongBoundOrder=IllegalArgumentException
```

### 7.1. Exact Key Match and No Candidate Found

At query 20, both `floor` and `ceiling` can return 20. `lower`/`higher` must find a strictly different key: in the original map they are 10/30, whereas in the reversed view they are 30/10.

Queries 5 and 45 demonstrate `null` when no candidate exists in the requested direction. For example, in descending order, 5 comes after all existing keys, so there is no `ceiling`/`higher` key for 5; `lower`/`floor` is 10. Returning no candidate does not modify the map.

### 7.2. from and to Also Follow the View's Comparator

`down.subMap(40, true, 20, false)` spans from 40 up to before 20 in descending order, producing `[40, 30]`. The `true` flag includes 40; the `false` flag excludes 20.

`down.headMap(30, false)` takes the portion before 30 in descending order, which is `[40]`. `down.tailMap(30, true)` takes from 30 onward, which is `[30, 20, 10]`.

`down.subMap(10, true, 40, true)` has the bounds in the wrong order because 10 comes after 40 in the view's comparator. It throws `IllegalArgumentException`. Do not use a "smaller number first" rule when specifying bounds for arbitrary views.

### 7.3. Translating a Range to the Reversed Direction

If you want the same set of keys in `(20, 40]` from the natural-order original map, you can view it via the original's `subMap(20, false, 40, true)` or the reversed view's `subMap(40, true, 20, false)`. Both contain the same mappings but iterate in opposite directions.

When swapping the start/end bounds, make sure to carry each **bound value's** inclusivity flag along with it: bound 40 remains inclusive, and bound 20 remains exclusive. Swapping only the two numbers while keeping the flags in their old positions would produce a different set of keys.

## 8. navigableKeySet: A Key View with Navigation Capabilities

### 8.1. Three Ways to View Keys in Reversed Order

For a map with keys 10, 20, 30, the following calls produce the same reversed key order:

```java
// Illustration inside a method that already has the map variable.
map.descendingKeySet();
map.navigableKeySet().descendingSet();
map.descendingMap().navigableKeySet();
```

They all view the keys in the order 30, 20, 10 and are all backed by the same map. Do not rely on whether they are the same `==` object to decide whether changes propagate to the original map. The view contract is what you should rely on.

`downKeys.first()` inspects the first element according to `downKeys`'s comparator, so in this natural-number example it is 30. The `lower`/`floor`/`ceiling`/`higher` methods of the set also use the set's own direction, following the same rule seen on the map.

### 8.2. Removing a Key from the View Removes the Entire Mapping

A key view is not just an independent set of numbers. On a `TreeMap`'s key view, element removal operations are supported:

| Operation on Key View | Effect |
|---|---|
| `remove(k)` | Removes the mapping for `k` if present in the view |
| `pollFirst()` | Retrieves the first key and removes its corresponding mapping |
| `pollLast()` | Retrieves the last key and removes its corresponding mapping |
| `iterator.remove()` after a valid `next()` | Removes the mapping of the key the iterator just returned |
| `clear()` | Removes all mappings currently visible through the key view |

If the key view comes from the entire map, `clear()` empties the map. If it comes from a range view, `clear()` removes only the mappings within that range. The backing relationship remains in effect across multiple layers of views.

The [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) documentation explicitly states that the key view is backed by the map and supports element removal. Passing a key view elsewhere grants that caller the ability to delete mappings, even though the parameter type they receive is just a set.

### 8.3. Cannot Add Keys via add

`keys.add(k)` and `keys.addAll(...)` are not supported on a map's key view; they throw `UnsupportedOperationException`. A standalone key does not provide a value `V` for the new mapping. To add a mapping, call `put` on the map with both key and value.

Therefore, "a modifiable map" does not mean "every mutating method on every view will succeed." A key view allows removing mappings but does not allow adding mappings via `add`. `NavigableSet` is just the API type; the exact supported operations also depend on the implementation and how the view was created.

### 8.4. Distinguishing Empty from No Candidate

| Call on the Given Type | When Empty or No Result |
|---|---|
| `keys.first()` / `keys.last()` | Throws `NoSuchElementException` if the set is empty |
| `keys.pollFirst()` / `keys.pollLast()` | Returns `null` if the set is empty |
| `keys.lower/floor/ceiling/higher(x)` | Returns `null` if there is no candidate |
| `map.firstKey()` / `map.lastKey()` | Throws `NoSuchElementException` if the map is empty |
| `map.firstEntry()` / `map.lastEntry()` | Returns a `null` entry if the map is empty |
| `map.pollFirstEntry()` / `map.pollLastEntry()` | Returns a `null` entry if the map is empty |

Do not apply one method's empty-collection rule to another method just because both deal with the first/last element. The `NavigableSet` contract is documented in [NavigableSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

## 9. Program 3: Key Views, Iterators, and the Null Case

Save the complete program to `TreeMapNavigableKeysDemo.java`. Exceptions are intentionally caught to print the observed behavior.

```java
import java.util.Comparator;
import java.util.Iterator;
import java.util.Map;
import java.util.NavigableSet;
import java.util.NoSuchElementException;
import java.util.TreeMap;

public class TreeMapNavigableKeysDemo {
    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        NavigableSet<Integer> keys = map.navigableKeySet();
        NavigableSet<Integer> downKeys = map.descendingKeySet();
        System.out.println("keys=" + keys);
        System.out.println("descendingKeys=" + downKeys);
        System.out.println("descendingSet=" + keys.descendingSet());
        System.out.println("keysFromDescendingMap="
                + map.descendingMap().navigableKeySet());
        System.out.println("descendingEnds=" + downKeys.first() + "," + downKeys.last());
        System.out.println("lower25=" + keys.lower(25) + "," + downKeys.lower(25));
        try {
            keys.add(15);
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("addKey=UnsupportedOperationException");
        }
        System.out.println("descendingPollFirst=" + downKeys.pollFirst());
        System.out.println("remove10=" + keys.remove(10));
        System.out.println("afterKeyRemovals=" + map);
        map.put(25, "X");
        System.out.println("sameKeyViews=" + keys + "," + downKeys);
        Iterator<Integer> iterator = downKeys.iterator();
        System.out.println("iteratorNext=" + iterator.next());
        iterator.remove();
        System.out.println("afterIteratorRemove=" + map);
        keys.clear();
        System.out.println("emptyMap=" + map.isEmpty());
        System.out.println("emptyPoll=" + keys.pollFirst());
        try {
            keys.first();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("emptyFirst=NoSuchElementException");
        }
        TreeMap<Integer, String> nullable =
                new TreeMap<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.put(null, "nil");
        nullable.put(10, "ten");
        System.out.println("nullableFirst=" + nullable.navigableKeySet().first());
        System.out.println("nullablePolledKey=" + nullable.navigableKeySet().pollFirst());
        System.out.println("nullableSizeAfterPoll=" + nullable.size());
        nullable.put(null, "nil-again");
        Map.Entry<Integer, String> entry = nullable.descendingMap().pollLastEntry();
        System.out.println("nullablePolledEntry=" + entry);
        System.out.println("nullableEntryExists=" + (entry != null));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapNavigableKeysDemo.java
java TreeMapNavigableKeysDemo
```

Stdout:

```text
keys=[10, 20, 30]
descendingKeys=[30, 20, 10]
descendingSet=[30, 20, 10]
keysFromDescendingMap=[30, 20, 10]
descendingEnds=30,10
lower25=20,30
addKey=UnsupportedOperationException
descendingPollFirst=30
remove10=true
afterKeyRemovals={20=B}
sameKeyViews=[20, 25],[25, 20]
iteratorNext=25
afterIteratorRemove={20=B}
emptyMap=true
emptyPoll=null
emptyFirst=NoSuchElementException
nullableFirst=null
nullablePolledKey=null
nullableSizeAfterPoll=1
nullablePolledEntry=null=nil-again
nullableEntryExists=true
```

### 9.1. Reversed Paths See the Same Order

All three lines `descendingKeys`, `descendingSet`, and `keysFromDescendingMap` print `[30, 20, 10]`. Meanwhile, `keys` prints `[10, 20, 30]`. `lower25=20,30` records the results on the forward view and the reversed view: the navigation direction changes with the view's direction.

The call `keys.add(15)` is rejected. Next, `downKeys.pollFirst()` retrieves 30 and removes mapping `30=C`. `keys.remove(10)` removes mapping `10=A`. The original map is left with only `20=B`.

### 9.2. An Existing View Still Reflects New Changes

When `25=X` is added via the original map, the existing view variables see `[20, 25]` and `[25, 20]`. They do not hold a separate snapshot of the three keys from the time they were created.

The iterator created from `downKeys` returns 25 first. Calling `iterator.remove()` right after that `next()` removes 25 from the map; the original map is left with `20=B`. This is the removal path supported by the iterator, not an external `map.remove` call while the iterator is active.

`keys.clear()` then empties the map. `pollFirst()` returns `null`, while `first()` throws `NoSuchElementException`, matching the two distinct contracts.

### 9.3. Null Keys Make Key-Only Results Potentially Ambiguous

The `nullable` map uses a comparator that allows a `null` key and places it first in the original order. When the map contains `null` and 10, `first()` returns the valid `null` key. `pollFirst()` also returns `null`, but this time it **removed a mapping**, as proven by `nullableSizeAfterPoll=1`.

Therefore, you cannot always infer "poll returned null means it was previously empty" if the structure itself permits null elements. The usual rule is unambiguous only when the key domain excludes `null`.

The final example switches to `pollLastEntry()` on the reversed view. The entry with the `null` key is at the end of the reversed order, so it is polled. The line `nullablePolledEntry=null=nil-again` depicts a real entry object containing a `null` key, and `nullableEntryExists=true` confirms that the returned entry object itself is non-null.

When you need to distinguish "no mapping" from "a mapping with a null key," an API that returns the full entry makes this clearer than an API that returns only the key. It does not require the value inside the entry to be non-null.

## 10. Range Views Still Share the Underlying Data

### 10.1. A Range Is a Bound Condition, Not a Captured Key List

`down.subMap(40, true, 20, false)` does not capture a separate copy of the keys present at the time of the call. It defines a window containing keys within the chosen range, according to the reversed comparator. When a new key within the range is added to the original map, that key appears in the view.

Conversely, keys outside the range do not appear even though they exist in the original map. Attempting to write an out-of-range key through the view is rejected with `IllegalArgumentException`; the fact that the original map can hold that key does not widen the view's bounds.

Removing an entry that sits exactly on a bound does not change the bound. After mapping 40 is removed, the view still has bound 40 and can still see key 35 added later. Do not think of a range bound as "the largest key currently remaining in the view."

### 10.2. clear Through a Range Only Deletes What Is Visible

Suppose the original map has 10, 20, 25, 30, 35, and a range view sees 35, 30, 25. `range.clear()` removes precisely mappings 25, 30, and 35 from the original map. Keys 10 and 20 remain because they are outside the range, with 20 excluded by the exclusive bound flag.

Deleting through a range and through a reversed view does not require running an extra deletion loop on the original map. For the same reason, however, you must not treat a range as a copy that can be freely cleared without affecting the map owner.

## 11. Program 4: Copies, Constructor Overloads, and Live Ranges

Save to `TreeMapViewCopyRangeDemo.java`. This example creates both backed views and copied structures to observe the differences after modifications.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapViewCopyRangeDemo {
    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        map.put(40, "D");
        NavigableMap<Integer, String> down = map.descendingMap();
        TreeMap<Integer, String> descendingCopy = new TreeMap<>(down);
        Map<Integer, String> generalMap = down;
        TreeMap<Integer, String> naturalCopy = new TreeMap<>(generalMap);
        List<Integer> keySnapshot = new ArrayList<>(down.navigableKeySet());
        System.out.println("descendingCopyKeys=" + descendingCopy.keySet());
        System.out.println("naturalCopyKeys=" + naturalCopy.keySet());
        System.out.println("keySnapshot=" + keySnapshot);
        NavigableMap<Integer, String> range = down.subMap(40, true, 20, false);
        System.out.println("initialRange=" + range);
        range.put(30, "C2");
        range.remove(40);
        map.put(35, "new");
        range.put(25, "X");
        System.out.println("sharedRange=" + range);
        System.out.println("sharedOriginal=" + map);
        try {
            range.put(10, "outside");
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("outsideRangePut=IllegalArgumentException");
        }
        System.out.println("unchanged10=" + map.get(10));
        range.clear();
        System.out.println("afterRangeClear=" + map);
        System.out.println("sameDescendingView=" + down);
        System.out.println("independentDescendingCopy=" + descendingCopy);
        System.out.println("independentNaturalCopy=" + naturalCopy);
        System.out.println("independentKeySnapshot=" + keySnapshot);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapViewCopyRangeDemo.java
java TreeMapViewCopyRangeDemo
```

Stdout:

```text
descendingCopyKeys=[40, 30, 20, 10]
naturalCopyKeys=[10, 20, 30, 40]
keySnapshot=[40, 30, 20, 10]
initialRange={40=D, 30=C}
sharedRange={35=new, 30=C2, 25=X}
sharedOriginal={10=A, 20=B, 25=X, 30=C2, 35=new}
outsideRangePut=IllegalArgumentException
unchanged10=A
afterRangeClear={10=A, 20=B}
sameDescendingView={20=B, 10=A}
independentDescendingCopy={40=D, 30=C, 20=B, 10=A}
independentNaturalCopy={10=A, 20=B, 30=C, 40=D}
independentKeySnapshot=[40, 30, 20, 10]
```

### 11.1. Same Input Object, Two Constructors with Different Ordering Contracts

`down` is declared as `NavigableMap`, which is also a `SortedMap`. Thus, `new TreeMap<>(down)` selects the constructor taking `SortedMap` and preserves `down`'s ordering rule. `descendingCopyKeys` is `[40, 30, 20, 10]`.

`generalMap` points to the exact same view but is declared as `Map`. The call `new TreeMap<>(generalMap)` selects the constructor taking `Map`, creating a `TreeMap` in **natural order**. The resulting `naturalCopyKeys` is `[10, 20, 30, 40]`.

Constructor overload resolution happens based on the static type the compiler sees at the call site, without automatically switching to the `SortedMap` overload just because the runtime object implements it. This is why a small change in variable type or method signature can change how ordering is copied.

These constructor contracts are described in [TreeMap — Constructor Details](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html). For keys that can only be compared using a custom comparator and have no natural order, picking the wrong `Map` constructor can cause an error rather than merely changing direction.

### 11.2. A Key List Is a Separate Structural Snapshot

`new ArrayList<>(down.navigableKeySet())` creates a new list in the view's iteration order at creation time: `[40, 30, 20, 10]`. Subsequent additions or removals of keys in the map do not automatically update this list.

The list holds only keys, not mappings. The two `TreeMap` copies hold both mappings, but are sorted according to the specific comparator selected at construction. Thus, "capturing data in reversed order" could mean a list of keys or a new map; choose the exact result type that subsequent work requires.

### 11.3. Writes Through the Range and Through the Original Are Both Reflected

`range` initially has `{40=D, 30=C}`. After the operations:

- `range.put(30, "C2")` updates 30 in the original map.
- `range.remove(40)` removes 40 from the original map.
- `map.put(35, "new")` makes 35 appear in `range` because it lies between the bounds.
- `range.put(25, "X")` adds 25 to both the original map and `range`.

`range` is now `{35=new, 30=C2, 25=X}`. The bounds remain from 40 inclusive to 20 exclusive. The call `range.put(10, "outside")` is rejected, and `unchanged10=A` confirms that mapping 10 in the original map was not altered.

After `range.clear()`, the original map has `{10=A, 20=B}`, and the reversed view has `{20=B, 10=A}`. Both `TreeMap` copies and the key list still retain the data from when they were created. They are structurally independent of the original map, whereas `down` and `range` continue to track current data.

### 11.4. Shallow Copy Is Not Deep Copy

The copy constructors and `ArrayList` here create new container structures, but do not deep-clone each key or value object. The example uses `Integer` and `String`, so there are no in-place value mutations that would make results harder to observe.

If a value is a mutable object, the original map and the copy can both hold references to it. Mutating that object through one reference can still be observed through both. Similarly, you must keep the key fields used by the comparator stable; copying a map does not automatically make mutable keys safe.

A copy is not read-only by default either. Structural independence, structural mutability, and object reference sharing are three separate questions.

## 12. Safe Iteration and Choosing the Right Mutability

### 12.1. Reverse Iteration Does Not Require Copying

If you only need to iterate over the keys in reverse, you can use `descendingKeySet()` in a loop or obtain `map.navigableKeySet().descendingIterator()`. `descendingIterator()` has the effect of iterating in the direction of `descendingSet().iterator()`.

If you need both keys and values, iterating over `map.descendingMap().entrySet()` reads both from each entry. There is no need to create a reversed key list and look up each key again just to fetch its value, unless a list copy serves a separate purpose.

The following snippet illustrates a read-only pass inside a method that already has `map`, not a standalone program:

```java
for (Map.Entry<Integer, String> entry : map.descendingMap().entrySet()) {
    System.out.println(entry.getKey() + ":" + entry.getValue());
}
```

This iteration does not remove mappings on its own. If you want to gradually take and remove mappings in reversed order on a single thread, you can call `pollFirstEntry()` on the view and check the returned entry object. Make sure whether removing before processing is appropriate if processing fails; `TreeMap` itself does not provide transactions for downstream work.

### 12.2. Modifying Through One View Also Affects Iterators on Other Views

The original map, reversed view, and key views do not have three separate copies of the data. If you are iterating over one view and add or remove mappings through another path, the iterator can be affected by the structural modification to the same map.

`TreeMap` has fail-fast iterators, which can throw `ConcurrentModificationException` when they detect that kind of modification. This is a best-effort bug-detection mechanism, not a concurrency coordination guarantee, nor a mechanism exclusively for multithreading. A single thread modifying the map outside its own iterator can still run into it.

When you need to remove the key currently being iterated, use `iterator.remove()` following the `next`/`remove` lifecycle, as in Program 3. Do not write a for-each loop over `downKeys` and call `map.remove(key)`, assuming that changing the receiver variable separates the removal from the structure being iterated.

If you need to build a modification plan before applying it, you can collect the keys into a separate list first. That separates iterating over the list structure from modifying the map structure; it does not make the whole workflow atomic if other threads are concurrently modifying the data.

### 12.3. Views Do Not Grant Read-Only Guarantees or Concurrency Support

`descendingMap()` by itself does not make a map read-only. `navigableKeySet()` is not a harmless publication of keys either if the recipient is allowed to call `remove` or `clear`. When designing APIs that return data, explicitly decide whether the caller should be allowed to mutate the source through the returned object.

An appropriate unmodifiable wrapper can prevent mutations through that wrapper, but read-only is still different from an independent snapshot: changes made by the original map's owner can continue to be seen through views. When structurally isolated data is required, create a new structure as in the copy examples.

`TreeMap` is not synchronized for concurrent access; its views do not add synchronization either. A sequence of `firstKey()` followed by `remove(key)` consists of two separate operations, so you must not assume data cannot change in between when multiple threads share it. All access paths through both the original map and its views must follow the same coordination design if concurrency is required.

## 13. Testing Based on Relationships Between Views

### 13.1. What to Verify

A test that only checks a descending printed string misses the most important aspects of views. You should test both backed data behavior and direction-dependent semantics:

1. Obtain a view, then insert through the original map: does the view see the new mapping in the right position?
2. Remove through the key view: is the mapping removed from the original map?
3. Poll the first element of the reversed view: does it remove the last element of the original map?
4. For an intermediate query, do `lower`/`floor`/`ceiling`/`higher` flip pairs correctly according to direction?
5. For a query matching an existing key, do `floor`/`ceiling` remain inclusive while `lower`/`higher` still exclude equality?
6. Does a range view accept the right bounds and reject writes outside the bounds?
7. Does a copy preserve the intended comparator and remain independent of structural changes to the original map?

Verify ordering using a list of keys in iteration order, such as `new ArrayList<>(view.navigableKeySet())`. Map or set equality does not check order, so two views going in opposite directions can still be equal in terms of mappings or key sets.

### 13.2. Educational Edge Cases

- Empty map: clearly separate methods that return `null` from methods that throw an exception.
- Single-mapping map: first and last are the same key; polling one end makes the other end disappear too.
- Map already using a descending comparator: `descendingMap` must flip back to ascending numerical order in that case.
- Range bounds not matching any existing key: a bound is still a comparison threshold and does not need to be present in the map.
- Removing a mapping that sits on a bound: the range still keeps its configured bound and does not shrink to the current key set.
- `null` keys if permitted by the comparator: distinguish a `null` entry from an entry with a `null` key.

If `from` and `to` are equivalent under the comparator, a range inclusive at both ends can contain the group of keys at that threshold; if either end is exclusive, it contains none. When working with custom comparators, reason in terms of comparison relationships rather than the surface representation of keys.

### 13.3. Cost Differences Between Views and Copies

Obtaining a view does not require copying all mappings into an independent map. Operations through the view still work on the backed structure, using the view's direction and bounds.

However, do not infer that every operation on a view runs in constant time. Iterating over `k` elements and building a list of `k` keys must process `k` elements; lookups on `TreeMap` still rely on the tree structure and key comparisons. Range views also perform bound checks and operate over the visible portion of the data.

Choose a view when you need to look at current data in a different direction or range. Choose a copy when you need an independent structure and accept the cost of allocating a new container. This is a decision about data relationships before it is a speed optimization decision.

## 14. Common Pitfalls

| Misconception | Consequence | How to Handle |
|---|---|---|
| `descendingMap` creates a separate `TreeMap` | Modifying the view unexpectedly mutates the original | Interpret the backed view relationship accurately |
| Creating a reversed view changes the original map's iteration order | Mispredicting results from the original variable | Keep each receiver object's direction separate |
| `descending` always means largest to smallest number | Wrong when the original already has a reversed comparator | It reverses the current order, not a fixed numerical rule |
| `lower` always returns a smaller number | Wrong on a descending view | Interpret according to the view's comparator |
| Writing `subMap` bounds smallest-first in every direction | `IllegalArgumentException` or wrong range | Pass `from`/`to` in the view's order |
| Swapping bounds without moving inclusivity flags | Wrongly including one end and excluding the other | Keep each flag paired with its bound value |
| `navigableKeySet` is an independent set of keys | `remove`/`clear` deletes source mappings | Create a new collection if you need a copy |
| Since the map is modifiable, `keys.add` works too | `UnsupportedOperationException` | Add mappings using `put` with both key and value |
| `poll` only inspects the first/last element | Data gets removed | Use `first`/`last` to inspect |
| `first` on an empty set returns `null` | Unhandled `NoSuchElementException` | Follow each method's specific contract |
| A key poll returning `null` always means empty | Wrong when a valid `null` key exists | Use entry-returning methods or a non-null key contract to distinguish |
| Every `TreeMap` copy constructor preserves the comparator | Copy changes order or fails to compare keys | Distinguish `Map` and `SortedMap` overloads |
| `Map.equals` or `Set.equals` proves the order is the same | Test fails to catch reversed order | Compare an ordered list of keys |

## 15. Self-Check

### Questions

1. A natural-order original map has `[10, 20, 30]`; after creating `down`, does the original automatically turn into `[30, 20, 10]`?
2. Does removing key 20 through `down.navigableKeySet()` affect the original map?
3. Does `down.pollFirstEntry()` take the first or last entry of the original map?
4. With original `[10, 20, 30, 40]`, what are `down.lowerKey(25)` and `down.ceilingKey(25)`?
5. Why is `down.subMap(10, true, 40, true)` invalid when `down` uses descending numerical order?
6. Do `map.descendingKeySet()` and `map.navigableKeySet().descendingSet()` need to be the same object to view the same data?
7. Can you add a key to the map using `navigableKeySet().add(key)`?
8. Does an `ArrayList` created from a key view continue to see keys added later?
9. When the input is declared as `NavigableMap`, which `TreeMap` copy constructor is chosen? What if it is declared as `Map`?
10. Is a key poll returning `null` enough to conclude there was no prior mapping in every `TreeMap`?

### Answers

1. No; the original keeps its old direction while `down` views it in reverse.
2. Yes; the key view is backed, so mapping 20 is removed from the original map.
3. The last entry of the original map, because that is the first entry of the reversed view.
4. 30 and 20, respectively, following `down`'s direction.
5. 10 comes after 40 in the descending comparator; the `from`/`to` bounds are reversed relative to the required order.
6. No; the relationship is guaranteed by the view contract, not by object identity.
7. No; key views do not support `add`/`addAll`—you must `put` the mapping on the map.
8. No; it is a new list containing the keys at creation time, even though the key objects themselves may still share references.
9. `NavigableMap` is also a `SortedMap`, so the `SortedMap` overload is chosen and preserves the order; type `Map` chooses the `Map` overload, which uses natural order.
10. No; if the comparator permits `null` keys, `poll` may have just removed a mapping with a `null` key.

## 16. Practice with Reference Results

### Exercise 1: Removing via a Reversed View

Create a natural-order original map with `1=A`, `2=B`, `3=C` and obtain `down`. Add `4=D` via the original map, then call `down.navigableKeySet().pollFirst()`. Before running, predict the returned key and the order in both directions.

Reference result: `poll` returns 4 and removes `4=D`; the original map has `[1, 2, 3]` left, and `down` has `[3, 2, 1]`. If you predicted 1, you read the view's start as the original map's start.

### Exercise 2: Inclusive Bounds in Reversed Order

With an original map having 10, 20, 30, 40, obtain `down.subMap(40, false, 20, true)`. List the visible keys and write a range on the original map containing the same mappings.

Reference result: `down` sees `[30, 20]`; the corresponding original range is `subMap(20, true, 40, false)` with order `[20, 30]`. The `true` flag stays with bound 20 and the `false` flag stays with bound 40.

### Exercise 3: Views Do Not Capture an Initial Key Snapshot

Create a reversed range from 40 inclusive to 20 exclusive when the original map only has 10, 20, 30, 40. Remove mapping 40, then add 35 via the original map. Explain why the range sees 35 even though that key did not exist when the range was created.

Reference result: the range sees `[35, 30]`. A range is defined by its bounds, not by a copied list of keys at initialization time.

### Exercise 4: Checking Copies and Declared Types

Create `down`, a `TreeMap` copy from a `NavigableMap` variable, and a `TreeMap` copy from a `Map` variable pointing to the same `down`. Then modify the original map. Compare the initial order of the two copies and whether they update automatically.

Reference result: the copy from `NavigableMap` keeps `down`'s direction; the copy from `Map` uses natural order. Neither updates its structure automatically with the original map. To verify order, compare key lists rather than just `Map.equals`.

## 17. Runtime Environment and Documentation

The four programs in this lesson are self-contained and use syntax and APIs compatible with Java 17. They were compiled with `javac --release 17 -encoding UTF-8` and run on JDK 24.0.2; stdout was verified from those runs. Each public class is saved in a file matching its name, with no external libraries required.

- [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): reversed views, key views, copy constructors, and backed ranges.
- [NavigableMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html): navigation relationships, `descendingMap`, and range bounds.
- [NavigableSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html): neighbor lookups, both ends, reversed views, and iterators.
- [SortedMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html): map ordering and corresponding collection views.
