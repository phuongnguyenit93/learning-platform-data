# SequencedMap: firstEntry, lastEntry, pollFirstEntry, and pollLastEntry

## 1. Working with both ends of an ordered map

A Map stores mappings from keys to values. When a map has a well-defined encounter order, you can also ask: which mapping is at the beginning, which mapping is at the end, and should that mapping be removed from the map or only inspected?

Since Java 21, `SequencedMap<K, V>` provides a common contract for maps with an encounter order. The four methods in this lesson fall into two groups:

- firstEntry and lastEntry: read a mapping at the beginning/end.
- pollFirstEntry and pollLastEntry: retrieve and remove a mapping at the beginning/end, if the removal operation is supported.

The result is a `Map.Entry<K, V>`, i.e., a key-value pair. This is not just a single V value, nor is it the entire map.

For example, an insertion-ordered LinkedHashMap currently contains B=20, A=10, C=30. firstEntry is B=20; lastEntry is C=30. They do not automatically pick A because A is alphabetically smallest, nor do they pick value 10 because it is numerically smallest.

What you must always determine before using the API is **where the map's order comes from**. With the same firstEntry call, an insertion-ordered LinkedHashMap may return the earliest-inserted mapping that still exists; a TreeMap may return the mapping with the first key according to its Comparator.

### 1.1. Prerequisites and version

You need to know how to declare generics, use Map's put/get, and read Map.Entry's getKey/getValue. You do not need to create a custom Entry class to use these four methods.

All complete programs in this lesson require JDK 21 or later. They use --release 21 and do not require enabling preview features.

The names of these four methods already existed on NavigableMap before Java 21; for example, TreeMap has supported them since Java 6. Java 21 added SequencedMap as a common interface and allows using the same group of operations with maps such as LinkedHashMap. Do not assume that every firstEntry call on TreeMap only appeared in Java 21.

## 2. Reading the contract of the four methods accurately

| Method | Result when mappings exist | Changes mapping count? | When modifiable map is empty |
|---|---|---|---|
| firstEntry() | Entry of the first mapping | Does not remove | Returns null |
| lastEntry() | Entry of the last mapping | Does not remove | Returns null |
| pollFirstEntry() | Entry of the first mapping just removed | Decreases by one mapping | Returns null |
| pollLastEntry() | Entry of the last mapping just removed | Decreases by one mapping | Returns null |

The two poll methods are optional operations. An object that does not support removal may throw UnsupportedOperationException. That condition must be considered separately from the empty state.

The entries returned by these four methods are **snapshots of the mapping at the time of the call**. They are not entries that allow modifying the map via setValue. A later section explains why a snapshot also does not mean deep-copying every key and value object.

