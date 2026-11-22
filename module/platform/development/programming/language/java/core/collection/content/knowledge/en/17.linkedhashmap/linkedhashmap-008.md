# First–Last Operations and Reversed Views of LinkedHashMap Since Java 21

## 1. The problem: given an ordered map, how do we work with both ends?

`LinkedHashMap` maintains key–value pairs in a defined encounter order. With a task list keyed by ID, we may want to inspect the first task, remove the last task from the list, move an existing ID to the front, or display the same data in reverse order.

Those requirements differ from a `get(key)` lookup. `get` searches by key, whereas first–last operations locate entries by **position in encounter order**. The first key is not necessarily the smallest, the first name is not necessarily alphabetically first, and the last value is not necessarily the largest.

Since Java 21, `LinkedHashMap` implements `SequencedMap`. As a result, programs have a unified API to inspect, insert, reposition, or remove mappings at either end and to obtain a reversed-order view. This is a standard library API and does not require `--enable-preview`. The examples in this article require JDK 21 or later; they will not compile with `--release 17`. You can verify when these APIs were added in [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

Three concepts will be used throughout:

- **Encounter order:** the order in which entries are observed when iterating over the map.
- **First and last:** the entry at the beginning or end in the order of the target object being called.
- **Reversed view (`reversed` view):** a way of viewing the same map in the opposite direction, backed by the original data.

Picture a map with key order A, B, C:

```text
map:          first → A → B → C ← last
map.reversed: first → C → B → A ← last
```

Simply creating a reversed view does not move A, B, or C in the original map. It changes the direction of observation. When calling a first–last operation on the view, "first" and "last" are evaluated according to the view's direction.

## 2. Identifying the new APIs accurately

### 2.1. Operations on whole mappings

Each mapping, also called an entry, consists of both a key and a value. For a map with key type `K` and value type `V`, the main methods are:

| Method | Return type | Modifies the map? | Meaning |
|---|---|---|---|
| `firstEntry()` | `Map.Entry<K,V>` or `null` | Does not remove/add entries | Inspect the first mapping |
| `lastEntry()` | `Map.Entry<K,V>` or `null` | Does not remove/add entries | Inspect the last mapping |
| `pollFirstEntry()` | `Map.Entry<K,V>` or `null` | Yes, if the map is non-empty | Retrieve and remove the first mapping |
| `pollLastEntry()` | `Map.Entry<K,V>` or `null` | Yes, if the map is non-empty | Retrieve and remove the last mapping |
| `putFirst(k, v)` | Previous value of type `V`, may be `null` | May add/update/reposition | Place the mapping at the front |
| `putLast(k, v)` | Previous value of type `V`, may be `null` | May add/update/reposition | Place the mapping at the end |
| `reversed()` | `SequencedMap<K,V>` | Creates a view, does not reverse original data | View the map in reverse order |

A standard `LinkedHashMap` supports all the mutating operations above. When writing code that accepts an arbitrary `SequencedMap`, remember that some mutating operations are optional: an implementation may not support arbitrarily placing mappings at the first or last position. The interface name does not remove the constraints of the concrete object.

### 2.2. Sequenced views

Three additional methods allow working with keys alone, values alone, or entries as types that support first–last operations:

| Method | Return type | What is an element of the view? |
|---|---|---|
| `sequencedKeySet()` | `SequencedSet<K>` | A key |
| `sequencedValues()` | `SequencedCollection<V>` | A value |
| `sequencedEntrySet()` | `SequencedSet<Map.Entry<K,V>>` | An entry |

`SequencedSet` combines the uniqueness guarantee of `Set` with a defined encounter order. `SequencedCollection` only describes an ordered collection without imposing uniqueness. Because multiple distinct keys can map to the same value, a map's values view is a collection, not a set.

The legacy views `keySet()`, `values()`, and `entrySet()` still iterate in `LinkedHashMap` order. Adding the new APIs does not make them unordered. The difference is that the return types of the new methods express first–last capabilities directly in source code.

### 2.3. Declared type determines which methods can be called

The following snippet is illustrative code inside a method, not a standalone Java file:

```java
LinkedHashMap<String, Integer> linked = new LinkedHashMap<>();
Map<String, Integer> general = linked;
SequencedMap<String, Integer> ordered = linked;

ordered.firstEntry();
linked.putFirst("A", 1);
// general.firstEntry(); // Does not compile: Map does not declare this method.
```

`general` and `ordered` may point to the same object. However, the compiler checks available methods against the variable's declared type. If an API needs ordering and both ends, accepting or returning `SequencedMap` communicates that requirement more clearly than `Map` alone.

You should not cast an arbitrary `Map` to `SequencedMap` just to make code compile. For example, a `HashMap` does not become an ordered map simply by being cast. You must know the actual object type or design appropriate API signatures.

## 3. Inspecting ends and polling ends are different actions

### 3.1. firstEntry and lastEntry only observe

`firstEntry()` returns the current first entry; `lastEntry()` returns the current last entry. They do not remove entries from the map. In access-order mode, these two inspection calls also do not count as a `get` access that promotes an entry to most-recently-used.

With order A, B, C, calling `firstEntry()` followed by `lastEntry()` leaves the order as A, B, C with all three entries intact. When you only need to inspect the next item to process without removing it yet, these are the appropriate operations.

### 3.2. pollFirstEntry and pollLastEntry both retrieve and remove

`pollFirstEntry()` returns the first entry and removes the corresponding mapping. `pollLastEntry()` does the same at the end. Even if you only print the result of a `poll` call, the map has already been modified without needing a separate `remove` statement.

For example, with order A, B, C:

```text
firstEntry()     → returns A, map remains [A, B, C]
pollFirstEntry() → returns A, map becomes [B, C]
pollLastEntry()  → returns C, map becomes [B]
```

These are mapping-level operations: they do not merely drop a value from an isolated list. After polling A, looking up key A in the map will no longer find that mapping.

### 3.3. Empty maps return null for all four methods

`firstEntry`, `lastEntry`, `pollFirstEntry`, and `pollLastEntry` all return `null` when the map is empty. Do not immediately call `map.firstEntry().getKey()` without knowing an entry exists. Store the result in a variable, check that it is non-`null`, and then read its key and value.

Allowing `null` values in the map does not make the entry result ambiguous the way `get` does. A map containing the mapping `A → null` has a non-`null` `firstEntry()`; only `entry.getValue()` is `null`. Similarly, if the key itself is `null`, the entry still exists.

## 4. putFirst and putLast: updating and positioning together

### 4.1. Absent key: insert at the front or end

`putFirst(k, v)` inserts a new mapping at the beginning of the encounter order. `putLast(k, v)` inserts a new mapping at the end. If there was no previous mapping for the key, the return value is `null`.

No integer index is passed. This is not `List.add(index, element)`, and there is no operation to insert directly at position 5. When calling `get(0)` on a map with integer keys, `0` is still the lookup key, not the index of the first entry.

### 4.2. Present key: keep one mapping, update value, and reposition

If the key already exists, `putFirst` or `putLast` updates that mapping's value and moves it to the front or end if needed. They do not create a duplicate key at the new position. The map still obeys the rule of at most one mapping per key.

The return value is the **previous value**, not the new entry, not a position, and not a flag indicating whether the entry moved. If the previous value was `null`, returning `null` does not distinguish that case from an absent key. When you need to know prior existence, check according to the appropriate contract before updating.

### 4.3. Difference from plain put in insertion-order mode

In a default `LinkedHashMap`, `put` for an existing key only replaces the value while preserving the key's position. `putFirst` and `putLast` express explicit positioning intent, so they can still change that position.

| Initial state `[A, B, C]` | Order after operation |
|---|---|
| `put("B", newValue)` on an insertion-order map | `[A, B, C]` |
| `putFirst("B", newValue)` | `[B, A, C]` |
| `putLast("B", newValue)` | `[A, C, B]` |

The table above shows three independent trials starting from the same state. Do not read them as three sequential operations. Access-order mode will be examined separately because plain `put` in that mode also refreshes access recency.

## 5. Program 1: inserting, repositioning, inspecting, and polling

Save the complete program as `LinkedHashMapEndsDemo.java`. The map is created with the default constructor, so it uses insertion order. The example uses key names that make positions easy to track; no alphabetical sorting takes place.

```java
import java.util.LinkedHashMap;

public class LinkedHashMapEndsDemo {
    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
        map.put("beta", 2);
        map.put("delta", 4);

        System.out.println("putFirstNew=" + map.putFirst("alpha", 1));
        System.out.println("putLastNew=" + map.putLast("omega", 9));
        System.out.println("afterNew=" + map);

        System.out.println("putFirstExisting=" + map.putFirst("delta", 40));
        System.out.println("afterMoveFirst=" + map);
        System.out.println("putLastExisting=" + map.putLast("alpha", 10));
        System.out.println("afterMoveLast=" + map);

        map.put("beta", 20);
        System.out.println("afterPlainPut=" + map);
        System.out.println("first=" + map.firstEntry());
        System.out.println("last=" + map.lastEntry());
        System.out.println("beforePollSize=" + map.size());

        System.out.println("pollFirst=" + map.pollFirstEntry());
        System.out.println("pollLast=" + map.pollLastEntry());
        System.out.println("remaining=" + map);
        System.out.println("size=" + map.size());
    }
}
```

Compile and run with JDK 21 or later:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapEndsDemo.java
java LinkedHashMapEndsDemo
```

Stdout:

```text
putFirstNew=null
putLastNew=null
afterNew={alpha=1, beta=2, delta=4, omega=9}
putFirstExisting=4
afterMoveFirst={delta=40, alpha=1, beta=2, omega=9}
putLastExisting=1
afterMoveLast={delta=40, beta=2, omega=9, alpha=10}
afterPlainPut={delta=40, beta=20, omega=9, alpha=10}
first=delta=40
last=alpha=10
beforePollSize=4
pollFirst=delta=40
pollLast=alpha=10
remaining={beta=20, omega=9}
size=2
```

### 5.1. Track order rather than looking only at values

Initially the map has `beta` and `delta`. Adding `alpha` at the front and `omega` at the end produces `[alpha, beta, delta, omega]`. Both insertions of new keys return `null`.

`putFirst("delta", 40)` returns the old value `4`, updates it to `40`, and moves `delta` to the front. Next, `putLast("alpha", 10)` returns `1`, updates it to `10`, and moves `alpha` to the end. The entry count stays four because both keys already existed.

`put("beta", 20)` only updates `beta` in place. Because this map uses insertion order, the resulting order remains `[delta, beta, omega, alpha]`.

`first=delta=40` and `last=alpha=10` show how an entry is printed in `key=value` format; those lines do not mean the methods return a string containing two equals signs. The actual return type is `Map.Entry<String, Integer>`.

### 5.2. Poll to retrieve and remove

The two inspection calls do not change `beforePollSize=4`. After `pollFirstEntry`, `delta` is removed. After `pollLastEntry`, `alpha` is removed. The map retains `beta` and `omega`, with size two.

This observation also explains why you must not use `poll` merely to check "what the next task is" if you still want to keep that task. Choose `firstEntry` or `lastEntry` when the intent is read-only.

## 6. Program 2: returned entries are snapshots, not live map editors

### 6.1. A snapshot of the mapping at call time

The four methods that return entries directly on `SequencedMap` — `firstEntry`, `lastEntry`, `pollFirstEntry`, `pollLastEntry` — return a **snapshot** of the mapping at the moment of the call. They do not support `setValue` to mutate the value in the map. This contract is documented in [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

Do not assume that every value of type `Map.Entry` can modify the map via `setValue`. How you obtain the entry determines its connection contract with the map. In particular, a snapshot entry differs from an entry provided during an `entrySet()` iteration.

The following program saves a snapshot, updates the map, attempts `setValue` on the snapshot, and checks `null` key/value cases. Save it as `LinkedHashMapEntrySnapshotDemo.java`.

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapEntrySnapshotDemo {
    public static void main(String[] args) {
        LinkedHashMap<String, String> map = new LinkedHashMap<>();
        System.out.println("emptyFirst=" + map.firstEntry());
        System.out.println("emptyLast=" + map.lastEntry());
        System.out.println("emptyPollFirst=" + map.pollFirstEntry());
        System.out.println("emptyPollLast=" + map.pollLastEntry());

        map.put(null, null);
        Map.Entry<String, String> snapshot = map.firstEntry();
        System.out.println("snapshot=" + snapshot);
        System.out.println("entryExists=" + (snapshot != null));
        System.out.println("keyIsNull=" + (snapshot.getKey() == null));
        System.out.println("valueIsNull=" + (snapshot.getValue() == null));

        map.put(null, "updated");
        System.out.println("currentFirst=" + map.firstEntry());
        System.out.println("oldSnapshot=" + snapshot);
        try {
            snapshot.setValue("changed");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("setValue=UnsupportedOperationException");
        }

        Map.Entry<String, String> removed = map.pollFirstEntry();
        System.out.println("removed=" + removed);
        System.out.println("emptyAfterPoll=" + map.isEmpty());
        System.out.println("removedValue=" + removed.getValue());
    }
}
```

Compile and run with JDK 21 or later:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapEntrySnapshotDemo.java
java LinkedHashMapEntrySnapshotDemo
```

Stdout:

```text
emptyFirst=null
emptyLast=null
emptyPollFirst=null
emptyPollLast=null
snapshot=null=null
entryExists=true
keyIsNull=true
valueIsNull=true
currentFirst=null=updated
oldSnapshot=null=null
setValue=UnsupportedOperationException
removed=null=updated
emptyAfterPoll=true
removedValue=updated
```

### 6.2. Do not confuse a null entry with a null key or value

The first four lines all print `null` because the map is empty. After `map.put(null, null)`, `snapshot` is a real entry printed as `null=null`. Therefore:

- `snapshot != null` is `true`.
- `snapshot.getKey() == null` is `true`.
- `snapshot.getValue() == null` is also `true`.

These are three distinct checks. With APIs that return an entry object, a mapping whose value is `null` remains distinguishable from having no mapping at the front of the map.

After updating the `null` key to `"updated"`, the current first entry is `null=updated`, while the old snapshot remains `null=null`. It is not a live handle that automatically syncs with subsequent value updates in the map.

### 6.3. setValue and snapshot independence

Calling `snapshot.setValue("changed")` throws `UnsupportedOperationException`. To update a mapping, call the map API matching your intended positioning: preserve position according to `put` rules, move to the front with `putFirst`, or move to the end with `putLast`.

After `pollFirstEntry`, the map is empty, yet `removed` still lets you read `updated`. It is a result describing the mapping that was just removed, not an entry still belonging to the map.

A snapshot does not mean deep-copying every object. If a key or value is a mutable object, the snapshot can still hold a reference to that same object. This example uses `String`, so `map.put` replaces the value reference with another string while the snapshot keeps the old reference. Do not use this outcome to claim that a mutable value would be cloned.

### 6.4. Do not treat all ways of obtaining an entry as identical

Three cases must be kept distinct:

| How the entry is obtained | What to know |
|---|---|
| `map.firstEntry()` or the other three first–last entry methods | Snapshot; does not support modifying the map via `setValue` |
| Entry during iteration over `map.entrySet()` or `sequencedEntrySet()` | Connected to the mapping per the iteration contract; `LinkedHashMap` allows updating the value via `setValue` within valid bounds |
| `map.sequencedEntrySet().getFirst()` | Do not carry over the snapshot guarantee or `setValue` behavior of `firstEntry()` to this call; `SequencedMap` does not universally specify connectedness for entries obtained this way |

In this article, view examples only read and print entries obtained via `getFirst`; do not rely on any assumption that `setValue` on such an entry must behave like another kind of entry.

## 7. reversed(): flipping the viewing direction over the same data

### 7.1. The view's first is the original map's last

Assigning `reverse = map.reversed()` simply creates another way to operate on the existing data. With `LinkedHashMap`, permitted mutations through the view propagate to the original map, and changes to the original map appear in the view. This is backed-view behavior, not copy behavior.

The correspondence between positional operations is:

| Call on `reverse` | Corresponding position in original `map` |
|---|---|
| `reverse.firstEntry()` | Inspect end of original map |
| `reverse.lastEntry()` | Inspect start of original map |
| `reverse.pollFirstEntry()` | Retrieve and remove end of original map |
| `reverse.pollLastEntry()` | Retrieve and remove start of original map |
| `reverse.putFirst(k, v)` | Place mapping at end of original map |
| `reverse.putLast(k, v)` | Place mapping at start of original map |

If the key already exists, the put operation still updates its value and repositions it accordingly without creating a second entry. The terms "first" and "last" must always be interpreted relative to the receiver object's direction.

### 7.2. Creating a view does not reverse the underlying structure

Suppose the original map is `[A, B, C]`. After obtaining the reversed view, the original map still iterates `[A, B, C]`, while the view iterates `[C, B, A]`. Both observe the same three mappings. At no point is the original map rewritten to `[C, B, A]` merely because `reversed()` was called.

This is useful when displaying the same dataset in both directions or polling from either end without building a duplicate map. However, returning a view to another caller also means handing out a handle connected to the original map. Calling `reverse.clear()` on a modifiable view will clear the original map's data.

### 7.3. Plain put on the view is not the view's putLast

This is an easy point to misread: because you are looking in reverse, you might assume `reverse.put(k, v)` with a new key appends to the end of the view. On `LinkedHashMap`'s reversed view, plain `put` follows the original map's behavior. In an insertion-order map, a new key is appended to the end of the **original map**, so it appears at the **front of the reversed view**.

To specify a position in the view, use `reverse.putFirst` or `reverse.putLast`. Do not assume `put` means "append to the end of the view" just because some other collection type appends at the end. The [LinkedHashMap source in OpenJDK 21](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/LinkedHashMap.java) shows that the view forwards `put` to the original map, whereas `putFirst` and `putLast` swap ends accordingly.

In insertion-order mode, updating an existing key via `reverse.put` still does not move that key. In access-order mode, that operation also records an access according to the original map's policy. A later section examines access-order mode with a dedicated program.

## 8. Program 3: bidirectional edits and creating an independent copy

Save the complete program as `LinkedHashMapReversedDemo.java`. `reverse` is a view; `copy` is a new map constructed from the order observed through the view.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class LinkedHashMapReversedDemo {
    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        SequencedMap<String, Integer> reverse = map.reversed();
        LinkedHashMap<String, Integer> copy = new LinkedHashMap<>(reverse);

        System.out.println("original=" + map);
        System.out.println("reverse=" + reverse);
        System.out.println("reverseFirst=" + reverse.firstEntry());
        System.out.println("reverseLast=" + reverse.lastEntry());

        reverse.putFirst("X", 24);
        System.out.println("afterReversePutFirst=" + map);
        reverse.putLast("Y", 25);
        System.out.println("afterReversePutLast=" + map);
        reverse.put("Z", 26);
        System.out.println("afterReversePlainPut=" + map);
        System.out.println("reverseNow=" + reverse);

        reverse.put("B", 20);
        reverse.remove("A");
        map.putLast("W", 23);
        System.out.println("sharedOriginal=" + map);
        System.out.println("sharedReverse=" + reverse);

        System.out.println("reversePollFirst=" + reverse.pollFirstEntry());
        System.out.println("reversePollLast=" + reverse.pollLastEntry());
        System.out.println("remainingOriginal=" + map);
        System.out.println("remainingReverse=" + reverse);
        System.out.println("twiceReversedOrder=" + reverse.reversed().keySet());
        System.out.println("equalMappings=" + map.equals(reverse));
        System.out.println("independentCopy=" + copy);
    }
}
```

Compile and run with JDK 21 or later:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapReversedDemo.java
java LinkedHashMapReversedDemo
```

Stdout:

```text
original={A=1, B=2, C=3}
reverse={C=3, B=2, A=1}
reverseFirst=C=3
reverseLast=A=1
afterReversePutFirst={A=1, B=2, C=3, X=24}
afterReversePutLast={Y=25, A=1, B=2, C=3, X=24}
afterReversePlainPut={Y=25, A=1, B=2, C=3, X=24, Z=26}
reverseNow={Z=26, X=24, C=3, B=2, A=1, Y=25}
sharedOriginal={Y=25, B=20, C=3, X=24, Z=26, W=23}
sharedReverse={W=23, Z=26, X=24, C=3, B=20, Y=25}
reversePollFirst=W=23
reversePollLast=Y=25
remainingOriginal={B=20, C=3, X=24, Z=26}
remainingReverse={Z=26, X=24, C=3, B=20}
twiceReversedOrder=[B, C, X, Z]
equalMappings=true
independentCopy={C=3, B=2, A=1}
```

### 8.1. Three objects, two data relationships

Right after creation:

```text
map:     {A=1, B=2, C=3}
reverse: {C=3, B=2, A=1}   ← views the same data in reverse
copy:    {C=3, B=2, A=1}   ← new map, capturing that order at creation time
```

`reverse` and `copy` print identically at the start, yet their subsequent behavior differs. How an object was constructed determines independence, not how it prints initially.

`new LinkedHashMap<>(reverse)` iterates over the reversed view's mappings and inserts them into a new insertion-order map. Subsequent structural changes or value replacements in the original map do not update the new map. This is still a shallow copy: key/value objects themselves can be shared if they are mutable.

### 8.2. Placing at first and last through the view

The first three operations produce notable results:

| Operation | Original map order after operation | What happened |
|---|---|---|
| `reverse.putFirst("X", 24)` | `[A, B, C, X]` | X is first in the view, i.e., last in the original |
| `reverse.putLast("Y", 25)` | `[Y, A, B, C, X]` | Y is last in the view, i.e., first in the original |
| `reverse.put("Z", 26)` | `[Y, A, B, C, X, Z]` | Plain `put` appends to the end of the original |

Hence `reverseNow` prints `[Z, X, C, B, A, Y]`. There is no need to manually reverse a key list after each mutation; the view reflects the reversed order of the live data.

### 8.3. Value updates and entry removals both pass through

`reverse.put("B", 20)` updates the original map's B mapping to `B=20`. `reverse.remove("A")` removes A from the original map. `map.putLast("W", 23)` appends W to the end of the original map and immediately places W at the front of the view.

`reverse.pollFirstEntry()` then removes W, since W is first in the view. `reverse.pollLastEntry()` removes Y, since Y is last in the view. The original map is left with `[B, C, X, Z]`, and the view with `[Z, X, C, B]`.

This is one set of mappings observed from two directions, not two maps requiring manual synchronization. If a program holds multiple view variables, remember that removing a mapping through any of them affects all other views.

### 8.4. Reversing twice and equality

`reverse.reversed()` restores the original map's order. The example checks the key order `[B, C, X, Z]`; do not use object identity `==` to define what double reversal means across all `SequencedMap` implementations.

`map.equals(reverse)` prints `true` even though their iteration orders are opposite. Map equality compares mappings, not encounter order. If you need to verify order, extract an ordered key list for comparison; do not use `Map.equals` as proof that two maps iterate in the same order.

`independentCopy={C=3, B=2, A=1}` preserves the data and order from when the copy was created. B in the copy is still 2, A is still present, and X/Y/Z/W were never added to the copy. This cleanly separates a **live view** from a **point-in-time copy**.

## 9. Sequenced views of keys, values, and entries

### 9.1. Each view's ends follow the map's order

Given `{A=7, B=7, C=9}`:

| View | Element order | First element | Last element |
|---|---|---|---|
| `sequencedKeySet()` | `[A, B, C]` | A | C |
| `sequencedValues()` | `[7, 7, 9]` | 7 (for A) | 9 (for C) |
| `sequencedEntrySet()` | `[A=7, B=7, C=9]` | A=7 | C=9 |

Each view supports `getFirst` and `getLast` to inspect elements in that view's order. They are not aliases for `Map.firstEntry`: the returned element type depends on the view. `keys.getFirst()` returns a key, `values.getFirst()` returns a value, and `entries.getFirst()` returns an entry.

Calling `reversed()` on a view reverses that view's perspective. For example, `map.sequencedKeySet().reversed()` yields the same key order as `map.reversed().sequencedKeySet()`. Both remain backed by the same map; a longer call chain does not create an independent copy.

### 9.2. Removing from a view removes the mapping from the map

These `LinkedHashMap` views support element removal. `keys.removeFirst()` removes the first key and its mapping; `values.removeLast()` removes the last value along with the mapping holding it; `entries.removeFirst()` removes the first entry.

Because values can repeat, position matters. With `A=7, B=7, C=9`, `values.removeFirst()` returns `7` and removes `A=7`, without removing all mappings with value `7`. `B=7` remains. Afterward, the key and entry views also reflect that A has left the map.

### 9.3. Unsupported add on a view does not mean the map is read-only

A modifiable map does not imply every add operation on every collection view is supported. On `LinkedHashMap`'s sequenced views, adding elements via `addFirst` or `addLast` is unsupported and throws `UnsupportedOperationException`.

For key or value views, adding a single element does not even describe a full key–value pair. Even for the entry view, which has both components, the view API does not provide that add operation. To insert or position a mapping, use `putFirst`/`putLast` on the map.

Therefore, do not read `SequencedSet` or `SequencedCollection` as a promise that every mutating method on the interface works on every view. Read, remove, and add capabilities must be checked separately.

### 9.4. Empty views throw exceptions on first/last get and remove

For the modifiable collection views in this article:

| Empty scenario | Result |
|---|---|
| `map.firstEntry()` or `map.lastEntry()` | `null` |
| `map.pollFirstEntry()` or `map.pollLastEntry()` | `null` |
| `keys.getFirst()` or `keys.getLast()` | `NoSuchElementException` |
| `keys.removeFirst()` or `keys.removeLast()` | `NoSuchElementException` |
| `values.getFirst/getLast/removeFirst/removeLast` | Same exception rule when empty |

The collection contract is documented in [SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html). Never use `keys.getFirst() == null` to test whether a view is empty: if the view is empty, the call throws an exception; if the first valid key is `null`, the result can be `null` even when the map is non-empty.

## 10. Program 4: mutability and empty-state errors of views

Save as `LinkedHashMapSequencedViewsDemo.java`. The exceptions in this example are caught intentionally and printed by name to verify the contracts, rather than ignoring unexpected errors.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.SequencedCollection;
import java.util.SequencedSet;

public class LinkedHashMapSequencedViewsDemo {
    private static void unsupported(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    private static void missing(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println(label + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 7);
        map.put("B", 7);
        map.put("C", 9);

        SequencedSet<String> keys = map.sequencedKeySet();
        SequencedCollection<Integer> values = map.sequencedValues();
        SequencedSet<Map.Entry<String, Integer>> entries =
                map.sequencedEntrySet();

        System.out.println("keyEnds=" + keys.getFirst() + "," + keys.getLast());
        System.out.println("valueEnds=" + values.getFirst() + "," + values.getLast());
        System.out.println("firstEntryFromView=" + entries.getFirst());
        System.out.println("reversedKeys=" + keys.reversed());
        System.out.println("reversedValues=" + values.reversed());

        unsupported("keyAddFirst", () -> keys.addFirst("X"));
        unsupported("valueAddLast", () -> values.addLast(99));
        unsupported("entryAddFirst",
                () -> entries.addFirst(Map.entry("X", 99)));

        System.out.println("removedFirstValue=" + values.removeFirst());
        System.out.println("afterValueRemoval=" + map);
        System.out.println("removedReverseFirstKey="
                + keys.reversed().removeFirst());
        System.out.println("afterReverseKeyRemoval=" + map);
        System.out.println("removedLastEntry=" + entries.removeLast());
        System.out.println("empty=" + map.isEmpty());

        missing("emptyKeyGetFirst", () -> keys.getFirst());
        missing("emptyKeyRemoveLast", () -> keys.removeLast());
        missing("emptyValueGetLast", () -> values.getLast());
        System.out.println("emptyMapFirst=" + map.firstEntry());

        map.put("D", 4);
        System.out.println("sameKeyViewAfterPut=" + keys);
        System.out.println("sameValueViewAfterPut=" + values);
    }
}
```

Compile and run with JDK 21 or later:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapSequencedViewsDemo.java
java LinkedHashMapSequencedViewsDemo
```

Stdout:

```text
keyEnds=A,C
valueEnds=7,9
firstEntryFromView=A=7
reversedKeys=[C, B, A]
reversedValues=[9, 7, 7]
keyAddFirst=UnsupportedOperationException
valueAddLast=UnsupportedOperationException
entryAddFirst=UnsupportedOperationException
removedFirstValue=7
afterValueRemoval={B=7, C=9}
removedReverseFirstKey=C
afterReverseKeyRemoval={B=7}
removedLastEntry=B=7
empty=true
emptyKeyGetFirst=NoSuchElementException
emptyKeyRemoveLast=NoSuchElementException
emptyValueGetLast=NoSuchElementException
emptyMapFirst=null
sameKeyViewAfterPut=[D]
sameValueViewAfterPut=[4]
```

### 10.1. Removing at the exact view position

Three removals run in sequence:

1. `values.removeFirst()` returns `7` and removes `A`, leaving `{B=7, C=9}`.
2. `keys.reversed().removeFirst()` returns `C` because `C` is first in the reversed key view, leaving `{B=7}`.
3. `entries.removeLast()` returns `B=7` and removes the final mapping, leaving the map empty.

Duplicate values remain tied to distinct mappings. Removing the first value does not remove all entries with that value. Removing the first key of a reversed view does not remove the first key of the original map.

### 10.2. Views stay live even after the map becomes empty

After the three removals, `keys`, `values`, and `entries` do not become permanently empty collections. They remain live views of the map. When `D=4` is inserted into the original map, those same view variables print `[D]` and `[4]`.

This is why you should never store a view and treat it as "the data at creation time". If you need an independent key list for later computation, create a new collection from the view in the desired direction. If you need both mappings and an independent order, create a new map like `copy` in the previous example.

Rejected add calls do not alter the map. Get/remove calls on empty views throw `NoSuchElementException`, while `emptyMapFirst=null` confirms that the map's entry-returning API follows a different empty-state rule.

## 11. Combining with access-order mode

### 11.1. View direction and access policy are separate concerns

`LinkedHashMap` uses insertion order by default. The three-argument constructor with `true` uses access order:

```java
// Illustrating configuration inside a method.
LinkedHashMap<String, Integer> map =
        new LinkedHashMap<>(16, 0.75f, true);
```

In an access-order original map, a `get` that finds a key moves that entry to the end. The reversed view observes the same change in the opposite direction, so the accessed entry appears at the **front of the reversed view**.

Do not infer that calling `reverse.get(key)` changes the policy to move the entry to the end of the view. The call still registers an access on the original map. Entry recency belongs to the single underlying map; there is no separate access history for the view.

Conversely, explicit positioning operations like `putFirst`/`putLast` place the entry at the requested end; they do not also trigger an access refresh that pulls the entry back to the end of the original map. If `putFirst` were immediately pulled to the end by an access refresh, it could never fulfill its contract of placing an entry at the front.

`firstEntry` and `lastEntry` only inspect the ends and do not refresh recency. Inspecting via collection views does not turn into `get` accesses either. Reading the exact method semantics matters more than lumping all of these together as "reading data".

### 11.2. Program 5: comparing each repositioning step

Save as `LinkedHashMapAccessOrderEndsDemo.java`. The program prints the original and reversed key orders side by side after each step to avoid confusing the two ends.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class LinkedHashMapAccessOrderEndsDemo {
    private static void show(String label,
            LinkedHashMap<String, Integer> map,
            SequencedMap<String, Integer> reverse) {
        System.out.println(label + ": original=" + map.keySet()
                + ", reverse=" + reverse.keySet());
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map =
                new LinkedHashMap<>(16, 0.75f, true);
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        SequencedMap<String, Integer> reverse = map.reversed();

        System.out.println("first=" + map.firstEntry());
        System.out.println("last=" + map.lastEntry());
        show("afterInspect", map, reverse);

        System.out.println("reverseGetA=" + reverse.get("A"));
        show("afterReverseGet", map, reverse);
        System.out.println("reverseContainsB=" + reverse.containsKey("B"));
        show("afterContains", map, reverse);

        map.putFirst("C", 30);
        show("afterExplicitFirst", map, reverse);
        System.out.println("getC=" + map.get("C"));
        show("afterGetC", map, reverse);

        reverse.putLast("A", 10);
        show("afterReverseExplicitLast", map, reverse);
        System.out.println("reverseGetB=" + reverse.get("B"));
        show("afterReverseGetB", map, reverse);
    }
}
```

Compile and run with JDK 21 or later:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapAccessOrderEndsDemo.java
java LinkedHashMapAccessOrderEndsDemo
```

Stdout:

```text
first=A=1
last=C=3
afterInspect: original=[A, B, C], reverse=[C, B, A]
reverseGetA=1
afterReverseGet: original=[B, C, A], reverse=[A, C, B]
reverseContainsB=true
afterContains: original=[B, C, A], reverse=[A, C, B]
afterExplicitFirst: original=[C, B, A], reverse=[A, B, C]
getC=30
afterGetC: original=[B, A, C], reverse=[C, A, B]
afterReverseExplicitLast: original=[A, B, C], reverse=[C, B, A]
reverseGetB=2
afterReverseGetB: original=[A, C, B], reverse=[B, C, A]
```

### 11.3. Explaining the output

The initial two inspections return `A=1` and `C=3`, yet `afterInspect` remains `[A, B, C]`. They do not refresh A or C.

`reverse.get("A")` finds A. The original map becomes `[B, C, A]`; the view becomes `[A, C, B]`. The newly accessed A is at the end of the original map and the front of the reversed view. `reverse.containsKey("B")` returns `true` without changing order, so B remains at the front of the original map.

`map.putFirst("C", 30)` places C at the front of the original map and updates its value to `30`. The result is `[C, B, A]`, not a state with C at the end due to an implicit access refresh. Immediately afterward, `map.get("C")` is an actual access and moves C to the end, yielding `[B, A, C]`.

`reverse.putLast("A", 10)` places A at the end of the view, which is the front of the original map. The original becomes `[A, B, C]`, and the reversed view becomes `[C, B, A]`. The final `reverse.get("B")` records an access again, moving B to the end of the original `[A, C, B]` and to the front of the view `[B, C, A]`.

The table below summarizes the differences on the same access-order map:

| Operation type | Intentionally refreshes access recency? | How position is interpreted |
|---|---|---|
| `get` that finds a key, including via reversed view | Yes | End of original, front of reversed view |
| `containsKey` | No | Does not change position |
| `firstEntry`/`lastEntry` | No | Only inspects current ends |
| `putFirst`/`putLast` | Explicit positioning | Relative to first/last of the receiver |
| Iterating views to read elements | Does not record accesses | Follows the view's direction |

### 11.4. Implications when the map is used as an LRU cache

In an access-order map subjected only to normal accesses, the front of the original map represents the least-recently-used entry. However, `putFirst` lets a program explicitly move an entry to the front. After such an explicit placement, you should no longer interpret the order as a history determined solely by usage.

If a cache class wants to preserve a consistent automatic LRU policy, it must decide whether external callers are allowed to invoke explicit positioning methods. Having a new API does not mean exposing every method freely while still claiming the cache is purely access-history driven.

In the reversed view, `pollFirstEntry()` removes the last entry of the original map. Under normal access order, that is the most-recently-used end, not the oldest entry. If you want to evict the oldest entry from a reversed view, the corresponding position is the end of the view. Before writing eviction logic based on first/last, confirm whether you hold the original map or the reversed view, and whether manual positioning has been used.

## 12. Choosing operations by intent

### 12.1. When inspecting, removing, positioning, or copying

| Intent | Appropriate expression on LinkedHashMap |
|---|---|
| Inspect the first mapping while keeping it | `firstEntry()` |
| Remove the last mapping from the map | `pollLastEntry()` |
| Move a key to the front with a desired value | `putFirst(key, value)` |
| Move a key to the end | `putLast(key, value)` |
| Traverse the same data in reverse | `reversed()` |
| Get the first key and accept an exception if empty | `sequencedKeySet().getFirst()` |
| Remove the last mapping via the key view | `sequencedKeySet().removeLast()` |
| Keep a separate map in the reversed order at creation time | `new LinkedHashMap<>(map.reversed())` |

These choices reflect distinct semantics, not interchangeable syntax. A view is not a copy; polling is not inspecting; a snapshot entry is not a direct editor for the mapping.

### 12.2. Draining mappings sequentially in one direction

If you need to drain all mappings in current order to process them on a single thread, you can use `poll` instead of acquiring an iterator and removing outside the iterator. The snippet below illustrates code inside a method that already has `map`; it is not a standalone program:

```java
Map.Entry<String, Integer> next;
while ((next = map.pollFirstEntry()) != null) {
    System.out.println(next.getKey() + ":" + next.getValue());
}
```

This loop **empties the map** when it runs to completion. It checks whether an entry object exists rather than using the entry's value to decide when to stop, so a mapping with a `null` value will not terminate the loop prematurely.

If you only want to iterate while keeping the data, use `forEach` or iterate `entrySet()` in the desired direction. If you want to drain from the opposite direction, use `pollLastEntry()` on the original map or `pollFirstEntry()` on the reversed view; both mutate the same map.

Polling before processing also implies an application-level design decision: if processing fails, the mapping has already left the map. Do not assume this provides a transactional work queue, retry mechanism, or durability simply because first–last polling APIs exist.

### 12.3. Keeping isolated data requires creating a new structure

`reversed()` by itself neither grants read-only protection nor isolates mutations. If you return a view to external callers, treat it as a handle connected to the original map. When the requirement is a structurally independent snapshot of the data, construct a new collection or map in the order you want to preserve.

The new copy is still mutable. Structural independence differs from object immutability, and shallow copying differs from deep copying. In examples using `String`/`Integer`, values cannot be mutated in place; for mutable domain objects, reference-sharing contracts must be defined separately.

Do not rely on `Map.copyOf` expecting it to "preserve the exact reversed order": the iteration order of maps created by that method is unspecified, per [Map — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#unmodifiable). Requiring a specific order must be expressed using a type or constructor with an ordering contract. Within the scope of this article, the `LinkedHashMap` constructor taking the reversed view clearly preserves the order when creating a copy.

## 13. Things to verify in production code

### 13.1. Iteration and repositioning

Moving entries with `putFirst`/`putLast`, or adding/removing entries, can alter the ordering structure an active iterator relies on. Mutating through the reversed view still mutates the same map; there is no isolated iterator protected simply because it was created from the opposite direction.

Especially in access-order mode, calling `get` while iterating over the same map can also change the order. To read keys and values during a single pass, read from the current entry rather than extracting the key and calling `get` again.

Fail-fast iterators may throw `ConcurrentModificationException` when they detect structural modifications, even on a single thread. That mechanism operates on a best-effort basis to detect bugs, not as a guarantee for program coordination. Do not build correctness logic on the assumption that every concurrent modification is guaranteed to throw.

If you need to reposition multiple entries based on a decision list, collect the keys into a separate collection first and apply the updates after the iteration finishes. Be explicit about the fact that those updates intentionally alter the order; copying the key list only decouples iteration from the map and does not negate the effects of subsequent calls.

### 13.2. Multiple threads are not protected by a view

`LinkedHashMap` is not synchronized. A reversed view does not make it thread-safe either. The original map, reversed view, and collection views all share the underlying state, so multi-threaded coordination must account for all of those access paths.

`firstEntry()` followed by `pollFirstEntry()` are two separate calls. If state can change in between, do not assume the inspected entry is the one that will be polled. For a single-step retrieval in the single-threaded model of this article, call `poll` directly and process its return value; multi-threaded atomicity requires a different design.

In an access-order map, a `get` call can modify order links, so not all read operations are state-preserving. The examples in this article run sequentially on a single thread and make no concurrency guarantees.

### 13.3. Compile-time and runtime versions

To use the APIs in this article, you need Java 21 or later at compile time and a compatible runtime. If a newer JDK is installed but the project is still configured with `--release 17`, `SequencedMap` and the new `LinkedHashMap` operations are not in the permitted API set.

Conversely, you cannot compile the examples for Java 21 and run the resulting class files on a Java 17 JVM. Check the JDK configuration in your IDE, compiler, and the environment used by the `java` command. This is a version-based API change, not a syntax error fixable by adding an import.

The programs use standard `LinkedHashMap` constructors with no preview language features or external libraries. `--release 21` in the compile command specifies the API/bytecode level required for this article.

## 14. Common mistakes

| Misconception | Consequence | Fix |
|---|---|---|
| First/last means smallest/largest key | Reading the wrong entry when the map is not key-sorted | Track the actual encounter order |
| Calling `poll` just to inspect | Mapping disappears unexpectedly | Use `firstEntry`/`lastEntry` to observe |
| Calling `.getKey()` directly on `firstEntry()` | Potential `NullPointerException` on an empty map | Check that the entry is non-`null` |
| `putFirst` on an existing key creates a duplicate | Incorrect size expectations | Understand it updates and repositions the same mapping |
| `put` on an existing key always moves it to the end | Wrong on insertion-order maps | Distinguish modes and positioning methods |
| `firstEntry().setValue(...)` updates the map | `UnsupportedOperationException` | Update via the appropriate map API |
| `reversed()` reverses the original map in place | Assuming all variables now have reversed order | Separate view direction from underlying data |
| `reversed()` creates an independent map | Mutating the view changes the original map | Create a new structure when independence is needed |
| `reverse.put(...)` appends to the end of the view | Wrong position with `LinkedHashMap` | Use explicit positioning methods when required |
| Removing first from reversed view removes first from original | Wrong entry removed | Reversed first corresponds to original last |
| A modifiable view supports `addFirst` | `UnsupportedOperationException` | Add full mappings through the map |
| `getFirst` on an empty view returns `null` | Unhandled `NoSuchElementException` | Follow each API's empty-state contract |
| Map equals reversed view means same order | Order checks miss bugs | Compare ordered lists when order matters |

## 15. Self-check and exercises

### 15.1. Questions

1. With original order `[A, B, C]`, which entry does `map.reversed().firstEntry()` observe?
2. How do `firstEntry` and `pollFirstEntry` differ in side effects?
3. Why is an `A=null` entry different from a `null` entry result?
4. Does `putFirst("B", value)` on a map already containing A, B, C increase its size?
5. After `reverse.putLast("D", 4)` where D is a new key, is D at the front or end of the original map?
6. Can you modify a value using `setValue` on an entry returned by `firstEntry`?
7. Does `map.sequencedKeySet().removeLast()` only edit a key set detached from the map?
8. Why does `sequencedValues()` not return `SequencedSet`?
9. Where does a successful `reverse.get("A")` on an access-order map place A in the original map and in the view?
10. Why can `map.equals(map.reversed())` be `true` even though their iteration orders differ?

### 15.2. Short answers

1. C; the front of the reversed view is the end of the original map.
2. `firstEntry` only inspects; `pollFirstEntry` retrieves the entry and removes the mapping. Both return `null` if the map is empty.
3. `A=null` is a real entry holding a `null` value; a `null` entry return value means there is no first entry because the map is empty.
4. No. It updates and moves mapping B to the front, changing the order to `[B, A, C]`.
5. Front of the original map, because the end of the reversed view corresponds to the start of the original map.
6. No; first–last snapshots in this article do not support `setValue`. Use the map's update operations.
7. No. The view is live-backed, so the last key's mapping is removed from the original map.
8. Because multiple distinct keys may map to the same value; the values view can contain duplicates.
9. End of the original map and front of the reversed view. The call records an access on the same underlying map.
10. Map equality checks the set of mappings, not the encounter order.

### 15.3. Exercise 1: repositioning without creating duplicate keys

Create an insertion-order map with `A=1, B=2, C=3`. Run `putFirst("B", 20)` followed by `putLast("A", 10)`. Before running, predict the old return value of each call, the final order, and the size.

Expected outcome: the two return values are `2` and `1` respectively; the final map is `{B=20, C=3, A=10}` with size three. If your prediction had four or five entries, you confused a map with a list that can hold multiple copies of the same key.

### 15.4. Exercise 2: confirm direction before removing

From original map `A=1, B=2, C=3`, create `reverse`. Run `reverse.putFirst("D", 4)` and then `reverse.pollLastEntry()`. Record both the original and reversed orders after each step.

Expected outcome: after putting D, original is `[A, B, C, D]` and reversed is `[D, C, B, A]`. Polling the last entry of the view removes `A=1`, leaving original `[B, C, D]` and reversed `[D, C, B]`. If D was removed instead, the first/last ends were mixed up.

### 15.5. Exercise 3: prove that a view and a copy behave differently

Create a reversed view and a `new LinkedHashMap<>(view)` from the same three-entry map. Then change B's value and add a new key through the original map. Print the original, the view, and the copy.

Verification criteria: the view sees B's new value and the new key in current reversed order; the copy retains the mappings and order from creation time. Next, remove a mapping through the view and confirm it disappears from the original map without disappearing from the copy.

### 15.6. Exercise 4: do not mix empty-state contracts

On an empty map, compare `firstEntry()` with `sequencedKeySet().getFirst()`. Next, add a mapping with a `null` key and `null` value and call both again.

Expected outcome: when empty, the map API returns a `null` entry, whereas the view API throws `NoSuchElementException`. Once the mapping exists, `firstEntry()` returns a non-`null` entry, while `getFirst()` on the key view returns the valid `null` key. You cannot check emptiness across all APIs with the same `== null` comparison.

## 16. Environment and references

The five standalone programs in this article were compiled with `javac --release 21 -encoding UTF-8` and run on JDK 24.0.2; stdout outputs were verified from those runs. `--release 21` checks Java 21 API usage at compile time; the runtime note states the exact JDK used. Each file contains a single `public` class matching its filename with no dependencies on other example files.

- [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): ordering modes, positioning methods, and the relationship between the map and its reversed view.
- [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): first–last mapping operations, entry snapshots, and ordering contracts.
- [SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): `getFirst/getLast`, `removeFirst/removeLast`, and empty-state behavior.
- [SequencedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): sets with encounter order and reversed views.
- [LinkedHashMap — OpenJDK 21 source](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/LinkedHashMap.java): reference for how the view forwards operations and swaps ends.