The contract is described at [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

### 2.1. poll is not reading while keeping the data intact

After a successful pollFirstEntry on a non-empty map, the returned mapping is no longer in that map. The key and value can still be referenced through the returned Entry, but the key–value association has been removed from the map.

If you only want to peek, choose firstEntry or lastEntry. Do not use poll to print the first/last entry and then be surprised when the data disappears from the container.

poll here is also not a blocking wait for data. On an empty modifiable map, it returns null by contract; it does not wait for another thread to add a mapping.

### 2.2. A single mapping is both first and last

If a map only has A=10, firstEntry and lastEntry both describe that mapping. Do not assume there must be two distinct mappings for these two methods to work.

Polling either end will make the map empty. The next poll on a modifiable map returns null, not the old mapping again.

Do not check whether two snapshot entries are the same object with == to confirm they represent the same mapping. The information to use is the key and value; the API does not promise to reuse the same Entry object across calls.

### 2.3. A null Entry is different from a null value

If firstEntry returns null, there is no first mapping to read. However, a non-null Entry can hold a null value if the map permits it.

Therefore, you must check the entry itself before calling getValue. Do not use `entry.getValue() == null` as an empty-map check: it can be a valid mapping, and it will also throw NullPointerException if entry is actually null.

LinkedHashMap also allows null keys. An entry with both a null key and a null value is still an existing Entry; it differs from a null result indicating no mapping remains.

## 3. Which order determines the first and last entries?

### 3.1. Three common policies

| Actual object | Order to understand | First/last typically represents |
|---|---|---|
| Default LinkedHashMap | Key insertion order | Earliest/latest inserted mapping still present |
| LinkedHashMap with accessOrder=true | Access order per the class contract | Least recently accessed / most recently accessed |
| TreeMap | Natural key order or Comparator | First/last key according to the comparison |
| Reversed view of a compatible map | Reverse of the source map's order | The view's first is the source's last |

Do not infer ascending key order, creation time, or business priority from the name firstEntry alone. Those meanings must come from the map's structure and how it is used.

With a default LinkedHashMap, updating the value for an existing key with put does not automatically move that key to the end. In access-order mode, access operations defined by the class can change the order. Make sure you identify the exact mode before using either end to select an item for processing.

### 3.2. Declared type affects calls at compile time

A LinkedHashMap instance can be held in a Map or SequencedMap variable. If the variable only has type Map, the compiler only exposes the Map contract; it does not allow calling firstEntry just because the runtime object is ordered.

Declare SequencedMap when your program's API genuinely needs ordered operations. This expresses intent more clearly than passing an arbitrary Map and casting inside.

A HashMap cannot be turned into a SequencedMap merely by casting. Creating a new LinkedHashMap from another map creates a new structure, and the resulting order depends on the source's iteration order. Do not take a Map without a guaranteed order as input and assign a fixed business meaning to its "first mapping".

### 3.3. Order applies to mappings, not just standalone keys

An Entry always pairs a key with its corresponding value. If you need the head of the map to process both, firstEntry or pollFirstEntry gives you the matching pair in a single result.

Do not read the "first key" in one call and the "first value" in a separate call when data can change between reads. Even an Entry snapshot does not provide extra concurrency guarantees for the whole map; access coordination is covered separately in the application patterns section.

## 4. Program 1: inspecting and removing are two different actions

Save the complete program to `SequencedMapEndsDemo.java`. The put statements are written sequentially so key insertion order is clear.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class SequencedMapEndsDemo {
    public static void main(String[] args) {
        SequencedMap<String, Integer> map = new LinkedHashMap<>();
        map.put("B", 20);
        map.put("A", 10);
        map.put("C", 30);
        System.out.println("initial=" + map);
        System.out.println("first=" + map.firstEntry());
        System.out.println("last=" + map.lastEntry());
        System.out.println("sizeAfterReads=" + map.size());
        System.out.println("pollFirst=" + map.pollFirstEntry());
        System.out.println("afterPollFirst=" + map);
        System.out.println("pollLast=" + map.pollLastEntry());
        System.out.println("afterPollLast=" + map);
        System.out.println("singleFirst=" + map.firstEntry());
        System.out.println("singleLast=" + map.lastEntry());
        System.out.println("pollSingle=" + map.pollFirstEntry());
        System.out.println("emptyFirst=" + map.firstEntry());
        System.out.println("emptyLast=" + map.lastEntry());
        System.out.println("emptyPollFirst=" + map.pollFirstEntry());
        System.out.println("emptyPollLast=" + map.pollLastEntry());
        System.out.println("emptySize=" + map.size());
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SequencedMapEndsDemo.java
java SequencedMapEndsDemo
```

Stdout:

```text
initial={B=20, A=10, C=30}
first=B=20
last=C=30
sizeAfterReads=3
pollFirst=B=20
afterPollFirst={A=10, C=30}
pollLast=C=30
afterPollLast={A=10}
singleFirst=A=10
singleLast=A=10
pollSingle=A=10
emptyFirst=null
emptyLast=null
emptyPollFirst=null
emptyPollLast=null
emptySize=0
```

### 4.1. B is first because it was inserted first

initial is `{B=20, A=10, C=30}`. B is at the front even though A is alphabetically smaller. The two reads return B=20 and C=30, while sizeAfterReads remains 3.

The printed format of Entry in the program is key=value. The string `first=B=20` consists of the label first, followed by the Entry representation B=20; it does not mean there are two mappings.

### 4.2. Poll removes exactly one mapping at the chosen end

pollFirstEntry removes B=20, leaving A=10,C=30 in the map. pollLastEntry then removes C=30, leaving A=10.

If you reverse the order of the poll calls, the intermediate state must be recalculated. Each poll operates on the map's current state, not on a list of ends captured at the start of the program.

### 4.3. One element, then empty

When only A=10 remains, both singleFirst and singleLast print A=10. pollSingle removes that mapping.

Afterward, all four methods print null on the modifiable LinkedHashMap in this example, and emptySize is 0. There is no NoSuchElementException simply from calling these four APIs on an empty modifiable map.


## 5. Returned entries are snapshots of the mapping

### 5.1. A pair of references at the time of the call

Snapshot here means the Entry records the mapping's key and value at the moment the method is called. Afterward, the map may update the key to another value or remove the mapping; the returned Entry does not become a live window that automatically reads the new value.

Example:

```text
At read time:
map:       task → queued
snapshot:  task → queued

After put(task, running):
map:       task → running
snapshot:  task → queued
```

If you need the current state, you must read from the map again using an appropriate API. Do not keep a snapshot in a variable and expect subsequent getValue calls to always reflect the latest map data.

For pollFirstEntry and pollLastEntry, understanding the snapshot is even more important: the mapping has already been removed from the map, while the returned result still holds the information for the caller to process.

### 5.2. Do not use setValue to update the map

Entries returned by these four methods do not support modifying the map via setValue. In the standard implementations tested in this lesson, calling setValue on such an entry throws UnsupportedOperationException.

This does not prove the source map is unmodifiable. The source LinkedHashMap can still put or remove; it is only the snapshot Entry object that is not a path for mutating the map.

To update a key, call the map's update API according to your business policy. Keep in mind that a snapshot can be stale: if the key has already been removed, calling put with the key from the snapshot will re-insert the mapping. Do not replace a current-state check with an entry held from earlier.

### 5.3. Snapshot is not a deep copy of keys and values

An Entry can hold the same reference to a mutable value object. If V is a List and the List's contents are modified, the snapshot's getValue still points to that List and can observe the new contents.

Two different things:

- The map changes a key's value reference to a different object.
- The program mutates the value object itself that both the map and the snapshot reference.

In the first case, the snapshot retains the old reference. In the second case, the same object is visible from multiple places. Do not describe an Entry snapshot as freezing the entire internal object graph.

### 5.4. Do not equate all sources of Map.Entry

An Entry obtained while iterating entrySet has a contract connected to the map for the duration of the iteration; whether setValue works depends on the map's capabilities. It differs from the snapshot group of firstEntry/lastEntry/pollFirstEntry/pollLastEntry.

Even `sequencedEntrySet().getFirst()` is not promised by the SequencedMap interface to have the same snapshot/setValue contract as firstEntry. Do not swap one way of obtaining an entry for another just because both return Map.Entry and have First in the name.

The [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html) documentation clearly separates these Entry sources. When designing code that mutates data, read the contract of the specific entry-producing path.

## 6. Program 2: snapshots, mutable values, and null

Save to `SequencedMapSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.SequencedMap;

public class SequencedMapSnapshotDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        SequencedMap<String, String> map = new LinkedHashMap<>();
        map.put("task", "queued");
        Map.Entry<String, String> snapshot = map.firstEntry();
        expectUnsupported("snapshotSetValue", () -> snapshot.setValue("forced"));
        map.put("task", "running");
        System.out.println("snapshotAfterPut=" + snapshot);
        System.out.println("currentEntry=" + map.firstEntry());
        Map.Entry<String, String> removed = map.pollLastEntry();
        System.out.println("removed=" + removed);
        System.out.println("snapshotAfterRemoval=" + snapshot);
        System.out.println("mapAfterRemoval=" + map);
        expectUnsupported("removedSetValue", () -> removed.setValue("changed"));

        SequencedMap<String, List<String>> mutable = new LinkedHashMap<>();
        List<String> steps = new ArrayList<>(List.of("start"));
        mutable.put("job", steps);
        Map.Entry<String, List<String>> shallow = mutable.firstEntry();
        steps.add("finish");
        System.out.println("snapshotSharedValue=" + shallow.getValue());
        System.out.println("sameValueReference=" + (shallow.getValue() == steps));

        SequencedMap<String, String> nullable = new LinkedHashMap<>();
        nullable.put(null, null);
        Map.Entry<String, String> nullMapping = nullable.pollFirstEntry();
        System.out.println("hasNullMapping=" + (nullMapping != null));
        System.out.println("nullKey=" + nullMapping.getKey());
        System.out.println("nullValue=" + nullMapping.getValue());
        System.out.println("afterNullMappingPoll=" + nullable.pollFirstEntry());
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SequencedMapSnapshotDemo.java
java SequencedMapSnapshotDemo
```

Stdout:

```text
snapshotSetValue=UnsupportedOperationException
snapshotAfterPut=task=queued
currentEntry=task=running
removed=task=running
snapshotAfterRemoval=task=queued
mapAfterRemoval={}
removedSetValue=UnsupportedOperationException
snapshotSharedValue=[start, finish]
sameValueReference=true
hasNullMapping=true
nullKey=null
nullValue=null
afterNullMappingPoll=null
```

### 6.1. Snapshot keeps queued when the map transitions to running

snapshot is taken when the map contains task=queued. setValue through snapshot is rejected. After put(task,running), snapshotAfterPut still prints task=queued, while the freshly read currentEntry is task=running.

pollLastEntry returns task=running and leaves the map empty. The old snapshot still prints task=queued; it does not turn into null when the source mapping is removed. The removed Entry also does not support setValue to recreate or modify the mapping.

### 6.2. The List object is still shared

mutable contains job pointing to the List steps. shallow records the same List reference. After adding finish to steps, snapshotSharedValue prints `[start, finish]`.

sameValueReference is true. This result matches a snapshot of the reference pair, not a deep copy of the List's elements. If deeply independent data is needed, you must design value-level copying rather than relying on the word snapshot in Entry.

### 6.3. A null mapping still returns an existing Entry

nullable has a mapping with a null key and a null value. pollFirstEntry returns a non-null Entry, so hasNullMapping is true; both its getKey and getValue are null.

Only after this mapping has been removed does the next poll return null. Thus you can distinguish:

```text
Non-null Entry, null value → mapping exists, value is null
Null Entry                 → no mapping to return
```

Do not call getKey/getValue before checking the entry in code that may encounter an empty map.

## 7. First and last swap roles on reversed

reversed returns a view seen in reverse order. In this view, the source's first becomes the last, and the source's last becomes the first.

On a modifiable reversed view of a LinkedHashMap, you can expect:

| Call on reversed view | Mapping selected in source map order |
|---|---|
| firstEntry() | Last mapping |
| lastEntry() | First mapping |
| pollFirstEntry() | Retrieve and remove the last mapping |
| pollLastEntry() | Retrieve and remove the first mapping |

The table describes which mapping is selected and the effect on the data; it does not promise that two separate calls return the same Entry object by ==. If data changes between calls, the new state must also be considered.

[LinkedHashMap.reversed — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html) allows mutations through this view and reflects those changes in the source map. This is a view sharing data, not an automatically created copy that callers can poll freely without affecting the source.

## 8. Program 3: polling through the reversed view mutates the original map

Save to `SequencedMapReverseDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class SequencedMapReverseDemo {
    public static void main(String[] args) {
        SequencedMap<String, Integer> forward = new LinkedHashMap<>();
        forward.put("a", 1);
        forward.put("b", 2);
        forward.put("c", 3);
        forward.put("d", 4);
        SequencedMap<String, Integer> reverse = forward.reversed();
        System.out.println("forward=" + forward);
        System.out.println("reverse=" + reverse);
        System.out.println("reverseFirst=" + reverse.firstEntry());
        System.out.println("reverseLast=" + reverse.lastEntry());
        System.out.println("reversePollFirst=" + reverse.pollFirstEntry());
        System.out.println("forwardAfterFirstPoll=" + forward);
        System.out.println("reversePollLast=" + reverse.pollLastEntry());
        System.out.println("forwardAfterLastPoll=" + forward);
        System.out.println("forwardPollFirst=" + forward.pollFirstEntry());
        System.out.println("reverseNow=" + reverse);
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SequencedMapReverseDemo.java
java SequencedMapReverseDemo
```

Stdout:

```text
forward={a=1, b=2, c=3, d=4}
reverse={d=4, c=3, b=2, a=1}
reverseFirst=d=4
reverseLast=a=1
reversePollFirst=d=4
forwardAfterFirstPoll={a=1, b=2, c=3}
reversePollLast=a=1
forwardAfterLastPoll={b=2, c=3}
forwardPollFirst=b=2
reverseNow={c=3}
```

### 8.1. Two views looking at the same four mappings

forward starts as a=1,b=2,c=3,d=4; reverse displays d=4,c=3,b=2,a=1. reverseFirst returns d=4, reverseLast returns a=1.

Reading first/last neither adds nor removes mappings. However, when polling through reverse, the selection direction for first/last is inverted.

### 8.2. Polling on the view mutates the source data

reverse.pollFirstEntry removes d=4, so forward only has a,b,c left. Next, reverse.pollLastEntry removes a=1, leaving b,c in forward.

forward.pollFirstEntry then removes b=2. reverseNow only has c=3 because it views the same source map in the opposite direction.

If you need an independent dataset to consume, you must create a separate map container with the chosen ordering policy. Calling reversed alone does not provide that independence.

## 9. TreeMap uses the same four methods, but first depends on Comparator

TreeMap sorts keys by natural order or a Comparator. It does not preserve key insertion order like a default LinkedHashMap.

With natural numeric keys, the first mapping has the smallest key. With Comparator.reverseOrder, the first mapping in map order has the largest key under normal numeric comparison. Do not call that "wrong order": the descending Comparator itself defines the ordering.

Nor does it automatically select entries by value V. A map with values one,two,three is still ordered by TreeMap according to key K, unless the application explicitly designs a different model.

[TreeMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html) and [NavigableMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html) are the reference sources for operations on these sorted key sets.

## 10. Program 4: first according to a descending Comparator

Save to `SequencedMapSortedDemo.java`:

```java
import java.util.Comparator;
import java.util.SequencedMap;
import java.util.TreeMap;

public class SequencedMapSortedDemo {
    public static void main(String[] args) {
        SequencedMap<Integer, String> sorted =
                new TreeMap<>(Comparator.reverseOrder());
        sorted.put(2, "two");
        sorted.put(1, "one");
        sorted.put(3, "three");
        System.out.println("sorted=" + sorted);
        System.out.println("first=" + sorted.firstEntry());
        System.out.println("last=" + sorted.lastEntry());
        System.out.println("pollFirst=" + sorted.pollFirstEntry());
        System.out.println("pollLast=" + sorted.pollLastEntry());
        System.out.println("remaining=" + sorted);
        System.out.println("remainingFirst=" + sorted.firstEntry());
        System.out.println("remainingLast=" + sorted.lastEntry());
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SequencedMapSortedDemo.java
java SequencedMapSortedDemo
```

Stdout:

```text
sorted={3=three, 2=two, 1=one}
first=3=three
last=1=one
pollFirst=3=three
pollLast=1=one
remaining={2=two}
remainingFirst=2=two
remainingLast=2=two
```

### 10.1. put order does not determine TreeMap order

The code inserts key 2, then 1, then 3. The map prints in 3,2,1 order due to Comparator.reverseOrder. firstEntry returns 3=three; lastEntry returns 1=one.

Changing only the declared variable type from TreeMap to SequencedMap does not change the runtime order. SequencedMap provides a common contract for calling methods; it does not replace the object's Comparator.

### 10.2. Poll does not require explicit positioning support

pollFirstEntry removes key 3; pollLastEntry removes key 1; key 2 remains. A modifiable TreeMap supports these removal operations.

That is different from requesting to place an arbitrary mapping at the front with putFirst. A TreeMap can support retrieving/removing both ends while not supporting explicit positioning. Do not assume every SequencedMap operation has the same level of support just because a poll operation succeeded.

When one mapping remains, remainingFirst and remainingLast are both 2=two. The single-mapping first/last rule is the same as in the LinkedHashMap example, while the policy that determines order is different.


## 11. Access order and removal capability are two separate conditions

### 11.1. Access-ordered LinkedHashMap

With the constructor setting accessOrder=true, mappings are maintained in access order per LinkedHashMap's contract. A successful get can move the accessed mapping to the end of the source map's order.

firstEntry and lastEntry do not count as a get-style access. Therefore, you can inspect both ends without causing the inspected mapping to move due to the access-order mechanism.

When used without explicit repositioning, the head of the map is the least recently accessed candidate. You can use firstEntry to inspect it, or pollFirstEntry to retrieve and evict that candidate. These two APIs do not automatically turn the map into a complete cache: capacity limits, eviction conditions, and resource cleanup must still be decided by the program.

If the code also calls putFirst/putLast to adjust positions explicitly, you must account for the resulting order after those operations. Do not automatically attach a business timestamp to first/last based solely on the name access-order.

The rules for what constitutes an access are described at [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

### 11.2. Unmodifiable views can read but cannot poll

Collections.unmodifiableSequencedMap returns a view that preserves the SequencedMap contract while disallowing modifications through the view. firstEntry and lastEntry can be used to read; poll operations are rejected with UnsupportedOperationException.

Do not try poll as a harmless read to check whether a map is empty. On a modifiable map, that probe actually deletes data; on an unmodifiable view, it can throw an exception. Choose the right API group for your intent.

An unmodifiable view is also not a copy of the data. The source mappings can still be modified through another reference; reads through the view observe the source data per the wrapper's contract.

Reference: [Collections.unmodifiableSequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

## 12. Program 5: reading ends, access order, and unmodifiable views

Save to `SequencedMapPolicyDemo.java`:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class SequencedMapPolicyDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> access = new LinkedHashMap<>(16, 0.75f, true);
        access.put("A", 1);
        access.put("B", 2);
        access.put("C", 3);
        System.out.println("initial=" + access);
        System.out.println("firstBeforeGet=" + access.firstEntry());
        System.out.println("lastBeforeGet=" + access.lastEntry());
        System.out.println("afterEndReads=" + access);
        System.out.println("getA=" + access.get("A"));
        System.out.println("afterGetA=" + access);
        System.out.println("firstAfterGet=" + access.firstEntry());
        System.out.println("pollLeastRecent=" + access.pollFirstEntry());
        System.out.println("afterPoll=" + access);

        SequencedMap<String, Integer> readOnly =
                Collections.unmodifiableSequencedMap(access);
        System.out.println("readOnlyFirst=" + readOnly.firstEntry());
        expectUnsupported("readOnlyPollFirst", () -> readOnly.pollFirstEntry());
        expectUnsupported("readOnlyPollLast", () -> readOnly.pollLastEntry());
        access.put("D", 4);
        System.out.println("readOnlyAfterSourcePut=" + readOnly);
    }
}
```

Compile and run:

```shell
javac --release 21 -encoding UTF-8 SequencedMapPolicyDemo.java
java SequencedMapPolicyDemo
```

Stdout:

```text
initial={A=1, B=2, C=3}
firstBeforeGet=A=1
lastBeforeGet=C=3
afterEndReads={A=1, B=2, C=3}
getA=1
afterGetA={B=2, C=3, A=1}
firstAfterGet=B=2
pollLeastRecent=B=2
afterPoll={C=3, A=1}
readOnlyFirst=C=3
readOnlyPollFirst=UnsupportedOperationException
readOnlyPollLast=UnsupportedOperationException
readOnlyAfterSourcePut={C=3, A=1, D=4}
```

### 12.1. Inspecting both ends does not make A recently accessed

The map starts in A,B,C order. firstBeforeGet is A=1 and lastBeforeGet is C=3. afterEndReads still shows A,B,C.

After get(A), the read result is 1 and the order becomes B,C,A. Now firstAfterGet is B=2. pollLeastRecent removes B=2, leaving C,A.

If you switch the map to default insertion-order mode, do not assume "get(A) moves A to the end". Always check the exact constructor used.

### 12.2. Blocking mutation through the view does not block the source reference

readOnly can read C=3, but both poll calls are rejected. The helper catches specifically UnsupportedOperationException to verify this condition; it does not mask other errors with a broad catch.

After access.put(D,4) via the source reference, readOnly sees C,A,D. This view does not provide a frozen history of the mappings at the time it was created.

### 12.3. Verify each kind of change

There are three distinct actions in the program:

1. Reading entries at both ends: does not remove and does not count as a LinkedHashMap access.
2. get(A) in access-order mode: updates the mapping's encounter order.
3. pollFirstEntry: removes one mapping at the current head.

If you only compare sizes, the second action will be missed because the mapping count stays unchanged. When verifying head/tail behavior, check the order as well, not just size.

## 13. Application patterns and practical limits

### 13.1. Peeking at a single mapping

The following snippet is illustrative code placed inside a method that already has a `pending` variable of type `SequencedMap<String,Integer>` and `Map` imported. It is not a standalone Java file:

```java
Map.Entry<String, Integer> next = pending.firstEntry();
if (next != null) {
    System.out.println(next.getKey() + ":" + next.getValue());
}
```

Checking that `next` is not null handles the case where the Integer value in a valid mapping is null. The code does not invoke methods on a null Entry.

Do not read firstEntry and then assume it is still the head after subsequent changes in the program. The snapshot records information at the time of the call; it does not pin the mapping's position in the map.

### 13.2. Consuming sequentially in current order

In the same context where `pending` is a modifiable map, this illustrative snippet removes mappings one by one from the front:

```java
Map.Entry<String, Integer> next;
while ((next = pending.pollFirstEntry()) != null) {
    System.out.println(next.getKey() + ":" + next.getValue());
}
```

Use the poll result itself both to check whether data remains and to obtain the key–value pair. There is no need for a separate isEmpty check just to decide whether you can read the result.

A precondition of this pattern is that the program allows removing the mapping before processing it. If the work inside fails, the mapping has already been removed from the map; the loop has no built-in acknowledgment, rollback, or retry mechanism. Those requirements must be designed separately.

This pattern suits a finite source with controlled access. If another part of the program keeps adding data, there is no guarantee the loop will terminate just because the map initially held a finite number of mappings.

### 13.3. Do not treat a pair of operations as an atomic transaction by assumption

SequencedMap does not guarantee that every implementation is thread-safe or that combined operations are atomic.

A firstEntry followed by a pollFirstEntry are two separate calls. If a modification occurs in between, the peeked mapping may differ from the mapping actually removed. Even when calling poll alone, thread safety and atomicity under concurrent access must be determined by the concrete class; the SequencedMap interface alone is not enough to conclude that.

The LinkedHashMap and TreeMap in these examples are not used as self-synchronizing structures. If multiple threads share them, you must design proper access coordination; do not rely on Entry snapshots or a modification-check exception as a substitute.

### 13.4. Do not poll while iterating with another iterator

A for-each loop over entrySet uses an iterator. Polling the map from inside that loop is a separate structural modification path. With LinkedHashMap or TreeMap, this can violate the iteration's modification rules and trigger ConcurrentModificationException.

If the goal is to consume from either end, use a dedicated poll loop with appropriate access control. If the goal is to iterate and remove via an iterator, follow that class's iterator contract. Do not mix the two mutation mechanisms arbitrarily.

The fixed stdout examples in this lesson do not depend on thread contention or modification-detection order.

### 13.5. Do not assume a single cost model from the interface alone

SequencedMap specifies the meaning of first/last and return values; it does not promise that all implementations have the same performance cost.

LinkedHashMap and TreeMap use different underlying data structures. A custom class might even rely on default implementations backed by an iterator. Choose the data structure based on both ordering policy and performance requirements; do not infer O(1) for every firstEntry or pollLastEntry just because the method name is short.

Similarly, the returned snapshot is a single Entry, not a full-map copy or a deep clone of all keys and values.

## 14. Common mistakes

| Usage or assumption | Problem | What to do instead |
|---|---|---|
| Using poll to peek at the head of the map | Removes the mapping if supported | Use firstEntry or lastEntry |
| Expecting firstEntry to always have the smallest key | Order depends on the map and Comparator | Identify the actual ordering policy |
| Calling getValue immediately on firstEntry's result | Result can be null when empty | Check the Entry first |
| Treating a null value as no remaining mapping | A valid mapping can have a null value | Distinguish null Entry from null value |
| Using setValue on a snapshot to update the map | It is not a map-mutating entry | Use the map's update API based on current state |
| Expecting a snapshot to hold the latest value after put | Snapshot records the mapping at call time | Re-read if you need current information |
| Thinking a snapshot deep-copies a List value | The List reference may still be shared | Copy values explicitly if independence is needed |
| Polling through reversed and expecting the original map unchanged | Modifiable views share underlying data | Create a separate container if independent consumption is needed |
| Assuming every Entry from a view behaves like firstEntry | Connection/setValue contract depends on how the entry was obtained | Read the contract of the entry-producing API |
| Expecting poll to block until a mapping arrives | It is not a blocking wait operation | Handle null results per the contract |
| Concluding SequencedMap guarantees poll works | Poll is an optional operation | Check the modifiability contract |
| Using firstEntry then remove as a single atomic operation | Changes can occur in between | Design synchronization or choose a structure with the right contract |
| Checking only size on an access-order map | Order can change while size stays the same | Check encounter order as well |
| Expecting Map.equals to check matching order | Map compares mappings, not order, for equals | Check the ordered sequence of keys/entries when order matters |

## 15. Self-check and practice

### 15.1. Questions and answers

1. **How do firstEntry and pollFirstEntry differ?** Both select the current head according to the map's order; firstEntry only reads, while pollFirstEntry also removes the mapping if supported.
2. **When a modifiable map is empty, what do the four methods return?** They return null. Whether removal is unsupported must be evaluated independently of emptiness.
3. **Does a non-null Entry with a null value prove the map is empty?** No. It describes a mapping whose value is null.
4. **A snapshot is taken when task=queued; after put(task,running), does the snapshot automatically change to running?** No. You must read from the map again to get the updated mapping.
5. **Why can modifying a List through another reference still be seen in a snapshot?** The snapshot holds the value reference; it does not deep-copy the List object.
6. **Can you use setValue on the entry from firstEntry to modify the map?** Not under this snapshot contract; the standard examples throw UnsupportedOperationException.
7. **Which side of the source does pollFirstEntry on a LinkedHashMap's reversed view take from?** The tail in the source map's order, while also removing that mapping from the source.
8. **Does a TreeMap with a descending Comparator have the numerically smallest key at the front?** No. For example, with keys 1,2,3, the front is 3 when the Comparator is reverseOrder.
9. **Does firstEntry on an access-order LinkedHashMap count as an access like get?** No. A successful get can change order per the class mechanism, whereas inspecting entries at either end does not create such an access.
10. **Does an Entry snapshot make an inspect-then-remove sequence atomic?** No. That requires a separate concurrency contract and coordination strategy.
11. **Is an unmodifiableSequencedMap view a fixed copy?** No. It blocks mutations through the view, while still reflecting changes made to the source.
12. **Why can a Map variable pointing to a LinkedHashMap not call firstEntry directly at compile time?** The declared type Map does not expose that method; you need an API type that expresses the appropriate ordering contract.

### 15.2. Exercise: predict state after each poll

Create a default LinkedHashMap and sequentially put K2=20, K1=10, K3=30.

Predict, then run: firstEntry, lastEntry, pollLastEntry, pollFirstEntry, firstEntry. Expect the results to be K2=20, K3=30, K3=30, K2=20, K1=10 in order; at the end, the map retains only K1=10.

Switch the two poll calls to operate on reversed and predict again before running. Explain using order direction rather than mechanically swapping First and Last labels.

### 15.3. Exercise: snapshot with two kinds of changes

Create a SequencedMap<String,List<String>> containing a List with two elements. Call firstEntry, then sequentially:

1. Modify the contents of the original List itself.
2. put a completely different List under the same key.

Observe the snapshot at each step. Expect step 1 to be visible because it is the same List object; step 2 does not make the snapshot point to the new List.

Try calling setValue on the snapshot and verify the operation is rejected. Do not use that snapshot result to conclude the map is unmodifiable.

### 15.4. Exercise: ordering policy and modifiability

Use the same set of numeric mappings for an insertion-ordered LinkedHashMap, an access-order LinkedHashMap, and a TreeMap with a descending Comparator.

Print the order before and after calling get on a key, then check firstEntry and lastEntry. Afterward, wrap a map with unmodifiableSequencedMap and test both poll operations separately on a non-empty map.

What to explain: first/last depends on the ordering policy, whereas whether poll succeeds depends on modifiability; these two factors do not substitute for one another.

## 16. References and verification scope

- [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): contract of the four methods, Entry snapshots, reversed views, and mapping order semantics.
- [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): insertion order, access order, operations that constitute accesses, and reversed.
- [NavigableMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html): origin of the first/last APIs on sorted maps, available since Java 6.
- [TreeMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html): ordering by key/Comparator and snapshot entries.
- [Map.Entry — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.Entry.html): distinction between entries from iteration and entries disconnected from the map.
- [Collections — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): unmodifiableSequencedMap and mutability through views.

The five complete programs were compiled with `javac --release 21 -encoding UTF-8` and run on JDK 21.0.9, producing the exact stdout shown. The snippets in the application patterns section are marked as illustrative and must be placed inside a method that already has the `pending` variable and the corresponding imports. They are not presented as standalone Java files.
